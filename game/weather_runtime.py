"""Deterministic atmospheric truth, ground memory, and weather artifacts.

This module deliberately has no simulation-system side effects.  Weather is a
function of the world seed, chunk coordinate, and tick, so unloaded places and
future times can be inspected without advancing RNG state or realizing world
content.  Rain, snow, fog, lightning flashes, and thunder timing are derived from
that truth.  A continuous ground field integrates recent weather into saturation,
snowpack, ice, ponding, and rare shallow flooding for downstream systems.
"""

from __future__ import annotations

import hashlib
import math
from functools import lru_cache


WEATHER_MODEL_VERSION = 3
GROUND_WEATHER_MODEL_VERSION = 2
WEATHER_PRESSURE_CELL_CHUNKS = 14.0
WEATHER_FLOW_CHUNKS_PER_HOUR = 0.42
WEATHER_FORECAST_HOURS = (0, 3, 6, 12, 18, 24)
GROUND_HISTORY_HOURS = 120
GROUND_HISTORY_STEP_HOURS = 3

_MASK_64 = (1 << 64) - 1
_DIRECTION_LABELS = (
    "E",
    "SE",
    "S",
    "SW",
    "W",
    "NW",
    "N",
    "NE",
)


def _clamp(value, low, high):
    return max(float(low), min(float(high), float(value)))


def _stable_seed(value):
    if isinstance(value, int):
        return int(value) & _MASK_64
    payload = f"bakerrrr-weather-v{WEATHER_MODEL_VERSION}|{value!r}".encode("utf-8")
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big")


def _mix64(value):
    value = int(value) & _MASK_64
    value ^= value >> 30
    value = (value * 0xBF58476D1CE4E5B9) & _MASK_64
    value ^= value >> 27
    value = (value * 0x94D049BB133111EB) & _MASK_64
    value ^= value >> 31
    return value & _MASK_64


def _lattice_value(seed, x, y, salt):
    value = (
        int(seed)
        ^ ((int(x) * 0x9E3779B185EBCA87) & _MASK_64)
        ^ ((int(y) * 0xC2B2AE3D27D4EB4F) & _MASK_64)
        ^ ((int(salt) * 0x165667B19E3779F9) & _MASK_64)
    )
    return _mix64(value) / float(_MASK_64)


def _smoothstep(value):
    value = _clamp(value, 0.0, 1.0)
    return value * value * (3.0 - (2.0 * value))


def _value_noise(seed, x, y, salt):
    x0 = math.floor(float(x))
    y0 = math.floor(float(y))
    fx = _smoothstep(float(x) - x0)
    fy = _smoothstep(float(y) - y0)
    v00 = _lattice_value(seed, x0, y0, salt)
    v10 = _lattice_value(seed, x0 + 1, y0, salt)
    v01 = _lattice_value(seed, x0, y0 + 1, salt)
    v11 = _lattice_value(seed, x0 + 1, y0 + 1, salt)
    top = v00 + ((v10 - v00) * fx)
    bottom = v01 + ((v11 - v01) * fx)
    return top + ((bottom - top) * fy)


def _clock_values(sim, tick=None):
    tick = int(getattr(sim, "tick", 0) if tick is None else tick)
    traits = getattr(sim, "world_traits", {})
    clock = traits.get("clock", {}) if isinstance(traits, dict) else {}
    try:
        ticks_per_hour = max(1, int(clock.get("ticks_per_hour", 600)))
    except (AttributeError, TypeError, ValueError):
        ticks_per_hour = 600
    try:
        start_hour = float(clock.get("start_hour", 9.0))
    except (AttributeError, TypeError, ValueError):
        start_hour = 9.0
    elapsed_hours = float(tick) / float(ticks_per_hour)
    absolute_hours = start_hour + elapsed_hours
    day_index = math.floor(absolute_hours / 24.0)
    hour_of_day = absolute_hours % 24.0
    return {
        "tick": tick,
        "ticks_per_hour": ticks_per_hour,
        "elapsed_hours": elapsed_hours,
        "absolute_hours": absolute_hours,
        "day_index": int(day_index),
        "hour_of_day": hour_of_day,
    }


def _flow_vector(seed):
    angle = _lattice_value(seed, 0, 0, 701) * math.tau
    return math.cos(angle), math.sin(angle)


def _direction_label(dx, dy):
    if abs(float(dx)) < 1e-9 and abs(float(dy)) < 1e-9:
        return "calm"
    angle = math.atan2(float(dy), float(dx)) % math.tau
    index = int(round(angle / (math.tau / 8.0))) % 8
    return _DIRECTION_LABELS[index]


def _advected_xy(seed, cx, cy, hours, *, speed=1.0, cross=0.0):
    flow_x, flow_y = _flow_vector(seed)
    cross_x, cross_y = -flow_y, flow_x
    distance = float(hours) * WEATHER_FLOW_CHUNKS_PER_HOUR * float(speed)
    return (
        float(cx) - (flow_x * distance) - (cross_x * distance * float(cross)),
        float(cy) - (flow_y * distance) - (cross_y * distance * float(cross)),
    )


def _pressure_hpa(seed, cx, cy, hours):
    sx, sy = _advected_xy(seed, cx, cy, hours, speed=1.0)
    broad = _value_noise(seed, sx / WEATHER_PRESSURE_CELL_CHUNKS, sy / WEATHER_PRESSURE_CELL_CHUNKS, 11)
    detail = _value_noise(seed, (sx + 31.0) / 5.0, (sy - 17.0) / 5.0, 12)
    return 1013.25 + ((broad - 0.5) * 35.0) + ((detail - 0.5) * 5.0)


def _humidity_pct(seed, cx, cy, hours, pressure_hpa):
    sx, sy = _advected_xy(seed, cx, cy, hours, speed=1.14, cross=0.12)
    broad = _value_noise(seed, (sx - 9.0) / 10.0, (sy + 23.0) / 10.0, 21)
    texture = _value_noise(seed, sx / 4.0, sy / 4.0, 22)
    humidity = 22.0 + (broad * 65.0) + ((texture - 0.5) * 12.0)
    humidity += max(0.0, 1013.25 - float(pressure_hpa)) * 0.7
    return _clamp(humidity, 12.0, 99.0)


