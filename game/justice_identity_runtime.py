"""Persistent justice leads whose subject may not yet be identified.

Canonical incidents may retain actor eids so the simulation can continue, but
justice consequences must be driven by what authorities were actually told.
This runtime stores those subjective reports separately and resolves a case to
an actor only when a reporter supplies firsthand recognition or verification.
"""

from __future__ import annotations

from copy import deepcopy

from game.components import IncidentKnowledge, Position
from game.identity_evidence import (
    description_match_score,
    description_match_for_actor,
    preferred_subject_account,
    subject_account_conflict_read,
)
from game.justice_runtime import jurisdiction_for_position


MAX_REPORTS_PER_CASE = 12
MAX_PROVISIONAL_ATTRIBUTIONS_PER_CASE = 12
MAX_CONTRADICTORY_REPORTS_PER_CASE = 12
PROVISIONAL_MAX_AGE_TICKS = 24
PROVISIONAL_MAX_SCENE_DISTANCE = 6
PROVISIONAL_MIN_SEVERITY = 35
PROVISIONAL_MIN_MATCH_SCORE = 0.92
PROVISIONAL_MIN_EVIDENCE_WEIGHT = 0.32
PROVISIONAL_MIN_MATCHED_CUES = 2
SUSPICION_MAX_AGE_TICKS = 240
SUSPICION_MAX_SCENE_DISTANCE = 12
SUSPICION_MIN_SEVERITY = 24
SUSPICION_MIN_MATCH_SCORE = 0.70
SUSPICION_MIN_EVIDENCE_WEIGHT = 0.20
SUSPICION_MIN_MATCHED_CUES = 1
ADJUDICATION_MIN_MATCH_SCORE = 0.84
ADJUDICATION_MIN_EVIDENCE_WEIGHT = 0.28
ADJUDICATION_MIN_MATCHED_CUES = 2
ADJUDICATION_MIN_STRENGTH = 0.78


def _text(value):
    return str(value or "").strip()


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def justice_identity_state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    state = traits.get("justice_identity_cases")
    if not isinstance(state, dict):
        state = {}
        traits["justice_identity_cases"] = state
    if not isinstance(state.get("cases"), dict):
        state["cases"] = {}
    state.setdefault("version", 1)
    return state


def justice_case_for_incident(sim, incident_id):
    try:
        key = str(int(incident_id))
    except (TypeError, ValueError):
        return None
    case = justice_identity_state(sim)["cases"].get(key)
    return case if isinstance(case, dict) else None


def subject_account_resolves_identity(account):
    """Return the recognized actor only for a supported firsthand account."""

    if not isinstance(account, dict):
        return None
    identification = _text(account.get("identification")).lower()
    if identification not in {"recognized", "verified"}:
        return None
    suspect_eid = account.get("suspect_eid")
    try:
        suspect_eid = int(suspect_eid)
    except (TypeError, ValueError):
        return None
    if suspect_eid <= 0:
        return None
    minimum = 0.5 if identification == "recognized" else 0.9
    if _float(account.get("identity_confidence"), 0.0) < minimum:
        return None
    return suspect_eid


def independent_supporting_reporter_eids(case):
    """Return unique reporters who supplied materially matching subject detail."""

    if not isinstance(case, dict):
        return ()
    best = case.get("best_subject_account") if isinstance(case.get("best_subject_account"), dict) else {}
    best_description = best.get("description") if isinstance(best.get("description"), dict) else {}
    if not best_description:
        return ()
    reporters = set()
    for row in tuple(case.get("reports", ()) or ()):
        if not isinstance(row, dict):
            continue
        reporter_eid = _int(row.get("reporter_eid"), -1)
        account = row.get("subject_account") if isinstance(row.get("subject_account"), dict) else {}
        description = account.get("description") if isinstance(account.get("description"), dict) else {}
        if reporter_eid < 0 or not description:
            continue
        match = description_match_score(best_description, description)
        if (
            float(match.get("score", 0.0) or 0.0) >= 0.62
            and float(match.get("evidence_weight", 0.0) or 0.0) >= 0.20
            and not subject_account_conflict_read(best, account).get("conflicted", False)
        ):
            reporters.add(reporter_eid)
    return tuple(sorted(reporters))


