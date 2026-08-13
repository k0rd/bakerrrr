"""Runtime systems for deployed drones."""

from collections import deque

from engine.events import Event
from engine.systems import System

from game.components import Collider, DroneState, Position, Vitality
from game.mechanical_device_runtime import (
    drone_detect_mechanical_devices_at,
    drone_knows_armed_mechanical_device_at,
    mechanical_devices_at,
)
from game.drone_runtime import (
    drone_deploy_tile_is_threshold,
    drone_deploy_tile_open,
    drone_destroyed_drop_resolution,
    drone_hull_damage_absorb,
    drone_link_disruption_status,
    drone_state_controlled_by_actor,
    drone_state_has_capability,
)
from game.drone_procedures import (
    cardinal_step_toward,
    default_drone_procedure_key,
    drone_procedure_implemented,
    drone_procedure_label,
    drone_procedure_missing_capability,
    normalize_drone_procedure_key,
)
from game.drone_programs import active_drone_program, run_drone_program_step, sync_drone_program_metadata
from game.drone_recon import apply_autonomous_mapping_knowledge
from game.signal_jammer_runtime import (
    clear_expired_drone_jammer_effects,
    drone_iff_disruption_status,
    drone_shutdown_status,
    jammer_iff_target_for_drone,
)
from game.movement_runtime import try_move_entity
from game.physical_target_runtime import apply_physical_property_damage, weapon_targetable_property_at
from game.property_runtime import property_is_vehicle, vehicle_label, vehicle_profile_from_property
from game.system_support.fire_runtime import fire_cell_state


DRONE_MOVE_BATTERY_COST = 1
DRONE_HOLD_CLEAR_OFFSETS = (
    (0, -1),
    (1, 0),
    (0, 1),
    (-1, 0),
)
DRONE_LOCAL_PATH_NODE_LIMIT = 128
DRONE_VEHICLE_IMPACT_RAW_BY_CLASS = {
    "A": 7,
    "B": 11,
    "C": 16,
    "D": 22,
    "E": 30,
}
DRONE_SELF_IMPACT_RAW_BY_CLASS = {
    "A": 12,
    "B": 11,
    "C": 10,
    "D": 9,
    "E": 8,
}


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _cardinal_step(dx, dy):
    dx = 1 if _int(dx) > 0 else -1 if _int(dx) < 0 else 0
    dy = 1 if _int(dy) > 0 else -1 if _int(dy) < 0 else 0
    if abs(dx) + abs(dy) != 1:
        return None
    return dx, dy


def _deployed_drone_state(sim, drone_eid):
    state = sim.ecs.get(DroneState).get(drone_eid)
    if state is None:
        return None
    if str(getattr(state, "mode", "") or "").strip().lower() != "deployed":
        return None
    return state


def _vehicle_property_at(sim, x, y, z=0):
    prop = weapon_targetable_property_at(sim, int(x), int(y), int(z))
    return prop if property_is_vehicle(prop) else None


def _drone_vehicle_impact_raw(state):
    chassis_class = str(getattr(state, "chassis_class", "") or "").strip().upper()
    return int(DRONE_VEHICLE_IMPACT_RAW_BY_CLASS.get(chassis_class, 12))


