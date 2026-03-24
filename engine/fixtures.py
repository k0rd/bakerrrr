"""Shared fixture generation helpers for chunk property registration."""

import json
import random
from pathlib import Path

PATH_GLYPHS = {"=", ":"}
PLACEMENT_BUCKETS = {"path_side", "path_tile", "entry_side", "street_side", "edge", "open"}
FIXTURES_PATH = Path(__file__).resolve().parent.parent / "game" / "fixtures.json"

DEFAULT_CITY_FIXTURE_SPECS = (
    {
        "id": "streetlamp",
        "name": "Streetlamp",
        "kind": "fixture",
        "glyph": "l",
        "color": "property_fixture",
        "cover_kind": "low",
        "cover_value": 0.32,
        "weight": 6,
        "priorities": ("path_side", "street_side", "entry_side", "edge", "open"),
        "light_enabled": True,
        "light_radius": 5,
        "light_intensity": 0.68,
        "light_phases": ("dawn", "dusk", "night"),
    },
    {
        "id": "utility_pole",
        "name": "Utility Pole",
        "kind": "fixture",
        "glyph": "p",
        "color": "property_fixture",
        "cover_kind": "low",
        "cover_value": 0.28,
        "weight": 4,
        "priorities": ("path_side", "edge", "street_side", "open"),
    },
    {
        "id": "hydrant",
        "name": "Hydrant",
        "kind": "fixture",
        "glyph": "h",
        "color": "property_fixture",
        "cover_kind": "low",
        "cover_value": 0.36,
        "weight": 3,
        "priorities": ("entry_side", "street_side", "path_side", "open"),
    },
    {
        "id": "bus_stop",
        "name": "Bus Stop",
        "kind": "fixture",
        "glyph": "u",
        "color": "property_fixture",
        "cover_kind": "low",
        "cover_value": 0.5,
        "weight": 2,
        "priorities": ("path_side", "path_tile", "street_side", "open"),
        "light_enabled": True,
        "light_radius": 2,
        "light_intensity": 0.18,
        "light_phases": ("dawn", "dusk", "night"),
    },
    {
        "id": "bench",
        "name": "Bench",
        "kind": "fixture",
        "glyph": ";",
        "color": "property_fixture",
        "cover_kind": "low",
        "cover_value": 0.26,
        "weight": 2,
        "priorities": ("path_side", "street_side", "open"),
    },
    {
        "id": "mailbox",
        "name": "Mailbox",
        "kind": "fixture",
        "glyph": "m",
        "color": "property_fixture",
        "cover_kind": "low",
        "cover_value": 0.24,
        "weight": 2,
        "priorities": ("entry_side", "street_side", "open"),
    },
    {
        "id": "junction_box",
        "name": "Junction Box",
        "kind": "asset",
        "glyph": "j",
        "color": "property_asset",
        "cover_kind": "low",
        "cover_value": 0.42,
        "weight": 2,
        "priorities": ("edge", "street_side", "entry_side", "open"),
    },
    {
        "id": "transformer",
        "name": "Transformer",
        "kind": "asset",
        "glyph": "t",
        "color": "property_asset",
        "cover_kind": "full",
        "cover_value": 0.55,
        "weight": 1,
        "priorities": ("edge", "street_side", "open"),
    },
    {
        "id": "atm_kiosk",
        "name": "ATM Kiosk",
        "kind": "asset",
        "glyph": "$",
        "color": "property_service",
        "cover_kind": "low",
        "cover_value": 0.38,
        "weight": 1,
        "priorities": ("path_side", "street_side", "open"),
        "finance_services": ("banking",),
        "public": True,
        "light_enabled": True,
        "light_radius": 3,
        "light_intensity": 0.32,
        "light_phases": ("dawn", "dusk", "night"),
    },
    {
        "id": "claim_terminal",
        "name": "Claim Terminal",
        "kind": "asset",
        "glyph": "c",
        "color": "property_service",
        "cover_kind": "low",
        "cover_value": 0.36,
        "weight": 1,
        "priorities": ("path_side", "entry_side", "open"),
        "finance_services": ("insurance",),
        "public": True,
        "light_enabled": True,
        "light_radius": 3,
        "light_intensity": 0.28,
        "light_phases": ("dawn", "dusk", "night"),
    },
)

