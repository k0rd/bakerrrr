"""Persistent fact-referenced social memory for actors and conversations.

The graph records socially meaningful history without granting any actor
omniscient access to simulation truth.  Domain systems still own incidents,
properties, employment, opportunities, and other material state.  This module
owns stable references, truth-neutral propositions, immutable occurrences,
actor-scoped perspectives with mutable attention, causal social effects, and
continuing threads.

Ordinary callers should use actor-scoped query helpers.  The explicitly named
``debug_social_fact_trace`` helper is the only public whole-graph read surface.
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections.abc import Iterable, Mapping
from typing import Any


SOCIAL_FACT_GRAPH_SCHEMA_VERSION = 2

PERSPECTIVE_STANCES = (
    "unknown",
    "plausible",
    "accepted",
    "doubtful",
    "rejected",
    "disputed",
)

EVIDENCE_POLARITIES = ("support", "contradict", "neutral")

EXPOSURE_LEVELS = (
    "none",
    "dreamed",
    "heard",
    "inferred",
    "observed",
    "witnessed",
    "verified",
)

SOCIAL_DIMENSIONS = (
    "trust",
    "closeness",
    "protectiveness",
    "reliability",
    "obligation",
    "resentment",
    "fear",
    "authority",
    "dependence",
)

THREAD_STATUSES = (
    "open",
    "awaiting_response",
    "considering",
    "acted",
    "corroborated",
    "disputed",
    "retracted",
    "closed",
)

_TOKEN_RE = re.compile(r"[^a-z0-9_.:-]+")
_ID_SUFFIX_RE = re.compile(r"^(?:occurrence|thread):(\d+)$")
_EXPOSURE_RANK = {name: index for index, name in enumerate(EXPOSURE_LEVELS)}
_MISSING = object()


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
    if not math.isfinite(result):
        result = float(default)
    return max(0.0, min(1.0, result))


def _token(value: Any, *, fallback: str = "") -> str:
    text = str(value or "").strip().lower().replace(" ", "_")
    text = _TOKEN_RE.sub("_", text).strip("_")
    return text or str(fallback or "").strip().lower()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _actor_id(value: Any) -> int | None:
    try:
        actor = int(value)
    except (TypeError, ValueError):
        return None
    return actor if actor > 0 else None


def _actor_ids(values: Iterable[Any]) -> tuple[int, ...]:
    result = []
    seen = set()
    for value in tuple(values or ()):
        actor = _actor_id(value)
        if actor is None or actor in seen:
            continue
        seen.add(actor)
        result.append(actor)
    return tuple(result)


def _string_ids(values: Iterable[Any]) -> tuple[str, ...]:
    result = []
    seen = set()
    for value in tuple(values or ()):
        key = _text(value)
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return tuple(result)


def _canonical_value(value: Any) -> Any:
    """Return a deterministic, persistence-safe copy for graph payloads."""

    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("social fact graph values must be finite")
        return float(value)
    if isinstance(value, Mapping):
        return {
            str(key): _canonical_value(item)
            for key, item in sorted(value.items(), key=lambda row: str(row[0]))
        }
    if isinstance(value, (list, tuple)):
        return tuple(_canonical_value(item) for item in value)
    if isinstance(value, (set, frozenset)):
        normalized = [_canonical_value(item) for item in value]
        normalized.sort(key=_canonical_json)
        return tuple(normalized)
    raise TypeError(f"unsupported social fact graph value: {type(value).__name__}")


def _json_ready(value: Any) -> Any:
    if isinstance(value, tuple):
        return [_json_ready(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_ready(item) for key, item in value.items()}
    return value


def _canonical_json(value: Any) -> str:
    return json.dumps(
        _json_ready(_canonical_value(value)),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )


def _empty_state() -> dict[str, Any]:
    return {
        "schema_version": SOCIAL_FACT_GRAPH_SCHEMA_VERSION,
        "next_occurrence_id": 1,
        "next_thread_id": 1,
        "referents": {},
        "propositions": {},
        "proposition_by_key": {},
        "occurrences": {},
        "occurrence_by_dedupe_key": {},
        "occurrence_order": [],
        "perspectives": {},
        "social_edges": {},
        "threads": {},
        "thread_by_key": {},
    }


def _next_numeric_id(records: Mapping[str, Any], prefix: str) -> int:
    highest = 0
    for raw_id in records.keys():
        match = _ID_SUFFIX_RE.match(str(raw_id))
        if match is None or not str(raw_id).startswith(f"{prefix}:"):
            continue
        highest = max(highest, _int(match.group(1), 0))
    return highest + 1


def _combined_weight(values: Iterable[float]) -> float:
    remainder = 1.0
    for value in tuple(values or ()):
        remainder *= 1.0 - _unit(value)
    return _unit(1.0 - remainder)


def _migrate_v1_perspective_attention(state: dict[str, Any]) -> None:
    """Move mutable salience out of immutable v1 evidence records."""

    occurrences = state.get("occurrences") if isinstance(state.get("occurrences"), dict) else {}
    perspectives = state.get("perspectives") if isinstance(state.get("perspectives"), dict) else {}
    for actor_rows in perspectives.values():
        if not isinstance(actor_rows, dict):
            continue
        for row in actor_rows.values():
            if not isinstance(row, dict):
                continue
            evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
            attention = row.get("attention") if isinstance(row.get("attention"), dict) else {}
            for occurrence_id, evidence_record in evidence.items():
                if not isinstance(evidence_record, dict) or "salience" not in evidence_record:
                    continue
                salience = _unit(evidence_record.pop("salience"), 0.0)
                occurrence = occurrences.get(occurrence_id)
                attention.setdefault(
                    occurrence_id,
                    {
                        "salience": salience,
                        "updated_tick": _int((occurrence or {}).get("tick"), 0),
                    },
                )
            row["attention"] = attention
            row["salience"] = _combined_weight(
                item.get("salience", 0.0)
                for item in attention.values()
                if isinstance(item, dict)
            )


def _normalize_state(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict) or not raw:
        return _empty_state()

    version = _int(raw.get("schema_version"), 0)
    if version > SOCIAL_FACT_GRAPH_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported social fact graph schema: {version} "
            f"> {SOCIAL_FACT_GRAPH_SCHEMA_VERSION}"
        )
    if version <= 0:
        # There was no pre-v1 public schema.  A non-empty unversioned mapping
        # cannot be interpreted safely as social truth.
        return _empty_state()

    state = raw
    if version == 1:
        _migrate_v1_perspective_attention(state)
    state["schema_version"] = SOCIAL_FACT_GRAPH_SCHEMA_VERSION
    for key in (
        "referents",
        "propositions",
        "proposition_by_key",
        "occurrences",
        "occurrence_by_dedupe_key",
        "perspectives",
        "social_edges",
        "threads",
        "thread_by_key",
    ):
        if not isinstance(state.get(key), dict):
            state[key] = {}
    if not isinstance(state.get("occurrence_order"), list):
        state["occurrence_order"] = []
    state["next_occurrence_id"] = max(
        1,
        _int(state.get("next_occurrence_id"), 1),
        _next_numeric_id(state["occurrences"], "occurrence"),
    )
    state["next_thread_id"] = max(
        1,
        _int(state.get("next_thread_id"), 1),
        _next_numeric_id(state["threads"], "thread"),
    )
    return state


def social_fact_graph_state(sim) -> dict[str, Any]:
    """Return the persistent, versioned social graph state for ``sim``."""

    state = _normalize_state(getattr(sim, "social_fact_graph", None))
    sim.social_fact_graph = state
    return state


def register_referent(
    sim,
    kind: str,
    external_id: Any,
    *,
    snapshot: Mapping[str, Any] | None = None,
    tick: int | None = None,
) -> dict[str, Any]:
    """Register one stable social referent without mutating prior snapshots."""

    kind_key = _token(kind)
    external_key = _text(external_id)
    if not kind_key or not external_key:
        raise ValueError("social referents require a kind and external id")
    referent_id = f"{kind_key}:{external_key}"
    state = social_fact_graph_state(sim)
    existing = state["referents"].get(referent_id)
    if isinstance(existing, dict):
        return copy.deepcopy(existing)
    record = {
        "id": referent_id,
        "kind": kind_key,
        "external_id": external_key,
        "created_tick": _int(getattr(sim, "tick", 0) if tick is None else tick, 0),
        "snapshot": _canonical_value(dict(snapshot or {})),
    }
    state["referents"][referent_id] = record
    return copy.deepcopy(record)


def referent_record(sim, referent_id: str) -> dict[str, Any] | None:
    record = social_fact_graph_state(sim)["referents"].get(_text(referent_id))
    return copy.deepcopy(record) if isinstance(record, dict) else None


def ensure_proposition(
    sim,
    subject_ref: str,
    predicate: str,
    *,
    object_ref: str | None = None,
    object_value: Any = None,
    qualifiers: Mapping[str, Any] | None = None,
    tick: int | None = None,
) -> dict[str, Any]:
    """Return the unique immutable proposition for one semantic statement."""

    state = social_fact_graph_state(sim)
    subject_key = _text(subject_ref)
    predicate_key = _token(predicate)
    object_key = _text(object_ref)
    if subject_key not in state["referents"]:
        raise KeyError(f"unknown proposition subject referent: {subject_key}")
    if not predicate_key:
        raise ValueError("social propositions require a predicate")
    if object_key and object_key not in state["referents"]:
        raise KeyError(f"unknown proposition object referent: {object_key}")
    if object_key and object_value is not None:
        raise ValueError("social propositions accept object_ref or object_value, not both")

    semantic = {
        "subject_ref": subject_key,
        "predicate": predicate_key,
        "object_ref": object_key or None,
        "object_value": None if object_key else _canonical_value(object_value),
        "qualifiers": _canonical_value(dict(qualifiers or {})),
    }
    semantic_json = _canonical_json(semantic)
    digest = hashlib.sha256(semantic_json.encode("utf-8")).hexdigest()
    existing_id = state["proposition_by_key"].get(digest)
    existing = state["propositions"].get(existing_id) if existing_id else None
    if isinstance(existing, dict):
        if str(existing.get("semantic_json", "")) != semantic_json:
            raise ValueError("social proposition digest collision")
        return copy.deepcopy(existing)

    proposition_id = f"proposition:{digest[:24]}"
    collision = state["propositions"].get(proposition_id)
    if isinstance(collision, dict) and str(collision.get("semantic_json", "")) != semantic_json:
        proposition_id = f"proposition:{digest}"
    record = {
        "id": proposition_id,
        **semantic,
        "semantic_key": digest,
        "semantic_json": semantic_json,
        "created_tick": _int(getattr(sim, "tick", 0) if tick is None else tick, 0),
    }
    state["propositions"][proposition_id] = record
    state["proposition_by_key"][digest] = proposition_id
    return copy.deepcopy(record)


def proposition_record(sim, proposition_id: str) -> dict[str, Any] | None:
    record = social_fact_graph_state(sim)["propositions"].get(_text(proposition_id))
    return copy.deepcopy(record) if isinstance(record, dict) else None


def _next_record_id(state: dict[str, Any], field: str, prefix: str) -> str:
    value = max(1, _int(state.get(field), 1))
    state[field] = value + 1
    return f"{prefix}:{value}"


def record_occurrence(
    sim,
    kind: str,
    *,
    actor_eids: Iterable[Any] = (),
    proposition_ids: Iterable[str] = (),
    referent_ids: Iterable[str] = (),
    source_occurrence_ids: Iterable[str] = (),
    payload: Mapping[str, Any] | None = None,
    flags: Iterable[str] = (),
    tick: int | None = None,
    dedupe_key: str | None = None,
) -> dict[str, Any]:
    """Append one immutable social occurrence, optionally source-idempotent."""

    state = social_fact_graph_state(sim)
    kind_key = _token(kind)
    if not kind_key:
        raise ValueError("social occurrences require a kind")
    actors = _actor_ids(actor_eids)
    proposition_keys = _string_ids(proposition_ids)
    referent_keys = _string_ids(referent_ids)
    source_keys = _string_ids(source_occurrence_ids)
    for proposition_id in proposition_keys:
        if proposition_id not in state["propositions"]:
            raise KeyError(f"unknown occurrence proposition: {proposition_id}")
    for referent_id in referent_keys:
        if referent_id not in state["referents"]:
            raise KeyError(f"unknown occurrence referent: {referent_id}")
    for occurrence_id in source_keys:
        if occurrence_id not in state["occurrences"]:
            raise KeyError(f"unknown source occurrence: {occurrence_id}")

    canonical_payload = _canonical_value(dict(payload or {}))
    canonical_flags = tuple(sorted({_token(flag) for flag in tuple(flags or ()) if _token(flag)}))
    dedupe_fingerprint = hashlib.sha256(_canonical_json({
        "kind": kind_key,
        "actor_eids": actors,
        "proposition_ids": proposition_keys,
        "referent_ids": referent_keys,
        "source_occurrence_ids": source_keys,
        "payload": canonical_payload,
        "flags": canonical_flags,
    }).encode("utf-8")).hexdigest()

    dedupe = _text(dedupe_key)
    if dedupe:
        existing_id = state["occurrence_by_dedupe_key"].get(dedupe)
        existing = state["occurrences"].get(existing_id) if existing_id else None
        if isinstance(existing, dict):
            if str(existing.get("dedupe_fingerprint", "")) != dedupe_fingerprint:
                raise ValueError(f"social occurrence dedupe collision: {dedupe}")
            return copy.deepcopy(existing)

    occurrence_id = _next_record_id(state, "next_occurrence_id", "occurrence")
    record = {
        "id": occurrence_id,
        "kind": kind_key,
        "tick": _int(getattr(sim, "tick", 0) if tick is None else tick, 0),
        "actor_eids": actors,
        "proposition_ids": proposition_keys,
        "referent_ids": referent_keys,
        "source_occurrence_ids": source_keys,
        "payload": canonical_payload,
        "flags": canonical_flags,
        "dedupe_key": dedupe or None,
        "dedupe_fingerprint": dedupe_fingerprint if dedupe else None,
    }
    state["occurrences"][occurrence_id] = record
    state["occurrence_order"].append(occurrence_id)
    if dedupe:
        state["occurrence_by_dedupe_key"][dedupe] = occurrence_id
    return copy.deepcopy(record)


def occurrence_record(sim, occurrence_id: str) -> dict[str, Any] | None:
    record = social_fact_graph_state(sim)["occurrences"].get(_text(occurrence_id))
    return copy.deepcopy(record) if isinstance(record, dict) else None


def _reduce_perspective(row: dict[str, Any], occurrences: Mapping[str, Any]) -> dict[str, Any]:
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    attention = row.get("attention") if isinstance(row.get("attention"), dict) else {}
    support = _combined_weight(
        item.get("strength", 0.0)
        for item in evidence.values()
        if isinstance(item, dict) and item.get("polarity") == "support"
    )
    contradict = _combined_weight(
        item.get("strength", 0.0)
        for item in evidence.values()
        if isinstance(item, dict) and item.get("polarity") == "contradict"
    )
    salience = _combined_weight(
        item.get("salience", 0.0)
        for item in attention.values()
        if isinstance(item, dict)
    )
    exposure = "none"
    first_tick = None
    last_tick = None
    source_actor_ids = set()
    for occurrence_id, item in evidence.items():
        if not isinstance(item, dict):
            continue
        item_exposure = str(item.get("exposure", "none") or "none").strip().lower()
        if _EXPOSURE_RANK.get(item_exposure, 0) > _EXPOSURE_RANK.get(exposure, 0):
            exposure = item_exposure
        occurrence = occurrences.get(occurrence_id)
        evidence_tick = _int((occurrence or {}).get("tick"), 0)
        first_tick = evidence_tick if first_tick is None else min(first_tick, evidence_tick)
        last_tick = evidence_tick if last_tick is None else max(last_tick, evidence_tick)
        source_actor = _actor_id(item.get("source_actor_eid"))
        if source_actor is not None:
            source_actor_ids.add(source_actor)

    margin = support - contradict
    if support >= 0.45 and contradict >= 0.45 and abs(margin) <= 0.2:
        stance = "disputed"
    elif support >= 0.68 and margin >= 0.25:
        stance = "accepted"
    elif margin >= 0.1:
        stance = "plausible"
    elif contradict >= 0.68 and margin <= -0.25:
        stance = "rejected"
    elif margin <= -0.1:
        stance = "doubtful"
    else:
        stance = "unknown"

    row["stance"] = stance
    row["exposure"] = exposure
    row["confidence"] = max(support, contradict)
    row["confidence_margin"] = abs(margin)
    row["support_score"] = support
    row["contradict_score"] = contradict
    row["salience"] = salience
    row["source_actor_ids"] = tuple(sorted(source_actor_ids))
    row["first_learned_tick"] = 0 if first_tick is None else int(first_tick)
    row["last_revised_tick"] = 0 if last_tick is None else int(last_tick)
    return row


def record_actor_evidence(
    sim,
    actor_eid: Any,
    proposition_id: str,
    occurrence_id: str,
    *,
    polarity: str = "support",
    strength: float = 0.5,
    exposure: str = "heard",
    source_actor_eid: Any = None,
    tags: Iterable[str] = (),
) -> dict[str, Any]:
    """Attach immutable evidence to one actor's mutable proposition view."""

    state = social_fact_graph_state(sim)
    actor = _actor_id(actor_eid)
    proposition_key = _text(proposition_id)
    occurrence_key = _text(occurrence_id)
    polarity_key = _token(polarity)
    exposure_key = _token(exposure)
    if actor is None:
        raise ValueError("actor evidence requires a positive actor id")
    if proposition_key not in state["propositions"]:
        raise KeyError(f"unknown evidence proposition: {proposition_key}")
    occurrence = state["occurrences"].get(occurrence_key)
    if not isinstance(occurrence, dict):
        raise KeyError(f"unknown evidence occurrence: {occurrence_key}")
    if proposition_key not in set(occurrence.get("proposition_ids", ()) or ()):
        raise ValueError("evidence occurrence does not reference the proposition")
    if polarity_key not in EVIDENCE_POLARITIES:
        raise ValueError(f"unsupported evidence polarity: {polarity_key}")
    if exposure_key not in EXPOSURE_LEVELS:
        raise ValueError(f"unsupported evidence exposure: {exposure_key}")

    perspectives = state["perspectives"].setdefault(actor, {})
    row = perspectives.get(proposition_key)
    if not isinstance(row, dict):
        row = {
            "actor_eid": actor,
            "proposition_id": proposition_key,
            "evidence": {},
            "attention": {},
        }
        perspectives[proposition_key] = row
    evidence = row.get("evidence")
    if not isinstance(evidence, dict):
        evidence = {}
        row["evidence"] = evidence
    evidence_record = {
        "occurrence_id": occurrence_key,
        "polarity": polarity_key,
        "strength": _unit(strength, 0.5),
        "exposure": exposure_key,
        "source_actor_eid": _actor_id(source_actor_eid),
        "tags": tuple(sorted({_token(tag) for tag in tuple(tags or ()) if _token(tag)})),
    }
    existing_evidence = evidence.get(occurrence_key)
    if isinstance(existing_evidence, dict):
        if existing_evidence != evidence_record:
            raise ValueError(
                "one occurrence cannot carry conflicting evidence for the "
                "same actor and proposition"
            )
    else:
        evidence[occurrence_key] = evidence_record
    _reduce_perspective(row, state["occurrences"])
    return copy.deepcopy(row)


