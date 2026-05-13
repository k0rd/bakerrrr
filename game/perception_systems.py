"""Perception, stealth, and combat-pacing systems extracted from ``game.systems``."""

from engine.events import Event
from engine.systems import System
from engine.visibility import update_player_visibility as _update_player_visibility
from game.lighting import update_lighting_state as _update_lighting_state
from game.components import AI, CoverState, NoiseProfile, PlayerModeState, Position
from game.skills import actor_skill as _actor_skill
from game.system_support.actor_runtime import _detail_tick_allowed, _entity_is_downed
from game.system_support.combat_targeting_runtime import QUIET_NOISE_CAUSES
from game.system_support.combat_pacing_runtime import _combat_overlay_state
from game.system_support.cover_runtime import (
    THREAT_STATES,
    _effective_cover_value,
    _is_cover_state_valid,
    _threat_positions_for_entity,
)
from game.system_support.entity_naming import _entity_display_name
from game.system_support.interaction_ordering import _manhattan
from game.system_support.stealth_runtime import _player_hidden_status


class CoverSystem(System):

    def __init__(self, sim):
        super().__init__(sim)
        self.runs_without_turn = True

    def update(self):
        covers = self.sim.ecs.get(CoverState)
        positions = self.sim.ecs.get(Position)
        ais = self.sim.ecs.get(AI)

        for eid, cover in covers.items():
            pos = positions.get(eid)
            if not pos:
                continue

            # Skip deep simulation work on coarse chunks, but keep player responsive.
            if eid in ais and not _detail_tick_allowed(self.sim, pos, eid, coarse_divisor=2):
                continue

            if cover.active and not _is_cover_state_valid(self.sim, pos, cover):
                cover.clear(tick=self.sim.tick)
                self.sim.emit(Event(
                    "cover_left",
                    eid=eid,
                    reason="displaced",
                ))

            threats = _threat_positions_for_entity(self.sim, eid, pos, radius=10)
            cover.threat_count = len(threats)
            cover.nearest_threat_dist = min((dist for _, dist, _, _ in threats), default=None)

            previous = cover.exposure
            if not threats:
                cover.exposure = 0.2 if cover.active else 1.0
            elif not cover.active:
                cover.exposure = 1.0
            else:
                worst = 0.0
                for _, _, tx, ty in threats:
                    value = _effective_cover_value(cover, pos.x, pos.y, tx, ty)
                    threat_exposure = max(0.05, 1.0 - value)
                    worst = max(worst, threat_exposure)
                cover.exposure = max(0.05, min(1.0, worst))

            if abs(cover.exposure - previous) >= 0.2:
                self.sim.emit(Event(
                    "cover_exposure_changed",
                    eid=eid,
                    exposure=round(cover.exposure, 2),
                    threat_count=cover.threat_count,
                    nearest_threat_dist=cover.nearest_threat_dist,
                ))


