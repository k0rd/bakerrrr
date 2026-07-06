"""Bounded loaded-world NPC/faction drone seeding and use."""

from __future__ import annotations

import random

from engine.events import Event

from game.components import (
    AI,
    Collider,
    CreatureIdentity,
    DroneState,
    JusticeProfile,
    NPCWill,
    Occupation,
    OrganizationAffiliations,
    OrganizationProfile,
    Position,
    Render,
    Vitality,
)
from game.drone_combat import drone_weapon_status
from game.drone_runtime import (
    deployed_drone_render_spec,
    drone_profile_for_item,
    first_open_drone_deploy_tile,
)
from game.items import ITEM_CATALOG
from game.system_support.combat_targeting_runtime import _entity_is_weapon_targetable


DRONE_FACTION_MAX_PER_CHUNK = 2
DRONE_FACTION_SOURCE_CONTEXT = "npc_faction_seed"
ARMED_SECURITY_KINDS = frozenset({"justice", "security", "corporate", "gang", "cult", "bodyguard", "enforcer"})
UTILITY_KINDS = frozenset({"scout", "rural", "civic", "utility"})


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _clean(value):
    return str(value or "").strip().lower()


def _runtime(sim):
    state = getattr(sim, "drone_faction_runtime", None)
    if not isinstance(state, dict):
        state = {}
        setattr(sim, "drone_faction_runtime", state)
    seeded = state.get("seeded_chunks")
    if not isinstance(seeded, set):
        seeded = set(seeded or ())
        state["seeded_chunks"] = seeded
    catchup = state.get("catchup_done_chunks")
    if not isinstance(catchup, set):
        catchup = set(catchup or ())
        state["catchup_done_chunks"] = catchup
    return state


def _chunk_key(sim, value):
    if isinstance(value, (list, tuple)) and len(value) >= 2:
        return (_int(value[0]), _int(value[1]))
    return None


def _loaded_chunks(sim):
    chunk_detail = getattr(sim, "chunk_detail", None)
    if isinstance(chunk_detail, dict) and chunk_detail:
        return tuple(
            key
            for key, detail in sorted(chunk_detail.items())
            if _chunk_key(sim, key) is not None and _clean(detail) != "unloaded"
        )
    positions = sim.ecs.get(Position) if getattr(sim, "ecs", None) is not None else {}
    return tuple(sorted({sim.chunk_coords(pos.x, pos.y) for pos in positions.values()}))


def _entity_chunk(sim, eid):
    pos = sim.ecs.get(Position).get(eid)
    if pos is None:
        return None
    return sim.chunk_coords(pos.x, pos.y)


def _org_tokens(sim, eid):
    tokens = set()
    affiliations = sim.ecs.get(OrganizationAffiliations).get(eid)
    profiles = sim.ecs.get(OrganizationProfile)
    memberships = getattr(affiliations, "memberships", {}) if affiliations is not None else {}
    if isinstance(memberships, dict):
        for org_eid, row in memberships.items():
            if not isinstance(row, dict) or not bool(row.get("active", True)):
                continue
            tokens.add(_clean(row.get("role")))
            tokens.add(_clean(row.get("kind")))
            tokens.add(_clean(row.get("title")))
            profile = profiles.get(org_eid)
            if profile is not None:
                tokens.add(_clean(getattr(profile, "kind", "")))
                tokens.update(_clean(tag) for tag in getattr(profile, "tags", set()) or set())
    return {token for token in tokens if token}


