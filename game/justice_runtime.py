from __future__ import annotations

from game.components import FinancialProfile


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
    "resisting_custody": 14,
    "unarmed_assault": 14,
    "melee_assault": 16,
    "armed_assault": 18,
    "explosive_discharge": 22,
}

INCIDENT_LABELS = {
    "trespass": "trespass",
    "tamper": "tampering",
    "theft": "theft",
    "contraband": "contraband use",
    "resisting_custody": "resisting custody",
    "unarmed_assault": "unarmed assault",
    "melee_assault": "armed melee assault",
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


def _release_grace_records(state):
    records = state.get("release_grace")
    if not isinstance(records, dict):
        records = {}
        state["release_grace"] = records
    return records


def _release_grace_property_key(property_id):
    if isinstance(property_id, dict):
        property_id = property_id.get("id")
    return _text(property_id)


def grant_custody_release_grace(sim, offender_eid, property_id, *, duration=18, reason="custody_release"):
    try:
        offender_key = str(int(offender_eid))
    except (TypeError, ValueError):
        return False
    property_key = _release_grace_property_key(property_id)
    if not property_key:
        return False

    state = _state(sim)
    records = _release_grace_records(state)
    actor_records = records.get(offender_key)
    if not isinstance(actor_records, dict):
        actor_records = {}
        records[offender_key] = actor_records

    tick = _safe_int(getattr(sim, "tick", 0), default=0)
    actor_records[property_key] = {
        "property_id": property_key,
        "granted_tick": tick,
        "expires_tick": tick + max(1, _safe_int(duration, default=18)),
        "reason": _text(reason).lower() or "custody_release",
    }
    return True


def custody_release_grace_active(sim, offender_eid, property_id):
    try:
        offender_key = str(int(offender_eid))
    except (TypeError, ValueError):
        return False
    property_key = _release_grace_property_key(property_id)
    if not property_key:
        return False

    state = _state(sim)
    records = _release_grace_records(state)
    actor_records = records.get(offender_key)
    if not isinstance(actor_records, dict):
        return False

    entry = actor_records.get(property_key)
    if not isinstance(entry, dict):
        return False

    tick = _safe_int(getattr(sim, "tick", 0), default=0)
    expires_tick = _safe_int(entry.get("expires_tick"), default=-1)
    if expires_tick < tick:
        actor_records.pop(property_key, None)
        if not actor_records:
            records.pop(offender_key, None)
        return False
    return True


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
            "held_property_site_id": "",
            "held_property_site_name": "",
            "held_property_entries": [],
            "held_property_updated_tick": -10_000,
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
    record["held_property_site_id"] = _text(record.get("held_property_site_id"))
    record["held_property_site_name"] = _text(record.get("held_property_site_name"))
    held_entries = record.get("held_property_entries")
    if not isinstance(held_entries, list):
        held_entries = []
    cleaned_entries = []
    for entry in held_entries:
        if not isinstance(entry, dict):
            continue
        item_id = _text(entry.get("item_id")).lower()
        instance_id = _text(entry.get("instance_id"))
        quantity = max(1, _safe_int(entry.get("quantity"), default=1))
        if not item_id or not instance_id:
            continue
        metadata = entry.get("metadata")
        cleaned_entries.append({
            "instance_id": instance_id,
            "item_id": item_id,
            "quantity": quantity,
            "owner_eid": entry.get("owner_eid"),
            "owner_tag": _text(entry.get("owner_tag")),
            "metadata": dict(metadata) if isinstance(metadata, dict) else {},
        })
    record["held_property_entries"] = cleaned_entries
    record["held_property_updated_tick"] = _safe_int(record.get("held_property_updated_tick"), default=-10_000)
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
            "held_property_count": 0,
            "held_property_site_id": "",
            "held_property_site_name": "",
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
        "held_property_count": int(sum(max(1, _safe_int(entry.get("quantity"), default=1)) for entry in record.get("held_property_entries", ()) if isinstance(entry, dict))),
        "held_property_site_id": _text(record.get("held_property_site_id")),
        "held_property_site_name": _text(record.get("held_property_site_name")),
    }


