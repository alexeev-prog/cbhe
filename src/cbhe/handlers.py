import curses
import os
from typing import Any, Callable

from .constants import EditorMode
from .keys import (
    GOTO_KEYS,
    INTERPRET_KEYS,
    KEY_BACKSPACE,
    KEY_BACKSPACE_ALT1,
    KEY_BACKSPACE_ALT2,
    KEY_CTRL_R,
    KEY_CTRL_S,
    KEY_DC,
    KEY_DOWN,
    KEY_END,
    KEY_ESC,
    KEY_HOME,
    KEY_LEFT,
    KEY_NPAGE,
    KEY_PPAGE,
    KEY_RESIZE,
    KEY_RIGHT,
    KEY_UP,
    QUIT_KEYS,
    SEARCH_ASCII_KEY,
    SEARCH_HEX_KEY,
    SEARCH_NEXT_KEY,
    SEARCH_PREV_KEY,
)
from .state import EditorState
from .hexfile import HexFile
from .search import SearchPattern
from .ui import draw_input_prompt

_HEX_CHARS: dict[int, int] = {
    **{ord(str(d)): d for d in range(10)},
    **{ord(c): v for c, v in zip("abcdef", range(10, 16))},
    **{ord(c): v for c, v in zip("ABCDEF", range(10, 16))},
}


def _parse_hex_query(raw: str) -> tuple[bytes | None, str]:
    tokens = raw.split()
    result = bytearray()
    for token in tokens:
        token = token.removeprefix("0x").removeprefix("0X")
        if len(token) % 2 != 0:
            token = "0" + token
        try:
            result.extend(bytes.fromhex(token))
        except ValueError:
            return None, f"invalid hex token: {token!r}"
    if not result:
        return None, "empty query"
    return bytes(result), ""


def _make_read_nav_table(state: EditorState, visible: int) -> dict[int, object]:
    return {
        KEY_DOWN: lambda: state.scroll(1, visible),
        KEY_UP: lambda: state.scroll(-1, visible),
        KEY_NPAGE: lambda: state.scroll(visible, visible),
        KEY_PPAGE: lambda: state.scroll(-visible, visible),
        KEY_HOME: lambda: setattr(state, "top_row", 0),
        KEY_END: lambda: setattr(
            state, "top_row", max(0, state.hf.total_rows - visible)
        ),
        ord("w"): state.cycle_width,
        ord("W"): state.cycle_width,
        ord("r"): lambda: state.set_mode(EditorMode.READ),
        ord("h"): lambda: state.set_mode(EditorMode.HEX),
        ord("a"): lambda: state.set_mode(EditorMode.ASCII),
    }


def _make_panel_nav_table(state: EditorState, visible: int) -> dict[int, object]:
    return {
        KEY_DOWN: lambda: (state.move_cursor(1, 0), state.sync_scroll(visible)),  # type: ignore
        KEY_UP: lambda: (state.move_cursor(-1, 0), state.sync_scroll(visible)),  # type: ignore
        KEY_LEFT: lambda: (state.move_cursor(0, -1), state.sync_scroll(visible)),  # type: ignore
        KEY_RIGHT: lambda: (state.move_cursor(0, 1), state.sync_scroll(visible)),  # type: ignore
        KEY_HOME: lambda: setattr(state, "cur_col", 0),
        KEY_END: lambda: setattr(state, "cur_col", state._max_col(state.cur_row)),
        KEY_PPAGE: lambda: (
            state.scroll(-visible, visible),  # type: ignore
            state.sync_scroll(visible),  # type: ignore
        ),
        KEY_NPAGE: lambda: (
            state.scroll(visible, visible),  # type: ignore
            state.sync_scroll(visible),  # type: ignore
        ),
        ord("e"): state.enter_edit,
        ord("E"): state.enter_edit,
        ord("u"): state.undo,
        ord("U"): state.undo,
        ord("r"): lambda: state.set_mode(EditorMode.READ),
        ord("h"): lambda: state.set_mode(EditorMode.HEX),
        ord("a"): lambda: state.set_mode(EditorMode.ASCII),
        ord("w"): state.cycle_width,
        ord("W"): state.cycle_width,
        KEY_ESC: lambda: state.set_mode(EditorMode.READ),
    }


def _make_edit_special_table(state: EditorState, visible: int) -> dict[int, object]:
    return {
        KEY_ESC: state.exit_edit,
        KEY_BACKSPACE: lambda: (state.delete_backward(), state.sync_scroll(visible)),  # type: ignore
        KEY_BACKSPACE_ALT1: lambda: (
            state.delete_backward(),  # type: ignore
            state.sync_scroll(visible),  # type: ignore
        ),
        KEY_BACKSPACE_ALT2: lambda: (
            state.delete_backward(),  # type: ignore
            state.sync_scroll(visible),  # type: ignore
        ),
        KEY_DC: lambda: (state.delete_forward(), state.sync_scroll(visible)),  # type: ignore
        KEY_CTRL_R: state.redo,
        26: state.undo,
    }


