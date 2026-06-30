from __future__ import annotations

from dataclasses import dataclass


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


_ACCESSORY_SLOTS = ("earrings", "necklace", "bracelet", "ring_left", "ring_right")
_METAL_BIAS = tuple((slot, 8) for slot in _ACCESSORY_SLOTS)
_SHOE_BIAS = (("shoes", 4),)
_OUTER_BIAS = (("outer", 3),)
_HAT_BIAS = (("hat", 3),)


def _row(
    word: str,
    rgb: tuple[int, int, int],
    c256: int,
    limited: str,
    *,
    attrs: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    weight: int = 1,
    bias: tuple[tuple[str, int], ...] = (),
) -> AppearancePaletteRow:
    return AppearancePaletteRow(
        word=word,
        render_key=f"clothing_{word}",
        pygame_rgb=rgb,
        curses_256=int(c256),
        curses_limited=limited,
        curses_attrs=tuple(attrs),
        tags=tuple(tags),
        roll_weight=int(weight),
        slot_bias=tuple(bias),
    )


APPEARANCE_PALETTE: tuple[AppearancePaletteRow, ...] = (
    _row("black", (82, 84, 92), 238, "white", attrs=("dim",), tags=("neutral", "dark", "muted", "practical"), weight=7, bias=_SHOE_BIAS),
    _row("charcoal", (110, 112, 122), 240, "white", attrs=("dim",), tags=("neutral", "dark", "muted", "practical"), weight=8, bias=_SHOE_BIAS + _OUTER_BIAS),
    _row("white", (238, 238, 232), 255, "white", attrs=("bold",), tags=("neutral", "light", "bright", "polished"), weight=5),
    _row("ivory", (232, 222, 194), 223, "white", attrs=("bold",), tags=("neutral", "light", "polished", "soft"), weight=4),
    _row("cream", (236, 218, 176), 230, "yellow", attrs=("bold",), tags=("neutral", "light", "soft", "muted"), weight=5),
    _row("gray", (156, 160, 168), 246, "white", tags=("neutral", "muted", "practical"), weight=8),
    _row("slate", (104, 128, 154), 109, "blue", tags=("neutral", "cool", "muted", "practical"), weight=6, bias=_OUTER_BIAS),
    _row("denim", (78, 128, 184), 67, "cyan", tags=("blue", "cool", "street", "practical"), weight=7, bias=(("bottom", 5), ("outer", 4), ("hat", 2))),
    _row("blue", (76, 150, 222), 75, "blue", attrs=("bold",), tags=("blue", "cool", "bright"), weight=5),
    _row("navy", (68, 86, 148), 61, "blue", tags=("blue", "cool", "dark", "muted", "polished"), weight=6, bias=_SHOE_BIAS + _OUTER_BIAS),
    _row("cobalt", (62, 112, 230), 69, "blue", attrs=("bold",), tags=("blue", "cool", "bright", "flashy"), weight=3),
    _row("olive", (124, 154, 88), 107, "green", tags=("green", "earth", "muted", "practical"), weight=6, bias=_OUTER_BIAS),
    _row("green", (90, 172, 104), 71, "green", attrs=("bold",), tags=("green", "earth", "bright"), weight=4),
    _row("moss", (99, 140, 76), 65, "green", tags=("green", "earth", "muted", "practical"), weight=6, bias=_OUTER_BIAS + _HAT_BIAS),
    _row("rust", (190, 98, 58), 166, "yellow", tags=("warm", "earth", "rough", "street"), weight=4, bias=_OUTER_BIAS),
    _row("brown", (145, 103, 70), 137, "yellow", attrs=("dim",), tags=("warm", "earth", "muted", "practical"), weight=7, bias=_SHOE_BIAS + _OUTER_BIAS),
    _row("tan", (198, 164, 110), 180, "yellow", tags=("warm", "earth", "muted", "practical"), weight=6),
    _row("red", (212, 80, 74), 167, "red", attrs=("bold",), tags=("red", "warm", "bright", "flashy"), weight=3),
    _row("wine", (176, 76, 120), 168, "magenta", tags=("red", "purple", "dark", "polished", "flashy"), weight=3),
    _row("coral", (232, 116, 96), 209, "red", attrs=("bold",), tags=("red", "warm", "bright", "soft", "flashy"), weight=3),
    _row("violet", (168, 112, 218), 141, "magenta", attrs=("bold",), tags=("purple", "cool", "bright", "flashy"), weight=3),
    _row("pink", (226, 134, 176), 218, "magenta", attrs=("bold",), tags=("red", "soft", "bright", "flashy"), weight=3),
    _row("gold", (230, 190, 76), 221, "yellow", attrs=("bold",), tags=("metal", "warm", "bright", "jewelry", "flashy"), weight=1, bias=_METAL_BIAS),
    _row("brass", (188, 152, 74), 178, "yellow", tags=("metal", "warm", "earth", "jewelry"), weight=1, bias=_METAL_BIAS),
    _row("silver", (206, 210, 214), 250, "white", tags=("metal", "neutral", "cool", "jewelry", "polished"), weight=1, bias=_METAL_BIAS),
    _row("steel", (136, 150, 162), 109, "blue", tags=("metal", "neutral", "cool", "practical", "jewelry"), weight=1, bias=_METAL_BIAS + _SHOE_BIAS),
    _row("onyx", (56, 58, 66), 235, "white", attrs=("dim",), tags=("metal", "neutral", "dark", "jewelry", "muted"), weight=1, bias=_METAL_BIAS + _SHOE_BIAS),
    _row("teal", (62, 176, 170), 80, "cyan", attrs=("bold",), tags=("blue", "green", "cool", "bright", "flashy"), weight=4),
    _row("maroon", (128, 52, 70), 124, "magenta", tags=("red", "dark", "muted", "polished"), weight=3),
    _row("burgundy", (142, 45, 82), 125, "magenta", tags=("red", "purple", "dark", "polished"), weight=3),
    _row("crimson", (202, 46, 66), 160, "red", attrs=("bold",), tags=("red", "bright", "flashy"), weight=2),
    _row("orange", (232, 126, 54), 208, "yellow", attrs=("bold",), tags=("warm", "bright", "flashy"), weight=3),
    _row("safety_orange", (255, 100, 18), 202, "yellow", attrs=("bold",), tags=("warm", "bright", "flashy", "safety", "high_visibility"), weight=0),
    _row("amber", (222, 156, 54), 214, "yellow", attrs=("bold",), tags=("warm", "bright", "earth"), weight=3),
    _row("mustard", (190, 154, 58), 178, "yellow", tags=("warm", "earth", "muted"), weight=4),
    _row("yellow", (236, 210, 72), 226, "yellow", attrs=("bold",), tags=("warm", "bright", "flashy"), weight=2),
    _row("copper", (186, 112, 66), 172, "yellow", tags=("metal", "warm", "earth", "jewelry"), weight=1, bias=_METAL_BIAS),
    _row("bronze", (154, 118, 68), 136, "yellow", tags=("metal", "warm", "earth", "jewelry", "muted"), weight=1, bias=_METAL_BIAS),
    _row("khaki", (180, 166, 112), 144, "yellow", tags=("earth", "muted", "practical"), weight=6, bias=(("bottom", 3), ("outer", 2))),
    _row("sand", (214, 188, 138), 180, "yellow", tags=("earth", "light", "muted", "soft"), weight=5),
    _row("sage", (154, 176, 132), 108, "green", tags=("green", "earth", "muted", "soft"), weight=5),
    _row("forest", (54, 126, 80), 29, "green", tags=("green", "earth", "dark", "practical"), weight=5, bias=_OUTER_BIAS),
    _row("emerald", (52, 184, 112), 41, "green", attrs=("bold",), tags=("green", "bright", "flashy"), weight=3),
    _row("mint", (142, 220, 176), 121, "green", attrs=("bold",), tags=("green", "light", "soft", "bright"), weight=3),
    _row("lime", (168, 218, 74), 118, "green", attrs=("bold",), tags=("green", "bright", "flashy"), weight=2),
    _row("aqua", (92, 220, 214), 123, "cyan", attrs=("bold",), tags=("blue", "green", "cool", "bright"), weight=3),
    _row("turquoise", (62, 190, 186), 80, "cyan", attrs=("bold",), tags=("blue", "green", "cool", "bright"), weight=3),
    _row("sky", (116, 188, 238), 117, "cyan", attrs=("bold",), tags=("blue", "cool", "light", "bright"), weight=4),
    _row("cerulean", (60, 150, 216), 32, "cyan", tags=("blue", "cool", "bright"), weight=4),
    _row("indigo", (78, 78, 164), 61, "blue", tags=("blue", "purple", "cool", "dark"), weight=3),
    _row("periwinkle", (158, 162, 228), 147, "blue", attrs=("bold",), tags=("blue", "purple", "cool", "soft"), weight=3),
    _row("lavender", (190, 150, 220), 183, "magenta", attrs=("bold",), tags=("purple", "soft", "light"), weight=3),
    _row("lilac", (204, 136, 214), 176, "magenta", attrs=("bold",), tags=("purple", "soft", "bright"), weight=3),
    _row("purple", (138, 86, 190), 99, "magenta", attrs=("bold",), tags=("purple", "cool", "flashy"), weight=3),
    _row("plum", (112, 62, 132), 96, "magenta", tags=("purple", "dark", "muted", "polished"), weight=3),
    _row("magenta", (214, 72, 174), 201, "magenta", attrs=("bold",), tags=("purple", "red", "bright", "flashy"), weight=2),
    _row("rose", (220, 112, 144), 211, "magenta", attrs=("bold",), tags=("red", "soft", "bright"), weight=3),
    _row("salmon", (224, 132, 112), 209, "red", attrs=("bold",), tags=("red", "warm", "soft", "light"), weight=3),
    _row("peach", (238, 172, 128), 216, "yellow", attrs=("bold",), tags=("warm", "soft", "light"), weight=3),
    _row("smoke", (124, 128, 136), 244, "white", attrs=("dim",), tags=("neutral", "muted", "cool"), weight=6),
    _row("ash", (176, 178, 182), 247, "white", tags=("neutral", "muted", "light"), weight=6),
)

