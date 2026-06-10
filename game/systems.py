import curses
import heapq
import hashlib
import itertools
import json
import math
import random
import re
import time
from collections import Counter, deque
from dataclasses import replace
from pathlib import Path

from engine.buildings import building_exterior_profile, layout_chunk_building, world_building_id
from engine.events import Event
from engine.fixtures import generate_chunk_fixture_records
from engine.persistence import restore_chunk_state, unload_chunk_state
from engine.sites import layout_chunk_site, site_gameplay_profile
from engine.systems import System
from engine.tilemap import Tile
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
from game.incident_runtime import incident_record
from game.appearance import (
    district_floor_color as _appearance_district_floor_color,
    district_floor_glyph as _appearance_district_floor_glyph,
    feature_tile_style as _appearance_feature_tile_style,
    property_render_snapshot as _appearance_property_render_snapshot,
    CAT_COAT_COLOR as APPEARANCE_CAT_COAT_COLOR,
)
from game.bones import archive_failed_run_bones, maybe_seed_bones_for_chunk
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
    SocialKnowledge,
    StatusEffects,
    SuppressionState,
    VehicleState,
    Vitality,
    WildlifeSocialState,
    WildlifeBehavior,
    WeaponLoadout,
    WeaponUseProfile,
)
from game.dialogue import (
    choose_dialogue_line,
    ordered_topic_ids as _ordered_dialogue_topic_ids,
    topic_menu_label as _dialogue_topic_menu_label,
    topic_player_line as _dialogue_topic_player_line,
    topic_player_reaction_line as _dialogue_topic_player_reaction_line,
    speaker_style as _dialogue_speaker_style,
    topic_label as _dialogue_topic_label,
    topic_unlocks as _dialogue_topic_unlocks,
)

