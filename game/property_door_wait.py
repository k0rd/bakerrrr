"""Door-knock responder and doorway wait runtime.

This seam keeps the knock/answer flow and the active responder hold behavior
out of ``game/systems.py`` so property interaction can keep peeling away from
the player-action monolith without losing the shared NPC follow-through.
"""

from engine.systems import System
from game.components import (
    AI,
    CreatureIdentity,
    DoorWaitState,
    NPCMemory,
    NPCNeeds,
    NPCRoutine,
    NPCSocial,
    NPCWill,
    Occupation,
    Position,
)
from game.property_access import (
    evaluate_property_access as _evaluate_property_access,
    property_access_controller as _property_access_controller,
    property_claim_reason as _property_claim_reason,
)
from game.property_doors import (
    _actor_is_animal_or_wildlife,
    _door_close_attempt,
    _operable_door_state_at,
    _set_door_open_state,
)
from game.property_keys import property_lock_state
from game.property_runtime import (
    property_covering as _property_covering,
    property_is_storefront as _property_is_storefront,
)
from game.system_support.actor_runtime import _entity_is_downed
from game.system_support.interaction_ordering import _manhattan


def _support():
    from game import systems as _systems

    return _systems


def _door_service_courtesies_state(sim):
    state = getattr(sim, "door_service_courtesies", None)
    if isinstance(state, dict):
        return state
    state = {}
    sim.door_service_courtesies = state
    return state


def _door_wait_ticks_per_hour(sim):
    clock = getattr(sim, "world_traits", {}).get("clock", {}) if sim is not None else {}
    try:
        ticks_per_hour = int(clock.get("ticks_per_hour", 600))
    except (TypeError, ValueError):
        ticks_per_hour = 600
    return max(60, ticks_per_hour)


def _actor_in_active_dialogue(sim, eid):
    dialog_ui = getattr(sim, "dialog_ui", None)
    if not isinstance(dialog_ui, dict) or not bool(dialog_ui.get("open")):
        return False
    npc_eid = dialog_ui.get("npc_eid")
    try:
        return int(npc_eid) == int(eid)
    except (TypeError, ValueError):
        return npc_eid == eid


def _actor_in_live_combat(sim, eid):
    ai = sim.ecs.get(AI).get(eid)
    if ai and str(ai.state or "").strip().lower() == "protecting":
        return True

    will = sim.ecs.get(NPCWill).get(eid)
    if will and str(will.intent or "").strip().lower() == "protecting":
        return True

    for other_eid, other_ai in sim.ecs.get(AI).items():
        if int(other_eid) == int(eid):
            continue
        if str(getattr(other_ai, "state", "") or "").strip().lower() != "protecting":
            continue
        try:
            if int(getattr(other_ai, "target_eid", None)) == int(eid):
                return True
        except (TypeError, ValueError):
            if getattr(other_ai, "target_eid", None) == eid:
                return True

    for other_eid, other_will in sim.ecs.get(NPCWill).items():
        if int(other_eid) == int(eid):
            continue
        if str(getattr(other_will, "intent", "") or "").strip().lower() != "protecting":
            continue
        try:
            if int(getattr(other_will, "target_eid", None)) == int(eid):
                return True
        except (TypeError, ValueError):
            if getattr(other_will, "target_eid", None) == eid:
                return True

    return False


def _door_wait_hold_target(state):
    if not isinstance(state, DoorWaitState):
        return None
    return (int(state.wait_x), int(state.wait_y), int(state.wait_z))


def _door_wait_clear_service_courtesies(sim, *, responder_eid=None, caller_eid=None, property_id=""):
    state = _door_service_courtesies_state(sim)
    property_id = str(property_id or "").strip()
    for key, grant in list(state.items()):
        if not isinstance(grant, dict):
            state.pop(key, None)
            continue
        if responder_eid is not None and int(grant.get("responder_eid", -1) or -1) != int(responder_eid):
            continue
        if caller_eid is not None and int(key[0]) != int(caller_eid):
            continue
        if property_id and str(key[1] or "").strip() != property_id:
            continue
        state.pop(key, None)


