from __future__ import annotations

from dataclasses import dataclass

from game.color_words import (
    COLOR_WORD_PALETTE,
    choose_color_word,
    clothing_render_key_for_color_word,
    color_word_row,
    color_word_tags,
    find_closest_native_color_word,
    normalize_color_word,
)


@dataclass(frozen=True)
class AppearancePaletteRow:
    word: str
    render_key: str
    pygame_rgb: tuple[int, int, int]
    curses_256: int
    curses_limited: str
    curses_attrs: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    roll_weight: int = 1
    slot_bias: tuple[tuple[str, int], ...] = ()


_CURSES_COMPAT: dict[str, tuple[int, str, tuple[str, ...]]] = {
    "black": (238, "white", ("dim",)),
    "total_black": (232, "white", ("dim",)),
    "charcoal": (240, "white", ("dim",)),
    "white": (255, "white", ("bold",)),
    "ivory": (223, "white", ("bold",)),
    "cream": (230, "yellow", ("bold",)),
    "gray": (246, "white", ()),
    "slate": (109, "blue", ()),
    "denim": (67, "cyan", ()),
    "blue": (75, "blue", ("bold",)),
    "navy": (61, "blue", ()),
    "cobalt": (69, "blue", ("bold",)),
    "olive": (107, "green", ()),
    "green": (71, "green", ("bold",)),
    "moss": (65, "green", ()),
    "rust": (166, "yellow", ()),
    "brown": (137, "yellow", ("dim",)),
    "tan": (180, "yellow", ()),
    "red": (167, "red", ("bold",)),
    "wine": (168, "magenta", ()),
    "coral": (209, "red", ("bold",)),
    "violet": (141, "magenta", ("bold",)),
    "pink": (218, "magenta", ("bold",)),
    "gold": (221, "yellow", ("bold",)),
    "brass": (178, "yellow", ()),
    "silver": (250, "white", ()),
    "steel": (109, "blue", ()),
    "onyx": (235, "white", ("dim",)),
    "teal": (80, "cyan", ("bold",)),
    "maroon": (124, "magenta", ()),
    "burgundy": (125, "magenta", ()),
    "crimson": (160, "red", ("bold",)),
    "orange": (208, "yellow", ("bold",)),
    "safety_orange": (202, "yellow", ("bold",)),
    "amber": (214, "yellow", ("bold",)),
    "mustard": (178, "yellow", ()),
    "yellow": (226, "yellow", ("bold",)),
    "copper": (172, "yellow", ()),
    "bronze": (136, "yellow", ()),
    "khaki": (144, "yellow", ()),
    "sand": (180, "yellow", ()),
    "sage": (108, "green", ()),
    "forest": (29, "green", ()),
    "emerald": (41, "green", ("bold",)),
    "mint": (121, "green", ("bold",)),
    "lime": (118, "green", ("bold",)),
    "aqua": (123, "cyan", ("bold",)),
    "turquoise": (80, "cyan", ("bold",)),
    "sky": (117, "cyan", ("bold",)),
    "cerulean": (32, "cyan", ()),
    "indigo": (61, "blue", ()),
    "periwinkle": (147, "blue", ("bold",)),
    "lavender": (183, "magenta", ("bold",)),
    "lilac": (176, "magenta", ("bold",)),
    "purple": (99, "magenta", ("bold",)),
    "plum": (96, "magenta", ()),
    "magenta": (201, "magenta", ("bold",)),
    "rose": (211, "magenta", ("bold",)),
    "salmon": (209, "red", ("bold",)),
    "peach": (216, "yellow", ("bold",)),
    "smoke": (244, "white", ("dim",)),
    "ash": (247, "white", ()),
}


def _appearance_row(row) -> AppearancePaletteRow:
    curses_256, limited, attrs = _CURSES_COMPAT.get(row.word, (250, "white", ()))
    return AppearancePaletteRow(
        word=row.word,
        render_key=clothing_render_key_for_color_word(row.word) or f"clothing_{row.word}",
        pygame_rgb=row.pygame_rgb,
        curses_256=int(curses_256),
        curses_limited=str(limited),
        curses_attrs=tuple(attrs),
        tags=row.tags,
        roll_weight=int(row.roll_weight),
        slot_bias=tuple(row.slot_bias),
    )


APPEARANCE_PALETTE: tuple[AppearancePaletteRow, ...] = tuple(
    _appearance_row(row) for row in COLOR_WORD_PALETTE
)

_ROWS_BY_WORD = {row.word: row for row in APPEARANCE_PALETTE}
_ROWS_BY_RENDER_KEY = {row.render_key: row for row in APPEARANCE_PALETTE}


def appearance_color_words() -> tuple[str, ...]:
    return tuple(row.word for row in APPEARANCE_PALETTE)


def palette_row_for_color_word(word: str) -> AppearancePaletteRow | None:
    normalized = normalize_color_word(word)
    return _ROWS_BY_WORD.get(normalized)


def render_key_for_color_word(word: str, default: str | None = None) -> str | None:
    normalized = normalize_color_word(word)
    if not normalized:
        return default
    return clothing_render_key_for_color_word(normalized, default=default)


def fallback_render_key_for_color_word(word: str, default: str | None = None) -> str | None:
    native_word = find_closest_native_color_word(word, default="")
    if not native_word:
        return render_key_for_color_word(word, default=default)
    return clothing_render_key_for_color_word(native_word, default=default)


def palette_row_for_render_key(render_key: str) -> AppearancePaletteRow | None:
    return _ROWS_BY_RENDER_KEY.get(str(render_key or "").strip().lower())


def pygame_palette_entries() -> dict[str, tuple[int, int, int]]:
    return {row.render_key: row.pygame_rgb for row in APPEARANCE_PALETTE}


def curses_palette_entries(colors: int | None = None) -> dict[str, dict[str, object]]:
    use_256 = int(colors or 0) >= 256
    rows = {}
    for row in APPEARANCE_PALETTE:
        rows[row.render_key] = {
            "fg": row.curses_256 if use_256 else row.curses_limited,
            "attrs": () if use_256 else row.curses_attrs,
        }
    return rows


def tags_for_color_word(word: str) -> tuple[str, ...]:
    row = color_word_row(word)
    return color_word_tags(row.word) if row else ()


def choose_appearance_color_word(rng, *, slots=()) -> str:
    return choose_color_word(rng, slots=slots, include_reserved=False)
