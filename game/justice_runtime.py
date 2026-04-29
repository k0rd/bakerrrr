from __future__ import annotations


MAX_ACTIVE_SCORE = 100
MAX_INCIDENT_HISTORY = 24
DECAY_INTERVAL = 60
DECAY_IDLE_TICKS = 120

WANTED_TIERS = (
    (30, "arrest_on_sight"),
    (16, "wanted"),
    (6, "questioning"),
)

INCIDENT_REPEAT_COOLDOWNS = {
    "trespass": 12,
    "tamper": 16,
    "theft": 16,
    "contraband": 14,
    "armed_assault": 18,
    "explosive_discharge": 22,
}

INCIDENT_LABELS = {
    "trespass": "trespass",
    "tamper": "tampering",
    "theft": "theft",
    "contraband": "contraband use",
    "armed_assault": "armed assault",
    "explosive_discharge": "explosive discharge",
}


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _text(value):
    return str(value or "").strip()


def _slug(value):
    text = _text(value).lower()
    chars = []
    last_sep = False
    for ch in text:
        if ch.isalnum():
            chars.append(ch)
            last_sep = False
        elif not last_sep:
            chars.append("_")
            last_sep = True
    return "".join(chars).strip("_")


def wanted_tier_for(score, *, in_custody=False):
    if in_custody:
        return "held"
    value = max(0, min(MAX_ACTIVE_SCORE, _safe_int(score, default=0)))
    for threshold, label in WANTED_TIERS:
        if value >= int(threshold):
            return str(label)
    return "clear"


def wanted_label(tier):
    tier = _text(tier).lower()
    if tier == "arrest_on_sight":
        return "arrest on sight"
    if tier == "questioning":
        return "wanted for questioning"
    if tier == "held":
        return "held in custody"
    return tier or "clear"


def _state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits

    state = traits.get("criminal_justice")
    if not isinstance(state, dict):
        state = {}
        traits["criminal_justice"] = state

    offenders = state.get("offenders")
    if not isinstance(offenders, dict):
        offenders = {}
        state["offenders"] = offenders

    state["last_decay_tick"] = _safe_int(state.get("last_decay_tick"), default=-10_000)
    return state


def _offender_record(state, offender_eid, *, create=False):
    try:
        offender_key = str(int(offender_eid))
    except (TypeError, ValueError):
        return None
    offenders = state.get("offenders", {})
    record = offenders.get(offender_key)
    if not isinstance(record, dict):
        if not create:
            return None
        record = {
            "eid": int(offender_eid),
            "active_score": 0,
            "peak_score": 0,
            "incident_count": 0,
            "incidents": [],
            "recent_keys": {},
            "last_incident_tick": -10_000,
            "last_change_tick": -10_000,
            "last_jurisdiction_key": "",
            "last_jurisdiction_name": "",
            "in_custody": False,
            "custody_tick": -10_000,
            "held_by_eid": None,
        }
        offenders[offender_key] = record

    record["eid"] = _safe_int(record.get("eid"), default=offender_eid)
    record["active_score"] = max(0, min(MAX_ACTIVE_SCORE, _safe_int(record.get("active_score"), default=0)))
    record["peak_score"] = max(record["active_score"], _safe_int(record.get("peak_score"), default=record["active_score"]))
    record["incident_count"] = max(0, _safe_int(record.get("incident_count"), default=0))
    incidents = record.get("incidents")
    if not isinstance(incidents, list):
        incidents = []
    if len(incidents) > MAX_INCIDENT_HISTORY:
        incidents = incidents[-MAX_INCIDENT_HISTORY:]
    record["incidents"] = incidents
    recent_keys = record.get("recent_keys")
    if not isinstance(recent_keys, dict):
        recent_keys = {}
    record["recent_keys"] = recent_keys
    record["last_incident_tick"] = _safe_int(record.get("last_incident_tick"), default=-10_000)
    record["last_change_tick"] = _safe_int(record.get("last_change_tick"), default=-10_000)
    record["last_jurisdiction_key"] = _text(record.get("last_jurisdiction_key")).lower()
    record["last_jurisdiction_name"] = _text(record.get("last_jurisdiction_name"))
    record["in_custody"] = bool(record.get("in_custody", False))
    record["custody_tick"] = _safe_int(record.get("custody_tick"), default=-10_000)
    held_by = record.get("held_by_eid")
    try:
        record["held_by_eid"] = int(held_by) if held_by is not None else None
    except (TypeError, ValueError):
        record["held_by_eid"] = None
    return record


