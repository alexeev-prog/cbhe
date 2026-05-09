import curses

from .constants import EditorMode
from .state import EditorState

_KEY_ESC = 27
_KEY_CTRL_R = 18
_KEY_CTRL_S = 19

_HEX_CHARS: dict[int, int] = {
    **{ord(str(d)): d for d in range(10)},
    **{ord(c): v for c, v in zip("abcdef", range(10, 16))},
    **{ord(c): v for c, v in zip("ABCDEF", range(10, 16))},
}


def _make_read_nav_table(state: EditorState, visible: int) -> dict[int, object]:
    return {
        curses.KEY_DOWN: lambda: state.scroll(1, visible),
        curses.KEY_UP: lambda: state.scroll(-1, visible),
        curses.KEY_NPAGE: lambda: state.scroll(visible, visible),
        curses.KEY_PPAGE: lambda: state.scroll(-visible, visible),
        curses.KEY_HOME: lambda: setattr(state, "top_row", 0),
        curses.KEY_END: lambda: setattr(
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
        curses.KEY_DOWN: lambda: (state.move_cursor(1, 0), state.sync_scroll(visible)),  # type: ignore
        curses.KEY_UP: lambda: (state.move_cursor(-1, 0), state.sync_scroll(visible)),  # type: ignore
        curses.KEY_LEFT: lambda: (state.move_cursor(0, -1), state.sync_scroll(visible)),  # type: ignore
        curses.KEY_RIGHT: lambda: (state.move_cursor(0, 1), state.sync_scroll(visible)),  # type: ignore
        curses.KEY_HOME: lambda: setattr(state, "cur_col", 0),
        curses.KEY_END: lambda: setattr(
            state, "cur_col", state._max_col(state.cur_row)
        ),
        curses.KEY_PPAGE: lambda: (
            state.scroll(-visible, visible),  # type: ignore
            state.sync_scroll(visible),  # type: ignore
        ),
        curses.KEY_NPAGE: lambda: (
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
        _KEY_ESC: lambda: state.set_mode(EditorMode.READ),
    }


def _make_edit_special_table(state: EditorState, visible: int) -> dict[int, object]:
    return {
        _KEY_ESC: state.exit_edit,
        curses.KEY_BACKSPACE: lambda: (
            state.delete_backward(),  # type: ignore
            state.sync_scroll(visible),  # type: ignore
        ),
        127: lambda: (state.delete_backward(), state.sync_scroll(visible)),  # type: ignore
        8: lambda: (state.delete_backward(), state.sync_scroll(visible)),  # type: ignore
        curses.KEY_DC: lambda: (state.delete_forward(), state.sync_scroll(visible)),  # type: ignore
        ord("u"): state.undo,
        _KEY_CTRL_R: state.redo,
    }


def handle_read(state: EditorState, key: int, visible: int) -> bool:
    if key in (ord("q"), ord("Q")):
        return False

    table = _make_read_nav_table(state, visible)
    action = table.get(key)
    if action is not None:
        action()  # type: ignore

    return True


def handle_panel_normal(state: EditorState, key: int, visible: int) -> bool:
    if key in (ord("q"), ord("Q")):
        return False

    table = _make_panel_nav_table(state, visible)
    action = table.get(key)
    if action is not None:
        action()  # type: ignore
        return True

    return True


def handle_hex_edit(state: EditorState, key: int, visible: int) -> None:
    special = _make_edit_special_table(state, visible)

    nav_keys: dict[int, tuple[int, int]] = {
        curses.KEY_DOWN: (1, 0),
        curses.KEY_UP: (-1, 0),
        curses.KEY_LEFT: (0, -1),
        curses.KEY_RIGHT: (0, 1),
    }

    if key in special:
        special[key]()  # type: ignore
    elif key in nav_keys:
        dr, dc = nav_keys[key]
        state.move_cursor(dr, dc)
        state.sync_scroll(visible)
    elif key == curses.KEY_HOME:
        state.cur_col = 0
    elif key == curses.KEY_END:
        state.cur_col = state._max_col(state.cur_row)
    elif key in _HEX_CHARS:
        state.write_hex_nibble(_HEX_CHARS[key])
        state.sync_scroll(visible)


def handle_ascii_edit(state: EditorState, key: int, visible: int) -> None:
    special = _make_edit_special_table(state, visible)

    nav_keys: dict[int, tuple[int, int]] = {
        curses.KEY_DOWN: (1, 0),
        curses.KEY_UP: (-1, 0),
        curses.KEY_LEFT: (0, -1),
        curses.KEY_RIGHT: (0, 1),
    }

    if key in special:
        special[key]()  # type: ignore
    elif key in nav_keys:
        dr, dc = nav_keys[key]
        state.move_cursor(dr, dc)
        state.sync_scroll(visible)
    elif key == curses.KEY_HOME:
        state.cur_col = 0
    elif key == curses.KEY_END:
        state.cur_col = state._max_col(state.cur_row)
    elif 32 <= key <= 126:
        state.write_ascii(chr(key))
        state.sync_scroll(visible)
