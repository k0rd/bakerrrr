"""Anchored quiet-maintenance coordination.

This module sits above the small structural repair helper. It lets concrete
business/ritual scenes resolve one bounded maintenance action without becoming
an always-on property upkeep simulation.
"""

from __future__ import annotations

from collections.abc import Mapping

from engine.events import Event
from game.cultivation_runtime import (
    FAILED_STAGES,
    advance_cultivation_records,
    ensure_cultivation_state,
    sync_cultivation_flora_patch,
)
from game.flora_runtime import EXHAUSTED_FLORA_STAGES
from game.property_runtime import property_display_position, property_focus_position, property_metadata
from game.system_support.building_repair_runtime import (
    property_damage_records,
    quiet_maintenance_cleanup as _minor_structural_cleanup,
)


SERIOUS_DAMAGE_CAUSES = frozenset(
    (
        "attack",
        "breach",
        "explosion",
        "fire",
        "forced_entry",
        "ramming",
        "sabotage",
        "shooting",
        "vehicle_collision",
    )
)

MAINTENANCE_ACTION_ORDER = {
    "maintenance_loop": ("minor_repair", "plant_tending", "frontage_reset"),
    "repair_lookover": ("minor_repair", "frontage_reset"),
    "plant_tending": ("plant_tending",),
    "counter_wipe": ("counter_reset",),
    "shelf_straightening": ("shelf_reset",),
}

RESET_CUES = {
    "frontage_reset": "the public edge has been put back in order",
    "counter_reset": "the counter has been wiped down and reset",
    "shelf_reset": "the visible shelf line has been squared up",
}


def _text(value):
    return str(value or "").strip()


def _slug(value):
    return _text(value).lower()


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _property_id(prop):
    return _text((prop or {}).get("id"))


def _property_name(prop):
    return _text((prop or {}).get("name")) or _property_id(prop) or "the place"


def _maintenance_state(prop, *, create=False):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    if not isinstance(metadata, dict):
        if not create:
            return {}
        metadata = {}
        prop["metadata"] = metadata
    state = metadata.get("quiet_maintenance")
    if not isinstance(state, dict):
        if not create:
            return {}
        state = {}
        metadata["quiet_maintenance"] = state
    return state


def _prop_anchor(prop):
    anchor = property_focus_position(prop) or property_display_position(prop)
    if not isinstance(anchor, (tuple, list)) or len(anchor) < 3:
        return (0, 0, 0)
    try:
        return (int(anchor[0]), int(anchor[1]), int(anchor[2]))
    except (TypeError, ValueError):
        return (0, 0, 0)


def _record_repair_kind(record):
    kind = _slug((record or {}).get("repair_kind"))
    aperture = _slug((record or {}).get("aperture_kind"))
    if kind in {"door", "window", "wall"}:
        return kind
    if "window" in aperture:
        return "window"
    if "door" in aperture:
        return "door"
    return kind or "wall"


def _minor_repair_record_allowed(record):
    if not isinstance(record, Mapping):
        return False
    repair_kind = _record_repair_kind(record)
    if repair_kind not in {"door", "window"}:
        return False
    if _safe_int(record.get("offender_eid"), 0):
        return False
    if _slug(record.get("cause")) in SERIOUS_DAMAGE_CAUSES:
        return False
    return True


def _nearby_cultivation_records(sim, prop, *, radius=7):
    if sim is None or not isinstance(prop, dict):
        return ()
    records = getattr(sim, "cultivation_records", None)
    if not isinstance(records, dict):
        return ()
    ax, ay, az = _prop_anchor(prop)
    rows = []
    for cid, record in records.items():
        if not isinstance(record, dict):
            continue
        if record.get("carried_by_eid") is not None:
            continue
        try:
            x = int(record.get("x"))
            y = int(record.get("y"))
            z = int(record.get("z", 0))
        except (TypeError, ValueError):
            continue
        if z != az or abs(x - ax) + abs(y - ay) > int(radius):
            continue
        rows.append((str(cid), record))
    rows.sort(key=lambda row: (
        abs(_safe_int(row[1].get("x"), ax) - ax) + abs(_safe_int(row[1].get("y"), ay) - ay),
        str(row[0]),
    ))
    return tuple(rows)