def set_actor_perspective_attention(
    sim,
    actor_eid: Any,
    proposition_id: str,
    occurrence_id: str,
    *,
    salience: float,
    tick: int | None = None,
) -> dict[str, Any]:
    """Set mutable attention grounded in evidence already owned by the actor."""

    state = social_fact_graph_state(sim)
    actor = _actor_id(actor_eid)
    proposition_key = _text(proposition_id)
    occurrence_key = _text(occurrence_id)
    if actor is None:
        raise ValueError("actor attention requires a positive actor id")
    row = state["perspectives"].get(actor, {}).get(proposition_key)
    if not isinstance(row, dict):
        raise KeyError("actor attention requires an existing perspective")
    evidence = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    if occurrence_key not in evidence:
        raise KeyError("actor attention must reference actor-owned evidence")
    attention = row.get("attention")
    if not isinstance(attention, dict):
        attention = {}
        row["attention"] = attention
    attention[occurrence_key] = {
        "salience": _unit(salience),
        "updated_tick": _int(getattr(sim, "tick", 0) if tick is None else tick, 0),
    }
    _reduce_perspective(row, state["occurrences"])
    return copy.deepcopy(row)


def actor_perspective(sim, actor_eid: Any, proposition_id: str) -> dict[str, Any] | None:
    """Return only ``actor_eid``'s perspective on one proposition."""

    actor = _actor_id(actor_eid)
    if actor is None:
        return None
    row = social_fact_graph_state(sim)["perspectives"].get(actor, {}).get(_text(proposition_id))
    return copy.deepcopy(row) if isinstance(row, dict) else None


