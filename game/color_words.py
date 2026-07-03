from __future__ import annotations

import colorsys
import html
import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ColorWordRow:
    word: str
    pygame_rgb: tuple[int, int, int]
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
    *,
    tags: tuple[str, ...] = (),
    weight: int = 1,
    bias: tuple[tuple[str, int], ...] = (),
) -> ColorWordRow:
    return ColorWordRow(
        word=str(word),
        pygame_rgb=tuple(int(channel) for channel in rgb[:3]),
        tags=tuple(str(tag) for tag in tags),
        roll_weight=int(weight),
        slot_bias=tuple((str(slot), int(value)) for slot, value in tuple(bias or ())),
    )


_COLOR_WORD_HEX_PATH = Path(__file__).resolve().parent / "color_words_hex_values.json"


_CURATED_COLOR_WORD_PALETTE: tuple[ColorWordRow, ...] = (
    _row("black", (82, 84, 92), tags=("neutral", "dark", "muted", "practical"), weight=7, bias=_SHOE_BIAS),
    _row("total_black", (28, 31, 36), tags=("neutral", "dark", "muted", "render_only"), weight=0),
    _row("charcoal", (110, 112, 122), tags=("neutral", "dark", "muted", "practical"), weight=8, bias=_SHOE_BIAS + _OUTER_BIAS),
    _row("white", (238, 238, 232), tags=("neutral", "light", "bright", "polished"), weight=5),
    _row("ivory", (232, 222, 194), tags=("neutral", "light", "polished", "soft"), weight=4),
    _row("cream", (236, 218, 176), tags=("neutral", "light", "soft", "muted"), weight=5),
    _row("gray", (156, 160, 168), tags=("neutral", "muted", "practical"), weight=8),
    _row("slate", (104, 128, 154), tags=("neutral", "cool", "muted", "practical"), weight=6, bias=_OUTER_BIAS),
    _row("denim", (78, 128, 184), tags=("blue", "cool", "street", "practical"), weight=7, bias=(("bottom", 5), ("outer", 4), ("hat", 2))),
    _row("blue", (76, 150, 222), tags=("blue", "cool", "bright"), weight=5),
    _row("navy", (68, 86, 148), tags=("blue", "cool", "dark", "muted", "polished"), weight=6, bias=_SHOE_BIAS + _OUTER_BIAS),
    _row("cobalt", (62, 112, 230), tags=("blue", "cool", "bright", "flashy"), weight=3),
    _row("olive", (124, 154, 88), tags=("green", "earth", "muted", "practical"), weight=6, bias=_OUTER_BIAS),
    _row("green", (90, 172, 104), tags=("green", "earth", "bright"), weight=4),
    _row("moss", (99, 140, 76), tags=("green", "earth", "muted", "practical"), weight=6, bias=_OUTER_BIAS + _HAT_BIAS),
    _row("rust", (190, 98, 58), tags=("warm", "earth", "rough", "street"), weight=4, bias=_OUTER_BIAS),
    _row("brown", (145, 103, 70), tags=("warm", "earth", "muted", "practical"), weight=7, bias=_SHOE_BIAS + _OUTER_BIAS),
    _row("tan", (198, 164, 110), tags=("warm", "earth", "muted", "practical"), weight=6),
    _row("red", (212, 80, 74), tags=("red", "warm", "bright", "flashy"), weight=3),
    _row("wine", (176, 76, 120), tags=("red", "purple", "dark", "polished", "flashy"), weight=3),
    _row("coral", (232, 116, 96), tags=("red", "warm", "bright", "soft", "flashy"), weight=3),
    _row("violet", (168, 112, 218), tags=("purple", "cool", "bright", "flashy"), weight=3),
    _row("pink", (226, 134, 176), tags=("red", "soft", "bright", "flashy"), weight=3),
    _row("gold", (230, 190, 76), tags=("metal", "warm", "bright", "jewelry", "flashy"), weight=1, bias=_METAL_BIAS),
    _row("brass", (188, 152, 74), tags=("metal", "warm", "earth", "jewelry"), weight=1, bias=_METAL_BIAS),
    _row("silver", (206, 210, 214), tags=("metal", "neutral", "cool", "jewelry", "polished"), weight=1, bias=_METAL_BIAS),
    _row("steel", (136, 150, 162), tags=("metal", "neutral", "cool", "practical", "jewelry"), weight=1, bias=_METAL_BIAS + _SHOE_BIAS),
    _row("onyx", (56, 58, 66), tags=("metal", "neutral", "dark", "jewelry", "muted"), weight=1, bias=_METAL_BIAS + _SHOE_BIAS),
    _row("teal", (62, 176, 170), tags=("blue", "green", "cool", "bright", "flashy"), weight=4),
    _row("maroon", (128, 52, 70), tags=("red", "dark", "muted", "polished"), weight=3),
    _row("burgundy", (142, 45, 82), tags=("red", "purple", "dark", "polished"), weight=3),
    _row("crimson", (202, 46, 66), tags=("red", "bright", "flashy"), weight=2),
    _row("orange", (232, 126, 54), tags=("warm", "bright", "flashy"), weight=3),
    _row("safety_orange", (255, 100, 18), tags=("warm", "bright", "flashy", "safety", "high_visibility"), weight=0),
    _row("amber", (222, 156, 54), tags=("warm", "bright", "earth"), weight=3),
    _row("mustard", (190, 154, 58), tags=("warm", "earth", "muted"), weight=4),
    _row("yellow", (236, 210, 72), tags=("warm", "bright", "flashy"), weight=2),
    _row("copper", (186, 112, 66), tags=("metal", "warm", "earth", "jewelry"), weight=1, bias=_METAL_BIAS),
    _row("bronze", (154, 118, 68), tags=("metal", "warm", "earth", "jewelry", "muted"), weight=1, bias=_METAL_BIAS),
    _row("khaki", (180, 166, 112), tags=("earth", "muted", "practical"), weight=6, bias=(("bottom", 3), ("outer", 2))),
    _row("sand", (214, 188, 138), tags=("earth", "light", "muted", "soft"), weight=5),
    _row("sage", (154, 176, 132), tags=("green", "earth", "muted", "soft"), weight=5),
    _row("forest", (54, 126, 80), tags=("green", "earth", "dark", "practical"), weight=5, bias=_OUTER_BIAS),
    _row("emerald", (52, 184, 112), tags=("green", "bright", "flashy"), weight=3),
    _row("mint", (142, 220, 176), tags=("green", "light", "soft", "bright"), weight=3),
    _row("lime", (168, 218, 74), tags=("green", "bright", "flashy"), weight=2),
    _row("aqua", (92, 220, 214), tags=("blue", "green", "cool", "bright"), weight=3),
    _row("turquoise", (62, 190, 186), tags=("blue", "green", "cool", "bright"), weight=3),
    _row("sky", (116, 188, 238), tags=("blue", "cool", "light", "bright"), weight=4),
    _row("cerulean", (60, 150, 216), tags=("blue", "cool", "bright"), weight=4),
    _row("indigo", (78, 78, 164), tags=("blue", "purple", "cool", "dark"), weight=3),
    _row("periwinkle", (158, 162, 228), tags=("blue", "purple", "cool", "soft"), weight=3),
    _row("lavender", (190, 150, 220), tags=("purple", "soft", "light"), weight=3),
    _row("lilac", (204, 136, 214), tags=("purple", "soft", "bright"), weight=3),
    _row("purple", (138, 86, 190), tags=("purple", "cool", "flashy"), weight=3),
    _row("plum", (112, 62, 132), tags=("purple", "dark", "muted", "polished"), weight=3),
    _row("magenta", (214, 72, 174), tags=("purple", "red", "bright", "flashy"), weight=2),
    _row("rose", (220, 112, 144), tags=("red", "soft", "bright"), weight=3),
    _row("salmon", (224, 132, 112), tags=("red", "warm", "soft", "light"), weight=3),
    _row("peach", (238, 172, 128), tags=("warm", "soft", "light"), weight=3),
    _row("smoke", (124, 128, 136), tags=("neutral", "muted", "cool"), weight=6),
    _row("ash", (176, 178, 182), tags=("neutral", "muted", "light"), weight=6),
)

