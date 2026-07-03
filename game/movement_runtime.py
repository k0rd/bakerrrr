"""Shared entity movement and doorway transition helpers."""

from engine.events import Event

from game.aerosol_trap_runtime import actor_knows_armed_aerosol_trap_at
from game.components import AI, Collider, Position
from game.property_access import (
    evaluate_property_access as _evaluate_property_access,
    property_ingress_context as _property_ingress_context,
)
from game.property_doors import (
    _actor_is_animal_or_wildlife,
    _door_property_at,
    _door_open_attempt,
    _operable_door_state_at,
)
from game.property_keys import property_lock_state
from game.property_runtime import (
    property_aperture_at as _property_aperture_at,
    property_covering as _property_covering,
)
from game.system_support.fire_runtime import fire_cell_state


def _entity_blocks(sim, moving_eid, x, y, z):
    colliders = sim.ecs.get(Collider)

    for other_eid in sim.tilemap.entities_at(x, y, z):
        if other_eid == moving_eid:
            continue

        collider = colliders.get(other_eid)
        if collider and collider.blocks:
            return True, other_eid

    return False, None


def _auto_open_closed_door_for_move(sim, eid, from_x, from_y, to_x, to_y, z, *, move_reason="move"):
    state = _operable_door_state_at(sim, to_x, to_y, z)
    if state is None or bool(state.get("open", False)) or bool(state.get("broken", False)):
        return True, None
    return _door_open_attempt(
        sim,
        eid,
        to_x,
        to_y,
        z,
        allow_override=False,
    )


def _closed_door_move_block_reason(sim, eid, x, y, z):
    state = _operable_door_state_at(sim, x, y, z)
    if state is None or bool(state.get("open", False)) or bool(state.get("broken", False)):
        return None
    if _actor_is_animal_or_wildlife(sim, eid):
        return "blocked_animal_doorway"

    positions = sim.ecs.get(Position)
    pos = positions.get(eid)
    if not pos:
        return "missing_position"

    prop = _door_property_at(sim, x, y, z, state=state)
    ingress = None
    if prop:
        ingress = _property_ingress_context(
            prop,
            from_x=pos.x,
            from_y=pos.y,
            from_z=pos.z,
            to_x=x,
            to_y=y,
            to_z=z,
        )
    if prop:
        access = _evaluate_property_access(
            sim,
            eid,
            prop,
            x=x,
            y=y,
            z=z,
            breach_severity=float(getattr(ingress, "breach_severity", 0.0) or 0.0),
        )
        if access.permitted:
            return "closed_door"
        lock_state = property_lock_state(prop)
        if bool(lock_state.get("locked")):
            return "locked_property"
        if access.access_level == "public" and access.currently_open is False:
            return "closed_property"
        return "door_access_denied"
    if bool(state.get("locked", False)):
        return "locked_door"
    return "closed_door"


def _closed_door_is_plannable_transition(sim, eid, from_x, from_y, to_x, to_y, z):
    state = _operable_door_state_at(sim, to_x, to_y, z)
    if state is None or bool(state.get("open", False)) or bool(state.get("broken", False)):
        return False
    if _actor_is_animal_or_wildlife(sim, eid):
        return False
    positions = sim.ecs.get(Position)
    actor_pos = positions.get(eid)
    if actor_pos is None:
        return False

    if eid != getattr(sim, "player_eid", None):
        ai = sim.ecs.get(AI).get(eid) if eid is not None else None
        if ai is not None:
            fire_cell = fire_cell_state(sim, to_x, to_y, z)
            if isinstance(fire_cell, dict) and int(fire_cell.get("fire_intensity", 0) or 0) > 0:
                return False

    prop = _door_property_at(sim, to_x, to_y, z, state=state)
    if prop:
        ingress = _property_ingress_context(
            prop,
            from_x=from_x,
            from_y=from_y,
            from_z=z,
            to_x=to_x,
            to_y=to_y,
            to_z=z,
        )
        actor_prop = _property_covering(sim, int(actor_pos.x), int(actor_pos.y), int(actor_pos.z))
        actor_inside_same_prop = bool(
            isinstance(actor_prop, dict)
            and str(actor_prop.get("id", "") or "").strip() == str(prop.get("id", "") or "").strip()
        )
        if ingress and ingress.from_inside and actor_inside_same_prop:
            return True

        access = _evaluate_property_access(
            sim,
            eid,
            prop,
            x=to_x,
            y=to_y,
            z=z,
            breach_severity=float(getattr(ingress, "breach_severity", 0.0) or 0.0),
        )
        if access.permitted:
            return True

        lock_state = property_lock_state(prop)
        return not bool(lock_state.get("locked"))

    return not bool(state.get("locked", False))


