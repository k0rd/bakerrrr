"""Extracted systems from ``game.systems``: CameraSystem, PropertyAwarenessSystem, PropertyDefenseSystem."""

from engine.events import Event
from engine.systems import System
from engine.visibility import (
    has_line_of_sight as _shared_has_line_of_sight,
    observer_can_see_position as _shared_observer_can_see_position,
    update_player_visibility as _update_player_visibility,
)
from game.checks import (
    crime_read_summary as _crime_read_summary,
    crime_sensitivity as _crime_sensitivity,
    justice_level as _justice_level,
    rumor_truth_read as _rumor_truth_read,
    social_read_axes as _social_read_axes,
)
from game.components import (
    AI,
    AnimalMemory,
    AnimalBehaviorContext,
    AnimalPhysicalProfile,
    AnimalSocialProfile,
    ArmorLoadout,
    Collider,
    ContactLedger,
    CoreStats,
    CoverState,
    CreatureIdentity,
    DoorWaitState,
    EcologyProfile,
    FinancialProfile,
    HumanWildlifePresence,
    InsightStats,
    Inventory,
    ItemUseProfile,
    JusticeProfile,
    MovementThrottle,
    NPCMemory,
    NPCNeeds,
    NPCRoutine,
    NPCSettlement,
    NPCSocial,
    NPCTraits,
    NPCWill,
    NoiseProfile,
    Occupation,
    OrganizationAffiliations,
    PlayerAssets,
    PlayerControlled,
    PlayerModeState,
    Position,
    PropertyKnowledge,
    PropertyPortfolio,
    Render,
    SkillProfile,
    StatusEffects,
    SuppressionState,
    VehicleState,
    Vitality,
    WildlifeSocialState,
    WildlifeBehavior,
    WeaponLoadout,
    WeaponUseProfile,
)
from game.property_access import (
    PropertyIngressResult,
    _boundary_tile as _property_boundary_tile,
    apply_controller_intrusion as _apply_controller_intrusion,
    controller_intrusion_access_for_actor as _controller_intrusion_access_for_actor,
    controller_intrusion_state as _controller_intrusion_state,
    default_site_services_for_archetype as _default_site_services_for_archetype,
    _property_archetype,
    property_access_controller as _property_access_controller,
    evaluate_property_access as _evaluate_property_access,
    sync_property_access_controller as _sync_property_access_controller,
    property_access_level as _property_access_level,
    property_apertures as _property_apertures,
    property_ingress_context as _property_ingress_context,
    property_claim_reason as _property_claim_reason,
    property_status_text as _property_status_text,
    world_hour as _world_hour,
)
from game.property_runtime import (
    building_id_from_property as _building_id_from_property,
    building_id_from_structure as _building_id_from_structure,
    clear_property_runtime_container_state as _clear_property_runtime_container_state,
    controller_access_requirement_text as _controller_access_requirement_text,
    controller_credential_short_label as _controller_credential_short_label,
    controller_holder_for_actor as _controller_holder_for_actor,
    finance_services_for_property as _finance_services_for_property,
    property_cover_intended as _property_cover_intended,
    property_infrastructure_role as _property_infrastructure_role,
    property_linked_building_id as _property_linked_building_id,
    property_linked_property_id as _property_linked_property_id,
    property_aperture_at as _property_aperture_at,
    property_covering as _property_covering,
    property_enclosing_structure as _property_enclosing_structure,
    property_display_position as _property_display_position,
    property_distance as _property_distance,
    property_focus_position as _property_focus_position,
    property_for_action as _property_for_action,
    property_is_public as _property_is_public,
    property_is_storefront as _property_is_storefront,
    property_is_vehicle as _property_is_vehicle,
    property_runtime_container_entry_count as _property_runtime_container_entry_count,
    property_runtime_container_entry_snapshot as _property_runtime_container_entry_snapshot,
    property_metadata as _property_metadata,
    remember_property_lead_for_actor as _remember_property_lead_for_actor,
    property_runtime_container_entries as _property_runtime_container_entries,
    property_services as _property_services,
    property_signage as _property_signage,
    site_services_for_property as _site_services_for_property,
    storefront_service_mode as _storefront_service_mode,
    vehicle_fuel_values as _vehicle_fuel_values,
    vehicle_label as _vehicle_label,
    vehicle_profile_from_property as _vehicle_profile_from_property,
    viewer_property_credential_status as _viewer_property_credential_status,
    viewer_revealed_building_id as _viewer_revealed_building_id,
)
from game.run_pressure import (
    apply_pressure_delta as _apply_pressure_delta,
    pressure_effects as _pressure_effects,
    pressure_snapshot as _pressure_snapshot,
)
from game.criminal_justice_runtime import (
    _defender_excuses_window_shot,
    _observer_is_active_contractor_ally,
)
from game.dialogue_runtime import _dialogue_guard_grace_active
from game.system_support.intrusion_runtime import (
    _ingress_method_label,
    _ingress_mode_label,
    _is_operable_door_aperture,
    _is_side_aperture,
    _is_window_aperture,
    _quiet_unwitnessed_tamper,
    _trespass_is_obvious_breach,
    _trespass_label_from_score,
)
from game.system_support.actor_runtime import (
    _apply_downed_actor_state,
    _detail_tick_allowed,
    _entity_is_downed,
)
from game.system_support.security_disguise_runtime import (
    _camera_disguise_scrutiny_profile,
    _degrade_player_disguise,
    _npc_disguise_scrutiny_profile,
    _security_fixture_is_online,
)
from game.system_support.business_event_state import _business_event_actor_note
from game.system_support.interaction_ordering import (
    _direction_step,
    _interaction_target_order_key,
    _manhattan,
    _normalized_direction,
)
from game.system_support.offense_runtime import (
    ACTION_OFFENSE_BASE,
    ACTION_OFFENSE_CONTEXT_BONUS,
    ASSAULT_OFFENSE_CONTEXTS,
    OFFICIAL_REPORTABLE_OFFENSE_CONTEXTS,
    VIOLENT_OFFENSE_CONTEXTS,
    _emit_action_offense_event,
    _offense_notice_radius,
    _offense_score_for_action,
    _offense_tier,
)
from game.system_support.player_feedback import _log_player_feedback