def _door_wait_claim_role(sim, responder_eid, prop):
    if not isinstance(prop, dict):
        return "resident"

    if prop.get("owner_eid") == responder_eid:
        return "owner"

    position = sim.ecs.get(Position).get(responder_eid)
    _, claim_reason = _property_claim_reason(
        sim,
        responder_eid,
        prop,
        x=getattr(position, "x", None),
        y=getattr(position, "y", None),
        z=getattr(position, "z", None),
        min_standing=0.58,
    )
    claim_reason = str(claim_reason or "").strip().lower()
    if claim_reason == "employee":
        return "worker"
    if claim_reason == "resident":
        return "resident"
    if claim_reason == "owner":
        return "owner"

    support = _support()
    routine = sim.ecs.get(NPCRoutine).get(responder_eid)
    occupation = sim.ecs.get(Occupation).get(responder_eid)
    workplace_prop = support._workplace_property(sim, occupation=occupation, routine=routine)
    if workplace_prop and str(workplace_prop.get("id", "")).strip() == str(prop.get("id", "")).strip():
        return "worker"
    home_prop = support._home_property(sim, routine=routine)
    if home_prop and str(home_prop.get("id", "")).strip() == str(prop.get("id", "")).strip():
        return "resident"
    return "resident"


def _door_wait_recent_offense_strength(sim, responder_eid, caller_eid, *, max_age=220):
    if responder_eid is None or caller_eid is None:
        return 0.0
    memory = sim.ecs.get(NPCMemory).get(responder_eid)
    if not memory:
        return 0.0
    best = 0.0
    current_tick = int(getattr(sim, "tick", 0))
    for entry in tuple(memory.entries):
        if str(entry.get("kind", "")).strip().lower() != "offense":
            continue
        if entry.get("data", {}).get("offender_eid") != caller_eid:
            continue
        if current_tick - int(entry.get("tick", 0) or 0) > max_age:
            continue
        try:
            best = max(best, float(entry.get("strength", 0.0) or 0.0))
        except (TypeError, ValueError):
            continue
    return max(0.0, min(1.0, best))


def _door_wait_relationship_score(sim, responder_eid, caller_eid):
    if responder_eid is None or caller_eid is None:
        return 0.0

    support = _support()
    score = 0.0
    intro = support._person_contact_entry(sim, caller_eid, responder_eid)
    if isinstance(intro, dict):
        try:
            score = max(score, float(intro.get("standing", 0.0) or 0.0))
        except (TypeError, ValueError):
            pass

    social = sim.ecs.get(NPCSocial).get(responder_eid)
    bond = social.bonds.get(caller_eid) if social else None
    if isinstance(bond, dict):
        try:
            closeness = max(0.0, min(1.0, float(bond.get("closeness", 0.0) or 0.0)))
        except (TypeError, ValueError):
            closeness = 0.0
        try:
            trust = max(0.0, min(1.0, float(bond.get("trust", 0.0) or 0.0)))
        except (TypeError, ValueError):
            trust = 0.0
        score = max(score, (trust * 0.6) + (closeness * 0.4))

    return max(0.0, min(1.0, score))


