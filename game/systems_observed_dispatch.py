"""Observed incident dispatch/vigil routing for BAKERRRR.

This module consumes `incident_authority_reported` events and turns them into
bounded, delayed responder movement. It intentionally does not make reports
spawn infinite authorities.

Core invariants:
- reports create dispatch opportunities
- dispatch does not create new reports for the same incident
- existing actors respond first
- civilian vigils are civic/social responses, not guaranteed police response
- police/security may respond if an available local actor and seeded chance allow it
"""

from __future__ import annotations

import hashlib
import hmac
from engine.events import Event
from engine.systems import System

from game.components import AI, JusticeProfile, NPCSocial, NPCTraits, NPCWill, Occupation, Position
from game.incident_runtime import incident_record
from game.organizations import local_protective_pressure_snapshot


PEACE_ROLES = {"guard", "scout", "officer", "police", "deputy", "marshal", "security"}
CIVIC_ROLES = {"civilian", "worker", "resident", "clerk", "cashier", "merchant", "shopkeeper", "manager"}
BUSY_STATES = {
    "protecting",
    "helping_victim",
    "reporting_incident",
    "warning",
    "chasing",
    "seeking_safety",
    "downed",
}
DEFAULT_DISPATCH_DELAY = 40
DEFAULT_VIGIL_RADIUS = 22
DEFAULT_MAX_VIGIL_RESPONDERS = 3
DEFAULT_MAX_PEACE_RESPONDERS = 1


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


def _text(value):
    return str(value or "").strip()


def _key(value):
    return _text(value).lower()


