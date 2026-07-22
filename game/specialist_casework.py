"""Evidence-gated wildlife and fire specialist casework.

Specialist referrals annotate an existing canonical incident.  They never make
a second crime, identify an unknown actor, or turn a simulated cause into an
eyewitness account.  Wildlife referrals consume the legality facts attached to
the reported hunt.  Fire referrals require a response worker's scene
assessment before origin facts become inspectable evidence.
"""

from __future__ import annotations

from engine.events import Event
from engine.visibility import has_line_of_sight

from game.civic_records import civic_license_record
from game.components import Position
from game.incident_runtime import (
    incident_record,
    incident_records,
    mark_incident_registry_changed,
)
from game.justice_identity_runtime import resolved_subject_for_incident


WILDLIFE_DOMAIN = "wildlife_enforcement"
FIRE_DOMAIN = "fire_investigation"

WILDLIFE_CASEWORK_KIND = "wildlife_enforcement_canvas"
FIRE_CASEWORK_KIND = "arson_investigation_canvas"

WILDLIFE_CAREER_TOKENS = (
    "wildlife_ranger",
    "wildlife_enforcement",
    "conservation_officer",
    "game_warden",
)
FIRE_INVESTIGATOR_CAREER_TOKENS = (
    "arson_investigator",
    "fire_investigator",
    "fire_inspector",
)

_WILDLIFE_CONTEXTS = {
    "unlicensed_hunting",
    "unsafe_hunting",
    "protected_wildlife_hunting",
}
_SUSPICIOUS_FIRE_SOURCES = {"explosion", "vehicle_explosion", "incendiary", "accelerant"}
_FORCED_ENTRY_ACTIONS = {"forced_breach", "wall_breach", "window_entry"}
_FORCED_ENTRY_METHODS = {"forced", "forced_breach", "breach", "pry", "wall_breach", "window_entry"}


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _text(value):
    return str(value or "").strip()


def _key(value):
    return _text(value).lower().replace(" ", "_")


def specialist_domain_for_career(career):
    career = _key(career)
    if any(token in career for token in WILDLIFE_CAREER_TOKENS):
        return WILDLIFE_DOMAIN
    if any(token in career for token in FIRE_INVESTIGATOR_CAREER_TOKENS):
        return FIRE_DOMAIN
    return ""


def specialist_casework_kind(domain):
    return {
        WILDLIFE_DOMAIN: WILDLIFE_CASEWORK_KIND,
        FIRE_DOMAIN: FIRE_CASEWORK_KIND,
    }.get(_key(domain), "investigator_canvas")


def specialist_response_role(domain):
    return {
        WILDLIFE_DOMAIN: "wildlife_enforcement_dispatched",
        FIRE_DOMAIN: "fire_investigator_dispatched",
    }.get(_key(domain), "peace_dispatched")


def specialist_referral(incident, domain):
    if not isinstance(incident, dict):
        return None
    referrals = incident.get("specialist_referrals")
    row = referrals.get(_key(domain)) if isinstance(referrals, dict) else None
    return row if isinstance(row, dict) else None


def _near_same_scene(left, right, *, radius=4, tick_window=180):
    if not isinstance(left, dict) or not isinstance(right, dict):
        return False
    left_property = _text(left.get("property_id"))
    right_property = _text(right.get("property_id"))
    if left_property and right_property and left_property == right_property:
        same_place = True
    else:
        if left.get("x") is None or left.get("y") is None or right.get("x") is None or right.get("y") is None:
            return False
        same_place = (
            _int(left.get("z"), 0) == _int(right.get("z"), 0)
            and abs(_int(left.get("x")) - _int(right.get("x")))
            + abs(_int(left.get("y")) - _int(right.get("y"))) <= int(radius)
        )
    left_tick = _int(left.get("last_observed_tick"), _int(left.get("created_tick"), 0))
    right_tick = _int(right.get("last_observed_tick"), _int(right.get("created_tick"), 0))
    return bool(same_place and abs(left_tick - right_tick) <= int(tick_window))


