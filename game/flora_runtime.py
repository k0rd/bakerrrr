"""Runtime helpers for lightweight visual flora patches.

Flora is nonblocking world presence. The catalog carries future hooks so later
systems can add breeding, medicine, food, fiber, or creeping growth without
reauthoring plants.
"""

from __future__ import annotations

import json
import random
from functools import lru_cache
from pathlib import Path

from game.content_warnings import warn_content_fallback
from game.json_metadata import split_object_document


FLORA_PATH = Path(__file__).resolve().parent / "flora.json"

VALID_GROWTH_FORMS = frozenset(("flower", "grass", "reed", "moss", "lichen", "vine", "shrub", "fern"))
VALID_GLYPHS = frozenset((",", "'", ";", "*"))
RARITY_BASE_WEIGHTS = {
    "common": 12.0,
    "uncommon": 5.0,
    "rare": 1.4,
}

DEFAULT_GLYPH_BY_FORM = {
    "flower": "'",
    "grass": ",",
    "reed": ",",
    "moss": ",",
    "lichen": ",",
    "vine": ";",
    "shrub": "*",
    "fern": ",",
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
    return {
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
    }


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


def _flora_record_id(cx, cy, cluster_index, tile_index):
    return f"flora:{int(cx)}:{int(cy)}:{int(cluster_index)}:{int(tile_index)}"


def _make_flora_record(row, *, cx, cy, x, y, z, cluster_index, tile_index, rng, spread_direction=None):
    variant_seed = rng.randrange(1, 2**31 - 1)
    spread_state = _spread_state_for(row, tile_index)
    return {
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
    }


def register_flora_patch(sim, record):
    patches, chunk_records = ensure_flora_state(sim)
    if not isinstance(record, dict):
        return None
    record_id = str(record.get("id") or "").strip()
    if not record_id:
        return None
    patches[record_id] = dict(record)
    chunk = record.get("chunk")
    if isinstance(chunk, (tuple, list)) and len(chunk) == 2:
        key = (int(chunk[0]), int(chunk[1]))
        bucket = [row for row in tuple(chunk_records.get(key, ()) or ()) if str(row.get("id", "")) != record_id]
        bucket.append(dict(record))
        chunk_records[key] = bucket
    return record_id


def ensure_chunk_flora(sim, chunk, *, property_records=None):
    patches, chunk_records = ensure_flora_state(sim)
    key = _chunk_key_from_chunk(chunk)
    if key is None:
        return ()
    if key in chunk_records:
        return tuple(chunk_records.get(key, ()) or ())

    catalog = load_flora_catalog()
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
    rows = []
    for record in getattr(sim, "flora_patches", {}).values():
        if not isinstance(record, dict):
            continue
        try:
            if int(record.get("x", 0) or 0) == int(x) and int(record.get("y", 0) or 0) == int(y) and int(record.get("z", 0) or 0) == int(z):
                rows.append(record)
        except (TypeError, ValueError):
            continue
    return tuple(sorted(rows, key=lambda row: str(row.get("id", ""))))


def flora_render_data(record):
    if not isinstance(record, dict):
        record = {}
    growth_form = _str_key(record.get("growth_form"), "flower")
    semantic = "flora_moss" if growth_form == "lichen" else f"flora_{growth_form}"
    return {
        "glyph": str(record.get("glyph") or DEFAULT_GLYPH_BY_FORM.get(growth_form, ","))[:1],
        "color": _str_key(record.get("color_key"), record.get("render_key") or DEFAULT_RENDER_KEY_BY_FORM.get(growth_form, "flora_leaf")),
        "semantic_id": semantic,
        "layer": "ground_overlay",
        "priority": -20,
        "effects": tuple(effect for effect in (record.get("spread_state"),) if effect in {"creeping", "trailing", "flowering"}),
    }


def flora_look_text(records):
    if isinstance(records, dict):
        rows = (records,)
    else:
        rows = tuple(row for row in (records or ()) if isinstance(row, dict))
    if not rows:
        return ""
    record = rows[0]
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
    }.get(form, "plants")
    text = f"{prefix}: {name}"
    if _str_key(record.get("stage")) == "picked":
        text = f"picked-over {prefix}: {name}"
    if form == "vine" and spread_state == "trailing" and direction:
        text += f" trailing {direction}"
    elif form in {"moss", "lichen"} and spread_state == "creeping" and direction:
        text += f" creeping {direction}"
    if len(rows) > 1:
        text += f" +{len(rows) - 1}"
    return text
