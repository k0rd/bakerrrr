"""Shared crafting and runtime behavior for physical field devices.

The canonical state is deliberately ordinary: crafted devices are inventory
items and deployed devices are properties.  The runtime index below is only a
rebuildable view over those properties, so save/load and chunk streaming do not
need a second device world.
"""

from __future__ import annotations

import copy
import json
import random
from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path

from engine.events import Event
from engine.systems import System
from engine.visibility import has_line_of_sight

from game.components import AI, CreatureIdentity, DroneState, Inventory, NPCMemory, NPCNeeds, Position, StatusEffects
from game.drone_recon import drone_sensor_modes
from game.drone_runtime import drone_sensor_suppression_status
from game.items import (
    ITEM_CATALOG,
    apply_item_durability_loss,
    item_condition_profile,
    item_display_name,
    item_instance_condition,
)
from game.skills import actor_skill
from game.property_access import evaluate_property_access
from game.property_runtime import property_covering
from game.system_support.awareness_runtime import observation_payload_for_position
from game.system_support.player_feedback import _log_player_feedback


MECHANICAL_RECIPES_PATH = Path(__file__).resolve().parent / "mechanical_recipes.json"
MECHANICAL_DEVICE_MEMORY_KIND = "placed_mechanical_device"
MECHANICAL_DEVICE_FIXTURE_TYPE = "mechanical_field_device"
MECHANICAL_PLAN_TAG = "mechanical_plan"
MECHANICAL_DEVICE_TAG = "mechanical_device"
MECHANICAL_TOOL_IDS = ("pocket_multitool", "prybar")
REMOTE_PAYLOAD_TAGS = frozenset({"aerosol", "smoke", "incendiary"})


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _key(value):
    return str(value or "").strip().lower()


def _coord(x, y, z=0):
    return (_int(x), _int(y), _int(z))


def _tags(item_def):
    return {
        _key(tag)
        for tag in tuple((item_def or {}).get("tags", ()) or ())
        if _key(tag)
    }


def _entity_name(sim, eid, default="someone"):
    identity = sim.ecs.get(CreatureIdentity).get(eid) if sim is not None and eid is not None else None
    return identity.display_name() if identity is not None else default


@lru_cache(maxsize=4)
def load_mechanical_recipe_catalog(path=MECHANICAL_RECIPES_PATH):
    try:
        raw = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(raw, dict):
        return {}
    recipes = {}
    for recipe_id, row in raw.items():
        if not isinstance(row, dict):
            continue
        recipe_id = _key(recipe_id)
        plan_item_id = _key(row.get("plan_item_id"))
        output_item_id = _key(row.get("output_item_id"))
        raw_components = row.get("components") if isinstance(row.get("components"), dict) else {}
        components = {
            _key(item_id): max(1, _int(quantity, 1))
            for item_id, quantity in raw_components.items()
            if _key(item_id)
        }
        component_choices = []
        raw_choices = row.get("component_choices") if isinstance(row.get("component_choices"), list) else ()
        for choice_index, raw_choice in enumerate(raw_choices):
            if not isinstance(raw_choice, dict):
                continue
            raw_options = raw_choice.get("options") if isinstance(raw_choice.get("options"), dict) else {}
            options = {
                _key(item_id): max(1, _int(quantity, 1))
                for item_id, quantity in raw_options.items()
                if _key(item_id)
            }
            if not options:
                continue
            component_choices.append({
                "id": _key(raw_choice.get("id")) or f"choice_{choice_index + 1}",
                "options": options,
            })
        profile = dict(row.get("device_profile") or {}) if isinstance(row.get("device_profile"), dict) else {}
        if not recipe_id or not plan_item_id or not output_item_id or (not components and not component_choices) or not profile:
            continue
        recipes[recipe_id] = {
            "id": recipe_id,
            "name": str(row.get("name") or recipe_id.replace("_", " ").title()).strip(),
            "plan_item_id": plan_item_id,
            "output_item_id": output_item_id,
            "components": components,
            "component_choices": tuple(component_choices),
            "difficulty": max(1.0, min(12.0, _float(row.get("difficulty"), 5.0))),
            "construction_ticks": max(1, _int(row.get("construction_ticks"), 2)),
            "field_craftable": bool(row.get("field_craftable", False)),
            "device_profile": normalize_device_profile(profile),
        }
    return recipes


def normalize_device_profile(value):
    raw = value if isinstance(value, Mapping) else {}
    profile = {
        "body": _key(raw.get("body")) or "floor_fixture",
        "trigger": _key(raw.get("trigger")) or "step",
        "payload": _key(raw.get("payload")) or "alarm",
        "glyph": str(raw.get("glyph", "^") or "^")[:1] or "^",
        "color": str(raw.get("color", "item_restricted") or "item_restricted").strip() or "item_restricted",
        "legal_status": _key(raw.get("legal_status")) or "restricted",
        "noise_radius": max(0, _int(raw.get("noise_radius"), 0)),
        "range": max(0, _int(raw.get("range"), 0)),
        "reset_count": max(0, _int(raw.get("reset_count"), 0)),
        "pulse_interval": max(1, _int(raw.get("pulse_interval"), 4)),
        "pulse_count": max(1, _int(raw.get("pulse_count"), 1)),
        "status": _key(raw.get("status")),
        "status_duration": max(1, _int(raw.get("status_duration"), 4)),
        "concealment": max(0.0, min(12.0, _float(raw.get("concealment"), 4.0))),
        "disarm_difficulty": max(1.0, min(12.0, _float(raw.get("disarm_difficulty"), 5.0))),
        "single_use": bool(raw.get("single_use", False)),
        "controller_retained": bool(raw.get("controller_retained", False)),
    }
    return profile


def mechanical_recipe_for_plan(item_id, *, recipe_catalog=None):
    item_id = _key(item_id)
    recipes = recipe_catalog or load_mechanical_recipe_catalog()
    return next((row for row in recipes.values() if row.get("plan_item_id") == item_id), None)


def mechanical_recipe_for_output(item_id, *, recipe_catalog=None):
    item_id = _key(item_id)
    recipes = recipe_catalog or load_mechanical_recipe_catalog()
    return next((row for row in recipes.values() if row.get("output_item_id") == item_id), None)


def item_is_mechanical_plan(item_or_def, *, item_catalog=None):
    catalog = item_catalog or ITEM_CATALOG
    item_def = catalog.get(_key(item_or_def), {}) if not isinstance(item_or_def, Mapping) else item_or_def
    return MECHANICAL_PLAN_TAG in _tags(item_def)


def item_is_mechanical_device(item_or_def, *, item_catalog=None):
    catalog = item_catalog or ITEM_CATALOG
    item_def = catalog.get(_key(item_or_def), {}) if not isinstance(item_or_def, Mapping) else item_or_def
    return MECHANICAL_DEVICE_TAG in _tags(item_def)


def ensure_mechanical_knowledge(sim):
    state = getattr(sim, "mechanical_known_recipes", None)
    if not isinstance(state, dict):
        state = {}
        sim.mechanical_known_recipes = state
    return state


def known_mechanical_recipes_for_actor(sim, eid):
    state = ensure_mechanical_knowledge(sim)
    return dict(state.get(str(eid), {}) or {})


def learn_mechanical_recipe(sim, eid, recipe_id, *, source_kind="plan"):
    recipes = load_mechanical_recipe_catalog()
    recipe_id = _key(recipe_id)
    if recipe_id not in recipes:
        return False
    actor_rows = ensure_mechanical_knowledge(sim).setdefault(str(eid), {})
    if recipe_id in actor_rows:
        return False
    actor_rows[recipe_id] = {
        "learned_tick": _int(getattr(sim, "tick", 0)),
        "source_kind": _key(source_kind) or "plan",
    }
    return True


def _inventory_for(sim, eid):
    return sim.ecs.get(Inventory).get(eid) if sim is not None and eid is not None else None


def _work_surface_at(sim, eid, x, y, z):
    tokens = {"repair_bench", "workshop", "service_bay", "parts_room", "workbench"}
    for prop in tuple(getattr(sim, "properties", {}).values()):
        if _int(prop.get("z"), 0) != _int(z):
            continue
        metadata = prop.get("metadata") if isinstance(prop.get("metadata"), Mapping) else {}
        room_kind = _key(metadata.get("room_kind"))
        fixture_type = _key(metadata.get("fixture_type"))
        archetype = _key(metadata.get("archetype"))
        if not ({room_kind, fixture_type, archetype} & tokens):
            continue
        footprint = metadata.get("footprint") if isinstance(metadata.get("footprint"), Mapping) else {}
        if footprint:
            left = _int(footprint.get("left"), prop.get("x", 0))
            right = _int(footprint.get("right"), prop.get("x", 0))
            top = _int(footprint.get("top"), prop.get("y", 0))
            bottom = _int(footprint.get("bottom"), prop.get("y", 0))
            if left <= int(x) <= right and top <= int(y) <= bottom:
                access = evaluate_property_access(sim, eid, prop, x=x, y=y, z=z)
                if bool(getattr(access, "permitted", False)):
                    return prop
        if abs(_int(prop.get("x")) - int(x)) + abs(_int(prop.get("y")) - int(y)) <= 1:
            access = evaluate_property_access(sim, eid, prop, x=x, y=y, z=z)
            if bool(getattr(access, "permitted", False)):
                return prop
    return None


