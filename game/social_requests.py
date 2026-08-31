"""Durable actor-to-actor requests with embodied NPC follow-through.

The request ledger is mutable operational state.  Every socially meaningful
transition is also written as an immutable Social Fact occurrence, so callers
can refer to the same promise later without treating the ledger as truth that
every actor somehow knows.

The runtime client is intentionally local: people make requests while actually
in contact, and accepted requests are fulfilled through ordinary movement
toward the requester's last-seen position.  Completion is verified against the
actors' real current positions.  Player-facing dialogue uses the same ledger;
there is no parallel quest-shaped favor state.
"""

from __future__ import annotations

import copy
import random
from collections.abc import Iterable, Mapping
from typing import Any

from engine.events import Event
from engine.systems import System
from game.components import (
    AI,
    Inventory,
    NPCMemory,
    NPCNeeds,
    NPCSocial,
    NPCTraits,
    NPCWill,
    PlayerControlled,
    Position,
    Vitality,
)
from game.items import ITEM_CATALOG
from game.social_fact_graph import (
    advance_social_thread,
    apply_social_effect,
    open_social_thread,
    record_occurrence,
    social_edge,
    social_thread,
)


SOCIAL_REQUEST_SCHEMA_VERSION = 2
SOCIAL_REQUEST_INTENT = "fulfilling_social_request"

REQUEST_STATUSES = {
    "proposed",
    "deferred",
    "countered",
    "accepted",
    "in_progress",
    "fulfilled",
    "refused",
    "failed",
    "expired",
    "withdrawn",
}
TERMINAL_REQUEST_STATUSES = {"fulfilled", "refused", "failed", "expired", "withdrawn"}

DEFAULT_DEADLINE_TICKS = 120
PAIR_REQUEST_COOLDOWN_TICKS = 180
PERSONAL_REQUEST_COOLDOWN_TICKS = 240
PERSONAL_FAVOR_MIN_MEETINGS = 2
PERSONAL_FAVOR_RENEGOTIATION_TICKS = 48
FOLLOWUP_MIN_AGE_TICKS = 10

PLAYER_FAVOR_TOPIC_IDS = frozenset({
    "favor_invite",
    "favor_why",
    "favor_accept",
    "favor_counter_later",
    "favor_defer",
    "favor_decline",
    "favor_fulfill",
    "favor_renegotiate",
    "favor_admit_failure",
    "favor_request_water",
    "favor_request_food",
    "favor_request_medical",
    "favor_request_check_in",
    "favor_check_status",
    "favor_refusal_why",
    "favor_ack_warm",
    "favor_ack_simple",
    "favor_ack_reserved",
})

ITEM_FAVOR_PROFILES = {
    "bring_water": {
        "need_attr": "thirst",
        "threshold": 46.0,
        "request_threshold": 72.0,
        "base_score": 0.68,
        "urgency": 0.76,
        "deadline_ticks": 80,
        "reason": "thirst",
        "item_ids": ("bottled_water", "hydration_salts", "sealed_juice"),
        "request_line": "I'm running dry. Could you spare some water?",
        "reason_line": "I haven't had anything to drink in a while, and I'm feeling it.",
        "summary": "someone asking a companion to bring over something to drink",
        "detail": "a personal request for a drink",
        "item_word": "water or another drink",
        "cue": "They look dry-mouthed and keep swallowing before they speak.",
        "offer_label": "Ask if they need something to drink",
        "offer_line": "You look thirsty. Do you need something to drink?",
        "ask_label": "Ask them to spare you something to drink",
        "ask_line": "Could you spare me something to drink?",
        "fulfill_line": "I brought you something to drink.",
        "completion_quote": "I brought you something to drink.",
        "completion_summary": "someone delivering a drink they had promised to bring",
        "missing_line": "You don't have something to drink for them yet.",
    },
    "bring_food": {
        "need_attr": "hunger",
        "threshold": 48.0,
        "request_threshold": 72.0,
        "base_score": 0.66,
        "urgency": 0.70,
        "deadline_ticks": 100,
        "reason": "hunger",
        "item_ids": (
            "street_ration",
            "protein_wrap",
            "noodle_cup",
            "instant_soup_pack",
            "energy_bar",
            "fruit_cup",
        ),
        "request_line": "I haven't eaten enough today. Could you spare me something to eat?",
        "reason_line": "I keep trying to ignore how hungry I am, but it is catching up with me.",
        "summary": "someone asking a companion to bring over something to eat",
        "detail": "a personal request for food",
        "item_word": "food",
        "cue": "They keep glancing at nearby food and rubbing at their stomach.",
        "offer_label": "Ask if they need something to eat",
        "offer_line": "You look like you have not eaten. Do you need something?",
        "ask_label": "Ask them to spare you something to eat",
        "ask_line": "Could you spare me something to eat?",
        "fulfill_line": "I brought you something to eat.",
        "completion_quote": "I brought you something to eat.",
        "completion_summary": "someone delivering food they had promised to bring",
        "missing_line": "You don't have something to eat for them yet.",
    },
    "bring_medical": {
        "need_attr": "health",
        "threshold": 58.0,
        "request_threshold": 78.0,
        "base_score": 0.72,
        "urgency": 0.82,
        "deadline_ticks": 72,
        "reason": "injury",
        "item_ids": ("med_gel", "micro_medkit", "trauma_foam", "field_dressing", "bandage_roll"),
        "request_line": "I'm hurt. Could you spare some medical supplies?",
        "reason_line": "I am trying to stay upright, but this is more than I can just shake off.",
        "summary": "someone asking a companion to bring medical supplies",
        "detail": "a personal request for medical supplies",
        "item_word": "medical supplies",
        "cue": "They are favoring an injury and trying not to show how much it hurts.",
        "offer_label": "Ask if they need medical supplies",
        "offer_line": "You look hurt. Do you need medical supplies?",
        "ask_label": "Ask them to spare you medical supplies",
        "ask_line": "Could you spare me some medical supplies?",
        "fulfill_line": "I brought you medical supplies.",
        "completion_quote": "I brought you medical supplies.",
        "completion_summary": "someone delivering medical supplies they had promised to bring",
        "missing_line": "You don't have medical supplies for them yet.",
    },
}
ITEM_FAVOR_KINDS = frozenset(ITEM_FAVOR_PROFILES)
PLAYER_ITEM_REQUEST_TOPICS = {
    "favor_request_water": "bring_water",
    "favor_request_food": "bring_food",
    "favor_request_medical": "bring_medical",
}

_INTERRUPTIBLE_STATES = {
    "idle",
    "lounging",
    "resting",
    "shopping",
    "socializing",
    "seeking_social",
    "working",
}


def _int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _token(value: Any) -> str:
    return str(value or "").strip().lower().replace(" ", "_")


def _actor(value: Any) -> int:
    actor_eid = _int(value, 0)
    if actor_eid <= 0:
        raise ValueError("social requests require positive actor ids")
    return actor_eid


def _string_ids(values: Iterable[Any]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value).strip() for value in tuple(values or ()) if str(value).strip()))


def _request_id_number(value: Any) -> int:
    text = str(value or "").strip()
    if not text.startswith("request:"):
        return 0
    return _int(text.split(":", 1)[1], 0)


def _empty_state() -> dict[str, Any]:
    return {
        "schema_version": SOCIAL_REQUEST_SCHEMA_VERSION,
        "next_request_id": 1,
        "requests": {},
        "pair_cooldowns": {},
        "actor_request_cooldowns": {},
    }


def social_request_state(sim) -> dict[str, Any]:
    """Return normalized, save-visible request state."""

    raw = getattr(sim, "social_requests", None)
    if not isinstance(raw, dict) or not raw:
        raw = _empty_state()
        sim.social_requests = raw
        return raw
    version = _int(raw.get("schema_version"), 0)
    if version > SOCIAL_REQUEST_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported social request schema: {version} > {SOCIAL_REQUEST_SCHEMA_VERSION}"
        )
    if version <= 0:
        raw = _empty_state()
        sim.social_requests = raw
        return raw
    raw["schema_version"] = SOCIAL_REQUEST_SCHEMA_VERSION
    if not isinstance(raw.get("requests"), dict):
        raw["requests"] = {}
    if not isinstance(raw.get("pair_cooldowns"), dict):
        raw["pair_cooldowns"] = {}
    if not isinstance(raw.get("actor_request_cooldowns"), dict):
        raw["actor_request_cooldowns"] = {}
    highest = max((_request_id_number(key) for key in raw["requests"]), default=0)
    raw["next_request_id"] = max(highest + 1, _int(raw.get("next_request_id"), 1), 1)
    return raw


def social_request(sim, request_id: Any) -> dict[str, Any] | None:
    row = social_request_state(sim)["requests"].get(str(request_id or "").strip())
    return copy.deepcopy(row) if isinstance(row, dict) else None


def social_requests_for_actor(
    sim,
    actor_eid: Any,
    *,
    statuses: Iterable[str] | None = None,
) -> tuple[dict[str, Any], ...]:
    actor_id = _actor(actor_eid)
    allowed = {_token(value) for value in tuple(statuses or ()) if _token(value)}
    rows = []
    for row in social_request_state(sim)["requests"].values():
        if not isinstance(row, dict):
            continue
        participants = {
            _int(row.get("requester_eid"), 0),
            _int(row.get("recipient_eid"), 0),
            _int(row.get("beneficiary_eid"), 0),
        }
        if actor_id not in participants:
            continue
        if allowed and _token(row.get("status")) not in allowed:
            continue
        rows.append(copy.deepcopy(row))
    rows.sort(key=lambda item: (_int(item.get("created_tick"), 0), str(item.get("id", ""))))
    return tuple(rows)


def _remember(sim, actor_eid: int, kind: str, *, strength: float = 0.8, **data: Any) -> None:
    memory = sim.ecs.get(NPCMemory).get(actor_eid)
    if memory is not None:
        memory.remember(_int(getattr(sim, "tick", 0), 0), kind, strength=strength, **data)


