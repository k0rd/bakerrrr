"""Deterministic NPC self-protection behavior under threat."""

from __future__ import annotations

import random

from engine.events import Event
from engine.visibility import has_line_of_sight
from game.components import AI, NPCMemory, NPCWill, Occupation, Position
from game.movement_runtime import _can_step_transition_for, _is_traversable_for
from game.npc_relationships import record_partner_combat_witnesses, relationship_partner_eid
from game.property_doors import _operable_door_state_at
from game.property_runtime import property_covering, property_metadata
from game.system_support.actor_attention_runtime import mark_actor_urgent, schedule_actor_due


_QUIRK_LINES = {
    "hide_behind_counter": (
        "They duck for the counter without making a speech of it.",
        "They put the nearest counter between them and trouble.",
        "They fold behind the work edge, fast and practiced.",
    ),
    "lock_nearest_door": (
        "They reach for the door habit before anything heroic.",
        "Their first thought is the lock, not the argument.",
        "They glance for a latch like it might still solve this.",
    ),
    "call_partner": (
        "They call for someone specific before their voice gets steady.",
        "They say a partner's name like it is a handhold.",
        "They call for their person, frightened and loyal at once.",
    ),
    "look_busy": (
        "They try to look busy enough to become furniture.",
        "They straighten something that does not need straightening.",
        "They make a little work mask and hope trouble walks past it.",
    ),
    "freeze": (
        "They freeze for one awful breath.",
        "They go still, not brave, not gone, just stopped.",
        "They hold perfectly still while their courage catches up.",
    ),
    "slip_out_back": (
        "They start looking for the ugly exit, not the proud one.",
        "They angle toward the back route without advertising it.",
        "They pick the way out that regulars know and strangers miss.",
    ),
    "shelter_with_crowd": (
        "They drift toward other bodies, borrowing courage from the crowd.",
        "They look for people before they look for a door.",
        "They fold into the nearest cluster and try not to be alone with it.",
    ),
    "stand_ground": (
        "They plant their feet and make fear wait its turn.",
        "They stay put, jaw tight, refusing to spend the first step.",
        "They hold the line they understand best.",
    ),
}


def _text(value) -> str:
    return str(value or "").strip()


def _key(value) -> str:
    return _text(value).lower()


