"""Observed incident social/response processing for BAKERRRR.

This module sits on top of the existing IncidentKnowledgeSystem seam.
It does not create canonical incidents; it consumes actor-held incident
knowledge and turns it into two distinct consequences:

- social rumor spread through aligned nearby bonds
- urgent response cues for report/help/look-away behavior

Core invariants:
- incidents are canonical records
- IncidentKnowledge records are actor-held accounts
- gossip spreads accounts and may drift after the soft propagation limit
- urgent/report cues route behavior; they do not casually gossip-spread
"""

from __future__ import annotations

import hashlib
import hmac
from copy import deepcopy

from engine.events import Event
from engine.systems import System

from game.components import (
    AI,
    IncidentKnowledge,
    JusticeProfile,
    NPCSocial,
    NPCTraits,
    NPCWill,
    Occupation,
    Position,
)
from game.incident_runtime import incident_propagation_allowed, incident_record


PEACE_ROLES = {"guard", "scout", "officer", "police", "deputy", "marshal", "security"}
CIVIC_ROLES = {"clerk", "cashier", "merchant", "shopkeeper", "manager", "worker", "resident", "civilian"}
VIOLENCE_TAGS = {"violence", "assault", "armed_assault", "weapon", "gunfire", "fire_weapon", "melee", "murder"}
DISASTER_TAGS = {"fire", "explosion", "collapse", "toxic", "hazard", "disaster", "gas", "flood"}
TRESPASS_TAGS = {"trespass", "forced_entry", "break_in", "break-in", "unauthorized"}


# Global first, as discussed. Later these can move into world_traits or content JSON.
RUMOR_SOFT_PROPAGATION_LIMIT = 2
RUMOR_HARD_PROPAGATION_LIMIT = 4
SOCIAL_SHARE_COOLDOWN_TICKS = 90
URGENT_RESPONSE_COOLDOWN_TICKS = 80
SOCIAL_SHARE_RANGE = 6


