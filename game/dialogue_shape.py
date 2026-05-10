"""Context-shaped NPC dialogue helpers.

This module is intentionally small and read-only.  It does not decide gameplay;
it turns already-known NPC state into short conversational surfaces so the
player can feel the social simulation without every line becoming exposition.
"""

from __future__ import annotations

import random

from game.components import AI, CreatureIdentity, IncidentKnowledge, Position
from game.incident_runtime import incident_record


_AUTHORITY_ROLES = {"guard", "security", "officer", "police", "deputy", "marshal"}
_SERVICE_ROLES = {"clerk", "cashier", "merchant", "shopkeeper", "manager", "worker"}


def _text(value, default=""):
    text = str(value or "").strip()
    return text if text else str(default or "").strip()


def _float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _entity_name(sim, eid, *, fallback="someone"):
    if eid is None:
        return fallback
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    if identity is None:
        return fallback
    for attr in ("personal_name", "common_name", "species"):
        name = _text(getattr(identity, attr, ""))
        if name:
            return name
    return fallback


def _distance_to_player(sim, x, y, z=0):
    player_eid = getattr(sim, "player_eid", None)
    if player_eid is None:
        return None
    player_pos = sim.ecs.get(Position).get(player_eid)
    if not player_pos:
        return None
    if _int(getattr(player_pos, "z", 0)) != _int(z, 0):
        return None
    return abs(_int(x) - _int(getattr(player_pos, "x", 0))) + abs(_int(y) - _int(getattr(player_pos, "y", 0)))


def _direction_from_player(sim, x, y, z=0):
    player_eid = getattr(sim, "player_eid", None)
    if player_eid is None:
        return "nearby"
    player_pos = sim.ecs.get(Position).get(player_eid)
    if not player_pos or _int(getattr(player_pos, "z", 0)) != _int(z, 0):
        return "nearby"
    dx = _int(x) - _int(getattr(player_pos, "x", 0))
    dy = _int(y) - _int(getattr(player_pos, "y", 0))
    if abs(dx) <= 1 and abs(dy) <= 1:
        return "right here"
    horiz = "east" if dx > 0 else "west" if dx < 0 else ""
    vert = "south" if dy > 0 else "north" if dy < 0 else ""
    if horiz and vert:
        return f"{vert}-{horiz}"
    return horiz or vert or "nearby"


def _incident_label(record, incident):
    kind = _text((incident or {}).get("kind") if isinstance(incident, dict) else "").lower()
    category = _text(record.get("category", "")).lower()
    tags = {
        _text(tag).lower()
        for tag in tuple((incident or {}).get("tags", ()) or ())
        if _text(tag)
    } if isinstance(incident, dict) else set()
    if kind == "property_trespass" or category == "property_trespass" or "trespass" in tags:
        return "trespass"
    if kind == "property_tamper" or "tamper" in tags or "alarm" in tags:
        return "tampering"
    if kind == "item_stolen" or "stolen" in tags or "theft" in tags:
        return "theft"
    if kind == "camera_alert" or "camera" in tags:
        return "camera hit"
    if kind == "action_offense" or "violence" in tags or "assault" in tags:
        return "violence"
    return kind.replace("_", " ") if kind else category.replace("_", " ") if category else "trouble"


def _best_incident_context(sim, npc_eid):
    knowledge = sim.ecs.get(IncidentKnowledge).get(npc_eid)
    if not knowledge or not isinstance(getattr(knowledge, "records", None), dict):
        return None
    best = None
    for incident_id, record in knowledge.records.items():
        if not isinstance(record, dict):
            continue
        incident = incident_record(sim, incident_id) or {}
        severity = max(_int(record.get("severity"), 0), _int(incident.get("severity"), 0) if isinstance(incident, dict) else 0)
        urgency = _float(record.get("urgency"), 0.0)
        social = _float(record.get("social_interest"), 0.0)
        firsthand = bool(record.get("firsthand"))
        confidence = _float(record.get("confidence"), 0.0)
        score = (severity / 100.0) * 0.36 + urgency * 0.34 + social * 0.2 + confidence * 0.08 + (0.08 if firsthand else 0.0)
        learned_tick = _int(record.get("last_learned_tick", record.get("learned_tick", 0)), 0)
        candidate = (score, learned_tick, incident_id, record, incident)
        if best is None or candidate > best:
            best = candidate
    if best is None:
        return None
    _score, _tick, incident_id, record, incident = best
    return {
        "incident_id": incident_id,
        "record": record,
        "incident": incident if isinstance(incident, dict) else {},
        "label": _incident_label(record, incident if isinstance(incident, dict) else {}),
        "firsthand": bool(record.get("firsthand")),
        "confidence": _float(record.get("confidence"), 0.0),
        "urgency": _float(record.get("urgency"), 0.0),
        "social_interest": _float(record.get("social_interest"), 0.0),
        "severity": max(_int(record.get("severity"), 0), _int((incident or {}).get("severity"), 0) if isinstance(incident, dict) else 0),
        "source_kind": _text(record.get("source_kind", "")).lower(),
        "propagation_depth": _int(record.get("propagation_depth"), 0),
        "officially_reported": bool((incident or {}).get("officially_reported")) if isinstance(incident, dict) else False,
        "x": record.get("x", (incident or {}).get("x") if isinstance(incident, dict) else None),
        "y": record.get("y", (incident or {}).get("y") if isinstance(incident, dict) else None),
        "z": record.get("z", (incident or {}).get("z") if isinstance(incident, dict) else 0),
    }