def _position_tuple(sim, actor_eid: int) -> tuple[int, int, int] | None:
    pos = sim.ecs.get(Position).get(actor_eid)
    if pos is None:
        return None
    return (int(pos.x), int(pos.y), int(pos.z))


def _append_occurrence(row: dict[str, Any], occurrence_id: str) -> None:
    occurrence_ids = list(row.get("occurrence_ids", ()) or ())
    if occurrence_id and occurrence_id not in occurrence_ids:
        occurrence_ids.append(occurrence_id)
    row["occurrence_ids"] = tuple(occurrence_ids)


def create_social_request(
    sim,
    *,
    requester_eid: Any,
    recipient_eid: Any,
    kind: str,
    beneficiary_eid: Any = None,
    proposition_ids: Iterable[str] = (),
    referent_ids: Iterable[str] = (),
    reason: str = "",
    terms: Mapping[str, Any] | None = None,
    privacy: str = "ordinary",
    urgency: float = 0.5,
    due_tick: int | None = None,
    deadline_tick: int | None = None,
    thread_key: str | None = None,
) -> dict[str, Any]:
    """Create one actor-routed request without presuming its answer."""

    requester = _actor(requester_eid)
    recipient = _actor(recipient_eid)
    if requester == recipient:
        raise ValueError("an actor cannot make a social request of themself")
    beneficiary = requester if beneficiary_eid is None else _actor(beneficiary_eid)
    kind_key = _token(kind)
    if not kind_key:
        raise ValueError("social requests require a kind")
    state = social_request_state(sim)
    number = max(1, _int(state.get("next_request_id"), 1))
    state["next_request_id"] = number + 1
    request_id = f"request:{number}"
    now = _int(getattr(sim, "tick", 0), 0)
    due = max(now, _int(due_tick, now))
    deadline = max(due + 1, _int(deadline_tick, now + DEFAULT_DEADLINE_TICKS))
    propositions = _string_ids(proposition_ids)
    referents = _string_ids(referent_ids)
    canonical_terms = copy.deepcopy(dict(terms or {}))

    proposed = record_occurrence(
        sim,
        "social_request_proposed",
        actor_eids=(requester, recipient, beneficiary),
        proposition_ids=propositions,
        referent_ids=referents,
        payload={
            "request_id": request_id,
            "request_kind": kind_key,
            "requester_eid": requester,
            "recipient_eid": recipient,
            "beneficiary_eid": beneficiary,
            "reason": str(reason or "").strip(),
            "terms": canonical_terms,
            "privacy": _token(privacy) or "ordinary",
            "urgency": max(0.0, min(1.0, _float(urgency, 0.5))),
            "due_tick": due,
            "deadline_tick": deadline,
        },
        flags=("spoken", "actor_routed"),
        dedupe_key=f"social-request:{request_id}:proposed",
    )
    thread = open_social_thread(
        sim,
        participants=(requester, recipient, beneficiary),
        proposition_ids=propositions,
        origin_occurrence_id=proposed["id"],
        kind="request",
        status="awaiting_response",
        awaiting_actor_eid=recipient,
        tags=("social_request", kind_key),
        metadata={
            "request_id": request_id,
            "request_kind": kind_key,
            "privacy": _token(privacy) or "ordinary",
        },
        thread_key=thread_key or f"social-request:{request_id}",
    )
    row = {
        "id": request_id,
        "kind": kind_key,
        "status": "proposed",
        "requester_eid": requester,
        "recipient_eid": recipient,
        "beneficiary_eid": beneficiary,
        "reason": str(reason or "").strip(),
        "terms": canonical_terms,
        "privacy": _token(privacy) or "ordinary",
        "urgency": max(0.0, min(1.0, _float(urgency, 0.5))),
        "proposition_ids": propositions,
        "referent_ids": referents,
        "thread_id": thread["id"],
        "occurrence_ids": (proposed["id"],),
        "created_tick": now,
        "last_changed_tick": now,
        "due_tick": due,
        "deadline_tick": deadline,
        "awaiting_actor_eid": recipient,
        "target_snapshot": _position_tuple(sim, requester),
        "response": None,
        "response_tick": None,
        "completed_tick": None,
        "outcome_reason": None,
        "followup_surfaced_tick": None,
    }
    state["requests"][request_id] = row
    _remember(
        sim,
        requester,
        "social_request_made",
        request_id=request_id,
        request_kind=kind_key,
        other_eid=recipient,
        beneficiary_eid=beneficiary,
    )
    _remember(
        sim,
        recipient,
        "social_request_received",
        request_id=request_id,
        request_kind=kind_key,
        other_eid=requester,
        beneficiary_eid=beneficiary,
    )
    return copy.deepcopy(row)


def respond_to_social_request(
    sim,
    request_id: Any,
    *,
    actor_eid: Any,
    outcome: str,
    counter_terms: Mapping[str, Any] | None = None,
    defer_until_tick: int | None = None,
    reason: str = "",
) -> dict[str, Any]:
    """Answer, counter, or delay a request as its currently awaited actor."""

    state = social_request_state(sim)
    key = str(request_id or "").strip()
    row = state["requests"].get(key)
    if not isinstance(row, dict):
        raise KeyError(f"unknown social request: {key}")
    status = _token(row.get("status"))
    if status in TERMINAL_REQUEST_STATUSES or status in {"accepted", "in_progress"}:
        return copy.deepcopy(row)
    actor_id = _actor(actor_eid)
    if actor_id != _int(row.get("awaiting_actor_eid"), 0):
        raise ValueError("only the actor currently holding the request may answer it")
    outcome_key = _token(outcome)
    if outcome_key not in {"accepted", "refused", "countered", "deferred"}:
        raise ValueError(f"unsupported social request response: {outcome_key}")
    now = _int(getattr(sim, "tick", 0), 0)

    if outcome_key == "countered":
        merged_terms = dict(row.get("terms", {}) or {})
        merged_terms.update(copy.deepcopy(dict(counter_terms or {})))
        row["terms"] = merged_terms
        requester = _int(row.get("requester_eid"), 0)
        recipient = _int(row.get("recipient_eid"), 0)
        next_awaiting = recipient if actor_id == requester else requester
        thread_status = "awaiting_response"
    elif outcome_key == "deferred":
        row["response_after_tick"] = max(now + 1, _int(defer_until_tick, now + 10))
        next_awaiting = actor_id
        thread_status = "considering"
    else:
        next_awaiting = None
        thread_status = "acted" if outcome_key == "accepted" else "closed"

    response = record_occurrence(
        sim,
        f"social_request_{outcome_key}",
        actor_eids=(
            _int(row.get("requester_eid"), 0),
            _int(row.get("recipient_eid"), 0),
            _int(row.get("beneficiary_eid"), 0),
        ),
        proposition_ids=tuple(row.get("proposition_ids", ()) or ()),
        referent_ids=tuple(row.get("referent_ids", ()) or ()),
        source_occurrence_ids=(tuple(row.get("occurrence_ids", ()) or ())[-1],),
        payload={
            "request_id": key,
            "request_kind": row.get("kind"),
            "responding_actor_eid": actor_id,
            "outcome": outcome_key,
            "reason": str(reason or "").strip(),
            "terms": copy.deepcopy(dict(row.get("terms", {}) or {})),
            "defer_until_tick": row.get("response_after_tick"),
        },
        flags=("spoken", "actor_routed"),
        dedupe_key=f"social-request:{key}:response:{len(tuple(row.get('occurrence_ids', ()) or ())) + 1}",
    )
    _append_occurrence(row, response["id"])
    row["status"] = outcome_key
    row["response"] = outcome_key
    row["response_reason"] = str(reason or "").strip()
    row["response_tick"] = now
    row["last_changed_tick"] = now
    row["awaiting_actor_eid"] = next_awaiting
    if outcome_key == "refused":
        row["completed_tick"] = now
        row["outcome_reason"] = _token(reason) or "refused"
    if outcome_key == "accepted":
        row["target_snapshot"] = _position_tuple(sim, _int(row.get("requester_eid"), 0))
        obligation_result = apply_social_effect(
            sim,
            _int(row.get("recipient_eid"), 0),
            _int(row.get("requester_eid"), 0),
            response["id"],
            "obligation",
            0.16,
            effect_kind="accepted_request",
            effect_key=f"{key}:performance-obligation:opened",
            contexts=("social_request", _token(row.get("kind"))),
        )
        row["performance_obligation_delta"] = _float(
            (obligation_result.get("effect") or {}).get("applied_delta"),
            0.0,
        )
        delay_ticks = max(0, _int((row.get("terms") or {}).get("delay_ticks"), 0))
        row["due_tick"] = max(_int(row.get("due_tick"), now), now + delay_ticks)
        row["deadline_tick"] = max(_int(row.get("deadline_tick"), now + 1), row["due_tick"] + 1)
    advance_social_thread(
        sim,
        row["thread_id"],
        occurrence_id=response["id"],
        status=thread_status,
        awaiting_actor_eid=next_awaiting,
    )
    requester = _int(row.get("requester_eid"), 0)
    recipient = _int(row.get("recipient_eid"), 0)
    _remember(
        sim,
        requester,
        "social_request_response",
        request_id=key,
        request_kind=row.get("kind"),
        outcome=outcome_key,
        other_eid=recipient,
    )
    _remember(
        sim,
        recipient,
        "social_request_response",
        request_id=key,
        request_kind=row.get("kind"),
        outcome=outcome_key,
        other_eid=requester,
    )
    return copy.deepcopy(row)