def _owner_kind(sim, eid):
    ai = sim.ecs.get(AI).get(eid)
    occupation = sim.ecs.get(Occupation).get(eid)
    justice = sim.ecs.get(JusticeProfile).get(eid)
    role = _clean(getattr(ai, "role", ""))
    career = _clean(getattr(occupation, "career", ""))
    tokens = {role, career}
    tokens.update(_org_tokens(sim, eid))
    text = " ".join(sorted(token for token in tokens if token))

    if justice is not None or any(token in text for token in ("cop", "police", "peace_officer", "justice", "sheriff")):
        return "justice"
    if any(token in text for token in ("security", "guard", "corporate", "corp")):
        return "security"
    if "bodyguard" in text:
        return "bodyguard"
    if any(token in text for token in ("enforcer", "gang")):
        return "gang"
    if "cult" in text:
        return "cult"
    if "scout" in text:
        return "scout"
    if any(token in text for token in ("rural", "ranch", "farm", "hunter")):
        return "rural"
    if any(token in text for token in ("civic", "municipal", "utility")):
        return "civic"
    return ""


def owner_drone_seed_eligible(sim, eid):
    if eid == getattr(sim, "player_eid", None):
        return False
    if sim.ecs.get(Position).get(eid) is None:
        return False
    kind = _owner_kind(sim, eid)
    return kind in ARMED_SECURITY_KINDS or kind in UTILITY_KINDS


def _owner_tag_for_kind(kind):
    if kind in {"justice", "security"}:
        return "justice"
    if kind in {"gang", "cult", "bodyguard", "enforcer"}:
        return kind
    if kind in {"scout", "rural", "civic", "utility"}:
        return kind
    return "private_security"


def _loadout_for_kind(kind, rng):
    kind = _clean(kind)
    if kind in {"justice", "security", "corporate"}:
        return {
            "chassis_item_id": "drone_chassis_e",
            "power_center_item_id": "drone_power_core_mk5",
            "battery_item_id": "drone_battery_industrial",
            "modules": [
                "drone_camera_module",
                "drone_remote_receiver_module",
                "drone_follow_procedure_module",
                "drone_pistol_module",
                "drone_ammo_rack_module",
            ],
            "procedure_key": "follow",
        }
    if kind in {"gang", "cult", "bodyguard", "enforcer"}:
        return {
            "chassis_item_id": "drone_chassis_e",
            "power_center_item_id": "drone_power_core_mk5",
            "battery_item_id": "drone_battery_heavy",
            "modules": [
                "drone_camera_module",
                "drone_remote_receiver_module",
                "drone_follow_procedure_module",
                "drone_pistol_module",
                "drone_ammo_rack_module",
            ],
            "procedure_key": "follow",
        }
    chassis = "drone_chassis_b"
    procedure = "mapping" if rng.randint(0, 1) else "follow"
    modules = [
        "drone_camera_module",
        "drone_radio_module",
        "drone_mapping_procedure_module",
    ]
    if procedure == "follow":
        modules = [
            "drone_camera_module",
            "drone_radio_module",
            "drone_follow_procedure_module",
        ]
    return {
        "chassis_item_id": chassis,
        "power_center_item_id": "drone_power_core_mk2",
        "battery_item_id": "drone_battery_standard",
        "modules": modules,
        "procedure_key": procedure,
    }


def _source_instance_id(sim, chunk, owner_eid, kind, ordinal):
    return f"npc-drone:{getattr(sim, 'seed', 0)}:{chunk[0]}:{chunk[1]}:{owner_eid}:{kind}:{ordinal}"


def _existing_seeded_drone_for_owner(sim, owner_eid):
    for _drone_eid, state in sim.ecs.get(DroneState).items():
        if getattr(state, "owner_eid", None) == owner_eid and _clean(getattr(state, "source_metadata", {}).get("source_context")) == DRONE_FACTION_SOURCE_CONTEXT:
            return True
    return False


def _faction_drone_count_in_chunk(sim, chunk):
    positions = sim.ecs.get(Position)
    count = 0
    for eid, state in sim.ecs.get(DroneState).items():
        if _clean(getattr(state, "source_metadata", {}).get("source_context")) != DRONE_FACTION_SOURCE_CONTEXT:
            continue
        pos = positions.get(eid)
        if pos is not None and sim.chunk_coords(pos.x, pos.y) == chunk:
            count += 1
    return count


