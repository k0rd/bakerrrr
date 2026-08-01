"""Durable, bounded organization wars with concrete local fronts.

Diplomacy answers how two organizations regard one another.  This module owns
the separate question of whether they are conducting an organized conflict.
Wars begin from attributed events, retain fronts and objectives, and can cool
into ceasefires.  A war never grants universal combat authority by itself.
"""

from __future__ import annotations

import random

from engine.events import Event
from engine.systems import System
from engine.underground import UNDERGROUND_ACCESS_SERVICE
from engine.visibility import has_line_of_sight
from game.components import AI, Position, SuppressionState, Vitality
from game.corporate_presence import (
    corporate_neighborhood_presence_rows,
    corporate_organization_for_property,
)
from game.organizations import (
    actor_org_memberships,
    organization_eid_for_key,
    organization_policy_snapshot,
    organization_profile,
    property_org_links,
    record_organization_relationship,
)
from game.movement_runtime import try_move_entity
from game.system_support.actor_attention_runtime import mark_actor_urgent, schedule_actor_due


ORGANIZATION_WAR_SCHEMA_VERSION = 4
ORGANIZATION_WAR_MAX_TENSIONS = 128
ORGANIZATION_WAR_MAX_WARS = 48
ORGANIZATION_WAR_MAX_FRONTS = 8
ORGANIZATION_WAR_MAX_HISTORY = 32
ORGANIZATION_WAR_MAX_EVIDENCE = 64
ORGANIZATION_WAR_MAX_ORDERS = 64
ORGANIZATION_WAR_MAX_ORDERS_PER_SIDE = 2
ORGANIZATION_WAR_MAX_FRONT_CONTRIBUTIONS = 24
ORGANIZATION_WAR_ORDER_REFRESH_INTERVAL = 30
ORGANIZATION_WAR_ORDER_MIN_DURATION = 240
ORGANIZATION_WAR_ORDER_MAX_DURATION = 420
ORGANIZATION_WAR_ORDER_REDEPLOY_DELAY = 180
ORGANIZATION_WAR_ORDER_RETREAT_HP_RATIO = 0.45
ORGANIZATION_WAR_ORDER_RETREAT_SUPPRESSION = 0.68
ORGANIZATION_WAR_SYNC_INTERVAL = 600
ORGANIZATION_WAR_TENSION_DECAY_DELAY = 3600
ORGANIZATION_WAR_COOLING_DELAY = 7200
ORGANIZATION_WAR_CEASEFIRE_HEAT = 34.0
ORGANIZATION_WAR_FRONT_DECISIVE_MARGIN = 24.0
ORGANIZATION_WAR_COMBAT_ROLES = frozenset({
    "bodyguard",
    "enforcer",
    "fighter",
    "guard",
    "security",
    "soldier",
})
ORGANIZATION_WAR_MOVEMENT_STATES = frozenset({
    "war_advancing",
    "war_holding",
    "war_mobilizing",
    "war_retreating",
})
ORGANIZATION_WAR_ACTIVE_ORDER_STATUSES = frozenset({
    "advancing",
    "engaged",
    "holding",
    "mobilizing",
    "retreating",
})
ORGANIZATION_WAR_TERMINAL_ORDER_STATUSES = frozenset({
    "cancelled",
    "complete",
})


def _text(value):
    return str(value or "").strip()


def _key(value):
    return _text(value).lower().replace(" ", "_")


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clamp(value, low, high):
    return max(float(low), min(float(high), float(value)))


def _pair_key(org_a_eid, org_b_eid):
    a = _safe_int(org_a_eid, 0)
    b = _safe_int(org_b_eid, 0)
    if a <= 0 or b <= 0 or a == b:
        return ""
    low, high = sorted((a, b))
    return f"{low}:{high}"


def _chunk_tuple(value):
    if not isinstance(value, (tuple, list)) or len(value) < 2:
        return None
    try:
        return (int(value[0]), int(value[1]))
    except (TypeError, ValueError):
        return None


def _profile_tags(profile):
    return {_key(tag) for tag in tuple(getattr(profile, "tags", ()) or ()) if _key(tag)} if profile else set()


def _organization_family(sim, organization_eid):
    policy = organization_policy_snapshot(sim, organization_eid=organization_eid) or {}
    return _key(policy.get("family"))


def _organization_root(sim, organization_eid):
    organization_eid = _safe_int(organization_eid, 0)
    profile = organization_profile(sim, organization_eid)
    if organization_eid <= 0 or profile is None:
        return None
    # Generated underground communities are the actual local political actors.
    # Their shared parent is a culture family, not one world-spanning war side.
    tags = _profile_tags(profile)
    profile_key = _text(getattr(profile, "key", ""))
    if "underground" in tags and ("community" in tags or profile_key.startswith("community:underground:")):
        return organization_eid
    policy = organization_policy_snapshot(sim, organization_eid=organization_eid) or {}
    root = _safe_int(policy.get("root_organization_eid"), organization_eid)
    return root if organization_profile(sim, root) is not None else organization_eid


def _is_corporate_organization(sim, organization_eid):
    profile = organization_profile(sim, organization_eid)
    if profile is None:
        return False
    family = _organization_family(sim, organization_eid)
    kind = _key(getattr(profile, "kind", ""))
    tags = _profile_tags(profile)
    return family == "corporate" or kind in {"corporate", "corporation"} or bool(tags & {"corporate", "corpsec"})


def _is_underground_community(sim, organization_eid):
    profile = organization_profile(sim, organization_eid)
    if profile is None:
        return False
    tags = _profile_tags(profile)
    key = _text(getattr(profile, "key", ""))
    return "underground" in tags and ("community" in tags or key.startswith("community:underground:"))


def _org_ref(sim, organization_eid):
    profile = organization_profile(sim, organization_eid)
    if profile is None:
        return {}
    return {
        "organization_eid": int(organization_eid),
        "organization_key": _text(getattr(profile, "key", "")),
        "organization_name": _text(getattr(profile, "name", "")) or f"Organization {organization_eid}",
        "organization_kind": _key(getattr(profile, "kind", "")) or "other",
        "family": _organization_family(sim, organization_eid),
    }


def _state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    state = traits.get("organization_wars")
    if not isinstance(state, dict):
        state = {}
        traits["organization_wars"] = state
    state["schema_version"] = ORGANIZATION_WAR_SCHEMA_VERSION
    for bucket in ("tensions", "wars", "active_war_by_pair", "orders"):
        if not isinstance(state.get(bucket), dict):
            state[bucket] = {}
    state["next_war_id"] = max(1, _safe_int(state.get("next_war_id"), 1))
    state["next_order_id"] = max(1, _safe_int(state.get("next_order_id"), 1))
    _trim_state(state)
    return state


def _trim_state(state):
    """Bound dormant ledger rows without ever discarding an active war."""

    wars = state.get("wars", {})
    active_by_pair = state.get("active_war_by_pair", {})
    for pair_key, war_id in tuple(active_by_pair.items()):
        if not isinstance(wars.get(str(_safe_int(war_id, 0))), dict):
            active_by_pair.pop(pair_key, None)

    excess_wars = max(0, len(wars) - ORGANIZATION_WAR_MAX_WARS)
    if excess_wars:
        dormant = sorted(
            (
                raw for raw in wars.values()
                if isinstance(raw, dict) and _key(raw.get("status")) != "active"
            ),
            key=lambda raw: (
                _safe_int(raw.get("last_event_tick"), 0),
                _safe_int(raw.get("war_id"), 0),
            ),
        )
        for raw in dormant[:excess_wars]:
            war_id = _safe_int(raw.get("war_id"), 0)
            pair_key = _text(raw.get("pair_key"))
            wars.pop(str(war_id), None)
            if _safe_int(active_by_pair.get(pair_key), 0) == war_id:
                active_by_pair.pop(pair_key, None)
            tension = state.get("tensions", {}).get(pair_key)
            if isinstance(tension, dict) and _safe_int(tension.get("active_war_id"), 0) == war_id:
                tension["active_war_id"] = None
                tension["status"] = "hostile"

    tensions = state.get("tensions", {})
    protected_pairs = {
        _text(raw.get("pair_key"))
        for raw in wars.values()
        if isinstance(raw, dict) and _text(raw.get("pair_key"))
    }
    excess_tensions = max(0, len(tensions) - ORGANIZATION_WAR_MAX_TENSIONS)
    if excess_tensions:
        removable = sorted(
            (
                (pair_key, raw) for pair_key, raw in tensions.items()
                if pair_key not in protected_pairs and isinstance(raw, dict)
            ),
            key=lambda item: (
                _safe_int(item[1].get("last_event_tick"), 0),
                item[0],
            ),
        )
        for pair_key, _raw in removable[:excess_tensions]:
            tensions.pop(pair_key, None)

    orders = state.get("orders", {})
    excess_orders = max(0, len(orders) - ORGANIZATION_WAR_MAX_ORDERS)
    if excess_orders:
        terminal = sorted(
            (
                (order_id, raw) for order_id, raw in orders.items()
                if isinstance(raw, dict)
                and _key(raw.get("status")) in ORGANIZATION_WAR_TERMINAL_ORDER_STATUSES
            ),
            key=lambda item: (
                _safe_int(item[1].get("completed_tick"), 0),
                _safe_int(item[1].get("issued_tick"), 0),
                item[0],
            ),
        )
        for order_id, _raw in terminal[:excess_orders]:
            orders.pop(order_id, None)

    for war in tuple(wars.values()):
        if not isinstance(war, dict):
            continue
        fronts = war.get("fronts") if isinstance(war.get("fronts"), dict) else {}
        for front in tuple(fronts.values()):
            if not isinstance(front, dict):
                continue
            contributions = [
                dict(row)
                for row in tuple(front.get("contributions", ()) or ())
                if isinstance(row, dict)
            ]
            if contributions:
                front["contributions"] = contributions[-ORGANIZATION_WAR_MAX_FRONT_CONTRIBUTIONS:]


def ensure_organization_war_state(sim):
    """Return the save-compatible organization war ledger."""

    return _state(sim)


def _property_chunk(sim, prop):
    if not isinstance(prop, dict):
        return None
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    chunk = _chunk_tuple(metadata.get("chunk"))
    if chunk is not None:
        return chunk
    try:
        return tuple(sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0))))
    except (AttributeError, TypeError, ValueError):
        return None


def _anchor_from_property(sim, prop):
    if not isinstance(prop, dict):
        return {}
    return {
        "property_id": _text(prop.get("id")),
        "property_name": _text(prop.get("name")) or _text(prop.get("id")) or "local site",
        "chunk": _property_chunk(sim, prop),
        "x": _safe_int(prop.get("x"), 0),
        "y": _safe_int(prop.get("y"), 0),
        "z": _safe_int(prop.get("z"), 0),
    }


def _normalize_anchor(sim, anchor=None, *, property_id=None, chunk=None, x=None, y=None, z=None):
    result = dict(anchor or {}) if isinstance(anchor, dict) else {}
    clean_property_id = _text(property_id) or _text(result.get("property_id"))
    prop = getattr(sim, "properties", {}).get(clean_property_id) if clean_property_id else None
    if isinstance(prop, dict):
        result = {**_anchor_from_property(sim, prop), **result}
    clean_chunk = _chunk_tuple(chunk) or _chunk_tuple(result.get("chunk"))
    resolved_x = result.get("x") if x is None else x
    resolved_y = result.get("y") if y is None else y
    resolved_z = result.get("z") if z is None else z
    if clean_chunk is None and resolved_x is not None and resolved_y is not None:
        try:
            clean_chunk = tuple(sim.chunk_coords(int(resolved_x), int(resolved_y)))
        except (AttributeError, TypeError, ValueError):
            clean_chunk = None
    result.update({
        "property_id": clean_property_id,
        "property_name": _text(result.get("property_name")) or _text((prop or {}).get("name")) or "local site",
        "chunk": clean_chunk,
        "x": _safe_int(resolved_x, 0),
        "y": _safe_int(resolved_y, 0),
        "z": _safe_int(resolved_z, 0),
    })
    return result


def _anchor_key(anchor):
    if not isinstance(anchor, dict):
        return ""
    if _text(anchor.get("property_id")):
        return f"property:{_text(anchor.get('property_id'))}"
    chunk = _chunk_tuple(anchor.get("chunk"))
    if chunk is not None:
        return f"chunk:{chunk[0]}:{chunk[1]}:z:{_safe_int(anchor.get('z'), 0)}"
    return ""


def _merge_anchor(rows, anchor, *, limit=8):
    rows = [dict(row) for row in tuple(rows or ()) if isinstance(row, dict)]
    key = _anchor_key(anchor)
    if not key:
        return rows[-limit:]
    replacement = {**dict(anchor), "anchor_key": key}
    for index, row in enumerate(rows):
        if _text(row.get("anchor_key")) == key or _anchor_key(row) == key:
            rows[index] = replacement
            break
    else:
        rows.append(replacement)
    return rows[-limit:]


def _war_threshold(sim, pair_key):
    rng = random.Random(f"{getattr(sim, 'seed', 0)}:organization-war-threshold:v1:{pair_key}")
    return float(rng.randint(92, 108))


def _war_id_for_pair(state, pair_key):
    active = _safe_int(state.get("active_war_by_pair", {}).get(pair_key), 0)
    if active > 0 and isinstance(state.get("wars", {}).get(str(active)), dict):
        return active
    return None


def _front_kind(cause):
    cause = _key(cause)
    if cause in {"attributed_blackwash", "repeated_dumping", "remediation_bed_destroyed", "toxic_discharge"}:
        return "remediation_line"
    if cause in {"access_seizure", "corporate_occupation", "infrastructure_control", "route_control"}:
        return "route_control"
    if cause in {"member_killed", "organized_raid", "reprisal"}:
        return "reprisal_line"
    if cause in {"data_seizure", "signal_sabotage"}:
        return "signal_front"
    return "pressure_line"


def _front_objectives(sim, participant_org_eids, front_kind):
    objectives = {}
    for organization_eid in participant_org_eids:
        if _is_underground_community(sim, organization_eid):
            objective = {
                "remediation_line": "keep the filter line alive and trace the source",
                "route_control": "keep the route open to residents",
                "reprisal_line": "protect residents and stop another removal",
                "signal_front": "keep local data and relays out of corporate hands",
            }.get(front_kind, "hold the local line and keep residents safe")
        elif _is_corporate_organization(sim, organization_eid):
            objective = {
                "remediation_line": "control the discharge record and restore the service route",
                "route_control": "secure the route under corporate access rules",
                "reprisal_line": "reassert enforcement control and isolate organizers",
                "signal_front": "recover the data and lock the relay network",
            }.get(front_kind, "restore corporate control of the local pressure point")
        else:
            objective = "hold the organization's local objective"
        objectives[str(int(organization_eid))] = objective
    return objectives


