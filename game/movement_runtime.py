"""Shared entity movement and doorway transition helpers."""

from dataclasses import dataclass, field

from engine.events import Event

from game.aerosol_trap_runtime import actor_known_armed_aerosol_trap_positions, actor_knows_armed_aerosol_trap_at
from game.mechanical_device_runtime import (
    actor_known_armed_mechanical_device_positions,
    actor_knows_armed_mechanical_device_at,
)
from game.components import AI, Collider, CreatureIdentity, Position
from game.property_access import (
    property_physical_access_for_actor as _property_physical_access_for_actor,
    property_ingress_context as _property_ingress_context,
)
from game.property_doors import (
    _actor_is_animal_or_wildlife,
    _door_is_physically_locked,
    _door_property_at,
    _door_open_attempt,
    _operable_door_state_at,
)
from game.property_runtime import (
    property_aperture_at as _property_aperture_at,
    property_covering as _property_covering,
)
from game.system_support.fire_runtime import fire_cell_state, fire_state


@dataclass(frozen=True, slots=True)
class MovementPlanningContext:
    """Actor-static and registry-view facts for one synchronous path search."""

    is_animal_or_wildlife: bool
    is_nonplayer_ai: bool
    known_armed_trap_positions: frozenset
    colliders: object
    fire_cells: object
    chunk_size: int
    chunk_detail: object
    world_coord_limit: int
    tiles_by_floor: object
    entities: object
    door_states: object
    door_access_permissions: dict = field(default_factory=dict, compare=False, repr=False)


def _entity_blocks(sim, moving_eid, x, y, z, *, colliders=None, entities=None):
    if colliders is None:
        colliders = sim.ecs.get(Collider)

    occupants = (
        entities.get((x, y, z), ())
        if isinstance(entities, dict)
        else sim.tilemap.entities_at(x, y, z)
    )
    for other_eid in occupants:
        if other_eid == moving_eid:
            continue

        collider = colliders.get(other_eid)
        if collider and collider.blocks:
            return True, other_eid

    return False, None


def _movement_planning_context(sim, moving_eid):
    """Hoist actor-static facts out of a single speculative path search."""
    ai = sim.ecs.get(AI).get(moving_eid) if moving_eid is not None else None
    identity = sim.ecs.get(CreatureIdentity).get(moving_eid) if moving_eid is not None else None
    role = str(getattr(ai, "role", "") or "").strip().lower()
    creature_type = str(getattr(identity, "creature_type", "") or "").strip().lower()
    is_nonplayer_ai = moving_eid != getattr(sim, "player_eid", None) and ai is not None
    state = fire_state(sim)
    cells = state.get("cells", {}) if isinstance(state, dict) else {}
    return MovementPlanningContext(
        is_animal_or_wildlife=role == "wildlife" or creature_type == "animal",
        is_nonplayer_ai=bool(is_nonplayer_ai),
        known_armed_trap_positions=(
            actor_known_armed_aerosol_trap_positions(sim, moving_eid)
            | actor_known_armed_mechanical_device_positions(sim, moving_eid)
            if is_nonplayer_ai
            else frozenset()
        ),
        colliders=sim.ecs.get(Collider),
        fire_cells=cells if isinstance(cells, dict) else {},
        chunk_size=max(1, int(getattr(sim, "chunk_size", 1) or 1)),
        chunk_detail=getattr(sim, "chunk_detail", {}),
        world_coord_limit=int(getattr(sim.tilemap, "world_coord_limit", 1_000_000) or 1_000_000),
        tiles_by_floor=getattr(sim.tilemap, "tiles_by_floor", {}),
        entities=getattr(sim.tilemap, "entities", {}),
        door_states=getattr(sim, "door_states", {}),
    )


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

    prop = _door_property_at(sim, x, y, z, state=state)
    if prop:
        if _door_is_physically_locked(state, prop):
            return "locked_property"
        return "closed_door"
    if _door_is_physically_locked(state):
        return "locked_door"
    return "closed_door"


def _closed_door_is_plannable_transition(sim, eid, from_x, from_y, to_x, to_y, z, *, planning_context=None):
    door_states = (
        planning_context.door_states
        if isinstance(planning_context, MovementPlanningContext)
        else None
    )
    state = _operable_door_state_at(sim, to_x, to_y, z, states=door_states)
    if state is None or bool(state.get("open", False)) or bool(state.get("broken", False)):
        return False
    is_animal = (
        planning_context.is_animal_or_wildlife
        if isinstance(planning_context, MovementPlanningContext)
        else bool(planning_context.get("is_animal_or_wildlife"))
        if isinstance(planning_context, dict)
        else _actor_is_animal_or_wildlife(sim, eid)
    )
    if is_animal:
        return False
    positions = sim.ecs.get(Position)
    actor_pos = positions.get(eid)
    if actor_pos is None:
        return False

    if isinstance(planning_context, MovementPlanningContext):
        is_nonplayer_ai = planning_context.is_nonplayer_ai
    elif isinstance(planning_context, dict):
        is_nonplayer_ai = bool(planning_context.get("is_nonplayer_ai"))
    else:
        is_nonplayer_ai = eid != getattr(sim, "player_eid", None) and sim.ecs.get(AI).get(eid) is not None
    if is_nonplayer_ai:
        fire_cell = (
            planning_context.fire_cells.get((int(to_x), int(to_y), int(z)))
            if isinstance(planning_context, MovementPlanningContext)
            else fire_cell_state(sim, to_x, to_y, z)
        )
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
            sim=sim,
        )
        actor_prop = _property_covering(sim, int(actor_pos.x), int(actor_pos.y), int(actor_pos.z))
        actor_inside_same_prop = bool(
            isinstance(actor_prop, dict)
            and str(actor_prop.get("id", "") or "").strip() == str(prop.get("id", "") or "").strip()
        )
        if ingress and ingress.from_inside and actor_inside_same_prop:
            return True

        if not _door_is_physically_locked(state, prop):
            return True

        if isinstance(planning_context, MovementPlanningContext):
            access_key = (id(prop), int(to_x), int(to_y), int(z))
            permitted = planning_context.door_access_permissions.get(access_key)
            if permitted is None:
                permitted = bool(_property_physical_access_for_actor(sim, eid, prop).get("granted", False))
                planning_context.door_access_permissions[access_key] = permitted
            return permitted

        return bool(_property_physical_access_for_actor(sim, eid, prop).get("granted", False))

    return not _door_is_physically_locked(state)


