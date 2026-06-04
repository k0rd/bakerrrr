"""Incident registry and actor knowledge adapters.

This module creates canonical incident records from existing gameplay events
and tracks which actors know about them, without requiring a full rewrite of
the current memory or justice systems.
"""

from __future__ import annotations

from engine.events import Event
from engine.systems import System

from game.components import AI, IncidentKnowledge, Inventory, JusticeProfile, NPCTraits, Occupation, Position
from game.incident_runtime import (
    create_or_merge_incident,
    incident_linked_item_counts,
    incident_linked_items,
    incident_propagation_allowed,
    incident_record,
    incident_registry,
    prune_incidents,
    record_incident_scene_items,
    update_incident_propagation,
)
from game.organizations import property_org_members
from game.property_runtime import property_covering, property_runtime_container_entries
from game.system_support.awareness_runtime import event_observation_accountability
from game.system_support.item_provenance_runtime import CLAIM_PUBLIC_FREE, CLAIM_SCENE_SALVAGE, classify_item_claim, stamp_item_provenance
from game.system_support.offense_runtime import OFFICIAL_REPORTABLE_OFFENSE_CONTEXTS, WILDLIFE_OFFENSE_CONTEXTS
from game.system_support.social_knowledge_runtime import hydrate_incident_social_knowledge


CAMERA_OWNER_AI_ROLES = {"guard", "scout", "officer", "police", "deputy", "marshal", "security"}
CAMERA_OWNER_CAREER_TOKENS = ("guard", "security", "patrol", "police", "deputy", "marshal", "surveillance", "monitor", "dispatch")
SCENE_RESIDUE_RADIUS = 2
PRECOMBAT_TRANSFER_WINDOW = 12
CONTAINER_CAPTURE_KINDS = {"container", "scene"}


