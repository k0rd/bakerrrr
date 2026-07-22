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
from game.drone_programs import (
    activate_drone_program,
    built_in_drone_program,
    installed_drone_program_cards,
)
from game.drone_runtime import (
    deployed_drone_render_spec,
    drone_deploy_tile_is_threshold,
    drone_deploy_tile_open,
    drone_profile_for_item,
)
from game.items import ITEM_CATALOG
from game.organization_production import (
    organization_manufacturing_identity,
    organization_manufacturing_modifiers,
)
from game.organization_supply import drone_supply_agreement_for_actor
from game.system_support.combat_targeting_runtime import _entity_is_weapon_targetable


DRONE_FACTION_MAX_PER_CHUNK = 2
DRONE_FACTION_SOURCE_CONTEXT = "npc_faction_seed"
NPC_DRONE_BEHAVIOR_POLICY_VERSION = 2
NPC_DRONE_RETASK_COOLDOWN = 12
NPC_DRONE_REPEAT_ACTION_COOLDOWN = 24
ARMED_SECURITY_KINDS = frozenset({"justice", "security", "corporate", "gang", "cult", "bodyguard", "enforcer"})
UTILITY_KINDS = frozenset({"scout", "rural", "civic", "utility"})
NPC_DRONE_DANGER_INTENTS = frozenset({"chasing", "ejecting_target", "investigating", "protecting"})
NPC_DRONE_WITHDRAWAL_INTENTS = frozenset({
    "evading_authority",
    "leaving_property",
    "seeking_medical_aid",
    "seeking_safe_spot",
    "seeking_safety",
    "seeking_shelter",
})
NPC_DRONE_COVERT_INTENTS = frozenset({"casing_target", "committing_property_crime", "rendezvousing_crew"})
NPC_DRONE_WATCH_INTENTS = frozenset({"helping_victim", "reporting_incident", "warning"})
DRONE_FACTION_SEED_CHANCE_BY_KIND = {
    "justice": 0.65,
    "security": 0.55,
    "corporate": 0.55,
    "gang": 0.42,
    "cult": 0.38,
    "bodyguard": 0.60,
    "enforcer": 0.55,
    "scout": 0.30,
    "rural": 0.20,
    "civic": 0.30,
    "utility": 0.28,
}

_TRANSITORY_ROOM_TOKENS = frozenset({"access", "corridor", "entry", "hall", "lobby", "passage", "stair"})
_CARDINAL_OFFSETS = ((0, -1), (1, 0), (0, 1), (-1, 0))


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
    if "bodyguard" in text:
        return "bodyguard"
    if "enforcer" in text:
        return "enforcer"
    if "gang" in text:
        return "gang"
    if "cult" in text:
        return "cult"
    if any(token in text for token in ("corporate", "corp")):
        return "corporate"
    if any(token in text for token in ("security", "guard", "corporate", "corp")):
        return "security"
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


def _roll_weighted_choice(rng, choices):
    total = sum(max(0, int(weight)) for weight, _value in choices)
    if total <= 0:
        return choices[-1][1]
    roll = rng.randrange(total)
    cursor = 0
    for weight, value in choices:
        cursor += max(0, int(weight))
        if roll < cursor:
            return value
    return choices[-1][1]


def _observer_loadout(chassis="a", *, procedure="hold"):
    chassis = _clean(chassis) or "a"
    if chassis == "b":
        return {
            "chassis_item_id": "drone_chassis_b",
            "power_center_item_id": "drone_power_core_mk3",
            "battery_item_id": "drone_battery_standard",
            "modules": [
                "drone_camera_module",
                "drone_radio_module",
                "drone_follow_procedure_module",
                "drone_mapping_procedure_module",
            ],
            "procedure_key": "follow" if procedure == "follow" else "mapping",
        }
    return {
        "chassis_item_id": "drone_chassis_a",
        "power_center_item_id": "drone_power_core_mk1",
        "battery_item_id": "drone_battery_light",
        "modules": [
            "drone_camera_module",
            "drone_follow_procedure_module",
        ],
        "procedure_key": "follow",
    }