def actor_knows_proposition(sim, actor_eid: Any, proposition_id: str) -> bool:
    row = actor_perspective(sim, actor_eid, proposition_id)
    return bool(row and row.get("exposure") not in {None, "", "none", "dreamed"})


def record_claim(
    sim,
    speaker_eid: Any,
    audience_eids: Iterable[Any],
    proposition_id: str,
    *,
    position: str = "support",
    certainty: float = 0.6,
    credibility_by_audience: Mapping[Any, Any] | None = None,
    salience: float = 0.35,
    spoken_text: str = "",
    source_occurrence_ids: Iterable[str] = (),
    tick: int | None = None,
    dedupe_key: str | None = None,
) -> dict[str, Any]:
    """Record a speech act and what each audience actually heard."""

    speaker = _actor_id(speaker_eid)
    audiences = _actor_ids(audience_eids)
    proposition_key = _text(proposition_id)
    position_key = _token(position)
    if speaker is None:
        raise ValueError("claims require a speaker")
    if not audiences:
        raise ValueError("claims require at least one audience actor")
    if position_key not in {"support", "contradict"}:
        raise ValueError("claim position must support or contradict its proposition")
    certainty_value = _unit(certainty, 0.6)
    occurrence = record_occurrence(
        sim,
        "claim",
        actor_eids=(speaker, *audiences),
        proposition_ids=(proposition_key,),
        source_occurrence_ids=source_occurrence_ids,
        payload={
            "speaker_eid": speaker,
            "audience_eids": audiences,
            "position": position_key,
            "stated_certainty": certainty_value,
            "spoken_text": _text(spoken_text),
        },
        flags=("speech", "attributed"),
        tick=tick,
        dedupe_key=dedupe_key,
    )
    credibility_map = credibility_by_audience if isinstance(credibility_by_audience, Mapping) else {}
    for audience in audiences:
        credibility = credibility_map.get(audience, credibility_map.get(str(audience), 0.5))
        record_actor_evidence(
            sim,
            audience,
            proposition_key,
            occurrence["id"],
            polarity=position_key,
            strength=certainty_value * _unit(credibility, 0.5),
            exposure="heard",
            source_actor_eid=speaker,
            tags=("claim", "attributed"),
        )
        set_actor_perspective_attention(
            sim,
            audience,
            proposition_key,
            occurrence["id"],
            salience=salience,
            tick=tick,
        )
    return occurrence


