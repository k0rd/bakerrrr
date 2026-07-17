"""Sparse emergency actions for NPCs under an immediate threat.

Regular will-planning is intentionally broad and deliberative.  This runtime
owns the smaller invariant that a conscious actor in unresolved danger must
keep doing something survival-relevant: escape while a credible route is
making progress, surrender when that state is real, or fight when trapped.
"""

from __future__ import annotations

from engine.systems import System
from game.components import AI, NPCEmergencyState, NPCWill, Position, SuppressionState, Vitality
from game.npc_self_protection_runtime import active_self_protection_action, clear_self_protection_action


EMERGENCY_STALE_TICKS = 36
EMERGENCY_ESCAPE_GRACE_TICKS = 6
EMERGENCY_SAFE_DISTANCE = 8
EMERGENCY_FORCE_ATTACK_TICKS = 3
TEMPORARY_HOLD_ACTIONS = {"freeze", "look_busy"}


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _distance(left, right):
    if left is None or right is None:
        return None
    if int(left.z) != int(right.z):
        return None
    return max(abs(int(left.x) - int(right.x)), abs(int(left.y) - int(right.y)))


def npc_emergency_state(sim, eid, *, create=False, threat_eid=None, damage=0):
    try:
        eid = int(eid)
    except (TypeError, ValueError):
        return None
    states = sim.ecs.get(NPCEmergencyState)
    state = states.get(eid)
    if state is None and create:
        state = NPCEmergencyState(
            threat_eid,
            tick=_safe_int(getattr(sim, "tick", 0)),
            damage=damage,
        )
        sim.ecs.add(eid, state)
    return state


def npc_emergency_active(sim, eid, *, current_tick=None):
    state = npc_emergency_state(sim, eid, create=False)
    if state is None or not bool(getattr(state, "active", False)):
        return False
    tick = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick)
    if tick <= _safe_int(getattr(state, "expires_tick", tick), tick):
        return True
    threat_ai = sim.ecs.get(AI).get(getattr(state, "threat_eid", None))
    return bool(
        threat_ai is not None
        and _safe_int(getattr(threat_ai, "target_eid", None), -1) == int(eid)
        and str(getattr(threat_ai, "state", "") or "").strip().lower() in {"protecting", "chasing"}
    )


def active_emergency_actor_eids(sim):
    tick = _safe_int(getattr(sim, "tick", 0))
    return tuple(
        sorted(
            int(eid)
            for eid, state in tuple(sim.ecs.get(NPCEmergencyState).items())
            if state is not None and npc_emergency_active(sim, eid, current_tick=tick)
        )
    )


def emergency_protected_chunks(sim, unload_candidates=()):
    """Keep only unresolved-conflict chunks coarse-loaded outside the radius."""

    candidates = {
        (int(row[0]), int(row[1]))
        for row in tuple(unload_candidates or ())
        if isinstance(row, (tuple, list)) and len(row) >= 2
    }
    if not candidates:
        return set()
    positions = sim.ecs.get(Position)
    protected = set()
    for eid in active_emergency_actor_eids(sim):
        state = npc_emergency_state(sim, eid)
        for actor_eid in (eid, getattr(state, "threat_eid", None)):
            pos = positions.get(actor_eid)
            if pos is None:
                continue
            chunk = tuple(sim.chunk_coords(int(pos.x), int(pos.y)))
            if chunk in candidates:
                protected.add(chunk)
    return protected


