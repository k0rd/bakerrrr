from engine.derived_facts import cached_derived_fact, derived_fact_revision
from game.property_access import (
    DEFAULT_START_HOUR,
    DEFAULT_TICKS_PER_HOUR,
    finance_services_for_property,
    property_apertures,
    property_is_open,
    property_is_public,
    property_is_storefront,
    site_services_for_property,
)
from game.components import Position, VehicleState
from game.system_support.fire_runtime import fire_state


PHASE_OUTDOOR_AMBIENT = {
    "night": 0.24,
    "dawn": 0.58,
    "day": 1.0,
    "dusk": 0.52,
}

_PHASE_WINDOWS = (
    ("dawn", 5, 8),
    ("day", 8, 18),
    ("dusk", 18, 21),
)

_APERTURE_KIND_SCALE = {
    "window": 1.0,
    "skylight": 1.0,
    "door": 0.75,
    "service_door": 0.85,
    "employee_door": 0.85,
    "side_door": 0.85,
}
_LIGHT_PHASES = {"dawn", "dusk", "night"}
_APERTURE_LOCAL_LIGHT_KIND_SCALE = {
    "window": 1.0,
    "skylight": 0.95,
    "door": 0.72,
    "service_door": 0.84,
    "employee_door": 0.8,
    "side_door": 0.78,
}

_FIRE_INTENSITY_PROFILE = {
    1: {"radius": 2, "intensity": 0.34},
    2: {"radius": 3, "intensity": 0.56},
    3: {"radius": 4, "intensity": 0.78},
}

LIGHT_COLOR_PROFILES = {
    "street_warm": {"rgb": (255, 190, 92), "priority": 1, "pulse": ""},
    "security_cool": {"rgb": (96, 172, 255), "priority": 2, "pulse": ""},
    "storefront_warm": {"rgb": (255, 214, 142), "priority": 1, "pulse": ""},
    "clinic_soft": {"rgb": (182, 255, 218), "priority": 1, "pulse": ""},
    "casino_neon": {"rgb": (211, 91, 255), "priority": 2, "pulse": "neon"},
    "fire_orange": {"rgb": (255, 116, 45), "priority": 3, "pulse": "warm"},
    "headlight_white": {"rgb": (255, 246, 216), "priority": 2, "pulse": ""},
    "emergency_red": {"rgb": (255, 62, 70), "priority": 4, "pulse": "emergency"},
    "underground_green": {"rgb": (94, 226, 168), "priority": 1, "pulse": ""},
    "ritual_violet": {"rgb": (168, 116, 255), "priority": 2, "pulse": "slow"},
    "accumulator_glow": {"rgb": (112, 244, 190), "priority": 2, "pulse": ""},
    "accumulator_glow_seaglass": {"rgb": (104, 236, 200), "priority": 2, "pulse": ""},
    "accumulator_glow_soft_green": {"rgb": (128, 240, 178), "priority": 2, "pulse": ""},
    "indicator_glow_amber": {"rgb": (238, 198, 108), "priority": 1, "pulse": ""},
    "indicator_glow_blue": {"rgb": (106, 204, 238), "priority": 1, "pulse": ""},
    "indicator_glow_green": {"rgb": (138, 222, 126), "priority": 1, "pulse": ""},
    "indicator_glow_violet": {"rgb": (190, 148, 236), "priority": 1, "pulse": ""},
    "indicator_glow_rose": {"rgb": (232, 144, 184), "priority": 1, "pulse": ""},
}

_FIXTURE_LIGHT_PROFILE_HINTS = {
    "streetlamp": "street_warm",
    "trail_lamp": "street_warm",
    "bus_stop": "security_cool",
    "atm_kiosk": "security_cool",
    "claim_terminal": "security_cool",
    "vending_machine": "security_cool",
    "charging_pillar": "security_cool",
    "security_camera": "security_cool",
    "storm_siren": "emergency_red",
    "campfire_ring": "fire_orange",
}

_BUILDING_LIGHT_PROFILE_HINTS = {
    "clinic": "clinic_soft",
    "backroom_clinic": "clinic_soft",
    "hospital": "clinic_soft",
    "pharmacy": "clinic_soft",
    "herbalist_shop": "clinic_soft",
    "herbalist_camp": "clinic_soft",
    "casino": "casino_neon",
    "arcade": "casino_neon",
    "game_room": "casino_neon",
    "tavern": "storefront_warm",
    "bar": "storefront_warm",
    "roadhouse": "storefront_warm",
    "police_station": "security_cool",
    "security_office": "security_cool",
    "justice_station": "security_cool",
    "jail": "security_cool",
    "courthouse": "security_cool",
    "watch_post": "security_cool",
    "firewatch_tower": "security_cool",
    "pump_house": "underground_green",
    "access_tunnel_network": "underground_green",
    "metro_underpass": "underground_green",
    "storm_drain": "underground_green",
    "service_basement": "underground_green",
    "utility_corridor": "underground_green",
    "maintenance_tunnel": "underground_green",
}

_SERVICE_LIGHT_PROFILE_HINTS = {
    "medical_care": "clinic_soft",
    "herbal_care": "clinic_soft",
    "herbal_prepare": "clinic_soft",
    "banking": "security_cool",
    "insurance": "security_cool",
    "casino_games": "casino_neon",
    "slots": "casino_neon",
    "blackjack": "casino_neon",
    "roulette": "casino_neon",
}

GLARE_RECOVERY_TICKS = 18
GLARE_EXPOSURE_THRESHOLD = 0.44
GLARE_LOW_AMBIENT_THRESHOLD = 0.46


