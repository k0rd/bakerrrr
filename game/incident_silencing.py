"""Actor-owned witness resolution and restraint on voluntary incident sharing.

This module does not erase incidents or knowledge. It records when the player
has a grounded reason to know a particular actor witnessed one of their acts,
then persists one bounded threat, bribe, or honest-accountability outcome on
that witness's own account. Dissemination and casework systems use that record
as their shared gate.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from engine.events import Event
from game.components import IncidentKnowledge, NPCSocial, SocialKnowledge
from game.social_fact_graph import (
    apply_social_effect,
    ensure_social_edge,
    record_occurrence,
    register_referent,
)
from game.social_fact_incidents import ensure_actor_incident_perspective


SILENCE_PRESSURE_KEY = "silence_pressure"
WITNESS_RESOLUTION_KEY = "witness_resolution"
SUPPRESSING_WITNESS_OUTCOMES = frozenset({"complied", "accepted", "forbearance"})


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _key(value: Any) -> str:
    return str(value or "").strip().lower()


def _incident_record(sim, actor_eid: Any, incident_id: Any) -> dict[str, Any] | None:
    actor = _int(actor_eid, 0)
    incident = _int(incident_id, 0)
    knowledge = sim.ecs.get(IncidentKnowledge).get(actor)
    record = (knowledge.records or {}).get(incident) if isinstance(knowledge, IncidentKnowledge) else None
    return record if isinstance(record, dict) else None


def record_player_known_firsthand_witness(
    sim,
    player_eid: Any,
    witness_eid: Any,
    incident_id: Any,
    *,
    basis: str,
) -> dict[str, Any] | None:
    """Give the player a provenance-backed witness reference they may act on."""

    player = _int(player_eid, 0)
    witness = _int(witness_eid, 0)
    incident = _int(incident_id, 0)
    if player <= 0 or witness <= 0 or incident <= 0 or player == witness:
        return None
    player_record = _incident_record(sim, player, incident)
    if not isinstance(player_record, dict):
        return None

    known = player_record.get("known_firsthand_witnesses")
    if not isinstance(known, dict):
        known = {}
        player_record["known_firsthand_witnesses"] = known
    existing = known.get(str(witness))
    if isinstance(existing, dict):
        return dict(existing)

    adapted = ensure_actor_incident_perspective(sim, player, incident)
    if not isinstance(adapted, dict):
        return None
    witness_ref = register_referent(sim, "person", witness)
    occurrence = record_occurrence(
        sim,
        "witness_awareness",
        actor_eids=(player,),
        proposition_ids=(adapted["proposition"]["id"],),
        referent_ids=(witness_ref["id"],),
        source_occurrence_ids=(adapted["evidence"]["id"],),
        payload={
            "incident_id": incident,
            "witness_eid": witness,
            "basis": _key(basis) or "direct_scene_awareness",
        },
        flags=("actor_owned", "grounded_access"),
        dedupe_key=f"incident-witness-awareness:{player}:{witness}:{incident}",
    )
    entry = {
        "actor_eid": witness,
        "learned_tick": _int(getattr(sim, "tick", 0), 0),
        "basis": _key(basis) or "direct_scene_awareness",
        "occurrence_id": occurrence["id"],
    }
    known[str(witness)] = entry
    return dict(entry)


def player_known_firsthand_witness(
    sim,
    player_eid: Any,
    witness_eid: Any,
    incident_id: Any,
) -> dict[str, Any] | None:
    record = _incident_record(sim, player_eid, incident_id)
    known = record.get("known_firsthand_witnesses") if isinstance(record, dict) else None
    entry = known.get(str(_int(witness_eid, 0))) if isinstance(known, dict) else None
    return dict(entry) if isinstance(entry, dict) else None


def incident_silence_pressure(sim, actor_eid: Any, incident_id: Any) -> dict[str, Any] | None:
    record = _incident_record(sim, actor_eid, incident_id)
    pressure = record.get(SILENCE_PRESSURE_KEY) if isinstance(record, dict) else None
    return dict(pressure) if isinstance(pressure, dict) else None


def incident_witness_resolution(sim, actor_eid: Any, incident_id: Any) -> dict[str, Any] | None:
    record = _incident_record(sim, actor_eid, incident_id)
    resolution = record.get(WITNESS_RESOLUTION_KEY) if isinstance(record, dict) else None
    if isinstance(resolution, dict):
        return dict(resolution)
    pressure = record.get(SILENCE_PRESSURE_KEY) if isinstance(record, dict) else None
    if isinstance(pressure, dict):
        return {
            **dict(pressure),
            "approach": "threat",
            "status": "resolved",
        }
    return None


def incident_spread_suppressed(sim, actor_eid: Any, incident_id: Any) -> bool:
    resolution = incident_witness_resolution(sim, actor_eid, incident_id)
    if not isinstance(resolution, dict):
        return False
    outcome = _key(resolution.get("outcome"))
    if outcome not in SUPPRESSING_WITNESS_OUTCOMES:
        return False
    if outcome == "forbearance":
        if _key(resolution.get("status")) != "active":
            return False
        deadline = _int(resolution.get("deadline_tick"), -1)
        return deadline < 0 or _int(getattr(sim, "tick", 0), 0) <= deadline
    return True


def incident_case_cooperation_withheld(sim, actor_eid: Any, incident_id: Any) -> bool:
    """Return whether this actor currently withholds voluntary case follow-up."""

    return incident_spread_suppressed(sim, actor_eid, incident_id)


def social_knowledge_incident_spread_suppressed(
    sim,
    actor_eid: Any,
    record: Mapping[str, Any],
) -> bool:
    if _key(record.get("source_domain")) != "incident":
        return False
    refs = record.get("refs") if isinstance(record.get("refs"), Mapping) else {}
    incident_id = _int(refs.get("incident_id"), _int(record.get("subject_key"), 0))
    return incident_id > 0 and incident_spread_suppressed(sim, actor_eid, incident_id)


def incident_prior_spread_state(sim, actor_eid: Any, incident_id: Any) -> dict[str, Any]:
    actor = _int(actor_eid, 0)
    incident = _int(incident_id, 0)
    knowledge = sim.ecs.get(IncidentKnowledge).get(actor)
    record = (knowledge.records or {}).get(incident) if isinstance(knowledge, IncidentKnowledge) else None
    shared = knowledge.last_shared.get(incident) if isinstance(knowledge, IncidentKnowledge) else None
    shared = shared if isinstance(shared, dict) else {}
    shared_with = tuple((record or {}).get("shared_with", ()) or ()) if isinstance(record, dict) else ()
    return {
        # Tick zero is a valid report time, so presence matters more than truthiness.
        "authority_reported": (
            record.get("authority_reported_tick") is not None
            if isinstance(record, dict)
            else False
        ),
        "authority_started": any(
            _key(channel) in {"report_authority", "authority_report", "official_report"}
            for channel in shared
        ),
        "social_shared_count": len({
            _int(eid, 0)
            for eid in shared_with
            if _int(eid, 0) > 0
        }),
    }


def _clear_voluntary_social_queues(sim, witness: int, incident: int, knowledge: IncidentKnowledge) -> None:
    knowledge.social_queue = [
        row
        for row in tuple(knowledge.social_queue or ())
        if _int(row.get("incident_id"), -1) != incident
    ]
    social = sim.ecs.get(SocialKnowledge).get(witness)
    if isinstance(social, SocialKnowledge):
        incident_key = f"incident:{incident}"
        social.social_queue = [
            row
            for row in tuple(social.social_queue or ())
            if str(row.get("key", "") or "").strip() != incident_key
        ]


def apply_incident_witness_resolution(
    sim,
    witness_eid: Any,
    incident_id: Any,
    *,
    player_eid: Any,
    approach: str,
    outcome: str,
    occurrence_id: str,
    status: str = "resolved",
    deadline_tick: Any = None,
    amount: Any = None,
    counter_amount: Any = None,
    offense_incident_id: Any = None,
    allow_transition: bool = False,
) -> dict[str, Any] | None:
    """Persist one bounded witness resolution or an allowed follow-up transition."""

    witness = _int(witness_eid, 0)
    incident = _int(incident_id, 0)
    player = _int(player_eid, 0)
    approach_key = _key(approach)
    outcome_key = _key(outcome)
    status_key = _key(status) or "resolved"
    if witness <= 0 or incident <= 0 or player <= 0:
        return None
    if approach_key not in {"threat", "bribe", "confession"} or not outcome_key:
        return None
    knowledge = sim.ecs.get(IncidentKnowledge).get(witness)
    record = (knowledge.records or {}).get(incident) if isinstance(knowledge, IncidentKnowledge) else None
    if not isinstance(record, dict):
        return None

    existing = record.get(WITNESS_RESOLUTION_KEY)
    if isinstance(existing, dict):
        existing_approach = _key(existing.get("approach"))
        existing_outcome = _key(existing.get("outcome"))
        allowed = bool(
            allow_transition
            and existing_approach == approach_key
            and (
                (approach_key == "bribe" and existing_outcome == "countered" and outcome_key in {"accepted", "declined"})
                or (
                    approach_key == "confession"
                    and existing_outcome == "forbearance"
                    and outcome_key in {"fulfilled", "breached"}
                )
            )
        )
        if not allowed:
            return {**dict(existing), "applied": False}

    resolution = {
        "player_eid": player,
        "approach": approach_key,
        "outcome": outcome_key,
        "status": status_key,
        "tick": _int(getattr(sim, "tick", 0), 0),
        "occurrence_id": str(occurrence_id or "").strip() or None,
    }
    if isinstance(existing, dict):
        resolution["opened_tick"] = _int(existing.get("opened_tick"), _int(existing.get("tick"), 0))
        resolution["origin_occurrence_id"] = existing.get("origin_occurrence_id") or existing.get("occurrence_id")
    else:
        resolution["opened_tick"] = _int(getattr(sim, "tick", 0), 0)
        resolution["origin_occurrence_id"] = resolution["occurrence_id"]
    if deadline_tick not in {None, ""}:
        resolution["deadline_tick"] = _int(deadline_tick, 0)
    elif isinstance(existing, dict) and existing.get("deadline_tick") is not None:
        resolution["deadline_tick"] = _int(existing.get("deadline_tick"), 0)
    if amount not in {None, ""}:
        resolution["amount"] = max(0, _int(amount, 0))
    elif isinstance(existing, dict) and existing.get("amount") is not None:
        resolution["amount"] = max(0, _int(existing.get("amount"), 0))
    if counter_amount not in {None, ""}:
        resolution["counter_amount"] = max(0, _int(counter_amount, 0))
    elif isinstance(existing, dict) and existing.get("counter_amount") is not None:
        resolution["counter_amount"] = max(0, _int(existing.get("counter_amount"), 0))
    if offense_incident_id not in {None, ""}:
        resolution["offense_incident_id"] = _int(offense_incident_id, 0)
    elif isinstance(existing, dict) and existing.get("offense_incident_id") is not None:
        resolution["offense_incident_id"] = _int(existing.get("offense_incident_id"), 0)
    record[WITNESS_RESOLUTION_KEY] = resolution

    if outcome_key in SUPPRESSING_WITNESS_OUTCOMES:
        record["voluntary_spread_suppressed"] = True
        _clear_voluntary_social_queues(sim, witness, incident, knowledge)
    elif outcome_key in {"refused", "declined", "accountability_required", "fulfilled", "breached"}:
        record["voluntary_spread_suppressed"] = False
        knowledge.queue_incident(
            incident,
            queue="social",
            score=max(0.55, float(record.get("social_interest", 0.0) or 0.0)),
            tick=_int(getattr(sim, "tick", 0), 0),
        )
        if bool(record.get("firsthand")):
            knowledge.queue_incident(
                incident,
                queue="urgent",
                score=max(0.72, float(record.get("urgency", 0.0) or 0.0)),
                tick=_int(getattr(sim, "tick", 0), 0),
            )
    return {**resolution, "applied": True}


def apply_incident_silence_pressure(
    sim,
    witness_eid: Any,
    incident_id: Any,
    *,
    threatener_eid: Any,
    outcome: str,
    occurrence_id: str,
) -> dict[str, Any] | None:
    """Persist one non-rerollable threat outcome on the witness's account."""

    witness = _int(witness_eid, 0)
    incident = _int(incident_id, 0)
    threatener = _int(threatener_eid, 0)
    result = _key(outcome)
    if witness <= 0 or incident <= 0 or threatener <= 0 or result not in {"complied", "refused"}:
        return None
    knowledge = sim.ecs.get(IncidentKnowledge).get(witness)
    record = (knowledge.records or {}).get(incident) if isinstance(knowledge, IncidentKnowledge) else None
    if not isinstance(record, dict):
        return None
    existing = record.get(SILENCE_PRESSURE_KEY)
    if isinstance(existing, dict):
        return {**dict(existing), "applied": False}

    applied = apply_incident_witness_resolution(
        sim,
        witness,
        incident,
        player_eid=threatener,
        approach="threat",
        outcome=result,
        occurrence_id=occurrence_id,
    )
    if not isinstance(applied, dict) or not bool(applied.get("applied", False)):
        return applied
    pressure = {
        "threatener_eid": threatener,
        "outcome": result,
        "tick": _int(getattr(sim, "tick", 0), 0),
        "occurrence_id": str(occurrence_id or "").strip() or None,
    }
    record[SILENCE_PRESSURE_KEY] = pressure

    return {**pressure, "applied": True}