def _craft_tool(inventory, *, item_catalog=None):
    catalog = item_catalog or ITEM_CATALOG
    candidates = []
    if inventory is None:
        return None
    for entry in inventory.items:
        item_id = _key(entry.get("item_id"))
        if item_id not in MECHANICAL_TOOL_IDS:
            continue
        condition = item_instance_condition(item_id, metadata=entry.get("metadata"), item_catalog=catalog)
        if not condition.get("usable", True):
            continue
        utility = (1 if item_id == "pocket_multitool" else 0) + _float(condition.get("durability_ratio"), 1.0)
        candidates.append((utility, item_id, entry))
    return max(candidates, key=lambda row: (row[0], row[1]))[2] if candidates else None


def _selected_components(inventory, requirements, component_choices=()):
    entries = tuple(getattr(inventory, "items", ()) or ())
    by_item = {}
    remaining_by_index = {}
    for index, entry in enumerate(entries):
        item_id = _key(entry.get("item_id"))
        by_item.setdefault(item_id, []).append(index)
        remaining_by_index[index] = max(0, _int(entry.get("quantity"), 0))
    selected_by_index = {}

    def allocate(item_id, needed, remaining, selected):
        needed = max(1, _int(needed, 1))
        for index in by_item.get(_key(item_id), ()):
            amount = min(needed, remaining.get(index, 0))
            if amount <= 0:
                continue
            remaining[index] -= amount
            selected[index] = selected.get(index, 0) + amount
            needed -= amount
            if needed <= 0:
                return True
        return False

    for item_id, needed in requirements.items():
        if not allocate(item_id, needed, remaining_by_index, selected_by_index):
            return None

    for choice in tuple(component_choices or ()):
        options = choice.get("options") if isinstance(choice, dict) and isinstance(choice.get("options"), dict) else {}
        resolved = None
        for item_id, needed in options.items():
            candidate_remaining = dict(remaining_by_index)
            candidate_selected = dict(selected_by_index)
            if allocate(item_id, needed, candidate_remaining, candidate_selected):
                resolved = (candidate_remaining, candidate_selected)
                break
        if resolved is None:
            return None
        remaining_by_index, selected_by_index = resolved

    return [
        (entries[index], quantity)
        for index, quantity in sorted(selected_by_index.items())
        if quantity > 0
    ]


def _quality_for_margin(margin):
    if margin < 0.0:
        return "poor"
    if margin < 1.8:
        return "standard"
    if margin < 3.7:
        return "good"
    return "excellent"


def craft_mechanical_recipe(sim, eid, plan_entry, *, item_catalog=None, recipe_catalog=None):
    catalog = item_catalog or ITEM_CATALOG
    recipes = recipe_catalog or load_mechanical_recipe_catalog()
    recipe = mechanical_recipe_for_plan((plan_entry or {}).get("item_id"), recipe_catalog=recipes)
    if recipe is None:
        return {"ok": False, "reason": "not_mechanical_plan"}
    learn_mechanical_recipe(sim, eid, recipe["id"], source_kind="carried_plan")
    inventory = _inventory_for(sim, eid)
    if inventory is None:
        return {"ok": False, "reason": "no_inventory", "recipe": recipe}
    tool = _craft_tool(inventory, item_catalog=catalog)
    if tool is None:
        return {"ok": False, "reason": "no_mechanical_tool", "recipe": recipe}
    selected = _selected_components(inventory, recipe["components"], recipe.get("component_choices"))
    if selected is None:
        return {"ok": False, "reason": "missing_components", "recipe": recipe}

    positions = sim.ecs.get(Position)
    pos = positions.get(eid)
    surface = _work_surface_at(sim, eid, pos.x, pos.y, pos.z) if pos is not None else None
    if surface is None and not bool(recipe.get("field_craftable")):
        return {"ok": False, "reason": "work_surface_required", "recipe": recipe}
    mechanics = actor_skill(sim, eid, "mechanics", default=5.0)
    tool_condition = item_instance_condition(tool.get("item_id"), metadata=tool.get("metadata"), item_catalog=catalog)
    tool_bonus = 0.65 if _key(tool.get("item_id")) == "pocket_multitool" else 0.25
    tool_bonus += _float(tool_condition.get("score_bonus"), 0.0)
    surface_bonus = 1.15 if surface is not None else 0.0
    plan_condition = item_instance_condition(
        plan_entry.get("item_id"),
        metadata=plan_entry.get("metadata"),
        item_catalog=catalog,
    )
    plan_bonus = _float(plan_condition.get("score_bonus"), 0.0) * 0.35
    component_scores = []
    for component_entry, quantity in selected:
        condition = item_instance_condition(
            component_entry.get("item_id"),
            metadata=component_entry.get("metadata"),
            item_catalog=catalog,
        )
        component_scores.extend([_float(condition.get("score_bonus"), 0.0)] * max(1, int(quantity)))
    material_bonus = (sum(component_scores) / len(component_scores)) * 0.45 if component_scores else 0.0
    needs = sim.ecs.get(NPCNeeds).get(eid)
    fatigue_penalty = 0.0
    if needs is not None:
        energy = max(0.0, min(100.0, _float(getattr(needs, "energy", 100.0), 100.0)))
        wakefulness = max(0.0, min(100.0, _float(getattr(needs, "wakefulness", 100.0), 100.0)))
        fatigue_penalty = (max(0.0, 55.0 - energy) / 55.0) * 0.7
        fatigue_penalty += (max(0.0, 55.0 - wakefulness) / 55.0) * 0.9
    token = (
        f"{getattr(sim, 'seed', 0)}:mechanical_craft:{getattr(sim, 'tick', 0)}:"
        f"{eid}:{recipe['id']}:{plan_entry.get('instance_id')}"
    )
    roll = random.Random(token).uniform(-1.15, 1.15)
    score = float(mechanics) + tool_bonus + surface_bonus + plan_bonus + material_bonus + roll - fatigue_penalty
    margin = score - float(recipe["difficulty"])
    quality = _quality_for_margin(margin)
    reliability = max(0.5, min(0.99, 0.72 + (margin * 0.055) + (0.06 if surface is not None else 0.0)))

    snapshot = copy.deepcopy(inventory.items)
    component_payload = []
    for entry, quantity in selected:
        removed = inventory.remove_item(instance_id=entry.get("instance_id"), quantity=quantity)
        if not removed:
            inventory.items = snapshot
            return {"ok": False, "reason": "component_remove_failed", "recipe": recipe}
        component_payload.append({
            "item_id": removed.get("item_id"),
            "instance_id": removed.get("instance_id"),
            "quantity": removed.get("quantity"),
            "metadata": copy.deepcopy(removed.get("metadata") or {}),
        })

    output_id = recipe["output_item_id"]
    output_def = catalog.get(output_id, {})
    condition_profile = item_condition_profile(output_id, item_catalog=catalog)
    max_durability = max(1, _int(condition_profile.get("max_durability"), 5))
    durability_ratio = {"poor": 0.48, "standard": 0.72, "good": 0.9, "excellent": 1.0}[quality]
    output_metadata = {
        "source": "mechanical_crafting",
        "source_context": "field_crafted" if surface is None else "workbench_crafted",
        "recipe_id": recipe["id"],
        "crafted_by_eid": eid,
        "crafted_by_name": _entity_name(sim, eid, default="unknown maker"),
        "crafted_tick": _int(getattr(sim, "tick", 0)),
        "construction_ticks": int(recipe["construction_ticks"]),
        "component_items": component_payload,
        "item_quality": quality,
        "item_max_durability": max_durability,
        "item_durability": max(1, min(max_durability, int(round(max_durability * durability_ratio)))),
        "device_reliability": round(float(reliability), 3),
        "device_profile": copy.deepcopy(recipe["device_profile"]),
        "work_surface_property_id": surface.get("id") if surface is not None else None,
        "craft_score": round(score, 3),
        "craft_requirement": round(float(recipe["difficulty"]), 3),
        "tool_score_bonus": round(float(tool_bonus), 3),
        "plan_score_bonus": round(float(plan_bonus), 3),
        "material_score_bonus": round(float(material_bonus), 3),
        "fatigue_penalty": round(float(fatigue_penalty), 3),
    }
    added, instance_id = inventory.add_item(
        output_id,
        quantity=1,
        stack_max=max(1, _int(output_def.get("stack_max"), 1)),
        instance_factory=sim.new_item_instance_id,
        owner_eid=eid,
        owner_tag="player" if eid == getattr(sim, "player_eid", None) else "npc",
        metadata=output_metadata,
    )
    if not added:
        inventory.items = snapshot
        return {"ok": False, "reason": "inventory_full", "recipe": recipe}

    wear = apply_item_durability_loss(
        tool.get("item_id"),
        metadata=tool.get("metadata"),
        amount=1 if margin < 2.5 else 0,
        item_catalog=catalog,
    )
    if _int(wear.get("lost"), 0) > 0:
        live_tool = inventory.find(instance_id=tool.get("instance_id"))
        if live_tool is not None:
            live_tool["metadata"] = wear["metadata"]
    event_payload = {
        "eid": eid,
        "recipe_id": recipe["id"],
        "recipe_name": recipe["name"],
        "plan_item_id": recipe["plan_item_id"],
        "output_item_id": output_id,
        "output_item_name": item_display_name(output_id, metadata=output_metadata, item_catalog=catalog),
        "output_instance_id": instance_id,
        "quality": quality,
        "reliability": round(float(reliability), 3),
        "score": round(float(score), 3),
        "requirement": round(float(recipe["difficulty"]), 3),
        "construction_ticks": int(recipe["construction_ticks"]),
        "surface_property_id": surface.get("id") if surface is not None else None,
        "component_items": component_payload,
    }
    sim.emit(Event("mechanical_device_crafted", **event_payload))
    if eid == getattr(sim, "player_eid", None):
        rough = " rough but usable" if quality == "poor" else f" {quality}"
        _log_player_feedback(sim, f"You build a{rough} {event_payload['output_item_name']}.", kind="craft")
    return {"ok": True, "recipe": recipe, "metadata": output_metadata, **event_payload}


