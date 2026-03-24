import curses


# Shared keycodes consumed by input handling across UI backends.
KEY_UP = int(getattr(curses, "KEY_UP", -1001))
KEY_DOWN = int(getattr(curses, "KEY_DOWN", -1002))
KEY_LEFT = int(getattr(curses, "KEY_LEFT", -1003))
KEY_RIGHT = int(getattr(curses, "KEY_RIGHT", -1004))
KEY_ENTER = int(getattr(curses, "KEY_ENTER", -1005))
ENTER_KEYS = tuple(dict.fromkeys((10, 13, KEY_ENTER)))