def _front_visible_cue(front_kind):
    return {
        "remediation_line": "fresh filter-bed markers face new corporate seals across the contaminated line",
        "route_control": "resident route marks and corporate access notices have been laid over one another",
        "reprisal_line": "watch positions and memorial marks share the same narrow approach",
        "signal_front": "patched local relays sit opposite newly tagged corporate hardware",
    }.get(front_kind, "two organizations have left fresh signs of a contested line")


def _new_front(sim, war_id, participant_org_eids, cause, anchor, *, created_tick=None):
    now = _safe_int(getattr(sim, "tick", 0) if created_tick is None else created_tick, 0)
    front_kind = _front_kind(cause)
    front_key = _anchor_key(anchor) or f"war:{war_id}:unanchored"
    front_id = f"war:{war_id}:front:{front_key}"
    return {
        "front_id": front_id,
        "front_kind": front_kind,
        "status": "contested",
        "anchor": dict(anchor),
        "objectives": _front_objectives(sim, participant_org_eids, front_kind),
        "pressure_by_org": {str(int(eid)): 0.0 for eid in participant_org_eids},
        "outcome": None,
        "outcome_history": [],
        "visible": True,
        "visible_cue": _front_visible_cue(front_kind),
        "created_tick": now,
        "last_event_tick": now,
    }


def organization_tension_snapshot(sim, org_a_eid, org_b_eid):
    pair_key = _pair_key(org_a_eid, org_b_eid)
    raw = _state(sim).get("tensions", {}).get(pair_key)
    if not pair_key or not isinstance(raw, dict):
        return None
    a_ref = _org_ref(sim, raw.get("org_a_eid"))
    b_ref = _org_ref(sim, raw.get("org_b_eid"))
    if not a_ref or not b_ref:
        return None
    return {
        **dict(raw),
        "reason_tags": tuple(raw.get("reason_tags", ()) or ()),
        "anchors": tuple(dict(row) for row in tuple(raw.get("anchors", ()) or ()) if isinstance(row, dict)),
        "history": tuple(dict(row) for row in tuple(raw.get("history", ()) or ()) if isinstance(row, dict)),
        "org_a": a_ref,
        "org_b": b_ref,
    }


def organization_tension_rows(sim, *, organization_eid=None, status=None):
    rows = []
    wanted = _safe_int(organization_eid, 0) or None
    wanted_status = _key(status)
    for raw in tuple(_state(sim).get("tensions", {}).values()):
        if not isinstance(raw, dict):
            continue
        if wanted and wanted not in {_safe_int(raw.get("org_a_eid"), 0), _safe_int(raw.get("org_b_eid"), 0)}:
            continue
        row = organization_tension_snapshot(sim, raw.get("org_a_eid"), raw.get("org_b_eid"))
        if row is None or (wanted_status and _key(row.get("status")) != wanted_status):
            continue
        rows.append(row)
    rows.sort(key=lambda row: (-_safe_float(row.get("escalation"), 0.0), _text(row.get("pair_key"))))
    return tuple(rows)


def _hostility_cue(sim, org_a_eid, org_b_eid, reason):
    if _key(reason) in {"attributed_blackwash", "toxic_discharge", "repeated_dumping"}:
        return "resident filter marks and corporate service tags share the wall without agreement"
    if _key(reason) in {"access_seizure", "corporate_occupation", "infrastructure_control"}:
        return "local route marks have been crossed by fresh corporate access notices"
    return "the two organizations are marking the same local line in openly incompatible ways"


def record_organization_tension(
    sim,
    *,
    org_a_eid,
    org_b_eid,
    reason,
    severity,
    source_event="",
    evidence_key="",
    anchor=None,
    property_id=None,
    chunk=None,
    x=None,
    y=None,
    z=None,
    instigator_org_eid=None,
    baseline=False,
    escalation_trigger=True,
    force_war=False,
):
    """Record one attributed pressure event between organizations.

    ``baseline`` records structural hostility without declaring organized war.
    A war begins only when an attributed trigger crosses the pair's threshold,
    or when an authored caller explicitly requests ``force_war``.
    """

    org_a_eid = _organization_root(sim, org_a_eid)
    org_b_eid = _organization_root(sim, org_b_eid)
    pair_key = _pair_key(org_a_eid, org_b_eid)
    if not pair_key:
        return None
    state = _state(sim)
    active_war_id = _war_id_for_pair(state, pair_key)
    clean_reason = _key(reason) or "organization_pressure"
    clean_source = _key(source_event) or clean_reason
    clean_anchor = _normalize_anchor(
        sim,
        anchor,
        property_id=property_id,
        chunk=chunk,
        x=x,
        y=y,
        z=z,
    )
    if active_war_id is not None:
        return record_organization_war_event(
            sim,
            active_war_id,
            event_kind=clean_reason,
            severity=severity,
            source_event=clean_source,
            evidence_key=evidence_key,
            anchor=clean_anchor,
            instigator_org_eid=instigator_org_eid,
        )

    now = _safe_int(getattr(sim, "tick", 0), 0)
    evidence_key = _text(evidence_key) or f"{clean_source}:{_anchor_key(clean_anchor)}:{now}"
    raw = state["tensions"].get(pair_key)
    if not isinstance(raw, dict):
        low, high = sorted((int(org_a_eid), int(org_b_eid)))
        raw = {
            "pair_key": pair_key,
            "org_a_eid": low,
            "org_b_eid": high,
            "status": "hostile",
            "baseline": 0.0,
            "escalation": 0.0,
            "threshold": _war_threshold(sim, pair_key),
            "reason_tags": [],
            "anchors": [],
            "history": [],
            "evidence_keys": [],
            "created_tick": now,
            "last_event_tick": now,
            "active_war_id": None,
        }
    evidence = list(raw.get("evidence_keys", ()) or ())
    if evidence_key in evidence:
        return organization_tension_snapshot(sim, org_a_eid, org_b_eid)

    amount = max(0.0, _safe_float(severity, 0.0))
    current_baseline = _safe_float(raw.get("baseline"), 0.0)
    current_escalation = _safe_float(raw.get("escalation"), current_baseline)
    if baseline:
        current_baseline = min(78.0, current_baseline + amount)
        current_escalation = max(current_escalation, current_baseline)
    else:
        current_escalation = min(200.0, current_escalation + amount)
    threshold = _safe_float(raw.get("threshold"), _war_threshold(sim, pair_key))
    if force_war:
        current_escalation = max(current_escalation, threshold)
    status = "mobilizing" if current_escalation >= threshold * 0.7 else "hostile"
    reasons = sorted(set(tuple(raw.get("reason_tags", ()) or ())) | {clean_reason})
    history = [dict(row) for row in tuple(raw.get("history", ()) or ()) if isinstance(row, dict)]
    history.append({
        "tick": now,
        "reason": clean_reason,
        "source_event": clean_source,
        "severity": round(amount, 3),
        "instigator_org_eid": _safe_int(instigator_org_eid, 0) or None,
        "anchor": dict(clean_anchor),
        "baseline": bool(baseline),
    })
    evidence.append(evidence_key)
    raw.update({
        "status": status,
        "baseline": round(current_baseline, 3),
        "escalation": round(current_escalation, 3),
        "threshold": round(threshold, 3),
        "reason_tags": reasons,
        "anchors": _merge_anchor(raw.get("anchors"), clean_anchor),
        "history": history[-ORGANIZATION_WAR_MAX_HISTORY:],
        "evidence_keys": evidence[-ORGANIZATION_WAR_MAX_EVIDENCE:],
        "last_event_tick": now,
    })
    state["tensions"][pair_key] = raw

    record_organization_relationship(
        sim,
        org_a_eid=org_a_eid,
        org_b_eid=org_b_eid,
        stance="hostile",
        confidence=min(0.98, 0.55 + (current_escalation / 250.0)),
        reason_tags=("organization_war_precursor", clean_reason),
        source_event=clean_source,
        anchor_property_id=clean_anchor.get("property_id") or None,
        visible=bool(clean_anchor.get("property_id")),
        visible_cue=_hostility_cue(sim, org_a_eid, org_b_eid, clean_reason),
        cooldown_ticks=0,
    )

    should_start = bool(force_war or (escalation_trigger and not baseline and current_escalation >= threshold))
    if should_start:
        return start_organization_war(
            sim,
            org_a_eid=org_a_eid,
            org_b_eid=org_b_eid,
            cause=clean_reason,
            source_event=clean_source,
            anchor=clean_anchor,
            instigator_org_eid=instigator_org_eid,
            opening_heat=max(72.0, min(140.0, current_escalation)),
        )
    return organization_tension_snapshot(sim, org_a_eid, org_b_eid)


def start_organization_war(
    sim,
    *,
    org_a_eid,
    org_b_eid,
    cause,
    source_event="",
    anchor=None,
    property_id=None,
    chunk=None,
    x=None,
    y=None,
    z=None,
    instigator_org_eid=None,
    opening_heat=100.0,
):
    """Begin or reactivate one concrete organization war."""

    org_a_eid = _organization_root(sim, org_a_eid)
    org_b_eid = _organization_root(sim, org_b_eid)
    pair_key = _pair_key(org_a_eid, org_b_eid)
    clean_anchor = _normalize_anchor(sim, anchor, property_id=property_id, chunk=chunk, x=x, y=y, z=z)
    if not pair_key or not _anchor_key(clean_anchor):
        return None
    state = _state(sim)
    existing_id = _war_id_for_pair(state, pair_key)
    if existing_id is not None:
        return record_organization_war_event(
            sim,
            existing_id,
            event_kind=_key(cause) or "organized_conflict",
            severity=max(0.0, _safe_float(opening_heat, 100.0)),
            source_event=_key(source_event) or _key(cause) or "war_started",
            anchor=clean_anchor,
            instigator_org_eid=instigator_org_eid,
        )

    now = _safe_int(getattr(sim, "tick", 0), 0)
    war_id = int(state["next_war_id"])
    state["next_war_id"] = war_id + 1
    participants = tuple(sorted((int(org_a_eid), int(org_b_eid))))
    front = _new_front(sim, war_id, participants, cause, clean_anchor, created_tick=now)
    history = [{
        "tick": now,
        "event_kind": "war_started",
        "source_event": _key(source_event) or _key(cause) or "war_started",
        "severity": round(_safe_float(opening_heat, 100.0), 3),
        "instigator_org_eid": _safe_int(instigator_org_eid, 0) or None,
        "front_id": front["front_id"],
    }]
    war = {
        "war_id": war_id,
        "pair_key": pair_key,
        "participant_org_eids": list(participants),
        "status": "active",
        "cause": _key(cause) or "organized_conflict",
        "cause_tags": [_key(cause) or "organized_conflict"],
        "started_tick": now,
        "last_event_tick": now,
        "ceasefire_tick": None,
        "ceasefire_reason": None,
        "heat": round(_clamp(opening_heat, 0.0, 200.0), 3),
        "momentum_by_org": {str(eid): 0.0 for eid in participants},
        "fronts": {front["front_id"]: front},
        "history": history,
    }
    state["wars"][str(war_id)] = war
    state["active_war_by_pair"][pair_key] = war_id
    tension = state["tensions"].get(pair_key)
    if isinstance(tension, dict):
        tension["status"] = "war"
        tension["active_war_id"] = war_id
        tension["last_event_tick"] = now

    refs = [_org_ref(sim, eid) for eid in participants]
    sim.emit(Event(
        "organization_war_started",
        war_id=war_id,
        pair_key=pair_key,
        participant_org_eids=participants,
        participant_names=tuple(ref.get("organization_name") for ref in refs),
        cause=war["cause"],
        front_id=front["front_id"],
        front_kind=front["front_kind"],
        property_id=clean_anchor.get("property_id"),
        property_name=clean_anchor.get("property_name"),
        chunk=clean_anchor.get("chunk"),
        x=clean_anchor.get("x"),
        y=clean_anchor.get("y"),
        z=clean_anchor.get("z"),
    ))
    return organization_war_snapshot(sim, war_id)


def organization_war_snapshot(sim, war_id):
    raw = _state(sim).get("wars", {}).get(str(_safe_int(war_id, 0)))
    if not isinstance(raw, dict):
        return None
    participants = tuple(
        eid for eid in (_safe_int(value, 0) for value in tuple(raw.get("participant_org_eids", ()) or ()))
        if eid > 0 and organization_profile(sim, eid) is not None
    )
    if len(participants) < 2:
        return None
    fronts = tuple(
        dict(front)
        for front in tuple((raw.get("fronts") or {}).values())
        if isinstance(front, dict)
    )
    fronts = tuple(sorted(fronts, key=lambda row: (_text(row.get("status")), _text(row.get("front_id")))))
    return {
        **dict(raw),
        "participant_org_eids": participants,
        "participants": tuple(_org_ref(sim, eid) for eid in participants),
        "cause_tags": tuple(raw.get("cause_tags", ()) or ()),
        "fronts": fronts,
        "history": tuple(dict(row) for row in tuple(raw.get("history", ()) or ()) if isinstance(row, dict)),
    }


def organization_war_rows(sim, *, organization_eid=None, status=None, active_only=False):
    wanted_eid = _safe_int(organization_eid, 0) or None
    wanted_status = _key(status)
    rows = []
    for raw in tuple(_state(sim).get("wars", {}).values()):
        if not isinstance(raw, dict):
            continue
        row = organization_war_snapshot(sim, raw.get("war_id"))
        if row is None:
            continue
        if wanted_eid and wanted_eid not in row.get("participant_org_eids", ()):
            continue
        if wanted_status and _key(row.get("status")) != wanted_status:
            continue
        if active_only and _key(row.get("status")) != "active":
            continue
        rows.append(row)
    rows.sort(key=lambda row: (0 if _key(row.get("status")) == "active" else 1, -_safe_float(row.get("heat"), 0.0), _safe_int(row.get("war_id"), 0)))
    return tuple(rows)


def organization_war_for_pair(sim, org_a_eid, org_b_eid, *, active_only=False):
    pair_key = _pair_key(_organization_root(sim, org_a_eid), _organization_root(sim, org_b_eid))
    war_id = _war_id_for_pair(_state(sim), pair_key)
    row = organization_war_snapshot(sim, war_id) if war_id is not None else None
    if active_only and isinstance(row, dict) and _key(row.get("status")) != "active":
        return None
    return row


def _front_for_anchor(war, anchor):
    anchor_key = _anchor_key(anchor)
    for front in tuple((war.get("fronts") or {}).values()) if isinstance(war.get("fronts"), dict) else ():
        if isinstance(front, dict) and _anchor_key(front.get("anchor")) == anchor_key:
            return front
    return None