def _door_wait_disposition(sim, responder_eid, caller_eid, prop):
    role = _door_wait_claim_role(sim, responder_eid, prop)
    player_eid = getattr(sim, "player_eid", None)
    position = sim.ecs.get(Position).get(caller_eid)
    access = _evaluate_property_access(
        sim,
        caller_eid,
        prop,
        x=getattr(position, "x", None),
        y=getattr(position, "y", None),
        z=getattr(position, "z", None),
    ) if caller_eid is not None else None

    relation = _door_wait_relationship_score(sim, responder_eid, caller_eid)
    offense = _door_wait_recent_offense_strength(sim, responder_eid, caller_eid)
    ai = sim.ecs.get(AI).get(responder_eid)
    needs = sim.ecs.get(NPCNeeds).get(responder_eid)

    wake_penalty = 0.0
    if ai and str(ai.state or "").strip().lower() == "resting":
        wake_penalty += 0.22
    if needs is not None:
        energy = max(0.0, min(100.0, float(getattr(needs, "energy", 100.0) or 100.0)))
        if energy < 28.0:
            wake_penalty += 0.22
        elif energy < 45.0:
            wake_penalty += 0.12
        elif energy < 60.0:
            wake_penalty += 0.05
    if access is not None and access.currently_open is False:
        wake_penalty += 0.06

    if caller_eid is not None and caller_eid != player_eid:
        relation = max(relation, 0.48)

    score = relation - wake_penalty - (offense * 0.9)
    if access is not None:
        if int(access.severity_score) >= 26:
            score -= 0.3
        elif int(access.severity_score) >= 12:
            score -= 0.12

    if offense >= 0.3 or (access is not None and int(access.severity_score) >= 26 and relation < 0.72):
        mood = "hostile"
    elif score < 0.22:
        mood = "hostile"
    elif score < 0.48:
        mood = "irritated"
    elif score < 0.74:
        mood = "neutral"
    else:
        mood = "friendly"

    allow_services = bool(
        caller_eid == player_eid
        and _property_is_storefront(prop)
        and mood in {"neutral", "friendly"}
        and relation >= 0.42
        and offense < 0.2
    )
    return {
        "role": role,
        "mood": mood,
        "allow_hours": mood != "hostile",
        "allow_services": allow_services,
    }


def _door_wait_timeout_ticks(sim, mood="neutral"):
    ticks_per_hour = _door_wait_ticks_per_hour(sim)
    mood_key = str(mood or "neutral").strip().lower() or "neutral"
    if mood_key == "friendly":
        return max(720, int(ticks_per_hour * 2.0))
    if mood_key == "irritated":
        return max(420, int(ticks_per_hour * 1.0))
    if mood_key == "hostile":
        return max(300, int(ticks_per_hour * 0.75))
    return max(600, int(ticks_per_hour * 1.25))


def _door_wait_neighbor_tiles(sim, prop, x, y, z):
    inside = []
    outside = []
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx = int(x) + dx
        ny = int(y) + dy
        nz = int(z)
        if not sim.tilemap.in_bounds(nx, ny):
            continue
        if not sim.tilemap.is_walkable(nx, ny, nz):
            continue
        covered = _property_covering(sim, nx, ny, nz)
        tile = (nx, ny, nz)
        if covered and str(covered.get("id", "")).strip() == str((prop or {}).get("id", "")).strip():
            inside.append(tile)
        else:
            outside.append(tile)
    return inside, outside


def _door_wait_target_for(sim, responder_eid, caller_eid, prop, x, y, z):
    player_eid = getattr(sim, "player_eid", None)
    responder_pos = sim.ecs.get(Position).get(responder_eid)
    inside_tiles, outside_tiles = _door_wait_neighbor_tiles(sim, prop, x, y, z)

    def _is_available(tile):
        tx, ty, tz = tile
        return not any(int(other_eid) != int(responder_eid) for other_eid in sim.tilemap.entities_at(tx, ty, tz))

    def _sorted_tiles(candidates):
        return sorted(
            candidates,
            key=lambda tile: (
                0 if _is_available(tile) else 1,
                _manhattan(
                    getattr(responder_pos, "x", int(x)),
                    getattr(responder_pos, "y", int(y)),
                    tile[0],
                    tile[1],
                ),
                abs(int(tile[2]) - int(getattr(responder_pos, "z", z))),
                tile[1],
                tile[0],
            ),
        )

    aperture_target = (int(x), int(y), int(z))
    if caller_eid == player_eid:
        aperture_blocked = any(int(other_eid) != int(responder_eid) for other_eid in sim.tilemap.entities_at(int(x), int(y), int(z)))
        if not aperture_blocked:
            return aperture_target
        for tile in _sorted_tiles(list(inside_tiles) + list(outside_tiles)):
            if _is_available(tile):
                return tile
        return aperture_target

    for tile in _sorted_tiles(inside_tiles):
        if _is_available(tile):
            return tile
    for tile in _sorted_tiles(outside_tiles):
        if _is_available(tile):
            return tile
    return aperture_target


