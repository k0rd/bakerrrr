"""Extracted systems from ``game.systems``: RenderSystem."""

import re
from dataclasses import replace
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
    CoverState,
    CreatureIdentity,
    DoorWaitState,
    EcologyProfile,
    FinancialProfile,
    HumanWildlifePresence,
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
    WireState,
    WeaponLoadout,
    WeaponUseProfile,
)
from game.system_support.sleep_pressure_runtime import chemical_wake_reserve_hours, ensure_sleep_needs
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
from game.inventory_display import (
    inventory_panel_entries_sortable,
    inventory_sort_label,
    normalize_inventory_sort_mode,
    sort_inventory_entries,
)
from game.hunting_runtime import hunting_carcasses_at
from game.flora_runtime import flora_records_in_rect, flora_render_data
from game.vision_scene_runtime import dream_residue_state, vision_scene_render_state
from game.ui_theme_runtime import draw_modal_frame, resolve_modal_theme, theme_token
from game.wire_visuals import wire_scene_theme, wire_visual_for_cell, wire_visual_for_kind
from ui.text_attrs import A_BOLD, A_DIM, A_REVERSE, A_UNDERLINE
from game.item_semantics import (
    appraise_item_for_actor,
    item_display_name_for_actor,
    item_entry_is_critical_quest_item,
    item_is_identified_for_actor,
    item_unknown_inspect_text_for_actor,
)
from game.item_compatibility import compatibility_row_fields, drone_compatibility_target
from game.lighting import (
    LIGHT_COLOR_PROFILES,
    ambient_snapshot as _lighting_ambient_snapshot,
    lighting_state as _lighting_state,
    prepare_ambient_sampling as _prepare_ambient_sampling,
    update_lighting_state as _update_lighting_state,
)
import game.report_debug_ui as _report_debug_ui
from game.release_runtime import debug_mode_enabled, release_control_text
from game.opportunities import (
    SPECIALTY_OPPORTUNITY_THEMES,
    append_external_opportunity,
    bounty_restraint_jab_status,
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
from game.player_interactions import CAMPFIRE_HERB_CACHE_KIND, entry_allowed_in_container
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
    _player_overworld_chunk,
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
)
from game.system_support.pause_runtime import manual_pause_active, manual_pause_state
from game.system_support.altered_state_runtime import hallucinated_tile_visual, hallucination_intensity
from game.system_support.combat_targeting_runtime import (
    _entity_uses_melee_aim,
    _entity_visible_to_player,
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
    _overworld_travel_tax_text,
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
from game.vehicle_motion import (
    ensure_vehicle_motion_state,
    vehicle_heading_glyph,
    vehicle_heading_label,
    vehicle_heading_tuple,
    vehicle_property_heading,
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
        attrs = A_BOLD
        layer = "ground_overlay"
        priority = 80
    else:
        glyphs = _SMOKE_VISUAL_GLYPHS
        color = "hazard_smoke"
        semantic_id = "hazard_smoke"
        effects = ()
        attrs = A_DIM
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
    _modal_body_widths,
    _modal_panel_width,
    _mode_line,
    _rich_line,
    _segment,
    _tick_duration_label,
    _view_text_wrap_width,
    _wrap_display_lines,
    _wrap_text_lines,
)


def _hud_line_is_read(line):
    text = _line_text(line).strip().lower()
    return text.startswith("read:") or text.startswith("read ")


def _hud_weapon_role(weapon):
    tags = {str(tag).strip().lower() for tag in (weapon or {}).get("tags", ()) if str(tag).strip()}
    if "melee" in tags:
        return "Melee"
    if "launcher" in tags or "explosive" in tags:
        return "Launcher"
    if "shotgun" in tags:
        return "Shotgun"
    if "smg" in tags:
        return "SMG"
    if "rifle" in tags or "carbine" in tags or "precision" in tags:
        return "Rifle"
    if "handgun" in tags or "pistol" in tags or "revolver" in tags:
        return "Pistol"
    return "Ranged"


def _hud_weapon_damage(weapon, instance):
    try:
        base_damage = float((weapon or {}).get("base_damage", 1))
    except (TypeError, ValueError):
        base_damage = 1.0
    try:
        damage_mult = float((instance or {}).get("damage_mult", 1.0))
    except (TypeError, ValueError):
        damage_mult = 1.0
    return int(max(1, round(base_damage * damage_mult)))


def _hud_weapon_summary(loadout):
    if not loadout or not loadout.current_weapon():
        return "Weapon none"
    weapon_id = loadout.current_weapon()
    weapon = weapon_by_id(weapon_id)
    instance = loadout.weapon_instance(weapon_id)
    role = _hud_weapon_role(weapon)
    damage = _hud_weapon_damage(weapon, instance)
    if _weapon_uses_ammo(weapon):
        reserve = _weapon_reserve_ammo(loadout, weapon_id)
        if reserve is None:
            reserve = int(loadout.reserve_ammo_value(
                weapon_id,
                default=_default_weapon_reserve_ammo(weapon),
            ))
        return f"{role} A{int(reserve)} D{damage}"
    return f"{role} D{damage}"


def _hud_armor_summary(armor_loadout):
    if not armor_loadout or not getattr(armor_loadout, "equipped_instance_id", None):
        return "Armor none"
    try:
        protection = float(getattr(armor_loadout, "damage_reduction", 0.0) or 0.0)
    except (TypeError, ValueError):
        protection = 0.0
    percent = int(round(max(0.0, min(0.85, protection)) * 100.0))
    return f"Armor {percent}%"


_HELP_SECTION_COLORS = (
    "human_slate",
    "human_olive",
    "human_denim",
    "human_wine",
    "human_rust",
    "human_charcoal",
)
_HELP_COMMAND_COLOR = "player"
_HELP_EMPHASIS_COLOR = "objective"
_HELP_MUTED_COLOR = "building_edge"
_HELP_COMMAND_TOKENS = (
    "Shift+J",
    "Shift+W",
    "Shift+K",
    "Shift+S",
    "Left/Right",
    "Up/Down",
    "q/e/z/c",
    "numpad 1-9",
    "WASD",
    "HJKL",
    "f/F",
    "j/t",
    "1-9",
    "1-4",
    "arrows",
    "space",
    "forward",
    "left/right",
    "back",
    "Enter",
    "Esc",
    "Tab",
)
_HELP_COMMAND_TOKEN_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    + "|".join(re.escape(token) for token in sorted(_HELP_COMMAND_TOKENS, key=len, reverse=True))
    + r"|[A-Z]|[xltvfc]|[/?'.,;+><:!*$&@\"_^~=5]"
    + r")(?![A-Za-z0-9])"
)
_HELP_EMPHASIS_PHRASES = (
    "newly surfaced topics",
    "public services",
    "restricted places",
    "owned places",
    "locked places",
    "one-time log warnings",
    "confirmation popups",
    "Combat turn mode",
    "Dangerous actions",
    "World seed",
    "tactical read",
    "topic menu",
    "follow-up branches",
    "property access",
    "objective state",
    "safe",
    "neutral",
    "dangerous",
    "threats",
    "allies",
    "contacts",
    "intel",
    "shelter",
    "loaded",
    "distant",
    "lighting",
    "stealth",
    "pressure",
    "banking",
    "insurance",
    "terminals",
    "transit",
    "storefront counters",
    "trade",
    "rumors",
    "inventory",
    "character sheet",
    "event log history",
    "Places notebook",
    "People notebook",
)
_HELP_EMPHASIS_RE = re.compile(
    r"(?<![A-Za-z0-9])(?:"
    + "|".join(re.escape(phrase) for phrase in sorted(_HELP_EMPHASIS_PHRASES, key=len, reverse=True))
    + r")(?![A-Za-z0-9])",
    re.IGNORECASE,
)
_CHARACTER_SECTION_COLORS = (
    "objective",
    "player",
    "human_olive",
    "human_denim",
    "human_wine",
    "human_rust",
)
_CHARACTER_LABEL_PREFIXES = (
    "Inventory slots",
    "Active effects",
    "Owned props",
    "Needs Energy",
    "Pronouns",
    "Identity",
    "Species",
    "Credits",
    "Bank",
    "Debt",
    "HP",
    "Heat",
    "Status",
    "Safety",
    "Social",
    "Survival",
    "Weapon",
    "Ammo",
    "Armor",
    "Tick",
    "Seed",
    "Chunk",
    "Tile",
    "Insurance",
    "Rumors",
    "Brawn",
    "Ath",
    "Dex",
    "Access",
    "Charm",
    "Sense",
    "base",
    "floor",
    "recent",
    "neglect",
)
_INVENTORY_KEY_ITEM_COLOR = "objective"
_INVENTORY_KEY_ITEM_IDS = frozenset(("property_key", "access_badge", "manager_badge"))
_INVENTORY_CRITICAL_QUEST_ITEM_COLOR = "inventory_critical_quest"
_INVENTORY_STOWED_ITEM_COLOR = "inventory_stowed"


def _help_section_color(index):
    return _HELP_SECTION_COLORS[int(index or 0) % len(_HELP_SECTION_COLORS)]


def _character_section_color(index):
    return _CHARACTER_SECTION_COLORS[int(index or 0) % len(_CHARACTER_SECTION_COLORS)]


def _looks_like_character_section_header(text):
    stripped = str(text or "").strip()
    return bool(stripped and stripped.upper() == stripped and any(ch.isalpha() for ch in stripped))


def _character_metric_segments(chunk, *, section_color):
    text = str(chunk or "")
    if not text:
        return []
    leading = text[: len(text) - len(text.lstrip())]
    trailing_len = len(text) - len(text.rstrip())
    trailing = text[len(text) - trailing_len:] if trailing_len else ""
    core = text.strip()
    if not core:
        return [_segment(text)]

    bold = A_BOLD
    segments = []
    if leading:
        segments.append(_segment(leading, color="human"))

    if ":" in core:
        label, value = core.split(":", 1)
        segments.append(_segment(f"{label.strip()}:", color=section_color, attrs=bold))
        if value:
            segments.append(_segment(value, color="human"))
    else:
        matched_prefix = ""
        for prefix in sorted(_CHARACTER_LABEL_PREFIXES, key=len, reverse=True):
            if core.lower().startswith(prefix.lower() + " ") or core.lower() == prefix.lower():
                matched_prefix = core[: len(prefix)]
                break
        if matched_prefix and len(core) > len(matched_prefix):
            segments.append(_segment(matched_prefix, color=section_color, attrs=bold))
            segments.append(_segment(core[len(matched_prefix):], color="human"))
        elif core.startswith("-"):
            segments.append(_segment("-", color=section_color, attrs=bold))
            segments.append(_segment(core[1:], color="human"))
        else:
            segments.append(_segment(core, color="human"))

    if trailing:
        segments.append(_segment(trailing, color="human"))
    return segments


def _character_sheet_rich_line(text, section_index=0):
    text = str(text or "")
    if not text:
        return ""

    bold = A_BOLD
    section_color = _character_section_color(section_index)
    if _looks_like_character_section_header(text):
        return _rich_line((_segment(text, color=section_color, attrs=bold),), text=text)

    parts = text.split(" | ")
    if len(parts) <= 1:
        return _rich_line(_character_metric_segments(text, section_color=section_color), text=text)

    segments = []
    for idx, part in enumerate(parts):
        if idx > 0:
            segments.append(_segment("   |   ", color="building_edge"))
        segments.extend(_character_metric_segments(part, section_color=section_color))
    return _rich_line(segments, text="   |   ".join(parts))


def _character_sheet_control_line(text):
    text = str(text or "")
    if not text:
        return ""

    bold = A_BOLD
    style = [["building_edge", 0] for _char in text]

    def apply_range(start, end, color, attrs=0):
        start = max(0, min(int(start), len(text)))
        end = max(0, min(int(end), len(text)))
        if end <= start:
            return
        for idx in range(start, end):
            style[idx] = [color, int(attrs or 0)]

    for match in _HELP_COMMAND_TOKEN_RE.finditer(text):
        apply_range(match.start(), match.end(), "objective", bold)
    for match in re.finditer(r"\b(?:Summary|Skills|Loadout|Recipes|Appearance|pages|jump|close|ops|notebooks|log|debug|help)\b", text):
        apply_range(match.start(), match.end(), "player", 0)

    segments = []
    current_text = []
    current_color = None
    current_attrs = 0
    for char, (color, attrs) in zip(text, style):
        if current_text and (color != current_color or attrs != current_attrs):
            segments.append(_segment("".join(current_text), color=current_color, attrs=current_attrs))
            current_text = [char]
            current_color = color
            current_attrs = attrs
            continue
        if not current_text:
            current_color = color
            current_attrs = attrs
        current_text.append(char)
    if current_text:
        segments.append(_segment("".join(current_text), color=current_color, attrs=current_attrs))
    return _rich_line(segments, text=text)


def _character_sheet_nav_line(pages, page_index):
    bold = A_BOLD
    segments = []
    plain_parts = []
    for idx, page in enumerate(list(pages or ())[:9]):
        label = str(page.get("label", f"Page {idx + 1}")).strip() or f"Page {idx + 1}"
        selected = idx == int(page_index or 0)
        if idx > 0:
            segments.append(_segment(" | ", color="building_edge"))
        if selected:
            segments.append(_segment("[", color="objective", attrs=bold))
        segments.append(_segment(str(idx + 1), color="objective", attrs=bold))
        segments.append(_segment(f" {label}", color="player", attrs=bold if selected else 0))
        if selected:
            segments.append(_segment("]", color="objective", attrs=bold))
        plain_parts.append(f"[{idx + 1} {label}]" if selected else f"{idx + 1} {label}")
    if not plain_parts:
        return _character_sheet_control_line("[1 Summary]")
    return _rich_line(segments, text=" | ".join(plain_parts))


def _inventory_entry_is_key_item(entry, item_def=None):
    if not isinstance(entry, dict):
        return False
    item_id = str(entry.get("item_id", "") or "").strip().lower()
    if item_id in _INVENTORY_KEY_ITEM_IDS:
        return True
    data = item_def if isinstance(item_def, dict) else {}
    tags = {str(tag).strip().lower() for tag in data.get("tags", ()) if str(tag).strip()}
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    return (
        "key" in tags
        or bool(str(metadata.get("property_key_id", "") or "").strip())
        or bool(str(metadata.get("property_credential_kind", "") or "").strip())
    )


def _inventory_entry_is_critical_quest_item(entry):
    return item_entry_is_critical_quest_item(entry)


def _character_sheet_display_lines(raw_lines):
    display_lines = []
    section_index = 0
    current_section = 0
    for raw in raw_lines or ():
        text = _line_text(raw)
        if not text:
            display_lines.append("")
            continue
        if _looks_like_character_section_header(text):
            current_section = section_index
            section_index += 1
            display_lines.append(_character_sheet_rich_line(text, section_index=current_section))
            continue
        display_lines.append(_character_sheet_rich_line(text, section_index=current_section))
    return display_lines


def _help_overlay_rich_line(text, section_index=0):
    text = str(text or "")
    if not text:
        return ""

    bold = A_BOLD
    stripped = text.strip()
    if stripped == "Help":
        return _rich_line((_segment(text, color=_HELP_EMPHASIS_COLOR, attrs=bold),), text=text)

    section_color = _help_section_color(section_index)
    base_color = _HELP_MUTED_COLOR if stripped.startswith("? or Esc closes") else section_color
    style = [[base_color, 0] for _char in text]

    def apply_range(start, end, color, attrs=0):
        start = max(0, min(int(start), len(text)))
        end = max(0, min(int(end), len(text)))
        if end <= start:
            return
        for idx in range(start, end):
            style[idx] = [color, int(attrs or 0)]

    if ":" in text and not stripped.startswith("? or Esc closes"):
        apply_range(0, text.index(":") + 1, section_color, bold)

    for match in _HELP_EMPHASIS_RE.finditer(text):
        apply_range(match.start(), match.end(), _HELP_EMPHASIS_COLOR, 0)
    for match in _HELP_COMMAND_TOKEN_RE.finditer(text):
        apply_range(match.start(), match.end(), _HELP_COMMAND_COLOR, bold)

    segments = []
    current_text = []
    current_color = None
    current_attrs = 0
    for char, (color, attrs) in zip(text, style):
        if current_text and (color != current_color or attrs != current_attrs):
            segments.append(_segment("".join(current_text), color=current_color, attrs=current_attrs))
            current_text = [char]
            current_color = color
            current_attrs = attrs
            continue
        if not current_text:
            current_color = color
            current_attrs = attrs
        current_text.append(char)
    if current_text:
        segments.append(_segment("".join(current_text), color=current_color, attrs=current_attrs))

    return _rich_line(segments, text=text)


def _append_help_section(lines, text):
    if lines and lines[-1] != "":
        lines.append("")
    lines.append(str(text))


from game.run_objectives import evaluate_visible_run_objective
from game.status_ui_runtime import (
    _active_status_summary,
    _hud_primary_status_chunks,
    _survival_indicator_chunks,
)
from game.weapons import weapon_by_id

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

def _vehicle_appearance_with_heading(appearance, state):
    if appearance is None or state is None:
        return appearance
    if isinstance(state, (tuple, list)):
        heading = vehicle_heading_tuple(state)
        headlights_on = True
    else:
        state = ensure_vehicle_motion_state(state)
        if state is None:
            return appearance
        heading = vehicle_heading_tuple(state)
        headlights_on = bool(getattr(state, "headlights_on", True))
    effects = tuple(getattr(appearance, "effects", ()) or ())
    if not headlights_on:
        effects = tuple(dict.fromkeys(effects + ("vehicle_headlights_off",)))
    return replace(
        appearance,
        glyph=vehicle_heading_glyph(heading),
        semantic_id=f"property_vehicle_heading_{vehicle_heading_label(heading).lower()}",
        effects=effects,
    )

