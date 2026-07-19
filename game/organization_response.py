from __future__ import annotations

from engine.events import Event
from engine.systems import System

from game.components import AI, Position
from game.incident_runtime import incident_record
from game.justice_identity_runtime import event_evidence_resolves_subject
from game.organization_reputation import organization_snapshot as _organization_snapshot
from game.organizations import (
    local_operational_practice_bundle,
    organization_profile,
    organization_policy_snapshot,
    property_org_watch_state,
    property_org_links,
    record_organization_watchlist,
)
from game.property_runtime import property_covering as _property_covering
from game.run_pressure import apply_pressure_delta
from game.system_support.awareness_runtime import event_observation_accountability
from game.vision_scene_runtime import event_is_vision_only


MAX_HISTORY = 64
RESPONSE_COOLDOWN_TICKS = 40
INHABITANT_ROLES = {
    "resident",
    "civilian",
    "worker",
    "clerk",
    "cashier",
    "merchant",
    "shopkeeper",
    "manager",
}
VIGILANTE_RESPONSE_BASE = {
    "property_trespass": 2,
    "property_tamper": 4,
    "item_stolen": 5,
    "unarmed_assault": 6,
    "melee_assault": 7,
    "armed_assault": 8,
    "explosive_discharge": 10,
    "homicide": 12,
}
VIGILANTE_DENIAL_TICKS = {
    "property_trespass": 150,
    "property_tamper": 220,
    "item_stolen": 260,
    "unarmed_assault": 280,
    "melee_assault": 320,
    "armed_assault": 360,
    "explosive_discharge": 420,
    "homicide": 520,
}


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _text(value):
    return str(value or "").strip()


def _state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    state = traits.get("organization_response")
    if not isinstance(state, dict):
        state = {}
        traits["organization_response"] = state
    denials = state.get("property_denials")
    if not isinstance(denials, dict):
        denials = {}
        state["property_denials"] = denials
    cooldowns = state.get("cooldowns")
    if not isinstance(cooldowns, dict):
        cooldowns = {}
        state["cooldowns"] = cooldowns
    history = state.get("history")
    if not isinstance(history, list):
        history = []
        state["history"] = history
    if len(history) > MAX_HISTORY:
        del history[:-MAX_HISTORY]
    return state


def property_vigilante_denial(sim, prop, *, viewer_eid=None, current_tick=None):
    if not isinstance(prop, dict):
        return None
    state = _state(sim)
    property_id = _text(prop.get("id"))
    if not property_id:
        return None
    tick = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick, 0)
    legacy = state["property_denials"].get(property_id)
    if isinstance(legacy, dict) and tick > _safe_int(legacy.get("service_denial_until_tick"), default=-1):
        state["property_denials"].pop(property_id, None)
        legacy = None
    if isinstance(legacy, dict):
        target_eid = legacy.get("target_eid")
        if viewer_eid is not None and target_eid not in {None, viewer_eid}:
            legacy = None

    watch_rows = property_org_watch_state(
        sim,
        prop,
        subject_eid=viewer_eid,
        active_only=True,
        current_tick=tick,
    )
    denial_rows = [
        row
        for row in watch_rows
        if _text(row.get("action")).lower() in {"deny_service", "deny_entry"}
    ]
    if not denial_rows:
        return dict(legacy) if isinstance(legacy, dict) else None

    watch_row = denial_rows[0]
    profile = organization_profile(sim, watch_row.get("organization_eid"))
    merged = {
        "property_id": property_id,
        "property_name": _text(prop.get("name", prop.get("id"))),
        "organization_eid": _safe_int(watch_row.get("organization_eid"), default=0) or None,
        "organization_key": _text(watch_row.get("organization_key")) or _text(getattr(profile, "key", "")),
        "organization_name": _text(watch_row.get("organization_name")) or _text(getattr(profile, "name", "")),
        "root_organization_eid": _safe_int(watch_row.get("organization_eid"), default=0) or None,
        "root_organization_key": _text(watch_row.get("organization_key")) or _text(getattr(profile, "key", "")),
        "root_organization_name": _text(watch_row.get("organization_name")) or _text(getattr(profile, "name", "")),
        "reason": _text(watch_row.get("reason")) or _text(watch_row.get("action")) or "organization_denial",
        "source_event": "organization_watchlist",
        "watchfulness": min(
            100,
            int(watch_row.get("priority", 60))
            + (18 if _text(watch_row.get("action")).lower() == "deny_entry" else 10),
        ),
        "service_denial_until_tick": _safe_int(watch_row.get("expires_tick"), default=tick + 180),
        "target_eid": _safe_int(watch_row.get("subject_eid"), default=0) or None,
        "last_trigger_tick": _safe_int(watch_row.get("last_update_tick"), default=tick),
        "practice_note": _text(watch_row.get("reason")) or None,
    }
    if isinstance(legacy, dict):
        merged["service_denial_until_tick"] = max(
            _safe_int(legacy.get("service_denial_until_tick"), default=0),
            _safe_int(merged.get("service_denial_until_tick"), default=0),
        )
        merged["watchfulness"] = max(
            _safe_int(legacy.get("watchfulness"), default=0),
            _safe_int(merged.get("watchfulness"), default=0),
        )
        if not merged.get("reason"):
            merged["reason"] = _text(legacy.get("reason")) or "organization_denial"
        merged["source_event"] = _text(legacy.get("source_event")) or merged["source_event"]
    return merged


