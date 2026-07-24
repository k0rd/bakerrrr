"""Small-batch herbal chemistry, harvesting, and recipe helpers."""

from __future__ import annotations

import copy
import json
import random
from functools import lru_cache
from pathlib import Path
from typing import Mapping

from engine.events import Event
from engine.systems import System
from engine.visibility import has_line_of_sight

from game.components import Inventory, PlayerAssets, Position
from game.flora_runtime import (
    EXHAUSTED_FLORA_STAGES,
    dynamic_flora_profile,
    ensure_dynamic_flora_profiles,
    flora_harvest_context,
    flora_harvest_remaining,
    flora_harvest_updates_after_pick,
    flora_patch_harvestable,
    flora_records_in_rect,
    load_flora_catalog,
    normalize_flora_harvest_state,
)
from game.ecology_registry import native_flora_effect_channels
from game.item_semantics import identify_item_for_actor, item_display_name_for_actor
from game.items import ITEM_CATALOG, item_display_name, prepare_item_stack_metadata
from game.json_metadata import split_object_document
from game.property_runtime import property_runtime_container_entries
from game.system_support.interaction_ordering import _manhattan
from game.system_support.item_provenance_runtime import CLAIM_PRIVATE_EFFECT, stamp_item_provenance


HERBAL_RECIPES_PATH = Path(__file__).resolve().parent / "herbal_recipes.json"

CHEMISTRY_CLASSES = (
    "mending",
    "hydrating",
    "cooling",
    "calming",
    "energizing",
    "cleansing",
    "numbing",
    "binding",
    "catalyst",
    "irritant",
    "toxic",
    "deliriant",
    "volatile",
)
SECONDARY_TRAITS = (
    "potentiator",
    "diluter",
    "stabilizer",
    "spoiler",
    "+wake",
    "-wake",
    "+nourish",
    "-nourish",
    "+hydrate",
    "-hydrate",
)
FALLBACK_SECONDARY_TRAITS = (
    "potentiator",
    "diluter",
    "stabilizer",
    "spoiler",
)
SECONDARY_TRAIT_LABELS = {
    "potentiator": "+effect",
    "diluter": "-effect",
    "stabilizer": "stabilizer",
    "spoiler": "spoiler",
    "+wake": "wake-restoring",
    "-wake": "wake-draining",
    "+nourish": "nourishing",
    "-nourish": "hunger-draining",
    "+hydrate": "hydrating",
    "-hydrate": "dehydrating",
}

HERBAL_INGREDIENT_ITEM_IDS = {
    "fresh_blossoms",
    "leaf_clippings",
    "moss_scrapings",
    "vine_cuttings",
}
HERBAL_INGREDIENT_DISPLAY_PARTS = {
    "fresh_blossoms": "Blossoms",
    "leaf_clippings": "Clippings",
    "moss_scrapings": "Scrapings",
    "vine_cuttings": "Cuttings",
}
INGREDIENT_ITEM_BY_FORM = {
    "flower": "fresh_blossoms",
    "grass": "leaf_clippings",
    "reed": "leaf_clippings",
    "shrub": "leaf_clippings",
    "fern": "leaf_clippings",
    "moss": "moss_scrapings",
    "lichen": "moss_scrapings",
    "vine": "vine_cuttings",
}
HARVEST_METHOD_BY_FORM = {
    "flower": "pluck",
    "grass": "pluck",
    "reed": "cut",
    "shrub": "cut",
    "fern": "cut",
    "vine": "cut",
    "moss": "scrape",
    "lichen": "scrape",
}
DIRECT_CUT_TOOL_IDS = {"field_knife", "trail_machete", "pruning_shears", "shiv_knife"}
DIRECT_SCRAPE_TOOL_IDS = DIRECT_CUT_TOOL_IDS | {"pocket_multitool"}
CUT_TOOL_TAGS = {"knife", "blade"}
MORTAR_KIT_ITEM_ID = "mortar_kit"
IMPROVISED_HERBAL_BLEND_ITEM_ID = "improvised_herbal_blend"
EXPERIMENTAL_CONCOCTION_ITEM_ID = "experimental_herbal_concoction"
WEAK_TOXIC_CONCOCTION_ITEM_ID = "weak_toxic_concoction"
SPOILED_HERBAL_SLURRY_ITEM_ID = "spoiled_herbal_slurry"
CAMPFIRE_HERB_CACHE_KIND = "campfire_herb_cache"
DILUTED_HERBAL_OUTPUTS = {
    "herbal_poultice": "diluted_herbal_poultice",
    "hydrating_tonic": "diluted_hydrating_tonic",
    "calming_tincture": "diluted_calming_tincture",
    "strong_herbal_poultice": "diluted_strong_herbal_poultice",
    "field_restorative": "diluted_field_restorative",
    "steadying_draught": "diluted_steadying_draught",
    "focus_inhaler": "diluted_focus_inhaler",
}
HERBAL_STABILITY_BASE_SCORES = {
    "recipe": 76,
    "discovered_recipe": 68,
    "exact_recipe": 68,
    "diluted": 50,
    "useful": 58,
    "odd": 36,
    "weak_toxic": 30,
}
HERBAL_STABILITY_WINDOWS = {
    "temperamental": 2400,
    "volatile": 1200,
    "feral": 600,
    "collapsed": 120,
}
HERBAL_DECAY_METADATA_KEYS = {
    "item_effect_scalar",
    "item_positive_effect_scalar",
    "item_negative_effect_scalar",
    "item_status_duration_scalar",
    "stability_window_ticks",
    "breakdown_tick",
    "herbal_decay",
    "herbal_result_read",
    "herbal_signed_effect_stacks",
    "herbal_class_effects",
    "herbal_hp_delta",
    "herbal_wakefulness_delta",
    "herbal_hunger_delta",
    "herbal_thirst_delta",
}