COLOR_WORD_ALIASES: dict[str, str] = {
    "grey": "gray",
    "bright_red": "red",
    "bright_green": "green",
    "bright_blue": "blue",
    "dark": "black",
}

CASINO_COLOR_WORDS: tuple[str, ...] = (
    "red",
    "green",
    "blue",
    "gold",
    "black",
    "white",
    "pink",
    "violet",
    "coral",
    "charcoal",
    "navy",
    "purple",
    "olive",
    "brown",
)

_FLORA_FLOWER_COLOR_KEYS: dict[str, str] = {
    "black": "flora_flower_violet",
    "total_black": "flora_flower_violet",
    "charcoal": "flora_flower_violet",
    "white": "flora_flower_white",
    "ivory": "flora_flower_white",
    "cream": "flora_flower_white",
    "gray": "flora_flower_white",
    "slate": "flora_flower_blue",
    "denim": "flora_flower_blue",
    "blue": "flora_flower_blue",
    "navy": "flora_flower_blue",
    "cobalt": "flora_flower_blue",
    "olive": "flora_shrub",
    "green": "flora_leaf",
    "moss": "flora_moss",
    "rust": "flora_flower_coral",
    "brown": "flora_shrub",
    "tan": "flora_flower_gold",
    "red": "flora_flower_coral",
    "wine": "flora_flower_violet",
    "coral": "flora_flower_coral",
    "violet": "flora_flower_violet",
    "pink": "flora_flower_pink",
    "gold": "flora_flower_gold",
    "brass": "flora_flower_gold",
    "silver": "flora_flower_white",
    "steel": "flora_flower_blue",
    "onyx": "flora_flower_violet",
    "teal": "flora_flower_blue",
    "maroon": "flora_flower_violet",
    "burgundy": "flora_flower_violet",
    "crimson": "flora_flower_coral",
    "orange": "flora_flower_coral",
    "safety_orange": "flora_flower_coral",
    "amber": "flora_flower_gold",
    "mustard": "flora_flower_gold",
    "yellow": "flora_flower_gold",
    "copper": "flora_flower_coral",
    "bronze": "flora_flower_gold",
    "khaki": "flora_grass",
    "sand": "flora_flower_gold",
    "sage": "flora_shrub",
    "forest": "flora_shrub",
    "emerald": "flora_leaf",
    "mint": "flora_leaf",
    "lime": "flora_leaf",
    "aqua": "flora_flower_blue",
    "turquoise": "flora_flower_blue",
    "sky": "flora_flower_blue",
    "cerulean": "flora_flower_blue",
    "indigo": "flora_flower_violet",
    "periwinkle": "flora_flower_violet",
    "lavender": "flora_flower_violet",
    "lilac": "flora_flower_violet",
    "purple": "flora_flower_violet",
    "plum": "flora_flower_violet",
    "magenta": "flora_flower_violet",
    "rose": "flora_flower_pink",
    "salmon": "flora_flower_coral",
    "peach": "flora_flower_coral",
    "smoke": "flora_flower_white",
    "ash": "flora_flower_white",
}