def process_expired_witness_forbearance(sim) -> int:
    """Expire honest grace periods and make the broken promise actionable."""

    now = _int(getattr(sim, "tick", 0), 0)
    expired = 0
    for witness, knowledge in tuple(sim.ecs.get(IncidentKnowledge).items()):
        if not isinstance(knowledge, IncidentKnowledge):
            continue
        for incident, record in tuple((knowledge.records or {}).items()):
            resolution = record.get(WITNESS_RESOLUTION_KEY) if isinstance(record, dict) else None
            if not isinstance(resolution, dict):
                continue
            if (
                _key(resolution.get("approach")) != "confession"
                or _key(resolution.get("outcome")) != "forbearance"
                or _key(resolution.get("status")) != "active"
                or now <= _int(resolution.get("deadline_tick"), now)
            ):
                continue
            player = _int(resolution.get("player_eid"), 0)
            source_occurrence = str(resolution.get("occurrence_id") or "").strip()
            occurrence = record_occurrence(
                sim,
                "witness_forbearance_breached",
                actor_eids=(witness, player),
                source_occurrence_ids=(source_occurrence,) if source_occurrence else (),
                payload={
                    "incident_id": _int(incident, 0),
                    "witness_eid": _int(witness, 0),
                    "player_eid": player,
                    "deadline_tick": _int(resolution.get("deadline_tick"), 0),
                },
                flags=("broken_promise", "accountability"),
                dedupe_key=f"witness-forbearance-breached:{witness}:{player}:{incident}",
            )
            applied = apply_incident_witness_resolution(
                sim,
                witness,
                incident,
                player_eid=player,
                approach="confession",
                outcome="breached",
                status="resolved",
                occurrence_id=occurrence["id"],
                allow_transition=True,
            )
            if not bool((applied or {}).get("applied", False)):
                resolution["outcome"] = "breached"
                resolution["status"] = "resolved"
                resolution["breached_tick"] = now
                record["voluntary_spread_suppressed"] = False
                knowledge.queue_incident(incident, queue="social", score=0.72, tick=now)
                knowledge.queue_incident(incident, queue="urgent", score=0.86, tick=now)
            if player > 0:
                ensure_social_edge(sim, witness, player, contexts=("incident_witness", "broken_promise"))
                apply_social_effect(
                    sim,
                    witness,
                    player,
                    occurrence["id"],
                    "trust",
                    -0.26,
                    effect_kind="witness_forbearance_breached",
                    effect_key=f"{occurrence['id']}:trust",
                    contexts=("incident_witness", "broken_promise"),
                )
                apply_social_effect(
                    sim,
                    witness,
                    player,
                    occurrence["id"],
                    "resentment",
                    0.30,
                    effect_kind="witness_forbearance_breached",
                    effect_key=f"{occurrence['id']}:resentment",
                    contexts=("incident_witness", "broken_promise"),
                )
                social = sim.ecs.get(NPCSocial).get(witness)
                bond = social.bonds.get(player) if isinstance(social, NPCSocial) else None
                if isinstance(bond, dict):
                    bond["trust"] = max(0.0, float(bond.get("trust", 0.0) or 0.0) - 0.26)
            sim.emit(Event(
                "incident_witness_resolution",
                npc_eid=_int(witness, 0),
                player_eid=player,
                incident_id=_int(incident, 0),
                approach="confession",
                outcome="breached",
                resolution_occurrence_id=occurrence["id"],
            ))
            expired += 1
    return expired


__all__ = [
    "apply_incident_silence_pressure",
    "apply_incident_witness_resolution",
    "incident_case_cooperation_withheld",
    "incident_prior_spread_state",
    "incident_silence_pressure",
    "incident_spread_suppressed",
    "incident_witness_resolution",
    "player_known_firsthand_witness",
    "process_expired_witness_forbearance",
    "record_player_known_firsthand_witness",
    "social_knowledge_incident_spread_suppressed",
]