def _spawn_seeded_drone(sim, owner_eid, chunk, ordinal):
    pos = sim.ecs.get(Position).get(owner_eid)
    if pos is None:
        return None
    deploy_tile = first_open_drone_deploy_tile(sim, pos.x, pos.y, pos.z)
    if deploy_tile is None:
        return None
    kind = _owner_kind(sim, owner_eid)
    rng = random.Random(f"{getattr(sim, 'seed', 0)}:drone-faction:{chunk}:{owner_eid}:{kind}:{ordinal}")
    metadata = _loadout_for_kind(kind, rng)
    owner_tag = _owner_tag_for_kind(kind)
    source_instance_id = _source_instance_id(sim, chunk, owner_eid, kind, ordinal)
    metadata.update({
        "source_context": DRONE_FACTION_SOURCE_CONTEXT,
        "source_item_instance_id": source_instance_id,
        "owner_eid": owner_eid,
        "owner_tag": owner_tag,
        "controller_eid": owner_eid,
        "controller_tag": owner_tag,
        "legal_owner_tag": owner_tag,
        "faction_id": owner_tag,
        "mode": "deployed",
        "home": (int(pos.x), int(pos.y), int(pos.z)),
        "target_eid": owner_eid if metadata.get("procedure_key") == "follow" else None,
        "paint": {
            "primary_color": "black" if kind in {"gang", "cult", "bodyguard", "enforcer"} else "white",
            "secondary_color": "red" if kind in {"justice", "security"} else "green",
            "accent_color": "red" if kind in {"justice", "security"} else "green",
        },
    })
    state = DroneState.from_packed_metadata(
        metadata,
        source_item_instance_id=source_instance_id,
        owner_eid=owner_eid,
        owner_tag=owner_tag,
        controller_eid=owner_eid,
        controller_tag=owner_tag,
        deployed_tick=getattr(sim, "tick", 0),
        item_catalog=ITEM_CATALOG,
    )
    state.mode = "deployed"
    state.home = (int(pos.x), int(pos.y), int(pos.z))
    chassis_profile = drone_profile_for_item(state.chassis_item_id, item_catalog=ITEM_CATALOG)
    state.range_limit = int(max(0, _int(chassis_profile.get("base_range"), getattr(state, "range_limit", 0) or 0)))
    state.source_metadata["range_limit"] = int(state.range_limit)
    if state.procedure_key == "follow":
        state.target_eid = owner_eid
    state.source_metadata["source_context"] = DRONE_FACTION_SOURCE_CONTEXT
    state.source_metadata["source_item_instance_id"] = source_instance_id
    render_spec = deployed_drone_render_spec(state.source_metadata, item_catalog=ITEM_CATALOG)

    drone_eid = sim.ecs.create()
    x, y, z = deploy_tile
    sim.ecs.add(drone_eid, Position(x, y, z))
    sim.ecs.add(drone_eid, Render(render_spec["glyph"], render_spec["color"], semantic_id="entity_drone"))
    sim.ecs.add(drone_eid, CreatureIdentity(taxonomy_class="machine", common_name=f"{state.chassis_class}-class drone"))
    sim.ecs.add(drone_eid, Collider(blocks=True))
    sim.ecs.add(drone_eid, Vitality(max_hp=state.hull_hp_max, hp=state.hull_hp))
    sim.ecs.add(drone_eid, state)
    sim.tilemap.add_entity(drone_eid, x, y, z)
    sim.emit(Event(
        "drone_deployed",
        eid=owner_eid,
        controller_eid=owner_eid,
        owner_eid=owner_eid,
        owner_tag=owner_tag,
        drone_eid=drone_eid,
        source_item_instance_id=source_instance_id,
        chassis_class=state.chassis_class,
        source_context=DRONE_FACTION_SOURCE_CONTEXT,
        x=x,
        y=y,
        z=z,
    ))
    return drone_eid


