"""Bounded, actor-routed consequences for Social Fact conversations.

The first consequence is deliberately narrow: after the player asks an NPC to
check an incident account, that NPC may approach one visible trusted contact
and ask what they have heard.  Contact selection never inspects the candidate's
knowledge.  Account comparison occurs only after both actors actually meet,
and this module never reads the canonical incident registry.  Independently
corroborated accounts may then close one protective warning circuit: the NPC
chooses a socially relevant person from their own bonds, physically delivers an
immutable actor-owned packet, and the recipient may visibly heed or contest it.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any

from engine.events import Event
from engine.systems import System
from engine.visibility import observer_can_see_position

from game.components import AI, CreatureIdentity, NPCMemory, NPCSocial, NPCWill, Position, Vitality
from game.social_fact_graph import (
    actor_perspective,
    advance_social_thread,
    occurrence_record,
    open_social_thread,
    record_actor_evidence,
    record_claim,
    record_occurrence,
    social_thread,
)
from game.social_fact_incidents import (
    ensure_actor_incident_perspective,
    incident_knowledge_for,
    project_heard_incident_account,
    project_heard_incident_packet,
)
from game.social_fact_packets import (
    actor_fact_packet,
    create_actor_incident_fact_packet,
    validate_actor_fact_packet,
)


SOCIAL_FACT_ACTION_SCHEMA_VERSION = 2
CORROBORATION_INTENT = "seeking_corroboration"
SOCIAL_FACT_DELIVERY_INTENT = "delivering_social_fact"
SOCIAL_WARNING_HEED_INTENT = "heeding_social_warning"
REQUEST_TTL_TICKS = 600
CONTACT_TTL_TICKS = 90
CONTACT_SIGHT_RADIUS = 12
CONTACT_MIN_BOND_SCORE = 0.28
WARNING_TTL_TICKS = 240
WARNING_CONTACT_TTL_TICKS = 90
WARNING_RELEVANCE_RADIUS = 6
WARNING_MIN_MOTIVATION = 0.52
WARNING_MIN_BOND_SCORE = 0.38
WARNING_RETREAT_RADIUS = 4
CORRECTION_RELAY_TTL_TICKS = 240

_BUSY_STATES = {
    "attacking",
    "chasing",
    "combat",
    "downed",
    "ejecting_target",
    "evading_authority",
    "fleeing",
    "helping_victim",
    "holding",
    "protecting",
    "reporting_incident",
    "seeking_corroboration",
    "seeking_safety",
    "delivering_social_fact",
    "heeding_social_warning",
    "warning",
}
_COMPLETE_TASK_STATUSES = {"completed", "failed"}
_TERMINAL_WARNING_STATUSES = {"delivered", "failed", "not_applicable"}
_TERMINAL_REPAIR_STATUSES = {"delivered", "failed", "not_needed"}


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


def _distance(left: Position, right: Position) -> int:
    return abs(int(left.x) - int(right.x)) + abs(int(left.y) - int(right.y))


def _empty_action_state() -> dict[str, Any]:
    return {
        "schema_version": SOCIAL_FACT_ACTION_SCHEMA_VERSION,
        "actions": {},
    }


def _normalize_task(task: dict[str, Any]) -> dict[str, Any]:
    """Upgrade one saved V1 corroboration task in place."""

    task.setdefault("warning_status", "not_applicable")
    task.setdefault("warning_outcome", None)
    task.setdefault("warning_reason", None)
    task.setdefault("warning_requested_tick", None)
    task.setdefault("warning_expires_tick", 0)
    task.setdefault("warning_candidate_eid", None)
    task.setdefault("warning_candidate_target", None)
    task.setdefault("warning_candidate_expires_tick", 0)
    task.setdefault("warning_attempted_contact_eids", ())
    task.setdefault("warning_relevance", None)
    task.setdefault("warning_packet_occurrence_id", None)
    task.setdefault("warning_delivery_occurrence_id", None)
    task.setdefault("warning_thread_id", None)
    task.setdefault("warning_completed_tick", None)
    task.setdefault("warning_behavior", None)
    task.setdefault("warning_report_delivered", False)
    task.setdefault("warning_progress_reported", False)
    task.setdefault("corroborating_contact_eid", None)
    task.setdefault("correction_relay_status", "not_needed")
    task.setdefault("correction_relay_occurrence_id", None)
    task.setdefault("correction_relay_expires_tick", 0)
    task.setdefault("correction_relay_target", None)
    task.setdefault("correction_relay_target_expires_tick", 0)
    task.setdefault("correction_relay_completed_tick", None)
    task.setdefault("correction_relay_report_delivered", False)
    return task


def social_fact_action_state(sim) -> dict[str, Any]:
    """Return normalized saved operational state for social consequences."""

    raw = getattr(sim, "social_fact_actions", None)
    if not isinstance(raw, dict) or not raw:
        raw = _empty_action_state()
        sim.social_fact_actions = raw
        return raw
    version = _int(raw.get("schema_version"), 0)
    if version > SOCIAL_FACT_ACTION_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported social fact action schema: {version} "
            f"> {SOCIAL_FACT_ACTION_SCHEMA_VERSION}"
        )
    if version <= 0:
        raw = _empty_action_state()
        sim.social_fact_actions = raw
        return raw
    raw["schema_version"] = SOCIAL_FACT_ACTION_SCHEMA_VERSION
    if not isinstance(raw.get("actions"), dict):
        raw["actions"] = {}
    for task in raw["actions"].values():
        if isinstance(task, dict):
            _normalize_task(task)
    sim.social_fact_actions = raw
    return raw


def request_incident_corroboration(
    sim,
    *,
    thread_id: str,
    owner_eid: Any,
    requester_eid: Any,
    incident_id: Any,
    proposition_id: str,
    label: str,
    request_occurrence_id: str,
) -> dict[str, Any]:
    """Create one idempotent saved action for an accepted player request."""

    thread_key = _text(thread_id)
    owner = _int(owner_eid, 0)
    requester = _int(requester_eid, 0)
    incident = _int(incident_id, 0)
    proposition_key = _text(proposition_id)
    request_occurrence_key = _text(request_occurrence_id)
    thread = social_thread(sim, thread_key)
    if not isinstance(thread, dict):
        raise KeyError(f"unknown social fact thread: {thread_key}")
    if owner <= 0 or requester <= 0 or {owner, requester} - set(thread.get("participants", ()) or ()):
        raise ValueError("social fact action actors must participate in its conversation thread")
    if incident <= 0 or proposition_key not in set(thread.get("proposition_ids", ()) or ()):
        raise ValueError("social fact action must reference the thread's incident proposition")
    if occurrence_record(sim, request_occurrence_key) is None:
        raise KeyError(f"unknown social fact action request: {request_occurrence_key}")

    actions = social_fact_action_state(sim)["actions"]
    existing = actions.get(thread_key)
    identity = {
        "kind": "incident_corroboration",
        "thread_id": thread_key,
        "owner_eid": owner,
        "requester_eid": requester,
        "incident_id": incident,
        "proposition_id": proposition_key,
        "request_occurrence_id": request_occurrence_key,
    }
    if isinstance(existing, dict):
        if any(existing.get(key) != value for key, value in identity.items()):
            raise ValueError(f"social fact action identity collision: {thread_key}")
        return copy.deepcopy(existing)

    now = _int(getattr(sim, "tick", 0), 0)
    task = {
        **identity,
        "label": _text(label) or "incident",
        "status": "requested",
        "requested_tick": now,
        "expires_tick": now + REQUEST_TTL_TICKS,
        "candidate_eid": None,
        "candidate_target": None,
        "candidate_expires_tick": 0,
        "attempted_contact_eids": (),
        "outcome": None,
        "contact_thread_id": None,
        "completed_tick": None,
        "report_delivered": False,
        "progress_reported": False,
    }
    _normalize_task(task)
    actions[thread_key] = task
    return copy.deepcopy(task)


def social_fact_action_for_thread(
    sim,
    thread_id: str,
    *,
    owner_eid: Any,
) -> dict[str, Any] | None:
    """Return a dialogue-safe view of an NPC's own follow-up action."""

    task = social_fact_action_state(sim)["actions"].get(_text(thread_id))
    owner = _int(owner_eid, 0)
    if not isinstance(task, dict) or owner <= 0 or _int(task.get("owner_eid"), 0) != owner:
        return None
    return {
        "kind": task.get("kind"),
        "thread_id": task.get("thread_id"),
        "owner_eid": owner,
        "status": task.get("status"),
        "outcome": task.get("outcome"),
        "requested_tick": task.get("requested_tick"),
        "completed_tick": task.get("completed_tick"),
        "report_delivered": bool(task.get("report_delivered", False)),
        "progress_reported": bool(task.get("progress_reported", False)),
        "warning_status": task.get("warning_status"),
        "warning_outcome": task.get("warning_outcome"),
        "warning_completed_tick": task.get("warning_completed_tick"),
        "warning_report_delivered": bool(task.get("warning_report_delivered", False)),
        "warning_progress_reported": bool(task.get("warning_progress_reported", False)),
        "correction_relay_status": task.get("correction_relay_status"),
        "correction_relay_completed_tick": task.get("correction_relay_completed_tick"),
        "correction_relay_report_delivered": bool(task.get("correction_relay_report_delivered", False)),
    }


