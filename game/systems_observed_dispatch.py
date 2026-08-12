"""Observed incident dispatch/vigil routing for BAKERRRR.

This module consumes `incident_authority_reported` events and turns them into
bounded, delayed responder movement. It intentionally does not make reports
spawn infinite authorities.

Core invariants:
- reports create dispatch opportunities
- dispatch does not create new reports for the same incident
- existing actors respond first
- civilian vigils are civic/social responses, not guaranteed police response
- a usable reported subject description receives one available bounded peace response
- reports without a usable subject lead retain a seeded police/security response chance
"""

from __future__ import annotations

import hashlib
import hmac
from engine.events import Event
from engine.systems import System

from game.components import AI, JusticeProfile, NPCSocial, NPCTraits, NPCWill, Occupation, Position
from game.identity_evidence import transmitted_subject_account
from game.incident_runtime import incident_record, incident_records, mark_incident_registry_changed
from game.justice_identity_runtime import justice_case_for_incident
from game.organizations import local_protective_pressure_snapshot
from game.purposeful_observation import begin_purposeful_report_search
from game.specialist_casework import (
    FIRE_DOMAIN,
    WILDLIFE_DOMAIN,
    record_specialist_referral,
    record_specialist_scene_review,
    specialist_casework_kind,
    specialist_domain_for_career,
    specialist_referral,
    specialist_referral_read,
    specialist_response_role,
)


