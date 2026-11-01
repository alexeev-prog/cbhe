import curses
from typing import Any, Optional

from .colors import ascii_color, field_color, hex_color
from .constants import (
    INTERPRET_PANEL_WIDTH,
    KEYBINDS_EDIT,
    KEYBINDS_NORMAL,
    KEYBINDS_READ,
    PAIR_ADDR,
    PAIR_CURSOR,
    PAIR_DIRTY,
    PAIR_HEADER,
    PAIR_HEADER_EDIT,
    PAIR_HIGHLIGHT,
    PAIR_INTERPRET_BORDER,
    PAIR_INTERPRET_LABEL,
    PAIR_INTERPRET_VALUE,
    PAIR_KEYBINDS,
    PAIR_KEYBINDS_EDIT,
    PAIR_SEARCH_MATCH,
    PAIR_SEP,
    PAIR_STATUS,
    PAIR_STATUS_FIELD,
    EditorMode,
    human_size,
)
from .hexfile import HexFile
from .interpret import InterpretRow, interpret_at
from .state import EditorState

_MODE_LABELS: dict[tuple[EditorMode, bool], str] = {
    (EditorMode.READ, False): "READ",
    (EditorMode.HEX, False): "HEX",
    (EditorMode.HEX, True): "HEX·EDIT",
    (EditorMode.ASCII, False): "ASCII",
    (EditorMode.ASCII, True): "ASCII·EDIT",
}


def _addstr(win: Any, y: int, x: int, text: str, attr: int = 0) -> int:
    h, w = win.getmaxyx()

    if y < 0 or x < 0 or y >= h or x >= w:
        return x

    text = text[: w - x - 1]
    if text:
        try:
            win.addstr(y, x, text, attr)
        except curses.error:
            pass

    return x + len(text)


def _status_offset(state: EditorState) -> int:
    if state.mode == EditorMode.READ:
        return state.top_row * state.hf.width
    return state.cursor_offset


def draw_header(win: Any, hf: HexFile, state: EditorState) -> None:
    _, w = win.getmaxyx()
    pct = 100 * state.top_row // max(1, hf.total_rows - 1)
    dirty_mark = " * " if hf.is_dirty else "   "

    mode_label = _MODE_LABELS.get((state.mode, state.editing), "READ")

    basename = hf.path.split("/")[-1]
    hsize = human_size(hf.size)

    interpret_mark = " [I]" if state.show_interpret else ""
    if hf.read_only:
        interpret_mark += " [RO]"
    if state.comparison:
        interpret_mark += " [DIFF]"
    title = (
        f"  cbhe  {mode_label}{interpret_mark} {dirty_mark}│  {basename}  │  "
        f"{hsize}  │  :{hf.width}  │  {hf.format_name.upper()}  │  {pct:3d}%  "
    )

    pair = PAIR_HEADER_EDIT if state.editing else PAIR_HEADER
    _addstr(win, 0, 0, title.ljust(w - 1), curses.color_pair(pair))


def draw_status(win: Any, state: EditorState) -> None:
    h, w = win.getmaxyx()
    y = h - 2

    if state.status.text:
        attr = curses.color_pair(PAIR_DIRTY if state.status.is_error else PAIR_STATUS)
        _addstr(win, y, 0, ("  " + state.status.text).ljust(w - 1), attr)
        return

    hf = state.hf
    offset = _status_offset(state)
    bval = hf.read_byte(offset)
    field_def = hf.get_field_at(offset)

    char_repr = chr(bval) if 32 <= bval <= 126 else "·"

    base = curses.color_pair(PAIR_STATUS)
    bold = base | curses.A_BOLD

    x = _addstr(win, y, 0, "  ", base)
    x = _addstr(win, y, x, "off:", base)
    x = _addstr(win, y, x, f"{offset:08x}", bold)
    x = _addstr(win, y, x, "  dec:", base)
    x = _addstr(win, y, x, f"{offset}", bold)
    x = _addstr(win, y, x, "  val:", base)
    x = _addstr(win, y, x, f"{bval:02x}", bold)
    x = _addstr(win, y, x, "  dec:", base)
    x = _addstr(win, y, x, f"{bval:3d}", bold)
    x = _addstr(win, y, x, "  chr:", base)
    x = _addstr(win, y, x, f"{char_repr}", bold)

    if field_def:
        x = _addstr(win, y, x, "  │  ", curses.color_pair(PAIR_SEP))
        pair_id = curses.color_pair(PAIR_STATUS_FIELD)
        x = _addstr(win, y, x, f"{field_def.name}", pair_id | curses.A_BOLD)
        x = _addstr(win, y, x, f" [{field_def.ftype.name}]", pair_id)

    if state.selection:
        start, end = state.selection
        x = _addstr(win, y, x, f"  sel:{start:x}..{end - 1:x} ({end - start} B)", bold)
    if state.comparison:
        other = state.comparison
        value = other.read_range(offset, 1)
        text = value.hex() if value else "EOF"
        x = _addstr(win, y, x, f"  other:{text} size:{other.size}", bold)

    status_msg = state.status.text
    if status_msg:
        err_attr = (
            curses.color_pair(PAIR_DIRTY)
            if state.status.is_error
            else base | curses.A_DIM
        )
        msg_x = max(x + 2, w - len(status_msg) - 2)
        _addstr(win, y, msg_x, status_msg, err_attr)

    try:
        win.clrtoeol()
    except curses.error:
        pass


