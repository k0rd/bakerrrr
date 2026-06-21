"""Lawful-force classification helpers for justice accounting."""

from game.components import AI, Position, SuppressionState, Vitality
from game.system_support.offense_runtime import VIOLENT_OFFENSE_CONTEXTS


CRIMINAL_ATTACK = "criminal_attack"
LAWFUL_DEFENSE = "lawful_defense"
DEFENSE_OF_PROPERTY = "defense_of_property"
DEFENSE_OF_OTHER = "defense_of_other"
MUTUAL_FIGHT = "mutual_fight"
UNCLEAR = "unclear"

_HOSTILE_STATES = {"attacking", "chasing", "protecting", "hostile", "combat"}
_PROPERTY_DEFENSE_STATES = {"protecting", "warning", "chasing"}


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _target_eid_from_data(data):
    if not isinstance(data, dict):
        return None
    for key in ("target_eid", "victim_eid", "defender_target_eid"):
        if data.get(key) is not None:
            return data.get(key)
    return None


def _ai_for(sim, eid):
    if sim is None or eid is None:
        return None
    return sim.ecs.get(AI).get(eid)


def _is_downed_or_surrendered(sim, eid):
    if sim is None or eid is None:
        return False
    vitality = sim.ecs.get(Vitality).get(eid)
    if vitality is not None and bool(getattr(vitality, "downed", False)):
        return True
    suppression = sim.ecs.get(SuppressionState).get(eid)
    if suppression is not None and bool(getattr(suppression, "surrendered", False)):
        return True
    ai = _ai_for(sim, eid)
    state = str(getattr(ai, "state", "") or "").strip().lower() if ai is not None else ""
    return state in {"downed", "surrendered"}


def _ai_targets(ai, eid):
    if ai is None or eid is None:
        return False
    try:
        return int(getattr(ai, "target_eid", -1)) == int(eid)
    except (TypeError, ValueError):
        return False


def _hostile_toward(sim, actor_eid, target_eid):
    ai = _ai_for(sim, actor_eid)
    if ai is None:
        return False
    state = str(getattr(ai, "state", "") or "").strip().lower()
    return state in _HOSTILE_STATES and _ai_targets(ai, target_eid)


def _active_threat_toward(sim, actor_eid, target_eid):
    ai = _ai_for(sim, actor_eid)
    if ai is None or not _ai_targets(ai, target_eid):
        return False
    state = str(getattr(ai, "state", "") or "").strip().lower()
    if state == "attacking":
        return _same_tile_or_near(sim, actor_eid, target_eid, radius=8)
    if state in {"chasing", "combat", "protecting"}:
        return _same_tile_or_near(sim, actor_eid, target_eid, radius=3)
    return False


def _position_tuple(sim, eid):
    if sim is None or eid is None:
        return None
    pos = sim.ecs.get(Position).get(eid)
    if pos is None:
        return None
    return (_safe_int(getattr(pos, "x", 0)), _safe_int(getattr(pos, "y", 0)), _safe_int(getattr(pos, "z", 0)))


def _same_tile_or_near(sim, eid_a, eid_b, radius=2):
    a = _position_tuple(sim, eid_a)
    b = _position_tuple(sim, eid_b)
    if not a or not b or a[2] != b[2]:
        return False
    return abs(a[0] - b[0]) + abs(a[1] - b[1]) <= int(radius)


def _offender_defending_property(sim, offender_eid, target_eid, data):
    ai = _ai_for(sim, offender_eid)
    if ai is None or target_eid is None:
        return False
    state = str(getattr(ai, "state", "") or "").strip().lower()
    if state not in _PROPERTY_DEFENSE_STATES or not _ai_targets(ai, target_eid):
        return False
    if data.get("property_id") or data.get("target_property_id"):
        return True
    role = str(getattr(ai, "role", "") or "").strip().lower()
    return role in {"guard", "security", "officer", "police", "deputy", "marshal"}


