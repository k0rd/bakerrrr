import json
import random
from pathlib import Path

from game.content_warnings import warn_content_fallback
from game.property_keys import ensure_property_lock_metadata


VEHICLE_DATA_PATH = Path(__file__).resolve().parent / "vehicles.json"

DEFAULT_CATALOG = {
    "vehicle_symbol": "&",
    "makes": (
        "Alder",
        "Brassline",
        "Cinder",
        "Drift",
        "Harbor",
        "Ironway",
        "Northgate",
        "Redline",
        "Stonecut",
        "Transit",
    ),
    "models": (
        {
            "name": "Runner",
            "vehicle_class": "sedan",
            "power": (4, 7),
            "durability": (5, 8),
            "fuel_efficiency": (6, 9),
            "fuel_capacity": (56, 74),
            "base_price": 560,
        },
    ),
    "quality_profiles": {
        "used": {
            "price_mult": (0.62, 0.86),
            "durability_shift": (-2, 0),
            "fuel_mult": (0.45, 0.78),
        },
        "new": {
            "price_mult": (1.18, 1.34),
            "durability_shift": (0, 1),
            "fuel_mult": (0.88, 1.0),
        },
    },
    "service_archetypes": {
        "fuel": (
            "auto_garage",
            "motor_pool",
            "freight_depot",
            "relay_post",
            "roadhouse",
            "dock_shack",
            "pump_house",
            "survey_post",
            "lookout_post",
            "ferry_post",
            "tide_station",
            "beacon_house",
        ),
        "repair": (
            "auto_garage",
            "motor_pool",
            "breaker_yard",
            "drydock_yard",
            "truck_stop",
            "work_shed",
            "salvage_camp",
        ),
        "new_sales": (
            "auto_garage",
            "motor_pool",
            "freight_depot",
        ),
        "used_sales": (
            "auto_garage",
            "chop_shop",
            "junk_market",
            "roadhouse",
            "salvage_camp",
            "work_shed",
            "survey_post",
        ),
        "fetch": (
            "truck_stop",
            "auto_garage",
            "roadhouse",
            "breaker_yard",
        ),
    },
}


def _clamp_int(value, lo, hi, default):
    try:
        ivalue = int(value)
    except (TypeError, ValueError):
        ivalue = int(default)
    return max(int(lo), min(int(hi), ivalue))


def _clamp_float(value, lo, hi, default):
    try:
        fvalue = float(value)
    except (TypeError, ValueError):
        fvalue = float(default)
    return max(float(lo), min(float(hi), fvalue))


def _int_pair(raw, default, lo=0, hi=9999):
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        low = _clamp_int(raw[0], lo, hi, default[0])
        high = _clamp_int(raw[1], low, hi, default[1])
        return (low, high)
    return (int(default[0]), int(default[1]))


def _float_pair(raw, default):
    if isinstance(raw, (list, tuple)) and len(raw) >= 2:
        lo = _clamp_float(raw[0], 0.01, 10.0, default[0])
        hi = _clamp_float(raw[1], lo, 10.0, default[1])
        return (lo, hi)
    return (float(default[0]), float(default[1]))


def _string_list(raw, fallback):
    if not isinstance(raw, (list, tuple)):
        return tuple(str(item).strip() for item in fallback if str(item).strip())
    values = [str(item).strip() for item in raw if str(item).strip()]
    if not values:
        values = [str(item).strip() for item in fallback if str(item).strip()]
    return tuple(values)