def _armed_loadout(chassis="c", *, armor=False, radio=False, elite_sensor=False):
    chassis = _clean(chassis) or "c"
    if chassis == "d":
        modules = [
            "drone_camera_module",
            "drone_remote_receiver_module",
            "drone_follow_procedure_module",
            "drone_pistol_module",
            "drone_ammo_rack_module",
        ]
        if radio:
            modules.insert(1, "drone_radio_module")
        if armor:
            modules.append("drone_armor_shell_module")
        return {
            "chassis_item_id": "drone_chassis_d",
            "power_center_item_id": "drone_power_core_mk4",
            "battery_item_id": "drone_battery_heavy",
            "modules": modules,
            "procedure_key": "hold",
        }
    if chassis == "e":
        modules = [
            "drone_camera_module",
            "drone_radio_module",
            "drone_remote_receiver_module",
            "drone_follow_procedure_module",
            "drone_pistol_module",
            "drone_ammo_rack_module",
            "drone_armor_shell_module",
        ]
        if elite_sensor:
            modules.append("drone_radar_module")
        return {
            "chassis_item_id": "drone_chassis_e",
            "power_center_item_id": "drone_power_core_mk5",
            "battery_item_id": "drone_battery_industrial",
            "modules": modules,
            "procedure_key": "hold",
        }
    return {
        "chassis_item_id": "drone_chassis_c",
        "power_center_item_id": "drone_power_core_mk4",
        "battery_item_id": "drone_battery_standard",
        "modules": [
            "drone_camera_module",
            "drone_remote_receiver_module",
            "drone_follow_procedure_module",
            "drone_pistol_module",
            "drone_ammo_rack_module",
        ],
        "procedure_key": "hold",
    }


def _covert_loadout():
    return {
        "chassis_item_id": "drone_chassis_b",
        "power_center_item_id": "drone_power_core_mk3",
        "battery_item_id": "drone_battery_standard",
        "modules": [
            "drone_camera_module",
            "drone_speaker_module",
            "drone_alarm_probe_module",
            "drone_follow_procedure_module",
            "drone_mapping_procedure_module",
        ],
        "procedure_key": "follow",
    }


def _utility_cargo_loadout():
    return {
        "chassis_item_id": "drone_chassis_b",
        "power_center_item_id": "drone_power_core_mk3",
        "battery_item_id": "drone_battery_standard",
        "modules": [
            "drone_camera_module",
            "drone_radio_module",
            "drone_cargo_clamp_module",
            "drone_follow_procedure_module",
            "drone_mapping_procedure_module",
        ],
        "procedure_key": "logistics",
    }


def _loadout_for_kind(kind, rng):
    kind = _clean(kind)
    if kind == "justice":
        tier = _roll_weighted_choice(rng, ((52, "b"), (34, "c"), (13, "d"), (1, "e")))
        if tier == "b":
            return _observer_loadout("b", procedure="follow")
        if tier == "d":
            return _armed_loadout("d", armor=True, radio=True)
        if tier == "e":
            return _armed_loadout("e", elite_sensor=True)
        return _armed_loadout("c")
    if kind in {"security", "corporate"}:
        tier = _roll_weighted_choice(rng, ((42, "a"), (36, "b"), (19, "c"), (3, "d")))
        if tier == "a":
            return _observer_loadout("a")
        if tier == "b":
            return _observer_loadout("b", procedure="follow")
        if tier == "d":
            return _armed_loadout("d", armor=True, radio=(kind == "corporate"))
        return _armed_loadout("c")
    if kind in {"gang", "cult", "bodyguard", "enforcer"}:
        tier = _roll_weighted_choice(rng, ((35, "a"), (42, "b"), (21, "c"), (2, "d")))
        if kind in {"bodyguard", "enforcer"}:
            tier = _roll_weighted_choice(rng, ((20, "b"), (72, "c"), (8, "d")))
        if tier == "a":
            return _observer_loadout("a")
        if tier == "b":
            if kind in {"gang", "cult"} and rng.randrange(3) == 0:
                return _covert_loadout()
            return _observer_loadout("b", procedure="follow")
        if tier == "d":
            return _armed_loadout("d", armor=(kind in {"bodyguard", "enforcer"}))
        return _armed_loadout("c")
    chassis = "drone_chassis_a" if rng.random() < 0.62 else "drone_chassis_b"
    core = "drone_power_core_mk1" if chassis == "drone_chassis_a" else "drone_power_core_mk2"
    battery = "drone_battery_light" if chassis == "drone_chassis_a" else "drone_battery_standard"
    procedure = "mapping" if rng.randint(0, 1) else "follow"
    if chassis == "drone_chassis_b" and rng.randrange(4) == 0:
        return _utility_cargo_loadout()
    if chassis == "drone_chassis_b":
        return _observer_loadout("b", procedure=procedure)
    modules = [
        "drone_sonar_module",
        "drone_mapping_procedure_module",
    ]
    return {
        "chassis_item_id": chassis,
        "power_center_item_id": core,
        "battery_item_id": battery,
        "modules": modules,
        "procedure_key": "mapping",
    }


def _actor_organization_eid(sim, actor_eid):
    affiliations = sim.ecs.get(OrganizationAffiliations).get(actor_eid)
    memberships = getattr(affiliations, "memberships", {}) if affiliations is not None else {}
    ranked = []
    if isinstance(memberships, dict):
        for org_eid, row in memberships.items():
            if not isinstance(row, dict) or not bool(row.get("active", True)):
                continue
            try:
                org_eid = int(org_eid)
            except (TypeError, ValueError):
                continue
            ranked.append((0 if bool(row.get("primary", False)) else 1, int(row.get("authority_rank", 99) or 99), org_eid))
    return sorted(ranked)[0][2] if ranked else None