class CombatPacingSystem(System):

    def __init__(
        self,
        sim,
        player_eid,
        engage_radius=10,
        danger_radius=6,
        calm_frames_to_exit=12,
        exposure_threshold=0.58,
    ):
        super().__init__(sim)
        self.player_eid = player_eid
        self.engage_radius = int(max(3, engage_radius))
        self.danger_radius = int(max(2, danger_radius))
        self.calm_frames_to_exit = int(max(1, calm_frames_to_exit))
        self.exposure_threshold = float(max(0.2, min(1.0, exposure_threshold)))
        self.calm_frames = 0
        self.runs_without_turn = True

        _combat_overlay_state(self.sim)

    def _threat_snapshot(self):
        positions = self.sim.ecs.get(Position)
        ais = self.sim.ecs.get(AI)
        player_pos = positions.get(self.player_eid)
        if not player_pos:
            return {
                "count": 0,
                "nearest_dist": None,
            }

        threat_count = 0
        nearest = None
        for eid, ai in ais.items():
            if eid == self.player_eid:
                continue
            if ai.state not in THREAT_STATES:
                continue
            if _entity_is_downed(self.sim, eid):
                continue

            pos = positions.get(eid)
            if not pos or pos.z != player_pos.z:
                continue

            dist = _manhattan(player_pos.x, player_pos.y, pos.x, pos.y)
            if dist > self.engage_radius:
                continue

            threat_count += 1
            if nearest is None or dist < nearest:
                nearest = dist

        return {
            "count": threat_count,
            "nearest_dist": nearest,
        }

    def update(self):
        snapshot = self._threat_snapshot()
        threat_count = snapshot["count"]
        nearest = snapshot["nearest_dist"]

        overlay = _combat_overlay_state(self.sim)
        overlay["threat_count"] = threat_count
        overlay["nearest_threat_dist"] = nearest
        manual_pacing = bool(overlay.get("manual_pacing"))
        player_cover = self.sim.ecs.get(CoverState).get(self.player_eid)
        player_exposure = float(player_cover.exposure) if player_cover else 1.0
        overlay["player_exposure"] = round(max(0.0, min(1.0, player_exposure)), 2)

        should_engage = False
        exposed = player_exposure >= self.exposure_threshold
        retain_exposed = player_exposure >= max(0.35, self.exposure_threshold - 0.12)
        if threat_count > 0:
            if nearest is None:
                should_engage = exposed
            elif nearest <= self.danger_radius:
                should_engage = exposed
            elif overlay["active"] and nearest <= self.engage_radius and retain_exposed:
                # Hysteresis: once engaged, stay in turn mode while threats remain nearby.
                should_engage = True

        if should_engage:
            self.calm_frames = 0
            if not overlay["active"]:
                overlay["active"] = True
                self.sim.turn_based = True
                self.sim.emit(Event(
                    "combat_overlay_entered",
                    player_eid=self.player_eid,
                    threat_count=threat_count,
                    nearest_threat_dist=nearest,
                ))
            return

        if overlay["active"]:
            self.calm_frames += 1
            if self.calm_frames >= self.calm_frames_to_exit:
                overlay["active"] = False
                self.calm_frames = 0
                self.sim.emit(Event(
                    "combat_overlay_exited",
                    player_eid=self.player_eid,
                ))
            if overlay["active"] or manual_pacing:
                self.sim.turn_based = True
                return

        if manual_pacing:
            self.sim.turn_based = True
            return

        self.sim.turn_based = False


class NoiseSystem(System):

    def __init__(self, sim):
        super().__init__(sim)
        self.sim.events.subscribe("player_action", self.on_player_action)

    def on_player_action(self, event):
        eid = event.data.get("eid")
        action = event.data.get("action")

        if action not in QUIET_NOISE_CAUSES:
            return

        positions = self.sim.ecs.get(Position)
        pos = positions.get(eid)
        if not pos:
            return

        profiles = self.sim.ecs.get(NoiseProfile)
        profile = profiles.get(eid)
        radius = profile.move_radius if profile else 5
        mode_state = self.sim.ecs.get(PlayerModeState).get(eid)

        if action == "wait":
            radius = 1
        elif action == "cover_hop":
            radius += 1
        elif action == "floor_change":
            radius += 1
        elif action == "interact":
            radius = max(2, radius - 1)
        elif action == "toggle_door_lock":
            radius = max(2, radius - 1)
        elif action == "pickup_item":
            radius = max(1, radius - 3)
        elif action == "drop_item":
            radius = max(1, radius - 4)
        elif action == "use_item":
            radius = max(1, radius - 2)
        elif action in {"banking", "insurance", "trade_buy", "trade_sell"}:
            radius = 1
        elif action in {"overworld_travel", "zoom_overworld", "zoom_city_enter"}:
            radius = 1

        if mode_state and mode_state.sneak and action in {
            "move",
            "cover_hop",
            "floor_change",
            "wait",
            "interact",
            "toggle_door_lock",
            "pickup_item",
            "drop_item",
            "use_item",
        }:
            radius = max(1, int(round(float(radius) * 0.5)))

        self.sim.emit(Event(
            "noise",
            source_eid=eid,
            x=pos.x,
            y=pos.y,
            z=pos.z,
            radius=radius,
            cause=action,
        ))


class LightingSystem(System):

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.runs_without_turn = True
        self.last_phase = None

    def update(self):
        player_pos = self.sim.ecs.get(Position).get(self.player_eid)
        state = _update_lighting_state(self.sim, player_pos=player_pos)
        phase = str(state.get("phase", "day")).strip().lower() or "day"

        if not self.last_phase:
            self.last_phase = phase
            return
        if phase == self.last_phase:
            return

        previous_phase = self.last_phase
        self.last_phase = phase
        self.sim.emit(Event(
            "lighting_phase_changed",
            eid=self.player_eid,
            phase=phase,
            previous_phase=previous_phase,
            hour=int(state.get("hour", 0)),
            minute=int(state.get("minute", 0)),
            time_label=str(state.get("time_label", "00:00")),
            outside_ambient=float(state.get("outside_ambient", 1.0)),
            player_inside=bool(state.get("player_inside", False)),
            player_ambient=float(state.get("player_ambient", state.get("outside_ambient", 1.0))),
        ))


