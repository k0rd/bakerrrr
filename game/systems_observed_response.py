"""Observed incident response routing for BAKERRRR.

This is the behavior-side companion to systems_observed_events.py.
It listens for `observed_response_cue` and turns authority/help cues into
persistent NPC intent targets that NPCWillSystem/NPCInvestigateSystem can move.

Keep this layer boring on purpose:
- observed incident consequence system decides WHY an NPC wants to respond
- this system decides WHERE the NPC should go / HOW it tries to report
- NPCWillSystem preserves the state
- NPCInvestigateSystem moves the actor and emits arrival/completion events
"""

from __future__ import annotations

from engine.events import Event
from engine.systems import System
from engine.visibility import observer_can_see_position

from game.components import AI, IncidentKnowledge, Inventory, JusticeProfile, NPCWill, NPCRoutine, Position
from game.incident_runtime import incident_record
from game.items import item_display_name
from game.item_semantics import inventory_has_phone, item_tags
from game.property_runtime import property_infrastructure_role as _property_infrastructure_role
from game.system_support.actor_runtime import _entity_is_downed
from game.system_support.awareness_runtime import observation_payload_from_observers


PEACE_ROLES = {"guard", "scout", "officer", "police", "deputy", "marshal", "security"}
RESPONSE_STATE_BY_CUE = {
    "report_authority": "reporting_incident",
    "help_victim": "helping_victim",
    "seek_shelter": "seeking_safety",
    "warn_nearby": "warning",
}
REPORT_METHOD_PRIORITY = ("camera_network", "cell_phone", "peace_officer", "alarm", "work_phone", "home_phone")
DEFAULT_RESPONSE_TTL = 900
DELAYED_REPORT_METHODS = {"peace_officer", "alarm", "work_phone", "home_phone"}


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


def _dist(a, b):
    return abs(int(a[0]) - int(b[0])) + abs(int(a[1]) - int(b[1]))


def _pos_tuple(pos):
    if pos is None:
        return None
    return (int(pos.x), int(pos.y), int(pos.z))