_WORLD_OBJECT_COLOR_KEYS: dict[str, str] = {
    "black": "world_object_charcoal",
    "total_black": "world_object_charcoal",
    "charcoal": "world_object_charcoal",
    "white": "world_object_white",
    "ivory": "world_object_white",
    "cream": "world_object_white",
    "gray": "world_object_silver",
    "slate": "world_object_silver",
    "denim": "world_object_blue",
    "blue": "world_object_blue",
    "navy": "world_object_blue",
    "cobalt": "world_object_blue",
    "olive": "world_object_green",
    "green": "world_object_green",
    "moss": "world_object_green",
    "rust": "world_object_coral",
    "brown": "world_object_gold",
    "tan": "world_object_gold",
    "red": "world_object_red",
    "wine": "world_object_red",
    "coral": "world_object_coral",
    "violet": "world_object_purple",
    "pink": "world_object_pink",
    "gold": "world_object_gold",
    "brass": "world_object_gold",
    "silver": "world_object_silver",
    "steel": "world_object_silver",
    "onyx": "world_object_charcoal",
    "teal": "world_object_blue",
    "maroon": "world_object_red",
    "burgundy": "world_object_red",
    "crimson": "world_object_red",
    "orange": "world_object_coral",
    "safety_orange": "world_object_coral",
    "amber": "world_object_gold",
    "mustard": "world_object_gold",
    "yellow": "world_object_gold",
    "copper": "world_object_gold",
    "bronze": "world_object_gold",
    "khaki": "world_object_gold",
    "sand": "world_object_gold",
    "sage": "world_object_green",
    "forest": "world_object_green",
    "emerald": "world_object_green",
    "mint": "world_object_green",
    "lime": "world_object_green",
    "aqua": "world_object_blue",
    "turquoise": "world_object_blue",
    "sky": "world_object_blue",
    "cerulean": "world_object_blue",
    "indigo": "world_object_purple",
    "periwinkle": "world_object_purple",
    "lavender": "world_object_purple",
    "lilac": "world_object_purple",
    "purple": "world_object_purple",
    "plum": "world_object_purple",
    "magenta": "world_object_purple",
    "rose": "world_object_pink",
    "salmon": "world_object_coral",
    "peach": "world_object_coral",
    "smoke": "world_object_silver",
    "ash": "world_object_silver",
}