def _report_signature(reporter_eid, method, account):
    transmission = account.get("transmission") if isinstance(account.get("transmission"), dict) else {}
    observation = account.get("observation") if isinstance(account.get("observation"), dict) else {}
    return (
        _int(reporter_eid, -1),
        _text(method).lower(),
        _text(account.get("identification")).lower(),
        account.get("suspect_eid"),
        _text(account.get("presented_name")).lower(),
        _int(observation.get("tick"), -1),
        _int(transmission.get("propagation_depth"), 0),
    )


def record_justice_identity_report(sim, incident, report_data):
    """Add a formal report and return ``(case, changed, newly_resolved)``."""

    if not isinstance(incident, dict) or not isinstance(report_data, dict):
        return None, False, False
    incident_id = incident.get("id", report_data.get("incident_id"))
    try:
        incident_id = int(incident_id)
    except (TypeError, ValueError):
        return None, False, False

    tick = _int(getattr(sim, "tick", 0), 0)
    x = incident.get("x", report_data.get("x"))
    y = incident.get("y", report_data.get("y"))
    z = incident.get("z", report_data.get("z", 0))
    jurisdiction = jurisdiction_for_position(sim, x=x, y=y)
    state = justice_identity_state(sim)
    key = str(incident_id)
    case = state["cases"].get(key)
    if not isinstance(case, dict):
        case = {
            "case_id": f"incident:{incident_id}",
            "incident_id": incident_id,
            "opened_tick": tick,
            "incident_tick": _int(incident.get("created_tick", incident.get("tick", tick)), tick),
            "updated_tick": tick,
            "status": "unresolved",
            "factual_incident": True,
            "kind": _text(incident.get("kind")).lower(),
            "action": _text(incident.get("action")).lower(),
            "context": _text(incident.get("context")).lower(),
            "merge_subject": _text(incident.get("merge_subject")).lower(),
            "severity": max(0, _int(incident.get("severity"), 0)),
            "property_id": _text(incident.get("property_id")),
            "x": x,
            "y": y,
            "z": z,
            "jurisdiction_key": _text(jurisdiction.get("key")).lower(),
            "jurisdiction_name": _text(jurisdiction.get("name")) or "Justice Office",
            "reports": [],
            "best_subject_account": {},
            "resolved_subject_eid": None,
            "resolution_basis": "",
            "resolved_tick": None,
            "provisional_attributions": [],
            "contradictory_reports": [],
            "report_conflict_count": 0,
            "evidence_posture": "open",
        }
        state["cases"][key] = case

    account = deepcopy(report_data.get("subject_account")) if isinstance(report_data.get("subject_account"), dict) else {
        "identification": "unknown",
        "suspect_eid": None,
        "presented_name": "",
        "identity_confidence": 0.0,
        "description": {},
        "observation": {},
    }
    reporter_eid = report_data.get("reporter_eid", report_data.get("npc_eid"))
    method = _text(report_data.get("method")).lower()
    signature = _report_signature(reporter_eid, method, account)
    existing_signatures = {
        tuple(row.get("signature", ()))
        for row in tuple(case.get("reports", ()) or ())
        if isinstance(row, dict)
    }
    changed = signature not in existing_signatures
    if changed:
        conflicts = []
        for previous in tuple(case.get("reports", ()) or ()):
            if not isinstance(previous, dict):
                continue
            previous_account = previous.get("subject_account")
            conflict = subject_account_conflict_read(previous_account, account)
            if conflict.get("conflicted"):
                conflicts.append({
                    "tick": tick,
                    "earlier_reporter_eid": _int(previous.get("reporter_eid"), -1),
                    "incoming_reporter_eid": _int(reporter_eid, -1),
                    "earlier_signature": tuple(previous.get("signature", ()) or ()),
                    "incoming_signature": signature,
                    **conflict,
                })
        report = {
            "reported_tick": tick,
            "reporter_eid": _int(reporter_eid, -1),
            "method": method,
            "subject_account": account,
            "signature": signature,
        }
        reports = list(case.get("reports", ()) or ())
        reports.append(report)
        case["reports"] = reports[-MAX_REPORTS_PER_CASE:]
        case["updated_tick"] = tick
        case["best_subject_account"] = preferred_subject_account(
            case.get("best_subject_account"),
            account,
        )
        if conflicts:
            contradictory = list(case.get("contradictory_reports", ()) or ())
            known_pairs = {
                (tuple(row.get("earlier_signature", ()) or ()), tuple(row.get("incoming_signature", ()) or ()))
                for row in contradictory
                if isinstance(row, dict)
            }
            for row in conflicts:
                pair = (tuple(row.get("earlier_signature", ()) or ()), tuple(row.get("incoming_signature", ()) or ()))
                if pair not in known_pairs:
                    contradictory.append(row)
                    known_pairs.add(pair)
            case["contradictory_reports"] = contradictory[-MAX_CONTRADICTORY_REPORTS_PER_CASE:]
            case["report_conflict_count"] = len(case["contradictory_reports"])
            case["evidence_posture"] = "contested"
        elif max(0, _int(case.get("report_conflict_count"), 0)) <= 0:
            case["evidence_posture"] = (
                "corroborated"
                if len(independent_supporting_reporter_eids(case)) >= 2
                else "open"
            )

    newly_resolved = False
    resolved_eid = subject_account_resolves_identity(account)
    if resolved_eid is not None and case.get("resolved_subject_eid") is None:
        case["resolved_subject_eid"] = resolved_eid
        case["resolution_basis"] = _text(account.get("identification")).lower()
        case["resolved_tick"] = tick
        case["status"] = "resolved"
        case["updated_tick"] = tick
        provisional_rows = [
            row
            for row in tuple(case.get("provisional_attributions", ()) or ())
            if isinstance(row, dict) and str(row.get("status", "active") or "active").strip().lower() == "active"
        ]
        misidentified_actor_eids = []
        provisional_confirmed = False
        for row in provisional_rows:
            row["canonical_identity_resolved"] = True
            if _int(row.get("actor_eid"), -1) == int(resolved_eid):
                row["status"] = "confirmed"
                if _text(row.get("adjudication_status")).lower() == "convicted_on_evidence":
                    row["adjudication_status"] = "conviction_confirmed"
                row["resolved_tick"] = tick
                case["provisional_confirmation"] = True
                provisional_confirmed = True
            else:
                row["status"] = "misidentified_pending_capture"
                if _text(row.get("adjudication_status")).lower() == "convicted_on_evidence":
                    row["adjudication_status"] = "conviction_contested_by_identification"
                row["resolved_tick"] = tick
                case["misidentification_confirmed"] = True
                case["misidentified_actor_eid"] = _int(row.get("actor_eid"), -1)
                case["misidentification_confirmed_tick"] = tick
                misidentified_actor_eids.append(_int(row.get("actor_eid"), -1))
        for row in tuple(case.get("evidentiary_convictions", ()) or ()):
            if not isinstance(row, dict) or _text(row.get("status") or "active").lower() != "active":
                continue
            row["status"] = "confirmed" if _int(row.get("actor_eid"), -1) == int(resolved_eid) else "misidentified_pending_capture"
            row["resolved_tick"] = tick
            row["resolved_subject_eid"] = int(resolved_eid)
        if misidentified_actor_eids:
            case["misidentified_actor_eids"] = tuple(dict.fromkeys(misidentified_actor_eids))
            case["provisional_status"] = "misidentified"
            case["institutional_error"] = True
            case["correction_status"] = "pending_actual_offender_capture"
            case["correction_required_tick"] = tick
        elif provisional_confirmed:
            case["provisional_status"] = "confirmed"
        newly_resolved = True
        changed = True
    return case, changed, newly_resolved