def _supplied_loadout_for_doctrine(kind, doctrine, rng, fallback):
    """Let a supplier's durable doctrine shape, not replace, receiver intent."""

    doctrine = _clean(doctrine).replace("_", " ")
    if kind not in {"gang", "cult", "bodyguard", "enforcer"}:
        return fallback
    if doctrine in {"visible deterrence", "interdiction", "close protection"}:
        return _armed_loadout("c", armor=doctrine == "close protection")
    if doctrine == "quiet survey":
        return _covert_loadout()
    if doctrine in {"courier", "salvage utility"}:
        return _utility_cargo_loadout()
    if doctrine in {"escort", "watchful"}:
        return _observer_loadout("b", procedure="follow")
    return fallback


def _loadout_module_ids(metadata):
    ids = set()
    if not isinstance(metadata, dict):
        return ids
    for module in tuple(metadata.get("modules", ()) or ()):
        if isinstance(module, dict):
            item_id = module.get("item_id")
        else:
            item_id = module
        item_id = _clean(item_id)
        if item_id:
            ids.add(item_id)
    return ids


def _seeded_task_for_loadout(kind, metadata, rng):
    kind = _clean(kind)
    procedure_key = _clean((metadata or {}).get("procedure_key"))
    module_ids = _loadout_module_ids(metadata)
    armed = bool({"drone_pistol_module", "drone_flame_nozzle_module"} & module_ids)
    has_radio = bool({"drone_radio_module", "drone_comms_module"} & module_ids)
    has_mapping_procedure = "drone_mapping_procedure_module" in module_ids
    has_follow_procedure = "drone_follow_procedure_module" in module_ids
    has_cargo = "drone_cargo_clamp_module" in module_ids

    if armed:
        if kind in {"bodyguard", "enforcer"}:
            return "protect_operator"
        if has_radio:
            return "guard_zone"
        return "protect_operator"
    if procedure_key == "logistics" and has_cargo and has_follow_procedure:
        return "seek_item_and_return"
    if procedure_key in {"mapping", "scout"} and has_mapping_procedure:
        return _roll_weighted_choice(rng, ((35, "map_area_loop"), (65, "patrol_route")))
    if procedure_key == "follow" and has_follow_procedure:
        if kind in {"justice", "security", "corporate"}:
            choices = [(30, "follow_operator"), (30, "guard_zone")]
            if has_mapping_procedure:
                choices.append((40, "patrol_route"))
            return _roll_weighted_choice(rng, choices)
        if kind in {"gang", "cult"}:
            choices = [(40, "follow_operator"), (25, "guard_zone")]
            if has_mapping_procedure:
                choices.append((35, "patrol_route"))
            return _roll_weighted_choice(rng, choices)
        if kind in {"scout", "rural", "civic", "utility"} and rng.randrange(3) == 0:
            return "watch_person"
        return "follow_operator"
    return None


def _property_covering(sim, x, y, z):
    covering = getattr(sim, "property_covering", None)
    if callable(covering):
        prop = covering(int(x), int(y), int(z))
        if isinstance(prop, dict):
            return prop
    direct = getattr(sim, "property_at", None)
    prop = direct(int(x), int(y), int(z)) if callable(direct) else None
    return prop if isinstance(prop, dict) else None


def _structure_identity(sim, x, y, z):
    structure_at = getattr(sim, "structure_at", None)
    structure = structure_at(int(x), int(y), int(z)) if callable(structure_at) else None
    if not isinstance(structure, dict):
        return None, ""
    building_id = str(structure.get("building_id", "") or "").strip()
    room_kind = _clean(structure.get("room_kind") or structure.get("kind"))
    return building_id or None, room_kind


def _same_drone_operating_space(sim, origin, candidate):
    ox, oy, oz = origin
    cx, cy, cz = candidate
    origin_prop = _property_covering(sim, ox, oy, oz)
    candidate_prop = _property_covering(sim, cx, cy, cz)
    origin_prop_id = str((origin_prop or {}).get("id", "") or "")
    candidate_prop_id = str((candidate_prop or {}).get("id", "") or "")
    if origin_prop_id or candidate_prop_id:
        return bool(origin_prop_id and origin_prop_id == candidate_prop_id)
    origin_building, _room = _structure_identity(sim, ox, oy, oz)
    candidate_building, _room = _structure_identity(sim, cx, cy, cz)
    if origin_building or candidate_building:
        return bool(origin_building and origin_building == candidate_building)
    return True


