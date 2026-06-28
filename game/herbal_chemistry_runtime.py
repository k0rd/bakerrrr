"""Small-batch herbal chemistry, harvesting, and recipe helpers."""

from __future__ import annotations

import copy
import json
import random
from functools import lru_cache
from pathlib import Path
from typing import Mapping

from engine.events import Event
from engine.visibility import has_line_of_sight

from game.components import Inventory, PlayerAssets, Position
from game.flora_runtime import (
    flora_harvest_context,
    flora_harvest_remaining,
    flora_harvest_updates_after_pick,
    flora_patch_harvestable,
    flora_records_in_rect,
    load_flora_catalog,
    normalize_flora_harvest_state,
)
from game.item_semantics import identify_item_for_actor, item_display_name_for_actor
from game.items import ITEM_CATALOG, item_display_name
from game.json_metadata import split_object_document
from game.system_support.interaction_ordering import _manhattan


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
)

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


def _inventory_can_accept(inventory, item_id, quantity=1, *, metadata=None, owner_eid=None, owner_tag=None):
    if not inventory:
        return False
    item_def = ITEM_CATALOG.get(str(item_id or "").strip().lower(), {})
    clone = _clone_inventory(inventory)
    added, _instance_id = clone.add_item(
        item_id,
        quantity=max(1, int(quantity)),
        stack_max=max(1, int(item_def.get("stack_max", 1) or 1)),
        owner_eid=owner_eid,
        owner_tag=owner_tag,
        metadata=metadata or {},
    )
    return bool(added)


def _add_inventory_item(sim, inventory, item_id, quantity=1, *, metadata=None, owner_eid=None, owner_tag=None):
    item_def = ITEM_CATALOG.get(str(item_id or "").strip().lower(), {})
    return inventory.add_item(
        item_id,
        quantity=max(1, int(quantity)),
        stack_max=max(1, int(item_def.get("stack_max", 1) or 1)),
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
        }
    return rows


def ensure_herbal_state(sim):
    if not isinstance(getattr(sim, "herbal_known_plant_traits", None), dict):
        sim.herbal_known_plant_traits = {}
    if not isinstance(getattr(sim, "herbal_known_recipes", None), dict):
        sim.herbal_known_recipes = {}
    return sim.herbal_known_plant_traits, sim.herbal_known_recipes


def _plant_bias_weights(row):
    text_bits = []
    for key in ("id", "name", "growth_form", "rarity"):
        text_bits.append(str(row.get(key, "")))
    for key in ("tags", "crossbreed_tags"):
        text_bits.extend(str(token) for token in row.get(key, ()) or ())
    for key in ("growth_traits", "genetics", "harvest_potential", "spread_profile"):
        data = row.get(key)
        if isinstance(data, Mapping):
            text_bits.extend(str(k) for k in data.keys())
            text_bits.extend(str(v) for v in data.values())
    text = " ".join(text_bits).strip().lower()
    weights = {}
    for class_id in CHEMISTRY_CLASSES:
        weights[class_id] = 1.0 + sum(1.65 for term in _BIAS_TERMS[class_id] if term in text)
    form = str(row.get("growth_form", "") or "").strip().lower()
    if form in {"vine", "reed"}:
        weights["binding"] += 1.7
    if form in {"moss", "lichen"}:
        weights["catalyst"] += 1.4
        weights["cleansing"] += 0.8
    if str(row.get("rarity", "")).strip().lower() == "rare":
        weights["catalyst"] += 1.2
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