def build_dialogue_shape(sim, npc_eid, *, context=None):
    """Return short, player-facing dialogue facts for an NPC.

    The result is a dict because the monolithic dialogue system already passes
    a context dict around.  Keep this read-only and deterministic.
    """
    context = dict(context or {})
    ai = sim.ecs.get(AI).get(npc_eid)
    role = _text(getattr(ai, "role", context.get("role_id", "local"))).lower() or "local"
    tone = _text(context.get("tone", "neutral")).lower() or "neutral"
    pressure = _text(context.get("pressure_tier", "low")).lower() or "low"
    incident = _best_incident_context(sim, npc_eid)
    shape = {
        "role": role,
        "tone": tone,
        "pressure_tier": pressure,
        "has_incident": bool(incident),
        "opening_lines": [],
        "local_line": "",
        "concern_line": "",
        "debug_tags": [],
    }
    if incident:
        label = incident["label"]
        firsthand = incident["firsthand"]
        urgency = incident["urgency"]
        social = incident["social_interest"]
        confidence = incident["confidence"]
        source_kind = incident["source_kind"]
        depth = incident["propagation_depth"]
        reported = incident["officially_reported"]
        where = "nearby"
        if incident.get("x") is not None and incident.get("y") is not None:
            direction = _direction_from_player(sim, incident.get("x"), incident.get("y"), incident.get("z", 0))
            dist = _distance_to_player(sim, incident.get("x"), incident.get("y"), incident.get("z", 0))
            if dist is not None and dist > 1:
                where = f"{direction}, about {dist} blocks"
            else:
                where = direction

        if urgency >= 0.62:
            if role in _AUTHORITY_ROLES:
                line = f"Stay clear. I am checking out {label} {where}."
            elif reported:
                line = f"People already called this in. I would not linger around that {label}."
            else:
                line = f"Something ugly happened {where}. Keep moving."
            shape["opening_lines"].append(line)
            shape["concern_line"] = line
            shape["debug_tags"].append("urgent_incident")
        elif social >= 0.34:
            if firsthand:
                line = f"I saw enough of that {label} to keep my mouth small."
            elif depth > 0 or source_kind in {"social_rumor", "rumor"}:
                line = f"People are talking about some {label} {where}. Could be bent by now."
            elif confidence < 0.48:
                line = f"Something about {label} is going around, but I would not swear to it."
            else:
                line = f"Word is there was {label} {where}."
            shape["local_line"] = line
            if tone in {"friendly", "open", "neutral"}:
                shape["opening_lines"].append(line)
            shape["debug_tags"].append("social_incident")

    if not shape["opening_lines"]:
        if role in _SERVICE_ROLES and pressure == "high":
            shape["opening_lines"].append("If you need something, make it quick.")
            shape["debug_tags"].append("service_pressure")
        elif role in _AUTHORITY_ROLES and tone in {"wary", "guarded"}:
            shape["opening_lines"].append("Keep your hands where I can see them and talk plain.")
            shape["debug_tags"].append("authority_guarded")

    # Deterministically avoid always choosing the same extra line if several
    # future producers add lines.
    if len(shape["opening_lines"]) > 1:
        rng = random.Random(f"{getattr(sim, 'seed', 0)}:dialogue-shape:{npc_eid}:{getattr(sim, 'tick', 0)}")
        rng.shuffle(shape["opening_lines"])
    shape["opening_lines"] = tuple(line for line in shape["opening_lines"] if _text(line))[:2]
    return shape


def shaped_opening_lines(context, *, limit=1):
    shape = context.get("dialogue_shape") if isinstance(context, dict) else None
    if not isinstance(shape, dict):
        return ()
    return tuple(_text(line) for line in tuple(shape.get("opening_lines", ()) or ()) if _text(line))[: max(0, int(limit))]


def shaped_local_line(context):
    shape = context.get("dialogue_shape") if isinstance(context, dict) else None
    if not isinstance(shape, dict):
        return ""
    return _text(shape.get("local_line", ""))


def shaped_concern_line(context):
    shape = context.get("dialogue_shape") if isinstance(context, dict) else None
    if not isinstance(shape, dict):
        return ""
    return _text(shape.get("concern_line", ""))
