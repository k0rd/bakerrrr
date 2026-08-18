"""Player movement, cover, and stakeout runtime."""

from collections import deque

from engine.events import Event

from game.components import AI, Collider, CoverState, DoorWaitState, NPCWill, PlayerModeState, Position, Vitality
from game.movement_runtime import _can_step_transition_for, try_move_entity
from game.opportunities import opportunity_intel_for_observer, reveal_opportunity_to_observer
from game.property_runtime import (
    property_covering as _property_covering,
    property_power_cut_active as _property_power_cut_active,
)
from game.system_support.cover_runtime import _effective_cover_value, _threat_positions_for_entity
from game.system_support.interaction_ordering import _direction_step
from game.system_support.player_feedback import _log_player_feedback


_BUMP_YIELD_BLOCKING_STATES = frozenset({
    "chasing",
    "ejecting_target",
    "protecting",
    "warning",
})
_BUMP_ANCHORED_STATES = frozenset({
    "playing_poker",
})


def _manhattan(ax, ay, bx, by):
    return abs(int(ax) - int(bx)) + abs(int(ay) - int(by))


def _same_eid(a, b):
    try:
        return int(a) == int(b)
    except (TypeError, ValueError):
        return a == b


def _blocked_entity_from_reason(reason):
    text = str(reason or "").strip().lower()
    if not text.startswith("blocked_entity:"):
        return None
    try:
        return int(text.split(":", 1)[1])
    except (TypeError, ValueError, IndexError):
        return None


def _active_door_wait_state(sim, eid):
    state = sim.ecs.get(DoorWaitState).get(eid)
    if not isinstance(state, DoorWaitState):
        return None
    is_expired = getattr(state, "is_expired", None)
    if callable(is_expired) and is_expired(getattr(sim, "tick", 0)):
        return None
    return state


def _npc_should_yield_to_bump(sim, npc_eid, player_eid):
    ai = sim.ecs.get(AI).get(npc_eid)
    if ai is None:
        return False
    if str(getattr(ai, "role", "") or "").strip().lower() == "wildlife":
        return False
    collider = sim.ecs.get(Collider).get(npc_eid)
    if collider is None or not bool(getattr(collider, "blocks", False)):
        return False
    vitality = sim.ecs.get(Vitality).get(npc_eid)
    if vitality is not None and bool(getattr(vitality, "downed", False)):
        return False
    if _active_door_wait_state(sim, npc_eid) is not None:
        return False

    state = str(getattr(ai, "state", "") or "").strip().lower()
    if state in _BUMP_ANCHORED_STATES:
        return False
    if state in _BUMP_YIELD_BLOCKING_STATES and _same_eid(getattr(ai, "target_eid", None), player_eid):
        return False
    will = sim.ecs.get(NPCWill).get(npc_eid)
    intent = str(getattr(will, "intent", "") or "").strip().lower() if will is not None else ""
    if intent in _BUMP_ANCHORED_STATES:
        return False
    if intent in _BUMP_YIELD_BLOCKING_STATES and _same_eid(getattr(will, "target_eid", None), player_eid):
        return False
    return True


def _bump_yield_candidates(player_x, player_y, npc_x, npc_y, dx, dy):
    current_dist = _manhattan(npc_x, npc_y, player_x, player_y)
    candidates = []
    if int(dx) != 0:
        candidates.extend([
            (int(npc_x) + int(dx), int(npc_y)),
            (int(npc_x), int(npc_y) - 1),
            (int(npc_x), int(npc_y) + 1),
        ])
    elif int(dy) != 0:
        candidates.extend([
            (int(npc_x), int(npc_y) + int(dy)),
            (int(npc_x) - 1, int(npc_y)),
            (int(npc_x) + 1, int(npc_y)),
        ])
    for candidate_x, candidate_y in candidates:
        if _manhattan(candidate_x, candidate_y, player_x, player_y) > current_dist:
            yield candidate_x, candidate_y