def _open_cardinal_shape(sim, x, y, z):
    open_directions = []
    tilemap = getattr(sim, "tilemap", None)
    for dx, dy in _CARDINAL_OFFSETS:
        if tilemap is not None and bool(tilemap.is_walkable(int(x) + dx, int(y) + dy, int(z))):
            open_directions.append((dx, dy))
    straight_choke = (
        len(open_directions) == 2
        and open_directions[0][0] == -open_directions[1][0]
        and open_directions[0][1] == -open_directions[1][1]
    )
    return len(open_directions), straight_choke


def _npc_drone_tile_score(sim, origin, candidate, *, owner_eid):
    x, y, z = candidate
    distance = abs(int(x) - int(origin[0])) + abs(int(y) - int(origin[1]))
    _building_id, room_kind = _structure_identity(sim, x, y, z)
    transitory_room = any(token in room_kind for token in _TRANSITORY_ROOM_TOKENS)
    open_neighbors, straight_choke = _open_cardinal_shape(sim, x, y, z)
    stable_tie = random.Random(
        f"{getattr(sim, 'seed', 0)}:npc-drone-station:{owner_eid}:{int(x)}:{int(y)}:{int(z)}"
    ).random()
    return (
        0 if _same_drone_operating_space(sim, origin, candidate) else 1,
        1 if drone_deploy_tile_is_threshold(sim, x, y, z) else 0,
        1 if transitory_room else 0,
        1 if straight_choke else 0,
        abs(distance - 2),
        abs(open_neighbors - 3),
        stable_tie,
    )


def _npc_drone_deploy_tile(sim, owner_eid, x, y, z):
    """Choose a nearby station without treating a doorway or hall axis as a pad."""

    origin = (int(x), int(y), int(z))
    origin_chunk = sim.chunk_coords(origin[0], origin[1])
    candidates = []
    for distance in (1, 2, 3):
        for dx in range(-distance, distance + 1):
            dy_abs = distance - abs(dx)
            for dy in ({dy_abs, -dy_abs} if dy_abs else {0}):
                candidate = (origin[0] + dx, origin[1] + dy, origin[2])
                if sim.chunk_coords(candidate[0], candidate[1]) != origin_chunk:
                    continue
                if not drone_deploy_tile_open(sim, *candidate):
                    continue
                candidates.append((_npc_drone_tile_score(sim, origin, candidate, owner_eid=owner_eid), candidate))
    candidates.sort(key=lambda row: row[0])
    return candidates[0][1] if candidates else None


def npc_drone_follow_station(sim, owner_eid, drone_eid):
    """Return a clear formation station instead of the operator's doorway."""

    owner_pos = sim.ecs.get(Position).get(owner_eid)
    drone_pos = sim.ecs.get(Position).get(drone_eid)
    if owner_pos is None or drone_pos is None or int(owner_pos.z) != int(drone_pos.z):
        return None
    owner_xyz = (int(owner_pos.x), int(owner_pos.y), int(owner_pos.z))
    current = (int(drone_pos.x), int(drone_pos.y), int(drone_pos.z))
    distance = abs(current[0] - owner_xyz[0]) + abs(current[1] - owner_xyz[1])
    _building_id, room_kind = _structure_identity(sim, *current)
    transitory_room = any(token in room_kind for token in _TRANSITORY_ROOM_TOKENS)
    _open_neighbors, straight_choke = _open_cardinal_shape(sim, *current)
    if (
        2 <= distance <= 3
        and _same_drone_operating_space(sim, owner_xyz, current)
        and not drone_deploy_tile_is_threshold(sim, *current)
        and not transitory_room
        and not straight_choke
    ):
        return current
    return _npc_drone_deploy_tile(sim, owner_eid, *owner_xyz)


def _seeded_patrol_points(sim, owner_eid, drone_eid, *, limit=5):
    """Build a short, connected local route instead of a wall-blind square."""

    pos = sim.ecs.get(Position).get(drone_eid)
    owner_pos = sim.ecs.get(Position).get(owner_eid)
    if pos is None:
        return ()
    origin = (int(pos.x), int(pos.y), int(pos.z))
    operating_origin = (
        (int(owner_pos.x), int(owner_pos.y), int(owner_pos.z))
        if owner_pos is not None and int(owner_pos.z) == int(pos.z)
        else origin
    )
    points = [origin]
    visited = {origin}
    current = origin
    for step_index in range(max(0, int(limit) - 1)):
        candidates = []
        for dx, dy in _CARDINAL_OFFSETS:
            candidate = (current[0] + dx, current[1] + dy, current[2])
            if candidate in visited or not drone_deploy_tile_open(sim, *candidate):
                continue
            if not _same_drone_operating_space(sim, operating_origin, candidate):
                continue
            if drone_deploy_tile_is_threshold(sim, *candidate):
                continue
            score = _npc_drone_tile_score(sim, operating_origin, candidate, owner_eid=owner_eid)
            tie = random.Random(
                f"{getattr(sim, 'seed', 0)}:npc-drone-route:{drone_eid}:{step_index}:{candidate}"
            ).random()
            candidates.append((score[:-1] + (tie,), candidate))
        if not candidates:
            break
        candidates.sort(key=lambda row: row[0])
        current = candidates[0][1]
        visited.add(current)
        points.append(current)
    return tuple(points)