from game.dialogue_shape import (
    build_dialogue_shape as _build_dialogue_shape,
    shaped_concern_line as _shaped_concern_line,
    shaped_local_line as _shaped_local_line,
    shaped_opening_lines as _shaped_opening_lines,
)
from game.dialogue_pressure import (
    dialogue_family_counts as _dialogue_family_counts,
    dialogue_topic_family as _dialogue_topic_family,
    repeated_topic_label as _repeated_topic_label,
    repeat_pressure_score as _repeat_pressure_score,
)
from game.economy import (
    chunk_economy_profile,
    pick_career_for_workplace,
    workplace_archetype_weight,
)
from game.final_operation import (
    active_final_operation_target_property_id,
    ensure_final_operation_unlocked,
    evaluate_final_operation,
    mark_final_operation_target_recovered,
    sync_final_operation_runtime,
    try_complete_final_operation,
    try_fail_final_operation,
)
from game.debug_overlay import (
    build_debug_overlay as _build_debug_overlay,
)
from game.dialogue_runtime import (
    _active_contractor_record,
    _career_label,
    _contact_benefit_labels,
    _contractor_order_target_from_record,
    _dialog_backup_cursor_payload,
    _dialog_backup_mark_from_state,
    _dialog_map_marker_for_player,
    _dialogue_credential_mode_text,
    _dialogue_guard_grace_active,
    _dialogue_guard_grace_key,
    _dialogue_guard_grace_state,
    _dialogue_hours_text,
    _dialogue_human_join,
    _dialogue_lower_start,
    _dialogue_security_tier_text,
    _disguise_role_label,
    _grant_dialogue_guard_grace,
    _infrastructure_target_property,
    _person_contact_entry,
    _property_access_summary,
    _property_contact_benefits,
    _property_contact_entry,
    _property_contact_lead,
    _workplace_property,
    _world_trait_claim_text,
    _world_trait_claim_value,
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
from game.justice_runtime import (
    booking_anchor_for as _justice_booking_anchor_for,
    decay_records as _decay_justice_records,
    grant_custody_release_grace as _grant_custody_release_grace,
    held_property_snapshot as _justice_held_property_snapshot,
    justice_snapshot as _justice_snapshot,
    justice_summary_rows as _justice_summary_rows,
    mark_in_custody as _mark_justice_in_custody,
    record_incident as _record_justice_incident,
    replace_held_property as _replace_justice_held_property,
    release_from_custody as _release_justice_from_custody,
    store_held_property as _store_justice_held_property,
)
from game.lighting import (
    ambient_snapshot as _lighting_ambient_snapshot,
    lighting_state as _lighting_state,
    update_lighting_state as _update_lighting_state,
)
from game.organization_reputation import (
    apply_organization_reputation_delta as _apply_organization_reputation_delta,
    decay_organization_heat as _decay_organization_heat,
    organization_snapshot as _organization_snapshot,
    organization_terms_for_property as _organization_terms_for_property,
)
from game.player_businesses import (
    actor_player_business_employment,
    fire_actor_from_player_business,
    hire_actor_into_player_business,
    player_business_role_fit,
    player_business_staffing_targets,
)
from game.character_sheet import (
    build_character_sheet_pages as _build_character_sheet_pages,
)
from game.report_runtime import (
    build_progress_report as _report_runtime_build_progress_report,
)
import game.report_debug_ui as _report_debug_ui
from game.skill_progression import SkillProgressionSystem
from game.trade_system import TradeSystem as _TradeSystemExtracted
import game.combat_systems as _combat_systems_module
from game.combat_systems import (
    NPCItemUseSystem as _NPCItemUseSystemExtracted,
    NPCWeaponSystem as _NPCWeaponSystemExtracted,
    StatusEffectSystem as _StatusEffectSystemExtracted,
    WeaponSystem as _WeaponSystemExtracted,
)
import game.perception_systems as _perception_systems_module
from game.perception_systems import (
    CombatPacingSystem as _CombatPacingSystemExtracted,
    CoverSystem as _CoverSystemExtracted,
    LightingSystem as _LightingSystemExtracted,
    NoiseSystem as _NoiseSystemExtracted,
    StealthSystem as _StealthSystemExtracted,
    VisibilitySystem as _VisibilitySystemExtracted,
)
from game.objective_progress import (
    award_objective_progress,
    objective_progress_explain_delta,
)
from game.npc_judgment import evaluate_opportunity_judgment
from game.npc_names import generate_human_personal_name
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
)
from game.organizations import (
    ensure_property_organization,
    occupation_targets_property,
    organization_name,
    property_org_members,
    property_organization_eid,
    seed_property_organization_defaults,
    sync_actor_organization_affiliations,
)
from game.population import (
    ADMIN_ROOM_KINDS,
    FRONT_ROOM_KINDS,
    HOSPITALITY_ROOM_KINDS,
    INDUSTRIAL_ARCHETYPES,
    MEDICAL_ARCHETYPES,
    MEDICAL_ROOM_KINDS,
    NIGHTLIFE_ARCHETYPES,
    RESIDENTIAL_ARCHETYPES,
    SALVAGE_ARCHETYPES,
    SECURITY_ARCHETYPES,
    SECURE_ROOM_KINDS,
    STOREFRONT_ARCHETYPES,
    TRANSIT_ARCHETYPES,
    WORKROOM_KINDS,
    _bond_pair,
    _give_item,
    _shift_window_for,
    _spawn_human,
    seed_chunk_items,
    spawn_chunk_npcs,
    work_shift_active,
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
from game.property_actions import PropertyActionRuntime
from game.property_door_wait import DoorWaitSystem, _actor_in_live_combat, _door_knock_attempt
from game.property_doors import (
    _door_action_text,
    _door_close_attempt,
    _door_interaction_candidate,
    _door_lock_action_text,
    _door_open_attempt,
    _door_state_at,
    _door_tile_is_occupied,
    _operable_door_state_at,
    _ordinary_door_state_at,
    _set_door_open_state,
    _set_property_locked_override,
)
from game.property_ingress import PropertyIngressRuntime, maybe_emit_accidental_trespass_boundary
from game.overworld_runtime import (
    PlayerOverworldRuntime,
    _chunk_tuple,
    _overworld_center_semantic_id,
    _overworld_chunk_knowledge,
    _overworld_chunk_memory_state,
    _overworld_chunk_view,
    _overworld_fill_semantic_id,
    _overworld_legend_line_from_snapshot,
    _overworld_render_style_from_snapshot,
    _player_overworld_visit_state,
    _remember_overworld_chunk_memory,
)
from game.item_actions import ItemActionRuntime
from game.player_look import PlayerLookRuntime
from game.player_interactions import PlayerInteractionRuntime
from game.player_movement import PlayerMovementRuntime
from game.player_travel import PlayerTravelRuntime
from game.movement_runtime import (
    _animal_npc_cannot_cross_doorway,
    _auto_open_closed_door_for_move,
    _can_step_transition_for,
    _closed_door_move_block_reason,
    _entity_blocks,
    _is_traversable_for,
    _movement_allows_auto_open,
    try_move_entity,
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
from game.system_support.access_checks import (
    _access_attempt_roll,
    _maybe_damage_access_tool,
    _resolve_access_skill_check,
)
from game.system_support.awareness_runtime import _watchers_for_position, observation_payload_for_position
from game.system_support.access_runtime import (
    _access_override_score_for_actor,
    _access_tool_context_for,
    _access_tool_terms_for_actor,
    _attempt_locked_property_entry_with_sim,
    _emit_property_lock_tamper_event,
    _lock_override_required_for_prop,
)
from game.system_support.container_runtime import (
    ITEM_STOWED_CONTAINER_METADATA_KEY,
    _clear_inventory_container_assignments,
    _entry_stowed_container_instance,
    _inventory_entries_loose_for_container,
    _inventory_entries_stowed_in_container,
    _unlink_removed_item_from_gear,
)
from game.system_support.actor_runtime import (
    _apply_downed_actor_state,
    _detail_tick_allowed,
    _entity_is_downed,
)
from game.system_support.entity_naming import _entity_display_name
from game.system_support.combat_pacing_runtime import (
    _combat_overlay_state,
    _combat_turn_pacing_active,
    _set_manual_combat_pacing,
)
from game.system_support.combat_targeting_runtime import (
    COMBAT_RELATION_AMBIENT,
    COMBAT_RELATION_DIRECT,
    _combat_relation_to_player,
)
from game.system_support.cover_runtime import (
    _effective_cover_value,
    _threat_positions_for_entity,
)
from game.system_support.interaction_ordering import (
    _direction_step,
    _interaction_target_order_key,
    _manhattan,
    _normalized_direction,
)
from game.system_support.item_runtime import (
    _apply_item_effects_to_entity,
    _default_weapon_reserve_ammo,
    _ensure_armor_loadout,
    _item_armor_profile,
    _item_tags,
    _item_weapon_id,
    _weapon_uses_ammo,
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
from game.system_support.security_disguise_runtime import (
    _camera_disguise_scrutiny_profile,
    _degrade_player_disguise,
    _npc_disguise_scrutiny_profile,
    _npc_recognizes_player,
    _security_fixture_is_online,
)
from game.system_support.status_runtime import (
    _npc_status_metric_args,
    _status_int_offset,
    _status_modifier_total,
    _status_multiplier,
    _status_tick_step,
)
from game.system_support.ai_intent_runtime import _sync_ai_intent
from game.service_runtime import (
    CASINO_GAME_SERVICE_IDS,
    TRANSIT_SERVICE_IDS,
    _building_site_service_seed_token,
    _casino_game_title,
    _clamp,
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
from game.status_ui_runtime import (
    _active_status_summary,
    _entity_status_move_speed_multiplier,
    _floor_label,
    _hud_primary_status_chunks,
    _humanize_slug,
    _sentence_from_note,
    _status_effect_label,
)
from game.location_presentation_runtime import (
    _access_prep_detail_lines,
    _active_property_opportunities,
    _build_known_locations_report,
    _building_street_summary,
    _creature_color_key,
    _entity_legend_line,
    _entity_render_style,
    _infrastructure_role_label,
    _item_display_glyph,
    _item_legend_line,
    _item_reference_line,
    _location_building_category,
    _location_description_snapshot,
    _property_contact_hint,
    _property_interaction_modes,
    _property_knowledge_hint,
    _property_legend_line,
    _property_summary,
    _stakeout_progress_snapshot,
    _stakeout_property_opportunity_stats,
    _storefront_illegal_goods_signal,
    _structure_summary,
    _tile_label,
    _tile_legend_line,
)
from game.ui_text_runtime import (
    LOG_FILTER_PRESETS,
    LOG_PRIORITY_CRITICAL,
    LOG_PRIORITY_HIGH,
    LOG_PRIORITY_LOW,
    LOG_PRIORITY_NORMAL,
    _bullet_display_line,
    _clip_display_line,
    _cycle_log_filter_id,
    _filtered_log_lines,
    _fit_wrapped_sections,
    _flow_text_chunks,
    _grid_distance,
    _hud_log_lines,
    _known_location_detail_lines,
    _known_location_list_line,
    _known_location_summary_bit_color,
    _known_location_summary_line,
    _legend_line,
    _line_channel,
    _line_matches_log_filter,
    _line_priority,
    _line_sequence,
    _line_tick,
    _line_segments,
    _line_text,
    _line_with_prefix,
    _line_with_suffix,
    _log_display_line,
    _log_filter_ids,
    _log_filter_label,
    _log_filter_spec,
    _log_prefix,
    _mode_line,
    _rich_line,
    _segment,
    _segments_to_styled_chars,
    _segments_text,
    _sorted_log_lines,
    _styled_chars_to_segments,
    _tick_duration_label,
    _view_text_wrap_width,
    _wrap_display_lines,
    _wrap_segment_lines,
    _wrap_text_lines,
)
from game.vehicles import (
    generate_chunk_vehicle_records,
    roll_vehicle_profile,
    vehicle_metadata,
    vehicle_services_for_archetype,
)
from game.run_objectives import evaluate_run_objective
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
from game.weapons import WEAPON_CATALOG, roll_weapon_instance, weapon_by_id
from ui.input_keys import ENTER_KEYS, KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_UP

DISTRICT_GLYPHS = {
    "industrial": ":",
    "residential": ".",
    "downtown": "%",
    "slums": ",",
    "corporate": ";",
    "military": "=",
    "entertainment": "*",
}

AREA_GLYPHS = {
    "city": ".",
    "frontier": ",",
    "wilderness": "'",
    "coastal": "_",
}

DISTRICT_FLOOR_COLORS = {
    "industrial": "floor_industrial",
    "residential": "floor_residential",
    "downtown": "floor_downtown",
    "slums": "floor_slums",
    "corporate": "floor_corporate",
    "military": "floor_military",
    "entertainment": "floor_entertainment",
}

AREA_FLOOR_COLORS = {
    "city": "floor_residential",
    "frontier": "floor_frontier",
    "wilderness": "floor_wilderness",
    "coastal": "floor_coastal",
}

PROPERTY_GLYPHS = {
    "building": "B",
    "fixture": "F",
    "asset": "A",
    "vehicle": "&",
}

PROPERTY_COLORS = {
    "building": "property_building",
    "fixture": "property_fixture",
    "asset": "property_asset",
    "vehicle": "vehicle_parked",
}

PROPERTY_ARCHETYPE_DISPLAY = {
    "bank": ("$", "property_service"),
    "brokerage": ("$", "property_service"),
    "pawn_shop": ("$", "property_service"),
    "pharmacy": ("M", "item_medical"),
    "backroom_clinic": ("M", "item_medical"),
    "biotech_clinic": ("M", "item_medical"),
    "field_hospital": ("M", "item_medical"),
    "tide_station": ("M", "item_medical"),
    "herbalist_camp": ("M", "item_medical"),
    "casino": ("C", "building_roof_entertainment"),
    "checkpoint": ("G", "building_roof_secure"),
    "armory": ("G", "building_roof_secure"),
    "barracks": ("G", "building_roof_secure"),
    "courthouse": ("G", "building_roof_secure"),
    "jail": ("G", "building_roof_secure"),
    "prison": ("G", "building_roof_secure"),
    "tower": ("G", "building_roof_secure"),
    "command_center": ("G", "building_roof_secure"),
    "supply_bunker": ("G", "building_roof_secure"),
    "nightclub": ("N", "building_roof_entertainment"),
    "bar": ("N", "building_roof_entertainment"),
    "theater": ("N", "building_roof_entertainment"),
    "music_venue": ("N", "building_roof_entertainment"),
    "gaming_hall": ("N", "building_roof_entertainment"),
    "karaoke_box": ("N", "building_roof_entertainment"),
    "pool_hall": ("N", "building_roof_entertainment"),
    "gallery": ("N", "building_roof_entertainment"),
    "tavern": ("T", "building_roof_entertainment"),
    "restaurant": ("R", "building_roof_storefront"),
    "street_kitchen": ("R", "building_roof_storefront"),
    "soup_kitchen": ("R", "building_roof_storefront"),
    "roadhouse": ("R", "building_roof_storefront"),
    "bait_shop": ("R", "building_roof_storefront"),
    "outfitter": ("G", "building_roof_storefront"),
    "surplus_store": ("G", "building_roof_storefront"),
    "auto_garage": ("V", "property_asset"),
    "truck_stop": ("V", "property_asset"),
    "dock_shack": ("V", "property_asset"),
    "ferry_post": ("V", "property_asset"),
    "metro_exchange": ("V", "property_asset"),
    "tool_depot": ("T", "building_roof_industrial"),
    "hardware_store": ("T", "building_roof_industrial"),
    "chop_shop": ("T", "building_roof_industrial"),
    "junk_market": ("T", "building_roof_industrial"),
    "cold_storage": ("T", "building_roof_industrial"),
    "house": ("H", "building_roof_residential"),
    "apartment": ("H", "building_roof_residential"),
    "tenement": ("H", "building_roof_residential"),
    "hotel": ("H", "building_roof_residential"),
    "flophouse": ("H", "building_roof_residential"),
    "ranger_hut": ("H", "building_roof_residential"),
    "ruin_shelter": ("H", "building_roof_residential"),
    "field_camp": ("H", "building_roof_residential"),
    "survey_post": ("H", "building_roof_residential"),
    "beacon_house": ("H", "building_roof_residential"),
    "office": ("O", "building_roof_civic"),
    "courier_office": ("O", "building_roof_civic"),
    "recruitment_office": ("O", "building_roof_civic"),
    "media_lab": ("O", "building_roof_civic"),
    "data_center": ("O", "building_roof_civic"),
    "server_hub": ("O", "building_roof_civic"),
}

SPECIAL_TILE_RENDER_STYLES = {
    "B": ("#", "building_edge"),
    "b": (".", "building_fill"),
    "#": ("#", "terrain_block"),
    ",": (",", "terrain_brush"),
    "^": ("^", "terrain_rock"),
    "~": ("~", "terrain_water"),
    "_": ("_", "terrain_salt"),
    "=": ("=", "terrain_road"),
    "+": ("+", "feature_door"),
    "/": ("/", "feature_breach"),
    ":": (":", "transit"),
    ">": (">", "transit"),
    "<": ("<", "transit"),
    "E": ("E", "transit"),
}

FEATURE_PRIORITY_TILE_GLYPHS = {'"', "+", "/", ":", "=", "S", ">", "<", "E"}

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

def _float_or_default(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)

THREAT_STATES = {"protecting", "investigating"}


def _dir_label(step, short=False):
    mapping = {
        (1, 0): ("east", "E"),
        (-1, 0): ("west", "W"),
        (0, 1): ("south", "S"),
        (0, -1): ("north", "N"),
        (1, 1): ("southeast", "SE"),
        (1, -1): ("northeast", "NE"),
        (-1, 1): ("southwest", "SW"),
        (-1, -1): ("northwest", "NW"),
    }
    label = mapping.get(tuple(step) if step is not None else None)
    if not label:
        return "?" if short else "unknown"
    return label[1] if short else label[0]


def _cover_profile_for_property(prop):
    metadata = prop.get("metadata") if isinstance(prop, dict) else None
    if isinstance(metadata, dict):
        cover_kind = str(metadata.get("cover_kind", "") or "").strip().lower()
        if cover_kind in {"none", "low", "full"}:
            try:
                cover_value = float(metadata.get("cover_value", 0.35))
            except (TypeError, ValueError):
                cover_value = 0.35
            cover_value = max(0.1, min(0.9, cover_value))
            if cover_kind == "none":
                return ("low", min(0.18, cover_value))
            return (cover_kind, cover_value)

    kind = prop.get("kind")
    if kind == "fixture":
        return ("low", 0.34)
    if kind == "building":
        return ("full", 0.62)
    if kind == "asset":
        return ("low", 0.38)
    if kind == "vehicle":
        return ("low", 0.46)
    return ("low", 0.35)


def _cover_candidates_near(sim, x, y, z):
    candidates = []

    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        nx = x + dx
        ny = y + dy
        if not sim.tilemap.in_bounds(nx, ny):
            continue
        tile = sim.tilemap.tile_at(nx, ny, z)
        if tile and not tile.walkable and not tile.transparent:
            candidates.append({
                "cover_kind": "hard",
                "cover_value": 0.82,
                "source": (nx, ny, z),
                "source_kind": "wall",
                "block_dir": (dx, dy),
                "distance": 1,
            })

    nearby_props = sim.properties_in_radius(x, y, z, r=1)
    for prop in nearby_props:
        cover_kind, cover_value = _cover_profile_for_property(prop)
        block_dir = _direction_step(x, y, prop["x"], prop["y"])
        if block_dir == (0, 0):
            block_dir = None

        candidates.append({
            "cover_kind": cover_kind,
            "cover_value": cover_value,
            "source": (prop["x"], prop["y"], prop["z"]),
            "source_kind": "property",
            "block_dir": block_dir,
            "distance": max(1, _manhattan(x, y, prop["x"], prop["y"])),
            "property_id": prop["id"],
        })

    candidates.sort(key=lambda row: (-row["cover_value"], row["distance"]))
    return candidates


def _best_cover_candidate(sim, x, y, z):
    options = _cover_candidates_near(sim, x, y, z)
    return options[0] if options else None


def _cover_matches_candidate(sim, cover, candidate):
    if not cover or not cover.active or not candidate:
        return False

    current_property_id = None
    if cover.source_kind == "property" and cover.source:
        sx, sy, sz = cover.source
        prop = sim.property_at(sx, sy, sz)
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


def _engage_cover_candidate_for_entity(sim, eid, candidate, *, tick=0, event_type="cover_taken"):
    cover = sim.ecs.get(CoverState).get(eid)
    if not cover or not candidate:
        return False

    cover.engage(
        cover_kind=candidate["cover_kind"],
        cover_value=candidate["cover_value"],
        source=candidate["source"],
        source_kind=candidate["source_kind"],
        block_dir=candidate.get("block_dir"),
        tick=tick,
    )
    sim.emit(Event(
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


def _clear_cover_for_entity(sim, eid, *, tick=0, reason="manual"):
    cover = sim.ecs.get(CoverState).get(eid)
    if not cover or not cover.active:
        return False
    cover.clear(tick=tick)
    sim.emit(Event(
        "cover_left",
        eid=eid,
        reason=reason,
    ))
    return True


def _cover_effect_for_candidate(candidate, entity_x, entity_y, threat_x, threat_y):
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


def _line_points(ax, ay, bx, by):
    x0 = int(ax)
    y0 = int(ay)
    x1 = int(bx)
    y1 = int(by)

    points = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    while True:
        points.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = err * 2
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy

    return points


def _first_blocking_entity_at(sim, x, y, z, exclude_eid=None):
    colliders = sim.ecs.get(Collider)
    vitalities = sim.ecs.get(Vitality)

    for other_eid in sorted(sim.tilemap.entities_at(x, y, z)):
        if other_eid == exclude_eid:
            continue
        collider = colliders.get(other_eid)
        if not collider or not collider.blocks:
            continue
        vitality = vitalities.get(other_eid)
        if vitality and vitality.downed:
            continue
        return other_eid
    return None


def _entity_is_weapon_targetable(sim, eid, *, current_tick=None):
    if sim is None or eid is None:
        return False

    vitality = sim.ecs.get(Vitality).get(eid)
    suppression = sim.ecs.get(SuppressionState).get(eid)
    if suppression and bool(getattr(suppression, "surrendered", False)):
        if vitality and bool(getattr(vitality, "downed", False)):
            return True
        if not vitality or int(getattr(vitality, "hp", 0) or 0) <= 0:
            return False

        try:
            surrender_tick = int(getattr(suppression, "surrender_tick", -1))
        except (TypeError, ValueError):
            surrender_tick = -1

        if current_tick is None:
            try:
                current_tick = int(getattr(sim, "tick", -1))
            except (TypeError, ValueError):
                current_tick = -1
        else:
            try:
                current_tick = int(current_tick)
            except (TypeError, ValueError):
                current_tick = -1

        # Let the surrender itself resolve before already-airborne shots in the
        # same tick can connect.
        if surrender_tick >= 0 and current_tick >= 0 and surrender_tick >= current_tick:
            return False
        return True

    collider = sim.ecs.get(Collider).get(eid)
    if collider and collider.blocks:
        return True

    if vitality and bool(getattr(vitality, "downed", False)):
        return True

    return False


def _first_targetable_entity_at(sim, x, y, z, exclude_eid=None, *, current_tick=None):
    for other_eid in sorted(sim.tilemap.entities_at(x, y, z)):
        if other_eid == exclude_eid:
            continue
        if _entity_is_weapon_targetable(sim, other_eid, current_tick=current_tick):
            return other_eid
    return None


def _projectile_endpoint(sx, sy, tx, ty, max_steps):
    max_steps = int(max(1, max_steps))
    dx = int(tx) - int(sx)
    dy = int(ty) - int(sy)
    distance = max(abs(dx), abs(dy))
    if distance <= 0:
        return None

    scale = float(max_steps) / float(distance)
    ex = int(round(int(sx) + (dx * scale)))
    ey = int(round(int(sy) + (dy * scale)))
    if (ex, ey) == (int(sx), int(sy)):
        ex = int(sx) + (1 if dx > 0 else -1 if dx < 0 else 0)
        ey = int(sy) + (1 if dy > 0 else -1 if dy < 0 else 0)
    return ex, ey


def _projectile_path_points(sx, sy, tx, ty, max_steps, spread=0, rng=None):
    sx = int(sx)
    sy = int(sy)
    tx = int(tx)
    ty = int(ty)
    max_steps = int(max(1, max_steps))

    if spread > 0 and rng is not None:
        tx += int(rng.randint(-spread, spread))
        ty += int(rng.randint(-spread, spread))

    endpoint = _projectile_endpoint(sx, sy, tx, ty, max_steps=max_steps)
    if endpoint is None:
        return []

    ex, ey = endpoint
    return [(int(px), int(py)) for px, py in _line_points(sx, sy, ex, ey)[1:max_steps + 1]]


def _trace_projectile_path(sim, source_eid, path, z, ignore_walls=False):
    traveled = []
    for px, py in path or ():
        px = int(px)
        py = int(py)
        traveled.append((px, py))

        tile = sim.tilemap.tile_at(px, py, z)
        if tile and not tile.walkable and not ignore_walls:
            return {
                "path": traveled,
                "blocked": True,
                "block_kind": "tile",
                "block_x": px,
                "block_y": py,
                "block_eid": None,
            }

        blocker_eid = _first_targetable_entity_at(
            sim,
            px,
            py,
            z,
            exclude_eid=source_eid,
            current_tick=getattr(sim, "tick", None),
        )
        if blocker_eid is not None:
            return {
                "path": traveled,
                "blocked": True,
                "block_kind": "entity",
                "block_x": px,
                "block_y": py,
                "block_eid": blocker_eid,
            }

    return {
        "path": traveled,
        "blocked": False,
        "block_kind": None,
        "block_x": None,
        "block_y": None,
        "block_eid": None,
    }


def _weapon_target_viability(sim, source_eid, source_pos, weapon, target_x, target_y, target_z, target_eid=None):
    if source_pos is None:
        return {
            "ok": False,
            "reason": "missing_position",
            "path": [],
        }

    try:
        tx = int(target_x)
        ty = int(target_y)
        tz = int(target_z)
    except (TypeError, ValueError):
        return {
            "ok": False,
            "reason": "invalid_target",
            "path": [],
        }

    if int(source_pos.z) != tz:
        return {
            "ok": False,
            "reason": "wrong_floor",
            "path": [],
        }

    max_range = int(max(1, weapon.get("range", 1)))
    path = _projectile_path_points(source_pos.x, source_pos.y, tx, ty, max_steps=max_range)
    if not path:
        return {
            "ok": False,
            "reason": "no_direction",
            "path": [],
        }

    ignore_walls = str(weapon.get("trajectory", "ballistic")).lower() == "lobbed"
    trace = _trace_projectile_path(sim, source_eid, path, tz, ignore_walls=ignore_walls)

    if target_eid is not None:
        for px, py in trace["path"]:
            if trace["blocked"] and (px, py) == (trace["block_x"], trace["block_y"]):
                return {
                    "ok": trace["block_kind"] == "entity" and trace["block_eid"] == target_eid,
                    "reason": None if (trace["block_kind"] == "entity" and trace["block_eid"] == target_eid) else "blocked_line",
                    "path": trace["path"],
                    "block_kind": trace["block_kind"],
                    "block_eid": trace["block_eid"],
                    "block_x": trace["block_x"],
                    "block_y": trace["block_y"],
                }
            if (px, py) == (tx, ty):
                return {
                    "ok": True,
                    "reason": None,
                    "path": trace["path"],
                    "block_kind": trace["block_kind"],
                    "block_eid": trace["block_eid"],
                    "block_x": trace["block_x"],
                    "block_y": trace["block_y"],
                }
        return {
            "ok": False,
            "reason": "off_line",
            "path": trace["path"],
            "block_kind": trace["block_kind"],
            "block_eid": trace["block_eid"],
            "block_x": trace["block_x"],
            "block_y": trace["block_y"],
        }

    if trace["blocked"]:
        return {
            "ok": False,
            "reason": "blocked_line",
            "path": trace["path"],
            "block_kind": trace["block_kind"],
            "block_eid": trace["block_eid"],
            "block_x": trace["block_x"],
            "block_y": trace["block_y"],
        }

    return {
        "ok": True,
        "reason": None,
        "path": trace["path"],
        "block_kind": None,
        "block_eid": None,
        "block_x": None,
        "block_y": None,
    }


def _weapon_context_for_entity(sim, eid):
    loadout = sim.ecs.get(WeaponLoadout).get(eid)
    if not loadout:
        return None, None, {}

    weapon_id = loadout.current_weapon()
    if not weapon_id:
        return loadout, None, {}

    weapon = weapon_by_id(weapon_id)
    instance = loadout.weapon_instance(weapon_id)
    return loadout, weapon, instance


def _weapon_tags(weapon):
    if not isinstance(weapon, dict):
        return set()
    return {
        str(tag).strip().lower()
        for tag in weapon.get("tags", ())
        if str(tag).strip()
    }


def _weapon_is_melee(weapon):
    if not isinstance(weapon, dict):
        return True
    if "melee" in _weapon_tags(weapon):
        return True
    try:
        return int(weapon.get("range", 1)) <= 1
    except (TypeError, ValueError):
        return True


def _npc_weapon_preferred_band(weapon, profile=None):
    if not isinstance(weapon, dict) or _weapon_is_melee(weapon):
        return (1, 1, 1)

    try:
        max_range = int(max(1, weapon.get("range", 1)))
    except (TypeError, ValueError):
        max_range = 1
    profile_max = int(max_range)
    if profile is not None:
        try:
            profile_max = int(max(1, getattr(profile, "max_range", max_range)))
        except (TypeError, ValueError):
            profile_max = int(max_range)
    profile_max = max(1, min(max_range, profile_max))

    tags = _weapon_tags(weapon)
    if "shotgun" in tags:
        ideal_min = 2
        ideal_max = min(profile_max, 4)
    elif "smg" in tags or "burst" in tags:
        ideal_min = 2
        ideal_max = min(profile_max, 6)
    elif "precision" in tags or "rifle" in tags:
        ideal_min = min(profile_max, max(3, int(round(max_range * 0.45))))
        ideal_max = profile_max
    else:
        ideal_min = max(2, int(round(max_range * 0.3)))
        ideal_max = min(profile_max, max(ideal_min, int(round(max_range * 0.75))))

    ideal_min = max(1, min(int(ideal_min), profile_max))
    ideal_max = max(ideal_min, min(int(ideal_max), profile_max))
    return ideal_min, ideal_max, max_range


def _npc_combat_metrics(
    *,
    needs=None,
    traits=None,
    vitality=None,
    suppression=None,
    weapon=None,
    pressure_mult=1.0,
    retreat_bias_delta=0.0,
    assault_bias_delta=0.0,
):
    traits = traits or NPCTraits()
    hp_ratio = 1.0
    if vitality:
        hp_ratio = max(0.0, min(1.0, float(vitality.hp) / float(max(1, vitality.max_hp))))

    pressure = 0.0
    if suppression:
        try:
            pressure = float(suppression.pressure)
        except (TypeError, ValueError):
            pressure = 0.0
    pressure = max(0.0, min(1.0, pressure * _float_or_default(pressure_mult, 1.0)))

    safety = 75.0
    if needs:
        try:
            safety = float(needs.safety)
        except (TypeError, ValueError):
            safety = 75.0
    safety = max(0.0, min(100.0, safety))

    has_ranged = bool(isinstance(weapon, dict) and not _weapon_is_melee(weapon))
    low_health = max(0.0, 0.6 - hp_ratio)
    low_safety = max(0.0, (48.0 - safety) / 48.0)

    retreat_bias = _clamp(
        (pressure * 0.72)
        + (low_health * 1.05)
        + (low_safety * 0.45)
        + (0.16 if not has_ranged else 0.0)
        - (float(traits.bravery) * 0.52)
        - (float(traits.discipline) * 0.18),
        lo=0.0,
        hi=1.0,
    )
    retreat_bias = _clamp(retreat_bias + _float_or_default(retreat_bias_delta, 0.0), lo=0.0, hi=1.0)
    assault_bias = _clamp(
        0.28
        + (float(traits.bravery) * 0.58)
        + (0.18 if has_ranged else 0.0)
        - (pressure * 0.45)
        - (low_health * 0.65)
        - (0.14 if not has_ranged else 0.0),
        lo=0.0,
        hi=1.0,
    )
    assault_bias = _clamp(assault_bias + _float_or_default(assault_bias_delta, 0.0), lo=0.0, hi=1.0)

    return {
        "hp_ratio": hp_ratio,
        "pressure": pressure,
        "safety": safety,
        "has_ranged": has_ranged,
        "retreat_bias": retreat_bias,
        "assault_bias": assault_bias,
    }


def _npc_tactical_reachable_tiles(sim, eid, pos, *, max_steps=4):
    origin = (int(pos.x), int(pos.y))
    frontier = deque([(origin[0], origin[1], 0)])
    seen = {origin}
    tiles = [(origin[0], origin[1], 0)]
    directions = (
        (0, -1),
        (1, 0),
        (0, 1),
        (-1, 0),
        (-1, -1),
        (1, -1),
        (-1, 1),
        (1, 1),
    )

    while frontier:
        cx, cy, steps = frontier.popleft()
        if steps >= int(max_steps):
            continue
        for dx, dy in directions:
            nx = int(cx + dx)
            ny = int(cy + dy)
            if (nx, ny) in seen:
                continue
            step_ok, _ = _can_step_transition_for(
                sim,
                moving_eid=eid,
                from_x=int(cx),
                from_y=int(cy),
                to_x=nx,
                to_y=ny,
                z=int(pos.z),
            )
            if not step_ok:
                continue
            seen.add((nx, ny))
            next_steps = int(steps) + 1
            frontier.append((nx, ny, next_steps))
            tiles.append((nx, ny, next_steps))
    return tiles


def _known_threat_position_for_npc(sim, eid, pos, *, target_eid=None, memory=None, radius=12):
    positions = sim.ecs.get(Position)
    if target_eid is not None:
        target_pos = positions.get(target_eid)
        if target_pos and int(target_pos.z) == int(pos.z):
            return (int(target_pos.x), int(target_pos.y), int(target_pos.z))

    if memory:
        threat = memory.strongest("threat")
        if threat:
            data = threat.get("data", {}) if isinstance(threat.get("data"), dict) else {}
            tx = data.get("x")
            ty = data.get("y")
            tz = data.get("z", pos.z)
            if tx is not None and ty is not None and int(tz) == int(pos.z):
                return (int(tx), int(ty), int(tz))

    threats = _threat_positions_for_entity(sim, eid, pos, radius=radius)
    if not threats:
        return None
    _threat_eid, _dist, tx, ty = min(threats, key=lambda row: row[1])
    return (int(tx), int(ty), int(pos.z))


def _pick_npc_retreat_target(sim, eid, pos, threat_pos, *, metrics=None, max_steps=5):
    if pos is None or not isinstance(threat_pos, (list, tuple)) or len(threat_pos) < 3:
        return None
    if int(threat_pos[2]) != int(pos.z):
        return None

    metrics = metrics or {}
    current_dist = _grid_distance(pos.x, pos.y, threat_pos[0], threat_pos[1])
    best = None
    best_score = float("-inf")

    for cx, cy, steps in _npc_tactical_reachable_tiles(sim, eid, pos, max_steps=max_steps):
        threat_dist = _grid_distance(cx, cy, threat_pos[0], threat_pos[1])
        if threat_dist < 2:
            continue
        candidate = _best_cover_candidate(sim, cx, cy, int(pos.z))
        cover_effect = _cover_effect_for_candidate(candidate, cx, cy, threat_pos[0], threat_pos[1])

        score = (float(threat_dist) * 2.8) + (cover_effect * 18.0) - (float(steps) * 4.0)
        if threat_dist <= current_dist:
            score -= 9.0
        if cover_effect >= 0.18:
            score += 8.0
        if (cx, cy) == (int(pos.x), int(pos.y)):
            score -= 4.0
        score += float(metrics.get("retreat_bias", 0.0) or 0.0) * float(max(0, threat_dist - current_dist)) * 4.0

        if best is None or score > best_score:
            best = (int(cx), int(cy), int(pos.z))
            best_score = score

    return best


def _score_npc_combat_tile(sim, eid, current_pos, target_pos, *, weapon=None, profile=None, metrics=None, tile=None, target_eid=None):
    if current_pos is None or target_pos is None or tile is None:
        return None

    cx, cy, steps = tile
    z = int(current_pos.z)
    current_dist = _grid_distance(current_pos.x, current_pos.y, target_pos.x, target_pos.y)
    dist = _grid_distance(cx, cy, target_pos.x, target_pos.y)
    metrics = metrics or {}
    retreat_bias = float(metrics.get("retreat_bias", 0.0) or 0.0)
    assault_bias = float(metrics.get("assault_bias", 0.0) or 0.0)
    has_ranged = bool(metrics.get("has_ranged", False))

    cover_candidate = _best_cover_candidate(sim, cx, cy, z)
    cover_effect = _cover_effect_for_candidate(cover_candidate, cx, cy, target_pos.x, target_pos.y)

    score = 0.0
    score -= float(steps) * 3.5
    if (cx, cy) == (int(current_pos.x), int(current_pos.y)):
        score += 5.0

    if has_ranged:
        ideal_min, ideal_max, max_range = _npc_weapon_preferred_band(weapon, profile=profile)
        if dist > max_range:
            score -= 42.0 + float(dist - max_range) * 7.0
        else:
            viability = _weapon_target_viability(
                sim,
                source_eid=eid,
                source_pos=Position(cx, cy, z),
                weapon=weapon,
                target_x=target_pos.x,
                target_y=target_pos.y,
                target_z=target_pos.z,
                target_eid=target_eid,
            )
            if viability.get("ok"):
                score += 18.0
            else:
                score -= 14.0

            if dist < ideal_min:
                score -= float(ideal_min - dist) * (12.0 + (retreat_bias * 12.0))
            elif dist > ideal_max:
                score -= float(dist - ideal_max) * 6.0
            else:
                score += 16.0

            if dist > current_dist and retreat_bias >= 0.3:
                score += float(dist - current_dist) * (4.0 + (retreat_bias * 6.0))
            elif dist < current_dist and assault_bias >= 0.45:
                score += float(current_dist - dist) * 2.2
    else:
        if dist <= 1:
            score += 22.0 * assault_bias
            score -= 18.0 * retreat_bias
        else:
            score -= float(dist) * max(2.0, 5.5 - (assault_bias * 3.0))
            if dist < current_dist:
                score += float(current_dist - dist) * ((8.0 * assault_bias) + 2.0)
            if dist > current_dist:
                score += float(dist - current_dist) * (9.0 * retreat_bias)

    score += cover_effect * (30.0 + (retreat_bias * 28.0) + (10.0 if has_ranged else 0.0))
    if dist <= 1 and has_ranged and retreat_bias >= 0.25:
        score -= 12.0
    if dist <= 1 and not has_ranged and retreat_bias >= 0.35:
        score -= 14.0

    return {
        "x": int(cx),
        "y": int(cy),
        "z": z,
        "steps": int(steps),
        "score": float(score),
        "cover_candidate": cover_candidate,
        "cover_effect": float(cover_effect),
        "distance": int(dist),
    }


def _pick_npc_combat_position(sim, eid, pos, target_pos, *, weapon=None, profile=None, metrics=None, target_eid=None):
    if pos is None or target_pos is None or int(target_pos.z) != int(pos.z):
        return None

    metrics = metrics or {}
    max_steps = 4 if bool(metrics.get("has_ranged")) or float(metrics.get("retreat_bias", 0.0) or 0.0) >= 0.4 else 3
    best = None
    for tile in _npc_tactical_reachable_tiles(sim, eid, pos, max_steps=max_steps):
        scored = _score_npc_combat_tile(
            sim,
            eid,
            pos,
            target_pos,
            weapon=weapon,
            profile=profile,
            metrics=metrics,
            tile=tile,
            target_eid=target_eid,
        )
        if not scored:
            continue
        if best is None:
            best = scored
            continue
        if float(scored["score"]) > float(best["score"]) + 0.05:
            best = scored
            continue
        if abs(float(scored["score"]) - float(best["score"])) <= 0.05 and int(scored["steps"]) < int(best["steps"]):
            best = scored
    return best


def _sync_npc_cover_against_threat(sim, eid, pos, threat_pos, *, tick=0, min_effect=0.18):
    cover = sim.ecs.get(CoverState).get(eid)
    if not cover or pos is None or threat_pos is None:
        return False
    if int(pos.z) != int(threat_pos[2]):
        return False

    candidate = _best_cover_candidate(sim, pos.x, pos.y, pos.z)
    if not candidate:
        return False

    effect = _cover_effect_for_candidate(candidate, pos.x, pos.y, threat_pos[0], threat_pos[1])
    current_effect = 0.0
    if cover.active:
        current_effect = _effective_cover_value(cover, pos.x, pos.y, threat_pos[0], threat_pos[1])
        if _cover_matches_candidate(sim, cover, candidate):
            return True

    if effect < max(float(min_effect), current_effect - 0.05):
        return False

    event_type = "cover_shifted" if cover.active else "cover_taken"
    return _engage_cover_candidate_for_entity(
        sim,
        eid,
        candidate,
        tick=tick,
        event_type=event_type,
    )


def _entity_uses_melee_aim(sim, eid):
    loadout = sim.ecs.get(WeaponLoadout).get(eid)
    if not loadout:
        return True
    weapon_id = loadout.current_weapon()
    if not weapon_id:
        return True
    weapon = weapon_by_id(weapon_id)
    tags = {str(tag).strip().lower() for tag in weapon.get("tags", ()) if str(tag).strip()}
    return "melee" in tags


def _aim_open_label(sim, eid):
    return "F aim/strike" if _entity_uses_melee_aim(sim, eid) else "F aim"


def _aim_confirm_label(sim, eid):
    return "Enter strike" if _entity_uses_melee_aim(sim, eid) else "Enter fire"


def _appearance_with_effect(appearance, effect):
    if appearance is None:
        return None
    effect = str(effect or "").strip().lower()
    if not effect:
        return appearance
    effects = tuple(getattr(appearance, "effects", ()) or ())
    if effect in effects:
        return appearance
    return replace(appearance, effects=tuple(dict.fromkeys(effects + (effect,))))


def _entity_should_blink_in_combat(sim, eid, *, player_eid=None):
    if eid is None or (player_eid is not None and int(eid) == int(player_eid)):
        return False
    if not _combat_turn_pacing_active(sim):
        return False
    return _combat_relation_to_player(sim, eid, player_eid=player_eid) == COMBAT_RELATION_DIRECT


def _entity_should_mark_ambient_combat(sim, eid, *, player_eid=None):
    if eid is None or (player_eid is not None and int(eid) == int(player_eid)):
        return False
    if not _combat_turn_pacing_active(sim):
        return False
    return _combat_relation_to_player(sim, eid, player_eid=player_eid) == COMBAT_RELATION_AMBIENT


def _weapon_ammo_type_label(weapon):
    if not _weapon_uses_ammo(weapon):
        return "melee"
    tags = {str(tag).strip().lower() for tag in weapon.get("tags", ()) if str(tag).strip()}
    if "launcher" in tags or "explosive" in tags:
        return "rockets"
    if "shotgun" in tags:
        return "shells"
    if "rifle" in tags or "carbine" in tags or "precision" in tags:
        return "rifle"
    if "handgun" in tags or "smg" in tags or "burst" in tags:
        return "light"
    return "ammo"


def _weapon_reserve_ammo(loadout, weapon_id):
    if not loadout or not weapon_id:
        return None
    return loadout.reserve_ammo_value(weapon_id, default=None)


def _manual_fire_preview(sim, eid, x, y, z):
    positions = sim.ecs.get(Position)
    pos = positions.get(eid)
    loadout, weapon, _instance = _weapon_context_for_entity(sim, eid)
    if not pos or not loadout or not weapon:
        return {
            "ok": False,
            "reason": "no_weapon",
            "summary": "aim:no weapon",
            "path": [],
        }

    x = int(x)
    y = int(y)
    z = int(z)
    if z != int(pos.z):
        return {
            "ok": False,
            "reason": "wrong_floor",
            "summary": f"aim:wrong floor z{z}",
            "path": [],
        }

    max_range = int(max(1, weapon.get("range", 1)))
    dist = _grid_distance(pos.x, pos.y, x, y)
    if dist <= 0:
        return {
            "ok": False,
            "reason": "no_direction",
            "summary": "aim:pick a tile",
            "path": [],
            "max_range": max_range,
        }

    path = _projectile_path_points(pos.x, pos.y, x, y, max_steps=max_range)
    if not path:
        return {
            "ok": False,
            "reason": "no_direction",
            "summary": "aim:no direction",
            "path": [],
            "max_range": max_range,
        }

    first_x, first_y = path[0]
    step = (int(first_x) - int(pos.x), int(first_y) - int(pos.y))
    direction = _dir_label(step, short=True)
    ignore_walls = str(weapon.get("trajectory", "ballistic")).lower() == "lobbed"

    trace = _trace_projectile_path(sim, eid, path, z, ignore_walls=ignore_walls)
    impact_label = "clear"
    impact_eid = None
    if trace["blocked"]:
        if trace["block_kind"] == "tile":
            impact_label = f"blocked@{trace['block_x']},{trace['block_y']}"
        elif trace["block_kind"] == "entity" and trace["block_eid"] is not None:
            impact_eid = trace["block_eid"]
            blocker_name = _entity_display_name(sim, impact_eid, title_case=False)
            impact_label = f"hit:{blocker_name}#{impact_eid}"

    target_eid = _first_targetable_entity_at(sim, x, y, z, exclude_eid=eid)
    target_label = ""
    if target_eid is not None:
        target_label = f"{_entity_display_name(sim, target_eid, title_case=False)}#{target_eid}"

    in_range = dist <= max_range
    range_text = f"{dist}/{max_range}"
    summary_bits = [f"aim {direction}", range_text]
    if not in_range:
        summary_bits.append("out")
    if impact_label and impact_label != "clear":
        summary_bits.append(impact_label)
    elif target_label:
        summary_bits.append(target_label)
    elif impact_label:
        summary_bits.append(impact_label)

    return {
        "ok": in_range,
        "reason": None if in_range else "out_of_range",
        "summary": " ".join(summary_bits),
        "path": trace["path"],
        "target_x": x,
        "target_y": y,
        "target_z": z,
        "target_eid": target_eid,
        "target_label": target_label,
        "impact_eid": impact_eid,
        "impact_label": impact_label,
        "max_range": max_range,
        "distance": dist,
        "direction_step": step,
        "direction_short": direction,
        "trajectory": str(weapon.get("trajectory", "ballistic")).lower(),
        "projectile_glyph": str(weapon.get("projectile_glyph", "."))[:1] or ".",
    }


def _target_condition_descriptor(sim, observer_eid, target_eid, *, include_uncertainty=False):
    if sim is None or target_eid is None:
        return ""
    vitality = sim.ecs.get(Vitality).get(target_eid)
    if not vitality:
        return ""
    if vitality.downed or int(vitality.hp) <= 0:
        return "downed"
    suppression = sim.ecs.get(SuppressionState).get(target_eid)
    if suppression and bool(getattr(suppression, "surrendered", False)):
        return "surrendered"

    max_hp = max(1, int(vitality.max_hp))
    hp = int(max(0, min(max_hp, int(vitality.hp))))
    ratio = float(hp) / float(max_hp)
    perception = float(_actor_skill(sim, observer_eid, "perception")) if observer_eid is not None else 5.0

    if perception >= 8.0:
        bands = (
            (0.10, "about to drop"),
            (0.25, "bleeding out"),
            (0.45, "hurt bad"),
            (0.70, "rattled"),
            (0.90, "holding steady"),
            (1.01, "untouched"),
        )
    elif perception >= 5.0:
        bands = (
            (0.20, "on borrowed time"),
            (0.50, "banged up"),
            (0.80, "still standing"),
            (1.01, "steady"),
        )
    else:
        bands = (
            (0.33, "in trouble"),
            (0.75, "worn down"),
            (1.01, "steady"),
        )

    label = "steady"
    for threshold, text in bands:
        if ratio <= float(threshold):
            label = str(text)
            break

    if include_uncertainty and perception < 4.0 and label not in {"downed", "about to drop"}:
        return f"{label} (hard to read)"
    return label


def _has_line_of_sight(sim, ax, ay, az, bx, by, bz):
    return _shared_has_line_of_sight(sim, ax, ay, az, bx, by, bz)


def _observer_is_relevant(ai, identity=None):
    if not ai:
        return False

    role = str(getattr(ai, "role", "") or "").strip().lower()
    if role == "wildlife":
        return False

    if identity:
        taxonomy = str(getattr(identity, "taxonomy_class", "") or "").strip().lower()
        if taxonomy == "hominid":
            return True

    return role in {"guard", "scout", "civilian"}


def _observer_notice_radius(ai=None, traits=None, justice=None):
    radius = 6
    role = str(getattr(ai, "role", "") or "").strip().lower()
    if role == "guard":
        radius += 2
    elif role == "scout":
        radius += 3
    elif role == "civilian":
        radius += 1

    if ai and getattr(ai, "state", "") in {"investigating", "protecting"}:
        radius += 1

    if traits:
        try:
            radius += int(round(float(getattr(traits, "discipline", 0.5)) * 2.0))
        except (TypeError, ValueError):
            pass

    radius += int(round(_crime_sensitivity(justice, default=0.4) * 2.0))
    return max(3, min(12, radius))


def _observer_light_notice_params(sim):
    state = getattr(sim, "visibility_state", None)
    if isinstance(state, dict):
        try:
            tick = int(getattr(sim, "tick", 0))
        except (TypeError, ValueError):
            tick = 0
        try:
            cached_tick = int(state.get("observer_notice_params_tick", -1))
        except (TypeError, ValueError):
            cached_tick = -1
        cached = state.get("observer_notice_params")
        if cached_tick == tick and isinstance(cached, dict):
            return cached

    params = {
        "close_range": 2.0,
        "target_weight": 0.72,
        "observer_weight": 0.28,
        "adaptation_strength": 0.22,
        "interior_floor_penalty": 0.04,
        "aperture_boost_scale": 0.12,
        "contrast_boost_scale": 0.08,
        "role_floor_default": 0.52,
        "role_floor_guard": 0.60,
        "role_floor_scout": 0.66,
        "role_floor_civilian": 0.54,
        "state_bonus_default": 0.0,
        "state_bonus_investigating": 0.04,
        "state_bonus_protecting": 0.06,
    }

    world_traits = getattr(sim, "world_traits", {})
    lighting = world_traits.get("lighting", {}) if isinstance(world_traits, dict) else {}
    if not isinstance(lighting, dict):
        return params
    configured = lighting.get("observer_notice", {})
    if not isinstance(configured, dict):
        return params

    for key, value in configured.items():
        if key not in params:
            continue
        try:
            params[key] = float(value)
        except (TypeError, ValueError):
            continue

    params["close_range"] = _clamp(params["close_range"], lo=1.0, hi=4.0)
    params["target_weight"] = _clamp(params["target_weight"], lo=0.0, hi=1.0)
    params["observer_weight"] = _clamp(params["observer_weight"], lo=0.0, hi=1.0)
    if (params["target_weight"] + params["observer_weight"]) <= 0.001:
        params["target_weight"] = 0.72
        params["observer_weight"] = 0.28
    weight_total = params["target_weight"] + params["observer_weight"]
    params["target_weight"] /= weight_total
    params["observer_weight"] /= weight_total
    params["adaptation_strength"] = _clamp(params["adaptation_strength"], lo=0.0, hi=0.6)
    params["interior_floor_penalty"] = _clamp(params["interior_floor_penalty"], lo=0.0, hi=0.2)
    params["aperture_boost_scale"] = _clamp(params["aperture_boost_scale"], lo=0.0, hi=0.4)
    params["contrast_boost_scale"] = _clamp(params["contrast_boost_scale"], lo=0.0, hi=0.4)
    params["role_floor_default"] = _clamp(params["role_floor_default"], lo=0.35, hi=0.9)
    params["role_floor_guard"] = _clamp(params["role_floor_guard"], lo=0.35, hi=0.95)
    params["role_floor_scout"] = _clamp(params["role_floor_scout"], lo=0.35, hi=0.95)
    params["role_floor_civilian"] = _clamp(params["role_floor_civilian"], lo=0.35, hi=0.95)
    params["state_bonus_default"] = _clamp(params["state_bonus_default"], lo=0.0, hi=0.2)
    params["state_bonus_investigating"] = _clamp(params["state_bonus_investigating"], lo=0.0, hi=0.25)
    params["state_bonus_protecting"] = _clamp(params["state_bonus_protecting"], lo=0.0, hi=0.25)
    if isinstance(state, dict):
        state["observer_notice_params_tick"] = int(getattr(sim, "tick", 0))
        state["observer_notice_params"] = dict(params)
    return params


def _observer_light_notice_multiplier(sim, observer_pos, target_x, target_y, target_z, ai=None, params=None):
    if params is None:
        params = _observer_light_notice_params(sim)

    target_sample = _lighting_ambient_snapshot(sim, target_x, target_y, target_z)
    try:
        target_ambient = float(target_sample.get("ambient", 1.0))
    except (TypeError, ValueError):
        target_ambient = 1.0
    target_ambient = _clamp(target_ambient, lo=0.0, hi=1.0)
    target_inside = bool(target_sample.get("inside", False))
    try:
        target_bleed = float(target_sample.get("aperture_bleed", 0.0) or 0.0)
    except (TypeError, ValueError):
        target_bleed = 0.0
    target_bleed = _clamp(target_bleed, lo=0.0, hi=1.0)

    observer_sample = _lighting_ambient_snapshot(sim, observer_pos.x, observer_pos.y, observer_pos.z)
    try:
        observer_ambient = float(observer_sample.get("ambient", 1.0))
    except (TypeError, ValueError):
        observer_ambient = 1.0
    observer_ambient = _clamp(observer_ambient, lo=0.0, hi=1.0)

    role = str(getattr(ai, "role", "") or "").strip().lower()
    floor = float(params["role_floor_default"])
    if role == "guard":
        floor = float(params["role_floor_guard"])
    elif role == "scout":
        floor = float(params["role_floor_scout"])
    elif role == "civilian":
        floor = float(params["role_floor_civilian"])

    state = str(getattr(ai, "state", "") or "").strip().lower()
    state_bonus_key = f"state_bonus_{state}"
    floor += float(params.get(state_bonus_key, params["state_bonus_default"]))

    if target_inside:
        floor -= float(params["interior_floor_penalty"]) * (1.0 - target_bleed)
        floor += float(params["aperture_boost_scale"]) * target_bleed * (1.0 - target_ambient)

    # Adaptation: observers already in low light are slightly less penalized noticing dark targets.
    adaptation = (1.0 - target_ambient) * max(0.0, (0.55 - observer_ambient)) * float(params["adaptation_strength"])
    floor = _clamp(floor + adaptation, lo=0.38, hi=0.9)

    weighted_ambient = (
        (target_ambient * float(params["target_weight"]))
        + (observer_ambient * float(params["observer_weight"]))
    )
    mult = floor + ((1.0 - floor) * weighted_ambient)

    contrast = target_ambient - observer_ambient
    mult += contrast * float(params["contrast_boost_scale"])

    # Deep interior darkness is intentionally harder to read unless aperture bleed helps.
    if target_inside and target_ambient < 0.35 and target_bleed < 0.2:
        mult -= 0.05

    return _clamp(mult, lo=0.32, hi=1.0)


def _observer_can_notice_position(sim, observer_eid, x, y, z):
    positions = sim.ecs.get(Position)
    ais = sim.ecs.get(AI)
    identities = sim.ecs.get(CreatureIdentity)
    traits_map = sim.ecs.get(NPCTraits)
    justices = sim.ecs.get(JusticeProfile)
    vitalities = sim.ecs.get(Vitality)

    observer_pos = positions.get(observer_eid)
    if not observer_pos or int(observer_pos.z) != int(z):
        return False

    vitality = vitalities.get(observer_eid)
    if vitality and vitality.downed:
        return False

    ai = ais.get(observer_eid)
    identity = identities.get(observer_eid)
    if not _observer_is_relevant(ai, identity=identity):
        return False

    radius = _observer_notice_radius(
        ai=ai,
        traits=traits_map.get(observer_eid),
        justice=justices.get(observer_eid),
    )
    radius += world_event_observer_notice_delta(
        sim,
        sim.chunk_coords(observer_pos.x, observer_pos.y),
    )
    radius = max(3, min(14, radius))
    distance = _grid_distance(observer_pos.x, observer_pos.y, x, y)
    if distance > radius:
        return False

    params = _observer_light_notice_params(sim)
    light_mult = _observer_light_notice_multiplier(
        sim,
        observer_pos=observer_pos,
        target_x=x,
        target_y=y,
        target_z=z,
        ai=ai,
        params=params,
    )
    close_range = float(params.get("close_range", 2.0))
    if distance > max(close_range, float(radius) * float(light_mult)):
        return False

    return _shared_observer_can_see_position(
        sim,
        observer_eid=observer_eid,
        observer_x=observer_pos.x,
        observer_y=observer_pos.y,
        observer_z=observer_pos.z,
        target_x=x,
        target_y=y,
        target_z=z,
        radius=radius,
    )


def _emit_move_access_events(
    sim,
    *,
    eid,
    action,
    origin_x,
    origin_y,
    origin_z,
    target_x,
    target_y,
    target_z,
    emit_clear_offense=True,
):
    prop = _property_covering(sim, target_x, target_y, target_z)
    if prop and _property_cover_intended(prop):
        # Cover-intended fixtures (benches, bus stops, etc.) are street
        # furniture — they should never source trespass events themselves.
        # If the fixture sits inside a building's footprint, charge that
        # building instead.
        key = (int(target_x), int(target_y), int(target_z))
        cover_index = getattr(sim, "property_cover_index", {})
        prop = None
        for _pid in cover_index.get(key, ()):
            _enc = sim.properties.get(_pid)
            if _enc is not None:
                prop = _enc
                break
    prop = _property_enclosing_structure(
        sim,
        target_x,
        target_y,
        target_z,
        prop=prop,
    )
    trespass_triggered = False
    if prop:
        ingress = _property_ingress_context(
            prop,
            from_x=origin_x,
            from_y=origin_y,
            from_z=origin_z,
            to_x=target_x,
            to_y=target_y,
            to_z=target_z,
        )
        access = _evaluate_property_access(
            sim,
            eid,
            prop,
            x=target_x,
            y=target_y,
            z=target_z,
            breach_severity=ingress.breach_severity,
        )
        if access.inside_bounds and access.severity_score > 0:
            observation = observation_payload_for_position(
                sim,
                target_x,
                target_y,
                target_z,
                exclude_eid=eid,
                offender_eid=eid,
                observation_channels=("actor_witness",),
            )
            witnesses = tuple(observation.get("witnesses", ()))
            offense_score = max(
                _offense_score_for_action(action, context="ordinary"),
                10 if access.severity_label == "suspicious" else _offense_score_for_action(action, context="trespass"),
            )
            if access.severity_label == "serious_trespass":
                offense_score = min(100, offense_score + 8)
            if ingress.breach_severity > 0.0:
                offense_score = min(100, offense_score + int(round(ingress.breach_severity * 12.0)))

            ingress_method = _ingress_method_from_context(
                ingress.ingress_kind,
                ingress.aperture_kind,
            )
            if maybe_emit_accidental_trespass_boundary(
                sim,
                eid=eid,
                prop=prop,
                access=access,
                ingress=ingress,
                x=target_x,
                y=target_y,
                z=target_z,
                observation=observation,
                ingress_method=ingress_method,
                action=action,
                offense_score=offense_score,
            ):
                trespass_triggered = True
                return trespass_triggered

            sim.emit(Event(
                "property_trespass",
                offender_eid=eid,
                property_id=prop["id"],
                owner_eid=prop.get("owner_eid"),
                x=target_x,
                y=target_y,
                z=target_z,
                **observation,
                access_level=access.access_level,
                severity_score=access.severity_score,
                severity_label=access.severity_label,
                standing_reason=access.standing_reason,
                currently_open=access.currently_open,
                current_hour=access.current_hour,
                ingress_kind=ingress.ingress_kind,
                aperture_kind=ingress.aperture_kind,
                ingress_method=ingress_method,
                breach_severity=ingress.breach_severity,
            ))
            if witnesses:
                _emit_action_offense_event(
                    sim,
                    eid=eid,
                    action=action,
                    context="trespass" if access.severity_label != "suspicious" else "ordinary",
                    score=offense_score,
                    x=target_x,
                    y=target_y,
                    z=target_z,
                )
            trespass_triggered = True

    if not trespass_triggered and emit_clear_offense:
        _emit_action_offense_event(
            sim,
            eid=eid,
            action=action,
            context="ordinary",
            x=target_x,
            y=target_y,
            z=target_z,
        )

    return trespass_triggered


def _strongest_memory_entry(memory, kind, *, predicate=None):
    if not memory:
        return None
    target_kind = str(kind or "").strip().lower()
    best = None
    for entry in memory.entries:
        if str(entry.get("kind", "")).strip().lower() != target_kind:
            continue
        if callable(predicate) and not predicate(entry):
            continue
        if best is None or float(entry.get("strength", 0.0)) > float(best.get("strength", 0.0)):
            best = entry
    return best


def _recent_actor_memory_impression(sim, memory, actor_eid, *, max_age=360):
    if sim is None or not memory or actor_eid is None:
        return 0.0
    player_eid = getattr(sim, "player_eid", None)
    total = 0.0
    total_weight = 0.0
    current_tick = int(getattr(sim, "tick", 0))

    for entry in list(getattr(memory, "entries", ()) or ()):
        if not isinstance(entry, dict):
            continue
        age = max(0, current_tick - int(entry.get("tick", current_tick) or current_tick))
        if age > int(max_age):
            continue
        kind = str(entry.get("kind", "")).strip().lower()
        data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
        strength = _clamp(float(entry.get("strength", 0.0) or 0.0), lo=0.0, hi=1.0)
        if strength <= 0.0:
            continue
        age_mult = max(0.25, 1.0 - (age / float(max_age + 1)))
        contribution = None

        if kind == "actor_reputation" and data.get("actor_eid") == actor_eid:
            approval = _clamp(float(data.get("approval", 0.0) or 0.0), lo=-1.0, hi=1.0)
            contribution = approval * strength * age_mult
        elif kind == "player_reputation" and actor_eid == player_eid and data.get("player_eid") == actor_eid:
            worldview = str(data.get("worldview", "neutral") or "neutral").strip().lower()
            approval = 0.44
            if worldview in {"order", "care"}:
                approval = 0.52
            elif worldview == "chaos":
                approval = 0.48
            contribution = approval * strength * age_mult
        elif kind == "offense" and data.get("offender_eid") == actor_eid:
            offense_score = int(data.get("offense_score", 0) or 0)
            severity = min(1.0, strength * (0.72 + (offense_score / 120.0)))
            contribution = -severity * age_mult
        elif kind == "threat" and data.get("source_eid") == actor_eid:
            contribution = -min(1.0, strength * 0.92) * age_mult

        if contribution is None or abs(float(contribution)) < 0.0001:
            continue
        total += float(contribution)
        total_weight += max(0.1, abs(float(contribution)))

    if total_weight <= 0.0:
        return 0.0
    return _clamp(total / total_weight, lo=-1.0, hi=1.0)


def _npc_actor_impression(sim, npc_eid, actor_eid, *, memory=None, social=None):
    if sim is None or npc_eid is None or actor_eid is None:
        return 0.0
    if npc_eid == actor_eid:
        return 1.0

    score = 0.0
    if social is None:
        social = sim.ecs.get(NPCSocial).get(npc_eid)
    if social:
        bond = social.bonds.get(actor_eid)
        if isinstance(bond, dict):
            relation = str(bond.get("kind", "") or "").strip().lower()
            bond_score = (
                (float(bond.get("trust", 0.0) or 0.0) * 0.44)
                + (float(bond.get("closeness", 0.0) or 0.0) * 0.33)
                + (float(bond.get("protectiveness", 0.0) or 0.0) * 0.23)
            )
            if relation in {"family", "partner"}:
                bond_score = max(bond_score, 0.84)
            elif relation == "friend":
                bond_score = max(bond_score, 0.68)
            score += min(0.9, bond_score)

    if memory is None:
        memory = sim.ecs.get(NPCMemory).get(npc_eid)
    score += _recent_actor_memory_impression(sim, memory, actor_eid, max_age=360)
    return _clamp(score, lo=-1.0, hi=1.0)


def _npc_conflict_alignment(sim, npc_eid, source_eid, target_eid, *, memory=None, social=None, traits=None, justice=None):
    if sim is None or npc_eid is None or source_eid is None or target_eid is None:
        return 0.0
    if source_eid == target_eid:
        return 0.0
    if npc_eid == target_eid:
        return 1.0
    if npc_eid == source_eid:
        return -1.0

    if memory is None:
        memory = sim.ecs.get(NPCMemory).get(npc_eid)
    if social is None:
        social = sim.ecs.get(NPCSocial).get(npc_eid)
    if traits is None:
        traits = sim.ecs.get(NPCTraits).get(npc_eid) or NPCTraits()
    if justice is None:
        justice = sim.ecs.get(JusticeProfile).get(npc_eid)

    corruption = _clamp(getattr(justice, "corruption", 0.0) if justice else 0.0, lo=0.0, hi=1.0)
    justice_drive = (
        (_justice_level(justice, default=0.5) * 0.46)
        + (_crime_sensitivity(justice, default=0.5) * 0.24)
        + ((1.0 - corruption) * 0.16)
        + (float(getattr(traits, "discipline", 0.5) or 0.5) * 0.14)
    )
    violence_bias = (
        0.06
        + (float(getattr(traits, "empathy", 0.5) or 0.5) * 0.22)
        + (justice_drive * 0.28)
        - (corruption * 0.12)
    )

    source_view = _npc_actor_impression(sim, npc_eid, source_eid, memory=memory, social=social)
    target_view = _npc_actor_impression(sim, npc_eid, target_eid, memory=memory, social=social)

    if social:
        target_bond = social.bonds.get(target_eid)
        if isinstance(target_bond, dict):
            violence_bias += (
                (float(target_bond.get("protectiveness", 0.0) or 0.0) * 0.35)
                + (float(target_bond.get("trust", 0.0) or 0.0) * 0.18)
            )
        source_bond = social.bonds.get(source_eid)
        if isinstance(source_bond, dict):
            violence_bias -= (
                (float(source_bond.get("protectiveness", 0.0) or 0.0) * 0.24)
                + (float(source_bond.get("trust", 0.0) or 0.0) * 0.14)
            )

    if source_view <= -0.35:
        violence_bias += min(0.42, abs(source_view) * 0.55)
    if target_view <= -0.35:
        violence_bias -= min(0.42, abs(target_view) * 0.55)

    alignment = violence_bias + (target_view * 0.72) - (source_view * 0.62)
    return _clamp(alignment, lo=-1.0, hi=1.0)


def _guard_grace_suppresses_memory_entry(sim, npc_eid, entry, offender_eid):
    if offender_eid is None or not isinstance(entry, dict):
        return False
    kind = str(entry.get("kind", "")).strip().lower()
    if kind not in {"offense", "property_threat"}:
        return False
    data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
    if data.get("offender_eid") != offender_eid:
        return False
    property_id = str(data.get("property_id", "")).strip()
    if not property_id:
        return False
    return _dialogue_guard_grace_active(sim, npc_eid, property_id)

def _path_next_step(sim, eid, sx, sy, tx, ty, z, max_nodes=512):
    if sx == tx and sy == ty:
        return None

    start = (sx, sy)
    goal = (tx, ty)

    parents = {start: None}
    costs = {start: 0}
    best = start
    best_score = _grid_distance(sx, sy, tx, ty)
    counter = 0
    open_heap = [(best_score, best_score, counter, start)]

    while open_heap and len(parents) < max_nodes:
        _priority, _heuristic, _order, current = heapq.heappop(open_heap)
        cx, cy = current
        current_cost = costs.get(current)
        if current_cost is None:
            continue

        if (cx, cy) == goal:
            best = goal
            break

        for dx, dy in (
            (0, -1),
            (1, 0),
            (0, 1),
            (-1, 0),
            (-1, -1),
            (1, -1),
            (-1, 1),
            (1, 1),
        ):
            nx = cx + dx
            ny = cy + dy
            node = (nx, ny)

            if node in parents:
                continue
            step_ok, _ = _can_step_transition_for(
                sim,
                moving_eid=eid,
                from_x=cx,
                from_y=cy,
                to_x=nx,
                to_y=ny,
                z=z,
            )
            if not step_ok:
                continue

            new_cost = int(current_cost) + 1
            old_cost = costs.get(node)
            if old_cost is not None and old_cost <= new_cost:
                continue

            parents[node] = (cx, cy)
            costs[node] = new_cost

            score = _grid_distance(nx, ny, tx, ty)
            if score < best_score:
                best = node
                best_score = score
            counter += 1
            heapq.heappush(open_heap, (new_cost + score, score, counter, node))

    if best == start:
        return None

    cursor = best
    while parents[cursor] is not None and parents[cursor] != start:
        cursor = parents[cursor]

    return cursor


def _district_floor_glyph(sim, x, y):
    return _appearance_district_floor_glyph(sim, x, y)


def _district_floor_color(sim, x, y):
    return _appearance_district_floor_color(sim, x, y)


def _appearance_prefers_floor_underlay(appearance):
    semantic_key = str(getattr(appearance, "semantic_id", "") or "").strip().lower()
    if semantic_key in {"feature_window", "feature_door", "feature_breach", "stair_up", "stair_down", "transit_stair_landing", "elevator"}:
        return True
    glyph = str(getattr(appearance, "glyph", "") or "")[:1]
    color_key = str(getattr(appearance, "color", "") or "").strip().lower()
    if color_key == "feature_window" and glyph == '"':
        return True
    if color_key == "feature_door" and glyph in {"+", "'"}:
        return True
    if color_key == "feature_breach" and glyph == "/":
        return True
    if color_key == "transit" and glyph in {">", "<", ":", "E"}:
        return True
    return False


def _floor_link_flags(sim, x, y, z):
    tilemap = getattr(sim, "tilemap", None)
    if tilemap is None:
        return False, False

    return (
        bool(tilemap.floor_transition(int(x), int(y), int(z), 1)),
        bool(tilemap.floor_transition(int(x), int(y), int(z), -1)),
    )


def _feature_tile_style(sim, tile, x, y, z=0):
    return _appearance_feature_tile_style(sim, tile, x, y, z)


def _tile_prefers_feature_legend(sim, tile, x, y, z=0):
    if not tile:
        return False

    glyph = str(tile.glyph)[:1] or "."
    if glyph not in FEATURE_PRIORITY_TILE_GLYPHS:
        return False
    return _feature_tile_style(sim, tile, x, y, z) is not None


def _building_exterior_profile_for(info):
    if not isinstance(info, dict):
        return {}
    return building_exterior_profile(info)


def _building_roof_style(info):
    profile = _building_exterior_profile_for(info)
    style = str(profile.get("roof_style", "") or "").strip()
    return style or "building_roof"


def _tile_render_style(sim, tile, x, y, z=0, revealed_building_id=""):
    appearance = sim.appearance.tile(
        tile,
        x,
        y,
        z=z,
        revealed_building_id=revealed_building_id,
    )
    return appearance.glyph, appearance.color


def _player_tile_memory_state(sim):
    state = getattr(sim, "visibility_state", None)
    if not isinstance(state, dict):
        return {}

    memory = state.get("player_tile_memory")
    if isinstance(memory, dict):
        return memory

    memory = {}
    state["player_tile_memory"] = memory
    return memory

def _trade_contact_terms(sim, viewer_eid, prop):
    entry = _property_contact_entry(sim, viewer_eid, prop)
    pressure = _pressure_snapshot(sim)
    effects = pressure.get("effects", {})
    pressure_tier = str(pressure.get("tier", "low")).strip().lower()
    pressure_buy = float(effects.get("trade_buy_mult", 1.0))
    pressure_sell = float(effects.get("trade_sell_mult", 1.0))
    skill_terms = _trade_skill_terms(sim, viewer_eid)
    org_terms = _organization_terms_for_property(sim, prop)

    # World event trade modifiers for the store's chunk.
    prop_x = int(prop.get("x", 0)) if isinstance(prop, dict) else 0
    prop_y = int(prop.get("y", 0)) if isinstance(prop, dict) else 0
    store_chunk = sim.chunk_coords(prop_x, prop_y)
    event_buy, event_sell = world_event_trade_multipliers(sim, store_chunk)

    note_bits = []
    skill_note = str(skill_terms.get("note", "")).strip()
    if skill_note:
        note_bits.append(skill_note)
    org_note = str(org_terms.get("note", "")).strip()
    if org_note:
        note_bits.append(org_note)
    base = {
        "buy_mult": max(
            0.75,
            min(
                1.6,
                pressure_buy
                * event_buy
                * float(skill_terms.get("buy_mult", 1.0))
                * float(org_terms.get("buy_mult", 1.0)),
            ),
        ),
        "sell_mult": max(
            0.6,
            min(
                1.6,
                pressure_sell
                * event_sell
                * float(skill_terms.get("sell_mult", 1.0))
                * float(org_terms.get("sell_mult", 1.0)),
            ),
        ),
        "source_eid": None,
        "note": "",
    }
    if pressure_tier in {"medium", "high"}:
        note_bits.append(f"city attention {pressure_tier}")
    event_labels = [
        e.get("label", "")
        for e in active_world_events_for_chunk(sim, store_chunk)
        if (e.get("trade_buy_mult", 1.0) != 1.0 or e.get("trade_sell_mult", 1.0) != 1.0)
        and world_event_visible_to_viewer(sim, e, viewer_eid=viewer_eid)
    ]
    if event_labels:
        note_bits.append("local: " + ", ".join(event_labels))
    if note_bits:
        base["note"] = "; ".join(note_bits)
    if not entry:
        return base

    benefits = set(entry.get("benefits", ()))
    standing = max(0.0, min(1.0, float(entry.get("standing", 0.0))))
    source_eid = entry.get("source_eid")

    buy_mult = 1.0
    sell_mult = 1.0
    labels = []
    if "trade_buy_discount" in benefits:
        buy_mult = max(0.84, 1.0 - (0.03 + (standing * 0.09)))
        labels.append("buy rates eased")
    if "trade_sell_bonus" in benefits:
        sell_mult = min(1.12, 1.0 + (0.02 + (standing * 0.07)))
        labels.append("better resale")

    buy_mult = max(
        0.75,
        min(
            1.6,
            buy_mult
            * max(0.75, pressure_buy)
            * event_buy
            * float(skill_terms.get("buy_mult", 1.0))
            * float(org_terms.get("buy_mult", 1.0)),
        ),
    )
    sell_mult = max(
        0.6,
        min(
            1.6,
            sell_mult
            * max(0.6, pressure_sell)
            * event_sell
            * float(skill_terms.get("sell_mult", 1.0))
            * float(org_terms.get("sell_mult", 1.0)),
        ),
    )

    note_bits = []
    if labels:
        source_name = _entity_display_name(sim, source_eid, title_case=True) if source_eid is not None else "Local contact"
        note_bits.append(f"{source_name}: {', '.join(labels)}")
    if skill_note:
        note_bits.append(skill_note)
    if org_note:
        note_bits.append(org_note)
    if pressure_tier in {"medium", "high"}:
        note_bits.append(f"attention {pressure_tier}")
    if event_labels:
        note_bits.append("local: " + ", ".join(event_labels))

    return {
        "buy_mult": buy_mult,
        "sell_mult": sell_mult,
        "source_eid": source_eid,
        "note": "; ".join(note_bits),
    }


def _cover_source_label(sim, cover_state, short=False):
    if not cover_state or not cover_state.active:
        return "none"

    source_kind = str(cover_state.source_kind or "cover").strip().lower()
    block_dir = cover_state.block_dir
    dir_text = _dir_label(block_dir, short=short) if block_dir else ("?" if short else "nearby")

    if source_kind == "wall":
        return f"wall {dir_text}"

    if source_kind == "property" and cover_state.source:
        sx, sy, sz = cover_state.source
        prop = sim.property_at(sx, sy, sz)
        if prop:
            kind = str(prop.get("kind", "property")).strip().lower() or "property"
            if short:
                if kind == "building" and _finance_services_for_property(prop):
                    return f"service {dir_text}"
                return f"{kind} {dir_text}"
            name = str(prop.get("name", kind)).strip() or kind
            return f"{name} {dir_text}"

    return f"cover {dir_text}"


def _cover_source_render(sim, cover_state, active_quest_target=None):
    if not cover_state or not cover_state.active or not cover_state.source:
        return None

    sx, sy, sz = cover_state.source
    if cover_state.source_kind == "wall":
        tile = sim.tilemap.tile_at(sx, sy, sz)
        glyph, color = _tile_render_style(sim, tile, sx, sy, sz)
        return {
            "x": sx,
            "y": sy,
            "z": sz,
            "glyph": glyph,
            "color": color,
            "attrs": getattr(curses, "A_BOLD", 0),
        }

    if cover_state.source_kind == "property":
        prop = sim.property_at(sx, sy, sz)
        if prop:
            appearance = _appearance_property_render_snapshot(
                prop,
                active_quest_target=active_quest_target,
            )
            return {
                "x": sx,
                "y": sy,
                "z": sz,
                "glyph": appearance.glyph,
                "color": appearance.color,
                "semantic_id": appearance.semantic_id,
                "overlays": appearance.overlays,
                "attrs": getattr(curses, "A_BOLD", 0),
            }

    return None


def _build_progress_report(sim, player_eid, opportunity_limit=8):
    return _report_runtime_build_progress_report(
        sim,
        player_eid,
        opportunity_limit=opportunity_limit,
    )


BUILDING_CATEGORY_OPENINGS = {
    "entertainment": (
        "The place is built to gather noise, light, and attention in one direction.",
        "Everything here wants a crowd, an audience, or at least a witness.",
        "The layout is tuned for spectacle before privacy.",
    ),
    "finance": (
        "Everything here suggests orderly transactions and controlled access.",
        "The place feels designed to slow people down before anything valuable is within reach.",
        "The layout is built around caution, routine, and the quiet weight of paperwork.",
    ),
    "general": (
        "The space carries the logic of its trade.",
        "The layout feels deliberate, even when the finish is plain.",
        "It reads as a place with a specific job and no urge to hide it.",
    ),
    "hospitality": (
        "The space works to soften people as soon as they cross the threshold.",
        "It feels designed for bodies to linger, eat, or settle in.",
        "Comfort is part of the plan here, even when the finish is worn.",
    ),
    "industrial": (
        "The place is all throughput and hard-wearing surfaces.",
        "It feels built for loading, repair, or storage before anything else.",
        "The layout favors utility over comfort at every turn.",
    ),
    "medical": (
        "The rooms are laid out for intake, treatment, and controlled movement.",
        "It reads as procedural space: triage first, reassurance second.",
        "The place balances care with containment.",
    ),
    "office": (
        "The space leans on workflow more than comfort.",
        "It reads as a place built for meetings, paperwork, and people moving on schedule.",
        "The interior feels arranged around desks, deadlines, and controlled circulation.",
    ),
    "residential": (
        "The building feels lived in before it feels designed.",
        "It reads as a place shaped by routine rather than presentation.",
        "The layout gives more room to habit than ceremony.",
    ),
    "retail": (
        "The frontage is meant to catch attention and hold it just long enough to make a sale.",
        "It feels tuned for quick judgment from the threshold.",
        "The place is arranged to turn foot traffic into decisions.",
    ),
    "secure": (
        "The whole building announces control before welcome.",
        "It reads as a place that expects scrutiny and keeps backups behind another door.",
        "Everything about it says checkpoints first, explanations later.",
    ),
    "transit": (
        "The space is organized around flow, handoff, and keeping people moving.",
        "Everything here is about passage rather than staying.",
        "It feels tuned for arrivals, departures, and quick exchanges.",
    ),
}
BUILDING_CATEGORY_DETAILS = {
    "entertainment": (
        "Even the quieter corners feel like staging areas for whatever happens in public.",
        "Nothing here stays neutral for long once voices start to bounce off the room.",
        "The deeper rooms feel like support spaces for a performance the street never fully sees.",
    ),
    "finance": (
        "The public side is polite, but the deeper rooms clearly belong to tighter rules.",
        "Open sightlines keep the front legible while the valuable work disappears deeper in.",
        "The room order makes it clear that trust here is procedural, not personal.",
    ),
    "general": (
        "The deeper you look, the more the floor plan starts explaining itself.",
        "The shape of the interior tells you more than the decor does.",
        "It feels like a working layout first and a mood second.",
    ),
    "hospitality": (
        "The place clearly expects people to stay long enough for the mood to matter.",
        "The front edge welcomes, but the service side keeps the whole illusion running.",
        "Even the practical corners are arranged so they do not fully break the mood.",
    ),
    "industrial": (
        "Most of the comfort has been traded away for clearance, reach, and durable surfaces.",
        "The plan keeps work moving forward even when nothing about it is pretty.",
        "Every deeper space feels like a support room for heavier work close by.",
    ),
    "medical": (
        "The order of the rooms makes it clear who gets sorted, treated, or kept waiting first.",
        "Clean procedure matters more here than charm.",
        "The whole place feels built to separate intake, care, and restricted handling.",
    ),
    "office": (
        "The plan separates greeting space from the rooms where the actual decisions pile up.",
        "Most of the tone comes from quiet control rather than any one decorative choice.",
        "The deeper rooms feel meant for people who already know why they are here.",
    ),
    "residential": (
        "Whatever the building was meant to be on paper, routine has had the final say.",
        "The plan feels shaped by repeated use more than by any single design gesture.",
        "The quieter rooms make the public face feel almost incidental.",
    ),
    "retail": (
        "The front is arranged to read quickly, while the deeper rooms do the slower work of keeping stock and margins intact.",
        "Everything close to the door is presentation; everything deeper in is maintenance.",
        "The room order moves cleanly from impression to transaction to back-room reality.",
    ),
    "secure": (
        "The plan keeps public access shallow and the serious work behind another threshold.",
        "Most of the comfort has been sacrificed to observation, delay, and control.",
        "The deeper rooms feel like answers to risks the public never gets to see.",
    ),
    "transit": (
        "The layout exists to keep one movement handing off to the next without much friction.",
        "The place reads like a chain of thresholds rather than a single settled room.",
        "Even the quieter pockets feel borrowed from a system built around movement.",
    ),
}
ROOM_CATEGORY_SENTENCES = {
    "admin": (
        "Paperwork, decisions, and quiet authority gather here.",
        "The room feels built for schedules, files, and conversations that stay behind closed doors.",
        "This is the kind of space where the building's rules get interpreted instead of explained.",
    ),
    "entertainment": (
        "The room is arranged to pull attention forward and keep the energy public.",
        "Everything here feels tuned for spectacle, reaction, or shared focus.",
        "The space wants an audience even when it is standing empty.",
    ),
    "front": (
        "The room is built to receive people before the rest of the building decides what to do with them.",
        "This is the threshold space where the building first states its intentions.",
        "The room works as an introduction, not a conclusion.",
    ),
    "general": (
        "The room carries the building's purpose in a quieter, more focused form.",
        "The space feels like one deliberate piece of a larger working plan.",
        "Whatever else the building is doing, this room has a clear part in it.",
    ),
    "hospitality": (
        "The room is meant to keep people settled, fed, or at least willing to stay a while.",
        "Comfort and service are doing most of the visible work here.",
        "The space softens people before the more practical parts of the building take over.",
    ),
    "medical": (
        "The room is laid out for examination, treatment, or careful handling.",
        "Everything about the space suggests procedure before improvisation.",
        "The room feels tuned for care that still has to stay controlled.",
    ),
    "residential": (
        "Privacy is thinner here than comfort, but routine still settles into the corners.",
        "The room feels shaped by repeated use more than by display.",
        "It reads as a lived-in space, even when the details are sparse.",
    ),
    "secure": (
        "Every surface suggests control, oversight, or deliberate delay.",
        "The room feels stripped down to whatever can be watched, locked, or accounted for.",
        "The space is plainly built for custody rather than comfort.",
    ),
    "transit": (
        "The room is set up for handoff and movement, not lingering.",
        "Everything here suggests passage, timing, and quick exchange.",
        "The space exists to keep people moving through a system bigger than this one room.",
    ),
    "work": (
        "Tool reach, clearance, and workflow matter more here than comfort.",
        "The room feels built around repeated tasks and quick access to the next step.",
        "Everything about the space says this is where the practical work lands.",
    ),
}
ROOM_KIND_SENTENCES = {
    "airlock": (
        "The room exists to slow entry down and make every transition deliberate.",
        "Nothing here is casual; the whole point is to control what crosses through.",
    ),
    "bar_top": (
        "The counter line turns the room into a narrow stage for service, gossip, and pacing.",
        "Everything about the room funnels attention toward whoever is standing behind the bar.",
    ),
    "cash_cage": (
        "Grilles, sightlines, and controlled reach make the room feel secure even when it is quiet.",
        "The whole space is built around keeping money visible to staff and distant from everyone else.",
    ),
    "clerk_office": (
        "The room feels like the quiet hinge between public procedure and the paperwork that keeps it standing up.",
        "Everything here suggests filings, scheduling, and the smaller decisions that keep bigger authority moving.",
    ),
    "concourse": (
        "The room spreads movement wide enough to sort traffic before it narrows again elsewhere.",
        "Everything about the space is built to absorb arrivals without letting them settle.",
    ),
    "count_room": (
        "The room feels clinical about value: tally first, trust later.",
        "Every detail suggests accounting under tight control rather than ordinary office work.",
    ),
    "courtroom": (
        "The room is arranged so authority has a fixed place and everyone else is expected to feel it.",
        "Sightlines, distance, and the raised points of focus make the room feel intentionally unequal.",
    ),
    "dance_floor": (
        "Open space and clear sightlines make the room feel ready for noise the second people fill it.",
        "The whole room exists to turn bodies into part of the performance.",
    ),
    "dispatch_desk": (
        "The room is tuned for quick decisions, short messages, and work moving out the door again.",
        "Everything here feels one step away from being handed off or rerouted.",
    ),
    "gaming_floor": (
        "The room is built to keep attention circulating without ever fully letting it rest.",
        "Sightlines, open lanes, and managed distractions make the room feel deliberately absorbing.",
    ),
    "guest_floor": (
        "The room trades privacy for orderly repetition, one door or partition after the next.",
        "Everything here feels standardized enough to host strangers without ever really personalizing the space.",
    ),
    "guest_lounge": (
        "The room tries to keep waiting guests comfortable without ever pretending the building belongs to them.",
        "Everything here softens transit and downtime into something the building can still manage.",
    ),
    "evidence_lockup": (
        "The room feels built for custody of objects that matter to someone else's trouble.",
        "Shelving, locks, and deliberate access make the space feel like memory under seal.",
    ),
    "front_desk": (
        "The room turns first contact into a small controlled ritual: greet, sort, direct, repeat.",
        "Everything here is built to catch arrivals early and decide where they belong next.",
    ),
    "booking": (
        "Counters, rails, and procedure make the room feel more like intake than welcome.",
        "Everything here is built to turn a person into paperwork before anything else happens.",
    ),
    "cell_block": (
        "Rows, sightlines, and controlled movement make the room feel built around containment first.",
        "The room is organized to make every occupied corner readable from somewhere more powerful.",
    ),
    "holding": (
        "Bare surfaces and controlled exits make the room feel temporary in all the worst ways.",
        "The room is plainly built to keep someone here, not comfortable.",
    ),
    "exercise_yard": (
        "Open air does not make the space feel free; the enclosure is still the loudest thing here.",
        "The room reads like controlled release, all perimeter and watchlines with just enough space to pace.",
    ),
    "kitchen": (
        "Heat, prep space, and short working paths dominate the room.",
        "Everything here is arranged around speed, mess, and staying one step ahead of the next plate.",
    ),
    "lab_floor": (
        "Bench space, procedure, and controlled mess give the room a focused, technical tension.",
        "The room feels built for repeatable work where mistakes would echo longer than the noise that made them.",
    ),
    "loading_bay": (
        "Wide clearance and blunt surfaces make the room feel ready for weight before people.",
        "The room is built for turnover, not comfort.",
    ),
    "manager_office": (
        "The room keeps authority close to the floor without fully mixing with it.",
        "Everything here suggests oversight with just enough distance to feel intentional.",
    ),
    "noc": (
        "The room feels built for watching systems rather than touching them directly.",
        "Every surface suggests monitoring, escalation, and quiet urgency.",
    ),
    "open_office": (
        "The room spreads work out in plain view, trading privacy for coordination.",
        "Shared sightlines and repeated desks make the space feel like workflow made visible.",
    ),
    "archive": (
        "The room feels less active than persistent, built to keep old answers within reach.",
        "Everything here suggests retention, cross-reference, and the slow weight of accumulated records.",
    ),
    "boardroom": (
        "The room is arranged for decisions made in company rather than in public.",
        "Distance, seating, and the fixed center of attention make the room feel intentionally strategic.",
    ),
    "platform": (
        "The room holds the tension between waiting and immediate departure.",
        "Everything here feels like a pause that expects to end abruptly.",
    ),
    "records": (
        "Paper trails and retrieval logic matter more here than comfort.",
        "The room feels built to preserve memory in whatever format the building trusts.",
    ),
    "records_office": (
        "Files, retention, and quiet administrative control define the room.",
        "The room feels like the back end of every public promise the building makes.",
    ),
    "records_room": (
        "The room exists to store decisions long after the people who made them have moved on.",
        "Everything here feels organized against forgetfulness.",
    ),
    "repair_bench": (
        "The room narrows into practical work: reach, tools, and the patience to keep something running.",
        "Every surface looks chosen for hard use instead of display.",
    ),
    "security_room": (
        "The room is built to watch, verify, and decide who becomes a problem.",
        "Everything here suggests oversight, restricted access, and quick escalation.",
    ),
    "server_room": (
        "The room trades comfort for containment, uptime, and controlled noise.",
        "Everything here feels designed to keep systems alive, not people at ease.",
    ),
    "service_bay": (
        "Working clearance and tool access matter more here than any attempt at polish.",
        "The room is tuned for vehicles, machinery, or equipment to arrive broken and leave useful.",
    ),
    "service_corridor": (
        "The room exists to keep support work moving without asking the public to notice it.",
        "Everything here feels like backstage circulation for a larger system.",
    ),
    "showroom": (
        "The room is staged to make stock look more certain than the back end probably feels.",
        "Everything visible here is doing sales work, even when nobody is speaking.",
    ),
    "stage": (
        "The room makes direction feel obvious; all the focus lines point one way.",
        "Even empty, the space still behaves like it expects attention.",
    ),
    "surveillance_room": (
        "The room is less about action than about owning the angle on it.",
        "Everything here suggests a habit of watching other rooms from a safer distance.",
    ),
    "teller_row": (
        "Counter lanes and queue rails turn the room into a controlled funnel for routine transactions.",
        "The room is all measured access, with just enough openness to keep the public moving in line.",
    ),
    "testing_lab": (
        "The room feels built for procedure, calibration, and results that need to stand up later.",
        "Everything here suggests controlled trials rather than open-ended experiment.",
    ),
    "ticketing": (
        "The room exists to turn movement into a transaction before it becomes a journey.",
        "Counters, queues, and repeated questions make the space feel like controlled passage sold a step at a time.",
    ),
    "visitation": (
        "Distance, furniture, and oversight make even ordinary conversation feel supervised.",
        "The room is arranged to allow contact without ever relaxing control of it.",
    ),
    "vault": (
        "Thick boundaries and a stripped-down layout make everything here feel weighty and watched.",
        "The room carries the plain logic of serious storage: less softness, more certainty.",
    ),
}


def _deterministic_text_rng(*parts):
    key = "||".join(str(part or "").strip() for part in parts if str(part or "").strip())
    if not key:
        key = "location-description"
    digest = hashlib.sha256(key.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def _description_choice(rng, options, fallback=""):
    values = [str(option).strip() for option in tuple(options or ()) if str(option).strip()]
    if not values:
        return str(fallback).strip()
    return values[rng.randrange(len(values))]

def _building_activity_token(prop=None, structure=None):
    prop = prop if isinstance(prop, dict) else None
    structure = structure if isinstance(structure, dict) else None
    return (
        _building_id_from_property(prop)
        or _building_id_from_structure(structure)
        or str((prop or {}).get("id", "") or "").strip()
        or str((structure or {}).get("id", "") or "").strip()
        or _building_display_name(prop, structure)
        or "building"
    )


def _building_display_name(prop=None, structure=None):
    if isinstance(prop, dict):
        signage = _property_signage(prop)
        sign_text = str((signage or {}).get("text", "") or "").strip()
        if sign_text:
            return sign_text

        metadata = _property_metadata(prop)
        business_name = str(metadata.get("business_name") or "").strip()
        if business_name:
            return business_name

        prop_name = str(prop.get("name", "") or "").strip()
        if prop_name and not (":" in prop_name and " " not in prop_name):
            return prop_name

        archetype_label = _humanize_slug(metadata.get("archetype"), title=True)
        if archetype_label:
            return archetype_label

    if isinstance(structure, dict):
        structure_name = str(structure.get("name", "") or "").strip()
        if structure_name and not (":" in structure_name and " " not in structure_name):
            return structure_name

        archetype_label = _humanize_slug(structure.get("archetype"), title=True)
        if archetype_label:
            return archetype_label

    return "Building"


def _room_plan_description_sentence(rooms, rng):
    labels = []
    for room in tuple(rooms or ()):
        label = _humanize_slug(room)
        if label and label not in labels:
            labels.append(label)
    if not labels:
        return ""
    if len(labels) == 1:
        return _description_choice(
            rng,
            (
                f"Most of the interior resolves into a single {labels[0]}.",
                f"The plan is almost entirely given over to one main {labels[0]}.",
            ),
        )
    if len(labels) == 2:
        return _description_choice(
            rng,
            (
                f"The plan moves from {labels[0]} to {labels[1]}.",
                f"Inside, the space steps from {labels[0]} into {labels[1]}.",
            ),
        )
    return _description_choice(
        rng,
        (
            f"The floor plan runs from {labels[0]} through {labels[1]} toward {labels[-1]}.",
            f"Inside, the rooms progress from {labels[0]} to {labels[1]}, then tighten around {labels[-1]}.",
            f"The plan starts with {labels[0]}, passes through {labels[1]}, and keeps pulling deeper toward {labels[-1]}.",
        ),
    )


def _building_security_detail(prop):
    metadata = _property_metadata(prop)
    feature_labels = []
    for feature in tuple(metadata.get("security_features", ()) or ()):
        feature_key = str(feature or "").strip().lower()
        if feature_key == "cameras":
            feature_labels.append("cameras")
        elif feature_key == "locked_doors":
            feature_labels.append("locked interior doors")
        elif feature_key == "guards":
            feature_labels.append("visible guard presence")
    feature_labels = [label for index, label in enumerate(feature_labels) if label not in feature_labels[:index]]
    if not feature_labels:
        return ""
    if len(feature_labels) == 1:
        return feature_labels[0]
    return f"{feature_labels[0]} and {feature_labels[1]}"


def _building_detail_sentence(prop, structure, category, rng):
    details = []
    metadata = _property_metadata(prop)

    sign_text = str((_property_signage(prop) or {}).get("text", "") or "").strip() if isinstance(prop, dict) else ""
    security_text = _building_security_detail(prop) if isinstance(prop, dict) else ""
    founder_last = str(metadata.get("business_founder_last_name") or "").strip()

    try:
        floors = int(metadata.get("floors", structure.get("floors", 1) if isinstance(structure, dict) else 1))
    except (TypeError, ValueError):
        floors = 1

    if security_text:
        details.append(f"{security_text.capitalize()} keep the place feeling watched even when nobody is speaking.")
    if sign_text:
        details.append(f'"{sign_text}" still does some of the welcoming before the room layout takes over.')
    if floors > 1:
        details.append("The stacked floors make it feel like a layered operation rather than a single public room.")
    if founder_last:
        details.append(f"It still carries the air of a {founder_last} venture meant to be remembered.")
    if isinstance(prop, dict) and bool(_property_is_storefront(prop)):
        details.append("The front edge is arranged to make a fast first impression before the deeper rooms explain themselves.")
    if isinstance(prop, dict) and bool(metadata.get("large_parcel")):
        details.append("It sprawls wide enough to feel like an operation, not just a frontage.")

    if not details:
        details = BUILDING_CATEGORY_DETAILS.get(category, BUILDING_CATEGORY_DETAILS["general"])
    return _description_choice(rng, details)


def _building_entry_description(sim, prop=None, structure=None):
    prop = prop if isinstance(prop, dict) else None
    structure = structure if isinstance(structure, dict) else None
    structure_archetype = str((structure or {}).get("archetype", "") or "").strip().lower()
    if prop is None and structure_archetype.endswith("_core"):
        return ""

    metadata = _property_metadata(prop)
    archetype = str(metadata.get("archetype", (structure or {}).get("archetype", "")) or "").strip().lower()
    display_name = _building_display_name(prop, structure)
    building_token = _building_activity_token(prop, structure) or display_name
    category = _location_building_category(
        archetype,
        storefront=bool(prop and _property_is_storefront(prop)),
    )
    rooms = tuple(metadata.get("rooms", ())) or tuple((structure or {}).get("rooms", ()))
    pulse = _building_pulse_snapshot(sim, prop=prop, structure=structure)
    rng = _deterministic_text_rng(
        getattr(sim, "seed", ""),
        "building-entry",
        building_token,
        archetype,
        pulse.get("phase", ""),
        pulse.get("event_phase", ""),
        pulse.get("hour", 0),
        pulse.get("bucket", 0),
    )

    parts = [
        f"{display_name}: {_description_choice(rng, BUILDING_CATEGORY_OPENINGS.get(category, BUILDING_CATEGORY_OPENINGS['general']))}",
        _room_plan_description_sentence(rooms, rng),
        str(pulse.get("entry_sentence", "") or "").strip(),
        _building_detail_sentence(prop, structure, category, rng),
    ]
    return " ".join(part for part in parts if part).strip()


def _room_category(room_kind, *, building_category="general"):
    room_kind = str(room_kind or "").strip().lower()
    if not room_kind:
        return "general"
    if room_kind in SECURE_ROOM_KINDS:
        return "secure"
    if room_kind in MEDICAL_ROOM_KINDS:
        return "medical"
    if room_kind in WORKROOM_KINDS:
        return "work"
    if room_kind in HOSPITALITY_ROOM_KINDS:
        return "hospitality"
    if room_kind in ADMIN_ROOM_KINDS:
        return "admin"
    if room_kind in FRONT_ROOM_KINDS:
        return "front"

    if any(token in room_kind for token in ("vault", "security", "surveillance", "cage", "holding", "armored", "airlock", "lockup")):
        return "secure"
    if any(token in room_kind for token in ("exam", "triage", "treatment", "surgery", "dispensary", "lab")):
        return "medical"
    if any(token in room_kind for token in ("office", "records", "conference", "meeting", "briefing", "interview", "manager", "executive")):
        return "admin"
    if any(token in room_kind for token in ("entry", "lobby", "reception", "foyer", "waiting", "counter", "desk", "showroom", "sales")):
        return "front"
    if any(token in room_kind for token in ("service", "repair", "loading", "sorting", "dispatch", "shop", "assembly", "parts", "storage", "power", "racks", "noc", "control")):
        return "work"
    if any(token in room_kind for token in ("bar", "kitchen", "dining", "seating", "commons", "booth", "guest")):
        return "hospitality"
    if any(token in room_kind for token in ("gaming", "dance", "stage", "song", "play", "prize", "exhibit", "studio", "green_room", "vip")):
        return "entertainment"
    if any(token in room_kind for token in ("platform", "concourse", "ticket", "locker")):
        return "transit"
    if any(token in room_kind for token in ("bed", "bunk", "living", "shared_room", "units", "washroom", "bathroom", "laundry", "nap")):
        return "residential"

    if building_category in {"entertainment", "transit", "medical"}:
        return building_category
    return "general"


def _room_position_sentence(structure, rng):
    info = structure if isinstance(structure, dict) else {}
    rooms = tuple(info.get("rooms", ())) if isinstance(info.get("rooms"), (list, tuple)) else ()
    try:
        room_index = int(info.get("room_index", -1))
    except (TypeError, ValueError):
        room_index = -1
    if room_index < 0 or len(rooms) <= 1:
        return ""
    if room_index == 0:
        return _description_choice(
            rng,
            (
                "It works as the front edge of the floor plan.",
                "This is where the building first starts telling you what kind of place it is.",
            ),
        )
    if room_index >= len(rooms) - 1:
        return _description_choice(
            rng,
            (
                "It sits at the deep end of the plan, where casual traffic thins out.",
                "The room feels like the place the public side was always leading away from.",
            ),
        )
    return _description_choice(
        rng,
        (
            "It occupies the middle stretch of the plan, meant to pass people inward or back out again.",
            "The room acts as a hinge between the public edge and the deeper work beyond it.",
        ),
    )


def _room_floor_sentence(structure, rng):
    info = structure if isinstance(structure, dict) else {}
    try:
        floor = int(info.get("floor", 0))
    except (TypeError, ValueError):
        floor = 0
    if floor > 0:
        return _description_choice(
            rng,
            (
                f"Up on {_floor_label(floor, long=True)}, the building feels a little more private and sorted.",
                f"{_floor_label(floor, long=True)} pulls the room away from the public pace below.",
            ),
        )
    if floor < 0:
        return _description_choice(
            rng,
            (
                f"Down on {_floor_label(floor, long=True)}, the space feels more stripped to utility and control.",
                f"{_floor_label(floor, long=True)} gives the room a deeper, more withheld mood.",
            ),
        )
    return ""


def _room_display_label(structure):
    info = structure if isinstance(structure, dict) else {}
    room_label = _humanize_slug(info.get("room_kind"), title=True) or "Room"
    try:
        floor = int(info.get("floor", 0))
    except (TypeError, ValueError):
        floor = 0
    if floor != 0:
        return f"{room_label} ({_floor_label(floor, long=True)})"
    return room_label


def _room_entry_description(sim, structure, prop=None):
    if not isinstance(structure, dict):
        return ""

    room_kind = str(structure.get("room_kind", "") or "").strip().lower()
    if not room_kind:
        return ""

    prop = prop if isinstance(prop, dict) else None
    building_token = (
        _building_id_from_property(prop)
        or _building_id_from_structure(structure)
        or str((prop or {}).get("id", "") or "").strip()
        or room_kind
    )
    building_category = _location_building_category(
        str(_property_metadata(prop).get("archetype", structure.get("archetype", "")) or "").strip().lower(),
        storefront=bool(prop and _property_is_storefront(prop)),
    )
    category = _room_category(room_kind, building_category=building_category)
    try:
        floor = int(structure.get("floor", 0))
    except (TypeError, ValueError):
        floor = 0
    rng = _deterministic_text_rng(getattr(sim, "seed", ""), "room-entry", building_token, floor, room_kind)

    core = _description_choice(
        rng,
        ROOM_KIND_SENTENCES.get(room_kind, ROOM_CATEGORY_SENTENCES.get(category, ROOM_CATEGORY_SENTENCES["general"])),
    )
    extra = _room_floor_sentence(structure, rng) or _room_position_sentence(structure, rng)
    parts = [f"{_room_display_label(structure)}: {core}"]
    if extra:
        parts.append(extra)
    return " ".join(part for part in parts if part).strip()


from game.systems_settlement import (
    _NEWCOMER_LOCAL_CAP,
    _active_business_scene_actor_ids,
    _adjacent_street_tiles,
    _anchor_distance,
    _business_event_chunk_population_target,
    _business_scene_origin,
    _business_scene_spillover_unsettled,
    _chunk_entity_tallies,
    _ensure_newcomer_component,
    _ensure_npc_routine,
    _home_property,
    _is_business_scene_spillover,
    _live_newcomer_count_in_chunk,
    _newcomer_distance_to_property,
    _newcomer_home_capacity,
    _newcomer_home_kind,
    _newcomer_home_load,
    _newcomer_runtime_state,
    _newcomer_work_capacity,
    _newcomer_work_load,
    _next_newcomer_story_id,
    _property_chunk_key,
    _release_actor_to_newcomer,
    _track_entity_in_chunk_population,
    _weighted_choice,
    NPCSettlementSystem,
    spawn_persistent_newcomer,
)



from game.systems_business_events import (
    _BUSINESS_EVENT_SCENE_CAP,
    _BUSINESS_EVENT_REGULAR_SCENE_CAP,
    _BUSINESS_EVENT_RELEASE_CAP,
    _BUSINESS_EVENT_DELIVERY_PHASES,
    _BUSINESS_EVENT_QUEUE_PHASES,
    _BUSINESS_EVENT_GATHERING_PHASES,
    _BUSINESS_EVENT_MEDICAL_RESPONSE_PHASES,
    _BUSINESS_EVENT_RESIDENTIAL_SOCIAL_PHASES,
    _BUSINESS_EVENT_SETTLEMENT_PHASES,
    _BUSINESS_EVENT_HOSPITALITY_PRESSURE_PHASES,
    _BUSINESS_EVENT_OPERATIONAL_PRESSURE_PHASES,
    _BUSINESS_EVENT_AFTERMATH_PHASES,
    _BUSINESS_EVENT_SHIFT_PHASES,
    _BUSINESS_EVENT_RARE_PHASE_CHANCES,
    _BUSINESS_EVENT_REGULAR_CHUNK_HOURLY_CHANCE,
    _BUSINESS_EVENT_SCENE_PROPERTY_COOLDOWN_HOURS,
    _business_event_scene_state,
    _business_event_overrides,
    _business_event_regular_chunk_hourly_chance,
    _business_event_actor_state,
    _business_event_actor_note,
    _business_event_seed_state,
    _business_event_ticks_per_hour,
    _business_event_time_point_text,
    _business_event_property_category,
    _business_event_aftermath_state,
    _prune_business_event_aftermath_state,
    _business_event_aftermath_entry,
    _business_event_reactive_property_near,
    _record_business_event_aftermath,
    _business_event_aftermath_micro_event,
    _business_event_delivery_blueprint,
    _business_event_gathering_blueprint,
    _business_event_inspection_blueprint,
    _business_event_admin_review_blueprint,
    _business_event_medical_response_blueprint,
    _business_event_residential_social_blueprint,
    _business_event_settlement_blueprint,
    _business_event_operational_pressure_blueprint,
    _business_event_aftermath_blueprint,
    _business_event_neighborhood_target,
    _business_event_hospitality_pressure_blueprint,
    _business_event_followup_target,
    _business_event_item_pool,
    _business_event_followup_anchor_fields,
    _business_event_followup_target_label,
    _business_event_enrich_followup_opportunity,
    _business_event_followup_note,
    _business_event_followup_seed,
    _business_event_consequence_seed,
    _business_event_frontage_anchor,
    _building_pulse_snapshot,
    _business_event_seed_scene_specs,
    _business_event_scene_fixture_interaction,
    _business_event_seed_scene_actor_note,
    _business_event_scene_blueprint,
    BusinessPulseAftermathSystem,
    BusinessPulseSceneSystem,
)

def _ingress_label(ingress_kind, aperture_kind=""):
    ingress_kind = str(ingress_kind or "").strip().lower()
    aperture_kind = str(aperture_kind or "").strip().lower()

    if ingress_kind in {"", "outside", "internal", "ordinary_entry"}:
        return ""
    if ingress_kind == "alternate_aperture":
        if aperture_kind in {"window", "skylight"}:
            return "via window"
        if aperture_kind in {"side_door", "service_door", "employee_door"}:
            return "via side door"
        if aperture_kind:
            return f"via {aperture_kind.replace('_', ' ')}"
        return "via alternate entry"
    if ingress_kind == "boundary_breach":
        return "by breach"
    if ingress_kind == "deep_breach":
        return "after appearing inside"
    return ingress_kind.replace("_", " ")

def _ingress_method_from_context(ingress_kind, aperture_kind=""):
    ingress_kind = str(ingress_kind or "").strip().lower()
    aperture_kind = str(aperture_kind or "").strip().lower()
    if ingress_kind in {"", "outside", "internal", "ordinary_entry"}:
        return "authorized_side_entry"
    if ingress_kind == "alternate_aperture":
        if _is_window_aperture(aperture_kind):
            return "window_entry"
        if _is_side_aperture(aperture_kind):
            return "side_entry"
        return "alternate_entry"
    if ingress_kind == "boundary_breach":
        return "forced_breach"
    if ingress_kind == "deep_breach":
        return "deep_breach"
    return ingress_kind

def _actor_is_animal_or_wildlife(sim, eid):
    ais = sim.ecs.get(AI)
    identities = sim.ecs.get(CreatureIdentity)
    ai = ais.get(eid)
    identity = identities.get(eid)
    role = str(getattr(ai, "role", "") or "").strip().lower()
    creature_type = str(getattr(identity, "creature_type", "") or "").strip().lower()
    return role == "wildlife" or creature_type == "animal"


def _shatter_window_for_projectile(sim, offender_eid, x, y, z):
    prop = _property_covering(sim, x, y, z)
    aperture = _property_aperture_at(prop, x, y, z) if isinstance(prop, dict) else None
    if not isinstance(aperture, dict) or not _is_window_aperture(aperture.get("kind", "")):
        return False

    sim.tilemap.set_tile(
        int(x),
        int(y),
        Tile(walkable=True, transparent=True, glyph="/"),
        z=int(z),
    )

    if offender_eid is None:
        return True

    offender_pos = sim.ecs.get(Position).get(offender_eid)
    witnesses = []
    for observer_eid in _watchers_for_position(
        sim,
        int(x),
        int(y),
        int(z),
        exclude_eid=offender_eid,
        offender_eid=offender_eid,
    ):
        if not offender_pos:
            continue
        if _observer_can_notice_position(
            sim,
            observer_eid,
            offender_pos.x,
            offender_pos.y,
            offender_pos.z,
        ):
            witnesses.append(observer_eid)
    access_level = _property_access_level(prop)
    severity_score = 28 + (6 if access_level == "restricted" else 0)
    sim.emit(Event(
        "property_tamper",
        offender_eid=offender_eid,
        property_id=prop.get("id"),
        owner_eid=prop.get("owner_eid"),
        x=int(x),
        y=int(y),
        z=int(z),
        witnessed=bool(witnesses),
        witness_count=len(witnesses),
        witnesses=tuple(witnesses[:6]),
        access_level=access_level,
        severity_score=min(100, severity_score),
        severity_label=_trespass_label_from_score(severity_score),
        standing_reason="none",
        ingress_kind="alternate_aperture",
        aperture_kind=str(aperture.get("kind", "window") or "window").strip().lower() or "window",
        ingress_method="window_shot",
        breach_severity=0.82,
        defender_witnesses_only=True,
        require_witnessed_identity=True,
    ))
    return True

def _resolve_ai_target(sim, ai):
    if ai.target_eid is not None:
        target_pos = sim.ecs.get(Position).get(ai.target_eid)
        if target_pos:
            ai.target = (target_pos.x, target_pos.y, target_pos.z)

    return ai.target


from game.input_system import InputSystem


from game.world_progression_systems import WorldStreamingSystem



from game.dialogue_runtime import (
    _active_contractor_record,
    _career_label,
    _contact_benefit_labels,
    _contractor_order_target_from_record,
    _dialog_backup_cursor_payload,
    _dialog_backup_mark_from_state,
    _dialog_map_marker_for_player,
    _dialogue_credential_mode_text,
    _dialogue_guard_grace_active,
    _dialogue_guard_grace_key,
    _dialogue_guard_grace_state,
    _dialogue_hours_text,
    _dialogue_human_join,
    _dialogue_lower_start,
    _dialogue_security_tier_text,
    _disguise_role_label,
    _first_blocking_entity_at,
    _grant_dialogue_guard_grace,
    _infrastructure_target_property,
    _person_contact_entry,
    _property_access_summary,
    _property_contact_benefits,
    _property_contact_entry,
    _property_contact_lead,
    _workplace_property,
    _world_trait_claim_text,
    _world_trait_claim_value,
)
from game.criminal_justice_runtime import (
    _defender_excuses_window_shot,
    _entities_have_family_bond,
    _noise_merits_attention,
    _observer_is_active_contractor_ally,
    _observer_turns_blind_eye_to_offense,
)


from game.npc_interaction_system import NPCInteractionSystem



from game.player_action_system import PlayerActionSystem


class ItemSystem(System):

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.catalog = ITEM_CATALOG
        self.item_actions = ItemActionRuntime(self)
        self.sim.events.subscribe("player_action", self.on_player_action)
        self.sim.events.subscribe("use_item_request", self.on_use_item_request)
        self.sim.events.subscribe("throw_item_request", self.on_throw_item_request)
        self.sim.events.subscribe("drop_item_request", self.on_drop_item_request)

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

    def _emit_removed_gear_events(self, eid, removed_entry, reason):
        return self.item_actions.emit_removed_gear_events(eid, removed_entry, reason)

    def _consume_item(self, eid, x, y, z, instance_id=None, reason="manual"):
        return self.item_actions.consume_item(
            eid,
            x,
            y,
            z,
            instance_id=instance_id,
            reason=reason,
        )

    def _handle_pickup(self, eid, x, y, z):
        return self.item_actions.handle_pickup(eid, x, y, z)

    def _handle_drop(self, eid, x, y, z, instance_id=None):
        return self.item_actions.handle_drop(
            eid,
            x,
            y,
            z,
            instance_id=instance_id,
        )

    def on_use_item_request(self, event):
        return self.item_actions.on_use_item_request(event)

    def on_throw_item_request(self, event):
        return self.item_actions.on_throw_item_request(event)

    def on_drop_item_request(self, event):
        return self.item_actions.on_drop_item_request(event)

    def on_player_action(self, event):
        return self.item_actions.on_player_action(event)

    def update(self):
        return self.item_actions.update()


class TradeSystem(_TradeSystemExtracted):

    def __init__(self, sim, player_eid):
        super().__init__(sim, player_eid, trade_contact_terms=_trade_contact_terms)


_combat_systems_module._float_or_default = _float_or_default
_combat_systems_module._grid_distance = _grid_distance
_combat_systems_module._clamp = _clamp
_combat_systems_module._dir_label = _dir_label
_combat_systems_module._first_targetable_entity_at = _first_targetable_entity_at
_combat_systems_module._manual_fire_preview = _manual_fire_preview
_combat_systems_module._projectile_path_points = _projectile_path_points
_combat_systems_module._shatter_window_for_projectile = _shatter_window_for_projectile
_combat_systems_module._weapon_target_viability = _weapon_target_viability
_combat_systems_module._weapon_is_melee = _weapon_is_melee
_combat_systems_module._npc_combat_metrics = _npc_combat_metrics
_perception_systems_module.QUIET_NOISE_CAUSES = QUIET_NOISE_CAUSES


class WeaponSystem(_WeaponSystemExtracted):
    pass


class NPCWeaponSystem(_NPCWeaponSystemExtracted):
    pass


class StatusEffectSystem(_StatusEffectSystemExtracted):
    pass


class NPCItemUseSystem(_NPCItemUseSystemExtracted):
    pass


class CoverSystem(_CoverSystemExtracted):
    pass


class CombatPacingSystem(_CombatPacingSystemExtracted):
    pass


class NoiseSystem(_NoiseSystemExtracted):
    pass


class LightingSystem(_LightingSystemExtracted):
    pass


class VisibilitySystem(_VisibilitySystemExtracted):
    pass


class StealthSystem(_StealthSystemExtracted):
    pass


from game.world_progression_systems import OpportunitySystem



from game.world_progression_systems import RivalOperatorSystem



from game.objective_progress import ObjectiveProgressSystem


from game.criminal_justice_system import CriminalJusticeSystem



from game.organization_reputation import OrganizationReputationSystem
from game.run_pressure import RunPressureSystem


from game.world_progression_systems import FinalOperationSystem



from game.property_security_systems import PropertyAwarenessSystem



from game.property_security_systems import PropertyDefenseSystem


from game.property_security_systems import CameraSystem



from game.systems_memory import (
    NPCMemorySystem,
    RumorSystem,
)

from game.systems_wildlife import (
    _actor_has_ranged_weapon,
    _actor_injury_score,
    _actor_is_human,
    _actors_use_wildlife_social,
    _animal_behavior_context_for_actor,
    _animal_ecology_profile_for_actor,
    _animal_memory_for_actor,
    _animal_memory_regard,
    _animal_physical_profile_for_actor,
    _animal_social_profile_for_actor,
    _default_animal_physical_profile,
    _default_animal_social_profile,
    _default_ecology_profile,
    _human_wildlife_presence_for_actor,
    _pick_wildlife_escape_target,
    _pick_wildlife_patrol_target,
    _relocate_indoor_wildlife_outdoors,
    _species_key,
    _sync_wildlife_bond_pair,
    _wildlife_best_scavenge_target,
    _wildlife_bond_for_actor,
    _wildlife_bond_score,
    _wildlife_can_observe,
    _wildlife_chase_drive,
    _wildlife_ecology_intent,
    _wildlife_flock_anchor,
    _wildlife_group_alarm_target,
    _wildlife_guardian_bonus,
    _wildlife_home_position,
    _wildlife_is_active,
    _wildlife_pack_support,
    _wildlife_social_intent,
    _wildlife_social_state_for_actor,
    _wildlife_social_target_score,
    _wildlife_threat_score,
    _wildlife_walkable_tiles,
    AnimalSocialSystem,
    CreatureHazardSystem,
)



from game.npc_intent_systems import NPCNeedsSystem



_WORKING_ROOM_CATEGORY_WEIGHTS = {
    "entertainment": {"entertainment": 6.0, "hospitality": 4.0, "front": 4.0, "work": 2.0, "admin": 1.5},
    "finance": {"secure": 5.0, "admin": 5.0, "front": 3.0, "work": 2.0},
    "general": {"work": 3.0, "admin": 2.0, "front": 2.0, "general": 1.5},
    "hospitality": {"hospitality": 5.0, "front": 4.0, "work": 3.0, "residential": 2.0, "admin": 1.5},
    "industrial": {"work": 6.0, "admin": 2.0, "secure": 1.5, "front": 1.0},
    "medical": {"medical": 6.0, "admin": 3.5, "front": 3.0, "secure": 2.0},
    "office": {"admin": 6.0, "work": 3.0, "front": 2.0},
    "residential": {"residential": 6.0, "hospitality": 2.0, "front": 1.0, "admin": 0.5},
    "retail": {"front": 5.0, "work": 4.0, "admin": 2.5, "hospitality": 2.0},
    "secure": {"secure": 6.0, "admin": 3.5, "front": 2.0, "work": 2.0},
    "transit": {"transit": 6.0, "front": 4.0, "work": 4.0, "admin": 2.0},
}
_GUARD_ROOM_CATEGORY_WEIGHTS = {
    "secure": 6.0,
    "admin": 3.0,
    "front": 2.0,
    "work": 1.0,
    "transit": 1.0,
}
_LOUNGING_ROOM_CATEGORY_WEIGHTS = {
    "residential": 6.0,
    "hospitality": 4.0,
    "general": 2.0,
    "front": 1.0,
    "work": 0.8,
    "admin": 0.5,
}


def _weighted_tile_choice(rng, weighted_candidates):
    cleaned = []
    total_weight = 0.0
    for tile, weight in tuple(weighted_candidates or ()):
        if not isinstance(tile, (list, tuple)) or len(tile) < 3:
            continue
        try:
            clean_weight = float(weight)
        except (TypeError, ValueError):
            continue
        if clean_weight <= 0.0:
            continue
        clean_tile = (int(tile[0]), int(tile[1]), int(tile[2]))
        cleaned.append((clean_tile, clean_weight))
        total_weight += clean_weight

    if not cleaned or total_weight <= 0.0:
        return None

    pick = rng.random() * total_weight
    cursor = 0.0
    for tile, weight in cleaned:
        cursor += weight
        if pick <= cursor:
            return tile
    return cleaned[-1][0]


def _property_room_preference_score(
    prop,
    room_kind,
    *,
    role="",
    intent="",
    building_category="",
    pulse_emphasis="",
):
    room_kind = str(room_kind or "").strip().lower()
    if not room_kind:
        return 0.0

    role = str(role or "").strip().lower()
    intent = str(intent or "").strip().lower()
    if not building_category:
        metadata = _property_metadata(prop)
        building_category = _location_building_category(
            str(metadata.get("archetype", "") or "").strip().lower(),
            storefront=bool(_property_is_storefront(prop)),
        )
    room_category = _room_category(room_kind, building_category=building_category)

    score = 0.0
    if intent == "working":
        if role in {"guard", "scout"}:
            score += _GUARD_ROOM_CATEGORY_WEIGHTS.get(room_category, 0.0)
        else:
            weights = _WORKING_ROOM_CATEGORY_WEIGHTS.get(
                building_category,
                _WORKING_ROOM_CATEGORY_WEIGHTS["general"],
            )
            score += weights.get(room_category, 0.0)
            if role == "worker" and room_category in {"front", "work"}:
                score += 0.45
            if role == "thief":
                score += {
                    "secure": 2.5,
                    "admin": 1.75,
                    "front": 0.5,
                }.get(room_category, 0.0)
    elif intent == "lounging":
        score += _LOUNGING_ROOM_CATEGORY_WEIGHTS.get(room_category, 0.0)
        if building_category == "residential" and room_category == "residential":
            score += 1.25
        if building_category in {"hospitality", "entertainment"} and room_category == "hospitality":
            score += 0.9

    emphasis = str(pulse_emphasis or "").strip().lower()
    if emphasis:
        if room_category == emphasis:
            score += 1.6
        elif emphasis == "front" and room_category == "hospitality":
            score += 0.45
        elif emphasis == "work" and room_category == "admin":
            score += 0.35
        elif emphasis == "secure" and room_category == "admin":
            score += 0.25

    return max(0.0, float(score))


def _frontage_pool_bias(*, role="", intent="", pulse_emphasis="", perimeter_bonus=0.0):
    role = str(role or "").strip().lower()
    intent = str(intent or "").strip().lower()
    pulse_emphasis = str(pulse_emphasis or "").strip().lower()
    try:
        perimeter_bonus = max(0.0, float(perimeter_bonus or 0.0))
    except (TypeError, ValueError):
        perimeter_bonus = 0.0

    bias = 0.0
    if role in {"guard", "scout"} and intent == "working":
        bias += 0.08

    if pulse_emphasis == "front":
        bias += 0.12
    elif pulse_emphasis in {"residential", "hospitality"} and intent == "lounging":
        bias += 0.05

    if bias > 0.0:
        bias += min(0.12, perimeter_bonus * 0.04)
    return max(0.0, min(0.42, float(bias)))


def _frontage_capacity(*, role="", intent="", pulse_emphasis="", perimeter_bonus=0.0):
    role = str(role or "").strip().lower()
    intent = str(intent or "").strip().lower()
    pulse_emphasis = str(pulse_emphasis or "").strip().lower()
    try:
        perimeter_bonus = max(0.0, float(perimeter_bonus or 0.0))
    except (TypeError, ValueError):
        perimeter_bonus = 0.0

    capacity = 1
    if role in {"guard", "scout"} and intent == "working":
        capacity = max(capacity, 2)
    if pulse_emphasis == "front" or perimeter_bonus >= 1.25:
        capacity += 1
    if perimeter_bonus >= 2.4:
        capacity += 1
    if perimeter_bonus >= 3.1:
        capacity += 1
    if intent == "lounging" and pulse_emphasis in {"residential", "hospitality"}:
        capacity += 1
    return max(1, min(4, int(capacity)))


def _frontage_tile_claims(sim, tiles, *, exclude_eid=None):
    cleaned_tiles = {
        (int(tile[0]), int(tile[1]), int(tile[2]))
        for tile in tuple(tiles or ())
        if isinstance(tile, (tuple, list)) and len(tile) >= 3
    }
    if not cleaned_tiles:
        return {}, 0

    claims = {tile: set() for tile in cleaned_tiles}
    positions = sim.ecs.get(Position)
    ais = sim.ecs.get(AI)

    for eid, pos in positions.items():
        if exclude_eid is not None and int(eid) == int(exclude_eid):
            continue
        tile = (int(pos.x), int(pos.y), int(pos.z))
        if tile in claims:
            claims[tile].add(int(eid))

    for eid, ai in ais.items():
        if exclude_eid is not None and int(eid) == int(exclude_eid):
            continue
        target = getattr(ai, "target", None)
        if not isinstance(target, (tuple, list)) or len(target) < 3:
            continue
        tile = (int(target[0]), int(target[1]), int(target[2]))
        if tile in claims:
            claims[tile].add(int(eid))

    claim_counts = {tile: len(eids) for tile, eids in claims.items()}
    total_claimed = len({eid for eids in claims.values() for eid in eids})
    return claim_counts, total_claimed


def _pick_property_roam_tile(sim, prop, eid, *, role="", intent=""):
    """Pick a random walkable tile inside or just outside the entrance of prop.

    Candidate pool:
      - Interior tiles not adjacent to any doorway/aperture
      - Outdoor perimeter tiles within radius 2 of the entry
    Interior tiles are weighted by room kind so workers drift toward rooms that
    match the building's trade and the current pulse of the site. Outdoor
    perimeter tiles stay in the pool so motion can still leak back toward the
    frontage. Falls back to the entry position when the footprint is missing or
    the property is empty.
    """
    rng = random.Random(f"{sim.seed}:{eid}:{sim.tick}:roam")
    pool_rng = random.Random(f"{sim.seed}:{eid}:{sim.tick}:roam-pool")
    entry = _property_focus_position(prop)
    metadata = _property_metadata(prop)
    footprint = metadata.get("footprint")
    actor_pos = sim.ecs.get(Position).get(eid)
    building_category = _location_building_category(
        str(metadata.get("archetype", "") or "").strip().lower(),
        storefront=bool(_property_is_storefront(prop)),
    )
    pulse = _building_pulse_snapshot(sim, prop=prop)
    pulse_emphasis = str(pulse.get("emphasis", "") or "").strip().lower()
    try:
        perimeter_bonus = max(0.0, float(pulse.get("perimeter_bonus", 0.0) or 0.0))
    except (TypeError, ValueError):
        perimeter_bonus = 0.0

    interior_weighted = []
    if isinstance(footprint, dict):
        try:
            left = int(footprint.get("left"))
            right = int(footprint.get("right"))
            top = int(footprint.get("top"))
            bottom = int(footprint.get("bottom"))
            base_z = int(prop.get("z", 0))
        except (TypeError, ValueError):
            left = right = top = bottom = base_z = None

        if left is not None:
            doorway_tiles = set()
            for aperture in _property_apertures(prop):
                ax, ay = int(aperture.get("x", 0)), int(aperture.get("y", 0))
                doorway_tiles.add((ax, ay))
                for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    doorway_tiles.add((ax + ddx, ay + ddy))
            if entry:
                ex, ey = entry[0], entry[1]
                doorway_tiles.add((ex, ey))
                for ddx, ddy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    doorway_tiles.add((ex + ddx, ey + ddy))

            floor_order = [base_z]
            if actor_pos:
                covered = sim.property_covering(actor_pos.x, actor_pos.y, actor_pos.z)
                if covered and covered.get("id") == prop.get("id"):
                    current_z = int(actor_pos.z)
                    floor_order = [current_z] + [z for z in floor_order if int(z) != current_z]

            for z in floor_order:
                all_inside = []
                for ty in range(top, bottom + 1):
                    for tx in range(left, right + 1):
                        if not sim.tilemap.is_walkable(tx, ty, z):
                            continue
                        covered = sim.property_covering(tx, ty, z)
                        if not (covered and covered.get("id") == prop.get("id")):
                            continue
                        all_inside.append((tx, ty, z))
                if not all_inside:
                    continue
                clear = [t for t in all_inside if (t[0], t[1]) not in doorway_tiles]
                interior = clear if clear else all_inside
                for tile in interior:
                    structure = sim.structure_at(tile[0], tile[1], tile[2]) if hasattr(sim, "structure_at") else None
                    room_kind = str((structure or {}).get("room_kind", "") or "").strip().lower()
                    weight = 1.0
                    if (tile[0], tile[1]) not in doorway_tiles:
                        weight += 0.35
                    weight += _property_room_preference_score(
                        prop,
                        room_kind,
                        role=role,
                        intent=intent,
                        building_category=building_category,
                        pulse_emphasis=pulse_emphasis,
                    )
                    interior_weighted.append((tile, weight))
                if interior_weighted:
                    break

    # Outdoor perimeter: walkable tiles just outside the entrance (radius 1-2)
    perimeter_weighted = []
    if entry:
        ex, ey, ez = entry
        perimeter_weight = 0.7
        if pulse_emphasis == "front":
            perimeter_weight += 0.9
        elif role in {"guard", "scout"} and str(intent or "").strip().lower() == "working":
            perimeter_weight += 0.35
        elif str(intent or "").strip().lower() == "lounging":
            perimeter_weight += 0.1
        perimeter_weight += perimeter_bonus
        for radius in range(1, 3):
            for ddx, ddy in ((radius, 0), (-radius, 0), (0, radius), (0, -radius)):
                nx, ny = ex + ddx, ey + ddy
                if not sim.tilemap.is_walkable(nx, ny, ez):
                    continue
                covered = sim.property_covering(nx, ny, ez)
                if covered and covered.get("id") == prop.get("id"):
                    continue  # inside, already in interior pool
                perimeter_weighted.append(((nx, ny, ez), perimeter_weight))

    if perimeter_weighted:
        claim_counts, total_claimed = _frontage_tile_claims(
            sim,
            [tile for tile, _weight in perimeter_weighted],
            exclude_eid=eid,
        )
        crowd_penalized = []
        for tile, weight in perimeter_weighted:
            crowd_penalty = 1.0 + (max(0, int(claim_counts.get(tile, 0))) * 1.4)
            crowd_penalized.append((tile, float(weight) / crowd_penalty))
        perimeter_weighted = crowd_penalized

        if interior_weighted:
            capacity = _frontage_capacity(
                role=role,
                intent=intent,
                pulse_emphasis=pulse_emphasis,
                perimeter_bonus=perimeter_bonus,
            )
            outside_bias = _frontage_pool_bias(
                role=role,
                intent=intent,
                pulse_emphasis=pulse_emphasis,
                perimeter_bonus=perimeter_bonus,
            )
            if total_claimed >= capacity:
                outside_bias = 0.0
            elif total_claimed == max(0, capacity - 1):
                outside_bias *= 0.35

            if outside_bias > 0.0 and pool_rng.random() < outside_bias:
                chosen = _weighted_tile_choice(rng, perimeter_weighted)
                if chosen is not None:
                    return chosen

            chosen = _weighted_tile_choice(rng, interior_weighted)
            if chosen is not None:
                return chosen

    chosen = _weighted_tile_choice(rng, interior_weighted + perimeter_weighted)
    return chosen or entry


_SOCIAL_VENUE_ARCHETYPES = frozenset({
    "bar", "cafe", "casino", "restaurant", "diner", "tavern", "club", "lounge",
    "park", "plaza", "market", "shop", "store", "pharmacy",
    "library", "gym", "barbershop", "salon",
})


def _pick_social_venue(sim, x, y, z, eid, own_prop_id=None, radius=12):
    """Return a (property, focus_position) pair for a nearby social venue.

    Scans properties_in_radius, prefers public storefronts or explicitly
    social archetypes, and excludes the NPC's own workplace.
    """
    rng = random.Random(f"{sim.seed}:{eid}:{sim.tick}:socialize")
    props = sim.properties_in_radius(x, y, z, r=radius)
    scored = []
    for prop in props:
        pid = prop.get("id")
        if pid and pid == own_prop_id:
            continue
        archetype = str(_property_metadata(prop).get("archetype", "") or "").strip().lower()
        is_public = _property_is_public(prop)
        is_store = _property_is_storefront(prop)
        focus = _property_focus_position(prop)
        if focus is None:
            continue
        if archetype in _SOCIAL_VENUE_ARCHETYPES:
            weight = 3.0
        elif is_public or is_store:
            weight = 1.5
        else:
            continue
        dist = _manhattan(x, y, focus[0], focus[1])
        if dist == 0:
            continue
        scored.append((prop, focus, weight / (1.0 + dist * 0.1)))
    if not scored:
        return None, None
    scored.sort(key=lambda r: r[2], reverse=True)
    top = scored[:max(1, len(scored) // 3)]
    chosen = rng.choice(top)
    return chosen[0], chosen[1]


from game.npc_intent_systems import NPCWillSystem



from game.systems_social import (
    EavesdropSystem,
    NPCSocialDynamicsSystem,
    SocialKnowledgeInfluenceSystem,
)



from game.npc_intent_systems import NPCInvestigateSystem



# ---------------------------------------------------------------------------
# World Events System — ambient events that fire without player input,
# creating time-limited decisions (exploit/avoid) and making the world feel
# alive.  State lives in sim.world_traits["world_events"].
# ---------------------------------------------------------------------------

_WORLD_EVENT_CATALOG = {
    "security_sweep": {
        "label": "Security Sweep",
        "duration_lo": 25,
        "duration_hi": 45,
        "weight": 20,
        "area_types": {"city"},
        "pressure_delta": 12,
        "trade_buy_mult": 1.0,
        "trade_sell_mult": 1.0,
        "observer_notice_delta": 2,
        "guard_count_lo": 2,
        "guard_count_hi": 4,
        "flavor_start": (
            "Armed patrols flood the district, checking credentials.",
            "Loudspeakers crackle: routine security sweep in progress.",
            "Checkpoint lights flare up across the block.",
        ),
        "flavor_end": (
            "The sweep winds down. Patrols thin out.",
            "Checkpoint lights go dark. The district exhales.",
        ),
    },
    "supply_shortage": {
        "label": "Supply Shortage",
        "duration_lo": 30,
        "duration_hi": 55,
        "weight": 18,
        "area_types": {"city"},
        "pressure_delta": 0,
        "trade_buy_mult": 1.35,
        "trade_sell_mult": 1.25,
        "flavor_start": (
            "Shelves are running thin. Merchants mark prices up overnight.",
            "Supply trucks haven't arrived. Locals are hoarding.",
            "A shortage grips the area — prices climb.",
        ),
        "flavor_end": (
            "Fresh stock trickles in. Prices begin to stabilize.",
            "The shortage eases as new shipments arrive.",
        ),
    },
    "black_market_window": {
        "label": "Black Market Window",
        "duration_lo": 18,
        "duration_hi": 32,
        "weight": 12,
        "area_types": {"city"},
        "pressure_delta": 5,
        "trade_buy_mult": 0.72,
        "trade_sell_mult": 0.80,
        "observer_notice_delta": -1,
        "spawn_market_stall": True,
        "flavor_start": (
            "Word spreads: an underground seller has set up nearby.",
            "Back-alley deals are being cut. Prices are low — but so is discretion.",
            "A hushed tip: cheap goods available, no questions asked.",
        ),
        "flavor_end": (
            "The underground seller packs up and vanishes.",
            "The black market window closes as quickly as it opened.",
        ),
    },
    "power_outage": {
        "label": "Power Outage",
        "duration_lo": 15,
        "duration_hi": 28,
        "weight": 14,
        "area_types": {"city"},
        "pressure_delta": -6,
        "trade_buy_mult": 1.0,
        "trade_sell_mult": 1.0,
        "fixture_light_mult": 0.18,
        "flavor_start": (
            "Lights flicker and die. The district plunges into darkness.",
            "A transformer blows somewhere. Emergency lighting only.",
            "Power cuts across the block. Security cameras go dark.",
        ),
        "flavor_end": (
            "Generators kick in. Lights stutter back to life.",
            "Power restored. The district blinks awake.",
        ),
    },
    "faction_clash": {
        "label": "Faction Clash",
        "duration_lo": 20,
        "duration_hi": 40,
        "weight": 10,
        "area_types": {"city"},
        "pressure_delta": 18,
        "trade_buy_mult": 1.15,
        "trade_sell_mult": 1.10,
        "flavor_start": (
            "Gunfire echoes between buildings. Two crews are settling a score.",
            "Rival factions face off in the street. Bystanders scatter.",
            "Tensions boil over — shouting, then shots.",
        ),
        "flavor_end": (
            "The clash burns itself out. Bodies and shell casings remain.",
            "Sirens wail. The faction fight is over — for now.",
        ),
    },
    "market_day": {
        "label": "Market Day",
        "duration_lo": 25,
        "duration_hi": 50,
        "weight": 16,
        "area_types": {"city"},
        "pressure_delta": -8,
        "trade_buy_mult": 0.88,
        "trade_sell_mult": 1.08,
        "observer_notice_delta": -1,
        "spawn_market_stall": True,
        "flavor_start": (
            "Stalls spring up along the road. Locals barter openly.",
            "A pop-up market fills the block with noise and colour.",
            "Vendors hawk wares, the crowd buzzing with energy.",
        ),
        "flavor_end": (
            "The market packs up. Quiet settles back in.",
            "Last stalls fold. The block returns to normal.",
        ),
    },
    "hunter_party": {
        "label": "Hunter Party",
        "duration_lo": 22,
        "duration_hi": 36,
        "weight": 14,
        "area_types": {"frontier", "wilderness"},
        "pressure_delta": 0,
        "trade_buy_mult": 1.0,
        "trade_sell_mult": 1.0,
        "flavor_start": (
            "Fresh boot prints and low voices mark a hunter party working the nearby wilds.",
            "A hunting crew has set a field rack and is trading stories over the day's haul.",
            "You catch the smell of game and woodsmoke: a hunter party is camped nearby.",
        ),
        "flavor_end": (
            "The hunter party shoulders their gear and slips back into the wilds.",
            "The hunting crew packs the rack and moves on before dark.",
        ),
    },
    "campout": {
        "label": "Campout",
        "duration_lo": 26,
        "duration_hi": 44,
        "weight": 12,
        "area_types": {"frontier", "wilderness", "coastal"},
        "pressure_delta": 0,
        "trade_buy_mult": 1.0,
        "trade_sell_mult": 1.0,
        "flavor_start": (
            "A small camp has gone up nearby, lanterns and low conversation carrying on the air.",
            "Someone has made a temporary camp in the open, with a fire ring and bedrolls.",
            "Camp smoke curls nearby: travelers are bedding down for a while.",
        ),
        "flavor_end": (
            "The campers stamp out the fire and clear the site.",
            "The camp breaks at first light, leaving only warm ash behind.",
        ),
    },
}

# Maximum simultaneous events and cooldown between rolls.
_WORLD_EVENT_MAX_ACTIVE = 3
_WORLD_EVENT_DURATION_SCALE = 4
_WORLD_EVENT_ROLL_INTERVAL = 180
_WORLD_EVENT_COOLDOWN_PER_CHUNK = 360
_WORLD_EVENT_PLAYER_REVEAL_RADIUS = 1


from game.systems_world_events import (
    _chunk_chebyshev_distance,
    _clear_world_event_revealed,
    _mark_world_event_revealed,
    _normalize_chunk_coord,
    _viewer_chunk_coord,
    _world_event_chunk_coord,
    _world_event_revealed_ids,
    _world_events_state,
    active_world_events_for_chunk,
    active_world_events_near_chunk,
    world_event_observer_notice_delta,
    world_event_trade_multipliers,
    world_event_visible_to_viewer,
    WorldEventsSystem,
)


class SuppressionSystem(System):
    """Accumulates suppression on NPCs from nearby fire, decays it each tick,
    and triggers surrender when an NPC is overwhelmed."""

    NEAR_MISS_RADIUS = 2
    SPIKE_DIRECT_HIT = 0.35
    SPIKE_NEAR_MISS = 0.12
    SPIKE_EXPLOSION = 0.28
    DECAY_RATE = 0.045
    SURRENDER_THRESHOLD = 0.88
    SURRENDER_BRAVERY_CAP = 0.38

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.rng = random.Random(f"{sim.seed}:suppression")
        self.sim.events.subscribe("entity_damaged", self.on_entity_damaged)
        self.sim.events.subscribe("projectile_impact", self.on_projectile_impact)
        self.sim.events.subscribe("explosion_triggered", self.on_explosion_triggered)
        self.runs_without_turn = True

    def on_entity_damaged(self, event):
        target_eid = event.data.get("target_eid")
        if target_eid is None or target_eid == self.player_eid:
            return
        suppression = self.sim.ecs.get(SuppressionState).get(target_eid)
        if suppression and not suppression.surrendered:
            suppression.spike(self.SPIKE_DIRECT_HIT, self.sim.tick)

    def on_projectile_impact(self, event):
        ix = event.data.get("x")
        iy = event.data.get("y")
        iz = event.data.get("z")
        source_eid = event.data.get("source_eid")
        if ix is None or iy is None:
            return
        positions = self.sim.ecs.get(Position)
        suppressions = self.sim.ecs.get(SuppressionState)
        for eid, suppression in suppressions.items():
            if eid == source_eid or eid == self.player_eid or suppression.surrendered:
                continue
            pos = positions.get(eid)
            if not pos or pos.z != iz:
                continue
            dist = _manhattan(pos.x, pos.y, ix, iy)
            if dist < 1 or dist > self.NEAR_MISS_RADIUS:
                continue
            intensity = self.SPIKE_NEAR_MISS * (1.0 - (dist / (self.NEAR_MISS_RADIUS + 1)))
            if intensity > 0.01:
                suppression.spike(intensity, self.sim.tick)

    def on_explosion_triggered(self, event):
        ex = event.data.get("x")
        ey = event.data.get("y")
        ez = event.data.get("z")
        radius = int(event.data.get("radius", 2))
        source_eid = event.data.get("source_eid")
        if ex is None or ey is None:
            return
        positions = self.sim.ecs.get(Position)
        suppressions = self.sim.ecs.get(SuppressionState)
        for eid, suppression in suppressions.items():
            if eid == source_eid or eid == self.player_eid or suppression.surrendered:
                continue
            pos = positions.get(eid)
            if not pos or pos.z != ez:
                continue
            dist = _manhattan(pos.x, pos.y, ex, ey)
            if dist > radius + 2:
                continue
            suppression.spike(self.SPIKE_EXPLOSION, self.sim.tick)

    def _count_downed_allies_near(self, eid, pos):
        socials = self.sim.ecs.get(NPCSocial)
        vitalities = self.sim.ecs.get(Vitality)
        social = socials.get(eid)
        if not social:
            return 0
        count = 0
        for bond_eid in social.bonds:
            v = vitalities.get(bond_eid)
            if v and v.downed:
                count += 1
        return count

    def _try_surrender(self, eid, suppression, traits, pos):
        if suppression.pressure < self.SURRENDER_THRESHOLD:
            return False
        if traits.bravery > self.SURRENDER_BRAVERY_CAP:
            return False
        downed_allies = self._count_downed_allies_near(eid, pos)
        # Low-bravery NPCs surrender when overwhelmed; downed allies make it easier.
        chance = 0.18 + (1.0 - traits.bravery) * 0.35 + (downed_allies * 0.15)
        if self.rng.random() > min(0.92, chance):
            return False

        suppression.surrendered = True
        suppression.surrender_tick = int(self.sim.tick)

        ais = self.sim.ecs.get(AI)
        ai = ais.get(eid)
        if ai:
            ai.state = "surrendered"
            ai.target = None
            ai.target_eid = None

        colliders = self.sim.ecs.get(Collider)
        collider = colliders.get(eid)
        if collider:
            collider.blocks = True

        # Drop weapon on the ground.
        loadouts = self.sim.ecs.get(WeaponLoadout)
        loadout = loadouts.get(eid)
        dropped_weapon = None
        if loadout and loadout.weapon_ids:
            weapon_id = loadout.current_weapon() or (loadout.weapon_ids[0] if loadout.weapon_ids else None)
            if weapon_id:
                dropped_weapon = weapon_id
                loadout.weapon_ids = [w for w in loadout.weapon_ids if w != weapon_id]
                if hasattr(loadout, "_current_index"):
                    loadout._current_index = 0

        self.sim.emit(Event(
            "npc_surrendered",
            eid=eid,
            x=pos.x,
            y=pos.y,
            z=pos.z,
            dropped_weapon=dropped_weapon,
        ))
        return True

    def update(self):
        suppressions = self.sim.ecs.get(SuppressionState)
        positions = self.sim.ecs.get(Position)
        traits_map = self.sim.ecs.get(NPCTraits)
        vitalities = self.sim.ecs.get(Vitality)
        ais = self.sim.ecs.get(AI)

        for eid, suppression in suppressions.items():
            if eid == self.player_eid:
                continue
            if suppression.surrendered:
                continue
            vitality = vitalities.get(eid)
            if vitality and vitality.downed:
                continue
            pos = positions.get(eid)
            if not pos:
                continue
            if not _detail_tick_allowed(self.sim, pos, eid, coarse_divisor=2):
                continue

            traits = traits_map.get(eid) or NPCTraits()

            was_pinned = suppression.pinned()
            was_shaken = suppression.shaken()

            # Attempt surrender before decay.
            if suppression.pressure >= self.SURRENDER_THRESHOLD:
                self._try_surrender(eid, suppression, traits, pos)
                if suppression.surrendered:
                    continue

            suppression.decay(self.DECAY_RATE, traits.bravery, traits.discipline)

            now_pinned = suppression.pinned()
            now_shaken = suppression.shaken()

            if now_pinned and not was_pinned:
                self.sim.emit(Event(
                    "npc_suppressed",
                    eid=eid,
                    level="pinned",
                    pressure=round(suppression.pressure, 2),
                    x=pos.x,
                    y=pos.y,
                    z=pos.z,
                ))
            elif now_shaken and not was_shaken and not now_pinned:
                self.sim.emit(Event(
                    "npc_suppressed",
                    eid=eid,
                    level="shaken",
                    pressure=round(suppression.pressure, 2),
                    x=pos.x,
                    y=pos.y,
                    z=pos.z,
                ))


from game.event_log_system import EventLogSystem



from game.render_system import RenderSystem
