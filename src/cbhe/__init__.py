#!/usr/bin/env python3
import curses
import os
import sys
from typing import Any

from .colors import init_colors
from .handlers import (
    handle_ascii_edit,
    handle_hex_edit,
    handle_panel_normal,
)
from .hexfile import HexFile
from .state import EditorState
from .ui import draw_header, draw_input_prompt, draw_keybinds, draw_rows


def _handle_edit(state: EditorState, key: int, visible: int) -> None:
    if state.mode == state.mode.HEX:
        handle_hex_edit(state, key, visible)
    elif state.mode == state.mode.ASCII:
        handle_ascii_edit(state, key, visible)


def _handle_search_next(state: EditorState, visible: int) -> None:
    state.search_next(visible)


def _handle_search_prev(state: EditorState, visible: int) -> None:
    state.search_prev(visible)


def _handle_goto(state: EditorState, stdscr: Any, visible: int) -> None:
    input_text = draw_input_prompt(stdscr, " goto offset (hex): ", 16)
    if not input_text:
        return
    try:
        offset = int(input_text, 16)
        state.jump_to_offset(offset, visible)
    except ValueError:
        pass


def _handle_search(state: EditorState, stdscr: Any, visible: int) -> None:
    query = draw_input_prompt(stdscr, " / search ascii: ", 64)
    if not query:
        return
    query_bytes = query.encode("utf-8")
    offset = state.hf.find_ascii(query_bytes)
    if offset is not None:
        state.jump_to_offset(offset, visible)


def run(stdscr: Any, path: str) -> None:
    init_colors()
    curses.curs_set(0)
    stdscr.keypad(True)

    state = EditorState(hf=HexFile(path))

    while True:
        h, _ = stdscr.getmaxyx()
        visible = max(1, h - 2)

        state.clamp_top(visible)
        stdscr.erase()

        draw_header(stdscr, state.hf, state)
        draw_rows(stdscr, state)
        draw_keybinds(stdscr, state)
        stdscr.refresh()

        key = stdscr.getch()

        if key == curses.KEY_RESIZE:
            stdscr.clear()
            continue

        if key == 19:
            state.hf.save()
            continue

        if not state.editing and key == ord("q"):
            break

        if state.editing:
            _handle_edit(state, key, visible)
            continue

        if key in (ord("g"), ord("G")):
            _handle_goto(state, stdscr, visible)
            continue

        if key == ord("/"):
            _handle_search(state, stdscr, visible)
            continue

        if key == ord("n"):
            _handle_search_next(state, visible)
            continue

        if key == ord("N"):
            _handle_search_prev(state, visible)
            continue

        if not handle_panel_normal(state, key, visible):
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
