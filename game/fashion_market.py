"""Installation-wide cosmetic fashion memory and variant valuation.

Fashion is deliberately isolated from mechanically consequential goods.  The
player can teach the installation to value a look across runs, and realized
NPC outfits provide a much lighter street-level signal, but neither path may
change the price of armor, medicine, tools, weapons, wire gear, or drone gear.
"""

from __future__ import annotations

import copy
import json
import math
import random
from pathlib import Path
from typing import Mapping

from engine.save_paths import SAVE_DIR


FASHION_MARKET_VERSION = 1
FASHION_MARKET_PATH = SAVE_DIR / "fashion_market.json"
NPC_OUTFITS_PER_FLUSH = 24
MAX_FASHION_SIGNALS = 2048


# Construction/material baselines for cosmetic forms only.  These are fair
# values before storefront markup, organization practices, or ordinary local
# supply pressure.  No non-cosmetic item is allowed through this table.
COSMETIC_ITEM_BASE_VALUES = {
    "undershirt": 8,
    "tank_undershirt": 9,
    "bra": 16,
    "bralette": 18,
    "camisole": 17,
    "bandeau": 13,
    "boxers": 9,
    "boxer_briefs": 11,
    "briefs": 8,
    "boyshorts": 13,
    "bikini_panties": 14,
    "cheeky_panties": 16,
    "thong": 13,
    "high_waist_panties": 15,
    "tee": 12,
    "button_up": 19,
    "blouse": 20,
    "sweater": 23,
    "overshirt": 24,
    "turtleneck": 22,
    "trousers": 24,
    "shorts": 16,
    "skirt": 20,
    "dress": 31,
    "worker_coverall": 34,
    "orange_jumpsuit": 20,
    "boots": 36,
    "sneakers": 28,
    "sandals": 18,
    "cap": 12,
    "baseball_cap": 14,
    "bandana": 8,
    "jacket": 38,
    "windbreaker": 32,
    "coat": 48,
    "cardigan": 30,
    "blazer": 45,
    "vest": 26,
    "maintenance_vest": 32,
    "patrol_rain_shell": 40,
    "security_jacket": 42,
    "butcher_apron": 25,
    "botany_apron": 25,
    "earrings": 22,
    "ring": 28,
    "necklace": 27,
    "scarf": 18,
    "bracelet": 22,
    "gloves": 24,
    "watch": 34,
}

FLORA_MOTIF_ELIGIBLE_ITEMS = frozenset({
    "undershirt", "tank_undershirt", "bra", "bralette", "camisole", "bandeau",
    "boxers", "boxer_briefs", "briefs", "boyshorts", "bikini_panties",
    "cheeky_panties", "thong", "high_waist_panties",
    "tee", "button_up", "blouse", "sweater", "turtleneck", "shorts", "skirt",
    "dress", "cardigan", "scarf", "cap", "baseball_cap", "bandana", "botany_apron",
})

MATERIAL_VALUE_MULTS = {
    "gauze": 0.88,
    "polyester": 0.9,
    "poly_cotton": 0.94,
    "rubber": 0.95,
    "jersey": 0.96,
    "woven_cord": 1.0,
    "mesh": 1.02,
    "flannel": 1.04,
    "knit": 1.04,
    "soft_jersey": 1.04,
    "brushed_cotton": 1.05,
    "ribbed_cotton": 1.05,
    "twill": 1.05,
    "poplin": 1.08,
    "canvas": 1.08,
    "ribbed_knit": 1.08,
    "denim": 1.1,
    "duck_cloth": 1.12,
    "modal": 1.16,
    "linen": 1.18,
    "wool": 1.24,
    "waxed_cotton": 1.24,
    "weatherproof_cloth": 1.28,
    "lace": 1.3,
    "satin": 1.34,
    "suede": 1.36,
    "leather": 1.42,
    "glass": 1.18,
    "brass": 1.25,
    "steel": 1.18,
    "silver": 1.58,
    "onyx": 1.55,
}