def _clean_word(value: object) -> str:
    text = html.unescape(str(value or "")).strip().lower()
    text = text.replace("&", " and ")
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return re.sub(r"_+", "_", text).strip("_")


def _parse_hex_rgb(value: object) -> tuple[int, int, int] | None:
    text = str(value or "").strip()
    if text.startswith("#"):
        text = text[1:]
    elif text.lower().startswith("0x"):
        text = text[2:]
    if len(text) == 3:
        text = "".join(ch * 2 for ch in text)
    if len(text) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", text):
        return None
    return tuple(int(text[index : index + 2], 16) for index in (0, 2, 4))


def _clamp_channel(value: object) -> int:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return 0
    return max(0, min(255, int(round(numeric))))


def _coerce_rgb_channels(channels: object) -> tuple[int, int, int] | None:
    if not isinstance(channels, (tuple, list)) or len(channels) < 3:
        return None
    try:
        numeric = tuple(float(channel) for channel in tuple(channels[:3]))
    except (TypeError, ValueError):
        return None
    if all(0.0 <= channel <= 1.0 for channel in numeric):
        return tuple(_clamp_channel(channel * 255.0) for channel in numeric)
    return tuple(_clamp_channel(channel) for channel in numeric)


def _coerce_rgb(value: object) -> tuple[int, int, int] | None:
    if value is None:
        return None
    if isinstance(value, str):
        row = color_word_row(value)
        if row:
            return row.pygame_rgb
        rgb = _parse_hex_rgb(value)
        if rgb is not None:
            return rgb
        match = re.fullmatch(
            r"rgba?\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)(?:\s*,\s*[0-9.]+)?\s*\)",
            value.strip(),
            flags=re.IGNORECASE,
        )
        if match:
            return tuple(_clamp_channel(part) for part in match.groups()[:3])
        return None
    if isinstance(value, dict):
        for key in ("color", "hex", "rgb", "value"):
            if key in value:
                rgb = _coerce_rgb(value.get(key))
                if rgb is not None:
                    return rgb
        if {"r", "g", "b"} <= set(value):
            return _coerce_rgb_channels((value.get("r"), value.get("g"), value.get("b")))
        return None
    if isinstance(value, (tuple, list)) and len(value) >= 3:
        return _coerce_rgb_channels(value)
    return None


def parse_color_value(value: object, fallback: tuple[int, int, int] | None = None) -> tuple[int, int, int] | None:
    rgb = _coerce_rgb(value)
    return rgb if rgb is not None else fallback