_BIAS_TERMS = {
    "mending": ("restorative", "soothing", "staunch", "heal", "mending", "clover", "soft"),
    "hydrating": ("water", "wet", "moist", "marsh", "hydrating", "coastal", "drink"),
    "cooling": ("cool", "cooling", "wetland", "blue", "mint", "shade"),
    "calming": ("calm", "calming", "dream", "sleep", "night", "violet", "soft"),
    "energizing": ("warm", "warming", "gold", "sun", "spice", "aromatic", "bright"),
    "cleansing": ("clean", "cleansing", "fresh", "salt", "white", "mineral", "antiseptic"),
    "numbing": ("sleep", "numb", "bitter", "thorn", "poppy", "dream"),
    "binding": ("fiber", "thread", "vine", "reed", "root", "clump", "patch"),
    "catalyst": ("rare", "orchid", "lantern", "moon", "lichen", "moss", "mineral"),
    "irritant": ("thorn", "bramble", "briar", "snapdragon", "sedge", "ash", "hardy", "astringent"),
    "toxic": ("bitter", "holly", "sorrel", "redleaf", "deep", "wine", "night", "toxic"),
    "deliriant": ("dream", "night", "moon", "morning", "violet", "poppy", "lace", "delicate"),
    "volatile": ("warm", "copper", "amber", "gold", "lantern", "aromatic", "spice", "dry"),
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


def _key(value):
    return str(value or "").strip().lower().replace(" ", "_")


def _actor_key(eid):
    try:
        return str(int(eid))
    except (TypeError, ValueError):
        return str(eid or "").strip()


def _entry_tags(item_id):
    return {
        str(tag).strip().lower()
        for tag in ITEM_CATALOG.get(str(item_id or "").strip().lower(), {}).get("tags", ())
        if str(tag).strip()
    }


def _inventory_for(sim, eid):
    return sim.ecs.get(Inventory).get(eid)


def _assets_for(sim, eid):
    return sim.ecs.get(PlayerAssets).get(eid)


def _clone_inventory(inventory):
    clone = Inventory(capacity=getattr(inventory, "capacity", 10))
    clone.items = copy.deepcopy(list(getattr(inventory, "items", ()) or ()))
    return clone


def _inventory_can_accept(inventory, item_id, quantity=1, *, metadata=None, owner_eid=None, owner_tag=None, stack_max=None):
    if not inventory:
        return False
    item_def = ITEM_CATALOG.get(str(item_id or "").strip().lower(), {})
    clone = _clone_inventory(inventory)
    added, _instance_id = clone.add_item(
        item_id,
        quantity=max(1, int(quantity)),
        stack_max=max(1, int(stack_max if stack_max is not None else item_def.get("stack_max", 1) or 1)),
        owner_eid=owner_eid,
        owner_tag=owner_tag,
        metadata=metadata or {},
    )
    return bool(added)


def _add_inventory_item(sim, inventory, item_id, quantity=1, *, metadata=None, owner_eid=None, owner_tag=None, stack_max=None):
    item_def = ITEM_CATALOG.get(str(item_id or "").strip().lower(), {})
    return inventory.add_item(
        item_id,
        quantity=max(1, int(quantity)),
        stack_max=max(1, int(stack_max if stack_max is not None else item_def.get("stack_max", 1) or 1)),
        instance_factory=sim.new_item_instance_id,
        owner_eid=owner_eid,
        owner_tag=owner_tag,
        metadata=metadata or {},
    )


def _has_item(inventory, item_id):
    item_id = str(item_id or "").strip().lower()
    if not inventory or not item_id:
        return False
    return any(str(entry.get("item_id", "")).strip().lower() == item_id for entry in tuple(inventory.items or ()))


def _herbal_preparation_profile(inventory, *, mode="self", ingredient_source_kind="inventory"):
    mode_key = _key(mode or "self")
    source_key = _key(ingredient_source_kind or "inventory")
    has_mortar = _has_item(inventory, MORTAR_KIT_ITEM_ID)
    if mode_key == "herbalist":
        return {
            "method": "herbalist",
            "item_quality": "good",
            "mortar_prepared": False,
            "positive_effect_bonus": 0.10,
            "negative_effect_reduction": 0.06,
            "duration_bonus": 0.06,
            "stability_bonus": 10,
        }
    if has_mortar:
        return {
            "method": "mortar_ground",
            "item_quality": "good",
            "mortar_prepared": True,
            "positive_effect_bonus": 0.12,
            "negative_effect_reduction": 0.06,
            "duration_bonus": 0.08,
            "stability_bonus": 12,
        }
    if source_key == CAMPFIRE_HERB_CACHE_KIND:
        return {
            "method": "campfire_hand_mixed",
            "item_quality": "standard",
            "mortar_prepared": False,
            "positive_effect_bonus": 0.0,
            "negative_effect_reduction": 0.0,
            "duration_bonus": 0.0,
            "stability_bonus": 0,
        }
    return None


def _tool_for_method(inventory, method):
    if method == "pluck":
        return {"item_id": None, "quality": 0.82, "label": "by hand"}
    if not inventory:
        return None
    wanted_ids = DIRECT_CUT_TOOL_IDS if method == "cut" else DIRECT_SCRAPE_TOOL_IDS
    for entry in tuple(inventory.items or ()):
        item_id = str(entry.get("item_id", "") or "").strip().lower()
        if item_id in wanted_ids:
            quality = 0.65 if item_id == "pocket_multitool" else 1.0
            if item_id == "pruning_shears":
                quality = 1.08
            return {"item_id": item_id, "quality": quality, "label": item_display_name(item_id, item_catalog=ITEM_CATALOG)}
        if method == "cut" and _entry_tags(item_id).intersection(CUT_TOOL_TAGS):
            return {"item_id": item_id, "quality": 0.95, "label": item_display_name(item_id, item_catalog=ITEM_CATALOG)}
        if method == "scrape" and _entry_tags(item_id).intersection(CUT_TOOL_TAGS):
            return {"item_id": item_id, "quality": 0.9, "label": item_display_name(item_id, item_catalog=ITEM_CATALOG)}
    return None


@lru_cache(maxsize=4)
def load_herbal_recipe_catalog(path=None):
    source = Path(path) if path else HERBAL_RECIPES_PATH
    with source.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    payload, _metadata = split_object_document(raw)
    rows = {}
    if not isinstance(payload, dict):
        return rows
    for recipe_id, row in payload.items():
        if not isinstance(row, Mapping):
            continue
        key = _key(recipe_id)
        required = tuple(_key(token) for token in row.get("required_classes", ()) if _key(token) in CHEMISTRY_CLASSES)
        if not key or not required:
            continue
        output_item_id = _key(row.get("output_item_id") or key)
        if output_item_id not in ITEM_CATALOG:
            continue
        count = max(2, min(3, _safe_int(row.get("component_count"), len(required))))
        rows[key] = {
            "id": key,
            "name": str(row.get("name") or key.replace("_", " ")).strip() or key.replace("_", " "),
            "output_item_id": output_item_id,
            "component_count": count,
            "required_classes": tuple(required[:count]),
            "service_fee": max(0, _safe_int(row.get("service_fee"), 8)),
            "recipe_price": max(1, _safe_int(row.get("recipe_price"), 16)),
            "tags": tuple(_key(tag) for tag in row.get("tags", ()) if _key(tag)),
            "self_only": bool(row.get("self_only")),
            "campfire_only": bool(row.get("campfire_only")),
        }
    return rows


def ensure_herbal_state(sim):
    if not isinstance(getattr(sim, "herbal_known_plant_traits", None), dict):
        sim.herbal_known_plant_traits = {}
    if not isinstance(getattr(sim, "herbal_known_recipes", None), dict):
        sim.herbal_known_recipes = {}
    return sim.herbal_known_plant_traits, sim.herbal_known_recipes


def _genetics_bias_terms(data):
    if not isinstance(data, Mapping):
        return ()
    # V1 genetics is a rich passive genome. Gameplay chemistry assignment keeps
    # using only the legacy small aliases so nested future traits do not leak.
    allowed_keys = (
        "hue_family",
        "petal_shape",
        "blade_shape",
        "stem_shape",
        "leaf_shape",
        "habit",
        "texture",
        "growth_form",
        "glyph",
    )
    terms = []
    for key in allowed_keys:
        value = data.get(key)
        if value is None:
            continue
        terms.append(str(key))
        terms.append(str(value))
    return tuple(terms)


def _plant_bias_weights(row):
    text_bits = []
    for key in ("id", "name", "growth_form", "rarity"):
        text_bits.append(str(row.get(key, "")))
    for key in ("tags", "crossbreed_tags"):
        text_bits.extend(str(token) for token in row.get(key, ()) or ())
    for key in ("growth_traits", "harvest_potential", "spread_profile"):
        data = row.get(key)
        if isinstance(data, Mapping):
            text_bits.extend(str(k) for k in data.keys())
            text_bits.extend(str(v) for v in data.values())
    text_bits.extend(_genetics_bias_terms(row.get("genetics")))
    text = " ".join(text_bits).strip().lower()
    weights = {}
    for class_id in CHEMISTRY_CLASSES:
        weights[class_id] = 1.0 + sum(1.65 for term in _BIAS_TERMS[class_id] if term in text)
    form = str(row.get("growth_form", "") or "").strip().lower()
    if form in {"vine", "reed"}:
        weights["binding"] += 1.7
        weights["irritant"] += 0.6
    if form in {"moss", "lichen"}:
        weights["catalyst"] += 1.4
        weights["cleansing"] += 0.8
        weights["volatile"] += 0.5
    if form in {"shrub", "fern"}:
        weights["toxic"] += 0.7
        weights["irritant"] += 0.5
    if str(row.get("rarity", "")).strip().lower() == "rare":
        weights["catalyst"] += 1.2
        weights["deliriant"] += 0.7
    return weights


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


def _herbal_flora_catalog(sim):
    """Compose authored and live flora while preserving the loader test seam."""

    catalog = {plant_id: dict(row) for plant_id, row in load_flora_catalog().items()}
    for plant_id, profile in ensure_dynamic_flora_profiles(sim).items():
        if isinstance(profile, dict):
            catalog[_key(plant_id)] = dict(profile)
    return catalog


def herbal_chemistry_profiles(sim):
    state = getattr(sim, "herbal_chemistry_profiles", None)
    seed = int(getattr(sim, "seed", 0) or 0)
    catalog = _herbal_flora_catalog(sim)
    catalog_marker = ",".join(sorted(catalog.keys()))
    native_channels = native_flora_effect_channels(sim)
    effect_marker = repr(tuple(
        (row.get("native_id"), row.get("chemistry_class"), tuple(row.get("secondary_traits") or ()))
        for row in native_channels
    ))
    if (
        isinstance(state, dict)
        and state.get("seed") == seed
        and state.get("catalog_marker") == catalog_marker
        and state.get("native_effect_marker") == effect_marker
    ):
        return dict(state.get("plants", {}) or {})

    rng = random.Random(f"{seed}:herbal-chemistry:v1")
    plant_ids = sorted(catalog.keys())
    rng.shuffle(plant_ids)
    assignments = {}
    for plant_id in plant_ids:
        row = catalog[plant_id]
        # A remembered cultivar keeps its body/shape, but its chemistry is a
        # fresh independent draw in every new world.
        weights = (
            {class_id: 1.0 for class_id in CHEMISTRY_CLASSES}
            if bool(row.get("effect_pool_detached"))
            else _plant_bias_weights(row)
        )
        assignments[plant_id] = _weighted_choice(rng, tuple(weights.items())) or "mending"

    target_count = max(1, min(3, len(plant_ids) // max(1, len(CHEMISTRY_CLASSES))))
    protected = set()
    for class_id in CHEMISTRY_CLASSES:
        while sum(1 for value in assignments.values() if value == class_id) < target_count:
            candidate = None
            best_weight = -1.0
            for plant_id in plant_ids:
                if plant_id in protected:
                    continue
                current = assignments.get(plant_id)
                if sum(1 for value in assignments.values() if value == current) <= target_count:
                    continue
                weight = _plant_bias_weights(catalog[plant_id]).get(class_id, 0.0)
                if weight > best_weight:
                    candidate = plant_id
                    best_weight = weight
            if candidate is None:
                break
            assignments[candidate] = class_id
            protected.add(candidate)

    # Remembered effect channels re-enter the run-wide pool independently of
    # their original cultivar identity.  Avoid the source identity whenever a
    # second plant exists, so a familiar shape never becomes solved chemistry.
    for index, channel in enumerate(native_channels):
        class_id = _key(channel.get("chemistry_class"))
        if class_id not in CHEMISTRY_CLASSES or not plant_ids:
            continue
        source_id = next(
            (
                plant_id
                for plant_id, row in catalog.items()
                if str(row.get("native_lineage_id") or "") == str(channel.get("native_id") or "")
            ),
            "",
        )
        targets = [plant_id for plant_id in plant_ids if plant_id != source_id] or list(plant_ids)
        target_rng = random.Random(f"{seed}:native-flora-effect:{channel.get('native_id')}:{index}")
        assignments[targets[target_rng.randrange(len(targets))]] = class_id

    sim.herbal_chemistry_profiles = {
        "seed": seed,
        "catalog_marker": catalog_marker,
        "native_effect_marker": effect_marker,
        "plants": dict(assignments),
    }
    return dict(assignments)


def _catalog_marker(catalog):
    return ",".join(sorted(str(key) for key in (catalog or {}).keys()))


def _expressed_genetic_secondary_traits(row):
    if not isinstance(row, Mapping):
        return ()
    genetics = row.get("genetics") if isinstance(row.get("genetics"), Mapping) else {}
    expressed = genetics.get("expressed") if isinstance(genetics.get("expressed"), Mapping) else {}
    effects = expressed.get("effects") if isinstance(expressed.get("effects"), Mapping) else {}
    traits = effects.get("traits") if isinstance(effects.get("traits"), (list, tuple, set)) else ()
    rows = []
    for trait in tuple(traits or ()):
        trait_key = _key(trait)
        if trait_key in SECONDARY_TRAITS:
            rows.append(trait_key)
    return tuple(dict.fromkeys(rows))


def _expressed_genetic_chemistry_class(row):
    if not isinstance(row, Mapping):
        return ""
    genetics = row.get("genetics") if isinstance(row.get("genetics"), Mapping) else {}
    expressed = genetics.get("expressed") if isinstance(genetics.get("expressed"), Mapping) else {}
    chemistry = expressed.get("chemistry") if isinstance(expressed.get("chemistry"), Mapping) else {}
    class_id = _key(chemistry.get("main_class"))
    return class_id if class_id in CHEMISTRY_CLASSES else ""


def _secondary_trait_fallback(seed, plant_id, class_id, row):
    marker = str(row.get("rarity") or row.get("growth_form") or "").strip().lower()
    rng = random.Random(f"{int(seed)}:herbal-secondary:v1:{plant_id}:{class_id}:{marker}")
    weights = {trait: 1.0 for trait in FALLBACK_SECONDARY_TRAITS}
    if class_id in {"mending", "hydrating", "calming", "cleansing", "binding"}:
        weights["stabilizer"] += 0.8
    if class_id in {"catalyst", "energizing", "volatile"}:
        weights["potentiator"] += 0.8
    if class_id in {"cooling", "numbing"}:
        weights["diluter"] += 0.6
    if class_id in {"irritant", "toxic", "deliriant", "volatile"}:
        weights["spoiler"] += 0.9
    if str(row.get("rarity", "")).strip().lower() == "rare":
        weights["potentiator"] += 0.5
    return _weighted_choice(rng, tuple(weights.items())) or "stabilizer"


def herbal_secondary_trait_profiles(sim):
    state = getattr(sim, "herbal_secondary_trait_profiles", None)
    seed = int(getattr(sim, "seed", 0) or 0)
    catalog = _herbal_flora_catalog(sim)
    catalog_marker = _catalog_marker(catalog)
    native_channels = native_flora_effect_channels(sim)
    effect_marker = repr(tuple(
        (row.get("native_id"), tuple(row.get("secondary_traits") or ()))
        for row in native_channels
    ))
    class_assignments = herbal_chemistry_profiles(sim)
    chemistry_marker = ",".join(
        f"{plant_id}:{class_assignments.get(plant_id, '')}"
        for plant_id in sorted(catalog)
    )
    if (
        isinstance(state, dict)
        and state.get("seed") == seed
        and state.get("catalog_marker") == catalog_marker
        and state.get("chemistry_marker") == chemistry_marker
        and state.get("native_effect_marker") == effect_marker
    ):
        return {
            _key(plant_id): tuple(_key(trait) for trait in tuple(traits or ()) if _key(trait) in SECONDARY_TRAITS)
            for plant_id, traits in (state.get("plants", {}) or {}).items()
        }

    assignments = {}
    for plant_id in sorted(catalog):
        row = catalog[plant_id]
        explicit = () if bool(row.get("effect_pool_detached")) else _expressed_genetic_secondary_traits(row)
        if explicit:
            assignments[plant_id] = tuple(explicit)
            continue
        class_id = class_assignments.get(plant_id, "") or "mending"
        assignments[plant_id] = (_secondary_trait_fallback(seed, plant_id, class_id, row),)

    plant_ids = sorted(catalog)
    # Each new world starts with a very small, honest genetic reservoir for
    # signed body-effect traits.  They are not recipe-bound: the trait rides
    # the harvested part, can become recessive through crossbreeding, and can
    # return through durable native effect channels in later runs.
    signed_traits = (
        "+wake",
        "-wake",
        "+nourish",
        "-nourish",
        "+hydrate",
        "-hydrate",
    )
    for trait in signed_traits:
        if not plant_ids or any(trait in tuple(values or ()) for values in assignments.values()):
            continue
        candidates = [
            plant_id
            for plant_id in plant_ids
            if not _expressed_genetic_secondary_traits(catalog.get(plant_id, {}))
        ]
        if not candidates:
            continue
        if trait == "+wake":
            preferred = [plant_id for plant_id in candidates if class_assignments.get(plant_id) in {"energizing", "catalyst"}]
            candidates = preferred or candidates
        elif trait == "-wake":
            preferred = [plant_id for plant_id in candidates if class_assignments.get(plant_id) in {"calming", "numbing", "deliriant"}]
            candidates = preferred or candidates
        elif trait in {"+nourish", "-nourish"}:
            preferred = [plant_id for plant_id in candidates if class_assignments.get(plant_id) in {"mending", "toxic"}]
            candidates = preferred or candidates
        elif trait in {"+hydrate", "-hydrate"}:
            preferred = [plant_id for plant_id in candidates if class_assignments.get(plant_id) in {"hydrating", "cooling", "irritant"}]
            candidates = preferred or candidates
        trait_rng = random.Random(f"{seed}:herbal-signed-trait:v1:{trait}")
        target_id = candidates[trait_rng.randrange(len(candidates))]
        assignments[target_id] = tuple(dict.fromkeys(tuple(assignments.get(target_id, ())) + (trait,)))

    for index, channel in enumerate(native_channels):
        traits = tuple(
            _key(trait)
            for trait in tuple(channel.get("secondary_traits") or ())
            if _key(trait) in SECONDARY_TRAITS
        )
        if not traits or not plant_ids:
            continue
        source_id = next(
            (
                plant_id
                for plant_id, row in catalog.items()
                if str(row.get("native_lineage_id") or "") == str(channel.get("native_id") or "")
            ),
            "",
        )
        targets = [plant_id for plant_id in plant_ids if plant_id != source_id] or list(plant_ids)
        target_rng = random.Random(f"{seed}:native-flora-secondary:{channel.get('native_id')}:{index}")
        target_id = targets[target_rng.randrange(len(targets))]
        assignments[target_id] = tuple(dict.fromkeys(tuple(assignments.get(target_id, ())) + traits))

    sim.herbal_secondary_trait_profiles = {
        "seed": seed,
        "catalog_marker": catalog_marker,
        "chemistry_marker": chemistry_marker,
        "native_effect_marker": effect_marker,
        "plants": {plant_id: list(traits) for plant_id, traits in assignments.items()},
    }
    return dict(assignments)


def plant_chemistry_class(sim, plant_id):
    plant_id = _key(plant_id)
    profile = dynamic_flora_profile(sim, plant_id) if plant_id else {}
    if profile and not bool(profile.get("effect_pool_detached")):
        class_id = _key(profile.get("chemistry_class")) or _expressed_genetic_chemistry_class(profile)
        if class_id in CHEMISTRY_CLASSES:
            return class_id
    return str(herbal_chemistry_profiles(sim).get(plant_id, "") or "").strip().lower()


def plant_secondary_traits(sim, plant_id):
    plant_id = _key(plant_id)
    profile = dynamic_flora_profile(sim, plant_id) if plant_id else {}
    if profile and not bool(profile.get("effect_pool_detached")):
        explicit = tuple(
            _key(trait)
            for trait in tuple(profile.get("secondary_traits") or ())
            if _key(trait) in SECONDARY_TRAITS
        )
        if explicit:
            return tuple(dict.fromkeys(explicit))
        genetic = _expressed_genetic_secondary_traits(profile)
        if genetic:
            return tuple(dict.fromkeys(genetic))
    traits = herbal_secondary_trait_profiles(sim).get(plant_id, ()) if plant_id else ()
    return tuple(_key(trait) for trait in tuple(traits or ()) if _key(trait) in SECONDARY_TRAITS)


def secondary_trait_labels(traits):
    return tuple(
        SECONDARY_TRAIT_LABELS.get(_key(trait), _key(trait).replace("_", " "))
        for trait in tuple(traits or ())
        if _key(trait) in SECONDARY_TRAITS
    )


def _clamp_float(value, lo, hi):
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = float(lo)
    return max(float(lo), min(float(hi), parsed))


def _entry_secondary_traits(sim, entry):
    metadata = entry.get("metadata") if isinstance(entry, Mapping) else {}
    if not isinstance(metadata, Mapping):
        metadata = {}
    raw_traits = metadata.get("secondary_traits") if isinstance(metadata.get("secondary_traits"), (list, tuple, set)) else ()
    traits = tuple(
        _key(trait)
        for trait in tuple(raw_traits or ())
        if _key(trait) in SECONDARY_TRAITS
    )
    plant_id = _key(metadata.get("source_plant_id"))
    if plant_id and not traits:
        traits = plant_secondary_traits(sim, plant_id)
    return traits


def _secondary_trait_counts_from_entries(sim, selected):
    counts = {trait: 0 for trait in SECONDARY_TRAITS}
    for entry in tuple(selected or ()):
        if not isinstance(entry, Mapping):
            continue
        for trait in _entry_secondary_traits(sim, entry):
            counts[trait] = int(counts.get(trait, 0)) + 1
    return counts


def _secondary_trait_counts_from_payload(component_payload):
    counts = {trait: 0 for trait in SECONDARY_TRAITS}
    for row in tuple(component_payload or ()):
        if not isinstance(row, Mapping):
            continue
        for trait in tuple(row.get("secondary_traits", ()) or ()):
            trait_key = _key(trait)
            if trait_key in SECONDARY_TRAITS:
                counts[trait_key] = int(counts.get(trait_key, 0)) + 1
    return counts


def herbal_weak_toxic_chance_for_traits(trait_counts=None):
    counts = trait_counts if isinstance(trait_counts, Mapping) else {}
    chance = 0.55
    chance += 0.15 * _safe_int(counts.get("spoiler"), 0)
    chance -= 0.15 * _safe_int(counts.get("stabilizer"), 0)
    chance += 0.08 * _safe_int(counts.get("potentiator"), 0)
    chance -= 0.08 * _safe_int(counts.get("diluter"), 0)
    return _clamp_float(chance, 0.10, 0.90)


def _herbal_stability_band(score):
    score = int(max(0, min(100, _safe_int(score, 0))))
    if score >= 75:
        return "stable"
    if score >= 55:
        return "temperamental"
    if score >= 35:
        return "volatile"
    if score >= 20:
        return "feral"
    return "collapsed"


def _herbal_item_allows_decay(item_id):
    item_def = ITEM_CATALOG.get(_key(item_id), {})
    tags = {
        str(tag).strip().lower()
        for tag in tuple(item_def.get("tags", ()) or ())
        if str(tag).strip()
    }
    if item_def.get("throw_profile") or item_def.get("trap_profile"):
        return False
    if tags.intersection({"aerosol", "throwable", "trap", "aerosol_trap"}):
        return False
    return "consumable" in tags or "herbal_medicine" in tags or "experimental" in tags


def _herbal_trait_result_read(trait_counts, band):
    reads = []
    if _safe_int(trait_counts.get("potentiator"), 0) > _safe_int(trait_counts.get("diluter"), 0):
        reads.append("stronger")
    elif _safe_int(trait_counts.get("diluter"), 0) > _safe_int(trait_counts.get("potentiator"), 0):
        reads.append("weaker")
    if band == "stable":
        reads.append("stable")
    elif band in {"feral", "collapsed"}:
        reads.append("spoiling soon")
    elif band in {"temperamental", "volatile"}:
        reads.append("unstable")
    return ", ".join(dict.fromkeys(reads))


def _herbal_trait_effect_metadata(
    sim,
    trait_counts,
    *,
    experiment_result="",
    mode="self",
    output_item_id="",
    preparation=None,
):
    counts = {trait: max(0, _safe_int((trait_counts or {}).get(trait), 0)) for trait in SECONDARY_TRAITS}
    preparation = preparation if isinstance(preparation, Mapping) else {}
    result_key = _key(experiment_result) or "recipe"
    base_score = HERBAL_STABILITY_BASE_SCORES.get(result_key, HERBAL_STABILITY_BASE_SCORES["recipe"])
    stability_score = int(base_score)
    stability_score += 15 * counts["stabilizer"]
    stability_score -= 18 * counts["spoiler"]
    stability_score += 4 * counts["diluter"]
    stability_score -= 5 * counts["potentiator"]
    stability_score += _safe_int(preparation.get("stability_bonus"), 0)
    stability_score = int(max(0, min(100, stability_score)))
    band = _herbal_stability_band(stability_score)

    positive_scalar = _clamp_float(
        1.0
        + (0.14 * counts["potentiator"])
        - (0.12 * counts["diluter"])
        + (0.04 * counts["stabilizer"])
        - (0.06 * counts["spoiler"])
        + _safe_float(preparation.get("positive_effect_bonus"), 0.0),
        0.50,
        1.75,
    )
    negative_scalar = _clamp_float(
        1.0
        + (0.06 * counts["potentiator"])
        - (0.12 * counts["diluter"])
        - (0.08 * counts["stabilizer"])
        + (0.16 * counts["spoiler"])
        - _safe_float(preparation.get("negative_effect_reduction"), 0.0),
        0.50,
        2.00,
    )
    duration_scalar = _clamp_float(
        1.0
        + (0.06 * counts["potentiator"])
        - (0.04 * counts["diluter"])
        + (0.08 * counts["stabilizer"])
        - (0.04 * counts["spoiler"])
        + _safe_float(preparation.get("duration_bonus"), 0.0),
        0.50,
        1.75,
    )

    metadata = {
        "trait_effects_applied": {trait: count for trait, count in counts.items() if count > 0},
        "item_positive_effect_scalar": round(positive_scalar, 3),
        "item_negative_effect_scalar": round(negative_scalar, 3),
        "item_status_duration_scalar": round(duration_scalar, 3),
        "stability_score": stability_score,
        "stability_band": band,
    }
    def _signed_stack(positive, negative):
        positive_count = min(5, max(0, _safe_int(counts.get(positive), 0)))
        negative_count = min(5, max(0, _safe_int(counts.get(negative), 0)))
        return max(-5, min(5, positive_count - negative_count))

    wake_stack = _signed_stack("+wake", "-wake")
    nourish_stack = _signed_stack("+nourish", "-nourish")
    hydrate_stack = _signed_stack("+hydrate", "-hydrate")
    signed_stacks = {
        key: value
        for key, value in {
            "wake": wake_stack,
            "nourish": nourish_stack,
            "hydrate": hydrate_stack,
        }.items()
        if value
    }
    if signed_stacks:
        metadata["herbal_signed_effect_stacks"] = signed_stacks
    if wake_stack:
        metadata["herbal_wakefulness_delta"] = float(wake_stack * 10.0)
    if nourish_stack:
        metadata["herbal_hunger_delta"] = float(nourish_stack * 12.0)
    if hydrate_stack:
        metadata["herbal_thirst_delta"] = float(hydrate_stack * 12.0)
    result_read = _herbal_trait_result_read(counts, band)
    if result_read:
        metadata["herbal_result_read"] = result_read
    if band != "stable" and _herbal_item_allows_decay(output_item_id):
        window = int(HERBAL_STABILITY_WINDOWS.get(band, HERBAL_STABILITY_WINDOWS["collapsed"]))
        metadata["stability_window_ticks"] = window
        metadata["breakdown_tick"] = _safe_int(getattr(sim, "tick", 0), 0) + window
        metadata["herbal_decay"] = True
    return metadata


def herbal_ingredient_display_name(item_id, plant_name):
    item_id = _key(item_id)
    plant_name = str(plant_name or "").replace("_", " ").strip()
    part = HERBAL_INGREDIENT_DISPLAY_PARTS.get(item_id, "")
    if not plant_name or not part:
        return item_display_name(item_id, item_catalog=ITEM_CATALOG)
    return f"{plant_name.title()} {part}"


def known_plant_traits_for_actor(sim, eid):
    known_traits, _known_recipes = ensure_herbal_state(sim)
    return dict(known_traits.get(_actor_key(eid), {}) or {})


def known_recipes_for_actor(sim, eid):
    _known_traits, known_recipes = ensure_herbal_state(sim)
    return dict(known_recipes.get(_actor_key(eid), {}) or {})


def plant_trait_known(sim, eid, plant_id):
    return _key(plant_id) in known_plant_traits_for_actor(sim, eid)


def learn_plant_trait(sim, eid, plant_id, *, source_kind="recipe"):
    plant_id = _key(plant_id)
    class_id = plant_chemistry_class(sim, plant_id)
    if not plant_id or not class_id:
        return False
    known_traits, _known_recipes = ensure_herbal_state(sim)
    actor_key = _actor_key(eid)
    rows = known_traits.setdefault(actor_key, {})
    was_new = plant_id not in rows
    existing = rows.get(plant_id)
    row = dict(existing) if isinstance(existing, Mapping) else {}
    tick = _safe_int(getattr(sim, "tick", 0), 0)
    source = str(source_kind or "recipe").strip().lower() or "recipe"
    if not row.get("learned_tick"):
        row["learned_tick"] = tick
    row["chemistry_class"] = class_id
    row["source_kind"] = source
    existing_traits = [
        _key(trait)
        for trait in tuple(row.get("secondary_traits", ()) or ())
        if _key(trait) in SECONDARY_TRAITS
    ]
    merged_traits = tuple(dict.fromkeys(tuple(existing_traits) + plant_secondary_traits(sim, plant_id)))
    if merged_traits:
        if tuple(existing_traits) != merged_traits:
            row["secondary_learned_tick"] = tick
            row["secondary_source_kind"] = source
        row["secondary_traits"] = list(merged_traits)
    rows[plant_id] = row
    return was_new


def learn_herbal_recipe(sim, eid, recipe_id, *, source_kind="recipe_sale", reveal_plants=True, prop=None):
    recipes = load_herbal_recipe_catalog()
    recipe_id = _key(recipe_id)
    if recipe_id not in recipes:
        return None
    _known_traits, known_recipes = ensure_herbal_state(sim)
    actor_key = _actor_key(eid)
    rows = known_recipes.setdefault(actor_key, {})
    was_new = recipe_id not in rows
    rows[recipe_id] = {
        "learned_tick": _safe_int(getattr(sim, "tick", 0), 0),
        "source_kind": str(source_kind or "recipe_sale").strip().lower() or "recipe_sale",
    }
    revealed = ()
    if reveal_plants:
        recipe = recipes[recipe_id]
        revealed = tuple(_reveal_recipe_plants(sim, eid, recipe, prop=prop, limit=max(1, int(recipe.get("component_count", 2) or 2))))
    return {"recipe": recipes[recipe_id], "was_new": was_new, "revealed_plants": revealed}


def _plants_near_actor(sim, eid, radius=12):
    pos = sim.ecs.get(Position).get(eid)
    if pos is None:
        return ()
    rows = flora_records_in_rect(sim, int(pos.x) - radius, int(pos.y) - radius, int(pos.x) + radius, int(pos.y) + radius, z=int(pos.z))
    return tuple(row for row in rows if isinstance(row, dict))


def _plants_in_property_chunk(sim, prop):
    if not isinstance(prop, Mapping):
        return ()
    try:
        x = int(prop.get("x", 0) or 0)
        y = int(prop.get("y", 0) or 0)
        z = int(prop.get("z", 0) or 0)
    except (TypeError, ValueError):
        return ()
    chunk = sim.chunk_coords(x, y)
    rows = []
    for row in getattr(sim, "flora_patches", {}).values() if isinstance(getattr(sim, "flora_patches", None), dict) else ():
        if not isinstance(row, Mapping):
            continue
        try:
            row_z = int(row.get("z", 0) or 0)
            raw_chunk = row.get("chunk")
            row_chunk = (
                (int(raw_chunk[0]), int(raw_chunk[1]))
                if isinstance(raw_chunk, (tuple, list)) and len(raw_chunk) == 2
                else sim.chunk_coords(int(row.get("x", 0) or 0), int(row.get("y", 0) or 0))
            )
        except (TypeError, ValueError):
            continue
        if row_z == z and tuple(row_chunk) == tuple(chunk):
            rows.append(row)
    return tuple(sorted(rows, key=lambda row: (str(row.get("plant_id", "")), str(row.get("id", "")))))


def herbalist_local_recipe_ids(sim, prop, *, include_self_only=False):
    recipes = load_herbal_recipe_catalog()
    if not isinstance(prop, Mapping):
        return tuple(
            recipe_id
            for recipe_id, recipe in recipes.items()
            if include_self_only or _recipe_available_for_sale(recipe)
        )
    assignments = herbal_chemistry_profiles(sim)
    local_classes = {
        assignments.get(_key(row.get("plant_id")))
        for row in _plants_in_property_chunk(sim, prop)
        if _key(row.get("plant_id"))
    }
    local_classes.discard(None)
    local_classes.discard("")
    available = []
    for recipe_id, recipe in recipes.items():
        if not include_self_only and not _recipe_available_for_sale(recipe):
            continue
        required = {
            _key(class_id)
            for class_id in tuple(recipe.get("required_classes", ()) or ())
            if _key(class_id)
        }
        if required and required.issubset(local_classes):
            available.append(recipe_id)
    return tuple(available)


def _reveal_recipe_plants(sim, eid, recipe, *, prop=None, limit=2):
    required = tuple(dict.fromkeys(str(class_id or "").strip().lower() for class_id in tuple(recipe.get("required_classes", ()) or ()) if str(class_id or "").strip()))
    if not required:
        return ()
    catalog = _herbal_flora_catalog(sim)
    assignments = herbal_chemistry_profiles(sim)
    nearby_by_class = {class_id: [] for class_id in required}
    source_rows = _plants_in_property_chunk(sim, prop) if isinstance(prop, Mapping) else _plants_near_actor(sim, eid)
    for row in source_rows:
        plant_id = _key(row.get("plant_id"))
        class_id = assignments.get(plant_id)
        if plant_id and class_id in nearby_by_class:
            nearby_by_class[class_id].append(plant_id)
    fallback_by_class = {
        class_id: [plant_id for plant_id in sorted(catalog) if assignments.get(plant_id) == class_id]
        for class_id in required
    }
    seed_bits = [getattr(sim, "seed", 0), getattr(sim, "tick", 0), eid, recipe.get("id")]
    if isinstance(prop, Mapping):
        seed_bits.append(prop.get("id") or prop.get("name"))
    rng = random.Random(":".join(str(bit) for bit in seed_bits))
    revealed = []
    limit = max(1, int(limit))
    for class_id in required:
        if len(revealed) >= max(1, int(limit)):
            break
        nearby = list(dict.fromkeys(nearby_by_class.get(class_id, ())))
        fallback = (
            []
            if isinstance(prop, Mapping)
            else [plant_id for plant_id in fallback_by_class.get(class_id, ()) if plant_id not in nearby]
        )
        rng.shuffle(nearby)
        rng.shuffle(fallback)
        for plant_id in tuple(nearby + fallback):
            learn_plant_trait(sim, eid, plant_id, source_kind="recipe_sale")
            revealed.append({
                "plant_id": plant_id,
                "plant_name": catalog.get(plant_id, {}).get("name", plant_id.replace("_", " ")),
                "chemistry_class": assignments.get(plant_id),
                "secondary_traits": list(plant_secondary_traits(sim, plant_id)),
            })
            break
    if len(revealed) < limit and not isinstance(prop, Mapping):
        already = {row.get("plant_id") for row in revealed if isinstance(row, dict)}
        fallback = [plant_id for plant_id in sorted(catalog) if assignments.get(plant_id) in required and plant_id not in already]
        rng.shuffle(fallback)
        for plant_id in fallback:
            if len(revealed) >= limit:
                break
            learn_plant_trait(sim, eid, plant_id, source_kind="recipe_sale")
            revealed.append({
                "plant_id": plant_id,
                "plant_name": catalog.get(plant_id, {}).get("name", plant_id.replace("_", " ")),
                "chemistry_class": assignments.get(plant_id),
                "secondary_traits": list(plant_secondary_traits(sim, plant_id)),
            })
    return tuple(revealed)


def _recipe_local_affinity_score(sim, eid, recipe):
    required = set(recipe.get("required_classes", ()) or ())
    if not required:
        return (0, 0, 0)
    assignments = herbal_chemistry_profiles(sim)
    nearby_classes = {
        assignments.get(_key(row.get("plant_id")))
        for row in _plants_near_actor(sim, eid, radius=18)
        if isinstance(row, Mapping)
    }
    coverage = len(required.intersection(nearby_classes))
    return (1 if coverage >= len(required) else 0, coverage, -len(required))


def _update_flora_record(sim, record_id, updates):
    patches = getattr(sim, "flora_patches", None)
    if not isinstance(patches, dict):
        return None
    record = patches.get(str(record_id or ""))
    if not isinstance(record, dict):
        return None
    record.update(dict(updates or {}))
    chunk = record.get("chunk")
    if isinstance(chunk, (tuple, list)) and len(chunk) == 2:
        key = (int(chunk[0]), int(chunk[1]))
        chunk_records = getattr(sim, "chunk_flora_records", None)
        if isinstance(chunk_records, dict):
            bucket = []
            for row in tuple(chunk_records.get(key, ()) or ()):
                if isinstance(row, dict) and str(row.get("id", "")) == str(record_id):
                    bucket.append(dict(record))
                else:
                    bucket.append(row)
            chunk_records[key] = bucket
    return record


def _nearest_flora_matching(
    sim,
    x,
    y,
    z=0,
    *,
    radius=1,
    preferred_dir=None,
    exact_direction=False,
    harvestable=None,
    exhausted_only=False,
):
    target = None
    if exact_direction and isinstance(preferred_dir, tuple) and len(preferred_dir) >= 2:
        dx = _safe_int(preferred_dir[0], 0)
        dy = _safe_int(preferred_dir[1], 0)
        if dx or dy:
            target = (int(x) + dx, int(y) + dy, int(z))
    rows = []
    for record in getattr(sim, "flora_patches", {}).values() if isinstance(getattr(sim, "flora_patches", None), dict) else ():
        if not isinstance(record, dict):
            continue
        is_harvestable = flora_patch_harvestable(record)
        normalized = normalize_flora_harvest_state(record)
        is_exhausted = _key(normalized.get("stage")) in EXHAUSTED_FLORA_STAGES
        if harvestable is True and not is_harvestable:
            continue
        if harvestable is False and is_harvestable:
            continue
        if exhausted_only and not is_exhausted:
            continue
        rx, ry, rz = _safe_int(record.get("x"), 0), _safe_int(record.get("y"), 0), _safe_int(record.get("z"), 0)
        if rz != int(z):
            continue
        if target is not None and (rx, ry, rz) != target:
            continue
        if target is not None:
            distance = max(abs(int(x) - rx), abs(int(y) - ry))
        else:
            distance = _manhattan(int(x), int(y), rx, ry)
        if distance > int(radius):
            continue
        try:
            if not has_line_of_sight(sim, int(x), int(y), int(z), rx, ry, rz):
                continue
        except Exception:
            pass
        rows.append((distance, str(record.get("id", "")), record))
    rows.sort(key=lambda item: (item[0], item[1]))
    return rows[0][2] if rows else None


def nearest_harvestable_flora(sim, x, y, z=0, *, radius=1, preferred_dir=None, exact_direction=False):
    return _nearest_flora_matching(
        sim,
        x,
        y,
        z,
        radius=radius,
        preferred_dir=preferred_dir,
        exact_direction=exact_direction,
        harvestable=True,
    )


def nearest_exhausted_flora(sim, x, y, z=0, *, radius=1, preferred_dir=None, exact_direction=False):
    return _nearest_flora_matching(
        sim,
        x,
        y,
        z,
        radius=radius,
        preferred_dir=preferred_dir,
        exact_direction=exact_direction,
        exhausted_only=True,
    )


def _harvest_units(record, tool):
    form = str(record.get("growth_form", "") or "").strip().lower()
    base = 1
    if form == "flower":
        base = 2
    if form in {"shrub", "vine", "reed"}:
        base = 2
    if str(record.get("rarity", "")).strip().lower() == "rare":
        base = max(1, base - 1)
    quality = _safe_float((tool or {}).get("quality"), 1.0)
    if quality >= 1.05 and form in {"shrub", "vine", "reed", "fern"}:
        base += 1
    if quality < 0.75:
        base = max(1, int(round(base * 0.65)))
    return max(1, int(base))


def harvest_flora_patch(sim, eid, flora_id=None, *, preferred_dir=None, exact_direction=False):
    pos = sim.ecs.get(Position).get(eid)
    inventory = _inventory_for(sim, eid)
    if pos is None or not inventory:
        sim.emit(Event("flora_harvest_blocked", eid=eid, flora_id=flora_id, reason="no_inventory"))
        return False
    record = None
    if flora_id:
        record = getattr(sim, "flora_patches", {}).get(str(flora_id))
    if not isinstance(record, dict):
        record = nearest_harvestable_flora(
            sim,
            pos.x,
            pos.y,
            pos.z,
            radius=1,
            preferred_dir=preferred_dir,
            exact_direction=exact_direction,
        )
    if not isinstance(record, dict):
        sim.emit(Event("flora_harvest_blocked", eid=eid, flora_id=flora_id, reason="no_flora"))
        return False
    record = normalize_flora_harvest_state(record)
    if not flora_patch_harvestable(record):
        sim.emit(Event("flora_harvest_blocked", eid=eid, flora_id=record.get("id"), plant_name=record.get("name"), reason="picked"))
        return False
    form = str(record.get("growth_form", "") or "").strip().lower()
    method = HARVEST_METHOD_BY_FORM.get(form, "pluck")
    tool = _tool_for_method(inventory, method)
    if not tool:
        sim.emit(Event(
            "flora_harvest_blocked",
            eid=eid,
            flora_id=record.get("id"),
            plant_name=record.get("name"),
            growth_form=form,
            harvest_method=method,
            reason="no_tool",
        ))
        return False
    item_id = INGREDIENT_ITEM_BY_FORM.get(form, "leaf_clippings")
    plant_id = _key(record.get("plant_id"))
    class_id = _key(record.get("chemistry_class")) or plant_chemistry_class(sim, plant_id)
    secondary_traits = tuple(
        _key(trait)
        for trait in tuple(record.get("secondary_traits") or plant_secondary_traits(sim, plant_id) or ())
        if _key(trait) in SECONDARY_TRAITS
    )
    harvest_context = flora_harvest_context(sim, record)
    base_units = _harvest_units(record, tool) + int(harvest_context.get("unit_bonus", 0) or 0)
    units = max(1, int(round(float(base_units) * float(harvest_context.get("yield_factor", 1.0) or 1.0))))
    quality_value = _safe_float(tool.get("quality"), 1.0)
    quality = "clean" if quality_value >= 1.0 else "rough"
    if str(harvest_context.get("bloom_state")) == "closed":
        quality = "tight"
    elif str(harvest_context.get("bloom_state")) == "night_open" and quality_value >= 0.75:
        quality = "bright"
    metadata = {
        "source": "flora",
        "source_context": "harvested",
        "source_plant_id": plant_id,
        "source_plant_name": str(record.get("name") or plant_id.replace("_", " ")).strip(),
        "growth_form": form,
        "chemistry_class": class_id,
        "secondary_traits": list(secondary_traits),
        "color_key": record.get("color_key"),
        "color_word": record.get("color_word"),
        "render_key": record.get("render_key"),
        "glyph": record.get("glyph"),
        "rarity": record.get("rarity"),
        "tags": list(record.get("tags") or ()),
        "crossbreed_tags": list(record.get("crossbreed_tags") or ()),
        "hybrid_generation": _safe_int(record.get("hybrid_generation"), 0),
        "parent_plant_ids": list(record.get("parent_plant_ids") or ()),
        "lineage": dict(record.get("lineage") or {}),
        "dynamic_flora": bool(record.get("dynamic_flora")),
        "stability_score": record.get("stability_score"),
        "stability_band": record.get("stability_band"),
        "notability": record.get("notability"),
        "harvest_method": method,
        "plant_part": str(harvest_context.get("plant_part") or "").strip().lower(),
        "bloom_state": str(harvest_context.get("bloom_state") or "").strip().lower(),
        "day_phase": str(harvest_context.get("day_phase") or "").strip().lower(),
        "harvest_hour": int(harvest_context.get("harvest_hour", 0) or 0),
        # Inventory quantity is the material count.  Keep the metadata value
        # per unit so splitting or consuming one item cannot duplicate a whole
        # harvest batch's potency.
        "material_units": 1,
        "harvest_batch_units": int(units),
        "quality": quality,
        "quality_hint": str(harvest_context.get("quality_hint") or "").strip().lower(),
        "harvested_tick": _safe_int(getattr(sim, "tick", 0), 0),
        "legal_status": "legal",
    }
    if isinstance(record.get("genetics"), Mapping):
        metadata["genetics"] = copy.deepcopy(dict(record.get("genetics") or {}))
    metadata["display_name"] = herbal_ingredient_display_name(item_id, metadata["source_plant_name"])
    if tool.get("item_id"):
        metadata["tool_item_id"] = tool.get("item_id")
    owner_tag = "player" if eid == getattr(sim, "player_eid", None) else "npc"
    if not _inventory_can_accept(inventory, item_id, units, metadata=metadata, owner_eid=eid, owner_tag=owner_tag):
        sim.emit(Event(
            "flora_harvest_blocked",
            eid=eid,
            flora_id=record.get("id"),
            plant_name=record.get("name"),
            output_item_id=item_id,
            reason="inventory_full",
        ))
        return False
    added, instance_id = _add_inventory_item(
        sim,
        inventory,
        item_id,
        units,
        metadata=metadata,
        owner_eid=eid,
        owner_tag=owner_tag,
    )
    if not added:
        sim.emit(Event("flora_harvest_blocked", eid=eid, flora_id=record.get("id"), plant_name=record.get("name"), reason="inventory_full"))
        return False
    harvest_updates = flora_harvest_updates_after_pick(
        record,
        eid=eid,
        tick=getattr(sim, "tick", 0),
        method=method,
        item_id=item_id,
        instance_id=instance_id,
    )
    updated_record = _update_flora_record(sim, record.get("id"), harvest_updates) or harvest_updates
    try:
        from game.cultivation_runtime import sync_cultivation_from_flora_patch

        sync_cultivation_from_flora_patch(sim, updated_record)
    except Exception:
        pass
    remaining_after = flora_harvest_remaining(updated_record)
    sim.emit(Event(
        "flora_harvested",
        eid=eid,
        flora_id=record.get("id"),
        plant_id=plant_id,
        plant_name=metadata["source_plant_name"],
        growth_form=form,
        harvest_method=method,
        tool_item_id=tool.get("item_id"),
        material_units=int(units),
        output_quantity=int(units),
        output_item_id=item_id,
        output_item_name=item_display_name_for_actor(
            sim,
            eid,
            {"item_id": item_id, "metadata": metadata},
            item_catalog=ITEM_CATALOG,
        ),
        output_instance_id=instance_id,
        plant_part=metadata.get("plant_part"),
        bloom_state=metadata.get("bloom_state"),
        day_phase=metadata.get("day_phase"),
        harvest_hour=metadata.get("harvest_hour"),
        quality=metadata.get("quality"),
        harvest_count=_safe_int(updated_record.get("harvest_count"), 1),
        harvest_limit=_safe_int(updated_record.get("harvest_limit"), 1),
        harvest_remaining=remaining_after,
        harvest_exhausted=remaining_after <= 0,
        x=int(record.get("x", 0) or 0),
        y=int(record.get("y", 0) or 0),
        z=int(record.get("z", 0) or 0),
    ))
    return True


def _source_entries(source):
    if not source:
        return ()
    if hasattr(source, "items"):
        return tuple(getattr(source, "items", ()) or ())
    if isinstance(source, (list, tuple)):
        return tuple(source)
    return ()


def _ingredient_entries(inventory):
    entries = _source_entries(inventory)
    if not entries:
        return ()
    rows = []
    for entry in entries:
        item_id = str(entry.get("item_id", "") or "").strip().lower()
        tags = _entry_tags(item_id)
        if item_id in HERBAL_INGREDIENT_ITEM_IDS or "herbal_ingredient" in tags:
            rows.append(entry)
    return tuple(rows)


def _entry_chemistry_class_for_actor(sim, eid, entry, *, require_known=True):
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), Mapping) else {}
    plant_id = _key(metadata.get("source_plant_id"))
    class_id = _key(metadata.get("chemistry_class"))
    if not plant_id or not class_id:
        return ""
    if require_known and not plant_trait_known(sim, eid, plant_id):
        return ""
    return class_id


def _auto_select_ingredients(sim, eid, recipe, inventory):
    selected = []
    used = set()
    entries = _ingredient_entries(inventory)
    for class_id in tuple(recipe.get("required_classes", ()) or ()):
        found = None
        for entry in entries:
            instance_id = str(entry.get("instance_id", "") or "")
            if instance_id in used:
                continue
            if _entry_chemistry_class_for_actor(sim, eid, entry, require_known=True) == class_id:
                found = entry
                break
        if found is None:
            return ()
        used.add(str(found.get("instance_id", "") or ""))
        selected.append(found)
    return tuple(selected)


def _validate_selected_ingredients(sim, eid, recipe, inventory, instance_ids):
    selected = _selected_ingredient_entries(inventory, instance_ids, min_count=int(recipe.get("component_count", 2)))
    if selected is None:
        return None
    required = list(recipe.get("required_classes", ()) or ())
    classes = [_entry_chemistry_class_for_actor(sim, eid, entry, require_known=False) for entry in selected]
    for entry in selected:
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), Mapping) else {}
        if metadata.get("source_plant_id"):
            learn_plant_trait(sim, eid, metadata.get("source_plant_id"), source_kind="experiment")
    if sorted(classes) != sorted(required):
        return None
    return tuple(selected)


