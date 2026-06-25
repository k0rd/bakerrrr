"""Runtime helpers for safe modal UI themes.

Themes are deliberately semantic: they select existing render color keys for a
small set of roles. They do not define layout, fonts, raw RGB values, or input
behavior.
"""

from __future__ import annotations

import copy
import hashlib
import random
from dataclasses import dataclass

from game.appearance_palette import APPEARANCE_PALETTE
from game.components import Position
from game.symbolic_palette import SYMBOLIC_PALETTE
from game.world_palette import WORLD_PALETTE


UI_THEME_ROLES = (
    "surface",
    "surface_alt",
    "border",
    "accent",
    "title",
    "body",
    "muted",
    "divider",
    "selection",
    "warning",
    "footer",
)

UI_THEME_ALLOWED_SELECTORS = (
    "area_types",
    "district_types",
    "context_tags",
)

DEFAULT_THEME_TOKENS = {
    "surface": "building_fill_dark",
    "surface_alt": "building_fill",
    "border": "building_edge",
    "accent": "player",
    "title": "objective",
    "body": "default",
    "muted": "human_slate",
    "divider": "building_edge",
    "selection": "player",
    "warning": "survival_meter_low",
    "footer": "human_slate",
}


@dataclass(frozen=True)
class BuiltinUITheme:
    theme_id: str
    label: str
    tokens: dict[str, str]
    area_types: tuple[str, ...] = ()
    district_types: tuple[str, ...] = ()
    context_tags: tuple[str, ...] = ()


def _theme(theme_id, label, tokens, *, area_types=(), district_types=(), context_tags=()):
    merged = dict(DEFAULT_THEME_TOKENS)
    merged.update({str(k): str(v) for k, v in dict(tokens or {}).items()})
    return BuiltinUITheme(
        theme_id=str(theme_id),
        label=str(label),
        tokens=merged,
        area_types=tuple(str(value).strip().lower() for value in area_types if str(value).strip()),
        district_types=tuple(str(value).strip().lower() for value in district_types if str(value).strip()),
        context_tags=tuple(str(value).strip().lower() for value in context_tags if str(value).strip()),
    )


