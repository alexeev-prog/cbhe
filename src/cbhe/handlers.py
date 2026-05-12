from typing import Callable

from .constants import EditorMode
from .keys import (
    KEY_BACKSPACE,
    KEY_BACKSPACE_ALT1,
    KEY_BACKSPACE_ALT2,
    KEY_CTRL_R,
    KEY_DC,
    KEY_DOWN,
    KEY_END,
    KEY_ESC,
    KEY_HOME,
    KEY_LEFT,
    KEY_NPAGE,
    KEY_PPAGE,
    KEY_RIGHT,
    KEY_UP,
)
from .state import EditorState

_HEX_CHARS: dict[int, int] = {
    **{ord(str(d)): d for d in range(10)},
    **{ord(c): v for c, v in zip("abcdef", range(10, 16))},
    **{ord(c): v for c, v in zip("ABCDEF", range(10, 16))},
}


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
        KEY_DOWN: lambda: (state.move_cursor(1, 0), state.sync_scroll(visible)),  # type: ignore[func-returns-value]
        KEY_UP: lambda: (state.move_cursor(-1, 0), state.sync_scroll(visible)),  # type: ignore[func-returns-value]
        KEY_LEFT: lambda: (state.move_cursor(0, -1), state.sync_scroll(visible)),  # type: ignore[func-returns-value]
        KEY_RIGHT: lambda: (state.move_cursor(0, 1), state.sync_scroll(visible)),  # type: ignore[func-returns-value]
        KEY_HOME: lambda: setattr(state, "cur_col", 0),
        KEY_END: lambda: setattr(state, "cur_col", state._max_col(state.cur_row)),
        KEY_PPAGE: lambda: (
            state.scroll(-visible, visible),  # type: ignore[func-returns-value]
            state.sync_scroll(visible),  # type: ignore[func-returns-value]
        ),
        KEY_NPAGE: lambda: (state.scroll(visible, visible), state.sync_scroll(visible)),  # type: ignore[func-returns-value]
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
        KEY_BACKSPACE: lambda: (state.delete_backward(), state.sync_scroll(visible)),  # type: ignore[func-returns-value]
        KEY_BACKSPACE_ALT1: lambda: (
            state.delete_backward(),  # type: ignore[func-returns-value]
            state.sync_scroll(visible),  # type: ignore[func-returns-value]
        ),
        KEY_BACKSPACE_ALT2: lambda: (
            state.delete_backward(),  # type: ignore[func-returns-value]
            state.sync_scroll(visible),  # type: ignore[func-returns-value]
        ),
        KEY_DC: lambda: (state.delete_forward(), state.sync_scroll(visible)),  # type: ignore[func-returns-value]
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
        special[key]()  # type: ignore[operator]
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
    if key in (ord("q"), ord("Q")):
        return False

    action = _make_read_nav_table(state, visible).get(key)
    if action is not None:
        action()  # type: ignore[operator]
    return True


def handle_panel_normal(state: EditorState, key: int, visible: int) -> bool:
    if key in (ord("q"), ord("Q")):
        return False

    action = _make_panel_nav_table(state, visible).get(key)
    if action is not None:
        action()  # type: ignore[operator]
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