def _selected_ingredient_entries(inventory, instance_ids, *, min_count=2, max_count=3):
    wanted = [str(value or "").strip() for value in tuple(instance_ids or ()) if str(value or "").strip()]
    if len(wanted) != len(set(wanted)) or len(wanted) < int(min_count) or len(wanted) > int(max_count):
        return None
    by_id = {
        str(entry.get("instance_id", "") or ""): entry
        for entry in _ingredient_entries(inventory)
    }
    selected = []
    for instance_id in wanted[: int(max_count)]:
        entry = by_id.get(instance_id)
        if entry is None:
            return None
        selected.append(entry)
    return tuple(selected)


def _recipe_matching_classes(recipes, class_ids):
    selected = sorted(_key(class_id) for class_id in tuple(class_ids or ()) if _key(class_id))
    if len(selected) < 2:
        return None
    for recipe in recipes.values():
        required = sorted(_key(class_id) for class_id in tuple(recipe.get("required_classes", ()) or ()) if _key(class_id))
        if selected == required:
            return recipe
    return None


def _class_overlap_count(required, selected):
    pool = [_key(class_id) for class_id in tuple(selected or ()) if _key(class_id)]
    count = 0
    for class_id in tuple(required or ()):
        class_id = _key(class_id)
        if class_id in pool:
            count += 1
            pool.remove(class_id)
    return int(count)


