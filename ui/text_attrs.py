"""Frontend-neutral rich-text emphasis flags.

The active branch is Pygame-first, but rich UI segments still carry small
integer emphasis flags. Keep those flags local so common runtime code does not
need to import curses for simple bold/dim/reverse semantics.
"""

# Keep the historic ncurses bit values so existing test fixtures, saved UI
# fragments, and old rich-text rows keep their emphasis when rendered by Pygame.
A_BOLD = 2_097_152
A_DIM = 1_048_576
A_UNDERLINE = 131_072
A_REVERSE = 262_144


_ATTR_BY_NAME = {
    "A_BOLD": A_BOLD,
    "A_DIM": A_DIM,
    "A_UNDERLINE": A_UNDERLINE,
    "A_REVERSE": A_REVERSE,
    "bold": A_BOLD,
    "dim": A_DIM,
    "underline": A_UNDERLINE,
    "reverse": A_REVERSE,
}


def attr_for_name(name, default=0):
    return int(_ATTR_BY_NAME.get(str(name or "").strip(), default) or 0)