def record_organization_war_event(
    sim,
    war_id,
    *,
    event_kind,
    severity,
    source_event="",
    evidence_key="",
    anchor=None,
    property_id=None,
    chunk=None,
    x=None,
    y=None,
    z=None,
    instigator_org_eid=None,
):
    """Apply an attributed event to an existing war and its local front."""

    state = _state(sim)
    war = state.get("wars", {}).get(str(_safe_int(war_id, 0)))
    if not isinstance(war, dict):
        return None
    now = _safe_int(getattr(sim, "tick", 0), 0)
    clean_anchor = _normalize_anchor(sim, anchor, property_id=property_id, chunk=chunk, x=x, y=y, z=z)
    clean_kind = _key(event_kind) or "war_pressure"
    clean_source = _key(source_event) or clean_kind
    evidence_key = _text(evidence_key) or f"{clean_source}:{_anchor_key(clean_anchor)}:{now}"
    history = [dict(row) for row in tuple(war.get("history", ()) or ()) if isinstance(row, dict)]
    if any(_text(row.get("evidence_key")) == evidence_key for row in history if _text(row.get("evidence_key"))):
        return organization_war_snapshot(sim, war_id)

    participants = tuple(_safe_int(value, 0) for value in tuple(war.get("participant_org_eids", ()) or ()))
    severity = max(0.0, _safe_float(severity, 0.0))
    instigator = _organization_root(sim, instigator_org_eid) if instigator_org_eid is not None else None
    fronts = war.get("fronts")
    if not isinstance(fronts, dict):
        fronts = {}
        war["fronts"] = fronts
    front = _front_for_anchor(war, clean_anchor) if _anchor_key(clean_anchor) else None
    if front is None and _anchor_key(clean_anchor) and len(fronts) < ORGANIZATION_WAR_MAX_FRONTS:
        front = _new_front(sim, war_id, participants, clean_kind, clean_anchor, created_tick=now)
        fronts[front["front_id"]] = front
    if isinstance(front, dict):
        prior_outcome = front.get("outcome") if isinstance(front.get("outcome"), dict) else None
        if prior_outcome is not None and _key(front.get("status")) != "contested":
            outcome_history = [
                dict(row)
                for row in tuple(front.get("outcome_history", ()) or ())
                if isinstance(row, dict)
            ]
            outcome_history.append(dict(prior_outcome))
            front["outcome_history"] = outcome_history[-8:]
            front["pressure_by_org"] = {str(int(eid)): 0.0 for eid in participants}
        front["outcome"] = None
        front["status"] = "contested"
        front["last_event_tick"] = now
        if instigator in participants:
            pressure = front.setdefault("pressure_by_org", {})
            key = str(int(instigator))
            pressure[key] = round(_clamp(_safe_float(pressure.get(key), 0.0) + severity, 0.0, 200.0), 3)

    previous_status = _key(war.get("status")) or "active"
    war["status"] = "active"
    war["ceasefire_tick"] = None
    war["ceasefire_reason"] = None
    war["heat"] = round(_clamp(_safe_float(war.get("heat"), 0.0) + severity, 0.0, 200.0), 3)
    war["last_event_tick"] = now
    if instigator in participants:
        momentum = war.setdefault("momentum_by_org", {})
        key = str(int(instigator))
        momentum[key] = round(_clamp(_safe_float(momentum.get(key), 0.0) + (severity * 0.25), -200.0, 200.0), 3)
    history.append({
        "tick": now,
        "event_kind": clean_kind,
        "source_event": clean_source,
        "severity": round(severity, 3),
        "instigator_org_eid": int(instigator) if instigator in participants else None,
        "front_id": front.get("front_id") if isinstance(front, dict) else None,
        "evidence_key": evidence_key,
    })
    war["history"] = history[-ORGANIZATION_WAR_MAX_HISTORY:]

    if previous_status == "ceasefire":
        sim.emit(Event(
            "organization_war_reignited",
            war_id=_safe_int(war.get("war_id"), 0),
            pair_key=war.get("pair_key"),
            event_kind=clean_kind,
            property_id=clean_anchor.get("property_id"),
            property_name=clean_anchor.get("property_name"),
            chunk=clean_anchor.get("chunk"),
            x=clean_anchor.get("x"),
            y=clean_anchor.get("y"),
            z=clean_anchor.get("z"),
        ))
    if isinstance(front, dict):
        _try_decisive_front_stand_down(sim, state, war, front, current_tick=now)
    return organization_war_snapshot(sim, war_id)


def _raw_front_orders(state, war_id, front_id, *, active_only=True):
    rows = []
    for raw in tuple(state.get("orders", {}).values()):
        if not isinstance(raw, dict):
            continue
        if _safe_int(raw.get("war_id"), 0) != _safe_int(war_id, 0):
            continue
        if _text(raw.get("front_id")) != _text(front_id):
            continue
        if active_only and _key(raw.get("status")) not in ORGANIZATION_WAR_ACTIVE_ORDER_STATUSES:
            continue
        rows.append(raw)
    rows.sort(key=lambda row: (_safe_int(row.get("issued_tick"), 0), _text(row.get("order_id"))))
    return tuple(rows)


def _order_actor_is_grounded(sim, raw):
    if not isinstance(raw, dict):
        return False
    actor_eid = _safe_int(raw.get("actor_eid"), 0)
    pos = sim.ecs.get(Position).get(actor_eid)
    if pos is None or sim.ecs.get(AI).get(actor_eid) is None:
        return False
    vitality = sim.ecs.get(Vitality).get(actor_eid)
    if vitality is not None and (
        bool(getattr(vitality, "downed", False))
        or _safe_int(getattr(vitality, "hp", 0), 0) <= 0
    ):
        return False
    suppression = sim.ecs.get(SuppressionState).get(actor_eid)
    return suppression is None or not bool(getattr(suppression, "surrendered", False))


def _order_established_at_front(sim, raw, front):
    if not isinstance(raw, dict) or _key(raw.get("status")) not in {"engaged", "holding"} or not _order_actor_is_grounded(sim, raw):
        return False
    pos = sim.ecs.get(Position).get(_safe_int(raw.get("actor_eid"), 0))
    anchor = front.get("anchor") if isinstance(front, dict) and isinstance(front.get("anchor"), dict) else {}
    if pos is None or int(pos.z) != _safe_int(anchor.get("z"), int(pos.z)):
        return False
    distance = abs(int(pos.x) - _safe_int(anchor.get("x"), int(pos.x))) + abs(
        int(pos.y) - _safe_int(anchor.get("y"), int(pos.y))
    )
    return distance <= 3


def _front_pressure_edge(front, participants):
    pressure = front.get("pressure_by_org") if isinstance(front, dict) and isinstance(front.get("pressure_by_org"), dict) else {}
    rows = sorted(
        (
            (_safe_float(pressure.get(str(int(organization_eid))), 0.0), int(organization_eid))
            for organization_eid in tuple(participants or ())
        ),
        reverse=True,
    )
    if len(rows) != 2:
        return None
    leading_pressure, leading_org_eid = rows[0]
    trailing_pressure, trailing_org_eid = rows[1]
    margin = leading_pressure - trailing_pressure
    if leading_pressure < ORGANIZATION_WAR_FRONT_DECISIVE_MARGIN or margin < ORGANIZATION_WAR_FRONT_DECISIVE_MARGIN:
        return None
    return leading_org_eid, trailing_org_eid, round(margin, 3)


def _emit_front_posture_event(sim, event_kind, war, front, outcome):
    anchor = front.get("anchor") if isinstance(front.get("anchor"), dict) else {}
    sim.emit(Event(
        event_kind,
        war_id=_safe_int(war.get("war_id"), 0),
        front_id=_text(front.get("front_id")),
        front_kind=_key(front.get("front_kind")) or "pressure_line",
        outcome_kind=_key(outcome.get("kind")) or "mutual_disengagement",
        beneficiary_org_eid=_safe_int(outcome.get("beneficiary_org_eid"), 0) or None,
        disadvantaged_org_eid=_safe_int(outcome.get("disadvantaged_org_eid"), 0) or None,
        pressure_margin=round(_safe_float(outcome.get("pressure_margin"), 0.0), 3),
        property_id=anchor.get("property_id"),
        property_name=anchor.get("property_name"),
        chunk=anchor.get("chunk"),
        x=anchor.get("x"),
        y=anchor.get("y"),
        z=anchor.get("z"),
    ))


def _start_front_stand_down(sim, state, war, front, outcome, *, current_tick):
    if _key(front.get("status")) != "contested":
        return False
    now = _safe_int(current_tick, 0)
    clean_outcome = {
        "kind": _key(outcome.get("kind")) or "mutual_disengagement",
        "beneficiary_org_eid": _safe_int(outcome.get("beneficiary_org_eid"), 0) or None,
        "disadvantaged_org_eid": _safe_int(outcome.get("disadvantaged_org_eid"), 0) or None,
        "pressure_margin": round(_safe_float(outcome.get("pressure_margin"), 0.0), 3),
        "decided_tick": now,
        "completed_tick": None,
    }
    front["status"] = "standing_down"
    front["outcome"] = clean_outcome
    front["last_event_tick"] = now
    war["last_event_tick"] = now
    history = [dict(row) for row in tuple(war.get("history", ()) or ()) if isinstance(row, dict)]
    history.append({
        "tick": now,
        "event_kind": "front_standing_down",
        "source_event": clean_outcome["kind"],
        "severity": clean_outcome["pressure_margin"],
        "instigator_org_eid": clean_outcome["beneficiary_org_eid"],
        "front_id": _text(front.get("front_id")),
        "beneficiary_org_eid": clean_outcome["beneficiary_org_eid"],
        "disadvantaged_org_eid": clean_outcome["disadvantaged_org_eid"],
    })
    war["history"] = history[-ORGANIZATION_WAR_MAX_HISTORY:]

    disadvantaged = clean_outcome["disadvantaged_org_eid"]
    for raw in _raw_front_orders(state, war.get("war_id"), front.get("front_id"), active_only=True):
        organization_eid = _safe_int(raw.get("organization_eid"), 0)
        if disadvantaged is None or organization_eid == disadvantaged:
            _begin_order_retreat(
                sim,
                raw,
                "local_edge_lost" if disadvantaged is not None else "mutual_stand_down",
                current_tick=now,
            )
    _emit_front_posture_event(sim, "organization_war_front_standing_down", war, front, clean_outcome)
    return True


def _try_decisive_front_stand_down(sim, state, war, front, *, current_tick):
    if _key(war.get("status")) != "active" or _key(front.get("status")) != "contested":
        return False
    participants = tuple(_safe_int(value, 0) for value in tuple(war.get("participant_org_eids", ()) or ()))
    edge = _front_pressure_edge(front, participants)
    if edge is None:
        return False
    leading_org_eid, trailing_org_eid, margin = edge
    active_orders = _raw_front_orders(state, war.get("war_id"), front.get("front_id"), active_only=True)
    leading_orders = [row for row in active_orders if _safe_int(row.get("organization_eid"), 0) == leading_org_eid]
    trailing_orders = [row for row in active_orders if _safe_int(row.get("organization_eid"), 0) == trailing_org_eid]
    if not any(_order_actor_is_grounded(sim, row) for row in trailing_orders):
        return False
    if not any(_order_established_at_front(sim, row, front) for row in leading_orders):
        return False
    return _start_front_stand_down(
        sim,
        state,
        war,
        front,
        {
            "kind": "local_advantage",
            "beneficiary_org_eid": leading_org_eid,
            "disadvantaged_org_eid": trailing_org_eid,
            "pressure_margin": margin,
        },
        current_tick=current_tick,
    )


def _progress_front_stand_down(sim, state, war, front, *, current_tick):
    if _key(front.get("status")) != "standing_down":
        return False
    now = _safe_int(current_tick, 0)
    outcome = front.get("outcome") if isinstance(front.get("outcome"), dict) else {}
    orders = _raw_front_orders(state, war.get("war_id"), front.get("front_id"), active_only=True)
    disadvantaged = _safe_int(outcome.get("disadvantaged_org_eid"), 0) or None
    waiting = orders if disadvantaged is None else tuple(
        row for row in orders if _safe_int(row.get("organization_eid"), 0) == disadvantaged
    )
    if waiting:
        return False
    front["status"] = "quiet"
    front["last_event_tick"] = now
    outcome["completed_tick"] = now
    front["outcome"] = outcome
    for raw in orders:
        _begin_order_retreat(sim, raw, "front_stood_down", current_tick=now)
    history = [dict(row) for row in tuple(war.get("history", ()) or ()) if isinstance(row, dict)]
    history.append({
        "tick": now,
        "event_kind": "front_quiet",
        "source_event": _key(outcome.get("kind")) or "mutual_disengagement",
        "severity": 0.0,
        "instigator_org_eid": None,
        "front_id": _text(front.get("front_id")),
        "beneficiary_org_eid": _safe_int(outcome.get("beneficiary_org_eid"), 0) or None,
    })
    war["history"] = history[-ORGANIZATION_WAR_MAX_HISTORY:]
    _emit_front_posture_event(sim, "organization_war_front_quiet", war, front, outcome)
    return True


def _war_has_active_orders(state, war_id):
    return any(
        isinstance(raw, dict)
        and _safe_int(raw.get("war_id"), 0) == _safe_int(war_id, 0)
        and _key(raw.get("status")) in ORGANIZATION_WAR_ACTIVE_ORDER_STATUSES
        for raw in tuple(state.get("orders", {}).values())
    )


def _complete_war_ceasefire(sim, state, war, *, current_tick, reason):
    now = _safe_int(current_tick, 0)
    war["status"] = "ceasefire"
    war["ceasefire_tick"] = now
    war["ceasefire_reason"] = _key(reason) or "fronts_stood_down"
    tension = state.get("tensions", {}).get(_text(war.get("pair_key")))
    if isinstance(tension, dict):
        tension["status"] = "ceasefire"
    history = [dict(row) for row in tuple(war.get("history", ()) or ()) if isinstance(row, dict)]
    history.append({
        "tick": now,
        "event_kind": "war_ceasefire",
        "source_event": war["ceasefire_reason"],
        "severity": 0.0,
        "instigator_org_eid": None,
        "front_id": None,
    })
    war["history"] = history[-ORGANIZATION_WAR_MAX_HISTORY:]
    sim.emit(Event(
        "organization_war_ceasefire",
        war_id=_safe_int(war.get("war_id"), 0),
        pair_key=war.get("pair_key"),
        participant_org_eids=tuple(war.get("participant_org_eids", ()) or ()),
        reason=war["ceasefire_reason"],
    ))
    return _safe_int(war.get("war_id"), 0)