def resolved_subject_for_incident(sim, incident_id):
    case = justice_case_for_incident(sim, incident_id)
    if not isinstance(case, dict):
        return None
    try:
        resolved = int(case.get("resolved_subject_eid"))
    except (TypeError, ValueError):
        return None
    return resolved if resolved > 0 else None


def event_evidence_resolves_subject(sim, event_or_data, subject_eid):
    """Return whether this event's communicated evidence identifies a subject."""

    data = getattr(event_or_data, "data", event_or_data)
    if not isinstance(data, dict):
        return False
    try:
        subject_eid = int(subject_eid)
    except (TypeError, ValueError):
        return False
    incident_id = data.get("knowledge_incident_id", data.get("incident_id"))
    resolved = resolved_subject_for_incident(sim, incident_id)
    if resolved is not None:
        return int(resolved) == subject_eid

    direct_account = data.get("subject_account")
    if subject_account_resolves_identity(direct_account) == subject_eid:
        return True
    for raw_observer_eid in tuple(data.get("accountable_observer_eids", data.get("observer_eids", ())) or ()):
        try:
            observer_eid = int(raw_observer_eid)
            knowledge = sim.ecs.get(IncidentKnowledge).get(observer_eid)
            record = knowledge.records.get(int(incident_id)) if knowledge is not None and incident_id is not None else None
        except (TypeError, ValueError):
            continue
        account = (record or {}).get("subject_account") if isinstance((record or {}).get("subject_account"), dict) else None
        if subject_account_resolves_identity(account) == subject_eid:
            return True
    return False


