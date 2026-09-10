"""Narrow, stateful adapters from atmospheric truth into the wider simulation.

``weather_runtime`` remains query-only.  This module is where actors, food,
wildlife, and vehicles opt into that truth.  Keeping the adapters here lets a
future flora producer, animal lineage, or vehicle model consume weather without
making the atmospheric model depend on those systems.
"""

from __future__ import annotations

import hashlib

from engine.events import Event

from game.components import Position, VehicleState, WildlifeBehavior
from game.lighting import is_interior_tile
from game.property_runtime import property_metadata, vehicle_profile_from_property
from game.weather_runtime import ground_weather_snapshot, weather_snapshot


FOOD_WEATHER_CATEGORIES = frozenset((
    "ground_food",
    "wild_forage",
    "flora_produce",
))


def _clamp(value, low=0.0, high=1.0):
    return max(float(low), min(float(high), float(value)))


def _clock(sim, tick=None):
    tick = int(getattr(sim, "tick", 0) if tick is None else tick)
    traits = getattr(sim, "world_traits", {})
    config = traits.get("clock", {}) if isinstance(traits, dict) else {}
    try:
        ticks_per_hour = max(1, int(config.get("ticks_per_hour", 600)))
    except (AttributeError, TypeError, ValueError):
        ticks_per_hour = 600
    return tick, ticks_per_hour