def advance_organization_wars(sim, *, current_tick=None):
    """Advance grounded stand-downs and cool only toward mutual disengagement."""

    state = _state(sim)
    now = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick, 0)
    changed = []
    for pair_key, tension in tuple(state.get("tensions", {}).items()):
        if not isinstance(tension, dict) or _safe_int(tension.get("active_war_id"), 0) > 0:
            continue
        if now - _safe_int(tension.get("last_event_tick"), now) < ORGANIZATION_WAR_TENSION_DECAY_DELAY:
            continue
        baseline = _safe_float(tension.get("baseline"), 0.0)
        escalation = max(baseline, _safe_float(tension.get("escalation"), baseline) - 1.0)
        tension["escalation"] = round(escalation, 3)
        tension["status"] = "mobilizing" if escalation >= _safe_float(tension.get("threshold"), 100.0) * 0.7 else "hostile"
    for raw in tuple(state.get("wars", {}).values()):
        if not isinstance(raw, dict) or _key(raw.get("status")) != "active":
            continue
        fronts = tuple(
            front for front in tuple((raw.get("fronts") or {}).values())
            if isinstance(front, dict)
        )
        for front in fronts:
            _try_decisive_front_stand_down(sim, state, raw, front, current_tick=now)

        cooling_ready = now - _safe_int(raw.get("last_event_tick"), now) >= ORGANIZATION_WAR_COOLING_DELAY
        if cooling_ready:
            raw["heat"] = round(max(0.0, _safe_float(raw.get("heat"), 0.0) - 2.0), 3)
            if raw["heat"] <= ORGANIZATION_WAR_CEASEFIRE_HEAT:
                for front in fronts:
                    if _key(front.get("status")) == "contested":
                        _start_front_stand_down(
                            sim,
                            state,
                            raw,
                            front,
                            {"kind": "mutual_disengagement"},
                            current_tick=now,
                        )

        for front in fronts:
            _progress_front_stand_down(sim, state, raw, front, current_tick=now)
        if fronts and all(_key(front.get("status")) == "quiet" for front in fronts):
            if not _war_has_active_orders(state, raw.get("war_id")):
                outcomes = tuple(
                    _key((front.get("outcome") or {}).get("kind"))
                    for front in fronts
                    if isinstance(front.get("outcome"), dict)
                )
                reason = "mutual_disengagement" if outcomes and all(
                    value == "mutual_disengagement" for value in outcomes
                ) else "fronts_stood_down"
                changed.append(_complete_war_ceasefire(sim, state, raw, current_tick=now, reason=reason))
    return tuple(changed)


def organization_war_front_rows(
    sim,
    *,
    property_id=None,
    chunk=None,
    z=None,
    organization_eid=None,
    active_only=True,
):
    wanted_property = _text(property_id)
    wanted_chunk = _chunk_tuple(chunk)
    wanted_org = _safe_int(organization_eid, 0) or None
    rows = []
    for war in organization_war_rows(sim, organization_eid=wanted_org, active_only=active_only):
        for front in tuple(war.get("fronts", ()) or ()):
            if not isinstance(front, dict):
                continue
            anchor = front.get("anchor") if isinstance(front.get("anchor"), dict) else {}
            if wanted_property and _text(anchor.get("property_id")) != wanted_property:
                continue
            if wanted_chunk is not None and _chunk_tuple(anchor.get("chunk")) != wanted_chunk:
                continue
            if z is not None and _safe_int(anchor.get("z"), 0) != _safe_int(z, 0):
                continue
            rows.append({
                **dict(front),
                "war_id": war.get("war_id"),
                "war_status": war.get("status"),
                "war_heat": war.get("heat"),
                "cause": war.get("cause"),
                "participant_org_eids": war.get("participant_org_eids"),
                "participants": war.get("participants"),
            })
    rows.sort(key=lambda row: (0 if _key(row.get("war_status")) == "active" else 1, -_safe_float(row.get("war_heat"), 0.0), _text(row.get("front_id"))))
    return tuple(rows)


def organization_war_front_summary(row):
    if not isinstance(row, dict):
        return None
    kind = _key(row.get("front_kind")) or "pressure_line"
    titles = {
        "remediation_line": "Contested Filter Line",
        "route_control": "Contested Access Line",
        "reprisal_line": "Reprisal Front",
        "signal_front": "Signal Front",
        "pressure_line": "Organization War Front",
    }
    actions = {
        "remediation_line": "inspect the seep, protect the bed, trace the source, or stay clear",
        "route_control": "read the access marks, question a watcher, choose a side, or detour",
        "reprisal_line": "question the watch, help the wounded, find the instigator, or leave",
        "signal_front": "inspect the relays, follow the data trail, interfere, or keep moving",
    }
    participants = tuple(row.get("participants", ()) or ())
    names = [
        _text(ref.get("organization_name"))
        for ref in participants
        if isinstance(ref, dict) and _text(ref.get("organization_name"))
    ]
    sides = " and ".join(names[:2]) if names else "two organizations"
    status = _key(row.get("war_status")) or "active"
    front_status = _key(row.get("status")) or "contested"
    outcome = row.get("outcome") if isinstance(row.get("outcome"), dict) else {}
    beneficiary_eid = _safe_int(outcome.get("beneficiary_org_eid"), 0) or None
    beneficiary_name = next((
        _text(ref.get("organization_name"))
        for ref in participants
        if isinstance(ref, dict) and _safe_int(ref.get("organization_eid"), 0) == beneficiary_eid
    ), "")
    summary = _text(row.get("visible_cue")) or _front_visible_cue(kind)
    if status == "ceasefire":
        if beneficiary_name and _key(outcome.get("kind")) == "local_advantage":
            summary = f"the line is quiet after the opposing detail withdrew from {beneficiary_name}'s local watch; neither side has taken its marks down"
        else:
            summary = f"the line between {sides} is quiet, but neither side has taken its marks down"
    elif front_status == "standing_down":
        if beneficiary_name:
            summary = f"{beneficiary_name}'s local watch has the edge and the opposing detail is withdrawing from the marked line"
        else:
            summary = f"both details are withdrawing from the marked line between {sides}"
    elif front_status == "quiet":
        if beneficiary_name:
            summary = f"the opposing detail has withdrawn from {beneficiary_name}'s local watch, but the site has not changed hands"
        else:
            summary = f"this line between {sides} is quiet while the wider conflict remains active"
    return {
        "title": titles.get(kind, "Organization War Front"),
        "summary": summary,
        "action": actions.get(kind, "read the line, question people nearby, choose a side, or move on"),
        "status": status,
        "front_status": front_status,
        "front_kind": kind,
        "sides": sides,
    }


def actor_war_alignment(sim, actor_eid, *, active_only=True):
    memberships = tuple(actor_org_memberships(sim, actor_eid, active_only=True))
    membership_by_root = {}
    for membership in memberships:
        root = _organization_root(sim, membership.get("organization_eid"))
        if root is not None and root not in membership_by_root:
            membership_by_root[root] = dict(membership)
    rows = []
    for war in organization_war_rows(sim, active_only=active_only):
        aligned = next((eid for eid in war.get("participant_org_eids", ()) if eid in membership_by_root), None)
        if aligned is None:
            continue
        membership = membership_by_root[aligned]
        role = _key(membership.get("role")) or "member"
        ai = sim.ecs.get(AI).get(actor_eid)
        ai_role = _key(getattr(ai, "role", "")) if ai is not None else ""
        rows.append({
            "war_id": war.get("war_id"),
            "war_status": war.get("status"),
            "organization_eid": int(aligned),
            "organization": _org_ref(sim, aligned),
            "opponent_org_eid": next((eid for eid in war.get("participant_org_eids", ()) if eid != aligned), None),
            "membership_role": role,
            "ai_role": ai_role,
            "combat_authorized": bool(
                _key(war.get("status")) == "active"
                and (role in ORGANIZATION_WAR_COMBAT_ROLES or ai_role in ORGANIZATION_WAR_COMBAT_ROLES)
            ),
        })
    return tuple(rows)


def _actor_authorized_war_side(sim, actor_eid, ai, participants):
    membership_by_root = {}
    for membership in actor_org_memberships(sim, actor_eid, active_only=True):
        root = _organization_root(sim, membership.get("organization_eid"))
        if root is not None and root not in membership_by_root:
            membership_by_root[root] = membership
    aligned = next((eid for eid in tuple(participants or ()) if eid in membership_by_root), None)
    if aligned is None:
        return None
    membership_role = _key(membership_by_root[aligned].get("role")) or "member"
    ai_role = _key(getattr(ai, "role", "")) if ai is not None else ""
    if membership_role not in ORGANIZATION_WAR_COMBAT_ROLES and ai_role not in ORGANIZATION_WAR_COMBAT_ROLES:
        return None
    return int(aligned)


def _order_snapshot(sim, raw):
    if not isinstance(raw, dict):
        return None
    actor_eid = _safe_int(raw.get("actor_eid"), 0)
    war_id = _safe_int(raw.get("war_id"), 0)
    if actor_eid <= 0 or war_id <= 0:
        return None
    return {
        **dict(raw),
        "actor_eid": actor_eid,
        "war_id": war_id,
        "organization_eid": _safe_int(raw.get("organization_eid"), 0),
        "opponent_org_eid": _safe_int(raw.get("opponent_org_eid"), 0),
        "origin": dict(raw.get("origin") or {}),
        "objective": dict(raw.get("objective") or {}),
    }


def organization_war_order_rows(
    sim,
    *,
    war_id=None,
    front_id=None,
    organization_eid=None,
    actor_eid=None,
    active_only=False,
):
    """Return durable mobilization orders without exposing mutable rows."""

    wanted_war = _safe_int(war_id, 0) or None
    wanted_front = _text(front_id)
    wanted_org = _safe_int(organization_eid, 0) or None
    wanted_actor = _safe_int(actor_eid, 0) or None
    rows = []
    for raw in tuple(_state(sim).get("orders", {}).values()):
        row = _order_snapshot(sim, raw)
        if row is None:
            continue
        if wanted_war is not None and row["war_id"] != wanted_war:
            continue
        if wanted_front and _text(row.get("front_id")) != wanted_front:
            continue
        if wanted_org is not None and row["organization_eid"] != wanted_org:
            continue
        if wanted_actor is not None and row["actor_eid"] != wanted_actor:
            continue
        if active_only and _key(row.get("status")) not in ORGANIZATION_WAR_ACTIVE_ORDER_STATUSES:
            continue
        rows.append(row)
    rows.sort(key=lambda row: (_safe_int(row.get("war_id"), 0), _text(row.get("front_id")), _safe_int(row.get("issued_tick"), 0), _safe_int(row.get("actor_eid"), 0)))
    return tuple(rows)


def actor_war_order(sim, actor_eid, *, active_only=True):
    rows = organization_war_order_rows(sim, actor_eid=actor_eid, active_only=active_only)
    if not rows:
        return None
    return sorted(
        rows,
        key=lambda row: (
            0 if _key(row.get("status")) == "retreating" else 1,
            -_safe_int(row.get("issued_tick"), 0),
            _text(row.get("order_id")),
        ),
    )[0]


def _raw_war(state, war_id):
    raw = state.get("wars", {}).get(str(_safe_int(war_id, 0)))
    return raw if isinstance(raw, dict) else None


def _raw_front(war, front_id):
    fronts = war.get("fronts") if isinstance(war, dict) else None
    if not isinstance(fronts, dict):
        return None
    front = fronts.get(_text(front_id))
    return front if isinstance(front, dict) else None


def _front_participant_property_side(sim, front, participants, property_id):
    """Return the one participant explicitly attached to a front asset.

    Floor family is deliberately not enough here.  A generic object broken on
    an underground floor must not become anti-community sabotage unless the
    front property itself belongs to that community (and likewise above).
    """

    property_id = _text(property_id)
    anchor = front.get("anchor") if isinstance(front, dict) and isinstance(front.get("anchor"), dict) else {}
    if not property_id or property_id != _text(anchor.get("property_id")):
        return None
    prop = getattr(sim, "properties", {}).get(property_id)
    if not isinstance(prop, dict):
        return None
    participants = {_safe_int(value, 0) for value in tuple(participants or ())}
    linked = set()
    for row in property_org_links(sim, prop, active_only=True):
        root = _organization_root(sim, row.get("organization_eid"))
        if root in participants:
            linked.add(root)
    corporate = corporate_organization_for_property(sim, prop)
    corporate = _organization_root(sim, corporate) if corporate is not None else None
    if corporate in participants:
        linked.add(corporate)
    linked.update(eid for eid in _communities_for_property(sim, prop) if eid in participants)
    return next(iter(linked)) if len(linked) == 1 else None


def _front_side_witnesses(sim, *, war_id, front_id, organization_eid, x, y, z):
    """Loaded ordered actors are the bounded carrier for side attribution."""

    witnesses = []
    for order in organization_war_order_rows(
        sim,
        war_id=war_id,
        front_id=front_id,
        organization_eid=organization_eid,
        active_only=True,
    ):
        actor_eid = _safe_int(order.get("actor_eid"), 0)
        pos = sim.ecs.get(Position).get(actor_eid)
        if pos is None or int(pos.z) != _safe_int(z, int(pos.z)):
            continue
        vitality = sim.ecs.get(Vitality).get(actor_eid)
        if vitality is not None and (
            bool(getattr(vitality, "downed", False))
            or _safe_int(getattr(vitality, "hp", 0), 0) <= 0
        ):
            continue
        if not has_line_of_sight(
            sim,
            int(pos.x),
            int(pos.y),
            int(pos.z),
            _safe_int(x, int(pos.x)),
            _safe_int(y, int(pos.y)),
            _safe_int(z, int(pos.z)),
        ):
            continue
        witnesses.append(actor_eid)
    return tuple(sorted(set(witnesses)))


