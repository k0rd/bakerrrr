"""NPC social boundary, ejection, and property exclusion behavior."""

from collections import deque

from engine.events import Event
from engine.systems import System
from game.components import AI, Collider, NPCMemory, NPCWill, Position
from game.incident_runtime import incident_record
from game.organizations import (
    actor_branch_briefing_packet,
    property_org_links,
    record_organization_watchlist,
    refresh_loaded_organization_branch_briefings,
)
from game.property_runtime import property_covering
from game.quick_travel_ramps import map_mode_active
from game.social_boundary_runtime import (
    BOUNDARY_DIALOGUE_BAN_TICKS,
    BOUNDARY_EJECTION_GRACE_TICKS,
    INCIDENT_DENY_TICKS_BY_KIND,
    active_ejection_state,
    ejection_key,
    eligible_incident_ban_kind,
)
from game.system_support.ai_intent_runtime import _sync_ai_intent


def _text(value):
    return str(value or "").strip()


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


def _manhattan(ax, ay, bx, by):
    return abs(int(ax) - int(bx)) + abs(int(ay) - int(by))


def _property_id(prop):
    return _text((prop or {}).get("id")) if isinstance(prop, dict) else ""


def _property_name(prop, fallback="this place"):
    if not isinstance(prop, dict):
        return fallback
    return _text(prop.get("name")) or _text(prop.get("id")) or fallback


def _prop_owner_eid(prop):
    if not isinstance(prop, dict):
        return None
    owner_eid = prop.get("owner_eid")
    try:
        return int(owner_eid) if owner_eid is not None else None
    except (TypeError, ValueError):
        return None


def _actor_has_property_claim(sim, actor_eid, prop):
    actor_eid = _safe_int(actor_eid, default=0)
    if actor_eid <= 0 or not isinstance(prop, dict):
        return False
    if _prop_owner_eid(prop) == actor_eid:
        return True
    packet = actor_branch_briefing_packet(sim, actor_eid, prop)
    if _safe_int(packet.get("packet_count"), default=0) > 0:
        return True
    return False


def _organization_for_property_enforcer(sim, enforcer_eid, prop):
    if not isinstance(prop, dict):
        return None
    packet = actor_branch_briefing_packet(sim, enforcer_eid, prop)
    for organization_eid in tuple(packet.get("organization_eids", ()) or ()):
        organization_eid = _safe_int(organization_eid, default=0)
        if organization_eid > 0:
            return organization_eid
    for link in property_org_links(sim, prop, active_only=True):
        organization_eid = _safe_int(link.get("organization_eid"), default=0)
        if organization_eid > 0:
            return organization_eid
    return None


def _row_active(row, tick):
    if not isinstance(row, dict):
        return False
    if not bool(row.get("active", True)):
        return False
    if _safe_int(row.get("effective_tick"), default=0) > int(tick):
        return False
    expires_tick = row.get("expires_tick")
    if expires_tick is not None and _safe_int(expires_tick, default=int(tick)) < int(tick):
        return False
    return True


def _watch_row_subject(row):
    return _safe_int((row or {}).get("subject_eid"), default=0)


def _row_action(row):
    return _text((row or {}).get("action")).lower()


def _blocking_actor_at(sim, moving_eid, x, y, z):
    colliders = sim.ecs.get(Collider)
    for other_eid in tuple(getattr(sim, "tilemap", None).entities_at(x, y, z) if getattr(sim, "tilemap", None) else ()):
        if other_eid == moving_eid:
            continue
        collider = colliders.get(other_eid) if colliders else None
        if collider and bool(getattr(collider, "blocks", False)):
            return other_eid
    return None