def _business_scene_watch_reason(sim, eid, prop):
    note = _business_event_actor_note(sim, eid)
    if not isinstance(note, dict):
        return ""
    if str(note.get("property_id", "") or "").strip() != str((prop or {}).get("id", "") or "").strip():
        return ""
    if str(note.get("event_phase", "") or "").strip().lower() != "block_watch":
        return ""
    career = str(note.get("career", "") or "").strip().lower()
    if career != "block_regular":
        return ""
    return "watcher"


class CameraSystem(System):
    """Detects the player in camera sightlines and raises offense events.

    Cameras are fixtures with interaction_role == "camera_target". They are
    disabled by power cuts (via fixture_power_cuts) or by direct player
    interaction (via camera_disabled). When active, if the player is within
    detection radius and camera has LOS, an offense is raised *only* if the
    player lacks legitimate access to that area.
    """

    DETECTION_COOLDOWN = 14   # ticks between repeat detections per camera
    SCRUTINY_RESET_TICKS = 42
    CAMERA_OFFENSE_SCORE = 26  # medium offense; between trespass and tamper

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self._last_detect = {}   # {cam_prop_id: last_tick_detected}
        self._scrutiny = {}      # {cam_prop_id: {"value": float, "tick": int}}
        self.sim.events.subscribe("player_action", self.on_player_action)

    def on_player_action(self, event):
        eid = event.data.get("eid")
        if eid != self.player_eid:
            return
        action = event.data.get("action")
        if action not in {"move", "wait", "interact", "pickup_item", "use_item"}:
            return
        self._check_cameras()

    def _camera_is_online(self, cam_id, cam_prop):
        return _security_fixture_is_online(self.sim, cam_prop, tick=int(getattr(self.sim, "tick", 0)))

    def _camera_scrutiny_value(self, cam_id, *, tick):
        state = self._scrutiny.get(cam_id)
        if not isinstance(state, dict):
            return 0.0
        last_tick = int(state.get("tick", -9999))
        if int(tick) - last_tick > self.SCRUTINY_RESET_TICKS:
            self._scrutiny.pop(cam_id, None)
            return 0.0
        return max(0.0, float(state.get("value", 0.0)))

    def _set_camera_scrutiny(self, cam_id, value, *, tick):
        value = max(0.0, float(value))
        if value <= 0.0:
            self._scrutiny.pop(cam_id, None)
            return
        self._scrutiny[cam_id] = {
            "value": round(value, 3),
            "tick": int(tick),
        }

    def _check_cameras(self):
        positions = self.sim.ecs.get(Position)
        player_pos = positions.get(self.player_eid)
        if not player_pos:
            return
        px = int(player_pos.x)
        py = int(player_pos.y)
        pz = int(player_pos.z)
        tick = int(getattr(self.sim, "tick", 0))

        for cam_id, cam_prop in self.sim.properties.items():
            if _property_infrastructure_role(cam_prop) != "camera_target":
                continue
            if not self._camera_is_online(cam_id, cam_prop):
                continue
            cam_x = int(cam_prop.get("x", 0))
            cam_y = int(cam_prop.get("y", 0))
            cam_z = int(cam_prop.get("z", 0))
            if cam_z != pz:
                continue
            metadata = cam_prop.get("metadata") or {}
            radius = int(metadata.get("detection_radius", 5))
            if _manhattan(cam_x, cam_y, px, py) > radius:
                continue
            # Throttle per-camera detections.
            if self._last_detect.get(cam_id, -999) + self.DETECTION_COOLDOWN > tick:
                continue
            # LOS check from camera to player.
            if not _shared_has_line_of_sight(self.sim, cam_x, cam_y, cam_z, px, py, pz):
                continue
            # Cameras only escalate inside an enclosing structure where the
            # player's access state is meaningfully criminal.
            covering_prop = _property_enclosing_structure(
                self.sim,
                px,
                py,
                pz,
                prop=_property_covering(self.sim, px, py, pz),
            )
            if not covering_prop:
                self._set_camera_scrutiny(cam_id, 0.0, tick=tick)
                continue
            access = _evaluate_property_access(
                self.sim,
                self.player_eid,
                covering_prop,
                x=px,
                y=py,
                z=pz,
            )
            if access.permitted or not access.inside_bounds or access.severity_score <= 0:
                self._set_camera_scrutiny(cam_id, 0.0, tick=tick)
                continue
            disguise_profile = _camera_disguise_scrutiny_profile(self.sim, covering_prop)
            camera_name = str(cam_prop.get("name", "camera") or "camera").strip() or "camera"
            if disguise_profile:
                scrutiny = self._camera_scrutiny_value(cam_id, tick=tick)
                new_scrutiny = scrutiny + float(disguise_profile.get("increment", 0.0))
                threshold = max(0.1, float(disguise_profile.get("threshold", 0.1)))
                confidence = max(0.0, min(1.0, new_scrutiny / threshold))
                if new_scrutiny + 1e-6 < threshold:
                    self._last_detect[cam_id] = tick
                    self._set_camera_scrutiny(cam_id, new_scrutiny, tick=tick)
                    self.sim.emit(Event(
                        "camera_scrutiny",
                        eid=self.player_eid,
                        camera_property_id=cam_id,
                        camera_name=camera_name,
                        property_id=covering_prop.get("id") if isinstance(covering_prop, dict) else None,
                        disguise_role=disguise_profile.get("role_id"),
                        scrutiny=round(new_scrutiny, 3),
                        threshold=round(threshold, 3),
                        confidence=round(confidence, 3),
                    ))
                    continue
            self._last_detect[cam_id] = tick
            self._set_camera_scrutiny(cam_id, 0.0, tick=tick)
            if disguise_profile:
                _degrade_player_disguise(self.sim, self.player_eid, amount=0.22)
            self.sim.emit(Event(
                "camera_alerted",
                eid=self.player_eid,
                camera_property_id=cam_id,
                camera_name=camera_name,
                property_id=covering_prop.get("id") if isinstance(covering_prop, dict) else None,
                x=px,
                y=py,
                z=pz,
                access_level=access.access_level,
                severity_score=access.severity_score,
                severity_label=access.severity_label,
                disguise_role=disguise_profile.get("role_id") if disguise_profile else None,
                disguise_failed=bool(disguise_profile),
            ))
            _emit_action_offense_event(
                self.sim,
                eid=self.player_eid,
                action="interact",
                context="trespass",
                x=px,
                y=py,
                z=pz,
                score=self.CAMERA_OFFENSE_SCORE,
            )
            _log_player_feedback(
                self.sim,
                "A security camera has eyes on you.",
                kind="warning",
            )

