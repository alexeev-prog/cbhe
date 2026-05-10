#!/usr/bin/env python3
import curses
import os
import sys
from typing import Any

from .colors import init_colors
from .constants import EditorMode
from .handlers import (
    handle_ascii_edit,
    handle_hex_edit,
    handle_panel_normal,
    handle_read,
)
from .hexfile import HexFile
from .state import EditorState
from .ui import (
    draw_header,
    draw_input_prompt,
    draw_interpret_panel,
    draw_keybinds,
    draw_rows,
    draw_status,
)

_KEY_CTRL_S = 19


def _handle_edit(state: EditorState, key: int, visible: int) -> None:
    if state.mode == EditorMode.HEX:
        handle_hex_edit(state, key, visible)
    elif state.mode == EditorMode.ASCII:
        handle_ascii_edit(state, key, visible)


def _handle_goto(state: EditorState, stdscr: Any, visible: int) -> None:
    input_text = draw_input_prompt(stdscr, " goto offset (hex): ", 16)
    if not input_text:
        return
    try:
        offset = int(input_text, 16)
        state.jump_to_offset(offset, visible)
    except ValueError:
        state.status.text = "invalid hex offset"
        state.status.is_error = True


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


def _handle_search_ascii(state: EditorState, stdscr: Any, visible: int) -> None:
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


def _handle_search_hex(state: EditorState, stdscr: Any, visible: int) -> None:
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


def _draw_frame(stdscr: Any, state: EditorState) -> None:
    stdscr.erase()
    draw_header(stdscr, state.hf, state)
    draw_rows(stdscr, state)
    draw_interpret_panel(stdscr, state)
    draw_status(stdscr, state)
    draw_keybinds(stdscr, state)
    stdscr.refresh()


def run(stdscr: Any, path: str) -> None:
    init_colors()
    curses.curs_set(0)
    stdscr.keypad(True)

    state = EditorState(hf=HexFile(path))

    while True:
        h, _ = stdscr.getmaxyx()
        visible = max(1, h - 3)

        state.clamp_top(visible)
        _draw_frame(stdscr, state)

        key = stdscr.getch()

        if key == curses.KEY_RESIZE:
            stdscr.clear()
            continue

        if key == _KEY_CTRL_S:
            state.hf.save()
            state.status.text = "saved"
            state.status.is_error = False
            continue

        if not state.editing and key == ord("q"):
            break

        if state.editing:
            _handle_edit(state, key, visible)
            continue

        if key in (ord("i"), ord("I")):
            state.toggle_interpret()
            continue

        if key in (ord("g"), ord("G")):
            _handle_goto(state, stdscr, visible)
            continue

        if key == ord("/"):
            _handle_search_ascii(state, stdscr, visible)
            continue

        if key == ord("?"):
            _handle_search_hex(state, stdscr, visible)
            continue

        if key == ord("n"):
            state.search_next(visible)
            continue

        if key == ord("N"):
            state.search_prev(visible)
            continue

        if state.mode == EditorMode.READ:
            if not handle_read(state, key, visible):
                break
        elif not handle_panel_normal(state, key, visible):
            break


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python hexview.py <filename>")
        sys.exit(1)

    path = sys.argv[1]
    if not os.path.isfile(path):
        print(f"File not found: {path}")
        sys.exit(1)

    curses.wrapper(run, path)


if __name__ == "__main__":
    main()