def begin_mechanical_recipe_craft(sim, eid, plan_entry, *, item_catalog=None, recipe_catalog=None):
    """Begin player construction as a short, hot-simulation activity."""
    catalog = item_catalog or ITEM_CATALOG
    recipes = recipe_catalog or load_mechanical_recipe_catalog()
    recipe = mechanical_recipe_for_plan((plan_entry or {}).get("item_id"), recipe_catalog=recipes)
    if recipe is None:
        return {"ok": False, "reason": "not_mechanical_plan"}
    learn_mechanical_recipe(sim, eid, recipe["id"], source_kind="carried_plan")
    inventory = _inventory_for(sim, eid)
    if inventory is None:
        return {"ok": False, "reason": "no_inventory", "recipe": recipe}
    if _craft_tool(inventory, item_catalog=catalog) is None:
        return {"ok": False, "reason": "no_mechanical_tool", "recipe": recipe}
    if _selected_components(inventory, recipe["components"], recipe.get("component_choices")) is None:
        return {"ok": False, "reason": "missing_components", "recipe": recipe}
    if eid != getattr(sim, "player_eid", None):
        return craft_mechanical_recipe(sim, eid, plan_entry, item_catalog=catalog, recipe_catalog=recipes)

    live = getattr(sim, "live_timeskip", None)
    if not isinstance(live, dict):
        live = {}
        sim.live_timeskip = live
    if bool(live.get("active")) or bool(live.get("result_pending")):
        return {"ok": False, "reason": "craft_in_progress", "recipe": recipe}
    pos = sim.ecs.get(Position).get(eid)
    if pos is None:
        return {"ok": False, "reason": "missing_position", "recipe": recipe}
    if not bool(recipe.get("field_craftable")) and _work_surface_at(sim, eid, pos.x, pos.y, pos.z) is None:
        return {"ok": False, "reason": "work_surface_required", "recipe": recipe}
    duration = max(1, int(recipe["construction_ticks"]))
    started_tick = _int(getattr(sim, "tick", 0))
    live.clear()
    live.update({
        "active": True,
        "owner": "mechanical_crafting",
        "kind": "mechanical_crafting",
        "service": "mechanical_crafting",
        "property_id": None,
        "property_name": recipe["name"],
        "title": f"Building {recipe['name']}...",
        "footer": "Your hands stay busy while the city keeps moving.",
        "started_tick": started_tick,
        "target_end_tick": started_tick + duration,
        "elapsed_ticks": 0,
        "total_ticks": duration,
        "player_anchor": (_int(pos.x), _int(pos.y), _int(pos.z)),
        "craft_actor_eid": eid,
        "craft_plan_instance_id": str((plan_entry or {}).get("instance_id", "") or "").strip(),
        "craft_recipe_id": recipe["id"],
        "completed": False,
        "interrupted": False,
        "interruption_reason": "",
        "result_pending": False,
        "mandatory_rest": False,
    })
    sim.emit(Event(
        "mechanical_crafting_started",
        eid=eid,
        recipe_id=recipe["id"],
        recipe_name=recipe["name"],
        construction_ticks=duration,
        started_tick=started_tick,
        target_end_tick=started_tick + duration,
    ))
    _log_player_feedback(sim, f"You lay out the parts for {recipe['name']}.", kind="craft")
    return {
        "ok": True,
        "action": "started",
        "recipe": recipe,
        "recipe_id": recipe["id"],
        "construction_ticks": duration,
    }


def _device_metadata(prop):
    metadata = (prop or {}).get("metadata") if isinstance((prop or {}).get("metadata"), Mapping) else {}
    # Old saves may contain the pre-grammar aerosol fixture.  Treat it as a
    # deployed device for indexing, sensing, and streaming while leaving its
    # aerosol runtime authoritative over the actual payload.
    return metadata if bool(metadata.get("mechanical_device") or metadata.get("aerosol_floor_trap")) else {}


def property_is_armed_mechanical_device(prop):
    metadata = _device_metadata(prop)
    return bool(metadata.get("armed", False))


def mechanical_devices_at(sim, x, y, z, *, armed_only=True):
    if sim is None:
        return ()
    if hasattr(sim, "properties_in_radius"):
        props = tuple(sim.properties_in_radius(int(x), int(y), int(z), r=0) or ())
    else:
        prop = sim.property_at(int(x), int(y), int(z)) if hasattr(sim, "property_at") else None
        props = (prop,) if prop else ()
    return tuple(
        prop for prop in props
        if _device_metadata(prop) and (not armed_only or property_is_armed_mechanical_device(prop))
    )


def _device_index(sim):
    index = getattr(sim, "_mechanical_device_ids", None)
    if not isinstance(index, set):
        index = set()
        sim._mechanical_device_ids = index
    return index


def rebuild_mechanical_device_index(sim):
    index = _device_index(sim)
    index.clear()
    for property_id, prop in getattr(sim, "properties", {}).items():
        if _device_metadata(prop):
            index.add(str(property_id))
    return index


def _remember_device(sim, observer_eid, prop, *, placer_eid=None, source="placement", strength=0.84):
    memory = sim.ecs.get(NPCMemory).get(observer_eid)
    if memory is None:
        return False
    metadata = _device_metadata(prop)
    memory.remember(
        getattr(sim, "tick", 0),
        MECHANICAL_DEVICE_MEMORY_KIND,
        strength=max(0.05, min(1.0, float(strength))),
        property_id=prop.get("id"),
        placer_eid=placer_eid,
        x=_int(prop.get("x")),
        y=_int(prop.get("y")),
        z=_int(prop.get("z")),
        item_id=metadata.get("source_item_id"),
        item_name=metadata.get("source_item_name"),
        device_id=metadata.get("device_id"),
        source=source,
    )
    return True


def actor_known_armed_mechanical_device_positions(sim, eid):
    memory = sim.ecs.get(NPCMemory).get(eid) if sim is not None and eid is not None else None
    if memory is None:
        return frozenset()
    positions = set()
    for entry in tuple(getattr(memory, "entries", ()) or ()):
        if _key(entry.get("kind")) != MECHANICAL_DEVICE_MEMORY_KIND:
            continue
        if _float(entry.get("strength"), 0.0) <= 0.05:
            continue
        data = entry.get("data") if isinstance(entry.get("data"), Mapping) else {}
        property_id = str(data.get("property_id", "") or "").strip()
        prop = getattr(sim, "properties", {}).get(property_id) if property_id else None
        if property_is_armed_mechanical_device(prop):
            positions.add(_coord(prop.get("x"), prop.get("y"), prop.get("z", 0)))
    return frozenset(positions)


def actor_knows_armed_mechanical_device_at(sim, eid, x, y, z):
    return _coord(x, y, z) in actor_known_armed_mechanical_device_positions(sim, eid)


def _drone_known_device_ids(state):
    metadata = getattr(state, "source_metadata", None)
    if not isinstance(metadata, dict):
        metadata = {}
        state.source_metadata = metadata
    known = {
        str(value or "").strip()
        for value in tuple(metadata.get("known_mechanical_device_ids", ()) or ())
        if str(value or "").strip()
    }
    metadata["known_mechanical_device_ids"] = sorted(known)
    return known