def _seeded_task_bindings(sim, owner_eid, drone_eid, state, task_id, *, target_eid=None):
    positions = sim.ecs.get(Position)
    owner_pos = positions.get(owner_eid)
    drone_pos = positions.get(drone_eid)
    home = getattr(state, "home", None)
    if isinstance(home, (list, tuple)) and len(home) >= 3:
        home_pos = (_int(home[0]), _int(home[1]), _int(home[2]))
    elif owner_pos is not None:
        home_pos = (int(owner_pos.x), int(owner_pos.y), int(owner_pos.z))
    elif drone_pos is not None:
        home_pos = (int(drone_pos.x), int(drone_pos.y), int(drone_pos.z))
    else:
        home_pos = None

    bindings = {}
    if task_id in {"follow_operator", "protect_operator", "watch_person"}:
        person_eid = target_eid if task_id == "watch_person" and target_eid is not None else owner_eid
        bindings["PERSON"] = {
            "kind": "person",
            "eid": person_eid,
            "label": "watched person" if task_id == "watch_person" and person_eid != owner_eid else "operator",
        }
    if task_id in {"guard_zone", "map_area_loop"} and home_pos is not None:
        bindings["AREA"] = {"kind": "area", "target": home_pos, "label": "operator area"}
    if task_id == "patrol_route":
        points = _seeded_patrol_points(sim, owner_eid, drone_eid)
        if points:
            bindings["ROUTE"] = {
                "kind": "route",
                "points": points,
                "label": "seeded patrol loop",
            }
    if task_id == "seek_item_and_return" and home_pos is not None:
        bindings["ITEM_TYPE"] = {"kind": "item_type", "item_id": "any", "label": "any item"}
        bindings["RETURN_TO"] = {"kind": "return_to", "target": home_pos, "label": "operator area"}
    return bindings


def _activate_seeded_task(sim, owner_eid, drone_eid, state, task_id, *, target_eid=None):
    task_id = _clean(task_id)
    if not task_id:
        return None
    installed_ids = {
        _clean(card.get("id"))
        for card in installed_drone_program_cards(state)
        if isinstance(card, dict) and card.get("id")
    }
    if task_id not in installed_ids:
        metadata = getattr(state, "source_metadata", None)
        if not isinstance(metadata, dict):
            metadata = {}
            state.source_metadata = metadata
        metadata["npc_drone_task"] = task_id
        metadata["npc_drone_task_activation_ok"] = False
        metadata["npc_drone_task_blocked_reason"] = "program_not_installed"
        return {"ok": False, "reason": "program_not_installed"}
    program = built_in_drone_program(task_id)
    if not isinstance(program, dict):
        return None
    if task_id in {"follow_operator", "protect_operator", "watch_person"}:
        state.target_eid = target_eid if task_id == "watch_person" and target_eid is not None else owner_eid
    else:
        state.target_eid = None
    bindings = _seeded_task_bindings(
        sim,
        owner_eid,
        drone_eid,
        state,
        task_id,
        target_eid=target_eid,
    )
    result = activate_drone_program(
        state,
        program,
        bindings=bindings,
        controller_eid=owner_eid,
        drone_eid=drone_eid,
        sim=sim,
    )
    metadata = getattr(state, "source_metadata", None)
    if not isinstance(metadata, dict):
        metadata = {}
        state.source_metadata = metadata
    metadata["npc_drone_task"] = task_id
    metadata["npc_drone_task_activation_ok"] = bool(result.get("ok"))
    if not result.get("ok"):
        metadata["npc_drone_task_blocked_reason"] = str(result.get("reason", "blocked") or "blocked")
    else:
        metadata.pop("npc_drone_task_blocked_reason", None)
    return result


def _installed_task_ids(state):
    return {
        _clean(card.get("id"))
        for card in installed_drone_program_cards(state)
        if isinstance(card, dict) and card.get("id")
    }