def record_organization_war_contribution(
    sim,
    war_id,
    front_id,
    *,
    actor_eid,
    beneficiary_org_eid,
    contribution_kind,
    magnitude,
    source_event="",
    evidence_key="",
    observed_by_eids=(),
):
    """Credit one concrete local intervention without inventing a result.

    Objective pressure and war momentum are factual even when nobody knows who
    acted.  Positive organization memory is added only when a loaded ordered
    actor for the beneficiary actually witnessed the intervention.  Accumulated
    pressure can start a stand-down only when both sides have real deployments
    and the beneficiary has an established loaded watch at the exact front.
    """

    state = _state(sim)
    war = _raw_war(state, war_id)
    front = _raw_front(war, front_id)
    if not isinstance(war, dict) or not isinstance(front, dict):
        return None
    if _key(war.get("status")) != "active" or _key(front.get("status")) != "contested":
        return None
    participants = tuple(_safe_int(value, 0) for value in tuple(war.get("participant_org_eids", ()) or ()))
    beneficiary = _organization_root(sim, beneficiary_org_eid)
    actor_eid = _safe_int(actor_eid, 0)
    if actor_eid <= 0 or beneficiary not in participants:
        return None
    kind = _key(contribution_kind) or "front_support"
    raw_amount = _safe_float(magnitude, 0.0)
    if raw_amount <= 0.0:
        return None
    amount = round(_clamp(raw_amount, 0.25, 16.0), 3)
    now = _safe_int(getattr(sim, "tick", 0), 0)
    evidence_key = _text(evidence_key) or f"{kind}:{actor_eid}:{front_id}:{now}"
    history = [dict(row) for row in tuple(war.get("history", ()) or ()) if isinstance(row, dict)]
    if any(_text(row.get("evidence_key")) == evidence_key for row in history):
        return None

    witnesses = tuple(sorted({
        _safe_int(value, 0)
        for value in tuple(observed_by_eids or ())
        if _safe_int(value, 0) > 0
    }))
    observed = bool(witnesses)
    momentum = war.setdefault("momentum_by_org", {})
    beneficiary_key = str(int(beneficiary))
    momentum[beneficiary_key] = round(
        _clamp(_safe_float(momentum.get(beneficiary_key), 0.0) + amount, -200.0, 200.0),
        3,
    )
    pressure = front.setdefault("pressure_by_org", {})
    pressure[beneficiary_key] = round(
        _clamp(_safe_float(pressure.get(beneficiary_key), 0.0) + amount, 0.0, 200.0),
        3,
    )
    front["last_event_tick"] = now
    war["last_event_tick"] = now
    war["heat"] = round(_clamp(_safe_float(war.get("heat"), 0.0) + (amount * 0.15), 0.0, 200.0), 3)

    contribution = {
        "tick": now,
        "actor_eid": actor_eid,
        "beneficiary_org_eid": int(beneficiary),
        "contribution_kind": kind,
        "magnitude": amount,
        "source_event": _key(source_event) or kind,
        "evidence_key": evidence_key,
        "observed": observed,
        "observer_eids": list(witnesses),
    }
    contributions = [
        dict(row)
        for row in tuple(front.get("contributions", ()) or ())
        if isinstance(row, dict)
    ]
    contributions.append(contribution)
    front["contributions"] = contributions[-ORGANIZATION_WAR_MAX_FRONT_CONTRIBUTIONS:]
    history.append({
        "tick": now,
        "event_kind": "front_contribution",
        "source_event": contribution["source_event"],
        "severity": amount,
        "instigator_org_eid": None,
        "front_id": _text(front_id),
        "actor_eid": actor_eid,
        "beneficiary_org_eid": int(beneficiary),
        "contribution_kind": kind,
        "observed": observed,
        "evidence_key": evidence_key,
    })
    war["history"] = history[-ORGANIZATION_WAR_MAX_HISTORY:]

    reputation_change = None
    if observed and actor_eid == _safe_int(getattr(sim, "player_eid", 0), 0):
        from game.organization_reputation import apply_organization_reputation_delta

        reputation_change = apply_organization_reputation_delta(
            sim,
            organization_eid=beneficiary,
            standing_delta=min(0.06, 0.008 + (amount * 0.004)),
            source="organization_war_front",
            reason=kind,
            source_event=contribution["source_event"],
        )

    beneficiary_ref = _org_ref(sim, beneficiary)
    anchor = front.get("anchor") if isinstance(front.get("anchor"), dict) else {}
    sim.emit(Event(
        "organization_war_contribution",
        war_id=_safe_int(war.get("war_id"), 0),
        front_id=_text(front_id),
        front_kind=_key(front.get("front_kind")) or "pressure_line",
        actor_eid=actor_eid,
        beneficiary_org_eid=int(beneficiary),
        beneficiary_org_name=beneficiary_ref.get("organization_name") or f"Organization {beneficiary}",
        contribution_kind=kind,
        magnitude=amount,
        observed=observed,
        observer_eids=witnesses,
        standing_delta=(reputation_change or {}).get("standing_delta", 0.0),
        property_id=anchor.get("property_id"),
        property_name=anchor.get("property_name"),
        chunk=anchor.get("chunk"),
        x=anchor.get("x"),
        y=anchor.get("y"),
        z=anchor.get("z"),
    ))
    _try_decisive_front_stand_down(sim, state, war, front, current_tick=now)
    return dict(contribution)


def _raw_active_order_for_actor(state, actor_eid):
    wanted = _safe_int(actor_eid, 0)
    matches = [
        raw for raw in tuple(state.get("orders", {}).values())
        if isinstance(raw, dict)
        and _safe_int(raw.get("actor_eid"), 0) == wanted
        and _key(raw.get("status")) in ORGANIZATION_WAR_ACTIVE_ORDER_STATUSES
    ]
    if not matches:
        return None
    matches.sort(key=lambda raw: (-_safe_int(raw.get("issued_tick"), 0), _text(raw.get("order_id"))))
    return matches[0]


def _actor_redeploy_available(state, actor_eid, now):
    wanted = _safe_int(actor_eid, 0)
    completed_ticks = [
        _safe_int(raw.get("completed_tick"), 0)
        for raw in tuple(state.get("orders", {}).values())
        if isinstance(raw, dict)
        and _safe_int(raw.get("actor_eid"), 0) == wanted
        and _key(raw.get("status")) in ORGANIZATION_WAR_TERMINAL_ORDER_STATUSES
    ]
    if not completed_ticks:
        return True
    return now - max(completed_ticks) >= ORGANIZATION_WAR_ORDER_REDEPLOY_DELAY


def _position_anchor(sim, pos):
    if pos is None:
        return {}
    prop = None
    try:
        prop = sim.property_at(int(pos.x), int(pos.y), int(pos.z))
    except (AttributeError, TypeError, ValueError):
        prop = None
    result = {
        "x": int(pos.x),
        "y": int(pos.y),
        "z": int(pos.z),
        "chunk": tuple(sim.chunk_coords(int(pos.x), int(pos.y))),
    }
    if isinstance(prop, dict):
        result["property_id"] = _text(prop.get("id")) or None
        result["property_name"] = _text(prop.get("name")) or _text(prop.get("id")) or "local site"
    return result


def _front_realm_organization(sim, front, participants):
    participants = tuple(_safe_int(value, 0) for value in tuple(participants or ()))
    anchor = front.get("anchor") if isinstance(front, dict) and isinstance(front.get("anchor"), dict) else {}
    prop = getattr(sim, "properties", {}).get(_text(anchor.get("property_id")))
    linked = set()
    if isinstance(prop, dict):
        for row in property_org_links(sim, prop, active_only=True):
            root = _organization_root(sim, row.get("organization_eid"))
            if root in participants:
                linked.add(root)
        corporate = corporate_organization_for_property(sim, prop)
        corporate = _organization_root(sim, corporate) if corporate is not None else None
        if corporate in participants:
            linked.add(corporate)
        linked.update(eid for eid in _communities_for_property(sim, prop) if eid in participants)
    if len(linked) == 1:
        return next(iter(linked))
    floor = _safe_int(anchor.get("z"), 0)
    preferred = [
        eid for eid in participants
        if (_is_underground_community(sim, eid) if floor < 0 else _is_corporate_organization(sim, eid))
    ]
    return preferred[0] if len(preferred) == 1 else None


def _front_order_kind(sim, front, organization_eid, participants):
    realm = _front_realm_organization(sim, front, participants)
    if realm is not None:
        return "hold" if int(realm) == int(organization_eid) else "incursion"
    anchor = front.get("anchor") if isinstance(front.get("anchor"), dict) else {}
    floor = _safe_int(anchor.get("z"), 0)
    if floor < 0:
        return "hold" if _is_underground_community(sim, organization_eid) else "incursion"
    return "hold" if _is_corporate_organization(sim, organization_eid) else "incursion"


def _actor_order_candidate(sim, actor_eid, ai, pos, *, combat_authorized, front_anchor, state, now):
    if actor_eid == getattr(sim, "player_eid", None) or ai is None or pos is None:
        return None
    if _key(getattr(ai, "role", "")) == "wildlife":
        return None
    if _raw_active_order_for_actor(state, actor_eid) is not None or not _actor_redeploy_available(state, actor_eid, now):
        return None
    vitality = sim.ecs.get(Vitality).get(actor_eid)
    if vitality is not None and (bool(getattr(vitality, "downed", False)) or _safe_int(getattr(vitality, "hp", 0), 0) <= 0):
        return None
    suppression = sim.ecs.get(SuppressionState).get(actor_eid)
    if suppression is not None and bool(getattr(suppression, "surrendered", False)):
        return None
    if not combat_authorized:
        return None
    front_chunk = _chunk_tuple(front_anchor.get("chunk"))
    actor_chunk = tuple(sim.chunk_coords(int(pos.x), int(pos.y)))
    if front_chunk is not None and actor_chunk != front_chunk:
        return None
    distance = abs(int(pos.x) - _safe_int(front_anchor.get("x"), pos.x)) + abs(int(pos.y) - _safe_int(front_anchor.get("y"), pos.y))
    floor_penalty = abs(int(pos.z) - _safe_int(front_anchor.get("z"), pos.z)) * 8
    return (distance + floor_penalty, int(actor_eid))


def _begin_order_retreat(sim, raw, reason, *, current_tick=None):
    if not isinstance(raw, dict):
        return None
    if _key(raw.get("status")) in ORGANIZATION_WAR_TERMINAL_ORDER_STATUSES:
        return _order_snapshot(sim, raw)
    now = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick, 0)
    already_retreating = _key(raw.get("status")) == "retreating"
    raw["status"] = "retreating"
    if not already_retreating or not _key(raw.get("retreat_reason")):
        raw["retreat_reason"] = _key(reason) or "order_recalled"
    raw["last_update_tick"] = now
    actor_eid = _safe_int(raw.get("actor_eid"), 0)
    if actor_eid > 0:
        mark_actor_urgent(sim, actor_eid, family="all", reason="organization_war_retreat", ttl_ticks=36)
        schedule_actor_due(sim, actor_eid, "will", delay_ticks=0, reason="organization_war_retreat")
        schedule_actor_due(sim, actor_eid, "move", delay_ticks=0, reason="organization_war_retreat")
    if not already_retreating:
        origin = raw.get("origin") if isinstance(raw.get("origin"), dict) else {}
        sim.emit(Event(
            "organization_war_order_recalled",
            order_id=raw.get("order_id"),
            war_id=_safe_int(raw.get("war_id"), 0),
            front_id=raw.get("front_id"),
            actor_eid=actor_eid,
            organization_eid=_safe_int(raw.get("organization_eid"), 0),
            reason=raw.get("retreat_reason"),
            x=origin.get("x"),
            y=origin.get("y"),
            z=origin.get("z"),
        ))
    return _order_snapshot(sim, raw)


def _finish_order(sim, raw, status, reason, *, current_tick=None):
    if not isinstance(raw, dict):
        return None
    now = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick, 0)
    raw["status"] = _key(status) if _key(status) in ORGANIZATION_WAR_TERMINAL_ORDER_STATUSES else "complete"
    raw["completion_reason"] = _key(reason) or "returned"
    raw["completed_tick"] = now
    raw["last_update_tick"] = now
    actor_eid = _safe_int(raw.get("actor_eid"), 0)
    pos = sim.ecs.get(Position).get(actor_eid)
    sim.emit(Event(
        "organization_war_order_completed",
        order_id=raw.get("order_id"),
        war_id=_safe_int(raw.get("war_id"), 0),
        front_id=raw.get("front_id"),
        actor_eid=actor_eid,
        organization_eid=_safe_int(raw.get("organization_eid"), 0),
        reason=raw.get("completion_reason"),
        x=int(pos.x) if pos is not None else None,
        y=int(pos.y) if pos is not None else None,
        z=int(pos.z) if pos is not None else None,
    ))
    return _order_snapshot(sim, raw)


def _issue_order(sim, state, war, front, organization_eid, opponent_org_eid, actor_eid, order_kind, *, current_tick=None):
    now = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick, 0)
    pos = sim.ecs.get(Position).get(actor_eid)
    if pos is None:
        return None
    active_count = sum(
        1 for raw in tuple(state.get("orders", {}).values())
        if isinstance(raw, dict) and _key(raw.get("status")) in ORGANIZATION_WAR_ACTIVE_ORDER_STATUSES
    )
    if active_count >= ORGANIZATION_WAR_MAX_ORDERS:
        return None
    anchor = dict(front.get("anchor") or {})
    order_number = max(1, _safe_int(state.get("next_order_id"), 1))
    state["next_order_id"] = order_number + 1
    order_id = f"war-order:{order_number}"
    rng = random.Random(f"{getattr(sim, 'seed', 0)}:{order_id}:{war.get('war_id')}:{front.get('front_id')}:{actor_eid}")
    duration = rng.randint(ORGANIZATION_WAR_ORDER_MIN_DURATION, ORGANIZATION_WAR_ORDER_MAX_DURATION)
    distance_limit = max(18, (_safe_int(getattr(sim, "chunk_size", 8), 8) * 2) + 6)
    at_objective = int(pos.z) == _safe_int(anchor.get("z"), pos.z) and (
        abs(int(pos.x) - _safe_int(anchor.get("x"), pos.x))
        + abs(int(pos.y) - _safe_int(anchor.get("y"), pos.y))
    ) <= 3
    raw = {
        "order_id": order_id,
        "war_id": _safe_int(war.get("war_id"), 0),
        "front_id": _text(front.get("front_id")),
        "organization_eid": int(organization_eid),
        "opponent_org_eid": int(opponent_org_eid),
        "actor_eid": int(actor_eid),
        "order_kind": _key(order_kind) or "hold",
        "status": "holding" if at_objective else "mobilizing",
        "origin": _position_anchor(sim, pos),
        "objective": anchor,
        "issued_tick": now,
        "expires_tick": now + duration,
        "last_update_tick": now,
        "last_progress_tick": now,
        "crossed_tick": None,
        "transition_count": 0,
        "max_displacement": distance_limit,
        "retreat_reason": None,
        "completion_reason": None,
        "completed_tick": None,
    }
    state["orders"][order_id] = raw
    mark_actor_urgent(sim, actor_eid, family="all", reason="organization_war_order", ttl_ticks=48)
    schedule_actor_due(sim, actor_eid, "will", delay_ticks=0, reason="organization_war_order")
    schedule_actor_due(sim, actor_eid, "move", delay_ticks=1, reason="organization_war_order")
    sim.emit(Event(
        "organization_war_order_issued",
        order_id=order_id,
        war_id=raw["war_id"],
        front_id=raw["front_id"],
        actor_eid=int(actor_eid),
        organization_eid=int(organization_eid),
        opponent_org_eid=int(opponent_org_eid),
        order_kind=raw["order_kind"],
        property_id=anchor.get("property_id"),
        property_name=anchor.get("property_name"),
        x=anchor.get("x"),
        y=anchor.get("y"),
        z=anchor.get("z"),
    ))
    return _order_snapshot(sim, raw)