def resolve_social_request(
    sim,
    request_id: Any,
    *,
    fulfilled: bool,
    reason: str,
) -> dict[str, Any]:
    """Close an accepted request and apply outcome-backed social effects once."""

    state = social_request_state(sim)
    key = str(request_id or "").strip()
    row = state["requests"].get(key)
    if not isinstance(row, dict):
        raise KeyError(f"unknown social request: {key}")
    if _token(row.get("status")) in TERMINAL_REQUEST_STATUSES:
        return copy.deepcopy(row)
    if _token(row.get("status")) not in {"accepted", "in_progress"}:
        raise ValueError("only an accepted social request can be resolved")
    now = _int(getattr(sim, "tick", 0), 0)
    outcome = "fulfilled" if fulfilled else ("expired" if _token(reason) == "deadline" else "failed")
    occurrence = record_occurrence(
        sim,
        f"social_request_{outcome}",
        actor_eids=(
            _int(row.get("requester_eid"), 0),
            _int(row.get("recipient_eid"), 0),
            _int(row.get("beneficiary_eid"), 0),
        ),
        proposition_ids=tuple(row.get("proposition_ids", ()) or ()),
        referent_ids=tuple(row.get("referent_ids", ()) or ()),
        source_occurrence_ids=(tuple(row.get("occurrence_ids", ()) or ())[-1],),
        payload={
            "request_id": key,
            "request_kind": row.get("kind"),
            "outcome": outcome,
            "reason": _token(reason),
            "terms": copy.deepcopy(dict(row.get("terms", {}) or {})),
        },
        flags=("embodied", "actor_routed"),
        dedupe_key=f"social-request:{key}:resolution",
    )
    _append_occurrence(row, occurrence["id"])
    row["status"] = outcome
    row["outcome_reason"] = _token(reason)
    row["completed_tick"] = now
    row["last_changed_tick"] = now
    row["awaiting_actor_eid"] = None
    requester = _int(row.get("requester_eid"), 0)
    recipient = _int(row.get("recipient_eid"), 0)
    apply_social_effect(
        sim,
        recipient,
        requester,
        occurrence["id"],
        "obligation",
        -max(0.0, _float(row.get("performance_obligation_delta"), 0.16)),
        effect_kind="request_resolved",
        effect_key=f"{key}:performance-obligation:closed",
        contexts=("social_request", _token(row.get("kind"))),
    )
    if fulfilled:
        for dimension, delta in (("reliability", 0.08), ("trust", 0.03), ("obligation", 0.08)):
            apply_social_effect(
                sim,
                requester,
                recipient,
                occurrence["id"],
                dimension,
                delta,
                effect_kind="request_fulfilled",
                effect_key=f"{key}:fulfilled:{dimension}",
                contexts=("social_request", _token(row.get("kind"))),
            )
    else:
        for dimension, delta in (("reliability", -0.12), ("trust", -0.05), ("resentment", 0.04)):
            apply_social_effect(
                sim,
                requester,
                recipient,
                occurrence["id"],
                dimension,
                delta,
                effect_kind="request_broken",
                effect_key=f"{key}:broken:{dimension}",
                contexts=("social_request", _token(row.get("kind"))),
            )
    advance_social_thread(
        sim,
        row["thread_id"],
        occurrence_id=occurrence["id"],
        status="closed",
        awaiting_actor_eid=None,
    )
    memory_kind = "social_request_fulfilled" if fulfilled else "social_request_broken"
    _remember(
        sim,
        requester,
        memory_kind,
        strength=0.95,
        request_id=key,
        request_kind=row.get("kind"),
        other_eid=recipient,
        reason=_token(reason),
    )
    _remember(
        sim,
        recipient,
        memory_kind,
        strength=0.95,
        request_id=key,
        request_kind=row.get("kind"),
        other_eid=requester,
        reason=_token(reason),
    )
    return copy.deepcopy(row)


def validate_social_requests(sim) -> tuple[str, ...]:
    """Return persistence and graph-reference invariant failures."""

    failures: list[str] = []
    state = social_request_state(sim)
    for request_id, row in state["requests"].items():
        if not isinstance(row, dict):
            failures.append(f"{request_id}: request row is not a mapping")
            continue
        if str(row.get("id", "")) != str(request_id):
            failures.append(f"{request_id}: mismatched id")
        if _token(row.get("status")) not in REQUEST_STATUSES:
            failures.append(f"{request_id}: invalid status {row.get('status')}")
        requester = _int(row.get("requester_eid"), 0)
        recipient = _int(row.get("recipient_eid"), 0)
        if requester <= 0 or recipient <= 0 or requester == recipient:
            failures.append(f"{request_id}: invalid actor routing")
        thread = social_thread(sim, row.get("thread_id"))
        if not isinstance(thread, dict):
            failures.append(f"{request_id}: missing social thread")
        elif {requester, recipient}.difference(set(thread.get("participants", ()) or ())):
            failures.append(f"{request_id}: thread is missing a participant")
        if _int(row.get("deadline_tick"), 0) <= _int(row.get("due_tick"), -1):
            failures.append(f"{request_id}: deadline does not follow due tick")
    return tuple(failures)


