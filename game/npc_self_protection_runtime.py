"""Deterministic NPC self-protection flavor under threat."""

from __future__ import annotations

import random

from engine.events import Event
from game.components import AI, Occupation, Position
from game.npc_relationships import relationship_partner_eid
from game.property_runtime import property_covering, property_metadata


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
        state = {"cooldowns": {}}
        sim.npc_self_protection_state = state
    state.setdefault("cooldowns", {})
    return state


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


def choose_self_protection_quirk(sim, eid, *, ai=None, pos=None, reason="threat") -> dict:
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
    if until > now:
        return {}
    choices = _candidate_quirks(sim, eid, ai=ai, pos=pos)
    seed = f"{getattr(sim, 'seed', 0)}:self-protect:{eid}:{now // 120}:{reason}:{len(choices)}"
    rng = random.Random(seed)
    quirk = choices[rng.randrange(len(choices))]
    line_bank = _QUIRK_LINES.get(quirk, _QUIRK_LINES["freeze"])
    line = line_bank[rng.randrange(len(line_bank))]
    cooldowns[key] = now + 120
    return {
        "quirk": quirk,
        "line": line,
        "cooldown_until": cooldowns[key],
        "reason": _key(reason) or "threat",
    }


def apply_self_protection_quirk(sim, eid, *, ai=None, pos=None, reason="threat", target=None, threat_eid=None) -> dict:
    row = choose_self_protection_quirk(sim, eid, ai=ai, pos=pos, reason=reason)
    if not row:
        return {}
    ai = ai or sim.ecs.get(AI).get(eid)
    if ai is not None:
        setattr(ai, "self_protection_quirk", row["quirk"])
        setattr(ai, "self_protection_reason", row["reason"])
        setattr(ai, "self_protection_until_tick", row["cooldown_until"])
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
        x=x,
        y=y,
        z=z,
    ))
    return row