def jurisdiction_for_position(sim, *, x=None, y=None):
    try:
        if x is None or y is None:
            raise ValueError
        cx, cy = sim.chunk_coords(int(x), int(y))
    except Exception:
        cx = 0
        cy = 0
    world = getattr(sim, "world", None)
    descriptor = world.overworld_descriptor(cx, cy) if world is not None else {}
    descriptor = descriptor if isinstance(descriptor, dict) else {}
    scope = (
        _text(descriptor.get("settlement_name"))
        or _text(descriptor.get("region_name"))
        or "Local"
    )
    scope_slug = _slug(scope) or "local"
    return {
        "key": f"justice:{scope_slug}",
        "name": f"{scope} Justice Office".strip(),
        "chunk": (int(cx), int(cy)),
        "settlement_name": _text(descriptor.get("settlement_name")),
        "region_name": _text(descriptor.get("region_name")),
    }


def justice_snapshot(sim, offender_eid):
    state = _state(sim)
    record = _offender_record(state, offender_eid, create=False)
    if not isinstance(record, dict):
        return {
            "eid": _safe_int(offender_eid, default=0),
            "active_score": 0,
            "peak_score": 0,
            "incident_count": 0,
            "last_incident_tick": -10_000,
            "last_jurisdiction_key": "",
            "last_jurisdiction_name": "",
            "wanted_tier": "clear",
            "wanted_label": wanted_label("clear"),
            "in_custody": False,
            "held_by_eid": None,
            "latest_incident": None,
        }
    incidents = record.get("incidents", [])
    latest = incidents[-1] if incidents else None
    tier = wanted_tier_for(record.get("active_score", 0), in_custody=bool(record.get("in_custody", False)))
    return {
        "eid": int(record["eid"]),
        "active_score": int(record["active_score"]),
        "peak_score": int(record["peak_score"]),
        "incident_count": int(record["incident_count"]),
        "last_incident_tick": int(record["last_incident_tick"]),
        "last_jurisdiction_key": _text(record.get("last_jurisdiction_key")).lower(),
        "last_jurisdiction_name": _text(record.get("last_jurisdiction_name")),
        "wanted_tier": tier,
        "wanted_label": wanted_label(tier),
        "in_custody": bool(record.get("in_custody", False)),
        "held_by_eid": record.get("held_by_eid"),
        "latest_incident": dict(latest) if isinstance(latest, dict) else None,
    }


