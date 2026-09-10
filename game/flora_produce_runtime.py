"""Inherited produce identity and weather response for flora.

The genome says what a plant bears and which weather it prefers.  This module
turns that expression into two run-scoped contracts: one edible produce profile
per visible phenotype, and one bounded growth/breeding multiplier.  Neither
contract changes biome viability or kills a plant.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from game.weather_runtime import weather_snapshot


PRODUCE_ITEM_ID = "wild_produce"
PRODUCE_KINDS = frozenset(("none", "fruit", "vegetable"))
PRODUCE_SHAPES = frozenset(("berry", "pear", "pod", "orb", "squash", "starfruit"))
PRODUCE_TOXICITY = frozenset(("safe", "bitter", "irritant", "toxic"))
WEATHER_TEMPERATURE_AFFINITIES = frozenset(("cool", "mild", "warm"))
WEATHER_MOISTURE_AFFINITIES = frozenset(("dry", "balanced", "humid", "rain"))
WEATHER_SKY_AFFINITIES = frozenset(("sun", "cloud", "storm"))


def _key(value, fallback=""):
    text = str(value if value is not None else "").strip().lower().replace(" ", "_").replace("-", "_")
    return text or str(fallback or "").strip().lower().replace(" ", "_").replace("-", "_")


def _clamp(value, low=0.0, high=1.0):
    return max(float(low), min(float(high), float(value)))


def _stable_int(*parts):
    payload = "|".join(str(part) for part in parts).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big")


def _expressed(record):
    genetics = record.get("genetics") if isinstance(record, Mapping) else {}
    return genetics.get("expressed") if isinstance(genetics, Mapping) and isinstance(genetics.get("expressed"), Mapping) else {}


def expressed_produce_traits(record):
    """Return the visible, inherited produce phenotype for a flora record."""

    expressed = _expressed(record)
    produce = expressed.get("produce") if isinstance(expressed.get("produce"), Mapping) else {}
    visual = expressed.get("visual") if isinstance(expressed.get("visual"), Mapping) else {}
    visual_color = visual.get("color") if isinstance(visual.get("color"), Mapping) else {}
    kind = _key(produce.get("kind"), record.get("produce_kind") if isinstance(record, Mapping) else "none")
    shape = _key(produce.get("shape"), record.get("produce_shape") if isinstance(record, Mapping) else "berry")
    color = produce.get("color")
    if isinstance(color, Mapping):
        color_word = _key(color.get("word"))
        color_key = _key(color.get("render_key_hint"))
    else:
        color_word = _key(color)
        color_key = ""
    if not color_word:
        color_word = _key((record or {}).get("produce_color_word") if isinstance(record, Mapping) else "")
    if not color_word:
        color_word = _key(visual_color.get("word"), "green")
    if not color_key:
        color_key = _key((record or {}).get("produce_color_key") if isinstance(record, Mapping) else "")
    if not color_key:
        color_key = _key(visual_color.get("render_key_hint"), (record or {}).get("color_key") if isinstance(record, Mapping) else "flora_leaf")
    toxicity = _key(produce.get("toxicity"), record.get("produce_toxicity") if isinstance(record, Mapping) else "safe")
    if kind not in PRODUCE_KINDS:
        kind = "none"
    if shape not in PRODUCE_SHAPES:
        shape = "berry"
    if toxicity not in PRODUCE_TOXICITY:
        toxicity = "safe"
    return {
        "produces_food": kind in {"fruit", "vegetable"},
        "kind": kind,
        "shape": shape,
        "color_word": color_word,
        "color_key": color_key,
        "toxicity": toxicity,
        "phenotype_id": f"{color_word}_{shape}",
    }


def produce_profile_for_flora(sim, record):
    """Resolve run-stable food effects from a visible produce phenotype.

    Effects are intentionally assigned from the run seed rather than fixed to
    a catalog species.  Every pink pear in one run therefore agrees, while a
    different run can attach that nutrition profile to another phenotype.
    """

    traits = expressed_produce_traits(record)
    if not traits["produces_food"]:
        return {}
    token = _stable_int(getattr(sim, "seed", 0), "flora-produce", traits["phenotype_id"])
    hunger_values = (9, 12, 15, 18, 21, 24)
    thirst_values = (3, 6, 9, 12, 15, 18)
    hunger = hunger_values[token % len(hunger_values)]
    thirst = thirst_values[(token >> 11) % len(thirst_values)]
    toxicity = traits["toxicity"]
    hp_delta = {"safe": 0, "bitter": 0, "irritant": -3, "toxic": -12}[toxicity]
    kind_name = "fruit" if traits["kind"] == "fruit" else "vegetable"
    display_name = f"{traits['color_word'].replace('_', ' ').title()} {traits['shape'].replace('_', ' ').title()}"
    return {
        **traits,
        "display_name": display_name,
        "kind_name": kind_name,
        "hunger_delta": int(hunger),
        "thirst_delta": int(thirst),
        "hp_delta": int(hp_delta),
        "item_id": PRODUCE_ITEM_ID,
    }


def produce_item_metadata(sim, record):
    profile = produce_profile_for_flora(sim, record)
    if not profile:
        return {}
    return {
        "source": "flora",
        "source_context": "fruiting_harvest",
        "source_plant_id": _key((record or {}).get("plant_id")),
        "source_plant_name": str((record or {}).get("name") or (record or {}).get("plant_name") or "plant").strip(),
        "display_name": profile["display_name"],
        "produce_phenotype_id": profile["phenotype_id"],
        "produce_kind": profile["kind"],
        "produce_shape": profile["shape"],
        "produce_color_word": profile["color_word"],
        "produce_color_key": profile["color_key"],
        "produce_toxicity": profile["toxicity"],
        "item_extra_hunger_delta": profile["hunger_delta"],
        "item_extra_thirst_delta": profile["thirst_delta"],
        "herbal_hp_delta": profile["hp_delta"],
        "visual_seed": profile["phenotype_id"],
        "legal_status": "legal",
    }


def expressed_weather_affinity(record):
    expressed = _expressed(record)
    climate = expressed.get("climate") if isinstance(expressed.get("climate"), Mapping) else {}
    temperature = _key(climate.get("temperature"), "mild")
    moisture = _key(climate.get("moisture"), "balanced")
    sky = _key(climate.get("sky"), "cloud")
    return {
        "temperature": temperature if temperature in WEATHER_TEMPERATURE_AFFINITIES else "mild",
        "moisture": moisture if moisture in WEATHER_MOISTURE_AFFINITIES else "balanced",
        "sky": sky if sky in WEATHER_SKY_AFFINITIES else "cloud",
    }


def flora_weather_response(sim, record, *, tick=None):
    """Return bounded thriving pressure without changing biome viability."""

    if not isinstance(record, Mapping) or record.get("x") is None or record.get("y") is None or int(record.get("z", 0) or 0) != 0:
        return {"growth_multiplier": 1.0, "breeding_multiplier": 1.0, "fit": 0.5, "label": "sheltered"}
    span = max(1, int(getattr(sim, "chunk_size", 16) or 16))
    sample_tick = int(getattr(sim, "tick", 0) if tick is None else tick)
    sample_key = (int(record["x"]) // span, int(record["y"]) // span, sample_tick)
    cache = getattr(sim, "_flora_weather_sample_cache", None)
    if not isinstance(cache, dict):
        cache = {}
        sim._flora_weather_sample_cache = cache
    weather = cache.get(sample_key)
    if not isinstance(weather, dict):
        weather = weather_snapshot(sim, sample_key[0], sample_key[1], tick=sample_tick)
        if len(cache) >= 96:
            cache.clear()
        cache[sample_key] = weather
    affinity = expressed_weather_affinity(record)
    temperature = float(weather.get("temperature_c", 13.0) or 13.0)
    humidity = float(weather.get("humidity_pct", 50.0) or 50.0)
    rain = float(weather.get("precipitation_intensity", 0.0) or 0.0)
    cloud = float(weather.get("cloud_cover_pct", 50.0) or 50.0) / 100.0
    storm = float(weather.get("storm_intensity", 0.0) or 0.0)

    ideal_temperature = {"cool": 7.0, "mild": 17.0, "warm": 28.0}[affinity["temperature"]]
    temperature_fit = _clamp(1.0 - abs(temperature - ideal_temperature) / 22.0)
    if affinity["moisture"] == "dry":
        moisture_fit = _clamp(1.0 - ((humidity / 100.0) * 0.55) - (rain * 0.45))
    elif affinity["moisture"] == "humid":
        moisture_fit = _clamp(1.0 - abs(humidity - 78.0) / 62.0)
    elif affinity["moisture"] == "rain":
        moisture_fit = _clamp(0.28 + (rain * 0.58) + ((humidity / 100.0) * 0.28))
    else:
        moisture_fit = _clamp(1.0 - abs(humidity - 55.0) / 75.0)
    sky_fit = {
        "sun": _clamp(1.0 - cloud),
        "cloud": _clamp(1.0 - abs(cloud - 0.58) / 0.70),
        "storm": _clamp(0.20 + (storm * 0.80)),
    }[affinity["sky"]]
    fit = _clamp((temperature_fit * 0.46) + (moisture_fit * 0.34) + (sky_fit * 0.20))
    growth = 0.55 + (fit * 0.85)
    breeding = 0.42 + (fit * 0.88)
    label = "thriving" if fit >= 0.72 else "slowed" if fit < 0.42 else "steady"
    return {
        "affinity": affinity,
        "fit": fit,
        "label": label,
        "growth_multiplier": growth,
        "breeding_multiplier": breeding,
        "weather": weather,
    }


__all__ = [
    "PRODUCE_ITEM_ID",
    "PRODUCE_KINDS",
    "PRODUCE_SHAPES",
    "PRODUCE_TOXICITY",
    "WEATHER_TEMPERATURE_AFFINITIES",
    "WEATHER_MOISTURE_AFFINITIES",
    "WEATHER_SKY_AFFINITIES",
    "expressed_produce_traits",
    "expressed_weather_affinity",
    "flora_weather_response",
    "produce_item_metadata",
    "produce_profile_for_flora",
]
