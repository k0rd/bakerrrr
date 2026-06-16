"""Extracted player action system."""

from engine.events import Event
from engine.systems import System
from engine.visibility import has_line_of_sight as _has_line_of_sight
from game.components import (
    AI,
    CoverState,
    CreatureIdentity,
    Inventory,
    Occupation,
    PlayerControlled,
    PlayerModeState,
    Position,
)
from game.overworld_runtime import (
    PlayerOverworldRuntime,
    _player_overworld_visit_state,
    _remember_overworld_chunk_memory,
)
from game.dialogue_runtime import (
    _career_label,
    _infrastructure_target_property,
    _workplace_property,
)
from game.player_interactions import PlayerInteractionRuntime
from game.player_look import PlayerLookRuntime
from game.player_movement import PlayerMovementRuntime
from game.player_travel import PlayerTravelRuntime
from game.property_access import (
    controller_intrusion_access_for_actor as _controller_intrusion_access_for_actor,
    property_access_controller as _property_access_controller,
    property_access_level as _property_access_level,
    site_services_for_property as _site_services_for_property,
)
from game.property_actions import PropertyActionRuntime
from game.property_ingress import PropertyIngressRuntime
from game.property_keys import (
    inventory_matching_property_credential,
    inventory_matching_property_key,
    property_lock_state,
)
from game.system_support.awareness_runtime import observation_payload_for_position
from game.system_support.opportunity_knowledge_runtime import (
    rehydrate_entity_knowledge as _rehydrate_entity_knowledge,
)
from game.property_runtime import (
    controller_access_requirement_text as _controller_access_requirement_text,
    controller_holder_for_actor as _controller_holder_for_actor,
    finance_services_for_property as _finance_services_for_property,
    property_is_public as _property_is_public,
    property_is_storefront as _property_is_storefront,
    property_metadata as _property_metadata,
)
from game.location_presentation_runtime import (
    _access_prep_detail_lines,
    _active_property_opportunities,
    _building_street_summary,
    _entity_legend_line,
    _item_legend_line,
    _property_contact_hint,
    _property_knowledge_hint,
    _property_legend_line,
    _property_summary,
    _stakeout_progress_snapshot,
    _stakeout_property_opportunity_stats,
    _structure_summary,
    _tile_label,
    _tile_legend_line,
)
from game.service_runtime import _credit_amount_label, _site_service_label
from game.situation_read import perform_tactical_read
from game.skills import (
    access_prep_skill_terms as _access_prep_skill_terms,
    actor_skill as _actor_skill,
    scan_skill_terms as _scan_skill_terms,
)
from game.system_support.access_checks import _maybe_damage_access_tool, _resolve_access_skill_check
from game.system_support.access_runtime import (
    _access_override_score_for_actor,
    _access_tool_context_for,
    _access_tool_terms_for_actor,
    _emit_property_lock_tamper_event,
    _lock_override_required_for_prop,
)
from game.system_support.actor_runtime import _apply_downed_actor_state, _entity_is_downed
from game.system_support.altered_state_runtime import control_lapse_active, maybe_misdirect_move
from game.system_support.combat_targeting_runtime import _manual_fire_preview, _target_condition_descriptor
from game.system_support.interaction_ordering import (
    _interaction_target_order_key,
    _manhattan,
    _normalized_direction,
)
from game.system_support.intrusion_runtime import _trespass_label_from_score
from game.system_support.offense_runtime import (
    ACTION_OFFENSE_BASE,
    ACTION_OFFENSE_CONTEXT_BONUS,
    _offense_notice_radius,
    _offense_tier,
)
from game.system_support.security_disguise_runtime import _security_fixture_is_online
from game.status_ui_runtime import _entity_status_move_speed_multiplier
from game.ui_text_runtime import _line_with_suffix

STAKEOUT_REVEAL_INTERVAL = 8
STAKEOUT_MAX_REVEALS = 4
CONTROL_LAPSE_TURN_ACTIONS = {
    "move",
    "vehicle_move",
    "vehicle_momentum",
    "overworld_travel",
    "zoom_city_enter",
    "floor_change",
    "wait",
    "toggle_sneak",
    "toggle_door_lock",
    "scan",
    "tactical_read",
    "interact",
    "side_entry",
    "window_entry",
    "forced_breach",
    "pickup_item",
    "drop_item",
    "use_item",
    "purchase_property",
    "cover_hop",
    "toggle_cover",
    "cycle_weapon",
}


def _facade():
    from game import systems as facade

    return facade

def _best_cover_candidate(*args, **kwargs):
    return _facade()._best_cover_candidate(*args, **kwargs)

def _emit_move_access_events(*args, **kwargs):
    return _facade()._emit_move_access_events(*args, **kwargs)


def _property_access_summary(*args, **kwargs):
    return _facade()._property_access_summary(*args, **kwargs)


def _tile_prefers_feature_legend(*args, **kwargs):
    return _facade()._tile_prefers_feature_legend(*args, **kwargs)


def _world_trait_claim_text(*args, **kwargs):
    return _facade()._world_trait_claim_text(*args, **kwargs)


def _world_trait_claim_value(*args, **kwargs):
    return _facade()._world_trait_claim_value(*args, **kwargs)