PREMIUM_STYLE_TOKENS = {
    "cross_back": 1.08,
    "cross_backed": 1.08,
    "lined": 1.12,
    "pleated": 1.1,
    "polished": 1.14,
    "ribbon_trimmed": 1.1,
    "scallop_trimmed": 1.12,
    "sharp": 1.08,
    "signet": 1.14,
    "structured": 1.14,
    "tailored": 1.2,
    "vintage_cut": 1.12,
    "weatherproof": 1.12,
}

FLORA_RARITY_VALUE_MULTS = {
    "common": 1.08,
    "uncommon": 1.18,
    "rare": 1.34,
}

SIGNAL_WEIGHTS = {
    "item": 0.34,
    "material": 0.2,
    "style": 0.12,
    "detail": 0.09,
    "color": 0.08,
    "pattern": 0.08,
    "motif": 0.24,
}


def _text(value):
    return str(value or "").strip()


def _key(value):
    return _text(value).lower().replace(" ", "_").replace("-", "_")


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _clamp(value, low, high):
    return max(float(low), min(float(high), float(value)))


def _json_safe(value):
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_safe(inner) for key, inner in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_json_safe(inner) for inner in value]
    return str(value)


def empty_fashion_market():
    return {
        "version": FASHION_MARKET_VERSION,
        "signals": {},
        "player_selections": 0,
        "npc_outfits_realized": 0,
    }


def normalize_fashion_market(payload):
    clean = empty_fashion_market()
    if not isinstance(payload, Mapping):
        return clean
    signals = payload.get("signals") if isinstance(payload.get("signals"), Mapping) else {}
    ranked = []
    for raw_key, raw_row in signals.items():
        signal_key = _text(raw_key).lower()
        if not signal_key or not isinstance(raw_row, Mapping):
            continue
        player_weight = _clamp(_safe_float(raw_row.get("player_weight"), 0.0), 0.0, 100000.0)
        npc_weight = _clamp(_safe_float(raw_row.get("npc_weight"), 0.0), 0.0, 100000.0)
        row = {
            "player_weight": round(player_weight, 4),
            "npc_weight": round(npc_weight, 4),
            "player_runs": max(0, _safe_int(raw_row.get("player_runs"), 0)),
            "npc_looks": max(0, _safe_int(raw_row.get("npc_looks"), 0)),
        }
        ranked.append((player_weight + npc_weight, signal_key, row))
    ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
    clean["signals"] = {
        signal_key: row
        for _score, signal_key, row in ranked[:MAX_FASHION_SIGNALS]
    }
    clean["player_selections"] = max(0, _safe_int(payload.get("player_selections"), 0))
    clean["npc_outfits_realized"] = max(0, _safe_int(payload.get("npc_outfits_realized"), 0))
    return clean