def held_property_snapshot(sim, offender_eid):
    state = _state(sim)
    record = _offender_record(state, offender_eid, create=False)
    if not isinstance(record, dict):
        return {
            "property_id": "",
            "property_name": "",
            "entry_count": 0,
            "item_count": 0,
            "entries": (),
            "updated_tick": -10_000,
        }
    entries = tuple(
        dict(entry)
        for entry in tuple(record.get("held_property_entries", ()) or ())
        if isinstance(entry, dict)
    )
    return {
        "property_id": _text(record.get("held_property_site_id")),
        "property_name": _text(record.get("held_property_site_name")),
        "entry_count": len(entries),
        "item_count": int(sum(max(1, _safe_int(entry.get("quantity"), default=1)) for entry in entries)),
        "entries": entries,
        "updated_tick": int(record.get("held_property_updated_tick", -10_000)),
    }


def replace_held_property(sim, offender_eid, *, property_id=None, property_name=None, entries=()):
    state = _state(sim)
    record = _offender_record(state, offender_eid, create=True)
    if not isinstance(record, dict):
        return None
    record["held_property_site_id"] = _text(property_id or record.get("held_property_site_id"))
    record["held_property_site_name"] = _text(property_name or record.get("held_property_site_name"))
    normalized = []
    for entry in tuple(entries or ()):
        if not isinstance(entry, dict):
            continue
        item_id = _text(entry.get("item_id")).lower()
        instance_id = _text(entry.get("instance_id"))
        quantity = max(1, _safe_int(entry.get("quantity"), default=1))
        if not item_id or not instance_id:
            continue
        metadata = entry.get("metadata")
        normalized.append({
            "instance_id": instance_id,
            "item_id": item_id,
            "quantity": quantity,
            "owner_eid": entry.get("owner_eid"),
            "owner_tag": _text(entry.get("owner_tag")),
            "metadata": dict(metadata) if isinstance(metadata, dict) else {},
        })
    record["held_property_entries"] = normalized
    record["held_property_updated_tick"] = _safe_int(getattr(sim, "tick", 0), default=0)
    if not normalized:
        record["held_property_site_id"] = ""
        record["held_property_site_name"] = ""
    return held_property_snapshot(sim, offender_eid)