def _handle_edit_common(
    state: EditorState,
    key: int,
    visible: int,
    char_predicate: Callable[[int], bool],
    char_writer: Callable[[int], None],
) -> None:
    special = _make_edit_special_table(state, visible)
    nav_keys: dict[int, tuple[int, int]] = {
        KEY_DOWN: (1, 0),
        KEY_UP: (-1, 0),
        KEY_LEFT: (0, -1),
        KEY_RIGHT: (0, 1),
    }

    if key in special:
        special[key]()  # type: ignore
    elif key in nav_keys:
        dr, dc = nav_keys[key]
        state.move_cursor(dr, dc)
        state.sync_scroll(visible)
    elif key == KEY_HOME:
        state.cur_col = 0
    elif key == KEY_END:
        state.cur_col = state._max_col(state.cur_row)
    elif char_predicate(key):
        char_writer(key)
        state.sync_scroll(visible)


def handle_read(state: EditorState, key: int, visible: int) -> bool:
    if key in QUIT_KEYS:
        return False

    action = _make_read_nav_table(state, visible).get(key)
    if action is not None:
        action()  # type: ignore
    return True


def handle_panel_normal(state: EditorState, key: int, visible: int) -> bool:
    if key in QUIT_KEYS:
        return False

    action = _make_panel_nav_table(state, visible).get(key)
    if action is not None:
        action()  # type: ignore
    return True


def handle_hex_edit(state: EditorState, key: int, visible: int) -> None:
    _handle_edit_common(
        state,
        key,
        visible,
        char_predicate=lambda k: k in _HEX_CHARS,
        char_writer=lambda k: state.write_hex_nibble(_HEX_CHARS[k]),
    )


def handle_ascii_edit(state: EditorState, key: int, visible: int) -> None:
    _handle_edit_common(
        state,
        key,
        visible,
        char_predicate=lambda k: 32 <= k <= 126,
        char_writer=lambda k: state.write_ascii(chr(k)),
    )


def handle_goto(state: EditorState, stdscr: Any, visible: int) -> None:
    input_text = draw_input_prompt(stdscr, " goto offset (hex): ", 16)
    if not input_text:
        return
    try:
        offset = int(input_text, 16)
        state.jump_to_offset(offset, visible)
    except ValueError:
        state.status.text = "invalid hex offset"
        state.status.is_error = True


def handle_search_ascii(state: EditorState, stdscr: Any, visible: int) -> None:
    query = draw_input_prompt(stdscr, " / ascii search: ", 64)
    if not query:
        return
    query_bytes = query.encode("utf-8")
    state.search.query = query_bytes
    state.search.match_len = len(query_bytes)
    state.search.is_hex = False
    state.search.pattern = SearchPattern.exact(query_bytes)
    offset = state.hf.find_ascii(query_bytes)
    if offset is not None:
        state.search.last_offset = offset
        state.jump_to_offset(offset, visible)
        state.status.text = f"found at {offset:08x}"
        state.status.is_error = False
    else:
        state.search.last_offset = -1
        state.status.text = f"not found: {query!r}"
        state.status.is_error = True


def handle_search_hex(state: EditorState, stdscr: Any, visible: int) -> None:
    raw = draw_input_prompt(stdscr, " ? hex/mask (48 8b ?? a?): ", 256)
    if not raw:
        return
    try:
        pattern = SearchPattern.from_hex(raw)
    except ValueError as error:
        state.status.text = str(error)
        state.status.is_error = True
        return
    query_bytes = pattern.values
    state.search.pattern = pattern
    state.search.query = query_bytes
    state.search.match_len = len(query_bytes)
    state.search.is_hex = True
    offset = state.hf.find_pattern(pattern)
    if offset is not None:
        state.search.last_offset = offset
        state.jump_to_offset(offset, visible)
        hex_repr = " ".join(f"{b:02x}" for b in query_bytes)
        state.status.text = f"hex [{hex_repr}] at {offset:08x}"
        state.status.is_error = False
    else:
        state.search.last_offset = -1
        hex_repr = " ".join(f"{b:02x}" for b in query_bytes)
        state.status.text = f"not found: {hex_repr}"
        state.status.is_error = True


def _save(state: EditorState, stdscr: Any) -> None:
    backup = os.path.realpath(state.hf.path) + ".bak"
    if state.hf.is_dirty and os.path.lexists(backup):
        answer = draw_input_prompt(
            stdscr, " backup exists; save without new backup? [yes/no]: ", 3
        )
        if answer.lower() != "yes":
            return
        state.hf.save(backup=False)
    else:
        state.hf.save()
    state.status.text = "saved"
    state.status.is_error = False


