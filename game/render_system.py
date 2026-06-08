"""Extracted systems from ``game.systems``: RenderSystem."""

import curses
import re
from engine.systems import System
from game.casino_ui_runtime import ensure_casino_ui_state
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
from game.appearance_loadout import is_entry_worn
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
from game.final_operation import (
    active_final_operation_target_property_id,
    ensure_final_operation_unlocked,
    evaluate_visible_final_operation,
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
from game.lighting import (
    ambient_snapshot as _lighting_ambient_snapshot,
    lighting_state as _lighting_state,
    update_lighting_state as _update_lighting_state,
)
import game.report_debug_ui as _report_debug_ui
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
from game.player_action_system import PlayerActionSystem
from game.dialogue_runtime import (
    _disguise_role_label,
    _property_access_summary,
)
from game.overworld_runtime import (
    PlayerOverworldRuntime,
    _chunk_tuple,
    _overworld_center_semantic_id,
    _overworld_chunk_knowledge,
    _overworld_chunk_memory_state,
    _overworld_chunk_view,
    _overworld_edge_legend_lines,
    _overworld_fill_semantic_id,
    _overworld_hud_lines,
    _overworld_legend_line_from_snapshot,
    _overworld_render_style_from_snapshot,
    _player_overworld_visit_state,
    _remember_overworld_chunk_memory,
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
from game.system_support.container_runtime import (
    ITEM_STOWED_CONTAINER_METADATA_KEY,
    _clear_inventory_container_assignments,
    _entry_stowed_container_instance,
    _inventory_entries_loose_for_container,
    _inventory_entries_stowed_in_container,
    _unlink_removed_item_from_gear,
)
from game.system_support.entity_naming import _entity_display_name
from game.system_support.combat_pacing_runtime import (
    _combat_overlay_state,
    _combat_turn_pacing_active,
    _set_manual_combat_pacing,
)
from game.system_support.combat_targeting_runtime import (
    _entity_uses_melee_aim,
    _first_targetable_entity_at,
    _manual_fire_preview,
    _target_condition_descriptor,
    _weapon_ammo_type_label,
    _weapon_reserve_ammo,
)
from game.system_support.fire_runtime import fire_cell_state, fire_state
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
from game.service_runtime import (
    CASINO_GAME_SERVICE_IDS,
    TRANSIT_SERVICE_IDS,
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
)


_FIRE_VISUAL_GLYPHS = ("*", "^", "x")
_SMOKE_VISUAL_GLYPHS = ("~", ",")
_HUD_CHANGE_FLASH_TICKS = 4
_HUD_CHANGE_FLASH_FRAMES = 4
_HUD_SURVIVAL_TOKEN_RE = re.compile(r"\b([FW])!{0,2}(\d{1,3})(?![/\d])")
_HUD_SURVIVAL_VALUE_RE = re.compile(r"^([FW])!{0,2}(\d{1,3})$")
_HUD_FLASH_VALUE_RE = re.compile(
    r"(?<![A-Za-z0-9_])"
    r"(?:"
    r"(?:So|[FWES])!{0,2}[+-]?\d+(?:\.\d+)?%?"
    r"|[+-]?\d+(?::\d{2})?(?:[.,/][+-]?\d+(?::\d{2})?)*%?"
    r")"
    r"(?![A-Za-z0-9_])"
)
_HUD_FLASH_WORD_RE = re.compile(r"\S+")


def _fire_visual_style(sim, x, y, z=0):
    cell = fire_cell_state(sim, x, y, z)
    if not isinstance(cell, dict):
        return None
    fire_intensity = max(0, int(cell.get("fire_intensity", 0) or 0))
    smoke_intensity = max(0, int(cell.get("smoke_intensity", 0) or 0))
    if fire_intensity <= 0 and smoke_intensity <= 0:
        return None
    if fire_intensity > 0:
        glyphs = _FIRE_VISUAL_GLYPHS
        color = "hazard_fire"
        semantic_id = "hazard_open_flame"
        effects = ("blink",)
        attrs = getattr(curses, "A_BOLD", 0)
        layer = "ground_overlay"
        priority = 80
    else:
        glyphs = _SMOKE_VISUAL_GLYPHS
        color = "hazard_smoke"
        semantic_id = "hazard_smoke"
        effects = ()
        attrs = getattr(curses, "A_DIM", 0)
        layer = "ground_overlay"
        priority = 70
    try:
        tick = int(getattr(sim, "tick", 0) or 0)
    except (TypeError, ValueError):
        tick = 0
    index = abs((int(x) * 7) + (int(y) * 11) + (int(z) * 13) + tick) % len(glyphs)
    return {
        "glyph": glyphs[index],
        "color": color,
        "semantic_id": semantic_id,
        "effects": effects,
        "attrs": attrs,
        "layer": layer,
        "priority": priority,
    }


def _hud_flash_signature(line):
    def survival_band(match):
        prefix = str(match.group(1))
        try:
            value = int(match.group(2))
        except (TypeError, ValueError):
            value = 0
        value = max(0, min(100, value))
        band = min(3, max(0, value // 25))
        return f"{prefix}#{band}"

    return _HUD_SURVIVAL_TOKEN_RE.sub(survival_band, _line_text(line))


def _hud_flash_value_signature(value):
    text = str(value or "")
    survival = _HUD_SURVIVAL_VALUE_RE.match(text)
    if survival:
        prefix = str(survival.group(1))
        try:
            numeric = int(survival.group(2))
        except (TypeError, ValueError):
            numeric = 0
        numeric = max(0, min(100, numeric))
        return f"{prefix}#{min(3, max(0, numeric // 25))}"
    return text


def _hud_flash_value_tokens(text):
    return [
        (match.span(), _hud_flash_value_signature(match.group(0)))
        for match in _HUD_FLASH_VALUE_RE.finditer(str(text or ""))
    ]


def _hud_merge_ranges(ranges, text_length):
    normalized = []
    for start, end in ranges or ():
        start = max(0, min(int(start), int(text_length)))
        end = max(0, min(int(end), int(text_length)))
        if end <= start:
            continue
        normalized.append((start, end))
    if not normalized:
        return ()

    normalized.sort()
    merged = []
    for start, end in normalized:
        if not merged or start > merged[-1][1]:
            merged.append([start, end])
            continue
        merged[-1][1] = max(merged[-1][1], end)
    return tuple((start, end) for start, end in merged)


def _hud_flash_changed_ranges(previous_text, current_text):
    previous_text = str(previous_text or "")
    current_text = str(current_text or "")
    if not current_text or previous_text == current_text:
        return ()

    previous_values = [signature for _span, signature in _hud_flash_value_tokens(previous_text)]
    current_values = _hud_flash_value_tokens(current_text)
    ranges = []
    for index, (span, signature) in enumerate(current_values):
        if index >= len(previous_values) or previous_values[index] != signature:
            ranges.append(span)
    if ranges:
        return _hud_merge_ranges(ranges, len(current_text))

    previous_words = [match.group(0) for match in _HUD_FLASH_WORD_RE.finditer(previous_text)]
    for index, match in enumerate(_HUD_FLASH_WORD_RE.finditer(current_text)):
        if index >= len(previous_words) or previous_words[index] != match.group(0):
            ranges.append(match.span())
    return _hud_merge_ranges(ranges, len(current_text))


def _hud_line_with_flash_ranges(line, ranges, flash_attrs):
    flash_attrs = int(flash_attrs or 0)
    text = _line_text(line)
    ranges = _hud_merge_ranges(ranges, len(text))
    if not flash_attrs or not ranges:
        return line

    source_segments = _line_segments(line)
    if not source_segments:
        source_segments = [_segment(text)]

    out_segments = []
    cursor = 0
    for segment in source_segments:
        if not isinstance(segment, dict):
            segment = _segment(str(segment))
        segment_text = str(segment.get("text", ""))
        if not segment_text:
            continue
        segment_start = cursor
        segment_end = segment_start + len(segment_text)
        split_points = {segment_start, segment_end}
        for range_start, range_end in ranges:
            overlap_start = max(segment_start, range_start)
            overlap_end = min(segment_end, range_end)
            if overlap_end > overlap_start:
                split_points.add(overlap_start)
                split_points.add(overlap_end)

        points = sorted(split_points)
        extras = {
            key: value
            for key, value in segment.items()
            if key not in {"text", "color", "attrs"}
        }
        for left, right in zip(points, points[1:]):
            if right <= left:
                continue
            chunk_text = segment_text[left - segment_start:right - segment_start]
            active = any(left < range_end and right > range_start for range_start, range_end in ranges)
            attrs = int(segment.get("attrs", 0) or 0)
            if active:
                attrs |= flash_attrs
            out_segments.append(_segment(
                chunk_text,
                color=segment.get("color"),
                attrs=attrs,
                **extras,
            ))
        cursor = segment_end

    return _rich_line(out_segments, text=text)

from game.location_presentation_runtime import (
    _creature_color_key,
    _entity_render_style,
    _item_legend_line,
    _stakeout_progress_snapshot,
)
from game.ui_text_runtime import (
    _clip_display_line,
    _filtered_log_lines,
    _flow_display_chunks,
    _fit_wrapped_sections,
    _flow_text_chunks,
    _hud_log_lines,
    _known_location_detail_lines,
    _known_location_list_line,
    _known_person_detail_lines,
    _known_person_list_line,
    _line_segments,
    _line_text,
    _line_with_prefix,
    _log_display_line,
    _log_filter_label,
    _log_filter_spec,
    _log_prefix,
    _mode_line,
    _rich_line,
    _segment,
    _tick_duration_label,
    _view_text_wrap_width,
    _wrap_display_lines,
    _wrap_text_lines,
)
from game.run_objectives import evaluate_visible_run_objective
from game.skill_ui import (
    skill_change_reason_label as _skill_change_reason_label,
    skill_debug_lines as _skill_debug_lines,
    skill_hud_status_chunks as _skill_hud_status_chunks,
)
from game.status_ui_runtime import (
    _active_status_summary,
    _hud_primary_status_chunks,
    _survival_indicator_chunks,
)
from game.weapons import WEAPON_CATALOG, roll_weapon_instance, weapon_by_id

def _facade():
    from game import systems as facade

    return facade


STAKEOUT_MAX_REVEALS = 4

STAKEOUT_REVEAL_INTERVAL = 8

def _aim_confirm_label(*args, **kwargs):
    return _facade()._aim_confirm_label(*args, **kwargs)

def _aim_open_label(*args, **kwargs):
    return _facade()._aim_open_label(*args, **kwargs)

def _ambient_attr(*args, **kwargs):
    return _facade()._ambient_attr(*args, **kwargs)

def _ambient_sample(*args, **kwargs):
    return _facade()._ambient_sample(*args, **kwargs)

def _appearance_prefers_floor_underlay(*args, **kwargs):
    return _facade()._appearance_prefers_floor_underlay(*args, **kwargs)

def _appearance_with_effect(*args, **kwargs):
    return _facade()._appearance_with_effect(*args, **kwargs)

def _clip(*args, **kwargs):
    return _facade()._clip(*args, **kwargs)

def _cover_source_label(*args, **kwargs):
    return _facade()._cover_source_label(*args, **kwargs)

def _cover_source_render(*args, **kwargs):
    return _facade()._cover_source_render(*args, **kwargs)

def _district_floor_color(*args, **kwargs):
    return _facade()._district_floor_color(*args, **kwargs)

def _district_floor_glyph(*args, **kwargs):
    return _facade()._district_floor_glyph(*args, **kwargs)

def _draw_overworld_frame(*args, **kwargs):
    return _facade()._draw_overworld_frame(*args, **kwargs)

def _entity_should_blink_in_combat(*args, **kwargs):
    return _facade()._entity_should_blink_in_combat(*args, **kwargs)

def _entity_should_mark_ambient_combat(*args, **kwargs):
    return _facade()._entity_should_mark_ambient_combat(*args, **kwargs)

def _is_explored(*args, **kwargs):
    return _facade()._is_explored(*args, **kwargs)

def _is_visible(*args, **kwargs):
    return _facade()._is_visible(*args, **kwargs)

def _overworld_cell_slots(*args, **kwargs):
    return _facade()._overworld_cell_slots(*args, **kwargs)

def _player_tile_memory_state(*args, **kwargs):
    return _facade()._player_tile_memory_state(*args, **kwargs)

def _pos(*args, **kwargs):
    return _facade()._pos(*args, **kwargs)

def _remember_tile_appearance(*args, **kwargs):
    return _facade()._remember_tile_appearance(*args, **kwargs)

def _remembered_tile_appearance(*args, **kwargs):
    return _facade()._remembered_tile_appearance(*args, **kwargs)

def _tile_prefers_feature_legend(*args, **kwargs):
    return _facade()._tile_prefers_feature_legend(*args, **kwargs)

class RenderSystem(System):

    CAT_COAT_COLOR = dict(APPEARANCE_CAT_COAT_COLOR)
    OVERWORLD_DISTRICT_GLYPHS = {
        "industrial": "I",
        "residential": "R",
        "downtown": "D",
        "slums": "S",
        "corporate": "C",
        "military": "M",
        "entertainment": "E",
    }
    OVERWORLD_AREA_GLYPHS = {
        "city": "X",
        "frontier": "F",
        "wilderness": "W",
        "coastal": "O",
    }
    OVERWORLD_DISTRICT_COLORS = {
        "industrial": "floor_industrial",
        "residential": "floor_residential",
        "downtown": "floor_downtown",
        "slums": "floor_slums",
        "corporate": "floor_corporate",
        "military": "floor_military",
        "entertainment": "floor_entertainment",
    }
    OVERWORLD_AREA_COLORS = {
        "city": "floor_downtown",
        "frontier": "floor_frontier",
        "wilderness": "floor_wilderness",
        "coastal": "floor_coastal",
    }
    OVERWORLD_TERRAIN_GLYPHS = {
        "urban": "u",
        "park": "p",
        "industrial_waste": "x",
        "scrub": "s",
        "plains": "p",
        "badlands": "b",
        "hills": "h",
        "forest": "f",
        "marsh": "m",
        "shore": "o",
        "shoals": "a",
        "dunes": "d",
        "cliffs": "c",
        "salt_flats": "t",
        "lake": "l",
        "ruins": "r",
    }
    OVERWORLD_TERRAIN_COLORS = {
        "urban": "floor_downtown",
        "park": "terrain_brush",
        "industrial_waste": "building_fill",
        "scrub": "floor_frontier",
        "plains": "floor_frontier",
        "badlands": "terrain_trail",
        "hills": "terrain_rock",
        "forest": "terrain_brush",
        "marsh": "floor_wilderness",
        "shore": "floor_coastal",
        "shoals": "terrain_water",
        "dunes": "terrain_salt",
        "cliffs": "terrain_rock",
        "salt_flats": "terrain_salt",
        "lake": "terrain_water",
        "ruins": "building_edge",
    }
    OVERWORLD_DISTRICT_FILL_GLYPHS = {
        "industrial": "=",
        "residential": ".",
        "downtown": "%",
        "slums": ",",
        "corporate": ":",
        "military": ";",
        "entertainment": "*",
    }
    OVERWORLD_AREA_FILL_GLYPHS = {
        "city": ".",
        "frontier": ",",
        "wilderness": "'",
        "coastal": "_",
    }
    OVERWORLD_TERRAIN_FILL_GLYPHS = {
        "urban": ".",
        "park": "'",
        "industrial_waste": ":",
        "scrub": ",",
        "plains": ".",
        "badlands": ";",
        "hills": "^",
        "forest": "'",
        "marsh": ";",
        "shore": "_",
        "shoals": ":",
        "dunes": ":",
        "cliffs": "#",
        "salt_flats": "_",
        "lake": "~",
        "ruins": "%",
    }
    OVERWORLD_PATH_GLYPHS = {
        "freeway": "#",
        "road": "=",
        "trail": ":",
    }
    OVERWORLD_PATH_COLORS = {
        "freeway": "transit",
        "road": "terrain_road",
        "trail": "terrain_trail",
    }
    OVERWORLD_CELL_W = 4
    OVERWORLD_CELL_H = 3

    def __init__(self, sim, view, player_eid, hud_lines=10):
        super().__init__(sim)
        self.view = view
        self.player_eid = player_eid
        self.hud_lines = hud_lines
        self.runs_without_turn = True
        self.runs_while_paused = True
        # Queue-based HUD log display state
        self._hud_queue = []       # entries waiting to be shown
        self._hud_display = []     # entries currently visible in the HUD strip
        self._hud_seen_seq = -1    # last log sequence ingested
        self._hud_last_tick = -1   # last sim tick when we drained messages
        self._hud_previous_section_lines = {}
        self._hud_previous_section_texts = {}
        self._hud_flash_ranges_by_line = {}
        self._hud_render_frame = 0

    def _hud_flash_clock(self):
        try:
            tick = int(getattr(self.sim, "tick", 0) or 0)
        except (TypeError, ValueError):
            tick = 0
        return tick, int(self._hud_render_frame)

    def _update_hud_flash_state(self, sections):
        tick, frame = self._hud_flash_clock()
        previous = self._hud_previous_section_lines if isinstance(self._hud_previous_section_lines, dict) else {}
        previous_texts = self._hud_previous_section_texts if isinstance(self._hud_previous_section_texts, dict) else {}
        current = {}
        current_texts = {}
        active_line_keys = set()

        for section_index, section in enumerate(sections or ()):
            section_id = str(section.get("id", f"section:{section_index}") or f"section:{section_index}")
            lines = list(section.get("lines", ()) or ())
            signatures = tuple(_hud_flash_signature(line) for line in lines)
            texts = tuple(_line_text(line) for line in lines)
            current[section_id] = signatures
            current_texts[section_id] = texts
            prior = previous.get(section_id)
            prior_texts = previous_texts.get(section_id, ())

            for line_index, signature in enumerate(signatures):
                key = (section_id, int(line_index))
                active_line_keys.add(key)
                if prior is None:
                    continue
                if line_index >= len(prior) or prior[line_index] != signature:
                    previous_text = prior_texts[line_index] if line_index < len(prior_texts) else ""
                    ranges = _hud_flash_changed_ranges(previous_text, texts[line_index])
                    if ranges:
                        self._hud_flash_ranges_by_line[key] = (
                            ranges,
                            tick + _HUD_CHANGE_FLASH_TICKS,
                            frame + _HUD_CHANGE_FLASH_FRAMES,
                        )

        self._hud_previous_section_lines = current
        self._hud_previous_section_texts = current_texts
        self._hud_flash_ranges_by_line = {
            key: value
            for key, value in dict(self._hud_flash_ranges_by_line).items()
            if key in active_line_keys
            and tick < int(value[1])
            and frame < int(value[2])
        }

    def _hud_flash_line(self, section_id, line_index, line):
        key = (str(section_id), int(line_index))
        state = self._hud_flash_ranges_by_line.get(key)
        if not state:
            return line
        ranges, expire_tick, expire_frame = state
        tick, frame = self._hud_flash_clock()
        if tick >= int(expire_tick) or frame >= int(expire_frame):
            return line
        return _hud_line_with_flash_ranges(line, ranges, getattr(curses, "A_REVERSE", 0))

    def _advance_hud_queue(self, budget):
        """Ingest new log entries and drain up to 2 per game tick into the HUD display buffer."""
        current_tick = int(getattr(self.sim, "tick", 0) or 0)
        dedup_window = 6

        for entry in getattr(self.sim.log, "entries", ()) or ():
            if not isinstance(entry, dict):
                continue
            seq = int(entry.get("sequence", -1))
            if seq <= self._hud_seen_seq:
                continue
            self._hud_seen_seq = seq

            text = entry.get("text", "")
            etick = entry.get("tick")
            if etick is not None:
                combined = self._hud_display + self._hud_queue
                if any(
                    d.get("text") == text
                    and d.get("tick") is not None
                    and etick - d["tick"] <= dedup_window
                    for d in combined
                ):
                    continue
            self._hud_queue.append(entry)

        if self._hud_queue and current_tick != self._hud_last_tick:
            self._hud_last_tick = current_tick
            overlay = getattr(self.sim, "combat_overlay", {})
            in_turn_based = bool(getattr(self.sim, "turn_based", False))
            combat_active = bool(isinstance(overlay, dict) and overlay.get("active"))
            backlog_flush = len(self._hud_queue) > max(2, int(budget))
            if in_turn_based or combat_active or backlog_flush:
                drain = len(self._hud_queue)
            else:
                drain = min(2, len(self._hud_queue))
            self._hud_display.extend(self._hud_queue[:drain])
            self._hud_queue = self._hud_queue[drain:]

        max_keep = max(budget * 2, 20)
        if len(self._hud_display) > max_keep:
            self._hud_display = self._hud_display[-max_keep:]

    def _visible_hud_logs(self, budget):
        budget = max(0, int(budget))
        if budget <= 0:
            return []

        log_ui = getattr(self.sim, "log_ui", None)
        if isinstance(log_ui, dict):
            filter_id = _log_filter_spec(log_ui.get("hud_filter", "priority"))["id"]
        else:
            filter_id = "priority"

        combined = list(self._hud_display) + list(self._hud_queue)
        if not combined:
            return []

        overlay = getattr(self.sim, "combat_overlay", {})
        in_turn_based = bool(getattr(self.sim, "turn_based", False))
        combat_active = bool(isinstance(overlay, dict) and overlay.get("active"))
        if in_turn_based or combat_active:
            return _filtered_log_lines(combined, filter_id)[-budget:]
        return _hud_log_lines(combined, filter_id, budget)

    def _visible_hud_log_display_lines(self, budget, wrap_width):
        budget = max(0, int(budget))
        wrap_width = max(1, int(wrap_width))
        if budget <= 0:
            return []

        visible_logs = list(self._visible_hud_logs(max(1, budget)))
        if not visible_logs:
            return []

        visible_lines = []
        remaining = budget
        for line in reversed(visible_logs):
            wrapped = list(
                _wrap_display_lines(
                    _line_with_prefix(line, _log_prefix(line)),
                    wrap_width,
                )
                or [""]
            )
            if len(wrapped) <= remaining:
                visible_lines[0:0] = wrapped
                remaining -= len(wrapped)
                if remaining <= 0:
                    break
                continue
            visible_lines[0:0] = wrapped[:remaining]
            break
        return visible_lines

    def _draw(self, x, y, glyph, color=None, attrs=0, semantic_id=None, effects=None, overlays=None, layer=None, priority=None):
        kwargs = {"attrs": int(attrs or 0)}
        if color is not None:
            kwargs["color"] = color
        if semantic_id:
            kwargs["semantic_id"] = semantic_id
        if effects:
            kwargs["effects"] = effects
        if overlays:
            kwargs["overlays"] = overlays
        if layer is not None:
            kwargs["layer"] = layer
        if priority is not None:
            kwargs["priority"] = int(priority)
        try:
            self.view.draw(x, y, glyph, **kwargs)
            return
        except TypeError:
            pass

        if color is None:
            try:
                self.view.draw(x, y, glyph, attrs=int(attrs or 0))
                return
            except TypeError:
                self.view.draw(x, y, glyph)
                return

        try:
            self.view.draw(x, y, glyph, color=color, attrs=int(attrs or 0))
        except TypeError:
            self.view.draw(x, y, glyph)

    def _draw_appearance(self, x, y, appearance, attrs=0):
        if not appearance or not bool(getattr(appearance, "visible", True)):
            return
        self._draw(
            x,
            y,
            getattr(appearance, "glyph", "?"),
            color=getattr(appearance, "color", None),
            attrs=int(attrs or 0) | int(getattr(appearance, "attrs", 0) or 0),
            semantic_id=getattr(appearance, "semantic_id", None),
            effects=getattr(appearance, "effects", ()),
            overlays=getattr(appearance, "overlays", ()),
            layer=getattr(appearance, "layer", None),
            priority=getattr(appearance, "priority", None),
        )

    def _entity_color(self, eid, render, identity):
        if eid == self.player_eid:
            return "player"

        if identity:
            ai = self.sim.ecs.get(AI).get(eid)
            role = str(getattr(ai, "role", "") or "").strip().lower()
            mapped = _creature_color_key(
                identity,
                role=role,
                cat_color_map=self.CAT_COAT_COLOR,
            )
            if mapped:
                return mapped

        return getattr(render, "color", None)

    def _player_overworld_markers(self):
        markers_by_eid = getattr(self.sim, "overworld_markers_by_eid", {})
        if not isinstance(markers_by_eid, dict):
            return []

        raw_markers = markers_by_eid.get(self.player_eid, [])
        if not isinstance(raw_markers, list):
            return []

        markers = []
        for marker in raw_markers:
            if not isinstance(marker, dict):
                continue
            chunk = marker.get("chunk")
            if not isinstance(chunk, (list, tuple)) or len(chunk) != 2:
                continue
            try:
                marker_id = int(marker.get("id", 0))
                cx = int(chunk[0])
                cy = int(chunk[1])
            except (TypeError, ValueError):
                continue
            markers.append({
                "id": marker_id,
                "chunk": (cx, cy),
            })
        return markers

    def _npc_label(self, eid, fallback="NPC"):
        if eid is None:
            return str(fallback or "NPC")
        name = _entity_display_name(self.sim, eid, title_case=True)
        if name and str(name).strip().lower() != "entity":
            return name
        return f"NPC {eid}"

    def _help_overlay_lines(self, zoom_mode, overlay_active=False):
        zoom_mode = str(zoom_mode).lower()
        view_only = zoom_mode == "overworld" and bool(
            getattr(self.sim, "overworld_view_only_by_eid", {}).get(int(self.player_eid), False)
        )
        aim_open = _aim_open_label(self.sim, self.player_eid)
        aim_confirm = _aim_confirm_label(self.sim, self.player_eid)
        lines = [
            "Help",
            "? or Esc closes this panel.",
            "",
            f"World seed: {self.sim.seed}",
            "Move: arrows, WASD, HJKL, q/e/z/c diagonals, or numpad 1-9. Wait with space or 5.",
            "Observe: / talks, ' physically interacts, . uses the service on your tile, ; locks or unlocks a nearby door, x opens the look cursor, and X opens the map. Vehicle interact enters or exits overworld.",
            "Conversation: talking to nearby people opens a topic menu with follow-up branches, trade, and rumors.",
            "Ingress: Shift+J door breach, Shift+W window entry, Shift+K wall breach.",
            'Features: + closed door, \' open door, " window, / breach opening, > higher stairs, < lower stairs, : stair landing, E elevator.',
            "Infrastructure: typed markers (l lamp, p pole, h hydrant, u stop, j/t utility, $ ATM, c claim terminal, r access panel).",
            "Local terrain: = road, : trail, , brush, ^ rock, ~ water, _ shore flats.",
            "Remote sites: relay/lookout/survey sites provide intel; camps and huts can offer shelter.",
            f"Aim/Combat: {aim_open}, move cursor, F cycle target, {aim_confirm}, C cover, v cover hop, Shift+S sneak, V cycle weapon.",
            "Items: I inventory, , picks up nearby items, U use/equip/stow, R drop.",
            "Visual classes: vehicles use '&' symbol colors only; properties use letters; items are bright symbols; humans use colored @ symbols and wildlife uses taxonomy letters.",
            "Progress: O operations report, Y opens the Places notebook; Tab switches to the People notebook. L opens event log history.",
            "Log modal: T cycles filters; H sets the current modal filter as the live HUD filter.",
            "Debug: D live telemetry for lighting, stealth, pressure, property access, and objective state.",
            "Services: . uses the service on your tile, including banking, insurance, terminals, transit, and storefront counters. P buy property.",
            "Character: + opens the character sheet. Tab or Left/Right switch pages.",
        ]
        if zoom_mode == "overworld":
            if view_only:
                lines.append("Map view: move to browse chunks, Enter or x inspect the selected chunk, and t return on-foot.")
                lines.append("Map tools: X opens the map from on foot, M adds a marker here, l lists markers, N jumps to the nearest marker, O ops, Y notebooks, L log.")
            else:
                lines.append("In-vehicle map: move travels chunks, G drives to the last marker, M adds a marker, l lists markers, N jumps to the nearest marker, and t exits on-foot.")
            lines.append("Overworld POIs: stronger non-city chunks can replace the center glyph with a site initial.")
            lines.append("Overworld centers: each chunk keeps its district or terrain icon; bright means loaded and dim means distant.")
            lines.append("Overworld regions: soft boundary lines separate major outside regions.")
        if overlay_active:
            lines.append("Combat turn mode: each action consumes a turn until danger settles.")
        lines.append("Dangerous actions teach through one-time log warnings, not confirmation popups.")
        return lines

    def _draw_display_line(self, x, y, line, max_width, attrs=0):
        segments = _line_segments(line)
        if segments:
            self.view.draw_segments(x, y, segments, max_width=max_width, attrs=int(attrs or 0))
            return
        self.view.draw_text(x, y, _line_text(line), attrs=int(attrs or 0))

    def update(self):
        self.view.clear()
        self._hud_render_frame += 1
        begin_frame = getattr(self.view, "begin_frame", None)
        if callable(begin_frame):
            animation_tick = None
            if not bool(getattr(self.view, "uses_realtime_animation", False)):
                animation_tick = int(getattr(self.sim, "tick", 0))
            begin_frame(animation_tick=animation_tick)

        positions = self.sim.ecs.get(Position)
        renders = self.sim.ecs.get(Render)
        identities = self.sim.ecs.get(CreatureIdentity)
        inventories = self.sim.ecs.get(Inventory)
        financials = self.sim.ecs.get(FinancialProfile)
        effects_map = self.sim.ecs.get(StatusEffects)
        loadouts = self.sim.ecs.get(WeaponLoadout)
        vitalities = self.sim.ecs.get(Vitality)
        covers = self.sim.ecs.get(CoverState)
        modes = self.sim.ecs.get(PlayerModeState)
        vehicle_states = self.sim.ecs.get(VehicleState)
        player_pos = positions.get(self.player_eid)
        active_z = player_pos.z if player_pos else 0
        inventory_ui = getattr(self.sim, "inventory_ui", {
            "open": False,
            "selected_index": 0,
            "inspect_text": "",
        })
        inventory_panel_kind = str(inventory_ui.get("panel_kind", "inventory")).strip().lower() or "inventory"
        if inventory_panel_kind == "cache":
            inventory_panel_kind = "container"
            inventory_ui["panel_kind"] = "container"
            inventory_ui.setdefault("container_kind", "cache")
            inventory_ui.setdefault("container_label", "Cache")
        inventory_container_kind = str(inventory_ui.get("container_kind", "")).strip().lower()
        if not inventory_container_kind and inventory_panel_kind == "container":
            inventory_container_kind = "container"
        inventory_container_label = str(inventory_ui.get("container_label", "")).strip() or (
            "Cache" if inventory_container_kind == "cache" else ("Cargo" if inventory_container_kind == "scene" else "Container")
        )
        inventory_container_instance_id = str(inventory_ui.get("container_instance_id", "") or "").strip() or None
        inventory_container_capacity = max(0, _int_or_default(inventory_ui.get("container_capacity"), 0))
        inventory_container_view = str(
            inventory_ui.get("container_view", inventory_ui.get("cache_view", "pack"))
        ).strip().lower() or "pack"
        inventory_container_view = "pack" if inventory_container_view == "pack" else "container"
        inventory_ui["container_view"] = inventory_container_view
        inventory_ui["cache_view"] = "pack" if inventory_container_view == "pack" else "cache"
        trade_ui = getattr(self.sim, "trade_ui", {
            "open": False,
            "mode": "buy",
            "selected_index": 0,
            "rows": [],
            "inspect_text": "",
            "store_name": "",
            "property_id": None,
            "supply_note": "",
            "contact_note": "",
        })
        casino_ui = ensure_casino_ui_state(self.sim)
        dialog_ui = getattr(self.sim, "dialog_ui", {
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
        })
        look_ui = getattr(self.sim, "look_ui", {
            "active": False,
            "mode": "city",
            "purpose": "inspect",
            "x": 0,
            "y": 0,
            "z": 0,
            "chunk_x": 0,
            "chunk_y": 0,
            "inspect_text": "",
        })
        help_ui = getattr(self.sim, "help_ui", {
            "open": False,
        })
        character_ui = getattr(self.sim, "character_ui", {
            "open": False,
            "title": "Character Sheet",
            "pages": [],
            "page_index": 0,
            "page_label": "Summary",
            "page_scrolls": {},
            "lines": [],
            "scroll": 0,
        })
        report_ui = _report_debug_ui.ensure_report_ui_state(self.sim)
        log_ui = getattr(self.sim, "log_ui", {
            "open": False,
            "title": "Event Log",
            "lines": [],
            "scroll": 0,
        })
        debug_ui = _report_debug_ui.ensure_debug_ui_state(self.sim)

        screen_w, screen_h = self.view.size()
        configured_hud_lines = max(1, int(self.hud_lines))
        map_h = max(1, min(self.sim.tilemap.height, screen_h - configured_hud_lines))
        hud_lines = max(
            1,
            min(
                max(1, int(screen_h) - 1),
                max(configured_hud_lines, int(screen_h) - int(map_h)),
            ),
        )
        map_w = min(self.sim.tilemap.width, screen_w)
        hud_w = max(1, int(screen_w))
        hud_text_w = _view_text_wrap_width(self.view, hud_w)
        live_timeskip = getattr(self.sim, "live_timeskip", {})
        if isinstance(live_timeskip, dict) and bool(live_timeskip.get("active")):
            service = str(live_timeskip.get("service", "") or "").strip().lower()
            prop_name = str(live_timeskip.get("property_name", live_timeskip.get("property_id", "site")) or "site").strip() or "site"
            title = "Sleeping..." if service == "rest" else "Laying low..."
            started_tick = int(live_timeskip.get("started_tick", 0) or 0)
            total_ticks = max(0, int(live_timeskip.get("total_ticks", 0) or 0))
            elapsed_ticks = max(
                int(live_timeskip.get("elapsed_ticks", 0) or 0),
                max(0, min(total_ticks, int(getattr(self.sim, "tick", 0)) - started_tick)),
            )
            panel_w = max(32, min(screen_w, 52))
            panel_h = max(8, min(screen_h, 10))
            panel_x = max(0, (screen_w - panel_w) // 2)
            panel_y = max(0, (screen_h - panel_h) // 2)
            top = "+" + ("-" * max(0, panel_w - 2)) + "+"
            mid = "|" + (" " * max(0, panel_w - 2)) + "|"
            bot = "+" + ("-" * max(0, panel_w - 2)) + "+"
            self.view.draw_text(panel_x, panel_y, top, color="human")
            for row in range(1, max(1, panel_h - 1)):
                self.view.draw_text(panel_x, panel_y + row, mid, color="human")
            self.view.draw_text(panel_x, panel_y + panel_h - 1, bot, color="human")

            def _clip(text, width):
                text = str(text or "")
                if width <= 0:
                    return ""
                if len(text) <= width:
                    return text
                if width <= 3:
                    return text[:width]
                return text[: width - 3] + "..."

            body_w = max(8, panel_w - 4)
            self.view.draw_text(panel_x + 2, panel_y + 1, _clip(title, body_w), color="objective")
            self.view.draw_text(panel_x + 2, panel_y + 3, _clip(prop_name, body_w), color="human")
            if total_ticks > 0:
                progress = f"{_tick_duration_label(self.sim, elapsed_ticks)} / {_tick_duration_label(self.sim, total_ticks)}"
                self.view.draw_text(panel_x + 2, panel_y + 4, _clip(progress, body_w), color="default")
            self.view.draw_text(panel_x + 2, panel_y + panel_h - 2, _clip("The city keeps moving without you.", body_w), color="default")
            return
        camera_x = (player_pos.x - (map_w // 2)) if player_pos else 0
        camera_y = (player_pos.y - (map_h // 2)) if player_pos else 0
        zoom_mode = str(getattr(self.sim, "zoom_mode", "city")).lower()
        look_purpose = str(look_ui.get("purpose", "inspect")).lower()
        visibility_state = getattr(self.sim, "visibility_state", {})
        player_visible = visibility_state.get("player_visible", set()) if isinstance(visibility_state, dict) else set()
        player_explored = visibility_state.get("player_explored", set()) if isinstance(visibility_state, dict) else set()
        if not isinstance(player_visible, set):
            player_visible = set(player_visible or ())
        if not isinstance(player_explored, set):
            player_explored = set(player_explored or ())
        player_tile_memory = _player_tile_memory_state(self.sim)
        if player_tile_memory and player_explored:
            stale_keys = [key for key in player_tile_memory.keys() if key not in player_explored]
            for key in stale_keys:
                player_tile_memory.pop(key, None)

        def _is_visible(x, y, z):
            return (int(x), int(y), int(z)) in player_visible

        def _is_explored(x, y, z):
            return (int(x), int(y), int(z)) in player_explored

        def _remember_tile_appearance(x, y, z, appearance):
            player_tile_memory[(int(x), int(y), int(z))] = appearance

        def _remembered_tile_appearance(x, y, z):
            return player_tile_memory.get((int(x), int(y), int(z)))

        lighting_state = _lighting_state(self.sim)
        if int(lighting_state.get("tick", -1)) != int(getattr(self.sim, "tick", 0)):
            lighting_state = _update_lighting_state(self.sim, player_pos=player_pos)
        if debug_ui.get("open"):
            debug_panel = _build_debug_overlay(
                self.sim,
                self.player_eid,
                duration_label_fn=_tick_duration_label,
                property_access_summary_fn=_property_access_summary,
            )
            debug_ui["title"] = str(debug_panel.get("title", "Debug Overlay")).strip() or "Debug Overlay"
            debug_ui["lines"] = list(debug_panel.get("lines", ()) or ())
        ambient_cache = {}
        ambient_dim_attr = getattr(curses, "A_DIM", 0)

        def _ambient_sample(x, y, z):
            key = (int(x), int(y), int(z))
            cached = ambient_cache.get(key)
            if isinstance(cached, dict):
                return cached
            sampled = _lighting_ambient_snapshot(self.sim, x, y, z, clock=lighting_state)
            ambient_cache[key] = sampled
            return sampled

        def _ambient_attr(x, y, z):
            if not ambient_dim_attr:
                return 0
            sample = _ambient_sample(x, y, z)
            try:
                ambient = float(sample.get("ambient", 1.0))
            except (TypeError, ValueError):
                ambient = 1.0
            if ambient >= 0.72:
                return 0
            return ambient_dim_attr

        if zoom_mode == "overworld":
            if player_pos:
                center_cx, center_cy = self.sim.chunk_coords(player_pos.x, player_pos.y)
            else:
                center_cx, center_cy = 0, 0

            legend_top_rows = 1 if map_h >= 4 else 0
            legend_bottom_rows = 1 if map_h >= 4 else 0
            usable_map_h = max(1, map_h - legend_top_rows - legend_bottom_rows)
            cell_w = max(2, int(self.OVERWORLD_CELL_W))
            cell_h = max(1, int(self.OVERWORLD_CELL_H))
            grid_w = max(1, map_w // cell_w)
            grid_h = max(1, usable_map_h // cell_h)
            origin_x = max(0, (map_w - (grid_w * cell_w)) // 2)
            origin_y = legend_top_rows + max(0, (usable_map_h - (grid_h * cell_h)) // 2)
            half_w = grid_w // 2
            half_h = grid_h // 2
            loaded = {(center_cx, center_cy)}
            knowledge = _overworld_chunk_knowledge(
                self.sim,
                self.player_eid,
                current_chunk=(center_cx, center_cy),
            )
            region_dim_attr = getattr(curses, "A_DIM", 0)
            fill_attrs = getattr(curses, "A_DIM", 0)
            unknown_fill_attrs = getattr(curses, "A_DIM", 0)
            path_attrs = 0
            markers = self._player_overworld_markers()
            nearest_marker_id = None
            if markers:
                nearest = min(
                    markers,
                    key=lambda marker: (
                        _manhattan(
                            center_cx,
                            center_cy,
                            marker["chunk"][0],
                            marker["chunk"][1],
                        ),
                        marker["id"],
                    ),
                )
                nearest_marker_id = nearest["id"]
            cursor_active = bool(look_ui.get("active")) and str(look_ui.get("mode", "")).lower() == "overworld"
            cursor_chunk = None
            if cursor_active:
                cursor_chunk = (
                    int(look_ui.get("chunk_x", center_cx)),
                    int(look_ui.get("chunk_y", center_cy)),
                )
            badge_chunks = {(center_cx, center_cy)}
            badge_chunks.update(tuple(marker["chunk"]) for marker in markers)
            if cursor_chunk is not None and cursor_chunk != (center_cx, center_cy):
                badge_chunks.add(cursor_chunk)

            def _overworld_cell_slots(cell_origin_x, cell_origin_y, *, reserve_badge=False):
                center_y = cell_origin_y + (cell_h // 2)
                center_x = cell_origin_x + (cell_w // 2)
                if not reserve_badge or cell_w < 3:
                    return center_x, center_y, center_x, center_y
                inner_left = cell_origin_x + 1
                inner_right = cell_origin_x + cell_w - 2
                if inner_right <= inner_left:
                    return center_x, center_y, center_x, center_y
                icon_x = inner_left + ((inner_right - inner_left) // 2)
                badge_x = inner_right
                return icon_x, center_y, badge_x, center_y

            cell_data = {}
            for gy in range(grid_h):
                for gx in range(grid_w):
                    cx = center_cx + (gx - half_w)
                    cy = center_cy + (gy - half_h)
                    view = _overworld_chunk_view(
                        self.sim,
                        self.player_eid,
                        (cx, cy),
                        knowledge=knowledge,
                    )
                    awareness = str(view.get("awareness", "unknown")).strip().lower() or "unknown"
                    desc = view.get("desc") if isinstance(view.get("desc"), dict) else {}
                    interest = view.get("interest") if isinstance(view.get("interest"), dict) else {}
                    if awareness in {"current", "memory", "adjacent_live"}:
                        area = str(desc.get("area_type", "city")).strip().lower() or "city"
                        district = str(desc.get("district_type", "residential")).strip().lower() or "residential"
                        terrain = str(desc.get("terrain", "")).strip().lower()
                        path = str(desc.get("path", "")).strip().lower()
                        landmark = desc.get("landmark")
                        region_name = str(desc.get("region_name", "")).strip().lower()
                        settlement_name = str(desc.get("settlement_name", "")).strip().lower()
                        if area == "city":
                            region_key = f"city:{settlement_name or region_name or 'metro'}"
                        else:
                            region_key = f"{area}:{region_name or terrain or 'wilds'}"
                    else:
                        area = ""
                        district = ""
                        terrain = ""
                        path = ""
                        landmark = {}
                        region_key = None
                    cell_data[(gx, gy)] = {
                        "cx": cx,
                        "cy": cy,
                        "view": view,
                        "awareness": awareness,
                        "desc": desc,
                        "area": area,
                        "district": district,
                        "terrain": terrain,
                        "path": path,
                        "interest": interest,
                        "landmark": landmark,
                        "region_key": region_key,
                    }

            def _draw_overworld_frame(cell_origin_x, cell_origin_y, color, attrs, semantic_prefix, *, priority_base):
                left_x = cell_origin_x
                right_x = cell_origin_x + cell_w - 1
                top_y = cell_origin_y
                bottom_y = cell_origin_y + cell_h - 1
                for dx in range(cell_w):
                    sx = cell_origin_x + dx
                    if 0 <= sx < map_w and 0 <= top_y < map_h:
                        self._draw(
                            sx,
                            top_y,
                            "─",
                            color=color,
                            attrs=attrs,
                            semantic_id=f"{semantic_prefix}_horizontal",
                            layer="ui_overlay",
                            priority=priority_base,
                        )
                    if 0 <= sx < map_w and 0 <= bottom_y < map_h:
                        self._draw(
                            sx,
                            bottom_y,
                            "─",
                            color=color,
                            attrs=attrs,
                            semantic_id=f"{semantic_prefix}_horizontal",
                            layer="ui_overlay",
                            priority=priority_base,
                        )
                for dy in range(cell_h):
                    sy = cell_origin_y + dy
                    if 0 <= left_x < map_w and 0 <= sy < map_h:
                        self._draw(
                            left_x,
                            sy,
                            "│",
                            color=color,
                            attrs=attrs,
                            semantic_id=f"{semantic_prefix}_vertical",
                            layer="ui_overlay",
                            priority=priority_base,
                        )
                    if 0 <= right_x < map_w and 0 <= sy < map_h:
                        self._draw(
                            right_x,
                            sy,
                            "│",
                            color=color,
                            attrs=attrs,
                            semantic_id=f"{semantic_prefix}_vertical",
                            layer="ui_overlay",
                            priority=priority_base,
                        )
                corners = (
                    (left_x, top_y, "┌", f"{semantic_prefix}_corner_nw"),
                    (right_x, top_y, "┐", f"{semantic_prefix}_corner_ne"),
                    (left_x, bottom_y, "└", f"{semantic_prefix}_corner_sw"),
                    (right_x, bottom_y, "┘", f"{semantic_prefix}_corner_se"),
                )
                for corner_x, corner_y, glyph, semantic_id in corners:
                    if 0 <= corner_x < map_w and 0 <= corner_y < map_h:
                        self._draw(
                            corner_x,
                            corner_y,
                            glyph,
                            color=color,
                            attrs=attrs,
                            semantic_id=semantic_id,
                            layer="ui_overlay",
                            priority=priority_base + 2,
                        )

            for gy in range(grid_h):
                for gx in range(grid_w):
                    data = cell_data[(gx, gy)]
                    cx = int(data["cx"])
                    cy = int(data["cy"])
                    awareness = str(data.get("awareness", "unknown"))
                    view = data.get("view") if isinstance(data.get("view"), dict) else {}
                    desc = data.get("desc") if isinstance(data.get("desc"), dict) else {}
                    area = str(data["area"])
                    district = str(data["district"])
                    terrain = str(data["terrain"])
                    path = str(data["path"])
                    interest = data["interest"] if isinstance(data["interest"], dict) else {}
                    landmark = data["landmark"] if isinstance(data["landmark"], dict) else {}
                    cell_origin_x = origin_x + (gx * cell_w)
                    cell_origin_y = origin_y + (gy * cell_h)
                    fill_semantic = None
                    fill_glyph = ""
                    fill_color = None
                    cell_fill_attrs = 0
                    glyph = ""
                    color = None

                    if awareness in {"current", "memory", "adjacent_live"}:
                        if area == "city":
                            fill_glyph = self.OVERWORLD_DISTRICT_FILL_GLYPHS.get(district, ".")
                            fill_color = self.OVERWORLD_DISTRICT_COLORS.get(
                                district,
                                self.OVERWORLD_AREA_COLORS.get(area, "human"),
                            )
                        else:
                            fill_glyph = self.OVERWORLD_TERRAIN_FILL_GLYPHS.get(
                                terrain,
                                self.OVERWORLD_AREA_FILL_GLYPHS.get(area, "."),
                            )
                            fill_color = self.OVERWORLD_TERRAIN_COLORS.get(
                                terrain,
                                self.OVERWORLD_AREA_COLORS.get(area, "human"),
                            )
                        fill_semantic = _overworld_fill_semantic_id(area, district, terrain)
                        cell_fill_attrs = fill_attrs
                        glyph, color = _overworld_render_style_from_snapshot(
                            desc,
                            interest,
                            loaded=awareness in {"current", "adjacent_live"},
                        )
                    elif awareness == "lead":
                        fill_glyph = "."
                        fill_color = "terrain_block"
                        cell_fill_attrs = unknown_fill_attrs
                        glyph = "?"
                        color = "player"
                    elif awareness == "adjacent":
                        fill_glyph = "."
                        fill_color = "terrain_block"
                        cell_fill_attrs = unknown_fill_attrs

                    if fill_glyph:
                        for dy in range(cell_h):
                            for dx in range(cell_w):
                                screen_x = cell_origin_x + dx
                                screen_y = cell_origin_y + dy
                                if 0 <= screen_x < map_w and 0 <= screen_y < map_h:
                                    self._draw(
                                        screen_x,
                                        screen_y,
                                        fill_glyph,
                                        color=fill_color,
                                        attrs=cell_fill_attrs,
                                        semantic_id=fill_semantic,
                                        layer="terrain",
                                        priority=-600,
                                    )

                    if awareness in {"current", "memory", "adjacent_live"} and path:
                        mid_y = cell_origin_y + (cell_h // 2)
                        path_semantic = f"overworld_path_{path}"
                        for dx in range(cell_w):
                            screen_x = cell_origin_x + dx
                            if 0 <= screen_x < map_w and 0 <= mid_y < map_h:
                                self._draw(
                                    screen_x,
                                    mid_y,
                                    self.OVERWORLD_PATH_GLYPHS.get(path, "="),
                                    color=self.OVERWORLD_PATH_COLORS.get(path, "human"),
                                    attrs=path_attrs,
                                    semantic_id=path_semantic,
                                    layer="ground_overlay",
                                    priority=-420,
                                )

                    # Draw soft region boundaries so outside areas read as larger landmasses.
                    if gx + 1 < grid_w:
                        right = cell_data[(gx + 1, gy)]
                        if data.get("region_key") and right.get("region_key") and data["region_key"] != right.get("region_key"):
                            border_x = cell_origin_x + cell_w - 1
                            for dy in range(cell_h):
                                screen_y = cell_origin_y + dy
                                if 0 <= border_x < map_w and 0 <= screen_y < map_h:
                                    ch = "│"
                                    self._draw(
                                        border_x,
                                        screen_y,
                                        ch,
                                        color="terrain_block",
                                        attrs=region_dim_attr,
                                        semantic_id="overworld_boundary_vertical",
                                        layer="ground_overlay",
                                        priority=-320,
                                    )
                    if gy + 1 < grid_h:
                        below = cell_data[(gx, gy + 1)]
                        if data.get("region_key") and below.get("region_key") and data["region_key"] != below.get("region_key"):
                            border_y = cell_origin_y + cell_h - 1
                            for dx in range(cell_w):
                                screen_x = cell_origin_x + dx
                                if 0 <= screen_x < map_w and 0 <= border_y < map_h:
                                    ch = "─"
                                    self._draw(
                                        screen_x,
                                        border_y,
                                        ch,
                                        color="terrain_block",
                                        attrs=region_dim_attr,
                                        semantic_id="overworld_boundary_horizontal",
                                        layer="ground_overlay",
                                        priority=-320,
                                    )

                    if (cx, cy) == (center_cx, center_cy):
                        focus_attr = getattr(curses, "A_BOLD", 0)
                        _draw_overworld_frame(cell_origin_x, cell_origin_y, "player", focus_attr, "overworld_focus", priority_base=-60)

                    if cursor_chunk is not None and (cx, cy) == cursor_chunk and (cx, cy) != (center_cx, center_cy):
                        selector_attr = getattr(curses, "A_BOLD", 0)
                        _draw_overworld_frame(cell_origin_x, cell_origin_y, "player", selector_attr, "overworld_selector", priority_base=-40)

                    if glyph:
                        reserve_badge = (cx, cy) in badge_chunks
                        screen_x, screen_y, _badge_x, _badge_y = _overworld_cell_slots(
                            cell_origin_x,
                            cell_origin_y,
                            reserve_badge=reserve_badge,
                        )
                        if 0 <= screen_x < map_w and 0 <= screen_y < map_h:
                            if awareness in {"current", "adjacent_live"}:
                                glyph_attrs = getattr(curses, "A_BOLD", 0)
                            else:
                                glyph_attrs = getattr(curses, "A_DIM", 0)
                            glyph_semantic = None
                            if awareness in {"current", "memory", "adjacent_live"}:
                                glyph_semantic = _overworld_center_semantic_id(
                                    cx,
                                    cy,
                                    area,
                                    district,
                                    terrain,
                                    landmark,
                                    interest,
                                    loaded,
                                )
                            self._draw(
                                screen_x,
                                screen_y,
                                glyph,
                                color=color,
                                attrs=glyph_attrs,
                                semantic_id=glyph_semantic or None,
                                layer="actor",
                                priority=-120,
                            )

            for marker in markers:
                cx, cy = marker["chunk"]
                gx = half_w + (cx - center_cx)
                gy = half_h + (cy - center_cy)
                if not (0 <= gx < grid_w and 0 <= gy < grid_h):
                    continue
                cell_origin_x = origin_x + (gx * cell_w)
                cell_origin_y = origin_y + (gy * cell_h)
                _icon_x, _icon_y, screen_x, screen_y = _overworld_cell_slots(
                    cell_origin_x,
                    cell_origin_y,
                    reserve_badge=True,
                )
                if not (0 <= screen_x < map_w and 0 <= screen_y < map_h):
                    continue
                is_nearest = marker["id"] == nearest_marker_id
                glyph = "!" if is_nearest else str(int(marker["id"]) % 10)
                color = "player" if is_nearest else "human"
                self._draw(
                    screen_x,
                    screen_y,
                    glyph,
                    color=color,
                    semantic_id="overworld_marker_nearest" if is_nearest else "overworld_marker",
                    layer="ui_overlay",
                    priority=40 if is_nearest else 30,
                )

            player_cell_origin_x = origin_x + (half_w * cell_w)
            player_cell_origin_y = origin_y + (half_h * cell_h)
            _player_icon_x, _player_icon_y, player_screen_x, player_screen_y = _overworld_cell_slots(
                player_cell_origin_x,
                player_cell_origin_y,
                reserve_badge=True,
            )
            if 0 <= player_screen_x < map_w and 0 <= player_screen_y < map_h:
                self._draw(
                    player_screen_x,
                    player_screen_y,
                    "@",
                    color="player",
                    semantic_id="overworld_player",
                    layer="ui_overlay",
                    priority=50,
                )

            if legend_top_rows or legend_bottom_rows:
                current_desc = self.sim.world.overworld_descriptor(center_cx, center_cy)
                current_interest = self.sim.world.overworld_interest(center_cx, center_cy, descriptor=current_desc)
                edge_header, edge_footer = _overworld_edge_legend_lines(
                    self.sim,
                    (center_cx, center_cy),
                    desc=current_desc,
                    interest=current_interest,
                    markers=markers,
                    look_ui=look_ui,
                )
                if legend_top_rows:
                    edge_segments = _line_segments(edge_header)
                    if edge_segments:
                        self.view.draw_segments(0, 0, edge_segments, max_width=map_w, layer="ui_overlay", priority=90)
                    else:
                        self.view.draw_text(0, 0, _line_text(edge_header), layer="ui_overlay", priority=90)
                if legend_bottom_rows:
                    footer_y = max(0, map_h - 1)
                    edge_segments = _line_segments(edge_footer)
                    if edge_segments:
                        self.view.draw_segments(0, footer_y, edge_segments, max_width=map_w, layer="ui_overlay", priority=90)
                    else:
                        self.view.draw_text(0, footer_y, _line_text(edge_footer), layer="ui_overlay", priority=90)
        else:
            revealed_building_id = _viewer_revealed_building_id(self.sim, self.player_eid, z=active_z)
            for sy in range(map_h):
                for sx in range(map_w):
                    wx = camera_x + sx
                    wy = camera_y + sy
                    detail = self.sim.detail_for_xy(wx, wy)
                    if detail == "unloaded":
                        self._draw(sx, sy, " ", layer="terrain", priority=-1000)
                        continue
                    visible_now = _is_visible(wx, wy, active_z)
                    explored = _is_explored(wx, wy, active_z)
                    if not visible_now and not explored:
                        self._draw(sx, sy, " ", layer="terrain", priority=-1000)
                        continue

                    tile = self.sim.tilemap.tile_at(wx, wy, active_z)
                    appearance = self.sim.appearance.tile(
                        tile,
                        wx,
                        wy,
                        z=active_z,
                        revealed_building_id=revealed_building_id,
                    )
                    if visible_now:
                        _remember_tile_appearance(wx, wy, active_z, appearance)
                        attrs = _ambient_attr(wx, wy, active_z)
                    else:
                        remembered = _remembered_tile_appearance(wx, wy, active_z)
                        if remembered is not None:
                            appearance = remembered
                        attrs = getattr(curses, "A_DIM", 0)
                    if _appearance_prefers_floor_underlay(appearance):
                        floor_glyph = _district_floor_glyph(self.sim, wx, wy)
                        floor_color = _district_floor_color(self.sim, wx, wy)
                        self._draw(
                            sx,
                            sy,
                            floor_glyph,
                            color=floor_color,
                            attrs=attrs,
                            semantic_id=self.sim.appearance.semantic_id_for(
                                floor_glyph,
                                floor_color,
                                preferred_categories=("terrain",),
                            ),
                            layer="terrain",
                            priority=-1000,
                        )
                    self._draw_appearance(sx, sy, appearance, attrs=attrs)

            active_quest_target = active_final_operation_target_property_id(self.sim)

            for prop in self.sim.properties.values():
                display_pos = _property_display_position(prop, active_quest_target=active_quest_target)
                if not display_pos:
                    continue
                screen_x = display_pos[0] - camera_x
                screen_y = display_pos[1] - camera_y
                if not (0 <= screen_x < map_w and 0 <= screen_y < map_h):
                    continue
                if self.sim.detail_for_xy(display_pos[0], display_pos[1]) == "unloaded":
                    continue
                visible_now = _is_visible(display_pos[0], display_pos[1], active_z)
                explored = _is_explored(display_pos[0], display_pos[1], active_z)
                if not visible_now and not explored:
                    continue
                tile = self.sim.tilemap.tile_at(display_pos[0], display_pos[1], active_z)
                if (
                    str(prop.get("kind", "") or "").strip().lower() != "vehicle"
                    and _tile_prefers_feature_legend(self.sim, tile, display_pos[0], display_pos[1], active_z)
                ):
                    continue

                appearance = self.sim.appearance.property(
                    prop,
                    active_quest_target=active_quest_target,
                )
                if visible_now:
                    attrs = _ambient_attr(display_pos[0], display_pos[1], active_z)
                else:
                    attrs = getattr(curses, "A_DIM", 0)
                self._draw_appearance(screen_x, screen_y, appearance, attrs=attrs)

            for ground in self.sim.ground_items.values():
                if ground["z"] != active_z:
                    continue
                screen_x = ground["x"] - camera_x
                screen_y = ground["y"] - camera_y
                if not (0 <= screen_x < map_w and 0 <= screen_y < map_h):
                    continue
                if self.sim.detail_for_xy(ground["x"], ground["y"]) == "unloaded":
                    continue
                if not _is_visible(ground["x"], ground["y"], active_z):
                    continue

                item_def = ITEM_CATALOG.get(ground["item_id"], {})
                appearance = self.sim.appearance.item(item_def)
                attrs = getattr(curses, "A_BOLD", 0) | _ambient_attr(ground["x"], ground["y"], active_z)
                self._draw_appearance(screen_x, screen_y, appearance, attrs=attrs)

            for projectile in self.sim.projectiles.values():
                if projectile.get("z") != active_z:
                    continue
                wx = int(projectile.get("x", -1))
                wy = int(projectile.get("y", -1))
                screen_x = wx - camera_x
                screen_y = wy - camera_y
                if not (0 <= screen_x < map_w and 0 <= screen_y < map_h):
                    continue
                if self.sim.detail_for_xy(wx, wy) == "unloaded":
                    continue
                if not _is_visible(wx, wy, active_z):
                    continue
                projectile_glyph = str(projectile.get("projectile_glyph", "."))[:1] or "."
                appearance = self.sim.appearance.projectile(projectile_glyph)
                self._draw_appearance(
                    screen_x,
                    screen_y,
                    appearance,
                    attrs=_ambient_attr(wx, wy, active_z),
                )

            for coord, cell in tuple(fire_state(self.sim).get("cells", {}).items()):
                if not isinstance(coord, tuple) or len(coord) < 3 or not isinstance(cell, dict):
                    continue
                if int(coord[2]) != int(active_z):
                    continue
                screen_x = int(coord[0]) - camera_x
                screen_y = int(coord[1]) - camera_y
                if not (0 <= screen_x < map_w and 0 <= screen_y < map_h):
                    continue
                if self.sim.detail_for_xy(int(coord[0]), int(coord[1])) == "unloaded":
                    continue
                if not _is_visible(int(coord[0]), int(coord[1]), active_z):
                    continue
                visual = _fire_visual_style(self.sim, int(coord[0]), int(coord[1]), int(coord[2]))
                if not isinstance(visual, dict):
                    continue
                self._draw(
                    screen_x,
                    screen_y,
                    visual.get("glyph", "*"),
                    color=visual.get("color"),
                    attrs=int(visual.get("attrs", 0) or 0) | _ambient_attr(int(coord[0]), int(coord[1]), active_z),
                    semantic_id=visual.get("semantic_id"),
                    effects=tuple(visual.get("effects", ())),
                    layer=visual.get("layer"),
                    priority=visual.get("priority"),
                )

            player_cover_source = _cover_source_render(
                self.sim,
                covers.get(self.player_eid),
                active_quest_target=active_quest_target,
            )
            if player_cover_source and int(player_cover_source["z"]) == int(active_z):
                screen_x = int(player_cover_source["x"]) - camera_x
                screen_y = int(player_cover_source["y"]) - camera_y
                if 0 <= screen_x < map_w and 0 <= screen_y < map_h:
                    if not _is_visible(player_cover_source["x"], player_cover_source["y"], active_z):
                        player_cover_source = None
                if player_cover_source and 0 <= screen_x < map_w and 0 <= screen_y < map_h:
                    attrs = player_cover_source["attrs"] | _ambient_attr(
                        player_cover_source["x"],
                        player_cover_source["y"],
                        active_z,
                    )
                    self._draw(
                        screen_x,
                        screen_y,
                        player_cover_source["glyph"],
                        color=player_cover_source["color"],
                        semantic_id=player_cover_source.get("semantic_id"),
                        overlays=player_cover_source.get("overlays"),
                        attrs=attrs,
                        layer="ground_overlay",
                        priority=30,
                    )

            drawables = []
            for eid, pos in positions.items():
                render = renders.get(eid)
                if not render:
                    continue
                if pos.z != active_z:
                    continue
                screen_x = pos.x - camera_x
                screen_y = pos.y - camera_y
                if not (0 <= screen_x < map_w and 0 <= screen_y < map_h):
                    continue
                if eid != self.player_eid and not _is_visible(pos.x, pos.y, pos.z):
                    continue
                drawables.append((pos.z, eid, pos, render, screen_x, screen_y))

            for _, eid, _pos, render, screen_x, screen_y in sorted(drawables, key=lambda item: (item[0], item[1])):
                appearance = _entity_render_style(self.sim, eid, player_eid=self.player_eid)
                attrs = _ambient_attr(_pos.x, _pos.y, _pos.z)
                if _entity_should_blink_in_combat(self.sim, eid, player_eid=self.player_eid):
                    appearance = _appearance_with_effect(appearance, "blink")
                elif _entity_should_mark_ambient_combat(self.sim, eid, player_eid=self.player_eid):
                    appearance = _appearance_with_effect(appearance, "combat_ambient")
                    attrs |= getattr(curses, "A_BOLD", 0)
                fire_cell = fire_cell_state(self.sim, _pos.x, _pos.y, _pos.z)
                if isinstance(fire_cell, dict) and int(fire_cell.get("fire_intensity", 0) or 0) > 0:
                    appearance = _appearance_with_effect(appearance, "blink")
                self._draw_appearance(
                    screen_x,
                    screen_y,
                    appearance,
                    attrs=attrs,
                )

            radio_scan = getattr(self.sim, "world_traits", {}).get("justice_radio_scan", {})
            if isinstance(radio_scan, dict) and int(radio_scan.get("expires_tick", -1) or -1) >= int(getattr(self.sim, "tick", 0)):
                ping_attr = getattr(curses, "A_BOLD", 0) | getattr(curses, "A_REVERSE", 0)
                for row in tuple(radio_scan.get("positions", ()) or ()):
                    if not isinstance(row, dict):
                        continue
                    wx = int(row.get("x", 0) or 0)
                    wy = int(row.get("y", 0) or 0)
                    wz = int(row.get("z", 0) or 0)
                    if wz != int(active_z):
                        continue
                    if self.sim.detail_for_xy(wx, wy) == "unloaded":
                        continue
                    if _is_visible(wx, wy, wz):
                        continue
                    sx = wx - camera_x
                    sy = wy - camera_y
                    if not (0 <= sx < map_w and 0 <= sy < map_h):
                        continue
                    appearance = self.sim.appearance.marker(
                        "justice_radio_ping",
                        "!",
                        color="player",
                        layer="ui_overlay",
                        priority=95,
                    )
                    self._draw_appearance(sx, sy, appearance, attrs=ping_attr)

            if look_ui.get("active") and look_purpose == "aim" and player_pos:
                preview = _manual_fire_preview(
                    self.sim,
                    eid=self.player_eid,
                    x=int(look_ui.get("x", player_pos.x)),
                    y=int(look_ui.get("y", player_pos.y)),
                    z=int(look_ui.get("z", active_z)),
                )
                projectile_glyph = str(preview.get("projectile_glyph", "."))[:1] or "."
                dim_attr = getattr(curses, "A_DIM", 0)
                occupied = {(item[4], item[5]) for item in drawables}
                for px, py in preview.get("path", []):
                    sx = int(px) - camera_x
                    sy = int(py) - camera_y
                    if not (0 <= sx < map_w and 0 <= sy < map_h):
                        continue
                    if not _is_visible(px, py, active_z):
                        continue
                    if (sx, sy) in occupied:
                        continue
                    appearance = self.sim.appearance.projectile(projectile_glyph, priority=-20)
                    self._draw_appearance(
                        sx,
                        sy,
                        appearance,
                        attrs=dim_attr,
                    )

            if look_ui.get("active") and str(look_ui.get("mode", "")).lower() == "city":
                cursor_x = int(look_ui.get("x", player_pos.x if player_pos else 0))
                cursor_y = int(look_ui.get("y", player_pos.y if player_pos else 0))
                cursor_z = int(look_ui.get("z", active_z))
                if cursor_z == active_z:
                    sx = cursor_x - camera_x
                    sy = cursor_y - camera_y
                    if 0 <= sx < map_w and 0 <= sy < map_h:
                        visible_now = _is_visible(cursor_x, cursor_y, cursor_z)
                        explored = _is_explored(cursor_x, cursor_y, cursor_z)
                        if visible_now or explored:
                            glyph = "@"
                            if not player_pos or (cursor_x, cursor_y, cursor_z) != (player_pos.x, player_pos.y, player_pos.z):
                                glyph = "X"
                            attrs = getattr(curses, "A_REVERSE", 0)
                            if not visible_now:
                                attrs |= getattr(curses, "A_DIM", 0)
                            else:
                                attrs |= _ambient_attr(cursor_x, cursor_y, cursor_z)
                            appearance = self.sim.appearance.marker(
                                "ui_cursor" if glyph == "@" else "ui_look_cursor",
                                glyph,
                                color="player",
                            )
                            self._draw_appearance(
                                sx,
                                sy,
                                appearance,
                                attrs=attrs,
                            )

        chunk = getattr(self.sim, "active_chunk", {})
        if not isinstance(chunk, dict):
            chunk = {}
        district = chunk.get("district", {})
        if not isinstance(district, dict):
            district = {}
        area_type = district.get("area_type", "city")
        district_type = district.get("district_type", "unknown")
        security = district.get("security_level", "?")

        assets = self.sim.ecs.get(PlayerAssets).get(self.player_eid)
        player_needs = self.sim.ecs.get(NPCNeeds).get(self.player_eid)
        insight = self.sim.ecs.get(SkillProfile).get(self.player_eid)
        if not insight:
            insight = self.sim.ecs.get(InsightStats).get(self.player_eid)
        core_stats = self.sim.ecs.get(CoreStats).get(self.player_eid)
        if not insight:
            insight = core_stats
        credits = assets.credits if assets else 0
        owned = len(assets.owned_property_ids) if assets else 0
        inventory = inventories.get(self.player_eid)
        finance = financials.get(self.player_eid)
        loadout = loadouts.get(self.player_eid)
        armor_loadout = self.sim.ecs.get(ArmorLoadout).get(self.player_eid)
        vitality = vitalities.get(self.player_eid)
        carried_slots = inventory.slot_count() if inventory else 0
        carried_units = sum(item["quantity"] for item in inventory.items) if inventory else 0
        status_effects = effects_map.get(self.player_eid)
        active_status_count = len(status_effects.active) if status_effects else 0
        active_status_summary = _active_status_summary(status_effects, max_names=1, title=True)
        player_cover = covers.get(self.player_eid)
        player_modes = modes.get(self.player_eid)
        player_vehicle_state = vehicle_states.get(self.player_eid)
        active_disguise = getattr(self.sim, "disguise_state", None)
        active_vehicle_prop = None
        if player_vehicle_state and player_vehicle_state.active_vehicle_id:
            maybe_vehicle = self.sim.properties.get(player_vehicle_state.active_vehicle_id)
            if _property_is_vehicle(maybe_vehicle):
                active_vehicle_prop = maybe_vehicle
        weapon_name = "none"
        ammo_text = "-"
        if loadout and loadout.current_weapon():
            weapon = weapon_by_id(loadout.current_weapon())
            instance = loadout.weapon_instance(loadout.current_weapon())
            weapon_name = str(instance.get("custom_name") or weapon.get("name", weapon.get("id", "weapon")))
            if _weapon_uses_ammo(weapon):
                ammo_type = _weapon_ammo_type_label(weapon)
                reserve = _weapon_reserve_ammo(loadout, loadout.current_weapon())
                if reserve is None:
                    reserve = int(loadout.reserve_ammo_value(
                        loadout.current_weapon(),
                        default=_default_weapon_reserve_ammo(weapon),
                    ))
                ammo_text = f"{int(reserve)} {ammo_type}"
            else:
                ammo_text = "melee"
        armor_name = "none"
        if armor_loadout and armor_loadout.equipped_instance_id:
            armor_name = str(armor_loadout.equipped_name or armor_loadout.equipped_item_id or "armor")
        hp_text = "?"
        if vitality:
            hp_text = f"{vitality.hp}/{vitality.max_hp}"

        status_chunks = _hud_primary_status_chunks(
            self.sim,
            zoom_mode=zoom_mode,
            active_z=active_z,
            player_pos=player_pos,
            lighting_state=lighting_state,
            area_type=area_type,
            district_type=district_type,
            security=security,
        )
        try:
            outside_pct = int(round(float(lighting_state.get("outside_ambient", 1.0)) * 100.0))
        except (TypeError, ValueError):
            outside_pct = 100
        outside_pct = max(0, min(100, outside_pct))
        if zoom_mode != "overworld" and player_pos:
            player_inside = bool(lighting_state.get("player_inside", False))
            try:
                player_pct = int(round(float(lighting_state.get("player_ambient", outside_pct / 100.0)) * 100.0))
            except (TypeError, ValueError):
                player_pct = outside_pct
            player_pct = max(0, min(100, player_pct))
            context = "in" if player_inside else "out"
            status_chunks.append(f"Light {context} {player_pct}% (out {outside_pct}%)")
        else:
            status_chunks.append(f"Light out {outside_pct}%")
        if isinstance(active_disguise, dict):
            role_text = _disguise_role_label(active_disguise.get("role_id"), title_case=True)
            try:
                strength_pct = int(round(float(active_disguise.get("strength", 0.0)) * 100.0))
            except (TypeError, ValueError):
                strength_pct = 0
            status_chunks.append(f"Disguise {role_text} {max(0, strength_pct)}%")
        stakeout_snapshot = _stakeout_progress_snapshot(self.sim, self.player_eid, player_pos, require_hidden=False)
        if isinstance(stakeout_snapshot, dict) and (bool(stakeout_snapshot.get("hidden")) or bool(stakeout_snapshot.get("active"))):
            target_name = str(stakeout_snapshot.get("property_name", "site")).strip() or "site"
            if bool(stakeout_snapshot.get("mapped")):
                status_chunks.append(f"Stakeout {target_name} mapped")
            elif bool(stakeout_snapshot.get("active")):
                reveals_done = max(0, _int_or_default(stakeout_snapshot.get("reveals_done", 0), 0))
                max_reveals = max(1, _int_or_default(stakeout_snapshot.get("max_reveals", STAKEOUT_MAX_REVEALS), STAKEOUT_MAX_REVEALS))
                next_reveal_in = max(1, _int_or_default(stakeout_snapshot.get("next_reveal_in", STAKEOUT_REVEAL_INTERVAL), STAKEOUT_REVEAL_INTERVAL))
                status_chunks.append(f"Stakeout {target_name} {reveals_done}/{max_reveals} next {next_reveal_in}t")
            else:
                status_chunks.append(f"Stakeout ready {target_name}")
        overlay = getattr(self.sim, "combat_overlay", {})
        if overlay.get("active"):
            threat_count = overlay.get("threat_count", 0)
            direct_count = overlay.get("direct_threat_count", threat_count)
            ambient_count = overlay.get("ambient_threat_count", 0)
            nearest = overlay.get("nearest_threat_dist")
            nearest_text = "?" if nearest is None else str(nearest)
            exposure = int(float(overlay.get("player_exposure", 1.0)) * 100)
            if ambient_count:
                threat_label = f"{direct_count} direct + {ambient_count} nearby"
            else:
                threat_label = str(threat_count)
            status_chunks.append(
                f"Combat threats {threat_label} near {nearest_text} exp {exposure}%"
            )
        if insight:
            status_chunks.extend(
                _skill_hud_status_chunks(
                    self.sim,
                    self.player_eid,
                    insight,
                    duration_label_fn=_tick_duration_label,
                )
            )
        if active_vehicle_prop:
            vehicle_name = _vehicle_label(active_vehicle_prop)
            fuel, fuel_capacity = _vehicle_fuel_values(active_vehicle_prop)
            mode_text = "driving" if (player_vehicle_state and player_vehicle_state.in_vehicle) else "parked"
            vehicle_bits = [f"Vehicle {vehicle_name} {mode_text} F{fuel}/{fuel_capacity}"]
            if player_pos and not (player_vehicle_state and player_vehicle_state.in_vehicle):
                vehicle_chunk = self.sim.chunk_coords(
                    int(active_vehicle_prop.get("x", player_pos.x)),
                    int(active_vehicle_prop.get("y", player_pos.y)),
                )
                player_chunk = self.sim.chunk_coords(int(player_pos.x), int(player_pos.y))
                if vehicle_chunk == player_chunk:
                    vehicle_bits.append("here")
                else:
                    vehicle_bits.append(f"offsite {vehicle_chunk[0]},{vehicle_chunk[1]}c")
            lock_state = property_lock_state(active_vehicle_prop)
            has_key = bool(
                lock_state["key_id"]
                and inventory_matching_property_key(
                    inventory,
                    property_id=active_vehicle_prop.get("id"),
                    key_id=lock_state["key_id"],
                ) is not None
            )
            hotwired = bool(_property_metadata(active_vehicle_prop).get("vehicle_hotwired"))
            if hotwired:
                vehicle_bits.append("hotwired")
            elif has_key:
                vehicle_bits.append("key")
            elif lock_state["locked"]:
                vehicle_bits.append("no-key")
            status_chunks.append(" ".join(vehicle_bits))
        if look_ui.get("active"):
            look_mode = str(look_ui.get("mode", zoom_mode)).lower()
            if look_purpose == "aim":
                label = "Aim"
            elif look_purpose == "interact":
                label = "Interact"
            elif look_purpose == "talk":
                label = "Talk"
            else:
                label = "Look"
            if look_mode == "overworld":
                look_coord = (
                    f"{int(look_ui.get('chunk_x', 0))},"
                    f"{int(look_ui.get('chunk_y', 0))}"
                )
                overworld_context = "map" if bool(
                    getattr(self.sim, "overworld_view_only_by_eid", {}).get(int(self.player_eid), False)
                ) else "in-vehicle"
                status_chunks.append(f"{label} {overworld_context} {look_coord}c")
            else:
                look_coord = (
                    f"{int(look_ui.get('x', 0))},"
                    f"{int(look_ui.get('y', 0))},"
                    f"{int(look_ui.get('z', active_z))}"
                )
                status_chunks.append(f"{label} on-foot {look_coord}")
                if look_purpose == "aim":
                    target_eid = _first_targetable_entity_at(
                        self.sim,
                        int(look_ui.get("x", 0)),
                        int(look_ui.get("y", 0)),
                        int(look_ui.get("z", active_z)),
                        exclude_eid=self.player_eid,
                    )
                    if target_eid is not None:
                        target_name = self._npc_label(target_eid)
                        condition = _target_condition_descriptor(
                            self.sim,
                            self.player_eid,
                            target_eid,
                            include_uncertainty=True,
                        )
                        if condition:
                            status_chunks.append(f"Target {target_name} ({condition})")
                        else:
                            status_chunks.append(f"Target {target_name}")
        status_lines = _flow_text_chunks(status_chunks, hud_text_w, max_lines=3)

        streamed_chunks = [
            f"Chunks {len(self.sim.chunk_detail)}",
            f"Active {sum(1 for detail in self.sim.chunk_detail.values() if detail == 'active')}",
            f"Entities {len(self.sim.tilemap.entities_on_floor(active_z))}",
        ]
        streamed_lines = []
        if zoom_mode == "overworld" and player_pos:
            current_chunk = self.sim.chunk_coords(player_pos.x, player_pos.y)
            desc = self.sim.world.overworld_descriptor(current_chunk[0], current_chunk[1])
            interest = self.sim.world.overworld_interest(current_chunk[0], current_chunk[1], descriptor=desc)
            travel = _overworld_travel_profile(self.sim, current_chunk[0], current_chunk[1], desc=desc, interest=interest)
            discovery = _overworld_discovery_profile(self.sim, current_chunk[0], current_chunk[1], desc=desc, interest=interest, travel=travel)
            identity = _overworld_identity_profile(
                self.sim,
                current_chunk[0],
                current_chunk[1],
                desc=desc,
                interest=interest,
                travel=travel,
                discovery=discovery,
            )
            markers = self._player_overworld_markers()
            streamed_lines = _overworld_hud_lines(
                self.sim,
                current_chunk[0],
                current_chunk[1],
                desc=desc,
                interest=interest,
                travel=travel,
                discovery=discovery,
                identity=identity,
                markers=markers,
                active_vehicle_prop=active_vehicle_prop,
            )
        else:
            streamed_lines = _flow_text_chunks(
                streamed_chunks,
                hud_text_w,
                max_lines=1,
            )

        economy_chunks = [
            f"Cr {credits}",
            f"Inv {carried_slots}/{inventory.capacity if inventory else 0} u{carried_units}",
            f"HP {hp_text}",
            f"Status {active_status_summary if active_status_count else 0}",
            f"Wpn {weapon_name}",
            f"Ammo {ammo_text}",
            f"Arm {armor_name}",
        ]
        if active_vehicle_prop:
            profile = _vehicle_profile_from_property(active_vehicle_prop)
            fuel, fuel_capacity = _vehicle_fuel_values(active_vehicle_prop)
            economy_chunks.append(f"Veh {_vehicle_label(active_vehicle_prop)} F{fuel}/{fuel_capacity}")
            economy_chunks.append(
                "Drive "
                f"P{_int_or_default(profile.get('power'), 5)}/"
                f"D{_int_or_default(profile.get('durability'), 5)}/"
                f"E{_int_or_default(profile.get('fuel_efficiency'), 5)}"
            )
        if player_needs:
            economy_chunks.append(
                f"Needs E{player_needs.energy:.0f}/S{player_needs.safety:.0f}/So{player_needs.social:.0f}"
            )
            economy_chunks.extend(_survival_indicator_chunks(player_needs, rich=True))
        pressure = _pressure_snapshot(self.sim)
        pressure_tier = str(pressure.get("tier", "low")).strip().lower()
        pressure_attention = int(pressure.get("attention", 0))
        economy_chunks.append(f"Heat {pressure_tier} {pressure_attention}")
        if player_cover:
            if player_cover.active:
                cover_text = f"{player_cover.cover_kind.upper()} {int(player_cover.cover_value * 100)}%"
                cover_source = _cover_source_label(self.sim, player_cover, short=True)
            else:
                cover_text = "NONE"
                cover_source = "-"
            economy_chunks.extend([
                f"Cover {cover_text}",
                f"Exp {int(player_cover.exposure * 100)}%",
                f"Threats {player_cover.threat_count}",
                f"Via {cover_source}",
            ])
        economy_lines = _flow_display_chunks(economy_chunks, hud_text_w, max_lines=3)

        objective_eval = evaluate_visible_run_objective(self.sim, self.player_eid)
        objective_line = ""
        if objective_eval:
            objective_line = str(objective_eval.get("summary_line", "")).strip()
        final_operation_eval = evaluate_visible_final_operation(self.sim, self.player_eid)
        final_operation_line = ""
        if final_operation_eval:
            final_operation_line = str(final_operation_eval.get("summary_line", "")).strip()
        opportunity_rows = evaluate_opportunity_facts(
            self.sim,
            self.player_eid,
            limit=1,
            observer_eid=self.player_eid,
        )
        known_count = int(opportunity_known_count(self.sim, self.player_eid, observer_eid=self.player_eid))
        if opportunity_rows:
            nearest = opportunity_rows[0]
            nearest_dist_text = opportunity_distance_text(
                int(nearest.get("distance", 0)),
                str(nearest.get("direction", "HERE")).strip(),
            )
            opportunity_line = (
                f"Opp {known_count} known | nearest "
                f"{str(nearest.get('title', 'Opportunity')).strip()} "
                f"{nearest_dist_text}"
            )
        else:
            opportunity_line = "Opp 0 known"
        show_opportunity_line = bool(opportunity_line)

        report_hint_line = "O ops report, Y notebooks."

        if look_ui.get("active"):
            look_entry = look_ui.get("inspect_text", "")
            look_text = _line_text(look_entry).strip()
            if look_text:
                if look_purpose == "aim":
                    prefix = "Aim: "
                elif look_purpose == "interact":
                    prefix = "Interact: "
                elif look_purpose == "talk":
                    prefix = "Talk: "
                else:
                    prefix = "Look: "
                report_hint_line = _line_with_prefix(look_entry, prefix)
            else:
                if look_purpose == "aim":
                    report_hint_line = "Aim mode active."
                elif look_purpose == "interact":
                    report_hint_line = "Interact target mode active."
                elif look_purpose == "talk":
                    report_hint_line = "Talk target mode active."
                else:
                    report_hint_line = "Look mode active."
            quest_lines = _wrap_display_lines(report_hint_line, hud_text_w, max_lines=2)
        else:
            quest_lines = []
            if objective_line:
                quest_lines.extend(_wrap_display_lines(objective_line, hud_text_w, max_lines=1))
            if final_operation_line and len(quest_lines) < 2:
                quest_lines.extend(
                    _wrap_display_lines(
                        final_operation_line,
                        hud_text_w,
                        max_lines=1,
                    )
                )
            if show_opportunity_line and len(quest_lines) < 2:
                quest_lines.extend(
                    _wrap_display_lines(
                        opportunity_line,
                        hud_text_w,
                        max_lines=1,
                    )
                )
            if len(quest_lines) < 2:
                quest_lines.extend(
                    _wrap_display_lines(
                        report_hint_line,
                        hud_text_w,
                        max_lines=max(1, 2 - len(quest_lines)),
                    )
                )
            quest_lines = quest_lines[:2] or [report_hint_line]

        if look_ui.get("active"):
            if look_purpose == "aim":
                if _entity_uses_melee_aim(self.sim, self.player_eid):
                    controls = "Aim (Melee): reticle adjacent-only, F cycle target, Enter strike, x inspect, Esc close, ? help"
                else:
                    controls = "Aim: move cursor, F cycle target, Enter fire, x inspect, Esc close, ? help"
            elif look_purpose == "interact":
                controls = "Interact: choose adjacent tile, '/Enter confirm, ; lock, x inspect, Esc fallback, ? help"
            elif look_purpose == "talk":
                controls = "Talk: choose visible person, / or Enter confirm, x inspect, Esc close, ? help"
            elif look_purpose == "backup_order":
                controls = "Order Mark: move cursor, E/Enter mark, x inspect, Esc cancel, ? help"
            else:
                controls = "Look: move cursor, Enter/x inspect, Esc close, ? help"
        elif inventory_ui.get("open"):
            if inventory_panel_kind == "container":
                controls = (
                    f"{inventory_container_label}: browse, U transfer, Left/Right or Tab switch "
                    f"{inventory_container_label.lower()}/pack, E inspect, O ops, Y notebooks, "
                    f"L log, D debug, I/Esc close, ? help"
                )
            else:
                controls = "Inventory: browse, U use/equip/stow, R drop, E inspect, O ops, Y notebooks, L log, D debug, I/Esc close, ? help"
        elif trade_ui.get("open"):
            controls = "Trade: browse, B/S mode, E trade, X inspect, O ops, Y notebooks, L log, D debug, M/Esc close, ? help"
        elif casino_ui.get("open"):
            casino_mode = str(casino_ui.get("mode", "floor") or "floor").strip().lower()
            if casino_mode in {"floor", "services", "wager"}:
                controls = "Casino: Up/Down browse, Enter select, Tab switch page, O ops, Y notebooks, L log, D debug, Esc leave, ? help"
            elif bool(casino_ui.get("close_pending")) or casino_mode == "result":
                controls = "Casino result: Space return, O ops, Y notebooks, L log, D debug, Esc return, ? help"
            else:
                controls = "Casino live: arrows move focus, Space stage, Backspace pull chip, Enter resolve, O ops, Y notebooks, L log, D debug, Esc back, ? help"
        elif dialog_ui.get("open"):
            dialog_topic_ids = {
                str(row.get("id", "")).strip().lower()
                for row in list(dialog_ui.get("topics", ()) or ())
                if isinstance(row, dict)
            }
            if dialog_topic_ids & {"backup_orders", "backup_goto_wait", "backup_wait_return", "backup_kill"}:
                controls = "Dialog: Up/Down choose, E ask, X mark spot, PgUp/PgDn scroll, M trade, O ops, Y notebooks, L log, D debug, Esc close, ? help"
            else:
                controls = "Dialog: Up/Down choose, E ask, PgUp/PgDn scroll, M trade, O ops, Y notebooks, L log, D debug, Esc close, ? help"
        elif character_ui.get("open"):
            controls = "Sheet: Left/Right or Tab pages, 1-4 jump, Up/Down browse, PgUp/PgDn jump, +/Esc close, O ops, Y notebooks, L log, D debug, ? help"
        elif report_ui.get("open"):
            report_kind = str(report_ui.get("kind", "progress")).strip().lower() or "progress"
            if report_kind == "known_locations":
                controls = "Places Notebook: Up/Down choose, Enter inspect, G go, M mark, R hide/restore, H hidden view, Tab people notebook, O ops, Y close, L log, D debug, ? help"
            else:
                controls = "People Notebook: Up/Down browse, PgUp/PgDn jump, Tab places notebook, O ops, Y close, L log, D debug, Esc close, ? help"
        elif log_ui.get("open"):
            controls = "Log: Up/Down browse, PgUp/PgDn jump, T filter, H set HUD filter, O ops, Y notebooks, D debug, L/Esc close, ? help"
        elif debug_ui.get("open"):
            controls = "Debug: Up/Down browse, O ops, Y notebooks, L log, D/Esc close, ? help"
        elif overlay.get("active"):
            controls = f"Combat: move or act, {_aim_open_label(self.sim, self.player_eid)}, C cover, v hop, Shift+S sneak, ? help, Q quit"
        elif zoom_mode == "overworld":
            if bool(getattr(self.sim, "overworld_view_only_by_eid", {}).get(int(self.player_eid), False)):
                controls = "Map: move browse chunks, Enter/x inspect selected chunk, M/l/N markers, + sheet, t return on-foot, ? help"
            else:
                controls = "In-vehicle: move, G drive marker, M/l/N markers, O ops, Y notebooks, L log, + sheet, t exit on-foot, center icons UPPER=loaded lower=distant, ? help"
        else:
            controls = f"Move: arrows/WASD/HJKL/QEZC, {_aim_open_label(self.sim, self.player_eid)}, / talk, . service, ' interact, , pickup, ; lock door, X map, + sheet, Shift+J breach door, O ops, Y notebooks, L log, D debug, or ? for help"

        mode_line = _mode_line(
            mode_state=player_modes,
            cover=player_cover,
            look_active=bool(look_ui.get("active")) and look_purpose != "aim",
            aim_active=bool(look_ui.get("active")) and look_purpose == "aim",
            turn_mode=_combat_turn_pacing_active(self.sim),
            stealth_state=getattr(self.sim, "player_stealth_state", None),
            intrusion_state=getattr(self.sim, "player_intrusion_state", None),
        )
        wrapped_sections_spec = [
            {
                "id": "status",
                "lines": status_lines,
                "min_lines": 1,
                "trim_priority": 1,
            },
            {
                "id": "streamed",
                "lines": streamed_lines,
                "min_lines": 1,
                "trim_priority": 4,
            },
            {
                "id": "economy",
                "lines": economy_lines,
                "min_lines": 1,
                "trim_priority": 2,
            },
            {
                "id": "mode",
                "lines": _wrap_display_lines(mode_line, hud_text_w, max_lines=2),
                "min_lines": 1,
                "trim_priority": 0,
            },
            {
                "id": "quest",
                "lines": quest_lines,
                "min_lines": 1,
                "trim_priority": 5,
            },
            {
                "id": "controls",
                "lines": _wrap_display_lines(controls, hud_text_w, max_lines=2),
                "min_lines": 1,
                "trim_priority": 3,
            },
        ]
        desired_log_rows = 3 if hud_lines >= 9 else (2 if hud_lines >= 6 else 1)
        min_section_rows = sum(
            1
            for section in wrapped_sections_spec
            if list(section.get("lines", ()) or ())
        )
        reserved_log_rows = max(
            1,
            min(
                desired_log_rows,
                max(0, int(hud_lines) - min_section_rows),
            ),
        )
        wrapped_sections = _fit_wrapped_sections(
            wrapped_sections_spec,
            max(1, hud_lines - reserved_log_rows),
        )
        self._update_hud_flash_state(wrapped_sections)

        hud_y = map_h
        for section in wrapped_sections:
            section_id = str(section.get("id", "section"))
            for line_index, line in enumerate(section["lines"]):
                if hud_y >= screen_h:
                    break
                self._draw_display_line(
                    0,
                    hud_y,
                    self._hud_flash_line(section_id, line_index, line),
                    hud_w,
                )
                hud_y += 1
            if hud_y >= screen_h:
                break

        if inventory_ui.get("open"):
            panel_w = min(max(36, screen_w - 4), screen_w)
            panel_x = max(0, (screen_w - panel_w) // 2)
            panel_y = 0
            panel_h = max(8, min(map_h, map_h - 1))

            def _clip(text, width):
                if width <= 0:
                    return ""
                if len(text) <= width:
                    return text
                if width <= 3:
                    return text[:width]
                return text[: width - 3] + "..."

            # Border
            if panel_w >= 2 and panel_h >= 2:
                top = "+" + ("-" * (panel_w - 2)) + "+"
                mid = "|" + (" " * (panel_w - 2)) + "|"
                bot = "+" + ("-" * (panel_w - 2)) + "+"

                self.view.draw_text(panel_x, panel_y, top)
                for row in range(1, panel_h - 1):
                    self.view.draw_text(panel_x, panel_y + row, mid)
                self.view.draw_text(panel_x, panel_y + panel_h - 1, bot)

            panel_kind = inventory_panel_kind
            panel_title = str(inventory_ui.get("title", "Inventory")).strip() or "Inventory"
            container_view = inventory_container_view
            container_kind = inventory_container_kind
            container_label = inventory_container_label
            container_instance_id = inventory_container_instance_id
            container_capacity = inventory_container_capacity
            note_text = str(inventory_ui.get("note_text", "")).strip()
            inv = inventories.get(self.player_eid)
            if panel_kind == "container" and container_view == "container":
                property_id = str(inventory_ui.get("property_id", "") or "").strip()
                if container_kind == "worn":
                    entries = _inventory_entries_stowed_in_container(inv, container_instance_id) if inv and container_instance_id else []
                else:
                    entries = (
                        _property_runtime_container_entry_snapshot(
                            self.sim,
                            property_id,
                            container_kind=container_kind,
                        )
                        if property_id
                        else []
                    )
            elif panel_kind == "container" and container_kind == "worn":
                entries = _inventory_entries_loose_for_container(inv, container_instance_id) if inv and container_instance_id else (list(inv.items) if inv else [])
            else:
                entries = list(inv.items) if inv else []
            if entries:
                selected_index = int(inventory_ui.get("selected_index", 0))
                selected_index = max(0, min(selected_index, len(entries) - 1))
                inventory_ui["selected_index"] = selected_index
            else:
                inventory_ui["selected_index"] = 0
                selected_index = 0

            header = f" {panel_title} "
            self.view.draw_text(panel_x + 2, panel_y, _clip(header, panel_w - 4))

            if panel_kind == "container":
                container_count = 0
                property_id = str(inventory_ui.get("property_id", "") or "").strip()
                if container_kind == "worn":
                    if inv and container_instance_id:
                        container_count = len(_inventory_entries_stowed_in_container(inv, container_instance_id))
                    if container_capacity > 0:
                        container_count_text = f"{container_label} {container_count}/{container_capacity}"
                    else:
                        container_count_text = f"{container_label} {container_count}"
                elif container_kind == "cache":
                    if property_id:
                        container_count = _property_runtime_container_entry_count(
                            self.sim,
                            property_id,
                            container_kind="cache",
                        )
                    container_count_text = f"{container_label} {container_count}/{PlayerActionSystem.CACHE_MAX_STACKS}"
                else:
                    if property_id:
                        container_count = _property_runtime_container_entry_count(
                            self.sim,
                            property_id,
                            container_kind=container_kind,
                        )
                    container_count_text = f"{container_label} {container_count}"
                if container_kind == "worn":
                    pack_entries = (
                        _inventory_entries_loose_for_container(inv, container_instance_id)
                        if inv and container_instance_id
                        else (list(inv.items) if inv else [])
                    )
                else:
                    pack_entries = list(inv.items) if inv else []
                pack_count = inv.slot_count(entries=pack_entries) if inv else 0
                pack_cap = inv.capacity if inv else 0
                slot_line = (
                    f"View {container_label.upper() if container_view == 'container' else 'PACK'}"
                    f" | {container_count_text}"
                    f" | Pack {pack_count}/{pack_cap}"
                )
                if note_text:
                    slot_line += f" | {note_text}"
            else:
                cap = inv.capacity if inv else 0
                slot_line = f"Slots {inv.slot_count(entries=entries) if inv else 0}/{cap}"
            self.view.draw_text(panel_x + 2, panel_y + 1, _clip(slot_line, panel_w - 4))

            list_y = panel_y + 2
            list_h = max(1, panel_h - 6)

            start = 0
            if selected_index >= list_h:
                start = selected_index - list_h + 1

            visible_entries = entries[start: start + list_h]
            armor_loadout = self.sim.ecs.get(ArmorLoadout).get(self.player_eid)
            weapon_loadout = self.sim.ecs.get(WeaponLoadout).get(self.player_eid)
            active_disguise = getattr(self.sim, "disguise_state", None)
            equipped_container = getattr(self.sim, "equipped_container", None)
            for idx, entry in enumerate(visible_entries):
                absolute = start + idx
                marker = ">" if absolute == selected_index else " "
                item_def = ITEM_CATALOG.get(entry["item_id"], {})
                glyph = item_def.get("glyph", "*")
                name = item_display_name_for_actor(self.sim, self.player_eid, entry, item_catalog=ITEM_CATALOG)
                gear_marker = ""
                if panel_kind != "container" or container_view == "pack":
                    if armor_loadout and armor_loadout.is_equipped(entry.get("instance_id")):
                        gear_marker = "A"
                    elif (
                        isinstance(active_disguise, dict)
                        and str(active_disguise.get("instance_id", "")).strip() == str(entry.get("instance_id", "")).strip()
                    ):
                        gear_marker = "D"
                    elif weapon_loadout:
                        weapon_id = _item_weapon_id(item_def)
                        instance = weapon_loadout.weapon_instances.get(weapon_id, {}) if weapon_id else {}
                        if (
                            weapon_id
                            and weapon_loadout.current_weapon() == weapon_id
                            and isinstance(instance, dict)
                            and str(instance.get("inventory_instance_id", "")).strip() == str(entry.get("instance_id", "")).strip()
                        ):
                            gear_marker = "W"
                    elif (
                        isinstance(equipped_container, dict)
                        and str(equipped_container.get("instance_id", "")).strip() == str(entry.get("instance_id", "")).strip()
                    ):
                        gear_marker = "C"
                ammo_suffix = ""
                weapon_id = _item_weapon_id(item_def)
                if weapon_id and (panel_kind != "container" or container_view == "pack"):
                    weapon = weapon_by_id(weapon_id)
                    ammo_type = _weapon_ammo_type_label(weapon)
                    if _weapon_uses_ammo(weapon):
                        reserve = _weapon_reserve_ammo(
                            weapon_loadout,
                            weapon_id,
                            instance_id=entry.get("instance_id"),
                        )
                        if reserve is not None:
                            ammo_suffix = f" [{ammo_type}:{reserve}]"
                        else:
                            ammo_suffix = f" [{ammo_type}]"
                    else:
                        ammo_suffix = " [melee]"
                storage_suffix = ""
                if panel_kind != "container":
                    stowed_container_instance = _entry_stowed_container_instance(entry)
                    if stowed_container_instance:
                        storage_suffix = " [stowed]"
                worn_suffix = ""
                if (panel_kind != "container" or container_view == "pack") and is_entry_worn(entry):
                    worn_suffix = " [worn]"
                label = f"{marker}{absolute + 1:02d}{gear_marker:>1} {glyph} {name} x{entry['quantity']}{ammo_suffix}{worn_suffix}{storage_suffix}"
                self.view.draw_text(panel_x + 1, list_y + idx, _clip(label, panel_w - 2))

            if not entries:
                empty_label = "(empty)"
                if panel_kind == "container":
                    empty_label = f"({container_label.lower()} empty)" if container_view == "container" else "(pack empty)"
                self.view.draw_text(panel_x + 2, list_y, _clip(empty_label, panel_w - 4))

            inspect_text = inventory_ui.get("inspect_text", "")
            if panel_kind == "container" and note_text and not inspect_text:
                inspect_text = note_text
            if entries:
                selected = entries[selected_index]
                item_def = ITEM_CATALOG.get(selected["item_id"], {})
                identified = item_is_identified_for_actor(self.sim, self.player_eid, selected, item_catalog=ITEM_CATALOG)
                legal = item_def.get("legal_status", "legal") if identified else "unknown"
                tags = ",".join(item_def.get("tags", [])[:3]) or "none"
                inspect_name = item_display_name_for_actor(
                    self.sim,
                    self.player_eid,
                    selected,
                    item_catalog=ITEM_CATALOG,
                )
                if not inspect_text:
                    if identified:
                        inspect_text = _item_legend_line(
                            selected["item_id"],
                            f"{inspect_name} [{legal}] {tags}",
                        )
                    else:
                        appraise_item_for_actor(self.sim, self.player_eid, selected, item_catalog=ITEM_CATALOG)
                        inspect_text = _item_legend_line(
                            selected["item_id"],
                            item_unknown_inspect_text_for_actor(
                                self.sim,
                                self.player_eid,
                                selected,
                                item_catalog=ITEM_CATALOG,
                            ),
                        )
            elif note_text:
                inspect_text = inspect_text or note_text

            self._draw_display_line(
                panel_x + 2,
                panel_y + panel_h - 3,
                _clip_display_line(inspect_text, panel_w - 4),
                panel_w - 4,
            )
            if panel_kind == "container":
                hint = (
                    f"U transfer  Left/Right or Tab switch {container_label.lower()}/pack  "
                    f"E inspect  O ops  Y notebooks  L log  D debug  I close"
                )
            else:
                hint = "U use/equip/stow  R drop  E inspect  O ops  Y notebooks  L log  D debug  I close"
            self.view.draw_text(panel_x + 2, panel_y + panel_h - 2, _clip(hint, panel_w - 4))
        elif trade_ui.get("open"):
            panel_w = min(max(52, screen_w - 4), screen_w)
            panel_x = max(0, (screen_w - panel_w) // 2)
            panel_y = 0
            panel_h = max(8, min(map_h, map_h - 1))

            def _clip(text, width):
                if width <= 0:
                    return ""
                if len(text) <= width:
                    return text
                if width <= 3:
                    return text[:width]
                return text[: width - 3] + "..."

            if panel_w >= 2 and panel_h >= 2:
                top = "+" + ("-" * (panel_w - 2)) + "+"
                mid = "|" + (" " * (panel_w - 2)) + "|"
                bot = "+" + ("-" * (panel_w - 2)) + "+"

                self.view.draw_text(panel_x, panel_y, top)
                for row in range(1, panel_h - 1):
                    self.view.draw_text(panel_x, panel_y + row, mid)
                self.view.draw_text(panel_x, panel_y + panel_h - 1, bot)

            rows = list(trade_ui.get("rows", []))
            if rows:
                selected_index = int(trade_ui.get("selected_index", 0))
                selected_index = max(0, min(selected_index, len(rows) - 1))
                trade_ui["selected_index"] = selected_index
            else:
                trade_ui["selected_index"] = 0
                selected_index = 0

            mode = str(trade_ui.get("mode", "buy")).lower()
            mode_label = "BUY" if mode == "buy" else "SELL"
            store_name = str(trade_ui.get("store_name", "")).strip() or "Store"
            service_note = str(trade_ui.get("service_note", "")).strip()
            supply_note = str(trade_ui.get("supply_note", "")).strip()
            contact_note = str(trade_ui.get("contact_note", "")).strip()
            panel_bits = [bit for bit in (service_note, supply_note, contact_note) if bit]
            store_line = store_name if not panel_bits else f"{store_name} [{' | '.join(panel_bits)}]"

            header = f" Trade {mode_label} "
            self.view.draw_text(panel_x + 2, panel_y, _clip(header, panel_w - 4))
            self.view.draw_text(panel_x + 2, panel_y + 1, _clip(store_line, panel_w - 4))

            list_y = panel_y + 2
            list_h = max(1, panel_h - 6)
            start = 0
            if selected_index >= list_h:
                start = selected_index - list_h + 1

            visible_rows = rows[start: start + list_h]
            for idx, row in enumerate(visible_rows):
                absolute = start + idx
                marker = ">" if absolute == selected_index else " "
                glyph = str(row.get("glyph", "*"))[:1] or "*"
                item_name = str(row.get("item_name", row.get("item_id", "item")))
                price = int(row.get("price", 0))
                action_label = str(row.get("action_label", "")).strip().lower()
                if mode == "buy":
                    stock = int(row.get("stock", 0))
                    if action_label:
                        label = f"{marker}{absolute + 1:02d} {glyph} {item_name} {action_label} stk {stock}"
                    else:
                        label = f"{marker}{absolute + 1:02d} {glyph} {item_name} {price}c stk {stock}"
                else:
                    qty = int(row.get("quantity", 0))
                    if action_label:
                        if action_label == "trade-in":
                            label = f"{marker}{absolute + 1:02d} {glyph} {item_name} trade-in {price}c x{qty}"
                        else:
                            label = f"{marker}{absolute + 1:02d} {glyph} {item_name} {action_label} x{qty}"
                    else:
                        listed = "L" if row.get("listed") else "U"
                        label = f"{marker}{absolute + 1:02d} {glyph} {item_name} {price}c x{qty} {listed}"
                self.view.draw_text(panel_x + 1, list_y + idx, _clip(label, panel_w - 2))

            if not rows:
                self.view.draw_text(panel_x + 2, list_y, _clip("(no offers)", panel_w - 4))

            inspect_text = trade_ui.get("inspect_text", "")
            if rows and not inspect_text:
                selected = rows[selected_index]
                action_label = str(selected.get("action_label", "")).strip().lower()
                if mode == "buy":
                    if action_label:
                        inspect_text = _item_legend_line(
                            selected.get("item_id"),
                            (
                                f"{selected.get('item_name', selected.get('item_id', 'item'))} "
                                f"{action_label} from shelf stock {int(selected.get('stock', 0))}"
                            ),
                        )
                    else:
                        inspect_text = _item_legend_line(
                            selected.get("item_id"),
                            (
                                f"{selected.get('item_name', selected.get('item_id', 'item'))} "
                                f"price {int(selected.get('price', 0))} credits "
                                f"stock {int(selected.get('stock', 0))}"
                            ),
                        )
                else:
                    if action_label:
                        if action_label == "trade-in":
                            inspect_text = _item_legend_line(
                                selected.get("item_id"),
                                (
                                    f"{selected.get('item_name', selected.get('item_id', 'item'))} "
                                    f"trade-in quote {int(selected.get('price', 0))} credits "
                                    f"qty {int(selected.get('quantity', 0))}"
                                ),
                            )
                        else:
                            inspect_text = _item_legend_line(
                                selected.get("item_id"),
                                (
                                    f"{selected.get('item_name', selected.get('item_id', 'item'))} "
                                    f"{action_label} into shelf stock qty {int(selected.get('quantity', 0))}"
                                ),
                            )
                    else:
                        listed_text = "listed" if selected.get("listed") else "unlisted"
                        inspect_text = _item_legend_line(
                            selected.get("item_id"),
                            (
                                f"{selected.get('item_name', selected.get('item_id', 'item'))} "
                                f"offer {int(selected.get('price', 0))} credits ({listed_text}) "
                                f"qty {int(selected.get('quantity', 0))}"
                            ),
                        )

            self._draw_display_line(
                panel_x + 2,
                panel_y + panel_h - 3,
                _clip_display_line(inspect_text, panel_w - 4),
                panel_w - 4,
            )
            hint = "E trade  B buy  S sell  X inspect  O ops  Y notebooks  L log  D debug  M/Esc close"
            self.view.draw_text(panel_x + 2, panel_y + panel_h - 2, _clip(hint, panel_w - 4))
        elif casino_ui.get("open"):
            panel_w = min(max(78, map_w - 4), map_w)
            panel_w = max(42, panel_w)
            panel_h = min(max(16, map_h - 1), map_h)
            panel_h = max(12, panel_h)
            panel_x = max(0, (map_w - panel_w) // 2)
            panel_y = max(0, (map_h - panel_h) // 2)

            if panel_w >= 2 and panel_h >= 2:
                top = "+" + ("=" * (panel_w - 2)) + "+"
                mid = "|" + (" " * (panel_w - 2)) + "|"
                bot = "+" + ("=" * (panel_w - 2)) + "+"
                self.view.draw_text(panel_x, panel_y, top)
                for row in range(1, panel_h - 1):
                    self.view.draw_text(panel_x, panel_y + row, mid)
                self.view.draw_text(panel_x, panel_y + panel_h - 1, bot)

            title = str(casino_ui.get("title", "Casino")).strip() or "Casino"
            title_line = {
                "text": f" {title} ",
                "segments": [{"text": f" {title} ", "color": "casino_gold"}],
            }
            self._draw_display_line(panel_x + 2, panel_y + 1, _clip_display_line(title_line, panel_w - 4), panel_w - 4)

            subtitle = str(casino_ui.get("subtitle", "")).strip()
            rail_w = max(16, min(24, panel_w // 4))
            rows = list(casino_ui.get("rows", ()) or [])
            rows_h = max(1, min(6, len(rows) if rows else 1))
            footer_y = panel_y + panel_h - 2
            body_top = panel_y + 2
            if subtitle:
                self._draw_display_line(panel_x + 2, body_top, _clip_display_line(subtitle, panel_w - 4), panel_w - 4)
                body_top += 1
            divider_y = max(body_top + 1, footer_y - rows_h - 1)
            body_h = max(1, divider_y - body_top)
            body_x = panel_x + 2
            rail_x = panel_x + panel_w - rail_w - 2
            body_w = max(12, rail_x - body_x - 2)
            rail_h = max(1, divider_y - body_top)

            wrapped_body = []
            for raw in list(casino_ui.get("body_lines", ()) or ()) or ["The floor is quiet."]:
                wrapped = _wrap_display_lines(raw, body_w) if _line_text(raw).strip() else [""]
                wrapped_body.extend(wrapped)
            for idx, line in enumerate(wrapped_body[:body_h]):
                self._draw_display_line(body_x, body_top + idx, _clip_display_line(line, body_w), body_w)

            self.view.draw_text(rail_x - 1, body_top, "|")
            for offset in range(1, rail_h):
                self.view.draw_text(rail_x - 1, body_top + offset, "|")

            wrapped_rail = []
            for raw in list(casino_ui.get("rail_lines", ()) or ()):
                wrapped = _wrap_display_lines(raw, rail_w) if _line_text(raw).strip() else [""]
                wrapped_rail.extend(wrapped)
            for idx, line in enumerate(wrapped_rail[:rail_h]):
                self._draw_display_line(rail_x, body_top + idx, _clip_display_line(line, rail_w), rail_w)

            self.view.draw_text(panel_x + 2, divider_y, "-" * max(1, panel_w - 4))

            selected_index = int(casino_ui.get("selected_index", 0) or 0)
            options_y = divider_y + 1
            visible_row_h = max(1, footer_y - options_y)
            row_start = 0
            if selected_index >= visible_row_h:
                row_start = selected_index - visible_row_h + 1
            visible_rows = rows[row_start: row_start + visible_row_h]
            for idx, row in enumerate(visible_rows):
                if not isinstance(row, dict):
                    continue
                label = str(row.get("label", row.get("id", "option"))).strip() or "option"
                absolute = row_start + idx
                if not bool(row.get("selectable", True)):
                    line = {
                        "text": f"  {label}",
                        "segments": [{"text": f"  {label}", "color": "casino_gold"}],
                    }
                else:
                    prefix = ">" if absolute == selected_index else " "
                    color = "casino_cursor" if absolute == selected_index else "default"
                    line = {
                        "text": f"{prefix} {label}",
                        "segments": [{"text": f"{prefix} {label}", "color": color}],
                    }
                self._draw_display_line(panel_x + 2, options_y + idx, _clip_display_line(line, panel_w - 4), panel_w - 4)

            if not rows:
                empty_text = "(press Space to return)" if bool(casino_ui.get("close_pending")) else "(live controls on the board)"
                self.view.draw_text(panel_x + 2, options_y, empty_text[: max(1, panel_w - 4)])

            hint = str(casino_ui.get("hint", "")).strip()
            footer = hint or "Casino floor"
            self.view.draw_text(panel_x + 2, footer_y, footer[: max(1, panel_w - 4)])
        elif dialog_ui.get("open"):
            panel_w = min(max(62, screen_w - 4), screen_w)
            panel_w = max(30, panel_w)
            panel_h = min(max(15, map_h - 1), map_h)
            panel_h = max(10, panel_h)
            panel_x = max(0, (screen_w - panel_w) // 2)
            panel_y = max(0, (map_h - panel_h) // 2)

            def _clip(text, width):
                if width <= 0:
                    return ""
                if len(text) <= width:
                    return text
                if width <= 3:
                    return text[:width]
                return text[: width - 3] + "..."

            if panel_w >= 2 and panel_h >= 2:
                top = "+" + ("-" * (panel_w - 2)) + "+"
                mid = "|" + (" " * (panel_w - 2)) + "|"
                bot = "+" + ("-" * (panel_w - 2)) + "+"

                self.view.draw_text(panel_x, panel_y, top)
                for row in range(1, panel_h - 1):
                    self.view.draw_text(panel_x, panel_y + row, mid)
                self.view.draw_text(panel_x, panel_y + panel_h - 1, bot)

            title = str(dialog_ui.get("title", "Conversation")).strip() or "Conversation"
            subtitle = str(dialog_ui.get("subtitle", "")).strip()
            self.view.draw_text(panel_x + 2, panel_y + 1, _clip(f" {title} ", panel_w - 4))

            body_w = max(8, _view_text_wrap_width(self.view, panel_w - 4))
            inner_top = panel_y + 2
            if subtitle:
                self.view.draw_text(panel_x + 2, inner_top, _clip(subtitle, body_w))
                inner_top += 1

            footer_y = panel_y + panel_h - 2
            raw_topics = list(dialog_ui.get("topics", ()) or [])
            close_pending = bool(dialog_ui.get("close_pending"))
            topics_h = max(1, min(6, len(raw_topics) if raw_topics else 1))
            divider_y = max(inner_top + 1, footer_y - topics_h - 1)
            transcript_h = max(1, divider_y - inner_top)

            display_lines = []
            for raw in list(dialog_ui.get("transcript", ()) or ()) or ["No conversation yet."]:
                wrapped = _wrap_display_lines(raw, body_w) if _line_text(raw).strip() else [""]
                display_lines.extend(wrapped)
            display_lines = display_lines or ["No conversation yet."]
            max_scroll = max(0, len(display_lines) - transcript_h)
            scroll = max(0, min(int(dialog_ui.get("scroll", 0)), max_scroll))
            dialog_ui["scroll"] = scroll
            visible_lines = display_lines[scroll: scroll + transcript_h]

            for idx, line in enumerate(visible_lines[:transcript_h]):
                self._draw_display_line(
                    panel_x + 2,
                    inner_top + idx,
                    _clip_display_line(line, body_w),
                    body_w,
                )

            self.view.draw_text(panel_x + 2, divider_y, _clip("-" * body_w, body_w))

            if raw_topics:
                selected_index = int(dialog_ui.get("selected_index", 0))
                selected_index = max(0, min(selected_index, len(raw_topics) - 1))
                dialog_ui["selected_index"] = selected_index
            else:
                dialog_ui["selected_index"] = 0
                selected_index = 0

            options_y = divider_y + 1
            visible_topic_h = max(1, footer_y - options_y)
            topic_start = 0
            if selected_index >= visible_topic_h:
                topic_start = selected_index - visible_topic_h + 1
            visible_topics = raw_topics[topic_start: topic_start + visible_topic_h]
            new_topic_ids = {
                str(topic_id).strip().lower()
                for topic_id in list(dialog_ui.get("new_topic_ids", ()) or ())
                if str(topic_id).strip()
            }

            for idx, row in enumerate(visible_topics):
                absolute = topic_start + idx
                marker = ">" if absolute == selected_index else " "
                topic_id = str(row.get("id", "")).strip().lower()
                new_flag = "+" if topic_id in new_topic_ids else " "
                label = str(row.get("label", row.get("id", "topic"))).strip() or "topic"
                row_attrs = getattr(curses, "A_BOLD", 0) if absolute == selected_index else 0
                line = _rich_line(
                    (
                        _segment(marker, color="player", attrs=row_attrs),
                        _segment(new_flag, color="objective" if topic_id in new_topic_ids else "player", attrs=row_attrs),
                        _segment(f"{absolute + 1:02d} {label}", color="player", attrs=row_attrs),
                    ),
                    text=f"{marker}{new_flag}{absolute + 1:02d} {label}",
                )
                self._draw_display_line(
                    panel_x + 2,
                    options_y + idx,
                    _clip_display_line(line, body_w),
                    body_w,
                )

            if not raw_topics:
                empty_text = "(press Space to close)" if close_pending else "(no topics)"
                self.view.draw_text(panel_x + 2, options_y, _clip(empty_text, body_w), color="player")

            footer_bits = []
            if scroll > 0:
                footer_bits.append("more above")
            if scroll + transcript_h < len(display_lines):
                footer_bits.append("more below")
            hint = str(dialog_ui.get("hint", "")).strip()
            if hint:
                footer_bits.append(hint)
            dialog_kind = str(dialog_ui.get("kind", "conversation") or "conversation").strip().lower()
            dialog_topic_ids = {
                str(row.get("id", "")).strip().lower()
                for row in raw_topics
                if isinstance(row, dict)
            }
            footer = " | ".join(footer_bits) if footer_bits else ""
            if close_pending:
                action_tail = "Space close | Esc close | O ops | Y notebooks | L log | D debug | ? help"
            elif dialog_kind == "justice_surrender":
                action_tail = "E choose | Esc resist | ? help"
            elif dialog_kind == "justice_questioning":
                action_tail = "E choose | Esc refuse | ? help"
            elif dialog_kind == "service_menu":
                action_tail = "E select | Esc close | O ops | Y notebooks | ? help"
            else:
                if dialog_topic_ids & {"backup_orders", "backup_goto_wait", "backup_wait_return", "backup_kill"}:
                    action_tail = "E ask | X mark | Esc close | M trade | O ops | Y notebooks | ? help"
                else:
                    action_tail = "E ask | Esc close | M trade | O ops | Y notebooks | ? help"
            if footer:
                footer = f"{footer} | {action_tail}"
            else:
                if close_pending:
                    footer = action_tail
                elif dialog_kind == "justice_surrender":
                    footer = action_tail
                elif dialog_kind == "justice_questioning":
                    footer = "E choose | Esc refuse | ? help"
                elif dialog_kind == "service_menu":
                    footer = f"{action_tail} | L log | D debug"
                else:
                    if dialog_topic_ids & {"backup_orders", "backup_goto_wait", "backup_wait_return", "backup_kill"}:
                        footer = "E ask | X mark | Esc close | M trade | O ops | Y notebooks | L log | D debug | ? help"
                    else:
                        footer = "E ask | Esc close | M trade | O ops | Y notebooks | L log | D debug | ? help"
            self.view.draw_text(panel_x + 2, footer_y, _clip(footer, body_w))
        elif character_ui.get("open"):
            panel_w = min(max(60, screen_w - 4), screen_w)
            panel_w = max(32, panel_w)
            panel_h = min(max(14, map_h - 1), map_h)
            panel_h = max(10, panel_h)
            panel_x = max(0, (screen_w - panel_w) // 2)
            panel_y = max(0, (map_h - panel_h) // 2)

            def _clip(text, width):
                if width <= 0:
                    return ""
                if len(text) <= width:
                    return text
                if width <= 3:
                    return text[:width]
                return text[: width - 3] + "..."

            if panel_w >= 2 and panel_h >= 2:
                top = "+" + ("-" * (panel_w - 2)) + "+"
                mid = "|" + (" " * (panel_w - 2)) + "|"
                bot = "+" + ("-" * (panel_w - 2)) + "+"

                self.view.draw_text(panel_x, panel_y, top)
                for row in range(1, panel_h - 1):
                    self.view.draw_text(panel_x, panel_y + row, mid)
                self.view.draw_text(panel_x, panel_y + panel_h - 1, bot)

            pages = list(character_ui.get("pages", ()) or [])
            if pages:
                page_index = max(0, min(int(character_ui.get("page_index", 0)), len(pages) - 1))
                character_ui["page_index"] = page_index
                current_page = pages[page_index]
            else:
                page_index = 0
                current_page = {"label": "Summary"}
            page_label = str(character_ui.get("page_label", current_page.get("label", "Summary"))).strip() or "Summary"
            title = str(character_ui.get("title", "Character Sheet")).strip() or "Character Sheet"
            title_text = f" {title} | {page_label} {page_index + 1}/{max(1, len(pages) or 1)} "
            self.view.draw_text(panel_x + 2, panel_y + 1, _clip(title_text, panel_w - 4))

            nav_bits = []
            for idx, page in enumerate(pages[:9]):
                label = str(page.get("label", f"Page {idx + 1}")).strip() or f"Page {idx + 1}"
                bit = f"{idx + 1} {label}"
                if idx == page_index:
                    bit = f"[{bit}]"
                nav_bits.append(bit)
            nav_line = " | ".join(nav_bits) if nav_bits else "[1 Summary]"
            self.view.draw_text(panel_x + 2, panel_y + 2, _clip(nav_line, panel_w - 4))

            body_w = max(8, _view_text_wrap_width(self.view, panel_w - 4))
            body_h = max(1, panel_h - 6)
            display_lines = []
            for raw in list(character_ui.get("lines", ()) or ()) or ["No character data."]:
                wrapped = _wrap_text_lines(raw, body_w) if str(raw).strip() else [""]
                display_lines.extend(wrapped)
            display_lines.extend(["", ""])
            display_lines = display_lines or ["No character data."]
            max_scroll = max(0, len(display_lines) - body_h)
            scroll = max(0, min(int(character_ui.get("scroll", 0)), max_scroll))
            character_ui["scroll"] = scroll
            visible_lines = display_lines[scroll: scroll + body_h]

            for idx, line in enumerate(visible_lines[:body_h]):
                self.view.draw_text(panel_x + 2, panel_y + 3 + idx, _clip(line, body_w))

            footer_bits = []
            if scroll > 0:
                footer_bits.append("more above")
            if scroll + body_h < len(display_lines):
                footer_bits.append("more below")
            footer = " | ".join(footer_bits) if footer_bits else ""
            action_tail = "Tab/Left/Right pages | 1-4 jump | + close | O ops | Y notebooks | L log | D debug | Up/Down scroll | ? help"
            if footer:
                footer = f"{footer} | {action_tail}"
            else:
                footer = action_tail
            self.view.draw_text(panel_x + 2, panel_y + panel_h - 2, _clip(footer, panel_w - 4))
        elif report_ui.get("open"):
            _report_debug_ui.draw_report_modal(
                self.view,
                report_ui,
                screen_w=screen_w,
                map_h=map_h,
                view_text_wrap_width_fn=_view_text_wrap_width,
                draw_display_line_fn=self._draw_display_line,
                clip_display_line_fn=_clip_display_line,
                wrap_display_lines_fn=_wrap_display_lines,
                line_text_fn=_line_text,
                known_location_list_line_fn=_known_location_list_line,
                known_location_detail_lines_fn=_known_location_detail_lines,
                known_person_list_line_fn=_known_person_list_line,
                known_person_detail_lines_fn=_known_person_detail_lines,
            )
        elif log_ui.get("open"):
            panel_w = min(max(56, screen_w - 4), screen_w)
            panel_w = max(28, panel_w)
            panel_h = min(max(12, map_h - 1), map_h)
            panel_h = max(8, panel_h)
            panel_x = max(0, (screen_w - panel_w) // 2)
            panel_y = max(0, (map_h - panel_h) // 2)

            def _clip(text, width):
                if width <= 0:
                    return ""
                if len(text) <= width:
                    return text
                if width <= 3:
                    return text[:width]
                return text[: width - 3] + "..."

            if panel_w >= 2 and panel_h >= 2:
                top = "+" + ("-" * (panel_w - 2)) + "+"
                mid = "|" + (" " * (panel_w - 2)) + "|"
                bot = "+" + ("-" * (panel_w - 2)) + "+"

                self.view.draw_text(panel_x, panel_y, top)
                for row in range(1, panel_h - 1):
                    self.view.draw_text(panel_x, panel_y + row, mid)
                self.view.draw_text(panel_x, panel_y + panel_h - 1, bot)
            title = str(log_ui.get("title", "Event Log")).strip() or "Event Log"
            filter_label = _log_filter_label(log_ui.get("view_filter", "all"))
            hud_filter_label = _log_filter_label(log_ui.get("hud_filter", "priority"))
            filtered_lines = _filtered_log_lines(list(log_ui.get("lines", ()) or ()), log_ui.get("view_filter", "all"))
            entry_count = len(filtered_lines)
            total_count = len(list(log_ui.get("lines", ()) or ()))
            pending_count = len(self._hud_queue)
            title_text = f" {title}: {filter_label} ({entry_count}/{total_count}) | HUD {hud_filter_label} | queue {pending_count} "
            self.view.draw_text(panel_x + 2, panel_y + 1, _clip(title_text, panel_w - 4))

            body_w = max(8, _view_text_wrap_width(self.view, panel_w - 4))
            body_h = max(1, panel_h - 4)
            display_lines = []
            for raw in filtered_lines or [f"No {filter_label.lower()} log entries yet."]:
                display_line = _log_display_line(raw)
                wrapped = _wrap_display_lines(display_line, body_w) if _line_text(display_line).strip() else [""]
                display_lines.extend(wrapped)
            display_lines = display_lines or [f"No {filter_label.lower()} log entries yet."]
            max_scroll = max(0, len(display_lines) - body_h)
            scroll = max(0, min(int(log_ui.get("scroll", 0)), max_scroll))
            log_ui["scroll"] = scroll
            visible_lines = display_lines[scroll: scroll + body_h]

            for idx, line in enumerate(visible_lines[:body_h]):
                self._draw_display_line(
                    panel_x + 2,
                    panel_y + 2 + idx,
                    _clip_display_line(line, body_w),
                    body_w,
                )

            footer_bits = []
            if scroll > 0:
                footer_bits.append("older above")
            if scroll + body_h < len(display_lines):
                footer_bits.append("newer below")
            footer = " | ".join(footer_bits) if footer_bits else ""
            if footer:
                footer = f"{footer} | T cycle filter | H set HUD filter | L close | O ops | Y notebooks | D debug | ? help"
            else:
                footer = "T cycle filter | H set HUD filter | L close | O ops | Y notebooks | D debug | Up/Down scroll | ? help"
            self.view.draw_text(panel_x + 2, panel_y + panel_h - 2, _clip(footer, panel_w - 4))
        elif debug_ui.get("open"):
            _report_debug_ui.draw_debug_modal(
                self.view,
                debug_ui,
                screen_w=screen_w,
                map_h=map_h,
                view_text_wrap_width_fn=_view_text_wrap_width,
                draw_display_line_fn=self._draw_display_line,
                clip_display_line_fn=_clip_display_line,
                wrap_display_lines_fn=_wrap_display_lines,
                line_text_fn=_line_text,
            )

        if help_ui.get("open"):
            panel_w = min(max(48, map_w - 2), map_w)
            panel_w = max(24, panel_w)
            panel_x = max(0, (map_w - panel_w) // 2)
            raw_lines = self._help_overlay_lines(zoom_mode, overlay_active=_combat_turn_pacing_active(self.sim))
            body_lines = []
            for line in raw_lines:
                body_lines.extend(_wrap_text_lines(line, max(8, panel_w - 4)))
            panel_h = min(max(8, len(body_lines) + 2), map_h)
            panel_y = max(0, (map_h - panel_h) // 2)

            if panel_w >= 2 and panel_h >= 2:
                top = "+" + ("-" * (panel_w - 2)) + "+"
                mid = "|" + (" " * (panel_w - 2)) + "|"
                bot = "+" + ("-" * (panel_w - 2)) + "+"

                self.view.draw_text(panel_x, panel_y, top)
                for row in range(1, panel_h - 1):
                    self.view.draw_text(panel_x, panel_y + row, mid)
                self.view.draw_text(panel_x, panel_y + panel_h - 1, bot)

            visible_lines = body_lines[: max(0, panel_h - 2)]
            for idx, line in enumerate(visible_lines):
                self.view.draw_text(panel_x + 2, panel_y + 1 + idx, line[: max(0, panel_w - 4)])

        visible_hud_rows = max(0, int(screen_h) - int(hud_y))
        log_budget = max(0, min(visible_hud_rows, int(hud_lines) - (int(hud_y) - int(map_h))))
        self._advance_hud_queue(log_budget)
        logs = self._visible_hud_log_display_lines(log_budget, hud_text_w)
        log_y = hud_y
        for line in logs:
            if log_y >= screen_h:
                break
            self._draw_display_line(0, log_y, line, hud_w)
            log_y += 1