def _temperature_c(seed, cx, cy, hours, hour_of_day):
    sx, sy = _advected_xy(seed, cx, cy, hours, speed=0.72, cross=-0.10)
    air_mass = _value_noise(seed, (sx + 47.0) / 22.0, (sy - 29.0) / 22.0, 31)
    local = _value_noise(seed, sx / 8.0, sy / 8.0, 32)
    diurnal = math.sin(((float(hour_of_day) - 8.0) / 24.0) * math.tau) * 3.5
    return 13.0 + ((air_mass - 0.5) * 25.0) + ((local - 0.5) * 4.0) + diurnal


def _instability(seed, cx, cy, hours, temperature_c, humidity_pct):
    sx, sy = _advected_xy(seed, cx, cy, hours, speed=0.94, cross=-0.16)
    lifted = _value_noise(seed, (sx + 13.0) / 9.0, (sy + 5.0) / 9.0, 41)
    warm_humid = max(0.0, (float(temperature_c) - 12.0) / 22.0) * max(0.0, (float(humidity_pct) - 50.0) / 50.0)
    return _clamp((lifted * 0.72) + (warm_humid * 0.45), 0.0, 1.0)


def _precipitation_truth(pressure, humidity, temperature, instability):
    """Resolve shared cloud and precipitation values from one air sample."""

    cloud_cover = _clamp(
        ((float(humidity) - 38.0) * 1.25)
        + (max(0.0, 1014.0 - float(pressure)) * 1.7)
        + (float(instability) * 17.0),
        0.0,
        100.0,
    )
    precipitation_potential = _clamp(
        (cloud_cover * 0.46)
        + (max(0.0, float(humidity) - 58.0) * 0.82)
        + (max(0.0, 1011.0 - float(pressure)) * 2.0)
        + (float(instability) * 24.0)
        - 22.0,
        0.0,
        100.0,
    )
    precipitation_intensity = _smoothstep((precipitation_potential - 48.0) / 42.0)
    precipitation_active = precipitation_intensity >= 0.045
    wet_bulb_temperature = float(temperature) - max(0.0, (100.0 - float(humidity)) * 0.025)
    if not precipitation_active:
        precipitation_kind = "none"
    elif wet_bulb_temperature <= 1.2:
        precipitation_kind = "snow"
    elif wet_bulb_temperature <= 3.0:
        precipitation_kind = "sleet"
    else:
        precipitation_kind = "rain"
    return {
        "cloud_cover_pct": cloud_cover,
        "precipitation_potential_pct": precipitation_potential,
        "precipitation_active": precipitation_active,
        "precipitation_kind": precipitation_kind,
        "precipitation_intensity": precipitation_intensity,
        "wet_bulb_temperature_c": wet_bulb_temperature,
    }


def _dominant_pressure_system(seed, cx, cy, hours):
    sx, sy = _advected_xy(seed, cx, cy, hours, speed=1.0)
    lattice_x = int(round(sx / WEATHER_PRESSURE_CELL_CHUNKS))
    lattice_y = int(round(sy / WEATHER_PRESSURE_CELL_CHUNKS))
    token = _mix64(seed ^ (lattice_x * 0x9E3779B1) ^ (lattice_y * 0x85EBCA77) ^ 0xA7F04C3D)
    return f"P-{token & 0xFFFF:04X}", lattice_x, lattice_y


def _condition_label(
    *,
    cloud_cover_pct,
    precipitation_kind,
    precipitation_intensity,
    storm_intensity,
    fog_density,
):
    precipitation_kind = str(precipitation_kind or "none")
    precipitation_intensity = float(precipitation_intensity)
    if float(storm_intensity) >= 0.16:
        return "thunderstorm", "TS"
    if precipitation_kind == "snow":
        return ("heavy snow", "SN") if precipitation_intensity >= 0.68 else ("snow", "SN")
    if precipitation_kind == "sleet":
        return "sleet", "SL"
    if precipitation_kind == "rain":
        if precipitation_intensity >= 0.68:
            return "heavy rain", "RN"
        if precipitation_intensity >= 0.28:
            return "rain", "RN"
        return "drizzle", "DZ"
    if float(fog_density) >= 0.14:
        return "fog", "FG"
    if float(cloud_cover_pct) >= 78.0:
        return "overcast", "OV"
    if float(cloud_cover_pct) >= 52.0:
        return "broken cloud", "BC"
    if float(cloud_cover_pct) >= 30.0:
        return "high cloud", "HC"
    return "clear", "CL"


def _cyclone_truth(seed, pressure_hpa, storm_intensity, wind_speed_kph, system_id):
    """Classify an organized rotating low without creating a scripted event.

    Cyclones are a rare, stronger expression of the same advected pressure,
    moisture, wind, and instability fields as ordinary weather.  Their identity
    therefore travels with the pressure system and is stable under save/load or
    query order.  Rotation is world-seeded rather than tied to an Earth
    hemisphere.
    """

    pressure_drive = _smoothstep((1008.0 - float(pressure_hpa)) / 10.0)
    storm_drive = _smoothstep((float(storm_intensity) - 0.12) / 0.76)
    wind_drive = _smoothstep((float(wind_speed_kph) - 16.0) / 34.0)
    organized = bool(
        float(pressure_hpa) <= 1005.5
        and float(storm_intensity) >= 0.28
        and float(wind_speed_kph) >= 20.0
    )
    intensity = _clamp(
        (pressure_drive * 0.34) + (storm_drive * 0.46) + (wind_drive * 0.20),
        0.0,
        1.0,
    ) if organized else 0.0
    if not organized:
        classification = "none"
    elif intensity >= 0.76:
        classification = "severe_cyclone"
    elif intensity >= 0.56:
        classification = "cyclone"
    else:
        classification = "cyclonic_storm"

    token = _mix64(int(seed) ^ _stable_seed(str(system_id)) ^ 0xC7C10E)
    rotation = "clockwise" if token & 1 else "counterclockwise"
    return {
        "cyclone_active": organized,
        "cyclone_id": f"CY-{system_id}" if organized else "",
        "cyclone_class": classification,
        "cyclone_intensity": intensity,
        "cyclone_intensity_pct": intensity * 100.0,
        "cyclone_rotation": rotation if organized else "none",
        # Consumers can choose their own material response to these normalized
        # physical loads instead of importing cyclone labels.
        "cyclone_wind_load": _clamp(intensity * wind_drive, 0.0, 1.0),
        "cyclone_runoff_load": _clamp(intensity * float(storm_intensity), 0.0, 1.0),
        "cyclone_debris_risk": _clamp((intensity - 0.52) * 0.42, 0.0, 0.20),
    }


