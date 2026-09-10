"""Deterministic tornado genesis, alerts, shelter choice, and physical impacts."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping

from engine.events import Event
from engine.systems import System
from game.components import Collider, Position, Render, Vitality
from game.items import ITEM_CATALOG
from game.lighting import is_interior_tile
from game.property_runtime import property_focus_position, property_is_vehicle, property_metadata
from game.system_support.actor_runtime import _apply_downed_actor_state
from game.system_support.structure_damage_runtime import apply_structural_damage
from game.vehicle_motion import apply_vehicle_durability_loss
from game.weather_runtime import weather_forecast, weather_snapshot


TORNADO_MODEL_VERSION = 1
TORNADO_MACRO_CHUNKS = 6
TORNADO_SLOT_HOURS = 6
TORNADO_IMPACT_INTERVAL = 6
TORNADO_WARNING_RADIUS_CHUNKS = 5

_DIRECTION_VECTOR = {
    "n": (0.0, -1.0),
    "ne": (0.707, -0.707),
    "e": (1.0, 0.0),
    "se": (0.707, 0.707),
    "s": (0.0, 1.0),
    "sw": (-0.707, 0.707),
    "w": (-1.0, 0.0),
    "nw": (-0.707, -0.707),
}


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


def _clamp(value, low=0.0, high=1.0):
    return max(float(low), min(float(high), float(value)))


def _stable_int(*parts):
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big")


def _clock(sim, tick=None):
    tick = _safe_int(getattr(sim, "tick", 0) if tick is None else tick, 0)
    traits = getattr(sim, "world_traits", {})
    config = traits.get("clock", {}) if isinstance(traits, Mapping) else {}
    ticks_per_hour = max(1, _safe_int(config.get("ticks_per_hour"), 600))
    return tick, ticks_per_hour


def tornado_potential(weather):
    """Return a 0..1 funnel environment score from atmospheric ingredients."""

    weather = weather if isinstance(weather, Mapping) else {}
    instability = _clamp(_safe_float(weather.get("instability_pct")) / 100.0)
    storm = _clamp(weather.get("storm_intensity", 0.0))
    humidity = _clamp((_safe_float(weather.get("humidity_pct"), 50.0) - 48.0) / 50.0)
    front = _clamp(_safe_float(weather.get("front_strength_pct")) / 100.0)
    wind = _clamp((_safe_float(weather.get("wind_speed_kph")) - 12.0) / 48.0)
    pressure_fall = _clamp(-_safe_float(weather.get("pressure_delta_3h")) / 7.0)
    score = (
        storm * 0.38
        + instability * 0.22
        + humidity * 0.13
        + front * 0.13
        + wind * 0.08
        + pressure_fall * 0.06
    )
    qualifying = bool(
        storm >= 0.18
        and instability >= 0.48
        and _safe_float(weather.get("humidity_pct"), 0.0) >= 62.0
        and _safe_float(weather.get("wind_speed_kph"), 0.0) >= 16.0
    )
    return _clamp(score if qualifying else score * 0.58)


def tornado_genesis_chance(weather):
    """Return the bounded funnel chance once a six-hour candidate slot is sampled."""

    potential = tornado_potential(weather)
    if potential < 0.38:
        return 0.0
    return _clamp(0.05 + (potential - 0.35) * 1.10, 0.0, 0.28)


def _candidate_cache(sim):
    cache = getattr(sim, "_tornado_candidate_cache", None)
    if not isinstance(cache, dict):
        cache = {}
        sim._tornado_candidate_cache = cache
    return cache


def _forced_candidate(sim, *, tick):
    traits = getattr(sim, "world_traits", {})
    debug = traits.get("weather_debug", {}) if isinstance(traits, Mapping) else {}
    forced = debug.get("force_tornado") if isinstance(debug, Mapping) else None
    if not isinstance(forced, Mapping) or not bool(forced.get("enabled")):
        return None
    start_tick = _safe_int(forced.get("start_tick"), tick)
    duration = max(24, _safe_int(forced.get("duration_ticks"), 360))
    if not (start_tick <= tick < start_tick + duration):
        return None
    x = _safe_float(forced.get("x"), 0.0)
    y = _safe_float(forced.get("y"), 0.0)
    dx = _safe_float(forced.get("dx"), 1.0)
    dy = _safe_float(forced.get("dy"), 0.0)
    magnitude = max(0.001, math.hypot(dx, dy))
    dx /= magnitude
    dy /= magnitude
    progress = _clamp((tick - start_tick) / float(duration))
    travel = _safe_float(forced.get("travel_tiles"), 18.0)
    return {
        "id": str(forced.get("id") or "debug-tornado"),
        "start_tick": start_tick,
        "end_tick": start_tick + duration,
        "duration_ticks": duration,
        "origin": (x, y),
        "center": (x + dx * travel * progress, y + dy * travel * progress, 0),
        "direction": (dx, dy),
        "progress": progress,
        "intensity": _clamp(forced.get("intensity", 0.86), 0.35, 1.0),
        "radius": max(1, min(4, _safe_int(forced.get("radius"), 2))),
        "debug_forced": True,
    }


def _tornado_candidate(sim, macro_x, macro_y, slot, *, tick):
    tick, ticks_per_hour = _clock(sim, tick=tick)
    cache_key = (getattr(sim, "seed", 0), int(macro_x), int(macro_y), int(slot), ticks_per_hour)
    cache = _candidate_cache(sim)
    base = cache.get(cache_key)
    if not isinstance(base, dict):
        seed = getattr(sim, "seed", 0)
        token = _stable_int(seed, "tornado", macro_x, macro_y, slot)
        slot_ticks = TORNADO_SLOT_HOURS * ticks_per_hour
        duration = int(round(ticks_per_hour * (0.48 + (((token >> 8) & 0xFFFF) / 0xFFFF) * 0.48)))
        start_tick = (int(slot) * slot_ticks) + int((token >> 25) % max(1, slot_ticks - duration))
        chunk_x = int(macro_x) * TORNADO_MACRO_CHUNKS + int((token >> 42) % TORNADO_MACRO_CHUNKS)
        chunk_y = int(macro_y) * TORNADO_MACRO_CHUNKS + int((token >> 49) % TORNADO_MACRO_CHUNKS)
        weather = weather_snapshot(sim, chunk_x, chunk_y, tick=start_tick)
        potential = tornado_potential(weather)
        genesis_roll = _stable_int(seed, weather.get("system_id"), macro_x, macro_y, slot, "funnel") / float((1 << 64) - 1)
        chance = tornado_genesis_chance(weather)
        qualifies = bool(chance > 0.0 and genesis_roll <= chance)
        span = max(1, int(getattr(sim, "chunk_size", 16) or 16))
        local_x = int((token >> 12) % span)
        local_y = int((token >> 18) % span)
        direction = _DIRECTION_VECTOR.get(str(weather.get("wind_direction", "e") or "e").strip().lower(), (1.0, 0.0))
        cross = ((((token >> 33) & 0xFF) / 255.0) - 0.5) * 0.34
        dx, dy = direction[0] - direction[1] * cross, direction[1] + direction[0] * cross
        magnitude = max(0.001, math.hypot(dx, dy))
        dx, dy = dx / magnitude, dy / magnitude
        intensity = _clamp(0.44 + potential * 0.55, 0.42, 1.0)
        base = {
            "id": f"TN-{int(slot):X}-{int(macro_x):+d}-{int(macro_y):+d}-{token & 0xFFFF:04X}",
            "qualifies": qualifies,
            "start_tick": start_tick,
            "end_tick": start_tick + duration,
            "duration_ticks": duration,
            "origin": ((chunk_x * span) + local_x, (chunk_y * span) + local_y),
            "direction": (dx, dy),
            "travel_tiles": 10.0 + (intensity * 16.0),
            "intensity": intensity,
            "radius": 1 if intensity < 0.58 else 2 if intensity < 0.84 else 3,
            "potential": potential,
            "weather_system_id": weather.get("system_id"),
            "genesis_roll": genesis_roll,
            "genesis_chance": chance,
        }
        if len(cache) >= 1024:
            cache.clear()
        cache[cache_key] = base
    if not bool(base.get("qualifies")) or not (_safe_int(base.get("start_tick")) <= tick < _safe_int(base.get("end_tick"))):
        return None
    progress = _clamp((tick - _safe_int(base["start_tick"])) / float(max(1, _safe_int(base["duration_ticks"], 1))))
    x = _safe_float(base["origin"][0]) + (_safe_float(base["direction"][0]) * _safe_float(base["travel_tiles"]) * progress)
    y = _safe_float(base["origin"][1]) + (_safe_float(base["direction"][1]) * _safe_float(base["travel_tiles"]) * progress)
    return {**base, "center": (x, y, 0), "progress": progress}


def active_tornadoes_near(sim, cx, cy, *, tick=None, radius_chunks=TORNADO_WARNING_RADIUS_CHUNKS):
    """Query the few deterministic macro candidates capable of reaching a chunk."""

    tick, ticks_per_hour = _clock(sim, tick=tick)
    forced = _forced_candidate(sim, tick=tick)
    rows = []
    if isinstance(forced, dict):
        forced_center = forced.get("center") or (0, 0, 0)
        span = max(1, int(getattr(sim, "chunk_size", 16) or 16))
        forced_cx = int(math.floor(_safe_float(forced_center[0]) / span))
        forced_cy = int(math.floor(_safe_float(forced_center[1]) / span))
        if max(abs(forced_cx - int(cx)), abs(forced_cy - int(cy))) <= max(0, int(radius_chunks)):
            rows.append(forced)
    slot_ticks = TORNADO_SLOT_HOURS * ticks_per_hour
    slot = math.floor(tick / slot_ticks)
    macro_x = math.floor(int(cx) / TORNADO_MACRO_CHUNKS)
    macro_y = math.floor(int(cy) / TORNADO_MACRO_CHUNKS)
    span = max(1, int(getattr(sim, "chunk_size", 16) or 16))
    seen = {str(row.get("id")) for row in rows}
    for candidate_slot in (slot - 1, slot):
        for my in range(macro_y - 1, macro_y + 2):
            for mx in range(macro_x - 1, macro_x + 2):
                row = _tornado_candidate(sim, mx, my, candidate_slot, tick=tick)
                if not isinstance(row, dict) or str(row.get("id")) in seen:
                    continue
                center = row.get("center") or (0, 0, 0)
                tornado_cx = int(math.floor(_safe_float(center[0]) / span))
                tornado_cy = int(math.floor(_safe_float(center[1]) / span))
                if max(abs(tornado_cx - int(cx)), abs(tornado_cy - int(cy))) > max(0, int(radius_chunks)):
                    continue
                seen.add(str(row.get("id")))
                rows.append(row)
    return tuple(sorted(rows, key=lambda row: str(row.get("id", ""))))


def weather_alert_at(sim, cx, cy, *, tick=None):
    """Return public watch/warning information, never a future funnel route."""

    tick, _ticks_per_hour = _clock(sim, tick=tick)
    cache = getattr(sim, "_weather_alert_cache", None)
    cache_key = (int(cx), int(cy), tick // TORNADO_IMPACT_INTERVAL)
    if not isinstance(cache, dict):
        cache = {}
        sim._weather_alert_cache = cache
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return dict(cached)
    active = active_tornadoes_near(sim, cx, cy, tick=tick)
    if active:
        strongest = max(active, key=lambda row: _safe_float(row.get("intensity")))
        result = {
            "level": "warning",
            "headline": "Tornado warning",
            "summary": "A funnel has been reported in the area. Take shelter in a strong interior room now.",
            "funnel_reported": True,
            "intensity": _safe_float(strongest.get("intensity")),
            "system_id": strongest.get("weather_system_id"),
        }
    else:
        samples = weather_forecast(sim, int(cx), int(cy), tick=tick, hours=(0, 1, 2, 3, 4, 6))
        risks = [(tornado_potential(sample), sample) for sample in samples]
        risk, sample = max(risks, key=lambda pair: pair[0])
        if risk >= 0.38:
            result = {
                "level": "watch",
                "headline": "Tornado watch",
                "summary": "Conditions could support a tornado. Know your nearest strong shelter and watch for a warning.",
                "funnel_reported": False,
                "intensity": risk,
                "forecast_offset_hours": _safe_int(sample.get("forecast_offset_hours")),
                "system_id": sample.get("system_id"),
            }
        elif any(bool(sample.get("storm_active")) for sample in samples):
            storm = max(samples, key=lambda row: _safe_float(row.get("storm_intensity")))
            result = {
                "level": "advisory",
                "headline": "Severe weather advisory",
                "summary": "Thunderstorms and strong wind are possible; travel and exposed work may become difficult.",
                "funnel_reported": False,
                "intensity": _safe_float(storm.get("storm_intensity")),
                "forecast_offset_hours": _safe_int(storm.get("forecast_offset_hours")),
                "system_id": storm.get("system_id"),
            }
        else:
            current = samples[0]
            result = {
                "level": "none",
                "headline": "No severe weather alert",
                "summary": f"No severe weather alert is posted. Current conditions: {str(current.get('condition', 'clear'))}.",
                "funnel_reported": False,
                "intensity": 0.0,
                "system_id": current.get("system_id"),
            }
    if len(cache) >= 256:
        cache.clear()
    cache[cache_key] = dict(result)
    return result


def weather_report_lines(sim, cx, cy, *, tick=None):
    current = weather_snapshot(sim, int(cx), int(cy), tick=tick)
    alert = weather_alert_at(sim, int(cx), int(cy), tick=tick)
    lines = [
        f"{alert['headline']}: {alert['summary']}",
        (
            f"Now: {str(current.get('condition', 'clear')).title()}, "
            f"{_safe_float(current.get('temperature_c')):.0f} C, "
            f"wind {current.get('wind_direction')} {_safe_float(current.get('wind_speed_kph')):.0f} km/h."
        ),
        "Forecast:",
    ]
    for sample in weather_forecast(sim, int(cx), int(cy), tick=tick, hours=(1, 3, 6, 12)):
        lines.append(
            f"+{_safe_int(sample.get('forecast_offset_hours'))}h: {str(sample.get('condition', 'clear'))}; "
            f"{_safe_float(sample.get('temperature_c')):.0f} C; wind {_safe_float(sample.get('wind_speed_kph')):.0f} km/h."
        )
    lines.append("Watches describe favorable conditions; warnings mean a funnel has actually been reported. Exact tracks remain uncertain.")
    return lines


def tornado_shelter_score(prop):
    if not isinstance(prop, Mapping) or str(prop.get("kind", "")).strip().lower() != "building":
        return 0.0
    metadata = property_metadata(prop)
    text = " ".join(
        str(metadata.get(key, "") or "").strip().lower()
        for key in ("archetype", "material", "construction", "structure_class")
    )
    text += " " + str(prop.get("name", "") or "").strip().lower()
    score = 0.54
    if any(term in text for term in ("bunker", "underground", "shelter", "concrete", "masonry", "courthouse", "hospital", "police", "station")):
        score += 0.34
    if any(term in text for term in ("tower", "warehouse", "factory", "brick", "secure")):
        score += 0.16
    if any(term in text for term in ("tent", "camp", "shack", "shed", "kiosk", "trailer", "wood")):
        score -= 0.30
    damage = metadata.get("structure_durability") if isinstance(metadata.get("structure_durability"), Mapping) else {}
    cells = damage.get("cells") if isinstance(damage.get("cells"), Mapping) else {}
    broken = sum(1 for row in cells.values() if isinstance(row, Mapping) and bool(row.get("broken")))
    score -= min(0.30, broken * 0.025)
    return _clamp(score, 0.08, 0.96)


def tornado_shelter_target(sim, x, y, z=0, *, radius=18):
    candidates = []
    for prop in tuple(sim.properties_in_radius(int(x), int(y), int(z), r=int(radius)) if hasattr(sim, "properties_in_radius") else ()):
        strength = tornado_shelter_score(prop)
        if strength < 0.42:
            continue
        focus = property_focus_position(prop)
        if not isinstance(focus, (tuple, list)) or len(focus) < 3 or int(focus[2]) != int(z):
            continue
        distance = abs(int(focus[0]) - int(x)) + abs(int(focus[1]) - int(y))
        candidates.append((strength * 100.0 - distance * 1.6, strength, str(prop.get("id", "")), prop, focus))
    if not candidates:
        return None
    _score, strength, _property_id, prop, focus = max(candidates, key=lambda row: (row[0], row[1], row[2]))
    return {
        "property_id": prop.get("id"),
        "property_name": prop.get("name") or prop.get("id"),
        "target": (int(focus[0]), int(focus[1]), int(focus[2])),
        "strength": strength,
    }


def _damage_actor(sim, eid, amount, *, tornado_id, x, y, z, source_kind="tornado"):
    vitality = sim.ecs.get(Vitality).get(eid)
    if vitality is None or bool(getattr(vitality, "downed", False)):
        return False
    amount = max(1, int(amount))
    before = max(0, _safe_int(getattr(vitality, "hp", 0)))
    vitality.hp = max(0, before - amount)
    sim.emit(Event(
        "entity_damaged",
        target_eid=eid,
        source_eid=None,
        weapon_id="tornado_debris" if source_kind == "debris" else "tornado",
        damage_kind="debris_impact" if source_kind == "debris" else "tornado",
        raw_damage=amount,
        damage=amount,
        cover_absorb=0.0,
        armor_absorb=0.0,
        hp=vitality.hp,
        max_hp=getattr(vitality, "max_hp", 1),
        tornado_id=tornado_id,
        x=int(x), y=int(y), z=int(z),
    ))
    if vitality.hp > 0:
        return True
    vitality.downed = True
    vitality.downed_tick = _safe_int(getattr(sim, "tick", 0))
    vitality.downed_count = _safe_int(getattr(vitality, "downed_count", 0)) + 1
    setattr(vitality, "death_reason", "tornado_debris" if source_kind == "debris" else "tornado")
    if eid == getattr(sim, "player_eid", None):
        sim.emit(Event("player_downed", target_eid=eid, source_eid=None, weapon_id="tornado", reason="tornado", damage_kind="tornado", x=x, y=y, z=z))
        return True
    _apply_downed_actor_state(sim, eid)
    collider = sim.ecs.get(Collider).get(eid)
    if collider:
        collider.blocks = False
    render = sim.ecs.get(Render).get(eid)
    if render:
        render.glyph = "x"
    sim.emit(Event("npc_downed", target_eid=eid, source_eid=None, weapon_id="tornado", reason="tornado", damage_kind="tornado", x=x, y=y, z=z))
    return True


def _move_actor(sim, eid, pos, x, y, z):
    if pos is None or sim.tilemap.tile_at(int(x), int(y), int(z)) is None:
        return False
    sim.tilemap.move_entity(eid, int(pos.x), int(pos.y), int(x), int(y), int(pos.z), int(z))
    pos.x, pos.y, pos.z = int(x), int(y), int(z)
    sim.emit(Event("entity_moved", eid=eid, x=int(x), y=int(y), z=int(z), forced=True, cause="tornado"))
    return True


def _impact_cells(center_x, center_y, radius):
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= radius * radius:
                yield int(center_x + dx), int(center_y + dy), 0, math.hypot(dx, dy)


def _move_vehicle_occupants(sim, vehicle_id, x, y, z):
    for eid in tuple(getattr(sim, "vehicle_occupants", {}).get(str(vehicle_id), ()) or ()):
        pos = sim.ecs.get(Position).get(eid)
        if pos is not None:
            _move_actor(sim, eid, pos, x, y, z)


def _ground_debris_impact(sim, ground, event, target_x, target_y, target_z):
    tornado_id = str(event.get("id", ""))
    metadata = ground.get("metadata") if isinstance(ground.get("metadata"), dict) else {}
    metadata["last_tornado_id"] = tornado_id
    metadata["last_tornado_toss_tick"] = _safe_int(getattr(sim, "tick", 0))
    metadata["tornado_debris"] = True
    ground["metadata"] = metadata
    sim.move_ground_item(ground.get("ground_item_id"), target_x, target_y, target_z)
    for eid in tuple(sim.tilemap.entities_at(target_x, target_y, target_z) or ()):
        _damage_actor(sim, eid, 3 + int(_safe_float(event.get("intensity")) * 9), tornado_id=tornado_id, x=target_x, y=target_y, z=target_z, source_kind="debris")
    prop = sim.property_covering(target_x, target_y, target_z) if hasattr(sim, "property_covering") else None
    if isinstance(prop, dict):
        apply_structural_damage(
            sim, prop, target_x, target_y, target_z,
            amount=4 + int(_safe_float(event.get("intensity")) * 11),
            cause="tornado_debris", damage_kind="debris_impact", weapon_id="tornado_debris",
        )
    item_def = ITEM_CATALOG.get(str(ground.get("item_id", "") or ""), {})
    tags = {str(tag).strip().lower() for tag in tuple(item_def.get("tags", ()) or ())}
    spark_source = bool(tags.intersection({"electronics", "battery", "fuel", "metal"}))
    spark_roll = _stable_int(getattr(sim, "seed", 0), tornado_id, ground.get("ground_item_id"), "spark") / float((1 << 64) - 1)
    if spark_source and spark_roll < 0.09 * _safe_float(event.get("intensity")):
        sim.emit(Event("tornado_debris_impact", tornado_id=tornado_id, x=target_x, y=target_y, z=target_z, spark_source=True, ground_item_id=ground.get("ground_item_id")))


def apply_tornado_impact_step(sim, event):
    """Apply one bounded physical slice at the funnel's current location."""

    center = event.get("center") if isinstance(event, Mapping) else None
    if not isinstance(center, (tuple, list)) or len(center) < 3:
        return {"actors": 0, "vehicles": 0, "structures": 0, "debris": 0}
    center_x, center_y, center_z = int(round(center[0])), int(round(center[1])), int(center[2])
    radius = max(1, min(4, _safe_int(event.get("radius"), 1)))
    intensity = _clamp(event.get("intensity", 0.5), 0.35, 1.0)
    dx, dy = event.get("direction") if isinstance(event.get("direction"), (tuple, list)) else (1.0, 0.0)
    actors_hit = set()
    structures_hit = set()
    for x, y, z, distance in _impact_cells(center_x, center_y, radius):
        prop = sim.property_covering(x, y, z) if hasattr(sim, "property_covering") else None
        shelter = tornado_shelter_score(prop) if isinstance(prop, dict) else 0.0
        if isinstance(prop, dict) and str(prop.get("kind", "")).strip().lower() == "building":
            result = apply_structural_damage(
                sim, prop, x, y, z,
                amount=max(1, int(round((4.0 + intensity * 15.0) * (1.0 - shelter * 0.64)))),
                cause="tornado", damage_kind="wind_debris", weapon_id="tornado",
            )
            if result.get("damaged"):
                structures_hit.add((str(prop.get("id", "")), x, y, z))
        for eid in tuple(sim.tilemap.entities_at(x, y, z) or ()):
            if eid in actors_hit:
                continue
            pos = sim.ecs.get(Position).get(eid)
            if pos is None:
                continue
            interior = bool(is_interior_tile(sim, x, y, z))
            protection = shelter if interior else 0.0
            exposure = _clamp(1.0 - protection * 0.94, 0.04, 1.0)
            damage = max(1, int(round((3.0 + intensity * 10.0) * exposure * (1.0 - distance / (radius + 1.0) * 0.28))))
            _damage_actor(sim, eid, damage, tornado_id=event.get("id"), x=x, y=y, z=z)
            if not interior and _stable_int(event.get("id"), event.get("impact_step"), eid, "lift") % 100 < int(38 * intensity):
                target_x = int(round(x + _safe_float(dx) * (1.0 + intensity * 3.0)))
                target_y = int(round(y + _safe_float(dy) * (1.0 + intensity * 3.0)))
                tile = sim.tilemap.tile_at(target_x, target_y, z)
                if tile is not None and bool(getattr(tile, "walkable", False)):
                    _move_actor(sim, eid, pos, target_x, target_y, z)
            actors_hit.add(eid)

    vehicles_hit = 0
    for prop in tuple(sim.properties_in_radius(center_x, center_y, center_z, r=radius) if hasattr(sim, "properties_in_radius") else ())[:8]:
        if not property_is_vehicle(prop):
            continue
        distance = abs(_safe_int(prop.get("x")) - center_x) + abs(_safe_int(prop.get("y")) - center_y)
        if distance > radius:
            continue
        loss = max(1, int(round(1.0 + intensity * 3.0 - distance * 0.3)))
        apply_vehicle_durability_loss(sim, prop, loss, cause="tornado")
        toss = max(1, int(round(2.0 + intensity * 5.0)))
        target_x = int(round(_safe_int(prop.get("x")) + _safe_float(dx) * toss))
        target_y = int(round(_safe_int(prop.get("y")) + _safe_float(dy) * toss))
        tile = sim.tilemap.tile_at(target_x, target_y, center_z)
        if tile is not None and bool(getattr(tile, "walkable", False)):
            if sim.move_property(prop.get("id"), target_x, target_y, center_z):
                _move_vehicle_occupants(sim, prop.get("id"), target_x, target_y, center_z)
        else:
            apply_vehicle_durability_loss(sim, prop, 1 + int(intensity * 2), cause="tornado_impact")
        metadata = property_metadata(prop)
        metadata["last_tornado_id"] = event.get("id")
        metadata["last_tornado_toss_tick"] = _safe_int(getattr(sim, "tick", 0))
        vehicles_hit += 1

    debris_hit = 0
    ground_rows = tuple(sim.ground_items_in_radius(center_x, center_y, center_z, r=radius) if hasattr(sim, "ground_items_in_radius") else ())[:10]
    for ground in ground_rows:
        if str((ground.get("metadata") or {}).get("last_tornado_id", "")) == str(event.get("id", "")):
            continue
        toss = 2 + int(intensity * 6) + int(_stable_int(event.get("id"), ground.get("ground_item_id"), event.get("impact_step")) % 3)
        target_x = int(round(_safe_int(ground.get("x")) + _safe_float(dx) * toss))
        target_y = int(round(_safe_int(ground.get("y")) + _safe_float(dy) * toss))
        if sim.tilemap.tile_at(target_x, target_y, center_z) is None:
            continue
        _ground_debris_impact(sim, ground, event, target_x, target_y, center_z)
        debris_hit += 1

    sim.emit(Event(
        "tornado_impact",
        tornado_id=event.get("id"), x=center_x, y=center_y, z=center_z,
        intensity=intensity, actors_hit=len(actors_hit), vehicles_hit=vehicles_hit,
        structures_hit=len(structures_hit), debris_tossed=debris_hit,
    ))
    return {"actors": len(actors_hit), "vehicles": vehicles_hit, "structures": len(structures_hit), "debris": debris_hit}