def _same_floor_exit_path(sim, prop, start_pos):
    if not isinstance(prop, dict) or start_pos is None:
        return ()
    tilemap = getattr(sim, "tilemap", None)
    if tilemap is None:
        return ()
    start = (int(start_pos.x), int(start_pos.y), int(start_pos.z))
    prop_id = _property_id(prop)
    if not prop_id:
        return ()
    queue = deque([start])
    seen = {start}
    parent = {start: None}
    best = None
    while queue and len(seen) < 256:
        x, y, z = queue.popleft()
        current_prop = property_covering(sim, x, y, z)
        if _property_id(current_prop) != prop_id and tilemap.is_walkable(x, y, z):
            path = []
            current = (x, y, z)
            while current is not None:
                path.append(current)
                current = parent.get(current)
            return tuple(reversed(path))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx = x + dx
            ny = y + dy
            nz = z
            key = (nx, ny, nz)
            if key in seen:
                continue
            if not tilemap.in_bounds(nx, ny) or not tilemap.is_walkable(nx, ny, nz):
                continue
            seen.add(key)
            parent[key] = (x, y, z)
            queue.append(key)
            if best is None:
                best = key
    if best is None:
        return ()
    path = []
    current = best
    while current is not None:
        path.append(current)
        current = parent.get(current)
    return tuple(reversed(path))


def _nearest_same_floor_exit(sim, prop, start_pos):
    path = _same_floor_exit_path(sim, prop, start_pos)
    if not path:
        return None
    return path[-1]