def _nearest_one_wrong_recipe(recipes, class_ids):
    selected = tuple(_key(class_id) for class_id in tuple(class_ids or ()) if _key(class_id))
    if len(selected) < 2:
        return None
    best = None
    for index, recipe in enumerate(recipes.values()):
        required = tuple(_key(class_id) for class_id in tuple(recipe.get("required_classes", ()) or ()) if _key(class_id))
        if len(required) != len(selected):
            continue
        overlap = _class_overlap_count(required, selected)
        if overlap != len(required) - 1:
            continue
        row = (overlap, -index, recipe)
        if best is None or row[:2] > best[:2]:
            best = row
    return best[2] if best else None


def _recipe_outputs_throwable(recipe):
    item_id = _key((recipe or {}).get("output_item_id"))
    item_def = ITEM_CATALOG.get(item_id, {})
    tags = {str(tag).strip().lower() for tag in item_def.get("tags", ()) if str(tag).strip()}
    return bool(item_def.get("throw_profile") or "throwable" in tags or "aerosol" in tags)


def _recipe_allowed_for_mode(recipe, mode):
    mode = _key(mode or "self")
    if bool((recipe or {}).get("self_only")) or bool((recipe or {}).get("campfire_only")):
        return mode == "self"
    return True


def _recipe_available_for_sale(recipe):
    return not (bool((recipe or {}).get("self_only")) or bool((recipe or {}).get("campfire_only")))