def _clamp(value, lo=0.0, hi=1.0, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    return max(float(lo), min(float(hi), number))


def _dist(a, b):
    return abs(int(a[0]) - int(b[0])) + abs(int(a[1]) - int(b[1]))


def _unit_roll(seed, *parts):
    key = str(seed).encode("utf-8")
    msg = "|".join(str(part) for part in parts).encode("utf-8")
    digest = hmac.new(key, msg, hashlib.sha256).hexdigest()
    return int(digest[:13], 16) / float(0x10000000000000)


def _peace_dispatch_bonus(tags):
    cleaned = {str(tag).strip().lower() for tag in (tags or ()) if str(tag).strip()}
    bonus = 0.0
    if cleaned & {"unarmed_assault", "assault"}:
        bonus = max(bonus, 0.06)
    if cleaned & {"melee_assault", "melee"}:
        bonus = max(bonus, 0.12)
    if cleaned & {"armed_assault", "fire_weapon", "gunfire", "weapon", "murder"}:
        bonus = max(bonus, 0.18)
    if cleaned & {"explosive_discharge", "explosion", "fire"}:
        bonus = max(bonus, 0.24)
    if cleaned & {"homicide", "death"}:
        bonus = max(bonus, 0.3)
    return bonus


def _incident_position(incident, event_data=None):
    event_data = event_data or {}
    x = event_data.get("x", incident.get("x") if isinstance(incident, dict) else None)
    y = event_data.get("y", incident.get("y") if isinstance(incident, dict) else None)
    z = event_data.get("z", incident.get("z", 0) if isinstance(incident, dict) else 0)
    if x is None or y is None:
        return None
    return (_int(x), _int(y), _int(z, 0))


class ObservedIncidentDispatchSystem(System):
    """Creates bounded civic/authority response from official reports.

    It does not create canonical incidents and it does not decide whether an
    NPC cared enough to report. That has already happened upstream. This layer
    only asks: once the report exists, who physically starts moving?
    """

    def __init__(self, sim):
        super().__init__(sim)
        self.pending = {}
        self.active = {}
        self.sim.events.subscribe("incident_authority_reported", self.on_incident_authority_reported)
        self.sim.events.subscribe("npc_investigation_complete", self.on_npc_investigation_complete)
        if not hasattr(sim, "observed_dispatch_stats"):
            sim.observed_dispatch_stats = {
                "queued": 0,
                "ignored_duplicates": 0,
                "vigils_started": 0,
                "peace_dispatched": 0,
                "arrivals": 0,
                "dropped": 0,
            }

    def on_incident_authority_reported(self, event):
        data = dict(getattr(event, "data", {}) or {})
        incident_id = _int(data.get("incident_id"), -1)
        if incident_id < 0:
            return
        incident = incident_record(self.sim, incident_id)
        if not isinstance(incident, dict):
            return

        state = _key(incident.get("dispatch_state"))
        if state in {"pending", "active"}:
            self.sim.observed_dispatch_stats["ignored_duplicates"] += 1
            self.sim.emit(Event(
                "incident_dispatch_ignored",
                incident_id=incident_id,
                reason="dispatch_already_active",
                dispatch_state=state,
            ))
            return

        target = _incident_position(incident, data)
        if target is None:
            self.sim.observed_dispatch_stats["dropped"] += 1
            self.sim.emit(Event("incident_dispatch_dropped", incident_id=incident_id, reason="missing_target"))
            return

        now = _int(getattr(self.sim, "tick", 0), 0)
        delay = self._dispatch_delay(incident_id, incident)
        incident["dispatch_state"] = "pending"
        incident["dispatch_pending_tick"] = now
        incident["dispatch_due_tick"] = now + delay
        incident["dispatch_count"] = _int(incident.get("dispatch_count"), 0) + 1
        incident["dispatch_target"] = target
        incident.setdefault("dispatched_eids", [])

        self.pending[incident_id] = {
            "incident_id": incident_id,
            "target": target,
            "reported_by_eid": _int(data.get("npc_eid"), -1),
            "method": _text(data.get("method")),
            "created_tick": now,
            "due_tick": now + delay,
        }
        self.sim.observed_dispatch_stats["queued"] += 1
        self.sim.emit(Event(
            "incident_dispatch_queued",
            incident_id=incident_id,
            x=target[0],
            y=target[1],
            z=target[2],
            due_tick=now + delay,
            method=_text(data.get("method")),
        ))

    def update(self):
        now = _int(getattr(self.sim, "tick", 0), 0)
        for incident_id, dispatch in tuple(self.pending.items()):
            incident = incident_record(self.sim, incident_id)
            if not isinstance(incident, dict):
                self.pending.pop(incident_id, None)
                self.sim.observed_dispatch_stats["dropped"] += 1
                continue
            if now < _int(dispatch.get("due_tick"), 0):
                continue
            self.pending.pop(incident_id, None)
            self._activate_dispatch(dispatch, incident)

    def on_npc_investigation_complete(self, event):
        data = dict(getattr(event, "data", {}) or {})
        npc_eid = _int(data.get("npc_eid"), -1)
        if npc_eid < 0:
            return
        ai = self.sim.ecs.get(AI).get(npc_eid)
        if not ai:
            return
        incident_id = _int(getattr(ai, "incident_id", -1), -1)
        role = _key(getattr(ai, "response_role", ""))
        if incident_id < 0 or role not in {"vigil_leader", "vigil_attendee", "peace_dispatched"}:
            return
        incident = incident_record(self.sim, incident_id)
        if isinstance(incident, dict):
            arrived = list(incident.get("dispatch_arrived_eids", []) or [])
            if npc_eid not in arrived:
                arrived.append(npc_eid)
            incident["dispatch_arrived_eids"] = arrived
        self.sim.observed_dispatch_stats["arrivals"] += 1
        self.sim.emit(Event(
            "incident_dispatch_arrived",
            incident_id=incident_id,
            npc_eid=npc_eid,
            response_role=role,
            x=data.get("x"),
            y=data.get("y"),
            z=data.get("z"),
        ))
        # Keep the suppress marker for a short while; clear only movement intent.
        if hasattr(ai, "response_role"):
            ai.response_role = None
        if hasattr(ai, "incident_id"):
            ai.incident_id = None

    def _activate_dispatch(self, dispatch, incident):
        incident_id = _int(dispatch.get("incident_id"), -1)
        target = tuple(dispatch.get("target") or ())
        if len(target) != 3:
            return
        incident["dispatch_state"] = "active"
        incident["dispatch_active_tick"] = _int(getattr(self.sim, "tick", 0), 0)

        peace_eids = self._maybe_select_peace_responders(incident_id, incident, target)
        vigil_eids = self._select_vigil_responders(incident_id, incident, target, excluded=set(peace_eids))
        dispatched = []

        for idx, eid in enumerate(peace_eids):
            if self._assign_responder(eid, incident_id, target, response_role="peace_dispatched", score=76.0, offset_index=idx):
                dispatched.append(eid)
                self.sim.observed_dispatch_stats["peace_dispatched"] += 1

        for idx, eid in enumerate(vigil_eids):
            role = "vigil_leader" if idx == 0 else "vigil_attendee"
            if self._assign_responder(eid, incident_id, target, response_role=role, score=48.0 if idx else 58.0, offset_index=idx + len(dispatched)):
                dispatched.append(eid)

        incident["dispatched_eids"] = list(dict.fromkeys(list(incident.get("dispatched_eids", []) or []) + dispatched))
        if vigil_eids:
            self.sim.observed_dispatch_stats["vigils_started"] += 1
        self.active[incident_id] = {
            "incident_id": incident_id,
            "target": target,
            "dispatched_eids": tuple(dispatched),
            "started_tick": _int(getattr(self.sim, "tick", 0), 0),
        }
        self.sim.emit(Event(
            "incident_dispatch_started",
            incident_id=incident_id,
            x=target[0],
            y=target[1],
            z=target[2],
            dispatched_eids=tuple(dispatched),
            peace_eids=tuple(peace_eids),
            vigil_eids=tuple(vigil_eids),
        ))

    def _dispatch_delay(self, incident_id, incident):
        severity = _int(incident.get("severity"), 0) if isinstance(incident, dict) else 0
        base = max(12, DEFAULT_DISPATCH_DELAY - int(severity * 0.25))
        prop = self.sim.properties.get(_text((incident or {}).get("property_id")))
        pressure = local_protective_pressure_snapshot(self.sim, prop) if isinstance(prop, dict) else {}
        dispatch_bonus = _float(pressure.get("dispatch_bonus"), 0.0)
        followthrough_bonus = _float(pressure.get("response_followthrough_bonus"), 0.0)
        readiness_tier = _int(pressure.get("response_readiness_tier"), 0)
        base = max(8, base - int(round(dispatch_bonus * 14.0)) - int(round(followthrough_bonus * 10.0)) - max(0, readiness_tier * 2))
        jitter = int(_unit_roll(getattr(self.sim, "seed", ""), "dispatch_delay", incident_id) * 18)
        return base + jitter

    def _maybe_select_peace_responders(self, incident_id, incident, target):
        max_count = _int(getattr(self.sim, "observed_dispatch_max_peace", DEFAULT_MAX_PEACE_RESPONDERS), DEFAULT_MAX_PEACE_RESPONDERS)
        if max_count <= 0:
            return []
        severity = _int(incident.get("severity"), 0) if isinstance(incident, dict) else 0
        tags = {str(tag).strip().lower() for tag in incident.get("tags", ()) or ()} if isinstance(incident, dict) else set()
        base_chance = 0.18 + min(0.45, severity / 180.0)
        base_chance += _peace_dispatch_bonus(tags)
        prop = self.sim.properties.get(_text((incident or {}).get("property_id")))
        pressure = local_protective_pressure_snapshot(self.sim, prop) if isinstance(prop, dict) else {}
        base_chance += min(
            0.18,
            (_float(pressure.get("dispatch_bonus"), 0.0) * 0.22)
            + (_float(pressure.get("response_followthrough_bonus"), 0.0) * 0.18)
            + (_int(pressure.get("response_readiness_tier"), 0) * 0.05),
        )
        if _unit_roll(getattr(self.sim, "seed", ""), "peace_dispatch", incident_id, severity) > min(0.85, base_chance):
            return []
        return [eid for _, eid in self._rank_candidates(target, peace_only=True)[:max_count]]

    def _select_vigil_responders(self, incident_id, incident, target, *, excluded=None):
        excluded = set(excluded or ())
        max_count = _int(getattr(self.sim, "observed_dispatch_max_vigil", DEFAULT_MAX_VIGIL_RESPONDERS), DEFAULT_MAX_VIGIL_RESPONDERS)
        if max_count <= 0:
            return []
        ranked = []
        for score, eid in self._rank_candidates(target, peace_only=False):
            if eid in excluded:
                continue
            ranked.append((score, eid))
        return [eid for _, eid in ranked[:max_count]]

    def _rank_candidates(self, target, *, peace_only=False):
        ais = self.sim.ecs.get(AI)
        positions = self.sim.ecs.get(Position)
        traits_map = self.sim.ecs.get(NPCTraits)
        socials = self.sim.ecs.get(NPCSocial)
        justices = self.sim.ecs.get(JusticeProfile)
        occupations = self.sim.ecs.get(Occupation)
        ranked = []
        for eid, ai in ais.items():
            role = _key(getattr(ai, "role", ""))
            occupation = occupations.get(eid)
            career = _key(getattr(occupation, "career", ""))
            is_peace = role in PEACE_ROLES or any(token in career for token in ("guard", "security", "patrol", "police", "deputy"))
            if peace_only and not is_peace:
                continue
            if not peace_only and is_peace:
                continue
            if not peace_only and role not in CIVIC_ROLES and not any(token in career for token in ("resident", "mourner", "witness", "worker", "clerk", "nurse", "medic")):
                continue
            if _key(getattr(ai, "state", "")) in BUSY_STATES:
                continue
            pos = positions.get(eid)
            if not pos or int(pos.z) != int(target[2]):
                continue
            distance = _dist((pos.x, pos.y, pos.z), target)
            if distance > DEFAULT_VIGIL_RADIUS:
                continue
            traits = traits_map.get(eid) or NPCTraits()
            justice = justices.get(eid)
            civic_pull = _clamp(getattr(traits, "empathy", 0.5), default=0.5) * 0.25
            civic_pull += _clamp(getattr(traits, "loyalty", 0.5), default=0.5) * 0.18
            civic_pull += _clamp(getattr(traits, "bravery", 0.5), default=0.5) * 0.18
            if justice:
                civic_pull += _clamp(getattr(justice, "justice", 0.5), default=0.5) * (0.25 if peace_only else 0.08)
            social = socials.get(eid)
            if social and getattr(social, "bonds", None):
                civic_pull += min(0.12, len(social.bonds) * 0.012)
            jitter = _unit_roll(getattr(self.sim, "seed", ""), "dispatch_candidate", target, eid) * 0.08
            score = civic_pull + jitter - (distance / float(DEFAULT_VIGIL_RADIUS + 1)) * 0.35
            ranked.append((score, eid))
        ranked.sort(key=lambda row: (row[0], -row[1]), reverse=True)
        return ranked

    def _assign_responder(self, eid, incident_id, target, *, response_role, score=50.0, offset_index=0):
        ai = self.sim.ecs.get(AI).get(eid)
        will = self.sim.ecs.get(NPCWill).get(eid)
        if not ai or not will:
            return False
        incident = incident_record(self.sim, incident_id)
        prop = self.sim.properties.get(_text((incident or {}).get("property_id"))) if isinstance(incident, dict) else None
        pressure = local_protective_pressure_snapshot(self.sim, prop) if isinstance(prop, dict) else {}
        adjusted_score = float(score)
        adjusted_score += (_float(pressure.get("response_score_bonus"), 0.0) * 0.6)
        adjusted_score += (_int(pressure.get("response_readiness_tier"), 0) * 2.0)
        adjusted_score += (_float(pressure.get("confrontation_posture_bonus"), 0.0) * 8.0)
        target = self._offset_target(target, incident_id, eid, offset_index)
        ai.state = "investigating"
        ai.target = target
        ai.target_eid = None
        ai.incident_id = int(incident_id)
        ai.response_role = str(response_role)
        ai.suppress_report_for_incident_id = int(incident_id)
        will.intent = "investigating"
        will.score = float(adjusted_score)
        will.target = target
        will.target_eid = None
        will.last_tick = _int(getattr(self.sim, "tick", 0), 0)
        self.sim.emit(Event(
            "incident_responder_assigned",
            incident_id=incident_id,
            npc_eid=eid,
            response_role=response_role,
            x=target[0],
            y=target[1],
            z=target[2],
        ))
        return True

    def _offset_target(self, target, incident_id, eid, offset_index):
        offsets = ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1))
        idx = int(_unit_roll(getattr(self.sim, "seed", ""), "dispatch_offset", incident_id, eid, offset_index) * len(offsets))
        dx, dy = offsets[min(len(offsets) - 1, idx)]
        return (int(target[0]) + dx, int(target[1]) + dy, int(target[2]))