def load_vehicle_catalog(path=VEHICLE_DATA_PATH):
    raw = None
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, OSError, json.JSONDecodeError) as exc:
        warn_content_fallback(path, "built-in vehicle catalog defaults", exc=exc)
        raw = None

    if raw is not None and not isinstance(raw, dict):
        warn_content_fallback(path, "built-in vehicle catalog defaults", problem="top-level JSON must be an object")
    if not isinstance(raw, dict):
        raw = {}

    symbol = str(raw.get("vehicle_symbol", DEFAULT_CATALOG["vehicle_symbol"]))[:1] or DEFAULT_CATALOG["vehicle_symbol"]
    makes = _string_list(raw.get("makes"), DEFAULT_CATALOG["makes"])

    models = []
    for entry in raw.get("models", []):
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        fallback = DEFAULT_CATALOG["models"][0]
        model = {
            "name": name,
            "vehicle_class": str(entry.get("vehicle_class", fallback["vehicle_class"])) or fallback["vehicle_class"],
            "power": _int_pair(entry.get("power"), fallback["power"]),
            "durability": _int_pair(entry.get("durability"), fallback["durability"]),
            "fuel_efficiency": _int_pair(entry.get("fuel_efficiency"), fallback["fuel_efficiency"]),
            "fuel_capacity": _int_pair(entry.get("fuel_capacity"), fallback["fuel_capacity"]),
            "base_price": _clamp_int(entry.get("base_price"), 100, 5000, fallback["base_price"]),
        }
        models.append(model)

    if not models:
        models = [dict(DEFAULT_CATALOG["models"][0])]

    quality_profiles = {}
    raw_quality = raw.get("quality_profiles") if isinstance(raw.get("quality_profiles"), dict) else {}
    for key, fallback in DEFAULT_CATALOG["quality_profiles"].items():
        candidate = raw_quality.get(key, {}) if isinstance(raw_quality.get(key), dict) else {}
        quality_profiles[key] = {
            "price_mult": _float_pair(candidate.get("price_mult"), fallback["price_mult"]),
            "durability_shift": _int_pair(candidate.get("durability_shift"), fallback["durability_shift"], lo=-9999),
            "fuel_mult": _float_pair(candidate.get("fuel_mult"), fallback["fuel_mult"]),
        }

    services = raw.get("service_archetypes") if isinstance(raw.get("service_archetypes"), dict) else {}
    service_archetypes = {
        "fuel": _string_list(services.get("fuel"), DEFAULT_CATALOG["service_archetypes"]["fuel"]),
        "repair": _string_list(services.get("repair"), DEFAULT_CATALOG["service_archetypes"]["repair"]),
        "new_sales": _string_list(services.get("new_sales"), DEFAULT_CATALOG["service_archetypes"]["new_sales"]),
        "used_sales": _string_list(services.get("used_sales"), DEFAULT_CATALOG["service_archetypes"]["used_sales"]),
        "fetch": _string_list(services.get("fetch"), DEFAULT_CATALOG["service_archetypes"]["fetch"]),
    }

    return {
        "vehicle_symbol": symbol,
        "makes": makes,
        "models": tuple(models),
        "quality_profiles": quality_profiles,
        "service_archetypes": service_archetypes,
    }


CATALOG = load_vehicle_catalog()

USED_VEHICLE_PAINT_KEYS = (
    "vehicle_paint_red",
    "vehicle_paint_blue",
    "vehicle_paint_green",
    "vehicle_paint_white",
    "vehicle_paint_black",
    "vehicle_paint_teal",
    "vehicle_paint_rust",
    "vehicle_paint_brown",
)

NEW_VEHICLE_PAINT_KEYS = (
    "vehicle_paint_red",
    "vehicle_paint_blue",
    "vehicle_paint_green",
    "vehicle_paint_white",
    "vehicle_paint_teal",
    "vehicle_paint_yellow",
)


def vehicle_symbol(catalog=None):
    source = catalog if isinstance(catalog, dict) else CATALOG
    return str(source.get("vehicle_symbol", "&"))[:1] or "&"


def roll_vehicle_paint_key(rng, quality="used"):
    quality = str(quality or "used").strip().lower()
    pool = NEW_VEHICLE_PAINT_KEYS if quality == "new" else USED_VEHICLE_PAINT_KEYS
    return str(rng.choice(tuple(pool))) if pool else "vehicle_parked"


def vehicle_services_for_archetype(archetype, catalog=None):
    source = catalog if isinstance(catalog, dict) else CATALOG
    profile = source.get("service_archetypes", {}) if isinstance(source, dict) else {}
    if not isinstance(profile, dict):
        profile = {}

    archetype = str(archetype or "").strip().lower()
    if not archetype:
        return ()

    fuel_set = set(str(item).strip().lower() for item in profile.get("fuel", ()) if str(item).strip())
    repair_set = set(str(item).strip().lower() for item in profile.get("repair", ()) if str(item).strip())
    new_set = set(str(item).strip().lower() for item in profile.get("new_sales", ()) if str(item).strip())
    used_set = set(str(item).strip().lower() for item in profile.get("used_sales", ()) if str(item).strip())

    fetch_set = set(str(item).strip().lower() for item in profile.get("fetch", ()) if str(item).strip())

    services = []
    if archetype in fuel_set:
        services.append("fuel")
    if archetype in repair_set:
        services.append("repair")
    if archetype in new_set:
        services.append("vehicle_sales_new")
    if archetype in used_set:
        services.append("vehicle_sales_used")
    if archetype in fetch_set:
        services.append("vehicle_fetch")
    return tuple(services)