def _lightning_artifact(seed, cx, cy, clock, storm_intensity, system_id, *, chunk_size):
    """Return a stable bolt identity/location and the brief visible flash phase."""

    storm_intensity = _clamp(storm_intensity, 0.0, 1.0)
    empty = {
        "lightning_event_id": "",
        "lightning_flash": 0.0,
        "lightning_strike_world": None,
        "lightning_strike_local": None,
    }
    if storm_intensity < 0.16:
        return empty

    tick = int(clock["tick"])
    ticks_per_hour = max(1, int(clock["ticks_per_hour"]))
    slot_ticks = max(6, int(round(ticks_per_hour / 24.0)))
    slot = math.floor(tick / slot_ticks)
    event_token = _mix64(
        int(seed)
        ^ ((int(cx) * 0xD6E8FEB86659FD93) & _MASK_64)
        ^ ((int(cy) * 0xA5A3564E27F8862B) & _MASK_64)
        ^ ((int(slot) * 0x9E3779B185EBCA87) & _MASK_64)
        ^ 0xB01751A7
    )
    strike_chance = 0.012 + (0.14 * (storm_intensity ** 1.45))
    if (event_token & 0xFFFFFF) / float(0xFFFFFF) >= strike_chance:
        return empty

    chunk_size = max(1, int(chunk_size))
    local_x = int((event_token >> 24) % chunk_size)
    local_y = int((event_token >> 40) % chunk_size)
    strike_world = (
        (int(cx) * chunk_size) + local_x,
        (int(cy) * chunk_size) + local_y,
        0,
    )
    phase = tick - (int(slot) * slot_ticks)
    flash_ticks = max(2, min(5, int(round(slot_ticks * 0.16))))
    if phase >= flash_ticks:
        flash = 0.0
    else:
        flash = storm_intensity * (1.0 - (float(phase) / float(flash_ticks)))
        if phase == 1 and flash_ticks >= 3:
            flash *= 0.46
        elif phase == 2 and flash_ticks >= 4:
            flash *= 0.82
    return {
        "lightning_event_id": f"L-{system_id}-{int(slot):X}-{event_token & 0xFFFF:04X}",
        "lightning_flash": _clamp(flash, 0.0, 1.0),
        "lightning_strike_world": strike_world,
        "lightning_strike_local": (local_x, local_y),
    }