def drone_knows_armed_mechanical_device_at(sim, drone_eid, x, y, z):
    state = sim.ecs.get(DroneState).get(drone_eid) if sim is not None and drone_eid is not None else None
    if state is None:
        return False
    known = _drone_known_device_ids(state)
    found = False
    stale = set()
    for property_id in known:
        prop = getattr(sim, "properties", {}).get(property_id)
        if not property_is_armed_mechanical_device(prop):
            stale.add(property_id)
            continue
        if _coord(prop.get("x"), prop.get("y"), prop.get("z", 0)) == _coord(x, y, z):
            found = True
    if stale:
        known.difference_update(stale)
        state.source_metadata["known_mechanical_device_ids"] = sorted(known)
    return found


def drone_detect_mechanical_devices_at(sim, drone_eid, x, y, z, *, emit=True):
    """Give one deployed drone an honest sensor read of a particular cell.

    This is deliberately a point query used by movement and the bounded device
    update.  No sensor means no detection, and a failed read is not converted
    into permanent knowledge.
    """
    props = mechanical_devices_at(sim, x, y, z)
    if not props:
        return False
    state = sim.ecs.get(DroneState).get(drone_eid) if sim is not None and drone_eid is not None else None
    pos = sim.ecs.get(Position).get(drone_eid) if state is not None else None
    if state is None or pos is None or _key(getattr(state, "mode", "")) != "deployed":
        return False
    if drone_knows_armed_mechanical_device_at(sim, drone_eid, x, y, z):
        return True
    if drone_sensor_suppression_status(state, tick=_int(getattr(sim, "tick", 0))).get("active"):
        return False
    distance = abs(_int(pos.x) - _int(x)) + abs(_int(pos.y) - _int(y))
    modes = tuple(
        mode for mode in drone_sensor_modes(state, item_catalog=ITEM_CATALOG)
        if int(mode.get("range", 0) or 0) >= distance
    )
    if not modes or _int(pos.z) != _int(z):
        return False
    if not has_line_of_sight(sim, pos.x, pos.y, pos.z, x, y, z):
        return False

    sensor_reads = {
        "radar": 7.2,
        "lidar": 6.7,
        "camera": 5.4,
        "sonar": 4.8,
        "ir": 3.8,
    }
    now = _int(getattr(sim, "tick", 0))
    known = _drone_known_device_ids(state)
    detected = False
    for prop in props:
        metadata = _device_metadata(prop)
        profile = metadata.get("device_profile") if isinstance(metadata.get("device_profile"), Mapping) else {}
        concealment = _float(profile.get("concealment"), 4.0)
        electronic = _key(profile.get("trigger")) in {"timer", "remote_signal", "proximity"}
        best = -99.0
        for mode in modes:
            sensor_kind = _key(mode.get("sensor_kind"))
            base = sensor_reads.get(sensor_kind, 4.6)
            if sensor_kind == "ir" and electronic:
                base += 1.1
            if bool(mode.get("threat")):
                base += 0.45
            best = max(best, base + max(0, 3 - distance) * 0.35)
        token = f"{getattr(sim, 'seed', 0)}:drone_device_notice:{prop.get('id')}:{drone_eid}:{now // 6}"
        if best + random.Random(token).uniform(-0.75, 0.75) < concealment:
            continue
        property_id = str(prop.get("id", "") or "").strip()
        if property_id:
            known.add(property_id)
        detected = True
        if emit:
            sim.emit(Event(
                "mechanical_device_discovered",
                drone_eid=drone_eid,
                controller_eid=getattr(state, "controller_eid", None),
                property_id=property_id,
                device_id=metadata.get("device_id"),
                item_name=metadata.get("source_item_name"),
                sensor_kind=max(
                    modes,
                    key=lambda row: sensor_reads.get(_key(row.get("sensor_kind")), 4.6),
                ).get("sensor_kind"),
                x=_int(x),
                y=_int(y),
                z=_int(z),
            ))
    state.source_metadata["known_mechanical_device_ids"] = sorted(known)
    return detected


def place_deployed_device(
    sim,
    eid,
    inventory,
    item_entry,
    x,
    y,
    z=0,
    *,
    profile,
    item_catalog=None,
    consume_item=True,
    metadata_extra=None,
):
    catalog = item_catalog or ITEM_CATALOG
    item_id = _key((item_entry or {}).get("item_id"))
    item_def = catalog.get(item_id, {})
    profile = normalize_device_profile(profile)
    tile = sim.tilemap.tile_at(int(x), int(y), int(z)) if hasattr(sim, "tilemap") else None
    if tile is None:
        return {"ok": False, "reason": "no_tile"}
    if not bool(getattr(tile, "walkable", False)):
        return {"ok": False, "reason": "blocked_tile"}
    if mechanical_devices_at(sim, x, y, z):
        return {"ok": False, "reason": "device_present"}
    if hasattr(sim, "ground_items_at") and sim.ground_items_at(int(x), int(y), z=int(z)):
        return {"ok": False, "reason": "ground_item_present"}

    covered_property = property_covering(sim, int(x), int(y), int(z))
    if consume_item:
        removed = inventory.remove_item(instance_id=item_entry.get("instance_id"), quantity=1) if inventory else None
        if not removed:
            return {"ok": False, "reason": "remove_failed"}
    else:
        removed = copy.deepcopy(dict(item_entry or {}))
        removed["quantity"] = 1
    source_metadata = copy.deepcopy(removed.get("metadata") if isinstance(removed.get("metadata"), Mapping) else {})
    item_name = item_display_name(item_id, metadata=source_metadata, item_catalog=catalog)
    device_id = _key(source_metadata.get("recipe_id")) or item_id
    reliability = max(0.05, min(1.0, _float(source_metadata.get("device_reliability"), 0.82)))
    now = _int(getattr(sim, "tick", 0))
    metadata = {
        "archetype": MECHANICAL_DEVICE_FIXTURE_TYPE,
        "fixture_type": MECHANICAL_DEVICE_FIXTURE_TYPE,
        "mechanical_device": True,
        "device_id": device_id,
        "device_profile": copy.deepcopy(profile),
        "device_body": profile["body"],
        "device_trigger": profile["trigger"],
        "device_payload": profile["payload"],
        "armed": True,
        "armed_by_eid": eid,
        "armed_by_name": _entity_name(sim, eid, default="the placer"),
        "armed_tick": now,
        "ignored_until_vacated_eids": [eid],
        "source_item_id": item_id,
        "source_item_name": item_name,
        "source_item_instance_id": removed.get("instance_id"),
        "source_item_metadata": source_metadata,
        "display_glyph": profile["glyph"],
        "display_color": profile["color"],
        "pickup_allowed": False,
        "legal_status": profile["legal_status"],
        "reliability": reliability,
        "reset_count": profile["reset_count"],
        "next_pulse_tick": now + profile["pulse_interval"],
        "remaining_pulses": profile["pulse_count"],
    }
    if isinstance(metadata_extra, Mapping):
        metadata.update(copy.deepcopy(dict(metadata_extra)))
    property_id = sim.register_property(
        name=item_name,
        kind="fixture",
        x=int(x),
        y=int(y),
        z=int(z),
        owner_eid=eid,
        owner_tag="player" if eid == getattr(sim, "player_eid", None) else "npc",
        metadata=metadata,
    )
    _device_index(sim).add(str(property_id))
    prop = sim.properties[property_id]
    observation = observation_payload_for_position(
        sim,
        int(x),
        int(y),
        int(z),
        exclude_eid=eid,
        offender_eid=eid,
        observation_channels=("actor_witness",),
    )
    remembered = []
    observer_ids = set(observation.get("observer_eids", ()) or ()) | set(observation.get("accountable_observer_eids", ()) or ())
    for observer_eid in sorted(observer_ids):
        if observer_eid != eid and _remember_device(sim, observer_eid, prop, placer_eid=eid):
            remembered.append(observer_eid)
    payload = {
        "eid": eid,
        "property_id": property_id,
        "device_id": device_id,
        "item_id": item_id,
        "item_name": item_name,
        "x": int(x),
        "y": int(y),
        "z": int(z),
        "remembered_eids": tuple(remembered),
        **observation,
    }
    sim.emit(Event("mechanical_device_placed", **payload))
    covered_id = str((covered_property or {}).get("id", "") or "").strip()
    covered_owner = (covered_property or {}).get("owner_eid")
    covered_owner_tag = _key((covered_property or {}).get("owner_tag"))
    placed_on_anothers_property = bool(
        covered_id
        and covered_id != property_id
        and (
            (covered_owner is not None and covered_owner != eid)
            or (covered_owner is None and covered_owner_tag not in {"", "public"})
        )
    )
    payload_kind = _key(profile.get("payload"))
    throw_profile = metadata.get("payload_throw_profile") if isinstance(metadata.get("payload_throw_profile"), Mapping) else {}
    harmful = payload_kind == "restraint" or bool(
        _key(throw_profile.get("aerosol_status"))
        or _int(throw_profile.get("fire_intensity"), 0) > 0
        or _int(throw_profile.get("damage"), 0) > 0
    )
    if placed_on_anothers_property:
        score = 38 if harmful else 18
        sim.emit(Event(
            "action_offense",
            offender_eid=eid,
            action="place_concealed_device",
            context="mechanical_device",
            offense_score=score,
            offense_tier="serious" if score >= 35 else "minor",
            item_id=item_id,
            item_name=item_name,
            property_id=covered_id,
            target_property_id=covered_id,
            target_name=(covered_property or {}).get("name"),
            device_property_id=property_id,
            x=int(x),
            y=int(y),
            z=int(z),
            **observation,
        ))
    return {"ok": True, "property_id": property_id, "item": removed, "metadata": metadata, **payload}