def _request_quit(state: EditorState, stdscr: Any) -> bool:
    if not state.hf.is_dirty:
        return False
    answer = draw_input_prompt(
        stdscr, " unsaved: [s]ave / [d]iscard / Enter cancel: ", 1
    ).lower()
    if answer == "d":
        return False
    if answer == "s":
        _save(state, stdscr)
        return state.hf.is_dirty
    return True


def _handle_structure(state: EditorState, key: int, visible: int) -> bool:
    if key in (KEY_ESC, ord("t")):
        state.show_structure = False
        return True
    fmt = state.hf.file_format
    fields = fmt.walk_fields() if fmt else []
    if not fields:
        return True
    if key in (KEY_UP, KEY_DOWN, KEY_HOME, KEY_END):
        if key == KEY_HOME:
            state.structure_index = 0
        elif key == KEY_END:
            state.structure_index = len(fields) - 1
        else:
            state.structure_index += 1 if key == KEY_DOWN else -1
        state.structure_index = max(0, min(state.structure_index, len(fields) - 1))
    elif key in (10, 13):
        item = fields[min(state.structure_index, len(fields) - 1)][1]
        if state.mode == EditorMode.READ:
            state.set_mode(EditorMode.HEX)
        state.jump_to_offset(item.offset, visible)
        state.show_structure = False
    return True


def _dispatch_key(state: EditorState, stdscr: Any, key: int, visible: int) -> bool:
    if key == KEY_RESIZE:
        return True

    if not state.editing:
        state.status.text = ""

    if key == KEY_CTRL_S:
        _save(state, stdscr)
        return True

    if not state.editing and key in QUIT_KEYS:
        return _request_quit(state, stdscr)

    if state.show_help:
        state.show_help = False
        return True

    if state.show_structure:
        return _handle_structure(state, key, visible)

    if state.editing:
        if state.mode == EditorMode.HEX:
            handle_hex_edit(state, key, visible)
        elif state.mode == EditorMode.ASCII:
            handle_ascii_edit(state, key, visible)
        return True

    if key == curses.KEY_F1:
        state.show_help = True
        return True
    if key == ord("t"):
        state.show_structure = True
        return True
    if key == ord("v"):
        state.toggle_selection()
        return True
    if key == ord("y"):
        state.copy_selection()
        return True
    if key == ord("p"):
        state.replace_range(state.clipboard)
        return True
    if key == ord("f"):
        raw = draw_input_prompt(stdscr, " fill selection with byte (hex): ", 2)
        if raw:
            value = int(raw, 16)
            state.replace_range(bytes([value]), fill=True)
        return True
    if key == ord("x"):
        path = draw_input_prompt(stdscr, " export selection to new file: ", 1024)
        if path:
            state.export_selection(path)
        return True
    if key == ord("S"):
        path = draw_input_prompt(stdscr, " save copy as (new file): ", 1024)
        if path:
            state.hf.save_as(path)
            state.status.text = "copy saved; original remains open"
            state.status.is_error = False
        return True
    if key == ord("c"):
        path = draw_input_prompt(
            stdscr, " compare file (empty: close comparison): ", 1024
        )
        other = HexFile(path, read_only=True) if path else None
        if state.comparison:
            state.comparison.close()
        state.comparison = other
        state.status.text = (
            "comparison opened; ]/[ next/previous difference"
            if other
            else "comparison closed"
        )
        state.status.is_error = False
        return True
    if key in (ord("["), ord("]")):
        state.difference(visible, backward=key == ord("["))
        return True
    if key == KEY_CTRL_R:
        state.redo()
        state.sync_scroll(visible)
        return True
    if key == 26:
        state.undo()
        state.sync_scroll(visible)
        return True

    if key in INTERPRET_KEYS:
        state.toggle_interpret()
        return True

    if key in GOTO_KEYS:
        handle_goto(state, stdscr, visible)
        return True

    if key == SEARCH_ASCII_KEY:
        handle_search_ascii(state, stdscr, visible)
        return True

    if key == SEARCH_HEX_KEY:
        handle_search_hex(state, stdscr, visible)
        return True

    if key == SEARCH_NEXT_KEY:
        state.search_next(visible)
        return True

    if key == SEARCH_PREV_KEY:
        state.search_prev(visible)
        return True

    if state.mode == EditorMode.READ:
        return handle_read(state, key, visible)

    return handle_panel_normal(state, key, visible)


def dispatch_key(state: EditorState, stdscr: Any, key: int, visible: int) -> bool:
    try:
        return _dispatch_key(state, stdscr, key, visible)
    except (OSError, ValueError) as error:
        state.status.text = str(error)
        state.status.is_error = True
        return True