def draw_keybinds(win: Any, state: EditorState) -> None:
    h, w = win.getmaxyx()
    y = h - 1
    x = 0

    if state.mode == EditorMode.READ:
        keybinds = KEYBINDS_READ
    elif state.editing:
        keybinds = KEYBINDS_EDIT
    else:
        keybinds = KEYBINDS_NORMAL

    pair = PAIR_KEYBINDS_EDIT if state.editing else PAIR_KEYBINDS
    base = curses.color_pair(pair)
    bold = base | curses.A_BOLD

    for key, label in keybinds:
        needed = len(key) + len(label) + 3
        if x + needed >= w:
            break
        x = _addstr(win, y, x, f" {key}", bold)
        x = _addstr(win, y, x, f":{label} ", base)

    _addstr(win, y, x, " " * max(0, w - x - 1), base)


def _is_search_match(offset: int, state: EditorState) -> bool:
    if not state.search.query or state.search.last_offset < 0:
        return False
    match_start = state.search.last_offset
    match_end = match_start + state.search.match_len
    return match_start <= offset < match_end


def _byte_attr(
    offset: int,
    col: int,
    b: int,
    cursor_col: Optional[int],
    mirror_col: Optional[int],
    dirty_offsets: set[int],
    hf: HexFile,
    state: EditorState,
    use_hex_color: bool,
) -> int:
    if col == cursor_col:
        return curses.color_pair(PAIR_CURSOR)
    if col == mirror_col:
        return curses.color_pair(PAIR_HIGHLIGHT)
    if offset in dirty_offsets:
        return curses.color_pair(PAIR_DIRTY)
    if state.selection:
        start, end = state.selection
        if start <= offset < end:
            return curses.color_pair(PAIR_SEARCH_MATCH) | curses.A_UNDERLINE
    if state.comparison:
        other = state.comparison
        if offset >= other.size or other.read_byte(offset) != b:
            return curses.color_pair(PAIR_DIRTY) | curses.A_BOLD | curses.A_UNDERLINE
    if _is_search_match(offset, state):
        return curses.color_pair(PAIR_SEARCH_MATCH)

    field_def = hf.get_field_at(offset)
    if field_def is not None:
        return field_color(field_def.ftype.name)

    return hex_color(b) if use_hex_color else ascii_color(b)


def _draw_hex_part(
    win: Any,
    y: int,
    x: int,
    data: bytearray,
    width: int,
    row: int,
    cursor_col: Optional[int],
    mirror_col: Optional[int],
    hex_nibble: int,
    editing: bool,
    dirty_offsets: set[int],
    hf: HexFile,
    state: EditorState,
) -> int:
    for gi in range(0, width, 4):
        if gi > 0:
            x = _addstr(win, y, x, " ╌", curses.color_pair(PAIR_SEP))

        for bi in range(4):
            idx = gi + bi
            if bi > 0:
                x = _addstr(win, y, x, " ", curses.color_pair(PAIR_SEP))

            if idx < len(data):
                b = data[idx]
                offset = row * width + idx
                attr = _byte_attr(
                    offset,
                    idx,
                    b,
                    cursor_col,
                    mirror_col,
                    dirty_offsets,
                    hf,
                    state,
                    use_hex_color=True,
                )

                hi = f"{b:02x}"
                if idx == cursor_col and editing:
                    for nibble, char in enumerate(hi):
                        nibble_attr = (
                            attr | curses.A_UNDERLINE | curses.A_BOLD
                            if nibble == hex_nibble
                            else attr
                        )
                        x = _addstr(win, y, x, char, nibble_attr)
                else:
                    x = _addstr(win, y, x, hi, attr)
            else:
                x = _addstr(win, y, x, "  ", curses.color_pair(PAIR_SEP))

    return x