DEFAULT_NON_CITY_FIXTURE_SPECS = (
    {
        "id": "way_marker",
        "name": "Way Marker",
        "kind": "fixture",
        "glyph": "s",
        "color": "property_fixture",
        "cover_kind": "low",
        "cover_value": 0.24,
        "weight": 4,
        "priorities": ("path_side", "path_tile", "open", "edge"),
    },
    {
        "id": "trail_lamp",
        "name": "Trail Lamp",
        "kind": "fixture",
        "glyph": "l",
        "color": "property_fixture",
        "cover_kind": "low",
        "cover_value": 0.28,
        "weight": 3,
        "priorities": ("path_side", "open", "edge"),
        "light_enabled": True,
        "light_radius": 4,
        "light_intensity": 0.6,
        "light_phases": ("dawn", "dusk", "night"),
    },
    {
        "id": "relay_pole",
        "name": "Relay Pole",
        "kind": "asset",
        "glyph": "p",
        "color": "property_asset",
        "cover_kind": "low",
        "cover_value": 0.34,
        "weight": 2,
        "priorities": ("edge", "path_side", "open"),
    },
    {
        "id": "field_cache_box",
        "name": "Field Cache Box",
        "kind": "asset",
        "glyph": "j",
        "color": "property_asset",
        "cover_kind": "low",
        "cover_value": 0.4,
        "weight": 1,
        "priorities": ("edge", "open", "path_side"),
    },
)