def _door_wait_existing_responder(sim, property_id, x, y, z):
    property_id = str(property_id or "").strip()
    for responder_eid, state in list(sim.ecs.get(DoorWaitState).items()):
        if not isinstance(state, DoorWaitState):
            continue
        if str(state.property_id or "").strip() != property_id:
            continue
        if (
            int(state.aperture_x),
            int(state.aperture_y),
            int(state.aperture_z),
        ) != (int(x), int(y), int(z)):
            continue
        if state.is_expired(int(getattr(sim, "tick", 0))):
            continue
        return responder_eid, state
    return None, None


def _door_wait_feedback_text(sim, caller_eid, responder_eid, disposition, *, existing=False, answered_now=False):
    player_eid = getattr(sim, "player_eid", None)
    if caller_eid != player_eid:
        return ""

    support = _support()
    responder_name = support._entity_display_name(sim, responder_eid, title_case=True) or "Someone"
    mood = str((disposition or {}).get("mood", "neutral") or "neutral").strip().lower() or "neutral"
    if existing:
        return f"You knock. {responder_name} is already coming to the door."
    if answered_now:
        if mood == "hostile":
            return f"You knock. {responder_name} takes the doorway with a hard look."
        if mood == "friendly":
            return f"You knock. {responder_name} answers and opens the door for you."
        return f"You knock. {responder_name} answers and comes to the door."
    if mood == "hostile":
        return f"You knock. {responder_name} stirs inside and does not sound pleased."
    if mood == "friendly":
        return f"You knock. {responder_name} answers from inside and starts for the door."
    if mood == "irritated":
        return f"You knock. {responder_name} answers from inside, sounding annoyed."
    return f"You knock. {responder_name} starts for the door."


def _door_wait_no_answer_text(sim, caller_eid):
    if caller_eid != getattr(sim, "player_eid", None):
        return ""
    return "You knock, but no one answers."


def _door_wait_candidate_score(sim, eid, pos, prop, x, y, z):
    role = _door_wait_claim_role(sim, eid, prop)
    role_rank = {
        "owner": 0,
        "worker": 1,
        "resident": 2,
    }.get(role, 3)
    ai = sim.ecs.get(AI).get(eid)
    role_id = str(getattr(ai, "role", "") or "").strip().lower()
    return (
        role_rank,
        0 if role_id in {"guard", "clerk", "merchant", "resident"} else 1,
        _manhattan(pos.x, pos.y, int(x), int(y)),
        int(pos.y),
        int(pos.x),
    )


def _pick_door_wait_responder(sim, caller_eid, prop, x, y, z):
    if not isinstance(prop, dict) or str(prop.get("kind", "")).strip().lower() != "building":
        return None

    support = _support()
    player_eid = getattr(sim, "player_eid", None)
    positions = sim.ecs.get(Position)
    identities = sim.ecs.get(CreatureIdentity)
    candidates = []
    for eid, pos in positions.items():
        if eid in {caller_eid, player_eid}:
            continue
        if int(pos.z) != int(z):
            continue
        if _entity_is_downed(sim, eid) or _actor_is_animal_or_wildlife(sim, eid):
            continue
        if sim.ecs.get(DoorWaitState).get(eid) is not None:
            continue
        if _actor_in_live_combat(sim, eid):
            continue
        identity = identities.get(eid)
        if identity and str(identity.taxonomy_class or "hominid").strip().lower() != "hominid":
            continue
        covered = _property_covering(sim, pos.x, pos.y, pos.z)
        if not covered or str(covered.get("id", "")).strip() != str(prop.get("id", "")).strip():
            continue
        access, claim_reason = _property_claim_reason(sim, eid, prop, x=pos.x, y=pos.y, z=pos.z, min_standing=0.58)
        if not claim_reason and float(getattr(access, "standing", 0.0) or 0.0) < 0.58:
            continue
        if sim.ecs.get(AI).get(eid) is None:
            continue
        candidates.append((_door_wait_candidate_score(sim, eid, pos, prop, x, y, z), eid))

    if not candidates:
        return None
    candidates.sort(key=lambda row: row[0])
    return candidates[0][1]