def record_correction(
    sim,
    speaker_eid: Any,
    audience_eids: Iterable[Any],
    original_claim_id: str,
    *,
    revised_proposition_id: str | None = None,
    certainty: float = 0.7,
    credibility_by_audience: Mapping[Any, Any] | None = None,
    salience: float = 0.45,
    spoken_text: str = "",
    tick: int | None = None,
    dedupe_key: str | None = None,
) -> dict[str, Any]:
    """Append a correction without erasing the original attributed claim."""

    state = social_fact_graph_state(sim)
    speaker = _actor_id(speaker_eid)
    audiences = _actor_ids(audience_eids)
    original_key = _text(original_claim_id)
    original = state["occurrences"].get(original_key)
    if speaker is None or not audiences:
        raise ValueError("corrections require a speaker and audience")
    if not isinstance(original, dict) or original.get("kind") != "claim":
        raise KeyError(f"unknown original claim occurrence: {original_key}")
    original_propositions = tuple(original.get("proposition_ids", ()) or ())
    if not original_propositions:
        raise ValueError("original claim has no proposition")
    original_proposition = str(original_propositions[0])
    revised_key = _text(revised_proposition_id)
    proposition_ids = [original_proposition]
    if revised_key:
        if revised_key not in state["propositions"]:
            raise KeyError(f"unknown revised proposition: {revised_key}")
        if revised_key not in proposition_ids:
            proposition_ids.append(revised_key)
    certainty_value = _unit(certainty, 0.7)
    correction = record_occurrence(
        sim,
        "correction",
        actor_eids=(speaker, *audiences),
        proposition_ids=tuple(proposition_ids),
        source_occurrence_ids=(original_key,),
        payload={
            "speaker_eid": speaker,
            "audience_eids": audiences,
            "original_claim_id": original_key,
            "revised_proposition_id": revised_key or None,
            "stated_certainty": certainty_value,
            "spoken_text": _text(spoken_text),
        },
        flags=("speech", "attributed", "repair"),
        tick=tick,
        dedupe_key=dedupe_key,
    )
    credibility_map = credibility_by_audience if isinstance(credibility_by_audience, Mapping) else {}
    for audience in audiences:
        credibility = _unit(credibility_map.get(audience, credibility_map.get(str(audience), 0.5)), 0.5)
        strength = certainty_value * credibility
        record_actor_evidence(
            sim,
            audience,
            original_proposition,
            correction["id"],
            polarity="contradict",
            strength=strength,
            exposure="heard",
            source_actor_eid=speaker,
            tags=("correction", "attributed"),
        )
        set_actor_perspective_attention(
            sim,
            audience,
            original_proposition,
            correction["id"],
            salience=salience,
            tick=tick,
        )
        if revised_key:
            record_actor_evidence(
                sim,
                audience,
                revised_key,
                correction["id"],
                polarity="support",
                strength=strength,
                exposure="heard",
                source_actor_eid=speaker,
                tags=("correction", "revised_claim", "attributed"),
            )
            set_actor_perspective_attention(
                sim,
                audience,
                revised_key,
                correction["id"],
                salience=salience,
                tick=tick,
            )
    return correction


def _social_edge_key(from_actor_eid: int, toward_actor_eid: int) -> str:
    return f"{int(from_actor_eid)}:{int(toward_actor_eid)}"