def _property_metadata(prop):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _clamp_unit(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    return max(0.0, min(1.0, number))


def _clamp_rgb_channel(value, default=255):
    try:
        return max(0, min(255, int(round(float(value)))))
    except (TypeError, ValueError):
        return int(default)


def _profile_row(profile_name, default_profile="storefront_warm"):
    name = str(profile_name or "").strip().lower()
    row = LIGHT_COLOR_PROFILES.get(name)
    if isinstance(row, dict):
        return name, row
    fallback_name = str(default_profile or "storefront_warm").strip().lower() or "storefront_warm"
    fallback = LIGHT_COLOR_PROFILES.get(fallback_name) or LIGHT_COLOR_PROFILES["storefront_warm"]
    return fallback_name if fallback_name in LIGHT_COLOR_PROFILES else "storefront_warm", fallback


def _normalize_light_rgb(value, *, profile_name=None, default_profile="storefront_warm"):
    if isinstance(value, (list, tuple)) and len(value) >= 3:
        return (
            _clamp_rgb_channel(value[0]),
            _clamp_rgb_channel(value[1]),
            _clamp_rgb_channel(value[2]),
        )

    if isinstance(value, str):
        text = value.strip().lower()
        if text in LIGHT_COLOR_PROFILES:
            return tuple(int(channel) for channel in LIGHT_COLOR_PROFILES[text]["rgb"])
        if text.startswith("#") and len(text) == 7:
            try:
                return (
                    int(text[1:3], 16),
                    int(text[3:5], 16),
                    int(text[5:7], 16),
                )
            except ValueError:
                pass

    _name, row = _profile_row(profile_name, default_profile=default_profile)
    return tuple(int(channel) for channel in row["rgb"])


def _int_or_default(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _float_or_default(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _default_light_profile_for_property(prop, default_profile="storefront_warm"):
    if not isinstance(prop, dict):
        return str(default_profile or "storefront_warm")
    metadata = _property_metadata(prop)
    kind = str(prop.get("kind", "") or "").strip().lower()
    archetype = str(metadata.get("archetype") or metadata.get("fixture_type") or prop.get("archetype") or "").strip().lower()
    fixture_kind = str(metadata.get("fixture_kind", "") or "").strip().lower()

    if kind == "vehicle":
        restricted = str(metadata.get("restricted_use", "") or "").strip().lower()
        if restricted == "justice" or "police" in archetype or "justice" in archetype:
            return "security_cool"
        return "headlight_white"

    if kind in {"fixture", "asset"}:
        if archetype in _FIXTURE_LIGHT_PROFILE_HINTS:
            return _FIXTURE_LIGHT_PROFILE_HINTS[archetype]
        if fixture_kind in {"electronic", "camera", "alarm"}:
            return "security_cool"
        return "street_warm"

    if kind == "building":
        if archetype in _BUILDING_LIGHT_PROFILE_HINTS:
            return _BUILDING_LIGHT_PROFILE_HINTS[archetype]
        for service in tuple(finance_services_for_property(prop)) + tuple(site_services_for_property(prop)):
            service_key = str(service or "").strip().lower()
            if service_key in _SERVICE_LIGHT_PROFILE_HINTS:
                return _SERVICE_LIGHT_PROFILE_HINTS[service_key]
        if property_is_storefront(prop):
            return "storefront_warm"
        if property_is_public(prop):
            return "street_warm"

    return str(default_profile or "storefront_warm")


def _light_visual_fields(metadata=None, *, prop=None, default_profile="storefront_warm"):
    metadata = metadata if isinstance(metadata, dict) else {}
    default_profile = _default_light_profile_for_property(prop, default_profile=default_profile)
    profile_name = str(metadata.get("light_profile") or metadata.get("profile") or default_profile).strip().lower()
    profile_name, row = _profile_row(profile_name, default_profile=default_profile)
    rgb = _normalize_light_rgb(metadata.get("light_color"), profile_name=profile_name, default_profile=profile_name)
    pulse = str(metadata.get("light_pulse", row.get("pulse", "")) or "").strip().lower()
    priority = _int_or_default(metadata.get("light_priority", row.get("priority", 0)), row.get("priority", 0))
    priority = max(0, min(8, priority))
    return {
        "light_profile": profile_name,
        "light_color": [int(rgb[0]), int(rgb[1]), int(rgb[2])],
        "light_pulse": pulse,
        "light_priority": int(priority),
    }


def _clock_config(sim):
    world_traits = getattr(sim, "world_traits", {}) if sim is not None else {}
    clock = world_traits.get("clock", {}) if isinstance(world_traits, dict) else {}
    if not isinstance(clock, dict):
        clock = {}

    try:
        start_hour = int(clock.get("start_hour", DEFAULT_START_HOUR))
    except (TypeError, ValueError):
        start_hour = DEFAULT_START_HOUR

    try:
        ticks_per_hour = int(clock.get("ticks_per_hour", DEFAULT_TICKS_PER_HOUR))
    except (TypeError, ValueError):
        ticks_per_hour = DEFAULT_TICKS_PER_HOUR

    return int(start_hour) % 24, max(60, int(ticks_per_hour))


def phase_for_hour(hour):
    hour = int(hour) % 24
    for phase, start_hour, end_hour in _PHASE_WINDOWS:
        if start_hour <= hour < end_hour:
            return phase
    return "night"


def clock_snapshot(sim):
    tick = max(0, int(getattr(sim, "tick", 0)))
    start_hour, ticks_per_hour = _clock_config(sim)
    total_minutes = ((start_hour * 60) + ((tick * 60) // ticks_per_hour)) % (24 * 60)
    hour = (total_minutes // 60) % 24
    minute = total_minutes % 60
    phase = phase_for_hour(hour)
    outdoor_ambient = PHASE_OUTDOOR_AMBIENT.get(phase, PHASE_OUTDOOR_AMBIENT["day"])
    return {
        "tick": tick,
        "hour": int(hour),
        "minute": int(minute),
        "time_label": f"{int(hour):02d}:{int(minute):02d}",
        "phase": phase,
        "outdoor_ambient": float(outdoor_ambient),
    }


def _structure_at(sim, x, y, z=0):
    if sim is None or not hasattr(sim, "structure_at"):
        return None
    try:
        return sim.structure_at(int(x), int(y), int(z))
    except (TypeError, ValueError):
        return None


def _door_open_at(sim, x, y, z=0):
    if sim is None:
        return False
    helper = getattr(sim, "door_state_at", None)
    state = None
    if callable(helper):
        try:
            state = helper(int(x), int(y), int(z))
        except (TypeError, ValueError):
            state = None
    if isinstance(state, dict):
        kind = str(state.get("kind", "door") or "door").strip().lower() or "door"
        if kind in {"door", "side_door", "service_door", "employee_door"}:
            return bool(state.get("open", False))

    tile = sim.tilemap.tile_at(int(x), int(y), int(z)) if hasattr(sim, "tilemap") else None
    return bool(tile and str(getattr(tile, "glyph", "") or "")[:1] == "'")


def _aperture_allows_light(sim, aperture, *, x=None, y=None, z=0):
    if not isinstance(aperture, dict):
        return False
    kind = str(aperture.get("kind", "door") or "door").strip().lower() or "door"
    if kind in {"door", "side_door", "service_door", "employee_door"}:
        try:
            ax = int(aperture.get("x", x))
            ay = int(aperture.get("y", y))
            az = int(aperture.get("z", z))
        except (TypeError, ValueError):
            return False
        return _door_open_at(sim, ax, ay, az)
    return True


def _tile_aperture_allows_light(sim, x, y, z=0):
    tile = sim.tilemap.tile_at(int(x), int(y), int(z)) if sim is not None and hasattr(sim, "tilemap") else None
    if not tile:
        return False
    glyph = str(getattr(tile, "glyph", "") or "")[:1]
    if glyph == "'":
        return True
    if glyph in {'"', "/"}:
        return True
    if glyph != "+":
        return False
    return _door_open_at(sim, x, y, z)


def is_interior_tile(sim, x, y, z=0):
    structure = _structure_at(sim, x, y, z)
    if not isinstance(structure, dict):
        return False
    return bool(
        structure.get("building_id")
        or structure.get("name")
        or structure.get("site_kind")
    )


def _neighbor_aperture_bonus(sim, x, y, z=0):
    try:
        x = int(x)
        y = int(y)
        z = int(z)
    except (TypeError, ValueError):
        return 0.0

    tilemap = getattr(sim, "tilemap", None)
    signature_helper = getattr(tilemap, "visibility_signature_for_region", None)
    if callable(signature_helper):
        topology_signature = signature_helper(x, y, z, 2)
    else:
        topology_signature = int(getattr(tilemap, "visibility_revision", 0) or 0)
    state = lighting_state(sim)
    bleed_cache = state.get("aperture_bleed_cache")
    if not isinstance(bleed_cache, dict):
        bleed_cache = {}
        state["aperture_bleed_cache"] = bleed_cache
    cache_key = (x, y, z)
    cached = bleed_cache.get(cache_key)
    if isinstance(cached, tuple) and len(cached) == 2 and cached[0] == topology_signature:
        return float(cached[1])

    structure = _structure_at(sim, x, y, z)
    if not isinstance(structure, dict):
        bleed_cache[cache_key] = (topology_signature, 0.0)
        return 0.0

    strongest = 0.0
    apertures = structure.get("apertures", ())
    if isinstance(apertures, (list, tuple)):
        for aperture in apertures:
            if not isinstance(aperture, dict):
                continue
            try:
                ax = int(aperture.get("x"))
                ay = int(aperture.get("y"))
                az = int(aperture.get("z", z))
            except (TypeError, ValueError):
                continue
            if az != z:
                continue
            dist = abs(ax - x) + abs(ay - y)
            if dist > 2:
                continue
            if not _aperture_allows_light(sim, aperture, x=ax, y=ay, z=az):
                continue
            if dist == 0:
                strength = 1.0
            elif dist == 1:
                strength = 0.72
            else:
                strength = 0.38
            kind = str(aperture.get("kind", "door") or "door").strip().lower()
            strength *= _APERTURE_KIND_SCALE.get(kind, 0.8)
            if strength > strongest:
                strongest = strength

    if strongest >= 0.999:
        bleed_cache[cache_key] = (topology_signature, 1.0)
        return 1.0

    if _tile_aperture_allows_light(sim, x, y, z):
        strongest = max(strongest, 0.85)

    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
        if _tile_aperture_allows_light(sim, nx, ny, z):
            strongest = max(strongest, 0.6)

    result = _clamp_unit(strongest)
    if len(bleed_cache) >= 16384 and cache_key not in bleed_cache:
        bleed_cache.clear()
    bleed_cache[cache_key] = (topology_signature, result)
    return result


def _loaded_property_bounds(sim):
    if sim is None or not hasattr(sim, "world") or not hasattr(sim.world, "loaded_chunks"):
        return None

    loaded = getattr(sim.world, "loaded_chunks", {})
    if not isinstance(loaded, dict) or not loaded:
        return None

    chunk_size = max(1, int(getattr(sim, "chunk_size", 24)))
    xs = []
    ys = []
    for key in loaded.keys():
        if not isinstance(key, tuple) or len(key) != 2:
            continue
        try:
            cx = int(key[0])
            cy = int(key[1])
        except (TypeError, ValueError):
            continue
        xs.append(cx)
        ys.append(cy)

    if not xs or not ys:
        return None

    return (
        min(xs) * chunk_size,
        ((max(xs) + 1) * chunk_size) - 1,
        min(ys) * chunk_size,
        ((max(ys) + 1) * chunk_size) - 1,
    )


def _property_in_loaded_bounds(prop, bounds, margin=0):
    if bounds is None:
        return True

    try:
        x = int(prop.get("x"))
        y = int(prop.get("y"))
    except (AttributeError, TypeError, ValueError):
        return False

    min_x, max_x, min_y, max_y = bounds
    margin = max(0, int(margin))
    return (
        (min_x - margin) <= x <= (max_x + margin)
        and (min_y - margin) <= y <= (max_y + margin)
    )


def _active_power_cut_cache_key(sim, *, tick=None):
    power_cuts = getattr(sim, "fixture_power_cuts", None)
    if not isinstance(power_cuts, dict) or not power_cuts:
        return ()
    if tick is None:
        tick = int(getattr(sim, "tick", 0))

    active = []
    for prop_id, cut_until in power_cuts.items():
        try:
            until = int(cut_until)
        except (TypeError, ValueError):
            continue
        if until <= int(tick):
            continue
        pid = str(prop_id or "").strip()
        if not pid:
            continue
        active.append((pid, until))
    active.sort()
    return tuple(active)


def _active_fire_cache_key(sim):
    state = getattr(sim, "fire_state", None)
    if not isinstance(state, dict):
        return ()

    def build():
        cells = state.get("cells", {})
        if not isinstance(cells, dict) or not cells:
            return ()
        active = []
        for coord, cell in cells.items():
            if not isinstance(cell, dict):
                continue
            try:
                fire_intensity = int(cell.get("fire_intensity", 0) or 0)
            except (TypeError, ValueError):
                fire_intensity = 0
            if fire_intensity <= 0:
                continue
            try:
                x = int(coord[0])
                y = int(coord[1])
                z = int(coord[2])
            except (TypeError, ValueError, IndexError):
                continue
            active.append((x, y, z, fire_intensity))
        active.sort()
        return tuple(active)

    return cached_derived_fact(
        sim,
        "fire.active_lights",
        "all",
        build,
        domains=("fire_light",),
        max_entries=1,
    )


def _power_cut_active_at(sim, x, y, z=0, *, tick=None):
    power_cuts = getattr(sim, "fixture_power_cuts", None)
    if not isinstance(power_cuts, dict) or not power_cuts:
        return False
    if tick is None:
        tick = int(getattr(sim, "tick", 0))

    try:
        key = (int(x), int(y), int(z))
    except (TypeError, ValueError):
        return False

    anchor_index = getattr(sim, "property_anchor_index", {})
    cover_index = getattr(sim, "property_cover_index", {})
    for bucket in (anchor_index.get(key, ()), cover_index.get(key, ())):
        for prop_id in bucket:
            try:
                if int(power_cuts.get(prop_id, 0) or 0) > int(tick):
                    return True
            except (TypeError, ValueError):
                continue
    return False


def _property_power_cut_active(sim, prop, *, tick=None):
    if not isinstance(prop, dict):
        return False
    power_cuts = getattr(sim, "fixture_power_cuts", None)
    if not isinstance(power_cuts, dict) or not power_cuts:
        return False
    if tick is None:
        tick = int(getattr(sim, "tick", 0))

    prop_id = str(prop.get("id", "") or "").strip()
    if prop_id:
        try:
            if int(power_cuts.get(prop_id, 0) or 0) > int(tick):
                return True
        except (TypeError, ValueError):
            pass

    return _power_cut_active_at(sim, prop.get("x"), prop.get("y"), prop.get("z", 0), tick=tick)


def _light_active_for_phase(metadata, phase):
    if str(phase or "").strip().lower() not in _LIGHT_PHASES:
        return False
    if not bool(metadata.get("light_enabled")):
        return False

    configured = metadata.get("light_phases", ())
    phases = []
    if isinstance(configured, (list, tuple, set)):
        for row in configured:
            label = str(row).strip().lower()
            if label and label not in phases:
                phases.append(label)
    elif isinstance(configured, str) and configured.strip():
        phases.append(configured.strip().lower())

    if not phases:
        phases = ["dawn", "dusk", "night"]
    return str(phase).strip().lower() in phases


def _building_light_profile(sim, prop, clock):
    if not isinstance(prop, dict):
        return None
    if str(prop.get("kind", "")).strip().lower() != "building":
        return None

    phase = str(clock.get("phase", "day")).strip().lower() or "day"
    if phase not in _LIGHT_PHASES:
        return None
    if _property_power_cut_active(sim, prop, tick=clock.get("tick")):
        return None

    if property_is_open(sim, prop, hour=clock.get("hour")) is not True:
        return None

    public = property_is_public(prop)
    storefront = property_is_storefront(prop)
    finance_services = finance_services_for_property(prop)
    site_services = site_services_for_property(prop)
    if not any((public, storefront, finance_services, site_services)):
        return None

    intensity = 0.18
    radius = 2
    if public:
        intensity = max(intensity, 0.22)
    if storefront:
        intensity = max(intensity, 0.28)
        radius = max(radius, 3)
    if finance_services:
        intensity = max(intensity, 0.34)
        radius = max(radius, 3)
    if site_services:
        intensity = max(intensity, 0.32)
        radius = max(radius, 3)

    metadata = _property_metadata(prop)
    visual = _light_visual_fields(metadata, prop=prop, default_profile="storefront_warm")
    return {
        "building_id": metadata.get("building_id"),
        "intensity": _clamp_unit(intensity),
        "radius": max(1, int(radius)),
        **visual,
    }


def _authored_fixture_light_sources(sim, clock):
    phase = str(clock.get("phase", "day")).strip().lower() or "day"
    bounds = _loaded_property_bounds(sim)
    sources = []
    if sim is None or not hasattr(sim, "properties"):
        return sources

    for prop in sim.properties.values():
        if not isinstance(prop, dict):
            continue
        metadata = _property_metadata(prop)
        if not _light_active_for_phase(metadata, phase):
            continue
        if _property_power_cut_active(sim, prop, tick=clock.get("tick")):
            continue
        if not _property_in_loaded_bounds(prop, bounds, margin=int(metadata.get("light_radius", 0) or 0)):
            continue

        try:
            x = int(prop.get("x"))
            y = int(prop.get("y"))
            z = int(prop.get("z", 0))
            radius = int(metadata.get("light_radius", 0))
            intensity = float(metadata.get("light_intensity", 0.0))
        except (TypeError, ValueError):
            continue
        if radius <= 0 or intensity <= 0.0:
            continue

        visual = _light_visual_fields(metadata, prop=prop, default_profile="street_warm")
        sources.append({
            "x": x,
            "y": y,
            "z": z,
            "radius": radius,
            "intensity": _clamp_unit(intensity),
            "kind": "fixture",
            "building_id": None,
            "property_id": prop.get("id"),
            **visual,
        })

    return sources


def _bioluminescent_flora_light_sources(sim):
    bounds = _loaded_property_bounds(sim)
    patches = getattr(sim, "flora_patches", None)
    if not isinstance(patches, dict):
        return []
    luminous_ids = getattr(sim, "bioluminescent_flora_ids", None)
    if not isinstance(luminous_ids, set):
        luminous_ids = {
            str(record_id)
            for record_id, record in patches.items()
            if isinstance(record, dict) and bool(record.get("bioluminescent"))
        }
        sim.bioluminescent_flora_ids = luminous_ids

    sources = []
    for record_id in sorted(tuple(luminous_ids)):
        record = patches.get(record_id)
        if not isinstance(record, dict) or not bool(record.get("bioluminescent")):
            luminous_ids.discard(record_id)
            continue
        absorbed = max(0.0, _float_or_default(record.get("absorbed_toxin_load"), 0.0))
        signal_strength = max(0.0, _float_or_default(record.get("bioluminescent_signal_strength"), 0.0))
        if absorbed <= 0.0 and signal_strength <= 0.0:
            continue
        radius = max(1, min(4, _int_or_default(record.get("bioluminescent_radius"), 2)))
        if not _property_in_loaded_bounds(record, bounds, margin=radius):
            continue
        try:
            x = int(record.get("x"))
            y = int(record.get("y"))
            z = int(record.get("z", 0))
        except (TypeError, ValueError):
            continue
        emission = max(absorbed, signal_strength)
        intensity = _clamp_unit(record.get("bioluminescent_intensity", 0.2 + (emission * 0.1)))
        profile_name, profile = _profile_row(
            record.get("bioluminescent_light_profile"),
            default_profile="accumulator_glow",
        )
        sources.append({
            "x": x,
            "y": y,
            "z": z,
            "radius": radius,
            "intensity": intensity,
            "kind": "bioluminescent_flora",
            "building_id": _structure_building_id(sim, x, y, z),
            "property_id": None,
            "flora_id": record_id,
            "light_profile": profile_name,
            "light_color": list(profile["rgb"]),
            "light_pulse": str(profile.get("pulse", "") or ""),
            "light_priority": int(profile["priority"]),
        })
    return sources


def _aperture_light_sources(sim, clock):
    phase = str(clock.get("phase", "day")).strip().lower() or "day"
    bounds = _loaded_property_bounds(sim)
    state = lighting_state(sim)
    cache_key = (
        phase,
        int(clock.get("hour", 0) or 0),
        bounds,
        int(len(getattr(sim, "properties", {}))),
        int(getattr(sim, "aperture_state_revision", 0) or 0),
        _active_power_cut_cache_key(sim, tick=clock.get("tick", getattr(sim, "tick", 0))),
    )
    if tuple(state.get("aperture_source_cache_key", ())) == cache_key:
        cached = state.get("aperture_light_sources", ())
        if isinstance(cached, (list, tuple)):
            return [dict(source) for source in cached if isinstance(source, dict)]

    sources = []
    if sim is None or not hasattr(sim, "properties"):
        return sources

    for prop in sim.properties.values():
        profile = _building_light_profile(sim, prop, clock)
        if not isinstance(profile, dict):
            continue
        if not _property_in_loaded_bounds(prop, bounds, margin=int(profile.get("radius", 0) or 0)):
            continue

        for aperture in property_apertures(prop):
            try:
                ax = int(aperture.get("x"))
                ay = int(aperture.get("y"))
                az = int(aperture.get("z", prop.get("z", 0)))
            except (TypeError, ValueError):
                continue
            if az != 0:
                continue
            if not _aperture_allows_light(sim, aperture, x=ax, y=ay, z=az):
                continue

            kind = str(aperture.get("kind", "door") or "door").strip().lower()
            intensity = float(profile["intensity"]) * _APERTURE_LOCAL_LIGHT_KIND_SCALE.get(kind, 0.76)
            radius = int(profile["radius"])
            if kind in {"window", "skylight"}:
                radius += 1
            sources.append({
                "x": ax,
                "y": ay,
                "z": az,
                "radius": max(1, radius),
                "intensity": _clamp_unit(intensity),
                "kind": "aperture",
                "building_id": profile.get("building_id"),
                "property_id": prop.get("id"),
                "light_profile": profile.get("light_profile"),
                "light_color": list(profile.get("light_color", ())),
                "light_pulse": profile.get("light_pulse", ""),
                "light_priority": int(profile.get("light_priority", 0) or 0),
            })

    state["aperture_source_cache_key"] = cache_key
    state["aperture_light_sources"] = [dict(source) for source in sources]
    return sources


def _fire_light_sources(sim):
    bounds = _loaded_property_bounds(sim)
    sources = []
    cells = fire_state(sim).get("cells", {})
    if not isinstance(cells, dict) or not cells:
        return sources

    for coord, cell in cells.items():
        if not isinstance(cell, dict):
            continue
        try:
            x = int(coord[0])
            y = int(coord[1])
            z = int(coord[2])
            fire_intensity = int(cell.get("fire_intensity", 0) or 0)
        except (TypeError, ValueError, IndexError):
            continue
        if fire_intensity <= 0:
            continue
        if bounds is not None:
            min_x, max_x, min_y, max_y = bounds
            profile = _FIRE_INTENSITY_PROFILE.get(max(1, min(3, fire_intensity)), _FIRE_INTENSITY_PROFILE[3])
            margin = int(profile.get("radius", 0) or 0)
            if not (
                (min_x - margin) <= x <= (max_x + margin)
                and (min_y - margin) <= y <= (max_y + margin)
            ):
                continue
        profile = _FIRE_INTENSITY_PROFILE.get(max(1, min(3, fire_intensity)), _FIRE_INTENSITY_PROFILE[3])
        sources.append({
            "x": x,
            "y": y,
            "z": z,
            "radius": int(profile.get("radius", 2) or 2),
            "intensity": _clamp_unit(profile.get("intensity", 0.34), default=0.34),
            "kind": "fire",
            "building_id": str(cell.get("building_id", "") or "").strip() or None,
            "property_id": str(cell.get("property_id", "") or "").strip() or None,
            **_light_visual_fields({}, default_profile="fire_orange"),
        })

    return sources


def _active_vehicle_light_cache_key(sim):
    try:
        vehicle_states = sim.ecs.get(VehicleState)
        positions = sim.ecs.get(Position)
    except AttributeError:
        return ()

    rows = []
    vehicle_by_occupant = getattr(sim, "vehicle_by_occupant", {})
    for eid, indexed_vehicle_id in tuple(vehicle_by_occupant.items()):
        raw_state = vehicle_states.get(eid)
        state = raw_state.ensure_motion_defaults() if hasattr(raw_state, "ensure_motion_defaults") else raw_state
        if not state or not bool(getattr(state, "in_vehicle", False)):
            continue
        vehicle_id = str(getattr(state, "active_vehicle_id", "") or "").strip()
        if not vehicle_id or vehicle_id != str(indexed_vehicle_id):
            continue
        pos = positions.get(eid)
        if not pos:
            continue
        rows.append((
            int(eid),
            vehicle_id,
            int(getattr(pos, "x", 0)),
            int(getattr(pos, "y", 0)),
            int(getattr(pos, "z", 0)),
            int(getattr(state, "heading_dx", 0) or 0),
            int(getattr(state, "heading_dy", -1) or -1),
            int(bool(getattr(state, "headlights_on", True))),
        ))
    return tuple(sorted(rows))


def _vehicle_headlight_sources(sim):
    try:
        vehicle_states = sim.ecs.get(VehicleState)
        positions = sim.ecs.get(Position)
    except AttributeError:
        return []

    bounds = _loaded_property_bounds(sim)
    sources = []
    vehicle_by_occupant = getattr(sim, "vehicle_by_occupant", {})
    for eid, indexed_vehicle_id in tuple(vehicle_by_occupant.items()):
        raw_state = vehicle_states.get(eid)
        state = raw_state.ensure_motion_defaults() if hasattr(raw_state, "ensure_motion_defaults") else raw_state
        if not state or not bool(getattr(state, "in_vehicle", False)):
            continue
        if not bool(getattr(state, "headlights_on", True)):
            continue
        vehicle_id = str(getattr(state, "active_vehicle_id", "") or "").strip()
        if not vehicle_id or vehicle_id != str(indexed_vehicle_id):
            continue
        vehicle_prop = getattr(sim, "properties", {}).get(vehicle_id) if vehicle_id else None
        if not isinstance(vehicle_prop, dict) or str(vehicle_prop.get("kind", "") or "").strip().lower() != "vehicle":
            continue
        pos = positions.get(eid)
        if not pos:
            continue
        x = int(getattr(pos, "x", vehicle_prop.get("x", 0)))
        y = int(getattr(pos, "y", vehicle_prop.get("y", 0)))
        z = int(getattr(pos, "z", vehicle_prop.get("z", 0)))
        dx = int(getattr(state, "heading_dx", 0) or 0)
        dy = int(getattr(state, "heading_dy", -1) or -1)
        dx = 1 if dx > 0 else -1 if dx < 0 else 0
        dy = 1 if dy > 0 else -1 if dy < 0 else 0
        if dx == 0 and dy == 0:
            dx, dy = 0, -1

        if bounds is not None:
            min_x, max_x, min_y, max_y = bounds
            margin = 8
            if not ((min_x - margin) <= x <= (max_x + margin) and (min_y - margin) <= y <= (max_y + margin)):
                continue

        # A compact two-source beam gives nearby fill and a brighter reach ahead.
        visual = _light_visual_fields(_property_metadata(vehicle_prop), prop=vehicle_prop, default_profile="headlight_white")
        for step, radius, intensity in ((1, 4, 0.62), (4, 5, 0.42)):
            sources.append({
                "x": x + (dx * step),
                "y": y + (dy * step),
                "z": z,
                "radius": int(radius),
                "intensity": _clamp_unit(intensity),
                "kind": "vehicle_headlight",
                "building_id": None,
                "property_id": vehicle_id,
                "eid": int(eid),
                **visual,
            })
    return sources


def _local_light_sources(sim, clock=None):
    if clock is None:
        clock = clock_snapshot(sim)

    state = lighting_state(sim)
    cache_key = (
        int(clock.get("tick", getattr(sim, "tick", 0))),
        str(clock.get("phase", "day")),
        int(clock.get("hour", 0)),
        int(len(getattr(sim, "properties", {}))),
        _active_power_cut_cache_key(sim, tick=clock.get("tick", getattr(sim, "tick", 0))),
        _active_fire_cache_key(sim),
        _active_vehicle_light_cache_key(sim),
        tuple(sorted(
            (
                str(record_id),
                round(_float_or_default((getattr(sim, "flora_patches", {}).get(record_id) or {}).get("absorbed_toxin_load"), 0.0), 3),
                round(_float_or_default((getattr(sim, "flora_patches", {}).get(record_id) or {}).get("bioluminescent_signal_strength"), 0.0), 3),
                str((getattr(sim, "flora_patches", {}).get(record_id) or {}).get("bioluminescent_light_profile", "")),
            )
            for record_id in tuple(getattr(sim, "bioluminescent_flora_ids", ()) or ())
        )),
    )
    if tuple(state.get("source_cache_key", ())) == cache_key:
        cached = state.get("local_light_sources", ())
        if isinstance(cached, (list, tuple)):
            return tuple(cached)

    vehicle_sources = tuple(_vehicle_headlight_sources(sim))
    flora_sources = tuple(_bioluminescent_flora_light_sources(sim))
    if str(clock.get("phase", "day")).strip().lower() not in _LIGHT_PHASES:
        sources = tuple(_fire_light_sources(sim) + list(vehicle_sources) + list(flora_sources))
    else:
        sources = tuple(
            _authored_fixture_light_sources(sim, clock)
            + _aperture_light_sources(sim, clock)
            + _fire_light_sources(sim)
            + list(vehicle_sources)
            + list(flora_sources)
        )

    state["source_cache_key"] = cache_key
    state["local_light_sources"] = [dict(source) for source in sources]
    state["source_count"] = len(sources)
    return sources


def _local_light_sources_near(sim, x, y, z, *, clock=None, sampling=None):
    """Return only sources whose exact radius covers the sampled cell."""

    state = lighting_state(sim)
    if isinstance(sampling, dict) and sampling.get("sim") is sim:
        sources = tuple(sampling.get("sources", ()) or ())
        source_key = tuple(sampling.get("source_key", ()))
    else:
        sources = _local_light_sources(sim, clock=clock)
        source_key = tuple(state.get("source_cache_key", ()))
    if tuple(state.get("source_spatial_cache_key", ())) != source_key:
        spatial = {}
        for source in sources:
            try:
                sx = int(source.get("x"))
                sy = int(source.get("y"))
                sz = int(source.get("z", 0))
                radius = max(1, int(source.get("radius", 0)))
            except (AttributeError, TypeError, ValueError):
                continue
            for dy in range(-radius, radius + 1):
                remaining = radius - abs(dy)
                for dx in range(-remaining, remaining + 1):
                    spatial.setdefault((sx + dx, sy + dy, sz), []).append(source)
        state["local_light_source_spatial"] = {
            key: tuple(rows)
            for key, rows in spatial.items()
        }
        state["source_spatial_cache_key"] = source_key
    spatial = state.get("local_light_source_spatial", {})
    if not isinstance(spatial, dict):
        return ()
    return tuple(spatial.get((int(x), int(y), int(z)), ()) or ())


def _structure_building_id(sim, x, y, z=0):
    structure = _structure_at(sim, x, y, z)
    if not isinstance(structure, dict):
        return None
    building_id = structure.get("building_id")
    return str(building_id).strip() if building_id else None


def _inside_light_factor(sample_building_id, source):
    source_kind = str(source.get("kind", "") or "").strip().lower()
    source_building_id = str(source.get("building_id", "") or "").strip() or None

    if sample_building_id and source_building_id and sample_building_id == source_building_id:
        return 1.0
    if source_kind == "fixture":
        return 0.0
    return 0.0


def _world_event_grid_light_mult(sim, x, y):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        return 1.0

    state = traits.get("world_events")
    if not isinstance(state, dict):
        return 1.0

    active = state.get("active")
    if not isinstance(active, list) or not active:
        return 1.0

    try:
        cx, cy = sim.chunk_coords(int(x), int(y))
    except (AttributeError, TypeError, ValueError):
        return 1.0

    mult = 1.0
    for event in active:
        if not isinstance(event, dict):
            continue
        try:
            ex = int(event.get("cx", -9999))
            ey = int(event.get("cy", -9999))
        except (TypeError, ValueError):
            continue
        if ex != cx or ey != cy:
            continue
        event_key = str(event.get("key", "") or "").strip().lower()
        if event_key == "power_outage":
            # Older saves may still carry the original dimming multiplier. A
            # power outage is categorical for ordinary grid lighting: natural
            # darkness remains, while fires and vehicle lights use independent
            # source kinds and continue to illuminate the scene.
            factor = 0.0
        else:
            try:
                factor = float(event.get("fixture_light_mult", 1.0))
            except (TypeError, ValueError):
                factor = 1.0
        mult *= max(0.0, min(1.0, factor))

    # Per-property power cuts from player sabotage.
    power_cuts = getattr(sim, "fixture_power_cuts", None)
    if power_cuts:
        try:
            tick = int(getattr(sim, "tick", 0))
            cover_index = getattr(sim, "property_cover_index", {})
            for z_check in (0, 1):
                key = (int(x), int(y), z_check)
                for pid in cover_index.get(key, ()):
                    cut_until = power_cuts.get(pid, 0)
                    if isinstance(cut_until, (int, float)) and int(cut_until) > tick:
                        mult *= 0.18
                        break
                else:
                    continue
                break
        except (TypeError, ValueError, AttributeError):
            pass

    return max(0.0, min(1.0, mult))


def _world_grid_light_event_key(sim):
    traits = getattr(sim, "world_traits", None)
    state = traits.get("world_events") if isinstance(traits, dict) else None
    active = state.get("active") if isinstance(state, dict) else None
    rows = []
    for event in tuple(active or ()):
        if not isinstance(event, dict):
            continue
        rows.append((
            str(event.get("key", "") or "").strip().lower(),
            _int_or_default(event.get("cx"), -9999),
            _int_or_default(event.get("cy"), -9999),
            round(_float_or_default(event.get("fixture_light_mult"), 1.0), 4),
        ))
    return tuple(sorted(rows))


def _local_light_contributions(
    sim,
    x,
    y,
    z=0,
    inside=False,
    aperture_bleed=0.0,
    clock=None,
    *,
    sampling=None,
):
    if clock is None:
        clock = clock_snapshot(sim)

    try:
        x = int(x)
        y = int(y)
        z = int(z)
    except (TypeError, ValueError):
        return []

    contributions = []
    sample_building_id = _structure_building_id(sim, x, y, z) if inside else None
    outside_bleed = _clamp_unit(aperture_bleed, default=0.0)
    for source in _local_light_sources_near(sim, x, y, z, clock=clock, sampling=sampling):
        try:
            sx = int(source.get("x"))
            sy = int(source.get("y"))
            sz = int(source.get("z", 0))
            radius = max(1, int(source.get("radius", 0)))
            intensity = _clamp_unit(source.get("intensity", 0.0))
        except (TypeError, ValueError):
            continue
        if sz != z or intensity <= 0.0:
            continue

        dist = abs(sx - x) + abs(sy - y)
        if dist > radius:
            continue

        falloff = max(0.0, 1.0 - (float(dist) / float(radius + 1)))
        contribution = intensity * falloff
        source_kind = str(source.get("kind", "") or "").strip().lower()
        if source_kind in {"fixture", "aperture"}:
            # Grid state belongs to the source's district. This matters at a
            # chunk edge, where light may spill into a neighboring district.
            contribution *= _world_event_grid_light_mult(sim, sx, sy)
        if contribution <= 0.0:
            continue

        if inside:
            inside_factor = _inside_light_factor(sample_building_id, source)
            if inside_factor <= 0.0:
                continue
            contribution *= inside_factor
        elif source_kind == "aperture":
            contribution *= 0.9 + (0.1 * outside_bleed)

        contributions.append((source, _clamp_unit(contribution)))

    return contributions


def _combine_local_light(contributions):
    values = []
    for row in contributions or ():
        if isinstance(row, (list, tuple)) and len(row) >= 2:
            values.append(_clamp_unit(row[1]))
        else:
            values.append(_clamp_unit(row))

    if not values:
        return 0.0

    combined_shadow = 1.0
    for contribution in values:
        combined_shadow *= (1.0 - contribution)
    return _clamp_unit(1.0 - combined_shadow)


def _light_tint_from_contributions(contributions):
    weighted = []
    for source, contribution in contributions or ():
        if not isinstance(source, dict):
            continue
        contribution = _clamp_unit(contribution)
        if contribution <= 0.0:
            continue
        profile = str(source.get("light_profile", "") or "").strip().lower()
        rgb = _normalize_light_rgb(source.get("light_color"), profile_name=profile or "storefront_warm")
        priority = max(0, min(8, _int_or_default(source.get("light_priority", 0), 0)))
        weight = contribution * (1.0 + (0.22 * priority))
        if weight <= 0.0:
            continue
        weighted.append({
            "source": source,
            "contribution": contribution,
            "weight": weight,
            "rgb": rgb,
            "priority": priority,
            "profile": profile or _profile_row(None)[0],
        })

    if not weighted:
        return None, []

    total_weight = sum(row["weight"] for row in weighted)
    if total_weight <= 0.0:
        return None, []

    rgb = []
    for channel in range(3):
        rgb.append(_clamp_rgb_channel(sum(row["rgb"][channel] * row["weight"] for row in weighted) / total_weight))

    combined_strength = _combine_local_light((row["source"], row["contribution"]) for row in weighted)
    dominant = max(weighted, key=lambda row: (row["weight"], row["priority"], row["profile"]))
    pulse = str(dominant["source"].get("light_pulse", "") or "").strip().lower()
    sources = []
    for row in sorted(weighted, key=lambda entry: (entry["weight"], entry["priority"]), reverse=True)[:3]:
        source = row["source"]
        sources.append({
            "kind": str(source.get("kind", "") or "").strip().lower(),
            "profile": row["profile"],
            "strength": round(float(row["contribution"]), 4),
            "weight": round(float(row["weight"]), 4),
            "priority": int(row["priority"]),
        })

    tint = {
        "rgb": [int(rgb[0]), int(rgb[1]), int(rgb[2])],
        "strength": round(float(combined_strength), 4),
        "profile": dominant["profile"],
        "pulse": pulse,
        "source_count": int(len(weighted)),
    }
    return tint, sources


def _local_light_level(sim, x, y, z=0, inside=False, aperture_bleed=0.0, clock=None):
    return _combine_local_light(
        _local_light_contributions(
            sim,
            x,
            y,
            z,
            inside=inside,
            aperture_bleed=aperture_bleed,
            clock=clock,
        )
    )


def prepare_ambient_sampling(sim, *, clock=None):
    if clock is None:
        clock = clock_snapshot(sim)

    sources = _local_light_sources(sim, clock=clock)
    state = lighting_state(sim)
    tilemap = getattr(sim, "tilemap", None)
    cache_signature = (
        int(clock.get("tick", getattr(sim, "tick", 0)) or 0),
        tuple(state.get("source_cache_key", ())),
        int(getattr(tilemap, "visibility_revision", 0) or 0),
        derived_fact_revision(sim, "transit_nodes"),
        _world_grid_light_event_key(sim),
    )
    if tuple(state.get("ambient_cache_signature", ())) != cache_signature:
        state["ambient_cache_signature"] = cache_signature
        state["ambient_cache"] = {}
    ambient_cache = state.get("ambient_cache")
    if not isinstance(ambient_cache, dict):
        ambient_cache = {}
        state["ambient_cache"] = ambient_cache
    return {
        "sim": sim,
        "clock": clock,
        "sources": sources,
        "source_key": tuple(state.get("source_cache_key", ())),
        "ambient_cache": ambient_cache,
        "signature": cache_signature,
    }


def ambient_snapshot(sim, x, y, z=0, clock=None, *, sampling=None):
    if not isinstance(sampling, dict) or sampling.get("sim") is not sim:
        sampling = prepare_ambient_sampling(sim, clock=clock)
    clock = sampling.get("clock") if isinstance(sampling.get("clock"), dict) else clock
    if clock is None:
        clock = clock_snapshot(sim)
    try:
        x, y, z = int(x), int(y), int(z)
    except (TypeError, ValueError):
        x, y, z = 0, 0, 0

    # Rendering and perception frequently ask the same exact lighting question
    # several times while simulation time is paused.  The sampling context
    # validates canonical fire, fixture, topology, vehicle, flora, and time
    # dependencies once for the caller's coherent observation window.
    ambient_cache = sampling.get("ambient_cache")
    if not isinstance(ambient_cache, dict):
        sampling = prepare_ambient_sampling(sim, clock=clock)
        ambient_cache = sampling["ambient_cache"]
    cache_key = (x, y, z)
    cached = ambient_cache.get(cache_key)
    if isinstance(cached, dict):
        return cached

    outdoor_ambient = _clamp_unit(
        clock.get("outdoor_ambient", clock.get("outside_ambient", 1.0)),
        default=1.0,
    )
    inside = bool(is_interior_tile(sim, x, y, z))
    if not inside:
        contributions = _local_light_contributions(
            sim,
            x,
            y,
            z,
            inside=False,
            aperture_bleed=0.0,
            clock=clock,
            sampling=sampling,
        )
        local_light = _combine_local_light(contributions)
        light_tint, light_sources = _light_tint_from_contributions(contributions)
        ambient = _clamp_unit(outdoor_ambient + ((1.0 - outdoor_ambient) * local_light), default=outdoor_ambient)
        result = {
            "phase": str(clock.get("phase", "day")),
            "ambient": ambient,
            "outside_ambient": outdoor_ambient,
            "inside": False,
            "aperture_bleed": 0.0,
            "local_light": local_light,
            "light_tint": light_tint,
            "light_sources": light_sources,
        }
        ambient_cache[cache_key] = result
        return result

    interior_base = max(0.12, min(0.48, outdoor_ambient * 0.58))
    bleed = _neighbor_aperture_bonus(sim, x, y, z)
    interior = interior_base + ((outdoor_ambient - interior_base) * (0.7 * bleed))
    contributions = _local_light_contributions(
        sim,
        x,
        y,
        z,
        inside=True,
        aperture_bleed=bleed,
        clock=clock,
        sampling=sampling,
    )
    local_light = _combine_local_light(contributions)
    light_tint, light_sources = _light_tint_from_contributions(contributions)
    interior = _clamp_unit(interior + ((1.0 - interior) * local_light), default=interior_base)
    result = {
        "phase": str(clock.get("phase", "day")),
        "ambient": interior,
        "outside_ambient": outdoor_ambient,
        "inside": True,
        "aperture_bleed": bleed,
        "local_light": local_light,
        "light_tint": light_tint,
        "light_sources": light_sources,
    }
    ambient_cache[cache_key] = result
    return result


def _visibility_ambient_from_sample(sample):
    if not isinstance(sample, dict):
        return 1.0
    ambient = _clamp_unit(sample.get("ambient", sample.get("outside_ambient", 1.0)), default=1.0)
    outside = _clamp_unit(sample.get("outside_ambient", ambient), default=ambient)
    local_light = _clamp_unit(sample.get("local_light", 0.0), default=0.0)
    if outside > GLARE_LOW_AMBIENT_THRESHOLD or local_light < GLARE_EXPOSURE_THRESHOLD:
        return ambient

    # Direct bright light should illuminate its own tiles and add glare wash,
    # but standing inside it should not turn the player's whole FOV into day.
    if local_light >= 0.999:
        return outside
    natural = (ambient - local_light) / max(0.001, 1.0 - local_light)
    return min(ambient, _clamp_unit(natural, default=outside))


def lighting_state(sim):
    world_traits = getattr(sim, "world_traits", None)
    if not isinstance(world_traits, dict):
        world_traits = {}
        if sim is not None:
            sim.world_traits = world_traits

    state = world_traits.get("lighting")
    if isinstance(state, dict):
        return state

    state = {
        "tick": -1,
        "hour": 0,
        "minute": 0,
        "time_label": "00:00",
        "phase": "day",
        "outside_ambient": 1.0,
        "player_inside": False,
        "player_ambient": 1.0,
        "player_visibility_ambient": 1.0,
        "player_aperture_bleed": 0.0,
        "player_local_light": 0.0,
        "player_light_tint": None,
        "player_light_sources": [],
        "player_glare": {},
        "source_cache_key": (),
        "local_light_sources": [],
        "source_spatial_cache_key": (),
        "local_light_source_spatial": {},
        "aperture_source_cache_key": (),
        "aperture_light_sources": [],
        "aperture_bleed_cache": {},
        "ambient_cache_signature": (),
        "ambient_cache": {},
        "source_count": 0,
    }
    world_traits["lighting"] = state
    return state


def _glare_strength_at_tick(glare, tick):
    if not isinstance(glare, dict):
        return 0.0
    try:
        expires = int(glare.get("expires_tick", 0) or 0)
        created = int(glare.get("created_tick", expires) or expires)
        peak = float(glare.get("peak", 0.0) or 0.0)
    except (TypeError, ValueError):
        return 0.0
    if expires <= int(tick) or peak <= 0.0:
        return 0.0
    span = max(1, expires - created)
    remaining = max(0, expires - int(tick))
    return _clamp_unit(peak * (float(remaining) / float(span)))


def glare_strength(sim, *, eid=None, tick=None):
    if tick is None:
        tick = int(getattr(sim, "tick", 0) or 0)
    if eid is not None:
        registry = getattr(sim, "visual_glare_by_eid", None)
        if isinstance(registry, dict):
            return _glare_strength_at_tick(registry.get(int(eid)), int(tick))
        return 0.0
    return _glare_strength_at_tick(lighting_state(sim).get("player_glare"), int(tick))


def _note_entity_glare(sim, eid, *, peak, source_profile=None, tick=None):
    if sim is None or eid is None:
        return None
    if tick is None:
        tick = int(getattr(sim, "tick", 0) or 0)
    registry = getattr(sim, "visual_glare_by_eid", None)
    if not isinstance(registry, dict):
        registry = {}
        sim.visual_glare_by_eid = registry
    existing = registry.get(int(eid))
    current = _glare_strength_at_tick(existing, int(tick))
    peak = max(float(peak), current)
    glare = {
        "created_tick": int(tick),
        "expires_tick": int(tick) + GLARE_RECOVERY_TICKS,
        "peak": round(_clamp_unit(peak), 4),
        "source_profile": str(source_profile or "bright_light"),
    }
    registry[int(eid)] = glare
    return glare


def update_visual_glare_for_entity(sim, eid, pos, *, clock=None):
    if sim is None or eid is None or pos is None:
        return None
    if clock is None:
        clock = clock_snapshot(sim)
    sample = ambient_snapshot(
        sim,
        getattr(pos, "x", 0),
        getattr(pos, "y", 0),
        getattr(pos, "z", 0),
        clock=clock,
    )
    try:
        outside = float(sample.get("outside_ambient", clock.get("outdoor_ambient", 1.0)) or 1.0)
        local_light = float(sample.get("local_light", 0.0) or 0.0)
    except (TypeError, ValueError):
        return None
    if outside > GLARE_LOW_AMBIENT_THRESHOLD or local_light < GLARE_EXPOSURE_THRESHOLD:
        return None
    light_tint = sample.get("light_tint") if isinstance(sample, dict) else None
    source_profile = ""
    if isinstance(light_tint, dict):
        source_profile = str(light_tint.get("profile", "") or "").strip().lower()
    overage = (local_light - GLARE_EXPOSURE_THRESHOLD) / max(0.01, 1.0 - GLARE_EXPOSURE_THRESHOLD)
    darkness = (GLARE_LOW_AMBIENT_THRESHOLD - outside) / max(0.01, GLARE_LOW_AMBIENT_THRESHOLD)
    peak = 0.32 + (0.50 * _clamp_unit(overage)) + (0.18 * _clamp_unit(darkness))
    return _note_entity_glare(sim, int(eid), peak=peak, source_profile=source_profile, tick=clock.get("tick"))


def update_lighting_state(sim, player_pos=None):
    state = lighting_state(sim)
    snapshot = clock_snapshot(sim)
    tick = int(snapshot["tick"])
    state["tick"] = int(snapshot["tick"])
    state["hour"] = int(snapshot["hour"])
    state["minute"] = int(snapshot["minute"])
    state["time_label"] = str(snapshot["time_label"])
    state["phase"] = str(snapshot["phase"])
    state["outside_ambient"] = _clamp_unit(snapshot["outdoor_ambient"], default=1.0)

    if player_pos is None:
        state["player_inside"] = False
        state["player_ambient"] = state["outside_ambient"]
        state["player_visibility_ambient"] = state["outside_ambient"]
        state["player_aperture_bleed"] = 0.0
        state["player_local_light"] = 0.0
        state["player_light_tint"] = None
        state["player_light_sources"] = []
        state["player_glare"] = {}
        _local_light_sources(sim, clock=snapshot)
        return state

    _local_light_sources(sim, clock=snapshot)
    player_eid = getattr(sim, "player_eid", None)
    if player_eid is not None:
        update_visual_glare_for_entity(sim, player_eid, player_pos, clock=snapshot)
    ambient = ambient_snapshot(
        sim,
        x=getattr(player_pos, "x", 0),
        y=getattr(player_pos, "y", 0),
        z=getattr(player_pos, "z", 0),
        clock=snapshot,
    )
    state["player_inside"] = bool(ambient.get("inside"))
    state["player_ambient"] = _clamp_unit(ambient.get("ambient", state["outside_ambient"]), default=state["outside_ambient"])
    state["player_visibility_ambient"] = _visibility_ambient_from_sample(ambient)
    state["player_aperture_bleed"] = _clamp_unit(ambient.get("aperture_bleed", 0.0))
    state["player_local_light"] = _clamp_unit(ambient.get("local_light", 0.0))
    state["player_light_tint"] = ambient.get("light_tint")
    state["player_light_sources"] = list(ambient.get("light_sources", ()) or ())
    glare = None
    if player_eid is not None:
        registry = getattr(sim, "visual_glare_by_eid", None)
        if isinstance(registry, dict):
            glare = registry.get(int(player_eid))
    if isinstance(glare, dict):
        strength = _glare_strength_at_tick(glare, tick)
        if strength > 0.0:
            state["player_glare"] = {**glare, "strength": round(float(strength), 4)}
        else:
            state["player_glare"] = {}
    else:
        state["player_glare"] = {}

    registry = getattr(sim, "visual_glare_by_eid", None)
    if isinstance(registry, dict) and registry:
        expired = [
            int(eid)
            for eid, row in tuple(registry.items())
            if _glare_strength_at_tick(row, tick) <= 0.0
        ]
        for eid in expired:
            registry.pop(eid, None)
    return state