def _imported_tags_for_rgb(word: str, rgb: tuple[int, int, int]) -> tuple[str, ...]:
    r, g, b = (max(0, min(255, int(channel))) / 255.0 for channel in rgb)
    hue, saturation, value = colorsys.rgb_to_hsv(r, g, b)
    hue_deg = hue * 360.0
    tags: list[str] = ["imported", "lookup_only"]
    tokens = set(word.split("_"))
    if value <= 0.18:
        tags.append("dark")
    elif value >= 0.82:
        tags.append("light")
    if saturation <= 0.12:
        tags.append("neutral")
        if value >= 0.82:
            tags.append("white")
        elif value <= 0.18:
            tags.append("black")
        else:
            tags.append("gray")
    else:
        if hue_deg < 15 or hue_deg >= 345:
            tags.extend(("red", "warm"))
        elif hue_deg < 42:
            tags.extend(("orange", "warm"))
        elif hue_deg < 68:
            tags.extend(("yellow", "warm"))
        elif hue_deg < 155:
            tags.extend(("green", "cool"))
        elif hue_deg < 195:
            tags.extend(("cyan", "blue", "cool"))
        elif hue_deg < 245:
            tags.extend(("blue", "cool"))
        elif hue_deg < 285:
            tags.extend(("purple", "cool"))
        elif hue_deg < 330:
            tags.extend(("magenta", "purple", "cool"))
        else:
            tags.extend(("pink", "red", "warm"))
    for tag in (
        "black",
        "white",
        "gray",
        "blue",
        "green",
        "red",
        "pink",
        "rose",
        "violet",
        "purple",
        "magenta",
        "orange",
        "yellow",
        "gold",
        "brown",
        "tan",
        "olive",
        "lime",
        "teal",
        "aqua",
        "cyan",
        "silver",
        "copper",
        "bronze",
        "brass",
    ):
        if tag in tokens:
            tags.append(tag)
    if {"gold", "silver", "copper", "bronze", "brass"} & tokens:
        tags.append("metal")
    if {"brown", "tan", "olive", "umber", "sienna", "sepia", "sand", "earth"} & tokens:
        tags.append("earth")
    if saturation <= 0.25:
        tags.append("muted")
    elif value >= 0.72:
        tags.append("bright")
    return tuple(dict.fromkeys(tags))


def _dedupe_imported_word(word: str, used: set[str], *, native_collision: bool) -> str:
    if word not in used:
        return word
    suffix_base = f"{word}_hex" if native_collision else word
    index = 1 if native_collision else 2
    candidate = suffix_base
    while candidate in used:
        candidate = f"{suffix_base}_{index}"
        index += 1
    return candidate


