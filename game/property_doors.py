"""Shared property-door state and interaction helpers."""

from engine.tilemap import Tile

from game.components import AI, CreatureIdentity, Position
from game.property_access import (
    property_apertures as _property_apertures,
    property_physical_access_for_actor as _property_physical_access_for_actor,
    property_ingress_context as _property_ingress_context,
)
from game.property_keys import ensure_property_lock, property_lock_state
from game.property_runtime import property_covering as _property_covering, property_metadata as _property_metadata
from game.system_support.interaction_ordering import _interaction_target_order_key
from game.system_support.intrusion_runtime import _is_operable_door_aperture


def _actor_is_animal_or_wildlife(sim, eid):
    ais = sim.ecs.get(AI)
    identities = sim.ecs.get(CreatureIdentity)
    ai = ais.get(eid)
    identity = identities.get(eid)
    role = str(getattr(ai, "role", "") or "").strip().lower()
    creature_type = str(getattr(identity, "creature_type", "") or "").strip().lower()
    return role == "wildlife" or creature_type == "animal"


def _door_state_at(sim, x, y, z=0):
    helper = getattr(sim, "door_state_at", None)
    if callable(helper):
        return helper(x, y, z)
    states = getattr(sim, "door_states", None)
    if not isinstance(states, dict):
        return None
    try:
        return states.get((int(x), int(y), int(z)))
    except (TypeError, ValueError):
        return None


def _ordinary_door_state_at(sim, x, y, z=0):
    state = _door_state_at(sim, x, y, z)
    if not isinstance(state, dict):
        return None
    kind = str(state.get("kind", "door") or "door").strip().lower() or "door"
    ordinary = bool(state.get("ordinary", kind == "door"))
    if kind != "door" or not ordinary:
        return None
    return state


def _operable_door_state_at(sim, x, y, z=0, *, states=None):
    if isinstance(states, dict):
        try:
            state = states.get((int(x), int(y), int(z)))
        except (TypeError, ValueError):
            state = None
    else:
        state = _door_state_at(sim, x, y, z)
    if not isinstance(state, dict):
        return None
    kind = str(state.get("kind", "door") or "door").strip().lower() or "door"
    if not _is_operable_door_aperture(kind):
        return None
    return state


def _door_property_at(sim, x, y, z=0, *, state=None):
    prop = _property_covering(sim, x, y, z)
    if isinstance(prop, dict):
        return prop

    if not isinstance(state, dict):
        state = _operable_door_state_at(sim, x, y, z)
    if not isinstance(state, dict):
        return None

    property_id = str(state.get("property_id", "") or "").strip()
    if not property_id:
        return None
    prop = getattr(sim, "properties", {}).get(property_id)
    return prop if isinstance(prop, dict) else None


def _door_tile_is_occupied(sim, x, y, z=0):
    try:
        occupants = tuple(sim.tilemap.entities_at(int(x), int(y), int(z)))
    except (TypeError, ValueError):
        return True
    return bool(occupants)


def _set_door_open_state(sim, x, y, z, is_open):
    helper = getattr(sim, "set_door_state", None)
    if callable(helper):
        state = helper(x, y, z, open=bool(is_open))
    else:
        state = _operable_door_state_at(sim, x, y, z)
        if state is None:
            return False
        state["open"] = bool(is_open)

    apply_helper = getattr(sim, "apply_door_state", None)
    if callable(apply_helper):
        apply_helper(x, y, z)
        return True

    tile = sim.tilemap.tile_at(x, y, z)
    if tile is None:
        return False
    visibility_changed = bool(getattr(tile, "transparent", True)) != bool(is_open)
    tile.walkable = bool(is_open)
    tile.transparent = bool(is_open)
    sim.tilemap.set_tile_appearance(
        x,
        y,
        z,
        glyph="'" if is_open else "+",
        color="feature_door",
        semantic_id="feature_door",
    )
    if visibility_changed and hasattr(sim.tilemap, "mark_visibility_changed"):
        sim.tilemap.mark_visibility_changed(x, y, z)
    return True


def _set_door_locked_state(sim, x, y, z, is_locked):
    helper = getattr(sim, "set_door_state", None)
    if callable(helper):
        state = helper(x, y, z, locked=bool(is_locked))
        return isinstance(state, dict)
    state = _operable_door_state_at(sim, x, y, z)
    if state is None:
        return False
    state["locked"] = bool(is_locked)
    return True


