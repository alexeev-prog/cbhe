import math
import os
from typing import Optional


class HexFile:
    CHUNK_BYTES = 65536
    CACHE_ROWS = 4096

    def __init__(self, path: str, width: int = 16) -> None:
        self.path = path
        self.width = width
        self.size = os.path.getsize(path)
        self._cache: dict[int, bytearray] = {}
        self._dirty: dict[int, int] = {}

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

    def save(self) -> None:
        if not self._dirty:
            return

        with open(self.path, "r+b") as fh:
            for offset, val in sorted(self._dirty.items()):
                fh.seek(offset)
                fh.write(bytes([val]))

        self._dirty.clear()

    def set_width(self, width: int) -> None:
        self.width = width
        self._cache.clear()

    def find_ascii(self, query: bytes) -> Optional[int]:
        if not query:
            return None

        chunk_size = 1024 * 1024
        offset = 0
        prev_tail = b""

        with open(self.path, "rb") as fh:
            while True:
                chunk = fh.read(chunk_size)
                if not chunk:
                    break

                search_data = prev_tail + chunk
                idx = search_data.find(query)
                if idx != -1:
                    return offset + idx - len(prev_tail)

                prev_tail = (
                    chunk[-(len(query) - 1) :] if len(chunk) >= len(query) else chunk
                )
                offset += len(chunk)

        return None