def ensure_social_edge(
    sim,
    from_actor_eid: Any,
    toward_actor_eid: Any,
    *,
    relation_kind: str = "",
    contexts: Iterable[str] = (),
    dimensions: Mapping[str, Any] | None = None,
    tick: int | None = None,
) -> dict[str, Any]:
    """Create or read a directional social edge aggregate."""

    state = social_fact_graph_state(sim)
    from_actor = _actor_id(from_actor_eid)
    toward_actor = _actor_id(toward_actor_eid)
    if from_actor is None or toward_actor is None or from_actor == toward_actor:
        raise ValueError("social edges require two distinct positive actor ids")
    key = _social_edge_key(from_actor, toward_actor)
    edge = state["social_edges"].get(key)
    if not isinstance(edge, dict):
        base_dimensions = {}
        for raw_name, raw_value in dict(dimensions or {}).items():
            name = _token(raw_name)
            if name not in SOCIAL_DIMENSIONS:
                raise ValueError(f"unsupported social dimension: {name}")
            base_dimensions[name] = _unit(raw_value)
        edge = {
            "id": key,
            "from_actor_eid": from_actor,
            "toward_actor_eid": toward_actor,
            "relation_kind": _token(relation_kind),
            "contexts": tuple(sorted({_token(value) for value in tuple(contexts or ()) if _token(value)})),
            "dimensions": base_dimensions,
            "effects": {},
            "created_tick": _int(getattr(sim, "tick", 0) if tick is None else tick, 0),
            "last_changed_tick": _int(getattr(sim, "tick", 0) if tick is None else tick, 0),
        }
        state["social_edges"][key] = edge
    return copy.deepcopy(edge)


def social_edge(sim, from_actor_eid: Any, toward_actor_eid: Any) -> dict[str, Any] | None:
    from_actor = _actor_id(from_actor_eid)
    toward_actor = _actor_id(toward_actor_eid)
    if from_actor is None or toward_actor is None:
        return None
    edge = social_fact_graph_state(sim)["social_edges"].get(_social_edge_key(from_actor, toward_actor))
    return copy.deepcopy(edge) if isinstance(edge, dict) else None


def apply_social_effect(
    sim,
    from_actor_eid: Any,
    toward_actor_eid: Any,
    cause_occurrence_id: str,
    dimension: str,
    delta: float,
    *,
    effect_kind: str = "",
    effect_key: str | None = None,
    relation_kind: str = "",
    contexts: Iterable[str] = (),
) -> dict[str, Any]:
    """Apply one occurrence-backed relationship change at most once."""

    state = social_fact_graph_state(sim)
    cause_key = _text(cause_occurrence_id)
    dimension_key = _token(dimension)
    if cause_key not in state["occurrences"]:
        raise KeyError(f"unknown social effect cause: {cause_key}")
    if dimension_key not in SOCIAL_DIMENSIONS:
        raise ValueError(f"unsupported social dimension: {dimension_key}")
    try:
        requested_delta = float(delta)
    except (TypeError, ValueError):
        raise ValueError("social effect delta must be numeric") from None
    if not math.isfinite(requested_delta):
        raise ValueError("social effect delta must be finite")
    effect_kind_key = _token(effect_kind, fallback="social")
    from_actor = _actor_id(from_actor_eid)
    toward_actor = _actor_id(toward_actor_eid)
    ensure_social_edge(
        sim,
        from_actor,
        toward_actor,
        relation_kind=relation_kind,
        contexts=contexts,
    )
    edge_key = _social_edge_key(int(from_actor), int(toward_actor))
    edge = state["social_edges"][edge_key]
    effect_id = _text(effect_key) or f"{cause_key}:{effect_kind_key}:{dimension_key}"
    existing = edge["effects"].get(effect_id)
    if isinstance(existing, dict):
        expected = (cause_key, effect_kind_key, dimension_key, requested_delta)
        actual = (
            _text(existing.get("cause_occurrence_id")),
            _token(existing.get("effect_kind"), fallback="social"),
            _token(existing.get("dimension")),
            float(existing.get("requested_delta", 0.0)),
        )
        if actual != expected:
            raise ValueError(f"social effect identity collision: {effect_id}")
        return {
            "applied": False,
            "edge": copy.deepcopy(edge),
            "effect": copy.deepcopy(existing),
        }
    before = _unit(edge["dimensions"].get(dimension_key, 0.0))
    after = _unit(before + requested_delta)
    applied_delta = after - before
    effect = {
        "id": effect_id,
        "cause_occurrence_id": cause_key,
        "effect_kind": effect_kind_key,
        "dimension": dimension_key,
        "requested_delta": requested_delta,
        "applied_delta": applied_delta,
        "before": before,
        "after": after,
        "tick": _int(state["occurrences"][cause_key].get("tick"), 0),
    }
    edge["effects"][effect_id] = effect
    edge["dimensions"][dimension_key] = after
    edge["last_changed_tick"] = max(_int(edge.get("last_changed_tick"), 0), effect["tick"])
    return {
        "applied": True,
        "edge": copy.deepcopy(edge),
        "effect": copy.deepcopy(effect),
    }


def open_social_thread(
    sim,
    *,
    participants: Iterable[Any],
    proposition_ids: Iterable[str] = (),
    origin_occurrence_id: str | None = None,
    kind: str = "conversation",
    status: str = "open",
    awaiting_actor_eid: Any = None,
    tags: Iterable[str] = (),
    metadata: Mapping[str, Any] | None = None,
    thread_key: str | None = None,
    tick: int | None = None,
) -> dict[str, Any]:
    """Create or retrieve one durable continuing social thread."""

    state = social_fact_graph_state(sim)
    participant_ids = _actor_ids(participants)
    proposition_keys = _string_ids(proposition_ids)
    origin_key = _text(origin_occurrence_id)
    kind_key = _token(kind, fallback="conversation")
    status_key = _token(status, fallback="open")
    awaiting_actor = _actor_id(awaiting_actor_eid)
    stable_key = _text(thread_key)
    if not participant_ids:
        raise ValueError("social threads require at least one participant")
    if status_key not in THREAD_STATUSES:
        raise ValueError(f"unsupported social thread status: {status_key}")
    if awaiting_actor is not None and awaiting_actor not in participant_ids:
        raise ValueError("awaiting actor must be a thread participant")
    for proposition_id in proposition_keys:
        if proposition_id not in state["propositions"]:
            raise KeyError(f"unknown thread proposition: {proposition_id}")
    if origin_key and origin_key not in state["occurrences"]:
        raise KeyError(f"unknown thread origin occurrence: {origin_key}")
    opening_fingerprint = hashlib.sha256(_canonical_json({
        "participants": tuple(sorted(participant_ids)),
        "proposition_ids": tuple(sorted(proposition_keys)),
        "origin_occurrence_id": origin_key or None,
        "kind": kind_key,
        "status": status_key,
        "awaiting_actor_eid": awaiting_actor,
        "tags": tuple(sorted({_token(tag) for tag in tuple(tags or ()) if _token(tag)})),
        "metadata": _canonical_value(dict(metadata or {})),
    }).encode("utf-8")).hexdigest()
    if stable_key:
        existing_id = state["thread_by_key"].get(stable_key)
        existing = state["threads"].get(existing_id) if existing_id else None
        if isinstance(existing, dict):
            if _text(existing.get("opening_fingerprint")) != opening_fingerprint:
                raise ValueError(f"social thread identity collision: {stable_key}")
            return copy.deepcopy(existing)

    now = _int(getattr(sim, "tick", 0) if tick is None else tick, 0)
    thread_id = _next_record_id(state, "next_thread_id", "thread")
    occurrence_ids = tuple(value for value in (origin_key,) if value)
    thread = {
        "id": thread_id,
        "thread_key": stable_key or None,
        "kind": kind_key,
        "participants": participant_ids,
        "proposition_ids": proposition_keys,
        "occurrence_ids": occurrence_ids,
        "origin_occurrence_id": origin_key or None,
        "opening_fingerprint": opening_fingerprint,
        "status": status_key,
        "awaiting_actor_eid": awaiting_actor,
        "tags": tuple(sorted({_token(tag) for tag in tuple(tags or ()) if _token(tag)})),
        "metadata": _canonical_value(dict(metadata or {})),
        "created_tick": now,
        "last_tick": now,
    }
    state["threads"][thread_id] = thread
    if stable_key:
        state["thread_by_key"][stable_key] = thread_id
    return copy.deepcopy(thread)


