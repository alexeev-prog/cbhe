from dataclasses import dataclass
from typing import Optional

from .constants import ASCII_PRINTABLE_END, ASCII_PRINTABLE_START, WIDTH_CYCLES
from .hexfile import HexFile


@dataclass
class EditorState:
    hf: HexFile
    top_row: int = 0
    editing: bool = False
    cur_row: int = 0
    cur_col: int = 0

    @property
    def cursor(self) -> Optional[tuple[int, int]]:
        return (self.cur_row, self.cur_col) if self.editing else None

    def clamp_top(self, visible: int) -> None:
        self.top_row = max(0, min(self.top_row, self.hf.total_rows - visible))

    def scroll(self, delta: int, visible: int) -> None:
        self.top_row = max(
            0,
            min(self.top_row + delta, self.hf.total_rows - visible),
        )

    def cycle_width(self) -> None:
        idx = WIDTH_CYCLES.index(self.hf.width)
        self.hf.set_width(WIDTH_CYCLES[(idx + 1) % len(WIDTH_CYCLES)])
        self.top_row = 0

    def enter_edit(self) -> None:
        self.editing = True
        self.cur_row = self.top_row
        self.cur_col = 0

    def exit_edit(self) -> None:
        self.editing = False

    def _max_col(self, row: int) -> int:
        data = self.hf.get_row(row)
        return (len(data) - 1) if data else 0

    def move_cursor(self, dr: int, dc: int) -> None:
        col = self.cur_col + dc
        row = self.cur_row + dr
        w = self.hf.width

        if col < 0:
            col, row = w - 1, row - 1
        elif col >= w:
            col, row = 0, row + 1

        row = max(0, min(row, self.hf.total_rows - 1))
        col = min(col, self._max_col(row))
        self.cur_row = row
        self.cur_col = col

    def write_ascii(self, char: str) -> None:
        if ASCII_PRINTABLE_START <= ord(char) <= ASCII_PRINTABLE_END:
            self.hf.write_byte(self.cur_row, self.cur_col, ord(char))
            self.move_cursor(0, 1)

    def delete_forward(self) -> None:
        self.hf.write_byte(self.cur_row, self.cur_col, 0x00)
        self.move_cursor(0, 1)

    def delete_backward(self) -> None:
        self.move_cursor(0, -1)
        self.hf.write_byte(self.cur_row, self.cur_col, 0x00)

    def sync_scroll(self, visible: int) -> None:
        if self.cur_row < self.top_row:
            self.top_row = self.cur_row
        elif self.cur_row >= self.top_row + visible:
            self.top_row = self.cur_row - visible + 1

    def jump_to_offset(self, offset: int, visible: int) -> None:
        row = offset // self.hf.width
        col = offset % self.hf.width

        self.cur_row = max(0, min(row, self.hf.total_rows - 1))
        self.cur_col = max(0, min(col, self._max_col(self.cur_row)))
        self.top_row = max(
            0,
            min(self.cur_row - visible // 2, self.hf.total_rows - visible),
        )