class NPCEmergencyActionSystem(System):
    """Advance only actors currently participating in unresolved danger."""

    def __init__(self, sim):
        super().__init__(sim)
        self.sim.events.subscribe("entity_damaged", self.on_entity_damaged)
        self.sim.events.subscribe("npc_intent_changed", self.on_npc_intent_changed)
        self.sim.events.subscribe("npc_downed", self.on_actor_resolved)
        self.sim.events.subscribe("npc_killed", self.on_actor_resolved)
        self._backfill_existing_conflicts()

    def _begin(self, eid, threat_eid, *, damage=0):
        try:
            eid = int(eid)
            threat_eid = int(threat_eid)
            damage = int(damage or 0)
        except (TypeError, ValueError):
            return None
        if eid == threat_eid or eid == getattr(self.sim, "player_eid", None):
            return None
        ai = self.sim.ecs.get(AI).get(eid)
        if ai is None or str(getattr(ai, "role", "") or "").strip().lower() == "wildlife":
            return None
        vitality = self.sim.ecs.get(Vitality).get(eid)
        if vitality is not None and bool(getattr(vitality, "downed", False)):
            return None

        now = _safe_int(getattr(self.sim, "tick", 0))
        existing = npc_emergency_state(self.sim, eid, create=False)
        state = npc_emergency_state(
            self.sim,
            eid,
            create=True,
            threat_eid=threat_eid,
            damage=damage,
        )
        if state is None:
            return None
        changed_threat = existing is not None and _safe_int(getattr(state, "threat_eid", None), -1) != threat_eid
        state.active = True
        state.threat_eid = threat_eid
        if damage > 0:
            state.last_damage_tick = now
            if existing is not None:
                state.damage_count = 1 if changed_threat else _safe_int(getattr(state, "damage_count", 0)) + 1
        state.expires_tick = now + EMERGENCY_STALE_TICKS
        state.response = str(getattr(ai, "state", "") or "assessing").strip().lower() or "assessing"

        actor_pos = self.sim.ecs.get(Position).get(eid)
        threat_pos = self.sim.ecs.get(Position).get(threat_eid)
        state.last_position = (
            (int(actor_pos.x), int(actor_pos.y), int(actor_pos.z))
            if actor_pos is not None
            else None
        )
        state.last_threat_distance = _distance(actor_pos, threat_pos)
        state.last_safer_tick = now
        state.force_attack_after_tick = now
        return state

    def _backfill_existing_conflicts(self):
        for eid, ai in tuple(self.sim.ecs.get(AI).items()):
            state = str(getattr(ai, "state", "") or "").strip().lower()
            target_eid = getattr(ai, "target_eid", None)
            target_ai = self.sim.ecs.get(AI).get(target_eid)
            reciprocal = bool(
                target_ai is not None
                and _safe_int(getattr(target_ai, "target_eid", None), -1) == int(eid)
                and str(getattr(target_ai, "state", "") or "").strip().lower() in {"protecting", "chasing"}
            )
            if state in {"protecting", "chasing"} and target_eid is not None and reciprocal:
                self._begin(eid, target_eid)

    def _drop(self, eid):
        try:
            eid = int(eid)
        except (TypeError, ValueError):
            return False
        return self.sim.ecs.get(NPCEmergencyState).pop(eid, None) is not None

    def on_actor_resolved(self, event):
        target_eid = event.data.get("target_eid", event.data.get("eid"))
        try:
            target_eid = int(target_eid)
        except (TypeError, ValueError):
            return
        self._drop(target_eid)
        for eid, state in tuple(self.sim.ecs.get(NPCEmergencyState).items()):
            if _safe_int(getattr(state, "threat_eid", None), -1) == target_eid:
                self._drop(eid)

    def on_npc_intent_changed(self, event):
        intent = str(event.data.get("intent", "") or "").strip().lower()
        if intent not in {"protecting", "chasing"}:
            return
        try:
            npc_eid = int(event.data.get("npc_eid"))
            target_eid = int(event.data.get("target_eid"))
        except (TypeError, ValueError):
            return
        target_ai = self.sim.ecs.get(AI).get(target_eid)
        reciprocal = bool(
            target_ai is not None
            and _safe_int(getattr(target_ai, "target_eid", None), -1) == npc_eid
            and str(getattr(target_ai, "state", "") or "").strip().lower() in {"protecting", "chasing"}
        )
        if not reciprocal:
            return
        self._begin(npc_eid, target_eid)
        self._begin(target_eid, npc_eid)

    def on_entity_damaged(self, event):
        try:
            source_eid = int(event.data.get("source_eid"))
            target_eid = int(event.data.get("target_eid"))
            damage = int(event.data.get("damage", 0) or 0)
        except (TypeError, ValueError):
            return
        if damage <= 0 or source_eid == target_eid:
            return
        self._begin(target_eid, source_eid, damage=damage)

    def _fight_back(self, eid, state, ai, actor_pos, threat_pos, now):
        clear_self_protection_action(self.sim, eid)
        target = (int(threat_pos.x), int(threat_pos.y), int(threat_pos.z))
        ai.state = "protecting"
        ai.target = target
        ai.target_eid = int(state.threat_eid)
        will = self.sim.ecs.get(NPCWill).get(eid)
        if will is not None:
            will.intent = "protecting"
            will.score = max(82.0, float(getattr(will, "score", 0.0) or 0.0))
            will.target = target
            will.target_eid = int(state.threat_eid)
            will.last_tick = now
        if now >= _safe_int(getattr(state, "force_attack_after_tick", now), now):
            ai.force_attack_reason = "emergency_trapped_self_defense"
            ai.force_attack_until_tick = now + EMERGENCY_FORCE_ATTACK_TICKS
            state.force_attack_after_tick = now + EMERGENCY_FORCE_ATTACK_TICKS
        state.response = "fight"

    def update(self):
        now = _safe_int(getattr(self.sim, "tick", 0))
        positions = self.sim.ecs.get(Position)
        ais = self.sim.ecs.get(AI)
        vitalities = self.sim.ecs.get(Vitality)
        suppressions = self.sim.ecs.get(SuppressionState)

        for eid, state in tuple(self.sim.ecs.get(NPCEmergencyState).items()):
            if state is None or not bool(getattr(state, "active", False)):
                self._drop(eid)
                continue
            ai = ais.get(eid)
            actor_pos = positions.get(eid)
            threat_eid = getattr(state, "threat_eid", None)
            threat_pos = positions.get(threat_eid)
            vitality = vitalities.get(eid)
            threat_vitality = vitalities.get(threat_eid)
            if (
                ai is None
                or actor_pos is None
                or threat_pos is None
                or int(actor_pos.z) != int(threat_pos.z)
                or (vitality is not None and bool(getattr(vitality, "downed", False)))
                or (threat_vitality is not None and bool(getattr(threat_vitality, "downed", False)))
            ):
                self._drop(eid)
                continue
            suppression = suppressions.get(eid)
            if str(getattr(ai, "state", "") or "").strip().lower() == "surrendered" or (
                suppression is not None and bool(getattr(suppression, "surrendered", False))
            ):
                state.response = "surrender"
                self._drop(eid)
                continue

            threat_ai = ais.get(threat_eid)
            reciprocal = bool(
                threat_ai is not None
                and _safe_int(getattr(threat_ai, "target_eid", None), -1) == int(eid)
                and str(getattr(threat_ai, "state", "") or "").strip().lower() in {"protecting", "chasing"}
            )
            if now > _safe_int(getattr(state, "expires_tick", now), now) and not reciprocal:
                self._drop(eid)
                continue
            if reciprocal:
                state.expires_tick = max(
                    _safe_int(getattr(state, "expires_tick", now), now),
                    now + EMERGENCY_STALE_TICKS,
                )

            distance = _distance(actor_pos, threat_pos)
            if distance is None:
                self._drop(eid)
                continue
            if distance >= EMERGENCY_SAFE_DISTANCE and now - _safe_int(state.last_damage_tick) >= 8 and not reciprocal:
                state.response = "escaped"
                self._drop(eid)
                continue

            action = active_self_protection_action(self.sim, eid, current_tick=now)
            action_name = str((action or {}).get("action", "") or "").strip().lower()
            if action_name in TEMPORARY_HOLD_ACTIONS:
                state.response = action_name
                continue

            current_position = (int(actor_pos.x), int(actor_pos.y), int(actor_pos.z))
            previous_distance = getattr(state, "last_threat_distance", None)
            if previous_distance is None or int(distance) > int(previous_distance):
                state.last_safer_tick = now
            state.last_position = current_position
            state.last_threat_distance = int(distance)

            ai_state = str(getattr(ai, "state", "") or "").strip().lower()
            target = getattr(ai, "target", None)
            escape_is_credible = False
            if ai_state == "seeking_safety" and isinstance(target, (tuple, list)) and len(target) >= 3:
                try:
                    target_distance = max(
                        abs(int(target[0]) - int(threat_pos.x)),
                        abs(int(target[1]) - int(threat_pos.y)),
                    )
                    escape_is_credible = (
                        int(target[2]) == int(actor_pos.z)
                        and (int(target[0]), int(target[1])) != (int(actor_pos.x), int(actor_pos.y))
                        and target_distance > int(distance)
                    )
                except (TypeError, ValueError):
                    escape_is_credible = False
            if escape_is_credible and now - _safe_int(state.last_safer_tick, now) <= EMERGENCY_ESCAPE_GRACE_TICKS:
                ai.target_eid = int(threat_eid)
                state.response = "escape"
                continue

            self._fight_back(eid, state, ai, actor_pos, threat_pos, now)
