"""Player vehicle, zoom, and overworld travel runtime."""

import random

from engine.events import Event

from game.components import NPCNeeds, PlayerAssets, PlayerControlled, VehicleState
from game.items import ITEM_CATALOG
from game.property_keys import is_public_owner_tag, property_lock_state
from game.property_runtime import (
    property_is_vehicle as _property_is_vehicle,
    property_metadata as _property_metadata,
    vehicle_fuel_values as _vehicle_fuel_values,
    vehicle_label as _vehicle_label,
    vehicle_profile_from_property as _vehicle_profile_from_property,
)
from game.quick_travel_ramps import (
    QUICK_TRAVEL_RAMP_INTERACT_RADIUS,
    quick_travel_ramp_near,
)
from game.service_runtime import (
    _overworld_discovery_profile,
    _overworld_identity_profile,
    _overworld_legend_line,
    _overworld_travel_profile,
    _overworld_travel_summary_bits,
)
from game.system_support.interaction_ordering import (
    _interaction_target_order_key,
    _manhattan,
    _normalized_direction,
)
from game.vehicle_motion import (
    emit_vehicle_blocked as _emit_vehicle_blocked_event,
    ensure_vehicle_motion_state,
    clamp_vehicle_speed,
    local_route_accessible_at as _vehicle_route_accessible_at,
    rotate_vehicle_heading,
    set_vehicle_speed,
    sync_vehicle_property_position,
    try_vehicle_step,
    vehicle_heading_label,
    vehicle_heading_tuple,
    vehicle_is_usable,
    vehicle_local_block_reason as _vehicle_local_block_reason_for,
    vehicle_medium_for_property,
    vehicle_top_speed,
)


def _clamp(value, lo=0.0, hi=100.0):
    return max(lo, min(hi, value))