def _draw_ascii_part(
    win: Any,
    y: int,
    x: int,
    data: bytearray,
    width: int,
    row: int,
    cursor_col: Optional[int],
    mirror_col: Optional[int],
    dirty_offsets: set[int],
    hf: HexFile,
    state: EditorState,
) -> None:
    _, w = win.getmaxyx()

    for i in range(min(width, len(data))):
        if x >= w - 1:
            break

        b = data[i]
        ch = chr(b) if 32 <= b <= 126 else "·"
        offset = row * width + i
        attr = _byte_attr(
            offset,
            i,
            b,
            cursor_col,
            mirror_col,
            dirty_offsets,
            hf,
            state,
            use_hex_color=False,
        )
        x = _addstr(win, y, x, ch, attr)


def _resolve_cursor_cols(
    row: int,
    state: EditorState,
) -> tuple[Optional[int], Optional[int], Optional[int], Optional[int]]:
    cursor = state.cursor
    if not cursor or cursor[0] != row:
        return None, None, None, None

    col = cursor[1]
    if state.mode == EditorMode.HEX:
        return col, None, None, col
    if state.mode == EditorMode.ASCII:
        return None, col, col, None
    return None, None, None, None


def draw_hex_row(
    win: Any,
    y: int,
    row: int,
    data: bytearray,
    state: EditorState,
    dirty_offsets: set[int],
    is_focus_row: bool,
) -> None:
    h, w = win.getmaxyx()
    if y >= h - 1:
        return

    hf = state.hf
    width = hf.width

    cursor_col_hex, cursor_col_ascii, mirror_col_hex, mirror_col_ascii = (
        _resolve_cursor_cols(row, state)
    )

    addr_attr = curses.color_pair(PAIR_HIGHLIGHT if is_focus_row else PAIR_ADDR)
    x = _addstr(win, y, 0, f" {row * width:08x} ", addr_attr)
    x = _addstr(win, y, x, "│ ", curses.color_pair(PAIR_SEP))
    x = _draw_hex_part(
        win,
        y,
        x,
        data,
        width,
        row,
        cursor_col_hex,
        mirror_col_hex,
        state.hex_nibble,
        state.editing,
        dirty_offsets,
        hf,
        state,
    )
    x = _addstr(win, y, x, " │ ", curses.color_pair(PAIR_SEP))
    _draw_ascii_part(
        win,
        y,
        x,
        data,
        width,
        row,
        cursor_col_ascii,
        mirror_col_ascii,
        dirty_offsets,
        hf,
        state,
    )

    try:
        win.clrtoeol()
    except curses.error:
        pass


def draw_rows(win: Any, state: EditorState) -> None:
    h, _ = win.getmaxyx()
    hf = state.hf
    dirty_offsets = hf.dirty_offsets
    visible = h - 3

    focus_row = state.top_row if state.mode == EditorMode.READ else state.cur_row

    for dy in range(visible):
        row = state.top_row + dy
        data = hf.get_row(row)

        if data is None:
            try:
                win.move(1 + dy, 0)
                win.clrtoeol()
            except curses.error:
                pass
        else:
            draw_hex_row(win, 1 + dy, row, data, state, dirty_offsets, row == focus_row)


def _interpret_panel_rows(win: Any, state: EditorState) -> list[InterpretRow]:
    offset = _status_offset(state)
    return interpret_at(state.hf, offset)


def draw_interpret_panel(win: Any, state: EditorState) -> None:
    if not state.show_interpret:
        return

    h, w = win.getmaxyx()
    panel_w = INTERPRET_PANEL_WIDTH
    panel_x = w - panel_w - 1
    if panel_x < 12 or h < 7:
        return

    rows = _interpret_panel_rows(win, state)
    label_w = 10
    value_w = panel_w - label_w - 3

    border_attr = curses.color_pair(PAIR_INTERPRET_BORDER)
    label_attr = curses.color_pair(PAIR_INTERPRET_LABEL)
    value_attr = curses.color_pair(PAIR_INTERPRET_VALUE) | curses.A_BOLD

    title = "interpret"
    title_line = f"┌─ {title} " + "─" * max(0, panel_w - len(title) - 4) + "┐"
    _addstr(win, 1, panel_x, title_line, border_attr)

    max_rows = h - 5
    for dy, (label, value) in enumerate(rows[:max_rows]):
        y = 2 + dy
        label_str = label[:label_w].ljust(label_w)
        value_str = value[:value_w].ljust(value_w)
        _addstr(win, y, panel_x, "│", border_attr)
        _addstr(win, y, panel_x + 1, label_str, label_attr)
        _addstr(win, y, panel_x + 1 + label_w, " ", border_attr)
        _addstr(win, y, panel_x + 2 + label_w, value_str, value_attr)
        _addstr(win, y, panel_x + panel_w, "│", border_attr)

    bottom_y = 2 + min(len(rows), max_rows)
    if bottom_y < h - 2:
        bottom_line = "└" + "─" * panel_w + "┘"
        _addstr(win, bottom_y, panel_x, bottom_line, border_attr)


