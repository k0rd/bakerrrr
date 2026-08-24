"""Runtime helpers for lightweight visual flora patches.

Flora is nonblocking world presence. The catalog carries future hooks so later
systems can add breeding, medicine, food, fiber, or creeping growth without
reauthoring plants.
"""

from __future__ import annotations

import json
import math
import random
from functools import lru_cache
from pathlib import Path

from engine.events import Event
from game.content_warnings import warn_content_fallback
from game.flora_genetics import (
    fungal_mutation_glow_color,
    normalize_flora_genetics,
    preroll_fungal_mutation_glow,
)
from game.json_metadata import split_object_document


FLORA_PATH = Path(__file__).resolve().parent / "flora.json"

VALID_GROWTH_FORMS = frozenset(("flower", "grass", "reed", "moss", "lichen", "vine", "shrub", "fern", "fungus"))
VALID_GLYPHS = frozenset((",", "'", ";", "*"))
RARITY_BASE_WEIGHTS = {
    "common": 12.0,
    "uncommon": 5.0,
    "rare": 1.4,
}
DEFAULT_START_HOUR = 9
DEFAULT_TICKS_PER_HOUR = 600

DEFAULT_GLYPH_BY_FORM = {
    "flower": "'",
    "grass": ",",
    "reed": ",",
    "moss": ",",
    "lichen": ",",
    "vine": ";",
    "shrub": "*",
    "fern": ",",
    "fungus": "*",
}

DEFAULT_RENDER_KEY_BY_FORM = {
    "flower": "flora_flower_pink",
    "grass": "flora_grass",
    "reed": "flora_reed",
    "moss": "flora_moss",
    "lichen": "flora_moss",
    "vine": "flora_vine",
    "shrub": "flora_shrub",
    "fern": "flora_shrub",
    "fungus": "flora_flower_white",
}

CITY_DISTRICTS = frozenset(("downtown", "corporate", "residential", "entertainment", "industrial", "slums", "military"))
CITY_FLORA_DISTRICT_BIAS = {
    "residential": 1.25,
    "entertainment": 1.1,
    "corporate": 0.75,
    "downtown": 0.7,
    "slums": 0.85,
    "industrial": 0.55,
    "military": 0.35,
}
AREA_DENSITY = {
    "city": (2, 4),
    "wilderness": (5, 9),
    "frontier": (4, 7),
    "coastal": (5, 8),
}
NO_FLORA_GLYPHS = frozenset(("=", ":", "+", "'", '"', "/", "#", "~", "^", ">", "<", "|"))
SPREAD_STATES_BY_FORM = {
    "moss": ("rooted", "creeping"),
    "lichen": ("rooted", "creeping"),
    "vine": ("rooted", "trailing"),
    "flower": ("flowering", "flowering"),
    "grass": ("rooted", "rooted"),
    "reed": ("rooted", "rooted"),
    "shrub": ("rooted", "rooted"),
    "fern": ("rooted", "rooted"),
    "fungus": ("rooted", "rooted"),
}
DEFAULT_HARVEST_LIMIT_BY_FORM = {
    "flower": 1,
    "grass": 1,
    "reed": 2,
    "moss": 2,
    "lichen": 2,
    "vine": 2,
    "shrub": 2,
    "fern": 2,
    "fungus": 1,
}
PARTIAL_HARVEST_STAGE_BY_FORM = {
    "reed": "clipped",
    "moss": "scraped",
    "lichen": "scraped",
    "vine": "clipped",
    "shrub": "clipped",
    "fern": "clipped",
}
EXHAUSTED_FLORA_STAGES = frozenset(("picked", "picked_over", "spent", "exhausted", "fruitless"))
IMMATURE_FLORA_STAGES = frozenset(("seeded", "sprouting", "young"))
FAILED_FLORA_STAGES = frozenset(("withering", "failed"))
NIGHT_BLOOM_TAGS = frozenset(("night_bloom", "night_blooming", "moon", "lantern"))
FLORA_REGROWTH_HOURS_BY_FORM = {
    "grass": 6,
    "moss": 8,
    "reed": 10,
    "vine": 12,
    "fern": 14,
    "flower": 18,
    "shrub": 24,
    "lichen": 30,
    "fungus": 16,
}
FLORA_REGROWTH_RARITY_MULTIPLIER = {
    "common": 1.0,
    "uncommon": 1.5,
    "rare": 2.5,
}
FLORA_FIRE_INTEGRITY_BY_FORM = {
    "flower": 3,
    "grass": 4,
    "reed": 5,
    "moss": 2,
    "lichen": 3,
    "vine": 6,
    "shrub": 8,
    "fern": 5,
    "fungus": 2,
}


def _str_key(value, fallback=""):
    text = str(value if value is not None else "").strip().lower()
    return text or str(fallback or "").strip().lower()


def _normalize_weight_map(value):
    if not isinstance(value, dict):
        return {}
    rows = {}
    for key, raw_weight in value.items():
        label = _str_key(key)
        if not label:
            continue
        try:
            weight = float(raw_weight)
        except (TypeError, ValueError):
            continue
        if weight <= 0:
            continue
        rows[label] = weight
    return rows


def _normalize_string_tuple(value):
    if isinstance(value, str):
        values = (value,)
    elif isinstance(value, (list, tuple, set)):
        values = tuple(value)
    else:
        values = ()
    rows = []
    seen = set()
    for raw in values:
        text = _str_key(raw)
        if text and text not in seen:
            rows.append(text)
            seen.add(text)
    return tuple(rows)