def _int_or_default(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


class PlayerTravelRuntime:

    VEHICLE_BASE_FUEL_COST = 4
    VEHICLE_PATH_FUEL_MULT = {
        "freeway": 0.45,
        "road": 0.58,
        "trail": 0.74,
    }
    VEHICLE_TERRAIN_FUEL_MULT = {
        "urban": 0.88,
        "park": 0.84,
        "plains": 0.92,
        "scrub": 1.00,
        "hills": 1.10,
        "forest": 1.14,
        "marsh": 1.28,
        "badlands": 1.22,
        "dunes": 1.26,
        "cliffs": 1.34,
        "industrial_waste": 1.12,
        "salt_flats": 1.18,
        "shore": 1.08,
        "shoals": 1.22,
        "lake": 1.34,
        "waterway": 1.18,
        "island": 1.20,
        "ocean": 1.38,
        "ruins": 1.16,
    }
    VEHICLE_ROUGH_TERRAINS = {
        "badlands",
        "cliffs",
        "dunes",
        "forest",
        "hills",
        "industrial_waste",
        "marsh",
        "ruins",
        "salt_flats",
        "shoals",
        "waterway",
        "island",
        "ocean",
    }

    def __init__(self, action_system):
        self.action_system = action_system
        self.sim = action_system.sim

    def _vehicle_state_for(self, eid):
        return ensure_vehicle_motion_state(self.sim.ecs.get(VehicleState).get(eid))

    def _overworld_view_only_records(self):
        records = getattr(self.sim, "overworld_view_only_by_eid", None)
        if not isinstance(records, dict):
            records = {}
            self.sim.overworld_view_only_by_eid = records
        return records

    def _overworld_view_only_for(self, eid):
        try:
            key = int(eid)
        except (TypeError, ValueError):
            return False
        return bool(self._overworld_view_only_records().get(key, False))

    def _set_overworld_view_only(self, eid, active):
        try:
            key = int(eid)
        except (TypeError, ValueError):
            return False
        records = self._overworld_view_only_records()
        if active:
            records[key] = True
        else:
            records.pop(key, None)
        return bool(active)

    def _vehicle_property_by_id(self, vehicle_id):
        if not vehicle_id:
            return None
        prop = self.sim.properties.get(vehicle_id)
        if not _property_is_vehicle(prop):
            return None
        return prop

    def _active_vehicle_property(self, eid):
        state = self._vehicle_state_for(eid)
        if not state:
            return None
        return self._vehicle_property_by_id(state.active_vehicle_id)

    def _vehicle_for_player_action(self, eid, pos, radius=1, *, preferred_dir=None, exact_direction=False):
        candidates = []
        scan_radius = int(radius)
        if exact_direction and preferred_dir is not None:
            scan_radius = max(
                scan_radius,
                abs(int(preferred_dir[0] or 0)) + abs(int(preferred_dir[1] or 0)),
            )
        for prop in self.sim.properties_in_radius(pos.x, pos.y, pos.z, r=scan_radius):
            if not _property_is_vehicle(prop):
                continue
            profile = _vehicle_profile_from_property(prop)
            if not profile or not profile.get("usable", True):
                continue
            step = _normalized_direction(int(prop.get("x", 0)) - int(pos.x), int(prop.get("y", 0)) - int(pos.y))
            if preferred_dir is not None and exact_direction and step != _normalized_direction(preferred_dir[0], preferred_dir[1]):
                continue
            owner_rank = 0
            if prop.get("owner_eid") == eid:
                owner_rank = 3
            elif str(prop.get("owner_tag", "")).strip().lower() == "player":
                owner_rank = 2
            elif str(prop.get("owner_tag", "")).strip().lower() == "public":
                owner_rank = 1
            if preferred_dir is not None:
                sort_key = (-owner_rank,) + _interaction_target_order_key(
                    pos.x,
                    pos.y,
                    int(prop.get("x", 0)),
                    int(prop.get("y", 0)),
                    preferred_dir=preferred_dir,
                    stable_tiebreaker=(str(prop.get("id", "")),),
                )
            else:
                sort_key = (-owner_rank,) + self.action_system._interaction_target_sort_key(
                    eid,
                    pos,
                    int(prop.get("x", 0)),
                    int(prop.get("y", 0)),
                    stable_tiebreaker=(str(prop.get("id", "")),),
                )
            candidates.append((sort_key, prop))
        if not candidates:
            return None
        candidates.sort(key=lambda row: row[0])
        return candidates[0][1]

    def _sync_vehicle_property_position(self, prop, x, y, z=0):
        sync_vehicle_property_position(self.sim, prop, x, y, z)

    def _local_route_accessible_at(self, x, y, z=0, *, ignore_property_id=None):
        prop = self._vehicle_property_by_id(ignore_property_id) if ignore_property_id else None
        medium = vehicle_medium_for_property(prop) if prop else "land"
        return _vehicle_route_accessible_at(
            self.sim,
            x,
            y,
            z,
            ignore_property_id=ignore_property_id,
            medium=medium,
        )

    def _quick_travel_ramp_near(self, x, y, z=0):
        return quick_travel_ramp_near(self.sim, x, y, z, radius=QUICK_TRAVEL_RAMP_INTERACT_RADIUS)

    def _ramp_distance_from_pos(self, ramp, pos):
        if not isinstance(ramp, dict) or pos is None:
            return None
        try:
            return abs(int(ramp.get("x", 0)) - int(pos.x)) + abs(int(ramp.get("y", 0)) - int(pos.y))
        except (TypeError, ValueError):
            return None

    def _emit_nearby_onramp_notice(self, eid, pos, vehicle_prop=None, ramp=None):
        ramp = ramp if isinstance(ramp, dict) else self._quick_travel_ramp_near(pos.x, pos.y, pos.z)
        if not isinstance(ramp, dict):
            return False
        distance = self._ramp_distance_from_pos(ramp, pos)
        self.sim.emit(Event(
            "vehicle_onramp_nearby",
            eid=eid,
            vehicle_id=(vehicle_prop or {}).get("id") if isinstance(vehicle_prop, dict) else None,
            vehicle_name=_vehicle_label(vehicle_prop) if isinstance(vehicle_prop, dict) else "",
            ramp_property_id=ramp.get("id"),
            ramp_name=str(ramp.get("name", "onramp") or "onramp").strip() or "onramp",
            distance=distance,
            radius=QUICK_TRAVEL_RAMP_INTERACT_RADIUS,
            x=int(pos.x),
            y=int(pos.y),
            z=int(pos.z),
            ramp_x=int(ramp.get("x", 0)),
            ramp_y=int(ramp.get("y", 0)),
            ramp_z=int(ramp.get("z", 0)),
            auto_ramp_enter=self._local_ramp_auto_enter_enabled(),
        ))
        return True

    def _local_ramp_auto_enter_state(self):
        state = getattr(self.sim, "local_drive_ui", None)
        if not isinstance(state, dict):
            state = {}
            self.sim.local_drive_ui = state
        state.setdefault("auto_ramp_enter", False)
        return state

    def _local_ramp_auto_enter_enabled(self):
        return bool(self._local_ramp_auto_enter_state().get("auto_ramp_enter", False))

    def _set_local_ramp_auto_enter(self, active):
        self._local_ramp_auto_enter_state()["auto_ramp_enter"] = bool(active)

    def _maybe_auto_enter_quick_travel_ramp(self, eid, pos, vehicle_prop=None):
        if not self._local_ramp_auto_enter_enabled():
            return False
        if str(getattr(self.sim, "zoom_mode", "city")).strip().lower() == "overworld":
            self._set_local_ramp_auto_enter(False)
            return False
        ramp = self._quick_travel_ramp_near(pos.x, pos.y, pos.z)
        if not isinstance(ramp, dict) or self._ramp_distance_from_pos(ramp, pos) != 0:
            return False
        if not self._enter_quick_travel_from_ramp(eid, pos, vehicle_prop=vehicle_prop):
            return False
        self._set_local_ramp_auto_enter(False)
        self.sim.emit(Event(
            "vehicle_ramp_auto_entered",
            eid=eid,
            vehicle_id=(vehicle_prop or {}).get("id") if isinstance(vehicle_prop, dict) else None,
            vehicle_name=_vehicle_label(vehicle_prop) if isinstance(vehicle_prop, dict) else "",
            x=int(pos.x),
            y=int(pos.y),
            z=int(pos.z),
        ))
        return True

    def _find_route_access_near(self, x, y, z=0, radius=10, *, ignore_property_id=None):
        if self._local_route_accessible_at(x, y, z, ignore_property_id=ignore_property_id):
            return int(x), int(y), int(z)
        for r in range(1, max(1, int(radius)) + 1):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if abs(dx) != r and abs(dy) != r:
                        continue
                    nx = int(x) + int(dx)
                    ny = int(y) + int(dy)
                    if self._local_route_accessible_at(nx, ny, z, ignore_property_id=ignore_property_id):
                        return nx, ny, int(z)
        return None

    def _vehicle_local_block_reason(self, eid, vehicle_prop, x, y, z=0):
        return _vehicle_local_block_reason_for(self.sim, eid, vehicle_prop, x, y, z)

    def _emit_vehicle_blocked(self, eid, vehicle_prop=None, *, reason="blocked", **extra):
        _emit_vehicle_blocked_event(self.sim, eid, vehicle_prop, reason=reason, **extra)

    def _vehicle_drive_command(self, dx, dy):
        step_x = 1 if dx > 0 else -1 if dx < 0 else 0
        step_y = 1 if dy > 0 else -1 if dy < 0 else 0
        if step_x == 0 and step_y == 0:
            return None, None
        turn = -1 if step_x < 0 else 1 if step_x > 0 else 0
        thrust = "accelerate" if step_y < 0 else "brake" if step_y > 0 else None
        return turn, thrust

    def _emit_vehicle_motion_event(self, event_type, eid, vehicle_prop, state, **payload):
        fuel, fuel_capacity = _vehicle_fuel_values(vehicle_prop)
        heading_dx, heading_dy = vehicle_heading_tuple(state)
        data = {
            "eid": eid,
            "vehicle_id": vehicle_prop.get("id"),
            "vehicle_name": _vehicle_label(vehicle_prop),
            "fuel": fuel,
            "fuel_capacity": fuel_capacity,
            "heading_dx": heading_dx,
            "heading_dy": heading_dy,
            "heading": vehicle_heading_label(state),
            "speed": int(getattr(state, "speed", 0) or 0),
            "top_speed": vehicle_top_speed(vehicle_prop),
        }
        data.update(payload)
        self.sim.emit(Event(event_type, **data))

    def _can_enter_quick_travel_from_local_vehicle(self, eid, pos):
        state = self._vehicle_state_for(eid)
        vehicle_prop = self._active_vehicle_property(eid)
        if not state or not state.in_vehicle or not vehicle_prop:
            self.sim.emit(Event(
                "vehicle_action_blocked",
                eid=eid,
                reason="vehicle_required",
            ))
            return False
        if vehicle_medium_for_property(vehicle_prop) == "water":
            self._emit_vehicle_blocked(eid, vehicle_prop, reason="water_map_unavailable")
            return False
        ramp = self._quick_travel_ramp_near(pos.x, pos.y, pos.z)
        if not ramp:
            self._emit_vehicle_blocked(eid, vehicle_prop, reason="quick_travel_ramp_required")
            return False
        if self._local_route_accessible_at(
            pos.x,
            pos.y,
            pos.z,
            ignore_property_id=vehicle_prop.get("id"),
        ):
            return True
        self._emit_vehicle_blocked(
            eid,
            vehicle_prop,
            reason="route_required",
        )
        return False

    def _enter_quick_travel_from_ramp(self, eid, pos, vehicle_prop=None):
        if vehicle_prop is None:
            vehicle_prop = self._active_vehicle_property(eid)
        ramp = self._quick_travel_ramp_near(pos.x, pos.y, pos.z)
        if not ramp:
            return False
        if not self._can_enter_quick_travel_from_local_vehicle(eid, pos):
            return False
        self._set_zoom_mode(
            eid=eid,
            pos=pos,
            mode="overworld",
            view_only=False,
            entry_reason="quick_travel_ramp",
            ramp_prop=ramp,
        )
        return True

    def _local_vehicle_discrete_controls(self):
        overlay = getattr(self.sim, "combat_overlay", {})
        return bool(getattr(self.sim, "turn_based", False)) or bool(isinstance(overlay, dict) and overlay.get("active"))

    def _local_vehicle_has_fuel(self, eid, pos, vehicle_prop):
        fuel, _fuel_capacity = _vehicle_fuel_values(vehicle_prop)
        if int(fuel) > 0:
            return True
        state = self._vehicle_state_for(eid)
        set_vehicle_speed(state, 0, tick=self.sim.tick, vehicle_prop=vehicle_prop)
        self._emit_vehicle_blocked(
            eid,
            vehicle_prop,
            reason="out_of_fuel",
            fuel_needed=1,
            chunk=self.sim.chunk_coords(pos.x, pos.y),
        )
        return False

    def _local_vehicle_is_usable(self, eid, vehicle_prop, state=None):
        if vehicle_is_usable(vehicle_prop):
            return True
        if state is None:
            state = self._vehicle_state_for(eid)
        set_vehicle_speed(state, 0, tick=self.sim.tick, vehicle_prop=vehicle_prop)
        self._emit_vehicle_blocked(eid, vehicle_prop, reason="vehicle_broken")
        return False

    def _move_local_vehicle_steps(self, eid, pos, vehicle_prop, state, move_dx, move_dy, move_steps=1, *, reason="vehicle_move"):
        moved_any = False
        for _step_index in range(int(max(0, move_steps))):
            target_x = int(pos.x) + int(move_dx)
            target_y = int(pos.y) + int(move_dy)
            target_z = int(pos.z)
            old_x, old_y, old_z = int(pos.x), int(pos.y), int(pos.z)
            moved, move_reason = try_vehicle_step(
                self.sim,
                eid,
                vehicle_prop,
                target_x,
                target_y,
                target_z,
                speed=max(1, int(getattr(state, "speed", 0) or 0)),
                reason=reason,
            )
            if not moved:
                set_vehicle_speed(state, 0, tick=self.sim.tick, vehicle_prop=vehicle_prop)
                if move_reason not in {"collision", "crash"}:
                    self._emit_vehicle_blocked(eid, vehicle_prop, reason=move_reason or "blocked_tile")
                return moved_any

            moved_any = True
            self.action_system._clear_cover(eid, reason=reason)
            self._emit_vehicle_motion_event(
                "vehicle_local_moved",
                eid,
                vehicle_prop,
                state,
                old_x=old_x,
                old_y=old_y,
                old_z=old_z,
                x=target_x,
                y=target_y,
                z=target_z,
                cruise_active=int(getattr(state, "speed", 0) or 0) > 0,
                reason=reason,
            )
            if self._maybe_auto_enter_quick_travel_ramp(eid, pos, vehicle_prop=vehicle_prop):
                return moved_any
            self._emit_nearby_onramp_notice(eid, pos, vehicle_prop=vehicle_prop)
        return moved_any

    def _handle_local_vehicle_move_discrete(self, eid, pos, dx, dy):
        state = self._vehicle_state_for(eid)
        vehicle_prop = self._active_vehicle_property(eid)
        if not state or not state.in_vehicle or not vehicle_prop:
            self._emit_vehicle_blocked(eid, vehicle_prop, reason="vehicle_required")
            return False
        if not self._local_vehicle_is_usable(eid, vehicle_prop, state):
            return False

        turn, thrust = self._vehicle_drive_command(dx, dy)
        if turn is None and thrust is None:
            return False

        if not self._local_vehicle_has_fuel(eid, pos, vehicle_prop):
            return False

        if turn:
            rotate_vehicle_heading(state, turn, tick=self.sim.tick)

        discrete_top_speed = min(2, vehicle_top_speed(vehicle_prop))
        old_speed = max(0, min(discrete_top_speed, int(getattr(state, "speed", 0) or 0)))
        set_vehicle_speed(state, old_speed, tick=self.sim.tick, vehicle_prop=vehicle_prop)
        move_dx = 0
        move_dy = 0
        move_steps = 0
        action = "turn"
        if thrust == "accelerate":
            action = "accelerate"
            new_speed = set_vehicle_speed(state, min(discrete_top_speed, old_speed + 1), tick=self.sim.tick, vehicle_prop=vehicle_prop)
            move_steps = int(new_speed)
            move_dx, move_dy = vehicle_heading_tuple(state)
        elif thrust == "brake":
            action = "brake"
            if old_speed > 0:
                set_vehicle_speed(state, max(0, old_speed - 1), tick=self.sim.tick, vehicle_prop=vehicle_prop)
            else:
                heading_dx, heading_dy = vehicle_heading_tuple(state)
                move_dx, move_dy = -heading_dx, -heading_dy
                move_steps = 1

        if move_steps <= 0:
            self._emit_vehicle_motion_event(
                "vehicle_local_controlled",
                eid,
                vehicle_prop,
                state,
                action=action,
                x=int(pos.x),
                y=int(pos.y),
                z=int(pos.z),
                cruise_active=False,
            )
            self._emit_nearby_onramp_notice(eid, pos, vehicle_prop=vehicle_prop)
            return True

        return self._move_local_vehicle_steps(
            eid,
            pos,
            vehicle_prop,
            state,
            move_dx,
            move_dy,
            move_steps,
            reason="vehicle_move",
        )

    def _handle_local_vehicle_move(self, eid, pos, dx, dy):
        if self._local_vehicle_discrete_controls():
            return self._handle_local_vehicle_move_discrete(eid, pos, dx, dy)

        state = self._vehicle_state_for(eid)
        vehicle_prop = self._active_vehicle_property(eid)
        if not state or not state.in_vehicle or not vehicle_prop:
            self._emit_vehicle_blocked(eid, vehicle_prop, reason="vehicle_required")
            return False
        if not self._local_vehicle_is_usable(eid, vehicle_prop, state):
            return False

        turn, thrust = self._vehicle_drive_command(dx, dy)
        if turn is None and thrust is None:
            return False
        if not self._local_vehicle_has_fuel(eid, pos, vehicle_prop):
            return False

        if turn:
            rotate_vehicle_heading(state, turn, tick=self.sim.tick)

        old_speed = clamp_vehicle_speed(vehicle_prop, getattr(state, "speed", 0))
        set_vehicle_speed(state, old_speed, tick=self.sim.tick, vehicle_prop=vehicle_prop)
        move_dx = 0
        move_dy = 0
        move_steps = 0
        action = "turn"
        if thrust == "accelerate":
            action = "accelerate"
            set_vehicle_speed(state, old_speed + 1, tick=self.sim.tick, vehicle_prop=vehicle_prop)
            move_steps = 1
            move_dx, move_dy = vehicle_heading_tuple(state)
        elif thrust == "brake":
            action = "brake"
            if old_speed > 0:
                set_vehicle_speed(state, old_speed - 1, tick=self.sim.tick, vehicle_prop=vehicle_prop)
            else:
                heading_dx, heading_dy = vehicle_heading_tuple(state)
                move_dx, move_dy = -heading_dx, -heading_dy
                move_steps = 1

        if move_steps <= 0:
            self._emit_vehicle_motion_event(
                "vehicle_local_controlled",
                eid,
                vehicle_prop,
                state,
                action=action,
                x=int(pos.x),
                y=int(pos.y),
                z=int(pos.z),
                cruise_active=int(getattr(state, "speed", 0) or 0) > 0,
            )
            self._emit_nearby_onramp_notice(eid, pos, vehicle_prop=vehicle_prop)
            return True

        moved_any = self._move_local_vehicle_steps(
            eid,
            pos,
            vehicle_prop,
            state,
            move_dx,
            move_dy,
            move_steps,
            reason="vehicle_move",
        )
        if str(getattr(self.sim, "zoom_mode", "city")).strip().lower() == "overworld":
            return moved_any
        self._emit_vehicle_motion_event(
            "vehicle_local_controlled",
            eid,
            vehicle_prop,
            state,
            action=action,
            x=int(pos.x),
            y=int(pos.y),
            z=int(pos.z),
            cruise_active=int(getattr(state, "speed", 0) or 0) > 0,
        )
        self._emit_nearby_onramp_notice(eid, pos, vehicle_prop=vehicle_prop)
        return moved_any

    def _handle_local_vehicle_momentum(self, eid, pos):
        state = self._vehicle_state_for(eid)
        vehicle_prop = self._active_vehicle_property(eid)
        if not state or not state.in_vehicle or not vehicle_prop:
            self._emit_vehicle_blocked(eid, vehicle_prop, reason="vehicle_required")
            return False
        if not self._local_vehicle_is_usable(eid, vehicle_prop, state):
            return False
        if self._local_vehicle_discrete_controls():
            return False
        if not self._local_vehicle_has_fuel(eid, pos, vehicle_prop):
            return False
        if int(getattr(state, "speed", 0) or 0) <= 0:
            return False
        move_dx, move_dy = vehicle_heading_tuple(state)
        return self._move_local_vehicle_steps(
            eid,
            pos,
            vehicle_prop,
            state,
            move_dx,
            move_dy,
            1,
            reason="vehicle_momentum",
        )

    def _vehicle_fuel_cost_for_chunk(self, vehicle_prop, desc):
        profile = _vehicle_profile_from_property(vehicle_prop)
        if not profile:
            return 0

        terrain = str((desc or {}).get("terrain", "plains")).strip().lower() or "plains"
        path = str((desc or {}).get("path", "")).strip().lower()
        base = float(self.VEHICLE_BASE_FUEL_COST)
        base *= float(self.VEHICLE_PATH_FUEL_MULT.get(path, 1.0))
        base *= float(self.VEHICLE_TERRAIN_FUEL_MULT.get(terrain, 1.0))

        fuel_efficiency = max(1, min(10, _int_or_default(profile.get("fuel_efficiency"), 5)))
        power = max(1, min(10, _int_or_default(profile.get("power"), 5)))
        durability = max(1, min(10, _int_or_default(profile.get("durability"), 5)))
        efficiency_mult = max(0.48, min(1.12, 1.18 - (float(fuel_efficiency) * 0.065)))
        base *= efficiency_mult
        if durability < 6:
            base *= (1.0 + ((6 - durability) * 0.04))

        if terrain in self.VEHICLE_ROUGH_TERRAINS:
            if power >= 7:
                base *= 0.95
            elif power <= 3:
                base *= 1.10
            if durability >= 8:
                base *= 0.96
            elif durability <= 3:
                base *= 1.12

        return max(1, int(round(base)))

    def _enter_vehicle(self, eid, pos, vehicle_prop):
        state = self._vehicle_state_for(eid)
        if not state or not _property_is_vehicle(vehicle_prop):
            self.sim.emit(Event(
                "vehicle_action_blocked",
                eid=eid,
                reason="no_vehicle_state",
            ))
            return False

        vehicle_id = str(vehicle_prop.get("id", "")).strip()
        if not vehicle_id:
            self.sim.emit(Event("vehicle_action_blocked", eid=eid, reason="invalid_vehicle"))
            return False
        if not vehicle_is_usable(vehicle_prop):
            self.sim.emit(Event(
                "vehicle_action_blocked",
                eid=eid,
                reason="vehicle_broken",
                vehicle_id=vehicle_id,
                vehicle_name=_vehicle_label(vehicle_prop),
            ))
            return False

        owner_tag = str(vehicle_prop.get("owner_tag", "")).strip().lower()
        lock_state = property_lock_state(vehicle_prop)
        has_key = self.action_system._property_key_entry_for(eid, vehicle_prop) is not None
        owned_by_actor = vehicle_prop.get("owner_eid") == eid or owner_tag == "player"
        public_vehicle = is_public_owner_tag(owner_tag)
        entry_method = "public"

        if owned_by_actor:
            if lock_state["locked"] and not has_key:
                self.sim.emit(Event(
                    "vehicle_action_blocked",
                    eid=eid,
                    reason="missing_key",
                    vehicle_id=vehicle_id,
                    vehicle_name=_vehicle_label(vehicle_prop),
                ))
                return False
            entry_method = "key" if has_key else "owner"
        elif has_key:
            entry_method = "key"
        elif public_vehicle and not lock_state["locked"]:
            entry_method = "public"
        else:
            theft_ok, block_reason, entry_method = self.action_system._attempt_vehicle_theft(eid, pos, vehicle_prop)
            if not theft_ok:
                self.sim.emit(Event(
                    "vehicle_action_blocked",
                    eid=eid,
                    reason=block_reason,
                    vehicle_id=vehicle_id,
                    vehicle_name=_vehicle_label(vehicle_prop),
                    lock_tier=lock_state["lock_tier"],
                ))
                return False

        medium = vehicle_medium_for_property(vehicle_prop)
        board_tile = (int(pos.x), int(pos.y), int(pos.z))
        if medium == "water":
            board_tile = self._best_water_vehicle_board_tile(vehicle_prop, pos)
            if board_tile is None:
                self._emit_vehicle_blocked(eid, vehicle_prop, reason="water_access_required")
                return False

        state.set_active_vehicle(vehicle_id, tick=self.sim.tick)
        state.set_in_vehicle(True, tick=self.sim.tick)
        state.medium = medium
        set_vehicle_speed(state, 0, tick=self.sim.tick)

        if medium == "water" and board_tile != (int(pos.x), int(pos.y), int(pos.z)):
            self._teleport_entity(eid, pos, board_tile[0], board_tile[1], board_tile[2], reason="enter_vehicle")
        self._sync_vehicle_property_position(vehicle_prop, board_tile[0], board_tile[1], board_tile[2])
        self.sim.city_anchor_by_chunk[self.sim.chunk_coords(board_tile[0], board_tile[1])] = board_tile

        fuel, fuel_capacity = _vehicle_fuel_values(vehicle_prop)
        self.sim.emit(Event(
            "vehicle_entered",
            eid=eid,
            vehicle_id=vehicle_id,
            vehicle_name=_vehicle_label(vehicle_prop),
            fuel=fuel,
            fuel_capacity=fuel_capacity,
            entry_method=entry_method,
            stolen=entry_method == "hotwire",
        ))
        return True

    def _exit_vehicle(self, eid, pos):
        state = self._vehicle_state_for(eid)
        vehicle_prop = self._active_vehicle_property(eid)
        vehicle_medium = vehicle_medium_for_property(vehicle_prop) if vehicle_prop else "land"
        if vehicle_prop and vehicle_medium == "water":
            park_x, park_y, park_z = self._best_vehicle_exit_vehicle_tile(
                pos.x,
                pos.y,
                pos.z,
                vehicle_prop=vehicle_prop,
            )
            exit_tile = self._best_water_vehicle_exit_player_tile(park_x, park_y, park_z)
            if exit_tile is None:
                self._emit_vehicle_blocked(eid, vehicle_prop, reason="shore_exit_required")
                return False
        else:
            park_x = int(pos.x)
            park_y = int(pos.y)
            park_z = int(pos.z)
            if vehicle_prop:
                park_x, park_y, park_z = self._best_vehicle_exit_vehicle_tile(
                    pos.x,
                    pos.y,
                    pos.z,
                    vehicle_prop=vehicle_prop,
                )
            exit_tile = self._best_vehicle_exit_player_tile(
                park_x,
                park_y,
                park_z,
                vehicle_prop=vehicle_prop,
            )

        self._set_zoom_mode(eid=eid, pos=pos, mode="city")
        if state:
            state.set_in_vehicle(False, tick=self.sim.tick)
            set_vehicle_speed(state, 0, tick=self.sim.tick)
        self._set_local_ramp_auto_enter(False)

        if vehicle_prop:
            self._sync_vehicle_property_position(vehicle_prop, park_x, park_y, park_z)
            fuel, fuel_capacity = _vehicle_fuel_values(vehicle_prop)
        else:
            fuel = 0
            fuel_capacity = 0

        exit_x, exit_y, exit_z = exit_tile
        if (exit_x, exit_y, exit_z) != (int(pos.x), int(pos.y), int(pos.z)):
            self._teleport_entity(eid, pos, exit_x, exit_y, exit_z, reason="exit_vehicle")

        if vehicle_prop:
            self.sim.emit(Event(
                "vehicle_exited",
                eid=eid,
                vehicle_id=vehicle_prop.get("id"),
                vehicle_name=_vehicle_label(vehicle_prop),
                fuel=fuel,
                fuel_capacity=fuel_capacity,
            ))
        return True

    def _vehicle_exit_tile_candidates(self, x, y, z=0, *, max_radius=8):
        yield int(x), int(y), int(z), 0, 0
        for radius in range(1, int(max_radius) + 1):
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    chebyshev = max(abs(dx), abs(dy))
                    if chebyshev != radius:
                        continue
                    yield int(x + dx), int(y + dy), int(z), chebyshev, abs(dx) + abs(dy)

    def _water_vehicle_tile_usable(self, vehicle_prop, x, y, z=0):
        if self.sim.detail_for_xy(int(x), int(y)) == "unloaded":
            return False
        if not self.sim.tilemap.in_bounds(int(x), int(y)):
            return False
        tile = self.sim.tilemap.tile_at(int(x), int(y), int(z))
        if not tile or str(getattr(tile, "glyph", "") or "")[:1] != "~":
            return False
        if self.sim.structure_at(int(x), int(y), int(z)) is not None:
            return False
        active_vehicle_id = str((vehicle_prop or {}).get("id", "")).strip()
        covering = self.sim.property_covering(int(x), int(y), int(z))
        if (
            isinstance(covering, dict)
            and str(covering.get("id", "")).strip() != active_vehicle_id
        ):
            return False
        return True

    def _best_water_vehicle_tile_near(self, vehicle_prop, x, y, z=0, *, max_radius=3):
        for tx, ty, tz, _chebyshev, _manhattan in self._vehicle_exit_tile_candidates(
            x,
            y,
            z,
            max_radius=max_radius,
        ):
            if self._water_vehicle_tile_usable(vehicle_prop, tx, ty, tz):
                return tx, ty, tz
        return None

    def _best_water_vehicle_board_tile(self, vehicle_prop, pos):
        seeds = (
            (
                int((vehicle_prop or {}).get("x", getattr(pos, "x", 0)) or 0),
                int((vehicle_prop or {}).get("y", getattr(pos, "y", 0)) or 0),
                int((vehicle_prop or {}).get("z", getattr(pos, "z", 0)) or 0),
            ),
            (int(pos.x), int(pos.y), int(pos.z)),
        )
        seen = set()
        for sx, sy, sz in seeds:
            key = (sx, sy, sz)
            if key in seen:
                continue
            seen.add(key)
            tile = self._best_water_vehicle_tile_near(vehicle_prop, sx, sy, sz, max_radius=3)
            if tile is not None:
                return tile
        return None

    def _best_water_vehicle_exit_player_tile(self, vehicle_x, vehicle_y, vehicle_z=0):
        best = None
        for tx, ty, tz, chebyshev, manhattan in self._vehicle_exit_tile_candidates(
            vehicle_x,
            vehicle_y,
            vehicle_z,
            max_radius=2,
        ):
            if chebyshev == 0:
                continue
            tile = self.sim.tilemap.tile_at(tx, ty, tz)
            if not tile or not tile.walkable:
                continue
            inside = self.sim.structure_at(tx, ty, tz) is not None
            score = (
                1 if inside else 0,
                chebyshev,
                manhattan,
                abs(ty - int(vehicle_y)),
                abs(tx - int(vehicle_x)),
                ty,
                tx,
            )
            if best is None or score < best[0]:
                best = (score, (tx, ty, tz))
        if best:
            return best[1]
        return None

    def _best_vehicle_exit_vehicle_tile(self, x, y, z=0, *, vehicle_prop=None):
        if vehicle_prop and vehicle_medium_for_property(vehicle_prop) == "water":
            tile = self._best_water_vehicle_tile_near(vehicle_prop, x, y, z, max_radius=3)
            if tile is not None:
                return tile
            return int(x), int(y), int(z)

        best = None
        for tx, ty, tz, chebyshev, manhattan in self._vehicle_exit_tile_candidates(x, y, z, max_radius=8):
            tile = self.sim.tilemap.tile_at(tx, ty, tz)
            if not tile or not tile.walkable:
                continue
            inside = self.sim.structure_at(tx, ty, tz) is not None or self.sim.property_covering(tx, ty, tz) is not None
            if inside:
                continue
            score = (1 if inside else 0, chebyshev, manhattan, abs(ty - int(y)), abs(tx - int(x)), ty, tx)
            if best is None or score < best[0]:
                best = (score, (tx, ty, tz))
                if score[0] == 0 and chebyshev == 0:
                    break
        if best:
            return best[1]
        return int(x), int(y), int(z)

    def _best_vehicle_exit_player_tile(self, vehicle_x, vehicle_y, vehicle_z=0, *, vehicle_prop=None):
        if vehicle_prop and vehicle_medium_for_property(vehicle_prop) == "water":
            return self._best_water_vehicle_exit_player_tile(vehicle_x, vehicle_y, vehicle_z) or (
                int(vehicle_x),
                int(vehicle_y),
                int(vehicle_z),
            )

        preferred = (
            (0, 1),
            (1, 0),
            (-1, 0),
            (0, -1),
            (1, 1),
            (-1, 1),
            (1, -1),
            (-1, -1),
        )
        best = None
        for dx, dy in preferred:
            tx = int(vehicle_x) + int(dx)
            ty = int(vehicle_y) + int(dy)
            tz = int(vehicle_z)
            tile = self.sim.tilemap.tile_at(tx, ty, tz)
            if not tile or not tile.walkable:
                continue
            inside = self.sim.structure_at(tx, ty, tz) is not None
            score = (1 if inside else 0, abs(dy), abs(dx), ty, tx)
            if best is None or score < best[0]:
                best = (score, (tx, ty, tz))
                if score[0] == 0:
                    break
        if best:
            return best[1]
        return int(vehicle_x), int(vehicle_y), int(vehicle_z)

    def _find_walkable_near(self, x, y, z=0, radius=8):
        if self.sim.tilemap.is_walkable(x, y, z):
            return x, y
        for r in range(1, max(1, int(radius)) + 1):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if abs(dx) != r and abs(dy) != r:
                        continue
                    nx = x + dx
                    ny = y + dy
                    if self.sim.detail_for_xy(nx, ny) == "unloaded":
                        continue
                    if self.sim.tilemap.is_walkable(nx, ny, z):
                        return nx, ny
        return x, y

    def _teleport_entity(self, eid, pos, new_x, new_y, new_z, reason="teleport"):
        old_x = pos.x
        old_y = pos.y
        old_z = pos.z
        if (old_x, old_y, old_z) == (new_x, new_y, new_z):
            return

        self.sim.tilemap.move_entity(
            eid,
            oldx=old_x,
            oldy=old_y,
            oldz=old_z,
            newx=new_x,
            newy=new_y,
            newz=new_z,
        )
        pos.x = int(new_x)
        pos.y = int(new_y)
        pos.z = int(new_z)

        self.sim.emit(Event(
            "entity_moved",
            eid=eid,
            old_x=old_x,
            old_y=old_y,
            old_z=old_z,
            x=pos.x,
            y=pos.y,
            z=pos.z,
            reason=reason,
        ))

    def _chunk_center(self, chunk_coord):
        cx, cy = chunk_coord
        ox, oy = self.sim.chunk_origin(cx, cy)
        half = max(2, self.sim.chunk_size // 2)
        return ox + half, oy + half

    def _set_zoom_mode(self, eid, pos, mode, *, view_only=None, entry_reason="", ramp_prop=None):
        mode = str(mode).lower()
        if mode not in {"city", "overworld"}:
            return

        current_chunk = self.sim.chunk_coords(pos.x, pos.y)
        if mode == "overworld":
            state = self._vehicle_state_for(eid)
            vehicle_prop = self._active_vehicle_property(eid)
            if view_only is None:
                view_only = not bool(state and state.in_vehicle and vehicle_prop)
            view_only = bool(view_only)
            if not view_only and vehicle_medium_for_property(vehicle_prop) == "water":
                self._emit_vehicle_blocked(eid, vehicle_prop, reason="water_map_unavailable")
                return

            self.sim.city_anchor_by_chunk[current_chunk] = (pos.x, pos.y, pos.z)
            self.sim.zoom_mode = "overworld"
            self._set_overworld_view_only(eid, view_only)
            if state:
                set_vehicle_speed(state, 0, tick=self.sim.tick)
            tx, ty = self._chunk_center(current_chunk)
            self.sim.stream_world(tx, ty)
            self.sim.ensure_loaded_chunk_terrain()
            tx, ty = self._find_walkable_near(tx, ty, z=0, radius=6)
            self._teleport_entity(eid, pos, tx, ty, 0, reason="zoom_overworld")
            if not view_only and vehicle_prop:
                self._sync_vehicle_property_position(vehicle_prop, tx, ty, 0)
            self.action_system._clear_cover(eid, reason="zoom")
            desc = self.sim.world.overworld_descriptor(current_chunk[0], current_chunk[1])
            interest = self.sim.world.overworld_interest(current_chunk[0], current_chunk[1], descriptor=desc)
            travel = _overworld_travel_profile(self.sim, current_chunk[0], current_chunk[1], desc=desc, interest=interest)
            discovery = _overworld_discovery_profile(
                self.sim,
                current_chunk[0],
                current_chunk[1],
                desc=desc,
                interest=interest,
                travel=travel,
            )
            identity = _overworld_identity_profile(
                self.sim,
                current_chunk[0],
                current_chunk[1],
                desc=desc,
                interest=interest,
                travel=travel,
                discovery=discovery,
            )
            self.action_system._remember_overworld_chunk_memory(
                eid,
                current_chunk,
                desc=desc,
                interest=interest,
                travel=travel,
                discovery=discovery,
                identity=identity,
                source="current",
            )
            self.sim.emit(Event(
                "zoom_mode_changed",
                eid=eid,
                mode="overworld",
                chunk=current_chunk,
                view_only=view_only,
                entry_reason=str(entry_reason or "").strip().lower(),
                ramp_property_id=(ramp_prop or {}).get("id") if isinstance(ramp_prop, dict) else None,
                ramp_name=str((ramp_prop or {}).get("name", "") if isinstance(ramp_prop, dict) else "").strip(),
            ))
            return

        chunk = self.sim.world.get_chunk(current_chunk[0], current_chunk[1])
        district = chunk.get("district", {})
        area_type = str(district.get("area_type", "city")).lower()
        state = self._vehicle_state_for(eid)
        vehicle_prop = self._active_vehicle_property(eid)
        vehicle_medium = vehicle_medium_for_property(vehicle_prop) if vehicle_prop else "land"
        self.sim.zoom_mode = "city"
        self._set_overworld_view_only(eid, False)
        anchor = self.sim.city_anchor_by_chunk.get(current_chunk)
        if not anchor:
            ax, ay = self._chunk_center(current_chunk)
            anchor = (ax, ay, 0)

        tx, ty, tz = int(anchor[0]), int(anchor[1]), int(anchor[2])
        self.sim.stream_world(tx, ty)
        self.sim.ensure_loaded_chunk_terrain()
        if (
            state
            and state.in_vehicle
            and vehicle_prop
            and not self._local_route_accessible_at(tx, ty, tz, ignore_property_id=vehicle_prop.get("id"))
        ):
            route_anchor = self._find_route_access_near(
                tx,
                ty,
                z=tz,
                radius=10,
                ignore_property_id=vehicle_prop.get("id"),
            )
            if route_anchor:
                tx, ty, tz = route_anchor
        if not (state and state.in_vehicle and vehicle_prop and vehicle_medium == "water"):
            tx, ty = self._find_walkable_near(tx, ty, z=tz, radius=8)
        self._teleport_entity(eid, pos, tx, ty, tz, reason="zoom_city")
        if state and state.in_vehicle and vehicle_prop:
            self._sync_vehicle_property_position(vehicle_prop, tx, ty, tz)
        self.action_system._clear_cover(eid, reason="zoom")
        self.sim.emit(Event(
            "zoom_mode_changed",
            eid=eid,
            mode="city",
            chunk=current_chunk,
            area_type=area_type,
        ))

    def _handle_overworld_travel(self, eid, pos, dx, dy):
        state = self._vehicle_state_for(eid)
        vehicle_prop = self._active_vehicle_property(eid)
        if not state or not state.in_vehicle or not vehicle_prop:
            self.sim.emit(Event(
                "vehicle_action_blocked",
                eid=eid,
                reason="vehicle_required",
            ))
            return
        if vehicle_medium_for_property(vehicle_prop) == "water":
            self._emit_vehicle_blocked(eid, vehicle_prop, reason="water_map_unavailable")
            return

        step_x = 1 if dx > 0 else -1 if dx < 0 else 0
        step_y = 1 if dy > 0 else -1 if dy < 0 else 0
        if step_x == 0 and step_y == 0:
            return

        from_chunk = self.sim.chunk_coords(pos.x, pos.y)
        target_chunk = (from_chunk[0] + step_x, from_chunk[1] + step_y)
        desc = self.sim.world.overworld_descriptor(target_chunk[0], target_chunk[1])
        interest = self.sim.world.overworld_interest(target_chunk[0], target_chunk[1], descriptor=desc)
        travel = _overworld_travel_profile(self.sim, target_chunk[0], target_chunk[1], desc=desc, interest=interest)
        discovery = _overworld_discovery_profile(
            self.sim,
            target_chunk[0],
            target_chunk[1],
            desc=desc,
            interest=interest,
            travel=travel,
        )
        identity = _overworld_identity_profile(
            self.sim,
            target_chunk[0],
            target_chunk[1],
            desc=desc,
            interest=interest,
            travel=travel,
            discovery=discovery,
        )

        fuel_cost = self._vehicle_fuel_cost_for_chunk(vehicle_prop, desc=desc)
        fuel, fuel_capacity = _vehicle_fuel_values(vehicle_prop)
        if fuel_cost > fuel:
            self.sim.emit(Event(
                "vehicle_action_blocked",
                eid=eid,
                reason="out_of_fuel",
                vehicle_id=vehicle_prop.get("id"),
                vehicle_name=_vehicle_label(vehicle_prop),
                fuel=fuel,
                fuel_capacity=fuel_capacity,
                fuel_needed=fuel_cost,
                chunk=target_chunk,
            ))
            return

        self.action_system._overworld_visit_state_for(eid).add((int(from_chunk[0]), int(from_chunk[1])))
        self.action_system._remember_overworld_chunk_memory(eid, from_chunk, source="visit")
        tx, ty = self._chunk_center(target_chunk)

        self.sim.stream_world(tx, ty)
        self.sim.ensure_loaded_chunk_terrain()
        tx, ty = self._find_walkable_near(tx, ty, z=0, radius=6)
        self.sim.city_anchor_by_chunk[target_chunk] = (int(tx), int(ty), 0)
        self._teleport_entity(eid, pos, tx, ty, 0, reason="overworld_travel")
        self._sync_vehicle_property_position(vehicle_prop, tx, ty, 0)
        set_vehicle_speed(state, 0, tick=self.sim.tick)
        self.action_system._clear_cover(eid, reason="zoom")

        chunk = self.sim.world.get_chunk(target_chunk[0], target_chunk[1])
        district = chunk.get("district", {})
        energy_cost = int(travel.get("energy_cost", 0))
        safety_cost = int(travel.get("safety_cost", 0))
        social_cost = int(travel.get("social_cost", 0))

        vehicle_meta = _property_metadata(vehicle_prop)
        vehicle_meta["fuel"] = max(0, int(fuel) - int(fuel_cost))
        remaining_fuel, fuel_capacity = _vehicle_fuel_values(vehicle_prop)

        needs = self.sim.ecs.get(NPCNeeds).get(eid)
        if needs:
            if energy_cost > 0:
                needs.energy = _clamp(float(needs.energy) - energy_cost)
            if safety_cost > 0:
                needs.safety = _clamp(float(needs.safety) - safety_cost)
            if social_cost > 0:
                needs.social = _clamp(float(needs.social) - social_cost)
        self.action_system._remember_overworld_chunk_memory(
            eid,
            target_chunk,
            desc=desc,
            interest=interest,
            travel=travel,
            discovery=discovery,
            identity=identity,
            source="visit",
        )
        nearest_landmark = desc.get("nearest_landmark") or {}
        self.sim.emit(Event(
            "overworld_travelled",
            eid=eid,
            from_chunk=from_chunk,
            to_chunk=target_chunk,
            area_type=district.get("area_type", "city"),
            district_type=district.get("district_type", "unknown"),
            terrain=desc.get("terrain"),
            path=desc.get("path"),
            region_name=desc.get("region_name"),
            settlement_name=desc.get("settlement_name"),
            landmark=(
                (desc.get("landmark") or {}).get("name")
                or nearest_landmark.get("name")
            ),
            interest=interest.get("detail"),
            identity=identity.get("label"),
            identity_hook=identity.get("hook"),
            risk=travel.get("risk_label"),
            support=travel.get("support_label"),
            energy_cost=energy_cost,
            safety_cost=safety_cost,
            social_cost=social_cost,
            fuel_cost=int(fuel_cost),
            fuel_left=int(remaining_fuel),
            fuel_capacity=int(fuel_capacity),
            vehicle_name=_vehicle_label(vehicle_prop),
        ))
        self._award_overworld_discovery(
            eid=eid,
            chunk=target_chunk,
            desc=desc,
            interest=interest,
            travel=travel,
        )

    def _overworld_discovery_lines(self, eid, cx, cy, radius=1):
        radius = max(1, int(radius))
        rows = []
        for qy in range(cy - radius, cy + radius + 1):
            for qx in range(cx - radius, cx + radius + 1):
                if (qx, qy) == (cx, cy):
                    continue
                desc = self.sim.world.overworld_descriptor(qx, qy)
                interest = self.sim.world.overworld_interest(qx, qy, descriptor=desc)
                travel = _overworld_travel_profile(self.sim, qx, qy, desc=desc, interest=interest)
                discovery = _overworld_discovery_profile(self.sim, qx, qy, desc=desc, interest=interest, travel=travel)
                identity = _overworld_identity_profile(
                    self.sim,
                    qx,
                    qy,
                    desc=desc,
                    interest=interest,
                    travel=travel,
                    discovery=discovery,
                )
                landmark = desc.get("landmark") or desc.get("nearest_landmark") or {}
                landmark_name = str(landmark.get("name", "")).strip()
                interest_detail = str(interest.get("detail", "")).strip()
                path = str(desc.get("path", "")).strip()
                if not landmark_name and not interest_detail and not path:
                    continue
                self.action_system._remember_overworld_chunk_memory(
                    eid,
                    (qx, qy),
                    desc=desc,
                    interest=interest,
                    travel=travel,
                    discovery=discovery,
                    identity=identity,
                    source="scout",
                )
                terrain = str(desc.get("terrain", "plain")).replace("_", " ").strip()
                area_type = str(desc.get("area_type", "city"))
                district_type = str(desc.get("district_type", "unknown"))
                parts = [
                    f"({qx},{qy}) {area_type}/{district_type}",
                    f"terr:{terrain}",
                ]
                if path:
                    parts.append(f"path:{path}")
                if landmark_name:
                    parts.append(f"landmark:{landmark_name}")
                if interest_detail:
                    parts.append(f"poi:{interest_detail}")
                parts.extend(_overworld_travel_summary_bits(travel))
                dist = _manhattan(cx, cy, qx, qy)
                score = 0
                if landmark_name:
                    score += 3
                if interest_detail:
                    score += 2
                if path:
                    score += 1
                rows.append((
                    -score,
                    dist,
                    qx,
                    qy,
                    _overworld_legend_line(self.sim, qx, qy, " ".join(parts)),
                ))
        rows.sort()
        return [row[4] for row in rows[:3]]

    def _award_overworld_discovery(self, eid, chunk, desc, interest, travel):
        chunk_key = (int(chunk[0]), int(chunk[1]))
        visits = self.action_system._overworld_visit_state_for(eid)
        if chunk_key in visits:
            return
        visits.add(chunk_key)

        discovery = _overworld_discovery_profile(
            self.sim,
            chunk_key[0],
            chunk_key[1],
            desc=desc,
            interest=interest,
            travel=travel,
        )
        kind = str(discovery.get("kind", "")).strip().lower()
        if not kind:
            return

        rng = random.Random(f"{self.sim.seed}:travel-discovery:{eid}:{chunk_key[0]}:{chunk_key[1]}:{kind}")
        assets = self.sim.ecs.get(PlayerAssets).get(eid)
        needs = self.sim.ecs.get(NPCNeeds).get(eid)
        inventory = self.action_system._inventory_for(eid)

        energy_gain = int(max(0, discovery.get("energy_gain", 0)))
        safety_gain = int(max(0, discovery.get("safety_gain", 0)))
        social_gain = int(max(0, discovery.get("social_gain", 0)))
        credits_gain = 0
        item_id = None
        item_name = ""
        intel_lines = []

        if kind in {"salvage", "tools"}:
            low = int(max(0, discovery.get("credits_min", 0)))
            high = int(max(low, discovery.get("credits_max", low)))
            credits_gain += rng.randint(low, high)

        item_pool = [
            str(candidate).strip()
            for candidate in discovery.get("item_pool", ())
            if str(candidate).strip() in ITEM_CATALOG
        ]
        if item_pool and inventory:
            should_roll_item = kind in {"supplies", "tools"}
            if should_roll_item:
                candidate = rng.choice(item_pool)
                item_def = ITEM_CATALOG.get(candidate, {})
                added, _instance_id = inventory.add_item(
                    item_id=candidate,
                    quantity=1,
                    stack_max=int(item_def.get("stack_max", 1)),
                    instance_factory=self.sim.new_item_instance_id,
                    owner_eid=eid,
                    owner_tag="player" if self.sim.ecs.get(PlayerControlled).get(eid) else "npc",
                    metadata={"overworld_discovery": kind, "chunk": chunk_key},
                )
                if added:
                    item_id = candidate
                    item_name = str(item_def.get("name", candidate))
                else:
                    credits_gain += 4

        if needs:
            if energy_gain > 0:
                needs.energy = _clamp(float(needs.energy) + energy_gain)
            if safety_gain > 0:
                needs.safety = _clamp(float(needs.safety) + safety_gain)
            if social_gain > 0:
                needs.social = _clamp(float(needs.social) + social_gain)
        else:
            energy_gain = 0
            safety_gain = 0
            social_gain = 0

        if assets and credits_gain > 0:
            assets.credits += credits_gain
        elif credits_gain > 0:
            credits_gain = 0

        intel_radius = int(max(0, discovery.get("intel_radius", 0)))
        if intel_radius > 0:
            intel_lines = self._overworld_discovery_lines(eid, chunk_key[0], chunk_key[1], radius=intel_radius)

        if (
            credits_gain <= 0
            and energy_gain <= 0
            and safety_gain <= 0
            and social_gain <= 0
            and not item_id
            and not intel_lines
        ):
            return

        self.sim.emit(Event(
            "overworld_discovery_found",
            eid=eid,
            chunk=chunk_key,
            kind=kind,
            label=str(discovery.get("label", kind)).strip() or kind,
            credits_gain=credits_gain,
            energy_gain=energy_gain,
            safety_gain=safety_gain,
            social_gain=social_gain,
            item_id=item_id,
            item_name=item_name,
            intel_lines=intel_lines,
        ))