def advance_social_thread(
    sim,
    thread_id: str,
    *,
    occurrence_id: str | None = None,
    status: str | None = None,
    awaiting_actor_eid: Any = _MISSING,
) -> dict[str, Any]:
    """Advance a mutable thread while retaining its immutable occurrences."""

    state = social_fact_graph_state(sim)
    thread_key = _text(thread_id)
    thread = state["threads"].get(thread_key)
    if not isinstance(thread, dict):
        raise KeyError(f"unknown social thread: {thread_key}")
    occurrence_key = _text(occurrence_id)
    if occurrence_key:
        occurrence = state["occurrences"].get(occurrence_key)
        if not isinstance(occurrence, dict):
            raise KeyError(f"unknown thread occurrence: {occurrence_key}")
        occurrence_actors = set(occurrence.get("actor_eids", ()) or ())
        if occurrence_actors and not occurrence_actors.issubset(set(thread.get("participants", ()) or ())):
            raise ValueError("thread occurrence contains an unregistered participant")
        occurrence_ids = list(thread.get("occurrence_ids", ()) or ())
        if occurrence_key not in occurrence_ids:
            occurrence_ids.append(occurrence_key)
            thread["occurrence_ids"] = tuple(occurrence_ids)
        proposition_ids = list(thread.get("proposition_ids", ()) or ())
        for proposition_id in tuple(occurrence.get("proposition_ids", ()) or ()):
            if proposition_id not in proposition_ids:
                proposition_ids.append(proposition_id)
        thread["proposition_ids"] = tuple(proposition_ids)
        thread["last_tick"] = max(_int(thread.get("last_tick"), 0), _int(occurrence.get("tick"), 0))
    if status is not None:
        status_key = _token(status)
        if status_key not in THREAD_STATUSES:
            raise ValueError(f"unsupported social thread status: {status_key}")
        thread["status"] = status_key
    if awaiting_actor_eid is not _MISSING:
        awaiting_actor = _actor_id(awaiting_actor_eid)
        if awaiting_actor is not None and awaiting_actor not in set(thread.get("participants", ()) or ()):
            raise ValueError("awaiting actor must be a thread participant")
        thread["awaiting_actor_eid"] = awaiting_actor
    return copy.deepcopy(thread)


def social_thread(sim, thread_id: str) -> dict[str, Any] | None:
    thread = social_fact_graph_state(sim)["threads"].get(_text(thread_id))
    return copy.deepcopy(thread) if isinstance(thread, dict) else None


def social_threads_for_actor(
    sim,
    actor_eid: Any,
    *,
    statuses: Iterable[str] | None = None,
    limit: int | None = None,
) -> tuple[dict[str, Any], ...]:
    """Return only threads in which ``actor_eid`` actually participates."""

    actor = _actor_id(actor_eid)
    if actor is None:
        return ()
    allowed = None
    if statuses is not None:
        allowed = {_token(value) for value in tuple(statuses or ()) if _token(value)}
    rows = []
    for thread in social_fact_graph_state(sim)["threads"].values():
        if not isinstance(thread, dict) or actor not in set(thread.get("participants", ()) or ()):
            continue
        if allowed is not None and str(thread.get("status", "")) not in allowed:
            continue
        rows.append(thread)
    rows.sort(key=lambda row: (_int(row.get("last_tick"), 0), str(row.get("id", ""))), reverse=True)
    if limit is not None:
        rows = rows[: max(0, int(limit))]
    return tuple(copy.deepcopy(row) for row in rows)


def _recency_score(now: int, tick: int, *, horizon: int = 7200) -> float:
    age = max(0, int(now) - int(tick))
    return 1.0 / (1.0 + (float(age) / float(max(1, horizon))))