class PropertyAwarenessSystem(System):

    def update(self):
        positions = self.sim.ecs.get(Position)
        knowledges = self.sim.ecs.get(PropertyKnowledge)
        socials = self.sim.ecs.get(NPCSocial)

        for eid, knowledge in knowledges.items():
            pos = positions.get(eid)
            if not pos:
                continue

            if not _detail_tick_allowed(self.sim, pos, eid, coarse_divisor=4):
                continue

            nearby = self.sim.properties_in_radius(pos.x, pos.y, pos.z, r=2)

            for prop in nearby:
                access = _evaluate_property_access(
                    self.sim,
                    eid,
                    prop,
                    x=pos.x,
                    y=pos.y,
                    z=pos.z,
                )
                existing = knowledge.known.get(prop["id"]) if isinstance(knowledge.known, dict) else None
                try:
                    prior_confidence = float((existing or {}).get("confidence", 0.0) or 0.0)
                except (TypeError, ValueError):
                    prior_confidence = 0.0
                confidence = 0.35
                if access.standing_reason == "owner":
                    confidence = 1.0
                elif access.standing_reason in {"resident", "employee"}:
                    confidence = max(confidence, 0.92)
                elif access.standing >= 0.55:
                    confidence = max(confidence, 0.55 + (access.standing * 0.3))
                elif eid == getattr(self.sim, "player_eid", None) and bool(access.inside_bounds):
                    confidence = max(confidence, 0.68)

                anchored = bool(
                    eid == getattr(self.sim, "player_eid", None)
                    and (
                        access.standing_reason == "owner"
                        or bool(access.inside_bounds)
                    )
                )
                knowledge.remember(
                    prop["id"],
                    owner_eid=prop.get("owner_eid"),
                    owner_tag=prop.get("owner_tag"),
                    confidence=confidence,
                    tick=self.sim.tick,
                    anchored=anchored,
                    anchor_kind=(
                        "owned"
                        if access.standing_reason == "owner"
                        else "presence"
                    ) if anchored else None,
                )
                updated = knowledge.known.get(prop["id"]) if isinstance(knowledge.known, dict) else None
                try:
                    new_confidence = float((updated or {}).get("confidence", prior_confidence) or prior_confidence)
                except (TypeError, ValueError):
                    new_confidence = prior_confidence
                if (
                    eid == getattr(self.sim, "player_eid", None)
                    and prior_confidence < 0.5 <= new_confidence
                ):
                    self.sim.emit(Event(
                        "property_self_discovered",
                        eid=eid,
                        property_id=prop.get("id"),
                        property_name=str(prop.get("name", prop.get("id", "location"))).strip() or "location",
                        discovery_mode="presence",
                        confidence=new_confidence,
                    ))

        # Knowledge sharing within trusted social links.
        for eid, social in socials.items():
            if (self.sim.tick + eid) % 5 != 0:
                continue

            source = knowledges.get(eid)
            src_pos = positions.get(eid)
            if not source or not src_pos:
                continue

            for other_eid, bond in social.bonds.items():
                if bond["trust"] < 0.55 or bond["closeness"] < 0.45:
                    continue

                other_knowledge = knowledges.get(other_eid)
                other_pos = positions.get(other_eid)
                if not other_knowledge or not other_pos:
                    continue

                if src_pos.z != other_pos.z:
                    continue
                if _manhattan(src_pos.x, src_pos.y, other_pos.x, other_pos.y) > 6:
                    continue

                ranked = sorted(
                    source.known.items(),
                    key=lambda item: item[1]["confidence"],
                    reverse=True,
                )
                for property_id, info in ranked[:2]:
                    shared_conf = info["confidence"] * (0.75 + (bond["trust"] * 0.2))
                    existing = other_knowledge.known.get(property_id)
                    existing_conf = existing["confidence"] if existing else 0.0
                    if shared_conf <= existing_conf + 0.05:
                        continue

                    other_knowledge.remember(
                        property_id,
                        owner_eid=info.get("owner_eid"),
                        owner_tag=info.get("owner_tag"),
                        confidence=shared_conf,
                        tick=self.sim.tick,
                    )

                    self.sim.emit(Event(
                        "property_knowledge_shared",
                        from_eid=eid,
                        to_eid=other_eid,
                        property_id=property_id,
                    ))
                    break