BUILTIN_UI_THEMES = (
    _theme("city_default", "City Glass", {}),
    _theme(
        "downtown",
        "Downtown Glass",
        {
            "surface": "floor_downtown",
            "surface_alt": "building_fill_gray_b",
            "border": "building_edge_gray_b",
            "accent": "flora_flower_blue",
            "title": "player",
            "muted": "human_slate",
            "divider": "floor_downtown",
            "footer": "human_denim",
        },
        district_types=("downtown",),
    ),
    _theme(
        "corporate",
        "Corporate Blue",
        {
            "surface": "floor_corporate",
            "surface_alt": "building_fill_painted",
            "border": "building_edge_painted",
            "accent": "vehicle_glass",
            "title": "player",
            "divider": "vehicle_glass",
            "footer": "human_slate",
        },
        district_types=("corporate",),
    ),
    _theme(
        "industrial",
        "Industrial Steel",
        {
            "surface": "floor_industrial",
            "surface_alt": "building_fill_gray_c",
            "border": "building_edge_dark",
            "accent": "item_metal",
            "title": "human_accent",
            "muted": "human_charcoal",
            "divider": "building_edge_gray_c",
            "footer": "human_charcoal",
        },
        district_types=("industrial",),
    ),
    _theme(
        "residential",
        "Residential Warmth",
        {
            "surface": "floor_residential",
            "surface_alt": "building_fill_plaster",
            "border": "building_edge_plaster",
            "accent": "flora_flower_white",
            "title": "human_accent",
            "muted": "human_rust",
            "divider": "building_edge_plaster",
            "footer": "human_rust",
        },
        district_types=("residential",),
    ),
    _theme(
        "slums",
        "Low Row Neon",
        {
            "surface": "floor_slums",
            "surface_alt": "building_fill_brick",
            "border": "building_edge_brick",
            "accent": "flora_flower_violet",
            "title": "human_wine",
            "muted": "human_rust",
            "divider": "building_edge_brick",
            "footer": "human_wine",
        },
        district_types=("slums",),
    ),
    _theme(
        "entertainment",
        "Night Sign",
        {
            "surface": "floor_entertainment",
            "surface_alt": "building_roof_entertainment",
            "border": "casino_gold",
            "accent": "casino_chip",
            "title": "casino_gold",
            "muted": "human_wine",
            "divider": "casino_red",
            "selection": "casino_cursor",
            "footer": "casino_gold",
        },
        district_types=("entertainment",),
    ),
    _theme(
        "secure",
        "Secure Green",
        {
            "surface": "floor_military",
            "surface_alt": "building_roof_secure",
            "border": "guard",
            "accent": "actor_role_accent",
            "title": "guard",
            "muted": "human_olive",
            "divider": "building_roof_secure",
            "footer": "human_olive",
        },
        district_types=("military",),
        context_tags=("secure",),
    ),
    _theme(
        "frontier",
        "Frontier Dust",
        {
            "surface": "floor_frontier",
            "surface_alt": "terrain_trail",
            "border": "terrain_road",
            "accent": "flora_flower_gold",
            "title": "human_rust",
            "muted": "human_olive",
            "divider": "terrain_trail",
            "footer": "human_rust",
        },
        area_types=("frontier",),
    ),
    _theme(
        "wilderness",
        "Wilderness Green",
        {
            "surface": "floor_wilderness",
            "surface_alt": "terrain_brush",
            "border": "flora_vine",
            "accent": "flora_flower_pink",
            "title": "flora_flower_white",
            "muted": "human_olive",
            "divider": "flora_moss",
            "footer": "flora_leaf",
        },
        area_types=("wilderness",),
    ),
    _theme(
        "coastal",
        "Coastal Blue",
        {
            "surface": "floor_coastal",
            "surface_alt": "terrain_water",
            "border": "terrain_water",
            "accent": "flora_flower_coral",
            "title": "vehicle_glass",
            "muted": "human_denim",
            "divider": "terrain_salt",
            "footer": "human_denim",
        },
        area_types=("coastal",),
    ),
    _theme(
        "underground",
        "Underground Service",
        {
            "surface": "building_fill_dark",
            "surface_alt": "terrain_block",
            "border": "building_edge_dark",
            "accent": "transit",
            "title": "item_metal",
            "muted": "human_charcoal",
            "divider": "building_edge_gray_c",
            "footer": "human_charcoal",
        },
        context_tags=("underground", "service"),
    ),
)


def _clean_token(value):
    return str(value or "").strip().lower()


def available_ui_theme_render_keys() -> tuple[str, ...]:
    keys = {"default"}
    keys.update(row.render_key for row in APPEARANCE_PALETTE)
    keys.update(row.key for row in SYMBOLIC_PALETTE)
    keys.update(row.key for row in WORLD_PALETTE)
    return tuple(sorted(keys))


def builtin_ui_theme_ids() -> tuple[str, ...]:
    return tuple(theme.theme_id for theme in BUILTIN_UI_THEMES)


def _hash_unit(text):
    digest = hashlib.sha256(str(text).encode("utf-8")).hexdigest()
    return int(digest[:16], 16) / float(0xFFFFFFFFFFFFFFFF)


def _sim_seed(sim):
    for attr in ("seed", "world_seed"):
        value = getattr(sim, attr, None)
        if value is not None:
            return value
    world = getattr(sim, "world", None)
    if world is not None:
        return getattr(world, "seed", 0)
    return 0