def _roll_stat(rng, stat_range, quality_shift=0):
    lo = int(stat_range[0])
    hi = int(max(lo, stat_range[1]))
    value = rng.randint(lo, hi) + int(quality_shift)
    return _clamp_int(value, 1, 10, lo)


def _roll_int(rng, int_range):
    lo = int(int_range[0])
    hi = int(max(lo, int_range[1]))
    return rng.randint(lo, hi)


def _roll_float(rng, float_range):
    lo = float(float_range[0])
    hi = float(max(lo, float_range[1]))
    return float(rng.uniform(lo, hi))


def roll_vehicle_profile(rng, quality="used", catalog=None):
    source = catalog if isinstance(catalog, dict) else CATALOG
    models = list(source.get("models", ()))
    if not models:
        models = list(DEFAULT_CATALOG["models"])

    model = dict(rng.choice(models))
    make = rng.choice(tuple(source.get("makes", DEFAULT_CATALOG["makes"])))
    quality = str(quality or "used").strip().lower()
    if quality not in {"new", "used"}:
        quality = "used"

    quality_profiles = source.get("quality_profiles", DEFAULT_CATALOG["quality_profiles"])
    quality_profile = quality_profiles.get(quality, DEFAULT_CATALOG["quality_profiles"][quality])

    durability_shift = _roll_int(rng, quality_profile.get("durability_shift", (0, 0)))
    power = _roll_stat(rng, model.get("power", (4, 7)), quality_shift=0)
    durability = _roll_stat(rng, model.get("durability", (5, 8)), quality_shift=durability_shift)
    fuel_efficiency = _roll_stat(rng, model.get("fuel_efficiency", (6, 9)), quality_shift=0)
    fuel_capacity = _roll_int(rng, model.get("fuel_capacity", (56, 74)))

    fuel_mult = _roll_float(rng, quality_profile.get("fuel_mult", (1.0, 1.0)))
    fuel = int(round(float(fuel_capacity) * fuel_mult))
    if quality == "new":
        fuel = max(fuel, int(round(float(fuel_capacity) * 0.88)))
    fuel = _clamp_int(fuel, 0, fuel_capacity, fuel_capacity)

    base_price = _clamp_int(model.get("base_price", 520), 100, 5000, 520)
    price_mult = _roll_float(rng, quality_profile.get("price_mult", (1.0, 1.0)))
    price = _clamp_int(int(round(base_price * price_mult)), 80, 10000, base_price)

    return {
        "quality": quality,
        "make": str(make),
        "model": str(model.get("name", "Runner")),
        "vehicle_class": str(model.get("vehicle_class", "sedan")),
        "power": power,
        "durability": durability,
        "fuel_efficiency": fuel_efficiency,
        "fuel_capacity": fuel_capacity,
        "fuel": fuel,
        "price": price,
        "glyph": vehicle_symbol(source),
    }


def vehicle_metadata(
    profile,
    chunk=None,
    owner_tag="public",
    display_color="vehicle_parked",
    locked=False,
    key_id=None,
    key_label=None,
    lock_tier=1,
):
    data = dict(profile or {})
    chunk_value = None
    if isinstance(chunk, (list, tuple)) and len(chunk) == 2:
        chunk_value = (int(chunk[0]), int(chunk[1]))

    fuel_capacity = _clamp_int(data.get("fuel_capacity", 60), 20, 220, 60)
    fuel = _clamp_int(data.get("fuel", fuel_capacity), 0, fuel_capacity, fuel_capacity)
    metadata = {
        "archetype": "vehicle",
        "vehicle_quality": str(data.get("quality", "used")).strip().lower() or "used",
        "vehicle_paint": str(data.get("paint", "")).strip(),
        "vehicle_make": str(data.get("make", "Unknown")).strip() or "Unknown",
        "vehicle_model": str(data.get("model", "Vehicle")).strip() or "Vehicle",
        "vehicle_class": str(data.get("vehicle_class", "sedan")).strip().lower() or "sedan",
        "power": _clamp_int(data.get("power", 5), 1, 10, 5),
        "durability": _clamp_int(data.get("durability", 5), 1, 10, 5),
        "fuel_efficiency": _clamp_int(data.get("fuel_efficiency", 5), 1, 10, 5),
        "fuel_capacity": fuel_capacity,
        "fuel": fuel,
        "purchase_cost": _clamp_int(data.get("price", 500), 80, 10000, 500),
        "display_glyph": str(data.get("glyph", vehicle_symbol()))[:1] or vehicle_symbol(),
        "display_color": str(display_color or "vehicle_parked").strip() or "vehicle_parked",
        "cover_kind": "low",
        "cover_value": 0.46,
        "public": bool(str(owner_tag).strip().lower() == "public"),
        "vehicle_usable": True,
        "vehicle_owner_tag": str(owner_tag or "public").strip().lower() or "public",
        "chunk": chunk_value,
    }
    return ensure_property_lock_metadata(
        metadata,
        property_name=f"{metadata['vehicle_make']} {metadata['vehicle_model']}",
        property_kind="vehicle",
        locked=locked,
        key_id=key_id,
        key_label=key_label,
        lock_tier=lock_tier,
    )


