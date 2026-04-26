PAIR_ADDR = 1
PAIR_SEP = 2
PAIR_HEADER = 3
PAIR_KEYBINDS = 4
PAIR_HIGHLIGHT = 5
PAIR_CURSOR = 6
PAIR_DIRTY = 7
PAIR_HEX_BASE = 10
PAIR_ASCII_BASE = 270
PAIR_HEADER_EDIT = 8
PAIR_KEYBINDS_EDIT = 9

WIDTH_CYCLES = [8, 16, 32]

KEYBINDS = [
    ("↑↓", "scroll"),
    ("PgUp/Dn", "page"),
    ("Home/End", "first/last"),
    ("g", "goto"),
    ("w", "width"),
    ("e", "edit"),
    ("/", "search"),
    ("^S", "save"),
    ("Esc", "exit edit"),
    ("q", "quit"),
]

COLOR_SLOTS = 256
ASCII_PRINTABLE_START = 32
ASCII_PRINTABLE_END = 126
ASCII_COLOR_COUNT = 95
BYTE_MAX = 0xFF
BYTE_MIN = 0x00
DEFAULT_BYTE_RGB = (64, 64, 64)
MAX_BYTE_RGB = (255, 255, 255)