_ROWS_BY_WORD = {row.word: row for row in APPEARANCE_PALETTE}
_ROWS_BY_RENDER_KEY = {row.render_key: row for row in APPEARANCE_PALETTE}


def appearance_color_words() -> tuple[str, ...]:
    return tuple(row.word for row in APPEARANCE_PALETTE)


def palette_row_for_color_word(word: str) -> AppearancePaletteRow | None:
    return _ROWS_BY_WORD.get(str(word or "").strip().lower())


def render_key_for_color_word(word: str, default: str | None = None) -> str | None:
    row = palette_row_for_color_word(word)
    return row.render_key if row else default


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
    row = palette_row_for_color_word(word)
    return row.tags if row else ()


def choose_appearance_color_word(rng, *, slots=()) -> str:
    slot_tokens = {
        str(slot or "").strip().lower()
        for slot in tuple(slots or ())
        if str(slot or "").strip()
    }
    weighted: list[tuple[str, int]] = []
    for row in APPEARANCE_PALETTE:
        weight = max(0, int(row.roll_weight))
        if slot_tokens:
            bias = dict(row.slot_bias)
            weight += sum(max(0, int(bias.get(slot, 0))) for slot in slot_tokens)
        if weight > 0:
            weighted.append((row.word, weight))
    if not weighted:
        return APPEARANCE_PALETTE[0].word
    total = sum(weight for _word, weight in weighted)
    roll = rng.uniform(0, total)
    cursor = 0.0
    for word, weight in weighted:
        cursor += weight
        if roll <= cursor:
            return word
    return weighted[-1][0]
