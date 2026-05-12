from enum import Enum, auto

PAIR_ADDR = 1
PAIR_SEP = 2
PAIR_HEADER = 3
PAIR_KEYBINDS = 4
PAIR_HIGHLIGHT = 5
PAIR_CURSOR = 6
PAIR_DIRTY = 7
PAIR_HEADER_EDIT = 8
PAIR_KEYBINDS_EDIT = 9
PAIR_HEX_BASE = 10
PAIR_FIELD_MAGIC = 366
PAIR_FIELD_SIZE = 367
PAIR_FIELD_OFFSET = 368
PAIR_FIELD_FLAGS = 369
PAIR_FIELD_CHECKSUM = 370
PAIR_FIELD_VERSION = 371
PAIR_FIELD_DATA = 372
PAIR_FIELD_RESERVED = 373
PAIR_FIELD_HEADER = 374
PAIR_FIELD_UNKNOWN = 375
PAIR_STATUS = 376
PAIR_STATUS_FIELD = 377
PAIR_SEARCH_MATCH = 378
PAIR_INTERPRET_LABEL = 379
PAIR_INTERPRET_VALUE = 380
PAIR_INTERPRET_BORDER = 381

FIELD_TYPE_COLORS = {
    "MAGIC": PAIR_FIELD_MAGIC,
    "SIZE": PAIR_FIELD_SIZE,
    "OFFSET": PAIR_FIELD_OFFSET,
    "FLAGS": PAIR_FIELD_FLAGS,
    "CHECKSUM": PAIR_FIELD_CHECKSUM,
    "VERSION": PAIR_FIELD_VERSION,
    "DATA": PAIR_FIELD_DATA,
    "RESERVED": PAIR_FIELD_RESERVED,
    "HEADER": PAIR_FIELD_HEADER,
    "UNKNOWN": PAIR_FIELD_UNKNOWN,
}

WIDTH_CYCLES = [8, 16, 32]

INTERPRET_PANEL_WIDTH = 28


class EditorMode(Enum):
    READ = auto()
    HEX = auto()
    ASCII = auto()


KEYBINDS_READ = [
    ("↑↓", "scroll"),
    ("PgUp/Dn", "page"),
    ("Home/End", "first/last"),
    ("g", "goto"),
    ("w", "width"),
    ("h", "hex"),
    ("a", "ascii"),
    ("i", "interpret"),
    ("?", "hex srch"),
    ("q", "quit"),
]

KEYBINDS_NORMAL = [
    ("↑↓←→", "move"),
    ("e", "edit"),
    ("/", "ascii srch"),
    ("?", "hex srch"),
    ("n/N", "next/prev"),
    ("i", "interpret"),
    ("^S", "save"),
    ("u/^R", "undo/redo"),
    ("Esc/r", "read"),
    ("h/a", "panel"),
]

KEYBINDS_EDIT = [
    ("↑↓←→", "move"),
    ("Esc", "normal"),
    ("^S", "save"),
    ("u/^R", "undo/redo"),
    ("Del/BS", "del"),
]

COLOR_SLOTS = 256
ASCII_PRINTABLE_START = 32
ASCII_PRINTABLE_END = 126
ASCII_COLOR_COUNT = 95
BYTE_MAX = 0xFF
BYTE_MIN = 0x00
DEFAULT_BYTE_RGB = (64, 64, 64)
MAX_BYTE_RGB = (255, 255, 255)

UNDO_LIMIT = 1000


def human_size(n: int) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if n < 1024 or unit == "TiB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} TiB"