def unresolved_justice_cases(sim, *, jurisdiction_key=""):
    wanted = _text(jurisdiction_key).lower()
    rows = []
    for case in justice_identity_state(sim)["cases"].values():
        if not isinstance(case, dict) or case.get("status") != "unresolved":
            continue
        if wanted and _text(case.get("jurisdiction_key")).lower() != wanted:
            continue
        rows.append(case)
    rows.sort(key=lambda row: (-_int(row.get("severity"), 0), -_int(row.get("updated_tick"), 0), _text(row.get("case_id"))))
    return tuple(rows)


def unresolved_case_matches_for_actor(sim, actor_eid, *, jurisdiction_key="", minimum_score=0.62):
    """Return plausible description leads for an actor, strongest first."""

    rows = []
    for case in unresolved_justice_cases(sim, jurisdiction_key=jurisdiction_key):
        account = case.get("best_subject_account") if isinstance(case.get("best_subject_account"), dict) else {}
        description = account.get("description") if isinstance(account.get("description"), dict) else {}
        match = description_match_for_actor(sim, description, actor_eid)
        if not match.get("plausible") or _float(match.get("score"), 0.0) < float(minimum_score):
            continue
        rows.append({"case": case, "match": match})
    rows.sort(key=lambda row: (
        -_float(row["match"].get("score"), 0.0),
        -_float(row["match"].get("evidence_weight"), 0.0),
        -_int(row["case"].get("severity"), 0),
        -_int(row["case"].get("updated_tick"), 0),
    ))
    return tuple(rows)