def _reported_forced_entry_evidence(sim, fire_incident):
    rows = []
    for incident in incident_records(sim):
        if incident is fire_incident or _key(incident.get("kind")) not in {"property_tamper", "property_trespass"}:
            continue
        if not bool(incident.get("officially_reported") or incident.get("accountable_observed")):
            continue
        action = _key(incident.get("action"))
        method = _key(incident.get("ingress_method"))
        tags = {_key(value) for value in tuple(incident.get("tags", ()) or ())}
        if not (
            action in _FORCED_ENTRY_ACTIONS
            or method in _FORCED_ENTRY_METHODS
            or bool(tags & (_FORCED_ENTRY_ACTIONS | _FORCED_ENTRY_METHODS))
        ):
            continue
        if not _near_same_scene(fire_incident, incident):
            continue
        rows.append({
            "incident_id": _int(incident.get("id"), -1),
            "basis": "reported_forced_entry",
        })
    rows.sort(key=lambda row: row["incident_id"])
    return tuple(rows)


def wildlife_referral_read(incident):
    if not isinstance(incident, dict):
        return {"eligible": False, "domain": WILDLIFE_DOMAIN, "evidence_codes": ()}
    context = _key(incident.get("context"))
    if context not in _WILDLIFE_CONTEXTS:
        return {"eligible": False, "domain": WILDLIFE_DOMAIN, "evidence_codes": ()}
    evidence = ["reported_hunt"]
    if context == "unlicensed_hunting" or _key(incident.get("hunting_license_status")) not in {"", "active"}:
        evidence.append("license_not_verified")
    if context == "unsafe_hunting":
        evidence.append("unsafe_hunt_location")
    if context == "protected_wildlife_hunting" or _key(incident.get("fauna_population_status")) in {"endangered", "protected", "extinct"}:
        evidence.append("protected_line")
    if bool(incident.get("cull_active")):
        evidence.append("active_cull_record")
    return {
        "eligible": True,
        "domain": WILDLIFE_DOMAIN,
        "casework_kind": WILDLIFE_CASEWORK_KIND,
        "evidence_codes": tuple(dict.fromkeys(evidence)),
        "reason": "reported hunting facts require wildlife-license and species review",
    }


def fire_referral_read(sim, incident):
    if not isinstance(incident, dict) or _key(incident.get("kind")) != "structure_fire":
        return {"eligible": False, "domain": FIRE_DOMAIN, "evidence_codes": ()}
    assessment = incident.get("fire_response_assessment")
    evidence = tuple(assessment.get("evidence_codes", ()) or ()) if isinstance(assessment, dict) else ()
    return {
        "eligible": bool(evidence),
        "domain": FIRE_DOMAIN,
        "casework_kind": FIRE_CASEWORK_KIND,
        "evidence_codes": tuple(dict.fromkeys(_key(value) for value in evidence if _key(value))),
        "reason": "fire-response scene evidence supports origin investigation" if evidence else "no response-scene basis for an arson referral",
    }


def specialist_referral_read(sim, incident):
    wildlife = wildlife_referral_read(incident)
    if wildlife.get("eligible"):
        return wildlife
    fire = fire_referral_read(sim, incident)
    if fire.get("eligible"):
        return fire
    return None


def record_specialist_referral(sim, incident, read, *, source="authority_report"):
    if not isinstance(incident, dict) or not isinstance(read, dict) or not bool(read.get("eligible")):
        return None
    domain = _key(read.get("domain"))
    if not domain:
        return None
    referrals = incident.get("specialist_referrals")
    if not isinstance(referrals, dict):
        referrals = {}
        incident["specialist_referrals"] = referrals
    existing = referrals.get(domain)
    if isinstance(existing, dict):
        combined = list(tuple(existing.get("evidence_codes", ()) or ()))
        for code in tuple(read.get("evidence_codes", ()) or ()):
            code = _key(code)
            if code and code not in combined:
                combined.append(code)
        existing["evidence_codes"] = tuple(combined)
        existing["updated_tick"] = _int(getattr(sim, "tick", 0), 0)
        mark_incident_registry_changed(sim)
        return existing
    tick = _int(getattr(sim, "tick", 0), 0)
    row = {
        "domain": domain,
        "casework_kind": _key(read.get("casework_kind")) or specialist_casework_kind(domain),
        "status": "referred",
        "reason": _text(read.get("reason")),
        "evidence_codes": tuple(dict.fromkeys(_key(value) for value in tuple(read.get("evidence_codes", ()) or ()) if _key(value))),
        "source_incident_id": _int(incident.get("id"), -1),
        "source": _key(source) or "authority_report",
        "referred_tick": tick,
        "updated_tick": tick,
    }
    referrals[domain] = row
    mark_incident_registry_changed(sim)
    sim.emit(Event(
        "incident_specialist_referred",
        incident_id=incident.get("id"),
        domain=domain,
        casework_kind=row["casework_kind"],
        evidence_codes=row["evidence_codes"],
        x=incident.get("x"),
        y=incident.get("y"),
        z=incident.get("z", 0),
        property_id=incident.get("property_id"),
    ))
    return row