def _cultivation_needs_tending(record, now):
    stage = _slug((record or {}).get("stage"))
    if stage in FAILED_STAGES or stage in EXHAUSTED_FLORA_STAGES:
        return False
    if _safe_int((record or {}).get("harvest_remaining"), 0) <= 0:
        return False
    last = (record or {}).get("tended_tick")
    if last in (None, ""):
        return True
    return int(now) - _safe_int(last, -100_000) >= 24 * 600


def _visible_cultivation_counts(sim, prop):
    now = _safe_int(getattr(sim, "tick", 0), 0)
    counts = {"nearby": 0, "needs_tending": 0, "failed": 0, "exhausted": 0}
    for _cid, record in _nearby_cultivation_records(sim, prop):
        counts["nearby"] += 1
        stage = _slug(record.get("stage"))
        if stage in FAILED_STAGES:
            counts["failed"] += 1
        if stage in EXHAUSTED_FLORA_STAGES or _safe_int(record.get("harvest_remaining"), 0) <= 0:
            counts["exhausted"] += 1
        if _cultivation_needs_tending(record, now):
            counts["needs_tending"] += 1
    return counts


def quiet_maintenance_status(sim, prop):
    """Return a compact derived maintenance read for a concrete property."""

    state = _maintenance_state(prop, create=False)
    now = _safe_int(getattr(sim, "tick", 0), 0)
    last_tick = _safe_int(state.get("last_tick"), -100_000) if isinstance(state, dict) else -100_000
    recent = bool(last_tick >= 0 and now - last_tick <= 24 * 600)
    records = tuple(property_damage_records(sim, prop) or ()) if isinstance(prop, dict) else ()
    minor_damage = sum(1 for record in records if _minor_repair_record_allowed(record))
    cultivation_counts = _visible_cultivation_counts(sim, prop)
    visible_damage = sum(
        1
        for record in records
        if _slug((record or {}).get("cause")) != "inferred"
    )
    neglected = bool(
        visible_damage > 0
        or cultivation_counts.get("failed", 0) > 0
        or cultivation_counts.get("needs_tending", 0) >= 2
    )
    return {
        "property_id": _property_id(prop),
        "property_name": _property_name(prop),
        "last_tick": int(last_tick),
        "recent": recent,
        "last_kind": _slug(state.get("last_kind")) if isinstance(state, dict) else "",
        "last_label": _text(state.get("last_label")) if isinstance(state, dict) else "",
        "visible_cue": _text(state.get("visible_cue")) if isinstance(state, dict) else "",
        "resolved_kinds": tuple(state.get("resolved_kinds", ()) or ()) if isinstance(state, dict) else (),
        "minor_damage_count": int(minor_damage),
        "visible_damage_count": int(visible_damage),
        "cultivation_counts": dict(cultivation_counts),
        "neglected": neglected and not recent,
    }


def _result_label(kind):
    labels = {
        "minor_repair": "minor repair",
        "plant_tending": "plant tending",
        "frontage_reset": "frontage reset",
        "counter_reset": "counter reset",
        "shelf_reset": "shelf reset",
    }
    return labels.get(_slug(kind), _slug(kind).replace("_", " "))


def _record_property_maintenance(prop, result):
    state = _maintenance_state(prop, create=True)
    now = _safe_int(result.get("tick"), 0)
    kind = _slug(result.get("maintenance_kind"))
    resolved = [str(value).strip().lower() for value in tuple(state.get("resolved_kinds", ()) or ()) if str(value).strip()]
    if kind:
        resolved.append(kind)
    state["last_tick"] = int(now)
    state["last_kind"] = kind
    state["last_label"] = _text(result.get("maintenance_label")) or _result_label(kind)
    state["last_source_kind"] = _slug(result.get("source_kind"))
    state["visible_cue"] = _text(result.get("visible_cue"))
    state["resolved_kinds"] = tuple(resolved[-6:])
    state["last_result"] = {
        "kind": kind,
        "label": state["last_label"],
        "tick": int(now),
        "visible_cue": state["visible_cue"],
    }
    return state