def _experimental_mix_roll(sim, eid, selected, class_ids):
    instance_bits = ",".join(str(entry.get("instance_id", "") or "") for entry in tuple(selected or ()))
    class_bits = ",".join(_key(class_id) for class_id in tuple(class_ids or ()) if _key(class_id))
    return random.Random(f"{getattr(sim, 'seed', 0)}:{getattr(sim, 'tick', 0)}:{eid}:herbal-experiment:{instance_bits}:{class_bits}")


def _free_mix_class_effect_profile(class_ids, trait_counts=None):
    classes = tuple(_key(class_id) for class_id in tuple(class_ids or ()) if _key(class_id))
    class_counts = {class_id: classes.count(class_id) for class_id in CHEMISTRY_CLASSES if class_id in classes}
    trait_counts = trait_counts if isinstance(trait_counts, Mapping) else {}
    hp_delta = 6.0 * class_counts.get("mending", 0)
    thirst_delta = (
        (10.0 * class_counts.get("hydrating", 0))
        + (3.0 * class_counts.get("cooling", 0))
    )
    energy_delta = 9.0 * class_counts.get("energizing", 0)
    safety_delta = (
        (7.0 * class_counts.get("calming", 0))
        + (4.0 * class_counts.get("cleansing", 0))
        + (3.0 * class_counts.get("numbing", 0))
        + (2.0 * class_counts.get("cooling", 0))
    )
    signed_positive = sum(
        max(0, _safe_int(trait_counts.get(positive), 0) - _safe_int(trait_counts.get(negative), 0))
        for positive, negative in (
            ("+wake", "-wake"),
            ("+nourish", "-nourish"),
            ("+hydrate", "-hydrate"),
        )
    )
    hazardous = sum(class_counts.get(class_id, 0) for class_id in ("irritant", "toxic", "deliriant", "volatile"))
    helpful = bool(hp_delta or thirst_delta or energy_delta or safety_delta or signed_positive)
    if hp_delta:
        display_name = "Improvised Restorative Blend"
    elif thirst_delta:
        display_name = "Improvised Hydrating Blend"
    elif energy_delta:
        display_name = "Improvised Invigorating Blend"
    elif safety_delta:
        display_name = "Improvised Soothing Blend"
    else:
        display_name = "Improvised Herbal Blend"
    metadata = {
        "display_name": display_name,
        "herbal_class_effects": {
            "classes": dict(class_counts),
            "hp": hp_delta,
            "energy": energy_delta,
            "safety": safety_delta,
            "thirst": thirst_delta,
        },
    }
    if hp_delta:
        metadata["herbal_hp_delta"] = hp_delta
    if energy_delta:
        metadata["item_extra_energy_delta"] = energy_delta
    if safety_delta:
        metadata["item_extra_safety_delta"] = safety_delta
    if thirst_delta:
        metadata["herbal_thirst_delta"] = thirst_delta
    return {
        "helpful": helpful,
        "hazardous": hazardous,
        "metadata": metadata,
    }


