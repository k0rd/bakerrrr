"""Perception, stealth, and combat-pacing systems extracted from ``game.systems``."""

from engine.events import Event
from engine.systems import System
from engine.visibility import update_player_visibility as _update_player_visibility
from game.checks import crime_sensitivity as _crime_sensitivity, justice_level as _justice_level
from game.lighting import (
    glare_strength as _lighting_glare_strength,
    update_lighting_state as _update_lighting_state,
)
from game.components import (
    AI,
    CoverState,
    JusticeProfile,
    NPCMemory,
    NPCNeeds,
    NPCTraits,
    NoiseProfile,
    PlayerModeState,
    Position,
    SuppressionState,
    Vitality,
)
from game.property_access import evaluate_property_access as _evaluate_property_access
from game.property_runtime import (
    property_cover_intended as _property_cover_intended,
    property_covering as _property_covering,
    property_enclosing_structure as _property_enclosing_structure,
)
from game.skills import actor_skill as _actor_skill
from game.system_support.actor_runtime import _detail_tick_allowed, _entity_is_downed
from game.system_support.awareness_runtime import _watchers_for_position
from game.system_support.combat_targeting_runtime import (
    COMBAT_RELATION_AMBIENT,
    COMBAT_RELATION_DIRECT,
    QUIET_NOISE_CAUSES,
    _combat_relation_to_player,
    _entity_visible_to_player,
)
from game.system_support.combat_pacing_runtime import _combat_overlay_state
from game.system_support.cover_runtime import (
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
    RECENT_HIT_DAMAGE_KINDS = {"melee", "ballistic", "explosive"}

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
        self.sim.events.subscribe("entity_damaged", self.on_entity_damaged)

    @staticmethod
    def _int_or_none(value):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    def _clear_recent_hit_target(self, overlay=None):
        overlay = overlay if isinstance(overlay, dict) else _combat_overlay_state(self.sim)
        overlay["recent_hit_target"] = None
        overlay["pursuit_target_count"] = 0

    def _target_available_for_recent_hit_pacing(self, target_eid):
        if target_eid is None:
            return False
        if int(target_eid) == int(self.player_eid):
            return False
        if self.sim.ecs.get(AI).get(target_eid) is None:
            return False
        vitality = self.sim.ecs.get(Vitality).get(target_eid)
        if vitality is None:
            return False
        if int(getattr(vitality, "hp", 0) or 0) <= 0:
            return False
        if bool(getattr(vitality, "downed", False)):
            return False
        suppression = self.sim.ecs.get(SuppressionState).get(target_eid)
        if suppression and bool(getattr(suppression, "surrendered", False)):
            return False
        return True

    def _recent_hit_pursuit_target(self, player_pos, counted_eids):
        overlay = _combat_overlay_state(self.sim)
        record = overlay.get("recent_hit_target")
        if not isinstance(record, dict):
            self._clear_recent_hit_target(overlay)
            return None

        target_eid = self._int_or_none(record.get("target_eid"))
        if target_eid is None:
            self._clear_recent_hit_target(overlay)
            return None
        if target_eid in counted_eids:
            overlay["pursuit_target_count"] = 0
            return None
        if not self._target_available_for_recent_hit_pacing(target_eid):
            self._clear_recent_hit_target(overlay)
            return None

        positions = self.sim.ecs.get(Position)
        target_pos = positions.get(target_eid)
        if not player_pos or not target_pos or int(player_pos.z) != int(target_pos.z):
            self._clear_recent_hit_target(overlay)
            return None
        if not _entity_visible_to_player(self.sim, self.player_eid, target_eid):
            self._clear_recent_hit_target(overlay)
            return None

        return target_eid, target_pos

    def on_entity_damaged(self, event):
        source_eid = self._int_or_none(event.data.get("source_eid"))
        target_eid = self._int_or_none(event.data.get("target_eid"))
        if source_eid is None or target_eid is None:
            return
        if int(source_eid) != int(self.player_eid):
            return
        if int(target_eid) == int(self.player_eid):
            return
        try:
            damage = int(event.data.get("damage", 0) or 0)
        except (TypeError, ValueError):
            damage = 0
        if damage <= 0:
            return

        damage_kind = str(event.data.get("damage_kind", "") or "").strip().lower()
        if damage_kind not in self.RECENT_HIT_DAMAGE_KINDS:
            return
        if not self._target_available_for_recent_hit_pacing(target_eid):
            return

        target_pos = self.sim.ecs.get(Position).get(target_eid)
        if target_pos is None:
            return

        overlay = _combat_overlay_state(self.sim)
        overlay["recent_hit_target"] = {
            "target_eid": int(target_eid),
            "last_hit_tick": int(getattr(self.sim, "tick", 0) or 0),
            "damage_kind": damage_kind,
            "last_x": int(target_pos.x),
            "last_y": int(target_pos.y),
            "last_z": int(target_pos.z),
        }

    def _threat_snapshot(self):
        positions = self.sim.ecs.get(Position)
        ais = self.sim.ecs.get(AI)
        player_pos = positions.get(self.player_eid)
        if not player_pos:
            return {
                "count": 0,
                "direct_count": 0,
                "ambient_count": 0,
                "nearest_dist": None,
            }

        threat_count = 0
        direct_count = 0
        ambient_count = 0
        pursuit_count = 0
        nearest = None
        counted_eids = set()
        for eid, _ai in ais.items():
            if eid == self.player_eid:
                continue
            if _entity_is_downed(self.sim, eid):
                continue

            pos = positions.get(eid)
            if not pos or pos.z != player_pos.z:
                continue

            dist = _manhattan(player_pos.x, player_pos.y, pos.x, pos.y)
            if dist > self.engage_radius:
                continue

            if not _entity_visible_to_player(self.sim, self.player_eid, eid):
                continue

            relation = _combat_relation_to_player(self.sim, eid, player_eid=self.player_eid)
            if relation == COMBAT_RELATION_DIRECT:
                direct_count += 1
            elif relation == COMBAT_RELATION_AMBIENT:
                ambient_count += 1
            else:
                continue

            counted_eids.add(int(eid))
            threat_count += 1
            if nearest is None or dist < nearest:
                nearest = dist

        recent = self._recent_hit_pursuit_target(player_pos, counted_eids)
        if recent is not None:
            target_eid, target_pos = recent
            pursuit_count = 1
            threat_count += 1
            dist = _manhattan(player_pos.x, player_pos.y, target_pos.x, target_pos.y)
            if nearest is None or dist < nearest:
                nearest = dist

        return {
            "count": threat_count,
            "direct_count": direct_count,
            "ambient_count": ambient_count,
            "pursuit_count": pursuit_count,
            "nearest_dist": nearest,
        }

    def update(self):
        snapshot = self._threat_snapshot()
        threat_count = snapshot["count"]
        nearest = snapshot["nearest_dist"]

        overlay = _combat_overlay_state(self.sim)
        overlay["threat_count"] = threat_count
        overlay["direct_threat_count"] = snapshot.get("direct_count", 0)
        overlay["ambient_threat_count"] = snapshot.get("ambient_count", 0)
        overlay["pursuit_target_count"] = snapshot.get("pursuit_count", 0)
        overlay["nearest_threat_dist"] = nearest
        manual_pacing = bool(overlay.get("manual_pacing"))
        player_cover = self.sim.ecs.get(CoverState).get(self.player_eid)
        player_exposure = float(player_cover.exposure) if player_cover else 1.0
        overlay["player_exposure"] = round(max(0.0, min(1.0, player_exposure)), 2)

        should_engage = False
        exposed = player_exposure >= self.exposure_threshold
        retain_exposed = player_exposure >= max(0.35, self.exposure_threshold - 0.12)
        if int(snapshot.get("pursuit_count", 0) or 0) > 0:
            should_engage = True
        elif threat_count > 0:
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
                    direct_threat_count=snapshot.get("direct_count", 0),
                    ambient_threat_count=snapshot.get("ambient_count", 0),
                    pursuit_target_count=snapshot.get("pursuit_count", 0),
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

    def __init__(self, sim, player_eid, default_player_radius=24):
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
        perception_scale = 1.0 + ((perception - 5.0) / 40.0)
        perception_scale = max(0.85, min(1.25, perception_scale))

        # Minimum visibility is never below a small baseline to avoid full blindness.
        scale = (0.28 + (ambient * 0.72)) * perception_scale
        glare = _lighting_glare_strength(self.sim)
        if glare > 0.0:
            darkness = max(0.0, 0.62 - ambient) / 0.62
            scale *= max(0.54, 1.0 - (0.36 * float(glare) * darkness))
        radius = int(round(radius * scale))

        return max(4, min(36, radius))

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

    CAMERA_ALERT_WINDOW = 18
    PROPERTY_SNEAK_COOLDOWN = 18
    PERSONAL_SNEAK_COOLDOWN = 12

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self._recent_camera_alerts = {}
        self._reaction_cooldowns = {}
        self.sim.events.subscribe("camera_alerted", self.on_camera_alerted)

    def on_camera_alerted(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        property_id = str(event.data.get("property_id", "") or "").strip()
        camera_key = property_id or str(event.data.get("camera_property_id", "") or "").strip()
        if not camera_key:
            return
        self._recent_camera_alerts[camera_key] = {
            "tick": int(getattr(self.sim, "tick", 0)),
            "property_id": property_id or None,
            "camera_name": str(event.data.get("camera_name", "camera") or "camera").strip() or "camera",
        }

    def _default_intrusion_state(self):
        return {
            "active": False,
            "property_id": None,
            "property_name": "",
            "access_level": "public",
            "severity_score": 0,
            "severity_label": "clear",
            "standing_reason": "none",
            "witness_count": 0,
            "witness_labels": (),
            "camera_alerted": False,
            "camera_name": "",
            "reportable": False,
            "status_text": "",
        }

    def _current_intrusion_property(self, pos):
        prop = _property_covering(self.sim, pos.x, pos.y, pos.z)
        if prop and _property_cover_intended(prop):
            key = (int(pos.x), int(pos.y), int(pos.z))
            cover_index = getattr(self.sim, "property_cover_index", {})
            prop = None
            for property_id in cover_index.get(key, ()):
                candidate = self.sim.properties.get(property_id)
                if candidate is None:
                    continue
                prop = candidate
                break
        return _property_enclosing_structure(
            self.sim,
            pos.x,
            pos.y,
            pos.z,
            prop=prop,
        )

    def _camera_alert_state(self, property_id):
        tick = int(getattr(self.sim, "tick", 0))
        stale_keys = []
        for key, record in self._recent_camera_alerts.items():
            if tick - int(record.get("tick", -10_000)) > int(self.CAMERA_ALERT_WINDOW):
                stale_keys.append(key)
        for key in stale_keys:
            self._recent_camera_alerts.pop(key, None)

        property_key = str(property_id or "").strip()
        if property_key and property_key in self._recent_camera_alerts:
            return self._recent_camera_alerts[property_key]
        return None

    def _intrusion_state_for(self, pos, watchers):
        state = self._default_intrusion_state()
        prop = self._current_intrusion_property(pos)
        if not isinstance(prop, dict):
            return state

        access = _evaluate_property_access(
            self.sim,
            self.player_eid,
            prop,
            x=pos.x,
            y=pos.y,
            z=pos.z,
        )
        if not bool(access.inside_bounds) or int(access.severity_score) <= 0:
            return state

        witness_labels = tuple(
            _entity_display_name(self.sim, watcher_eid, title_case=False)
            for watcher_eid in watchers[:2]
        )
        camera_alert = self._camera_alert_state(prop.get("id"))
        camera_name = str((camera_alert or {}).get("camera_name", "") or "").strip()
        witness_count = len(watchers)
        reportable = witness_count > 0 or camera_alert is not None

        if witness_count > 0:
            if witness_count == 1 and witness_labels:
                status_text = f"seen:{witness_labels[0]}"
            elif witness_labels:
                status_text = f"seen:{witness_labels[0]}+{witness_count - 1}"
            else:
                status_text = f"seen:{witness_count}"
        elif camera_alert is not None:
            status_text = f"seen:{camera_name or 'camera'}"
        else:
            status_text = "unseen"

        state.update({
            "active": True,
            "property_id": str(prop.get("id", "") or "").strip() or None,
            "property_name": str(prop.get("name", prop.get("id", "property")) or "property").strip() or "property",
            "access_level": str(access.access_level or "public").strip().lower() or "public",
            "severity_score": int(access.severity_score),
            "severity_label": str(access.severity_label or "clear").strip().lower() or "clear",
            "standing_reason": str(access.standing_reason or "none").strip().lower() or "none",
            "witness_count": witness_count,
            "witness_labels": witness_labels,
            "camera_alerted": camera_alert is not None,
            "camera_name": camera_name,
            "reportable": bool(reportable),
            "status_text": status_text,
        })
        return state

    def _observer_law_drive(self, observer_eid):
        justice = self.sim.ecs.get(JusticeProfile).get(observer_eid)
        if justice is None:
            return 0.45
        return (
            (_justice_level(justice, default=0.5) * 0.65)
            + (_crime_sensitivity(justice, default=0.5) * 0.35)
        )

    def _reaction_ready(self, observer_eid, context, subject, cooldown):
        tick = int(getattr(self.sim, "tick", 0))
        key = (int(observer_eid), str(context or ""), str(subject or ""))
        last_tick = int(self._reaction_cooldowns.get(key, -10_000))
        if tick - last_tick < int(cooldown):
            return False
        self._reaction_cooldowns[key] = tick
        return True

    def _emit_close_sneak_threat(self, observer_eid, pos, *, threat_strength, safety_hit, context):
        memory = self.sim.ecs.get(NPCMemory).get(observer_eid)
        if memory is not None:
            memory.remember(
                tick=int(getattr(self.sim, "tick", 0)),
                kind="threat",
                strength=max(0.12, min(1.0, float(threat_strength))),
                source_eid=self.player_eid,
                target_eid=observer_eid,
                action="visible_sneak",
                context=str(context or "").strip().lower() or "visible_sneak",
                x=int(pos.x),
                y=int(pos.y),
                z=int(pos.z),
            )
        needs = self.sim.ecs.get(NPCNeeds).get(observer_eid)
        if needs is not None:
            needs.safety = max(0.0, min(100.0, float(getattr(needs, "safety", 100.0) or 100.0) - float(safety_hit)))

    def _emit_visible_sneak_reactions(self, pos, watchers, intrusion_state):
        modes = self.sim.ecs.get(PlayerModeState).get(self.player_eid)
        if not modes or not bool(getattr(modes, "sneak", False)):
            return
        if not watchers:
            return
        if bool(getattr(modes, "hidden", False)):
            return

        ais = self.sim.ecs.get(AI)
        positions = self.sim.ecs.get(Position)
        traits_map = self.sim.ecs.get(NPCTraits)
        severity_label = str(intrusion_state.get("severity_label", "clear") or "clear").strip().lower()
        severity_base = {
            "suspicious": 16,
            "trespass": 24,
            "serious_trespass": 34,
        }.get(severity_label, 0)
        property_id = str(intrusion_state.get("property_id", "") or "").strip()

        for observer_eid in watchers:
            observer_ai = ais.get(observer_eid)
            if observer_ai is None:
                continue
            if str(getattr(observer_ai, "role", "") or "").strip().lower() == "wildlife":
                continue

            observer_pos = positions.get(observer_eid)
            if observer_pos is None or int(observer_pos.z) != int(pos.z):
                continue

            dist = _manhattan(pos.x, pos.y, observer_pos.x, observer_pos.y)
            traits = traits_map.get(observer_eid) or NPCTraits()
            bravery = max(0.0, min(1.0, float(getattr(traits, "bravery", 0.5) or 0.5)))
            discipline = max(0.0, min(1.0, float(getattr(traits, "discipline", 0.5) or 0.5)))
            law_drive = self._observer_law_drive(observer_eid)

            if dist <= 1:
                if not self._reaction_ready(
                    observer_eid,
                    "personal_space",
                    observer_eid,
                    self.PERSONAL_SNEAK_COOLDOWN,
                ):
                    continue
                fearful = law_drive < 0.55 and bravery < 0.28
                if not fearful:
                    offense_score = min(
                        48,
                        24 + int(round((law_drive * 8.0) + ((1.0 - bravery) * 10.0) + ((1.0 - discipline) * 4.0))),
                    )
                    perceived = max(0.62, min(1.0, 0.74 + (law_drive * 0.1) + ((1.0 - bravery) * 0.14)))
                    self.sim.emit(Event(
                        "npc_offended",
                        npc_eid=observer_eid,
                        offender_eid=self.player_eid,
                        action="sneak",
                        context="personal_space",
                        offense_score=offense_score,
                        perceived=round(perceived, 3),
                    ))
                self._emit_close_sneak_threat(
                    observer_eid,
                    pos,
                    threat_strength=(0.72 if fearful else 0.56) + ((1.0 - bravery) * 0.26),
                    safety_hit=(22.0 if fearful else 12.0) + ((1.0 - bravery) * 18.0),
                    context="personal_space",
                )
                continue

            if not bool(intrusion_state.get("active")) or severity_base <= 0 or not property_id:
                continue
            if not self._reaction_ready(
                observer_eid,
                "property_sneak",
                property_id,
                self.PROPERTY_SNEAK_COOLDOWN,
            ):
                continue

            offense_score = min(
                44,
                severity_base + int(round((law_drive * 8.0) + (discipline * 4.0))),
            )
            perceived = max(0.45, min(0.92, 0.5 + (law_drive * 0.18) + (discipline * 0.1)))
            self.sim.emit(Event(
                "npc_offended",
                npc_eid=observer_eid,
                offender_eid=self.player_eid,
                action="sneak",
                context="property_sneak",
                offense_score=offense_score,
                perceived=round(perceived, 3),
            ))

    def update(self):
        modes = self.sim.ecs.get(PlayerModeState).get(self.player_eid)
        pos = self.sim.ecs.get(Position).get(self.player_eid)
        if not modes or not pos:
            self.sim.player_stealth_state = {
                "hidden": False,
                "witness_count": 0,
                "witness_labels": (),
            }
            self.sim.player_intrusion_state = self._default_intrusion_state()
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
        intrusion_state = self._intrusion_state_for(pos, watchers)
        self.sim.player_intrusion_state = intrusion_state
        self._emit_visible_sneak_reactions(pos, watchers, intrusion_state)
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
