# Shared keycodes consumed by input handling. These match the common ncurses
# values used by the terminal-stable branch, but main no longer imports curses
# just to route Pygame/controller input.
KEY_UP = 259
KEY_DOWN = 258
KEY_LEFT = 260
KEY_RIGHT = 261
KEY_ENTER = 343
KEY_PAGE_UP = 339
KEY_PAGE_DOWN = 338
KEY_HOME = 262
KEY_END = 360
KEY_BACKSPACE = 263
KEY_BACK_TAB = 353
KEY_A1 = 348
KEY_A2 = -1010
KEY_A3 = 349
KEY_B1 = -1011
KEY_B2 = 350
KEY_B3 = -1012
KEY_C1 = 351
KEY_C2 = -1013
KEY_C3 = 352
ENTER_KEYS = tuple(dict.fromkeys((10, 13, KEY_ENTER)))
