import curses

from .constants import (
    ASCII_COLOR_COUNT,
    ASCII_PRINTABLE_END,
    ASCII_PRINTABLE_START,
    BYTE_MAX,
    BYTE_MIN,
    COLOR_SLOTS,
    DEFAULT_BYTE_RGB,
    MAX_BYTE_RGB,
    PAIR_ADDR,
    PAIR_ASCII_BASE,
    PAIR_CURSOR,
    PAIR_DIRTY,
    PAIR_HEADER,
    PAIR_HEADER_EDIT,
    PAIR_HEX_BASE,
    PAIR_HIGHLIGHT,
    PAIR_KEYBINDS,
    PAIR_KEYBINDS_EDIT,
    PAIR_SEP,
)


def _hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    h = h % 360.0
    c = v * s
    x = c * (1.0 - abs((h / 60.0) % 2.0 - 1.0))
    m = v - c

    if h < 60:
        r, g, b = c, x, 0.0
    elif h < 120:
        r, g, b = x, c, 0.0
    elif h < 180:
        r, g, b = 0.0, c, x
    elif h < 240:
        r, g, b = 0.0, x, c
    elif h < 300:
        r, g, b = x, 0.0, c
    else:
        r, g, b = c, 0.0, x

    return (
        int((r + m) * 255),
        int((g + m) * 255),
        int((b + m) * 255),
    )


def _byte_to_rgb(bval: int) -> tuple[int, int, int]:
    if bval == BYTE_MIN:
        return DEFAULT_BYTE_RGB
    if bval == BYTE_MAX:
        return MAX_BYTE_RGB

    hue = (bval / 255.0) * 360.0
    return _hsv_to_rgb(hue, 0.8, 0.9)


def _init_color_slot(slot: int, r: int, g: int, b: int) -> bool:
    if slot >= curses.COLORS:
        return False

    try:
        curses.init_color(slot, r * 1000 // 255, g * 1000 // 255, b * 1000 // 255)
        return True
    except (curses.error, ValueError):
        return False


def init_colors() -> None:
    curses.start_color()
    curses.use_default_colors()

    _init_base_pairs()
    _init_hex_pairs()
    _init_ascii_pairs()


def _init_base_pairs() -> None:
    pairs = [
        (PAIR_ADDR, curses.COLOR_CYAN, -1),
        (PAIR_SEP, curses.COLOR_WHITE, -1),
        (PAIR_HEADER, curses.COLOR_BLACK, curses.COLOR_CYAN),
        (PAIR_HEADER_EDIT, curses.COLOR_BLACK, curses.COLOR_GREEN),
        (PAIR_KEYBINDS, curses.COLOR_BLACK, curses.COLOR_WHITE),
        (PAIR_KEYBINDS_EDIT, curses.COLOR_BLACK, curses.COLOR_GREEN),
        (PAIR_HIGHLIGHT, curses.COLOR_BLACK, curses.COLOR_YELLOW),
        (PAIR_CURSOR, curses.COLOR_BLACK, curses.COLOR_GREEN),
        (PAIR_DIRTY, curses.COLOR_BLACK, curses.COLOR_RED),
    ]

    for pair_id, fg, bg in pairs:
        curses.init_pair(pair_id, fg, bg)


def _init_hex_pairs() -> None:
    rich = curses.can_change_color() and curses.COLORS > 16

    for bval in range(COLOR_SLOTS):
        slot = 16 + bval
        pair_id = PAIR_HEX_BASE + bval

        if rich and _init_color_slot(slot, *_byte_to_rgb(bval)):
            curses.init_pair(pair_id, slot, -1)
        else:
            curses.init_pair(pair_id, curses.COLOR_WHITE, -1)


def _init_ascii_pairs() -> None:
    rich = curses.can_change_color() and curses.COLORS > 16

    for i in range(ASCII_COLOR_COUNT):
        slot = 272 + i
        pair_id = PAIR_ASCII_BASE + i

        if rich:
            gray = 150 + int(i / 94 * 105)
            if _init_color_slot(slot, gray, gray, gray):
                curses.init_pair(pair_id, slot, -1)
                continue

        curses.init_pair(pair_id, curses.COLOR_WHITE, -1)


def hex_color(bval: int) -> int:
    return curses.color_pair(PAIR_HEX_BASE + bval)


def ascii_color(bval: int) -> int:
    if ASCII_PRINTABLE_START <= bval <= ASCII_PRINTABLE_END:
        return curses.color_pair(PAIR_ASCII_BASE + (bval - ASCII_PRINTABLE_START))
    return curses.color_pair(PAIR_HEX_BASE + bval)