def weather_snapshot(sim, cx, cy, *, tick=None):
    """Return atmospheric truth without reading or mutating loaded world state."""

    cx = int(cx)
    cy = int(cy)
    clock = _clock_values(sim, tick=tick)
    seed = _stable_seed(getattr(sim, "seed", 0))
    hours = float(clock["elapsed_hours"])
    hour_of_day = float(clock["hour_of_day"])

    pressure = _pressure_hpa(seed, cx, cy, hours)
    pressure_future = _pressure_hpa(seed, cx, cy, hours + 3.0)
    pressure_dx = (_pressure_hpa(seed, cx + 1, cy, hours) - _pressure_hpa(seed, cx - 1, cy, hours)) / 2.0
    pressure_dy = (_pressure_hpa(seed, cx, cy + 1, hours) - _pressure_hpa(seed, cx, cy - 1, hours)) / 2.0
    pressure_gradient = math.hypot(pressure_dx, pressure_dy)

    humidity = _humidity_pct(seed, cx, cy, hours, pressure)
    temperature = _temperature_c(seed, cx, cy, hours, hour_of_day)
    temperature_future = _temperature_c(
        seed,
        cx,
        cy,
        hours + 3.0,
        hour_of_day,
    )
    temperature_dx = (
        _temperature_c(seed, cx + 1, cy, hours, hour_of_day)
        - _temperature_c(seed, cx - 1, cy, hours, hour_of_day)
    ) / 2.0
    temperature_dy = (
        _temperature_c(seed, cx, cy + 1, hours, hour_of_day)
        - _temperature_c(seed, cx, cy - 1, hours, hour_of_day)
    ) / 2.0
    temperature_gradient = math.hypot(temperature_dx, temperature_dy)

    instability = _instability(seed, cx, cy, hours, temperature, humidity)
    precipitation = _precipitation_truth(pressure, humidity, temperature, instability)
    cloud_cover = float(precipitation["cloud_cover_pct"])
    precipitation_potential = float(precipitation["precipitation_potential_pct"])
    dew_point = temperature - ((100.0 - humidity) / 5.0)

    flow_x, flow_y = _flow_vector(seed)
    wind_x = (flow_x * 0.8) - (pressure_dx * 0.15) - (pressure_dy * 0.10)
    wind_y = (flow_y * 0.8) - (pressure_dy * 0.15) + (pressure_dx * 0.10)
    wind_magnitude = math.hypot(wind_x, wind_y)
    if wind_magnitude <= 1e-9:
        wind_x, wind_y = flow_x, flow_y
        wind_magnitude = max(1e-9, math.hypot(wind_x, wind_y))
    wind_x /= wind_magnitude
    wind_y /= wind_magnitude
    wind_speed = _clamp(
        5.0 + (pressure_gradient * 7.5) + (abs(1013.25 - pressure) * 0.30) + (instability * 13.0),
        2.0,
        72.0,
    )

    precipitation_intensity = float(precipitation["precipitation_intensity"])
    precipitation_active = bool(precipitation["precipitation_active"])
    wet_bulb_temperature = float(precipitation["wet_bulb_temperature_c"])
    precipitation_kind = str(precipitation["precipitation_kind"])
    convective_strength = _smoothstep((instability - 0.48) / 0.34)
    storm_intensity = precipitation_intensity * convective_strength
    saturation = _smoothstep((humidity - 80.0) / 18.0)
    calm_air = 1.0 - _smoothstep((wind_speed - 6.0) / 38.0)
    predawn_cooling = (math.cos(((hour_of_day - 5.0) / 24.0) * math.tau) + 1.0) * 0.5
    fog_density = saturation * calm_air * (0.58 + (0.42 * predawn_cooling))
    fog_density *= 1.0 - (precipitation_intensity * 0.72)
    fog_density = _clamp(fog_density, 0.0, 1.0)

    front_strength = _clamp(
        (temperature_gradient * 24.0) + (pressure_gradient * 5.0) - 8.0,
        0.0,
        100.0,
    )
    temperature_tendency = temperature_future - temperature
    if front_strength < 22.0:
        front_kind = "none"
    elif temperature_tendency <= -0.45:
        front_kind = "cold"
    elif temperature_tendency >= 0.45:
        front_kind = "warm"
    else:
        front_kind = "stationary"

    condition, condition_code = _condition_label(
        cloud_cover_pct=cloud_cover,
        precipitation_kind=precipitation_kind,
        precipitation_intensity=precipitation_intensity,
        storm_intensity=storm_intensity,
        fog_density=fog_density,
    )
    system_id, system_lattice_x, system_lattice_y = _dominant_pressure_system(seed, cx, cy, hours)
    cyclone = _cyclone_truth(seed, pressure, storm_intensity, wind_speed, system_id)
    if cyclone["cyclone_active"]:
        condition = str(cyclone["cyclone_class"]).replace("_", " ")
        map_code = "CY"
    elif condition_code in {"CL", "HC", "BC", "OV"}:
        if front_kind == "cold":
            map_code = "CF"
        elif front_kind == "warm":
            map_code = "WF"
        elif pressure <= 1003.0:
            map_code = "LO"
        elif pressure >= 1023.0:
            map_code = "HI"
        else:
            map_code = condition_code
    else:
        map_code = condition_code

    lightning = _lightning_artifact(
        seed,
        cx,
        cy,
        clock,
        storm_intensity,
        system_id,
        chunk_size=getattr(sim, "chunk_size", 16),
    )
    pressure_kind = "low" if pressure < 1009.0 else "high" if pressure > 1017.0 else "neutral"
    pressure_delta = pressure_future - pressure
    if pressure_delta <= -0.6:
        pressure_tendency = "falling"
    elif pressure_delta >= 0.6:
        pressure_tendency = "rising"
    else:
        pressure_tendency = "steady"

    return {
        "model_version": WEATHER_MODEL_VERSION,
        "seed": getattr(sim, "seed", 0),
        "tick": int(clock["tick"]),
        "ticks_per_hour": int(clock["ticks_per_hour"]),
        "day_index": int(clock["day_index"]),
        "hour_of_day": hour_of_day,
        "chunk": (cx, cy),
        "condition": condition,
        "map_code": map_code,
        "pressure_hpa": pressure,
        "pressure_kind": pressure_kind,
        "pressure_tendency": pressure_tendency,
        "pressure_delta_3h": pressure_delta,
        "humidity_pct": humidity,
        "temperature_c": temperature,
        "temperature_tendency_3h": temperature_tendency,
        "dew_point_c": dew_point,
        "cloud_cover_pct": cloud_cover,
        "instability_pct": instability * 100.0,
        "precipitation_potential_pct": precipitation_potential,
        "precipitation_active": precipitation_active,
        "precipitation_kind": precipitation_kind,
        "precipitation_intensity": precipitation_intensity,
        "precipitation_intensity_pct": precipitation_intensity * 100.0,
        "wet_bulb_temperature_c": wet_bulb_temperature,
        "storm_active": storm_intensity >= 0.16,
        "storm_intensity": storm_intensity,
        "storm_intensity_pct": storm_intensity * 100.0,
        "storm_darkness": _clamp(0.08 + (storm_intensity * 0.46), 0.0, 0.58) if storm_intensity >= 0.16 else 0.0,
        "fog_active": fog_density >= 0.14,
        "fog_density": fog_density,
        "fog_density_pct": fog_density * 100.0,
        "gameplay_effects_active": True,
        "active_gameplay_effects": (
            "ground",
            "fishing",
            "exposed_campfires",
            "frozen_water_passage",
            "vehicle_weather",
            "wildlife_food",
            "hibernation",
            "tornadoes",
        ),
        "front_kind": front_kind,
        "front_strength_pct": front_strength,
        "system_id": system_id,
        "system_lattice": (system_lattice_x, system_lattice_y),
        "pattern_direction": _direction_label(flow_x, flow_y),
        "pattern_speed_chunks_per_hour": WEATHER_FLOW_CHUNKS_PER_HOUR,
        "wind_direction": _direction_label(wind_x, wind_y),
        "wind_speed_kph": wind_speed,
        **cyclone,
        **lightning,
    }