def _door_knock_attempt(sim, caller_eid, x, y, z, *, reason="", source="interact"):
    support = _support()
    prop = _property_covering(sim, x, y, z)
    if not isinstance(prop, dict) or str(prop.get("kind", "")).strip().lower() != "building":
        return {"handled": False, "message": ""}

    property_id = str(prop.get("id", "") or "").strip()
    if not property_id:
        return {"handled": False, "message": ""}

    responder_eid, existing_state = _door_wait_existing_responder(sim, property_id, x, y, z)
    if responder_eid is not None and isinstance(existing_state, DoorWaitState):
        disposition = {
            "mood": str(existing_state.mood or "neutral").strip().lower() or "neutral",
        }
        answered_now = False
        responder_pos = sim.ecs.get(Position).get(responder_eid)
        if responder_pos and (
            int(responder_pos.x),
            int(responder_pos.y),
            int(responder_pos.z),
        ) == (
            int(existing_state.wait_x),
            int(existing_state.wait_y),
            int(existing_state.wait_z),
        ):
            answered_now = True
        return {
            "handled": True,
            "message": _door_wait_feedback_text(
                sim,
                caller_eid,
                responder_eid,
                disposition,
                existing=True,
                answered_now=answered_now,
            ),
        }

    responder_eid = _pick_door_wait_responder(sim, caller_eid, prop, x, y, z)
    if responder_eid is None:
        return {"handled": True, "message": _door_wait_no_answer_text(sim, caller_eid)}

    disposition = _door_wait_disposition(sim, responder_eid, caller_eid, prop)
    wait_target = _door_wait_target_for(sim, responder_eid, caller_eid, prop, x, y, z)
    timeout_ticks = _door_wait_timeout_ticks(sim, disposition.get("mood", "neutral"))
    state = DoorWaitState(
        int(x),
        int(y),
        int(z),
        wait_x=wait_target[0],
        wait_y=wait_target[1],
        wait_z=wait_target[2],
        property_id=property_id,
        caller_eid=caller_eid,
        start_tick=int(getattr(sim, "tick", 0)),
        timeout_ticks=timeout_ticks,
        mood=str(disposition.get("mood", "neutral") or "neutral"),
        answer_role=str(disposition.get("role", "resident") or "resident"),
        allow_hours=bool(disposition.get("allow_hours", True)),
        allow_services=bool(disposition.get("allow_services", False)),
        close_on_finish=True,
    )
    sim.ecs.add(responder_eid, state)

    ai = sim.ecs.get(AI).get(responder_eid)
    will = sim.ecs.get(NPCWill).get(responder_eid)
    if ai is not None:
        support._sync_ai_intent(
            ai,
            will,
            int(getattr(sim, "tick", 0)),
            "holding",
            score=74.0,
            target=wait_target,
            target_eid=None,
        )

    responder_pos = sim.ecs.get(Position).get(responder_eid)
    answered_now = bool(
        responder_pos
        and (
            int(responder_pos.x),
            int(responder_pos.y),
            int(responder_pos.z),
        ) == (
            int(wait_target[0]),
            int(wait_target[1]),
            int(wait_target[2]),
        )
    )
    if answered_now and _manhattan(int(responder_pos.x), int(responder_pos.y), int(x), int(y)) <= 1:
        _set_door_open_state(sim, int(x), int(y), int(z), True)

    return {
        "handled": True,
        "message": _door_wait_feedback_text(
            sim,
            caller_eid,
            responder_eid,
            disposition,
            existing=False,
            answered_now=answered_now,
        ),
    }