def _clamp_unit(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    return float(max(0.0, min(1.0, number)))


def _text(value):
    return str(value or "").strip()


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _property_building_id(prop):
    metadata = prop.get("metadata") if isinstance((prop or {}).get("metadata"), dict) else {}
    return _text(metadata.get("building_id"))


def _official_item_link_summary(incident, link_kind, *, item_id=""):
    victim_name = _text((incident or {}).get("victim_name"))
    property_name = _text((incident or {}).get("property_name"))
    item_name = _text(item_id).replace("_", " ")
    if link_kind == "victim_inventory":
        if victim_name:
            return f"{victim_name} personal effects"
        return f"{item_name or 'victim'} personal effects"
    if link_kind == "precombat_stolen_from_victim":
        if victim_name:
            return f"{victim_name} property taken during the assault scene"
        return "property taken during the assault scene"
    if link_kind == "scene_claimed":
        if property_name:
            return f"claimed scene property from {property_name}"
        return "claimed scene property"
    if link_kind == "scene_residue":
        if property_name:
            return f"scene residue from {property_name}"
        return "scene residue"
    return property_name or victim_name or item_name or "scene-linked item"


def _official_item_link_rows(incident, *, exact=False):
    rows = []
    for row in incident_linked_items(incident):
        rows.append({
            "instance_id": _text(row.get("instance_id")) or None,
            "item_id": _text(row.get("item_id")).lower() or None,
            "link_kind": _text(row.get("link_kind")).lower() or None,
            "property_id": _text(row.get("property_id")) or None,
            "victim_eid": row.get("source_victim_eid", incident.get("victim_eid")),
            "summary_label": _official_item_link_summary(
                incident,
                _text(row.get("link_kind")).lower(),
                item_id=row.get("item_id"),
            ),
        })
    return tuple(rows)


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
        self.sim.events.subscribe("fire_started", self.on_fire_event)
        self.sim.events.subscribe("fire_spread", self.on_fire_event)
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
            official_item_links=(
                _official_item_link_rows(incident, exact=True)
                if incident.get("official_reportable") and str(source_kind or "").strip().lower() != "social_rumor"
                else None
            ),
            official_item_link_counts=(
                incident_linked_item_counts(incident)
                if incident.get("official_reportable")
                else None
            ),
        )
        update_incident_propagation(incident, propagation_depth)

        social_queued = False
        if queue and str(source_kind or "").strip().lower() != "self":
            if urgency >= self.MIN_URGENT_QUEUE_SCORE:
                knowledge.queue_incident(
                    incident_id,
                    queue="urgent",
                    score=urgency,
                    tick=getattr(self.sim, "tick", 0),
                )
            elif social_interest >= self.MIN_SOCIAL_QUEUE_SCORE:
                social_queued = knowledge.queue_incident(
                    incident_id,
                    queue="social",
                    score=social_interest,
                    tick=getattr(self.sim, "tick", 0),
                )
        if social_queued:
            hydrate_incident_social_knowledge(self.sim, eid, source_event="incident_social_queued")

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

    def _incident_scene_anchor(self, incident, event):
        victim_eid = event.data.get("victim_eid")
        victim_pos = self.sim.ecs.get(Position).get(victim_eid) if victim_eid is not None else None
        if victim_pos is not None:
            scene_x = int(victim_pos.x)
            scene_y = int(victim_pos.y)
            scene_z = int(victim_pos.z)
        else:
            scene_x = _safe_int(event.data.get("target_x", event.data.get("x")), default=0)
            scene_y = _safe_int(event.data.get("target_y", event.data.get("y")), default=0)
            scene_z = _safe_int(event.data.get("target_z", event.data.get("z", 0)), default=0)
        prop = None
        property_id = _text(incident.get("property_id") or event.data.get("property_id"))
        if property_id:
            prop = self.sim.properties.get(property_id)
        if not isinstance(prop, dict):
            prop = property_covering(self.sim, scene_x, scene_y, scene_z)
        property_id = _text((prop or {}).get("id"))
        building_id = _property_building_id(prop)
        if property_id and not incident.get("property_id"):
            incident["property_id"] = property_id
        if property_id and not incident.get("property_name") and isinstance(prop, dict):
            incident["property_name"] = prop.get("name")
        return {
            "x": scene_x,
            "y": scene_y,
            "z": scene_z,
            "prop": prop if isinstance(prop, dict) else None,
            "property_id": property_id or None,
            "building_id": building_id or None,
        }

    def _scene_property_ids(self, *, property_id="", building_id=""):
        property_id = _text(property_id)
        building_id = _text(building_id)
        if not property_id and not building_id:
            return ()
        ids = []
        for raw_property_id, prop in getattr(self.sim, "properties", {}).items():
            current_property_id = _text(raw_property_id)
            if not current_property_id or not isinstance(prop, dict):
                continue
            if property_id and current_property_id == property_id:
                ids.append(current_property_id)
                continue
            if building_id and _property_building_id(prop) == building_id:
                ids.append(current_property_id)
        return tuple(dict.fromkeys(ids))

    def _stamp_scene_link_metadata(self, entry, *, prop=None, incident_id=None, victim_eid=None):
        metadata = stamp_item_provenance(
            self.sim,
            entry,
            prop=prop,
            source_context=((entry or {}).get("metadata") or {}).get("source_context"),
            source_incident_id=incident_id,
            source_victim_eid=victim_eid,
        )
        return metadata

    def _capture_inventory_entry(self, rows, inventory, entry, *, link_kind, holder_eid_at_capture, prop=None, building_id="", victim_eid=None, incident_id=None, capture_tick=0):
        if not isinstance(entry, dict):
            return
        claim = classify_item_claim(self.sim, entry, prop=prop)
        metadata = self._stamp_scene_link_metadata(
            {**entry, "metadata": entry.get("metadata")},
            prop=prop,
            incident_id=incident_id,
            victim_eid=victim_eid,
        )
        if inventory is not None and hasattr(inventory, "update_item_metadata"):
            inventory.update_item_metadata(entry.get("instance_id"), metadata=metadata, replace=True)
        rows.append({
            "instance_id": entry.get("instance_id"),
            "item_id": entry.get("item_id"),
            "link_kind": link_kind,
            "claim_class": claim.get("claim_class"),
            "owner_eid": claim.get("source_owner_eid", entry.get("owner_eid")),
            "holder_eid_at_capture": holder_eid_at_capture,
            "property_id": _text((prop or {}).get("id")) or claim.get("source_property_id"),
            "building_id": building_id or _property_building_id(prop),
            "captured_tick": capture_tick,
            "source_victim_eid": victim_eid,
            "source_incident_id": incident_id,
        })

    def _capture_container_entry(self, rows, entry, *, prop=None, building_id="", victim_eid=None, incident_id=None, capture_tick=0):
        if not isinstance(entry, dict):
            return
        claim = classify_item_claim(self.sim, entry, prop=prop)
        if claim.get("claim_class") in {CLAIM_PUBLIC_FREE, CLAIM_SCENE_SALVAGE}:
            return
        entry["metadata"] = self._stamp_scene_link_metadata(
            {**entry, "metadata": entry.get("metadata")},
            prop=prop,
            incident_id=incident_id,
            victim_eid=victim_eid,
        )
        rows.append({
            "instance_id": entry.get("instance_id"),
            "item_id": entry.get("item_id"),
            "link_kind": "scene_claimed",
            "claim_class": claim.get("claim_class"),
            "owner_eid": claim.get("source_owner_eid", entry.get("owner_eid")),
            "holder_eid_at_capture": None,
            "property_id": _text((prop or {}).get("id")) or claim.get("source_property_id"),
            "building_id": building_id or _property_building_id(prop),
            "captured_tick": capture_tick,
            "source_victim_eid": victim_eid,
            "source_incident_id": incident_id,
        })

    def _capture_ground_item(self, rows, ground, *, prop=None, building_id="", victim_eid=None, incident_id=None, capture_tick=0, scene_x=0, scene_y=0, scene_z=0):
        if not isinstance(ground, dict):
            return
        claim = classify_item_claim(self.sim, ground, prop=prop)
        distance = abs(_safe_int(ground.get("x"), scene_x) - int(scene_x)) + abs(_safe_int(ground.get("y"), scene_y) - int(scene_y))
        same_level = _safe_int(ground.get("z"), scene_z) == int(scene_z)
        claim_class = claim.get("claim_class")
        if claim_class in {CLAIM_PUBLIC_FREE, CLAIM_SCENE_SALVAGE}:
            if not same_level or distance > int(SCENE_RESIDUE_RADIUS):
                return
            link_kind = "scene_residue"
        else:
            link_kind = "scene_claimed"
        ground["metadata"] = self._stamp_scene_link_metadata(
            {**ground, "metadata": ground.get("metadata")},
            prop=prop,
            incident_id=incident_id,
            victim_eid=victim_eid,
        )
        rows.append({
            "instance_id": ground.get("instance_id"),
            "item_id": ground.get("item_id"),
            "link_kind": link_kind,
            "claim_class": claim_class,
            "owner_eid": claim.get("source_owner_eid", ground.get("owner_eid")),
            "holder_eid_at_capture": None,
            "property_id": _text((prop or {}).get("id")) or claim.get("source_property_id"),
            "building_id": building_id or _property_building_id(prop),
            "captured_tick": capture_tick,
            "source_victim_eid": victim_eid,
            "source_incident_id": incident_id,
        })

    def _recent_victim_take(self, entry, *, victim_eid=None, offender_eid=None, property_id="", building_id="", capture_tick=0):
        metadata = entry.get("metadata") if isinstance((entry or {}).get("metadata"), dict) else {}
        if victim_eid is None or offender_eid is None:
            return False
        victim_eid = _safe_int(victim_eid, default=-1)
        offender_eid = _safe_int(offender_eid, default=-1)
        source_owner_eid = _safe_int(metadata.get("source_owner_eid"), default=-1)
        source_actor_eid = _safe_int(metadata.get("source_actor_eid"), default=-1)
        if source_owner_eid != victim_eid and source_actor_eid != victim_eid:
            return False
        if _safe_int(metadata.get("last_holder_eid"), default=-1) != offender_eid:
            return False
        transfer_tick = _safe_int(metadata.get("last_transfer_tick"), default=-10_000)
        if int(capture_tick) - transfer_tick > int(PRECOMBAT_TRANSFER_WINDOW):
            return False
        source_property_id = _text(metadata.get("source_property_id"))
        if property_id and source_property_id and source_property_id == _text(property_id):
            return True
        source_prop = self.sim.properties.get(source_property_id) if source_property_id else None
        source_building_id = _property_building_id(source_prop)
        if building_id and source_building_id and source_building_id == _text(building_id):
            return True
        return not property_id and not building_id

    def _capture_violent_scene_items(self, incident, event):
        if not isinstance(incident, dict):
            return incident
        victim_eid = event.data.get("victim_eid")
        if victim_eid is None:
            return incident
        offender_eid = event.data.get("offender_eid", event.data.get("eid"))
        capture_tick = int(getattr(self.sim, "tick", 0))
        anchor = self._incident_scene_anchor(incident, event)
        property_id = _text(anchor.get("property_id"))
        building_id = _text(anchor.get("building_id"))
        scene_prop = anchor.get("prop")
        scene_x = _safe_int(anchor.get("x"), default=0)
        scene_y = _safe_int(anchor.get("y"), default=0)
        scene_z = _safe_int(anchor.get("z"), default=0)
        scene_property_ids = self._scene_property_ids(property_id=property_id, building_id=building_id)

        linked_rows = []

        victim_inventory = self.sim.ecs.get(Inventory).get(victim_eid)
        if victim_inventory is not None:
            for entry in list(getattr(victim_inventory, "items", ()) or ()):
                self._capture_inventory_entry(
                    linked_rows,
                    victim_inventory,
                    entry,
                    link_kind="victim_inventory",
                    holder_eid_at_capture=victim_eid,
                    prop=scene_prop,
                    building_id=building_id,
                    victim_eid=victim_eid,
                    incident_id=incident.get("id"),
                    capture_tick=capture_tick,
                )

        offender_inventory = self.sim.ecs.get(Inventory).get(offender_eid) if offender_eid is not None else None
        if offender_inventory is not None:
            for entry in list(getattr(offender_inventory, "items", ()) or ()):
                if not self._recent_victim_take(
                    entry,
                    victim_eid=victim_eid,
                    offender_eid=offender_eid,
                    property_id=property_id,
                    building_id=building_id,
                    capture_tick=capture_tick,
                ):
                    continue
                self._capture_inventory_entry(
                    linked_rows,
                    offender_inventory,
                    entry,
                    link_kind="precombat_stolen_from_victim",
                    holder_eid_at_capture=offender_eid,
                    prop=scene_prop,
                    building_id=building_id,
                    victim_eid=victim_eid,
                    incident_id=incident.get("id"),
                    capture_tick=capture_tick,
                )

        for ground in tuple(getattr(self.sim, "ground_items", {}).values()):
            if not isinstance(ground, dict):
                continue
            ground_prop = property_covering(
                self.sim,
                _safe_int(ground.get("x"), default=scene_x),
                _safe_int(ground.get("y"), default=scene_y),
                _safe_int(ground.get("z"), default=scene_z),
            )
            ground_property_id = _text((ground_prop or {}).get("id"))
            ground_building_id = _property_building_id(ground_prop)
            same_scope = False
            if property_id and ground_property_id == property_id:
                same_scope = True
            elif building_id and ground_building_id == building_id:
                same_scope = True
            elif not property_id and not building_id:
                same_scope = True
            if not same_scope:
                continue
            self._capture_ground_item(
                linked_rows,
                ground,
                prop=ground_prop if isinstance(ground_prop, dict) else scene_prop,
                building_id=ground_building_id or building_id,
                victim_eid=victim_eid,
                incident_id=incident.get("id"),
                capture_tick=capture_tick,
                scene_x=scene_x,
                scene_y=scene_y,
                scene_z=scene_z,
            )

        inventories_by_kind = getattr(self.sim, "container_inventories", None)
        if isinstance(inventories_by_kind, dict):
            for container_kind, inventories in inventories_by_kind.items():
                kind_key = _text(container_kind).lower()
                if kind_key not in CONTAINER_CAPTURE_KINDS or not isinstance(inventories, dict):
                    continue
                for candidate_property_id in scene_property_ids:
                    prop = self.sim.properties.get(candidate_property_id)
                    entries = property_runtime_container_entries(
                        self.sim,
                        candidate_property_id,
                        container_kind=kind_key,
                    )
                    for entry in list(entries or ()):
                        self._capture_container_entry(
                            linked_rows,
                            entry,
                            prop=prop,
                            building_id=_property_building_id(prop) or building_id,
                            victim_eid=victim_eid,
                            incident_id=incident.get("id"),
                            capture_tick=capture_tick,
                        )

        return record_incident_scene_items(
            self.sim,
            incident.get("id"),
            capture_tick=capture_tick,
            property_id=property_id,
            building_id=building_id,
            linked_items=linked_rows,
        )

    def _event_accountability(self, event, *, strict=False):
        offender_eid = event.data.get("offender_eid", event.data.get("eid"))
        return event_observation_accountability(
            self.sim,
            event,
            offender_eid=offender_eid,
            default_channels=("actor_witness",),
            use_legacy_witness_fallback=not bool(strict),
            allow_position_backfill=not bool(strict),
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
        observation = self._event_accountability(event, strict=True)
        existing_observers = {
            int(observer_eid)
            for observer_eid in tuple(incident.get("observer_eids", ()))
            if observer_eid is not None
        }
        existing_observers.update(int(observer_eid) for observer_eid in tuple(observation.get("observer_eids", ())))
        existing_accountable = {
            int(observer_eid)
            for observer_eid in tuple(incident.get("accountable_observer_eids", ()))
            if observer_eid is not None
        }
        existing_accountable.update(
            int(observer_eid)
            for observer_eid in tuple(observation.get("accountable_observer_eids", ()))
            if observer_eid is not None
        )
        observation_channels = {
            str(channel or "").strip().lower()
            for channel in tuple(incident.get("observation_channels", ()))
            if str(channel or "").strip()
        }
        observation_channels.update(
            str(channel or "").strip().lower()
            for channel in tuple(observation.get("observation_channels", ()))
            if str(channel or "").strip()
        )
        incident["observer_eids"] = tuple(sorted(existing_observers))
        incident["accountable_observer_eids"] = tuple(sorted(existing_accountable))
        incident["observation_channels"] = tuple(sorted(observation_channels))
        incident["accountable_observed"] = bool(
            incident.get("accountable_observed")
            or observation.get("has_accountable_observation")
        )
        incident["witnessed"] = bool(incident["accountable_observed"])
        for field in (
            "access_level",
            "severity_label",
            "ingress_kind",
            "aperture_kind",
            "ingress_method",
            "context",
            "action",
            "offense_tier",
            "item_id",
            "item_name",
            "target_eid",
            "target_name",
            "target_taxonomy",
        ):
            value = event.data.get(field)
            if value not in (None, "", ()):
                incident[field] = value
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
        observation = self._event_accountability(event, strict=True)

        official_reportable = (
            bool(observation.get("has_accountable_observation"))
            and (
                context in OFFICIAL_REPORTABLE_OFFENSE_CONTEXTS
                or (context not in WILDLIFE_OFFENSE_CONTEXTS and offense_score >= 24)
            )
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
        if context in {"unarmed_assault", "melee_assault", "armed_assault", "explosive_discharge"} and event.data.get("victim_eid") is not None:
            incident = self._capture_violent_scene_items(incident, event) or incident
        witnesses = tuple(observation.get("accountable_observer_eids", ()))
        self._learn_self_and_witnesses(incident, event, source_kind="witnessed", witnesses=witnesses)

    def on_property_trespass(self, event):
        severity = int(event.data.get("severity_score", 0) or 0)
        if severity <= 0:
            return
        observation = self._event_accountability(event, strict=True)
        incident = self._create_incident(
            event,
            kind="property_trespass",
            severity=severity,
            merge_subject=str(event.data.get("property_id", "") or "").strip(),
            official_reportable=bool(observation.get("has_accountable_observation")),
            note=str(event.data.get("severity_label", "trespass") or "").strip().lower(),
            tags=(
                event.data.get("severity_label"),
                event.data.get("access_level"),
                event.data.get("ingress_kind"),
                event.data.get("ingress_method"),
            ),
        )
        witnesses = tuple(observation.get("accountable_observer_eids", ()))
        self._learn_self_and_witnesses(incident, event, source_kind="witnessed", witnesses=witnesses)

    def on_property_tamper(self, event):
        severity = int(event.data.get("severity_score", 0) or 0)
        if severity <= 0:
            return
        observation = self._event_accountability(event, strict=True)
        incident = self._create_incident(
            event,
            kind="property_tamper",
            severity=severity,
            merge_subject=str(event.data.get("property_id", "") or "").strip(),
            official_reportable=bool(observation.get("has_accountable_observation")),
            note="property_tamper",
            tags=(
                event.data.get("severity_label"),
                event.data.get("ingress_kind"),
                event.data.get("ingress_method"),
            ),
        )
        witnesses = tuple(observation.get("accountable_observer_eids", ()))
        self._learn_self_and_witnesses(incident, event, source_kind="witnessed", witnesses=witnesses)

    def on_item_stolen(self, event):
        item_name = str(event.data.get("item_name", event.data.get("item_id", "item")) or "").strip() or "item"
        observation = self._event_accountability(event, strict=True)
        incident = self._create_incident(
            event,
            kind="item_stolen",
            severity=72,
            merge_subject=str(event.data.get("property_id", event.data.get("item_id", "")) or "").strip(),
            official_reportable=bool(observation.get("has_accountable_observation")),
            note=item_name,
            tags=("theft", event.data.get("item_id")),
        )
        witnesses = tuple(observation.get("accountable_observer_eids", ()))
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

    def on_fire_event(self, event):
        x = event.data.get("x")
        y = event.data.get("y")
        if x is None or y is None:
            return
        try:
            severity = max(24, min(100, int(event.data.get("severity", 40) or 40)))
        except (TypeError, ValueError):
            severity = 40
        building_id = str(event.data.get("building_id", "") or "").strip().lower()
        property_id = str(event.data.get("property_id", "") or "").strip().lower()
        merge_subject = building_id or property_id or f"{int(x)}:{int(y)}:{int(event.data.get('z', 0) or 0)}"
        source_kind = str(event.data.get("source_kind", "") or "").strip().lower()
        note = f"{source_kind} fire" if source_kind else "structure fire"
        incident = self._create_incident(
            event,
            kind="structure_fire",
            severity=severity,
            merge_subject=merge_subject,
            official_reportable=True,
            note=note,
            tags=("fire", "hazard", "disaster"),
        )
        observation = self._event_accountability(event)
        witnesses = tuple(observation.get("accountable_observer_eids", ()))
        self._learn_self_and_witnesses(incident, event, source_kind="witnessed", witnesses=witnesses)

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
