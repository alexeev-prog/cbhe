import math
import mmap
import os
import shutil
import tempfile
from collections import OrderedDict
from typing import Optional

from .formats import FieldDef, FormatDef, detect_format, get_field_at
from .search import SearchPattern

_LARGE_FILE_THRESHOLD = 64 * 1024 * 1024
_SEARCH_CHUNK = 4 * 1024 * 1024


def _group_consecutive(offsets_vals: list[tuple[int, int]]) -> list[tuple[int, bytes]]:
    if not offsets_vals:
        return []

    groups: list[tuple[int, bytes]] = []
    sorted_pairs = sorted(offsets_vals, key=lambda p: p[0])

    run_start, run_bytes = sorted_pairs[0]
    run = bytearray([run_bytes])

    for offset, val in sorted_pairs[1:]:
        if offset == run_start + len(run):
            run.append(val)
        else:
            groups.append((run_start, bytes(run)))
            run_start = offset
            run = bytearray([val])

    groups.append((run_start, bytes(run)))
    return groups


class _LRURowCache:
    def __init__(self, capacity: int) -> None:
        self._cap = capacity
        self._store: OrderedDict[int, bytearray] = OrderedDict()

    def get(self, key: int) -> Optional[bytearray]:
        if key not in self._store:
            return None
        self._store.move_to_end(key)
        return self._store[key]

    def put(self, key: int, value: bytearray) -> None:
        if key in self._store:
            self._store.move_to_end(key)
        self._store[key] = value
        if len(self._store) > self._cap:
            self._store.popitem(last=False)

    def update(self, key: int, col: int, value: int) -> None:
        row = self._store.get(key)
        if row is not None and col < len(row):
            row[col] = value

    def clear(self) -> None:
        self._store.clear()

    def __contains__(self, key: int) -> bool:
        return key in self._store


