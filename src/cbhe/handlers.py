import curses

from .state import EditorState


def handle_normal(state: EditorState, key: int, visible: int) -> bool:
    key_actions = {
        ord("q"): lambda: False,
        ord("Q"): lambda: False,
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
        ord("e"): state.enter_edit,
        ord("E"): state.enter_edit,
    }

    action = key_actions.get(key)
    if action is not None:
        result = action()
        return result if result is False else True

    return True


def handle_edit(state: EditorState, key: int, visible: int) -> None:
    special_keys = {
        27: state.exit_edit,
        curses.KEY_BACKSPACE: lambda: _delete_backward(state, visible),
        127: lambda: _delete_backward(state, visible),
        8: lambda: _delete_backward(state, visible),
        curses.KEY_DC: lambda: _delete_forward(state, visible),
    }

    nav_keys = {
        curses.KEY_DOWN: (1, 0),
        curses.KEY_UP: (-1, 0),
        curses.KEY_LEFT: (0, -1),
        curses.KEY_RIGHT: (0, 1),
    }

    if key in special_keys:
        special_keys[key]()
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


def _delete_backward(state: EditorState, visible: int) -> None:
    state.delete_backward()
    state.sync_scroll(visible)


def _delete_forward(state: EditorState, visible: int) -> None:
    state.delete_forward()
    state.sync_scroll(visible)