def assess_fire_response_scene(sim, incident_id, responder_eid, *, x=None, y=None, z=None):
    """Convert physically inspectable response-scene cues into referral evidence."""

    incident = incident_record(sim, incident_id)
    if not isinstance(incident, dict) or _key(incident.get("kind")) != "structure_fire":
        return None
    origins = tuple(row for row in tuple(incident.get("fire_origin_observations", ()) or ()) if isinstance(row, dict))
    source_kinds = {_key(row.get("source_kind")) for row in origins}
    origin_keys = {
        (
            _key(row.get("source_kind")),
            _int(row.get("origin_x"), _int(row.get("x"), 0)),
            _int(row.get("origin_y"), _int(row.get("y"), 0)),
            _int(row.get("origin_z"), _int(row.get("z"), 0)),
        )
        for row in origins
    }
    evidence = []
    if source_kinds & _SUSPICIOUS_FIRE_SOURCES:
        evidence.append("blast_origin_damage")
    if len(origin_keys) > 1:
        evidence.append("multiple_origins")
    if any(_key(row.get("source_item_id")) for row in origins):
        evidence.append("device_or_incendiary_residue")
    forced_entry = _reported_forced_entry_evidence(sim, incident)
    if forced_entry:
        evidence.append("reported_forced_entry")
    evidence_codes = tuple(dict.fromkeys(evidence))
    existing = incident.get("fire_response_assessment")
    if (
        isinstance(existing, dict)
        and tuple(existing.get("evidence_codes", ()) or ()) == evidence_codes
        and _int(existing.get("origin_count"), 0) == len(origin_keys)
        and tuple(existing.get("related_reported_incidents", ()) or ()) == forced_entry
    ):
        return existing
    assessment = {
        "responder_eid": _int(responder_eid, -1),
        "assessed_tick": _int(getattr(sim, "tick", 0), 0),
        "x": _int(x, _int(incident.get("x"), 0)),
        "y": _int(y, _int(incident.get("y"), 0)),
        "z": _int(z, _int(incident.get("z"), 0)),
        "origin_count": len(origin_keys),
        "evidence_codes": evidence_codes,
        "related_reported_incidents": forced_entry,
        "disposition": "refer_fire_investigation" if evidence else "no_suspicious_origin_observed",
    }
    incident["fire_response_assessment"] = assessment
    mark_incident_registry_changed(sim)
    sim.emit(Event(
        "fire_response_scene_assessed",
        incident_id=incident.get("id"),
        responder_eid=responder_eid,
        evidence_codes=assessment["evidence_codes"],
        disposition=assessment["disposition"],
        x=assessment["x"],
        y=assessment["y"],
        z=assessment["z"],
        property_id=incident.get("property_id"),
    ))
    return assessment


