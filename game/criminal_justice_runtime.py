"""Shared justice-facing witness and custody helpers."""

from game.checks import (
    crime_sensitivity as _crime_sensitivity,
    justice_level as _justice_level,
)
from game.components import AI, JusticeProfile, NPCSocial, Position
from game.dialogue_runtime import _active_contractor_record
from game.justice_runtime import (
    booking_seizure_snapshot as _justice_booking_seizure_snapshot,
    booking_anchor_for as _justice_booking_anchor_for,
    clear_restitution_claims as _clear_justice_restitution_claims,
    custody_release_grace_active as _custody_release_grace_active,
    decay_records as _decay_justice_records,
    grant_custody_release_grace as _grant_custody_release_grace,
    held_property_snapshot as _justice_held_property_snapshot,
    justice_snapshot as _justice_snapshot,
    justice_summary_rows as _justice_summary_rows,
    mark_in_custody as _mark_justice_in_custody,
    record_booking_completion as _record_justice_booking_completion,
    record_incident as _record_justice_incident,
    record_restitution_claim as _record_justice_restitution_claim,
    replace_held_property as _replace_justice_held_property,
    release_from_custody as _release_justice_from_custody,
    restitution_snapshot as _justice_restitution_snapshot,
    store_held_property as _store_justice_held_property,
)
from game.property_access import (
    evaluate_property_access as _evaluate_property_access,
    property_claim_reason as _property_claim_reason,
)
from game.property_runtime import property_covering as _property_covering
from game.system_support.awareness_runtime import _watchers_for_position
from game.system_support.combat_targeting_runtime import QUIET_NOISE_CAUSES
from game.system_support.offense_runtime import OFFICIAL_REPORTABLE_OFFENSE_CONTEXTS


def observer_is_active_contractor_ally(sim, observer_eid, offender_eid):
    return _active_contractor_record(
        sim,
        observer_eid,
        ally_eid=offender_eid,
        jobs={"backup", "party"},
    ) is not None


def observer_turns_blind_eye_to_offense(sim, observer_eid, offender_eid, *, action="", context="ordinary", offense_score=0):
    if sim is None or observer_eid is None or offender_eid is None:
        return False
    if observer_eid == offender_eid:
        return True
    if observer_is_active_contractor_ally(sim, observer_eid, offender_eid):
        return True
    if offender_eid != getattr(sim, "player_eid", None):
        return False

    context_key = str(context or "ordinary").strip().lower() or "ordinary"
    action_key = str(action or "").strip().lower()
    if context_key in OFFICIAL_REPORTABLE_OFFENSE_CONTEXTS:
        return False
    if action_key in {"fire_weapon", "vehicle_theft", "tamper"}:
        return False

    social = sim.ecs.get(NPCSocial).get(observer_eid)
    if not social:
        return False
    bond = social.bonds.get(offender_eid)
    if not isinstance(bond, dict):
        return False

    trust = float(bond.get("trust", 0.0) or 0.0)
    closeness = float(bond.get("closeness", 0.0) or 0.0)
    protectiveness = float(bond.get("protectiveness", 0.0) or 0.0)
    relation = str(bond.get("kind", "") or "").strip().lower()
    rapport = (trust * 0.5) + (closeness * 0.35) + (protectiveness * 0.15)
    if relation in {"family", "partner"}:
        rapport = max(rapport, 0.82)
    if trust < 0.58 or closeness < 0.44:
        return False

    max_score = 12 + int(round(rapport * 14.0))
    if relation in {"family", "partner", "friend"}:
        max_score += 2
    return int(offense_score or 0) <= max_score


def entities_have_family_bond(sim, first_eid, second_eid):
    if sim is None or first_eid is None or second_eid is None:
        return False

    socials = sim.ecs.get(NPCSocial)
    for source_eid, other_eid in ((first_eid, second_eid), (second_eid, first_eid)):
        social = socials.get(source_eid)
        if not social:
            continue
        bond = social.bonds.get(other_eid)
        if not isinstance(bond, dict):
            continue
        if str(bond.get("kind", "") or "").strip().lower() == "family":
            return True
    return False


