"""Runtime systems for deployed drones."""

from engine.events import Event
from engine.systems import System

from game.aerosol_trap_runtime import armed_aerosol_traps_at
from game.components import DroneState, Position, Vitality
from game.drone_runtime import (
    drone_deploy_tile_is_threshold,
    drone_deploy_tile_open,
    drone_destroyed_drop_resolution,
    drone_state_controlled_by_actor,
    drone_state_has_capability,
)
from game.drone_procedures import (
    cardinal_step_toward,
    drone_procedure_implemented,
    drone_procedure_label,
    drone_procedure_missing_capability,
    normalize_drone_procedure_key,
)
from game.drone_programs import active_drone_program, run_drone_program_step, sync_drone_program_metadata
from game.drone_recon import apply_autonomous_mapping_knowledge
from game.movement_runtime import try_move_entity
from game.system_support.fire_runtime import fire_cell_state


DRONE_MOVE_BATTERY_COST = 1
DRONE_HOLD_CLEAR_OFFSETS = (
    (0, -1),
    (1, 0),
    (0, 1),
    (-1, 0),
)


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


def _range_anchor(sim, state):
    controller_eid = getattr(state, "controller_eid", None)
    controller_pos = sim.ecs.get(Position).get(controller_eid) if controller_eid is not None else None
    if controller_pos is not None:
        return (int(controller_pos.x), int(controller_pos.y), int(controller_pos.z))
    home = getattr(state, "home", None)
    if isinstance(home, (list, tuple)) and len(home) >= 3:
        return (_int(home[0]), _int(home[1]), _int(home[2]))
    return None


def _sync_state_hull_from_vitality(state, vitality):
    if state is None or vitality is None:
        return
    state.hull_hp = int(max(0, _int(getattr(vitality, "hp", 0), 0)))
    state.hull_hp_max = int(max(1, _int(getattr(vitality, "max_hp", 1), 1)))
    state.source_metadata["hull_hp"] = int(state.hull_hp)
    state.source_metadata["hull_hp_max"] = int(state.hull_hp_max)


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
        }
        for entry in tuple(resolution.get("destroyed_items", ()) or ())
        if str(entry.get("item_id", "") or "").strip()
    )

    chassis_class = getattr(state, "chassis_class", None)
    owner_eid = getattr(state, "owner_eid", None)
    controller_eid = getattr(state, "controller_eid", None)
    source_instance_id = getattr(state, "source_item_instance_id", None)
    removed = sim.remove_entity(drone_eid)
    if removed:
        sim.emit(Event(
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
        ))
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

    def _hold_threshold_clear_step(self, state, pos):
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
            if armed_aerosol_traps_at(self.sim, nx, ny, nz):
                continue
            return dx, dy
        return None

    def _run_hold_procedure(self, controller_eid, drone_eid, state, pos, procedure_key):
        clear_step = self._hold_threshold_clear_step(state, pos)
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
        program = active_drone_program(state)
        if program is not None and str(getattr(state, "procedure_status", "") or "").strip().lower() in {"", "running", "blocked"}:
            controller_eid = self._controller_for_state(state)
            if controller_eid is None:
                return self._procedure_blocked(None, drone_eid, state, program.get("id"), "missing_controller")
            return run_drone_program_step(self, controller_eid, drone_eid, state)
        procedure_key = normalize_drone_procedure_key(getattr(state, "procedure_key", None))
        if not procedure_key:
            return {"ok": True, "reason": None, "procedure_key": ""}
        tick = int(getattr(self.sim, "tick", 0) or 0)
        if _int(getattr(state, "source_metadata", {}).get("procedure_skip_tick"), -1) == tick:
            return {"ok": True, "reason": "skipped", "procedure_key": procedure_key}
        controller_eid = self._controller_for_state(state)
        if controller_eid is None:
            return self._procedure_blocked(None, drone_eid, state, procedure_key, "missing_controller")
        if not drone_procedure_implemented(procedure_key):
            return self._procedure_blocked(controller_eid, drone_eid, state, procedure_key, "procedure_not_implemented")
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
        from game.drone_factions import seed_loaded_faction_drones, tick_faction_drone_combat

        seed_loaded_faction_drones(self.sim)
        for drone_eid in list(self.sim.ecs.get(DroneState).keys()):
            state = self.sim.ecs.get(DroneState).get(drone_eid)
            if state is not None:
                tick_drone_weapon_cooldowns(state, tick=int(getattr(self.sim, "tick", 0) or 0))
            self.run_drone_procedure(drone_eid)
        tick_faction_drone_combat(self.sim, self)

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

    def move_drone(self, controller_eid, drone_eid, dx, dy):
        step = _cardinal_step(dx, dy)
        if step is None:
            return self._movement_blocked(controller_eid, drone_eid, "invalid_direction", dx=dx, dy=dy)
        dx, dy = step

        state = _deployed_drone_state(self.sim, drone_eid)
        if state is None:
            return self._movement_blocked(controller_eid, drone_eid, "not_deployed", dx=dx, dy=dy)
        if not drone_state_controlled_by_actor(state, controller_eid):
            return self._movement_blocked(controller_eid, drone_eid, "not_controller", dx=dx, dy=dy)

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
        if armed_aerosol_traps_at(self.sim, target_x, target_y, target_z):
            return self._movement_blocked(controller_eid, drone_eid, "armed_trap", x=target_x, y=target_y, z=target_z, dx=dx, dy=dy)

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
            if bool(result.get("ok")):
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