def draw_input_prompt(win: Any, prompt: str, max_len: int) -> str:
    h, w = win.getmaxyx()
    text = ""
    attr = curses.color_pair(PAIR_KEYBINDS)
    try:
        curses.curs_set(1)
        while True:
            label = prompt[: max(0, w - 12)]
            room = max(1, w - len(label) - 2)
            shown = text[-room:]
            _addstr(win, h - 1, 0, (label + shown).ljust(w - 1), attr)
            win.move(h - 1, min(w - 2, len(label) + len(shown)))
            win.refresh()
            key = win.get_wch()
            if key == "\x1b" or key == curses.KEY_RESIZE:
                return ""
            if key in ("\n", "\r", curses.KEY_ENTER):
                return text.strip()
            if key in ("\b", "\x7f", curses.KEY_BACKSPACE):
                text = text[:-1]
            elif isinstance(key, str) and key.isprintable() and len(text) < max_len:
                text += key
    except curses.error:
        return ""
    finally:
        try:
            curses.curs_set(0)
        except curses.error:
            pass


HELP_LINES = [
    "Navigation: arrows, PgUp/PgDn, Home/End; g: hex offset; w: row width",
    "Modes: h: HEX, a: ASCII, r/Esc: read; e: edit; Esc: stop editing",
    "Editing: Ctrl+Z: undo, Ctrl+R: redo; Del/Backspace: zero byte",
    "Save: Ctrl+S (atomic + .bak); S: save copy to a new file; q: quit",
    "Search: /: UTF-8 text; ?: HEX with ??/A?/?F masks; n/N: next/previous",
    "Range: v: start/clear; arrows: extend; y: copy; p: overwrite paste",
    "Range: f: fill with byte; x: export to new file (no overwrite)",
    "Compare: c: open/close second file; ]/[: next/previous differing byte",
    "Compare: underlined bytes differ; status shows other byte and size",
    "Structure: t: field navigator; arrows/Home/End: select; Enter: jump",
    "i: interpretation panel; F1: help; Esc: cancel input",
    "Copy uses an internal buffer (16 MiB max); fill/paste max 1 MiB",
    "Save As writes a copy: the original stays open and dirty",
    "Press any key to close help",
]


def draw_overlay(win: Any, state: EditorState) -> None:
    h, w = win.getmaxyx()
    if state.show_help:
        title = "Help — F1"
        lines = HELP_LINES
        selected = -1
        first = 0
    elif state.show_structure:
        fmt = state.hf.file_format
        fields = fmt.walk_fields() if fmt else []
        title = f"Structure: {state.hf.format_name} — Enter jump / Esc close"
        lines = []
        for depth, item in fields:
            data = state.hf.read_range(item.offset, min(item.length, 16))
            value = (
                str(int.from_bytes(data, item.endian))
                if 0 < item.length <= 8
                else data.hex(" ")
            )
            if len(data) < item.length:
                value += (
                    " …"
                    if item.offset + item.length <= state.hf.size
                    else " [truncated]"
                )
            lines.append(
                f"{'  ' * depth}{item.name}  @{item.offset:08x} +{item.length} [{item.ftype.name}] {value}"
            )
        if not lines:
            lines = ["No known structure. Load JSON definitions with --formats."]
        selected = min(state.structure_index, len(lines) - 1)
        first = max(0, selected - max(1, h - 6) // 2)
    else:
        return
    attr = curses.color_pair(PAIR_STATUS)
    _addstr(
        win, 1, 0, title.ljust(w - 1), curses.color_pair(PAIR_HEADER) | curses.A_BOLD
    )
    for y in range(2, max(2, h - 2)):
        index = first + y - 2
        text = lines[index] if index < len(lines) else ""
        row_attr = curses.color_pair(PAIR_CURSOR) if index == selected else attr
        _addstr(win, y, 0, text.ljust(w - 1), row_attr)


def draw_frame(stdscr: Any, state: EditorState) -> None:
    stdscr.erase()
    h, w = stdscr.getmaxyx()
    if h < 5 or w < 24:
        _addstr(stdscr, 0, 0, "Resize terminal (24x5 min)")
        stdscr.refresh()
        return
    draw_header(stdscr, state.hf, state)
    draw_rows(stdscr, state)
    draw_interpret_panel(stdscr, state)
    draw_overlay(stdscr, state)
    draw_status(stdscr, state)
    draw_keybinds(stdscr, state)
    stdscr.refresh()
