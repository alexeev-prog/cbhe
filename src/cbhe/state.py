from collections import deque
from dataclasses import dataclass, field
from typing import Optional

from .constants import (
    ASCII_PRINTABLE_END,
    ASCII_PRINTABLE_START,
    UNDO_LIMIT,
    WIDTH_CYCLES,
    EditorMode,
)
from .hexfile import HexFile


@dataclass
class _UndoEntry:
    row: int
    col: int
    old_val: int
    new_val: int


@dataclass
class SearchState:
    query: bytes = b""
    last_offset: int = -1
    match_len: int = 0
    is_hex: bool = False


@dataclass
class StatusMessage:
    text: str = ""
    is_error: bool = False


@dataclass
class EditorState:
    hf: HexFile
    top_row: int = 0
    mode: EditorMode = EditorMode.READ
    editing: bool = False
    cur_row: int = 0
    cur_col: int = 0
    hex_nibble: int = 0
    show_interpret: bool = False
    search: SearchState = field(default_factory=SearchState)
    status: StatusMessage = field(default_factory=StatusMessage)
    _undo_stack: deque[_UndoEntry] = field(
        default_factory=lambda: deque(maxlen=UNDO_LIMIT), init=False, repr=False
    )
    _redo_stack: deque[_UndoEntry] = field(
        default_factory=lambda: deque(maxlen=UNDO_LIMIT), init=False, repr=False
    )

    @property
    def cursor(self) -> Optional[tuple[int, int]]:
        return (self.cur_row, self.cur_col) if self.mode != EditorMode.READ else None

    @property
    def in_hex_panel(self) -> bool:
        return self.mode == EditorMode.HEX

    @property
    def in_ascii_panel(self) -> bool:
        return self.mode == EditorMode.ASCII

    @property
    def cursor_offset(self) -> int:
        return self.cur_row * self.hf.width + self.cur_col

    def toggle_interpret(self) -> None:
        self.show_interpret = not self.show_interpret

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

    def set_mode(self, mode: EditorMode) -> None:
        self.mode = mode
        self.editing = False
        self.hex_nibble = 0
        if mode != EditorMode.READ:
            self.cur_row = self.top_row
            self.cur_col = 0

    def enter_edit(self) -> None:
        if self.mode != EditorMode.READ:
            self.editing = True
            self.hex_nibble = 0

    def exit_edit(self) -> None:
        self.editing = False
        self.hex_nibble = 0

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
        self.hex_nibble = 0

    def _record_write(self, row: int, col: int, new_val: int) -> None:
        old_val = self.hf.read_byte(row * self.hf.width + col)
        self.hf.write_byte(row, col, new_val)
        entry = _UndoEntry(row=row, col=col, old_val=old_val, new_val=new_val)
        self._undo_stack.append(entry)
        self._redo_stack.clear()

    def write_hex_nibble(self, nibble: int) -> None:
        offset = self.cur_row * self.hf.width + self.cur_col
        current = self.hf.read_byte(offset)

        if self.hex_nibble == 0:
            new_val = (nibble << 4) | (current & 0x0F)
            self._record_write(self.cur_row, self.cur_col, new_val)
            self.hex_nibble = 1
        else:
            current_in_file = self.hf.read_byte(offset)
            new_val = (current_in_file & 0xF0) | nibble
            self._record_write(self.cur_row, self.cur_col, new_val)
            self.hex_nibble = 0
            self.move_cursor(0, 1)

    def write_ascii(self, char: str) -> None:
        if ASCII_PRINTABLE_START <= ord(char) <= ASCII_PRINTABLE_END:
            self._record_write(self.cur_row, self.cur_col, ord(char))
            self.move_cursor(0, 1)

    def delete_forward(self) -> None:
        self._record_write(self.cur_row, self.cur_col, 0x00)
        self.move_cursor(0, 1)

    def delete_backward(self) -> None:
        self.move_cursor(0, -1)
        self._record_write(self.cur_row, self.cur_col, 0x00)

    def undo(self) -> None:
        if not self._undo_stack:
            self.status = StatusMessage("nothing to undo", is_error=True)
            return
        entry = self._undo_stack.pop()
        self.hf.write_byte(entry.row, entry.col, entry.old_val)
        self._redo_stack.append(entry)
        self.cur_row = entry.row
        self.cur_col = entry.col
        self.status = StatusMessage(
            f"undo → {entry.old_val:02x} at {entry.row * self.hf.width + entry.col:08x}"
        )

    def redo(self) -> None:
        if not self._redo_stack:
            self.status = StatusMessage("nothing to redo", is_error=True)
            return
        entry = self._redo_stack.pop()
        self.hf.write_byte(entry.row, entry.col, entry.new_val)
        self._undo_stack.append(entry)
        self.cur_row = entry.row
        self.cur_col = entry.col
        self.status = StatusMessage(
            f"redo → {entry.new_val:02x} at {entry.row * self.hf.width + entry.col:08x}"
        )

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

    def _apply_search_result(
        self, found: Optional[int], visible: int, wrapped_msg: str
    ) -> bool:
        if found is None:
            self.status = StatusMessage(
                f"not found: {self.search.query!r}", is_error=True
            )
            return False
        self.search.last_offset = found
        self.search.match_len = len(self.search.query)
        self.jump_to_offset(found, visible)
        return True

    def search_next(self, visible: int) -> bool:
        if not self.search.query:
            return False
        start = self.cur_row * self.hf.width + self.cur_col + 1
        found = self.hf.find_bytes(self.search.query, start)
        if found is None:
            found = self.hf.find_bytes(self.search.query, 0)
            if found is not None:
                self.status = StatusMessage("search wrapped to start")
        return self._apply_search_result(found, visible, "search wrapped to start")

    def search_prev(self, visible: int) -> bool:
        if not self.search.query:
            return False
        current = self.cur_row * self.hf.width + self.cur_col
        found = self.hf.find_bytes_backward(self.search.query, current)
        if found is None:
            found = self.hf.find_bytes_backward(self.search.query, self.hf.size)
            if found is not None:
                self.status = StatusMessage("search wrapped to end")
        return self._apply_search_result(found, visible, "search wrapped to end")