class DoorWaitSystem(System):

    def _clear_wait(self, eid, state):
        ai = self.sim.ecs.get(AI).get(eid)
        will = self.sim.ecs.get(NPCWill).get(eid)
        target = _door_wait_hold_target(state)
        if ai and str(ai.state or "").strip().lower() == "holding":
            if target is None or tuple(ai.target or ()) == tuple(target):
                ai.state = "idle"
                ai.target = None
                ai.target_eid = None
        if will and str(will.intent or "").strip().lower() == "holding":
            if target is None or tuple(will.target or ()) == tuple(target):
                will.intent = "idle"
                will.score = 0.0
                will.target = None
                will.target_eid = None

        _door_wait_clear_service_courtesies(
            self.sim,
            responder_eid=eid,
            caller_eid=getattr(state, "caller_eid", None),
            property_id=str(getattr(state, "property_id", "") or "").strip(),
        )

        prop = self.sim.properties.get(str(getattr(state, "property_id", "") or "").strip())
        should_close = False
        if isinstance(prop, dict):
            lock_state = property_lock_state(prop)
            if bool(lock_state.get("locked")):
                should_close = True
            else:
                controller = _property_access_controller(self.sim, prop)
                should_close = bool(isinstance(controller, dict) and controller.get("open_now") is False)
        if should_close and bool(getattr(state, "close_on_finish", False)):
            _door_close_attempt(
                self.sim,
                eid,
                int(getattr(state, "aperture_x", 0)),
                int(getattr(state, "aperture_y", 0)),
                int(getattr(state, "aperture_z", 0)),
            )

        self.sim.ecs.get(DoorWaitState).pop(eid, None)

    def update(self):
        support = _support()
        positions = self.sim.ecs.get(Position)
        ais = self.sim.ecs.get(AI)
        wills = self.sim.ecs.get(NPCWill)
        current_tick = int(getattr(self.sim, "tick", 0))
        courtesy_state = _door_service_courtesies_state(self.sim)

        for key, grant in list(courtesy_state.items()):
            if not isinstance(grant, dict) or int(grant.get("until_tick", 0) or 0) <= current_tick:
                courtesy_state.pop(key, None)

        for eid, state in list(self.sim.ecs.get(DoorWaitState).items()):
            if not isinstance(state, DoorWaitState):
                self.sim.ecs.get(DoorWaitState).pop(eid, None)
                continue

            pos = positions.get(eid)
            if pos is None:
                self._clear_wait(eid, state)
                continue

            if _actor_in_live_combat(self.sim, eid):
                self._clear_wait(eid, state)
                continue

            if (
                support._active_contractor_record(self.sim, eid, ally_eid=getattr(self.sim, "player_eid", None)) is not None
                or support.actor_player_business_employment(self.sim, eid, owner_eid=getattr(self.sim, "player_eid", None)) is not None
            ) and not _actor_in_active_dialogue(self.sim, eid):
                self._clear_wait(eid, state)
                continue

            if state.is_expired(current_tick) and not _actor_in_active_dialogue(self.sim, eid):
                self._clear_wait(eid, state)
                continue

            target = _door_wait_hold_target(state)
            ai = ais.get(eid)
            will = wills.get(eid)
            if (
                ai is not None
                and not _actor_in_active_dialogue(self.sim, eid)
                and str(ai.state or "").strip().lower() != "protecting"
            ):
                if tuple(ai.target or ()) != tuple(target) or str(ai.state or "").strip().lower() != "holding" or ai.target_eid is not None:
                    support._sync_ai_intent(
                        ai,
                        will,
                        current_tick,
                        "holding",
                        score=74.0,
                        target=target,
                        target_eid=None,
                    )

            near_aperture = bool(
                int(pos.z) == int(state.aperture_z)
                and _manhattan(int(pos.x), int(pos.y), int(state.aperture_x), int(state.aperture_y)) <= 1
            )
            if near_aperture:
                door_state = _operable_door_state_at(
                    self.sim,
                    int(state.aperture_x),
                    int(state.aperture_y),
                    int(state.aperture_z),
                )
                if isinstance(door_state, dict) and not bool(door_state.get("open", False)):
                    _set_door_open_state(
                        self.sim,
                        int(state.aperture_x),
                        int(state.aperture_y),
                        int(state.aperture_z),
                        True,
                    )

                property_id = str(state.property_id or "").strip()
                caller_eid = getattr(state, "caller_eid", None)
                if bool(getattr(state, "allow_services", False)) and caller_eid is not None and property_id:
                    courtesy_state[(int(caller_eid), property_id)] = {
                        "until_tick": current_tick + max(1, int(state.timeout_ticks or 1)),
                        "allow_services": True,
                        "responder_eid": int(eid),
                    }
            else:
                _door_wait_clear_service_courtesies(
                    self.sim,
                    responder_eid=eid,
                    caller_eid=getattr(state, "caller_eid", None),
                    property_id=str(state.property_id or "").strip(),
                )
