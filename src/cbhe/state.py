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
from .search import SearchPattern


@dataclass
class _UndoEntry:
    offset: int
    old_val: int
    new_val: int


@dataclass
class SearchState:
    query: bytes = b""
    last_offset: int = -1
    match_len: int = 0
    is_hex: bool = False
    pattern: SearchPattern | None = None


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
    comparison: HexFile | None = None
    selection_anchor: int | None = None
    clipboard: bytes = b""
    show_structure: bool = False
    structure_index: int = 0
    show_help: bool = False
    search: SearchState = field(default_factory=SearchState)
    status: StatusMessage = field(default_factory=StatusMessage)
    _undo_stack: deque[list[_UndoEntry]] = field(
        default_factory=lambda: deque(maxlen=UNDO_LIMIT), init=False, repr=False
    )
    _redo_stack: deque[list[_UndoEntry]] = field(
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
        offset = self.cursor_offset
        top = self.top_row * self.hf.width
        idx = WIDTH_CYCLES.index(self.hf.width)
        self.hf.set_width(WIDTH_CYCLES[(idx + 1) % len(WIDTH_CYCLES)])
        self.cur_row, self.cur_col = divmod(offset, self.hf.width)
        self.top_row = top // self.hf.width

    def set_mode(self, mode: EditorMode) -> None:
        previous = self.mode
        self.mode = mode
        self.editing = False
        self.hex_nibble = 0
        if mode != EditorMode.READ and previous == EditorMode.READ:
            self.cur_row = self.top_row
            self.cur_col = 0

    def enter_edit(self) -> None:
        if self.hf.read_only:
            self.status = StatusMessage("read-only file; use Save As", is_error=True)
            return
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
        offset = row * self.hf.width + col
        if not 0 <= offset < self.hf.size:
            return
        old_val = self.hf.read_byte(offset)
        if old_val == new_val:
            return
        self.hf.write_byte(row, col, new_val)
        entry = _UndoEntry(offset=offset, old_val=old_val, new_val=new_val)
        self._undo_stack.append([entry])
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
        entries = self._undo_stack.pop()
        for entry in reversed(entries):
            row, col = divmod(entry.offset, self.hf.width)
            self.hf.write_byte(row, col, entry.old_val)
        entry = entries[0]
        row, col = divmod(entry.offset, self.hf.width)
        self._redo_stack.append(entries)
        self.cur_row = row
        self.cur_col = col
        self.status = StatusMessage(f"undo → {entry.old_val:02x} at {entry.offset:08x}")

    def redo(self) -> None:
        if not self._redo_stack:
            self.status = StatusMessage("nothing to redo", is_error=True)
            return
        entries = self._redo_stack.pop()
        for entry in entries:
            row, col = divmod(entry.offset, self.hf.width)
            self.hf.write_byte(row, col, entry.new_val)
        entry = entries[0]
        row, col = divmod(entry.offset, self.hf.width)
        self._undo_stack.append(entries)
        self.cur_row = row
        self.cur_col = col
        self.status = StatusMessage(f"redo → {entry.new_val:02x} at {entry.offset:08x}")

    def sync_scroll(self, visible: int) -> None:
        if self.cur_row < self.top_row:
            self.top_row = self.cur_row
        elif self.cur_row >= self.top_row + visible:
            self.top_row = self.cur_row - visible + 1

    def jump_to_offset(self, offset: int, visible: int) -> None:
        offset = max(0, min(offset, max(0, self.hf.size - 1)))
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
        pattern = self.search.pattern or SearchPattern.exact(self.search.query)
        found = self.hf.find_pattern(pattern, start)
        if found is None:
            found = self.hf.find_pattern(pattern, 0)
            if found is not None:
                self.status = StatusMessage("search wrapped to start")
        return self._apply_search_result(found, visible, "search wrapped to start")

    def search_prev(self, visible: int) -> bool:
        if not self.search.query:
            return False
        current = self.cur_row * self.hf.width + self.cur_col
        pattern = self.search.pattern or SearchPattern.exact(self.search.query)
        found = self.hf.find_pattern(pattern, current, backward=True)
        if found is None:
            found = self.hf.find_pattern(pattern, self.hf.size, backward=True)
            if found is not None:
                self.status = StatusMessage("search wrapped to end")
        return self._apply_search_result(found, visible, "search wrapped to end")

    @property
    def selection(self) -> tuple[int, int] | None:
        if self.selection_anchor is None or not self.hf.size:
            return None
        start, end = sorted((self.selection_anchor, self.cursor_offset))
        return start, end + 1

    def toggle_selection(self) -> None:
        if self.mode == EditorMode.READ:
            self.set_mode(EditorMode.HEX)
        self.selection_anchor = (
            self.cursor_offset if self.selection_anchor is None else None
        )

    def copy_selection(self) -> None:
        bounds = self.selection
        if bounds is None:
            raise ValueError("select a range with v first")
        start, end = bounds
        if end - start > 16 * 1024 * 1024:
            raise ValueError("copy limit is 16 MiB; export the range instead")
        self.clipboard = self.hf.read_range(start, end - start)
        self.status = StatusMessage(
            f"copied {len(self.clipboard)} bytes (internal buffer)"
        )

    def export_selection(self, path: str) -> None:
        bounds = self.selection
        if bounds is None:
            raise ValueError("select a range with v first")
        start, end = bounds
        with open(path, "xb") as fh:
            for offset in range(start, end, 1024 * 1024):
                fh.write(self.hf.read_range(offset, min(1024 * 1024, end - offset)))
        self.status = StatusMessage(f"exported {end - start} bytes")

    def replace_range(self, data: bytes, fill: bool = False) -> None:
        if self.hf.read_only:
            raise PermissionError("file is read-only")
        if not data:
            raise ValueError("internal buffer is empty")
        bounds = self.selection if fill else None
        start, end = bounds or (self.cursor_offset, self.cursor_offset + len(data))
        if fill and bounds is None:
            raise ValueError("select a range with v first")
        if end > self.hf.size:
            raise ValueError("paste would extend beyond end of file")
        if end - start > 1024 * 1024:
            raise ValueError("fill/paste limit is 1 MiB; use smaller ranges")
        entries = []
        for offset in range(start, end):
            row, col = divmod(offset, self.hf.width)
            old_val = self.hf.read_byte(offset)
            new_val = data[(offset - start) % len(data)]
            if old_val != new_val:
                self.hf.write_byte(row, col, new_val)
                entries.append(_UndoEntry(offset, old_val, new_val))
        if entries:
            self._undo_stack.append(entries)
            self._redo_stack.clear()
        self.status = StatusMessage(f"updated {len(entries)} bytes; u to undo range")

    def difference(self, visible: int, backward: bool = False) -> None:
        if self.comparison is None:
            raise ValueError("open a comparison file with c first")
        start = self.cursor_offset if backward else self.cursor_offset + 1
        found = self.hf.find_difference(self.comparison, start, backward)
        if found is None:
            start = max(self.hf.size, self.comparison.size) if backward else 0
            found = self.hf.find_difference(self.comparison, start, backward)
        if found is None:
            self.status = StatusMessage("files are identical")
            return
        if self.mode == EditorMode.READ:
            self.set_mode(EditorMode.HEX)
        self.jump_to_offset(found, visible)
        suffix = " (comparison-only tail)" if found >= self.hf.size else ""
        self.status = StatusMessage(f"difference at {found:08x}{suffix}")