def provisional_attribution_read(sim, case, actor_eid, *, match=None):
    """Measure whether a factual unresolved case can support a fallible arrest.

    Detention and conviction deliberately use different thresholds.  A nearby
    person who mostly matches an actionable report can be detained on
    reasonable suspicion; booking needs stronger corroboration.  Neither path
    resolves canonical identity, and consistent misinformation can therefore
    still produce a wrongful result.
    """

    result = {
        "eligible": False,
        "detainable": False,
        "factual_incident": False,
        "age_ticks": None,
        "scene_distance": None,
        "same_level": False,
        "severity": 0,
        "match_score": 0.0,
        "evidence_weight": 0.0,
        "matched_cues": (),
        "conflicting_cues": (),
        "contextual_cues": (),
        "evidence_strength": 0.0,
        "adjudication_strength": 0.0,
        "convictable": False,
        "detention_reasons": (),
        "adjudication_reasons": (),
        "reasons": (),
    }
    if not isinstance(case, dict) or _text(case.get("status")).lower() != "unresolved":
        result["reasons"] = ("case_not_unresolved",)
        return result
    if not bool(case.get("factual_incident", False)) or case.get("incident_id") is None:
        result["reasons"] = ("no_factual_incident",)
        return result
    result["factual_incident"] = True
    if not bool(case.get("provisional_crime_actionable", False)):
        result["reasons"] = ("crime_not_factually_actionable",)
        return result

    actor_pos = sim.ecs.get(Position).get(actor_eid)
    if actor_pos is None:
        result["reasons"] = ("actor_not_realized",)
        return result
    try:
        case_x = int(case.get("x"))
        case_y = int(case.get("y"))
        case_z = int(case.get("z", 0) or 0)
    except (TypeError, ValueError):
        result["reasons"] = ("scene_location_unknown",)
        return result

    tick = _int(getattr(sim, "tick", 0), 0)
    incident_tick = _int(case.get("incident_tick", case.get("opened_tick", tick)), tick)
    age_ticks = max(0, tick - incident_tick)
    same_level = int(actor_pos.z) == case_z
    distance = abs(int(actor_pos.x) - case_x) + abs(int(actor_pos.y) - case_y) if same_level else 10_000
    result["age_ticks"] = age_ticks
    result["scene_distance"] = distance
    result["same_level"] = same_level

    if not isinstance(match, dict):
        account = case.get("best_subject_account") if isinstance(case.get("best_subject_account"), dict) else {}
        description = account.get("description") if isinstance(account.get("description"), dict) else {}
        match = description_match_for_actor(sim, description, actor_eid)
    score = _float(match.get("score"), 0.0)
    evidence_weight = _float(match.get("evidence_weight"), 0.0)
    matched_cues = tuple(match.get("matched_cues", ()) or ())
    conflicting_cues = tuple(match.get("conflicting_cues", ()) or ())
    contextual_cues = tuple(match.get("contextual_cues", ()) or ())
    crime_profile = case.get("provisional_crime_profile") if isinstance(case.get("provisional_crime_profile"), dict) else {}
    severity = max(0, _int(crime_profile.get("severity", case.get("severity")), 0))
    result.update({
        "severity": severity,
        "match_score": score,
        "evidence_weight": evidence_weight,
        "matched_cues": matched_cues,
        "conflicting_cues": conflicting_cues,
        "contextual_cues": contextual_cues,
    })

    reasons = []
    if max(0, _int(case.get("report_conflict_count"), 0)) > 0:
        reasons.append("contradictory_reports")
    if severity < PROVISIONAL_MIN_SEVERITY:
        reasons.append("crime_not_serious_enough")
    if age_ticks > PROVISIONAL_MAX_AGE_TICKS:
        reasons.append("not_immediate")
    if not same_level or distance > PROVISIONAL_MAX_SCENE_DISTANCE:
        reasons.append("not_near_scene")
    if score < PROVISIONAL_MIN_MATCH_SCORE:
        reasons.append("description_not_close_enough")
    if evidence_weight < PROVISIONAL_MIN_EVIDENCE_WEIGHT:
        reasons.append("description_too_sparse")
    if len(matched_cues) < PROVISIONAL_MIN_MATCHED_CUES:
        reasons.append("too_few_matching_cues")
    if conflicting_cues:
        reasons.append("description_contradiction")
    freshness = max(0.0, 1.0 - (float(age_ticks) / float(max(1, PROVISIONAL_MAX_AGE_TICKS))))
    proximity = max(0.0, 1.0 - (float(distance) / float(max(1, PROVISIONAL_MAX_SCENE_DISTANCE)))) if same_level else 0.0
    independent_report_count = len(independent_supporting_reporter_eids(case))
    report_support = min(1.0, float(independent_report_count) / 3.0)
    context_support = min(1.0, float(len(contextual_cues)) / 2.0)
    evidence_strength = (
        (score * 0.44)
        + (evidence_weight * 0.18)
        + (freshness * 0.14)
        + (proximity * 0.12)
        + (report_support * 0.06)
        + (context_support * 0.06)
    )
    result["reasons"] = tuple(reasons)
    result["eligible"] = not reasons
    result["evidence_strength"] = round(max(0.0, min(1.0, evidence_strength)), 3)
    result["independent_report_count"] = independent_report_count

    detention_reasons = []
    if severity < SUSPICION_MIN_SEVERITY:
        detention_reasons.append("crime_not_serious_enough_for_detention")
    if age_ticks > SUSPICION_MAX_AGE_TICKS:
        detention_reasons.append("reported_suspect_no_longer_nearby_in_time")
    if not same_level or distance > SUSPICION_MAX_SCENE_DISTANCE:
        detention_reasons.append("reported_suspect_no_longer_nearby")
    if score < SUSPICION_MIN_MATCH_SCORE:
        detention_reasons.append("description_not_close_enough_for_suspicion")
    if evidence_weight < SUSPICION_MIN_EVIDENCE_WEIGHT:
        detention_reasons.append("description_too_sparse_for_suspicion")
    if len(matched_cues) < SUSPICION_MIN_MATCHED_CUES:
        detention_reasons.append("no_matching_description_cue")
    if len(conflicting_cues) >= 2 or (conflicting_cues and score < 0.82):
        detention_reasons.append("close_contact_materially_contradicts_report")
    result["detention_reasons"] = tuple(detention_reasons)
    result["detainable"] = not detention_reasons

    authoritative_reporters = set()
    for report in tuple(case.get("reports", ()) or ()):
        if not isinstance(report, dict):
            continue
        account = report.get("subject_account") if isinstance(report.get("subject_account"), dict) else {}
        description = account.get("description") if isinstance(account.get("description"), dict) else {}
        observation = account.get("observation") if isinstance(account.get("observation"), dict) else {}
        basis = _text(observation.get("description_basis")).lower()
        if not description or not (
            bool(observation.get("durable_visual_reference", False))
            or basis in {"phone_photo", "expert_observation"}
        ):
            continue
        reporter_eid = _int(report.get("reporter_eid"), -1)
        authoritative_reporters.add(reporter_eid if reporter_eid > 0 else f"report:{len(authoritative_reporters)}")
    authoritative_report_count = len(authoritative_reporters)
    source_support = 1.0 if authoritative_report_count else 0.0
    adjudication_strength = (
        (score * 0.54)
        + (evidence_weight * 0.24)
        + (min(1.0, float(independent_report_count) / 2.0) * 0.12)
        + (source_support * 0.10)
    )
    adjudication_reasons = []
    if max(0, _int(case.get("report_conflict_count"), 0)) > 0:
        adjudication_reasons.append("materially_conflicting_statements")
    if score < ADJUDICATION_MIN_MATCH_SCORE:
        adjudication_reasons.append("description_match_below_booking_threshold")
    if evidence_weight < ADJUDICATION_MIN_EVIDENCE_WEIGHT:
        adjudication_reasons.append("description_evidence_below_booking_threshold")
    if len(matched_cues) < ADJUDICATION_MIN_MATCHED_CUES:
        adjudication_reasons.append("too_few_booking_cues")
    if conflicting_cues:
        adjudication_reasons.append("booking_description_contradiction")
    if independent_report_count < 2 and not contextual_cues and authoritative_report_count <= 0:
        adjudication_reasons.append("uncorroborated_statement")
    if adjudication_strength < ADJUDICATION_MIN_STRENGTH:
        adjudication_reasons.append("insufficient_total_booking_evidence")
    result["authoritative_report_count"] = authoritative_report_count
    result["adjudication_strength"] = round(max(0.0, min(1.0, adjudication_strength)), 3)
    result["adjudication_reasons"] = tuple(adjudication_reasons)
    result["convictable"] = not adjudication_reasons
    return result