def classify_lawful_force(sim, data, *, offender_eid=None):
    """Return a conservative force-context read for a violent action offense.

    The helper suppresses only clean defense cases. Ambiguous violence remains
    recordable so existing justice behavior keeps carrying uncertain cases.
    """
    data = data if isinstance(data, dict) else {}
    context = str(data.get("context", "") or "").strip().lower()
    if context not in VIOLENT_OFFENSE_CONTEXTS:
        return {
            "force_context": UNCLEAR,
            "force_reason": "not a violent-force context",
            "severity_mitigation": 0,
            "recordable": True,
            "suppressed": False,
        }
    offender_eid = offender_eid if offender_eid is not None else data.get("offender_eid")
    target_eid = _target_eid_from_data(data)

    if context == "explosive_discharge":
        return {
            "force_context": CRIMINAL_ATTACK,
            "force_reason": "explosive force stays criminally serious",
            "severity_mitigation": 0,
            "recordable": True,
            "suppressed": False,
        }
    if target_eid is None:
        return {
            "force_context": UNCLEAR,
            "force_reason": "no clear target for the violent force",
            "severity_mitigation": 0,
            "recordable": True,
            "suppressed": False,
        }
    if _is_downed_or_surrendered(sim, target_eid):
        return {
            "force_context": CRIMINAL_ATTACK,
            "force_reason": "target was downed or surrendered",
            "severity_mitigation": 0,
            "recordable": True,
            "suppressed": False,
        }
    if _offender_defending_property(sim, offender_eid, target_eid, data):
        return {
            "force_context": DEFENSE_OF_PROPERTY,
            "force_reason": "defender was responding to a protected property target",
            "severity_mitigation": 1.0,
            "recordable": False,
            "suppressed": True,
        }
    if _active_threat_toward(sim, target_eid, offender_eid):
        offender_ai = _ai_for(sim, offender_eid)
        if offender_ai is not None and _hostile_toward(sim, offender_eid, target_eid):
            return {
                "force_context": MUTUAL_FIGHT,
                "force_reason": "both sides were actively targeting each other",
                "severity_mitigation": 0.35,
                "recordable": True,
                "suppressed": False,
            }
        return {
            "force_context": LAWFUL_DEFENSE,
            "force_reason": "target was actively threatening the actor",
            "severity_mitigation": 1.0,
            "recordable": False,
            "suppressed": True,
        }
    target_ai = _ai_for(sim, target_eid)
    protected_eid = getattr(target_ai, "target_eid", None) if target_ai is not None else None
    if protected_eid is not None and _active_threat_toward(sim, target_eid, protected_eid) and _same_tile_or_near(sim, offender_eid, protected_eid, radius=4):
        return {
            "force_context": DEFENSE_OF_OTHER,
            "force_reason": "target was threatening someone nearby",
            "severity_mitigation": 1.0,
            "recordable": False,
            "suppressed": True,
        }
    return {
        "force_context": CRIMINAL_ATTACK,
        "force_reason": "no concrete defensive threat was present",
        "severity_mitigation": 0,
        "recordable": True,
        "suppressed": False,
    }


def mitigated_force_severity(severity, force_read):
    try:
        severity = int(severity or 0)
    except (TypeError, ValueError):
        severity = 0
    if severity <= 0:
        return 0
    if not isinstance(force_read, dict):
        return severity
    if bool(force_read.get("suppressed")) or not bool(force_read.get("recordable", True)):
        return 0
    try:
        mitigation = float(force_read.get("severity_mitigation", 0) or 0)
    except (TypeError, ValueError):
        mitigation = 0.0
    mitigation = max(0.0, min(0.9, mitigation))
    return max(1, int(round(float(severity) * (1.0 - mitigation))))


def force_payload(force_read):
    force_read = force_read if isinstance(force_read, dict) else {}
    return {
        "force_context": str(force_read.get("force_context", UNCLEAR) or UNCLEAR).strip().lower(),
        "force_reason": str(force_read.get("force_reason", "") or "").strip(),
        "severity_mitigation": force_read.get("severity_mitigation", 0),
    }