def herbal_chemistry_profiles(sim):
    state = getattr(sim, "herbal_chemistry_profiles", None)
    seed = int(getattr(sim, "seed", 0) or 0)
    catalog = load_flora_catalog()
    catalog_marker = ",".join(sorted(catalog.keys()))
    if isinstance(state, dict) and state.get("seed") == seed and state.get("catalog_marker") == catalog_marker:
        return dict(state.get("plants", {}) or {})

    rng = random.Random(f"{seed}:herbal-chemistry:v1")
    plant_ids = sorted(catalog.keys())
    rng.shuffle(plant_ids)
    assignments = {}
    for plant_id in plant_ids:
        row = catalog[plant_id]
        weights = _plant_bias_weights(row)
        assignments[plant_id] = _weighted_choice(rng, tuple(weights.items())) or "mending"

    target_count = 3 if len(plant_ids) >= len(CHEMISTRY_CLASSES) * 3 else 1
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

    sim.herbal_chemistry_profiles = {
        "seed": seed,
        "catalog_marker": catalog_marker,
        "plants": dict(assignments),
    }
    return dict(assignments)


def plant_chemistry_class(sim, plant_id):
    plant_id = _key(plant_id)
    return str(herbal_chemistry_profiles(sim).get(plant_id, "") or "").strip().lower()


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
    rows[plant_id] = {
        "chemistry_class": class_id,
        "learned_tick": _safe_int(getattr(sim, "tick", 0), 0),
        "source_kind": str(source_kind or "recipe").strip().lower() or "recipe",
    }
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
        revealed = tuple(_reveal_recipe_plants(sim, eid, recipes[recipe_id], prop=prop, limit=2))
    return {"recipe": recipes[recipe_id], "was_new": was_new, "revealed_plants": revealed}


def _plants_near_actor(sim, eid, radius=12):
    pos = sim.ecs.get(Position).get(eid)
    if pos is None:
        return ()
    rows = flora_records_in_rect(sim, int(pos.x) - radius, int(pos.y) - radius, int(pos.x) + radius, int(pos.y) + radius, z=int(pos.z))
    return tuple(row for row in rows if isinstance(row, dict))


def _reveal_recipe_plants(sim, eid, recipe, *, prop=None, limit=2):
    required = set(recipe.get("required_classes", ()) or ())
    if not required:
        return ()
    catalog = load_flora_catalog()
    assignments = herbal_chemistry_profiles(sim)
    nearby = []
    for row in _plants_near_actor(sim, eid):
        plant_id = _key(row.get("plant_id"))
        if plant_id and assignments.get(plant_id) in required:
            nearby.append(plant_id)
    fallback = [plant_id for plant_id in sorted(catalog) if assignments.get(plant_id) in required]
    seed_bits = [getattr(sim, "seed", 0), getattr(sim, "tick", 0), eid, recipe.get("id")]
    if isinstance(prop, Mapping):
        seed_bits.append(prop.get("id") or prop.get("name"))
    rng = random.Random(":".join(str(bit) for bit in seed_bits))
    ordered = list(dict.fromkeys(nearby + fallback))
    rng.shuffle(ordered)
    revealed = []
    for plant_id in ordered:
        if len(revealed) >= max(1, int(limit)):
            break
        if learn_plant_trait(sim, eid, plant_id, source_kind="recipe_sale"):
            revealed.append({
                "plant_id": plant_id,
                "plant_name": catalog.get(plant_id, {}).get("name", plant_id.replace("_", " ")),
                "chemistry_class": assignments.get(plant_id),
            })
    return tuple(revealed)


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


