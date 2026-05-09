import math
import os
from typing import Optional

from .formats import FieldDef, FormatDef, detect_format, get_field_at


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


class HexFile:
    CHUNK_BYTES = 65536
    CACHE_ROWS = 4096

    def __init__(self, path: str, width: int = 16) -> None:
        self.path = path
        self.width = width
        self.size = os.path.getsize(path)
        self._cache: dict[int, bytearray] = {}
        self._dirty: dict[int, int] = {}
        self.file_format: Optional[FormatDef] = None
        self._detect_format()

    def _detect_format(self) -> None:
        try:
            with open(self.path, "rb") as fh:
                header = fh.read(1024)
            self.file_format = detect_format(header)
        except (IOError, OSError):
            self.file_format = None

    @property
    def total_rows(self) -> int:
        return math.ceil(self.size / self.width)

    @property
    def is_dirty(self) -> bool:
        return bool(self._dirty)

    @property
    def dirty_offsets(self) -> set[int]:
        return set(self._dirty.keys())

    def _load_region(self, row_start: int) -> None:
        self._cache.clear()
        byte_start = row_start * self.width
        byte_end = min(byte_start + self.CACHE_ROWS * self.width, self.size)

        with open(self.path, "rb") as fh:
            fh.seek(byte_start)
            raw = fh.read(byte_end - byte_start)

        for i in range(0, len(raw), self.width):
            self._cache[row_start + i // self.width] = bytearray(
                raw[i : i + self.width]
            )

    def get_row(self, row: int) -> Optional[bytearray]:
        if not (0 <= row < self.total_rows):
            return None

        if row not in self._cache:
            self._load_region(max(0, row - self.CACHE_ROWS // 4))

        data = self._cache.get(row)
        if data is None:
            return None

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

        if row in self._cache:
            cache_data = self._cache[row]
            if col < len(cache_data):
                cache_data[col] = value

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

        with open(self.path, "r+b") as fh:
            for offset, block in groups:
                fh.seek(offset)
                fh.write(block)

        self._dirty.clear()
        self.file_format = None
        self._detect_format()

    def set_width(self, width: int) -> None:
        self.width = width
        self._cache.clear()

    def find_bytes(self, query: bytes, start: int = 0) -> Optional[int]:
        if not query:
            return None

        chunk_size = 1024 * 1024
        overlap = len(query) - 1
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

        with open(self.path, "rb") as fh:
            search_end = min(start + len(query) - 1, self.size)
            fh.seek(0)
            data = fh.read(search_end)

        idx = data.rfind(query, 0, start)
        if idx != -1:
            return idx

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
            return "none"
        return self.file_format.name