class HexFile:
    CACHE_ROWS = 8192
    PREFETCH_ROWS = 512

    def __init__(self, path: str, width: int = 16, read_only: bool = False) -> None:
        if width not in (8, 16, 32):
            raise ValueError("width must be 8, 16 or 32")
        self.path = path
        self.read_only = read_only
        self.auto_detect = True
        self._target = os.path.realpath(path)
        self._snapshot = self._file_identity()
        self.width = width
        self.size = os.path.getsize(path)
        self._cache = _LRURowCache(self.CACHE_ROWS)
        self._dirty: dict[int, int] = {}
        self.file_format: Optional[FormatDef] = None
        self._mmap: Optional[mmap.mmap] = None
        self._mmap_fh = None
        self._use_mmap = self.size >= _LARGE_FILE_THRESHOLD
        self._open_mmap()
        self._detect_format()

    def _file_identity(self) -> tuple[int, int, int, int, int]:
        stat = os.stat(self._target)
        return (
            stat.st_dev,
            stat.st_ino,
            stat.st_size,
            stat.st_mtime_ns,
            stat.st_ctime_ns,
        )

    def _check_unchanged(self) -> None:
        if (
            os.path.realpath(self.path) != self._target
            or self._file_identity() != self._snapshot
        ):
            raise OSError("file changed on disk; reopen it or use Save As")

    def read_range(self, offset: int, length: int) -> bytes:
        if offset < 0 or length < 0:
            raise ValueError("negative offset or length")
        data = self._read_raw(offset, min(length, max(0, self.size - offset)))
        for pos, value in self._dirty.items():
            if offset <= pos < offset + len(data):
                data[pos - offset] = value
        return bytes(data)

    def _open_mmap(self) -> None:
        if not self._use_mmap or self.size == 0:
            return
        try:
            self._mmap_fh = open(self.path, "rb")  # type: ignore
            self._mmap = mmap.mmap(self._mmap_fh.fileno(), 0, access=mmap.ACCESS_READ)  # type: ignore
        except (OSError, ValueError):
            self._mmap = None
            if self._mmap_fh:
                self._mmap_fh.close()
                self._mmap_fh = None

    def _close_mmap(self) -> None:
        if self._mmap is not None:
            try:
                self._mmap.close()
            except Exception:
                pass
            self._mmap = None
        if self._mmap_fh is not None:
            try:
                self._mmap_fh.close()
            except Exception:
                pass
            self._mmap_fh = None

    def _detect_format(self) -> None:
        if not self.auto_detect:
            self.file_format = None
            return
        try:
            header = self._read_raw(0, 1024)
            self.file_format = detect_format(bytes(header))
        except (IOError, OSError):
            self.file_format = None

    def _read_raw(self, byte_start: int, length: int) -> bytearray:
        if self._mmap is not None:
            end = min(byte_start + length, self.size)
            return bytearray(self._mmap[byte_start:end])

        with open(self.path, "rb") as fh:
            fh.seek(byte_start)
            return bytearray(fh.read(length))

    def _load_region(self, anchor_row: int) -> None:
        row_start = max(0, anchor_row - self.PREFETCH_ROWS // 4)
        byte_start = row_start * self.width
        byte_len = min(self.PREFETCH_ROWS * self.width, self.size - byte_start)

        if byte_len <= 0:
            return

        raw = self._read_raw(byte_start, byte_len)

        for i in range(0, len(raw), self.width):
            r = row_start + i // self.width
            self._cache.put(r, bytearray(raw[i : i + self.width]))

    @property
    def total_rows(self) -> int:
        return math.ceil(self.size / self.width)

    @property
    def is_dirty(self) -> bool:
        return bool(self._dirty)

    @property
    def dirty_offsets(self) -> set[int]:
        return set(self._dirty.keys())

    def get_row(self, row: int) -> Optional[bytearray]:
        if not (0 <= row < self.total_rows):
            return None

        cached = self._cache.get(row)
        if cached is None:
            self._load_region(row)
            cached = self._cache.get(row)

        if cached is None:
            return None

        data = bytearray(cached)
        start_offset = row * self.width
        for col in range(len(data)):
            off = start_offset + col
            if off in self._dirty:
                data[col] = self._dirty[off]

        return data

    def write_byte(self, row: int, col: int, value: int) -> None:
        if self.read_only:
            raise PermissionError("file is read-only")
        offset = row * self.width + col
        if not (0 <= offset < self.size):
            return
        if not 0 <= value <= 255:
            raise ValueError("byte must be in range 0..255")
        original = self._read_raw(offset, 1)[0]
        if value == original:
            self._dirty.pop(offset, None)
        else:
            self._dirty[offset] = value

    def read_byte(self, offset: int) -> int:
        if offset in self._dirty:
            return self._dirty[offset]

        row = offset // self.width
        col = offset % self.width
        data = self.get_row(row)
        if data is None or col >= len(data):
            return 0
        return data[col]

    def save(self, backup: bool = True) -> None:
        if self.read_only:
            raise PermissionError("file is read-only; use Save As")
        if not self._dirty:
            return
        self._check_unchanged()
        self.save_as(self._target, overwrite=True, backup=backup)
        self._dirty.clear()
        self._cache.clear()
        self._snapshot = self._file_identity()
        self._use_mmap = self.size >= _LARGE_FILE_THRESHOLD
        self._close_mmap()
        self._open_mmap()
        self.file_format = None
        self._detect_format()

    def save_as(self, path: str, overwrite: bool = False, backup: bool = False) -> None:
        target = os.path.abspath(os.path.expanduser(path))
        same = os.path.realpath(target) == self._target
        if same:
            if self.read_only:
                raise PermissionError("cannot overwrite a read-only source")
            self._check_unchanged()
        if os.path.lexists(target) and not overwrite:
            raise FileExistsError(f"file already exists: {target}")
        fd, temp = tempfile.mkstemp(prefix=".cbhe-", dir=os.path.dirname(target))
        try:
            with os.fdopen(fd, "wb") as fh:
                for offset in range(0, self.size, _SEARCH_CHUNK):
                    fh.write(
                        self.read_range(offset, min(_SEARCH_CHUNK, self.size - offset))
                    )
                fh.flush()
                os.fsync(fh.fileno())
            shutil.copymode(self._target, temp)
            if same:
                self._check_unchanged()
            if backup and os.path.exists(target):
                # Never follow a pre-existing backup symlink or overwrite a backup.
                with open(target, "rb") as source, open(target + ".bak", "xb") as dest:
                    shutil.copyfileobj(source, dest)
                    dest.flush()
                    os.fsync(dest.fileno())
            if overwrite:
                os.replace(temp, target)
            else:
                os.link(temp, target)
        finally:
            if os.path.exists(temp):
                os.unlink(temp)

    def set_width(self, width: int) -> None:
        if width not in (8, 16, 32):
            raise ValueError("width must be 8, 16 or 32")
        self.width = width
        self._cache.clear()

    def find_bytes(self, query: bytes, start: int = 0) -> Optional[int]:
        if not query:
            return None
        return self.find_pattern(SearchPattern.exact(query), start)

    def find_bytes_backward(self, query: bytes, start: int) -> Optional[int]:
        if not query:
            return None
        return self.find_pattern(SearchPattern.exact(query), start, backward=True)

    def find_pattern(
        self, pattern: SearchPattern, start: int = 0, backward: bool = False
    ) -> Optional[int]:
        length = len(pattern.values)
        limit = max(0, self.size - length + 1)
        exact = all(mask == 255 for mask in pattern.masks)
        regex = None if exact else pattern.compile()
        stop = min(max(0, start), limit) if backward else limit
        offset = 0 if backward else max(0, start)
        while (stop > 0) if backward else (offset < limit):
            if backward:
                offset = max(0, stop - _SEARCH_CHUNK)
            end = stop if backward else min(limit, offset + _SEARCH_CHUNK)
            data = self.read_range(offset, end - offset + length - 1)
            if exact:
                idx = (
                    data.rfind(pattern.values)
                    if backward
                    else data.find(pattern.values)
                )
            else:
                assert regex is not None
                if backward:
                    idx = -1
                    for match in regex.finditer(data):
                        idx = match.start()
                else:
                    match = regex.search(data)
                    idx = match.start() if match else -1
            if idx >= 0:
                return offset + idx
            if backward:
                stop = offset
            else:
                offset = end
        return None

    def find_difference(
        self, other: "HexFile", start: int = 0, backward: bool = False
    ) -> Optional[int]:
        size = max(self.size, other.size)
        stop = min(max(0, start), size) if backward else size
        offset = 0 if backward else max(0, start)
        while (stop > 0) if backward else (offset < size):
            if backward:
                offset = max(0, stop - _SEARCH_CHUNK)
            end = stop if backward else min(size, offset + _SEARCH_CHUNK)
            left = self.read_range(offset, end - offset)
            right = other.read_range(offset, end - offset)
            if left != right:
                indices = (
                    range(end - offset - 1, -1, -1) if backward else range(end - offset)
                )
                for i in indices:
                    if (left[i] if i < len(left) else None) != (
                        right[i] if i < len(right) else None
                    ):
                        return offset + i
            if backward:
                stop = offset
            else:
                offset = end
        return None

    def find_ascii(self, query: bytes, start: int = 0) -> Optional[int]:
        return self.find_bytes(query, start)

    def get_field_at(self, offset: int) -> Optional[FieldDef]:
        if self.file_format is None:
            return None
        return get_field_at(offset, self.file_format)

    @property
    def format_name(self) -> str:
        if self.file_format is None:
            return "raw"
        return self.file_format.name

    def __del__(self) -> None:
        self.close()

    def close(self) -> None:
        if hasattr(self, "_mmap"):
            self._close_mmap()