PEACE_ROLES = {"guard", "scout", "officer", "police", "deputy", "marshal", "security"}
PEACE_CAREER_TOKENS = (
    "guard", "security", "patrol", "police", "deputy", "marshal", "bailiff",
    "detective", "investigator", "inspector", "ranger", "warden", "conservation",
    "wildlife_enforcement",
)
INVESTIGATOR_CAREER_TOKENS = ("detective", "investigator", "inspector")
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
DEFAULT_PEACE_DISPATCH_RADIUS = 80
DEFAULT_MAX_VIGIL_RESPONDERS = 3
DEFAULT_MAX_PEACE_RESPONDERS = 1
SPECIALIST_RESPONSE_ROLES = {
    "wildlife_enforcement_dispatched": WILDLIFE_DOMAIN,
    "fire_investigator_dispatched": FIRE_DOMAIN,
}
SPECIALIST_RETRY_TICKS = 60
SPECIALIST_MAX_ASSIGNMENT_ATTEMPTS = 6


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
        self.specialist_pending = {}
        self.specialist_active = {}
        self.sim.events.subscribe("incident_authority_reported", self.on_incident_authority_reported)
        self.sim.events.subscribe("fire_response_scene_assessed", self.on_fire_response_scene_assessed)
        self.sim.events.subscribe("npc_investigation_complete", self.on_npc_investigation_complete)
        if not hasattr(sim, "observed_dispatch_stats"):
            sim.observed_dispatch_stats = {
                "queued": 0,
                "ignored_duplicates": 0,
                "vigils_started": 0,
                "peace_dispatched": 0,
                "arrivals": 0,
                "dropped": 0,
                "specialist_referred": 0,
                "specialist_dispatched": 0,
                "specialist_unstaffed": 0,
            }
        else:
            self.sim.observed_dispatch_stats.setdefault("specialist_referred", 0)
            self.sim.observed_dispatch_stats.setdefault("specialist_dispatched", 0)
            self.sim.observed_dispatch_stats.setdefault("specialist_unstaffed", 0)
        self._restore_specialist_pending()

    def _restore_specialist_pending(self):
        now = _int(getattr(self.sim, "tick", 0), 0)
        for incident in incident_records(self.sim):
            incident_id = _int(incident.get("id"), -1)
            target = _incident_position(incident)
            referrals = incident.get("specialist_referrals")
            if incident_id < 0 or target is None or not isinstance(referrals, dict):
                continue
            for domain, referral in referrals.items():
                domain = _key(domain)
                if (
                    domain not in {WILDLIFE_DOMAIN, FIRE_DOMAIN}
                    or not isinstance(referral, dict)
                    or _key(referral.get("status")) not in {"pending", "waiting_for_specialist"}
                ):
                    continue
                key = (incident_id, domain)
                self.specialist_pending[key] = {
                    "incident_id": incident_id,
                    "domain": domain,
                    "target": target,
                    "created_tick": _int(referral.get("referred_tick"), now),
                    "due_tick": max(now, _int(referral.get("dispatch_due_tick"), now)),
                    "attempts": max(0, _int(referral.get("dispatch_attempts"), 0)),
                }

    def on_incident_authority_reported(self, event):
        data = dict(getattr(event, "data", {}) or {})
        incident_id = _int(data.get("incident_id"), -1)
        if incident_id < 0:
            return
        incident = incident_record(self.sim, incident_id)
        if not isinstance(incident, dict):
            return

        self._consider_specialist_handoff(incident, source="authority_report")

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

    def on_fire_response_scene_assessed(self, event):
        incident = incident_record(self.sim, event.data.get("incident_id"))
        if not isinstance(incident, dict) or not bool(incident.get("officially_reported", False)):
            return
        self._consider_specialist_handoff(incident, source="fire_response_assessment")

    def _consider_specialist_handoff(self, incident, *, source="authority_report"):
        read = specialist_referral_read(self.sim, incident)
        if not isinstance(read, dict):
            return None
        referral = record_specialist_referral(self.sim, incident, read, source=source)
        if not isinstance(referral, dict):
            return None
        domain = _key(referral.get("domain"))
        status = _key(referral.get("status"))
        if domain not in {WILDLIFE_DOMAIN, FIRE_DOMAIN} or status in {"pending", "assigned", "scene_reviewed"}:
            return referral
        target = _incident_position(incident)
        if target is None:
            referral["status"] = "missing_scene"
            referral["updated_tick"] = _int(getattr(self.sim, "tick", 0), 0)
            mark_incident_registry_changed(self.sim)
            return referral
        incident_id = _int(incident.get("id"), -1)
        key = (incident_id, domain)
        if key in self.specialist_pending or key in self.specialist_active:
            return referral
        now = _int(getattr(self.sim, "tick", 0), 0)
        delay = self._dispatch_delay(incident_id, incident) + (12 if domain == WILDLIFE_DOMAIN else 20)
        self.specialist_pending[key] = {
            "incident_id": incident_id,
            "domain": domain,
            "target": target,
            "created_tick": now,
            "due_tick": now + delay,
            "attempts": 0,
        }
        referral["status"] = "pending"
        referral["dispatch_due_tick"] = now + delay
        referral["updated_tick"] = now
        mark_incident_registry_changed(self.sim)
        self.sim.observed_dispatch_stats["specialist_referred"] += 1
        return referral

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
        for key, dispatch in tuple(self.specialist_pending.items()):
            if now < _int(dispatch.get("due_tick"), 0):
                continue
            incident = incident_record(self.sim, dispatch.get("incident_id"))
            if not isinstance(incident, dict):
                self.specialist_pending.pop(key, None)
                continue
            if self._activate_specialist_dispatch(dispatch, incident):
                self.specialist_pending.pop(key, None)
                continue
            attempts = _int(dispatch.get("attempts"), 0) + 1
            dispatch["attempts"] = attempts
            referral = specialist_referral(incident, dispatch.get("domain"))
            if attempts >= SPECIALIST_MAX_ASSIGNMENT_ATTEMPTS:
                self.specialist_pending.pop(key, None)
                if isinstance(referral, dict):
                    referral["status"] = "unstaffed"
                    referral["dispatch_attempts"] = attempts
                    referral["updated_tick"] = now
                    mark_incident_registry_changed(self.sim)
                self.sim.observed_dispatch_stats["specialist_unstaffed"] += 1
            else:
                dispatch["due_tick"] = now + SPECIALIST_RETRY_TICKS
                if isinstance(referral, dict):
                    referral["status"] = "waiting_for_specialist"
                    referral["dispatch_attempts"] = attempts
                    referral["dispatch_due_tick"] = dispatch["due_tick"]
                    referral["updated_tick"] = now
                    mark_incident_registry_changed(self.sim)

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
        if incident_id < 0 or role not in {"vigil_leader", "vigil_attendee", "peace_dispatched", *SPECIALIST_RESPONSE_ROLES}:
            return
        incident = incident_record(self.sim, incident_id)
        domain = SPECIALIST_RESPONSE_ROLES.get(role, "")
        if domain:
            review = record_specialist_scene_review(
                self.sim,
                incident_id,
                npc_eid,
                domain=domain,
                x=data.get("x"),
                y=data.get("y"),
                z=data.get("z"),
            )
            self.specialist_active.pop((incident_id, domain), None)
            if isinstance(review, dict):
                data["specialist_reviewed"] = True
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

        investigator_eid = self._select_case_investigator(incident_id, target)
        case = justice_case_for_incident(self.sim, incident_id)
        account = case.get("best_subject_account") if isinstance(case, dict) and isinstance(case.get("best_subject_account"), dict) else {}
        description = account.get("description") if isinstance(account.get("description"), dict) else {}
        requires_casework_response = bool(
            isinstance(case, dict)
            and _key(case.get("status")) == "unresolved"
            and bool(case.get("factual_incident", False))
            and description
        )
        peace_eids = (
            [investigator_eid]
            if investigator_eid is not None
            else self._maybe_select_peace_responders(
                incident_id,
                incident,
                target,
                required=requires_casework_response,
            )
        )
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

    def _activate_specialist_dispatch(self, dispatch, incident):
        incident_id = _int(dispatch.get("incident_id"), -1)
        domain = _key(dispatch.get("domain"))
        target = tuple(dispatch.get("target") or ())
        if incident_id < 0 or domain not in {WILDLIFE_DOMAIN, FIRE_DOMAIN} or len(target) != 3:
            return False
        specialist_eid = self._select_specialist_responder(domain, target)
        if specialist_eid is None:
            return False
        response_role = specialist_response_role(domain)
        if not self._assign_responder(
            specialist_eid,
            incident_id,
            target,
            response_role=response_role,
            score=82.0,
            offset_index=0,
        ):
            return False
        now = _int(getattr(self.sim, "tick", 0), 0)
        referral = specialist_referral(incident, domain)
        if isinstance(referral, dict):
            referral["status"] = "assigned"
            referral["specialist_eid"] = int(specialist_eid)
            referral["assigned_tick"] = now
            referral["updated_tick"] = now
            mark_incident_registry_changed(self.sim)
        key = (incident_id, domain)
        self.specialist_active[key] = {
            "incident_id": incident_id,
            "domain": domain,
            "target": target,
            "specialist_eid": int(specialist_eid),
            "started_tick": now,
        }
        incident["dispatched_eids"] = list(dict.fromkeys(
            list(incident.get("dispatched_eids", []) or []) + [int(specialist_eid)]
        ))
        self.sim.observed_dispatch_stats["specialist_dispatched"] += 1
        self.sim.emit(Event(
            "incident_specialist_dispatched",
            incident_id=incident_id,
            specialist_eid=int(specialist_eid),
            domain=domain,
            response_role=response_role,
            x=target[0],
            y=target[1],
            z=target[2],
        ))
        return True

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

    def _maybe_select_peace_responders(self, incident_id, incident, target, *, required=False):
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
        if (
            not bool(required)
            and _unit_roll(getattr(self.sim, "seed", ""), "peace_dispatch", incident_id, severity) > min(0.85, base_chance)
        ):
            return []
        occupations = self.sim.ecs.get(Occupation)
        available = [
            eid
            for _score, eid in self._rank_candidates(target, peace_only=True)
            if not specialist_domain_for_career(getattr(occupations.get(eid), "career", ""))
        ]
        return available[:max_count]

    def _select_case_investigator(self, incident_id, target):
        case = justice_case_for_incident(self.sim, incident_id)
        if not isinstance(case, dict) or _key(case.get("status")) != "unresolved":
            return None
        occupations = self.sim.ecs.get(Occupation)
        for _score, eid in self._rank_candidates(target, peace_only=True):
            occupation = occupations.get(eid)
            career = _key(getattr(occupation, "career", ""))
            if specialist_domain_for_career(career):
                continue
            if any(token in career for token in INVESTIGATOR_CAREER_TOKENS):
                return int(eid)
        return None

    def _select_specialist_responder(self, domain, target):
        occupations = self.sim.ecs.get(Occupation)
        ais = self.sim.ecs.get(AI)
        for _score, eid in self._rank_candidates(target, peace_only=True):
            ai = ais.get(eid)
            occupation = occupations.get(eid)
            career = _key(getattr(occupation, "career", ""))
            if specialist_domain_for_career(career) != _key(domain):
                continue
            if _key(getattr(ai, "state", "")) == "investigating" or _text(getattr(ai, "response_role", "")):
                continue
            return int(eid)
        return None

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
            is_peace = role in PEACE_ROLES or any(token in career for token in PEACE_CAREER_TOKENS)
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
            response_radius = DEFAULT_PEACE_DISPATCH_RADIUS if peace_only else DEFAULT_VIGIL_RADIUS
            if distance > response_radius:
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
            investigator_bonus = 0.07 if peace_only and any(token in career for token in INVESTIGATOR_CAREER_TOKENS) else 0.0
            score = civic_pull + investigator_bonus + jitter - (distance / float(response_radius + 1)) * 0.35
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
        reported_target = tuple(target)
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
        # A responder receives the reporter's account, not the canonical
        # offender eid retained by the incident simulation.  Their first job is
        # therefore a bounded search around the reported place.
        specialist_domain = SPECIALIST_RESPONSE_ROLES.get(str(response_role), "")
        if str(response_role) == "peace_dispatched" or specialist_domain:
            case = justice_case_for_incident(self.sim, incident_id)
            account = case.get("best_subject_account") if isinstance(case, dict) and isinstance(case.get("best_subject_account"), dict) else {}
            description = account.get("description") if isinstance(account.get("description"), dict) else {}
            if str((case or {}).get("status", "") or "").strip().lower() == "unresolved" and (description or specialist_domain):
                occupation = self.sim.ecs.get(Occupation).get(eid)
                career = _key(getattr(occupation, "career", ""))
                is_investigator = bool(specialist_domain) or any(token in career for token in INVESTIGATOR_CAREER_TOKENS)
                reports = tuple(case.get("reports", ()) or ())
                latest_report = reports[-1] if reports and isinstance(reports[-1], dict) else {}
                carried_account = (
                    transmitted_subject_account(
                        account,
                        channel="dispatch_handoff",
                        source_eid=latest_report.get("reporter_eid", case.get("reporter_eid")),
                        confidence=0.96,
                        propagation_depth=1,
                        preserve_reporter_account=False,
                    )
                    if account
                    else {}
                )
                canvas_limit = 5
                if specialist_domain == WILDLIFE_DOMAIN:
                    canvas_limit = 4
                elif specialist_domain == FIRE_DOMAIN:
                    canvas_limit = 6
                ai.investigation_context = begin_purposeful_report_search(
                    self.sim,
                    eid,
                    reported_target,
                    subject_account=carried_account,
                    incident_id=incident_id,
                    reporter_eid=latest_report.get("reporter_eid"),
                    knowledge_channel=f"{specialist_domain}_handoff" if specialist_domain else "dispatch_handoff",
                    approach_position=target,
                    report_conflict_count=(case or {}).get("report_conflict_count", 0),
                    canvas_enabled=is_investigator,
                    canvas_limit=canvas_limit if is_investigator else 0,
                    casework_kind=specialist_casework_kind(specialist_domain) if specialist_domain else "investigator_canvas" if is_investigator else "guard_scene_search",
                )
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