def nearest_harvestable_flora(sim, x, y, z=0, *, radius=1, preferred_dir=None, exact_direction=False):
    target = None
    if exact_direction and isinstance(preferred_dir, tuple) and len(preferred_dir) >= 2:
        dx = _safe_int(preferred_dir[0], 0)
        dy = _safe_int(preferred_dir[1], 0)
        if dx or dy:
            target = (int(x) + dx, int(y) + dy, int(z))
    rows = []
    for record in getattr(sim, "flora_patches", {}).values() if isinstance(getattr(sim, "flora_patches", None), dict) else ():
        if not isinstance(record, dict) or not flora_patch_harvestable(record):
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
        "harvest_method": method,
        "plant_part": str(harvest_context.get("plant_part") or "").strip().lower(),
        "bloom_state": str(harvest_context.get("bloom_state") or "").strip().lower(),
        "day_phase": str(harvest_context.get("day_phase") or "").strip().lower(),
        "harvest_hour": int(harvest_context.get("harvest_hour", 0) or 0),
        "material_units": int(units),
        "quality": quality,
        "quality_hint": str(harvest_context.get("quality_hint") or "").strip().lower(),
        "harvested_tick": _safe_int(getattr(sim, "tick", 0), 0),
        "legal_status": "legal",
    }
    metadata["display_name"] = herbal_ingredient_display_name(item_id, metadata["source_plant_name"])
    if tool.get("item_id"):
        metadata["tool_item_id"] = tool.get("item_id")
    owner_tag = "player" if eid == getattr(sim, "player_eid", None) else "npc"
    if not _inventory_can_accept(inventory, item_id, 1, metadata=metadata, owner_eid=eid, owner_tag=owner_tag):
        sim.emit(Event(
            "flora_harvest_blocked",
            eid=eid,
            flora_id=record.get("id"),
            plant_name=record.get("name"),
            output_item_id=item_id,
            reason="inventory_full",
        ))
        return False
    added, instance_id = _add_inventory_item(sim, inventory, item_id, 1, metadata=metadata, owner_eid=eid, owner_tag=owner_tag)
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


def _ingredient_entries(inventory):
    if not inventory:
        return ()
    rows = []
    for entry in tuple(inventory.items or ()):
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
    wanted = [str(value or "").strip() for value in tuple(instance_ids or ()) if str(value or "").strip()]
    if len(wanted) != len(set(wanted)) or len(wanted) < int(recipe.get("component_count", 2)):
        return None
    by_id = {
        str(entry.get("instance_id", "") or ""): entry
        for entry in _ingredient_entries(inventory)
    }
    selected = []
    for instance_id in wanted[: int(recipe.get("component_count", 2))]:
        entry = by_id.get(instance_id)
        if entry is None:
            return None
        selected.append(entry)
    required = list(recipe.get("required_classes", ()) or ())
    classes = [_entry_chemistry_class_for_actor(sim, eid, entry, require_known=False) for entry in selected]
    for entry in selected:
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), Mapping) else {}
        if metadata.get("source_plant_id"):
            learn_plant_trait(sim, eid, metadata.get("source_plant_id"), source_kind="experiment")
    if sorted(classes) != sorted(required):
        return None
    return tuple(selected)


def _craftable_recipe_order(sim, eid):
    recipes = load_herbal_recipe_catalog()
    known = known_recipes_for_actor(sim, eid)
    return tuple(recipe for recipe_id, recipe in recipes.items() if recipe_id in known)


def first_craftable_herbal_recipe(sim, eid):
    inventory = _inventory_for(sim, eid)
    if not inventory:
        return None
    for recipe in _craftable_recipe_order(sim, eid):
        if _auto_select_ingredients(sim, eid, recipe, inventory):
            return recipe
    return None