def _nearby_alarm_target(sim, drone_eid, *, radius=1):
    pos = sim.ecs.get(Position).get(drone_eid)
    if pos is None:
        return None
    matches = []
    for prop in tuple(getattr(sim, "properties", {}).values()):
        if not isinstance(prop, dict):
            continue
        metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
        role = _clean(metadata.get("interaction_role") or prop.get("interaction_role"))
        fixture_type = _clean(metadata.get("fixture_type") or prop.get("fixture_type") or prop.get("archetype"))
        if role != "alarm_target" and "alarm" not in fixture_type:
            continue
        prop_id = str(prop.get("id", "") or "")
        disabled = getattr(sim, "camera_disabled", {})
        disabled_until = _int(disabled.get(prop_id), 0) if isinstance(disabled, dict) else 0
        if disabled_until > int(getattr(sim, "tick", 0) or 0):
            continue
        try:
            target = (_int(prop.get("x")), _int(prop.get("y")), _int(prop.get("z")))
        except (TypeError, ValueError):
            continue
        if target[2] != int(pos.z):
            continue
        distance = abs(target[0] - int(pos.x)) + abs(target[1] - int(pos.y))
        if distance <= int(max(0, radius)):
            matches.append((distance, prop_id, prop))
    matches.sort(key=lambda row: (row[0], row[1]))
    return matches[0][2] if matches else None


def _owner_will_state(sim, owner_eid):
    ai = sim.ecs.get(AI).get(owner_eid)
    will = sim.ecs.get(NPCWill).get(owner_eid)
    candidates = (
        _clean(getattr(will, "intent", "")) if will is not None else "",
        _clean(getattr(ai, "state", "")) if ai is not None else "",
    )
    intent = next((value for value in candidates if value and value != "idle"), "idle")
    return intent, _owner_active_target(sim, owner_eid)


def _desired_npc_drone_task(sim, owner_eid, drone_eid, state, *, intent=None, active_target=None):
    available = _installed_task_ids(state)
    if not available:
        return None, "idle", None
    if intent is None:
        intent, active_target = _owner_will_state(sim, owner_eid)
    armed = bool(drone_weapon_status(state, item_catalog=ITEM_CATALOG).get("armed"))
    module_ids = {
        _clean(module.get("item_id"))
        for module in tuple(getattr(state, "modules", ()) or ())
        if isinstance(module, dict)
    }

    if active_target is not None:
        if armed and "protect_operator" in available:
            return "protect_operator", intent, active_target
        if "watch_person" in available:
            return "watch_person", intent, active_target
    if intent in NPC_DRONE_COVERT_INTENTS:
        if "disable_alarm" in available and _nearby_alarm_target(sim, drone_eid) is not None:
            return "disable_alarm", intent, None
        if "distract" in available:
            return "distract", intent, None
        if "watch_person" in available:
            return "watch_person", intent, None
    if intent == "scavenging" and "drone_cargo_clamp_module" in module_ids and "seek_item_and_return" in available:
        return "seek_item_and_return", intent, None
    if intent in NPC_DRONE_WITHDRAWAL_INTENTS:
        if "follow_operator" in available:
            return "follow_operator", intent, None
        if armed and "protect_operator" in available:
            return "protect_operator", intent, None
    if intent in NPC_DRONE_DANGER_INTENTS:
        if armed and "protect_operator" in available:
            return "protect_operator", intent, None
        if "watch_person" in available:
            return "watch_person", intent, None
    if intent in NPC_DRONE_WATCH_INTENTS and "watch_person" in available:
        return "watch_person", intent, None

    metadata = getattr(state, "source_metadata", {})
    baseline = _clean(metadata.get("npc_drone_base_task")) if isinstance(metadata, dict) else ""
    if baseline in available:
        return baseline, intent, None
    for fallback in ("follow_operator", "guard_zone", "patrol_route", "map_area_loop", "watch_person"):
        if fallback in available:
            return fallback, intent, None
    return None, intent, None


