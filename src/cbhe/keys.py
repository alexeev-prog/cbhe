import curses

KEY_UP = curses.KEY_UP
KEY_DOWN = curses.KEY_DOWN
KEY_LEFT = curses.KEY_LEFT
KEY_RIGHT = curses.KEY_RIGHT
KEY_HOME = curses.KEY_HOME
KEY_END = curses.KEY_END
KEY_PPAGE = curses.KEY_PPAGE
KEY_NPAGE = curses.KEY_NPAGE
KEY_BACKSPACE = curses.KEY_BACKSPACE
KEY_DC = curses.KEY_DC
KEY_RESIZE = curses.KEY_RESIZE

KEY_ESC = 27
KEY_CTRL_R = 18
KEY_CTRL_S = 19
KEY_BACKSPACE_ALT1 = 127
KEY_BACKSPACE_ALT2 = 8

GOTO_KEYS = {ord("g"), ord("G")}
SEARCH_ASCII_KEY = ord("/")
SEARCH_HEX_KEY = ord("?")
SEARCH_NEXT_KEY = ord("n")
SEARCH_PREV_KEY = ord("N")
INTERPRET_KEYS = {ord("i"), ord("I")}
QUIT_KEYS = {ord("q"), ord("Q")}
