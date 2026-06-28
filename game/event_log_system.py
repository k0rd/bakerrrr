"""Extracted systems from ``game.systems``: EventLogSystem."""

from engine.sites import layout_chunk_site, site_gameplay_profile
from engine.systems import System
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
from game.economy import (
    chunk_economy_profile,
    item_market_bias,
    pick_career_for_workplace,
    store_supply_profile,
    workplace_archetype_weight,
)
from game.items import (
    ITEM_CATALOG,
    apply_item_durability_loss,
    credstick_total_credits,
    is_credstick_item,
    item_display_name,
    merge_item_stack_metadata,
    prepare_item_stack_metadata,
)
from game.item_semantics import (
    appraise_item_for_actor,
    item_display_name_for_actor,
    item_is_identified_for_actor,
    item_unknown_inspect_text_for_actor,
)
from game.organizations import local_protective_pressure_snapshot
from game.quick_travel_ramps import map_mode_active
from game.system_support.actor_attention_runtime import record_area_warmth
from game.system_support.awareness_runtime import event_observation_accountability
from game.system_support.crime_plan_runtime import (
    CRIME_PLAN_OBSERVATION_WITNESS,
    record_crime_plan_observation,
)
from game.world_event_presentation import world_event_effect_summary
from game.objective_progress import (
    award_objective_progress,
    objective_progress_explain_delta,
)
from game.opportunities import (
    SPECIALTY_OPPORTUNITY_THEMES,
    append_external_opportunity,
    evaluate_opportunity_board,
    evaluate_opportunity_facts,
    format_reward_text,
    opportunity_intel_for_observer,
    opportunity_distance_text,
    opportunity_known_count,
    opportunity_source_label,
    refresh_dynamic_opportunities,
    reveal_opportunity_to_observer,
    resolve_external_opportunity,
    resolve_opportunities,
    seed_run_opportunities,
    stage_active_opportunities,
    opportunity_target_arrival_notes,
)
from game.property_keys import (
    can_receive_property_key,
    ensure_actor_has_property_credential,
    ensure_actor_has_property_key,
    ensure_property_lock,
    inventory_matching_property_credential,
    inventory_matching_property_key,
    is_public_owner_tag,
    remove_actor_property_credentials,
    property_lock_state,
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


_BUSINESS_POSTURE_PHASE_LABELS = {
    "owner_screening": "Screened Entry",
    "paperwork_surge": "Paperwork Surge",
    "manifest_check": "Manifest Check",
    "dispatch_surge": "Dispatch Surge",
    "day_labor_call": "Crew Call",
    "clinic_outreach": "Clinic Outreach",
    "mutual_aid_table": "Mutual Aid Table",
    "loading_push": "Loading Push",
}
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
from game.system_support.intrusion_runtime import (
    _ingress_method_label,
    _ingress_mode_label,
    _is_operable_door_aperture,
    _is_side_aperture,
    _is_window_aperture,
    _quiet_unwitnessed_tamper,
    _trespass_label_from_score,
)
from game.system_support.entity_naming import _entity_display_name
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
from game.system_support.environment_hazard_runtime import environment_hazard_player_note
from game.service_runtime import (
    CASINO_GAME_SERVICE_IDS,
    TRANSIT_SERVICE_IDS,
    _building_site_service_seed_token,
    _casino_game_title,
    _chunk_site_kinds,
    _credit_amount_label,
    _int_or_default,
    _overworld_discovery_profile,
    _overworld_identity_profile,
    _overworld_discovery_summary_bits,
    _overworld_legend_line,
    _overworld_travel_profile,
    _overworld_travel_summary_bits,
    _service_menu_option_label,
    _site_service_label,
    _storefront_service_profile,
    _transit_inventory_label,
    _transit_services_connecting_chunks,
    _transit_service_log_prefix,
    _transit_service_mode_label,
    _transit_service_profile,
    _transit_service_title,
    _transit_token_amount_label,
    _vehicle_sale_stats_text,
    _site_service_seed_token,
)
from game.vehicles import (
    generate_chunk_vehicle_records,
    roll_vehicle_profile,
    vehicle_metadata,
    vehicle_services_for_archetype,
)
from game.run_objectives import evaluate_run_objective
from game.location_presentation_runtime import (
    _entity_legend_line,
    _location_description_snapshot,
    _property_contact_hint,
    _property_interaction_modes,
    _property_summary,
)
from game.dialogue_runtime import (
    _contact_benefit_labels,
    _disguise_role_label,
    _infrastructure_target_property,
)
from game.skills import (
    access_prep_skill_terms as _access_prep_skill_terms,
    actor_skill as _actor_skill,
    dialogue_prep_skill_terms as _dialogue_prep_skill_terms,
    scan_skill_terms as _scan_skill_terms,
    skill_label as _skill_label,
    trade_skill_terms as _trade_skill_terms,
)
from game.skill_ui import (
    skill_change_reason_label as _skill_change_reason_label,
    skill_debug_lines as _skill_debug_lines,
    skill_hud_status_chunks as _skill_hud_status_chunks,
)
from game.system_support.combat_targeting_runtime import (
    _dir_label,
    _target_condition_descriptor,
)
from game.status_ui_runtime import (
    _floor_label,
    _humanize_slug,
    _sentence_from_note,
    _status_effect_label,
)
from game.ui_text_runtime import (
    _line_segments,
    _line_text,
    _line_with_prefix,
    _segment,
    _tick_duration_label,
)
from game.weapons import WEAPON_CATALOG, roll_weapon_instance, weapon_by_id

def _facade():
    from game import systems as facade

    return facade


def _world_events_module():
    from game import systems_world_events as world_events

    return world_events


def _chunk_chebyshev_distance(*args, **kwargs):
    return _world_events_module()._chunk_chebyshev_distance(*args, **kwargs)


def _clear_world_event_revealed(*args, **kwargs):
    return _world_events_module()._clear_world_event_revealed(*args, **kwargs)


def _mark_world_event_revealed(*args, **kwargs):
    return _world_events_module()._mark_world_event_revealed(*args, **kwargs)


def _world_event_chunk_coord(*args, **kwargs):
    return _world_events_module()._world_event_chunk_coord(*args, **kwargs)


def _world_event_revealed_ids(*args, **kwargs):
    return _world_events_module()._world_event_revealed_ids(*args, **kwargs)


def active_world_events_near_chunk(*args, **kwargs):
    return _world_events_module().active_world_events_near_chunk(*args, **kwargs)


def world_event_visible_to_viewer(*args, **kwargs):
    return _world_events_module().world_event_visible_to_viewer(*args, **kwargs)


QUIET_NOISE_CAUSES = {
    "move",
    "cover_hop",
    "floor_change",
    "wait",
    "interact",
    "toggle_door_lock",
    "pickup_item",
    "drop_item",
    "use_item",
    "banking",
    "insurance",
    "trade_buy",
    "trade_sell",
    "overworld_travel",
    "zoom_overworld",
    "zoom_city_enter",
}

COMBAT_NOISE_CAUSES = {
    "melee_attack",
    "fire_weapon",
    "throw_item",
    "thrown_item",
    "explosion",
}

_WORLD_EVENT_PLAYER_REVEAL_RADIUS = 1

def _building_entry_description(*args, **kwargs):
    return _facade()._building_entry_description(*args, **kwargs)

def _ingress_label(*args, **kwargs):
    return _facade()._ingress_label(*args, **kwargs)

def _room_entry_description(*args, **kwargs):
    return _facade()._room_entry_description(*args, **kwargs)


def _possessive_label(label):
    label = str(label or "").strip()
    if not label:
        return ""
    return f"{label}'" if label.lower().endswith("s") else f"{label}'s"


class EventLogSystem(System):
    def on_world_event_started(self, event):
        if not world_event_visible_to_viewer(self.sim, event.data, self.player_eid):
            return
        # Log the start of a world event with its label and flavor text
        event_id = _int_or_default(event.data.get("event_id"), 0)
        if event_id > 0:
            _mark_world_event_revealed(self.sim, event_id)
        label = event.data.get("label", "World Event")
        flavor = event.data.get("flavor", "Something unusual is happening in the world.")
        effect = world_event_effect_summary(event.data)
        effect_text = f" Effect: {effect}." if effect else ""
        self._log(
            f"[WORLD EVENT BEGINS] {label}: {flavor}{effect_text}",
            channel="world",
            priority="high",
            dedupe_window=10,
            dedupe_key=f"world_event_start_{event_id or label}",
        )

    def on_world_event_ended(self, event):
        if not world_event_visible_to_viewer(self.sim, event.data, self.player_eid):
            _clear_world_event_revealed(self.sim, _int_or_default(event.data.get("event_id"), 0))
            return
        # Log the end of a world event with its label
        event_id = _int_or_default(event.data.get("event_id"), 0)
        label = event.data.get("label", "World Event")
        effect = world_event_effect_summary(event.data, ending=True)
        effect_text = f" Effect: {effect}." if effect else ""
        self._log(
            f"[WORLD EVENT ENDED] {label} has concluded.{effect_text}",
            channel="world",
            priority="normal",
            dedupe_window=10,
            dedupe_key=f"world_event_end_{event_id or label}",
        )
        _clear_world_event_revealed(self.sim, event_id)

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.run_warning_flags = set()
        self.last_location_building_token = ""
        self.last_location_room_token = ""

        player_pos = self.sim.ecs.get(Position).get(self.player_eid)
        if player_pos is not None:
            snapshot = _location_description_snapshot(self.sim, player_pos.x, player_pos.y, player_pos.z)
            self.last_location_building_token = snapshot["building_token"]
            self.last_location_room_token = snapshot["room_token"]

        self.sim.events.subscribe("move_blocked", self.on_move_blocked)
        self.sim.events.subscribe("entity_moved", self.on_entity_moved)
        self.sim.events.subscribe("floor_change_blocked", self.on_floor_change_blocked)
        self.sim.events.subscribe("entity_changed_floor", self.on_entity_changed_floor)
        self.sim.events.subscribe("noise", self.on_noise)
        self.sim.events.subscribe("creature_hazard_triggered", self.on_creature_hazard_triggered)
        self.sim.events.subscribe("environmental_hazard_triggered", self.on_environmental_hazard_triggered)
        self.sim.events.subscribe("fire_started", self.on_fire_started)
        self.sim.events.subscribe("fire_contained", self.on_fire_contained)
        self.sim.events.subscribe("fire_burned_out", self.on_fire_burned_out)
        self.sim.events.subscribe("world_condition_triggered", self.on_world_condition_triggered)
        self.sim.events.subscribe("scan_report", self.on_scan_report)
        self.sim.events.subscribe("look_mode_toggled", self.on_look_mode_toggled)
        self.sim.events.subscribe("cursor_examined", self.on_cursor_examined)
        self.sim.events.subscribe("property_self_discovered", self.on_property_self_discovered)
        self.sim.events.subscribe("player_mode_toggled", self.on_player_mode_toggled)
        self.sim.events.subscribe("player_hidden_changed", self.on_player_hidden_changed)
        self.sim.events.subscribe("interact_empty", self.on_interact_empty)
        self.sim.events.subscribe("property_interact", self.on_property_interact)
        self.sim.events.subscribe("access_panel_used", self.on_access_panel_used)
        self.sim.events.subscribe("access_panel_blocked", self.on_access_panel_blocked)
        self.sim.events.subscribe("npc_interacted", self.on_npc_interacted)
        self.sim.events.subscribe("dialogue_opportunity_hint", self.on_dialogue_opportunity_hint)
        self.sim.events.subscribe("eavesdrop_opportunity_hint", self.on_eavesdrop_opportunity_hint)
        self.sim.events.subscribe("eavesdrop_property_hint", self.on_eavesdrop_property_hint)
        self.sim.events.subscribe("dialogue_guard_resolution", self.on_dialogue_guard_resolution)
        self.sim.events.subscribe("contact_learned", self.on_contact_learned)
        self.sim.events.subscribe("site_service_used", self.on_site_service_used)
        self.sim.events.subscribe("site_service_blocked", self.on_site_service_blocked)
        self.sim.events.subscribe("hunting_carcass_harvested", self.on_hunting_carcass_harvested)
        self.sim.events.subscribe("hunting_carcass_blocked", self.on_hunting_carcass_blocked)
        self.sim.events.subscribe("flora_harvested", self.on_flora_harvested)
        self.sim.events.subscribe("flora_harvest_blocked", self.on_flora_harvest_blocked)
        self.sim.events.subscribe("flora_planted", self.on_flora_planted)
        self.sim.events.subscribe("flora_planting_blocked", self.on_flora_planting_blocked)
        self.sim.events.subscribe("flora_crossbred", self.on_flora_crossbred)
        self.sim.events.subscribe("flora_crossbreed_blocked", self.on_flora_crossbreed_blocked)
        self.sim.events.subscribe("potted_plant_placed", self.on_potted_plant_placed)
        self.sim.events.subscribe("potted_plant_picked_up", self.on_potted_plant_picked_up)
        self.sim.events.subscribe("herbal_medicine_crafted", self.on_herbal_medicine_crafted)
        self.sim.events.subscribe("herbal_recipe_purchased", self.on_herbal_recipe_purchased)
        self.sim.events.subscribe("hunter_party_carcass_dressed", self.on_hunter_party_carcass_dressed)
        self.sim.events.subscribe("site_intel_report", self.on_site_intel_report)
        self.sim.events.subscribe("vehicle_delivered", self.on_vehicle_delivered)
        self.sim.events.subscribe("property_closing_time_warning", self.on_property_closing_time_warning)
        self.sim.events.subscribe("npc_investigate", self.on_npc_investigate)
        self.sim.events.subscribe("npc_warn_property", self.on_npc_warn_property)
        self.sim.events.subscribe("npc_protect_ally", self.on_npc_protect_ally)
        self.sim.events.subscribe("npc_defend_property", self.on_npc_defend_property)
        self.sim.events.subscribe("npc_crime_attempt_started", self.on_npc_crime_attempt_started)
        self.sim.events.subscribe("npc_crime_attempt_resolved", self.on_npc_crime_attempt_resolved)
        self.sim.events.subscribe("crime_plan_disrupted", self.on_crime_plan_disrupted)
        self.sim.events.subscribe("npc_affiliation_attempt_resolved", self.on_npc_affiliation_attempt_resolved)
        self.sim.events.subscribe("npc_need_critical", self.on_npc_need_critical)
        self.sim.events.subscribe("action_offense", self.on_action_offense)
        self.sim.events.subscribe("player_action_blocked", self.on_player_action_blocked)
        self.sim.events.subscribe("npc_offended", self.on_npc_offended)
        self.sim.events.subscribe("npc_conversation_refused", self.on_npc_conversation_refused)
        self.sim.events.subscribe("npc_eject_target", self.on_npc_eject_target)
        self.sim.events.subscribe("npc_ejection_complied", self.on_npc_ejection_complied)
        self.sim.events.subscribe("npc_ejection_refused", self.on_npc_ejection_refused)
        self.sim.events.subscribe("item_picked_up", self.on_item_picked_up)
        self.sim.events.subscribe("item_pickup_blocked", self.on_item_pickup_blocked)
        self.sim.events.subscribe("item_dropped", self.on_item_dropped)
        self.sim.events.subscribe("item_drop_blocked", self.on_item_drop_blocked)
        self.sim.events.subscribe("item_used", self.on_item_used)
        self.sim.events.subscribe("item_use_blocked", self.on_item_use_blocked)
        self.sim.events.subscribe("report_device_used", self.on_report_device_used)
        self.sim.events.subscribe("justice_vehicle_misuse_barked", self.on_justice_vehicle_misuse_barked)
        self.sim.events.subscribe("item_stolen", self.on_item_stolen)
        self.sim.events.subscribe("business_scene_posture_started", self.on_business_scene_posture_started)
        self.sim.events.subscribe("ambient_ritual_started", self.on_ambient_ritual_started)
        self.sim.events.subscribe("business_scene_nuisance", self.on_business_scene_nuisance)
        self.sim.events.subscribe("camera_scrutiny", self.on_camera_scrutiny)
        self.sim.events.subscribe("camera_alerted", self.on_camera_alerted)
        self.sim.events.subscribe("status_applied", self.on_status_applied)
        self.sim.events.subscribe("status_expired", self.on_status_expired)
        self.sim.events.subscribe("movement_misdirected", self.on_movement_misdirected)
        self.sim.events.subscribe("bonus_move_used", self.on_bonus_move_used)
        self.sim.events.subscribe("control_lapse_started", self.on_control_lapse_started)
        self.sim.events.subscribe("drug_blackout_started", self.on_drug_blackout_started)
        self.sim.events.subscribe("drug_blackout_resolved", self.on_drug_blackout_resolved)
        self.sim.events.subscribe("inventory_panel_toggled", self.on_inventory_panel_toggled)
        self.sim.events.subscribe("inventory_inspected", self.on_inventory_inspected)
        self.sim.events.subscribe("trade_panel_toggled", self.on_trade_panel_toggled)
        self.sim.events.subscribe("trade_panel_blocked", self.on_trade_panel_blocked)
        self.sim.events.subscribe("cover_taken", self.on_cover_taken)
        self.sim.events.subscribe("cover_shifted", self.on_cover_shifted)
        self.sim.events.subscribe("cover_hopped", self.on_cover_hopped)
        self.sim.events.subscribe("cover_left", self.on_cover_left)
        self.sim.events.subscribe("cover_blocked", self.on_cover_blocked)
        self.sim.events.subscribe("stakeout_started", self.on_stakeout_started)
        self.sim.events.subscribe("stakeout_ended", self.on_stakeout_ended)
        self.sim.events.subscribe("rumor_shared", self.on_rumor_shared)
        self.sim.events.subscribe("npc_socialized", self.on_npc_socialized)
        self.sim.events.subscribe("npc_partner_acknowledged", self.on_npc_partner_acknowledged)
        self.sim.events.subscribe("animal_socialized", self.on_animal_socialized)
        self.sim.events.subscribe("armor_equipped", self.on_armor_equipped)
        self.sim.events.subscribe("armor_removed", self.on_armor_removed)
        self.sim.events.subscribe("appearance_item_equipped", self.on_appearance_item_equipped)
        self.sim.events.subscribe("appearance_item_unequipped", self.on_appearance_item_unequipped)
        self.sim.events.subscribe("disguise_equipped", self.on_disguise_equipped)
        self.sim.events.subscribe("disguise_removed", self.on_disguise_removed)
        self.sim.events.subscribe("disguise_blown", self.on_disguise_blown)
        self.sim.events.subscribe("weapon_equipped", self.on_weapon_equipped)
        self.sim.events.subscribe("weapon_removed", self.on_weapon_removed)
        self.sim.events.subscribe("weapon_cycle_blocked", self.on_weapon_cycle_blocked)
        self.sim.events.subscribe("weapon_fired", self.on_weapon_fired)
        self.sim.events.subscribe("melee_attack", self.on_melee_attack)
        self.sim.events.subscribe("weapon_fire_blocked", self.on_weapon_fire_blocked)
        self.sim.events.subscribe("projectile_impact", self.on_projectile_impact)
        self.sim.events.subscribe("smoke_cloud_released", self.on_smoke_cloud_released)
        self.sim.events.subscribe("aerosol_cloud_released", self.on_aerosol_cloud_released)
        self.sim.events.subscribe("aerosol_exposure_triggered", self.on_aerosol_exposure_triggered)
        self.sim.events.subscribe("entity_damaged", self.on_entity_damaged)
        self.sim.events.subscribe("actor_deprivation_damage", self.on_actor_deprivation_damage)
        self.sim.events.subscribe("player_downed", self.on_player_downed)
        self.sim.events.subscribe("player_recovered_from_downed", self.on_player_recovered_from_downed)
        self.sim.events.subscribe("player_critical_saved", self.on_player_critical_saved)
        self.sim.events.subscribe("player_killed", self.on_player_killed)
        self.sim.events.subscribe("npc_downed", self.on_npc_downed)
        self.sim.events.subscribe("npc_medical_rescue_applied", self.on_npc_medical_rescue_applied)
        self.sim.events.subscribe("npc_killed", self.on_npc_killed)
        self.sim.events.subscribe("explosion_triggered", self.on_explosion_triggered)
        self.sim.events.subscribe("combat_overlay_entered", self.on_combat_overlay_entered)
        self.sim.events.subscribe("combat_overlay_exited", self.on_combat_overlay_exited)
        self.sim.events.subscribe("property_trespass", self.on_property_trespass)
        self.sim.events.subscribe("property_tamper", self.on_property_tamper)
        self.sim.events.subscribe("property_owner_changed", self.on_property_owner_changed)
        self.sim.events.subscribe("property_purchased", self.on_property_purchased)
        self.sim.events.subscribe("player_business_acquired", self.on_player_business_acquired)
        self.sim.events.subscribe("player_business_staff_hired", self.on_player_business_staff_hired)
        self.sim.events.subscribe("player_business_staff_fired", self.on_player_business_staff_fired)
        self.sim.events.subscribe("player_business_staff_resigned", self.on_player_business_staff_resigned)
        self.sim.events.subscribe("property_purchase_blocked", self.on_property_purchase_blocked)
        self.sim.events.subscribe("trade_bought", self.on_trade_bought)
        self.sim.events.subscribe("street_vendor_purchase", self.on_street_vendor_purchase)
        self.sim.events.subscribe("street_buy_transaction", self.on_street_buy_transaction)
        self.sim.events.subscribe("npc_item_purchased", self.on_npc_item_purchased)
        self.sim.events.subscribe("trade_buy_blocked", self.on_trade_buy_blocked)
        self.sim.events.subscribe("trade_sold", self.on_trade_sold)
        self.sim.events.subscribe("trade_sell_blocked", self.on_trade_sell_blocked)
        self.sim.events.subscribe("bank_transaction", self.on_bank_transaction)
        self.sim.events.subscribe("banking_action_blocked", self.on_banking_action_blocked)
        self.sim.events.subscribe("insurance_policy_purchased", self.on_insurance_policy_purchased)
        self.sim.events.subscribe("insurance_action_blocked", self.on_insurance_action_blocked)
        self.sim.events.subscribe("insurance_policy_expired", self.on_insurance_policy_expired)
        self.sim.events.subscribe("insurance_claim_paid", self.on_insurance_claim_paid)
        self.sim.events.subscribe("insurance_claim_blocked", self.on_insurance_claim_blocked)
        self.sim.events.subscribe("insurance_item_saved", self.on_insurance_item_saved)
        self.sim.events.subscribe("insurance_medical_boost", self.on_insurance_medical_boost)
        self.sim.events.subscribe("downed_item_lost", self.on_downed_item_lost)
        self.sim.events.subscribe("quit_requested", self.on_quit_requested)
        self.sim.events.subscribe("zoom_mode_changed", self.on_zoom_mode_changed)
        self.sim.events.subscribe("zoom_mode_blocked", self.on_zoom_mode_blocked)
        self.sim.events.subscribe("vehicle_entered", self.on_vehicle_entered)
        self.sim.events.subscribe("vehicle_exited", self.on_vehicle_exited)
        self.sim.events.subscribe("vehicle_onramp_nearby", self.on_vehicle_onramp_nearby)
        self.sim.events.subscribe("vehicle_action_blocked", self.on_vehicle_action_blocked)
        self.sim.events.subscribe("vehicle_collision", self.on_vehicle_collision)
        self.sim.events.subscribe("vehicle_crash", self.on_vehicle_crash)
        self.sim.events.subscribe("overworld_travelled", self.on_overworld_travelled)
        self.sim.events.subscribe("overworld_discovery_found", self.on_overworld_discovery_found)
        self.sim.events.subscribe("overworld_marker_added", self.on_overworld_marker_added)
        self.sim.events.subscribe("overworld_marker_updated", self.on_overworld_marker_updated)
        self.sim.events.subscribe("overworld_marker_none", self.on_overworld_marker_none)
        self.sim.events.subscribe("overworld_marker_report", self.on_overworld_marker_report)
        self.sim.events.subscribe("opportunity_added", self.on_opportunity_added)
        self.sim.events.subscribe("opportunity_completed", self.on_opportunity_completed)
        self.sim.events.subscribe("opportunity_failed", self.on_opportunity_failed)
        self.sim.events.subscribe("opportunity_report", self.on_opportunity_report)
        self.sim.events.subscribe("rival_operator_seeded", self.on_rival_operator_seeded)
        self.sim.events.subscribe("rival_operator_spotted", self.on_rival_operator_spotted)
        self.sim.events.subscribe("rival_operator_activity", self.on_rival_operator_activity)
        self.sim.events.subscribe("rival_opportunity_resolved", self.on_rival_opportunity_resolved)
        self.sim.events.subscribe("rival_followup_seeded", self.on_rival_followup_seeded)
        self.sim.events.subscribe("rival_operator_wounded", self.on_rival_operator_wounded)
        self.sim.events.subscribe("rival_operator_removed", self.on_rival_operator_removed)
        self.sim.events.subscribe("objective_progress_awarded", self.on_objective_progress_awarded)
        self.sim.events.subscribe("final_operation_unlocked", self.on_final_operation_unlocked)
        self.sim.events.subscribe("final_operation_target_identified", self.on_final_operation_target_identified)
        self.sim.events.subscribe("final_operation_target_recovered", self.on_final_operation_target_recovered)
        self.sim.events.subscribe("final_operation_failed", self.on_final_operation_failed)
        self.sim.events.subscribe("final_operation_completed", self.on_final_operation_completed)
        self.sim.events.subscribe("run_concluded", self.on_run_concluded)
        self.sim.events.subscribe("run_pressure_changed", self.on_run_pressure_changed)
        self.sim.events.subscribe("run_pressure_tier_changed", self.on_run_pressure_tier_changed)
        self.sim.events.subscribe("run_pressure_mitigated", self.on_run_pressure_mitigated)
        self.sim.events.subscribe("justice_record_changed", self.on_justice_record_changed)
        self.sim.events.subscribe("justice_wanted_tier_changed", self.on_justice_wanted_tier_changed)
        self.sim.events.subscribe("actor_detained", self.on_actor_detained)
        self.sim.events.subscribe("justice_inventory_inspected", self.on_justice_inventory_inspected)
        self.sim.events.subscribe("justice_questioning_resolved", self.on_justice_questioning_resolved)
        self.sim.events.subscribe("justice_booking_completed", self.on_justice_booking_completed)
        self.sim.events.subscribe("organization_vigilante_response", self.on_organization_vigilante_response)
        self.sim.events.subscribe("incident_dispatch_started", self.on_incident_dispatch_started)
        self.sim.events.subscribe("organization_heat_tier_changed", self.on_organization_heat_tier_changed)
        self.sim.events.subscribe("organization_standing_tier_changed", self.on_organization_standing_tier_changed)
        self.sim.events.subscribe("skill_rating_changed", self.on_skill_rating_changed)
        self.sim.events.subscribe("lighting_phase_changed", self.on_lighting_phase_changed)
        self.sim.events.subscribe("chunk_focus_changed", self.on_chunk_focus_changed)
        self.sim.events.subscribe("npc_suppressed", self.on_npc_suppressed)
        self.sim.events.subscribe("npc_surrendered", self.on_npc_surrendered)

    def _log(self, text, *, channel="general", priority="normal", dedupe_window=None, dedupe_key=None):
        self.sim.log.add(
            text,
            channel=channel,
            priority=priority,
            dedupe_window=dedupe_window,
            dedupe_key=dedupe_key,
        )

    def _log_rich(self, segments, *, text=None, channel="general", priority="normal", dedupe_window=None, dedupe_key=None):
        self.sim.log.add_rich(
            segments,
            text=text,
            channel=channel,
            priority=priority,
            dedupe_window=dedupe_window,
            dedupe_key=dedupe_key,
        )

    def _warn_once(self, key, text, *, channel="alerts", priority="high"):
        key = str(key).strip().lower()
        if not key or key in self.run_warning_flags:
            return False
        self.run_warning_flags.add(key)
        self._log(text, channel=channel, priority=priority)
        return True

    def _npc_label(self, eid, fallback="NPC"):
        if eid is None:
            return str(fallback or "NPC")
        name = _entity_display_name(self.sim, eid, title_case=True)
        if name and str(name).strip().lower() != "entity":
            return name
        return f"NPC {eid}"

    def _property_name(self, property_id, fallback="property"):
        property_id = str(property_id or "").strip()
        if property_id:
            prop = self.sim.properties.get(property_id)
            if isinstance(prop, dict):
                name = str(prop.get("name", prop.get("id", property_id)) or property_id).strip()
                if name:
                    return name
        return str(fallback or "property")

    def _property_name_if_known(self, property_id):
        property_id = str(property_id or "").strip()
        if not property_id:
            return ""
        prop = self.sim.properties.get(property_id)
        if not isinstance(prop, dict):
            return ""
        return str(prop.get("name", prop.get("id", property_id)) or property_id).strip()

    def _event_property_name(self, event, fallback="property"):
        property_name = str(event.data.get("property_name", "") or "").strip()
        if property_name:
            return property_name
        return self._property_name(event.data.get("property_id"), fallback=fallback)

    def _event_site_name(self, event):
        property_name = str(event.data.get("property_name", "") or "").strip()
        if property_name:
            return property_name
        x = event.data.get("x")
        y = event.data.get("y")
        z = event.data.get("z")
        try:
            if x is None or y is None or z is None:
                raise ValueError
            prop = self.sim.property_at(int(x), int(y), int(z)) or _property_covering(self.sim, int(x), int(y), int(z))
        except (TypeError, ValueError):
            prop = None
        if isinstance(prop, dict):
            return str(prop.get("name", prop.get("id", "property")) or "property").strip() or "property"
        return ""

    def _event_place_name(self, event):
        property_name = str(event.data.get("property_name", "") or "").strip()
        if property_name:
            return property_name
        provider_name = str(event.data.get("provider_name", "") or "").strip()
        if provider_name:
            return provider_name
        property_name = self._property_name_if_known(event.data.get("property_id"))
        if property_name:
            return property_name
        return self._event_site_name(event)

    def _event_item_label(self, event, *, fallback="item"):
        item_name = str(event.data.get("item_name", "") or "").strip()
        if item_name:
            return item_name
        item_id = str(event.data.get("item_id", "") or "").strip().lower()
        if item_id:
            return item_display_name(item_id, item_catalog=ITEM_CATALOG)
        return str(fallback or "item")

    def _action_event_label(self, action, *, fallback="action"):
        action = str(action or "").strip().lower()
        labels = {
            "fire_weapon": "gunfire",
            "melee_attack": "an assault",
            "use_item": "item use",
            "purchase_property": "an illegal purchase attempt",
            "forced_breach": "a forced breach",
            "window_entry": "a window entry",
            "side_entry": "a side entry",
            "toggle_door_lock": "lock tampering",
        }
        if action in labels:
            return labels[action]
        if action:
            return action.replace("_", " ")
        return str(fallback or "action")

    def _justice_incident_cause_text(self, event):
        incident_type = str(event.data.get("incident_type", "") or "").strip().lower()
        incident_label = str(event.data.get("incident_label", incident_type.replace("_", " ")) or "").strip()
        note = str(event.data.get("note", "") or "").strip()
        property_name = self._event_property_name(event, fallback="").strip()
        witnessed = bool(event.data.get("incident_witnessed", False))
        unseen_prefix = "unseen " if not witnessed else ""

        if incident_type == "trespass":
            severity = note.replace("_", " ").strip() or incident_label or "trespass"
            if property_name:
                return f"{unseen_prefix}{severity} at {property_name}"
            return f"{unseen_prefix}{severity}"
        if incident_type == "tamper":
            return f"{unseen_prefix}tampering at {property_name}" if property_name else f"{unseen_prefix}tampering"
        if incident_type == "theft":
            item_name = note or incident_label or "theft"
            if property_name:
                return f"theft of {item_name} at {property_name}"
            return f"theft of {item_name}"
        if incident_type == "contraband":
            if property_name:
                return f"visible contraband use at {property_name}"
            return "visible contraband use"
        if incident_type in VIOLENT_OFFENSE_CONTEXTS:
            action_slug = note.split("/", 1)[0].strip().lower() if note else ""
            action_text = self._action_event_label(action_slug, fallback=incident_label or "violence")
            if property_name:
                return f"{action_text} at {property_name}"
            return action_text
        if incident_label and property_name:
            return f"{incident_label} at {property_name}"
        return incident_label or property_name or "an incident"

    def _objective_progress_channel_label(self, channel):
        channel = str(channel or "").strip().lower()
        labels = {
            "talk": "conversation",
            "contact": "new contacts",
            "trade": "trade",
            "site_service": "local services",
            "site_intel": "site intel",
            "discovery": "scouting",
            "opportunity": "side work",
        }
        if channel in labels:
            return labels[channel]
        if channel:
            return channel.replace("_", " ")
        return "field work"

    def _current_objective_title(self):
        objective_eval = evaluate_run_objective(self.sim, self.player_eid)
        if not isinstance(objective_eval, dict):
            return ""
        return str(objective_eval.get("title", "") or "").strip()

    def _opportunity_completion_text(self, completion_reason):
        text = str(completion_reason or "").strip()
        if not text:
            return "you met the local handoff conditions"
        normalized = text.replace("_", " ").strip()
        if normalized.startswith("entered target chunk"):
            return "you reached the target area"
        if normalized == "requirements met":
            return "you met the local handoff conditions"
        return normalized

    def _pressure_cause_text(self, event):
        source = str(event.data.get("source", "pressure") or "pressure").strip().lower()
        reason = str(event.data.get("reason", "") or "").strip().lower()
        place_name = self._event_place_name(event)
        place_suffix = f" at {place_name}" if place_name else ""
        witnessed = bool(event.data.get("witnessed", False))
        unseen_prefix = "unseen " if not witnessed else ""

        if source == "offense":
            action_key = reason.split("/", 1)[0].strip().lower()
            context = str(event.data.get("context", "") or "").strip().lower()
            if context == "contraband_use":
                return f"visible contraband{place_suffix}" if place_name else "visible contraband"
            action_text = self._action_event_label(action_key, fallback="trouble")
            return f"{action_text}{place_suffix}" if place_name else action_text
        if source == "trespass":
            severity = str(event.data.get("severity_label", reason or "trespass") or "trespass").replace("_", " ").strip()
            if place_name:
                return f"{unseen_prefix}{severity} at {place_name}"
            return f"{unseen_prefix}{severity}".strip()
        if source == "tamper":
            if place_name:
                return f"{unseen_prefix}tampering at {place_name}"
            return f"{unseen_prefix}tampering".strip()
        if source == "dialogue":
            tactic = str(event.data.get("tactic", "dialogue") or "dialogue").strip().lower()
            outcome = str(event.data.get("outcome", "wary") or "wary").strip().lower()
            if outcome == "deescalated":
                detail = "talking a guard down"
            elif outcome == "aggravated":
                detail = "pushing a guard the wrong way"
            else:
                detail = f"a tense {tactic.replace('_', ' ')} with a guard"
            return f"{detail}{place_suffix}" if place_name else detail
        if source == "shelter":
            return f"lying low{place_suffix}" if place_name else "lying low"
        if source == "banking":
            kind = str(
                event.data.get("transaction_kind", event.data.get("kind", "transaction")) or "transaction"
            ).strip().lower()
            if kind == "debt_payment":
                detail = "paying down justice debt"
            else:
                detail = "fresh banking paperwork"
            return f"{detail}{place_suffix}" if place_name else detail
        if source == "insurance":
            policy_name = str(event.data.get("policy_name", "") or "").strip()
            detail = f"buying {policy_name}" if policy_name else "buying cover"
            return f"{detail}{place_suffix}" if place_name else detail
        if source == "lay_low":
            return "keeping your head down"
        if source == "passive_decay":
            return "letting time pass without new trouble"
        if source == "warning":
            return f"drawing a warning{place_suffix}" if place_name else "drawing a warning"
        if source == "defense":
            return f"triggering a defense response{place_suffix}" if place_name else "triggering a defense response"
        if reason:
            return reason.replace("_", " ")
        if place_name:
            return f"{source.replace('_', ' ')} at {place_name}"
        return source.replace("_", " ")

    def _log_npc_message(self, eid, text, *, channel="social", priority="normal", dedupe_window=None, dedupe_key=None):
        message = str(text or "").strip()
        if not message:
            return
        if eid is None:
            self._log(
                message,
                channel=channel,
                priority=priority,
                dedupe_window=dedupe_window,
                dedupe_key=dedupe_key,
            )
            return
        entry = _entity_legend_line(self.sim, eid, message, player_eid=self.player_eid)
        segments = _line_segments(entry)
        if segments:
            self._log_rich(
                segments,
                text=_line_text(entry),
                channel=channel,
                priority=priority,
                dedupe_window=dedupe_window,
                dedupe_key=dedupe_key,
            )
        else:
            self._log(
                _line_text(entry),
                channel=channel,
                priority=priority,
                dedupe_window=dedupe_window,
                dedupe_key=dedupe_key,
            )

    def _entity_log_color(self, eid):
        if eid is None:
            return None
        entry = _entity_legend_line(self.sim, eid, "", player_eid=self.player_eid)
        for segment in _line_segments(entry) or ():
            if isinstance(segment, dict) and segment.get("color"):
                return segment.get("color")
        return None

    def _log_visible_social_quote(
        self,
        speaker_eid,
        partner_eid,
        speaker,
        partner,
        quote,
        *,
        channel="social",
        priority="low",
        dedupe_window=None,
        dedupe_key=None,
    ):
        speaker_color = self._entity_log_color(speaker_eid)
        partner_color = self._entity_log_color(partner_eid)
        prefix = _entity_legend_line(self.sim, speaker_eid, "", player_eid=self.player_eid)
        segments = list(_line_segments(prefix) or ())
        if segments:
            segments.append(_segment(" "))
        segments.extend((
            _segment(speaker, color=speaker_color),
            _segment(", to "),
            _segment(partner, color=partner_color),
            _segment(': "'),
            _segment(quote, color=speaker_color),
            _segment('"'),
        ))
        text = "".join(str(segment.get("text", "")) for segment in segments if isinstance(segment, dict))
        self._log_rich(
            segments,
            text=text,
            channel=channel,
            priority=priority,
            dedupe_window=dedupe_window,
            dedupe_key=dedupe_key,
        )

    def _move_blocked_phrase(self, x, y, z, reason):
        reason = str(reason or "").strip().lower()

        if reason.startswith("blocked_entity:"):
            blocker_text = reason.split(":", 1)[1].strip()
            try:
                blocker_eid = int(blocker_text)
            except (TypeError, ValueError):
                blocker_eid = None
            if blocker_eid is not None:
                return f"You cannot walk past {_entity_display_name(self.sim, blocker_eid, title_case=False)} here."

        prop = None
        if x is not None and y is not None and z is not None:
            prop = self.sim.property_at(x, y, z) or _property_covering(self.sim, x, y, z)
        if prop:
            kind = str(prop.get("kind", "property") or "property").strip().lower()
            if kind == "vehicle":
                return f"You cannot walk by {_vehicle_label(prop)} here."
            if kind in {"fixture", "asset"}:
                label = str(prop.get("name", prop.get("id", kind))).strip() or kind.replace("_", " ")
                return f"You cannot walk by {label} here."

        tile = self.sim.tilemap.tile_at(x, y, z) if x is not None and y is not None and z is not None else None
        if reason == "blocked_animal_doorway":
            return "Animals do not pass through doorways on their own."
        if tile and not tile.walkable:
            glyph = str(getattr(tile, "glyph", "") or "")[:1]
            if glyph in {"#", "B", "b"}:
                return "You cannot walk through the wall here."
            if glyph in {"+", "/"}:
                return "You cannot walk through the doorway here."
            if glyph == "~":
                return "You cannot walk through the water here."
            return "You cannot walk by the obstacle here."

        if reason == "out_of_bounds":
            return "You cannot go that way."
        return "You cannot walk there."

    def _movement_blocked_message(self, *, reason, x=None, y=None, z=None, property_id=None, floor_context=False):
        reason = str(reason or "").strip().lower()

        prop = None
        if property_id is not None:
            prop = self.sim.properties.get(property_id)
        if prop is None and None not in {x, y, z}:
            prop = self.sim.property_at(x, y, z) or _property_covering(self.sim, x, y, z)

        if reason == "locked_property":
            name = str((prop or {}).get("name", (prop or {}).get("id", "The property"))).strip() or "The property"
            controller = _property_access_controller(self.sim, prop) if prop else {}
            requirement = _controller_access_requirement_text(controller)
            return f"{name} is secured. You need {requirement}, a lockpick kit, or exceptional intrusion skill."
        if reason == "closed_property":
            name = str((prop or {}).get("name", (prop or {}).get("id", "The place"))).strip() or "The place"
            return f"{name} is closed."
        if reason == "lock_override_failed":
            name = str((prop or {}).get("name", (prop or {}).get("id", "the lock"))).strip() or "the lock"
            controller = _property_access_controller(self.sim, prop) if prop else {}
            fixture = str(controller.get("fixture_label", "") or "lock").strip() or "lock"
            return f"You fail to defeat the {fixture} at {name}."
        if reason == "lock_override_fumble":
            name = str((prop or {}).get("name", (prop or {}).get("id", "the lock"))).strip() or "the lock"
            controller = _property_access_controller(self.sim, prop) if prop else {}
            fixture = str(controller.get("fixture_label", "") or "lock").strip() or "lock"
            return f"Your hand slips on the {fixture} at {name}; the override attempt fumbles."
        if reason == "door_access_denied":
            if floor_context:
                if isinstance(prop, dict):
                    name = str(prop.get("name", prop.get("id", "that floor"))).strip() or "that floor"
                    return f"You cannot access {name} from here."
                return "You cannot access that floor connection."
            return "You cannot open that door."
        if reason == "power_cut":
            if floor_context:
                return "The elevator is offline. Power is out."
            if isinstance(prop, dict):
                name = str(prop.get("name", prop.get("id", "The site"))).strip() or "The site"
                return f"{name} is offline. Power is out."
            return "That system is offline. Power is out."
        if None not in {x, y, z}:
            return self._move_blocked_phrase(x, y, z, reason)
        if floor_context:
            return "That route to another floor is blocked."
        return "You cannot walk there."

    def _player_has_los_to_position(self, x, y, z):
        state = getattr(self.sim, "visibility_state", None)
        if not isinstance(state, dict):
            return True
        if int(_int_or_default(state.get("tick", -1), -1)) < 0:
            return True
        if state.get("player_eid") not in {None, self.player_eid}:
            return True
        visible = state.get("player_visible")
        if visible is None:
            return True
        if not isinstance(visible, set):
            visible = set(visible or ())
        try:
            key = (int(x), int(y), int(z))
        except (TypeError, ValueError):
            return False
        return key in visible

    def _player_can_perceive_entity(self, eid):
        if eid == self.player_eid:
            return True
        if eid is None:
            return False
        pos = self.sim.ecs.get(Position).get(eid)
        if not pos:
            return False
        return self._player_has_los_to_position(pos.x, pos.y, pos.z)

    def _player_can_perceive_event_position(self, event):
        x = event.data.get("x")
        y = event.data.get("y")
        z = event.data.get("z")
        if x is None or y is None or z is None:
            return False
        return self._player_has_los_to_position(x, y, z)

    def _player_position(self):
        return self.sim.ecs.get(Position).get(self.player_eid)

    def _ground_item_notice_label(self, ground):
        if not isinstance(ground, dict):
            return ""
        item_name = item_display_name_for_actor(
            self.sim,
            self.player_eid,
            ground,
            item_catalog=ITEM_CATALOG,
        )
        qty = int(max(1, _int_or_default(ground.get("quantity"), 1)))
        if qty <= 1:
            return item_name
        return f"{item_name} x{qty}"

    def _ground_item_notice_text(self, x, y, z):
        if map_mode_active(self.sim):
            return "", ""

        ground_items = list(self.sim.ground_items_at(x, y, z=z))
        if not ground_items:
            return "", ""

        labels = [
            self._ground_item_notice_label(ground)
            for ground in ground_items[:2]
            if self._ground_item_notice_label(ground)
        ]
        if not labels:
            return "", ""

        remaining = max(0, len(ground_items) - len(labels))
        if remaining <= 0:
            if len(labels) == 1:
                item_text = labels[0]
            else:
                item_text = f"{labels[0]} and {labels[1]}"
        else:
            suffix = "item" if remaining == 1 else "items"
            item_text = f"{', '.join(labels)}, and {remaining} more {suffix}"

        signature = ",".join(
            f"{str(ground.get('ground_item_id', '')).strip()}:{int(max(1, _int_or_default(ground.get('quantity'), 1)))}"
            for ground in ground_items
        )
        return f"You see {item_text} here.", signature

    def _emit_location_entry_descriptions(self, event):
        current = _location_description_snapshot(
            self.sim,
            event.data.get("x"),
            event.data.get("y"),
            event.data.get("z"),
        )
        previous = _location_description_snapshot(
            self.sim,
            event.data.get("old_x"),
            event.data.get("old_y"),
            event.data.get("old_z"),
        )

        previous_building_token = previous["building_token"] or self.last_location_building_token
        previous_room_token = previous["room_token"] or self.last_location_room_token
        current_building_token = current["building_token"]
        current_room_token = current["room_token"]

        if current_building_token and current_building_token != previous_building_token:
            text = _building_entry_description(
                self.sim,
                prop=current["prop"],
                structure=current["structure"],
            )
            if text:
                _log_player_feedback(
                    self.sim,
                    text,
                    kind="location",
                    dedupe_key=f"location:building:{current_building_token}",
                )

        if current_room_token and current_room_token != previous_room_token:
            text = _room_entry_description(
                self.sim,
                current["structure"],
                prop=current["prop"],
            )
            if text:
                _log_player_feedback(
                    self.sim,
                    text,
                    kind="location",
                    dedupe_key=f"location:room:{current_room_token}",
                )

        self.last_location_building_token = current_building_token
        self.last_location_room_token = current_room_token

    def _player_is_near_event_position(self, event, radius=8):
        x = event.data.get("x")
        y = event.data.get("y")
        z = event.data.get("z")
        if x is None or y is None or z is None:
            return False
        player_pos = self._player_position()
        if not player_pos:
            return False
        if int(player_pos.z) != int(z):
            return False
        return _manhattan(int(player_pos.x), int(player_pos.y), int(x), int(y)) <= int(max(1, radius))

    def _player_is_near_property(self, prop, radius=10):
        if not isinstance(prop, dict):
            return False
        player_pos = self._player_position()
        if not player_pos:
            return False
        try:
            px = int(prop.get("x", 0))
            py = int(prop.get("y", 0))
            pz = int(prop.get("z", 0))
        except (TypeError, ValueError):
            return False
        if int(player_pos.z) != pz:
            return False
        return _manhattan(int(player_pos.x), int(player_pos.y), px, py) <= int(max(1, radius))

    def _weapon_log_profile(self, weapon_id, projectile_count=1):
        weapon = weapon_by_id(weapon_id)
        tags = {str(tag).strip().lower() for tag in weapon.get("tags", ()) if str(tag).strip()}
        trajectory = str(weapon.get("trajectory", "ballistic")).strip().lower()
        explosive = int(weapon.get("explosion_radius", 0)) > 0 or trajectory == "lobbed" or "explosive" in tags
        shotgun = "shotgun" in tags
        smg_like = "smg" in tags or "burst" in tags or int(projectile_count) > 1 or int(weapon.get("pellets", 1)) > 1
        rifle = "rifle" in tags or "precision" in tags or "carbine" in tags

        if explosive:
            return {
                "player_verb": "launch",
                "npc_verb": "launches",
                "noun": "rocket",
                "miss": "The rocket bursts wide.",
                "blocked": "The rocket detonates against cover.",
            }
        if shotgun:
            return {
                "player_verb": "blast",
                "npc_verb": "blasts",
                "noun": "scattershot",
                "miss": "The blast scatters wide.",
                "blocked": "The blast slams into terrain.",
            }
        if smg_like:
            return {
                "player_verb": "rip",
                "npc_verb": "rips",
                "noun": "burst",
                "miss": "The burst goes wide.",
                "blocked": "The burst chews into cover.",
            }
        if rifle:
            return {
                "player_verb": "crack",
                "npc_verb": "cracks",
                "noun": "round",
                "miss": "The shot misses.",
                "blocked": "The round punches into terrain.",
            }
        return {
            "player_verb": "fire",
            "npc_verb": "fires",
            "noun": "shot",
            "miss": "Shot misses.",
            "blocked": "Shot blocked by terrain.",
        }

    def _combat_target_text(self, target_eid, target_name, target_x, target_y):
        if target_eid is not None:
            return f" at {self._npc_label(target_eid)}"
        raw = str(target_name or "").strip()
        if raw:
            return f" at {raw}"
        if target_x is not None and target_y is not None:
            return f" toward ({int(target_x)},{int(target_y)})"
        return ""

    def _npc_role(self, eid):
        ai = self.sim.ecs.get(AI).get(eid)
        return str(getattr(ai, "role", "") or "").strip().lower()

    def _investigation_combat_noise(self, npc_eid, event):
        cause = str(event.data.get("cause", "") or "").strip().lower()
        if cause not in COMBAT_NOISE_CAUSES:
            return False
        if event.data.get("source_eid") != self.player_eid:
            return False
        return True

    def _investigation_bark_is_direct_target(self, npc_eid, event):
        target_eid = event.data.get("target_eid")
        if target_eid is not None and npc_eid is not None:
            try:
                if int(target_eid) == int(npc_eid):
                    return True
            except (TypeError, ValueError):
                if target_eid == npc_eid:
                    return True
        ai = self.sim.ecs.get(AI).get(npc_eid)
        if ai is None:
            return False
        try:
            return int(getattr(ai, "target_eid", None)) == int(self.player_eid)
        except (TypeError, ValueError):
            return getattr(ai, "target_eid", None) == self.player_eid

    def _npc_notice_mode(self, npc_eid):
        positions = self.sim.ecs.get(Position)
        player_pos = positions.get(self.player_eid)
        npc_pos = positions.get(npc_eid)
        if npc_pos and self._player_has_los_to_position(npc_pos.x, npc_pos.y, npc_pos.z):
            return "visible"
        if player_pos and npc_pos and int(player_pos.z) != int(npc_pos.z):
            return "other_floor"
        return "nearby"

    def _log_npc_bark(self, npc_eid, quote, nearby_audio, other_floor_audio=None, *, channel="alerts", priority="high", dedupe_key=None):
        mode = self._npc_notice_mode(npc_eid)
        if mode == "visible":
            npc_name = self._npc_label(npc_eid)
            self._log_npc_message(
                npc_eid,
                f'{npc_name}: "{quote}"',
                channel=channel,
                priority=priority,
                dedupe_window=4,
                dedupe_key=dedupe_key or quote,
            )
            return
        if mode == "other_floor":
            self._log(
                other_floor_audio or nearby_audio,
                channel=channel,
                priority=priority,
                dedupe_window=4,
                dedupe_key=dedupe_key or quote,
            )
            return
        self._log(
            nearby_audio,
            channel=channel,
            priority=priority,
            dedupe_window=4,
            dedupe_key=dedupe_key or quote,
        )

    def _bark_location_label(self, prop):
        if not prop:
            return "this area"
        label = str(prop.get("name", "") or "").strip()
        return label or "this area"

    def _investigation_bark(self, npc_eid, event):
        role = self._npc_role(npc_eid)
        if self._investigation_combat_noise(npc_eid, event):
            direct_target = self._investigation_bark_is_direct_target(npc_eid, event)
            if direct_target:
                quote = "Back off!"
            elif role == "guard":
                quote = "Drop it."
            elif role in {"worker", "manager"}:
                quote = "Stop that!"
            else:
                quote = "Cut it out!"
            return (
                quote,
                "You hear someone shouting nearby.",
                "You hear shouting on another floor.",
            )
        positions = self.sim.ecs.get(Position)
        source_pos = positions.get(event.data.get("source_eid"))
        prop = _property_covering(self.sim, source_pos.x, source_pos.y, source_pos.z) if source_pos else None
        access = (
            _evaluate_property_access(
                self.sim,
                self.player_eid,
                prop,
                x=source_pos.x,
                y=source_pos.y,
                z=source_pos.z,
            )
            if (prop and source_pos)
            else None
        )
        suspicious = bool(access and access.inside_bounds and access.severity_score > 0)
        restricted = bool(access and access.access_level == "restricted")

        if suspicious:
            if restricted:
                return (
                    "This area is restricted.",
                    "You hear someone challenge you nearby.",
                    "You hear someone calling out on another floor.",
                )
            if role == "guard":
                return (
                    "What are you doing here?",
                    "You hear someone challenge you nearby.",
                    "You hear someone calling out on another floor.",
                )
            if role in {"worker", "manager"}:
                return (
                    "You should not be back here.",
                    "You hear someone challenge you nearby.",
                    "You hear someone calling out on another floor.",
                )
            return (
                "What are you doing here?",
                "You hear someone challenge you nearby.",
                "You hear someone calling out on another floor.",
            )

        if role == "guard":
            return (
                "I heard that.",
                "You hear someone searching nearby.",
                "You hear someone searching on another floor.",
            )
        if role in {"worker", "manager"}:
            return (
                "Can I help you?",
                "You hear someone searching nearby.",
                "You hear someone searching on another floor.",
            )
        return (
            "What was that?",
            "You hear someone searching nearby.",
            "You hear someone searching on another floor.",
        )

    def _warning_bark(self, npc_eid, event, prop):
        role = self._npc_role(npc_eid)
        location = self._bark_location_label(prop)
        reason = str(event.data.get("defender_reason", "") or "").strip().lower()
        access_level = _property_access_level(prop) if prop else ""

        if reason == "owner":
            quote = "What are you doing on my property?"
        elif reason == "watcher":
            quote = f"People on this block are watching {location}." if location != "this area" else "People on this block are watching this place."
        elif access_level == "restricted":
            quote = "This area is off-limits."
        elif role == "guard":
            quote = "Move along. This area is off-limits."
        elif role in {"worker", "manager"}:
            quote = "You should not be back here."
        elif location != "this area":
            quote = f"Step away from {location}."
        else:
            quote = "What are you doing here?"

        return (
            quote,
            "You hear someone challenge you nearby.",
            "You hear someone calling out on another floor.",
        )

    def _defense_bark(self, npc_eid, event, prop):
        role = self._npc_role(npc_eid)
        location = self._bark_location_label(prop)
        reason = str(event.data.get("defender_reason", "") or "").strip().lower()
        access_level = _property_access_level(prop) if prop else ""

        if reason == "owner":
            quote = "Get off my property!"
        elif reason == "watcher":
            quote = f"Back off. This block watches {location}." if location != "this area" else "Back off. This block watches its own."
        elif access_level == "restricted":
            quote = "Back away, now."
        elif location != "this area":
            quote = f"Back away from {location}, now."
        elif role == "guard":
            quote = "Back away, now."
        else:
            quote = "Get out of here!"

        return (
            quote,
            "You hear someone shouting nearby.",
            "You hear shouting on another floor.",
        )

    def _protect_ally_bark(self, npc_eid, relation):
        relation = str(relation or "ally").strip().lower()
        if relation in {"family", "partner", "friend", "coworker", "neighbor"}:
            quote = f"Back off from my {relation}."
        else:
            quote = "Leave them alone."
        return (
            quote,
            "You hear someone rush to help nearby.",
            "You hear someone shouting on another floor.",
        )

    def _closing_time_bark(self, npc_eid, prop):
        role = self._npc_role(npc_eid)
        prop_name = str((prop or {}).get("name", "") or "").strip()
        if role == "guard":
            quote = "Closing time. Move along."
        elif role in {"worker", "manager"}:
            quote = "We're closing. Don't linger."
        elif prop_name:
            quote = f"Closing time at {prop_name}. Out you go."
        else:
            quote = "Closing time. Out you go."

        return (
            quote,
            "You hear someone ushering people out nearby.",
            "You hear someone calling closing time on another floor.",
        )

    def _offended_bark(self, event):
        action = str(event.data.get("action", "") or "").strip().lower()
        context = str(event.data.get("context", "") or "").strip().lower()

        if context == "dialogue_insult":
            quote = "Watch your mouth."
        elif context == "dialogue_pry":
            quote = "That is none of your business."
        elif context == "dialogue_weird":
            quote = "What kind of question is that?"
        elif context == "dialogue_repeat":
            quote = "I already answered you."
        elif context == "item_theft" or action == "pickup_item":
            quote = "Put that back."
        elif context == "trespass" or action == "move":
            quote = "You should not be here."
        elif action in {"interact", "use_item"}:
            quote = "Leave that alone."
        elif context in VIOLENT_OFFENSE_CONTEXTS or action in {"fire_weapon", "melee_attack"}:
            quote = "Get down!"
        else:
            quote = "What do you think you are doing?"

        return (
            quote,
            "You hear an angry voice nearby.",
            "You hear shouting on another floor.",
        )

    def _player_chunk_coord(self):
        pos = self.sim.ecs.get(Position).get(self.player_eid)
        if pos:
            return self.sim.chunk_coords(pos.x, pos.y)
        return getattr(self.sim, "active_chunk_coord", None)

    def _chunk_preview_service_names(self, service, chunk_coord, limit=3):
        if not chunk_coord:
            return ()
        cx, cy = chunk_coord
        chunk = self.sim.world.get_chunk(int(cx), int(cy))
        service_key = str(service or "").strip().lower()
        names = []

        for block in chunk.get("blocks", ()):
            for building_index, building in enumerate(block.get("buildings", ())):
                archetype = str(building.get("archetype", "")).strip().lower()
                service_seed_token = _building_site_service_seed_token(cx, cy, building, building_index=building_index)
                services = list(_default_site_services_for_archetype(archetype, seed_token=service_seed_token)) + list(vehicle_services_for_archetype(archetype))
                if service_key not in {str(item).strip().lower() for item in services if str(item).strip()}:
                    continue
                label = str(building.get("business_name") or archetype.replace("_", " ").title()).strip()
                if label:
                    names.append(label)

        for site_index, site in enumerate(chunk.get("sites", ())):
            kind = str(site.get("kind", "")).strip().lower()
            service_seed_token = _site_service_seed_token(cx, cy, site, site_index=site_index)
            gameplay = site_gameplay_profile(site)
            services = list(gameplay.get("site_services", ()))
            if not services:
                services = list(_default_site_services_for_archetype(kind, seed_token=service_seed_token))
            services += list(vehicle_services_for_archetype(kind))
            if service_key not in {str(item).strip().lower() for item in services if str(item).strip()}:
                continue
            label = str(site.get("name") or kind.replace("_", " ").title()).strip()
            if label:
                names.append(label)

        deduped = []
        seen = set()
        for name in names:
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            deduped.append(name)
        return tuple(deduped[: max(1, int(limit))])

    def _current_chunk_service_props(self, service, limit=3):
        chunk_coord = self._player_chunk_coord()
        if not chunk_coord:
            return ()
        pos = self.sim.ecs.get(Position).get(self.player_eid)
        service_key = str(service or "").strip().lower()
        candidates = []
        for prop in self.sim.properties.values():
            if self.sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0))) != tuple(chunk_coord):
                continue
            services = set(_property_services(prop))
            if service_key not in services:
                continue
            distance = 999
            if pos:
                distance = _manhattan(pos.x, pos.y, int(prop.get("x", 0)), int(prop.get("y", 0)))
            access = _evaluate_property_access(
                self.sim,
                self.player_eid,
                prop,
                x=getattr(pos, "x", None),
                y=getattr(pos, "y", None),
                z=getattr(pos, "z", None),
            )
            role_priority = 0 if _property_infrastructure_role(prop) == "service_terminal" else 1
            candidates.append((
                0 if access.can_use_services else 1,
                int(distance),
                role_priority,
                str(prop.get("name", prop.get("id", "site"))).strip().lower(),
                str(prop.get("name", prop.get("id", "site"))).strip() or "site",
            ))
        candidates.sort()
        return tuple(row[4] for row in candidates[: max(1, int(limit))])

    def _nearest_chunk_service_preview(self, service, radius=6, limit=3):
        origin = self._player_chunk_coord()
        if not origin:
            return None, ()
        ox, oy = origin
        for dist in range(0, max(1, int(radius)) + 1):
            matches = []
            for cx in range(int(ox) - dist, int(ox) + dist + 1):
                for cy in range(int(oy) - dist, int(oy) + dist + 1):
                    if abs(cx - int(ox)) + abs(cy - int(oy)) != dist:
                        continue
                    names = self._chunk_preview_service_names(service, (cx, cy), limit=limit)
                    if names:
                        matches.append((dist, int(cy), int(cx), (int(cx), int(cy)), names))
            if matches:
                matches.sort()
                best = matches[0]
                return best[3], best[4]
        return None, ()

    def _current_chunk_owned_vehicle_recovery_options(self, *, exclude_vehicle_id=None, require_fuel=False, limit=2):
        chunk_coord = self._player_chunk_coord()
        if not chunk_coord:
            return ()
        pos = self.sim.ecs.get(Position).get(self.player_eid)
        assets = self.sim.ecs.get(PlayerAssets).get(self.player_eid)
        inventory = self.sim.ecs.get(Inventory).get(self.player_eid)
        excluded_id = str(exclude_vehicle_id or "").strip()
        candidates = []
        for prop in self.sim.properties.values():
            if not _property_is_vehicle(prop):
                continue
            vehicle_id = str(prop.get("id", "")).strip()
            if excluded_id and vehicle_id == excluded_id:
                continue
            if self.sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0))) != tuple(chunk_coord):
                continue
            owned = bool(
                prop.get("owner_eid") == self.player_eid
                or str(prop.get("owner_tag", "") or "").strip().lower() == "player"
                or (assets and vehicle_id in getattr(assets, "owned_property_ids", set()))
            )
            if not owned:
                continue
            fuel, fuel_capacity = _vehicle_fuel_values(prop)
            if require_fuel and fuel <= 0:
                continue
            lock_state = property_lock_state(prop)
            has_key = bool(
                lock_state["key_id"]
                and inventory_matching_property_key(
                    inventory,
                    property_id=prop.get("id"),
                    key_id=lock_state["key_id"],
                ) is not None
            )
            hotwired = bool(_property_metadata(prop).get("vehicle_hotwired"))
            if lock_state["locked"] and not has_key and not hotwired:
                continue
            distance = 999
            if pos:
                distance = _manhattan(pos.x, pos.y, int(prop.get("x", 0)), int(prop.get("y", 0)))
            if hotwired:
                readiness = "hotwired"
            elif has_key:
                readiness = "key on hand"
            elif lock_state["locked"]:
                readiness = "locked"
            else:
                readiness = "unlocked"
            candidates.append((
                int(distance),
                -int(fuel),
                str(prop.get("name", prop.get("id", "vehicle"))).strip().lower(),
                {
                    "name": _vehicle_label(prop),
                    "fuel": int(fuel),
                    "fuel_capacity": int(fuel_capacity),
                    "readiness": readiness,
                },
            ))
        candidates.sort()
        return tuple(row[3] for row in candidates[: max(1, int(limit))])

    def _owned_vehicle_recovery_sentence(self, *, exclude_vehicle_id=None):
        options = self._current_chunk_owned_vehicle_recovery_options(
            exclude_vehicle_id=exclude_vehicle_id,
            require_fuel=True,
            limit=2,
        )
        if not options:
            return ""
        first = options[0]
        subject = "Another owned vehicle is in this chunk" if str(exclude_vehicle_id or "").strip() else "Owned vehicle in this chunk"
        detail = (
            f"{first['name']} {first['fuel']}/{first['fuel_capacity']} "
            f"({first['readiness']})"
        )
        if len(options) > 1:
            detail += f" (+{len(options) - 1} more)"
        return f"{subject}: {detail}."

    def _service_recovery_hint(self, service, *, on_foot=False):
        service_label = _site_service_label(service).strip() or str(service or "service")
        service_key = str(service or "").strip().lower()
        sentences = []
        has_owned_recovery = False
        if not on_foot:
            sentences.append("Press Z to go on foot.")
        if service_key == "fuel":
            active_vehicle = self._player_active_vehicle_property()
            recovery_sentence = self._owned_vehicle_recovery_sentence(
                exclude_vehicle_id=(active_vehicle or {}).get("id"),
            )
            if recovery_sentence:
                sentences.append(recovery_sentence)
                has_owned_recovery = True
        local_names = self._current_chunk_service_props(service)
        if not local_names:
            local_names = self._chunk_preview_service_names(service, self._player_chunk_coord())
        if local_names:
            target_text = ", ".join(local_names[:2])
            if len(local_names) > 2:
                target_text += f" (+{len(local_names) - 2} more)"
            sentences.append(
                f"{service_label.title()} is available in this chunk at {target_text}."
                + (" Walk over and press E." if on_foot else "")
            )
            return "Recovery: " + " ".join(sentences)

        chunk_coord, names = self._nearest_chunk_service_preview(service)
        if chunk_coord:
            preview = f" ({', '.join(names[:2])})" if names else ""
            sentences.append(f"No {service_label} in this chunk. Nearest known {service_label} is around chunk {chunk_coord}{preview}.")
            return "Recovery: " + " ".join(sentences)

        if has_owned_recovery:
            return "Recovery: " + " ".join(sentences)
        sentences.append(
            f"No clear {service_label} lead here. Search for another vehicle, service site, or settlement."
        )
        return "Recovery: " + " ".join(sentences)

    def _player_active_vehicle_property(self):
        state = self.sim.ecs.get(VehicleState).get(self.player_eid)
        if not state or not state.active_vehicle_id:
            return None
        prop = self.sim.properties.get(state.active_vehicle_id)
        if _property_is_vehicle(prop):
            return prop
        return None

    def _site_service_interaction_label(self, service):
        service_key = str(service or "").strip().lower()
        if service_key not in {"fuel", "repair"}:
            return _site_service_label(service)

        vehicle_prop = self._player_active_vehicle_property()
        if not vehicle_prop:
            if service_key == "fuel":
                return "fuel (needs active vehicle)"
            return "repair (needs owned vehicle)"

        vehicle_name = _vehicle_label(vehicle_prop)
        if service_key == "fuel":
            fuel, fuel_capacity = _vehicle_fuel_values(vehicle_prop)
            if fuel_capacity > 0 and fuel >= fuel_capacity:
                return f"fuel for {vehicle_name} {fuel}/{fuel_capacity} (full)"
            if fuel <= 0:
                return f"fuel for {vehicle_name} {fuel}/{fuel_capacity} (empty)"
            return f"fuel for {vehicle_name} {fuel}/{fuel_capacity}"

        durability = max(0, min(10, _int_or_default(_vehicle_profile_from_property(vehicle_prop).get("durability"), 5)))
        if durability >= 10:
            return f"repair for {vehicle_name} D{durability}/10 (solid)"
        if durability <= 3:
            return f"repair for {vehicle_name} D{durability}/10 (rough)"
        if durability <= 6:
            return f"repair for {vehicle_name} D{durability}/10 (worn)"
        return f"repair for {vehicle_name} D{durability}/10"

    def _security_post_target(self, prop):
        linked = _infrastructure_target_property(self.sim, prop)
        if linked is not None:
            return linked
        if not isinstance(prop, dict):
            return None

        try:
            x = int(prop.get("x", 0))
            y = int(prop.get("y", 0))
            z = int(prop.get("z", 0))
        except (TypeError, ValueError):
            return None

        candidates = []
        for candidate in self.sim.properties_in_radius(x, y, z, r=3):
            if candidate.get("id") == prop.get("id"):
                continue
            if str(candidate.get("kind", "")).strip().lower() != "building":
                continue
            controller = _property_access_controller(self.sim, candidate)
            access_level = _property_access_level(candidate)
            security_tier = max(1, _int_or_default(controller.get("security_tier"), 1))
            if access_level != "restricted" and security_tier < 3:
                continue
            candidates.append((
                0 if access_level == "restricted" else 1,
                -security_tier,
                _property_distance(x, y, candidate),
                candidate,
            ))
        if not candidates:
            return None
        candidates.sort(key=lambda row: (row[0], row[1], row[2]))
        return candidates[0][3]

    def on_move_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        reason = str(event.data.get("reason", "")).strip().lower()
        _log_player_feedback(
            self.sim,
            self._movement_blocked_message(
                reason=reason,
                x=event.data.get("x"),
                y=event.data.get("y"),
                z=event.data.get("z"),
                property_id=event.data.get("property_id"),
            ),
            kind="movement",
        )

    def on_entity_moved(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        reason = str(event.data.get("reason", "")).strip().lower()
        if reason == "cover_hop":
            return

        x = event.data.get("x")
        y = event.data.get("y")
        z = event.data.get("z")
        if x is None or y is None or z is None:
            return

        self._emit_location_entry_descriptions(event)

        text, signature = self._ground_item_notice_text(x, y, z)
        if not text:
            return

        _log_player_feedback(
            self.sim,
            text,
            kind="movement",
            dedupe_key=f"ground-item-notice:{int(x)}:{int(y)}:{int(z)}:{signature}",
        )

    def on_floor_change_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        reason = str(event.data.get("reason", "") or "").strip().lower()
        if reason == "overworld_mode":
            _log_player_feedback(self.sim, "Floor changes are unavailable in the overworld map.", kind="movement")
            return
        if reason == "no_transition":
            _log_player_feedback(self.sim, "No stairs/elevator connection here.", kind="movement")
            return

        try:
            x = int(event.data.get("x"))
            y = int(event.data.get("y"))
            z = int(event.data.get("z"))
            dz = int(event.data.get("dz", 0))
        except (TypeError, ValueError):
            x = y = z = dz = None

        floor_link = self.sim.tilemap.floor_transition(x, y, z, dz) if None not in {x, y, z, dz} else None
        target_x = int(floor_link.get("x", x or 0)) if isinstance(floor_link, dict) else x
        target_y = int(floor_link.get("y", y or 0)) if isinstance(floor_link, dict) else y
        target_z = int(floor_link.get("z", z or 0)) if isinstance(floor_link, dict) else z
        target_prop = None
        if target_x is not None and target_y is not None and target_z is not None:
            target_prop = (
                self.sim.property_at(target_x, target_y, target_z)
                or _property_covering(self.sim, target_x, target_y, target_z)
            )

        _log_player_feedback(
            self.sim,
            self._movement_blocked_message(
                reason=reason,
                x=target_x,
                y=target_y,
                z=target_z,
                property_id=(target_prop or {}).get("id") if isinstance(target_prop, dict) else None,
                floor_context=True,
            ),
            kind="movement",
        )

    def on_entity_changed_floor(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        to_z = event.data.get("to_z")
        kind = event.data.get("kind")
        _log_player_feedback(self.sim, f"You take the {kind} to {_floor_label(to_z, long=True)}.", kind="movement")

    def on_noise(self, event):
        if event.data.get("source_eid") != self.player_eid:
            return
        radius = event.data.get("radius", 0)
        cause = event.data.get("cause")
        mode_state = self.sim.ecs.get(PlayerModeState).get(self.player_eid)
        sneak_active = bool(mode_state and mode_state.sneak)

        if cause in QUIET_NOISE_CAUSES:
            if not sneak_active:
                return
            cause_text = str(cause).replace("_", " ")
            if cause == "move":
                self.sim.log.add(f"You move quietly (r={radius}).")
            else:
                self.sim.log.add(f"You keep quiet ({cause_text}, r={radius}).")
            return

        self.sim.log.add(f"You make noise ({cause}, r={radius}).")

    def on_player_mode_toggled(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        mode = str(event.data.get("mode", "")).strip().lower()
        active = bool(event.data.get("active"))
        if mode == "sneak":
            if active:
                self.sim.log.add("Sneak mode enabled. Footstep noise reduced.")
            else:
                self.sim.log.add("Sneak mode disabled.")
            return

        label = mode.replace("_", " ").strip() or "mode"
        state = "enabled" if active else "disabled"
        self.sim.log.add(f"{label.title()} {state}.")

    def on_player_hidden_changed(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        if bool(event.data.get("active")):
            self.sim.log.add("You slip out of sight.")
            return

        reason = str(event.data.get("reason", "")).strip().lower()
        if reason == "observed":
            labels = [str(label).strip() for label in event.data.get("witness_labels", ()) if str(label).strip()]
            if labels:
                self.sim.log.add(f"You are no longer hidden ({', '.join(labels[:2])}).")
            else:
                self.sim.log.add("You are no longer hidden.")

    def on_creature_hazard_triggered(self, event):
        if event.data.get("target_eid") != self.player_eid:
            return
        hazard_kind = str(event.data.get("hazard_kind", "toxic_cat") or "toxic_cat").strip().lower()
        if hazard_kind == "venom":
            species = str(event.data.get("species", "snake") or "snake").replace("_", " ")
            self._log(f"Venom contact: {species} bite burns.", channel="status", priority="high")
            return
        coat = str(event.data.get("coat_variant", "unknown")).replace("_", " ")
        self._log(f"Toxic contact: {coat} cat venom burns.", channel="status", priority="high")

    def on_environmental_hazard_triggered(self, event):
        if event.data.get("target_eid") != self.player_eid:
            return
        profile_id = str(event.data.get("hazard_profile", "") or "").strip().lower()
        hazard_name = str(event.data.get("hazard_name", event.data.get("property_name", "hazard")) or "").strip()
        note = str(event.data.get("hazard_note", "")).strip() or environment_hazard_player_note(profile_id, name=hazard_name)
        self._log(f"Hazard: {note}", channel="status", priority="high")

    def on_fire_started(self, event):
        place = self._event_place_name(event) or self._event_property_name(event, fallback="the frontage")
        if event.data.get("source_eid") == self.player_eid:
            self._log(f"Fire catches at {place}.", channel="combat", priority="critical")
            return
        if not self._player_can_perceive_event_position(event):
            return
        self._log(f"Fire breaks out at {place}.", channel="world", priority="critical")

    def on_fire_contained(self, event):
        if not self._player_can_perceive_event_position(event):
            return
        place = self._event_place_name(event) or self._event_property_name(event, fallback="the frontage")
        self._log(f"Fire response holds at {place}.", channel="world", priority="high")

    def on_fire_burned_out(self, event):
        if not self._player_can_perceive_event_position(event):
            return
        place = self._event_place_name(event) or self._event_property_name(event, fallback="the frontage")
        self._log(f"The fire at {place} burns down to smoke and cleanup.", channel="world", priority="normal")

    def on_world_condition_triggered(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        topic = str(event.data.get("topic", "world_condition")).strip().lower()
        target = str(event.data.get("target_value", "unknown")).replace("_", " ").strip()
        is_positive = bool(event.data.get("is_positive", False))

        if topic == "contamination_taxonomy":
            text = f"Exposure event: {target} contamination."
        elif topic == "illness_human_role":
            text = f"Illness wave brushes against {target} groups."
        elif topic == "war_human_role":
            text = f"War tension spikes around {target} groups."
        elif topic == "blessing_taxonomy":
            text = f"Lucky streak from {target} wildlife currents."
        else:
            text = f"World condition triggered: {topic.replace('_', ' ')} ({target})."

        if is_positive:
            self.sim.log.add(f"Boons: {text}")
        else:
            self.sim.log.add(f"Hazards: {text}")

    def on_scan_report(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        lines = event.data.get("lines") or []
        note = _sentence_from_note(event.data.get("note", ""))
        radius_used = _int_or_default(event.data.get("radius"), 0)
        display_limit = max(1, min(8, _int_or_default(event.data.get("display_limit"), 5)))
        if note:
            if radius_used > 0:
                self.sim.log.add(f"Scan sweep {radius_used}t: {note}")
            else:
                self.sim.log.add(f"Scan: {note}")
        if not lines:
            self.sim.log.add("Scan finds nothing useful.")
            return

        first = True
        for raw in lines[:display_limit]:
            text = _line_text(raw).strip()
            if not text:
                continue
            entry = _line_with_prefix(raw, "Scan: " if first else "  ")
            segments = _line_segments(entry)
            if first:
                if segments:
                    self.sim.log.add_rich(segments, text=_line_text(entry))
                else:
                    self.sim.log.add(_line_text(entry))
                first = False
            else:
                if segments:
                    self.sim.log.add_rich(segments, text=_line_text(entry))
                else:
                    self.sim.log.add(_line_text(entry))

    def on_look_mode_toggled(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        active = bool(event.data.get("active"))
        purpose = str(event.data.get("purpose", "inspect")).lower()
        if active:
            mode = str(event.data.get("mode", "city")).lower()
            if purpose == "aim":
                self.sim.log.add(f"Aim mode enabled ({mode}).")
            elif purpose == "interact":
                self.sim.log.add(f"Interact target mode enabled ({mode}).")
            else:
                self.sim.log.add(f"Look mode enabled ({mode}).")
        else:
            if purpose == "aim":
                self.sim.log.add("Aim mode disabled.")
            elif purpose == "interact":
                self.sim.log.add("Interact target mode disabled.")
            else:
                self.sim.log.add("Look mode disabled.")

    def on_cursor_examined(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        if not bool(event.data.get("announce")):
            return
        purpose = str(event.data.get("purpose", "inspect")).lower()
        raw = event.data.get("text", "")
        text = _line_text(raw).strip()
        if text:
            if purpose == "aim":
                prefix = "Aim: "
            elif purpose == "interact":
                prefix = "Interact: "
            else:
                prefix = "Look: "
            entry = _line_with_prefix(raw, prefix)
            segments = _line_segments(entry)
            if segments:
                self.sim.log.add_rich(segments, text=_line_text(entry))
            else:
                self.sim.log.add(_line_text(entry))

    def on_property_self_discovered(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        property_name = str(event.data.get("property_name", "location")).strip() or "location"
        discovery_mode = str(event.data.get("discovery_mode", "sight")).strip().lower() or "sight"
        source_item_name = str(event.data.get("source_item_name", "") or "").strip()
        hidden = bool(event.data.get("hidden"))
        confidence = max(0, min(100, int(round(float(event.data.get("confidence", 0.0) or 0.0) * 100.0))))
        bucket = "hidden locations" if hidden else "known locations"
        if discovery_mode == "interact":
            self.sim.log.add(f"Location confirmed: {property_name} added to {bucket} ({confidence}% confidence).")
            return
        if discovery_mode == "scan":
            self.sim.log.add(f"Scan noted: {property_name} added to {bucket} ({confidence}% confidence).")
            return
        if discovery_mode == "advertisement":
            if source_item_name:
                self.sim.log.add(f"Lead noted from {source_item_name}: {property_name} added to {bucket} ({confidence}% confidence).")
                return
            self.sim.log.add(f"Lead noted: {property_name} added to {bucket} ({confidence}% confidence).")
            return
        if discovery_mode == "covert_note":
            if source_item_name:
                self.sim.log.add(f"Hidden lead filed from {source_item_name}: {property_name} added to {bucket} ({confidence}% confidence).")
                return
            self.sim.log.add(f"Hidden lead filed: {property_name} added to {bucket} ({confidence}% confidence).")
            return
        self.sim.log.add(f"Location noted: {property_name} added to {bucket} ({confidence}% confidence).")

    def on_interact_empty(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        interaction_mode = str(event.data.get("interaction_mode", "") or "").strip().lower()
        if interaction_mode == "talk":
            self.sim.log.add("No one close enough to talk to.")
            return
        if interaction_mode == "service":
            self.sim.log.add("No service terminal or same-tile counter is available here.")
            return
        self.sim.log.add("Nothing nearby responds to that interaction.")

    def on_access_panel_used(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        panel_name = str(event.data.get("property_name", "access panel")).strip() or "access panel"
        target_name = str(event.data.get("target_property_name", "property")).strip() or "property"
        outcome = str(event.data.get("outcome", "status")).strip().lower()
        method = str(event.data.get("method", "status_check")).strip().lower()
        requirement = str(event.data.get("requirement", "authorization")).strip() or "authorization"
        open_now = event.data.get("open_now")
        intrusion_label = str(event.data.get("intrusion_label", "")).strip()
        intrusion_ticks = max(0, _int_or_default(event.data.get("intrusion_remaining_ticks"), 0))

        if outcome == "authorized_open":
            self.sim.log.add(f"You use {panel_name}. {target_name} unlocks for authorized access.")
            return
        if outcome == "intrusion_open":
            self.sim.log.add(
                f"You work the {panel_name} ({_ingress_method_label(method)}). {target_name} opens under {intrusion_label or 'an intrusion window'} for {intrusion_ticks} ticks."
            )
            return
        if outcome == "override_open":
            self.sim.log.add(f"You work the {panel_name} ({_ingress_method_label(method)}). {target_name} unlocks.")
            return

        if open_now is True:
            status_text = "open"
        elif open_now is False:
            status_text = "closed"
        else:
            status_text = "secured"
        if intrusion_label and intrusion_ticks > 0:
            self.sim.log.add(
                f"{panel_name}: {target_name} shows {status_text}. {intrusion_label.title()} active for {intrusion_ticks} ticks."
            )
            return
        self.sim.log.add(f"{panel_name}: {target_name} reads {status_text}. Requirement: {requirement}.")

    def on_access_panel_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        panel_name = str(event.data.get("property_name", "access panel")).strip() or "access panel"
        target_name = str(event.data.get("target_property_name", "property")).strip() or "property"
        reason = str(event.data.get("reason", "")).strip().lower()
        requirement = str(event.data.get("requirement", "authorization")).strip() or "authorization"
        intrusion_label = str(event.data.get("intrusion_label", "")).strip() or "intrusion"

        if reason == "offline":
            if target_name and target_name != "property":
                self.sim.log.add(f"{panel_name} has no live link to {target_name}.")
            else:
                self.sim.log.add(f"{panel_name} has no live link.")
            return
        if reason == "panel_intrusion_failed":
            self.sim.log.add(f"You fail to land the {intrusion_label} on {panel_name}; {target_name} stays secured.")
            return
        if reason == "panel_intrusion_fumble":
            self.sim.log.add(f"You fumble the {intrusion_label} on {panel_name}; {target_name} stays secured.")
            return
        if reason == "lock_override_failed":
            self.sim.log.add(f"You fail to defeat the {panel_name} guarding {target_name}.")
            return
        if reason == "lock_override_fumble":
            self.sim.log.add(f"You fumble the {panel_name} override on {target_name}.")
            return
        if reason == "locked_property":
            self.sim.log.add(f"{panel_name} rejects you. You need {requirement}, a lockpick kit, or exceptional intrusion skill.")
            return
        self.sim.log.add(f"{panel_name} blocks access to {target_name} right now.")

    def on_property_interact(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        if bool(event.data.get("handled")):
            return
        prop = self.sim.properties.get(event.data.get("property_id"))
        if not prop:
            self.sim.log.add("You check a nearby access point.")
            return

        name = str(prop.get("name", prop.get("id", "property"))).strip() or "property"
        infrastructure_role = _property_infrastructure_role(prop)
        if infrastructure_role == "security_post":
            target = self._security_post_target(prop)
            if target:
                controller = _property_access_controller(self.sim, target)
                target_name = str(target.get("name", target.get("id", "property"))).strip() or "property"
                access_level = _property_access_level(target)
                open_now = controller.get("open_now")
                open_text = "open" if open_now is True else ("closed" if open_now is False else "secured")
                requirement = _controller_access_requirement_text(controller)
                security_tier = max(1, _int_or_default(controller.get("security_tier"), 1))
                self.sim.log.add(
                    f"{name}: watching {target_name} ({access_level}, {open_text}, {requirement}, sec {security_tier})."
                )
            else:
                district = self.sim.active_chunk.get("district", {}) if isinstance(getattr(self.sim, "active_chunk", {}), dict) else {}
                security = str(district.get("security_level", "?")).strip() or "?"
                self.sim.log.add(f"{name}: district security watch level {security}.")
            return

        owns_property = prop.get("owner_eid") == self.player_eid
        player_pos = self.sim.ecs.get(Position).get(self.player_eid)
        access = _evaluate_property_access(
            self.sim,
            self.player_eid,
            prop,
            x=getattr(player_pos, "x", None),
            y=getattr(player_pos, "y", None),
            z=getattr(player_pos, "z", None),
        )
        is_public = access.access_level == "public"
        interaction_modes = _property_interaction_modes(self.sim, prop, viewer_eid=self.player_eid)
        actionable = tuple(mode for mode in interaction_modes if mode != "inspect")

        if actionable:
            if _property_is_storefront(prop):
                return
            if "banking" in actionable or "insurance" in actionable:
                return
            if "intel" in actionable or "shelter" in actionable:
                return

        finance_services = list(_finance_services_for_property(prop))
        site_services = [self._site_service_interaction_label(service) for service in _site_services_for_property(prop)]
        services = finance_services + [label for label in site_services if label not in finance_services]
        contact_hint = _property_contact_hint(self.sim, self.player_eid, prop)
        if services:
            service_text = ", ".join(services)
            if access.can_use_services:
                if not owns_property and not is_public:
                    if contact_hint:
                        self.sim.log.add(f"{name} is protected. Public services here: {service_text}. {contact_hint}.")
                    else:
                        self.sim.log.add(f"{name} is protected. Public services here: {service_text}.")
                else:
                    if contact_hint:
                        self.sim.log.add(f"Interact: {name}. Services: {service_text}. {contact_hint}.")
                    else:
                        self.sim.log.add(f"Interact: {name}. Services: {service_text}.")
                return

            if access.access_level == "public" and access.currently_open is False:
                if contact_hint:
                    self.sim.log.add(f"{name} is closed right now. Services here: {service_text}. {contact_hint}.")
                else:
                    self.sim.log.add(f"{name} is closed right now. Services here: {service_text}.")
                return

            if not owns_property and not is_public:
                if contact_hint:
                    self.sim.log.add(f"{name} is protected. Services here: {service_text}, but no public access is exposed. {contact_hint}.")
                else:
                    self.sim.log.add(f"{name} is protected. Services here: {service_text}, but no public access is exposed.")
            else:
                if contact_hint:
                    self.sim.log.add(f"Interact: {name}. Services: {service_text}. {contact_hint}.")
                else:
                    self.sim.log.add(f"Interact: {name}. Services: {service_text}.")
            return

        if not owns_property and not is_public:
            if access.access_level == "public" and access.currently_open is False:
                if contact_hint:
                    self.sim.log.add(f"{name} is closed right now. {contact_hint}.")
                else:
                    self.sim.log.add(f"{name} is closed right now.")
                return
            if contact_hint:
                self.sim.log.add(f"{name} is protected. No public interaction is exposed. {contact_hint}.")
            else:
                self.sim.log.add(f"{name} is protected. No public interaction is exposed.")
            return

        if contact_hint:
            self.sim.log.add(f"Interact: {_property_summary(self.sim, prop, viewer_eid=self.player_eid)}. {contact_hint}.")
            return
        self.sim.log.add(f"Interact: {_property_summary(self.sim, prop, viewer_eid=self.player_eid)}.")

    def on_npc_interacted(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        if bool(event.data.get("dialog_modal")):
            return

        lines = event.data.get("lines") or []
        if not lines:
            self.sim.log.add("You talk for a moment.")
            return

        first = True
        for raw in lines[:4]:
            text = str(raw).strip()
            if not text:
                continue
            if first:
                self.sim.log.add(f"Talk: {text}")
                first = False
            else:
                self.sim.log.add(f"  {text}")

    def on_dialogue_opportunity_hint(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        summary = str(event.data.get("summary", "")).strip()
        detail = str(event.data.get("detail", "")).strip()
        npc_eid = event.data.get("npc_eid")
        speaker = _entity_display_name(self.sim, npc_eid, title_case=True) if npc_eid is not None else "Someone"
        if summary:
            self._log(
                f"Opportunity: {speaker} mentions {summary}.",
                channel="opportunity",
                priority="high",
                dedupe_window=12,
                dedupe_key=f"dialogue-opportunity:{summary.lower()}",
            )
        if detail:
            self.sim.log.add(f"  {detail}", channel="opportunity", priority="normal", dedupe_window=12)

    def on_eavesdrop_opportunity_hint(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        summary = str(event.data.get("summary", "")).strip()
        if not summary:
            return
        confidence = max(0, min(100, int(round(float(event.data.get("confidence", 0.0) or 0.0) * 100.0))))
        self._log(
            f"Street intel: {summary} ({confidence}% confidence).",
            channel="opportunity",
            priority="normal",
            dedupe_window=14,
            dedupe_key=f"eavesdrop-opportunity:{str(event.data.get('opportunity_id', 0))}:{summary.lower()}",
        )

    def on_eavesdrop_property_hint(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        property_name = str(event.data.get("property_name", "property")).strip() or "property"
        lead_kind = str(event.data.get("lead_kind", "")).strip().lower()
        lead_label = str(event.data.get("lead_label", "")).strip() or "covert contact"
        hidden = bool(event.data.get("hidden"))
        newly_known = bool(event.data.get("newly_known"))
        confidence = max(0, min(100, int(round(float(event.data.get("confidence", 0.0) or 0.0) * 100.0))))
        if hidden:
            if newly_known:
                text = f"Overheard covert lead: {property_name} sounds like a {lead_label} ({confidence}% confidence). Added to hidden locations."
            else:
                text = f"Overheard covert lead: {property_name} sounds more likely to be a {lead_label} ({confidence}% confidence)."
            channel = "social"
        elif lead_kind == "contraband":
            text = f"Street rumor: {property_name} may move illegal goods ({confidence}% confidence)."
            channel = "opportunity"
        elif lead_kind == "hours":
            text = f"Overheard hours: {property_name} sounds more reliable now ({confidence}% confidence)."
            channel = "social"
        else:
            text = f"Overheard access lead: {property_name} sounds more reliable now ({confidence}% confidence)."
            channel = "social"
        self._log(
            text,
            channel=channel,
            priority="normal",
            dedupe_window=14,
            dedupe_key=f"eavesdrop-property:{event.data.get('property_id')}:{lead_kind}:{int(hidden)}",
        )

    def on_dialogue_guard_resolution(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        npc_eid = event.data.get("npc_eid")
        npc_name = _entity_display_name(self.sim, npc_eid, title_case=True) if npc_eid is not None else "Someone"
        tactic = str(event.data.get("tactic", "dialogue")).strip().lower() or "dialogue"
        outcome = str(event.data.get("outcome", "wary")).strip().lower() or "wary"
        if outcome == "deescalated":
            self._log(
                f"{npc_name} eases up after you {tactic.replace('_', ' ')}.",
                channel="social",
                priority="high",
                dedupe_window=8,
                dedupe_key=f"dialogue-guard:{npc_eid}:{outcome}:{tactic}",
            )
            return
        if outcome == "aggravated":
            self._log(
                f"{npc_name} is not buying it.",
                channel="alerts",
                priority="high",
                dedupe_window=8,
                dedupe_key=f"dialogue-guard:{npc_eid}:{outcome}:{tactic}",
            )
            return
        self._log(
            f"{npc_name} stays wary.",
            channel="alerts",
            priority="normal",
            dedupe_window=8,
            dedupe_key=f"dialogue-guard:{npc_eid}:{outcome}:{tactic}",
        )

    def on_contact_learned(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        referred_eid = event.data.get("referred_eid")
        if referred_eid is not None:
            referred_name = str(event.data.get("referred_name", "")).strip() or _entity_display_name(self.sim, referred_eid, title_case=True) or "someone"
            relation_kind = str(event.data.get("relation_kind", "")).replace("_", " ").strip().lower()
            prop = self.sim.properties.get(event.data.get("property_id"))
            source_eid = event.data.get("npc_eid")
            source_name = _entity_display_name(self.sim, source_eid, title_case=True) if source_eid is not None else "Someone"
            if prop:
                prop_name = str(prop.get("name", prop.get("id", "property"))).strip() or "their place"
                if relation_kind:
                    self.sim.log.add(f"Introduction: {source_name} points you to {referred_name}, their {relation_kind} at {prop_name}.")
                else:
                    self.sim.log.add(f"Introduction: {source_name} points you to {referred_name} at {prop_name}.")
                return
            if relation_kind:
                self.sim.log.add(f"Introduction: {source_name} points you to {referred_name}, their {relation_kind}.")
            else:
                self.sim.log.add(f"Introduction: {source_name} points you to {referred_name}.")
            return

        prop = self.sim.properties.get(event.data.get("property_id"))
        prop_name = str(prop.get("name", prop.get("id", "property"))).strip() if prop else "property"
        source_eid = event.data.get("npc_eid")
        source_name = _entity_display_name(self.sim, source_eid, title_case=True) if source_eid is not None else "Someone"
        labels = _contact_benefit_labels(event.data.get("benefits", ()))
        if labels:
            self.sim.log.add(f"Contact: {source_name} can vouch for you at {prop_name} ({', '.join(labels)}).")
            return
        self.sim.log.add(f"Contact: {source_name} gives you a lead at {prop_name}.")

    def on_hunting_carcass_harvested(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        animal = str(event.data.get("animal_name") or event.data.get("species_label") or "wildlife").strip()
        size_class = str(event.data.get("animal_size_class") or "").replace("_", " ").strip()
        output_name = str(event.data.get("output_item_name", "meat")).strip() or "meat"
        quantity = int(event.data.get("quantity", 0) or 0)
        tool_id = str(event.data.get("tool_item_id") or "").strip().lower()
        tool_name = item_display_name(tool_id, item_catalog=ITEM_CATALOG) if tool_id else "a blade"
        tool_phrase = f"with your {tool_name}" if tool_id else f"with {tool_name}"
        animal_text = f"the {size_class} {animal}" if size_class else animal
        output_label = output_name.lower() if output_name else "meat"
        if bool(event.data.get("kill_bag_used")):
            _log_player_feedback(
                self.sim,
                f"You cut and bagged {quantity} piece{'s' if quantity != 1 else ''} of {output_label} from the remains of {animal_text} {tool_phrase}.",
                kind="craft",
            )
            return
        _log_player_feedback(
            self.sim,
            f"You were able to cut {quantity} piece{'s' if quantity != 1 else ''} of {output_label} from the remains of {animal_text} {tool_phrase}.",
            kind="craft",
        )

    def on_hunting_carcass_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        reason = str(event.data.get("reason", "blocked") or "blocked").strip().lower()
        animal = str(event.data.get("animal_name") or "the carcass").strip()
        if reason == "no_tool":
            _log_player_feedback(self.sim, f"You need a blade or field knife to dress {animal}.", kind="craft")
            return
        if reason == "inventory_full":
            _log_player_feedback(self.sim, "No room for the field-dressed meat. Free up space and try again.", kind="craft")
            return
        if reason == "no_usable_meat":
            _log_player_feedback(self.sim, f"{animal} has no usable cuts worth packing.", kind="craft")
            return
        _log_player_feedback(self.sim, "That carcass is no longer available.", kind="craft")

    def on_flora_harvested(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        plant_name = str(event.data.get("plant_name") or "plant").strip() or "plant"
        output_name = str(event.data.get("output_item_name") or "plant material").strip() or "plant material"
        units = int(event.data.get("material_units", 1) or 1)
        method = str(event.data.get("harvest_method") or "harvest").replace("_", " ").strip()
        plant_part = str(event.data.get("plant_part") or "").replace("_", " ").strip().lower()
        tool_id = str(event.data.get("tool_item_id") or "").strip().lower()
        if tool_id:
            tool_name = item_display_name(tool_id, item_catalog=ITEM_CATALOG)
            tool_phrase = f" with your {tool_name}"
        elif method == "pluck":
            tool_phrase = " by hand"
        else:
            tool_phrase = ""
        exhausted = bool(event.data.get("harvest_exhausted"))
        remaining = int(event.data.get("harvest_remaining", 0) or 0)
        if exhausted:
            tail = " The patch is picked over now."
        elif remaining > 0:
            tail = f" The patch still has {remaining} small cut{'s' if remaining != 1 else ''} left."
        else:
            tail = ""
        if plant_part and plant_part not in {"plant material", "leaf", "open blossom"}:
            output_phrase = f"{plant_part} as {output_name}"
        else:
            output_phrase = output_name
        _log_player_feedback(
            self.sim,
            f"You {method} {plant_name}{tool_phrase} and pack {output_phrase} ({units} unit{'s' if units != 1 else ''}).{tail}",
            kind="craft",
        )

    def on_flora_harvest_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        reason = str(event.data.get("reason", "blocked") or "blocked").strip().lower()
        plant_name = str(event.data.get("plant_name") or "the plant").strip() or "the plant"
        method = str(event.data.get("harvest_method") or "harvest").replace("_", " ").strip() or "harvest"
        if reason == "no_flora":
            _log_player_feedback(self.sim, "No harvestable plant is close enough.", kind="craft")
            return
        if reason == "picked":
            _log_player_feedback(self.sim, f"{plant_name} is already picked over.", kind="craft")
            return
        if reason == "no_tool":
            _log_player_feedback(self.sim, f"You need the right tool to {method} {plant_name}.", kind="craft")
            return
        if reason == "inventory_full":
            _log_player_feedback(self.sim, "No room for the plant material. Free up space and try again.", kind="craft")
            return
        _log_player_feedback(self.sim, "That plant cannot be harvested right now.", kind="craft")

    def on_flora_planted(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        plant_name = str(event.data.get("plant_name") or "plant").strip() or "plant"
        container = str(event.data.get("container_kind") or "ground").replace("_", " ").strip() or "ground"
        failed = bool(event.data.get("failed"))
        if failed:
            _log_player_feedback(
                self.sim,
                f"You plant {plant_name}, but this place is wrong for it. The start is already withering.",
                kind="craft",
            )
            return
        if container == "pot":
            _log_player_feedback(self.sim, f"You settle {plant_name} into a plant pot.", kind="craft")
        elif container == "planter":
            _log_player_feedback(self.sim, f"You plant {plant_name} in the planter.", kind="craft")
        else:
            _log_player_feedback(self.sim, f"You plant {plant_name} in the ground.", kind="craft")

    def on_flora_planting_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        reason = str(event.data.get("reason", "blocked") or "blocked").strip().lower()
        plant_name = str(event.data.get("plant_name") or "that plant").strip() or "that plant"
        container = str(event.data.get("container_kind") or "").replace("_", " ").strip()
        if reason == "wrong_container":
            _log_player_feedback(self.sim, f"{plant_name} will not take in a pot. Try a planter or suitable ground.", kind="craft")
        elif reason == "no_empty_pot":
            _log_player_feedback(self.sim, f"You need an empty plant pot for {plant_name}.", kind="craft")
        elif reason == "bad_ground":
            _log_player_feedback(self.sim, "That ground will not take a planting.", kind="craft")
        elif reason == "consume_failed":
            _log_player_feedback(self.sim, f"{plant_name} would not leave your pack cleanly.", kind="craft")
        elif reason == "no_target":
            _log_player_feedback(self.sim, "Aim at a planter or open ground, or carry an empty plant pot.", kind="craft")
        else:
            target = f" in the {container}" if container else ""
            _log_player_feedback(self.sim, f"You cannot plant {plant_name}{target} right now.", kind="craft")

    def on_flora_crossbred(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        pollen = str(event.data.get("pollen_plant_name") or "one plant").strip() or "one plant"
        target = str(event.data.get("target_plant_name") or "the other").strip() or "the other"
        output = str(event.data.get("output_item_name") or "hybrid seed packet").strip() or "hybrid seed packet"
        _log_player_feedback(
            self.sim,
            f"You dust {target} with {pollen} and collect {output}.",
            kind="craft",
        )

    def on_flora_crossbreed_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        reason = str(event.data.get("reason", "blocked") or "blocked").strip().lower()
        target = str(event.data.get("target_name") or "that plant").strip() or "that plant"
        if reason == "target_not_open":
            _log_player_feedback(self.sim, f"{target} is not open enough to take pollen right now.", kind="craft")
        elif reason == "incompatible":
            _log_player_feedback(self.sim, f"The pollen will not take on {target}.", kind="craft")
        elif reason == "spent_fertility":
            _log_player_feedback(self.sim, f"{target} has no fertile blooms left.", kind="craft")
        elif reason == "inventory_full":
            _log_player_feedback(self.sim, "No room for the seed packet. Free up space and try again.", kind="craft")
        else:
            _log_player_feedback(self.sim, "That cross will not take right now.", kind="craft")

    def on_potted_plant_placed(self, event):
        if event.data.get("eid") == self.player_eid:
            item_name = str(event.data.get("item_name") or "potted plant").strip() or "potted plant"
            _log_player_feedback(self.sim, f"Set down {item_name}.", kind="interaction")

    def on_potted_plant_picked_up(self, event):
        if event.data.get("eid") == self.player_eid:
            item_name = str(event.data.get("item_name") or "potted plant").strip() or "potted plant"
            _log_player_feedback(self.sim, f"Picked up {item_name}. Growth pauses while you carry it.", kind="pickup")

    def on_herbal_medicine_crafted(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        output_name = str(event.data.get("output_item_name") or "herbal medicine").strip() or "herbal medicine"
        count = int(event.data.get("ingredient_count", 0) or 0)
        recipe_name = str(event.data.get("recipe_name") or "recipe").strip() or "recipe"
        credits = int(event.data.get("credits_spent", 0) or 0)
        text = f"You turned {count} plant material{'s' if count != 1 else ''} into {output_name} using {recipe_name}."
        if credits > 0:
            text = f"You paid {credits} cr and " + text[0].lower() + text[1:]
        _log_player_feedback(self.sim, text, kind="craft")

    def on_herbal_recipe_purchased(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        recipe_name = str(event.data.get("recipe_name") or "herbal recipe").strip() or "herbal recipe"
        output_name = str(event.data.get("output_item_name") or "medicine").strip() or "medicine"
        credits = int(event.data.get("credits_spent", 0) or 0)
        revealed = tuple(event.data.get("revealed_plants", ()) or ())
        suffix = ""
        if revealed:
            names = []
            for row in revealed[:2]:
                if isinstance(row, dict):
                    name = str(row.get("plant_name") or "").strip()
                    class_id = str(row.get("chemistry_class") or "").replace("_", " ").strip()
                    if name and class_id:
                        names.append(f"{name} is {class_id}")
            if names:
                suffix = " " + "; ".join(names) + "."
        _log_player_feedback(self.sim, f"You bought {recipe_name} for {credits} cr; it makes {output_name}.{suffix}", kind="commerce")

    def on_hunter_party_carcass_dressed(self, event):
        player_pos = self.sim.ecs.get(Position).get(self.player_eid)
        if player_pos is None:
            return
        try:
            x = int(event.data.get("x", 0))
            y = int(event.data.get("y", 0))
            z = int(event.data.get("z", 0))
        except (TypeError, ValueError):
            return
        if int(player_pos.z) != z or _manhattan(int(player_pos.x), int(player_pos.y), x, y) > 18:
            return
        animal = str(event.data.get("animal_name") or "wildlife").strip() or "wildlife"
        self.sim.log.add(f"Hunters dress {animal} near their game rack.", channel="world", priority="normal")

    def on_site_service_used(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        service = str(event.data.get("service", "")).strip().lower()
        prop_name = str(event.data.get("property_name", "site")).strip() or "site"
        skill_note = _sentence_from_note(event.data.get("skill_note", ""))
        if service in CASINO_GAME_SERVICE_IDS:
            stake = int(event.data.get("stake", event.data.get("wager", 0)))
            payout = int(event.data.get("payout", 0))
            net_credits = int(event.data.get("net_credits", payout - stake))
            headline = str(event.data.get("headline", "")).strip() or f"You play {_site_service_label(service)}."
            summary = str(event.data.get("summary", "")).strip() or headline
            social_gain = int(event.data.get("social_gain", 0))
            social_note = f" So +{social_gain}." if social_gain > 0 else ""
            self.sim.log.add(
                f"{_casino_game_title(service)}: {prop_name}. {summary} "
                f"Stake {stake}c, payout {payout}c, net {net_credits:+d}c.{social_note}"
            )
            return
        if service == "fuel":
            fuel_gain = int(event.data.get("fuel_gain", 0))
            credits_spent = int(event.data.get("credits_spent", 0))
            base_credits_spent = int(event.data.get("base_credits_spent", credits_spent))
            fuel = int(event.data.get("fuel", 0))
            fuel_capacity = int(event.data.get("fuel_capacity", 0))
            vehicle_name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
            text = f"Fuel: {prop_name} refuels {vehicle_name} (+{fuel_gain}, -{credits_spent}c, {fuel}/{fuel_capacity})."
            if base_credits_spent > credits_spent:
                text += f" Quoted down from {base_credits_spent}c."
            if skill_note:
                text += f" {skill_note}"
            self.sim.log.add(text)
            return
        if service == "repair":
            durability_gain = int(event.data.get("durability_gain", 0))
            durability = int(event.data.get("durability", 0))
            durability_max = int(event.data.get("durability_max", 10))
            credits_spent = int(event.data.get("credits_spent", 0))
            base_credits_spent = int(event.data.get("base_credits_spent", credits_spent))
            vehicle_name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
            text = (
                f"Repair: {prop_name} patches up {vehicle_name} "
                f"(+{durability_gain}D, -{credits_spent}c, {durability}/{durability_max})."
            )
            if base_credits_spent > credits_spent:
                text += f" Quoted down from {base_credits_spent}c."
            if skill_note:
                text += f" {skill_note}"
            self.sim.log.add(text)
            return
        if service == "vending":
            item_name = str(event.data.get("item_name", "snack")).strip() or "snack"
            credits_spent = int(event.data.get("credits_spent", 0))
            _log_player_feedback(self.sim, f"You bought {item_name} from {prop_name} for {credits_spent} cr.", kind="commerce")
            return
        if service in {"herbal_prepare", "herbal_compound"}:
            item_name = str(event.data.get("output_item_name", "herbal medicine")).strip() or "herbal medicine"
            count = int(event.data.get("ingredient_count", 0) or 0)
            credits_spent = int(event.data.get("credits_spent", 0) or 0)
            if service == "herbal_prepare":
                _log_player_feedback(
                    self.sim,
                    f"You paid {prop_name} {credits_spent} cr to prepare {count} plant material{'s' if count != 1 else ''} into {item_name}.",
                    kind="commerce",
                )
            else:
                _log_player_feedback(
                    self.sim,
                    f"You compounded {count} plant material{'s' if count != 1 else ''} into {item_name} at {prop_name}.",
                    kind="craft",
                )
            return
        if service == "herbal_recipe_sales":
            recipe_name = str(event.data.get("recipe_name", "herbal recipe")).strip() or "herbal recipe"
            credits_spent = int(event.data.get("credits_spent", 0) or 0)
            _log_player_feedback(self.sim, f"You bought {recipe_name} from {prop_name} for {credits_spent} cr.", kind="commerce")
            return
        if service == "campfire_cook":
            input_units = int(event.data.get("input_units", 0) or 0)
            output_units = int(event.data.get("output_units", 0) or 0)
            item_name = str(event.data.get("output_item_name", "cooked meat")).strip() or "cooked meat"
            _log_player_feedback(
                self.sim,
                f"You cooked {input_units} meat into {output_units} {item_name} at {prop_name}.",
                kind="craft",
            )
            return
        if service == "butcher_prepare":
            input_units = int(event.data.get("input_units", 0) or 0)
            output_units = int(event.data.get("output_units", 0) or 0)
            item_name = str(event.data.get("output_item_name", "packaged meat")).strip() or "packaged meat"
            credits_spent = int(event.data.get("credits_spent", 0) or 0)
            _log_player_feedback(
                self.sim,
                f"You paid {prop_name} {credits_spent} cr to prepare {input_units} meat into {output_units} {item_name}.",
                kind="commerce",
            )
            return
        if service in TRANSIT_SERVICE_IDS:
            profile = _transit_service_profile(service) or {}
            title = _transit_service_log_prefix(service)
            mode_label = _transit_service_mode_label(service)
            destination_name = str(event.data.get("destination_name", "the next stop")).strip() or "the next stop"
            distance = max(1, int(event.data.get("distance", 0) or 0))
            fare_mode = str(event.data.get("fare_mode", "credits")).strip().lower() or "credits"
            credits_spent = int(event.data.get("credits_spent", 0) or 0)
            token_cost = int(event.data.get("token_cost", 0) or 0)
            time_advanced_ticks = int(event.data.get("time_advanced_ticks", 0) or 0)
            text = f"{title}: {prop_name} sends you to {destination_name} ({distance}c)."
            if fare_mode == "transit_daypass":
                text += " Ride covered by daypass."
            elif fare_mode == "city_pass_token":
                text += f" Ride covered by {_transit_token_amount_label(token_cost)}."
            else:
                text += f" Fare -{credits_spent}c."
            if time_advanced_ticks > 0:
                text += f" Travel time {_tick_duration_label(self.sim, time_advanced_ticks)}."
            if not profile:
                text = f"{title}: {prop_name} sends you to {destination_name} ({distance}c by {mode_label})."
            if skill_note:
                text += f" {skill_note}"
            self.sim.log.add(text)
            return
        if service == "underground_access":
            destination_name = str(event.data.get("destination_name", "the passage")).strip() or "the passage"
            destination_z = int(event.data.get("destination_z", 0) or 0)
            time_advanced_ticks = int(event.data.get("time_advanced_ticks", 0) or 0)
            level_note = " underground" if destination_z < 0 else " topside"
            text = f"Passage: {prop_name} leads to {destination_name}{level_note}."
            if time_advanced_ticks > 0:
                text += f" Travel time {_tick_duration_label(self.sim, time_advanced_ticks)}."
            self.sim.log.add(text)
            return
        if service in {"vehicle_sales_new", "vehicle_sales_used"}:
            vehicle_name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
            price = int(event.data.get("price", 0))
            base_price = int(event.data.get("base_price", price))
            quality = "new" if service == "vehicle_sales_new" else "used"
            key_note = " Key issued." if bool(event.data.get("key_issued", False)) else ""
            stats = _vehicle_sale_stats_text(event.data)
            stats_note = f" {stats}." if stats else ""
            price_note = f" Quoted down from {base_price}c." if base_price > price else ""
            skill_suffix = f" {skill_note}" if skill_note else ""
            self.sim.log.add(
                f"Vehicle purchase: {vehicle_name} ({quality}) for {price} credits at {prop_name}.{stats_note}{price_note}{key_note}{skill_suffix}"
            )
            return
        if service == "shelter":
            bits = []
            hp_gain = int(event.data.get("hp_gain", 0))
            energy_gain = int(event.data.get("energy_gain", 0))
            safety_gain = int(event.data.get("safety_gain", 0))
            social_gain = int(event.data.get("social_gain", 0))
            time_advanced_ticks = int(event.data.get("time_advanced_ticks", 0))
            interrupted = bool(event.data.get("interrupted"))
            interruption_reason = str(event.data.get("interruption_reason", "") or "").strip().lower()
            wake_cause = str(event.data.get("wake_cause", "") or "").strip().lower()
            if hp_gain > 0:
                bits.append(f"HP +{hp_gain}")
            if energy_gain > 0:
                bits.append(f"E +{energy_gain}")
            if safety_gain > 0:
                bits.append(f"S +{safety_gain}")
            if social_gain > 0:
                bits.append(f"So +{social_gain}")
            gains = " ".join(bits) if bits else "steadying your nerves"
            duration_note = f" over {_tick_duration_label(self.sim, time_advanced_ticks)}" if time_advanced_ticks > 0 else ""
            text = f"Shelter: {prop_name} lets you catch your breath{duration_note} ({gains})."
            if interrupted:
                if interruption_reason == "woken_by_noise" and wake_cause:
                    text += f" Nearby {wake_cause.replace('_', ' ')} wakes you."
                elif interruption_reason in {"justice_surrender", "justice_questioning", "actor_detained", "justice_booking_completed"}:
                    text += " Justice cuts the stay short."
                else:
                    text += " Danger cuts the stay short."
            self.sim.log.add(text)
            return
        if service == "rest":
            bits = []
            hp_gain = int(event.data.get("hp_gain", 0))
            energy_gain = int(event.data.get("energy_gain", 0))
            safety_gain = int(event.data.get("safety_gain", 0))
            social_gain = int(event.data.get("social_gain", 0))
            credits_spent = int(event.data.get("credits_spent", 0))
            time_advanced_ticks = int(event.data.get("time_advanced_ticks", 0))
            interrupted = bool(event.data.get("interrupted"))
            interruption_reason = str(event.data.get("interruption_reason", "") or "").strip().lower()
            wake_cause = str(event.data.get("wake_cause", "") or "").strip().lower()
            well_rested_granted = bool(event.data.get("well_rested_granted"))
            if hp_gain > 0:
                bits.append(f"HP +{hp_gain}")
            if energy_gain > 0:
                bits.append(f"E +{energy_gain}")
            if safety_gain > 0:
                bits.append(f"S +{safety_gain}")
            if social_gain > 0:
                bits.append(f"So +{social_gain}")
            gains = " ".join(bits) if bits else "a good night's sleep"
            duration_note = f", {_tick_duration_label(self.sim, time_advanced_ticks)}" if time_advanced_ticks > 0 else ""
            text = f"Rest: {prop_name} rents you a room (-{credits_spent}c{duration_note}). {gains}."
            if interrupted:
                if interruption_reason == "woken_by_noise" and wake_cause:
                    text += f" Nearby {wake_cause.replace('_', ' ')} wakes you."
                elif interruption_reason in {"justice_surrender", "justice_questioning", "actor_detained", "justice_booking_completed"}:
                    text += " Justice cuts the stay short."
                else:
                    text += " Danger cuts the stay short."
            elif well_rested_granted:
                text += " You feel well rested."
            self.sim.log.add(text)
            return
        if service == "vehicle_fetch":
            vehicle_name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
            credits_spent = int(event.data.get("credits_spent", 0))
            base_credits_spent = int(event.data.get("base_credits_spent", credits_spent))
            text = f"Fetch: {prop_name} dispatches a runner to retrieve your {vehicle_name} (-{credits_spent}c)."
            if base_credits_spent > credits_spent:
                text += f" Quoted down from {base_credits_spent}c."
            if skill_note:
                text += f" {skill_note}"
            self.sim.log.add(text)
            return

        self.sim.log.add(f"{prop_name} provides {_site_service_label(service)}.")

    def on_site_service_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        service = str(event.data.get("service", "")).strip().lower()
        prop_name = str(event.data.get("property_name", "site")).strip() or "site"
        reason = str(event.data.get("reason", "blocked")).strip().lower()
        if reason == "invalid_wager" and service in CASINO_GAME_SERVICE_IDS:
            self.sim.log.add(f"{_casino_game_title(service)}: {prop_name} refuses that stake. Pick one of the posted bets.")
            return
        if reason == "invalid_round" and service in CASINO_GAME_SERVICE_IDS:
            self.sim.log.add(f"{_casino_game_title(service)}: {prop_name} loses the round state. Start a fresh round.")
            return
        if reason == "cooldown":
            ready_in = int(event.data.get("ready_in", 0))
            self.sim.log.add(f"{prop_name} cannot help with {_site_service_label(service)} again yet ({ready_in}t).")
            return
        if service in TRANSIT_SERVICE_IDS and reason == "no_destinations":
            profile = _transit_service_profile(service) or {}
            title = _transit_service_log_prefix(service)
            line = str(
                profile.get("no_destinations_line", "No outbound transit service is posted from {prop_name} right now.")
            ).format(prop_name=prop_name)
            self.sim.log.add(f"{title}: {line}")
            return
        if service in TRANSIT_SERVICE_IDS and reason == "invalid_destination":
            title = _transit_service_log_prefix(service)
            self.sim.log.add(f"{title}: {prop_name} loses that departure off the board before you can board.")
            return
        if service in TRANSIT_SERVICE_IDS and reason == "leave_vehicle":
            title = _transit_service_log_prefix(service)
            self.sim.log.add(f"{title}: leave your vehicle before boarding at {prop_name}.")
            return
        if reason == "no_need" and service == "shelter":
            self.sim.log.add(f"You do not need to bunk at {prop_name} right now.")
            return
        if reason == "no_leads" and service == "intel":
            self.sim.log.add(f"{prop_name} has no fresh routes or leads right now.")
            return
        if reason == "no_vehicle" and service == "fuel":
            self.sim.log.add(f"Fuel: {prop_name} can only fuel a vehicle you own or have set active.")
            return
        if reason == "no_vehicle" and service == "repair":
            self.sim.log.add(f"Repair: {prop_name} can only work on a vehicle you own or have set active.")
            return
        if reason == "tank_full" and service == "fuel":
            vehicle_name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
            fuel = int(event.data.get("fuel", 0))
            fuel_capacity = int(event.data.get("fuel_capacity", 0))
            if fuel_capacity > 0:
                self.sim.log.add(f"Fuel: {vehicle_name} is already topped off at {prop_name} ({fuel}/{fuel_capacity}).")
            else:
                self.sim.log.add(f"Fuel: {vehicle_name} is already topped off at {prop_name}.")
            return
        if reason == "fully_repaired" and service == "repair":
            vehicle_name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
            durability = int(event.data.get("durability", 0))
            durability_max = int(event.data.get("durability_max", 10))
            self.sim.log.add(f"Repair: {vehicle_name} is already in solid shape at {prop_name} ({durability}/{durability_max}).")
            return
        if reason == "no_credits" and service == "fuel":
            cost = int(event.data.get("cost", 0))
            credits = int(event.data.get("credits", 0))
            vehicle_name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
            fuel = int(event.data.get("fuel", 0))
            fuel_capacity = int(event.data.get("fuel_capacity", 0))
            if fuel_capacity > 0:
                self.sim.log.add(
                    f"Fuel: {prop_name} charges {cost}c per unit for {vehicle_name}; you have {credits}c ({fuel}/{fuel_capacity})."
                )
            else:
                self.sim.log.add(f"Fuel: {prop_name} charges {cost}c per unit for {vehicle_name}; you have {credits}c.")
            return
        if reason == "no_credits" and service == "repair":
            cost = int(event.data.get("cost", 0))
            credits = int(event.data.get("credits", 0))
            vehicle_name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
            durability = int(event.data.get("durability", 0))
            durability_max = int(event.data.get("durability_max", 10))
            self.sim.log.add(
                f"Repair: {prop_name} quotes {cost}c per point for {vehicle_name}; you have {credits}c ({durability}/{durability_max})."
            )
            return
        if reason == "no_credits" and service == "vending":
            cost = int(event.data.get("cost", 0))
            credits = int(event.data.get("credits", 0))
            item_name = str(event.data.get("item_name", "snack")).strip() or "snack"
            self.sim.log.add(f"Vending: {item_name} costs {cost}c at {prop_name}; you only have {credits}c.")
            return
        if reason == "no_recipe" and service in {"herbal_prepare", "herbal_compound"}:
            self.sim.log.add(f"Herbal prep: learn a recipe before using {prop_name}.")
            return
        if reason == "no_ingredients" and service in {"herbal_prepare", "herbal_compound"}:
            self.sim.log.add(f"Herbal prep: you need known plant materials for a learned recipe at {prop_name}.")
            return
        if reason == "invalid_mix" and service in {"herbal_prepare", "herbal_compound"}:
            self.sim.log.add("Herbal prep: those plant materials do not satisfy the recipe. Nothing was consumed.")
            return
        if reason == "no_tool" and service == "herbal_compound":
            self.sim.log.add(f"Herbal prep: you need a mortar kit to compound herbs at {prop_name}.")
            return
        if reason == "all_known" and service == "herbal_recipe_sales":
            self.sim.log.add(f"Herbal recipe: you already know what {prop_name} is selling.")
            return
        if reason == "no_credits" and service in {"herbal_prepare", "herbal_recipe_sales"}:
            cost = int(event.data.get("cost", 0))
            credits = int(event.data.get("credits", 0))
            self.sim.log.add(f"Herbal service: {prop_name} needs {cost}c to start; you have {credits}c.")
            return
        if reason == "no_meat" and service == "campfire_cook":
            self.sim.log.add(f"Campfire: bring raw or bagged game meat to cook at {prop_name}.")
            return
        if reason == "no_meat" and service == "butcher_prepare":
            self.sim.log.add(f"Butcher: bring raw or bagged game meat to {prop_name}.")
            return
        if reason == "inventory_full" and service in {"campfire_cook", "butcher_prepare"}:
            self.sim.log.add(f"{prop_name} cannot return prepared meat until you free up inventory space.")
            return
        if reason == "inventory_full" and service in {"herbal_prepare", "herbal_compound"}:
            self.sim.log.add(f"{prop_name} cannot return prepared medicine until you free up inventory space.")
            return
        if reason == "no_credits" and service == "butcher_prepare":
            cost = int(event.data.get("cost", 0))
            credits = int(event.data.get("credits", 0))
            self.sim.log.add(f"Butcher: {prop_name} needs {cost}c to start; you have {credits}c.")
            return
        if reason == "no_tokens" and service in TRANSIT_SERVICE_IDS:
            title = _transit_service_log_prefix(service)
            token_cost = int(event.data.get("token_cost", 0) or 0)
            city_tokens = int(event.data.get("city_tokens", 0) or 0)
            daypasses = int(event.data.get("daypasses", 0) or 0)
            destination_name = str(event.data.get("destination_name", "that stop")).strip() or "that stop"
            inventory_label = _transit_inventory_label(city_tokens=city_tokens, daypasses=daypasses)
            self.sim.log.add(
                f"{title}: fare to {destination_name} from {prop_name} is {_transit_token_amount_label(token_cost)}; "
                f"you only have {inventory_label}."
            )
            return
        if reason == "no_credits" and service in TRANSIT_SERVICE_IDS:
            title = _transit_service_log_prefix(service)
            cost = int(event.data.get("cost", 0))
            credits = int(event.data.get("credits", 0))
            destination_name = str(event.data.get("destination_name", "that stop")).strip() or "that stop"
            self.sim.log.add(f"{title}: fare to {destination_name} from {prop_name} is {cost}c; you only have {credits}c.")
            return
        if reason == "inventory_full" and service == "vending":
            item_name = str(event.data.get("item_name", "snack")).strip() or "snack"
            self.sim.log.add(f"Vending: no room for {item_name}. Free an inventory slot first.")
            return
        if reason == "power_cut":
            self.sim.log.add(f"{prop_name} is offline. Power is out.")
            return
        if reason == "no_return_path" and service == "underground_access":
            self.sim.log.add(f"Passage: {prop_name} is not safe to enter right now. No verified way back to ground could be confirmed.")
            return
        if reason == "unavailable":
            if service == "vending":
                self.sim.log.add(f"Vending: {prop_name} does not dispense anything right now.")
                return
            if service in {"vehicle_sales_new", "vehicle_sales_used"}:
                quality = "new" if service.endswith("_new") else "used"
                self.sim.log.add(f"Vehicles: the posted {quality} offer at {prop_name} is gone.")
                return
            self.sim.log.add(f"{prop_name} is not offering {_site_service_label(service)} right now.")
            return
        if reason == "no_credits":
            cost = int(event.data.get("cost", 0))
            credits = int(event.data.get("credits", 0))
            self.sim.log.add(
                f"{_site_service_label(service).title()}: {prop_name} needs {cost}c; you only have {credits}c."
            )
            return
        if reason == "no_space" and service in {"vehicle_sales_new", "vehicle_sales_used"}:
            self.sim.log.add(f"Vehicles: no clear spot near {prop_name} to place the purchase.")
            return
        if reason == "key_storage_full" and service in {"vehicle_sales_new", "vehicle_sales_used"}:
            self.sim.log.add("You need a free inventory slot for the vehicle key.")
            return
        if reason == "no_vehicle" and service == "vehicle_fetch":
            self.sim.log.add(f"Fetch: you don't own any vehicles for {prop_name} to retrieve.")
            return
        self.sim.log.add(f"{prop_name} is not offering {_site_service_label(service)} right now.")

    def on_site_intel_report(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        prop_name = str(event.data.get("property_name", "site")).strip() or "site"
        lines = event.data.get("lines") or []
        display_limit = max(1, min(8, _int_or_default(event.data.get("display_limit"), 4)))
        note = _sentence_from_note(event.data.get("skill_note", ""))
        lead_item_name = str(event.data.get("lead_item_name", "") or "").strip()
        lead_delivery = str(event.data.get("lead_delivery", "") or "").strip().lower()
        lead_line = ""
        if lead_item_name:
            if lead_delivery == "ground":
                lead_line = f"Relay dead drop: {lead_item_name} falls beside the terminal."
            else:
                lead_line = f"Relay dead drop: {lead_item_name} slides into your bag."
        opportunity_title = str(event.data.get("lead_opportunity_title", "") or "").strip()
        opportunity_property_name = str(event.data.get("lead_opportunity_property_name", "") or "").strip()
        opportunity_line = ""
        if opportunity_title:
            if opportunity_property_name:
                opportunity_line = f"Lead opened: {opportunity_title} at {opportunity_property_name}."
            else:
                opportunity_line = f"Lead opened: {opportunity_title}."
        if not lines and not lead_line and not opportunity_line:
            self.sim.log.add(f"Intel: {prop_name} has nothing useful right now.")
            return

        if note:
            self.sim.log.add(f"Intel @{prop_name}: {note}")
        first = True
        for raw in lines[:display_limit]:
            text = _line_text(raw).strip()
            if not text:
                continue
            prefix = f"Intel @{prop_name}: " if first else "  "
            entry = _line_with_prefix(raw, prefix)
            segments = _line_segments(entry)
            if segments:
                self.sim.log.add_rich(segments, text=_line_text(entry))
            else:
                self.sim.log.add(_line_text(entry))
            first = False
        if lead_line:
            self.sim.log.add(lead_line)
        if opportunity_line:
            self.sim.log.add(opportunity_line)

    def on_vehicle_delivered(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        vehicle_name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
        site_name = str(event.data.get("site_prop_name", "site")).strip() or "site"
        self.sim.log.add(f"Delivery: your {vehicle_name} has arrived (courtesy of {site_name}).")

    def on_property_closing_time_warning(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        prop = self.sim.properties.get(event.data.get("property_id"))
        speaker_eid = event.data.get("speaker_eid")
        dedupe_key = f"closing-time:{event.data.get('property_id')}"
        if speaker_eid is not None and self.sim.ecs.get(Position).get(speaker_eid):
            quote, nearby_audio, other_floor_audio = self._closing_time_bark(speaker_eid, prop)
            self._log_npc_bark(
                speaker_eid,
                quote,
                nearby_audio,
                other_floor_audio,
                channel="alerts",
                priority="high",
                dedupe_key=dedupe_key,
            )
            return

        prop_name = str(event.data.get("property_name", "property")).strip() or "property"
        self._log(
            f"Closing time at {prop_name}. Somebody wants you heading out.",
            channel="alerts",
            priority="high",
            dedupe_window=4,
            dedupe_key=dedupe_key,
        )

    def on_npc_investigate(self, event):
        if event.data.get("source_eid") != self.player_eid:
            return
        npc_eid = event.data.get("npc_eid")
        quote, nearby_audio, other_floor_audio = self._investigation_bark(npc_eid, event)
        combat_noise = self._investigation_combat_noise(npc_eid, event)
        self._log_npc_bark(
            npc_eid,
            quote,
            nearby_audio,
            other_floor_audio,
            channel="combat" if combat_noise else "alerts",
            priority="critical" if combat_noise and self._investigation_bark_is_direct_target(npc_eid, event) else "high",
        )

    def on_npc_protect_ally(self, event):
        if event.data.get("against_eid") != self.player_eid:
            return

        relation = event.data.get("relation", "ally")
        npc_eid = event.data.get("npc_eid")
        quote, nearby_audio, other_floor_audio = self._protect_ally_bark(npc_eid, relation)
        self._log_npc_bark(npc_eid, quote, nearby_audio, other_floor_audio, channel="alerts", priority="high")

    def on_npc_warn_property(self, event):
        if event.data.get("offender_eid") != self.player_eid:
            return
        prop = self.sim.properties.get(event.data.get("property_id"))
        npc_eid = event.data.get("npc_eid")
        quote, nearby_audio, other_floor_audio = self._warning_bark(npc_eid, event, prop)
        self._log_npc_bark(npc_eid, quote, nearby_audio, other_floor_audio, channel="alerts", priority="high")

    def on_npc_conversation_refused(self, event):
        if event.data.get("target_eid") != self.player_eid:
            return
        npc_eid = event.data.get("npc_eid")
        quote = str(event.data.get("line", "") or "").strip() or "I am done talking to you."
        self._log_npc_bark(
            npc_eid,
            quote,
            "You hear someone shut down the conversation nearby.",
            "You hear someone refusing to talk on another floor.",
            channel="alerts",
            priority="high",
            dedupe_key=f"conversation_refused:{npc_eid}",
        )

    def on_npc_eject_target(self, event):
        if event.data.get("target_eid") != self.player_eid:
            return
        npc_eid = event.data.get("npc_eid") or event.data.get("enforcer_eid")
        place = str(event.data.get("property_name", "") or "").strip() or "this place"
        if bool(event.data.get("follow_required", False)):
            quote = f"Follow me out of {place}."
        else:
            quote = f"You need to leave {place}."
        self._log_npc_bark(
            npc_eid,
            quote,
            "You hear someone ordering you to leave nearby.",
            "You hear someone ordering you to leave from another floor.",
            channel="alerts",
            priority="high",
            dedupe_key=f"eject:{npc_eid}:{place}",
        )

    def on_npc_ejection_complied(self, event):
        if event.data.get("target_eid") != self.player_eid:
            return
        place = str(event.data.get("property_name", "") or "").strip() or "the property"
        self._log(
            f"You leave {place} before it escalates.",
            channel="general",
            priority="normal",
            dedupe_window=4,
            dedupe_key=f"ejection_complied:{event.data.get('property_id')}",
        )

    def on_npc_ejection_refused(self, event):
        if event.data.get("target_eid") != self.player_eid:
            return
        place = str(event.data.get("property_name", "") or "").strip() or "the property"
        self._log(
            f"You are still inside {place}; this is trespassing now.",
            channel="alerts",
            priority="high",
            dedupe_window=4,
            dedupe_key=f"ejection_refused:{event.data.get('property_id')}",
        )

    def on_npc_defend_property(self, event):
        if event.data.get("offender_eid") != self.player_eid:
            return
        prop = self.sim.properties.get(event.data.get("property_id"))
        npc_eid = event.data.get("npc_eid")
        quote, nearby_audio, other_floor_audio = self._defense_bark(npc_eid, event, prop)
        self._log_npc_bark(npc_eid, quote, nearby_audio, other_floor_audio, channel="combat", priority="critical")

    def _player_survival_need_warning(self, need, value):
        need = str(need or "").strip().lower()
        if need not in {"hunger", "thirst"}:
            return
        try:
            value = max(0.0, min(100.0, float(value)))
        except (TypeError, ValueError):
            value = 0.0

        if need == "hunger":
            text = (
                f"You are getting hungry ({value:.0f}/100). Hunger is draining energy; "
                "if it gets severe, starvation can damage you."
            )
        else:
            text = (
                f"You are getting thirsty ({value:.0f}/100). Thirst is slowing you down; "
                "if it gets severe, dehydration can damage you."
            )
        self._log(
            text,
            channel="general",
            priority="high",
            dedupe_window=90,
            dedupe_key=f"player_survival_need:{need}",
        )

    def on_npc_need_critical(self, event):
        npc_eid = event.data.get("npc_eid")
        need = event.data.get("need")
        value = event.data.get("value")
        if npc_eid is None or need is None or value is None:
            return
        if npc_eid == self.player_eid:
            self._player_survival_need_warning(need, value)
            return

        if (self.sim.tick + npc_eid) % 20 == 0:
            npc_name = self._npc_label(npc_eid)
            self._log_npc_message(npc_eid, f"{npc_name} critical {need} ({value:.1f}).")

    def on_npc_crime_attempt_started(self, event):
        npc_eid = event.data.get("npc_eid")
        if npc_eid in {None, self.player_eid}:
            return
        if not (self._player_can_perceive_entity(npc_eid) or self._player_can_perceive_event_position(event)):
            return
        intent = str(event.data.get("intent", "") or "").strip().lower()
        summary = str(event.data.get("summary", "") or "").strip()
        org_name = str(event.data.get("organization_name", "") or "").strip()
        method_label = str(event.data.get("plan_method_label", "") or "").strip()
        plan_stage = str(event.data.get("plan_stage", "") or "").strip().lower()
        plan_key = str(event.data.get("plan_key", "") or "").strip()
        record_area_warmth(
            self.sim,
            x=event.data.get("x"),
            y=event.data.get("y"),
            reason="crime_scene",
            score_delta=0.75,
            source_kind="crime_scene",
            source_id=plan_key or f"{npc_eid}:{intent}:{getattr(self.sim, 'tick', 0)}",
        )
        if plan_key:
            record_crime_plan_observation(
                self.sim,
                plan_key,
                observer_eid=self.player_eid,
                source_kind="witnessed_event",
                score_delta=CRIME_PLAN_OBSERVATION_WITNESS,
            )
        npc_name = self._npc_label(npc_eid)
        if intent == "rendezvousing_crew":
            if org_name and method_label:
                text = f"{npc_name} looks like they're linking up with {org_name} for a {method_label}."
            elif org_name:
                text = f"{npc_name} looks like they're linking up with {org_name} for a crew move."
            elif method_label:
                text = f"{npc_name} looks like they're linking up for a {method_label}."
            else:
                text = f"{npc_name} looks like they're linking up for a crew move."
        elif intent == "seeking_criminal_affiliation":
            if org_name:
                text = f"{npc_name} looks like they're trying to find a way into {org_name}."
            else:
                text = f"{npc_name} looks like they're trying to find a crew."
        elif intent == "casing_target":
            if org_name and method_label:
                text = f"{npc_name} is casing the block for {_possessive_label(org_name)} {method_label}."
            elif org_name:
                text = f"{npc_name} is casing the block for {org_name}."
            else:
                text = f"{npc_name} is casing the block."
        elif intent == "committing_property_crime":
            if org_name and method_label:
                text = f"{npc_name} looks like they're moving on {_possessive_label(org_name)} {method_label}."
            elif org_name:
                text = f"{npc_name} looks like they're moving on a soft target for {org_name}."
            elif method_label:
                text = f"{npc_name} looks like they're moving on a {method_label}."
            else:
                text = f"{npc_name} looks like they're moving on a soft target."
        elif method_label:
            stage_text = f" ({plan_stage})" if plan_stage else ""
            text = summary or f"{npc_name} is moving with a {method_label}{stage_text}."
        else:
            text = summary or f"{npc_name} is moving with criminal purpose."
        self._log(
            text,
            channel="alerts",
            priority="high",
            dedupe_window=8,
            dedupe_key=f"npc_crime_start:{npc_eid}:{intent}:{str(event.data.get('plan_key', '') or '')}",
        )

    def on_npc_crime_attempt_resolved(self, event):
        npc_eid = event.data.get("npc_eid")
        if npc_eid in {None, self.player_eid}:
            return
        if not (self._player_can_perceive_entity(npc_eid) or self._player_can_perceive_event_position(event)):
            return
        success = bool(event.data.get("success"))
        reason = str(event.data.get("reason", "") or "").strip().replace("_", " ")
        method_label = str(event.data.get("plan_method_label", "") or "").strip()
        plan_stage = str(event.data.get("plan_stage", "") or "").strip().lower()
        npc_name = self._npc_label(npc_eid)
        if success:
            if method_label:
                text = f"{npc_name} pulls off the {method_label} and starts clearing out."
            else:
                text = f"{npc_name} slips something and starts clearing out."
        else:
            text = f"{npc_name} loses their nerve around the target."
            if method_label:
                stage_text = f" during {plan_stage}" if plan_stage else ""
                text = f"{npc_name}'s {method_label}{stage_text} falls apart."
            if reason and reason not in {"cased target", "no loot"}:
                text = f"{npc_name}'s {method_label or 'move'} falls apart: {reason}."
        self._log(
            text,
            channel="alerts",
            priority="high" if success else "normal",
            dedupe_window=8,
            dedupe_key=f"npc_crime_resolved:{npc_eid}:{str(event.data.get('plan_key', '') or '')}:{int(success)}",
        )

    def on_crime_plan_disrupted(self, event):
        observer_eid = event.data.get("observer_eid")
        if observer_eid not in {None, self.player_eid} and not self._player_can_perceive_event_position(event):
            return
        if observer_eid is None and not self._player_can_perceive_event_position(event):
            return
        org_name = str(event.data.get("organization_name", "") or "").strip() or "A local crew"
        method_label = str(event.data.get("plan_method_label", "") or "").strip() or "crew move"
        action = str(event.data.get("action", "") or "").strip().lower()
        if action == "cancelled":
            text = f"{_possessive_label(org_name)} {method_label} gets spooked and breaks off."
            priority = "high"
        elif action == "delayed":
            text = f"{_possessive_label(org_name)} {method_label} gets spooked and slows down."
            priority = "normal"
        else:
            return
        self._log(
            text,
            channel="alerts",
            priority=priority,
            dedupe_window=8,
            dedupe_key=f"crime_plan_disrupted:{event.data.get('plan_key')}:{action}",
        )

    def on_npc_affiliation_attempt_resolved(self, event):
        npc_eid = event.data.get("npc_eid")
        if npc_eid in {None, self.player_eid}:
            return
        if not self._player_can_perceive_entity(npc_eid):
            return
        accepted = bool(event.data.get("accepted"))
        org_name = str(event.data.get("organization_name", "") or "").strip() or "the crew"
        npc_name = self._npc_label(npc_eid)
        if accepted:
            text = f"{npc_name} looks like they just got folded into {org_name}."
        else:
            text = f"{npc_name} gets brushed off trying to make a crew connection."
        self._log(
            text,
            channel="alerts",
            priority="normal",
            dedupe_window=10,
            dedupe_key=f"npc_affiliation:{npc_eid}:{org_name}:{int(accepted)}",
        )

    def on_property_trespass(self, event):
        if event.data.get("offender_eid") != self.player_eid:
            return
        prop = self.sim.properties.get(event.data.get("property_id"))
        label = _property_summary(self.sim, prop, viewer_eid=self.player_eid) if prop else str(event.data.get("property_id"))
        severity_label = str(event.data.get("severity_label", "trespass") or "trespass").strip().lower()
        currently_open = event.data.get("currently_open")
        standing_reason = str(event.data.get("standing_reason", "") or "").strip().lower()
        ingress_text = _ingress_label(
            event.data.get("ingress_kind"),
            event.data.get("aperture_kind"),
        )
        method_text = _ingress_method_label(event.data.get("ingress_method"))
        if severity_label == "suspicious" and currently_open is False:
            prefix = "After-hours presence"
        elif severity_label == "suspicious":
            prefix = "Suspicious presence"
        elif severity_label == "serious_trespass":
            prefix = "Serious trespass"
        else:
            prefix = "Trespass"

        if standing_reason == "contact":
            label = f"{label} via contact"
        elif standing_reason in {"family", "partner", "neighbor", "coworker"}:
            label = f"{label} via {standing_reason}"
        if ingress_text:
            label = f"{label} {ingress_text}"
        if method_text and method_text not in {"authorized", "door breach", "window entry", "alternate entry"}:
            label = f"{label} ({method_text})"

        if bool(event.data.get("witnessed", False)):
            self._log(f"{prefix}: {label}.", channel="alerts", priority="high", dedupe_window=4)
            ingress_method = str(event.data.get("ingress_method", "") or "").strip().lower()
            ingress_kind = str(event.data.get("ingress_kind", "") or "").strip().lower()
            aperture_kind = str(event.data.get("aperture_kind", "") or "").strip().lower()
            if ingress_method == "jimmied_side_entry":
                self._warn_once(
                    "jimmied_entry",
                    "Warning: a jimmied door breach is still trespass and can escalate if spotted.",
                )
            elif ingress_method == "forced_side_entry":
                self._warn_once(
                    "forced_side_entry",
                    "Warning: forcing a door is treated as overtly hostile ingress.",
                )
            elif ingress_method == "quiet_window_entry":
                self._warn_once(
                    "quiet_window_entry",
                    "Warning: even quiet window entry can draw armed response in sensitive properties.",
                )
            if ingress_kind == "alternate_aperture" and _is_window_aperture(aperture_kind):
                self._warn_once(
                    "window_entry",
                    "Warning: window entry is often treated as hostile ingress even before outright violence.",
                )
            elif ingress_kind in {"boundary_breach", "deep_breach"}:
                self._warn_once(
                    "forced_breach",
                    "Warning: forced breaches are treated as overt hostile entry and can trigger immediate defense.",
                )
            self._warn_once(
                "trespass",
                "Warning: protected spaces can escalate from suspicion to intervention if witnesses care.",
            )
        else:
            self._log(f"{prefix} (unseen): {label}.", channel="alerts", priority="high", dedupe_window=4)

    def on_property_tamper(self, event):
        if event.data.get("offender_eid") != self.player_eid:
            return
        prop = self.sim.properties.get(event.data.get("property_id"))
        label = _property_summary(self.sim, prop, viewer_eid=self.player_eid) if prop else str(event.data.get("property_id"))
        ingress_text = _ingress_label(
            event.data.get("ingress_kind"),
            event.data.get("aperture_kind"),
        )
        method_text = _ingress_method_label(event.data.get("ingress_method"))
        if ingress_text:
            label = f"{label} {ingress_text}"
        if method_text and method_text not in {"authorized", "door breach", "window entry", "alternate entry"}:
            label = f"{label} ({method_text})"
        witnessed = bool(event.data.get("witnessed", False))
        ingress_kind = str(event.data.get("ingress_kind", "") or "").strip().lower()
        ingress_method = str(event.data.get("ingress_method", "") or "").strip().lower()
        breach_severity = float(event.data.get("breach_severity", 0.0) or 0.0)
        if _quiet_unwitnessed_tamper(
            prop,
            witnessed=witnessed,
            ingress_kind=ingress_kind,
            ingress_method=ingress_method,
            breach_severity=breach_severity,
        ):
            self._log(f"Quiet tamper (unseen): {label}.", channel="alerts", priority="high", dedupe_window=4)
            self._warn_once(
                "quiet_tamper",
                "Warning: quiet tampering stays quieter while unseen, but witnesses can still turn it into a real problem.",
            )
            return
        if witnessed:
            self._log(f"Tampering: {label}.", channel="alerts", priority="high", dedupe_window=4)
            self._warn_once(
                "tamper",
                "Warning: tampering is a threatening action and can trigger armed protection.",
            )
            return
        self._log(f"Tampering (unseen): {label}.", channel="alerts", priority="high", dedupe_window=4)
        self._warn_once(
            "unseen_tamper",
            "Warning: unseen tampering still alters the site, but it only becomes reportable once somebody actually sees you.",
        )

    def on_action_offense(self, event):
        if event.data.get("offender_eid") != self.player_eid:
            return
        observation = event_observation_accountability(
            self.sim,
            event,
            offender_eid=self.player_eid,
            default_channels=("actor_witness",),
            use_legacy_witness_fallback=False,
        )
        if not bool(observation.get("has_accountable_observation")):
            return

        offense_score = int(event.data.get("offense_score", 0))
        if offense_score < 20:
            return

        tier = event.data.get("offense_tier", _offense_tier(offense_score))
        action = event.data.get("action", "action")
        context = event.data.get("context", "ordinary")
        site_name = self._event_site_name(event)
        site_text = f" at {site_name}" if site_name else ""
        action_label = self._action_event_label(action)
        target_name = str(event.data.get("target_name", "") or "").strip()
        wildlife_text = f" to {target_name}" if target_name else ""
        if context == "contraband_use":
            summary = f"Contraband exposed{site_text}: {action_label}."
            self._warn_once(
                "contraband",
                "Warning: obvious contraband use can alarm nearby people and provoke a harsher response.",
            )
        elif context == "wildlife_harassment":
            summary = f"Wildlife harmed{site_text}: {action_label}{wildlife_text}."
            self._warn_once(
                "wildlife_harassment",
                "Warning: roughing up wildlife can still draw attention, but it is not treated like assaulting a person.",
            )
        elif context == "wildlife_hunting":
            summary = f"Wildlife harmed{site_text}: {action_label}{wildlife_text}."
            self._warn_once(
                "wildlife_hunting",
                "Warning: harming wildlife is still noticed, but it does not carry the same civic response as attacking a person.",
            )
        elif context == "unarmed_assault":
            summary = f"Violence witnessed{site_text}: {action_label}."
            self._warn_once(
                "unarmed_assault",
                "Warning: even an unarmed assault can turn bystanders and escalate the scene quickly.",
            )
        elif context == "melee_assault":
            summary = f"Violence witnessed{site_text}: {action_label}."
            self._warn_once(
                "melee_assault",
                "Warning: armed melee is read as more serious than a fistfight and can trigger a violent response.",
            )
        elif context == "armed_assault":
            summary = f"Violence witnessed{site_text}: {action_label}."
            self._warn_once(
                "shooting",
                "Warning: shooting is an overtly threatening action and can trigger immediate violence.",
            )
        elif context == "explosive_discharge":
            summary = f"Explosion witnessed{site_text}: {action_label}."
            self._warn_once(
                "explosives",
                "Warning: explosives are openly hostile and can trigger immediate violent response.",
            )
        else:
            summary = f"Offense witnessed{site_text}: {action_label}."
        self._log(
            f"{summary} Risk {tier} ({offense_score}).",
            channel="alerts",
            priority="high",
            dedupe_window=4,
        )

    def on_npc_offended(self, event):
        if event.data.get("offender_eid") != self.player_eid:
            return

        perceived = float(event.data.get("perceived", 0.0))
        if perceived < 0.55:
            return

        npc_eid = event.data.get("npc_eid")
        quote, nearby_audio, other_floor_audio = self._offended_bark(event)
        self._log_npc_bark(npc_eid, quote, nearby_audio, other_floor_audio, channel="alerts", priority="high")

    def on_item_picked_up(self, event):
        eid = event.data.get("eid")
        item_name = event.data.get("item_name", event.data.get("item_id", "item"))
        qty = event.data.get("quantity", 1)
        cash_pickup = bool(event.data.get("cash_pickup"))
        credits_gained = int(event.data.get("credits_gained", 0) or 0)

        if eid == self.player_eid:
            if cash_pickup and credits_gained > 0:
                _log_player_feedback(self.sim, f"Pocketed {credits_gained} credits.", kind="pickup")
                return
            if qty == 1:
                _log_player_feedback(self.sim, f"Picked up {item_name}.", kind="pickup")
            else:
                _log_player_feedback(self.sim, f"Picked up {item_name} x{qty}.", kind="pickup")
            return

        if not (
            self._player_can_perceive_entity(eid)
            or self._player_can_perceive_event_position(event)
        ):
            return

        npc_name = self._npc_label(eid)
        if qty == 1:
            self._log_npc_message(eid, f"{npc_name} picked up {item_name}.", channel="general")
        else:
            self._log_npc_message(eid, f"{npc_name} picked up {item_name} x{qty}.", channel="general")

    def on_item_pickup_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        reason = event.data.get("reason")
        item_name = self._event_item_label(event)
        if reason == "no_inventory":
            _log_player_feedback(self.sim, "You have no inventory access right now.", kind="pickup")
        elif reason == "map_mode":
            _log_player_feedback(self.sim, "Return to local view before picking up nearby items.", kind="pickup")
        elif reason == "no_item_nearby":
            _log_player_feedback(self.sim, "No item on or next to you to pick up.", kind="pickup")
        elif reason == "inventory_full":
            _log_player_feedback(self.sim, f"Inventory is full. Cannot pick up {item_name}.", kind="pickup")
        else:
            _log_player_feedback(self.sim, f"You cannot pick up {item_name} right now.", kind="pickup")

    def on_item_dropped(self, event):
        eid = event.data.get("eid")
        item_name = event.data.get("item_name", event.data.get("item_id", "item"))
        qty = event.data.get("quantity", 1)

        if eid == self.player_eid:
            _log_player_feedback(self.sim, f"Dropped {item_name} x{qty}.", kind="interaction")
            return

        if not (
            self._player_can_perceive_entity(eid)
            or self._player_can_perceive_event_position(event)
        ):
            return

        npc_name = self._npc_label(eid)
        self._log_npc_message(eid, f"{npc_name} dropped {item_name} x{qty}.", channel="general")

    def on_item_drop_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        reason = event.data.get("reason")
        item_name = self._event_item_label(event)
        if reason == "no_inventory":
            _log_player_feedback(self.sim, "You have no inventory access right now.", kind="interaction")
        elif reason == "inventory_empty":
            _log_player_feedback(self.sim, "Inventory is empty.", kind="interaction")
        elif reason == "remove_failed":
            _log_player_feedback(self.sim, f"{item_name} would not leave your inventory.", kind="interaction")
        else:
            _log_player_feedback(self.sim, f"You cannot drop {item_name} right now.", kind="interaction")

    def on_item_used(self, event):
        eid = event.data.get("eid")
        item_name = event.data.get("item_name", event.data.get("item_id", "item"))
        if eid == self.player_eid:
            item_id = str(event.data.get("item_id", "") or "").strip().lower()
            usage_kind = str(event.data.get("usage_kind", "") or "").strip().lower()
            if usage_kind == "throw":
                target_x = event.data.get("target_x")
                target_y = event.data.get("target_y")
                if target_x is not None and target_y is not None:
                    _log_player_feedback(self.sim, f"Threw {item_name} toward {int(target_x)},{int(target_y)}.", kind="interaction")
                else:
                    _log_player_feedback(self.sim, f"Threw {item_name}.", kind="interaction")
                return
            if usage_kind == "property_lead":
                if not bool(event.data.get("lead_changed")):
                    property_name = str(event.data.get("property_name", "") or "").strip()
                    hidden = bool(event.data.get("hidden"))
                    if property_name:
                        bucket = "hidden notebook" if hidden else "notebook"
                        _log_player_feedback(self.sim, f"{item_name} points to {property_name}, but you already filed it in your {bucket}.", kind="interaction")
                    else:
                        _log_player_feedback(self.sim, f"{item_name} does not tell you anything new.", kind="interaction")
                return
            if usage_kind == "justice_radio_scan":
                try:
                    mechanics = float(event.data.get("mechanics", 0.0) or 0.0)
                except (TypeError, ValueError):
                    mechanics = 0.0
                if not bool(event.data.get("success")):
                    _log_player_feedback(self.sim, f"{item_name} spits static, overheats, and dies. Mechanics {mechanics:.1f} was not enough.", kind="interaction")
                    return
                rows = list(event.data.get("scan_rows", ()) or ())
                duration = _int_or_default(event.data.get("duration"), 0)
                radius = _int_or_default(event.data.get("radius"), 0)
                if not rows:
                    _log_player_feedback(self.sim, f"{item_name} burns out after a clean sweep: no justice signals within {radius} tiles.", kind="interaction")
                    return
                nearest = []
                for row in rows[:3]:
                    if not isinstance(row, dict):
                        continue
                    distance = _int_or_default(row.get("distance"), 0)
                    role = str(row.get("role", "justice") or "justice").replace("_", " ")
                    nearest.append(f"{role} {distance}t")
                detail = "; ".join(nearest)
                if detail:
                    _log_player_feedback(self.sim, f"{item_name} burns out, but flags {len(rows)} justice signal(s) for {duration} ticks: {detail}.", kind="interaction")
                else:
                    _log_player_feedback(self.sim, f"{item_name} burns out, but flags {len(rows)} justice signal(s) for {duration} ticks.", kind="interaction")
                return
            applied = list(event.data.get("applied", ()) or ())
            credits_delta = 0
            for entry in applied:
                if not isinstance(entry, dict):
                    continue
                if str(entry.get("type", "")).strip().lower() != "credits":
                    continue
                try:
                    credits_delta += int(entry.get("delta", 0) or 0)
                except (TypeError, ValueError):
                    continue
            if item_id == "scratch_ticket":
                if credits_delta > 0:
                    _log_player_feedback(self.sim, f"You scratch the ticket and win {credits_delta} cr.", kind="game")
                elif credits_delta < 0:
                    _log_player_feedback(self.sim, f"You scratch the ticket and lose {abs(credits_delta)} cr.", kind="game")
                else:
                    _log_player_feedback(self.sim, "You scratch the ticket and it pays nothing.", kind="game")
                return
            bits = []
            for entry in applied:
                if not isinstance(entry, dict):
                    continue
                effect_type = str(entry.get("type", "")).strip().lower()
                if effect_type == "restore_hp":
                    delta = int(entry.get("delta", 0))
                    if delta > 0:
                        bits.append(f"HP +{delta}")
                    continue
                if effect_type == "modify_need":
                    need = str(entry.get("need", "")).strip().lower()
                    try:
                        delta = int(round(float(entry.get("delta", 0))))
                    except (TypeError, ValueError):
                        delta = 0
                    if delta == 0:
                        continue
                    label = {"energy": "E", "safety": "S", "social": "So"}.get(need, need[:2].upper() or "N")
                    sign = "+" if delta > 0 else ""
                    bits.append(f"{label} {sign}{delta}")
                    continue
                if effect_type == "status":
                    status = _status_effect_label(
                        entry.get("status", "status"),
                        duration=entry.get("duration", 0),
                        modifiers=entry.get("modifiers", {}),
                        title=False,
                        limit=2,
                    )
                    if status:
                        bits.append(status)
                    continue
                if effect_type == "credits":
                    try:
                        delta = int(entry.get("delta", 0) or 0)
                    except (TypeError, ValueError):
                        delta = 0
                    if delta:
                        bits.append(f"Cr {'+' if delta > 0 else ''}{delta}")
            if bits:
                _log_player_feedback(self.sim, f"Used {item_name} ({', '.join(bits[:4])}).", kind="interaction")
            else:
                _log_player_feedback(self.sim, f"Used {item_name}.", kind="interaction")
            return

        if (self.sim.tick + eid) % 17 == 0:
            npc_name = self._npc_label(eid)
            self._log_npc_message(eid, f"{npc_name} used {item_name}.")

    def on_armor_equipped(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        armor_name = event.data.get("armor_name", event.data.get("item_id", "armor"))
        reduction = int(round(float(event.data.get("damage_reduction", 0.0)) * 100.0))
        self.sim.log.add(f"Equipped {armor_name} ({reduction}% armor).")

    def on_armor_removed(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        armor_name = event.data.get("armor_name", event.data.get("item_id", "armor"))
        self.sim.log.add(f"Removed {armor_name}.")

    def on_appearance_item_equipped(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        item_name = str(event.data.get("item_name", event.data.get("item_id", "item"))).strip() or "item"
        slot = str(event.data.get("slot", "") or "").replace("_", " ").strip()
        suffix = f" ({slot})" if slot else ""
        _log_player_feedback(self.sim, f"Wearing {item_name}{suffix}.", kind="interaction")

    def on_appearance_item_unequipped(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        item_name = str(event.data.get("item_name", event.data.get("item_id", "item"))).strip() or "item"
        _log_player_feedback(self.sim, f"Removed {item_name}.", kind="interaction")

    def on_disguise_equipped(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        item_name = str(event.data.get("item_name", event.data.get("item_id", "disguise"))).strip() or "disguise"
        role_text = _disguise_role_label(event.data.get("role_id"), title_case=True)
        try:
            strength_pct = int(round(float(event.data.get("strength", 1.0)) * 100.0))
        except (TypeError, ValueError):
            strength_pct = 100
        strength_pct = max(1, strength_pct)
        self.sim.log.add(f"Disguise on: {item_name} ({role_text}, {strength_pct}%).")

    def on_disguise_removed(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        item_name = str(event.data.get("item_name", event.data.get("item_id", "disguise"))).strip() or "disguise"
        reason = str(event.data.get("reason", "") or "").strip().lower()
        if reason in {"dropped", "sold", "stashed"}:
            self.sim.log.add(f"Disguise lost: {item_name}.")
            return
        self.sim.log.add(f"Disguise off: {item_name}.")

    def on_disguise_blown(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        item_name = str(event.data.get("item_name", event.data.get("item_id", "disguise"))).strip() or "disguise"
        self._log(
            f"Disguise blown: {item_name}.",
            channel="alerts",
            priority="high",
            dedupe_window=6,
            dedupe_key=f"disguise-blown:{item_name.lower()}",
        )

    def on_camera_scrutiny(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        camera_name = str(event.data.get("camera_name", "camera") or "camera").strip() or "camera"
        role_text = _disguise_role_label(event.data.get("disguise_role"))
        confidence = max(0.0, min(1.0, float(event.data.get("confidence", 0.0) or 0.0)))
        if confidence >= 0.72:
            self._log(
                f"{camera_name} lingers on your {role_text} cover.",
                channel="alerts",
                priority="high",
                dedupe_window=8,
                dedupe_key=f"camera-scrutiny:{event.data.get('camera_property_id')}:{int(confidence * 10)}",
            )
            return
        self._log(
            f"{camera_name} tracks you, but the {role_text} cover still holds.",
            channel="alerts",
            priority="normal",
            dedupe_window=8,
            dedupe_key=f"camera-scrutiny:{event.data.get('camera_property_id')}:low",
        )

    def on_camera_alerted(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        camera_name = str(event.data.get("camera_name", "camera") or "camera").strip() or "camera"
        if bool(event.data.get("disguise_failed")):
            role_text = _disguise_role_label(event.data.get("disguise_role"))
            self._log(
                f"{camera_name} burns through your {role_text} cover.",
                channel="alerts",
                priority="high",
                dedupe_window=8,
                dedupe_key=f"camera-alert:{event.data.get('camera_property_id')}:cover",
            )
            return
        self._log(
            f"{camera_name} spots you.",
            channel="alerts",
            priority="high",
            dedupe_window=8,
            dedupe_key=f"camera-alert:{event.data.get('camera_property_id')}:plain",
        )

    def on_stakeout_started(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        property_name = str(event.data.get("property_name", "target site") or "target site").strip() or "target site"
        self._log(
            f"Stakeout started: {property_name}. Hold position while hidden.",
            channel="status",
            priority="normal",
            dedupe_window=10,
            dedupe_key=f"stakeout-start:{event.data.get('property_id')}",
        )

    def on_stakeout_ended(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        property_name = str(event.data.get("property_name", "target site") or "target site").strip() or "target site"
        reason = str(event.data.get("reason", "") or "").strip().lower()
        if reason == "observed":
            message = f"Stakeout blown: {property_name}."
        elif reason == "move":
            message = f"Stakeout broken: {property_name}."
        else:
            message = f"Stakeout ended: {property_name}."
        self._log(
            message,
            channel="status",
            priority="normal" if reason != "observed" else "high",
            dedupe_window=10,
            dedupe_key=f"stakeout-end:{event.data.get('property_id')}:{reason or 'ended'}",
        )

    def on_item_use_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        reason = event.data.get("reason")
        item_name = self._event_item_label(event, fallback="that item")
        if reason == "no_inventory":
            _log_player_feedback(self.sim, "You have no inventory access right now.", kind="interaction")
        elif reason == "no_usable_item":
            _log_player_feedback(self.sim, "No usable item in inventory.", kind="interaction")
        elif reason == "auto_only_item":
            _log_player_feedback(self.sim, f"{item_name} only triggers automatically in a critical state.", kind="interaction")
        elif reason == "downed_requires_medical":
            _log_player_feedback(self.sim, "You need restorative medical aid while downed.", kind="interaction")
        elif reason == "item_not_usable":
            _log_player_feedback(self.sim, f"{item_name} cannot be used.", kind="interaction")
        elif reason == "item_not_throwable":
            _log_player_feedback(self.sim, f"{item_name} is not something you can throw usefully.", kind="interaction")
        elif reason == "no_throw_target":
            _log_player_feedback(self.sim, f"Aim {item_name} away from yourself first.", kind="interaction")
        elif reason == "throw_out_of_range":
            _log_player_feedback(self.sim, f"{item_name} will not reach that far.", kind="interaction")
        elif reason == "wrong_floor":
            _log_player_feedback(self.sim, f"{item_name} cannot be thrown to another floor from here.", kind="interaction")
        elif reason == "no_property_lead":
            _log_player_feedback(self.sim, f"{item_name} does not point to any clear location right now.", kind="interaction")
        elif reason == "no_applicable_effect":
            _log_player_feedback(self.sim, f"{item_name} has no effect right now.", kind="interaction")
        elif reason == "consume_failed":
            _log_player_feedback(self.sim, f"{item_name} failed before it took effect.", kind="interaction")
        elif reason == "appearance_pack_full":
            _log_player_feedback(self.sim, f"Your pack is too full to stow {item_name}.", kind="interaction")
        elif reason == "appearance_armor_outer_active":
            _log_player_feedback(self.sim, "Armor is occupying your outer slot.", kind="interaction")
        elif reason == "appearance_slot_occupied":
            _log_player_feedback(self.sim, "That appearance slot is already occupied.", kind="interaction")
        elif str(reason or "").startswith("appearance_conflicts_"):
            _log_player_feedback(self.sim, f"{item_name} conflicts with what you are already wearing.", kind="interaction")
        else:
            _log_player_feedback(self.sim, f"You cannot use {item_name} right now.", kind="interaction")

    def on_report_device_used(self, event):
        npc_eid = event.data.get("npc_eid")
        if npc_eid == self.player_eid or not self._player_can_perceive_entity(npc_eid):
            return
        method = str(event.data.get("method", "") or "").strip().lower()
        if method == "radio":
            message = f"{self._npc_label(npc_eid)} keys a radio and calls for help."
        else:
            message = f"{self._npc_label(npc_eid)} makes a quick phone call."
        self._log_npc_message(
            npc_eid,
            message,
            channel="alerts",
            priority="normal",
            dedupe_window=6,
            dedupe_key=f"report-device:{npc_eid}:{event.data.get('incident_id')}:{method or 'device'}",
        )

    def on_justice_vehicle_misuse_barked(self, event):
        npc_eid = event.data.get("npc_eid") or event.data.get("observer_eid")
        offender_eid = event.data.get("offender_eid") or event.data.get("eid")
        if offender_eid != self.player_eid and not self._player_can_perceive_entity(npc_eid):
            return
        quote = str(event.data.get("quote", "") or "").strip() or "Police! Out of the vehicle!"
        self._log_npc_bark(
            npc_eid,
            quote,
            "A justice officer shouts nearby.",
            "A justice officer shouts from another floor.",
            channel="combat",
            priority="critical",
            dedupe_key=f"justice-vehicle-misuse:{npc_eid}:{event.data.get('incident_id')}",
        )

    def on_item_stolen(self, event):
        if event.data.get("offender_eid") != self.player_eid:
            return
        self._log(
            f"Stole {event.data.get('item_name', event.data.get('item_id', 'item'))}.",
            channel="alerts",
            priority="high",
        )
        self._warn_once(
            "theft",
            "Warning: theft is a threatening action and can trigger pursuit, intervention, or violence.",
        )

    def on_business_scene_posture_started(self, event):
        property_id = str(event.data.get("property_id", "") or "").strip()
        prop = self.sim.properties.get(property_id) if property_id else None
        if isinstance(prop, dict):
            if not (self._player_is_near_property(prop, radius=12) or self._player_can_perceive_event_position(event)):
                return
            prop_label = str(prop.get("name", property_id)).strip() or property_id
        else:
            if not self._player_can_perceive_event_position(event):
                return
            prop_label = str(event.data.get("property_name", property_id or "the site")).strip() or "the site"

        phase = str(event.data.get("event_phase", "") or "").strip().lower()
        label = _BUSINESS_POSTURE_PHASE_LABELS.get(phase)
        if not label:
            return
        scene_id = str(event.data.get("scene_id", "") or "").strip()
        self._log(
            f"{label} at {prop_label}.",
            channel="mission",
            priority="normal",
            dedupe_window=20,
            dedupe_key=f"business-posture:{scene_id or property_id}:{phase}",
        )

    def on_ambient_ritual_started(self, event):
        property_id = str(event.data.get("property_id", "") or "").strip()
        prop = self.sim.properties.get(property_id) if property_id else None
        if isinstance(prop, dict):
            if not (self._player_is_near_property(prop, radius=10) or self._player_can_perceive_event_position(event)):
                return
        elif not self._player_can_perceive_event_position(event):
            return
        text = str(event.data.get("log_text", "") or "").strip()
        if not text:
            return
        scene_id = str(event.data.get("scene_id", "") or "").strip()
        ritual_kind = str(event.data.get("ritual_kind", "") or "").strip().lower()
        self._log(
            text.rstrip(".") + ".",
            channel="general",
            priority="low",
            dedupe_window=30,
            dedupe_key=f"ambient-ritual:{scene_id or property_id}:{ritual_kind}",
        )

    def on_business_scene_nuisance(self, event):
        prop = self.sim.properties.get(event.data.get("property_id"))
        prop_label = _property_summary(self.sim, prop, viewer_eid=self.player_eid) if prop else (
            str(event.data.get("property_name", event.data.get("property_id", "the frontage"))).strip() or "the frontage"
        )
        offender_eid = event.data.get("offender_eid")
        owner_player = False
        if isinstance(prop, dict):
            owner_eid = prop.get("owner_eid")
            if owner_eid is not None and self.player_eid is not None:
                try:
                    owner_player = int(owner_eid) == int(self.player_eid)
                except (TypeError, ValueError):
                    owner_player = owner_eid == self.player_eid

        if not owner_player and not (
            self._player_can_perceive_entity(offender_eid)
            or self._player_can_perceive_event_position(event)
        ):
            return

        nuisance_kind = str(event.data.get("nuisance_kind", "") or "").strip().lower()
        loss_credits = max(0, int(event.data.get("loss_credits", 0) or 0))
        if owner_player and nuisance_kind == "skim" and loss_credits > 0:
            message = f"Frontage skim: {prop_label} lost {loss_credits} credits."
        elif owner_player:
            message = f"Soft-front pressure at {prop_label}."
        elif nuisance_kind == "skim":
            message = f"Soft front at {prop_label}: somebody is working the crowd for easy marks."
        else:
            message = f"Soft-front trouble stirs at {prop_label}."
        self._log(
            message,
            channel="alerts",
            priority="high" if owner_player else "normal",
            dedupe_window=8,
            dedupe_key=f"business-scene-nuisance:{event.data.get('property_id')}:{nuisance_kind or 'generic'}:{int(bool(owner_player))}",
        )

    def on_status_applied(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        status_text = _status_effect_label(
            event.data.get("status", "effect"),
            duration=event.data.get("duration", 0),
            modifiers=event.data.get("modifiers", {}),
            title=True,
            limit=3,
        )
        prefix = "Status applied" if bool(event.data.get("new", True)) else "Status refreshed"
        self._log(f"{prefix}: {status_text}.", channel="status", priority="high")

    def on_status_expired(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        status = _humanize_slug(event.data.get("status", "effect"), title=True) or "Effect"
        self._log(f"Status expired: {status}.", channel="status", priority="high")

    def on_movement_misdirected(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        _log_player_feedback(
            self.sim,
            "Your step slips sideways.",
            kind="movement",
            dedupe_window=3,
            dedupe_key="movement_misdirected",
        )

    def on_bonus_move_used(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        _log_player_feedback(
            self.sim,
            "You move before the moment closes.",
            kind="movement",
            dedupe_window=2,
            dedupe_key=f"bonus_move:{int(getattr(self.sim, 'tick', 0))}",
        )

    def on_control_lapse_started(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        duration = int(event.data.get("duration", 0) or 0)
        suffix = f" for {duration}t" if duration > 1 else " for a beat"
        _log_player_feedback(
            self.sim,
            f"Your body goes distant{suffix}.",
            kind="status",
            dedupe_window=4,
            dedupe_key="control_lapse_started",
        )

    def on_drug_blackout_started(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        ticks = int(event.data.get("duration_ticks", 0) or 0)
        duration = _tick_duration_label(self.sim, ticks) if ticks > 0 else "a while"
        self._log(f"You nod off. Time slips for {duration}.", channel="status", priority="high")

    def on_drug_blackout_resolved(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        ticks = int(event.data.get("time_advanced_ticks", 0) or 0)
        duration = _tick_duration_label(self.sim, ticks) if ticks > 0 else "a moment"
        if bool(event.data.get("interrupted")):
            reason = str(event.data.get("interruption_reason", "") or "").replace("_", " ").strip()
            suffix = f" ({reason})" if reason else ""
            self._log(f"You come back after {duration}{suffix}.", channel="status", priority="high")
            return
        self._log(f"You come back after {duration}.", channel="status", priority="high")

    def on_inventory_panel_toggled(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        open_state = bool(event.data.get("open"))
        panel_kind = str(event.data.get("panel_kind", "inventory")).strip().lower() or "inventory"
        title = str(event.data.get("title", "Inventory")).strip() or "Inventory"
        if panel_kind in {"cache", "container"}:
            self.sim.log.add(f"{title} {'opened' if open_state else 'closed'}.")
            return
        if open_state:
            self.sim.log.add("Inventory opened.")
        else:
            self.sim.log.add("Inventory closed.")

    def on_inventory_inspected(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        if event.data.get("empty"):
            panel_kind = str(event.data.get("panel_kind", "inventory")).strip().lower() or "inventory"
            title = str(event.data.get("title", "Inventory")).strip() or "Inventory"
            if panel_kind in {"cache", "container"}:
                self.sim.log.add(f"{title} is empty.")
            else:
                self.sim.log.add("Inventory empty.")
            return
        text = event.data.get("inspect_text")
        if text:
            self.sim.log.add(_line_text(_line_with_prefix(text, "Inspect: ")))

    def on_trade_panel_toggled(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        open_state = bool(event.data.get("open"))
        if open_state:
            mode = str(event.data.get("mode", "buy")).lower()
            store_name = event.data.get("store_name", "store")
            supply_note = str(event.data.get("supply_note", "")).strip()
            contact_note = str(event.data.get("contact_note", "")).strip()
            service_note = str(event.data.get("service_note", "")).strip()
            rows = int(event.data.get("rows", 0))
            mode_label = "BUY" if mode == "buy" else "SELL"
            extras = [note for note in (service_note, supply_note, contact_note) if note]
            if extras:
                self.sim.log.add(f"Trade {mode_label} panel opened at {store_name} ({rows} offers). {' '.join(extras)}.")
            else:
                self.sim.log.add(f"Trade {mode_label} panel opened at {store_name} ({rows} offers).")
        else:
            self.sim.log.add("Trade panel closed.")

    def on_trade_panel_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        reason = event.data.get("reason")
        store_name = self._event_property_name(event, fallback="That storefront")
        if reason == "no_store":
            self.sim.log.add("No storefront nearby for shopping.")
            return
        if reason == "no_machine_store":
            self.sim.log.add("No unattended machine nearby. Use E at a staffed counter.")
            return
        if reason == "no_street_vendor":
            self.sim.log.add("That street contact is not close enough to trade.")
            return
        if reason == "street_vendor_no_trade":
            self.sim.log.add("That street contact is not opening trade right now.")
            return
        if reason == "no_staff":
            self.sim.log.add(f"{store_name} has no clerk on the counter right now.")
            return
        self.sim.log.add(f"No shopping counter is ready at {store_name} right now.")

    def on_cover_taken(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        kind = str(event.data.get("cover_kind", "cover")).upper()
        value = int(float(event.data.get("cover_value", 0.0)) * 100)
        source_kind = str(event.data.get("source_kind", "cover")).strip().lower()
        block_dir = event.data.get("block_dir")
        dir_text = _dir_label(block_dir, short=False) if block_dir else "nearby"
        if source_kind == "wall":
            source_text = f"wall to the {dir_text}"
        elif source_kind == "property":
            property_id = event.data.get("property_id")
            prop = self.sim.properties.get(property_id) if property_id else None
            prop_name = prop.get("name") if prop else "property"
            source_text = f"{prop_name} to the {dir_text}"
        else:
            source_text = f"cover to the {dir_text}"
        self.sim.log.add(f"You take {kind} cover ({value}%) behind {source_text}.")

    def on_cover_left(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        reason = event.data.get("reason", "manual")
        if reason in {"moved", "floor_change"}:
            self.sim.log.add("You break cover.")
            return
        if reason == "displaced":
            self.sim.log.add("Cover lost: no valid cover object.")
            return
        self.sim.log.add("You leave cover.")

    def on_cover_shifted(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        kind = str(event.data.get("cover_kind", "cover")).upper()
        source_kind = str(event.data.get("source_kind", "cover")).strip().lower()
        block_dir = event.data.get("block_dir")
        dir_text = _dir_label(block_dir, short=False) if block_dir else "nearby"
        if source_kind == "wall":
            source_text = f"wall to the {dir_text}"
        elif source_kind == "property":
            property_id = event.data.get("property_id")
            prop = self.sim.properties.get(property_id) if property_id else None
            prop_name = prop.get("name") if prop else "property"
            source_text = f"{prop_name} to the {dir_text}"
        else:
            source_text = f"cover to the {dir_text}"
        self.sim.log.add(f"You shift into {kind} cover behind {source_text}.")

    def on_cover_hopped(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        steps = max(1, int(event.data.get("steps", 1)))
        kind = str(event.data.get("cover_kind", "cover")).upper()
        value = int(float(event.data.get("cover_value", 0.0)) * 100)
        source_kind = str(event.data.get("source_kind", "cover")).strip().lower()
        block_dir = event.data.get("block_dir")
        dir_text = _dir_label(block_dir, short=False) if block_dir else "nearby"
        if source_kind == "wall":
            source_text = f"wall to the {dir_text}"
        elif source_kind == "property":
            property_id = event.data.get("property_id")
            prop = self.sim.properties.get(property_id) if property_id else None
            prop_name = prop.get("name") if prop else "property"
            source_text = f"{prop_name} to the {dir_text}"
        else:
            source_text = f"cover to the {dir_text}"
        self.sim.log.add(f"You hop {steps} tiles into {kind} cover ({value}%) behind {source_text}.")

    def on_cover_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        reason = event.data.get("reason", "blocked")
        if reason == "missing_cover_state":
            self.sim.log.add("You are not braced to take cover right now.")
        elif reason == "no_cover_object":
            self.sim.log.add("Nothing solid nearby to use as cover.")
        elif reason == "cover_hop_requires_cover":
            self.sim.log.add("You need to be in cover before hopping.")
        elif reason == "no_cover_hop_target":
            self.sim.log.add("No reachable cover to hop into.")
        elif reason == "cover_hop_path_blocked":
            block_reason = str(event.data.get("block_reason", "") or "").strip().lower()
            detail = self._movement_blocked_message(
                reason=block_reason or "blocked",
                x=event.data.get("block_x"),
                y=event.data.get("block_y"),
                z=event.data.get("block_z"),
                property_id=event.data.get("property_id"),
            )
            self.sim.log.add(f"Cover hop blocked. {detail}")
        else:
            self.sim.log.add("You cannot settle into cover from here.")

    def on_rumor_shared(self, event):
        if event.data.get("offender_eid") != self.player_eid:
            return
        from_eid = event.data.get("from_eid")
        to_eid = event.data.get("to_eid")
        if from_eid is None or to_eid is None:
            return
        if (self.sim.tick + to_eid) % 6 != 0:
            return
        from_name = self._npc_label(from_eid)
        to_name = self._npc_label(to_eid)
        self._log_npc_message(from_eid, f"{from_name} warns {to_name} about you.")

    def on_npc_socialized(self, event):
        npc_eid = event.data.get("npc_eid")
        partner_eid = event.data.get("partner_eid")
        if npc_eid is None or partner_eid is None:
            return

        positions = self.sim.ecs.get(Position)
        player_pos = positions.get(self.player_eid)
        npc_pos = positions.get(npc_eid)
        partner_pos = positions.get(partner_eid)
        tone = str(event.data.get("tone", "gossip") or "").strip().lower()
        topic = str(event.data.get("topic", "") or "").strip().lower()
        quote = str(event.data.get("quote", "") or "").strip()
        summary = str(event.data.get("summary", "") or "").strip()
        channel = str(event.data.get("channel", "social") or "").strip().lower() or "social"
        priority = str(event.data.get("priority", "low") or "").strip().lower() or "low"
        dedupe_key = f"npc-socialized:{topic or tone}:{summary.lower() or npc_eid}"

        visible = False
        for pos in (npc_pos, partner_pos):
            if pos and self._player_has_los_to_position(pos.x, pos.y, pos.z):
                visible = True
                break

        if visible:
            speaker = self._npc_label(npc_eid)
            partner = self._npc_label(partner_eid)
            if quote:
                self._log_visible_social_quote(
                    npc_eid,
                    partner_eid,
                    speaker,
                    partner,
                    quote,
                    channel=channel,
                    priority=priority,
                    dedupe_window=8,
                    dedupe_key=dedupe_key,
                )
                return
            if tone == "conspiring":
                text = f"{speaker} huddles with {partner}."
            elif tone == "rambling":
                text = f"{speaker} rambles at {partner}."
            elif tone == "check_in":
                text = f"{speaker} checks in with {partner}."
            else:
                text = f"{speaker} chats with {partner}."
            self._log_npc_message(npc_eid, text, dedupe_window=4, dedupe_key=dedupe_key)
            return

        if player_pos and npc_pos and int(player_pos.z) != int(npc_pos.z):
            if summary:
                heard = summary.rstrip(".!?")
                self._log(
                    f"You hear someone on another floor mention {heard}.",
                    channel=channel,
                    priority=priority,
                    dedupe_window=8,
                    dedupe_key=dedupe_key,
                )
                return
            if tone == "conspiring":
                self._log("You hear low voices on another floor.", channel="social", priority="low", dedupe_window=4)
            elif tone == "rambling":
                self._log("You hear slurred voices on another floor.", channel="social", priority="low", dedupe_window=4)
            else:
                self._log("You hear voices on another floor.", channel="social", priority="low", dedupe_window=4)
            return

        if summary:
            heard = summary.rstrip(".!?")
            self._log(
                f"You overhear someone mention {heard}.",
                channel=channel,
                priority=priority,
                dedupe_window=8,
                dedupe_key=dedupe_key,
            )
            return
        if tone == "conspiring":
            self._log("You hear low voices nearby.", channel="social", priority="low", dedupe_window=4)
        elif tone == "rambling":
            self._log("You hear slurred voices nearby.", channel="social", priority="low", dedupe_window=4)
        else:
            self._log("You hear nearby conversation.", channel="social", priority="low", dedupe_window=4)

    def on_npc_partner_acknowledged(self, event):
        speaker_eid = event.data.get("speaker_eid")
        partner_eid = event.data.get("partner_eid")
        if speaker_eid is None or partner_eid is None:
            return
        positions = self.sim.ecs.get(Position)
        speaker_pos = positions.get(speaker_eid)
        partner_pos = positions.get(partner_eid)
        visible = False
        for pos in (speaker_pos, partner_pos):
            if pos and self._player_has_los_to_position(pos.x, pos.y, pos.z):
                visible = True
                break
        if not visible:
            return
        speaker = self._npc_label(speaker_eid)
        quote = str(event.data.get("quote", "") or "").strip()
        if not quote:
            partner = self._npc_label(partner_eid)
            quote = f"Hey, {partner}."
        dedupe_key = f"npc-partner-ack:{speaker_eid}:{partner_eid}:{str(quote).lower()}"
        self._log_npc_message(
            speaker_eid,
            f'{speaker}: "{quote}"',
            channel="social",
            priority="low",
            dedupe_window=12,
            dedupe_key=dedupe_key,
        )

    def on_animal_socialized(self, event):
        left_eid = event.data.get("eid")
        right_eid = event.data.get("partner_eid")
        if left_eid is None or right_eid is None:
            return
        positions = self.sim.ecs.get(Position)
        player_pos = positions.get(self.player_eid)
        left_pos = positions.get(left_eid)
        right_pos = positions.get(right_eid)
        if not left_pos and not right_pos:
            return
        summary = str(event.data.get("summary", "") or "").strip()
        dedupe_key = f"animal-socialized:{left_eid}:{right_eid}"

        visible = False
        for pos in (left_pos, right_pos):
            if pos and self._player_has_los_to_position(pos.x, pos.y, pos.z):
                visible = True
                break

        if visible and summary:
            self._log(summary.rstrip(".") + ".", channel="social", priority="low", dedupe_window=6, dedupe_key=dedupe_key)
            return
        if player_pos and left_pos and int(player_pos.z) != int(left_pos.z):
            self._log("You hear an animal settle nearby on another floor.", channel="social", priority="low", dedupe_window=6, dedupe_key=dedupe_key)
            return
        if summary:
            self._log(f"You notice {summary.rstrip('.')}.", channel="social", priority="low", dedupe_window=6, dedupe_key=dedupe_key)

    def on_weapon_equipped(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        name = event.data.get("weapon_name", event.data.get("weapon_id", "weapon"))
        self.sim.log.add(f"Equipped {name}.")

    def on_weapon_removed(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        name = event.data.get("weapon_name", event.data.get("weapon_id", "weapon"))
        self.sim.log.add(f"Stowed {name}.")

    def on_weapon_cycle_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        self.sim.log.add("No weapon in your loadout to equip.")

    def on_weapon_fired(self, event):
        eid = event.data.get("eid")
        weapon_id = event.data.get("weapon_id")
        weapon_name = str(event.data.get("weapon_name", weapon_id or "weapon")).strip() or "weapon"
        count = int(event.data.get("projectile_count", 1))
        profile = self._weapon_log_profile(weapon_id, projectile_count=count)
        if eid != self.player_eid:
            can_see = (
                self._player_can_perceive_entity(eid)
                or self._player_can_perceive_entity(event.data.get("target_eid"))
                or self._player_can_perceive_event_position(event)
            )
            can_hear = self._player_is_near_event_position(event, radius=10)
            if not can_see and not can_hear:
                return
            if not can_see:
                self._log(
                    "You hear gunfire nearby.",
                    channel="combat",
                    priority="high",
                    dedupe_window=2,
                    dedupe_key="combat-nearby-gunfire",
                )
                return
            npc_name = self._npc_label(eid)
            target_eid = event.data.get("target_eid")
            if target_eid == self.player_eid:
                target_text = " at you"
            elif target_eid is not None:
                target_text = f" at {self._npc_label(target_eid)}"
            else:
                target_text = ""
            self._log_npc_message(
                eid,
                f"{npc_name} {profile['npc_verb']} {weapon_name}{target_text}.",
                channel="combat",
                priority="high",
                dedupe_window=2,
            )
            return
        direction = str(event.data.get("direction_short", "")).strip()
        target_name = str(event.data.get("target_name", "")).strip()
        target_eid = event.data.get("target_eid")
        target_x = event.data.get("target_x")
        target_y = event.data.get("target_y")
        dist = event.data.get("target_dist")
        ammo_remaining = event.data.get("ammo_remaining")
        target_text = self._combat_target_text(target_eid, target_name, target_x, target_y)

        direction_text = f" {direction}" if direction else ""
        range_text = f" [{int(dist)}]" if dist is not None else ""
        action_text = f"You {profile['player_verb']} {profile['noun']} from {weapon_name}{direction_text}{range_text}{target_text}"
        if count > 1:
            ammo_text = f" ammo {int(ammo_remaining)}" if ammo_remaining is not None else ""
            self.sim.log.add(f"{action_text} ({count} projectiles{ammo_text}).")
        else:
            ammo_text = f" (ammo {int(ammo_remaining)})" if ammo_remaining is not None else ""
            self.sim.log.add(f"{action_text}.{ammo_text}")

    def on_melee_attack(self, event):
        attacker_eid = event.data.get("eid")
        target_eid = event.data.get("target_eid")
        weapon_name = str(event.data.get("weapon_name", "Unarmed") or "Unarmed").strip() or "Unarmed"

        if attacker_eid == self.player_eid:
            target_name = self._npc_label(target_eid)
            self._log_npc_message(
                target_eid,
                f"You strike {target_name} with {weapon_name}.",
                channel="combat",
                priority="high",
                dedupe_window=1,
            )
            return

        can_see = (
            self._player_can_perceive_entity(attacker_eid)
            or self._player_can_perceive_entity(target_eid)
            or self._player_can_perceive_event_position(event)
        )
        can_hear = self._player_is_near_event_position(event, radius=6)
        if not can_see and not can_hear:
            return
        if not can_see:
            self._log(
                "You hear a scuffle nearby.",
                channel="combat",
                priority="high",
                dedupe_window=2,
                dedupe_key="combat-nearby-scuffle",
            )
            return

        attacker_name = self._npc_label(attacker_eid)
        if target_eid == self.player_eid:
            message = f"{attacker_name} comes at you with {weapon_name}."
        elif target_eid is not None:
            message = f"{attacker_name} strikes {self._npc_label(target_eid)} with {weapon_name}."
        else:
            message = f"{attacker_name} swings {weapon_name}."
        self._log_npc_message(
            attacker_eid,
            message,
            channel="combat",
            priority="high",
            dedupe_window=1,
        )

    def on_projectile_impact(self, event):
        source_eid = event.data.get("source_eid")
        if source_eid != self.player_eid:
            return
        hit_eid = event.data.get("hit_eid")
        if hit_eid is not None:
            return

        if not self._player_can_perceive_event_position(event):
            return

        profile = self._weapon_log_profile(event.data.get("weapon_id"), projectile_count=max(1, int(event.data.get("hits", 0))))
        reason = str(event.data.get("reason", "impact") or "impact").strip().lower()
        thrown_name = str(event.data.get("thrown_item_name", "") or "").strip()
        if thrown_name and bool(event.data.get("shatter", False)):
            self._log(f"{thrown_name} shatters.", channel="combat", priority="high", dedupe_window=2)
            return
        if reason == "shattered_window":
            self._log("The shot shatters the window.", channel="combat", priority="high", dedupe_window=2)
            return
        if reason == "blocked_tile":
            self._log(profile["blocked"], channel="combat", priority="high", dedupe_window=2)
            return
        if reason == "range_end":
            self._log(profile["miss"], channel="combat", priority="high", dedupe_window=2)
            return

    def on_smoke_cloud_released(self, event):
        if event.data.get("source_eid") != self.player_eid:
            return
        if not self._player_can_perceive_event_position(event):
            return
        name = str(event.data.get("thrown_item_name", "") or "").strip() or "The canister"
        radius = int(event.data.get("radius", 0) or 0)
        duration = int(event.data.get("cloud_duration", 0) or 0)
        duration_text = f" for about {duration}t" if duration > 0 else ""
        self._log(f"{name} vents smoke r={radius}{duration_text}.", channel="combat", priority="high", dedupe_window=2)

    def on_aerosol_cloud_released(self, event):
        if event.data.get("source_eid") != self.player_eid:
            return
        if not self._player_can_perceive_event_position(event):
            return
        label = str(event.data.get("aerosol_label", "") or "").strip() or "aerosol"
        cooldown = int(event.data.get("aerosol_exposure_cooldown", 0) or 0)
        caution = f" Re-exposure can hit again after about {cooldown}t." if cooldown > 0 else " Stay out of it."
        self._log(f"{label.capitalize()} spreads through the smoke.{caution}", channel="combat", priority="high", dedupe_window=2)

    def on_aerosol_exposure_triggered(self, event):
        if event.data.get("target_eid") != self.player_eid:
            return
        label = str(event.data.get("aerosol_label", "") or "").strip() or str(event.data.get("status", "aerosol") or "aerosol").replace("_", " ")
        self._log(f"Hazard: {label} gets into your lungs and eyes.", channel="status", priority="high", dedupe_window=3)

    def on_weapon_fire_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        reason = event.data.get("reason")
        if reason == "cooldown":
            self._log(f"Weapon cooling down ({event.data.get('ready_in', 0)}t).", channel="combat", priority="high")
            return
        if reason == "no_loadout":
            self.sim.log.add("No weapon or attack setup is ready.")
            return
        if reason == "no_target":
            self.sim.log.add("No target in range.")
            return
        if reason == "no_weapon_equipped":
            self.sim.log.add("No weapon equipped.")
            return
        if reason == "no_ammo":
            self.sim.log.add("Click. Out of ammo.")
            return
        if reason == "out_of_range":
            self.sim.log.add("Target is beyond weapon range.")
            return
        if reason == "wrong_floor":
            self.sim.log.add("You cannot fire at a different floor from here.")
            return
        if reason == "no_direction":
            self.sim.log.add("Aim at a tile before firing.")
            return
        if reason == "downed":
            self.sim.log.add("You are too hurt to fire.")
            return
        weapon_name = str(event.data.get("weapon_name", "") or "").strip()
        if weapon_name:
            self._log(f"{weapon_name} will not fire.", channel="combat", priority="high")
            return
        self._log("Your weapon will not fire.", channel="combat", priority="high")

    def on_entity_damaged(self, event):
        target = event.data.get("target_eid")
        source = event.data.get("source_eid")
        if target != self.player_eid and source != self.player_eid:
            return

        damage = int(event.data.get("damage", 0))
        hp = int(event.data.get("hp", 0))
        max_hp = int(event.data.get("max_hp", 1))
        try:
            armor_absorb = float(event.data.get("armor_absorb", 0.0))
        except (TypeError, ValueError):
            armor_absorb = 0.0
        try:
            cover_absorb = float(event.data.get("cover_absorb", 0.0))
        except (TypeError, ValueError):
            cover_absorb = 0.0

        if target == self.player_eid:
            detail = []
            if cover_absorb > 0.0:
                detail.append(f"cover {int(round(cover_absorb * 100.0))}%")
            if armor_absorb > 0.0:
                detail.append(f"armor {int(round(armor_absorb * 100.0))}%")
            suffix = f", {' + '.join(detail)}" if detail else ""
            self._log(
                f"You take {damage} damage ({hp}/{max_hp} HP{suffix}).",
                channel="combat",
                priority="critical",
            )
            return

        if not self._player_can_perceive_entity(target):
            return

        target_name = self._npc_label(target)
        condition = _target_condition_descriptor(self.sim, self.player_eid, target, include_uncertainty=True)
        detail = []
        if cover_absorb > 0.0:
            detail.append(f"cover {int(round(cover_absorb * 100.0))}%")
        if armor_absorb > 0.0:
            detail.append(f"armor {int(round(armor_absorb * 100.0))}%")
        suffix = f" ({', '.join(detail)})" if detail else ""
        condition_suffix = f"; {condition}" if condition else ""
        self._log_npc_message(
            target,
            f"Hit {target_name} for {damage}{condition_suffix}{suffix}.",
            channel="combat",
            priority="high",
            dedupe_window=1,
        )

    def on_actor_deprivation_damage(self, event):
        if event.data.get("target_eid") != self.player_eid:
            return

        reason = str(event.data.get("reason", "") or "deprivation").strip().lower() or "deprivation"
        if reason == "dehydration":
            cause = "dehydration"
        elif reason == "starvation":
            cause = "starvation"
        elif reason == "deprivation":
            cause = "hunger and thirst"
        else:
            cause = reason.replace("_", " ")

        try:
            damage = int(event.data.get("damage", 0) or 0)
        except (TypeError, ValueError):
            damage = 0
        try:
            hp = int(event.data.get("hp", 0) or 0)
        except (TypeError, ValueError):
            hp = 0
        try:
            max_hp = max(1, int(event.data.get("max_hp", 1) or 1))
        except (TypeError, ValueError):
            max_hp = 1
        try:
            hunger = max(0.0, min(100.0, float(event.data.get("hunger", 0.0) or 0.0)))
        except (TypeError, ValueError):
            hunger = 0.0
        try:
            thirst = max(0.0, min(100.0, float(event.data.get("thirst", 0.0) or 0.0)))
        except (TypeError, ValueError):
            thirst = 0.0

        subject = cause[:1].upper() + cause[1:]
        verb = "are" if cause == "hunger and thirst" else "is"
        self._log(
            f"{subject} {verb} damaging you: -{damage} HP ({hp}/{max_hp} HP). Food {hunger:.0f}/100, water {thirst:.0f}/100.",
            channel="general",
            priority="critical",
            dedupe_window=4,
            dedupe_key=f"player_deprivation_damage:{reason}",
        )

    def on_player_downed(self, event):
        if event.data.get("target_eid") != self.player_eid:
            return
        bleedout_ticks = int(event.data.get("bleedout_ticks", 0) or 0)
        self._log(
            f"Downed. Bleeding out in {bleedout_ticks} ticks. Use medical aid if you can.",
            channel="combat",
            priority="critical",
        )

    def on_player_recovered_from_downed(self, event):
        if event.data.get("target_eid") != self.player_eid:
            return
        item_name = str(event.data.get("item_name", event.data.get("item_id", "medical aid"))).strip() or "medical aid"
        recovered = int(event.data.get("recovered_hp", 1) or 1)
        rescuer_eid = event.data.get("rescuer_eid")
        if rescuer_eid is not None and rescuer_eid != self.player_eid:
            rescuer_name = self._npc_label(rescuer_eid)
            self._log(
                f"{rescuer_name} uses {item_name} and gets you back up at {recovered} HP.",
                channel="combat",
                priority="critical",
            )
            return
        self._log(
            f"{item_name} gets you back up at {recovered} HP.",
            channel="combat",
            priority="critical",
        )

    def on_player_critical_saved(self, event):
        if event.data.get("target_eid") != self.player_eid:
            return
        item_name = str(event.data.get("item_name", event.data.get("item_id", "emergency device"))).strip() or "emergency device"
        recovered = int(event.data.get("recovered_hp", 1))
        self._log(
            f"{item_name} fires. Barely stable at {recovered} HP.",
            channel="combat",
            priority="critical",
        )

    def on_player_killed(self, event):
        if event.data.get("target_eid") != self.player_eid:
            return
        reason = str(event.data.get("reason", "") or "").strip().lower()
        source_name = str(event.data.get("source_name", "") or "").strip()
        if reason == "bled_out":
            self._log(
                "You bled out.",
                channel="combat",
                priority="critical",
            )
            return
        if reason == "executed_while_downed":
            text = f"Executed by {source_name} while downed." if source_name else "Executed while downed."
            self._log(
                text,
                channel="combat",
                priority="critical",
            )
            return
        if source_name:
            self._log(
                f"Killed by {source_name}.",
                channel="combat",
                priority="critical",
            )
            return
        self._log(
            "You are dead.",
            channel="combat",
            priority="critical",
        )

    def on_player_action_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        reason = str(event.data.get("reason", "") or "").strip().lower()
        if reason == "control_lapse":
            _log_player_feedback(
                self.sim,
                "You cannot make your body answer yet.",
                kind="status",
                dedupe_window=3,
                dedupe_key="player_action_blocked:control_lapse",
            )
            return
        if reason != "downed":
            return
        _log_player_feedback(
            self.sim,
            "You are downed. Use restorative medical aid.",
            kind="combat",
            dedupe_window=4,
            dedupe_key="player_action_blocked:downed",
        )

    def on_npc_downed(self, event):
        if event.data.get("source_eid") != self.player_eid:
            return
        target = event.data.get("target_eid")
        target_name = self._npc_label(target)
        self._log_npc_message(target, f"{target_name} is downed.", channel="combat", priority="high")

    def on_npc_medical_rescue_applied(self, event):
        target = event.data.get("target_eid")
        if target == self.player_eid:
            return
        rescuer = event.data.get("rescuer_eid")
        if not (
            self._player_can_perceive_entity(rescuer)
            or self._player_can_perceive_entity(target)
            or self._player_can_perceive_event_position(event)
        ):
            return
        rescuer_name = self._npc_label(rescuer)
        target_name = self._npc_label(target)
        item_name = str(event.data.get("item_name", event.data.get("item_id", "medical aid"))).strip() or "medical aid"
        recovered = int(event.data.get("recovered_hp", 1) or 1)
        try:
            player_is_rescuer = int(rescuer) == int(self.player_eid)
        except (TypeError, ValueError):
            player_is_rescuer = rescuer == self.player_eid
        if player_is_rescuer:
            self._log(
                f"You use {item_name} and get {target_name} back up at {recovered} HP.",
                channel="combat",
                priority="high",
                dedupe_window=2,
                dedupe_key=f"npc_medical_rescue:{rescuer}:{target}",
            )
            return
        self._log(
            f"{rescuer_name} uses {item_name} and gets {target_name} back up at {recovered} HP.",
            channel="combat",
            priority="high",
            dedupe_window=2,
            dedupe_key=f"npc_medical_rescue:{rescuer}:{target}",
        )

    def on_npc_killed(self, event):
        target = event.data.get("target_eid")
        source = event.data.get("source_eid")
        reason = str(event.data.get("reason", "dead")).strip().replace("_", " ")
        target_name = event.data.get("target_name") or self._npc_label(target)

        # Track for contract-kill opportunity completion.
        if target is not None:
            try:
                eid_int = int(target)
                traits = getattr(self.sim, "world_traits", None)
                if isinstance(traits, dict):
                    killed_list = traits.get("killed_npc_eids")
                    if not isinstance(killed_list, list):
                        killed_list = []
                        traits["killed_npc_eids"] = killed_list
                    if eid_int not in killed_list:
                        killed_list.append(eid_int)
            except (TypeError, ValueError):
                pass

        if source == self.player_eid:
            self._log_npc_message(
                target,
                f"{target_name} is dead ({reason}).",
                channel="combat",
                priority="critical",
            )
            dropped = event.data.get("dropped_items") or []
            if dropped:
                item_names = []
                for drop in dropped[:6]:
                    d_id = str(drop.get("item_id", "")).strip()
                    d_qty = int(drop.get("quantity", 1))
                    name = item_display_name(d_id)
                    if d_qty > 1:
                        item_names.append(f"{name} x{d_qty}")
                    else:
                        item_names.append(name)
                loot_text = ", ".join(item_names)
                self.sim.log.add(f"  Dropped: {loot_text}.")
            p2p_bonus = int(event.data.get("p2p_bonus", 0))
            if p2p_bonus > 0:
                self.sim.log.add(f"  P2P siphon: +{p2p_bonus}c in cracked credstick funds.")
            return

        if self._player_can_perceive_event_position(event):
            self._log_npc_message(
                target,
                f"{target_name} dies.",
                channel="combat",
                priority="high",
            )

    def on_explosion_triggered(self, event):
        if event.data.get("source_eid") != self.player_eid:
            return
        radius = event.data.get("radius", 0)
        hits = event.data.get("hits", 0)
        self._log(f"Explosion r={radius} affects {hits} targets.", channel="combat", priority="critical")

    def on_combat_overlay_entered(self, event):
        if event.data.get("player_eid") != self.player_eid:
            return
        threat_count = event.data.get("threat_count", 0)
        direct_count = event.data.get("direct_threat_count", threat_count)
        ambient_count = event.data.get("ambient_threat_count", 0)
        pursuit_count = event.data.get("pursuit_target_count", 0)
        nearest = event.data.get("nearest_threat_dist")
        player_cover = self.sim.ecs.get(CoverState).get(self.player_eid)
        exposure = int(float(player_cover.exposure if player_cover else 1.0) * 100)
        if ambient_count or pursuit_count:
            parts = []
            if direct_count:
                parts.append(f"{direct_count} direct")
            if ambient_count:
                parts.append(f"{ambient_count} nearby")
            if pursuit_count:
                parts.append(f"{pursuit_count} pursuit")
            threat_label = " + ".join(parts) if parts else f"{threat_count} threat"
        else:
            threat_label = f"{threat_count} threat"
        if nearest is None:
            self._log(
                f"Combat turn mode engaged ({threat_label}, exposure {exposure}%).",
                channel="combat",
                priority="critical",
            )
        else:
            self._log(
                f"Combat turn mode engaged ({threat_label}, nearest {nearest}, exposure {exposure}%).",
                channel="combat",
                priority="critical",
            )

    def on_combat_overlay_exited(self, event):
        if event.data.get("player_eid") != self.player_eid:
            return
        self._log("Combat turn mode cleared. Returning to free movement.", channel="combat", priority="high")

    def on_npc_suppressed(self, event):
        eid = event.data.get("eid")
        if not self._player_can_perceive_entity(eid):
            return
        level = event.data.get("level", "shaken")
        name = self._npc_label(eid)
        if level == "pinned":
            self._log_npc_message(
                eid,
                f"{name} ducks low, pinned down by fire.",
                channel="combat",
                priority="high",
                dedupe_window=4,
                dedupe_key=f"suppressed-{eid}",
            )
        else:
            self._log_npc_message(
                eid,
                f"{name} flinches as rounds crack nearby.",
                channel="combat",
                priority="normal",
                dedupe_window=4,
                dedupe_key=f"suppressed-{eid}",
            )

    def on_npc_surrendered(self, event):
        eid = event.data.get("eid")
        name = self._npc_label(eid)
        dropped = event.data.get("dropped_weapon")
        if self._player_can_perceive_entity(eid):
            weapon_name = ""
            if dropped:
                weapon = weapon_by_id(dropped)
                weapon_name = str(weapon.get("name", dropped)) if weapon else str(dropped)
            self._log_npc_message(
                eid,
                (
                    f"{name} fumbles {weapon_name} to the ground and throws up both hands. "
                    "\"Okay, okay, I'm done!\""
                    if weapon_name
                    else f"{name} throws up their hands. \"Okay, okay, I'm done!\""
                ),
                channel="combat",
                priority="critical",
            )
            if weapon_name:
                self.sim.log.add(f"  Dropped: {weapon_name}.")
        elif self._player_is_near_event_position(event, radius=8):
            self._log(
                "Someone nearby shouts a surrender.",
                channel="combat",
                priority="high",
                dedupe_window=3,
                dedupe_key="surrender-nearby",
            )

    def on_property_owner_changed(self, event):
        if event.data.get("new_owner_eid") != self.player_eid:
            return
        property_name = self._property_name(event.data.get("property_id"))
        self.sim.log.add(f"You now own {property_name}.")

    def on_property_purchased(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        prop = self._property_name(event.data.get("property_id"))
        price = event.data.get("price", 0)
        self.sim.log.add(f"Purchased {prop} for {price} credits.")

    def on_player_business_acquired(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        business_name = str(event.data.get("business_name", "Business")).strip() or "Business"
        staff_total = int(event.data.get("staff_total", 0))
        required_staff = int(event.data.get("required_staff", 1))
        self.sim.log.add(f"{business_name} now has a business account. Staff {staff_total}/{required_staff}.")

    def on_player_business_staff_hired(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        business_name = str(event.data.get("business_name", "Business")).strip() or "Business"
        npc_name = self._npc_label(event.data.get("npc_eid"))
        role = str(event.data.get("role", "staff") or "staff").strip().lower() or "staff"
        housing_kind = str(event.data.get("housing_kind", "") or "").strip().lower()
        housing_name = str(event.data.get("housing_name", "") or "").strip()
        if role == "manager":
            line = f"{npc_name} now manages {business_name}."
            if housing_kind == "workplace_lodging":
                line = line[:-1] + " They will stay on-site."
            elif housing_kind in {"nearby_housing", "nearby_lodging"} and housing_name:
                line = line[:-1] + f" They will stay at {housing_name}."
            self.sim.log.add(line)
            return
        line = f"{npc_name} is now on staff at {business_name}."
        if housing_kind == "workplace_lodging":
            line = line[:-1] + " They will stay on-site."
        elif housing_kind in {"nearby_housing", "nearby_lodging"} and housing_name:
            line = line[:-1] + f" They will stay at {housing_name}."
        self.sim.log.add(line)

    def on_player_business_staff_fired(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        business_name = str(event.data.get("business_name", "Business")).strip() or "Business"
        npc_name = self._npc_label(event.data.get("npc_eid"))
        self.sim.log.add(f"{npc_name} is no longer employed at {business_name}.")

    def on_player_business_staff_resigned(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        business_name = str(event.data.get("business_name", "Business")).strip() or "Business"
        npc_name = self._npc_label(event.data.get("npc_eid"))
        self.sim.log.add(f"{npc_name} resigns from {business_name}.")

    def on_property_purchase_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        reason = event.data.get("reason")
        property_name = self._event_property_name(event, fallback="That property")
        if reason == "no_property":
            self.sim.log.add("No property nearby to purchase.")
        elif reason == "already_owner":
            self.sim.log.add(f"You already own {property_name}.")
        elif reason == "not_for_sale":
            owner_tag = str(event.data.get("owner_tag", "") or "").strip().lower()
            if owner_tag and owner_tag not in {"", "city"}:
                self.sim.log.add(f"{property_name} is already held privately and is not on the market.")
            else:
                self.sim.log.add(f"{property_name} is not currently for sale.")
        elif reason == "insufficient_funds":
            price = event.data.get("price", 0)
            credits = event.data.get("credits", 0)
            self.sim.log.add(f"{property_name} costs {price} credits; you have {credits}.")
        elif reason == "active_dispute":
            self.sim.log.add(f"{property_name} will not close a sale while you are in an active property dispute there.")
        elif reason == "missing_assets":
            self.sim.log.add(f"Cannot purchase {property_name} because your wallet is not accessible right now.")
        else:
            self.sim.log.add(f"Purchase of {property_name} could not be finalized.")

    def on_trade_bought(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        item_name = event.data.get("item_name", event.data.get("item_id", "item"))
        price = int(event.data.get("price", 0))
        base_price = int(event.data.get("base_price", price))
        store = event.data.get("store_name", "store")
        contact_note = str(event.data.get("contact_note", "")).strip()
        if bool(event.data.get("owner_transfer")):
            _log_player_feedback(self.sim, f"You withdrew {item_name} from {store} stock.", kind="commerce")
            return
        if contact_note and price != base_price:
            _log_player_feedback(self.sim, f"You bought {item_name} for {price} cr at {store}. {contact_note}.", kind="commerce")
            return
        _log_player_feedback(self.sim, f"You bought {item_name} for {price} cr at {store}.", kind="commerce")

    def on_street_vendor_purchase(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        item_name = event.data.get("item_name", event.data.get("item_id", "item"))
        price = int(event.data.get("price", 0) or 0)
        npc_name = self._npc_label(event.data.get("npc_eid"), fallback="the street contact")
        risk = str(event.data.get("risk_label", "") or "").strip()
        suffix = f" {risk}." if risk else ""
        _log_player_feedback(self.sim, f"You bought {item_name} for {price} cr from {npc_name}.{suffix}", kind="commerce")

    def on_street_buy_transaction(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        item_name = self._event_item_label(event)
        payout = int(event.data.get("payout", event.data.get("price", 0)) or 0)
        npc_name = self._npc_label(event.data.get("npc_eid"), fallback="the street contact")
        _log_player_feedback(self.sim, f"You sold {item_name} for {payout} cr to {npc_name}.", kind="commerce")

    def on_npc_item_purchased(self, event):
        npc_eid = event.data.get("npc_eid", event.data.get("eid"))
        if npc_eid == self.player_eid:
            return
        visible = self._player_can_perceive_entity(npc_eid)
        near = self._player_is_near_event_position(event, radius=8)
        if not visible and not near:
            return
        item_name = self._event_item_label(event)
        store = self._event_property_name(event, fallback=str(event.data.get("store_name", "store") or "store"))
        impulse = bool(event.data.get("impulse"))
        wallet_after = int(event.data.get("wallet_after", 0) or 0)
        if visible:
            name = self._npc_label(npc_eid, fallback="Someone")
            if impulse and wallet_after <= 0:
                self._log(
                    f"{name} spends their last credits on {item_name} at {store}.",
                    channel="social",
                    priority="low",
                    dedupe_window=4,
                    dedupe_key=f"npc-shopping:{npc_eid}:{event.data.get('item_id')}:{event.data.get('property_id')}",
                )
            else:
                self._log(
                    f"{name} buys {item_name} at {store}.",
                    channel="social",
                    priority="low",
                    dedupe_window=4,
                    dedupe_key=f"npc-shopping:{npc_eid}:{event.data.get('item_id')}:{event.data.get('property_id')}",
                )
            return
        self._log(
            f"You hear a quick purchase at {store}.",
            channel="social",
            priority="low",
            dedupe_window=4,
            dedupe_key=f"npc-shopping-near:{event.data.get('property_id')}",
        )

    def on_trade_buy_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        reason = event.data.get("reason")
        store_name = self._event_property_name(event, fallback="That storefront")
        item_name = self._event_item_label(event)
        if reason == "no_store":
            _log_player_feedback(self.sim, "No storefront nearby to buy from.", kind="commerce")
            return
        if reason == "no_street_vendor":
            _log_player_feedback(self.sim, "That street contact is not close enough to buy from.", kind="commerce")
            return
        if reason == "street_vendor_empty":
            _log_player_feedback(self.sim, "That street contact has nothing to sell right now.", kind="commerce")
            return
        if reason == "no_assets":
            _log_player_feedback(self.sim, "Cannot buy right now: your wallet is not accessible.", kind="commerce")
            return
        if reason == "no_inventory":
            _log_player_feedback(self.sim, "Cannot buy right now: you have nowhere to carry the purchase.", kind="commerce")
            return
        if reason == "store_empty":
            _log_player_feedback(self.sim, f"{store_name} is out of stock.", kind="commerce")
            return
        if reason == "item_unavailable":
            _log_player_feedback(self.sim, f"{store_name} does not have {item_name} available right now.", kind="commerce")
            return
        if reason == "insufficient_funds":
            cheapest = int(event.data.get("cheapest_price", 0))
            credits = int(event.data.get("credits", 0))
            _log_player_feedback(self.sim, f"Cannot buy from {store_name}: you have {credits} cr and need {cheapest} cr.", kind="commerce")
            return
        if reason == "inventory_full":
            _log_player_feedback(self.sim, f"Cannot buy {item_name}: inventory is full.", kind="commerce")
            return
        _log_player_feedback(self.sim, f"Purchase of {item_name} at {store_name} could not be finalized.", kind="commerce")

    def on_trade_sold(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        item_name = event.data.get("item_name", event.data.get("item_id", "item"))
        price = int(event.data.get("price", 0))
        store = event.data.get("store_name", "store")
        contact_note = str(event.data.get("contact_note", "")).strip()
        if bool(event.data.get("owner_transfer")):
            _log_player_feedback(self.sim, f"You stocked {item_name} into {store}.", kind="commerce")
            return
        if contact_note:
            _log_player_feedback(self.sim, f"You sold {item_name} for {price} cr at {store}. {contact_note}.", kind="commerce")
            return
        _log_player_feedback(self.sim, f"You sold {item_name} for {price} cr at {store}.", kind="commerce")

    def on_trade_sell_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        reason = event.data.get("reason")
        store_name = self._event_property_name(event, fallback="That storefront")
        item_name = self._event_item_label(event)
        if reason == "no_store":
            _log_player_feedback(self.sim, "No storefront nearby to sell to.", kind="commerce")
            return
        if reason == "no_street_vendor":
            _log_player_feedback(self.sim, "That street contact is not close enough to sell to.", kind="commerce")
            return
        if reason == "no_assets":
            _log_player_feedback(self.sim, "Cannot sell right now: your wallet is not accessible.", kind="commerce")
            return
        if reason == "no_inventory":
            _log_player_feedback(self.sim, "Cannot sell right now: your carried inventory is not accessible.", kind="commerce")
            return
        if reason == "inventory_empty":
            _log_player_feedback(self.sim, "Nothing to sell.", kind="commerce")
            return
        if reason == "no_sellable_item":
            _log_player_feedback(self.sim, f"{store_name} has nothing to buy from what you're carrying.", kind="commerce")
            return
        if reason == "item_not_found":
            _log_player_feedback(self.sim, "That sale item is no longer available in your inventory.", kind="commerce")
            return
        if reason == "unwanted_item_warning":
            _log_player_feedback(self.sim, f"{store_name} does not usually buy {item_name}. The worker waves it off.", kind="commerce")
            return
        if reason == "unwanted_item_firm":
            _log_player_feedback(self.sim, f"{store_name} is not taking {item_name}. The worker tells you to stop putting it on the counter.", kind="commerce")
            return
        if reason == "unwanted_item_eject":
            _log_player_feedback(self.sim, f"{store_name} is done with that offer. The worker tells you to leave.", kind="commerce")
            return
        if reason == "vehicle_not_in_chunk":
            vehicle_name = str(event.data.get("vehicle_name", "vehicle") or "vehicle").strip()
            _log_player_feedback(self.sim, f"{vehicle_name} is not in this chunk, so nobody here will buy the key.", kind="commerce")
            return
        if reason == "vehicle_not_owned":
            _log_player_feedback(self.sim, "That key does not match a vehicle you own.", kind="commerce")
            return
        if reason == "vehicle_not_found":
            _log_player_feedback(self.sim, "That key no longer points to an available vehicle.", kind="commerce")
            return
        if reason == "invalid_vehicle_key":
            _log_player_feedback(self.sim, "That key is not tied to a vehicle record.", kind="commerce")
            return
        if reason == "missing_sale_state":
            _log_player_feedback(self.sim, f"Cannot price a sale at {store_name} right now.", kind="commerce")
            return
        if reason == "remove_failed":
            _log_player_feedback(self.sim, f"The sale of {item_name} stalled before it left your inventory.", kind="commerce")
            return
        _log_player_feedback(self.sim, f"Sale of {item_name} at {store_name} could not be finalized.", kind="commerce")

    def on_bank_transaction(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        kind = event.data.get("kind", "deposit")
        provider_name = self._event_place_name(event)
        place_note = f" at {provider_name}" if provider_name else ""
        account_kind = str(event.data.get("account_kind", "personal")).strip().lower() or "personal"
        amount = int(event.data.get("amount", 0))
        wallet = int(event.data.get("wallet_credits", 0))
        bank = int(event.data.get("bank_balance", 0))
        if account_kind == "business":
            business_name = str(event.data.get("business_name", "Business")).strip() or "Business"
            business_balance = int(event.data.get("business_balance", 0))
            if kind == "withdraw":
                self.sim.log.add(
                    f"Withdrew {amount} credits from {business_name}{place_note}. Wallet {wallet} | {business_name} {business_balance}."
                )
                return
            self.sim.log.add(
                f"Deposited {amount} credits into {business_name}{place_note}. Wallet {wallet} | {business_name} {business_balance}."
            )
            return
        if kind == "debt_payment":
            debt_balance = int(event.data.get("debt_balance", 0))
            self.sim.log.add(
                f"Paid {amount}c toward justice debt{place_note}. Wallet {wallet}c | Bank {bank}c | Debt {debt_balance}c."
            )
            return
        if kind == "withdraw":
            self.sim.log.add(f"Withdrew {amount} credits{place_note}. Wallet {wallet} | Bank {bank}.")
            return
        self.sim.log.add(f"Deposited {amount} credits{place_note}. Wallet {wallet} | Bank {bank}.")

    def on_banking_action_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        reason = event.data.get("reason")
        provider_name = self._event_place_name(event) or "the bank"
        if reason == "no_banking_service":
            self.sim.log.add("No bank or teller nearby.")
            return
        if reason == "no_business_account":
            self.sim.log.add(f"No owned business account is available through {provider_name}.")
            return
        if reason == "no_bank_balance":
            self.sim.log.add(f"Bank account at {provider_name} is empty.")
            return
        if reason == "missing_finance_profile":
            self.sim.log.add(f"{provider_name} cannot verify your account record right now.")
            return
        if reason == "no_debt_balance":
            self.sim.log.add("No justice debt is currently on the books.")
            return
        if reason == "insufficient_liquid_funds":
            available = int(event.data.get("available_liquid", 0))
            debt_balance = int(event.data.get("debt_balance", 0))
            self.sim.log.add(
                f"Cannot clear justice debt through {provider_name} ({available}c liquid on hand vs {debt_balance}c due)."
            )
            return
        if reason == "deposit_not_needed":
            self.sim.log.add(f"{provider_name} does not need a wallet-topoff deposit right now.")
            return
        if reason == "no_funds_to_manage":
            self.sim.log.add(f"No funds are available to move through {provider_name} right now.")
            return
        if reason == "insufficient_business_balance":
            amount = int(event.data.get("amount", 0))
            business_balance = int(event.data.get("business_balance", 0))
            business_name = str(event.data.get("business_name", "Business")).strip() or "Business"
            self.sim.log.add(
                f"{provider_name} cannot withdraw {amount}c from {business_name} ({business_balance}c available)."
            )
            return
        if reason == "insufficient_bank_balance":
            amount = int(event.data.get("amount", 0))
            bank_balance = int(event.data.get("bank_balance", 0))
            self.sim.log.add(f"{provider_name} cannot cover a withdrawal of {amount}c ({bank_balance}c in bank).")
            return
        if reason == "insufficient_wallet_funds":
            amount = int(event.data.get("amount", 0))
            credits = int(event.data.get("credits", 0))
            self.sim.log.add(f"{provider_name} cannot deposit {amount}c from your wallet ({credits}c on hand).")
            return
        if reason == "invalid_amount":
            kind = str(event.data.get("kind", "")).strip().lower()
            if kind == "pay_justice_debt":
                self.sim.log.add(f"Choose a non-zero justice-debt payment for {provider_name}.")
            else:
                self.sim.log.add(f"Choose a non-zero banking amount for {provider_name}.")
            return
        self.sim.log.add(f"{provider_name} cannot process that banking request right now.")

    def on_insurance_policy_purchased(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        policy_name = event.data.get("policy_name", "policy")
        provider_name = self._event_place_name(event)
        provider_note = f" from {provider_name}" if provider_name else ""
        premium = int(event.data.get("premium", 0))
        base_premium = int(event.data.get("base_premium", premium))
        channel = event.data.get("channel", "insurance")
        expires_tick = int(event.data.get("expires_tick", 0))
        duration_ticks = int(event.data.get("duration_ticks", max(0, expires_tick - int(self.sim.tick))))
        duration_text = _tick_duration_label(self.sim, duration_ticks)
        contact_note = str(event.data.get("contact_note", "")).strip()
        if contact_note and premium != base_premium:
            self.sim.log.add(
                f"Purchased {policy_name}{provider_note} via {channel} (-{premium} credits, covers {duration_text}, expires t{expires_tick}). {contact_note}."
            )
            return
        self.sim.log.add(
            f"Purchased {policy_name}{provider_note} via {channel} (-{premium} credits, covers {duration_text}, expires t{expires_tick})."
        )

    def on_insurance_action_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        reason = event.data.get("reason")
        provider_name = self._event_place_name(event) or "the insurer"
        if reason == "no_insurance_service":
            self.sim.log.add("No insurer nearby.")
            return
        if reason == "insufficient_funds":
            premium = int(event.data.get("premium", 0))
            credits = int(event.data.get("credits", 0))
            policy_name = event.data.get("policy_name", "policy")
            self.sim.log.add(f"{provider_name} wants {premium} credits for {policy_name} ({credits} available).")
            return
        if reason == "provider_no_products":
            self.sim.log.add(f"{provider_name} has no policies on the board right now.")
            return
        if reason == "no_offer":
            self.sim.log.add(f"{provider_name} has nothing to underwrite for you right now.")
            return
        if reason == "missing_finance_profile":
            self.sim.log.add(f"{provider_name} cannot verify your customer record right now.")
            return
        self.sim.log.add(f"{provider_name} cannot issue or update coverage right now.")

    def on_insurance_policy_expired(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        policy_name = event.data.get("policy_name", event.data.get("policy_key", "policy"))
        self.sim.log.add(f"{policy_name} expired.")

    def on_insurance_claim_paid(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        policy_name = event.data.get("policy_name", "policy")
        payout = int(event.data.get("payout", 0))
        penalty = int(event.data.get("penalty", 0))
        self.sim.log.add(f"{policy_name} paid {payout} credits on {penalty} loss.")

    def on_insurance_claim_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        policy_name = event.data.get("policy_name", "policy")
        reason = event.data.get("reason", "blocked")
        if reason == "policy_depleted":
            self.sim.log.add(f"{policy_name} is depleted and cannot pay out anymore.")
            return
        if reason == "claim_zero":
            self.sim.log.add(f"{policy_name} does not pay out on a loss this small.")
            return
        self.sim.log.add(f"{policy_name} will not pay that claim right now.")

    def on_insurance_item_saved(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        policy_name = event.data.get("policy_name", "item policy")
        left = int(event.data.get("charges_left", 0))
        self.sim.log.add(f"{policy_name} saved your gear ({left} charges left).")

    def on_insurance_medical_boost(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        bonus = int(event.data.get("hp_bonus", 0))
        hp = int(event.data.get("hp", 0))
        max_hp = int(event.data.get("max_hp", 1))
        self.sim.log.add(f"Medical policy restores +{bonus} HP ({hp}/{max_hp}).")

    def on_downed_item_lost(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        item_name = event.data.get("item_name", event.data.get("item_id", "item"))
        self.sim.log.add(f"While downed, you dropped {item_name}.")

    def on_quit_requested(self, _event):
        self.sim.log.add("Exit requested.")

    def on_zoom_mode_changed(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        mode = str(event.data.get("mode", "city")).lower()
        chunk = event.data.get("chunk")
        if mode == "overworld":
            if bool(event.data.get("view_only")):
                self.sim.log.add(f"Opened the view-only overworld map at chunk {chunk}.")
                return
            ramp_name = str(event.data.get("ramp_name", "") or "").strip()
            if ramp_name:
                self.sim.log.add(f"Entered quick travel from {ramp_name} at chunk {chunk}.")
                return
            self.sim.log.add(f"Entered quick travel at chunk {chunk}.")
            return
        area = str(event.data.get("area_type", "local")).strip().lower() or "local"
        self.sim.log.add(f"Entered local view at chunk {chunk} ({area}).")

    def on_zoom_mode_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        reason = event.data.get("reason")
        if reason == "vehicle_required":
            self.sim.log.add("You need to be inside a vehicle to open the overworld map.")
            return
        if reason == "overworld_action_restricted":
            action = str(event.data.get("action", "action")).replace("_", " ")
            self.sim.log.add(f"{action.title()} only works on foot.")
            return
        mode = str(event.data.get("mode", "map") or "map").strip().lower()
        if mode == "overworld":
            self.sim.log.add("Cannot switch to the overworld map right now.")
            return
        if mode == "city":
            self.sim.log.add("Cannot switch back to the city map right now.")
            return
        self.sim.log.add("Cannot change map view right now.")

    def on_vehicle_entered(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
        fuel = _int_or_default(event.data.get("fuel"), 0)
        fuel_capacity = max(1, _int_or_default(event.data.get("fuel_capacity"), 1))
        entry_method = str(event.data.get("entry_method", "")).strip().lower()
        if entry_method == "hotwire":
            self.sim.log.add(f"Hotwired {name}. Fuel {fuel}/{fuel_capacity}.")
            return
        if entry_method == "ignition_override":
            self.sim.log.add(f"Bypassed the ignition on {name}. Fuel {fuel}/{fuel_capacity}.")
            return
        self.sim.log.add(f"Entered {name}. Fuel {fuel}/{fuel_capacity}.")

    def on_vehicle_exited(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
        fuel = _int_or_default(event.data.get("fuel"), 0)
        fuel_capacity = max(1, _int_or_default(event.data.get("fuel_capacity"), 1))
        self.sim.log.add(f"Exited {name}. Fuel {fuel}/{fuel_capacity}.")
        if fuel <= 0:
            self.sim.log.add(self._service_recovery_hint("fuel", on_foot=True))

    def on_vehicle_onramp_nearby(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        ramp_id = str(event.data.get("ramp_property_id", "") or "").strip()
        distance = _int_or_default(event.data.get("distance"), 0)
        distance_text = "here" if distance <= 0 else f"{distance}t away"
        _log_player_feedback(
            self.sim,
            f"There is an onramp nearby ({distance_text}). Interact to enter quick travel.",
            kind="movement",
            dedupe_window=8,
            dedupe_key=f"vehicle-onramp-nearby:{ramp_id or 'unknown'}",
        )

    def on_vehicle_action_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        reason = str(event.data.get("reason", "blocked")).strip().lower()
        if reason == "vehicle_required":
            self.sim.log.add("You need a usable vehicle for overworld travel.")
            return
        if reason == "route_required":
            self.sim.log.add("That ramp is not on a usable route.")
            return
        if reason == "quick_travel_ramp_required":
            self.sim.log.add("Interact near an entrance ramp to start quick travel.")
            return
        if reason == "water_route_required":
            self.sim.log.add("You need a usable shore, dock, or waterway access point for that boat route.")
            return
        if reason == "water_access_required":
            self.sim.log.add("That boat needs usable water before you can board it.")
            return
        if reason == "shore_exit_required":
            self.sim.log.add("Bring the boat alongside a shore or dock before getting out.")
            return
        if reason == "water_map_unavailable":
            self.sim.log.add("Boats stay in local water for now.")
            return
        if reason == "property_tile":
            self.sim.log.add("The vehicle cannot drive through property grounds or building tiles.")
            return
        if reason == "chunk_unready":
            self.sim.log.add("The route ahead is still coming into view.")
            return
        if reason == "vehicle_broken":
            name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
            self.sim.log.add(f"{name} is broken and will not move.")
            return
        if reason in {"blocked_tile", "closed_door", "locked_door", "locked_property", "closed_property", "door_access_denied", "active_fire"}:
            self.sim.log.add("The vehicle cannot pass that way.")
            return
        if reason.startswith("blocked_entity"):
            self.sim.log.add("Something is blocking the vehicle.")
            return
        if reason == "no_vehicle_state":
            self.sim.log.add("You are not linked to a usable vehicle right now.")
            return
        if reason == "invalid_vehicle":
            self.sim.log.add("That vehicle is no longer available to use.")
            return
        if reason == "missing_key":
            name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
            self.sim.log.add(f"You own {name}, but you don't have its key on hand.")
            return
        if reason == "key_required":
            name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
            self.sim.log.add(f"{name} is locked and not yours. You'll need a key, a lockpick kit, or exceptional intrusion skill.")
            return
        if reason == "hotwire_failed":
            name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
            self.sim.log.add(f"{name} stays dead. You fail to bypass the lock.")
            return
        if reason == "hotwire_fumble":
            name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
            self.sim.log.add(f"You fumble the hotwire attempt on {name}; the ignition stays dead.")
            return
        if reason == "out_of_fuel":
            name = str(event.data.get("vehicle_name", "vehicle")).strip() or "vehicle"
            fuel = _int_or_default(event.data.get("fuel"), 0)
            fuel_capacity = max(1, _int_or_default(event.data.get("fuel_capacity"), 1))
            fuel_needed = max(1, _int_or_default(event.data.get("fuel_needed"), 1))
            self.sim.log.add(
                f"Out of fuel: {name} has {fuel}/{fuel_capacity}, needs {fuel_needed} for that leg."
            )
            self.sim.log.add(self._service_recovery_hint("fuel", on_foot=False))
            return
        name = str(event.data.get("vehicle_name", "") or "").strip()
        if name:
            self.sim.log.add(f"{name} does not respond to your controls right now.")
            return
        self.sim.log.add("No vehicle responds to your controls right now.")

    def on_vehicle_collision(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        target_name = str(event.data.get("target_name", "") or "").strip() or "someone"
        damage = _int_or_default(event.data.get("damage"), 0)
        durability_lost = _int_or_default(event.data.get("durability_lost"), 0)
        condition = ""
        if durability_lost > 0:
            condition = f" Condition {int(event.data.get('durability_after', 0) or 0)}/10."
        if damage > 0:
            self.sim.log.add(f"The vehicle hits {target_name} and stops.{condition}")
            return
        self.sim.log.add(f"The vehicle hits something hard and stops.{condition}")

    def on_vehicle_crash(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        impact_kind = str(event.data.get("impact_kind", "blocked") or "blocked").replace("_", " ")
        durability_after = _int_or_default(event.data.get("durability_after"), 0)
        driver_damage = _int_or_default(event.data.get("driver_damage"), 0)
        hurt_text = f" You are jolted for {driver_damage} harm." if driver_damage > 0 else ""
        broken_text = " It will not move until repaired." if bool(event.data.get("vehicle_broken", False)) else ""
        self.sim.log.add(f"The vehicle crashes into {impact_kind} and stops. Condition {durability_after}/10.{broken_text}{hurt_text}")

    def on_overworld_travelled(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        to_chunk = event.data.get("to_chunk")
        area_type = event.data.get("area_type", "city")
        district_type = event.data.get("district_type", "unknown")
        terrain_raw = event.data.get("terrain")
        path_raw = event.data.get("path")
        landmark_raw = event.data.get("landmark")
        region_raw = event.data.get("region_name")
        settlement_raw = event.data.get("settlement_name")
        interest_raw = event.data.get("interest")
        identity_raw = event.data.get("identity")
        identity_hook_raw = event.data.get("identity_hook")
        risk_raw = event.data.get("risk")
        support_raw = event.data.get("support")
        energy_cost_raw = event.data.get("energy_cost", 0)
        safety_cost_raw = event.data.get("safety_cost", 0)
        social_cost_raw = event.data.get("social_cost", 0)
        fuel_cost_raw = event.data.get("fuel_cost", 0)
        fuel_left_raw = event.data.get("fuel_left", 0)
        fuel_capacity_raw = event.data.get("fuel_capacity", 0)
        vehicle_name = str(event.data.get("vehicle_name", "")).strip()
        terrain = str(terrain_raw).replace("_", " ").strip() if terrain_raw not in (None, "") else ""
        path = str(path_raw).strip() if path_raw not in (None, "") else ""
        landmark = str(landmark_raw).strip() if landmark_raw not in (None, "") else ""
        region_name = str(region_raw).strip() if region_raw not in (None, "") else ""
        settlement_name = str(settlement_raw).strip() if settlement_raw not in (None, "") else ""
        interest = str(interest_raw).strip() if interest_raw not in (None, "") else ""
        identity = str(identity_raw).strip() if identity_raw not in (None, "") else ""
        identity_hook = str(identity_hook_raw).strip() if identity_hook_raw not in (None, "") else ""
        risk = str(risk_raw).strip() if risk_raw not in (None, "") else ""
        support = str(support_raw).strip() if support_raw not in (None, "") else ""
        cost_bits = []
        try:
            energy_cost = int(energy_cost_raw)
        except (TypeError, ValueError):
            energy_cost = 0
        try:
            safety_cost = int(safety_cost_raw)
        except (TypeError, ValueError):
            safety_cost = 0
        try:
            social_cost = int(social_cost_raw)
        except (TypeError, ValueError):
            social_cost = 0
        try:
            fuel_cost = int(fuel_cost_raw)
        except (TypeError, ValueError):
            fuel_cost = 0
        try:
            fuel_left = int(fuel_left_raw)
        except (TypeError, ValueError):
            fuel_left = 0
        try:
            fuel_capacity = int(fuel_capacity_raw)
        except (TypeError, ValueError):
            fuel_capacity = 0
        if energy_cost > 0:
            cost_bits.append(f"E{energy_cost}")
        if safety_cost > 0:
            cost_bits.append(f"S{safety_cost}")
        if social_cost > 0:
            cost_bits.append(f"So{social_cost}")
        if fuel_cost > 0:
            cost_bits.append(f"F{fuel_cost}")
        extras = []
        if vehicle_name:
            extras.append(f"veh:{vehicle_name}")
        if terrain:
            extras.append(f"terrain:{terrain}")
        if path:
            extras.append(f"path:{path}")
        if landmark:
            extras.append(f"landmark:{landmark}")
        if identity:
            extras.append(f"id:{identity}")
        if interest:
            extras.append(f"poi:{interest}")
        if risk:
            extras.append(f"risk:{risk}")
        if support:
            extras.append(f"support:{support}")
        if identity_hook:
            extras.append(f"read:{identity_hook}")
        if cost_bits:
            extras.append(f"tax:{'/'.join(cost_bits)}")
        if fuel_capacity > 0:
            extras.append(f"fuel:{fuel_left}/{fuel_capacity}")
        if region_name:
            extras.append(f"region:{region_name}")
        if settlement_name:
            extras.append(f"city:{settlement_name}")
        suffix = f" {' '.join(extras)}" if extras else ""
        self.sim.log.add(f"Travelled to {to_chunk} ({area_type}/{district_type}).{suffix}")

    def on_overworld_discovery_found(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        chunk = event.data.get("chunk")
        label = str(event.data.get("label", "discovery")).strip() or "discovery"
        kind = str(event.data.get("kind", "")).strip().lower()
        credits_gain = int(event.data.get("credits_gain", 0))
        energy_gain = int(event.data.get("energy_gain", 0))
        safety_gain = int(event.data.get("safety_gain", 0))
        social_gain = int(event.data.get("social_gain", 0))
        item_name = str(event.data.get("item_name", "")).strip()
        bits = []
        if credits_gain > 0:
            bits.append(f"+{credits_gain}c")
        if energy_gain > 0:
            bits.append(f"E +{energy_gain}")
        if safety_gain > 0:
            bits.append(f"S +{safety_gain}")
        if social_gain > 0:
            bits.append(f"So +{social_gain}")
        if item_name:
            bits.append(item_name)
        suffix = f" ({', '.join(bits)})" if bits else ""
        if kind == "landmark":
            self.sim.log.add(f"Discovery @ {chunk}: vantage gained{suffix}.")
        else:
            self.sim.log.add(f"Discovery @ {chunk}: {label}{suffix}.")

        for raw in list(event.data.get("intel_lines") or [])[:3]:
            if isinstance(raw, dict) and raw.get("segments"):
                self.sim.log.add_rich(raw)
                continue
            text = str(raw).strip()
            if text:
                self.sim.log.add(f"  {text}")

    def on_overworld_marker_added(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        marker_id = int(event.data.get("marker_id", 0))
        chunk = event.data.get("chunk")
        marker_label = str(event.data.get("marker_label", "") or "").strip()
        terrain = str(event.data.get("terrain", "plain")).strip()
        landmark = str(event.data.get("landmark", "")).strip()
        region_name = str(event.data.get("region_name", "")).strip()
        settlement_name = str(event.data.get("settlement_name", "")).strip()
        interest = str(event.data.get("interest", "")).strip()
        identity = str(event.data.get("identity", "")).strip()
        identity_hook = str(event.data.get("identity_hook", "")).strip()
        risk = str(event.data.get("risk", "")).strip()
        support = str(event.data.get("support", "")).strip()
        discovery = str(event.data.get("discovery", "")).strip()
        cost_bits = []
        for label, key in (("E", "energy_cost"), ("S", "safety_cost"), ("So", "social_cost")):
            try:
                value = int(event.data.get(key, 0))
            except (TypeError, ValueError):
                value = 0
            if value > 0:
                cost_bits.append(f"{label}{value}")
        extras = [f"terrain:{terrain}"] if terrain else []
        if landmark:
            extras.append(f"landmark:{landmark}")
        if identity:
            extras.append(f"id:{identity}")
        if interest:
            extras.append(f"poi:{interest}")
        if risk:
            extras.append(f"risk:{risk}")
        if support:
            extras.append(f"support:{support}")
        if identity_hook:
            extras.append(f"read:{identity_hook}")
        if cost_bits:
            extras.append(f"tax:{'/'.join(cost_bits)}")
        if discovery:
            extras.append(f"opp:{discovery}")
        if region_name:
            extras.append(f"region:{region_name}")
        if settlement_name:
            extras.append(f"city:{settlement_name}")
        suffix = f" {' '.join(extras)}" if extras else ""
        if marker_label:
            self.sim.log.add(f"Marker M{marker_id} set for {marker_label} at {chunk}.{suffix}")
            return
        self.sim.log.add(f"Marker M{marker_id} set at {chunk}.{suffix}")

    def on_overworld_marker_updated(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        marker_id = int(event.data.get("marker_id", 0))
        chunk = event.data.get("chunk")
        marker_label = str(event.data.get("marker_label", "") or "").strip()
        retargeted = bool(event.data.get("retargeted", False))
        old_chunk = event.data.get("old_chunk")
        interest = str(event.data.get("interest", "")).strip()
        identity = str(event.data.get("identity", "")).strip()
        identity_hook = str(event.data.get("identity_hook", "")).strip()
        risk = str(event.data.get("risk", "")).strip()
        support = str(event.data.get("support", "")).strip()
        discovery = str(event.data.get("discovery", "")).strip()
        extras = []
        if identity:
            extras.append(f"id:{identity}")
        if interest:
            extras.append(f"poi:{interest}")
        if risk:
            extras.append(f"risk:{risk}")
        if support:
            extras.append(f"support:{support}")
        if identity_hook:
            extras.append(f"read:{identity_hook}")
        if discovery:
            extras.append(f"opp:{discovery}")
        if retargeted:
            label_text = f" for {marker_label}" if marker_label else ""
            origin_text = f" from {old_chunk}" if old_chunk else ""
            if extras:
                self.sim.log.add(f"Marker M{marker_id} retargeted{label_text} to {chunk}{origin_text} ({' '.join(extras)}).")
                return
            self.sim.log.add(f"Marker M{marker_id} retargeted{label_text} to {chunk}{origin_text}.")
            return
        if extras:
            if marker_label:
                self.sim.log.add(f"Marker M{marker_id} already tracks {marker_label} at {chunk} ({' '.join(extras)}).")
                return
            self.sim.log.add(f"Marker M{marker_id} already exists at {chunk} ({' '.join(extras)}).")
            return
        if marker_label:
            self.sim.log.add(f"Marker M{marker_id} already tracks {marker_label} at {chunk}.")
            return
        self.sim.log.add(f"Marker M{marker_id} already exists at {chunk}.")

    def on_overworld_marker_none(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        self.sim.log.add("No overworld markers. Press M to set one.")

    def on_overworld_marker_report(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        title = str(event.data.get("title", "Markers")).strip() or "Markers"
        lines = event.data.get("lines") or []
        if not lines:
            self.sim.log.add(f"{title}: none.")
            return

        self.sim.log.add(f"{title}: {lines[0]}")
        for raw in lines[1:5]:
            text = str(raw).strip()
            if text:
                self.sim.log.add(f"  {text}")

        remaining = int(event.data.get("remaining", 0))
        if remaining > 0:
            self.sim.log.add(f"  ... and {remaining} more.")

    def on_opportunity_completed(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        opp_id = int(event.data.get("opportunity_id", 0))
        title = str(event.data.get("title", "Opportunity")).strip() or "Opportunity"
        summary = str(event.data.get("summary", "")).strip()
        chunk = event.data.get("chunk", (0, 0))
        reward_text = str(event.data.get("reward_text", "")).strip()
        source = str(event.data.get("source", "unknown")).strip()
        completion_reason = str(event.data.get("completion_reason", "")).strip()
        active_remaining = int(event.data.get("active_remaining", 0))
        source_key = source.lower()
        is_discovery_style = (
            source_key in {"overworld_tag", "property_service", "economy_profile"}
            and completion_reason.startswith("entered target chunk")
        )
        completion_text = self._opportunity_completion_text(completion_reason)
        label = f"O{opp_id} {title}" if opp_id > 0 else title
        location = f" @ {chunk}" if isinstance(chunk, (list, tuple)) and len(chunk) == 2 else ""
        headline = "Lead confirmed" if is_discovery_style else "Opportunity complete"
        if completion_text:
            headline_text = f"{headline}: {label}{location} after {completion_text}."
        else:
            headline_text = f"{headline}: {label}{location}."

        self._log(
            headline_text,
            channel="opportunity",
            priority="high",
        )

        if summary:
            self.sim.log.add(f"  {summary}")

        source_text = opportunity_source_label(source, short=False)
        details = [f"Source {source_text}"]
        if reward_text:
            details.append(f"Reward {reward_text}")
        details.append(f"{active_remaining} active remain")
        details.append("Press O for report")
        self.sim.log.add("  " + " | ".join(details) + ".")

    def on_opportunity_failed(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        opp_id = int(event.data.get("opportunity_id", 0))
        title = str(event.data.get("title", "Opportunity")).strip() or "Opportunity"
        summary = str(event.data.get("summary", "")).strip()
        chunk = event.data.get("chunk", (0, 0))
        source = str(event.data.get("source", "unknown")).strip()
        failure_reason = str(event.data.get("failure_reason", "")).strip() or "the lead collapsed"
        active_remaining = int(event.data.get("active_remaining", 0))
        label = f"O{opp_id} {title}" if opp_id > 0 else title
        location = f" @ {chunk}" if isinstance(chunk, (list, tuple)) and len(chunk) == 2 else ""

        self._log(
            f"Opportunity failed: {label}{location} after {failure_reason}.",
            channel="opportunity",
            priority="high",
        )

        if summary:
            self.sim.log.add(f"  {summary}")

        source_text = opportunity_source_label(source, short=False)
        details = [f"Source {source_text}", f"{active_remaining} active remain", "Press O for report"]
        self.sim.log.add("  " + " | ".join(details) + ".")

    def on_opportunity_added(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        count = max(0, int(event.data.get("count", 0)))
        lines = list(event.data.get("lines", ()) or ())
        if count <= 0:
            return
        if count == 1:
            self._log("New opportunity posted.", channel="opportunity", priority="high")
        else:
            self._log(f"{count} new opportunities posted.", channel="opportunity", priority="high")
        for raw in lines[:3]:
            text = str(raw).strip()
            if text:
                self.sim.log.add(f"  {text}")
        remaining = max(0, int(event.data.get("remaining", 0)))
        if remaining > 0:
            self.sim.log.add(f"  ... and {remaining} more. Press O for report.")
            return
        self.sim.log.add("  Press O for report.")

    def on_opportunity_report(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        title = str(event.data.get("title", "Opportunities")).strip() or "Opportunities"
        summary = str(event.data.get("summary", "")).strip()
        lines = list(event.data.get("lines", ()) or ())
        if summary:
            self.sim.log.add(summary + ".")
        if not lines:
            self.sim.log.add(f"{title}: none.")
            return

        self.sim.log.add(f"{title}: {lines[0]}")
        for raw in lines[1:5]:
            text = str(raw).strip()
            if text:
                self.sim.log.add(f"  {text}")

        remaining = int(event.data.get("remaining", 0))
        if remaining > 0:
            self.sim.log.add(f"  ... and {remaining} more.")

    def on_rival_operator_seeded(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        count = max(0, int(event.data.get("count", 0)))
        if count <= 0:
            return
        if count == 1:
            self._log("Street word: another operator is working this run.", channel="opportunity", priority="high", dedupe_window=40)
            return
        self._log(
            f"Street word: {count} rival operators are working this run.",
            channel="opportunity",
            priority="high",
            dedupe_window=40,
        )

    def on_rival_operator_spotted(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        rival_name = str(event.data.get("rival_name", "someone")).strip() or "someone"
        summary = str(event.data.get("summary", "")).strip()
        self._log(
            f"You spot {rival_name} {summary}.".strip(),
            channel="opportunity",
            priority="high",
            dedupe_window=18,
            dedupe_key=f"rival-spotted:{event.data.get('rival_id')}:{summary.lower()}",
        )
        self._note_rival_target_property(event, confidence_floor=0.9)

    def _note_rival_target_property(self, event, *, confidence_floor=0.72):
        if event.data.get("eid") != self.player_eid:
            return False
        if event.data.get("truthful") is False:
            return False
        property_id = str(event.data.get("property_id", "") or "").strip()
        if not property_id or not hasattr(self.sim, "properties"):
            return False
        prop = self.sim.properties.get(property_id)
        if not isinstance(prop, dict):
            return False
        knowledge = self.sim.ecs.get(PropertyKnowledge).get(self.player_eid)
        existing = knowledge.known.get(property_id) if knowledge else None
        changed = _remember_property_lead_for_actor(
            self.sim,
            self.player_eid,
            prop,
            source_eid=None,
            lead_kind="location",
            confidence=max(float(confidence_floor), float(event.data.get("confidence", 0.0) or 0.0)),
        )
        if changed and existing is None:
            property_name = str(prop.get("name", prop.get("id", "that place"))).strip() or "that place"
            self.sim.log.add(f"  Lead noted: {property_name} added to notebook.")
        return bool(changed)

    def on_rival_operator_activity(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        confidence = float(event.data.get("confidence", 0.0) or 0.0)
        player_distance = max(0, int(event.data.get("player_distance", 99) or 99))
        known_to_player = bool(event.data.get("known_to_player"))
        if not known_to_player and player_distance > 4 and confidence < 0.6:
            return
        rival_name = str(event.data.get("rival_name", "someone")).strip() or "someone"
        summary = str(event.data.get("summary", "")).strip()
        if not summary:
            return
        confidence_pct = max(0, min(100, int(round(confidence * 100.0))))
        self._log(
            f"Street rumor: {summary} ({confidence_pct}% confidence).",
            channel="opportunity",
            priority="normal",
            dedupe_window=18,
            dedupe_key=f"rival-rumor:{event.data.get('rival_id')}:{summary.lower()}",
        )
        if player_distance <= 2 and confidence >= 0.58:
            self.sim.log.add(f"  {rival_name} sounds close enough to matter.")
        self._note_rival_target_property(event, confidence_floor=0.74)

    def on_rival_opportunity_resolved(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        confidence = float(event.data.get("confidence", 0.0) or 0.0)
        known_to_player = bool(event.data.get("known_to_player"))
        player_distance = max(0, int(event.data.get("player_distance", 99) or 99))
        if not known_to_player and player_distance > 5 and confidence < 0.58:
            return

        rival_name = str(event.data.get("rival_name", "someone")).strip() or "someone"
        title = str(event.data.get("title", "Opportunity")).strip() or "Opportunity"
        chunk = event.data.get("chunk", (0, 0))
        resolution = str(event.data.get("resolution", "claimed")).strip().lower() or "claimed"
        confidence_pct = max(0, min(100, int(round(confidence * 100.0))))
        reward_text = str(event.data.get("reward_text", "")).strip()
        casualty = str(event.data.get("casualty", "")).strip().lower()
        followup_title = str(event.data.get("followup_title", "")).strip()
        opp_id = int(event.data.get("opportunity_id", 0) or 0)
        opp_label = f"O{opp_id} {title}" if known_to_player and opp_id > 0 else title

        if resolution == "burned":
            headline = f"Rival fallout: {rival_name} may have burned {opp_label} @ {chunk}."
        else:
            headline = f"Rival move: {rival_name} may have gotten to {opp_label} first @ {chunk}."
        self._log(
            f"{headline} ({confidence_pct}% confidence)",
            channel="opportunity",
            priority="high" if known_to_player else "normal",
            dedupe_window=30,
            dedupe_key=f"rival-resolve:{opp_id}:{resolution}",
        )
        if reward_text and resolution == "claimed":
            self.sim.log.add(f"  Street read: {rival_name} probably walked away with {reward_text}.")
        if casualty == "dead":
            self.sim.log.add(f"  Street read: {rival_name} may not have made it out clean.")
        elif casualty == "wounded":
            self.sim.log.add(f"  Street read: {rival_name} may have been hurt on the job.")
        if followup_title:
            self.sim.log.add(f"  New lead posted: {followup_title}. Press O for report.")

    def on_rival_followup_seeded(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        title = str(event.data.get("followup_title", "Opportunity")).strip() or "Opportunity"
        rival_name = str(event.data.get("rival_name", "someone")).strip() or "someone"
        casualty = str(event.data.get("casualty", "")).strip().lower()
        if casualty == "dead":
            self._log(
                f"Fresh fallout: {title} opened after {rival_name}'s last job.",
                channel="opportunity",
                priority="high",
                dedupe_window=30,
                dedupe_key=f"rival-followup:{event.data.get('followup_id')}",
            )
            return
        self._log(
            f"Fresh fallout: {title} opened in {rival_name}'s wake.",
            channel="opportunity",
            priority="high",
            dedupe_window=30,
            dedupe_key=f"rival-followup:{event.data.get('followup_id')}",
        )

    def on_rival_operator_wounded(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        rival_name = str(event.data.get("rival_name", "someone")).strip() or "someone"
        self._log(
            f"Street word: {rival_name} got chewed up on a job and is laying low.",
            channel="opportunity",
            priority="normal",
            dedupe_window=40,
            dedupe_key=f"rival-wounded:{event.data.get('rival_id')}",
        )

    def on_rival_operator_removed(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        rival_name = str(event.data.get("rival_name", "someone")).strip() or "someone"
        by_player = bool(event.data.get("by_player"))
        reason = str(event.data.get("reason", "killed")).strip().replace("_", " ") or "killed"
        if by_player:
            self._log(
                f"{rival_name} is out of the run.",
                channel="opportunity",
                priority="high",
                dedupe_window=40,
                dedupe_key=f"rival-removed:{event.data.get('rival_id')}",
            )
            return
        if reason in {"job went bad", "contract backfire", "ambushed offscreen"}:
            self._log(
                f"Street word: {rival_name} died offscreen ({reason}).",
                channel="opportunity",
                priority="normal",
                dedupe_window=40,
                dedupe_key=f"rival-removed:{event.data.get('rival_id')}",
            )
            return
        self._log(
            f"Street word: {rival_name} dropped out of the run ({reason}).",
            channel="opportunity",
            priority="normal",
            dedupe_window=40,
            dedupe_key=f"rival-removed:{event.data.get('rival_id')}",
        )

    def on_objective_progress_awarded(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        channel = self._objective_progress_channel_label(event.data.get("channel", "action"))
        delta = dict(event.data.get("delta", {}) or {})
        objective_id = str(event.data.get("objective_id", "")).strip().lower()
        bits = objective_progress_explain_delta(objective_id, delta)
        if not bits:
            return

        reason = str(event.data.get("reason", "")).strip().replace("_", " ")
        objective_title = self._current_objective_title() or "Run objective"
        suffix = f" ({reason})" if reason else ""
        self._log(
            f"{objective_title} advances: {', '.join(bits)} via {channel}{suffix}.",
            channel="mission",
            priority="high",
        )

    def on_final_operation_unlocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        target = event.data.get("target_chunk", (0, 0))
        if not isinstance(target, (list, tuple)) or len(target) != 2:
            target = (0, 0)
        target_label = str(event.data.get("target_label", "")).strip()
        objective_title = str(event.data.get("objective_title", "Run Objective")).strip() or "Run Objective"
        objective_id = str(event.data.get("objective_id", "")).strip().lower()
        if objective_id == "high_value_retrieval":
            if target_label:
                self._log(
                    f"Final operation unlocked: {objective_title}. Reach ({int(target[0])},{int(target[1])}) [{target_label}], enter local, and identify the retrieval site.",
                    channel="mission",
                    priority="critical",
                )
            else:
                self._log(
                    f"Final operation unlocked: {objective_title}. Reach ({int(target[0])},{int(target[1])}), enter local, and identify the retrieval site.",
                    channel="mission",
                    priority="critical",
                )
            return
        if target_label:
            self._log(
                f"Final operation unlocked: {objective_title}. Reach ({int(target[0])},{int(target[1])}) [{target_label}] and enter local.",
                channel="mission",
                priority="critical",
            )
        else:
            self._log(
                f"Final operation unlocked: {objective_title}. Reach ({int(target[0])},{int(target[1])}) and enter local.",
                channel="mission",
                priority="critical",
            )

    def on_final_operation_target_identified(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        property_name = str(event.data.get("target_property_name", "")).strip() or "target site"
        item_name = str(event.data.get("target_item_name", "")).strip() or "target asset"
        target_reason = str(event.data.get("target_reason", "")).strip() or "site lead"
        quality_label = str(event.data.get("target_quality_label", "")).strip() or "working"
        target_value_bonus = max(0, int(event.data.get("target_value_bonus", 0) or 0))
        target_intel_score = max(0, int(event.data.get("target_intel_score", 0) or 0))
        target_entry_detail = str(event.data.get("target_entry_detail", "")).strip()
        message = f"Target site identified: {property_name}. Recover {item_name}."
        if target_intel_score > 0:
            mark_text = "richer mark" if target_value_bonus >= 2 else "cleaner mark" if target_value_bonus >= 1 else "right mark"
            message += f" {quality_label.capitalize()} intel via {target_reason} makes it the {mark_text}."
        if target_entry_detail:
            message += f" Best angle: {target_entry_detail}"
        self._log(message, channel="mission", priority="critical")

    def on_final_operation_target_recovered(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        property_name = str(event.data.get("target_property_name", "")).strip() or "target site"
        item_name = str(event.data.get("target_item_name", "")).strip() or "target asset"
        self._log(
            f"Target recovered: {item_name} from {property_name}.",
            channel="mission",
            priority="critical",
        )

    def on_final_operation_completed(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        objective_title = str(event.data.get("objective_title", "Run Objective")).strip() or "Run Objective"
        self._log(f"Run success: final operation complete ({objective_title}).", channel="mission", priority="critical")
        lines = [str(line).strip() for line in event.data.get("summary_lines", ()) if str(line).strip()]
        for line in lines[:5]:
            self.sim.log.add(f"  {line}")

    def on_final_operation_failed(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        objective_title = str(event.data.get("objective_title", "Run Objective")).strip() or "Run Objective"
        fail_reason = str(event.data.get("fail_reason", "")).strip().replace("_", " ")
        if fail_reason:
            self._log(
                f"Run failed: final operation collapsed ({objective_title}; {fail_reason}).",
                channel="mission",
                priority="critical",
            )
        else:
            self._log(
                f"Run failed: final operation collapsed ({objective_title}).",
                channel="mission",
                priority="critical",
            )
        lines = [str(line).strip() for line in event.data.get("summary_lines", ()) if str(line).strip()]
        for line in lines[:5]:
            self.sim.log.add(f"  {line}")

    def on_run_concluded(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        outcome = str(event.data.get("outcome", "unknown")).strip().lower()
        if outcome == "success":
            self.sim.log.add("Run concluded: success. Closing session.")
        elif outcome == "failed":
            self.sim.log.add("Run concluded: failure. Closing session.")
        else:
            self.sim.log.add("Run concluded. Closing session.")

    def on_run_pressure_changed(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        delta = int(event.data.get("delta", 0))
        if delta <= 0:
            return
        if delta < 8:
            return

        cause = self._pressure_cause_text(event)
        tier = str(event.data.get("tier", "low")).strip().lower()
        after = int(event.data.get("after", 0))
        verb = "spikes" if delta >= 12 else "jumps" if delta >= 9 else "rises"
        self._log(
            f"Attention {verb} by {delta} after {cause}. Pressure now {after} ({tier}).",
            channel="mission",
            priority="high",
            dedupe_window=10,
            dedupe_key=(
                f"run-pressure-up:{str(event.data.get('source', '')).strip().lower()}:"
                f"{str(event.data.get('reason', '')).strip().lower()}:{str(event.data.get('property_id', '')).strip().lower()}"
            ),
        )

    def on_run_pressure_tier_changed(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        tier = str(event.data.get("tier", "low")).strip().lower()
        after = int(event.data.get("after", 0))
        delta = int(event.data.get("delta", 0))
        cause = self._pressure_cause_text(event)
        if tier == "high":
            self._log(
                f"Attention HIGH at {after} after {cause}. City response hardens and services tighten.",
                channel="mission",
                priority="high",
                dedupe_window=10,
                dedupe_key=f"run-pressure-tier:high:{str(event.data.get('source', '')).strip().lower()}",
            )
            return
        if tier == "medium":
            if delta < 0:
                text = (
                    f"Attention drops to MEDIUM at {after} after {cause}. "
                    "The city eases off a notch, but scrutiny is still up."
                )
            else:
                text = (
                    f"Attention MEDIUM at {after} after {cause}. "
                    "Scrutiny rises and goodwill drops."
                )
            self._log(
                text,
                channel="mission",
                priority="high",
                dedupe_window=10,
                dedupe_key=f"run-pressure-tier:medium:{str(event.data.get('source', '')).strip().lower()}",
            )
            return
        self._log(
            f"Attention LOW at {after} after {cause}. Local pressure has cooled.",
            channel="mission",
            priority="high",
            dedupe_window=10,
            dedupe_key=f"run-pressure-tier:low:{str(event.data.get('source', '')).strip().lower()}",
        )

    def on_run_pressure_mitigated(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        delta = int(event.data.get("delta", 0))
        if delta >= 0:
            return
        source = str(event.data.get("source", "mitigation")).strip().lower()
        if source == "dialogue":
            return
        cause = self._pressure_cause_text(event)
        after = int(event.data.get("after", 0))
        tier = str(event.data.get("tier", "low")).strip().lower()
        amount = abs(delta)
        if source == "passive_decay":
            text = f"Attention eases by {amount} as time passes without new trouble. Pressure now {after} ({tier})."
            dedupe_window = 24
        else:
            text = f"Attention eases by {amount} after {cause}. Pressure now {after} ({tier})."
            dedupe_window = 12
        self._log(
            text,
            channel="mission",
            priority="high",
            dedupe_window=dedupe_window,
            dedupe_key=(
                f"run-pressure-down:{source}:{str(event.data.get('reason', '')).strip().lower()}:"
                f"{str(event.data.get('property_id', '')).strip().lower()}"
            ),
        )

    def on_justice_record_changed(self, event):
        if event.data.get("offender_eid") != self.player_eid:
            return
        before_tier = str(event.data.get("before_tier", "clear") or "clear").strip().lower() or "clear"
        after_tier = str(event.data.get("after_tier", "clear") or "clear").strip().lower() or "clear"
        if before_tier != after_tier:
            return

        delta = int(event.data.get("score_delta", 0) or 0)
        if delta <= 0:
            return

        jurisdiction = str(event.data.get("jurisdiction_name", "Justice Office")).strip() or "Justice Office"
        after_score = int(event.data.get("after_score", 0) or 0)
        cause = self._justice_incident_cause_text(event)
        self._log(
            f"Law pressure +{delta} in {jurisdiction} ({after_score}) after {cause}.",
            channel="mission",
            priority="high",
            dedupe_window=10,
            dedupe_key=(
                f"justice-record:{str(event.data.get('jurisdiction_key', jurisdiction)).strip().lower()}:"
                f"{str(event.data.get('incident_type', '')).strip().lower()}:{str(event.data.get('property_id', '')).strip().lower()}"
            ),
        )

    def on_justice_wanted_tier_changed(self, event):
        if event.data.get("offender_eid") != self.player_eid:
            return
        jurisdiction = str(event.data.get("jurisdiction_name", "Justice Office")).strip() or "Justice Office"
        after_tier = str(event.data.get("after_tier", "clear")).strip().lower() or "clear"
        before_tier = str(event.data.get("before_tier", "clear")).strip().lower() or "clear"
        after_score = int(event.data.get("after_score", 0))
        cause = self._justice_incident_cause_text(event)
        if after_tier == "arrest_on_sight":
            text = f"Law: {jurisdiction} wants you on sight ({after_score}) after {cause}."
        elif after_tier == "wanted":
            text = f"Law: {jurisdiction} marks you wanted ({after_score}) after {cause}."
        elif after_tier == "questioning":
            text = f"Law: {jurisdiction} wants to question you ({after_score}) after {cause}."
        elif after_tier == "held":
            text = f"Law: {jurisdiction} takes you into custody."
        elif before_tier != after_tier:
            text = f"Law: {jurisdiction} cools off ({after_score})."
        else:
            return
        self._log(
            text,
            channel="mission",
            priority="high",
            dedupe_window=20,
            dedupe_key=f"justice:{str(event.data.get('jurisdiction_key', jurisdiction)).strip().lower()}:{after_tier}",
        )

    def on_actor_detained(self, event):
        eid = event.data.get("eid")
        by_eid = event.data.get("by_eid")
        jurisdiction = str(event.data.get("jurisdiction_name", "Justice Office")).strip() or "Justice Office"
        if eid == self.player_eid:
            self._log(f"{jurisdiction} takes you into custody.", channel="mission", priority="critical")
            return
        if not (
            self._player_can_perceive_entity(eid)
            or self._player_is_near_event_position(event, radius=8)
        ):
            return
        name = self._npc_label(eid)
        officer = self._npc_label(by_eid, fallback="an enforcer")
        self._log_npc_message(
            eid,
            f"{name} is taken into custody by {officer}.",
            channel="mission",
            priority="high",
            dedupe_window=12,
            dedupe_key=f"detained:{eid}",
        )

    def on_justice_booking_completed(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        property_name = str(event.data.get("property_name", "Justice Office")).strip() or "Justice Office"
        hold_hours = float(event.data.get("hold_hours", 0.0) or 0.0)
        after_tier = str(event.data.get("after_tier", "clear")).strip().lower() or "clear"
        after_score = int(event.data.get("after_score", 0) or 0)
        fine_due = int(event.data.get("fine_due", 0) or 0)
        restitution_due = int(event.data.get("restitution_due", 0) or 0)
        restitution_property_count = int(event.data.get("restitution_property_count", 0) or 0)
        fine_paid = int(event.data.get("fine_paid", 0) or 0)
        cash_fine_paid = int(event.data.get("cash_fine_paid", 0) or 0)
        wallet_fine_paid = int(event.data.get("wallet_fine_paid", 0) or 0)
        bank_fine_paid = int(event.data.get("bank_fine_paid", 0) or 0)
        debt_added = int(event.data.get("debt_added", 0) or 0)
        confiscated_count = int(event.data.get("confiscated_item_count", 0) or 0)
        held_count = int(event.data.get("held_item_count", 0) or 0)
        forfeited_count = int(event.data.get("forfeited_item_count", 0) or 0)
        illegal_count = int(event.data.get("illegal_item_count", 0) or 0)
        restricted_count = int(event.data.get("restricted_item_count", 0) or 0)
        contraband_count = int(event.data.get("contraband_item_count", 0) or 0)
        stolen_count = int(event.data.get("stolen_item_count", 0) or 0)
        evidence_surcharge = int(event.data.get("evidence_surcharge", 0) or 0)
        homicide_surcharge = int(event.data.get("homicide_surcharge", 0) or 0)
        homicide_count = int(event.data.get("homicide_count", 0) or 0)
        weapon_count = int(event.data.get("weapon_item_count", 0) or 0)
        match_labels = [str(label).strip() for label in list(event.data.get("incident_match_labels", ()) or ()) if str(label).strip()]
        posture_label = str(event.data.get("protective_posture_label", "") or "").strip()
        labels = [str(label).strip() for label in list(event.data.get("confiscated_labels", ()) or ()) if str(label).strip()]
        held_labels = [str(label).strip() for label in list(event.data.get("held_labels", ()) or ()) if str(label).strip()]
        forfeited_labels = [str(label).strip() for label in list(event.data.get("forfeited_labels", ()) or ()) if str(label).strip()]
        held_reason_labels = [str(label).strip() for label in list(event.data.get("held_reason_labels", ()) or ()) if str(label).strip()]
        forfeited_reason_labels = [str(label).strip() for label in list(event.data.get("forfeited_reason_labels", ()) or ()) if str(label).strip()]
        ignored_count = int(event.data.get("ignored_item_count", 0) or 0)
        ignored_labels = [str(label).strip() for label in list(event.data.get("ignored_labels", ()) or ()) if str(label).strip()]
        ignored_reason_labels = [str(label).strip() for label in list(event.data.get("ignored_reason_labels", ()) or ()) if str(label).strip()]
        penalty_breakdown = event.data.get("penalty_breakdown") if isinstance(event.data.get("penalty_breakdown"), dict) else {}
        held_property_name = str(event.data.get("held_property_name", property_name)).strip() or property_name
        status_text = {
            "questioning": "wanted for questioning",
            "wanted": "wanted",
            "arrest_on_sight": "arrest on sight",
            "clear": "clear",
        }.get(after_tier, after_tier.replace("_", " ").strip() or "clear")
        summary = f"Booking: processed at {property_name}."
        if hold_hours > 0:
            summary += f" Held about {hold_hours:g}h."
        if fine_due > 0:
            base_fine = int(penalty_breakdown.get("base_fine", 0) or 0)
            if fine_paid > 0:
                summary += f" Fine {fine_paid}c paid"
                payment_bits = []
                if cash_fine_paid > 0:
                    payment_bits.append(f"{cash_fine_paid}c carried")
                if wallet_fine_paid > 0:
                    payment_bits.append(f"{wallet_fine_paid}c wallet")
                if bank_fine_paid > 0:
                    payment_bits.append(f"{bank_fine_paid}c bank")
                if payment_bits:
                    summary += f" ({', '.join(payment_bits)})"
                if debt_added > 0:
                    summary += f"; debt {debt_added}c filed"
                elif fine_paid < fine_due:
                    summary += f" on {fine_due}c due"
                summary += "."
            elif debt_added > 0:
                summary += f" Fine converted to {debt_added}c debt."
            else:
                summary += f" Fine assessed: {fine_due}c."
            if base_fine > 0:
                summary += f" Base fine {base_fine}c."
        if evidence_surcharge > 0:
            summary += f" Evidence surcharge {evidence_surcharge}c."
        if homicide_surcharge > 0:
            count_text = f" for {homicide_count} homicide record(s)" if homicide_count > 0 else ""
            summary += f" Homicide penalty {homicide_surcharge}c{count_text}."
        if restitution_due > 0:
            site_word = "site" if restitution_property_count == 1 else "sites"
            summary += f" Restitution {restitution_due}c across {restitution_property_count} damaged {site_word}."
        summary += f" Released {status_text} ({after_score})."
        if confiscated_count > 0:
            seized_bits = []
            if weapon_count > 0:
                seized_bits.append(f"weapons {weapon_count}")
            if contraband_count > 0:
                seized_bits.append(f"contraband {contraband_count}")
            if illegal_count > 0:
                seized_bits.append(f"illegal {illegal_count}")
            if restricted_count > 0:
                seized_bits.append(f"restricted {restricted_count}")
            if stolen_count > 0:
                seized_bits.append(f"stolen {stolen_count}")
            seized_text = ", ".join(seized_bits) if seized_bits else f"{confiscated_count}"
            summary += f" Seized {confiscated_count} item(s)"
            if seized_text:
                summary += f" [{seized_text}]"
            if labels:
                summary += f": {', '.join(labels[:3])}"
            summary += "."
        if held_count > 0:
            summary += f" Held for release at {held_property_name}: {held_count} item(s)"
            if held_labels:
                summary += f" ({', '.join(held_labels[:3])})"
            if held_reason_labels:
                summary += f" because {', '.join(held_reason_labels[:3])}"
            summary += "."
        if forfeited_count > 0:
            summary += f" Forfeited as evidence/contraband: {forfeited_count} item(s)"
            if forfeited_labels:
                summary += f" ({', '.join(forfeited_labels[:3])})"
            if forfeited_reason_labels:
                summary += f" because {', '.join(forfeited_reason_labels[:3])}"
            summary += "."
        if ignored_count > 0:
            summary += f" Left with you after search: {ignored_count} item(s)"
            if ignored_labels:
                summary += f" ({', '.join(ignored_labels[:3])})"
            if ignored_reason_labels:
                summary += f" because {', '.join(ignored_reason_labels[:3])}"
            summary += "."
        if match_labels:
            summary += f" Strongest evidence: {match_labels[0]}."
        if posture_label:
            summary += f" {posture_label} shaped the local posture."
        self._log(
            summary,
            channel="mission",
            priority="high",
            dedupe_window=12,
            dedupe_key=f"justice-booking:{str(event.data.get('property_id', property_name)).strip().lower()}:{after_tier}:{after_score}",
        )

    def on_justice_inventory_inspected(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        severe = int(event.data.get("incident_evidence_count", 0) or 0)
        stolen = int(event.data.get("reported_stolen_count", 0) or 0)
        contraband = int(event.data.get("contraband_count", 0) or 0)
        latent = int(event.data.get("latent_claim_count", 0) or 0)
        match_labels = [str(label).strip() for label in list(event.data.get("incident_match_labels", ()) or ()) if str(label).strip()]
        if severe > 0:
            text = f"Justice search ties your gear to a reported violent incident ({severe})."
            if match_labels:
                text += f" Strongest read: {match_labels[0]}."
        elif stolen > 0:
            text = f"Justice search matches {stolen} carried item(s) to reported theft."
            if match_labels:
                text += f" Strongest read: {match_labels[0]}."
        elif contraband > 0:
            text = f"Justice search turns up {contraband} contraband item(s)."
        elif latent > 0:
            text = f"Justice search flags {latent} suspicious item(s) with no reported match yet."
        else:
            text = "Justice search turns up nothing actionable."
        self._log(text, channel="mission", priority="high", dedupe_window=8, dedupe_key="justice-inspection")

    def on_justice_questioning_resolved(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        outcome = str(event.data.get("outcome", "") or "").strip().lower()
        evidence_surcharge = int(event.data.get("evidence_surcharge", 0) or 0)
        match_labels = [str(label).strip() for label in list(event.data.get("incident_match_labels", ()) or ()) if str(label).strip()]
        posture_label = str(event.data.get("protective_posture_label", "") or "").strip()
        fine_due = int(event.data.get("fine_due", 0) or 0)
        fine_paid = int(event.data.get("fine_paid", 0) or 0)
        debt_added = int(event.data.get("debt_added", 0) or 0)
        held_count = int(event.data.get("held_item_count", 0) or 0)
        forfeited_count = int(event.data.get("forfeited_item_count", 0) or 0)
        held_labels = [str(label).strip() for label in list(event.data.get("held_labels", ()) or ()) if str(label).strip()]
        forfeited_labels = [str(label).strip() for label in list(event.data.get("forfeited_labels", ()) or ()) if str(label).strip()]
        held_reason_labels = [str(label).strip() for label in list(event.data.get("held_reason_labels", ()) or ()) if str(label).strip()]
        forfeited_reason_labels = [str(label).strip() for label in list(event.data.get("forfeited_reason_labels", ()) or ()) if str(label).strip()]
        if outcome == "custody_escalation":
            text = "Questioning breaks down and justice escalates to custody."
        elif outcome == "release_keep_items":
            text = "Questioning ends with a warning and low-severity contraband overlooked."
        elif outcome == "citation_confiscation":
            text = "Questioning ends in a citation and confiscation."
        elif outcome == "fine_confiscation":
            text = "Questioning ends in a fine and confiscation."
        elif outcome == "full_booking":
            text = "Questioning turns into full booking."
        else:
            text = "Questioning ends with a warning and release."
        if match_labels:
            text += f" Match: {match_labels[0]}."
        if evidence_surcharge > 0:
            text += f" Evidence surcharge {evidence_surcharge}c."
        if fine_due > 0:
            text += f" Fine {fine_due}c."
            if fine_paid > 0:
                text += f" Paid {fine_paid}c."
            if debt_added > 0:
                text += f" Debt {debt_added}c filed."
        if held_count > 0:
            text += f" Held for release: {held_count} item(s)"
            if held_labels:
                text += f" ({', '.join(held_labels[:3])})"
            if held_reason_labels:
                text += f" because {', '.join(held_reason_labels[:3])}"
            text += "."
        if forfeited_count > 0:
            text += f" Forfeited/confiscated: {forfeited_count} item(s)"
            if forfeited_labels:
                text += f" ({', '.join(forfeited_labels[:3])})"
            if forfeited_reason_labels:
                text += f" because {', '.join(forfeited_reason_labels[:3])}"
            text += "."
        if posture_label:
            text += f" {posture_label} stays in effect."
        self._log(text, channel="mission", priority="high", dedupe_window=8, dedupe_key=f"justice-questioning:{outcome}")

    def on_organization_vigilante_response(self, event):
        property_id = str(event.data.get("property_id", "") or "").strip()
        prop = self.sim.properties.get(property_id) if property_id else None
        if not isinstance(prop, dict):
            return
        if not (self._player_is_near_property(prop, radius=12) or self._player_can_perceive_event_position(event)):
            return
        snapshot = local_protective_pressure_snapshot(self.sim, prop)
        label = str(snapshot.get("state_label", "") or "").strip() or "Residents on Alert"
        summary = str(snapshot.get("summary", "") or "").strip()
        text = f"{label} at {str(prop.get('name', property_id)).strip() or property_id}."
        if summary:
            text += f" {summary}."
        self._log(
            text,
            channel="mission",
            priority="high",
            dedupe_window=14,
            dedupe_key=f"protective-response:{property_id}:{label.lower()}",
        )

    def on_incident_dispatch_started(self, event):
        try:
            from game.incident_runtime import incident_record
            incident = incident_record(self.sim, event.data.get("incident_id"))
        except Exception:
            incident = None
        if not isinstance(incident, dict):
            return
        property_id = str(incident.get("property_id", "") or "").strip()
        prop = self.sim.properties.get(property_id) if property_id else None
        if not isinstance(prop, dict):
            return
        if not (self._player_is_near_property(prop, radius=14) or self._player_is_near_event_position(event, radius=12)):
            return
        snapshot = local_protective_pressure_snapshot(self.sim, prop)
        label = str(snapshot.get("state_label", "") or "").strip()
        if label not in {"Justice Sweep", "Checkpoint Questioning"}:
            return
        summary = str(snapshot.get("summary", "") or "").strip()
        text = f"{label} at {str(prop.get('name', property_id)).strip() or property_id}."
        if summary:
            text += f" {summary}."
        self._log(
            text,
            channel="mission",
            priority="high",
            dedupe_window=14,
            dedupe_key=f"protective-dispatch:{property_id}:{label.lower()}",
        )

    def on_organization_heat_tier_changed(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        name = str(event.data.get("organization_name", "Organization")).strip() or "Organization"
        after_tier = str(event.data.get("after_tier", "quiet")).strip().lower() or "quiet"
        before_tier = str(event.data.get("before_tier", "quiet")).strip().lower() or "quiet"
        after_heat = int(event.data.get("after_heat", 0))
        if after_tier == "burned":
            text = f"{name} is burned on you ({after_heat})."
        elif after_tier == "hot":
            text = f"{name} is on alert ({after_heat})."
        elif after_tier == "watchful":
            text = f"{name} gets watchful ({after_heat})."
        elif before_tier != after_tier:
            text = f"{name} cools off ({after_heat})."
        else:
            return
        self._log(
            text,
            channel="mission",
            priority="high",
            dedupe_window=20,
            dedupe_key=f"org-heat:{str(event.data.get('organization_key', name)).strip().lower()}:{after_tier}",
        )

    def on_organization_standing_tier_changed(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        name = str(event.data.get("organization_name", "Organization")).strip() or "Organization"
        after_tier = str(event.data.get("after_tier", "neutral")).strip().lower() or "neutral"
        before_tier = str(event.data.get("before_tier", "neutral")).strip().lower() or "neutral"
        after_standing = float(event.data.get("after_standing", 0.0))
        if after_tier in {"trusted", "favored"}:
            text = f"{name} warms to you ({after_tier} {after_standing:+.2f})."
        elif after_tier in {"hostile", "blacklisted"}:
            text = f"{name} freezes you out ({after_tier} {after_standing:+.2f})."
        elif before_tier != after_tier:
            text = f"{name} resets to neutral standing ({after_standing:+.2f})."
        else:
            return
        self._log(
            text,
            channel="mission",
            priority="high",
            dedupe_window=20,
            dedupe_key=f"org-standing:{str(event.data.get('organization_key', name)).strip().lower()}:{after_tier}",
        )

    def on_skill_rating_changed(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        skill_id = str(event.data.get("skill_id", "") or "").strip().lower()
        if not skill_id:
            return
        label = _skill_label(skill_id)
        delta = float(event.data.get("delta", 0.0) or 0.0)
        if abs(delta) <= 1e-9:
            return
        value = float(event.data.get("value", _actor_skill(self.sim, self.player_eid, skill_id)) or 0.0)
        floor = float(event.data.get("floor", value) or value)
        reason = str(event.data.get("reason", "") or "").strip().lower()
        reason_label = _skill_change_reason_label(reason)

        if delta > 0.0:
            suffix = ""
            if reason_label and reason_label != "practice":
                suffix = f" from {reason_label}"
            self._log(
                f"{label} improves to {value:.1f}{suffix}.",
                channel="general",
                priority="high",
                dedupe_window=6,
                dedupe_key=f"skill-up:{skill_id}:{value:.1f}",
            )
            return

        if reason == "neglect_decay":
            suffix = " and settles at its floor" if value <= floor + 1e-6 else f" (floor {floor:.1f})"
            self._log(
                f"{label} slips to {value:.1f} from neglect{suffix}.",
                channel="general",
                priority="high",
                dedupe_window=6,
                dedupe_key=f"skill-down:{skill_id}:{value:.1f}",
            )
            return

        self._log(
            f"{label} shifts to {value:.1f}.",
            channel="general",
            priority="high",
            dedupe_window=6,
            dedupe_key=f"skill-shift:{skill_id}:{value:.1f}",
        )

    def on_lighting_phase_changed(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        phase = str(event.data.get("phase", "day")).strip().lower() or "day"
        time_label = str(event.data.get("time_label", "")).strip()
        if phase == "dawn":
            headline = "Light shift: dawn breaks."
        elif phase == "day":
            headline = "Light shift: full daylight."
        elif phase == "dusk":
            headline = "Light shift: dusk settles."
        else:
            headline = "Light shift: night falls."

        if time_label:
            headline = f"{headline} ({time_label})"

        player_inside = bool(event.data.get("player_inside", False))
        try:
            player_ambient = float(event.data.get("player_ambient", 1.0))
        except (TypeError, ValueError):
            player_ambient = 1.0
        player_ambient = max(0.0, min(1.0, player_ambient))
        context = "inside" if player_inside else "outside"
        self.sim.log.add(f"{headline} ambient {context} {int(round(player_ambient * 100.0))}%.")

    def on_chunk_focus_changed(self, event):
        cx = event.data["cx"]
        cy = event.data["cy"]
        district = event.data["district_type"]
        area_type = event.data.get("area_type")
        region_name = str(event.data.get("region_name", "")).strip()
        settlement_name = str(event.data.get("settlement_name", "")).strip()
        extras = []
        if region_name:
            extras.append(f"region:{region_name}")
        if settlement_name:
            extras.append(f"city:{settlement_name}")
        suffix = f" {' '.join(extras)}" if extras else ""
        if area_type:
            self.sim.log.add(f"Entered chunk ({cx}, {cy}) - {area_type}/{district}.{suffix}")
        else:
            self.sim.log.add(f"Entered chunk ({cx}, {cy}) - {district}.{suffix}")

        chunk = self.sim.world.get_chunk(cx, cy)
        local_profile = chunk_economy_profile(self.sim, chunk)
        context_label = str(local_profile.get("context_label", "")).strip()
        family_profile = str(local_profile.get("family_profile", "")).strip()
        pressure_note = str(local_profile.get("pressure_note", "")).strip()
        if context_label:
            note = context_label
            if family_profile:
                note = f"{note}; {family_profile}"
            if pressure_note:
                note = f"{note}; {pressure_note}"
            self.sim.log.add(f"Local feel: {note}.")

        for note in opportunity_target_arrival_notes(self.sim, (cx, cy)):
            self.sim.log.add(f"Target drift: {note}", channel="opportunity", priority="high")

        revealed_ids = _world_event_revealed_ids(self.sim)
        for active_event in active_world_events_near_chunk(self.sim, (cx, cy), radius=_WORLD_EVENT_PLAYER_REVEAL_RADIUS):
            event_id = _int_or_default(active_event.get("id"), 0)
            if event_id > 0 and event_id in revealed_ids:
                continue
            label = str(active_event.get("label", "World Event")).strip() or "World Event"
            flavor = str(active_event.get("flavor_start", "")).strip()
            effect = world_event_effect_summary(active_event)
            effect_text = f" Effect: {effect}." if effect else ""
            distance = _chunk_chebyshev_distance((cx, cy), _world_event_chunk_coord(active_event))
            if distance == 0:
                message = f"[WORLD EVENT ACTIVE] {label}: {flavor}{effect_text}" if flavor else f"[WORLD EVENT ACTIVE] {label}.{effect_text}"
                priority = "high"
            else:
                message = f"[WORLD EVENT NEARBY] {label}: {flavor}{effect_text}" if flavor else f"[WORLD EVENT NEARBY] {label} close by.{effect_text}"
                priority = "normal"
            self._log(
                message,
                channel="world",
                priority=priority,
                dedupe_window=20,
                dedupe_key=f"world_event_reveal_{event_id or label}",
            )
            if event_id > 0:
                _mark_world_event_revealed(self.sim, event_id)