def refresh_organization_war_orders(sim, *, chunk=None, current_tick=None):
    """Issue sparse loaded-actor orders and recall invalid deployments.

    This never creates offscreen units.  Incursions require two currently loaded,
    explicitly combat-authorized actors; a lone guard may hold a local line but
    will not be sent into another side's realm.
    """

    state = _state(sim)
    now = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick, 0)
    positions = sim.ecs.get(Position)
    ais = sim.ecs.get(AI)
    wanted_chunk = _chunk_tuple(chunk)

    for raw in tuple(state.get("orders", {}).values()):
        if not isinstance(raw, dict) or _key(raw.get("status")) not in ORGANIZATION_WAR_ACTIVE_ORDER_STATUSES:
            continue
        actor_eid = _safe_int(raw.get("actor_eid"), 0)
        if actor_eid not in positions or actor_eid not in ais:
            _finish_order(sim, raw, "cancelled", "actor_unloaded", current_tick=now)
            continue
        war = _raw_war(state, raw.get("war_id"))
        front = _raw_front(war, raw.get("front_id"))
        if not isinstance(war, dict) or not isinstance(front, dict):
            _begin_order_retreat(sim, raw, "front_lost", current_tick=now)
            continue
        if _key(war.get("status")) != "active" or _key(front.get("status")) == "quiet":
            _begin_order_retreat(sim, raw, "ceasefire", current_tick=now)
            continue
        if now >= _safe_int(raw.get("expires_tick"), now + 1):
            _begin_order_retreat(sim, raw, "order_expired", current_tick=now)

    for war in tuple(state.get("wars", {}).values()):
        if not isinstance(war, dict) or _key(war.get("status")) != "active":
            continue
        for front in tuple((war.get("fronts") or {}).values()):
            if not isinstance(front, dict):
                continue
            _try_decisive_front_stand_down(sim, state, war, front, current_tick=now)
            _progress_front_stand_down(sim, state, war, front, current_tick=now)

    wars = organization_war_rows(sim, active_only=True)
    for war in wars:
        participants = tuple(_safe_int(value, 0) for value in tuple(war.get("participant_org_eids", ()) or ()))
        if len(participants) < 2:
            continue
        authorized_side_by_actor = {
            int(actor_eid): side
            for actor_eid, ai in tuple(ais.items())
            for side in (_actor_authorized_war_side(sim, actor_eid, ai, participants),)
            if side is not None
        }
        for front in tuple(war.get("fronts", ()) or ()):
            if not isinstance(front, dict) or _key(front.get("status")) != "contested":
                continue
            anchor = front.get("anchor") if isinstance(front.get("anchor"), dict) else {}
            front_chunk = _chunk_tuple(anchor.get("chunk"))
            if wanted_chunk is not None and front_chunk != wanted_chunk:
                continue
            for organization_eid in participants:
                opponent_org_eid = next((eid for eid in participants if eid != organization_eid), None)
                if opponent_org_eid is None:
                    continue
                order_kind = _front_order_kind(sim, front, organization_eid, participants)
                existing = [
                    raw for raw in tuple(state.get("orders", {}).values())
                    if isinstance(raw, dict)
                    and _safe_int(raw.get("war_id"), 0) == _safe_int(war.get("war_id"), 0)
                    and _text(raw.get("front_id")) == _text(front.get("front_id"))
                    and _safe_int(raw.get("organization_eid"), 0) == int(organization_eid)
                    and _key(raw.get("status")) in ORGANIZATION_WAR_ACTIVE_ORDER_STATUSES
                    and _key(raw.get("status")) != "retreating"
                ]
                candidates = []
                for actor_eid, ai in tuple(ais.items()):
                    if authorized_side_by_actor.get(int(actor_eid)) != int(organization_eid):
                        continue
                    pos = positions.get(actor_eid)
                    score = _actor_order_candidate(
                        sim,
                        actor_eid,
                        ai,
                        pos,
                        combat_authorized=True,
                        front_anchor=anchor,
                        state=state,
                        now=now,
                    )
                    if score is not None:
                        candidates.append((score, int(actor_eid)))
                candidates.sort(key=lambda row: row[0])
                available_total = len(existing) + len(candidates)
                if order_kind == "incursion" and available_total < 2:
                    for raw in existing:
                        if now - _safe_int(raw.get("issued_tick"), now) >= ORGANIZATION_WAR_ORDER_REFRESH_INTERVAL:
                            _begin_order_retreat(sim, raw, "support_lost", current_tick=now)
                    continue
                desired = min(ORGANIZATION_WAR_MAX_ORDERS_PER_SIDE, available_total)
                for _score, actor_eid in candidates[:max(0, desired - len(existing))]:
                    _issue_order(
                        sim,
                        state,
                        war,
                        front,
                        organization_eid,
                        opponent_org_eid,
                        actor_eid,
                        order_kind,
                        current_tick=now,
                    )
    _trim_state(state)
    return organization_war_order_rows(sim, active_only=True)


def _access_destination(prop):
    if not isinstance(prop, dict):
        return None
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    services = {_key(value) for value in tuple(metadata.get("site_services", ()) or ())}
    if _key(UNDERGROUND_ACCESS_SERVICE) not in services:
        return None
    destinations = metadata.get("site_service_destinations")
    if not isinstance(destinations, dict):
        return None
    destination = destinations.get(UNDERGROUND_ACCESS_SERVICE)
    if not isinstance(destination, dict):
        destination = destinations.get(_key(UNDERGROUND_ACCESS_SERVICE))
    return dict(destination) if isinstance(destination, dict) else None


def _access_for_levels(sim, pos, target, *, front_chunk=None):
    target_z = _safe_int(target.get("z"), int(pos.z))
    candidates = []
    for prop in tuple(getattr(sim, "properties", {}).values()):
        if not isinstance(prop, dict) or _safe_int(prop.get("z"), 0) != int(pos.z):
            continue
        destination = _access_destination(prop)
        if not isinstance(destination, dict) or _safe_int(destination.get("z"), int(pos.z)) != target_z:
            continue
        prop_chunk = _property_chunk(sim, prop)
        if front_chunk is not None and prop_chunk != front_chunk:
            continue
        distance = abs(_safe_int(prop.get("x"), pos.x) - int(pos.x)) + abs(_safe_int(prop.get("y"), pos.y) - int(pos.y))
        candidates.append((distance, _text(prop.get("id")), prop, destination))
    if not candidates:
        return None
    candidates.sort(key=lambda row: (row[0], row[1]))
    _distance, _property_id, prop, destination = candidates[0]
    return prop, destination


def _transition_actor_through_access(sim, raw, actor_eid, pos, prop, destination):
    try:
        dest_x = int(destination.get("x"))
        dest_y = int(destination.get("y"))
        dest_z = int(destination.get("z"))
    except (TypeError, ValueError):
        return False
    if hasattr(sim, "stream_world"):
        sim.stream_world(dest_x, dest_y)
    if hasattr(sim, "ensure_loaded_chunk_terrain"):
        sim.ensure_loaded_chunk_terrain()
    candidates = [(dest_x, dest_y)]
    for radius in range(1, 5):
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if abs(dx) + abs(dy) == radius:
                    candidates.append((dest_x + dx, dest_y + dy))
    moved = False
    for landing_x, landing_y in candidates:
        tile = sim.tilemap.tile_at(landing_x, landing_y, dest_z)
        if tile is None or not bool(getattr(tile, "walkable", False)):
            continue
        moved, _reason = try_move_entity(
            sim,
            actor_eid,
            landing_x,
            landing_y,
            dest_z,
            reason="organization_war_access_transition",
        )
        if moved:
            break
    if not moved:
        return False
    now = _safe_int(getattr(sim, "tick", 0), 0)
    raw["transition_count"] = _safe_int(raw.get("transition_count"), 0) + 1
    raw["crossed_tick"] = now
    raw["last_progress_tick"] = now
    raw["last_update_tick"] = now
    sim.emit(Event(
        "organization_war_actor_crossed",
        order_id=raw.get("order_id"),
        war_id=_safe_int(raw.get("war_id"), 0),
        front_id=raw.get("front_id"),
        actor_eid=int(actor_eid),
        organization_eid=_safe_int(raw.get("organization_eid"), 0),
        opponent_org_eid=_safe_int(raw.get("opponent_org_eid"), 0),
        order_kind=raw.get("order_kind"),
        access_property_id=prop.get("id"),
        access_property_name=prop.get("name"),
        x=int(sim.ecs.get(Position).get(actor_eid).x),
        y=int(sim.ecs.get(Position).get(actor_eid).y),
        z=int(sim.ecs.get(Position).get(actor_eid).z),
    ))
    return True


def _order_opponent_contact(sim, raw, pos):
    state = _state(sim)
    opponent_org_eid = _safe_int(raw.get("opponent_org_eid"), 0)
    war_id = _safe_int(raw.get("war_id"), 0)
    front_id = _text(raw.get("front_id"))
    candidates = []
    vitalities = sim.ecs.get(Vitality)
    suppressions = sim.ecs.get(SuppressionState)
    positions = sim.ecs.get(Position)
    for other in tuple(state.get("orders", {}).values()):
        if not isinstance(other, dict) or _key(other.get("status")) not in {"advancing", "engaged", "holding", "mobilizing"}:
            continue
        if _safe_int(other.get("war_id"), 0) != war_id or _text(other.get("front_id")) != front_id:
            continue
        if _safe_int(other.get("organization_eid"), 0) != opponent_org_eid:
            continue
        other_eid = _safe_int(other.get("actor_eid"), 0)
        other_pos = positions.get(other_eid)
        if other_pos is None or int(other_pos.z) != int(pos.z):
            continue
        vitality = vitalities.get(other_eid)
        if vitality is not None and (bool(getattr(vitality, "downed", False)) or _safe_int(getattr(vitality, "hp", 0), 0) <= 0):
            continue
        suppression = suppressions.get(other_eid)
        if suppression is not None and bool(getattr(suppression, "surrendered", False)):
            continue
        distance = abs(int(pos.x) - int(other_pos.x)) + abs(int(pos.y) - int(other_pos.y))
        if distance > 12:
            continue
        if not has_line_of_sight(sim, int(pos.x), int(pos.y), int(pos.z), int(other_pos.x), int(other_pos.y), int(other_pos.z)):
            continue
        candidates.append((distance, other_eid, other_pos))
    if not candidates:
        return None
    candidates.sort(key=lambda row: (row[0], row[1]))
    distance, other_eid, other_pos = candidates[0]
    return {
        "target_eid": int(other_eid),
        "target": (int(other_pos.x), int(other_pos.y), int(other_pos.z)),
        "distance": int(distance),
    }


def actor_war_order_intent(sim, actor_eid):
    """Advance one loaded actor's durable order and return its immediate intent."""

    state = _state(sim)
    raw = _raw_active_order_for_actor(state, actor_eid)
    if not isinstance(raw, dict):
        return None
    now = _safe_int(getattr(sim, "tick", 0), 0)
    pos = sim.ecs.get(Position).get(actor_eid)
    ai = sim.ecs.get(AI).get(actor_eid)
    if pos is None or ai is None:
        _finish_order(sim, raw, "cancelled", "actor_unloaded", current_tick=now)
        return None
    war = _raw_war(state, raw.get("war_id"))
    front = _raw_front(war, raw.get("front_id"))
    authorized_side = _actor_authorized_war_side(
        sim,
        actor_eid,
        ai,
        tuple(war.get("participant_org_eids", ()) or ()) if isinstance(war, dict) else (),
    )
    if not isinstance(war, dict) or not isinstance(front, dict):
        _begin_order_retreat(sim, raw, "front_lost", current_tick=now)
    elif _key(war.get("status")) != "active" or _key(front.get("status")) == "quiet":
        _begin_order_retreat(sim, raw, "ceasefire", current_tick=now)
    elif authorized_side != _safe_int(raw.get("organization_eid"), 0):
        _begin_order_retreat(sim, raw, "role_lost", current_tick=now)
    elif now >= _safe_int(raw.get("expires_tick"), now + 1):
        _begin_order_retreat(sim, raw, "order_expired", current_tick=now)

    vitality = sim.ecs.get(Vitality).get(actor_eid)
    if _key(raw.get("status")) != "retreating" and vitality is not None:
        max_hp = max(1, _safe_int(getattr(vitality, "max_hp", 1), 1))
        if bool(getattr(vitality, "downed", False)) or (_safe_int(getattr(vitality, "hp", max_hp), max_hp) / float(max_hp)) <= ORGANIZATION_WAR_ORDER_RETREAT_HP_RATIO:
            _begin_order_retreat(sim, raw, "injured", current_tick=now)
    suppression = sim.ecs.get(SuppressionState).get(actor_eid)
    if _key(raw.get("status")) != "retreating" and suppression is not None:
        if bool(getattr(suppression, "surrendered", False)) or _safe_float(getattr(suppression, "pressure", 0.0), 0.0) >= ORGANIZATION_WAR_ORDER_RETREAT_SUPPRESSION:
            _begin_order_retreat(sim, raw, "suppressed", current_tick=now)

    retreating = _key(raw.get("status")) == "retreating"
    target = dict(raw.get("origin") if retreating else raw.get("objective") or {})
    if not target:
        _finish_order(sim, raw, "cancelled", "missing_anchor", current_tick=now)
        return None
    target_chunk = _chunk_tuple(target.get("chunk"))
    current_chunk = tuple(sim.chunk_coords(int(pos.x), int(pos.y)))
    if not retreating and target_chunk is not None and current_chunk != target_chunk:
        _begin_order_retreat(sim, raw, "displaced", current_tick=now)
        retreating = True
        target = dict(raw.get("origin") or {})
        target_chunk = _chunk_tuple(target.get("chunk"))
    if not retreating:
        origin = raw.get("origin") if isinstance(raw.get("origin"), dict) else {}
        objective = raw.get("objective") if isinstance(raw.get("objective"), dict) else {}
        current_to_origin = abs(int(pos.x) - _safe_int(origin.get("x"), pos.x)) + abs(int(pos.y) - _safe_int(origin.get("y"), pos.y))
        current_to_objective = abs(int(pos.x) - _safe_int(objective.get("x"), pos.x)) + abs(int(pos.y) - _safe_int(objective.get("y"), pos.y))
        if min(current_to_origin, current_to_objective) > max(8, _safe_int(raw.get("max_displacement"), 22)):
            _begin_order_retreat(sim, raw, "displaced", current_tick=now)
            retreating = True
            target = dict(raw.get("origin") or {})
            target_chunk = _chunk_tuple(target.get("chunk"))

    if int(pos.z) != _safe_int(target.get("z"), int(pos.z)):
        access = _access_for_levels(sim, pos, target, front_chunk=target_chunk)
        if access is None:
            if retreating:
                _finish_order(sim, raw, "cancelled", "return_route_lost", current_tick=now)
            else:
                _begin_order_retreat(sim, raw, "route_lost", current_tick=now)
            return None
        access_prop, destination = access
        access_target = (
            _safe_int(access_prop.get("x"), pos.x),
            _safe_int(access_prop.get("y"), pos.y),
            _safe_int(access_prop.get("z"), pos.z),
        )
        distance = abs(int(pos.x) - access_target[0]) + abs(int(pos.y) - access_target[1])
        if distance <= 1 and _transition_actor_through_access(sim, raw, actor_eid, pos, access_prop, destination):
            pos = sim.ecs.get(Position).get(actor_eid)
        else:
            raw["last_update_tick"] = now
            raw["status"] = "retreating" if retreating else "mobilizing"
            return {
                "intent": "war_retreating" if retreating else "war_mobilizing",
                "score": 96.0 if retreating else 88.0,
                "target": access_target,
                "target_eid": None,
                "order": _order_snapshot(sim, raw),
            }

    destination_target = (
        _safe_int(target.get("x"), pos.x),
        _safe_int(target.get("y"), pos.y),
        _safe_int(target.get("z"), pos.z),
    )
    distance = abs(int(pos.x) - destination_target[0]) + abs(int(pos.y) - destination_target[1])
    if retreating:
        if int(pos.z) == destination_target[2] and distance <= 1:
            _finish_order(sim, raw, "complete", raw.get("retreat_reason") or "returned", current_tick=now)
            return None
        raw["last_update_tick"] = now
        return {
            "intent": "war_retreating",
            "score": 96.0,
            "target": destination_target,
            "target_eid": None,
            "order": _order_snapshot(sim, raw),
        }

    contact = _order_opponent_contact(sim, raw, pos)
    if isinstance(contact, dict):
        raw["status"] = "engaged"
        raw["last_update_tick"] = now
        return {
            "intent": "protecting",
            "score": 94.0,
            "target": contact["target"],
            "target_eid": contact["target_eid"],
            "order": _order_snapshot(sim, raw),
            "war_contact": True,
        }

    if int(pos.z) == destination_target[2] and distance <= 3:
        raw["status"] = "holding"
        intent = "war_holding"
        score = 84.0
    else:
        raw["status"] = "advancing" if _key(raw.get("order_kind")) == "incursion" else "mobilizing"
        intent = "war_advancing" if raw["status"] == "advancing" else "war_mobilizing"
        score = 90.0 if raw["status"] == "advancing" else 86.0
    raw["last_update_tick"] = now
    return {
        "intent": intent,
        "score": score,
        "target": destination_target,
        "target_eid": None,
        "order": _order_snapshot(sim, raw),
    }


