import math
import mmap
import os
from collections import OrderedDict
from typing import Optional

from .formats import FieldDef, FormatDef, detect_format, get_field_at

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

    def __init__(self, path: str, width: int = 16) -> None:
        self.path = path
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
        offset = row * self.width + col
        if offset >= self.size:
            return

        self._dirty[offset] = value
        self._cache.update(row, col, value)

    def read_byte(self, offset: int) -> int:
        if offset in self._dirty:
            return self._dirty[offset]

        row = offset // self.width
        col = offset % self.width
        data = self.get_row(row)
        if data is None or col >= len(data):
            return 0
        return data[col]

    def save(self) -> None:
        if not self._dirty:
            return

        groups = _group_consecutive(list(self._dirty.items()))

        self._close_mmap()

        with open(self.path, "r+b") as fh:
            for offset, block in groups:
                fh.seek(offset)
                fh.write(block)

        self._dirty.clear()
        self._cache.clear()

        self._use_mmap = self.size >= _LARGE_FILE_THRESHOLD
        self._open_mmap()
        self.file_format = None
        self._detect_format()

    def set_width(self, width: int) -> None:
        self.width = width
        self._cache.clear()

    def find_bytes(self, query: bytes, start: int = 0) -> Optional[int]:
        if not query:
            return None

        if self._mmap is not None:
            idx = self._mmap.find(query, max(0, start))
            return idx if idx != -1 else None

        overlap = len(query) - 1
        chunk_size = _SEARCH_CHUNK
        offset = max(0, start - overlap)
        prev_tail = b""

        with open(self.path, "rb") as fh:
            fh.seek(offset)
            while True:
                chunk = fh.read(chunk_size)
                if not chunk:
                    break

                search_data = prev_tail + chunk
                idx = search_data.find(query)
                if idx != -1:
                    found = offset + idx - len(prev_tail)
                    if found >= start:
                        return found

                prev_tail = chunk[-overlap:] if overlap else b""
                offset += len(chunk)

        return None

    def find_bytes_backward(self, query: bytes, start: int) -> Optional[int]:
        if not query:
            return None

        if self._mmap is not None:
            search_end = min(start + len(query) - 1, self.size)
            idx = self._mmap.rfind(query, 0, search_end)
            if idx != -1 and idx < start:
                return idx
            return None

        with open(self.path, "rb") as fh:
            search_end = min(start + len(query) - 1, self.size)
            fh.seek(0)
            data = fh.read(search_end)

        idx = data.rfind(query, 0, start)
        return idx if idx != -1 else None

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
        self._close_mmap()