@lru_cache(maxsize=16384)
def _ground_history_context(seed, cx, cy, elapsed_hour, start_hour):
    """Integrate a coarse weather history without realizing or mutating a chunk."""

    seed = int(seed)
    cx = int(cx)
    cy = int(cy)
    elapsed_hour = int(elapsed_hour)
    start_hour = float(start_hour)
    climate_texture = _value_noise(seed, (cx - 19.0) / 11.0, (cy + 7.0) / 11.0, 811)
    moisture_equilibrium = 0.24 + (climate_texture * 0.34)
    saturation = moisture_equilibrium
    snowpack = 0.0
    freeze_index = 0.0
    runoff = 0.0
    recent_liquid = 0.0
    current = None

    first_hour = elapsed_hour - int(GROUND_HISTORY_HOURS)
    for sample_hour in range(first_hour, elapsed_hour + 1, int(GROUND_HISTORY_STEP_HOURS)):
        hour_of_day = (start_hour + float(sample_hour)) % 24.0
        pressure = _pressure_hpa(seed, cx, cy, float(sample_hour))
        humidity = _humidity_pct(seed, cx, cy, float(sample_hour), pressure)
        temperature = _temperature_c(seed, cx, cy, float(sample_hour), hour_of_day)
        instability = _instability(seed, cx, cy, float(sample_hour), temperature, humidity)
        precipitation = _precipitation_truth(pressure, humidity, temperature, instability)
        intensity = float(precipitation["precipitation_intensity"])
        kind = str(precipitation["precipitation_kind"])

        snow_input = intensity * (0.42 if kind == "snow" else 0.16 if kind == "sleet" else 0.0)
        snowpack = _clamp(snowpack + snow_input - 0.004, 0.0, 1.5)
        melt = 0.0
        if temperature > 0.8 and snowpack > 0.0:
            melt = min(snowpack, min(0.22, (temperature - 0.8) * 0.012 + (0.035 * intensity if kind == "rain" else 0.0)))
            snowpack -= melt

        liquid = melt * 0.85
        if kind == "rain":
            liquid += intensity * 0.36
        elif kind == "sleet":
            liquid += intensity * 0.13

        equilibrium_pull = (moisture_equilibrium - saturation) * 0.035
        evaporation = 0.002 + (max(0.0, temperature) * 0.00028) + ((1.0 - (humidity / 100.0)) * 0.004)
        drainage = 0.003 + (0.003 * (1.0 - climate_texture))
        saturation = _clamp(saturation + equilibrium_pull + (liquid * 0.86) - evaporation - drainage, 0.0, 1.0)
        excess = max(0.0, saturation - 0.80)
        runoff = _clamp((runoff * 0.72) + (excess * 0.78) + (liquid * saturation * 0.30), 0.0, 1.0)
        recent_liquid = _clamp((recent_liquid * 0.70) + liquid, 0.0, 1.0)

        if temperature <= 1.5:
            freeze_index = _clamp(freeze_index + min(0.12, 0.016 + ((1.5 - temperature) * 0.013)), 0.0, 1.0)
        elif temperature < 4.0:
            freeze_index = _clamp(freeze_index - 0.010, 0.0, 1.0)
        else:
            freeze_index = _clamp(freeze_index - min(0.16, (temperature - 3.0) * 0.014), 0.0, 1.0)

        current = {
            "temperature_c": temperature,
            "humidity_pct": humidity,
            "current_rain": intensity if kind == "rain" else 0.0,
            "current_snow": intensity if kind == "snow" else 0.0,
            "current_sleet": intensity if kind == "sleet" else 0.0,
        }

    current = current or {
        "temperature_c": 13.0,
        "humidity_pct": 50.0,
        "current_rain": 0.0,
        "current_snow": 0.0,
        "current_sleet": 0.0,
    }
    return {
        **current,
        "soil_saturation": saturation,
        "snowpack": snowpack,
        "freeze_index": freeze_index,
        "runoff": runoff,
        "recent_liquid": recent_liquid,
    }


def relative_ground_height(sim, world_x, world_y):
    """Return a smooth 0..1 drainage-height proxy in continuous world space."""

    seed = _stable_seed(getattr(sim, "seed", 0))
    x = float(world_x)
    y = float(world_y)
    broad = _value_noise(seed, (x + 37.0) / 192.0, (y - 61.0) / 192.0, 821)
    local = _value_noise(seed, (x - 11.0) / 52.0, (y + 29.0) / 52.0, 822)
    detail = _value_noise(seed, (x + 3.0) / 19.0, (y - 5.0) / 19.0, 823)
    return _clamp((broad * 0.62) + (local * 0.29) + (detail * 0.09), 0.0, 1.0)


def _ground_lattice_context(sim, world_x, world_y, *, tick=None, cache=None):
    clock = _clock_values(sim, tick=tick)
    span = max(1, int(getattr(sim, "chunk_size", 16) or 16))
    gx = ((float(world_x) + 0.5) / float(span)) - 0.5
    gy = ((float(world_y) + 0.5) / float(span)) - 0.5
    x0 = math.floor(gx)
    y0 = math.floor(gy)
    fx = _smoothstep(gx - x0)
    fy = _smoothstep(gy - y0)
    seed = _stable_seed(getattr(sim, "seed", 0))
    elapsed_hour = math.floor(float(clock["elapsed_hours"]))
    start_hour = float(clock["absolute_hours"]) - float(clock["elapsed_hours"])

    def sample(cx, cy):
        key = (int(seed), int(cx), int(cy), int(elapsed_hour), round(start_hour, 6))
        if isinstance(cache, dict) and key in cache:
            return cache[key]
        value = _ground_history_context(*key)
        if isinstance(cache, dict):
            cache[key] = value
        return value

    corners = (
        (sample(x0, y0), (1.0 - fx) * (1.0 - fy)),
        (sample(x0 + 1, y0), fx * (1.0 - fy)),
        (sample(x0, y0 + 1), (1.0 - fx) * fy),
        (sample(x0 + 1, y0 + 1), fx * fy),
    )
    keys = tuple(corners[0][0])
    return {
        key: sum(float(values.get(key, 0.0)) * weight for values, weight in corners)
        for key in keys
    }