class NPCSocialRequestSystem(System):
    """Create requests at real conversations and carry accepted promises out."""

    def __init__(self, sim):
        super().__init__(sim)
        self.sim.social_request_system = self
        social_request_state(sim)
        self.sim.events.subscribe("npc_social_request_arrived", self.on_request_arrived)
        self.sim.events.subscribe("npc_social_request_failed", self.on_request_failed)

    def _pair_key(self, requester: int, recipient: int) -> str:
        return f"{int(requester)}:{int(recipient)}"

    def _actor_key(self, actor_eid: int) -> str:
        return str(int(actor_eid))

    def _request_cooldown_ready(self, requester: int, recipient: int) -> bool:
        state = social_request_state(self.sim)
        now = _int(getattr(self.sim, "tick", 0), 0)
        pair_ready = _int(state["pair_cooldowns"].get(self._pair_key(requester, recipient)), 0)
        actor_ready = _int(state["actor_request_cooldowns"].get(self._actor_key(requester)), 0)
        return now >= pair_ready and now >= actor_ready

    def _mark_request_cooldowns(self, requester: int, recipient: int) -> None:
        state = social_request_state(self.sim)
        now = _int(getattr(self.sim, "tick", 0), 0)
        pair_ready = now + PAIR_REQUEST_COOLDOWN_TICKS
        state["pair_cooldowns"][self._pair_key(requester, recipient)] = pair_ready
        state["pair_cooldowns"][self._pair_key(recipient, requester)] = pair_ready
        state["actor_request_cooldowns"][self._actor_key(requester)] = (
            now + PERSONAL_REQUEST_COOLDOWN_TICKS
        )

    def _rows_between(self, first: int, second: int) -> tuple[dict[str, Any], ...]:
        rows = []
        pair = {int(first), int(second)}
        for row in social_request_state(self.sim)["requests"].values():
            if not isinstance(row, dict):
                continue
            actors = {_int(row.get("requester_eid"), 0), _int(row.get("recipient_eid"), 0)}
            if actors == pair:
                rows.append(row)
        rows.sort(key=lambda item: (_int(item.get("created_tick"), 0), _request_id_number(item.get("id"))))
        return tuple(rows)

    def _active_row_between(self, first: int, second: int) -> dict[str, Any] | None:
        active = REQUEST_STATUSES.difference(TERMINAL_REQUEST_STATUSES)
        candidates = [
            row for row in self._rows_between(first, second)
            if _token(row.get("status")) in active
        ]
        return candidates[-1] if candidates else None

    def _is_player(self, actor_eid: int) -> bool:
        return self.sim.ecs.get(PlayerControlled).get(int(actor_eid)) is not None

    def _actors_adjacent(self, first: int, second: int) -> bool:
        positions = self.sim.ecs.get(Position)
        first_pos = positions.get(int(first))
        second_pos = positions.get(int(second))
        return bool(
            first_pos is not None
            and second_pos is not None
            and int(first_pos.z) == int(second_pos.z)
            and abs(int(first_pos.x) - int(second_pos.x))
            + abs(int(first_pos.y) - int(second_pos.y)) <= 1
        )

    def _relationship_ready(self, context: Mapping[str, Any] | None) -> bool:
        context = context if isinstance(context, Mapping) else {}
        if bool(context.get("guarded")) or bool(context.get("door_answering")):
            return False
        pressure = _token(context.get("pressure_tier")) or "low"
        if pressure == "high":
            return False
        bond = context.get("bond") if isinstance(context.get("bond"), Mapping) else {}
        bond_kind = _token(bond.get("kind"))
        relationship_band = _token(context.get("dialogue_relationship_band"))
        if bond_kind in {"friend", "family", "partner"} or relationship_band in {
            "friend",
            "family",
            "partner",
        }:
            return True
        return bool(context.get("met_directly")) and _int(
            context.get("opened_count"), 0
        ) >= PERSONAL_FAVOR_MIN_MEETINGS

    def _active_between(self, first: int, second: int) -> bool:
        return self._active_row_between(first, second) is not None

    def _bond(self, actor: int, other: int) -> dict[str, Any]:
        social = self.sim.ecs.get(NPCSocial).get(actor)
        bond = (getattr(social, "bonds", {}) or {}).get(other) if social is not None else None
        return bond if isinstance(bond, dict) else {}

    def _item_favor_profile(self, kind: str) -> Mapping[str, Any] | None:
        profile = ITEM_FAVOR_PROFILES.get(_token(kind))
        return profile if isinstance(profile, Mapping) else None

    def _is_item_favor(self, kind: str) -> bool:
        return _token(kind) in ITEM_FAVOR_KINDS

    def _item_favor_terms(self, kind: str, *, delay_ticks: int = 4) -> dict[str, Any]:
        profile = self._item_favor_profile(kind)
        if profile is None:
            return {"delay_ticks": max(0, int(delay_ticks))}
        item_ids = tuple(str(item_id).strip() for item_id in profile.get("item_ids", ()) if str(item_id).strip())
        return {
            "item_id": item_ids[0] if item_ids else "",
            "acceptable_item_ids": item_ids,
            "quantity": 1,
            "delay_ticks": max(0, int(delay_ticks)),
        }

    def _request_item_ids(self, kind: str, terms: Mapping[str, Any] | None = None) -> tuple[str, ...]:
        profile = self._item_favor_profile(kind)
        profile_ids = tuple(
            str(item_id).strip()
            for item_id in (profile or {}).get("item_ids", ())
            if str(item_id).strip()
        )
        terms = terms if isinstance(terms, Mapping) else {}
        stored_ids = tuple(
            str(item_id).strip()
            for item_id in tuple(terms.get("acceptable_item_ids", ()) or ())
            if str(item_id).strip()
        )
        item_id = str(terms.get("item_id", "") or "").strip()
        allowed = stored_ids or profile_ids or ((item_id,) if item_id else ())
        if item_id and item_id in allowed:
            return (item_id,) + tuple(candidate for candidate in allowed if candidate != item_id)
        return tuple(dict.fromkeys(allowed))

    def _available_request_item(
        self,
        actor: int,
        kind: str,
        terms: Mapping[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        inventory = self.sim.ecs.get(Inventory).get(actor)
        if inventory is None:
            return None
        request_terms = terms if isinstance(terms, Mapping) else {}
        allowed_item_ids = self._request_item_ids(kind, request_terms)
        instance_id = str(request_terms.get("item_instance_id", "") or "").strip()
        if instance_id:
            row = inventory.find(instance_id=instance_id)
            if (
                isinstance(row, dict)
                and str(row.get("item_id", "") or "").strip() in allowed_item_ids
                and _int(row.get("quantity"), 0) > 0
            ):
                return copy.deepcopy(row)
        for item_id in allowed_item_ids:
            row = inventory.find(item_id=item_id)
            if isinstance(row, dict) and _int(row.get("quantity"), 0) > 0:
                return copy.deepcopy(row)
        return None

    def player_item_favor_for_entry(
        self,
        player_eid: int,
        npc_eid: int,
        entry: Mapping[str, Any] | None,
    ) -> dict[str, Any] | None:
        """Describe an active promise this physical item can fulfill."""

        row = self._active_row_between(player_eid, npc_eid)
        if not isinstance(row, dict):
            return None
        if _token(row.get("status")) not in {"accepted", "in_progress"}:
            return None
        if _int(row.get("recipient_eid"), 0) != int(player_eid):
            return None
        if _int(row.get("requester_eid"), 0) != int(npc_eid):
            return None
        kind = _token(row.get("kind"))
        item_id = str((entry or {}).get("item_id", "") or "").strip()
        if not self._is_item_favor(kind) or item_id not in self._request_item_ids(kind, row.get("terms")):
            return None
        profile = self._item_favor_profile(kind)
        return {
            "request_id": str(row.get("id", "") or ""),
            "request_kind": kind,
            "player_line": str(
                (profile or {}).get("fulfill_line", "I brought what you asked for.")
                or "I brought what you asked for."
            ),
        }

    def fulfill_player_item_favor_from_exchange(
        self,
        player_eid: int,
        npc_eid: int,
        request_id: str,
        *,
        item_id: str,
        received_instance_id: str = "",
    ) -> bool:
        """Resolve a promise after the shared exchange seam moved the item."""

        row = social_request_state(self.sim)["requests"].get(str(request_id or "").strip())
        if not isinstance(row, dict):
            return False
        if _token(row.get("status")) not in {"accepted", "in_progress"}:
            return False
        if _int(row.get("recipient_eid"), 0) != int(player_eid):
            return False
        if _int(row.get("requester_eid"), 0) != int(npc_eid):
            return False
        kind = _token(row.get("kind"))
        item_id = str(item_id or "").strip()
        if not self._is_item_favor(kind) or item_id not in self._request_item_ids(kind, row.get("terms")):
            return False
        if not self._actors_adjacent(player_eid, npc_eid):
            return False
        row.setdefault("terms", {})["item_id"] = item_id
        row.setdefault("terms", {})["received_item_instance_id"] = str(received_instance_id or "").strip()
        resolve_social_request(
            self.sim,
            row["id"],
            fulfilled=True,
            reason="performed_through_item_exchange",
        )
        return True

    def _request_need_level(self, actor: int, kind: str) -> float:
        profile = self._item_favor_profile(kind)
        if profile is None:
            return 100.0
        need_attr = str(profile.get("need_attr", "") or "").strip()
        if need_attr == "health":
            vitality = self.sim.ecs.get(Vitality).get(actor)
            if vitality is None:
                return 100.0
            maximum = max(1.0, _float(getattr(vitality, "max_hp", 1.0), 1.0))
            return max(0.0, min(100.0, (_float(getattr(vitality, "hp", maximum), maximum) / maximum) * 100.0))
        needs = self.sim.ecs.get(NPCNeeds).get(actor)
        return max(0.0, min(100.0, _float(getattr(needs, need_attr, 100.0), 100.0)))

    def _item_favor_candidates(self, requester: int) -> list[tuple[float, str, dict[str, Any], str]]:
        candidates = []
        for kind, profile in ITEM_FAVOR_PROFILES.items():
            threshold = _float(profile.get("threshold"), 0.0)
            level = self._request_need_level(requester, kind)
            if level >= threshold:
                continue
            score = _float(profile.get("base_score"), 0.6) + max(0.0, (threshold - level) / 100.0)
            candidates.append((
                score,
                kind,
                self._item_favor_terms(kind),
                str(profile.get("cue", "") or "").strip(),
            ))
        return candidates

    def _request_reason(self, kind: str) -> str:
        profile = self._item_favor_profile(kind)
        return str((profile or {}).get("reason", "wants_company") or "wants_company")

    def _request_urgency(self, kind: str) -> float:
        profile = self._item_favor_profile(kind)
        return _float((profile or {}).get("urgency", 0.58), 0.58)

    def _request_deadline_ticks(self, kind: str) -> int:
        profile = self._item_favor_profile(kind)
        return max(1, _int((profile or {}).get("deadline_ticks", 140), 140))

    def _candidate_kind(self, requester: int, recipient: int, relation: str) -> tuple[str, dict[str, Any]] | None:
        bond = self._bond(requester, recipient)
        closeness = _float(bond.get("closeness"), 0.0)
        trust = _float(bond.get("trust"), 0.0)
        relation_key = _token(relation)
        item_candidates = self._item_favor_candidates(requester)
        if item_candidates and trust >= 0.28:
            _score, kind, terms, _cue = max(item_candidates, key=lambda item: item[0])
            return kind, terms
        needs = self.sim.ecs.get(NPCNeeds).get(requester)
        if needs is None:
            return None
        if (
            _float(getattr(needs, "social", 100.0), 100.0) < 54.0
            and (relation_key in {"family", "partner", "friend"} or closeness >= 0.42)
        ):
            return "check_in_later", {"delay_ticks": 16}
        return None

    def _response(self, requester: int, recipient: int, kind: str, *, forced: str | None = None) -> str:
        if self._is_item_favor(kind) and self._available_request_item(recipient, kind) is None:
            return "refused"
        forced_key = _token(forced)
        if forced_key in {"accepted", "refused"}:
            return forced_key
        traits = self.sim.ecs.get(NPCTraits).get(recipient) or NPCTraits()
        bond = self._bond(recipient, requester)
        reverse = self._bond(requester, recipient)
        graph_edge = social_edge(self.sim, recipient, requester) or {}
        history = graph_edge.get("dimensions") if isinstance(graph_edge.get("dimensions"), dict) else {}
        score = (
            _float(getattr(traits, "empathy", 0.5), 0.5) * 0.25
            + _float(getattr(traits, "loyalty", 0.5), 0.5) * 0.20
            + _float(getattr(traits, "discipline", 0.5), 0.5) * 0.13
            + _float(bond.get("trust"), 0.2) * 0.16
            + _float(bond.get("closeness"), 0.2) * 0.12
            + _float(reverse.get("closeness"), 0.2) * 0.08
            + _float(history.get("trust"), 0.0) * 0.12
            + _float(history.get("obligation"), 0.0) * 0.10
            - _float(history.get("resentment"), 0.0) * 0.18
        )
        roll = random.Random(
            f"{getattr(self.sim, 'seed', 0)}:social-request-answer:{requester}:{recipient}:{getattr(self.sim, 'tick', 0)}:{kind}"
        ).random()
        return "accepted" if score >= 0.42 + (roll * 0.20) else "refused"

    def _request_lines(self, kind: str, response: str, response_reason: str) -> tuple[str, str, str, str]:
        profile = self._item_favor_profile(kind)
        if profile is not None:
            request_line = str(profile.get("request_line", "") or "")
            summary = str(profile.get("summary", "") or "")
            detail = str(profile.get("detail", "") or "")
        else:
            request_line = "Could you come find me again later? I don't want to sit with this alone."
            summary = "someone asking for a later check-in"
            detail = "a personal promise to return and check on someone later"
        if response == "accepted":
            response_line = "I will. Give me a little while."
        elif str(response_reason or "").startswith("lacks_"):
            response_line = "I don't have any to spare."
        else:
            response_line = "I can't promise that today."
        return request_line, response_line, summary, detail

    def propose_at_contact(
        self,
        requester_eid: int,
        recipient_eid: int,
        *,
        kind: str,
        terms: Mapping[str, Any] | None = None,
        force_response: str | None = None,
    ) -> dict[str, Any]:
        requester = _actor(requester_eid)
        recipient = _actor(recipient_eid)
        kind_key = _token(kind)
        now = _int(getattr(self.sim, "tick", 0), 0)
        request_terms = copy.deepcopy(dict(terms or {}))
        if self._is_item_favor(kind_key):
            defaults = self._item_favor_terms(kind_key)
            defaults.update(request_terms)
            request_terms = defaults
        # A caller may already know a candidate instance, but it belongs to the
        # recipient's answer rather than the requester's proposal.
        request_terms.pop("item_instance_id", None)
        delay = max(0, _int(request_terms.get("delay_ticks"), 0))
        urgency = self._request_urgency(kind_key)
        reason = self._request_reason(kind_key)
        row = create_social_request(
            self.sim,
            requester_eid=requester,
            recipient_eid=recipient,
            beneficiary_eid=requester,
            kind=kind_key,
            reason=reason,
            terms=request_terms,
            urgency=urgency,
            due_tick=now + delay,
            deadline_tick=now + self._request_deadline_ticks(kind_key),
        )
        response = self._response(requester, recipient, kind_key, forced=force_response)
        response_reason = "willing" if response == "accepted" else "cannot_commit"
        if self._is_item_favor(kind_key):
            supplied_item = self._available_request_item(recipient, kind_key, request_terms)
            if response == "accepted" and supplied_item is not None:
                selected_instance = str(supplied_item.get("instance_id", ""))
                live_row = social_request_state(self.sim)["requests"].get(row["id"])
                if isinstance(live_row, dict):
                    live_row.setdefault("terms", {})["item_instance_id"] = selected_instance
                    live_row.setdefault("terms", {})["item_id"] = str(supplied_item.get("item_id", "") or "")
            elif response == "refused" and supplied_item is None:
                response_reason = f"lacks_{self._request_reason(kind_key)}"
        answered = respond_to_social_request(
            self.sim,
            row["id"],
            actor_eid=recipient,
            outcome=response,
            reason=response_reason,
        )
        self._mark_request_cooldowns(requester, recipient)
        request_line, response_line, summary, detail = self._request_lines(kind_key, response, response_reason)
        return {
            "topic": "social_request",
            "quote": request_line,
            "response_quote": response_line,
            "summary": summary,
            "detail": detail,
            "channel": "social",
            "priority": "normal" if response == "accepted" else "low",
            "source_domain": "social_request",
            "request_id": answered["id"],
            "request_kind": kind_key,
            "request_status": response,
            "level_local": True,
            "audible_radius": 8,
        }

    def _request_prompt(self, kind: str) -> str:
        profile = self._item_favor_profile(kind)
        if profile is not None:
            return str(profile.get("request_line", "") or "")
        return "Could you come find me again later? I don't want to sit with this alone."

    def _request_reason_line(self, row: Mapping[str, Any]) -> str:
        profile = self._item_favor_profile(_token(row.get("kind")))
        if profile is not None:
            return str(profile.get("reason_line", "") or "")
        return "I've been alone too long today. I don't want to keep carrying it by myself."

    def _record_dialogue_occurrence(
        self,
        row: dict[str, Any],
        kind: str,
        *,
        actor_eid: int,
        **payload: Any,
    ) -> dict[str, Any]:
        source_ids = tuple(row.get("occurrence_ids", ()) or ())
        occurrence = record_occurrence(
            self.sim,
            kind,
            actor_eids=(
                _int(row.get("requester_eid"), 0),
                _int(row.get("recipient_eid"), 0),
                _int(row.get("beneficiary_eid"), 0),
            ),
            proposition_ids=tuple(row.get("proposition_ids", ()) or ()),
            referent_ids=tuple(row.get("referent_ids", ()) or ()),
            source_occurrence_ids=(source_ids[-1],) if source_ids else (),
            payload={
                "request_id": row.get("id"),
                "request_kind": row.get("kind"),
                "speaking_actor_eid": int(actor_eid),
                **copy.deepcopy(payload),
            },
            flags=("spoken", "in_person", "actor_routed"),
            dedupe_key=(
                f"social-request:{row.get('id')}:{_token(kind)}:"
                f"{len(tuple(row.get('occurrence_ids', ()) or ())) + 1}"
            ),
        )
        _append_occurrence(row, occurrence["id"])
        row["last_changed_tick"] = _int(getattr(self.sim, "tick", 0), 0)
        advance_social_thread(
            self.sim,
            row["thread_id"],
            occurrence_id=occurrence["id"],
        )
        return occurrence

    def _player_offer_candidate(
        self,
        npc_eid: int,
        player_eid: int,
        context: Mapping[str, Any] | None,
    ) -> dict[str, Any] | None:
        npc = _actor(npc_eid)
        player = _actor(player_eid)
        if not self._relationship_ready(context):
            return None
        if self._active_between(npc, player) or not self._request_cooldown_ready(npc, player):
            return None
        candidates = self._item_favor_candidates(npc)
        if not candidates:
            return None
        score, kind, terms, cue = max(candidates, key=lambda item: item[0])
        return {
            "kind": kind,
            "terms": copy.deepcopy(terms),
            "cue": cue,
            "prompt": self._request_prompt(kind),
            "score": min(0.92, score),
        }

    def player_offer_candidate(
        self,
        npc_eid: int,
        player_eid: int,
        context: Mapping[str, Any] | None,
    ) -> dict[str, Any] | None:
        candidate = self._player_offer_candidate(npc_eid, player_eid, context)
        return copy.deepcopy(candidate) if isinstance(candidate, dict) else None

    def begin_player_offer(
        self,
        npc_eid: int,
        player_eid: int,
        *,
        kind: str,
        terms: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        npc = _actor(npc_eid)
        player = _actor(player_eid)
        kind_key = _token(kind)
        now = _int(getattr(self.sim, "tick", 0), 0)
        request_terms = copy.deepcopy(dict(terms or {}))
        delay = max(0, _int(request_terms.get("delay_ticks"), 0))
        row = create_social_request(
            self.sim,
            requester_eid=npc,
            recipient_eid=player,
            beneficiary_eid=npc,
            kind=kind_key,
            reason=self._request_reason(kind_key),
            terms=request_terms,
            urgency=self._request_urgency(kind_key),
            due_tick=now + delay,
            deadline_tick=now + self._request_deadline_ticks(kind_key),
        )
        self._mark_request_cooldowns(npc, player)
        return {
            "request_id": row["id"],
            "request_kind": kind_key,
            "prompt": self._request_prompt(kind_key),
        }

    def _player_request_rows(self, player_eid: int, npc_eid: int) -> list[dict[str, Any]]:
        rows = []
        for topic_id, kind in PLAYER_ITEM_REQUEST_TOPICS.items():
            profile = self._item_favor_profile(kind)
            if profile is None:
                continue
            if self._request_need_level(player_eid, kind) >= _float(profile.get("request_threshold"), 100.0):
                continue
            if self._available_request_item(player_eid, kind) is not None:
                continue
            rows.append({
                "id": topic_id,
                "label": str(profile.get("ask_label", "Ask them for help") or "Ask them for help"),
                "prompt_text": str(profile.get("ask_label", "Ask them for help") or "Ask them for help"),
                "player_line": str(profile.get("ask_line", "Could you spare something?") or "Could you spare something?"),
                "favor_kind": kind,
            })
        return rows

    def player_dialogue_rows(
        self,
        player_eid: int,
        npc_eid: int,
        context: Mapping[str, Any] | None,
    ) -> list[dict[str, Any]]:
        player = _actor(player_eid)
        npc = _actor(npc_eid)
        now = _int(getattr(self.sim, "tick", 0), 0)
        active = self._active_row_between(player, npc)
        if isinstance(active, dict):
            request_id = str(active.get("id", ""))
            kind = _token(active.get("kind"))
            status = _token(active.get("status"))
            requester = _int(active.get("requester_eid"), 0)
            recipient = _int(active.get("recipient_eid"), 0)
            awaiting = _int(active.get("awaiting_actor_eid"), 0)
            rows = []
            response_ready = status != "deferred" or now >= _int(active.get("response_after_tick"), now + 1)
            if status in {"proposed", "countered", "deferred"} and awaiting == player and response_ready:
                if active.get("reason_explained_tick") is None:
                    rows.append({
                        "id": "favor_why",
                        "label": "Ask why they need this",
                        "player_line": "Why do you need me to do this?",
                        "request_id": request_id,
                    })
                rows.append({
                    "id": "favor_accept",
                    "label": "Promise to help",
                    "player_line": "All right. I'll do it.",
                    "request_id": request_id,
                })
                if _int(active.get("counter_count"), 0) < 1:
                    rows.append({
                        "id": "favor_counter_later",
                        "label": "Agree, but ask for more time",
                        "player_line": "I can do it, but I need more time.",
                        "request_id": request_id,
                    })
                if _int(active.get("defer_count"), 0) < 1:
                    rows.append({
                        "id": "favor_defer",
                        "label": "Ask for time to think",
                        "player_line": "Let me think about it before I promise.",
                        "request_id": request_id,
                    })
                rows.append({
                    "id": "favor_decline",
                    "label": "Say you can't promise that",
                    "player_line": "I can't promise that.",
                    "request_id": request_id,
                })
                return rows
            if status in {"accepted", "in_progress"} and recipient == player:
                if self._actors_adjacent(player, npc):
                    if kind == "check_in_later":
                        rows.append({
                            "id": "favor_fulfill",
                            "label": "Keep your promise now",
                            "player_line": "I said I'd come back. How are you holding up?",
                            "request_id": request_id,
                        })
                    elif _int(active.get("renegotiation_count"), 0) < 1:
                        rows.append({
                            "id": "favor_renegotiate",
                            "label": "Admit you need more time",
                            "player_line": "I haven't found what you need yet. Can you give me more time?",
                            "request_id": request_id,
                        })
                rows.append({
                    "id": "favor_admit_failure",
                    "label": "Admit you can't keep the promise",
                    "player_line": "I need to be honest. I can't do what I promised.",
                    "request_id": request_id,
                })
                return rows
            if status in {"accepted", "in_progress"} and requester == player:
                return [{
                    "id": "favor_check_status",
                    "label": "Ask about the favor you requested",
                    "player_line": "Are you still able to do what you promised?",
                    "request_id": request_id,
                }]
            return rows

        terminal_rows = list(reversed(self._rows_between(player, npc)))
        for row in terminal_rows:
            if bool(row.get("player_ack_pending")) and _int(row.get("requester_eid"), 0) == player:
                request_id = str(row.get("id", ""))
                if _token(row.get("status")) != "fulfilled":
                    return [
                        {"id": "favor_ack_warm", "label": "Accept the explanation", "player_line": "Thank you for telling me. I understand.", "request_id": request_id},
                        {"id": "favor_ack_simple", "label": "Acknowledge what happened", "player_line": "All right. I heard you.", "request_id": request_id},
                        {"id": "favor_ack_reserved", "label": "Hold them to the broken promise", "player_line": "You said you would come through.", "request_id": request_id},
                    ]
                if _token(row.get("kind")) == "check_in_later":
                    return [
                        {"id": "favor_ack_warm", "label": "Tell them it helped", "player_line": "Better. Thank you for coming back.", "request_id": request_id},
                        {"id": "favor_ack_simple", "label": "Thank them", "player_line": "Thanks for coming.", "request_id": request_id},
                        {"id": "favor_ack_reserved", "label": "Say you're all right", "player_line": "I'm all right. But I noticed you came.", "request_id": request_id},
                    ]
                return [
                    {"id": "favor_ack_warm", "label": "Thank them warmly", "player_line": "Thank you. I really needed that.", "request_id": request_id},
                    {"id": "favor_ack_simple", "label": "Thank them", "player_line": "Thank you for bringing it.", "request_id": request_id},
                    {"id": "favor_ack_reserved", "label": "Acknowledge the delivery", "player_line": "You came through.", "request_id": request_id},
                ]
            if (
                _token(row.get("status")) == "refused"
                and _int(row.get("requester_eid"), 0) == player
                and row.get("reason_explained_tick") is None
                and now - _int(row.get("completed_tick"), row.get("response_tick", now)) <= 180
            ):
                return [{
                    "id": "favor_refusal_why",
                    "label": "Ask why they refused",
                    "player_line": "Can I ask why not?",
                    "request_id": str(row.get("id", "")),
                }]

        if not self._relationship_ready(context):
            return []
        rows = []
        candidate = self._player_offer_candidate(npc, player, context)
        if candidate:
            profile = self._item_favor_profile(candidate["kind"])
            rows.append({
                "id": "favor_invite",
                "label": (
                    str(profile.get("offer_label", "Ask if they need help") or "Ask if they need help")
                    if profile is not None
                    else "Ask if they want you to check in later"
                ),
                "player_line": (
                    str(profile.get("offer_line", "Do you need help?") or "Do you need help?")
                    if profile is not None
                    else "You seem like you don't want to be alone. Should I come find you later?"
                ),
                "favor_kind": candidate["kind"],
                "favor_terms": copy.deepcopy(candidate["terms"]),
                "visible_cue": candidate["cue"],
            })
        if self._request_cooldown_ready(player, npc):
            rows.extend(self._player_request_rows(player, npc))
        return rows

    def _bind_available_item(self, row: dict[str, Any], actor_eid: int) -> None:
        supplied_item = self._available_request_item(
            actor_eid,
            _token(row.get("kind")),
            row.get("terms"),
        )
        if not isinstance(supplied_item, dict):
            return
        row.setdefault("terms", {})["item_instance_id"] = str(supplied_item.get("instance_id", ""))
        row.setdefault("terms", {})["item_id"] = str(supplied_item.get("item_id", "") or "")

    def _perform_player_favor(self, row: dict[str, Any], player_eid: int) -> tuple[bool, str]:
        if _int(row.get("recipient_eid"), 0) != int(player_eid):
            return False, "not_your_promise"
        if _token(row.get("status")) not in {"accepted", "in_progress"}:
            return False, "promise_not_active"
        requester = _int(row.get("requester_eid"), 0)
        if not self._actors_adjacent(player_eid, requester):
            return False, "requester_not_here"
        performed, reason = self._perform_request(row)
        if not performed:
            return False, reason
        resolve_social_request(self.sim, row["id"], fulfilled=True, reason=reason)
        return True, reason

    def _renegotiate_player_favor(self, row: dict[str, Any], player_eid: int) -> tuple[bool, str]:
        if _int(row.get("recipient_eid"), 0) != int(player_eid):
            return False, "not_your_promise"
        if _token(row.get("status")) not in {"accepted", "in_progress"}:
            return False, "promise_not_active"
        if _int(row.get("renegotiation_count"), 0) >= 1:
            return False, "already_renegotiated"
        requester = _int(row.get("requester_eid"), 0)
        if self._is_item_favor(_token(row.get("kind"))) and self._request_need_level(
            requester,
            _token(row.get("kind")),
        ) < 20.0:
            self._record_dialogue_occurrence(
                row,
                "social_request_renegotiation_refused",
                actor_eid=requester,
                reason="need_is_immediate",
            )
            row["renegotiation_count"] = 1
            return False, "need_is_immediate"
        now = _int(getattr(self.sim, "tick", 0), 0)
        row["renegotiation_count"] = 1
        row["deadline_tick"] = max(_int(row.get("deadline_tick"), now + 1), now) + PERSONAL_FAVOR_RENEGOTIATION_TICKS
        row["last_changed_tick"] = now
        self._record_dialogue_occurrence(
            row,
            "social_request_renegotiated",
            actor_eid=requester,
            extension_ticks=PERSONAL_FAVOR_RENEGOTIATION_TICKS,
        )
        return True, "extension_granted"

    def resolve_player_dialogue_choice(
        self,
        player_eid: int,
        npc_eid: int,
        topic_id: str,
        topic_row: Mapping[str, Any] | None,
        context: Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        player = _actor(player_eid)
        npc = _actor(npc_eid)
        topic = _token(topic_id)
        choice = dict(topic_row or {})
        request_id = str(choice.get("request_id", "") or "").strip()
        row = social_request_state(self.sim)["requests"].get(request_id) if request_id else None

        if topic == "favor_invite":
            candidate = self._player_offer_candidate(npc, player, context)
            if not candidate or _token(choice.get("favor_kind")) != candidate["kind"]:
                return {"npc_lines": ["Not right now. I lost the nerve to ask."]}
            opened = self.begin_player_offer(
                npc,
                player,
                kind=candidate["kind"],
                terms=candidate["terms"],
            )
            return {"npc_lines": [opened["prompt"]], "favor_request_id": opened["request_id"]}

        if topic in set(PLAYER_ITEM_REQUEST_TOPICS) | {"favor_request_check_in"}:
            kind = PLAYER_ITEM_REQUEST_TOPICS.get(topic, "check_in_later")
            if not self._relationship_ready(context) or not self._request_cooldown_ready(player, npc):
                return {"npc_lines": ["Not today. This isn't the moment for that."]}
            terms = (
                self._item_favor_terms(kind)
                if self._is_item_favor(kind)
                else {"delay_ticks": 16}
            )
            payload = self.propose_at_contact(player, npc, kind=kind, terms=terms)
            return {"npc_lines": [payload["response_quote"]], "favor_request_id": payload["request_id"]}

        if not isinstance(row, dict) or {
            _int(row.get("requester_eid"), 0),
            _int(row.get("recipient_eid"), 0),
        } != {player, npc}:
            return {"npc_lines": ["That isn't between us anymore."]}

        if topic == "favor_why":
            self._record_dialogue_occurrence(row, "social_request_reason_asked", actor_eid=player)
            row["reason_explained_tick"] = _int(getattr(self.sim, "tick", 0), 0)
            return {"npc_lines": [self._request_reason_line(row)]}
        if topic == "favor_accept":
            if self._is_item_favor(_token(row.get("kind"))):
                self._bind_available_item(row, player)
            respond_to_social_request(self.sim, row["id"], actor_eid=player, outcome="accepted", reason="player_promised")
            return {"npc_lines": ["Thank you. I won't pretend that means nothing to me."]}
        if topic == "favor_counter_later":
            row["counter_count"] = _int(row.get("counter_count"), 0) + 1
            current_delay = max(0, _int((row.get("terms") or {}).get("delay_ticks"), 0))
            respond_to_social_request(
                self.sim,
                row["id"],
                actor_eid=player,
                outcome="countered",
                counter_terms={"delay_ticks": current_delay + 12},
                reason="player_needs_more_time",
            )
            kind = _token(row.get("kind"))
            too_urgent = self._is_item_favor(kind) and self._request_need_level(npc, kind) < 20.0
            respond_to_social_request(
                self.sim,
                row["id"],
                actor_eid=npc,
                outcome="refused" if too_urgent else "accepted",
                reason="counter_too_slow" if too_urgent else "counter_accepted",
            )
            return {"npc_lines": [
                "I need it sooner than that. Forget it." if too_urgent else "All right. Just don't forget."
            ]}
        if topic == "favor_defer":
            row["defer_count"] = _int(row.get("defer_count"), 0) + 1
            respond_to_social_request(
                self.sim,
                row["id"],
                actor_eid=player,
                outcome="deferred",
                defer_until_tick=_int(getattr(self.sim, "tick", 0), 0) + 12,
                reason="player_is_thinking",
            )
            return {"npc_lines": ["All right. Think about it, but I can't wait forever."]}
        if topic == "favor_decline":
            respond_to_social_request(self.sim, row["id"], actor_eid=player, outcome="refused", reason="player_declined")
            return {"npc_lines": ["All right. I needed an honest answer more than a false promise."]}
        if topic == "favor_fulfill":
            kept, reason = self._perform_player_favor(row, player)
            if not kept:
                profile = self._item_favor_profile(_token(row.get("kind")))
                if reason.startswith("promised_") and profile is not None:
                    return {"npc_lines": [str(profile.get("missing_line", "You don't have what they asked for yet.") or "You don't have what they asked for yet.")]}
                return {"npc_lines": ["We can't settle that promise here and now."]}
            return {"npc_lines": [
                "Thank you. I needed that."
                if self._is_item_favor(_token(row.get("kind")))
                else "Better now that you're here."
            ]}
        if topic == "favor_renegotiate":
            extended, reason = self._renegotiate_player_favor(row, player)
            return {"npc_lines": [
                "All right. But don't leave it too long."
                if extended
                else "No. I need it now, not after another promise."
            ], "favor_renegotiation": reason}
        if topic == "favor_admit_failure":
            resolve_social_request(self.sim, row["id"], fulfilled=False, reason="admitted_failure")
            return {"npc_lines": ["I'm glad you told me. I'm still disappointed."]}
        if topic == "favor_check_status":
            self._record_dialogue_occurrence(row, "social_request_status_asked", actor_eid=player)
            kind = _token(row.get("kind"))
            if self._is_item_favor(kind) and self._available_request_item(npc, kind, row.get("terms")) is None:
                return {"npc_lines": ["I haven't found something I can spare yet, but I haven't forgotten."]}
            return {"npc_lines": ["I said I would. I'm still working on it."]}
        if topic == "favor_refusal_why":
            self._record_dialogue_occurrence(row, "social_request_refusal_explained", actor_eid=npc)
            row["reason_explained_tick"] = _int(getattr(self.sim, "tick", 0), 0)
            reason = _token(row.get("response_reason"))
            if reason.startswith("lacks_"):
                profile = self._item_favor_profile(_token(row.get("kind")))
                item_word = "that" if profile is None else str(profile.get("item_word", "that") or "that")
                line = f"I don't have any {item_word} to spare. Saying yes wouldn't change that."
            elif reason == "counter_too_slow":
                line = "I needed help sooner than that. Waiting would not have helped me."
            else:
                line = "I have too much else to keep straight today. I didn't want to promise and fail you."
            return {"npc_lines": [line]}
        if topic in {"favor_ack_warm", "favor_ack_simple", "favor_ack_reserved"}:
            self._record_dialogue_occurrence(
                row,
                "social_request_player_acknowledged",
                actor_eid=player,
                acknowledgement=topic.removeprefix("favor_ack_"),
            )
            row["player_ack_pending"] = False
            row["followup_surfaced_tick"] = _int(getattr(self.sim, "tick", 0), 0)
            if _token(row.get("status")) == "fulfilled":
                replies = {
                    "favor_ack_warm": "Of course. I'm glad I came through.",
                    "favor_ack_simple": "You're welcome.",
                    "favor_ack_reserved": "All right. I just wanted you to know I meant it.",
                }
            else:
                replies = {
                    "favor_ack_warm": "I appreciate that. I still know I let you down.",
                    "favor_ack_simple": "I won't dress it up. I failed you.",
                    "favor_ack_reserved": "I know. You have every right to remember that.",
                }
            return {"npc_lines": [replies[topic]]}
        return {"npc_lines": ["Let's leave that there."]}

    def _followup_payload(self, first: int, second: int) -> dict[str, Any] | None:
        now = _int(getattr(self.sim, "tick", 0), 0)
        candidates = []
        for row in social_request_state(self.sim)["requests"].values():
            if not isinstance(row, dict) or _token(row.get("status")) not in {"fulfilled", "failed", "expired"}:
                continue
            if _token(row.get("status")) == "expired" and _token(row.get("response")) != "accepted":
                continue
            if row.get("followup_surfaced_tick") is not None:
                continue
            if now - _int(row.get("completed_tick"), now) < FOLLOWUP_MIN_AGE_TICKS:
                continue
            if {_int(row.get("requester_eid"), 0), _int(row.get("recipient_eid"), 0)} != {int(first), int(second)}:
                continue
            candidates.append(row)
        if not candidates:
            return None
        row = max(candidates, key=lambda item: _int(item.get("completed_tick"), 0))
        row["followup_surfaced_tick"] = now
        fulfilled = _token(row.get("status")) == "fulfilled"
        requester = _int(row.get("requester_eid"), 0)
        speaker_is_requester = int(first) == requester
        if fulfilled:
            first_line = "You actually came through for me." if speaker_is_requester else "I said I'd come through."
            second_line = "I said I'd come through." if speaker_is_requester else "You actually came through for me."
            summary = "someone acknowledging a favor that was actually kept"
        else:
            first_line = "You said you would come." if speaker_is_requester else "I know. I let you down."
            second_line = "I know. I let you down." if speaker_is_requester else "You said you would come."
            summary = "someone confronting a companion about a broken promise"
        source_ids = tuple(row.get("occurrence_ids", ()) or ())
        followup_occurrence = record_occurrence(
            self.sim,
            "social_request_followup_discussed",
            actor_eids=(first, second),
            proposition_ids=tuple(row.get("proposition_ids", ()) or ()),
            referent_ids=tuple(row.get("referent_ids", ()) or ()),
            source_occurrence_ids=(source_ids[-1],) if source_ids else (),
            payload={
                "request_id": row.get("id"),
                "request_kind": row.get("kind"),
                "request_status": row.get("status"),
            },
            flags=("spoken", "in_person"),
            dedupe_key=f"social-request:{row.get('id')}:followup",
        )
        _append_occurrence(row, followup_occurrence["id"])
        advance_social_thread(
            self.sim,
            row["thread_id"],
            occurrence_id=followup_occurrence["id"],
            status="closed",
            awaiting_actor_eid=None,
        )
        return {
            "topic": "social_request_followup",
            "quote": first_line,
            "response_quote": second_line,
            "summary": summary,
            "detail": str(row.get("outcome_reason", "") or "").replace("_", " "),
            "channel": "social",
            "priority": "normal",
            "source_domain": "social_request",
            "request_id": row.get("id"),
            "request_kind": row.get("kind"),
            "request_status": row.get("status"),
            "level_local": True,
            "audible_radius": 8,
        }

    def social_contact_payload(self, speaker_eid: int, partner_eid: int, relation: str, tone: str) -> dict[str, Any] | None:
        """Return request speech only when these two actors are really in contact."""

        speaker = _int(speaker_eid, 0)
        partner = _int(partner_eid, 0)
        if speaker <= 0 or partner <= 0 or speaker == partner:
            return None
        player_controlled = self.sim.ecs.get(PlayerControlled)
        if speaker in player_controlled or partner in player_controlled:
            return None
        followup = self._followup_payload(speaker, partner)
        if followup:
            return followup
        if self._active_between(speaker, partner):
            return None
        now = _int(getattr(self.sim, "tick", 0), 0)
        if not self._request_cooldown_ready(speaker, partner):
            return None
        candidate = self._candidate_kind(speaker, partner, relation)
        if candidate is None:
            return None
        kind, terms = candidate
        profile = self._item_favor_profile(kind)
        if profile is not None:
            threshold = max(1.0, _float(profile.get("threshold"), 50.0))
            urgency = max(0.0, (threshold - self._request_need_level(speaker, kind)) / threshold)
        else:
            needs = self.sim.ecs.get(NPCNeeds).get(speaker)
            urgency = max(0.0, (60.0 - _float(getattr(needs, "social", 100.0), 100.0)) / 60.0)
        chance = 0.12 + min(0.46, urgency * 0.6)
        roll = random.Random(
            f"{getattr(self.sim, 'seed', 0)}:social-request-offer:{speaker}:{partner}:{now // 6}:{kind}:{tone}"
        ).random()
        if roll > chance:
            return None
        return self.propose_at_contact(speaker, partner, kind=kind, terms=terms)

    def _clear_actor_intent(self, actor_eid: int, request_id: str) -> None:
        ai = self.sim.ecs.get(AI).get(actor_eid)
        if ai is not None and str(getattr(ai, "social_request_id", "") or "") == request_id:
            ai.state = "idle"
            ai.target = None
            ai.target_eid = None
            delattr(ai, "social_request_id")
        will = self.sim.ecs.get(NPCWill).get(actor_eid)
        if will is not None and str(getattr(will, "social_request_id", "") or "") == request_id:
            will.intent = "idle"
            will.score = 0.0
            will.target = None
            will.target_eid = None
            will.last_tick = _int(getattr(self.sim, "tick", 0), 0) - 1
            delattr(will, "social_request_id")

    def _transfer_promised_item(self, row: dict[str, Any]) -> bool:
        recipient = _int(row.get("recipient_eid"), 0)
        beneficiary = _int(row.get("beneficiary_eid"), 0)
        terms = dict(row.get("terms", {}) or {})
        kind = _token(row.get("kind"))
        item_id = str(terms.get("item_id", "") or "").strip()
        quantity = max(1, _int(terms.get("quantity"), 1))
        source = self.sim.ecs.get(Inventory).get(recipient)
        if source is None:
            return False
        source_entry = self._available_request_item(recipient, kind, terms)
        allowed_item_ids = self._request_item_ids(kind, terms)
        if (
            not isinstance(source_entry, dict)
            or str(source_entry.get("item_id", "") or "").strip() not in allowed_item_ids
            or (item_id and item_id not in allowed_item_ids)
        ):
            return False
        transferred_item_id = str(source_entry.get("item_id", "") or "").strip()
        row.setdefault("terms", {})["item_id"] = transferred_item_id
        row.setdefault("terms", {})["item_instance_id"] = str(source_entry.get("instance_id", "") or "")
        removed = source.remove_item(instance_id=source_entry.get("instance_id"), quantity=quantity)
        if not isinstance(removed, dict) or _int(removed.get("quantity"), 0) < quantity:
            return False
        inventories = self.sim.ecs.get(Inventory)
        target = inventories.get(beneficiary)
        if target is None:
            target = Inventory(capacity=10)
            self.sim.ecs.add(beneficiary, target)
        catalog = ITEM_CATALOG.get(transferred_item_id, {}) if isinstance(ITEM_CATALOG, dict) else {}
        added, _instance = target.add_item(
            transferred_item_id,
            quantity=quantity,
            stack_max=max(1, _int(catalog.get("stack_max"), 1)),
            instance_id=removed.get("instance_id"),
            owner_eid=beneficiary,
            owner_tag="gift",
            metadata=removed.get("metadata"),
        )
        if added:
            return True
        source.add_item(
            transferred_item_id,
            quantity=quantity,
            stack_max=max(1, _int(catalog.get("stack_max"), 1)),
            instance_id=removed.get("instance_id"),
            owner_eid=removed.get("owner_eid"),
            owner_tag=removed.get("owner_tag"),
            metadata=removed.get("metadata"),
        )
        return False

    def _perform_request(self, row: dict[str, Any]) -> tuple[bool, str]:
        kind = _token(row.get("kind"))
        beneficiary = _int(row.get("beneficiary_eid"), 0)
        recipient = _int(row.get("recipient_eid"), 0)
        if self._is_item_favor(kind):
            if not self._transfer_promised_item(row):
                return False, f"promised_{self._request_reason(kind)}_unavailable"
        elif kind == "check_in_later":
            needs = self.sim.ecs.get(NPCNeeds).get(beneficiary)
            if needs is not None:
                needs.social = min(100.0, _float(getattr(needs, "social", 0.0), 0.0) + 8.0)
            recipient_needs = self.sim.ecs.get(NPCNeeds).get(recipient)
            if recipient_needs is not None:
                recipient_needs.social = min(100.0, _float(getattr(recipient_needs, "social", 0.0), 0.0) + 3.0)
        else:
            return False, "unsupported_request_kind"
        return True, "performed_in_person"

    def _completion_payload(self, row: Mapping[str, Any], fulfilled: bool) -> dict[str, Any]:
        kind = _token(row.get("kind"))
        profile = self._item_favor_profile(kind)
        if fulfilled and profile is not None:
            quote = str(profile.get("completion_quote", "I brought what I promised.") or "I brought what I promised.")
            reply = "Thank you. I needed that."
            summary = str(profile.get("completion_summary", "someone delivering what they had promised to bring") or "someone delivering what they had promised to bring")
        elif fulfilled:
            quote = "I came back. How are you holding up?"
            reply = "Better now that you're here."
            summary = "someone returning for a promised check-in"
        else:
            quote = "I came, but I couldn't do what I promised."
            reply = "Then don't pretend the promise meant nothing."
            summary = "someone admitting they failed to keep a personal promise"
        return {
            "topic": "social_request_fulfilled" if fulfilled else "social_request_failed",
            "quote": quote,
            "response_quote": reply,
            "summary": summary,
            "detail": str(row.get("outcome_reason", "") or "").replace("_", " "),
            "channel": "social",
            "priority": "normal",
            "source_domain": "social_request",
            "request_id": row.get("id"),
            "request_kind": kind,
            "request_status": "fulfilled" if fulfilled else "failed",
            "level_local": True,
            "audible_radius": 8,
        }

    def on_request_arrived(self, event) -> None:
        data = dict(getattr(event, "data", {}) or {})
        request_id = str(data.get("request_id", "") or "").strip()
        state = social_request_state(self.sim)
        row = state["requests"].get(request_id)
        if not isinstance(row, dict) or _token(row.get("status")) not in {"accepted", "in_progress"}:
            return
        recipient = _int(row.get("recipient_eid"), 0)
        requester = _int(row.get("requester_eid"), 0)
        if _int(data.get("npc_eid"), -1) != recipient or _int(data.get("requester_eid"), -1) != requester:
            return
        positions = self.sim.ecs.get(Position)
        actor_pos = positions.get(recipient)
        requester_pos = positions.get(requester)
        present = (
            actor_pos is not None
            and requester_pos is not None
            and int(actor_pos.z) == int(requester_pos.z)
            and abs(int(actor_pos.x) - int(requester_pos.x)) + abs(int(actor_pos.y) - int(requester_pos.y)) <= 1
        )
        if not present:
            self._clear_actor_intent(recipient, request_id)
            resolved = resolve_social_request(self.sim, request_id, fulfilled=False, reason="requester_not_found")
            return
        performed, reason = self._perform_request(row)
        resolved = resolve_social_request(self.sim, request_id, fulfilled=performed, reason=reason)
        self._clear_actor_intent(recipient, request_id)
        payload = self._completion_payload(resolved, performed)
        player_requester = self._is_player(requester)
        if player_requester:
            live_row = social_request_state(self.sim)["requests"].get(request_id)
            if isinstance(live_row, dict):
                live_row["player_ack_pending"] = True
            # The NPC may initiate the exchange, but the event must never put
            # words in the player's mouth.  Their answer remains a real row in
            # the ordinary conversation modal.
            payload["response_quote"] = ""
        self.sim.emit(Event(
            "npc_socialized",
            npc_eid=recipient,
            partner_eid=requester,
            relation="personal_request",
            tone="check_in",
            x=int(actor_pos.x),
            y=int(actor_pos.y),
            z=int(actor_pos.z),
            **payload,
        ))
        if player_requester:
            self.sim.emit(Event(
                "npc_dialogue_request",
                eid=requester,
                npc_eid=recipient,
                prompt_lines=(payload.get("quote", ""),),
                highlight_topic_ids=("favor_ack_warm", "favor_ack_simple", "favor_ack_reserved"),
            ))

    def on_request_failed(self, event) -> None:
        data = dict(getattr(event, "data", {}) or {})
        request_id = str(data.get("request_id", "") or "").strip()
        row = social_request_state(self.sim)["requests"].get(request_id)
        if not isinstance(row, dict) or _token(row.get("status")) not in {"accepted", "in_progress"}:
            return
        recipient = _int(row.get("recipient_eid"), 0)
        if _int(data.get("npc_eid"), -1) != recipient:
            return
        self._clear_actor_intent(recipient, request_id)
        resolve_social_request(
            self.sim,
            request_id,
            fulfilled=False,
            reason=_token(data.get("reason")) or "unreachable_requester",
        )

    def _actor_can_start(self, actor_eid: int) -> bool:
        ai = self.sim.ecs.get(AI).get(actor_eid)
        if ai is None:
            return False
        vitality = self.sim.ecs.get(Vitality).get(actor_eid)
        if vitality is not None and (
            bool(getattr(vitality, "downed", False))
            or _float(getattr(vitality, "hp", 1.0), 1.0) <= 0.0
        ):
            return False
        state = _token(getattr(ai, "state", "idle")) or "idle"
        return state in _INTERRUPTIBLE_STATES or state == SOCIAL_REQUEST_INTENT

    def _start_or_preserve(self, row: dict[str, Any]) -> None:
        recipient = _int(row.get("recipient_eid"), 0)
        requester = _int(row.get("requester_eid"), 0)
        if not self._actor_can_start(recipient):
            return
        target = row.get("target_snapshot")
        if not isinstance(target, (tuple, list)) or len(target) < 3:
            return
        target_tuple = (_int(target[0]), _int(target[1]), _int(target[2]))
        ai = self.sim.ecs.get(AI).get(recipient)
        will = self.sim.ecs.get(NPCWill).get(recipient)
        if ai is None:
            return
        ai.state = SOCIAL_REQUEST_INTENT
        ai.target = target_tuple
        ai.target_eid = requester
        ai.social_request_id = row["id"]
        if will is not None:
            will.intent = SOCIAL_REQUEST_INTENT
            will.score = 92.0 + (_float(row.get("urgency"), 0.5) * 8.0)
            will.target = target_tuple
            will.target_eid = requester
            will.last_tick = _int(getattr(self.sim, "tick", 0), 0)
            will.social_request_id = row["id"]
        row["status"] = "in_progress"
        if row.get("started_tick") is None:
            row["started_tick"] = _int(getattr(self.sim, "tick", 0), 0)
        row["last_changed_tick"] = _int(getattr(self.sim, "tick", 0), 0)

    def update(self) -> None:
        now = _int(getattr(self.sim, "tick", 0), 0)
        for row in tuple(social_request_state(self.sim)["requests"].values()):
            if not isinstance(row, dict):
                continue
            status = _token(row.get("status"))
            if status in TERMINAL_REQUEST_STATUSES:
                continue
            if now > _int(row.get("deadline_tick"), now + 1):
                if status in {"accepted", "in_progress"}:
                    recipient = _int(row.get("recipient_eid"), 0)
                    self._clear_actor_intent(recipient, str(row.get("id", "")))
                    resolve_social_request(self.sim, row["id"], fulfilled=False, reason="deadline")
                elif status in {"proposed", "countered", "deferred"}:
                    source_ids = tuple(row.get("occurrence_ids", ()) or ())
                    expired = record_occurrence(
                        self.sim,
                        "social_request_expired",
                        actor_eids=(
                            _int(row.get("requester_eid"), 0),
                            _int(row.get("recipient_eid"), 0),
                            _int(row.get("beneficiary_eid"), 0),
                        ),
                        proposition_ids=tuple(row.get("proposition_ids", ()) or ()),
                        referent_ids=tuple(row.get("referent_ids", ()) or ()),
                        source_occurrence_ids=(source_ids[-1],) if source_ids else (),
                        payload={
                            "request_id": row.get("id"),
                            "request_kind": row.get("kind"),
                            "prior_status": status,
                            "reason": "deadline",
                        },
                        flags=("actor_routed",),
                        dedupe_key=f"social-request:{row.get('id')}:unanswered-expiration",
                    )
                    _append_occurrence(row, expired["id"])
                    row["status"] = "expired"
                    row["outcome_reason"] = "deadline"
                    row["completed_tick"] = now
                    row["last_changed_tick"] = now
                    advance_social_thread(
                        self.sim,
                        row["thread_id"],
                        occurrence_id=expired["id"],
                        status="closed",
                        awaiting_actor_eid=None,
                    )
                continue
            if status == "deferred" and now >= _int(row.get("response_after_tick"), now + 1):
                row["status"] = "proposed"
                row["last_changed_tick"] = now
                advance_social_thread(
                    self.sim,
                    row["thread_id"],
                    status="awaiting_response",
                    awaiting_actor_eid=_int(row.get("awaiting_actor_eid"), 0),
                )
                continue
            if status not in {"accepted", "in_progress"} or now < _int(row.get("due_tick"), now):
                continue
            ai = self.sim.ecs.get(AI).get(_int(row.get("recipient_eid"), 0))
            if status == "in_progress" and ai is not None:
                same_request = (
                    _token(getattr(ai, "state", "")) == SOCIAL_REQUEST_INTENT
                    and str(getattr(ai, "social_request_id", "") or "") == str(row.get("id", ""))
                )
                if same_request:
                    self._start_or_preserve(row)
                    continue
                row["status"] = "accepted"
            self._start_or_preserve(row)


__all__ = (
    "NPCSocialRequestSystem",
    "PERSONAL_FAVOR_MIN_MEETINGS",
    "PERSONAL_REQUEST_COOLDOWN_TICKS",
    "PLAYER_FAVOR_TOPIC_IDS",
    "REQUEST_STATUSES",
    "SOCIAL_REQUEST_INTENT",
    "SOCIAL_REQUEST_SCHEMA_VERSION",
    "TERMINAL_REQUEST_STATUSES",
    "create_social_request",
    "resolve_social_request",
    "respond_to_social_request",
    "social_request",
    "social_request_state",
    "social_requests_for_actor",
    "validate_social_requests",
)