def tornado_render_cells(sim, left, top, right, bottom, *, z=0):
    if int(z) != 0:
        return ()
    traits = getattr(sim, "world_traits", {})
    state = traits.get("tornado_runtime", {}) if isinstance(traits, Mapping) else {}
    active = state.get("active", ()) if isinstance(state, Mapping) else ()
    cells = []
    for event in tuple(active or ()):
        center = event.get("center") if isinstance(event, Mapping) else None
        if not isinstance(center, (tuple, list)) or len(center) < 3:
            continue
        cx, cy = int(round(center[0])), int(round(center[1]))
        radius = max(1, _safe_int(event.get("radius"), 1))
        for x, y, _cell_z, distance in _impact_cells(cx, cy, radius):
            if int(left) <= x <= int(right) and int(top) <= y <= int(bottom):
                cells.append({
                    "x": x,
                    "y": y,
                    "kind": "funnel" if distance < 0.75 else "debris",
                    "strength": _clamp(_safe_float(event.get("intensity")) * (1.0 - distance / (radius + 1.0) * 0.45)),
                    "tornado_id": event.get("id"),
                })
    return tuple(cells)


class TornadoSystem(System):
    """Materialize deterministic funnels only where their route is loaded."""

    def __init__(self, sim):
        super().__init__(sim)
        self.runs_without_turn = True
        traits = getattr(sim, "world_traits", None)
        if not isinstance(traits, dict):
            sim.world_traits = {}
            traits = sim.world_traits
        state = traits.get("tornado_runtime")
        if not isinstance(state, dict):
            state = {}
            traits["tornado_runtime"] = state
        state.setdefault("model_version", TORNADO_MODEL_VERSION)
        state.setdefault("impact_steps", {})
        state.setdefault("reported", {})
        state.setdefault("active", [])

    def _loaded_chunks(self):
        loaded = getattr(getattr(self.sim, "world", None), "loaded_chunks", None)
        if isinstance(loaded, Mapping) and loaded:
            return tuple(loaded)
        active = getattr(self.sim, "active_chunk", None)
        if isinstance(active, (tuple, list)) and len(active) >= 2:
            return ((int(active[0]), int(active[1])),)
        return ((0, 0),)

    def update(self):
        now = _safe_int(getattr(self.sim, "tick", 0), 0)
        if now % TORNADO_IMPACT_INTERVAL != 0:
            return
        state = self.sim.world_traits["tornado_runtime"]
        active = {}
        loaded = set((int(row[0]), int(row[1])) for row in self._loaded_chunks())
        span = max(1, int(getattr(self.sim, "chunk_size", 16) or 16))
        for chunk in tuple(sorted(loaded)):
            for event in active_tornadoes_near(self.sim, chunk[0], chunk[1], tick=now, radius_chunks=1):
                center = event.get("center") or (0, 0, 0)
                center_chunk = (int(math.floor(_safe_float(center[0]) / span)), int(math.floor(_safe_float(center[1]) / span)))
                if center_chunk in loaded:
                    active[str(event.get("id"))] = event
        state["active"] = [dict(row) for row in active.values()]
        impacts = state.setdefault("impact_steps", {})
        reported = state.setdefault("reported", {})
        for tornado_id, event in active.items():
            if tornado_id not in reported:
                reported[tornado_id] = now
                center = event.get("center") or (0, 0, 0)
                self.sim.emit(Event("tornado_reported", tornado_id=tornado_id, x=int(round(center[0])), y=int(round(center[1])), z=0, intensity=event.get("intensity")))
            step = now // TORNADO_IMPACT_INTERVAL
            step_key = f"{tornado_id}:{step}"
            if step_key in impacts:
                continue
            event = dict(event)
            event["impact_step"] = step
            impacts[step_key] = now
            apply_tornado_impact_step(self.sim, event)
        cutoff = now - max(3600, TORNADO_SLOT_HOURS * _clock(self.sim)[1] * 2)
        for key, value in tuple(impacts.items()):
            if _safe_int(value) < cutoff:
                impacts.pop(key, None)
        if len(reported) > 96:
            oldest = sorted(reported, key=lambda key: _safe_int(reported.get(key)))[:-64]
            for key in oldest:
                reported.pop(key, None)


__all__ = [
    "TORNADO_IMPACT_INTERVAL",
    "TORNADO_WARNING_RADIUS_CHUNKS",
    "TornadoSystem",
    "active_tornadoes_near",
    "apply_tornado_impact_step",
    "tornado_genesis_chance",
    "tornado_potential",
    "tornado_render_cells",
    "tornado_shelter_score",
    "tornado_shelter_target",
    "weather_alert_at",
    "weather_report_lines",
]