def _surface_profile(sim, world_x, world_y, tile):
    glyph = str(getattr(tile, "glyph", ".") or ".")[:1]
    semantic = str(getattr(tile, "semantic_id", "") or "").strip().lower()
    color = str(getattr(tile, "color", "") or "").strip().lower()
    water = glyph == "~" or semantic == "terrain_water"
    area_type = ""
    if not water:
        try:
            cx, cy = sim.chunk_coords(int(world_x), int(world_y))
            descriptor = sim.world.overworld_descriptor(cx, cy)
            area_type = str(descriptor.get("area_type", "") or "").strip().lower()
        except (AttributeError, TypeError, ValueError):
            area_type = ""
    paved = (
        glyph == "="
        or "terrain_road" in {semantic, color}
        or (area_type == "city" and glyph in {".", "%", ";", ":"})
    )
    if water:
        permeability = 0.0
    elif paved:
        permeability = 0.08
    elif glyph == "_" or "salt" in semantic or "salt" in color:
        permeability = 0.82
    elif glyph == ":" or "trail" in semantic or "trail" in color:
        permeability = 0.50
    elif glyph == "," or "brush" in semantic or "brush" in color:
        permeability = 0.72
    else:
        permeability = 0.60
    return {
        "glyph": glyph,
        "water": water,
        "paved": paved,
        "permeability": permeability,
        "walkable": bool(getattr(tile, "walkable", tile is None)),
    }


def ground_weather_snapshot(sim, world_x, world_y, *, z=0, tick=None, tile=None, cache=None):
    """Resolve accumulated snow, ice, softness, ponding, and rare flooding."""

    world_x = int(world_x)
    world_y = int(world_y)
    z = int(z)
    if z != 0:
        return {
            "active": False,
            "effect": "none",
            "relative_height": relative_ground_height(sim, world_x, world_y),
        }
    if tile is None:
        tilemap = getattr(sim, "tilemap", None)
        tile = tilemap.tile_at(world_x, world_y, z) if tilemap is not None else None

    climate = _ground_lattice_context(sim, world_x, world_y, tick=tick, cache=cache)
    surface = _surface_profile(sim, world_x, world_y, tile)
    height = relative_ground_height(sim, world_x, world_y)
    lowland = _smoothstep((0.38 - height) / 0.34)
    highland = _smoothstep((height - 0.58) / 0.34)
    texture_seed = _stable_seed(getattr(sim, "seed", 0))
    micro = _value_noise(texture_seed, (world_x + 5.0) / 13.0, (world_y - 9.0) / 13.0, 824) - 0.5
    saturation = _clamp(
        float(climate["soil_saturation"])
        + (lowland * 0.20)
        - (highland * 0.11)
        + (micro * 0.10),
        0.0,
        1.0,
    )
    snow_strength = _clamp(
        (float(climate["snowpack"]) * 1.45) + (float(climate["current_snow"]) * 0.22),
        0.0,
        1.0,
    )
    freeze_index = _clamp(climate["freeze_index"], 0.0, 1.0)
    ice_strength = _smoothstep((freeze_index - 0.26) / 0.46)
    current_temperature = float(climate["temperature_c"])
    water_frozen = bool(surface["water"] and ice_strength >= 0.16 and current_temperature <= 1.8)
    supports_foot_traffic = bool(water_frozen and ice_strength >= 0.46 and current_temperature <= 0.5)
    supports_vehicle_traffic = bool(water_frozen and ice_strength >= 0.82 and current_temperature <= -2.0)
    ground_ice = bool(
        not surface["water"]
        and surface["walkable"]
        and saturation >= 0.62
        and ice_strength >= 0.20
        and snow_strength < 0.46
        and current_temperature <= 1.5
    )
    snow_cover = bool(
        snow_strength >= 0.07
        and current_temperature <= 4.5
        and (not surface["water"] or water_frozen)
    )

    nearby_water = False
    tilemap = getattr(sim, "tilemap", None)
    if tilemap is not None and not surface["water"]:
        for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0), (-1, -1), (1, -1), (1, 1), (-1, 1)):
            neighbor = tilemap.tile_at(world_x + dx, world_y + dy, z)
            if neighbor is not None and str(getattr(neighbor, "glyph", "") or "")[:1] == "~":
                nearby_water = True
                break

    recent_liquid = _clamp(climate["recent_liquid"], 0.0, 1.0)
    runoff = _clamp(climate["runoff"], 0.0, 1.0)
    ponding = _clamp(
        ((saturation - 0.68) * 1.45)
        + (lowland * 0.24)
        + ((1.0 - float(surface["permeability"])) * recent_liquid * 0.34),
        0.0,
        1.0,
    )
    flooded = bool(
        surface["walkable"]
        and not surface["water"]
        and not ground_ice
        and saturation >= 0.94
        and runoff >= 0.42
        and height <= (0.34 if nearby_water else 0.24)
    )
    flood_depth = _clamp((saturation - 0.92) * 1.1 + runoff * 0.11, 0.0, 0.18) if flooded else 0.0
    puddled = bool(
        surface["walkable"]
        and not surface["water"]
        and not flooded
        and not ground_ice
        and ponding >= 0.23
        and (surface["paved"] or height <= 0.42 or nearby_water)
    )
    soft_ground = bool(
        surface["walkable"]
        and not surface["water"]
        and not surface["paved"]
        and not flooded
        and not ground_ice
        and saturation >= 0.61
        and current_temperature > -0.5
    )

    if water_frozen:
        effect = "frozen_water"
        strength = ice_strength
    elif flooded:
        effect = "shallow_flood"
        strength = _clamp(flood_depth / 0.18, 0.0, 1.0)
    elif snow_cover:
        effect = "snow_cover"
        strength = snow_strength
    elif ground_ice:
        effect = "ground_ice"
        strength = ice_strength
    elif puddled:
        effect = "puddle"
        strength = ponding
    elif soft_ground:
        effect = "soft_ground"
        strength = _smoothstep((saturation - 0.56) / 0.40)
    else:
        effect = "none"
        strength = 0.0

    traction = _clamp(
        1.0
        - (0.48 * ice_strength if water_frozen or ground_ice else 0.0)
        - (0.19 * snow_strength if snow_cover else 0.0)
        - (0.18 * strength if soft_ground else 0.0)
        - (0.15 * ponding if puddled else 0.0)
        - (0.36 * strength if flooded else 0.0),
        0.35,
        1.0,
    )
    route_surface = "paved" if surface["paved"] else "trail" if surface["glyph"] == ":" else "natural"
    if route_surface == "paved" and not (water_frozen or ground_ice):
        traction = max(0.84, traction)
    elif route_surface == "trail" and not (water_frozen or ground_ice):
        traction = max(0.72, traction)

    return {
        "model_version": GROUND_WEATHER_MODEL_VERSION,
        "active": effect != "none",
        "effect": effect,
        "strength": strength,
        "relative_height": height,
        "soil_saturation": saturation,
        "snowpack": _clamp(climate["snowpack"], 0.0, 1.5),
        "snow_cover": snow_cover,
        "freeze_index": freeze_index,
        "ice_strength": ice_strength,
        "water_frozen": water_frozen,
        "supports_foot_traffic": supports_foot_traffic,
        "supports_vehicle_traffic": supports_vehicle_traffic,
        "ground_ice": ground_ice,
        "soft_ground": soft_ground,
        "puddled": puddled,
        "ponding": ponding,
        "flooded": flooded,
        "flood_depth": flood_depth,
        "runoff": runoff,
        "near_water": nearby_water,
        "surface_kind": route_surface,
        "temperature_c": current_temperature,
        "traction_factor": traction,
        "footing_factor": traction,
        "vehicle_controls_consume_traction": True,
    }