def social_fact_warning_report_for_thread(
    sim,
    thread_id: str,
    *,
    owner_eid: Any,
) -> dict[str, Any] | None:
    """Return owner-authorized details only after a warning attempt concludes."""

    task = social_fact_action_state(sim)["actions"].get(_text(thread_id))
    owner = _int(owner_eid, 0)
    if not isinstance(task, dict) or owner <= 0 or _int(task.get("owner_eid"), 0) != owner:
        return None
    if _token(task.get("warning_status")) not in _TERMINAL_WARNING_STATUSES:
        return None
    recipient = _int(task.get("warning_candidate_eid"), 0) or None
    identity = None
    if recipient is not None:
        recipient_identity = sim.ecs.get(CreatureIdentity).get(recipient)
        identity = _text(
            getattr(recipient_identity, "personal_name", "")
            or getattr(recipient_identity, "common_name", "")
        ) or "someone I know"
    return {
        "warning_status": _token(task.get("warning_status")),
        "warning_outcome": _token(task.get("warning_outcome")),
        "warning_reason": _token(task.get("warning_reason")),
        "warning_recipient_eid": recipient,
        "warning_recipient_name": identity,
        "warning_relevance": _token(task.get("warning_relevance")),
        "warning_behavior": _token(task.get("warning_behavior")),
        "corrected_at_delivery": bool(task.get("warning_corrected_at_delivery", False)),
        "correction_relay_status": _token(task.get("correction_relay_status")),
    }


def mark_social_fact_action_reported(sim, thread_id: str, *, owner_eid: Any) -> bool:
    task = social_fact_action_state(sim)["actions"].get(_text(thread_id))
    if not isinstance(task, dict) or _int(task.get("owner_eid"), 0) != _int(owner_eid, -1):
        return False
    task["report_delivered"] = True
    task["warning_report_delivered"] = True
    if _token(task.get("correction_relay_status")) in _TERMINAL_REPAIR_STATUSES:
        task["correction_relay_report_delivered"] = True
    return True


def mark_social_fact_action_progress_reported(sim, thread_id: str, *, owner_eid: Any) -> bool:
    task = social_fact_action_state(sim)["actions"].get(_text(thread_id))
    if not isinstance(task, dict) or _int(task.get("owner_eid"), 0) != _int(owner_eid, -1):
        return False
    task["progress_reported"] = True
    return True


def mark_social_fact_warning_progress_reported(sim, thread_id: str, *, owner_eid: Any) -> bool:
    task = social_fact_action_state(sim)["actions"].get(_text(thread_id))
    if not isinstance(task, dict) or _int(task.get("owner_eid"), 0) != _int(owner_eid, -1):
        return False
    task["warning_progress_reported"] = True
    return True


def mark_social_fact_correction_relay_reported(sim, thread_id: str, *, owner_eid: Any) -> bool:
    task = social_fact_action_state(sim)["actions"].get(_text(thread_id))
    if not isinstance(task, dict) or _int(task.get("owner_eid"), 0) != _int(owner_eid, -1):
        return False
    task["correction_relay_report_delivered"] = True
    return True


def request_social_fact_warning_correction(
    sim,
    thread_id: str,
    *,
    owner_eid: Any,
    correction_occurrence_id: str,
) -> bool:
    """Queue a physical correction relay only if a warning was delivered."""

    task = social_fact_action_state(sim)["actions"].get(_text(thread_id))
    owner = _int(owner_eid, 0)
    correction_id = _text(correction_occurrence_id)
    if (
        not isinstance(task, dict)
        or owner <= 0
        or _int(task.get("owner_eid"), 0) != owner
        or occurrence_record(sim, correction_id) is None
    ):
        return False
    if _token(task.get("warning_status")) != "delivered":
        return False
    existing = _text(task.get("correction_relay_occurrence_id"))
    if existing:
        return existing == correction_id
    now = _int(getattr(sim, "tick", 0), 0)
    task["correction_relay_status"] = "requested"
    task["correction_relay_occurrence_id"] = correction_id
    task["correction_relay_expires_tick"] = now + CORRECTION_RELAY_TTL_TICKS
    task["correction_relay_target"] = task.get("warning_delivery_position")
    task["correction_relay_target_expires_tick"] = 0
    task["correction_relay_completed_tick"] = None
    task["correction_relay_report_delivered"] = False
    return True


def validate_social_fact_actions(sim) -> tuple[str, ...]:
    errors = []
    for thread_id, task in social_fact_action_state(sim)["actions"].items():
        if not isinstance(task, dict):
            errors.append(f"social fact action {thread_id} is not a record")
            continue
        thread = social_thread(sim, thread_id)
        if not isinstance(thread, dict):
            errors.append(f"social fact action {thread_id} has no conversation thread")
            continue
        participants = set(thread.get("participants", ()) or ())
        if _int(task.get("owner_eid"), 0) not in participants:
            errors.append(f"social fact action {thread_id} owner is not a participant")
        if _int(task.get("requester_eid"), 0) not in participants:
            errors.append(f"social fact action {thread_id} requester is not a participant")
        if _text(task.get("proposition_id")) not in set(thread.get("proposition_ids", ()) or ()):
            errors.append(f"social fact action {thread_id} has an unrelated proposition")
        if occurrence_record(sim, task.get("request_occurrence_id")) is None:
            errors.append(f"social fact action {thread_id} has no request occurrence")
        if _token(task.get("status")) not in {"requested", "seeking", "completed", "failed"}:
            errors.append(f"social fact action {thread_id} has an invalid status")
        warning_status = _token(task.get("warning_status"))
        if warning_status not in {"not_applicable", "requested", "seeking", "delivered", "failed"}:
            errors.append(f"social fact action {thread_id} has an invalid warning status")
        packet_id = _text(task.get("warning_packet_occurrence_id"))
        if packet_id:
            for error in validate_actor_fact_packet(sim, packet_id):
                errors.append(f"social fact action {thread_id} packet: {error}")
        if warning_status == "delivered" and occurrence_record(sim, task.get("warning_delivery_occurrence_id")) is None:
            errors.append(f"social fact action {thread_id} has no warning delivery occurrence")
        repair_status = _token(task.get("correction_relay_status"))
        if repair_status not in {"not_needed", "requested", "seeking", "delivered", "failed"}:
            errors.append(f"social fact action {thread_id} has an invalid correction relay status")
        if repair_status in {"requested", "seeking", "delivered"} and occurrence_record(
            sim,
            task.get("correction_relay_occurrence_id"),
        ) is None:
            errors.append(f"social fact action {thread_id} has no correction relay source")
    return tuple(errors)


def _thread_was_corrected(sim, thread: Mapping[str, Any]) -> bool:
    origin_id = _text(thread.get("origin_occurrence_id"))
    for occurrence_id in tuple(thread.get("occurrence_ids", ()) or ()):
        occurrence = occurrence_record(sim, occurrence_id)
        if not isinstance(occurrence, dict) or occurrence.get("kind") != "correction":
            continue
        if origin_id in set(occurrence.get("source_occurrence_ids", ()) or ()):
            return True
    return False