def herbal_free_mix_success_chance(class_ids, trait_counts=None, *, mortar_prepared=False):
    profile = _free_mix_class_effect_profile(class_ids, trait_counts)
    if not profile.get("helpful") or int(profile.get("hazardous", 0) or 0) > 0:
        return 0.0
    counts = trait_counts if isinstance(trait_counts, Mapping) else {}
    chance = 0.62
    chance += 0.10 * _safe_int(counts.get("stabilizer"), 0)
    chance += 0.05 * tuple(_key(value) for value in tuple(class_ids or ())).count("binding")
    chance += 0.06 * tuple(_key(value) for value in tuple(class_ids or ())).count("catalyst")
    chance -= 0.13 * _safe_int(counts.get("spoiler"), 0)
    chance -= 0.05 * sum(
        max(0, _safe_int(counts.get(negative), 0) - _safe_int(counts.get(positive), 0))
        for positive, negative in (
            ("+wake", "-wake"),
            ("+nourish", "-nourish"),
            ("+hydrate", "-hydrate"),
        )
    )
    if mortar_prepared:
        chance += 0.10
    return _clamp_float(chance, 0.15, 0.92)


def _experimental_recipe_for_mix(sim, eid, selected, class_ids, trait_counts=None, *, preparation=None):
    classes = tuple(_key(class_id) for class_id in tuple(class_ids or ()) if _key(class_id))
    rng = _experimental_mix_roll(sim, eid, selected, classes)
    preparation = preparation if isinstance(preparation, Mapping) else {}
    success_chance = herbal_free_mix_success_chance(
        classes,
        trait_counts,
        mortar_prepared=bool(preparation.get("mortar_prepared")),
    )
    effect_profile = _free_mix_class_effect_profile(classes, trait_counts)
    if success_chance > 0.0 and rng.random() < success_chance:
        return {
            "id": "improvised_mix",
            "name": str((effect_profile.get("metadata") or {}).get("display_name") or "improvised herbal blend").lower(),
            "output_item_id": IMPROVISED_HERBAL_BLEND_ITEM_ID,
            "component_count": len(tuple(selected or ())),
            "required_classes": classes,
            "service_fee": 0,
            "recipe_price": 0,
            "tags": ("experimental", "useful", "improvised"),
            "dynamic_effect_metadata": dict(effect_profile.get("metadata") or {}),
        }
    toxic = "toxic" in classes
    weak_toxic_chance = herbal_weak_toxic_chance_for_traits(trait_counts)
    output_item_id = WEAK_TOXIC_CONCOCTION_ITEM_ID if toxic and rng.random() < weak_toxic_chance else EXPERIMENTAL_CONCOCTION_ITEM_ID
    name = "weak toxic concoction" if output_item_id == WEAK_TOXIC_CONCOCTION_ITEM_ID else "odd herbal concoction"
    return {
        "id": "experimental_mix",
        "name": name,
        "output_item_id": output_item_id,
        "component_count": len(tuple(selected or ())),
        "required_classes": classes,
        "service_fee": 0,
        "recipe_price": 0,
        "tags": ("experimental", "toxin" if toxic else "odd"),
    }


def _craftable_recipe_order(sim, eid, *, mode="self", prop=None):
    recipes = load_herbal_recipe_catalog()
    known = known_recipes_for_actor(sim, eid)
    local_recipe_ids = (
        set(herbalist_local_recipe_ids(sim, prop, include_self_only=False))
        if _key(mode) == "herbalist" and isinstance(prop, Mapping)
        else None
    )
    return tuple(
        recipe
        for recipe_id, recipe in recipes.items()
        if recipe_id in known and (local_recipe_ids is None or recipe_id in local_recipe_ids)
    )


def first_craftable_herbal_recipe(sim, eid, ingredient_source=None, *, mode="self", prop=None):
    source = ingredient_source if ingredient_source is not None else _inventory_for(sim, eid)
    if not source:
        return None
    for recipe in _craftable_recipe_order(sim, eid, mode=mode, prop=prop):
        if not _recipe_allowed_for_mode(recipe, mode):
            continue
        if _auto_select_ingredients(sim, eid, recipe, source):
            return recipe
    return None