_CAMPFIRE_WEATHER_SENSITIVE_SERVICES = {
    "rest",
    "campfire_cook",
    "campfire_herbal_recipe",
    "campfire_herbal_mix",
    "prepare_fish",
}


def campfire_weather_block(sim, prop, *, service=None, tick=None):
    """Return a grounded block record when rain overwhelms an exposed fire ring."""

    if not isinstance(prop, dict):
        return None
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    archetype = str(metadata.get("archetype") or metadata.get("fixture_type") or "").strip().lower()
    if archetype != "campfire_ring" or int(prop.get("z", 0) or 0) != 0:
        return None
    service = str(service or "").strip().lower()
    if service and service not in _CAMPFIRE_WEATHER_SENSITIVE_SERVICES:
        return None
    try:
        cx, cy = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
    except (AttributeError, TypeError, ValueError):
        return None
    weather = weather_snapshot(sim, cx, cy, tick=tick)
    kind = str(weather.get("precipitation_kind", "none") or "none")
    intensity = float(weather.get("precipitation_intensity", 0.0) or 0.0)
    blocked = (kind == "rain" and intensity >= 0.28) or (kind == "sleet" and intensity >= 0.20)
    if not blocked:
        return None
    return {
        "reason": "weather_exposed",
        "condition": str(weather.get("condition", kind) or kind),
        "precipitation_kind": kind,
        "precipitation_intensity": intensity,
    }


def weather_cell_artifacts(snapshot, world_x, world_y, *, animation_tick=0):
    """Return sparse, deterministic screen particles for one outdoor world cell."""

    snapshot = snapshot if isinstance(snapshot, dict) else {}
    world_x = int(world_x)
    world_y = int(world_y)
    animation_tick = int(animation_tick)
    seed = _stable_seed(snapshot.get("seed", 0))
    phase = animation_tick // 12
    base = (
        seed
        ^ ((world_x * 0x9E3779B185EBCA87) & _MASK_64)
        ^ ((world_y * 0xC2B2AE3D27D4EB4F) & _MASK_64)
        ^ ((phase * 0x165667B19E3779F9) & _MASK_64)
    )
    artifacts = []
    fog_density = _clamp(snapshot.get("fog_density", 0.0) or 0.0, 0.0, 1.0)
    if fog_density >= 0.14:
        fog_token = _mix64(base ^ 0xF06A11)
        if (fog_token & 0xFFFF) / float(0xFFFF) < 0.24 + (fog_density * 0.58):
            artifacts.append({
                "kind": "fog",
                "band": "dense" if fog_density >= 0.55 else "light",
                "variant": int((fog_token >> 24) & 3),
                "strength": fog_density,
            })

    precipitation_intensity = _clamp(snapshot.get("precipitation_intensity", 0.0) or 0.0, 0.0, 1.0)
    precipitation_kind = str(snapshot.get("precipitation_kind", "none") or "none")
    if bool(snapshot.get("precipitation_active")) and precipitation_kind in {"rain", "snow", "sleet"}:
        precipitation_token = _mix64(base ^ 0xC10D5EED)
        density = (0.08 if precipitation_kind == "snow" else 0.12) + (precipitation_intensity * 0.54)
        if (precipitation_token & 0xFFFF) / float(0xFFFF) < density:
            artifacts.append({
                "kind": precipitation_kind,
                "band": "heavy" if precipitation_intensity >= 0.62 else "light",
                "variant": int((precipitation_token >> 25) & 3),
                "strength": precipitation_intensity,
            })
    return tuple(artifacts)


def weather_map_label(snapshot):
    code = str((snapshot or {}).get("map_code", "--") or "--").strip().upper()
    return (code + "--")[:2]


def weather_forecast(sim, cx, cy, *, tick=None, hours=WEATHER_FORECAST_HOURS):
    clock = _clock_values(sim, tick=tick)
    base_tick = int(clock["tick"])
    ticks_per_hour = int(clock["ticks_per_hour"])
    rows = []
    for offset in tuple(hours or ()):
        offset = int(offset)
        sample = weather_snapshot(sim, cx, cy, tick=base_tick + (offset * ticks_per_hour))
        sample["forecast_offset_hours"] = offset
        rows.append(sample)
    return rows


def weather_time_label(snapshot):
    hour_value = float((snapshot or {}).get("hour_of_day", 0.0)) % 24.0
    hour = int(hour_value)
    minute = int(round((hour_value - hour) * 60.0))
    if minute >= 60:
        hour = (hour + 1) % 24
        minute = 0
    return f"{hour:02d}:{minute:02d}"


