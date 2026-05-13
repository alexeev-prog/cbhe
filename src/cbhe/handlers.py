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
        ord("u"): state.undo,
        KEY_CTRL_R: state.redo,
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
    raw = draw_input_prompt(stdscr, " ? hex search (e.g. ff d8 ff): ", 80)
    if not raw:
        return
    query_bytes, err = _parse_hex_query(raw)
    if query_bytes is None:
        state.status.text = err
        state.status.is_error = True
        return
    state.search.query = query_bytes
    state.search.match_len = len(query_bytes)
    state.search.is_hex = True
    offset = state.hf.find_bytes(query_bytes)
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


def dispatch_key(state: EditorState, stdscr: Any, key: int, visible: int) -> bool:
    if key == KEY_RESIZE:
        return True

    if key == KEY_CTRL_S:
        state.hf.save()
        state.status.text = "saved"
        state.status.is_error = False
        return True

    if not state.editing and key in QUIT_KEYS:
        return False

    if state.editing:
        if state.mode == EditorMode.HEX:
            handle_hex_edit(state, key, visible)
        elif state.mode == EditorMode.ASCII:
            handle_ascii_edit(state, key, visible)
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