def seed_loaded_faction_drones(sim):
    state = _runtime(sim)
    seeded = state["seeded_chunks"]
    for chunk in _loaded_chunks(sim):
        if chunk in seeded:
            continue
        if _faction_drone_count_in_chunk(sim, chunk) >= DRONE_FACTION_MAX_PER_CHUNK:
            seeded.add(chunk)
            continue
        owner_candidates = []
        for eid in sorted(sim.entity_ids_in_chunk(chunk) if hasattr(sim, "entity_ids_in_chunk") else sim.ecs.get(Position).keys()):
            if not owner_drone_seed_eligible(sim, eid):
                continue
            if _existing_seeded_drone_for_owner(sim, eid):
                continue
            owner_candidates.append(eid)
        if not owner_candidates:
            continue
        spawned = 0
        for ordinal, owner_eid in enumerate(owner_candidates):
            if _faction_drone_count_in_chunk(sim, chunk) >= DRONE_FACTION_MAX_PER_CHUNK:
                break
            if _spawn_seeded_drone(sim, owner_eid, chunk, ordinal) is not None:
                spawned += 1
        if spawned:
            seeded.add(chunk)
            sim.emit(Event("drone_faction_seeded", chunk=chunk, count=spawned))


def _owner_active_target(sim, owner_eid):
    ai = sim.ecs.get(AI).get(owner_eid)
    will = sim.ecs.get(NPCWill).get(owner_eid)
    for source in (ai, will):
        target_eid = getattr(source, "target_eid", None) if source is not None else None
        if target_eid is None or target_eid == owner_eid:
            continue
        if not _entity_is_weapon_targetable(sim, target_eid, current_tick=getattr(sim, "tick", None)):
            continue
        return target_eid
    return None


def tick_faction_drone_combat(sim, drone_system):
    positions = sim.ecs.get(Position)
    for drone_eid, state in list(sim.ecs.get(DroneState).items()):
        if _clean(getattr(state, "source_metadata", {}).get("source_context")) != DRONE_FACTION_SOURCE_CONTEXT:
            continue
        owner_eid = getattr(state, "owner_eid", None) or getattr(state, "controller_eid", None)
        if owner_eid is None:
            continue
        owner_pos = positions.get(owner_eid)
        drone_pos = positions.get(drone_eid)
        if owner_pos is None or drone_pos is None or int(owner_pos.z) != int(drone_pos.z):
            continue
        target_eid = _owner_active_target(sim, owner_eid)
        if target_eid is None:
            continue
        status = drone_weapon_status(state, item_catalog=ITEM_CATALOG)
        if not status.get("armed"):
            continue
        result = drone_system.fire_drone_weapon(
            owner_eid,
            drone_eid,
            target_eid=target_eid,
            weapon_kind=status.get("primary_weapon") or "auto",
            require_remote=True,
            require_camera=True,
            consume_turn=False,
        )
        if result.get("ok"):
            state.source_metadata["npc_faction_last_fire_tick"] = int(getattr(sim, "tick", 0) or 0)


def catch_up_faction_drones_for_chunk(sim, drone_system, chunk):
    chunk = _chunk_key(sim, chunk)
    if chunk is None:
        return 0
    state = _runtime(sim)
    catchup = state["catchup_done_chunks"]
    key = (chunk[0], chunk[1], int(getattr(sim, "tick", 0) or 0))
    if key in catchup:
        return 0
    count = 0
    for drone_eid, drone_state in list(sim.ecs.get(DroneState).items()):
        if _clean(getattr(drone_state, "source_metadata", {}).get("source_context")) != DRONE_FACTION_SOURCE_CONTEXT:
            continue
        if _entity_chunk(sim, drone_eid) != chunk:
            continue
        if getattr(drone_state, "owner_eid", None) == getattr(sim, "player_eid", None):
            continue
        result = drone_system.run_drone_procedure(drone_eid)
        if result.get("ok"):
            count += 1
    catchup.add(key)
    return count


__all__ = [
    "DRONE_FACTION_MAX_PER_CHUNK",
    "DRONE_FACTION_SOURCE_CONTEXT",
    "catch_up_faction_drones_for_chunk",
    "owner_drone_seed_eligible",
    "seed_loaded_faction_drones",
    "tick_faction_drone_combat",
]