def retask_npc_drones_from_owner_will(sim):
    """Translate changing NPC intent into bounded, installed drone routines."""

    now = int(getattr(sim, "tick", 0) or 0)
    retasked = 0
    for drone_eid, state in list(sim.ecs.get(DroneState).items()):
        metadata = getattr(state, "source_metadata", None)
        if not isinstance(metadata, dict):
            continue
        if _clean(metadata.get("source_context")) == DRONE_FACTION_SOURCE_CONTEXT:
            collider = sim.ecs.get(Collider).get(drone_eid)
            if collider is not None:
                collider.blocks = False
            metadata["npc_drone_yields_foot_traffic"] = True
        if not bool(metadata.get("npc_will_driven")):
            continue
        owner_eid = getattr(state, "owner_eid", None) or getattr(state, "controller_eid", None)
        if owner_eid is None or owner_eid == getattr(sim, "player_eid", None):
            continue
        if sim.ecs.get(AI).get(owner_eid) is None and sim.ecs.get(NPCWill).get(owner_eid) is None:
            continue
        intent, active_target = _owner_will_state(sim, owner_eid)
        will_signature = (intent, active_target)
        raw_signature = metadata.get("npc_drone_owner_will_signature", ())
        previous_signature = tuple(raw_signature) if isinstance(raw_signature, (list, tuple)) else ()
        metadata["npc_drone_owner_intent"] = intent
        metadata["npc_drone_owner_target_eid"] = active_target
        metadata["npc_drone_owner_will_signature"] = will_signature
        current = _clean(getattr(state, "procedure_program_id", ""))
        status = _clean(getattr(state, "procedure_status", ""))
        last_retask = _int(metadata.get("npc_drone_last_retask_tick"), -9999)
        if previous_signature == will_signature:
            if current and status in {"", "running"}:
                continue
            if not current:
                continue
            retry_cooldown = NPC_DRONE_REPEAT_ACTION_COOLDOWN if current in {"disable_alarm", "distract"} else NPC_DRONE_RETASK_COOLDOWN
            if now - last_retask < retry_cooldown:
                continue

        desired, intent, active_target = _desired_npc_drone_task(
            sim,
            owner_eid,
            drone_eid,
            state,
            intent=intent,
            active_target=active_target,
        )
        if not desired:
            continue

        if current == desired and status in {"", "running"}:
            continue
        cooldown = NPC_DRONE_REPEAT_ACTION_COOLDOWN if current == desired else NPC_DRONE_RETASK_COOLDOWN
        urgent = active_target is not None and desired in {"protect_operator", "watch_person"}
        if not urgent and now - last_retask < cooldown:
            continue

        previous = current or None
        result = _activate_seeded_task(
            sim,
            owner_eid,
            drone_eid,
            state,
            desired,
            target_eid=active_target,
        )
        metadata["npc_drone_last_retask_tick"] = now
        if not result or not result.get("ok"):
            continue
        metadata["npc_drone_last_retask_from"] = previous
        metadata["npc_drone_last_retask_intent"] = intent
        retasked += 1
        sim.emit(Event(
            "npc_drone_retasked",
            eid=owner_eid,
            owner_eid=owner_eid,
            drone_eid=drone_eid,
            previous_task=previous,
            task=desired,
            intent=intent,
            target_eid=active_target,
        ))
    return retasked


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


def _should_seed_owner_drone(sim, chunk, owner_eid, kind):
    kind = _clean(kind)
    chance = float(DRONE_FACTION_SEED_CHANCE_BY_KIND.get(kind, 0.0))
    if chance <= 0.0:
        return False
    if chance >= 1.0:
        return True
    rng = random.Random(f"{getattr(sim, 'seed', 0)}:drone-faction-seed:{chunk}:{owner_eid}:{kind}")
    return rng.random() < chance


