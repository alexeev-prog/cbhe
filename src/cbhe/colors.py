import curses

from .constants import (
    BYTE_MAX,
    BYTE_MIN,
    COLOR_SLOTS,
    DEFAULT_BYTE_RGB,
    FIELD_TYPE_COLORS,
    MAX_BYTE_RGB,
    PAIR_ADDR,
    PAIR_CURSOR,
    PAIR_DIRTY,
    PAIR_FIELD_CHECKSUM,
    PAIR_FIELD_DATA,
    PAIR_FIELD_FLAGS,
    PAIR_FIELD_HEADER,
    PAIR_FIELD_MAGIC,
    PAIR_FIELD_OFFSET,
    PAIR_FIELD_RESERVED,
    PAIR_FIELD_SIZE,
    PAIR_FIELD_UNKNOWN,
    PAIR_FIELD_VERSION,
    PAIR_HEADER,
    PAIR_HEADER_EDIT,
    PAIR_HEX_BASE,
    PAIR_HIGHLIGHT,
    PAIR_INTERPRET_BORDER,
    PAIR_INTERPRET_LABEL,
    PAIR_INTERPRET_VALUE,
    PAIR_KEYBINDS,
    PAIR_KEYBINDS_EDIT,
    PAIR_SEARCH_MATCH,
    PAIR_SEP,
    PAIR_STATUS,
    PAIR_STATUS_FIELD,
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
    _init_field_pairs()
    _init_hex_pairs()
    _init_extra_pairs()
    _init_interpret_pairs()


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


def _init_field_pairs() -> None:
    field_colors = [
        (PAIR_FIELD_MAGIC, curses.COLOR_YELLOW, -1),
        (PAIR_FIELD_SIZE, curses.COLOR_GREEN, -1),
        (PAIR_FIELD_OFFSET, curses.COLOR_CYAN, -1),
        (PAIR_FIELD_FLAGS, curses.COLOR_MAGENTA, -1),
        (PAIR_FIELD_CHECKSUM, curses.COLOR_RED, -1),
        (PAIR_FIELD_VERSION, curses.COLOR_BLUE, -1),
        (PAIR_FIELD_DATA, curses.COLOR_WHITE, -1),
        (PAIR_FIELD_RESERVED, -1, curses.COLOR_WHITE),
        (PAIR_FIELD_HEADER, curses.COLOR_BLACK, curses.COLOR_YELLOW),
        (PAIR_FIELD_UNKNOWN, curses.COLOR_WHITE, -1),
    ]

    for pair_id, fg, bg in field_colors:
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


def _init_extra_pairs() -> None:
    curses.init_pair(PAIR_STATUS, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(PAIR_STATUS_FIELD, curses.COLOR_YELLOW, curses.COLOR_BLACK)
    curses.init_pair(PAIR_SEARCH_MATCH, curses.COLOR_BLACK, curses.COLOR_YELLOW)


def _init_interpret_pairs() -> None:
    curses.init_pair(PAIR_INTERPRET_LABEL, curses.COLOR_CYAN, curses.COLOR_BLACK)
    curses.init_pair(PAIR_INTERPRET_VALUE, curses.COLOR_WHITE, curses.COLOR_BLACK)
    curses.init_pair(PAIR_INTERPRET_BORDER, curses.COLOR_BLACK, curses.COLOR_BLACK)


def hex_color(bval: int) -> int:
    return curses.color_pair(PAIR_HEX_BASE + bval)


def ascii_color(bval: int) -> int:
    return hex_color(bval)


def field_color(field_type_name: str) -> int:
    pair_id = FIELD_TYPE_COLORS.get(field_type_name, PAIR_FIELD_UNKNOWN)
    return curses.color_pair(pair_id)