def _clamp(value, lo=0.0, hi=1.0, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    return max(float(lo), min(float(hi), number))


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _text(value):
    return str(value or "").strip()


def _key(value):
    return _text(value).strip().lower()


def _tags(record):
    if not isinstance(record, dict):
        return set()
    values = set()
    for field in ("tags", "source_events"):
        for tag in record.get(field, ()) or ():
            tag_key = _key(tag)
            if tag_key:
                values.add(tag_key)
    for field in ("kind", "note", "merge_subject"):
        tag_key = _key(record.get(field))
        if tag_key:
            values.add(tag_key)
    return values


def _manhattan(a, b):
    return abs(int(a.x) - int(b.x)) + abs(int(a.y) - int(b.y))


def _unit_roll(seed, *parts):
    """Stable deterministic [0,1) roll for seeded social drift."""
    key = str(seed).encode("utf-8")
    msg = "|".join(str(part) for part in parts).encode("utf-8")
    digest = hmac.new(key, msg, hashlib.sha256).hexdigest()
    return int(digest[:13], 16) / float(0x10000000000000)


def _choice(seed, choices, *parts):
    if not choices:
        return None
    roll = _unit_roll(seed, *parts)
    idx = min(len(choices) - 1, int(roll * len(choices)))
    return choices[idx]


def _bond_score(bond):
    if not isinstance(bond, dict):
        return 0.0
    return _clamp(bond.get("trust"), default=0.0) * 0.58 + _clamp(bond.get("closeness"), default=0.0) * 0.42


def _bond_protectiveness(bond):
    if not isinstance(bond, dict):
        return 0.0
    return _clamp(bond.get("protectiveness"), default=0.0)


class ObservedIncidentConsequenceSystem(System):
    """Turns held incident knowledge into gossip and urgent response cues.

    Put this after IncidentKnowledgeSystem in system construction so that
    `rumor_shared` events immediately create recipient IncidentKnowledge.
    The module is intentionally conservative: it emits response cues instead
    of trying to hard-code pathing to phones/alarms inside this layer.
    """

    def __init__(self, sim):
        super().__init__(sim)
        self._last_social_attempt = {}
        self._last_urgent_attempt = {}
        if not hasattr(sim, "observed_incident_stats"):
            sim.observed_incident_stats = {
                "rumors_shared": 0,
                "rumors_corrupted": 0,
                "urgent_cues": 0,
                "looked_away": 0,
            }

    # ------------------------------------------------------------------
    # Public update pass
    # ------------------------------------------------------------------

    def update(self):
        self._process_urgent_queues()
        self._process_social_queues()

    # ------------------------------------------------------------------
    # Social gossip
    # ------------------------------------------------------------------

    def _process_social_queues(self):
        knowledge_map = self.sim.ecs.get(IncidentKnowledge)
        positions = self.sim.ecs.get(Position)
        socials = self.sim.ecs.get(NPCSocial)

        for from_eid, knowledge in tuple(knowledge_map.items()):
            pos = positions.get(from_eid)
            social = socials.get(from_eid)
            if not pos or not social:
                continue
            if not knowledge.social_queue:
                continue

            # Cheap staggering so big settlements do not all gossip on the same tick.
            if (getattr(self.sim, "tick", 0) + int(from_eid)) % 4 != 0:
                continue

            for entry in tuple(knowledge.social_queue):
                incident_id = _int(entry.get("incident_id"), -1)
                record = knowledge.records.get(incident_id)
                incident = incident_record(self.sim, incident_id)
                if not isinstance(record, dict) or not isinstance(incident, dict):
                    self._remove_queue_item(knowledge, "social", incident_id)
                    continue

                listener_eid = self._pick_social_listener(from_eid, incident_id, record, social, pos)
                if listener_eid is None:
                    continue

                if self._share_rumor(from_eid, listener_eid, incident_id, record, incident):
                    self._remove_queue_item(knowledge, "social", incident_id)
                break

    def _pick_social_listener(self, from_eid, incident_id, source_record, social, source_pos):
        positions = self.sim.ecs.get(Position)
        knowledge_map = self.sim.ecs.get(IncidentKnowledge)
        now = getattr(self.sim, "tick", 0)

        ranked = []
        for to_eid, bond in getattr(social, "bonds", {}).items():
            to_pos = positions.get(to_eid)
            if not to_pos or to_pos.z != source_pos.z:
                continue
            if _manhattan(source_pos, to_pos) > SOCIAL_SHARE_RANGE:
                continue
            if to_eid == from_eid:
                continue

            bond_score = _bond_score(bond)
            if bond_score < 0.48:
                continue

            target_knowledge = knowledge_map.get(to_eid)
            if target_knowledge and incident_id in target_knowledge.records:
                continue

            cooldown_key = (from_eid, to_eid, incident_id, "social")
            if now - self._last_social_attempt.get(cooldown_key, -10_000) < SOCIAL_SHARE_COOLDOWN_TICKS:
                continue

            # Prefer close trusted friends, but add deterministic tie-breaking.
            jitter = _unit_roll(getattr(self.sim, "seed", ""), "social_listener", from_eid, to_eid, incident_id) * 0.08
            ranked.append((bond_score + jitter, to_eid))

        if not ranked:
            return None
        ranked.sort(reverse=True)
        return ranked[0][1]

    def _share_rumor(self, from_eid, to_eid, incident_id, source_record, incident):
        source_depth = _int(source_record.get("propagation_depth"), 0)
        next_depth = source_depth + 1
        if next_depth > RUMOR_HARD_PROPAGATION_LIMIT:
            return False
        if not incident_propagation_allowed(incident, next_depth):
            return False

        now = getattr(self.sim, "tick", 0)
        cooldown_key = (from_eid, to_eid, incident_id, "social")
        if now - self._last_social_attempt.get(cooldown_key, -10_000) < SOCIAL_SHARE_COOLDOWN_TICKS:
            return False
        self._last_social_attempt[cooldown_key] = now

        confidence = _clamp(source_record.get("confidence"), default=0.45) * 0.88
        account = self._rumor_account_for_transfer(from_eid, to_eid, incident_id, source_record, incident, next_depth)

        self.sim.emit(Event(
            "rumor_shared",
            incident_id=incident_id,
            from_eid=from_eid,
            to_eid=to_eid,
            offender_eid=incident.get("primary_actor_eid"),
            victim_eid=incident.get("victim_eid"),
            strength=round(confidence, 3),
            propagation_depth=next_depth,
            corruption_kind=account.get("corruption_kind", ""),
            rumor_note=account.get("account_note", ""),
            rumor_tags=tuple(account.get("account_tags", ())),
        ))

        # The existing IncidentKnowledgeSystem learns the incident synchronously
        # from rumor_shared. Mutate only the recipient's actor-held account.
        target_knowledge = self.sim.ecs.get(IncidentKnowledge).get(to_eid)
        if target_knowledge is not None:
            target_record = target_knowledge.records.get(int(incident_id))
            if isinstance(target_record, dict):
                target_record["account_note"] = account.get("account_note", "")
                target_record["account_tags"] = tuple(account.get("account_tags", ()))
                target_record["corruption_kind"] = account.get("corruption_kind", "")
                target_record["spreadable"] = bool(next_depth < RUMOR_HARD_PROPAGATION_LIMIT)
                target_knowledge.mark_shared(incident_id, tick=now, channel="social")

        self.sim.observed_incident_stats["rumors_shared"] += 1
        if account.get("corruption_kind"):
            self.sim.observed_incident_stats["rumors_corrupted"] += 1
        return True

    def _rumor_account_for_transfer(self, from_eid, to_eid, incident_id, source_record, incident, next_depth):
        note = _text(source_record.get("account_note")) or _text(incident.get("note")) or _text(incident.get("kind"))
        account_tags = set(source_record.get("account_tags", ()) or ()) | _tags(incident)
        corruption_kind = ""

        # Corruption begins after the soft limit. Common case is no drift.
        if next_depth > RUMOR_SOFT_PROPAGATION_LIMIT:
            over = next_depth - RUMOR_SOFT_PROPAGATION_LIMIT
            chance = min(0.45, 0.14 * over)
            roll = _unit_roll(
                getattr(self.sim, "seed", ""),
                "rumor_corruption",
                incident_id,
                from_eid,
                to_eid,
                next_depth,
                note,
            )
            if roll < chance:
                corruption_kind = self._pick_corruption_kind(incident_id, from_eid, to_eid, next_depth)
                note, account_tags = self._apply_rumor_corruption(note, account_tags, corruption_kind)

        return {
            "account_note": note,
            "account_tags": tuple(sorted(tag for tag in account_tags if tag)),
            "corruption_kind": corruption_kind,
        }

    def _pick_corruption_kind(self, incident_id, from_eid, to_eid, depth):
        # Detail loss dominates. Severity drift is rare on purpose.
        weighted = (
            ["detail_loss"] * 8
            + ["confidence_decay"] * 4
            + ["time_blur"] * 3
            + ["target_blur"] * 2
            + ["severity_drift"] * 1
            + ["actor_blur"] * 1
        )
        return _choice(getattr(self.sim, "seed", ""), weighted, "corruption_kind", incident_id, from_eid, to_eid, depth)

    def _apply_rumor_corruption(self, note, tags, kind):
        tags = set(tags or ())
        note = _text(note)
        if kind == "detail_loss":
            tags.add("detail_loss")
            if "/" in note:
                note = note.split("/", 1)[0]
            elif note:
                note = f"something about {note}"
            else:
                note = "something happened"
        elif kind == "confidence_decay":
            tags.add("uncertain")
            note = f"heard about {note}" if note else "heard something happened"
        elif kind == "time_blur":
            tags.add("time_blur")
            note = f"recent {note}" if note else "something recent"
        elif kind == "target_blur":
            tags.add("target_blur")
            note = f"something near {note}" if note else "something nearby"
        elif kind == "severity_drift":
            tags.add("severity_drift")
            if "trespass" in tags:
                tags.add("break-in-ish")
                note = "possible break-in"
            else:
                note = f"serious {note}" if note else "serious incident"
        elif kind == "actor_blur":
            tags.add("actor_blur")
            note = f"someone did {note}" if note else "someone did something"
        return note, tags

    # ------------------------------------------------------------------
    # Urgent cue triage
    # ------------------------------------------------------------------

    def _process_urgent_queues(self):
        knowledge_map = self.sim.ecs.get(IncidentKnowledge)
        for eid, knowledge in tuple(knowledge_map.items()):
            if not knowledge.urgent_queue:
                continue
            if (getattr(self.sim, "tick", 0) + int(eid)) % 3 != 0:
                continue
            for entry in tuple(knowledge.urgent_queue):
                incident_id = _int(entry.get("incident_id"), -1)
                record = knowledge.records.get(incident_id)
                incident = incident_record(self.sim, incident_id)
                if not isinstance(record, dict) or not isinstance(incident, dict):
                    self._remove_queue_item(knowledge, "urgent", incident_id)
                    continue
                if self._handle_urgent_incident(eid, incident_id, record, incident):
                    self._remove_queue_item(knowledge, "urgent", incident_id)
                break

    def _handle_urgent_incident(self, eid, incident_id, source_record, incident):
        now = getattr(self.sim, "tick", 0)
        key = (eid, incident_id, "urgent")
        if now - self._last_urgent_attempt.get(key, -10_000) < URGENT_RESPONSE_COOLDOWN_TICKS:
            return False
        self._last_urgent_attempt[key] = now

        if not self._is_urgent_report_class(incident, source_record):
            return True

        decision = self._choose_urgent_response(eid, incident, source_record)
        cue_kind = decision["kind"]
        if cue_kind == "look_away":
            source_record["dismissed"] = True
            source_record["looked_away"] = True
            self.sim.observed_incident_stats["looked_away"] += 1
            self.sim.emit(Event(
                "incident_looked_away",
                npc_eid=eid,
                incident_id=incident_id,
                reason=decision.get("reason", ""),
                score=round(float(decision.get("score", 0.0)), 3),
            ))
            return True

        target = self._cue_target_position(incident)
        self.sim.emit(Event(
            "observed_response_cue",
            npc_eid=eid,
            incident_id=incident_id,
            cue_kind=cue_kind,
            target=target,
            target_eid=decision.get("target_eid"),
            urgency=round(float(decision.get("score", 0.0)), 3),
            reason=decision.get("reason", ""),
            preferred_methods=tuple(decision.get("preferred_methods", ())),
        ))
        self._soft_apply_response_intent(eid, cue_kind, target, decision.get("target_eid"), decision.get("score", 0.0))
        knowledge = self.sim.ecs.get(IncidentKnowledge).get(eid)
        if knowledge is not None:
            knowledge.mark_shared(incident_id, tick=now, channel=cue_kind)
        self.sim.observed_incident_stats["urgent_cues"] += 1
        return True

    def _is_urgent_report_class(self, incident, source_record):
        tags = _tags(incident) | set(source_record.get("account_tags", ()) or ())
        kind = _key(incident.get("kind"))
        severity = _int(incident.get("severity"), 0)
        if tags & VIOLENCE_TAGS or severity >= 65:
            return True
        if tags & DISASTER_TAGS:
            return True
        if kind == "property_trespass" or tags & TRESPASS_TAGS:
            # Known/observed trespass only. Rumor alone should usually not call police.
            return bool(source_record.get("firsthand")) and _clamp(source_record.get("confidence"), default=0.0) >= 0.62
        return bool(incident.get("official_reportable")) and bool(source_record.get("firsthand"))

    def _choose_urgent_response(self, eid, incident, source_record):
        scores = self._urgent_scores(eid, incident, source_record)
        ordered = sorted(scores.items(), key=lambda row: row[1], reverse=True)
        best_kind, best_score = ordered[0]

        if best_kind == "help_victim" and best_score >= 0.42:
            return {
                "kind": "help_victim",
                "score": best_score,
                "target_eid": incident.get("victim_eid"),
                "reason": "victim_aligned_or_in_danger",
                "preferred_methods": ("reach_victim", "warn", "first_aid", "intervene"),
            }
        if best_kind == "look_away" and best_score >= 0.46:
            return {
                "kind": "look_away",
                "score": best_score,
                "reason": "aligned_with_offender_or_avoiding_authority",
            }
        if scores.get("report", 0.0) >= 0.38:
            return {
                "kind": "report_authority",
                "score": scores.get("report", 0.0),
                "target_eid": None,
                "reason": "reportable_and_motivated",
                "preferred_methods": ("cell_phone", "alarm", "work_phone", "home_phone", "peace_officer"),
            }
        return {
            "kind": "look_away",
            "score": max(best_score, 0.2),
            "reason": "insufficient_motivation_to_act",
        }

    def _urgent_scores(self, eid, incident, source_record):
        severity = _int(incident.get("severity"), 0) / 100.0
        confidence = _clamp(source_record.get("confidence"), default=0.5)
        traits = self.sim.ecs.get(NPCTraits).get(eid) or NPCTraits()
        justice = self.sim.ecs.get(JusticeProfile).get(eid)
        role = _key(getattr(self.sim.ecs.get(AI).get(eid), "role", ""))

        victim_alignment = self._alignment(eid, incident.get("victim_eid"))
        offender_alignment = self._alignment(eid, incident.get("primary_actor_eid"))
        property_stake = self._property_stake(eid, incident)
        role_duty = 0.65 if role in PEACE_ROLES else 0.35 if property_stake else 0.12 if role in CIVIC_ROLES else 0.0
        justice_duty = 0.0
        anti_authority = 0.0
        if justice:
            justice_duty = _clamp(getattr(justice, "justice", 0.5), default=0.5) * 0.35
            anti_authority = _clamp(getattr(justice, "corruption", 0.0), default=0.0) * 0.35

        bravery = _clamp(getattr(traits, "bravery", 0.5), default=0.5)
        empathy = _clamp(getattr(traits, "empathy", 0.5), default=0.5)
        loyalty = _clamp(getattr(traits, "loyalty", 0.5), default=0.5)
        discipline = _clamp(getattr(traits, "discipline", 0.5), default=0.5)

        immediate_danger = 1.0 if (severity >= 0.6 or (_tags(incident) & VIOLENCE_TAGS)) else 0.25
        report = (
            severity * 0.42
            + confidence * 0.18
            + victim_alignment * 0.28
            + property_stake * 0.32
            + role_duty * 0.5
            + justice_duty
            + discipline * 0.12
            - offender_alignment * 0.25
            - anti_authority
        )
        look_away = (
            offender_alignment * 0.5
            + anti_authority
            + (1.0 - bravery) * 0.22
            + (1.0 - confidence) * 0.22
            - victim_alignment * 0.28
            - role_duty * 0.35
            - severity * 0.18
        )
        help_victim = (
            victim_alignment * 0.55
            + empathy * 0.18
            + loyalty * 0.2
            + bravery * 0.18
            + immediate_danger * 0.36
            - offender_alignment * 0.15
            - (1.0 - confidence) * 0.1
        )
        return {
            "report": _clamp(report),
            "look_away": _clamp(look_away),
            "help_victim": _clamp(help_victim),
        }

    def _alignment(self, eid, other_eid):
        if eid is None or other_eid is None or eid == other_eid:
            return 0.0
        social = self.sim.ecs.get(NPCSocial).get(eid)
        if not social:
            return 0.0
        bond = getattr(social, "bonds", {}).get(other_eid)
        if not isinstance(bond, dict):
            return 0.0
        return _clamp(_bond_score(bond) * 0.65 + _bond_protectiveness(bond) * 0.35)

    def _property_stake(self, eid, incident):
        property_id = _text(incident.get("property_id"))
        if not property_id:
            return 0.0
        prop = getattr(self.sim, "properties", {}).get(property_id)
        if isinstance(prop, dict) and prop.get("owner_eid") == eid:
            return 1.0
        occupation = self.sim.ecs.get(Occupation).get(eid)
        workplace = getattr(occupation, "workplace", None)
        if isinstance(workplace, dict) and _text(workplace.get("property_id")) == property_id:
            return 0.7
        return 0.0

    def _cue_target_position(self, incident):
        x = incident.get("x")
        y = incident.get("y")
        if x is None or y is None:
            return None
        return (_int(x), _int(y), _int(incident.get("z"), 0))

    def _soft_apply_response_intent(self, eid, cue_kind, target, target_eid, score):
        """Bridge until NPCWill consumes observed_response_cue directly.

        This only sets clear high-level states that existing will/movement code
        can preserve or route around. If those states are not yet handled, the
        emitted event remains the authoritative integration seam.
        """
        ai = self.sim.ecs.get(AI).get(eid)
        will = self.sim.ecs.get(NPCWill).get(eid)
        if not ai or not will:
            return
        state = {
            "help_victim": "protecting",
            "report_authority": "reporting_incident",
            "warn_nearby": "warning",
        }.get(cue_kind)
        if not state:
            return
        ai.state = state
        ai.target = target
        ai.target_eid = target_eid
        will.intent = state
        will.score = float(score or 0.0) * 100.0
        will.target = target
        will.target_eid = target_eid
        will.last_tick = getattr(self.sim, "tick", 0)

    def _remove_queue_item(self, knowledge, queue, incident_id):
        target_name = "urgent_queue" if queue == "urgent" else "social_queue"
        current = getattr(knowledge, target_name, [])
        setattr(
            knowledge,
            target_name,
            [entry for entry in current if _int(entry.get("incident_id"), -1) != int(incident_id)],
        )