def record_provisional_justice_attribution(
    sim,
    incident_id,
    *,
    actor_eid,
    officer_eid=None,
    match=None,
    read=None,
    disposition="provisional_suspect",
):
    """Persist an actor-neutral, explicitly fallible justice attribution."""

    case = justice_case_for_incident(sim, incident_id)
    if not isinstance(case, dict):
        return None
    read = read if isinstance(read, dict) else provisional_attribution_read(sim, case, actor_eid, match=match)
    if not bool(read.get("detainable", read.get("eligible", False))):
        return None
    tick = _int(getattr(sim, "tick", 0), 0)
    actor_id = _int(actor_eid, -1)
    for row in reversed(tuple(case.get("provisional_attributions", ()) or ())):
        if not isinstance(row, dict):
            continue
        if _int(row.get("actor_eid"), -2) == actor_id and _text(row.get("status") or "active").lower() == "active":
            return row
    row = {
        "tick": tick,
        "actor_eid": actor_id,
        "officer_eid": _int(officer_eid, -1),
        "status": "active",
        "disposition": _text(disposition).lower() or "provisional_suspect",
        "basis": "nearby_reported_description_match",
        "match": deepcopy(match) if isinstance(match, dict) else {},
        "read": deepcopy(read),
        "canonical_identity_resolved": False,
        "wrongful_risk": True,
        "evidence_strength": _float(read.get("evidence_strength"), 0.0),
        "adjudication_status": "convicted_on_evidence" if bool(read.get("convictable", False)) else "actionable_suspicion",
    }
    rows = list(case.get("provisional_attributions", ()) or ())
    rows.append(row)
    case["provisional_attributions"] = rows[-MAX_PROVISIONAL_ATTRIBUTIONS_PER_CASE:]
    case["provisional_subject_eid"] = actor_id
    case["provisional_tick"] = tick
    case["provisional_status"] = "active"
    if bool(read.get("convictable", False)):
        convictions = list(case.get("evidentiary_convictions", ()) or ())
        convictions.append({
            "tick": tick,
            "actor_eid": actor_id,
            "officer_eid": _int(officer_eid, -1),
            "evidence_strength": _float(read.get("evidence_strength"), 0.0),
            "wrongful_risk": True,
            "status": "active",
        })
        case["evidentiary_convictions"] = convictions[-MAX_PROVISIONAL_ATTRIBUTIONS_PER_CASE:]
    case["updated_tick"] = tick
    return row