def _visible_carcass_rows(sim, observer_eid, incident, *, radius=4):
    observer_pos = sim.ecs.get(Position).get(observer_eid)
    if observer_pos is None:
        return ()
    rows = []
    for carcass in tuple((getattr(sim, "hunting_carcasses", {}) or {}).values()):
        if not isinstance(carcass, dict) or bool(carcass.get("harvested", False)):
            continue
        cx, cy, cz = _int(carcass.get("x")), _int(carcass.get("y")), _int(carcass.get("z"), 0)
        if cz != int(observer_pos.z) or abs(cx - int(observer_pos.x)) + abs(cy - int(observer_pos.y)) > int(radius):
            continue
        if not has_line_of_sight(sim, int(observer_pos.x), int(observer_pos.y), int(observer_pos.z), cx, cy, cz):
            continue
        legality = carcass.get("hunt_legality") if isinstance(carcass.get("hunt_legality"), dict) else {}
        rows.append({
            "carcass_id": _int(carcass.get("carcass_id"), -1),
            "species_label": _text(carcass.get("species_label") or carcass.get("animal_name")) or "wildlife",
            "fauna_lineage_id": _key(carcass.get("fauna_lineage_id")) or None,
            "inspection_grade": _key(legality.get("inspection_grade")) or "unknown",
            "hunting_context": _key(legality.get("context")) or "unknown",
        })
    rows.sort(key=lambda row: row["carcass_id"])
    return tuple(rows)


def record_specialist_scene_review(sim, incident_id, specialist_eid, *, domain="", x=None, y=None, z=None):
    incident = incident_record(sim, incident_id)
    domain = _key(domain)
    if not isinstance(incident, dict) or domain not in {WILDLIFE_DOMAIN, FIRE_DOMAIN}:
        return None
    reviews = [row for row in tuple(incident.get("specialist_reviews", ()) or ()) if isinstance(row, dict)]
    for row in reviews:
        if _key(row.get("domain")) == domain and _int(row.get("specialist_eid"), -1) == _int(specialist_eid, -1):
            return row
    findings = {}
    if domain == WILDLIFE_DOMAIN:
        findings = {
            "reported_hunting_context": _key(incident.get("context")) or "unknown",
            "reported_license_status": _key(incident.get("hunting_license_status")) or "unknown",
            "reported_population_status": _key(incident.get("fauna_population_status")) or "unmanaged",
            "reported_cull_active": bool(incident.get("cull_active", False)),
            "visible_carcasses": _visible_carcass_rows(sim, specialist_eid, incident),
        }
        resolved_eid = resolved_subject_for_incident(sim, incident_id)
        if resolved_eid is not None:
            license_row = civic_license_record(sim, resolved_eid, "hunting") or {}
            findings["resolved_subject_license_status"] = _key(license_row.get("status")) or "unlicensed"
    else:
        assessment = incident.get("fire_response_assessment") if isinstance(incident.get("fire_response_assessment"), dict) else {}
        findings = {
            "response_assessment": dict(assessment),
            "active_origin_questions": tuple(assessment.get("evidence_codes", ()) or ()),
        }
    row = {
        "domain": domain,
        "specialist_eid": _int(specialist_eid, -1),
        "reviewed_tick": _int(getattr(sim, "tick", 0), 0),
        "x": _int(x, _int(incident.get("x"), 0)),
        "y": _int(y, _int(incident.get("y"), 0)),
        "z": _int(z, _int(incident.get("z"), 0)),
        "findings": findings,
    }
    reviews.append(row)
    incident["specialist_reviews"] = tuple(reviews[-12:])
    referral = specialist_referral(incident, domain)
    if isinstance(referral, dict):
        referral["status"] = "scene_reviewed"
        referral["reviewed_tick"] = row["reviewed_tick"]
        referral["specialist_eid"] = row["specialist_eid"]
        referral["updated_tick"] = row["reviewed_tick"]
    mark_incident_registry_changed(sim)
    sim.emit(Event(
        "specialist_incident_reviewed",
        incident_id=incident_id,
        specialist_eid=specialist_eid,
        domain=domain,
        x=row["x"],
        y=row["y"],
        z=row["z"],
        property_id=incident.get("property_id"),
    ))
    return row


__all__ = [
    "FIRE_CASEWORK_KIND",
    "FIRE_DOMAIN",
    "FIRE_INVESTIGATOR_CAREER_TOKENS",
    "WILDLIFE_CASEWORK_KIND",
    "WILDLIFE_CAREER_TOKENS",
    "WILDLIFE_DOMAIN",
    "assess_fire_response_scene",
    "fire_referral_read",
    "record_specialist_referral",
    "record_specialist_scene_review",
    "specialist_casework_kind",
    "specialist_domain_for_career",
    "specialist_referral",
    "specialist_referral_read",
    "specialist_response_role",
    "wildlife_referral_read",
]