def _clip(text, width):
    text = str(text)
    width = int(max(0, width))
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."

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

    def _modal_theme_enabled(self):
        return getattr(self.view, "pygame", None) is not None

    def _theme_color(self, theme, role, fallback=None):
        if self._modal_theme_enabled():
            return theme_token(theme, role, fallback or "default")
        return fallback

    def _draw_modal_frame(self, panel_x, panel_y, panel_w, panel_h, theme):
        draw_modal_frame(
            self.view,
            panel_x,
            panel_y,
            panel_w,
            panel_h,
            theme=theme,
            use_theme=self._modal_theme_enabled(),
        )

    def _draw_inventory_inspect_modal(self, inventory_ui, *, screen_w, map_h, modal_theme):
        if not isinstance(inventory_ui, dict) or not bool(inventory_ui.get("inspect_open")):
            return

        inspect_text = inventory_ui.get("inspect_text", "")
        if not _line_text(inspect_text).strip():
            return
        panel_w = _modal_panel_width(screen_w, fraction=0.60, min_width=42)
        body_cell_w, body_w = _modal_body_widths(self.view, panel_w)
        wrapped = list(_wrap_display_lines(inspect_text, body_w) or [""])
        page_cap = max(1, min(10, int(map_h) - 4))
        visible_count = max(1, min(page_cap, len(wrapped)))
        panel_h = min(int(map_h), max(5, visible_count + 4))
        page_size = max(1, panel_h - 4)
        scroll_max = max(0, len(wrapped) - page_size)
        scroll = max(0, min(int(inventory_ui.get("inspect_scroll", 0) or 0), scroll_max))
        inventory_ui["inspect_scroll"] = int(scroll)
        inventory_ui["inspect_scroll_max"] = int(scroll_max)
        inventory_ui["inspect_page_size"] = int(page_size)

        panel_x = max(0, (int(screen_w) - panel_w) // 2)
        panel_y = max(0, (int(map_h) - panel_h) // 2)
        self._draw_modal_frame(panel_x, panel_y, panel_w, panel_h, modal_theme)

        title = str(inventory_ui.get("inspect_title", "Item") or "Item").strip() or "Item"
        title_line = _clip_display_line(f" Inspect: {title} ", body_w)
        self._draw_display_line(panel_x + 2, panel_y, title_line, body_cell_w, attrs=A_BOLD)

        for idx, line in enumerate(wrapped[scroll: scroll + page_size]):
            self._draw_display_line(
                panel_x + 2,
                panel_y + 2 + idx,
                _clip_display_line(line, body_w),
                body_cell_w,
            )

        if scroll_max > 0:
            position = f"{scroll + 1}-{min(len(wrapped), scroll + page_size)}/{len(wrapped)}"
            hint = f"Up/Down scroll  {position}  E/Enter/Esc close"
        else:
            hint = "E/Enter/Esc close"
        self.view.draw_text(
            panel_x + 2,
            panel_y + panel_h - 2,
            _clip_display_line(hint, body_w),
            color=self._theme_color(modal_theme, "footer"),
        )

    def _draw_action_menu(self, action_menu_ui, *, player_screen_x, player_screen_y, map_w, map_h, modal_theme):
        if not isinstance(action_menu_ui, dict) or not bool(action_menu_ui.get("open")):
            return
        rows = list(action_menu_ui.get("rows", ()) or ())
        selected_index = max(0, min(int(action_menu_ui.get("selected_index", 0) or 0), len(rows) - 1)) if rows else 0
        visible_count = max(1, min(8, len(rows) if rows else 1, max(1, int(map_h) - 5)))
        scroll = max(0, min(int(action_menu_ui.get("scroll", 0) or 0), max(0, len(rows) - visible_count)))
        if selected_index < scroll:
            scroll = selected_index
        elif selected_index >= scroll + visible_count:
            scroll = selected_index - visible_count + 1
        action_menu_ui["scroll"] = scroll

        panel_w = max(28, min(42, int(map_w) - 2))
        panel_h = max(5, min(int(map_h), visible_count + 4))
        if panel_w >= int(map_w):
            panel_w = max(8, int(map_w))
        if panel_h >= int(map_h):
            panel_h = max(5, int(map_h))

        try:
            last_dx = int(action_menu_ui.get("last_anchor_dx", 0) or 0)
            last_dy = int(action_menu_ui.get("last_anchor_dy", 1) or 1)
        except (TypeError, ValueError):
            last_dx, last_dy = 0, 1
        anchor_dx = -max(-1, min(1, last_dx))
        anchor_dy = -max(-1, min(1, last_dy))
        if anchor_dx == 0 and anchor_dy == 0:
            anchor_dy = -1

        def _candidate_for(dx, dy):
            if abs(dx) >= abs(dy) and dx:
                x = int(player_screen_x) + (2 if dx > 0 else -panel_w - 2)
                y = int(player_screen_y) - (panel_h // 2)
            else:
                x = int(player_screen_x) - (panel_w // 2)
                y = int(player_screen_y) + (2 if dy > 0 else -panel_h - 2)
            return x, y

        def _clamp_panel(x, y):
            max_x = max(0, int(map_w) - panel_w)
            max_y = max(0, int(map_h) - panel_h)
            return max(0, min(int(x), max_x)), max(0, min(int(y), max_y))

        def _covers_player(x, y):
            return x <= int(player_screen_x) < x + panel_w and y <= int(player_screen_y) < y + panel_h

        candidates = [_candidate_for(anchor_dx, anchor_dy)]
        candidates.extend([
            _candidate_for(1, 0),
            _candidate_for(-1, 0),
            _candidate_for(0, -1),
            _candidate_for(0, 1),
        ])
        panel_x, panel_y = _clamp_panel(*candidates[0])
        for raw_x, raw_y in candidates:
            cand_x, cand_y = _clamp_panel(raw_x, raw_y)
            if not _covers_player(cand_x, cand_y):
                panel_x, panel_y = cand_x, cand_y
                break

        def _clip(text, width):
            text = str(text or "")
            if width <= 0:
                return ""
            if len(text) <= width:
                return text
            if width <= 3:
                return text[:width]
            return text[: width - 3] + "..."

        self._draw_modal_frame(panel_x, panel_y, panel_w, panel_h, modal_theme)
        body_w = max(1, panel_w - 4)
        mode = str(action_menu_ui.get("mode", "action") or "action").strip().lower()
        title = " Bind key " if mode == "bind" else " Actions "
        self.view.draw_text(panel_x + 2, panel_y, _clip(title, body_w), color=self._theme_color(modal_theme, "title", "objective"))
        list_y = panel_y + 1
        visible_rows = rows[scroll: scroll + visible_count]
        for idx, row in enumerate(visible_rows):
            absolute = scroll + idx
            marker = ">" if absolute == selected_index else " "
            label = str(row.get("label", row.get("id", "action"))).strip() or "action"
            binding = str(row.get("binding", "unbound") or "unbound").strip() or "unbound"
            available = bool(row.get("available", True))
            reason = str(row.get("reason", "") or "").strip()
            suffix = f" ({reason})" if reason and not available else ""
            line = f"{marker} [{binding}] {label}{suffix}"
            color = "player" if absolute == selected_index else ("human_slate" if available else "human")
            self.view.draw_text(panel_x + 1, list_y + idx, _clip(line, panel_w - 2), color=color)
        if not rows:
            self.view.draw_text(panel_x + 2, list_y, _clip("(no actions)", body_w), color="human")

        feedback = str(action_menu_ui.get("feedback", "") or "").strip()
        footer = feedback
        if not footer:
            controller_recent = str(action_menu_ui.get("last_input_kind", "") or "").strip().lower() == "controller"
            if mode == "bind":
                footer = "Press input | Back cancel" if controller_recent else "Press a key | Esc cancel"
            else:
                footer = "South run | West bind | North reset | East close" if controller_recent else "Enter run | B bind | R reset | Esc close"
        self.view.draw_text(
            panel_x + 2,
            panel_y + panel_h - 2,
            _clip(footer, body_w),
            color=self._theme_color(modal_theme, "footer", "human_slate"),
        )

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
                if _hud_line_is_read(lines[line_index]):
                    self._hud_flash_ranges_by_line.pop(key, None)
                    continue
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
        return _hud_line_with_flash_ranges(line, ranges, A_REVERSE)

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

    def _draw(self, x, y, glyph, color=None, color_word=None, attrs=0, semantic_id=None, effects=None, overlays=None, layer=None, priority=None, light_tint=None, visual_source=None):
        kwargs = {"attrs": int(attrs or 0)}
        if color is not None:
            kwargs["color"] = color
        if color_word and hasattr(self.view, "pygame"):
            kwargs["color_word"] = color_word
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
        if isinstance(light_tint, dict) and light_tint:
            kwargs["light_tint"] = light_tint
        if visual_source is not None and hasattr(self.view, "pygame"):
            kwargs["visual_source"] = tuple(visual_source)
        try:
            self.view.draw(x, y, glyph, **kwargs)
            return
        except TypeError:
            if "light_tint" in kwargs:
                retry_kwargs = dict(kwargs)
                retry_kwargs.pop("light_tint", None)
                try:
                    self.view.draw(x, y, glyph, **retry_kwargs)
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

    def _draw_appearance(self, x, y, appearance, attrs=0, light_tint=None, visual_source=None):
        if not appearance or not bool(getattr(appearance, "visible", True)):
            return
        self._draw(
            x,
            y,
            getattr(appearance, "glyph", "?"),
            color=getattr(appearance, "color", None),
            color_word=getattr(appearance, "color_word", None),
            attrs=int(attrs or 0) | int(getattr(appearance, "attrs", 0) or 0),
            semantic_id=getattr(appearance, "semantic_id", None),
            effects=getattr(appearance, "effects", ()),
            overlays=getattr(appearance, "overlays", ()),
            layer=getattr(appearance, "layer", None),
            priority=getattr(appearance, "priority", None),
            light_tint=light_tint,
            visual_source=visual_source,
        )

    def _draw_vision_scene(self, scene, screen_w, screen_h):
        scene = scene if isinstance(scene, dict) else {}
        is_pygame = hasattr(self.view, "pygame")
        started_tick = int(scene.get("started_tick", 0) or 0)
        target_end_tick = int(scene.get("target_end_tick", started_tick) or started_tick)
        total_ticks = max(0, target_end_tick - started_tick)
        elapsed_ticks = max(0, min(total_ticks, int(getattr(self.sim, "tick", 0) or 0) - started_tick))
        remaining_ticks = max(0, total_ticks - elapsed_ticks)
        progress = ""
        if total_ticks > 0:
            progress = (
                f"Dreaming... {_tick_duration_label(self.sim, elapsed_ticks)} / "
                f"{_tick_duration_label(self.sim, total_ticks)}"
            )
            if remaining_ticks > 0:
                progress += f" ({_tick_duration_label(self.sim, remaining_ticks)} left)"
        if not is_pygame:
            title = "Dreaming..."
            hint = "The room goes blank until you wake."
            center_y = max(0, int(screen_h) // 2 - 1)
            self.view.draw_text(max(0, (int(screen_w) - len(title)) // 2), center_y, title, color="objective")
            self.view.draw_text(max(0, (int(screen_w) - len(hint)) // 2), center_y + 2, hint, color="default")
            if progress:
                self.view.draw_text(max(0, (int(screen_w) - len(progress)) // 2), center_y + 4, progress, color="default")
            return True

        width = max(1, int(scene.get("width", 1) or 1))
        height = max(1, int(scene.get("height", 1) or 1))
        offset_x = max(0, (int(screen_w) - width) // 2)
        offset_y = max(0, (int(screen_h) - height) // 2)
        tile_styles = {
            "floor": (" ", "floor_downtown", "floor_downtown"),
            "grass": (" ", "floor_wilderness", "floor_wilderness"),
            "shadow": (" ", "building_fill_dark", "building_fill_dark"),
            "wall": ("#", "building_edge_gray_b", "building_edge_gray_b"),
            "door": ("+", "feature_door", "feature_door"),
            "window": ("=", "feature_window", "feature_window"),
            "counter": ("=", "building_roof_storefront", "building_roof_storefront"),
            "table": ("_", "building_fill_painted", "building_fill_painted"),
        }
        tiles = scene.get("tiles")
        if not isinstance(tiles, list):
            tiles = []
        for y in range(height):
            row = tiles[y] if y < len(tiles) and isinstance(tiles[y], list) else []
            for x in range(width):
                tile_kind = str(row[x] if x < len(row) else "floor").strip().lower() or "floor"
                glyph, color, semantic_id = tile_styles.get(tile_kind, tile_styles["floor"])
                self._draw(
                    offset_x + x,
                    offset_y + y,
                    glyph,
                    color=color,
                    semantic_id=semantic_id,
                    layer="terrain",
                    priority=-900,
                )

        for prop in tuple(scene.get("props", ()) or ()):
            if not isinstance(prop, dict):
                continue
            try:
                prop_x = int(prop.get("x", 0) or 0)
                prop_y = int(prop.get("y", 0) or 0)
            except (TypeError, ValueError):
                continue
            if not (0 <= prop_x < width and 0 <= prop_y < height):
                continue
            self._draw(
                offset_x + prop_x,
                offset_y + prop_y,
                str(prop.get("glyph", "o") or "o")[:1],
                color=prop.get("color") or "world_object_home",
                semantic_id=prop.get("semantic_id") or "world_object_personal_home",
                effects=tuple(prop.get("effects", ()) or ()),
                layer="fixture",
                priority=5,
            )

        for actor in tuple(scene.get("actors", ()) or ()):
            if not isinstance(actor, dict):
                continue
            try:
                actor_x = int(actor.get("x", 0) or 0)
                actor_y = int(actor.get("y", 0) or 0)
            except (TypeError, ValueError):
                continue
            if not (0 <= actor_x < width and 0 <= actor_y < height):
                continue
            self._draw(
                offset_x + actor_x,
                offset_y + actor_y,
                str(actor.get("glyph", "@") or "@")[:1],
                color=actor.get("color") or "human",
                semantic_id=actor.get("semantic_id") or "npc_civilian",
                effects=tuple(actor.get("effects", ()) or ()),
                overlays=tuple(actor.get("overlays", ()) or ()),
                layer="actor",
                priority=30,
            )
        if progress:
            progress = str(progress)
            progress_y = min(max(0, int(screen_h) - 2), max(0, offset_y + height + 1))
            progress_x = max(0, (int(screen_w) - len(progress)) // 2)
            self.view.draw_text(progress_x, progress_y, progress[: max(0, int(screen_w))], color="default")
        return True

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
        ]
        for line in (
            "Move: arrows, WASD, HJKL, q/e/z/c diagonals, or numpad 1-9. Wait with space or 5.",
            "Action palette: Tab opens a nearby action menu. Enter runs the selected action, B rebinds it, R resets it, and protected movement/back/help keys stay fixed.",
            "Observe: / talks, ' physically interacts, . uses the service at your tile or adjacent terminal, ; locks or unlocks a nearby door, x opens the look cursor, T takes a tactical read, and X opens the map.",
            "Vehicles: ' enters a vehicle. Local driving uses forward to accelerate, left/right to turn, back to brake or reverse from rest. H toggles headlights. X opens a view-only map; drive onto an entrance ramp for quick travel. Boats stay local. Press t to get out.",
            "Conversation: talking to nearby people opens a topic menu with follow-up branches, trade, and rumors.",
            "Conversation controls: Up/Down selects, Enter or E answers, Esc or Q declines or closes, and Space closes completed exchanges.",
            "Conversation read: + marks newly surfaced topics when your character notices them; at higher Conversation, its color hints safe, neutral, or dangerous.",
            "Ingress: Shift+J door breach, Shift+W window entry, Shift+K wall breach.",
            'Features: + closed door, \' open door, " window, / breach opening, > higher stairs, < lower stairs, : stair landing, E elevator.',
            "Infrastructure: typed markers (l lamp, p pole, h hydrant, u stop, j/t utility, $ ATM, c claim terminal, r access panel).",
            "Local terrain: = road, : trail, , brush, ^ rock, ~ water, _ shore flats.",
            "Remote sites: relay/lookout/survey sites provide intel; camps and huts can offer shelter.",
            f"Aim/Combat: {aim_open}; firearms use f/F target lock, with free aim available from Tab actions or any binding you assign. {aim_confirm}, T tactical read, C cover, v cover hop, Shift+S sneak, V cycle weapon.",
            "Items: I inventory, , picks up nearby items, U use/equip/stow/throw, R drop.",
            "Tinkering: inspect a mechanical plan for its parts, carry a usable multitool, and press U on the plan to build. Press U on the finished device to deploy or operate it; physically interact with your own deployed device to recover it.",
            "Visual classes: vehicles use '&' symbol colors only; properties use letters; items are bright symbols; humans use colored @ symbols and wildlife uses taxonomy letters.",
            "Badges: ! marks threats or restricted places, + marks allies or public services, * marks contacts or owned places, and L marks locked places.",
            "Progress: O operations report, Y opens the Places notebook; Tab switches to the People notebook. L opens event log history.",
            "Log modal: T cycles filters; H sets the current modal filter as the live HUD filter.",
            "Services: . uses the service at your tile or adjacent terminal, including banking, insurance, terminals, transit, and storefront counters. P buy property.",
            "Character: + opens the character sheet. Tab or Left/Right switch pages.",
        ):
            _append_help_section(lines, line)
        if debug_mode_enabled(self.sim):
            debug_line = "Debug: D live telemetry for lighting, stealth, pressure, property access, and objective state."
            character_line = lines.pop()
            if lines and lines[-1] == "":
                lines.pop()
            _append_help_section(lines, debug_line)
            _append_help_section(lines, character_line)
        if zoom_mode == "overworld":
            if view_only:
                _append_help_section(lines, "Map view: move to browse chunks, Enter or x inspect the selected chunk, and t returns to local view.")
                _append_help_section(lines, "Map tools: X opens the map from local mode, M adds a marker here, l lists markers, N jumps to the nearest marker, O ops, Y notebooks, L log.")
            else:
                _append_help_section(lines, "Quick travel: normal 8-way movement travels chunks, G drives to the last marker, M adds a marker, l lists markers, N jumps to the nearest marker, and t returns to local driving.")
            _append_help_section(lines, "Overworld POIs: stronger non-city chunks can replace the center glyph with a site initial.")
            _append_help_section(lines, "Overworld centers: each chunk keeps its district or terrain icon; bright means loaded and dim means distant.")
            _append_help_section(lines, "Overworld regions: soft boundary lines separate major outside regions.")
        if overlay_active:
            _append_help_section(lines, "Combat turn mode: each action consumes a turn until danger settles.")
        _append_help_section(lines, "Dangerous actions teach through one-time log warnings, not confirmation popups.")
        return lines

    def _help_overlay_display_lines(self, raw_lines):
        display_lines = []
        section_index = 0
        for raw in raw_lines or ():
            text = _line_text(raw)
            if not text:
                display_lines.append("")
                continue
            stripped = str(text).strip()
            if stripped == "Help" or stripped.startswith("? or Esc closes"):
                display_lines.append(_help_overlay_rich_line(text, section_index=section_index))
                continue
            display_lines.append(_help_overlay_rich_line(text, section_index=section_index))
            section_index += 1
        return display_lines

    def _draw_display_line(self, x, y, line, max_width, attrs=0):
        segments = _line_segments(line)
        if segments:
            self.view.draw_segments(x, y, segments, max_width=max_width, attrs=int(attrs or 0))
            return
        self.view.draw_text(x, y, _line_text(line), attrs=int(attrs or 0))

    def _draw_dream_residue_mood_line(self, residue_line, map_w, map_h):
        text = str(residue_line or "").strip()
        if not text:
            return
        map_w = max(1, int(map_w or 1))
        map_h = max(1, int(map_h or 1))
        cell_w = max(1, map_w - 4)
        text_w = max(1, _view_text_wrap_width(self.view, cell_w))
        lines = [
            line
            for line in _wrap_display_lines(text, text_w, max_lines=2)
            if _line_text(line).strip()
        ]
        if not lines:
            return
        start_y = max(0, map_h - len(lines))
        for idx, line in enumerate(lines):
            plain = _line_text(line)
            # Pygame UI text is narrower than map cells, so center by the
            # resolved text/cell ratio instead of raw character count.
            approx_cell_len = max(1, min(cell_w, (len(plain) * cell_w + text_w - 1) // text_w))
            x = max(0, min(map_w - 1, (map_w - approx_cell_len) // 2))
            segments = _line_segments(line) or [_segment(plain, color="flora_flower_violet")]
            self.view.draw_segments(
                x,
                start_y + idx,
                segments,
                max_width=cell_w,
                attrs=A_DIM,
            )

    def _side_state_layout(self, screen_w, screen_h, configured_hud_lines, *, panels_open=False):
        screen_w = max(1, int(screen_w))
        screen_h = max(1, int(screen_h))
        configured_hud_lines = max(1, int(configured_hud_lines))
        supported = screen_w >= 58 and screen_h >= 18
        if not supported:
            map_h = max(1, min(self.sim.tilemap.height, screen_h - configured_hud_lines))
            hud_lines = max(
                1,
                min(
                    max(1, screen_h - 1),
                    max(configured_hud_lines, screen_h - map_h),
                ),
            )
            return {
                "supported": False,
                "rail_visible": False,
                "rail_w": 0,
                "rail_x": screen_w,
                "map_w": min(self.sim.tilemap.width, screen_w),
                "map_h": map_h,
                "hud_lines": hud_lines,
            }

        target_log_rows = 6 if screen_h >= 34 else (5 if screen_h >= 28 else 4)
        log_rows = max(3, min(target_log_rows, configured_hud_lines))
        requested_hud_rows = min(max(1, screen_h - 1), log_rows + 1)
        map_h = max(1, min(self.sim.tilemap.height, screen_h - requested_hud_rows))
        hud_lines = max(1, min(max(1, screen_h - 1), screen_h - map_h))
        if panels_open:
            return {
                "supported": True,
                "rail_visible": False,
                "rail_w": 0,
                "rail_x": screen_w,
                "map_w": min(self.sim.tilemap.width, screen_w),
                "map_h": map_h,
                "hud_lines": hud_lines,
            }

        min_map_w = 36
        gap_w = 1
        desired_rail_w = min(36, max(22, screen_w // 4))
        available_rail_w = max(0, screen_w - min_map_w - gap_w)
        rail_w = min(desired_rail_w, available_rail_w)
        rail_visible = rail_w >= 20
        if not rail_visible:
            return {
                "supported": True,
                "rail_visible": False,
                "rail_w": 0,
                "rail_x": screen_w,
                "map_w": min(self.sim.tilemap.width, screen_w),
                "map_h": map_h,
                "hud_lines": hud_lines,
            }

        map_w = min(self.sim.tilemap.width, max(1, screen_w - rail_w - gap_w))
        rail_x = min(screen_w - rail_w, map_w + gap_w)
        return {
            "supported": True,
            "rail_visible": True,
            "rail_w": rail_w,
            "rail_x": rail_x,
            "map_w": map_w,
            "map_h": map_h,
            "hud_lines": hud_lines,
        }

    def _draw_state_rail(self, *, rail_x, rail_y, rail_w, rail_h, modal_theme, sections):
        rail_x = int(rail_x)
        rail_y = int(rail_y)
        rail_w = int(rail_w)
        rail_h = int(rail_h)
        if rail_w < 20 or rail_h < 6:
            return False

        self._draw_modal_frame(rail_x, rail_y, rail_w, rail_h, modal_theme)
        body_x = rail_x + 2
        body_cell_w, body_text_w = _modal_body_widths(self.view, rail_w, horizontal_padding=4, min_width=1)
        bottom_y = rail_y + rail_h - 1
        y = rail_y + 1
        section_gap = 1 if rail_h >= 28 else 0

        title = "STATE"
        self.view.draw_text(
            body_x,
            y,
            _clip_display_line(title, body_text_w),
            color=self._theme_color(modal_theme, "title", "objective"),
            attrs=A_BOLD,
        )
        y += 1

        for section in sections or ():
            if y >= bottom_y:
                break
            lines = list(section.get("lines", ()) or ())
            if not lines:
                continue
            title = str(section.get("title", "") or "").strip()
            if title:
                if y >= bottom_y:
                    break
                self.view.draw_text(
                    body_x,
                    y,
                    _clip_display_line(title.upper(), body_text_w),
                    color=self._theme_color(modal_theme, "accent", "player"),
                    attrs=A_BOLD,
                )
                y += 1
            section_id = str(section.get("id", title or "state") or "state")
            for line_index, line in enumerate(lines):
                if y >= bottom_y:
                    break
                flashed = self._hud_flash_line(section_id, line_index, line)
                self._draw_display_line(
                    body_x,
                    y,
                    _clip_display_line(flashed, body_text_w),
                    body_cell_w,
                )
                y += 1
            if section_gap and y < bottom_y:
                y += section_gap

        return True

    def _draw_log_divider(self, y, width, modal_theme):
        y = int(y)
        width = max(1, int(width))
        if y < 0:
            return False
        self.view.draw_text(
            0,
            y,
            "-" * width,
            color=self._theme_color(modal_theme, "divider", "building_edge"),
        )
        return True

    def _hud_token_line(self, text, *, label="", color=None):
        text = str(text or "").strip()
        if not text:
            return ""
        label = str(label or "").strip()
        if not label:
            label = text.split(" ", 1)[0].rstrip(":")
        if not label:
            return text
        if not text.lower().startswith(label.lower()):
            return text
        prefix = text[:len(label)]
        rest = text[len(label):]
        return _rich_line(
            (
                _segment(prefix, color=color, attrs=A_BOLD),
                _segment(rest),
            ),
            text=text,
        )

    def _hud_styled_chunk(self, text):
        raw = text
        text = _line_text(raw).strip()
        if not text:
            return ""
        lower = text.lower()
        if lower.startswith("combat "):
            return self._hud_token_line(text, label="Combat", color="projectile")
        if lower.startswith("heat "):
            return self._hud_token_line(text, label="Heat", color="projectile")
        if lower.startswith("hp "):
            return self._hud_token_line(text, label="HP", color="survival_meter_mid")
        if lower.startswith("downed:") or lower.startswith("downed "):
            label = "Downed:" if lower.startswith("downed:") else "Downed"
            return self._hud_token_line(text, label=label, color="projectile")
        if lower.startswith("cr "):
            return self._hud_token_line(text, label="Cr", color="player")
        if lower.startswith("opp "):
            return self._hud_token_line(text, label="Opp", color="objective")
        if lower.startswith("look "):
            return self._hud_token_line(text, label="Look", color="objective")
        if lower.startswith("aim "):
            return self._hud_token_line(text, label="Aim", color="projectile")
        if lower.startswith("read:") or lower.startswith("read "):
            return text
        if lower.startswith("tactical:") or lower.startswith("tactical "):
            label = "Tactical:" if lower.startswith("tactical:") else "Tactical"
            return self._hud_token_line(text, label=label, color="projectile")
        if lower.startswith("talk "):
            return self._hud_token_line(text, label="Talk", color="player")
        if lower.startswith("interact "):
            return self._hud_token_line(text, label="Interact", color="property_service")
        if lower.startswith("throw "):
            return self._hud_token_line(text, label="Throw", color="projectile")
        if _line_segments(raw):
            return raw
        return text

    def _look_focus_label(self, look_purpose):
        purpose = str(look_purpose or "inspect").strip().lower()
        if purpose == "aim":
            return "Aim", "projectile"
        if purpose == "throw":
            return "Throw", "projectile"
        if purpose == "interact":
            return "Interact", "property_service"
        if purpose == "talk":
            return "Talk", "player"
        if purpose == "backup_order":
            return "Order", "objective"
        return "Look", "objective"

    def _look_focus_coord_text(self, look_ui, *, active_z=0, zoom_mode="city"):
        look_ui = look_ui if isinstance(look_ui, dict) else {}
        mode = str(look_ui.get("mode", zoom_mode) or zoom_mode).strip().lower()
        if mode == "overworld":
            return f"{int(look_ui.get('chunk_x', 0) or 0)},{int(look_ui.get('chunk_y', 0) or 0)}c"
        return (
            f"{int(look_ui.get('x', 0) or 0)},"
            f"{int(look_ui.get('y', 0) or 0)},"
            f"{int(look_ui.get('z', active_z) or active_z)}"
        )

    def _look_focus_header_line(self, look_ui, look_purpose, *, active_z=0, zoom_mode="city"):
        label, color = self._look_focus_label(look_purpose)
        coord = self._look_focus_coord_text(look_ui, active_z=active_z, zoom_mode=zoom_mode)
        text = f"{label} {coord}"
        return _rich_line(
            (
                _segment(label, color=color, attrs=A_BOLD),
                _segment(f" {coord}", color="building_edge"),
            ),
            text=text,
        )

    def _draw_look_focus_card(
        self,
        look_ui,
        look_purpose,
        *,
        map_w,
        map_h,
        active_z=0,
        zoom_mode="city",
        panels_open=False,
    ):
        if panels_open or not isinstance(look_ui, dict) or not bool(look_ui.get("active")):
            return False
        inspect_text = look_ui.get("inspect_text", "")
        if not _line_text(inspect_text).strip():
            return False
        map_w = int(map_w)
        map_h = int(map_h)
        if map_w < 30 or map_h < 8:
            return False
        panel_w = min(64, map_w - 2)
        panel_w = max(28, panel_w)
        body_w = max(8, _view_text_wrap_width(self.view, panel_w - 4))
        header = self._look_focus_header_line(look_ui, look_purpose, active_z=active_z, zoom_mode=zoom_mode)
        body_lines = [header]
        wrapped_inspect = list(_wrap_display_lines(inspect_text, body_w, max_lines=2) or [])
        body_lines.extend(wrapped_inspect[: max(0, 3 - len(body_lines))])
        if not body_lines:
            return False
        panel_h = len(body_lines) + 2
        if panel_h + 1 >= map_h:
            return False
        panel_x = 1
        panel_y = max(0, map_h - panel_h - 1)
        top = "+" + ("-" * max(0, panel_w - 2)) + "+"
        mid = "|" + (" " * max(0, panel_w - 2)) + "|"
        bot = "+" + ("-" * max(0, panel_w - 2)) + "+"
        self.view.draw_text(panel_x, panel_y, top, color="building_edge")
        for row in range(1, panel_h - 1):
            self.view.draw_text(panel_x, panel_y + row, mid, color="building_edge")
        self.view.draw_text(panel_x, panel_y + panel_h - 1, bot, color="building_edge")
        for idx, line in enumerate(body_lines[:3]):
            self._draw_display_line(
                panel_x + 2,
                panel_y + 1 + idx,
                _clip_display_line(line, body_w),
                body_w,
            )
        return True

    def _draw_drone_command_card(self, drone_command_ui, *, map_w, map_h, modal_theme):
        if not isinstance(drone_command_ui, dict) or not bool(drone_command_ui.get("open")):
            return False
        map_w = int(map_w)
        map_h = int(map_h)
        if map_w < 36 or map_h < 9:
            return False
        panel_w = min(74, map_w - 2)
        panel_w = max(34, panel_w)
        body_w = max(12, _view_text_wrap_width(self.view, panel_w - 4))
        raw_lines = list(drone_command_ui.get("status_lines", ()) or [])
        feedback = str(drone_command_ui.get("feedback", "") or "").strip()
        camera_open = bool(drone_command_ui.get("camera_open"))
        camera_mode = str(drone_command_ui.get("camera_mode", "inspect") or "inspect").strip().lower()
        camera_inspect = str(drone_command_ui.get("camera_inspect_text", "") or "").strip()
        hint = (
            "Attack: move cursor  A/Enter fire  X inspect  Esc command"
            if camera_open and camera_mode == "attack" else
            "Camera: move cursor  X/Enter inspect  Esc command  G close"
            if camera_open else
            "Move: directions  Cycle: [/]  A attack  X camera  H/F/R/M intent  G/Esc close"
        )
        body_lines = ["Drone Attack" if camera_open and camera_mode == "attack" else "Drone Camera" if camera_open else "Drone Command"]
        for line in raw_lines:
            body_lines.extend(_wrap_display_lines(str(line), body_w, max_lines=2))
        if camera_open and camera_inspect:
            body_lines.extend(_wrap_display_lines(camera_inspect, body_w, max_lines=2))
        if feedback:
            body_lines.extend(_wrap_display_lines(feedback, body_w, max_lines=2))
        body_lines.extend(_wrap_display_lines(hint, body_w, max_lines=2))
        max_body = max(3, min(12, map_h - 3))
        body_lines = body_lines[:max_body]
        panel_h = len(body_lines) + 2
        panel_x = 1
        panel_y = max(0, map_h - panel_h - 1)
        self._draw_modal_frame(panel_x, panel_y, panel_w, panel_h, modal_theme)
        for idx, line in enumerate(body_lines):
            if idx == 0:
                self.view.draw_text(
                    panel_x + 2,
                    panel_y + 1 + idx,
                    _clip(str(line), body_w),
                    color=self._theme_color(modal_theme, "title", "objective"),
                )
                continue
            self._draw_display_line(panel_x + 2, panel_y + 1 + idx, _clip_display_line(line, body_w), body_w)
        return True

    def _draw_drone_sheet_modal(self, drone_sheet_ui, *, screen_w, map_h, modal_theme):
        if not isinstance(drone_sheet_ui, dict) or not bool(drone_sheet_ui.get("open")):
            return False
        screen_w = int(screen_w)
        map_h = int(map_h)
        if screen_w < 48 or map_h < 12:
            return False

        def _local_clip(text, width):
            text = str(text)
            width = int(max(0, width))
            if len(text) <= width:
                return text
            if width <= 3:
                return text[:width]
            return text[: width - 3] + "..."

        panel_w = min(screen_w - 4, _modal_panel_width(screen_w, fraction=0.75, min_width=58))
        panel_x = max(0, (screen_w - panel_w) // 2)
        panel_h = max(12, min(map_h, int(round(map_h * 0.82))))
        panel_y = max(0, (map_h - panel_h) // 2)
        body_cell_w, body_w = _modal_body_widths(self.view, panel_w)
        _row_cell_w, row_w = _modal_body_widths(self.view, panel_w, horizontal_padding=4)
        self._draw_modal_frame(panel_x, panel_y, panel_w, panel_h, modal_theme)

        tab = str(drone_sheet_ui.get("tab", "status") or "status").strip().lower() or "status"
        cargo_side = str(drone_sheet_ui.get("cargo_side", "pack") or "pack").strip().lower() or "pack"
        module_side = str(drone_sheet_ui.get("module_side", "drone") or "drone").strip().lower() or "drone"
        if module_side == "pack":
            module_side = "bay"
        visual = drone_sheet_ui.get("visual_model") if isinstance(drone_sheet_ui.get("visual_model"), dict) else {}
        title = f" {str(visual.get('title', 'Drone Workshop') or 'Drone Workshop')} "
        self.view.draw_text(
            panel_x + 2,
            panel_y,
            _local_clip(title, body_w),
            color=self._theme_color(modal_theme, "title", "objective"),
            attrs=A_BOLD,
        )

        tab_labels = []
        tab_ids = tuple(drone_sheet_ui.get("tabs", ()) or ("status", "cargo", "battery", "modules", "schematic"))
        for idx, tab_id in enumerate(tab_ids, start=1):
            label = f"[{str(tab_id).upper()}]" if tab_id == tab else str(tab_id)
            tab_labels.append(f"{idx}:{label}")
        tab_line = "  ".join(tab_labels)
        if tab == "cargo":
            tab_line += f" | {cargo_side}"
        if tab == "modules":
            tab_line += f" | {'workshop stock' if module_side == 'bay' else 'installed'}"
        self.view.draw_text(
            panel_x + 2,
            panel_y + 1,
            _local_clip(tab_line, body_w),
            color=self._theme_color(modal_theme, "muted"),
        )

        eligible = list(drone_sheet_ui.get("eligible", ()) or ())
        visible_start = max(0, int(drone_sheet_ui.get("visible_start", 0) or 0))
        target_bits = []
        for row in eligible[visible_start: visible_start + 4]:
            marker = ">" if bool(row.get("selected")) else "-"
            access = "nearby" if bool(row.get("accessible")) else "remote"
            target_bits.append(f"{marker}{row.get('label', 'drone')} ({access})")
        subtitle = str(visual.get("subtitle", "") or "").strip()
        target_line = "TARGETS " + " | ".join(target_bits) if target_bits else (subtitle or "WORKSHOP STORAGE")
        self.view.draw_text(
            panel_x + 2,
            panel_y + 2,
            _local_clip(target_line, body_w),
            color=self._theme_color(modal_theme, "title"),
        )

        def _meter_text(meter, width=5):
            label = str((meter or {}).get("label", "") or "")[:7]
            try:
                used = max(0, int((meter or {}).get("used", 0) or 0))
            except (TypeError, ValueError):
                used = 0
            try:
                limit = max(0, int((meter or {}).get("limit", 0) or 0))
            except (TypeError, ValueError):
                limit = 0
            filled = 0 if limit <= 0 else min(width, int(round(width * min(used, limit) / limit)))
            return f"{label} [{'=' * filled}{'.' * (width - filled)}] {used}/{limit}"

        dashboard_y = panel_y + 3
        dashboard_lines = 0
        mode = str(visual.get("mode", "") or "").strip().lower()
        if panel_h >= 16:
            if mode != "storage":
                chassis_class = str(visual.get("chassis_class", "") or "?").strip().upper() or "?"
                glyph = str(visual.get("glyph", "d") or "d")[:1] or "d"
                core_name = str(visual.get("core_name", "none") or "none")
                paint = visual.get("paint") if isinstance(visual.get("paint"), dict) else {}
                primary = str(paint.get("primary_color", "steel") or "steel")
                secondary = str(paint.get("secondary_color") or paint.get("accent_color", "blue") or "blue")
                frame_line = f"FRAME [ {glyph} ] {chassis_class}-CLASS  |  CORE {core_name}  |  FINISH {primary}/{secondary}"
                self.view.draw_text(
                    panel_x + 2,
                    dashboard_y,
                    _local_clip(frame_line, body_w),
                    color="item_restricted",
                    attrs=A_BOLD,
                )
                dashboard_lines += 1

            meters = tuple(visual.get("meters", ()) or ())
            if meters:
                meter_segments = []
                for meter in meters:
                    meter_segments.append(_segment(_meter_text(meter) + "  ", color=(meter or {}).get("color")))
                self.view.draw_segments(
                    panel_x + 2,
                    dashboard_y + dashboard_lines,
                    meter_segments,
                    max_width=body_cell_w,
                )
                dashboard_lines += 1

            if mode != "storage":
                ports = "  ".join(str(value) for value in tuple(visual.get("ports", ()) or ())) or "none"
                capabilities = ", ".join(str(value) for value in tuple(visual.get("capabilities", ()) or ())) or "none"
                detail_line = f"PORTS {ports}  |  CAPABILITIES {capabilities}"
                self.view.draw_text(
                    panel_x + 2,
                    dashboard_y + dashboard_lines,
                    _local_clip(detail_line, body_w),
                    color=self._theme_color(modal_theme, "muted"),
                )
                dashboard_lines += 1

        rows = list(drone_sheet_ui.get("rows", ()) or [])
        selected_index = max(0, min(int(drone_sheet_ui.get("selected_index", 0) or 0), len(rows) - 1)) if rows else 0
        section_y = dashboard_y + dashboard_lines
        section_side = ""
        if tab == "modules":
            section_side = " / WORKSHOP STOCK" if module_side == "bay" else " / INSTALLED"
        elif tab == "cargo":
            section_side = f" / {cargo_side.upper()}"
        section_line = f"-- {tab.upper()}{section_side} "
        section_line += "-" * max(0, body_w - len(section_line))
        self.view.draw_text(
            panel_x + 2,
            section_y,
            _local_clip(section_line, body_w),
            color=self._theme_color(modal_theme, "muted"),
        )

        body_top = section_y + 1
        footer_y = panel_y + panel_h - 2
        list_h = max(1, footer_y - body_top)
        display_rows = []
        row_anchors = []
        for idx, raw in enumerate(rows):
            row = raw if isinstance(raw, dict) else {"label": str(raw)}
            label = str(row.get("label", "") or "")
            selection_prefix = "> " if idx == selected_index else "  "
            glyph = str(row.get("glyph", "") or "")[:1]
            mark = str(row.get("compatibility_mark", "") or "")[:5]
            class_band = str(row.get("drone_class_band", "") or "")[:4]
            row_color = None
            if not bool(row.get("actionable", False)):
                row_color = self._theme_color(modal_theme, "muted")
            if str(row.get("compatibility_match", "") or "") == "incompatible" or row.get("compatible") is False:
                row_color = self._theme_color(modal_theme, "warning")
            if glyph or mark or class_band:
                item_prefix = f"{glyph or ' '} "
                row_segments = (
                    _segment(selection_prefix, color=row_color),
                    _segment(item_prefix[:1], color=row.get("swatch_color") or row_color),
                    _segment(item_prefix[1:], color=row_color),
                    _segment(f"{mark:<5}", color=row.get("compatibility_color") or row_color),
                    _segment(f"{class_band:<4} ", color=row.get("compatibility_color") or row_color),
                    _segment(label, color=row_color),
                )
            else:
                row_segments = (
                    _segment(selection_prefix, color=row_color),
                    _segment(label, color=row_color),
                )
            row_anchors.append(len(display_rows))
            rich_row = _rich_line(row_segments)
            wrapped = _wrap_display_lines(rich_row, row_w, max_lines=2) if label.strip() else [rich_row]
            for line in wrapped:
                display_rows.append({
                    "line": line,
                    "row_index": idx,
                })

        scroll = max(0, int(drone_sheet_ui.get("scroll", 0) or 0))
        if row_anchors and selected_index < len(row_anchors):
            anchor = row_anchors[selected_index]
            if anchor < scroll:
                scroll = anchor
            elif anchor >= scroll + list_h:
                scroll = max(0, anchor - list_h + 1)
        max_scroll = max(0, len(display_rows) - list_h)
        scroll = max(0, min(scroll, max_scroll))
        drone_sheet_ui["scroll"] = scroll
        for draw_index, display in enumerate(display_rows[scroll: scroll + list_h]):
            selected = int(display["row_index"]) == selected_index
            attrs = A_REVERSE if selected else 0
            line = _clip_display_line(display["line"], row_w)
            self._draw_display_line(
                panel_x + 2,
                body_top + draw_index,
                line,
                row_w,
                attrs=attrs,
            )
        if not display_rows:
            self.view.draw_text(panel_x + 2, body_top, "(empty)", color=self._theme_color(modal_theme, "muted"))

        feedback = str(drone_sheet_ui.get("feedback", "") or "").strip()
        selected_row = rows[selected_index] if rows and selected_index < len(rows) and isinstance(rows[selected_index], dict) else {}
        context_line = feedback or str(selected_row.get("action_hint", "") or "").strip()
        if not context_line:
            context_line = f"1-{len(tab_ids)} tabs  [/] target  Arrows select  G/Esc close"
        self.view.draw_text(
            panel_x + 2,
            footer_y,
            _local_clip(context_line, body_w),
            color=self._theme_color(modal_theme, "footer"),
        )
        return True

    def _draw_wire_kit_modal(self, wire_kit_ui, *, screen_w, map_h, modal_theme):
        if not isinstance(wire_kit_ui, dict) or not bool(wire_kit_ui.get("open")):
            return False
        screen_w = int(screen_w)
        map_h = int(map_h)
        if screen_w < 48 or map_h < 12:
            return False

        def _local_clip(text, width):
            text = str(text)
            width = int(max(0, width))
            if len(text) <= width:
                return text
            if width <= 3:
                return text[:width]
            return text[: width - 3] + "..."

        panel_w = min(screen_w - 4, _modal_panel_width(screen_w, fraction=0.72, min_width=58))
        panel_x = max(0, (screen_w - panel_w) // 2)
        panel_h = max(12, min(map_h, int(round(map_h * 0.74))))
        panel_y = max(0, (map_h - panel_h) // 2)
        body_cell_w, body_w = _modal_body_widths(self.view, panel_w)
        row_cell_w, row_w = _modal_body_widths(self.view, panel_w, horizontal_padding=4)
        self._draw_modal_frame(panel_x, panel_y, panel_w, panel_h, modal_theme)

        self.view.draw_text(panel_x + 2, panel_y, _local_clip(" Wire Kit ", body_w), color=self._theme_color(modal_theme, "title", "objective"))
        tab = str(wire_kit_ui.get("tab", "kit") or "kit").strip().lower() or "kit"
        tab_ids = tuple(wire_kit_ui.get("tabs", ()) or ("kit", "pack", "programs", "data", "credentials", "backups", "corrupted"))
        tab_labels = []
        for idx, tab_id in enumerate(tab_ids, start=1):
            label = tab_id.upper() if tab_id == tab else tab_id
            tab_labels.append(f"{idx}:{label}")
        self.view.draw_text(panel_x + 2, panel_y + 1, _local_clip("Tabs " + "  ".join(tab_labels), body_w), color=self._theme_color(modal_theme, "muted"))

        status_lines = list(wire_kit_ui.get("status_lines", ()) or ())
        status_y = panel_y + 2
        for idx, line in enumerate(status_lines[:3]):
            self._draw_display_line(panel_x + 2, status_y + idx, _clip_display_line(str(line), body_w), body_cell_w)

        rows = list(wire_kit_ui.get("rows", ()) or [])
        selected_index = max(0, min(int(wire_kit_ui.get("selected_index", 0) or 0), len(rows) - 1)) if rows else 0
        body_top = panel_y + 6
        footer_y = panel_y + panel_h - 2
        list_h = max(1, footer_y - body_top - 1)
        display_rows = []
        row_anchors = []
        for idx, row in enumerate(rows):
            label = str(row.get("label", row) if isinstance(row, dict) else row)
            prefix = "> " if idx == selected_index else "  "
            row_anchors.append(len(display_rows))
            wrapped = _wrap_display_lines(prefix + label, row_w, max_lines=2) if label.strip() else [prefix.strip()]
            display_rows.extend(wrapped)
        scroll = max(0, int(wire_kit_ui.get("scroll", 0) or 0))
        if row_anchors and selected_index < len(row_anchors):
            anchor = row_anchors[selected_index]
            if anchor < scroll:
                scroll = anchor
            elif anchor >= scroll + list_h:
                scroll = max(0, anchor - list_h + 1)
        max_scroll = max(0, len(display_rows) - list_h)
        scroll = max(0, min(scroll, max_scroll))
        wire_kit_ui["scroll"] = scroll
        for idx, line in enumerate(display_rows[scroll: scroll + list_h]):
            self._draw_display_line(panel_x + 2, body_top + idx, _clip_display_line(line, row_w), row_cell_w)
        if not display_rows:
            empty = "No wire entries here." if tab != "pack" else "No wireware or data in backpack."
            self.view.draw_text(panel_x + 2, body_top, _local_clip(empty, body_w), color=self._theme_color(modal_theme, "muted"))

        feedback = str(wire_kit_ui.get("feedback", "") or "").strip()
        if feedback:
            self._draw_display_line(panel_x + 2, footer_y - 1, _clip_display_line(feedback, body_w), body_cell_w)
        if tab == "programs":
            hint = f"1-{len(tab_ids)} tabs  Arrows select  Enter RAM load/unload  U backpack  Esc/Q close"
        else:
            hint = f"1-{len(tab_ids)} tabs  Arrows select  Enter act/study  U load-unload  Esc/Q close"
        self.view.draw_text(panel_x + 2, footer_y, _local_clip(hint, body_w), color=self._theme_color(modal_theme, "footer"))
        return True

    def _draw_wire_connection_modal(self, wire_connection_ui, *, screen_w, map_h, modal_theme):
        if not isinstance(wire_connection_ui, dict) or not bool(wire_connection_ui.get("open")):
            return False
        screen_w = int(screen_w)
        map_h = int(map_h)
        if screen_w < 48 or map_h < 12:
            return False

        def _local_clip(text, width):
            text = str(text)
            width = int(max(0, width))
            if len(text) <= width:
                return text
            if width <= 3:
                return text[:width]
            return text[: width - 3] + "..."

        panel_w = min(screen_w - 4, _modal_panel_width(screen_w, fraction=0.72, min_width=58))
        panel_x = max(0, (screen_w - panel_w) // 2)
        panel_h = max(12, min(map_h, int(round(map_h * 0.68))))
        panel_y = max(0, (map_h - panel_h) // 2)
        body_cell_w, body_w = _modal_body_widths(self.view, panel_w)
        row_cell_w, row_w = _modal_body_widths(self.view, panel_w, horizontal_padding=4)
        self._draw_modal_frame(panel_x, panel_y, panel_w, panel_h, modal_theme)

        target_class = str(wire_connection_ui.get("target_class", "wire") or "wire").replace("_", " ")
        self.view.draw_text(panel_x + 2, panel_y, _local_clip(f" Wire Connection: {target_class} ", body_w), color=self._theme_color(modal_theme, "title", "objective"))

        status_lines = list(wire_connection_ui.get("status_lines", ()) or ())
        status_y = panel_y + 1
        for idx, line in enumerate(status_lines[:4]):
            wrapped = _wrap_display_lines(str(line), body_w, max_lines=1)
            self._draw_display_line(panel_x + 2, status_y + idx, _clip_display_line(wrapped[0], body_w), body_cell_w)

        rows = list(wire_connection_ui.get("rows", ()) or [])
        selected_index = max(0, min(int(wire_connection_ui.get("selected_index", 0) or 0), len(rows) - 1)) if rows else 0
        body_top = panel_y + 6
        footer_y = panel_y + panel_h - 2
        list_h = max(1, footer_y - body_top - 1)
        display_rows = []
        row_anchors = []
        for idx, row in enumerate(rows):
            label = str(row.get("label", row) if isinstance(row, dict) else row)
            prefix = "> " if idx == selected_index else "  "
            row_anchors.append(len(display_rows))
            display_rows.extend(_wrap_display_lines(prefix + label, row_w, max_lines=2))
        scroll = max(0, int(wire_connection_ui.get("scroll", 0) or 0))
        if row_anchors and selected_index < len(row_anchors):
            anchor = row_anchors[selected_index]
            if anchor < scroll:
                scroll = anchor
            elif anchor >= scroll + list_h:
                scroll = max(0, anchor - list_h + 1)
        max_scroll = max(0, len(display_rows) - list_h)
        scroll = max(0, min(scroll, max_scroll))
        wire_connection_ui["scroll"] = scroll
        for idx, line in enumerate(display_rows[scroll: scroll + list_h]):
            self._draw_display_line(panel_x + 2, body_top + idx, _clip_display_line(line, row_w), row_cell_w)
        if not display_rows:
            self.view.draw_text(panel_x + 2, body_top, _local_clip("No wire connection rows.", body_w), color=self._theme_color(modal_theme, "muted"))

        feedback = str(wire_connection_ui.get("feedback", "") or "").strip()
        if feedback:
            self._draw_display_line(panel_x + 2, footer_y - 1, _clip_display_line(feedback, body_w), body_cell_w)
        hint = "Arrows select  Enter/U choose  Esc/Q close"
        self.view.draw_text(panel_x + 2, footer_y, _local_clip(hint, body_w), color=self._theme_color(modal_theme, "footer"))
        return True

    def _draw_wire_scene_modal(self, wire_scene_ui, *, screen_w, map_h, modal_theme):
        if not isinstance(wire_scene_ui, dict) or not bool(wire_scene_ui.get("open")):
            return False
        wire_state = self.sim.ecs.get(WireState).get(self.player_eid)
        scene = getattr(wire_state, "active_scene", None) if wire_state is not None else None
        if not isinstance(scene, dict):
            return False
        screen_w = int(screen_w)
        map_h = int(map_h)
        if screen_w < 54 or map_h < 16:
            return False

        def _local_clip(text, width):
            text = str(text)
            width = int(max(0, width))
            if len(text) <= width:
                return text
            if width <= 3:
                return text[:width]
            return text[: width - 3] + "..."

        scene_theme = wire_scene_theme(scene, modal_theme)
        panel_w = min(screen_w - 4, _modal_panel_width(screen_w, fraction=0.82, min_width=68))
        panel_x = max(0, (screen_w - panel_w) // 2)
        panel_h = max(16, min(map_h, int(round(map_h * 0.82))))
        panel_y = max(0, (map_h - panel_h) // 2)
        body_cell_w, body_w = _modal_body_widths(self.view, panel_w)
        self._draw_modal_frame(panel_x, panel_y, panel_w, panel_h, scene_theme)

        title = f" Wire Layer: {scene.get('target_name', 'wire target')} "
        self.view.draw_text(panel_x + 2, panel_y, _local_clip(title, body_w), color=self._theme_color(scene_theme, "title", "objective"))

        bounds = scene.get("bounds") if isinstance(scene.get("bounds"), dict) else {}
        grid_w = max(1, int(bounds.get("width", 27) or 27))
        grid_h = max(1, int(bounds.get("height", 15) or 15))
        # Split the modal in screen-cell space, then derive text capacity for
        # each region.  Pygame can fit more UI-font characters than map cells
        # across the same pixel width, so using ``body_w`` here lets the HUD
        # rail (and especially node reads) spill beyond its physical bounds.
        map_w = min(grid_w, max(18, body_cell_w // 2))
        map_top = panel_y + 2
        map_left = panel_x + 2
        side_x = map_left + map_w + 3
        side_cell_w = max(1, body_cell_w - map_w - 3)
        side_w = max(1, _view_text_wrap_width(self.view, side_cell_w))
        footer_y = panel_y + panel_h - 2
        map_rows = min(grid_h, max(1, footer_y - map_top - 1))
        walkable = {
            (int(point[0]), int(point[1]))
            for point in (scene.get("walkable") or ())
            if isinstance(point, (list, tuple)) and len(point) >= 2
        }
        node_by_pos = {}
        for node in scene.get("nodes", ()) or ():
            if isinstance(node, dict):
                node_by_pos[(int(node.get("x", -1)), int(node.get("y", -1)))] = node
        entity_by_pos = {}
        for entity in scene.get("wire_entities", ()) or ():
            if not isinstance(entity, dict) or bool(entity.get("destroyed")):
                continue
            if str(entity.get("source", "") or "").strip().lower() == "ice" and not bool(entity.get("revealed")):
                continue
            try:
                hp = int(entity.get("hp", 0) or 0)
                point = (int(entity.get("x", -1)), int(entity.get("y", -1)))
            except (TypeError, ValueError):
                continue
            if hp > 0:
                entity_by_pos[point] = entity
        user_by_pos = {}
        for user in scene.get("wire_users", ()) or ():
            if not isinstance(user, dict) or not bool(user.get("available", True)):
                continue
            try:
                point = (int(user.get("x", -1)), int(user.get("y", -1)))
            except (TypeError, ValueError):
                continue
            user_by_pos.setdefault(point, user)
        effect_by_pos = {}
        for effect in scene.get("wire_action_effects", ()) or ():
            if not isinstance(effect, dict):
                continue
            visual = wire_visual_for_kind(effect.get("visual_kind", "effect_packet_pulse"))
            path = list(effect.get("path", ()) or ())
            for raw_point in path:
                if not isinstance(raw_point, (list, tuple)) or len(raw_point) < 2:
                    continue
                try:
                    point = (int(raw_point[0]), int(raw_point[1]))
                except (TypeError, ValueError):
                    continue
                effect_by_pos[point] = visual
        avatar = scene.get("avatar") if isinstance(scene.get("avatar"), dict) else {}
        avatar_pos = (int(avatar.get("x", -999)), int(avatar.get("y", -999)))

        def _draw_wire_cell(cell_x, cell_y, visual):
            glyph = str(visual.get("glyph", " ") or " ")[:1]
            color = visual.get("color", "default")
            semantic_id = visual.get("semantic_id")
            if hasattr(self.view, "draw"):
                self._draw(cell_x, cell_y, glyph, color=color, semantic_id=semantic_id, layer="ui_overlay", priority=55)
            else:
                self.view.draw_text(cell_x, cell_y, glyph, color=color)

        for gy in range(map_rows):
            for gx in range(map_w):
                point = (gx, gy)
                node = node_by_pos.get(point)
                entity = entity_by_pos.get(point)
                user = user_by_pos.get(point)
                if entity and point != avatar_pos:
                    visual = wire_visual_for_kind(entity.get("visual_kind", "ice_trace_sentinel"))
                elif user and point != avatar_pos:
                    visual = wire_visual_for_kind(user.get("visual_kind", "wire_user"))
                elif point in effect_by_pos and point != avatar_pos:
                    visual = effect_by_pos[point]
                else:
                    visual = wire_visual_for_cell(
                        scene,
                        gx,
                        gy,
                        walkable=(point in walkable),
                        node=node,
                        avatar=(point == avatar_pos),
                        width=grid_w,
                        height=grid_h,
                    )
                _draw_wire_cell(map_left + gx, map_top + gy, visual)

        status_lines = list(wire_scene_ui.get("status_lines", ()) or [])
        if not status_lines:
            status_lines = [
                f"Layer: {scene.get('target_class', 'wire').replace('_', ' ')}",
                f"Interface: {scene.get('interface_name', 'interface')}",
            ]
        side_y = map_top
        theme_label = "wire"
        interface_theme = scene.get("interface_theme") if isinstance(scene.get("interface_theme"), dict) else {}
        if interface_theme:
            theme_label = str(interface_theme.get("label", theme_label) or theme_label)
        dialogue = wire_scene_ui.get("wire_dialogue") if isinstance(wire_scene_ui.get("wire_dialogue"), dict) else {}
        dialogue_open = bool(dialogue.get("open"))
        if dialogue_open:
            panel_label = "WIRE DIALOGUE"
        else:
            if bool(wire_scene_ui.get("program_load_panel")):
                panel_label = "LOAD RAM"
            else:
                panel_label = "PROGRAMS" if bool(wire_scene_ui.get("program_panel")) else f"{theme_label} HUD"
        self.view.draw_text(side_x, side_y, _local_clip(panel_label, side_w), color=self._theme_color(scene_theme, "title", "objective"))
        side_y += 1
        if dialogue_open:
            header = f"{dialogue.get('user_label', 'wire user')} / {dialogue.get('wire_handle', 'handle')}"
            for line in (
                header,
                f"Link: {dialogue.get('provenance_kind', 'unknown')} / {dialogue.get('link_state', 'unknown')}",
                str(dialogue.get("last_response", "")),
            ):
                if not line:
                    continue
                wrapped = _wrap_display_lines(str(line), side_w, max_lines=2)
                for part in wrapped:
                    if side_y >= footer_y - 2:
                        break
                    self._draw_display_line(side_x, side_y, _clip_display_line(part, side_w), side_cell_w)
                    side_y += 1
            side_y += 1
            rows = list(dialogue.get("rows", ()) or [])
            selected_dialogue = int(wire_scene_ui.get("selected_dialogue_index", 0) or 0)
            max_rows = max(1, footer_y - side_y - 2)
            for idx, row in enumerate(rows[:max_rows]):
                prefix = "> " if idx == selected_dialogue else "  "
                wrapped = _wrap_display_lines(prefix + str(row.get("label", "topic")), side_w, max_lines=1)
                self._draw_display_line(side_x, side_y, _clip_display_line(wrapped[0], side_w), side_cell_w)
                side_y += 1
        elif bool(wire_scene_ui.get("program_load_panel")):
            load_rows = list(wire_scene_ui.get("load_program_rows", ()) or [])
            selected_load = int(wire_scene_ui.get("selected_load_program_index", 0) or 0)
            self.view.draw_text(side_x, side_y, _local_clip("KIT PROGRAMS", side_w), color=self._theme_color(scene_theme, "title", "objective"))
            side_y += 1
            if not load_rows:
                self._draw_display_line(side_x, side_y, "No unloaded kit programs.", side_cell_w)
                side_y += 1
            max_load_rows = max(1, footer_y - side_y - 2)
            for idx, row in enumerate(load_rows[:max_load_rows]):
                prefix = "> " if idx == selected_load else "  "
                wrapped = _wrap_display_lines(prefix + str(row.get("label", "program")), side_w, max_lines=2)
                for part in wrapped:
                    if side_y >= footer_y - 1:
                        break
                    self._draw_display_line(side_x, side_y, _clip_display_line(part, side_w), side_cell_w)
                    side_y += 1
        elif bool(wire_scene_ui.get("program_panel")):
            program_rows = list(wire_scene_ui.get("program_rows", ()) or [])
            target_rows = list(wire_scene_ui.get("target_rows", ()) or [])
            selected_program = int(wire_scene_ui.get("selected_program_index", 0) or 0)
            selected_target = int(wire_scene_ui.get("selected_target_index", 0) or 0)
            self.view.draw_text(side_x, side_y, _local_clip("RAM", side_w), color=self._theme_color(scene_theme, "title", "objective"))
            side_y += 1
            max_program_rows = max(1, min(5, footer_y - side_y - 6))
            if not program_rows:
                self._draw_display_line(side_x, side_y, "L loads the first fitting kit program", side_cell_w)
                side_y += 1
            for idx, row in enumerate(program_rows[:max_program_rows]):
                prefix = "> " if idx == selected_program else "  "
                wrapped = _wrap_display_lines(prefix + str(row.get("label", "program")), side_w, max_lines=1)
                self._draw_display_line(side_x, side_y, _clip_display_line(wrapped[0], side_w), side_cell_w)
                side_y += 1
            side_y += 1
            self.view.draw_text(side_x, side_y, _local_clip("Target", side_w), color=self._theme_color(scene_theme, "title", "objective"))
            side_y += 1
            max_target_rows = max(1, min(5, footer_y - side_y - 2))
            for idx, row in enumerate(target_rows[:max_target_rows]):
                prefix = "> " if idx == selected_target else "  "
                wrapped = _wrap_display_lines(prefix + str(row.get("label", "target")), side_w, max_lines=1)
                self._draw_display_line(side_x, side_y, _clip_display_line(wrapped[0], side_w), side_cell_w)
                side_y += 1
        else:
            for line in status_lines[:8]:
                wrapped = _wrap_display_lines(str(line), side_w, max_lines=1)
                self._draw_display_line(side_x, side_y, _clip_display_line(wrapped[0], side_w), side_cell_w)
                side_y += 1
            side_y += 1
            self.view.draw_text(side_x, side_y, _local_clip("Read", side_w), color=self._theme_color(scene_theme, "title", "objective"))
            side_y += 1
            read_lines = list(wire_scene_ui.get("read_lines", ()) or scene.get("last_read_lines", ()) or ())
            max_read_lines = max(1, footer_y - side_y - 2)
            display_lines = []
            for raw in read_lines:
                display_lines.extend(_wrap_display_lines(str(raw), side_w, max_lines=2))
            for idx, line in enumerate(display_lines[:max_read_lines]):
                self._draw_display_line(side_x, side_y + idx, _clip_display_line(line, side_w), side_cell_w)

        feedback = str(wire_scene_ui.get("feedback", "") or scene.get("last_feedback", "") or "").strip()
        if feedback:
            self._draw_display_line(panel_x + 2, footer_y - 1, _clip_display_line(feedback, body_w), body_cell_w)
        if dialogue_open:
            hint = "Up/Down topic  Enter choose  Esc back"
        elif bool(wire_scene_ui.get("program_load_panel")):
            hint = "Up/Down choose exact program  Enter/L load  Esc/U back"
        elif bool(wire_scene_ui.get("program_panel")):
            hint = "Up/Down program  Left/Right target  Enter/R run  L load  U unload  Esc back"
        else:
            hint = "Move  D download records  Enter/I/X read  R programs  P panic  Esc/Q exit-node disconnect"
        self.view.draw_text(panel_x + 2, footer_y, _local_clip(hint, body_w), color=self._theme_color(scene_theme, "footer"))
        return True

    def _dialog_header_line(self, dialog_ui):
        dialog_ui = dialog_ui if isinstance(dialog_ui, dict) else {}
        title = str(dialog_ui.get("title", "Conversation")).strip() or "Conversation"
        npc_eid = dialog_ui.get("npc_eid")
        if npc_eid is None:
            return f" {title} "
        try:
            npc_eid = int(npc_eid)
        except (TypeError, ValueError):
            return f" {title} "
        appearance = None
        try:
            appearance = self.sim.appearance.entity(npc_eid, player_eid=self.player_eid)
        except Exception:
            appearance = None
        color = getattr(appearance, "color", None) or "human"
        color_word = getattr(appearance, "color_word", None)
        semantic_id = getattr(appearance, "semantic_id", None) or "npc_civilian"
        effects = tuple(getattr(appearance, "effects", ()) or ())
        overlays = tuple(getattr(appearance, "overlays", ()) or ())
        header_text = f" @ {title} "
        return _rich_line(
            (
                _segment(" "),
                _segment(
                    "@",
                    color=color,
                    attrs=A_BOLD,
                    inline_glyph=True,
                    semantic_id=semantic_id,
                    color_word=color_word,
                    effects=effects,
                    overlays=overlays,
                ),
                _segment(f" {title} "),
            ),
            text=header_text,
        )

    def update(self):
        self.view.clear()
        self._hud_render_frame += 1
        begin_frame = getattr(self.view, "begin_frame", None)
        if callable(begin_frame):
            animation_tick = None
            if not bool(getattr(self.view, "uses_realtime_animation", False)):
                animation_tick = int(getattr(self.sim, "tick", 0))
            begin_frame(animation_tick=animation_tick)

        if manual_pause_active(self.sim):
            screen_w, screen_h = self.view.size()
            pause_state = manual_pause_state(self.sim)
            binding_label = str(pause_state.get("binding_label", "unbound") or "unbound").strip()
            title = "Paused"
            prompt = f"Press {binding_label} to resume."
            center_y = max(0, int(screen_h) // 2)
            self.view.draw_text(
                max(0, (int(screen_w) - len(title)) // 2),
                max(0, center_y - 1),
                title,
                color="objective",
            )
            self.view.draw_text(
                max(0, (int(screen_w) - len(prompt)) // 2),
                min(max(0, int(screen_h) - 1), center_y + 1),
                prompt,
                color="player",
            )
            return

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
        modal_theme = resolve_modal_theme(self.sim, kind="modal")
        player_vehicle_state = vehicle_states.get(self.player_eid)
        active_vehicle_prop = None
        if player_vehicle_state and player_vehicle_state.active_vehicle_id:
            maybe_vehicle = self.sim.properties.get(player_vehicle_state.active_vehicle_id)
            if _property_is_vehicle(maybe_vehicle):
                active_vehicle_prop = maybe_vehicle
        inventory_ui = getattr(self.sim, "inventory_ui", {
            "open": False,
            "selected_index": 0,
            "inspect_text": "",
            "sort_mode": "default",
        })
        inventory_ui["sort_mode"] = normalize_inventory_sort_mode(inventory_ui.get("sort_mode", "default"))
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
            "Cache" if inventory_container_kind == "cache" else ("Cargo" if inventory_container_kind == "scene" else ("Herbs" if inventory_container_kind == "campfire_herb_cache" else "Container"))
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
            "conversation_read": "",
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
        aim_lock_ui = getattr(self.sim, "aim_lock_ui", {
            "active": False,
            "target_eid": None,
        })
        help_ui = getattr(self.sim, "help_ui", {
            "open": False,
            "scroll": 0,
        })
        action_menu_ui = getattr(self.sim, "action_menu_ui", {
            "open": False,
            "rows": [],
            "selected_index": 0,
            "scroll": 0,
        })
        drone_command_ui = getattr(self.sim, "drone_command_ui", {
            "open": False,
            "selected_drone_eid": None,
            "eligible": [],
            "status_lines": [],
            "feedback": "",
        })
        drone_sheet_ui = getattr(self.sim, "drone_sheet_ui", {
            "open": False,
            "selected_drone_eid": None,
            "eligible": [],
            "tab": "status",
            "cargo_side": "pack",
            "module_side": "drone",
            "rows": [],
            "feedback": "",
        })
        wire_kit_ui = getattr(self.sim, "wire_kit_ui", {
            "open": False,
            "tab": "kit",
            "rows": [],
            "status_lines": [],
            "feedback": "",
        })
        wire_connection_ui = getattr(self.sim, "wire_connection_ui", {
            "open": False,
            "rows": [],
            "status_lines": [],
            "feedback": "",
        })
        wire_scene_ui = getattr(self.sim, "wire_scene_ui", {
            "open": False,
            "status_lines": [],
            "read_lines": [],
            "feedback": "",
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
        blocking_panel_open = any(
            bool(state.get("open"))
            for state in (
                inventory_ui,
                trade_ui,
                casino_ui,
                dialog_ui,
                action_menu_ui,
                drone_command_ui,
                drone_sheet_ui,
                wire_kit_ui,
                wire_connection_ui,
                wire_scene_ui,
                help_ui,
                character_ui,
                report_ui,
                log_ui,
                debug_ui,
            )
            if isinstance(state, dict)
        )

        screen_w, screen_h = self.view.size()
        configured_hud_lines = max(1, int(self.hud_lines))
        side_layout = self._side_state_layout(
            screen_w,
            screen_h,
            configured_hud_lines,
            panels_open=blocking_panel_open,
        )
        map_view_h = int(side_layout["map_h"])
        hud_lines = int(side_layout["hud_lines"])
        map_view_w = int(side_layout["map_w"])
        side_layout_supported = bool(side_layout.get("supported"))
        side_rail_visible = bool(side_layout.get("rail_visible"))
        rail_x = int(side_layout.get("rail_x", screen_w))
        rail_w = int(side_layout.get("rail_w", 0))
        hud_w = max(1, int(screen_w))
        hud_text_w = _view_text_wrap_width(self.view, hud_w)
        live_timeskip = getattr(self.sim, "live_timeskip", {})
        vision_scene = vision_scene_render_state(self.sim)
        zoom_mode = str(getattr(self.sim, "zoom_mode", "city")).lower()
        try:
            requested_world_magnification = int(getattr(self.view, "world_magnification", 1) or 1)
        except (TypeError, ValueError):
            requested_world_magnification = 1
        requested_world_magnification = 2 if requested_world_magnification == 2 and zoom_mode != "overworld" else 1
        map_w = max(1, (map_view_w + requested_world_magnification - 1) // requested_world_magnification)
        map_h = max(1, (map_view_h + requested_world_magnification - 1) // requested_world_magnification)

        def _aim_lock_target_pos():
            if not isinstance(aim_lock_ui, dict) or not bool(aim_lock_ui.get("active")):
                return None, None
            try:
                target_eid = int(aim_lock_ui.get("target_eid"))
            except (TypeError, ValueError):
                return None, None
            target_pos = positions.get(target_eid)
            if not target_pos or int(target_pos.z) != int(active_z):
                return None, None
            vitality = vitalities.get(target_eid)
            if vitality and (bool(getattr(vitality, "downed", False)) or int(getattr(vitality, "hp", 1)) <= 0):
                return None, None
            if not _entity_visible_to_player(self.sim, self.player_eid, target_eid):
                return None, None
            return target_eid, target_pos
        if vision_scene is not None:
            self._draw_vision_scene(vision_scene, screen_w, screen_h)
            return
        if isinstance(live_timeskip, dict) and bool(live_timeskip.get("active")):
            service = str(live_timeskip.get("service", "") or "").strip().lower()
            prop_name = str(live_timeskip.get("property_name", live_timeskip.get("property_id", "site")) or "site").strip() or "site"
            title = str(live_timeskip.get("title", "") or "").strip()
            if not title:
                title = "Sleeping..." if service == "rest" else "Laying low..."
            footer = str(live_timeskip.get("footer", "") or "").strip() or "The city keeps moving without you."
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
            self.view.draw_text(panel_x + 2, panel_y + panel_h - 2, _clip(footer, body_w), color="default")
            return
        world_view_started = False
        if requested_world_magnification > 1:
            begin_world_view = getattr(self.view, "begin_world_view", None)
            if callable(begin_world_view):
                world_view_started = bool(begin_world_view(
                    map_w,
                    map_h,
                    allocation_width_cells=map_view_w,
                    allocation_height_cells=map_view_h,
                ))
        if not world_view_started:
            requested_world_magnification = 1
            map_w = map_view_w
            map_h = map_view_h

        camera_x = (player_pos.x - (map_w // 2)) if player_pos else 0
        camera_y = (player_pos.y - (map_h // 2)) if player_pos else 0

        def _overworld_anchor_chunk():
            return _player_overworld_chunk(
                self.sim,
                self.player_eid,
                pos=player_pos,
            )

        look_purpose = str(look_ui.get("purpose", "inspect")).lower()
        visibility_state = getattr(self.sim, "visibility_state", {})
        player_visible = visibility_state.get("player_visible", set()) if isinstance(visibility_state, dict) else set()
        player_explored = visibility_state.get("player_explored", set()) if isinstance(visibility_state, dict) else set()
        if not isinstance(player_visible, set):
            player_visible = set(player_visible or ())
        if not isinstance(player_explored, set):
            player_explored = set(player_explored or ())
        player_tile_memory = _player_tile_memory_state(self.sim)

        def _is_visible(x, y, z):
            return (int(x), int(y), int(z)) in player_visible

        def _is_explored(x, y, z):
            return (int(x), int(y), int(z)) in player_explored

        def _remember_tile_appearance(x, y, z, appearance):
            player_tile_memory[(int(x), int(y), int(z))] = appearance

        def _remembered_tile_appearance(x, y, z):
            return player_tile_memory.get((int(x), int(y), int(z)))

        occupied_vehicle_choices = {}
        hidden_vehicle_occupants = set()
        if zoom_mode != "overworld":
            vehicle_by_occupant = getattr(self.sim, "vehicle_by_occupant", {})
            primary_occupants = getattr(self.sim, "vehicle_primary_occupants", {})
            for occupant_eid, indexed_vehicle_id in tuple(vehicle_by_occupant.items()):
                raw_state = vehicle_states.get(occupant_eid)
                state = ensure_vehicle_motion_state(raw_state)
                if not state or not bool(getattr(state, "in_vehicle", False)):
                    continue
                vehicle_id = str(getattr(state, "active_vehicle_id", "") or "").strip()
                if not vehicle_id or vehicle_id != str(indexed_vehicle_id):
                    continue
                vehicle_prop = self.sim.properties.get(vehicle_id)
                if not _property_is_vehicle(vehicle_prop):
                    continue
                occupant_pos = positions.get(occupant_eid)
                if not occupant_pos or int(occupant_pos.z) != int(active_z):
                    continue
                if not renders.get(occupant_eid):
                    continue
                hidden_vehicle_occupants.add(occupant_eid)
                if primary_occupants.get(vehicle_id) != occupant_eid:
                    continue
                choice_key = (0 if occupant_eid == self.player_eid else 1, int(occupant_eid))
                occupied_vehicle_choices[vehicle_id] = (
                    choice_key,
                    occupant_eid,
                    state,
                    vehicle_prop,
                    occupant_pos,
                )
        occupied_vehicle_by_driver = {
            occupant_eid: (state, vehicle_prop)
            for _vehicle_id, (_choice_key, occupant_eid, state, vehicle_prop, _pos) in occupied_vehicle_choices.items()
        }

        lighting_state = _lighting_state(self.sim)
        if int(lighting_state.get("tick", -1)) != int(getattr(self.sim, "tick", 0)):
            lighting_state = _update_lighting_state(self.sim, player_pos=player_pos)
        ambient_sampling = _prepare_ambient_sampling(self.sim, clock=lighting_state, z=active_z)
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
        ambient_dim_attr = A_DIM

        def _ambient_sample(x, y, z):
            key = (int(x), int(y), int(z))
            cached = ambient_cache.get(key)
            if isinstance(cached, dict):
                return cached
            sampled = _lighting_ambient_snapshot(
                self.sim,
                x,
                y,
                z,
                clock=lighting_state,
                sampling=ambient_sampling,
            )
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

        def _actor_ambient_attr(x, y, z):
            if not ambient_dim_attr:
                return 0
            sample = _ambient_sample(x, y, z)
            try:
                ambient = float(sample.get("ambient", 1.0))
            except (TypeError, ValueError):
                ambient = 1.0
            # Pygame/curses A_DIM is intentionally blunt. Keep moderate daylight
            # interiors readable on actors while terrain still shows room shade.
            if ambient >= 0.55:
                return 0
            return ambient_dim_attr

        light_tint_drawer = getattr(self.view, "draw_light_tint", None)
        player_glare = lighting_state.get("player_glare")
        try:
            player_glare_strength = float(player_glare.get("strength", 0.0) if isinstance(player_glare, dict) else 0.0)
        except (TypeError, ValueError):
            player_glare_strength = 0.0
        player_glare_strength = max(0.0, min(1.0, player_glare_strength))

        def _draw_light_tint_overlay(sx, sy, wx, wy, z):
            if not callable(light_tint_drawer):
                return
            sample = _ambient_sample(wx, wy, z)
            tint = sample.get("light_tint") if isinstance(sample, dict) else None
            if not isinstance(tint, dict):
                return
            try:
                if float(tint.get("strength", 0.0) or 0.0) <= 0.0:
                    return
            except (TypeError, ValueError):
                return
            light_tint_drawer(sx, sy, tint, layer="fx", priority=-900)

        def _draw_glare_wash_overlay(sx, sy, wx, wy, z):
            if player_glare_strength <= 0.0 or not callable(light_tint_drawer) or player_pos is None:
                return
            sample = _ambient_sample(wx, wy, z)
            try:
                ambient = float(sample.get("ambient", 1.0) or 1.0)
            except (TypeError, ValueError):
                ambient = 1.0
            ambient = max(0.0, min(1.0, ambient))
            dist = abs(int(wx) - int(player_pos.x)) + abs(int(wy) - int(player_pos.y))
            distance_factor = max(0.0, min(1.0, float(dist) / 14.0))
            dark_factor = max(0.0, 0.72 - ambient) / 0.72
            wash = player_glare_strength * (0.035 + (0.08 * distance_factor) + (0.12 * dark_factor))
            if wash <= 0.025:
                return
            tint = {
                "rgb": [255, 250, 226],
                "strength": round(max(0.02, min(0.22, wash)), 4),
                "profile": "visual_glare",
                "pulse": "soft",
            }
            light_tint_drawer(sx, sy, tint, layer="fx", priority=-625)

        def _surface_light_tint(wx, wy, z):
            sample = _ambient_sample(wx, wy, z)
            tint = sample.get("light_tint") if isinstance(sample, dict) else None
            if not isinstance(tint, dict):
                return None
            try:
                strength = float(tint.get("strength", 0.0) or 0.0)
                outside = float(sample.get("outside_ambient", 1.0) or 1.0)
            except (TypeError, ValueError):
                return None
            if strength <= 0.0:
                return None
            profile = str(tint.get("profile", "") or "").strip().lower()
            vivid_profiles = {"casino_neon", "fire_orange", "emergency_red", "headlight_white", "ritual_violet"}
            if bool(sample.get("inside")) or profile in vivid_profiles:
                scale = 1.18
            else:
                scale = max(0.42, 1.15 - (0.62 * max(0.0, min(1.0, outside))))
            surface_strength = max(0.0, min(1.0, strength * scale))
            if surface_strength <= 0.035:
                return None
            surface_tint = dict(tint)
            surface_tint["strength"] = round(float(surface_strength), 4)
            surface_tint["surface_light"] = True
            return surface_tint

        def _draw_dream_residue_overlay():
            residue = dream_residue_state(self.sim)
            if not isinstance(residue, dict) or not callable(light_tint_drawer):
                return
            if zoom_mode == "overworld" or player_pos is None:
                return
            profile_key = str(residue.get("light_profile_hint", "") or "").strip().lower()
            profile = LIGHT_COLOR_PROFILES.get(profile_key) or LIGHT_COLOR_PROFILES.get("ritual_violet", {})
            rgb = tuple(profile.get("rgb", (168, 116, 255)) or (168, 116, 255))
            try:
                expires = int(residue.get("expires_tick", 0) or 0)
                created = int(residue.get("created_tick", expires) or expires)
                now = int(getattr(self.sim, "tick", 0) or 0)
            except (TypeError, ValueError):
                expires = created = now = 0
            span = max(1, expires - created)
            remaining = max(0, expires - now)
            strength = 0.06 + (0.16 * (float(remaining) / float(span)))
            tint = {
                "rgb": rgb,
                "strength": max(0.04, min(0.22, strength)),
                "pulse": str(profile.get("pulse", "") or "slow"),
                "profile": profile_key or "ritual_violet",
            }
            px = int(player_pos.x)
            py = int(player_pos.y)
            for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                wx = px + dx
                wy = py + dy
                if not _is_visible(wx, wy, active_z):
                    continue
                sx = wx - camera_x
                sy = wy - camera_y
                if 0 <= sx < map_w and 0 <= sy < map_h:
                    light_tint_drawer(sx, sy, tint, layer="fx", priority=-650)

        if zoom_mode == "overworld":
            player_cx, player_cy = _overworld_anchor_chunk()
            view_only = bool(getattr(self.sim, "overworld_view_only_by_eid", {}).get(int(self.player_eid), False))
            cursor_active = bool(look_ui.get("active")) and str(look_ui.get("mode", "")).lower() == "overworld"
            cursor_chunk = None
            if cursor_active:
                cursor_chunk = (
                    int(look_ui.get("chunk_x", player_cx)),
                    int(look_ui.get("chunk_y", player_cy)),
                )
            if view_only and cursor_chunk is not None:
                center_cx, center_cy = cursor_chunk
            else:
                center_cx, center_cy = player_cx, player_cy

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
            loaded = {(player_cx, player_cy)}
            knowledge = _overworld_chunk_knowledge(
                self.sim,
                self.player_eid,
                current_chunk=(player_cx, player_cy),
            )
            region_dim_attr = A_DIM
            fill_attrs = A_DIM
            unknown_fill_attrs = A_DIM
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
            badge_chunks = {(player_cx, player_cy)}
            badge_chunks.update(tuple(marker["chunk"]) for marker in markers)
            if cursor_chunk is not None and cursor_chunk != (player_cx, player_cy):
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

                    if (cx, cy) == (player_cx, player_cy):
                        focus_attr = A_BOLD
                        _draw_overworld_frame(cell_origin_x, cell_origin_y, "player", focus_attr, "overworld_focus", priority_base=-60)

                    if cursor_chunk is not None and (cx, cy) == cursor_chunk and (cx, cy) != (player_cx, player_cy):
                        selector_attr = A_BOLD
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
                                glyph_attrs = A_BOLD
                            else:
                                glyph_attrs = A_DIM
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

            player_gx = half_w + (int(player_cx) - int(center_cx))
            player_gy = half_h + (int(player_cy) - int(center_cy))
            if 0 <= player_gx < grid_w and 0 <= player_gy < grid_h:
                player_cell_origin_x = origin_x + (player_gx * cell_w)
                player_cell_origin_y = origin_y + (player_gy * cell_h)
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
                current_desc = self.sim.world.overworld_descriptor(player_cx, player_cy)
                current_interest = self.sim.world.overworld_interest(player_cx, player_cy, descriptor=current_desc)
                edge_header, edge_footer = _overworld_edge_legend_lines(
                    self.sim,
                    (player_cx, player_cy),
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
            # Hallucination strength is actor state, not tile state.  Resolve it
            # once for the frame; the per-tile helper still owns the seeded
            # spatial roll, so active hallucinations keep their exact pattern.
            tile_hallucination_intensity = hallucination_intensity(self.sim, self.player_eid)
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
                        attrs = A_DIM
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
                    self._draw_appearance(
                        sx,
                        sy,
                        appearance,
                        attrs=attrs,
                        visual_source=(wx, wy, active_z),
                    )
                    if visible_now:
                        hallucination = None
                        if tile_hallucination_intensity > 0.0:
                            hallucination = hallucinated_tile_visual(
                                self.sim,
                                self.player_eid,
                                wx,
                                wy,
                                active_z,
                                intensity=tile_hallucination_intensity,
                            )
                        if hallucination:
                            self._draw(
                                sx,
                                sy,
                                hallucination.get("glyph", "?"),
                                color=hallucination.get("color", "objective"),
                                attrs=attrs | A_BOLD,
                                semantic_id=hallucination.get("semantic_id", "hallucinated_tile"),
                                effects=("shimmer",),
                                layer="terrain",
                                priority=-850,
                            )
                        _draw_light_tint_overlay(sx, sy, wx, wy, active_z)
                        _draw_glare_wash_overlay(sx, sy, wx, wy, active_z)

            for flora in flora_records_in_rect(
                self.sim,
                camera_x,
                camera_y,
                camera_x + map_w - 1,
                camera_y + map_h - 1,
                z=active_z,
            ):
                wx = int(flora.get("x", -999999))
                wy = int(flora.get("y", -999999))
                wz = int(flora.get("z", 0))
                if wz != active_z:
                    continue
                if self.sim.detail_for_xy(wx, wy) == "unloaded":
                    continue
                if not _is_visible(wx, wy, active_z):
                    continue
                screen_x = wx - camera_x
                screen_y = wy - camera_y
                if not (0 <= screen_x < map_w and 0 <= screen_y < map_h):
                    continue
                data = flora_render_data(flora, sim=self.sim)
                appearance = self.sim.appearance.snapshot(
                    data["glyph"],
                    color=data["color"],
                    semantic_id=data["semantic_id"],
                    preferred_categories=("flora",),
                    layer=data["layer"],
                    priority=data["priority"],
                    effects=data.get("effects", ()),
                )
                attrs = _ambient_attr(wx, wy, active_z)
                self._draw_appearance(
                    screen_x,
                    screen_y,
                    appearance,
                    attrs=attrs,
                    light_tint=_surface_light_tint(wx, wy, active_z),
                    visual_source=(wx, wy, active_z),
                )

            active_quest_target = active_final_operation_target_property_id(self.sim)

            visible_properties = self.sim.properties_in_rect(
                camera_x - 1,
                camera_y - 1,
                camera_x + map_w,
                camera_y + map_h,
                active_z,
                include_covering=True,
            )
            for prop in visible_properties:
                prop_id = str(prop.get("id", "") or "").strip()
                occupied_choice = occupied_vehicle_choices.get(prop_id)
                if occupied_choice is not None:
                    _choice_key, occupant_eid, _state, _vehicle_prop, occupant_pos = occupied_choice
                    if occupant_eid == self.player_eid or _is_visible(occupant_pos.x, occupant_pos.y, occupant_pos.z):
                        continue
                display_pos = _property_display_position(prop, active_quest_target=active_quest_target)
                if not display_pos:
                    continue
                if int(display_pos[2]) != int(active_z):
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
                appearance = self.sim.appearance.property(
                    prop,
                    active_quest_target=active_quest_target,
                )
                if str(prop.get("kind", "") or "").strip().lower() == "vehicle":
                    appearance = _vehicle_appearance_with_heading(appearance, vehicle_property_heading(prop))
                if (
                    str(prop.get("kind", "") or "").strip().lower() != "vehicle"
                    and _tile_prefers_feature_legend(self.sim, tile, display_pos[0], display_pos[1], active_z)
                    and str(getattr(appearance, "semantic_id", "") or "").strip().lower()
                    not in {"prop_vehicle_onramp"}
                ):
                    continue

                if (
                    active_vehicle_prop
                    and str(prop_id) == str(active_vehicle_prop.get("id", "") or "").strip()
                    and player_vehicle_state
                ):
                    appearance = _vehicle_appearance_with_heading(appearance, player_vehicle_state)
                if visible_now:
                    attrs = _ambient_attr(display_pos[0], display_pos[1], active_z)
                else:
                    attrs = A_DIM
                self._draw_appearance(
                    screen_x,
                    screen_y,
                    appearance,
                    attrs=attrs,
                    light_tint=_surface_light_tint(display_pos[0], display_pos[1], active_z) if visible_now else None,
                )

            visible_ground_items = self.sim.ground_items_in_rect(
                camera_x,
                camera_y,
                camera_x + map_w - 1,
                camera_y + map_h - 1,
                active_z,
            )
            for ground in visible_ground_items:
                screen_x = ground["x"] - camera_x
                screen_y = ground["y"] - camera_y
                if not (0 <= screen_x < map_w and 0 <= screen_y < map_h):
                    continue
                if self.sim.detail_for_xy(ground["x"], ground["y"]) == "unloaded":
                    continue
                if not _is_visible(ground["x"], ground["y"], active_z):
                    continue

                item_def = ITEM_CATALOG.get(ground["item_id"], {})
                appearance = self.sim.appearance.item(item_def, metadata=ground.get("metadata"))
                attrs = A_BOLD | _ambient_attr(ground["x"], ground["y"], active_z)
                self._draw_appearance(
                    screen_x,
                    screen_y,
                    appearance,
                    attrs=attrs,
                    light_tint=_surface_light_tint(ground["x"], ground["y"], active_z),
                )

            for record in tuple(getattr(self.sim, "hunting_carcasses", {}).values()):
                if bool(record.get("harvested")):
                    continue
                wx = int(record.get("x", -999999))
                wy = int(record.get("y", -999999))
                wz = int(record.get("z", 0))
                if wz != active_z:
                    continue
                screen_x = wx - camera_x
                screen_y = wy - camera_y
                if not (0 <= screen_x < map_w and 0 <= screen_y < map_h):
                    continue
                if self.sim.detail_for_xy(wx, wy) == "unloaded":
                    continue
                if not _is_visible(wx, wy, active_z):
                    continue
                if not hunting_carcasses_at(self.sim, wx, wy, wz):
                    continue
                appearance = self.sim.appearance.snapshot(
                    "%",
                    color="item_food",
                    semantic_id="item_food",
                    preferred_categories=("items",),
                    layer="item",
                    priority=40,
                )
                attrs = A_BOLD | _ambient_attr(wx, wy, active_z)
                self._draw_appearance(screen_x, screen_y, appearance, attrs=attrs, light_tint=_surface_light_tint(wx, wy, active_z))

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
                    light_tint=_surface_light_tint(wx, wy, active_z),
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
                if eid in hidden_vehicle_occupants and eid not in occupied_vehicle_by_driver:
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
                occupied_vehicle = occupied_vehicle_by_driver.get(eid)
                if occupied_vehicle:
                    occupant_vehicle_state, occupant_vehicle_prop = occupied_vehicle
                    appearance = self.sim.appearance.property(
                        occupant_vehicle_prop,
                        active_quest_target=active_quest_target,
                    )
                    appearance = _vehicle_appearance_with_heading(appearance, occupant_vehicle_state)
                else:
                    appearance = _entity_render_style(self.sim, eid, player_eid=self.player_eid)
                attrs = _actor_ambient_attr(_pos.x, _pos.y, _pos.z)
                if _entity_should_blink_in_combat(self.sim, eid, player_eid=self.player_eid):
                    appearance = _appearance_with_effect(appearance, "blink")
                elif _entity_should_mark_ambient_combat(self.sim, eid, player_eid=self.player_eid):
                    appearance = _appearance_with_effect(appearance, "combat_ambient")
                    attrs |= A_BOLD
                fire_cell = fire_cell_state(self.sim, _pos.x, _pos.y, _pos.z)
                if isinstance(fire_cell, dict) and int(fire_cell.get("fire_intensity", 0) or 0) > 0:
                    appearance = _appearance_with_effect(appearance, "blink")
                self._draw_appearance(
                    screen_x,
                    screen_y,
                    appearance,
                    attrs=attrs,
                    light_tint=_surface_light_tint(_pos.x, _pos.y, _pos.z),
                )

            radio_scan = getattr(self.sim, "world_traits", {}).get("justice_radio_scan", {})
            if isinstance(radio_scan, dict) and int(radio_scan.get("expires_tick", -1) or -1) >= int(getattr(self.sim, "tick", 0)):
                ping_attr = A_BOLD | A_REVERSE
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

            aim_lock_target_eid, aim_lock_target_pos = _aim_lock_target_pos()
            if (
                ((look_ui.get("active") and look_purpose == "aim") or aim_lock_target_pos is not None)
                and player_pos
            ):
                preview_x = int(look_ui.get("x", player_pos.x))
                preview_y = int(look_ui.get("y", player_pos.y))
                preview_z = int(look_ui.get("z", active_z))
                if aim_lock_target_pos is not None and not (look_ui.get("active") and look_purpose == "aim"):
                    preview_x = int(aim_lock_target_pos.x)
                    preview_y = int(aim_lock_target_pos.y)
                    preview_z = int(aim_lock_target_pos.z)
                preview = _manual_fire_preview(
                    self.sim,
                    eid=self.player_eid,
                    x=preview_x,
                    y=preview_y,
                    z=preview_z,
                )
                projectile_glyph = str(preview.get("projectile_glyph", "."))[:1] or "."
                dim_attr = A_DIM
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

            if aim_lock_target_pos is not None:
                sx = int(aim_lock_target_pos.x) - camera_x
                sy = int(aim_lock_target_pos.y) - camera_y
                if 0 <= sx < map_w and 0 <= sy < map_h and _is_visible(aim_lock_target_pos.x, aim_lock_target_pos.y, active_z):
                    appearance = self.sim.appearance.marker(
                        "X",
                        "X",
                        color="projectile",
                        layer="ui_overlay",
                        priority=95,
                    )
                    self._draw_appearance(
                        sx,
                        sy,
                        appearance,
                        attrs=A_REVERSE | A_BOLD,
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
                            attrs = A_REVERSE
                            if not visible_now:
                                attrs |= A_DIM
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
            _draw_dream_residue_overlay()
            if world_view_started:
                end_world_view = getattr(self.view, "end_world_view", None)
                if callable(end_world_view):
                    end_world_view()
                world_view_started = False
            map_w = map_view_w
            map_h = map_view_h
            residue = dream_residue_state(self.sim)
            residue_line = str((residue or {}).get("mood_line", "") or "").strip()
            if residue_line:
                self._draw_dream_residue_mood_line(residue_line, map_w, map_h)

        chunk = getattr(self.sim, "active_chunk", {})
        if not isinstance(chunk, dict):
            chunk = {}
        district = chunk.get("district", {})
        if not isinstance(district, dict):
            district = {}
        area_type = district.get("area_type", "city")
        district_type = district.get("district_type", "unknown")
        security = district.get("security_level", "?")
        if zoom_mode == "overworld":
            map_chunk = _overworld_anchor_chunk()
            map_desc = self.sim.world.overworld_descriptor(map_chunk[0], map_chunk[1])
            area_type = map_desc.get("area_type", "city")
            district_type = map_desc.get("district_type", "unknown")
            security = "?"

        assets = self.sim.ecs.get(PlayerAssets).get(self.player_eid)
        player_needs = self.sim.ecs.get(NPCNeeds).get(self.player_eid)
        credits = assets.credits if assets else 0
        owned = len(assets.owned_property_ids) if assets else 0
        inventory = inventories.get(self.player_eid)
        finance = financials.get(self.player_eid)
        loadout = loadouts.get(self.player_eid)
        armor_loadout = self.sim.ecs.get(ArmorLoadout).get(self.player_eid)
        vitality = vitalities.get(self.player_eid)
        carried_slots = inventory.slot_count() if inventory else 0
        status_effects = effects_map.get(self.player_eid)
        active_status_count = len(status_effects.active) if status_effects else 0
        active_status_summary = _active_status_summary(status_effects, max_names=1, title=True)
        player_cover = covers.get(self.player_eid)
        player_modes = modes.get(self.player_eid)
        active_disguise = getattr(self.sim, "disguise_state", None)
        weapon_summary = _hud_weapon_summary(loadout)
        armor_summary = _hud_armor_summary(armor_loadout)
        hp_text = "?"
        if vitality:
            hp_text = f"{vitality.hp}/{vitality.max_hp}"
        downed_lines = []
        if vitality and bool(getattr(vitality, "downed", False)):
            try:
                downed_tick = int(getattr(vitality, "downed_tick", self.sim.tick))
            except (TypeError, ValueError):
                downed_tick = int(getattr(self.sim, "tick", 0))
            bleedout_ticks = max(1, _int_or_default(getattr(self.sim, "player_bleedout_ticks", 8), 8))
            remaining = max(0, bleedout_ticks - max(0, int(getattr(self.sim, "tick", 0)) - downed_tick))
            downed_lines = _wrap_display_lines(
                self._hud_styled_chunk(f"Downed: bleeding out {remaining}t"),
                hud_text_w,
                max_lines=1,
            )

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
        aim_lock_target_eid, aim_lock_target_pos = _aim_lock_target_pos()
        if not bool(look_ui.get("active")) and aim_lock_target_eid is not None and aim_lock_target_pos is not None:
            target_name = self._npc_label(aim_lock_target_eid)
            condition = _target_condition_descriptor(
                self.sim,
                self.player_eid,
                aim_lock_target_eid,
                include_uncertainty=True,
            )
            lock_text = f"Aim lock {target_name}"
            if condition:
                lock_text = f"{lock_text} ({condition})"
            status_chunks.append(lock_text)
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
            player_glare = lighting_state.get("player_glare")
            try:
                glare_pct = int(round(float(player_glare.get("strength", 0.0) if isinstance(player_glare, dict) else 0.0) * 100.0))
            except (TypeError, ValueError):
                glare_pct = 0
            if glare_pct > 0:
                status_chunks.append(f"Glare {max(1, min(100, glare_pct))}%")
        else:
            status_chunks.append(f"Light out {outside_pct}%")
        if isinstance(active_disguise, dict):
            role_text = _disguise_role_label(active_disguise.get("role_id"), title_case=True)
            try:
                strength_pct = int(round(float(active_disguise.get("strength", 0.0)) * 100.0))
            except (TypeError, ValueError):
                strength_pct = 0
            status_chunks.append(f"Cover {role_text} {max(0, strength_pct)}%")
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
            pursuit_count = overlay.get("pursuit_target_count", 0)
            nearest = overlay.get("nearest_threat_dist")
            nearest_text = "?" if nearest is None else str(nearest)
            exposure = int(float(overlay.get("player_exposure", 1.0)) * 100)
            if ambient_count or pursuit_count:
                parts = []
                if direct_count:
                    parts.append(f"{direct_count} direct")
                if ambient_count:
                    parts.append(f"{ambient_count} nearby")
                if pursuit_count:
                    parts.append(f"{pursuit_count} pursuit")
                threat_label = " + ".join(parts) if parts else str(threat_count)
            else:
                threat_label = str(threat_count)
            status_chunks.append(
                f"Combat threats {threat_label} near {nearest_text} exp {exposure}%"
            )
        if active_vehicle_prop:
            fuel, fuel_capacity = _vehicle_fuel_values(active_vehicle_prop)
            in_vehicle = bool(player_vehicle_state and player_vehicle_state.in_vehicle)
            mode_text = "driving" if in_vehicle else "parked"
            vehicle_bits = [f"Vehicle {mode_text} F{fuel}/{fuel_capacity}"]
            if in_vehicle:
                vehicle_bits.append(f"H{vehicle_heading_label(player_vehicle_state)}")
                vehicle_bits.append(f"S{int(getattr(player_vehicle_state, 'speed', 0) or 0)}")
                vehicle_bits.append("Lt on" if bool(getattr(player_vehicle_state, "headlights_on", True)) else "Lt off")
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
            elif look_purpose == "throw":
                label = "Throw"
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
        status_lines = _flow_display_chunks(
            (self._hud_styled_chunk(chunk) for chunk in status_chunks),
            hud_text_w,
            max_lines=3,
        )

        streamed_chunks = [
            f"Chunks {len(self.sim.chunk_detail)}",
            f"Active {sum(1 for detail in self.sim.chunk_detail.values() if detail == 'active')}",
            f"Entities {len(self.sim.tilemap.entities_on_floor(active_z))}",
        ]
        streamed_lines = []
        overworld_rail_chunks = []
        if zoom_mode == "overworld":
            current_chunk = _overworld_anchor_chunk()
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

            def _title(raw):
                text = str(raw or "").replace("_", " ").strip()
                return text.title() if text else "-"

            area = str(desc.get("area_type", "city")).strip().lower() or "city"
            district = str(desc.get("district_type", "residential")).strip().lower() or "residential"
            terrain = str(desc.get("terrain", "")).strip().lower()
            path = str(desc.get("path", "")).strip().lower() or "-"
            marker_distance = None
            if markers:
                try:
                    marker_distance = min(
                        _manhattan(
                            int(current_chunk[0]),
                            int(current_chunk[1]),
                            int(marker["chunk"][0]),
                            int(marker["chunk"][1]),
                        )
                        for marker in markers
                    )
                except (KeyError, TypeError, ValueError, IndexError):
                    marker_distance = None
            marker_text = (
                f"{len(markers)} near {marker_distance if marker_distance is not None else '?'}c"
                if markers
                else "0"
            )
            overworld_rail_chunks = [
                f"Chunk {int(current_chunk[0])},{int(current_chunk[1])}",
                f"Area {_title(area)}",
            ]
            if area == "city":
                overworld_rail_chunks.append(f"District {_title(district)}")
            elif terrain:
                overworld_rail_chunks.append(f"Terrain {_title(terrain)}")
            overworld_rail_chunks.extend([
                f"Path {_title(path) if path != '-' else '-'}",
                f"Travel {_overworld_travel_tax_text(travel)}",
                f"Markers {marker_text}",
            ])
        else:
            streamed_lines = _flow_text_chunks(
                streamed_chunks,
                hud_text_w,
                max_lines=1,
            )

        resource_chunks = [
            f"Cr {credits}",
            f"Inv {carried_slots}/{inventory.capacity if inventory else 0}",
            f"HP {hp_text}",
        ]
        if player_needs:
            ensure_sleep_needs(player_needs)
            resource_chunks.extend(_survival_indicator_chunks(player_needs, rich=True))
        pressure = _pressure_snapshot(self.sim)
        pressure_tier = str(pressure.get("tier", "low")).strip().lower()
        pressure_attention = int(pressure.get("attention", 0))
        resource_chunks.append(f"Heat {pressure_tier} {pressure_attention}")
        if player_needs:
            wake_text = f"Wake {float(getattr(player_needs, 'wakefulness', 100.0)):.0f}"
            reserve_hours = chemical_wake_reserve_hours(player_needs)
            if reserve_hours >= 0.05:
                wake_text += f"+{reserve_hours:.1f}h"
            resource_chunks.append(wake_text)
            resource_chunks.append(
                f"Needs E{player_needs.energy:.0f}/S{player_needs.safety:.0f}/So{player_needs.social:.0f}"
            )
        if active_status_count:
            resource_chunks.append(f"Status {active_status_summary}")
        gear_chunks = []
        if active_vehicle_prop:
            fuel, fuel_capacity = _vehicle_fuel_values(active_vehicle_prop)
            gear_chunks.append(f"Vehicle F{fuel}/{fuel_capacity}")
            if player_vehicle_state and bool(getattr(player_vehicle_state, "in_vehicle", False)):
                gear_chunks.append(
                    f"Drive H{vehicle_heading_label(player_vehicle_state)} "
                    f"S{int(getattr(player_vehicle_state, 'speed', 0) or 0)} "
                    f"{'Lt on' if bool(getattr(player_vehicle_state, 'headlights_on', True)) else 'Lt off'}"
                )
        gear_chunks.extend([
            weapon_summary,
            armor_summary,
        ])
        if player_cover:
            if player_cover.active:
                cover_text = f"{player_cover.cover_kind.upper()} {int(player_cover.cover_value * 100)}%"
                cover_source = _cover_source_label(self.sim, player_cover, short=True)
            else:
                cover_text = "NONE"
                cover_source = "-"
            gear_chunks.extend([
                f"Cover {cover_text}",
                f"Exp {int(player_cover.exposure * 100)}%",
                f"Threats {player_cover.threat_count}",
                f"Via {cover_source}",
            ])
        economy_chunks = list(resource_chunks) + list(gear_chunks)
        economy_lines = _flow_display_chunks(
            (self._hud_styled_chunk(chunk) for chunk in economy_chunks),
            hud_text_w,
            max_lines=3,
        )

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

        report_hint_line = ""

        if look_ui.get("active"):
            look_entry = look_ui.get("inspect_text", "")
            look_text = _line_text(look_entry).strip()
            if look_text:
                report_hint_line = self._look_focus_header_line(
                    look_ui,
                    look_purpose,
                    active_z=active_z,
                    zoom_mode=zoom_mode,
                )
            else:
                if look_purpose == "aim":
                    report_hint_line = "Aim mode active."
                elif look_purpose == "interact":
                    report_hint_line = "Interact target mode active."
                elif look_purpose == "talk":
                    report_hint_line = "Talk target mode active."
                else:
                    report_hint_line = "Look mode active."
            quest_lines = _wrap_display_lines(report_hint_line, hud_text_w, max_lines=1)
        else:
            quest_lines = []
            if objective_line and len(quest_lines) < 2:
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
                        self._hud_styled_chunk(opportunity_line),
                        hud_text_w,
                        max_lines=1,
                    )
                )
            quest_lines = quest_lines[:2]

        read_state = getattr(self.sim, "situation_read_state", {})
        read_text = ""
        if isinstance(read_state, dict):
            read_text = str(read_state.get("text", "") or "").strip()
        read_lines = []
        if read_text:
            read_lines = _wrap_display_lines(
                self._hud_styled_chunk(read_text),
                hud_text_w,
                max_lines=1,
            )

        mode_line = _mode_line(
            mode_state=player_modes,
            cover=player_cover,
            look_active=bool(look_ui.get("active")) and look_purpose != "aim",
            aim_active=(bool(look_ui.get("active")) and look_purpose == "aim")
            or (isinstance(aim_lock_ui, dict) and bool(aim_lock_ui.get("active"))),
            turn_mode=_combat_turn_pacing_active(self.sim),
            stealth_state=getattr(self.sim, "player_stealth_state", None),
            intrusion_state=getattr(self.sim, "player_intrusion_state", None),
        )
        state_rail_sections = []
        if side_rail_visible:
            _rail_body_cell_w, rail_text_w = _modal_body_widths(self.view, rail_w, horizontal_padding=4, min_width=1)

            def _rail_chunk_lines(chunks, *, max_lines):
                return _flow_display_chunks(
                    (self._hud_styled_chunk(chunk) for chunk in chunks),
                    rail_text_w,
                    max_lines=max_lines,
                )

            rail_mode_lines = []
            if downed_lines:
                rail_mode_lines.extend(
                    _wrap_display_lines(
                        self._hud_styled_chunk(_line_text(downed_lines[0])),
                        rail_text_w,
                        max_lines=1,
                    )
                )
            rail_mode_lines.extend(_wrap_display_lines(mode_line, rail_text_w, max_lines=2))

            rail_run_lines = []
            if look_ui.get("active"):
                rail_run_lines.extend(_wrap_display_lines(report_hint_line, rail_text_w, max_lines=1))
            else:
                if objective_line and len(rail_run_lines) < 3:
                    rail_run_lines.extend(_wrap_display_lines(objective_line, rail_text_w, max_lines=1))
                if final_operation_line and len(rail_run_lines) < 3:
                    rail_run_lines.extend(_wrap_display_lines(final_operation_line, rail_text_w, max_lines=1))
                if show_opportunity_line and len(rail_run_lines) < 3:
                    rail_run_lines.extend(
                        _wrap_display_lines(
                            self._hud_styled_chunk(opportunity_line),
                            rail_text_w,
                            max_lines=1,
                        )
                    )
            if read_text and len(rail_run_lines) < 4:
                read_max_lines = min(2, max(1, 4 - len(rail_run_lines)))
                rail_run_lines.extend(
                    _wrap_display_lines(
                        self._hud_styled_chunk(read_text),
                        rail_text_w,
                        max_lines=read_max_lines,
                    )
                )

            scene_chunks = [
                chunk
                for chunk in status_chunks
                if not str(_line_text(chunk)).strip().lower().startswith("vehicle ")
            ]
            state_rail_sections = [
                {"id": "mode", "title": "Mode", "lines": rail_mode_lines},
                {"id": "run", "title": "Run", "lines": rail_run_lines[:4]},
                {"id": "body", "title": "Body", "lines": _rail_chunk_lines(resource_chunks, max_lines=6)},
                {"id": "gear", "title": "Gear", "lines": _rail_chunk_lines(gear_chunks, max_lines=6)},
                {
                    "id": "streamed",
                    "title": "Map",
                    "lines": _rail_chunk_lines(overworld_rail_chunks, max_lines=5) if zoom_mode == "overworld" else [],
                },
                {"id": "scene", "title": "Scene", "lines": _rail_chunk_lines(scene_chunks, max_lines=7)},
            ]
            state_rail_sections = [
                section
                for section in state_rail_sections
                if list(section.get("lines", ()) or ())
            ]
        wrapped_sections_spec = [
            {
                "id": "mode",
                "lines": _wrap_display_lines(mode_line, hud_text_w, max_lines=2),
                "min_lines": 1,
                "trim_priority": 0,
            },
            {
                "id": "downed",
                "lines": downed_lines,
                "min_lines": 1,
                "trim_priority": 0,
            },
            {
                "id": "quest",
                "lines": quest_lines,
                "min_lines": 1,
                "trim_priority": 1,
            },
            {
                "id": "read",
                "lines": read_lines,
                "min_lines": 1,
                "trim_priority": 1,
            },
            {
                "id": "economy",
                "lines": economy_lines,
                "min_lines": 1,
                "trim_priority": 2,
            },
            {
                "id": "status",
                "lines": status_lines,
                "min_lines": 1,
                "trim_priority": 3,
            },
            {
                "id": "streamed",
                "lines": streamed_lines,
                "min_lines": 1,
                "trim_priority": 5,
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

        hud_y = map_h
        if side_rail_visible:
            self._update_hud_flash_state(state_rail_sections)
            self._draw_state_rail(
                rail_x=rail_x,
                rail_y=0,
                rail_w=rail_w,
                rail_h=map_h,
                modal_theme=modal_theme,
                sections=state_rail_sections,
            )
        elif side_layout_supported:
            self._update_hud_flash_state(())
        else:
            self._update_hud_flash_state(wrapped_sections)
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

        self._draw_look_focus_card(
            look_ui,
            look_purpose,
            map_w=map_w,
            map_h=map_h,
            active_z=active_z,
            zoom_mode=zoom_mode,
            panels_open=blocking_panel_open,
        )
        self._draw_drone_command_card(
            drone_command_ui,
            map_w=map_w,
            map_h=map_h,
            modal_theme=modal_theme,
        )
        self._draw_drone_sheet_modal(
            drone_sheet_ui,
            screen_w=screen_w,
            map_h=map_h,
            modal_theme=modal_theme,
        )
        self._draw_wire_kit_modal(
            wire_kit_ui,
            screen_w=screen_w,
            map_h=map_h,
            modal_theme=modal_theme,
        )
        self._draw_wire_connection_modal(
            wire_connection_ui,
            screen_w=screen_w,
            map_h=map_h,
            modal_theme=modal_theme,
        )
        self._draw_wire_scene_modal(
            wire_scene_ui,
            screen_w=screen_w,
            map_h=map_h,
            modal_theme=modal_theme,
        )
        if (
            isinstance(action_menu_ui, dict)
            and bool(action_menu_ui.get("open"))
            and zoom_mode != "overworld"
            and player_pos is not None
        ):
            self._draw_action_menu(
                action_menu_ui,
                player_screen_x=(int(player_pos.x) - int(camera_x)) * requested_world_magnification,
                player_screen_y=(int(player_pos.y) - int(camera_y)) * requested_world_magnification,
                map_w=map_w,
                map_h=map_h,
                modal_theme=modal_theme,
            )
        elif isinstance(action_menu_ui, dict) and bool(action_menu_ui.get("open")):
            self._draw_action_menu(
                action_menu_ui,
                player_screen_x=max(0, map_w // 2),
                player_screen_y=max(0, map_h // 2),
                map_w=map_w,
                map_h=map_h,
                modal_theme=modal_theme,
            )

        if inventory_ui.get("open"):
            panel_w = _modal_panel_width(screen_w, fraction=0.75, min_width=48)
            panel_x = max(0, (screen_w - panel_w) // 2)
            panel_h = max(8, min(map_h, int(round(map_h * 0.75))))
            panel_y = max(0, (map_h - panel_h) // 2)
            body_cell_w, body_w = _modal_body_widths(self.view, panel_w)
            _row_cell_w, row_w = _modal_body_widths(self.view, panel_w, horizontal_padding=2)

            def _clip(text, width):
                if width <= 0:
                    return ""
                if len(text) <= width:
                    return text
                if width <= 3:
                    return text[:width]
                return text[: width - 3] + "..."

            self._draw_modal_frame(panel_x, panel_y, panel_w, panel_h, modal_theme)

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
                if panel_kind == "container" and container_kind == CAMPFIRE_HERB_CACHE_KIND:
                    entries = [
                        entry
                        for entry in entries
                        if entry_allowed_in_container(entry, container_kind=container_kind, item_catalog=ITEM_CATALOG)
                    ]
            if inventory_panel_entries_sortable(panel_kind, container_view):
                entries = sort_inventory_entries(
                    self.sim,
                    self.player_eid,
                    entries,
                    sort_mode=inventory_ui.get("sort_mode", "default"),
                    item_catalog=ITEM_CATALOG,
                )
            if entries:
                selected_index = int(inventory_ui.get("selected_index", 0))
                selected_index = max(0, min(selected_index, len(entries) - 1))
                inventory_ui["selected_index"] = selected_index
            else:
                inventory_ui["selected_index"] = 0
                selected_index = 0

            header = f" {panel_title} "
            self.view.draw_text(panel_x + 2, panel_y, _clip(header, body_w), color=self._theme_color(modal_theme, "title"))

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
                    max_count = container_capacity if container_capacity > 0 else PlayerActionSystem.CACHE_MAX_STACKS
                    container_count_text = f"{container_label} {container_count}/{max_count}"
                else:
                    if property_id:
                        container_count = _property_runtime_container_entry_count(
                            self.sim,
                            property_id,
                            container_kind=container_kind,
                        )
                    if container_capacity > 0:
                        container_count_text = f"{container_label} {container_count}/{container_capacity}"
                    else:
                        container_count_text = f"{container_label} {container_count}"
                if container_kind == "worn":
                    pack_entries = (
                        _inventory_entries_loose_for_container(inv, container_instance_id)
                        if inv and container_instance_id
                        else (list(inv.items) if inv else [])
                    )
                else:
                    pack_entries = list(inv.items) if inv else []
                    if container_kind == CAMPFIRE_HERB_CACHE_KIND:
                        pack_entries = [
                            entry
                            for entry in pack_entries
                            if entry_allowed_in_container(entry, container_kind=container_kind, item_catalog=ITEM_CATALOG)
                        ]
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
            if inventory_panel_entries_sortable(panel_kind, container_view):
                slot_line += f" | Sort {inventory_sort_label(inventory_ui.get('sort_mode', 'default'))}"
            self.view.draw_text(panel_x + 2, panel_y + 1, _clip(slot_line, body_w), color=self._theme_color(modal_theme, "muted"))

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

            inspect_max_lines = max(1, min(6, panel_h - 7))
            inspect_lines = list(
                _wrap_display_lines(inspect_text, body_w, max_lines=inspect_max_lines)
                or [""]
            )
            list_y = panel_y + 2
            list_h = max(1, panel_h - 5 - len(inspect_lines))

            start = 0
            if selected_index >= list_h:
                start = selected_index - list_h + 1

            visible_entries = entries[start: start + list_h]
            armor_loadout = self.sim.ecs.get(ArmorLoadout).get(self.player_eid)
            weapon_loadout = self.sim.ecs.get(WeaponLoadout).get(self.player_eid)
            active_disguise = getattr(self.sim, "disguise_state", None)
            equipped_container = getattr(self.sim, "equipped_container", None)
            compatibility_target_class = drone_compatibility_target(self.sim)
            for idx, entry in enumerate(visible_entries):
                absolute = start + idx
                marker = ">" if absolute == selected_index else " "
                item_def = ITEM_CATALOG.get(entry["item_id"], {})
                glyph = item_def.get("glyph", "*")
                name = item_display_name_for_actor(self.sim, self.player_eid, entry, item_catalog=ITEM_CATALOG)
                gear_marker = ""
                row_color = None
                entry_instance_id = str(entry.get("instance_id", "") or "").strip()
                stowed_container_instance = _entry_stowed_container_instance(entry)
                if panel_kind != "container" or container_view == "pack":
                    if armor_loadout and armor_loadout.is_equipped(entry_instance_id):
                        gear_marker = "A"
                        row_color = "inventory_equipped_consequence"
                    elif (
                        isinstance(active_disguise, dict)
                        and str(active_disguise.get("instance_id", "")).strip() == entry_instance_id
                    ):
                        gear_marker = "K"
                        row_color = "inventory_equipped_consequence"
                    if not gear_marker and weapon_loadout:
                        weapon_id = _item_weapon_id(item_def)
                        instance = weapon_loadout.weapon_instances.get(weapon_id, {}) if weapon_id else {}
                        if (
                            weapon_id
                            and weapon_loadout.current_weapon() == weapon_id
                            and isinstance(instance, dict)
                            and str(instance.get("inventory_instance_id", "")).strip() == entry_instance_id
                        ):
                            gear_marker = "W"
                            row_color = "inventory_equipped_weapon"
                    if (
                        not gear_marker
                        and isinstance(equipped_container, dict)
                        and str(equipped_container.get("instance_id", "")).strip() == entry_instance_id
                    ):
                        gear_marker = "C"
                if (
                    panel_kind == "container"
                    and container_kind == "worn"
                    and container_view == "container"
                    and row_color is None
                ):
                    row_color = _INVENTORY_STOWED_ITEM_COLOR
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
                    if stowed_container_instance:
                        storage_suffix = " [stowed]"
                        if row_color is None:
                            row_color = _INVENTORY_STOWED_ITEM_COLOR
                worn_suffix = ""
                if (panel_kind != "container" or container_view == "pack") and is_entry_worn(entry):
                    worn_suffix = " [worn]"
                    if row_color is None:
                        row_color = "inventory_equipped_clothing"
                if _inventory_entry_is_key_item(entry, item_def):
                    row_color = _INVENTORY_KEY_ITEM_COLOR
                elif _inventory_entry_is_critical_quest_item(entry):
                    row_color = _INVENTORY_CRITICAL_QUEST_ITEM_COLOR
                compatibility = compatibility_row_fields(
                    item_def,
                    target_chassis_class=compatibility_target_class,
                )
                compatibility_mark = str(compatibility.get("compatibility_mark", "") or "")[:5]
                class_band = str(compatibility.get("drone_class_band", "") or "")[:4]
                row_prefix = f"{marker}{absolute + 1:02d}{gear_marker:>1} {glyph} "
                compatibility_color = compatibility.get("compatibility_color")
                suffix = f"{name} x{entry['quantity']}{ammo_suffix}{worn_suffix}{storage_suffix}"
                restraint_indicator = ""
                restraint_indicator_color = row_color
                if str(entry.get("item_id", "") or "").strip().lower() == "field_restraint_jab":
                    restraint_status = bounty_restraint_jab_status(self.sim, self.player_eid, entry)
                    lit = bool(
                        restraint_status.get("active")
                        and restraint_status.get("target_live")
                        and restraint_status.get("near_target")
                    )
                    restraint_indicator = " [●]" if lit else " [○]"
                    restraint_indicator_color = "property_service" if lit else "human_slate"
                # Keep compatibility marks in one proportional-text flow.
                # Drawing the complete label and then repainting a mark at a
                # character-count offset duplicated it beside the item name in
                # Pygame, whose UI font advances by measured pixel width.
                self.view.draw_segments(
                    panel_x + 1,
                    list_y + idx,
                    (
                        _segment(row_prefix, color=row_color),
                        _segment(f"{compatibility_mark:<5}", color=compatibility_color or row_color),
                        _segment(f"{class_band:<4} ", color=compatibility_color or row_color),
                        _segment(suffix, color=row_color),
                        _segment(restraint_indicator, color=restraint_indicator_color),
                    ),
                    max_width=row_w,
                )

            if not entries:
                empty_label = "(empty)"
                if panel_kind == "container":
                    empty_label = f"({container_label.lower()} empty)" if container_view == "container" else "(pack empty)"
                self.view.draw_text(panel_x + 2, list_y, _clip(empty_label, body_w))

            inspect_y = panel_y + panel_h - 2 - len(inspect_lines)
            for line_offset, inspect_line in enumerate(inspect_lines):
                self._draw_display_line(
                    panel_x + 2,
                    inspect_y + line_offset,
                    inspect_line,
                    body_cell_w,
                )
            if panel_kind == "container":
                hint = (
                    f"U transfer  Left/Right or Tab switch {container_label.lower()}/pack  "
                    f"S sort pack  E inspect  O ops  Y notebooks  L log  D debug  I close"
                )
            else:
                hint = "U use/equip/stow  R drop  S sort  E inspect  O ops  Y notebooks  L log  D debug  I close"
            hint = release_control_text(hint, self.sim)
            self.view.draw_text(panel_x + 2, panel_y + panel_h - 2, _clip(hint, body_w), color=self._theme_color(modal_theme, "footer"))
            self._draw_inventory_inspect_modal(
                inventory_ui,
                screen_w=screen_w,
                map_h=map_h,
                modal_theme=modal_theme,
            )
        elif trade_ui.get("open"):
            panel_w = _modal_panel_width(screen_w, fraction=0.75, min_width=52)
            panel_x = max(0, (screen_w - panel_w) // 2)
            panel_h = max(8, min(map_h, int(round(map_h * 0.75))))
            panel_y = max(0, (map_h - panel_h) // 2)
            body_cell_w, body_w = _modal_body_widths(self.view, panel_w)
            _row_cell_w, row_w = _modal_body_widths(self.view, panel_w, horizontal_padding=2)

            def _clip(text, width):
                if width <= 0:
                    return ""
                if len(text) <= width:
                    return text
                if width <= 3:
                    return text[:width]
                return text[: width - 3] + "..."

            self._draw_modal_frame(panel_x, panel_y, panel_w, panel_h, modal_theme)

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
            target_class = str(trade_ui.get("compatibility_target_class", "") or "").strip().upper()
            target_label = str(trade_ui.get("compatibility_target_label", "") or "").strip()
            if target_class:
                panel_bits.append(f"target {target_label or (target_class + '-class drone')}")
            store_line = store_name if not panel_bits else f"{store_name} [{' | '.join(panel_bits)}]"

            header = f" Trade {mode_label} "
            self.view.draw_text(panel_x + 2, panel_y, _clip(header, body_w), color=self._theme_color(modal_theme, "title"))
            self.view.draw_text(panel_x + 2, panel_y + 1, _clip(store_line, body_w), color=self._theme_color(modal_theme, "muted"))

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
                compatibility_mark = str(row.get("compatibility_mark", "") or "")[:5]
                class_band = str(row.get("drone_class_band", "") or "")[:4]
                base_prefix = f"{marker}{absolute + 1:02d} {glyph} "
                item_name = str(row.get("item_name", row.get("item_id", "item")))
                price = int(row.get("price", 0))
                action_label = str(row.get("action_label", "")).strip().lower()
                equipment_badge = ""
                if mode == "buy":
                    stock = int(row.get("stock", 0))
                    badge = str(row.get("row_badge", "") or "").strip()
                    badge_text = f" {badge}" if badge else ""
                    if action_label:
                        row_suffix = f" {action_label} stk {stock}{badge_text}"
                    else:
                        row_suffix = f" {price}c stk {stock}{badge_text}"
                else:
                    qty = int(row.get("quantity", 0))
                    equipment_tag = str(row.get("equipment_tag", "") or "").strip().upper()
                    equipment_badge = f"[{equipment_tag}] " if equipment_tag else ""
                    if action_label:
                        if action_label == "trade-in":
                            row_suffix = f" trade-in {price}c x{qty}"
                        else:
                            row_suffix = f" {action_label} x{qty}"
                    else:
                        listed = "L" if row.get("listed") else "U"
                        interest = str(row.get("purchase_interest", "") or "").strip().lower()
                        interest_marker = {
                            "wanted": "W",
                            "adjacent": "A",
                            "unusual": "?",
                            "refused": "!",
                        }.get(interest, listed)
                        row_suffix = f" {price}c x{qty} {listed}/{interest_marker}"
                compatibility_width = 10  # five cells each for the slot key and class band.
                item_width = max(
                    1,
                    row_w - len(base_prefix) - compatibility_width - len(equipment_badge) - len(row_suffix),
                )
                item_label = _clip(item_name, item_width)
                row_color = row.get("row_color")
                compatibility_color = row.get("compatibility_color")
                # Trade rows share Inventory's glyph-first visual language. Keep
                # the entire row in one proportional-text flow: repainting these
                # fields at character-count offsets duplicated them over the item
                # name in Pygame's pixel-advanced UI font.
                self.view.draw_segments(
                    panel_x + 1,
                    list_y + idx,
                    (
                        _segment(base_prefix, color=row_color),
                        _segment(f"{compatibility_mark:<5}", color=compatibility_color or row_color),
                        _segment(f"{class_band:<4} ", color=compatibility_color or row_color),
                        _segment(f"{equipment_badge}{item_label}{row_suffix}", color=row_color),
                    ),
                    max_width=row_w,
                )

            if not rows:
                self.view.draw_text(panel_x + 2, list_y, _clip("(no offers)", body_w))

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
                    equipment_note = str(selected.get("equipment_note", "") or "").strip()
                    equipment_text = f"; {equipment_note}" if equipment_note else ""
                    if action_label:
                        if action_label == "trade-in":
                            inspect_text = _item_legend_line(
                                selected.get("item_id"),
                                (
                                    f"{selected.get('item_name', selected.get('item_id', 'item'))} "
                                    f"trade-in quote {int(selected.get('price', 0))} credits "
                                    f"qty {int(selected.get('quantity', 0))}{equipment_text}"
                                ),
                            )
                        else:
                            inspect_text = _item_legend_line(
                                selected.get("item_id"),
                                (
                                    f"{selected.get('item_name', selected.get('item_id', 'item'))} "
                                    f"{action_label} into shelf stock qty {int(selected.get('quantity', 0))}{equipment_text}"
                                ),
                            )
                    else:
                        listed_text = "listed" if selected.get("listed") else "unlisted"
                        interest_text = str(selected.get("interest_label", "") or "").strip()
                        read_text = ""
                        if interest_text:
                            read_text = f"; {interest_text}"
                            if not bool(selected.get("interest_known", True)):
                                read_text += " (your read)"
                        inspect_text = _item_legend_line(
                            selected.get("item_id"),
                            (
                                f"{selected.get('item_name', selected.get('item_id', 'item'))} "
                                f"offer {int(selected.get('price', 0))} credits ({listed_text}) "
                                f"qty {int(selected.get('quantity', 0))}{equipment_text}{read_text}"
                            ),
                        )

            self._draw_display_line(
                panel_x + 2,
                panel_y + panel_h - 3,
                _clip_display_line(inspect_text, body_w),
                body_cell_w,
            )
            hint = "E trade  B buy  S sell  X inspect  O ops  Y notebooks  L log  D debug  M/Esc close"
            hint = release_control_text(hint, self.sim)
            self.view.draw_text(panel_x + 2, panel_y + panel_h - 2, _clip(hint, body_w), color=self._theme_color(modal_theme, "footer"))
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
            text_body_top = body_top
            text_body_h = body_h

            draw_casino_art = getattr(self.view, "draw_casino_table_art", None)
            if callable(draw_casino_art) and body_h >= 5:
                try:
                    service_key = str(casino_ui.get("service", "") or "").strip().lower()
                    mode_key = str(casino_ui.get("mode", "") or "").strip().lower()
                    if service_key == "texas_holdem_cash":
                        art_request_h = min(11, max(7, body_h - 2))
                    else:
                        art_request_h = min(7, max(4, body_h // 2))
                    if mode_key == "result" and service_key in {"keno", "plinko"}:
                        art_request_h = min(4, art_request_h)
                    text_rows_after_art = body_h - art_request_h - 1
                    if mode_key == "result" and service_key in {"keno", "plinko"} and text_rows_after_art < 4:
                        art_h = 0
                    else:
                        art_h = int(draw_casino_art(body_x, body_top, body_w, art_request_h, casino_ui) or 0)
                except Exception:
                    art_h = 0
                if art_h > 0:
                    text_body_top = min(divider_y - 1, body_top + art_h + 1)
                    text_body_h = max(1, divider_y - text_body_top)

            raw_body_lines = list(casino_ui.get("body_lines", ()) or ()) or ["The floor is quiet."]
            wrapped_body = []
            body_line_anchors = []
            for raw_index, raw in enumerate(raw_body_lines):
                body_line_anchors.append(len(wrapped_body))
                wrapped = _wrap_display_lines(raw, body_w) if _line_text(raw).strip() else [""]
                wrapped_body.extend(wrapped)
            body_start = 0
            body_scroll_max = max(0, len(wrapped_body) - text_body_h)
            if body_scroll_max > 0:
                try:
                    focus_line = int(casino_ui.get("body_focus_line", -1))
                except (TypeError, ValueError):
                    focus_line = -1
                if bool(casino_ui.get("body_scroll_manual")):
                    try:
                        body_start = int(casino_ui.get("body_scroll", 0) or 0)
                    except (TypeError, ValueError):
                        body_start = 0
                elif 0 <= focus_line < len(body_line_anchors):
                    focus_wrapped = body_line_anchors[focus_line]
                    body_start = focus_wrapped - max(0, (text_body_h - 2) // 2)
                body_start = max(0, min(body_start, body_scroll_max))
            casino_ui["body_scroll"] = int(body_start)
            casino_ui["body_scroll_max"] = int(body_scroll_max)
            casino_ui["body_page_size"] = int(text_body_h)
            visible_body = wrapped_body[body_start: body_start + text_body_h]
            for idx, line in enumerate(visible_body):
                self._draw_display_line(body_x, text_body_top + idx, _clip_display_line(line, body_w), body_w)
            if len(wrapped_body) > text_body_h and body_w >= 8:
                marker_x = body_x + max(0, body_w - 6)
                if body_start > 0:
                    self.view.draw_text(marker_x, text_body_top, "^ more")
                if body_start + text_body_h < len(wrapped_body):
                    self.view.draw_text(marker_x, text_body_top + text_body_h - 1, "v more")

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
            if int(casino_ui.get("body_scroll_max", 0) or 0) > 0:
                footer = f"PgUp/PgDn scroll | {footer}"
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

            self._draw_modal_frame(panel_x, panel_y, panel_w, panel_h, modal_theme)

            subtitle = str(dialog_ui.get("subtitle", "")).strip()
            header_line = self._dialog_header_line(dialog_ui)
            self._draw_display_line(
                panel_x + 2,
                panel_y + 1,
                _clip_display_line(header_line, panel_w - 4),
                panel_w - 4,
            )

            body_w = max(8, _view_text_wrap_width(self.view, panel_w - 4))
            inner_top = panel_y + 2
            if subtitle:
                self.view.draw_text(panel_x + 2, inner_top, _clip(subtitle, body_w), color=self._theme_color(modal_theme, "muted"))
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

            self.view.draw_text(panel_x + 2, divider_y, _clip("-" * body_w, body_w), color=self._theme_color(modal_theme, "divider"))

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
                if topic_id in new_topic_ids:
                    if "new_marker_visible" in row:
                        show_new_marker = bool(row.get("new_marker_visible"))
                    else:
                        show_new_marker = True
                else:
                    show_new_marker = False
                new_flag = str(row.get("new_marker", "+") or "+")[:1] if show_new_marker else " "
                new_color = str(row.get("new_marker_color", "") or "").strip() or (
                    "objective" if topic_id in new_topic_ids else "player"
                )
                label = str(row.get("label", row.get("id", "topic"))).strip() or "topic"
                row_attrs = A_BOLD if absolute == selected_index else 0
                line = _rich_line(
                    (
                        _segment(marker, color="player", attrs=row_attrs),
                        _segment(new_flag, color=new_color, attrs=row_attrs),
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
                empty_text = "(conversation over)" if close_pending else "(no topics)"
                self.view.draw_text(panel_x + 2, options_y, _clip(empty_text, body_w), color="player")

            footer_bits = []
            if scroll > 0:
                footer_bits.append("more above")
            if scroll + transcript_h < len(display_lines):
                footer_bits.append("more below")
            hint = str(dialog_ui.get("hint", "")).strip()
            if hint:
                footer_bits.append(hint)
            footer = " | ".join(footer_bits) if footer_bits else ""
            self.view.draw_text(panel_x + 2, footer_y, _clip(footer, body_w), color=self._theme_color(modal_theme, "footer"))
        elif character_ui.get("open"):
            panel_w = _modal_panel_width(map_w, fraction=0.75, min_width=48)
            panel_h = min(max(14, map_h - 1), map_h)
            panel_h = max(10, panel_h)
            panel_x = max(0, (map_w - panel_w) // 2)
            panel_y = max(0, (map_h - panel_h) // 2)

            self._draw_modal_frame(panel_x, panel_y, panel_w, panel_h, modal_theme)

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
            body_cell_w, body_w = _modal_body_widths(self.view, panel_w)
            title_line = _rich_line(
                (
                    _segment(f" {title}", color="objective", attrs=A_BOLD),
                    _segment("   |   ", color="building_edge"),
                    _segment(page_label, color="player", attrs=A_BOLD),
                    _segment(f" {page_index + 1}/{max(1, len(pages) or 1)} ", color="human"),
                ),
                text=title_text,
            )
            self._draw_display_line(
                panel_x + 2,
                panel_y + 1,
                _clip_display_line(title_line, body_w),
                body_cell_w,
            )

            nav_line = _character_sheet_nav_line(pages, page_index)
            self._draw_display_line(
                panel_x + 2,
                panel_y + 2,
                _clip_display_line(nav_line, body_w),
                body_cell_w,
            )

            body_h = max(1, panel_h - 6)
            display_lines = []
            sheet_lines = _character_sheet_display_lines(
                list(character_ui.get("lines", ()) or ()) or ["No character data."]
            )
            for raw in sheet_lines:
                wrapped = _wrap_display_lines(raw, body_w) if _line_text(raw).strip() else [""]
                display_lines.extend(wrapped)
            display_lines = display_lines or ["No character data."]
            max_scroll = max(0, len(display_lines) - body_h)
            scroll = max(0, min(int(character_ui.get("scroll", 0)), max_scroll))
            character_ui["scroll"] = scroll
            visible_lines = display_lines[scroll: scroll + body_h]

            for idx, line in enumerate(visible_lines[:body_h]):
                self._draw_display_line(
                    panel_x + 2,
                    panel_y + 3 + idx,
                    _clip_display_line(line, body_w),
                    body_cell_w,
                )

            footer_bits = []
            if scroll > 0:
                footer_bits.append("more above")
            if scroll + body_h < len(display_lines):
                footer_bits.append("more below")
            footer = " | ".join(footer_bits) if footer_bits else ""
            jump_max = min(9, max(1, len(pages) or 1))
            action_tail = f"Tab/Left/Right pages | 1-{jump_max} jump | + close | O ops | Y notebooks | L log | D debug | Up/Down scroll | ? help"
            if footer:
                footer = f"{footer} | {action_tail}"
            else:
                footer = action_tail
            footer = release_control_text(footer, self.sim)
            footer_line = _character_sheet_control_line(footer)
            self._draw_display_line(
                panel_x + 2,
                panel_y + panel_h - 2,
                _clip_display_line(footer_line, body_w),
                body_cell_w,
            )
        elif report_ui.get("open"):
            _report_debug_ui.draw_report_modal(
                self.view,
                report_ui,
                screen_w=screen_w,
                map_w=map_w,
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
                sim=self.sim,
                modal_theme=modal_theme,
                draw_box_fn=lambda view, x, y, w, h: self._draw_modal_frame(x, y, w, h, modal_theme),
            )
        elif log_ui.get("open"):
            panel_w = _modal_panel_width(map_w, fraction=0.75, min_width=48)
            panel_h = min(max(12, map_h - 1), map_h)
            panel_h = max(8, panel_h)
            panel_x = max(0, (map_w - panel_w) // 2)
            panel_y = max(0, (map_h - panel_h) // 2)

            def _clip(text, width):
                if width <= 0:
                    return ""
                if len(text) <= width:
                    return text
                if width <= 3:
                    return text[:width]
                return text[: width - 3] + "..."

            self._draw_modal_frame(panel_x, panel_y, panel_w, panel_h, modal_theme)
            title = str(log_ui.get("title", "Event Log")).strip() or "Event Log"
            filter_label = _log_filter_label(log_ui.get("view_filter", "all"))
            hud_filter_label = _log_filter_label(log_ui.get("hud_filter", "priority"))
            filtered_lines = _filtered_log_lines(list(log_ui.get("lines", ()) or ()), log_ui.get("view_filter", "all"))
            entry_count = len(filtered_lines)
            total_count = len(list(log_ui.get("lines", ()) or ()))
            pending_count = len(self._hud_queue)
            title_text = f" {title}: {filter_label} ({entry_count}/{total_count}) | HUD {hud_filter_label} | queue {pending_count} "
            body_cell_w, body_w = _modal_body_widths(self.view, panel_w)
            self.view.draw_text(panel_x + 2, panel_y + 1, _clip(title_text, body_w), color=self._theme_color(modal_theme, "title"))

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
                    body_cell_w,
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
            footer = release_control_text(footer, self.sim)
            self.view.draw_text(panel_x + 2, panel_y + panel_h - 2, _clip(footer, body_w), color=self._theme_color(modal_theme, "footer"))
        elif debug_ui.get("open"):
            _report_debug_ui.draw_debug_modal(
                self.view,
                debug_ui,
                screen_w=screen_w,
                map_w=map_w,
                map_h=map_h,
                view_text_wrap_width_fn=_view_text_wrap_width,
                draw_display_line_fn=self._draw_display_line,
                clip_display_line_fn=_clip_display_line,
                wrap_display_lines_fn=_wrap_display_lines,
                line_text_fn=_line_text,
                modal_theme=modal_theme,
                draw_box_fn=lambda view, x, y, w, h: self._draw_modal_frame(x, y, w, h, modal_theme),
            )

        if help_ui.get("open"):
            panel_w = _modal_panel_width(map_w, fraction=0.75, min_width=48)
            panel_x = max(0, (map_w - panel_w) // 2)
            raw_lines = self._help_overlay_lines(zoom_mode, overlay_active=_combat_turn_pacing_active(self.sim))
            display_lines = self._help_overlay_display_lines(raw_lines)
            body_w, text_w = _modal_body_widths(self.view, panel_w)
            body_lines = []
            for line in display_lines:
                body_lines.extend(_wrap_display_lines(line, text_w))
            panel_h = min(max(8, len(body_lines) + 2), map_h)
            panel_y = max(0, (map_h - panel_h) // 2)
            raw_body_h = max(0, panel_h - 2)
            needs_scroll_footer = len(body_lines) > raw_body_h
            body_h = max(0, panel_h - (3 if needs_scroll_footer else 2))
            max_scroll = max(0, len(body_lines) - body_h)
            scroll = max(0, min(int(help_ui.get("scroll", 0)), max_scroll))
            help_ui["scroll"] = scroll

            self._draw_modal_frame(panel_x, panel_y, panel_w, panel_h, modal_theme)

            visible_lines = body_lines[scroll: scroll + body_h]
            for idx, line in enumerate(visible_lines):
                self._draw_display_line(
                    panel_x + 2,
                    panel_y + 1 + idx,
                    _clip_display_line(line, text_w),
                    body_w,
                )
            if needs_scroll_footer:
                footer_bits = []
                if scroll > 0:
                    footer_bits.append("more above")
                if scroll + body_h < len(body_lines):
                    footer_bits.append("more below")
                footer_bits.append("Up/Down scroll")
                footer_bits.append("?/Esc close")
                footer = " | ".join(footer_bits)
                footer_line = _help_overlay_rich_line(footer, section_index=len(display_lines))
                self._draw_display_line(
                    panel_x + 2,
                    panel_y + panel_h - 2,
                    _clip_display_line(footer_line, text_w),
                    body_w,
                )

        if side_layout_supported and int(hud_y) <= int(map_h) and int(map_h) < int(screen_h):
            self._draw_log_divider(map_h, screen_w, modal_theme)
            hud_y = int(map_h) + 1

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