def craft_herbal_medicine(
    sim,
    eid,
    recipe_id=None,
    ingredient_instance_ids=None,
    *,
    mode="self",
    prop=None,
    emit_event=True,
    ingredient_entries=None,
    consume_ingredient_entry=None,
    restore_ingredient_entry=None,
    ingredient_source_kind="inventory",
):
    inventory = _inventory_for(sim, eid)
    if not inventory:
        return {"ok": False, "reason": "no_inventory"}
    mode = str(mode or "self").strip().lower()
    preparation = _herbal_preparation_profile(
        inventory,
        mode=mode,
        ingredient_source_kind=ingredient_source_kind,
    )
    ingredient_source = tuple(ingredient_entries or ()) if ingredient_entries is not None else inventory
    recipes = load_herbal_recipe_catalog()
    requested_recipe_id = _key(recipe_id)
    recipe = recipes.get(requested_recipe_id) if requested_recipe_id else None
    selected = None
    experiment_result = ""
    discovered_recipe = False
    diluted_target_recipe = None
    selected_trait_counts = {trait: 0 for trait in SECONDARY_TRAITS}

    if (
        recipe is not None
        and mode == "herbalist"
        and isinstance(prop, Mapping)
        and _recipe_allowed_for_mode(recipe, mode)
    ):
        if _key(recipe.get("id")) not in set(herbalist_local_recipe_ids(sim, prop, include_self_only=False)):
            return {"ok": False, "reason": "no_local_recipe", "recipe_id": recipe["id"]}

    if recipe is None and ingredient_instance_ids and mode == "self":
        if preparation is None:
            return {"ok": False, "reason": "no_tool", "tool_item_id": MORTAR_KIT_ITEM_ID}
        selected = _selected_ingredient_entries(ingredient_source, ingredient_instance_ids, min_count=2)
        if selected is None:
            return {"ok": False, "reason": "invalid_mix"}
        selected_classes = tuple(_entry_chemistry_class_for_actor(sim, eid, entry, require_known=False) for entry in selected)
        selected_trait_counts = _secondary_trait_counts_from_entries(sim, selected)
        for entry in selected:
            metadata = entry.get("metadata") if isinstance(entry.get("metadata"), Mapping) else {}
            if metadata.get("source_plant_id"):
                learn_plant_trait(sim, eid, metadata.get("source_plant_id"), source_kind="experiment")
        exact_recipe = _recipe_matching_classes(recipes, selected_classes)
        if exact_recipe is not None:
            if not _recipe_allowed_for_mode(exact_recipe, mode):
                return {"ok": False, "reason": "no_recipe", "recipe_id": exact_recipe["id"]}
            recipe = exact_recipe
            learned = learn_herbal_recipe(sim, eid, exact_recipe["id"], source_kind="experiment", reveal_plants=False)
            discovered_recipe = bool((learned or {}).get("was_new", False))
            experiment_result = "discovered_recipe" if discovered_recipe else "exact_recipe"
        else:
            near_recipe = _nearest_one_wrong_recipe(recipes, selected_classes)
            if near_recipe is not None and not _recipe_outputs_throwable(near_recipe):
                recipe = near_recipe
                diluted_target_recipe = near_recipe
                experiment_result = "diluted"
            else:
                recipe = _experimental_recipe_for_mix(
                    sim,
                    eid,
                    selected,
                    selected_classes,
                    selected_trait_counts,
                    preparation=preparation,
                )
                if recipe["output_item_id"] == IMPROVISED_HERBAL_BLEND_ITEM_ID:
                    experiment_result = "useful"
                elif recipe["output_item_id"] == WEAK_TOXIC_CONCOCTION_ITEM_ID:
                    experiment_result = "weak_toxic"
                else:
                    experiment_result = "odd"

    if recipe is None:
        recipe = first_craftable_herbal_recipe(sim, eid, ingredient_source, mode=mode, prop=prop)
    if recipe is None:
        if not known_recipes_for_actor(sim, eid):
            return {"ok": False, "reason": "no_recipe"}
        if mode == "herbalist" and isinstance(prop, Mapping):
            local_known = set(known_recipes_for_actor(sim, eid)).intersection(
                herbalist_local_recipe_ids(sim, prop, include_self_only=False)
            )
            if not local_known:
                return {"ok": False, "reason": "no_local_recipe"}
        return {"ok": False, "reason": "no_ingredients"}
    if not _recipe_allowed_for_mode(recipe, mode):
        return {"ok": False, "reason": "no_recipe", "recipe_id": recipe["id"]}
    if not experiment_result and _key(recipe["id"]) not in known_recipes_for_actor(sim, eid):
        return {"ok": False, "reason": "no_recipe", "recipe_id": recipe["id"]}
    if mode == "self" and preparation is None:
        return {"ok": False, "reason": "no_tool", "tool_item_id": MORTAR_KIT_ITEM_ID}

    if selected is not None:
        pass
    elif ingredient_instance_ids:
        selected = _validate_selected_ingredients(sim, eid, recipe, ingredient_source, ingredient_instance_ids)
        if selected is None:
            return {"ok": False, "reason": "invalid_mix", "recipe_id": recipe["id"]}
    else:
        selected = _auto_select_ingredients(sim, eid, recipe, ingredient_source)
        if not selected:
            return {"ok": False, "reason": "no_ingredients", "recipe_id": recipe["id"]}
    selected_trait_counts = _secondary_trait_counts_from_entries(sim, selected)

    fee = int(recipe.get("service_fee", 0) or 0) if mode == "herbalist" else 0
    assets = _assets_for(sim, eid)
    credits = int(getattr(assets, "credits", 0)) if assets else 0
    if fee > 0 and credits < fee:
        return {"ok": False, "reason": "no_credits", "cost": fee, "credits": credits, "recipe_id": recipe["id"]}

    base_output_item_id = recipe["output_item_id"]
    output_item_id = DILUTED_HERBAL_OUTPUTS.get(base_output_item_id, base_output_item_id) if diluted_target_recipe is not None else base_output_item_id
    component_payload = []
    for entry in selected:
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), Mapping) else {}
        plant_id = _key(metadata.get("source_plant_id"))
        secondary_traits = _entry_secondary_traits(sim, entry)
        component_payload.append({
            "item_id": entry.get("item_id"),
            "instance_id": entry.get("instance_id"),
            "plant_id": plant_id or metadata.get("source_plant_id"),
            "plant_name": metadata.get("source_plant_name"),
            "chemistry_class": metadata.get("chemistry_class"),
            "secondary_traits": list(secondary_traits),
            "material_units": _safe_int(metadata.get("material_units"), 1),
            "quality": metadata.get("quality"),
        })
    component_secondary_traits = tuple(
        dict.fromkeys(
            trait
            for row in component_payload
            for trait in tuple(row.get("secondary_traits", ()) or ())
            if _key(trait) in SECONDARY_TRAITS
        )
    )
    component_secondary_trait_counts = _secondary_trait_counts_from_payload(component_payload)
    owner_tag = "player" if eid == getattr(sim, "player_eid", None) else "npc"
    source_context = "crafted" if mode == "self" else "herbalist_prepared"
    output_metadata = {
        "source": "herbal_chemistry",
        "source_context": source_context,
        "recipe_id": recipe["id"],
        "crafted_tick": _safe_int(getattr(sim, "tick", 0), 0),
        "crafted_mode": mode,
        "ingredient_source": str(ingredient_source_kind or "inventory").strip().lower() or "inventory",
        "component_plants": [row.get("plant_id") for row in component_payload if row.get("plant_id")],
        "component_classes": [row.get("chemistry_class") for row in component_payload if row.get("chemistry_class")],
        "component_secondary_traits": list(component_secondary_traits),
        "component_secondary_trait_counts": dict(component_secondary_trait_counts),
        "item_quality": str((preparation or {}).get("item_quality", "standard") or "standard"),
        "preparation_method": str((preparation or {}).get("method", mode) or mode),
        "mortar_prepared": bool((preparation or {}).get("mortar_prepared", False)),
        "legal_status": str(ITEM_CATALOG.get(output_item_id, {}).get("legal_status", "legal") or "legal").strip().lower(),
    }
    if experiment_result:
        output_metadata["source_context"] = "herbal_experiment" if mode == "self" else "herbalist_experiment"
        output_metadata["experiment_result"] = experiment_result
        output_metadata["discovered_recipe"] = bool(discovered_recipe)
        output_metadata["component_classes"] = [row.get("chemistry_class") for row in component_payload if row.get("chemistry_class")]
        if diluted_target_recipe is not None:
            output_metadata["target_recipe_id"] = diluted_target_recipe["id"]
            output_metadata["target_recipe_name"] = diluted_target_recipe["name"]
            output_metadata["target_output_item_id"] = base_output_item_id
            output_metadata["legal_status"] = "suspicious"
    output_metadata.update(_herbal_trait_effect_metadata(
        sim,
        component_secondary_trait_counts,
        experiment_result=experiment_result,
        mode=mode,
        output_item_id=output_item_id,
        preparation=preparation,
    ))
    dynamic_effect_metadata = recipe.get("dynamic_effect_metadata") if isinstance(recipe.get("dynamic_effect_metadata"), Mapping) else {}
    additive_effect_keys = {
        "herbal_hp_delta",
        "herbal_wakefulness_delta",
        "herbal_hunger_delta",
        "herbal_thirst_delta",
        "item_extra_energy_delta",
        "item_extra_safety_delta",
        "item_extra_social_delta",
    }
    for key, value in dynamic_effect_metadata.items():
        if key in additive_effect_keys:
            output_metadata[key] = _safe_float(output_metadata.get(key), 0.0) + _safe_float(value, 0.0)
        else:
            output_metadata[key] = copy.deepcopy(value)
    source_context = str(output_metadata.get("source_context", source_context) or source_context)
    output_metadata = stamp_item_provenance(
        sim,
        {
            "item_id": output_item_id,
            "owner_eid": eid,
            "owner_tag": owner_tag,
            "metadata": output_metadata,
        },
        source_context=source_context,
        claim_class=CLAIM_PRIVATE_EFFECT,
        source_owner_eid=eid,
        source_owner_tag=owner_tag,
        source_actor_eid=eid,
        latent_claim_violation=False,
        last_transfer_tick=_safe_int(getattr(sim, "tick", 0), 0),
        last_transfer_kind=source_context,
        last_holder_eid=eid,
    )
    output_stack_max = (
        1
        if diluted_target_recipe is not None or output_metadata.get("breakdown_tick")
        else max(1, int(ITEM_CATALOG.get(output_item_id, {}).get("stack_max", 1) or 1))
    )
    if not _inventory_can_accept(
        inventory,
        output_item_id,
        1,
        metadata=output_metadata,
        owner_eid=eid,
        owner_tag=owner_tag,
        stack_max=output_stack_max,
    ):
        return {"ok": False, "reason": "inventory_full", "output_item_id": output_item_id, "quantity": 1}

    if fee > 0 and assets:
        assets.credits = max(0, int(assets.credits) - fee)
    removed = []
    for entry in selected:
        if callable(consume_ingredient_entry):
            removed_entry = consume_ingredient_entry(entry)
        else:
            removed_entry = inventory.remove_item(instance_id=entry.get("instance_id"), quantity=1)
        if removed_entry:
            removed.append(removed_entry)
    added, instance_id = _add_inventory_item(
        sim,
        inventory,
        output_item_id,
        1,
        metadata=output_metadata,
        owner_eid=eid,
        owner_tag=owner_tag,
        stack_max=output_stack_max,
    )
    if not added:
        for entry in removed:
            if callable(restore_ingredient_entry):
                restore_ingredient_entry(entry)
            else:
                metadata = entry.get("metadata") if isinstance(entry.get("metadata"), Mapping) else {}
                _add_inventory_item(sim, inventory, entry.get("item_id"), entry.get("quantity", 1), metadata=metadata, owner_eid=entry.get("owner_eid"), owner_tag=entry.get("owner_tag"))
        return {"ok": False, "reason": "inventory_full", "output_item_id": output_item_id, "quantity": 1}

    _note_herbal_decay_deadline(sim, output_metadata.get("breakdown_tick"))
    output_entry = inventory.find(instance_id=instance_id)
    if not experiment_result or experiment_result in {"discovered_recipe", "exact_recipe"}:
        identify_item_for_actor(sim, eid, output_entry or {"item_id": output_item_id, "metadata": output_metadata}, source_kind="crafted", item_catalog=ITEM_CATALOG)
    result = {
        "ok": True,
        "recipe_id": recipe["id"],
        "recipe_name": recipe["name"],
        "output_item_id": output_item_id,
        "output_item_name": item_display_name(output_item_id, metadata=output_metadata, item_catalog=ITEM_CATALOG),
        "output_instance_id": instance_id,
        "ingredient_count": len(selected),
        "ingredient_names": tuple(item_display_name_for_actor(sim, eid, entry, item_catalog=ITEM_CATALOG) for entry in selected),
        "component_plants": tuple(row.get("plant_name") or row.get("plant_id") for row in component_payload),
        "component_secondary_traits": component_secondary_traits,
        "trait_effects_applied": dict(output_metadata.get("trait_effects_applied") or {}),
        "stability_score": output_metadata.get("stability_score"),
        "stability_band": output_metadata.get("stability_band"),
        "breakdown_tick": output_metadata.get("breakdown_tick"),
        "herbal_result_read": output_metadata.get("herbal_result_read"),
        "item_quality": output_metadata.get("item_quality"),
        "preparation_method": output_metadata.get("preparation_method"),
        "mortar_prepared": bool(output_metadata.get("mortar_prepared", False)),
        "credits_spent": fee,
        "mode": mode,
        "ingredient_source": str(ingredient_source_kind or "inventory").strip().lower() or "inventory",
    }
    if experiment_result:
        result["experiment_result"] = experiment_result
        result["discovered_recipe"] = bool(discovered_recipe)
        if diluted_target_recipe is not None:
            result["target_recipe_id"] = diluted_target_recipe["id"]
    if emit_event:
        sim.emit(Event("herbal_medicine_crafted", eid=eid, **result))
    return result


def _entry_breakdown_tick(entry):
    metadata = entry.get("metadata") if isinstance(entry, Mapping) else {}
    if not isinstance(metadata, Mapping):
        return None
    breakdown_tick = metadata.get("breakdown_tick")
    if breakdown_tick is None:
        return None
    try:
        return int(breakdown_tick)
    except (TypeError, ValueError):
        return None