def _movement_allows_auto_open(sim, eid, *, reason="move"):
    reason_key = str(reason or "").strip().lower()
    if reason_key in {"player_move", "vehicle_move", "vehicle_momentum", "npc_vehicle_move"}:
        return False
    return True


def _animal_npc_cannot_cross_doorway(sim, moving_eid, from_x, from_y, to_x, to_y, z):
    if not _actor_is_animal_or_wildlife(sim, moving_eid):
        return None

    origin_prop = _property_covering(sim, from_x, from_y, z)
    target_prop = _property_covering(sim, to_x, to_y, z)
    origin_id = origin_prop.get("id") if isinstance(origin_prop, dict) else None
    target_id = target_prop.get("id") if isinstance(target_prop, dict) else None

    if origin_id and target_id and origin_id == target_id:
        return None

    if target_prop:
        ingress = _property_ingress_context(
            target_prop,
            from_x=from_x,
            from_y=from_y,
            from_z=z,
            to_x=to_x,
            to_y=to_y,
            to_z=z,
        )
        if ingress.entered_bounds and ingress.ingress_kind in {"ordinary_entry", "alternate_aperture"}:
            return "blocked_animal_doorway"

    if origin_prop and origin_id != target_id:
        aperture = _property_aperture_at(origin_prop, from_x, from_y, z)
        if aperture:
            return "blocked_animal_doorway"

    return None


def _is_traversable_for(sim, moving_eid, x, y, z):
    if sim.detail_for_xy(x, y) == "unloaded":
        return False, "out_of_bounds"
    if not sim.tilemap.in_bounds(x, y):
        return False, "out_of_bounds"
    if not sim.tilemap.is_walkable(x, y, z):
        return False, "blocked_tile"
    if moving_eid != getattr(sim, "player_eid", None):
        ai = sim.ecs.get(AI).get(moving_eid) if moving_eid is not None else None
        if ai is not None:
            fire_cell = fire_cell_state(sim, x, y, z)
            if isinstance(fire_cell, dict) and int(fire_cell.get("fire_intensity", 0) or 0) > 0:
                return False, "active_fire"
            if actor_knows_armed_aerosol_trap_at(sim, moving_eid, x, y, z):
                return False, "known_trap"
    blocked, blocker_eid = _entity_blocks(sim, moving_eid, x, y, z)
    if blocked:
        return False, f"blocked_entity:{blocker_eid}"
    return True, None


def _can_step_transition_for(sim, moving_eid, from_x, from_y, to_x, to_y, z):
    traversable, reason = _is_traversable_for(sim, moving_eid, to_x, to_y, z)
    if not traversable:
        if not (
            str(reason or "").strip().lower() == "blocked_tile"
            and _closed_door_is_plannable_transition(sim, moving_eid, from_x, from_y, to_x, to_y, z)
        ):
            return False, reason
    animal_transition_reason = _animal_npc_cannot_cross_doorway(
        sim,
        moving_eid,
        from_x,
        from_y,
        to_x,
        to_y,
        z,
    )
    if animal_transition_reason:
        return False, animal_transition_reason
    return True, None


def try_move_entity(sim, eid, new_x, new_y, new_z, reason="move"):
    positions = sim.ecs.get(Position)
    pos = positions.get(eid)
    if not pos:
        return False, "missing_position"

    if _movement_allows_auto_open(sim, eid, reason=reason):
        opened, open_reason = _auto_open_closed_door_for_move(
            sim,
            eid,
            pos.x,
            pos.y,
            new_x,
            new_y,
            new_z,
            move_reason=reason,
        )
        if not opened and open_reason is not None:
            return False, open_reason
    else:
        door_block_reason = _closed_door_move_block_reason(sim, eid, new_x, new_y, new_z)
        if door_block_reason is not None:
            return False, door_block_reason

    step_ok, reason_text = _can_step_transition_for(
        sim,
        moving_eid=eid,
        from_x=pos.x,
        from_y=pos.y,
        to_x=new_x,
        to_y=new_y,
        z=new_z,
    )
    if not step_ok:
        return False, reason_text

    old_x = pos.x
    old_y = pos.y
    old_z = pos.z

    sim.tilemap.move_entity(
        eid,
        oldx=old_x,
        oldy=old_y,
        oldz=old_z,
        newx=new_x,
        newy=new_y,
        newz=new_z,
    )

    pos.x = new_x
    pos.y = new_y
    pos.z = new_z

    sim.emit(Event(
        "entity_moved",
        eid=eid,
        old_x=old_x,
        old_y=old_y,
        old_z=old_z,
        x=new_x,
        y=new_y,
        z=new_z,
        reason=reason,
    ))

    return True, None
