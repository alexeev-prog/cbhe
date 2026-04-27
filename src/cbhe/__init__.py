#!/usr/bin/env python3
import curses
import os
import sys
from typing import Any

from .colors import init_colors
from .handlers import handle_edit, handle_normal
from .hexfile import HexFile
from .state import EditorState
from .ui import draw_header, draw_input_prompt, draw_keybinds, draw_rows


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

        draw_header(stdscr, state.hf, state.top_row, state.editing)
        draw_rows(stdscr, state.hf, state.top_row, state.cursor)
        draw_keybinds(stdscr, state.editing)
        stdscr.refresh()

        key = stdscr.getch()

        if key == curses.KEY_RESIZE:
            stdscr.clear()
            continue

        if key == 19:
            state.hf.save()
            continue

        if state.editing:
            handle_edit(state, key, visible)
            continue

        if key in (ord("g"), ord("G")):
            input_text = draw_input_prompt(stdscr, " goto offset (hex): ", 16)
            if input_text:
                try:
                    offset: int | None = int(input_text, 16)
                    state.jump_to_offset(offset if offset is not None else 0, visible)
                except ValueError:
                    pass

        elif key == ord("/"):
            query = draw_input_prompt(stdscr, " / search ascii: ", 64)
            if query:
                query_bytes = query.encode("utf-8")
                offset = state.hf.find_ascii(query_bytes)
                if offset is not None:
                    state.jump_to_offset(offset, visible)

        elif not handle_normal(state, key, visible):
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