def _result(sim, prop, kind, *, source_kind, visible_cue, summary="", extra=None):
    now = _safe_int(getattr(sim, "tick", 0), 0)
    result = {
        "ok": True,
        "reason": "resolved",
        "property_id": _property_id(prop),
        "property_name": _property_name(prop),
        "maintenance_kind": _slug(kind),
        "maintenance_label": _result_label(kind),
        "resolved_kinds": (_slug(kind),),
        "source_kind": _slug(source_kind) or "maintenance_loop",
        "visible_cue": _text(visible_cue),
        "summary": _text(summary),
        "tick": int(now),
        "restored_count": 0,
        "restored_kinds": (),
    }
    if isinstance(extra, dict):
        result.update(extra)
    _record_property_maintenance(prop, result)
    return result


def _try_minor_repair(sim, prop, source_kind):
    result = _minor_structural_cleanup(
        sim,
        prop,
        max_records=1,
        source_kind=source_kind,
        emit_event=False,
    )
    if not bool((result or {}).get("ok")):
        return None
    kinds = tuple(result.get("restored_kinds", ()) or ())
    if kinds == ("window",):
        cue = "a broken pane has been set right"
    elif kinds == ("door",):
        cue = "a bad door has been reset"
    else:
        cue = "a small repair has been settled"
    return _result(
        sim,
        prop,
        "minor_repair",
        source_kind=source_kind,
        visible_cue=cue,
        summary=f"{_property_name(prop)} gets one small repair handled.",
        extra={
            "reason": "restored",
            "restored_count": _safe_int(result.get("restored_count"), 0),
            "restored_kinds": tuple(kinds),
        },
    )


def _try_plant_tending(sim, prop, source_kind):
    advance_cultivation_records(sim)
    now = _safe_int(getattr(sim, "tick", 0), 0)
    records = ensure_cultivation_state(sim)
    for cid, record in _nearby_cultivation_records(sim, prop):
        if not _cultivation_needs_tending(record, now):
            continue
        record = records.get(cid)
        if not isinstance(record, dict):
            continue
        record["tended_tick"] = int(now)
        record["tend_count"] = _safe_int(record.get("tend_count"), 0) + 1
        record["maintenance_tended"] = True
        record["maintenance_quality_bonus"] = min(2, _safe_int(record.get("maintenance_quality_bonus"), 0) + 1)
        record["last_tending_source"] = _slug(source_kind) or "maintenance_loop"
        records[cid] = record
        sync_cultivation_flora_patch(sim, record)
        plant_name = _text(record.get("plant_name")) or _text(record.get("plant_id")) or "plant"
        return _result(
            sim,
            prop,
            "plant_tending",
            source_kind=source_kind,
            visible_cue=f"{plant_name} has been watered and checked",
            summary=f"Someone tends {plant_name} at {_property_name(prop)}.",
            extra={
                "tended_count": 1,
                "cultivation_ids": (str(cid),),
                "plant_names": (plant_name,),
            },
        )
    return None


def _try_reset(sim, prop, source_kind, kind):
    cue = RESET_CUES.get(kind, "the visible work edge has been reset")
    prop_name = _property_name(prop)
    summaries = {
        "counter_reset": f"Someone wipes down the counter at {prop_name}.",
        "shelf_reset": f"Someone squares up the visible shelves at {prop_name}.",
        "frontage_reset": f"Someone resets the public edge at {prop_name}.",
    }
    return _result(
        sim,
        prop,
        kind,
        source_kind=source_kind,
        visible_cue=cue,
        summary=summaries.get(kind, f"Someone resets the visible edge at {prop_name}."),
        extra={"reset_count": 1},
    )


def _action_order(source_kind, preferred_kind=""):
    preferred_kind = _slug(preferred_kind)
    if preferred_kind:
        return (preferred_kind,)
    source_kind = _slug(source_kind)
    if source_kind in MAINTENANCE_ACTION_ORDER:
        return MAINTENANCE_ACTION_ORDER[source_kind]
    return ("minor_repair", "plant_tending", "frontage_reset")