def salient_people_for(
    sim,
    actor_eid: Any,
    *,
    purpose: str = "general",
    limit: int = 8,
) -> tuple[dict[str, Any], ...]:
    """Rank people present in the actor's own social history and perspective."""

    actor = _actor_id(actor_eid)
    if actor is None:
        return ()
    state = social_fact_graph_state(sim)
    now = _int(getattr(sim, "tick", 0), 0)
    scores: dict[int, float] = {}
    reasons: dict[int, set[str]] = {}

    def add(other: Any, score: float, reason: str) -> None:
        other_actor = _actor_id(other)
        if other_actor is None or other_actor == actor or score <= 0.0:
            return
        scores[other_actor] = scores.get(other_actor, 0.0) + float(score)
        reasons.setdefault(other_actor, set()).add(reason)

    for edge in state["social_edges"].values():
        if not isinstance(edge, dict) or _actor_id(edge.get("from_actor_eid")) != actor:
            continue
        dimensions = edge.get("dimensions") if isinstance(edge.get("dimensions"), dict) else {}
        social_score = (
            _unit(dimensions.get("closeness")) * 0.34
            + _unit(dimensions.get("trust")) * 0.22
            + _unit(dimensions.get("protectiveness")) * 0.16
            + _unit(dimensions.get("obligation")) * 0.12
            + _unit(dimensions.get("fear")) * 0.08
            + _unit(dimensions.get("resentment")) * 0.08
        )
        add(edge.get("toward_actor_eid"), social_score, "relationship")

    for thread in state["threads"].values():
        if not isinstance(thread, dict) or actor not in set(thread.get("participants", ()) or ()):
            continue
        status = str(thread.get("status", "open") or "open")
        unresolved = status not in {"closed", "corroborated", "retracted"}
        thread_score = 0.18 + (0.34 if unresolved else 0.0)
        thread_score *= _recency_score(now, _int(thread.get("last_tick"), 0))
        if _actor_id(thread.get("awaiting_actor_eid")) == actor:
            thread_score += 0.16
        for participant in tuple(thread.get("participants", ()) or ()):
            add(participant, thread_score, "unresolved_thread" if unresolved else "shared_thread")

    actor_perspectives = state["perspectives"].get(actor, {})
    visible_occurrence_ids = set()
    for perspective in actor_perspectives.values():
        if not isinstance(perspective, dict):
            continue
        perspective_salience = _unit(perspective.get("salience"))
        for occurrence_id, evidence in dict(perspective.get("evidence", {}) or {}).items():
            visible_occurrence_ids.add(occurrence_id)
            if isinstance(evidence, dict):
                add(evidence.get("source_actor_eid"), 0.08 + (perspective_salience * 0.18), "knowledge_source")

    for occurrence_id in tuple(state.get("occurrence_order", ()) or ()):
        occurrence = state["occurrences"].get(occurrence_id)
        if not isinstance(occurrence, dict):
            continue
        participants = set(occurrence.get("actor_eids", ()) or ())
        if actor not in participants and occurrence_id not in visible_occurrence_ids:
            continue
        occurrence_score = 0.08 * _recency_score(now, _int(occurrence.get("tick"), 0))
        flags = set(occurrence.get("flags", ()) or ())
        if "emotionally_salient" in flags:
            occurrence_score += 0.2
        if "repair" in flags:
            occurrence_score += 0.08
        for participant in participants:
            add(participant, occurrence_score, "shared_occurrence")

    purpose_key = _token(purpose, fallback="general")
    rows = [
        {
            "actor_eid": other,
            "score": round(score, 6),
            "reasons": tuple(sorted(reasons.get(other, ()))),
            "purpose": purpose_key,
        }
        for other, score in scores.items()
    ]
    rows.sort(key=lambda row: (-float(row["score"]), int(row["actor_eid"])))
    return tuple(rows[: max(0, int(limit))])


def actor_known_people_for_proposition(
    sim,
    actor_eid: Any,
    proposition_id: str,
    *,
    limit: int = 8,
) -> tuple[dict[str, Any], ...]:
    """Return people connected through the actor's evidence, never hidden truth."""

    actor = _actor_id(actor_eid)
    perspective = actor_perspective(sim, actor, proposition_id)
    if actor is None or not isinstance(perspective, dict):
        return ()
    state = social_fact_graph_state(sim)
    scores: dict[int, float] = {}
    reasons: dict[int, set[str]] = {}

    def add(other: Any, score: float, reason: str) -> None:
        other_actor = _actor_id(other)
        if other_actor is None or other_actor == actor:
            return
        scores[other_actor] = scores.get(other_actor, 0.0) + float(score)
        reasons.setdefault(other_actor, set()).add(reason)

    for occurrence_id, evidence in dict(perspective.get("evidence", {}) or {}).items():
        if not isinstance(evidence, dict):
            continue
        strength = _unit(evidence.get("strength"), 0.0)
        add(evidence.get("source_actor_eid"), 0.25 + (strength * 0.35), "evidence_source")
        occurrence = state["occurrences"].get(occurrence_id)
        if not isinstance(occurrence, dict):
            continue
        for participant in tuple(occurrence.get("actor_eids", ()) or ()):
            add(participant, 0.12 + (strength * 0.2), "known_occurrence")

    rows = [
        {
            "actor_eid": other,
            "score": round(score, 6),
            "reasons": tuple(sorted(reasons.get(other, ()))),
        }
        for other, score in scores.items()
    ]
    rows.sort(key=lambda row: (-float(row["score"]), int(row["actor_eid"])))
    return tuple(rows[: max(0, int(limit))])