def _door_is_physically_locked(state, prop=None):
    """Read aperture truth first, with one legacy-property fallback."""

    if isinstance(state, dict) and "locked" in state:
        return bool(state.get("locked", False))
    if isinstance(prop, dict):
        return bool(property_lock_state(prop).get("locked", False))
    return False


def _set_property_apertures_locked(sim, prop, locked, *, auto_managed=None):
    """Apply one controller/authority lock command to real door endpoints."""

    if sim is None or not isinstance(prop, dict):
        return 0
    changed = 0
    for aperture in _property_apertures(prop):
        if not isinstance(aperture, dict):
            continue
        kind = str(aperture.get("kind", "door") or "door").strip().lower() or "door"
        if not _is_operable_door_aperture(kind):
            continue
        try:
            x = int(aperture.get("x"))
            y = int(aperture.get("y"))
            z = int(aperture.get("z", prop.get("z", 0)))
        except (TypeError, ValueError):
            continue
        kwargs = {
            "locked": bool(locked),
            "kind": kind,
            "ordinary": bool(aperture.get("ordinary", kind == "door")),
            "property_id": prop.get("id"),
        }
        if auto_managed is not None:
            kwargs["auto_managed"] = bool(auto_managed)
        state = sim.set_door_state(x, y, z, **kwargs)
        if isinstance(state, dict):
            changed += 1

    if changed:
        # Compatibility projection for legacy/UI readers. Door states above
        # remain the canonical physical facts.
        _property_metadata(prop)["property_locked"] = bool(locked)
    return changed


def _door_open_attempt(sim, eid, x, y, z, *, allow_override=False):
    state = _operable_door_state_at(sim, x, y, z)
    if state is None:
        return False, "not_door"
    if bool(state.get("broken", False)):
        return True, "broken_open"
    if bool(state.get("open", False)):
        return True, "already_open"
    if _actor_is_animal_or_wildlife(sim, eid):
        return False, "blocked_animal_doorway"

    positions = sim.ecs.get(Position)
    pos = positions.get(eid)
    if not pos:
        return False, "missing_position"

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
            sim=sim,
        )
    if ingress and ingress.from_inside:
        if _door_is_physically_locked(state, prop):
            _set_door_locked_state(sim, x, y, z, False)
        return (_set_door_open_state(sim, x, y, z, True), "opened_inside")

    if prop:
        if not _door_is_physically_locked(state, prop):
            return (_set_door_open_state(sim, x, y, z, True), "opened_unlocked")

        physical_access = _property_physical_access_for_actor(sim, eid, prop)
        if not bool(physical_access.get("granted", False)):
            return False, "locked_property"
        if not _set_door_locked_state(sim, x, y, z, False):
            return False, "locked_property"
        return (_set_door_open_state(sim, x, y, z, True), "credential_open")

    if _door_is_physically_locked(state):
        return False, "locked_door"
    return (_set_door_open_state(sim, x, y, z, True), "opened")


def _door_close_attempt(sim, eid, x, y, z):
    state = _operable_door_state_at(sim, x, y, z)
    if state is None:
        return False, "not_door"
    if bool(state.get("broken", False)):
        return False, "broken_door"
    if not bool(state.get("open", False)):
        return False, "already_closed"
    if _door_tile_is_occupied(sim, x, y, z):
        return False, "door_occupied"
    return (_set_door_open_state(sim, x, y, z, False), "closed")


def _set_property_locked_override(prop, *, locked, tick=0, method="manual_lock"):
    if not isinstance(prop, dict):
        return False

    state = property_lock_state(prop)
    ensure_property_lock(
        prop,
        locked=bool(locked),
        lock_tier=max(1, int(state.get("lock_tier", 1) or 1)),
        key_label=str(state.get("key_label") or prop.get("name", prop.get("id", "Property"))).strip() or "Property",
    )
    metadata = _property_metadata(prop)
    metadata["property_override_tick"] = int(tick or 0)
    metadata["property_override_method"] = (
        str(method or ("manual_lock" if locked else "manual_unlock")).strip().lower()
        or ("manual_lock" if locked else "manual_unlock")
    )
    return True