def _load_imported_color_word_palette() -> tuple[ColorWordRow, ...]:
    try:
        raw_document = json.loads(_COLOR_WORD_HEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ()
    if isinstance(raw_document, list):
        raw_rows = raw_document
    elif isinstance(raw_document, dict):
        meta = raw_document.get("_meta", {})
        schema_version = meta.get("schema_version") if isinstance(meta, dict) else None
        try:
            schema_version = int(schema_version)
        except (TypeError, ValueError):
            return ()
        if schema_version != 1:
            return ()
        raw_rows = []
        for key, value in raw_document.items():
            if str(key).startswith("_") or not isinstance(value, dict):
                continue
            row = dict(value)
            row.setdefault("id", key)
            raw_rows.append(row)
    else:
        return ()
    native_words = {row.word for row in _CURATED_COLOR_WORD_PALETTE}
    used_words = set(native_words)
    rows: list[ColorWordRow] = []
    for raw in raw_rows:
        if not isinstance(raw, dict):
            continue
        word = _clean_word(raw.get("name"))
        rgb = _parse_hex_rgb(raw.get("color"))
        if not word or rgb is None:
            continue
        word = _dedupe_imported_word(word, used_words, native_collision=word in native_words)
        used_words.add(word)
        rows.append(_row(word, rgb, tags=_imported_tags_for_rgb(word, rgb), weight=0))
    return tuple(rows)


CURATED_COLOR_WORD_PALETTE: tuple[ColorWordRow, ...] = _CURATED_COLOR_WORD_PALETTE
IMPORTED_COLOR_WORD_PALETTE: tuple[ColorWordRow, ...] = _load_imported_color_word_palette()
COLOR_WORD_PALETTE: tuple[ColorWordRow, ...] = CURATED_COLOR_WORD_PALETTE + IMPORTED_COLOR_WORD_PALETTE
_ROWS_BY_WORD = {row.word: row for row in COLOR_WORD_PALETTE}


def normalize_color_word(value: object, default: str = "") -> str:
    word = _clean_word(value)
    if word in _ROWS_BY_WORD:
        return word
    word = COLOR_WORD_ALIASES.get(word, word)
    if word in _ROWS_BY_WORD:
        return word
    return normalize_color_word(default) if default and default != value else ""


def curated_color_words(*, include_reserved: bool = True) -> tuple[str, ...]:
    if include_reserved:
        return tuple(row.word for row in CURATED_COLOR_WORD_PALETTE)
    return tuple(row.word for row in CURATED_COLOR_WORD_PALETTE if int(row.roll_weight) > 0)


def imported_color_words() -> tuple[str, ...]:
    return tuple(row.word for row in IMPORTED_COLOR_WORD_PALETTE)


def approved_color_words(*, include_reserved: bool = True, include_imported: bool = True) -> tuple[str, ...]:
    rows = COLOR_WORD_PALETTE if include_imported else CURATED_COLOR_WORD_PALETTE
    if include_reserved:
        return tuple(row.word for row in rows)
    return tuple(row.word for row in rows if int(row.roll_weight) > 0)


def color_word_row(word: object) -> ColorWordRow | None:
    return _ROWS_BY_WORD.get(normalize_color_word(word))


def color_word_rgb(word: object, fallback: tuple[int, int, int] | None = None) -> tuple[int, int, int] | None:
    row = color_word_row(word)
    if row:
        return row.pygame_rgb
    return fallback


def color_word_tags(word: object) -> tuple[str, ...]:
    row = color_word_row(word)
    return row.tags if row else ()


def color_word_display_name(word: object, default: str = "") -> str:
    normalized = normalize_color_word(word, default=default)
    if not normalized:
        normalized = _clean_word(default) or _clean_word(word)
    return normalized.replace("_", " ")


def clothing_render_key_for_color_word(word: object, default: str | None = None) -> str | None:
    normalized = normalize_color_word(word)
    return f"clothing_{normalized}" if normalized else default


def flora_render_key_for_color_word(
    word: object,
    *,
    growth_form: str | None = None,
    fallback: str | None = None,
) -> str | None:
    normalized = normalize_color_word(word)
    if not normalized:
        return fallback
    form = str(growth_form or "").strip().lower()
    tags = set(color_word_tags(normalized))
    if form in {"moss", "lichen"} and {"green", "earth", "neutral"} & tags:
        return "flora_moss"
    if form == "vine" and {"green", "earth"} & tags:
        return "flora_vine"
    if form in {"grass", "reed"} and {"green", "earth", "neutral"} & tags:
        return "flora_reed" if form == "reed" else "flora_grass"
    if form in {"shrub", "fern"} and {"green", "earth", "neutral"} & tags:
        return "flora_shrub"
    if normalized in _FLORA_FLOWER_COLOR_KEYS:
        return _FLORA_FLOWER_COLOR_KEYS[normalized]
    if {"pink", "rose"} & tags:
        return "flora_flower_pink"
    if {"purple", "violet", "magenta"} & tags:
        return "flora_flower_violet"
    if {"blue", "cyan", "aqua", "teal"} & tags:
        return "flora_flower_blue"
    if {"yellow", "gold"} & tags:
        return "flora_flower_gold"
    if {"red", "orange", "coral"} & tags:
        return "flora_flower_coral"
    if {"black", "dark"} & tags:
        return "flora_flower_violet"
    if {"white", "gray", "neutral", "silver"} & tags:
        return "flora_flower_white"
    if {"green", "earth", "brown"} & tags:
        return "flora_leaf"
    return fallback


def world_object_render_key_for_color_word(word: object, default: str | None = None) -> str | None:
    normalized = normalize_color_word(word)
    if not normalized:
        return default
    if normalized in _WORLD_OBJECT_COLOR_KEYS:
        return _WORLD_OBJECT_COLOR_KEYS[normalized]
    tags = set(color_word_tags(normalized))
    if {"pink", "rose"} & tags:
        return "world_object_pink"
    if {"purple", "violet", "magenta"} & tags:
        return "world_object_purple"
    if {"blue", "cyan", "aqua", "teal"} & tags:
        return "world_object_blue"
    if {"green"} & tags:
        return "world_object_green"
    if {"red"} & tags:
        return "world_object_red"
    if {"orange", "coral"} & tags:
        return "world_object_coral"
    if {"yellow", "gold", "brown", "tan", "earth"} & tags:
        return "world_object_gold"
    if {"black", "dark"} & tags:
        return "world_object_charcoal"
    if {"silver", "gray"} & tags:
        return "world_object_silver"
    if {"white", "neutral"} & tags:
        return "world_object_white"
    return default


def casino_color_word(value: object) -> str:
    normalized = normalize_color_word(value)
    if normalized == "total_black":
        normalized = "black"
    if normalized == "yellow":
        normalized = "gold"
    elif normalized in {"silver", "cream", "ivory"}:
        normalized = "white"
    elif normalized == "gray":
        normalized = "charcoal"
    return normalized if normalized in CASINO_COLOR_WORDS else ""


def render_key_for_color_word(
    word: object,
    *,
    domain: str = "clothing",
    growth_form: str | None = None,
    default: str | None = None,
) -> str | None:
    domain_key = str(domain or "clothing").strip().lower()
    if domain_key in {"clothing", "appearance", "cosmetic"}:
        return clothing_render_key_for_color_word(word, default=default)
    if domain_key == "flora":
        return flora_render_key_for_color_word(word, growth_form=growth_form, fallback=default)
    if domain_key in {"world_object", "object"}:
        return world_object_render_key_for_color_word(word, default=default)
    if domain_key in {"casino", "table"}:
        return casino_color_word(word) or default
    normalized = normalize_color_word(word)
    return normalized or default


def _rgb_distance_sq(a: tuple[int, int, int], b: tuple[int, int, int]) -> int:
    return sum((int(left) - int(right)) ** 2 for left, right in zip(a, b))


def find_nearest_color_word(
    value: object,
    *,
    include_reserved: bool = True,
    include_imported: bool = True,
    default: str = "",
) -> str:
    rgb = parse_color_value(value)
    if rgb is None:
        return normalize_color_word(value, default=default) or default
    candidates = approved_color_words(include_reserved=include_reserved, include_imported=include_imported)
    if not candidates:
        return default
    best_word = default
    best_distance: int | None = None
    for word in candidates:
        candidate_rgb = color_word_rgb(word)
        if candidate_rgb is None:
            continue
        distance = _rgb_distance_sq(rgb, candidate_rgb)
        if best_distance is None or distance < best_distance:
            best_word = word
            best_distance = distance
            if distance == 0:
                break
    return best_word


nearest_color_word = find_nearest_color_word


def choose_color_word(rng, *, slots=(), include_reserved: bool = False) -> str:
    slot_tokens = {
        str(slot or "").strip().lower()
        for slot in tuple(slots or ())
        if str(slot or "").strip()
    }
    weighted: list[tuple[str, int]] = []
    for row in COLOR_WORD_PALETTE:
        if not include_reserved and int(row.roll_weight) <= 0:
            continue
        weight = max(0, int(row.roll_weight))
        if slot_tokens:
            bias = dict(row.slot_bias)
            weight += sum(max(0, int(bias.get(slot, 0))) for slot in slot_tokens)
        if weight > 0:
            weighted.append((row.word, weight))
    if not weighted:
        return COLOR_WORD_PALETTE[0].word
    total = sum(weight for _word, weight in weighted)
    roll = rng.uniform(0, total)
    cursor = 0.0
    for word, weight in weighted:
        cursor += weight
        if roll <= cursor:
            return word
    return weighted[-1][0]