def _is_path_tile(sim, x, y, z=0):
    tile = sim.tilemap.tile_at(int(x), int(y), int(z))
    if not tile:
        return False
    glyph = str(tile.glyph)[:1]
    return glyph in {"=", ":"}


def _vehicle_candidate_tiles(sim, origin_x, origin_y, chunk_size):
    tiles = []
    for y in range(int(origin_y) + 1, int(origin_y) + int(chunk_size) - 1):
        for x in range(int(origin_x) + 1, int(origin_x) + int(chunk_size) - 1):
            if sim.property_at(x, y, 0):
                continue
            if sim.structure_at(x, y, 0):
                continue
            tile = sim.tilemap.tile_at(x, y, 0)
            if not tile or not tile.walkable:
                continue

            path_score = 0
            for ny in range(y - 1, y + 2):
                for nx in range(x - 1, x + 2):
                    if nx == x and ny == y:
                        continue
                    if _is_path_tile(sim, nx, ny, z=0):
                        if str(sim.tilemap.tile_at(nx, ny, 0).glyph)[:1] == "=":
                            path_score = max(path_score, 3)
                        else:
                            path_score = max(path_score, 2)
            open_score = 1
            for ny in range(y - 1, y + 2):
                for nx in range(x - 1, x + 2):
                    if sim.structure_at(nx, ny, 0):
                        open_score = 0
                        break
                if open_score == 0:
                    break

            tiles.append((path_score + open_score, x, y))
    return tiles


def generate_chunk_vehicle_records(
    sim,
    chunk,
    rng,
    origin_x,
    origin_y,
    chunk_size,
    target_count=None,
    catalog=None,
):
    source = catalog if isinstance(catalog, dict) else CATALOG
    area_type = str(chunk.get("district", {}).get("area_type", "city")).strip().lower() or "city"

    if target_count is None:
        if area_type == "city":
            target_count = max(1, int(chunk_size) // 12)
        else:
            target_count = 1 if rng.random() < 0.55 else 0

    target_count = max(0, int(target_count))
    if target_count <= 0:
        return []

    candidates = _vehicle_candidate_tiles(sim, origin_x=origin_x, origin_y=origin_y, chunk_size=chunk_size)
    if not candidates:
        return []

    rng.shuffle(candidates)
    candidates.sort(key=lambda row: (-int(row[0]), int(row[2]), int(row[1])))

    selected = []
    for _score, x, y in candidates:
        if len(selected) >= target_count:
            break
        if any(abs(x - sx) + abs(y - sy) < 4 for sx, sy in selected):
            continue
        selected.append((x, y))

    records = []
    chunk_coord = (int(chunk.get("cx", 0)), int(chunk.get("cy", 0)))
    for index, (x, y) in enumerate(selected):
        near_road = any(
            _is_path_tile(sim, x + dx, y + dy, z=0)
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            if not (dx == 0 and dy == 0)
        )
        quality = "used"
        if area_type == "city" and near_road and rng.random() < 0.28:
            quality = "new"

        profile = roll_vehicle_profile(rng, quality=quality, catalog=source)
        paint_key = roll_vehicle_paint_key(rng, quality=quality)
        profile["paint"] = paint_key
        vehicle_token = f"veh:{chunk_coord[0]}:{chunk_coord[1]}:{index}"
        owner_tag = "public" if rng.random() < 0.18 else "private"
        locked = owner_tag != "public"
        lock_tier = 3 if quality == "new" else 2
        metadata = vehicle_metadata(
            profile,
            chunk=chunk_coord,
            owner_tag=owner_tag,
            display_color=paint_key,
            locked=locked,
            key_id=vehicle_token,
            key_label=f"{profile['make']} {profile['model']}",
            lock_tier=lock_tier,
        )
        metadata["vehicle_id"] = vehicle_token

        records.append({
            "name": f"{profile['make']} {profile['model']}",
            "kind": "vehicle",
            "x": int(x),
            "y": int(y),
            "z": 0,
            "owner_tag": owner_tag,
            "metadata": metadata,
        })

    return records
