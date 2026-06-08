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

from game.components import AI, IncidentKnowledge, Inventory, NPCWill, NPCRoutine, Position
from game.incident_runtime import incident_record
from game.property_runtime import property_infrastructure_role as _property_infrastructure_role


PEACE_ROLES = {"guard", "scout", "officer", "police", "deputy", "marshal", "security"}
PHONE_ITEM_IDS = {"burner_phone", "cell_phone", "phone", "radio", "walkie_talkie", "two_way_radio"}
RESPONSE_STATE_BY_CUE = {
    "report_authority": "reporting_incident",
    "help_victim": "helping_victim",
    "warn_nearby": "warning",
}
REPORT_METHOD_PRIORITY = ("cell_phone", "peace_officer", "alarm", "work_phone", "home_phone", "incident_site")
DEFAULT_RESPONSE_TTL = 900


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
            return

        now = int(getattr(self.sim, "tick", 0))
        pending = {
            "npc_eid": npc_eid,
            "incident_id": incident_id,
            "cue_kind": cue_kind,
            "state": state,
            "method": route.get("method", ""),
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
        if cue_kind == "report_authority" and route.get("method") == "cell_phone":
            self._emit_authority_report(pending, x=pos.x, y=pos.y, z=pos.z)
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
            self._apply_pending_intent(cue)

    def on_npc_report_arrived(self, event):
        data = dict(getattr(event, "data", {}) or {})
        npc_eid = _int(data.get("npc_eid"), -1)
        incident_id = _int(data.get("incident_id"), -1)
        cue = self.pending.get(npc_eid)
        if not cue or _int(cue.get("incident_id"), -2) != incident_id:
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

        if cue_kind == "warn_nearby":
            target = self._incident_position(incident) or cue_data.get("target") or _pos_tuple(self.sim.ecs.get(Position).get(npc_eid))
            return {"method": "local_warning", "target": tuple(target), "target_eid": None} if target else None

        if cue_kind != "report_authority":
            return None

        if self._has_phone(npc_eid):
            return {"method": "cell_phone", "target": _pos_tuple(self.sim.ecs.get(Position).get(npc_eid)), "target_eid": None}

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

        target = self._incident_position(incident) or cue_data.get("target")
        if target:
            return {"method": "incident_site", "target": tuple(target), "target_eid": None}
        return None

    def _has_phone(self, eid):
        inv = self.sim.ecs.get(Inventory).get(eid)
        if not inv:
            return False
        for item in getattr(inv, "items", ()) or ():
            item_id = _key(item.get("item_id") if isinstance(item, dict) else "")
            if item_id in PHONE_ITEM_IDS:
                return True
        return False

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

    def _emit_authority_report(self, cue, *, x=None, y=None, z=None):
        incident_id = _int(cue.get("incident_id"), -1)
        incident = incident_record(self.sim, incident_id)
        if isinstance(incident, dict):
            incident["officially_reported"] = True
            incident["reported_tick"] = int(getattr(self.sim, "tick", 0))
            incident["reported_by_eid"] = _int(cue.get("npc_eid"), -1)
            incident["report_method"] = _text(cue.get("method"))

        reports = getattr(self.sim, "world_traits", {}).setdefault("observed_authority_reports", {})
        reports[str(incident_id)] = {
            "incident_id": incident_id,
            "reported_tick": int(getattr(self.sim, "tick", 0)),
            "reported_by_eid": _int(cue.get("npc_eid"), -1),
            "method": _text(cue.get("method")),
            "x": _int(x, 0),
            "y": _int(y, 0),
            "z": _int(z, 0),
        }
        self.sim.observed_response_stats["reported"] += 1
        self.sim.emit(Event(
            "incident_authority_reported",
            incident_id=incident_id,
            npc_eid=_int(cue.get("npc_eid"), -1),
            method=_text(cue.get("method")),
            x=_int(x, 0),
            y=_int(y, 0),
            z=_int(z, 0),
        ))

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
        if ai and _key(getattr(ai, "state", "")) in set(RESPONSE_STATE_BY_CUE.values()):
            ai.state = "idle"
            ai.target = None
            ai.target_eid = None
            if hasattr(ai, "incident_id"):
                ai.incident_id = None
        if will and _key(getattr(will, "intent", "")) in set(RESPONSE_STATE_BY_CUE.values()):
            will.intent = "idle"
            will.target = None
            will.target_eid = None
            will.score = 0.0
            will.last_tick = int(getattr(self.sim, "tick", 0))
