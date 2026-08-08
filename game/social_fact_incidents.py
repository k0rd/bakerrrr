"""Actor-owned incident adapters for the Social Fact Graph.

This module is the only ordinary bridge between legacy ``IncidentKnowledge``
accounts and incident propositions.  It never consults the canonical incident
registry.  Dialogue and social consequences can therefore compare what
particular actors know without receiving material world truth as an input.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from typing import Any

from game.components import IncidentKnowledge
from game.social_fact_graph import (
    ensure_proposition,
    record_actor_evidence,
    record_occurrence,
    register_referent,
)


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _unit(value: Any, default: float = 0.0) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        result = float(default)
    return max(0.0, min(1.0, result))


def _text(value: Any) -> str:
    return " ".join(str(value or "").strip().split())


def _token(value: Any) -> str:
    return _text(value).lower().replace(" ", "_")


def incident_knowledge_for(sim, actor_eid: Any, *, create: bool = False) -> IncidentKnowledge | None:
    """Return only ``actor_eid``'s legacy incident ledger."""

    actor = _int(actor_eid, -1)
    knowledge = sim.ecs.get(IncidentKnowledge).get(actor)
    if not isinstance(knowledge, IncidentKnowledge) and create and actor > 0:
        knowledge = IncidentKnowledge()
        sim.ecs.add(actor, knowledge)
    return knowledge if isinstance(knowledge, IncidentKnowledge) else None


def incident_account_label(record: Mapping[str, Any]) -> str:
    for key in ("kind_label", "friendly_kind", "category_label", "friendly_category"):
        label = _text(record.get(key))
        if label:
            return label.lower()
    for key in ("incident_kind", "action", "category"):
        label = _text(record.get(key)).replace("_", " ")
        if label and label not in {"other", "official", "social"}:
            return label.lower()
    return "incident"


def incident_account_semantic(record: Mapping[str, Any]) -> dict[str, Any]:
    """Return only the claim content present in an actor's own account."""

    return {
        "kind": _token(record.get("incident_kind") or record.get("kind_label") or record.get("category")),
        "action": _token(record.get("action")) or None,
        "context": _token(record.get("context")) or None,
        "tags": tuple(sorted({
            _token(tag)
            for tag in tuple(record.get("tags", ()) or ())
            if _token(tag)
        })),
    }


def incident_account_snapshot(record: Mapping[str, Any]) -> dict[str, Any]:
    """Freeze the actor-owned account used by a social occurrence."""

    account = record.get("subject_account")
    account = account if isinstance(account, Mapping) else {}
    location = None
    if record.get("x") is not None and record.get("y") is not None:
        location = {
            "x": _int(record.get("x"), 0),
            "y": _int(record.get("y"), 0),
            "z": _int(record.get("z"), 0),
        }
    return {
        "incident_id": _int(record.get("incident_id"), 0),
        "semantic": incident_account_semantic(record),
        "label": incident_account_label(record),
        "source_kind": _token(record.get("source_kind")),
        "source_eid": _int(record.get("source_eid"), 0) or None,
        "firsthand": bool(record.get("firsthand", False)),
        "confidence": _unit(record.get("confidence"), 0.5),
        "propagation_depth": max(0, _int(record.get("propagation_depth"), 0)),
        "learned_tick": max(0, _int(record.get("learned_tick"), 0)),
        "subject_identification": _token(account.get("identification")) or "unknown",
        "location": location,
    }


def _snapshot_digest(snapshot: Mapping[str, Any]) -> str:
    encoded = json.dumps(snapshot, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:20]


def ensure_actor_incident_perspective(sim, actor_eid: Any, incident_id: Any) -> dict[str, Any] | None:
    """Adapt one actor's incident account without consulting world truth."""

    actor = _int(actor_eid, 0)
    incident = _int(incident_id, 0)
    knowledge = incident_knowledge_for(sim, actor)
    record = (knowledge.records or {}).get(incident) if knowledge is not None else None
    if actor <= 0 or incident <= 0 or not isinstance(record, dict):
        return None

    snapshot = incident_account_snapshot(record)
    person_ref = register_referent(sim, "person", actor)
    incident_ref = register_referent(
        sim,
        "incident",
        incident,
        snapshot={"label": snapshot["label"]},
        tick=snapshot["learned_tick"],
    )
    proposition = ensure_proposition(
        sim,
        incident_ref["id"],
        "was_reported_as",
        object_value=snapshot["semantic"],
        qualifiers={"account_scope": "incident_knowledge"},
        tick=snapshot["learned_tick"],
    )
    evidence = record_occurrence(
        sim,
        "incident_knowledge_snapshot",
        actor_eids=(actor,),
        proposition_ids=(proposition["id"],),
        referent_ids=(person_ref["id"], incident_ref["id"]),
        payload=snapshot,
        flags=("firsthand",) if snapshot["firsthand"] else ("actor_owned",),
        tick=snapshot["learned_tick"],
        dedupe_key=(
            f"incident-knowledge:{actor}:{incident}:{proposition['id']}:"
            f"{_snapshot_digest(snapshot)}"
        ),
    )
    exposure = "witnessed" if snapshot["firsthand"] else "heard"
    perspective = record_actor_evidence(
        sim,
        actor,
        proposition["id"],
        evidence["id"],
        polarity="support",
        strength=snapshot["confidence"],
        exposure=exposure,
        source_actor_eid=snapshot["source_eid"],
        salience=max(
            _unit(record.get("social_interest"), 0.0),
            _unit(record.get("urgency"), 0.0),
        ),
        tags=("incident_knowledge_adapter",),
    )
    return {
        "incident_id": incident,
        "label": snapshot["label"],
        "record": dict(record),
        "snapshot": snapshot,
        "proposition": proposition,
        "perspective": perspective,
        "evidence": evidence,
    }