def _drone_self_impact_raw(state, vehicle_prop):
    chassis_class = str(getattr(state, "chassis_class", "") or "").strip().upper()
    profile = vehicle_profile_from_property(vehicle_prop) or {}
    power = max(1, min(10, _int(profile.get("power"), 5)))
    durability = max(0, min(10, _int(profile.get("durability"), 5)))
    return int(DRONE_SELF_IMPACT_RAW_BY_CLASS.get(chassis_class, 10) + (power // 2) + (durability // 3))


def _range_anchor(sim, state):
    controller_eid = getattr(state, "controller_eid", None)
    controller_pos = sim.ecs.get(Position).get(controller_eid) if controller_eid is not None else None
    if controller_pos is not None:
        return (int(controller_pos.x), int(controller_pos.y), int(controller_pos.z))
    home = getattr(state, "home", None)
    if isinstance(home, (list, tuple)) and len(home) >= 3:
        return (_int(home[0]), _int(home[1]), _int(home[2]))
    return None


def _drone_path_cell_open(sim, drone_eid, state, x, y, z):
    if sim.detail_for_xy(int(x), int(y)) == "unloaded":
        return False
    if not sim.tilemap.in_bounds(int(x), int(y)) or not sim.tilemap.is_walkable(int(x), int(y), int(z)):
        return False
    anchor = _range_anchor(sim, state)
    range_limit = int(max(0, getattr(state, "range_limit", 0) or 0))
    if anchor is None or range_limit <= 0 or int(anchor[2]) != int(z):
        return False
    if abs(int(x) - int(anchor[0])) + abs(int(y) - int(anchor[1])) > range_limit:
        return False
    fire_cell = fire_cell_state(sim, int(x), int(y), int(z))
    if isinstance(fire_cell, dict) and int(fire_cell.get("fire_intensity", 0) or 0) > 0:
        return False
    if drone_knows_armed_mechanical_device_at(sim, drone_eid, int(x), int(y), int(z)):
        return False
    if _vehicle_property_at(sim, int(x), int(y), int(z)) is not None:
        return False
    for other_eid in tuple(sim.tilemap.entities_at(int(x), int(y), int(z)) or ()):
        if other_eid == drone_eid:
            continue
        collider = sim.ecs.get(Collider).get(other_eid)
        if collider is not None and bool(getattr(collider, "blocks", False)):
            return False
    return True


def _bounded_drone_path_step(sim, drone_eid, state, start, target, *, max_nodes=DRONE_LOCAL_PATH_NODE_LIMIT):
    """Find one local step only when the cheap direct step is obstructed."""

    if start == target:
        return None
    frontier = deque([start])
    previous = {start: None}
    found = False
    while frontier and len(previous) <= int(max_nodes):
        current = frontier.popleft()
        neighbors = [
            (current[0] + dx, current[1] + dy, current[2])
            for dx, dy in DRONE_HOLD_CLEAR_OFFSETS
        ]
        neighbors.sort(
            key=lambda point: (
                abs(point[0] - target[0]) + abs(point[1] - target[1]),
                point[1],
                point[0],
            )
        )
        for candidate in neighbors:
            if candidate in previous or not _drone_path_cell_open(sim, drone_eid, state, *candidate):
                continue
            previous[candidate] = current
            if candidate == target:
                found = True
                frontier.clear()
                break
            frontier.append(candidate)
    if not found:
        return None
    cursor = target
    while previous.get(cursor) is not None and previous[cursor] != start:
        cursor = previous[cursor]
    if previous.get(cursor) != start:
        return None
    return (int(cursor[0]) - int(start[0]), int(cursor[1]) - int(start[1]))


def _sync_state_hull_from_vitality(state, vitality):
    if state is None or vitality is None:
        return
    state.hull_hp = int(max(0, _int(getattr(vitality, "hp", 0), 0)))
    state.hull_hp_max = int(max(1, _int(getattr(vitality, "max_hp", 1), 1)))
    state.source_metadata["hull_hp"] = int(state.hull_hp)
    state.source_metadata["hull_hp_max"] = int(state.hull_hp_max)


def apply_deployed_drone_collision_damage(
    sim,
    drone_eid,
    raw_damage,
    *,
    source_eid=None,
    damage_kind="collision",
    weapon_id="impact",
    x=None,
    y=None,
    z=None,
):
    """Apply a physical impact through drone hull armor and salvage rules."""

    state = _deployed_drone_state(sim, drone_eid)
    vitality = sim.ecs.get(Vitality).get(drone_eid)
    pos = sim.ecs.get(Position).get(drone_eid)
    if state is None or vitality is None:
        return {"damage": 0, "destroyed": False, "reason": "not_deployed"}

    if x is None:
        x = getattr(pos, "x", 0)
    if y is None:
        y = getattr(pos, "y", 0)
    if z is None:
        z = getattr(pos, "z", 0)
    previous_hp = int(max(0, getattr(vitality, "hp", 0) or 0))
    raw_damage = int(max(1, _int(raw_damage, 1)))
    armor_absorb = drone_hull_damage_absorb(
        state,
        weapon_id=weapon_id,
        damage_kind=damage_kind,
    )
    final_damage = int(max(1, round(raw_damage * (1.0 - armor_absorb))))
    vitality.hp = max(0, int(vitality.hp) - final_damage)
    chassis_class = str(getattr(state, "chassis_class", "") or "").strip().upper()
    sim.emit(Event(
        "entity_damaged",
        target_eid=drone_eid,
        source_eid=source_eid,
        weapon_id=str(weapon_id or "impact"),
        damage_kind=str(damage_kind or "collision"),
        raw_damage=raw_damage,
        damage=final_damage,
        cover_absorb=0.0,
        armor_absorb=round(float(armor_absorb), 3),
        armor_name=f"{chassis_class}-class hull" if chassis_class else "drone hull",
        hp=vitality.hp,
        max_hp=vitality.max_hp,
        x=int(x),
        y=int(y),
        z=int(z),
    ))
    _sync_state_hull_from_vitality(state, vitality)

    destroyed = int(vitality.hp) <= 0
    if destroyed:
        destroy_deployed_drone(
            sim,
            drone_eid,
            source_eid=source_eid,
            reason="collision",
            damage_kind=str(damage_kind or "collision"),
            damage_amount=final_damage,
            overkill_amount=max(0, final_damage - previous_hp),
        )
    return {
        "damage": int(final_damage),
        "raw_damage": int(raw_damage),
        "armor_absorb": round(float(armor_absorb), 3),
        "hp_before": int(previous_hp),
        "hp": int(max(0, getattr(vitality, "hp", 0) or 0)),
        "destroyed": bool(destroyed),
    }


def destroy_deployed_drone(
    sim,
    drone_eid,
    *,
    source_eid=None,
    reason="destroyed",
    damage_kind="damage",
    damage_amount=None,
    overkill_amount=0,
):
    state = _deployed_drone_state(sim, drone_eid)
    if state is None:
        return False
    pos = sim.ecs.get(Position).get(drone_eid)
    vitality = sim.ecs.get(Vitality).get(drone_eid)
    _sync_state_hull_from_vitality(state, vitality)

    drop_x = int(getattr(pos, "x", 0) or 0)
    drop_y = int(getattr(pos, "y", 0) or 0)
    drop_z = int(getattr(pos, "z", 0) or 0)
    dropped_items = []
    resolution = drone_destroyed_drop_resolution(
        state,
        damage_amount=damage_amount,
        overkill_amount=overkill_amount,
        damage_kind=damage_kind,
    )
    for entry in resolution.get("drops", ()):
        item_id = str(entry.get("item_id", "") or "").strip().lower()
        if not item_id:
            continue
        quantity = int(max(1, _int(entry.get("quantity"), 1)))
        sim.register_ground_item(
            item_id=item_id,
            x=drop_x,
            y=drop_y,
            z=drop_z,
            quantity=quantity,
            owner_eid=None,
            owner_tag=None,
            metadata=dict(entry.get("metadata") or {}),
        )
        dropped_items.append({
            "item_id": item_id,
            "quantity": quantity,
            "drop_kind": str(entry.get("drop_kind", "") or "").strip().lower() or "drone_part",
        })
    destroyed_items = tuple(
        {
            "item_id": str(entry.get("item_id", "") or "").strip().lower(),
            "quantity": int(max(1, _int(entry.get("quantity"), 1))),
            "drop_kind": str(entry.get("drop_kind", "") or "").strip().lower() or "drone_part",
            "metadata": dict(entry.get("metadata") or {}),
            "resolution": str(entry.get("resolution", "destroyed") or "destroyed").strip().lower(),
            "salvage_item_id": str(entry.get("salvage_item_id", "") or "").strip().lower() or None,
        }
        for entry in tuple(resolution.get("destroyed_items", ()) or ())
        if str(entry.get("item_id", "") or "").strip()
    )

    chassis_class = getattr(state, "chassis_class", None)
    owner_eid = getattr(state, "owner_eid", None)
    controller_eid = getattr(state, "controller_eid", None)
    source_instance_id = getattr(state, "source_item_instance_id", None)
    battery_exploded = bool(resolution.get("battery_exploded"))
    battery_item_id = resolution.get("battery_item_id")
    battery_charge = int(max(0, _int(resolution.get("battery_charge"), 0)))
    battery_charge_max = int(max(0, _int(resolution.get("battery_charge_max"), 0)))
    removed = sim.remove_entity(drone_eid)
    if removed:
        destroyed_event = Event(
            "drone_destroyed",
            drone_eid=drone_eid,
            source_eid=source_eid,
            owner_eid=owner_eid,
            controller_eid=controller_eid,
            source_item_instance_id=source_instance_id,
            chassis_class=chassis_class,
            reason=reason,
            damage_kind=damage_kind,
            x=drop_x,
            y=drop_y,
            z=drop_z,
            dropped_items=tuple(dropped_items),
            destroyed_items=destroyed_items,
            damage_amount=damage_amount,
            overkill_amount=int(max(0, _int(overkill_amount), 0)),
            battery_exploded=battery_exploded,
            battery_item_id=battery_item_id,
            battery_charge=battery_charge,
            battery_charge_max=battery_charge_max,
        )
        if battery_exploded:
            sim.emit(Event(
                "drone_battery_exploded",
                drone_eid=drone_eid,
                source_eid=source_eid,
                owner_eid=owner_eid,
                controller_eid=controller_eid,
                source_item_instance_id=source_instance_id,
                battery_item_id=battery_item_id,
                battery_charge=battery_charge,
                battery_charge_max=battery_charge_max,
                x=drop_x,
                y=drop_y,
                z=drop_z,
            ))
        sim.emit(destroyed_event)
    return bool(removed)


class DroneSystem(System):
    def __init__(self, sim):
        super().__init__(sim)
        self.sim.events.subscribe("drone_move_request", self.on_drone_move_request)
        self.sim.events.subscribe("drone_command_request", self.on_drone_command_request)
        self.sim.events.subscribe("drone_weapon_fire_request", self.on_drone_weapon_fire_request)
        self.sim.events.subscribe("entity_damaged", self.on_entity_damaged)
        self.sim.events.subscribe("chunk_loaded", self.on_chunk_loaded)

    def _controller_for_state(self, state):
        for value in (getattr(state, "controller_eid", None), getattr(state, "owner_eid", None)):
            if value is None:
                continue
            if drone_state_controlled_by_actor(state, value):
                return value
        return None

    def _sync_procedure_metadata(self, state, *, procedure_key=None, reason=None):
        if state is None:
            return
        metadata = getattr(state, "source_metadata", None)
        if not isinstance(metadata, dict):
            metadata = {}
            state.source_metadata = metadata
        if procedure_key is not None:
            metadata["procedure_key"] = procedure_key
        metadata["last_command"] = getattr(state, "last_command", None)
        metadata["target_eid"] = getattr(state, "target_eid", None)
        target = getattr(state, "target", None)
        if isinstance(target, (list, tuple)):
            metadata["target"] = tuple(target)
        else:
            metadata.pop("target", None)
        tick = int(getattr(self.sim, "tick", 0) or 0)
        metadata["procedure_last_tick"] = tick
        if hasattr(state, "procedure_last_tick"):
            state.procedure_last_tick = tick
        if reason:
            metadata["procedure_last_reason"] = str(reason)
            if hasattr(state, "procedure_last_reason"):
                state.procedure_last_reason = str(reason)
            if hasattr(state, "procedure_last_result"):
                state.procedure_last_result = "blocked"
        else:
            metadata.pop("procedure_last_reason", None)
            if hasattr(state, "procedure_last_reason"):
                state.procedure_last_reason = None
        sync_drone_program_metadata(state)

    def _procedure_blocked(self, controller_eid, drone_eid, state, procedure_key, reason, **extra):
        reason = str(reason or "blocked").strip().lower() or "blocked"
        self._sync_procedure_metadata(state, procedure_key=procedure_key, reason=reason)
        metadata = getattr(state, "source_metadata", {}) if state is not None else {}
        tick = int(getattr(self.sim, "tick", 0) or 0)
        emit_key = (str(procedure_key or ""), reason)
        last_key = tuple(metadata.get("procedure_last_emit_key", ())) if isinstance(metadata, dict) else ()
        last_tick = _int(metadata.get("procedure_last_emit_tick"), -9999) if isinstance(metadata, dict) else -9999
        should_emit = emit_key != last_key or tick - last_tick >= 5
        if isinstance(metadata, dict):
            metadata["procedure_last_emit_key"] = emit_key
            metadata["procedure_last_emit_tick"] = tick
        if should_emit:
            self.sim.emit(Event(
                "drone_procedure_blocked",
                eid=controller_eid,
                controller_eid=controller_eid,
                drone_eid=drone_eid,
                chassis_class=getattr(state, "chassis_class", None) if state is not None else None,
                procedure_key=procedure_key,
                procedure_label=drone_procedure_label(procedure_key),
                reason=reason,
                **extra,
            ))
        return {"ok": False, "reason": reason, "procedure_key": procedure_key}

    def _procedure_ran(self, controller_eid, drone_eid, state, procedure_key, **extra):
        self._sync_procedure_metadata(state, procedure_key=procedure_key)
        self.sim.emit(Event(
            "drone_procedure_ran",
            eid=controller_eid,
            controller_eid=controller_eid,
            drone_eid=drone_eid,
            chassis_class=getattr(state, "chassis_class", None) if state is not None else None,
            procedure_key=procedure_key,
            procedure_label=drone_procedure_label(procedure_key),
            **extra,
        ))
        payload = {"ok": True, "reason": None, "procedure_key": procedure_key}
        payload.update(extra)
        return payload

    def _hold_threshold_clear_step(self, drone_eid, state, pos):
        if pos is None:
            return None
        if int(getattr(state, "battery_charge", 0) or 0) < DRONE_MOVE_BATTERY_COST:
            return None
        if not drone_deploy_tile_is_threshold(self.sim, pos.x, pos.y, pos.z):
            return None
        anchor = _range_anchor(self.sim, state)
        range_limit = int(max(0, getattr(state, "range_limit", 0) or 0))
        for dx, dy in DRONE_HOLD_CLEAR_OFFSETS:
            nx = int(pos.x) + int(dx)
            ny = int(pos.y) + int(dy)
            nz = int(pos.z)
            if not drone_deploy_tile_open(self.sim, nx, ny, nz):
                continue
            if drone_deploy_tile_is_threshold(self.sim, nx, ny, nz):
                continue
            if anchor is None or range_limit <= 0:
                continue
            if int(anchor[2]) != nz or abs(nx - int(anchor[0])) + abs(ny - int(anchor[1])) > range_limit:
                continue
            fire_cell = fire_cell_state(self.sim, nx, ny, nz)
            if isinstance(fire_cell, dict) and int(fire_cell.get("fire_intensity", 0) or 0) > 0:
                continue
            if (
                drone_knows_armed_mechanical_device_at(self.sim, drone_eid, nx, ny, nz)
                or drone_detect_mechanical_devices_at(self.sim, drone_eid, nx, ny, nz)
            ):
                continue
            return dx, dy
        return None

    def _run_hold_procedure(self, controller_eid, drone_eid, state, pos, procedure_key):
        clear_step = self._hold_threshold_clear_step(drone_eid, state, pos)
        if clear_step is not None:
            result = self.move_drone(controller_eid, drone_eid, clear_step[0], clear_step[1])
            if result.get("ok"):
                state.last_command = procedure_key
                self._sync_procedure_metadata(state, procedure_key=procedure_key)
                return self._procedure_ran(
                    controller_eid,
                    drone_eid,
                    state,
                    procedure_key,
                    action="clear_threshold",
                    dx=clear_step[0],
                    dy=clear_step[1],
                )
        if pos is not None:
            state.target = (int(pos.x), int(pos.y), int(pos.z))
        state.last_command = procedure_key
        return self._procedure_ran(controller_eid, drone_eid, state, procedure_key, action="hold")

    def _run_follow_procedure(self, controller_eid, drone_eid, state, pos, procedure_key):
        target_pos = self.sim.ecs.get(Position).get(getattr(state, "target_eid", None) or controller_eid)
        if pos is None:
            return self._procedure_blocked(controller_eid, drone_eid, state, procedure_key, "missing_position")
        if target_pos is None:
            return self._procedure_blocked(controller_eid, drone_eid, state, procedure_key, "missing_target")
        if int(pos.z) != int(target_pos.z):
            return self._procedure_blocked(controller_eid, drone_eid, state, procedure_key, "wrong_floor")
        distance = abs(int(pos.x) - int(target_pos.x)) + abs(int(pos.y) - int(target_pos.y))
        state.target = (int(target_pos.x), int(target_pos.y), int(target_pos.z))
        if distance <= 1:
            state.last_command = procedure_key
            return self._procedure_ran(controller_eid, drone_eid, state, procedure_key, action="hold", distance=distance)
        step = cardinal_step_toward((pos.x, pos.y), (target_pos.x, target_pos.y))
        if step is None:
            return self._procedure_blocked(controller_eid, drone_eid, state, procedure_key, "no_step")
        result = self.move_drone(controller_eid, drone_eid, step[0], step[1])
        if not result.get("ok"):
            self._sync_procedure_metadata(state, procedure_key=procedure_key, reason=result.get("reason"))
            return result
        state.last_command = procedure_key
        self._sync_procedure_metadata(state, procedure_key=procedure_key)
        return self._procedure_ran(controller_eid, drone_eid, state, procedure_key, action="move", dx=step[0], dy=step[1], distance=distance)

    def _run_return_procedure(self, controller_eid, drone_eid, state, pos, procedure_key):
        home = getattr(state, "home", None)
        if pos is None:
            return self._procedure_blocked(controller_eid, drone_eid, state, procedure_key, "missing_position")
        if not isinstance(home, (list, tuple)) or len(home) < 3:
            return self._procedure_blocked(controller_eid, drone_eid, state, procedure_key, "missing_home")
        target = (_int(home[0]), _int(home[1]), _int(home[2]))
        state.target = target
        if int(pos.z) != target[2]:
            return self._procedure_blocked(controller_eid, drone_eid, state, procedure_key, "wrong_floor")
        if (int(pos.x), int(pos.y), int(pos.z)) == target:
            state.last_command = procedure_key
            return self._procedure_ran(controller_eid, drone_eid, state, procedure_key, action="hold", arrived=True)
        step = cardinal_step_toward((pos.x, pos.y), target)
        if step is None:
            return self._procedure_blocked(controller_eid, drone_eid, state, procedure_key, "no_step")
        result = self.move_drone(controller_eid, drone_eid, step[0], step[1])
        if not result.get("ok"):
            self._sync_procedure_metadata(state, procedure_key=procedure_key, reason=result.get("reason"))
            return result
        state.last_command = procedure_key
        self._sync_procedure_metadata(state, procedure_key=procedure_key)
        return self._procedure_ran(controller_eid, drone_eid, state, procedure_key, action="move", dx=step[0], dy=step[1], target=target)

    def _run_mapping_procedure(self, controller_eid, drone_eid, state, _pos, procedure_key):
        result = apply_autonomous_mapping_knowledge(self.sim, controller_eid, drone_eid)
        if not result.get("ok"):
            return self._procedure_blocked(controller_eid, drone_eid, state, procedure_key, result.get("reason", "blocked"))
        state.last_command = procedure_key
        learned = int(max(0, _int(result.get("learned_count"), 0)))
        state.source_metadata["autonomous_mapping_last_visible"] = len(set(result.get("visible", set()) or set()))
        state.source_metadata["autonomous_mapping_last_learned"] = learned
        return self._procedure_ran(controller_eid, drone_eid, state, procedure_key, action="map", learned_count=learned)

    def run_drone_procedure(self, drone_eid):
        state = _deployed_drone_state(self.sim, drone_eid)
        if state is None:
            return {"ok": False, "reason": "not_deployed"}
        tick = int(getattr(self.sim, "tick", 0) or 0)
        if drone_shutdown_status(state, tick=tick).get("active"):
            return {"ok": False, "reason": "jammer_shutdown"}
        if drone_iff_disruption_status(state, tick=tick).get("active"):
            return {"ok": False, "reason": "iff_scrambled"}
        program = active_drone_program(state)
        if program is not None and str(getattr(state, "procedure_status", "") or "").strip().lower() in {"", "running", "blocked"}:
            controller_eid = self._controller_for_state(state)
            if controller_eid is None:
                return self._procedure_blocked(None, drone_eid, state, program.get("id"), "missing_controller")
            return run_drone_program_step(self, controller_eid, drone_eid, state)
        procedure_key = normalize_drone_procedure_key(getattr(state, "procedure_key", None))
        if not procedure_key:
            procedure_key = default_drone_procedure_key(state)
            if procedure_key:
                state.procedure_key = procedure_key
                state.last_command = procedure_key
                self._sync_procedure_metadata(state, procedure_key=procedure_key)
        if not procedure_key:
            return {"ok": True, "reason": None, "procedure_key": ""}
        if _int(getattr(state, "source_metadata", {}).get("procedure_skip_tick"), -1) == tick:
            return {"ok": True, "reason": "skipped", "procedure_key": procedure_key}
        controller_eid = self._controller_for_state(state)
        if controller_eid is None:
            return self._procedure_blocked(None, drone_eid, state, procedure_key, "missing_controller")
        if not drone_procedure_implemented(procedure_key):
            return self._procedure_blocked(controller_eid, drone_eid, state, procedure_key, "unknown_procedure")
        missing = drone_procedure_missing_capability(state, procedure_key)
        if missing:
            return self._procedure_blocked(controller_eid, drone_eid, state, procedure_key, missing)
        pos = self.sim.ecs.get(Position).get(drone_eid)
        if procedure_key == "hold":
            return self._run_hold_procedure(controller_eid, drone_eid, state, pos, procedure_key)
        if procedure_key == "follow":
            return self._run_follow_procedure(controller_eid, drone_eid, state, pos, procedure_key)
        if procedure_key == "return":
            return self._run_return_procedure(controller_eid, drone_eid, state, pos, procedure_key)
        if procedure_key in {"mapping", "scout"}:
            return self._run_mapping_procedure(controller_eid, drone_eid, state, pos, "mapping")
        return self._procedure_blocked(controller_eid, drone_eid, state, procedure_key, "unknown_procedure")

    def update(self):
        from game.drone_combat import tick_drone_weapon_cooldowns
        from game.drone_factions import retask_npc_drones_from_owner_will, seed_loaded_faction_drones, tick_faction_drone_combat

        seed_loaded_faction_drones(self.sim)
        retask_npc_drones_from_owner_will(self.sim)
        for drone_eid in list(self.sim.ecs.get(DroneState).keys()):
            state = self.sim.ecs.get(DroneState).get(drone_eid)
            if state is not None:
                clear_expired_drone_jammer_effects(
                    state,
                    tick=int(getattr(self.sim, "tick", 0) or 0),
                )
                self._expire_external_link_disruption(drone_eid, state)
                tick_drone_weapon_cooldowns(state, tick=int(getattr(self.sim, "tick", 0) or 0))
                if drone_shutdown_status(state, tick=int(getattr(self.sim, "tick", 0) or 0)).get("active"):
                    continue
                if drone_iff_disruption_status(state, tick=int(getattr(self.sim, "tick", 0) or 0)).get("active"):
                    self._run_jammer_iff_behavior(drone_eid, state)
                    continue
            self.run_drone_procedure(drone_eid)
        tick_faction_drone_combat(self.sim, self)

    def _run_jammer_iff_behavior(self, drone_eid, state):
        """Give a scrambled drone one bounded hostile action."""

        controller_eid = self._controller_for_state(state)
        if controller_eid is None:
            return {"ok": False, "reason": "missing_controller"}
        target_eid = jammer_iff_target_for_drone(self.sim, drone_eid, state)
        if target_eid is None:
            return {"ok": True, "reason": "no_jammer_target", "action": "hold"}
        target_pos = self.sim.ecs.get(Position).get(target_eid)
        if target_pos is None:
            return {"ok": False, "reason": "missing_target"}
        state.target_eid = target_eid
        state.target = (int(target_pos.x), int(target_pos.y), int(target_pos.z))

        from game.drone_combat import drone_weapon_status

        weapon = drone_weapon_status(
            state,
            tick=int(getattr(self.sim, "tick", 0) or 0),
        )
        if weapon.get("armed"):
            result = self.fire_drone_weapon(
                controller_eid,
                drone_eid,
                target_eid=target_eid,
                weapon_kind=weapon.get("primary_weapon") or "auto",
                require_remote=False,
                require_camera=True,
                consume_turn=False,
            )
            if result.get("ok"):
                return result
        drone_pos = self.sim.ecs.get(Position).get(drone_eid)
        if (
            drone_pos is not None
            and int(drone_pos.z) == int(target_pos.z)
            and abs(int(drone_pos.x) - int(target_pos.x))
            + abs(int(drone_pos.y) - int(target_pos.y)) <= 1
        ):
            return {"ok": True, "reason": "jammer_target_adjacent", "action": "hold"}
        return self.move_drone_toward(
            controller_eid,
            drone_eid,
            (int(target_pos.x), int(target_pos.y), int(target_pos.z)),
            jammer_override=True,
        )

    def _expire_external_link_disruption(self, drone_eid, state):
        metadata = getattr(state, "source_metadata", None)
        if not isinstance(metadata, dict):
            return False
        until_tick = _int(metadata.get("external_link_disrupted_until_tick"), 0)
        now = int(getattr(self.sim, "tick", 0) or 0)
        if until_tick <= 0 or until_tick > now:
            return False
        source_kind = str(metadata.get("external_link_disruption_source_kind", "") or "").strip().lower()
        source_eid = metadata.get("external_link_disruption_source_eid")
        from game.drone_runtime import set_drone_link_disruption

        set_drone_link_disruption(state, until_tick=0)
        controller_eid = self._controller_for_state(state)
        self.sim.emit(Event(
            "drone_wire_link_restored",
            eid=controller_eid,
            controller_eid=getattr(state, "controller_eid", None),
            owner_eid=getattr(state, "owner_eid", None),
            drone_eid=drone_eid,
            reason="natural_expiry",
            source_kind="wire_link_expiry",
            disruption_source_kind=source_kind,
            disruption_source_eid=source_eid,
            restored_tick=now,
        ))
        return True

    def _movement_blocked(self, controller_eid, drone_eid, reason, *, x=None, y=None, z=None, dx=0, dy=0):
        self.sim.emit(Event(
            "drone_move_blocked",
            eid=controller_eid,
            controller_eid=controller_eid,
            drone_eid=drone_eid,
            reason=str(reason or "blocked").strip().lower() or "blocked",
            x=x,
            y=y,
            z=z,
            dx=dx,
            dy=dy,
        ))
        return {"ok": False, "reason": str(reason or "blocked").strip().lower() or "blocked"}

    def _collide_with_vehicle(self, controller_eid, drone_eid, state, vehicle_prop, x, y, z):
        battery_before = int(max(0, getattr(state, "battery_charge", 0) or 0))
        state.battery_charge = max(0, battery_before - DRONE_MOVE_BATTERY_COST)
        state.source_metadata["battery_charge"] = int(state.battery_charge)
        state.last_command = "move"
        vehicle_impact_raw = _drone_vehicle_impact_raw(state)
        drone_impact_raw = _drone_self_impact_raw(state, vehicle_prop)

        vehicle_result = apply_physical_property_damage(
            self.sim,
            vehicle_prop,
            vehicle_impact_raw,
            damage_kind="drone_collision",
            weapon_id="drone",
            source_eid=controller_eid,
            x=int(x),
            y=int(y),
            z=int(z),
        )
        drone_result = apply_deployed_drone_collision_damage(
            self.sim,
            drone_eid,
            drone_impact_raw,
            source_eid=controller_eid,
            damage_kind="drone_vehicle_collision",
            weapon_id="vehicle",
            x=int(x),
            y=int(y),
            z=int(z),
        )
        chassis_class = str(getattr(state, "chassis_class", "") or "").strip().upper()
        self.sim.emit(Event(
            "drone_vehicle_collision",
            eid=controller_eid,
            controller_eid=controller_eid,
            drone_eid=drone_eid,
            chassis_class=chassis_class or None,
            vehicle_id=vehicle_prop.get("id"),
            vehicle_name=vehicle_label(vehicle_prop),
            drone_damage=int(drone_result.get("damage", 0) or 0),
            drone_hull=int(drone_result.get("hp", 0) or 0),
            drone_destroyed=bool(drone_result.get("destroyed")),
            vehicle_damage=int(vehicle_result.get("damage", 0) or 0),
            vehicle_condition=int(vehicle_result.get("integrity", 0) or 0),
            vehicle_broken=bool(vehicle_result.get("broken")),
            battery_charge=int(state.battery_charge),
            battery_charge_max=int(getattr(state, "battery_charge_max", 0) or 0),
            x=int(x),
            y=int(y),
            z=int(z),
        ))
        self.sim.emit(Event(
            "noise",
            source_eid=controller_eid,
            x=int(x),
            y=int(y),
            z=int(z),
            radius=5,
            cause="drone_vehicle_collision",
            drone_eid=drone_eid,
            vehicle_id=vehicle_prop.get("id"),
        ))
        return {
            "ok": False,
            "acted": True,
            "reason": "vehicle_collision",
            "drone_damage": int(drone_result.get("damage", 0) or 0),
            "drone_destroyed": bool(drone_result.get("destroyed")),
            "vehicle_damage": int(vehicle_result.get("damage", 0) or 0),
            "vehicle_broken": bool(vehicle_result.get("broken")),
            "x": int(x),
            "y": int(y),
            "z": int(z),
        }

    def move_drone(self, controller_eid, drone_eid, dx, dy, *, jammer_override=False):
        step = _cardinal_step(dx, dy)
        if step is None:
            return self._movement_blocked(controller_eid, drone_eid, "invalid_direction", dx=dx, dy=dy)
        dx, dy = step

        state = _deployed_drone_state(self.sim, drone_eid)
        if state is None:
            return self._movement_blocked(controller_eid, drone_eid, "not_deployed", dx=dx, dy=dy)
        if not drone_state_controlled_by_actor(state, controller_eid):
            return self._movement_blocked(controller_eid, drone_eid, "not_controller", dx=dx, dy=dy)

        tick = int(getattr(self.sim, "tick", 0) or 0)
        if drone_shutdown_status(state, tick=tick).get("active"):
            return self._movement_blocked(controller_eid, drone_eid, "jammer_shutdown", dx=dx, dy=dy)
        if not jammer_override and drone_iff_disruption_status(state, tick=tick).get("active"):
            return self._movement_blocked(controller_eid, drone_eid, "iff_scrambled", dx=dx, dy=dy)

        pos = self.sim.ecs.get(Position).get(drone_eid)
        if pos is None:
            return self._movement_blocked(controller_eid, drone_eid, "missing_position", dx=dx, dy=dy)

        if int(getattr(state, "battery_charge", 0) or 0) < DRONE_MOVE_BATTERY_COST:
            return self._movement_blocked(controller_eid, drone_eid, "battery_depleted", x=pos.x, y=pos.y, z=pos.z, dx=dx, dy=dy)

        target_x = int(pos.x) + int(dx)
        target_y = int(pos.y) + int(dy)
        target_z = int(pos.z)
        anchor = _range_anchor(self.sim, state)
        if anchor is None:
            return self._movement_blocked(controller_eid, drone_eid, "no_range_anchor", x=target_x, y=target_y, z=target_z, dx=dx, dy=dy)
        range_limit = int(max(0, getattr(state, "range_limit", 0) or 0))
        if range_limit <= 0:
            return self._movement_blocked(controller_eid, drone_eid, "no_range", x=target_x, y=target_y, z=target_z, dx=dx, dy=dy)
        if int(anchor[2]) != target_z or abs(target_x - int(anchor[0])) + abs(target_y - int(anchor[1])) > range_limit:
            return self._movement_blocked(controller_eid, drone_eid, "out_of_range", x=target_x, y=target_y, z=target_z, dx=dx, dy=dy)

        fire_cell = fire_cell_state(self.sim, target_x, target_y, target_z)
        if isinstance(fire_cell, dict) and int(fire_cell.get("fire_intensity", 0) or 0) > 0:
            return self._movement_blocked(controller_eid, drone_eid, "active_fire", x=target_x, y=target_y, z=target_z, dx=dx, dy=dy)
        if (
            drone_knows_armed_mechanical_device_at(self.sim, drone_eid, target_x, target_y, target_z)
            or drone_detect_mechanical_devices_at(self.sim, drone_eid, target_x, target_y, target_z)
        ):
            reason = "armed_trap" if any(
                bool((prop.get("metadata") or {}).get("aerosol_floor_trap"))
                for prop in mechanical_devices_at(self.sim, target_x, target_y, target_z)
            ) else "known_trap"
            return self._movement_blocked(controller_eid, drone_eid, reason, x=target_x, y=target_y, z=target_z, dx=dx, dy=dy)

        vehicle_prop = _vehicle_property_at(self.sim, target_x, target_y, target_z)
        if vehicle_prop is not None:
            return self._collide_with_vehicle(
                controller_eid,
                drone_eid,
                state,
                vehicle_prop,
                target_x,
                target_y,
                target_z,
            )

        old_x = int(pos.x)
        old_y = int(pos.y)
        old_z = int(pos.z)
        moved, reason = try_move_entity(self.sim, drone_eid, target_x, target_y, target_z, reason="drone_move")
        if not moved:
            return self._movement_blocked(controller_eid, drone_eid, reason or "blocked", x=target_x, y=target_y, z=target_z, dx=dx, dy=dy)

        state.battery_charge = int(max(0, int(getattr(state, "battery_charge", 0) or 0) - DRONE_MOVE_BATTERY_COST))
        state.source_metadata["battery_charge"] = int(state.battery_charge)
        state.last_command = "move"
        state.target = (int(pos.x), int(pos.y), int(pos.z))
        self.sim.emit(Event(
            "drone_moved",
            eid=controller_eid,
            controller_eid=controller_eid,
            drone_eid=drone_eid,
            chassis_class=getattr(state, "chassis_class", None),
            old_x=old_x,
            old_y=old_y,
            old_z=old_z,
            x=int(pos.x),
            y=int(pos.y),
            z=int(pos.z),
            dx=dx,
            dy=dy,
            battery_charge=int(state.battery_charge),
            battery_charge_max=int(getattr(state, "battery_charge_max", 0) or 0),
        ))
        return {"ok": True, "reason": None, "x": int(pos.x), "y": int(pos.y), "z": int(pos.z)}

    def move_drone_toward(self, controller_eid, drone_eid, target, *, jammer_override=False):
        """Take one ordinary drone step toward a factual world coordinate."""

        pos = self.sim.ecs.get(Position).get(drone_eid)
        if pos is None:
            return self._movement_blocked(controller_eid, drone_eid, "missing_position")
        if not isinstance(target, (tuple, list)) or len(target) < 3:
            return self._movement_blocked(controller_eid, drone_eid, "missing_target")
        try:
            target = (int(target[0]), int(target[1]), int(target[2]))
        except (TypeError, ValueError):
            return self._movement_blocked(controller_eid, drone_eid, "missing_target")
        if int(pos.z) != target[2]:
            return self._movement_blocked(controller_eid, drone_eid, "wrong_floor", x=target[0], y=target[1], z=target[2])
        if (int(pos.x), int(pos.y), int(pos.z)) == target:
            return {"ok": True, "reason": None, "action": "arrived", "x": int(pos.x), "y": int(pos.y), "z": int(pos.z)}
        state = _deployed_drone_state(self.sim, drone_eid)
        if state is None:
            return self._movement_blocked(controller_eid, drone_eid, "not_deployed")
        start = (int(pos.x), int(pos.y), int(pos.z))
        step = cardinal_step_toward(start, target)
        if step is None:
            return self._movement_blocked(controller_eid, drone_eid, "no_step", x=target[0], y=target[1], z=target[2])
        direct = (start[0] + int(step[0]), start[1] + int(step[1]), start[2])
        if not _drone_path_cell_open(self.sim, drone_eid, state, *direct):
            alternate = _bounded_drone_path_step(self.sim, drone_eid, state, start, target)
            if alternate is not None:
                step = alternate
        return self.move_drone(
            controller_eid,
            drone_eid,
            step[0],
            step[1],
            jammer_override=jammer_override,
        )

    def _command_blocked(self, controller_eid, drone_eid, reason, *, command=None, x=None, y=None, z=None):
        self.sim.emit(Event(
            "drone_command_blocked",
            eid=controller_eid,
            controller_eid=controller_eid,
            drone_eid=drone_eid,
            command=str(command or "").strip().lower(),
            reason=str(reason or "blocked").strip().lower() or "blocked",
            x=x,
            y=y,
            z=z,
        ))
        return {"ok": False, "reason": str(reason or "blocked").strip().lower() or "blocked"}

    def _sync_command_metadata(self, state):
        if state is None:
            return
        state.source_metadata["procedure_key"] = getattr(state, "procedure_key", None)
        state.source_metadata["last_command"] = getattr(state, "last_command", None)
        state.source_metadata["target_eid"] = getattr(state, "target_eid", None)
        target = getattr(state, "target", None)
        if isinstance(target, (list, tuple)):
            state.source_metadata["target"] = tuple(target)
        else:
            state.source_metadata.pop("target", None)

    def _clear_active_program_for_command_intent(self, state):
        if state is None:
            return
        for attr in (
            "procedure_program_id",
            "procedure_program",
            "procedure_bindings",
            "procedure_pc",
            "procedure_status",
            "procedure_last_result",
            "procedure_last_reason",
            "procedure_last_tick",
        ):
            setattr(state, attr, None)
        state.observation_context = None
        sync_drone_program_metadata(state)

    def command_drone(self, controller_eid, drone_eid, command, *, dx=0, dy=0, consume_turn=False):
        command = str(command or "").strip().lower()
        if command in {"direct_move", "step"}:
            command = "move"
        if command in {"inspect", "refresh"}:
            command = "status"
        if command in {"map", "recon", "scout"}:
            command = "mapping"

        state = _deployed_drone_state(self.sim, drone_eid)
        pos = self.sim.ecs.get(Position).get(drone_eid) if state is not None else None
        if state is None:
            return self._command_blocked(controller_eid, drone_eid, "not_deployed", command=command)
        if not drone_state_controlled_by_actor(state, controller_eid):
            return self._command_blocked(
                controller_eid,
                drone_eid,
                "not_controller",
                command=command,
                x=getattr(pos, "x", None),
                y=getattr(pos, "y", None),
                z=getattr(pos, "z", None),
            )
        tick = int(getattr(self.sim, "tick", 0) or 0)
        if drone_shutdown_status(state, tick=tick).get("active"):
            return self._command_blocked(
                controller_eid,
                drone_eid,
                "jammer_shutdown",
                command=command,
                x=getattr(pos, "x", None),
                y=getattr(pos, "y", None),
                z=getattr(pos, "z", None),
            )
        if drone_iff_disruption_status(state, tick=tick).get("active"):
            return self._command_blocked(
                controller_eid,
                drone_eid,
                "iff_scrambled",
                command=command,
                x=getattr(pos, "x", None),
                y=getattr(pos, "y", None),
                z=getattr(pos, "z", None),
            )
        link = drone_link_disruption_status(state, tick=int(getattr(self.sim, "tick", 0) or 0))
        if link.get("active"):
            return self._command_blocked(
                controller_eid,
                drone_eid,
                "link_disrupted",
                command=command,
                x=getattr(pos, "x", None),
                y=getattr(pos, "y", None),
                z=getattr(pos, "z", None),
            )
        if not drone_state_has_capability(state, "remote_control"):
            return self._command_blocked(
                controller_eid,
                drone_eid,
                "no_remote_control",
                command=command,
                x=getattr(pos, "x", None),
                y=getattr(pos, "y", None),
                z=getattr(pos, "z", None),
            )

        if command == "move":
            result = self.move_drone(controller_eid, drone_eid, dx, dy)
            if bool(result.get("ok")) or bool(result.get("acted")):
                state.source_metadata["procedure_skip_tick"] = int(getattr(self.sim, "tick", 0) or 0)
                if consume_turn:
                    self.sim.turn_advance_requested = True
            return result

        if command == "status":
            return {"ok": True, "reason": None, "command": "status"}

        if command == "fire":
            return self.fire_drone_weapon(
                controller_eid,
                drone_eid,
                target_eid=None,
                consume_turn=consume_turn,
            )

        if command not in {"hold", "follow", "return", "mapping"}:
            return self._command_blocked(
                controller_eid,
                drone_eid,
                "unknown_command",
                command=command,
                x=getattr(pos, "x", None),
                y=getattr(pos, "y", None),
                z=getattr(pos, "z", None),
            )

        self._clear_active_program_for_command_intent(state)
        state.procedure_key = command
        state.last_command = command
        state.target_eid = None
        if command == "hold":
            if pos is not None:
                state.target = (int(pos.x), int(pos.y), int(pos.z))
        elif command == "follow":
            state.target_eid = controller_eid
            controller_pos = self.sim.ecs.get(Position).get(controller_eid)
            state.target = (
                (int(controller_pos.x), int(controller_pos.y), int(controller_pos.z))
                if controller_pos is not None else None
            )
        elif command == "return":
            state.target = tuple(getattr(state, "home", None)) if isinstance(getattr(state, "home", None), (list, tuple)) else None
        elif command == "mapping":
            if pos is not None:
                state.target = (int(pos.x), int(pos.y), int(pos.z))
        self._sync_command_metadata(state)
        self.sim.emit(Event(
            "drone_commanded",
            eid=controller_eid,
            controller_eid=controller_eid,
            drone_eid=drone_eid,
            chassis_class=getattr(state, "chassis_class", None),
            command=command,
            procedure_key=getattr(state, "procedure_key", None),
            target=getattr(state, "target", None),
            target_eid=getattr(state, "target_eid", None),
            x=getattr(pos, "x", None),
            y=getattr(pos, "y", None),
            z=getattr(pos, "z", None),
        ))
        return {"ok": True, "reason": None, "command": command}

    def fire_drone_weapon(
        self,
        controller_eid,
        drone_eid,
        *,
        target_eid=None,
        target_x=None,
        target_y=None,
        target_z=None,
        weapon_kind="auto",
        require_remote=True,
        require_camera=True,
        consume_turn=False,
    ):
        from game.drone_combat import fire_drone_weapon

        return fire_drone_weapon(
            self.sim,
            controller_eid,
            drone_eid,
            target_eid=target_eid,
            target_x=target_x,
            target_y=target_y,
            target_z=target_z,
            weapon_kind=weapon_kind,
            require_remote=require_remote,
            require_camera=require_camera,
            consume_turn=consume_turn,
        )

    def on_drone_move_request(self, event):
        self.move_drone(
            event.data.get("controller_eid", event.data.get("eid")),
            event.data.get("drone_eid"),
            event.data.get("dx", 0),
            event.data.get("dy", 0),
        )

    def on_drone_command_request(self, event):
        self.command_drone(
            event.data.get("controller_eid", event.data.get("eid")),
            event.data.get("drone_eid"),
            event.data.get("command"),
            dx=event.data.get("dx", 0),
            dy=event.data.get("dy", 0),
            consume_turn=bool(event.data.get("consume_turn", False)),
        )

    def on_drone_weapon_fire_request(self, event):
        self.fire_drone_weapon(
            event.data.get("controller_eid", event.data.get("eid")),
            event.data.get("drone_eid"),
            target_eid=event.data.get("target_eid"),
            target_x=event.data.get("target_x", event.data.get("x")),
            target_y=event.data.get("target_y", event.data.get("y")),
            target_z=event.data.get("target_z", event.data.get("z")),
            weapon_kind=event.data.get("weapon_kind", "auto"),
            require_remote=bool(event.data.get("require_remote", True)),
            require_camera=bool(event.data.get("require_camera", True)),
            consume_turn=bool(event.data.get("consume_turn", False)),
        )

    def on_entity_damaged(self, event):
        drone_eid = event.data.get("target_eid")
        state = _deployed_drone_state(self.sim, drone_eid)
        if state is None:
            return
        vitality = self.sim.ecs.get(Vitality).get(drone_eid)
        _sync_state_hull_from_vitality(state, vitality)

    def on_chunk_loaded(self, event):
        from game.drone_factions import catch_up_faction_drones_for_chunk

        chunk = (
            event.data.get("cx", event.data.get("chunk_x")),
            event.data.get("cy", event.data.get("chunk_y")),
        )
        catch_up_faction_drones_for_chunk(self.sim, self, chunk)