class SocialFactConsequenceSystem(System):
    """Carries corroboration, protective warning, and repair through contact."""

    def __init__(self, sim):
        super().__init__(sim)
        self.sim.events.subscribe("npc_corroboration_contact_arrived", self.on_contact_arrived)
        self.sim.events.subscribe("npc_corroboration_contact_failed", self.on_contact_failed)
        self.sim.events.subscribe("npc_social_fact_delivery_arrived", self.on_delivery_arrived)
        self.sim.events.subscribe("npc_social_fact_delivery_failed", self.on_delivery_failed)

    def update(self):
        now = _int(getattr(self.sim, "tick", 0), 0)
        for task in tuple(social_fact_action_state(self.sim)["actions"].values()):
            if not isinstance(task, dict) or task.get("kind") != "incident_corroboration":
                continue
            status = _token(task.get("status"))
            if status not in _COMPLETE_TASK_STATUSES:
                if now > _int(task.get("expires_tick"), 0):
                    self._finish_task(task, outcome="no_contact", failed=True)
                    continue
                if status == "seeking":
                    if now > _int(task.get("candidate_expires_tick"), 0):
                        self._release_candidate(task, reason="lost_contact")
                        continue
                    self._preserve_or_resume(task)
                    continue
                self._start_with_visible_contact(task)
                continue
            self._progress_warning(task, now)
            self._progress_correction_relay(task, now)

    def _actor_available(self, eid: int) -> bool:
        ai = self.sim.ecs.get(AI).get(eid)
        pos = self.sim.ecs.get(Position).get(eid)
        vitality = self.sim.ecs.get(Vitality).get(eid)
        if ai is None or pos is None:
            return False
        if vitality is not None and bool(getattr(vitality, "downed", False)):
            return False
        return _token(getattr(ai, "state", "idle")) not in _BUSY_STATES

    def _actor_name(self, eid: int, fallback: str = "someone") -> str:
        identity = self.sim.ecs.get(CreatureIdentity).get(eid)
        return _text(
            getattr(identity, "personal_name", "")
            or getattr(identity, "common_name", "")
        ) or fallback

    def _visible_position(self, observer: int, candidate: int, radius: int) -> tuple[int, int, int] | None:
        observer_pos = self.sim.ecs.get(Position).get(observer)
        candidate_pos = self.sim.ecs.get(Position).get(candidate)
        if observer_pos is None or candidate_pos is None or int(observer_pos.z) != int(candidate_pos.z):
            return None
        if _distance(observer_pos, candidate_pos) > max(1, int(radius)):
            return None
        if not observer_can_see_position(
            self.sim,
            observer,
            int(observer_pos.x),
            int(observer_pos.y),
            int(observer_pos.z),
            int(candidate_pos.x),
            int(candidate_pos.y),
            int(candidate_pos.z),
            max(1, int(radius)),
        ):
            return None
        return (int(candidate_pos.x), int(candidate_pos.y), int(candidate_pos.z))

    def _warning_motivation(self, task: Mapping[str, Any]) -> float:
        owner = _int(task.get("owner_eid"), 0)
        proposition_id = _text(task.get("proposition_id"))
        perspective = actor_perspective(self.sim, owner, proposition_id) or {}
        adapted = ensure_actor_incident_perspective(self.sim, owner, task.get("incident_id"))
        record = adapted.get("record") if isinstance(adapted, dict) else {}
        confidence = _unit(perspective.get("confidence"), 0.0)
        salience = max(
            _unit(perspective.get("salience"), 0.0),
            _unit((record or {}).get("urgency"), 0.0),
            _unit((record or {}).get("social_interest"), 0.0),
        )
        return (confidence * 0.62) + (salience * 0.38)

    def _prepare_warning(self, task: dict[str, Any]) -> None:
        now = _int(getattr(self.sim, "tick", 0), 0)
        if _token(task.get("outcome")) != "corroborated":
            task["warning_status"] = "not_applicable"
            task["warning_outcome"] = "insufficient_account"
            task["warning_completed_tick"] = now
            return
        if self._warning_motivation(task) < WARNING_MIN_MOTIVATION:
            task["warning_status"] = "not_applicable"
            task["warning_outcome"] = "not_motivated"
            task["warning_completed_tick"] = now
            return
        task["warning_status"] = "requested"
        task["warning_requested_tick"] = now
        task["warning_expires_tick"] = now + WARNING_TTL_TICKS
        task["warning_outcome"] = None
        task["warning_completed_tick"] = None

    def _progress_warning(self, task: dict[str, Any], now: int) -> None:
        status = _token(task.get("warning_status"))
        if status in _TERMINAL_WARNING_STATUSES:
            return
        if now > _int(task.get("warning_expires_tick"), 0):
            self._finish_warning(task, outcome="no_relevant_contact", failed=True)
            return
        if status == "seeking":
            if now > _int(task.get("warning_candidate_expires_tick"), 0):
                self._release_warning_candidate(task, reason="lost_warning_contact")
                return
            self._preserve_delivery_intent(task, delivery_kind="warning")
            return
        self._start_warning_with_visible_contact(task)

    def _warning_candidate_rows(
        self,
        task: Mapping[str, Any],
    ) -> tuple[tuple[float, int, tuple[int, int, int], str], ...]:
        owner = _int(task.get("owner_eid"), 0)
        requester = _int(task.get("requester_eid"), 0)
        corroborator = _int(task.get("corroborating_contact_eid"), 0)
        owner_pos = self.sim.ecs.get(Position).get(owner)
        social = self.sim.ecs.get(NPCSocial).get(owner)
        adapted = ensure_actor_incident_perspective(self.sim, owner, task.get("incident_id"))
        snapshot = adapted.get("snapshot") if isinstance(adapted, dict) else {}
        location = snapshot.get("location") if isinstance(snapshot, Mapping) else None
        if owner_pos is None or not isinstance(social, NPCSocial):
            return ()
        attempted = {
            _int(value, -1)
            for value in tuple(task.get("warning_attempted_contact_eids", ()) or ())
        }
        rows = []
        for raw_eid, bond in tuple((social.bonds or {}).items()):
            candidate = _int(raw_eid, 0)
            if candidate <= 0 or candidate in {owner, requester, corroborator} or candidate in attempted:
                continue
            if not isinstance(bond, dict) or not self._actor_available(candidate):
                continue
            target = self._visible_position(owner, candidate, CONTACT_SIGHT_RADIUS)
            if target is None:
                continue
            trust = _unit(bond.get("trust"), 0.0)
            closeness = _unit(bond.get("closeness"), 0.0)
            protectiveness = _unit(bond.get("protectiveness"), 0.0)
            bond_score = (protectiveness * 0.48) + (closeness * 0.32) + (trust * 0.2)
            if bond_score < WARNING_MIN_BOND_SCORE:
                continue
            relevance = ""
            location_bonus = 0.0
            if isinstance(location, Mapping) and _int(location.get("z"), target[2]) == target[2]:
                place_distance = abs(target[0] - _int(location.get("x"))) + abs(target[1] - _int(location.get("y")))
                if place_distance <= WARNING_RELEVANCE_RADIUS:
                    relevance = "near_reported_location"
                    location_bonus = max(0.0, 0.22 - (place_distance * 0.025))
            bond_kind = _token(bond.get("kind"))
            if not relevance and bond_kind in {"family", "partner"} and protectiveness >= 0.72:
                relevance = "person_i_protect"
            if not relevance:
                continue
            distance = _distance(owner_pos, self.sim.ecs.get(Position).get(candidate))
            rows.append((bond_score + location_bonus - (distance * 0.005), candidate, target, relevance))
        rows.sort(key=lambda row: (-row[0], row[1]))
        return tuple(rows)

    def _start_warning_with_visible_contact(self, task: dict[str, Any]) -> bool:
        owner = _int(task.get("owner_eid"), 0)
        if not self._actor_available(owner):
            return False
        rows = self._warning_candidate_rows(task)
        if not rows:
            return False
        _score, candidate, target, relevance = rows[0]
        now = _int(getattr(self.sim, "tick", 0), 0)
        task["warning_status"] = "seeking"
        task["warning_candidate_eid"] = candidate
        task["warning_candidate_target"] = target
        task["warning_candidate_expires_tick"] = min(
            _int(task.get("warning_expires_tick"), now),
            now + WARNING_CONTACT_TTL_TICKS,
        )
        task["warning_relevance"] = relevance
        return self._apply_delivery_intent(task, delivery_kind="warning", target=target)

    def _apply_delivery_intent(
        self,
        task: Mapping[str, Any],
        *,
        delivery_kind: str,
        target: Any,
    ) -> bool:
        owner = _int(task.get("owner_eid"), 0)
        contact = _int(task.get("warning_candidate_eid"), 0)
        if owner <= 0 or contact <= 0 or not isinstance(target, (tuple, list)) or len(target) < 3:
            return False
        ai = self.sim.ecs.get(AI).get(owner)
        will = self.sim.ecs.get(NPCWill).get(owner)
        if ai is None:
            return False
        target_xyz = (_int(target[0]), _int(target[1]), _int(target[2]))
        ai.state = SOCIAL_FACT_DELIVERY_INTENT
        ai.target = target_xyz
        ai.target_eid = contact
        ai.social_fact_action_thread_id = _text(task.get("thread_id"))
        ai.social_fact_contact_eid = contact
        ai.social_fact_delivery_kind = _token(delivery_kind)
        if will is not None:
            will.intent = SOCIAL_FACT_DELIVERY_INTENT
            will.score = 66.0 if _token(delivery_kind) == "warning" else 61.0
            will.target = target_xyz
            will.target_eid = contact
            will.last_tick = _int(getattr(self.sim, "tick", 0), 0)
        self.sim.emit(Event(
            "npc_intent_changed",
            npc_eid=owner,
            intent=SOCIAL_FACT_DELIVERY_INTENT,
            score=66.0 if _token(delivery_kind) == "warning" else 61.0,
            target=target_xyz,
            target_eid=contact,
        ))
        return True

    def _preserve_delivery_intent(self, task: dict[str, Any], *, delivery_kind: str) -> None:
        owner = _int(task.get("owner_eid"), 0)
        ai = self.sim.ecs.get(AI).get(owner)
        if ai is None:
            return
        if (
            _token(getattr(ai, "state", "")) == SOCIAL_FACT_DELIVERY_INTENT
            and _text(getattr(ai, "social_fact_action_thread_id", "")) == _text(task.get("thread_id"))
            and _token(getattr(ai, "social_fact_delivery_kind", "")) == _token(delivery_kind)
        ):
            target = (
                task.get("warning_candidate_target")
                if _token(delivery_kind) == "warning"
                else task.get("correction_relay_target")
            )
            # Re-emit the bounded intent so a freshly restored movement
            # scheduler observes work that was already in flight at save time.
            self._apply_delivery_intent(task, delivery_kind=delivery_kind, target=target)
            return
        if _token(getattr(ai, "state", "idle")) in _BUSY_STATES:
            return
        target = (
            task.get("warning_candidate_target")
            if _token(delivery_kind) == "warning"
            else task.get("correction_relay_target")
        )
        self._apply_delivery_intent(task, delivery_kind=delivery_kind, target=target)

    def _clear_delivery_intent(self, task: Mapping[str, Any]) -> None:
        owner = _int(task.get("owner_eid"), 0)
        ai = self.sim.ecs.get(AI).get(owner)
        will = self.sim.ecs.get(NPCWill).get(owner)
        if ai is not None and _text(getattr(ai, "social_fact_action_thread_id", "")) == _text(task.get("thread_id")):
            if _token(getattr(ai, "state", "")) == SOCIAL_FACT_DELIVERY_INTENT:
                ai.state = "idle"
                ai.target = None
                ai.target_eid = None
            for attr in (
                "social_fact_action_thread_id",
                "social_fact_contact_eid",
                "social_fact_delivery_kind",
            ):
                if hasattr(ai, attr):
                    delattr(ai, attr)
        if will is not None and _token(getattr(will, "intent", "")) == SOCIAL_FACT_DELIVERY_INTENT:
            will.intent = "idle"
            will.score = 0.0
            will.target = None
            will.target_eid = None
            will.last_tick = _int(getattr(self.sim, "tick", 0), 0)

    def _release_warning_candidate(self, task: dict[str, Any], *, reason: str) -> None:
        candidate = _int(task.get("warning_candidate_eid"), 0)
        attempted = {
            _int(value, -1)
            for value in tuple(task.get("warning_attempted_contact_eids", ()) or ())
        }
        if candidate > 0:
            attempted.add(candidate)
        self._clear_delivery_intent(task)
        task["warning_attempted_contact_eids"] = tuple(sorted(value for value in attempted if value > 0))
        task["warning_status"] = "requested"
        task["warning_candidate_eid"] = None
        task["warning_candidate_target"] = None
        task["warning_candidate_expires_tick"] = 0
        task["warning_reason"] = _token(reason) or "warning_contact_failed"

    def on_delivery_failed(self, event) -> None:
        data = dict(getattr(event, "data", {}) or {})
        task = social_fact_action_state(self.sim)["actions"].get(_text(data.get("thread_id")))
        if not isinstance(task, dict) or _int(data.get("npc_eid"), -1) != _int(task.get("owner_eid"), 0):
            return
        delivery_kind = _token(data.get("delivery_kind"))
        if delivery_kind == "warning" and _token(task.get("warning_status")) == "seeking":
            self._release_warning_candidate(task, reason=data.get("reason", "warning_contact_failed"))
        elif delivery_kind == "correction" and _token(task.get("correction_relay_status")) == "seeking":
            self._release_correction_relay(task, reason=data.get("reason", "correction_contact_failed"))

    def on_delivery_arrived(self, event) -> None:
        data = dict(getattr(event, "data", {}) or {})
        task = social_fact_action_state(self.sim)["actions"].get(_text(data.get("thread_id")))
        if not isinstance(task, dict):
            return
        owner = _int(task.get("owner_eid"), 0)
        contact = _int(task.get("warning_candidate_eid"), 0)
        delivery_kind = _token(data.get("delivery_kind"))
        if _int(data.get("npc_eid"), -1) != owner or _int(data.get("contact_eid"), -1) != contact:
            return
        owner_pos = self.sim.ecs.get(Position).get(owner)
        contact_pos = self.sim.ecs.get(Position).get(contact)
        present = (
            owner_pos is not None
            and contact_pos is not None
            and int(owner_pos.z) == int(contact_pos.z)
            and _distance(owner_pos, contact_pos) <= 1
        )
        if not present:
            if delivery_kind == "warning":
                self._release_warning_candidate(task, reason="warning_contact_not_present")
            elif delivery_kind == "correction":
                self._release_correction_relay(task, reason="correction_contact_not_present")
            return
        if delivery_kind == "warning" and _token(task.get("warning_status")) == "seeking":
            self._resolve_warning_delivery(task, contact)
        elif delivery_kind == "correction" and _token(task.get("correction_relay_status")) == "seeking":
            self._resolve_correction_relay(task, contact)

    def _packet_source_occurrences(self, task: Mapping[str, Any]) -> tuple[str, ...]:
        source_ids = [_text(task.get("request_occurrence_id"))]
        contact_thread = social_thread(self.sim, task.get("contact_thread_id")) or {}
        for occurrence_id in tuple(contact_thread.get("occurrence_ids", ()) or ())[-2:]:
            if _text(occurrence_id):
                source_ids.append(_text(occurrence_id))
        return tuple(dict.fromkeys(value for value in source_ids if value))

    def _recipient_warning_credibility(self, recipient: int, speaker: int) -> float:
        social = self.sim.ecs.get(NPCSocial).get(recipient)
        bond = (social.bonds or {}).get(speaker) if isinstance(social, NPCSocial) else None
        if not isinstance(bond, Mapping):
            return 0.22
        return _unit(bond.get("trust"), 0.22)

    def _resolve_warning_delivery(self, task: dict[str, Any], recipient: int) -> None:
        owner = _int(task.get("owner_eid"), 0)
        requester = _int(task.get("requester_eid"), 0)
        incident_id = _int(task.get("incident_id"), 0)
        proposition_id = _text(task.get("proposition_id"))
        label = _text(task.get("label")) or "incident"
        origin_thread = social_thread(self.sim, task.get("thread_id")) or {}
        corrected = _thread_was_corrected(self.sim, origin_thread)
        prior_view = ensure_actor_incident_perspective(self.sim, recipient, incident_id)
        packet = create_actor_incident_fact_packet(
            self.sim,
            speaker_eid=owner,
            incident_id=incident_id,
            proposition_id=proposition_id,
            purpose="protective_warning",
            source_occurrence_ids=self._packet_source_occurrences(task),
            source_class="independent_account",
            initiating_actor_eid=requester,
            initiating_claim_corrected=corrected,
            attribution_disclosed=True,
            max_hops=1,
            dedupe_key=f"social-fact-warning:packet:{task['thread_id']}:{recipient}",
        )
        requester_name = self._actor_name(requester, "someone")
        if corrected:
            spoken = (
                f"{requester_name} first brought me a story about a {label}, then backed off how certain "
                "they were. I still found a separate account that held up. You're close enough to the place "
                "that I thought you should know both parts."
            )
        else:
            spoken = (
                f"{requester_name} brought me a story about a {label}. I checked it against a separate "
                "account, and it held up. You're close enough to the place that I thought you should know."
            )
        credibility = self._recipient_warning_credibility(recipient, owner)
        claim = record_claim(
            self.sim,
            owner,
            (recipient,),
            proposition_id,
            certainty=max(0.4, _unit(packet.get("confidence"), 0.5)),
            credibility_by_audience={recipient: max(0.28, credibility)},
            salience=max(0.45, _unit(packet.get("salience"), 0.45)),
            spoken_text=spoken,
            source_occurrence_ids=(packet["packet_occurrence_id"],),
            dedupe_key=f"social-fact-warning:delivery:{task['thread_id']}:{recipient}",
        )
        warning_thread = open_social_thread(
            self.sim,
            participants=(owner, recipient),
            proposition_ids=(proposition_id,),
            origin_occurrence_id=claim["id"],
            kind="conversation",
            status="awaiting_response",
            awaiting_actor_eid=recipient,
            tags=("protective_warning", "actor_fact_packet"),
            metadata={
                "exchange_kind": "social_fact_warning",
                "initiating_thread_id": task.get("thread_id"),
                "packet_occurrence_id": packet["packet_occurrence_id"],
                "speaker_eid": owner,
                "recipient_eid": recipient,
                "requester_eid": requester,
                "label": label,
                "relevance": task.get("warning_relevance"),
            },
            thread_key=f"social-fact-warning:{task['thread_id']}:{owner}:{recipient}",
        )

        prior_proposition = _text((prior_view or {}).get("proposition", {}).get("id"))
        prior_record = (prior_view or {}).get("record") if isinstance(prior_view, dict) else {}
        prior_social_warning = bool((prior_record or {}).get("social_fact_warning_thread_id")) or _token(
            (prior_record or {}).get("source_kind")
        ) == "social_warning"
        prior_independent = bool((prior_record or {}).get("firsthand")) or _token(
            (prior_record or {}).get("source_kind")
        ) in {"authority_report", "camera", "official_report", "verified", "witnessed"}
        acceptance_score = (
            (_unit(packet.get("confidence"), 0.5) * 0.58)
            + (credibility * 0.27)
            + 0.16
            - (0.14 if corrected else 0.0)
        )
        if prior_proposition and prior_proposition != proposition_id:
            outcome = "disputed"
            response_line = "That isn't the account I had. I'm not going to pretend those fit together."
        elif prior_proposition == proposition_id and prior_independent:
            outcome = "already_knew"
            response_line = "I know. I had my own reason to take it seriously before you came over."
        elif prior_proposition == proposition_id and prior_social_warning:
            outcome = "already_warned"
            response_line = (
                "Someone already warned me about the same account. Hearing it make another lap doesn't "
                "turn it into a new reason to move."
            )
        elif acceptance_score >= 0.58:
            outcome = "accepted"
            response_line = (
                "All right. I'm not staying close just to see whether the warning was right."
                if not corrected
                else "I hear the qualification. I'm still not staying close just to test the separate account."
            )
        elif acceptance_score >= 0.36:
            outcome = "doubtful"
            response_line = "I'll keep it in mind, but I'm not treating that as settled just because you checked once."
        else:
            outcome = "rejected"
            response_line = "No. That's too many hands away for me to move on it."

        reaction = record_occurrence(
            self.sim,
            "warning_reaction",
            actor_eids=(recipient, owner),
            proposition_ids=(proposition_id,),
            source_occurrence_ids=(claim["id"], packet["packet_occurrence_id"]),
            payload={
                "outcome": outcome,
                "npc_spoken_text": response_line,
                "initiating_claim_corrected": corrected,
            },
            flags=("speech", "attributed", "perceptible", "actor_owned"),
            dedupe_key=f"social-fact-warning:reaction:{task['thread_id']}:{recipient}",
        )
        if outcome in {"disputed", "rejected"}:
            record_actor_evidence(
                self.sim,
                recipient,
                proposition_id,
                reaction["id"],
                polarity="contradict",
                strength=0.5 if outcome == "disputed" else 0.34,
                exposure="heard",
                source_actor_eid=recipient,
                salience=0.5,
                tags=("warning_pushback", outcome),
            )
        advance_social_thread(
            self.sim,
            warning_thread["id"],
            occurrence_id=reaction["id"],
            status="disputed" if outcome == "disputed" else "closed",
            awaiting_actor_eid=None,
        )
        projected = project_heard_incident_packet(
            self.sim,
            recipient,
            owner,
            packet,
            thread_id=warning_thread["id"],
            reaction=outcome,
            origin_thread_id=task.get("thread_id"),
        )
        memory = self.sim.ecs.get(NPCMemory).get(recipient)
        if memory is not None:
            account = packet.get("account") if isinstance(packet.get("account"), Mapping) else {}
            memory.remember(
                _int(getattr(self.sim, "tick", 0), 0),
                "social_fact_warning",
                strength=max(0.35, _unit(packet.get("salience"), 0.45)),
                incident_id=incident_id,
                proposition_id=proposition_id,
                speaker_eid=owner,
                requester_eid=requester,
                reaction=outcome,
                corrected=corrected,
                location=copy.deepcopy(account.get("location")),
            )
        behavior = self._apply_warning_retreat(recipient, packet) if outcome == "accepted" else "kept_position"
        if isinstance(projected, dict):
            projected["social_fact_warning_behavior"] = behavior
        owner_pos = self.sim.ecs.get(Position).get(owner)
        self._clear_delivery_intent(task)
        task["warning_status"] = "delivered"
        task["warning_outcome"] = outcome
        task["warning_packet_occurrence_id"] = packet["packet_occurrence_id"]
        task["warning_delivery_occurrence_id"] = claim["id"]
        task["warning_thread_id"] = warning_thread["id"]
        task["warning_completed_tick"] = _int(getattr(self.sim, "tick", 0), 0)
        task["warning_behavior"] = behavior
        task["warning_corrected_at_delivery"] = corrected
        task["warning_delivery_position"] = (
            (int(owner_pos.x), int(owner_pos.y), int(owner_pos.z)) if owner_pos is not None else None
        )
        task["warning_candidate_target"] = None
        task["warning_candidate_expires_tick"] = 0
        task["correction_relay_status"] = "not_needed"

    def _apply_warning_retreat(self, recipient: int, packet: Mapping[str, Any]) -> str:
        account = packet.get("account") if isinstance(packet.get("account"), Mapping) else {}
        location = account.get("location") if isinstance(account.get("location"), Mapping) else None
        pos = self.sim.ecs.get(Position).get(recipient)
        ai = self.sim.ecs.get(AI).get(recipient)
        will = self.sim.ecs.get(NPCWill).get(recipient)
        if not isinstance(location, Mapping) or pos is None or ai is None:
            return "kept_in_mind"
        warning_z = _int(location.get("z"), int(pos.z))
        if warning_z != int(pos.z):
            return "kept_in_mind"
        warning_x = _int(location.get("x"), int(pos.x))
        warning_y = _int(location.get("y"), int(pos.y))
        current_distance = abs(int(pos.x) - warning_x) + abs(int(pos.y) - warning_y)
        if current_distance > WARNING_RELEVANCE_RADIUS:
            return "kept_in_mind"
        candidates = []
        for x in range(int(pos.x) - WARNING_RETREAT_RADIUS, int(pos.x) + WARNING_RETREAT_RADIUS + 1):
            for y in range(int(pos.y) - WARNING_RETREAT_RADIUS, int(pos.y) + WARNING_RETREAT_RADIUS + 1):
                travel = abs(x - int(pos.x)) + abs(y - int(pos.y))
                if travel <= 0 or travel > WARNING_RETREAT_RADIUS:
                    continue
                if not self.sim.tilemap.in_bounds(x, y) or not self.sim.tilemap.is_walkable(x, y, int(pos.z)):
                    continue
                occupants = set(self.sim.tilemap.entities_at(x, y, int(pos.z)) or ())
                if occupants - {recipient}:
                    continue
                warning_distance = abs(x - warning_x) + abs(y - warning_y)
                if warning_distance <= current_distance:
                    continue
                candidates.append((warning_distance - (travel * 0.12), x, y))
        if not candidates:
            return "wanted_distance_but_stayed"
        candidates.sort(key=lambda row: (-row[0], row[1], row[2]))
        _score, target_x, target_y = candidates[0]
        target = (target_x, target_y, int(pos.z))
        ai.state = SOCIAL_WARNING_HEED_INTENT
        ai.target = target
        ai.target_eid = None
        ai.social_fact_warning_packet_id = _text(packet.get("packet_occurrence_id"))
        if will is not None:
            will.intent = SOCIAL_WARNING_HEED_INTENT
            will.score = 63.0
            will.target = target
            will.target_eid = None
            will.last_tick = _int(getattr(self.sim, "tick", 0), 0)
        self.sim.emit(Event(
            "npc_intent_changed",
            npc_eid=recipient,
            intent=SOCIAL_WARNING_HEED_INTENT,
            score=63.0,
            target=target,
            target_eid=None,
        ))
        return "started_moving_away"

    def _finish_warning(self, task: dict[str, Any], *, outcome: str, failed: bool) -> None:
        self._clear_delivery_intent(task)
        task["warning_status"] = "failed" if failed else "delivered"
        task["warning_outcome"] = _token(outcome) or "unresolved"
        task["warning_completed_tick"] = _int(getattr(self.sim, "tick", 0), 0)
        task["warning_candidate_eid"] = None
        task["warning_candidate_target"] = None
        task["warning_candidate_expires_tick"] = 0

    def _progress_correction_relay(self, task: dict[str, Any], now: int) -> None:
        status = _token(task.get("correction_relay_status"))
        if status in _TERMINAL_REPAIR_STATUSES:
            return
        if now > _int(task.get("correction_relay_expires_tick"), 0):
            self._finish_correction_relay(task, delivered=False, reason="no_correction_contact")
            return
        if status == "seeking":
            if now > _int(task.get("correction_relay_target_expires_tick"), 0):
                self._release_correction_relay(task, reason="lost_correction_contact")
                return
            self._preserve_delivery_intent(task, delivery_kind="correction")
            return
        owner = _int(task.get("owner_eid"), 0)
        recipient = _int(task.get("warning_candidate_eid"), 0)
        if owner <= 0 or recipient <= 0 or not self._actor_available(owner):
            return
        target = self._visible_position(owner, recipient, CONTACT_SIGHT_RADIUS)
        if target is None:
            target = task.get("correction_relay_target")
        if not isinstance(target, (tuple, list)) or len(target) < 3:
            return
        task["correction_relay_status"] = "seeking"
        task["correction_relay_target"] = tuple(target[:3])
        task["correction_relay_target_expires_tick"] = min(
            _int(task.get("correction_relay_expires_tick"), now),
            now + CONTACT_TTL_TICKS,
        )
        self._apply_delivery_intent(task, delivery_kind="correction", target=target)

    def _release_correction_relay(self, task: dict[str, Any], *, reason: str) -> None:
        self._clear_delivery_intent(task)
        task["correction_relay_status"] = "requested"
        task["correction_relay_target"] = None
        task["correction_relay_target_expires_tick"] = 0
        task["correction_relay_failure_reason"] = _token(reason) or "correction_contact_failed"

    def _resolve_correction_relay(self, task: dict[str, Any], recipient: int) -> None:
        owner = _int(task.get("owner_eid"), 0)
        proposition_id = _text(task.get("proposition_id"))
        correction_id = _text(task.get("correction_relay_occurrence_id"))
        label = _text(task.get("label")) or "incident"
        line = (
            f"The person who first brought me that {label} has backed off how certain they were. "
            "I still heard a separate account, but you should know that part changed."
        )
        relay = record_occurrence(
            self.sim,
            "warning_correction_relay",
            actor_eids=(owner, recipient),
            proposition_ids=(proposition_id,),
            source_occurrence_ids=tuple(
                value
                for value in (correction_id, _text(task.get("warning_delivery_occurrence_id")))
                if value
            ),
            payload={"speaker_eid": owner, "recipient_eid": recipient, "spoken_text": line},
            flags=("speech", "attributed", "repair_disclosed"),
            dedupe_key=f"social-fact-warning:correction-relay:{task['thread_id']}:{recipient}",
        )
        record_actor_evidence(
            self.sim,
            recipient,
            proposition_id,
            relay["id"],
            polarity="contradict",
            strength=0.3,
            exposure="heard",
            source_actor_eid=owner,
            salience=0.5,
            tags=("source_correction", "warning_repair"),
        )
        response_line = (
            "I hear you. I already moved on the warning; I can't make that part unhappen."
            if _token(task.get("warning_behavior")) == "started_moving_away"
            else "I hear you. I'll keep the correction with the warning."
        )
        reaction = record_occurrence(
            self.sim,
            "warning_correction_reaction",
            actor_eids=(recipient, owner),
            proposition_ids=(proposition_id,),
            source_occurrence_ids=(relay["id"],),
            payload={"npc_spoken_text": response_line},
            flags=("speech", "attributed", "perceptible"),
            dedupe_key=f"social-fact-warning:correction-reaction:{task['thread_id']}:{recipient}",
        )
        warning_thread = social_thread(self.sim, task.get("warning_thread_id"))
        if isinstance(warning_thread, dict):
            advance_social_thread(self.sim, warning_thread["id"], occurrence_id=relay["id"])
            advance_social_thread(
                self.sim,
                warning_thread["id"],
                occurrence_id=reaction["id"],
                status="disputed",
                awaiting_actor_eid=None,
            )
        knowledge_component = incident_knowledge_for(self.sim, recipient)
        stored = (
            (knowledge_component.records or {}).get(_int(task.get("incident_id"), 0))
            if knowledge_component is not None
            else None
        )
        if isinstance(stored, dict):
            stored["social_fact_warning_correction_tick"] = _int(getattr(self.sim, "tick", 0), 0)
            stored["social_fact_warning_corrected"] = True
            stored["social_fact_warning_correction_relay_id"] = relay["id"]
        self._finish_correction_relay(task, delivered=True, reason="correction_delivered")

    def _finish_correction_relay(self, task: dict[str, Any], *, delivered: bool, reason: str) -> None:
        self._clear_delivery_intent(task)
        task["correction_relay_status"] = "delivered" if delivered else "failed"
        task["correction_relay_completed_tick"] = _int(getattr(self.sim, "tick", 0), 0)
        task["correction_relay_target"] = None
        task["correction_relay_target_expires_tick"] = 0
        task["correction_relay_failure_reason"] = _token(reason)

    def _candidate_rows(self, task: Mapping[str, Any]) -> tuple[tuple[float, int, tuple[int, int, int]], ...]:
        owner = _int(task.get("owner_eid"), 0)
        requester = _int(task.get("requester_eid"), 0)
        owner_pos = self.sim.ecs.get(Position).get(owner)
        social = self.sim.ecs.get(NPCSocial).get(owner)
        if owner_pos is None or not isinstance(social, NPCSocial):
            return ()
        attempted = {_int(value, -1) for value in tuple(task.get("attempted_contact_eids", ()) or ())}
        rows = []
        for raw_eid, bond in tuple((social.bonds or {}).items()):
            candidate = _int(raw_eid, 0)
            if candidate <= 0 or candidate in {owner, requester} or candidate in attempted:
                continue
            if not isinstance(bond, dict) or not self._actor_available(candidate):
                continue
            candidate_pos = self.sim.ecs.get(Position).get(candidate)
            if candidate_pos is None or int(candidate_pos.z) != int(owner_pos.z):
                continue
            distance = _distance(owner_pos, candidate_pos)
            if distance > CONTACT_SIGHT_RADIUS:
                continue
            if not observer_can_see_position(
                self.sim,
                owner,
                int(owner_pos.x),
                int(owner_pos.y),
                int(owner_pos.z),
                int(candidate_pos.x),
                int(candidate_pos.y),
                int(candidate_pos.z),
                CONTACT_SIGHT_RADIUS,
            ):
                continue
            trust = _unit(bond.get("trust"), 0.0)
            closeness = _unit(bond.get("closeness"), 0.0)
            protectiveness = _unit(bond.get("protectiveness"), 0.0)
            score = (trust * 0.5) + (closeness * 0.38) + (protectiveness * 0.12)
            if score < CONTACT_MIN_BOND_SCORE:
                continue
            rows.append((score - (distance * 0.006), candidate, (
                int(candidate_pos.x), int(candidate_pos.y), int(candidate_pos.z),
            )))
        rows.sort(key=lambda row: (-row[0], row[1]))
        return tuple(rows)

    def _start_with_visible_contact(self, task: dict[str, Any]) -> bool:
        owner = _int(task.get("owner_eid"), 0)
        if not self._actor_available(owner):
            return False
        rows = self._candidate_rows(task)
        if not rows:
            return False
        _score, candidate, target = rows[0]
        now = _int(getattr(self.sim, "tick", 0), 0)
        task["status"] = "seeking"
        task["candidate_eid"] = candidate
        task["candidate_target"] = target
        task["candidate_expires_tick"] = min(_int(task.get("expires_tick"), now), now + CONTACT_TTL_TICKS)
        self._apply_intent(task)
        advance_social_thread(self.sim, task["thread_id"], status="acted", awaiting_actor_eid=None)
        return True

    def _apply_intent(self, task: Mapping[str, Any]) -> bool:
        owner = _int(task.get("owner_eid"), 0)
        candidate = _int(task.get("candidate_eid"), 0)
        target = task.get("candidate_target")
        if owner <= 0 or candidate <= 0 or not isinstance(target, (tuple, list)) or len(target) < 3:
            return False
        ai = self.sim.ecs.get(AI).get(owner)
        will = self.sim.ecs.get(NPCWill).get(owner)
        if ai is None:
            return False
        target_xyz = (_int(target[0]), _int(target[1]), _int(target[2]))
        ai.state = CORROBORATION_INTENT
        ai.target = target_xyz
        ai.target_eid = candidate
        ai.social_fact_action_thread_id = _text(task.get("thread_id"))
        ai.social_fact_contact_eid = candidate
        if will is not None:
            will.intent = CORROBORATION_INTENT
            will.score = 64.0
            will.target = target_xyz
            will.target_eid = candidate
            will.last_tick = _int(getattr(self.sim, "tick", 0), 0)
        self.sim.emit(Event(
            "npc_intent_changed",
            npc_eid=owner,
            intent=CORROBORATION_INTENT,
            score=64.0,
            target=target_xyz,
            target_eid=candidate,
        ))
        return True

    def _preserve_or_resume(self, task: dict[str, Any]) -> None:
        owner = _int(task.get("owner_eid"), 0)
        ai = self.sim.ecs.get(AI).get(owner)
        if ai is None:
            return
        if (
            _token(getattr(ai, "state", "")) == CORROBORATION_INTENT
            and _text(getattr(ai, "social_fact_action_thread_id", "")) == _text(task.get("thread_id"))
        ):
            # Save/load restores component state before runtime schedulers.  A
            # fresh intent event makes the existing approach due again.
            self._apply_intent(task)
            return
        if _token(getattr(ai, "state", "idle")) in _BUSY_STATES:
            return
        self._apply_intent(task)

    def _clear_actor_intent(self, task: Mapping[str, Any]) -> None:
        owner = _int(task.get("owner_eid"), 0)
        ai = self.sim.ecs.get(AI).get(owner)
        will = self.sim.ecs.get(NPCWill).get(owner)
        if ai is not None and _text(getattr(ai, "social_fact_action_thread_id", "")) == _text(task.get("thread_id")):
            if _token(getattr(ai, "state", "")) == CORROBORATION_INTENT:
                ai.state = "idle"
                ai.target = None
                ai.target_eid = None
            for attr in ("social_fact_action_thread_id", "social_fact_contact_eid"):
                if hasattr(ai, attr):
                    delattr(ai, attr)
        if will is not None and _token(getattr(will, "intent", "")) == CORROBORATION_INTENT:
            will.intent = "idle"
            will.score = 0.0
            will.target = None
            will.target_eid = None
            will.last_tick = _int(getattr(self.sim, "tick", 0), 0)

    def _release_candidate(self, task: dict[str, Any], *, reason: str) -> None:
        candidate = _int(task.get("candidate_eid"), 0)
        attempted = {_int(value, -1) for value in tuple(task.get("attempted_contact_eids", ()) or ())}
        if candidate > 0:
            attempted.add(candidate)
        self._clear_actor_intent(task)
        task["attempted_contact_eids"] = tuple(sorted(value for value in attempted if value > 0))
        task["status"] = "requested"
        task["candidate_eid"] = None
        task["candidate_target"] = None
        task["candidate_expires_tick"] = 0
        task["last_failure_reason"] = _token(reason) or "contact_failed"

    def on_contact_failed(self, event) -> None:
        data = dict(getattr(event, "data", {}) or {})
        thread_id = _text(data.get("thread_id"))
        task = social_fact_action_state(self.sim)["actions"].get(thread_id)
        if not isinstance(task, dict) or _token(task.get("status")) != "seeking":
            return
        if _int(data.get("npc_eid"), -1) != _int(task.get("owner_eid"), 0):
            return
        self._release_candidate(task, reason=data.get("reason", "contact_failed"))

    def on_contact_arrived(self, event) -> None:
        data = dict(getattr(event, "data", {}) or {})
        thread_id = _text(data.get("thread_id"))
        task = social_fact_action_state(self.sim)["actions"].get(thread_id)
        if not isinstance(task, dict) or _token(task.get("status")) != "seeking":
            return
        owner = _int(task.get("owner_eid"), 0)
        contact = _int(task.get("candidate_eid"), 0)
        if _int(data.get("npc_eid"), -1) != owner or _int(data.get("contact_eid"), -1) != contact:
            return
        owner_pos = self.sim.ecs.get(Position).get(owner)
        contact_pos = self.sim.ecs.get(Position).get(contact)
        if (
            owner_pos is None
            or contact_pos is None
            or int(owner_pos.z) != int(contact_pos.z)
            or _distance(owner_pos, contact_pos) > 1
        ):
            self._release_candidate(task, reason="contact_not_present")
            return
        self._resolve_contact(task, contact)

    def _resolve_contact(self, task: dict[str, Any], contact: int) -> None:
        owner = _int(task.get("owner_eid"), 0)
        incident_id = _int(task.get("incident_id"), 0)
        proposition_id = _text(task.get("proposition_id"))
        original_thread = social_thread(self.sim, task.get("thread_id")) or {}
        contact_view = ensure_actor_incident_perspective(self.sim, contact, incident_id)
        owner_view = actor_perspective(self.sim, owner, proposition_id) or {}
        corrected = _thread_was_corrected(self.sim, original_thread)
        label = _text(task.get("label")) or "incident"

        if corrected:
            query = record_occurrence(
                self.sim,
                "corroboration_query",
                actor_eids=(owner, contact),
                proposition_ids=(proposition_id,),
                source_occurrence_ids=(task.get("request_occurrence_id"),),
                payload={
                    "speaker_eid": owner,
                    "audience_eid": contact,
                    "spoken_text": (
                        f"I was told about a {label}, but the person who told me backed off it. "
                        "Had you heard anything yourself?"
                    ),
                    "correction_disclosed": True,
                },
                flags=("speech", "attributed", "qualified", "repair_disclosed"),
                dedupe_key=f"social-fact-corroboration:qualified-query:{task['thread_id']}:{contact}",
            )
            record_actor_evidence(
                self.sim,
                contact,
                proposition_id,
                query["id"],
                polarity="neutral",
                strength=0.3,
                exposure="heard",
                source_actor_eid=owner,
                salience=0.32,
                tags=("qualified_query", "source_corrected"),
            )
        else:
            query = record_claim(
                self.sim,
                owner,
                (contact,),
                proposition_id,
                certainty=max(0.35, _unit(owner_view.get("confidence"), 0.5)),
                credibility_by_audience={contact: 0.5},
                salience=max(0.3, _unit(owner_view.get("salience"), 0.35)),
                spoken_text=f"Someone told me about a {label}. Had you heard anything yourself?",
                source_occurrence_ids=(task.get("request_occurrence_id"),),
                dedupe_key=f"social-fact-corroboration:query:{task['thread_id']}:{contact}",
            )

        contact_thread = open_social_thread(
            self.sim,
            participants=(owner, contact),
            proposition_ids=(proposition_id,),
            origin_occurrence_id=query["id"],
            kind="conversation",
            status="awaiting_response",
            awaiting_actor_eid=contact,
            tags=("incident_corroboration", "npc_followup"),
            metadata={
                "exchange_kind": "incident_corroboration",
                "incident_id": incident_id,
                "initiating_thread_id": task.get("thread_id"),
                "owner_eid": owner,
                "contact_eid": contact,
                "label": label,
            },
            thread_key=f"incident-corroboration:{task['thread_id']}:{owner}:{contact}",
        )

        if not isinstance(contact_view, dict):
            response = record_occurrence(
                self.sim,
                "corroboration_response",
                actor_eids=(contact, owner),
                proposition_ids=(proposition_id,),
                source_occurrence_ids=(query["id"],),
                payload={"outcome": "no_prior_account", "npc_spoken_text": "No. That's new to me."},
                flags=("speech", "attributed"),
                dedupe_key=f"social-fact-corroboration:no-account:{task['thread_id']}:{contact}",
            )
            advance_social_thread(
                self.sim,
                contact_thread["id"],
                occurrence_id=response["id"],
                status="closed",
                awaiting_actor_eid=None,
            )
            self._finish_task(task, outcome="no_prior_account", contact_thread_id=contact_thread["id"])
            return

        contact_proposition = _text(contact_view["proposition"].get("id"))
        contact_record = contact_view["record"]
        if contact_proposition == proposition_id:
            independent = bool(contact_record.get("firsthand")) or _token(contact_record.get("source_kind")) in {
                "authority_report",
                "camera",
                "official_report",
                "verified",
                "witnessed",
            }
            if independent:
                response = record_occurrence(
                    self.sim,
                    "corroboration",
                    actor_eids=(contact, owner),
                    proposition_ids=(proposition_id,),
                    source_occurrence_ids=(query["id"], contact_view["evidence"]["id"]),
                    payload={
                        "outcome": "independent_match",
                        "npc_spoken_text": "Yes. I have my own reason to believe that happened.",
                        "source_exposure": contact_view["snapshot"].get("firsthand") and "firsthand" or "verified",
                    },
                    flags=("speech", "attributed", "actor_owned", "independent_account"),
                    dedupe_key=f"social-fact-corroboration:match:{task['thread_id']}:{contact}",
                )
                record_actor_evidence(
                    self.sim,
                    owner,
                    proposition_id,
                    response["id"],
                    polarity="support",
                    strength=_unit(contact_record.get("confidence"), 0.5) * 0.85,
                    exposure="heard",
                    source_actor_eid=contact,
                    salience=0.58,
                    tags=("corroboration", "independent_account"),
                )
                advance_social_thread(
                    self.sim,
                    contact_thread["id"],
                    occurrence_id=response["id"],
                    status="corroborated",
                    awaiting_actor_eid=None,
                )
                project_heard_incident_account(
                    self.sim,
                    owner,
                    contact,
                    contact_record,
                    thread_id=contact_thread["id"],
                )
                self._finish_task(task, outcome="corroborated", contact_thread_id=contact_thread["id"])
                return

            response = record_occurrence(
                self.sim,
                "corroboration_response",
                actor_eids=(contact, owner),
                proposition_ids=(proposition_id,),
                source_occurrence_ids=(query["id"], contact_view["evidence"]["id"]),
                payload={
                    "outcome": "same_hearsay",
                    "npc_spoken_text": "I've heard that too, but not for myself.",
                },
                flags=("speech", "attributed", "actor_owned", "hearsay"),
                dedupe_key=f"social-fact-corroboration:echo:{task['thread_id']}:{contact}",
            )
            advance_social_thread(
                self.sim,
                contact_thread["id"],
                occurrence_id=response["id"],
                status="closed",
                awaiting_actor_eid=None,
            )
            self._finish_task(task, outcome="same_hearsay", contact_thread_id=contact_thread["id"])
            return

        counterclaim = record_claim(
            self.sim,
            contact,
            (owner,),
            contact_proposition,
            certainty=_unit(contact_record.get("confidence"), 0.5),
            credibility_by_audience={owner: 0.58},
            salience=max(0.35, _unit(contact_record.get("social_interest"), 0.0)),
            spoken_text="What I heard was different from that.",
            source_occurrence_ids=(query["id"], contact_view["evidence"]["id"]),
            dedupe_key=f"social-fact-corroboration:counterclaim:{task['thread_id']}:{contact}:{contact_proposition}",
        )
        conflict = record_occurrence(
            self.sim,
            "account_conflict",
            actor_eids=(contact, owner),
            proposition_ids=(proposition_id, contact_proposition),
            source_occurrence_ids=(query["id"], counterclaim["id"]),
            payload={"outcome": "different_account", "npc_spoken_text": "That isn't how I heard it."},
            flags=("speech", "attributed", "actor_owned", "unresolved"),
            dedupe_key=f"social-fact-corroboration:conflict:{task['thread_id']}:{contact}",
        )
        record_actor_evidence(
            self.sim,
            owner,
            proposition_id,
            conflict["id"],
            polarity="contradict",
            strength=_unit(contact_record.get("confidence"), 0.5) * 0.62,
            exposure="heard",
            source_actor_eid=contact,
            salience=0.55,
            tags=("different_account", "unresolved"),
        )
        advance_social_thread(self.sim, contact_thread["id"], occurrence_id=counterclaim["id"])
        advance_social_thread(
            self.sim,
            contact_thread["id"],
            occurrence_id=conflict["id"],
            status="disputed",
            awaiting_actor_eid=None,
        )
        project_heard_incident_account(
            self.sim,
            owner,
            contact,
            contact_record,
            thread_id=contact_thread["id"],
        )
        self._finish_task(task, outcome="different_account", contact_thread_id=contact_thread["id"])

    def _finish_task(
        self,
        task: dict[str, Any],
        *,
        outcome: str,
        contact_thread_id: str | None = None,
        failed: bool = False,
    ) -> None:
        corroborating_contact = _int(task.get("candidate_eid"), 0) or None
        self._clear_actor_intent(task)
        task["status"] = "failed" if failed else "completed"
        task["outcome"] = _token(outcome) or "unresolved"
        task["contact_thread_id"] = _text(contact_thread_id) or None
        task["corroborating_contact_eid"] = corroborating_contact
        task["completed_tick"] = _int(getattr(self.sim, "tick", 0), 0)
        task["candidate_eid"] = None
        task["candidate_target"] = None
        task["candidate_expires_tick"] = 0
        self._prepare_warning(task)


__all__ = [
    "CORROBORATION_INTENT",
    "SOCIAL_FACT_DELIVERY_INTENT",
    "SOCIAL_WARNING_HEED_INTENT",
    "SOCIAL_FACT_ACTION_SCHEMA_VERSION",
    "SocialFactConsequenceSystem",
    "mark_social_fact_action_progress_reported",
    "mark_social_fact_action_reported",
    "mark_social_fact_correction_relay_reported",
    "mark_social_fact_warning_progress_reported",
    "request_incident_corroboration",
    "request_social_fact_warning_correction",
    "social_fact_action_for_thread",
    "social_fact_action_state",
    "social_fact_warning_report_for_thread",
    "validate_social_fact_actions",
]
