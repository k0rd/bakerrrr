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

    structure = _structure_at(sim, x, y, z)
    if not isinstance(structure, dict):
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
        return 1.0

    if _tile_aperture_allows_light(sim, x, y, z):
        strongest = max(strongest, 0.85)

    for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
        if _tile_aperture_allows_light(sim, nx, ny, z):
            strongest = max(strongest, 0.6)

    return _clamp_unit(strongest)


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
    return {
        "building_id": metadata.get("building_id"),
        "intensity": _clamp_unit(intensity),
        "radius": max(1, int(radius)),
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

        sources.append({
            "x": x,
            "y": y,
            "z": z,
            "radius": radius,
            "intensity": _clamp_unit(intensity),
            "kind": "fixture",
            "building_id": None,
            "property_id": prop.get("id"),
        })

    return sources


def _aperture_light_sources(sim, clock):
    phase = str(clock.get("phase", "day")).strip().lower() or "day"
    bounds = _loaded_property_bounds(sim)
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
    )
    if tuple(state.get("source_cache_key", ())) == cache_key:
        cached = state.get("local_light_sources", ())
        if isinstance(cached, (list, tuple)):
            return tuple(cached)

    if str(clock.get("phase", "day")).strip().lower() not in _LIGHT_PHASES:
        sources = ()
    else:
        sources = tuple(_authored_fixture_light_sources(sim, clock) + _aperture_light_sources(sim, clock))

    state["source_cache_key"] = cache_key
    state["local_light_sources"] = [dict(source) for source in sources]
    state["source_count"] = len(sources)
    return sources


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


def _world_event_fixture_light_mult(sim, x, y):
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
        try:
            factor = float(event.get("fixture_light_mult", 1.0))
        except (TypeError, ValueError):
            factor = 1.0
        mult *= max(0.0, min(1.0, factor))
    return max(0.0, min(1.0, mult))


def _local_light_level(sim, x, y, z=0, inside=False, aperture_bleed=0.0, clock=None):
    if clock is None:
        clock = clock_snapshot(sim)

    try:
        x = int(x)
        y = int(y)
        z = int(z)
    except (TypeError, ValueError):
        return 0.0

    contributions = []
    sample_building_id = _structure_building_id(sim, x, y, z) if inside else None
    outside_bleed = _clamp_unit(aperture_bleed, default=0.0)
    for source in _local_light_sources(sim, clock=clock):
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
        if str(source.get("kind", "") or "").strip().lower() == "fixture":
            contribution *= _world_event_fixture_light_mult(sim, x, y)
        if contribution <= 0.0:
            continue

        if inside:
            inside_factor = _inside_light_factor(sample_building_id, source)
            if inside_factor <= 0.0:
                continue
            contribution *= inside_factor
        elif str(source.get("kind", "") or "").strip().lower() == "aperture":
            contribution *= 0.9 + (0.1 * outside_bleed)

        contributions.append(_clamp_unit(contribution))

    if not contributions:
        return 0.0

    combined_shadow = 1.0
    for contribution in contributions:
        combined_shadow *= (1.0 - contribution)
    return _clamp_unit(1.0 - combined_shadow)


def ambient_snapshot(sim, x, y, z=0, clock=None):
    if clock is None:
        clock = clock_snapshot(sim)
    outdoor_ambient = _clamp_unit(
        clock.get("outdoor_ambient", clock.get("outside_ambient", 1.0)),
        default=1.0,
    )
    inside = bool(is_interior_tile(sim, x, y, z))
    if not inside:
        local_light = _local_light_level(sim, x, y, z, inside=False, aperture_bleed=0.0, clock=clock)
        ambient = _clamp_unit(outdoor_ambient + ((1.0 - outdoor_ambient) * local_light), default=outdoor_ambient)
        return {
            "phase": str(clock.get("phase", "day")),
            "ambient": ambient,
            "outside_ambient": outdoor_ambient,
            "inside": False,
            "aperture_bleed": 0.0,
            "local_light": local_light,
        }

    interior_base = max(0.12, min(0.48, outdoor_ambient * 0.58))
    bleed = _neighbor_aperture_bonus(sim, x, y, z)
    interior = interior_base + ((outdoor_ambient - interior_base) * (0.7 * bleed))
    local_light = _local_light_level(sim, x, y, z, inside=True, aperture_bleed=bleed, clock=clock)
    interior = _clamp_unit(interior + ((1.0 - interior) * local_light), default=interior_base)
    return {
        "phase": str(clock.get("phase", "day")),
        "ambient": interior,
        "outside_ambient": outdoor_ambient,
        "inside": True,
        "aperture_bleed": bleed,
        "local_light": local_light,
    }


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
        "player_aperture_bleed": 0.0,
        "player_local_light": 0.0,
        "source_cache_key": (),
        "local_light_sources": [],
        "source_count": 0,
    }
    world_traits["lighting"] = state
    return state


def update_lighting_state(sim, player_pos=None):
    state = lighting_state(sim)
    snapshot = clock_snapshot(sim)
    state["tick"] = int(snapshot["tick"])
    state["hour"] = int(snapshot["hour"])
    state["minute"] = int(snapshot["minute"])
    state["time_label"] = str(snapshot["time_label"])
    state["phase"] = str(snapshot["phase"])
    state["outside_ambient"] = _clamp_unit(snapshot["outdoor_ambient"], default=1.0)

    if player_pos is None:
        state["player_inside"] = False
        state["player_ambient"] = state["outside_ambient"]
        state["player_aperture_bleed"] = 0.0
        state["player_local_light"] = 0.0
        _local_light_sources(sim, clock=snapshot)
        return state

    _local_light_sources(sim, clock=snapshot)
    ambient = ambient_snapshot(
        sim,
        x=getattr(player_pos, "x", 0),
        y=getattr(player_pos, "y", 0),
        z=getattr(player_pos, "z", 0),
        clock=snapshot,
    )
    state["player_inside"] = bool(ambient.get("inside"))
    state["player_ambient"] = _clamp_unit(ambient.get("ambient", state["outside_ambient"]), default=state["outside_ambient"])
    state["player_aperture_bleed"] = _clamp_unit(ambient.get("aperture_bleed", 0.0))
    state["player_local_light"] = _clamp_unit(ambient.get("local_light", 0.0))
    return state