def _movement_allows_auto_open(sim, eid, *, reason="move"):
    reason_key = str(reason or "").strip().lower()
    if reason_key in {
        "player_move",
        "player_bump_yield",
        "vehicle_move",
        "vehicle_momentum",
        "npc_vehicle_move",
        "drone_move",
    }:
        return False
    return True


def _animal_npc_cannot_cross_doorway(sim, moving_eid, from_x, from_y, to_x, to_y, z, *, planning_context=None):
    is_animal = (
        planning_context.is_animal_or_wildlife
        if isinstance(planning_context, MovementPlanningContext)
        else bool(planning_context.get("is_animal_or_wildlife"))
        if isinstance(planning_context, dict)
        else _actor_is_animal_or_wildlife(sim, moving_eid)
    )
    if not is_animal:
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
            sim=sim,
        )
        if ingress.entered_bounds and ingress.ingress_kind in {"ordinary_entry", "alternate_aperture"}:
            return "blocked_animal_doorway"

    if origin_prop and origin_id != target_id:
        aperture = _property_aperture_at(origin_prop, from_x, from_y, z)
        if aperture:
            return "blocked_animal_doorway"

    return None


def _is_traversable_for(sim, moving_eid, x, y, z, *, planning_context=None):
    if isinstance(planning_context, MovementPlanningContext):
        chunk_coord = (x // planning_context.chunk_size, y // planning_context.chunk_size)
        if planning_context.chunk_detail.get(chunk_coord, "unloaded") == "unloaded":
            return False, "out_of_bounds"
        try:
            tile_x = int(x)
            tile_y = int(y)
        except (TypeError, ValueError):
            return False, "out_of_bounds"
        if abs(tile_x) > planning_context.world_coord_limit or abs(tile_y) > planning_context.world_coord_limit:
            return False, "out_of_bounds"
        floor = planning_context.tiles_by_floor.get(z)
        tile = floor.get((tile_x, tile_y)) if isinstance(floor, dict) else None
        if not bool(tile and tile.walkable):
            return False, "blocked_tile"
    else:
        if sim.detail_for_xy(x, y) == "unloaded":
            return False, "out_of_bounds"
        if not sim.tilemap.in_bounds(x, y):
            return False, "out_of_bounds"
        if not sim.tilemap.is_walkable(x, y, z):
            return False, "blocked_tile"
    if isinstance(planning_context, MovementPlanningContext):
        is_nonplayer_ai = planning_context.is_nonplayer_ai
    elif isinstance(planning_context, dict):
        is_nonplayer_ai = bool(planning_context.get("is_nonplayer_ai"))
    else:
        is_nonplayer_ai = moving_eid != getattr(sim, "player_eid", None) and sim.ecs.get(AI).get(moving_eid) is not None
    if is_nonplayer_ai:
        fire_cell = (
            planning_context.fire_cells.get((int(x), int(y), int(z)))
            if isinstance(planning_context, MovementPlanningContext)
            else fire_cell_state(sim, x, y, z)
        )
        if isinstance(fire_cell, dict) and int(fire_cell.get("fire_intensity", 0) or 0) > 0:
            return False, "active_fire"
        if isinstance(planning_context, MovementPlanningContext):
            known_trap = (int(x), int(y), int(z)) in planning_context.known_armed_trap_positions
        elif isinstance(planning_context, dict):
            known_trap = (int(x), int(y), int(z)) in planning_context.get("known_armed_trap_positions", ())
        else:
            known_trap = (
                actor_knows_armed_aerosol_trap_at(sim, moving_eid, x, y, z)
                or actor_knows_armed_mechanical_device_at(sim, moving_eid, x, y, z)
            )
        if known_trap:
            return False, "known_trap"
    colliders = planning_context.colliders if isinstance(planning_context, MovementPlanningContext) else None
    entities = planning_context.entities if isinstance(planning_context, MovementPlanningContext) else None
    blocked, blocker_eid = _entity_blocks(sim, moving_eid, x, y, z, colliders=colliders, entities=entities)
    if blocked:
        return False, f"blocked_entity:{blocker_eid}"
    return True, None


def _can_step_transition_for(sim, moving_eid, from_x, from_y, to_x, to_y, z, *, planning_context=None):
    traversable, reason = _is_traversable_for(
        sim,
        moving_eid,
        to_x,
        to_y,
        z,
        planning_context=planning_context,
    )
    if not traversable:
        if not (
            str(reason or "").strip().lower() == "blocked_tile"
            and _closed_door_is_plannable_transition(
                sim,
                moving_eid,
                from_x,
                from_y,
                to_x,
                to_y,
                z,
                planning_context=planning_context,
            )
        ):
            return False, reason
    if isinstance(planning_context, MovementPlanningContext) and not planning_context.is_animal_or_wildlife:
        animal_transition_reason = None
    else:
        animal_transition_reason = _animal_npc_cannot_cross_doorway(
            sim,
            moving_eid,
            from_x,
            from_y,
            to_x,
            to_y,
            z,
            planning_context=planning_context,
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