class PropertyDefenseSystem(System):

    def __init__(self, sim):
        super().__init__(sim)
        self.sim.events.subscribe("property_trespass", self.on_property_threat)
        self.sim.events.subscribe("property_tamper", self.on_property_threat)

    def on_property_threat(self, event):
        offender_eid = event.data.get("offender_eid")
        property_id = event.data.get("property_id")
        threat_type = str(event.type or "property_tamper").strip().lower()
        witnessed = bool(event.data.get("witnessed", False))
        witness_eids = set()
        raw_witnesses = event.data.get("witnesses", ())
        if isinstance(raw_witnesses, (list, tuple, set, frozenset)):
            for raw_eid in raw_witnesses:
                try:
                    witness_eids.add(int(raw_eid))
                except (TypeError, ValueError):
                    continue
        severity_score = int(event.data.get("severity_score", 24 if threat_type != "property_trespass" else 18))
        severity_label = str(event.data.get("severity_label", "trespass") or "trespass").strip().lower()
        ingress_kind = str(event.data.get("ingress_kind", "") or "").strip().lower()
        aperture_kind = str(event.data.get("aperture_kind", "") or "").strip().lower()
        ingress_method = str(event.data.get("ingress_method", "") or "").strip().lower()
        defender_witnesses_only = bool(event.data.get("defender_witnesses_only", False))
        require_witnessed_identity = bool(event.data.get("require_witnessed_identity", False))
        pressure_effects = _pressure_effects(self.sim)
        severity_bias = int(max(0, pressure_effects.get("defense_severity_bias", 0)))
        protect_shift = int(max(0, pressure_effects.get("protect_threshold_shift", 0)))
        severity_score = max(0, min(100, int(severity_score) + severity_bias))

        prop = self.sim.properties.get(property_id)
        if not prop:
            return

        if threat_type == "property_trespass" and not witnessed:
            return
        if threat_type == "property_tamper" and _quiet_unwitnessed_tamper(
            prop,
            witnessed=witnessed,
            ingress_kind=ingress_kind,
            ingress_method=ingress_method,
            breach_severity=float(event.data.get("breach_severity", 0.0) or 0.0),
        ):
            return
        if threat_type == "property_tamper" and require_witnessed_identity and not witnessed:
            return
        if threat_type == "property_trespass" and severity_score < 10:
            return

        response_mode = "protect" if threat_type == "property_tamper" else "warn"
        if threat_type == "property_trespass":
            threshold = lambda base: max(6, int(base) - protect_shift)
            window_entry = ingress_kind == "alternate_aperture" and _is_window_aperture(aperture_kind)
            forced_entry = ingress_kind in {"boundary_breach", "deep_breach"}
            if severity_label == "serious_trespass":
                response_mode = "protect"
            elif forced_entry and severity_score >= threshold(12):
                response_mode = "protect"
            elif window_entry and severity_score >= threshold(16):
                response_mode = "protect"
            elif ingress_method == "forced_side_entry" and severity_score >= threshold(14):
                response_mode = "protect"
            elif ingress_method == "jimmied_side_entry" and severity_score >= threshold(22):
                response_mode = "protect"
            elif ingress_method in {"crash_window_entry", "forced_breach", "deep_breach"} and severity_score >= threshold(12):
                response_mode = "protect"
            elif ingress_method in {"quiet_window_entry", "careful_window_entry"} and severity_score >= threshold(20):
                response_mode = "protect"

        if response_mode == "protect":
            self.sim.emit(Event(
                "property_threatened",
                property_id=property_id,
                offender_eid=offender_eid,
                x=prop["x"],
                y=prop["y"],
                z=prop["z"],
                threat_type=threat_type,
            ))

        # If the property's power is cut, alarms are offline — suppress protect escalation.
        power_cuts = getattr(self.sim, "fixture_power_cuts", {})
        if power_cuts and response_mode == "protect":
            tick = int(getattr(self.sim, "tick", 0))
            pid = str(property_id or "").strip()
            prop_power_cut = power_cuts.get(pid, 0) > tick
            if not prop_power_cut:
                cover_index = getattr(self.sim, "property_cover_index", {})
                for covered_pid in cover_index.get(
                    (int(prop.get("x", 0)), int(prop.get("y", 0)), int(prop.get("z", 0))), ()
                ):
                    if power_cuts.get(covered_pid, 0) > tick:
                        prop_power_cut = True
                        break
            if prop_power_cut:
                response_mode = "warn"

        self._dispatch_defenders(
            prop,
            offender_eid,
            response_mode=response_mode,
            severity_score=severity_score,
            severity_label=severity_label,
            threat_type=threat_type,
            ingress_kind=ingress_kind,
            aperture_kind=aperture_kind,
            ingress_method=ingress_method,
            witness_eids=frozenset(witness_eids) if defender_witnesses_only else None,
        )

    def _dispatch_defenders(
        self,
        prop,
        offender_eid,
        response_mode="protect",
        severity_score=24,
        severity_label="trespass",
        threat_type="property_trespass",
        ingress_kind="",
        aperture_kind="",
        ingress_method="",
        witness_eids=None,
    ):
        ais = self.sim.ecs.get(AI)
        wills = self.sim.ecs.get(NPCWill)
        traits_map = self.sim.ecs.get(NPCTraits)
        knowledges = self.sim.ecs.get(PropertyKnowledge)
        justices = self.sim.ecs.get(JusticeProfile)
        positions = self.sim.ecs.get(Position)

        offender_pos = positions.get(offender_eid)
        focus = _property_focus_position(prop)
        focus_x = focus[0] if focus else int(prop["x"])
        focus_y = focus[1] if focus else int(prop["y"])
        focus_z = focus[2] if focus else int(prop["z"])

        defenders = {}
        owner = prop.get("owner_eid")

        if owner is not None and owner != offender_eid:
            defenders[owner] = "owner"

        standing_threshold = 0.72 if severity_score < 18 else 0.58
        for eid, pos in positions.items():
            if eid == offender_eid:
                continue
            if pos.z != focus_z:
                continue
            if _manhattan(pos.x, pos.y, focus_x, focus_y) > 12:
                continue

            _, claim_reason = _property_claim_reason(
                self.sim,
                eid,
                prop,
                x=pos.x,
                y=pos.y,
                z=pos.z,
                min_standing=standing_threshold,
            )
            if not claim_reason:
                claim_reason = _business_scene_watch_reason(self.sim, eid, prop)
            if not claim_reason:
                continue
            defenders[eid] = claim_reason

        for eid, profile in justices.items():
            if eid == offender_eid:
                continue
            if severity_score < 18:
                continue

            pos = positions.get(eid)
            if not pos or pos.z != focus_z:
                continue

            if _manhattan(pos.x, pos.y, focus_x, focus_y) > 12:
                continue

            if profile.corruption > 0.75 and not profile.enforce_all:
                continue

            if profile.enforce_all:
                defenders.setdefault(eid, "watcher")
                continue

            law_drive = (_justice_level(profile) * 0.65) + (_crime_sensitivity(profile) * 0.35)
            threshold = 0.74 if severity_label == "trespass" else 0.82
            if law_drive < threshold:
                continue

            knowledge = knowledges.get(eid)
            if not knowledge:
                continue

            known = knowledge.known.get(prop["id"])
            if known and known["confidence"] >= 0.5:
                defenders.setdefault(eid, "watcher")

        for defender_eid, defender_reason in defenders.items():
            if defender_eid == offender_eid:
                continue
            if witness_eids is not None and defender_eid not in witness_eids:
                continue
            if _observer_is_active_contractor_ally(self.sim, defender_eid, offender_eid):
                continue
            if ingress_method == "window_shot" and _defender_excuses_window_shot(
                self.sim,
                defender_eid,
                offender_eid,
                prop,
                defender_reason=defender_reason,
            ):
                continue

            ai = ais.get(defender_eid)
            pos = positions.get(defender_eid)
            if not ai or not pos:
                continue
            if _entity_is_downed(self.sim, defender_eid):
                _apply_downed_actor_state(self.sim, defender_eid, tick=self.sim.tick)
                continue
            if pos.z != prop["z"]:
                continue
            if (
                offender_eid == getattr(self.sim, "player_eid", None)
                and _dialogue_guard_grace_active(self.sim, defender_eid, prop)
            ):
                continue

            if offender_pos and offender_pos.z == pos.z:
                target = (offender_pos.x, offender_pos.y, offender_pos.z)
            else:
                target = (prop["x"], prop["y"], prop["z"])

            if response_mode == "warn" and ai.state == "protecting" and ai.target_eid == offender_eid:
                continue

            defender_response_mode = response_mode
            if (
                offender_eid == getattr(self.sim, "player_eid", None)
                and threat_type == "property_trespass"
            ):
                disguise_profile = _npc_disguise_scrutiny_profile(
                    self.sim,
                    defender_eid,
                    prop,
                    offender_eid=offender_eid,
                )
                if disguise_profile:
                    hard_entry = bool(
                        severity_label == "serious_trespass"
                        or ingress_kind in {"boundary_breach", "deep_breach"}
                        or ingress_method in {
                            "forced_side_entry",
                            "jimmied_side_entry",
                            "quiet_window_entry",
                            "careful_window_entry",
                            "crash_window_entry",
                            "forced_breach",
                            "deep_breach",
                        }
                        or _is_window_aperture(aperture_kind)
                    )
                    if (
                        defender_response_mode == "warn"
                        and disguise_profile.get("allow_pass")
                        and severity_score <= 18
                        and not hard_entry
                    ):
                        continue
                    if (
                        defender_response_mode == "protect"
                        and disguise_profile.get("downgrade_protect")
                        and severity_score <= 24
                        and not hard_entry
                    ):
                        defender_response_mode = "warn"
                    elif (
                        defender_response_mode == "warn"
                        and disguise_profile.get("escalate_warn")
                        and severity_score >= 12
                    ):
                        defender_response_mode = "protect"

            if defender_response_mode == "warn":
                ai.state = "investigating"
            else:
                ai.state = "protecting"
            ai.target = target
            ai.target_eid = offender_eid if defender_response_mode == "protect" else None

            will = wills.get(defender_eid)
            traits = traits_map.get(defender_eid) or NPCTraits()
            if will:
                if defender_response_mode == "warn":
                    will.intent = "investigating"
                    will.score = 42.0 + (traits.discipline * 18.0)
                    will.target_eid = None
                else:
                    will.intent = "protecting"
                    will.score = 70.0 + (traits.loyalty * 25.0)
                    will.target_eid = offender_eid
                will.target = target
                will.last_tick = self.sim.tick

            if defender_response_mode == "warn":
                self.sim.emit(Event(
                    "npc_warn_property",
                    npc_eid=defender_eid,
                    offender_eid=offender_eid,
                    property_id=prop["id"],
                    owner_eid=owner,
                    defender_reason=defender_reason,
                    threat_type=threat_type,
                    severity_label=severity_label,
                    ingress_kind=ingress_kind,
                    aperture_kind=aperture_kind,
                    ingress_method=ingress_method,
                ))
            else:
                self.sim.emit(Event(
                    "npc_defend_property",
                    npc_eid=defender_eid,
                    offender_eid=offender_eid,
                    property_id=prop["id"],
                    owner_eid=owner,
                    defender_reason=defender_reason,
                    threat_type=threat_type,
                    severity_label=severity_label,
                    ingress_kind=ingress_kind,
                    aperture_kind=aperture_kind,
                    ingress_method=ingress_method,
                ))
