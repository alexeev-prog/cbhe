import curses
from typing import Any, Callable


def setup(stdscr: Any) -> None:
    curses.curs_set(0)
    stdscr.keypad(True)


def run_with_wrapper(fn: Callable[..., None], *args: Any) -> None:
    curses.wrapper(fn, *args)


def read_key(stdscr: Any) -> int:
    return stdscr.getch()


def clear(stdscr: Any) -> None:
    stdscr.clear()


def screen_size(stdscr: Any) -> tuple[int, int]:
    return stdscr.getmaxyx()