def load_fashion_market(path=None):
    source = Path(path) if path is not None else FASHION_MARKET_PATH
    if not source.exists():
        return empty_fashion_market()
    try:
        return normalize_fashion_market(json.loads(source.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return empty_fashion_market()


def save_fashion_market(registry, path=None):
    target = Path(path) if path is not None else FASHION_MARKET_PATH
    payload = normalize_fashion_market(registry)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(_json_safe(payload), indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(target)
    return target


def prime_fashion_market(sim, *, market_path=None):
    if sim is None:
        return empty_fashion_market()
    path = Path(market_path) if market_path is not None else FASHION_MARKET_PATH
    previous = getattr(sim, "fashion_market_runtime", None)
    previous = previous if isinstance(previous, dict) else {}
    runtime = {
        "path": str(path),
        "registry": load_fashion_market(path),
        "primed": True,
        "player_seen_features": set(previous.get("player_seen_features", set()) or set()),
        "npc_seen_features": set(previous.get("npc_seen_features", set()) or set()),
        "npc_outfits_since_flush": max(0, _safe_int(previous.get("npc_outfits_since_flush"), 0)),
    }
    sim.fashion_market_runtime = runtime
    return runtime["registry"]


def fashion_market_for_sim(sim):
    runtime = getattr(sim, "fashion_market_runtime", None) if sim is not None else None
    if not isinstance(runtime, dict) or not bool(runtime.get("primed")):
        return None
    registry = runtime.get("registry")
    if not isinstance(registry, dict):
        registry = empty_fashion_market()
        runtime["registry"] = registry
    return registry


def flush_fashion_market(sim):
    runtime = getattr(sim, "fashion_market_runtime", None) if sim is not None else None
    registry = fashion_market_for_sim(sim)
    if not isinstance(runtime, dict) or registry is None:
        return None
    rules = getattr(sim, "world_traits", {}).get("rules", {}) if isinstance(getattr(sim, "world_traits", None), dict) else {}
    if isinstance(rules, dict) and bool(rules.get("tutorial_no_persistence")):
        return None
    runtime["npc_outfits_since_flush"] = 0
    return save_fashion_market(registry, path=runtime.get("path"))


def is_cosmetic_fashion_item(item_id):
    return _key(item_id) in COSMETIC_ITEM_BASE_VALUES


def _metadata_profile(metadata):
    metadata = metadata if isinstance(metadata, Mapping) else {}
    nested = metadata.get("appearance") if isinstance(metadata.get("appearance"), Mapping) else {}
    merged = dict(nested)
    for key in (
        "appearance_type", "appearance_label", "color", "color_word", "material", "style",
        "detail", "pattern", "emblem", "flora_motif", "fashion_rarity", "fashion_rarity_score",
    ):
        if metadata.get(key) not in (None, "", {}, []):
            merged[key] = metadata.get(key)
    return merged


def _flora_visual_traits(profile):
    genetics = profile.get("genetics") if isinstance(profile.get("genetics"), Mapping) else {}
    expressed = genetics.get("expressed") if isinstance(genetics.get("expressed"), Mapping) else {}
    visual = expressed.get("visual") if isinstance(expressed.get("visual"), Mapping) else {}
    color = visual.get("color") if isinstance(visual.get("color"), Mapping) else {}
    shape = visual.get("shape") if isinstance(visual.get("shape"), Mapping) else {}
    legacy = genetics if isinstance(genetics, Mapping) else {}
    return {
        "color_word": _key(color.get("word") or profile.get("color_word") or legacy.get("hue_family")),
        "petal_shape": _key(shape.get("petal_shape") or legacy.get("petal_shape")),
        "leaf_shape": _key(shape.get("leaf_shape") or legacy.get("leaf_shape")),
    }


def choose_cosmetic_flora_motif(
    sim,
    item_id,
    *,
    seed_token="",
    slots=(),
    force=False,
    treatment_hint="",
):
    """Choose a real authored or installation-native flora line when applicable."""

    item_id = _key(item_id)
    if sim is None or item_id not in FLORA_MOTIF_ELIGIBLE_ITEMS:
        return {}
    slot_set = {_key(slot) for slot in tuple(slots or ())}
    if {"base_top", "base_bottom"} & slot_set:
        chance = 0.34
    elif item_id == "botany_apron":
        chance = 0.32
    elif {"hat", "necklace"} & slot_set:
        chance = 0.18
    else:
        chance = 0.14
    rng = random.Random(f"fashion-flora:{getattr(sim, 'seed', 0)}:{item_id}:{seed_token}")
    if not bool(force) and rng.random() >= chance:
        return {}

    from game.flora_runtime import flora_catalog_for_sim

    catalog = flora_catalog_for_sim(sim)
    candidates = []
    rarity_weights = {"common": 8.0, "uncommon": 3.0, "rare": 1.0}
    form_weights = {"flower": 5.0, "vine": 2.0, "shrub": 1.5, "herb": 1.25, "grass": 0.6, "moss": 0.45, "lichen": 0.4, "tree": 0.7}
    for plant_id, profile in sorted(catalog.items()):
        if not isinstance(profile, Mapping):
            continue
        name = _text(profile.get("name") or profile.get("plant_name") or plant_id.replace("_", " "))
        if not name:
            continue
        rarity = _key(profile.get("rarity")) or "common"
        growth_form = _key(profile.get("growth_form")) or "flower"
        weight = rarity_weights.get(rarity, 2.0) * form_weights.get(growth_form, 0.5)
        if _text(profile.get("native_lineage_id")):
            weight *= 1.5
        if weight > 0:
            candidates.append((str(plant_id), dict(profile), weight))
    if not candidates:
        return {}
    pick = rng.uniform(0.0, sum(weight for _plant_id, _profile, weight in candidates))
    running = 0.0
    chosen_id, chosen, _weight = candidates[-1]
    for plant_id, profile, weight in candidates:
        running += weight
        if pick <= running:
            chosen_id, chosen = plant_id, profile
            break
    visual = _flora_visual_traits(chosen)
    treatment = _key(treatment_hint)
    if treatment not in {"embroidery", "print"}:
        treatment = rng.choice(("embroidery", "embroidery", "embroidery", "print", "print"))
    return {
        "plant_id": _key(chosen_id),
        "name": _text(chosen.get("name") or chosen.get("plant_name") or chosen_id.replace("_", " ")),
        "rarity": _key(chosen.get("rarity")) or "common",
        "growth_form": _key(chosen.get("growth_form")) or "flower",
        "color_word": visual.get("color_word", ""),
        "petal_shape": visual.get("petal_shape", ""),
        "leaf_shape": visual.get("leaf_shape", ""),
        "native_lineage_id": _text(chosen.get("native_lineage_id")),
        "treatment": treatment,
    }


def cosmetic_flora_motif_phrase(motif):
    motif = motif if isinstance(motif, Mapping) else {}
    name = _text(motif.get("name") or motif.get("plant_id")).replace("_", " ")
    treatment = _key(motif.get("treatment")) or "embroidery"
    if not name:
        return ""
    if treatment == "print":
        return f"a {name} print"
    return f"{name} embroidery"


def cosmetic_variant_rarity(item_id, metadata=None):
    item_id = _key(item_id)
    base_value = COSMETIC_ITEM_BASE_VALUES.get(item_id)
    if base_value is None:
        return {}
    profile = _metadata_profile(metadata)
    material = _key(profile.get("material"))
    style = _key(profile.get("style"))
    detail = _key(profile.get("detail"))
    pattern = _key(profile.get("pattern"))
    emblem = _key(profile.get("emblem"))
    motif = profile.get("flora_motif") if isinstance(profile.get("flora_motif"), Mapping) else {}

    rarity_mult = MATERIAL_VALUE_MULTS.get(material, 1.0)
    for token in {style, detail}:
        rarity_mult *= PREMIUM_STYLE_TOKENS.get(token, 1.0)
    if "lacy" in {style, detail}:
        rarity_mult *= 1.14
    if pattern:
        rarity_mult *= 1.07
    if emblem:
        rarity_mult *= 1.08
    if motif:
        rarity_mult *= FLORA_RARITY_VALUE_MULTS.get(_key(motif.get("rarity")), 1.12)
        if _text(motif.get("native_lineage_id")):
            rarity_mult *= 1.16
    rarity_mult = _clamp(rarity_mult, 0.78, 2.75)
    if rarity_mult < 1.08:
        band = "common"
    elif rarity_mult < 1.27:
        band = "distinctive"
    elif rarity_mult < 1.58:
        band = "rare"
    else:
        band = "singular"
    return {
        "base_value": int(base_value),
        "rarity_mult": round(rarity_mult, 4),
        "rarity_value": max(1, int(round(base_value * rarity_mult))),
        "rarity_band": band,
    }


def with_cosmetic_rarity_metadata(item_id, metadata=None):
    updated = copy.deepcopy(dict(metadata or {}))
    rarity = cosmetic_variant_rarity(item_id, updated)
    if not rarity:
        return updated
    fields = {
        "fashion_rarity": rarity["rarity_band"],
        "fashion_rarity_score": rarity["rarity_mult"],
        "fashion_base_value": rarity["base_value"],
        "fashion_rarity_value": rarity["rarity_value"],
    }
    updated.update(fields)
    nested = dict(updated.get("appearance") or {})
    nested.update(fields)
    updated["appearance"] = nested
    return updated


def cosmetic_feature_keys(item_id, metadata=None):
    item_id = _key(item_id)
    if item_id not in COSMETIC_ITEM_BASE_VALUES:
        return ()
    profile = _metadata_profile(metadata)
    motif = profile.get("flora_motif") if isinstance(profile.get("flora_motif"), Mapping) else {}
    rows = [
        ("item", item_id),
        ("material", _key(profile.get("material"))),
        ("style", _key(profile.get("style"))),
        ("detail", _key(profile.get("detail"))),
        ("color", _key(profile.get("color_word") or profile.get("color"))),
        ("pattern", _key(profile.get("pattern"))),
        ("motif", _key(motif.get("plant_id") or motif.get("name"))),
    ]
    return tuple(
        (kind, value, float(SIGNAL_WEIGHTS[kind]))
        for kind, value in rows
        if value and kind in SIGNAL_WEIGHTS
    )


def record_cosmetic_popularity(sim, item_id, metadata=None, *, source="player", source_token=""):
    registry = fashion_market_for_sim(sim)
    runtime = getattr(sim, "fashion_market_runtime", None) if sim is not None else None
    if registry is None or not isinstance(runtime, dict) or not is_cosmetic_fashion_item(item_id):
        return False
    rules = getattr(sim, "world_traits", {}).get("rules", {}) if isinstance(getattr(sim, "world_traits", None), dict) else {}
    if isinstance(rules, dict) and bool(rules.get("tutorial_no_persistence")):
        return False
    source = _key(source)
    if source not in {"player", "npc"}:
        return False
    features = cosmetic_feature_keys(item_id, metadata)
    if not features:
        return False
    changed = False
    signals = registry.setdefault("signals", {})
    if source == "player":
        seen = runtime.setdefault("player_seen_features", set())
        increment = 1.0
    else:
        seen = runtime.setdefault("npc_seen_features", set())
        increment = 0.015
    actor_token = _text(source_token) or _key(item_id)
    for kind, value, _weight in features:
        signal_key = f"{kind}:{value}"
        seen_key = signal_key if source == "player" else f"{actor_token}:{signal_key}"
        if seen_key in seen:
            continue
        seen.add(seen_key)
        row = signals.setdefault(signal_key, {
            "player_weight": 0.0,
            "npc_weight": 0.0,
            "player_runs": 0,
            "npc_looks": 0,
        })
        if source == "player":
            row["player_weight"] = round(_safe_float(row.get("player_weight"), 0.0) + increment, 4)
            row["player_runs"] = max(0, _safe_int(row.get("player_runs"), 0)) + 1
        else:
            row["npc_weight"] = round(_safe_float(row.get("npc_weight"), 0.0) + increment, 4)
            row["npc_looks"] = max(0, _safe_int(row.get("npc_looks"), 0)) + 1
        changed = True
    if not changed:
        return False
    if source == "player":
        registry["player_selections"] = max(0, _safe_int(registry.get("player_selections"), 0)) + 1
        flush_fashion_market(sim)
    else:
        registry["npc_outfits_realized"] = max(0, _safe_int(registry.get("npc_outfits_realized"), 0)) + 1
        runtime["npc_outfits_since_flush"] = max(0, _safe_int(runtime.get("npc_outfits_since_flush"), 0)) + 1
        if runtime["npc_outfits_since_flush"] >= NPC_OUTFITS_PER_FLUSH:
            flush_fashion_market(sim)
    return True


def cosmetic_demand_profile(sim, item_id, metadata=None):
    features = cosmetic_feature_keys(item_id, metadata)
    if not features:
        return {}
    registry = fashion_market_for_sim(sim)
    signals = registry.get("signals", {}) if isinstance(registry, Mapping) and isinstance(registry.get("signals"), Mapping) else {}
    weighted_score = 0.0
    total_weight = 0.0
    player_score = 0.0
    npc_score = 0.0
    for kind, value, weight in features:
        row = signals.get(f"{kind}:{value}") if isinstance(signals, Mapping) else None
        row = row if isinstance(row, Mapping) else {}
        player = max(0.0, _safe_float(row.get("player_weight"), 0.0))
        npc = max(0.0, _safe_float(row.get("npc_weight"), 0.0))
        weighted_score += (player + npc) * weight
        player_score += player * weight
        npc_score += npc * weight
        total_weight += weight
    if total_weight > 0.0:
        weighted_score /= total_weight
        player_score /= total_weight
        npc_score /= total_weight
    demand_mult = 1.0 + min(0.65, 0.075 * math.sqrt(max(0.0, weighted_score)))
    if weighted_score < 0.12:
        label = "baseline"
    elif weighted_score < 0.75:
        label = "noticed"
    elif weighted_score < 2.5:
        label = "locally popular"
    elif weighted_score < 7.5:
        label = "in demand"
    else:
        label = "installation favorite"
    return {
        "demand_index": round(weighted_score, 4),
        "demand_mult": round(demand_mult, 4),
        "demand_label": label,
        "player_influence": round(player_score, 4),
        "npc_influence": round(npc_score, 4),
    }


def cosmetic_fashion_quote(sim, item_id, metadata=None):
    rarity = cosmetic_variant_rarity(item_id, metadata)
    if not rarity:
        return {}
    demand = cosmetic_demand_profile(sim, item_id, metadata)
    fair_value = max(1, int(round(rarity["rarity_value"] * demand["demand_mult"])))
    return {
        **rarity,
        **demand,
        "fair_value": fair_value,
        "market_note": f"{rarity['rarity_band']} make; {demand['demand_label']} demand",
    }


def with_cosmetic_market_metadata(sim, item_id, metadata=None):
    updated = with_cosmetic_rarity_metadata(item_id, metadata)
    quote = cosmetic_fashion_quote(sim, item_id, updated)
    if not quote:
        return updated
    fields = {
        "fashion_demand": quote["demand_label"],
        "fashion_demand_index": quote["demand_index"],
        "fashion_demand_mult": quote["demand_mult"],
        "fashion_player_influence": quote["player_influence"],
        "fashion_npc_influence": quote["npc_influence"],
        "fashion_fair_value": quote["fair_value"],
        "fashion_market_note": quote["market_note"],
    }
    updated.update(fields)
    nested = dict(updated.get("appearance") or {})
    nested.update(fields)
    updated["appearance"] = nested
    return updated


__all__ = (
    "COSMETIC_ITEM_BASE_VALUES",
    "FASHION_MARKET_PATH",
    "choose_cosmetic_flora_motif",
    "cosmetic_demand_profile",
    "cosmetic_fashion_quote",
    "cosmetic_feature_keys",
    "cosmetic_flora_motif_phrase",
    "cosmetic_variant_rarity",
    "empty_fashion_market",
    "fashion_market_for_sim",
    "flush_fashion_market",
    "is_cosmetic_fashion_item",
    "load_fashion_market",
    "normalize_fashion_market",
    "prime_fashion_market",
    "record_cosmetic_popularity",
    "save_fashion_market",
    "with_cosmetic_market_metadata",
    "with_cosmetic_rarity_metadata",
)