def _actor_front(sim, actor_eid, alignment):
    pos = sim.ecs.get(Position).get(actor_eid)
    if pos is None:
        return None
    chunk = tuple(sim.chunk_coords(int(pos.x), int(pos.y)))
    rows = organization_war_front_rows(
        sim,
        chunk=chunk,
        z=int(pos.z),
        organization_eid=alignment.get("organization_eid"),
        active_only=True,
    )
    if not rows:
        return None
    rows = sorted(
        rows,
        key=lambda row: (
            abs(_safe_int((row.get("anchor") or {}).get("x"), pos.x) - int(pos.x))
            + abs(_safe_int((row.get("anchor") or {}).get("y"), pos.y) - int(pos.y)),
            _text(row.get("front_id")),
        ),
    )
    return rows[0]


def war_chatter_payload_for_actor(sim, speaker_eid, partner_eid, *, relation="neighbor", tone="gossip", count=0):
    positions = sim.ecs.get(Position)
    speaker_pos = positions.get(speaker_eid)
    partner_pos = positions.get(partner_eid)
    if speaker_pos is None or partner_pos is None or int(speaker_pos.z) != int(partner_pos.z):
        return None
    if tuple(sim.chunk_coords(int(speaker_pos.x), int(speaker_pos.y))) != tuple(
        sim.chunk_coords(int(partner_pos.x), int(partner_pos.y))
    ):
        return None
    speaker_alignments = actor_war_alignment(sim, speaker_eid, active_only=True)
    partner_alignments = actor_war_alignment(sim, partner_eid, active_only=True)
    if not speaker_alignments or not partner_alignments:
        return None
    alignment = next(
        (
            row for row in speaker_alignments
            if any(
                other.get("war_id") == row.get("war_id")
                and other.get("organization_eid") == row.get("organization_eid")
                for other in partner_alignments
            )
        ),
        None,
    )
    if alignment is None:
        return None
    front = _actor_front(sim, speaker_eid, alignment)
    if not isinstance(front, dict):
        return None
    rng = random.Random(
        f"{getattr(sim, 'seed', 0)}:war-chatter:{alignment.get('war_id')}:"
        f"{speaker_eid}:{partner_eid}:{relation}:{tone}:{int(count)}"
    )
    if rng.random() >= 0.48:
        return None
    anchor = front.get("anchor") if isinstance(front.get("anchor"), dict) else {}
    place = _text(anchor.get("property_name")) or "the local line"
    organization_eid = alignment.get("organization_eid")
    objective = _text((front.get("objectives") or {}).get(str(int(organization_eid))))
    front_status = _key(front.get("status")) or "contested"
    outcome = front.get("outcome") if isinstance(front.get("outcome"), dict) else {}
    beneficiary = _safe_int(outcome.get("beneficiary_org_eid"), 0) or None
    if front_status == "standing_down" and beneficiary == _safe_int(organization_eid, 0):
        quotes = (
            f"They're pulling off {place}. Keep the way clear and let them go.",
            f"Hold the marks at {place}. Nobody follows the retreat home.",
            f"The line at {place} bent our way. That is not permission to chase.",
        )
    elif front_status == "standing_down":
        quotes = (
            f"We're coming off {place}. Keep the return route open.",
            f"The detail at {place} is withdrawing. Nobody gets left on the stairs.",
            f"Pull the watch back from {place}. The line is spent for now.",
        )
    elif _is_underground_community(sim, organization_eid):
        quotes = (
            f"Someone needs eyes on {place}. They have marked the line again.",
            f"Check {place} before you settle in. Quiet does not mean cleared.",
            f"The watch at {place} needs another pair of hands.",
        )
    else:
        quotes = (
            f"The line at {place} is still contested. Keep your credentials visible.",
            f"Do not improvise around {place}. The access order is still live.",
            f"They are holding at {place}. Report changes before you approach.",
        )
    quote = quotes[rng.randrange(len(quotes))]
    return {
        "topic": "organization_war",
        "quote": quote,
        "summary": f"voices trade warnings about the contested line at {place}",
        "detail": objective or "The warning belongs to an active local front.",
        "channel": "social",
        "priority": "medium",
        "source_domain": "organization_war",
        "war_id": alignment.get("war_id"),
        "front_id": front.get("front_id"),
        "property_id": anchor.get("property_id"),
        "property_name": place,
        "organization_eid": organization_eid,
        "opponent_org_eid": alignment.get("opponent_org_eid"),
        "level_local": True,
    }


def _communities_for_property(sim, prop):
    rows = set()
    if not isinstance(prop, dict):
        return ()
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    culture_key = _text(metadata.get("underground_culture_key"))
    culture_eid = organization_eid_for_key(sim, culture_key) if culture_key else None
    if culture_eid is not None and _is_underground_community(sim, culture_eid):
        rows.add(int(culture_eid))
    for link in property_org_links(sim, prop, active_only=True):
        organization_eid = _safe_int(link.get("organization_eid"), 0)
        if organization_eid > 0 and _is_underground_community(sim, organization_eid):
            rows.add(organization_eid)
    return tuple(sorted(rows))


def _communities_for_chunk(sim, chunk):
    chunk = _chunk_tuple(chunk)
    if chunk is None:
        return ()
    rows = set()
    for prop in tuple(getattr(sim, "properties", {}).values()):
        if isinstance(prop, dict) and _property_chunk(sim, prop) == chunk:
            rows.update(_communities_for_property(sim, prop))
    return tuple(sorted(rows))


def _property_for_origin(sim, origin):
    origin = _text(origin)
    if not origin:
        return None
    direct = getattr(sim, "properties", {}).get(origin)
    if isinstance(direct, dict):
        return direct
    for prop in tuple(getattr(sim, "properties", {}).values()):
        if not isinstance(prop, dict):
            continue
        metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
        if origin in {
            _text(metadata.get("building_id")),
            _text(metadata.get("local_building_id")),
        }:
            return prop
    return None


def _corporate_source_for_hazard(sim, hazard):
    if not isinstance(hazard, dict):
        return None
    metadata = hazard.get("metadata") if isinstance(hazard.get("metadata"), dict) else {}
    explicit = _safe_int(
        metadata.get("source_organization_eid")
        or metadata.get("accountable_organization_eid")
        or metadata.get("corporate_organization_eid"),
        0,
    )
    if explicit > 0 and _is_corporate_organization(sim, explicit):
        return _organization_root(sim, explicit)
    candidates = []
    linked = getattr(sim, "properties", {}).get(_text(metadata.get("linked_property_id")))
    if isinstance(linked, dict):
        candidates.append(linked)
    origin = _property_for_origin(sim, metadata.get("contamination_origin"))
    if isinstance(origin, dict):
        candidates.append(origin)
    for prop in candidates:
        corporate = corporate_organization_for_property(sim, prop)
        if corporate is not None:
            return _organization_root(sim, corporate)
    return None


def _hazard_has_filter_bed(sim, hazard_id):
    hazard_id = _text(hazard_id)
    return any(
        isinstance(row, dict)
        and _text(row.get("contamination_property_id")) == hazard_id
        and bool(row.get("tended_filter_bed"))
        for row in tuple(getattr(sim, "flora_patches", {}).values())
    )


def sync_underground_corporate_tensions(sim, *, chunk=None, limit=8):
    """Discover only locally justified corporate/community hostility."""

    wanted_chunk = _chunk_tuple(chunk)
    culture_properties = []
    for prop in tuple(getattr(sim, "properties", {}).values()):
        if not isinstance(prop, dict):
            continue
        metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
        if not _text(metadata.get("underground_culture_key")):
            continue
        prop_chunk = _property_chunk(sim, prop)
        if wanted_chunk is not None and prop_chunk != wanted_chunk:
            continue
        culture_properties.append(prop)
    synced = []
    for community_prop in culture_properties:
        if len(synced) >= max(1, _safe_int(limit, 8)):
            break
        community_ids = _communities_for_property(sim, community_prop)
        if not community_ids:
            continue
        local_chunk = _property_chunk(sim, community_prop)
        candidates = {}

        direct_corporate = corporate_organization_for_property(sim, community_prop)
        if direct_corporate is not None:
            candidates.setdefault(_organization_root(sim, direct_corporate), []).append({
                "reason": "infrastructure_control",
                "severity": 28.0,
                "anchor": _anchor_from_property(sim, community_prop),
                "evidence_key": f"infrastructure-control:{community_prop.get('id')}:{direct_corporate}",
            })

        for presence in corporate_neighborhood_presence_rows(sim, chunk=local_chunk, active_only=True):
            corporate = _organization_root(sim, presence.get("corporate_org_eid"))
            if corporate is None:
                continue
            tier = max(1, _safe_int(presence.get("tier"), 1))
            candidates.setdefault(corporate, []).append({
                "reason": "corporate_occupation",
                "severity": min(38.0, 18.0 + (tier * 5.0)),
                "anchor": _anchor_from_property(sim, community_prop),
                "evidence_key": f"corporate-occupation:{corporate}:{local_chunk}",
            })

        for hazard in tuple(getattr(sim, "properties", {}).values()):
            if not isinstance(hazard, dict) or _property_chunk(sim, hazard) != local_chunk:
                continue
            metadata = hazard.get("metadata") if isinstance(hazard.get("metadata"), dict) else {}
            if _key(metadata.get("hazard_profile")) != "spent_cell_blackwash":
                continue
            corporate = _corporate_source_for_hazard(sim, hazard)
            if corporate is None:
                continue
            load = max(0.0, _safe_float(metadata.get("contamination_load"), 0.0))
            filtered = _hazard_has_filter_bed(sim, hazard.get("id"))
            candidates.setdefault(corporate, []).append({
                "reason": "attributed_blackwash",
                "severity": min(48.0, 26.0 + (load * 3.0) + (6.0 if filtered else 0.0)),
                "anchor": _anchor_from_property(sim, hazard),
                "evidence_key": f"attributed-blackwash:{hazard.get('id')}:{corporate}",
                "historical_war_eligible": bool(filtered and load >= 1.0),
            })

        for community_eid in community_ids:
            for corporate_eid, evidence_rows in sorted(candidates.items()):
                if len(synced) >= max(1, _safe_int(limit, 8)):
                    break
                if corporate_eid is None or int(corporate_eid) == int(community_eid):
                    continue
                last = None
                for evidence in evidence_rows:
                    last = record_organization_tension(
                        sim,
                        org_a_eid=community_eid,
                        org_b_eid=corporate_eid,
                        reason=evidence["reason"],
                        severity=evidence["severity"],
                        source_event="underground_conflict_sync",
                        evidence_key=evidence["evidence_key"],
                        anchor=evidence["anchor"],
                        baseline=True,
                        escalation_trigger=False,
                    )
                    if evidence.get("historical_war_eligible"):
                        rng = random.Random(
                            f"{getattr(sim, 'seed', 0)}:historical-underground-war:"
                            f"{_pair_key(community_eid, corporate_eid)}:{evidence['evidence_key']}"
                        )
                        if rng.random() < 0.22:
                            last = record_organization_tension(
                                sim,
                                org_a_eid=community_eid,
                                org_b_eid=corporate_eid,
                                reason="repeated_dumping",
                                severity=100.0,
                                source_event="historical_conflict_seed",
                                evidence_key=f"historical-war:{evidence['evidence_key']}",
                                anchor=evidence["anchor"],
                                instigator_org_eid=corporate_eid,
                                force_war=True,
                            )
                if last is not None:
                    synced.append((_pair_key(community_eid, corporate_eid), last))
    return tuple(synced)