def _tick(sim) -> int:
    try:
        return int(getattr(sim, "tick", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _cooldown_state(sim) -> dict:
    state = getattr(sim, "npc_self_protection_state", None)
    if not isinstance(state, dict):
        state = {"cooldowns": {}, "active": {}}
        sim.npc_self_protection_state = state
    state.setdefault("cooldowns", {})
    state.setdefault("active", {})
    return state


def _action_state(sim) -> dict:
    state = _cooldown_state(sim)
    active = state.get("active")
    if not isinstance(active, dict):
        active = {}
        state["active"] = active
    return active


def _active_key(eid) -> str:
    try:
        return str(int(eid))
    except (TypeError, ValueError):
        return str(eid)


def _property_context(sim, pos) -> tuple[str, str]:
    if pos is None:
        return "", ""
    prop = property_covering(sim, int(pos.x), int(pos.y), int(pos.z))
    if not isinstance(prop, dict):
        return "", ""
    metadata = property_metadata(prop)
    category = _key(metadata.get("archetype") or prop.get("kind"))
    name = _text(metadata.get("business_name")) or _text(prop.get("name")) or _text(prop.get("id"))
    return category, name


def _candidate_quirks(sim, eid, *, ai=None, pos=None) -> tuple[str, ...]:
    ai = ai or sim.ecs.get(AI).get(eid)
    role = _key(getattr(ai, "role", "civilian"))
    occupation = sim.ecs.get(Occupation).get(eid)
    career = _key(getattr(occupation, "career", ""))
    category, _place_name = _property_context(sim, pos)
    partner = relationship_partner_eid(sim, eid, minimum_stage="dating")
    choices = []
    if partner is not None:
        choices.extend(("call_partner", "call_partner"))
    if role in {"guard", "security", "officer", "police", "deputy", "marshal", "scout"} or career in {"guard", "security", "patrol"}:
        choices.extend(("stand_ground", "lock_nearest_door", "shelter_with_crowd"))
    if category in {"restaurant", "bar", "tavern", "casino", "corner_store", "outfitter", "pharmacy"} or career in {"clerk", "merchant", "bartender", "server"}:
        choices.extend(("hide_behind_counter", "look_busy", "slip_out_back"))
    if category in {"residence", "apartment", "shelter"}:
        choices.extend(("lock_nearest_door", "shelter_with_crowd", "freeze"))
    if category in {"work_shed", "breaker_yard", "salvage_camp", "pump_house", "drydock_yard"} or career in {"worker", "mechanic", "maintenance_tech"}:
        choices.extend(("slip_out_back", "look_busy", "stand_ground"))
    if not choices:
        choices.extend(("freeze", "slip_out_back", "shelter_with_crowd", "look_busy"))
    return tuple(choices)


def choose_self_protection_quirk(sim, eid, *, ai=None, pos=None, reason="threat", forced_quirk=None) -> dict:
    try:
        eid = int(eid)
    except (TypeError, ValueError):
        return {}
    now = _tick(sim)
    state = _cooldown_state(sim)
    cooldowns = state.get("cooldowns", {})
    key = str(eid)
    try:
        until = int(cooldowns.get(key, 0) or 0)
    except (TypeError, ValueError):
        until = 0
    forced_key = _key(forced_quirk)
    if until > now and not forced_key:
        return {}
    choices = _candidate_quirks(sim, eid, ai=ai, pos=pos)
    seed = f"{getattr(sim, 'seed', 0)}:self-protect:{eid}:{now // 120}:{reason}:{len(choices)}"
    rng = random.Random(seed)
    quirk = forced_key if forced_key in _QUIRK_LINES else choices[rng.randrange(len(choices))]
    line_bank = _QUIRK_LINES.get(quirk, _QUIRK_LINES["freeze"])
    line = line_bank[rng.randrange(len(line_bank))]
    cooldowns[key] = now + 120
    return {
        "quirk": quirk,
        "line": line,
        "cooldown_until": cooldowns[key],
        "reason": _key(reason) or "threat",
    }


def clear_self_protection_action(sim, eid):
    active = _action_state(sim)
    active.pop(_active_key(eid), None)
    ai = sim.ecs.get(AI).get(eid)
    if ai is not None:
        for attr in (
            "self_protection_action",
            "self_protection_action_target",
            "self_protection_action_until_tick",
            "self_protection_action_result",
        ):
            if hasattr(ai, attr):
                delattr(ai, attr)


def active_self_protection_action(sim, eid, *, current_tick=None) -> dict:
    active = _action_state(sim)
    row = active.get(_active_key(eid))
    if not isinstance(row, dict):
        return {}
    now = _tick(sim) if current_tick is None else int(current_tick)
    try:
        until = int(row.get("until_tick", 0) or 0)
    except (TypeError, ValueError):
        until = 0
    if until and until <= now:
        clear_self_protection_action(sim, eid)
        return {}
    return row


def _record_action(sim, eid, row: dict) -> dict:
    if not isinstance(row, dict):
        return {}
    active = _action_state(sim)
    active[_active_key(eid)] = dict(row)
    ai = sim.ecs.get(AI).get(eid)
    if ai is not None:
        setattr(ai, "self_protection_action", row.get("action"))
        setattr(ai, "self_protection_action_target", row.get("target"))
        setattr(ai, "self_protection_action_until_tick", row.get("until_tick"))
        setattr(ai, "self_protection_action_result", row.get("result"))
    return row


def _threat_pos_tuple(sim, threat_eid=None, threat_pos=None):
    if isinstance(threat_pos, (tuple, list)) and len(threat_pos) >= 3:
        try:
            return (int(threat_pos[0]), int(threat_pos[1]), int(threat_pos[2]))
        except (TypeError, ValueError):
            pass
    if threat_eid is None:
        return None
    pos = sim.ecs.get(Position).get(threat_eid)
    if pos is None:
        return None
    return (int(pos.x), int(pos.y), int(pos.z))


def _reachable_tiles(sim, eid, pos, *, max_steps=4):
    if pos is None:
        return ()
    origin = (int(pos.x), int(pos.y))
    z = int(pos.z)
    frontier = [(origin[0], origin[1], 0)]
    seen = {origin}
    out = [(origin[0], origin[1], 0)]
    directions = (
        (0, -1),
        (1, 0),
        (0, 1),
        (-1, 0),
        (-1, -1),
        (1, -1),
        (-1, 1),
        (1, 1),
    )
    while frontier:
        cx, cy, steps = frontier.pop(0)
        if int(steps) >= int(max_steps):
            continue
        for dx, dy in directions:
            nx = int(cx) + int(dx)
            ny = int(cy) + int(dy)
            if (nx, ny) in seen:
                continue
            step_ok, _reason = _can_step_transition_for(
                sim,
                moving_eid=eid,
                from_x=int(cx),
                from_y=int(cy),
                to_x=nx,
                to_y=ny,
                z=z,
            )
            if not step_ok:
                continue
            seen.add((nx, ny))
            next_steps = int(steps) + 1
            frontier.append((nx, ny, next_steps))
            out.append((nx, ny, next_steps))
    return tuple(out)


def _nearest_cover_target(sim, eid, pos, threat_pos, *, max_steps=4):
    if pos is None or not threat_pos or int(threat_pos[2]) != int(pos.z):
        return None
    current_dist = abs(int(pos.x) - int(threat_pos[0])) + abs(int(pos.y) - int(threat_pos[1]))
    best = None
    best_score = float("-inf")
    for cx, cy, steps in _reachable_tiles(sim, eid, pos, max_steps=max_steps):
        tile = sim.tilemap.tile_at(cx, cy, int(pos.z))
        if tile is None:
            continue
        threat_dist = abs(int(cx) - int(threat_pos[0])) + abs(int(cy) - int(threat_pos[1]))
        cover_score = 0.0
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            adj = sim.tilemap.tile_at(int(cx) + dx, int(cy) + dy, int(pos.z))
            if adj is not None and not bool(getattr(adj, "walkable", False)) and not bool(getattr(adj, "transparent", False)):
                cover_score = max(cover_score, 1.0)
        if property_covering(sim, int(cx), int(cy), int(pos.z)):
            cover_score = max(cover_score, 0.55)
        if cover_score <= 0.0:
            continue
        score = (cover_score * 20.0) + (float(threat_dist) * 2.0) - (float(steps) * 2.5)
        if threat_dist >= current_dist:
            score += 5.0
        if best is None or score > best_score:
            best = (int(cx), int(cy), int(pos.z))
            best_score = score
    return best


def _slip_route_target(sim, eid, pos, threat_pos, *, max_steps=7):
    if pos is None or not threat_pos or int(threat_pos[2]) != int(pos.z):
        return None
    current_dist = abs(int(pos.x) - int(threat_pos[0])) + abs(int(pos.y) - int(threat_pos[1]))
    current_prop = property_covering(sim, int(pos.x), int(pos.y), int(pos.z))
    current_prop_id = str((current_prop or {}).get("id", "") or "").strip() if isinstance(current_prop, dict) else ""
    best = None
    best_score = float("-inf")
    for cx, cy, steps in _reachable_tiles(sim, eid, pos, max_steps=max_steps):
        threat_dist = abs(int(cx) - int(threat_pos[0])) + abs(int(cy) - int(threat_pos[1]))
        if threat_dist <= current_dist and int(steps) > 0:
            continue
        prop = property_covering(sim, int(cx), int(cy), int(pos.z))
        prop_id = str((prop or {}).get("id", "") or "").strip() if isinstance(prop, dict) else ""
        line_blocked = not has_line_of_sight(sim, int(cx), int(cy), int(pos.z), int(threat_pos[0]), int(threat_pos[1]), int(threat_pos[2]))
        exits_prop = bool(current_prop_id and prop_id != current_prop_id)
        score = (float(threat_dist - current_dist) * 7.0) - (float(steps) * 2.2)
        if line_blocked:
            score += 16.0
        if exits_prop:
            score += 8.0
        if steps <= 0:
            score -= 12.0
        if best is None or score > best_score:
            best = (int(cx), int(cy), int(pos.z))
            best_score = score
    return best


def _crowd_shelter_target(sim, eid, pos, threat_pos=None, threat_eid=None, *, max_steps=5):
    if pos is None:
        return None
    actor_positions = sim.ecs.get(Position)
    candidates = []
    for cx, cy, steps in _reachable_tiles(sim, eid, pos, max_steps=max_steps):
        nearby = 0
        for other_eid, other_pos in actor_positions.items():
            if other_eid == eid or other_pos is None or int(other_pos.z) != int(pos.z):
                continue
            if other_eid == threat_eid or other_eid == getattr(sim, "player_eid", None):
                continue
            other_ai = sim.ecs.get(AI).get(other_eid)
            other_state = _key(getattr(other_ai, "state", ""))
            if other_state in {"protecting", "chasing", "attacking", "downed", "surrendered"}:
                continue
            if abs(int(other_pos.x) - int(cx)) + abs(int(other_pos.y) - int(cy)) <= 2:
                nearby += 1
        if nearby <= 0:
            continue
        threat_score = 0.0
        if threat_pos and int(threat_pos[2]) == int(pos.z):
            threat_score = abs(int(cx) - int(threat_pos[0])) + abs(int(cy) - int(threat_pos[1]))
        score = (nearby * 10.0) + (threat_score * 1.5) - (float(steps) * 2.5)
        candidates.append((score, int(cx), int(cy), int(pos.z)))
    if not candidates:
        return None
    candidates.sort(reverse=True)
    _score, x, y, z = candidates[0]
    return (x, y, z)


def _nearest_lockable_door(sim, eid, pos, threat_pos=None):
    if pos is None:
        return None
    actor_prop = property_covering(sim, int(pos.x), int(pos.y), int(pos.z))
    actor_prop_id = str((actor_prop or {}).get("id", "") or "").strip() if isinstance(actor_prop, dict) else ""
    best = None
    best_score = float("inf")
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            x = int(pos.x) + dx
            y = int(pos.y) + dy
            z = int(pos.z)
            state = _operable_door_state_at(sim, x, y, z)
            if not isinstance(state, dict) or bool(state.get("broken", False)):
                continue
            if abs(dx) + abs(dy) > 2:
                continue
            traversable, _reason = _is_traversable_for(sim, eid, x, y, z)
            if traversable:
                # A walkable open door tile can still be closed, but we avoid
                # closing it while standing on it.
                occupants = tuple(sim.tilemap.entities_at(x, y, z))
                if occupants:
                    continue
            door_prop_id = str(state.get("property_id", "") or "").strip()
            if actor_prop_id and door_prop_id and door_prop_id != actor_prop_id:
                continue
            if actor_prop_id and not door_prop_id:
                prop = property_covering(sim, x, y, z)
                prop_id = str((prop or {}).get("id", "") or "").strip() if isinstance(prop, dict) else ""
                if prop_id and prop_id != actor_prop_id:
                    continue
            score = abs(dx) + abs(dy)
            if threat_pos:
                score -= min(2, abs(x - int(threat_pos[0])) + abs(y - int(threat_pos[1])))
            if score < best_score:
                best = (x, y, z, state)
                best_score = score
    return best


def _try_lock_nearest_door(sim, eid, pos, threat_pos=None) -> dict:
    door = _nearest_lockable_door(sim, eid, pos, threat_pos=threat_pos)
    if not door:
        return {"result": "no_door"}
    x, y, z, state = door
    helper = getattr(sim, "set_door_state", None)
    if not callable(helper):
        return {"result": "no_door_helper", "door": (x, y, z)}
    helper(x, y, z, open=False, locked=True)
    apply_helper = getattr(sim, "apply_door_state", None)
    if callable(apply_helper):
        apply_helper(x, y, z)
    return {
        "result": "locked",
        "door": (x, y, z),
        "was_open": bool(state.get("open", False)),
    }


def _call_partner_for_help(sim, eid, threat_eid=None, damage=0, pos=None, threat_pos=None) -> dict:
    partner_eid = relationship_partner_eid(sim, eid, minimum_stage="dating")
    if partner_eid is None or threat_eid is None:
        return {"result": "no_partner"}
    partner_pos = sim.ecs.get(Position).get(partner_eid)
    if partner_pos is None or pos is None or int(partner_pos.z) != int(pos.z):
        return {"result": "partner_unavailable", "partner_eid": partner_eid}
    changed = record_partner_combat_witnesses(
        sim,
        threat_eid,
        eid,
        damage=damage or 0,
        x=(threat_pos or (None, None, None))[0] if threat_pos else None,
        y=(threat_pos or (None, None, None))[1] if threat_pos else None,
        z=(threat_pos or (None, None, None))[2] if threat_pos else None,
    )
    if not changed:
        memory = sim.ecs.get(NPCMemory).get(partner_eid)
        if memory is None:
            memory = NPCMemory()
            sim.ecs.add(partner_eid, memory)
        threat_record = _threat_pos_tuple(sim, threat_eid=threat_eid, threat_pos=threat_pos)
        memory.remember(
            tick=_tick(sim),
            kind="ally_threatened",
            strength=0.76,
            side_eid=eid,
            ally_eid=eid,
            against_eid=threat_eid,
            x=int(threat_record[0]) if threat_record else int(getattr(pos, "x", 0)),
            y=int(threat_record[1]) if threat_record else int(getattr(pos, "y", 0)),
            z=int(threat_record[2]) if threat_record else int(getattr(pos, "z", 0)),
            via="self_protection_partner_call",
        )
        threat_pos_component = sim.ecs.get(Position).get(threat_eid)
        partner_ai = sim.ecs.get(AI).get(partner_eid)
        if partner_ai is not None and threat_pos_component is not None:
            partner_ai.state = "protecting"
            partner_ai.target_eid = threat_eid
            partner_ai.target = (int(threat_pos_component.x), int(threat_pos_component.y), int(threat_pos_component.z))
        will = sim.ecs.get(NPCWill).get(partner_eid)
        if will is not None and threat_pos_component is not None:
            will.intent = "protecting"
            will.score = max(float(getattr(will, "score", 0.0) or 0.0), 90.0)
            will.target_eid = threat_eid
            will.target = (int(threat_pos_component.x), int(threat_pos_component.y), int(threat_pos_component.z))
            will.last_tick = _tick(sim)
        mark_actor_urgent(sim, partner_eid, family="will", reason="self_protection_partner_call", ttl_ticks=18)
        mark_actor_urgent(sim, partner_eid, family="move", reason="self_protection_partner_call", ttl_ticks=18)
        schedule_actor_due(sim, partner_eid, "will", delay_ticks=0, reason="self_protection_partner_call")
        schedule_actor_due(sim, partner_eid, "move", delay_ticks=0, reason="self_protection_partner_call")
    return {"result": "partner_alerted", "partner_eid": partner_eid, "changed": int(changed or 0)}


def build_self_protection_action(
    sim,
    eid,
    quirk,
    *,
    pos=None,
    threat_eid=None,
    threat_pos=None,
    base_target=None,
    reason="threat",
    damage=0,
) -> dict:
    quirk = _key(quirk)
    pos = pos or sim.ecs.get(Position).get(eid)
    now = _tick(sim)
    threat_pos = _threat_pos_tuple(sim, threat_eid=threat_eid, threat_pos=threat_pos)
    result = ""
    target = None
    until = now + 8
    if quirk == "hide_behind_counter":
        target = _nearest_cover_target(sim, eid, pos, threat_pos, max_steps=4) or base_target
        result = "cover_target" if target else "no_cover"
        until = now + 24
    elif quirk == "lock_nearest_door":
        lock_result = _try_lock_nearest_door(sim, eid, pos, threat_pos=threat_pos)
        result = str(lock_result.get("result", "no_door"))
        target = lock_result.get("door") or base_target
        until = now + 6
    elif quirk == "call_partner":
        call_result = _call_partner_for_help(sim, eid, threat_eid=threat_eid, damage=damage, pos=pos, threat_pos=threat_pos)
        result = str(call_result.get("result", "no_partner"))
        target = base_target
        until = now + 10
    elif quirk == "look_busy":
        result = "hold_posture"
        target = (int(pos.x), int(pos.y), int(pos.z)) if pos is not None else base_target
        until = now + 3
    elif quirk == "freeze":
        result = "frozen"
        target = (int(pos.x), int(pos.y), int(pos.z)) if pos is not None else base_target
        until = now + 4
    elif quirk == "slip_out_back":
        target = _slip_route_target(sim, eid, pos, threat_pos, max_steps=7) or base_target
        result = "slip_target" if target else "no_route"
        until = now + 28
    elif quirk == "shelter_with_crowd":
        target = _crowd_shelter_target(sim, eid, pos, threat_pos=threat_pos, threat_eid=threat_eid, max_steps=5) or base_target
        result = "crowd_target" if target and target != base_target else "fallback_target"
        until = now + 22
    elif quirk == "stand_ground":
        target = (int(pos.x), int(pos.y), int(pos.z)) if pos is not None else base_target
        result = "hold_ground"
        until = now + 18
    else:
        target = base_target
        result = "flavor_only"
    row = {
        "action": quirk,
        "result": result,
        "target": target,
        "threat_eid": threat_eid,
        "threat_pos": threat_pos,
        "reason": _key(reason) or "threat",
        "started_tick": now,
        "until_tick": int(until),
    }
    return _record_action(sim, eid, row)


def apply_self_protection_quirk(
    sim,
    eid,
    *,
    ai=None,
    pos=None,
    reason="threat",
    target=None,
    threat_eid=None,
    threat_pos=None,
    damage=0,
    forced_quirk=None,
) -> dict:
    row = choose_self_protection_quirk(sim, eid, ai=ai, pos=pos, reason=reason, forced_quirk=forced_quirk)
    if not row:
        return {}
    ai = ai or sim.ecs.get(AI).get(eid)
    action = build_self_protection_action(
        sim,
        eid,
        row["quirk"],
        pos=pos,
        threat_eid=threat_eid,
        threat_pos=threat_pos,
        base_target=target,
        reason=reason,
        damage=damage,
    )
    row["action"] = action
    if action.get("target") is not None:
        row["target"] = action.get("target")
    if ai is not None:
        setattr(ai, "self_protection_quirk", row["quirk"])
        setattr(ai, "self_protection_reason", row["reason"])
        setattr(ai, "self_protection_until_tick", row["cooldown_until"])
        if action:
            setattr(ai, "self_protection_action", action.get("action"))
            setattr(ai, "self_protection_action_target", action.get("target"))
            setattr(ai, "self_protection_action_until_tick", action.get("until_tick"))
            setattr(ai, "self_protection_action_result", action.get("result"))
    x = getattr(pos, "x", None)
    y = getattr(pos, "y", None)
    z = getattr(pos, "z", None)
    sim.emit(Event(
        "npc_self_protection_quirk",
        npc_eid=int(eid),
        quirk=row["quirk"],
        line=row["line"],
        reason=row["reason"],
        target=target,
        threat_eid=threat_eid,
        action=action.get("action") if isinstance(action, dict) else None,
        action_result=action.get("result") if isinstance(action, dict) else None,
        action_target=action.get("target") if isinstance(action, dict) else None,
        x=x,
        y=y,
        z=z,
    ))
    return row
