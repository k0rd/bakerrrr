from __future__ import annotations

import random

from game.components import Inventory, Position
from game.items import item_display_name
from game.property_access import property_access_controller
from game.property_keys import property_credential_item_metadata
from game.property_runtime import property_access_level, property_entry_position
from game.run_objectives import evaluate_run_objective

SECURE_ROOM_KINDS = {
    "vault",
    "secure_storage",
    "secure_cage",
    "security_room",
    "count_room",
    "cash_cage",
    "surveillance_room",
    "holding",
    "armored_store",
    "cold_backup",
    "server_room",
    "signals_room",
    "control_room",
    "control_booth",
    "noc",
}
ADMIN_ROOM_KINDS = {
    "office",
    "back_office",
    "front_office",
    "executive_office",
    "executive_suite",
    "manager_office",
    "meeting_room",
    "conference",
    "records",
    "records_room",
    "records_office",
    "dispatch",
    "dispatch_desk",
    "briefing_room",
    "reception",
    "lobby",
    "front_counter",
    "service_counter",
}
WORKROOM_KINDS = {
    "tool_crib",
    "parts",
    "parts_room",
    "parts_store",
    "stock_room",
    "stock_rack",
    "repair_bench",
    "maintenance",
    "service_bay",
    "shop_floor",
    "assembly",
    "assembly_line",
    "sorting_floor",
    "loading_bay",
    "loading_lane",
    "receiving",
    "storage",
    "power_room",
    "racks",
}
FRONT_ROOM_KINDS = {
    "entry",
    "entrance",
    "lobby",
    "reception",
    "waiting",
    "foyer",
    "concourse",
    "public_hall",
    "counter",
    "front_counter",
    "host_desk",
    "service_counter",
    "showroom",
    "sales",
    "gaming_floor",
    "main_floor",
    "dining",
    "seating",
    "common_room",
}


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _text(value):
    return str(value or "").strip()