def _remote_payload_entry(inventory, controller_entry, *, item_catalog=None):
    catalog = item_catalog or ITEM_CATALOG
    if inventory is None:
        return None
    for entry in inventory.items:
        if entry.get("instance_id") == controller_entry.get("instance_id"):
            continue
        item_def = catalog.get(_key(entry.get("item_id")), {})
        throw_profile = item_def.get("throw_profile") if isinstance(item_def.get("throw_profile"), Mapping) else {}
        if not throw_profile:
            continue
        if _tags(item_def).intersection(REMOTE_PAYLOAD_TAGS) or any(
            _int(throw_profile.get(key), 0) > 0
            for key in ("smoke_intensity", "fire_intensity", "cloud_duration")
        ):
            return entry
    return None


def _clear_remote_link(sim, metadata, *, wear=0):
    controller_instance_id = str(metadata.get("controller_instance_id", "") or "").strip()
    owner_eid = metadata.get("armed_by_eid")
    inventory = _inventory_for(sim, owner_eid)
    controller = inventory.find(instance_id=controller_instance_id) if inventory is not None and controller_instance_id else None
    if controller is not None:
        controller_metadata = controller.setdefault("metadata", {})
        if int(wear) > 0:
            result = apply_item_durability_loss(
                controller.get("item_id"),
                metadata=controller_metadata,
                amount=int(wear),
                item_catalog=ITEM_CATALOG,
            )
            controller["metadata"] = result.get("metadata", controller_metadata)
            controller_metadata = controller["metadata"]
        controller_metadata.pop("linked_device_property_id", None)
        controller_metadata.pop("linked_device_channel", None)


def _release_remote_payload(sim, prop, *, trigger_eid=None):
    metadata = _device_metadata(prop)
    throw_profile = metadata.get("payload_throw_profile") if isinstance(metadata.get("payload_throw_profile"), Mapping) else {}
    if not throw_profile:
        return False
    x, y, z = _coord(prop.get("x"), prop.get("y"), prop.get("z", 0))
    source_eid = metadata.get("armed_by_eid")
    payload = {
        "source_eid": source_eid,
        "weapon_id": metadata.get("payload_item_id"),
        "x": x,
        "y": y,
        "z": z,
        "radius": max(0, _int(throw_profile.get("cloud_radius"), 0)),
        "smoke_intensity": max(0, _int(throw_profile.get("smoke_intensity"), 0)),
        "cloud_duration": max(0, _int(throw_profile.get("cloud_duration"), 0)),
        "thrown_item_id": metadata.get("payload_item_id"),
        "thrown_item_name": metadata.get("payload_item_name"),
        "fire_intensity": max(0, _int(throw_profile.get("fire_intensity"), 0)),
    }
    aerosol_status = _key(throw_profile.get("aerosol_status"))
    if aerosol_status:
        payload.update({
            "aerosol_status": aerosol_status,
            "aerosol_duration": max(1, _int(throw_profile.get("aerosol_duration"), 1)),
            "aerosol_modifiers": dict(throw_profile.get("aerosol_modifiers", {}) or {}),
            "aerosol_exposure_cooldown": max(1, _int(throw_profile.get("aerosol_exposure_cooldown"), 6)),
            "aerosol_label": str(throw_profile.get("aerosol_label", "") or "").strip(),
        })
    if payload["smoke_intensity"] > 0 or payload["cloud_duration"] > 0:
        sim.emit(Event("smoke_cloud_released", **payload))
    if aerosol_status:
        sim.emit(Event("aerosol_cloud_released", **payload))
    if payload["fire_intensity"] > 0:
        sim.emit(Event("fire_started", source_eid=source_eid, x=x, y=y, z=z, intensity=payload["fire_intensity"], cause="remote_release_rig"))
    observation = observation_payload_for_position(
        sim, x, y, z, exclude_eid=source_eid, offender_eid=source_eid, observation_channels=("actor_witness",)
    )
    sim.emit(Event(
        "mechanical_device_triggered",
        property_id=prop.get("id"),
        device_id=metadata.get("device_id"),
        source_eid=source_eid,
        trigger_eid=trigger_eid,
        item_id=metadata.get("source_item_id"),
        item_name=metadata.get("source_item_name"),
        payload_item_id=metadata.get("payload_item_id"),
        payload_item_name=metadata.get("payload_item_name"),
        x=x,
        y=y,
        z=z,
        **observation,
    ))
    if source_eid is not None and (aerosol_status or payload["fire_intensity"] > 0):
        sim.emit(Event(
            "action_offense",
            offender_eid=source_eid,
            action="remote_device_release",
            context="mechanical_device",
            offense_score=52,
            offense_tier="serious",
            item_id=metadata.get("source_item_id"),
            item_name=metadata.get("source_item_name"),
            property_id=prop.get("id"),
            x=x,
            y=y,
            z=z,
            **observation,
        ))
    _clear_remote_link(sim, metadata, wear=1)
    _device_index(sim).discard(str(prop.get("id")))
    sim.remove_property(prop.get("id"))
    return True


def use_mechanical_device_item(sim, eid, inventory, item_entry, x, y, z=0, *, item_catalog=None, recipe_catalog=None):
    catalog = item_catalog or ITEM_CATALOG
    recipes = recipe_catalog or load_mechanical_recipe_catalog()
    item_id = _key((item_entry or {}).get("item_id"))
    recipe = mechanical_recipe_for_output(item_id, recipe_catalog=recipes)
    if recipe is None:
        return {"ok": False, "reason": "not_mechanical_device"}
    profile = recipe["device_profile"]
    metadata = item_entry.get("metadata") if isinstance(item_entry.get("metadata"), dict) else {}
    linked_id = str(metadata.get("linked_device_property_id", "") or "").strip()
    if profile.get("trigger") == "remote_signal" and linked_id:
        prop = getattr(sim, "properties", {}).get(linked_id)
        if not property_is_armed_mechanical_device(prop):
            metadata.pop("linked_device_property_id", None)
            metadata.pop("linked_device_channel", None)
            return {"ok": False, "reason": "remote_link_lost"}
        distance = abs(_int(prop.get("x")) - int(x)) + abs(_int(prop.get("y")) - int(y))
        if _int(prop.get("z")) != int(z) or distance > int(profile.get("range", 0)):
            return {"ok": False, "reason": "remote_out_of_range", "distance": distance, "range": profile.get("range", 0)}
        if not _release_remote_payload(sim, prop, trigger_eid=eid):
            return {"ok": False, "reason": "remote_payload_failed"}
        return {"ok": True, "action": "triggered", "property_id": linked_id}

    metadata_extra = {}
    consume_item = not bool(profile.get("controller_retained"))
    payload_entry = None
    if profile.get("trigger") == "remote_signal":
        payload_entry = _remote_payload_entry(inventory, item_entry, item_catalog=catalog)
        if payload_entry is None:
            return {"ok": False, "reason": "remote_payload_missing"}
        payload_def = catalog.get(_key(payload_entry.get("item_id")), {})
        payload_name = item_display_name(payload_entry.get("item_id"), metadata=payload_entry.get("metadata"), item_catalog=catalog)
        channel = f"field-{getattr(sim, 'seed', 0)}-{item_entry.get('instance_id')}-{getattr(sim, 'tick', 0)}"
        metadata_extra = {
            "controller_instance_id": item_entry.get("instance_id"),
            "remote_channel": channel,
            "payload_item_id": payload_entry.get("item_id"),
            "payload_item_name": payload_name,
            "payload_item_metadata": copy.deepcopy(payload_entry.get("metadata") or {}),
            "payload_throw_profile": copy.deepcopy(payload_def.get("throw_profile") or {}),
        }
    result = place_deployed_device(
        sim,
        eid,
        inventory,
        item_entry,
        x,
        y,
        z,
        profile=profile,
        item_catalog=catalog,
        consume_item=consume_item,
        metadata_extra=metadata_extra,
    )
    if not result.get("ok"):
        return result
    if payload_entry is not None:
        removed_payload = inventory.remove_item(instance_id=payload_entry.get("instance_id"), quantity=1)
        if not removed_payload:
            sim.remove_property(result.get("property_id"))
            _device_index(sim).discard(str(result.get("property_id")))
            return {"ok": False, "reason": "remote_payload_remove_failed"}
        metadata["linked_device_property_id"] = result["property_id"]
        metadata["linked_device_channel"] = metadata_extra["remote_channel"]
    return {"ok": True, "action": "placed", **result}


