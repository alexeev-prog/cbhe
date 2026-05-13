#!/usr/bin/env python3
import argparse
import glob
import os
import sys
from typing import Any

from cbhe.formats import load_custom_formats, register_builtins

from .colors import init_colors
from .constants import EditorMode
from .handlers import dispatch_key
from .hexfile import HexFile
from .keys import KEY_RESIZE
from .state import EditorState
from .terminal import clear, run_with_wrapper, screen_size, setup
from .ui import draw_frame


def _visible_rows(stdscr: Any) -> int:
    h, _ = screen_size(stdscr)
    return max(1, h - 3)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Curses-based hex editor with interpretation and highlighting",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s file.bin
  %(prog)s --formats custom.json file.bin
  %(prog)s -f fmt1.json -f fmt2.json file.bin
  %(prog)s -w 32 file.bin
  %(prog)s -m hex file.bin
        """,
    )

    parser.add_argument("file", help="File to open and edit")
    parser.add_argument(
        "-f",
        "--formats",
        action="append",
        dest="format_files",
        help="JSON file with custom format definitions",
    )
    parser.add_argument(
        "-w",
        "--width",
        type=int,
        choices=[8, 16, 32],
        default=16,
        help="Initial bytes per row",
    )
    parser.add_argument(
        "-m",
        "--mode",
        choices=["read", "hex", "ascii"],
        default="read",
        help="Initial mode",
    )
    parser.add_argument(
        "--no-auto-detect",
        action="store_true",
        help="Disable automatic format detection",
    )
    parser.add_argument(
        "--format-dir",
        help="Directory containing JSON format files",
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
        draw_frame(stdscr, state)

        key = stdscr.getch()

        if not dispatch_key(state, stdscr, key, visible):
            break

        if key == KEY_RESIZE:
            clear(stdscr)


def main() -> None:
    args = parse_arguments()

    if not os.path.isfile(args.file):
        print(f"File not found: {args.file}")
        sys.exit(1)

    load_all_formats(args)
    run_with_wrapper(run, args)


if __name__ == "__main__":
    main()
