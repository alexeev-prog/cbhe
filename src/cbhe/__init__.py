#!/usr/bin/env python3
import argparse
import glob
import os
import sys
from typing import Any

from cbhe.formats import load_custom_formats, register_builtins

from .colors import init_colors
from .constants import EditorMode
from .handlers import (
    handle_ascii_edit,
    handle_hex_edit,
    handle_panel_normal,
    handle_read,
)
from .hexfile import HexFile
from .keys import KEY_CTRL_S, KEY_RESIZE
from .state import EditorState
from .terminal import clear, read_key, run_with_wrapper, screen_size, setup
from .ui import (
    draw_header,
    draw_input_prompt,
    draw_interpret_panel,
    draw_keybinds,
    draw_rows,
    draw_status,
)


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


def _visible_rows(stdscr: Any) -> int:
    h, _ = screen_size(stdscr)
    return max(1, h - 3)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Curses-based hex editor with interpretation and highlighting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s file.bin                    # Open file with auto-detection
  %(prog)s --formats custom.json file.bin  # Load custom formats
  %(prog)s -f fmt1.json -f fmt2.json file.bin  # Multiple format files
  %(prog)s -w 32 file.bin              # Set initial width to 32
  %(prog)s -m hex file.bin             # Start in hex mode
        """,
    )

    parser.add_argument("file", help="File to open and edit")
    parser.add_argument(
        "-f",
        "--formats",
        action="append",
        dest="format_files",
        help="JSON file with custom format definitions (can be used multiple times)",
    )
    parser.add_argument(
        "-w",
        "--width",
        type=int,
        choices=[8, 16, 32],
        default=16,
        help="Initial bytes per row (default: 16)",
    )
    parser.add_argument(
        "-m",
        "--mode",
        choices=["read", "hex", "ascii"],
        default="read",
        help="Initial mode (default: read)",
    )
    parser.add_argument(
        "--no-auto-detect",
        action="store_true",
        help="Disable automatic format detection",
    )
    parser.add_argument(
        "--format-dir", help="Directory containing JSON format files (loads all *.json)"
    )

    return parser.parse_args()


def load_all_formats(args: argparse.Namespace) -> None:
    format_files: list[str] = []

    if args.format_files:
        format_files.extend(args.format_files)

    if args.format_dir and os.path.isdir(args.format_dir):
        json_files = glob.glob(os.path.join(args.format_dir, "*.json"))
        format_files.extend(json_files)
        print(f"Found {len(json_files)} format files in {args.format_dir}")

    register_builtins()

    if format_files:
        print(f"Loading formats from: {format_files}")
        load_custom_formats(format_files)


_MODE_MAP: dict[str, EditorMode] = {
    "read": EditorMode.READ,
    "hex": EditorMode.HEX,
    "ascii": EditorMode.ASCII,
}

_SEARCH_KEYS = {ord("/"), ord("?")}
_GOTO_KEYS = {ord("g"), ord("G")}
_INTERPRET_KEYS = {ord("i"), ord("I")}


def run(stdscr: Any, args: argparse.Namespace) -> None:
    init_colors()
    setup(stdscr)

    hf = HexFile(args.file, width=args.width)

    if args.no_auto_detect:
        hf.file_format = None

    state = EditorState(hf=hf)
    state.set_mode(_MODE_MAP[args.mode])

    while True:
        visible = _visible_rows(stdscr)
        state.clamp_top(visible)
        _draw_frame(stdscr, state)

        key = read_key(stdscr)

        if key == KEY_RESIZE:
            clear(stdscr)
            continue

        if key == KEY_CTRL_S:
            state.hf.save()
            state.status.text = "saved"
            state.status.is_error = False
            continue

        if not state.editing and key == ord("q"):
            break

        if state.editing:
            _handle_edit(state, key, visible)
            continue

        if key in _INTERPRET_KEYS:
            state.toggle_interpret()
            continue

        if key in _GOTO_KEYS:
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
    args = parse_arguments()

    if not os.path.isfile(args.file):
        print(f"File not found: {args.file}")
        sys.exit(1)

    load_all_formats(args)
    run_with_wrapper(run, args)


if __name__ == "__main__":
    main()