class PlayerActionSystem(System):

    PLAYER_DISCOVERY_CONFIDENCE = {
        "sight": 0.58,
        "scan": 0.60,
        "interact": 0.72,
    }

    def __init__(self, sim):
        super().__init__(sim)
        self.property_actions = PropertyActionRuntime(self)
        self.property_ingress = PropertyIngressRuntime(self)
        self.player_overworld = PlayerOverworldRuntime(self)
        self.player_look = PlayerLookRuntime(
            self,
            tile_label=_tile_label,
            property_summary=_property_summary,
            structure_summary=_structure_summary,
            building_street_summary=_building_street_summary,
            property_knowledge_hint=_property_knowledge_hint,
            property_contact_hint=_property_contact_hint,
            target_condition_descriptor=_target_condition_descriptor,
            career_label=_career_label,
            workplace_property=_workplace_property,
            entity_legend_line=_entity_legend_line,
            item_legend_line=_item_legend_line,
            property_legend_line=_property_legend_line,
            tile_legend_line=_tile_legend_line,
            tile_prefers_feature_legend=_tile_prefers_feature_legend,
            manual_fire_preview=_manual_fire_preview,
            line_with_suffix=_line_with_suffix,
            scan_skill_terms=_scan_skill_terms,
            access_prep_skill_terms=_access_prep_skill_terms,
            property_access_controller=_property_access_controller,
            controller_access_requirement_text=_controller_access_requirement_text,
            property_access_summary=_property_access_summary,
            site_services_for_property=_site_services_for_property,
            stakeout_property_opportunity_stats=_stakeout_property_opportunity_stats,
            security_fixture_is_online=_security_fixture_is_online,
            access_prep_detail_lines=_access_prep_detail_lines,
            entity_status_move_speed_multiplier=_entity_status_move_speed_multiplier,
            world_trait_claim_value=_world_trait_claim_value,
            world_trait_claim_text=_world_trait_claim_text,
        )
        self.player_movement = PlayerMovementRuntime(
            self,
            best_cover_candidate=_best_cover_candidate,
            emit_move_access_events=_emit_move_access_events,
            stakeout_progress_snapshot=_stakeout_progress_snapshot,
            stakeout_reveal_interval=STAKEOUT_REVEAL_INTERVAL,
            stakeout_max_reveals=STAKEOUT_MAX_REVEALS,
        )
        self.player_interactions = PlayerInteractionRuntime(
            self,
            infrastructure_target_property=_infrastructure_target_property,
        )
        self.player_travel = PlayerTravelRuntime(self)
        self.sim.events.subscribe("player_action", self.on_player_action)
        self.sim.events.subscribe("property_purchase_execute_request", self.on_property_purchase_execute_request)
        self.sim.events.subscribe("player_hidden_changed", self.on_player_hidden_changed)
        self.sim.events.subscribe("container_transfer_request", self.on_container_transfer_request)
        self.sim.events.subscribe("cache_transfer_request", self.on_cache_transfer_request)

    def on_player_hidden_changed(self, event):
        if bool(event.data.get("active")):
            return
        self.player_movement.clear_stakeout(
            eid=event.data.get("eid"),
            reason=str(event.data.get("reason", "")).strip().lower() or "lost_hidden",
        )

    def _player_interact_direction_state(self):
        state = getattr(self.sim, "player_interact_directions", None)
        if not isinstance(state, dict):
            self.sim.player_interact_directions = {}
            state = self.sim.player_interact_directions
        return state

    def _remember_player_interact_direction(self, eid, dx, dy):
        if eid is None:
            return
        direction = _normalized_direction(dx, dy)
        if direction == (0, 0):
            return
        self._player_interact_direction_state()[int(eid)] = {
            "dx": direction[0],
            "dy": direction[1],
            "tick": int(self.sim.tick),
        }

    def _adjacent_aim_interact_direction(self, eid, pos):
        if eid is None or pos is None:
            return None
        state = getattr(self.sim, "look_ui", None)
        if not isinstance(state, dict):
            return None
        if not bool(state.get("active")):
            return None
        if str(state.get("mode", "city")).strip().lower() != "city":
            return None
        if str(state.get("purpose", "inspect")).strip().lower() not in {"aim", "interact"}:
            return None
        try:
            target_x = int(state.get("x", pos.x))
            target_y = int(state.get("y", pos.y))
            target_z = int(state.get("z", pos.z))
        except (TypeError, ValueError):
            return None
        if int(target_z) != int(pos.z):
            return None
        dx = int(target_x) - int(pos.x)
        dy = int(target_y) - int(pos.y)
        if max(abs(dx), abs(dy)) != 1:
            return None
        direction = _normalized_direction(dx, dy)
        return None if direction == (0, 0) else direction

    def _player_interact_direction(self, eid, pos=None):
        aimed_direction = self._adjacent_aim_interact_direction(eid, pos)
        if aimed_direction is not None:
            return aimed_direction
        if eid is None:
            return None
        state = self._player_interact_direction_state().get(int(eid))
        if not isinstance(state, dict):
            return None
        direction = _normalized_direction(state.get("dx", 0), state.get("dy", 0))
        if direction == (0, 0):
            return None
        return direction

    def _interaction_target_sort_key(self, eid, pos, target_x, target_y, *, stable_tiebreaker=()):
        return _interaction_target_order_key(
            pos.x,
            pos.y,
            target_x,
            target_y,
            preferred_dir=self._player_interact_direction(eid, pos),
            stable_tiebreaker=stable_tiebreaker,
        )

    def _nearest_sabotage_fixture(self, eid, pos):
        return self.player_interactions.nearest_sabotage_fixture(eid, pos)

    def _security_fixture_target_property(self, prop):
        return self.player_interactions.security_fixture_target_property(prop)

    def _player_sabotage_fixture(self, eid, pos, prop):
        return self.player_interactions.player_sabotage_fixture(eid, pos, prop)

    def _vehicle_state_for(self, eid):
        return self.player_travel._vehicle_state_for(eid)

    def _vehicle_property_by_id(self, vehicle_id):
        return self.player_travel._vehicle_property_by_id(vehicle_id)

    def _active_vehicle_property(self, eid):
        return self.player_travel._active_vehicle_property(eid)

    def _vehicle_for_player_action(self, eid, pos, radius=1, *, preferred_dir=None, exact_direction=False):
        return self.player_travel._vehicle_for_player_action(
            eid,
            pos,
            radius=radius,
            preferred_dir=preferred_dir,
            exact_direction=exact_direction,
        )

    def _sync_vehicle_property_position(self, prop, x, y, z=0):
        return self.player_travel._sync_vehicle_property_position(prop, x, y, z=z)

    def _vehicle_fuel_cost_for_chunk(self, vehicle_prop, desc):
        return self.player_travel._vehicle_fuel_cost_for_chunk(vehicle_prop, desc=desc)

    def _enter_vehicle(self, eid, pos, vehicle_prop):
        return self.player_travel._enter_vehicle(eid, pos, vehicle_prop)

    def _exit_vehicle(self, eid, pos):
        return self.player_travel._exit_vehicle(eid, pos)

    def _vehicle_exit_tile_candidates(self, x, y, z=0, *, max_radius=8):
        yield from self.player_travel._vehicle_exit_tile_candidates(x, y, z=z, max_radius=max_radius)

    def _best_vehicle_exit_vehicle_tile(self, x, y, z=0):
        return self.player_travel._best_vehicle_exit_vehicle_tile(x, y, z=z)

    def _best_vehicle_exit_player_tile(self, vehicle_x, vehicle_y, vehicle_z=0):
        return self.player_travel._best_vehicle_exit_player_tile(vehicle_x, vehicle_y, vehicle_z=vehicle_z)

    def _cover_state_for(self, eid):
        return self.sim.ecs.get(CoverState).get(eid)

    def _mode_state_for(self, eid):
        return self.sim.ecs.get(PlayerModeState).get(eid)

    def _inventory_for(self, eid):
        return self.sim.ecs.get(Inventory).get(eid)

    def _equipped_worn_container(self, eid, container_instance_id=None):
        return self.player_interactions.equipped_worn_container(eid, container_instance_id)

    def _worn_container_panel_note(self, runtime):
        return self.player_interactions.worn_container_panel_note(runtime)

    def _refresh_worn_container_panel_state(self, eid, container_instance_id):
        return self.player_interactions.refresh_worn_container_panel_state(eid, container_instance_id)

    def _set_sneak_mode(self, eid, active, reason="manual"):
        return self.player_movement.set_sneak_mode(eid, active, reason=reason)

    def _clear_cover(self, eid, reason):
        return self.player_movement.clear_cover(eid, reason)

    def _handle_toggle_cover(self, eid, pos):
        return self.player_movement.handle_toggle_cover(eid, pos)

    def _handle_cover_hop(self, eid, pos):
        return self.player_movement.handle_cover_hop(eid, pos)

    def _emit_move_access_offense(
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
        return self.player_movement.emit_move_access_offense(
            eid=eid,
            action=action,
            origin_x=origin_x,
            origin_y=origin_y,
            origin_z=origin_z,
            target_x=target_x,
            target_y=target_y,
            target_z=target_z,
        )

    def _refresh_cover_after_move(self, eid, pos, had_cover=False):
        return self.player_movement.refresh_cover_after_move(eid, pos, had_cover=had_cover)

    def _player_owns_property(self, eid, prop):
        return self.property_actions.player_owns_property(eid, prop)

    def _property_for_player_action(self, pos, radius=1):
        return self.property_actions.property_for_player_action(pos, radius=radius)

    def _counts_as_known_location(self, prop):
        return self.property_actions.counts_as_known_location(prop)

    def _discovery_property_at(self, x, y, z):
        return self.property_actions.discovery_property_at(x, y, z)

    def _remember_player_property_discovery(self, eid, prop, *, discovery_mode="sight", confidence=None):
        return self.property_actions.remember_player_property_discovery(
            eid,
            prop,
            discovery_mode=discovery_mode,
            confidence=confidence,
        )

    def _action_target_tuple(self, event, pos):
        data = getattr(event, "data", {}) or {}
        if "target_x" not in data or "target_y" not in data:
            return None
        target_z = data.get("target_z")
        if target_z is None and pos is not None:
            target_z = pos.z
        return (data.get("target_x"), data.get("target_y"), target_z)

    def _handle_door_interaction(self, eid, pos, *, target=None):
        return self.property_actions.handle_door_interaction(eid, pos, target=target)

    def _handle_door_lock_toggle(self, eid, pos, *, target=None):
        return self.property_actions.handle_door_lock_toggle(eid, pos, target=target)

    def _npc_for_player_action(self, eid, pos, radius=1, *, preferred_dir=None, exact_direction=False):
        positions = self.sim.ecs.get(Position)
        ais = self.sim.ecs.get(AI)
        players = self.sim.ecs.get(PlayerControlled)
        identities = self.sim.ecs.get(CreatureIdentity)
        occupations = self.sim.ecs.get(Occupation)

        candidates = []
        for other_eid, other_pos in positions.items():
            if other_eid == eid:
                continue
            if players.get(other_eid):
                continue
            if not ais.get(other_eid):
                continue
            if other_pos.z != pos.z:
                continue

            dist = _manhattan(pos.x, pos.y, other_pos.x, other_pos.y)
            if dist <= 0 or dist > radius:
                continue

            step = _normalized_direction(other_pos.x - pos.x, other_pos.y - pos.y)
            if preferred_dir is not None and exact_direction and step != _normalized_direction(preferred_dir[0], preferred_dir[1]):
                continue

            identity = identities.get(other_eid)
            humanish = int(bool(identity and identity.taxonomy_class == "hominid"))
            has_job = int(bool(occupations.get(other_eid)))
            if preferred_dir is not None:
                sort_key = _interaction_target_order_key(
                    pos.x,
                    pos.y,
                    other_pos.x,
                    other_pos.y,
                    preferred_dir=preferred_dir,
                    stable_tiebreaker=(-humanish, -has_job, other_eid),
                )
                candidates.append((sort_key, other_eid))
            else:
                candidates.append(((-humanish, -has_job, dist, other_eid), other_eid))

        if not candidates:
            return None

        candidates.sort(key=lambda row: row[0])
        return candidates[0][1]

    def _talk_npc_for_player_action(self, eid, pos, *, target_eid=None, force_target=False):
        positions = self.sim.ecs.get(Position)
        ais = self.sim.ecs.get(AI)
        players = self.sim.ecs.get(PlayerControlled)
        identities = self.sim.ecs.get(CreatureIdentity)
        occupations = self.sim.ecs.get(Occupation)

        def _valid_talk_target(other_eid, *, max_range=2):
            if other_eid is None:
                return None
            try:
                other_eid = int(other_eid)
            except (TypeError, ValueError):
                return None
            if other_eid == eid:
                return None
            if players.get(other_eid):
                return None
            if not ais.get(other_eid):
                return None
            other_pos = positions.get(other_eid)
            if not other_pos or other_pos.z != pos.z:
                return None
            dist = _manhattan(pos.x, pos.y, other_pos.x, other_pos.y)
            if dist <= 0 or dist > int(max_range):
                return None
            if not _has_line_of_sight(
                self.sim,
                int(pos.x),
                int(pos.y),
                int(pos.z),
                int(other_pos.x),
                int(other_pos.y),
                int(other_pos.z),
            ):
                return None
            return other_eid

        targeted = _valid_talk_target(target_eid, max_range=2)
        if targeted is not None or force_target:
            return targeted

        def _collect(max_range):
            candidates = []
            for other_eid, other_pos in positions.items():
                if other_eid == eid:
                    continue
                if players.get(other_eid):
                    continue
                if not ais.get(other_eid):
                    continue
                if other_pos.z != pos.z:
                    continue
                dist = _manhattan(pos.x, pos.y, other_pos.x, other_pos.y)
                if dist <= 0 or dist > max_range:
                    continue
                if not _has_line_of_sight(
                    self.sim,
                    int(pos.x),
                    int(pos.y),
                    int(pos.z),
                    int(other_pos.x),
                    int(other_pos.y),
                    int(other_pos.z),
                ):
                    continue
                identity = identities.get(other_eid)
                humanish = int(bool(identity and identity.taxonomy_class == "hominid"))
                has_job = int(bool(occupations.get(other_eid)))
                sort_key = _interaction_target_order_key(
                    pos.x,
                    pos.y,
                    other_pos.x,
                    other_pos.y,
                    stable_tiebreaker=(dist, -humanish, -has_job, other_eid),
                )
                candidates.append((sort_key, other_eid))
            if not candidates:
                return None
            candidates.sort(key=lambda row: row[0])
            return candidates[0][1]

        target = _collect(1)
        if target is not None:
            return target
        return _collect(2)

    def _is_protected_property(self, prop):
        if not prop:
            return False
        return _property_access_level(prop) != "public"

    def _offense_score_for(self, action, context="ordinary"):
        base = ACTION_OFFENSE_BASE.get(action, 0)
        bonus = ACTION_OFFENSE_CONTEXT_BONUS.get(context, 0)
        return max(0, min(100, base + bonus))

    def _emit_action_offense(self, eid, action, x, y, z, context="ordinary", score=None, **extra):
        if score is None:
            score = self._offense_score_for(action, context=context)
        if score <= 0:
            return

        payload = {
            "offender_eid": eid,
            "action": action,
            "context": context,
            "offense_score": score,
            "offense_tier": _offense_tier(score),
            "x": x,
            "y": y,
            "z": z,
            "radius": _offense_notice_radius(score),
        }
        if isinstance(extra, dict):
            payload.update(extra)
        if not any(
            key in payload
            for key in ("observer_eids", "accountable_observer_eids", "observation_channels", "witnessed", "witnesses")
        ):
            payload.update(
                observation_payload_for_position(
                    self.sim,
                    x,
                    y,
                    z,
                    exclude_eid=eid,
                    offender_eid=eid,
                    observation_channels=("actor_witness",),
                )
            )
        self.sim.emit(Event("action_offense", **payload))

    def _player_has_item(self, eid, item_id):
        inventory = self.sim.ecs.get(Inventory).get(eid)
        if not inventory:
            return False
        target = str(item_id or "").strip().lower()
        if not target:
            return False
        for entry in inventory.items:
            if str(entry.get("item_id", "")).strip().lower() != target:
                continue
            if int(entry.get("quantity", 0)) > 0:
                return True
        return False

    def _property_key_entry_for(self, eid, prop):
        inventory = self._inventory_for(eid)
        if not inventory or not isinstance(prop, dict):
            return None
        state = property_lock_state(prop)
        if not state["key_id"]:
            return None
        return inventory_matching_property_key(
            inventory,
            property_id=prop.get("id"),
            key_id=state["key_id"],
        )

    def _property_credential_access_for(self, eid, prop):
        if not isinstance(prop, dict):
            return None

        kind = str(prop.get("kind", "")).strip().lower()
        if kind != "building":
            entry = self._property_key_entry_for(eid, prop)
            if not entry:
                return None
            return {
                "mode": "mechanical_key",
                "entry": entry,
                "reason": "key",
            }

        intrusion_access = _controller_intrusion_access_for_actor(self.sim, eid, prop)
        if intrusion_access:
            return {
                "mode": str(intrusion_access.get("mode", "badge")).strip().lower() or "badge",
                "entry": None,
                "reason": str(intrusion_access.get("reason", "spoofed_access")).strip().lower() or "spoofed_access",
            }

        controller = _property_access_controller(self.sim, prop)
        required_tier = max(1, _facade()._int_or_default(controller.get("required_credential_tier"), 1))
        inventory = self._inventory_for(eid)
        if inventory:
            entry = inventory_matching_property_credential(
                inventory,
                property_id=prop.get("id"),
                key_id=property_lock_state(prop)["key_id"],
                allowed_kinds=controller.get("accepted_credentials", ()),
                minimum_tier=required_tier,
            )
            if entry:
                return {
                    "mode": str(controller.get("credential_mode", "mechanical_key")).strip().lower() or "mechanical_key",
                    "entry": entry,
                    "reason": "credential",
                }

        if str(controller.get("credential_mode", "")).strip().lower() == "biometric":
            holder = _controller_holder_for_actor(controller, eid)
            if holder and _facade()._int_or_default(holder.get("credential_tier"), 0) >= required_tier:
                return {
                    "mode": "biometric",
                    "entry": None,
                    "reason": "biometric_authorization",
                }
        return None

    def _property_lock_access_for(self, eid, prop):
        if not isinstance(prop, dict):
            return None

        owner_eid = prop.get("owner_eid")
        try:
            owner_eid = int(owner_eid) if owner_eid is not None else None
        except (TypeError, ValueError):
            owner_eid = None
        if owner_eid is not None and int(eid) == owner_eid:
            return {
                "mode": "owner",
                "entry": None,
                "reason": "owner",
            }
        if str(prop.get("owner_tag", "") or "").strip().lower() == "player":
            return {
                "mode": "owner",
                "entry": None,
                "reason": "owner",
            }
        return self._property_credential_access_for(eid, prop)

    def _access_skill(self, eid):
        return _actor_skill(self.sim, eid, "intrusion")

    def _access_tool_context(self, prop=None, *, ignition=False, context=None):
        return _access_tool_context_for(self.sim, prop, ignition=ignition, context=context)

    def _access_tool_terms_for(self, eid, prop=None, *, ignition=False, context=None):
        return _access_tool_terms_for_actor(
            self.sim,
            eid,
            prop,
            ignition=ignition,
            context=context,
        )

    def _access_override_score(self, eid, *, tool_terms=None, ignition=False):
        return _access_override_score_for_actor(
            self.sim,
            eid,
            tool_terms=tool_terms,
            ignition=ignition,
        )

    def _lock_override_required(self, prop, *, tool_terms=None, ignition=False):
        return _lock_override_required_for_prop(
            self.sim,
            prop,
            tool_terms=tool_terms,
            ignition=ignition,
        )

    def _vehicle_hotwire_score(self, eid, *, tool_terms=None):
        return self._access_override_score(eid, tool_terms=tool_terms, ignition=True)

    def _emit_property_lock_tamper(self, eid, prop, *, x, y, z, method, tool_terms=None):
        _emit_property_lock_tamper_event(
            self.sim,
            eid,
            prop,
            x=x,
            y=y,
            z=z,
            method=method,
            tool_terms=tool_terms,
        )

    def _emit_vehicle_tamper(self, eid, vehicle_prop, method):
        if not isinstance(vehicle_prop, dict):
            return
        vx = int(vehicle_prop.get("x", 0))
        vy = int(vehicle_prop.get("y", 0))
        vz = int(vehicle_prop.get("z", 0))
        lock_state = property_lock_state(vehicle_prop)
        observation = observation_payload_for_position(
            self.sim,
            vx,
            vy,
            vz,
            exclude_eid=eid,
            offender_eid=eid,
            observation_channels=("actor_witness",),
        )
        witnessed = bool(observation.get("witnessed", False))
        severity_score = min(100, 22 + (lock_state["lock_tier"] * 8))
        self.sim.emit(Event(
            "property_tamper",
            offender_eid=eid,
            property_id=vehicle_prop.get("id"),
            owner_eid=vehicle_prop.get("owner_eid"),
            x=vx,
            y=vy,
            z=vz,
            **observation,
            access_level="protected",
            severity_score=severity_score,
            severity_label=_trespass_label_from_score(severity_score),
            standing_reason="none",
            ingress_method=method,
        ))
        if witnessed:
            self._emit_action_offense(
                eid=eid,
                action="vehicle_theft",
                context="tamper",
                x=vx,
                y=vy,
                z=vz,
            )

    def _attempt_vehicle_theft(self, eid, pos, vehicle_prop):
        if not isinstance(vehicle_prop, dict):
            return False, "invalid_vehicle", "blocked"

        tool_terms = self._access_tool_terms_for(eid, vehicle_prop, ignition=True)
        score = self._vehicle_hotwire_score(eid, tool_terms=tool_terms)
        required = self._lock_override_required(vehicle_prop, tool_terms=tool_terms, ignition=True)
        if not tool_terms.get("enabled") and score + 1.5 < required:
            self._emit_vehicle_tamper(eid, vehicle_prop, method="locked_vehicle_entry")
            return False, "key_required", "blocked"
        method = "hotwire" if tool_terms.get("enabled") else "ignition_override"
        self._emit_vehicle_tamper(eid, vehicle_prop, method=method)
        context = self._access_tool_context(vehicle_prop, ignition=True)
        attempt = _resolve_access_skill_check(
            self.sim,
            eid=eid,
            prop=vehicle_prop,
            context=context,
            channel="vehicle_theft",
            score=score,
            required=required,
            tool_terms=tool_terms,
            allow_fumble=True,
        )
        if not attempt["success"]:
            _maybe_damage_access_tool(
                self.sim,
                eid,
                tool_terms,
                prop=vehicle_prop,
                score=attempt["score"],
                required=attempt["required"],
                context=context,
                channel="vehicle_theft",
                fumbled=attempt["fumbled"],
            )
            if attempt["fumbled"]:
                return False, "hotwire_fumble", "blocked"
            return False, "hotwire_failed", "blocked"

        metadata = _property_metadata(vehicle_prop)
        metadata["property_locked"] = False
        metadata["vehicle_hotwired"] = True
        metadata["vehicle_hotwire_tick"] = int(self.sim.tick)
        return True, method, method

    def _locked_ordinary_entry_property(self, eid, pos, target_x, target_y, target_z):
        return self.property_ingress.locked_ordinary_entry_property(
            eid,
            pos,
            target_x,
            target_y,
            target_z,
        )

    def _attempt_locked_property_entry(self, eid, prop, *, target_x, target_y, target_z):
        return self.property_ingress.attempt_locked_property_entry(
            eid,
            prop,
            target_x=target_x,
            target_y=target_y,
            target_z=target_z,
        )

    def _handle_ingress_action(self, eid, pos, ingress_mode):
        return self.property_ingress.handle_ingress_action(eid, pos, ingress_mode)

    def _nearest_camera_fixture(self, eid, pos):
        return self.player_interactions.nearest_camera_fixture(eid, pos)

    def _player_disable_camera(self, eid, pos, prop):
        return self.player_interactions.player_disable_camera(eid, pos, prop)

    def _nearest_alarm_fixture(self, eid, pos):
        return self.player_interactions.nearest_alarm_fixture(eid, pos)

    def _player_disable_alarm(self, eid, pos, prop):
        return self.player_interactions.player_disable_alarm(eid, pos, prop)

    CACHE_MAX_STACKS = 8

    def _container_inventory_entries(self, prop_id, *, container_kind="container"):
        return self.player_interactions.container_inventory_entries(
            prop_id,
            container_kind=container_kind,
        )

    def _cache_panel_mission_note(self, prop):
        return self.player_interactions.cache_panel_mission_note(prop)

    def _container_panel_note(self, prop, *, container_kind=None):
        return self.player_interactions.container_panel_note(
            prop,
            container_kind=container_kind,
        )

    def _container_label(self, container_kind=None):
        return self.player_interactions.container_label(container_kind)

    def _nearest_cache_fixture(self, eid, pos):
        return self.player_interactions.nearest_cache_fixture(eid, pos)

    def _nearest_business_scene_cache(self, eid, pos):
        return self.player_interactions.nearest_business_scene_cache(eid, pos)

    def _open_property_container_ui(self, eid, prop, *, container_kind="container", container_label=None):
        return self.player_interactions.open_property_container_ui(
            eid,
            prop,
            container_kind=container_kind,
            container_label=container_label,
        )

    def _player_interact_cache(self, eid, pos, prop):
        return self.player_interactions.player_interact_cache(eid, pos, prop)

    def _player_interact_business_scene_cache(self, eid, pos, prop):
        return self.player_interactions.player_interact_business_scene_cache(eid, pos, prop)

    def _withdraw_from_worn_container(self, eid, container_instance_id, *, selected_index=0):
        return self.player_interactions.withdraw_from_worn_container(
            eid,
            container_instance_id,
            selected_index=selected_index,
        )

    def _withdraw_from_container(self, eid, prop_id, *, selected_index=0, container_kind="container"):
        return self.player_interactions.withdraw_from_container(
            eid,
            prop_id,
            selected_index=selected_index,
            container_kind=container_kind,
        )

    def _withdraw_from_cache(self, eid, prop_id, *, selected_index=0):
        return self.player_interactions.withdraw_from_cache(
            eid,
            prop_id,
            selected_index=selected_index,
        )

    def _deposit_to_worn_container(self, eid, container_instance_id, *, instance_id=None):
        return self.player_interactions.deposit_to_worn_container(
            eid,
            container_instance_id,
            instance_id=instance_id,
        )

    def _deposit_to_container(self, eid, prop_id, *, instance_id=None, container_kind="container"):
        return self.player_interactions.deposit_to_container(
            eid,
            prop_id,
            instance_id=instance_id,
            container_kind=container_kind,
        )

    def _deposit_to_cache(self, eid, prop_id, *, instance_id=None):
        return self.player_interactions.deposit_to_cache(
            eid,
            prop_id,
            instance_id=instance_id,
        )

    def on_container_transfer_request(self, event):
        eid = event.data.get("eid")
        if eid is None:
            return
        if _entity_is_downed(self.sim, eid):
            _apply_downed_actor_state(self.sim, eid, tick=self.sim.tick)
            return
        container_kind = str(event.data.get("container_kind", "") or "").strip().lower() or "container"
        container_instance_id = str(event.data.get("container_instance_id", "") or "").strip()
        container_view = str(
            event.data.get("container_view", event.data.get("cache_view", "container"))
        ).strip().lower() or "container"
        container_view = "pack" if container_view == "pack" else "container"
        selected_index = int(event.data.get("selected_index", 0) or 0)
        if container_kind == "worn":
            if not container_instance_id:
                return
            if container_view == "pack":
                self._deposit_to_worn_container(
                    eid,
                    container_instance_id,
                    instance_id=event.data.get("instance_id"),
                )
                return
            self._withdraw_from_worn_container(
                eid,
                container_instance_id,
                selected_index=selected_index,
            )
            return
        prop_id = str(event.data.get("property_id", "") or "").strip()
        if not prop_id:
            return
        if container_view == "pack":
            self._deposit_to_container(
                eid,
                prop_id,
                instance_id=event.data.get("instance_id"),
                container_kind=container_kind,
            )
            return
        self._withdraw_from_container(
            eid,
            prop_id,
            selected_index=selected_index,
            container_kind=container_kind,
        )

    def on_cache_transfer_request(self, event):
        data = dict(getattr(event, "data", {}) or {})
        data.setdefault("container_kind", "cache")
        cache_view = str(data.get("cache_view", "cache")).strip().lower() or "cache"
        data.setdefault("container_view", "pack" if cache_view == "pack" else "container")
        self.on_container_transfer_request(Event(event.type, **data))

    def _clear_stakeout(self, eid=None, *, reason=""):
        return self.player_movement.clear_stakeout(eid=eid, reason=reason)

    def _active_property_opportunities(self, prop_id):
        return _active_property_opportunities(self.sim, prop_id)

    def _try_advance_stakeout(self, eid, pos):
        return self.player_movement.try_advance_stakeout(eid, pos)

    def _handle_interact_action(self, eid, pos, *, force_direction=False, target=None):
        return self.player_interactions.handle_interact_action(
            eid,
            pos,
            force_direction=force_direction,
            target=target,
        )

    def _dialog_ui_state(self):
        state = getattr(self.sim, "dialog_ui", None)
        if not isinstance(state, dict):
            state = {}
            self.sim.dialog_ui = state
        state.setdefault("open", False)
        state.setdefault("kind", "conversation")
        state.setdefault("npc_eid", None)
        state.setdefault("property_id", None)
        state.setdefault("title", "Conversation")
        state.setdefault("subtitle", "")
        state.setdefault("transcript", [])
        state.setdefault("topics", [])
        state.setdefault("selected_index", 0)
        state.setdefault("scroll", 0)
        state.setdefault("hint", "")
        state.setdefault("new_topic_ids", [])
        state.setdefault("close_pending", False)
        state.setdefault("machine_action", None)
        state.setdefault("backup_cursor_mark", None)
        state.setdefault("backup_cursor_pending_topic", "")
        return state

    def _rehydrate_dialog_pause(self, eid=None):
        if eid is None:
            eid = getattr(self.sim, "player_eid", None)
        if eid is None:
            return None
        return _rehydrate_entity_knowledge(
            self.sim,
            eid,
            radius=18,
            search_radius=10,
            current_tick=int(getattr(self.sim, "tick", 0)),
            reason="dialog_pause",
        )

    def _finance_service_label(self, service):
        return str(service or "").strip().replace("_", " ") or "service"

    def _property_purchase_lines(self, context):
        context = context if isinstance(context, dict) else {}
        prop = context.get("prop") if isinstance(context.get("prop"), dict) else {}
        archetype = str(context.get("archetype", "") or "").strip().replace("_", " ")
        price = int(context.get("price", 0) or 0)
        credits = int(context.get("credits", 0) or 0)
        owner_eid = context.get("owner_eid")
        owner_tag = str(context.get("owner_tag", "") or "").strip().lower()

        services = []
        if _property_is_storefront(prop):
            services.append("shopping")
        services.extend(
            self._finance_service_label(service)
            for service in _finance_services_for_property(prop)
            if str(service).strip()
        )
        services.extend(
            _site_service_label(service).strip().lower()
            for service in _site_services_for_property(prop)
            if str(service).strip()
        )
        deduped_services = [label for label in dict.fromkeys(label for label in services if str(label).strip())]
        owner_line = "Seller: city listing." if owner_eid is None or owner_tag in {"", "city"} else f"Seller: {owner_tag} holder."
        lines = [
            owner_line,
            f"Type: {archetype or 'building'}.",
            f"Price: {_credit_amount_label(price)} | Wallet: {_credit_amount_label(credits)}.",
        ]
        if deduped_services:
            lines.append(f"Known uses: {', '.join(deduped_services[:4])}.")
        if bool(_property_is_public(prop)):
            lines.append("Status: publicly accessible location.")
        return lines

    def _present_property_purchase_result(self, title, lines, *, property_id=None):
        state = self._dialog_ui_state()
        transcript = [str(line).strip() for line in list(lines or ()) if str(line).strip()]
        if not transcript:
            transcript = ["No sale details are available right now."]
        self.sim.set_time_paused(True, reason="dialog")
        self._rehydrate_dialog_pause()
        state.update({
            "open": True,
            "kind": "service_menu",
            "npc_eid": None,
            "property_id": property_id,
            "title": str(title or "Property Purchase").strip() or "Property Purchase",
            "subtitle": "",
            "transcript": transcript,
            "topics": [],
            "selected_index": 0,
            "scroll": max(0, len(transcript) - 1),
            "hint": "Press Space to close.",
            "new_topic_ids": [],
            "close_pending": True,
            "machine_action": None,
            "service_menu_mode": "property_purchase_result",
        })
        return True

    def _open_property_purchase_prompt(self, eid, pos, *, target_property_id=None):
        context = self.property_actions.purchase_context(eid, pos, target_property_id=target_property_id)
        reason = str(context.get("reason", "") or "").strip().lower()
        prop = context.get("prop") if isinstance(context.get("prop"), dict) else None
        if reason == "no_property" or prop is None:
            self.property_actions.handle_purchase(eid, pos, target_property_id=target_property_id)
            return False

        property_id = str(context.get("property_id", "") or "").strip()
        property_name = str(context.get("property_name", property_id or "Property") or property_id or "Property").strip() or "Property"
        title = f"Property Purchase: {property_name}"
        lines = self._property_purchase_lines(context)
        if reason == "already_owner":
            lines.append("You already own this property.")
            return self._present_property_purchase_result(title, lines, property_id=property_id)
        if reason == "not_for_sale":
            lines.append("This property is not currently for sale.")
            return self._present_property_purchase_result(title, lines, property_id=property_id)
        if reason == "insufficient_funds":
            lines.append("You do not have enough credits to close this purchase.")
            return self._present_property_purchase_result(title, lines, property_id=property_id)
        if reason == "missing_assets":
            lines.append("No asset profile is available for this purchase.")
            return self._present_property_purchase_result(title, lines, property_id=property_id)

        state = self._dialog_ui_state()
        self.sim.set_time_paused(True, reason="dialog")
        self._rehydrate_dialog_pause(eid=eid)
        state.update({
            "open": True,
            "kind": "service_menu",
            "npc_eid": None,
            "property_id": property_id,
            "title": title,
            "subtitle": "",
            "transcript": lines + ["Buy this property?"],
            "topics": [
                {"id": f"property_purchase:confirm:{property_id}", "label": f"Confirm purchase [{_credit_amount_label(int(context.get('price', 0) or 0))}]"},
                {"id": f"property_purchase:cancel:{property_id}", "label": "Cancel"},
            ],
            "selected_index": 0,
            "scroll": 0,
            "hint": "Confirm to spend credits and transfer ownership.",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
            "service_menu_mode": "property_purchase",
        })
        return True

    def _handle_purchase(self, eid, pos, *, target_property_id=None):
        return self.property_actions.handle_purchase(eid, pos, target_property_id=target_property_id)

    def _find_walkable_near(self, x, y, z=0, radius=8):
        return self.player_travel._find_walkable_near(x, y, z=z, radius=radius)

    def _teleport_entity(self, eid, pos, new_x, new_y, new_z, reason="teleport"):
        return self.player_travel._teleport_entity(eid, pos, new_x, new_y, new_z, reason=reason)

    def _chunk_center(self, chunk_coord):
        return self.player_travel._chunk_center(chunk_coord)

    def _set_zoom_mode(self, eid, pos, mode, **kwargs):
        return self.player_travel._set_zoom_mode(eid, pos, mode, **kwargs)

    def _handle_overworld_travel(self, eid, pos, dx, dy):
        return self.player_travel._handle_overworld_travel(eid, pos, dx, dy)

    def _handle_local_vehicle_move(self, eid, pos, dx, dy):
        return self.player_travel._handle_local_vehicle_move(eid, pos, dx, dy)

    def _handle_local_vehicle_momentum(self, eid, pos):
        return self.player_travel._handle_local_vehicle_momentum(eid, pos)

    def _can_enter_overworld_from_local_vehicle(self, eid, pos):
        return self.player_travel._can_enter_quick_travel_from_local_vehicle(eid, pos)

    def _overworld_view_only_for(self, eid):
        return self.player_travel._overworld_view_only_for(eid)

    def _overworld_visit_state_for(self, eid):
        return _player_overworld_visit_state(self.sim, eid)

    def _remember_overworld_chunk_memory(self, eid, chunk, **kwargs):
        return _remember_overworld_chunk_memory(self.sim, eid, chunk, **kwargs)

    def _overworld_discovery_lines(self, eid, cx, cy, radius=1):
        return self.player_travel._overworld_discovery_lines(eid, cx, cy, radius=radius)

    def _award_overworld_discovery(self, eid, chunk, desc, interest, travel):
        return self.player_travel._award_overworld_discovery(eid, chunk, desc, interest, travel)

    def _overworld_markers_for(self, eid):
        return self.player_overworld._overworld_markers_for(eid)

    def _next_overworld_marker_id(self, eid):
        return self.player_overworld._next_overworld_marker_id(eid)

    def _marker_descriptor(self, chunk):
        return self.player_overworld._marker_descriptor(chunk)

    def _chunk_direction(self, from_chunk, to_chunk):
        return self.player_overworld._chunk_direction(from_chunk, to_chunk)

    def _overworld_chunk_inspect_line(self, eid, origin_chunk, chunk, *, label=None, knowledge=None):
        return self.player_overworld._overworld_chunk_inspect_line(
            eid,
            origin_chunk,
            chunk,
            label=label,
            knowledge=knowledge,
        )

    def _marker_line(self, eid, marker, origin_chunk, *, knowledge=None):
        return self.player_overworld._marker_line(eid, marker, origin_chunk, knowledge=knowledge)

    def _set_overworld_marker(self, eid, chunk, *, label="", property_id=None):
        return self.player_overworld._set_overworld_marker(
            eid,
            chunk,
            label=label,
            property_id=property_id,
        )

    def _handle_overworld_marker_add(self, eid, pos):
        return self.player_overworld._handle_overworld_marker_add(eid, pos)

    def _handle_overworld_marker_list(self, eid, pos, limit=8):
        return self.player_overworld._handle_overworld_marker_list(eid, pos, limit=limit)

    def _handle_overworld_marker_nearest(self, eid, pos):
        return self.player_overworld._handle_overworld_marker_nearest(eid, pos)

    def _set_look_inspect_text(self, text):
        return self.player_look.set_look_inspect_text(text)

    def _describe_overworld_cursor(self, eid, pos, cx, cy):
        return self.player_overworld._describe_overworld_cursor(eid, pos, cx, cy)

    def _handle_cursor_examine(self, eid, pos, event):
        mode = str(event.data.get("cursor_mode", getattr(self.sim, "zoom_mode", "city"))).lower()
        announce = bool(event.data.get("announce", False))
        look_state = getattr(self.sim, "look_ui", None)
        if not isinstance(look_state, dict):
            look_state = {}
            self.sim.look_ui = look_state
        look_state["mode"] = mode
        purpose = str(look_state.get("purpose", "inspect")).lower()

        if mode == "overworld":
            self.player_overworld.handle_cursor_examine(
                eid,
                pos,
                event,
                announce=announce,
                purpose=purpose,
            )
            return

        self.player_look.handle_cursor_examine(
            eid,
            pos,
            event,
            announce=announce,
            purpose=purpose,
        )

    def _handle_scan_action(self, eid, pos, zoom_mode, radius=8):
        radius = max(1, int(radius))

        if zoom_mode == "overworld":
            self.player_overworld.handle_scan_action(eid, pos)
            return

        self.player_look.handle_scan_action(eid, pos, radius=radius)

    def on_player_action(self, event):
        action = event.data.get("action")
        eid = event.data.get("eid")

        positions = self.sim.ecs.get(Position)
        pos = positions.get(eid)
        if not pos:
            return
        zoom_mode = str(getattr(self.sim, "zoom_mode", "city")).lower()

        if _entity_is_downed(self.sim, eid):
            _apply_downed_actor_state(self.sim, eid, tick=self.sim.tick)
            if action != "use_item":
                self.sim.emit(Event(
                    "player_action_blocked",
                    eid=eid,
                    action=action,
                    reason="downed",
                ))
            return

        if action in CONTROL_LAPSE_TURN_ACTIONS and control_lapse_active(self.sim, eid):
            self.sim.emit(Event(
                "player_action_blocked",
                eid=eid,
                action=action,
                reason="control_lapse",
            ))
            return

        if action == "zoom_overworld":
            self._set_sneak_mode(eid, False, reason="zoom")
            self._set_zoom_mode(eid=eid, pos=pos, mode="overworld", view_only=True, entry_reason="map_view")
            return

        if action == "zoom_city_enter":
            vehicle_state = self._vehicle_state_for(eid)
            if zoom_mode == "overworld":
                if vehicle_state and vehicle_state.in_vehicle and not self._overworld_view_only_for(eid):
                    self._set_zoom_mode(eid=eid, pos=pos, mode="city")
                else:
                    self._set_zoom_mode(eid=eid, pos=pos, mode="city")
                return
            if vehicle_state and vehicle_state.in_vehicle:
                self._exit_vehicle(eid=eid, pos=pos)
                return
            self._set_zoom_mode(eid=eid, pos=pos, mode="city")
            return

        if action == "overworld_travel":
            if zoom_mode != "overworld":
                return
            self._handle_overworld_travel(
                eid=eid,
                pos=pos,
                dx=int(event.data.get("dx", 0)),
                dy=int(event.data.get("dy", 0)),
            )
            return

        if self.player_overworld.handle_player_action(
            action,
            eid,
            pos,
            zoom_mode=zoom_mode,
            event=event,
        ):
            return

        if action == "move":
            if zoom_mode == "overworld":
                return
            vehicle_state = self._vehicle_state_for(eid)
            if vehicle_state and vehicle_state.in_vehicle:
                self._handle_local_vehicle_move(
                    eid,
                    pos,
                    dx=int(event.data.get("dx", 0)),
                    dy=int(event.data.get("dy", 0)),
                )
                return
            dx, dy, _misdirected = maybe_misdirect_move(
                self.sim,
                eid,
                int(event.data.get("dx", 0)),
                int(event.data.get("dy", 0)),
            )
            self.player_movement.handle_move_action(
                eid,
                pos,
                dx=dx,
                dy=dy,
            )
            return

        if action == "vehicle_move":
            if zoom_mode == "overworld":
                return
            self._handle_local_vehicle_move(
                eid,
                pos,
                dx=int(event.data.get("dx", 0)),
                dy=int(event.data.get("dy", 0)),
            )
            return

        if action == "vehicle_momentum":
            if zoom_mode == "overworld":
                return
            self._handle_local_vehicle_momentum(eid, pos)
            return

        if action == "side_entry":
            if zoom_mode == "overworld":
                return
            self._handle_ingress_action(eid, pos, ingress_mode="side_entry")
            return

        if action == "window_entry":
            if zoom_mode == "overworld":
                return
            self._handle_ingress_action(eid, pos, ingress_mode="window_entry")
            return

        if action == "forced_breach":
            if zoom_mode == "overworld":
                return
            self._handle_ingress_action(eid, pos, ingress_mode="forced_breach")
            return

        if action == "floor_change":
            self.player_movement.handle_floor_change(
                eid,
                pos,
                dz=event.data.get("dz", 0),
                zoom_mode=zoom_mode,
            )
            return

        if action == "wait":
            self.player_movement.handle_wait_action(eid, pos)
            return

        if action == "toggle_sneak":
            self.player_movement.handle_toggle_sneak_action(eid)
            return

        if action == "toggle_door_lock":
            self._handle_door_lock_toggle(eid, pos, target=self._action_target_tuple(event, pos))
            return

        if action == "scan":
            self._handle_scan_action(eid=eid, pos=pos, zoom_mode=zoom_mode, radius=8)
            return

        if action == "tactical_read":
            if zoom_mode == "overworld":
                return
            target = {}
            if event.data.get("target_x") is not None and event.data.get("target_y") is not None:
                target = {
                    "x": event.data.get("target_x"),
                    "y": event.data.get("target_y"),
                    "z": event.data.get("target_z", pos.z),
                }
            if event.data.get("target_eid") is not None:
                target["target_eid"] = event.data.get("target_eid")
            perform_tactical_read(
                self.sim,
                eid,
                target=target,
                purpose=str(event.data.get("purpose", "") or ""),
            )
            return

        if action == "examine_cursor":
            self._handle_cursor_examine(eid=eid, pos=pos, event=event)
            return

        if action == "talk":
            if self.property_actions.handle_talk_action(
                eid,
                pos,
                target_eid=event.data.get("target_eid"),
                force_target=bool(event.data.get("force_target")),
            ):
                self.sim.turn_advance_requested = True
            return

        if action == "service_interact":
            self.property_actions.handle_service_interact_action(eid, pos)
            return

        if action == "interact":
            self._handle_interact_action(
                eid,
                pos,
                force_direction=bool(event.data.get("force_direction")),
                target=self._action_target_tuple(event, pos),
            )
            return

        if action == "purchase_property":
            self._open_property_purchase_prompt(eid, pos)
            return

        if action == "toggle_cover":
            self.player_movement.handle_toggle_cover(eid, pos)
            return

        if action == "cover_hop":
            if zoom_mode == "overworld":
                return
            self.player_movement.handle_cover_hop(eid, pos)
            return

        if action == "fire_weapon":
            self.sim.emit(Event(
                "weapon_fire_request",
                eid=eid,
                reason="manual",
                manual_aim=bool(event.data.get("manual_aim", False)),
                target_x=event.data.get("target_x"),
                target_y=event.data.get("target_y"),
                target_z=event.data.get("target_z"),
                target_eid=event.data.get("target_eid"),
            ))
            return

        if action == "cycle_weapon":
            self.sim.emit(Event(
                "weapon_cycle_request",
                eid=eid,
                step=1,
            ))
            return

    def on_property_purchase_execute_request(self, event):
        eid = event.data.get("eid")
        if eid != getattr(self.sim, "player_eid", None):
            return
        pos = self.sim.ecs.get(Position).get(eid)
        if not pos:
            return
        self._handle_purchase(eid, pos, target_property_id=event.data.get("property_id"))