def _incident_weight(incident_type, *, severity=0, witnessed=False):
    incident_type = _text(incident_type).lower()
    severity = max(0, _safe_int(severity, default=0))
    witnessed_bonus = 2 if witnessed else 0
    if incident_type == "trespass":
        return min(12, 4 + (severity // 20) + witnessed_bonus)
    if incident_type == "tamper":
        return min(18, 7 + (severity // 18) + witnessed_bonus)
    if incident_type == "theft":
        return min(18, 9 + (severity // 16) + witnessed_bonus)
    if incident_type == "contraband":
        return min(16, 7 + (severity // 14) + witnessed_bonus)
    if incident_type == "armed_assault":
        return min(26, 16 + (severity // 10) + witnessed_bonus)
    if incident_type == "explosive_discharge":
        return min(32, 22 + (severity // 8) + witnessed_bonus)
    return min(10, 3 + (severity // 24) + witnessed_bonus)


def _prune_recent_keys(record, tick):
    recent_keys = record.get("recent_keys", {})
    if not isinstance(recent_keys, dict):
        record["recent_keys"] = {}
        return
    stale_before = int(tick) - (max(INCIDENT_REPEAT_COOLDOWNS.values()) * 4)
    cleaned = {
        str(key): _safe_int(value, default=stale_before)
        for key, value in recent_keys.items()
        if _safe_int(value, default=stale_before - 1) >= stale_before
    }
    record["recent_keys"] = cleaned


def record_incident(
    sim,
    offender_eid,
    *,
    incident_type,
    severity=0,
    source_event="",
    property_id=None,
    x=None,
    y=None,
    witnessed=False,
    note="",
):
    state = _state(sim)
    record = _offender_record(state, offender_eid, create=True)
    if not isinstance(record, dict):
        return None

    tick = _safe_int(getattr(sim, "tick", 0), default=0)
    incident_type = _text(incident_type).lower()
    before_score = int(record["active_score"])
    before_tier = wanted_tier_for(before_score, in_custody=bool(record.get("in_custody", False)))
    if record.get("in_custody", False):
        record["in_custody"] = False
        record["custody_tick"] = -10_000
        record["held_by_eid"] = None

    jurisdiction = jurisdiction_for_position(sim, x=x, y=y)
    source_key = _text(source_event).lower() or incident_type
    repeat_scope = _text(property_id).lower() or jurisdiction["key"]
    recent_key = f"{incident_type}:{source_key}:{repeat_scope}"
    cooldown = int(INCIDENT_REPEAT_COOLDOWNS.get(incident_type, 12))
    last_tick = _safe_int(record.get("recent_keys", {}).get(recent_key), default=-10_000)
    if tick - last_tick < cooldown:
        return None

    weight = _incident_weight(incident_type, severity=severity, witnessed=witnessed)
    after_score = max(before_score, min(MAX_ACTIVE_SCORE, before_score + weight))
    record["active_score"] = int(after_score)
    record["peak_score"] = max(int(record["peak_score"]), int(after_score))
    record["incident_count"] = int(record["incident_count"]) + 1
    record["last_incident_tick"] = tick
    record["last_change_tick"] = tick
    record["last_jurisdiction_key"] = _text(jurisdiction["key"]).lower()
    record["last_jurisdiction_name"] = _text(jurisdiction["name"])
    record["recent_keys"][recent_key] = tick
    _prune_recent_keys(record, tick)

    incident = {
        "tick": tick,
        "type": incident_type,
        "label": _text(INCIDENT_LABELS.get(incident_type, incident_type.replace("_", " "))),
        "source_event": source_key,
        "severity": max(0, _safe_int(severity, default=0)),
        "weight": int(weight),
        "witnessed": bool(witnessed),
        "property_id": _text(property_id),
        "jurisdiction_key": _text(jurisdiction["key"]).lower(),
        "jurisdiction_name": _text(jurisdiction["name"]),
        "settlement_name": _text(jurisdiction.get("settlement_name")),
        "region_name": _text(jurisdiction.get("region_name")),
        "note": _text(note),
    }
    record["incidents"].append(incident)
    if len(record["incidents"]) > MAX_INCIDENT_HISTORY:
        del record["incidents"][:-MAX_INCIDENT_HISTORY]

    after_tier = wanted_tier_for(record["active_score"], in_custody=False)
    return {
        "eid": int(record["eid"]),
        "before_score": int(before_score),
        "after_score": int(record["active_score"]),
        "before_tier": before_tier,
        "after_tier": after_tier,
        "tier_changed": before_tier != after_tier,
        "incident_count": int(record["incident_count"]),
        "incident": dict(incident),
    }


def decay_records(sim, *, interval=DECAY_INTERVAL, idle_ticks=DECAY_IDLE_TICKS, step=1):
    state = _state(sim)
    tick = _safe_int(getattr(sim, "tick", 0), default=0)
    last_decay_tick = _safe_int(state.get("last_decay_tick"), default=-10_000)
    if tick - last_decay_tick < int(interval):
        return []

    changes = []
    for offender_key in tuple(state.get("offenders", {}).keys()):
        record = _offender_record(state, offender_key, create=False)
        if not isinstance(record, dict):
            continue
        if bool(record.get("in_custody", False)):
            continue
        before_score = int(record["active_score"])
        if before_score <= 0:
            continue
        if tick - int(record.get("last_incident_tick", -10_000)) < int(idle_ticks):
            continue
        before_tier = wanted_tier_for(before_score, in_custody=False)
        after_score = max(0, before_score - max(1, int(step)))
        if after_score == before_score:
            continue
        record["active_score"] = int(after_score)
        record["last_change_tick"] = tick
        after_tier = wanted_tier_for(after_score, in_custody=False)
        changes.append({
            "eid": int(record["eid"]),
            "before_score": before_score,
            "after_score": int(after_score),
            "before_tier": before_tier,
            "after_tier": after_tier,
            "tier_changed": before_tier != after_tier,
            "reason": "cooldown",
            "last_jurisdiction_key": _text(record.get("last_jurisdiction_key")).lower(),
            "last_jurisdiction_name": _text(record.get("last_jurisdiction_name")),
        })
    state["last_decay_tick"] = tick
    return changes


def mark_in_custody(sim, offender_eid, *, held_by_eid=None, x=None, y=None):
    state = _state(sim)
    record = _offender_record(state, offender_eid, create=True)
    if not isinstance(record, dict):
        return None
    tick = _safe_int(getattr(sim, "tick", 0), default=0)
    before_score = int(record["active_score"])
    before_tier = wanted_tier_for(before_score, in_custody=bool(record.get("in_custody", False)))
    jurisdiction = jurisdiction_for_position(sim, x=x, y=y)
    record["in_custody"] = True
    record["custody_tick"] = tick
    record["held_by_eid"] = _safe_int(held_by_eid, default=0) if held_by_eid is not None else None
    record["last_change_tick"] = tick
    record["last_jurisdiction_key"] = _text(jurisdiction["key"]).lower()
    record["last_jurisdiction_name"] = _text(jurisdiction["name"])
    after_tier = wanted_tier_for(before_score, in_custody=True)
    return {
        "eid": int(record["eid"]),
        "before_score": before_score,
        "after_score": before_score,
        "before_tier": before_tier,
        "after_tier": after_tier,
        "tier_changed": before_tier != after_tier,
        "held_by_eid": record.get("held_by_eid"),
        "jurisdiction_key": _text(jurisdiction["key"]).lower(),
        "jurisdiction_name": _text(jurisdiction["name"]),
    }


def release_from_custody(sim, offender_eid, *, new_score=None, x=None, y=None):
    state = _state(sim)
    record = _offender_record(state, offender_eid, create=True)
    if not isinstance(record, dict):
        return None

    tick = _safe_int(getattr(sim, "tick", 0), default=0)
    before_score = int(record["active_score"])
    before_tier = wanted_tier_for(before_score, in_custody=bool(record.get("in_custody", False)))
    after_score = before_score if new_score is None else max(
        0,
        min(MAX_ACTIVE_SCORE, _safe_int(new_score, default=before_score)),
    )
    jurisdiction = jurisdiction_for_position(sim, x=x, y=y)
    record["active_score"] = int(after_score)
    record["in_custody"] = False
    record["custody_tick"] = -10_000
    record["held_by_eid"] = None
    record["last_change_tick"] = tick
    record["last_jurisdiction_key"] = _text(jurisdiction["key"]).lower()
    record["last_jurisdiction_name"] = _text(jurisdiction["name"])
    after_tier = wanted_tier_for(after_score, in_custody=False)
    return {
        "eid": int(record["eid"]),
        "before_score": before_score,
        "after_score": int(after_score),
        "before_tier": before_tier,
        "after_tier": after_tier,
        "tier_changed": before_tier != after_tier,
        "jurisdiction_key": _text(jurisdiction["key"]).lower(),
        "jurisdiction_name": _text(jurisdiction["name"]),
    }


def justice_summary_rows(sim, offender_eid):
    snapshot = justice_snapshot(sim, offender_eid)
    status = str(snapshot.get("wanted_tier", "clear")).strip().lower() or "clear"
    score = max(0, _safe_int(snapshot.get("active_score"), default=0))
    incident_count = max(0, _safe_int(snapshot.get("incident_count"), default=0))
    jurisdiction = _text(snapshot.get("last_jurisdiction_name")) or "Local Justice Office"
    latest = snapshot.get("latest_incident") if isinstance(snapshot.get("latest_incident"), dict) else {}
    latest_label = _text(latest.get("label")) or "incident"

    if status == "held":
        return [
            f"Held in custody by {jurisdiction}.",
            f"Recorded incidents {incident_count}; latest {latest_label}.",
        ]
    if score <= 0 and incident_count <= 0:
        return ["Legal clear. No active justice attention."]

    if status == "clear":
        lead = f"Legal attention is cooling in {jurisdiction}."
    else:
        lead = f"Status {wanted_label(status)} in {jurisdiction}."
    return [
        lead,
        f"Legal pressure {score} | recorded incidents {incident_count} | latest {latest_label}.",
    ]
