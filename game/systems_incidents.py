"""Incident registry and actor knowledge adapters.

This module creates canonical incident records from existing gameplay events
and tracks which actors know about them, without requiring a full rewrite of
the current memory or justice systems.
"""

from __future__ import annotations

from engine.events import Event
from engine.systems import System

from game.components import AI, IncidentKnowledge, JusticeProfile, NPCTraits, Occupation, Position
from game.incident_runtime import (
    create_or_merge_incident,
    incident_propagation_allowed,
    incident_record,
    incident_registry,
    prune_incidents,
    update_incident_propagation,
)
from game.organizations import property_org_members
from game.system_support.awareness_runtime import _watchers_for_position
from game.system_support.offense_runtime import OFFICIAL_REPORTABLE_OFFENSE_CONTEXTS, WILDLIFE_OFFENSE_CONTEXTS


CAMERA_OWNER_AI_ROLES = {"guard", "scout", "officer", "police", "deputy", "marshal", "security"}
CAMERA_OWNER_CAREER_TOKENS = ("guard", "security", "patrol", "police", "deputy", "marshal", "surveillance", "monitor", "dispatch")


def _clamp_unit(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    return float(max(0.0, min(1.0, number)))


class IncidentKnowledgeSystem(System):

    MIN_ACTION_OFFENSE_SCORE = 8
    MIN_SOCIAL_QUEUE_SCORE = 0.24
    MIN_URGENT_QUEUE_SCORE = 0.55

    def __init__(self, sim):
        super().__init__(sim)
        self.sim.events.subscribe("action_offense", self.on_action_offense)
        self.sim.events.subscribe("property_trespass", self.on_property_trespass)
        self.sim.events.subscribe("property_tamper", self.on_property_tamper)
        self.sim.events.subscribe("item_stolen", self.on_item_stolen)
        self.sim.events.subscribe("camera_scrutiny", self.on_camera_scrutiny)
        self.sim.events.subscribe("camera_alerted", self.on_camera_alerted)
        self.sim.events.subscribe("rumor_shared", self.on_rumor_shared)
        if not hasattr(self.sim, "incident_stats"):
            self.sim.incident_stats = {
                "active": 0,
                "removed_last_tick": 0,
            }

    def _knowledge_for(self, eid, *, create=False):
        if eid is None:
            return None
        try:
            actor_eid = int(eid)
        except (TypeError, ValueError):
            return None
        knowledge = self.sim.ecs.get(IncidentKnowledge).get(actor_eid)
        if knowledge is None and create:
            self.sim.ecs.add(actor_eid, IncidentKnowledge())
            knowledge = self.sim.ecs.get(IncidentKnowledge).get(actor_eid)
        return knowledge

    def _observer_role(self, eid):
        ai = self.sim.ecs.get(AI).get(eid)
        return str(getattr(ai, "role", "") or "").strip().lower()

    def _observer_property_stake(self, eid, incident):
        if eid is None or not isinstance(incident, dict):
            return False
        property_id = str(incident.get("property_id", "") or "").strip()
        if not property_id:
            return False
        prop = self.sim.properties.get(property_id)
        if isinstance(prop, dict) and prop.get("owner_eid") == eid:
            return True
        occupation = self.sim.ecs.get(Occupation).get(eid)
        workplace = getattr(occupation, "workplace", None)
        if isinstance(workplace, dict) and str(workplace.get("property_id", "") or "").strip() == property_id:
            return True
        return False

    def _observer_urgency(self, eid, incident, *, source_kind="", firsthand=False):
        severity = max(0.0, min(1.0, float(int(incident.get("severity", 0) or 0)) / 100.0))
        justice = self.sim.ecs.get(JusticeProfile).get(eid)
        role = self._observer_role(eid)
        official = bool(
            role in {"guard", "scout", "officer", "police", "deputy", "marshal"}
            or (justice and (justice.enforce_all or float(justice.justice) >= 0.78))
        )
        stake = self._observer_property_stake(eid, incident)
        source_mult = 1.0 if firsthand else 0.82 if str(source_kind or "").strip().lower() == "camera" else 0.72
        urgency = (severity * 0.52) + (0.24 if incident.get("official_reportable") else 0.0)
        if official:
            urgency += 0.28
        if stake:
            urgency += 0.2
        if justice:
            urgency += float(getattr(justice, "crime_sensitivity", 0.5) or 0.5) * 0.1
        return _clamp_unit(urgency * source_mult, default=0.0)

    def _observer_social_interest(self, eid, incident, *, source_kind="", firsthand=False):
        severity = max(0.0, min(1.0, float(int(incident.get("severity", 0) or 0)) / 100.0))
        traits = self.sim.ecs.get(NPCTraits).get(eid) or NPCTraits()
        role = self._observer_role(eid)
        stake = self._observer_property_stake(eid, incident)
        interest = (severity * 0.22) + (float(getattr(traits, "empathy", 0.5) or 0.5) * 0.16)
        if stake:
            interest += 0.3
        if firsthand:
            interest += 0.12
        if role in {"resident", "civilian", "worker", "clerk", "cashier", "merchant", "shopkeeper", "manager"}:
            interest += 0.12
        if role in {"guard", "scout", "officer", "police", "deputy", "marshal"}:
            interest *= 0.55
        if str(source_kind or "").strip().lower() == "camera":
            interest *= 0.45
        return _clamp_unit(interest, default=0.0)

    def _learn_incident(
        self,
        eid,
        incident_id,
        *,
        source_kind="",
        source_eid=None,
        firsthand=False,
        confidence=1.0,
        propagation_depth=0,
        queue=True,
    ):
        incident = incident_record(self.sim, incident_id)
        if not isinstance(incident, dict):
            return None
        if not incident_propagation_allowed(incident, propagation_depth):
            return None

        knowledge = self._knowledge_for(eid, create=True)
        urgency = self._observer_urgency(
            eid,
            incident,
            source_kind=source_kind,
            firsthand=firsthand,
        )
        social_interest = self._observer_social_interest(
            eid,
            incident,
            source_kind=source_kind,
            firsthand=firsthand,
        )
        record = knowledge.remember(
            incident_id,
            learned_tick=getattr(self.sim, "tick", 0),
            source_kind=source_kind,
            source_eid=source_eid,
            confidence=confidence,
            firsthand=firsthand,
            propagation_depth=propagation_depth,
            urgency=urgency,
            social_interest=social_interest,
            category="official" if incident.get("official_reportable") else "social",
            severity=int(incident.get("severity", 0) or 0),
            x=incident.get("x"),
            y=incident.get("y"),
            z=incident.get("z"),
        )
        update_incident_propagation(incident, propagation_depth)

        if queue and str(source_kind or "").strip().lower() != "self":
            if urgency >= self.MIN_URGENT_QUEUE_SCORE:
                knowledge.queue_incident(
                    incident_id,
                    queue="urgent",
                    score=urgency,
                    tick=getattr(self.sim, "tick", 0),
                )
            elif social_interest >= self.MIN_SOCIAL_QUEUE_SCORE:
                knowledge.queue_incident(
                    incident_id,
                    queue="social",
                    score=social_interest,
                    tick=getattr(self.sim, "tick", 0),
                )

        self.sim.emit(Event(
            "knowledge_incident_learned",
            eid=eid,
            incident_id=incident_id,
            source_kind=str(source_kind or "").strip().lower(),
            source_eid=source_eid,
            firsthand=bool(firsthand),
            confidence=round(float(record.get("confidence", confidence) or confidence), 3) if isinstance(record, dict) else round(float(confidence), 3),
            propagation_depth=int(propagation_depth),
            urgency=round(float(urgency), 3),
            social_interest=round(float(social_interest), 3),
        ))
        return record

    def _incident_watchers(self, *, x=None, y=None, z=0, exclude_eid=None):
        if x is None or y is None:
            return ()
        return tuple(
            int(observer_eid)
            for observer_eid in _watchers_for_position(
                self.sim,
                x,
                y,
                z,
                exclude_eid=exclude_eid,
                offender_eid=exclude_eid,
            )
        )

    def _camera_property(self, event):
        property_id = str(event.data.get("property_id", "") or "").strip()
        if not property_id:
            return None
        prop = self.sim.properties.get(property_id)
        return prop if isinstance(prop, dict) else None

    def _camera_owner_recipients(self, prop, *, exclude_eid=None):
        if not isinstance(prop, dict):
            return ()
        recipients = []
        seen = set()

        def _add(raw_eid):
            try:
                eid = int(raw_eid)
            except (TypeError, ValueError):
                return
            if eid == exclude_eid or eid in seen:
                return
            if self.sim.ecs.get(AI).get(eid) is None:
                return
            seen.add(eid)
            recipients.append(eid)

        _add(prop.get("owner_eid"))
        for member in property_org_members(self.sim, prop):
            eid = member.get("eid")
            role = str(member.get("role", "") or "").strip().lower()
            occupation = member.get("occupation")
            career = str(getattr(occupation, "career", "") or "").strip().lower()
            ai_role = self._observer_role(eid)
            if (
                role in {"owner", "manager"}
                or ai_role in CAMERA_OWNER_AI_ROLES
                or any(token in career for token in CAMERA_OWNER_CAREER_TOKENS)
            ):
                _add(eid)
        return tuple(recipients)

    def _prime_camera_event_position(self, event):
        offender_eid = event.data.get("eid")
        pos = self.sim.ecs.get(Position).get(offender_eid)
        if pos is None:
            return
        event.data.setdefault("x", pos.x)
        event.data.setdefault("y", pos.y)
        event.data.setdefault("z", pos.z)

    def _camera_incident(self, event, prop, *, severity, official_reportable=False, note="", tags=()):
        if isinstance(prop, dict) and prop.get("owner_eid") is not None:
            event.data.setdefault("owner_eid", prop.get("owner_eid"))
        self._prime_camera_event_position(event)
        return self._create_incident(
            event,
            kind="camera_alert",
            severity=severity,
            merge_subject=str(event.data.get("property_id", event.data.get("camera_property_id", "")) or "").strip(),
            official_reportable=official_reportable,
            note=note,
            tags=tags,
        )

    def _learn_camera_recipients(self, incident, prop, *, exclude_eid=None, confidence=0.65, queue=False):
        if not isinstance(incident, dict) or not isinstance(prop, dict):
            return
        incident_id = int(incident.get("id", 0) or 0)
        for observer_eid in self._camera_owner_recipients(prop, exclude_eid=exclude_eid):
            self._learn_incident(
                observer_eid,
                incident_id,
                source_kind="camera",
                source_eid=None,
                firsthand=True,
                confidence=confidence,
                propagation_depth=0,
                queue=queue,
            )

    def _create_incident(self, event, *, kind, severity, merge_subject="", official_reportable=False, note="", tags=()):
        incident, merged = create_or_merge_incident(
            self.sim,
            kind=kind,
            x=event.data.get("x"),
            y=event.data.get("y"),
            z=event.data.get("z", 0),
            tick=getattr(self.sim, "tick", 0),
            severity=severity,
            primary_actor_eid=event.data.get("offender_eid", event.data.get("eid")),
            victim_eid=event.data.get("victim_eid"),
            victim_name=event.data.get("victim_name", event.data.get("target_name")),
            owner_eid=event.data.get("owner_eid"),
            property_id=event.data.get("property_id"),
            property_name=event.data.get("property_name"),
            merge_subject=merge_subject,
            source_event=event.type,
            official_reportable=official_reportable,
            note=note,
            tags=tags,
        )
        event.data["knowledge_incident_id"] = incident["id"]
        self.sim.emit(Event(
            "knowledge_incident_created",
            incident_id=incident["id"],
            kind=str(incident.get("kind", kind) or kind),
            merged=bool(merged),
            severity=int(incident.get("severity", severity) or severity),
            property_id=incident.get("property_id"),
            primary_actor_eid=incident.get("primary_actor_eid"),
            official_reportable=bool(incident.get("official_reportable", official_reportable)),
        ))
        return incident

    def _learn_self_and_witnesses(self, incident, event, *, source_kind="witnessed", witnesses=()):
        incident_id = int(incident.get("id", 0) or 0)
        offender_eid = event.data.get("offender_eid", event.data.get("eid"))
        if offender_eid is not None:
            self._learn_incident(
                offender_eid,
                incident_id,
                source_kind="self",
                source_eid=offender_eid,
                firsthand=True,
                confidence=1.0,
                propagation_depth=0,
                queue=False,
            )
        for observer_eid in tuple(witnesses or ()):
            if observer_eid == offender_eid:
                continue
            self._learn_incident(
                observer_eid,
                incident_id,
                source_kind=source_kind,
                source_eid=offender_eid,
                firsthand=True,
                confidence=1.0,
                propagation_depth=0,
            )

    def on_action_offense(self, event):
        offense_score = int(event.data.get("offense_score", 0) or 0)
        context = str(event.data.get("context", "ordinary") or "").strip().lower() or "ordinary"
        action = str(event.data.get("action", "action") or "").strip().lower() or "action"
        if offense_score <= 0:
            return
        if context == "ordinary" and offense_score < self.MIN_ACTION_OFFENSE_SCORE:
            return

        official_reportable = (
            context in OFFICIAL_REPORTABLE_OFFENSE_CONTEXTS
            or (context not in WILDLIFE_OFFENSE_CONTEXTS and offense_score >= 24)
        )
        incident = self._create_incident(
            event,
            kind="action_offense",
            severity=offense_score,
            merge_subject=f"{action}:{context}",
            official_reportable=official_reportable,
            note=f"{action}/{context}",
            tags=(context, action, event.data.get("offense_tier")),
        )
        witnesses = self._incident_watchers(
            x=event.data.get("x"),
            y=event.data.get("y"),
            z=event.data.get("z", 0),
            exclude_eid=event.data.get("offender_eid"),
        )
        self._learn_self_and_witnesses(incident, event, source_kind="witnessed", witnesses=witnesses)

    def on_property_trespass(self, event):
        severity = int(event.data.get("severity_score", 0) or 0)
        if severity <= 0:
            return
        incident = self._create_incident(
            event,
            kind="property_trespass",
            severity=severity,
            merge_subject=str(event.data.get("property_id", "") or "").strip(),
            official_reportable=bool(event.data.get("witnessed", False)),
            note=str(event.data.get("severity_label", "trespass") or "").strip().lower(),
            tags=(
                event.data.get("severity_label"),
                event.data.get("access_level"),
                event.data.get("ingress_kind"),
                event.data.get("ingress_method"),
            ),
        )
        witnesses = tuple(int(eid) for eid in event.data.get("witnesses", ()) if eid is not None)
        if not witnesses and bool(event.data.get("witnessed", False)):
            witnesses = self._incident_watchers(
                x=event.data.get("x"),
                y=event.data.get("y"),
                z=event.data.get("z", 0),
                exclude_eid=event.data.get("offender_eid"),
            )
        self._learn_self_and_witnesses(incident, event, source_kind="witnessed", witnesses=witnesses)

    def on_property_tamper(self, event):
        severity = int(event.data.get("severity_score", 0) or 0)
        if severity <= 0:
            return
        incident = self._create_incident(
            event,
            kind="property_tamper",
            severity=severity,
            merge_subject=str(event.data.get("property_id", "") or "").strip(),
            official_reportable=bool(event.data.get("witnessed", False)),
            note="property_tamper",
            tags=(
                event.data.get("severity_label"),
                event.data.get("ingress_kind"),
                event.data.get("ingress_method"),
            ),
        )
        witnesses = tuple(int(eid) for eid in event.data.get("witnesses", ()) if eid is not None)
        if not witnesses and bool(event.data.get("witnessed", False)):
            witnesses = self._incident_watchers(
                x=event.data.get("x"),
                y=event.data.get("y"),
                z=event.data.get("z", 0),
                exclude_eid=event.data.get("offender_eid"),
            )
        self._learn_self_and_witnesses(incident, event, source_kind="witnessed", witnesses=witnesses)

    def on_item_stolen(self, event):
        item_name = str(event.data.get("item_name", event.data.get("item_id", "item")) or "").strip() or "item"
        incident = self._create_incident(
            event,
            kind="item_stolen",
            severity=72,
            merge_subject=str(event.data.get("property_id", event.data.get("item_id", "")) or "").strip(),
            official_reportable=True,
            note=item_name,
            tags=("theft", event.data.get("item_id")),
        )
        witnesses = tuple(int(eid) for eid in event.data.get("witnesses", ()) if eid is not None)
        if not witnesses:
            witnesses = self._incident_watchers(
                x=event.data.get("x"),
                y=event.data.get("y"),
                z=event.data.get("z", 0),
                exclude_eid=event.data.get("offender_eid"),
            )
        self._learn_self_and_witnesses(incident, event, source_kind="witnessed", witnesses=witnesses)

    def on_camera_scrutiny(self, event):
        offender_eid = event.data.get("eid")
        confidence = _clamp_unit(event.data.get("confidence"), default=0.0)
        prop = self._camera_property(event)
        if offender_eid is None or confidence <= 0.0 or not isinstance(prop, dict):
            return
        severity = max(6, min(18, int(round(confidence * 18.0))))
        incident = self._camera_incident(
            event,
            prop,
            severity=severity,
            official_reportable=False,
            note="camera_scrutiny",
            tags=("camera", "scrutiny", event.data.get("disguise_role")),
        )
        self._learn_camera_recipients(
            incident,
            prop,
            exclude_eid=offender_eid,
            confidence=max(0.35, confidence),
            queue=False,
        )

    def on_camera_alerted(self, event):
        severity = int(event.data.get("severity_score", 0) or 0)
        if severity <= 0:
            return
        prop = self._camera_property(event)
        incident = self._camera_incident(
            event,
            prop,
            severity=severity,
            official_reportable=True,
            note=str(event.data.get("severity_label", "camera_alert") or "").strip().lower(),
            tags=("camera", event.data.get("severity_label"), event.data.get("access_level")),
        )
        offender_eid = event.data.get("eid")
        if offender_eid is not None:
            self._learn_incident(
                offender_eid,
                int(incident.get("id", 0) or 0),
                source_kind="self",
                source_eid=offender_eid,
                firsthand=True,
                confidence=1.0,
                propagation_depth=0,
                queue=False,
            )
        self._learn_camera_recipients(
            incident,
            prop,
            exclude_eid=offender_eid,
            confidence=0.96,
            queue=True,
        )

    def on_rumor_shared(self, event):
        incident_id = event.data.get("incident_id")
        from_eid = event.data.get("from_eid")
        to_eid = event.data.get("to_eid")
        if incident_id is None or from_eid is None or to_eid is None:
            return
        incident = incident_record(self.sim, incident_id)
        if not isinstance(incident, dict):
            return

        source_knowledge = self._knowledge_for(from_eid, create=False)
        source_record = None
        if source_knowledge is not None:
            source_record = source_knowledge.records.get(int(incident_id))
        source_depth = int((source_record or {}).get("propagation_depth", 0) or 0)
        propagation_depth = source_depth + 1
        if not incident_propagation_allowed(incident, propagation_depth):
            return

        confidence = _clamp_unit(float(event.data.get("strength", 0.0) or 0.0) * 0.92, default=0.22)
        self._learn_incident(
            to_eid,
            int(incident_id),
            source_kind="social_rumor",
            source_eid=from_eid,
            firsthand=False,
            confidence=confidence,
            propagation_depth=propagation_depth,
        )
        target_knowledge = self._knowledge_for(to_eid, create=False)
        if target_knowledge is not None:
            target_knowledge.mark_shared(incident_id, tick=getattr(self.sim, "tick", 0), channel="social")

    def update(self):
        removed = prune_incidents(self.sim, tick=getattr(self.sim, "tick", 0))
        if removed:
            knowledge_map = self.sim.ecs.get(IncidentKnowledge)
            for _eid, knowledge in knowledge_map.items():
                for incident_id in removed:
                    knowledge.forget(incident_id)
        self.sim.incident_stats["active"] = len(incident_registry(self.sim))
        self.sim.incident_stats["removed_last_tick"] = len(removed)