def ui_theme_context(sim) -> dict[str, object]:
    area_type = "city"
    district_type = "unknown"
    terrain = ""
    chunk_coord = getattr(sim, "active_chunk_coord", None)
    chunk = None
    z = 0

    try:
        player_eid = getattr(sim, "player_eid", None)
        positions = sim.ecs.get(Position)
        pos = positions.get(player_eid) if player_eid is not None else None
    except Exception:
        pos = None

    if pos is not None:
        z = int(getattr(pos, "z", 0) or 0)
        chunk_size = int(max(1, getattr(sim, "chunk_size", 16) or 16))
        cx = int(getattr(pos, "x", 0) or 0) // chunk_size
        cy = int(getattr(pos, "y", 0) or 0) // chunk_size
        chunk_coord = (cx, cy)
        active_coord = getattr(sim, "active_chunk_coord", None)
        active_chunk = getattr(sim, "active_chunk", None)
        if active_coord == (cx, cy) and isinstance(active_chunk, dict):
            chunk = active_chunk
        world = getattr(sim, "world", None)
        if not isinstance(chunk, dict) and world is not None:
            try:
                loaded = getattr(world, "loaded_chunks", {})
                chunk = loaded.get((cx, cy)) if isinstance(loaded, dict) else None
                if not isinstance(chunk, dict):
                    chunk = world.get_chunk(cx, cy)
            except Exception:
                chunk = None

    if not isinstance(chunk, dict):
        chunk = getattr(sim, "active_chunk", {})
    if not isinstance(chunk, dict):
        chunk = {}
    district = chunk.get("district", {})
    if not isinstance(district, dict):
        district = {}
    area_type = _clean_token(district.get("area_type", area_type)) or area_type
    district_type = _clean_token(district.get("district_type", district_type)) or district_type
    terrain = _clean_token(district.get("terrain", chunk.get("terrain", ""))) or ""

    tags = {area_type, district_type}
    if terrain:
        tags.add(terrain)
    if z < 0:
        tags.add("underground")
    if district_type in {"military", "corporate"}:
        tags.add("secure")
    for key in ("site_kind", "site_kinds", "features"):
        value = district.get(key, chunk.get(key))
        if isinstance(value, str) and value.strip():
            tags.add(_clean_token(value))
        elif isinstance(value, (list, tuple, set)):
            tags.update(_clean_token(item) for item in value if _clean_token(item))

    return {
        "area_type": area_type,
        "district_type": district_type,
        "terrain": terrain,
        "chunk": chunk_coord if isinstance(chunk_coord, tuple) else None,
        "z": z,
        "tags": tuple(sorted(tag for tag in tags if tag)),
    }


def _theme_matches(theme, context):
    area_type = str(context.get("area_type", "")).strip().lower()
    district_type = str(context.get("district_type", "")).strip().lower()
    tags = set(context.get("tags", ()) or ())
    area_types = tuple(theme.get("area_types", ()) if isinstance(theme, dict) else theme.area_types)
    district_types = tuple(theme.get("district_types", ()) if isinstance(theme, dict) else theme.district_types)
    context_tags = tuple(theme.get("context_tags", ()) if isinstance(theme, dict) else theme.context_tags)
    if area_types and area_type not in set(area_types):
        return False
    if district_types and district_type not in set(district_types):
        return False
    if context_tags and not (set(context_tags) & tags):
        return False
    return True


def _theme_score(theme, context):
    score = 0
    area_type = str(context.get("area_type", "")).strip().lower()
    district_type = str(context.get("district_type", "")).strip().lower()
    tags = set(context.get("tags", ()) or ())
    area_types = tuple(theme.get("area_types", ()) if isinstance(theme, dict) else theme.area_types)
    district_types = tuple(theme.get("district_types", ()) if isinstance(theme, dict) else theme.district_types)
    context_tags = tuple(theme.get("context_tags", ()) if isinstance(theme, dict) else theme.context_tags)
    if area_type in set(area_types):
        score += 5
    if district_type in set(district_types):
        score += 3
    score += 4 * len(set(context_tags) & tags)
    return score


def _builtin_theme_for_context(context):
    matches = [theme for theme in BUILTIN_UI_THEMES if _theme_matches(theme, context)]
    if not matches:
        return BUILTIN_UI_THEMES[0]
    return sorted(matches, key=lambda theme: (_theme_score(theme, context), theme.theme_id), reverse=True)[0]