def weather_debug_lines(sim, cx, cy, *, tick=None):
    current = weather_snapshot(sim, cx, cy, tick=tick)
    from game.tornado_runtime import tornado_potential, weather_alert_at

    tornado_score = tornado_potential(current)
    tornado_alert = weather_alert_at(sim, cx, cy, tick=tick)
    chunk_span = max(1, int(getattr(sim, "chunk_size", 16) or 16))
    ground_x = (int(cx) * chunk_span) + (chunk_span // 2)
    ground_y = (int(cy) * chunk_span) + (chunk_span // 2)
    ground = ground_weather_snapshot(sim, ground_x, ground_y, tick=tick)
    front = str(current["front_kind"])
    if front == "none":
        front_text = f"none analyzed | strength {current['front_strength_pct']:.0f}%"
    else:
        front_text = f"{front} | strength {current['front_strength_pct']:.0f}%"
    lines = [
        "Weather -> ground, water, vehicles, wildlife, fishing, fires.",
        "",
        f"Chunk {int(cx)},{int(cy)} | tick {current['tick']} | day {current['day_index']} {weather_time_label(current)}",
        f"Label {weather_map_label(current)} - {current['condition']}",
        (
            f"Pressure {current['pressure_hpa']:.1f} hPa | {current['pressure_kind']} / "
            f"{current['pressure_tendency']} ({current['pressure_delta_3h']:+.1f} hPa in 3h)"
        ),
        (
            f"Air {current['temperature_c']:.1f} C | dew point {current['dew_point_c']:.1f} C | "
            f"humidity {current['humidity_pct']:.0f}%"
        ),
        (
            f"Cloud {current['cloud_cover_pct']:.0f}% | precipitation potential "
            f"{current['precipitation_potential_pct']:.0f}% | "
            f"{current['precipitation_kind']} {current['precipitation_intensity_pct']:.0f}%"
        ),
        (
            f"Fog {current['fog_density_pct']:.0f}% | storm {current['storm_intensity_pct']:.0f}% | "
            f"wind toward {current['wind_direction']} {current['wind_speed_kph']:.0f} km/h"
        ),
        (
            f"Instability {current['instability_pct']:.0f}% | cyclone "
            f"{current['cyclone_class'].replace('_', ' ')} {current['cyclone_intensity_pct']:.0f}%"
        ),
        f"Front {front_text}",
        (
            f"System {current['system_id']} | pattern toward "
            f"{current['pattern_direction']} {current['pattern_speed_chunks_per_hour']:.2f} chunks/h"
        ),
        (
            f"Ground center {ground_x},{ground_y} | height {ground['relative_height']:.3f} | "
            f"saturation {ground.get('soil_saturation', 0.0):.0%} | runoff {ground.get('runoff', 0.0):.0%}"
        ),
        (
            f"Surface {str(ground.get('effect', 'none')).replace('_', ' ')} | snow {ground.get('snowpack', 0.0):.0%} | "
            f"freeze {ground.get('freeze_index', 0.0):.0%} | traction {ground.get('traction_factor', 1.0):.2f}"
        ),
        (
            f"Tornado potential {tornado_score:.0%} | {tornado_alert['headline']} | "
            f"funnel reported {'yes' if tornado_alert.get('funnel_reported') else 'no'}"
        ),
        "",
        "Forecast samples",
    ]
    for sample in weather_forecast(sim, cx, cy, tick=tick):
        offset = int(sample.get("forecast_offset_hours", 0))
        when = "now" if offset == 0 else f"+{offset}h"
        lines.append(
            f"{when:>4} {weather_time_label(sample)} | {weather_map_label(sample)} {sample['condition']} | "
            f"{sample['pressure_hpa']:.1f} hPa | {sample['temperature_c']:.1f} C | "
            f"RH {sample['humidity_pct']:.0f}% | wind {sample['wind_direction']} {sample['wind_speed_kph']:.0f}"
        )
    lines.extend([
        "",
        "Map codes: CL clear | HC high cloud | BC broken cloud | OV overcast | FG fog",
        "HI high pressure | LO low pressure | CF cold front | WF warm front",
        "DZ drizzle | RN rain | SN snow | SL sleet | TS thunderstorm | CY cyclone | TN tornado",
    ])
    if current.get("lightning_event_id"):
        lines.extend([
            "",
            f"Bolt {current['lightning_event_id']} | strike {current['lightning_strike_world']} | flash {current['lightning_flash']:.2f}",
        ])
    if current.get("cyclone_active"):
        lines.extend([
            "",
            f"Cyclone rotation {current['cyclone_rotation']} | wind load {current['cyclone_wind_load']:.0%} | runoff load {current['cyclone_runoff_load']:.0%}",
        ])
    return lines


def weather_map_edge_lines(sim, cx, cy, *, tick=None):
    snapshot = weather_snapshot(sim, cx, cy, tick=tick)
    from game.tornado_runtime import weather_alert_at

    alert = weather_alert_at(sim, cx, cy, tick=tick)
    alert_text = " | TN warning" if alert.get("level") == "warning" else " | tornado watch" if alert.get("level") == "watch" else ""
    header = "ATMOSPHERE | CL clear | FG fog | RN rain | SN snow | SL sleet | TS storm | CY cyclone" + alert_text
    footer = (
        f"{int(cx)},{int(cy)} {weather_map_label(snapshot)} {snapshot['condition']} | "
        f"{snapshot['pressure_hpa']:.1f} hPa {snapshot['pressure_tendency']} | "
        f"RH {snapshot['humidity_pct']:.0f}% | wind {snapshot['wind_direction']} {snapshot['wind_speed_kph']:.0f} | "
        "Enter details | F funnel test | T teleport | W close"
    )
    return header, footer


def default_weather_debug_ui_state():
    return {
        "open": False,
        "detail_open": False,
        "return_to_city": False,
        "title": "Atmosphere Debug",
        "lines": [],
        "scroll": 0,
        "last_teleport_chunk": None,
    }


def ensure_weather_debug_ui_state(sim):
    state = getattr(sim, "weather_debug_ui", None)
    if not isinstance(state, dict):
        state = default_weather_debug_ui_state()
        sim.weather_debug_ui = state
        return state
    for key, value in default_weather_debug_ui_state().items():
        state.setdefault(key, value)
    return state