def _spawn_seeded_drone(sim, owner_eid, chunk, ordinal):
    pos = sim.ecs.get(Position).get(owner_eid)
    if pos is None:
        return None
    deploy_tile = _npc_drone_deploy_tile(sim, owner_eid, pos.x, pos.y, pos.z)
    if deploy_tile is None:
        return None
    kind = _owner_kind(sim, owner_eid)
    rng = random.Random(f"{getattr(sim, 'seed', 0)}:drone-faction:{chunk}:{owner_eid}:{kind}:{ordinal}")
    metadata = _loadout_for_kind(kind, rng)
    operator_org_eid = _actor_organization_eid(sim, owner_eid)
    supply = drone_supply_agreement_for_actor(sim, owner_eid)
    manufacturer_org_eid = (
        int(supply.get("supplier_org_eid"))
        if isinstance(supply, dict) and supply.get("supplier_org_eid") is not None
        else operator_org_eid
    )
    manufacturing_identity = (
        organization_manufacturing_identity(sim, manufacturer_org_eid)
        if manufacturer_org_eid is not None
        else {}
    )
    manufacturing_modifiers = (
        organization_manufacturing_modifiers(sim, manufacturer_org_eid)
        if manufacturer_org_eid is not None
        else {}
    )
    if isinstance(supply, dict) and int(supply.get("flow_percent", 0) or 0) >= 40:
        metadata = _supplied_loadout_for_doctrine(
            kind,
            manufacturing_identity.get("drone_doctrine"),
            rng,
            metadata,
        )
    seeded_task = _seeded_task_for_loadout(kind, metadata, rng)
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
        "npc_drone_task": seeded_task,
        "npc_drone_base_task": seeded_task,
        "npc_will_driven": True,
        "npc_drone_behavior_policy_version": NPC_DRONE_BEHAVIOR_POLICY_VERSION,
        "npc_drone_yields_foot_traffic": True,
        "operator_organization_eid": operator_org_eid,
        "manufacturer_organization_eid": manufacturer_org_eid,
        "manufacturer_organization_key": manufacturing_identity.get("organization_key"),
        "manufacturer_organization_name": manufacturing_identity.get("organization_name"),
        "manufacturer": manufacturing_identity.get("manufacturer"),
        "manufacturing_signature": manufacturing_identity.get("manufacturing_signature"),
        "product_motif": manufacturing_identity.get("product_motif"),
        "product_finish": manufacturing_identity.get("product_finish"),
        "manufacturing_modifiers": manufacturing_modifiers,
        "supply_agreement_id": (supply or {}).get("agreement_id") if isinstance(supply, dict) else None,
        "supply_flow_percent": (supply or {}).get("flow_percent") if isinstance(supply, dict) else None,
        "paint": {
            "primary_color": manufacturing_identity.get("primary_color_word")
            or ("black" if kind in {"gang", "cult", "bodyguard", "enforcer"} else "white"),
            "secondary_color": manufacturing_identity.get("secondary_color_word")
            or ("red" if kind in {"justice", "security"} else "green"),
            "accent_color": manufacturing_identity.get("accent_color_word")
            or ("red" if kind in {"justice", "security"} else "green"),
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
    signal_bonus = max(-2, min(2, _int(manufacturing_modifiers.get("signal_integrity"), 0)))
    state.range_limit = int(max(1, _int(chassis_profile.get("base_range"), getattr(state, "range_limit", 0) or 0) + signal_bonus))
    state.source_metadata["range_limit"] = int(state.range_limit)
    if state.procedure_key == "follow":
        state.target_eid = owner_eid
    state.source_metadata["source_context"] = DRONE_FACTION_SOURCE_CONTEXT
    state.source_metadata["source_item_instance_id"] = source_instance_id
    render_spec = deployed_drone_render_spec(state.source_metadata, item_catalog=ITEM_CATALOG)

    drone_eid = sim.ecs.create()
    x, y, z = deploy_tile
    sim.ecs.add(drone_eid, Position(x, y, z))
    sim.ecs.add(
        drone_eid,
        Render(
            render_spec["glyph"],
            render_spec["color"],
            color_word=render_spec.get("color_word"),
            semantic_id="entity_drone",
        ),
    )
    sim.ecs.add(
        drone_eid,
        CreatureIdentity(
            taxonomy_class="machine",
            species="drone",
            creature_type="drone",
            common_name=f"{state.chassis_class}-class drone",
        ),
    )
    # These are mobile machines, not player-built barricades.  They remain
    # targetable physical entities while yielding the foot-traffic plane.
    sim.ecs.add(drone_eid, Collider(blocks=False))
    sim.ecs.add(drone_eid, Vitality(max_hp=state.hull_hp_max, hp=state.hull_hp))
    sim.ecs.add(drone_eid, state)
    sim.tilemap.add_entity(drone_eid, x, y, z)
    _activate_seeded_task(sim, owner_eid, drone_eid, state, seeded_task)
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
    policy_version = _int(state.get("behavior_policy_version"), 0)
    if policy_version < NPC_DRONE_BEHAVIOR_POLICY_VERSION:
        # Reconsider already visited chunks once when density/activity policy
        # improves. Existing owner drones prevent duplication below.
        state["seeded_chunks"] = set()
        state["catchup_done_chunks"] = set()
        state["behavior_policy_version"] = NPC_DRONE_BEHAVIOR_POLICY_VERSION
        for drone_eid, drone_state in tuple(sim.ecs.get(DroneState).items()):
            metadata = getattr(drone_state, "source_metadata", None)
            if not isinstance(metadata, dict) or _clean(metadata.get("source_context")) != DRONE_FACTION_SOURCE_CONTEXT:
                continue
            collider = sim.ecs.get(Collider).get(drone_eid)
            if collider is not None:
                collider.blocks = False
            metadata["npc_drone_yields_foot_traffic"] = True
    seeded = state["seeded_chunks"]
    for chunk in _loaded_chunks(sim):
        if chunk in seeded:
            continue
        if _faction_drone_count_in_chunk(sim, chunk) >= DRONE_FACTION_MAX_PER_CHUNK:
            seeded.add(chunk)
            continue
        owner_candidates = []
        eligible_seen = False
        for eid in sorted(sim.entity_ids_in_chunk(chunk) if hasattr(sim, "entity_ids_in_chunk") else sim.ecs.get(Position).keys()):
            if not owner_drone_seed_eligible(sim, eid):
                continue
            eligible_seen = True
            if _existing_seeded_drone_for_owner(sim, eid):
                continue
            kind = _owner_kind(sim, eid)
            if _should_seed_owner_drone(sim, chunk, eid, kind):
                owner_candidates.append(eid)
        if not owner_candidates:
            if eligible_seen:
                seeded.add(chunk)
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
            require_remote=False,
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
    "NPC_DRONE_BEHAVIOR_POLICY_VERSION",
    "catch_up_faction_drones_for_chunk",
    "npc_drone_follow_station",
    "owner_drone_seed_eligible",
    "retask_npc_drones_from_owner_will",
    "seed_loaded_faction_drones",
    "tick_faction_drone_combat",
]