def _chunk_tuple(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        return (int(value[0]), int(value[1]))
    except (TypeError, ValueError):
        return None


def _manhattan(a, b):
    if not a or not b:
        return 0
    return abs(int(a[0]) - int(b[0])) + abs(int(a[1]) - int(b[1]))


def _risk_score(label):
    label = str(label or "").strip().lower()
    return {"low": 1, "exposed": 2, "hazardous": 3}.get(label, 1)


def _state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits

    state = traits.get("final_operation")
    if not isinstance(state, dict):
        state = {}
        traits["final_operation"] = state

    state["unlocked"] = bool(state.get("unlocked", False))
    state["completed"] = bool(state.get("completed", False))
    state["failed"] = bool(state.get("failed", False))
    state["unlock_tick"] = _safe_int(state.get("unlock_tick"), default=-1)
    state["complete_tick"] = _safe_int(state.get("complete_tick"), default=-1)
    state["fail_tick"] = _safe_int(state.get("fail_tick"), default=-1)
    state["fail_reason"] = str(state.get("fail_reason", "")).strip().lower()
    state["objective_id"] = str(state.get("objective_id", "")).strip().lower()
    state["objective_title"] = str(state.get("objective_title", "")).strip()
    target_chunk = _chunk_tuple(state.get("target_chunk"))
    state["target_chunk"] = target_chunk
    state["target_label"] = str(state.get("target_label", "")).strip()
    state["target_property_id"] = _text(state.get("target_property_id"))
    state["target_property_name"] = _text(state.get("target_property_name"))
    state["target_item_id"] = _text(state.get("target_item_id")).lower()
    state["target_item_name"] = _text(state.get("target_item_name"))
    state["target_item_instance_id"] = _text(state.get("target_item_instance_id"))
    state["target_ground_item_id"] = _text(state.get("target_ground_item_id"))
    state["target_recovered"] = bool(state.get("target_recovered", False))
    state["target_identified_tick"] = _safe_int(state.get("target_identified_tick"), default=-1)
    state["target_recovered_tick"] = _safe_int(state.get("target_recovered_tick"), default=-1)
    summary = state.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    state["summary"] = summary
    return state


def _current_chunk(sim, player_eid):
    pos = sim.ecs.get(Position).get(player_eid) if sim is not None else None
    if pos:
        cx, cy = sim.chunk_coords(pos.x, pos.y)
        return (int(cx), int(cy))
    active = getattr(sim, "active_chunk_coord", None)
    return _chunk_tuple(active) or (0, 0)


def _target_label(sim, chunk):
    cx, cy = chunk
    desc = sim.world.overworld_descriptor(cx, cy)
    interest = sim.world.overworld_interest(cx, cy, descriptor=desc)
    detail = str(interest.get("detail", "")).strip()
    if detail:
        return detail
    settlement = str(desc.get("settlement_name", "")).strip()
    if settlement:
        return settlement
    district = str(desc.get("district_type", "")).strip().replace("_", " ")
    area = str(desc.get("area_type", "")).strip().replace("_", " ")
    if district:
        return f"{area}/{district}" if area else district
    return area or f"chunk {cx},{cy}"


def _player_inventory(sim, player_eid):
    return sim.ecs.get(Inventory).get(player_eid) if sim is not None else None


def _inventory_has_instance(inventory, instance_id):
    instance_id = _text(instance_id)
    if not inventory or not instance_id:
        return False
    return inventory.find(instance_id=instance_id) is not None


def _ground_item_by_instance(sim, instance_id):
    instance_id = _text(instance_id)
    if sim is None or not instance_id:
        return None
    for ground in getattr(sim, "ground_items", {}).values():
        if _text(ground.get("instance_id")) == instance_id:
            return ground
    return None


def _property_chunk(sim, prop):
    if sim is None or not isinstance(prop, dict):
        return None
    metadata = prop.get("metadata")
    if isinstance(metadata, dict):
        chunk = _chunk_tuple(metadata.get("chunk"))
        if chunk:
            return chunk
    try:
        return sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
    except (TypeError, ValueError):
        return None


def _room_kind_at(sim, x, y, z):
    info = sim.structure_at(x, y, z) if hasattr(sim, "structure_at") else None
    if not isinstance(info, dict):
        return ""
    return _text(info.get("room_kind")).lower()


def _room_kind_weight(room_kind):
    if room_kind in SECURE_ROOM_KINDS:
        return 7
    if room_kind in ADMIN_ROOM_KINDS:
        return 5
    if room_kind in WORKROOM_KINDS:
        return 3
    if room_kind in FRONT_ROOM_KINDS:
        return -4
    return 0


def _walkable_inside_tiles(sim, prop):
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    footprint = metadata.get("footprint")
    if not isinstance(footprint, dict):
        return []
    try:
        left = int(footprint.get("left"))
        right = int(footprint.get("right"))
        top = int(footprint.get("top"))
        bottom = int(footprint.get("bottom"))
        base_z = int(prop.get("z", 0))
        floors = max(1, _safe_int(metadata.get("floors"), default=1))
        basement_levels = max(0, _safe_int(metadata.get("basement_levels"), default=0))
    except (TypeError, ValueError):
        return []

    low_z = base_z - basement_levels
    high_z = base_z + floors - 1
    tiles = []
    for z in range(int(low_z), int(high_z) + 1):
        for y in range(top, bottom + 1):
            for x in range(left, right + 1):
                if not sim.tilemap.is_walkable(x, y, z):
                    continue
                covered = sim.property_covering(x, y, z)
                if not (covered and covered.get("id") == prop.get("id")):
                    continue
                tiles.append((x, y, z))
    return tiles


def _pick_retrieval_tile(sim, prop, rng):
    entry = property_entry_position(prop)
    candidates = _walkable_inside_tiles(sim, prop)
    if not candidates:
        return entry

    scored = []
    for tile in candidates:
        room_kind = _room_kind_at(sim, tile[0], tile[1], tile[2])
        if entry:
            dist = abs(int(tile[0]) - int(entry[0])) + abs(int(tile[1]) - int(entry[1])) + (2 * abs(int(tile[2]) - int(entry[2])))
        else:
            dist = 0
        score = (_room_kind_weight(room_kind) * 10) + dist
        scored.append((score, dist, tile))

    scored.sort(key=lambda row: (row[0], row[1], row[2][2], row[2][1], row[2][0]), reverse=True)
    top = [row[2] for row in scored[: min(5, len(scored))]]
    return rng.choice(top) if top else entry


def _target_property_score(sim, prop):
    kind = _text(prop.get("kind")).lower() or "property"
    if kind == "vehicle":
        return None

    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    footprint = metadata.get("footprint") if isinstance(metadata.get("footprint"), dict) else {}
    controller = property_access_controller(sim, prop)
    access_level = property_access_level(prop)
    access_score = {"public": 0, "protected": 8, "restricted": 13}.get(access_level, 0)
    mode = _text(controller.get("credential_mode")).lower() or "mechanical_key"
    mode_score = {"mechanical_key": 0, "badge": 2, "biometric": 5}.get(mode, 0)
    security_tier = max(1, _safe_int(controller.get("security_tier"), default=1))
    required_tier = max(1, _safe_int(controller.get("required_credential_tier"), default=1))
    floors = max(1, _safe_int(metadata.get("floors"), default=1))
    basement_levels = max(0, _safe_int(metadata.get("basement_levels"), default=0))
    area = 0
    if footprint:
        try:
            area = max(0, (int(footprint.get("right")) - int(footprint.get("left")) + 1) * (int(footprint.get("bottom")) - int(footprint.get("top")) + 1))
        except (TypeError, ValueError):
            area = 0

    score = access_score + (security_tier * 3) + (required_tier * 2) + mode_score + floors + basement_levels + min(6, area // 12)
    if kind == "building":
        score += 4
    if prop.get("owner_eid") is not None:
        score += 1
    return score


def _pick_target_property(sim, target_chunk, rng):
    if sim is None or not target_chunk:
        return None

    matching = []
    for prop in getattr(sim, "properties", {}).values():
        if _property_chunk(sim, prop) != target_chunk:
            continue
        score = _target_property_score(sim, prop)
        if score is None:
            continue
        matching.append((score, _text(prop.get("id")), prop))

    if not matching:
        return None

    building_rows = [row for row in matching if _text(row[2].get("kind")).lower() == "building"]
    rows = building_rows or matching
    rows.sort(key=lambda row: (row[0], row[1]), reverse=True)
    top = rows[: min(3, len(rows))]
    return rng.choice(top)[2] if top else None


def _target_item_profile(sim, prop):
    controller = property_access_controller(sim, prop)
    mode = _text(controller.get("credential_mode")).lower() or "mechanical_key"
    label = _text(prop.get("name")) or "Target Site"

    if mode == "badge":
        item_id = "manager_badge"
        metadata = property_credential_item_metadata(
            prop,
            credential_kind="manager_badge",
            holder_role="manager",
            display_name=f"{label} Manager Badge",
        )
    elif mode == "biometric":
        item_id = "cloned_thumb"
        metadata = {
            "display_name": f"{label} Cloned Thumb",
            "property_id": prop.get("id"),
            "property_name": label,
        }
    else:
        item_id = "property_key"
        metadata = property_credential_item_metadata(
            prop,
            credential_kind="mechanical_key",
            holder_role="manager",
            display_name=f"{label} Master Key",
        )
    return {
        "item_id": item_id,
        "item_name": item_display_name(item_id, metadata=metadata),
        "metadata": metadata,
    }


def _seed_retrieval_target(sim, state, prop):
    if sim is None or not isinstance(prop, dict):
        return None

    rng = random.Random(
        f"{getattr(sim, 'seed', 'seed')}:final_op_target:{state.get('objective_id', '')}:{_text(prop.get('id'))}"
    )
    tile = _pick_retrieval_tile(sim, prop, rng=rng)
    if tile is None:
        return None

    profile = _target_item_profile(sim, prop)
    instance_id = state.get("target_item_instance_id") or sim.new_item_instance_id()
    metadata = dict(profile["metadata"])
    metadata.update({
        "final_operation_target": True,
        "final_operation_objective_id": state.get("objective_id", ""),
        "final_operation_property_id": prop.get("id"),
        "final_operation_target_label": state.get("target_label", ""),
        "final_operation_target_chunk": tuple(state.get("target_chunk") or (0, 0)),
    })
    ground_id = sim.register_ground_item(
        profile["item_id"],
        int(tile[0]),
        int(tile[1]),
        int(tile[2]),
        quantity=1,
        owner_eid=prop.get("owner_eid"),
        owner_tag=prop.get("owner_tag"),
        instance_id=instance_id,
        metadata=metadata,
    )
    state["target_property_id"] = _text(prop.get("id"))
    state["target_property_name"] = _text(prop.get("name")) or state["target_property_id"] or "target site"
    state["target_item_id"] = profile["item_id"]
    state["target_item_name"] = profile["item_name"]
    state["target_item_instance_id"] = _text(instance_id)
    state["target_ground_item_id"] = _text(ground_id)
    return {
        "target_property_id": state["target_property_id"],
        "target_property_name": state["target_property_name"],
        "target_item_id": state["target_item_id"],
        "target_item_name": state["target_item_name"],
        "target_item_instance_id": state["target_item_instance_id"],
        "target_ground_item_id": state["target_ground_item_id"],
    }


def _pick_target_chunk(sim, player_eid, rng):
    origin = _current_chunk(sim, player_eid)
    traits = getattr(sim, "world_traits", {}) if sim is not None else {}
    opportunities = traits.get("opportunities", {}) if isinstance(traits, dict) else {}
    active = opportunities.get("active", ()) if isinstance(opportunities, dict) else ()

    scored = []
    seen = set()
    for entry in active if isinstance(active, list) else ():
        if not isinstance(entry, dict):
            continue
        chunk = _chunk_tuple(entry.get("chunk"))
        if not chunk:
            continue
        if chunk in seen:
            continue
        seen.add(chunk)
        dist = _manhattan(origin, chunk)
        if dist < 3:
            continue
        risk = _risk_score(entry.get("risk", "low"))
        source = str(entry.get("source", "unknown")).strip().lower()
        source_bonus = 2 if source in {"overworld_tag", "intel"} else 1
        score = (dist * 4) + (risk * 3) + source_bonus
        scored.append((score, dist, risk, chunk))

    if scored:
        scored.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
        top = scored[:3]
        return rng.choice(top)[3]

    fallback = []
    for radius in range(4, 10):
        for dy in range(-radius, radius + 1):
            dx = radius - abs(dy)
            for sign in (-1, 1):
                cx = origin[0] + (dx * sign)
                cy = origin[1] + dy
                chunk = (cx, cy)
                if chunk in seen:
                    continue
                desc = sim.world.overworld_descriptor(cx, cy)
                interest = sim.world.overworld_interest(cx, cy, descriptor=desc)
                prominence = _safe_int(interest.get("prominence"), default=0)
                area = str(desc.get("area_type", "city")).strip().lower() or "city"
                area_bonus = 2 if area != "city" else 1
                score = (radius * 3) + (prominence * 2) + area_bonus
                fallback.append((score, radius, chunk))
    if fallback:
        fallback.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return rng.choice(fallback[:6])[2]
    return origin


def ensure_final_operation_unlocked(sim, player_eid, objective_eval=None):
    state = _state(sim)
    if state["unlocked"] or state["completed"] or state["failed"]:
        return None

    if not isinstance(objective_eval, dict):
        objective_eval = evaluate_run_objective(sim, player_eid)
    if not objective_eval or not bool(objective_eval.get("completed")):
        return None

    objective_id = str(objective_eval.get("id", "")).strip().lower()
    objective_title = str(objective_eval.get("title", "Run Objective")).strip() or "Run Objective"
    seed = f"{getattr(sim, 'seed', 'seed')}:final_op:{objective_id}:{getattr(sim, 'tick', 0)}"
    rng = random.Random(seed)
    target_chunk = _pick_target_chunk(sim, player_eid, rng=rng)
    target_label = _target_label(sim, target_chunk)

    state["unlocked"] = True
    state["unlock_tick"] = _safe_int(getattr(sim, "tick", 0), default=0)
    state["objective_id"] = objective_id
    state["objective_title"] = objective_title
    state["target_chunk"] = target_chunk
    state["target_label"] = target_label
    state["target_property_id"] = ""
    state["target_property_name"] = ""
    state["target_item_id"] = ""
    state["target_item_name"] = ""
    state["target_item_instance_id"] = ""
    state["target_ground_item_id"] = ""
    state["target_recovered"] = False
    state["target_identified_tick"] = -1
    state["target_recovered_tick"] = -1
    return {
        "objective_id": objective_id,
        "objective_title": objective_title,
        "target_chunk": target_chunk,
        "target_label": target_label,
    }


def active_final_operation_target_property_id(sim):
    state = _state(sim)
    if not state["unlocked"] or state["completed"] or state["failed"]:
        return None
    if state.get("objective_id") != "high_value_retrieval":
        return None
    property_id = _text(state.get("target_property_id"))
    if not property_id or state.get("target_recovered"):
        return None
    return property_id


def sync_final_operation_runtime(sim, player_eid):
    state = _state(sim)
    if not state["unlocked"] or state["completed"] or state["failed"]:
        return None
    if state.get("objective_id") != "high_value_retrieval":
        return None

    inventory = _player_inventory(sim, player_eid)
    target_instance_id = _text(state.get("target_item_instance_id"))
    if target_instance_id and _inventory_has_instance(inventory, target_instance_id):
        state["target_recovered"] = True
        if int(state.get("target_recovered_tick", -1)) < 0:
            state["target_recovered_tick"] = _safe_int(getattr(sim, "tick", 0), default=0)
        return None

    target_chunk = _chunk_tuple(state.get("target_chunk"))
    if not target_chunk:
        return None

    identified = False
    target_prop = sim.properties.get(state.get("target_property_id")) if state.get("target_property_id") else None
    if not isinstance(target_prop, dict):
        rng = random.Random(
            f"{getattr(sim, 'seed', 'seed')}:final_op_site:{state.get('objective_id', '')}:{target_chunk[0]}:{target_chunk[1]}"
        )
        target_prop = _pick_target_property(sim, target_chunk, rng=rng)
        if not isinstance(target_prop, dict):
            return None
        state["target_property_id"] = _text(target_prop.get("id"))
        state["target_property_name"] = _text(target_prop.get("name")) or state["target_property_id"] or "target site"
        if int(state.get("target_identified_tick", -1)) < 0:
            state["target_identified_tick"] = _safe_int(getattr(sim, "tick", 0), default=0)
            identified = True
    else:
        state["target_property_name"] = _text(target_prop.get("name")) or state.get("target_property_name") or state.get("target_property_id") or "target site"

    ground = None
    if state.get("target_ground_item_id"):
        ground = sim.ground_items.get(state.get("target_ground_item_id"))
    if ground is None and target_instance_id:
        ground = _ground_item_by_instance(sim, target_instance_id)
    if ground is not None:
        metadata = ground.get("metadata") if isinstance(ground.get("metadata"), dict) else {}
        state["target_ground_item_id"] = _text(ground.get("ground_item_id"))
        state["target_item_instance_id"] = _text(ground.get("instance_id"))
        state["target_item_id"] = _text(ground.get("item_id")).lower()
        state["target_item_name"] = item_display_name(ground.get("item_id"), metadata=metadata)
    elif not state.get("target_recovered"):
        seeded = _seed_retrieval_target(sim, state, target_prop)
        if seeded is None:
            return None

    if identified:
        return {
            "objective_id": state.get("objective_id", ""),
            "objective_title": state.get("objective_title", ""),
            "target_chunk": target_chunk,
            "target_label": state.get("target_label", ""),
            "target_property_id": state.get("target_property_id", ""),
            "target_property_name": state.get("target_property_name", ""),
            "target_item_id": state.get("target_item_id", ""),
            "target_item_name": state.get("target_item_name", ""),
        }
    return None


def mark_final_operation_target_recovered(sim, player_eid, *, instance_id=None):
    state = _state(sim)
    if not state["unlocked"] or state["completed"] or state["failed"]:
        return None
    if state.get("objective_id") != "high_value_retrieval":
        return None

    target_instance_id = _text(state.get("target_item_instance_id"))
    if not target_instance_id or _text(instance_id) != target_instance_id:
        return None
    if state.get("target_recovered"):
        return None

    inventory = _player_inventory(sim, player_eid)
    if inventory and not _inventory_has_instance(inventory, target_instance_id):
        return None

    state["target_recovered"] = True
    state["target_recovered_tick"] = _safe_int(getattr(sim, "tick", 0), default=0)
    state["target_ground_item_id"] = ""
    return {
        "objective_id": state.get("objective_id", ""),
        "objective_title": state.get("objective_title", ""),
        "target_chunk": _chunk_tuple(state.get("target_chunk")) or (0, 0),
        "target_label": state.get("target_label", ""),
        "target_property_id": state.get("target_property_id", ""),
        "target_property_name": state.get("target_property_name", ""),
        "target_item_id": state.get("target_item_id", ""),
        "target_item_name": state.get("target_item_name", ""),
        "target_recovered_tick": int(state.get("target_recovered_tick", 0)),
    }


def evaluate_final_operation(sim, player_eid):
    state = _state(sim)
    if not state["unlocked"]:
        return None

    target = _chunk_tuple(state.get("target_chunk"))
    current = _current_chunk(sim, player_eid)
    if not target:
        target = current
    distance = _manhattan(current, target)
    unlocked = bool(state["unlocked"])
    completed = bool(state["completed"])
    objective_id = _text(state.get("objective_id")).lower()
    target_property_id = _text(state.get("target_property_id"))
    target_property_name = _text(state.get("target_property_name"))
    target_item_name = _text(state.get("target_item_name"))

    if completed:
        summary_line = "Final operation complete."
        next_step = "Run completed. Review summary."
    elif state["failed"]:
        summary_line = "Final operation failed."
        next_step = "Run failed."
    elif objective_id == "high_value_retrieval":
        label = target_property_name or "target site"
        item_label = target_item_name or "target asset"
        if state.get("target_recovered"):
            summary_line = f"Final operation: recovered {item_label}."
            next_step = "Hold the target. Run will conclude."
        elif target_property_id:
            if distance > 0:
                summary_line = (
                    f"Final operation: recover {item_label} from {label} "
                    f"in chunk ({target[0]},{target[1]}) [{state.get('target_label', 'target')}] ({distance}c)."
                )
                next_step = f"Travel to target chunk and hit {label}."
            elif str(getattr(sim, "zoom_mode", "city")).strip().lower() == "overworld":
                summary_line = f"Final operation: recover {item_label} from {label}."
                next_step = f"Enter local area and hit {label}."
            else:
                pos = sim.ecs.get(Position).get(player_eid) if sim is not None else None
                covered = sim.property_covering(pos.x, pos.y, pos.z) if pos and hasattr(sim, "property_covering") else None
                if covered and covered.get("id") == target_property_id:
                    next_step = f"Recover {item_label} from inside {label}."
                else:
                    next_step = f"Enter {label} and recover {item_label}."
                summary_line = f"Final operation: recover {item_label} from {label}."
        else:
            summary_line = (
                f"Final operation: reach chunk ({target[0]},{target[1]}) "
                f"[{state.get('target_label', 'target')}] and identify the site ({distance}c)."
            )
            next_step = "Travel to target chunk and identify the retrieval site."
    else:
        summary_line = (
            f"Final operation: reach chunk ({target[0]},{target[1]}) "
            f"[{state.get('target_label', 'target')}] ({distance}c)."
        )
        next_step = "Travel to target chunk and enter local area."

    return {
        "unlocked": unlocked,
        "completed": completed,
        "target_chunk": target,
        "target_label": state.get("target_label", ""),
        "target_property_id": target_property_id,
        "target_property_name": target_property_name,
        "target_item_name": target_item_name,
        "target_recovered": bool(state.get("target_recovered")),
        "distance": distance,
        "summary_line": summary_line,
        "next_step": next_step,
    }


def _summary_lines(sim, player_eid, state):
    traits = getattr(sim, "world_traits", {}) if sim is not None else {}
    opportunities = traits.get("opportunities", {}) if isinstance(traits, dict) else {}
    run_pressure = traits.get("run_pressure", {}) if isinstance(traits, dict) else {}
    objective_progress = traits.get("objective_progress", {}) if isinstance(traits, dict) else {}
    visited_map = getattr(sim, "overworld_visit_state_by_eid", {})
    visited = visited_map.get(player_eid, set()) if isinstance(visited_map, dict) else set()
    if not isinstance(visited, (set, list, tuple)):
        visited = set()

    completed_opps = opportunities.get("completed", ()) if isinstance(opportunities, dict) else ()
    pressure_peak = _safe_int(run_pressure.get("peak_attention"), default=0) if isinstance(run_pressure, dict) else 0
    reserve_bonus = _safe_int(objective_progress.get("reserve_bonus_credits"), default=0) if isinstance(objective_progress, dict) else 0
    intel_bonus = _safe_int(objective_progress.get("intel_marks"), default=0) if isinstance(objective_progress, dict) else 0
    network_bonus = _safe_int(objective_progress.get("network_marks"), default=0) if isinstance(objective_progress, dict) else 0

    lines = [
        f"Final operation complete: {state.get('objective_title', 'Run Objective')}.",
    ]
    if state.get("objective_id") == "high_value_retrieval":
        item_name = _text(state.get("target_item_name")) or "target asset"
        property_name = _text(state.get("target_property_name")) or _text(state.get("target_label")) or "target site"
        lines.append(f"Recovered target: {item_name} from {property_name}.")
    lines.extend([
        f"Run ticks: {_safe_int(getattr(sim, 'tick', 0), default=0)}.",
        f"Travel footprint: {len(visited)} chunks visited.",
        f"Opportunities completed: {len(completed_opps) if isinstance(completed_opps, list) else 0}.",
        f"Peak attention: {pressure_peak}.",
        f"Objective bonus track: reserve {reserve_bonus}, network {network_bonus}, intel {intel_bonus}.",
    ])
    return lines


def _failure_summary_lines(sim, player_eid, state):
    traits = getattr(sim, "world_traits", {}) if sim is not None else {}
    opportunities = traits.get("opportunities", {}) if isinstance(traits, dict) else {}
    run_pressure = traits.get("run_pressure", {}) if isinstance(traits, dict) else {}
    visited_map = getattr(sim, "overworld_visit_state_by_eid", {})
    visited = visited_map.get(player_eid, set()) if isinstance(visited_map, dict) else set()
    if not isinstance(visited, (set, list, tuple)):
        visited = set()

    completed_opps = opportunities.get("completed", ()) if isinstance(opportunities, dict) else ()
    pressure_peak = _safe_int(run_pressure.get("peak_attention"), default=0) if isinstance(run_pressure, dict) else 0
    fail_reason = str(state.get("fail_reason", "")).strip().replace("_", " ")
    reason_suffix = f" ({fail_reason})" if fail_reason else ""

    lines = [
        f"Final operation failed: {state.get('objective_title', 'Run Objective')}{reason_suffix}.",
    ]
    if state.get("objective_id") == "high_value_retrieval":
        item_name = _text(state.get("target_item_name")) or "target asset"
        property_name = _text(state.get("target_property_name")) or _text(state.get("target_label")) or "target site"
        lines.append(f"Target missed: {item_name} from {property_name}.")
    lines.extend([
        f"Run ticks: {_safe_int(getattr(sim, 'tick', 0), default=0)}.",
        f"Travel footprint: {len(visited)} chunks visited.",
        f"Opportunities completed: {len(completed_opps) if isinstance(completed_opps, list) else 0}.",
        f"Peak attention: {pressure_peak}.",
    ])
    return lines


def try_complete_final_operation(sim, player_eid):
    state = _state(sim)
    if not state["unlocked"] or state["completed"] or state["failed"]:
        return None

    if state.get("objective_id") == "high_value_retrieval":
        target_instance_id = _text(state.get("target_item_instance_id"))
        if target_instance_id and _inventory_has_instance(_player_inventory(sim, player_eid), target_instance_id):
            state["target_recovered"] = True
            if int(state.get("target_recovered_tick", -1)) < 0:
                state["target_recovered_tick"] = _safe_int(getattr(sim, "tick", 0), default=0)
        if not state.get("target_recovered"):
            return None
    else:
        target = _chunk_tuple(state.get("target_chunk"))
        current = _current_chunk(sim, player_eid)
        if not target or not current or target != current:
            return None
        if str(getattr(sim, "zoom_mode", "city")).strip().lower() == "overworld":
            return None
    target = _chunk_tuple(state.get("target_chunk")) or _current_chunk(sim, player_eid)

    state["completed"] = True
    state["complete_tick"] = _safe_int(getattr(sim, "tick", 0), default=0)
    lines = _summary_lines(sim, player_eid, state)
    state["summary"] = {
        "lines": list(lines),
        "tick": int(state["complete_tick"]),
    }
    return {
        "objective_id": state.get("objective_id", ""),
        "objective_title": state.get("objective_title", ""),
        "target_chunk": target,
        "target_label": state.get("target_label", ""),
        "target_property_id": state.get("target_property_id", ""),
        "target_property_name": state.get("target_property_name", ""),
        "target_item_name": state.get("target_item_name", ""),
        "complete_tick": int(state["complete_tick"]),
        "summary_lines": lines,
    }


def try_fail_final_operation(sim, player_eid, reason=""):
    state = _state(sim)
    if not state["unlocked"] or state["completed"] or state["failed"]:
        return None

    state["failed"] = True
    state["fail_tick"] = _safe_int(getattr(sim, "tick", 0), default=0)
    state["fail_reason"] = str(reason or "").strip().lower()
    lines = _failure_summary_lines(sim, player_eid, state)
    state["summary"] = {
        "lines": list(lines),
        "tick": int(state["fail_tick"]),
        "failed": True,
    }
    return {
        "objective_id": state.get("objective_id", ""),
        "objective_title": state.get("objective_title", ""),
        "target_chunk": _chunk_tuple(state.get("target_chunk")) or (0, 0),
        "target_label": state.get("target_label", ""),
        "fail_tick": int(state["fail_tick"]),
        "fail_reason": state.get("fail_reason", ""),
        "summary_lines": lines,
    }