def _normalize_dict(value):
    return dict(value) if isinstance(value, dict) else {}


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def flora_world_hour(sim):
    world_traits = getattr(sim, "world_traits", {}) if sim is not None else {}
    clock = world_traits.get("clock", {}) if isinstance(world_traits, dict) else {}
    if not isinstance(clock, dict):
        clock = {}
    start_hour = _safe_int(clock.get("start_hour"), DEFAULT_START_HOUR)
    ticks_per_hour = max(60, _safe_int(clock.get("ticks_per_hour"), DEFAULT_TICKS_PER_HOUR))
    return (start_hour + (_safe_int(getattr(sim, "tick", 0), 0) // ticks_per_hour)) % 24


def flora_day_phase(sim):
    hour = int(flora_world_hour(sim)) % 24
    if 5 <= hour < 7:
        return "dawn"
    if 7 <= hour < 18:
        return "day"
    if 18 <= hour < 20:
        return "dusk"
    return "night"


def _normalize_hour_window(value):
    if isinstance(value, dict):
        value = (value.get("start"), value.get("end"))
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        start = max(0, min(23, _safe_int(value[0], 0)))
        end = max(0, min(23, _safe_int(value[1], 0)))
        return (start, end)
    return None


def _hour_in_window(hour, window):
    if not isinstance(window, tuple) or len(window) != 2:
        return True
    start, end = int(window[0]) % 24, int(window[1]) % 24
    hour = int(hour) % 24
    if start == end:
        return True
    if start < end:
        return start <= hour < end
    return hour >= start or hour < end


def _catalog_row_for_record(record):
    if not isinstance(record, dict):
        return {}
    plant_id = _str_key(record.get("plant_id"))
    if not plant_id:
        return {}
    return load_flora_catalog().get(plant_id, {}) or {}


def _record_traits(record):
    row = _catalog_row_for_record(record)
    traits = {}
    for source in (row.get("growth_traits"), record.get("growth_traits")):
        if isinstance(source, dict):
            traits.update(source)
    return traits


def _record_harvest_potential(record):
    row = _catalog_row_for_record(record)
    potential = {}
    for source in (row.get("harvest_potential"), record.get("harvest_potential")):
        if isinstance(source, dict):
            potential.update(source)
    return potential


def _record_tags(record):
    row = _catalog_row_for_record(record)
    tags = set(_normalize_string_tuple(row.get("tags")))
    tags.update(_normalize_string_tuple(record.get("tags")))
    return tags


def _normalize_flora_row(plant_id, raw):
    if not isinstance(raw, dict):
        return None
    plant_key = _str_key(raw.get("id") or plant_id)
    if not plant_key:
        return None
    growth_form = _str_key(raw.get("growth_form"), "flower")
    if growth_form not in VALID_GROWTH_FORMS:
        growth_form = "flower"
    glyph = str(raw.get("glyph") or DEFAULT_GLYPH_BY_FORM[growth_form])[:1]
    if glyph not in VALID_GLYPHS:
        glyph = DEFAULT_GLYPH_BY_FORM[growth_form]
    render_key = _str_key(raw.get("render_key"), DEFAULT_RENDER_KEY_BY_FORM[growth_form])
    colors = _normalize_string_tuple(raw.get("colors")) or (render_key,)
    rarity = _str_key(raw.get("rarity"), "common")
    if rarity not in RARITY_BASE_WEIGHTS:
        rarity = "common"
    tags = set(_normalize_string_tuple(raw.get("tags")))
    tags.add(growth_form)
    if growth_form in {"moss", "lichen", "vine"}:
        tags.add("spreading")
    row = {
        "id": plant_key,
        "name": str(raw.get("name") or plant_key.replace("_", " ")).strip() or plant_key.replace("_", " "),
        "growth_form": growth_form,
        "glyph": glyph,
        "render_key": render_key,
        "colors": tuple(colors),
        "rarity": rarity,
        "area_weights": _normalize_weight_map(raw.get("area_weights")),
        "terrain_weights": _normalize_weight_map(raw.get("terrain_weights")),
        "district_weights": _normalize_weight_map(raw.get("district_weights")),
        "tags": tuple(sorted(tags)),
        "growth_traits": _normalize_dict(raw.get("growth_traits")),
        "genetics": _normalize_dict(raw.get("genetics")),
        "harvest_potential": _normalize_dict(raw.get("harvest_potential")),
        "crossbreed_tags": _normalize_string_tuple(raw.get("crossbreed_tags")),
        "spread_profile": _normalize_dict(raw.get("spread_profile")),
        "wild_spawn": bool(raw.get("wild_spawn", True)),
        "cultivation_allowed": bool(raw.get("cultivation_allowed", True)),
        "crossbreed_allowed": bool(raw.get("crossbreed_allowed", True)),
        "herbal_pool_allowed": bool(raw.get("herbal_pool_allowed", True)),
    }
    row["genetics"] = normalize_flora_genetics(plant_key, row, seed=0)
    return row


@lru_cache(maxsize=4)
def load_flora_catalog(path=None):
    source = Path(path) if path else FLORA_PATH
    try:
        with source.open("r", encoding="utf-8") as fh:
            raw = json.load(fh)
        payload, _metadata = split_object_document(raw)
    except Exception as exc:
        warn_content_fallback(f"flora catalog could not be loaded from {source}: {exc}")
        payload = {}

    rows = {}
    if isinstance(payload, dict):
        for plant_id, row in payload.items():
            if str(plant_id).startswith("_"):
                continue
            normalized = _normalize_flora_row(plant_id, row)
            if normalized is None:
                continue
            rows[normalized["id"]] = normalized

    if not rows:
        warn_content_fallback("flora catalog had no valid rows; using one fallback grass row")
        rows["fallback_grass"] = _normalize_flora_row(
            "fallback_grass",
            {
                "name": "fallback grass",
                "growth_form": "grass",
                "glyph": ",",
                "render_key": "flora_grass",
                "colors": ["flora_grass"],
                "rarity": "common",
                "area_weights": {"wilderness": 1.0, "city": 0.5, "frontier": 1.0, "coastal": 1.0},
                "terrain_weights": {"terrain_brush": 1.0},
                "district_weights": {},
                "tags": ["grass"],
                "growth_traits": {},
                "genetics": {},
                "harvest_potential": {},
                "crossbreed_tags": [],
                "spread_profile": {},
            },
        )
    return rows


def ensure_flora_state(sim):
    if not isinstance(getattr(sim, "flora_patches", None), dict):
        sim.flora_patches = {}
    if not isinstance(getattr(sim, "chunk_flora_records", None), dict):
        sim.chunk_flora_records = {}
    return sim.flora_patches, sim.chunk_flora_records


def ensure_dynamic_flora_profiles(sim):
    if sim is None:
        return {}
    if not isinstance(getattr(sim, "dynamic_flora_profiles", None), dict):
        sim.dynamic_flora_profiles = {}
    return sim.dynamic_flora_profiles


def dynamic_flora_profile(sim, plant_id):
    if sim is None:
        return {}
    plant_id = _str_key(plant_id)
    if not plant_id:
        return {}
    profiles = ensure_dynamic_flora_profiles(sim)
    profile = profiles.get(plant_id)
    return dict(profile) if isinstance(profile, dict) else {}


def flora_catalog_for_sim(sim, *, native_only=False):
    """Return authored flora plus installation-native (or all live) lines."""

    catalog = {plant_id: dict(row) for plant_id, row in load_flora_catalog().items()}
    for plant_id, profile in ensure_dynamic_flora_profiles(sim).items():
        if not isinstance(profile, dict):
            continue
        if native_only and not str(profile.get("native_lineage_id") or "").strip():
            continue
        catalog[_str_key(plant_id)] = dict(profile)
    return catalog


def register_dynamic_flora_profile(sim, profile):
    if sim is None:
        return None
    if not isinstance(profile, dict):
        return None
    plant_id = _str_key(profile.get("plant_id") or profile.get("id"))
    if not plant_id:
        return None
    is_dynamic = (
        plant_id not in load_flora_catalog()
        or str(plant_id).startswith("hybrid_")
        or _safe_int(profile.get("hybrid_generation"), 0) > 0
        or bool(profile.get("dynamic_flora"))
    )
    if not is_dynamic:
        return None
    row = dict(profile)
    row["id"] = plant_id
    row["plant_id"] = plant_id
    row["name"] = str(row.get("name") or row.get("plant_name") or plant_id.replace("_", " ")).strip()
    row["plant_name"] = str(row.get("plant_name") or row["name"]).strip()
    row["growth_form"] = _str_key(row.get("growth_form"), "flower")
    row["glyph"] = str(row.get("glyph") or DEFAULT_GLYPH_BY_FORM.get(row["growth_form"], "'"))[:1]
    row["render_key"] = _str_key(row.get("render_key") or row.get("color_key"), DEFAULT_RENDER_KEY_BY_FORM.get(row["growth_form"], "flora_flower_pink"))
    row["color_key"] = _str_key(row.get("color_key") or row.get("render_key"), row["render_key"])
    row["color_word"] = _str_key(row.get("color_word"))
    row["colors"] = tuple(_normalize_string_tuple(row.get("colors")) or (row["color_key"],))
    row["tags"] = tuple(_normalize_string_tuple(row.get("tags")) or (row["growth_form"],))
    row["crossbreed_tags"] = tuple(_normalize_string_tuple(row.get("crossbreed_tags")))
    row["secondary_traits"] = tuple(_normalize_string_tuple(row.get("secondary_traits")))
    row["chemistry_class"] = _str_key(row.get("chemistry_class"))
    row["parent_chemistry_classes"] = tuple(_normalize_string_tuple(row.get("parent_chemistry_classes")))
    row["parent_plant_ids"] = tuple(_normalize_string_tuple(row.get("parent_plant_ids")))
    row["parent_line_name"] = str(row.get("parent_line_name") or "").strip()
    row["hybrid_generation"] = _safe_int(row.get("hybrid_generation"), 0)
    row["hybrid_signature"] = _str_key(row.get("hybrid_signature"))
    row["lineage"] = dict(row.get("lineage") or {}) if isinstance(row.get("lineage"), dict) else {}
    row["stability_band"] = _str_key(row.get("stability_band"))
    row["notability"] = _str_key(row.get("notability"))
    row["genetics"] = dict(row.get("genetics") or {}) if isinstance(row.get("genetics"), dict) else {}
    if _safe_int(row["genetics"].get("schema_version"), 0) != 1:
        row["genetics"] = normalize_flora_genetics(
            plant_id,
            row,
            seed=getattr(sim, "seed", 0),
        )
    row["dynamic_flora"] = True
    ensure_dynamic_flora_profiles(sim)[plant_id] = row
    return dict(row)


def _chunk_key_from_chunk(chunk):
    if not isinstance(chunk, dict):
        return None
    try:
        return (int(chunk.get("cx", 0)), int(chunk.get("cy", 0)))
    except (TypeError, ValueError):
        return None


def _chunk_area_context(sim, chunk):
    district = chunk.get("district") if isinstance(chunk, dict) and isinstance(chunk.get("district"), dict) else {}
    area_type = _str_key(
        (chunk.get("area_type") if isinstance(chunk, dict) else None) or district.get("area_type"),
        "wilderness",
    )
    district_type = _str_key(district.get("district_type") or (chunk.get("district") if isinstance(chunk, dict) else None), "")
    if area_type in CITY_DISTRICTS or district_type:
        area_key = "city"
    elif area_type in AREA_DENSITY:
        area_key = area_type
    else:
        area_key = "wilderness"
    if not district_type and area_key == "city":
        try:
            descriptor = sim.world.overworld_descriptor(int(chunk.get("cx", 0)), int(chunk.get("cy", 0)))
            district_type = _str_key(descriptor.get("district"), "residential")
        except Exception:
            district_type = "residential"
    return area_key, district_type


def _tile_color_key(tile):
    if tile is None:
        return ""
    return _str_key(getattr(tile, "color", ""))


def _tile_allows_flora(sim, x, y, z=0):
    tile = sim.tilemap.tile_at(int(x), int(y), int(z))
    if tile is None or not bool(getattr(tile, "walkable", True)):
        return False
    glyph = str(getattr(tile, "glyph", "") or "")[:1]
    color_key = _tile_color_key(tile)
    if glyph in NO_FLORA_GLYPHS:
        return False
    if color_key in {"terrain_road", "terrain_trail", "feature_door", "feature_window", "terrain_water", "terrain_rock"}:
        return False
    if hasattr(sim, "structure_at") and sim.structure_at(int(x), int(y), int(z)) is not None:
        return False
    if hasattr(sim, "property_covering") and sim.property_covering(int(x), int(y), int(z)):
        return False
    if hasattr(sim, "ground_items_at") and sim.ground_items_at(int(x), int(y), z=int(z)):
        return False
    try:
        if sim.tilemap.entities_at(int(x), int(y), int(z)):
            return False
    except Exception:
        pass
    return True


def _near_fixture_score(sim, x, y, z=0):
    best = 0.0
    for prop in getattr(sim, "properties", {}).values():
        if not isinstance(prop, dict):
            continue
        try:
            if int(prop.get("z", 0) or 0) != int(z):
                continue
            distance = abs(int(prop.get("x", 0) or 0) - int(x)) + abs(int(prop.get("y", 0) or 0) - int(y))
        except (TypeError, ValueError):
            continue
        if distance > 4:
            continue
        metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
        label = " ".join(
            str(metadata.get(key, "") or "").lower()
            for key in ("fixture_type", "archetype", "service_id", "label", "name")
        )
        if any(term in label for term in ("planter", "garden", "bench", "fountain", "market", "herbalist")):
            best = max(best, 2.6 if distance <= 2 else 1.4)
    return best


def _candidate_positions(sim, chunk):
    if not isinstance(chunk, dict):
        return []
    cx, cy = _chunk_key_from_chunk(chunk) or (0, 0)
    chunk_size = int(getattr(sim, "chunk_size", 16) or 16)
    min_x = cx * chunk_size
    min_y = cy * chunk_size
    max_x = min_x + chunk_size
    max_y = min_y + chunk_size
    area_key, district_type = _chunk_area_context(sim, chunk)
    candidates = []
    for y in range(min_y, max_y):
        for x in range(min_x, max_x):
            z = 0
            if not _tile_allows_flora(sim, x, y, z):
                continue
            tile = sim.tilemap.tile_at(x, y, z)
            color_key = _tile_color_key(tile)
            glyph = str(getattr(tile, "glyph", "") or "")[:1]
            score = 1.0
            if glyph == "," or color_key == "terrain_brush":
                score += 2.2
            if color_key.startswith("floor_"):
                score += 0.25
            if area_key == "city":
                score *= CITY_FLORA_DISTRICT_BIAS.get(district_type, 0.75)
                score += _near_fixture_score(sim, x, y, z)
            elif area_key == "wilderness":
                score += 2.0
            elif area_key == "coastal":
                score += 1.8 if color_key in {"floor_coastal", "terrain_salt"} else 0.9
            elif area_key == "frontier":
                score += 1.1
            if score <= 0:
                continue
            candidates.append((x, y, z, max(0.1, score), color_key))
    return candidates


def _weighted_choice(rng, rows):
    total = sum(max(0.0, float(weight)) for _value, weight in rows)
    if total <= 0:
        return rows[0][0] if rows else None
    roll = rng.random() * total
    running = 0.0
    for value, weight in rows:
        running += max(0.0, float(weight))
        if roll <= running:
            return value
    return rows[-1][0]


def _plant_weight_for_context(row, *, area_key, district_type, terrain_key):
    rarity = RARITY_BASE_WEIGHTS.get(row.get("rarity"), 1.0)
    area = row.get("area_weights", {}).get(area_key, 0.15)
    district = row.get("district_weights", {}).get(district_type, 1.0 if not district_type else 0.7)
    terrain = row.get("terrain_weights", {}).get(terrain_key, 0.8)
    if area_key != "city" and district_type:
        district = max(0.4, district)
    return max(0.0, rarity * area * district * terrain)


def _select_plant(catalog, rng, *, area_key, district_type, terrain_key):
    rows = []
    for row in catalog.values():
        if not bool(row.get("wild_spawn", True)):
            continue
        weight = _plant_weight_for_context(row, area_key=area_key, district_type=district_type, terrain_key=terrain_key)
        if weight > 0:
            rows.append((row, weight))
    return _weighted_choice(rng, rows) or next(iter(catalog.values()))


def _cluster_size_for_plant(row, rng, *, area_key):
    traits = row.get("growth_traits") if isinstance(row.get("growth_traits"), dict) else {}
    try:
        low = int(traits.get("cluster_min", 1) or 1)
        high = int(traits.get("cluster_max", low) or low)
    except (TypeError, ValueError):
        low = high = 1
    low = max(1, min(low, 8))
    high = max(low, min(high, 10))
    if area_key == "city":
        high = max(low, min(high, 3))
    return rng.randint(low, high)


def _cluster_neighbors(x, y):
    return (
        (x + 1, y, "east"),
        (x - 1, y, "west"),
        (x, y + 1, "south"),
        (x, y - 1, "north"),
        (x + 1, y + 1, "southeast"),
        (x - 1, y - 1, "northwest"),
        (x + 1, y - 1, "northeast"),
        (x - 1, y + 1, "southwest"),
    )


def _color_for_row(row, rng):
    colors = tuple(row.get("colors") or ())
    if not colors:
        return str(row.get("render_key") or DEFAULT_RENDER_KEY_BY_FORM.get(row.get("growth_form"), "flora_leaf"))
    return str(rng.choice(colors))


def _spread_state_for(row, index):
    form = row.get("growth_form", "flower")
    root_state, child_state = SPREAD_STATES_BY_FORM.get(form, ("rooted", "rooted"))
    return root_state if int(index or 0) == 0 else child_state


def _harvest_limit_for_form(form):
    return int(DEFAULT_HARVEST_LIMIT_BY_FORM.get(_str_key(form), 1))


def flora_harvest_limit(record):
    if not isinstance(record, dict):
        return 1
    configured = record.get("harvest_limit")
    if configured is None:
        harvest_potential = record.get("harvest_potential") if isinstance(record.get("harvest_potential"), dict) else {}
        configured = (
            harvest_potential.get("harvest_limit")
            or harvest_potential.get("max_harvests")
            or harvest_potential.get("uses")
            or harvest_potential.get("small_batch_uses")
        )
    default = _harvest_limit_for_form(record.get("growth_form"))
    limit = _safe_int(configured, default)
    if str(record.get("rarity", "")).strip().lower() == "rare":
        limit = min(limit, default)
    return max(1, min(limit, 4))


def normalize_flora_harvest_state(record):
    if not isinstance(record, dict):
        return {}
    row = dict(record)
    limit = flora_harvest_limit(row)
    stage = _str_key(row.get("stage"), "mature")
    count = max(0, _safe_int(row.get("harvest_count"), 0))
    if stage in FAILED_FLORA_STAGES:
        count = max(count, limit)
        remaining = 0
    elif stage in EXHAUSTED_FLORA_STAGES:
        count = max(count, limit)
        remaining = 0
    else:
        remaining = row.get("harvest_remaining")
        if remaining is None:
            remaining = max(0, limit - count)
        remaining = max(0, min(limit, _safe_int(remaining, limit)))
        if remaining <= 0:
            stage = "picked"
            count = max(count, limit)
    row["harvest_limit"] = int(limit)
    row["harvest_count"] = int(min(max(count, 0), limit))
    row["harvest_remaining"] = int(remaining)
    row["stage"] = stage or "mature"
    if int(remaining) <= 0 and stage not in FAILED_FLORA_STAGES:
        row["harvest_exhausted"] = True
        row.setdefault("exhaustion_kind", "picked_over")
    else:
        row["harvest_exhausted"] = False
    return row


def flora_patch_harvestable(record):
    if not isinstance(record, dict):
        return False
    if bool(record.get("harvest_locked")):
        return False
    row = normalize_flora_harvest_state(record)
    stage = _str_key(row.get("stage"))
    if stage in EXHAUSTED_FLORA_STAGES or stage in IMMATURE_FLORA_STAGES or stage in FAILED_FLORA_STAGES:
        return False
    return _safe_int(row.get("harvest_remaining"), 0) > 0


def flora_harvest_remaining(record):
    if not isinstance(record, dict):
        return 0
    return max(0, _safe_int(normalize_flora_harvest_state(record).get("harvest_remaining"), 0))


def flora_bloom_profile(record):
    if not isinstance(record, dict):
        record = {}
    form = _str_key(record.get("growth_form"), "flower")
    traits = _record_traits(record)
    harvest_potential = _record_harvest_potential(record)
    tags = _record_tags(record)
    night_bloom = bool(traits.get("night_bloom") or harvest_potential.get("night_bloom") or (tags & NIGHT_BLOOM_TAGS))
    bloom_hours = (
        _normalize_hour_window(record.get("bloom_hours"))
        or _normalize_hour_window(traits.get("bloom_hours"))
        or _normalize_hour_window(harvest_potential.get("bloom_hours"))
    )
    if bloom_hours is None:
        if night_bloom:
            bloom_hours = (20, 5)
        elif form == "vine" and "morning" in tags:
            bloom_hours = (5, 11)
        elif form == "flower" or "flowering" in tags:
            bloom_hours = (6, 19)
    closed_yield_factor = _safe_float(
        record.get("closed_yield_factor")
        if record.get("closed_yield_factor") is not None
        else traits.get("closed_yield_factor", harvest_potential.get("closed_yield_factor", 0.55)),
        0.55,
    )
    harvest_phase_bonus = _safe_float(
        record.get("harvest_phase_bonus")
        if record.get("harvest_phase_bonus") is not None
        else traits.get("harvest_phase_bonus", harvest_potential.get("harvest_phase_bonus", 0.0)),
        0.0,
    )
    return {
        "growth_form": form,
        "bloom_hours": bloom_hours,
        "night_bloom": bool(night_bloom),
        "closed_yield_factor": max(0.15, min(1.0, closed_yield_factor)),
        "harvest_phase_bonus": max(0.0, min(2.0, harvest_phase_bonus)),
        "tags": tuple(sorted(tags)),
    }


def flora_bloom_state(sim, record):
    if not isinstance(record, dict):
        return "dormant"
    row = normalize_flora_harvest_state(record)
    stage = _str_key(row.get("stage"))
    if stage in EXHAUSTED_FLORA_STAGES or stage in IMMATURE_FLORA_STAGES or stage in FAILED_FLORA_STAGES or _safe_int(row.get("harvest_remaining"), 0) <= 0:
        return "dormant"
    profile = flora_bloom_profile(row)
    form = profile.get("growth_form", "flower")
    tags = set(profile.get("tags") or ())
    window = profile.get("bloom_hours")
    flowering = form == "flower" or "flowering" in tags or bool(profile.get("night_bloom"))
    if not flowering:
        return "open"
    if _hour_in_window(flora_world_hour(sim), window):
        return "night_open" if profile.get("night_bloom") else "open"
    return "closed"


def flora_harvest_context(sim, record):
    row = normalize_flora_harvest_state(record if isinstance(record, dict) else {})
    form = _str_key(row.get("growth_form"), "flower")
    state = flora_bloom_state(sim, row)
    phase = flora_day_phase(sim)
    profile = flora_bloom_profile(row)
    yield_factor = 1.0
    unit_bonus = 0
    quality_hint = ""
    if form == "flower":
        if state == "closed":
            plant_part = "closed_bud"
            yield_factor = float(profile.get("closed_yield_factor", 0.55) or 0.55)
            quality_hint = "closed"
        elif state == "night_open":
            plant_part = "night_blossom"
            unit_bonus = 1 if str(row.get("rarity", "")).strip().lower() == "rare" else 0
            quality_hint = "night_bloom"
        else:
            plant_part = "open_blossom"
            if phase in {"dawn", "dusk"}:
                quality_hint = phase
    elif form in {"moss", "lichen"} and phase in {"dawn", "night"}:
        plant_part = f"damp_{form}"
        unit_bonus = 1 if float(profile.get("harvest_phase_bonus", 0.0) or 0.0) >= 1.0 else 0
        quality_hint = "damp"
    elif form == "vine" and state == "night_open":
        plant_part = "night_cutting"
        unit_bonus = 1 if float(profile.get("harvest_phase_bonus", 0.0) or 0.0) >= 1.0 else 0
        quality_hint = "night_bloom"
    else:
        plant_part = {
            "grass": "leaf",
            "reed": "reed_cutting",
            "shrub": "leaf_cutting",
            "fern": "fern_frond",
            "vine": "vine_cutting",
            "moss": "moss_scraping",
            "lichen": "lichen_scraping",
        }.get(form, "plant_material")
    return {
        "day_phase": phase,
        "harvest_hour": int(flora_world_hour(sim)) % 24,
        "bloom_state": state,
        "plant_part": plant_part,
        "yield_factor": float(yield_factor),
        "unit_bonus": int(unit_bonus),
        "quality_hint": quality_hint,
    }


def flora_harvest_updates_after_pick(record, *, eid=None, tick=0, method="", item_id="", instance_id=""):
    row = normalize_flora_harvest_state(record)
    limit = _safe_int(row.get("harvest_limit"), 1)
    before = max(1, _safe_int(row.get("harvest_remaining"), limit))
    remaining = max(0, before - 1)
    count = min(limit, _safe_int(row.get("harvest_count"), 0) + 1)
    form = _str_key(row.get("growth_form"), "flower")
    if remaining <= 0:
        stage = "picked"
        exhausted = True
        exhaustion_kind = "picked_over"
    else:
        stage = PARTIAL_HARVEST_STAGE_BY_FORM.get(form, "thinned")
        exhausted = False
        exhaustion_kind = ""
    updates = {
        "stage": stage,
        "harvest_limit": int(limit),
        "harvest_count": int(count),
        "harvest_remaining": int(remaining),
        "harvest_exhausted": bool(exhausted),
        "harvested_by_eid": eid,
        "harvested_tick": _safe_int(tick, 0),
        "last_harvest_tick": _safe_int(tick, 0),
        "lifetime_harvest_count": max(
            _safe_int(row.get("lifetime_harvest_count"), _safe_int(row.get("harvest_count"), 0)),
            _safe_int(row.get("harvest_count"), 0),
        ) + 1,
        "regrowth_started_tick": _safe_int(tick, 0),
        "regrowth_pause_baseline": max(0, _safe_int(row.get("paused_ticks"), 0)),
        "harvest_method": str(method or "").strip().lower(),
        "output_item_id": str(item_id or "").strip().lower(),
        "output_instance_id": str(instance_id or "").strip(),
    }
    if exhausted:
        updates["exhaustion_kind"] = exhaustion_kind
        updates["exhausted_tick"] = _safe_int(tick, 0)
    else:
        updates["exhaustion_kind"] = ""
        updates["exhausted_tick"] = None
    return updates


def flora_regrowth_interval_ticks(record):
    """Return the active-world ticks needed to recover one harvest use."""

    if not isinstance(record, dict):
        record = {}
    potential = record.get("harvest_potential") if isinstance(record.get("harvest_potential"), dict) else {}
    configured_ticks = record.get("regrowth_ticks")
    if configured_ticks is None:
        configured_ticks = potential.get("regrowth_ticks")
    configured_hours = record.get("regrowth_hours")
    if configured_hours is None:
        configured_hours = potential.get("regrowth_hours")

    if configured_ticks is not None:
        base_ticks = max(DEFAULT_TICKS_PER_HOUR, _safe_int(configured_ticks, DEFAULT_TICKS_PER_HOUR))
    elif configured_hours is not None:
        base_ticks = max(
            DEFAULT_TICKS_PER_HOUR,
            int(max(1.0, _safe_float(configured_hours, 1.0)) * DEFAULT_TICKS_PER_HOUR),
        )
    else:
        form = _str_key(record.get("growth_form"), "flower")
        rarity = _str_key(record.get("rarity"), "common")
        hours = FLORA_REGROWTH_HOURS_BY_FORM.get(form, FLORA_REGROWTH_HOURS_BY_FORM["flower"])
        rarity_multiplier = FLORA_REGROWTH_RARITY_MULTIPLIER.get(rarity, 1.0)
        base_ticks = int(float(hours) * float(rarity_multiplier) * DEFAULT_TICKS_PER_HOUR)

    care_multiplier = 1.0
    if str(record.get("cultivation_id") or "").strip():
        container = _str_key(record.get("container_kind"), "ground")
        care_multiplier *= {"planter": 0.80, "pot": 0.90}.get(container, 0.90)
        quality_bonus = min(2, max(0, _safe_int(record.get("maintenance_quality_bonus"), 0)))
        care_multiplier *= 1.0 - 0.10 * quality_bonus

    raw_ticks = max(DEFAULT_TICKS_PER_HOUR, int(float(base_ticks) * care_multiplier))
    return max(
        DEFAULT_TICKS_PER_HOUR,
        ((raw_ticks + DEFAULT_TICKS_PER_HOUR - 1) // DEFAULT_TICKS_PER_HOUR) * DEFAULT_TICKS_PER_HOUR,
    )


def _flora_record_chunk_key(sim, record):
    chunk = record.get("chunk") if isinstance(record, dict) else None
    if isinstance(chunk, (tuple, list)) and len(chunk) == 2:
        try:
            return (int(chunk[0]), int(chunk[1]))
        except (TypeError, ValueError):
            pass
    try:
        return tuple(int(value) for value in sim.chunk_coords(record.get("x", 0), record.get("y", 0)))
    except Exception:
        size = max(1, _safe_int(getattr(sim, "chunk_size", 16), 16))
        return (_safe_int(record.get("x"), 0) // size, _safe_int(record.get("y"), 0) // size)


def _loaded_flora_records(sim):
    patches, chunk_records = ensure_flora_state(sim)
    loaded = getattr(getattr(sim, "world", None), "loaded_chunks", None)
    loaded_keys = set(loaded) if isinstance(loaded, dict) and loaded else set(chunk_records)
    rows = []
    seen = set()
    for key in sorted(loaded_keys):
        for stored in tuple(chunk_records.get(key, ()) or ()):
            if not isinstance(stored, dict):
                continue
            record_id = str(stored.get("id") or "").strip()
            if not record_id or record_id in seen:
                continue
            canonical = patches.get(record_id)
            rows.append(canonical if isinstance(canonical, dict) else stored)
            seen.add(record_id)
    if rows or chunk_records:
        return tuple(rows)
    for stored in tuple(patches.values()):
        if not isinstance(stored, dict):
            continue
        if loaded_keys and _flora_record_chunk_key(sim, stored) not in loaded_keys:
            continue
        record_id = str(stored.get("id") or "").strip()
        if record_id and record_id not in seen:
            rows.append(stored)
            seen.add(record_id)
    return tuple(rows)


def _store_flora_record(sim, record):
    patches, chunk_records = ensure_flora_state(sim)
    record_id = str((record or {}).get("id") or "").strip()
    if not record_id:
        return
    stored = dict(record)
    patches[record_id] = stored
    key = _flora_record_chunk_key(sim, stored)
    bucket = []
    replaced = False
    for row in tuple(chunk_records.get(key, ()) or ()):
        if str((row or {}).get("id") or "").strip() == record_id:
            bucket.append(dict(stored))
            replaced = True
        else:
            bucket.append(dict(row) if isinstance(row, dict) else row)
    if not replaced:
        bucket.append(dict(stored))
    chunk_records[key] = bucket


def _advance_flora_record_regrowth(record, now):
    row = normalize_flora_harvest_state(record)
    stage = _str_key(row.get("stage"), "mature")
    if stage in FAILED_FLORA_STAGES or stage in IMMATURE_FLORA_STAGES or bool(row.get("growth_paused")):
        return row, 0, False
    limit = flora_harvest_limit(row)
    remaining = max(0, min(limit, _safe_int(row.get("harvest_remaining"), limit)))
    if remaining >= limit:
        return row, 0, False

    anchor_values = []
    for field in ("regrowth_started_tick", "last_harvest_tick", "exhausted_tick", "harvested_tick"):
        value = row.get(field)
        if value not in (None, ""):
            anchor_values.append(_safe_int(value, now))
    paused_total = max(0, _safe_int(row.get("paused_ticks"), 0))
    if not anchor_values:
        row["regrowth_started_tick"] = int(now)
        row["regrowth_pause_baseline"] = int(paused_total)
        return row, 0, True

    anchor = max(anchor_values)
    pause_baseline = max(0, _safe_int(row.get("regrowth_pause_baseline"), paused_total))
    paused_since_anchor = max(0, paused_total - pause_baseline)
    active_elapsed = max(0, int(now) - int(anchor) - int(paused_since_anchor))
    interval = flora_regrowth_interval_ticks(row)
    recovered = min(limit - remaining, active_elapsed // interval)
    if recovered <= 0:
        return row, 0, False

    row["lifetime_harvest_count"] = max(
        _safe_int(row.get("lifetime_harvest_count"), 0),
        _safe_int(row.get("harvest_count"), 0),
    )
    remaining += int(recovered)
    residual = active_elapsed - int(recovered) * interval
    row["harvest_remaining"] = int(remaining)
    row["harvest_count"] = max(0, int(limit) - int(remaining))
    row["harvest_exhausted"] = False
    row["regrowth_started_tick"] = int(now) - int(residual)
    row["regrowth_pause_baseline"] = int(paused_total)
    row["last_regrowth_tick"] = int(now)
    row["regrowth_count"] = max(0, _safe_int(row.get("regrowth_count"), 0)) + int(recovered)
    row.pop("exhaustion_kind", None)
    row.pop("exhausted_tick", None)
    form = _str_key(row.get("growth_form"), "flower")
    if remaining >= limit:
        row["stage"] = "mature"
        row["regrown_tick"] = int(now)
    else:
        row["stage"] = PARTIAL_HARVEST_STAGE_BY_FORM.get(form, "thinned")
    return normalize_flora_harvest_state(row), int(recovered), True


def advance_loaded_flora_regrowth(sim, *, now=None):
    """Advance harvested flora already indexed in realized chunk buckets."""

    now = _safe_int(getattr(sim, "tick", 0) if now is None else now, 0)
    checked = 0
    initialized = 0
    recovered_uses = 0
    changed_records = []
    for record in _loaded_flora_records(sim):
        if not isinstance(record, dict):
            continue
        checked += 1
        updated, recovered, changed = _advance_flora_record_regrowth(record, now)
        if not changed:
            continue
        _store_flora_record(sim, updated)
        changed_records.append(updated)
        if recovered <= 0:
            initialized += 1
            continue
        recovered_uses += int(recovered)
        sim.emit(Event(
            "flora_regrown",
            flora_id=updated.get("id"),
            plant_id=updated.get("plant_id"),
            plant_name=updated.get("name"),
            growth_form=updated.get("growth_form"),
            rarity=updated.get("rarity"),
            recovered_uses=int(recovered),
            harvest_remaining=_safe_int(updated.get("harvest_remaining"), 0),
            harvest_limit=_safe_int(updated.get("harvest_limit"), 1),
            fully_regrown=_safe_int(updated.get("harvest_remaining"), 0) >= _safe_int(updated.get("harvest_limit"), 1),
            regrowth_interval_ticks=flora_regrowth_interval_ticks(updated),
            x=updated.get("x"),
            y=updated.get("y"),
            z=updated.get("z", 0),
        ))
    return {
        "checked": int(checked),
        "initialized": int(initialized),
        "recovered_uses": int(recovered_uses),
        "records": tuple(changed_records),
    }


def _flora_record_id(cx, cy, cluster_index, tile_index):
    return f"flora:{int(cx)}:{int(cy)}:{int(cluster_index)}:{int(tile_index)}"


def _make_flora_record(row, *, cx, cy, x, y, z, cluster_index, tile_index, rng, spread_direction=None):
    variant_seed = rng.randrange(1, 2**31 - 1)
    spread_state = _spread_state_for(row, tile_index)
    genetics = dict(row.get("genetics", {}) or {})
    if _str_key(row.get("growth_form")) == "fungus":
        genetics = preroll_fungal_mutation_glow(genetics, seed=variant_seed)
    record = {
        "id": _flora_record_id(cx, cy, cluster_index, tile_index),
        "plant_id": row["id"],
        "name": row["name"],
        "x": int(x),
        "y": int(y),
        "z": int(z),
        "chunk": [int(cx), int(cy)],
        "stage": "mature",
        "variant_seed": int(variant_seed),
        "color_key": _color_for_row(row, rng),
        "growth_form": row["growth_form"],
        "glyph": row["glyph"],
        "render_key": row["render_key"],
        "spread_state": spread_state,
        "spread_direction": spread_direction if spread_direction and spread_state in {"trailing", "creeping"} else None,
        "cluster_id": f"flora:{int(cx)}:{int(cy)}:{int(cluster_index)}",
        "tags": list(row.get("tags", ())),
        "rarity": row.get("rarity", "common"),
        "genetics": genetics,
        "harvest_potential": dict(row.get("harvest_potential", {}) or {}),
        "wild_spawn": bool(row.get("wild_spawn", True)),
        "cultivation_allowed": bool(row.get("cultivation_allowed", True)),
        "crossbreed_allowed": bool(row.get("crossbreed_allowed", True)),
        "herbal_pool_allowed": bool(row.get("herbal_pool_allowed", True)),
    }
    return normalize_flora_harvest_state(record)


def register_flora_patch(sim, record):
    patches, chunk_records = ensure_flora_state(sim)
    if not isinstance(record, dict):
        return None
    record_id = str(record.get("id") or "").strip()
    if not record_id:
        return None
    normalized = normalize_flora_harvest_state(record)
    genetics = normalized.get("genetics") if isinstance(normalized.get("genetics"), dict) else {}
    if _safe_int(genetics.get("schema_version"), 0) != 1:
        catalog_row = _catalog_row_for_record(normalized)
        genetics_row = dict(catalog_row or normalized)
        genetics_row["genetics"] = genetics or catalog_row.get("genetics", {}) if isinstance(catalog_row, dict) else genetics
        normalized["genetics"] = normalize_flora_genetics(normalized.get("plant_id") or normalized.get("id"), genetics_row, seed=0)
    if _str_key(normalized.get("growth_form")) == "fungus":
        normalized["genetics"] = preroll_fungal_mutation_glow(
            normalized.get("genetics"),
            seed=normalized.get("variant_seed") or record_id,
        )
    register_dynamic_flora_profile(sim, normalized)
    patches[record_id] = dict(normalized)
    luminous_ids = getattr(sim, "bioluminescent_flora_ids", None)
    if not isinstance(luminous_ids, set):
        luminous_ids = set()
        sim.bioluminescent_flora_ids = luminous_ids
    if bool(normalized.get("bioluminescent")):
        luminous_ids.add(record_id)
    else:
        luminous_ids.discard(record_id)
    chunk = record.get("chunk")
    if isinstance(chunk, (tuple, list)) and len(chunk) == 2:
        key = (int(chunk[0]), int(chunk[1]))
        bucket = [row for row in tuple(chunk_records.get(key, ()) or ()) if str(row.get("id", "")) != record_id]
        bucket.append(dict(normalized))
        chunk_records[key] = bucket
    return record_id


def update_flora_patch(sim, record_id, updates):
    patches, _chunk_records = ensure_flora_state(sim)
    record_id = str(record_id or "").strip()
    record = patches.get(record_id)
    if not record_id or not isinstance(record, dict):
        return None
    updated = dict(record)
    updated.update(dict(updates or {}))
    _store_flora_record(sim, updated)
    luminous_ids = getattr(sim, "bioluminescent_flora_ids", None)
    if not isinstance(luminous_ids, set):
        luminous_ids = set()
        sim.bioluminescent_flora_ids = luminous_ids
    if bool(updated.get("bioluminescent")):
        luminous_ids.add(record_id)
    else:
        luminous_ids.discard(record_id)
    return updated


def flora_fire_integrity_max(record):
    """Return a small persistent heat budget for one flora patch."""

    if not isinstance(record, dict):
        return 1
    traits = _record_traits(record)
    configured = record.get("fire_integrity_max", traits.get("fire_integrity"))
    fallback = FLORA_FIRE_INTEGRITY_BY_FORM.get(_str_key(record.get("growth_form")), 4)
    return max(1, _safe_int(configured, fallback))


def apply_flora_fire_damage(sim, record, amount, *, fire_intensity=1, source_eid=None):
    """Scorch one canonical flora-layer patch and persist the result.

    Flora deliberately remains outside ECS and property durability.  Failed
    plants stay on their own render layer as visible withered remains, while a
    destruction event gives ecology systems a clean reaction seam.
    """

    if not isinstance(record, dict):
        return {"damaged": False, "reason": "missing_flora"}
    record_id = str(record.get("id") or "").strip()
    canonical = getattr(sim, "flora_patches", {}).get(record_id)
    if isinstance(canonical, dict):
        record = canonical
    if not record_id or bool(record.get("fire_destroyed")):
        return {"damaged": False, "reason": "already_destroyed"}

    profile = _catalog_row_for_record(record)
    traits = _record_traits(record)
    spread_profile = {}
    for source in ((profile or {}).get("spread_profile"), record.get("spread_profile")):
        if isinstance(source, dict):
            spread_profile.update(source)
    try:
        resistance = float(
            record.get(
                "fire_resistance",
                traits.get("fire_resistance", spread_profile.get("fire_resistance", 1.0)),
            )
            or 1.0
        )
    except (TypeError, ValueError):
        resistance = 1.0
    resistance = max(0.25, min(4.0, resistance))
    requested = max(0, _safe_int(amount, 0))
    loss = max(1, int(math.ceil(float(requested) / resistance))) if requested > 0 else 0
    maximum = flora_fire_integrity_max(record)
    before = max(0, min(maximum, _safe_int(record.get("fire_integrity"), maximum)))
    after = max(0, before - loss)
    applied = max(0, before - after)
    if applied <= 0:
        return {"damaged": False, "reason": "no_damage"}

    tick = _safe_int(getattr(sim, "tick", 0), 0)
    updated = dict(record)
    updated.update({
        "fire_integrity_max": int(maximum),
        "fire_integrity": int(after),
        "last_fire_damage_tick": int(tick),
        "last_fire_intensity": max(1, _safe_int(fire_intensity, 1)),
        "last_fire_source_eid": source_eid,
    })
    destroyed = after <= 0
    if destroyed:
        updated.update({
            "stage": "failed",
            "failure_kind": "fire",
            "fire_destroyed": True,
            "fire_destroyed_tick": int(tick),
            "harvest_count": flora_harvest_limit(updated),
            "harvest_remaining": 0,
            "harvest_exhausted": True,
            "fertility_remaining": 0,
        })
    _store_flora_record(sim, updated)

    cultivation_id = str(updated.get("cultivation_id") or "").strip()
    cultivation = getattr(sim, "cultivation_records", None)
    if cultivation_id and isinstance(cultivation, dict) and isinstance(cultivation.get(cultivation_id), dict):
        cultivation[cultivation_id].update({
            "fire_integrity_max": int(maximum),
            "fire_integrity": int(after),
            "last_fire_damage_tick": int(tick),
        })
        if destroyed:
            cultivation[cultivation_id].update({
                "stage": "failed",
                "failure_kind": "fire",
                "fire_destroyed": True,
                "fire_destroyed_tick": int(tick),
                "harvest_remaining": 0,
                "fertility_remaining": 0,
            })

    payload = {
        "flora_id": record_id,
        "plant_id": updated.get("plant_id"),
        "plant_name": updated.get("name") or updated.get("plant_name"),
        "growth_form": updated.get("growth_form"),
        "damage": int(applied),
        "integrity_before": int(before),
        "integrity": int(after),
        "max_integrity": int(maximum),
        "fire_intensity": max(1, _safe_int(fire_intensity, 1)),
        "source_eid": source_eid,
        "x": _safe_int(updated.get("x"), 0),
        "y": _safe_int(updated.get("y"), 0),
        "z": _safe_int(updated.get("z"), 0),
        "flora_record": dict(updated),
    }
    sim.emit(Event("flora_fire_damaged", **payload))
    if destroyed and before > 0:
        sim.emit(Event("flora_destroyed_by_fire", **payload))
    return {
        "damaged": True,
        "flora_id": record_id,
        "damage": int(applied),
        "integrity_before": int(before),
        "integrity": int(after),
        "max_integrity": int(maximum),
        "destroyed": bool(destroyed),
    }


def ensure_chunk_flora(sim, chunk, *, property_records=None):
    patches, chunk_records = ensure_flora_state(sim)
    key = _chunk_key_from_chunk(chunk)
    if key is None:
        return ()
    if key in chunk_records:
        return tuple(chunk_records.get(key, ()) or ())

    catalog = flora_catalog_for_sim(sim, native_only=True)
    candidates = _candidate_positions(sim, chunk)
    if not candidates:
        chunk_records[key] = []
        return ()

    area_key, district_type = _chunk_area_context(sim, chunk)
    low, high = AREA_DENSITY.get(area_key, AREA_DENSITY["wilderness"])
    rng = random.Random(f"{getattr(sim, 'seed', 0)}:flora:{key[0]}:{key[1]}")
    cluster_count = rng.randint(low, high)
    if len(candidates) < cluster_count:
        cluster_count = len(candidates)
    used = set()
    records = []
    candidate_by_xy = {(x, y, z): (x, y, z, weight, terrain_key) for x, y, z, weight, terrain_key in candidates}

    for cluster_index in range(cluster_count):
        available = [row for row in candidates if (row[0], row[1], row[2]) not in used]
        if not available:
            break
        root = _weighted_choice(rng, [((x, y, z, terrain), weight) for x, y, z, weight, terrain in available])
        if root is None:
            break
        root_x, root_y, root_z, terrain_key = root
        plant = _select_plant(catalog, rng, area_key=area_key, district_type=district_type, terrain_key=terrain_key)
        cluster_size = _cluster_size_for_plant(plant, rng, area_key=area_key)
        positions = [(root_x, root_y, root_z, None)]
        used.add((root_x, root_y, root_z))
        frontier = [(root_x, root_y)]
        while len(positions) < cluster_size and frontier:
            base_x, base_y = rng.choice(frontier)
            rng_neighbors = list(_cluster_neighbors(base_x, base_y))
            rng.shuffle(rng_neighbors)
            added = False
            for nx, ny, direction in rng_neighbors:
                nkey = (nx, ny, root_z)
                if nkey in used or nkey not in candidate_by_xy:
                    continue
                used.add(nkey)
                frontier.append((nx, ny))
                positions.append((nx, ny, root_z, direction))
                added = True
                break
            if not added:
                frontier.remove((base_x, base_y))

        for tile_index, (x, y, z, direction) in enumerate(positions):
            record = _make_flora_record(
                plant,
                cx=key[0],
                cy=key[1],
                x=x,
                y=y,
                z=z,
                cluster_index=cluster_index,
                tile_index=tile_index,
                rng=rng,
                spread_direction=direction,
            )
            records.append(record)
            patches[record["id"]] = dict(record)

    chunk_records[key] = records
    return tuple(records)


def flora_records_in_rect(sim, min_x, min_y, max_x, max_y, z=0):
    ensure_flora_state(sim)
    rows = []
    for record in getattr(sim, "flora_patches", {}).values():
        if not isinstance(record, dict):
            continue
        try:
            x = int(record.get("x", 0) or 0)
            y = int(record.get("y", 0) or 0)
            rz = int(record.get("z", 0) or 0)
        except (TypeError, ValueError):
            continue
        if rz != int(z):
            continue
        if int(min_x) <= x <= int(max_x) and int(min_y) <= y <= int(max_y):
            rows.append(record)
    return tuple(sorted(rows, key=lambda row: (int(row.get("y", 0) or 0), int(row.get("x", 0) or 0), str(row.get("id", "")))))


def flora_at(sim, x, y, z=0):
    ensure_flora_state(sim)
    try:
        target = (int(x), int(y), int(z))
        chunk = sim.chunk_coords(target[0], target[1])
    except (TypeError, ValueError, AttributeError):
        return ()
    rows = []
    patches = getattr(sim, "flora_patches", {})
    chunk_records = getattr(sim, "chunk_flora_records", {})
    indexed = isinstance(chunk_records, dict) and chunk in chunk_records
    source_rows = tuple(chunk_records.get(chunk, ()) or ()) if indexed else tuple(patches.values())
    cache = getattr(sim, "_flora_at_chunk_index", None)
    if not isinstance(cache, dict):
        cache = {}
        sim._flora_at_chunk_index = cache
    cache_key = chunk if indexed else None
    signature = (id(chunk_records.get(chunk)) if indexed else id(patches), len(source_rows), id(patches))
    entry = cache.get(cache_key)
    if not isinstance(entry, dict) or entry.get("signature") != signature:
        coord_index = {}
        for stored in source_rows:
            if not isinstance(stored, dict):
                continue
            record_id = str(stored.get("id") or "").strip()
            record = patches.get(record_id) if record_id else None
            if not isinstance(record, dict):
                record = stored
            try:
                coord = (
                    int(record.get("x", 0) or 0),
                    int(record.get("y", 0) or 0),
                    int(record.get("z", 0) or 0),
                )
            except (TypeError, ValueError):
                continue
            coord_index.setdefault(coord, []).append(record_id or record)
        entry = {
            "signature": signature,
            "coords": {coord: tuple(rows) for coord, rows in coord_index.items()},
        }
        if len(cache) >= 128 and cache_key not in cache:
            cache.clear()
        cache[cache_key] = entry

    rows = []
    seen = set()
    for stored in tuple(entry.get("coords", {}).get(target, ()) or ()):
        if isinstance(stored, str):
            record_id = stored
        elif isinstance(stored, dict):
            record_id = str(stored.get("id") or "").strip()
        else:
            record_id = ""
        record = patches.get(record_id) if record_id else None
        if not isinstance(record, dict):
            record = stored
        if not isinstance(record, dict):
            continue
        if record_id and record_id in seen:
            continue
        rows.append(record)
        if record_id:
            seen.add(record_id)
    return tuple(sorted(rows, key=lambda row: str(row.get("id", ""))))


def flora_render_data(record, *, sim=None):
    if not isinstance(record, dict):
        record = {}
    record = normalize_flora_harvest_state(record)
    growth_form = _str_key(record.get("growth_form"), "flower")
    stage = _str_key(record.get("stage"))
    exhausted = stage in EXHAUSTED_FLORA_STAGES or _safe_int(record.get("harvest_remaining"), 0) <= 0
    failed = stage in FAILED_FLORA_STAGES
    bloom_state = flora_bloom_state(sim, record)
    environmental_morph = _str_key(record.get("environmental_morph"))
    if failed:
        semantic = "flora_withered"
    elif stage in {"seeded", "sprouting"}:
        semantic = "flora_seedling"
    elif stage == "young":
        semantic = "flora_young"
    elif environmental_morph == "accumulator":
        semantic = "flora_accumulator"
    elif environmental_morph == "contaminant_indicator":
        semantic = "flora_indicator"
    elif growth_form == "lichen":
        semantic = "flora_moss"
    elif growth_form == "flower" and bloom_state == "closed" and not exhausted:
        semantic = "flora_flower_bud"
    elif growth_form == "flower" and bloom_state == "night_open" and not exhausted:
        semantic = "flora_flower_night"
    else:
        semantic = f"flora_{growth_form}"
    if environmental_morph == "accumulator" and not failed:
        color = _str_key(
            record.get("bioluminescent_color_key"),
            fungal_mutation_glow_color(record.get("genetics")),
        )
    elif failed:
        color = "flora_withered"
    elif stage in {"seeded", "sprouting"}:
        color = "flora_seedling"
    elif stage == "young":
        color = _str_key(record.get("color_key"), "flora_leaf")
    elif exhausted:
        color = "flora_spent"
    elif growth_form == "flower" and bloom_state == "closed":
        color = "flora_flower_closed"
    elif growth_form == "flower" and bloom_state == "night_open":
        color = "flora_flower_night"
    else:
        color = _str_key(record.get("color_key"), record.get("render_key") or DEFAULT_RENDER_KEY_BY_FORM.get(growth_form, "flora_leaf"))
    effects = [effect for effect in (record.get("spread_state"),) if effect in {"creeping", "trailing", "flowering"}]
    if bloom_state in {"open", "closed", "night_open"} and (growth_form == "flower" or bloom_state != "open"):
        effects.append(f"flower_{bloom_state}" if growth_form == "flower" else bloom_state)
    if exhausted and not failed:
        effects.append("picked")
    if failed:
        effects.append("withered")
    elif stage in IMMATURE_FLORA_STAGES:
        effects.append(stage)
    return {
        "glyph": "," if stage in {"seeded", "sprouting", "young"} else str(record.get("glyph") or DEFAULT_GLYPH_BY_FORM.get(growth_form, ","))[:1],
        "color": color,
        "semantic_id": semantic,
        "layer": "ground_overlay",
        "priority": -20,
        "effects": tuple(dict.fromkeys(effects)),
    }


def flora_look_text(records, *, sim=None):
    if isinstance(records, dict):
        rows = (records,)
    else:
        rows = tuple(row for row in (records or ()) if isinstance(row, dict))
    if not rows:
        return ""
    record = normalize_flora_harvest_state(rows[0])
    form = _str_key(record.get("growth_form"), "flower")
    name = str(record.get("name") or record.get("plant_id") or "plant").replace("_", " ").strip()
    spread_state = _str_key(record.get("spread_state"))
    direction = _str_key(record.get("spread_direction"))
    prefix = {
        "flower": "flowers",
        "grass": "grass",
        "reed": "reeds",
        "moss": "moss",
        "lichen": "lichen",
        "vine": "vine",
        "shrub": "shrub",
        "fern": "fern",
        "fungus": "mushrooms",
    }.get(form, "plants")
    if _str_key(record.get("environmental_morph")) == "accumulator":
        prefix = "tended accumulator bed"
    text = f"{prefix}: {name}"
    stage = _str_key(record.get("stage"))
    if stage == "seeded":
        text = f"seeded {prefix}: {name}"
    elif stage == "sprouting":
        text = f"sprouting {prefix}: {name}"
    elif stage == "young":
        text = f"young {prefix}: {name}"
    elif stage in FAILED_FLORA_STAGES:
        text = f"withering {prefix}: {name}"
    elif stage in EXHAUSTED_FLORA_STAGES or _safe_int(record.get("harvest_remaining"), 0) <= 0:
        text = f"picked-over {prefix}: {name}"
    elif _safe_int(record.get("harvest_count"), 0) > 0:
        text = f"partly harvested {prefix}: {name}"
    elif form == "flower":
        state = flora_bloom_state(sim, record)
        if state == "closed":
            text = f"closed blossoms: {name}"
        elif state == "night_open":
            text = f"night-blooming flowers: {name}"
        else:
            text = f"open flowers: {name}"
    elif flora_bloom_state(sim, record) == "night_open":
        text = f"night-blooming {prefix}: {name}"
    if form == "vine" and spread_state == "trailing" and direction:
        text += f" trailing {direction}"
    elif form in {"moss", "lichen"} and spread_state == "creeping" and direction:
        text += f" creeping {direction}"
    if len(rows) > 1:
        text += f" +{len(rows) - 1}"
    ecology_note = str(record.get("ecology_note", "") or "").strip()
    if ecology_note:
        text += f". {ecology_note}"
    return text