def _num(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _normalize_fixture_spec(raw):
    if not isinstance(raw, dict):
        return None

    fixture_id = str(raw.get("id", "")).strip().lower()
    if not fixture_id:
        return None

    kind = str(raw.get("kind", "fixture")).strip().lower()
    if kind not in {"fixture", "asset"}:
        kind = "fixture"

    display = raw.get("display")
    if not isinstance(display, dict):
        display = {}

    cover = raw.get("cover")
    if not isinstance(cover, dict):
        cover = {}

    placement = raw.get("placement")
    if not isinstance(placement, dict):
        placement = {}

    name = str(raw.get("name", fixture_id.replace("_", " ").title())).strip() or fixture_id.replace("_", " ").title()
    glyph = str(raw.get("glyph", display.get("glyph", "f")))[:1] or "f"
    color = str(raw.get("color", display.get("color", "property_fixture" if kind == "fixture" else "property_asset"))).strip()
    if not color:
        color = "property_fixture" if kind == "fixture" else "property_asset"

    cover_kind = str(raw.get("cover_kind", cover.get("kind", "low"))).strip().lower()
    if cover_kind not in {"none", "low", "full"}:
        cover_kind = "low"
    cover_value = _num(raw.get("cover_value", cover.get("value", 0.35)), 0.35)
    cover_value = max(0.0, min(0.9, cover_value))

    weight = _num(raw.get("weight", placement.get("weight", 1.0)), 1.0)
    weight = max(0.1, weight)

    raw_priorities = raw.get("priorities", placement.get("priorities", ("open",)))
    priorities = []
    if isinstance(raw_priorities, (list, tuple)):
        for bucket in raw_priorities:
            name_key = str(bucket).strip().lower()
            if name_key and name_key in PLACEMENT_BUCKETS and name_key not in priorities:
                priorities.append(name_key)
    if not priorities:
        priorities = ["open"]

    raw_services = raw.get("services", raw.get("finance_services", ()))
    services = []
    if isinstance(raw_services, (list, tuple)):
        for service in raw_services:
            label = str(service).strip().lower()
            if label and label not in services:
                services.append(label)

    family = str(raw.get("family", "")).strip().lower()
    public_default = kind == "fixture"
    public = bool(raw.get("public", public_default))
    light = raw.get("light")
    if not isinstance(light, dict):
        light = {}
    light_enabled = bool(raw.get("light_enabled", light.get("enabled", False)))
    light_radius = int(max(0, round(_num(raw.get("light_radius", light.get("radius", 0)), 0.0))))
    light_intensity = max(0.0, min(1.0, _num(raw.get("light_intensity", light.get("intensity", 0.0)), 0.0)))
    raw_light_phases = raw.get("light_phases", light.get("phases", ()))
    light_phases = []
    if isinstance(raw_light_phases, (list, tuple)):
        for phase in raw_light_phases:
            label = str(phase).strip().lower()
            if label in {"dawn", "day", "dusk", "night"} and label not in light_phases:
                light_phases.append(label)
    if light_enabled and not light_phases:
        light_phases = ["dawn", "dusk", "night"]

    return {
        "id": fixture_id,
        "name": name,
        "kind": kind,
        "glyph": glyph,
        "color": color,
        "cover_kind": cover_kind,
        "cover_value": cover_value,
        "weight": weight,
        "priorities": tuple(priorities),
        "finance_services": tuple(services),
        "public": public,
        "family": family,
        "light_enabled": bool(light_enabled and light_radius > 0 and light_intensity > 0.0),
        "light_radius": max(0, int(light_radius)),
        "light_intensity": float(light_intensity),
        "light_phases": tuple(light_phases),
    }


def _normalize_fixture_list(raw_specs, fallback_specs):
    specs = []
    if isinstance(raw_specs, (list, tuple)):
        for row in raw_specs:
            normalized = _normalize_fixture_spec(row)
            if normalized:
                specs.append(normalized)

    if specs:
        return tuple(specs)
    return tuple(dict(spec) for spec in fallback_specs)


def load_fixture_specs(path=FIXTURES_PATH):
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        raw = {}

    if not isinstance(raw, dict):
        raw = {}

    city_specs = _normalize_fixture_list(raw.get("city"), DEFAULT_CITY_FIXTURE_SPECS)
    non_city_specs = _normalize_fixture_list(raw.get("non_city"), DEFAULT_NON_CITY_FIXTURE_SPECS)

    by_area = {
        "city": city_specs,
        "non_city": non_city_specs,
    }
    for area_key in ("frontier", "wilderness", "coastal"):
        by_area[area_key] = _normalize_fixture_list(raw.get(area_key), non_city_specs)
    return by_area


FIXTURE_SPECS_BY_AREA = load_fixture_specs()


def fixture_specs_for_area(area_type):
    area = str(area_type or "").strip().lower() or "city"
    if area == "city":
        return FIXTURE_SPECS_BY_AREA.get("city", DEFAULT_CITY_FIXTURE_SPECS)
    if area in {"frontier", "wilderness", "coastal"}:
        return FIXTURE_SPECS_BY_AREA.get(area, FIXTURE_SPECS_BY_AREA.get("non_city", DEFAULT_NON_CITY_FIXTURE_SPECS))
    return FIXTURE_SPECS_BY_AREA.get("non_city", DEFAULT_NON_CITY_FIXTURE_SPECS)


def _adjacent_positions(x, y):
    return (
        (int(x) + 1, int(y)),
        (int(x) - 1, int(y)),
        (int(x), int(y) + 1),
        (int(x), int(y) - 1),
    )


def _entry_positions_in_chunk(sim, origin_x, origin_y, chunk_size):
    entry_positions = set()
    min_x = int(origin_x)
    max_x = int(origin_x) + int(chunk_size) - 1
    min_y = int(origin_y)
    max_y = int(origin_y) + int(chunk_size) - 1

    for prop in sim.properties.values():
        if str(prop.get("kind", "")).strip().lower() != "building":
            continue
        metadata = prop.get("metadata")
        if not isinstance(metadata, dict):
            continue
        entry = metadata.get("entry")
        if not isinstance(entry, dict):
            continue
        try:
            ex = int(entry.get("x"))
            ey = int(entry.get("y"))
            ez = int(entry.get("z", prop.get("z", 0)))
        except (TypeError, ValueError):
            continue
        if ez != 0:
            continue
        if min_x <= ex <= max_x and min_y <= ey <= max_y:
            entry_positions.add((ex, ey))
    return entry_positions


def _candidate_buckets(sim, origin_x, origin_y, chunk_size):
    origin_x = int(origin_x)
    origin_y = int(origin_y)
    chunk_size = int(chunk_size)
    entry_positions = _entry_positions_in_chunk(sim, origin_x, origin_y, chunk_size)
    edge_margin = 2

    buckets = {
        "path_side": [],
        "path_tile": [],
        "entry_side": [],
        "street_side": [],
        "edge": [],
        "open": [],
    }

    for y in range(origin_y + 1, origin_y + chunk_size - 1):
        for x in range(origin_x + 1, origin_x + chunk_size - 1):
            tile = sim.tilemap.tile_at(x, y, 0)
            if not tile or not tile.walkable:
                continue
            if sim.property_covering(x, y, 0):
                continue

            glyph = str(tile.glyph)[:1] or "."
            on_path = glyph in PATH_GLYPHS
            near_path = False
            near_entry = (x, y) in entry_positions
            near_building = False
            for nx, ny in _adjacent_positions(x, y):
                ntile = sim.tilemap.tile_at(nx, ny, 0)
                if ntile and (str(ntile.glyph)[:1] or ".") in PATH_GLYPHS:
                    near_path = True
                if (nx, ny) in entry_positions:
                    near_entry = True
                nprop = sim.property_covering(nx, ny, 0)
                if nprop and str(nprop.get("kind", "")).strip().lower() == "building":
                    near_building = True

            near_edge = (
                x <= origin_x + edge_margin
                or x >= origin_x + chunk_size - 1 - edge_margin
                or y <= origin_y + edge_margin
                or y >= origin_y + chunk_size - 1 - edge_margin
            )

            if near_path and not on_path:
                buckets["path_side"].append((x, y))
            if on_path:
                buckets["path_tile"].append((x, y))
            if near_entry:
                buckets["entry_side"].append((x, y))
            if near_building and not on_path:
                buckets["street_side"].append((x, y))
            if near_edge:
                buckets["edge"].append((x, y))
            buckets["open"].append((x, y))

    return buckets


def _weighted_spec_choice(rng, specs):
    total = 0.0
    weighted = []
    for spec in specs:
        try:
            weight = max(0.0, float(spec.get("weight", 1)))
        except (TypeError, ValueError):
            weight = 1.0
        total += weight
        weighted.append((spec, weight))

    if total <= 0.0:
        return specs[0]

    pick = rng.uniform(0.0, total)
    running = 0.0
    for spec, weight in weighted:
        running += weight
        if pick <= running:
            return spec
    return weighted[-1][0]


def _reserve_position(position, buckets):
    for pool in buckets.values():
        while True:
            try:
                pool.remove(position)
            except ValueError:
                break


def _pick_position_for_spec(spec, buckets, rng):
    priorities = tuple(spec.get("priorities", ("open",)))
    for bucket_name in priorities:
        pool = buckets.get(bucket_name, ())
        if pool:
            return pool[rng.randrange(len(pool))]
    fallback = buckets.get("open", ())
    if fallback:
        return fallback[rng.randrange(len(fallback))]
    return None


def _build_fixture_metadata(spec, rng, area_type):
    kind = str(spec.get("kind", "fixture")).strip().lower() or "fixture"
    public_default = kind == "fixture"
    public = bool(spec.get("public", public_default))
    finance_services = tuple(spec.get("finance_services", ()))
    cost_min = 90 if kind == "fixture" else 120
    cost_max = 260 if kind == "fixture" else 320

    return {
        "archetype": str(spec.get("id", "fixture")).strip().lower() or "fixture",
        "fixture_type": str(spec.get("id", "fixture")).strip().lower() or "fixture",
        "display_glyph": str(spec.get("glyph", "f"))[:1] or "f",
        "display_color": str(spec.get("color", "property_fixture" if kind == "fixture" else "property_asset")),
        "cover_kind": str(spec.get("cover_kind", "low")).strip().lower() or "low",
        "cover_value": float(spec.get("cover_value", 0.35)),
        "infrastructure_family": str(spec.get("family", area_type or "city")).strip().lower() or "city",
        "public": public,
        "finance_services": list(finance_services),
        "purchase_cost": rng.randint(cost_min, cost_max),
        "light_enabled": bool(spec.get("light_enabled", False)),
        "light_radius": int(max(0, spec.get("light_radius", 0))),
        "light_intensity": float(max(0.0, min(1.0, spec.get("light_intensity", 0.0)))),
        "light_phases": list(spec.get("light_phases", ())),
    }


def generate_chunk_fixture_records(sim, chunk, rng, origin_x, origin_y, chunk_size, target_count):
    """Generate deterministic fixture/property records for one chunk."""
    district = chunk.get("district", {}) if isinstance(chunk, dict) else {}
    area_type = str(district.get("area_type", "city")).strip().lower() or "city"
    specs = fixture_specs_for_area(area_type)
    target_count = int(max(0, target_count))
    if target_count <= 0:
        return []

    buckets = _candidate_buckets(sim, origin_x, origin_y, chunk_size)
    if not buckets.get("open"):
        return []

    records = []
    attempts = 0
    attempt_limit = max(16, target_count * 8)
    while len(records) < target_count and attempts < attempt_limit:
        attempts += 1
        spec = _weighted_spec_choice(rng, specs)
        position = _pick_position_for_spec(spec, buckets, rng)
        if position is None:
            break
        _reserve_position(position, buckets)

        kind = str(spec.get("kind", "fixture")).strip().lower() or "fixture"
        metadata = _build_fixture_metadata(spec, rng, area_type=area_type)
        owner_tag = "public" if bool(metadata.get("public")) else "city"
        records.append({
            "name": str(spec.get("name", "Fixture")).strip() or "Fixture",
            "kind": kind,
            "x": int(position[0]),
            "y": int(position[1]),
            "z": 0,
            "owner_tag": owner_tag,
            "metadata": metadata,
            "archetype": metadata.get("archetype"),
        })

    return records