class VisibilitySystem(System):

    def __init__(self, sim, player_eid, default_player_radius=11):
        super().__init__(sim)
        self.player_eid = player_eid
        self.default_player_radius = max(4, int(default_player_radius))
        self.runs_without_turn = True

    def _player_radius(self):
        traits = getattr(self.sim, "world_traits", {})
        visibility = traits.get("visibility", {}) if isinstance(traits, dict) else {}
        if not isinstance(visibility, dict):
            visibility = {}
        try:
            radius = int(visibility.get("player_radius", self.default_player_radius))
        except (TypeError, ValueError):
            radius = self.default_player_radius

        # Scale visibility range by ambient light: darker means shorter sight.
        lighting = traits.get("lighting", {}) if isinstance(traits, dict) else {}
        try:
            ambient = float(lighting.get("player_ambient", 1.0))
        except (TypeError, ValueError):
            ambient = 1.0
        ambient = max(0.0, min(1.0, ambient))

        # Apply a small bonus for player perception skill so high-skill players can still see farther in dim light.
        perception = _actor_skill(self.sim, self.player_eid, "perception")
        try:
            perception = float(perception)
        except (TypeError, ValueError):
            perception = 5.0
        # 5 is baseline; higher gives up to +25%, lower down to -15%, but keep within reasonable bounds.
        perception_scale = 0.9 + ((perception - 5.0) / 40.0)
        perception_scale = max(0.75, min(1.25, perception_scale))

        # Minimum visibility is never below a small baseline to avoid full blindness.
        scale = (0.5 + (ambient * 0.5)) * perception_scale
        radius = int(round(radius * scale))

        return max(4, min(24, radius))

    def _state(self):
        state = getattr(self.sim, "visibility_state", None)
        if isinstance(state, dict):
            return state

        state = {
            "tick": -1,
            "observers": {},
            "player_eid": None,
            "player_origin": None,
            "player_radius": 0,
            "player_visible": set(),
            "player_explored": set(),
        }
        self.sim.visibility_state = state
        return state

    def update(self):
        state = self._state()
        state["player_eid"] = self.player_eid

        positions = self.sim.ecs.get(Position)
        pos = positions.get(self.player_eid)
        if not pos or str(getattr(self.sim, "zoom_mode", "city")).strip().lower() == "overworld":
            state["tick"] = int(getattr(self.sim, "tick", 0))
            state["observers"] = {}
            state["player_origin"] = None
            state["player_radius"] = 0
            state["player_visible"] = set()
            return

        _update_player_visibility(
            self.sim,
            player_eid=self.player_eid,
            x=pos.x,
            y=pos.y,
            z=pos.z,
            radius=self._player_radius(),
        )


class StealthSystem(System):

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid

    def update(self):
        modes = self.sim.ecs.get(PlayerModeState).get(self.player_eid)
        pos = self.sim.ecs.get(Position).get(self.player_eid)
        if not modes or not pos:
            self.sim.player_stealth_state = {
                "hidden": False,
                "witness_count": 0,
                "witness_labels": (),
            }
            return

        hidden, watchers = _player_hidden_status(
            self.sim,
            self.player_eid,
            pos.x,
            pos.y,
            pos.z,
        )
        witness_labels = tuple(
            _entity_display_name(self.sim, watcher_eid, title_case=False)
            for watcher_eid in watchers[:2]
        )
        self.sim.player_stealth_state = {
            "hidden": bool(hidden),
            "witness_count": len(watchers),
            "witness_labels": witness_labels,
        }
        if bool(modes.hidden) == bool(hidden):
            return

        modes.set_hidden(hidden, tick=self.sim.tick)
        self.sim.emit(Event(
            "player_hidden_changed",
            eid=self.player_eid,
            active=bool(hidden),
            witness_count=len(watchers),
            witnesses=tuple(watchers[:4]),
            witness_labels=witness_labels,
            reason="unseen" if hidden else "observed",
            x=pos.x,
            y=pos.y,
            z=pos.z,
        ))