class PlayerMovementRuntime:
    def __init__(
        self,
        action_system,
        *,
        best_cover_candidate,
        emit_move_access_events,
        stakeout_progress_snapshot,
        stakeout_reveal_interval,
        stakeout_max_reveals,
    ):
        self.action_system = action_system
        self.sim = action_system.sim
        self._best_cover_candidate = best_cover_candidate
        self._emit_move_access_events = emit_move_access_events
        self._stakeout_progress_snapshot = stakeout_progress_snapshot
        self._stakeout_reveal_interval = max(1, int(stakeout_reveal_interval))
        self._stakeout_max_reveals = max(1, int(stakeout_max_reveals))

    def _cover_state_for(self, eid):
        return self.sim.ecs.get(CoverState).get(eid)

    def _mode_state_for(self, eid):
        return self.sim.ecs.get(PlayerModeState).get(eid)

    def _try_bump_yield(self, eid, pos, *, dx, dy, blocked_reason):
        blocker_eid = _blocked_entity_from_reason(blocked_reason)
        if blocker_eid is None or blocker_eid == eid:
            return False
        blocker_pos = self.sim.ecs.get(Position).get(blocker_eid)
        if blocker_pos is None or int(blocker_pos.z) != int(pos.z):
            return False
        if _manhattan(pos.x, pos.y, blocker_pos.x, blocker_pos.y) != 1:
            return False
        if not _npc_should_yield_to_bump(self.sim, blocker_eid, eid):
            return False

        old_x = int(blocker_pos.x)
        old_y = int(blocker_pos.y)
        old_z = int(blocker_pos.z)
        for candidate_x, candidate_y in _bump_yield_candidates(pos.x, pos.y, old_x, old_y, dx, dy):
            moved, _reason = try_move_entity(
                self.sim,
                eid=blocker_eid,
                new_x=candidate_x,
                new_y=candidate_y,
                new_z=old_z,
                reason="player_bump_yield",
            )
            if moved:
                self.sim.emit(Event(
                    "npc_yielded_to_bump",
                    player_eid=eid,
                    npc_eid=blocker_eid,
                    old_x=old_x,
                    old_y=old_y,
                    old_z=old_z,
                    x=candidate_x,
                    y=candidate_y,
                    z=old_z,
                ))
                return True
        return False

    def set_sneak_mode(self, eid, active, reason="manual"):
        modes = self._mode_state_for(eid)
        if not modes:
            return False

        active = bool(active)
        changed = bool(modes.sneak) != active
        hidden_changed = bool(modes.hidden) and not active
        if not changed and not hidden_changed:
            return False

        was_hidden = bool(modes.hidden)
        modes.sneak = active
        if not active:
            modes.hidden = False
        modes.last_changed_tick = int(self.sim.tick)

        self.sim.emit(Event(
            "player_mode_toggled",
            eid=eid,
            mode="sneak",
            active=modes.sneak,
            hidden=modes.hidden,
            reason=reason,
        ))
        if was_hidden and not modes.hidden:
            self.sim.emit(Event(
                "player_hidden_changed",
                eid=eid,
                active=False,
                witness_count=0,
                witnesses=(),
                reason="mode_off",
            ))
        return True

    def clear_cover(self, eid, reason):
        cover = self._cover_state_for(eid)
        if not cover or not cover.active:
            return

        cover.clear(tick=self.sim.tick)
        self.sim.emit(Event(
            "cover_left",
            eid=eid,
            reason=reason,
        ))

    def _engage_cover_candidate(self, eid, candidate, tick=None, event_type="cover_taken"):
        cover = self._cover_state_for(eid)
        if not cover or not candidate:
            return False

        if tick is None:
            tick = self.sim.tick

        cover.engage(
            cover_kind=candidate["cover_kind"],
            cover_value=candidate["cover_value"],
            source=candidate["source"],
            source_kind=candidate["source_kind"],
            block_dir=candidate.get("block_dir"),
            tick=tick,
        )
        self.sim.emit(Event(
            event_type,
            eid=eid,
            cover_kind=cover.cover_kind,
            cover_value=round(cover.cover_value, 2),
            source=cover.source,
            source_kind=cover.source_kind,
            block_dir=cover.block_dir,
            property_id=candidate.get("property_id"),
        ))
        return True

    def _cover_matches_candidate(self, cover, candidate):
        if not cover or not cover.active or not candidate:
            return False

        current_property_id = None
        if cover.source_kind == "property" and cover.source:
            sx, sy, sz = cover.source
            prop = self.sim.property_at(sx, sy, sz)
            if prop:
                current_property_id = prop.get("id")

        return (
            cover.cover_kind == candidate["cover_kind"]
            and round(float(cover.cover_value), 2) == round(float(candidate["cover_value"]), 2)
            and cover.source == candidate["source"]
            and cover.source_kind == candidate["source_kind"]
            and cover.block_dir == candidate.get("block_dir")
            and current_property_id == candidate.get("property_id")
        )

    def handle_toggle_cover(self, eid, pos):
        cover = self._cover_state_for(eid)
        if not cover:
            self.sim.emit(Event("cover_blocked", eid=eid, reason="missing_cover_state"))
            return

        if cover.active:
            cover.clear(tick=self.sim.tick)
            self.sim.emit(Event("cover_left", eid=eid, reason="manual"))
            return

        candidate = self._best_cover_candidate(self.sim, pos.x, pos.y, pos.z)
        if not candidate:
            self.sim.emit(Event("cover_blocked", eid=eid, reason="no_cover_object"))
            return

        self._engage_cover_candidate(eid, candidate, tick=self.sim.tick, event_type="cover_taken")

    def _cover_effect_for_candidate(self, candidate, entity_x, entity_y, threat_x, threat_y):
        if not candidate:
            return 0.0
        base = float(max(0.0, min(0.95, candidate.get("cover_value", 0.0))))
        block_dir = candidate.get("block_dir")
        if not block_dir:
            return base * 0.55
        threat_dir = _direction_step(entity_x, entity_y, threat_x, threat_y)
        if threat_dir == tuple(block_dir):
            return base
        if threat_dir == (-int(block_dir[0]), -int(block_dir[1])):
            return base * 0.2
        return base * 0.35

    def _cover_hop_options(self, eid, pos, max_steps=4):
        max_steps = max(1, int(max_steps))
        cover = self._cover_state_for(eid)
        threats = _threat_positions_for_entity(self.sim, eid, pos, radius=12)
        nearest_threat = min(threats, key=lambda row: row[1]) if threats else None
        current_effect = None
        if cover and cover.active and nearest_threat:
            _, _, tx, ty = nearest_threat
            current_effect = _effective_cover_value(cover, pos.x, pos.y, tx, ty)

        frontier = deque([(int(pos.x), int(pos.y), tuple())])
        visited = {(int(pos.x), int(pos.y))}
        options = []
        steps = (
            (1, 0),
            (-1, 0),
            (0, 1),
            (0, -1),
            (1, 1),
            (1, -1),
            (-1, 1),
            (-1, -1),
        )

        while frontier:
            cx, cy, path = frontier.popleft()
            if len(path) >= max_steps:
                continue

            for dx, dy in steps:
                nx = int(cx + dx)
                ny = int(cy + dy)
                if (nx, ny) in visited:
                    continue
                can_step, _ = _can_step_transition_for(
                    self.sim,
                    moving_eid=eid,
                    from_x=int(cx),
                    from_y=int(cy),
                    to_x=nx,
                    to_y=ny,
                    z=int(pos.z),
                )
                if not can_step:
                    continue
                visited.add((nx, ny))
                new_path = path + ((nx, ny),)
                frontier.append((nx, ny, new_path))

                candidate = self._best_cover_candidate(self.sim, nx, ny, pos.z)
                if not candidate:
                    continue
                if cover and cover.active and self._cover_matches_candidate(cover, candidate):
                    continue

                distance = len(new_path)
                score = float(candidate.get("cover_value", 0.0)) * 100.0
                score -= float(distance) * 7.0
                if nearest_threat:
                    _, _, tx, ty = nearest_threat
                    predicted = self._cover_effect_for_candidate(
                        candidate,
                        entity_x=nx,
                        entity_y=ny,
                        threat_x=tx,
                        threat_y=ty,
                    )
                    score += predicted * 90.0
                    if current_effect is not None:
                        score += (predicted - float(current_effect)) * 120.0
                if cover and cover.active and cover.block_dir and candidate.get("block_dir"):
                    if tuple(cover.block_dir) != tuple(candidate.get("block_dir")):
                        score += 5.0

                options.append({
                    "path": new_path,
                    "candidate": candidate,
                    "distance": distance,
                    "score": score,
                    "x": nx,
                    "y": ny,
                })

        options.sort(key=lambda row: (-float(row["score"]), int(row["distance"])))
        return options

    def handle_cover_hop(self, eid, pos):
        cover = self._cover_state_for(eid)
        if not cover or not cover.active:
            self.sim.emit(Event("cover_blocked", eid=eid, reason="cover_hop_requires_cover"))
            return

        options = self._cover_hop_options(eid, pos, max_steps=4)
        if not options:
            self.sim.emit(Event("cover_blocked", eid=eid, reason="no_cover_hop_target"))
            return

        best = options[0]
        path = list(best.get("path", ()))
        if not path:
            self.sim.emit(Event("cover_blocked", eid=eid, reason="no_cover_hop_target"))
            return

        start_x = int(pos.x)
        start_y = int(pos.y)
        start_z = int(pos.z)
        for step_x, step_y in path:
            moved, reason = try_move_entity(
                self.sim,
                eid=eid,
                new_x=int(step_x),
                new_y=int(step_y),
                new_z=start_z,
                reason="cover_hop",
            )
            if not moved:
                blocked_prop = (
                    self.sim.property_at(int(step_x), int(step_y), int(start_z))
                    or _property_covering(self.sim, int(step_x), int(step_y), int(start_z))
                )
                self.sim.emit(Event(
                    "cover_blocked",
                    eid=eid,
                    reason="cover_hop_path_blocked",
                    block_reason=reason,
                    block_x=int(step_x),
                    block_y=int(step_y),
                    block_z=int(start_z),
                    property_id=(blocked_prop or {}).get("id"),
                ))
                return

        new_pos = self.sim.ecs.get(Position).get(eid)
        if not new_pos:
            self.sim.emit(Event("cover_blocked", eid=eid, reason="cover_hop_path_blocked"))
            return

        candidate = best.get("candidate") or self._best_cover_candidate(self.sim, new_pos.x, new_pos.y, new_pos.z)
        if not candidate:
            self.clear_cover(eid, reason="displaced")
            self.sim.emit(Event("cover_blocked", eid=eid, reason="no_cover_object"))
            return

        self._engage_cover_candidate(eid, candidate, tick=self.sim.tick, event_type="cover_shifted")
        self.sim.emit(Event(
            "cover_hopped",
            eid=eid,
            from_x=start_x,
            from_y=start_y,
            to_x=int(new_pos.x),
            to_y=int(new_pos.y),
            z=int(new_pos.z),
            steps=len(path),
            cover_kind=str(candidate.get("cover_kind", "cover")),
            cover_value=float(candidate.get("cover_value", 0.0)),
            source_kind=str(candidate.get("source_kind", "cover")),
            block_dir=candidate.get("block_dir"),
            property_id=candidate.get("property_id"),
        ))
        self.emit_move_access_offense(
            eid=eid,
            action="cover_hop",
            origin_x=start_x,
            origin_y=start_y,
            origin_z=start_z,
            target_x=int(new_pos.x),
            target_y=int(new_pos.y),
            target_z=int(new_pos.z),
        )

    def emit_move_access_offense(
        self,
        *,
        eid,
        action,
        origin_x,
        origin_y,
        origin_z,
        target_x,
        target_y,
        target_z,
    ):
        self._emit_move_access_events(
            self.sim,
            eid=eid,
            action=action,
            origin_x=origin_x,
            origin_y=origin_y,
            origin_z=origin_z,
            target_x=target_x,
            target_y=target_y,
            target_z=target_z,
            emit_clear_offense=True,
        )

    def refresh_cover_after_move(self, eid, pos, had_cover=False):
        cover = self._cover_state_for(eid)
        if not had_cover:
            self.clear_cover(eid, reason="moved")
            return

        if not pos:
            self.clear_cover(eid, reason="moved")
            return

        candidate = self._best_cover_candidate(self.sim, pos.x, pos.y, pos.z)
        if candidate:
            if self._cover_matches_candidate(cover, candidate):
                cover.engage(
                    cover_kind=candidate["cover_kind"],
                    cover_value=candidate["cover_value"],
                    source=candidate["source"],
                    source_kind=candidate["source_kind"],
                    block_dir=candidate.get("block_dir"),
                    tick=self.sim.tick,
                )
                return
            self._engage_cover_candidate(eid, candidate, tick=self.sim.tick, event_type="cover_shifted")
            return

        self.clear_cover(eid, reason="moved")

    def clear_stakeout(self, eid=None, *, reason=""):
        state = getattr(self.sim, "stakeout_state", None)
        if not isinstance(state, dict):
            self.sim.stakeout_state = None
            return
        prop_id = str(state.get("prop_id", "")).strip()
        prop = self.sim.properties.get(prop_id) if prop_id else None
        prop_name = str((prop or {}).get("name", prop_id or "target site")).strip() or "target site"
        had_progress = (
            int(state.get("ticks", 0) or 0) > 0
            or int(state.get("reveals_done", 0) or 0) > 0
        )
        self.sim.stakeout_state = None
        if had_progress and eid is not None:
            self.sim.emit(Event(
                "stakeout_ended",
                eid=eid,
                property_id=prop_id,
                property_name=prop_name,
                reason=str(reason or "").strip().lower() or "ended",
            ))

    def _stakeout_reveal_intel(self, eid, prop_id):
        active_opps = list(self.action_system._active_property_opportunities(prop_id))
        if not active_opps:
            return False
        player_eid = getattr(self.sim, "player_eid", eid)
        best_opp = None
        best_conf = 2.0
        for opp in active_opps:
            oid = int(opp.get("id", 0))
            if oid <= 0:
                continue
            intel = opportunity_intel_for_observer(self.sim, player_eid, oid)
            if intel is None:
                best_opp = opp
                break
            conf = float(intel.get("confidence", 0.0))
            if conf < best_conf:
                best_conf = conf
                best_opp = opp
        if not best_opp:
            return False
        oid = int(best_opp.get("id", 0))
        intel = opportunity_intel_for_observer(self.sim, player_eid, oid)
        current_conf = float((intel or {}).get("confidence", 0.0))
        new_conf = min(0.88, current_conf + 0.08)
        if new_conf <= current_conf + 0.01:
            return False
        reveal_opportunity_to_observer(
            self.sim,
            player_eid,
            oid,
            awareness_state="confirmed" if new_conf >= 0.75 else "heard",
            confidence=new_conf,
            source="stakeout",
        )
        return True

    def try_advance_stakeout(self, eid, pos):
        snapshot = self._stakeout_progress_snapshot(self.sim, eid, pos, require_hidden=True)
        if not isinstance(snapshot, dict):
            stealth_state = getattr(self.sim, "player_stealth_state", {})
            hidden = bool(stealth_state.get("hidden")) if isinstance(stealth_state, dict) else False
            self.clear_stakeout(eid=eid, reason="left_site" if hidden else "observed")
            return
        prop_id = snapshot["property_id"]
        prop_name = snapshot["property_name"]
        state = getattr(self.sim, "stakeout_state", None)
        if not isinstance(state, dict) or state.get("prop_id") != prop_id:
            state = {
                "prop_id": prop_id,
                "start_tick": self.sim.tick,
                "ticks": 0,
                "reveals_done": 0,
            }
            self.sim.stakeout_state = state
            self.sim.emit(Event(
                "stakeout_started",
                eid=eid,
                property_id=prop_id,
                property_name=prop_name,
            ))
        if int(state.get("reveals_done", 0)) >= self._stakeout_max_reveals:
            return
        state["ticks"] = int(state.get("ticks", 0)) + 1
        if state["ticks"] % self._stakeout_reveal_interval != 0:
            return
        revealed = self._stakeout_reveal_intel(eid, prop_id)
        if revealed:
            state["reveals_done"] = int(state.get("reveals_done", 0)) + 1
            if state["reveals_done"] >= self._stakeout_max_reveals:
                _log_player_feedback(
                    self.sim,
                    f"You've thoroughly cased {prop_name}. Every angle mapped.",
                    kind="interaction",
                )
            else:
                _log_player_feedback(
                    self.sim,
                    (
                        f"Watching {prop_name}. Patterns are taking shape "
                        f"({int(state['reveals_done'])}/{self._stakeout_max_reveals})."
                    ),
                    kind="interaction",
                )
            self.sim.emit(Event(
                "stakeout_intel_gained",
                eid=eid,
                property_id=prop_id,
                property_name=prop_name,
                ticks=state["ticks"],
                reveals_done=state["reveals_done"],
            ))

    def handle_move_action(self, eid, pos, *, dx, dy):
        self.action_system._remember_player_interact_direction(eid, dx, dy)
        origin_x = pos.x
        origin_y = pos.y
        origin_z = pos.z
        target_x = pos.x + dx
        target_y = pos.y + dy
        cover = self._cover_state_for(eid)
        had_cover = bool(cover and cover.active)

        moved, reason = try_move_entity(
            self.sim,
            eid=eid,
            new_x=target_x,
            new_y=target_y,
            new_z=pos.z,
            reason="player_move",
        )

        if not moved:
            if self._try_bump_yield(eid, pos, dx=dx, dy=dy, blocked_reason=reason):
                moved, reason = try_move_entity(
                    self.sim,
                    eid=eid,
                    new_x=target_x,
                    new_y=target_y,
                    new_z=pos.z,
                    reason="player_move",
                )
                if moved:
                    target_x = pos.x
                    target_y = pos.y
        if not moved:
            blocked_prop = _property_covering(self.sim, target_x, target_y, pos.z)
            self.sim.emit(Event(
                "move_blocked",
                eid=eid,
                x=target_x,
                y=target_y,
                z=pos.z,
                reason=reason,
                property_id=(blocked_prop or {}).get("id"),
            ))
            return

        current_pos = self.sim.ecs.get(Position).get(eid)
        if current_pos is not None:
            self.sim.emit(Event(
                "player_moved",
                eid=eid,
                origin_x=origin_x,
                origin_y=origin_y,
                origin_z=origin_z,
                x=int(current_pos.x),
                y=int(current_pos.y),
                z=int(current_pos.z),
                dx=int(dx),
                dy=int(dy),
            ))

        self.clear_stakeout(eid=eid, reason="move")
        self.emit_move_access_offense(
            eid=eid,
            action="move",
            origin_x=origin_x,
            origin_y=origin_y,
            origin_z=origin_z,
            target_x=target_x,
            target_y=target_y,
            target_z=pos.z,
        )
        self.refresh_cover_after_move(
            eid,
            self.sim.ecs.get(Position).get(eid),
            had_cover=had_cover,
        )
        if current_pos is not None:
            visits = self.action_system._overworld_visit_state_for(eid)
            origin_chunk = self.sim.chunk_coords(origin_x, origin_y)
            current_chunk = self.sim.chunk_coords(current_pos.x, current_pos.y)
            origin_key = (int(origin_chunk[0]), int(origin_chunk[1]))
            current_key = (int(current_chunk[0]), int(current_chunk[1]))
            first_visit = current_key not in visits
            visits.add(origin_key)
            visits.add(current_key)
            # Overworld summaries describe chunks, not individual local steps.
            # Refresh only when this move establishes or crosses a chunk visit.
            if first_visit or current_key != origin_key:
                self.action_system._remember_overworld_chunk_memory(eid, current_key, source="visit")

    def handle_floor_change(self, eid, pos, *, dz, zoom_mode):
        if str(zoom_mode).lower() == "overworld":
            self.sim.emit(Event(
                "floor_change_blocked",
                eid=eid,
                reason="overworld_mode",
                x=pos.x,
                y=pos.y,
                z=pos.z,
                dz=dz,
            ))
            return

        floor_link = self.sim.tilemap.floor_transition(pos.x, pos.y, pos.z, dz)
        if not floor_link:
            self.sim.emit(Event(
                "floor_change_blocked",
                eid=eid,
                reason="no_transition",
                x=pos.x,
                y=pos.y,
                z=pos.z,
                dz=dz,
            ))
            return

        if str(floor_link.get("kind", "") or "").strip().lower() == "elevator":
            current_prop = self.sim.property_at(pos.x, pos.y, pos.z) or _property_covering(self.sim, pos.x, pos.y, pos.z)
            target_prop = self.sim.property_at(
                floor_link["x"],
                floor_link["y"],
                floor_link["z"],
            ) or _property_covering(
                self.sim,
                floor_link["x"],
                floor_link["y"],
                floor_link["z"],
            )
            if any(
                _property_power_cut_active(self.sim, prop)
                for prop in (current_prop, target_prop)
                if isinstance(prop, dict)
            ):
                self.sim.emit(Event(
                    "floor_change_blocked",
                    eid=eid,
                    reason="power_cut",
                    x=pos.x,
                    y=pos.y,
                    z=pos.z,
                    dz=dz,
                ))
                return

        old_z = pos.z
        moved, reason = try_move_entity(
            self.sim,
            eid=eid,
            new_x=floor_link["x"],
            new_y=floor_link["y"],
            new_z=floor_link["z"],
            reason=floor_link["kind"],
        )
        if not moved:
            self.sim.emit(Event(
                "floor_change_blocked",
                eid=eid,
                reason=reason,
                x=pos.x,
                y=pos.y,
                z=pos.z,
                dz=dz,
            ))
            return

        self.sim.emit(Event(
            "entity_changed_floor",
            eid=eid,
            x=pos.x,
            y=pos.y,
            from_z=old_z,
            to_z=floor_link["z"],
            kind=floor_link["kind"],
        ))
        self.action_system._emit_action_offense(
            eid=eid,
            action="floor_change",
            context="ordinary",
            x=pos.x,
            y=pos.y,
            z=floor_link["z"],
        )
        self.clear_cover(eid, reason="floor_change")

    def handle_wait_action(self, eid, pos):
        self.sim.emit(Event("entity_waited", eid=eid, x=pos.x, y=pos.y, z=pos.z))
        self.try_advance_stakeout(eid, pos)

    def handle_toggle_sneak_action(self, eid):
        mode_state = self._mode_state_for(eid)
        if not mode_state:
            return
        self.set_sneak_mode(eid, not mode_state.sneak, reason="manual")