class OrganizationResponseSystem(System):

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.sim.events.subscribe("property_trespass", self.on_property_trespass)
        self.sim.events.subscribe("property_tamper", self.on_property_tamper)
        self.sim.events.subscribe("item_stolen", self.on_item_stolen)
        self.sim.events.subscribe("action_offense", self.on_action_offense)
        self.sim.events.subscribe("incident_authority_reported", self.on_incident_authority_reported)

    def _event_accountability(self, event, *, offender_eid=None, allow_position_backfill=True):
        return event_observation_accountability(
            self.sim,
            event,
            offender_eid=offender_eid,
            default_channels=("actor_witness",),
            allow_position_backfill=bool(allow_position_backfill),
        )

    def _mark_incident_accounted(self, incident_id):
        incident = incident_record(self.sim, incident_id)
        if not isinstance(incident, dict):
            return None
        incident["organization_response_accounted"] = True
        incident["organization_response_accounted_tick"] = int(getattr(self.sim, "tick", 0))
        return incident

    def _target_is_inhabitant(self, actor_eid):
        ai = self.sim.ecs.get(AI).get(actor_eid)
        role = _text(getattr(ai, "role", "")).lower()
        return role in INHABITANT_ROLES

    def _property_for_data(self, data):
        if not isinstance(data, dict):
            return None
        property_id = _text(data.get("property_id"))
        if property_id:
            prop = self.sim.properties.get(property_id)
            if isinstance(prop, dict):
                return prop
        try:
            x = int(data.get("x"))
            y = int(data.get("y"))
            z = int(data.get("z", 0))
        except (TypeError, ValueError):
            return None
        return _property_covering(self.sim, x, y, z)

    def _local_vigilante_link(self, prop):
        if not isinstance(prop, dict):
            return None
        ranked = []
        for link in property_org_links(self.sim, prop, active_only=True):
            organization_eid = _safe_int(link.get("organization_eid"), default=0)
            if organization_eid <= 0:
                continue
            policy = organization_policy_snapshot(self.sim, organization_eid=organization_eid)
            if not isinstance(policy, dict) or policy.get("family") != "street_gang":
                continue
            root_eid = _safe_int(policy.get("root_organization_eid"), default=organization_eid)
            root_profile = organization_profile(self.sim, root_eid)
            root_tags = {str(tag).strip().lower() for tag in getattr(root_profile, "tags", ()) or ()}
            if "gang_posture:vigilante" not in root_tags:
                continue
            rank = (
                0 if policy.get("org_role") == "cell" else 1,
                0 if _text(link.get("link_kind")).lower() in {"territory", "meeting_place", "safehouse"} else 1,
                0 if bool(link.get("primary", False)) else 1,
                organization_eid,
            )
            ranked.append((rank, link, policy))
        if not ranked:
            return None
        ranked.sort(key=lambda row: row[0])
        return {
            "link": ranked[0][1],
            "policy": ranked[0][2],
        }

    def _response_strength(self, prop, policy, reason):
        organization_eid = _safe_int(policy.get("organization_eid"), default=0)
        reputation = _organization_snapshot(self.sim, organization_eid=organization_eid, ensure=True) if organization_eid > 0 else None
        practice = local_operational_practice_bundle(
            self.sim,
            prop=prop,
            organization_eid=organization_eid if organization_eid > 0 else None,
            current_tick=getattr(self.sim, "tick", 0),
        )
        modifiers = dict(practice.get("effect_modifiers", {}))
        targeting_delta = _safe_float(modifiers.get("targeting_delta"), default=0.0)
        quality_delta = _safe_float(modifiers.get("quality_delta"), default=0.0)
        watchfulness_bonus = _safe_float(modifiers.get("watchfulness_bonus"), default=0.0)
        watch_priority_bonus = _safe_float(modifiers.get("watch_priority_bonus"), default=0.0)
        response_followthrough_bonus = _safe_float(modifiers.get("response_followthrough_bonus"), default=0.0)
        readiness_bonus = _safe_float(modifiers.get("response_readiness_tier"), default=0.0)
        confrontation_bonus = _safe_float(modifiers.get("confrontation_posture_bonus"), default=0.0)
        heat_bonus = int(max(0, int((reputation or {}).get("heat", 0) or 0)) // 25)
        base = int(VIGILANTE_RESPONSE_BASE.get(reason, 0))
        bonus = (
            int(round(max(0.0, targeting_delta) * 10.0))
            + int(round(max(0.0, quality_delta) * 6.0))
            + int(round(max(0.0, watchfulness_bonus) * 0.4))
            + int(round(max(0.0, watch_priority_bonus) * 0.25))
            + int(round(max(0.0, response_followthrough_bonus) * 12.0))
            + int(round(max(0.0, readiness_bonus) * 2.0))
            + int(round(max(0.0, confrontation_bonus) * 10.0))
            + heat_bonus
        )
        return {
            "pressure_delta": max(1, min(16, base + bonus)),
            "watchfulness": max(
                1,
                min(
                    100,
                    (base * 10)
                    + int(round(max(0.0, targeting_delta) * 25.0))
                    + int(round(max(0.0, watchfulness_bonus)))
                    + int(round(max(0.0, watch_priority_bonus)))
                    + int(round(max(0.0, confrontation_bonus) * 18.0))
                    + (heat_bonus * 6),
                ),
            ),
            "service_denial_until_tick": int(getattr(self.sim, "tick", 0)) + int(VIGILANTE_DENIAL_TICKS.get(reason, 180)),
            "practice_note": _text(practice.get("note_text")),
        }

    def _apply_vigilante_response(self, *, prop, reason, source_event, target_eid=None, source_incident_id=None):
        local = self._local_vigilante_link(prop)
        if not isinstance(local, dict):
            return None
        policy = local["policy"]
        organization_eid = _safe_int(policy.get("organization_eid"), default=0)
        root_eid = _safe_int(policy.get("root_organization_eid"), default=organization_eid)
        state = _state(self.sim)
        property_id = _text(prop.get("id"))
        cooldown_key = f"{property_id}:{_text(policy.get('root_organization_key')) or root_eid}:{reason}"
        now = int(getattr(self.sim, "tick", 0))
        last_tick = _safe_int(state["cooldowns"].get(cooldown_key), default=-10_000)
        strength = self._response_strength(prop, policy, reason)
        denial = {
            "property_id": property_id,
            "property_name": _text(prop.get("name", prop.get("id"))),
            "organization_eid": organization_eid or None,
            "organization_key": _text(policy.get("organization_key")),
            "organization_name": _text(policy.get("organization_name")),
            "root_organization_eid": root_eid or None,
            "root_organization_key": _text(policy.get("root_organization_key")),
            "root_organization_name": _text(policy.get("root_organization_name")),
            "reason": reason,
            "source_event": source_event,
            "watchfulness": int(strength["watchfulness"]),
            "service_denial_until_tick": int(strength["service_denial_until_tick"]),
            "target_eid": target_eid,
            "last_trigger_tick": now,
            "practice_note": _text(strength.get("practice_note")),
        }
        existing = state["property_denials"].get(property_id)
        if isinstance(existing, dict):
            denial["service_denial_until_tick"] = max(
                _safe_int(existing.get("service_denial_until_tick"), default=0),
                int(denial["service_denial_until_tick"]),
            )
            denial["watchfulness"] = max(
                _safe_int(existing.get("watchfulness"), default=0),
                int(denial["watchfulness"]),
            )
        state["property_denials"][property_id] = denial
        watch_action = "deny_entry" if reason in {"unarmed_assault", "melee_assault", "armed_assault", "explosive_discharge", "homicide"} else "deny_service"
        if target_eid is not None:
            record_organization_watchlist(
                self.sim,
                organization_eid=root_eid or organization_eid,
                entry_key=f"vigilante_{property_id}_{int(target_eid)}_{reason}",
                subject_eid=target_eid,
                action=watch_action,
                reason=reason,
                source_kind="organization_response",
                source_incident_id=source_incident_id,
                target_scope="property",
                target_property_id=property_id,
                priority=75 if watch_action == "deny_entry" else 68,
                effective_tick=now,
                expires_tick=int(denial["service_denial_until_tick"]),
                active=True,
            )
        state["cooldowns"][cooldown_key] = now
        if now - last_tick >= int(RESPONSE_COOLDOWN_TICKS):
            apply_pressure_delta(
                self.sim,
                delta=int(strength["pressure_delta"]),
                source="organization_vigilante",
                reason=f"{_text(policy.get('root_organization_key')) or _text(policy.get('root_organization_name'))}:{reason}",
                source_event=source_event,
            )
        entry = {
            "tick": now,
            "property_id": property_id,
            "organization_key": _text(policy.get("organization_key")),
            "root_organization_key": _text(policy.get("root_organization_key")),
            "reason": reason,
            "source_event": source_event,
            "target_eid": target_eid,
        }
        state["history"].append(entry)
        if len(state["history"]) > MAX_HISTORY:
            del state["history"][:-MAX_HISTORY]
        self.sim.emit(Event(
            "organization_vigilante_response",
            property_id=property_id,
            property_name=denial["property_name"],
            organization_eid=organization_eid or None,
            organization_key=denial["organization_key"],
            organization_name=denial["organization_name"],
            root_organization_eid=root_eid or None,
            root_organization_key=denial["root_organization_key"],
            root_organization_name=denial["root_organization_name"],
            reason=reason,
            source_event=source_event,
            target_eid=target_eid,
            watchfulness=int(denial["watchfulness"]),
            service_denial_until_tick=int(denial["service_denial_until_tick"]),
            practice_note=denial["practice_note"],
        ))
        return denial

    def on_property_trespass(self, event):
        if event_is_vision_only(event):
            return
        if event.data.get("offender_eid") != self.player_eid:
            return
        observation = self._event_accountability(event, offender_eid=self.player_eid)
        if not bool(observation.get("has_accountable_observation")):
            return
        if not event_evidence_resolves_subject(self.sim, event, self.player_eid):
            return
        prop = self._property_for_data(event.data)
        if not isinstance(prop, dict):
            return
        response = self._apply_vigilante_response(
            prop=prop,
            reason="property_trespass",
            source_event="property_trespass",
            target_eid=self.player_eid,
            source_incident_id=event.data.get("knowledge_incident_id"),
        )
        if response is not None:
            self._mark_incident_accounted(event.data.get("knowledge_incident_id"))

    def on_property_tamper(self, event):
        if event_is_vision_only(event):
            return
        if event.data.get("offender_eid") != self.player_eid:
            return
        observation = self._event_accountability(event, offender_eid=self.player_eid)
        if not bool(observation.get("has_accountable_observation")):
            return
        if not event_evidence_resolves_subject(self.sim, event, self.player_eid):
            return
        prop = self._property_for_data(event.data)
        if not isinstance(prop, dict):
            return
        response = self._apply_vigilante_response(
            prop=prop,
            reason="property_tamper",
            source_event="property_tamper",
            target_eid=self.player_eid,
            source_incident_id=event.data.get("knowledge_incident_id"),
        )
        if response is not None:
            self._mark_incident_accounted(event.data.get("knowledge_incident_id"))

    def on_item_stolen(self, event):
        if event_is_vision_only(event):
            return
        if event.data.get("offender_eid") != self.player_eid:
            return
        observation = self._event_accountability(event, offender_eid=self.player_eid)
        if not bool(observation.get("has_accountable_observation")):
            return
        if not event_evidence_resolves_subject(self.sim, event, self.player_eid):
            return
        prop = self._property_for_data(event.data)
        if not isinstance(prop, dict):
            return
        response = self._apply_vigilante_response(
            prop=prop,
            reason="item_stolen",
            source_event="item_stolen",
            target_eid=self.player_eid,
            source_incident_id=event.data.get("knowledge_incident_id"),
        )
        if response is not None:
            self._mark_incident_accounted(event.data.get("knowledge_incident_id"))

    def on_action_offense(self, event):
        if event_is_vision_only(event):
            return
        if event.data.get("offender_eid") != self.player_eid:
            return
        context = _text(event.data.get("context")).lower()
        if context not in {"unarmed_assault", "melee_assault", "armed_assault", "explosive_discharge", "homicide"}:
            return
        observation = self._event_accountability(event, offender_eid=self.player_eid)
        if not bool(observation.get("has_accountable_observation")):
            return
        if not event_evidence_resolves_subject(self.sim, event, self.player_eid):
            return
        target_eid = event.data.get("target_eid")
        if target_eid is None or not self._target_is_inhabitant(target_eid):
            return
        prop = self._property_for_data(event.data)
        if not isinstance(prop, dict):
            return
        response = self._apply_vigilante_response(
            prop=prop,
            reason=context,
            source_event="action_offense",
            target_eid=self.player_eid,
            source_incident_id=event.data.get("knowledge_incident_id"),
        )
        if response is not None:
            self._mark_incident_accounted(event.data.get("knowledge_incident_id"))

    def on_incident_authority_reported(self, event):
        if event_is_vision_only(event):
            return
        incident = incident_record(self.sim, event.data.get("incident_id"))
        if not isinstance(incident, dict):
            return
        if event_is_vision_only(incident):
            return
        if not event_evidence_resolves_subject(self.sim, event, self.player_eid):
            return
        if bool(incident.get("organization_response_accounted")):
            return
        observation = self._event_accountability(
            event,
            offender_eid=self.player_eid,
            allow_position_backfill=False,
        )
        if not bool(observation.get("has_accountable_observation")):
            return
        kind = _text(incident.get("kind")).lower()
        if kind in {"camera_alert", "property_trespass"}:
            reason = "property_trespass"
            prop = self._property_for_data(incident)
        elif kind == "property_tamper":
            reason = "property_tamper"
            prop = self._property_for_data(incident)
        elif kind == "item_stolen":
            reason = "item_stolen"
            prop = self._property_for_data(incident)
        elif kind == "homicide":
            reason = "homicide"
            target_eid = incident.get("victim_eid") or incident.get("target_eid")
            if target_eid is None or not self._target_is_inhabitant(target_eid):
                return
            prop = self._property_for_data(incident)
        elif kind == "action_offense":
            reason = _text(incident.get("context")).lower() or _text(incident.get("merge_subject")).split(":")[-1].lower()
            if reason not in {"unarmed_assault", "melee_assault", "armed_assault", "explosive_discharge", "homicide"}:
                return
            target_eid = incident.get("victim_eid") or incident.get("target_eid")
            if target_eid is None or not self._target_is_inhabitant(target_eid):
                return
            prop = self._property_for_data(incident)
        else:
            return
        if not isinstance(prop, dict):
            return
        response = self._apply_vigilante_response(
            prop=prop,
            reason=reason,
            source_event="incident_authority_reported",
            target_eid=self.player_eid,
            source_incident_id=incident.get("id"),
        )
        if response is not None:
            self._mark_incident_accounted(incident.get("id"))


__all__ = ["OrganizationResponseSystem", "property_vigilante_denial"]