def quiet_maintenance_worker_careers(result, *, category=""):
    kind = _slug((result or {}).get("maintenance_kind"))
    category = _slug(category)
    if kind == "plant_tending":
        return ("gardener", "caretaker") if category not in {"medical"} else ("gardener", "remedy_mixer")
    if kind == "minor_repair":
        return ("maintenance_tech",)
    if kind == "counter_reset":
        if category in {"hospitality", "entertainment"}:
            return ("server", "dishwasher")
        if category == "medical":
            return ("sanitation_worker", "porter")
        return ("sanitation_worker", "porter")
    if kind == "shelf_reset":
        if category == "hospitality":
            return ("server", "cook")
        return ("stock_clerk", "porter")
    if kind == "frontage_reset":
        if category in {"hospitality", "entertainment"}:
            return ("porter", "server")
        if category == "medical":
            return ("porter", "sanitation_worker")
        return ("porter", "maintenance_tech")
    return ("maintenance_tech",)


def quiet_maintenance_actor_line(result):
    kind = _slug((result or {}).get("maintenance_kind"))
    cue = _text((result or {}).get("visible_cue"))
    lines = {
        "minor_repair": "Small fixes are how a place tells you it still has hands on it.",
        "plant_tending": "A tended plant changes the whole room, even when nobody admits it.",
        "frontage_reset": "You reset the frontage before the frontage starts talking for you.",
        "counter_reset": "A clean counter buys everyone one calmer minute.",
        "shelf_reset": "Straight shelves make the rest of the story easier to believe.",
    }
    return lines.get(kind) or cue


def quiet_maintenance_detail_line(result):
    kind = _slug((result or {}).get("maintenance_kind"))
    cue = _text((result or {}).get("visible_cue"))
    if kind == "plant_tending":
        plants = ", ".join(_text(name) for name in tuple((result or {}).get("plant_names", ()) or ()) if _text(name))
        return f"The plant care is practical and bounded; {plants or 'the greenery'} looks checked, not magically renewed."
    if kind == "minor_repair":
        return f"The repair is small and concrete: {cue or 'one weak bit got reset'}."
    if kind in {"frontage_reset", "counter_reset", "shelf_reset"}:
        return f"The reset is presentation care, not a change to stock, policy, or legal truth."
    return cue


def run_quiet_maintenance(sim, prop, *, source_kind="maintenance_loop", preferred_kind="", emit_event=True):
    """Resolve one quiet-maintenance action for an anchored scene."""

    if sim is None or not isinstance(prop, dict):
        return {"ok": False, "reason": "invalid_property", "resolved_kinds": ()}
    source = _slug(source_kind) or "maintenance_loop"
    result = None
    for action in _action_order(source, preferred_kind=preferred_kind):
        action = _slug(action)
        if action == "minor_repair":
            result = _try_minor_repair(sim, prop, source)
        elif action == "plant_tending":
            result = _try_plant_tending(sim, prop, source)
        elif action in {"frontage_reset", "counter_reset", "shelf_reset"}:
            result = _try_reset(sim, prop, source, action)
        else:
            result = None
        if result:
            break
    if not result:
        return {"ok": False, "reason": "nothing_to_maintain", "resolved_kinds": (), "source_kind": source}
    if emit_event:
        x, y, z = _prop_anchor(prop)
        sim.emit(Event(
            "quiet_maintenance_resolved",
            property_id=result["property_id"],
            property_name=result["property_name"],
            maintenance_kind=result["maintenance_kind"],
            maintenance_label=result["maintenance_label"],
            resolved_kinds=tuple(result.get("resolved_kinds", ()) or ()),
            restored_count=_safe_int(result.get("restored_count"), 0),
            restored_kinds=tuple(result.get("restored_kinds", ()) or ()),
            tended_count=_safe_int(result.get("tended_count"), 0),
            reset_count=_safe_int(result.get("reset_count"), 0),
            visible_cue=_text(result.get("visible_cue")),
            summary=_text(result.get("summary")),
            source_kind=source,
            x=x,
            y=y,
            z=z,
        ))
    return result


__all__ = [
    "quiet_maintenance_actor_line",
    "quiet_maintenance_detail_line",
    "quiet_maintenance_status",
    "quiet_maintenance_worker_careers",
    "run_quiet_maintenance",
]