def _weather_at(sim, x, y, *, tick=None):
    span = max(1, int(getattr(sim, "chunk_size", 16) or 16))
    tick = int(getattr(sim, "tick", 0) if tick is None else tick)
    key = (int(x) // span, int(y) // span)
    cache = getattr(sim, "_weather_effects_atmosphere_cache", None)
    if not isinstance(cache, dict) or int(cache.get("tick", -1)) != tick:
        cache = {"tick": tick, "cells": {}}
        setattr(sim, "_weather_effects_atmosphere_cache", cache)
    cells = cache.get("cells")
    if not isinstance(cells, dict):
        cells = {}
        cache["cells"] = cells
    if key not in cells:
        cells[key] = weather_snapshot(sim, key[0], key[1], tick=tick)
    return cells[key]


def _stable_unit(*parts):
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    value = int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big")
    return value / float((1 << 64) - 1)


def actor_weather_exposure(sim, eid, pos=None, *, tick=None):
    """Return modest hot/cold need multipliers for an exposed actor.

    This deliberately does not apply damage or statuses.  It is the bare needs
    bridge shared by the player, NPCs, and animals.
    """

    if pos is None:
        pos = sim.ecs.get(Position).get(eid)
    if pos is None or int(getattr(pos, "z", 0) or 0) != 0:
        return {
            "exposed": False,
            "shelter_factor": 0.0,
            "temperature_c": None,
            "heat_load": 0.0,
            "cold_load": 0.0,
            "hunger_drain_multiplier": 1.0,
            "thirst_drain_multiplier": 1.0,
            "energy_drain": 0.0,
        }

    x = int(pos.x)
    y = int(pos.y)
    if is_interior_tile(sim, x, y, 0):
        shelter_factor = 0.0
    else:
        state = sim.ecs.get(VehicleState).get(eid)
        shelter_factor = 0.28 if state is not None and bool(getattr(state, "in_vehicle", False)) else 1.0

    weather = _weather_at(sim, x, y, tick=tick)
    temperature = float(weather.get("temperature_c", 13.0) or 13.0)
    humidity = _clamp(float(weather.get("humidity_pct", 50.0) or 50.0) / 100.0)
    wind = max(0.0, float(weather.get("wind_speed_kph", 0.0) or 0.0))
    rain = float(weather.get("precipitation_intensity", 0.0) or 0.0) if str(weather.get("precipitation_kind", "none")) in {"rain", "sleet"} else 0.0

    heat_load = _clamp((temperature - 24.0) / 16.0) * (0.62 + (humidity * 0.38))
    wind_chill = max(0.0, wind - 8.0) / 54.0
    cold_load = _clamp((6.0 - temperature) / 22.0)
    cold_load = _clamp(cold_load * (1.0 + (wind_chill * 0.42) + (rain * 0.34)))
    heat_load *= shelter_factor
    cold_load *= shelter_factor
    return {
        "exposed": shelter_factor > 0.0,
        "shelter_factor": shelter_factor,
        "temperature_c": temperature,
        "humidity_pct": humidity * 100.0,
        "heat_load": heat_load,
        "cold_load": cold_load,
        "hunger_drain_multiplier": 1.0 + (cold_load * 0.32),
        "thirst_drain_multiplier": 1.0 + (heat_load * 0.78) + (cold_load * 0.08),
        "energy_drain": (heat_load * 0.012) + (cold_load * 0.014),
    }


def food_weather_availability(sim, category, x, y, z=0, *, tick=None):
    """Describe weather accessibility without creating any food supply.

    ``flora_produce`` is intentionally a provider contract only.  A later
    fruit-producing flora category can supply real units and multiply them by
    ``weather_factor``; this function never invents fruit or a plant record.
    """

    aliases = {
        "food": "ground_food",
        "scavenge": "ground_food",
        "forage": "wild_forage",
        "produce": "flora_produce",
        "fruit": "flora_produce",
    }
    category = aliases.get(str(category or "").strip().lower(), str(category or "").strip().lower())
    if category not in FOOD_WEATHER_CATEGORIES:
        category = "ground_food"
    ground = ground_weather_snapshot(sim, int(x), int(y), z=int(z), tick=tick)
    if int(z) != 0 or not bool(ground.get("active", False)):
        factor = 1.0
    else:
        effect = str(ground.get("effect", "none") or "none")
        strength = _clamp(ground.get("strength", 0.0) or 0.0)
        penalties = {
            "frozen_water": 0.82,
            "shallow_flood": 0.72,
            "snow_cover": 0.58,
            "ground_ice": 0.20,
            "puddle": 0.10,
            "soft_ground": 0.14,
        }
        factor = _clamp(1.0 - (float(penalties.get(effect, 0.0)) * strength), 0.12, 1.0)

    temperature = float(ground.get("temperature_c", 13.0) or 13.0)
    if category == "wild_forage":
        factor *= _clamp((temperature + 8.0) / 22.0, 0.16, 1.0)
    elif category == "flora_produce":
        growing_temperature = _clamp((temperature + 4.0) / 18.0, 0.0, 1.0)
        heat_stress = _clamp((38.0 - temperature) / 10.0, 0.18, 1.0)
        factor *= growing_temperature * heat_stress

    provider_bound = category != "flora_produce"
    return {
        "category": category,
        "weather_factor": _clamp(factor),
        "provider_bound": provider_bound,
        "provider_contract": "flora_bound_fruit_producer" if category == "flora_produce" else "existing_food_record",
        "supply_units": None,
        "ground_effect": str(ground.get("effect", "none") or "none"),
        "temperature_c": temperature,
    }


def hibernation_weather_state(sim, genome, behavior, pos, *, tick=None, commit=True):
    """Resolve the inherited cold-hibernation phenotype with thaw hysteresis."""

    abilities = {
        str(value).strip().lower()
        for value in (getattr(genome, "expressed", {}) or {}).get("abilities", ())
        if str(value).strip()
    }
    inherited = "hibernates_cold" in abilities
    tick, ticks_per_hour = _clock(sim, tick=tick)
    current = bool(getattr(behavior, "hibernating", False)) if behavior is not None else False
    if not inherited or pos is None:
        if commit and behavior is not None:
            behavior.hibernating = False
        return {"inherited": inherited, "active": False, "wants_hibernation": False, "reason": "trait_absent" if not inherited else "position_absent"}

    ground = ground_weather_snapshot(sim, int(pos.x), int(pos.y), z=int(pos.z), tick=tick)
    temperature = float(ground.get("temperature_c", _weather_at(sim, pos.x, pos.y, tick=tick).get("temperature_c", 13.0)) or 13.0)
    freeze_index = _clamp(ground.get("freeze_index", 0.0) or 0.0)
    roused_until = int(getattr(behavior, "hibernation_roused_until_tick", -1) or -1)
    roused = tick < roused_until
    enter = bool(not roused and temperature <= 2.5 and freeze_index >= 0.42)
    thawed = bool(temperature >= 6.0 and freeze_index <= 0.20)
    active = bool((current and not thawed and not roused) or (not current and enter))

    if commit and behavior is not None:
        if active and not current:
            behavior.hibernation_since_tick = tick
        if current and not active:
            behavior.hibernation_last_wake_tick = tick
        behavior.hibernating = active
        behavior.hibernation_last_weather_tick = tick
    return {
        "inherited": True,
        "active": active,
        "wants_hibernation": active or enter,
        "reason": "sustained_cold" if active else "temporarily_roused" if roused else "season_thawed",
        "temperature_c": temperature,
        "freeze_index": freeze_index,
        "minimum_rest_ticks": ticks_per_hour,
    }


def rouse_hibernating_animal(behavior, sim, *, hours=2.0):
    """Let immediate danger temporarily outrank seasonal torpor."""

    if behavior is None:
        return
    tick, ticks_per_hour = _clock(sim)
    behavior.hibernating = False
    behavior.hibernation_last_wake_tick = tick
    behavior.hibernation_roused_until_tick = tick + max(1, int(round(float(hours) * ticks_per_hour)))


def actor_is_hibernating(sim, eid):
    behavior = sim.ecs.get(WildlifeBehavior).get(eid)
    return bool(behavior is not None and getattr(behavior, "hibernating", False))


def _vehicle_is_exposed(sim, vehicle_prop, x, y, z):
    if int(z) != 0:
        return False
    return not is_interior_tile(sim, int(x), int(y), int(z))


def update_vehicle_wetness(sim, vehicle_prop, x, y, z=0, *, tick=None):
    """Persist exterior wetness while keeping its atmospheric source query-only."""

    metadata = property_metadata(vehicle_prop)
    tick, ticks_per_hour = _clock(sim, tick=tick)
    previous_tick = int(metadata.get("weather_wetness_tick", tick) or tick)
    elapsed_hours = max(0.0, min(48.0, float(tick - previous_tick) / float(ticks_per_hour)))
    wetness = _clamp(metadata.get("weather_wetness", 0.0) or 0.0)
    weather = _weather_at(sim, x, y, tick=tick)
    exposed = _vehicle_is_exposed(sim, vehicle_prop, x, y, z)
    kind = str(weather.get("precipitation_kind", "none") or "none")
    intensity = _clamp(weather.get("precipitation_intensity", 0.0) or 0.0)
    temperature = float(weather.get("temperature_c", 13.0) or 13.0)
    wet_input = intensity if exposed and kind in {"rain", "sleet"} else intensity * 0.20 if exposed and kind == "snow" else 0.0
    if wet_input > 0.0:
        wetness = max(wetness, wet_input * 0.28)
        wetness = _clamp(wetness + (wet_input * max(elapsed_hours, 1.0 / 60.0) * 1.8))
    elif elapsed_hours > 0.0:
        drying_rate = 0.10 + (max(0.0, temperature) * 0.008) + (float(weather.get("wind_speed_kph", 0.0) or 0.0) * 0.002)
        if not exposed:
            drying_rate *= 0.58
        wetness = _clamp(wetness - (elapsed_hours * drying_rate))

    metadata["weather_wetness"] = round(wetness, 6)
    metadata["weather_wetness_tick"] = tick
    metadata["weather_wet"] = wetness >= 0.08
    return {
        "exposed": exposed,
        "wetness": wetness,
        "wet": wetness >= 0.08,
        "precipitation_kind": kind,
        "precipitation_intensity": intensity,
        "temperature_c": temperature,
        "weather": weather,
    }


def vehicle_weather_control(sim, vehicle_prop, x, y, z=0, *, speed=1, tick=None):
    """Apply surface traction, crosswind, bogging, and deterministic recovery."""

    tick, _ticks_per_hour = _clock(sim, tick=tick)
    vehicle_id = str((vehicle_prop or {}).get("id", "vehicle") or "vehicle")
    profile = vehicle_profile_from_property(vehicle_prop) or {}
    metadata = property_metadata(vehicle_prop)
    wet = update_vehicle_wetness(sim, vehicle_prop, x, y, z, tick=tick)
    tile = sim.tilemap.tile_at(int(x), int(y), int(z))
    ground = ground_weather_snapshot(sim, int(x), int(y), z=int(z), tick=tick, tile=tile)
    weather = wet["weather"]
    surface_traction = _clamp(ground.get("traction_factor", 1.0) or 1.0, 0.20, 1.0)
    wind_load = _clamp(weather.get("cyclone_wind_load", 0.0) or 0.0)
    speed_factor = _clamp(float(max(1, int(speed or 1))) / 4.0, 0.25, 1.0)
    control_traction = _clamp(surface_traction - (wind_load * speed_factor * 0.22), 0.20, 1.0)
    surface_kind = str(ground.get("surface_kind", "natural") or "natural")
    effect = str(ground.get("effect", "none") or "none")
    strength = _clamp(ground.get("strength", 0.0) or 0.0)
    power = max(1, min(10, int(profile.get("power", 5) or 5)))
    vehicle_class = str(profile.get("vehicle_class", "sedan") or "sedan").strip().lower()
    capable_class = vehicle_class in {"pickup", "suv", "utility", "truck", "armored", "military"}

    route_risk_mult = 0.06 if surface_kind == "paved" else 0.38 if surface_kind == "trail" else 1.0
    bog_risk = 0.0
    if effect == "soft_ground":
        bog_risk = 0.08 + ((1.0 - control_traction) * 0.42) + (strength * 0.12)
    elif effect == "snow_cover":
        bog_risk = max(0.0, strength - 0.28) * 0.24
    elif effect == "shallow_flood":
        bog_risk = 0.08 + (strength * 0.18)
    bog_risk *= route_risk_mult
    bog_risk *= max(0.32, 1.18 - (power * 0.075) - (0.18 if capable_class else 0.0))
    bog_risk = _clamp(bog_risk, 0.0, 0.34)

    stuck = metadata.get("weather_stuck") if isinstance(metadata.get("weather_stuck"), dict) else None
    if stuck:
        attempts = max(0, int(stuck.get("attempts", 0) or 0)) + 1
        recovery_chance = _clamp(0.16 + (power * 0.045) + (attempts * 0.10) + (0.34 if surface_kind == "paved" else 0.10 if surface_kind == "trail" else 0.0), 0.12, 0.92)
        recovery_roll = _stable_unit(getattr(sim, "seed", 0), vehicle_id, "recover", tick, attempts, int(x), int(y))
        if recovery_roll >= recovery_chance:
            stuck["attempts"] = attempts
            stuck["last_attempt_tick"] = tick
            return {
                "allowed": False,
                "blocked_reason": "weather_stuck",
                "recovered": False,
                "bog_risk": bog_risk,
                "surface_traction": surface_traction,
                "control_traction": control_traction,
                "ground": ground,
                **wet,
            }
        metadata.pop("weather_stuck", None)
        sim.emit(Event(
            "vehicle_weather_recovered",
            eid=None,
            vehicle_id=vehicle_id,
            x=int(x),
            y=int(y),
            z=int(z),
            attempts=attempts,
        ))

    bog_roll = _stable_unit(getattr(sim, "seed", 0), vehicle_id, "bog", tick, int(x), int(y), effect)
    if bog_risk > 0.0 and bog_roll < bog_risk:
        metadata["weather_stuck"] = {
            "effect": effect,
            "x": int(x),
            "y": int(y),
            "z": int(z),
            "since_tick": tick,
            "attempts": 0,
        }
        return {
            "allowed": False,
            "blocked_reason": "weather_stuck",
            "recovered": False,
            "bog_risk": bog_risk,
            "surface_traction": surface_traction,
            "control_traction": control_traction,
            "ground": ground,
            **wet,
        }

    skid_risk = _clamp(max(0.0, 0.70 - control_traction) * 0.22 * speed_factor, 0.0, 0.12)
    skid_roll = _stable_unit(getattr(sim, "seed", 0), vehicle_id, "skid", tick, int(x), int(y), int(speed or 1))
    if skid_risk > 0.0 and skid_roll < skid_risk:
        return {
            "allowed": False,
            "blocked_reason": "weather_skid",
            "recovered": False,
            "bog_risk": bog_risk,
            "skid_risk": skid_risk,
            "surface_traction": surface_traction,
            "control_traction": control_traction,
            "ground": ground,
            **wet,
        }

    return {
        "allowed": True,
        "blocked_reason": None,
        "recovered": bool(stuck),
        "bog_risk": bog_risk,
        "skid_risk": skid_risk,
        "surface_traction": surface_traction,
        "control_traction": control_traction,
        "ground": ground,
        **wet,
    }
