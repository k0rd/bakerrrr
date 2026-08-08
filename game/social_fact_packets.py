"""Actor-bounded fact packets for social behavior.

A packet freezes what one actor is prepared to say and why they are prepared to
say it.  It is an immutable Social Fact Graph occurrence, not a material truth
record, and it is built exclusively from the speaker's own perspective and
legacy account.  Consumers must not enrich it from the canonical incident
registry.
"""

from __future__ import annotations

import copy
from collections.abc import Iterable, Mapping
from typing import Any

from game.social_fact_graph import actor_perspective, occurrence_record, record_occurrence
from game.social_fact_incidents import ensure_actor_incident_perspective


ACTOR_FACT_PACKET_SCHEMA_VERSION = 1


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _unit(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    return max(0.0, min(1.0, number))


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _token(value: Any) -> str:
    return _text(value).lower().replace(" ", "_")


def create_actor_incident_fact_packet(
    sim,
    *,
    speaker_eid: Any,
    incident_id: Any,
    proposition_id: str,
    purpose: str,
    source_occurrence_ids: Iterable[str],
    source_class: str,
    initiating_actor_eid: Any = None,
    initiating_claim_corrected: bool = False,
    attribution_disclosed: bool = True,
    max_hops: int = 1,
    dedupe_key: str,
) -> dict[str, Any]:
    """Freeze one speaker-owned incident account as an immutable packet."""

    speaker = _int(speaker_eid, 0)
    incident = _int(incident_id, 0)
    proposition_key = _text(proposition_id)
    purpose_key = _token(purpose)
    if speaker <= 0 or incident <= 0 or not proposition_key or not purpose_key:
        raise ValueError("actor fact packets require speaker, incident, proposition, and purpose")
    adapted = ensure_actor_incident_perspective(sim, speaker, incident)
    if not isinstance(adapted, dict) or adapted["proposition"]["id"] != proposition_key:
        raise ValueError("actor fact packet must match the speaker's own incident account")
    perspective = actor_perspective(sim, speaker, proposition_key) or {}
    record = adapted["record"]
    snapshot = adapted["snapshot"]
    account = {
        "incident_id": incident,
        "label": snapshot.get("label") or "incident",
        "semantic": copy.deepcopy(snapshot.get("semantic") or {}),
        "location": copy.deepcopy(snapshot.get("location")),
        "category": _token(record.get("category")) or "social",
        "category_label": _text(record.get("category_label")),
        "kind_label": _text(record.get("kind_label")),
        "severity": max(0, min(100, _int(record.get("severity"), 0))),
        "urgency": _unit(record.get("urgency"), 0.0),
        "social_interest": _unit(record.get("social_interest"), 0.0),
        "propagation_depth": max(0, _int(record.get("propagation_depth"), 0)),
    }
    initiating_actor = _int(initiating_actor_eid, 0) or None
    packet = {
        "schema_version": ACTOR_FACT_PACKET_SCHEMA_VERSION,
        "speaker_eid": speaker,
        "purpose": purpose_key,
        "proposition_id": proposition_key,
        "account": account,
        "stance": _token(perspective.get("stance")) or "unknown",
        "confidence": _unit(perspective.get("confidence"), snapshot.get("confidence", 0.5)),
        "salience": _unit(perspective.get("salience"), max(account["urgency"], account["social_interest"])),
        "source_class": _token(source_class) or "actor_account",
        "initiating_actor_eid": initiating_actor if attribution_disclosed else None,
        "initiating_claim_corrected": bool(initiating_claim_corrected),
        "attribution_disclosed": bool(attribution_disclosed and initiating_actor is not None),
        "hop": 0,
        "max_hops": max(0, min(4, _int(max_hops, 1))),
    }
    occurrence = record_occurrence(
        sim,
        "actor_fact_packet",
        actor_eids=(speaker,),
        proposition_ids=(proposition_key,),
        source_occurrence_ids=tuple(source_occurrence_ids or ()),
        payload={"packet": packet},
        flags=("actor_owned", "behavior_packet", "no_canonical_lookup"),
        dedupe_key=_text(dedupe_key),
    )
    return {"packet_occurrence_id": occurrence["id"], **copy.deepcopy(packet)}


def actor_fact_packet(sim, packet_occurrence_id: str, *, speaker_eid: Any = None) -> dict[str, Any] | None:
    """Read one immutable packet, optionally proving speaker ownership."""

    occurrence = occurrence_record(sim, packet_occurrence_id)
    if not isinstance(occurrence, dict) or occurrence.get("kind") != "actor_fact_packet":
        return None
    payload = occurrence.get("payload") if isinstance(occurrence.get("payload"), Mapping) else {}
    packet = payload.get("packet") if isinstance(payload.get("packet"), Mapping) else None
    if not isinstance(packet, Mapping):
        return None
    speaker = _int(packet.get("speaker_eid"), 0)
    required_speaker = _int(speaker_eid, 0)
    if speaker <= 0 or (required_speaker > 0 and speaker != required_speaker):
        return None
    if _int(packet.get("schema_version"), 0) != ACTOR_FACT_PACKET_SCHEMA_VERSION:
        return None
    return {"packet_occurrence_id": occurrence["id"], **copy.deepcopy(dict(packet))}


def validate_actor_fact_packet(sim, packet_occurrence_id: str) -> tuple[str, ...]:
    """Return packet-specific provenance and boundary errors."""

    packet = actor_fact_packet(sim, packet_occurrence_id)
    if not isinstance(packet, dict):
        return ("missing or invalid actor fact packet",)
    errors = []
    account = packet.get("account") if isinstance(packet.get("account"), Mapping) else {}
    if _int(account.get("incident_id"), 0) <= 0:
        errors.append("actor fact packet has no actor-owned incident identity")
    if not _text(packet.get("proposition_id")):
        errors.append("actor fact packet has no proposition")
    if not _token(packet.get("purpose")):
        errors.append("actor fact packet has no purpose")
    if _int(packet.get("hop"), 0) > _int(packet.get("max_hops"), 0):
        errors.append("actor fact packet exceeds its propagation bound")
    return tuple(errors)


__all__ = [
    "ACTOR_FACT_PACKET_SCHEMA_VERSION",
    "actor_fact_packet",
    "create_actor_incident_fact_packet",
    "validate_actor_fact_packet",
]
