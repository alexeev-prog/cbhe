import curses
from typing import Any, Optional

from .colors import ascii_color, field_color, hex_color
from .constants import (
    KEYBINDS_EDIT,
    KEYBINDS_NORMAL,
    KEYBINDS_READ,
    PAIR_ADDR,
    PAIR_CURSOR,
    PAIR_DIRTY,
    PAIR_HEADER,
    PAIR_HEADER_EDIT,
    PAIR_KEYBINDS,
    PAIR_KEYBINDS_EDIT,
    PAIR_SEP,
    EditorMode,
)
from .hexfile import HexFile
from .state import EditorState


def _addstr(win: Any, y: int, x: int, text: str, attr: int = 0) -> int:
    h, w = win.getmaxyx()
    if y >= h or x >= w:
        return x

    text = text[: w - x - 1]
    if text:
        try:
            win.addstr(y, x, text, attr)
        except curses.error:
            pass

    return x + len(text)


def draw_header(win: Any, hf: HexFile, state: EditorState) -> None:
    _, w = win.getmaxyx()
    pct = 100 * state.top_row // max(1, hf.total_rows - 1)
    dirty_mark = " [*] " if hf.is_dirty else " "

    mode_label = {
        EditorMode.READ: "READ",
        EditorMode.HEX: "HEX-NORM" if not state.editing else "HEX-EDIT",
        EditorMode.ASCII: "ASCII-NORM" if not state.editing else "ASCII-EDIT",
    }[state.mode]

    title = (
        f"  cbhe [{mode_label}] │  {hf.path}{dirty_mark}│  "
        f"{hf.size:,} B  │  w={hf.width}  │  fmt={hf.format_name}  │  {pct}%"
    )

    pair = PAIR_HEADER_EDIT if state.editing else PAIR_HEADER
    _addstr(win, 0, 0, title.ljust(w - 1), curses.color_pair(pair))


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


def _draw_hex_part(
    win: Any,
    y: int,
    x: int,
    data: bytearray,
    width: int,
    row: int,
    cursor_col: Optional[int],
    hex_nibble: int,
    editing: bool,
    dirty_offsets: set[int],
    hf: HexFile,
) -> int:
    for gi in range(0, width, 4):
        if gi > 0:
            x = _addstr(win, y, x, "  ", curses.color_pair(PAIR_SEP))

        for bi in range(4):
            idx = gi + bi
            if bi > 0:
                x = _addstr(win, y, x, " ", curses.color_pair(PAIR_SEP))

            if idx < len(data):
                b = data[idx]
                offset = row * width + idx

                if idx == cursor_col:
                    attr = curses.color_pair(PAIR_CURSOR)
                elif offset in dirty_offsets:
                    attr = curses.color_pair(PAIR_DIRTY)
                else:
                    field_def = hf.get_field_at(offset)
                    if field_def is not None:
                        attr = field_color(field_def.ftype.name)
                    else:
                        attr = hex_color(b)

                hi = f"{b:02x}"
                if idx == cursor_col and editing:
                    hi_char = hi[hex_nibble]
                    lo_char = hi[1 - hex_nibble]
                    x = _addstr(
                        win, y, x, hi_char, attr | curses.A_UNDERLINE | curses.A_BOLD
                    )
                    x = _addstr(win, y, x, lo_char, attr)
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
    dirty_offsets: set[int],
    hf: HexFile,
) -> None:
    _, w = win.getmaxyx()

    for i in range(min(width, len(data))):
        if x >= w - 1:
            break

        b = data[i]
        ch = chr(b) if 32 <= b <= 126 else "·"
        offset = row * width + i

        if i == cursor_col:
            attr = curses.color_pair(PAIR_CURSOR)
        elif offset in dirty_offsets:
            attr = curses.color_pair(PAIR_DIRTY)
        else:
            field_def = hf.get_field_at(offset)
            if field_def is not None:
                attr = field_color(field_def.ftype.name)
            else:
                attr = ascii_color(b)

        x = _addstr(win, y, x, ch, attr)


def draw_hex_row(
    win: Any,
    y: int,
    row: int,
    data: bytearray,
    state: EditorState,
    dirty_offsets: set[int],
) -> None:
    h, w = win.getmaxyx()
    if y >= h - 1:
        return

    hf = state.hf
    width = hf.width
    cursor = state.cursor

    cursor_col_hex: Optional[int] = None
    cursor_col_ascii: Optional[int] = None

    if cursor and cursor[0] == row:
        if state.mode == EditorMode.HEX:
            cursor_col_hex = cursor[1]
        elif state.mode == EditorMode.ASCII:
            cursor_col_ascii = cursor[1]

    x = _addstr(win, y, 0, f"{row * width:08x}  ", curses.color_pair(PAIR_ADDR))
    x = _draw_hex_part(
        win,
        y,
        x,
        data,
        width,
        row,
        cursor_col_hex,
        state.hex_nibble,
        state.editing,
        dirty_offsets,
        hf,
    )
    x = _addstr(win, y, x, "  │  ", curses.color_pair(PAIR_SEP))
    _draw_ascii_part(win, y, x, data, width, row, cursor_col_ascii, dirty_offsets, hf)

    try:
        win.clrtoeol()
    except curses.error:
        pass


def draw_rows(
    win: Any,
    state: EditorState,
) -> None:
    h, _ = win.getmaxyx()
    hf = state.hf
    dirty_offsets = hf.dirty_offsets

    for dy in range(h - 2):
        row = state.top_row + dy
        data = hf.get_row(row)

        if data is None:
            try:
                win.move(1 + dy, 0)
                win.clrtoeol()
            except curses.error:
                pass
        else:
            draw_hex_row(win, 1 + dy, row, data, state, dirty_offsets)


def draw_input_prompt(win: Any, prompt: str, max_len: int) -> str:
    h, _ = win.getmaxyx()
    pair = PAIR_KEYBINDS
    _addstr(win, h - 1, 0, prompt.ljust(40), curses.color_pair(pair))

    curses.echo()
    curses.curs_set(1)
    try:
        raw = (
            win.getstr(h - 1, len(prompt), max_len)
            .decode("utf-8", errors="ignore")
            .strip()
        )
    except Exception:
        raw = ""
    finally:
        curses.noecho()
        curses.curs_set(0)

    return raw