def defender_excuses_window_shot(sim, defender_eid, offender_eid, prop, *, defender_reason=""):
    if sim is None or defender_eid is None or offender_eid is None or not isinstance(prop, dict):
        return False
    if defender_eid == offender_eid:
        return True

    positions = sim.ecs.get(Position)
    offender_pos = positions.get(offender_eid)
    if offender_pos:
        offender_access = _evaluate_property_access(
            sim,
            offender_eid,
            prop,
            x=offender_pos.x,
            y=offender_pos.y,
            z=offender_pos.z,
        )
    else:
        offender_access = _evaluate_property_access(
            sim,
            offender_eid,
            prop,
            x=prop.get("x"),
            y=prop.get("y"),
            z=prop.get("z", 0),
        )

    offender_reason = str(getattr(offender_access, "standing_reason", "") or "").strip().lower()
    defender_reason = str(defender_reason or "").strip().lower()
    if offender_reason in {"owner", "employee"} and defender_reason in {"owner", "employee"}:
        return True
    if entities_have_family_bond(sim, defender_eid, offender_eid):
        return True
    return False


def noise_merits_attention(sim, observer_eid, source_eid, x, y, z, cause):
    cause = str(cause or "").strip().lower()
    if source_eid is not None and observer_is_active_contractor_ally(sim, observer_eid, source_eid):
        return False
    if cause not in QUIET_NOISE_CAUSES:
        return True

    if source_eid is None:
        return False

    prop = _property_covering(sim, x, y, z)
    if not prop:
        return False

    access = _evaluate_property_access(sim, source_eid, prop, x=x, y=y, z=z)
    if not access.inside_bounds or access.severity_score <= 0:
        return False

    positions = sim.ecs.get(Position)
    observer_pos = positions.get(observer_eid)
    if not observer_pos:
        return False

    _, claim_reason = _property_claim_reason(
        sim,
        observer_eid,
        prop,
        x=observer_pos.x,
        y=observer_pos.y,
        z=observer_pos.z,
        min_standing=0.58,
    )
    if claim_reason:
        return True

    ais = sim.ecs.get(AI)
    ai = ais.get(observer_eid)
    role = str(getattr(ai, "role", "") or "").strip().lower()
    if role in {"guard", "scout"}:
        return True

    justices = sim.ecs.get(JusticeProfile)
    justice = justices.get(observer_eid)
    if not justice:
        return False
    if justice.enforce_all:
        return True

    law_drive = (_justice_level(justice) * 0.65) + (_crime_sensitivity(justice) * 0.35)
    threshold = 0.8 if access.severity_label == "suspicious" else 0.68
    return law_drive >= threshold


_custody_release_grace_active = _custody_release_grace_active
_decay_justice_records = _decay_justice_records
_defender_excuses_window_shot = defender_excuses_window_shot
_entities_have_family_bond = entities_have_family_bond
_grant_custody_release_grace = _grant_custody_release_grace
_justice_booking_anchor_for = _justice_booking_anchor_for
_justice_held_property_snapshot = _justice_held_property_snapshot
_justice_snapshot = _justice_snapshot
_justice_summary_rows = _justice_summary_rows
_mark_justice_in_custody = _mark_justice_in_custody
_noise_merits_attention = noise_merits_attention
_observer_is_active_contractor_ally = observer_is_active_contractor_ally
_observer_turns_blind_eye_to_offense = observer_turns_blind_eye_to_offense
_record_justice_booking_completion = _record_justice_booking_completion
_record_justice_incident = _record_justice_incident
_release_justice_from_custody = _release_justice_from_custody
_replace_justice_held_property = _replace_justice_held_property
_store_justice_held_property = _store_justice_held_property