def store_held_property(sim, offender_eid, *, property_id=None, property_name=None, entries=()):
    current = held_property_snapshot(sim, offender_eid)
    combined = list(current.get("entries", ()) or ())
    combined.extend(
        dict(entry)
        for entry in tuple(entries or ())
        if isinstance(entry, dict)
    )
    return replace_held_property(
        sim,
        offender_eid,
        property_id=property_id,
        property_name=property_name,
        entries=combined,
    )


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
    if incident_type == "resisting_custody":
        return min(22, 10 + (severity // 12) + witnessed_bonus)
    if incident_type == "unarmed_assault":
        return min(18, 8 + (severity // 14) + witnessed_bonus)
    if incident_type == "melee_assault":
        return min(22, 12 + (severity // 12) + witnessed_bonus)
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
    try:
        incident_x = int(x)
    except (TypeError, ValueError):
        incident_x = None
    try:
        incident_y = int(y)
    except (TypeError, ValueError):
        incident_y = None
    incident["x"] = incident_x
    incident["y"] = incident_y
    if incident_x is not None and incident_y is not None:
        try:
            incident["chunk"] = tuple(sim.chunk_coords(int(incident_x), int(incident_y)))
        except Exception:
            incident["chunk"] = None
    else:
        incident["chunk"] = None
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


def booking_anchor_for(sim, offender_eid, *, fallback_x=None, fallback_y=None):
    state = _state(sim)
    record = _offender_record(state, offender_eid, create=False)
    best_incident = None
    best_rank = None
    if isinstance(record, dict):
        for incident in tuple(record.get("incidents", ()) or ()):
            if not isinstance(incident, dict):
                continue
            try:
                incident_x = int(incident.get("x"))
                incident_y = int(incident.get("y"))
            except (TypeError, ValueError):
                continue
            rank = (
                max(0, _safe_int(incident.get("weight"), default=0)),
                max(0, _safe_int(incident.get("severity"), default=0)),
                _safe_int(incident.get("tick"), default=-10_000),
            )
            if best_rank is None or rank > best_rank:
                best_incident = dict(incident)
                best_incident["x"] = int(incident_x)
                best_incident["y"] = int(incident_y)
                best_rank = rank

    if isinstance(best_incident, dict):
        x = int(best_incident.get("x", 0))
        y = int(best_incident.get("y", 0))
        chunk = best_incident.get("chunk")
        if not (isinstance(chunk, (tuple, list)) and len(chunk) >= 2):
            try:
                chunk = tuple(sim.chunk_coords(x, y))
            except Exception:
                chunk = None
        return {
            "x": x,
            "y": y,
            "chunk": tuple(chunk) if isinstance(chunk, (tuple, list)) and len(chunk) >= 2 else None,
            "incident": best_incident,
            "fallback": False,
            "jurisdiction_key": _text(best_incident.get("jurisdiction_key")).lower(),
            "jurisdiction_name": _text(best_incident.get("jurisdiction_name")),
            "settlement_name": _text(best_incident.get("settlement_name")),
            "region_name": _text(best_incident.get("region_name")),
        }

    try:
        x = int(fallback_x)
        y = int(fallback_y)
    except (TypeError, ValueError):
        return None

    jurisdiction = jurisdiction_for_position(sim, x=x, y=y)
    return {
        "x": x,
        "y": y,
        "chunk": tuple(jurisdiction.get("chunk", ())) if isinstance(jurisdiction.get("chunk"), (tuple, list)) else None,
        "incident": None,
        "fallback": True,
        "jurisdiction_key": _text(jurisdiction.get("key")).lower(),
        "jurisdiction_name": _text(jurisdiction.get("name")),
        "settlement_name": _text(jurisdiction.get("settlement_name")),
        "region_name": _text(jurisdiction.get("region_name")),
    }


def justice_summary_rows(sim, offender_eid):
    snapshot = justice_snapshot(sim, offender_eid)
    status = str(snapshot.get("wanted_tier", "clear")).strip().lower() or "clear"
    score = max(0, _safe_int(snapshot.get("active_score"), default=0))
    incident_count = max(0, _safe_int(snapshot.get("incident_count"), default=0))
    jurisdiction = _text(snapshot.get("last_jurisdiction_name")) or "Local Justice Office"
    latest = snapshot.get("latest_incident") if isinstance(snapshot.get("latest_incident"), dict) else {}
    latest_label = _text(latest.get("label")) or "incident"
    held = held_property_snapshot(sim, offender_eid)
    held_count = max(0, _safe_int(held.get("item_count"), default=0))
    held_site = _text(held.get("property_name")) or _text(snapshot.get("held_property_site_name")) or jurisdiction
    finance = sim.ecs.get(FinancialProfile).get(offender_eid) if sim is not None else None
    justice_debt = int(finance.debt_amount("justice_fines")) if finance and hasattr(finance, "debt_amount") else 0

    lines = []
    if status == "held":
        lines.extend([
            f"Held in custody by {jurisdiction}.",
            f"Recorded incidents {incident_count}; latest {latest_label}.",
        ])
    elif score <= 0 and incident_count <= 0:
        lines.append("Legal clear. No active justice attention.")
    else:
        if status == "clear":
            lead = f"Legal attention is cooling in {jurisdiction}."
        else:
            lead = f"Status {wanted_label(status)} in {jurisdiction}."
        lines.extend([
            lead,
            f"Legal pressure {score} | recorded incidents {incident_count} | latest {latest_label}.",
        ])

    if justice_debt > 0:
        lines.append(f"Justice debt {justice_debt}c is on the books.")
    if held_count > 0:
        if justice_debt > 0:
            lines.append(f"Held property at {held_site}: {held_count} item(s); release waits on justice debt.")
        else:
            lines.append(f"Held property at {held_site}: {held_count} item(s) ready for release.")
    return lines