def _note_herbal_decay_deadline(sim, breakdown_tick):
    """Move the next authoritative decay scan earlier when new chemistry warrants it."""

    if sim is None or breakdown_tick is None:
        return None
    try:
        breakdown_tick = int(breakdown_tick)
    except (TypeError, ValueError):
        return None
    current = getattr(sim, "_herbal_decay_next_tick", None)
    try:
        current = int(current) if current is not None else None
    except (TypeError, ValueError):
        current = None
    if current is None or breakdown_tick < current:
        sim._herbal_decay_next_tick = breakdown_tick
    return int(sim._herbal_decay_next_tick)


def decay_herbal_mixture_entry_if_due(
    sim,
    entry,
    *,
    holder_kind="",
    holder_eid=None,
    property_id=None,
    container_kind=None,
    ground_item_id=None,
    x=None,
    y=None,
    z=None,
    emit_event=True,
):
    if not isinstance(entry, dict):
        return False
    old_item_id = _key(entry.get("item_id"))
    if not old_item_id or old_item_id == SPOILED_HERBAL_SLURRY_ITEM_ID:
        return False
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), Mapping) else {}
    if not isinstance(metadata, Mapping):
        metadata = {}
    breakdown_tick = _entry_breakdown_tick(entry)
    if breakdown_tick is None:
        return False
    if _safe_int(getattr(sim, "tick", 0), 0) < int(breakdown_tick):
        return False
    if not bool(metadata.get("herbal_decay")) and _key(metadata.get("source")) != "herbal_chemistry":
        return False

    old_name = item_display_name(old_item_id, metadata=metadata, item_catalog=ITEM_CATALOG)
    updated = dict(metadata)
    for key in HERBAL_DECAY_METADATA_KEYS:
        updated.pop(key, None)
    updated.pop("display_name", None)
    updated.update({
        "source": "herbal_chemistry",
        "source_context": "herbal_breakdown",
        "legal_status": "suspicious",
        "decayed_from_item_id": old_item_id,
        "decayed_from_item_name": old_name,
        "decayed_from_recipe_id": metadata.get("recipe_id"),
        "decayed_tick": _safe_int(getattr(sim, "tick", 0), 0),
        "decay_holder_kind": str(holder_kind or "").strip().lower() or "unknown",
    })
    quantity = 1
    entry["item_id"] = SPOILED_HERBAL_SLURRY_ITEM_ID
    entry["quantity"] = quantity
    entry["metadata"] = prepare_item_stack_metadata(
        SPOILED_HERBAL_SLURRY_ITEM_ID,
        metadata=updated,
        quantity=quantity,
        item_catalog=ITEM_CATALOG,
    )
    if emit_event:
        sim.emit(Event(
            "herbal_mixture_decayed",
            item_id=SPOILED_HERBAL_SLURRY_ITEM_ID,
            item_name=item_display_name(SPOILED_HERBAL_SLURRY_ITEM_ID, metadata=entry.get("metadata"), item_catalog=ITEM_CATALOG),
            old_item_id=old_item_id,
            old_item_name=old_name,
            instance_id=entry.get("instance_id"),
            holder_kind=str(holder_kind or "").strip().lower() or "unknown",
            holder_eid=holder_eid,
            property_id=property_id,
            container_kind=container_kind,
            ground_item_id=ground_item_id,
            x=x if x is not None else entry.get("x"),
            y=y if y is not None else entry.get("y"),
            z=z if z is not None else entry.get("z"),
            breakdown_tick=breakdown_tick,
            decayed_tick=_safe_int(getattr(sim, "tick", 0), 0),
        ))
    return True


class HerbalMixtureDecaySystem(System):
    """Transforms expired loaded herbal mixtures without materializing chunks."""

    def __init__(self, sim, *, scan_interval_ticks=1):
        super().__init__(sim)
        self.scan_interval_ticks = max(1, int(scan_interval_ticks or 1))
        self._needs_full_scan = True

    def _review_entry(self, entry, **location):
        breakdown_tick = _entry_breakdown_tick(entry)
        if breakdown_tick is None:
            return False
        tick = _safe_int(getattr(self.sim, "tick", 0), 0)
        if int(breakdown_tick) > tick:
            _note_herbal_decay_deadline(self.sim, breakdown_tick)
            return False
        return decay_herbal_mixture_entry_if_due(self.sim, entry, **location)

    def _scan_inventory_entries(self):
        inventories = self.sim.ecs.get(Inventory)
        for eid, inventory in tuple(inventories.items()):
            for entry in tuple(getattr(inventory, "items", ()) or ()):
                self._review_entry(
                    entry,
                    holder_kind="inventory",
                    holder_eid=eid,
                )

    def _scan_ground_entries(self):
        ground_items = getattr(self.sim, "ground_items", None)
        if not isinstance(ground_items, dict):
            return
        for ground_item_id, entry in tuple(ground_items.items()):
            if not isinstance(entry, dict):
                continue
            self._review_entry(
                entry,
                holder_kind="ground",
                ground_item_id=ground_item_id,
                x=entry.get("x"),
                y=entry.get("y"),
                z=entry.get("z"),
            )

    def _scan_container_entries(self):
        cache_inventories = getattr(self.sim, "cache_inventories", None)
        if isinstance(cache_inventories, dict):
            for property_id, entries in tuple(cache_inventories.items()):
                for entry in tuple(entries or ()):
                    self._review_entry(
                        entry,
                        holder_kind="container",
                        property_id=property_id,
                        container_kind="cache",
                    )
        inventories_by_kind = getattr(self.sim, "container_inventories", None)
        if not isinstance(inventories_by_kind, dict):
            return
        for container_kind, inventories in tuple(inventories_by_kind.items()):
            if not isinstance(inventories, dict):
                continue
            for property_id, entries in tuple(inventories.items()):
                for entry in tuple(entries or ()):
                    self._review_entry(
                        entry,
                        holder_kind="container",
                        property_id=property_id,
                        container_kind=container_kind,
                    )

    def update(self):
        tick = _safe_int(getattr(self.sim, "tick", 0), 0)
        next_tick = getattr(self.sim, "_herbal_decay_next_tick", None)
        try:
            next_tick = int(next_tick) if next_tick is not None else None
        except (TypeError, ValueError):
            next_tick = None
        if not self._needs_full_scan and (next_tick is None or tick < next_tick):
            return
        self._needs_full_scan = False
        self.sim._herbal_decay_next_tick = None
        self._scan_inventory_entries()
        self._scan_ground_entries()
        self._scan_container_entries()


def _remove_container_ingredient_entry(container_entries, selected_entry):
    instance_id = str((selected_entry or {}).get("instance_id", "") or "").strip()
    if not instance_id:
        return None
    for index, entry in enumerate(list(container_entries or ())):
        if str((entry or {}).get("instance_id", "") or "").strip() != instance_id:
            continue
        quantity = max(1, _safe_int(entry.get("quantity"), 1))
        removed = dict(entry)
        removed["quantity"] = 1
        if quantity <= 1:
            container_entries.pop(index)
        else:
            entry["quantity"] = quantity - 1
        return removed
    return None


def craft_herbal_medicine_from_container(
    sim,
    eid,
    prop,
    *,
    recipe_id=None,
    freeform=False,
    mode="self",
    container_kind=CAMPFIRE_HERB_CACHE_KIND,
    emit_event=True,
):
    property_id = str((prop or {}).get("id", "") or "").strip()
    if not property_id:
        return {"ok": False, "reason": "unavailable"}
    container_entries = property_runtime_container_entries(sim, property_id, container_kind=container_kind)
    ingredient_rows = tuple(_ingredient_entries(container_entries))
    if bool(freeform):
        if len(ingredient_rows) < 2:
            return {"ok": False, "reason": "no_ingredients"}
        if len(ingredient_rows) > 3:
            return {"ok": False, "reason": "invalid_mix"}
        ingredient_instance_ids = tuple(str(entry.get("instance_id", "") or "") for entry in ingredient_rows)
    else:
        ingredient_instance_ids = None

    def _consume(entry):
        return _remove_container_ingredient_entry(container_entries, entry)

    def _restore(entry):
        if isinstance(entry, Mapping):
            container_entries.append(dict(entry))

    result = craft_herbal_medicine(
        sim,
        eid,
        recipe_id=recipe_id,
        ingredient_instance_ids=ingredient_instance_ids,
        mode=mode,
        prop=prop,
        emit_event=emit_event,
        ingredient_entries=tuple(container_entries),
        consume_ingredient_entry=_consume,
        restore_ingredient_entry=_restore,
        ingredient_source_kind=container_kind,
    )
    if isinstance(result, dict):
        if not result.get("ok"):
            result.setdefault("ingredient_count", len(ingredient_rows))
            if (
                not bool(freeform)
                and str(result.get("reason", "") or "").strip().lower() == "no_ingredients"
                and 2 <= len(ingredient_rows) <= 3
            ):
                result["reason"] = "no_matching_recipe"
        result["ingredient_source"] = container_kind
    return result


def purchase_herbal_recipe(sim, eid, recipe_id=None, *, prop=None, emit_event=True):
    recipes = load_herbal_recipe_catalog()
    known = known_recipes_for_actor(sim, eid)
    recipe = recipes.get(_key(recipe_id)) if recipe_id else None
    if recipe is not None and not _recipe_available_for_sale(recipe):
        return {"ok": False, "reason": "all_known"}
    local_recipe_ids = (
        set(herbalist_local_recipe_ids(sim, prop, include_self_only=False))
        if isinstance(prop, Mapping)
        else {
            candidate_id
            for candidate_id, candidate in recipes.items()
            if _recipe_available_for_sale(candidate)
        }
    )
    if recipe is not None and _key(recipe.get("id")) not in local_recipe_ids:
        return {"ok": False, "reason": "no_local_recipe", "recipe_id": recipe["id"]}
    if recipe is None:
        candidates = [
            (index, candidate)
            for index, (candidate_id, candidate) in enumerate(recipes.items())
            if candidate_id not in known
            and candidate_id in local_recipe_ids
            and _recipe_available_for_sale(candidate)
        ]
        if candidates:
            index, recipe = max(
                candidates,
                key=lambda row: (
                    _recipe_local_affinity_score(sim, eid, row[1]),
                    -int(row[0]),
                ),
            )
    if recipe is None and not local_recipe_ids:
        return {"ok": False, "reason": "no_local_recipe"}
    if recipe is None:
        return {"ok": False, "reason": "all_known"}
    assets = _assets_for(sim, eid)
    credits = int(getattr(assets, "credits", 0)) if assets else 0
    cost = int(recipe.get("recipe_price", 1) or 1)
    if credits < cost:
        return {"ok": False, "reason": "no_credits", "cost": cost, "credits": credits, "recipe_id": recipe["id"]}
    if assets:
        assets.credits = max(0, int(assets.credits) - cost)
    learned = learn_herbal_recipe(sim, eid, recipe["id"], source_kind="recipe_sale", reveal_plants=True, prop=prop) or {}
    result = {
        "ok": True,
        "recipe_id": recipe["id"],
        "recipe_name": recipe["name"],
        "output_item_id": recipe["output_item_id"],
        "output_item_name": item_display_name(recipe["output_item_id"], item_catalog=ITEM_CATALOG),
        "credits_spent": cost,
        "revealed_plants": tuple(learned.get("revealed_plants", ()) or ()),
        "was_new": bool(learned.get("was_new", True)),
    }
    if emit_event:
        sim.emit(Event("herbal_recipe_purchased", eid=eid, **result))
    return result