class NPCBoundaryEnforcementSystem(System):
    """Turns social boundary violations into refusal/ejection before violence."""

    UPDATE_INTERVAL = 2

    def __init__(self, sim):
        super().__init__(sim)
        self.next_update_tick = 0
        self.sim.events.subscribe("npc_boundary_violation", self.on_npc_boundary_violation)
        self.sim.events.subscribe("knowledge_incident_learned", self.on_knowledge_incident_learned)
        self.sim.events.subscribe("entity_moved", self.on_entity_moved)

    def _remember_social_irritation(self, npc_eid, target_eid, *, reason="", strength=0.42, event=None):
        memories = self.sim.ecs.get(NPCMemory)
        memory = memories.get(npc_eid) if memories else None
        if memories is not None and memory is None:
            memory = NPCMemory()
            self.sim.ecs.add(npc_eid, memory)
        if not memory:
            return
        memory.remember(
            tick=self.sim.tick,
            kind="social_irritation",
            strength=max(0.08, min(1.0, _safe_float(strength, default=0.42))),
            actor_eid=target_eid,
            reason=_text(reason) or "dialogue_boundary",
            source_event=_text(event),
        )

    def _emit_violence_eligible_offense(self, event):
        npc_eid = event.data.get("npc_eid") or event.data.get("enforcer_eid")
        target_eid = event.data.get("target_eid") or event.data.get("offender_eid")
        if npc_eid is None or target_eid is None:
            return
        self.sim.emit(Event(
            "npc_offended",
            npc_eid=npc_eid,
            offender_eid=target_eid,
            action="boundary_violation",
            context="dialogue_boundary_violation",
            offense_score=max(30, _safe_int(event.data.get("offense_score"), default=30)),
            offense_tier="serious",
            perceived=max(0.72, _safe_float(event.data.get("perceived"), default=0.72)),
            violence_eligible=True,
        ))

    def _record_property_watchlist(
        self,
        *,
        enforcer_eid,
        target_eid,
        prop,
        action="deny_entry",
        reason="dialogue_boundary",
        source_kind="dialogue_boundary",
        source_incident_id=None,
        priority=72,
        expires_tick=None,
    ):
        property_id = _property_id(prop)
        if not property_id:
            return None
        organization_eid = _organization_for_property_enforcer(self.sim, enforcer_eid, prop)
        if organization_eid is None:
            return None
        if expires_tick is None:
            expires_tick = int(self.sim.tick) + BOUNDARY_DIALOGUE_BAN_TICKS
        entry_key = f"{_text(reason) or 'boundary'}_{property_id}_{_safe_int(target_eid)}_{_text(source_incident_id) or self.sim.tick}"
        row = record_organization_watchlist(
            self.sim,
            organization_eid=organization_eid,
            entry_key=entry_key,
            subject_eid=target_eid,
            action=action,
            reason=reason,
            source_kind=source_kind,
            source_eid=enforcer_eid,
            source_incident_id=source_incident_id,
            target_scope="property",
            target_property_id=property_id,
            priority=priority,
            effective_tick=int(self.sim.tick),
            expires_tick=expires_tick,
            active=True,
        )
        if row is not None:
            refresh_loaded_organization_branch_briefings(
                self.sim,
                property_ids=(property_id,),
                reason="boundary_watchlist",
            )
        return row

    def _enforcer_monitor_target(self, enforcer_eid, target_eid, prop, exit_path=()):
        positions = self.sim.ecs.get(Position)
        tilemap = getattr(self.sim, "tilemap", None)
        if tilemap is None or not isinstance(prop, dict):
            return None
        enforcer_pos = positions.get(enforcer_eid) if positions else None
        target_pos = positions.get(target_eid) if positions else None
        if enforcer_pos is None or target_pos is None:
            return None
        avoid = {
            (int(cell[0]), int(cell[1]), int(cell[2]))
            for cell in tuple(exit_path or ())
            if isinstance(cell, (tuple, list)) and len(cell) >= 3
        }
        current = (int(enforcer_pos.x), int(enforcer_pos.y), int(enforcer_pos.z))
        target_cell = (int(target_pos.x), int(target_pos.y), int(target_pos.z))
        if current not in avoid and current != target_cell:
            return current

        candidates = []
        z = int(target_pos.z)
        for radius in (1, 2, 3):
            for dx in range(-radius, radius + 1):
                for dy in range(-radius, radius + 1):
                    if abs(dx) + abs(dy) != radius:
                        continue
                    x = int(target_pos.x) + dx
                    y = int(target_pos.y) + dy
                    cell = (x, y, z)
                    if cell in avoid or cell == target_cell:
                        continue
                    if not tilemap.in_bounds(x, y) or not tilemap.is_walkable(x, y, z):
                        continue
                    if _blocking_actor_at(self.sim, enforcer_eid, x, y, z) is not None:
                        continue
                    candidates.append(cell)
            if candidates:
                break
        if not candidates:
            return None
        candidates.sort(key=lambda cell: (_manhattan(cell[0], cell[1], enforcer_pos.x, enforcer_pos.y), _manhattan(cell[0], cell[1], target_pos.x, target_pos.y)))
        return candidates[0]

    def _set_enforcer_intent(self, enforcer_eid, target_eid, *, prop=None, exit_path=()):
        ais = self.sim.ecs.get(AI)
        wills = self.sim.ecs.get(NPCWill)
        positions = self.sim.ecs.get(Position)
        ai = ais.get(enforcer_eid) if ais else None
        if not ai:
            return
        target = self._enforcer_monitor_target(enforcer_eid, target_eid, prop, exit_path=exit_path)
        if target is None:
            target_pos = positions.get(target_eid) if positions else None
            if target_pos is not None:
                target = (int(target_pos.x), int(target_pos.y), int(target_pos.z))
        _sync_ai_intent(
            ai,
            wills.get(enforcer_eid) if wills else None,
            self.sim.tick,
            "ejecting_target",
            score=0.92,
            target=target,
            target_eid=target_eid,
        )
        self.sim.emit(Event(
            "npc_intent_changed",
            npc_eid=enforcer_eid,
            intent="ejecting_target",
            target=target,
            target_eid=target_eid,
        ))

    def _set_enforcer_leading_intent(self, enforcer_eid, target_eid, prop, *, exit_path=()):
        ais = self.sim.ecs.get(AI)
        wills = self.sim.ecs.get(NPCWill)
        positions = self.sim.ecs.get(Position)
        ai = ais.get(enforcer_eid) if ais else None
        enforcer_pos = positions.get(enforcer_eid) if positions else None
        if not ai or enforcer_pos is None:
            return None
        leader_path = _same_floor_exit_path(self.sim, prop, enforcer_pos)
        lead_target = tuple(leader_path[-1]) if leader_path else (tuple(exit_path[-1]) if exit_path else None)
        if lead_target is None:
            return None
        _sync_ai_intent(
            ai,
            wills.get(enforcer_eid) if wills else None,
            self.sim.tick,
            "ejecting_target",
            score=0.98,
            target=lead_target,
            target_eid=target_eid,
        )
        self.sim.emit(Event(
            "npc_intent_changed",
            npc_eid=enforcer_eid,
            intent="ejecting_target",
            target=lead_target,
            target_eid=target_eid,
        ))
        return lead_target

    def _ejectee_exit_path(self, target_eid, prop):
        positions = self.sim.ecs.get(Position)
        target_pos = positions.get(target_eid) if positions else None
        if not target_pos:
            return ()
        return _same_floor_exit_path(self.sim, prop, target_pos)

    def _set_target_leaving(self, target_eid, prop, *, exit_path=()):
        ais = self.sim.ecs.get(AI)
        wills = self.sim.ecs.get(NPCWill)
        ai = ais.get(target_eid) if ais else None
        if not ai:
            return None
        if not exit_path:
            exit_path = self._ejectee_exit_path(target_eid, prop)
        exit_target = tuple(exit_path[-1]) if exit_path else None
        if not exit_target:
            return None
        _sync_ai_intent(
            ai,
            wills.get(target_eid) if wills else None,
            self.sim.tick,
            "leaving_property",
            score=0.96,
            target=exit_target,
            target_eid=None,
        )
        self.sim.emit(Event(
            "npc_intent_changed",
            npc_eid=target_eid,
            intent="leaving_property",
            target=exit_target,
            target_eid=None,
        ))
        return exit_target

    def _set_target_following_ejector(self, target_eid, enforcer_eid):
        if _safe_int(target_eid, default=0) == _safe_int(getattr(self.sim, "player_eid", None), default=-1):
            return None
        ais = self.sim.ecs.get(AI)
        wills = self.sim.ecs.get(NPCWill)
        positions = self.sim.ecs.get(Position)
        ai = ais.get(target_eid) if ais else None
        enforcer_pos = positions.get(enforcer_eid) if positions else None
        if not ai or enforcer_pos is None:
            return None
        target = (int(enforcer_pos.x), int(enforcer_pos.y), int(enforcer_pos.z))
        _sync_ai_intent(
            ai,
            wills.get(target_eid) if wills else None,
            self.sim.tick,
            "following",
            score=0.95,
            target=target,
            target_eid=enforcer_eid,
        )
        self.sim.emit(Event(
            "npc_intent_changed",
            npc_eid=target_eid,
            intent="following",
            target=target,
            target_eid=enforcer_eid,
        ))
        return target

    def _start_ejection(
        self,
        *,
        enforcer_eid,
        target_eid,
        prop,
        reason="dialogue_boundary",
        source_kind="dialogue_boundary",
        source_incident_id=None,
        violation_count=0,
        violence_eligible=False,
        record_watchlist=True,
    ):
        property_id = _property_id(prop)
        key = ejection_key(property_id, target_eid)
        if not key:
            return None
        if _safe_int(target_eid, default=0) == _safe_int(getattr(self.sim, "player_eid", None), default=-1) and map_mode_active(self.sim):
            return None
        state = active_ejection_state(self.sim)
        now = int(self.sim.tick)
        row = state.get(key) if isinstance(state.get(key), dict) else {}
        grace_until = max(_safe_int(row.get("grace_until_tick"), default=0), now + BOUNDARY_EJECTION_GRACE_TICKS)
        exit_path = self._ejectee_exit_path(target_eid, prop)
        monitor_target = self._enforcer_monitor_target(enforcer_eid, target_eid, prop, exit_path=exit_path)
        follow_ejector = not bool(exit_path) or monitor_target is None
        if follow_ejector:
            grace_until = max(grace_until, now + (BOUNDARY_EJECTION_GRACE_TICKS * 3))
        row.update(
            {
                "key": key,
                "property_id": property_id,
                "property_name": _property_name(prop),
                "enforcer_eid": _safe_int(enforcer_eid, default=0),
                "target_eid": _safe_int(target_eid, default=0),
                "reason": _text(reason) or "dialogue_boundary",
                "source_kind": _text(source_kind) or "dialogue_boundary",
                "source_incident_id": source_incident_id,
                "created_tick": _safe_int(row.get("created_tick"), default=now) or now,
                "last_warned_tick": now,
                "grace_until_tick": grace_until,
                "violation_count": max(_safe_int(row.get("violation_count"), default=0), _safe_int(violation_count, default=0)),
                "violence_eligible": bool(row.get("violence_eligible", False) or violence_eligible),
                "refused": bool(row.get("refused", False)),
                "egress_path": exit_path,
                "egress_mode": "follow_ejector" if follow_ejector else "direct_exit",
                "follow_required": bool(follow_ejector),
                "follow_grace_until_tick": grace_until if follow_ejector else 0,
                "monitor_target": monitor_target,
            }
        )
        state[key] = row

        if record_watchlist:
            self._record_property_watchlist(
                enforcer_eid=enforcer_eid,
                target_eid=target_eid,
                prop=prop,
                action="deny_entry",
                reason=_text(reason) or "dialogue_boundary",
                source_kind=source_kind,
                source_incident_id=source_incident_id,
                priority=76 if row["violence_eligible"] else 68,
            )

        exit_target = None
        lead_target = None
        follow_target = None
        if follow_ejector:
            lead_target = self._set_enforcer_leading_intent(enforcer_eid, target_eid, prop, exit_path=exit_path)
            follow_target = self._set_target_following_ejector(target_eid, enforcer_eid)
            exit_target = lead_target
            row["lead_target"] = lead_target
            row["follow_target"] = follow_target
        else:
            if _safe_int(target_eid, default=0) != _safe_int(getattr(self.sim, "player_eid", None), default=-1):
                exit_target = self._set_target_leaving(target_eid, prop, exit_path=exit_path)
            self._set_enforcer_intent(enforcer_eid, target_eid, prop=prop, exit_path=exit_path)

        self.sim.emit(Event(
            "npc_eject_target",
            npc_eid=enforcer_eid,
            enforcer_eid=enforcer_eid,
            target_eid=target_eid,
            property_id=property_id,
            property_name=_property_name(prop),
            reason=row["reason"],
            source_kind=row["source_kind"],
            source_incident_id=source_incident_id,
            grace_until_tick=grace_until,
            violence_eligible=bool(row["violence_eligible"]),
            egress_path=exit_path,
            egress_mode=row["egress_mode"],
            follow_required=bool(row["follow_required"]),
            lead_target=lead_target,
            follow_target=follow_target,
            exit_target=exit_target,
        ))
        return row

    def on_npc_boundary_violation(self, event):
        npc_eid = event.data.get("npc_eid") or event.data.get("enforcer_eid")
        target_eid = event.data.get("target_eid") or event.data.get("offender_eid")
        if npc_eid is None or target_eid is None:
            return
        violation_count = _safe_int(event.data.get("violation_count"), default=0)
        violence_eligible = bool(event.data.get("violence_eligible", False))
        self._remember_social_irritation(
            npc_eid,
            target_eid,
            reason=event.data.get("context") or event.data.get("source_kind") or "dialogue_boundary",
            strength=0.34 + (0.12 * max(0, violation_count)),
            event="npc_boundary_violation",
        )

        prop = None
        property_id = _text(event.data.get("property_id"))
        if property_id:
            prop = getattr(self.sim, "properties", {}).get(property_id)
        if prop is None:
            positions = self.sim.ecs.get(Position)
            pos = positions.get(target_eid) if positions else None
            if pos is not None:
                prop = property_covering(self.sim, pos.x, pos.y, pos.z)

        if isinstance(prop, dict) and _actor_has_property_claim(self.sim, npc_eid, prop):
            self._start_ejection(
                enforcer_eid=npc_eid,
                target_eid=target_eid,
                prop=prop,
                reason=event.data.get("context") or "dialogue_boundary",
                source_kind=event.data.get("source_kind") or "dialogue_boundary",
                source_incident_id=event.data.get("incident_id"),
                violation_count=violation_count,
                violence_eligible=violence_eligible,
                record_watchlist=bool(event.data.get("record_watchlist", True)),
            )
            return

        if violence_eligible:
            self._emit_violence_eligible_offense(event)

    def _incident_actor_target(self, record):
        for key in ("primary_actor_eid", "offender_eid", "actor_eid", "target_eid"):
            value = record.get(key)
            if value is not None:
                target = _safe_int(value, default=0)
                if target > 0:
                    return target
        return 0

    def _incident_property(self, record):
        property_id = _text(record.get("property_id") or record.get("scene_capture_property_id"))
        if not property_id:
            return None
        return getattr(self.sim, "properties", {}).get(property_id)

    def _knowledge_can_record_ban(self, learner_eid, prop):
        if learner_eid is None or not isinstance(prop, dict):
            return False
        if _prop_owner_eid(prop) == _safe_int(learner_eid, default=0):
            return True
        packet = actor_branch_briefing_packet(self.sim, learner_eid, prop)
        return _safe_int(packet.get("packet_count"), default=0) > 0

    def _incident_watch_action(self, event, record, ban_kind):
        confidence = _safe_float(event.data.get("confidence"), default=0.0)
        source_kind = _text(event.data.get("source_kind")).lower()
        firsthand = bool(event.data.get("firsthand", False))
        severity = max(
            _safe_int(event.data.get("severity"), default=0),
            _safe_int(record.get("severity"), default=0),
        )
        trusted_source = firsthand or source_kind in {
            "self",
            "witnessed",
            "camera",
            "authority_report",
            "official_report",
            "official",
        }
        if trusted_source and confidence >= 0.48:
            return "deny_entry"
        if ban_kind in {"assault", "weapon_discharge", "theft", "property_tamper", "tamper"} and confidence >= 0.72:
            return "deny_entry"
        if confidence >= 0.76 and severity >= 36:
            return "watch"
        return ""

    def on_knowledge_incident_learned(self, event):
        learner_eid = event.data.get("eid")
        incident_id = event.data.get("incident_id")
        record = incident_record(self.sim, incident_id)
        if not isinstance(record, dict):
            return
        ban_kind = eligible_incident_ban_kind(record.get("kind"), record.get("tags", ()))
        if not ban_kind:
            return
        prop = self._incident_property(record)
        if not isinstance(prop, dict):
            return
        target_eid = self._incident_actor_target(record)
        if target_eid <= 0 or target_eid == _safe_int(learner_eid, default=-1):
            return
        if not self._knowledge_can_record_ban(learner_eid, prop):
            return
        action = self._incident_watch_action(event, record, ban_kind)
        if not action:
            return
        expires_tick = int(self.sim.tick) + INCIDENT_DENY_TICKS_BY_KIND.get(ban_kind, 420)
        self._record_property_watchlist(
            enforcer_eid=learner_eid,
            target_eid=target_eid,
            prop=prop,
            action=action,
            reason=ban_kind,
            source_kind=event.data.get("source_kind") or "incident_knowledge",
            source_incident_id=incident_id,
            priority=82 if action == "deny_entry" else 48,
            expires_tick=expires_tick,
        )

    def _target_in_property(self, target_eid, property_id):
        positions = self.sim.ecs.get(Position)
        pos = positions.get(target_eid) if positions else None
        if pos is None:
            return False
        return _property_id(property_covering(self.sim, pos.x, pos.y, pos.z)) == _text(property_id)

    def _emit_ejection_refused(self, row, *, ingress_method="refused_ejection"):
        if bool(row.get("refused", False)):
            return
        row["refused"] = True
        target_eid = _safe_int(row.get("target_eid"), default=0)
        enforcer_eid = _safe_int(row.get("enforcer_eid"), default=0)
        property_id = _text(row.get("property_id"))
        self.sim.emit(Event(
            "npc_ejection_refused",
            npc_eid=enforcer_eid,
            enforcer_eid=enforcer_eid,
            target_eid=target_eid,
            property_id=property_id,
            property_name=row.get("property_name"),
            reason=row.get("reason"),
            ingress_method=ingress_method,
            violence_eligible=bool(row.get("violence_eligible", False)),
        ))
        pos = self.sim.ecs.get(Position).get(target_eid)
        self.sim.emit(Event(
            "property_trespass",
            offender_eid=target_eid,
            property_id=property_id,
            property_name=row.get("property_name"),
            x=getattr(pos, "x", None),
            y=getattr(pos, "y", None),
            z=getattr(pos, "z", 0),
            ingress_method=ingress_method,
            ingress_kind=ingress_method,
            witnessed=True,
            witnesses=(enforcer_eid,) if enforcer_eid > 0 else (),
            severity_score=34 if bool(row.get("violence_eligible", False)) else 24,
            severity_label="serious_trespass" if bool(row.get("violence_eligible", False)) else "trespass",
            source_event="npc_ejection_refused",
        ))

    def _emit_ejection_complied(self, key, row):
        self.sim.emit(Event(
            "npc_ejection_complied",
            npc_eid=_safe_int(row.get("enforcer_eid"), default=0),
            enforcer_eid=_safe_int(row.get("enforcer_eid"), default=0),
            target_eid=_safe_int(row.get("target_eid"), default=0),
            property_id=_text(row.get("property_id")),
            property_name=row.get("property_name"),
            reason=row.get("reason"),
        ))
        active_ejection_state(self.sim).pop(key, None)

    def _refresh_follow_ejection(self, row):
        if not isinstance(row, dict) or not bool(row.get("follow_required", False)):
            return False
        property_id = _text(row.get("property_id"))
        prop = getattr(self.sim, "properties", {}).get(property_id)
        if not isinstance(prop, dict):
            return False
        enforcer_eid = _safe_int(row.get("enforcer_eid"), default=0)
        target_eid = _safe_int(row.get("target_eid"), default=0)
        if enforcer_eid <= 0 or target_eid <= 0:
            return False
        lead_target = self._set_enforcer_leading_intent(
            enforcer_eid,
            target_eid,
            prop,
            exit_path=tuple(row.get("egress_path", ()) or ()),
        )
        follow_target = self._set_target_following_ejector(target_eid, enforcer_eid)
        if lead_target is not None:
            row["lead_target"] = lead_target
        if follow_target is not None:
            row["follow_target"] = follow_target
        return True

    def _enforcer_with_denial_brief(self, target_eid, prop):
        positions = self.sim.ecs.get(Position)
        target_pos = positions.get(target_eid) if positions else None
        if target_pos is None or not isinstance(prop, dict):
            return None, None
        best = None
        best_row = None
        for eid, pos in tuple(positions.items()):
            if eid == target_eid or int(pos.z) != int(target_pos.z):
                continue
            if _manhattan(pos.x, pos.y, target_pos.x, target_pos.y) > 8:
                continue
            packet = actor_branch_briefing_packet(self.sim, eid, prop)
            for row in tuple(packet.get("watch_rows", ()) or ()):
                if _watch_row_subject(row) != _safe_int(target_eid, default=0):
                    continue
                if _row_action(row) != "deny_entry" or not _row_active(row, self.sim.tick):
                    continue
                best = eid
                best_row = row
                break
            if best is not None:
                break
        return best, best_row

    def _enforce_denials_for_entity(self, target_eid, *, ingress_method="returned_after_ban"):
        positions = self.sim.ecs.get(Position)
        pos = positions.get(target_eid) if positions else None
        if pos is None:
            return False
        prop = property_covering(self.sim, pos.x, pos.y, pos.z)
        property_id = _property_id(prop)
        if not property_id:
            return False
        if ejection_key(property_id, target_eid) in active_ejection_state(self.sim):
            return False
        enforcer_eid, row = self._enforcer_with_denial_brief(target_eid, prop)
        if enforcer_eid is None or row is None:
            return False
        ejection = self._start_ejection(
            enforcer_eid=enforcer_eid,
            target_eid=target_eid,
            prop=prop,
            reason="returned_after_ban",
            source_kind=row.get("source_kind") or "organization_watchlist",
            source_incident_id=row.get("source_incident_id"),
            violation_count=1,
            violence_eligible=True,
            record_watchlist=False,
        )
        if ejection is not None:
            self._emit_ejection_refused(ejection, ingress_method=ingress_method)
            return True
        return False

    def _enforce_local_briefed_denials(self):
        positions = self.sim.ecs.get(Position)
        if not positions:
            return False
        enforced = False
        seen_pairs = set()
        for enforcer_eid, enforcer_pos in tuple(positions.items()):
            prop = property_covering(self.sim, enforcer_pos.x, enforcer_pos.y, enforcer_pos.z)
            property_id = _property_id(prop)
            if not property_id:
                continue
            packet = actor_branch_briefing_packet(self.sim, enforcer_eid, prop)
            if _safe_int(packet.get("packet_count"), default=0) <= 0:
                continue
            for watch_row in tuple(packet.get("watch_rows", ()) or ()):
                if _row_action(watch_row) != "deny_entry" or not _row_active(watch_row, self.sim.tick):
                    continue
                target_eid = _watch_row_subject(watch_row)
                if target_eid <= 0 or target_eid == _safe_int(enforcer_eid, default=0):
                    continue
                if target_eid == _safe_int(getattr(self.sim, "player_eid", None), default=-1) and map_mode_active(self.sim):
                    continue
                pair = (property_id, target_eid)
                if pair in seen_pairs or ejection_key(property_id, target_eid) in active_ejection_state(self.sim):
                    continue
                target_pos = positions.get(target_eid)
                if target_pos is None:
                    continue
                if _property_id(property_covering(self.sim, target_pos.x, target_pos.y, target_pos.z)) != property_id:
                    continue
                seen_pairs.add(pair)
                ejection = self._start_ejection(
                    enforcer_eid=enforcer_eid,
                    target_eid=target_eid,
                    prop=prop,
                    reason="returned_after_ban",
                    source_kind=watch_row.get("source_kind") or "organization_watchlist",
                    source_incident_id=watch_row.get("source_incident_id"),
                    violation_count=1,
                    violence_eligible=True,
                    record_watchlist=False,
                )
                if ejection is not None:
                    self._emit_ejection_refused(ejection, ingress_method="returned_after_ban")
                    enforced = True
        return enforced

    def on_entity_moved(self, event):
        target_eid = event.data.get("eid")
        if target_eid is None:
            return
        if target_eid == getattr(self.sim, "player_eid", None) and map_mode_active(self.sim):
            return
        self._enforce_denials_for_entity(target_eid)

    def update(self):
        if int(self.sim.tick) < int(self.next_update_tick):
            return
        self.next_update_tick = int(self.sim.tick) + self.UPDATE_INTERVAL
        state = active_ejection_state(self.sim)
        for key, row in tuple(state.items()):
            if not isinstance(row, dict):
                state.pop(key, None)
                continue
            target_eid = _safe_int(row.get("target_eid"), default=0)
            property_id = _text(row.get("property_id"))
            if target_eid <= 0 or not property_id:
                state.pop(key, None)
                continue
            if target_eid == _safe_int(getattr(self.sim, "player_eid", None), default=-1) and map_mode_active(self.sim):
                continue
            if not self._target_in_property(target_eid, property_id):
                self._emit_ejection_complied(key, row)
                continue
            if bool(row.get("follow_required", False)):
                self._refresh_follow_ejection(row)
            if int(self.sim.tick) >= _safe_int(row.get("grace_until_tick"), default=0):
                self._emit_ejection_refused(row)
        player_eid = getattr(self.sim, "player_eid", None)
        if player_eid is not None and not map_mode_active(self.sim):
            self._enforce_denials_for_entity(player_eid)
        self._enforce_local_briefed_denials()