class ObservedIncidentResponseSystem(System):
    """Routes response cues into durable NPC movement/arrival behavior."""

    def __init__(self, sim):
        super().__init__(sim)
        self.pending = {}
        self.completed = set()
        self.sim.events.subscribe("observed_response_cue", self.on_observed_response_cue)
        self.sim.events.subscribe("npc_report_arrived", self.on_npc_report_arrived)
        self.sim.events.subscribe("npc_help_arrived", self.on_npc_help_arrived)
        if not hasattr(sim, "observed_response_stats"):
            sim.observed_response_stats = {
                "queued": 0,
                "reported": 0,
                "help_arrivals": 0,
                "phone_reports": 0,
                "radio_reports": 0,
                "radio_assists": 0,
                "camera_reports": 0,
                "dropped": 0,
            }

    def on_observed_response_cue(self, event):
        data = dict(getattr(event, "data", {}) or {})
        npc_eid = data.get("npc_eid")
        incident_id = data.get("incident_id")
        try:
            npc_eid = int(npc_eid)
            incident_id = int(incident_id)
        except (TypeError, ValueError):
            return

        cue_kind = _key(data.get("cue_kind"))
        state = RESPONSE_STATE_BY_CUE.get(cue_kind)
        if not state:
            return

        incident = incident_record(self.sim, incident_id) or {}
        pos = self.sim.ecs.get(Position).get(npc_eid)
        if pos is None:
            return

        route = self._select_route(npc_eid, cue_kind, incident, data)
        if not route:
            if cue_kind == "report_authority":
                self.sim.observed_response_stats["dropped"] += 1
                self._clear_actor_cue(npc_eid, incident_id)
                self.sim.emit(Event(
                    "observed_response_dropped",
                    npc_eid=npc_eid,
                    incident_id=incident_id,
                    reason="no_report_route",
                ))
            return

        now = int(getattr(self.sim, "tick", 0))
        pending = {
            "npc_eid": npc_eid,
            "incident_id": incident_id,
            "cue_kind": cue_kind,
            "state": state,
            "method": route.get("method", ""),
            "report_device_item_id": route.get("item_id"),
            "report_device_item_name": route.get("item_name"),
            "target": route.get("target"),
            "target_eid": route.get("target_eid"),
            "urgency": _float(data.get("urgency"), 0.0),
            "reason": _text(data.get("reason")),
            "created_tick": now,
            "expires_tick": now + DEFAULT_RESPONSE_TTL,
            "completed": False,
        }

        # If the NPC has a phone/radio, reporting is immediate and local. Still
        # emit a report event so authority/report systems can dedupe globally.
        if cue_kind == "report_authority" and route.get("method") in {"cell_phone", "radio", "camera_network"}:
            if route.get("method") == "cell_phone":
                self._emit_report_device_used(pending, x=pos.x, y=pos.y, z=pos.z)
            self._emit_authority_report(pending, x=pos.x, y=pos.y, z=pos.z)
            if route.get("method") == "radio":
                assist_eid = self._call_remote_peace_officer(pending, reporter_pos=pos, incident=incident)
                if assist_eid is None:
                    self._emit_report_device_used(pending, x=pos.x, y=pos.y, z=pos.z)
                self.sim.observed_response_stats["radio_reports"] += 1
            if route.get("method") == "camera_network":
                self.sim.observed_response_stats["camera_reports"] += 1
            elif route.get("method") == "cell_phone":
                self.sim.observed_response_stats["phone_reports"] += 1
            self._clear_actor_cue(npc_eid, incident_id)
            return

        self.pending[npc_eid] = pending
        self.sim.observed_response_stats["queued"] += 1
        self._apply_pending_intent(pending)

    def update(self):
        now = int(getattr(self.sim, "tick", 0))
        positions = self.sim.ecs.get(Position)
        for npc_eid, cue in tuple(self.pending.items()):
            if cue.get("completed"):
                self.pending.pop(npc_eid, None)
                continue
            if now > int(cue.get("expires_tick", 0) or 0):
                self._drop_cue(npc_eid, cue, reason="expired")
                continue
            if incident_record(self.sim, cue.get("incident_id")) is None:
                self._drop_cue(npc_eid, cue, reason="incident_missing")
                continue
            pos = positions.get(npc_eid)
            if pos is None:
                self._drop_cue(npc_eid, cue, reason="actor_missing_position")
                continue
            if cue.get("holding_report"):
                ai = self.sim.ecs.get(AI).get(npc_eid)
                if _entity_is_downed(self.sim, npc_eid):
                    self._drop_cue(npc_eid, cue, reason="reporter_downed")
                    continue
                if not self._report_hold_is_valid(cue, pos, ai):
                    self._drop_cue(npc_eid, cue, reason="report_interrupted")
                    continue
                if now >= _int(cue.get("report_ready_tick"), now + 1):
                    self._emit_authority_report(cue, x=pos.x, y=pos.y, z=pos.z)
                    self._finish_cue(npc_eid, cue)
                    continue
                self._apply_report_hold(cue)
                continue
            if self._cue_is_complete(cue, pos):
                self._finish_cue(npc_eid, cue)
                continue
            self._apply_pending_intent(cue)

    def on_npc_report_arrived(self, event):
        data = dict(getattr(event, "data", {}) or {})
        npc_eid = _int(data.get("npc_eid"), -1)
        incident_id = _int(data.get("incident_id"), -1)
        cue = self.pending.get(npc_eid)
        if not cue or _int(cue.get("incident_id"), -2) != incident_id:
            return
        if self._cue_needs_report_hold(cue):
            hold_pos = self.sim.ecs.get(Position).get(npc_eid)
            if hold_pos is None:
                self._drop_cue(npc_eid, cue, reason="actor_missing_position")
                return
            self._begin_report_hold(cue, hold_pos)
            return
        self._emit_authority_report(cue, x=data.get("x"), y=data.get("y"), z=data.get("z"))
        self._finish_cue(npc_eid, cue)

    def on_npc_help_arrived(self, event):
        data = dict(getattr(event, "data", {}) or {})
        npc_eid = _int(data.get("npc_eid"), -1)
        incident_id = _int(data.get("incident_id"), -1)
        cue = self.pending.get(npc_eid)
        if not cue or _int(cue.get("incident_id"), -2) != incident_id:
            return
        self.sim.observed_response_stats["help_arrivals"] += 1
        self.sim.emit(Event(
            "npc_helped_victim",
            npc_eid=npc_eid,
            incident_id=incident_id,
            victim_eid=cue.get("target_eid"),
            method=cue.get("method", "reach_victim"),
            x=data.get("x"),
            y=data.get("y"),
            z=data.get("z"),
        ))
        self._finish_cue(npc_eid, cue)

    def _select_route(self, npc_eid, cue_kind, incident, cue_data):
        if cue_kind == "help_victim":
            target_eid = cue_data.get("target_eid") or incident.get("victim_eid")
            target_pos = self._entity_position(target_eid)
            if target_pos:
                return {"method": "reach_victim", "target": target_pos, "target_eid": target_eid}
            fallback = self._incident_position(incident) or cue_data.get("target")
            if fallback:
                return {"method": "incident_site", "target": tuple(fallback), "target_eid": target_eid}
            return None

        if cue_kind == "seek_shelter":
            target = cue_data.get("target")
            if target:
                return {
                    "method": "retreat",
                    "target": tuple(target),
                    "target_eid": cue_data.get("target_eid") or incident.get("primary_actor_eid"),
                }
            return None

        if cue_kind == "warn_nearby":
            target = self._incident_position(incident) or cue_data.get("target") or _pos_tuple(self.sim.ecs.get(Position).get(npc_eid))
            return {"method": "local_warning", "target": tuple(target), "target_eid": None} if target else None

        if cue_kind != "report_authority":
            return None

        preferred_methods = tuple(
            method
            for method in (_key(raw_method) for raw_method in (cue_data.get("preferred_methods") or ()))
            if method
        )
        if "camera_network" in preferred_methods and self._has_camera_network(npc_eid, cue_data.get("incident_id")):
            return {
                "method": "camera_network",
                "target": self._incident_position(incident) or _pos_tuple(self.sim.ecs.get(Position).get(npc_eid)),
                "target_eid": None,
            }

        device = self._report_device(npc_eid)
        if device:
            return {
                "method": device.get("method", "cell_phone"),
                "item_id": device.get("item_id"),
                "item_name": device.get("item_name"),
                "target": _pos_tuple(self.sim.ecs.get(Position).get(npc_eid)),
                "target_eid": None,
            }

        pos = self.sim.ecs.get(Position).get(npc_eid)
        if pos is None:
            return None

        peace = self._nearest_peace_officer(npc_eid, pos, max_radius=18)
        if peace:
            return {"method": "peace_officer", "target": peace["target"], "target_eid": peace["eid"]}

        alarm = self._nearest_alarm(npc_eid, pos, max_radius=14)
        if alarm:
            return {"method": "alarm", "target": alarm["target"], "target_eid": None, "property_id": alarm.get("property_id")}

        routine = self.sim.ecs.get(NPCRoutine).get(npc_eid)
        if routine and routine.work:
            return {"method": "work_phone", "target": tuple(routine.work), "target_eid": None}
        if routine and routine.home:
            return {"method": "home_phone", "target": tuple(routine.home), "target_eid": None}

        return None

    def _cue_is_complete(self, cue, pos):
        cue_kind = _key(cue.get("cue_kind"))
        if cue_kind != "seek_shelter":
            return False
        target = cue.get("target")
        if not isinstance(target, (list, tuple)) or len(target) < 3:
            return False
        if int(pos.z) != _int(target[2], int(pos.z)):
            return False
        if _dist((pos.x, pos.y, pos.z), target) > 1:
            return False
        self.sim.emit(Event(
            "npc_shelter_arrived",
            npc_eid=_int(cue.get("npc_eid"), -1),
            incident_id=_int(cue.get("incident_id"), -1),
            method=_text(cue.get("method") or "retreat"),
            x=int(pos.x),
            y=int(pos.y),
            z=int(pos.z),
        ))
        return True

    def _has_phone(self, eid):
        inv = self.sim.ecs.get(Inventory).get(eid)
        if not inv:
            return False
        return inventory_has_phone(inv)

    def _report_device(self, eid):
        inv = self.sim.ecs.get(Inventory).get(eid)
        if not inv:
            return None
        fallback = None
        for entry in tuple(getattr(inv, "items", ()) or ()):
            item_id = _key(entry.get("item_id") if isinstance(entry, dict) else None)
            tags = item_tags(entry)
            if not item_id:
                continue
            if item_id in {"two_way_radio", "radio", "walkie_talkie"} or {"radio", "comms"} & tags:
                return {
                    "method": "radio",
                    "item_id": item_id,
                    "item_name": item_display_name(item_id, metadata=entry.get("metadata") if isinstance(entry, dict) else None),
                }
            if item_id in {"mobile_phone", "burner_phone", "unregistered_mobile_phone", "cell_phone", "phone"} or {"phone", "cellular"} & tags:
                fallback = {
                    "method": "cell_phone",
                    "item_id": item_id,
                    "item_name": item_display_name(item_id, metadata=entry.get("metadata") if isinstance(entry, dict) else None),
                }
        return fallback

    def _has_camera_network(self, eid, incident_id):
        try:
            incident_id = int(incident_id)
        except (TypeError, ValueError):
            return False
        knowledge = self.sim.ecs.get(IncidentKnowledge).get(eid)
        if knowledge is None:
            return False
        record = knowledge.records.get(incident_id)
        if not isinstance(record, dict):
            return False
        return _key(record.get("source_kind")) == "camera" and bool(record.get("firsthand"))

    def _entity_position(self, eid):
        try:
            eid = int(eid)
        except (TypeError, ValueError):
            return None
        return _pos_tuple(self.sim.ecs.get(Position).get(eid))

    def _incident_position(self, incident):
        if not isinstance(incident, dict):
            return None
        if incident.get("x") is None or incident.get("y") is None:
            return None
        return (_int(incident.get("x")), _int(incident.get("y")), _int(incident.get("z"), 0))

    def _nearest_peace_officer(self, npc_eid, pos, *, max_radius=18):
        ais = self.sim.ecs.get(AI)
        positions = self.sim.ecs.get(Position)
        origin = (int(pos.x), int(pos.y), int(pos.z))
        ranked = []
        for eid, ai in ais.items():
            if eid == npc_eid:
                continue
            role = _key(getattr(ai, "role", ""))
            if role not in PEACE_ROLES:
                continue
            p = positions.get(eid)
            if not p or int(p.z) != int(pos.z):
                continue
            target = (int(p.x), int(p.y), int(p.z))
            distance = _dist(origin, target)
            if distance <= int(max_radius):
                ranked.append((distance, eid, target))
        if not ranked:
            return None
        ranked.sort(key=lambda row: (row[0], row[1]))
        return {"eid": ranked[0][1], "target": ranked[0][2]}

    def _nearest_remote_peace_officer(self, npc_eid, pos, *, max_radius=32):
        ais = self.sim.ecs.get(AI)
        positions = self.sim.ecs.get(Position)
        justices = self.sim.ecs.get(JusticeProfile)
        origin = (int(pos.x), int(pos.y), int(pos.z))
        ranked = []
        for eid, ai in ais.items():
            if eid == npc_eid:
                continue
            role = _key(getattr(ai, "role", ""))
            justice = justices.get(eid)
            if role not in PEACE_ROLES and not bool(getattr(justice, "enforce_all", False)):
                continue
            if _key(getattr(ai, "state", "")) in {"protecting", "reporting_incident", "helping_victim", "seeking_safety", "downed"}:
                continue
            if _entity_is_downed(self.sim, eid):
                continue
            p = positions.get(eid)
            if not p or int(p.z) != int(pos.z):
                continue
            target = (int(p.x), int(p.y), int(p.z))
            distance = _dist(origin, target)
            if distance > int(max_radius):
                continue
            if observer_can_see_position(
                self.sim,
                npc_eid,
                int(pos.x),
                int(pos.y),
                int(pos.z),
                target[0],
                target[1],
                target[2],
                radius=12,
            ):
                continue
            ranked.append((distance, eid, target))
        if not ranked:
            return None
        ranked.sort(key=lambda row: (row[0], row[1]))
        return {"eid": ranked[0][1], "target": ranked[0][2]}

    def _nearest_alarm(self, npc_eid, pos, *, max_radius=14):
        origin = (int(pos.x), int(pos.y), int(pos.z))
        disabled = getattr(self.sim, "camera_disabled", {})
        ranked = []
        for prop in getattr(self.sim, "properties", {}).values():
            if not isinstance(prop, dict):
                continue
            if _property_infrastructure_role(prop) != "alarm_target":
                continue
            if disabled.get(prop.get("id"), 0) > int(getattr(self.sim, "tick", 0)):
                continue
            pz = _int(prop.get("z"), 0)
            if pz != int(pos.z):
                continue
            target = (_int(prop.get("x")), _int(prop.get("y")), pz)
            distance = _dist(origin, target)
            if distance <= int(max_radius):
                ranked.append((distance, _text(prop.get("id")), target, prop))
        if not ranked:
            return None
        ranked.sort(key=lambda row: (row[0], row[1]))
        return {"target": ranked[0][2], "property_id": ranked[0][3].get("id")}

    def _apply_pending_intent(self, cue):
        npc_eid = _int(cue.get("npc_eid"), -1)
        ai = self.sim.ecs.get(AI).get(npc_eid)
        will = self.sim.ecs.get(NPCWill).get(npc_eid)
        if not ai or not will:
            return
        state = _text(cue.get("state"))
        target = cue.get("target")
        target_eid = cue.get("target_eid")
        score = max(45.0, min(98.0, _float(cue.get("urgency"), 0.5) * 100.0))
        ai.state = state
        ai.target = target
        ai.target_eid = target_eid
        ai.incident_id = cue.get("incident_id")
        will.intent = state
        will.score = score
        will.target = target
        will.target_eid = target_eid
        will.last_tick = int(getattr(self.sim, "tick", 0))

    def _cue_needs_report_hold(self, cue):
        return (
            _key(cue.get("cue_kind")) == "report_authority"
            and _key(cue.get("method")) in DELAYED_REPORT_METHODS
        )

    def _report_delay_ticks(self, method):
        method_key = _key(method)
        if method_key not in DELAYED_REPORT_METHODS:
            return 0
        clock = getattr(self.sim, "world_traits", {}).get("clock", {})
        ticks_per_hour = _int((clock or {}).get("ticks_per_hour"), 600)
        return max(1, int(round(float(ticks_per_hour) / 60.0)))

    def _begin_report_hold(self, cue, pos):
        now = int(getattr(self.sim, "tick", 0))
        hold_pos = (int(pos.x), int(pos.y), int(pos.z))
        cue["holding_report"] = True
        cue["hold_position"] = hold_pos
        if _int(cue.get("report_ready_tick"), 0) <= now:
            cue["report_ready_tick"] = now + self._report_delay_ticks(cue.get("method"))
        self._apply_report_hold(cue)

    def _apply_report_hold(self, cue):
        npc_eid = _int(cue.get("npc_eid"), -1)
        ai = self.sim.ecs.get(AI).get(npc_eid)
        will = self.sim.ecs.get(NPCWill).get(npc_eid)
        hold_pos = cue.get("hold_position")
        if not ai or not will or not isinstance(hold_pos, (list, tuple)) or len(hold_pos) < 3:
            return
        score = max(45.0, min(98.0, _float(cue.get("urgency"), 0.5) * 100.0))
        ai.state = "holding"
        ai.target = tuple(hold_pos)
        ai.target_eid = None
        ai.incident_id = cue.get("incident_id")
        will.intent = "holding"
        will.score = score
        will.target = tuple(hold_pos)
        will.target_eid = None
        will.last_tick = int(getattr(self.sim, "tick", 0))

    def _report_hold_is_valid(self, cue, pos, ai):
        if ai is None:
            return False
        if _key(getattr(ai, "state", "")) != "holding":
            return False
        hold_pos = cue.get("hold_position")
        if not isinstance(hold_pos, (list, tuple)) or len(hold_pos) < 3:
            return False
        if int(pos.z) != _int(hold_pos[2], int(pos.z)):
            return False
        return _dist((pos.x, pos.y, pos.z), hold_pos) <= 1

    def _emit_authority_report(self, cue, *, x=None, y=None, z=None):
        incident_id = _int(cue.get("incident_id"), -1)
        incident = incident_record(self.sim, incident_id)
        reporter_eid = _int(cue.get("npc_eid"), -1)
        if isinstance(incident, dict):
            incident["officially_reported"] = True
            incident["reported_tick"] = int(getattr(self.sim, "tick", 0))
            incident["reported_by_eid"] = reporter_eid
            incident["report_method"] = _text(cue.get("method"))

        reports = getattr(self.sim, "world_traits", {}).setdefault("observed_authority_reports", {})
        reports[str(incident_id)] = {
            "incident_id": incident_id,
            "reported_tick": int(getattr(self.sim, "tick", 0)),
            "reported_by_eid": reporter_eid,
            "method": _text(cue.get("method")),
            "x": _int(x, 0),
            "y": _int(y, 0),
            "z": _int(z, 0),
        }
        self.sim.observed_response_stats["reported"] += 1
        observation = observation_payload_from_observers(
            self.sim,
            (reporter_eid,) if reporter_eid >= 0 else (),
            observation_channels=("authority_report",),
            allow_player_accountable=True,
        )
        self.sim.emit(Event(
            "incident_authority_reported",
            incident_id=incident_id,
            npc_eid=reporter_eid,
            method=_text(cue.get("method")),
            x=_int(x, 0),
            y=_int(y, 0),
            z=_int(z, 0),
            **observation,
        ))

    def _emit_report_device_used(self, cue, *, x=None, y=None, z=None, assist_eid=None):
        reporter_eid = _int(cue.get("npc_eid"), -1)
        method = _key(cue.get("method"))
        self.sim.emit(Event(
            "report_device_used",
            npc_eid=reporter_eid,
            incident_id=_int(cue.get("incident_id"), -1),
            method=method,
            item_id=_text(cue.get("report_device_item_id")),
            item_name=_text(cue.get("report_device_item_name")) or ("Two-Way Radio" if method == "radio" else "Phone"),
            assist_eid=assist_eid,
            x=_int(x, 0),
            y=_int(y, 0),
            z=_int(z, 0),
        ))

    def _call_remote_peace_officer(self, cue, *, reporter_pos, incident):
        reporter_eid = _int(cue.get("npc_eid"), -1)
        if reporter_eid < 0 or reporter_pos is None:
            return None
        candidate = self._nearest_remote_peace_officer(reporter_eid, reporter_pos)
        if not candidate:
            return None
        incident_id = _int(cue.get("incident_id"), -1)
        officer_eid = _int(candidate.get("eid"), -1)
        target_eid = None
        target = None
        if isinstance(incident, dict):
            target_eid = incident.get("primary_actor_eid")
            target = self._entity_position(target_eid)
            if target is None:
                target = self._incident_position(incident)
        if target is None:
            target = _pos_tuple(reporter_pos)
        if target is None:
            return None

        ai = self.sim.ecs.get(AI).get(officer_eid)
        will = self.sim.ecs.get(NPCWill).get(officer_eid)
        if not ai or not will:
            return None
        ai.state = "protecting" if target_eid is not None else "investigating"
        ai.target = tuple(target)
        ai.target_eid = target_eid
        ai.incident_id = incident_id
        ai.response_role = "radio_assist"
        ai.suppress_report_for_incident_id = incident_id
        will.intent = ai.state
        will.score = max(72.0, min(98.0, _float(cue.get("urgency"), 0.7) * 100.0))
        will.target = tuple(target)
        will.target_eid = target_eid
        will.last_tick = int(getattr(self.sim, "tick", 0))
        self.sim.observed_response_stats["radio_assists"] += 1
        self._emit_report_device_used(
            cue,
            x=reporter_pos.x,
            y=reporter_pos.y,
            z=reporter_pos.z,
            assist_eid=officer_eid,
        )
        self.sim.emit(Event(
            "radio_assist_called",
            incident_id=incident_id,
            reporter_eid=reporter_eid,
            officer_eid=officer_eid,
            target_eid=target_eid,
            x=int(target[0]),
            y=int(target[1]),
            z=int(target[2]),
        ))
        return officer_eid

    def _finish_cue(self, npc_eid, cue):
        cue["completed"] = True
        self.completed.add((_int(npc_eid, -1), _int(cue.get("incident_id"), -1), _text(cue.get("cue_kind"))))
        self.pending.pop(npc_eid, None)
        self._clear_actor_cue(npc_eid, cue.get("incident_id"))

    def _drop_cue(self, npc_eid, cue, *, reason=""):
        self.sim.observed_response_stats["dropped"] += 1
        self.pending.pop(npc_eid, None)
        self._clear_actor_cue(npc_eid, cue.get("incident_id"))
        self.sim.emit(Event(
            "observed_response_dropped",
            npc_eid=npc_eid,
            incident_id=cue.get("incident_id"),
            reason=reason,
        ))

    def _clear_actor_cue(self, npc_eid, incident_id):
        knowledge = self.sim.ecs.get(IncidentKnowledge).get(npc_eid)
        if knowledge is not None:
            try:
                incident_id = int(incident_id)
                knowledge.urgent_queue = [
                    entry for entry in knowledge.urgent_queue
                    if _int(entry.get("incident_id"), -1) != incident_id
                ]
            except (TypeError, ValueError):
                pass
        ai = self.sim.ecs.get(AI).get(npc_eid)
        will = self.sim.ecs.get(NPCWill).get(npc_eid)
        ai_incident_id = _int(getattr(ai, "incident_id", None), -1) if ai else -1
        clear_holding = bool(ai and _key(getattr(ai, "state", "")) == "holding" and ai_incident_id == _int(incident_id, -2))
        if ai and (_key(getattr(ai, "state", "")) in set(RESPONSE_STATE_BY_CUE.values()) or clear_holding):
            ai.state = "idle"
            ai.target = None
            ai.target_eid = None
            if hasattr(ai, "incident_id"):
                ai.incident_id = None
        if will and (
            _key(getattr(will, "intent", "")) in set(RESPONSE_STATE_BY_CUE.values())
            or (clear_holding and _key(getattr(will, "intent", "")) == "holding")
        ):
            will.intent = "idle"
            will.target = None
            will.target_eid = None
            will.score = 0.0
            will.last_tick = int(getattr(self.sim, "tick", 0))