def justice_case_recently_checked(case, actor_eid, *, current_tick=0, cooldown_ticks=360):
    if not isinstance(case, dict):
        return False
    actor_eid = _int(actor_eid, -1)
    current_tick = _int(current_tick, 0)
    for row in reversed(tuple(case.get("encounters", ()) or ())):
        if not isinstance(row, dict) or _int(row.get("actor_eid"), -2) != actor_eid:
            continue
        return current_tick - _int(row.get("tick"), -10_000) < max(1, _int(cooldown_ticks, 360))
    return False


def record_justice_case_encounter(
    sim,
    incident_id,
    *,
    actor_eid,
    officer_eid=None,
    choice_id="",
    outcome="noted",
    match=None,
    presented_name="",
):
    case = justice_case_for_incident(sim, incident_id)
    if not isinstance(case, dict):
        return None
    row = {
        "tick": _int(getattr(sim, "tick", 0), 0),
        "actor_eid": _int(actor_eid, -1),
        "officer_eid": _int(officer_eid, -1),
        "choice_id": _text(choice_id).lower(),
        "outcome": _text(outcome).lower() or "noted",
        "presented_name": _text(presented_name),
        "match": deepcopy(match) if isinstance(match, dict) else {},
    }
    encounters = list(case.get("encounters", ()) or ())
    encounters.append(row)
    case["encounters"] = encounters[-16:]
    case["updated_tick"] = row["tick"]
    if row["presented_name"]:
        candidates = list(case.get("candidate_leads", ()) or ())
        candidates.append({
            "actor_eid": row["actor_eid"],
            "presented_name": row["presented_name"],
            "source": "voluntary_identity_check",
            "tick": row["tick"],
            "match_score": _float((match or {}).get("score"), 0.0),
            "resolved_identity": False,
        })
        case["candidate_leads"] = candidates[-12:]
    return row


def justice_case_event_payload(case):
    if not isinstance(case, dict):
        return {}
    best = case.get("best_subject_account") if isinstance(case.get("best_subject_account"), dict) else {}
    return {
        "case_id": case.get("case_id"),
        "incident_id": case.get("incident_id"),
        "case_status": case.get("status", "unresolved"),
        "kind": case.get("kind", ""),
        "severity": case.get("severity", 0),
        "property_id": case.get("property_id", ""),
        "x": case.get("x"),
        "y": case.get("y"),
        "z": case.get("z"),
        "jurisdiction_key": case.get("jurisdiction_key", ""),
        "jurisdiction_name": case.get("jurisdiction_name", "Justice Office"),
        "factual_incident": bool(case.get("factual_incident", False)),
        "provisional_subject_eid": case.get("provisional_subject_eid"),
        "provisional_status": case.get("provisional_status", ""),
        "institutional_error": bool(case.get("institutional_error", False)),
        "correction_status": case.get("correction_status", ""),
        "misidentified_actor_eids": tuple(case.get("misidentified_actor_eids", ()) or ()),
        "resolved_subject_eid": case.get("resolved_subject_eid"),
        "subject_identification": best.get("identification", "unknown"),
        "subject_account": deepcopy(best),
        "report_count": len(tuple(case.get("reports", ()) or ())),
        "report_conflict_count": max(0, _int(case.get("report_conflict_count"), 0)),
        "evidence_posture": _text(case.get("evidence_posture")) or "open",
    }


__all__ = [
    "independent_supporting_reporter_eids",
    "justice_case_event_payload",
    "justice_case_for_incident",
    "justice_identity_state",
    "provisional_attribution_read",
    "record_justice_identity_report",
    "record_justice_case_encounter",
    "record_provisional_justice_attribution",
    "resolved_subject_for_incident",
    "event_evidence_resolves_subject",
    "subject_account_resolves_identity",
    "justice_case_recently_checked",
    "unresolved_case_matches_for_actor",
    "unresolved_justice_cases",
]
