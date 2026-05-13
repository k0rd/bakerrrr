import curses
import hashlib
import itertools
import json
import math
import random
import re
import textwrap
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
    creature_color_key as _appearance_creature_color_key,
    district_floor_color as _appearance_district_floor_color,
    district_floor_glyph as _appearance_district_floor_glyph,
    feature_tile_style as _appearance_feature_tile_style,
    ground_item_color as _appearance_ground_item_color,
    item_display_glyph as _appearance_item_display_glyph,
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
    item_market_bias,
    pick_career_for_workplace,
    store_supply_profile,
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
    build_known_locations_report as _report_runtime_build_known_locations_report,
    build_progress_report as _report_runtime_build_progress_report,
)
import game.report_debug_ui as _report_debug_ui
from game.semantic_catalog import get_runtime_semantic_catalog
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
from game.property_ingress import PropertyIngressRuntime
from game.overworld_runtime import (
    PlayerOverworldRuntime,
    _chunk_tuple,
    _overworld_center_semantic_id,
    _overworld_chunk_knowledge,
    _overworld_chunk_memory_state,
    _overworld_chunk_view,
    _overworld_edge_legend_lines as _shared_overworld_edge_legend_lines,
    _overworld_fill_semantic_id,
    _overworld_hud_lines as _shared_overworld_hud_lines,
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
from game.system_support.awareness_runtime import _watchers_for_position
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
from game.system_support.status_runtime import (
    _npc_status_metric_args,
    _status_int_offset,
    _status_modifier_total,
    _status_multiplier,
    _status_tick_step,
)
from game.service_runtime import (
    CASINO_GAME_SERVICE_IDS,
    TRANSIT_SERVICE_IDS,
    _casino_game_title,
    _chunk_site_kinds,
    _credit_amount_label,
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

def _int_or_default(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _float_or_default(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _tick_duration_label(sim, ticks):
    try:
        total_ticks = int(ticks)
    except (TypeError, ValueError):
        total_ticks = 0
    total_ticks = max(0, total_ticks)
    if total_ticks <= 0:
        return "0t"

    world_traits = getattr(sim, "world_traits", {})
    clock = world_traits.get("clock", {}) if isinstance(world_traits, dict) else {}
    try:
        ticks_per_hour = int(clock.get("ticks_per_hour", 600))
    except (TypeError, ValueError, AttributeError):
        ticks_per_hour = 600
    ticks_per_hour = max(60, ticks_per_hour)

    hours = total_ticks / float(ticks_per_hour)
    if hours >= 1.0:
        rounded = round(hours, 1)
        if abs(rounded - int(rounded)) < 0.05:
            return f"{int(round(rounded))}h"
        return f"{rounded:.1f}h"
    return f"{total_ticks}t"


def _grid_distance(ax, ay, bx, by):
    return max(abs(ax - bx), abs(ay - by))


def _clamp(value, lo=0.0, hi=100.0):
    return max(lo, min(hi, value))


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
    instance = loadout.weapon_instances.get(weapon_id, {})
    if not isinstance(instance, dict):
        instance = {}
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
    ai = sim.ecs.get(AI).get(eid)
    if not ai or str(ai.state or "").strip().lower() not in THREAT_STATES:
        return False
    if _entity_is_downed(sim, eid):
        return False
    player_pos = sim.ecs.get(Position).get(player_eid) if player_eid is not None else None
    pos = sim.ecs.get(Position).get(eid)
    if player_pos and pos and int(pos.z) != int(player_pos.z):
        return False
    return True


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
    if weapon_id not in loadout.reserve_ammo:
        return None
    try:
        return int(loadout.reserve_ammo.get(weapon_id, 0))
    except (TypeError, ValueError):
        return None


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


def _active_contractor_record(sim, npc_eid, *, ally_eid=None, jobs=None):
    if sim is None or npc_eid is None:
        return None
    contractors = getattr(sim, "contractors", {})
    if not isinstance(contractors, dict):
        return None
    tick = int(getattr(sim, "tick", 0))
    job_keys = None
    if jobs is not None:
        job_keys = {
            str(job).strip().lower()
            for job in (jobs if isinstance(jobs, (set, tuple, list)) else (jobs,))
            if str(job).strip()
        }
    for key, rec in contractors.items():
        try:
            same_npc = int(key) == int(npc_eid)
        except (TypeError, ValueError):
            same_npc = key == npc_eid
        if not same_npc or not isinstance(rec, dict):
            continue
        if int(rec.get("until", 0) or 0) <= tick:
            continue
        job = str(rec.get("job", "") or "").strip().lower()
        if job_keys is not None and job not in job_keys:
            continue
        if ally_eid is not None:
            rec_ally = rec.get("ally_eid", getattr(sim, "player_eid", None))
            try:
                same_ally = int(rec_ally) == int(ally_eid)
            except (TypeError, ValueError):
                same_ally = rec_ally == ally_eid
            if not same_ally:
                continue
        return rec
    return None


def _contractor_order_target_from_record(rec):
    if not isinstance(rec, dict):
        return None
    target = rec.get("order_target")
    if not isinstance(target, (tuple, list)) or len(target) < 3:
        return None
    try:
        return (int(target[0]), int(target[1]), int(target[2]))
    except (TypeError, ValueError):
        return None


def _dialog_backup_mark_from_state(state):
    if not isinstance(state, dict):
        return {}
    mark = state.get("backup_cursor_mark")
    if not isinstance(mark, dict):
        return {}
    try:
        x = int(mark.get("x", 0))
        y = int(mark.get("y", 0))
        z = int(mark.get("z", 0))
    except (TypeError, ValueError):
        return {}
    target_eid = mark.get("target_eid")
    if target_eid is not None:
        try:
            target_eid = int(target_eid)
        except (TypeError, ValueError):
            target_eid = None
    return {
        "x": x,
        "y": y,
        "z": z,
        "label": str(mark.get("label", "")).strip(),
        "target_eid": target_eid,
        "target_name": str(mark.get("target_name", "")).strip(),
    }


def _dialog_map_marker_for_player(sim, player_eid, x, y, z):
    player_pos = sim.ecs.get(Position).get(player_eid) if sim is not None else None
    if player_pos and int(player_pos.z) == int(z):
        return f"{int(x)},{int(y)}"
    return f"{int(x)},{int(y)},z{int(z)}"


def _dialog_backup_cursor_payload(sim, player_eid, npc_eid, x, y, z):
    if sim is None or player_eid is None:
        return {}
    try:
        x = int(x)
        y = int(y)
        z = int(z)
    except (TypeError, ValueError):
        return {}
    player_pos = sim.ecs.get(Position).get(player_eid)
    if not player_pos or int(player_pos.z) != int(z):
        return {}

    target_eid = _first_blocking_entity_at(
        sim,
        x,
        y,
        z,
        exclude_eid=player_eid,
    )
    if target_eid in {None, npc_eid}:
        target_eid = None
    elif _active_contractor_record(
        sim,
        target_eid,
        ally_eid=player_eid,
        jobs={"backup", "party"},
    ) is not None:
        target_eid = None

    target_name = _entity_display_name(sim, target_eid, title_case=True) if target_eid is not None else ""
    return {
        "x": x,
        "y": y,
        "z": z,
        "label": _dialog_map_marker_for_player(sim, player_eid, x, y, z),
        "target_eid": target_eid,
        "target_name": target_name,
    }


def _observer_is_active_contractor_ally(sim, observer_eid, offender_eid):
    return _active_contractor_record(
        sim,
        observer_eid,
        ally_eid=offender_eid,
        jobs={"backup", "party"},
    ) is not None


def _observer_turns_blind_eye_to_offense(sim, observer_eid, offender_eid, *, action="", context="ordinary", offense_score=0):
    if sim is None or observer_eid is None or offender_eid is None:
        return False
    if observer_eid == offender_eid:
        return True
    if _observer_is_active_contractor_ally(sim, observer_eid, offender_eid):
        return True
    if offender_eid != getattr(sim, "player_eid", None):
        return False

    context_key = str(context or "ordinary").strip().lower() or "ordinary"
    action_key = str(action or "").strip().lower()
    if context_key in OFFICIAL_REPORTABLE_OFFENSE_CONTEXTS:
        return False
    if action_key in {"fire_weapon", "vehicle_theft", "tamper"}:
        return False

    social = sim.ecs.get(NPCSocial).get(observer_eid)
    if not social:
        return False
    bond = social.bonds.get(offender_eid)
    if not isinstance(bond, dict):
        return False

    trust = float(bond.get("trust", 0.0) or 0.0)
    closeness = float(bond.get("closeness", 0.0) or 0.0)
    protectiveness = float(bond.get("protectiveness", 0.0) or 0.0)
    relation = str(bond.get("kind", "") or "").strip().lower()
    rapport = (trust * 0.5) + (closeness * 0.35) + (protectiveness * 0.15)
    if relation in {"family", "partner"}:
        rapport = max(rapport, 0.82)
    if trust < 0.58 or closeness < 0.44:
        return False

    max_score = 12 + int(round(rapport * 14.0))
    if relation in {"family", "partner", "friend"}:
        max_score += 2
    return int(offense_score or 0) <= max_score


def _entities_have_family_bond(sim, first_eid, second_eid):
    if sim is None or first_eid is None or second_eid is None:
        return False

    socials = sim.ecs.get(NPCSocial)
    for source_eid, other_eid in ((first_eid, second_eid), (second_eid, first_eid)):
        social = socials.get(source_eid)
        if not social:
            continue
        bond = social.bonds.get(other_eid)
        if not isinstance(bond, dict):
            continue
        if str(bond.get("kind", "") or "").strip().lower() == "family":
            return True
    return False


def _defender_excuses_window_shot(sim, defender_eid, offender_eid, prop, *, defender_reason=""):
    if sim is None or defender_eid is None or offender_eid is None or not isinstance(prop, dict):
        return False
    if defender_eid == offender_eid:
        return True

    positions = sim.ecs.get(Position)
    offender_pos = positions.get(offender_eid)
    if offender_pos:
        offender_access = _evaluate_property_access(
            sim,
            offender_eid,
            prop,
            x=offender_pos.x,
            y=offender_pos.y,
            z=offender_pos.z,
        )
    else:
        offender_access = _evaluate_property_access(
            sim,
            offender_eid,
            prop,
            x=prop.get("x"),
            y=prop.get("y"),
            z=prop.get("z", 0),
        )

    offender_reason = str(getattr(offender_access, "standing_reason", "") or "").strip().lower()
    defender_reason = str(defender_reason or "").strip().lower()
    if offender_reason in {"owner", "employee"} and defender_reason in {"owner", "employee"}:
        return True
    if _entities_have_family_bond(sim, defender_eid, offender_eid):
        return True
    return False

def _noise_merits_attention(sim, observer_eid, source_eid, x, y, z, cause):
    cause = str(cause or "").strip().lower()
    if source_eid is not None and _observer_is_active_contractor_ally(sim, observer_eid, source_eid):
        return False
    if cause not in QUIET_NOISE_CAUSES:
        return True

    if source_eid is None:
        return False

    prop = _property_covering(sim, x, y, z)
    if not prop:
        return False

    access = _evaluate_property_access(sim, source_eid, prop, x=x, y=y, z=z)
    if not access.inside_bounds or access.severity_score <= 0:
        return False

    positions = sim.ecs.get(Position)
    observer_pos = positions.get(observer_eid)
    if not observer_pos:
        return False

    _, claim_reason = _property_claim_reason(
        sim,
        observer_eid,
        prop,
        x=observer_pos.x,
        y=observer_pos.y,
        z=observer_pos.z,
        min_standing=0.58,
    )
    if claim_reason:
        return True

    ais = sim.ecs.get(AI)
    ai = ais.get(observer_eid)
    role = str(getattr(ai, "role", "") or "").strip().lower()
    if role in {"guard", "scout"}:
        return True

    justices = sim.ecs.get(JusticeProfile)
    justice = justices.get(observer_eid)
    if not justice:
        return False
    if justice.enforce_all:
        return True

    law_drive = (_justice_level(justice) * 0.65) + (_crime_sensitivity(justice) * 0.35)
    threshold = 0.8 if access.severity_label == "suspicious" else 0.68
    return law_drive >= threshold

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
            witnesses = _watchers_for_position(
                sim,
                target_x,
                target_y,
                target_z,
                exclude_eid=eid,
                offender_eid=eid,
            )
            offense_score = max(
                _offense_score_for_action(action, context="ordinary"),
                10 if access.severity_label == "suspicious" else _offense_score_for_action(action, context="trespass"),
            )
            if access.severity_label == "serious_trespass":
                offense_score = min(100, offense_score + 8)
            if ingress.breach_severity > 0.0:
                offense_score = min(100, offense_score + int(round(ingress.breach_severity * 12.0)))

            sim.emit(Event(
                "property_trespass",
                offender_eid=eid,
                property_id=prop["id"],
                owner_eid=prop.get("owner_eid"),
                x=target_x,
                y=target_y,
                z=target_z,
                witnessed=bool(witnesses),
                witness_count=len(witnesses),
                witnesses=tuple(witnesses[:4]),
                access_level=access.access_level,
                severity_score=access.severity_score,
                severity_label=access.severity_label,
                standing_reason=access.standing_reason,
                currently_open=access.currently_open,
                current_hour=access.current_hour,
                ingress_kind=ingress.ingress_kind,
                aperture_kind=ingress.aperture_kind,
                ingress_method=_ingress_method_from_context(
                    ingress.ingress_kind,
                    ingress.aperture_kind,
                ),
                breach_severity=ingress.breach_severity,
            ))
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


def _world_trait_claim_value(data):
    if not isinstance(data, dict):
        return ""
    value = data.get("claimed_value")
    if value in (None, ""):
        value = data.get("claimed_coat", "")
    return str(value).strip().lower()


def _dialogue_guard_grace_state(sim):
    state = getattr(sim, "dialogue_guard_grace", None)
    if not isinstance(state, dict):
        state = {}
        sim.dialogue_guard_grace = state
    return state


def _dialogue_guard_grace_key(npc_eid, prop_or_property_id):
    if isinstance(prop_or_property_id, dict):
        property_id = str(prop_or_property_id.get("id", "")).strip()
    else:
        property_id = str(prop_or_property_id or "").strip()
    if not property_id:
        return None
    try:
        npc_key = int(npc_eid)
    except (TypeError, ValueError):
        npc_key = npc_eid
    return (npc_key, property_id)


def _dialogue_guard_grace_active(sim, npc_eid, prop_or_property_id):
    key = _dialogue_guard_grace_key(npc_eid, prop_or_property_id)
    if key is None:
        return False
    state = _dialogue_guard_grace_state(sim)
    entry = state.get(key)
    if not isinstance(entry, dict):
        return False
    try:
        expires_tick = int(entry.get("expires_tick", -1))
    except (TypeError, ValueError):
        expires_tick = -1
    if expires_tick < int(getattr(sim, "tick", 0)):
        state.pop(key, None)
        return False
    return True


def _grant_dialogue_guard_grace(sim, npc_eid, prop_or_property_id, *, duration=18, tactic=""):
    key = _dialogue_guard_grace_key(npc_eid, prop_or_property_id)
    if key is None:
        return False
    state = _dialogue_guard_grace_state(sim)
    duration = max(1, int(duration))
    state[key] = {
        "expires_tick": int(getattr(sim, "tick", 0)) + duration,
        "property_id": key[1],
        "tactic": str(tactic or "").strip().lower(),
    }
    return True


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


def _world_trait_claim_text(topic, claim_value):
    topic = str(topic or "").strip().lower()
    claim = str(claim_value or "").replace("_", " ").strip()
    if not claim:
        claim = "unknown"

    if topic == "cat_toxin_coat":
        return f"{claim} cats are poisonous."
    if topic == "contamination_taxonomy":
        return f"{claim} animals are contaminated this cycle."
    if topic == "illness_human_role":
        return f"{claim} groups are carrying an illness."
    if topic == "war_human_role":
        return f"{claim} groups are gearing for conflict."
    if topic == "blessing_taxonomy":
        return f"{claim} animals are said to be lucky this run."
    return f"{topic.replace('_', ' ')} -> {claim}."


def _path_next_step(sim, eid, sx, sy, tx, ty, z, max_nodes=512):
    if sx == tx and sy == ty:
        return None

    start = (sx, sy)
    goal = (tx, ty)

    queue = deque([start])
    parents = {start: None}
    best = start
    best_score = _grid_distance(sx, sy, tx, ty)

    while queue and len(parents) < max_nodes:
        cx, cy = queue.popleft()

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

            parents[node] = (cx, cy)
            queue.append(node)

            score = _grid_distance(nx, ny, tx, ty)
            if score < best_score:
                best = node
                best_score = score

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


def _infrastructure_target_property(sim, prop):
    if not isinstance(prop, dict):
        return None

    linked_property_id = _property_linked_property_id(prop)
    if linked_property_id:
        target = sim.properties.get(linked_property_id)
        if target is not None:
            return target

    linked_building_id = _property_linked_building_id(prop)
    if not linked_building_id:
        return None

    for candidate in sim.properties.values():
        if str(candidate.get("kind", "")).strip().lower() != "building":
            continue
        if _building_id_from_property(candidate) == linked_building_id:
            return candidate
    return None


def _infrastructure_role_label(role):
    role_key = str(role or "").strip().lower()
    return {
        "access_panel": "access panel",
        "bones_stash": "stash",
        "security_post": "security post",
        "service_terminal": "service terminal",
    }.get(role_key, role_key.replace("_", " "))


def _property_interaction_modes(sim, prop, viewer_eid=None):
    if not isinstance(prop, dict):
        return ()

    access = _evaluate_property_access(sim, viewer_eid, prop)
    modes = []
    infrastructure_role = _property_infrastructure_role(prop)
    if infrastructure_role == "access_panel":
        modes.append("panel")
    elif infrastructure_role == "security_post":
        modes.append("security")

    if _property_is_storefront(prop) and access.can_use_services:
        service = _storefront_service_profile(sim, prop)
        if service.get("available"):
            modes.append("trade")

    services = set(_finance_services_for_property(prop))
    if "banking" in services and access.can_use_services:
        modes.append("banking")
    if "insurance" in services and access.can_use_services:
        modes.append("insurance")
    for site_service in _site_services_for_property(prop):
        if access.can_use_services:
            modes.append(site_service)

    if viewer_eid is not None:
        owner_eid = prop.get("owner_eid")
        if owner_eid == viewer_eid or _property_is_public(prop) or access.standing >= 0.45:
            modes.append("inspect")

    return tuple(modes)


def _property_access_summary(sim, prop, viewer_eid=None):
    access_modes = [
        mode
        for mode in _property_interaction_modes(sim, prop, viewer_eid=viewer_eid)
        if mode != "inspect"
    ]
    if not access_modes:
        return ""
    return ",".join(access_modes)


def _access_prep_detail_lines(sim, viewer_eid, prop, *, controller=None, reveal_tier=None):
    if not isinstance(prop, dict) or str(prop.get("kind", "")).strip().lower() != "building":
        return ()

    if controller is None:
        controller = _property_access_controller(sim, prop)
    if not isinstance(controller, dict):
        return ()

    if reveal_tier is None:
        terms = _access_prep_skill_terms(sim, viewer_eid)
        reveal_tier = _int_or_default(terms.get("reveal_tier"), 0)
    reveal_tier = max(0, int(reveal_tier))
    if reveal_tier <= 0:
        return ()

    lines = []
    detail_bits = []
    controller_kind = str(controller.get("kind", "") or "").strip().lower()
    if controller_kind and controller_kind != "none":
        detail_bits.append("ctrl:" + controller_kind.replace("_", " "))
    mode_text = _dialogue_credential_mode_text(controller.get("credential_mode"))
    if mode_text:
        detail_bits.append("mode:" + mode_text)
    hours_text = _dialogue_hours_text(controller.get("opening_window"))
    if hours_text:
        detail_bits.append("hours:" + hours_text)
    requirement = _controller_access_requirement_text(controller)
    if requirement:
        detail_bits.append("req:" + requirement)
    if detail_bits:
        lines.append("Prep detail: " + "  ".join(detail_bits))

    if reveal_tier < 2:
        return tuple(lines)

    metadata = _property_metadata(prop)
    followup_bits = []
    panel_id = str(metadata.get("access_panel_property_id", "") or "").strip()
    if panel_id and sim.properties.get(panel_id):
        followup_bits.append("panel:street")
    terminal_id = str(metadata.get("service_terminal_property_id", "") or "").strip()
    if terminal_id:
        terminal = sim.properties.get(terminal_id)
        if isinstance(terminal, dict):
            terminal_services = [
                str(service).strip().lower()
                for service in list(_property_services(terminal) or ())
                if str(service).strip()
            ]
            if terminal_services:
                followup_bits.append("terminal:" + ",".join(terminal_services[:3]))
            else:
                followup_bits.append("terminal:street")

    alternate_labels = []
    ordinary_count = 0
    for aperture in _property_apertures(prop):
        kind = str(aperture.get("kind", "") or "").strip().lower()
        ordinary = bool(aperture.get("ordinary"))
        if ordinary:
            ordinary_count += 1
            continue
        label = kind.replace("_", " ").strip()
        if label and label not in alternate_labels:
            alternate_labels.append(label)
    if alternate_labels:
        followup_bits.append("alternates:" + _dialogue_human_join(alternate_labels[:3]))
    elif ordinary_count > 0:
        if ordinary_count == 1:
            followup_bits.append("entry:ordinary door")
        else:
            followup_bits.append(f"entry:{ordinary_count} ordinary doors")

    if followup_bits:
        lines.append("Prep detail: " + "  ".join(followup_bits))
    return tuple(lines)


def _property_contact_lead(sim, prop, relation, viewer_eid=None):
    if not prop:
        return ""

    relation = str(relation or "linked").strip().lower() or "linked"
    relation_text = {
        "workplace": "they work at",
        "owner": "they own",
    }.get(relation, relation.replace("_", " "))
    name = str(prop.get("name", prop.get("id", "property"))).strip() or "property"
    access = _property_access_level(prop)
    access_modes = _property_access_summary(sim, prop, viewer_eid=viewer_eid)
    if access_modes:
        return f"Lead: {relation_text} {name} ({access}; access:{access_modes})."
    return f"Lead: {relation_text} {name} ({access})."


def _property_contact_benefits(prop):
    if not isinstance(prop, dict):
        return ()

    benefits = set()
    if _property_is_storefront(prop):
        benefits.update({"trade_buy_discount", "trade_sell_bonus"})

    services = set(_finance_services_for_property(prop))
    if "insurance" in services or "banking" in services:
        benefits.add("insurance_discount")

    if not _property_is_public(prop):
        benefits.add("soft_access")
    elif not benefits:
        benefits.add("known_name")

    return tuple(sorted(benefits))


def _property_contact_entry(sim, viewer_eid, prop):
    if viewer_eid is None or not prop:
        return None

    ledger = sim.ecs.get(ContactLedger).get(viewer_eid)
    if not ledger:
        return None
    return ledger.property_entry(prop["id"])


def _person_contact_entry(sim, viewer_eid, person_eid):
    if viewer_eid is None or person_eid is None:
        return None

    ledger = sim.ecs.get(ContactLedger).get(viewer_eid)
    if not ledger:
        return None
    return ledger.person_entry(person_eid)


def _contact_benefit_labels(benefits):
    benefits = {str(bit).strip().lower() for bit in benefits if str(bit).strip()}
    labels = []
    if "trade_buy_discount" in benefits or "trade_sell_bonus" in benefits:
        labels.append("trade terms")
    if "insurance_discount" in benefits:
        labels.append("policy rates")
    if "soft_access" in benefits and ("trade terms" in labels or "policy rates" in labels):
        labels.append("soft access")
    if "soft_access" in benefits and not labels:
        labels.append("local name")
    return labels


def _property_contact_hint(sim, viewer_eid, prop):
    entry = _property_contact_entry(sim, viewer_eid, prop)
    if not entry:
        return ""

    source_eid = entry.get("source_eid")
    source_name = _entity_display_name(sim, source_eid, title_case=True) if source_eid is not None else ""
    standing = float(entry.get("standing", 0.0))
    benefits = entry.get("benefits", ())
    labels = _contact_benefit_labels(benefits)

    if labels == ["local name"]:
        if source_name:
            lead = f"contact:{source_name} knows people here"
        else:
            lead = "contact:someone knows people here"
    elif source_name:
        lead = f"contact:{source_name} can vouch here"
    else:
        lead = "contact:someone can vouch here"

    if labels:
        lead += f" ({', '.join(labels)})"
    elif standing >= 0.7:
        lead += " (solid local lead)"
    return lead


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


def _property_render_style(prop, active_quest_target=None):
    appearance = _appearance_property_render_snapshot(
        prop,
        active_quest_target=active_quest_target,
    )
    return appearance.glyph, appearance.color


def _item_display_glyph(item_def):
    return _appearance_item_display_glyph(item_def)


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


def _ground_item_color(item_def):
    return _appearance_ground_item_color(item_def)


def _item_reference_semantic_id(item_def):
    catalog = get_runtime_semantic_catalog()
    color_key = _ground_item_color(item_def)
    semantic_key = str(color_key or "").strip()
    semantics = getattr(catalog, "semantics", {})
    if semantic_key and isinstance(semantics, dict) and semantic_key in semantics:
        return semantic_key
    glyph = _item_display_glyph(item_def)
    return catalog.semantic_id_for(glyph, color_key, preferred_categories=("items",))


def _segment(text, color=None, attrs=0, **extras):
    segment = {
        "text": str(text),
        "color": color,
        "attrs": int(attrs or 0),
    }
    for key, value in extras.items():
        segment[str(key)] = value
    return segment


def _segments_text(segments):
    return "".join(str(segment.get("text", "")) for segment in segments or () if isinstance(segment, dict))


def _rich_line(segments, text=None):
    normalized = []
    for segment in segments or ():
        if not isinstance(segment, dict):
            continue
        seg_text = str(segment.get("text", ""))
        if not seg_text:
            continue
        extras = {
            key: value
            for key, value in segment.items()
            if key not in {"text", "color", "attrs"}
        }
        normalized.append(_segment(
            seg_text,
            color=segment.get("color"),
            attrs=segment.get("attrs", 0),
            **extras,
        ))
    plain = str(text) if text is not None else _segments_text(normalized)
    return {
        "text": plain,
        "segments": normalized,
    }


def _line_text(line):
    if isinstance(line, dict):
        return str(line.get("text", ""))
    return str(line)


def _line_segments(line):
    if isinstance(line, dict):
        segments = line.get("segments")
        if isinstance(segments, list):
            return segments
    return None


LOG_PRIORITY_LOW = 0
LOG_PRIORITY_NORMAL = 1
LOG_PRIORITY_HIGH = 2
LOG_PRIORITY_CRITICAL = 3

LOG_FILTER_PRESETS = (
    {
        "id": "all",
        "label": "All",
        "channels": None,
        "min_priority": LOG_PRIORITY_LOW,
    },
    {
        "id": "priority",
        "label": "Priority",
        "channels": None,
        "min_priority": LOG_PRIORITY_HIGH,
    },
    {
        "id": "mission",
        "label": "Mission",
        "channels": {"mission", "opportunity"},
        "min_priority": LOG_PRIORITY_LOW,
    },
    {
        "id": "combat",
        "label": "Combat/Aggro",
        "channels": {"combat", "alerts"},
        "min_priority": LOG_PRIORITY_LOW,
    },
    {
        "id": "status",
        "label": "Status",
        "channels": {"status"},
        "min_priority": LOG_PRIORITY_LOW,
    },
)


def _line_channel(line):
    if isinstance(line, dict):
        value = str(line.get("channel", "general") or "general").strip().lower()
        return value or "general"
    return "general"


def _line_priority(line):
    if isinstance(line, dict):
        try:
            return int(line.get("priority", LOG_PRIORITY_NORMAL))
        except (TypeError, ValueError):
            return LOG_PRIORITY_NORMAL
    return LOG_PRIORITY_NORMAL


def _line_tick(line):
    if isinstance(line, dict):
        value = line.get("tick")
        try:
            return None if value is None else int(value)
        except (TypeError, ValueError):
            return None
    return None


def _line_sequence(line):
    if isinstance(line, dict):
        try:
            return int(line.get("sequence", 0))
        except (TypeError, ValueError):
            return 0
    return 0


def _log_filter_spec(filter_id):
    current = str(filter_id or "all").strip().lower() or "all"
    for spec in LOG_FILTER_PRESETS:
        if spec["id"] == current:
            return spec
    return LOG_FILTER_PRESETS[0]


def _log_filter_ids():
    return [spec["id"] for spec in LOG_FILTER_PRESETS]


def _log_filter_label(filter_id):
    return _log_filter_spec(filter_id)["label"]


def _cycle_log_filter_id(filter_id, step=1):
    filter_ids = _log_filter_ids()
    if not filter_ids:
        return "all"
    current = str(filter_id or "all").strip().lower() or "all"
    try:
        index = filter_ids.index(current)
    except ValueError:
        index = 0
    return filter_ids[(index + int(step)) % len(filter_ids)]


def _sorted_log_lines(lines):
    return sorted(
        list(lines or ()),
        key=lambda line: (
            -1 if _line_tick(line) is None else _line_tick(line),
            _line_priority(line),
            _line_sequence(line),
        ),
    )


def _line_matches_log_filter(line, filter_id):
    spec = _log_filter_spec(filter_id)
    if _line_priority(line) < int(spec.get("min_priority", LOG_PRIORITY_LOW)):
        return False
    channels = spec.get("channels")
    if channels is not None and _line_channel(line) not in set(channels):
        return False
    return True


def _filtered_log_lines(lines, filter_id):
    return [line for line in _sorted_log_lines(lines) if _line_matches_log_filter(line, filter_id)]


def _log_prefix(line):
    priority = _line_priority(line)
    if priority >= LOG_PRIORITY_CRITICAL:
        return "!! "
    if priority >= LOG_PRIORITY_HIGH:
        return "! "
    return "- "


def _log_display_line(line):
    segments = _line_segments(line)
    if segments:
        return _rich_line(segments, text=_line_text(line))

    prefix = _log_prefix(line)
    priority = _line_priority(line)
    if priority >= LOG_PRIORITY_CRITICAL:
        prefix_color = "projectile"
    elif priority >= LOG_PRIORITY_HIGH:
        prefix_color = "property_asset"
    else:
        prefix_color = "building_edge"
    prefix_attrs = getattr(curses, "A_BOLD", 0) if priority >= LOG_PRIORITY_HIGH else 0
    prefixed_segments = [
        _segment(prefix, color=prefix_color, attrs=prefix_attrs),
        _segment(_line_text(line)),
    ]
    return _rich_line(prefixed_segments, text=prefix + _line_text(line))


def _hud_log_lines(lines, filter_id, budget):
    budget = max(0, int(budget))
    if budget <= 0:
        return []

    filtered = list(_filtered_log_lines(lines, filter_id))
    if not filtered:
        return []

    indexed = list(enumerate(filtered))
    recent_budget = indexed[-budget:]
    recent_indexes = {idx for idx, _line in recent_budget}
    recent_min_priority = min(
        (_line_priority(line) for _idx, line in recent_budget),
        default=LOG_PRIORITY_LOW,
    )
    sticky_indexes = []
    sticky_limit = min(2, budget)
    sticky_window = indexed[-max(budget * 4, 12):]
    for idx, line in reversed(sticky_window):
        line_priority = _line_priority(line)
        if line_priority < LOG_PRIORITY_HIGH:
            continue
        if idx in recent_indexes or idx in sticky_indexes:
            continue
        if line_priority <= recent_min_priority:
            continue
        sticky_indexes.insert(0, idx)
        if len(sticky_indexes) >= sticky_limit:
            break

    selected_indexes = list(sticky_indexes)
    for idx, _line in recent_budget:
        if idx not in selected_indexes:
            selected_indexes.append(idx)

    sticky_set = set(sticky_indexes)
    while len(selected_indexes) > budget:
        removed = False
        for pos, idx in enumerate(selected_indexes):
            if idx in sticky_set:
                continue
            del selected_indexes[pos]
            removed = True
            break
        if not removed:
            selected_indexes = selected_indexes[-budget:]
            break
    return [filtered[idx] for idx in selected_indexes]


def _line_with_prefix(line, prefix):
    prefix = str(prefix)
    segments = _line_segments(line)
    if not segments:
        return prefix + _line_text(line)
    prefixed = [_segment(prefix)]
    prefixed.extend(segments)
    return _rich_line(prefixed, text=prefix + _line_text(line))


def _line_with_suffix(line, suffix):
    suffix = str(suffix)
    if not suffix:
        return line
    segments = _line_segments(line)
    if not segments:
        return _line_text(line) + suffix
    appended = list(segments)
    appended.append(_segment(suffix))
    return _rich_line(appended, text=_line_text(line) + suffix)


def _legend_line(text, glyph=None, color=None, prefix="", attrs=0, semantic_id=None):
    segments = []
    plain = ""
    prefix = str(prefix)
    if prefix:
        segments.append(_segment(prefix))
        plain += prefix
    glyph_text = str(glyph)[:1] if glyph not in (None, "") else ""
    if glyph_text:
        extras = {"inline_glyph": True}
        if semantic_id:
            extras["semantic_id"] = str(semantic_id)
        segments.append(_segment(glyph_text, color=color, attrs=attrs, **extras))
        plain += glyph_text
        if text:
            segments.append(_segment(" "))
            plain += " "
    text = str(text)
    if text:
        segments.append(_segment(text))
        plain += text
    return _rich_line(segments, text=plain)


def _bullet_display_line(text, *, bullet="-", bullet_color="building_edge", text_color=None):
    text = str(text or "").strip()
    if not text:
        return ""
    bold = getattr(curses, "A_BOLD", 0)
    segments = [
        _segment(f"{str(bullet)[:1]} ", color=bullet_color, attrs=bold),
        _segment(text, color=text_color),
    ]
    return _rich_line(segments, text=f"{str(bullet)[:1]} {text}")


def _known_location_summary_bit_color(bit):
    label = str(bit or "").strip().lower()
    if not label:
        return None
    if "confirmed" in label:
        return "property_service"
    if "owned" in label:
        return "player"
    if label.endswith("lead") or "lead" in label:
        return "objective"
    if label.startswith("services "):
        return "property_service"
    if "vehicle" in label:
        return "vehicle_player"
    return "human"


def _known_location_summary_line(row):
    row = row if isinstance(row, dict) else {}
    confidence = int(round(float(row.get("confidence", 0.0)) * 100.0))
    summary_bits = [
        str(bit).strip()
        for bit in row.get("summary_bits", ())
        if str(bit).strip()
    ]
    bold = getattr(curses, "A_BOLD", 0)
    segments = [
        _segment(f"{confidence}% confident", color="player", attrs=bold),
    ]
    for bit in summary_bits:
        segments.append(_segment(" | ", color="building_edge"))
        segments.append(_segment(bit, color=_known_location_summary_bit_color(bit)))
    return _rich_line(segments, text=_segments_text(segments))


def _known_location_detail_lines(row):
    row = row if isinstance(row, dict) else {}
    lines = []
    legend_line = row.get("legend_line")
    if isinstance(legend_line, dict):
        lines.append(legend_line)
    else:
        name = str(row.get("name", "location")).strip() or "location"
        coords = str(row.get("coords", "coords unknown")).strip() or "coords unknown"
        lines.append(f"{name} @ {coords}")
    lines.append(_known_location_summary_line(row))
    for fact in row.get("fact_lines", ()):
        bullet = _bullet_display_line(fact, bullet="-", bullet_color="building_edge")
        if bullet:
            lines.append(bullet)
    return lines


def _known_location_list_line(row, *, ordinal=1, selected=False):
    row = row if isinstance(row, dict) else {}
    base_line = row.get("legend_line")
    if not isinstance(base_line, dict):
        name = str(row.get("name", "location")).strip() or "location"
        coords = str(row.get("coords", "coords unknown")).strip() or "coords unknown"
        base_line = f"{name} @ {coords}"

    confidence = max(0, min(100, int(round(float(row.get("confidence", 0.0)) * 100.0))))
    marker_color = "player" if selected else "building_edge"
    marker_attrs = getattr(curses, "A_BOLD", 0) if selected else 0
    confidence_color = "property_service" if confidence >= 80 else ("property_asset" if confidence >= 50 else "projectile")

    segments = [
        _segment(">" if selected else " ", color=marker_color, attrs=marker_attrs),
        _segment(f"{max(1, int(ordinal)):02d} ", color="building_edge", attrs=marker_attrs),
    ]
    base_segments = _line_segments(base_line)
    if base_segments:
        segments.extend(base_segments)
    else:
        segments.append(_segment(_line_text(base_line)))
    segments.extend([
        _segment(" | ", color="building_edge"),
        _segment(f"{confidence}%", color=confidence_color, attrs=marker_attrs),
    ])
    return _rich_line(segments, text=f"{'>' if selected else ' '}{max(1, int(ordinal)):02d} {_line_text(base_line)} | {confidence}%")


def _overworld_hud_lines(
    sim,
    cx,
    cy,
    *,
    desc,
    interest,
    travel,
    discovery,
    identity=None,
    markers=(),
    active_vehicle_prop=None,
):
    return _shared_overworld_hud_lines(
        sim,
        cx,
        cy,
        desc=desc,
        interest=interest,
        travel=travel,
        discovery=discovery,
        identity=identity,
        markers=markers,
        active_vehicle_prop=active_vehicle_prop,
    )


def _overworld_edge_legend_lines(
    sim,
    current_chunk,
    *,
    desc,
    interest,
    markers=(),
    look_ui=None,
):
    return _shared_overworld_edge_legend_lines(
        sim,
        current_chunk,
        desc=desc,
        interest=interest,
        markers=markers,
        look_ui=look_ui,
    )


def _wrap_text_lines(text, width):
    width = max(1, int(width))
    raw = _line_text(text)
    if not raw:
        return [""]

    lines = []
    for paragraph in str(raw).splitlines() or [""]:
        wrapped = textwrap.wrap(
            paragraph,
            width=width,
            break_long_words=True,
            break_on_hyphens=False,
            replace_whitespace=False,
            drop_whitespace=True,
        )
        if not wrapped:
            wrapped = [""]
        lines.extend(wrapped)
    return lines or [""]


def _dialogue_lower_start(text):
    text = str(text or "").strip()
    if not text:
        return ""
    return text[:1].lower() + text[1:]


def _dialogue_human_join(labels):
    cleaned = [str(label).strip() for label in tuple(labels or ()) if str(label).strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return ", ".join(cleaned[:-1]) + f", and {cleaned[-1]}"


def _dialogue_hours_text(window):
    if not isinstance(window, (list, tuple)) or len(window) != 2:
        return ""
    try:
        start = int(window[0]) % 24
        end = int(window[1]) % 24
    except (TypeError, ValueError):
        return ""

    def _fmt(hour):
        suffix = "AM"
        display = hour % 24
        if display == 0:
            display = 12
        elif display == 12:
            suffix = "PM"
        elif display > 12:
            display -= 12
            suffix = "PM"
        return f"{display}:00 {suffix}"

    if start == end:
        return "around the clock"
    return f"{_fmt(start)} to {_fmt(end)}"


def _dialogue_credential_mode_text(mode):
    mode = str(mode or "").strip().lower()
    mapping = {
        "mechanical_key": "key-controlled",
        "badge": "badge-controlled",
        "biometric": "biometric-controlled",
    }
    return mapping.get(mode, "controlled")


def _dialogue_security_tier_text(tier):
    try:
        resolved = max(1, min(5, int(tier)))
    except (TypeError, ValueError):
        resolved = 1
    mapping = {
        1: "light security",
        2: "some security",
        3: "tight security",
        4: "heavy security",
        5: "serious security",
    }
    return mapping.get(resolved, "security")


def _segments_to_styled_chars(segments):
    chars = []
    for segment in segments or ():
        if isinstance(segment, dict):
            text = str(segment.get("text", ""))
            color = segment.get("color")
            attrs = int(segment.get("attrs", 0) or 0)
            extras = {
                key: value
                for key, value in segment.items()
                if key not in {"text", "color", "attrs"}
            }
        else:
            text = str(segment)
            color = None
            attrs = 0
            extras = {}
        for char in text:
            chars.append((char, color, attrs, dict(extras)))
    return chars


def _styled_chars_to_segments(chars):
    if not chars:
        return []

    grouped = []
    current_text = []
    current_color = None
    current_attrs = 0
    current_extras = {}

    for entry in chars:
        if len(entry) >= 4:
            char, color, attrs, extras = entry
        else:
            char, color, attrs = entry
            extras = {}
        extras = dict(extras or {})
        if current_text and (color != current_color or attrs != current_attrs or extras != current_extras):
            grouped.append(_segment("".join(current_text), color=current_color, attrs=current_attrs, **current_extras))
            current_text = [char]
            current_color = color
            current_attrs = attrs
            current_extras = extras
            continue

        if not current_text:
            current_color = color
            current_attrs = attrs
            current_extras = extras
        current_text.append(char)

    if current_text:
        grouped.append(_segment("".join(current_text), color=current_color, attrs=current_attrs, **current_extras))
    return grouped


def _wrap_segment_lines(segments, width):
    width = max(1, int(width))
    chars = _segments_to_styled_chars(segments)
    if not chars:
        return [[]]

    wrapped = []
    remaining = list(chars)

    while remaining:
        if len(remaining) <= width:
            line_chars = remaining
            remaining = []
        else:
            break_at = None
            for idx in range(width - 1, -1, -1):
                if remaining[idx][0].isspace():
                    break_at = idx
                    break

            if break_at is not None and any(not remaining[i][0].isspace() for i in range(break_at)):
                line_chars = remaining[:break_at]
                remaining = remaining[break_at + 1:]
            else:
                line_chars = remaining[:width]
                remaining = remaining[width:]

        while line_chars and line_chars[-1][0].isspace():
            line_chars.pop()
        while remaining and remaining[0][0].isspace():
            remaining.pop(0)

        wrapped.append(_styled_chars_to_segments(line_chars))

    return wrapped or [[]]


def _wrap_display_lines(line, width, max_lines=None):
    segments = _line_segments(line)
    if segments:
        lines = [_rich_line(wrapped) for wrapped in _wrap_segment_lines(segments, width)]
    else:
        lines = _wrap_text_lines(_line_text(line), width)

    if max_lines is not None:
        lines = lines[: max(0, int(max_lines))]
    return lines or [""]


def _clip_display_line(line, width):
    width = max(0, int(width))
    if width <= 0:
        return ""

    segments = _line_segments(line)
    plain = _line_text(line)
    if not segments:
        if len(plain) <= width:
            return plain
        if width <= 3:
            return plain[:width]
        return plain[: width - 3] + "..."

    if len(plain) <= width:
        return _rich_line(segments, text=plain)

    if width <= 3:
        clipped_chars = _segments_to_styled_chars(segments)[:width]
        clipped_segments = _styled_chars_to_segments(clipped_chars)
        return _rich_line(clipped_segments, text=plain[:width])

    clipped_chars = _segments_to_styled_chars(segments)[: width - 3]
    clipped_segments = _styled_chars_to_segments(clipped_chars)
    clipped_segments.append(_segment("..."))
    return _rich_line(clipped_segments, text=plain[: width - 3] + "...")


def _view_text_wrap_width(view, width):
    width = max(1, int(width))
    helper = getattr(view, "text_wrap_width", None)
    if callable(helper):
        try:
            resolved = int(helper(width))
        except (TypeError, ValueError):
            resolved = width
        return max(1, resolved)
    return width


def _flow_text_chunks(chunks, width, gap="  ", max_lines=None):
    width = max(1, int(width))
    lines = []
    current = ""

    for raw_chunk in chunks or ():
        chunk = str(raw_chunk).strip()
        if not chunk:
            continue

        candidate = chunk if not current else f"{current}{gap}{chunk}"
        if len(candidate) <= width:
            current = candidate
            continue

        if current:
            lines.append(current)
            if max_lines is not None and len(lines) >= max_lines:
                return lines[:max_lines]
            current = ""

        wrapped = _wrap_text_lines(chunk, width)
        if len(wrapped) == 1:
            current = wrapped[0]
            continue

        lines.extend(wrapped[:-1])
        if max_lines is not None and len(lines) >= max_lines:
            return lines[:max_lines]
        current = wrapped[-1]

    if current or not lines:
        lines.append(current)

    if max_lines is not None:
        lines = lines[:max_lines]
    return lines or [""]


def _fit_wrapped_sections(sections, max_rows):
    max_rows = max(1, int(max_rows))
    normalized = []
    total_rows = 0

    for section in sections or ():
        lines = list(section.get("lines", []) or [])
        if not lines:
            continue

        min_lines = max(0, min(int(section.get("min_lines", 0)), len(lines)))
        trim_priority = int(section.get("trim_priority", 0))
        normalized.append({
            "lines": lines,
            "min_lines": min_lines,
            "trim_priority": trim_priority,
        })
        total_rows += len(lines)

    if total_rows <= max_rows:
        return normalized

    while total_rows > max_rows:
        trimmed = False
        for section in sorted(normalized, key=lambda entry: entry["trim_priority"], reverse=True):
            if len(section["lines"]) <= section["min_lines"]:
                continue
            section["lines"].pop()
            total_rows -= 1
            trimmed = True
            if total_rows <= max_rows:
                break
        if not trimmed:
            break

    return normalized


def _build_progress_report(sim, player_eid, opportunity_limit=8):
    return _report_runtime_build_progress_report(
        sim,
        player_eid,
        opportunity_limit=opportunity_limit,
    )


def _build_known_locations_report(sim, player_eid, limit=None, include_hidden=False):
    return _report_runtime_build_known_locations_report(
        sim,
        player_eid,
        limit=limit,
        include_hidden=include_hidden,
        entity_display_name_fn=_entity_display_name,
        hours_text_fn=_dialogue_hours_text,
        security_tier_text_fn=_dialogue_security_tier_text,
        human_join_fn=_dialogue_human_join,
        infrastructure_target_property_fn=_infrastructure_target_property,
        infrastructure_role_label_fn=_infrastructure_role_label,
        storefront_illegal_goods_signal_fn=_storefront_illegal_goods_signal,
        property_legend_line_fn=_property_legend_line,
    )


STAKEOUT_RADIUS = 3
STAKEOUT_REVEAL_INTERVAL = 8
STAKEOUT_MAX_REVEALS = 4
STAKEOUT_CONFIDENCE_CAP = 0.88


def _active_property_opportunities(sim, prop_id):
    prop_key = str(prop_id or "").strip()
    if not prop_key:
        return ()
    opp_state = getattr(sim, "world_traits", {}).get("opportunities", {})
    active = []
    for entry in opp_state.get("active", ()):
        if not isinstance(entry, dict):
            continue
        requirements = entry.get("requirements", {}) if isinstance(entry.get("requirements", {}), dict) else {}
        if str(requirements.get("property_id", "")).strip() != prop_key:
            continue
        active.append(entry)
    return tuple(active)


def _nearest_stakeable_property(sim, pos):
    if pos is None:
        return None
    nearby = sim.properties_in_radius(pos.x, pos.y, pos.z, r=STAKEOUT_RADIUS)
    candidates = [
        prop for prop in nearby
        if str(prop.get("kind", "")).strip().lower() == "building"
        and _active_property_opportunities(sim, prop.get("id"))
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda p: _manhattan(pos.x, pos.y, p["x"], p["y"]))


def _stakeout_property_opportunity_stats(sim, observer_eid, prop_id):
    active = list(_active_property_opportunities(sim, prop_id))
    if not active:
        return None

    least_confidence = 2.0
    unknown_count = 0
    for entry in active:
        oid = int(entry.get("id", 0) or 0)
        if oid <= 0:
            continue
        intel = opportunity_intel_for_observer(sim, observer_eid, oid)
        if intel is None:
            unknown_count += 1
            least_confidence = min(least_confidence, 0.0)
            continue
        least_confidence = min(least_confidence, max(0.0, float(intel.get("confidence", 0.0) or 0.0)))

    if least_confidence > 1.0:
        least_confidence = 0.0

    return {
        "count": len(active),
        "unknown_count": unknown_count,
        "least_confidence": max(0.0, min(1.0, float(least_confidence))),
        "mapped": unknown_count <= 0 and least_confidence >= (STAKEOUT_CONFIDENCE_CAP - 0.01),
    }


def _stakeout_progress_snapshot(sim, observer_eid, pos, *, require_hidden=False):
    if pos is None:
        return None
    stealth_state = getattr(sim, "player_stealth_state", {})
    hidden = bool(stealth_state.get("hidden")) if isinstance(stealth_state, dict) else False
    if require_hidden and not hidden:
        return None
    target_prop = _nearest_stakeable_property(sim, pos)
    if not isinstance(target_prop, dict):
        return None
    prop_id = str(target_prop.get("id", "")).strip()
    stats = _stakeout_property_opportunity_stats(sim, observer_eid, prop_id)
    if not isinstance(stats, dict):
        return None

    state = getattr(sim, "stakeout_state", None)
    active = isinstance(state, dict) and str(state.get("prop_id", "")).strip() == prop_id
    ticks = _int_or_default((state or {}).get("ticks", 0), 0) if active else 0
    reveals_done = _int_or_default((state or {}).get("reveals_done", 0), 0) if active else 0
    progress_mod = ticks % STAKEOUT_REVEAL_INTERVAL
    next_reveal_in = STAKEOUT_REVEAL_INTERVAL if progress_mod == 0 else (STAKEOUT_REVEAL_INTERVAL - progress_mod)
    return {
        "property_id": prop_id,
        "property_name": str(target_prop.get("name", prop_id or "target site")).strip() or "target site",
        "hidden": hidden,
        "active": active,
        "ready": hidden,
        "ticks": max(0, ticks),
        "reveals_done": max(0, reveals_done),
        "max_reveals": STAKEOUT_MAX_REVEALS,
        "next_reveal_in": max(1, next_reveal_in),
        **stats,
    }


def _mode_line(mode_state=None, cover=None, look_active=False, aim_active=False, turn_mode=False, stealth_state=None):
    bold = getattr(curses, "A_BOLD", 0)
    segments = [_segment("Modes: ")]

    badges = []
    if mode_state and getattr(mode_state, "sneak", False):
        badges.append(("SNEAK", "scout"))
    if mode_state and getattr(mode_state, "hidden", False):
        badges.append(("HIDDEN", "player"))
    if cover and getattr(cover, "active", False):
        badges.append(("COVER", "guard"))
    if bool(aim_active):
        badges.append(("AIM", "projectile"))
    elif bool(look_active):
        badges.append(("LOOK", "objective"))
    if bool(turn_mode):
        badges.append(("TURN", "projectile"))

    if not badges:
        segments.append(_segment("-"))
        return _rich_line(segments, text=_segments_text(segments))

    for index, (label, color) in enumerate(badges):
        if index:
            segments.append(_segment(" "))
        segments.append(_segment("["))
        segments.append(_segment(label, color=color, attrs=bold))
        segments.append(_segment("]"))

    if mode_state and getattr(mode_state, "sneak", False):
        stealth_state = stealth_state if isinstance(stealth_state, dict) else {}
        hidden = bool(stealth_state.get("hidden"))
        witness_count = int(stealth_state.get("witness_count", 0))
        witness_labels = list(stealth_state.get("witness_labels", ()))
        segments.append(_segment("  "))
        if hidden:
            segments.append(_segment("unseen", color="scout"))
        elif witness_count > 0:
            if witness_count == 1 and witness_labels:
                summary = f"seen:{witness_labels[0]}"
            elif witness_labels:
                summary = f"seen:{witness_labels[0]}+{witness_count - 1}"
            else:
                summary = f"seen:{witness_count}"
            segments.append(_segment(summary, color="projectile"))
        else:
            segments.append(_segment("searching", color="human"))

    return _rich_line(segments, text=_segments_text(segments))


def _tile_legend_line(sim, x, y, z, text):
    tile = sim.tilemap.tile_at(x, y, z)
    glyph, color = _tile_render_style(sim, tile, x, y, z)
    return _legend_line(text, glyph=glyph, color=color, attrs=getattr(curses, "A_BOLD", 0))


def _property_legend_line(prop, text, active_quest_target=None):
    appearance = _appearance_property_render_snapshot(
        prop,
        active_quest_target=active_quest_target,
    )
    return _legend_line(
        text,
        glyph=appearance.glyph,
        color=appearance.color,
        attrs=getattr(curses, "A_BOLD", 0),
        semantic_id=appearance.semantic_id,
    )


def _item_reference_line(item_id, text, prefix=""):
    item_def = ITEM_CATALOG.get(item_id, {})
    glyph = _item_display_glyph(item_def)
    color = _ground_item_color(item_def)
    semantic_id = _item_reference_semantic_id(item_def)
    return _legend_line(
        text,
        glyph=glyph,
        color=color,
        prefix=prefix,
        attrs=getattr(curses, "A_BOLD", 0),
        semantic_id=semantic_id,
    )


def _item_legend_line(item_id, text):
    return _item_reference_line(item_id, text)


def _creature_color_key(identity, *, role="", cat_color_map=None):
    return _appearance_creature_color_key(identity, role=role)


def _entity_render_style(sim, eid, player_eid=None):
    return sim.appearance.entity(eid, player_eid=player_eid)


def _entity_legend_line(sim, eid, text, player_eid=None):
    appearance = _entity_render_style(sim, eid, player_eid=player_eid)
    return _legend_line(
        text,
        glyph=appearance.glyph,
        color=appearance.color,
        attrs=getattr(curses, "A_BOLD", 0),
    )


def _tile_label(sim, tile, x, y, z=0):
    if not tile:
        return "open ground"

    feature_style = _feature_tile_style(sim, tile, x, y, z)
    if feature_style:
        return feature_style[2]

    glyph = str(tile.glyph)[:1] or "."
    structure = sim.structure_at(x, y, z) if hasattr(sim, "structure_at") else None
    if not tile.walkable and glyph == "#" and _building_id_from_structure(structure):
        return "building wall"
    if tile.walkable and glyph == "." and _building_id_from_structure(structure):
        return "building interior"
    if glyph == "B":
        return "building wall"
    if glyph == "b":
        return "building interior"
    if glyph == "#":
        return "rough barrier"
    if glyph == ",":
        return "brush or ground cover"
    if glyph == "^":
        return "rock outcrop"
    if glyph == "~":
        return "water"
    if glyph == "_":
        return "shore or salt flats"
    if glyph == "=":
        return "road"
    if glyph == '"':
        return "window"
    if glyph == ".":
        return "open ground"
    return f"tile:{glyph}"


BUILDING_STREET_LABELS = {
    "arcade": "arcade frontage",
    "auto_garage": "garage frontage",
    "backroom_clinic": "clinic frontage",
    "bank": "bank branch",
    "bar": "bar frontage",
    "casino": "casino frontage",
    "checkpoint": "checkpoint",
    "corner_store": "corner storefront",
    "courthouse": "civic building",
    "jail": "city jail",
    "prison": "prison complex",
    "daycare": "daycare building",
    "gaming_hall": "gaming hall",
    "hotel": "hotel frontage",
    "junk_market": "market frontage",
    "laundromat": "laundromat",
    "metro_exchange": "exchange building",
    "music_venue": "music venue",
    "nightclub": "nightclub frontage",
    "office": "office building",
    "outfitter": "outfitter frontage",
    "pawn_shop": "pawn shop frontage",
    "pharmacy": "pharmacy frontage",
    "pump_house": "pump house",
    "relay_post": "relay post",
    "restaurant": "restaurant frontage",
    "roadhouse": "roadhouse",
    "ruin_shelter": "ruin shelter",
    "ranger_hut": "ranger hut",
    "salvage_camp": "salvage camp",
    "server_hub": "utility block",
    "surplus_store": "surplus storefront",
    "survey_post": "survey post",
    "soup_kitchen": "soup kitchen",
    "tavern": "tavern frontage",
    "theater": "theater frontage",
    "tide_station": "tide station",
    "tower": "tower block",
    "warehouse": "warehouse",
    "work_shed": "work shed",
    "field_camp": "field camp",
    "lookout_post": "lookout post",
    "dock_shack": "dock shack",
    "ferry_post": "ferry post",
    "net_house": "net house",
    "beacon_house": "beacon house",
}


def _building_street_label(prop):
    metadata = _property_metadata(prop)
    archetype = str(metadata.get("archetype", "") or "").strip().lower()
    if archetype in BUILDING_STREET_LABELS:
        return BUILDING_STREET_LABELS[archetype]
    if archetype:
        return f"{archetype.replace('_', ' ')} building"
    return "building exterior"


def _building_frontage_bits(prop):
    apertures = _property_apertures(prop)
    bits = []
    profile = _building_exterior_profile_for(_property_metadata(prop))
    frontage = str(profile.get("frontage", "") or "").strip()
    if frontage and frontage != "plain frontage":
        bits.append(frontage)
    if any(bool(aperture.get("ordinary")) for aperture in apertures):
        bits.append("front door")
    if any(str(aperture.get("kind", "")).strip().lower() in {"service_door", "employee_door", "side_door"} for aperture in apertures):
        bits.append("side/service door")
    window_count = sum(
        1
        for aperture in apertures
        if str(aperture.get("kind", "")).strip().lower() in {"window", "skylight"}
    )
    exterior_class = str(profile.get("class", "") or "").strip().lower()
    if window_count == 1:
        if exterior_class == "industrial":
            bits.append("single service window")
        else:
            bits.append("1 window")
    elif window_count > 1:
        if exterior_class == "storefront":
            bits.append(f"{window_count} display windows")
        elif exterior_class == "residential":
            bits.append(f"{window_count} home windows")
        elif exterior_class == "corporate":
            bits.append(f"{window_count} office windows")
        elif exterior_class == "civic":
            bits.append(f"{window_count} public windows")
        elif exterior_class == "entertainment":
            bits.append(f"{window_count} venue windows")
        else:
            bits.append(f"{window_count} windows")
    elif exterior_class == "secure":
        bits.append("few exterior openings")
    return bits


def _building_street_summary(sim, prop):
    if not prop:
        return ""

    metadata = _property_metadata(prop)
    pulse = _building_pulse_snapshot(sim, prop=prop)
    profile = _building_exterior_profile_for(metadata)
    bits = [_building_street_label(prop)]
    access_level = _property_access_level(prop)
    if access_level == "public":
        bits.append(_property_status_text(sim, prop))
    elif access_level == "restricted":
        bits.append("restricted")
    else:
        bits.append("protected")

    try:
        floors = int(metadata.get("floors", 1))
    except (TypeError, ValueError):
        floors = 1
    if floors > 1:
        bits.append(f"{floors} floors")
    pulse_street = str(pulse.get("street_label", "") or "").strip()
    if pulse_street:
        bits.append("activity:" + pulse_street)

    bits.extend(_building_frontage_bits(prop))

    signage = _property_signage(prop)
    sign_text = str(signage.get("text", "") or "").strip() if signage else ""
    if sign_text:
        bits.append(f"sign:{sign_text}")
    elif str(profile.get("class", "") or "").strip().lower() in {"industrial", "secure"}:
        bits.append("no public sign")

    return ", ".join(bit for bit in bits if bit)


def _property_summary(sim, prop, viewer_eid=None, x=None, y=None, z=None):
    if not prop:
        return "property"

    metadata = _property_metadata(prop)
    kind = str(prop.get("kind", "property")).strip().lower() or "property"
    archetype = str(metadata.get("archetype", "")).strip().lower()
    infrastructure_role = _property_infrastructure_role(prop)
    infrastructure_target = _infrastructure_target_property(sim, prop) if infrastructure_role else None
    owner_eid = prop.get("owner_eid")
    owner_tag = prop.get("owner_tag")

    if owner_eid == viewer_eid:
        owner_text = "you"
    elif owner_eid is not None:
        owner_text = _entity_display_name(sim, owner_eid, title_case=False)
    else:
        owner_text = str(owner_tag or "unowned")

    bits = [str(prop.get("name", prop.get("id", "property"))).strip() or "property"]
    label = kind if not archetype else f"{kind}/{archetype}"
    bits.append(f"[{label}]")
    organization_eid = property_organization_eid(sim, prop, ensure=(kind == "building"))
    organization_text = organization_name(sim, organization_eid)
    if organization_text and organization_text.lower() != bits[0].lower():
        bits.append(f"org:{organization_text}")
    if kind == "building":
        building_id = _building_id_from_property(prop)
        revealed_building_id = _viewer_revealed_building_id(sim, viewer_eid, z=z if z is not None else prop.get("z", 0))
        bits.append("interior" if building_id and building_id == revealed_building_id else "exterior")
        pulse_label = str(_building_pulse_snapshot(sim, prop=prop).get("label", "") or "").strip()
        if pulse_label:
            bits.append("pulse:" + pulse_label)
    if infrastructure_role:
        bits.append("role:" + _infrastructure_role_label(infrastructure_role))
        if infrastructure_target:
            target_name = str(infrastructure_target.get("name", infrastructure_target.get("id", "property"))).strip() or "property"
            bits.append("target:" + target_name)
    bits.append(f"owner:{owner_text}")
    access = _evaluate_property_access(sim, viewer_eid, prop, x=x, y=y, z=z)
    access_text = access.access_level
    if access.currently_open is not None:
        access_text = f"{access_text}/{_property_status_text(sim, prop, hour=access.current_hour)}"
    bits.append(access_text)
    if _property_is_storefront(prop):
        service = _storefront_service_profile(sim, prop)
        label = str(service.get("summary_label", "")).strip()
        if label:
            bits.append(f"trade:{label}")
    lock_source = infrastructure_target if infrastructure_role == "access_panel" and infrastructure_target else prop
    lock_state = property_lock_state(lock_source)
    controller = None
    credential_status = ""
    if str(lock_source.get("kind", "")).strip().lower() == "building":
        controller = _property_access_controller(sim, lock_source)
    if lock_state["key_id"]:
        bits.append(f"lock:{'locked' if lock_state['locked'] else 'unlocked'}")
        if controller:
            bits.append("req:" + _controller_credential_short_label(controller))
        credential_status = _viewer_property_credential_status(sim, viewer_eid, lock_source)
        if credential_status and kind != "vehicle":
            bits.append("cred:" + credential_status)
    if str(lock_source.get("kind", "")).strip().lower() == "building":
        controller_kind = str(controller.get("kind", "") or "").strip().lower()
        if controller_kind in {"owner_schedule", "auto_timer", "auto_lock"}:
            bits.append("ctrl:" + controller_kind.replace("_", " "))

    if kind == "vehicle":
        profile = _vehicle_profile_from_property(prop)
        owned_vehicle = (
            prop.get("owner_eid") == viewer_eid
            or str(prop.get("owner_tag", "") or "").strip().lower() == "player"
        )
        if owned_vehicle:
            bits.append("owned")
        if lock_state["key_id"]:
            if credential_status == "held":
                bits.append("key:held")
            elif owned_vehicle:
                bits.append("key:missing")
        if profile:
            fuel, fuel_capacity = _vehicle_fuel_values(prop)
            bits.append(f"class:{profile['vehicle_class']}")
            bits.append(
                f"stats:p{int(profile['power'])}/d{int(profile['durability'])}/e{int(profile['fuel_efficiency'])}"
            )
            bits.append(f"fuel:{fuel}/{fuel_capacity}")
        return " ".join(bits)

    access_modes = _property_access_summary(sim, prop, viewer_eid=viewer_eid)
    if access_modes:
        bits.append("access:" + access_modes)

    services = _property_services(prop)
    if services:
        bits.append("services:" + ",".join(services))

    if access.standing_reason and access.standing_reason not in {"none", "open_business", "public_space"}:
        bits.append(f"standing:{access.standing_reason}")

    cover_kind = str(metadata.get("cover_kind", "") or "").strip().lower()
    if cover_kind in {"none", "low", "full"}:
        try:
            cover_value = int(float(metadata.get("cover_value", 0.0)) * 100)
        except (TypeError, ValueError):
            cover_value = 0
        cover_value = max(0, min(99, cover_value))
        bits.append(f"cover:{cover_kind}:{cover_value}%")

    floors = metadata.get("floors")
    try:
        floors = int(floors)
    except (TypeError, ValueError):
        floors = None
    if floors and floors > 1:
        bits.append(f"floors:{floors}")

    rooms = metadata.get("rooms")
    if isinstance(rooms, (list, tuple)) and rooms:
        bits.append(f"rooms:{len(rooms)}")

    signage = _property_signage(prop)
    if signage:
        sign_text = str(signage.get("text", "") or "").strip()
        if sign_text and sign_text.lower() != bits[0].lower():
            bits.append(f"sign:{sign_text}")

    purchase_cost = metadata.get("purchase_cost")
    try:
        purchase_cost = int(purchase_cost)
    except (TypeError, ValueError):
        purchase_cost = None
    if purchase_cost is not None:
        bits.append(f"cost:{purchase_cost}")

    return " ".join(bits)


def _floor_label(z, *, long=False):
    try:
        z = int(z)
    except (TypeError, ValueError):
        return str(z)
    if z < 0:
        return f"Basement {abs(z)}" if long else f"B{abs(z)}"
    if long:
        return f"Floor {z + 1}"
    return str(z + 1)


def _structure_summary(info):
    if not isinstance(info, dict):
        return ""

    name = str(info.get("name", "building")).strip() or "building"
    archetype = str(info.get("archetype", "")).strip().lower()
    room_kind = str(info.get("room_kind", "")).strip().lower()
    try:
        floor = int(info.get("floor", 0))
    except (TypeError, ValueError):
        floor = 0
    try:
        floors = int(info.get("floors", 1))
    except (TypeError, ValueError):
        floors = 1
    try:
        basement_levels = int(info.get("basement_levels", 0))
    except (TypeError, ValueError):
        basement_levels = 0
    try:
        total_levels = int(info.get("total_levels", floors + basement_levels))
    except (TypeError, ValueError):
        total_levels = floors + basement_levels

    bits = [name]
    if archetype and archetype not in name.lower():
        bits.append(f"[{archetype}]")
    if total_levels > 1:
        bits.append(f"floor:{_floor_label(floor)}/{total_levels}")
    if room_kind:
        bits.append("room:" + room_kind.replace("_", " "))

    rooms = info.get("rooms")
    if isinstance(rooms, (list, tuple)) and rooms:
        preview = ", ".join(str(room).replace("_", " ") for room in rooms[:2])
        if len(rooms) > 2:
            preview += f" +{len(rooms) - 2}"
        bits.append(f"plan:{preview}")

    return " ".join(bit for bit in bits if bit)


FINANCE_ARCHETYPES = {
    "bank",
    "brokerage",
    "pawn_shop",
}
ENTERTAINMENT_ARCHETYPES = NIGHTLIFE_ARCHETYPES | {
    "casino",
    "gallery",
}
HOSPITALITY_ARCHETYPES = {
    "bar",
    "flophouse",
    "hotel",
    "restaurant",
    "soup_kitchen",
    "street_kitchen",
    "tavern",
}
OFFICE_ARCHETYPES = {
    "co_working_hub",
    "media_lab",
    "office",
    "tower",
}
TRANSIT_BUILDING_ARCHETYPES = TRANSIT_ARCHETYPES | {
    "metro_exchange",
}

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


def _humanize_slug(value, *, title=False):
    text = re.sub(r"\s+", " ", str(value or "").replace("_", " ").strip())
    if not text:
        return ""
    return text.title() if title else text


def _location_building_category(archetype, *, storefront=False):
    archetype = str(archetype or "").strip().lower()
    if archetype in FINANCE_ARCHETYPES:
        return "finance"
    if archetype in MEDICAL_ARCHETYPES:
        return "medical"
    if archetype in SECURITY_ARCHETYPES:
        return "secure"
    if archetype in INDUSTRIAL_ARCHETYPES or archetype in SALVAGE_ARCHETYPES:
        return "industrial"
    if archetype in ENTERTAINMENT_ARCHETYPES:
        return "entertainment"
    if archetype in HOSPITALITY_ARCHETYPES:
        return "hospitality"
    if archetype in RESIDENTIAL_ARCHETYPES or archetype in {"barracks", "hotel"}:
        return "residential"
    if archetype in TRANSIT_BUILDING_ARCHETYPES:
        return "transit"
    if archetype in OFFICE_ARCHETYPES:
        return "office"
    if storefront or archetype in STOREFRONT_ARCHETYPES:
        return "retail"
    return "general"


_BUILDING_PULSE_BUCKETS = 4


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


def _building_tick_snapshot(sim, *, bucket_count=_BUILDING_PULSE_BUCKETS):
    if sim is None:
        return {
            "ticks_per_hour": 600,
            "hour_tick": 0,
            "bucket": 0,
            "bucket_count": max(1, int(bucket_count)),
            "minute": 0,
        }

    world_traits = getattr(sim, "world_traits", {}) if sim is not None else {}
    clock = world_traits.get("clock", {}) if isinstance(world_traits, dict) else {}
    if not isinstance(clock, dict):
        clock = {}

    try:
        ticks_per_hour = int(clock.get("ticks_per_hour", 600))
    except (TypeError, ValueError):
        ticks_per_hour = 600
    ticks_per_hour = max(60, ticks_per_hour)

    bucket_count = max(1, int(bucket_count))
    tick = int(getattr(sim, "tick", 0) or 0)
    hour_tick = tick % ticks_per_hour
    bucket_span = max(1, ticks_per_hour // bucket_count)
    bucket = min(bucket_count - 1, hour_tick // bucket_span)
    minute = min(59, int((hour_tick * 60) / ticks_per_hour))
    return {
        "ticks_per_hour": ticks_per_hour,
        "hour_tick": hour_tick,
        "bucket": bucket,
        "bucket_count": bucket_count,
        "minute": minute,
    }


def _building_micro_event_pool(category, phase, *, open_now=False):
    category = str(category or "").strip().lower()
    phase = str(phase or "").strip().lower()
    if not phase or phase in {"after_hours", "locked_down", "quiet_hours", "quiet_interior"}:
        return ()

    if category in {"retail", "finance", "office"}:
        if phase == "opening":
            return (
                {
                    "phase": "delivery_drop",
                    "label": "delivery drop",
                    "street_label": "courier stop at the door",
                    "entry_sentence": "A delivery is briefly pulling motion toward the threshold and the back-room route behind it.",
                    "emphasis": "front",
                    "perimeter_bonus": 1.1,
                },
                {
                    "phase": "staff_handoff",
                    "label": "staff handoff",
                    "street_label": "staff cycling through the frontage",
                    "entry_sentence": "A short handoff is making the threshold feel busier than the customer side behind it.",
                    "emphasis": "admin",
                    "perimeter_bonus": 0.9,
                },
                {
                    "phase": "help_wanted_board",
                    "label": "help-wanted board",
                    "street_label": "job seekers checking a notice board",
                    "entry_sentence": "A small help-wanted knot has formed off the front, with people reading the posted shift needs before deciding whether to step in.",
                    "emphasis": "front",
                    "perimeter_bonus": 1.7,
                },
            )
        if phase == "rush":
            return (
                {
                    "phase": "counter_queue",
                    "label": "counter queue",
                    "street_label": "short line holding at the entrance",
                    "entry_sentence": "A short queue keeps forming and dissolving at the front, so the place feels like it is breathing in bursts instead of evenly.",
                    "emphasis": "front",
                    "perimeter_bonus": 2.1,
                },
                {
                    "phase": "courier_stop",
                    "label": "courier stop",
                    "street_label": "messenger traffic clipping the curb",
                    "entry_sentence": "A courier stop keeps interrupting the normal flow, pulling attention back toward the threshold every few minutes.",
                    "emphasis": "front",
                    "perimeter_bonus": 1.4,
                },
            )
        if phase in {"back_office", "steady_trade"}:
            return (
                {
                    "phase": "paperwork_surge",
                    "label": "paperwork surge",
                    "street_label": "front thinning while the back office catches up",
                    "entry_sentence": "The public rooms are quieter because a paperwork crunch is pulling more people deeper inside.",
                    "emphasis": "admin",
                    "perimeter_bonus": 0.1,
                },
                {
                    "phase": "shift_handoff",
                    "label": "shift handoff",
                    "street_label": "staff rotating through the frontage",
                    "entry_sentence": "A quick shift handoff is making the front edge feel more exposed than settled.",
                    "emphasis": "admin",
                    "perimeter_bonus": 1.0,
                },
            )

    if category in {"hospitality", "entertainment"}:
        if phase in {"prep", "cleanup"}:
            return (
                {
                    "phase": "supplier_drop",
                    "label": "supplier drop",
                    "street_label": "crates and carts near the service door",
                    "entry_sentence": "A supplier drop has the support loop briefly spilling out into public view.",
                    "emphasis": "work",
                    "perimeter_bonus": 0.8,
                },
                {
                    "phase": "reset_scramble",
                    "label": "reset scramble",
                    "street_label": "staff cutting hard between the front and the back",
                    "entry_sentence": "A reset scramble is keeping the place in short efficient loops rather than one smooth flow.",
                    "emphasis": "work",
                    "perimeter_bonus": 0.2,
                },
            )
        if phase in {"lunch_rush", "evening_crowd"}:
            return (
                {
                    "phase": "table_turnover",
                    "label": "table turnover",
                    "street_label": "staff threading hard through the front room",
                    "entry_sentence": "A turnover crunch is keeping the public rooms in constant motion, with barely any pause between one party and the next.",
                    "emphasis": "hospitality",
                    "perimeter_bonus": 0.3,
                },
                {
                    "phase": "crowd_spillover",
                    "label": "crowd spillover",
                    "street_label": "people bunching outside the door",
                    "entry_sentence": "A knot of people has started to spill back onto the sidewalk, making the place feel bigger than its footprint.",
                    "emphasis": "front",
                    "perimeter_bonus": 3.2,
                },
                {
                    "phase": "waiting_parties",
                    "label": "waiting parties",
                    "street_label": "small groups lingering just outside",
                    "entry_sentence": "Small waiting parties are collecting outside, turning the threshold into part of the room.",
                    "emphasis": "front",
                    "perimeter_bonus": 2.5,
                },
            )
        if phase == "late_buzz":
            return (
                {
                    "phase": "barback_reset",
                    "label": "barback reset",
                    "street_label": "staff shuttling between the door and the back",
                    "entry_sentence": "The late hour has compressed the motion here into short reset loops and quiet checks.",
                    "emphasis": "work",
                    "perimeter_bonus": 0.4,
                },
                {
                    "phase": "last_call_spill",
                    "label": "last-call spill",
                    "street_label": "slow exits and smokers outside",
                    "entry_sentence": "Last call is leaking onto the street in slow exits, smoke breaks, and people deciding whether they are really leaving.",
                    "emphasis": "front",
                    "perimeter_bonus": 3.4,
                },
            )

    if category in {"industrial", "transit"}:
        if phase == "receiving":
            return (
                {
                    "phase": "delivery_run",
                    "label": "delivery run",
                    "street_label": "truck-side handoffs at the curb",
                    "entry_sentence": "A delivery run has the site briefly organized around handoff rather than storage.",
                    "emphasis": "work",
                    "perimeter_bonus": 1.8,
                },
                {
                    "phase": "manifest_check",
                    "label": "manifest check",
                    "street_label": "crew pausing near the gate with clipboards",
                    "entry_sentence": "A manifest check has movement bunching near the edge of the site before it can spread deeper in.",
                    "emphasis": "admin",
                    "perimeter_bonus": 1.2,
                },
            )
        if phase in {"shift_work", "steady_ops"}:
            events = [
                {
                    "phase": "loading_push",
                    "label": "loading push",
                    "street_label": "freight moving in short bursts",
                    "entry_sentence": "A loading push is giving the place a start-stop tempo instead of a smooth hum.",
                    "emphasis": "work",
                    "perimeter_bonus": 0.8,
                },
                {
                    "phase": "dispatch_surge",
                    "label": "dispatch surge",
                    "street_label": "dispatch traffic clipping the frontage",
                    "entry_sentence": "A dispatch surge is briefly pulling operational attention back toward the edge of the site.",
                    "emphasis": "transit" if category == "transit" else "admin",
                    "perimeter_bonus": 1.1,
                },
            ]
            if category == "transit":
                events.append({
                    "phase": "boarding_crush",
                    "label": "boarding crush",
                    "street_label": "fares and boarding calls bunching at the stop",
                    "entry_sentence": "A boarding crush is turning the stop into a brief knot of fares, shouted destinations, and people trying not to miss the clean connection.",
                    "emphasis": "front",
                    "perimeter_bonus": 3.0,
                })
                events.append({
                    "phase": "commuter_orientation",
                    "label": "commuter orientation",
                    "street_label": "new arrivals sorting routes by the edge",
                    "entry_sentence": "A few new arrivals are sorting routes and work leads near the stop instead of committing to a direction yet.",
                    "emphasis": "transit",
                    "perimeter_bonus": 1.6,
                })
            else:
                events.append({
                    "phase": "day_labor_call",
                    "label": "day-labor call",
                    "street_label": "hands gathering around a crew list",
                    "entry_sentence": "A day-labor call is pulling loose workers toward the edge of the site, all names, short terms, and people hoping the shift sticks.",
                    "emphasis": "work",
                    "perimeter_bonus": 1.5,
                })
            return tuple(events)
        if phase == "handoff":
            events = [
                {
                    "phase": "shift_change",
                    "label": "shift change",
                    "street_label": "workers bunching near the entrance",
                    "entry_sentence": "A shift change has people collecting near the threshold longer than the building usually likes.",
                    "emphasis": "front",
                    "perimeter_bonus": 2.6,
                },
                {
                    "phase": "gate_briefing",
                    "label": "gate briefing",
                    "street_label": "supervisors stopping people just inside the gate",
                    "entry_sentence": "A quick gate briefing is turning the entrance into a temporary choke point.",
                    "emphasis": "admin",
                    "perimeter_bonus": 2.0,
                },
            ]
            if category == "transit":
                events.append({
                    "phase": "arrival_handoff",
                    "label": "arrival handoff",
                    "street_label": "incoming riders and pickups meeting at the edge",
                    "entry_sentence": "An arrival handoff is making the stop feel connected to somewhere farther out, with inbound riders, relief pickups, and quick onward directions all landing at once.",
                    "emphasis": "transit",
                    "perimeter_bonus": 2.4,
                })
            return tuple(events)

    if category == "medical":
        if phase == "intake":
            return (
                {
                    "phase": "triage_spill",
                    "label": "triage spill",
                    "street_label": "intake queue holding at the door",
                    "entry_sentence": "An intake queue is keeping more people near the threshold than the lobby was built to flatter.",
                    "emphasis": "front",
                    "perimeter_bonus": 2.2,
                },
                {
                    "phase": "chart_handoff",
                    "label": "chart handoff",
                    "street_label": "staff cutting brisk lines between desks",
                    "entry_sentence": "A chart handoff is pulling staff into short loops between the desk and the deeper rooms.",
                    "emphasis": "medical",
                    "perimeter_bonus": 0.6,
                },
                {
                    "phase": "clinic_outreach",
                    "label": "clinic outreach",
                    "street_label": "walk-ins checking in at an outreach table",
                    "entry_sentence": "An outreach table has made the front feel less like a door and more like a first safe stop for people trying to get steady.",
                    "emphasis": "medical",
                    "perimeter_bonus": 1.4,
                },
            )
        if phase in {"treatment", "night_watch"}:
            return (
                {
                    "phase": "supply_run",
                    "label": "supply run",
                    "street_label": "carts and staff slipping between doors",
                    "entry_sentence": "A supply run is briefly making the place feel more logistical than serene.",
                    "emphasis": "medical",
                    "perimeter_bonus": 0.4,
                },
                {
                    "phase": "quiet_handoff",
                    "label": "quiet handoff",
                    "street_label": "a subdued exchange near the front desk",
                    "entry_sentence": "A quiet handoff is briefly gathering staff near the front before they disappear deeper in again.",
                    "emphasis": "front",
                    "perimeter_bonus": 1.1,
                },
                {
                    "phase": "street_triage",
                    "label": "curbside triage",
                    "street_label": "medics stabilizing somebody outside",
                    "entry_sentence": "Emergency treatment has spilled right out to the threshold, where hurt bodies and clipped orders are suddenly visible from the street.",
                    "emphasis": "medical",
                    "perimeter_bonus": 1.8,
                },
            )

    if category == "secure":
        if phase == "intake":
            return (
                {
                    "phase": "visitor_screening",
                    "label": "visitor screening",
                    "street_label": "screening line bunching at the entrance",
                    "entry_sentence": "Visitor screening is briefly turning the front into a controlled queue.",
                    "emphasis": "front",
                    "perimeter_bonus": 2.4,
                },
                {
                    "phase": "booking_queue",
                    "label": "booking queue",
                    "street_label": "processing traffic holding near the desk",
                    "entry_sentence": "A booking queue is holding movement near the front longer than the building would like.",
                    "emphasis": "admin",
                    "perimeter_bonus": 1.9,
                },
            )
        if phase in {"controlled_ops", "night_watch"}:
            return (
                {
                    "phase": "guard_rotation",
                    "label": "guard rotation",
                    "street_label": "uniformed staff changing over by the gate",
                    "entry_sentence": "A guard rotation is briefly making the secure edge of the site more legible than usual.",
                    "emphasis": "admin",
                    "perimeter_bonus": 1.5,
                },
                {
                    "phase": "custody_handoff",
                    "label": "custody handoff",
                    "street_label": "staff clustering for a controlled handoff",
                    "entry_sentence": "A custody handoff has movement bunching where the building can keep eyes on all of it.",
                    "emphasis": "secure",
                    "perimeter_bonus": 1.3,
                },
            )
        if phase == "handoff":
            return (
                {
                    "phase": "custody_handoff",
                    "label": "custody handoff",
                    "street_label": "officers pausing at the secure threshold",
                    "entry_sentence": "A custody handoff is turning the entrance into a temporary checkpoint inside the checkpoint.",
                    "emphasis": "secure",
                    "perimeter_bonus": 2.1,
                },
                {
                    "phase": "release_queue",
                    "label": "release queue",
                    "street_label": "families and releases holding near the front",
                    "entry_sentence": "A release queue is making the building show more human traffic at the edge than it usually allows.",
                    "emphasis": "front",
                    "perimeter_bonus": 2.3,
                },
            )

    if category == "residential":
        if phase == "starting_day":
            return (
                {
                    "phase": "school_run",
                    "label": "school-run cluster",
                    "street_label": "families bunching at the stoop",
                    "entry_sentence": "For a few minutes the building is all keys, bags, and people trying not to be late.",
                    "emphasis": "front",
                    "perimeter_bonus": 1.6,
                },
                {
                    "phase": "doorstep_drop",
                    "label": "doorstep drop",
                    "street_label": "a courier hovering at the entrance",
                    "entry_sentence": "A doorstep drop has pulled attention back toward the entrance and whoever is hurrying to meet it.",
                    "emphasis": "front",
                    "perimeter_bonus": 1.1,
                },
            )
        if phase == "settled_evening":
            return (
                {
                    "phase": "neighbors_lingering",
                    "label": "neighbors lingering",
                    "street_label": "people talking just outside the entrance",
                    "entry_sentence": "The evening has spilled out to the threshold, where a few people are stretching conversation before heading in.",
                    "emphasis": "residential",
                    "perimeter_bonus": 1.5,
                },
                {
                    "phase": "takeout_arrival",
                    "label": "takeout arrival",
                    "street_label": "delivery arrivals at the curb",
                    "entry_sentence": "A takeout arrival is briefly making the front edge feel more social than private.",
                    "emphasis": "front",
                    "perimeter_bonus": 1.2,
                },
                {
                    "phase": "tenant_meetup",
                    "label": "tenant meetup",
                    "street_label": "a new tenant and neighbors comparing notes",
                    "entry_sentence": "A new tenant meetup has brought a few people down to the stoop, half introductions and half practical advice about the building.",
                    "emphasis": "residential",
                    "perimeter_bonus": 1.4,
                },
                {
                    "phase": "mutual_aid_table",
                    "label": "mutual aid table",
                    "street_label": "volunteers sharing supplies near the stoop",
                    "entry_sentence": "A small mutual aid table is making the frontage feel like a soft landing spot instead of a pass-through.",
                    "emphasis": "residential",
                    "perimeter_bonus": 1.6,
                },
            )

    if open_now or phase == "active_floor":
        return (
            {
                "phase": "brief_pickup",
                "label": "brief pickup stop",
                "street_label": "a short pickup lingering at the door",
                "entry_sentence": "A brief pickup is momentarily pulling activity back toward the entrance.",
                "emphasis": "front",
                "perimeter_bonus": 1.0,
            },
            {
                "phase": "maintenance_loop",
                "label": "maintenance loop",
                "street_label": "tools and staff slipping in and out",
                "entry_sentence": "A maintenance loop is making the place feel more improvised than settled.",
                "emphasis": "work",
                "perimeter_bonus": 0.6,
            },
            {
                "phase": "street_triage",
                "label": "street triage",
                "street_label": "someone being patched up near the entrance",
                "entry_sentence": "A sudden injury has turned the frontage into a rough treatment spot, with somebody working fast to keep a hurt person steady.",
                "emphasis": "front",
                "perimeter_bonus": 1.7,
            },
        )
    return ()


def _raw_building_micro_event_snapshot(sim, prop=None, structure=None, base_pulse=None):
    if sim is None:
        return {}

    prop = prop if isinstance(prop, dict) else None
    structure = structure if isinstance(structure, dict) else None
    base_pulse = base_pulse if isinstance(base_pulse, dict) else {}

    category = str(base_pulse.get("category", "") or "").strip().lower()
    phase = str(base_pulse.get("phase", "") or "").strip().lower()
    open_now = bool(base_pulse.get("open_now"))
    bucket = max(0, int(base_pulse.get("bucket", 0) or 0))
    hour = max(0, int(base_pulse.get("hour", 0) or 0))

    aftermath_event = _business_event_aftermath_micro_event(
        sim,
        prop=prop,
        structure=structure,
        base_pulse=base_pulse,
    )
    if isinstance(aftermath_event, dict) and str(aftermath_event.get("phase", "") or "").strip():
        return {
            "phase": str(aftermath_event.get("phase", "") or "").strip().lower(),
            "label": str(aftermath_event.get("label", "") or "").strip(),
            "street_label": str(aftermath_event.get("street_label", "") or "").strip(),
            "entry_sentence": str(aftermath_event.get("entry_sentence", "") or "").strip(),
            "emphasis": str(aftermath_event.get("emphasis", "") or "").strip().lower(),
            "perimeter_bonus": max(0.0, float(aftermath_event.get("perimeter_bonus", 0.0) or 0.0)),
        }
    events = list(_building_micro_event_pool(category, phase, open_now=open_now))
    if not events:
        return {}

    sceneable_events = []
    for event_item in events:
        if not isinstance(event_item, dict):
            continue
        event_phase = str(event_item.get("phase", "") or "").strip().lower()
        if _business_event_scene_blueprint(prop, {"event_phase": event_phase, "category": category}) is not None:
            sceneable_events.append(event_item)
    candidate_events = sceneable_events if sceneable_events else list(events)

    building_key = _building_id_from_property(prop) or _building_id_from_structure(structure) or str((prop or {}).get("id", "") or "").strip()
    seed = f"{getattr(sim, 'seed', 0)}:building-micro-event:{building_key}:{phase}:{hour}"
    rng = random.Random(seed)
    event = rng.choice(candidate_events)
    if not isinstance(event, dict):
        return {}

    event_phase = str(event.get("phase", "") or "").strip().lower()
    if event_phase in _BUSINESS_EVENT_DELIVERY_PHASES:
        rarity_rng = random.Random(f"{getattr(sim, 'seed', 0)}:building-micro-event-rarity:{building_key}:{event_phase}:{hour}")
        if rarity_rng.random() > 0.35:
            return {}
    rare_phase_chance = _BUSINESS_EVENT_RARE_PHASE_CHANCES.get(event_phase)
    if rare_phase_chance is not None:
        rarity_rng = random.Random(f"{getattr(sim, 'seed', 0)}:building-micro-event-rarity:{building_key}:{event_phase}:{hour}")
        if rarity_rng.random() > float(rare_phase_chance):
            return {}

    return {
        "phase": str(event.get("phase", "") or "").strip().lower(),
        "label": str(event.get("label", "") or "").strip(),
        "street_label": str(event.get("street_label", "") or "").strip(),
        "entry_sentence": str(event.get("entry_sentence", "") or "").strip(),
        "emphasis": str(event.get("emphasis", "") or "").strip().lower(),
        "perimeter_bonus": max(0.0, float(event.get("perimeter_bonus", 0.0) or 0.0)),
    }


def _building_regular_chunk_pulse_cache(sim):
    state = getattr(sim, "building_regular_chunk_pulse_cache", None)
    if not isinstance(state, dict):
        state = {}
        sim.building_regular_chunk_pulse_cache = state

    try:
        hour = int(_world_hour(sim)) % 24 if sim is not None else 0
    except (TypeError, ValueError):
        hour = 0
    token = (
        hour,
        len(getattr(sim, "properties", {}) or {}),
        int(_BUSINESS_EVENT_REGULAR_SCENE_CAP or 0),
    )
    if state.get("token") != token:
        state.clear()
        state["token"] = token
        state["winners"] = {}
    winners = state.get("winners")
    if not isinstance(winners, dict):
        winners = {}
        state["winners"] = winners
    return winners


def _base_building_pulse_snapshot(sim, prop=None, structure=None):
    prop = prop if isinstance(prop, dict) else None
    structure = structure if isinstance(structure, dict) else None
    metadata = _property_metadata(prop)
    archetype = str(
        metadata.get("archetype", (structure or {}).get("archetype", "")) or ""
    ).strip().lower()
    category = _location_building_category(
        archetype,
        storefront=bool(prop and _property_is_storefront(prop)),
    )
    try:
        hour = int(_world_hour(sim)) % 24 if sim is not None else 12
    except (TypeError, ValueError):
        hour = 12
    tick_snapshot = _building_tick_snapshot(sim)
    bucket = int(tick_snapshot.get("bucket", 0) or 0)
    minute = int(tick_snapshot.get("minute", 0) or 0)

    status_text = ""
    if sim is not None and prop is not None:
        status_text = str(_property_status_text(sim, prop, hour=hour)).strip().lower()
    open_now = status_text == "open"

    phase = "steady"
    label = "steady rhythm"
    street_label = "steady foot traffic"
    entry_sentence = "The place is holding its ordinary rhythm right now."
    emphasis = "front" if open_now else "secure"

    if category in {"retail", "finance", "office"}:
        if open_now and 7 <= hour < 10:
            phase = "opening"
            label = "opening hour"
            street_label = "front waking up"
            entry_sentence = "At this hour the place feels like it is still gathering itself, with most of the motion collecting near the front."
            emphasis = "front"
        elif open_now and 11 <= hour < 14:
            phase = "rush"
            label = "midday rush"
            street_label = "traffic bunching at the front"
            entry_sentence = "Right now the place feels caught in a midday rush, with the front edge carrying more motion than the deeper rooms can fully hide."
            emphasis = "front"
        elif open_now and 15 <= hour < 18:
            phase = "back_office"
            label = "back-room churn"
            street_label = "quieter frontage, busier back rooms"
            entry_sentence = "The public face feels thinner right now while the real work slips deeper into the building."
            emphasis = "admin"
        elif open_now:
            phase = "steady_trade"
            label = "steady trade"
            street_label = "working pace at the front"
            entry_sentence = "The place is moving at working pace right now, more routine than spectacle."
            emphasis = "front"
        else:
            phase = "after_hours"
            label = "after hours"
            street_label = "dark front, watchful interior"
            entry_sentence = "At this hour the place feels more locked into itself than open to the street."
            emphasis = "secure"
    elif category in {"hospitality", "entertainment"}:
        if category == "hospitality" and 6 <= hour < 11:
            phase = "prep"
            label = "prep cycle"
            street_label = "setup and reset work"
            entry_sentence = "The public side is only part of the story right now; most of the energy feels like setup, cleanup, and short service loops."
            emphasis = "work"
        elif open_now and category == "hospitality" and 11 <= hour < 14:
            phase = "lunch_rush"
            label = "lunch rush"
            street_label = "crowd pressing the front"
            entry_sentence = "Right now the place feels caught in a meal rush, with the front doing everything it can to stay ahead of the back rooms."
            emphasis = "front"
        elif open_now and 17 <= hour < 23:
            phase = "evening_crowd"
            label = "evening crowd"
            street_label = "voices and traffic at the front"
            entry_sentence = "The building feels tilted toward the public rooms right now, as if the whole place is leaning into whoever just came through the door."
            emphasis = "hospitality"
        elif open_now and (hour >= 23 or hour < 3):
            phase = "late_buzz"
            label = "late buzz"
            street_label = "late traffic and lingering bodies"
            entry_sentence = "At this hour the place feels stretched into its late rhythm, all lingering voices, short service loops, and slower exits."
            emphasis = "front"
        elif open_now:
            phase = "cleanup"
            label = "cleanup cycle"
            street_label = "quiet front, active reset"
            entry_sentence = "The front is calmer right now, but the support spaces still feel busy with reset work."
            emphasis = "work"
        else:
            phase = "after_hours"
            label = "after hours"
            street_label = "shut frontage and faint after-hours motion"
            entry_sentence = "At this hour, without the public flow, the place feels more like a held interior than an invitation."
            emphasis = "secure"
    elif category in {"industrial", "transit"}:
        if 5 <= hour < 9:
            phase = "receiving"
            label = "receiving window"
            street_label = "handoff traffic and loading work"
            entry_sentence = "The building feels tuned to handoff right now, with short purposeful movement replacing any sense of lingering."
            emphasis = "work"
        elif open_now and 9 <= hour < 16:
            phase = "shift_work"
            label = "shift churn"
            street_label = "steady operational traffic"
            entry_sentence = "Everything here feels locked into active throughput right now: tasks landing, getting handled, and moving on."
            emphasis = "work"
        elif open_now and 16 <= hour < 19:
            phase = "handoff"
            label = "handoff hour"
            street_label = "between-shift movement"
            entry_sentence = "The place feels between shifts right now, all short exchanges, delayed exits, and one task handing off to the next."
            emphasis = "admin" if category == "industrial" else "transit"
        elif open_now:
            phase = "steady_ops"
            label = "steady operations"
            street_label = "working yard pace"
            entry_sentence = "The site feels busy in a practical way right now, more throughput than display."
            emphasis = "work"
        else:
            phase = "locked_down"
            label = "locked down"
            street_label = "quiet yard and sealed doors"
            entry_sentence = "At this hour the useful motion has dropped away, leaving the place feeling more controlled than alive."
            emphasis = "secure"
    elif category == "medical":
        if 7 <= hour < 10:
            phase = "intake"
            label = "intake wave"
            street_label = "people sorting at the front"
            entry_sentence = "Right now the place feels caught in intake, with movement clustering near the front before the deeper rooms can absorb it."
            emphasis = "front"
        elif 10 <= hour < 18:
            phase = "treatment"
            label = "treatment hours"
            street_label = "steady clinical traffic"
            entry_sentence = "The place is moving with procedural focus right now, all treatment rooms, short handoffs, and purposeful waiting."
            emphasis = "medical"
        elif open_now:
            phase = "night_watch"
            label = "night watch"
            street_label = "quiet entrance, active interior"
            entry_sentence = "At this hour the public edge is quiet, but the deeper rooms still feel actively watched."
            emphasis = "secure"
        else:
            phase = "after_hours"
            label = "after hours"
            street_label = "held quiet behind the threshold"
            entry_sentence = "At this hour the place feels more held in reserve than open to the street."
            emphasis = "secure"
    elif category == "secure":
        if 7 <= hour < 10:
            phase = "intake"
            label = "processing hour"
            street_label = "people being sorted at the secure front"
            entry_sentence = "The site feels caught in controlled processing right now, with movement stopping at the front before it can go anywhere else."
            emphasis = "front"
        elif 10 <= hour < 17:
            phase = "controlled_ops"
            label = "controlled operations"
            street_label = "guarded movement inside the perimeter"
            entry_sentence = "Everything here feels organized around observation, procedure, and slow deliberate motion."
            emphasis = "secure"
        elif 17 <= hour < 20:
            phase = "handoff"
            label = "custody turnover"
            street_label = "between-shift pressure at the gate"
            entry_sentence = "The place feels between watches right now, all clipped orders, delayed exits, and controlled handoffs."
            emphasis = "admin"
        else:
            phase = "night_watch"
            label = "night watch"
            street_label = "sealed frontage under watch"
            entry_sentence = "At this hour the site feels less closed than actively held, like the perimeter itself is still on duty."
            emphasis = "secure"
    elif category == "residential":
        if 6 <= hour < 9:
            phase = "starting_day"
            label = "starting day"
            street_label = "early household movement"
            entry_sentence = "The building feels like it is just pulling itself into the day, with routine doing more shaping than any formal design."
            emphasis = "residential"
        elif 18 <= hour < 23:
            phase = "settled_evening"
            label = "lived-in evening"
            street_label = "windows bright and people settling in"
            entry_sentence = "At this hour the place feels more lived-in than transactional, like routine has taken full possession of the rooms."
            emphasis = "residential"
        else:
            phase = "quiet_hours"
            label = "quiet hours"
            street_label = "low-light household quiet"
            entry_sentence = "The building has gone quiet in a way that suggests people have settled into it rather than left it."
            emphasis = "residential"
    else:
        if open_now:
            phase = "active_floor"
            label = "active floor"
            street_label = "front moving at work pace"
            entry_sentence = "The place feels active right now, with most of the motion staying close enough to the front to read from the threshold."
            emphasis = "front"
        else:
            phase = "quiet_interior"
            label = "quiet interior"
            street_label = "still frontage"
            entry_sentence = "The building feels quieter than empty right now, as if the useful activity has retreated deeper in."
            emphasis = "secure"

    pulse = {
        "phase": phase,
        "label": label,
        "street_label": street_label,
        "entry_sentence": entry_sentence,
        "emphasis": emphasis,
        "hour": hour,
        "minute": minute,
        "bucket": bucket,
        "category": category,
        "open_now": bool(open_now),
        "event_phase": "",
        "event_label": "",
        "perimeter_bonus": 0.0,
    }
    return pulse


def _regular_building_micro_event_visible_property_ids(sim, chunk):
    if sim is None or not isinstance(chunk, (tuple, list)) or len(chunk) < 2:
        return ()
    try:
        chunk_key = (int(chunk[0]), int(chunk[1]))
    except (TypeError, ValueError):
        return ()

    winners = _building_regular_chunk_pulse_cache(sim)
    cached = winners.get(chunk_key)
    if cached is not None:
        return tuple(str(property_id or "").strip() for property_id in tuple(cached or ()) if str(property_id or "").strip())

    chance = _business_event_regular_chunk_hourly_chance(sim)
    if chance <= 0.0:
        winners[chunk_key] = ()
        return ()

    try:
        hour = int(_world_hour(sim)) % 24 if sim is not None else 0
    except (TypeError, ValueError):
        hour = 0
    activation_rng = random.Random(
        f"{getattr(sim, 'seed', 0)}:building-regular-chunk-active:{chunk_key[0]}:{chunk_key[1]}:{hour}"
    )
    if activation_rng.random() > chance:
        winners[chunk_key] = ()
        return ()

    candidates = []
    for prop in getattr(sim, "properties", {}).values():
        if not isinstance(prop, dict):
            continue
        if str(prop.get("kind", "") or "").strip().lower() != "building":
            continue
        try:
            prop_chunk = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
        except (TypeError, ValueError):
            continue
        if prop_chunk != chunk_key:
            continue

        base_pulse = _base_building_pulse_snapshot(sim, prop=prop)
        event = _raw_building_micro_event_snapshot(sim, prop=prop, base_pulse=base_pulse)
        event_phase = str(event.get("phase", "") or "").strip().lower()
        if not event_phase or event_phase in _BUSINESS_EVENT_AFTERMATH_PHASES:
            continue

        category = str(base_pulse.get("category", "") or "").strip().lower()
        if _business_event_scene_blueprint(prop, {"event_phase": event_phase, "category": category}) is None:
            continue

        property_id = str(prop.get("id", "") or "").strip()
        if not property_id:
            continue

        score = float(event.get("perimeter_bonus", 0.0) or 0.0)
        if _property_is_storefront(prop) or _property_is_public(prop):
            score += 0.75
        if _property_access_level(prop) == "public":
            score += 0.35
        candidates.append((
            -score,
            event_phase,
            property_id,
        ))

    candidates.sort()
    visible_count = max(0, int(_BUSINESS_EVENT_REGULAR_SCENE_CAP or 0))
    visible_ids = tuple(
        str(candidate[2] or "").strip()
        for candidate in candidates[:visible_count]
        if str(candidate[2] or "").strip()
    )
    winners[chunk_key] = visible_ids
    return visible_ids


def _building_micro_event_snapshot(sim, prop=None, structure=None, base_pulse=None, *, respect_chunk_cap=True):
    event = _raw_building_micro_event_snapshot(sim, prop=prop, structure=structure, base_pulse=base_pulse)
    if not event or not respect_chunk_cap:
        return event

    prop = prop if isinstance(prop, dict) else None
    if prop is None or sim is None:
        return event

    event_phase = str(event.get("phase", "") or "").strip().lower()
    if not event_phase or event_phase in _BUSINESS_EVENT_AFTERMATH_PHASES:
        return event

    category = str(((base_pulse or {}) if isinstance(base_pulse, dict) else {}).get("category", "") or "").strip().lower()
    if _business_event_scene_blueprint(prop, {"event_phase": event_phase, "category": category}) is None:
        return event

    try:
        prop_chunk = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
    except (TypeError, ValueError):
        return event

    property_id = str(prop.get("id", "") or "").strip()
    if not property_id:
        return event
    visible_ids = _regular_building_micro_event_visible_property_ids(sim, prop_chunk)
    if property_id not in visible_ids:
        return {}
    return event


def _building_pulse_snapshot(sim, prop=None, structure=None, *, respect_chunk_cap=True):
    pulse = _base_building_pulse_snapshot(sim, prop=prop, structure=structure)
    base_label = str(pulse.get("label", "") or "").strip()
    base_entry_sentence = str(pulse.get("entry_sentence", "") or "").strip()
    event = _building_micro_event_snapshot(
        sim,
        prop=prop,
        structure=structure,
        base_pulse=pulse,
        respect_chunk_cap=respect_chunk_cap,
    )
    if event:
        event_label = str(event.get("label", "") or "").strip()
        if event_label:
            pulse["label"] = f"{base_label} + {event_label}"
            pulse["event_label"] = event_label
        event_street = str(event.get("street_label", "") or "").strip()
        if event_street:
            pulse["street_label"] = event_street
        event_sentence = str(event.get("entry_sentence", "") or "").strip()
        if event_sentence:
            pulse["entry_sentence"] = f"{base_entry_sentence} {event_sentence}".strip()
        event_emphasis = str(event.get("emphasis", "") or "").strip().lower()
        if event_emphasis:
            pulse["emphasis"] = event_emphasis
        pulse["event_phase"] = str(event.get("phase", "") or "").strip().lower()
        try:
            pulse["perimeter_bonus"] = max(0.0, float(event.get("perimeter_bonus", 0.0) or 0.0))
        except (TypeError, ValueError):
            pulse["perimeter_bonus"] = 0.0
    return pulse


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


def _location_description_snapshot(sim, x, y, z):
    if sim is None or x is None or y is None or z is None:
        return {
            "prop": None,
            "structure": None,
            "building_token": "",
            "room_token": "",
        }

    try:
        x = int(x)
        y = int(y)
        z = int(z)
    except (TypeError, ValueError):
        return {
            "prop": None,
            "structure": None,
            "building_token": "",
            "room_token": "",
        }

    structure = sim.structure_at(x, y, z) if hasattr(sim, "structure_at") else None
    prop = _property_covering(sim, x, y, z)
    prop_kind = str((prop or {}).get("kind", "") or "").strip().lower()
    building_token = _building_id_from_property(prop) if prop_kind == "building" else ""
    if not building_token:
        building_token = _building_id_from_structure(structure)

    room_kind = str((structure or {}).get("room_kind", "") or "").strip().lower()
    room_token = ""
    if room_kind:
        try:
            floor = int((structure or {}).get("floor", z))
        except (TypeError, ValueError):
            floor = int(z)
        room_token = f"{building_token}:{floor}:{room_kind}" if building_token else f"{floor}:{room_kind}"

    return {
        "prop": prop if isinstance(prop, dict) else None,
        "structure": structure if isinstance(structure, dict) else None,
        "building_token": str(building_token or "").strip(),
        "room_token": room_token,
    }


def _property_knowledge_hint(sim, viewer_eid, prop):
    if not prop or viewer_eid is None:
        return ""

    knowledge = sim.ecs.get(PropertyKnowledge).get(viewer_eid)
    if not knowledge:
        return ""

    known = knowledge.known.get(prop["id"])
    if not known or float(known.get("confidence", 0.0)) < 0.5:
        return ""

    source_eid = known.get("source_eid")
    source_name = ""
    if source_eid is not None:
        source_name = _entity_display_name(sim, source_eid, title_case=True)

    lead_kind = str(known.get("lead_kind", "") or "").strip().lower()
    if lead_kind == "workplace":
        return f"known:{source_name} works here" if source_name else "known:workplace"
    if lead_kind == "owner":
        return f"known:{source_name} owns this" if source_name else "known:owner"
    if lead_kind == "hours":
        return f"known:{source_name} mentioned public hours" if source_name else "known:hours"
    if lead_kind == "location":
        return f"known:{source_name} placed this on your map" if source_name else "known:location"
    if lead_kind in {"access", "security"}:
        return f"known:{source_name} mentioned access" if source_name else "known:access"
    if lead_kind == "contraband":
        return f"known:{source_name} mentioned hot goods" if source_name else "known:contraband"

    owner_eid = known.get("owner_eid")
    if owner_eid == viewer_eid:
        return "known:your property"
    if owner_eid is not None:
        return "known:privately owned"

    owner_tag = str(known.get("owner_tag", "") or "").strip().lower()
    if owner_tag:
        return f"known:{owner_tag}"
    return ""


def _storefront_illegal_goods_signal(sim, prop):
    if not prop or not _property_is_storefront(prop):
        return None
    metadata = prop.get("metadata", {}) if isinstance(prop.get("metadata", {}), dict) else {}
    archetype = str(metadata.get("archetype", "")).strip().lower()
    if not archetype:
        return None

    profile = dict(getattr(TradeSystem, "STORE_PROFILES", {}).get(archetype, {}))
    weighted_pool = list(profile.get("item_pool", ()))
    if not weighted_pool:
        return None

    store_state = getattr(sim, "stores", {}).get(prop.get("id")) if isinstance(getattr(sim, "stores", {}), dict) else None
    actual_examples = []
    if isinstance(store_state, dict):
        for entry in store_state.get("entries", ()):
            item_id = str(entry.get("item_id", "")).strip().lower()
            if int(entry.get("stock", 0) or 0) <= 0:
                continue
            item_def = ITEM_CATALOG.get(item_id, {})
            if str(item_def.get("legal_status", "legal")).strip().lower() != "illegal":
                continue
            actual_examples.append(item_display_name(item_id))
    if actual_examples:
        unique_examples = []
        seen = set()
        for label in actual_examples:
            clean = str(label).strip()
            if not clean or clean in seen:
                continue
            seen.add(clean)
            unique_examples.append(clean)
        return {
            "confidence": 0.78,
            "examples": tuple(unique_examples[:3]),
            "source": "live_stock",
            "archetype": archetype,
        }

    market_profile = store_supply_profile(sim, prop)
    illegal_weight = 0.0
    total_weight = 0.0
    example_rows = []
    for item_id, weight in weighted_pool:
        item_def = ITEM_CATALOG.get(item_id, {})
        legal_status = str(item_def.get("legal_status", "legal")).strip().lower()
        if legal_status not in {"legal", "restricted", "illegal"}:
            legal_status = "legal"
        bias = item_market_bias(item_id, market_profile)
        adjusted_weight = max(0.0, float(weight) * max(0.1, float(bias.get("weight_mult", 1.0))))
        total_weight += adjusted_weight
        if legal_status != "illegal":
            continue
        illegal_weight += adjusted_weight
        example_rows.append((adjusted_weight, item_display_name(item_id)))
    if total_weight <= 0.0 or illegal_weight <= 0.0:
        return None

    example_rows.sort(key=lambda row: (-row[0], row[1]))
    examples = []
    seen = set()
    for _weight, label in example_rows:
        clean = str(label).strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        examples.append(clean)
        if len(examples) >= 3:
            break

    ratio = illegal_weight / total_weight
    if ratio < 0.14:
        return None
    return {
        "confidence": min(0.74, 0.48 + (ratio * 0.6)),
        "examples": tuple(examples),
        "source": "market_profile",
        "archetype": archetype,
    }
def _career_label(occupation, title_case=False):
    if not occupation:
        return ""

    label = str(getattr(occupation, "career", "") or "").replace("_", " ").strip()
    if not label:
        return ""
    return label.title() if title_case else label


def _disguise_role_label(role_id, *, title_case=False):
    label = str(role_id or "").replace("_", " ").strip()
    if not label:
        return "unknown" if not title_case else "Unknown"
    return label.title() if title_case else label


def _workplace_property(sim, occupation=None, routine=None):
    workplace = getattr(occupation, "workplace", None)
    if isinstance(workplace, dict):
        property_id = workplace.get("property_id")
        if property_id:
            prop = sim.properties.get(property_id)
            if prop:
                return prop

    work = getattr(routine, "work", None)
    if isinstance(work, (list, tuple)) and len(work) >= 3:
        prop = _property_covering(sim, int(work[0]), int(work[1]), int(work[2]))
        if prop:
            return prop

    return None

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

def _hud_status_label(text, fallback="Unknown"):
    label = str(text or "").strip().replace("_", " ")
    if not label:
        return str(fallback or "Unknown")
    return label.title()


def _hud_primary_status_chunks(sim, *, zoom_mode, active_z, player_pos, lighting_state, area_type, district_type, security):
    chunk_coord = getattr(sim, "active_chunk_coord", None)
    if chunk_coord:
        chunk_text = f"{int(chunk_coord[0])},{int(chunk_coord[1])}"
    else:
        chunk_text = "?,?"

    light_phase = _hud_status_label(lighting_state.get("phase", "day"), fallback="Day")
    time_label = str(lighting_state.get("time_label", "--:--")).strip() or "--:--"
    area_label = _hud_status_label(area_type, fallback="Unknown")
    district_label = _hud_status_label(district_type, fallback="")
    floor_text = _floor_label(active_z, long=True)

    view_only = False
    if zoom_mode == "overworld":
        records = getattr(sim, "overworld_view_only_by_eid", {})
        try:
            view_only = bool(records.get(int(getattr(sim, "player_eid", 0) or 0), False))
        except (TypeError, ValueError):
            view_only = False

    status_chunks = [
        "Map View" if zoom_mode == "overworld" and view_only else "In Vehicle" if zoom_mode == "overworld" else "On Foot",
        "Overworld Map" if zoom_mode == "overworld" and view_only else "Overworld" if zoom_mode == "overworld" else floor_text,
        f"Chunk {chunk_text}",
        f"Area {area_label}",
    ]
    if district_label and district_label.lower() != area_label.lower():
        status_chunks.append(f"District {district_label}")
    if str(security or "").strip() and str(security).strip() != "?":
        status_chunks.append(f"Security {security}")
    status_chunks.append(f"Time {time_label} {light_phase}")
    return status_chunks


def _sentence_from_note(note):
    text = str(note or "").strip()
    if not text:
        return ""
    text = text[:1].upper() + text[1:]
    if text[-1] not in ".!?":
        text += "."
    return text


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


def _status_modifier_brief_label(key, value):
    value = _float_or_default(value, 0.0)
    if abs(value) <= 0.0001:
        return ""

    if key == "ranged_accuracy_mult":
        return f"aim {value * 100.0:+.0f}%"
    if key == "projectile_spread_mod":
        return f"spread {int(round(value)):+d}"
    if key == "weapon_cooldown_mult":
        return f"fire {(-value) * 100.0:+.0f}%"
    if key == "melee_cooldown_mult":
        return f"melee rate {(-value) * 100.0:+.0f}%"
    if key == "ranged_damage_mult":
        return f"shot {value * 100.0:+.0f}%"
    if key == "melee_damage_mult":
        return f"melee {value * 100.0:+.0f}%"
    if key == "incoming_damage_mult":
        return f"guard {(-value) * 100.0:+.0f}%"
    if key == "armor_absorb_bonus":
        return f"armor {value * 100.0:+.0f}%"
    if key == "cover_absorb_bonus":
        return f"cover {value * 100.0:+.0f}%"
    if key == "suppression_resist_mult":
        return f"steady {value * 100.0:+.0f}%"
    if key == "move_speed_mult":
        return f"speed {value * 100.0:+.0f}%"
    if key == "hp_tick_delta":
        label = "regen" if value > 0.0 else "bleed"
        return f"{label} {value:+.2f}/t"
    if key == "assault_bias_delta":
        return f"push {value * 100.0:+.0f}%"
    if key == "retreat_bias_delta":
        return f"nerve {(-value) * 100.0:+.0f}%"
    return ""


def _status_modifier_summary_text(modifiers, *, limit=3):
    if not isinstance(modifiers, dict):
        return ""

    labels = []
    ordered_keys = (
        "ranged_accuracy_mult",
        "projectile_spread_mod",
        "weapon_cooldown_mult",
        "ranged_damage_mult",
        "melee_damage_mult",
        "incoming_damage_mult",
        "suppression_resist_mult",
        "move_speed_mult",
        "hp_tick_delta",
        "armor_absorb_bonus",
        "cover_absorb_bonus",
        "assault_bias_delta",
        "retreat_bias_delta",
    )
    for key in ordered_keys:
        if key not in modifiers:
            continue
        label = _status_modifier_brief_label(key, modifiers.get(key, 0.0))
        if label:
            labels.append(label)

    if not labels:
        return ""
    if len(labels) <= int(max(1, limit)):
        return ", ".join(labels)
    visible = labels[: int(max(1, limit))]
    visible.append(f"+{len(labels) - len(visible)} more")
    return ", ".join(visible)


def _status_effect_label(status, duration=0, modifiers=None, *, title=False, limit=3):
    status_name = _humanize_slug(status, title=title) or ("Effect" if title else "effect")
    try:
        duration = int(duration)
    except (TypeError, ValueError):
        duration = 0
    summary = _status_modifier_summary_text(modifiers, limit=limit)
    if duration > 0 and summary:
        return f"{status_name} {duration}t [{summary}]"
    if duration > 0:
        return f"{status_name} {duration}t"
    if summary:
        return f"{status_name} [{summary}]"
    return status_name


def _active_status_summary(effects, *, max_names=1, title=False):
    if not effects or not isinstance(getattr(effects, "active", None), dict):
        return "0"
    active = list(effects.active.items())
    if not active:
        return "0"
    active.sort(key=lambda item: (-_int_or_default(item[1].get("remaining", 0), 0), str(item[0])))
    labels = [
        _humanize_slug(status, title=title) or ("Effect" if title else "effect")
        for status, _state in active
    ]
    max_names = max(1, int(max_names))
    if len(labels) <= max_names:
        return ", ".join(labels)
    visible = labels[:max_names]
    visible.append(f"+{len(labels) - max_names}")
    return " ".join(visible)

def _entity_status_move_speed_multiplier(sim, eid, *, base=1.0, minimum=0.2, maximum=3.0):
    try:
        speed = float(base)
    except (TypeError, ValueError):
        speed = 1.0

    return _status_multiplier(
        sim,
        eid,
        "move_speed_mult",
        base=speed,
        minimum=minimum,
        maximum=maximum,
    )


from game.input_system import InputSystem



def _building_site_service_seed_token(chunk_x, chunk_y, building, *, building_index=0):
    local_building_id = ""
    if isinstance(building, dict):
        local_building_id = str(building.get("building_id", "") or "").strip()
    if not local_building_id:
        local_building_id = str(int(building_index))
    return f"{int(chunk_x)}:{int(chunk_y)}:building:{local_building_id}"


def _site_service_seed_token(chunk_x, chunk_y, site, *, site_index=0):
    site_kind = "site"
    site_id = ""
    if isinstance(site, dict):
        site_kind = str(site.get("kind", site_kind)).strip().lower() or "site"
        site_id = str(site.get("site_id", "") or "").strip()
    if not site_id:
        site_id = str(int(site_index))
    return f"{int(chunk_x)}:{int(chunk_y)}:site:{site_kind}:{site_id}"


from game.world_progression_systems import WorldStreamingSystem



from game.world_progression_systems import QuestSystem



class NPCInteractionSystem(System):

    STATE_TEXT = {
        "idle": "between tasks",
        "patrolling": "on patrol",
        "resting": "taking it easy",
        "investigating": "watching the area",
        "protecting": "covering someone",
        "following": "watching your back",
        "holding": "holding position",
        "seeking_social": "looking for company",
        "seeking_companionship": "sticking close to a companion",
        "seeking_safety": "keeping their distance",
        "surrendered": "standing down",
    }
    ROOT_TOPICS = {"name", "job", "local", "opportunities", "attention", "contacts", "where_place", "hire", "fire", "trade", "bye", "purpose", "apologize", "leave"}
    MISSTEP_TOPICS = ("weird", "pry", "insult")
    MENU_REPEAT_ROW_BUDGET = 3
    REPEAT_PRESSURE_SKIP_TOPICS = {
        "bye",
        "trade",
        "purpose",
        "apologize",
        "leave",
        "payoff",
        "fence",
        "opportunities",
        "fallout",
        "objective",
        "angle",
        "risk",
        "attention",
        "hire_runner",
        "backup_orders",
        "backup_follow",
        "backup_hold",
        "backup_distract",
        "backup_goto_wait",
        "backup_wait_return",
        "backup_kill",
    }
    PAYOFF_BASE_COST = 40
    PAYOFF_COOLDOWN_TICKS = 800
    FENCE_COOLDOWN_TICKS = 600
    FENCE_MIN_STANDING = 0.42
    FENCE_MIN_CORRUPTION = 0.45
    CONTRACTOR_COST = 60
    CONTRACTOR_DURATION = 240   # ticks of bought backup
    CONTRACTOR_MIN_STANDING = 0.35
    CONTRACTOR_MIN_CORRUPTION = 0.30
    FALLOUT_MIN_STANDING = 0.28
    SIDE_JOB_MIN_STANDING = 0.44
    SIDE_JOB_COOLDOWN_TICKS = 240
    SIDE_JOB_KINDS = ("issuer_delivery", "issuer_pickup", "issuer_procure", "issuer_pressure")
    SIDE_JOB_ITEM_POOL = (
        "credstick_chip",
        "street_ration",
        "med_gel",
        "micro_medkit",
        "trauma_foam",
        "hydration_salts",
        "transit_daypass",
        "access_badge",
        "lockpick_kit",
        "pocket_multitool",
        "light_ammo_box",
    )
    CONTRACTOR_DISTRACTION_TICKS = 24
    CONTRACTOR_RETURN_WAIT_TICKS = 20
    CONTRACTOR_KILL_SURCHARGE = 90
    SERVICE_LOCATOR_SEARCH_RADIUS = 8
    OUTFITTER_LOCATOR_ARCHETYPES = ("outfitter", "surplus_store")
    JUSTICE_LOCATOR_ARCHETYPES = ("jail", "courthouse", "prison")
    JUSTICE_LOCATOR_ROLE_TOKENS = ("guard", "corrections", "deputy", "bailiff", "sergeant")
    SERVICE_LOCATOR_TOPICS = {
        "service_fuel": {
            "services": ("fuel",),
            "service_label": "fuel",
            "offer_label": "fuel",
            "lead_kind": "service_fuel",
        },
        "service_repair": {
            "services": ("repair",),
            "service_label": "repair shop",
            "offer_label": "vehicle repair",
            "lead_kind": "service_repair",
        },
        "service_banking": {
            "services": ("banking",),
            "service_label": "bank or broker",
            "offer_label": "banking or brokerage",
            "lead_kind": "service_banking",
        },
        "service_insurance": {
            "services": ("insurance",),
            "service_label": "insurer",
            "offer_label": "coverage or claims",
            "lead_kind": "service_insurance",
        },
        "service_rest": {
            "services": ("rest", "shelter"),
            "service_label": "lodging",
            "offer_label": "lodging",
            "lead_kind": "service_rest",
        },
        "service_transit": {
            "services": tuple(TRANSIT_SERVICE_IDS),
            "service_label": "transit stop",
            "offer_label": "transit",
            "lead_kind": "service_transit",
            "local_summary": "In this chunk, {names_text} can put you onto the transit network.",
            "near_summary": "Nearest transit stop I know is {distance_phrase} at {names_text}.",
        },
        "service_rail": {
            "services": ("rail_transit",),
            "service_label": "rail station",
            "offer_label": "rail travel",
            "lead_kind": "service_rail",
            "local_summary": "In this chunk, {names_text} can put you on a rail line.",
            "near_summary": "Nearest rail station I know is {distance_phrase} at {names_text}.",
        },
        "service_bus": {
            "services": ("bus_transit",),
            "service_label": "bus stop",
            "offer_label": "bus travel",
            "lead_kind": "service_bus",
            "local_summary": "In this chunk, {names_text} posts bus routes.",
            "near_summary": "Nearest bus stop I know is {distance_phrase} at {names_text}.",
        },
        "service_shuttle": {
            "services": ("shuttle_transit",),
            "service_label": "shuttle stop",
            "offer_label": "shuttle travel",
            "lead_kind": "service_shuttle",
            "local_summary": "In this chunk, {names_text} posts shuttle transfers.",
            "near_summary": "Nearest shuttle stop I know is {distance_phrase} at {names_text}.",
        },
        "service_ferry": {
            "services": ("ferry_transit",),
            "service_label": "ferry landing",
            "offer_label": "ferry travel",
            "lead_kind": "service_ferry",
            "local_summary": "In this chunk, {names_text} posts ferry departures.",
            "near_summary": "Nearest ferry landing I know is {distance_phrase} at {names_text}.",
        },
        "service_intel": {
            "services": ("intel",),
            "service_label": "intel",
            "offer_label": "intel",
            "lead_kind": "service_intel",
        },
        "service_trade": {
            "services": (),
            "service_label": "shopping spot",
            "offer_label": "shopping",
            "lead_kind": "service_trade",
            "storefront": True,
        },
        "service_outfitter": {
            "services": (),
            "service_label": "outfitter",
            "offer_label": "gear and clothing",
            "lead_kind": "service_outfitter",
            "archetypes": OUTFITTER_LOCATOR_ARCHETYPES,
        },
        "service_justice": {
            "services": (),
            "service_label": "justice site",
            "offer_label": "booking or court business",
            "lead_kind": "service_justice",
            "archetypes": JUSTICE_LOCATOR_ARCHETYPES,
            "local_summary": "In this chunk, {names_text} handles booking and court business.",
            "near_summary": "Nearest justice site I know is {distance_phrase} at {names_text}.",
        },
        "service_used_cars": {
            "services": ("vehicle_sales_used",),
            "service_label": "used-car spot",
            "offer_label": "used vehicles",
            "lead_kind": "service_used_cars",
        },
        "service_vehicle_fetch": {
            "services": ("vehicle_fetch",),
            "service_label": "vehicle retrieval service",
            "offer_label": "vehicle retrieval",
            "lead_kind": "service_vehicle_fetch",
        },
        "service_gaming": {
            "services": tuple(CASINO_GAME_SERVICE_IDS),
            "service_label": "gaming spot",
            "offer_label": "gaming",
            "lead_kind": "service_gaming",
            "archetypes": ("casino", "gaming_hall"),
        },
    }

    def __init__(self, sim, player_eid, repeat_cooldown=18):
        super().__init__(sim)
        self.player_eid = player_eid
        self.repeat_cooldown = max(1, int(repeat_cooldown))
        self.last_interaction_tick = {}
        if not hasattr(self.sim, "dialog_ui"):
            self.sim.dialog_ui = {
                "open": False,
                "npc_eid": None,
                "title": "Conversation",
                "subtitle": "",
                "transcript": [],
                "topics": [],
                "selected_index": 0,
                "scroll": 0,
                "hint": "",
                "new_topic_ids": [],
                "close_pending": False,
            }
        if not hasattr(self.sim, "dialogue_history"):
            self.sim.dialogue_history = {}
        if not hasattr(self.sim, "dialogue_guard_grace"):
            self.sim.dialogue_guard_grace = {}
        if not hasattr(self, "payoff_cooldown_ticks"):
            self.payoff_cooldown_ticks = {}
        if not hasattr(self, "fence_cooldown_ticks"):
            self.fence_cooldown_ticks = {}
        self.sim.events.subscribe("npc_interact", self.on_npc_interact)
        self.sim.events.subscribe("dialog_topic_request", self.on_dialog_topic_request)
        self.sim.events.subscribe("dialog_close_request", self.on_dialog_close_request)
        self.sim.events.subscribe("contractor_hired", self.on_contractor_hired)
        self.sim.events.subscribe("entity_moved", self.on_entity_moved)
        self.sim.events.subscribe("entity_damaged", self.on_entity_damaged)
        self.sim.events.subscribe("npc_downed", self.on_npc_downed)
        self.sim.events.subscribe("npc_killed", self.on_npc_killed)

    def _dialog_ui_state(self):
        state = getattr(self.sim, "dialog_ui", None)
        if not isinstance(state, dict):
            state = {
                "open": False,
                "npc_eid": None,
                "title": "Conversation",
                "subtitle": "",
                "transcript": [],
                "topics": [],
                "selected_index": 0,
                "scroll": 0,
                "hint": "",
                "new_topic_ids": [],
                "close_pending": False,
                "backup_cursor_mark": None,
                "backup_cursor_pending_topic": "",
            }
            self.sim.dialog_ui = state
        else:
            state.setdefault("subtitle", "")
            state.setdefault("transcript", [])
            state.setdefault("topics", [])
            state.setdefault("selected_index", 0)
            state.setdefault("scroll", 0)
            state.setdefault("hint", "")
            state.setdefault("new_topic_ids", [])
            state.setdefault("close_pending", False)
            state.setdefault("backup_cursor_mark", None)
            state.setdefault("backup_cursor_pending_topic", "")
        return state

    def _dialogue_history_map(self):
        history = getattr(self.sim, "dialogue_history", None)
        if not isinstance(history, dict):
            history = {}
            self.sim.dialogue_history = history
        return history

    def _guard_grace_state(self):
        return _dialogue_guard_grace_state(self.sim)

    def _dialogue_memory(self, npc_eid):
        history = self._dialogue_history_map()
        try:
            key = int(npc_eid)
        except (TypeError, ValueError):
            key = npc_eid
        memory = history.get(key)
        if not isinstance(memory, dict):
            memory = {
                "opened_count": 0,
                "last_tick": -1,
                "last_topic_id": "",
                "topic_counts": {},
                "topic_family_counts": {},
                "unlocked_topics": set(),
                "last_property_id": "",
                "last_property_lead_kind": "",
                "last_property_source_eid": None,
            }
            history[key] = memory
            return memory
        if not isinstance(memory.get("topic_counts"), dict):
            memory["topic_counts"] = {}
        _dialogue_family_counts(memory)
        unlocked = memory.get("unlocked_topics")
        if isinstance(unlocked, set):
            pass
        elif isinstance(unlocked, (list, tuple)):
            memory["unlocked_topics"] = {
                str(topic).strip().lower()
                for topic in unlocked
                if str(topic).strip()
            }
        else:
            memory["unlocked_topics"] = set()
        memory.setdefault("opened_count", 0)
        memory.setdefault("last_tick", -1)
        memory.setdefault("last_topic_id", "")
        memory.setdefault("last_property_id", "")
        memory.setdefault("last_property_lead_kind", "")
        memory.setdefault("last_property_source_eid", None)
        return memory

    def _guard_grace_key(self, npc_eid, prop):
        return _dialogue_guard_grace_key(npc_eid, prop)

    def _guard_grace_active(self, npc_eid, prop):
        return _dialogue_guard_grace_active(self.sim, npc_eid, prop)

    def _grant_guard_grace(self, npc_eid, prop, *, duration=18, tactic=""):
        return _grant_dialogue_guard_grace(
            self.sim,
            npc_eid,
            prop,
            duration=duration,
            tactic=tactic,
        )

    def _clear_guarded_memory(self, npc_eid, *, guarded_prop=None, recent_offense=None):
        memory = self.sim.ecs.get(NPCMemory).get(npc_eid)
        if not memory or not memory.entries:
            return False

        prop_id = str(guarded_prop.get("id", "")).strip() if isinstance(guarded_prop, dict) else ""
        recent_tick = None
        if isinstance(recent_offense, dict):
            try:
                recent_tick = int(recent_offense.get("tick", -1))
            except (TypeError, ValueError):
                recent_tick = -1

        kept = []
        removed = False
        for entry in memory.entries:
            if recent_offense is not None and entry is recent_offense:
                removed = True
                continue

            kind = str(entry.get("kind", "")).strip().lower()
            data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
            if data.get("offender_eid") != self.player_eid:
                kept.append(entry)
                continue

            entry_prop_id = str(data.get("property_id", "")).strip()
            if kind == "property_threat" and prop_id and entry_prop_id == prop_id:
                removed = True
                continue
            if kind == "offense":
                if prop_id and entry_prop_id == prop_id:
                    removed = True
                    continue
                if recent_tick is not None:
                    try:
                        entry_tick = int(entry.get("tick", -2))
                    except (TypeError, ValueError):
                        entry_tick = -2
                    if entry_tick == recent_tick:
                        removed = True
                        continue

            kept.append(entry)

        if removed:
            memory.entries = kept
        return removed

    def _clear_guarded_aggression(self, npc_eid, *, guarded_prop=None):
        grace_active = _dialogue_guard_grace_active(self.sim, npc_eid, guarded_prop)
        changed = False

        ai = self.sim.ecs.get(AI).get(npc_eid)
        if ai:
            state = str(ai.state or "").strip().lower()
            if state in THREAT_STATES and (grace_active or ai.target_eid == self.player_eid):
                ai.state = "idle"
                ai.target = None
                ai.target_eid = None
                changed = True

        will = self.sim.ecs.get(NPCWill).get(npc_eid)
        if will:
            intent = str(will.intent or "").strip().lower()
            if intent in THREAT_STATES and (grace_active or will.target_eid == self.player_eid):
                will.intent = "idle"
                will.score = 0.0
                will.target = None
                will.target_eid = None
                will.last_tick = self.sim.tick
                changed = True

        return changed

    def _ensure_dialogue_bond(self, npc_eid, *, guarded=False):
        social = self.sim.ecs.get(NPCSocial).get(npc_eid)
        if not social:
            return None
        bond = social.bonds.get(self.player_eid)
        if bond:
            return bond
        social.add_bond(
            self.player_eid,
            kind="neighbor",
            closeness=0.08 if guarded else 0.18,
            trust=0.1 if guarded else 0.22,
            protectiveness=0.14 if guarded else 0.18,
        )
        return social.bonds.get(self.player_eid)

    def _shift_dialogue_bond(self, npc_eid, *, trust_delta=0.0, closeness_delta=0.0, guarded=False):
        if abs(float(trust_delta)) < 0.0001 and abs(float(closeness_delta)) < 0.0001:
            return None
        bond = self._ensure_dialogue_bond(npc_eid, guarded=guarded)
        if not bond:
            return None
        bond["trust"] = max(0.0, min(0.98, float(bond.get("trust", 0.0)) + float(trust_delta)))
        bond["closeness"] = max(0.0, min(0.98, float(bond.get("closeness", 0.0)) + float(closeness_delta)))
        return bond

    def _recently_interacted(self, npc_eid):
        key = (self.player_eid, int(npc_eid))
        last_tick = int(self.last_interaction_tick.get(key, -999999))
        return (self.sim.tick - last_tick) < self.repeat_cooldown

    def _mark_interacted(self, npc_eid):
        self.last_interaction_tick[(self.player_eid, int(npc_eid))] = self.sim.tick

    def _state_text(self, ai):
        if not ai:
            return "hard to read"
        state = str(ai.state or "idle").strip().lower() or "idle"
        return self.STATE_TEXT.get(state, state.replace("_", " "))

    def _dialogue_topic_count(self, npc_eid, topic_id):
        topic_key = str(topic_id or "").strip().lower()
        if not topic_key:
            return 0
        topic_counts = self._dialogue_memory(npc_eid)["topic_counts"]
        try:
            return max(0, int(topic_counts.get(topic_key, 0)))
        except (TypeError, ValueError):
            return 0

    def _dialogue_topic_family_count(self, npc_eid, topic_id):
        family_key = _dialogue_topic_family(topic_id)
        if not family_key:
            return 0
        counts = _dialogue_family_counts(self._dialogue_memory(npc_eid))
        try:
            return max(0, int(counts.get(family_key, 0)))
        except (TypeError, ValueError):
            return 0

    def _dialogue_mark_topic(self, npc_eid, topic_id):
        topic_key = str(topic_id or "").strip().lower()
        if not topic_key:
            return 0
        memory = self._dialogue_memory(npc_eid)
        count = self._dialogue_topic_count(npc_eid, topic_key) + 1
        memory["topic_counts"][topic_key] = count
        family_key = _dialogue_topic_family(topic_key)
        if family_key:
            family_counts = _dialogue_family_counts(memory)
            family_counts[family_key] = self._dialogue_topic_family_count(npc_eid, topic_key) + 1
        memory["last_topic_id"] = topic_key
        return count

    def _dialogue_total_topics_asked(self, npc_eid):
        topic_counts = self._dialogue_memory(npc_eid)["topic_counts"]
        total = 0
        for value in topic_counts.values():
            try:
                total += max(0, int(value))
            except (TypeError, ValueError):
                continue
        return total

    def _dialogue_misstep_count(self, npc_eid):
        topic_counts = self._dialogue_memory(npc_eid)["topic_counts"]
        total = 0
        for topic_id in self.MISSTEP_TOPICS:
            try:
                total += max(0, int(topic_counts.get(topic_id, 0)))
            except (TypeError, ValueError):
                continue
        return total

    def _dialogue_unlock_topics(self, npc_eid, *topic_ids):
        unlocked = self._dialogue_memory(npc_eid)["unlocked_topics"]
        for topic_id in topic_ids:
            topic_key = str(topic_id or "").strip().lower()
            if topic_key:
                unlocked.add(topic_key)
        return unlocked

    def _dialogue_repeat_row_count(self, context, topic_id, ask_count):
        topic_id = str(topic_id or "").strip().lower()
        ask_count = max(0, int(ask_count))
        if ask_count <= 0 or bool(context.get("guarded")):
            return 0
        if topic_id in self.REPEAT_PRESSURE_SKIP_TOPICS or topic_id in self.MISSTEP_TOPICS:
            return 0
        family_count = self._dialogue_topic_family_count(context.get("npc_eid"), topic_id)
        pressure_count = max(ask_count, family_count)
        if pressure_count <= 0:
            return 0
        extra = 1
        if pressure_count >= 3:
            extra += 1
        return extra

    def _dialogue_row_key(self, row):
        if not isinstance(row, dict):
            return None
        topic_id = str(row.get("id", "")).strip().lower()
        if not topic_id:
            return None
        try:
            repeat_slot = max(0, int(row.get("repeat_slot", 0) or 0))
        except (TypeError, ValueError):
            repeat_slot = 0
        return (topic_id, repeat_slot)

    def _dialogue_shuffle_rng(self, context, *, row_count=0):
        npc_eid = context.get("npc_eid") if isinstance(context, dict) else None
        memory = self._dialogue_memory(npc_eid)
        topic_counts = memory.get("topic_counts", {}) if isinstance(memory.get("topic_counts"), dict) else {}
        signature_bits = []
        for topic_id, count in sorted(topic_counts.items()):
            clean_topic = str(topic_id).strip().lower()
            if not clean_topic:
                continue
            try:
                clean_count = max(0, int(count))
            except (TypeError, ValueError):
                clean_count = 0
            signature_bits.append(f"{clean_topic}:{clean_count}")
        signature = "|".join(signature_bits)
        return random.Random(
            f"{self.sim.seed}:dialog-menu:{npc_eid}:{int(memory.get('opened_count', 0))}:"
            f"{self._dialogue_total_topics_asked(npc_eid)}:{str(memory.get('last_topic_id', '')).strip().lower()}:"
            f"{int(row_count)}:{signature}"
        )

    def _restore_dialog_selection(self, rows, *, preferred_row=None, fallback_index=0):
        state = self._dialog_ui_state()
        rows = list(rows or ())
        if not rows:
            state["selected_index"] = 0
            return 0

        preferred_key = self._dialogue_row_key(preferred_row)
        if preferred_key is not None:
            for idx, row in enumerate(rows):
                if self._dialogue_row_key(row) == preferred_key:
                    state["selected_index"] = idx
                    return idx

        preferred_topic_id = ""
        if isinstance(preferred_row, dict):
            preferred_topic_id = str(preferred_row.get("id", "")).strip().lower()
        if preferred_topic_id:
            for idx, row in enumerate(rows):
                if str(row.get("id", "")).strip().lower() == preferred_topic_id:
                    state["selected_index"] = idx
                    return idx

        selected_index = max(0, min(int(fallback_index), len(rows) - 1))
        state["selected_index"] = selected_index
        return selected_index

    def _current_dialog_selected_row(self):
        state = self._dialog_ui_state()
        rows = list(state.get("topics", ()) or ())
        if not rows:
            return None
        selected_index = max(0, min(int(state.get("selected_index", 0)), len(rows) - 1))
        return rows[selected_index]

    def _augment_repeat_dialogue_rows(self, context, rows):
        npc_eid = context.get("npc_eid") if isinstance(context, dict) else None
        if npc_eid is None:
            return list(rows or ())
        base_rows = [dict(row) for row in list(rows or ()) if isinstance(row, dict)]
        if not base_rows:
            return []

        last_topic_id = str(self._dialogue_memory(npc_eid).get("last_topic_id", "")).strip().lower()
        ranked = []
        for index, row in enumerate(base_rows):
            topic_id = str(row.get("id", "")).strip().lower()
            if not topic_id:
                continue
            ask_count = self._dialogue_topic_count(npc_eid, topic_id)
            extra = self._dialogue_repeat_row_count(context, topic_id, ask_count)
            if extra <= 0:
                continue
            ranked.append((
                0 if topic_id == last_topic_id else 1,
                -max(ask_count, self._dialogue_topic_family_count(npc_eid, topic_id)),
                index,
                topic_id,
                extra,
            ))

        ranked.sort()
        extras_by_topic = {}
        budget = max(0, int(self.MENU_REPEAT_ROW_BUDGET))
        for _recent_rank, _neg_count, _index, topic_id, extra in ranked:
            if budget <= 0:
                break
            take = min(int(extra), budget)
            if take <= 0:
                continue
            extras_by_topic[topic_id] = take
            budget -= take

        if not extras_by_topic:
            return base_rows

        base_indexes = {
            str(row.get("id", "")).strip().lower(): idx
            for idx, row in enumerate(base_rows)
            if str(row.get("id", "")).strip()
        }
        extra_rows = []
        for row in base_rows:
            topic_id = str(row.get("id", "")).strip().lower()
            for repeat_slot in range(extras_by_topic.get(topic_id, 0)):
                clone = dict(row)
                clone["repeat_slot"] = repeat_slot + 1
                clone["label"] = _repeated_topic_label(
                    row.get("label", row.get("id", "topic")),
                    topic_id=topic_id,
                    repeat_slot=repeat_slot + 1,
                    ask_count=self._dialogue_topic_count(npc_eid, topic_id),
                    family_count=self._dialogue_topic_family_count(npc_eid, topic_id),
                )
                extra_rows.append(clone)

        if not extra_rows:
            return base_rows

        rng = self._dialogue_shuffle_rng(
            context,
            row_count=len(base_rows) + len(extra_rows),
        )
        slots = [[] for _ in range(len(base_rows) + 1)]
        all_slot_indexes = list(range(len(slots)))
        for clone in extra_rows:
            topic_id = str(clone.get("id", "")).strip().lower()
            base_index = base_indexes.get(topic_id)
            candidate_slots = list(all_slot_indexes)
            if base_index is not None and len(candidate_slots) > 2:
                candidate_slots = [
                    slot_index
                    for slot_index in candidate_slots
                    if slot_index not in {base_index, base_index + 1}
                ] or candidate_slots
            slot_index = rng.choice(candidate_slots)
            slots[slot_index].append(clone)

        for bucket in slots:
            rng.shuffle(bucket)

        augmented = []
        for idx, row in enumerate(base_rows):
            augmented.extend(slots[idx])
            augmented.append(row)
        augmented.extend(slots[-1])
        return augmented

    def _bond_tone(self, bond):
        if not bond:
            return "neutral"
        score = (float(bond.get("closeness", 0.0)) * 0.45) + (float(bond.get("trust", 0.0)) * 0.55)
        if score < 0.25:
            return "wary"
        if score < 0.45:
            return "neutral"
        if score < 0.68:
            return "open"
        return "friendly"

    def _recent_player_offense(self, memory):
        if not memory:
            return None
        best = None
        for entry in memory.entries:
            if entry.get("kind") != "offense":
                continue
            if entry.get("data", {}).get("offender_eid") != self.player_eid:
                continue
            if self.sim.tick - int(entry.get("tick", 0)) > 220:
                continue
            if not best or float(entry.get("strength", 0.0)) > float(best.get("strength", 0.0)):
                best = entry
        return best

    def _current_trespass_property(self, npc_eid, player_pos):
        if not player_pos:
            return None
        prop = _property_covering(self.sim, player_pos.x, player_pos.y, player_pos.z)
        if not prop:
            return None
        if self._guard_grace_active(npc_eid, prop):
            return None
        npc_pos = self.sim.ecs.get(Position).get(npc_eid)
        if not npc_pos:
            return None
        _, claim_reason = _property_claim_reason(
            self.sim,
            npc_eid,
            prop,
            x=npc_pos.x,
            y=npc_pos.y,
            z=npc_pos.z,
            min_standing=0.58,
        )
        if not claim_reason:
            return None
        access = _evaluate_property_access(
            self.sim,
            self.player_eid,
            prop,
            x=player_pos.x,
            y=player_pos.y,
            z=player_pos.z,
        )
        if access.permitted or access.severity_score < 12:
            return None
        return prop

    def _remember_player_property_lead(self, prop, source_eid, lead_kind, confidence):
        changed = _remember_property_lead_for_actor(
            self.sim,
            self.player_eid,
            prop,
            source_eid=source_eid,
            lead_kind=lead_kind,
            confidence=confidence,
        )
        self._dialogue_mark_property_reference(
            source_eid,
            prop,
            lead_kind=lead_kind,
        )
        return changed

    def _dialogue_mark_property_reference(self, npc_eid, prop, *, lead_kind=""):
        if npc_eid is None or not isinstance(prop, dict):
            return False
        property_id = str(prop.get("id", "") or "").strip()
        if not property_id:
            return False
        memory = self._dialogue_memory(npc_eid)
        memory["last_property_id"] = property_id
        memory["last_property_lead_kind"] = str(lead_kind or "").strip().lower()
        memory["last_property_source_eid"] = npc_eid
        return True

    def _remember_player_contact(self, prop, source_eid, contact_kind, standing, benefits):
        if not prop:
            return False
        ledger = self.sim.ecs.get(ContactLedger).get(self.player_eid)
        if not ledger:
            return False
        existing = ledger.property_entry(prop["id"])
        prior_standing = float(existing.get("standing", 0.0)) if existing else 0.0
        prior_source = existing.get("source_eid") if existing else None
        prior_kind = str(existing.get("contact_kind", "") or "").strip().lower() if existing else ""
        prior_benefits = set(existing.get("benefits", ())) if existing else set()
        next_benefits = {str(bit).strip().lower() for bit in benefits if str(bit).strip()}
        ledger.remember(
            prop["id"],
            source_eid=source_eid,
            contact_kind=contact_kind,
            standing=standing,
            tick=self.sim.tick,
            benefits=next_benefits,
        )
        self._dialogue_mark_property_reference(
            source_eid,
            prop,
            lead_kind="contact",
        )
        return (
            existing is None
            or prior_source != source_eid
            or prior_kind != str(contact_kind or "").strip().lower()
            or next_benefits != prior_benefits
            or (prior_standing < 0.7 <= float(standing))
        )

    def _player_person_contact_entry(self, person_eid):
        return _person_contact_entry(self.sim, self.player_eid, person_eid)

    def _player_knows_person_name(self, person_eid):
        entry = self._player_person_contact_entry(person_eid)
        if not entry:
            return False
        benefits = {
            str(bit).strip().lower()
            for bit in tuple(entry.get("benefits", ()) or ())
            if str(bit).strip()
        }
        return bool(entry.get("introduced", False)) or "known_name" in benefits

    def _remember_player_person_contact(
        self,
        person_eid,
        *,
        source_eid,
        relation_kind,
        standing,
        property_id=None,
        introduced=False,
        benefits=(),
    ):
        if person_eid is None:
            return False
        ledger = self.sim.ecs.get(ContactLedger).get(self.player_eid)
        if not ledger:
            return False
        existing = ledger.person_entry(person_eid)
        prior_standing = float(existing.get("standing", 0.0)) if existing else 0.0
        prior_source = existing.get("source_eid") if existing else None
        prior_relation = str(existing.get("relation_kind", "") or "").strip().lower() if existing else ""
        prior_property = existing.get("property_id") if existing else None
        prior_intro = bool(existing.get("introduced", False)) if existing else False
        prior_benefits = set(existing.get("benefits", ())) if existing else set()
        next_benefits = {str(bit).strip().lower() for bit in benefits if str(bit).strip()}
        ledger.remember_person(
            person_eid,
            source_eid=source_eid,
            relation_kind=relation_kind,
            standing=standing,
            tick=self.sim.tick,
            property_id=property_id,
            benefits=next_benefits,
            introduced=introduced,
        )
        if property_id:
            prop = self.sim.properties.get(str(property_id))
            if isinstance(prop, dict):
                self._dialogue_mark_property_reference(
                    source_eid,
                    prop,
                    lead_kind="contact",
                )
        return (
            existing is None
            or prior_source != source_eid
            or prior_relation != str(relation_kind or "").strip().lower()
            or prior_property != property_id
            or prior_intro != bool(introduced)
            or next_benefits != prior_benefits
            or (prior_standing < 0.66 <= float(standing))
        )

    def _remember_revealed_social_lead_names(self, context, response):
        if not isinstance(context, dict) or not isinstance(response, dict):
            return
        npc_lines = tuple(response.get("npc_lines", ()) or ())
        if not npc_lines:
            return

        source_eid = context.get("npc_eid")
        standing = float(context.get("contact_standing", 0.0) or 0.0)
        for lead in tuple(context.get("social_leads", ()) or ()):
            if not isinstance(lead, dict):
                continue
            person_eid = lead.get("eid")
            name = str(lead.get("name", "")).strip()
            if person_eid is None or not name or self._player_knows_person_name(person_eid):
                continue
            pattern = re.compile(rf"(?<![A-Za-z0-9]){re.escape(name)}(?![A-Za-z0-9])", re.IGNORECASE)
            if not any(pattern.search(str(line)) for line in npc_lines):
                continue
            self._remember_player_person_contact(
                person_eid,
                source_eid=source_eid,
                relation_kind=lead.get("relation_kind"),
                standing=max(0.18, standing),
                property_id=lead.get("property_id"),
                introduced=False,
                benefits={"known_name"},
            )

    def _contact_standing(self, bond, rapport):
        trust = float((bond or {}).get("trust", 0.0))
        closeness = float((bond or {}).get("closeness", 0.0))
        bond_score = (trust * 0.6) + (closeness * 0.4)
        rapport = max(0.0, min(1.0, float(rapport or 0.0)))
        return max(0.0, min(0.96, 0.12 + (bond_score * 0.52) + (rapport * 0.42)))

    def _pressure_adjusted_tone(self, tone, *, pressure_tier="low", standing=0.0, recent_offense=False):
        tone_key = str(tone or "neutral").strip().lower() or "neutral"
        if tone_key == "guarded":
            return tone_key
        tone_order = ("wary", "neutral", "open", "friendly")
        if tone_key not in tone_order:
            tone_key = "neutral"
        standing = max(0.0, min(1.0, float(standing or 0.0)))
        pressure_tier = str(pressure_tier or "low").strip().lower() or "low"
        severity = 0
        if pressure_tier == "medium" and standing < 0.54:
            severity = 1
        elif pressure_tier == "high":
            severity = 2 if standing < 0.5 else 1
        if recent_offense and pressure_tier in {"medium", "high"}:
            severity += 1
        if severity <= 0:
            return tone_key
        index = max(0, tone_order.index(tone_key) - severity)
        return tone_order[index]

    def _dialogue_pressure_role(self, context):
        role_id = str(context.get("role_id", "") or "").strip().lower()
        career_text = str(context.get("career_text", "") or "").strip().lower()
        organization_kind = str(context.get("organization_kind", "") or "").strip().lower()
        service_summary = str(context.get("service_summary", "") or "").strip().lower()
        trade_available = bool(context.get("trade_available"))
        workplace_prop = context.get("workplace_prop")
        home_prop = context.get("home_prop")
        current_prop = context.get("current_prop")

        if role_id == "guard" or "guard" in career_text or "security" in career_text:
            return "guard"
        if bool(context.get("is_rival_operator")):
            return "chaotic"

        chaotic_terms = (
            "gang",
            "gang_member",
            "criminal",
            "thug",
            "raider",
            "bandit",
            "outlaw",
            "smuggler",
            "runner",
            "hustler",
            "scavenger",
            "thief",
            "crook",
        )
        if (
            role_id in chaotic_terms
            or any(term in career_text for term in chaotic_terms)
            or organization_kind in {"gang", "crew", "criminal"}
        ):
            return "chaotic"

        merchant_terms = (
            "shopkeeper",
            "clerk",
            "cashier",
            "vendor",
            "merchant",
            "broker",
            "dealer",
            "bartender",
            "pit boss",
        )
        if trade_available or "trade" in service_summary or any(term in career_text for term in merchant_terms):
            return "merchant"

        if role_id in {"resident", "neighbor"}:
            return "neighbor"

        home_id = str((home_prop or {}).get("id", "")).strip() if isinstance(home_prop, dict) else ""
        current_id = str((current_prop or {}).get("id", "")).strip() if isinstance(current_prop, dict) else ""
        if home_id and current_id and home_id == current_id and not workplace_prop:
            return "neighbor"

        if workplace_prop:
            return "worker"
        if home_prop:
            return "neighbor"
        return "local"

    def _pressure_contact_bank(self, base_bank_id, context):
        role = str(context.get("pressure_role", "") or self._dialogue_pressure_role(context)).strip().lower()
        if base_bank_id == "trade_yes_caution":
            if role in {"merchant", "chaotic"}:
                return f"{base_bank_id}_{role}"
            return base_bank_id
        if role in {"guard", "worker", "merchant", "neighbor", "chaotic"}:
            return f"{base_bank_id}_{role}"
        return base_bank_id

    def _pressure_contact_threshold(self, context, kind):
        kind = str(kind or "contact").strip().lower() or "contact"
        base = {
            "contact": 0.42,
            "introduction": 0.44,
            "vouch": 0.5,
        }.get(kind, 0.42)
        pressure_tier = str(context.get("pressure_tier", "low")).strip().lower() or "low"
        pressure_role = str(context.get("pressure_role", "") or self._dialogue_pressure_role(context)).strip().lower() or "local"
        extra = 0.0
        if pressure_tier == "medium":
            extra += {
                "contact": 0.05,
                "introduction": 0.08,
                "vouch": 0.1,
            }.get(kind, 0.05)
        elif pressure_tier == "high":
            extra += {
                "contact": 0.16,
                "introduction": 0.2,
                "vouch": 0.24,
            }.get(kind, 0.16)
        if context.get("recent_offense"):
            extra += 0.05
        if context.get("intro_source_name"):
            extra = max(0.0, extra - 0.04)
        extra += {
            "guard": {"contact": 0.08, "introduction": 0.1, "vouch": 0.14},
            "worker": {"contact": 0.05, "introduction": 0.07, "vouch": 0.1},
            "merchant": {"contact": 0.03, "introduction": 0.04, "vouch": 0.03},
            "neighbor": {"contact": -0.04, "introduction": -0.02, "vouch": 0.0},
            "chaotic": {"contact": -0.08, "introduction": -0.06, "vouch": -0.1},
        }.get(pressure_role, {}).get(kind, 0.0)
        if pressure_role == "worker" and context.get("workplace_here"):
            extra += 0.02
        return max(0.0, min(0.96, base + extra))

    def _pressure_contact_blocked(self, context, kind):
        if context.get("guarded") and kind in {"introduction", "vouch"}:
            return True
        pressure_tier = str(context.get("pressure_tier", "low")).strip().lower() or "low"
        if pressure_tier == "low" and not context.get("recent_offense"):
            return False
        standing = float(context.get("contact_standing", 0.0))
        return standing < self._pressure_contact_threshold(context, kind)

    def _pressure_offer_is_cautious(self, context, kind):
        kind = str(kind or "contact").strip().lower() or "contact"
        pressure_tier = str(context.get("pressure_tier", "low")).strip().lower() or "low"
        standing = float(context.get("contact_standing", 0.0))
        pressure_role = str(context.get("pressure_role", "") or self._dialogue_pressure_role(context)).strip().lower() or "local"
        if pressure_role == "guard":
            return pressure_tier in {"medium", "high"}
        if pressure_role == "worker":
            if pressure_tier == "high":
                return True
            if pressure_tier == "medium" and standing < 0.86:
                return True
        elif pressure_role == "merchant":
            if kind == "trade" and pressure_tier in {"medium", "high"}:
                return True
            if pressure_tier == "high":
                return True
            if pressure_tier == "medium" and standing < 0.68:
                return True
        elif pressure_role == "neighbor":
            if pressure_tier == "high" and kind in {"vouch", "introduction"}:
                return True
            if pressure_tier == "medium" and kind == "vouch" and standing < 0.7:
                return True
        elif pressure_role == "chaotic":
            if pressure_tier == "high" and standing < 0.46 and kind != "contact":
                return True
        if pressure_tier == "high":
            return True
        if pressure_tier == "medium" and standing < 0.74:
            return True
        if kind in {"introduction", "vouch"} and context.get("recent_offense"):
            return True
        return False

    def _contact_candidates(self, workplace_prop, owned_prop):
        candidates = []
        if workplace_prop:
            candidates.append(("workplace", workplace_prop))
        if owned_prop and (not workplace_prop or owned_prop["id"] != workplace_prop["id"]):
            candidates.append(("owner", owned_prop))
        return candidates

    def _offer_contact(self, npc_eid, workplace_prop, owned_prop, bond, rapport):
        standing = self._contact_standing(bond, rapport)
        if standing < 0.42:
            return None
        for contact_kind, prop in self._contact_candidates(workplace_prop, owned_prop):
            benefits = _property_contact_benefits(prop)
            if not benefits and standing < 0.58:
                continue
            if contact_kind == "owner" and standing < 0.5:
                continue
            changed = self._remember_player_contact(
                prop,
                source_eid=npc_eid,
                contact_kind=contact_kind,
                standing=standing,
                benefits=benefits,
            )
            if changed:
                self.sim.emit(Event(
                    "contact_learned",
                    eid=self.player_eid,
                    npc_eid=npc_eid,
                    property_id=prop["id"],
                    contact_kind=contact_kind,
                    standing=standing,
                    benefits=tuple(benefits),
                ))
            return {
                "contact_kind": contact_kind,
                "prop": prop,
                "standing": standing,
                "benefits": tuple(benefits),
                "newly_learned": bool(changed),
            }
        return None

    def _social_leads(self, npc_eid, *, workplace_prop=None, home_prop=None, current_prop=None, limit=3):
        social = self.sim.ecs.get(NPCSocial).get(npc_eid)
        if not social:
            return ()

        rows = []
        for other_eid, info in social.bonds.items():
            if other_eid == self.player_eid:
                continue
            name = _entity_display_name(self.sim, other_eid, title_case=True)
            if not name:
                continue
            identity = self.sim.ecs.get(CreatureIdentity).get(other_eid)
            if identity and str(identity.taxonomy_class or "hominid").strip().lower() != "hominid":
                continue

            occupation = self.sim.ecs.get(Occupation).get(other_eid)
            other_workplace = None
            workplace = getattr(occupation, "workplace", None)
            if isinstance(workplace, dict):
                property_id = str(workplace.get("property_id", "")).strip()
                if property_id:
                    other_workplace = self.sim.properties.get(property_id)
            other_routine = self.sim.ecs.get(NPCRoutine).get(other_eid)
            other_home = _home_property(self.sim, routine=other_routine)
            relation_kind = str(info.get("kind", "contact") or "contact").strip().lower() or "contact"
            closeness = max(0.0, min(1.0, float(info.get("closeness", 0.0))))
            trust = max(0.0, min(1.0, float(info.get("trust", 0.0))))
            score = (closeness * 0.58) + (trust * 0.42)

            shared_workplace = bool(
                workplace_prop
                and other_workplace
                and str(other_workplace.get("id")) == str(workplace_prop.get("id"))
            )
            shared_home = bool(
                home_prop
                and other_home
                and str(other_home.get("id")) == str(home_prop.get("id"))
            )

            place_prop = other_workplace or other_home
            place_name = ""
            place_role = ""
            if other_workplace:
                place_name = str(other_workplace.get("name", other_workplace.get("id", "workplace"))).strip()
                place_role = "workplace"
            elif other_home:
                place_name = str(other_home.get("name", other_home.get("id", "home"))).strip()
                place_role = "home"
            elif current_prop:
                place_name = str(current_prop.get("name", current_prop.get("id", "area"))).strip()
                place_role = "local"

            if relation_kind in {"family", "partner"}:
                score += 0.22
            elif relation_kind == "friend":
                score += 0.14
            elif relation_kind == "coworker":
                score += 0.08
            elif relation_kind == "neighbor":
                score += 0.04
            if shared_workplace:
                score += 0.16
            if shared_home:
                score += 0.1

            rows.append({
                "eid": other_eid,
                "name": name,
                "relation_kind": relation_kind,
                "relation_text": relation_kind.replace("_", " ").strip() or "contact",
                "career_text": _career_label(occupation),
                "property_id": place_prop.get("id") if isinstance(place_prop, dict) else None,
                "place_name": place_name,
                "place_role": place_role,
                "shared_workplace": shared_workplace,
                "shared_home": shared_home,
                "score": score,
                "bond_trust": trust,
                "bond_closeness": closeness,
            })

        rows.sort(key=lambda row: (float(row["score"]), row["name"].lower(), int(row["eid"])), reverse=True)
        if limit is not None:
            rows = rows[:max(0, int(limit))]
        return tuple(rows)

    def _player_social_axes(self):
        profile = self.sim.ecs.get(SkillProfile).get(self.player_eid)
        if profile:
            return _social_read_axes(profile), profile
        insight = self.sim.ecs.get(InsightStats).get(self.player_eid)
        if insight:
            return _social_read_axes(insight), insight
        core = self.sim.ecs.get(CoreStats).get(self.player_eid)
        if core:
            return _social_read_axes(core), core
        return (5.0, 5.0, 5.0), None

    def _conversation_rapport(self):
        (perception, conversation, streetwise), _ = self._player_social_axes()
        return ((conversation * 0.55) + (streetwise * 0.25) + (perception * 0.2)) / 10.0

    def _dialogue_pressure_intel_quality(self, context, topic_id=""):
        context = context if isinstance(context, dict) else {}
        topic_id = str(topic_id or "").strip().lower()
        pressure_tier = str(context.get("pressure_tier", "low")).strip().lower() or "low"
        pressure_role = str(
            context.get("pressure_role", "") or self._dialogue_pressure_role(context)
        ).strip().lower() or "local"
        guarded = bool(context.get("guarded"))
        recent_offense = context.get("recent_offense")
        social_standing = max(0.0, min(1.0, float(context.get("social_standing", 0.0) or 0.0)))
        rapport = max(0.0, min(1.0, float(context.get("rapport", 0.0) or 0.0)))
        (perception, conversation, streetwise), _ = self._player_social_axes()
        social_score = max(
            0.0,
            min(
                1.0,
                (
                    (float(conversation) * 0.42)
                    + (float(perception) * 0.28)
                    + (float(streetwise) * 0.30)
                ) / 10.0,
            ),
        )
        prep_terms = context.get("dialogue_prep_terms") if isinstance(context.get("dialogue_prep_terms"), dict) else {}
        prep_score = max(0.0, min(1.0, float(prep_terms.get("score", 0.0) or 0.0) / 10.0))
        base_detail = max(0, _int_or_default(prep_terms.get("detail_level"), 0))

        prep_topics = {"routine", "hours", "security", "access", "entry", "keyholder", "weak_point"}
        opportunity_topics = {"local", "detail", "opportunities", "objective", "angle", "risk"}
        is_prep = topic_id in prep_topics
        is_opportunity = topic_id in opportunity_topics

        pressure = {
            "low": 0.0,
            "medium": 0.2,
            "high": 0.38,
        }.get(pressure_tier, 0.0)
        pressure += {
            "guard": 0.1,
            "worker": 0.06,
            "merchant": 0.03,
            "neighbor": 0.01,
            "chaotic": -0.03,
        }.get(pressure_role, 0.0)
        if is_prep and pressure_role in {"guard", "worker"}:
            pressure += 0.05
        if is_opportunity:
            pressure += 0.04
        if guarded:
            pressure += 0.18
        if recent_offense:
            pressure += min(0.16, float(recent_offense.get("strength", 0.0) or 0.0) * 0.22)

        cutthrough = 0.0
        cutthrough += social_standing * 0.22
        cutthrough += rapport * 0.08
        cutthrough += social_score * 0.22
        cutthrough += prep_score * (0.18 if is_prep else 0.1)
        if base_detail >= 2 and is_prep:
            cutthrough += 0.05

        guard_score = pressure - cutthrough
        if guard_score <= 0.04:
            mode = "clear"
        elif guard_score <= 0.16:
            mode = "guarded"
        else:
            mode = "vague"

        detail_level = base_detail
        if mode == "guarded":
            detail_level = min(detail_level, 1)
        elif mode == "vague":
            detail_level = 0

        confidence_mult = {
            "clear": 1.0,
            "guarded": 0.82,
            "vague": 0.64,
        }[mode]
        return {
            "mode": mode,
            "confidence_mult": confidence_mult,
            "detail_level": detail_level,
            "base_detail_level": base_detail,
        }

    def _player_current_chunk(self):
        pos = self.sim.ecs.get(Position).get(self.player_eid)
        if pos:
            cx, cy = self.sim.chunk_coords(pos.x, pos.y)
            return (int(cx), int(cy))
        active = getattr(self.sim, "active_chunk_coord", None)
        if isinstance(active, (list, tuple)) and len(active) == 2:
            return (int(active[0]), int(active[1]))
        return (0, 0)

    def _dialogue_normalize_chunk(self, value, fallback=None):
        if isinstance(value, (list, tuple)) and len(value) == 2:
            try:
                return (int(value[0]), int(value[1]))
            except (TypeError, ValueError):
                pass
        if isinstance(fallback, (list, tuple)) and len(fallback) == 2:
            return (int(fallback[0]), int(fallback[1]))
        return (0, 0)

    def _dialogue_chunk_direction(self, from_chunk, to_chunk):
        dx = int(to_chunk[0]) - int(from_chunk[0])
        dy = int(to_chunk[1]) - int(from_chunk[1])
        parts = []
        if dy < 0:
            parts.append("N")
        elif dy > 0:
            parts.append("S")
        if dx > 0:
            parts.append("E")
        elif dx < 0:
            parts.append("W")
        return "".join(parts) if parts else "HERE"

    def _dialogue_allows_opportunity_entry(self, entry, *, allow_rival_followup=False):
        if not isinstance(entry, dict):
            return False
        kind = str(entry.get("kind", "")).strip().lower()
        requirements = entry.get("requirements", {})
        is_rival_followup = kind == "rival_followup"
        if isinstance(requirements, dict) and bool(requirements.get("rival_followup")):
            is_rival_followup = True
        if is_rival_followup and not allow_rival_followup:
            return False
        return True

    def _dialogue_is_rival_followup_entry(self, entry):
        return self._dialogue_allows_opportunity_entry(entry, allow_rival_followup=True) and not self._dialogue_allows_opportunity_entry(entry)

    def _dialogue_opportunity_rows(self, limit=3, observer_eid=None):
        # Structured opportunity facts are produced by the opportunities module.
        # This keeps dialogue logic focused on phrasing, while the underlying
        # opportunity data stays consistent with other consumers.
        observer = self.player_eid if observer_eid is None else observer_eid
        capped_limit = max(1, int(limit))
        rows = evaluate_opportunity_facts(
            self.sim,
            self.player_eid,
            limit=max(12, capped_limit * 4),
            observer_eid=observer,
        )
        filtered = [
            row for row in rows
            if self._dialogue_allows_opportunity_entry(row)
        ]
        return tuple(filtered[:capped_limit])

    def _dialogue_fallout_rows(self, limit=4, observer_eid=None):
        observer = self.player_eid if observer_eid is None else observer_eid
        capped_limit = max(1, int(limit))
        rows = evaluate_opportunity_facts(
            self.sim,
            self.player_eid,
            limit=max(12, capped_limit * 4),
            observer_eid=observer,
        )
        filtered = [
            row for row in rows
            if self._dialogue_is_rival_followup_entry(row)
        ]
        return tuple(filtered[:capped_limit])

    def _dialogue_active_opportunity_entry(self, opportunity_id):
        try:
            target_id = int(opportunity_id or 0)
        except (TypeError, ValueError):
            target_id = 0
        if target_id <= 0:
            return None
        traits = getattr(self.sim, "world_traits", {})
        opp_state = traits.get("opportunities", {}) if isinstance(traits, dict) else {}
        active = opp_state.get("active", ()) if isinstance(opp_state, dict) else ()
        for entry in active:
            if not isinstance(entry, dict):
                continue
            if int(entry.get("id", 0) or 0) == target_id:
                return entry
        return None

    def _dialogue_fallout_shortlist(self, rows, context):
        if not rows:
            return ()
        scored = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            distance = max(0, int(row.get("distance", 99) or 99))
            reward = dict(row.get("reward", {}))
            confidence = max(0.0, min(1.0, float(row.get("confidence", 0.0) or 0.0)))
            risk = str(row.get("risk", "low")).strip().lower() or "low"
            raw_entry = self._dialogue_active_opportunity_entry(row.get("id"))
            seed_tick = int((raw_entry or {}).get("seed_tick", 0) or 0)
            age = max(0, int(self.sim.tick) - seed_tick)
            intel_value = max(0, int(reward.get("intel", 0) or 0))
            standing_value = max(0, int(reward.get("standing", 0) or 0))
            credits_value = max(0, int(reward.get("credits", 0) or 0))

            score = 1.0
            score += max(0.0, 2.6 - (distance * 0.34))
            score += min(1.4, intel_value * 0.55)
            score += min(0.8, standing_value * 0.35)
            score += min(0.9, credits_value / 30.0)
            score += confidence * 0.9
            score += max(0.0, 1.2 - (age / 240.0))
            if risk == "hazardous":
                score += 0.22
            elif risk == "exposed":
                score += 0.12

            scored.append((score, seed_tick, int(row.get("id", 0) or 0), row))

        if not scored:
            return ()

        scored.sort(key=lambda item: (item[0], item[1], item[2]), reverse=True)
        return tuple(item[3] for item in scored[: min(3, len(scored))])

    def _dialogue_selected_fallout_row(self, context, *, ask_count=1):
        rows = tuple(context.get("fallout_rows", ()) or ())
        shortlist = self._dialogue_fallout_shortlist(rows, context)
        if not shortlist:
            return None
        ask_index = max(0, int(ask_count or 1) - 1)
        memory = self._dialogue_memory(context.get("npc_eid"))
        open_count = max(1, int(memory.get("opened_count", 1) or 1))
        chooser = random.Random(
            f"{self.sim.seed}:dialogue-fallout:{context.get('npc_eid', 0)}:{open_count}:{len(shortlist)}"
        )
        start_index = chooser.randrange(len(shortlist))
        return shortlist[(start_index + ask_index) % len(shortlist)]

    def _rival_operator_rows(self):
        traits = getattr(self.sim, "world_traits", {})
        state = traits.get("rival_operators", {}) if isinstance(traits, dict) else {}
        rivals = state.get("rivals", ()) if isinstance(state, dict) else ()
        return [row for row in rivals if isinstance(row, dict)]

    def _rival_operator_for_npc(self, npc_eid):
        try:
            target_eid = int(npc_eid)
        except (TypeError, ValueError):
            return None
        if target_eid <= 0:
            return None
        for rival in self._rival_operator_rows():
            try:
                materialized_eid = int(rival.get("materialized_eid") or 0)
            except (TypeError, ValueError):
                materialized_eid = 0
            if materialized_eid == target_eid:
                return rival
        return None

    def _rival_active_opportunities(self, *, allow_rival_followup=True):
        traits = getattr(self.sim, "world_traits", {})
        opp_state = traits.get("opportunities", {}) if isinstance(traits, dict) else {}
        active = opp_state.get("active", ()) if isinstance(opp_state, dict) else ()
        entries = [entry for entry in active if isinstance(entry, dict)]
        if allow_rival_followup:
            return entries
        return [
            entry for entry in entries
            if self._dialogue_allows_opportunity_entry(entry)
        ]

    def _rival_target_entry(self, rival):
        try:
            target_id = int((rival or {}).get("target_opportunity_id", 0) or 0)
        except (TypeError, ValueError):
            target_id = 0
        if target_id <= 0:
            return None
        for entry in self._rival_active_opportunities(allow_rival_followup=False):
            if int(entry.get("id", 0) or 0) == target_id:
                return entry
        return None

    def _dialogue_fact_from_opportunity_entry(self, entry):
        if not isinstance(entry, dict):
            return None
        try:
            opportunity_id = int(entry.get("id", 0) or 0)
        except (TypeError, ValueError):
            opportunity_id = 0
        if opportunity_id <= 0:
            return None

        current = self._player_current_chunk()
        chunk = self._dialogue_normalize_chunk(entry.get("chunk"), fallback=current)
        distance = _manhattan(current[0], current[1], chunk[0], chunk[1])
        direction = self._dialogue_chunk_direction(current, chunk)
        reward = dict(entry.get("reward", {}))
        playstyles = tuple(
            str(style).strip()
            for style in list(entry.get("playstyles", ()) or ())
            if str(style).strip()
        )
        risk = str(entry.get("risk", "low")).strip().lower() or "low"
        risk_score = {"calm": 0, "low": 1, "exposed": 2, "hazardous": 3}.get(risk, 1)
        intel = opportunity_intel_for_observer(self.sim, self.player_eid, opportunity_id)
        awareness_state = str((intel or {}).get("awareness_state", "heard")).strip().lower() or "heard"
        confidence = float((intel or {}).get("confidence", 0.54) or 0.54)
        return {
            "id": opportunity_id,
            "kind": str(entry.get("kind", "")).strip().lower(),
            "title": str(entry.get("title", "Opportunity")).strip() or "Opportunity",
            "summary": str(entry.get("summary", "")).strip(),
            "risk": risk,
            "source": str(entry.get("source", "unknown")).strip().lower(),
            "source_text": opportunity_source_label(entry.get("source", "unknown"), short=False),
            "distance": distance,
            "direction": direction,
            "chunk": chunk,
            "location": str(entry.get("location", "")).strip(),
            "reward": reward,
            "reward_text": format_reward_text(reward),
            "requirements": dict(entry.get("requirements", {})) if isinstance(entry.get("requirements", {}), dict) else {},
            "playstyles": playstyles,
            "risk_score": risk_score,
            "awareness_state": awareness_state,
            "confidence": confidence,
            "intel_source": str((intel or {}).get("source", "")).strip().lower() or "unknown",
        }

    def _rival_dialogue_truthful(self, rival, npc_eid, bond):
        bond = bond if isinstance(bond, dict) else {}
        (perception, _conversation, streetwise), _ = self._player_social_axes()
        memory = self._dialogue_memory(npc_eid)
        conversation_index = max(1, int(memory.get("opened_count", 0) or 0))
        honesty = float(rival.get("honesty", 0.5))
        greed = float(rival.get("greed", 0.5))
        heat = max(0.0, float(rival.get("heat", 0) or 0))
        trust = float(bond.get("trust", 0.0))
        closeness = float(bond.get("closeness", 0.0))
        reputation = str(rival.get("reputation", "steady")).strip().lower() or "steady"

        threshold = 0.14
        threshold += honesty * 0.56
        threshold += trust * 0.16
        threshold += closeness * 0.06
        threshold += (float(streetwise) / 10.0) * 0.06
        threshold += (float(perception) / 10.0) * 0.04
        threshold -= greed * 0.08
        threshold -= max(0.0, heat - 24.0) * 0.002
        if reputation in {"professional", "steady"}:
            threshold += 0.04
        elif reputation in {"dangerous", "hungry"}:
            threshold -= 0.03
        threshold = _clamp(threshold, lo=0.14, hi=0.92)

        rival_id = int(rival.get("id", 0) or 0)
        roll = random.Random(
            f"{self.sim.seed}:rival-dialogue-truth:{rival_id}:{npc_eid}:{conversation_index}"
        ).random()
        return roll <= threshold

    def _rival_dialogue_decoy_entry(self, rival, *, exclude_id=0):
        current_chunk = self._dialogue_normalize_chunk(rival.get("current_chunk"))
        hustle = str(rival.get("hustle", "cash")).strip().lower() or "cash"
        scored = []
        for entry in self._rival_active_opportunities(allow_rival_followup=False):
            try:
                opportunity_id = int(entry.get("id", 0) or 0)
            except (TypeError, ValueError):
                opportunity_id = 0
            if opportunity_id <= 0 or opportunity_id == int(exclude_id or 0):
                continue
            chunk = self._dialogue_normalize_chunk(entry.get("chunk"), fallback=current_chunk)
            distance = _manhattan(current_chunk[0], current_chunk[1], chunk[0], chunk[1])
            reward = dict(entry.get("reward", {}))
            styles = {
                str(style).strip().lower()
                for style in list(entry.get("playstyles", ()) or ())
                if str(style).strip()
            }
            score = max(0.25, 3.4 - (distance * 0.52))
            if hustle == "cash":
                score += min(2.0, max(0, int(reward.get("credits", 0) or 0)) / 18.0)
                if "economic" in styles:
                    score += 0.8
            elif hustle == "network":
                score += min(1.8, max(0, int(reward.get("standing", 0) or 0)) * 0.75)
                if "social" in styles:
                    score += 0.7
            elif hustle == "intel":
                score += min(1.8, max(0, int(reward.get("intel", 0) or 0)) * 0.85)
                if "stealth" in styles:
                    score += 0.75
            else:
                if "combat" in styles:
                    score += 1.15
            scored.append((score, opportunity_id, entry))

        if not scored:
            return None

        scored.sort(key=lambda row: (row[0], -row[1]), reverse=True)
        shortlist = scored[: min(3, len(scored))]
        total = sum(max(0.15, row[0]) for row in shortlist)
        rival_id = int(rival.get("id", 0) or 0)
        chooser = random.Random(f"{self.sim.seed}:rival-dialogue-decoy:{rival_id}")
        pick = chooser.uniform(0.0, total)
        cursor = 0.0
        selected = shortlist[0][2]
        for score, _opportunity_id, entry in shortlist:
            cursor += max(0.15, score)
            if pick <= cursor:
                selected = entry
                break
        return selected

    def _apply_rival_dialogue_context(self, context):
        if not isinstance(context, dict):
            return context
        npc_eid = context.get("npc_eid")
        rival = self._rival_operator_for_npc(npc_eid)
        if rival is None:
            return context

        context = dict(context)
        bond = context.get("bond") if isinstance(context.get("bond"), dict) else self._bond_snapshot(npc_eid)
        truthful = self._rival_dialogue_truthful(rival, npc_eid, bond)
        target_entry = self._rival_target_entry(rival)
        chosen_entry = target_entry if truthful else self._rival_dialogue_decoy_entry(
            rival,
            exclude_id=int(target_entry.get("id", 0) or 0) if isinstance(target_entry, dict) else 0,
        )
        if not self._dialogue_allows_opportunity_entry(chosen_entry):
            chosen_entry = None
        chosen_row = self._dialogue_fact_from_opportunity_entry(chosen_entry)

        context.update({
            "is_rival_operator": True,
            "rival_id": int(rival.get("id", 0) or 0),
            "rival_mask": str(rival.get("public_mask", "quiet")).strip().lower() or "quiet",
            "rival_reputation": str(rival.get("reputation", "steady")).strip().lower() or "steady",
            "rival_hustle": str(rival.get("hustle", "cash")).strip().lower() or "cash",
            "rival_status": str(rival.get("status", "hustling")).strip().lower() or "hustling",
            "rival_honesty": float(rival.get("honesty", 0.5) or 0.5),
            "rival_current_chunk": self._dialogue_normalize_chunk(rival.get("current_chunk")),
            "rival_home_chunk": self._dialogue_normalize_chunk(rival.get("home_chunk")),
            "rival_resolved_count": int(rival.get("resolved_count", 0) or 0),
            "rival_dialogue_truthful": bool(truthful and chosen_row),
            "objective_title": "",
            "objective_next_step": "",
            "objective_summary_line": "",
            "objective_why_lines": (),
            "objective_how_lines": (),
            "objective_activity_lines": (),
            "objective_focus_lines": (),
            "opportunity_rows": (),
            "opportunity_judgments": (),
            "primary_opportunity_judgment": {},
            "primary_opportunity_title": "",
            "primary_opportunity_id": 0,
            "opportunity_summary": "",
            "opportunity_detail": "",
        })

        subtitle = str(context.get("subtitle", "")).strip()
        rival_tag = f"rival {context['rival_mask']}/{context['rival_reputation']}"
        if subtitle:
            if rival_tag.lower() not in subtitle.lower():
                context["subtitle"] = f"{subtitle} | {rival_tag}"
        else:
            context["subtitle"] = rival_tag

        if chosen_row:
            chosen_row["confidence"] = 0.78 if truthful else 0.42
            chosen_row["awareness_state"] = chosen_row.get("awareness_state") or "heard"
            judgment = evaluate_opportunity_judgment(
                self.sim,
                npc_eid,
                chosen_row,
                pressure_tier=str(context.get("pressure_tier", "low")).strip().lower() or "low",
                rapport=float(context.get("rapport", 0.0) or 0.0),
                tone=str(context.get("tone", "neutral")).strip().lower() or "neutral",
            )
            context["opportunity_rows"] = (chosen_row,)
            context["opportunity_judgments"] = (judgment,)
            context["primary_opportunity_judgment"] = judgment
            context["primary_opportunity_title"] = str(chosen_row.get("title", "")).strip()
            context["primary_opportunity_id"] = int(chosen_row.get("id", 0) or 0)
            summary = self._opportunity_summary(context)
            detail = (
                summary
                or self._cycled_dialogue_line(self._opportunity_angle_lines(context, include_final_operation=False), 1)
                or self._cycled_dialogue_line(self._opportunity_risk_lines(context, include_final_operation=False), 1)
            )
            context["opportunity_summary"] = summary
            context["opportunity_detail"] = summary
            context["local_source"] = "opportunity"
            context["detail_line"] = detail
            context["detail_label"] = "Tell me more."
            context["has_local_detail"] = bool(detail)

        return context

    def _contract_kill_for_npc(self, npc_eid):
        """Return the active contract_kill opportunity this NPC is the giver for, or None."""
        if npc_eid is None:
            return None
        try:
            npc_int = int(npc_eid)
        except (TypeError, ValueError):
            return None
        traits = getattr(self.sim, "world_traits", None)
        if not isinstance(traits, dict):
            return None
        opp_state = traits.get("opportunities")
        if not isinstance(opp_state, dict):
            return None
        for entry in opp_state.get("active", ()):
            if not isinstance(entry, dict):
                continue
            if str(entry.get("kind", "")).strip().lower() != "contract_kill":
                continue
            req = entry.get("requirements", {})
            try:
                if int(req.get("giver_npc_eid", -1)) == npc_int:
                    return entry
            except (TypeError, ValueError):
                pass
        return None

    def _side_job_for_npc(self, npc_eid):
        if npc_eid is None:
            return None
        try:
            npc_int = int(npc_eid)
        except (TypeError, ValueError):
            return None
        traits = getattr(self.sim, "world_traits", None)
        if not isinstance(traits, dict):
            return None
        opp_state = traits.get("opportunities")
        if not isinstance(opp_state, dict):
            return None
        for entry in opp_state.get("active", ()):
            if not isinstance(entry, dict):
                continue
            if str(entry.get("kind", "")).strip().lower() not in self.SIDE_JOB_KINDS:
                continue
            issuer = entry.get("issuer", {}) if isinstance(entry.get("issuer"), dict) else {}
            if _int_or_default(issuer.get("npc_eid"), 0) == npc_int:
                return entry
        return None

    def _recent_side_job_completion_for_npc(self, npc_eid):
        if npc_eid is None:
            return None
        try:
            npc_int = int(npc_eid)
        except (TypeError, ValueError):
            return None
        traits = getattr(self.sim, "world_traits", None)
        if not isinstance(traits, dict):
            return None
        opp_state = traits.get("opportunities")
        if not isinstance(opp_state, dict):
            return None
        for entry in reversed(list(opp_state.get("completed", ()))):
            if not isinstance(entry, dict):
                continue
            if str(entry.get("kind", "")).strip().lower() not in self.SIDE_JOB_KINDS:
                continue
            issuer = entry.get("issuer", {}) if isinstance(entry.get("issuer"), dict) else {}
            if _int_or_default(issuer.get("npc_eid"), 0) != npc_int:
                continue
            completed_tick = _int_or_default(entry.get("completed_tick"), -10_000)
            if self.sim.tick - completed_tick < self.SIDE_JOB_COOLDOWN_TICKS:
                return entry
            break
        return None

    def _remember_opportunity_npc_interaction(self, npc_eid):
        npc_int = _int_or_default(npc_eid, 0)
        if npc_int <= 0:
            return
        traits = getattr(self.sim, "world_traits", None)
        if not isinstance(traits, dict):
            self.sim.world_traits = {}
            traits = self.sim.world_traits
        recent = traits.get("recent_npc_interactions")
        if not isinstance(recent, dict):
            recent = {}
            traits["recent_npc_interactions"] = recent
        current_tick = int(getattr(self.sim, "tick", 0))
        recent[str(npc_int)] = current_tick
        cutoff = current_tick - 12
        for raw_eid, raw_tick in list(recent.items()):
            if _int_or_default(raw_tick, default=-10_000) < cutoff:
                recent.pop(raw_eid, None)

    def _side_job_target_properties(self, origin_chunk, *, issuer_property_id, max_distance=3):
        origin_chunk = (
            _int_or_default((origin_chunk or (0, 0))[0], 0),
            _int_or_default((origin_chunk or (0, 0))[1], 0),
        )
        candidates = []
        for prop in list(getattr(self.sim, "properties", {}).values()):
            if not isinstance(prop, dict):
                continue
            property_id = str(prop.get("id", "") or "").strip()
            if not property_id or property_id == str(issuer_property_id or "").strip():
                continue
            if str(prop.get("kind", "")).strip().lower() != "building":
                continue
            try:
                chunk = self.sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
            except (TypeError, ValueError):
                continue
            distance = abs(int(chunk[0]) - int(origin_chunk[0])) + abs(int(chunk[1]) - int(origin_chunk[1]))
            if distance <= 0 or distance > int(max_distance):
                continue
            score = 0
            if _property_is_storefront(prop):
                score += 4
            if _finance_services_for_property(prop):
                score += 2
            if _site_services_for_property(prop):
                score += 2
            if _property_is_public(prop):
                score += 1
            name = str(prop.get("name", property_id)).strip() or property_id
            candidates.append((-score, distance, name.lower(), property_id, prop))
        candidates.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
        return [row[-1] for row in candidates]

    def _side_job_pressure_target(self, npc_eid, *, issuer_property_id, origin_chunk, max_distance=3):
        memories = self.sim.ecs.get(NPCMemory)
        memory = memories.get(npc_eid) if memories else None
        if not memory:
            return None

        origin_chunk = (
            _int_or_default((origin_chunk or (0, 0))[0], 0),
            _int_or_default((origin_chunk or (0, 0))[1], 0),
        )
        issuer_property_id = str(issuer_property_id or "").strip()
        player_eid = _int_or_default(getattr(self, "player_eid", None), 0)
        socials = self.sim.ecs.get(NPCSocial)
        social = socials.get(npc_eid)
        occupations = self.sim.ecs.get(Occupation)
        routines = self.sim.ecs.get(NPCRoutine)
        positions = self.sim.ecs.get(Position)
        ais = self.sim.ecs.get(AI)
        issuer_name = _entity_display_name(self.sim, npc_eid, title_case=True) or "your contact"
        now = int(getattr(self.sim, "tick", 0))

        def _target_site(target_eid):
            occupation = occupations.get(target_eid)
            routine = routines.get(target_eid)
            prop = _workplace_property(self.sim, occupation=occupation, routine=routine) or _home_property(self.sim, routine=routine)
            if isinstance(prop, dict):
                return prop
            pos = positions.get(target_eid)
            if not pos:
                return None
            prop = _property_covering(self.sim, pos.x, pos.y, pos.z) or self.sim.property_at(pos.x, pos.y, pos.z)
            return prop if isinstance(prop, dict) else None

        candidates = []
        for entry in reversed(list(getattr(memory, "entries", ()) or ())):
            if not isinstance(entry, dict):
                continue
            age = max(0, now - _int_or_default(entry.get("tick"), now))
            data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
            kind = str(entry.get("kind", "")).strip().lower()
            target_eid = 0
            score = 0.0
            reason = ""

            if kind == "actor_reputation" and age <= 260:
                target_eid = _int_or_default(data.get("actor_eid"), 0)
                try:
                    approval = float(data.get("approval", 0.0) or 0.0)
                except (TypeError, ValueError):
                    approval = 0.0
                if target_eid <= 0 or target_eid in {_int_or_default(npc_eid, 0), player_eid} or approval > -0.28:
                    continue
                score = abs(approval) * max(0.08, float(entry.get("strength", 0.0) or 0.0))
                target_name = _entity_display_name(self.sim, target_eid, title_case=True) or "someone nearby"
                against_eid = _int_or_default(data.get("against_eid"), 0)
                if against_eid == _int_or_default(npc_eid, 0):
                    reason = f"{target_name} keeps crossing {issuer_name}."
                    score += 0.08
                elif social and against_eid > 0 and against_eid in social.bonds:
                    against_name = _entity_display_name(self.sim, against_eid, title_case=True) or "someone nearby"
                    reason = f"{target_name} has been leaning on {against_name}."
                    score += 0.05
                else:
                    reason = f"{target_name} keeps coming up as trouble around {issuer_name}."
            elif kind == "conflict_side" and age <= 180:
                side_eid = _int_or_default(data.get("side_eid"), 0)
                target_eid = _int_or_default(data.get("against_eid"), 0)
                if target_eid <= 0 or target_eid in {_int_or_default(npc_eid, 0), player_eid}:
                    continue
                ally_score = 0.0
                ally_name = issuer_name
                if side_eid == _int_or_default(npc_eid, 0):
                    ally_score = 0.74
                elif social and side_eid in social.bonds:
                    bond = social.bonds.get(side_eid, {})
                    ally_score = (float(bond.get("trust", 0.0) or 0.0) * 0.62) + (float(bond.get("closeness", 0.0) or 0.0) * 0.38)
                    ally_name = _entity_display_name(self.sim, side_eid, title_case=True) or issuer_name
                if ally_score < 0.34:
                    continue
                score = max(0.08, float(entry.get("strength", 0.0) or 0.0)) * (0.74 + (ally_score * 0.42))
                target_name = _entity_display_name(self.sim, target_eid, title_case=True) or "someone nearby"
                reason = (
                    f"{target_name} has been crossing {issuer_name} lately."
                    if side_eid == _int_or_default(npc_eid, 0)
                    else f"{target_name} has been leaning on {ally_name}."
                )
            else:
                continue

            if target_eid <= 0 or score <= 0.0:
                continue
            target_prop = _target_site(target_eid)
            if not isinstance(target_prop, dict):
                continue
            target_property_id = str(target_prop.get("id", "") or "").strip()
            if not target_property_id or target_property_id == issuer_property_id:
                continue
            try:
                target_chunk = self.sim.chunk_coords(int(target_prop.get("x", 0)), int(target_prop.get("y", 0)))
            except (TypeError, ValueError):
                continue
            distance = abs(int(target_chunk[0]) - int(origin_chunk[0])) + abs(int(target_chunk[1]) - int(origin_chunk[1]))
            if distance > int(max_distance):
                continue
            occupation = occupations.get(target_eid)
            ai = ais.get(target_eid)
            target_role = _career_label(occupation) or str(getattr(ai, "role", "person") or "person").replace("_", " ").strip() or "person"
            candidates.append({
                "npc_eid": int(target_eid),
                "npc_name": _entity_display_name(self.sim, target_eid, title_case=True) or "someone nearby",
                "target_role": target_role,
                "property_id": target_property_id,
                "property_name": str(target_prop.get("name", target_property_id)).strip() or "the site",
                "building_id": _building_id_from_property(target_prop),
                "chunk": (int(target_chunk[0]), int(target_chunk[1])),
                "distance": int(distance),
                "reason": reason,
                "score": round(score, 3),
                "public": _property_is_public(target_prop),
            })

        if not candidates:
            return None
        candidates.sort(
            key=lambda row: (
                -float(row.get("score", 0.0) or 0.0),
                int(row.get("distance", 99) or 99),
                str(row.get("npc_name", "")).lower(),
            )
        )
        return dict(candidates[0])

    def _build_side_job_offer(self, context):
        if not isinstance(context, dict):
            return None
        npc_eid = context.get("npc_eid")
        if npc_eid is None or bool(context.get("guarded")):
            return None
        if float(context.get("contact_standing", 0.0) or 0.0) < self.SIDE_JOB_MIN_STANDING:
            return None
        if self._recent_side_job_completion_for_npc(npc_eid):
            return None

        issuer_prop = (
            context.get("workplace_prop")
            or context.get("owner_place")
            or context.get("current_prop")
            or context.get("owned_prop")
        )
        if not isinstance(issuer_prop, dict):
            return None

        issuer_property_id = str(issuer_prop.get("id", "") or "").strip()
        if not issuer_property_id:
            return None

        rng = random.Random(
            f"{self.sim.seed}:issuer-side-job:{int(npc_eid)}:{issuer_property_id}:{self.sim.tick // self.SIDE_JOB_COOLDOWN_TICKS}"
        )

        def _item_pool(item_ids):
            if isinstance(item_ids, str):
                raw = [item_ids]
            elif isinstance(item_ids, (list, tuple, set)):
                raw = list(item_ids)
            else:
                raw = []
            return [
                str(item_id).strip().lower()
                for item_id in raw
                if str(item_id).strip().lower() in ITEM_CATALOG
            ]

        def _pick_item(item_ids):
            pool = _item_pool(item_ids)
            if not pool:
                pool = _item_pool(self.SIDE_JOB_ITEM_POOL)
            if not pool:
                return ""
            return str(rng.choice(pool)).strip().lower()

        def _reward_with_bonus(base_reward, *bonus_item_pools):
            reward = dict(base_reward or {})
            bonus_items = []
            for pool in bonus_item_pools:
                bonus_item_id = _pick_item(pool)
                if not bonus_item_id:
                    continue
                bonus_items.append({"item_id": bonus_item_id, "quantity": 1})
            if bonus_items:
                reward["items"] = bonus_items
            return reward

        origin_chunk = self.sim.chunk_coords(
            _int_or_default(issuer_prop.get("x"), 0),
            _int_or_default(issuer_prop.get("y"), 0),
        )
        issuer_name = _entity_display_name(self.sim, npc_eid, title_case=True) or str(context.get("npc_name", "")).strip() or "your contact"
        issuer_place_name = str(issuer_prop.get("name", issuer_property_id)).strip() or "the handoff point"
        issuer_building_id = _building_id_from_property(issuer_prop)
        issuer_justice = self.sim.ecs.get(JusticeProfile).get(npc_eid)
        org_eid = property_organization_eid(self.sim, issuer_prop, ensure=True)
        org_name = organization_name(
            self.sim,
            org_eid,
            fallback=str(context.get("organization_name", "")).strip() or issuer_place_name,
        )
        base_reward = 16 + int(round(float(context.get("contact_standing", 0.0) or 0.0) * 18.0))
        issuer_finance = set(_finance_services_for_property(issuer_prop))
        issuer_site_services = set(_site_services_for_property(issuer_prop))
        issuer_storefront = _property_is_storefront(issuer_prop)
        issuer_payload = {
            "npc_eid": int(npc_eid),
            "npc_name": issuer_name,
            "property_id": issuer_property_id,
            "organization_eid": int(org_eid) if org_eid is not None else None,
            "organization_name": org_name,
            "relation_kind": "job_issuer",
            "person_standing_delta": 0.08,
            "property_standing_delta": 0.05,
            "organization_standing_delta": 0.06 if org_eid is not None else 0.0,
            "benefits": ("known_name",),
        }

        remote_candidates = self._side_job_target_properties(
            origin_chunk,
            issuer_property_id=issuer_property_id,
            max_distance=3,
        )
        pressure_target = self._side_job_pressure_target(
            npc_eid,
            issuer_property_id=issuer_property_id,
            origin_chunk=origin_chunk,
            max_distance=3,
        )
        remote_prop = rng.choice(remote_candidates[: min(6, len(remote_candidates))]) if remote_candidates else None
        remote_chunk = None
        remote_property_id = ""
        remote_building_id = ""
        remote_place_name = ""
        distance = 0
        distance_text = "here"
        remote_finance = set()
        remote_site_services = set()
        remote_storefront = False
        remote_public = False
        if isinstance(remote_prop, dict):
            remote_property_id = str(remote_prop.get("id", "") or "").strip()
            remote_building_id = _building_id_from_property(remote_prop)
            remote_place_name = str(remote_prop.get("name", remote_property_id)).strip() or "the destination"
            remote_finance = set(_finance_services_for_property(remote_prop))
            remote_site_services = set(_site_services_for_property(remote_prop))
            remote_storefront = _property_is_storefront(remote_prop)
            remote_public = _property_is_public(remote_prop)
            remote_chunk = self.sim.chunk_coords(
                _int_or_default(remote_prop.get("x"), 0),
                _int_or_default(remote_prop.get("y"), 0),
            )
            distance = abs(int(remote_chunk[0]) - int(origin_chunk[0])) + abs(int(remote_chunk[1]) - int(origin_chunk[1]))
            direction_bits = []
            if int(remote_chunk[1]) < int(origin_chunk[1]):
                direction_bits.append("N")
            elif int(remote_chunk[1]) > int(origin_chunk[1]):
                direction_bits.append("S")
            if int(remote_chunk[0]) > int(origin_chunk[0]):
                direction_bits.append("E")
            elif int(remote_chunk[0]) < int(origin_chunk[0]):
                direction_bits.append("W")
            distance_text = opportunity_distance_text(distance, "".join(direction_bits) if direction_bits else "HERE")

        period_key = self.sim.tick // self.SIDE_JOB_COOLDOWN_TICKS
        offers = []
        pressure_offers = []

        def _append_procure_offer(family, title, summary_template, item_ids, *, credit_bonus=8, standing=1, intel=0, bonus_items=(), pressure="medium"):
            item_id = _pick_item(item_ids)
            if not item_id:
                return
            item_label = item_display_name(item_id, item_catalog=ITEM_CATALOG)
            reward = {"credits": max(22, min(54, base_reward + int(credit_bonus))), "standing": int(standing)}
            if int(intel) > 0:
                reward["intel"] = int(intel)
            offers.append({
                "key": f"issuer_procure:{family}:{int(npc_eid)}:{issuer_property_id}:{item_id}:{period_key}",
                "title": title,
                "summary": summary_template.format(item_label=item_label),
                "kind": "issuer_procure",
                "contract_family": family,
                "source": "contact",
                "chunk": origin_chunk,
                "location": "issued_job",
                "playstyles": ("economic", "social", "stealth"),
                "reward": _reward_with_bonus(reward, *bonus_items),
                "risk": "low",
                "pressure": pressure,
                "requirements": {
                    "delivery_chunk": origin_chunk,
                    "visit_chunk": origin_chunk,
                    "delivery_property_id": issuer_property_id,
                    "delivery_building_id": issuer_building_id,
                    "interact_npc_eid": int(npc_eid),
                    "interact_npc_name": issuer_name,
                    "require_item_id": item_id,
                    "require_item_qty": 1,
                    "consume_item": True,
                    "provide_item": False,
                    "item_label": item_label,
                    "acquisition_hint": "buy_or_find",
                    "player_accepted": True,
                },
                "issuer": dict(issuer_payload),
                "status": "active",
                "seed_tick": int(getattr(self.sim, "tick", 0)),
            })

        def _append_delivery_offer(family, title, summary_template, item_ids, *, credit_bonus=0, standing=1, intel=0, bonus_items=(), risk=None, pressure=None):
            if not remote_chunk or not remote_property_id:
                return
            item_id = _pick_item(item_ids)
            if not item_id:
                return
            item_label = item_display_name(item_id, item_catalog=ITEM_CATALOG)
            reward = {"credits": max(18, min(50, base_reward + int(credit_bonus) + (distance * 4))), "standing": int(standing)}
            if int(intel) > 0:
                reward["intel"] = int(intel)
            offers.append({
                "key": f"issuer_delivery:{family}:{int(npc_eid)}:{issuer_property_id}:{remote_property_id}:{item_id}:{period_key}",
                "title": title,
                "summary": summary_template.format(item_label=item_label),
                "kind": "issuer_delivery",
                "contract_family": family,
                "source": "contact",
                "chunk": remote_chunk,
                "location": "issued_job",
                "playstyles": ("social", "stealth", "economic"),
                "reward": _reward_with_bonus(reward, *bonus_items),
                "risk": str(risk or ("low" if distance <= 1 else "exposed")).strip().lower() or "low",
                "pressure": str(pressure or ("low" if distance <= 1 else "medium")).strip().lower() or "low",
                "requirements": {
                    "pickup_chunk": origin_chunk,
                    "pickup_property_id": issuer_property_id,
                    "pickup_building_id": issuer_building_id,
                    "pickup_interact_npc_eid": int(npc_eid),
                    "pickup_interact_npc_name": issuer_name,
                    "delivery_chunk": remote_chunk,
                    "visit_chunk": remote_chunk,
                    "delivery_property_id": remote_property_id,
                    "delivery_building_id": remote_building_id,
                    "property_id": remote_property_id,
                    "building_id": remote_building_id,
                    "require_item_id": item_id,
                    "require_item_qty": 1,
                    "consume_item": True,
                    "provide_item": True,
                    "item_label": item_label,
                    "acquisition_hint": "provided",
                    "player_accepted": True,
                },
                "issuer": dict(issuer_payload),
                "status": "active",
                "seed_tick": int(getattr(self.sim, "tick", 0)),
            })

        def _append_pickup_offer(family, title, summary_template, item_ids, *, credit_bonus=4, standing=1, intel=0, bonus_items=(), risk=None, pressure=None):
            if not remote_chunk or not remote_property_id:
                return
            item_id = _pick_item(item_ids)
            if not item_id:
                return
            item_label = item_display_name(item_id, item_catalog=ITEM_CATALOG)
            reward = {"credits": max(20, min(52, base_reward + int(credit_bonus) + (distance * 4))), "standing": int(standing)}
            if int(intel) > 0:
                reward["intel"] = int(intel)
            offers.append({
                "key": f"issuer_pickup:{family}:{int(npc_eid)}:{issuer_property_id}:{remote_property_id}:{item_id}:{period_key}",
                "title": title,
                "summary": summary_template.format(item_label=item_label),
                "kind": "issuer_pickup",
                "contract_family": family,
                "source": "contact",
                "chunk": remote_chunk,
                "location": "issued_job",
                "playstyles": ("social", "stealth", "economic"),
                "reward": _reward_with_bonus(reward, *bonus_items),
                "risk": str(risk or ("low" if distance <= 1 else "exposed")).strip().lower() or "low",
                "pressure": str(pressure or ("medium" if distance >= 2 else "low")).strip().lower() or "low",
                "requirements": {
                    "pickup_chunk": remote_chunk,
                    "pickup_property_id": remote_property_id,
                    "pickup_building_id": remote_building_id,
                    "delivery_chunk": origin_chunk,
                    "visit_chunk": origin_chunk,
                    "delivery_property_id": issuer_property_id,
                    "delivery_building_id": issuer_building_id,
                    "interact_npc_eid": int(npc_eid),
                    "interact_npc_name": issuer_name,
                    "require_item_id": item_id,
                    "require_item_qty": 1,
                    "consume_item": True,
                    "provide_item": True,
                    "item_label": item_label,
                    "acquisition_hint": "pickup",
                    "player_accepted": True,
                },
                "issuer": dict(issuer_payload),
                "status": "active",
                "seed_tick": int(getattr(self.sim, "tick", 0)),
            })

        def _append_pressure_offer(family, title, summary_template, *, credit_bonus=10, standing=2, bonus_items=(), risk="exposed", pressure="medium"):
            if not isinstance(pressure_target, dict):
                return
            target_eid = _int_or_default(pressure_target.get("npc_eid"), 0)
            target_property_id = str(pressure_target.get("property_id", "") or "").strip()
            if target_eid <= 0 or not target_property_id:
                return
            target_name = str(pressure_target.get("npc_name", "") or "").strip() or "the mark"
            target_place_name = str(pressure_target.get("property_name", "") or "").strip() or "the site"
            target_building_id = str(pressure_target.get("building_id", "") or "").strip()
            target_chunk = tuple(pressure_target.get("chunk", ())) if isinstance(pressure_target.get("chunk"), (list, tuple)) else ()
            if len(target_chunk) != 2:
                return
            target_distance = _int_or_default(pressure_target.get("distance"), 0)
            direction_bits = []
            if int(target_chunk[1]) < int(origin_chunk[1]):
                direction_bits.append("N")
            elif int(target_chunk[1]) > int(origin_chunk[1]):
                direction_bits.append("S")
            if int(target_chunk[0]) > int(origin_chunk[0]):
                direction_bits.append("E")
            elif int(target_chunk[0]) < int(origin_chunk[0]):
                direction_bits.append("W")
            distance_text = opportunity_distance_text(target_distance, "".join(direction_bits) if direction_bits else "HERE")
            reward = {"credits": max(24, min(66, base_reward + int(credit_bonus) + (target_distance * 5))), "standing": int(standing)}
            pressure_offers.append({
                "key": f"issuer_pressure:{family}:{int(npc_eid)}:{issuer_property_id}:{target_property_id}:{target_eid}:{period_key}",
                "title": title,
                "summary": summary_template.format(
                    target_name=target_name,
                    target_place_name=target_place_name,
                    distance_text=distance_text,
                    issuer_name=issuer_name,
                    pressure_reason=str(pressure_target.get("reason", "") or "").strip(),
                ),
                "kind": "issuer_pressure",
                "contract_family": family,
                "source": "contact",
                "chunk": (int(target_chunk[0]), int(target_chunk[1])),
                "location": "issued_job",
                "playstyles": ("social", "stealth"),
                "reward": _reward_with_bonus(reward, *bonus_items),
                "risk": str(risk or "exposed").strip().lower() or "exposed",
                "pressure": str(pressure or "medium").strip().lower() or "medium",
                "requirements": {
                    "visit_chunk": (int(target_chunk[0]), int(target_chunk[1])),
                    "interaction_chunk": (int(target_chunk[0]), int(target_chunk[1])),
                    "property_id": target_property_id,
                    "building_id": target_building_id,
                    "interact_npc_eid": int(target_eid),
                    "interact_npc_name": target_name,
                    "interaction_requirement": "pressure",
                    "pressure_reason": str(pressure_target.get("reason", "") or "").strip(),
                    "player_accepted": True,
                },
                "issuer": dict(issuer_payload),
                "status": "active",
                "seed_tick": int(getattr(self.sim, "tick", 0)),
            })

        _append_procure_offer(
            "tool_request",
            "Tool Request",
            f"Find {{item_label}} and hand it to {issuer_name} at {issuer_place_name}. They need usable kit before the local window closes.",
            ("lockpick_kit", "pocket_multitool", "access_badge"),
            credit_bonus=10,
            bonus_items=(("credstick_chip", "transit_daypass"),),
        )
        _append_procure_offer(
            "medical_resupply",
            "Medical Resupply",
            f"Source {{item_label}} and bring it back to {issuer_name} at {issuer_place_name}. Somebody nearby needs it quickly and quietly.",
            ("med_gel", "micro_medkit", "trauma_foam", "hydration_salts"),
            credit_bonus=8,
            bonus_items=(("med_gel", "hydration_salts"),),
        )
        _append_procure_offer(
            "paper_run",
            "Clean Papers",
            f"Bring {{item_label}} back to {issuer_name} at {issuer_place_name}. They are lining up a clean-looking handoff and need the paperwork to match.",
            ("access_badge", "transit_daypass", "credstick_chip"),
            credit_bonus=6,
            intel=1,
            bonus_items=(("credstick_chip", "transit_daypass"),),
            pressure="low",
        )
        if issuer_storefront or issuer_finance or issuer_site_services:
            _append_procure_offer(
                "buyback",
                "Buyback Order",
                f"Find {{item_label}} and sell it back to {issuer_name} at {issuer_place_name}. They have a quiet buyer waiting on the strip.",
                ("street_ration", "hydration_salts", "med_gel", "lockpick_kit", "pocket_multitool"),
                credit_bonus=9,
                bonus_items=(("street_ration", "credstick_chip"),),
            )

        if remote_chunk and remote_property_id:
            _append_delivery_offer(
                "quiet_delivery",
                "Quiet Delivery",
                f"Carry {{item_label}} from {issuer_place_name} to {remote_place_name} {distance_text} and hand it off there.",
                ("credstick_chip", "access_badge", "transit_daypass"),
                bonus_items=(("credstick_chip", "transit_daypass"),),
            )
            _append_delivery_offer(
                "medical_drop",
                "Medical Drop",
                f"Carry {{item_label}} from {issuer_place_name} to {remote_place_name} {distance_text}. Keep it clean and get it there before the need turns loud.",
                ("med_gel", "micro_medkit", "trauma_foam"),
                credit_bonus=2,
                bonus_items=(("med_gel", "hydration_salts"),),
                risk="exposed" if distance >= 2 else "low",
                pressure="medium",
            )
            if remote_storefront or remote_public or "repair" in remote_site_services:
                _append_delivery_offer(
                    "backroom_transfer",
                    "Backroom Transfer",
                    f"Move {{item_label}} from {issuer_place_name} to {remote_place_name} {distance_text}. The buyer wants it off the floor and out of sight.",
                    ("lockpick_kit", "pocket_multitool", "light_ammo_box"),
                    credit_bonus=4,
                    bonus_items=(("lockpick_kit", "light_ammo_box"),),
                    risk="exposed",
                    pressure="medium",
                )
            if remote_finance or "intel" in remote_site_services:
                _append_delivery_offer(
                    "claims_packet",
                    "Claims Packet",
                    f"Carry {{item_label}} from {issuer_place_name} to {remote_place_name} {distance_text}. It has to land before the claim traffic dries up.",
                    ("credstick_chip", "access_badge", "transit_daypass"),
                    credit_bonus=5,
                    intel=1,
                    bonus_items=(("credstick_chip", "transit_daypass"),),
                    risk="exposed",
                    pressure="medium",
                )

            _append_pickup_offer(
                "dead_drop_return",
                "Dead Drop Return",
                f"Pick up {{item_label}} from {remote_place_name} {distance_text} and bring it back to {issuer_name}. The package should already be waiting.",
                ("credstick_chip", "light_ammo_box", "transit_daypass"),
                bonus_items=(("lockpick_kit", "pocket_multitool"),),
            )
            _append_pickup_offer(
                "parts_return",
                "Parts Return",
                f"Collect {{item_label}} from {remote_place_name} {distance_text} and bring it back to {issuer_name} before another buyer notices the gap.",
                ("pocket_multitool", "lockpick_kit", "light_ammo_box"),
                credit_bonus=5,
                bonus_items=(("light_ammo_box", "pocket_multitool"),),
                risk="exposed",
            )
            if remote_public or "shelter" in remote_site_services:
                _append_pickup_offer(
                    "clinic_recovery",
                    "Clinic Recovery",
                    f"Pick up {{item_label}} from {remote_place_name} {distance_text} and bring it back to {issuer_name}. They want the recovery stock moved before anyone audits it.",
                    ("med_gel", "micro_medkit", "trauma_foam", "hydration_salts"),
                    credit_bonus=3,
                    bonus_items=(("med_gel", "micro_medkit"),),
                )
            if remote_finance or "intel" in remote_site_services:
                _append_pickup_offer(
                    "records_recovery",
                    "Records Recovery",
                    f"Recover {{item_label}} from {remote_place_name} {distance_text} and bring it back to {issuer_name}. Somebody there still owes them clean paperwork.",
                    ("access_badge", "credstick_chip", "transit_daypass"),
                    credit_bonus=6,
                    intel=1,
                    bonus_items=(("credstick_chip", "transit_daypass"),),
                    risk="exposed",
                )

        if pressure_target:
            _append_pressure_offer(
                "pressure_visit",
                "Pressure Visit",
                "{target_name} is at {target_place_name} {distance_text}. Find them and make it clear {issuer_name} wants the problem settled. {pressure_reason}",
                bonus_items=(("credstick_chip", "light_ammo_box"),),
            )
            if bool(pressure_target.get("public")):
                _append_pressure_offer(
                    "quiet_collection",
                    "Quiet Collection",
                    "Catch {target_name} at {target_place_name} {distance_text} and lean on them until they stop dodging {issuer_name}. {pressure_reason}",
                    credit_bonus=12,
                    bonus_items=(("credstick_chip", "transit_daypass"),),
                    risk="hazardous",
                    pressure="high",
                )

        if pressure_offers:
            corruption = float(getattr(issuer_justice, "corruption", 0.0) or 0.0) if issuer_justice else 0.0
            if float(pressure_target.get("score", 0.0) or 0.0) >= 0.48 and (
                corruption >= 0.34 or float(context.get("contact_standing", 0.0) or 0.0) >= 0.76
            ):
                return dict(rng.choice(pressure_offers))
            offers.extend(pressure_offers)

        if not offers:
            return None
        return dict(rng.choice(offers))

    def _ensure_side_job_offer(self, context):
        existing = self._side_job_for_npc(context.get("npc_eid"))
        if isinstance(existing, dict):
            reveal_opportunity_to_observer(
                self.sim,
                self.player_eid,
                int(existing.get("id", 0)),
                awareness_state="confirmed",
                confidence=0.95,
                source="npc_dialogue_side_job",
            )
            return existing

        opportunity = self._build_side_job_offer(context)
        if not isinstance(opportunity, dict):
            return None
        return append_external_opportunity(
            self.sim,
            opportunity,
            observer_eid=self.player_eid,
            awareness_state="confirmed",
            confidence=0.95,
            source="npc_dialogue_side_job",
        )

    def _learn_dialogue_opportunity(self, context, *, source="dialogue", confidence_mult=1.0):
        if not isinstance(context, dict):
            return
        opportunity_id = int(context.get("primary_opportunity_id", 0) or 0)
        if opportunity_id <= 0:
            return
        source_text = str(source or "dialogue")
        confidence = 0.68
        if context.get("is_rival_operator"):
            truthful = bool(context.get("rival_dialogue_truthful"))
            confidence = 0.74 if truthful else 0.42
            source_text = f"{source_text}_{'truth' if truthful else 'bluff'}"
        try:
            confidence *= float(confidence_mult)
        except (TypeError, ValueError):
            pass
        confidence = max(0.24, min(0.96, confidence))
        reveal_opportunity_to_observer(
            self.sim,
            self.player_eid,
            opportunity_id,
            awareness_state="heard",
            confidence=confidence,
            source=source_text,
        )

    def _learn_dialogue_opportunity_row(self, row, *, source="dialogue", confidence_mult=1.0):
        if not isinstance(row, dict):
            return
        opportunity_id = int(row.get("id", 0) or 0)
        if opportunity_id <= 0:
            return
        confidence = max(0.42, min(0.92, float(row.get("confidence", 0.66) or 0.66)))
        try:
            confidence *= float(confidence_mult)
        except (TypeError, ValueError):
            pass
        confidence = max(0.24, min(0.96, confidence))
        reveal_opportunity_to_observer(
            self.sim,
            self.player_eid,
            opportunity_id,
            awareness_state="heard",
            confidence=confidence,
            source=str(source or "dialogue"),
        )

    def _learn_scene_followup(self, context, *, source="dialogue"):
        if not isinstance(context, dict):
            return None
        opportunity = context.get("scene_followup_opportunity")
        if not isinstance(opportunity, dict) or not opportunity:
            return None

        confidence = max(0.56, min(0.9, float(context.get("lead_confidence", 0.62) or 0.62) + 0.06))
        added = append_external_opportunity(
            self.sim,
            opportunity,
            observer_eid=self.player_eid,
            awareness_state="heard",
            confidence=confidence,
            source=str(source or "dialogue"),
        )

        npc_eid = context.get("npc_eid")
        property_id = str(context.get("scene_followup_property_id", "") or "").strip()
        lead_kind = str(context.get("scene_followup_lead_kind", "") or "").strip().lower() or "hours"
        seed_id = str(context.get("scene_followup_seed_id", "") or "").strip()
        if property_id:
            prop = self.sim.properties.get(property_id)
            if prop is not None:
                self._remember_player_property_lead(
                    prop,
                    source_eid=npc_eid,
                    lead_kind=lead_kind,
                    confidence=max(0.6, confidence - 0.04),
                )

        note = context.get("scene_note")
        note_shared = bool((note or {}).get("followup_shared"))
        if added is not None or not note_shared:
            summary = str(opportunity.get("title", "Fresh lead")).strip() or "Fresh lead"
            detail = str(opportunity.get("summary", "")).strip()
            self.sim.emit(Event(
                "dialogue_opportunity_hint",
                eid=self.player_eid,
                npc_eid=npc_eid,
                summary=summary,
                detail=detail,
            ))
            if seed_id:
                seeds = _business_event_seed_state(self.sim).get("active", {})
                seed = seeds.get(seed_id)
                if isinstance(seed, dict):
                    seed["shared"] = True
            if isinstance(note, dict):
                note["followup_shared"] = True
                actor_state = _business_event_actor_state(self.sim)
                if npc_eid is not None:
                    actor_state[int(npc_eid)] = note
        return added

    def _bond_snapshot(self, npc_eid):
        social = self.sim.ecs.get(NPCSocial).get(npc_eid)
        if not social:
            return None
        return social.bonds.get(self.player_eid)

    def _conversation_bond(self, npc_eid, npc_ai, npc_needs, npc_traits, guarded):
        social = self.sim.ecs.get(NPCSocial).get(npc_eid)
        if not social:
            return None
        bond = social.bonds.get(self.player_eid)
        intro_entry = self._player_person_contact_entry(npc_eid)
        if not bond:
            if guarded:
                return None
            intro_standing = float((intro_entry or {}).get("standing", 0.0))
            social.add_bond(
                self.player_eid,
                kind="neighbor",
                closeness=max(0.18, 0.16 + (intro_standing * 0.16)),
                trust=max(0.22, 0.2 + (intro_standing * 0.2)),
                protectiveness=0.18,
            )
            bond = social.bonds.get(self.player_eid)
        elif intro_entry and not guarded:
            intro_standing = float(intro_entry.get("standing", 0.0))
            bond["closeness"] = max(float(bond.get("closeness", 0.0)), 0.16 + (intro_standing * 0.14))
            bond["trust"] = max(float(bond.get("trust", 0.0)), 0.2 + (intro_standing * 0.18))
        if guarded or self._recently_interacted(npc_eid):
            return bond
        (perception, conversation, streetwise), _ = self._player_social_axes()
        common_sense = (perception + streetwise) / 2.0
        npc_traits = npc_traits or NPCTraits()
        openness = 0.7 + (npc_traits.empathy * 0.45)
        if npc_needs and npc_needs.social < 45:
            openness += 0.18
        if npc_ai and npc_ai.state in {"investigating", "protecting"}:
            openness *= 0.65
        closeness_gain = min(0.08, 0.014 + ((conversation / 10.0) * 0.035 * openness))
        trust_gain = min(
            0.07,
            0.012 + ((common_sense / 10.0) * 0.03 * (0.85 + (npc_traits.discipline * 0.25))),
        )
        goodwill_mult = max(0.2, float(_pressure_effects(self.sim).get("goodwill_mult", 1.0)))
        bond["closeness"] = min(0.95, float(bond.get("closeness", 0.0)) + (closeness_gain * goodwill_mult))
        bond["trust"] = min(0.95, float(bond.get("trust", 0.0)) + (trust_gain * goodwill_mult))
        if bond.get("kind") == "neighbor" and bond["closeness"] >= 0.58 and bond["trust"] >= 0.6:
            bond["kind"] = "friend"
            bond["protectiveness"] = max(
                float(bond.get("protectiveness", 0.18)),
                NPCSocial.DEFAULT_PROTECT.get("friend", 0.7),
            )
        return bond

    def _memory_line(self, memory, player_profile):
        if not memory:
            return None
        strongest_trait = None
        strongest_property_threat = None
        strongest_actor_reputation = None
        strongest_actor_score = 0.0
        strongest_conflict_side = None
        for entry in memory.entries:
            age = self.sim.tick - int(entry.get("tick", 0))
            if entry.get("kind") == "world_trait" and age <= 240:
                if not strongest_trait or float(entry.get("strength", 0.0)) > float(strongest_trait.get("strength", 0.0)):
                    strongest_trait = entry
            elif entry.get("kind") == "property_threat" and age <= 200:
                if not strongest_property_threat or float(entry.get("strength", 0.0)) > float(strongest_property_threat.get("strength", 0.0)):
                    strongest_property_threat = entry
            elif entry.get("kind") == "actor_reputation" and age <= 220:
                data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
                actor_eid = _int_or_default(data.get("actor_eid"), 0)
                try:
                    approval = float(data.get("approval", 0.0) or 0.0)
                except (TypeError, ValueError):
                    approval = 0.0
                if actor_eid <= 0 or abs(approval) < 0.18:
                    continue
                score = abs(approval) * max(0.08, float(entry.get("strength", 0.0) or 0.0))
                if actor_eid == int(self.player_eid):
                    score += 0.06
                if strongest_actor_reputation is None or score > strongest_actor_score:
                    strongest_actor_reputation = entry
                    strongest_actor_score = score
            elif entry.get("kind") == "conflict_side" and age <= 180:
                data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
                side_eid = _int_or_default(data.get("side_eid"), 0)
                against_eid = _int_or_default(data.get("against_eid"), 0)
                if side_eid <= 0 or against_eid <= 0 or side_eid == against_eid:
                    continue
                if not strongest_conflict_side or float(entry.get("strength", 0.0)) > float(strongest_conflict_side.get("strength", 0.0)):
                    strongest_conflict_side = entry
        if strongest_property_threat:
            property_id = strongest_property_threat.get("data", {}).get("property_id")
            prop = self.sim.properties.get(property_id) if property_id else None
            if prop:
                return f"They warn you about trouble around {prop.get('name', property_id)}."
        if strongest_actor_reputation:
            data = strongest_actor_reputation.get("data", {}) if isinstance(strongest_actor_reputation.get("data"), dict) else {}
            actor_eid = _int_or_default(data.get("actor_eid"), 0)
            try:
                approval = float(data.get("approval", 0.0) or 0.0)
            except (TypeError, ValueError):
                approval = 0.0
            via = str(data.get("via", "") or "").strip().lower()
            if actor_eid == int(self.player_eid):
                if approval <= -0.48 or via in {"witnessed_damage", "witnessed_offense", "npc_offended"}:
                    return "They have heard you bring trouble with you."
                if approval < 0.0:
                    return "They have heard your name on the wrong side of a few stories."
                if via == "dialogue_guard_resolution":
                    return "They have heard you can talk a hot room back down."
                return "They have heard you come through when things count."
            actor_name = _entity_display_name(self.sim, actor_eid, title_case=True) or "someone nearby"
            if approval <= -0.48:
                return f"They keep bringing up {actor_name} as bad news."
            if approval < 0.0:
                return f"They keep bringing up {actor_name} as somebody who causes trouble."
            return f"They keep bringing up {actor_name} as someone who comes through."
        strongest_reputation = None
        for entry in memory.entries:
            age = self.sim.tick - int(entry.get("tick", 0))
            if entry.get("kind") != "player_reputation" or age > 320:
                continue
            data = entry.get("data", {}) if isinstance(entry.get("data"), dict) else {}
            if int(data.get("player_eid", -1) or -1) != int(self.player_eid):
                continue
            if not strongest_reputation or float(entry.get("strength", 0.0)) > float(strongest_reputation.get("strength", 0.0)):
                strongest_reputation = entry
        if strongest_reputation:
            family = str(strongest_reputation.get("data", {}).get("contract_family", "work")).replace("_", " ").strip() or "work"
            worldview = str(strongest_reputation.get("data", {}).get("worldview", "neutral")).strip().lower() or "neutral"
            if worldview == "order":
                return f"They remember you handled {family} cleanly."
            if worldview == "chaos":
                return f"They remember you came through when things got messy around the {family} job."
            return f"They remember you came through on {family}."
        if strongest_conflict_side:
            data = strongest_conflict_side.get("data", {}) if isinstance(strongest_conflict_side.get("data"), dict) else {}
            side_eid = _int_or_default(data.get("side_eid"), 0)
            against_eid = _int_or_default(data.get("against_eid"), 0)
            if side_eid > 0 and against_eid > 0 and side_eid != against_eid:
                side_name = "you" if side_eid == int(self.player_eid) else (_entity_display_name(self.sim, side_eid, title_case=True) or "someone nearby")
                against_name = "you" if against_eid == int(self.player_eid) else (_entity_display_name(self.sim, against_eid, title_case=True) or "someone nearby")
                if side_name != against_name:
                    return f"They say the room keeps taking {side_name}'s side over {against_name}."
        if strongest_trait:
            topic = str(strongest_trait.get("data", {}).get("topic", "")).strip().lower()
            claim_value = _world_trait_claim_value(strongest_trait.get("data", {}))
            claim_text = _world_trait_claim_text(topic, claim_value)
            read = _rumor_truth_read(player_profile, strongest_trait)
            return f"Rumor: {claim_text} ({read})."
        return None

    def _social_need_line(self, npc_needs, bond):
        if npc_needs:
            if npc_needs.safety < 40:
                return "They seem on edge."
            if npc_needs.energy < 35:
                return "They look exhausted."
            if npc_needs.social < 45:
                return "They seem glad to have company."
        return f"They seem {self._bond_tone(bond)} toward you."

    def _strongest_other_bond(self, npc_eid):
        social = self.sim.ecs.get(NPCSocial).get(npc_eid)
        if not social:
            return None
        ranked_bonds = sorted(
            (
                (other_eid, info)
                for other_eid, info in social.bonds.items()
                if other_eid != self.player_eid
            ),
            key=lambda item: (float(item[1].get("trust", 0.0)) + float(item[1].get("closeness", 0.0))),
            reverse=True,
        )
        if not ranked_bonds:
            return None
        return ranked_bonds[0]

    def _player_profile(self):
        profile = self.sim.ecs.get(SkillProfile).get(self.player_eid)
        if not profile:
            profile = self.sim.ecs.get(InsightStats).get(self.player_eid)
        if not profile:
            profile = self.sim.ecs.get(CoreStats).get(self.player_eid)
        return profile

    def _owner_label_for(self, prop):
        if not prop:
            return "", ""
        owner_eid = prop.get("owner_eid")
        if owner_eid is not None:
            return _entity_display_name(self.sim, owner_eid, title_case=True), "owner"
        metadata = _property_metadata(prop)
        founder_name = str(metadata.get("business_founder_name") or "").strip()
        if not founder_name:
            founder_first = str(metadata.get("business_founder_first_name") or "").strip()
            founder_last = str(metadata.get("business_founder_last_name") or "").strip()
            founder_name = " ".join(bit for bit in (founder_first, founder_last) if bit).strip()
        if founder_name:
            return founder_name, "founder"
        owner_tag = str(prop.get("owner_tag", "") or "").strip().lower()
        if owner_tag:
            return owner_tag.replace("_", " "), "tag"
        return "", ""

    def _service_summary_for(self, prop):
        if not prop:
            return ""
        bits = []
        if _property_is_storefront(prop):
            service_profile = _storefront_service_profile(self.sim, prop)
            if service_profile.get("available"):
                if service_profile.get("mode") == "automated":
                    bits.append("self-serve trade")
                elif service_profile.get("service_eid") is not None:
                    bits.append("counter trade")
                else:
                    bits.append("trade")
        services = set(_finance_services_for_property(prop))
        if "banking" in services:
            bits.append("banking")
        if "insurance" in services:
            bits.append("insurance")
        for service in _site_services_for_property(prop):
            label = _site_service_label(service).strip().lower()
            if label:
                bits.append(label)
        seen = set()
        ordered = []
        for bit in bits:
            key = str(bit).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            ordered.append(str(bit).strip())
        return ", ".join(ordered)

    def _service_locator_spec(self, topic_id):
        return self.SERVICE_LOCATOR_TOPICS.get(str(topic_id or "").strip().lower())

    def _justice_locator_topic_available(self, context):
        if not isinstance(context, dict) or not bool(context.get("human", True)):
            return False
        occupation = context.get("occupation")
        career = str(getattr(occupation, "career", "") or "").strip().lower()
        role_id = str(context.get("role_id", "") or "").strip().lower()
        organization_kind = str(context.get("organization_kind", "") or "").strip().lower()
        workplace_archetype = _property_archetype(context.get("workplace_prop"))
        owner_place_archetype = _property_archetype(context.get("owner_place"))
        justice_archetypes = set(self.JUSTICE_LOCATOR_ARCHETYPES)
        justice_contact = bool(
            role_id == "guard"
            or any(token in career for token in self.JUSTICE_LOCATOR_ROLE_TOKENS)
            or organization_kind == "civic"
            or workplace_archetype in justice_archetypes
            or owner_place_archetype in justice_archetypes
        )
        player_snapshot = _justice_snapshot(self.sim, self.player_eid)
        player_tier = str((player_snapshot or {}).get("wanted_tier", "clear")).strip().lower() or "clear"
        player_flagged = player_tier in {"questioning", "wanted", "arrest_on_sight"} or bool((player_snapshot or {}).get("in_custody", False))
        if bool(context.get("guarded")):
            return justice_contact
        return justice_contact or player_flagged

    def _service_locator_topic_available(self, context, topic_id):
        if not isinstance(context, dict) or not bool(context.get("human", True)):
            return False
        topic_id = str(topic_id or "").strip().lower()
        if topic_id == "service_justice":
            return self._justice_locator_topic_available(context)
        return not bool(context.get("guarded"))

    def _service_locator_service_keys(self, spec):
        if not isinstance(spec, dict):
            return set()
        return {
            str(service).strip().lower()
            for service in tuple(spec.get("services", ()) or ())
            if str(service).strip()
        }

    def _service_locator_archetypes(self, spec):
        if not isinstance(spec, dict):
            return set()
        return {
            str(archetype).strip().lower()
            for archetype in tuple(spec.get("archetypes", ()) or ())
            if str(archetype).strip()
        }

    def _service_locator_matches(self, spec, *, services=(), archetype="", storefront=False):
        service_keys = self._service_locator_service_keys(spec)
        resolved_services = {
            str(service).strip().lower()
            for service in tuple(services or ())
            if str(service).strip()
        }
        if service_keys and (resolved_services & service_keys):
            return True
        if bool(spec.get("storefront")) and bool(storefront):
            return True
        archetype_key = str(archetype or "").strip().lower()
        if archetype_key and archetype_key in self._service_locator_archetypes(spec):
            return True
        return False

    def _service_locator_rows(self, services, *, radius=None):
        spec = services if isinstance(services, dict) else {"services": tuple(services or ())}
        if not self._service_locator_service_keys(spec) and not bool(spec.get("storefront")) and not self._service_locator_archetypes(spec):
            return ()
        origin = self._player_current_chunk()
        if not origin:
            return ()
        radius = int(self.SERVICE_LOCATOR_SEARCH_RADIUS if radius is None else radius)
        pos = self.sim.ecs.get(Position).get(self.player_eid)
        rows = []
        for prop in self.sim.properties.values():
            prop_services = tuple(_property_services(prop) or ())
            archetype = str(_property_metadata(prop).get("archetype", "") or "").strip().lower()
            if not self._service_locator_matches(
                spec,
                services=prop_services,
                archetype=archetype,
                storefront=_property_is_storefront(prop),
            ):
                continue
            chunk_coord = self.sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
            chunk_distance = _manhattan(origin[0], origin[1], int(chunk_coord[0]), int(chunk_coord[1]))
            if chunk_distance > max(0, int(radius)):
                continue
            tile_distance = 999
            if pos and int(prop.get("z", 0)) == pos.z:
                tile_distance = _manhattan(pos.x, pos.y, int(prop.get("x", 0)), int(prop.get("y", 0)))
            access = _evaluate_property_access(
                self.sim,
                self.player_eid,
                prop,
                x=getattr(pos, "x", None),
                y=getattr(pos, "y", None),
                z=getattr(pos, "z", None),
            )
            rows.append({
                "prop": prop,
                "name": str(prop.get("name", prop.get("id", "site"))).strip() or "site",
                "chunk_coord": (int(chunk_coord[0]), int(chunk_coord[1])),
                "chunk_distance": int(chunk_distance),
                "tile_distance": int(tile_distance),
                "accessible": bool(access.can_use_services),
                "role_priority": 0 if _property_infrastructure_role(prop) == "service_terminal" else 1,
            })
        rows.sort(
            key=lambda row: (
                int(row["chunk_distance"]),
                0 if bool(row["accessible"]) else 1,
                int(row["tile_distance"]),
                int(row["role_priority"]),
                str(row["name"]).lower(),
            )
        )
        return tuple(rows)

    def _service_locator_preview_names(self, services, chunk_coord, *, limit=3):
        spec = services if isinstance(services, dict) else {"services": tuple(services or ())}
        if (
            not self._service_locator_service_keys(spec)
            and not bool(spec.get("storefront"))
            and not self._service_locator_archetypes(spec)
        ) or not chunk_coord:
            return ()
        cx, cy = chunk_coord
        chunk = self.sim.world.get_chunk(int(cx), int(cy))
        names = []

        for block in chunk.get("blocks", ()):
            for building_index, building in enumerate(block.get("buildings", ())):
                archetype = str(building.get("archetype", "")).strip().lower()
                service_seed_token = _building_site_service_seed_token(cx, cy, building, building_index=building_index)
                prop_stub = {"metadata": {"archetype": archetype}} if archetype else {"metadata": {}}
                services_here = (
                    list(_finance_services_for_property(prop_stub))
                    + list(_default_site_services_for_archetype(archetype, seed_token=service_seed_token))
                    + list(vehicle_services_for_archetype(archetype))
                )
                if not self._service_locator_matches(
                    spec,
                    services=services_here,
                    archetype=archetype,
                    storefront=bool(building.get("is_storefront")),
                ):
                    continue
                label = str(building.get("business_name") or archetype.replace("_", " ").title()).strip()
                if label:
                    names.append(label)

        for site_index, site in enumerate(chunk.get("sites", ())):
            kind = str(site.get("kind", "")).strip().lower()
            service_seed_token = _site_service_seed_token(cx, cy, site, site_index=site_index)
            gameplay = site_gameplay_profile(site)
            prop_stub = {"metadata": {"archetype": kind}} if kind else {"metadata": {}}
            configured_site_services = list(gameplay.get("site_services", ()))
            if not configured_site_services:
                configured_site_services = list(_default_site_services_for_archetype(kind, seed_token=service_seed_token))
            services_here = (
                list(_finance_services_for_property(prop_stub))
                + configured_site_services
                + list(vehicle_services_for_archetype(kind))
            )
            if not self._service_locator_matches(
                spec,
                services=services_here,
                archetype=kind,
                storefront=False,
            ):
                continue
            label = str(site.get("name") or kind.replace("_", " ").title()).strip()
            if label:
                names.append(label)

        deduped = []
        seen = set()
        for name in names:
            key = str(name).strip().lower()
            if not key or key in seen:
                continue
            seen.add(key)
            deduped.append(str(name).strip())
        return tuple(deduped[: max(1, int(limit))])

    def _nearest_service_locator_preview(self, services, *, radius=None, limit=3):
        origin = self._player_current_chunk()
        if not origin:
            return None, ()
        radius = int(self.SERVICE_LOCATOR_SEARCH_RADIUS if radius is None else radius)
        ox, oy = origin
        for dist in range(0, max(1, int(radius)) + 1):
            matches = []
            for cx in range(int(ox) - dist, int(ox) + dist + 1):
                for cy in range(int(oy) - dist, int(oy) + dist + 1):
                    if abs(cx - int(ox)) + abs(cy - int(oy)) != dist:
                        continue
                    names = self._service_locator_preview_names(services, (cx, cy), limit=limit)
                    if names:
                        matches.append(((int(cx), int(cy)), names))
            if matches:
                matches.sort(key=lambda row: (row[0][1], row[0][0]))
                return matches[0]
        return None, ()

    def _service_locator_chunk_clause(self, spec, chunk_coord, *, lead_prop=None):
        if not chunk_coord:
            return ""

        cx, cy = int(chunk_coord[0]), int(chunk_coord[1])
        desc = self.sim.world.overworld_descriptor(cx, cy)
        if str(desc.get("area_type", "city")).strip().lower() == "city":
            return ""

        lead_meta = _property_metadata(lead_prop) if isinstance(lead_prop, dict) else {}
        extra_site_kinds = []
        for field in ("site_kind", "archetype"):
            label = str(lead_meta.get(field, "") or "").strip().lower()
            if label:
                extra_site_kinds.append(label)

        chunk = self.sim.world.get_chunk(cx, cy)
        site_kinds = _chunk_site_kinds(chunk, extra_site_kinds)
        interest = self.sim.world.overworld_interest(cx, cy, descriptor=desc)
        travel = self.sim.world.overworld_travel_profile(cx, cy, descriptor=desc, interest=interest)
        discovery = self.sim.world.overworld_discovery_profile(cx, cy, descriptor=desc, interest=interest, travel=travel)
        identity = _overworld_identity_profile(
            self.sim,
            cx,
            cy,
            desc=desc,
            interest=interest,
            travel=travel,
            discovery=discovery,
            site_kinds=site_kinds,
        )
        theme_id = str(identity.get("theme_id", "") or "").strip().lower()
        label = str(identity.get("label", "") or "").strip()
        if not theme_id or not label:
            return ""

        service_keys = self._service_locator_service_keys(spec)
        if theme_id == "route_hub":
            if service_keys & set(TRANSIT_SERVICE_IDS):
                return f"That chunk carries a {label} read, so transit turnover stays active there."
            if service_keys & {"rest", "shelter", "fuel", "repair", "trade", "vehicle_fetch"} or bool(spec.get("storefront")):
                return f"That chunk carries a {label} read, so traveler services tend to bunch up there."
            return f"That chunk carries a {label} read, so traffic turns over fast there."

        if theme_id == "parts_yard":
            if service_keys & {"repair", "fuel", "vehicle_fetch", "vehicle_sales_used", "vehicle_sales_new"}:
                return f"That chunk carries a {label} read, so repair jobs and spare parts tend to collect there."
            return f"That chunk carries a {label} read, so salvage crews leave useful scraps behind."

        if theme_id == "watch_network":
            return f"That chunk carries a {label} read, so lookout traffic and quiet watchers linger there."

        if theme_id == "field_refuge":
            if service_keys & {"rest", "shelter"}:
                return f"That chunk carries a {label} read, so people lean on it for shelter and recovery."
            return f"That chunk carries a {label} read, so water and quiet cover matter there."

        return ""

    def _service_locator_summary_with_chunk_clause(self, summary, spec, chunk_coord, *, lead_prop=None):
        summary = str(summary or "").strip()
        clause = self._service_locator_chunk_clause(spec, chunk_coord, lead_prop=lead_prop)
        if not clause:
            return summary
        if not summary:
            return clause
        if summary[-1] not in ".!?":
            summary = f"{summary}."
        return f"{summary} {clause}"

    def _service_locator_summary(self, context, topic_id):
        spec = self._service_locator_spec(topic_id)
        if not isinstance(spec, dict):
            return {"summary": "", "service_label": "service", "lead_prop": None}

        service_label = str(spec.get("service_label", "service")).strip() or "service"
        offer_label = str(spec.get("offer_label", service_label)).strip() or service_label
        local_template = str(spec.get("local_summary", "")).strip()
        near_template = str(spec.get("near_summary", "")).strip()
        rows = list(self._service_locator_rows(spec, radius=self.SERVICE_LOCATOR_SEARCH_RADIUS))
        origin = self._player_current_chunk()

        if rows:
            best_chunk = tuple(rows[0]["chunk_coord"])
            names = []
            seen = set()
            lead_prop = None
            for row in rows:
                if tuple(row["chunk_coord"]) != best_chunk:
                    continue
                name = str(row["name"]).strip()
                key = name.lower()
                if name and key not in seen:
                    seen.add(key)
                    names.append(name)
                if lead_prop is None:
                    lead_prop = row["prop"]
                if len(names) >= 3:
                    break
            names_text = _dialogue_human_join(names)
            if best_chunk == origin:
                if local_template:
                    summary = local_template.format(
                        names_text=names_text,
                        offer_label=offer_label,
                        service_label=service_label,
                    )
                else:
                    summary = f"In this chunk, {names_text} can handle {offer_label}."
                summary = self._service_locator_summary_with_chunk_clause(
                    summary,
                    spec,
                    best_chunk,
                    lead_prop=lead_prop,
                )
                return {
                    "summary": summary,
                    "service_label": service_label,
                    "lead_prop": lead_prop,
                }
            distance = _manhattan(origin[0], origin[1], best_chunk[0], best_chunk[1])
            direction = self._dialogue_chunk_direction(origin, best_chunk)
            distance_phrase = self._humanize_distance_with_direction(distance, direction, context)
            if near_template:
                summary = near_template.format(
                    names_text=names_text,
                    offer_label=offer_label,
                    service_label=service_label,
                    distance_phrase=distance_phrase,
                )
            else:
                summary = f"Nearest {service_label} I know is {distance_phrase} at {names_text}."
            summary = self._service_locator_summary_with_chunk_clause(
                summary,
                spec,
                best_chunk,
                lead_prop=lead_prop,
            )
            return {
                "summary": summary,
                "service_label": service_label,
                "lead_prop": lead_prop,
            }

        chunk_coord, names = self._nearest_service_locator_preview(
            spec,
            radius=self.SERVICE_LOCATOR_SEARCH_RADIUS,
            limit=3,
        )
        if chunk_coord and names:
            names_text = _dialogue_human_join(names)
            if tuple(chunk_coord) == origin:
                if local_template:
                    summary = local_template.format(
                        names_text=names_text,
                        offer_label=offer_label,
                        service_label=service_label,
                    )
                else:
                    summary = f"In this chunk, {names_text} can handle {offer_label}."
                summary = self._service_locator_summary_with_chunk_clause(
                    summary,
                    spec,
                    chunk_coord,
                )
                return {
                    "summary": summary,
                    "service_label": service_label,
                    "lead_prop": None,
                }
            distance = _manhattan(origin[0], origin[1], int(chunk_coord[0]), int(chunk_coord[1]))
            direction = self._dialogue_chunk_direction(origin, chunk_coord)
            distance_phrase = self._humanize_distance_with_direction(distance, direction, context)
            if near_template:
                summary = near_template.format(
                    names_text=names_text,
                    offer_label=offer_label,
                    service_label=service_label,
                    distance_phrase=distance_phrase,
                )
            else:
                summary = f"Nearest {service_label} I know is {distance_phrase} at {names_text}."
            summary = self._service_locator_summary_with_chunk_clause(
                summary,
                spec,
                chunk_coord,
            )
            return {
                "summary": summary,
                "service_label": service_label,
                "lead_prop": None,
            }

        return {"summary": "", "service_label": service_label, "lead_prop": None}

    # ── Fence helpers ────────────────────────────────────────────────────────

    _FENCE_ITEM_VALUE = {
        "weapon": 50, "firearm": 50, "gear": 32, "armor": 32,
        "tool": 24, "access": 28, "stimulant": 18, "drug": 18,
    }
    _FENCE_DEFAULT_VALUE = 14

    def _fence_illegal_items(self, player_eid):
        inventory = self.sim.ecs.get(Inventory).get(player_eid)
        if not inventory:
            return []
        result = []
        for entry in inventory.items:
            item_id = entry.get("item_id") or ""
            item_def = ITEM_CATALOG.get(item_id, {})
            if str(item_def.get("legal_status", "legal")).strip().lower() != "illegal":
                continue
            result.append(entry)
        return result

    def _fence_item_value(self, item_id):
        item_def = ITEM_CATALOG.get(item_id, {})
        tags = set(str(t).strip().lower() for t in item_def.get("tags", ()))
        for tag, val in self._FENCE_ITEM_VALUE.items():
            if tag in tags:
                return val
        return self._FENCE_DEFAULT_VALUE

    def _fence_payout_preview(self, player_eid):
        items = self._fence_illegal_items(player_eid)
        if not items:
            return 0
        total = sum(self._fence_item_value(e.get("item_id", "")) for e in items)
        return max(10, int(total * 0.55))

    def _fence_available_for(self, npc_eid, contact_standing, guarded):
        if guarded:
            return False
        if float(contact_standing) < self.FENCE_MIN_STANDING:
            return False
        if self.sim.tick < self.fence_cooldown_ticks.get(npc_eid, 0):
            return False
        justice_profile = self.sim.ecs.get(JusticeProfile).get(npc_eid)
        corruption = float(getattr(justice_profile, "corruption", 0.0))
        if corruption < self.FENCE_MIN_CORRUPTION:
            return False
        return bool(self._fence_illegal_items(self.player_eid))

    def _hire_runner_available_for(self, npc_eid, contact_standing, guarded):
        if guarded:
            return False
        if float(contact_standing) < self.CONTRACTOR_MIN_STANDING:
            return False
        # Guard/scout NPCs won't accept — they're already on payroll.
        ai = self.sim.ecs.get(AI).get(npc_eid)
        if ai and str(getattr(ai, "role", "")).strip().lower() in {"guard", "scout"}:
            return False
        # Needs enough moral flexibility.
        justice_profile = self.sim.ecs.get(JusticeProfile).get(npc_eid)
        corruption = float(getattr(justice_profile, "corruption", 0.0))
        enforce_all = bool(getattr(justice_profile, "enforce_all", False))
        if enforce_all or corruption < self.CONTRACTOR_MIN_CORRUPTION:
            return False
        # Player must be able to afford it.
        assets = self.sim.ecs.get(PlayerAssets).get(self.player_eid)
        if not assets or int(getattr(assets, "credits", 0)) < self.CONTRACTOR_COST:
            return False
        return True

    def _active_backup_contract(self, npc_eid):
        rec = _active_contractor_record(
            self.sim,
            npc_eid,
            ally_eid=self.player_eid,
            jobs={"backup", "party"},
        )
        return rec if isinstance(rec, dict) else None

    def _active_peaceful_surrender(self, npc_eid, *, ensure=False):
        rec = _active_contractor_record(
            self.sim,
            npc_eid,
            ally_eid=self.player_eid,
            jobs={"surrendered"},
        )
        if isinstance(rec, dict) or not ensure:
            return rec if isinstance(rec, dict) else None

        suppression = self.sim.ecs.get(SuppressionState).get(npc_eid)
        pos = self.sim.ecs.get(Position).get(npc_eid)
        if not suppression or not bool(getattr(suppression, "surrendered", False)) or not pos:
            return None

        contractors = getattr(self.sim, "contractors", None)
        if not isinstance(contractors, dict):
            self.sim.contractors = {}
            contractors = self.sim.contractors

        rec = {
            "hired_tick": int(self.sim.tick),
            "until": int(self.sim.tick) + 999999,
            "cost": 0,
            "job": "surrendered",
            "ally_eid": self.player_eid,
            "order": "hold",
            "order_target": (int(pos.x), int(pos.y), int(pos.z)),
        }
        contractors[npc_eid] = rec
        return rec

    def _contractor_order_mode(self, rec):
        if not isinstance(rec, dict):
            return "passive"
        mode = str(rec.get("order", "passive") or "passive").strip().lower()
        return mode or "passive"

    def _contractor_order_target(self, rec):
        return _contractor_order_target_from_record(rec)

    def _set_contractor_order(self, rec, mode, *, target=None, target_eid=None, wait_ticks=0, kill_surcharge=0):
        if not isinstance(rec, dict):
            return None
        rec["order"] = str(mode or "passive").strip().lower() or "passive"
        rec.pop("focus_threat_eid", None)
        rec.pop("focus_threat_until", None)
        rec.pop("order_target", None)
        rec.pop("order_target_eid", None)
        rec.pop("order_wait_ticks", None)
        rec.pop("order_wait_started", None)
        rec.pop("kill_surcharge_paid", None)
        if target is not None:
            rec["order_target"] = (
                int(target[0]),
                int(target[1]),
                int(target[2]),
            )
        if target_eid is not None:
            rec["order_target_eid"] = int(target_eid)
        if wait_ticks > 0:
            rec["order_wait_ticks"] = int(wait_ticks)
        if kill_surcharge > 0:
            rec["kill_surcharge_paid"] = int(kill_surcharge)
        return rec

    def _format_dialog_map_marker(self, x, y, z):
        return _dialog_map_marker_for_player(self.sim, self.player_eid, x, y, z)

    def _dialogue_backup_cursor_data(self, npc_eid):
        dialog_state = self._dialog_ui_state()
        state = getattr(self.sim, "look_ui", None)
        if isinstance(state, dict) and bool(state.get("active")) and str(state.get("mode", "city")).strip().lower() == "city":
            payload = _dialog_backup_cursor_payload(
                self.sim,
                self.player_eid,
                npc_eid,
                state.get("x", 0),
                state.get("y", 0),
                state.get("z", 0),
            )
            if payload:
                return payload
        mark = _dialog_backup_mark_from_state(dialog_state)
        if not mark:
            return {}
        return _dialog_backup_cursor_payload(
            self.sim,
            self.player_eid,
            npc_eid,
            mark.get("x", 0),
            mark.get("y", 0),
            mark.get("z", 0),
        )

    def _contractor_kill_terms(self, npc_eid, *, bond=None):
        bond = bond if isinstance(bond, dict) else self._bond_snapshot(npc_eid) or {}
        trust = float(bond.get("trust", 0.0) or 0.0)
        closeness = float(bond.get("closeness", 0.0) or 0.0)
        protectiveness = float(bond.get("protectiveness", 0.0) or 0.0)
        relation = str(bond.get("kind", "") or "").strip().lower()

        trust_score = (trust * 0.45) + (closeness * 0.3) + (protectiveness * 0.25)
        trusted = relation in {"family", "partner"} or (
            trust >= 0.72 and closeness >= 0.62 and trust_score >= 0.76
        )
        surcharge = 0 if trusted else int(self.CONTRACTOR_KILL_SURCHARGE)
        assets = self.sim.ecs.get(PlayerAssets).get(self.player_eid)
        credits = int(getattr(assets, "credits", 0)) if assets else 0
        return {
            "trusted": bool(trusted),
            "surcharge": surcharge,
            "can_pay": surcharge <= 0 or credits >= surcharge,
            "credits": credits,
        }

    def _contractor_order_status(self, rec):
        mode = self._contractor_order_mode(rec)
        job = str((rec or {}).get("job", "") or "").strip().lower()
        if mode == "hold":
            return "staying put" if job == "surrendered" else "holding here"
        if mode == "goto_wait":
            target = self._contractor_order_target(rec)
            if target:
                return f"posted at {self._format_dialog_map_marker(*target)}"
            return "posted up"
        if mode == "wait_return":
            target = self._contractor_order_target(rec)
            if target:
                return f"posted at {self._format_dialog_map_marker(*target)}, then back"
            return "posted up, then back"
        if mode == "distraction":
            return "running a distraction"
        if mode == "kill":
            target_eid = rec.get("order_target_eid")
            target_name = _entity_display_name(self.sim, target_eid, title_case=True) if target_eid is not None else ""
            if target_name:
                return f"hunting {target_name}"
            return "on a hard job"
        if job == "surrendered":
            return "waiting on you"
        return "passive cover"

    # ── End fence helpers ────────────────────────────────────────────────────

    def _trade_context(self, npc_eid, workplace_prop, current_prop):
        player_pos = self.sim.ecs.get(Position).get(self.player_eid)
        if not player_pos:
            return None
        for prop in (workplace_prop, current_prop):
            if not prop or not _property_is_storefront(prop):
                continue
            access = _evaluate_property_access(
                self.sim,
                self.player_eid,
                prop,
                x=player_pos.x,
                y=player_pos.y,
                z=player_pos.z,
            )
            if not access.can_use_services:
                continue
            service = _storefront_service_profile(self.sim, prop)
            if not service.get("available"):
                continue
            if service.get("service_eid") not in {None, npc_eid}:
                continue
            return {"property_id": prop["id"], "prop": prop, "service": service}
        return None

    def _player_business_staffing_options(self, context):
        if not isinstance(context, dict):
            return {"hire": None, "fire": None}
        if bool(context.get("guarded")) or not bool(context.get("human", True)):
            return {"hire": None, "fire": None}

        npc_eid = context.get("npc_eid")
        if npc_eid in {None, self.player_eid}:
            return {"hire": None, "fire": None}

        fire_record = actor_player_business_employment(self.sim, npc_eid, owner_eid=self.player_eid)
        fire_option = None
        if fire_record:
            fire_prop = fire_record.get("prop")
            fire_option = {
                "property_id": str((fire_prop or {}).get("id", "")).strip(),
                "prop": fire_prop,
                "business_name": str((fire_prop or {}).get("metadata", {}).get("business_name", "")).strip()
                or str((fire_prop or {}).get("name", "Business")).strip()
                or "Business",
                "role": str(fire_record.get("role", "staff") or "staff").strip().lower() or "staff",
            }

        hire_option = None
        occupation = self.sim.ecs.get(Occupation).get(npc_eid)
        workplace = getattr(occupation, "workplace", None)
        employed_elsewhere = bool(
            isinstance(workplace, dict)
            and str(workplace.get("property_id", "")).strip()
            and fire_option is None
        )
        if not employed_elsewhere and fire_option is None:
            targets = list(player_business_staffing_targets(self.sim, self.player_eid))
            if targets:
                preferred_ids = []
                for key in ("current_prop", "owner_place", "workplace_prop"):
                    prop = context.get(key)
                    property_id = str((prop or {}).get("id", "")).strip() if isinstance(prop, dict) else ""
                    if property_id and property_id not in preferred_ids:
                        preferred_ids.append(property_id)

                player_pos = self.sim.ecs.get(Position).get(self.player_eid)
                npc_pos = self.sim.ecs.get(Position).get(npc_eid)
                scored = []
                for target in targets:
                    prop = target.get("prop")
                    property_id = str(target.get("property_id", "")).strip()
                    score = 0
                    if property_id in preferred_ids:
                        score += max(40, 140 - (preferred_ids.index(property_id) * 22))
                    if player_pos is not None:
                        score += max(0, 12 - _property_distance(player_pos.x, player_pos.y, prop)) * 5
                    if npc_pos is not None and int(npc_pos.z) == int((prop or {}).get("z", npc_pos.z)):
                        score += max(0, 10 - _property_distance(npc_pos.x, npc_pos.y, prop)) * 3
                    score += int(target.get("shortage", 0) or 0) * 18
                    if str(target.get("open_role", "")).strip().lower() == "manager":
                        score += 16
                    if str((target.get("summary") or {}).get("note", "")).strip().lower() == "no staff":
                        score += 10
                    scored.append((-score, str(target.get("business_name", "")).lower(), property_id, target))

                if scored:
                    scored.sort()
                    best = scored[0][3]
                    open_roles = tuple(
                        str(role).strip().lower()
                        for role in tuple(best.get("open_roles", ()) or ())
                        if str(role).strip()
                    )
                    primary_role = str(best.get("open_role", "staff") or "staff").strip().lower() or "staff"
                    if not open_roles:
                        open_roles = (primary_role,)
                    hire_option = {
                        "property_id": str(best.get("property_id", "")).strip(),
                        "prop": best.get("prop"),
                        "business_name": str(best.get("business_name", "")).strip() or "Business",
                        "role": primary_role,
                        "roles": open_roles,
                    }

        return {
            "hire": hire_option,
            "fire": fire_option,
        }

    def _player_business_hire_decision(self, context, option):
        if not isinstance(option, dict):
            return False, "no_opening"
        if bool(context.get("guarded")):
            return False, "guarded"

        role_id = str(context.get("role_id", "") or "").strip().lower()
        career_text = str(context.get("career_text", "") or "").strip().lower()
        if role_id == "guard" or "guard" in career_text or "security" in career_text:
            return False, "career_conflict"

        npc_needs = context.get("npc_needs")
        tone = str(context.get("tone", "neutral") or "neutral").strip().lower()
        pressure_tier = str(context.get("pressure_tier", "low") or "low").strip().lower()
        conversation = float(_actor_skill(self.sim, self.player_eid, "conversation", default=5.0))
        streetwise = float(_actor_skill(self.sim, self.player_eid, "streetwise", default=5.0))
        social_standing = float(context.get("social_standing", 0.0) or 0.0)

        score = 0.26
        score += social_standing * 0.38
        score += (conversation / 10.0) * 0.18
        score += (streetwise / 10.0) * 0.08
        if str(option.get("role", "staff")).strip().lower() == "manager" and (
            "manager" in career_text or "lead" in career_text or "supervisor" in career_text
        ):
            score += 0.08
        if isinstance(context.get("current_prop"), dict) and str(context["current_prop"].get("id", "")).strip() == str(option.get("property_id", "")).strip():
            score += 0.08
        if tone == "friendly":
            score += 0.06
        elif tone in {"wary", "guarded"}:
            score -= 0.08
        if pressure_tier == "high":
            score -= 0.05
        elif pressure_tier == "medium":
            score -= 0.02
        if npc_needs:
            if float(getattr(npc_needs, "safety", 100.0)) < 38.0:
                score -= 0.06
            if float(getattr(npc_needs, "energy", 100.0)) < 28.0:
                score -= 0.04

        threshold = 0.5 if str(option.get("role", "staff")).strip().lower() == "staff" else 0.56
        return score >= threshold, "accepted" if score >= threshold else "declined"

    def _player_business_hire_option_for_role(self, context, role):
        option = context.get("player_business_hire_option") if isinstance(context, dict) else None
        if not isinstance(option, dict):
            return None
        role_key = str(role or "").strip().lower()
        available_roles = tuple(
            str(entry).strip().lower()
            for entry in tuple(option.get("roles", ()) or ())
            if str(entry).strip()
        )
        if role_key not in {"manager", "staff"}:
            return None
        if available_roles and role_key not in available_roles:
            return None
        resolved = dict(option)
        resolved["role"] = role_key
        resolved["roles"] = available_roles or (role_key,)
        return resolved

    def _player_business_skill_text(self, skill_ids, *, limit=2):
        labels = []
        for skill_id in tuple(skill_ids or ())[: max(1, int(limit or 0))]:
            label = str(_skill_label(skill_id)).strip()
            if label and label not in labels:
                labels.append(label)
        return " + ".join(labels)

    def _player_business_hire_preview(self, npc_eid, option):
        if npc_eid is None or not isinstance(option, dict):
            return None
        prop = option.get("prop")
        if not isinstance(prop, dict):
            return None
        role = str(option.get("role", "staff") or "staff").strip().lower() or "staff"
        fit = player_business_role_fit(self.sim, npc_eid, prop, role)
        if not isinstance(fit, dict):
            return None

        label = str(fit.get("label", "solid")).strip().lower() or "solid"
        strengths_text = self._player_business_skill_text(fit.get("strong_skills", ()))
        weak_text = self._player_business_skill_text(fit.get("weak_skills", ()))

        topic_hint = f"{label} fit"
        if label in {"weak", "patchy"} and weak_text:
            topic_hint = f"{topic_hint}; light on {weak_text}"
        elif strengths_text:
            topic_hint = f"{topic_hint}; {strengths_text}"

        if role == "manager":
            if label in {"excellent", "strong"}:
                line = f"Running it looks like a {label} fit for me."
            elif label in {"weak", "patchy"} and weak_text:
                line = f"Running it looks {label}; I'd be light on {weak_text}."
            else:
                line = f"Running it looks like a {label} fit for me."
        else:
            if label in {"excellent", "strong"}:
                line = f"Shift work there looks like a {label} fit for me."
            elif label in {"weak", "patchy"} and weak_text:
                line = f"Shift work there looks {label}; I'd be light on {weak_text}."
            else:
                line = f"Shift work there looks like a {label} fit for me."

        return {
            "role": role,
            "fit": fit,
            "label": label,
            "topic_hint": topic_hint,
            "line": line,
        }

    def _resolve_player_business_hire(self, context, option, *, npc_eid):
        if not isinstance(option, dict):
            return {"npc_lines": ["No. I am not taking work from you right now."]}
        accepted, reason = self._player_business_hire_decision(context, option)
        business_name = str(option.get("business_name", "the business")).strip() or "the business"
        role = str(option.get("role", "staff") or "staff").strip().lower() or "staff"
        if not accepted:
            if reason == "guarded":
                line = "No. Not after this."
            elif reason == "career_conflict":
                line = f"No. {business_name} is not my kind of work."
            elif role == "manager":
                line = f"Not me. I am not taking point on {business_name}."
            else:
                line = f"Maybe another time. I am not taking work at {business_name} right now."
            return {"npc_lines": [line]}
        outcome = hire_actor_into_player_business(
            self.sim,
            self.player_eid,
            npc_eid,
            option.get("prop"),
            role=role,
        )
        if not isinstance(outcome, dict):
            return {"npc_lines": [f"I cannot commit to {business_name} right now."]}
        self.sim.emit(Event(
            "player_business_staff_hired",
            eid=self.player_eid,
            npc_eid=npc_eid,
            property_id=outcome.get("property_id"),
            business_name=outcome.get("business_name"),
            role=outcome.get("role"),
            career=outcome.get("career"),
            housing_kind=outcome.get("housing_kind"),
            housing_local=outcome.get("housing_local"),
            housing_relocated=outcome.get("housing_relocated"),
            housing_property_id=outcome.get("housing_property_id"),
            housing_name=outcome.get("housing_name"),
        ))
        self._shift_dialogue_bond(
            npc_eid,
            trust_delta=0.04 if role == "manager" else 0.03,
            closeness_delta=0.025 if role == "manager" else 0.02,
            guarded=False,
        )
        housing_kind = str(outcome.get("housing_kind", "") or "").strip().lower()
        housing_name = str(outcome.get("housing_name", "") or "").strip()
        if role == "manager":
            line = f"Yeah. I can run {business_name} for you."
        else:
            line = f"Sure. I can take a shift at {business_name}."
        if housing_kind == "workplace_lodging":
            line = line[:-1] + " and stay on-site."
        elif housing_kind in {"nearby_housing", "nearby_lodging"} and housing_name:
            line = line[:-1] + f" and stay at {housing_name}."
        return {"npc_lines": [line], "close": True}

    def _organization_snapshot(self, npc_eid, occupation, workplace_prop):
        workplace = getattr(occupation, "workplace", None)
        organization_eid = None
        organization_text = ""
        organization_kind = ""
        if isinstance(workplace, dict):
            raw_org_eid = workplace.get("organization_eid")
            try:
                organization_eid = int(raw_org_eid)
            except (TypeError, ValueError):
                organization_eid = None
            organization_text = str(workplace.get("organization_name", "")).strip()
            organization_kind = str(workplace.get("organization_kind", "")).strip().lower()

        members = ()
        if workplace_prop:
            property_org_eid = property_organization_eid(self.sim, workplace_prop, ensure=True)
            if organization_eid is None:
                organization_eid = property_org_eid
            if not organization_text:
                organization_text = organization_name(self.sim, organization_eid)
            if not organization_kind:
                organization_kind = str(_property_metadata(workplace_prop).get("organization_kind", "")).strip().lower()
            members = tuple(property_org_members(self.sim, workplace_prop))
        elif organization_eid is not None and not organization_text:
            organization_text = organization_name(self.sim, organization_eid)

        member_by_eid = {
            int(row.get("eid")): row
            for row in members
            if row.get("eid") is not None
        }
        self_member = member_by_eid.get(int(npc_eid))
        organization_role = str((self_member or {}).get("role", "") or "").strip().lower()
        if not organization_role and workplace_prop and workplace_prop.get("owner_eid") == npc_eid:
            organization_role = "owner"

        supervisor_row = None
        if organization_role == "owner":
            supervisor_row = self_member
        else:
            preferred_roles = ("owner", "manager")
            if organization_role == "manager":
                preferred_roles = ("owner",)
            for preferred_role in preferred_roles:
                for row in members:
                    if int(row.get("eid", -1)) == int(npc_eid):
                        continue
                    if str(row.get("role", "") or "").strip().lower() != preferred_role:
                        continue
                    supervisor_row = row
                    break
                if supervisor_row:
                    break

        coworker_rows = []
        for row in members:
            try:
                row_eid = int(row.get("eid"))
            except (TypeError, ValueError):
                continue
            if row_eid == int(npc_eid):
                continue
            if supervisor_row and row_eid == int(supervisor_row.get("eid")):
                continue
            row_role = str(row.get("role", "") or "").strip().lower()
            if row_role in {"owner", "manager"}:
                continue
            coworker_rows.append(row)

        if not coworker_rows:
            for row in members:
                try:
                    row_eid = int(row.get("eid"))
                except (TypeError, ValueError):
                    continue
                if row_eid == int(npc_eid):
                    continue
                if supervisor_row and row_eid == int(supervisor_row.get("eid")):
                    continue
                coworker_rows.append(row)

        coworker_names = []
        for row in coworker_rows:
            try:
                row_eid = int(row.get("eid"))
            except (TypeError, ValueError):
                continue
            coworker_name = _entity_display_name(self.sim, row_eid, title_case=True)
            if coworker_name and coworker_name not in coworker_names:
                coworker_names.append(coworker_name)

        supervisor_name = ""
        supervisor_role = ""
        if supervisor_row:
            supervisor_name = _entity_display_name(self.sim, supervisor_row.get("eid"), title_case=True)
            supervisor_role = str(supervisor_row.get("role", "") or "").strip().lower()

        return {
            "organization_eid": organization_eid,
            "organization_name": organization_text,
            "organization_kind": organization_kind,
            "organization_role": organization_role,
            "supervisor_name": supervisor_name,
            "supervisor_role": supervisor_role,
            "coworker_names": tuple(coworker_names),
            "coworker_count": len(coworker_names),
            "member_count": len(members),
        }

    def _dialogue_context(self, npc_eid, *, bond=None):
        positions = self.sim.ecs.get(Position)
        npc_pos = positions.get(npc_eid)
        player_pos = positions.get(self.player_eid)
        if not npc_pos or not player_pos or npc_pos.z != player_pos.z:
            return None
        if _manhattan(player_pos.x, player_pos.y, npc_pos.x, npc_pos.y) > 1:
            return None
        if _entity_is_downed(self.sim, npc_eid):
            return None
        identity = self.sim.ecs.get(CreatureIdentity).get(npc_eid)
        ai = self.sim.ecs.get(AI).get(npc_eid)
        occupation = self.sim.ecs.get(Occupation).get(npc_eid)
        routine = self.sim.ecs.get(NPCRoutine).get(npc_eid)
        npc_needs = self.sim.ecs.get(NPCNeeds).get(npc_eid)
        npc_traits = self.sim.ecs.get(NPCTraits).get(npc_eid)
        memory = self.sim.ecs.get(NPCMemory).get(npc_eid)
        door_wait_state = self.sim.ecs.get(DoorWaitState).get(npc_eid)
        suppression = self.sim.ecs.get(SuppressionState).get(npc_eid)
        portfolio = self.sim.ecs.get(PropertyPortfolio).get(npc_eid)
        recent_offense = self._recent_player_offense(memory)
        door_answering = False
        if isinstance(door_wait_state, DoorWaitState) and not door_wait_state.is_expired(self.sim.tick):
            try:
                door_answering = int(getattr(door_wait_state, "caller_eid", -1)) == int(self.player_eid)
            except (TypeError, ValueError):
                door_answering = getattr(door_wait_state, "caller_eid", None) == self.player_eid
        door_answer_mood = (
            str(getattr(door_wait_state, "mood", "neutral") or "neutral").strip().lower()
            if door_answering
            else ""
        )
        trespass_prop = self._current_trespass_property(npc_eid, player_pos)
        guarded = bool(
            trespass_prop
            or (recent_offense and float(recent_offense.get("strength", 0.0)) >= 0.18)
            or (door_answering and door_answer_mood in {"hostile", "irritated"})
        )
        peaceful_orders_only = bool(suppression and suppression.surrendered)
        display_name = _entity_display_name(self.sim, npc_eid, title_case=True)
        career_text = _career_label(occupation)
        role_id = str(getattr(ai, "role", "") or "").strip().lower() or "local"
        role_text = str(getattr(ai, "role", "") or "").replace("_", " ").strip() or "local"
        state_text = self._state_text(ai)
        scene_note = _business_event_actor_note(self.sim, npc_eid) if npc_eid is not None else None
        workplace_prop = _workplace_property(self.sim, occupation=occupation, routine=routine)
        home_prop = _home_property(self.sim, routine=routine)
        owned_prop = None
        if portfolio:
            for property_id in sorted(portfolio.owned_property_ids):
                prop = self.sim.properties.get(property_id)
                if prop:
                    owned_prop = prop
                    break
        dialogue_memory = self._dialogue_memory(npc_eid)
        current_prop = _property_covering(self.sim, player_pos.x, player_pos.y, player_pos.z)
        if current_prop is None:
            current_prop = _property_for_action(self.sim, player_pos, radius=1)
        if current_prop is not None and str(current_prop.get("kind", "") or "").strip().lower() != "building":
            linked_prop = _infrastructure_target_property(self.sim, current_prop)
            if linked_prop is not None:
                current_prop = linked_prop
        referenced_place_prop = None
        referenced_place_id = str(dialogue_memory.get("last_property_id", "") or "").strip()
        if referenced_place_id:
            candidate = self.sim.properties.get(referenced_place_id)
            if isinstance(candidate, dict):
                referenced_place_prop = candidate
        scene_prop = None
        if isinstance(scene_note, dict):
            scene_property_id = str(scene_note.get("property_id", "") or "").strip()
            if scene_property_id:
                scene_prop = self.sim.properties.get(scene_property_id)
        owner_place = workplace_prop or current_prop or owned_prop or scene_prop
        owner_place_name = str(owner_place.get("name", owner_place.get("id", "place"))).strip() if owner_place else ""
        referenced_place_name = (
            str(referenced_place_prop.get("name", referenced_place_prop.get("id", "place"))).strip()
            if referenced_place_prop else ""
        )
        organization = self._organization_snapshot(npc_eid, occupation, workplace_prop)
        bond = bond if bond is not None else self._bond_snapshot(npc_eid)
        rapport = self._conversation_rapport()
        intro_entry = self._player_person_contact_entry(npc_eid)
        intro_standing = float((intro_entry or {}).get("standing", 0.0))
        trust = float((bond or {}).get("trust", 0.0))
        closeness = float((bond or {}).get("closeness", 0.0))
        bond_score = (trust * 0.6) + (closeness * 0.4)
        contact_standing = self._contact_standing(bond, rapport)
        social_standing = max(contact_standing, intro_standing)
        fallout_rep = max(intro_standing, bond_score)
        pressure = _pressure_snapshot(self.sim)
        pressure_effects = dict(pressure.get("effects", {}) if isinstance(pressure, dict) else {})
        pressure_tier = str(pressure.get("tier", "low")).strip().lower() or "low"
        if door_answering:
            tone = {
                "hostile": "guarded",
                "irritated": "wary",
                "friendly": "friendly",
            }.get(door_answer_mood, "neutral")
        else:
            tone = "guarded" if guarded else self._pressure_adjusted_tone(
                self._bond_tone(bond),
                pressure_tier=pressure_tier,
                standing=social_standing,
                recent_offense=bool(recent_offense),
            )
        lead_confidence = min(0.96, 0.56 + (rapport * 0.28))
        chunk = {}
        world = getattr(self.sim, "world", None)
        if world is not None:
            chunk = world.get_chunk(*self.sim.chunk_coords(npc_pos.x, npc_pos.y))
        district = chunk.get("district", {}) if isinstance(chunk, dict) else {}
        if not isinstance(district, dict):
            district = {}
        area_type = str(district.get("area_type", "city")).strip().lower() or "city"
        district_type = str(district.get("district_type", "unknown")).strip().lower() or "unknown"
        owner_name, owner_source = self._owner_label_for(owner_place)
        service_summary = self._service_summary_for(owner_place)
        controller = _property_access_controller(self.sim, owner_place) if owner_place else {}
        access_level = _property_access_level(owner_place) if owner_place else ""
        hours_text = _dialogue_hours_text(controller.get("opening_window"))
        shift_text = ""
        shift_start = getattr(occupation, "shift_start", None) if occupation else None
        shift_end = getattr(occupation, "shift_end", None) if occupation else None
        if shift_start is not None and shift_end is not None:
            shift_text = _dialogue_hours_text((shift_start, shift_end))
        social_leads = self._social_leads(
            npc_eid,
            workplace_prop=workplace_prop,
            home_prop=home_prop,
            current_prop=current_prop,
            limit=3,
        )
        primary_social_lead = social_leads[0] if social_leads else None
        other_name = ""
        other_relation = ""
        if primary_social_lead:
            other_name = str(primary_social_lead.get("name", "")).strip()
            other_relation = str(primary_social_lead.get("relation_text", "")).strip() or "contact"
        intro_source_name = ""
        if intro_entry:
            intro_source_name = _entity_display_name(self.sim, intro_entry.get("source_eid"), title_case=True)
        player_profile = self._player_profile()
        rumor_line = self._memory_line(memory, player_profile)
        objective_eval = evaluate_run_objective(self.sim, self.player_eid)
        objective_title = str((objective_eval or {}).get("title", "")).strip()
        objective_next_step = str((objective_eval or {}).get("next_step", "")).strip()
        objective_summary_line = str((objective_eval or {}).get("summary_line", "")).strip()
        objective_why_lines = tuple(str(line).strip() for line in list((objective_eval or {}).get("why_lines", ()) or ()) if str(line).strip())
        objective_how_lines = tuple(str(line).strip() for line in list((objective_eval or {}).get("how_lines", ()) or ()) if str(line).strip())
        objective_activity_lines = tuple(str(line).strip() for line in list((objective_eval or {}).get("activity_lines", ()) or ()) if str(line).strip())
        objective_focus = ()
        if objective_eval:
            from game.opportunities import objective_focus_facts

            focus_facts = objective_focus_facts(
                self.sim,
                self.player_eid,
                (objective_eval or {}).get("id", ""),
                limit=3,
            )
            focus_lines = []
            for row in focus_facts:
                if not isinstance(row, dict):
                    continue
                if not self._dialogue_allows_opportunity_entry(row):
                    continue
                title = str(row.get("title", "Opportunity")).strip() or "Opportunity"
                reason = str(row.get("reason", "")).strip()
                distance = int(row.get("distance", 0) or 0)
                direction = str(row.get("direction", "HERE")).strip()
                distance_phrase = self._humanize_distance_with_direction(
                    distance,
                    direction,
                    {
                        "district_type": district_type,
                        "role_id": role_id,
                    },
                )
                if reason:
                    focus_lines.append(f"{title} {distance_phrase}: {reason}.")
                else:
                    focus_lines.append(f"{title} {distance_phrase}.")
            objective_focus = tuple(line for line in focus_lines if line)
        final_operation_eval = evaluate_final_operation(self.sim, self.player_eid)
        opportunity_rows = self._dialogue_opportunity_rows(limit=3, observer_eid=npc_eid)
        fallout_rows = self._dialogue_fallout_rows(limit=6, observer_eid=npc_eid)

        # Dialogue should use structured opportunity facts rather than the
        # board-style text output. Keep the board evaluation around for
        # debug/UI purposes, but synthesize a human-friendly summary for
        # conversational use.
        base_context = {
            "npc_eid": npc_eid,
            "role_id": role_id,
            "career_text": career_text,
            "district_type": district_type,
            "objective_focus_lines": objective_focus,
            "opportunity_rows": opportunity_rows,
            "fallout_rows": fallout_rows,
        }
        opportunity_summary = self._opportunity_summary(base_context)
        opportunity_detail = self._opportunity_detail(base_context)

        # Evaluate NPC-level judgments for each opportunity row.
        opportunity_judgments = []
        if opportunity_rows:
            for row in opportunity_rows:
                judgment = evaluate_opportunity_judgment(
                    self.sim,
                    npc_eid,
                    row,
                    pressure_tier=pressure_tier,
                    rapport=rapport,
                    tone=tone,
                )
                opportunity_judgments.append(judgment)
        primary_opportunity_judgment = opportunity_judgments[0] if opportunity_judgments else {}

        local_source = ""
        detail_line = ""
        detail_label = "Tell me more."
        scene_local_line = str((scene_note or {}).get("local_line", "") or "").strip() if isinstance(scene_note, dict) else ""
        scene_detail_line = str((scene_note or {}).get("detail_line", "") or "").strip() if isinstance(scene_note, dict) else ""
        if scene_local_line or scene_detail_line:
            local_source = "scene_event"
            detail_line = scene_detail_line or scene_local_line
            detail_label = "What happens next?"
        elif rumor_line:
            local_source = "rumor"
            detail_line = rumor_line
        elif opportunity_summary:
            local_source = "opportunity"
            detail_line = opportunity_detail or opportunity_summary
            detail_label = "Any specifics on that?"
        elif other_name:
            local_source = "other"
            detail_line = f"Try {other_name}. They hear more than I do."
        trade_context = self._trade_context(npc_eid, workplace_prop, current_prop)
        contractor = self._active_backup_contract(npc_eid)
        peaceful_contract = self._active_peaceful_surrender(npc_eid) if peaceful_orders_only else None
        order_rec = contractor or peaceful_contract
        contractor_status = self._contractor_order_status(order_rec) if order_rec else ""
        backup_cursor = self._dialogue_backup_cursor_data(npc_eid) if (contractor or peaceful_orders_only) else {}
        kill_terms = self._contractor_kill_terms(npc_eid, bond=bond) if contractor else {
            "trusted": False,
            "surcharge": int(self.CONTRACTOR_KILL_SURCHARGE),
            "can_pay": False,
            "credits": 0,
        }
        backup_kill_target_eid = backup_cursor.get("target_eid")
        backup_kill_target_name = str(backup_cursor.get("target_name", "")).strip()
        contract_kill_offer = self._contract_kill_for_npc(npc_eid)
        workplace_here = bool(workplace_prop and current_prop and workplace_prop["id"] == current_prop["id"])
        subtitle_bits = []
        if career_text:
            subtitle_bits.append(career_text)
        elif role_text:
            subtitle_bits.append(role_text)
        subtitle_bits.append(state_text)
        if contractor_status and contractor_status not in {"passive cover", "waiting on you"}:
            subtitle_bits.append(contractor_status)
        elif peaceful_orders_only:
            subtitle_bits.append("hands up")
        subtitle_bits.append(tone)
        if pressure_tier in {"medium", "high"}:
            subtitle_bits.append(f"heat {pressure_tier}")
        subtitle_bits.append(f"{area_type}/{district_type}")
        if owner_place_name:
            subtitle_bits.append(owner_place_name)
        organization_name_text = str(organization.get("organization_name", "")).strip()
        if organization_name_text and organization_name_text.lower() != owner_place_name.lower():
            subtitle_bits.append(organization_name_text)
        human = identity is None or str(identity.taxonomy_class or "hominid").strip().lower() == "hominid"
        speech_style = _dialogue_speaker_style(
            self.sim.seed,
            npc_eid,
            area_type=area_type,
            district_type=district_type,
            role_id=role_id,
            tone=tone,
            empathy=getattr(npc_traits, "empathy", 0.5) if npc_traits else 0.5,
            discipline=getattr(npc_traits, "discipline", 0.5) if npc_traits else 0.5,
        )
        context = {
            "npc_eid": npc_eid,
            "npc_name": display_name,
            "human": human,
            "identity": identity,
            "ai": ai,
            "occupation": occupation,
            "routine": routine,
            "npc_needs": npc_needs,
            "npc_traits": npc_traits,
            "suppression": suppression,
            "memory": memory,
            "player_profile": player_profile,
            "guarded": guarded,
            "peaceful_orders_only": peaceful_orders_only,
            "recent_offense": recent_offense,
            "trespass_prop": trespass_prop,
            "bond": bond,
            "tone": tone,
            "rapport": rapport,
            "lead_confidence": lead_confidence,
            "career_text": career_text,
            "role_id": role_id,
            "role_text": role_text,
            "state_text": state_text,
            "subtitle": " | ".join(bit for bit in subtitle_bits if bit),
            "area_type": area_type,
            "district_type": district_type,
            "speech_style": speech_style,
            "pressure_attention": int(pressure.get("attention", 0)),
            "pressure_tier": pressure_tier,
            "pressure_goodwill_mult": float(pressure_effects.get("goodwill_mult", 1.0)),
            "pressure_suspicion_mult": float(pressure_effects.get("suspicion_mult", 1.0)),
            "payoff_available": (
                pressure_tier in {"medium", "high"}
                and not guarded
                and self.sim.ecs.get(PlayerAssets).get(self.player_eid) is not None
                and self.sim.tick >= self.payoff_cooldown_ticks.get(npc_eid, 0)
            ),
            "payoff_cost_amount": max(self.PAYOFF_BASE_COST, int(pressure.get("attention", 0)) * 2),
            "payoff_cost": f"{max(self.PAYOFF_BASE_COST, int(pressure.get('attention', 0)) * 2)} credits",
            "fence_available": self._fence_available_for(npc_eid, contact_standing, guarded),
            "fence_payout_preview": self._fence_payout_preview(self.player_eid),
            "hire_runner_available": self._hire_runner_available_for(npc_eid, contact_standing, guarded),
            "hire_runner_cost": self.CONTRACTOR_COST,
            "hire_runner_hours": f"{max(1, self.CONTRACTOR_DURATION // 60)} hours",
            "contact_standing": contact_standing,
            "intro_standing": intro_standing,
            "social_standing": social_standing,
            "door_answering": door_answering,
            "door_answer_mood": door_answer_mood,
            "door_answer_role": str(getattr(door_wait_state, "answer_role", "") or "").strip().lower() if door_answering else "",
            "door_answer_hours": bool(getattr(door_wait_state, "allow_hours", False)) if door_answering else False,
            "door_answer_services": bool(getattr(door_wait_state, "allow_services", False)) if door_answering else False,
            "home_prop": home_prop,
            "workplace_prop": workplace_prop,
            "owned_prop": owned_prop,
            "current_prop": current_prop,
            "owner_place": owner_place,
            "owner_place_name": owner_place_name,
            "referenced_place_prop": referenced_place_prop,
            "referenced_place_name": referenced_place_name,
            "referenced_place_lead_kind": str(dialogue_memory.get("last_property_lead_kind", "") or "").strip().lower(),
            "organization_eid": organization.get("organization_eid"),
            "organization_name": organization_name_text,
            "organization_kind": str(organization.get("organization_kind", "")).strip().lower(),
            "organization_role": str(organization.get("organization_role", "")).strip().lower(),
            "supervisor_name": str(organization.get("supervisor_name", "")).strip(),
            "supervisor_role": str(organization.get("supervisor_role", "")).strip().lower(),
            "coworker_names": tuple(organization.get("coworker_names", ()) or ()),
            "coworker_count": int(organization.get("coworker_count", 0) or 0),
            "organization_member_count": int(organization.get("member_count", 0) or 0),
            "home_name": str(home_prop.get("name", home_prop.get("id", "home"))).strip() if home_prop else "",
            "workplace_name": str(workplace_prop.get("name", workplace_prop.get("id", "place"))).strip() if workplace_prop else "",
            "workplace_here": workplace_here,
            "owner_name": owner_name,
            "owner_source": owner_source,
            "service_summary": service_summary,
            "service_summary_cap": service_summary[:1].upper() + service_summary[1:] if service_summary else "",
            "scene_note": dict(scene_note) if isinstance(scene_note, dict) else {},
            "scene_local_line": scene_local_line,
            "scene_detail_line": scene_detail_line,
            "scene_followup_opportunity": dict((scene_note or {}).get("followup_opportunity", {}) or {}) if isinstance(scene_note, dict) else {},
            "scene_followup_seed_id": str((scene_note or {}).get("followup_seed_id", "") or "").strip() if isinstance(scene_note, dict) else "",
            "scene_followup_property_id": str((scene_note or {}).get("followup_property_id", "") or "").strip() if isinstance(scene_note, dict) else "",
            "scene_followup_lead_kind": str((scene_note or {}).get("followup_lead_kind", "") or "").strip().lower() if isinstance(scene_note, dict) else "",
            "scene_carried_item_ids": tuple((scene_note or {}).get("carried_item_ids", ()) or ()) if isinstance(scene_note, dict) else (),
            "controller": controller,
            "access_level": access_level,
            "hours_text": hours_text,
            "shift_text": shift_text,
            "social_leads": social_leads,
            "social_lead_name": (
                str(primary_social_lead.get("name", "")).strip()
                if primary_social_lead and self._player_knows_person_name(primary_social_lead.get("eid"))
                else ""
            ),
            "social_lead_relation": str(primary_social_lead.get("relation_text", "")).strip() if primary_social_lead else "",
            "intro_entry": intro_entry,
            "intro_source_name": intro_source_name,
            "other_name": other_name,
            "other_relation": other_relation,
            "rumor_line": rumor_line,
            "objective_id": str((objective_eval or {}).get("id", "")).strip().lower(),
            "objective_title": objective_title,
            "objective_next_step": objective_next_step,
            "objective_summary_line": objective_summary_line,
            "objective_why_lines": objective_why_lines,
            "objective_how_lines": objective_how_lines,
            "objective_activity_lines": objective_activity_lines,
            "objective_focus_lines": objective_focus,
            "final_operation_summary_line": str((final_operation_eval or {}).get("summary_line", "")).strip(),
            "final_operation_next_step": str((final_operation_eval or {}).get("next_step", "")).strip(),
            "final_operation_target_property_id": str((final_operation_eval or {}).get("target_property_id", "")).strip(),
            "final_operation_target_property_name": str((final_operation_eval or {}).get("target_property_name", "")).strip(),
            "final_operation_target_reason": str((final_operation_eval or {}).get("target_reason", "")).strip(),
            "final_operation_target_quality_label": str((final_operation_eval or {}).get("target_quality_label", "")).strip(),
            "final_operation_target_entry_label": str((final_operation_eval or {}).get("target_entry_label", "")).strip(),
            "final_operation_target_entry_detail": str((final_operation_eval or {}).get("target_entry_detail", "")).strip(),
            "opportunity_rows": opportunity_rows,
            "fallout_rows": fallout_rows,
            "fallout_count": len(fallout_rows),
            "fallout_rep": fallout_rep,
            "fallout_available": bool(
                fallout_rows
                and not guarded
                and float(fallout_rep or 0.0) >= self.FALLOUT_MIN_STANDING
            ),
            "opportunity_judgments": tuple(opportunity_judgments),
            "primary_opportunity_judgment": primary_opportunity_judgment,
            "primary_opportunity_title": str(opportunity_rows[0].get("title", "")).strip() if opportunity_rows else "",
            "primary_opportunity_id": int(opportunity_rows[0].get("id", 0)) if opportunity_rows else 0,
            "opportunity_summary": opportunity_summary,
            "opportunity_detail": opportunity_detail,
            "local_source": local_source,
            "detail_line": detail_line,
            "detail_label": detail_label,
            "has_local_detail": bool(detail_line),
            "trade_available": bool(trade_context),
            "trade_context": trade_context,
            "vouch_place": workplace_prop or owned_prop,
            "backup_orders_available": bool(contractor or peaceful_orders_only),
            "backup_status_hint": contractor_status,
            "backup_cursor_hint": str(backup_cursor.get("label", "")).strip(),
            "backup_cursor_x": backup_cursor.get("x"),
            "backup_cursor_y": backup_cursor.get("y"),
            "backup_cursor_z": backup_cursor.get("z"),
            "backup_cursor_ready": bool(backup_cursor),
            "backup_kill_target_eid": backup_kill_target_eid,
            "backup_kill_target_name": backup_kill_target_name,
            "backup_kill_cost_hint": "trusted" if kill_terms.get("trusted") else (
                f"{int(kill_terms.get('surcharge', 0))} credits" if contractor and backup_kill_target_eid is not None else ""
            ),
            "backup_kill_surcharge": int(kill_terms.get("surcharge", 0)),
            "backup_kill_trusted": bool(kill_terms.get("trusted")),
            "backup_kill_available": bool(
                contractor
                and not peaceful_orders_only
                and backup_kill_target_eid is not None
                and (bool(kill_terms.get("trusted")) or bool(kill_terms.get("can_pay")))
            ),
            "contract_kill_offer": contract_kill_offer,
            "contract_target_role": str(
                (contract_kill_offer or {}).get("requirements", {}).get("kill_target_role", "")
            ).strip(),
        }
        context = self._apply_rival_dialogue_context(context)
        context["side_job_offer"] = self._side_job_for_npc(npc_eid)
        context["side_job_available"] = bool(context["side_job_offer"] or self._build_side_job_offer(context))
        context["pressure_role"] = self._dialogue_pressure_role(context)
        context["dialogue_prep_terms"] = _dialogue_prep_skill_terms(self.sim, self.player_eid)
        staffing = self._player_business_staffing_options(context)
        hire_option = staffing.get("hire") if isinstance(staffing, dict) else None
        fire_option = staffing.get("fire") if isinstance(staffing, dict) else None
        context.update({
            "player_business_hire_option": hire_option,
            "player_business_fire_option": fire_option,
            "player_business_hire_name": str((hire_option or {}).get("business_name", "")).strip(),
            "player_business_hire_role": str((hire_option or {}).get("role", "")).strip().lower(),
            "player_business_fire_name": str((fire_option or {}).get("business_name", "")).strip(),
            "player_business_fire_role": str((fire_option or {}).get("role", "")).strip().lower(),
        })
        hire_manager_option = self._player_business_hire_option_for_role(context, "manager")
        hire_staff_option = self._player_business_hire_option_for_role(context, "staff")
        hire_preview = self._player_business_hire_preview(npc_eid, hire_option)
        hire_manager_preview = self._player_business_hire_preview(npc_eid, hire_manager_option)
        hire_staff_preview = self._player_business_hire_preview(npc_eid, hire_staff_option)
        hire_roles = tuple(
            str(role).strip().lower()
            for role in tuple((hire_option or {}).get("roles", ()) or ())
            if str(role).strip()
        )
        hire_fit_hint = str((hire_preview or {}).get("topic_hint", "")).strip()
        if len(hire_roles) > 1:
            hint_bits = []
            if isinstance(hire_manager_preview, dict):
                hint_bits.append(f"mgr {str(hire_manager_preview.get('label', '')).strip().lower()}")
            if isinstance(hire_staff_preview, dict):
                hint_bits.append(f"staff {str(hire_staff_preview.get('label', '')).strip().lower()}")
            hire_fit_hint = " | ".join(bit for bit in hint_bits if bit)
        context.update({
            "player_business_hire_roles": hire_roles,
            "player_business_hire_manager_option": hire_manager_option,
            "player_business_hire_staff_option": hire_staff_option,
            "player_business_hire_preview": hire_preview,
            "player_business_hire_manager_preview": hire_manager_preview,
            "player_business_hire_staff_preview": hire_staff_preview,
            "player_business_hire_fit_hint": hire_fit_hint,
            "player_business_hire_manager_fit_hint": str((hire_manager_preview or {}).get("topic_hint", "")).strip(),
            "player_business_hire_staff_fit_hint": str((hire_staff_preview or {}).get("topic_hint", "")).strip(),
        })
        context["dialogue_shape"] = _build_dialogue_shape(self.sim, npc_eid, context=context)
        return context

    def _history_summary(self, context):
        if context.get("is_rival_operator"):
            hustle = str(context.get("rival_hustle", "")).strip().lower()
            reputation = str(context.get("rival_reputation", "")).strip().lower()
            if hustle == "intel":
                return "Long enough to know who lies badly and which doors they forget to respect."
            if hustle == "network":
                return "Long enough to know who talks when they need money and who talks when they panic."
            if hustle == "predator":
                return "Long enough to know every block eventually gives somebody up."
            if reputation == "professional":
                return "Long enough to know sloppy people keep funding careful ones."
            return "Long enough to know the city pays out in mistakes."
        scene_note = dict(context.get("scene_note", {}) or {})
        scene_type = str(scene_note.get("scene_type", "")).strip().lower()
        event_phase = str(scene_note.get("event_phase", "")).strip().lower()
        site_affiliated = bool(scene_note.get("site_affiliated"))
        career = str(scene_note.get("career", "")).strip().lower()
        if scene_type == "delivery" and (career == "courier" or not site_affiliated):
            if event_phase == "doorstep_drop":
                return "Not long. I am only here long enough to finish this doorstep drop."
            return "Not long. I am only here for this drop before I move on."
        if event_phase == "maintenance_loop" and not site_affiliated:
            return "Not long. I am just here for a service call before I move on."
        owner_place_name = str(context.get("owner_place_name", "")).strip()
        workplace_name = str(context.get("workplace_name", "")).strip()
        home_name = str(context.get("home_name", "")).strip()
        other_name = str(context.get("other_name", "")).strip()
        if context.get("guarded") and owner_place_name:
            return f"I have been around {owner_place_name} long enough to know who belongs near it."
        if workplace_name and home_name and workplace_name.lower() != home_name.lower():
            return f"Long enough that {workplace_name} is work and {home_name} is home."
        if home_name:
            return f"Long enough that {home_name} feels like home."
        if workplace_name:
            return f"Long enough that {workplace_name} stopped feeling new."
        if owner_place_name:
            return f"Long enough to know the rhythm around {owner_place_name}."
        if other_name:
            return f"Long enough to know {other_name} and a few other faces."
        return "Long enough to recognize the regulars."

    def _routine_summary(self, context, *, quality=None):
        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, "routine")
        quality_mode = str(quality.get("mode", "clear")).strip().lower() or "clear"
        if context.get("is_rival_operator"):
            hustle = str(context.get("rival_hustle", "")).strip().lower()
            target_title = str(context.get("primary_opportunity_title", "")).strip()
            if target_title:
                if hustle == "intel":
                    return f"I keep circling until {target_title} starts giving something away."
                if hustle == "network":
                    return f"I talk, drift, and wait for {target_title} to loosen up."
                if hustle == "predator":
                    return f"I keep moving until {target_title} stops looking ready for trouble and starts looking ready for me."
                return f"I stay light on my feet until {target_title} is ready to pay."
            if hustle == "intel":
                return "I move block to block, case something promising, then disappear before it gets noisy."
            if hustle == "network":
                return "I drift, listen, and lean on the right line until something opens."
            if hustle == "predator":
                return "I move until someone else gets careless first."
            return "I keep moving until a lead turns into money."
        owner_place_name = str(context.get("owner_place_name", "")).strip()
        workplace_name = str(context.get("workplace_name", "")).strip()
        home_name = str(context.get("home_name", "")).strip()
        shift_text = str(context.get("shift_text", "")).strip()
        state_text = str(context.get("state_text", "")).strip().lower()
        if context.get("guarded") and owner_place_name:
            return f"I keep an eye on {owner_place_name} and on who drifts through it."
        if quality_mode == "vague":
            if workplace_name and home_name and workplace_name.lower() != home_name.lower():
                return f"I drift between {workplace_name} and {home_name} depending on who is moving."
            if workplace_name:
                return f"I show around {workplace_name} when the place is moving."
            if home_name:
                return f"I stay around {home_name} until something pulls me out."
            if state_text:
                return f"I have been keeping {state_text} and mobile."
            return ""
        if quality_mode == "guarded":
            if workplace_name and home_name and workplace_name.lower() != home_name.lower():
                return f"I am usually around {workplace_name} while the shift is moving, then back to {home_name} after."
            if workplace_name and shift_text:
                return f"I am usually around {workplace_name} while staff are on."
            if workplace_name:
                return f"I drift through {workplace_name} when the day needs me."
            if home_name:
                return f"I mostly stay around {home_name} unless work pulls me out."
            if state_text:
                return f"Lately I have been {state_text} and staying flexible."
            return ""
        if workplace_name and shift_text and home_name and workplace_name.lower() != home_name.lower():
            return f"I am usually at {workplace_name} {shift_text}, then back to {home_name} when I am off."
        if workplace_name and shift_text:
            return f"I am usually at {workplace_name} {shift_text}."
        if workplace_name:
            return f"I drift in and out of {workplace_name} depending on the day."
        if home_name:
            return f"I mostly stay around {home_name} unless something pulls me elsewhere."
        if state_text:
            return f"Lately I have been {state_text} and seeing where that leads."
        return ""

    def _organization_summary(self, context):
        if context.get("is_rival_operator"):
            reputation = str(context.get("rival_reputation", "")).strip().lower()
            if reputation == "professional":
                return "Nobody signs my checks. That is the point."
            return "Mostly myself. Everybody else only matters when a job does."
        organization_name_text = str(context.get("organization_name", "")).strip()
        organization_kind = str(context.get("organization_kind", "")).strip().lower()
        organization_role = str(context.get("organization_role", "")).strip().lower()
        career_text = str(context.get("career_text", "")).strip()
        workplace_name = str(context.get("workplace_name", "")).strip()
        owner_name = str(context.get("owner_name", "")).strip()
        owner_source = str(context.get("owner_source", "")).strip().lower()
        scene_note = dict(context.get("scene_note", {}) or {})
        scene_type = str(scene_note.get("scene_type", "")).strip().lower()
        event_phase = str(scene_note.get("event_phase", "")).strip().lower()
        site_affiliated = bool(scene_note.get("site_affiliated"))

        if scene_type == "delivery" and not site_affiliated:
            return "Nobody at this stop signs me. I am with the delivery side, then I move on."
        if event_phase == "maintenance_loop" and not site_affiliated:
            return "Nobody here signs me. I am on the maintenance side for this call and then I am gone."
        if organization_role == "owner" and workplace_name and organization_name_text and organization_name_text.lower() != workplace_name.lower():
            return f"Nobody over me. {workplace_name} runs under {organization_name_text}, and it is mine."
        if organization_role == "owner" and workplace_name:
            return f"Nobody over me. {workplace_name} is mine."
        if organization_role == "owner":
            return "Nobody over me. I work for myself."
        if organization_name_text:
            if workplace_name and organization_name_text.lower() != workplace_name.lower():
                if career_text:
                    if organization_kind == "civic":
                        return f"{workplace_name} runs under {organization_name_text}. I do {career_text} work on the public side."
                    if organization_kind == "institution":
                        return f"{workplace_name} runs under {organization_name_text}. I do {career_text} work under their chain."
                    return f"{workplace_name} runs under {organization_name_text}. I do {career_text} work for them."
                if organization_role == "manager":
                    return f"{workplace_name} runs under {organization_name_text}. I manage it for them."
                if organization_kind == "civic":
                    return f"{workplace_name} sits on the {organization_name_text} side."
                if organization_kind == "institution":
                    return f"{workplace_name} answers up to {organization_name_text}."
                return f"{workplace_name} runs under {organization_name_text}."
            if workplace_name and career_text:
                if organization_kind == "civic":
                    return f"{organization_name_text} runs the place. I do {career_text} work on the public side."
                if organization_kind == "institution":
                    return f"{organization_name_text} runs the place. I do {career_text} work under their chain."
                return f"{organization_name_text} runs the place. I do {career_text} work for them."
            if workplace_name and organization_role == "manager":
                return f"{organization_name_text} runs the place. I manage it for them."
            if career_text:
                if organization_kind == "civic":
                    return f"{organization_name_text}. I do {career_text} work on the public side."
                if organization_kind == "institution":
                    return f"{organization_name_text}. I do {career_text} work under their chain."
                return f"{organization_name_text}. I do {career_text} work for them."
            if organization_role == "manager":
                return f"{organization_name_text}. I manage the place for them."
            if organization_kind == "civic":
                return f"It is {organization_name_text}. Public side of things."
            if organization_kind == "institution":
                return f"It is {organization_name_text}. More chain of command than charm."
            return f"{organization_name_text}. That is the outfit I am with."
        if owner_name and workplace_name:
            if owner_source == "owner":
                if career_text:
                    return f"{owner_name} owns {workplace_name}. I do {career_text} work for them."
                return f"{owner_name} owns {workplace_name}."
            if owner_source == "founder":
                if career_text:
                    return f"{owner_name} founded {workplace_name}. I do {career_text} work here."
                return f"{owner_name} founded {workplace_name}."
            if owner_source == "tag":
                if career_text:
                    return f"{owner_name.title()} side, mostly. I do {career_text} work here."
                return f"{owner_name.title()} side, mostly."
        if workplace_name and career_text:
            return f"No bigger outfit than {workplace_name} that I know. I do {career_text} work here."
        if workplace_name:
            return f"No bigger outfit than {workplace_name} that I know."
        return ""

    def _supervisor_summary(self, context):
        organization_role = str(context.get("organization_role", "")).strip().lower()
        supervisor_name = str(context.get("supervisor_name", "")).strip()
        supervisor_role = str(context.get("supervisor_role", "")).strip().lower()
        workplace_name = str(context.get("workplace_name", "")).strip()
        organization_name_text = str(context.get("organization_name", "")).strip()
        organization_kind = str(context.get("organization_kind", "")).strip().lower()

        if organization_role == "owner":
            if workplace_name:
                return f"Nobody above me at {workplace_name}. It is my call."
            return "Nobody above me. It is my call."
        if supervisor_name:
            if supervisor_role == "owner":
                if workplace_name:
                    return f"{supervisor_name} owns {workplace_name}. Big calls go through them."
                return f"{supervisor_name} owns the place."
            if supervisor_role == "manager":
                if workplace_name:
                    return f"{supervisor_name} runs the floor at {workplace_name} most days."
                return f"{supervisor_name} runs the floor most days."
            return f"I answer to {supervisor_name}."
        if organization_role == "manager":
            if workplace_name:
                return f"Nobody local above me at {workplace_name}. Floor calls land on me."
            return "Nobody local above me. Floor calls land on me."
        if organization_kind == "civic":
            return "Depends which supervisor drew the shift."
        if organization_name_text:
            return f"{organization_name_text} keeps a chain over the place, even if it changes faces."
        return ""

    def _coworker_summary(self, context):
        workplace_name = str(context.get("workplace_name", "")).strip()
        supervisor_name = str(context.get("supervisor_name", "")).strip()
        organization_role = str(context.get("organization_role", "")).strip().lower()
        coworker_names = list(context.get("coworker_names", ()) or ())
        organization_member_count = max(0, int(context.get("organization_member_count", 0) or 0))

        if coworker_names:
            shown_names = coworker_names[:2]
            extra = max(0, len(coworker_names) - len(shown_names))
            names_text = _dialogue_human_join(shown_names)
            if extra > 0:
                if workplace_name:
                    return f"You will usually see {names_text}, plus {extra} more around {workplace_name}."
                return f"Usually {names_text}, plus {extra} more."
            if workplace_name:
                return f"You will usually see {names_text} around {workplace_name}."
            return f"Usually {names_text}."
        if organization_member_count <= 1:
            if workplace_name:
                return f"No regular crew at {workplace_name}. Usually just me."
            return "No regular crew. Usually just me."
        if supervisor_name and workplace_name and organization_role not in {"owner", "manager"} and organization_member_count <= 2:
            return f"Usually just {supervisor_name} and me around {workplace_name}."
        if organization_role == "owner":
            if workplace_name:
                return f"No steady crew at {workplace_name}. I mostly keep it moving myself."
            return "No steady crew. I mostly keep it moving myself."
        if organization_role == "manager":
            if workplace_name:
                return f"The roster shifts around at {workplace_name}, but I am usually the one holding it together."
            return "The roster shifts around, but I am usually the one holding it together."
        if workplace_name:
            return f"Small crew at {workplace_name}. Depends who is on."
        return ""

    def _where_place_summary(self, context):
        prop = context.get("referenced_place_prop")
        if not isinstance(prop, dict):
            return ""
        place_name = str(context.get("referenced_place_name", "") or prop.get("name", prop.get("id", "that place"))).strip() or "that place"
        current_prop = context.get("current_prop")
        if isinstance(current_prop, dict) and str(current_prop.get("id", "")).strip() == str(prop.get("id", "")).strip():
            return f"Right here. {place_name} is the place you're standing in."

        focus = _property_focus_position(prop) or _property_display_position(prop)
        if focus is None:
            return f"{place_name} is on my mind, but I cannot place it cleanly from here."

        player_pos = self.sim.ecs.get(Position).get(self.player_eid)
        if player_pos is None:
            return f"{place_name} is around {int(focus[0])},{int(focus[1])}."

        origin_chunk = self.sim.chunk_coords(int(player_pos.x), int(player_pos.y))
        target_chunk = self.sim.chunk_coords(int(focus[0]), int(focus[1]))
        if tuple(origin_chunk) == tuple(target_chunk):
            return f"{place_name} is in this chunk."

        distance = _manhattan(int(origin_chunk[0]), int(origin_chunk[1]), int(target_chunk[0]), int(target_chunk[1]))
        direction = self._dialogue_chunk_direction(origin_chunk, target_chunk)
        distance_phrase = self._humanize_distance_with_direction(distance, direction, context)
        return f"{place_name} is {distance_phrase}."

    def _social_lead_sentence(self, lead):
        if not isinstance(lead, dict):
            return ""
        name = str(lead.get("name", "")).strip()
        if not name:
            return ""
        relation_text = str(lead.get("relation_text", "")).strip()
        career_text = str(lead.get("career_text", "")).strip()
        place_name = str(lead.get("place_name", "")).strip()
        place_role = str(lead.get("place_role", "")).strip().lower()

        if relation_text and career_text and place_name and place_role == "workplace":
            return f"{name} is my {relation_text} and does {career_text} work at {place_name}."
        if relation_text and place_name and place_role == "home":
            return f"{name} is my {relation_text} from around {place_name}."
        if relation_text and place_name and place_role == "workplace":
            return f"{name} is my {relation_text} over at {place_name}."
        if relation_text and career_text:
            return f"{name} is my {relation_text}, and they do {career_text} work."
        if career_text and place_name and place_role == "workplace":
            return f"{name} does {career_text} work at {place_name}."
        if relation_text:
            return f"{name} is my {relation_text}."
        if place_name:
            return f"{name} is usually around {place_name}."
        return f"{name} is worth knowing."

    def _people_summary(self, context):
        leads = list(context.get("social_leads", ()) or ())
        if not leads:
            return ""
        shown = leads[:2]
        sentences = [self._social_lead_sentence(lead) for lead in shown]
        sentences = [sentence for sentence in sentences if sentence]
        if not sentences:
            return ""
        extra = max(0, len(leads) - len(shown))
        if extra > 0:
            sentences.append(f"There are {extra} more names behind them, but those are the ones I would start with.")
        return " ".join(sentences)

    def _introduction_target(self, context):
        leads = list(context.get("social_leads", ()) or ())
        if not leads:
            return None
        standing = self._contact_standing(context.get("bond"), context.get("rapport", 0.0))
        for lead in leads:
            if float(lead.get("score", 0.0)) < 0.44 and standing < 0.62:
                continue
            return lead
        return leads[0]

    def _cycled_dialogue_line(self, lines, ask_count):
        cleaned = [str(line).strip() for line in tuple(lines or ()) if str(line).strip()]
        if not cleaned:
            return ""
        index = max(0, int(ask_count) - 1) % len(cleaned)
        return cleaned[index]

    def _npc_direction_knowledge(self, context):
        """Estimate how confidently an NPC can give cardinal directions."""
        context = context or {}
        npc_eid = context.get("npc_eid")
        try:
            streetwise = float(_actor_skill(self.sim, npc_eid, "streetwise", default=5.0))
            perception = float(_actor_skill(self.sim, npc_eid, "perception", default=5.0))
        except (TypeError, ValueError):
            streetwise = 5.0
            perception = 5.0
        knowledge_score = (streetwise * 0.6) + (perception * 0.4)

        # Deterministic local familiarity variation so not all average NPCs
        # describe directions with the same confidence.
        district_type = str(context.get("district_type", "")).strip().lower()
        role_id = str(context.get("role_id", "")).strip().lower()
        career_text = str(context.get("career_text", "")).strip().lower()
        seed = f"{getattr(self.sim, 'seed', 0)}:direction-knowledge:{npc_eid}:{district_type}:{role_id}"
        variation = random.Random(seed).uniform(-1.1, 1.1)
        knowledge_score += variation

        if role_id in {"guard", "scout"}:
            knowledge_score += 0.6
        if any(token in career_text for token in ("guard", "scout", "courier", "driver", "patrol", "security", "ranger")):
            knowledge_score += 0.45

        if knowledge_score >= 6.8:
            return "precise"
        if knowledge_score >= 5.2:
            return "approx"
        return "vague"

    def _humanize_distance_with_direction(self, distance, direction, context=None):
        """Convert distance (chunks) and direction into natural dialogue.

        Scale assumption: 1 chunk ~= 200m (20 tiles at roughly 10m/tile).
        Close ranges are more precise; far ranges naturally sound less certain.
        NPC directional confidence varies by their own skills.
        """
        direction = str(direction or "HERE").strip().upper()
        distance = int(distance or 0)

        if distance == 0:
            return "right here"

        # Map cardinal directions to spoken forms for narrative feel.
        dir_map = {
            "N": "north", "S": "south", "E": "east", "W": "west",
            "NE": "the northeast", "NW": "the northwest",
            "SE": "the southeast", "SW": "the southwest",
            "HERE": "here",
        }
        spoken_dir = dir_map.get(direction, "")
        has_article = spoken_dir.startswith("the ")
        dir_to_phrase = f"to {spoken_dir}" if has_article else f"to the {spoken_dir}"

        direction_knowledge = self._npc_direction_knowledge(context)
        can_use_direction = bool(spoken_dir and direction != "HERE" and direction_knowledge != "vague")

        if distance == 1:
            if can_use_direction:
                return f"nearby {dir_to_phrase}"
            return "nearby"

        if distance <= 3:
            if can_use_direction:
                if direction_knowledge == "approx":
                    return f"across town, around {spoken_dir}"
                return f"across town {dir_to_phrase}"
            return "across town"

        if distance <= 6:
            if can_use_direction:
                return f"not far off, probably {spoken_dir}"
            return "not far off"

        # Far range (7+ chunks): kilometer-level phrasing with softer certainty.
        km = max(1.0, distance * 0.2)
        if km < 1.5:
            km_phrase = "a few kilometers"
        elif km < 2.0:
            km_phrase = "a couple kilometers"
        else:
            km_phrase = f"{int(round(km))} kilometers"

        if can_use_direction:
            if direction_knowledge == "approx":
                return f"{km_phrase} or so, somewhere {spoken_dir}"
            return f"{km_phrase} {spoken_dir}"
        return f"{km_phrase} out"

    def _opportunity_requirement_summary_fragment(self, row):
        requirements = dict(row.get("requirements", {}) or {}) if isinstance(row, dict) else {}
        item_label = str(requirements.get("item_label", "")).strip()
        acquisition_hint = str(requirements.get("acquisition_hint", "")).strip().lower()
        if not item_label:
            interact_name = str(requirements.get("interact_npc_name", "")).strip()
            interaction_requirement = str(requirements.get("interaction_requirement", "contact")).strip().lower() or "contact"
            if not interact_name:
                return ""
            if interaction_requirement == "pressure":
                return f"You need to lean on {interact_name} in person"
            return f"You need to reach {interact_name} in person"
        if acquisition_hint == "provided":
            return f"They should hand over the {item_label} at pickup"
        if acquisition_hint == "buy_or_find":
            return f"You still need to buy or find {item_label} first"
        if acquisition_hint == "pickup":
            return f"You have to make the pickup first, then haul the {item_label} back"
        return ""

    def _opportunity_anchor_property(self, row):
        if not isinstance(row, dict):
            return None
        requirements = dict(row.get("requirements", {}) or {})
        property_id = str(requirements.get("property_id", "")).strip()
        if not property_id:
            return None
        prop = self.sim.properties.get(property_id)
        return prop if isinstance(prop, dict) else None

    def _opportunity_anchor_name(self, row):
        prop = self._opportunity_anchor_property(row)
        if isinstance(prop, dict):
            return str(prop.get("name", prop.get("id", "site"))).strip() or "the site"
        requirements = dict(row.get("requirements", {}) or {}) if isinstance(row, dict) else {}
        return str(requirements.get("property_name", "")).strip()

    def _opportunity_anchor_clause(self, row, context, *, preposition="around"):
        place_name = self._opportunity_anchor_name(row)
        distance = int((row or {}).get("distance", 0) or 0) if isinstance(row, dict) else 0
        direction = str((row or {}).get("direction", "HERE")).strip() if isinstance(row, dict) else "HERE"
        distance_phrase = self._humanize_distance_with_direction(distance, direction, context)
        if place_name and distance_phrase and distance_phrase != "here":
            return f"{preposition} {place_name}, {distance_phrase}"
        if place_name:
            return f"{preposition} {place_name}"
        if distance_phrase and distance_phrase != "here":
            return distance_phrase
        return "nearby"

    def _opportunity_followthrough_fields(self, row):
        if not isinstance(row, dict):
            return "", "", "", ""
        place_name = str(row.get("anchor_site_name", "")).strip() or self._opportunity_anchor_name(row)
        organization_name = str(row.get("organization_name", "")).strip()
        contact_name = str(row.get("contact_name", "")).strip()
        contact_role = str(row.get("contact_role", "")).strip().replace("_", " ")
        return place_name, organization_name, contact_name, contact_role

    def _opportunity_followthrough_detail_tier(self, row, *, quality=None):
        if not isinstance(row, dict):
            return 0
        quality_mode = str((quality or {}).get("mode", "clear")).strip().lower() if isinstance(quality, dict) else "clear"
        if quality_mode != "clear":
            return 0
        awareness = str(row.get("awareness_state", "heard")).strip().lower() or "heard"
        source = str(row.get("source", "")).strip().lower()
        try:
            confidence = float(row.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0

        tier = 0
        if source == "business_scene":
            tier += 2
        elif source == "specialty_theme":
            tier += 1
        if awareness == "confirmed":
            tier += 1
        if confidence >= 0.86:
            tier += 2
        elif confidence >= 0.72:
            tier += 1
        return tier

    def _opportunity_followthrough_summary_tail(self, row, *, quality=None):
        place_name, organization_name, contact_name, contact_role = self._opportunity_followthrough_fields(row)
        tier = self._opportunity_followthrough_detail_tier(row, quality=quality)
        if tier <= 0:
            return ""
        place_lc = place_name.lower()
        org_lc = organization_name.lower()
        if organization_name and place_name and org_lc and org_lc != place_lc and tier >= 2:
            return f"{place_name} is running under {organization_name}."
        if contact_role and place_name and organization_name and org_lc and org_lc != place_lc and tier >= 4:
            return f"The {contact_role} at {place_name} answers to {organization_name}."
        if contact_role and place_name and tier >= 3:
            return f"The {contact_role} at {place_name} is the face that repeats."
        if contact_name and place_name and organization_name and org_lc and org_lc != place_lc and tier >= 5:
            return f"{contact_name} is the face there, working under {organization_name}."
        if contact_name and place_name and tier >= 4:
            return f"{contact_name} is the repeat face at {place_name}."
        return ""

    def _opportunity_followthrough_angle_tail(self, row, *, quality=None):
        place_name, organization_name, contact_name, contact_role = self._opportunity_followthrough_fields(row)
        tier = self._opportunity_followthrough_detail_tier(row, quality=quality)
        if tier <= 0:
            return ""
        place_lc = place_name.lower()
        org_lc = organization_name.lower()
        if contact_name and place_name and tier >= 4:
            return f"Start by reading {contact_name} at {place_name}; they set the rhythm."
        if contact_role and place_name and tier >= 2:
            return f"Start by reading the {contact_role} at {place_name}; they set the rhythm."
        if organization_name and place_name and org_lc and org_lc != place_lc and tier >= 3:
            return f"Read who is working that stop for {organization_name}, not just who drifts through it."
        return ""

    def _opportunity_followthrough_risk_tail(self, row, *, quality=None):
        place_name, organization_name, contact_name, contact_role = self._opportunity_followthrough_fields(row)
        tier = self._opportunity_followthrough_detail_tier(row, quality=quality)
        if tier <= 0:
            return ""
        place_lc = place_name.lower()
        org_lc = organization_name.lower()
        if contact_name and place_name and tier >= 4:
            return f"If {contact_name} remembers you for the wrong reason, the lane closes fast."
        if contact_role and place_name and tier >= 3:
            return f"If the {contact_role} at {place_name} clocks you wrong, the lane closes fast."
        if organization_name and place_name and org_lc and org_lc != place_lc and tier >= 2:
            return f"Once {organization_name} starts reading you as pressure instead of traffic, the room tightens."
        return ""

    def _specialty_opportunity_summary_line(self, row, context, *, quality=None, retrieval=False):
        if not isinstance(row, dict):
            return ""
        kind = str(row.get("kind", "")).strip().lower()
        if kind not in SPECIALTY_OPPORTUNITY_THEMES:
            return ""

        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, "opportunities")
        quality_mode = str(quality.get("mode", "clear")).strip().lower() or "clear"
        anchor = self._opportunity_anchor_clause(row, context, preposition="around")
        summary = str(row.get("summary", "")).strip()
        summary_tail = self._opportunity_followthrough_summary_tail(row, quality=quality)

        if kind == "layover_shuffle":
            if retrieval:
                if quality_mode == "guarded":
                    return f"For the retrieval, I would lean on the layover churn {anchor}, but only after you sort the real travelers from the handoff traffic."
                if quality_mode == "vague":
                    return f"For the retrieval, the layover churn {anchor} is worth a harder look."
                line = f"For the retrieval, the layover churn {anchor} is the strongest live lead. Traveler turnover there hides cover, favors, and the real handoff."
                return f"{line} {summary_tail}".strip() if summary_tail else line
            if quality_mode == "guarded":
                return f"The layover churn {anchor} is live, but faces turn over fast there, so verify it yourself."
            if quality_mode == "vague":
                return f"There is layover churn {anchor} if you want a route that keeps moving."
            line = f"Layover traffic {anchor} is still working. {summary}".strip()
            return f"{line} {summary_tail}".strip() if summary_tail else line

        if kind == "route_stash":
            if retrieval:
                if quality_mode == "guarded":
                    return f"For the retrieval, I would check the route stash {anchor}, but only if you can read who is servicing it and who is only passing through."
                if quality_mode == "vague":
                    return f"For the retrieval, the route stash {anchor} is worth a look."
                line = f"For the retrieval, the route stash {anchor} is the strongest live lead. Stash runners there tell you who keeps using the lane with purpose."
                return f"{line} {summary_tail}".strip() if summary_tail else line
            if quality_mode == "guarded":
                return f"The route stash {anchor} is still hot, but those little caches cool fast once the wrong face hangs around them."
            if quality_mode == "vague":
                return f"There is a route stash {anchor} if you want something small and fast-moving."
            line = f"The route stash {anchor} is still hot. {summary}".strip()
            return f"{line} {summary_tail}".strip() if summary_tail else line

        if kind == "yard_strip":
            if retrieval:
                if quality_mode == "guarded":
                    return f"For the retrieval, I would use the yard strip {anchor}, but only after you know which crew is working it and which crew is waiting to pounce."
                if quality_mode == "vague":
                    return f"For the retrieval, the yard strip {anchor} is worth a look."
                line = f"For the retrieval, the yard strip {anchor} is the strongest live lead. Salvage traffic there exposes who needs discreet parts, quick fixes, and quiet exits."
                return f"{line} {summary_tail}".strip() if summary_tail else line
            if quality_mode == "guarded":
                return f"The yard strip {anchor} is still open, but salvage lanes turn territorial fast if you show up late or loud."
            if quality_mode == "vague":
                return f"There is a yard strip {anchor} if you want a harder scrap lane."
            line = f"The yard strip {anchor} is still open. {summary}".strip()
            return f"{line} {summary_tail}".strip() if summary_tail else line

        if kind == "field_repair_call":
            if retrieval:
                if quality_mode == "guarded":
                    return f"For the retrieval, I would lean on the repair call {anchor}, but make sure the desperate customer is the one you are reading, not the crew circling them."
                if quality_mode == "vague":
                    return f"For the retrieval, the repair call {anchor} is worth a second look."
                line = f"For the retrieval, the repair call {anchor} is the strongest live lead. Quiet fixes there expose who needs a vehicle ready and who cannot afford public attention."
                return f"{line} {summary_tail}".strip() if summary_tail else line
            if quality_mode == "guarded":
                return f"The repair call {anchor} is moving, but once that fix turns noisy the whole lane knows about it."
            if quality_mode == "vague":
                return f"There is a quiet repair call {anchor} if you want a softer mechanical lane."
            line = f"The quiet repair call {anchor} is still moving. {summary}".strip()
            return f"{line} {summary_tail}".strip() if summary_tail else line

        if kind == "sightline_check":
            if retrieval:
                if quality_mode == "guarded":
                    return f"For the retrieval, I would use the sightline read {anchor}, but only if you can stay watcher instead of becoming the thing being watched."
                if quality_mode == "vague":
                    return f"For the retrieval, the sightline read {anchor} is worth your time."
                line = f"For the retrieval, the sightline read {anchor} is the strongest live lead. Long views there tell you who crosses the dead ground and who owns the route."
                return f"{line} {summary_tail}".strip() if summary_tail else line
            if quality_mode == "guarded":
                return f"The sightline read {anchor} still pays, but good sightlines work both ways."
            if quality_mode == "vague":
                return f"There is a sightline read {anchor} if you want a cleaner watch lane."
            line = f"The sightline read {anchor} is still paying. {summary}".strip()
            return f"{line} {summary_tail}".strip() if summary_tail else line

        if kind == "relay_watch":
            if retrieval:
                if quality_mode == "guarded":
                    return f"For the retrieval, I would lean on the relay watch {anchor}, but only after you know which repeat faces belong there and which ones mean trouble."
                if quality_mode == "vague":
                    return f"For the retrieval, the relay watch {anchor} is worth a closer look."
                line = f"For the retrieval, the relay watch {anchor} is the strongest live lead. Repeat traffic there tells you who keeps using the chain with intent."
                return f"{line} {summary_tail}".strip() if summary_tail else line
            if quality_mode == "guarded":
                return f"The relay watch {anchor} is still live, but quiet chains remember patterns fast."
            if quality_mode == "vague":
                return f"There is a relay watch {anchor} if you want a patient read."
            line = f"The relay watch {anchor} is still live. {summary}".strip()
            return f"{line} {summary_tail}".strip() if summary_tail else line

        if kind == "refuge_resupply":
            if retrieval:
                if quality_mode == "guarded":
                    return f"For the retrieval, I would use the refuge resupply {anchor}, but only if you can tell real need from somebody running a lure."
                if quality_mode == "vague":
                    return f"For the retrieval, the refuge resupply {anchor} might still open a quiet lane."
                line = f"For the retrieval, the refuge resupply {anchor} is the strongest live lead. Short shelter stops there tell you who keeps coming through with pressure on them."
                return f"{line} {summary_tail}".strip() if summary_tail else line
            if quality_mode == "guarded":
                return f"The refuge resupply {anchor} is still soft enough to work, but the room turns watchful the moment you read like pressure instead of help."
            if quality_mode == "vague":
                return f"There is a refuge resupply {anchor} if you want a quieter lane."
            line = f"The refuge resupply {anchor} is still soft enough to work. {summary}".strip()
            return f"{line} {summary_tail}".strip() if summary_tail else line

        if kind == "spring_run":
            if retrieval:
                if quality_mode == "guarded":
                    return f"For the retrieval, I would lean on the spring run {anchor}, but only if you can stay useful without becoming memorable."
                if quality_mode == "vague":
                    return f"For the retrieval, the spring run {anchor} could still open a quiet path."
                line = f"For the retrieval, the spring run {anchor} is the strongest live lead. Water legs there tell you who cannot miss the route and who keeps the refuge chain alive."
                return f"{line} {summary_tail}".strip() if summary_tail else line
            if quality_mode == "guarded":
                return f"The spring run {anchor} is still worth a walk, but once somebody misses water every stranger starts getting remembered."
            if quality_mode == "vague":
                return f"There is a spring run {anchor} if you want a quieter cover lane."
            line = f"The spring run {anchor} is still worth a walk. {summary}".strip()
            return f"{line} {summary_tail}".strip() if summary_tail else line

        return ""

    def _specialty_opportunity_angle_line(self, row, context, *, quality=None, retrieval=False):
        if not isinstance(row, dict):
            return ""
        kind = str(row.get("kind", "")).strip().lower()
        if kind not in SPECIALTY_OPPORTUNITY_THEMES:
            return ""

        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, "angle")
        quality_mode = str(quality.get("mode", "clear")).strip().lower() or "clear"
        anchor = self._opportunity_anchor_clause(row, context, preposition="around")
        angle_tail = self._opportunity_followthrough_angle_tail(row, quality=quality)

        if kind == "layover_shuffle":
            if retrieval:
                line = (
                    f"For the retrieval, start with the traveler turnover {anchor} and see who keeps treating the stop like a working handoff."
                    if quality_mode != "guarded"
                    else f"For the retrieval, start with the traveler turnover {anchor}, but make sure you sort the real regulars from the handoff traffic."
                )
                return f"{line} {angle_tail}".strip() if quality_mode == "clear" and angle_tail else line
            if quality_mode == "guarded":
                return f"Start with the layover churn {anchor}, then make sure you can pass for one more traveler before you lean harder."
            if quality_mode == "vague":
                return f"Start with the layover churn {anchor} before you touch anything fixed."
            line = f"Start with the layover churn {anchor}; if you look like one more traveler between legs, the real handoff has room to show itself."
            return f"{line} {angle_tail}".strip() if angle_tail else line

        if kind == "route_stash":
            if retrieval:
                line = (
                    f"For the retrieval, start with the route stash {anchor} and watch who services it like clockwork."
                    if quality_mode != "guarded"
                    else f"For the retrieval, start with the route stash {anchor}, but confirm who is servicing it and who is only drifting past."
                )
                return f"{line} {angle_tail}".strip() if quality_mode == "clear" and angle_tail else line
            if quality_mode == "guarded":
                return f"Start with the route stash {anchor}, then see who keeps servicing it before the lane turns over."
            if quality_mode == "vague":
                return f"Start with the route stash {anchor} before the next line clears it."
            line = f"Start with the route stash {anchor}; whoever keeps it fed is the one moving with purpose."
            return f"{line} {angle_tail}".strip() if angle_tail else line

        if kind == "yard_strip":
            if retrieval:
                line = (
                    f"For the retrieval, start with the yard strip {anchor} and log which crew is still working the hot edge."
                    if quality_mode != "guarded"
                    else f"For the retrieval, start with the yard strip {anchor}, but know whose scrap lane you are stepping into before you show your face."
                )
                return f"{line} {angle_tail}".strip() if quality_mode == "clear" and angle_tail else line
            if quality_mode == "guarded":
                return f"Start with the yard strip {anchor}, then work out which crew owns the lane before you move."
            if quality_mode == "vague":
                return f"Start with the yard strip {anchor} before the regular crews clean it out."
            line = f"Start with the yard strip {anchor}; the crew working the hot edge tells you who still needs the lane quiet."
            return f"{line} {angle_tail}".strip() if angle_tail else line

        if kind == "field_repair_call":
            if retrieval:
                line = (
                    f"For the retrieval, start with the repair call {anchor} and follow the person who cannot let the breakdown become public."
                    if quality_mode != "guarded"
                    else f"For the retrieval, start with the repair call {anchor}, but do not mistake the desperate customer for the whole crew behind them."
                )
                return f"{line} {angle_tail}".strip() if quality_mode == "clear" and angle_tail else line
            if quality_mode == "guarded":
                return f"Start with the repair call {anchor}, then make sure the desperate customer is the one you follow."
            if quality_mode == "vague":
                return f"Start with the repair call {anchor} before the fix gets folded back into normal traffic."
            line = f"Start with the repair call {anchor}; whoever cannot afford a public breakdown is the one who opens the lane."
            return f"{line} {angle_tail}".strip() if angle_tail else line

        if kind == "sightline_check":
            if retrieval:
                line = (
                    f"For the retrieval, start with the sightline read {anchor} and map who crosses the dead ground with confidence."
                    if quality_mode != "guarded"
                    else f"For the retrieval, start with the sightline read {anchor}, but keep moving before you become the thing in the glass."
                )
                return f"{line} {angle_tail}".strip() if quality_mode == "clear" and angle_tail else line
            if quality_mode == "guarded":
                return f"Start with the sightline read {anchor}, but keep it moving before the watch lane notices you back."
            if quality_mode == "vague":
                return f"Start with the sightline read {anchor} before you touch the block itself."
            line = f"Start with the sightline read {anchor}; map who owns the dead ground before you commit to a route."
            return f"{line} {angle_tail}".strip() if angle_tail else line

        if kind == "relay_watch":
            if retrieval:
                line = (
                    f"For the retrieval, start with the relay watch {anchor} and match the repeat faces that keep using the chain after dark."
                    if quality_mode != "guarded"
                    else f"For the retrieval, start with the relay watch {anchor}, but make sure the repeat face you choose is real and not the decoy everyone else already sees."
                )
                return f"{line} {angle_tail}".strip() if quality_mode == "clear" and angle_tail else line
            if quality_mode == "guarded":
                return f"Start with the relay watch {anchor}, then separate the real repeat faces from the noise."
            if quality_mode == "vague":
                return f"Start with the relay watch {anchor} after dark."
            line = f"Start with the relay watch {anchor}; the repeat face on that chain is the one worth following."
            return f"{line} {angle_tail}".strip() if angle_tail else line

        if kind == "refuge_resupply":
            if retrieval:
                line = (
                    f"For the retrieval, start with the refuge resupply {anchor} and see which stop is running short enough to talk."
                    if quality_mode != "guarded"
                    else f"For the retrieval, start with the refuge resupply {anchor}, but keep your help useful enough that nobody starts reading you as pressure."
                )
                return f"{line} {angle_tail}".strip() if quality_mode == "clear" and angle_tail else line
            if quality_mode == "guarded":
                return f"Start with the refuge resupply {anchor}, then stay useful enough that the room does not turn on you."
            if quality_mode == "vague":
                return f"Start with the refuge resupply {anchor} before you touch the harder lanes."
            line = f"Start with the refuge resupply {anchor}; the stop running shortest is the stop that talks first."
            return f"{line} {angle_tail}".strip() if angle_tail else line

        if kind == "spring_run":
            if retrieval:
                line = (
                    f"For the retrieval, start with the spring run {anchor} and see who cannot miss the water leg."
                    if quality_mode != "guarded"
                    else f"For the retrieval, start with the spring run {anchor}, but do not linger long enough to become the memorable stranger on the route."
                )
                return f"{line} {angle_tail}".strip() if quality_mode == "clear" and angle_tail else line
            if quality_mode == "guarded":
                return f"Start with the spring run {anchor}, then move before the route starts remembering you."
            if quality_mode == "vague":
                return f"Start with the spring run {anchor} before the refuge chain settles."
            line = f"Start with the spring run {anchor}; whoever cannot miss the water leg is the one who gives the chain away."
            return f"{line} {angle_tail}".strip() if angle_tail else line

        return ""

    def _specialty_opportunity_risk_line(self, row, context, *, quality=None, retrieval=False):
        if not isinstance(row, dict):
            return ""
        kind = str(row.get("kind", "")).strip().lower()
        if kind not in SPECIALTY_OPPORTUNITY_THEMES:
            return ""

        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, "risk")
        quality_mode = str(quality.get("mode", "clear")).strip().lower() or "clear"
        anchor = self._opportunity_anchor_clause(row, context, preposition="around")
        risk_tail = self._opportunity_followthrough_risk_tail(row, quality=quality)

        if kind == "layover_shuffle":
            if quality_mode == "vague":
                return f"Traveler turnover {anchor} hides you until it decides you are the extra."
            if quality_mode == "guarded":
                return f"Traveler turnover {anchor} gives you cover, but strangers there still remember the wrong face."
            line = f"Traveler turnover {anchor} gives you cover, but strangers there still remember the wrong face once you stop looking like you belong."
            return f"{line} {risk_tail}".strip() if risk_tail else line

        if kind == "route_stash":
            if quality_mode == "vague":
                return f"Route stashes {anchor} cool fast."
            if quality_mode == "guarded":
                return f"Route stashes {anchor} cool fast, and hovering around one makes you the obvious extra."
            line = f"Route stashes {anchor} cool fast, and hovering around one makes you the obvious extra before the next line turns over."
            return f"{line} {risk_tail}".strip() if risk_tail else line

        if kind == "yard_strip":
            if quality_mode == "vague":
                return f"Salvage lanes {anchor} can turn rough quickly."
            if quality_mode == "guarded":
                return f"Salvage lanes {anchor} turn territorial fast if you show up late or loud."
            line = f"Salvage lanes {anchor} turn territorial fast if you show up late, loud, or on the wrong crew's edge."
            return f"{line} {risk_tail}".strip() if risk_tail else line

        if kind == "field_repair_call":
            if quality_mode == "vague":
                return f"Quiet repair calls {anchor} stay quiet right up until they do not."
            if quality_mode == "guarded":
                return f"Quiet repair calls {anchor} stay soft only until the fix goes noisy and everybody starts watching."
            line = f"Quiet repair calls {anchor} stay soft only until the fix goes noisy and everybody starts watching the same breakdown."
            return f"{line} {risk_tail}".strip() if risk_tail else line

        if kind == "sightline_check":
            if quality_mode == "vague":
                return f"Good sightlines {anchor} work both ways."
            if quality_mode == "guarded":
                return f"Good sightlines {anchor} pay in reads, but they also make you easier to clock if you overstay."
            line = f"Good sightlines {anchor} pay in reads, but they also make you easier to clock if you overstay and become the thing being watched."
            return f"{line} {risk_tail}".strip() if risk_tail else line

        if kind == "relay_watch":
            if quality_mode == "vague":
                return f"Quiet relay chains {anchor} remember patterns."
            if quality_mode == "guarded":
                return f"Quiet relay chains {anchor} remember patterns, and one bad repeat can close the lane on you."
            line = f"Quiet relay chains {anchor} remember patterns, and one bad repeat can close the lane on you before you learn anything useful."
            return f"{line} {risk_tail}".strip() if risk_tail else line

        if kind == "refuge_resupply":
            if quality_mode == "vague":
                return f"Refuge stops {anchor} are soft until you read like pressure."
            if quality_mode == "guarded":
                return f"Refuge stops {anchor} are grateful right up until you stop reading like help."
            line = f"Refuge stops {anchor} are grateful right up until you stop reading like help and start reading like pressure."
            return f"{line} {risk_tail}".strip() if risk_tail else line

        if kind == "spring_run":
            if quality_mode == "vague":
                return f"Water legs {anchor} get memorable fast when somebody misses one."
            if quality_mode == "guarded":
                return f"Water legs {anchor} sound soft until somebody misses one and every stranger gets remembered."
            line = f"Water legs {anchor} sound soft until somebody misses one and every stranger on the route gets remembered."
            return f"{line} {risk_tail}".strip() if risk_tail else line

        return ""

    def _opportunity_detail(self, context, *, quality=None):
        rows = list(context.get("opportunity_rows", ()) or ())
        if not rows:
            return str(context.get("opportunity_summary", "")).strip()
        row = rows[0]
        summary = str(row.get("summary", "")).strip()
        requirement_fragment = self._opportunity_requirement_summary_fragment(row)
        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, "opportunities")
        quality_mode = str(quality.get("mode", "clear")).strip().lower() or "clear"

        detail = summary
        if requirement_fragment and quality_mode != "vague":
            if detail:
                if detail[-1] not in ".!?":
                    detail = f"{detail}."
                detail = f"{detail} {requirement_fragment}."
            else:
                detail = requirement_fragment
        if detail:
            return detail.strip()
        return self._opportunity_summary(context, quality=quality)

    def _retrieval_opportunity_summary(self, row, context, *, quality=None):
        if str(context.get("objective_id", "")).strip().lower() != "high_value_retrieval":
            return ""
        if not isinstance(row, dict):
            return ""

        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, "opportunities")
        quality_mode = str(quality.get("mode", "clear")).strip().lower() or "clear"
        kind = str(row.get("kind", "")).strip().lower()
        summary = str(row.get("summary", "")).strip()
        anchor = self._opportunity_anchor_clause(row, context, preposition="around")
        summary_tail = self._opportunity_followthrough_summary_tail(row, quality=quality)

        specialty_line = self._specialty_opportunity_summary_line(row, context, quality=quality, retrieval=True)
        if specialty_line:
            return specialty_line

        clear_base = ""
        fallback_tail = ""
        guarded_base = ""
        guarded_tail = ""
        vague_base = ""

        if kind == "service_friction":
            clear_base = f"For the retrieval, the service trouble {anchor} is the strongest live lead."
            fallback_tail = "Dragged-out staff and complaint traffic there are exposing timings, access habits, and weak points."
            guarded_base = f"For the retrieval, I would check the service trouble {anchor} first."
            guarded_tail = "People under that kind of drag get sloppy, but verify it yourself."
            vague_base = f"If you are building the retrieval chain, start with the service trouble {anchor}."
        elif kind == "missing_person":
            clear_base = f"For the retrieval, the missing-person trail {anchor} is the strongest live lead."
            fallback_tail = "Search traffic there is exposing who comes and goes, and who acts like they belong."
            guarded_base = f"For the retrieval, I would check the missing-person trail {anchor} first."
            guarded_tail = "Searches shake routine loose, but I would still confirm it yourself."
            vague_base = f"If you are building the retrieval chain, start with the missing-person trail {anchor}."
        elif kind == "property_dispute":
            clear_base = f"For the retrieval, the dispute {anchor} is the strongest live lead."
            fallback_tail = "Split loyalties there make people talk, and routine starts to leak around the edges."
            guarded_base = f"For the retrieval, I would lean on the dispute {anchor} first."
            guarded_tail = "When loyalties split, somebody usually talks, but make them prove it."
            vague_base = f"If you are building the retrieval chain, start with the dispute {anchor}."
        elif kind == "lead_followup":
            clear_base = f"For the retrieval, the follow-up lead {anchor} is still warm."
            fallback_tail = "Walk it before the trail cools and turns back into rumor."
            guarded_base = f"For the retrieval, I would walk the follow-up lead {anchor} first."
            guarded_tail = "Fresh trails cool fast."
            vague_base = f"If you are building the retrieval chain, walk the follow-up lead {anchor}."
        elif kind == "intel_scout":
            clear_base = f"For the retrieval, the scout read {anchor} is worth the walk."
            fallback_tail = "A clean pass there should tell you who belongs, who lingers, and when the site breathes."
            guarded_base = f"For the retrieval, I would scout {anchor} before committing."
            guarded_tail = "Do the read yourself before you trust the timing."
            vague_base = f"If you are building the retrieval chain, scout {anchor} first."
        elif kind == "landmark_survey":
            clear_base = f"For the retrieval, the survey lead {anchor} is worth your time."
            fallback_tail = "Watching who treats that place like background can tell you what it is hiding."
            guarded_base = f"For the retrieval, I would survey {anchor} before pushing deeper."
            guarded_tail = "You want the place to look ordinary before it starts giving anything away."
            vague_base = f"If you are building the retrieval chain, survey {anchor} first."
        elif kind == "district_contract":
            clear_base = f"For the retrieval, the contract traffic {anchor} is the live lead."
            fallback_tail = "Side work there can put you on the right block without looking like you are casing it."
            guarded_base = f"For the retrieval, I would ride the contract traffic {anchor} first."
            guarded_tail = "It can cover you, but only if you still look like you belong in the lane."
            vague_base = f"If you are building the retrieval chain, use the contract traffic {anchor} first."
        else:
            return ""

        if quality_mode == "guarded":
            return f"{guarded_base} {guarded_tail}".strip()
        if quality_mode == "vague":
            return vague_base.strip()

        detail = summary or fallback_tail
        if detail:
            line = f"{clear_base} {detail}".strip()
            return f"{line} {summary_tail}".strip() if summary_tail else line
        return f"{clear_base} {summary_tail}".strip() if summary_tail else clear_base.strip()

    def _opportunity_summary(self, context, *, quality=None):
        focus_lines = list(context.get("objective_focus_lines", ()) or ())
        rows = list(context.get("opportunity_rows", ()) or ())
        judgment = context.get("primary_opportunity_judgment", {}) or {}
        urgency = str(judgment.get("urgency", "")).strip().lower()
        invitation = str(judgment.get("invitation", "mention")).strip().lower()
        voice_tone = str(judgment.get("voice_tone", "")).strip().lower()
        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, "opportunities")
        quality_mode = str(quality.get("mode", "clear")).strip().lower() or "clear"

        # If the NPC's judgment is "pass", don't mention the opportunity at all.
        if invitation == "pass" and not focus_lines:
            return ""

        if rows:
            row = rows[0]
            retrieval_summary = self._retrieval_opportunity_summary(row, context, quality=quality)
            if retrieval_summary:
                return retrieval_summary
            specialty_summary = self._specialty_opportunity_summary_line(row, context, quality=quality)
            if specialty_summary:
                return specialty_summary
            title = str(row.get("title", "Opportunity")).strip() or "Opportunity"
            summary = str(row.get("summary", "")).strip()
            distance = int(row.get("distance", 0))
            direction = str(row.get("direction", "HERE")).strip()
            risk = str(row.get("risk", "low")).strip().lower() or "low"
            requirement_fragment = self._opportunity_requirement_summary_fragment(row)
            followthrough_tail = self._opportunity_followthrough_summary_tail(row, quality=quality)

            # Humanize distance with directional context (1 chunk = ~200m).
            distance_phrase = self._humanize_distance_with_direction(distance, direction, context)

            if quality_mode == "guarded":
                base = f"{title} {distance_phrase} is the one I keep hearing about."
                if risk == "hazardous":
                    base += " Might pay, but I would verify it yourself before betting on it."
                else:
                    base += " Might be worth checking, but verify the timing yourself."
                if focus_lines:
                    base = f"{base} {str(focus_lines[0]).strip()}"
                return base.strip()
            if quality_mode == "vague":
                base = f"{title} {distance_phrase} might be moving."
                if risk in {"exposed", "hazardous"}:
                    base += " I would double-check it before you lean on it."
                else:
                    base += " Check it yourself before you bet on it."
                return base.strip()

            # Build a more conversational summary instead of a board-style line.
            # Deterministically pick a template based on seed + NPC + opportunity.
            if voice_tone == "eager":
                templates = [
                    "You should check out {title} {distance_phrase}. {summary}",
                    "There's a sharp one: {title} {distance_phrase}. {summary}",
                    "{title} {distance_phrase} is exactly the thing. {summary}",
                    "Mark this down: {title} {distance_phrase}. {summary}",
                ]
            elif voice_tone == "cautious":
                templates = [
                    "There's a {title} {distance_phrase} if you want. {summary}",
                    "I heard about {title} {distance_phrase}. Could work if {summary}",
                    "{title} is {distance_phrase}, though {summary}",
                    "Maybe {title} {distance_phrase}? {summary}",
                ]
            else:  # dry / neutral
                templates = [
                    "There's a {title} {distance_phrase} that {summary}",
                    "I heard about {title} {distance_phrase}. {summary}",
                    "{title} is {distance_phrase}. {summary}",
                    "{title} {distance_phrase} is the one people are talking about. {summary}",
                ]
            
            seed = f"{getattr(self.sim, 'seed', 0)}:opportunity_summary:{context.get('npc_eid', 0)}:{row.get('id')}"
            chooser = random.Random(seed)
            template = chooser.choice(templates)

            safe_summary = summary or "might be worth a look"
            base = template.format(title=title, summary=safe_summary, distance_phrase=distance_phrase)
            if requirement_fragment:
                if not base.endswith(('.', '!', '?')):
                    base = f"{base}."
                base = f"{base} {requirement_fragment}."

            # Voice urgency through framing when not already baked into template.
            if voice_tone == "dry" and urgency == "high":
                base = f"Heads up: {base}"
            elif voice_tone == "dry" and urgency == "low":
                base = f"If you want, {base}"

            # Mention non-standard risks conversationally, using natural language.
            extra_parts = []
            if risk == "exposed":
                extra_parts.append("watch your back")
            elif risk == "hazardous":
                extra_parts.append("it's rough out there")
            extra = ""
            if extra_parts:
                extra = " " + " and ".join(extra_parts) + "."

            focus_line = str(focus_lines[0]).strip() if focus_lines else ""
            result = f"{base}{extra}".strip()
            if followthrough_tail:
                result = f"{result} {followthrough_tail}".strip()
            if focus_line:
                result = f"{result} {focus_line}"
            return result
        if focus_lines:
            return str(focus_lines[0]).strip()
        return str(context.get("opportunity_summary", "")).strip()

    def _fallout_summary(self, row, context, *, quality=None):
        if not isinstance(row, dict):
            return ""
        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, "fallout")
        quality_mode = str(quality.get("mode", "clear")).strip().lower() or "clear"
        title = str(row.get("title", "Opportunity")).strip() or "Opportunity"
        summary = str(row.get("summary", "")).strip()
        distance = int(row.get("distance", 0) or 0)
        direction = str(row.get("direction", "HERE")).strip()
        risk = str(row.get("risk", "low")).strip().lower() or "low"
        distance_phrase = self._humanize_distance_with_direction(distance, direction, context)

        if quality_mode == "guarded":
            return f"{title} {distance_phrase} is still the fallout I would watch, but I would get there before the story settles."
        if quality_mode == "vague":
            return f"{title} {distance_phrase} might still have something left in the wake."

        base = f"{title} {distance_phrase} is still live."
        if summary:
            base = f"{base} {summary}"
        if risk == "hazardous":
            base = f"{base} It could still turn ugly."
        elif risk == "exposed":
            base = f"{base} Move before the block finishes comparing notes."
        else:
            base = f"{base} It is cleaner if you get there before it cools."
        return base.strip()

    def _final_operation_lead_reason_line(self, context, *, quality=None):
        target_property_name = str(context.get("final_operation_target_property_name", "")).strip() or "the target site"
        target_property_id = str(context.get("final_operation_target_property_id", "")).strip()
        target_reason = str(context.get("final_operation_target_reason", "")).strip()
        target_quality = str(context.get("final_operation_target_quality_label", "")).strip()
        if not target_property_id:
            return ""

        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, "objective")
        quality_mode = str(quality.get("mode", "clear")).strip().lower() or "clear"
        if quality_mode == "vague":
            return f"The retrieval trail keeps bending toward {target_property_name}; there is enough there to justify a harder look."
        if quality_mode == "guarded":
            if target_reason:
                return f"{target_property_name} still reads like the right site off that {target_reason}, but I would walk the chain again myself before committing."
            return f"{target_property_name} still reads like the right site, but I would walk the chain again myself before committing."
        if target_reason and target_quality:
            return f"The {target_quality} {target_reason} around {target_property_name} is what keeps putting it at the center of the retrieval chain."
        if target_reason:
            return f"The {target_reason} around {target_property_name} is what keeps putting it at the center of the retrieval chain."
        return f"{target_property_name} is where the retrieval chain keeps collapsing."

    def _retrieval_objective_support_line(self, row, context, *, quality=None):
        if str(context.get("objective_id", "")).strip().lower() != "high_value_retrieval":
            return ""
        if not isinstance(row, dict):
            return ""

        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, "objective")
        quality_mode = str(quality.get("mode", "clear")).strip().lower() or "clear"
        kind = str(row.get("kind", "")).strip().lower()
        anchor = self._opportunity_anchor_clause(row, context, preposition="around")

        if kind == "layover_shuffle":
            return (
                f"Build the retrieval chain through the traveler turnover {anchor}; cover traffic there hides who is really moving with intent."
                if quality_mode != "guarded"
                else f"Lean on the traveler turnover {anchor}, but make sure you can sort the real handoff from the ordinary layover."
            )
        if kind == "route_stash":
            return (
                f"Build the retrieval chain through the route stash {anchor}; whoever keeps servicing it tells you who uses the lane on purpose."
                if quality_mode != "guarded"
                else f"Lean on the route stash {anchor}, but confirm who is servicing it before you trust the read."
            )
        if kind == "yard_strip":
            return (
                f"Build the retrieval chain through the yard strip {anchor}; salvage traffic there exposes who needs discreet parts and quiet exits."
                if quality_mode != "guarded"
                else f"Lean on the yard strip {anchor}, but do not mistake crew noise for the real route."
            )
        if kind == "field_repair_call":
            return (
                f"Build the retrieval chain through the repair call {anchor}; desperate fixes expose who needs a vehicle ready without attention."
                if quality_mode != "guarded"
                else f"Lean on the repair call {anchor}, but make the desperate customer prove they matter before you commit."
            )
        if kind == "sightline_check":
            return (
                f"Build the retrieval chain through the sightline read {anchor}; it tells you who owns the dead ground and who only crosses it."
                if quality_mode != "guarded"
                else f"Lean on the sightline read {anchor}, but keep moving before you become the obvious watcher."
            )
        if kind == "relay_watch":
            return (
                f"Build the retrieval chain through the relay watch {anchor}; repeat traffic there tells you who keeps using the chain with intent."
                if quality_mode != "guarded"
                else f"Lean on the relay watch {anchor}, but make sure the repeat face you pick is real and not the decoy."
            )
        if kind == "refuge_resupply":
            return (
                f"Build the retrieval chain through the refuge resupply {anchor}; short shelter stops expose who keeps leaning on the quiet route."
                if quality_mode != "guarded"
                else f"Lean on the refuge resupply {anchor}, but stay useful enough that nobody starts reading you as pressure."
            )
        if kind == "spring_run":
            return (
                f"Build the retrieval chain through the spring run {anchor}; water legs tell you who cannot afford to miss the route."
                if quality_mode != "guarded"
                else f"Lean on the spring run {anchor}, but do not linger long enough to become the memorable stranger."
            )

        if kind == "service_friction":
            if quality_mode == "vague":
                return f"Build the retrieval chain through the service trouble {anchor}."
            if quality_mode == "guarded":
                return f"Lean on the service trouble {anchor}, but make it prove itself before you bet the run on it."
            return f"Build the retrieval chain through the service trouble {anchor}; dragged-out staff leak timings and weak points."
        if kind == "missing_person":
            if quality_mode == "vague":
                return f"Build the retrieval chain through the missing-person trail {anchor}."
            if quality_mode == "guarded":
                return f"Lean on the missing-person trail {anchor}, but confirm who is really searching and who is only listening."
            return f"Build the retrieval chain through the missing-person trail {anchor}; search traffic exposes who comes and goes."
        if kind == "property_dispute":
            if quality_mode == "vague":
                return f"Build the retrieval chain through the dispute {anchor}."
            if quality_mode == "guarded":
                return f"Lean on the dispute {anchor}, but do not mistake noise for a real seam."
            return f"Build the retrieval chain through the dispute {anchor}; split loyalties make people talk."
        if kind == "lead_followup":
            return (
                f"Push the follow-up lead {anchor} before it cools."
                if quality_mode != "guarded"
                else f"Push the follow-up lead {anchor}, but walk it yourself before it turns back into rumor."
            )
        if kind == "intel_scout":
            return (
                f"Scout {anchor} until routine stops looking ordinary."
                if quality_mode != "guarded"
                else f"Scout {anchor}, but do the read yourself before you trust it."
            )
        if kind == "landmark_survey":
            return (
                f"Survey {anchor} until you know who treats the place like scenery."
                if quality_mode != "guarded"
                else f"Survey {anchor}, but do not force a pattern before the place gives you one."
            )
        if kind == "district_contract":
            return (
                f"Use the contract traffic {anchor} to get on the block without looking like a casing pass."
                if quality_mode != "guarded"
                else f"Use the contract traffic {anchor}, but only if you still look like you belong in that lane."
            )
        return ""

    def _objective_lines(self, context, *, quality=None):
        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, "objective")
        if context.get("is_rival_operator"):
            lines = self._opportunity_angle_lines(context)
            if not lines:
                lines = self._opportunity_risk_lines(context)
            return [str(line).strip() for line in lines if str(line).strip()]
        lines = []
        objective_id = str(context.get("objective_id", "")).strip().lower()
        if objective_id == "high_value_retrieval":
            final_reason_line = self._final_operation_lead_reason_line(context, quality=quality)
            if final_reason_line:
                lines.append(final_reason_line)
            for row in list(context.get("opportunity_rows", ()) or ())[:2]:
                support_line = self._retrieval_objective_support_line(row, context, quality=quality)
                if support_line and support_line not in lines:
                    lines.append(support_line)
        objective_title = str(context.get("objective_title", "")).strip() or "the run"
        next_step = str(context.get("objective_next_step", "")).strip()
        if next_step:
            lines.append(f"For {objective_title}, {next_step[:1].lower() + next_step[1:]}")
        lines.extend(list(context.get("objective_why_lines", ()) or ()))
        lines.extend(list(context.get("objective_how_lines", ()) or ()))
        return [str(line).strip() for line in lines if str(line).strip()]

    def _objective_summary(self, context, ask_count):
        quality = self._dialogue_pressure_intel_quality(context, "objective")
        return self._cycled_dialogue_line(self._objective_lines(context, quality=quality), ask_count)

    def _opportunity_requirement_angle_line(self, row):
        requirements = dict(row.get("requirements", {}) or {}) if isinstance(row, dict) else {}
        item_label = str(requirements.get("item_label", "")).strip()
        acquisition_hint = str(requirements.get("acquisition_hint", "")).strip().lower()
        if not item_label:
            interact_name = str(requirements.get("interact_npc_name", "")).strip()
            interaction_requirement = str(requirements.get("interaction_requirement", "contact")).strip().lower() or "contact"
            if not interact_name:
                return ""
            if interaction_requirement == "pressure":
                return f"You need to find {interact_name} in person and make the message stick."
            return f"The real job is reaching {interact_name} directly, not just touching the block."
        if acquisition_hint == "provided":
            return f"They should hand you the {item_label} at pickup, so the real job is making the drop cleanly."
        if acquisition_hint == "buy_or_find":
            return f"You need to source {item_label} yourself first, then make the handoff."
        if acquisition_hint == "pickup":
            return f"Make the outward trip first, collect the {item_label}, then bring it back on the return leg."
        return ""

    def _opportunity_requirement_risk_line(self, row):
        requirements = dict(row.get("requirements", {}) or {}) if isinstance(row, dict) else {}
        item_label = str(requirements.get("item_label", "")).strip()
        acquisition_hint = str(requirements.get("acquisition_hint", "")).strip().lower()
        if not item_label:
            interact_name = str(requirements.get("interact_npc_name", "")).strip()
            interaction_requirement = str(requirements.get("interaction_requirement", "contact")).strip().lower() or "contact"
            if not interact_name:
                return ""
            if interaction_requirement == "pressure":
                return f"If {interact_name} slips away or brushes you off, the whole pressure job stays open."
            return f"It only pays once you reach {interact_name} directly."
        if acquisition_hint == "provided":
            return f"Once they hand over the {item_label}, do not lose it before the drop."
        if acquisition_hint == "buy_or_find":
            return f"The catch is you still have to buy or find {item_label} before it pays out."
        if acquisition_hint == "pickup":
            return f"It is a two-leg run, and carrying the {item_label} back is the part that can go sideways."
        return ""

    _ANGLE_PLAYSTYLE_PHRASES = {
        "social": (
            "People are the opening on it.",
            "The first seam is usually a person, not a lock.",
            "It starts with somebody talking.",
        ),
        "economic": (
            "Money is the lever on it.",
            "Follow the payout trail, not just the route.",
            "The credits are part of the route, not just the reward.",
        ),
        "stealth": (
            "Quiet setup matters more than speed.",
            "It wants softer feet than the room expects.",
            "You win it by staying cleaner than the site expects.",
        ),
        "combat": (
            "Go in ready for friction.",
            "Do not assume it stays soft once you touch it.",
            "Force is an option, not a guarantee.",
        ),
    }

    def _opportunity_angle_style_line(self, row, context):
        if not isinstance(row, dict):
            return ""
        playstyles = [
            str(style).strip().lower()
            for style in tuple(row.get("playstyles", ()) or ())
            if str(style).strip()
        ]
        if not playstyles:
            return ""
        variants = self._ANGLE_PLAYSTYLE_PHRASES.get(playstyles[0])
        if not variants:
            return ""
        seed = f"{getattr(self.sim, 'seed', 0)}:angle-style:{context.get('npc_eid', 0)}:{row.get('id', 0)}"
        return str(random.Random(seed).choice(variants)).strip()

    def _final_operation_angle_line(self, context, *, quality=None):
        target_property_id = str(context.get("final_operation_target_property_id", "") or "").strip()
        target_property_name = str(context.get("final_operation_target_property_name", "") or "").strip() or "the target site"
        entry_detail = str(context.get("final_operation_target_entry_detail", "") or "").strip()
        if not target_property_id or not entry_detail:
            return ""

        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, "angle")
        quality_mode = str(quality.get("mode", "clear")).strip().lower() or "clear"
        if quality_mode == "vague":
            return f"For the retrieval itself, do not hit {target_property_name} from the front. Walk it and find the softer seam first."
        if quality_mode == "guarded":
            return f"For the retrieval itself, there is a cleaner angle into {target_property_name}, but I would confirm it on-site before betting on it."
        return f"For the retrieval itself, {entry_detail}"

    def _retrieval_opportunity_angle_line(self, row, context, *, quality=None):
        if str(context.get("objective_id", "")).strip().lower() != "high_value_retrieval":
            return ""
        if not isinstance(row, dict):
            return ""

        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, "angle")
        quality_mode = str(quality.get("mode", "clear")).strip().lower() or "clear"
        kind = str(row.get("kind", "")).strip().lower()
        anchor = self._opportunity_anchor_clause(row, context, preposition="around")
        angle_tail = self._opportunity_followthrough_angle_tail(row, quality=quality)

        specialty_line = self._specialty_opportunity_angle_line(row, context, quality=quality, retrieval=True)
        if specialty_line:
            return specialty_line

        if kind == "service_friction":
            if quality_mode == "vague":
                return f"Start with the service trouble {anchor} before you touch anything else."
            if quality_mode == "guarded":
                return f"Start with the service trouble {anchor}, then confirm the timing yourself."
            line = f"Start with the complaint-heavy side {anchor}; delayed service is exposing timings and access habits."
            return f"{line} {angle_tail}".strip() if angle_tail else line
        if kind == "missing_person":
            if quality_mode == "vague":
                return f"Start with the missing-person trail {anchor}."
            if quality_mode == "guarded":
                return f"Start with the missing-person trail {anchor}, then verify who is really moving because of it."
            line = f"Start with the people asking after the missing person {anchor}; search traffic shakes routine loose."
            return f"{line} {angle_tail}".strip() if angle_tail else line
        if kind == "property_dispute":
            if quality_mode == "vague":
                return f"Start with the dispute {anchor}."
            if quality_mode == "guarded":
                return f"Start with the dispute {anchor}, then make somebody prove which side is actually talking."
            line = f"Start with the split {anchor}; the side that feels squeezed is the side that talks."
            return f"{line} {angle_tail}".strip() if angle_tail else line
        if kind == "lead_followup":
            line = (
                f"Start by walking the follow-up lead {anchor} before it cools."
                if quality_mode != "guarded"
                else f"Start by walking the follow-up lead {anchor}, then confirm it before it turns back into rumor."
            )
            return f"{line} {angle_tail}".strip() if quality_mode == "clear" and angle_tail else line
        if kind == "intel_scout":
            line = (
                f"Start by scouting {anchor} until you know who belongs and who lingers."
                if quality_mode != "guarded"
                else f"Start by scouting {anchor}, but make the read yourself before you trust it."
            )
            return f"{line} {angle_tail}".strip() if quality_mode == "clear" and angle_tail else line
        if kind == "landmark_survey":
            line = (
                f"Start by watching {anchor} long enough to see who treats it like background."
                if quality_mode != "guarded"
                else f"Start by surveying {anchor}, but do not force the pattern before the place gives it to you."
            )
            return f"{line} {angle_tail}".strip() if quality_mode == "clear" and angle_tail else line
        if kind == "district_contract":
            line = (
                f"Start with the contract traffic {anchor}; it gives you a reason to be on the block."
                if quality_mode != "guarded"
                else f"Start with the contract traffic {anchor}, but make sure you still look like you belong in that lane."
            )
            return f"{line} {angle_tail}".strip() if quality_mode == "clear" and angle_tail else line
        return ""

    def _final_operation_risk_line(self, context, *, quality=None):
        target_property_id = str(context.get("final_operation_target_property_id", "") or "").strip()
        target_property_name = str(context.get("final_operation_target_property_name", "") or "").strip() or "the target site"
        entry_detail = str(context.get("final_operation_target_entry_detail", "") or "").strip().lower()
        if not target_property_id:
            return ""

        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, "risk")
        quality_mode = str(quality.get("mode", "clear")).strip().lower() or "clear"

        prop = self.sim.properties.get(target_property_id)
        controller = _property_access_controller(self.sim, prop) if isinstance(prop, dict) else {}
        requirement = _controller_access_requirement_text(controller) if isinstance(controller, dict) else "real clearance"
        security_text = _dialogue_security_tier_text((controller or {}).get("security_tier"))

        if quality_mode == "vague":
            return f"On the retrieval, do not count on the first soft read holding once you show your face at {target_property_name}."
        if quality_mode == "guarded":
            return f"On the retrieval, if the clean angle is gone, {target_property_name} goes back to real {requirement} fast."

        bits = [f"If that entry window closes, {target_property_name} falls back to {requirement}"]
        if security_text:
            bits[-1] = f"{bits[-1]} and {security_text}"
        bits[-1] = f"{bits[-1]}."
        if "blackout" in entry_detail:
            bits.append("That blackout edge will not hold forever.")
        elif "worker cover" in entry_detail or "shift" in entry_detail:
            bits.append("Once the routine settles, the clean window gets thinner.")
        elif "hired backup" in entry_detail:
            bits.append("Miss the timing and the easy support edge goes away with it.")
        return " ".join(bit for bit in bits if bit)

    def _opportunity_angle_lines(self, context, *, quality=None, include_final_operation=True):
        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, "angle")
        quality_mode = str(quality.get("mode", "clear")).strip().lower() or "clear"
        lines = []
        retrieval_objective = str(context.get("objective_id", "")).strip().lower() == "high_value_retrieval"
        final_operation_line = self._final_operation_angle_line(context, quality=quality)
        if include_final_operation and final_operation_line:
            lines.append(final_operation_line)
        for row in list(context.get("opportunity_rows", ()) or ()):
            retrieval_line = self._retrieval_opportunity_angle_line(row, context, quality=quality)
            if retrieval_line:
                lines.append(retrieval_line)
                continue
            specialty_line = self._specialty_opportunity_angle_line(row, context, quality=quality)
            if specialty_line:
                lines.append(specialty_line)
                continue
            title = str(row.get("title", "Opportunity")).strip() or "Opportunity"
            summary = str(row.get("summary", "")).strip()
            distance = int(row.get("distance", 0))
            direction = str(row.get("direction", "HERE")).strip()
            followthrough_angle = self._opportunity_followthrough_angle_tail(row, quality=quality)
            
            # Humanize distance with directional context (1 chunk = ~200m).
            distance_phrase = self._humanize_distance_with_direction(distance, direction, context)
            requirement_line = self._opportunity_requirement_angle_line(row)
            style_line = self._opportunity_angle_style_line(row, context)
            
            if quality_mode == "guarded":
                line = f"Start with {title} {distance_phrase}, then confirm the rest yourself."
            elif quality_mode == "vague":
                line = f"{title} {distance_phrase} is the kind you walk first before committing."
            else:
                if summary:
                    line = f"Start with {title} {distance_phrase}: {summary}"
                else:
                    line = f"Start with {title} {distance_phrase}."
                if requirement_line:
                    line = f"{line} {requirement_line}"
                if style_line:
                    line = f"{line} {style_line}"
                if followthrough_angle:
                    line = f"{line} {followthrough_angle}"
            lines.append(line)
        if not retrieval_objective:
            lines.extend(list(context.get("objective_focus_lines", ()) or ()))
        if retrieval_objective:
            lines.extend(list(context.get("objective_focus_lines", ()) or ()))
        lines.extend(list(context.get("objective_activity_lines", ()) or ()))
        return [str(line).strip() for line in lines if str(line).strip()]

    def _angle_summary(self, context, ask_count):
        return self._cycled_dialogue_line(self._opportunity_angle_lines(context, include_final_operation=True), ask_count)

    # Human-readable playstyle descriptors, keyed by the internal tag.
    # Multiple variants are chosen deterministically per NPC + opportunity.
    _PLAYSTYLE_PHRASES = {
        "social":   ("runs through people", "talk gets you in", "people carry it"),
        "economic": ("money's the angle", "follow the money on it", "worth the payout"),
        "stealth":  ("quiet work", "best done quiet", "clean if you stay careful"),
        "combat":   ("can get rough", "expect friction", "not a soft job"),
    }

    def _retrieval_opportunity_risk_line(self, row, context, *, quality=None):
        if str(context.get("objective_id", "")).strip().lower() != "high_value_retrieval":
            return ""
        if not isinstance(row, dict):
            return ""

        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, "risk")
        quality_mode = str(quality.get("mode", "clear")).strip().lower() or "clear"
        kind = str(row.get("kind", "")).strip().lower()
        anchor = self._opportunity_anchor_clause(row, context, preposition="around")
        risk_tail = self._opportunity_followthrough_risk_tail(row, quality=quality)

        specialty_line = self._specialty_opportunity_risk_line(row, context, quality=quality, retrieval=True)
        if specialty_line:
            return specialty_line

        if kind == "service_friction":
            if quality_mode == "vague":
                return f"Service trouble {anchor} also means extra eyes if you handle it badly."
            if quality_mode == "guarded":
                return f"Service trouble {anchor} can still pay, but irritated staff remember the wrong face."
            line = f"Service trouble {anchor} means more irritated staff, more complaints, and more people remembering the wrong face."
            return f"{line} {risk_tail}".strip() if risk_tail else line
        if kind == "missing_person":
            if quality_mode == "vague":
                return f"A missing-person trail {anchor} brings extra eyes with it."
            if quality_mode == "guarded":
                return f"A missing-person trail {anchor} means anxious people comparing notes about strangers."
            line = f"A missing-person trail {anchor} means anxious people comparing notes about strangers."
            return f"{line} {risk_tail}".strip() if risk_tail else line
        if kind == "property_dispute":
            if quality_mode == "vague":
                return f"A dispute {anchor} can turn everybody jumpy fast."
            if quality_mode == "guarded":
                return f"A dispute {anchor} means everybody is already expecting somebody to lie."
            line = f"A dispute {anchor} means everybody is already expecting somebody to lie."
            return f"{line} {risk_tail}".strip() if risk_tail else line
        if kind == "lead_followup":
            if quality_mode == "vague":
                return f"That follow-up lead {anchor} will cool if you let the block settle."
            if quality_mode == "guarded":
                return f"That follow-up lead {anchor} cools fast, and if you loiter without purpose you become the memorable part."
            line = f"That follow-up lead {anchor} cools fast, and if you loiter without purpose you become the memorable part."
            return f"{line} {risk_tail}".strip() if risk_tail else line
        if kind == "intel_scout":
            if quality_mode == "vague":
                return f"A scout pass {anchor} is only clean if you keep moving."
            if quality_mode == "guarded":
                return f"A scout pass {anchor} pays in sightlines, but it still tags you if you overstay it."
            line = f"A scout pass {anchor} pays in sightlines, but it still tags you if you overstay it."
            return f"{line} {risk_tail}".strip() if risk_tail else line
        if kind == "landmark_survey":
            if quality_mode == "vague":
                return f"The risk {anchor} is becoming the person who watches a little too carefully."
            if quality_mode == "guarded":
                return f"The risk {anchor} is becoming the person who watches a little too carefully."
            line = f"The risk {anchor} is becoming the person who watches a little too carefully."
            return f"{line} {risk_tail}".strip() if risk_tail else line
        if kind == "district_contract":
            if quality_mode == "vague":
                return f"Contract traffic {anchor} can cover you or expose you."
            if quality_mode == "guarded":
                return f"Contract traffic {anchor} can cover you, but somebody will notice if you do not fit the lane."
            line = f"Contract traffic {anchor} can cover you, but somebody will notice if you do not fit the lane."
            return f"{line} {risk_tail}".strip() if risk_tail else line
        return ""

    def _opportunity_risk_lines(self, context, *, quality=None, include_final_operation=True):
        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, "risk")
        quality_mode = str(quality.get("mode", "clear")).strip().lower() or "clear"
        lines = []
        final_operation_line = self._final_operation_risk_line(context, quality=quality)
        if include_final_operation and final_operation_line:
            lines.append(final_operation_line)
        for row in list(context.get("opportunity_rows", ()) or ()):
            retrieval_line = self._retrieval_opportunity_risk_line(row, context, quality=quality)
            if retrieval_line:
                lines.append(retrieval_line)
                continue
            specialty_line = self._specialty_opportunity_risk_line(row, context, quality=quality)
            if specialty_line:
                lines.append(specialty_line)
                continue
            title = str(row.get("title", "Opportunity")).strip() or "Opportunity"
            risk = str(row.get("risk", "low")).strip() or "low"
            playstyles = [str(style).strip() for style in row.get("playstyles", ()) if str(style).strip()]
            followthrough_risk = self._opportunity_followthrough_risk_tail(row, quality=quality)

            if quality_mode == "guarded":
                lines.append(f"{title} can still pay, but expect less room to improvise than people say.")
                continue
            if quality_mode == "vague":
                lines.append(f"{title} can go sideways fast. Do a clean read before you commit.")
                continue

            # Humanize risk language.
            if risk == "calm":
                risk_text = "is clean"
            elif risk == "low":
                risk_text = "is straightforward"
            elif risk == "exposed":
                risk_text = "draws attention if you mess up"
            else:  # hazardous
                risk_text = "is rough"

            # Convert the raw playstyle tag into a natural spoken phrase,
            # chosen deterministically per NPC + opportunity.
            style_phrase = ""
            if playstyles:
                primary = playstyles[0]
                variants = self._PLAYSTYLE_PHRASES.get(primary)
                if variants:
                    seed = f"{getattr(self.sim, 'seed', 0)}:risk-style:{context.get('npc_eid', 0)}:{row.get('id', 0)}"
                    style_phrase = random.Random(seed).choice(variants).capitalize() + "."
                else:
                    # Unknown tag: drop rather than dump the raw label.
                    style_phrase = ""

            parts = [f"{title} {risk_text}."]
            if style_phrase:
                parts.append(style_phrase)
            requirement_risk = self._opportunity_requirement_risk_line(row)
            if requirement_risk:
                parts.append(requirement_risk)
            if followthrough_risk:
                parts.append(followthrough_risk)
            lines.append(" ".join(parts))
        return [str(line).strip() for line in lines if str(line).strip()]

    def _risk_summary(self, context, ask_count):
        lines = self._opportunity_risk_lines(context)
        if not lines:
            lines = list(context.get("objective_activity_lines", ()) or ())
        return self._cycled_dialogue_line(lines, ask_count)

    def _attention_lines(self, context):
        lines = []
        pressure_tier = str(context.get("pressure_tier", "low")).strip().lower() or "low"
        pressure_role = str(context.get("pressure_role", "") or self._dialogue_pressure_role(context)).strip().lower() or "local"
        owner_place_name = str(context.get("owner_place_name", "")).strip()
        access_level = str(context.get("access_level", "")).strip().lower()
        standing = float(context.get("contact_standing", 0.0))
        recent_offense = context.get("recent_offense")
        guarded = bool(context.get("guarded"))

        if guarded and owner_place_name:
            lines.append(f"Badly. Around {owner_place_name}, you already look like trouble.")
        elif recent_offense:
            action = str(recent_offense.get("data", {}).get("action", "trouble")).replace("_", " ").strip() or "trouble"
            lines.append(f"People still remember your {action}. That keeps attention on you longer than you think.")

        if pressure_tier in {"medium", "high"}:
            if pressure_role == "guard":
                lines.append("Patrol types remember faces. Push another secure door right now and someone is going to stop or report you.")
            elif pressure_role == "worker":
                lines.append("Workers talk, managers ask questions, and shifts remember who made trouble.")
            elif pressure_role == "merchant":
                lines.append("Heat scares off ordinary customers. Anything messy around a counter turns into gossip fast.")
            elif pressure_role == "neighbor":
                lines.append("Blocks remember loiterers. Keep it off stoops, hallways, and other people's doors for a while.")
            elif pressure_role == "chaotic":
                lines.append("Hot streets do not scare everyone; they just make the smart ones move faster and talk less.")

        if pressure_tier == "high":
            lines.append("City attention is high. Keep your head down and stay away from protected places for a while.")
            if standing >= 0.62:
                lines.append("Friendly faces might still help you, but nobody is going to like being obvious about it.")
            else:
                lines.append("You are not reading clean right now. I would not go asking for favors in public.")
        elif pressure_tier == "medium":
            lines.append("You are drawing some attention. People are starting to notice patterns, even if they are not acting on them yet.")
            if standing >= 0.62:
                lines.append("Stick to people who already know you and keep the ask small.")
            else:
                lines.append("Keep it local, keep it light, and do not press secure doors.")
        else:
            lines.append("Not much heat on you right now. Keep it that way by not lingering where you do not belong.")
            if standing >= 0.62:
                lines.append("You are reading clean enough that a careful ask can still land.")
            else:
                lines.append("Do not mistake quiet for safety. People still remember strange behavior.")

        if access_level in {"protected", "restricted"} and owner_place_name and pressure_tier in {"medium", "high"}:
            lines.append(f"If you want less attention, avoid pushing {owner_place_name} until things cool.")

        cleaned = []
        seen = set()
        for raw in lines:
            text = str(raw).strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            cleaned.append(text)
        return cleaned

    def _attention_summary(self, context, ask_count):
        return self._cycled_dialogue_line(self._attention_lines(context), ask_count)

    def _credential_access_label(self, controller):
        mode = str((controller or {}).get("credential_mode", "") or "").strip().lower()
        if mode == "badge":
            return "badge access"
        if mode == "biometric":
            return "biometric clearance"
        return "the keys"

    def _aperture_summary_label(self, aperture, *, article=True):
        kind = str((aperture or {}).get("kind", "door") or "door").strip().lower()
        side = str((aperture or {}).get("side", "") or "").strip().lower()
        if kind in {"service_door", "employee_door"}:
            label = "service door"
        elif kind == "side_door":
            label = "side door"
        elif kind == "skylight":
            label = "skylight"
        elif kind == "window":
            label = "window"
        elif bool((aperture or {}).get("ordinary")):
            label = "front door"
        else:
            label = kind.replace("_", " ").strip() or "door"

        if side and label not in {"front door"} and side not in {"front", "street"}:
            label = f"{label} on the {side} side"

        if not article:
            return label
        if label[:1].lower() in {"a", "e", "i", "o", "u"}:
            return f"an {label}"
        return f"a {label}"

    def _dialogue_controller_named_holders(self, controller):
        if not isinstance(controller, dict):
            return []
        named_holders = []
        for holder in tuple(controller.get("authorized_holders", ()) or ()):
            holder_eid = holder.get("eid")
            if holder_eid is None:
                continue
            holder_name = _entity_display_name(self.sim, holder_eid, title_case=True)
            if not holder_name:
                continue
            named_holders.append({
                "name": holder_name,
                "role": str(holder.get("role", "") or "").strip().lower(),
                "tier": _int_or_default(holder.get("credential_tier"), 1),
                "eid": int(holder_eid),
            })
        return named_holders

    def _dialogue_property_fixture_refs(self, owner_place):
        if not isinstance(owner_place, dict):
            return None, None
        metadata = _property_metadata(owner_place)
        panel_id = str(metadata.get("access_panel_property_id", "") or "").strip()
        terminal_id = str(metadata.get("service_terminal_property_id", "") or "").strip()
        panel_prop = self.sim.properties.get(panel_id) if panel_id else None
        terminal_prop = self.sim.properties.get(terminal_id) if terminal_id else None
        return panel_prop, terminal_prop

    def _dialogue_hours_summary(self, context, *, quality=None):
        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, "hours")
        mode = str(quality.get("mode", "clear")).strip().lower() or "clear"
        hours_text = str(context.get("hours_text", "")).strip()
        shift_text = str(context.get("shift_text", "")).strip()
        schedule_source = str((context.get("controller") or {}).get("schedule_source", "") or "").strip().lower()
        if mode == "clear":
            return hours_text
        if mode == "guarded":
            if schedule_source == "owner_shift" and shift_text:
                return "mostly while staff are on"
            if hours_text == "around the clock":
                return "most of the time"
            return "mostly during regular open hours"
        if schedule_source == "owner_shift" and shift_text:
            return "when staff are moving through"
        return "when the place is active"

    def _dialogue_prep_detail(self, context, topic_id, *, quality=None):
        topic_id = str(topic_id or "").strip().lower()
        terms = context.get("dialogue_prep_terms") if isinstance(context, dict) else {}
        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, topic_id)
        detail_level = max(
            0,
            _int_or_default(
                quality.get("detail_level"),
                _int_or_default((terms or {}).get("detail_level"), 0),
            ),
        )
        if detail_level <= 0:
            return ""

        owner_place = context.get("owner_place")
        controller = context.get("controller")
        if not isinstance(owner_place, dict) or not isinstance(controller, dict):
            return ""

        place_name = str(context.get("owner_place_name", "")).strip() or str(owner_place.get("name", owner_place.get("id", "the place"))).strip() or "the place"
        hours_text = str(context.get("hours_text", "")).strip()
        shift_text = str(context.get("shift_text", "")).strip()
        access_level = str(context.get("access_level", "")).strip().lower()
        requirement = _controller_access_requirement_text(controller)
        fixture = str(controller.get("fixture_label", "") or "lock").strip() or "lock"
        schedule_source = str(controller.get("schedule_source", "") or "").strip().lower()
        panel_prop, terminal_prop = self._dialogue_property_fixture_refs(owner_place)

        apertures = tuple(_property_apertures(owner_place))
        side_doors = [
            aperture
            for aperture in apertures
            if str(aperture.get("kind", "") or "").strip().lower() in {"service_door", "employee_door", "side_door"}
        ]
        windows = [
            aperture
            for aperture in apertures
            if str(aperture.get("kind", "") or "").strip().lower() in {"window", "skylight"}
        ]

        named_holders = self._dialogue_controller_named_holders(controller)
        highest = max(
            named_holders,
            key=lambda row: (row["tier"], 1 if row["role"] in {"owner", "manager"} else 0),
            default=None,
        )

        if topic_id == "hours":
            if detail_level >= 2 and highest and (hours_text or shift_text):
                timing = shift_text or hours_text
                return f"If you are timing it, watch {highest['name']} around {timing}; that is when the real {requirement} tends to move."
            if schedule_source == "owner_shift" and shift_text:
                return f"The useful read is staff presence: {shift_text} is what really keeps the front easy."
            if hours_text:
                return f"The clean window is {hours_text}; outside that, the {fixture} tightens around {requirement}."
            return ""

        if topic_id == "routine":
            timing = shift_text or hours_text
            if detail_level >= 2 and highest and side_doors and timing:
                label = self._aperture_summary_label(side_doors[0], article=False)
                return f"Shift turn is the part worth watching. {highest['name']} and the {label} tell you when real access starts moving."
            if detail_level >= 2 and highest and timing:
                return f"If you are reading the place for prep, watch {highest['name']} around {timing}; that is when the real clearance starts moving."
            if side_doors and timing:
                label = self._aperture_summary_label(side_doors[0], article=False)
                return f"Routine traffic usually leaks through the {label} around {timing}, not the front."
            if schedule_source == "owner_shift" and shift_text:
                return "The real rhythm is the staff shift, not the posted hours."
            return ""

        if topic_id == "security":
            if detail_level >= 2 and panel_prop is not None:
                return f"The street-side panel is the seam I would watch first before touching {place_name} blind."
            if detail_level >= 2 and side_doors:
                label = self._aperture_summary_label(side_doors[0], article=False)
                return f"If there is a softer angle, it is usually the {label}, not the front."
            if panel_prop is not None:
                return f"There is an exterior access panel tied into the {fixture}, so the hardware is not all on the threshold."
            if hours_text and access_level in {"public", "restricted", "protected"}:
                return f"The place changes character hard after {hours_text}; that is when the secure read really matters."
            return ""

        if topic_id == "access":
            if detail_level >= 2 and panel_prop is not None:
                return f"You can work the panel from outside if you know what you are doing, instead of testing the threshold cold."
            if detail_level >= 2 and highest and highest["role"] in {"owner", "manager"}:
                return f"{highest['name']} looks like the cleanest carrier for real {requirement}, not just routine access."
            if schedule_source == "owner_shift" and shift_text:
                return f"Shift timing matters almost as much as the credential; when staff are really on, the front reads softer."
            if hours_text:
                return f"Best clean read is during {hours_text}; outside that, expect the {fixture} to ask for the real thing."
            return ""

        if topic_id == "entry":
            if detail_level >= 2 and panel_prop is not None:
                return "There is also an exterior panel, so you do not have to treat the threshold as the only seam."
            if detail_level >= 2 and terminal_prop is not None:
                return "There is a nearby service terminal on the same site, which can matter if you are mapping the place instead of rushing it."
            if side_doors:
                label = self._aperture_summary_label(side_doors[0], article=False)
                return f"The cleaner alternate looks like the {label}, not the front."
            if windows:
                label = self._aperture_summary_label(windows[0], article=False)
                return f"If you are really mapping ingress, the useful alternate is the {label}."
            return ""

        if topic_id == "keyholder":
            if detail_level >= 2 and highest and highest["role"] in {"owner", "manager"}:
                return f"If you are watching for the real carry, {highest['name']} is the one I would track."
            if highest and highest["tier"] > 1:
                return f"There is a hierarchy to it. {highest['name']} is carrying stronger clearance than the rest."
            if shift_text:
                return f"Shift change is when access tends to move around, especially near {shift_text}."
            return ""

        if topic_id == "weak_point":
            final_target_property_id = str(context.get("final_operation_target_property_id", "") or "").strip()
            final_entry_detail = str(context.get("final_operation_target_entry_detail", "") or "").strip()
            if final_entry_detail and final_target_property_id and final_target_property_id == str(owner_place.get("id", "")).strip():
                return final_entry_detail
            timing = shift_text or hours_text
            if detail_level >= 2 and panel_prop is not None and side_doors:
                label = self._aperture_summary_label(side_doors[0], article=False)
                return f"If you are forcing a choice, start with the panel or the {label}; the front is for people who belong there."
            if detail_level >= 2 and highest and timing:
                return f"Best timing is when {highest['name']} moves around {timing}; access is shifting and attention splits."
            if side_doors and timing:
                label = self._aperture_summary_label(side_doors[0], article=False)
                return f"The {label} is softest around {timing}, when routine traffic covers movement."
            if panel_prop is not None:
                return "The exterior panel matters more than the front if you can work it without being seen."
            return ""

        return ""

    def _weak_point_summary(self, context, *, quality=None):
        owner_place = context.get("owner_place")
        controller = context.get("controller")
        if not isinstance(owner_place, dict) or not isinstance(controller, dict):
            return ""

        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, "weak_point")
        quality_mode = str(quality.get("mode", "clear")).strip().lower() or "clear"
        detail_level = max(0, _int_or_default(quality.get("detail_level"), 0))
        place_name = str(context.get("owner_place_name", "")).strip() or str(owner_place.get("name", owner_place.get("id", "the place"))).strip() or "the place"
        hours_text = str(context.get("hours_text", "")).strip()
        shift_text = str(context.get("shift_text", "")).strip()
        access_level = str(context.get("access_level", "")).strip().lower()
        panel_prop, _terminal_prop = self._dialogue_property_fixture_refs(owner_place)
        apertures = tuple(_property_apertures(owner_place))
        side_doors = [
            aperture
            for aperture in apertures
            if str(aperture.get("kind", "") or "").strip().lower() in {"service_door", "employee_door", "side_door"}
        ]
        windows = [
            aperture
            for aperture in apertures
            if str(aperture.get("kind", "") or "").strip().lower() in {"window", "skylight"}
        ]

        final_target_property_id = str(context.get("final_operation_target_property_id", "") or "").strip()
        final_entry_detail = str(context.get("final_operation_target_entry_detail", "") or "").strip()
        if final_entry_detail and final_target_property_id == str(owner_place.get("id", "")).strip():
            if quality_mode == "vague":
                return f"Do not hit {place_name} from the front. Find the softer seam first."
            if quality_mode == "guarded":
                return f"There is a cleaner seam into {place_name}, but I would verify it before you lean on it."
            if detail_level <= 0:
                return f"There is a cleaner seam into {place_name}, but you still need to walk it instead of trusting the front."
            return final_entry_detail

        if quality_mode == "vague":
            if hours_text or shift_text:
                return "The soft part is timing, not the front."
            return f"Places like {place_name} only soften when routine beats posture."

        if quality_mode == "guarded":
            if panel_prop is not None or side_doors:
                return "The weak point is where routine traffic and hardware meet, not the front."
            if access_level == "public" and hours_text:
                return "The soft spot is the handoff between open doors and real clearance."
            return "Watch timing more than the front door."

        timing = shift_text or hours_text
        if detail_level <= 0:
            if timing:
                return f"The soft part is around {timing}, when routine matters more than posture."
            if access_level == "public" and hours_text:
                return "The soft spot is the handoff between open doors and real clearance."
            return "The weak point is usually timing and side movement, not the front."
        if panel_prop is not None and side_doors:
            label = self._aperture_summary_label(side_doors[0], article=False)
            if timing:
                return f"The seam is between the exterior panel and the {label} around {timing}, when staff traffic splits attention."
            return f"The exterior panel and the {label} are both softer than the front if you stay quiet."
        if panel_prop is not None:
            return f"The exterior panel is the weak seam at {place_name}; the front is where they expect strangers."
        if side_doors:
            label = self._aperture_summary_label(side_doors[0], article=False)
            if timing:
                return f"The {label} softens most around {timing}, when routine traffic covers movement."
            return f"The {label} is the softer seam, not the front."
        if windows:
            label = self._aperture_summary_label(windows[0], article=False)
            return f"The {label} is quieter than the front if you can keep it contained."
        if shift_text:
            return f"Shift change around {shift_text} is the weak point; attention splits and access starts moving."
        if access_level == "public" and hours_text:
            return f"The easy front only holds during {hours_text}; after that, routine is the real seam."
        return ""

    def _access_summary(self, context, *, quality=None):
        owner_place = context.get("owner_place")
        controller = context.get("controller")
        if not owner_place or not isinstance(controller, dict):
            return ""

        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, "access")
        quality_mode = str(quality.get("mode", "clear")).strip().lower() or "clear"
        place_name = str(context.get("owner_place_name", "")).strip() or str(owner_place.get("name", owner_place.get("id", "the place"))).strip() or "the place"
        access_level = str(context.get("access_level", "")).strip().lower()
        hours_text = str(context.get("hours_text", "")).strip()
        fixture = str(controller.get("fixture_label", "") or "lock").strip() or "lock"
        requirement = _controller_access_requirement_text(controller)
        security_text = _dialogue_security_tier_text(controller.get("security_tier"))
        schedule_source = str(controller.get("schedule_source", "") or "").strip().lower()

        if quality_mode == "guarded":
            if access_level == "public" and hours_text:
                return "The front reads easier while the place is active. After hours it wants real clearance."
            if access_level in {"restricted", "protected"}:
                return f"Not a casual door. When it is quiet, the {fixture} wants someone who belongs there."
            return f"Timing matters almost as much as the {fixture}."
        if quality_mode == "vague":
            if access_level == "public":
                return "Easy enough while it is active. If it looks shut, assume it wants someone who belongs there."
            return "Not a casual threshold. If you test it blind, expect it to ask for the real thing."

        if access_level == "public" and hours_text:
            if schedule_source == "owner_shift":
                return f"They relax the front {hours_text} while staff are on shift. After that, the {fixture} wants {requirement}."
            return f"{place_name} runs public hours {hours_text}. After that, the {fixture} wants {requirement}."
        if access_level == "public":
            return f"If it is open, it is straightforward. If not, the {fixture} wants {requirement}."
        if access_level == "restricted":
            return f"{place_name} stays behind {requirement} on the {fixture}, with {security_text}."
        if access_level == "protected":
            return f"{place_name} is usually locked down on the {fixture}. {requirement} gets you through cleanly."
        return f"The {fixture} expects {requirement}."

    def _entry_summary(self, context, *, quality=None):
        owner_place = context.get("owner_place")
        if not owner_place:
            return ""

        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, "entry")
        quality_mode = str(quality.get("mode", "clear")).strip().lower() or "clear"
        apertures = tuple(_property_apertures(owner_place))
        if not apertures:
            return ""

        ordinary = [aperture for aperture in apertures if bool(aperture.get("ordinary"))]
        side_doors = [
            aperture
            for aperture in apertures
            if str(aperture.get("kind", "") or "").strip().lower() in {"service_door", "employee_door", "side_door"}
        ]
        windows = [
            aperture
            for aperture in apertures
            if str(aperture.get("kind", "") or "").strip().lower() in {"window", "skylight"}
        ]

        bits = []
        if ordinary:
            bits.append("the front door")
        if len(side_doors) == 1:
            bits.append(self._aperture_summary_label(side_doors[0], article=True))
        elif len(side_doors) > 1:
            bits.append(f"{len(side_doors)} side/service doors")
        if len(windows) == 1:
            bits.append(self._aperture_summary_label(windows[0], article=True))
        elif len(windows) > 1:
            bits.append(f"{len(windows)} windows")

        if not bits:
            return ""
        if quality_mode == "guarded":
            if len(bits) > 1:
                return "There is more than just the front, but you would want to walk it yourself."
            return "Mostly the front, though I would still walk the perimeter before trusting that read."
        if quality_mode == "vague":
            if len(bits) > 1:
                return "There are other seams besides the front, but I am not mapping them cleanly for you."
            return "Front is the obvious read. If there is another seam, you would have to find it yourself."
        if bits == ["the front door"]:
            return "Mostly just the front door."
        return "There is " + _dialogue_human_join(bits) + "."

    def _keyholder_summary(self, context, *, quality=None):
        owner_place = context.get("owner_place")
        controller = context.get("controller")
        if not owner_place or not isinstance(controller, dict):
            return ""

        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, "keyholder")
        quality_mode = str(quality.get("mode", "clear")).strip().lower() or "clear"
        place_name = str(context.get("owner_place_name", "")).strip() or str(owner_place.get("name", owner_place.get("id", "the place"))).strip() or "the place"
        credential_text = self._credential_access_label(controller)
        holders = tuple(controller.get("authorized_holders", ()) or ())
        kind = str(controller.get("kind", "") or "").strip().lower()

        if not holders:
            if kind in {"auto_timer", "auto_lock"}:
                return f"Nobody local carries it. {place_name} mostly runs off the timer."
            return ""

        self_holder = _controller_holder_for_actor(controller, context.get("npc_eid"))
        named_holders = self._dialogue_controller_named_holders(controller)

        if not named_holders:
            return ""

        if quality_mode == "guarded":
            return f"Management and trusted staff carry the real {credential_text} around {place_name}."
        if quality_mode == "vague":
            return f"Someone above the floor is carrying the real {credential_text} there."

        highest = max(named_holders, key=lambda row: (row["tier"], 1 if row["role"] in {"owner", "manager"} else 0))
        others = [row for row in named_holders if row["eid"] != highest["eid"]]
        other_names = [row["name"] for row in others[:2]]

        if self_holder:
            self_role = str(self_holder.get("role", "") or "").strip().lower()
            self_tier = _int_or_default(self_holder.get("credential_tier"), 1)
            if highest["eid"] == context.get("npc_eid"):
                if other_names:
                    return f"I carry the higher-tier {credential_text} for {place_name}. {_dialogue_human_join(other_names)} also carry it."
                if self_role in {"owner", "manager"}:
                    return f"I carry the main {credential_text} for {place_name}."
                return f"I carry {credential_text} for {place_name}."
            if other_names:
                return f"I carry {credential_text} there, but {highest['name']} has the stronger clearance."
            if self_tier > 1 or self_role in {"owner", "manager"}:
                return f"I carry the important {credential_text} there."
            return f"I carry {credential_text} there."

        if highest["role"] in {"owner", "manager"}:
            shown_names = [row["name"] for row in others[:2]]
            extra = max(0, len(others) - len(shown_names))
            if not shown_names:
                return f"{highest['name']} is the one to watch for real {credential_text} at {place_name}."
            names_text = _dialogue_human_join(shown_names)
            if extra > 0:
                names_text += f", plus {extra} more"
            return f"{highest['name']} is the safer name for real {credential_text}; {names_text} also carry it around {place_name}."
        shown_names = [row["name"] for row in named_holders[:2]]
        extra = max(0, len(named_holders) - len(shown_names))
        names_text = _dialogue_human_join(shown_names)
        if extra > 0:
            names_text += f", plus {extra} more"
        return f"{names_text} carry the {credential_text} for {place_name}."

    def _security_summary(self, context, *, quality=None):
        owner_place_name = str(context.get("owner_place_name", "")).strip() or "the place"
        controller = context.get("controller")
        if not isinstance(controller, dict) or not context.get("owner_place"):
            return ""
        quality = quality if isinstance(quality, dict) else self._dialogue_pressure_intel_quality(context, "security")
        quality_mode = str(quality.get("mode", "clear")).strip().lower() or "clear"
        credential_text = _dialogue_credential_mode_text(controller.get("credential_mode"))
        security_text = _dialogue_security_tier_text(controller.get("security_tier"))
        hours_text = str(context.get("hours_text", "")).strip()
        access_level = str(context.get("access_level", "")).strip().lower()
        if context.get("guarded"):
            return f"{owner_place_name} is {credential_text} with {security_text}, and strangers get noticed fast."
        if quality_mode == "guarded":
            if access_level == "public" and hours_text:
                return f"{owner_place_name} reads tighter after hours, and strangers get noticed fast."
            return f"Strangers get read hard at {owner_place_name}, especially once regular traffic thins out."
        if quality_mode == "vague":
            return f"{owner_place_name} is not soft security. I would not test it blind."
        if access_level == "public" and hours_text:
            return f"{owner_place_name} keeps public hours {hours_text}, then turns {credential_text} with {security_text} after that."
        if hours_text:
            return f"{owner_place_name} usually runs {hours_text} and stays {credential_text} with {security_text}."
        return f"{owner_place_name} stays {credential_text} with {security_text}."

    def _concern_summary(self, context):
        if context.get("trespass_prop"):
            prop_name = str(context["trespass_prop"].get("name", context["trespass_prop"].get("id", "property"))).strip() or "that property"
            return f"People hanging around {prop_name} like they belong there."
        if context.get("guarded") and context.get("owner_place_name"):
            return f"Strangers testing the edges around {context['owner_place_name']}."
        recent_offense = context.get("recent_offense")
        if recent_offense:
            action = str(recent_offense.get("data", {}).get("action", "trouble")).replace("_", " ").strip() or "trouble"
            return f"The wrong kind of {action} around here."
        if context.get("local_source") == "opportunity" and context.get("opportunity_summary"):
            return f"People keep circling back to {context['opportunity_summary']}."
        if context.get("local_source") == "rumor" and context.get("rumor_line"):
            return str(context["rumor_line"]).strip()
        role_id = str(context.get("role_id", "")).strip().lower()
        if role_id in {"guard", "scout"}:
            return "After-hours wanderers and doors that should stay shut."
        if role_id == "thief":
            return "Sharp-eyed crowds and anyone who thinks their pockets are safe."
        if role_id == "drunk":
            return "Usually the kind of trouble you hear before you see."
        if context.get("other_name"):
            return f"{context['other_name']} stays close to more of the local trouble than they admit."
        return "Nothing sharper than the usual nerves."

    def _resolve_guard_dialogue(self, context, tactic):
        tactic = str(tactic or "").strip().lower()
        npc_eid = context["npc_eid"]
        guarded_prop = context.get("trespass_prop") or context.get("owner_place")
        npc_traits = context.get("npc_traits") or NPCTraits()
        bond = context.get("bond") or self._bond_snapshot(npc_eid) or {}
        recent_offense = context.get("recent_offense")
        pressure = _pressure_effects(self.sim)
        goodwill_mult = max(0.25, float(pressure.get("goodwill_mult", 1.0)))
        (perception, conversation, streetwise), _ = self._player_social_axes()
        trust = float(bond.get("trust", 0.0))
        closeness = float(bond.get("closeness", 0.0))
        empathy = float(getattr(npc_traits, "empathy", 0.5))
        discipline = float(getattr(npc_traits, "discipline", 0.5))
        bravery = float(getattr(npc_traits, "bravery", 0.5))

        score = 0.12
        score += (conversation / 10.0) * 0.24
        score += ((perception + streetwise) / 20.0) * 0.14
        score += trust * 0.24
        score += closeness * 0.1
        score += empathy * 0.12
        score -= discipline * 0.1
        score *= (0.82 + (goodwill_mult * 0.18))

        if recent_offense:
            score -= min(0.28, float(recent_offense.get("strength", 0.0)) * 0.4)
        if tactic == "apologize":
            score += 0.16 + (empathy * 0.06)
        elif tactic == "purpose":
            score += 0.08 + ((conversation / 10.0) * 0.08)
        elif tactic == "leave":
            score += 0.2 + (discipline * 0.03)

        if context.get("access_level") == "restricted":
            score -= 0.16 + (bravery * 0.04)
        elif context.get("access_level") == "protected":
            score -= 0.06

        severe_recent = bool(recent_offense and float(recent_offense.get("strength", 0.0)) >= 0.32)

        if tactic == "leave":
            if score >= 0.46 and not severe_recent:
                outcome = "deescalated"
                bank_id = "leave_defuse"
                pressure_delta = -2
                trust_delta = 0.015
                closeness_delta = 0.0
                grace_duration = 22
                close_dialog = True
            elif score >= 0.26:
                outcome = "wary"
                bank_id = "leave_wary"
                pressure_delta = -1
                trust_delta = 0.0
                closeness_delta = 0.0
                grace_duration = 12
                close_dialog = True
            else:
                outcome = "aggravated"
                bank_id = "leave_fail"
                pressure_delta = 1
                trust_delta = -0.02
                closeness_delta = -0.01
                grace_duration = 0
                close_dialog = True
        elif tactic == "apologize":
            if score >= 0.5 and not severe_recent:
                outcome = "deescalated"
                bank_id = "apologize_defuse"
                pressure_delta = -2
                trust_delta = 0.04
                closeness_delta = 0.015
                grace_duration = 18
                close_dialog = False
            elif score >= 0.33:
                outcome = "wary"
                bank_id = "apologize_wary"
                pressure_delta = 0
                trust_delta = 0.0
                closeness_delta = 0.0
                grace_duration = 0
                close_dialog = False
            else:
                outcome = "aggravated"
                bank_id = "apologize_fail"
                pressure_delta = 1
                trust_delta = -0.03
                closeness_delta = -0.015
                grace_duration = 0
                close_dialog = False
        else:
            if score >= 0.52 and not severe_recent:
                outcome = "deescalated"
                bank_id = "purpose_defuse"
                pressure_delta = -1
                trust_delta = 0.025
                closeness_delta = 0.01
                grace_duration = 14
                close_dialog = False
            elif score >= 0.34:
                outcome = "wary"
                bank_id = "purpose_wary"
                pressure_delta = 0
                trust_delta = 0.0
                closeness_delta = 0.0
                grace_duration = 0
                close_dialog = False
            else:
                outcome = "aggravated"
                bank_id = "purpose_fail"
                pressure_delta = 1
                trust_delta = -0.025
                closeness_delta = -0.01
                grace_duration = 0
                close_dialog = False

        line = self._say(bank_id, context, topic_id=tactic, count=self._dialogue_topic_count(npc_eid, tactic))
        self._shift_dialogue_bond(
            npc_eid,
            trust_delta=trust_delta,
            closeness_delta=closeness_delta,
            guarded=True,
        )
        if grace_duration > 0 and guarded_prop is not None:
            self._grant_guard_grace(npc_eid, guarded_prop, duration=grace_duration, tactic=tactic)
        if outcome == "deescalated":
            self._clear_guarded_memory(
                npc_eid,
                guarded_prop=guarded_prop,
                recent_offense=recent_offense,
            )
            self._clear_guarded_aggression(
                npc_eid,
                guarded_prop=guarded_prop,
            )

        self.sim.emit(Event(
            "dialogue_guard_resolution",
            eid=self.player_eid,
            npc_eid=npc_eid,
            property_id=guarded_prop.get("id") if isinstance(guarded_prop, dict) else None,
            tactic=tactic,
            outcome=outcome,
            pressure_delta=int(pressure_delta),
            grace_duration=int(grace_duration),
            close_dialog=bool(close_dialog),
        ))

        return {
            "npc_lines": [line],
            "close": bool(close_dialog),
            "guard_outcome": outcome,
        }

    def _dialogue_misstep_available(self, context, topic_id):
        if not isinstance(context, dict):
            return False
        if bool(context.get("guarded")) or not bool(context.get("human", True)):
            return False
        npc_eid = context.get("npc_eid")
        if npc_eid is None:
            return False
        topic_id = str(topic_id or "").strip().lower()
        total_asked = self._dialogue_total_topics_asked(npc_eid)
        missteps = self._dialogue_misstep_count(npc_eid)
        tone = str(context.get("tone", "neutral")).strip().lower() or "neutral"
        if topic_id == "weird":
            return total_asked >= 2
        if topic_id == "pry":
            return total_asked >= 3 or missteps >= 1 or tone == "wary"
        if topic_id == "insult":
            return total_asked >= 4 or self._dialogue_topic_count(npc_eid, "pry") > 0 or missteps >= 1 or tone == "wary"
        return False

    def _emit_dialogue_offended(self, npc_eid, *, context_id, perceived, offense_score):
        if npc_eid is None or perceived <= 0.0 or offense_score <= 0:
            return
        self.sim.emit(Event(
            "npc_offended",
            npc_eid=npc_eid,
            offender_eid=self.player_eid,
            action="talk",
            context=str(context_id or "dialogue").strip().lower(),
            offense_score=int(offense_score),
            offense_tier=_offense_tier(offense_score),
            perceived=round(float(perceived), 3),
        ))

    def _resolve_social_misstep(self, context, tactic, *, ask_count=1):
        tactic = str(tactic or "").strip().lower()
        npc_eid = context["npc_eid"]
        npc_traits = context.get("npc_traits") or NPCTraits()
        bond = context.get("bond") or self._bond_snapshot(npc_eid) or {}
        tone = str(context.get("tone", "neutral")).strip().lower() or "neutral"
        pressure_tier = str(context.get("pressure_tier", "low")).strip().lower() or "low"
        empathy = float(getattr(npc_traits, "empathy", 0.5))
        discipline = float(getattr(npc_traits, "discipline", 0.5))
        bravery = float(getattr(npc_traits, "bravery", 0.5))
        trust = float(bond.get("trust", 0.0))
        closeness = float(bond.get("closeness", 0.0))
        (_perception, conversation, _streetwise), _ = self._player_social_axes()
        conversation = float(conversation)

        total_asked = self._dialogue_total_topics_asked(npc_eid)
        misstep_count = max(0, self._dialogue_misstep_count(npc_eid) - 1)
        score = 0.22
        score += trust * 0.34
        score += closeness * 0.18
        score += empathy * 0.16
        score += (conversation / 10.0) * 0.08
        score -= discipline * 0.12
        score -= bravery * 0.08
        score -= max(0.0, float(total_asked - 2) * 0.028)
        score -= float(misstep_count) * 0.14
        if tone == "wary":
            score -= 0.08
        if pressure_tier == "medium":
            score -= 0.03
        elif pressure_tier == "high":
            score -= 0.07

        bank_id = ""
        outcome = ""
        trust_delta = 0.0
        closeness_delta = 0.0
        close_dialog = False
        perceived = 0.0
        offense_score = 0

        if tactic == "weird":
            score += 0.08
            if score >= 0.56:
                bank_id = "weird_soft"
                outcome = "soft"
                trust_delta = -0.005
                closeness_delta = 0.0
            elif score >= 0.3:
                bank_id = "weird_wary"
                outcome = "wary"
                trust_delta = -0.02
                closeness_delta = -0.01
                perceived = 0.42
                offense_score = 10
            else:
                bank_id = "weird_fail"
                outcome = "fail"
                trust_delta = -0.05
                closeness_delta = -0.03
                close_dialog = True
                perceived = 0.6
                offense_score = 18
        elif tactic == "pry":
            score -= 0.04
            if score >= 0.6:
                bank_id = "pry_soft"
                outcome = "soft"
                trust_delta = -0.015
                closeness_delta = -0.01
            elif score >= 0.36:
                bank_id = "pry_wary"
                outcome = "wary"
                trust_delta = -0.035
                closeness_delta = -0.02
                perceived = 0.58
                offense_score = 18
            else:
                bank_id = "pry_fail"
                outcome = "fail"
                trust_delta = -0.07
                closeness_delta = -0.04
                close_dialog = True
                perceived = 0.78
                offense_score = 28
        else:
            score -= 0.18
            if score >= 0.68:
                bank_id = "insult_soft"
                outcome = "soft"
                trust_delta = -0.03
                closeness_delta = -0.02
                perceived = 0.5
                offense_score = 16
            elif score >= 0.44:
                bank_id = "insult_wary"
                outcome = "wary"
                trust_delta = -0.06
                closeness_delta = -0.035
                perceived = 0.72
                offense_score = 28
            else:
                bank_id = "insult_fail"
                outcome = "fail"
                trust_delta = -0.1
                closeness_delta = -0.06
                close_dialog = True
                perceived = 0.94
                offense_score = 40

        line = self._dialogue_misstep_reaction_line(
            context,
            tactic,
            ask_count=ask_count,
            outcome=outcome,
        ) or self._say(bank_id, context, topic_id=tactic, count=ask_count)
        self._shift_dialogue_bond(
            npc_eid,
            trust_delta=trust_delta,
            closeness_delta=closeness_delta,
            guarded=False,
        )
        self._emit_dialogue_offended(
            npc_eid,
            context_id=f"dialogue_{tactic}",
            perceived=perceived,
            offense_score=offense_score,
        )
        return {
            "npc_lines": [line],
            "close": bool(close_dialog),
            "social_misstep": tactic,
        }

    def _say(self, bank_id, context, *, topic_id="", count=0, salt="", **slots):
        return choose_dialogue_line(
            bank_id,
            seed=self.sim.seed,
            npc_eid=context["npc_eid"],
            topic_id=topic_id,
            count=count,
            salt=salt,
            style_profile=context.get("speech_style"),
            **slots,
        )

    def _dialogue_misstep_reaction_line(self, context, tactic, *, ask_count, outcome):
        tactic = str(tactic or "").strip().lower()
        outcome = str(outcome or "").strip().lower()
        if tactic not in self.MISSTEP_TOPICS or not outcome:
            return ""
        return _dialogue_topic_player_reaction_line(
            tactic,
            seed=self.sim.seed,
            npc_eid=context.get("npc_eid"),
            count=ask_count,
            outcome=outcome,
            context=context,
        )

    def _dialogue_initiative_line(self, context, topic_id):
        topic_id = str(topic_id or "").strip().lower()
        if bool(context.get("guarded")) or topic_id in self.MISSTEP_TOPICS:
            return ""
        npc_eid = context.get("npc_eid")
        if npc_eid is None:
            return ""
        ask_count = self._dialogue_topic_count(npc_eid, topic_id)
        if ask_count != 1:
            return ""

        tone = str(context.get("tone", "neutral")).strip().lower() or "neutral"
        pressure_tier = str(context.get("pressure_tier", "low")).strip().lower() or "low"
        bond = context.get("bond") or self._bond_snapshot(npc_eid) or {}
        npc_traits = context.get("npc_traits") or NPCTraits()
        trust = float(bond.get("trust", 0.0))
        closeness = float(bond.get("closeness", 0.0))
        empathy = float(getattr(npc_traits, "empathy", 0.5))

        if topic_id == "name":
            if tone == "wary" and trust < 0.34:
                return ""
            return self._say("initiative_name", context, topic_id=topic_id, count=ask_count, salt="initiative")

        bank_map = {
            "history": "initiative_history",
            "job": "initiative_job",
            "workplace": "initiative_workplace",
            "organization": "initiative_organization",
            "people": "initiative_people",
            "local": "initiative_local",
            "concern": "initiative_concern",
            "contacts": "initiative_contacts",
            "introduction": "initiative_introduction",
        }
        bank_id = bank_map.get(topic_id)
        if not bank_id:
            return ""

        chance = {
            "history": 0.14,
            "job": 0.22,
            "workplace": 0.13,
            "organization": 0.13,
            "people": 0.17,
            "local": 0.2,
            "concern": 0.14,
            "contacts": 0.18,
            "introduction": 0.16,
        }.get(topic_id, 0.0)
        chance += trust * 0.18
        chance += closeness * 0.08
        chance += empathy * 0.08
        if tone == "friendly":
            chance += 0.08
        elif tone == "wary":
            chance -= 0.12
        if pressure_tier == "medium":
            chance -= 0.05
        elif pressure_tier == "high":
            chance -= 0.1
        chance = max(0.0, min(0.62, chance))
        if chance <= 0.0:
            return ""
        roll = random.Random(
            f"{self.sim.seed}:dialogue-initiative:{npc_eid}:{topic_id}:{ask_count}:{self._dialogue_total_topics_asked(npc_eid)}"
        ).random()
        if roll > chance:
            return ""
        return self._say(bank_id, context, topic_id=topic_id, count=ask_count, salt="initiative")

    def _apply_dialogue_initiative(self, context, topic_id, response):
        response = dict(response or {})
        if response.get("close") or response.get("open_trade"):
            return response
        initiative = self._dialogue_initiative_line(context, topic_id)
        if not initiative:
            return response
        npc_lines = list(response.get("npc_lines", ()) or ())
        npc_lines.append(initiative)
        response["npc_lines"] = npc_lines
        return response

    def _dialogue_tutorial_hint(self, context):
        pressure_tier = str(context.get("pressure_tier", "low")).strip().lower()
        if pressure_tier in {"medium", "high"}:
            return "Common topics unlock follow-ups as you talk. Heat is up, favors may stay cautious, and repeating yourself or pushing too hard can sour the conversation."
        return "Common topics unlock follow-ups as you talk. New branches show with +, and repeating yourself or pushing too hard can sour the conversation."

    def _dialogue_status_hint(self, context):
        if bool(context.get("peaceful_orders_only")):
            return "They have surrendered. Keep it simple: move them, leave them, or end it."
        if bool(context.get("door_answering")):
            mood = str(context.get("door_answer_mood", "neutral") or "neutral").strip().lower() or "neutral"
            if mood == "hostile":
                return "They answered the knock, but only barely. Say what you need or step away."
            if mood == "irritated":
                return "They came to the door annoyed. Keep it short and to the point."
            if bool(context.get("door_answer_services")):
                return "They are willing to handle a little after-hours business from the doorway."
            return "They answered the door. Stick to the reason you knocked."
        tone = str(context.get("tone", "neutral")).strip().lower() or "neutral"
        pressure_tier = str(context.get("pressure_tier", "low")).strip().lower() or "low"
        if bool(context.get("guarded")):
            return "They are not in a friendly mood. Keep it clean or back out."
        if pressure_tier == "high":
            return "They are talking, but heat has them tight. One bad question could shut this down."
        if pressure_tier == "medium":
            return "They seem willing enough, but the heat is keeping them careful about names and favors."
        bond = context.get("bond") or self._bond_snapshot(context.get("npc_eid")) or {}
        trust = float(bond.get("trust", 0.0))
        closeness = float(bond.get("closeness", 0.0))
        if tone == "friendly":
            return "They seem comfortable. A thoughtful follow-up should land better than a hard push."
        if tone == "wary":
            return "They are answering, but only just. Stay light or they may close off."
        if trust >= 0.58 or closeness >= 0.56:
            return "They seem open enough to volunteer a little if you give them something real to respond to."
        return "They are talking, but you still need a reason for the sharper questions."

    def _dialogue_hint_text(self, context, *, new_topic_labels=None):
        if bool(context.get("peaceful_orders_only")):
            return "They are complying for now. Give a peaceful order or back out."
        npc_eid = context.get("npc_eid")
        opened_count = 0
        total_asked = 0
        if npc_eid is not None:
            memory = self._dialogue_memory(npc_eid)
            opened_count = max(0, int(memory.get("opened_count", 0)))
            total_asked = self._dialogue_total_topics_asked(npc_eid)
        early_tutorial = opened_count <= 1 and total_asked <= 4
        if new_topic_labels:
            joined = ", ".join(str(label).strip() for label in new_topic_labels if str(label).strip())
            if not joined:
                return self._dialogue_tutorial_hint(context) if early_tutorial else self._dialogue_status_hint(context)
            if early_tutorial:
                return f"New topics: {joined}."
            tone = str(context.get("tone", "neutral")).strip().lower() or "neutral"
            pressure_tier = str(context.get("pressure_tier", "low")).strip().lower() or "low"
            if pressure_tier in {"medium", "high"}:
                lead = "Even cautious, they gave you a little more."
            elif tone == "friendly":
                lead = "They are warming to the conversation."
            elif tone == "wary":
                lead = "You got a little more out of them."
            else:
                lead = "That got them talking."
            return f"{lead} New topics: {joined}."
        if early_tutorial:
            return self._dialogue_tutorial_hint(context)
        return self._dialogue_status_hint(context)

    def _dialogue_player_line(self, topic_label):
        return f'You: "{str(topic_label).strip()}"'

    def _dialogue_npc_line(self, npc_name, text):
        text = str(text or "").strip()
        if not text:
            return ""
        return f'{npc_name}: "{text}"'

    def _door_answer_allowed_topics(self, context):
        if not bool(context.get("door_answering")):
            return set()
        mood = str(context.get("door_answer_mood", "neutral") or "neutral").strip().lower() or "neutral"
        allowed = {"bye"}
        if mood == "hostile":
            allowed.update({"purpose", "apologize", "leave"})
            return allowed
        allowed.update({"name", "job", "owner", "hours", "purpose", "apologize", "leave"})
        if context.get("workplace_prop"):
            allowed.add("workplace")
        if context.get("service_summary"):
            allowed.add("services")
        if context.get("trade_available"):
            allowed.add("trade")
        if mood == "friendly":
            allowed.add("contacts")
        return allowed

    def _dialogue_opening_lines(self, context):
        memory = self._dialogue_memory(context["npc_eid"])
        open_count = max(0, int(memory.get("opened_count", 0)))
        if bool(context.get("peaceful_orders_only")):
            return [
                self._dialogue_npc_line(
                    context["npc_name"],
                    "Okay. I dropped it. Just tell me where you want me.",
                )
            ]
        if bool(context.get("door_answering")):
            mood = str(context.get("door_answer_mood", "neutral") or "neutral").strip().lower() or "neutral"
            if mood == "hostile":
                first = "It's closed. Say what you need and keep it short."
            elif mood == "irritated":
                first = "You got me to the door. Make it quick."
            elif mood == "friendly":
                first = "We're closed, but if this is quick I can help from the doorway."
            else:
                first = "We're shut, but I'm listening. What do you need?"
            lines = [self._dialogue_npc_line(context["npc_name"], first)]
            if bool(context.get("door_answer_services")) and context.get("service_summary"):
                lines.append(
                    self._dialogue_npc_line(
                        context["npc_name"],
                        f"If you just need {context['service_summary']}, I can handle that from here.",
                    )
                )
            elif bool(context.get("door_answer_hours")) and context.get("hours_text"):
                lines.append(
                    self._dialogue_npc_line(
                        context["npc_name"],
                        f"If you're checking hours, it's {self._dialogue_hours_summary(context)}.",
                    )
                )
            return [line for line in lines if line]
        if context.get("guarded"):
            first = self._say(
                "greet_guarded",
                context,
                topic_id="greet",
                count=open_count,
                npc_name=context["npc_name"],
            )
            lines = [self._dialogue_npc_line(context["npc_name"], first)]
            if context.get("trespass_prop"):
                prop_name = str(context["trespass_prop"].get("name", context["trespass_prop"].get("id", "property"))).strip() or "property"
                lines.append(self._dialogue_npc_line(context["npc_name"], f"You should not be hanging around {prop_name}."))
            elif context.get("recent_offense"):
                action = str(context["recent_offense"].get("data", {}).get("action", "trouble")).replace("_", " ").strip() or "trouble"
                lines.append(self._dialogue_npc_line(context["npc_name"], f"I still remember your {action}."))
            return [line for line in lines if line]
        if context.get("intro_source_name") and open_count <= 1:
            bank_id = "greet_introduced"
        elif context.get("tone") == "friendly":
            bank_id = "greet_friendly"
        elif context.get("tone") == "wary":
            bank_id = "greet_wary"
        else:
            bank_id = "greet_neutral"
        first = self._say(
            bank_id,
            context,
            topic_id="greet",
            count=open_count,
            npc_name=context["npc_name"],
            intro_source_name=context.get("intro_source_name", "someone"),
        )
        lines = [self._dialogue_npc_line(context["npc_name"], first)]
        for shaped_line in _shaped_opening_lines(context, limit=1):
            formatted = self._dialogue_npc_line(context["npc_name"], shaped_line)
            if formatted and formatted not in lines:
                lines.append(formatted)
        return [line for line in lines if line]

    def _available_dialog_topics(self, context):
        available = []
        unlocked = set(self._dialogue_memory(context["npc_eid"])["unlocked_topics"])
        door_topics = self._door_answer_allowed_topics(context)
        guarded_only = {"purpose", "apologize", "leave"}
        peaceful_orders_only = bool(context.get("peaceful_orders_only"))
        peaceful_topics = {
            "backup_orders",
            "backup_follow",
            "backup_hold",
            "backup_goto_wait",
            "backup_wait_return",
            "bye",
        }
        for topic_id in _ordered_dialogue_topic_ids():
            if peaceful_orders_only and topic_id not in peaceful_topics:
                continue
            if topic_id in self.MISSTEP_TOPICS:
                if not self._dialogue_misstep_available(context, topic_id):
                    continue
            elif not (peaceful_orders_only and topic_id in peaceful_topics) and topic_id not in self.ROOT_TOPICS and topic_id not in unlocked and topic_id not in door_topics:
                continue
            if door_topics and topic_id not in door_topics:
                continue
            if topic_id in self.SERVICE_LOCATOR_TOPICS and not self._service_locator_topic_available(context, topic_id):
                continue
            if topic_id in guarded_only and not context.get("guarded"):
                continue
            if topic_id == "trade" and not context.get("trade_available"):
                continue
            if topic_id == "routine" and not self._routine_summary(context):
                continue
            if topic_id == "workplace" and not context.get("workplace_prop"):
                continue
            if topic_id == "organization" and not self._organization_summary(context):
                continue
            if topic_id == "supervisor" and not self._supervisor_summary(context):
                continue
            if topic_id == "coworkers" and not self._coworker_summary(context):
                continue
            if topic_id == "people" and not self._people_summary(context):
                continue
            if topic_id == "where_place" and not self._where_place_summary(context):
                continue
            if topic_id == "hire" and not context.get("player_business_hire_option"):
                continue
            if topic_id == "hire_manager" and not context.get("player_business_hire_manager_option"):
                continue
            if topic_id == "hire_staff" and not context.get("player_business_hire_staff_option"):
                continue
            if topic_id in {"hire_manager", "hire_staff"} and len(tuple(context.get("player_business_hire_roles", ()) or ())) <= 1:
                continue
            if topic_id == "fire" and not context.get("player_business_fire_option"):
                continue
            if topic_id == "introduction" and not self._introduction_target(context):
                continue
            if topic_id in {"services", "hours", "owner"} and not context.get("owner_place"):
                continue
            if topic_id == "security" and not self._security_summary(context):
                continue
            if topic_id == "access" and not self._access_summary(context):
                continue
            if topic_id == "entry" and not self._entry_summary(context):
                continue
            if topic_id == "keyholder" and not self._keyholder_summary(context):
                continue
            if topic_id == "weak_point" and not self._weak_point_summary(context):
                continue
            if topic_id == "history" and not self._history_summary(context):
                continue
            if topic_id == "concern" and not self._concern_summary(context):
                continue
            if topic_id == "detail" and not context.get("has_local_detail"):
                continue
            if topic_id == "opportunities" and not (self._opportunity_summary(context) or self._objective_summary(context, 1)):
                continue
            if topic_id == "fallout" and not context.get("fallout_available"):
                continue
            if topic_id == "contract" and not context.get("contract_kill_offer"):
                continue
            if topic_id == "side_job" and not context.get("side_job_available"):
                continue
            if topic_id == "payoff" and not context.get("payoff_available"):
                continue
            if topic_id == "fence" and not context.get("fence_available"):
                continue
            if topic_id == "hire_runner" and not context.get("hire_runner_available"):
                continue
            if topic_id == "backup_orders" and not context.get("backup_orders_available"):
                continue
            if topic_id in {"backup_follow", "backup_hold", "backup_distract"} and not context.get("backup_orders_available"):
                continue
            if topic_id == "backup_kill" and not context.get("backup_kill_available"):
                continue
            if topic_id == "objective" and not self._objective_summary(context, 1):
                continue
            if topic_id == "angle" and not self._angle_summary(context, 1):
                continue
            if topic_id == "risk" and not self._risk_summary(context, 1):
                continue
            if topic_id == "attention" and not self._attention_summary(context, 1):
                continue
            if topic_id == "vouch" and not context.get("vouch_place"):
                continue
            available.append({"id": topic_id, "label": _dialogue_topic_label(topic_id, context=context)})
        return self._augment_repeat_dialogue_rows(context, available)

    def _open_dialogue(self, context):
        memory = self._dialogue_memory(context["npc_eid"])
        state = self._dialog_ui_state()
        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "open": True,
            "kind": "conversation",
            "npc_eid": context["npc_eid"],
            "property_id": None,
            "title": f"Conversation: {context['npc_name']}",
            "subtitle": context.get("subtitle", ""),
            "transcript": self._dialogue_opening_lines(context),
            "topics": self._available_dialog_topics(context),
            "selected_index": 0,
            "scroll": 0,
            "hint": self._dialogue_hint_text(context),
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
            "backup_cursor_mark": None,
            "backup_cursor_pending_topic": "",
        })
        memory["opened_count"] = max(0, int(memory.get("opened_count", 0))) + 1
        memory["last_tick"] = int(self.sim.tick)
        return state

    def _hold_dialog_for_ack(self):
        state = self._dialog_ui_state()
        state.update({
            "topics": [],
            "selected_index": 0,
            "hint": "Conversation over. Press Space to close.",
            "new_topic_ids": [],
            "close_pending": True,
            "machine_action": None,
            "backup_cursor_pending_topic": "",
        })
        return state

    def _close_dialog(self):
        state = self._dialog_ui_state()
        self.sim.set_time_paused(False, reason="dialog")
        state.update({
            "open": False,
            "kind": "conversation",
            "npc_eid": None,
            "property_id": None,
            "title": "Conversation",
            "subtitle": "",
            "transcript": [],
            "topics": [],
            "selected_index": 0,
            "scroll": 0,
            "hint": "",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
            "backup_cursor_mark": None,
            "backup_cursor_pending_topic": "",
        })
        return state

    def _introduction_context_text(self, lead):
        if not isinstance(lead, dict):
            return ""
        relation_text = str(lead.get("relation_text", "")).strip()
        career_text = str(lead.get("career_text", "")).strip()
        place_name = str(lead.get("place_name", "")).strip()
        place_role = str(lead.get("place_role", "")).strip().lower()

        if relation_text and career_text and place_name and place_role == "workplace":
            return f"my {relation_text} who does {career_text} work at {place_name}"
        if relation_text and place_name and place_role == "workplace":
            return f"my {relation_text} over at {place_name}"
        if relation_text and place_name and place_role == "home":
            return f"my {relation_text} from {place_name}"
        if career_text and place_name and place_role == "workplace":
            return f"someone who does {career_text} work at {place_name}"
        if relation_text:
            return f"my {relation_text}"
        if place_name:
            return f"someone around {place_name}"
        return "someone worth meeting"

    def _offer_introduction(self, context):
        if context.get("guarded"):
            return None
        lead = self._introduction_target(context)
        if not lead:
            return None
        standing = float(context.get("contact_standing", 0.0))
        if standing < 0.44:
            return None
        if self._pressure_contact_blocked(context, "introduction"):
            return None
        if float(lead.get("score", 0.0)) < 0.36 and standing < 0.62:
            return None

        changed = self._remember_player_person_contact(
            lead.get("eid"),
            source_eid=context["npc_eid"],
            relation_kind=lead.get("relation_kind"),
            standing=standing,
            property_id=lead.get("property_id"),
            introduced=True,
            benefits={"known_name"},
        )
        if changed:
            self.sim.emit(Event(
                "contact_learned",
                eid=self.player_eid,
                npc_eid=context["npc_eid"],
                referred_eid=lead.get("eid"),
                referred_name=lead.get("name"),
                relation_kind=lead.get("relation_kind"),
                property_id=lead.get("property_id"),
                contact_kind="introduction",
                standing=standing,
                introduced=True,
                benefits=("known_name",),
            ))

        return {
            "lead": lead,
            "standing": standing,
            "newly_learned": bool(changed),
            "contact_context": self._introduction_context_text(lead),
        }

    def _dialogue_contact_response(self, context, *, vouch=False):
        topic_id = "vouch" if vouch else "contacts"
        if context.get("guarded"):
            bank_id = "contacts_hard_no"
            return self._say(bank_id, context, topic_id=topic_id, count=self._dialogue_topic_count(context["npc_eid"], topic_id), npc_name=context["npc_name"])
        if self._pressure_contact_blocked(context, "vouch" if vouch else "contact"):
            bank_id = self._pressure_contact_bank("vouch_caution_no" if vouch else "contacts_caution_no", context)
            return self._say(bank_id, context, topic_id=topic_id, count=self._dialogue_topic_count(context["npc_eid"], topic_id), npc_name=context["npc_name"])
        offer = self._offer_contact(
            npc_eid=context["npc_eid"],
            workplace_prop=context.get("workplace_prop"),
            owned_prop=context.get("owned_prop"),
            bond=context.get("bond"),
            rapport=context.get("rapport", 0.0),
        )
        if offer:
            prop = offer.get("prop")
            prop_name = str(prop.get("name", prop.get("id", "place"))).strip() if prop else "the place"
            if vouch:
                if self._pressure_offer_is_cautious(context, "vouch"):
                    bank_id = self._pressure_contact_bank("vouch_offer_caution", context)
                else:
                    bank_id = "vouch_offer" if self._dialogue_topic_count(context["npc_eid"], "vouch") <= 1 else "vouch_repeat"
            else:
                if self._pressure_offer_is_cautious(context, "contact"):
                    bank_id = self._pressure_contact_bank("contacts_offer_caution", context)
                else:
                    bank_id = "contacts_offer" if self._dialogue_topic_count(context["npc_eid"], "contacts") <= 1 else "contacts_repeat"
            return self._say(bank_id, context, topic_id=topic_id, count=self._dialogue_topic_count(context["npc_eid"], topic_id), npc_name=context["npc_name"], contact_place=prop_name)
        if not vouch:
            target = self._introduction_target(context)
            if target:
                if self._pressure_contact_blocked(context, "introduction"):
                    return self._say("contacts_caution_no", context, topic_id=topic_id, count=self._dialogue_topic_count(context["npc_eid"], topic_id), npc_name=context["npc_name"])
                bank_id = "contacts_person_hint" if self._dialogue_topic_count(context["npc_eid"], "contacts") <= 1 else "contacts_person_repeat"
                return self._say(
                    bank_id,
                    context,
                    topic_id=topic_id,
                    count=self._dialogue_topic_count(context["npc_eid"], topic_id),
                    contact_name=target.get("name", "someone"),
                    contact_context=self._introduction_context_text(target),
                )
        bank_id = "vouch_soft_no" if vouch else "contacts_soft_no"
        return self._say(bank_id, context, topic_id=topic_id, count=self._dialogue_topic_count(context["npc_eid"], topic_id), npc_name=context["npc_name"])

    def _resolve_dialog_topic(self, context, topic_id):
        topic_id = str(topic_id or "").strip().lower()
        npc_eid = context["npc_eid"]
        ask_count = self._dialogue_mark_topic(npc_eid, topic_id)
        self._dialogue_unlock_topics(npc_eid, *_dialogue_topic_unlocks(topic_id))
        if topic_id == "name":
            if context.get("guarded"):
                bank_id = "name_guarded"
            else:
                bank_id = "name_first" if ask_count <= 1 else "name_repeat"
            return {"npc_lines": [self._say(bank_id, context, topic_id=topic_id, count=ask_count, npc_name=context["npc_name"])]}
        if topic_id == "history":
            summary = self._history_summary(context)
            bank_id = "history" if summary else "history_none"
            return {
                "npc_lines": [
                    self._say(
                        bank_id,
                        context,
                        topic_id=topic_id,
                        count=ask_count,
                        history_summary=summary,
                    )
                ]
            }
        if topic_id == "job":
            if context.get("career_text"):
                bank_id = "job_first" if ask_count <= 1 else "job_repeat"
                return {"npc_lines": [self._say(bank_id, context, topic_id=topic_id, count=ask_count, career_text=context["career_text"])]}
            return {"npc_lines": [self._say("job_none", context, topic_id=topic_id, count=ask_count)]}
        if topic_id == "routine":
            quality = self._dialogue_pressure_intel_quality(context, topic_id)
            summary = self._routine_summary(context, quality=quality)
            bank_id = "routine" if summary else "routine_none"
            lines = [
                self._say(
                    bank_id,
                    context,
                    topic_id=topic_id,
                    count=ask_count,
                    routine_summary=summary,
                )
            ]
            prep_detail = self._dialogue_prep_detail(context, topic_id, quality=quality)
            if prep_detail:
                lines.append(prep_detail)
            return {"npc_lines": lines}
        if topic_id == "workplace":
            workplace_prop = context.get("workplace_prop")
            if workplace_prop:
                self._remember_player_property_lead(workplace_prop, source_eid=npc_eid, lead_kind="workplace", confidence=context.get("lead_confidence", 0.6))
                bank_id = "workplace_here" if context.get("workplace_here") else ("workplace_first" if ask_count <= 1 else "workplace_repeat")
                return {"npc_lines": [self._say(bank_id, context, topic_id=topic_id, count=ask_count, workplace_name=context.get("workplace_name") or context.get("owner_place_name") or "work")]}
            return {"npc_lines": [self._say("workplace_none", context, topic_id=topic_id, count=ask_count)]}
        if topic_id == "organization":
            summary = self._organization_summary(context)
            bank_id = "organization" if summary else "organization_none"
            return {
                "npc_lines": [
                    self._say(
                        bank_id,
                        context,
                        topic_id=topic_id,
                        count=ask_count,
                        organization_summary=summary,
                    )
                ]
            }
        if topic_id == "supervisor":
            summary = self._supervisor_summary(context)
            bank_id = "supervisor" if summary else "supervisor_none"
            return {
                "npc_lines": [
                    self._say(
                        bank_id,
                        context,
                        topic_id=topic_id,
                        count=ask_count,
                        supervisor_summary=summary,
                    )
                ]
            }
        if topic_id == "coworkers":
            summary = self._coworker_summary(context)
            bank_id = "coworkers" if summary else "coworkers_none"
            return {
                "npc_lines": [
                    self._say(
                        bank_id,
                        context,
                        topic_id=topic_id,
                        count=ask_count,
                        coworker_summary=summary,
                    )
                ]
            }
        if topic_id == "people":
            summary = self._people_summary(context)
            bank_id = "people" if summary else "people_none"
            return {
                "npc_lines": [
                    self._say(
                        bank_id,
                        context,
                        topic_id=topic_id,
                        count=ask_count,
                        people_summary=summary,
                    )
                ]
            }
        if topic_id == "where_place":
            summary = self._where_place_summary(context)
            referenced_prop = context.get("referenced_place_prop")
            if referenced_prop:
                lead_kind = str(context.get("referenced_place_lead_kind", "") or "").strip().lower()
                if lead_kind in {"", "contact"}:
                    lead_kind = "location"
                self._remember_player_property_lead(
                    referenced_prop,
                    source_eid=npc_eid,
                    lead_kind=lead_kind,
                    confidence=max(0.76, float(context.get("lead_confidence", 0.6)) + 0.08),
                )
            bank_id = "where_place" if summary else "where_place_none"
            return {
                "npc_lines": [
                    self._say(
                        bank_id,
                        context,
                        topic_id=topic_id,
                        count=ask_count,
                        place_location_summary=summary,
                        place_location_summary_lc=_dialogue_lower_start(summary),
                    )
                ]
            }
        if topic_id == "hire":
            option = context.get("player_business_hire_option")
            if not isinstance(option, dict):
                return {"npc_lines": ["No. I am not taking work from you right now."]}
            business_name = str(option.get("business_name", "the business")).strip() or "the business"
            hire_roles = tuple(
                str(role).strip().lower()
                for role in tuple(context.get("player_business_hire_roles", ()) or ())
                if str(role).strip()
            )
            if len(hire_roles) > 1:
                lines = [f"Maybe. Are you asking me to run {business_name} or just take shifts there?"]
                manager_preview = context.get("player_business_hire_manager_preview")
                staff_preview = context.get("player_business_hire_staff_preview")
                for preview in (manager_preview, staff_preview):
                    if isinstance(preview, dict):
                        line = str(preview.get("line", "")).strip()
                        if line and line not in lines:
                            lines.append(line)
                return {
                    "npc_lines": lines
                }
            return self._resolve_player_business_hire(context, option, npc_eid=npc_eid)
        if topic_id == "hire_manager":
            option = context.get("player_business_hire_manager_option")
            if not isinstance(option, dict):
                return {"npc_lines": ["That slot is not open right now."]}
            return self._resolve_player_business_hire(context, option, npc_eid=npc_eid)
        if topic_id == "hire_staff":
            option = context.get("player_business_hire_staff_option")
            if not isinstance(option, dict):
                return {"npc_lines": ["That slot is not open right now."]}
            return self._resolve_player_business_hire(context, option, npc_eid=npc_eid)
        if topic_id == "fire":
            option = context.get("player_business_fire_option")
            if not isinstance(option, dict):
                return {"npc_lines": ["That is not your call with me."]}
            business_name = str(option.get("business_name", "the business")).strip() or "the business"
            role = str(option.get("role", "staff") or "staff").strip().lower() or "staff"
            outcome = fire_actor_from_player_business(
                self.sim,
                self.player_eid,
                npc_eid,
                option.get("prop"),
            )
            if not isinstance(outcome, dict):
                return {"npc_lines": [f"That does not land cleanly for {business_name}."]}
            self.sim.emit(Event(
                "player_business_staff_fired",
                eid=self.player_eid,
                npc_eid=npc_eid,
                property_id=outcome.get("property_id"),
                business_name=outcome.get("business_name"),
                role=outcome.get("role"),
            ))
            self._shift_dialogue_bond(
                npc_eid,
                trust_delta=-0.14 if role == "manager" else -0.1,
                closeness_delta=-0.08 if role == "manager" else -0.06,
                guarded=False,
            )
            if role == "manager":
                line = f"Right. I am done running {business_name}."
            else:
                line = f"Understood. I will clear out of {business_name}."
            return {"npc_lines": [line], "close": True}
        if topic_id == "introduction":
            offer = self._offer_introduction(context)
            if offer:
                lead = offer.get("lead") or {}
                if self._pressure_offer_is_cautious(context, "introduction"):
                    bank_id = "introduction_offer_caution"
                else:
                    bank_id = "introduction_offer" if ask_count <= 1 else "introduction_repeat"
                return {
                    "npc_lines": [
                        self._say(
                            bank_id,
                            context,
                            topic_id=topic_id,
                            count=ask_count,
                            contact_name=lead.get("name", "someone"),
                            contact_context=offer.get("contact_context", "someone worth meeting"),
                        )
                    ]
                }
            if self._pressure_contact_blocked(context, "introduction"):
                return {"npc_lines": [self._say("introduction_caution_no", context, topic_id=topic_id, count=ask_count)]}
            return {"npc_lines": [self._say("introduction_soft_no", context, topic_id=topic_id, count=ask_count)]}
        if topic_id == "services":
            if context.get("service_summary"):
                return {"npc_lines": [self._say("services", context, topic_id=topic_id, count=ask_count, service_summary=context["service_summary"], service_summary_cap=context["service_summary_cap"])]}
            return {"npc_lines": [self._say("services_none", context, topic_id=topic_id, count=ask_count)]}
        if topic_id in self.SERVICE_LOCATOR_TOPICS:
            locator = self._service_locator_summary(context, topic_id)
            lead_prop = locator.get("lead_prop")
            if lead_prop is not None and not context.get("guarded"):
                spec = self._service_locator_spec(topic_id) or {}
                self._remember_player_property_lead(
                    lead_prop,
                    source_eid=npc_eid,
                    lead_kind=str(spec.get("lead_kind", "service")).strip().lower() or "service",
                    confidence=max(0.56, float(context.get("lead_confidence", 0.6)) - 0.02),
                )
            summary = str(locator.get("summary", "")).strip()
            service_label = str(locator.get("service_label", "service")).strip() or "service"
            bank_id = "service_locator" if summary else "service_locator_none"
            return {
                "npc_lines": [
                    self._say(
                        bank_id,
                        context,
                        topic_id=topic_id,
                        count=ask_count,
                        service_label=service_label,
                        service_locator_summary=summary,
                        service_locator_summary_lc=_dialogue_lower_start(summary),
                    )
                ]
            }
        if topic_id == "hours":
            if context.get("hours_text"):
                quality = self._dialogue_pressure_intel_quality(context, topic_id)
                lines = [
                    self._say(
                        "hours",
                        context,
                        topic_id=topic_id,
                        count=ask_count,
                        hours_text=self._dialogue_hours_summary(context, quality=quality),
                    )
                ]
                prep_detail = self._dialogue_prep_detail(context, topic_id, quality=quality)
                if prep_detail:
                    lines.append(prep_detail)
                return {"npc_lines": lines}
            return {"npc_lines": [self._say("hours_none", context, topic_id=topic_id, count=ask_count)]}
        if topic_id == "owner":
            owner_place = context.get("owner_place")
            if owner_place and not context.get("guarded"):
                self._remember_player_property_lead(owner_place, source_eid=npc_eid, lead_kind="owner", confidence=max(0.62, float(context.get("lead_confidence", 0.6)) - 0.04))
            if context.get("owner_name") and context.get("owner_source") == "owner":
                bank_id = "owner_named"
            elif context.get("owner_name") and context.get("owner_source") == "founder":
                bank_id = "owner_founder"
            elif context.get("owner_source") == "tag":
                bank_id = "owner_tag"
            else:
                bank_id = "owner_none"
            return {"npc_lines": [self._say(bank_id, context, topic_id=topic_id, count=ask_count, owner_name=context.get("owner_name", "nobody"))]}
        if topic_id == "security":
            quality = self._dialogue_pressure_intel_quality(context, topic_id)
            summary = self._security_summary(context, quality=quality)
            bank_id = "security" if summary else "security_none"
            lines = [
                self._say(
                    bank_id,
                    context,
                    topic_id=topic_id,
                    count=ask_count,
                    security_summary=summary,
                )
            ]
            prep_detail = self._dialogue_prep_detail(context, topic_id, quality=quality)
            if prep_detail:
                lines.append(prep_detail)
            return {"npc_lines": lines}
        if topic_id == "access":
            quality = self._dialogue_pressure_intel_quality(context, topic_id)
            owner_place = context.get("owner_place")
            if owner_place and not context.get("guarded"):
                self._remember_player_property_lead(
                    owner_place,
                    source_eid=npc_eid,
                    lead_kind="access",
                    confidence=max(0.28, max(0.64, float(context.get("lead_confidence", 0.6))) * float(quality.get("confidence_mult", 1.0))),
                )
            summary = self._access_summary(context, quality=quality)
            bank_id = "access" if summary else "access_none"
            lines = [
                self._say(
                    bank_id,
                    context,
                    topic_id=topic_id,
                    count=ask_count,
                    access_summary=summary,
                )
            ]
            prep_detail = self._dialogue_prep_detail(context, topic_id, quality=quality)
            if prep_detail:
                lines.append(prep_detail)
            return {"npc_lines": lines}
        if topic_id == "entry":
            quality = self._dialogue_pressure_intel_quality(context, topic_id)
            owner_place = context.get("owner_place")
            if owner_place and not context.get("guarded"):
                self._remember_player_property_lead(
                    owner_place,
                    source_eid=npc_eid,
                    lead_kind="entry",
                    confidence=max(0.28, max(0.62, float(context.get("lead_confidence", 0.6)) - 0.02) * float(quality.get("confidence_mult", 1.0))),
                )
            summary = self._entry_summary(context, quality=quality)
            bank_id = "entry" if summary else "entry_none"
            lines = [
                self._say(
                    bank_id,
                    context,
                    topic_id=topic_id,
                    count=ask_count,
                    entry_summary=summary,
                )
            ]
            prep_detail = self._dialogue_prep_detail(context, topic_id, quality=quality)
            if prep_detail:
                lines.append(prep_detail)
            return {"npc_lines": lines}
        if topic_id == "keyholder":
            quality = self._dialogue_pressure_intel_quality(context, topic_id)
            owner_place = context.get("owner_place")
            if owner_place and not context.get("guarded"):
                self._remember_player_property_lead(
                    owner_place,
                    source_eid=npc_eid,
                    lead_kind="keyholder",
                    confidence=max(0.28, max(0.66, float(context.get("lead_confidence", 0.6))) * float(quality.get("confidence_mult", 1.0))),
                )
            summary = self._keyholder_summary(context, quality=quality)
            bank_id = "keyholder" if summary else "keyholder_none"
            lines = [
                self._say(
                    bank_id,
                    context,
                    topic_id=topic_id,
                    count=ask_count,
                    keyholder_summary=summary,
                )
            ]
            prep_detail = self._dialogue_prep_detail(context, topic_id, quality=quality)
            if prep_detail:
                lines.append(prep_detail)
            return {"npc_lines": lines}
        if topic_id == "weak_point":
            quality = self._dialogue_pressure_intel_quality(context, topic_id)
            owner_place = context.get("owner_place")
            if owner_place and not context.get("guarded"):
                self._remember_player_property_lead(
                    owner_place,
                    source_eid=npc_eid,
                    lead_kind="security",
                    confidence=max(0.28, max(0.64, float(context.get("lead_confidence", 0.6)) - 0.01) * float(quality.get("confidence_mult", 1.0))),
                )
            summary = self._weak_point_summary(context, quality=quality)
            bank_id = "weak_point" if summary else "weak_point_none"
            lines = [
                self._say(
                    bank_id,
                    context,
                    topic_id=topic_id,
                    count=ask_count,
                    weak_point_summary=summary,
                    weak_point_summary_lc=_dialogue_lower_start(summary),
                )
            ]
            prep_detail = self._dialogue_prep_detail(context, topic_id, quality=quality)
            if prep_detail and prep_detail != summary:
                lines.append(prep_detail)
            return {"npc_lines": lines}
        if topic_id in {"purpose", "apologize", "leave"}:
            return self._resolve_guard_dialogue(context, topic_id)
        if topic_id == "local":
            shaped_line = _shaped_local_line(context)
            if shaped_line:
                line = shaped_line
            elif context.get("local_source") == "scene_event":
                self._learn_scene_followup(context, source="npc_dialogue_scene_local")
                line = (
                    str(context.get("scene_local_line", "")).strip()
                    or str(context.get("detail_line", "")).strip()
                    or "This rush is tied to something else moving nearby."
                )
            elif context.get("local_source") == "rumor":
                line = self._say("local_rumor", context, topic_id=topic_id, count=ask_count, rumor_line=context["rumor_line"], rumor_line_lc=_dialogue_lower_start(context["rumor_line"]))
            elif context.get("local_source") == "opportunity":
                quality = self._dialogue_pressure_intel_quality(context, topic_id)
                summary = self._opportunity_summary(context, quality=quality)
                detail = (
                    self._cycled_dialogue_line(self._opportunity_angle_lines(context, quality=quality, include_final_operation=False), 1)
                    or self._cycled_dialogue_line(self._opportunity_risk_lines(context, quality=quality, include_final_operation=False), 1)
                    or summary
                )
                self._learn_dialogue_opportunity(
                    context,
                    source="npc_dialogue_local",
                    confidence_mult=float(quality.get("confidence_mult", 1.0)),
                )
                line = self._say("local_opportunity", context, topic_id=topic_id, count=ask_count, opportunity_summary=summary)
                self.sim.emit(Event("dialogue_opportunity_hint", eid=self.player_eid, npc_eid=npc_eid, summary=summary, detail=detail))
            elif context.get("other_name"):
                line = self._say("local_other_bond", context, topic_id=topic_id, count=ask_count, other_name=context["other_name"])
            else:
                line = self._say("local_none", context, topic_id=topic_id, count=ask_count)
            return {"npc_lines": [line]}
        if topic_id == "concern":
            shaped_line = _shaped_concern_line(context)
            if shaped_line:
                return {"npc_lines": [shaped_line]}
            summary = self._concern_summary(context)
            bank_id = "concern" if summary else "concern_none"
            return {
                "npc_lines": [
                    self._say(
                        bank_id,
                        context,
                        topic_id=topic_id,
                        count=ask_count,
                        concern_summary=summary,
                    )
                ]
            }
        if topic_id == "detail":
            detail_line = context.get("detail_line")
            if context.get("local_source") == "scene_event":
                self._learn_scene_followup(context, source="npc_dialogue_scene_detail")
                detail_line = (
                    str(context.get("scene_detail_line", "")).strip()
                    or str(detail_line or "").strip()
                    or "The block is pulling toward another stop later."
                )
                return {"npc_lines": [detail_line]}
            if context.get("local_source") == "opportunity":
                detail_line = (
                    self._cycled_dialogue_line(self._opportunity_angle_lines(context, include_final_operation=False), 1)
                    or self._cycled_dialogue_line(self._opportunity_risk_lines(context, include_final_operation=False), 1)
                    or self._opportunity_summary(context)
                )
            if context.get("local_source") == "opportunity" and detail_line:
                line = self._say("detail_opportunity", context, topic_id=topic_id, count=ask_count, detail_line=detail_line, detail_line_lc=_dialogue_lower_start(detail_line))
            elif detail_line:
                line = self._say("detail_rumor", context, topic_id=topic_id, count=ask_count, detail_line=detail_line, detail_line_lc=_dialogue_lower_start(detail_line))
            else:
                line = self._say("detail_none", context, topic_id=topic_id, count=ask_count)
            return {"npc_lines": [line]}
        if topic_id == "opportunities":
            quality = self._dialogue_pressure_intel_quality(context, topic_id)
            summary = self._opportunity_summary(context, quality=quality)
            bank_id = "opportunities" if summary else "opportunities_none"
            if summary:
                self._learn_dialogue_opportunity(
                    context,
                    source="npc_dialogue_opportunities",
                    confidence_mult=float(quality.get("confidence_mult", 1.0)),
                )
            if summary and ask_count <= 1:
                self.sim.emit(Event(
                    "dialogue_opportunity_hint",
                    eid=self.player_eid,
                    npc_eid=npc_eid,
                    summary=summary,
                    detail=(
                        self._cycled_dialogue_line(self._opportunity_angle_lines(context, quality=quality, include_final_operation=False), 1)
                        or self._cycled_dialogue_line(self._opportunity_risk_lines(context, quality=quality, include_final_operation=False), 1)
                    ),
                ))
            return {
                "npc_lines": [
                    self._say(
                        bank_id,
                        context,
                        topic_id=topic_id,
                        count=ask_count,
                        opportunity_summary=summary,
                        opportunity_summary_lc=_dialogue_lower_start(summary),
                    )
                ]
            }
        if topic_id == "fallout":
            quality = self._dialogue_pressure_intel_quality(context, topic_id)
            row = self._dialogue_selected_fallout_row(context, ask_count=ask_count)
            summary = self._fallout_summary(row, context, quality=quality)
            bank_id = "fallout" if summary else "fallout_none"
            if row:
                self._learn_dialogue_opportunity_row(
                    row,
                    source="npc_dialogue_fallout",
                    confidence_mult=float(quality.get("confidence_mult", 1.0)),
                )
                self.sim.emit(Event(
                    "dialogue_opportunity_hint",
                    eid=self.player_eid,
                    npc_eid=npc_eid,
                    summary=summary,
                    detail=str(row.get("summary", "")).strip() or summary,
                ))
            return {
                "npc_lines": [
                    self._say(
                        bank_id,
                        context,
                        topic_id=topic_id,
                        count=ask_count,
                        fallout_summary=summary,
                        fallout_summary_lc=_dialogue_lower_start(summary),
                    )
                ]
            }
        if topic_id == "objective":
            summary = self._objective_summary(context, ask_count)
            bank_id = "objective" if summary else "objective_none"
            if summary:
                quality = self._dialogue_pressure_intel_quality(context, topic_id)
                self._learn_dialogue_opportunity(
                    context,
                    source="npc_dialogue_objective",
                    confidence_mult=float(quality.get("confidence_mult", 1.0)),
                )
            return {
                "npc_lines": [
                    self._say(
                        bank_id,
                        context,
                        topic_id=topic_id,
                        count=ask_count,
                        objective_summary=summary,
                        objective_summary_lc=_dialogue_lower_start(summary),
                    )
                ]
            }
        if topic_id == "angle":
            quality = self._dialogue_pressure_intel_quality(context, topic_id)
            summary = self._angle_summary(context, ask_count)
            bank_id = "angle" if summary else "angle_none"
            if summary:
                self._learn_dialogue_opportunity(
                    context,
                    source="npc_dialogue_angle",
                    confidence_mult=float(quality.get("confidence_mult", 1.0)),
                )
            return {
                "npc_lines": [
                    self._say(
                        bank_id,
                        context,
                        topic_id=topic_id,
                        count=ask_count,
                        angle_summary=summary,
                        angle_summary_lc=_dialogue_lower_start(summary),
                    )
                ]
            }
        if topic_id == "risk":
            quality = self._dialogue_pressure_intel_quality(context, topic_id)
            summary = self._risk_summary(context, ask_count)
            bank_id = "risk" if summary else "risk_none"
            if summary:
                self._learn_dialogue_opportunity(
                    context,
                    source="npc_dialogue_risk",
                    confidence_mult=float(quality.get("confidence_mult", 1.0)),
                )
            return {
                "npc_lines": [
                    self._say(
                        bank_id,
                        context,
                        topic_id=topic_id,
                        count=ask_count,
                        risk_summary=summary,
                        risk_summary_lc=_dialogue_lower_start(summary),
                    )
                ]
            }
        if topic_id == "attention":
            summary = self._attention_summary(context, ask_count)
            bank_id = "attention" if summary else "attention_none"
            return {
                "npc_lines": [
                    self._say(
                        bank_id,
                        context,
                        topic_id=topic_id,
                        count=ask_count,
                        attention_summary=summary,
                        attention_summary_lc=_dialogue_lower_start(summary),
                    )
                ]
            }
        if topic_id in self.MISSTEP_TOPICS:
            return self._resolve_social_misstep(context, topic_id, ask_count=ask_count)
        if topic_id == "contacts":
            return {"npc_lines": [self._dialogue_contact_response(context, vouch=False)]}
        if topic_id == "vouch":
            return {"npc_lines": [self._dialogue_contact_response(context, vouch=True)]}
        if topic_id == "trade":
            if context.get("trade_context"):
                bank_id = self._pressure_contact_bank("trade_yes_caution", context) if self._pressure_offer_is_cautious(context, "trade") else "trade_yes"
                line = self._say(bank_id, context, topic_id=topic_id, count=ask_count)
                return {"npc_lines": [line], "open_trade": True, "trade_property_id": context["trade_context"].get("property_id")}
            return {"npc_lines": [self._say("trade_no", context, topic_id=topic_id, count=ask_count)]}
        if topic_id == "payoff":
            npc_eid = context.get("npc_eid")
            cost_amount = int(context.get("payoff_cost_amount", self.PAYOFF_BASE_COST))
            assets = self.sim.ecs.get(PlayerAssets).get(self.player_eid)
            # Cooldown check — if we somehow got here despite the gate, refuse politely.
            if npc_eid and self.sim.tick < self.payoff_cooldown_ticks.get(npc_eid, 0):
                return {"npc_lines": [self._say("payoff_cooldown", context, topic_id=topic_id, count=ask_count)]}
            # Corruptibility check.
            npc_traits = context.get("npc_traits") or NPCTraits()
            justice_profile = self.sim.ecs.get(JusticeProfile).get(npc_eid) if npc_eid else None
            enforce_all = bool(getattr(justice_profile, "enforce_all", False))
            corruption = float(getattr(justice_profile, "corruption", 0.0))
            discipline = float(getattr(npc_traits, "discipline", 0.5))
            tone = str(context.get("tone", "neutral")).strip().lower() or "neutral"
            incorruptible = enforce_all or (corruption < 0.25 and discipline > 0.72 and tone in {"guarded", "hostile"})
            if incorruptible:
                return {"npc_lines": [self._say("payoff_refuse_clean", context, topic_id=topic_id, count=ask_count)]}
            # Insufficient funds check.
            if assets is None or assets.credits < cost_amount:
                return {"npc_lines": [self._say("payoff_refuse_broke", context, topic_id=topic_id, count=ask_count)]}
            # Payoff accepted — deduct credits, reduce heat, set cooldown.
            assets.credits -= cost_amount
            pressure_tier = str(context.get("pressure_tier", "medium")).strip().lower()
            heat_delta = -12 if pressure_tier == "high" else -7
            _apply_pressure_delta(
                self.sim,
                delta=heat_delta,
                source="payoff",
                reason="npc_payoff",
                source_event="dialogue_payoff",
            )
            if npc_eid:
                self.payoff_cooldown_ticks[npc_eid] = self.sim.tick + self.PAYOFF_COOLDOWN_TICKS
                memory = self.sim.ecs.get(NPCMemory).get(npc_eid)
                if memory is not None:
                    memory.remember(
                        self.sim.tick,
                        "recognized",
                        strength=0.55,
                        player_eid=self.player_eid,
                        source="payoff",
                    )
            return {"npc_lines": [self._say("payoff_accept", context, topic_id=topic_id, count=ask_count, payoff_cost=context.get("payoff_cost", f"{cost_amount} credits"))]}
        if topic_id == "fence":
            npc_eid = context.get("npc_eid")
            # Cooldown check.
            if npc_eid and self.sim.tick < self.fence_cooldown_ticks.get(npc_eid, 0):
                return {"npc_lines": [self._say("fence_cooldown", context, topic_id=topic_id, count=ask_count)]}
            # Corruptibility check.
            justice_profile = self.sim.ecs.get(JusticeProfile).get(npc_eid) if npc_eid else None
            corruption = float(getattr(justice_profile, "corruption", 0.0))
            enforce_all = bool(getattr(justice_profile, "enforce_all", False))
            if enforce_all or corruption < self.FENCE_MIN_CORRUPTION:
                return {"npc_lines": [self._say("fence_decline_clean", context, topic_id=topic_id, count=ask_count)]}
            # Check inventory for illegal items.
            illegal_items = self._fence_illegal_items(self.player_eid)
            if not illegal_items:
                return {"npc_lines": [self._say("fence_decline_corrupt", context, topic_id=topic_id, count=ask_count)]}
            # Execute the fence transaction.
            payout = int(context.get("fence_payout_preview") or self._fence_payout_preview(self.player_eid))
            if payout <= 0:
                return {"npc_lines": [self._say("fence_decline_corrupt", context, topic_id=topic_id, count=ask_count)]}
            inventory = self.sim.ecs.get(Inventory).get(self.player_eid)
            if inventory:
                for entry in list(illegal_items):
                    inventory.remove_item(instance_id=entry.get("instance_id"), quantity=int(entry.get("quantity", 1)))
            assets = self.sim.ecs.get(PlayerAssets).get(self.player_eid)
            if assets:
                assets.credits += payout
            if npc_eid:
                self.fence_cooldown_ticks[npc_eid] = self.sim.tick + self.FENCE_COOLDOWN_TICKS
                self._shift_dialogue_bond(npc_eid, trust_delta=0.06, closeness_delta=0.03, guarded=False)
            self.sim.emit(Event(
                "fence_transaction",
                eid=self.player_eid,
                npc_eid=npc_eid,
                payout=payout,
                item_count=len(illegal_items),
                credits=int(getattr(assets, "credits", 0)) if assets else 0,
            ))
            return {"npc_lines": [self._say("fence_accept", context, topic_id=topic_id, count=ask_count, fence_payout=f"{payout} credits")]}
        if topic_id == "bye":
            return {"npc_lines": [self._say("farewell", context, topic_id=topic_id, count=ask_count)], "close": True}
        if topic_id == "contract":
            offer = context.get("contract_kill_offer")
            if not offer:
                return {"npc_lines": [self._say("contract_no_contract", context, topic_id=topic_id, count=ask_count)]}
            req = offer.get("requirements", {})
            target_description = str(req.get("kill_target_description") or req.get("kill_target_name") or "the target").strip()
            reward_hint = format_reward_text(offer.get("reward", {}))
            bank_id = "contract_offer" if ask_count <= 1 else "contract_repeat"
            # Mark accepted and reveal to player with confirmed intel.
            offer.setdefault("requirements", {})["player_accepted"] = True
            reveal_opportunity_to_observer(
                self.sim,
                self.player_eid,
                int(offer.get("id", 0)),
                awareness_state="confirmed",
                confidence=0.95,
                source="npc_dialogue_contract",
            )
            lines = [self._say(bank_id, context, topic_id=topic_id, count=ask_count, target_description=target_description, reward_hint=reward_hint)]
            if ask_count <= 1:
                lines.append(self._say("contract_accepted", context, topic_id=topic_id, count=ask_count))
            return {"npc_lines": lines}
        if topic_id == "side_job":
            offer = context.get("side_job_offer") or self._ensure_side_job_offer(context)
            if not offer:
                return {"npc_lines": [self._say("side_job_none", context, topic_id=topic_id, count=ask_count)]}
            issuer = offer.get("issuer", {}) if isinstance(offer.get("issuer"), dict) else {}
            favor_target = str(issuer.get("organization_name", "")).strip() or str(issuer.get("npc_name", "")).strip() or "me"
            reward_hint = format_reward_text(offer.get("reward", {}))
            side_job_summary = str(offer.get("summary", "")).strip() or "Handle the drop quietly."
            bank_id = "side_job_offer" if ask_count <= 1 else "side_job_repeat"
            lines = [
                self._say(
                    bank_id,
                    context,
                    topic_id=topic_id,
                    count=ask_count,
                    side_job_summary=side_job_summary,
                    reward_hint=reward_hint,
                    favor_target=favor_target,
                )
            ]
            if ask_count <= 1:
                lines.append(self._say("side_job_accepted", context, topic_id=topic_id, count=ask_count))
            return {"npc_lines": lines}
        if topic_id == "hire_runner":
            npc_eid = context.get("npc_eid")
            cost = int(self.CONTRACTOR_COST)
            cost_str = f"{cost} credits"
            hours_str = str(context.get("hire_runner_hours", f"{max(1, self.CONTRACTOR_DURATION // 60)} hours"))
            # If already hired for current run, just confirm.
            contractors = getattr(self.sim, "contractors", {})
            if npc_eid and contractors.get(npc_eid, {}).get("until", 0) > self.sim.tick:
                return {"npc_lines": [self._say("hire_runner_already_hired", context, topic_id=topic_id, count=ask_count)]}
            # Verify at resolution time — context may be stale.
            if not context.get("hire_runner_available"):
                justice_profile = self.sim.ecs.get(JusticeProfile).get(npc_eid) if npc_eid else None
                corruption = float(getattr(justice_profile, "corruption", 0.0))
                enforce_all = bool(getattr(justice_profile, "enforce_all", False))
                if enforce_all or corruption < self.CONTRACTOR_MIN_CORRUPTION:
                    return {"npc_lines": [self._say("hire_runner_decline_clean", context, topic_id=topic_id, count=ask_count)]}
                return {"npc_lines": [self._say("hire_runner_decline_clean", context, topic_id=topic_id, count=ask_count)]}
            # Check player funds.
            assets = self.sim.ecs.get(PlayerAssets).get(self.player_eid)
            if not assets or int(getattr(assets, "credits", 0)) < cost:
                return {"npc_lines": [self._say("hire_runner_decline_broke", context, topic_id=topic_id, count=ask_count)]}
            # Complete the hire.
            assets.credits -= cost
            now = self.sim.tick
            if not isinstance(contractors, dict):
                self.sim.contractors = {}
                contractors = self.sim.contractors
            contractors[npc_eid] = {
                "hired_tick": now,
                "until": now + self.CONTRACTOR_DURATION,
                "cost": cost,
                "job": "backup",
                "ally_eid": self.player_eid,
                "order": "passive",
            }
            if npc_eid:
                self._shift_dialogue_bond(npc_eid, trust_delta=0.08, closeness_delta=0.04, guarded=False)
                self._prime_backup_bond(npc_eid)
                self._clear_contractor_player_heat(npc_eid, self.player_eid)
            self.sim.emit(Event(
                "contractor_hired",
                eid=self.player_eid,
                npc_eid=npc_eid,
                cost=cost,
                duration=self.CONTRACTOR_DURATION,
                job="backup",
                ally_eid=self.player_eid,
                credits=int(getattr(assets, "credits", 0)),
            ))
            return {"npc_lines": [self._say("hire_runner_accept", context, topic_id=topic_id, count=ask_count, hire_runner_cost=cost_str, hire_runner_hours=hours_str)]}
        if topic_id == "backup_orders":
            return {"npc_lines": [self._say("backup_orders", context, topic_id=topic_id, count=ask_count)]}
        if topic_id in {
            "backup_follow",
            "backup_hold",
            "backup_distract",
            "backup_goto_wait",
            "backup_wait_return",
            "backup_kill",
        }:
            peaceful_orders_only = bool(context.get("peaceful_orders_only"))
            contractor = self._active_backup_contract(npc_eid)
            if contractor is None and peaceful_orders_only:
                contractor = self._active_peaceful_surrender(npc_eid, ensure=True)
            if not contractor:
                return {"npc_lines": ["They are not in a state to follow orders."]}
            positions = self.sim.ecs.get(Position)
            player_pos = positions.get(self.player_eid)
            npc_pos = positions.get(npc_eid)
            if not npc_pos:
                return {"npc_lines": []}
            if topic_id == "backup_follow":
                self._set_contractor_order(contractor, "passive")
                if peaceful_orders_only:
                    self._assign_peaceful_surrender_follow(npc_eid, self.player_eid, player_pos)
                else:
                    self._assign_contractor_backup(npc_eid, self.player_eid, player_pos, contractor)
                return {"npc_lines": [self._say("backup_follow", context, topic_id=topic_id, count=ask_count)]}
            if topic_id == "backup_hold":
                self._set_contractor_order(
                    contractor,
                    "hold",
                    target=(int(npc_pos.x), int(npc_pos.y), int(npc_pos.z)),
                )
                if peaceful_orders_only:
                    self._assign_peaceful_surrender_hold(npc_eid, contractor)
                else:
                    self._assign_contractor_hold(npc_eid, self.player_eid, player_pos, contractor)
                return {"npc_lines": [self._say("backup_hold", context, topic_id=topic_id, count=ask_count)]}
            if peaceful_orders_only and topic_id in {"backup_distract", "backup_kill"}:
                return {"npc_lines": ["They keep their hands visible and refuse anything violent."]}
            if topic_id == "backup_distract":
                distraction_target = self._distraction_waypoint(npc_pos, player_pos)
                self._set_contractor_order(
                    contractor,
                    "distraction",
                    target=distraction_target,
                    wait_ticks=int(self.CONTRACTOR_DISTRACTION_TICKS),
                )
                self._assign_contractor_distraction(npc_eid, player_pos, contractor)
                return {"npc_lines": [self._say("backup_distract", context, topic_id=topic_id, count=ask_count)]}
            if topic_id in {"backup_goto_wait", "backup_wait_return"}:
                try:
                    target = (
                        int(context.get("backup_cursor_x")),
                        int(context.get("backup_cursor_y")),
                        int(context.get("backup_cursor_z")),
                    )
                except (TypeError, ValueError):
                    return {"npc_lines": ["Mark a spot for me first."]}
                wait_ticks = int(self.CONTRACTOR_RETURN_WAIT_TICKS) if topic_id == "backup_wait_return" else 0
                self._set_contractor_order(
                    contractor,
                    "wait_return" if topic_id == "backup_wait_return" else "goto_wait",
                    target=target,
                    wait_ticks=wait_ticks,
                )
                if peaceful_orders_only:
                    self._assign_peaceful_surrender_hold(npc_eid, contractor)
                else:
                    self._assign_contractor_hold(npc_eid, self.player_eid, player_pos, contractor)
                return {
                    "npc_lines": [
                        self._say(
                            "backup_wait_return" if topic_id == "backup_wait_return" else "backup_goto_wait",
                            context,
                            topic_id=topic_id,
                            count=ask_count,
                            backup_marked_spot=context.get("backup_cursor_hint", "the mark"),
                        )
                    ]
                }
            target_eid = context.get("backup_kill_target_eid")
            if target_eid is None:
                return {"npc_lines": [self._say("backup_kill_refuse", context, topic_id=topic_id, count=ask_count)]}
            target_pos = positions.get(target_eid)
            if not target_pos or _entity_is_downed(self.sim, target_eid):
                return {"npc_lines": [self._say("backup_kill_refuse", context, topic_id=topic_id, count=ask_count)]}
            kill_terms = self._contractor_kill_terms(npc_eid, bond=context.get("bond"))
            surcharge = 0 if kill_terms.get("trusted") else int(kill_terms.get("surcharge", 0))
            if surcharge > 0:
                assets = self.sim.ecs.get(PlayerAssets).get(self.player_eid)
                if not assets or int(getattr(assets, "credits", 0)) < surcharge:
                    return {"npc_lines": [self._say("hire_runner_decline_broke", context, topic_id=topic_id, count=ask_count)]}
                assets.credits -= surcharge
            self._set_contractor_order(
                contractor,
                "kill",
                target_eid=target_eid,
                kill_surcharge=surcharge,
            )
            self._assign_contractor_kill(npc_eid, self.player_eid, player_pos, contractor)
            return {
                "npc_lines": [
                    self._say(
                        "backup_kill_trusted" if kill_terms.get("trusted") else "backup_kill_paid",
                        context,
                        topic_id=topic_id,
                        count=ask_count,
                        backup_kill_target=context.get("backup_kill_target_name", "the mark"),
                        backup_kill_cost=f"{surcharge} credits" if surcharge > 0 else "",
                    )
                ]
            }
        return {"npc_lines": []}

    def _apply_dialogue_repeat_friction(self, context, topic_id, response):
        topic_id = str(topic_id or "").strip().lower()
        response = dict(response or {})
        npc_eid = context.get("npc_eid") if isinstance(context, dict) else None
        if npc_eid is None or bool(context.get("guarded")):
            return response
        if topic_id in self.REPEAT_PRESSURE_SKIP_TOPICS or topic_id in self.MISSTEP_TOPICS:
            return response
        if response.get("open_trade"):
            return response

        ask_count = self._dialogue_topic_count(npc_eid, topic_id)
        family_count = self._dialogue_topic_family_count(npc_eid, topic_id)
        if ask_count <= 1 and family_count <= 1:
            return response

        bond = context.get("bond") or self._bond_snapshot(npc_eid) or {}
        npc_traits = context.get("npc_traits") or NPCTraits()
        tone = str(context.get("tone", "neutral")).strip().lower() or "neutral"
        pressure_tier = str(context.get("pressure_tier", "low")).strip().lower() or "low"
        empathy = float(getattr(npc_traits, "empathy", 0.5))
        discipline = float(getattr(npc_traits, "discipline", 0.5))
        trust = float(bond.get("trust", 0.0))
        closeness = float(bond.get("closeness", 0.0))
        (_perception, conversation, _streetwise), _ = self._player_social_axes()
        conversation = float(conversation)

        # Let first-pass follow-up exploration land before adjacent-family
        # pressure starts replacing the actual answer with a brush-off line.
        # We still apply a small bond cost, but distinct newly reached topics
        # should remain readable on their first ask even if the player is
        # walking a whole seam of related questions.
        pressure_count = max(ask_count, family_count)
        if ask_count <= 1:
            if pressure_count >= 2:
                trust_delta = -0.004 * float(min(6, pressure_count - 1))
                closeness_delta = -0.003 * float(min(6, pressure_count - 1))
                self._shift_dialogue_bond(
                    npc_eid,
                    trust_delta=trust_delta,
                    closeness_delta=closeness_delta,
                    guarded=False,
                )
            return response

        severity = max(0.0, float(ask_count - 2) * 0.24)
        severity += _repeat_pressure_score(ask_count=ask_count, family_count=family_count)
        severity += max(0.0, float(self._dialogue_total_topics_asked(npc_eid) - ask_count - 2) * 0.012)
        severity += float(self._dialogue_misstep_count(npc_eid)) * 0.05
        severity += discipline * 0.08
        severity -= empathy * 0.12
        severity -= trust * 0.22
        severity -= closeness * 0.08
        severity -= (conversation / 10.0) * 0.06
        if tone == "friendly":
            severity -= 0.04
        elif tone == "wary":
            severity += 0.08
        if pressure_tier == "medium":
            severity += 0.04
        elif pressure_tier == "high":
            severity += 0.08

        bonus_line = self._dialogue_repeat_bonus_line(
            context,
            topic_id,
            ask_count=ask_count,
            severity=severity,
        )
        if bonus_line:
            npc_lines = list(response.get("npc_lines", ()) or ())
            npc_lines.append(bonus_line)
            response["npc_lines"] = npc_lines
            severity = max(0.0, severity - 0.12)

        bank_id = ""
        trust_delta = 0.0
        closeness_delta = 0.0
        close_dialog = False
        perceived = 0.0
        offense_score = 0

        if pressure_count == 2 and severity < 0.34:
            trust_delta = -0.01
            closeness_delta = -0.006
        elif pressure_count == 2:
            bank_id = "repeat_soft"
            trust_delta = -0.018
            closeness_delta = -0.01
        elif pressure_count == 3 and severity < 0.72:
            bank_id = "repeat_wary"
            trust_delta = -0.035
            closeness_delta = -0.02
            perceived = 0.46
            offense_score = 12
        else:
            bank_id = "repeat_fail"
            trust_delta = -0.085 if pressure_count >= 4 else -0.07
            closeness_delta = -0.048 if pressure_count >= 4 else -0.038
            close_dialog = True
            perceived = 0.82 if pressure_count >= 4 else 0.72
            offense_score = 30 if pressure_count >= 4 else 24

        self._shift_dialogue_bond(
            npc_eid,
            trust_delta=trust_delta,
            closeness_delta=closeness_delta,
            guarded=False,
        )
        if bank_id:
            npc_lines = list(response.get("npc_lines", ()) or ())
            npc_lines.append(self._say(bank_id, context, topic_id=topic_id, count=ask_count, salt="repeat"))
            response["npc_lines"] = npc_lines
        if close_dialog:
            response["close"] = True
        self._emit_dialogue_offended(
            npc_eid,
            context_id="dialogue_repeat",
            perceived=perceived,
            offense_score=offense_score,
        )
        return response

    def _dialogue_repeat_bonus_detail(self, context, topic_id, ask_count):
        topic_id = str(topic_id or "").strip().lower()
        ask_count = max(1, int(ask_count))
        detail_line = str(context.get("detail_line", "")).strip()
        prep_detail = str(self._dialogue_prep_detail(context, topic_id)).strip()
        if topic_id == "routine":
            return prep_detail or self._weak_point_summary(context) or self._access_summary(context)
        if topic_id == "hours":
            return prep_detail or self._access_summary(context) or self._security_summary(context)
        if topic_id == "services":
            return str(context.get("hours_text", "")).strip() or self._access_summary(context)
        if topic_id == "owner":
            return self._security_summary(context) or self._keyholder_summary(context)
        if topic_id == "security":
            return prep_detail or self._keyholder_summary(context) or self._entry_summary(context) or self._access_summary(context)
        if topic_id == "access":
            return prep_detail or self._keyholder_summary(context) or self._entry_summary(context)
        if topic_id == "entry":
            return prep_detail or self._access_summary(context) or self._keyholder_summary(context)
        if topic_id == "keyholder":
            return prep_detail or self._access_summary(context) or self._security_summary(context)
        if topic_id == "weak_point":
            return prep_detail or self._entry_summary(context) or self._security_summary(context)
        if topic_id == "local":
            return detail_line or self._concern_summary(context)
        if topic_id == "concern":
            return detail_line
        if topic_id == "detail":
            return self._opportunity_summary(context) or self._concern_summary(context)
        if topic_id == "opportunities":
            return (
                self._objective_summary(context, 2)
                or self._angle_summary(context, 1)
                or self._risk_summary(context, 1)
            )
        if topic_id == "fallout":
            next_row = self._dialogue_selected_fallout_row(context, ask_count=ask_count + 1)
            return self._fallout_summary(next_row, context)
        if topic_id == "objective":
            return self._angle_summary(context, ask_count + 1) or self._risk_summary(context, 1)
        if topic_id == "angle":
            return self._risk_summary(context, ask_count + 1) or self._attention_summary(context, 1)
        if topic_id == "risk":
            return self._attention_summary(context, 1)
        if topic_id == "contacts":
            intro = self._introduction_target(context)
            if intro:
                return f"{intro.get('name', 'They')} are {self._introduction_context_text(intro)}."
            return ""
        if topic_id == "introduction":
            intro = self._introduction_target(context)
            if intro:
                return self._social_lead_sentence(intro)
            return ""
        return ""

    def _dialogue_repeat_bonus_knowledge(self, context, topic_id):
        topic_id = str(topic_id or "").strip().lower()
        npc_eid = context.get("npc_eid")
        owner_place = context.get("owner_place")
        if owner_place and topic_id in {"hours", "services", "owner", "security", "access", "entry", "keyholder"}:
            lead_kind = {
                "hours": "access",
                "services": "workplace",
                "owner": "owner",
                "security": "security",
                "access": "access",
                "entry": "entry",
                "keyholder": "keyholder",
            }.get(topic_id)
            if lead_kind:
                self._remember_player_property_lead(
                    owner_place,
                    source_eid=npc_eid,
                    lead_kind=lead_kind,
                    confidence=max(0.74, float(context.get("lead_confidence", 0.6)) + 0.08),
                )
        if topic_id in {"local", "concern", "detail", "opportunities", "objective", "angle", "risk"}:
            self._learn_dialogue_opportunity(context, source="npc_dialogue_repeat_bonus")

    def _dialogue_repeat_bonus_line(self, context, topic_id, *, ask_count, severity):
        topic_id = str(topic_id or "").strip().lower()
        ask_count = max(1, int(ask_count))
        if ask_count > 3 or severity >= 0.42:
            return ""

        npc_eid = context.get("npc_eid")
        if npc_eid is None:
            return ""

        detail = str(self._dialogue_repeat_bonus_detail(context, topic_id, ask_count)).strip()
        if not detail:
            return ""

        bond = context.get("bond") or self._bond_snapshot(npc_eid) or {}
        npc_traits = context.get("npc_traits") or NPCTraits()
        tone = str(context.get("tone", "neutral")).strip().lower() or "neutral"
        pressure_tier = str(context.get("pressure_tier", "low")).strip().lower() or "low"
        trust = float(bond.get("trust", 0.0))
        closeness = float(bond.get("closeness", 0.0))
        empathy = float(getattr(npc_traits, "empathy", 0.5))
        (_perception, conversation, streetwise), _ = self._player_social_axes()

        chance = 0.04
        chance += trust * 0.12
        chance += closeness * 0.06
        chance += empathy * 0.06
        chance += (float(conversation) / 10.0) * 0.1
        chance += (float(streetwise) / 10.0) * 0.04
        if tone == "friendly":
            chance += 0.05
        elif tone == "wary":
            chance -= 0.08
        if pressure_tier == "medium":
            chance -= 0.03
        elif pressure_tier == "high":
            chance -= 0.07
        if ask_count >= 3:
            chance -= 0.04
        chance = max(0.0, min(0.24, chance))
        if chance <= 0.0:
            return ""

        roll = random.Random(
            f"{self.sim.seed}:dialogue-repeat-bonus:{npc_eid}:{topic_id}:{ask_count}:{self._dialogue_total_topics_asked(npc_eid)}"
        ).random()
        if roll > chance:
            return ""

        self._dialogue_repeat_bonus_knowledge(context, topic_id)
        return self._say(
            "repeat_bonus",
            context,
            topic_id=topic_id,
            count=ask_count,
            salt="repeat_bonus",
            extra_detail=detail,
            extra_detail_lc=_dialogue_lower_start(detail),
        )

    def _append_dialogue_response(self, context, topic_id, response, *, previous_topic_id=""):
        state = self._dialog_ui_state()
        transcript = list(state.get("transcript", ()) or ())
        transcript.append(
            self._dialogue_player_line(
                _dialogue_topic_player_line(
                    topic_id,
                    seed=getattr(self.sim, "seed", 0),
                    npc_eid=context.get("npc_eid"),
                    count=self._dialogue_topic_count(context.get("npc_eid"), topic_id),
                    context=context,
                    previous_topic_id=previous_topic_id,
                    total_asked=self._dialogue_total_topics_asked(context.get("npc_eid")),
                )
            )
        )
        for line in response.get("npc_lines", ()) or ():
            formatted = self._dialogue_npc_line(context["npc_name"], line)
            if formatted:
                transcript.append(formatted)
        state["transcript"] = transcript

    def _emit_simple_npc_interaction(self, context):
        npc_eid = context["npc_eid"]
        lines = []
        if context.get("identity") and context["identity"].taxonomy_class != "hominid":
            lines.append(f"{context['npc_name']}#{npc_eid} watches you for a moment.")
        elif context.get("career_text"):
            lines.append(f"{context['npc_name']}#{npc_eid} is a {context['career_text']}, currently {context['state_text']}.")
        elif context.get("ai"):
            lines.append(f"{context['npc_name']}#{npc_eid} is {context['role_text']}, currently {context['state_text']}.")
        else:
            lines.append(f"{context['npc_name']}#{npc_eid} is hard to read.")
        read_line = _crime_read_summary(self.sim, self.player_eid, npc_eid, mode="talk", sentence=True)
        if read_line:
            lines.append(read_line)
        workplace_prop = context.get("workplace_prop")
        owned_prop = context.get("owned_prop")
        property_bits = []
        if workplace_prop:
            property_bits.append(_property_contact_lead(self.sim, workplace_prop, "workplace", viewer_eid=self.player_eid))
        if owned_prop and (not workplace_prop or owned_prop["id"] != workplace_prop["id"]):
            property_bits.append(_property_contact_lead(self.sim, owned_prop, "owner", viewer_eid=self.player_eid))
        if property_bits:
            lines.append(" ".join(bit for bit in property_bits if bit))
        if context.get("trespass_prop"):
            lines.append(f"They do not like you lingering around {context['trespass_prop'].get('name', context['trespass_prop'].get('id', 'property'))}.")
        elif context.get("recent_offense") and float(context["recent_offense"].get("strength", 0.0)) >= 0.18:
            action = str(context["recent_offense"].get("data", {}).get("action", "trouble")).replace("_", " ").strip()
            lines.append(f"They remember your recent {action} and stay guarded.")
        else:
            if context.get("rumor_line"):
                lines.append(context["rumor_line"])
            elif context.get("other_name"):
                lines.append(f"They mention {context['other_relation']} {context['other_name']}.")
            else:
                lines.append(self._social_need_line(context.get("npc_needs"), context.get("bond")))
        self.sim.emit(Event("npc_interacted", eid=self.player_eid, npc_eid=npc_eid, lines=lines[:4], guarded=bool(context.get("guarded"))))

    def on_npc_interact(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        npc_eid = event.data.get("npc_eid")
        if npc_eid is None:
            return
        self._remember_opportunity_npc_interaction(npc_eid)
        context = self._dialogue_context(npc_eid)
        if not context:
            return
        fresh = not self._recently_interacted(npc_eid)
        bond = self._conversation_bond(
            npc_eid=npc_eid,
            npc_ai=context.get("ai"),
            npc_needs=context.get("npc_needs"),
            npc_traits=context.get("npc_traits"),
            guarded=bool(context.get("guarded")),
        )
        if fresh:
            self._mark_interacted(npc_eid)
        player_needs = self.sim.ecs.get(NPCNeeds).get(self.player_eid)
        if fresh and not context.get("guarded"):
            rapport = self._conversation_rapport()
            social_gain = min(2.4, 0.55 + (rapport * 1.1))
            if player_needs:
                player_needs.social = _clamp(player_needs.social + social_gain)
            if context.get("npc_needs"):
                context["npc_needs"].social = _clamp(context["npc_needs"].social + max(0.25, social_gain * 0.45))
        context = self._dialogue_context(npc_eid, bond=bond)
        if not context:
            return
        if not context.get("human"):
            self._emit_simple_npc_interaction(context)
            return
        self._open_dialogue(context)
        self.sim.emit(Event("npc_interacted", eid=self.player_eid, npc_eid=npc_eid, lines=(), guarded=bool(context.get("guarded")), dialog_modal=True))

    def on_dialog_topic_request(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        state = self._dialog_ui_state()
        if not state.get("open"):
            return
        npc_eid = state.get("npc_eid")
        if npc_eid is None:
            return
        self._remember_opportunity_npc_interaction(npc_eid)
        topic_id = str(event.data.get("topic_id", "") or "").strip().lower()
        if not topic_id:
            return
        previous_topic_id = str(self._dialogue_memory(npc_eid).get("last_topic_id", "")).strip().lower()
        selected_row = self._current_dialog_selected_row()
        previous_index = int(state.get("selected_index", 0))
        previous_topic_ids = {
            str(row.get("id", "")).strip().lower()
            for row in list(state.get("topics", ()) or ())
            if str(row.get("id", "")).strip()
        }
        context = self._dialogue_context(npc_eid)
        if not context:
            self._close_dialog()
            self.sim.log.add("The conversation slips away.", channel="social", priority="low")
            return
        response = self._resolve_dialog_topic(context, topic_id)
        response = self._apply_dialogue_initiative(context, topic_id, response)
        response = self._apply_dialogue_repeat_friction(context, topic_id, response)
        self._remember_revealed_social_lead_names(context, response)
        self._append_dialogue_response(
            context,
            topic_id,
            response,
            previous_topic_id=previous_topic_id,
        )
        refreshed = self._dialogue_context(npc_eid)
        if not refreshed:
            self._close_dialog()
            return
        state["subtitle"] = refreshed.get("subtitle", "")
        state["topics"] = self._available_dialog_topics(refreshed)
        new_topic_ids = [
            str(row.get("id", "")).strip().lower()
            for row in list(state.get("topics", ()) or ())
            if str(row.get("id", "")).strip().lower() not in previous_topic_ids
        ]
        state["new_topic_ids"] = [topic for topic in new_topic_ids if topic]
        if state["new_topic_ids"]:
            label_map = {
                str(row.get("id", "")).strip().lower(): str(row.get("label", row.get("id", "topic"))).strip()
                for row in list(state.get("topics", ()) or ())
            }
            labels = [label_map.get(topic_id, topic_id.replace("_", " ")) for topic_id in state["new_topic_ids"][:3]]
            state["hint"] = self._dialogue_hint_text(refreshed, new_topic_labels=labels)
        else:
            state["hint"] = self._dialogue_hint_text(refreshed)
        self._restore_dialog_selection(
            state.get("topics", ()),
            preferred_row=selected_row,
            fallback_index=previous_index,
        )
        state["scroll"] = max(0, len(list(state.get("transcript", ()) or ())) - 1)
        if response.get("open_trade"):
            self._close_dialog()
            trade_property_id = str(response.get("trade_property_id", "") or "").strip()
            trade_prop = self.sim.properties.get(trade_property_id) if trade_property_id else None
            if isinstance(trade_prop, dict):
                self.sim.emit(Event(
                    "property_interact",
                    eid=self.player_eid,
                    property_id=trade_prop.get("id"),
                    x=trade_prop.get("x"),
                    y=trade_prop.get("y"),
                    z=trade_prop.get("z"),
                ))
            else:
                self.sim.emit(Event("trade_panel_open_request", eid=self.player_eid, mode="buy", property_id=trade_property_id))
            return
        if response.get("close"):
            self._hold_dialog_for_ack()

    def on_dialog_close_request(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        self._close_dialog()

    def _clear_contractor_player_heat(self, npc_eid, ally_eid):
        ai = self.sim.ecs.get(AI).get(npc_eid)
        if ai and ai.target_eid == ally_eid and ai.state in THREAT_STATES:
            ai.state = "idle"
            ai.target = None
            ai.target_eid = None
        will = self.sim.ecs.get(NPCWill).get(npc_eid)
        if will and will.target_eid == ally_eid and str(will.intent or "").strip().lower() in THREAT_STATES:
            will.intent = "idle"
            will.score = 0.0
            will.target = None
            will.target_eid = None
            will.last_tick = self.sim.tick
        memory = self.sim.ecs.get(NPCMemory).get(npc_eid)
        if memory:
            keep = []
            for entry in list(memory.entries):
                kind = str(entry.get("kind", "") or "").strip().lower()
                data = entry.get("data", {}) if isinstance(entry.get("data", {}), dict) else {}
                offender_eid = data.get("offender_eid", data.get("source_eid"))
                property_offender = data.get("offender_eid")
                if kind in {"offense", "threat"} and offender_eid == ally_eid:
                    continue
                if kind == "property_threat" and property_offender == ally_eid:
                    continue
                keep.append(entry)
            memory.entries = keep

    def _prime_backup_bond(self, npc_eid):
        bond = self._ensure_dialogue_bond(npc_eid, guarded=False)
        if not bond:
            return None
        bond["trust"] = max(float(bond.get("trust", 0.0) or 0.0), 0.72)
        bond["closeness"] = max(float(bond.get("closeness", 0.0) or 0.0), 0.64)
        bond["protectiveness"] = max(float(bond.get("protectiveness", 0.0) or 0.0), 0.88)
        return bond

    def _contractor_follow_target(self, npc_eid, npc_pos, ally_pos):
        if not npc_pos or not ally_pos:
            return None
        if int(npc_pos.z) != int(ally_pos.z):
            return (int(npc_pos.x), int(npc_pos.y), int(npc_pos.z))
        if _manhattan(npc_pos.x, npc_pos.y, ally_pos.x, ally_pos.y) <= 1:
            return (int(npc_pos.x), int(npc_pos.y), int(npc_pos.z))

        candidates = []
        offsets = (
            (0, 1), (1, 0), (0, -1), (-1, 0),
            (1, 1), (1, -1), (-1, 1), (-1, -1),
            (0, 2), (2, 0), (0, -2), (-2, 0),
        )
        for dx, dy in offsets:
            tx = int(ally_pos.x) + int(dx)
            ty = int(ally_pos.y) + int(dy)
            tz = int(ally_pos.z)
            if not self.sim.tilemap.is_walkable(tx, ty, tz):
                continue
            blocker = _first_blocking_entity_at(self.sim, tx, ty, tz, exclude_eid=npc_eid)
            if blocker is not None:
                continue
            dist_to_ally = _manhattan(tx, ty, ally_pos.x, ally_pos.y)
            dist_to_npc = _manhattan(tx, ty, npc_pos.x, npc_pos.y)
            candidates.append((dist_to_ally, dist_to_npc, tx, ty, tz))
        if candidates:
            candidates.sort()
            best = candidates[0]
            return (best[2], best[3], best[4])
        return (int(npc_pos.x), int(npc_pos.y), int(npc_pos.z))

    def _contractor_focus_threat(self, rec, ally_pos):
        threat_eid = rec.get("focus_threat_eid")
        if threat_eid is None or int(rec.get("focus_threat_until", 0) or 0) <= int(self.sim.tick):
            rec.pop("focus_threat_eid", None)
            rec.pop("focus_threat_until", None)
            return None
        threat_pos = self.sim.ecs.get(Position).get(threat_eid)
        if not threat_pos or not ally_pos or int(threat_pos.z) != int(ally_pos.z):
            return None
        if _entity_is_downed(self.sim, threat_eid):
            return None
        return threat_eid

    def _contractor_backup_threat(self, npc_eid, npc_pos, ally_eid, ally_pos, rec, *, protect_ally=True):
        focused = self._contractor_focus_threat(rec, ally_pos) if protect_ally else None
        if focused is not None:
            return focused

        ais = self.sim.ecs.get(AI)
        positions = self.sim.ecs.get(Position)
        best = None
        for other_eid, other_ai in ais.items():
            if other_eid in {npc_eid, ally_eid}:
                continue
            if str(getattr(other_ai, "state", "") or "").strip().lower() not in THREAT_STATES:
                continue
            target_eid = getattr(other_ai, "target_eid", None)
            if protect_ally:
                if target_eid not in {ally_eid, npc_eid}:
                    continue
            elif target_eid != npc_eid:
                continue
            other_pos = positions.get(other_eid)
            if not other_pos or not ally_pos or int(other_pos.z) != int(ally_pos.z):
                continue
            if _entity_is_downed(self.sim, other_eid):
                continue
            player_dist = _manhattan(other_pos.x, other_pos.y, ally_pos.x, ally_pos.y)
            npc_dist = _manhattan(other_pos.x, other_pos.y, npc_pos.x, npc_pos.y)
            if min(player_dist, npc_dist) > 12:
                continue
            score = 120 - (player_dist * 5) - npc_dist
            if protect_ally and target_eid == ally_eid:
                score += 12
            if best is None or score > best[0]:
                best = (score, other_eid)
        return best[1] if best else None

    # ── Contractor task system ───────────────────────────────────────────────

    CONTRACTOR_TICK_INTERVAL = 5

    def update(self):
        tick = self.sim.tick
        if tick % self.CONTRACTOR_TICK_INTERVAL != 0:
            return
        self._tick_contractors()

    def _tick_contractors(self):
        contractors = getattr(self.sim, "contractors", {})
        if not contractors:
            return
        tick = self.sim.tick
        expired = [eid for eid, rec in list(contractors.items()) if rec.get("until", 0) <= tick]
        for npc_eid in expired:
            rec = contractors.pop(npc_eid)
            self._clear_contractor_player_heat(
                npc_eid,
                rec.get("ally_eid", self.player_eid),
            )
            self.sim.emit(Event(
                "contractor_task_complete",
                npc_eid=npc_eid,
                job=rec.get("job", "distraction"),
                hired_tick=rec.get("hired_tick", 0),
            ))
        positions = self.sim.ecs.get(Position)
        for npc_eid, rec in list(contractors.items()):
            job = str(rec.get("job", "distraction") or "distraction").strip().lower()
            ally_eid = rec.get("ally_eid", self.player_eid)
            ally_pos = positions.get(ally_eid)
            if job == "distraction":
                self._assign_contractor_distraction(npc_eid, ally_pos)
            elif job == "surrendered":
                order = self._contractor_order_mode(rec)
                if order in {"hold", "goto_wait"}:
                    self._assign_peaceful_surrender_hold(npc_eid, rec)
                elif order == "wait_return":
                    self._assign_peaceful_surrender_hold(npc_eid, rec)
                    target = self._contractor_order_target(rec)
                    npc_pos = positions.get(npc_eid)
                    if target and npc_pos and _manhattan(npc_pos.x, npc_pos.y, target[0], target[1]) <= 0:
                        wait_started = int(rec.get("order_wait_started", 0) or 0)
                        if wait_started <= 0:
                            rec["order_wait_started"] = tick
                        elif tick - wait_started >= int(rec.get("order_wait_ticks", self.CONTRACTOR_RETURN_WAIT_TICKS) or self.CONTRACTOR_RETURN_WAIT_TICKS):
                            self._set_contractor_order(rec, "passive")
                            self._assign_peaceful_surrender_follow(npc_eid, ally_eid, ally_pos)
                else:
                    self._assign_peaceful_surrender_follow(npc_eid, ally_eid, ally_pos)
            elif job in {"backup", "party"}:
                order = self._contractor_order_mode(rec)
                if order == "distraction":
                    issued = int(rec.get("order_wait_started", 0) or 0)
                    duration = int(rec.get("order_wait_ticks", self.CONTRACTOR_DISTRACTION_TICKS) or self.CONTRACTOR_DISTRACTION_TICKS)
                    if issued <= 0:
                        rec["order_wait_started"] = tick
                    elif tick - issued >= duration:
                        self._set_contractor_order(rec, "passive")
                        self._assign_contractor_backup(npc_eid, ally_eid, ally_pos, rec)
                        continue
                    self._assign_contractor_distraction(npc_eid, ally_pos, rec)
                elif order in {"hold", "goto_wait"}:
                    self._assign_contractor_hold(npc_eid, ally_eid, ally_pos, rec)
                elif order == "wait_return":
                    self._assign_contractor_hold(npc_eid, ally_eid, ally_pos, rec)
                    target = self._contractor_order_target(rec)
                    npc_pos = positions.get(npc_eid)
                    if target and npc_pos and _manhattan(npc_pos.x, npc_pos.y, target[0], target[1]) <= 0:
                        wait_started = int(rec.get("order_wait_started", 0) or 0)
                        if wait_started <= 0:
                            rec["order_wait_started"] = tick
                        elif tick - wait_started >= int(rec.get("order_wait_ticks", self.CONTRACTOR_RETURN_WAIT_TICKS) or self.CONTRACTOR_RETURN_WAIT_TICKS):
                            self._set_contractor_order(rec, "passive")
                            self._assign_contractor_backup(npc_eid, ally_eid, ally_pos, rec)
                elif order == "kill":
                    if not self._assign_contractor_kill(npc_eid, ally_eid, ally_pos, rec):
                        self._set_contractor_order(rec, "passive")
                        self._assign_contractor_backup(npc_eid, ally_eid, ally_pos, rec)
                else:
                    self._assign_contractor_backup(npc_eid, ally_eid, ally_pos, rec)

    def on_contractor_hired(self, event):
        npc_eid = event.data.get("npc_eid")
        if not npc_eid:
            return
        contractors = getattr(self.sim, "contractors", {})
        rec = contractors.get(npc_eid, {}) if isinstance(contractors, dict) else {}
        job = str(event.data.get("job", rec.get("job", "distraction")) or "distraction").strip().lower()
        ally_eid = event.data.get("ally_eid", rec.get("ally_eid", self.player_eid))
        ally_pos = self.sim.ecs.get(Position).get(ally_eid)
        if job in {"backup", "party"}:
            self._assign_contractor_backup(npc_eid, ally_eid, ally_pos, rec if isinstance(rec, dict) else {})
        else:
            self._assign_contractor_distraction(npc_eid, ally_pos)

    def on_entity_moved(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        contractors = getattr(self.sim, "contractors", {})
        if not isinstance(contractors, dict) or not contractors:
            return
        player_pos = self.sim.ecs.get(Position).get(self.player_eid)
        for npc_eid, rec in list(contractors.items()):
            job = str(rec.get("job", "") or "").strip().lower()
            if job not in {"backup", "party", "surrendered"}:
                continue
            if self._contractor_order_mode(rec) != "passive":
                continue
            if job == "surrendered":
                self._assign_peaceful_surrender_follow(npc_eid, self.player_eid, player_pos)
            else:
                self._assign_contractor_backup(npc_eid, self.player_eid, player_pos, rec)

    def on_entity_damaged(self, event):
        if event.data.get("target_eid") != self.player_eid:
            return
        source_eid = event.data.get("source_eid")
        if source_eid is None:
            return
        contractors = getattr(self.sim, "contractors", {})
        if not isinstance(contractors, dict) or not contractors:
            return
        player_pos = self.sim.ecs.get(Position).get(self.player_eid)
        for npc_eid, rec in list(contractors.items()):
            if str(rec.get("job", "") or "").strip().lower() not in {"backup", "party"}:
                continue
            if self._contractor_order_mode(rec) != "passive":
                continue
            rec["focus_threat_eid"] = source_eid
            rec["focus_threat_until"] = int(self.sim.tick) + 45
            self._assign_contractor_backup(npc_eid, self.player_eid, player_pos, rec)

    def on_npc_downed(self, event):
        contractors = getattr(self.sim, "contractors", {})
        if isinstance(contractors, dict):
            contractors.pop(event.data.get("target_eid"), None)

    def on_npc_killed(self, event):
        contractors = getattr(self.sim, "contractors", {})
        if isinstance(contractors, dict):
            contractors.pop(event.data.get("target_eid"), None)

    def _assign_peaceful_surrender_hold(self, npc_eid, rec):
        ai = self.sim.ecs.get(AI).get(npc_eid)
        will = self.sim.ecs.get(NPCWill).get(npc_eid)
        npc_pos = self.sim.ecs.get(Position).get(npc_eid)
        if not ai or not npc_pos:
            return
        if _entity_is_downed(self.sim, npc_eid):
            _apply_downed_actor_state(self.sim, npc_eid, tick=self.sim.tick)
            return

        hold_target = self._contractor_order_target(rec) or (int(npc_pos.x), int(npc_pos.y), int(npc_pos.z))
        _sync_ai_intent(
            ai,
            will,
            self.sim.tick,
            "holding",
            score=58.0,
            target=hold_target,
            target_eid=None,
        )

    def _assign_peaceful_surrender_follow(self, npc_eid, ally_eid, ally_pos):
        ai = self.sim.ecs.get(AI).get(npc_eid)
        will = self.sim.ecs.get(NPCWill).get(npc_eid)
        npc_pos = self.sim.ecs.get(Position).get(npc_eid)
        if not ai or not npc_pos or not ally_pos:
            return
        if _entity_is_downed(self.sim, npc_eid):
            _apply_downed_actor_state(self.sim, npc_eid, tick=self.sim.tick)
            return

        follow_target = self._contractor_follow_target(npc_eid, npc_pos, ally_pos)
        if follow_target is None:
            return
        _sync_ai_intent(
            ai,
            will,
            self.sim.tick,
            "following",
            score=60.0,
            target=follow_target,
            target_eid=None,
        )

    def _assign_contractor_distraction(self, npc_eid, player_pos, rec=None):
        ai = self.sim.ecs.get(AI).get(npc_eid)
        will = self.sim.ecs.get(NPCWill).get(npc_eid)
        npc_pos = self.sim.ecs.get(Position).get(npc_eid)
        if not ai or not npc_pos:
            return
        if _entity_is_downed(self.sim, npc_eid):
            _apply_downed_actor_state(self.sim, npc_eid, tick=self.sim.tick)
            return
        target_eid = None
        if isinstance(rec, dict):
            target_eid = self._contractor_backup_threat(
                npc_eid,
                npc_pos,
                self.player_eid,
                player_pos,
                rec,
                protect_ally=False,
            )
        if target_eid is not None:
            target_pos = self.sim.ecs.get(Position).get(target_eid)
            if target_pos and int(target_pos.z) == int(npc_pos.z):
                target = (int(target_pos.x), int(target_pos.y), int(target_pos.z))
                _sync_ai_intent(
                    ai,
                    will,
                    self.sim.tick,
                    "protecting",
                    score=84.0,
                    target=target,
                    target_eid=target_eid,
                )
                return
        # Don't interrupt if already investigating toward the distraction target.
        if getattr(ai, "state", "") == "investigating" and getattr(ai, "target", None):
            return
        target = self._contractor_order_target(rec) if isinstance(rec, dict) else None
        if target is None:
            target = self._distraction_waypoint(npc_pos, player_pos)
        _sync_ai_intent(ai, will, self.sim.tick, "investigating", score=65.0, target=target)

    def _assign_contractor_hold(self, npc_eid, ally_eid, ally_pos, rec):
        ai = self.sim.ecs.get(AI).get(npc_eid)
        will = self.sim.ecs.get(NPCWill).get(npc_eid)
        npc_pos = self.sim.ecs.get(Position).get(npc_eid)
        if not ai or not npc_pos:
            return
        if _entity_is_downed(self.sim, npc_eid):
            _apply_downed_actor_state(self.sim, npc_eid, tick=self.sim.tick)
            return

        self._clear_contractor_player_heat(npc_eid, ally_eid)
        threat_eid = self._contractor_backup_threat(
            npc_eid,
            npc_pos,
            ally_eid,
            ally_pos or npc_pos,
            rec,
            protect_ally=False,
        )
        if threat_eid is not None:
            threat_pos = self.sim.ecs.get(Position).get(threat_eid)
            if threat_pos and int(threat_pos.z) == int(npc_pos.z):
                target = (int(threat_pos.x), int(threat_pos.y), int(threat_pos.z))
                _sync_ai_intent(
                    ai,
                    will,
                    self.sim.tick,
                    "protecting",
                    score=86.0,
                    target=target,
                    target_eid=threat_eid,
                )
                return

        hold_target = self._contractor_order_target(rec) or (int(npc_pos.x), int(npc_pos.y), int(npc_pos.z))
        _sync_ai_intent(
            ai,
            will,
            self.sim.tick,
            "holding",
            score=80.0,
            target=hold_target,
            target_eid=None,
        )

    def _assign_contractor_kill(self, npc_eid, ally_eid, ally_pos, rec):
        ai = self.sim.ecs.get(AI).get(npc_eid)
        will = self.sim.ecs.get(NPCWill).get(npc_eid)
        npc_pos = self.sim.ecs.get(Position).get(npc_eid)
        target_eid = rec.get("order_target_eid") if isinstance(rec, dict) else None
        if not ai or not npc_pos or target_eid in {None, npc_eid, ally_eid}:
            return False
        if _entity_is_downed(self.sim, npc_eid):
            _apply_downed_actor_state(self.sim, npc_eid, tick=self.sim.tick)
            return False

        target_pos = self.sim.ecs.get(Position).get(target_eid)
        if not target_pos or _entity_is_downed(self.sim, target_eid):
            return False
        if ally_pos and int(target_pos.z) != int(ally_pos.z):
            return False

        self._clear_contractor_player_heat(npc_eid, ally_eid)
        _sync_ai_intent(
            ai,
            will,
            self.sim.tick,
            "protecting",
            score=92.0,
            target=(int(target_pos.x), int(target_pos.y), int(target_pos.z)),
            target_eid=target_eid,
        )
        return True

    def _assign_contractor_backup(self, npc_eid, ally_eid, ally_pos, rec):
        ai = self.sim.ecs.get(AI).get(npc_eid)
        will = self.sim.ecs.get(NPCWill).get(npc_eid)
        npc_pos = self.sim.ecs.get(Position).get(npc_eid)
        if not ai or not npc_pos or not ally_pos:
            return
        if _entity_is_downed(self.sim, npc_eid):
            _apply_downed_actor_state(self.sim, npc_eid, tick=self.sim.tick)
            return

        self._clear_contractor_player_heat(npc_eid, ally_eid)
        threat_eid = self._contractor_backup_threat(npc_eid, npc_pos, ally_eid, ally_pos, rec)
        if threat_eid is not None:
            threat_pos = self.sim.ecs.get(Position).get(threat_eid)
            if threat_pos and int(threat_pos.z) == int(npc_pos.z):
                target = (int(threat_pos.x), int(threat_pos.y), int(threat_pos.z))
            else:
                target = (int(ally_pos.x), int(ally_pos.y), int(ally_pos.z))
            switched = not (ai.state == "protecting" and ai.target_eid == threat_eid)
            _sync_ai_intent(
                ai,
                will,
                self.sim.tick,
                "protecting",
                score=88.0,
                target=target,
                target_eid=threat_eid,
            )
            if switched:
                self.sim.emit(Event(
                    "npc_protect_ally",
                    npc_eid=npc_eid,
                    ally_eid=ally_eid,
                    against_eid=threat_eid,
                    relation="ally",
                ))
            return

        follow_target = self._contractor_follow_target(npc_eid, npc_pos, ally_pos)
        if follow_target is None:
            return
        _sync_ai_intent(
            ai,
            will,
            self.sim.tick,
            "following",
            score=82.0,
            target=follow_target,
            target_eid=None,
        )

    def _distraction_waypoint(self, npc_pos, player_pos):
        nx, ny = int(npc_pos.x), int(npc_pos.y)
        nz = int(getattr(npc_pos, "z", 0))
        if player_pos:
            dx = nx - int(player_pos.x)
            dy = ny - int(player_pos.y)
            mag = max(1.0, (dx ** 2 + dy ** 2) ** 0.5)
            tx = nx + int(round(dx / mag * 10))
            ty = ny + int(round(dy / mag * 10))
        else:
            tx, ty = nx + 10, ny
        if self.sim.tilemap.is_walkable(tx, ty, nz):
            return (tx, ty, nz)
        for r in range(1, 6):
            for ddx, ddy in ((r, 0), (-r, 0), (0, r), (0, -r), (r, r), (-r, r), (r, -r), (-r, -r)):
                cx, cy = tx + ddx, ty + ddy
                if self.sim.tilemap.is_walkable(cx, cy, nz):
                    return (cx, cy, nz)
        return (tx, ty, nz)


from game.player_action_system import PlayerActionSystem


class ItemSystem(System):

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.catalog = ITEM_CATALOG
        self.item_actions = ItemActionRuntime(self)
        self.sim.events.subscribe("player_action", self.on_player_action)
        self.sim.events.subscribe("use_item_request", self.on_use_item_request)
        self.sim.events.subscribe("drop_item_request", self.on_drop_item_request)

    def _offense_score_for(self, action, context="ordinary"):
        base = ACTION_OFFENSE_BASE.get(action, 0)
        bonus = ACTION_OFFENSE_CONTEXT_BONUS.get(context, 0)
        return max(0, min(100, base + bonus))

    def _emit_action_offense(self, eid, action, x, y, z, context="ordinary", score=None):
        if score is None:
            score = self._offense_score_for(action, context=context)
        if score <= 0:
            return

        self.sim.emit(Event(
            "action_offense",
            offender_eid=eid,
            action=action,
            context=context,
            offense_score=score,
            offense_tier=_offense_tier(score),
            x=x,
            y=y,
            z=z,
            radius=_offense_notice_radius(score),
        ))

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


class CriminalJusticeSystem(System):

    DETENTION_QUEUE_WINDOW = 30
    DETENTION_RADIUS = 10
    JUSTICE_SITE_SEARCH_RADIUS = 24
    PLAYER_BOOKING_RELEASE_GRACE_TICKS = 18
    SURRENDER_PROMPT_COOLDOWN_TICKS = 180
    SURRENDER_DIALOG_KIND = "justice_surrender"
    BOOKING_ARCHETYPES = ("jail", "courthouse")
    JUSTICE_DEBT_KEY = "justice_fines"
    NPC_CUSTODY_ARCHETYPES_BY_TIER = {
        "questioning": ("jail",),
        "wanted": ("jail",),
        "arrest_on_sight": ("prison", "jail"),
    }
    CUSTODY_ROOM_KINDS_BY_ARCHETYPE = {
        "jail": ("cell_block", "holding", "booking"),
        "prison": ("cell_block", "holding", "intake"),
        "courthouse": ("holding", "booking", "public_hall"),
        "default": ("holding", "booking"),
    }
    RELEASE_ROOM_KINDS_BY_ARCHETYPE = {
        "jail": ("visitation", "booking", "public_hall", "lobby"),
        "prison": ("visitation", "intake", "booking", "public_hall"),
        "courthouse": ("public_hall", "booking", "lobby", "visitation"),
        "default": ("booking", "public_hall", "lobby"),
    }
    PLAYER_AUTO_ARREST_RADIUS_BY_TIER = {
        "questioning": 1,
        "wanted": 1,
        "arrest_on_sight": 2,
    }
    BOOKING_HOURS_BY_TIER = {
        "questioning": 1.0,
        "wanted": 3.0,
        "arrest_on_sight": 6.0,
    }
    NPC_BOOKING_HOURS_BY_TIER = {
        "wanted": 4.0,
        "arrest_on_sight": 8.0,
    }

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.pending_detentions = {}
        self.player_surrender_prompt = None
        self._streaming_system = None
        self.sim.events.subscribe("property_trespass", self.on_property_trespass)
        self.sim.events.subscribe("property_tamper", self.on_property_tamper)
        self.sim.events.subscribe("item_stolen", self.on_item_stolen)
        self.sim.events.subscribe("action_offense", self.on_action_offense)
        self.sim.events.subscribe("incident_authority_reported", self.on_incident_authority_reported)
        self.sim.events.subscribe("property_interact", self.on_property_interact)
        self.sim.events.subscribe("npc_interact", self.on_npc_interact)
        self.sim.events.subscribe("npc_surrendered", self.on_npc_surrendered)
        self.sim.events.subscribe("justice_surrender_choice", self.on_justice_surrender_choice)

    def _emit_change_events(self, change, *, source_event="", reason=""):
        if not isinstance(change, dict):
            return
        incident = change.get("incident") if isinstance(change.get("incident"), dict) else {}
        jurisdiction_key = str(
            incident.get("jurisdiction_key", change.get("jurisdiction_key", ""))
            or ""
        ).strip().lower()
        jurisdiction_name = str(
            incident.get("jurisdiction_name", change.get("jurisdiction_name", "Justice Office"))
            or "Justice Office"
        ).strip() or "Justice Office"
        payload = {
            "offender_eid": change.get("eid"),
            "before_score": int(change.get("before_score", 0)),
            "after_score": int(change.get("after_score", 0)),
            "score_delta": int(change.get("after_score", 0)) - int(change.get("before_score", 0)),
            "incident_count": int(change.get("incident_count", 0)),
            "jurisdiction_key": jurisdiction_key,
            "jurisdiction_name": jurisdiction_name,
            "source_event": str(source_event or incident.get("source_event", "") or "").strip().lower(),
            "reason": str(reason or incident.get("type", "") or "").strip().lower(),
            "incident_type": str(incident.get("type", "") or "").strip().lower(),
            "incident_label": str(incident.get("label", "") or "").strip(),
            "property_id": str(incident.get("property_id", "") or "").strip(),
            "property_name": "",
            "note": str(incident.get("note", "") or "").strip(),
            "incident_witnessed": bool(incident.get("witnessed", False)),
            "before_tier": str(change.get("before_tier", "clear")).strip().lower() or "clear",
            "after_tier": str(change.get("after_tier", "clear")).strip().lower() or "clear",
            "tick": int(getattr(self.sim, "tick", 0)),
        }
        property_id = str(payload.get("property_id", "") or "").strip()
        if property_id:
            prop = self.sim.properties.get(property_id)
            if isinstance(prop, dict):
                payload["property_name"] = str(prop.get("name", prop.get("id", property_id)) or property_id).strip()
        self.sim.emit(Event("justice_record_changed", **payload))
        if bool(change.get("tier_changed")):
            self.sim.emit(Event("justice_wanted_tier_changed", **payload))

    def _justice_state(self):
        traits = getattr(self.sim, "world_traits", None)
        if not isinstance(traits, dict):
            self.sim.world_traits = {}
            traits = self.sim.world_traits
        state = traits.get("criminal_justice")
        if not isinstance(state, dict):
            state = {}
            traits["criminal_justice"] = state
        return state

    def _npc_custody_records(self):
        state = self._justice_state()
        records = state.get("npc_custody")
        if not isinstance(records, dict):
            records = {}
            state["npc_custody"] = records
        return records

    def _player_surrender_offer_records(self):
        state = self._justice_state()
        records = state.get("player_surrender_offers")
        if not isinstance(records, dict):
            records = {}
            state["player_surrender_offers"] = records
        return records

    def _clear_player_surrender_offer_records(self):
        records = self._player_surrender_offer_records()
        records.clear()
        return records

    def _grant_player_release_grace(self, prop_or_property_id, *, duration=None, reason="booking_release"):
        grace_ticks = self.PLAYER_BOOKING_RELEASE_GRACE_TICKS if duration is None else duration
        return _grant_custody_release_grace(
            self.sim,
            self.player_eid,
            prop_or_property_id,
            duration=max(1, int(grace_ticks)),
            reason=reason,
        )

    def _officer_surrender_offer_record(self, npc_eid, *, create=False):
        try:
            officer_id = int(npc_eid)
        except (TypeError, ValueError):
            return None
        if officer_id <= 0:
            return None
        records = self._player_surrender_offer_records()
        key = str(officer_id)
        record = records.get(key)
        if not isinstance(record, dict):
            if not create:
                return None
            record = {}
            records[key] = record
        record.setdefault("last_prompt_tick", -10_000)
        record.setdefault("cooldown_until_tick", -10_000)
        return record

    def _officer_surrender_offer_on_cooldown(self, npc_eid):
        record = self._officer_surrender_offer_record(npc_eid, create=False)
        if not isinstance(record, dict):
            return False
        tick = int(getattr(self.sim, "tick", 0))
        return int(record.get("cooldown_until_tick", -10_000) or -10_000) > tick

    def _mark_officer_surrender_prompt_opened(self, npc_eid):
        record = self._officer_surrender_offer_record(npc_eid, create=True)
        if not isinstance(record, dict):
            return None
        record["last_prompt_tick"] = int(getattr(self.sim, "tick", 0))
        return record

    def _mark_officer_surrender_offer_cooldown(self, npc_eid, *, ticks=None):
        record = self._officer_surrender_offer_record(npc_eid, create=True)
        if not isinstance(record, dict):
            return None
        tick = int(getattr(self.sim, "tick", 0))
        cooldown_ticks = max(1, int(self.SURRENDER_PROMPT_COOLDOWN_TICKS if ticks is None else ticks))
        record["last_prompt_tick"] = tick
        record["cooldown_until_tick"] = int(tick + cooldown_ticks)
        return record

    def _record_incident(
        self,
        offender_eid,
        *,
        incident_type,
        severity=0,
        source_event="",
        property_id=None,
        x=None,
        y=None,
        witnessed=False,
        note="",
    ):
        change = _record_justice_incident(
            self.sim,
            offender_eid,
            incident_type=incident_type,
            severity=severity,
            source_event=source_event,
            property_id=property_id,
            x=x,
            y=y,
            witnessed=witnessed,
            note=note,
        )
        if change is not None:
            self._emit_change_events(change, source_event=source_event, reason=incident_type)
        return change

    def _watchers_present(self, offender_eid, x, y, z):
        if x is None or y is None or z is None:
            return False
        watchers = _watchers_for_position(
            self.sim,
            x,
            y,
            z,
            exclude_eid=offender_eid,
            offender_eid=offender_eid,
        )
        return bool(watchers)

    def _position_for(self, eid):
        return self.sim.ecs.get(Position).get(eid)

    def _find_walkable_near(self, x, y, z=0, radius=8):
        try:
            tx = int(x)
            ty = int(y)
            tz = int(z)
        except (TypeError, ValueError):
            return 0, 0, 0
        if self.sim.tilemap.is_walkable(tx, ty, tz):
            return tx, ty, tz
        for ring in range(1, max(1, int(radius)) + 1):
            for dy in range(-ring, ring + 1):
                for dx in range(-ring, ring + 1):
                    if abs(dx) != ring and abs(dy) != ring:
                        continue
                    nx = tx + dx
                    ny = ty + dy
                    if self.sim.detail_for_xy(nx, ny) == "unloaded":
                        continue
                    if self.sim.tilemap.is_walkable(nx, ny, tz):
                        return nx, ny, tz
        return tx, ty, tz

    def _teleport_entity(self, eid, pos, new_x, new_y, new_z, reason="teleport"):
        old_x = pos.x
        old_y = pos.y
        old_z = pos.z
        if (old_x, old_y, old_z) == (int(new_x), int(new_y), int(new_z)):
            return
        self.sim.tilemap.move_entity(
            eid,
            oldx=old_x,
            oldy=old_y,
            oldz=old_z,
            newx=int(new_x),
            newy=int(new_y),
            newz=int(new_z),
        )
        pos.x = int(new_x)
        pos.y = int(new_y)
        pos.z = int(new_z)
        self.sim.emit(Event(
            "entity_moved",
            eid=eid,
            old_x=old_x,
            old_y=old_y,
            old_z=old_z,
            x=pos.x,
            y=pos.y,
            z=pos.z,
            reason=reason,
        ))

    def _ticks_per_hour(self):
        world_traits = getattr(self.sim, "world_traits", {})
        clock = world_traits.get("clock", {}) if isinstance(world_traits, dict) else {}
        try:
            ticks_per_hour = int(clock.get("ticks_per_hour", 600))
        except (TypeError, ValueError, AttributeError):
            ticks_per_hour = 600
        return max(60, ticks_per_hour)

    def _hours_to_ticks(self, hours):
        try:
            total_hours = float(hours)
        except (TypeError, ValueError):
            total_hours = 0.0
        return max(0, int(round(total_hours * float(self._ticks_per_hour()))))

    def _advance_time_for_booking(self, ticks, *, property_id=None, property_name="", held_by_eid=None):
        ticks = max(0, int(ticks))
        if ticks <= 0:
            return 0
        advanced_ticks = int(self.sim.advance_time(
            ticks,
            reason="justice_booking",
            eid=self.player_eid,
            property_id=property_id,
            property_name=str(property_name or "Justice Office").strip() or "Justice Office",
            held_by_eid=held_by_eid,
        ))
        effects_map = self.sim.ecs.get(StatusEffects)
        for target_eid, effects in list(effects_map.items()):
            expired = effects.advance(advanced_ticks)
            for status in expired:
                self.sim.emit(Event(
                    "status_expired",
                    eid=target_eid,
                    status=status,
                ))
        return advanced_ticks

    def _actor_is_enforcer(self, eid):
        justices = self.sim.ecs.get(JusticeProfile)
        occupations = self.sim.ecs.get(Occupation)
        ais = self.sim.ecs.get(AI)
        profile = justices.get(eid)
        occupation = occupations.get(eid)
        ai = ais.get(eid)
        career = str(getattr(occupation, "career", "") or "").strip().lower()
        role = str(getattr(ai, "role", "") or "").strip().lower()
        if role == "wildlife":
            return False, 0.0, 0

        law_drive = 0.0
        if profile:
            if profile.corruption > 0.82 and not profile.enforce_all:
                return False, 0.0, 0
            law_drive = (_justice_level(profile) * 0.65) + (_crime_sensitivity(profile) * 0.35)

        explicit_enforcer = bool(
            (profile and profile.enforce_all)
            or role == "guard"
            or any(token in career for token in ("guard", "corrections", "deputy", "bailiff", "sergeant"))
        )
        if not explicit_enforcer and law_drive < 0.78:
            return False, law_drive, 0

        priority = 0
        if profile and profile.enforce_all:
            priority += 3
        if role == "guard":
            priority += 2
        if any(token in career for token in ("corrections", "deputy", "bailiff", "sergeant")):
            priority += 2
        return True, law_drive, priority

    def _player_bookable_snapshot(self):
        snapshot = _justice_snapshot(self.sim, self.player_eid)
        tier = str(snapshot.get("wanted_tier", "clear")).strip().lower() or "clear"
        if tier not in {"questioning", "wanted", "arrest_on_sight"}:
            return None
        if bool(snapshot.get("in_custody", False)):
            return None
        return snapshot

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
        return state

    def _reset_dialog_ui(self, state=None):
        state = state if isinstance(state, dict) else self._dialog_ui_state()
        state.update({
            "open": False,
            "kind": "conversation",
            "npc_eid": None,
            "property_id": None,
            "title": "Conversation",
            "subtitle": "",
            "transcript": [],
            "topics": [],
            "selected_index": 0,
            "scroll": 0,
            "hint": "",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
            "backup_cursor_mark": None,
            "backup_cursor_pending_topic": "",
        })
        return state

    def _player_surrender_prompt_open(self):
        state = self._dialog_ui_state()
        return bool(state.get("open")) and str(state.get("kind", "")).strip().lower() == self.SURRENDER_DIALOG_KIND

    def _player_cash_on_hand(self):
        return self._inventory_cash_total_from_entries(self._snapshot_inventory_items(self.player_eid))

    def _player_assets(self, *, create=False):
        assets = self.sim.ecs.get(PlayerAssets).get(self.player_eid)
        if assets is None and create:
            assets = PlayerAssets(credits=0)
            self.sim.ecs.add(self.player_eid, assets)
        return assets

    def _player_finance_profile(self, *, create=False):
        profile = self.sim.ecs.get(FinancialProfile).get(self.player_eid)
        if profile is None and create:
            profile = FinancialProfile(bank_balance=0)
            self.sim.ecs.add(self.player_eid, profile)
        return profile

    def _player_wallet_credits(self):
        assets = self._player_assets(create=False)
        return int(max(0, getattr(assets, "credits", 0) or 0)) if assets is not None else 0

    def _player_bank_balance(self):
        profile = self._player_finance_profile(create=False)
        return int(max(0, getattr(profile, "bank_balance", 0) or 0)) if profile is not None else 0

    def _player_debt_balance(self):
        profile = self._player_finance_profile(create=False)
        if profile is None:
            return 0
        total_debt = getattr(profile, "total_debt", None)
        if callable(total_debt):
            return int(max(0, total_debt() or 0))
        return int(max(0, getattr(profile, "debt_balance", 0) or 0))

    def _player_justice_debt_balance(self):
        profile = self._player_finance_profile(create=False)
        if profile is None:
            return 0
        debt_amount = getattr(profile, "debt_amount", None)
        if callable(debt_amount):
            return int(max(0, debt_amount(self.JUSTICE_DEBT_KEY) or 0))
        return int(max(0, getattr(profile, "debt_balance", 0) or 0))

    def _player_held_property_snapshot(self):
        return _justice_held_property_snapshot(self.sim, self.player_eid)

    def _present_justice_result(self, title, lines, *, property_id=None, subtitle=""):
        state = self._dialog_ui_state()
        cleaned = [str(line).strip() for line in list(lines or ()) if str(line).strip()]
        if not cleaned:
            cleaned = ["Nothing is on file right now."]
        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "open": True,
            "kind": "service_menu",
            "npc_eid": None,
            "property_id": property_id,
            "title": str(title or "Justice Desk").strip() or "Justice Desk",
            "subtitle": str(subtitle or "").strip(),
            "transcript": cleaned,
            "topics": [],
            "selected_index": 0,
            "scroll": 0,
            "hint": "Space closes. O opens your report.",
            "new_topic_ids": [],
            "close_pending": True,
            "machine_action": None,
            "service_menu_mode": "justice_result",
            "casino_session": None,
        })
        return True

    def _justice_item_hold_policy(self, entry):
        entry = entry if isinstance(entry, dict) else {}
        item_id = str(entry.get("item_id", "") or "").strip().lower()
        item_def = ITEM_CATALOG.get(item_id, {})
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        legal_status = str(item_def.get("legal_status", "legal")).strip().lower() or "legal"
        tags = _item_tags(item_def)
        weapon = bool(_item_weapon_id(item_def)) or "weapon" in tags
        illegal = legal_status == "illegal"
        restricted = legal_status == "restricted"
        contraband = illegal or restricted
        stolen = bool(metadata.get("justice_stolen"))
        objective_protected = bool(metadata.get("final_operation_target"))
        if not objective_protected:
            try:
                objective_protected = int(metadata.get("quest_opportunity_id", 0) or 0) > 0
            except (TypeError, ValueError):
                objective_protected = False

        hold_for_release = bool(objective_protected or ((weapon or restricted) and not (illegal or stolen)))
        forfeit = bool((illegal or stolen) and not objective_protected)
        seized = bool(weapon or contraband or stolen or objective_protected)
        return {
            "item_id": item_id,
            "weapon": weapon,
            "illegal": illegal,
            "restricted": restricted,
            "contraband": contraband,
            "stolen": stolen,
            "objective_protected": objective_protected,
            "hold_for_release": hold_for_release,
            "forfeit": forfeit,
            "seized": seized,
        }

    def _inventory_can_accept_entry(self, inventory, entry):
        if inventory is None or not isinstance(entry, dict):
            return False
        item_id = str(entry.get("item_id", "") or "").strip().lower()
        if not item_id:
            return False
        item_def = ITEM_CATALOG.get(item_id, {})
        quantity = max(1, int(entry.get("quantity", 1) or 1))
        stack_max = max(1, int(item_def.get("stack_max", 1) or 1))
        if stack_max <= 1:
            needed_slots = quantity
            return (int(inventory.slot_count()) + int(needed_slots)) <= int(getattr(inventory, "capacity", 0) or 0)

        open_room = 0
        for current in list(getattr(inventory, "items", ()) or ()):
            if str(current.get("item_id", "") or "").strip().lower() != item_id:
                continue
            if current.get("owner_eid") != self.player_eid:
                continue
            if str(current.get("owner_tag", "") or "").strip().lower() != "player":
                continue
            current_qty = max(0, int(current.get("quantity", 0) or 0))
            if current_qty >= stack_max:
                continue
            open_room += max(0, stack_max - current_qty)
        remaining = max(0, quantity - open_room)
        needed_slots = (remaining + stack_max - 1) // stack_max if remaining > 0 else 0
        return (int(inventory.slot_count()) + int(needed_slots)) <= int(getattr(inventory, "capacity", 0) or 0)

    def _restore_inventory_entry(self, inventory, entry):
        if inventory is None or not isinstance(entry, dict):
            return False
        item_id = str(entry.get("item_id", "") or "").strip().lower()
        if not item_id:
            return False
        item_def = ITEM_CATALOG.get(item_id, {})
        added, _instance_id = inventory.add_item(
            item_id=item_id,
            quantity=max(1, int(entry.get("quantity", 1) or 1)),
            stack_max=max(1, int(item_def.get("stack_max", 1) or 1)),
            instance_id=entry.get("instance_id"),
            owner_eid=self.player_eid,
            owner_tag="player",
            metadata=dict(entry.get("metadata") or {}),
        )
        return bool(added)

    def _justice_status_lines(self, *, current_prop=None):
        current_prop = current_prop if isinstance(current_prop, dict) else None
        lines = list(_justice_summary_rows(self.sim, self.player_eid) or ())
        debt_balance = int(self._player_justice_debt_balance())
        held = self._player_held_property_snapshot()
        held_site_name = str(held.get("property_name", "") or "").strip()
        held_site_id = str(held.get("property_id", "") or "").strip()
        current_property_id = str(current_prop.get("id", "") or "").strip() if current_prop else ""
        if held_site_id and held_site_name and current_property_id and held_site_id != current_property_id:
            lines.append(f"Released property is logged at {held_site_name}.")
        if debt_balance > 0:
            lines.append("Any banking service can take a justice-debt payment.")
        return [str(line).strip() for line in lines if str(line).strip()]

    def _player_funds_snapshot(self):
        carried_credits = int(self._player_cash_on_hand())
        wallet_credits = int(self._player_wallet_credits())
        bank_balance = int(self._player_bank_balance())
        debt_balance = int(self._player_debt_balance())
        return {
            "carried_credits": carried_credits,
            "wallet_credits": wallet_credits,
            "bank_balance": bank_balance,
            "debt_balance": debt_balance,
            "immediate_total": int(carried_credits + wallet_credits + bank_balance),
        }

    def _apply_player_finance_debt(self, amount, *, debt_key="justice_fines"):
        amount = int(max(0, amount or 0))
        if amount <= 0:
            if str(debt_key or "").strip().lower() == self.JUSTICE_DEBT_KEY:
                return 0, self._player_justice_debt_balance()
            return 0, self._player_debt_balance()
        profile = self._player_finance_profile(create=True)
        if str(debt_key or "").strip().lower() == self.JUSTICE_DEBT_KEY:
            before = int(self._player_justice_debt_balance())
        else:
            before = int(self._player_debt_balance())
        add_debt = getattr(profile, "add_debt", None)
        if callable(add_debt):
            add_debt(debt_key, amount)
            if str(debt_key or "").strip().lower() == self.JUSTICE_DEBT_KEY:
                return int(amount), int(self._player_justice_debt_balance())
            return int(amount), int(self._player_debt_balance())
        profile.debt_balance = int(max(0, getattr(profile, "debt_balance", 0) or 0)) + int(amount)
        return int(profile.debt_balance - before), int(profile.debt_balance)

    def _deduct_player_wallet_credits(self, amount):
        amount = int(max(0, amount or 0))
        assets = self._player_assets(create=False)
        before = int(max(0, getattr(assets, "credits", 0) or 0)) if assets is not None else 0
        if assets is None or amount <= 0 or before <= 0:
            return 0, before, before
        paid = min(before, amount)
        assets.credits = int(max(0, before - paid))
        return int(paid), before, int(assets.credits)

    def _deduct_player_bank_balance(self, amount):
        amount = int(max(0, amount or 0))
        profile = self._player_finance_profile(create=False)
        before = int(max(0, getattr(profile, "bank_balance", 0) or 0)) if profile is not None else 0
        if profile is None or amount <= 0 or before <= 0:
            return 0, before, before
        paid = min(before, amount)
        profile.bank_balance = int(max(0, before - paid))
        return int(paid), before, int(profile.bank_balance)

    def _collect_player_fine(self, amount):
        amount = int(max(0, amount or 0))
        inventory_before = int(self._player_cash_on_hand())
        wallet_credit_before = int(self._player_wallet_credits())
        bank_before = int(self._player_bank_balance())
        debt_before = int(self._player_justice_debt_balance())
        if amount <= 0:
            return {
                "fine_due": 0,
                "fine_paid": 0,
                "cash_fine_paid": 0,
                "wallet_fine_paid": 0,
                "bank_fine_paid": 0,
                "debt_added": 0,
                "fine_outstanding": 0,
                "wallet_credits_before": inventory_before,
                "wallet_credits_after": inventory_before,
                "asset_credits_before": wallet_credit_before,
                "asset_credits_after": wallet_credit_before,
                "bank_balance_before": bank_before,
                "bank_balance_after": bank_before,
                "debt_balance_before": debt_before,
                "debt_balance_after": debt_before,
            }

        remaining = int(amount)
        cash_paid, inventory_after, _snapshot_items = self._deduct_cash_from_live_inventory(self.player_eid, remaining)
        remaining = max(0, remaining - int(cash_paid))
        wallet_paid, _wallet_before, wallet_after = self._deduct_player_wallet_credits(remaining)
        remaining = max(0, remaining - int(wallet_paid))
        bank_paid, _bank_before, bank_after = self._deduct_player_bank_balance(remaining)
        remaining = max(0, remaining - int(bank_paid))
        debt_added = 0
        debt_after = debt_before
        if remaining > 0:
            debt_added, debt_after = self._apply_player_finance_debt(remaining, debt_key="justice_fines")
        return {
            "fine_due": int(amount),
            "fine_paid": int(cash_paid + wallet_paid + bank_paid),
            "cash_fine_paid": int(cash_paid),
            "wallet_fine_paid": int(wallet_paid),
            "bank_fine_paid": int(bank_paid),
            "debt_added": int(debt_added),
            "fine_outstanding": int(max(0, amount - (cash_paid + wallet_paid + bank_paid))),
            "wallet_credits_before": int(inventory_before),
            "wallet_credits_after": int(inventory_after),
            "asset_credits_before": int(wallet_credit_before),
            "asset_credits_after": int(wallet_after),
            "bank_balance_before": int(bank_before),
            "bank_balance_after": int(bank_after),
            "debt_balance_before": int(debt_before),
            "debt_balance_after": int(debt_after),
        }

    def _inventory_cash_total_from_entries(self, entries):
        total = 0
        for entry in list(entries or ()):
            item_id = str(entry.get("item_id", "") or "").strip().lower()
            if not is_credstick_item(item_id):
                continue
            total += credstick_total_credits(
                quantity=entry.get("quantity", 1),
                metadata=entry.get("metadata"),
            )
        return int(max(0, total))

    def _snapshot_inventory_items(self, eid):
        inventory = self.sim.ecs.get(Inventory).get(eid)
        if not inventory:
            return []
        items = []
        for entry in list(getattr(inventory, "items", ()) or ()):
            items.append({
                "instance_id": entry.get("instance_id"),
                "item_id": entry.get("item_id"),
                "quantity": int(max(1, int(entry.get("quantity", 1) or 1))),
                "owner_eid": entry.get("owner_eid"),
                "owner_tag": entry.get("owner_tag"),
                "metadata": dict(entry.get("metadata") or {}),
            })
        return items

    def _deduct_cash_from_inventory_entries(self, entries, amount):
        remaining = max(0, int(amount or 0))
        updated = []
        for entry in list(entries or ()):
            current = {
                "instance_id": entry.get("instance_id"),
                "item_id": entry.get("item_id"),
                "quantity": int(max(1, int(entry.get("quantity", 1) or 1))),
                "owner_eid": entry.get("owner_eid"),
                "owner_tag": entry.get("owner_tag"),
                "metadata": dict(entry.get("metadata") or {}),
            }
            item_id = str(current.get("item_id", "") or "").strip().lower()
            if remaining > 0 and is_credstick_item(item_id):
                total = credstick_total_credits(
                    quantity=current.get("quantity", 1),
                    metadata=current.get("metadata"),
                )
                paid = min(int(total), int(remaining))
                remaining -= int(paid)
                leftover = max(0, int(total) - int(paid))
                if leftover > 0:
                    current["metadata"] = prepare_item_stack_metadata(
                        item_id,
                        metadata={**current.get("metadata", {}), "stored_credits": int(leftover)},
                        quantity=current.get("quantity", 1),
                    )
                    updated.append(current)
                continue
            updated.append(current)
        fine_paid = max(0, int(amount or 0) - int(remaining))
        return updated, int(fine_paid), self._inventory_cash_total_from_entries(updated)

    def _deduct_cash_from_live_inventory(self, eid, amount):
        remaining = max(0, int(amount or 0))
        inventory = self.sim.ecs.get(Inventory).get(eid)
        if not inventory or remaining <= 0:
            snapshot_items = self._snapshot_inventory_items(eid)
            return 0, self._inventory_cash_total_from_entries(snapshot_items), snapshot_items

        for entry in list(getattr(inventory, "items", ()) or ()):
            if remaining <= 0:
                break
            item_id = str(entry.get("item_id", "") or "").strip().lower()
            if not is_credstick_item(item_id):
                continue
            total = credstick_total_credits(
                quantity=entry.get("quantity", 1),
                metadata=entry.get("metadata"),
            )
            if total <= 0:
                continue
            paid = min(int(total), int(remaining))
            remaining -= int(paid)
            leftover = max(0, int(total) - int(paid))
            if leftover <= 0:
                inventory.remove_item(
                    instance_id=entry.get("instance_id"),
                    quantity=int(entry.get("quantity", 1) or 1),
                )
                continue
            inventory.update_item_metadata(
                entry.get("instance_id"),
                {"stored_credits": int(leftover)},
                replace=False,
            )

        snapshot_items = self._snapshot_inventory_items(eid)
        fine_paid = max(0, int(amount or 0) - int(remaining))
        return int(fine_paid), self._inventory_cash_total_from_entries(snapshot_items), snapshot_items

    def _npc_fine_amount(self, snapshot):
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        tier = str(snapshot.get("wanted_tier", "clear")).strip().lower() or "clear"
        score = max(0, int(snapshot.get("active_score", 0) or 0))
        base = {
            "questioning": 8,
            "wanted": 22,
            "arrest_on_sight": 54,
        }.get(tier, 12)
        per_score = {
            "questioning": 1.0,
            "wanted": 1.5,
            "arrest_on_sight": 2.0,
        }.get(tier, 1.0)
        return int(max(base, min(180, round(base + (score * per_score)))))

    def _player_fine_amount(self, snapshot):
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        tier = str(snapshot.get("wanted_tier", "clear")).strip().lower() or "clear"
        score = max(0, int(snapshot.get("active_score", 0) or 0))
        base = {
            "questioning": 10,
            "wanted": 30,
            "arrest_on_sight": 72,
        }.get(tier, 12)
        per_score = {
            "questioning": 0.8,
            "wanted": 1.4,
            "arrest_on_sight": 2.1,
        }.get(tier, 1.0)
        return int(max(base, min(240, round(base + (score * per_score)))))

    def _player_booking_anchor(self, fallback_pos):
        if fallback_pos is None:
            return None
        anchor = _justice_booking_anchor_for(
            self.sim,
            self.player_eid,
            fallback_x=fallback_pos.x,
            fallback_y=fallback_pos.y,
        )
        if isinstance(anchor, dict):
            return anchor
        return {
            "x": int(fallback_pos.x),
            "y": int(fallback_pos.y),
            "chunk": tuple(self.sim.chunk_coords(int(fallback_pos.x), int(fallback_pos.y))),
            "incident": None,
            "fallback": True,
            "jurisdiction_key": "",
            "jurisdiction_name": "Justice Office",
            "settlement_name": "",
            "region_name": "",
        }

    def _justice_anchor_place_label(self, anchor):
        anchor = anchor if isinstance(anchor, dict) else {}
        settlement_name = str(anchor.get("settlement_name", "") or "").strip()
        region_name = str(anchor.get("region_name", "") or "").strip()
        jurisdiction_name = str(anchor.get("jurisdiction_name", "") or "").strip()
        if settlement_name:
            return settlement_name
        if region_name:
            return region_name
        if jurisdiction_name:
            return jurisdiction_name
        return "the local district"

    def _justice_surrender_quote(self, npc_eid, anchor):
        jurisdiction_name = str((anchor or {}).get("jurisdiction_name", "Justice Office") or "Justice Office").strip() or "Justice Office"
        place_label = self._justice_anchor_place_label(anchor)
        incident = (anchor or {}).get("incident") if isinstance((anchor or {}).get("incident"), dict) else {}
        incident_label = str(incident.get("label", "") or "").strip().lower() or "your record"
        rng = random.Random(
            f"{self.sim.seed}:justice-surrender:{int(npc_eid or 0)}:{jurisdiction_name}:{place_label}:{incident_label}"
        )
        templates = [
            f"By order of {jurisdiction_name}, drop it and surrender now.",
            f"Last warning. {place_label} law has you marked for {incident_label}.",
            f"Hands clear and on your knees. {jurisdiction_name} is taking you in.",
            f"Stand down. {place_label} justice wants you alive and compliant.",
        ]
        return rng.choice(templates)

    def _resolve_prompt_source_property(self, source_prop=None):
        if isinstance(source_prop, dict):
            return source_prop
        player_pos = self._position_for(self.player_eid)
        if player_pos is None or not hasattr(self.sim, "property_covering"):
            return None
        return self.sim.property_covering(player_pos.x, player_pos.y, player_pos.z)

    def _confiscation_summary_text(self, manifest):
        manifest = manifest if isinstance(manifest, dict) else {}
        weapon_units = int(manifest.get("weapon_units", 0) or 0)
        contraband_units = int(manifest.get("contraband_units", 0) or 0)
        stolen_units = int(manifest.get("stolen_units", 0) or 0)
        labels = [str(label).strip() for label in list(manifest.get("labels", ()) or ()) if str(label).strip()]
        if weapon_units <= 0 and contraband_units <= 0 and stolen_units <= 0:
            return "Any weapons, contraband, or stolen goods on you will be seized during booking."

        seized_bits = []
        if weapon_units > 0:
            seized_bits.append(f"{weapon_units} weapon" + ("s" if weapon_units != 1 else ""))
        if contraband_units > 0:
            seized_bits.append(f"{contraband_units} contraband item" + ("s" if contraband_units != 1 else ""))
        if stolen_units > 0:
            seized_bits.append(f"{stolen_units} stolen item" + ("s" if stolen_units != 1 else ""))
        summary = "Booking seizure preview: " + ", ".join(seized_bits) + "."
        if labels:
            summary += f" Likely taken: {', '.join(labels[:3])}."
        return summary

    def _open_player_surrender_prompt(self, npc_eid, *, snapshot=None, source_prop=None, respect_cooldown=False):
        try:
            npc_eid = int(npc_eid)
        except (TypeError, ValueError):
            return False
        if respect_cooldown and self._officer_surrender_offer_on_cooldown(npc_eid):
            return False
        snapshot = snapshot if isinstance(snapshot, dict) else self._player_bookable_snapshot()
        player_pos = self._position_for(self.player_eid)
        if snapshot is None or player_pos is None or _actor_in_live_combat(self.sim, self.player_eid):
            return False

        source_prop = self._resolve_prompt_source_property(source_prop)
        anchor = self._player_booking_anchor(player_pos)
        if not isinstance(anchor, dict):
            return False
        tier = str(snapshot.get("wanted_tier", "clear")).strip().lower() or "clear"
        hold_hours = float(self.BOOKING_HOURS_BY_TIER.get(tier, 1.0))
        fine_due = int(self._player_fine_amount(snapshot))
        funds = self._player_funds_snapshot()
        manifest = self._player_confiscation_manifest(remove=False)
        place_label = self._justice_anchor_place_label(anchor)
        jurisdiction_name = str(anchor.get("jurisdiction_name", "Justice Office") or "Justice Office").strip() or "Justice Office"
        booking_line = f"If you surrender, {jurisdiction_name} will book you near {place_label} for about {hold_hours:g}h."
        if fine_due > 0:
            if int(funds.get("immediate_total", 0) or 0) > 0:
                fund_bits = []
                if int(funds.get("carried_credits", 0) or 0) > 0:
                    fund_bits.append(f"carried {int(funds.get('carried_credits', 0) or 0)}c")
                if int(funds.get("wallet_credits", 0) or 0) > 0:
                    fund_bits.append(f"wallet {int(funds.get('wallet_credits', 0) or 0)}c")
                if int(funds.get("bank_balance", 0) or 0) > 0:
                    fund_bits.append(f"bank {int(funds.get('bank_balance', 0) or 0)}c")
                booking_line += f" Fine estimate: {fine_due}c"
                if fund_bits:
                    booking_line += f" ({', '.join(fund_bits)})"
                booking_line += "."
            else:
                booking_line += f" Fine estimate: {fine_due}c. Unpaid balance will be filed as debt."

        state = self._dialog_ui_state()
        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "open": True,
            "kind": self.SURRENDER_DIALOG_KIND,
            "npc_eid": npc_eid,
            "property_id": source_prop.get("id") if isinstance(source_prop, dict) else None,
            "title": f"Justice Order: {_entity_display_name(self.sim, npc_eid, title_case=True) or 'Officer'}",
            "subtitle": jurisdiction_name,
            "transcript": [
                self._justice_surrender_quote(npc_eid, anchor),
                booking_line,
                self._confiscation_summary_text(manifest),
                "Refusal will provoke immediate force.",
            ],
            "topics": [
                {"id": "surrender", "label": "Surrender now"},
                {"id": "resist", "label": "Resist arrest"},
            ],
            "selected_index": 0,
            "scroll": 0,
            "hint": "Surrender accepts booking. Resist triggers violence.",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
        })
        self.player_surrender_prompt = {
            "npc_eid": npc_eid,
            "source_prop_id": source_prop.get("id") if isinstance(source_prop, dict) else None,
            "opened_tick": int(getattr(self.sim, "tick", 0)),
            "jurisdiction_key": str(anchor.get("jurisdiction_key", "") or "").strip().lower(),
            "jurisdiction_name": jurisdiction_name,
            "anchor_x": int(anchor.get("x", player_pos.x) or player_pos.x),
            "anchor_y": int(anchor.get("y", player_pos.y) or player_pos.y),
            "fallback": bool(anchor.get("fallback", False)),
        }
        self._mark_officer_surrender_prompt_opened(npc_eid)
        return True

    def _close_player_surrender_prompt(self):
        state = self._dialog_ui_state()
        if bool(state.get("open")) and str(state.get("kind", "")).strip().lower() == self.SURRENDER_DIALOG_KIND:
            self.sim.set_time_paused(False, reason="dialog")
            self._reset_dialog_ui(state)
        self.player_surrender_prompt = None
        return state

    def _justice_enforcers_near_player(self, *, primary_eid=None, radius=None):
        player_pos = self._position_for(self.player_eid)
        if player_pos is None:
            return []
        radius = max(1, int(radius or max(self.DETENTION_RADIUS, 8)))
        positions = self.sim.ecs.get(Position)
        candidates = []
        for eid, pos in positions.items():
            if eid == self.player_eid or pos.z != player_pos.z:
                continue
            dist = _manhattan(pos.x, pos.y, player_pos.x, player_pos.y)
            if dist <= 0 or dist > radius:
                continue
            enforcer, law_drive, priority = self._actor_is_enforcer(eid)
            if not enforcer:
                continue
            if int(eid) != int(primary_eid or -1):
                if not _shared_observer_can_see_position(
                    self.sim,
                    observer_eid=eid,
                    observer_x=pos.x,
                    observer_y=pos.y,
                    observer_z=pos.z,
                    target_x=player_pos.x,
                    target_y=player_pos.y,
                    target_z=player_pos.z,
                    radius=max(4, radius + 2),
                ):
                    continue
            candidates.append((0 if int(eid) == int(primary_eid or -1) else 1, dist, -priority, -law_drive, int(eid)))
        candidates.sort()
        return [eid for _primary, _dist, _priority, _law_drive, eid in candidates]

    def _escalate_player_surrender_refusal(self, *, by_eid=None, source_prop=None, snapshot=None):
        snapshot = snapshot if isinstance(snapshot, dict) else self._player_bookable_snapshot()
        player_pos = self._position_for(self.player_eid)
        if snapshot is None or player_pos is None:
            return False
        if by_eid is not None:
            self._mark_officer_surrender_offer_cooldown(by_eid)
        source_prop = self._resolve_prompt_source_property(source_prop)
        severity = max(24, int(snapshot.get("active_score", 0) or 0) + 12)
        self._record_incident(
            self.player_eid,
            incident_type="resisting_custody",
            severity=severity,
            source_event="justice_surrender_choice",
            property_id=(source_prop or {}).get("id") if isinstance(source_prop, dict) else None,
            x=player_pos.x,
            y=player_pos.y,
            witnessed=True,
            note="player_refused_surrender",
        )

        target = (player_pos.x, player_pos.y, player_pos.z)
        enforcers = self._justice_enforcers_near_player(primary_eid=by_eid, radius=max(self.DETENTION_RADIUS + 2, 10))
        primary = int(by_eid) if by_eid is not None else (enforcers[0] if enforcers else None)
        for enforcer_eid in enforcers:
            ai = self.sim.ecs.get(AI).get(enforcer_eid)
            will = self.sim.ecs.get(NPCWill).get(enforcer_eid)
            if ai is not None and will is not None:
                _sync_ai_intent(
                    ai,
                    will,
                    self.sim.tick,
                    "protecting",
                    score=92.0,
                    target=target,
                    target_eid=self.player_eid,
                )
                continue
            if ai is not None:
                ai.state = "protecting"
                ai.target = target
                ai.target_eid = self.player_eid
            if will is not None:
                will.intent = "protecting"
                will.score = 92.0
                will.target = target
                will.target_eid = self.player_eid
                will.last_tick = self.sim.tick

        if primary is not None:
            self.sim.emit(Event(
                "npc_defend_property",
                npc_eid=primary,
                offender_eid=self.player_eid,
                property_id=(source_prop or {}).get("id") if isinstance(source_prop, dict) else None,
                owner_eid=(source_prop or {}).get("owner_eid") if isinstance(source_prop, dict) else None,
                defender_reason="law",
                threat_type="justice_resistance",
                severity_label="resisting_custody",
                ingress_kind="custody_refusal",
                aperture_kind="",
                ingress_method="custody_refusal",
            ))
        return bool(enforcers)

    def _world_streaming_system(self):
        current = getattr(self, "_streaming_system", None)
        if current is not None and hasattr(current, "_ensure_chunk_properties"):
            return current
        for system in getattr(self.sim, "systems", ()):
            if hasattr(system, "_ensure_chunk_properties") and hasattr(system, "_ensure_chunk_population"):
                self._streaming_system = system
                return system
        self._streaming_system = WorldStreamingSystem(self.sim, self.player_eid)
        return self._streaming_system

    def _props_in_chunk(self, chunk):
        if not isinstance(chunk, (tuple, list)) or len(chunk) < 2:
            return []
        key = (int(chunk[0]), int(chunk[1]))
        props = []
        seen = set()
        for record in tuple(getattr(self.sim, "chunk_property_records", {}).get(key, ()) or ()):
            prop_id = str((record or {}).get("id", "") or "").strip()
            if not prop_id:
                continue
            prop = self.sim.properties.get(prop_id)
            if not isinstance(prop, dict):
                continue
            seen.add(prop_id)
            props.append(prop)
        for prop_id, prop in tuple(getattr(self.sim, "properties", {}).items()):
            if prop_id in seen or not isinstance(prop, dict):
                continue
            if _property_chunk_key(self.sim, prop) == key:
                props.append(prop)
        return props

    def _chunk_contains_archetype(self, chunk, allowed_archetypes):
        if not isinstance(chunk, dict):
            return False
        allowed = {
            str(archetype or "").strip().lower()
            for archetype in tuple(allowed_archetypes or ())
            if str(archetype or "").strip()
        }
        if not allowed:
            return False
        for block in tuple(chunk.get("blocks", ()) or ()):
            if not isinstance(block, dict):
                continue
            for building in tuple(block.get("buildings", ()) or ()):
                if not isinstance(building, dict):
                    continue
                archetype = str(building.get("archetype", "") or "").strip().lower()
                if archetype in allowed:
                    return True
        for site in tuple(chunk.get("sites", ()) or ()):
            if not isinstance(site, dict):
                continue
            kind = str(site.get("kind", "") or "").strip().lower()
            if kind in allowed:
                return True
        return False

    def _ensure_search_chunk_ready(self, chunk):
        if not isinstance(chunk, (tuple, list)) or len(chunk) < 2:
            return []
        key = (int(chunk[0]), int(chunk[1]))
        self.sim.ensure_chunk_terrain(key[0], key[1])
        streamer = self._world_streaming_system()
        streamer._ensure_chunk_properties(key[0], key[1])
        return self._props_in_chunk(key)

    def _justice_search_chunk_bounds(self):
        # City streaming can realize chunks well beyond the initial viewport,
        # so the tilemap width/height are not reliable world bounds here.
        return None

    def _justice_search_max_radius(self, base_chunk, bounds):
        base_radius = max(0, int(self.JUSTICE_SITE_SEARCH_RADIUS))
        if not (isinstance(base_chunk, (tuple, list)) and len(base_chunk) >= 2 and isinstance(bounds, (tuple, list)) and len(bounds) >= 4):
            return max(base_radius, base_radius * 2)
        base_cx = int(base_chunk[0])
        base_cy = int(base_chunk[1])
        min_cx, max_cx, min_cy, max_cy = (
            int(bounds[0]),
            int(bounds[1]),
            int(bounds[2]),
            int(bounds[3]),
        )
        corners = (
            (min_cx, min_cy),
            (min_cx, max_cy),
            (max_cx, min_cy),
            (max_cx, max_cy),
        )
        return max(
            0,
            max(
                _manhattan(base_cx, base_cy, corner_cx, corner_cy)
                for corner_cx, corner_cy in corners
            ),
        )

    def _justice_chunk_ring(self, base_chunk, chunk_dist, *, bounds=None):
        if not isinstance(base_chunk, (tuple, list)) or len(base_chunk) < 2:
            return
        base_cx = int(base_chunk[0])
        base_cy = int(base_chunk[1])
        chunk_dist = max(0, int(chunk_dist))
        min_cx = max_cx = min_cy = max_cy = None
        if isinstance(bounds, (tuple, list)) and len(bounds) >= 4:
            min_cx = int(bounds[0])
            max_cx = int(bounds[1])
            min_cy = int(bounds[2])
            max_cy = int(bounds[3])
        for cx in range(base_cx - chunk_dist, base_cx + chunk_dist + 1):
            if min_cx is not None and (cx < min_cx or cx > max_cx):
                continue
            for cy in range(base_cy - chunk_dist, base_cy + chunk_dist + 1):
                if min_cy is not None and (cy < min_cy or cy > max_cy):
                    continue
                if abs(cx - base_cx) + abs(cy - base_cy) != chunk_dist:
                    continue
                yield (int(cx), int(cy))

    def _find_justice_property(self, *, allowed_archetypes=(), source_prop=None, origin_x=None, origin_y=None):
        allowed = tuple(
            str(archetype or "").strip().lower()
            for archetype in tuple(allowed_archetypes or ())
            if str(archetype or "").strip()
        )
        if not allowed:
            return source_prop if isinstance(source_prop, dict) else None

        allowed_set = set(allowed)
        if isinstance(source_prop, dict) and _property_archetype(source_prop) in allowed_set:
            return source_prop

        try:
            base_x = int(origin_x)
            base_y = int(origin_y)
        except (TypeError, ValueError):
            pos = self._position_for(self.player_eid)
            base_x = int(getattr(pos, "x", 0))
            base_y = int(getattr(pos, "y", 0))
        base_chunk = self.sim.chunk_coords(base_x, base_y)
        archetype_rank = {label: index for index, label in enumerate(allowed)}
        def _rank_candidate(prop):
            archetype = _property_archetype(prop)
            if archetype not in allowed_set:
                return None
            anchor = _property_focus_position(prop)
            if not anchor:
                anchor = (int(prop.get("x", 0)), int(prop.get("y", 0)), int(prop.get("z", 0)))
            chunk = self.sim.chunk_coords(int(anchor[0]), int(anchor[1]))
            same_chunk = 0 if tuple(chunk) == tuple(base_chunk) else 1
            dist = _manhattan(base_x, base_y, int(anchor[0]), int(anchor[1]))
            return (
                same_chunk,
                int(archetype_rank.get(archetype, len(archetype_rank))),
                dist,
                str(prop.get("id", "")),
                prop,
            )

        candidates = []
        for prop in self.sim.properties.values():
            ranked = _rank_candidate(prop)
            if ranked is not None:
                candidates.append(ranked)
        if not candidates:
            bounds = self._justice_search_chunk_bounds()
            local_radius = max(0, int(self.JUSTICE_SITE_SEARCH_RADIUS))
            max_radius = max(local_radius, self._justice_search_max_radius(base_chunk, bounds))
            for chunk_dist in range(0, max_radius + 1):
                ring_candidates = []
                for key in self._justice_chunk_ring(base_chunk, chunk_dist, bounds=bounds):
                    chunk = self.sim.world.get_chunk(key[0], key[1])
                    if not self._chunk_contains_archetype(chunk, allowed_set):
                        continue
                    for prop in self._ensure_search_chunk_ready(key):
                        ranked = _rank_candidate(prop)
                        if ranked is not None:
                            ring_candidates.append(ranked)
                if ring_candidates:
                    ring_candidates.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
                    return ring_candidates[0][4]
            return source_prop if isinstance(source_prop, dict) and _property_archetype(source_prop) in allowed_set else None
        candidates.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
        return candidates[0][4]

    def _property_room_candidates(self, prop, *, preferred_room_kinds=()):
        if not isinstance(prop, dict):
            return []
        cover_coords = getattr(self.sim, "_property_cover_coords", None)
        if not callable(cover_coords):
            return []

        preferred = tuple(
            str(room_kind or "").strip().lower()
            for room_kind in tuple(preferred_room_kinds or ())
            if str(room_kind or "").strip()
        )
        preferred_index = {room_kind: index for index, room_kind in enumerate(preferred)}
        anchor = _property_focus_position(prop)
        if not anchor:
            anchor = (int(prop.get("x", 0)), int(prop.get("y", 0)), int(prop.get("z", 0)))
        candidates = []
        for x, y, z in tuple(cover_coords(prop) or ()):
            try:
                x = int(x)
                y = int(y)
                z = int(z)
            except (TypeError, ValueError):
                continue
            if not self.sim.tilemap.is_walkable(x, y, z):
                continue
            covered = self.sim.property_covering(x, y, z)
            if not (covered and covered.get("id") == prop.get("id")):
                continue
            structure = self.sim.structure_at(x, y, z) if hasattr(self.sim, "structure_at") else None
            room_kind = str((structure or {}).get("room_kind", "") or "").strip().lower()
            room_rank = preferred_index.get(room_kind, len(preferred_index))
            candidates.append({
                "pos": (x, y, z),
                "room_kind": room_kind,
                "room_rank": int(room_rank),
                "dist": _manhattan(int(anchor[0]), int(anchor[1]), x, y),
            })

        if preferred:
            matching = [candidate for candidate in candidates if candidate["room_rank"] < len(preferred)]
            if matching:
                return matching
        return candidates

    def _pick_property_room_tile(self, prop, *, preferred_room_kinds=(), exclude_eid=None, claim_prefix=""):
        candidates = self._property_room_candidates(prop, preferred_room_kinds=preferred_room_kinds)
        if not candidates:
            x, y, z = self._booking_anchor(prop)
            return int(x), int(y), int(z), ""

        claims = Counter()
        for record in self._npc_custody_records().values():
            if not isinstance(record, dict) or not bool(record.get("active", False)):
                continue
            if str(record.get("claim_prefix", "") or "").strip().lower() != str(claim_prefix or "").strip().lower():
                continue
            tile = (
                int(record.get("custody_x", 0) or 0),
                int(record.get("custody_y", 0) or 0),
                int(record.get("custody_z", 0) or 0),
            )
            claims[tile] += 1

        best = None
        best_rank = None
        for candidate in candidates:
            pos = candidate["pos"]
            occupants = [
                other_eid
                for other_eid in tuple(self.sim.tilemap.entities_at(pos[0], pos[1], pos[2]) or ())
                if exclude_eid is None or int(other_eid) != int(exclude_eid)
            ]
            rank = (
                int(candidate.get("room_rank", 0) or 0),
                int(claims.get(pos, 0)),
                len(occupants),
                int(candidate.get("dist", 0) or 0),
                int(pos[2]),
                int(pos[1]),
                int(pos[0]),
            )
            if best_rank is None or rank < best_rank:
                best = candidate
                best_rank = rank

        chosen = best or candidates[0]
        pos = chosen["pos"]
        return int(pos[0]), int(pos[1]), int(pos[2]), str(chosen.get("room_kind", "") or "").strip().lower()

    def _custody_room_kinds_for(self, prop):
        archetype = _property_archetype(prop)
        return self.CUSTODY_ROOM_KINDS_BY_ARCHETYPE.get(archetype, self.CUSTODY_ROOM_KINDS_BY_ARCHETYPE["default"])

    def _release_room_kinds_for(self, prop):
        archetype = _property_archetype(prop)
        return self.RELEASE_ROOM_KINDS_BY_ARCHETYPE.get(archetype, self.RELEASE_ROOM_KINDS_BY_ARCHETYPE["default"])

    def _npc_release_anchor(self, offender_eid, *, origin_pos=None, custody_prop=None):
        routine = self.sim.ecs.get(NPCRoutine).get(offender_eid)
        newcomer = self.sim.ecs.get(NPCSettlement).get(offender_eid)
        property_ids = []
        if newcomer is not None:
            property_ids.extend((
                str(getattr(newcomer, "home_property_id", "") or "").strip(),
                str(getattr(newcomer, "work_property_id", "") or "").strip(),
            ))
        for property_id in property_ids:
            prop = self.sim.properties.get(property_id)
            if not isinstance(prop, dict):
                continue
            anchor = _property_focus_position(prop)
            if anchor:
                return self._find_walkable_near(anchor[0], anchor[1], anchor[2], radius=8)
        for anchor in (
            getattr(routine, "home", None) if routine is not None else None,
            getattr(routine, "work", None) if routine is not None else None,
        ):
            if isinstance(anchor, (tuple, list)) and len(anchor) >= 3:
                return self._find_walkable_near(anchor[0], anchor[1], anchor[2], radius=8)
        if origin_pos is not None:
            return self._find_walkable_near(origin_pos.x, origin_pos.y, origin_pos.z, radius=8)
        if isinstance(custody_prop, dict):
            x, y, z, _room_kind = self._pick_property_room_tile(
                custody_prop,
                preferred_room_kinds=self._release_room_kinds_for(custody_prop),
                claim_prefix="release",
            )
            return int(x), int(y), int(z)
        return 0, 0, 0

    def _custody_should_clear_employment(self, record):
        if not isinstance(record, dict):
            return False
        archetype = str(record.get("custody_property_archetype", "") or "").strip().lower()
        before_tier = str(record.get("before_tier", "") or "").strip().lower()
        return archetype == "prison" or before_tier == "arrest_on_sight"

    def _terminate_npc_employment_for_custody(self, offender_eid, record):
        if not self._custody_should_clear_employment(record):
            if isinstance(record, dict):
                record["employment_terminated"] = False
            return False

        occupation = self.sim.ecs.get(Occupation).get(offender_eid)
        routine = self.sim.ecs.get(NPCRoutine).get(offender_eid)
        newcomer = self.sim.ecs.get(NPCSettlement).get(offender_eid)
        ai = self.sim.ecs.get(AI).get(offender_eid)
        workplace = getattr(occupation, "workplace", None) if occupation is not None else None
        if not isinstance(workplace, dict):
            if isinstance(record, dict):
                record["employment_terminated"] = False
            return False

        former_property_id = str(workplace.get("property_id", "") or "").strip()
        former_building_id = str(workplace.get("building_id", "") or "").strip()
        former_career = str(getattr(occupation, "career", "") or "").strip().lower()
        former_org_eid = None
        raw_org_eid = workplace.get("organization_eid")
        try:
            former_org_eid = int(raw_org_eid) if raw_org_eid is not None else None
        except (TypeError, ValueError):
            former_org_eid = None

        employment = actor_player_business_employment(
            self.sim,
            offender_eid,
            owner_eid=getattr(self.sim, "player_eid", None),
        )
        if employment is not None:
            fire_actor_from_player_business(
                self.sim,
                getattr(self.sim, "player_eid", None),
                offender_eid,
                prop=employment.get("prop"),
            )
        else:
            if former_org_eid is not None:
                affiliations = self.sim.ecs.get(OrganizationAffiliations).get(offender_eid)
                membership = affiliations.memberships.get(int(former_org_eid)) if affiliations else None
                if isinstance(membership, dict):
                    site_property_id = str(membership.get("site_property_id", "") or "").strip()
                    site_building_id = str(membership.get("site_building_id", "") or "").strip()
                    if (
                        (former_property_id and site_property_id == former_property_id)
                        or (former_building_id and site_building_id == former_building_id)
                    ):
                        membership["active"] = False
                        membership["site_property_id"] = None
                        membership["site_building_id"] = None
            occupation.workplace = None
            occupation.shift_start = None
            occupation.shift_end = None
            if former_career not in {"resident", "lodger", "drifter"}:
                occupation.career = "unemployed"
            if routine is not None:
                routine.work = None
            if ai is not None and str(getattr(ai, "role", "") or "").strip().lower() in {"worker", "guard"}:
                ai.role = "civilian"

        if newcomer is not None:
            newcomer.work_property_id = ""
            newcomer.employment_status = "unemployed"
            newcomer.last_job_tick = int(getattr(self.sim, "tick", 0))
            if str(getattr(newcomer, "housing_status", "") or "").strip().lower() in {"housing"}:
                newcomer.phase = "settling"
            elif str(getattr(newcomer, "housing_status", "") or "").strip().lower() in {"lodging", "shelter"}:
                newcomer.phase = "lodged"
            else:
                newcomer.phase = "drifting" if bool(getattr(newcomer, "drift_preferred", False)) else "arriving"

        if isinstance(record, dict):
            record["employment_terminated"] = True
            record["former_work_property_id"] = former_property_id
            record["former_work_building_id"] = former_building_id
            record["former_work_organization_eid"] = former_org_eid
            record["former_career"] = former_career
        return True

    def _move_npc_to_custody(self, offender_eid, record):
        pos = self._position_for(offender_eid)
        if pos is None or not isinstance(record, dict):
            return False
        self._teleport_entity(
            offender_eid,
            pos,
            int(record.get("custody_x", pos.x)),
            int(record.get("custody_y", pos.y)),
            int(record.get("custody_z", pos.z)),
            reason="npc_custody_transfer",
        )
        _track_entity_in_chunk_population(self.sim, offender_eid)

        ai = self.sim.ecs.get(AI).get(offender_eid)
        will = self.sim.ecs.get(NPCWill).get(offender_eid)
        hold_target = (
            int(record.get("custody_x", pos.x)),
            int(record.get("custody_y", pos.y)),
            int(record.get("custody_z", pos.z)),
        )
        if ai is not None and will is not None:
            _sync_ai_intent(
                ai,
                will,
                self.sim.tick,
                "holding",
                score=88.0,
                target=hold_target,
                target_eid=None,
            )
        else:
            if ai is not None:
                ai.state = "holding"
                ai.target = hold_target
                ai.target_eid = None
            if will is not None:
                will.intent = "holding"
                will.score = 88.0
                will.target = hold_target
                will.target_eid = None
                will.last_tick = self.sim.tick

        suppression = self.sim.ecs.get(SuppressionState).get(offender_eid)
        if suppression is not None:
            suppression.surrendered = False
            suppression.surrender_tick = -1
        self._terminate_npc_employment_for_custody(offender_eid, record)
        return True

    def _release_npc_from_custody(self, offender_eid, record):
        pos = self._position_for(offender_eid)
        if pos is not None and isinstance(record, dict):
            self._teleport_entity(
                offender_eid,
                pos,
                int(record.get("release_x", pos.x)),
                int(record.get("release_y", pos.y)),
                int(record.get("release_z", pos.z)),
                reason="npc_custody_release",
            )
            _track_entity_in_chunk_population(self.sim, offender_eid)

        ai = self.sim.ecs.get(AI).get(offender_eid)
        will = self.sim.ecs.get(NPCWill).get(offender_eid)
        if ai is not None:
            ai.state = "idle"
            ai.target = None
            ai.target_eid = None
        if will is not None:
            will.intent = "idle"
            will.score = 0.0
            will.target = None
            will.target_eid = None
            will.last_tick = self.sim.tick

        suppression = self.sim.ecs.get(SuppressionState).get(offender_eid)
        if suppression is not None:
            suppression.surrendered = False
            suppression.surrender_tick = -1
        newcomer = self.sim.ecs.get(NPCSettlement).get(offender_eid)
        if newcomer is not None and bool((record or {}).get("employment_terminated", False)):
            newcomer.last_job_tick = int(getattr(self.sim, "tick", 0))
        return pos is not None

    def _store_npc_custody_record(self, offender_eid, snapshot, *, held_by_eid=None, pos=None):
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        tier = str(snapshot.get("wanted_tier", "wanted")).strip().lower() or "wanted"
        if tier not in {"wanted", "arrest_on_sight"}:
            tier = "wanted"
        hold_ticks = self._hours_to_ticks(self.NPC_BOOKING_HOURS_BY_TIER.get(tier, 4.0))
        if hold_ticks <= 0:
            hold_ticks = self._hours_to_ticks(4.0)

        origin_x = int(getattr(pos, "x", 0) if pos is not None else 0)
        origin_y = int(getattr(pos, "y", 0) if pos is not None else 0)
        custody_prop = self._find_justice_property(
            allowed_archetypes=self.NPC_CUSTODY_ARCHETYPES_BY_TIER.get(tier, ("jail",)),
            origin_x=origin_x,
            origin_y=origin_y,
        )
        if custody_prop is None:
            custody_prop = self._find_booking_property(origin_x=origin_x, origin_y=origin_y)
        custody_x, custody_y, custody_z, custody_room_kind = self._pick_property_room_tile(
            custody_prop,
            preferred_room_kinds=self._custody_room_kinds_for(custody_prop),
            exclude_eid=offender_eid,
            claim_prefix="custody",
        )
        release_x, release_y, release_z = self._npc_release_anchor(
            offender_eid,
            origin_pos=pos,
            custody_prop=custody_prop,
        )
        inventory_items = self._snapshot_inventory_items(offender_eid)
        wallet_before = self._inventory_cash_total_from_entries(inventory_items)
        record = {
            "eid": int(offender_eid),
            "active": True,
            "start_tick": int(getattr(self.sim, "tick", 0)),
            "hold_until_tick": int(getattr(self.sim, "tick", 0)) + int(hold_ticks),
            "hold_ticks": int(hold_ticks),
            "held_by_eid": held_by_eid,
            "booking_property_id": (custody_prop or {}).get("id") if isinstance(custody_prop, dict) else None,
            "booking_property_name": str((custody_prop or {}).get("name", "Justice Office") if isinstance(custody_prop, dict) else "Justice Office").strip() or "Justice Office",
            "booking_x": int(custody_x),
            "booking_y": int(custody_y),
            "booking_z": int(custody_z),
            "custody_property_id": (custody_prop or {}).get("id") if isinstance(custody_prop, dict) else None,
            "custody_property_archetype": _property_archetype(custody_prop) if isinstance(custody_prop, dict) else "",
            "custody_x": int(custody_x),
            "custody_y": int(custody_y),
            "custody_z": int(custody_z),
            "custody_room_kind": str(custody_room_kind or "").strip().lower(),
            "claim_prefix": "custody",
            "origin_x": int(origin_x),
            "origin_y": int(origin_y),
            "origin_z": int(getattr(pos, "z", 0) if pos is not None else 0),
            "release_x": int(release_x),
            "release_y": int(release_y),
            "release_z": int(release_z),
            "before_tier": tier,
            "before_score": int(snapshot.get("active_score", 0) or 0),
            "release_score": int(self._booking_release_score(snapshot)),
            "fine_due": int(self._npc_fine_amount(snapshot)),
            "fine_paid": 0,
            "wallet_credits_before": int(wallet_before),
            "wallet_credits_after": int(wallet_before),
            "inventory_items": inventory_items,
        }
        self._npc_custody_records()[str(int(offender_eid))] = record
        return record

    def _find_auto_arrest_enforcer(self, snapshot):
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        tier = str(snapshot.get("wanted_tier", "clear")).strip().lower() or "clear"
        radius = int(self.PLAYER_AUTO_ARREST_RADIUS_BY_TIER.get(tier, 0))
        if radius <= 0:
            return None
        player_pos = self._position_for(self.player_eid)
        if player_pos is None or _entity_is_downed(self.sim, self.player_eid):
            return None

        positions = self.sim.ecs.get(Position)
        best = None
        best_rank = None
        for eid, pos in positions.items():
            if eid == self.player_eid or pos.z != player_pos.z:
                continue
            dist = _manhattan(pos.x, pos.y, player_pos.x, player_pos.y)
            if dist <= 0 or dist > radius:
                continue
            enforcer, law_drive, priority = self._actor_is_enforcer(eid)
            if not enforcer:
                continue
            if not _shared_observer_can_see_position(
                self.sim,
                observer_eid=eid,
                observer_x=pos.x,
                observer_y=pos.y,
                observer_z=pos.z,
                target_x=player_pos.x,
                target_y=player_pos.y,
                target_z=player_pos.z,
                radius=max(4, radius + 2),
            ):
                continue
            rank = (dist, -priority, -law_drive, int(eid))
            if best_rank is None or rank < best_rank:
                best = int(eid)
                best_rank = rank
        return best

    def _booking_property_allowed(self, prop):
        return isinstance(prop, dict) and _property_archetype(prop) in set(self.BOOKING_ARCHETYPES)

    def _find_booking_property(self, *, source_prop=None, origin_x=None, origin_y=None):
        return self._find_justice_property(
            allowed_archetypes=self.BOOKING_ARCHETYPES,
            source_prop=source_prop,
            origin_x=origin_x,
            origin_y=origin_y,
        )

    def _booking_anchor(self, prop, fallback_pos=None):
        if isinstance(prop, dict):
            anchor = _property_focus_position(prop)
            if anchor:
                return self._find_walkable_near(anchor[0], anchor[1], anchor[2], radius=8)
            return self._find_walkable_near(
                int(prop.get("x", 0)),
                int(prop.get("y", 0)),
                int(prop.get("z", 0)),
                radius=8,
            )
        if fallback_pos is not None:
            return self._find_walkable_near(fallback_pos.x, fallback_pos.y, fallback_pos.z, radius=4)
        return 0, 0, 0

    def _booking_release_score(self, snapshot):
        tier = str((snapshot or {}).get("wanted_tier", "clear")).strip().lower() or "clear"
        score = max(0, int((snapshot or {}).get("active_score", 0) or 0))
        if tier == "questioning":
            return 0
        if tier == "wanted":
            return min(score, 5)
        if tier == "arrest_on_sight":
            return min(score, 12)
        return score

    def _emit_removed_gear_events(self, eid, removed_entry, *, reason):
        changes = _unlink_removed_item_from_gear(self.sim, eid, removed_entry, item_catalog=ITEM_CATALOG)
        if changes.get("armor_name"):
            self.sim.emit(Event(
                "armor_removed",
                eid=eid,
                item_id=changes.get("armor_item_id"),
                armor_name=changes["armor_name"],
                reason=reason,
            ))
        if changes.get("weapon_id"):
            self.sim.emit(Event(
                "weapon_removed",
                eid=eid,
                weapon_id=changes["weapon_id"],
                weapon_name=changes["weapon_name"],
                reason=reason,
            ))
        if changes.get("disguise_name"):
            self.sim.emit(Event(
                "disguise_removed",
                eid=eid,
                item_id=changes.get("disguise_item_id"),
                item_name=changes["disguise_name"],
                reason=reason,
            ))
        if changes.get("container_name"):
            self.sim.emit(Event(
                "container_removed",
                eid=eid,
                item_id=changes.get("container_item_id"),
                item_name=changes["container_name"],
                reason=reason,
            ))

    def _player_confiscation_manifest(self, *, remove=False):
        inventory = self.sim.ecs.get(Inventory).get(self.player_eid)
        if not inventory:
            return {
                "confiscated_units": 0,
                "held_units": 0,
                "forfeited_units": 0,
                "illegal_units": 0,
                "restricted_units": 0,
                "contraband_units": 0,
                "stolen_units": 0,
                "weapon_units": 0,
                "held_entries": (),
                "forfeited_entries": (),
                "labels": (),
                "held_labels": (),
                "forfeited_labels": (),
            }

        confiscated_units = 0
        held_units = 0
        forfeited_units = 0
        illegal_units = 0
        restricted_units = 0
        contraband_units = 0
        stolen_units = 0
        weapon_units = 0
        labels = []
        held_labels = []
        forfeited_labels = []
        held_entries = []
        forfeited_entries = []
        for entry in list(getattr(inventory, "items", ()) or ()):
            hold_policy = self._justice_item_hold_policy(entry)
            if not bool(hold_policy.get("seized")):
                continue

            quantity = max(1, int(entry.get("quantity", 1) or 1))
            removed = entry
            if remove:
                removed = inventory.remove_item(instance_id=entry.get("instance_id"), quantity=quantity)
                if not removed:
                    continue
            removed_qty = max(1, int(removed.get("quantity", quantity) or quantity))
            item_id = str(removed.get("item_id", entry.get("item_id", "")) or "").strip().lower()
            metadata = removed.get("metadata") if isinstance(removed.get("metadata"), dict) else {}
            item_name = item_display_name(item_id, metadata=metadata, item_catalog=ITEM_CATALOG)
            confiscated_units += removed_qty
            if bool(hold_policy.get("hold_for_release")):
                held_units += removed_qty
                held_entries.append({
                    "instance_id": removed.get("instance_id"),
                    "item_id": item_id,
                    "quantity": removed_qty,
                    "owner_eid": removed.get("owner_eid"),
                    "owner_tag": removed.get("owner_tag"),
                    "metadata": dict(metadata),
                })
                held_labels.append(item_name)
            if bool(hold_policy.get("forfeit")):
                forfeited_units += removed_qty
                forfeited_entries.append({
                    "instance_id": removed.get("instance_id"),
                    "item_id": item_id,
                    "quantity": removed_qty,
                    "owner_eid": removed.get("owner_eid"),
                    "owner_tag": removed.get("owner_tag"),
                    "metadata": dict(metadata),
                })
                forfeited_labels.append(item_name)
            if bool(hold_policy.get("illegal")):
                illegal_units += removed_qty
            if bool(hold_policy.get("restricted")):
                restricted_units += removed_qty
            if bool(hold_policy.get("contraband")):
                contraband_units += removed_qty
            if bool(hold_policy.get("stolen")):
                stolen_units += removed_qty
            if bool(hold_policy.get("weapon")):
                weapon_units += removed_qty
            labels.append(item_name)
            if remove:
                self._emit_removed_gear_events(self.player_eid, removed, reason="confiscated")

        deduped_labels = tuple(dict.fromkeys(label for label in labels if str(label).strip()))
        deduped_held_labels = tuple(dict.fromkeys(label for label in held_labels if str(label).strip()))
        deduped_forfeited_labels = tuple(dict.fromkeys(label for label in forfeited_labels if str(label).strip()))
        return {
            "confiscated_units": confiscated_units,
            "held_units": held_units,
            "forfeited_units": forfeited_units,
            "illegal_units": illegal_units,
            "restricted_units": restricted_units,
            "contraband_units": contraband_units,
            "stolen_units": stolen_units,
            "weapon_units": weapon_units,
            "held_entries": tuple(held_entries),
            "forfeited_entries": tuple(forfeited_entries),
            "labels": deduped_labels[:4],
            "held_labels": deduped_held_labels[:4],
            "forfeited_labels": deduped_forfeited_labels[:4],
        }

    def _confiscate_player_inventory(self, *, booking_prop=None):
        manifest = self._player_confiscation_manifest(remove=True)
        held_entries = tuple(manifest.get("held_entries", ()) or ())
        if held_entries:
            _store_justice_held_property(
                self.sim,
                self.player_eid,
                property_id=(booking_prop or {}).get("id") if isinstance(booking_prop, dict) else None,
                property_name=(booking_prop or {}).get("name") if isinstance(booking_prop, dict) else None,
                entries=held_entries,
            )
        return manifest

    def _reclaim_player_held_property(self, *, current_prop=None):
        current_prop = current_prop if isinstance(current_prop, dict) else None
        held = self._player_held_property_snapshot()
        entries = [
            dict(entry)
            for entry in list(held.get("entries", ()) or ())
            if isinstance(entry, dict)
        ]
        if not entries:
            return {
                "claimed_entries": (),
                "remaining_entries": (),
                "claimed_units": 0,
                "remaining_units": 0,
                "claimed_labels": (),
                "remaining_labels": (),
                "blocked_reason": "no_property",
                "property_id": "",
                "property_name": "",
            }

        inventory = self.sim.ecs.get(Inventory).get(self.player_eid)
        if inventory is None:
            return {
                "claimed_entries": (),
                "remaining_entries": tuple(entries),
                "claimed_units": 0,
                "remaining_units": int(sum(max(1, int(entry.get("quantity", 1) or 1)) for entry in entries)),
                "claimed_labels": (),
                "remaining_labels": tuple(
                    dict.fromkeys(
                        item_display_name(
                            entry.get("item_id"),
                            metadata=entry.get("metadata"),
                            item_catalog=ITEM_CATALOG,
                        )
                        for entry in entries
                    )
                )[:4],
                "blocked_reason": "missing_inventory",
                "property_id": str(held.get("property_id", "") or "").strip(),
                "property_name": str(held.get("property_name", "") or "").strip(),
            }

        claimed_entries = []
        remaining_entries = []
        claimed_labels = []
        remaining_labels = []
        claimed_units = 0
        remaining_units = 0
        for entry in entries:
            item_name = item_display_name(
                entry.get("item_id"),
                metadata=entry.get("metadata"),
                item_catalog=ITEM_CATALOG,
            )
            quantity = max(1, int(entry.get("quantity", 1) or 1))
            if self._inventory_can_accept_entry(inventory, entry) and self._restore_inventory_entry(inventory, entry):
                claimed_entries.append(dict(entry))
                claimed_labels.append(item_name)
                claimed_units += quantity
                continue
            remaining_entries.append(dict(entry))
            remaining_labels.append(item_name)
            remaining_units += quantity

        _replace_justice_held_property(
            self.sim,
            self.player_eid,
            property_id=(current_prop or {}).get("id") if isinstance(current_prop, dict) else held.get("property_id"),
            property_name=(current_prop or {}).get("name") if isinstance(current_prop, dict) else held.get("property_name"),
            entries=remaining_entries,
        )
        return {
            "claimed_entries": tuple(claimed_entries),
            "remaining_entries": tuple(remaining_entries),
            "claimed_units": int(claimed_units),
            "remaining_units": int(remaining_units),
            "claimed_labels": tuple(dict.fromkeys(label for label in claimed_labels if str(label).strip()))[:4],
            "remaining_labels": tuple(dict.fromkeys(label for label in remaining_labels if str(label).strip()))[:4],
            "blocked_reason": "inventory_full" if remaining_entries and not claimed_entries else "",
            "property_id": str(held.get("property_id", "") or "").strip(),
            "property_name": str(held.get("property_name", "") or "").strip(),
        }

    def _book_player(self, *, by_eid=None, source_prop=None):
        snapshot = self._player_bookable_snapshot()
        player_pos = self._position_for(self.player_eid)
        if snapshot is None or player_pos is None:
            return False
        if self._player_surrender_prompt_open():
            self._close_player_surrender_prompt()

        starting_tier = str(snapshot.get("wanted_tier", "clear")).strip().lower() or "clear"
        anchor = self._player_booking_anchor(player_pos)
        anchor_x = int((anchor or {}).get("x", player_pos.x) or player_pos.x)
        anchor_y = int((anchor or {}).get("y", player_pos.y) or player_pos.y)
        custody_change = _mark_justice_in_custody(
            self.sim,
            self.player_eid,
            held_by_eid=by_eid,
            x=anchor_x,
            y=anchor_y,
        )
        self._emit_change_events(custody_change, source_event="actor_detained", reason="custody")
        self.sim.emit(Event(
            "actor_detained",
            eid=self.player_eid,
            by_eid=by_eid,
            x=player_pos.x,
            y=player_pos.y,
            z=player_pos.z,
            before_tier=starting_tier,
            after_tier=str((custody_change or {}).get("after_tier", "held")).strip().lower() or "held",
            jurisdiction_key=str((custody_change or {}).get("jurisdiction_key", "") or "").strip().lower(),
            jurisdiction_name=str((custody_change or {}).get("jurisdiction_name", "Justice Office") or "Justice Office").strip() or "Justice Office",
        ))

        booking_prop = self._find_booking_property(
            source_prop=source_prop,
            origin_x=anchor_x,
            origin_y=anchor_y,
        )
        if booking_prop is None and not bool((anchor or {}).get("fallback", False)):
            booking_prop = self._find_booking_property(
                source_prop=source_prop,
                origin_x=player_pos.x,
                origin_y=player_pos.y,
            )
        booking_x, booking_y, booking_z = self._booking_anchor(booking_prop, fallback_pos=player_pos)
        self._teleport_entity(
            self.player_eid,
            player_pos,
            booking_x,
            booking_y,
            booking_z,
            reason="justice_booking",
        )

        confiscation = self._confiscate_player_inventory(booking_prop=booking_prop)
        fine_due = int(self._player_fine_amount(snapshot))
        fine_result = self._collect_player_fine(fine_due)
        hold_ticks = self._advance_time_for_booking(
            self._hours_to_ticks(self.BOOKING_HOURS_BY_TIER.get(starting_tier, 1.0)),
            property_id=(booking_prop or {}).get("id") if isinstance(booking_prop, dict) else None,
            property_name=(booking_prop or {}).get("name", "Justice Office") if isinstance(booking_prop, dict) else "Justice Office",
            held_by_eid=by_eid,
        )
        release_change = _release_justice_from_custody(
            self.sim,
            self.player_eid,
            new_score=self._booking_release_score(snapshot),
            x=booking_x,
            y=booking_y,
        )
        if isinstance(booking_prop, dict):
            self._grant_player_release_grace(booking_prop, reason="booking_release")
        self._emit_change_events(release_change, source_event="justice_booking_release", reason="booking_release")
        self.sim.emit(Event(
            "justice_booking_completed",
            eid=self.player_eid,
            property_id=(booking_prop or {}).get("id") if isinstance(booking_prop, dict) else None,
            property_name=str((booking_prop or {}).get("name", "Justice Office") if isinstance(booking_prop, dict) else "Justice Office").strip() or "Justice Office",
            held_by_eid=by_eid,
            hold_ticks=int(hold_ticks),
            hold_hours=round(float(hold_ticks) / float(self._ticks_per_hour()), 2) if hold_ticks > 0 else 0.0,
            before_tier=starting_tier,
            after_tier=str((release_change or {}).get("after_tier", "clear")).strip().lower() or "clear",
            before_score=int(snapshot.get("active_score", 0) or 0),
            after_score=int((release_change or {}).get("after_score", 0) or 0),
            fine_due=int(fine_due),
            fine_paid=int(fine_result.get("fine_paid", 0) or 0),
            cash_fine_paid=int(fine_result.get("cash_fine_paid", 0) or 0),
            wallet_fine_paid=int(fine_result.get("wallet_fine_paid", 0) or 0),
            bank_fine_paid=int(fine_result.get("bank_fine_paid", 0) or 0),
            debt_added=int(fine_result.get("debt_added", 0) or 0),
            fine_outstanding=int(fine_result.get("fine_outstanding", 0) or 0),
            wallet_credits_before=int(fine_result.get("wallet_credits_before", 0) or 0),
            wallet_credits_after=int(fine_result.get("wallet_credits_after", 0) or 0),
            asset_credits_before=int(fine_result.get("asset_credits_before", 0) or 0),
            asset_credits_after=int(fine_result.get("asset_credits_after", 0) or 0),
            bank_balance_before=int(fine_result.get("bank_balance_before", 0) or 0),
            bank_balance_after=int(fine_result.get("bank_balance_after", 0) or 0),
            debt_balance_before=int(fine_result.get("debt_balance_before", 0) or 0),
            debt_balance_after=int(fine_result.get("debt_balance_after", 0) or 0),
            confiscated_item_count=int(confiscation.get("confiscated_units", 0) or 0),
            held_item_count=int(confiscation.get("held_units", 0) or 0),
            forfeited_item_count=int(confiscation.get("forfeited_units", 0) or 0),
            illegal_item_count=int(confiscation.get("illegal_units", 0) or 0),
            restricted_item_count=int(confiscation.get("restricted_units", 0) or 0),
            contraband_item_count=int(confiscation.get("contraband_units", 0) or 0),
            stolen_item_count=int(confiscation.get("stolen_units", 0) or 0),
            weapon_item_count=int(confiscation.get("weapon_units", 0) or 0),
            confiscated_labels=tuple(confiscation.get("labels", ()) or ()),
            held_labels=tuple(confiscation.get("held_labels", ()) or ()),
            forfeited_labels=tuple(confiscation.get("forfeited_labels", ()) or ()),
            held_property_id=(booking_prop or {}).get("id") if isinstance(booking_prop, dict) else None,
            held_property_name=str((booking_prop or {}).get("name", "Justice Office") if isinstance(booking_prop, dict) else "Justice Office").strip() or "Justice Office",
            booking_anchor_x=int(anchor_x),
            booking_anchor_y=int(anchor_y),
            booking_anchor_fallback=bool((anchor or {}).get("fallback", False)),
            booking_anchor_jurisdiction_key=str((anchor or {}).get("jurisdiction_key", "") or "").strip().lower(),
            booking_anchor_jurisdiction_name=str((anchor or {}).get("jurisdiction_name", "Justice Office") or "Justice Office").strip() or "Justice Office",
            x=booking_x,
            y=booking_y,
            z=booking_z,
        ))
        return True

    def _find_detaining_enforcer(self, offender_eid):
        positions = self.sim.ecs.get(Position)
        offender_pos = positions.get(offender_eid)
        if offender_pos is None:
            return None

        best = None
        best_rank = None
        for eid, pos in positions.items():
            if eid == offender_eid or pos.z != offender_pos.z:
                continue
            dist = _manhattan(pos.x, pos.y, offender_pos.x, offender_pos.y)
            if dist > int(self.DETENTION_RADIUS):
                continue

            enforcer, law_drive, priority = self._actor_is_enforcer(eid)
            if not enforcer:
                continue
            rank = (dist, -priority, -law_drive, int(eid))
            if best_rank is None or rank < best_rank:
                best = int(eid)
                best_rank = rank
        return best

    def on_property_trespass(self, event):
        offender_eid = event.data.get("offender_eid")
        if offender_eid is None:
            return
        witnessed = bool(event.data.get("witnessed", False))
        ingress_kind = str(event.data.get("ingress_kind", "") or "").strip().lower()
        ingress_method = str(event.data.get("ingress_method", "") or "").strip().lower()
        breach_severity = float(event.data.get("breach_severity", 0.0) or 0.0)
        if not witnessed and not _trespass_is_obvious_breach(
            ingress_kind=ingress_kind,
            ingress_method=ingress_method,
            breach_severity=breach_severity,
        ):
            return
        self._record_incident(
            offender_eid,
            incident_type="trespass",
            severity=int(event.data.get("severity_score", 0) or 0),
            source_event="property_trespass",
            property_id=event.data.get("property_id"),
            x=event.data.get("x"),
            y=event.data.get("y"),
            witnessed=witnessed,
            note=str(event.data.get("severity_label", "trespass") or "").strip().lower(),
        )

    def on_property_tamper(self, event):
        offender_eid = event.data.get("offender_eid")
        if offender_eid is None:
            return
        property_id = str(event.data.get("property_id", "") or "").strip()
        prop = self.sim.properties.get(property_id) if property_id else None
        witnessed = bool(event.data.get("witnessed", False))
        if _quiet_unwitnessed_tamper(
            prop,
            witnessed=witnessed,
            ingress_kind=str(event.data.get("ingress_kind", "") or "").strip().lower(),
            ingress_method=str(event.data.get("ingress_method", "") or "").strip().lower(),
            breach_severity=float(event.data.get("breach_severity", 0.0) or 0.0),
        ):
            return
        self._record_incident(
            offender_eid,
            incident_type="tamper",
            severity=int(event.data.get("severity_score", 0) or 0),
            source_event="property_tamper",
            property_id=property_id,
            x=event.data.get("x"),
            y=event.data.get("y"),
            witnessed=witnessed,
            note="property_tamper",
        )

    def on_item_stolen(self, event):
        offender_eid = event.data.get("offender_eid")
        if offender_eid is None:
            return
        x = event.data.get("x")
        y = event.data.get("y")
        z = event.data.get("z", 0)
        if not self._watchers_present(offender_eid, x, y, z):
            return
        self._record_incident(
            offender_eid,
            incident_type="theft",
            severity=72,
            source_event="item_stolen",
            x=x,
            y=y,
            witnessed=True,
            note=str(event.data.get("item_name", event.data.get("item_id", "item")) or "").strip(),
        )

    def on_action_offense(self, event):
        offender_eid = event.data.get("offender_eid")
        if offender_eid is None:
            return
        context = str(event.data.get("context", "ordinary") or "").strip().lower() or "ordinary"
        if context not in {"contraband_use", *VIOLENT_OFFENSE_CONTEXTS}:
            return
        if offender_eid != self.player_eid and context in VIOLENT_OFFENSE_CONTEXTS:
            # NPC violence needs lawful-force context before it can share the
            # same consequences as the player. Keep first-pass NPC justice to
            # clearer property and theft offenses.
            return
        x = event.data.get("x")
        y = event.data.get("y")
        z = event.data.get("z", 0)
        if not self._watchers_present(offender_eid, x, y, z):
            return
        incident_type = {
            "contraband_use": "contraband",
            "unarmed_assault": "unarmed_assault",
            "melee_assault": "melee_assault",
            "armed_assault": "armed_assault",
            "explosive_discharge": "explosive_discharge",
        }.get(context, context)
        self._record_incident(
            offender_eid,
            incident_type=incident_type,
            severity=int(event.data.get("offense_score", 0) or 0),
            source_event="action_offense",
            x=x,
            y=y,
            witnessed=True,
            note=f"{str(event.data.get('action', 'action') or '').strip().lower()}/{context}",
        )

    def on_incident_authority_reported(self, event):
        incident = incident_record(self.sim, event.data.get("incident_id"))
        if not isinstance(incident, dict):
            return
        if str(incident.get("kind", "") or "").strip().lower() != "camera_alert":
            return
        offender_eid = incident.get("primary_actor_eid")
        if offender_eid is None:
            return
        property_id = str(incident.get("property_id", "") or "").strip()
        severity_score = int(incident.get("severity", 0) or 0)
        if not property_id or severity_score <= 0:
            return
        self._record_incident(
            offender_eid,
            incident_type="trespass",
            severity=severity_score,
            source_event="property_trespass",
            property_id=property_id,
            x=incident.get("x"),
            y=incident.get("y"),
            witnessed=True,
            note=str(incident.get("note", "camera_alert") or "camera_alert").strip().lower(),
        )

    def on_property_interact(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        if bool(event.data.get("handled")):
            return
        prop = self.sim.properties.get(event.data.get("property_id"))
        if not self._booking_property_allowed(prop):
            return
        snapshot = self._player_bookable_snapshot()
        if snapshot is not None:
            if self._book_player(source_prop=prop):
                event.data["handled"] = True
            return

        justice_snapshot = _justice_snapshot(self.sim, self.player_eid)
        held = self._player_held_property_snapshot()
        held_count = int(held.get("item_count", 0) or 0)
        debt_balance = int(self._player_justice_debt_balance())
        active_score = int(justice_snapshot.get("active_score", 0) or 0)
        incident_count = int(justice_snapshot.get("incident_count", 0) or 0)
        if held_count <= 0 and debt_balance <= 0 and active_score <= 0 and incident_count <= 0:
            return

        event.data["handled"] = True
        prop_name = str(prop.get("name", "Justice Desk") or "Justice Desk").strip() or "Justice Desk"
        current_property_id = str(prop.get("id", "") or "").strip()
        held_property_id = str(held.get("property_id", "") or "").strip()
        held_property_name = str(held.get("property_name", "") or "").strip()
        title = f"Justice Desk: {prop_name}"

        if held_count > 0 and held_property_id and held_property_id != current_property_id:
            lines = [
                "This desk is not holding your seized property.",
                *self._justice_status_lines(current_prop=prop),
            ]
            if held_property_name:
                if debt_balance > 0:
                    lines.append(f"Settle the debt, then report to {held_property_name} for release.")
                else:
                    lines.append(f"Report to {held_property_name} for release.")
            self._present_justice_result(title, lines, property_id=prop.get("id"))
            return

        if held_count > 0 and debt_balance > 0:
            lines = [
                "Release is blocked until your justice debt is cleared.",
                *self._justice_status_lines(current_prop=prop),
            ]
            self._present_justice_result(title, lines, property_id=prop.get("id"))
            return

        if held_count > 0:
            reclaim = self._reclaim_player_held_property(current_prop=prop)
            claimed_units = int(reclaim.get("claimed_units", 0) or 0)
            remaining_units = int(reclaim.get("remaining_units", 0) or 0)
            claimed_labels = [str(label).strip() for label in list(reclaim.get("claimed_labels", ()) or ()) if str(label).strip()]
            remaining_labels = [str(label).strip() for label in list(reclaim.get("remaining_labels", ()) or ()) if str(label).strip()]
            lines = []
            if claimed_units > 0:
                lines.append(f"Released {claimed_units} held item(s) from the property locker.")
                if claimed_labels:
                    lines.append(f"Recovered: {', '.join(claimed_labels[:3])}.")
            if remaining_units > 0:
                if str(reclaim.get("blocked_reason", "")).strip().lower() == "missing_inventory":
                    lines.append("No inventory is available to receive the remaining property.")
                else:
                    lines.append(f"{remaining_units} item(s) remain in holding until you make room.")
                if remaining_labels:
                    lines.append(f"Still held: {', '.join(remaining_labels[:3])}.")
            if not lines:
                lines.append("No held property was released.")
            self._present_justice_result(title, lines, property_id=prop.get("id"))
            return

        self._present_justice_result(
            title,
            self._justice_status_lines(current_prop=prop),
            property_id=prop.get("id"),
        )

    def on_npc_interact(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        if bool(event.data.get("handled")):
            return
        snapshot = self._player_bookable_snapshot()
        if snapshot is None or _actor_in_live_combat(self.sim, self.player_eid):
            return
        npc_eid = event.data.get("npc_eid")
        if npc_eid is None:
            return
        enforcer, _law_drive, _priority = self._actor_is_enforcer(npc_eid)
        if not enforcer:
            return
        npc_ai = self.sim.ecs.get(AI).get(npc_eid)
        npc_will = self.sim.ecs.get(NPCWill).get(npc_eid)
        if npc_ai is not None and str(npc_ai.state or "").strip().lower() in THREAT_STATES and npc_ai.target_eid == self.player_eid:
            return
        if npc_will is not None and str(npc_will.intent or "").strip().lower() in THREAT_STATES and npc_will.target_eid == self.player_eid:
            return
        if self._open_player_surrender_prompt(npc_eid, snapshot=snapshot, respect_cooldown=False):
            event.data["handled"] = True

    def on_justice_surrender_choice(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        if not self._player_surrender_prompt_open():
            return
        prompt = self.player_surrender_prompt if isinstance(self.player_surrender_prompt, dict) else {}
        by_eid = prompt.get("npc_eid", event.data.get("npc_eid"))
        source_prop = self.sim.properties.get(prompt.get("source_prop_id")) if prompt.get("source_prop_id") else None
        snapshot = self._player_bookable_snapshot()
        choice_id = str(event.data.get("choice_id", "") or "").strip().lower() or "resist"
        self._close_player_surrender_prompt()
        if choice_id == "surrender":
            self._book_player(by_eid=by_eid, source_prop=source_prop)
            return
        self._escalate_player_surrender_refusal(by_eid=by_eid, source_prop=source_prop, snapshot=snapshot)

    def on_npc_surrendered(self, event):
        offender_eid = event.data.get("eid")
        if offender_eid in {None, self.player_eid}:
            return
        snapshot = _justice_snapshot(self.sim, offender_eid)
        if bool(snapshot.get("in_custody", False)):
            return
        if str(snapshot.get("wanted_tier", "clear")).strip().lower() not in {"wanted", "arrest_on_sight"}:
            return
        self.pending_detentions[int(offender_eid)] = int(getattr(self.sim, "tick", 0)) + int(self.DETENTION_QUEUE_WINDOW)

    def _process_pending_detentions(self):
        positions = self.sim.ecs.get(Position)
        tick = int(getattr(self.sim, "tick", 0))
        for offender_eid, expires_at in list(self.pending_detentions.items()):
            if tick > int(expires_at):
                self.pending_detentions.pop(int(offender_eid), None)
                continue
            pos = positions.get(offender_eid)
            if pos is None:
                self.pending_detentions.pop(int(offender_eid), None)
                continue
            snapshot = _justice_snapshot(self.sim, offender_eid)
            if bool(snapshot.get("in_custody", False)):
                self.pending_detentions.pop(int(offender_eid), None)
                continue
            if str(snapshot.get("wanted_tier", "clear")).strip().lower() not in {"wanted", "arrest_on_sight"}:
                self.pending_detentions.pop(int(offender_eid), None)
                continue

            held_by_eid = self._find_detaining_enforcer(offender_eid)
            if held_by_eid is None:
                continue

            custody_change = _mark_justice_in_custody(
                self.sim,
                offender_eid,
                held_by_eid=held_by_eid,
                x=pos.x,
                y=pos.y,
            )
            self._emit_change_events(custody_change, source_event="actor_detained", reason="custody")
            self.sim.emit(Event(
                "actor_detained",
                eid=offender_eid,
                by_eid=held_by_eid,
                x=pos.x,
                y=pos.y,
                z=pos.z,
                before_tier=str(snapshot.get("wanted_tier", "clear")).strip().lower() or "clear",
                after_tier=str((custody_change or {}).get("after_tier", "held")).strip().lower() or "held",
                jurisdiction_key=str((custody_change or {}).get("jurisdiction_key", "") or "").strip().lower(),
                jurisdiction_name=str((custody_change or {}).get("jurisdiction_name", "Justice Office") or "Justice Office").strip() or "Justice Office",
            ))
            self._store_npc_custody_record(
                offender_eid,
                snapshot,
                held_by_eid=held_by_eid,
                pos=pos,
            )
            record = self._npc_custody_records().get(str(int(offender_eid)))
            if isinstance(record, dict):
                self._move_npc_to_custody(offender_eid, record)
            self.pending_detentions.pop(int(offender_eid), None)

    def _process_guard_initiated_player_arrest(self):
        snapshot = self._player_bookable_snapshot()
        if snapshot is None:
            return False
        if self._player_surrender_prompt_open():
            return False
        if _actor_in_live_combat(self.sim, self.player_eid):
            return False
        held_by_eid = self._find_auto_arrest_enforcer(snapshot)
        if held_by_eid is None:
            return False
        return bool(self._open_player_surrender_prompt(held_by_eid, snapshot=snapshot, respect_cooldown=True))

    def _process_resolved_npc_custody(self):
        tick = int(getattr(self.sim, "tick", 0))
        for offender_key, record in list(self._npc_custody_records().items()):
            if not isinstance(record, dict) or not bool(record.get("active", False)):
                continue
            if tick < int(record.get("hold_until_tick", tick + 1)):
                continue
            fine_paid, wallet_after, updated_items = self._deduct_cash_from_live_inventory(
                int(record.get("eid", 0) or 0),
                record.get("fine_due", 0),
            )
            if fine_paid <= 0 and int(record.get("fine_due", 0) or 0) > 0:
                updated_items, fine_paid, wallet_after = self._deduct_cash_from_inventory_entries(
                    record.get("inventory_items"),
                    record.get("fine_due", 0),
                )
            record["inventory_items"] = updated_items
            record["fine_paid"] = int(fine_paid)
            record["wallet_credits_after"] = int(wallet_after)
            record["released_tick"] = int(tick)
            record["active"] = False

            release_change = _release_justice_from_custody(
                self.sim,
                int(record.get("eid", 0) or 0),
                new_score=int(record.get("release_score", 0) or 0),
                x=record.get("booking_x"),
                y=record.get("booking_y"),
            )
            self._release_npc_from_custody(int(record.get("eid", 0) or 0), record)
            self._emit_change_events(release_change, source_event="npc_custody_release", reason="custody_release")
            self.sim.emit(Event(
                "npc_custody_resolved",
                eid=int(record.get("eid", 0) or 0),
                by_eid=record.get("held_by_eid"),
                property_id=record.get("booking_property_id"),
                property_name=str(record.get("booking_property_name", "Justice Office") or "Justice Office").strip() or "Justice Office",
                hold_ticks=int(record.get("hold_ticks", 0) or 0),
                fine_due=int(record.get("fine_due", 0) or 0),
                fine_paid=int(fine_paid),
                wallet_credits_before=int(record.get("wallet_credits_before", 0) or 0),
                wallet_credits_after=int(wallet_after),
                before_tier=str(record.get("before_tier", "wanted")).strip().lower() or "wanted",
                after_tier=str((release_change or {}).get("after_tier", "clear")).strip().lower() or "clear",
                release_x=int(record.get("release_x", 0) or 0),
                release_y=int(record.get("release_y", 0) or 0),
                release_z=int(record.get("release_z", 0) or 0),
            ))

    def update(self):
        if self._player_surrender_prompt_open() and self._player_bookable_snapshot() is None:
            self._close_player_surrender_prompt()
        if self._player_bookable_snapshot() is None:
            self._clear_player_surrender_offer_records()
        for change in _decay_justice_records(self.sim):
            self._emit_change_events(change, source_event="justice_decay", reason=str(change.get("reason", "cooldown")))
        self._process_guard_initiated_player_arrest()
        self._process_pending_detentions()
        self._process_resolved_npc_custody()


from game.organization_reputation import OrganizationReputationSystem
from game.run_pressure import RunPressureSystem


from game.world_progression_systems import FinalOperationSystem



from game.property_security_systems import PropertyAwarenessSystem



from game.property_security_systems import PropertyDefenseSystem



def _npc_recognizes_player(memory, player_eid):
    """Return the strength of a live `recognized` memory entry for player_eid."""
    if memory is None:
        return 0.0
    best = 0.0
    for entry in memory.entries:
        if entry.get("kind") != "recognized":
            continue
        data = entry.get("data") or {}
        if data.get("player_eid") == player_eid:
            best = max(best, float(entry.get("strength", 0.0)))
    return best


def _degrade_player_disguise(sim, player_eid, amount=0.35):
    """Reduce active disguise strength; clear it if it hits zero."""
    disguise = getattr(sim, "disguise_state", None)
    if not isinstance(disguise, dict):
        return
    new_strength = float(disguise.get("strength", 0.0)) - float(amount)
    if new_strength <= 0.0:
        sim.disguise_state = None
        sim.emit(Event(
            "disguise_blown",
            eid=player_eid,
            item_id=disguise.get("item_id"),
            item_name=disguise.get("item_name", ""),
        ))
    else:
        disguise["strength"] = round(new_strength, 3)


def _observer_primary_role(sim, observer_eid):
    if sim is None or observer_eid is None:
        return ""
    ai = sim.ecs.get(AI).get(observer_eid)
    role = str(getattr(ai, "role", "") or "").strip().lower()
    if role and role != "civilian":
        return role

    occupation = sim.ecs.get(Occupation).get(observer_eid)
    career = str(getattr(occupation, "career", "") or "").strip().lower()
    if any(token in career for token in ("guard", "security", "patrol", "watch")):
        return "guard"
    if any(token in career for token in ("worker", "labor", "loader", "mechanic", "salvage", "operator", "janitor", "tech")):
        return "worker"
    return role


def _npc_disguise_scrutiny_profile(sim, observer_eid, prop, *, offender_eid=None):
    if sim is None or observer_eid is None or not isinstance(prop, dict):
        return None
    if offender_eid != getattr(sim, "player_eid", None):
        return None
    disguise = getattr(sim, "disguise_state", None)
    if not isinstance(disguise, dict):
        return None

    role_id = str(disguise.get("role_id", "") or "").strip().lower()
    strength = max(0.0, float(disguise.get("strength", 0.0) or 0.0))
    if role_id not in {"guard", "worker"} or strength <= 0.0:
        return None

    archetype = _property_archetype(prop)
    access_level = _property_access_level(prop)
    security_site = archetype in SECURITY_ARCHETYPES or access_level == "restricted"
    worker_site = archetype in INDUSTRIAL_ARCHETYPES or archetype in SALVAGE_ARCHETYPES
    observer_role = _observer_primary_role(sim, observer_eid)
    observer_access, observer_claim = _property_claim_reason(
        sim,
        observer_eid,
        prop,
        x=prop.get("x"),
        y=prop.get("y"),
        z=prop.get("z", 0),
        min_standing=0.58,
    )
    embedded_observer = observer_claim in {"owner", "employee", "credential_holder", "resident"}

    fit_score = 0
    if role_id == "guard":
        fit_score += 2 if security_site else -2 if worker_site else -1
        if observer_role == "guard":
            fit_score += 2
        elif observer_role == "worker":
            fit_score -= 2
        if embedded_observer and security_site:
            fit_score += 1
    elif role_id == "worker":
        fit_score += 2 if worker_site else -2 if security_site else -1
        if observer_role == "worker":
            fit_score += 2
        elif observer_role == "guard":
            fit_score -= 2
        if embedded_observer and worker_site:
            fit_score += 1

    if fit_score >= 5:
        fit_label = "strong_fit"
        suspicion_mult = 0.52
        recognition_floor = 0.18
    elif fit_score >= 3:
        fit_label = "good_fit"
        suspicion_mult = 0.68
        recognition_floor = 0.24
    elif fit_score >= 1:
        fit_label = "partial_fit"
        suspicion_mult = 0.86
        recognition_floor = 0.32
    elif fit_score <= -3:
        fit_label = "hard_mismatch"
        suspicion_mult = 1.38
        recognition_floor = 0.62
    else:
        fit_label = "soft_mismatch"
        suspicion_mult = 1.18
        recognition_floor = 0.48

    if fit_score >= 1:
        suspicion_mult += max(0.0, (1.0 - strength) * 0.28)
    else:
        suspicion_mult += max(0.0, (1.0 - strength) * 0.12)

    return {
        "role_id": role_id,
        "strength": round(strength, 3),
        "observer_role": observer_role,
        "observer_claim": observer_claim,
        "observer_standing": round(float(observer_access.standing), 3) if observer_access else 0.0,
        "fit_score": int(fit_score),
        "fit_label": fit_label,
        "suspicion_mult": round(float(suspicion_mult), 3),
        "recognition_floor": round(float(recognition_floor), 3),
        "allow_pass": bool(fit_label == "strong_fit" and strength >= 0.72),
        "downgrade_protect": bool(fit_label in {"strong_fit", "good_fit"} and strength >= 0.62),
        "escalate_warn": bool(fit_label == "hard_mismatch"),
    }


def _security_fixture_temporarily_disabled_until(sim, prop):
    if not isinstance(prop, dict):
        return 0
    disabled_map = getattr(sim, "camera_disabled", {})
    if not isinstance(disabled_map, dict):
        return 0
    return _int_or_default(disabled_map.get(prop.get("id"), 0), 0)


def _security_fixture_power_cut_active(sim, prop, *, tick=None):
    if not isinstance(prop, dict):
        return False
    if tick is None:
        tick = int(getattr(sim, "tick", 0))
    power_cuts = getattr(sim, "fixture_power_cuts", {})
    if not isinstance(power_cuts, dict):
        return False
    prop_id = str(prop.get("id", "")).strip()
    if prop_id and _int_or_default(power_cuts.get(prop_id), 0) > int(tick):
        return True
    cover_index = getattr(sim, "property_cover_index", {})
    if not isinstance(cover_index, dict):
        return False
    prop_x = int(prop.get("x", 0))
    prop_y = int(prop.get("y", 0))
    prop_z = int(prop.get("z", 0))
    for covered_pid in cover_index.get((prop_x, prop_y, prop_z), ()):
        if _int_or_default(power_cuts.get(covered_pid), 0) > int(tick):
            return True
    return False


def _security_fixture_is_online(sim, prop, *, tick=None):
    if not isinstance(prop, dict):
        return False
    if tick is None:
        tick = int(getattr(sim, "tick", 0))
    if _security_fixture_power_cut_active(sim, prop, tick=tick):
        return False
    if _security_fixture_temporarily_disabled_until(sim, prop) > int(tick):
        return False
    return True


def _camera_disguise_scrutiny_profile(sim, prop):
    disguise = getattr(sim, "disguise_state", None)
    if not isinstance(disguise, dict):
        return None
    role_id = str(disguise.get("role_id", "") or "").strip().lower()
    strength = max(0.0, float(disguise.get("strength", 0.0) or 0.0))
    if not role_id or strength <= 0.0:
        return None
    archetype = _property_archetype(prop) if isinstance(prop, dict) else ""
    access_level = _property_access_level(prop) if isinstance(prop, dict) else "public"
    protected_site = access_level != "public"
    security_site = archetype in SECURITY_ARCHETYPES or protected_site
    worker_site = archetype in INDUSTRIAL_ARCHETYPES or archetype in SALVAGE_ARCHETYPES
    if role_id == "guard":
        threshold = 1.12 if security_site else 0.78
        increment = 0.34 if security_site else 0.58
    elif role_id == "worker":
        if worker_site:
            threshold = 0.96
            increment = 0.41
        elif security_site:
            threshold = 0.52
            increment = 0.78
        else:
            threshold = 0.4
            increment = 0.9
    else:
        return None

    threshold *= max(0.75, min(1.1, 0.7 + (strength * 0.35)))
    increment *= max(0.72, min(1.08, 1.04 - (strength * 0.16)))
    return {
        "role_id": role_id,
        "strength": strength,
        "threshold": round(float(threshold), 3),
        "increment": round(float(increment), 3),
    }


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


def _sync_ai_intent(ai, will, tick, intent, *, score=0.0, target=None, target_eid=None):
    ai.state = intent
    ai.target = target
    ai.target_eid = target_eid
    if not will:
        return
    will.intent = intent
    will.score = float(score)
    will.target = target
    will.target_eid = target_eid
    will.last_tick = int(tick)


from game.npc_intent_systems import NPCWillSystem



from game.systems_social import (
    EavesdropSystem,
    NPCSocialDynamicsSystem,
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