class OrganizationWarSystem(System):
    """Event-driven war escalation plus a sparse cooling/sync pulse."""

    def __init__(self, sim, refresh_interval=ORGANIZATION_WAR_SYNC_INTERVAL):
        super().__init__(sim)
        self.refresh_interval = max(120, _safe_int(refresh_interval, ORGANIZATION_WAR_SYNC_INTERVAL))
        self._next_refresh_tick = 0
        self.order_refresh_interval = ORGANIZATION_WAR_ORDER_REFRESH_INTERVAL
        self._next_order_refresh_tick = 0
        self.sim.events.subscribe("contamination_released", self.on_contamination_released)
        self.sim.events.subscribe("property_tamper", self.on_property_tamper)
        self.sim.events.subscribe("corporate_occupation_disrupted", self.on_corporate_occupation_disrupted)
        self.sim.events.subscribe("entity_damaged", self.on_entity_damaged)
        self.sim.events.subscribe("npc_killed", self.on_npc_killed)

    def _community_memberships(self, actor_eid):
        return tuple(sorted(
            root
            for root in {
                _organization_root(self.sim, row.get("organization_eid"))
                for row in actor_org_memberships(self.sim, actor_eid, active_only=True)
            }
            if root is not None and _is_underground_community(self.sim, root)
        ))

    def _player_side_witnesses(self, front, beneficiary_org_eid):
        player_eid = _safe_int(getattr(self.sim, "player_eid", 0), 0)
        pos = self.sim.ecs.get(Position).get(player_eid)
        if player_eid <= 0 or pos is None:
            return ()
        return _front_side_witnesses(
            self.sim,
            war_id=front.get("war_id"),
            front_id=front.get("front_id"),
            organization_eid=beneficiary_org_eid,
            x=pos.x,
            y=pos.y,
            z=pos.z,
        )

    def _record_player_asset_intervention(self, event):
        player_eid = _safe_int(getattr(self.sim, "player_eid", 0), 0)
        if player_eid <= 0 or _safe_int(event.data.get("offender_eid"), 0) != player_eid:
            return ()
        property_id = _text(event.data.get("property_id"))
        if not property_id:
            return ()
        prop = getattr(self.sim, "properties", {}).get(property_id)
        if not isinstance(prop, dict):
            return ()
        z = _safe_int(event.data.get("z"), _safe_int(prop.get("z"), 0))
        contributions = []
        for front in organization_war_front_rows(
            self.sim,
            property_id=property_id,
            z=z,
            active_only=True,
        ):
            participants = tuple(_safe_int(value, 0) for value in tuple(front.get("participant_org_eids", ()) or ()))
            asset_side = _front_participant_property_side(self.sim, front, participants, property_id)
            beneficiary = next((eid for eid in participants if eid != asset_side), None) if asset_side is not None else None
            if beneficiary is None:
                continue
            kind = {
                "signal_front": "relay_sabotage",
                "route_control": "route_asset_sabotage",
                "remediation_line": "remediation_asset_sabotage",
                "reprisal_line": "reprisal_asset_sabotage",
            }.get(_key(front.get("front_kind")), "front_asset_sabotage")
            severity = max(1.0, min(12.0, _safe_float(event.data.get("severity_score"), 20.0) / 8.0))
            contribution = record_organization_war_contribution(
                self.sim,
                front.get("war_id"),
                front.get("front_id"),
                actor_eid=player_eid,
                beneficiary_org_eid=beneficiary,
                contribution_kind=kind,
                magnitude=severity,
                source_event="property_tamper",
                evidence_key=(
                    f"player-front-asset:{player_eid}:{property_id}:"
                    f"{_safe_int(getattr(self.sim, 'tick', 0), 0) // 30}"
                ),
                observed_by_eids=self._player_side_witnesses(front, beneficiary),
            )
            if contribution is not None:
                contributions.append(contribution)
        return tuple(contributions)

    def on_contamination_released(self, event):
        corporate = _safe_int(
            event.data.get("source_organization_eid")
            or event.data.get("accountable_organization_eid")
            or event.data.get("corporate_organization_eid"),
            0,
        )
        if corporate <= 0 or not _is_corporate_organization(self.sim, corporate):
            return
        linked = getattr(self.sim, "properties", {}).get(_text(event.data.get("linked_property_id")))
        chunk = _chunk_tuple(event.data.get("chunk"))
        if chunk is None and event.data.get("x") is not None and event.data.get("y") is not None:
            chunk = tuple(self.sim.chunk_coords(_safe_int(event.data.get("x"), 0), _safe_int(event.data.get("y"), 0)))
        communities = _communities_for_property(self.sim, linked) if isinstance(linked, dict) else _communities_for_chunk(self.sim, chunk)
        severity = min(72.0, 30.0 + (_safe_float(event.data.get("contamination_load"), 1.0) * 8.0) + (_safe_float(event.data.get("technology_grade"), 1.0) * 4.0))
        for community in communities:
            record_organization_tension(
                self.sim,
                org_a_eid=community,
                org_b_eid=corporate,
                reason="toxic_discharge",
                severity=severity,
                source_event="contamination_released",
                evidence_key=_text(event.data.get("release_id")) or f"release:{getattr(self.sim, 'tick', 0)}:{community}:{corporate}",
                property_id=event.data.get("linked_property_id"),
                chunk=chunk,
                x=event.data.get("x"),
                y=event.data.get("y"),
                z=event.data.get("z", -1),
                instigator_org_eid=corporate,
            )

    def on_property_tamper(self, event):
        self._record_player_asset_intervention(event)
        corporate = _safe_int(event.data.get("suspected_source_organization_eid"), 0)
        if corporate <= 0 or not _is_corporate_organization(self.sim, corporate):
            return
        prop = getattr(self.sim, "properties", {}).get(_text(event.data.get("property_id")))
        for community in _communities_for_property(self.sim, prop):
            severity = max(10.0, min(58.0, _safe_float(event.data.get("severity_score"), 20.0) * 0.75))
            record_organization_tension(
                self.sim,
                org_a_eid=community,
                org_b_eid=corporate,
                reason="corporate_sabotage",
                severity=severity,
                source_event="property_tamper",
                evidence_key=f"tamper:{getattr(self.sim, 'tick', 0)}:{event.data.get('property_id')}:{event.data.get('offender_eid')}",
                anchor=_anchor_from_property(self.sim, prop),
                instigator_org_eid=corporate,
            )

    def on_corporate_occupation_disrupted(self, event):
        corporate = _safe_int(event.data.get("organization_eid"), 0)
        source_eid = _safe_int(event.data.get("eid"), 0)
        if corporate <= 0 or source_eid <= 0:
            return
        if source_eid == _safe_int(getattr(self.sim, "player_eid", 0), 0):
            property_id = _text(event.data.get("source_property_id"))
            prop = getattr(self.sim, "properties", {}).get(property_id)
            if isinstance(prop, dict):
                exact_fronts = list(organization_war_front_rows(
                    self.sim,
                    property_id=property_id,
                    z=_safe_int(prop.get("z"), 0),
                    active_only=True,
                ))
                if not exact_fronts:
                    chunk = _chunk_tuple(event.data.get("chunk")) or _property_chunk(self.sim, prop)
                    local_communities = set(_communities_for_chunk(self.sim, chunk))
                    corporate_root = _organization_root(self.sim, corporate)
                    for war in organization_war_rows(
                        self.sim,
                        organization_eid=corporate_root,
                        active_only=True,
                    ):
                        participants = tuple(_safe_int(value, 0) for value in tuple(war.get("participant_org_eids", ()) or ()))
                        if not any(eid in local_communities for eid in participants):
                            continue
                        record_organization_war_event(
                            self.sim,
                            war.get("war_id"),
                            event_kind="signal_sabotage",
                            severity=max(2.0, min(8.0, _safe_float(event.data.get("disruption"), 0.0) * 2.0)),
                            source_event="corporate_occupation_disrupted",
                            evidence_key=(
                                f"player-occupation-front:{source_eid}:{property_id}:"
                                f"{_safe_int(getattr(self.sim, 'tick', 0), 0)}"
                            ),
                            property_id=property_id,
                        )
                    exact_fronts = list(organization_war_front_rows(
                        self.sim,
                        property_id=property_id,
                        z=_safe_int(prop.get("z"), 0),
                        active_only=True,
                    ))
                for front in exact_fronts:
                    participants = tuple(_safe_int(value, 0) for value in tuple(front.get("participant_org_eids", ()) or ()))
                    corporate_root = _organization_root(self.sim, corporate)
                    beneficiary = next((
                        eid for eid in participants
                        if eid != corporate_root and _is_underground_community(self.sim, eid)
                    ), None)
                    if beneficiary is None or corporate_root not in participants:
                        continue
                    amount = max(2.0, min(12.0, 2.0 + (_safe_float(event.data.get("disruption"), 0.0) * 2.0)))
                    record_organization_war_contribution(
                        self.sim,
                        front.get("war_id"),
                        front.get("front_id"),
                        actor_eid=source_eid,
                        beneficiary_org_eid=beneficiary,
                        contribution_kind="occupation_disruption",
                        magnitude=amount,
                        source_event="corporate_occupation_disrupted",
                        evidence_key=(
                            f"player-front-asset:{source_eid}:{property_id}:"
                            f"{_safe_int(getattr(self.sim, 'tick', 0), 0) // 30}"
                        ),
                        observed_by_eids=self._player_side_witnesses(front, beneficiary),
                    )
        for community in self._community_memberships(source_eid):
            record_organization_tension(
                self.sim,
                org_a_eid=community,
                org_b_eid=corporate,
                reason="signal_sabotage",
                severity=32.0,
                source_event="corporate_occupation_disrupted",
                evidence_key=f"occupation-disruption:{getattr(self.sim, 'tick', 0)}:{event.data.get('source_property_id')}:{source_eid}",
                property_id=event.data.get("source_property_id"),
                chunk=event.data.get("chunk"),
                instigator_org_eid=community,
            )

    def on_entity_damaged(self, event):
        player_eid = _safe_int(getattr(self.sim, "player_eid", 0), 0)
        if player_eid <= 0 or _safe_int(event.data.get("source_eid"), 0) != player_eid:
            return
        target_eid = _safe_int(event.data.get("target_eid"), 0)
        order = actor_war_order(self.sim, target_eid, active_only=True)
        if not isinstance(order, dict):
            return
        war = organization_war_snapshot(self.sim, order.get("war_id"))
        if not isinstance(war, dict) or _key(war.get("status")) != "active":
            return
        front = next((
            row for row in tuple(war.get("fronts", ()) or ())
            if _text(row.get("front_id")) == _text(order.get("front_id"))
        ), None)
        if not isinstance(front, dict) or _key(front.get("status")) == "quiet":
            return
        front = {
            **dict(front),
            "war_id": war.get("war_id"),
            "participant_org_eids": war.get("participant_org_eids"),
        }
        beneficiary = _safe_int(order.get("opponent_org_eid"), 0)
        damage = max(1.0, _safe_float(event.data.get("damage"), 1.0))
        max_hp = max(1.0, _safe_float(event.data.get("max_hp"), 100.0))
        amount = max(0.5, min(8.0, (damage / max_hp) * 24.0))
        record_organization_war_contribution(
            self.sim,
            war.get("war_id"),
            front.get("front_id"),
            actor_eid=player_eid,
            beneficiary_org_eid=beneficiary,
            contribution_kind="front_combat_support",
            magnitude=amount,
            source_event="entity_damaged",
            evidence_key=(
                f"player-front-damage:{player_eid}:{target_eid}:"
                f"{_safe_int(getattr(self.sim, 'tick', 0), 0) // 12}"
            ),
            observed_by_eids=self._player_side_witnesses(front, beneficiary),
        )

    def on_npc_killed(self, event):
        target_orgs = tuple(_safe_int(value, 0) for value in tuple(event.data.get("target_organization_eids", ()) or ()))
        source_orgs = tuple(_safe_int(value, 0) for value in tuple(event.data.get("source_organization_eids", ()) or ()))
        if not target_orgs or not source_orgs:
            return
        for target_org in target_orgs:
            for source_org in source_orgs:
                target_root = _organization_root(self.sim, target_org)
                source_root = _organization_root(self.sim, source_org)
                if not target_root or not source_root:
                    continue
                if not (
                    (_is_corporate_organization(self.sim, target_root) and _is_underground_community(self.sim, source_root))
                    or (_is_underground_community(self.sim, target_root) and _is_corporate_organization(self.sim, source_root))
                ):
                    continue
                record_organization_tension(
                    self.sim,
                    org_a_eid=target_root,
                    org_b_eid=source_root,
                    reason="member_killed",
                    severity=72.0,
                    source_event="npc_killed",
                    evidence_key=f"war-killing:{event.data.get('target_eid')}:{getattr(self.sim, 'tick', 0)}",
                    x=event.data.get("x"),
                    y=event.data.get("y"),
                    z=event.data.get("z", 0),
                    instigator_org_eid=source_root,
                )

    def update(self):
        now = _safe_int(getattr(self.sim, "tick", 0), 0)
        active_chunk = _chunk_tuple(getattr(self.sim, "active_chunk_coord", None))
        if now >= self._next_order_refresh_tick:
            self._next_order_refresh_tick = now + self.order_refresh_interval
            if active_chunk is not None:
                refresh_organization_war_orders(self.sim, chunk=active_chunk, current_tick=now)
        if now >= self._next_refresh_tick:
            self._next_refresh_tick = now + self.refresh_interval
            if active_chunk is not None:
                sync_underground_corporate_tensions(self.sim, chunk=active_chunk, limit=8)
            advance_organization_wars(self.sim, current_tick=now)


__all__ = [
    "ORGANIZATION_WAR_COMBAT_ROLES",
    "ORGANIZATION_WAR_SCHEMA_VERSION",
    "ORGANIZATION_WAR_MOVEMENT_STATES",
    "OrganizationWarSystem",
    "actor_war_order",
    "actor_war_order_intent",
    "actor_war_alignment",
    "advance_organization_wars",
    "ensure_organization_war_state",
    "organization_tension_rows",
    "organization_tension_snapshot",
    "organization_war_for_pair",
    "organization_war_front_rows",
    "organization_war_front_summary",
    "organization_war_order_rows",
    "organization_war_rows",
    "organization_war_snapshot",
    "record_organization_tension",
    "record_organization_war_contribution",
    "record_organization_war_event",
    "refresh_organization_war_orders",
    "start_organization_war",
    "sync_underground_corporate_tensions",
    "war_chatter_payload_for_actor",
]