def project_heard_incident_account(
    sim,
    recipient_eid: Any,
    source_eid: Any,
    source_record: Mapping[str, Any],
    *,
    thread_id: str = "",
) -> dict[str, Any] | None:
    """Project a physically heard account into legacy actor knowledge.

    This deliberately does not queue rumor, urgent response, or authority
    behavior.  Those legacy consumers still enrich accounts from canonical
    incidents, which would exceed the fact packet delivered here.
    """

    recipient = _int(recipient_eid, 0)
    source = _int(source_eid, 0)
    incident_id = _int(source_record.get("incident_id"), 0)
    if recipient <= 0 or source <= 0 or incident_id <= 0:
        return None
    knowledge = incident_knowledge_for(sim, recipient, create=True)
    if knowledge is None:
        return None
    source_confidence = _unit(source_record.get("confidence"), 0.5)
    record = knowledge.remember(
        incident_id,
        learned_tick=_int(getattr(sim, "tick", 0), 0),
        source_kind="social_rumor",
        source_eid=source,
        confidence=source_confidence * 0.9,
        firsthand=False,
        propagation_depth=max(1, _int(source_record.get("propagation_depth"), 0) + 1),
        urgency=_unit(source_record.get("urgency"), 0.0) * 0.55,
        social_interest=max(0.2, _unit(source_record.get("social_interest"), 0.0) * 0.85),
        category=source_record.get("category", "social"),
        kind=source_record.get("incident_kind"),
        action=source_record.get("action"),
        context=source_record.get("context"),
        tags=tuple(source_record.get("tags", ()) or ()),
        category_label=source_record.get("category_label"),
        kind_label=source_record.get("kind_label"),
        severity=_int(source_record.get("severity"), 0),
        x=source_record.get("x"),
        y=source_record.get("y"),
        z=source_record.get("z"),
    )
    if isinstance(record, dict):
        record["social_fact_contact_thread_id"] = _text(thread_id) or None
        record["heard_from_eid"] = source
        record["legacy_action_queued"] = False
    return record


def project_heard_incident_packet(
    sim,
    recipient_eid: Any,
    speaker_eid: Any,
    packet: Mapping[str, Any],
    *,
    thread_id: str = "",
    reaction: str = "",
    origin_thread_id: str = "",
) -> dict[str, Any] | None:
    """Project exactly one delivered actor packet into recipient knowledge.

    Unlike the legacy queue consumers, this adapter has no incident-registry
    lookup available.  The recipient receives the semantic, location, and
    uncertainty the speaker actually carried, plus delivery provenance.
    """

    recipient = _int(recipient_eid, 0)
    speaker = _int(speaker_eid, 0)
    if recipient <= 0 or speaker <= 0 or not isinstance(packet, Mapping):
        return None
    if _int(packet.get("speaker_eid"), 0) != speaker:
        return None
    account = packet.get("account") if isinstance(packet.get("account"), Mapping) else {}
    semantic = account.get("semantic") if isinstance(account.get("semantic"), Mapping) else {}
    location = account.get("location") if isinstance(account.get("location"), Mapping) else {}
    incident_id = _int(account.get("incident_id"), 0)
    if incident_id <= 0:
        return None
    knowledge = incident_knowledge_for(sim, recipient, create=True)
    if knowledge is None:
        return None
    packet_confidence = _unit(packet.get("confidence"), 0.5)
    source_class = _token(packet.get("source_class"))
    independent = source_class in {"independent_account", "firsthand", "verified"}
    record = knowledge.remember(
        incident_id,
        learned_tick=_int(getattr(sim, "tick", 0), 0),
        source_kind="social_warning",
        source_eid=speaker,
        confidence=packet_confidence * (0.88 if independent else 0.72),
        firsthand=False,
        propagation_depth=max(1, _int(account.get("propagation_depth"), 0) + 1),
        urgency=_unit(account.get("urgency"), 0.0) * 0.72,
        social_interest=max(0.25, _unit(account.get("social_interest"), 0.0) * 0.88),
        category=account.get("category", "social"),
        kind=semantic.get("kind"),
        action=semantic.get("action"),
        context=semantic.get("context"),
        tags=tuple(semantic.get("tags", ()) or ()),
        category_label=account.get("category_label"),
        kind_label=account.get("kind_label") or account.get("label"),
        severity=_int(account.get("severity"), 0),
        x=location.get("x"),
        y=location.get("y"),
        z=location.get("z"),
    )
    if isinstance(record, dict):
        record["social_fact_warning_thread_id"] = _text(thread_id) or None
        record["social_fact_warning_origin_thread_id"] = _text(origin_thread_id) or None
        record["social_fact_packet_occurrence_id"] = _text(packet.get("packet_occurrence_id")) or None
        record["social_fact_warning_reaction"] = _token(reaction) or "heard"
        record["social_fact_warning_requester_eid"] = _int(packet.get("initiating_actor_eid"), 0) or None
        record["social_fact_warning_corrected_at_delivery"] = bool(
            packet.get("initiating_claim_corrected", False)
        )
        record["heard_from_eid"] = speaker
        record["legacy_action_queued"] = False
    return record


__all__ = [
    "ensure_actor_incident_perspective",
    "incident_account_label",
    "incident_account_semantic",
    "incident_account_snapshot",
    "incident_knowledge_for",
    "project_heard_incident_account",
    "project_heard_incident_packet",
]
