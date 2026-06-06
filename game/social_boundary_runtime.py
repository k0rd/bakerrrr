"""Shared helpers for NPC social refusal and property ejection state."""

BOUNDARY_REFUSAL_TICKS = 90
BOUNDARY_EJECTION_GRACE_TICKS = 12
BOUNDARY_DIALOGUE_BAN_TICKS = 220
BOUNDARY_REFUSAL_VIOLENCE_THRESHOLD = 2

INCIDENT_DENY_TICKS_BY_KIND = {
    "trespass": 360,
    "property_trespass": 360,
    "tamper": 520,
    "property_tamper": 520,
    "theft": 720,
    "assault": 900,
    "weapon_discharge": 900,
}

INCIDENT_BAN_KINDS = {
    "trespass",
    "property_trespass",
    "tamper",
    "property_tamper",
    "theft",
    "assault",
    "weapon_discharge",
}


def _text(value):
    return str(value or "").strip()


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def active_ejection_state(sim):
    state = getattr(sim, "active_ejections", None)
    if not isinstance(state, dict):
        state = {}
        setattr(sim, "active_ejections", state)
    return state


def ejection_key(property_id, target_eid):
    property_id = _text(property_id)
    target_eid = _safe_int(target_eid, default=0)
    if not property_id or target_eid <= 0:
        return ""
    return f"{property_id}:{target_eid}"


def dialogue_refusal_active(memory_state, tick):
    if not isinstance(memory_state, dict):
        return False
    return _safe_int(memory_state.get("refusal_until_tick"), default=0) > _safe_int(tick, default=0)


def dialogue_refusal_remaining(memory_state, tick):
    if not isinstance(memory_state, dict):
        return 0
    return max(0, _safe_int(memory_state.get("refusal_until_tick"), default=0) - _safe_int(tick, default=0))


def eligible_incident_ban_kind(kind, tags=()):
    kind_key = _text(kind).lower()
    if kind_key in INCIDENT_BAN_KINDS:
        return kind_key
    tag_keys = {_text(tag).lower() for tag in tags or ()}
    for tag in tag_keys:
        if tag in INCIDENT_BAN_KINDS:
            return tag
    return ""