def _custom_theme_candidates(sim, context):
    themes = getattr(sim, "custom_ui_themes", {}) if sim is not None else {}
    if not isinstance(themes, dict):
        return []
    return [
        theme
        for theme in themes.values()
        if isinstance(theme, dict) and _theme_matches(theme, context)
    ]


def _select_custom_theme(sim, context):
    candidates = _custom_theme_candidates(sim, context)
    if not candidates:
        return None
    seed = _sim_seed(sim)
    chunk = context.get("chunk") or (0, 0)
    token = f"{seed}:ui_theme:{context.get('area_type')}:{context.get('district_type')}:{context.get('terrain')}:{chunk}"
    total = sum(max(0.01, float(theme.get("selection_weight", 1.0) or 1.0)) for theme in candidates)
    roll = _hash_unit(token) * total
    cursor = 0.0
    for theme in sorted(candidates, key=lambda row: str(row.get("id", ""))):
        cursor += max(0.01, float(theme.get("selection_weight", 1.0) or 1.0))
        if roll <= cursor:
            return theme
    return candidates[-1]


def resolve_modal_theme(sim=None, kind="modal") -> dict[str, object]:
    context = ui_theme_context(sim)
    builtin = _builtin_theme_for_context(context)
    tokens = dict(builtin.tokens)
    theme_id = builtin.theme_id
    label = builtin.label
    source = "built_in"

    custom = _select_custom_theme(sim, context)
    if isinstance(custom, dict):
        custom_tokens = custom.get("tokens", {})
        if isinstance(custom_tokens, dict):
            tokens.update({role: value for role, value in custom_tokens.items() if role in UI_THEME_ROLES})
        theme_id = str(custom.get("id", theme_id) or theme_id)
        label = str(custom.get("label", label) or label)
        source = "custom"

    return {
        "id": theme_id,
        "kind": str(kind or "modal"),
        "label": label,
        "source": source,
        "tokens": tokens,
        "context": context,
    }


def theme_token(theme, role, fallback="default") -> str:
    role = str(role or "").strip().lower()
    tokens = theme.get("tokens", {}) if isinstance(theme, dict) else {}
    value = tokens.get(role) if isinstance(tokens, dict) else None
    value = str(value or "").strip()
    return value or str(fallback or "default")


def theme_tokens(theme) -> dict[str, str]:
    tokens = theme.get("tokens", {}) if isinstance(theme, dict) else {}
    clean = dict(DEFAULT_THEME_TOKENS)
    if isinstance(tokens, dict):
        clean.update({role: str(tokens.get(role) or clean[role]) for role in UI_THEME_ROLES})
    return clean


def draw_modal_frame(view, panel_x, panel_y, panel_w, panel_h, *, theme=None, use_theme=True):
    if panel_w < 2 or panel_h < 2:
        return
    themed = bool(use_theme and getattr(view, "pygame", None) is not None and isinstance(theme, dict))
    if themed:
        top_color = theme_token(theme, "border", "building_edge")
        mid_color = theme_token(theme, "surface", "building_fill_dark")
        bot_color = top_color
    else:
        top_color = None
        mid_color = None
        bot_color = None
    top = "+" + ("-" * (panel_w - 2)) + "+"
    mid = "|" + (" " * (panel_w - 2)) + "|"
    bot = "+" + ("-" * (panel_w - 2)) + "+"
    view.draw_text(panel_x, panel_y, top, color=top_color)
    for row in range(1, panel_h - 1):
        view.draw_text(panel_x, panel_y + row, mid, color=mid_color)
    view.draw_text(panel_x, panel_y + panel_h - 1, bot, color=bot_color)


def copy_custom_ui_themes(themes) -> dict[str, dict]:
    if not isinstance(themes, dict):
        return {}
    return copy.deepcopy(themes)