def validate_social_fact_graph(sim) -> tuple[str, ...]:
    """Return referential-integrity errors without exposing graph content."""

    state = social_fact_graph_state(sim)
    errors = []
    referents = state["referents"]
    propositions = state["propositions"]
    occurrences = state["occurrences"]
    proposition_index = state["proposition_by_key"]
    occurrence_index = state["occurrence_by_dedupe_key"]
    occurrence_order = tuple(state.get("occurrence_order", ()) or ())
    occurrence_order_set = set(occurrence_order)
    if len(occurrence_order) != len(occurrence_order_set):
        errors.append("occurrence order contains duplicate ids")
    for occurrence_id in occurrence_order:
        if occurrence_id not in occurrences:
            errors.append(f"occurrence order has unknown id {occurrence_id}")
    for semantic_key, proposition_id in proposition_index.items():
        proposition = propositions.get(proposition_id)
        if not isinstance(proposition, dict):
            errors.append(f"proposition index {semantic_key} has unknown id {proposition_id}")
        elif _text(proposition.get("semantic_key")) != _text(semantic_key):
            errors.append(f"proposition index {semantic_key} disagrees with its record")
    for dedupe_key, occurrence_id in occurrence_index.items():
        occurrence = occurrences.get(occurrence_id)
        if not isinstance(occurrence, dict):
            errors.append(f"occurrence index {dedupe_key} has unknown id {occurrence_id}")
        elif _text(occurrence.get("dedupe_key")) != _text(dedupe_key):
            errors.append(f"occurrence index {dedupe_key} disagrees with its record")
    for proposition_id, proposition in propositions.items():
        if not isinstance(proposition, dict):
            errors.append(f"proposition {proposition_id} is not a record")
            continue
        if proposition.get("subject_ref") not in referents:
            errors.append(f"proposition {proposition_id} has unknown subject")
        object_ref = proposition.get("object_ref")
        if object_ref and object_ref not in referents:
            errors.append(f"proposition {proposition_id} has unknown object")
        semantic_key = _text(proposition.get("semantic_key"))
        if proposition_index.get(semantic_key) != proposition_id:
            errors.append(f"proposition {proposition_id} is missing from its semantic index")
    for occurrence_id, occurrence in occurrences.items():
        if not isinstance(occurrence, dict):
            errors.append(f"occurrence {occurrence_id} is not a record")
            continue
        for proposition_id in tuple(occurrence.get("proposition_ids", ()) or ()):
            if proposition_id not in propositions:
                errors.append(f"occurrence {occurrence_id} has unknown proposition {proposition_id}")
        for referent_id in tuple(occurrence.get("referent_ids", ()) or ()):
            if referent_id not in referents:
                errors.append(f"occurrence {occurrence_id} has unknown referent {referent_id}")
        for source_id in tuple(occurrence.get("source_occurrence_ids", ()) or ()):
            if source_id not in occurrences:
                errors.append(f"occurrence {occurrence_id} has unknown source {source_id}")
        dedupe_key = _text(occurrence.get("dedupe_key"))
        if dedupe_key and occurrence_index.get(dedupe_key) != occurrence_id:
            errors.append(f"occurrence {occurrence_id} is missing from its dedupe index")
    for occurrence_id in occurrences:
        if occurrence_id not in occurrence_order_set:
            errors.append(f"occurrence {occurrence_id} is missing from occurrence order")
    for actor_eid, actor_rows in state["perspectives"].items():
        if _actor_id(actor_eid) is None or not isinstance(actor_rows, dict):
            errors.append(f"invalid perspective actor {actor_eid}")
            continue
        for proposition_id, perspective in actor_rows.items():
            if proposition_id not in propositions:
                errors.append(f"actor {actor_eid} has unknown proposition {proposition_id}")
            for occurrence_id, evidence in dict((perspective or {}).get("evidence", {}) or {}).items():
                if occurrence_id not in occurrences:
                    errors.append(f"actor {actor_eid} has unknown evidence {occurrence_id}")
                elif proposition_id not in set(occurrences[occurrence_id].get("proposition_ids", ()) or ()):
                    errors.append(
                        f"actor {actor_eid} evidence {occurrence_id} does not cite "
                        f"proposition {proposition_id}"
                    )
                if isinstance(evidence, dict) and _text(evidence.get("occurrence_id")) != occurrence_id:
                    errors.append(f"actor {actor_eid} evidence key disagrees with its record")
                if isinstance(evidence, dict) and "salience" in evidence:
                    errors.append(f"actor {actor_eid} evidence {occurrence_id} carries mutable salience")
            attention = (perspective or {}).get("attention", {})
            if not isinstance(attention, dict):
                errors.append(f"actor {actor_eid} perspective attention is not a record")
                attention = {}
            for occurrence_id, attention_record in attention.items():
                if occurrence_id not in dict((perspective or {}).get("evidence", {}) or {}):
                    errors.append(f"actor {actor_eid} attention has unknown evidence {occurrence_id}")
                if not isinstance(attention_record, dict):
                    errors.append(f"actor {actor_eid} attention {occurrence_id} is not a record")
                    continue
                raw_salience = attention_record.get("salience", 0.0)
                try:
                    valid_salience = math.isfinite(float(raw_salience)) and 0.0 <= float(raw_salience) <= 1.0
                except (TypeError, ValueError):
                    valid_salience = False
                if not valid_salience:
                    errors.append(f"actor {actor_eid} attention {occurrence_id} has invalid salience")
            derived_salience = _combined_weight(
                item.get("salience", 0.0)
                for item in attention.values()
                if isinstance(item, dict)
            )
            if abs(_unit((perspective or {}).get("salience"), 0.0) - derived_salience) > 1e-9:
                errors.append(f"actor {actor_eid} perspective salience disagrees with attention")
    for edge_id, edge in state["social_edges"].items():
        if not isinstance(edge, dict):
            errors.append(f"social edge {edge_id} is not a record")
            continue
        for effect in dict(edge.get("effects", {}) or {}).values():
            cause = (effect or {}).get("cause_occurrence_id")
            if cause not in occurrences:
                errors.append(f"social edge {edge_id} has unknown effect cause {cause}")
    for thread_id, thread in state["threads"].items():
        if not isinstance(thread, dict):
            errors.append(f"thread {thread_id} is not a record")
            continue
        for proposition_id in tuple(thread.get("proposition_ids", ()) or ()):
            if proposition_id not in propositions:
                errors.append(f"thread {thread_id} has unknown proposition {proposition_id}")
        for occurrence_id in tuple(thread.get("occurrence_ids", ()) or ()):
            if occurrence_id not in occurrences:
                errors.append(f"thread {thread_id} has unknown occurrence {occurrence_id}")
        awaiting_actor = _actor_id(thread.get("awaiting_actor_eid"))
        if awaiting_actor is not None and awaiting_actor not in set(thread.get("participants", ()) or ()):
            errors.append(f"thread {thread_id} awaits a nonparticipant")
        stable_key = _text(thread.get("thread_key"))
        if stable_key and state["thread_by_key"].get(stable_key) != thread_id:
            errors.append(f"thread {thread_id} is missing from its stable-key index")
    for stable_key, thread_id in state["thread_by_key"].items():
        thread = state["threads"].get(thread_id)
        if not isinstance(thread, dict):
            errors.append(f"thread index {stable_key} has unknown id {thread_id}")
        elif _text(thread.get("thread_key")) != _text(stable_key):
            errors.append(f"thread index {stable_key} disagrees with its record")
    return tuple(errors)


def debug_social_fact_trace(sim, proposition_id: str) -> dict[str, Any]:
    """Return an explicitly omniscient developer trace for one proposition."""

    state = social_fact_graph_state(sim)
    proposition_key = _text(proposition_id)
    proposition = state["propositions"].get(proposition_key)
    if not isinstance(proposition, dict):
        return {}
    occurrence_ids = [
        occurrence_id
        for occurrence_id in tuple(state.get("occurrence_order", ()) or ())
        if proposition_key in set((state["occurrences"].get(occurrence_id) or {}).get("proposition_ids", ()) or ())
    ]
    perspectives = {
        actor_eid: rows[proposition_key]
        for actor_eid, rows in state["perspectives"].items()
        if isinstance(rows, dict) and proposition_key in rows
    }
    threads = {
        thread_id: thread
        for thread_id, thread in state["threads"].items()
        if isinstance(thread, dict) and proposition_key in set(thread.get("proposition_ids", ()) or ())
    }
    return copy.deepcopy({
        "proposition": proposition,
        "occurrences": [state["occurrences"][occurrence_id] for occurrence_id in occurrence_ids],
        "perspectives": perspectives,
        "threads": threads,
    })


__all__ = [
    "EVIDENCE_POLARITIES",
    "EXPOSURE_LEVELS",
    "PERSPECTIVE_STANCES",
    "SOCIAL_DIMENSIONS",
    "SOCIAL_FACT_GRAPH_SCHEMA_VERSION",
    "THREAD_STATUSES",
    "actor_known_people_for_proposition",
    "actor_knows_proposition",
    "actor_perspective",
    "advance_social_thread",
    "apply_social_effect",
    "debug_social_fact_trace",
    "ensure_proposition",
    "ensure_social_edge",
    "occurrence_record",
    "open_social_thread",
    "proposition_record",
    "record_actor_evidence",
    "record_claim",
    "record_correction",
    "record_occurrence",
    "referent_record",
    "register_referent",
    "salient_people_for",
    "set_actor_perspective_attention",
    "social_edge",
    "social_fact_graph_state",
    "social_thread",
    "social_threads_for_actor",
    "validate_social_fact_graph",
]