def craft_herbal_medicine(sim, eid, recipe_id=None, ingredient_instance_ids=None, *, mode="self", prop=None, emit_event=True):
    inventory = _inventory_for(sim, eid)
    if not inventory:
        return {"ok": False, "reason": "no_inventory"}
    mode = str(mode or "self").strip().lower()
    recipes = load_herbal_recipe_catalog()
    recipe = recipes.get(_key(recipe_id)) if recipe_id else None
    if recipe is None:
        recipe = first_craftable_herbal_recipe(sim, eid)
    if recipe is None:
        if not known_recipes_for_actor(sim, eid):
            return {"ok": False, "reason": "no_recipe"}
        return {"ok": False, "reason": "no_ingredients"}
    if _key(recipe["id"]) not in known_recipes_for_actor(sim, eid):
        return {"ok": False, "reason": "no_recipe", "recipe_id": recipe["id"]}
    if mode == "self" and not _has_item(inventory, MORTAR_KIT_ITEM_ID):
        return {"ok": False, "reason": "no_tool", "tool_item_id": MORTAR_KIT_ITEM_ID}

    if ingredient_instance_ids:
        selected = _validate_selected_ingredients(sim, eid, recipe, inventory, ingredient_instance_ids)
        if selected is None:
            return {"ok": False, "reason": "invalid_mix", "recipe_id": recipe["id"]}
    else:
        selected = _auto_select_ingredients(sim, eid, recipe, inventory)
        if not selected:
            return {"ok": False, "reason": "no_ingredients", "recipe_id": recipe["id"]}

    fee = int(recipe.get("service_fee", 0) or 0) if mode == "herbalist" else 0
    assets = _assets_for(sim, eid)
    credits = int(getattr(assets, "credits", 0)) if assets else 0
    if fee > 0 and credits < fee:
        return {"ok": False, "reason": "no_credits", "cost": fee, "credits": credits, "recipe_id": recipe["id"]}

    output_item_id = recipe["output_item_id"]
    component_payload = []
    for entry in selected:
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), Mapping) else {}
        component_payload.append({
            "item_id": entry.get("item_id"),
            "instance_id": entry.get("instance_id"),
            "plant_id": metadata.get("source_plant_id"),
            "plant_name": metadata.get("source_plant_name"),
            "chemistry_class": metadata.get("chemistry_class"),
            "material_units": _safe_int(metadata.get("material_units"), 1),
            "quality": metadata.get("quality"),
        })
    output_metadata = {
        "source": "herbal_chemistry",
        "source_context": "crafted" if mode == "self" else "herbalist_prepared",
        "recipe_id": recipe["id"],
        "crafted_tick": _safe_int(getattr(sim, "tick", 0), 0),
        "crafted_mode": mode,
        "component_plants": [row.get("plant_id") for row in component_payload if row.get("plant_id")],
        "component_classes": [row.get("chemistry_class") for row in component_payload if row.get("chemistry_class")],
        "legal_status": "legal",
    }
    owner_tag = "player" if eid == getattr(sim, "player_eid", None) else "npc"
    if not _inventory_can_accept(inventory, output_item_id, 1, metadata=output_metadata, owner_eid=eid, owner_tag=owner_tag):
        return {"ok": False, "reason": "inventory_full", "output_item_id": output_item_id, "quantity": 1}

    if fee > 0 and assets:
        assets.credits = max(0, int(assets.credits) - fee)
    removed = []
    for entry in selected:
        removed_entry = inventory.remove_item(instance_id=entry.get("instance_id"), quantity=1)
        if removed_entry:
            removed.append(removed_entry)
    added, instance_id = _add_inventory_item(sim, inventory, output_item_id, 1, metadata=output_metadata, owner_eid=eid, owner_tag=owner_tag)
    if not added:
        for entry in removed:
            metadata = entry.get("metadata") if isinstance(entry.get("metadata"), Mapping) else {}
            _add_inventory_item(sim, inventory, entry.get("item_id"), entry.get("quantity", 1), metadata=metadata, owner_eid=entry.get("owner_eid"), owner_tag=entry.get("owner_tag"))
        return {"ok": False, "reason": "inventory_full", "output_item_id": output_item_id, "quantity": 1}

    output_entry = inventory.find(instance_id=instance_id)
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
        "credits_spent": fee,
        "mode": mode,
    }
    if emit_event:
        sim.emit(Event("herbal_medicine_crafted", eid=eid, **result))
    return result


def purchase_herbal_recipe(sim, eid, recipe_id=None, *, prop=None, emit_event=True):
    recipes = load_herbal_recipe_catalog()
    known = known_recipes_for_actor(sim, eid)
    recipe = recipes.get(_key(recipe_id)) if recipe_id else None
    if recipe is None:
        for candidate_id, candidate in recipes.items():
            if candidate_id not in known:
                recipe = candidate
                break
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