def _door_interaction_candidate(sim, pos, *, preferred_dir=None, target=None):
    if pos is None:
        return None

    if target is not None:
        try:
            target_x, target_y, target_z = target
            target_x = int(target_x)
            target_y = int(target_y)
            target_z = int(target_z)
        except (TypeError, ValueError):
            target_x = target_y = target_z = None
        if target_x is not None and target_z == int(pos.z):
            dx = int(target_x) - int(pos.x)
            dy = int(target_y) - int(pos.y)
            if max(abs(dx), abs(dy)) <= 1:
                state = _operable_door_state_at(sim, target_x, target_y, target_z)
                if state is not None:
                    return {
                        "x": target_x,
                        "y": target_y,
                        "z": target_z,
                        "state": state,
                        "prop": _door_property_at(sim, target_x, target_y, target_z, state=state),
                    }

    candidates = [
        (int(pos.x), int(pos.y), int(pos.z)),
        (int(pos.x), int(pos.y) - 1, int(pos.z)),
        (int(pos.x) + 1, int(pos.y), int(pos.z)),
        (int(pos.x), int(pos.y) + 1, int(pos.z)),
        (int(pos.x) - 1, int(pos.y), int(pos.z)),
        (int(pos.x) - 1, int(pos.y) - 1, int(pos.z)),
        (int(pos.x) + 1, int(pos.y) - 1, int(pos.z)),
        (int(pos.x) + 1, int(pos.y) + 1, int(pos.z)),
        (int(pos.x) - 1, int(pos.y) + 1, int(pos.z)),
    ]
    ranked = []
    same_tile_ranked = []
    for index, (x, y, z) in enumerate(candidates):
        state = _operable_door_state_at(sim, x, y, z)
        if state is None:
            continue
        open_penalty = 1 if bool(state.get("open", False)) else 0
        row = (
            _interaction_target_order_key(
                pos.x,
                pos.y,
                x,
                y,
                preferred_dir=preferred_dir,
                stable_tiebreaker=(open_penalty, index),
            ),
            {
                "x": x,
                "y": y,
                "z": z,
                "state": state,
                "prop": _door_property_at(sim, x, y, z, state=state),
            },
        )
        if int(x) == int(pos.x) and int(y) == int(pos.y):
            same_tile_ranked.append(row)
        else:
            ranked.append(row)
    ranked.sort(key=lambda row: row[0])
    if ranked:
        return ranked[0][1]
    same_tile_ranked.sort(key=lambda row: row[0])
    if same_tile_ranked:
        return same_tile_ranked[0][1]
    return None


def _door_action_text(reason, *, opening=False):
    reason_key = str(reason or "").strip().lower()
    if opening:
        if reason_key == "already_open":
            return "The door is already open."
        if reason_key in {"authorized_open", "credential_open", "opened", "opened_inside", "opened_unlocked", "override_open", "picked_front_door", "manual_front_door_override"}:
            return "You open the door."
        if reason_key in {"locked_property", "locked_door"}:
            return "The door is locked."
        if reason_key == "closed_property":
            return "The place is closed."
        if reason_key == "door_access_denied":
            return "You cannot open that door."
        if reason_key == "lock_override_failed":
            return "You fail to work the lock."
        if reason_key == "lock_override_fumble":
            return "You botch the lock and the door stays shut."
        if reason_key == "blocked_animal_doorway":
            return "Animals do not work doors."
        return "The door will not open."

    if reason_key == "closed":
        return "You close the door."
    if reason_key == "door_occupied":
        return "Something is in the doorway."
    if reason_key == "already_closed":
        return "The door is already closed."
    return "You cannot close the door."


def _door_lock_action_text(reason, *, requirement="the matching key"):
    reason_key = str(reason or "").strip().lower()
    requirement_text = str(requirement or "the matching key").strip() or "the matching key"
    if reason_key == "closed_locked":
        return "You close the locked door."
    if reason_key == "closed_then_locked":
        return "You close and lock the door."
    if reason_key == "locked":
        return "You lock the door."
    if reason_key == "unlocked":
        return "You unlock the door."
    if reason_key == "door_occupied":
        return "Something is in the doorway."
    if reason_key == "lock_access_denied":
        return f"You need {requirement_text} to work that lock."
    if reason_key == "locked_property":
        return f"You need {requirement_text}, a lockpick kit, or exceptional intrusion skill."
    if reason_key == "lock_override_failed":
        return "You fail to work the lock."
    if reason_key == "lock_override_fumble":
        return "You botch the lock and it stays shut."
    if reason_key == "not_property_door":
        return "That doorway has no lock you can work."
    return "You cannot change that lock."