class MechanicalDeviceSystem(System):
    def __init__(self, sim):
        super().__init__(sim)
        rebuild_mechanical_device_index(sim)
        sim.mechanical_device_system = self
        self.sim.events.subscribe("entity_moved", self.on_entity_moved)
        self.sim.events.subscribe("property_interact", self.on_property_interact)
        self.sim.events.subscribe("npc_intent_changed", self.on_npc_intent_changed)

    def _live_props(self):
        for property_id in tuple(_device_index(self.sim)):
            prop = self.sim.properties.get(property_id)
            if _device_metadata(prop):
                yield prop
            else:
                _device_index(self.sim).discard(property_id)

    def _remove_device(self, prop):
        property_id = str(prop.get("id", "") or "")
        _clear_remote_link(self.sim, _device_metadata(prop))
        _device_index(self.sim).discard(property_id)
        self.sim.remove_property(property_id)

    def _release_ignored_actor(self, eid, x, y, z):
        for prop in mechanical_devices_at(self.sim, x, y, z):
            metadata = _device_metadata(prop)
            ignored = list(metadata.get("ignored_until_vacated_eids", ()) or ())
            if eid in ignored:
                metadata["ignored_until_vacated_eids"] = [value for value in ignored if value != eid]

    def on_entity_moved(self, event):
        eid = event.data.get("eid")
        if eid is None:
            return
        old_x, old_y = event.data.get("old_x"), event.data.get("old_y")
        old_z = event.data.get("old_z", event.data.get("z", 0))
        if old_x is not None and old_y is not None:
            self._release_ignored_actor(eid, old_x, old_y, old_z)
        x, y, z = event.data.get("x"), event.data.get("y"), event.data.get("z", 0)
        if x is None or y is None:
            return
        for prop in mechanical_devices_at(self.sim, x, y, z):
            metadata = _device_metadata(prop)
            if metadata.get("aerosol_floor_trap"):
                continue
            if eid in set(metadata.get("ignored_until_vacated_eids", ()) or ()):
                continue
            profile = metadata.get("device_profile") if isinstance(metadata.get("device_profile"), Mapping) else {}
            if _key(profile.get("trigger")) == "step":
                self._trigger_step_device(prop, eid)
                break

    def _reliability_holds(self, prop, target_eid):
        metadata = _device_metadata(prop)
        reliability = max(0.05, min(1.0, _float(metadata.get("reliability"), 0.82)))
        token = f"{getattr(self.sim, 'seed', 0)}:device_trigger:{prop.get('id')}:{target_eid}:{getattr(self.sim, 'tick', 0)}"
        if random.Random(token).random() <= reliability:
            return True
        self.sim.emit(Event(
            "mechanical_device_misfired",
            property_id=prop.get("id"),
            device_id=metadata.get("device_id"),
            item_name=metadata.get("source_item_name"),
            target_eid=target_eid,
            x=prop.get("x"),
            y=prop.get("y"),
            z=prop.get("z"),
        ))
        metadata["armed"] = False
        metadata["misfired_tick"] = _int(getattr(self.sim, "tick", 0))
        return False

    def _trigger_step_device(self, prop, target_eid):
        metadata = _device_metadata(prop)
        profile = metadata.get("device_profile") if isinstance(metadata.get("device_profile"), Mapping) else {}
        if not self._reliability_holds(prop, target_eid):
            return False
        x, y, z = _coord(prop.get("x"), prop.get("y"), prop.get("z", 0))
        payload_kind = _key(profile.get("payload"))
        source_eid = metadata.get("armed_by_eid")
        if payload_kind == "alarm":
            self.sim.emit(Event(
                "noise",
                source_eid=None,
                device_owner_eid=source_eid,
                x=x,
                y=y,
                z=z,
                radius=max(1, _int(profile.get("noise_radius"), 8)),
                cause="tripline_alarm",
                target_eid=target_eid,
                property_id=prop.get("id"),
            ))
        elif payload_kind == "restraint":
            statuses = self.sim.ecs.get(StatusEffects)
            status = statuses.get(target_eid)
            if status is None:
                status = StatusEffects()
                self.sim.ecs.add(target_eid, status)
            identity = self.sim.ecs.get(CreatureIdentity).get(target_eid)
            taxonomy = _key(getattr(identity, "taxonomy_class", ""))
            duration = max(1, _int(profile.get("status_duration"), 5))
            if taxonomy in {"avian", "insect", "amphibian"}:
                duration = max(1, duration // 2)
            status.add(
                _key(profile.get("status")) or "snared",
                duration,
                modifiers={"move_speed_mult": -0.78, "retreat_bias_delta": 0.18},
                source_item=metadata.get("source_item_id"),
            )
        observation = observation_payload_for_position(
            self.sim, x, y, z, exclude_eid=source_eid, offender_eid=source_eid, observation_channels=("actor_witness",)
        )
        self.sim.emit(Event(
            "mechanical_device_triggered",
            property_id=prop.get("id"),
            device_id=metadata.get("device_id"),
            source_eid=source_eid,
            target_eid=target_eid,
            target_name=_entity_name(self.sim, target_eid),
            item_id=metadata.get("source_item_id"),
            item_name=metadata.get("source_item_name"),
            payload=payload_kind,
            x=x,
            y=y,
            z=z,
            **observation,
        ))
        source_metadata = metadata.get("source_item_metadata") if isinstance(metadata.get("source_item_metadata"), dict) else {}
        wear = apply_item_durability_loss(
            metadata.get("source_item_id"),
            metadata=source_metadata,
            amount=1,
            item_catalog=ITEM_CATALOG,
        )
        metadata["source_item_metadata"] = wear.get("metadata", source_metadata)
        if payload_kind == "restraint" and source_eid is not None and target_eid != source_eid:
            self.sim.emit(Event(
                "action_offense",
                offender_eid=source_eid,
                action="restraint_snare",
                context="mechanical_device",
                offense_score=42,
                offense_tier="serious",
                victim_eid=target_eid,
                target_eid=target_eid,
                item_id=metadata.get("source_item_id"),
                item_name=metadata.get("source_item_name"),
                property_id=prop.get("id"),
                x=x,
                y=y,
                z=z,
                **observation,
            ))
        reset_count = max(0, _int(metadata.get("reset_count"), 0))
        if payload_kind == "alarm" and reset_count > 1:
            metadata["reset_count"] = reset_count - 1
            metadata.setdefault("ignored_until_vacated_eids", []).append(target_eid)
        else:
            self._remove_device(prop)
        return True

    def _pulse_decoy(self, prop):
        metadata = _device_metadata(prop)
        profile = metadata.get("device_profile") if isinstance(metadata.get("device_profile"), Mapping) else {}
        x, y, z = _coord(prop.get("x"), prop.get("y"), prop.get("z", 0))
        self.sim.emit(Event(
            "noise",
            source_eid=None,
            device_owner_eid=metadata.get("armed_by_eid"),
            x=x,
            y=y,
            z=z,
            radius=max(1, _int(profile.get("noise_radius"), 10)),
            cause="decoy_beacon",
            property_id=prop.get("id"),
        ))
        self.sim.emit(Event(
            "mechanical_device_pulsed",
            property_id=prop.get("id"),
            device_id=metadata.get("device_id"),
            item_name=metadata.get("source_item_name"),
            x=x,
            y=y,
            z=z,
        ))
        remaining = max(0, _int(metadata.get("remaining_pulses"), 1) - 1)
        metadata["remaining_pulses"] = remaining
        if remaining <= 0:
            self._remove_device(prop)
        else:
            metadata["next_pulse_tick"] = _int(getattr(self.sim, "tick", 0)) + max(1, _int(profile.get("pulse_interval"), 4))

    def _discover_devices(self):
        positions = self.sim.ecs.get(Position)
        memories = self.sim.ecs.get(NPCMemory)
        now = _int(getattr(self.sim, "tick", 0))
        for prop in self._live_props():
            if not property_is_armed_mechanical_device(prop):
                continue
            metadata = _device_metadata(prop)
            profile = metadata.get("device_profile") if isinstance(metadata.get("device_profile"), Mapping) else {}
            x, y, z = _coord(prop.get("x"), prop.get("y"), prop.get("z", 0))
            for eid in self.sim.entity_ids_in_radius(x, y, z, 3):
                if eid == metadata.get("armed_by_eid") or memories.get(eid) is None:
                    continue
                if actor_knows_armed_mechanical_device_at(self.sim, eid, x, y, z):
                    continue
                pos = positions.get(eid)
                if pos is None or _int(pos.z) != z:
                    continue
                if not has_line_of_sight(self.sim, pos.x, pos.y, pos.z, x, y, z):
                    continue
                distance = abs(_int(pos.x) - x) + abs(_int(pos.y) - y)
                perception = actor_skill(self.sim, eid, "perception", default=5.0)
                token = f"{getattr(self.sim, 'seed', 0)}:device_notice:{prop.get('id')}:{eid}:{now // 6}"
                read = perception + random.Random(token).uniform(-1.0, 1.0) + max(0, 3 - distance) * 0.45
                if read >= _float(profile.get("concealment"), 4.0):
                    _remember_device(self.sim, eid, prop, placer_eid=None, source="discovery", strength=0.7)
                    self.sim.emit(Event(
                        "mechanical_device_discovered",
                        npc_eid=eid,
                        property_id=prop.get("id"),
                        device_id=metadata.get("device_id"),
                        item_name=metadata.get("source_item_name"),
                        x=x,
                        y=y,
                        z=z,
                    ))
                    if self._npc_respond_to_discovered_device(eid, prop, distance=distance):
                        break

            for drone_eid in self.sim.entity_ids_in_radius(x, y, z, 3):
                if self.sim.ecs.get(DroneState).get(drone_eid) is None:
                    continue
                drone_detect_mechanical_devices_at(self.sim, drone_eid, x, y, z)

    def _npc_respond_to_discovered_device(self, eid, prop, *, distance):
        metadata = _device_metadata(prop)
        if not metadata:
            return False
        ai = self.sim.ecs.get(AI).get(eid)
        role = _key(getattr(ai, "role", ""))
        profile = metadata.get("device_profile") if isinstance(metadata.get("device_profile"), Mapping) else {}
        mechanics = actor_skill(self.sim, eid, "mechanics", default=5.0)
        requirement = _float(profile.get("disarm_difficulty"), 5.0)
        if int(distance) <= 1 and role in {"guard", "worker", "scout"} and mechanics >= requirement:
            if self._recover_to_ground(prop, eid, disarmed=True):
                self.sim.emit(Event(
                    "mechanical_device_disarmed",
                    npc_eid=eid,
                    property_id=prop.get("id"),
                    device_id=metadata.get("device_id"),
                    item_name=metadata.get("source_item_name"),
                    owner_eid=metadata.get("armed_by_eid"),
                    x=prop.get("x"),
                    y=prop.get("y"),
                    z=prop.get("z"),
                ))
                return True
        if role in {"guard", "scout"}:
            reported = set(metadata.get("reported_by_eids", ()) or ())
            if eid not in reported:
                reported.add(eid)
                metadata["reported_by_eids"] = sorted(reported)
                self.sim.emit(Event(
                    "mechanical_device_reported",
                    npc_eid=eid,
                    property_id=prop.get("id"),
                    device_id=metadata.get("device_id"),
                    item_name=metadata.get("source_item_name"),
                    x=prop.get("x"),
                    y=prop.get("y"),
                    z=prop.get("z"),
                ))
                profile = metadata.get("device_profile") if isinstance(metadata.get("device_profile"), Mapping) else {}
                payload_kind = _key(profile.get("payload"))
                harmful = payload_kind in {"restraint", "fire", "direct_injury"} or bool(
                    _key((metadata.get("payload_throw_profile") or {}).get("aerosol_status"))
                )
                observation = observation_payload_for_position(
                    self.sim,
                    _int(prop.get("x")),
                    _int(prop.get("y")),
                    _int(prop.get("z")),
                    offender_eid=None,
                    observation_channels=("actor_witness",),
                )
                self.sim.emit(Event(
                    "action_offense",
                    offender_eid=None,
                    action="discovered_concealed_device",
                    context="mechanical_device",
                    offense_score=40 if harmful else 24,
                    offense_tier="serious" if harmful else "moderate",
                    item_id=metadata.get("source_item_id"),
                    item_name=metadata.get("source_item_name"),
                    property_id=prop.get("id"),
                    x=prop.get("x"),
                    y=prop.get("y"),
                    z=prop.get("z"),
                    **observation,
                ))
        return False

    def _recover_to_ground(self, prop, actor_eid, *, disarmed=False):
        metadata = _device_metadata(prop)
        profile = metadata.get("device_profile") if isinstance(metadata.get("device_profile"), Mapping) else {}
        if bool(profile.get("controller_retained")):
            payload_item_id = _key(metadata.get("payload_item_id"))
            if payload_item_id:
                self.sim.register_ground_item(
                    item_id=payload_item_id,
                    x=_int(prop.get("x")),
                    y=_int(prop.get("y")),
                    z=_int(prop.get("z")),
                    quantity=1,
                    owner_eid=metadata.get("armed_by_eid"),
                    owner_tag="player" if metadata.get("armed_by_eid") == getattr(self.sim, "player_eid", None) else "npc",
                    instance_id=self.sim.new_item_instance_id(),
                    metadata=copy.deepcopy(metadata.get("payload_item_metadata") or {}),
                )
            self._remove_device(prop)
            return True
        source_item_id = _key(metadata.get("source_item_id"))
        if not source_item_id:
            return False
        source_metadata = copy.deepcopy(metadata.get("source_item_metadata") or {})
        if disarmed:
            source_metadata["device_reliability"] = max(0.45, _float(source_metadata.get("device_reliability"), 0.8) - 0.08)
        self.sim.register_ground_item(
            item_id=source_item_id,
            x=_int(prop.get("x")),
            y=_int(prop.get("y")),
            z=_int(prop.get("z")),
            quantity=1,
            owner_eid=metadata.get("armed_by_eid"),
            owner_tag="player" if metadata.get("armed_by_eid") == getattr(self.sim, "player_eid", None) else "npc",
            instance_id=metadata.get("source_item_instance_id") or self.sim.new_item_instance_id(),
            metadata=source_metadata,
        )
        self._remove_device(prop)
        return True

    def on_property_interact(self, event):
        prop = self.sim.properties.get(event.data.get("property_id"))
        metadata = _device_metadata(prop)
        if not metadata:
            return
        eid = event.data.get("eid")
        if eid is None:
            return
        known = eid == metadata.get("armed_by_eid") or actor_knows_armed_mechanical_device_at(
            self.sim, eid, prop.get("x"), prop.get("y"), prop.get("z", 0)
        )
        mechanics = actor_skill(self.sim, eid, "mechanics", default=5.0)
        requirement = _float((metadata.get("device_profile") or {}).get("disarm_difficulty"), 5.0)
        if not known:
            if eid == getattr(self.sim, "player_eid", None):
                _log_player_feedback(self.sim, "You do not yet see enough to safely handle that fixture.", kind="interaction")
            event.data["handled"] = True
            return
        if eid != metadata.get("armed_by_eid") and mechanics < requirement:
            if eid == getattr(self.sim, "player_eid", None):
                _log_player_feedback(self.sim, f"The {metadata.get('source_item_name', 'device')} is beyond your safe disarm read.", kind="interaction")
            event.data["handled"] = True
            return
        inventory = _inventory_for(self.sim, eid)
        item_id = _key(metadata.get("source_item_id"))
        item_def = ITEM_CATALOG.get(item_id, {})
        source_metadata = copy.deepcopy(metadata.get("source_item_metadata") or {})
        if inventory is None:
            return
        profile = metadata.get("device_profile") if isinstance(metadata.get("device_profile"), Mapping) else {}
        if bool(profile.get("controller_retained")):
            payload_item_id = _key(metadata.get("payload_item_id"))
            payload_def = ITEM_CATALOG.get(payload_item_id, {})
            if payload_item_id:
                added, _payload_instance_id = inventory.add_item(
                    payload_item_id,
                    quantity=1,
                    stack_max=max(1, _int(payload_def.get("stack_max"), 1)),
                    instance_factory=self.sim.new_item_instance_id,
                    owner_eid=eid,
                    owner_tag="player" if eid == getattr(self.sim, "player_eid", None) else "npc",
                    metadata=copy.deepcopy(metadata.get("payload_item_metadata") or {}),
                )
                if not added:
                    if eid == getattr(self.sim, "player_eid", None):
                        _log_player_feedback(self.sim, "Your backpack needs room for the receiver's payload.", kind="interaction")
                    event.data["handled"] = True
                    return
            self._remove_device(prop)
            event.data["handled"] = True
            self.sim.emit(Event(
                "mechanical_device_recovered",
                eid=eid,
                property_id=prop.get("id"),
                device_id=metadata.get("device_id"),
                item_id=item_id,
                item_name=metadata.get("source_item_name"),
                payload_item_id=payload_item_id,
                owner_eid=metadata.get("armed_by_eid"),
                disarmed=bool(eid != metadata.get("armed_by_eid")),
            ))
            if eid == getattr(self.sim, "player_eid", None):
                _log_player_feedback(self.sim, "You recover the receiver and unload its payload.", kind="interaction")
            return
        added, _instance_id = inventory.add_item(
            item_id,
            quantity=1,
            stack_max=max(1, _int(item_def.get("stack_max"), 1)),
            instance_id=metadata.get("source_item_instance_id"),
            instance_factory=self.sim.new_item_instance_id,
            owner_eid=eid,
            owner_tag="player" if eid == getattr(self.sim, "player_eid", None) else "npc",
            metadata=source_metadata,
        )
        if not added:
            if eid == getattr(self.sim, "player_eid", None):
                _log_player_feedback(self.sim, "Your backpack has no room for the recovered device.", kind="interaction")
            event.data["handled"] = True
            return
        self._remove_device(prop)
        event.data["handled"] = True
        self.sim.emit(Event(
            "mechanical_device_recovered",
            eid=eid,
            property_id=prop.get("id"),
            device_id=metadata.get("device_id"),
            item_id=item_id,
            item_name=metadata.get("source_item_name"),
            owner_eid=metadata.get("armed_by_eid"),
            disarmed=bool(eid != metadata.get("armed_by_eid")),
        ))
        if eid == getattr(self.sim, "player_eid", None):
            verb = "disarm and recover" if eid != metadata.get("armed_by_eid") else "recover"
            _log_player_feedback(self.sim, f"You {verb} {metadata.get('source_item_name', 'the device')}.", kind="interaction")

    def on_npc_intent_changed(self, event):
        eid = event.data.get("npc_eid")
        intent = _key(event.data.get("intent"))
        if eid is None or intent not in {"protecting", "holding", "casing_target", "evading_authority"}:
            return
        ai = self.sim.ecs.get(AI).get(eid)
        pos = self.sim.ecs.get(Position).get(eid)
        inventory = _inventory_for(self.sim, eid)
        if ai is None or pos is None or inventory is None:
            return
        now = _int(getattr(self.sim, "tick", 0))
        if now - _int(getattr(ai, "last_field_device_tick", -10000), -10000) < 90:
            return
        preferred = (
            ("tripline_alarm", "restraint_snare")
            if intent in {"protecting", "holding"}
            else ("remote_release_rig", "decoy_beacon")
        )
        entry = next((row for row in inventory.items if _key(row.get("item_id")) in preferred), None)
        if entry is None or mechanical_devices_at(self.sim, pos.x, pos.y, pos.z):
            return
        result = use_mechanical_device_item(self.sim, eid, inventory, entry, pos.x, pos.y, pos.z)
        if result.get("ok"):
            ai.last_field_device_tick = now
            self.sim.emit(Event(
                "npc_mechanical_device_deployed",
                npc_eid=eid,
                intent=intent,
                property_id=result.get("property_id"),
                item_id=entry.get("item_id"),
                x=pos.x,
                y=pos.y,
                z=pos.z,
            ))

    def _npc_remote_release(self, prop):
        metadata = _device_metadata(prop)
        owner_eid = metadata.get("armed_by_eid")
        if owner_eid is None or owner_eid == getattr(self.sim, "player_eid", None):
            return False
        ai = self.sim.ecs.get(AI).get(owner_eid)
        owner_pos = self.sim.ecs.get(Position).get(owner_eid)
        if ai is None or owner_pos is None or _key(getattr(ai, "state", "")) != "evading_authority":
            return False
        x, y, z = _coord(prop.get("x"), prop.get("y"), prop.get("z", 0))
        distance = abs(_int(owner_pos.x) - x) + abs(_int(owner_pos.y) - y)
        profile = metadata.get("device_profile") if isinstance(metadata.get("device_profile"), Mapping) else {}
        if _int(owner_pos.z) != z or distance < 2 or distance > max(1, _int(profile.get("range"), 1)):
            return False
        target_eid = getattr(ai, "target_eid", None)
        for candidate_eid in self.sim.entity_ids_in_radius(x, y, z, 1):
            if candidate_eid == owner_eid:
                continue
            candidate_ai = self.sim.ecs.get(AI).get(candidate_eid)
            candidate_role = _key(getattr(candidate_ai, "role", ""))
            if candidate_eid not in {target_eid, getattr(self.sim, "player_eid", None)} and candidate_role != "guard":
                continue
            return _release_remote_payload(self.sim, prop, trigger_eid=owner_eid)
        return False

    def _advance_player_crafting(self):
        live = getattr(self.sim, "live_timeskip", None)
        if not isinstance(live, dict) or _key(live.get("owner")) != "mechanical_crafting":
            return False
        actor_eid = live.get("craft_actor_eid")
        recipe_id = _key(live.get("craft_recipe_id"))
        plan_instance_id = str(live.get("craft_plan_instance_id", "") or "").strip()

        def resolve_completed_build(*, completed_tick=None):
            now = _int(getattr(self.sim, "tick", 0))
            effective_completed_tick = max(now, _int(completed_tick, now))
            inventory = _inventory_for(self.sim, actor_eid)
            plan_entry = inventory.find(instance_id=plan_instance_id) if inventory is not None and plan_instance_id else None
            result = (
                craft_mechanical_recipe(self.sim, actor_eid, plan_entry)
                if plan_entry is not None
                else {"ok": False, "reason": "plan_missing"}
            )
            self.sim.emit(Event(
                "mechanical_crafting_resolved",
                eid=actor_eid,
                recipe_id=recipe_id,
                completed=bool(result.get("ok")),
                reason=str(result.get("reason", "") or "").strip().lower(),
                time_advanced_ticks=max(
                    _int(live.get("elapsed_ticks"), 0),
                    effective_completed_tick - _int(live.get("started_tick"), effective_completed_tick),
                ),
                output_item_id=result.get("output_item_id"),
                output_instance_id=result.get("output_instance_id"),
            ))
            if not result.get("ok") and actor_eid == getattr(self.sim, "player_eid", None):
                _log_player_feedback(
                    self.sim,
                    "The build cannot be completed from the parts still at hand.",
                    kind="craft",
                )
            live.clear()
            return True

        if not bool(live.get("active")):
            if bool(live.get("completed")) and bool(live.get("result_pending")):
                return resolve_completed_build(completed_tick=live.get("target_end_tick"))
            if bool(live.get("interrupted")) or bool(live.get("result_pending")):
                reason = _key(live.get("interruption_reason")) or "interrupted"
                self.sim.emit(Event(
                    "mechanical_crafting_interrupted",
                    eid=actor_eid,
                    recipe_id=recipe_id,
                    reason=reason,
                    elapsed_ticks=_int(live.get("elapsed_ticks"), 0),
                ))
                if actor_eid == getattr(self.sim, "player_eid", None):
                    message = {
                        "position_changed": "You leave the work spot, breaking off construction; the laid-out parts remain yours.",
                        "entity_damaged": "Taking damage breaks off your construction work; the laid-out parts remain yours.",
                        "woken_by_noise": "A nearby disturbance breaks your concentration; the laid-out parts remain yours.",
                        "justice_surrender": "The surrender interrupts your construction work; the laid-out parts remain yours.",
                        "justice_questioning": "The questioning interrupts your construction work; the laid-out parts remain yours.",
                        "justice_identity_check": "The identity check interrupts your construction work; the laid-out parts remain yours.",
                        "actor_detained": "Being detained ends your construction work; the laid-out parts remain yours.",
                        "justice_booking_completed": "Booking ends your construction work; the laid-out parts remain yours.",
                        "player_killed": "Your construction work ends; the laid-out parts remain yours.",
                    }.get(reason, "Your construction work breaks off; the laid-out parts remain yours.")
                    _log_player_feedback(
                        self.sim,
                        message,
                        kind="craft",
                    )
                live.clear()
                return True
            return False
        now = _int(getattr(self.sim, "tick", 0))
        live["elapsed_ticks"] = max(
            0,
            min(_int(live.get("total_ticks"), 0), now - _int(live.get("started_tick"), now)),
        )
        anchor = tuple(live.get("player_anchor", ()) or ())
        pos = self.sim.ecs.get(Position).get(actor_eid)
        if pos is None or len(anchor) < 3 or _coord(pos.x, pos.y, pos.z) != _coord(*anchor[:3]):
            live["active"] = False
            live["interrupted"] = True
            live["result_pending"] = True
            live["interruption_reason"] = "position_changed"
            return self._advance_player_crafting()
        # Systems run before Simulation advances its tick.  Resolve during the
        # final construction tick so the shared live-timeskip coordinator does
        # not mark a legitimately finished build as a pending interruption.
        if now + 1 < _int(live.get("target_end_tick"), now + 1):
            return False
        return resolve_completed_build(completed_tick=now + 1)

    def update(self):
        self._advance_player_crafting()
        now = _int(getattr(self.sim, "tick", 0))
        for prop in tuple(self._live_props()):
            metadata = _device_metadata(prop)
            profile = metadata.get("device_profile") if isinstance(metadata.get("device_profile"), Mapping) else {}
            if property_is_armed_mechanical_device(prop) and _key(profile.get("trigger")) == "remote_signal":
                if self._npc_remote_release(prop):
                    continue
            if property_is_armed_mechanical_device(prop) and _key(profile.get("payload")) == "decoy_noise":
                if now >= _int(metadata.get("next_pulse_tick"), now + 1):
                    self._pulse_decoy(prop)
        if now % 6 == 0:
            self._discover_devices()
