"""Extracted systems from ``game.systems``: InputSystem."""

import time
from engine.events import Event
from engine.systems import System
from engine.visibility import has_line_of_sight as _has_line_of_sight
from game.appearance_loadout import APPEARANCE_SLOT_LABELS, appearance_metadata_for_entry, is_appearance_item, is_entry_worn
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
    DroneState,
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
from game.opportunities import _item_label
from game.player_action_system import PlayerActionSystem
from game.player_interactions import (
    CAMPFIRE_HERB_CACHE_CAPACITY,
    CAMPFIRE_HERB_CACHE_KIND,
    campfire_herb_cache_note,
    entry_allowed_in_container,
)
from game.character_sheet import (
    build_character_sheet_pages as _build_character_sheet_pages,
)
import game.report_debug_ui as _report_debug_ui
from game.action_bindings import (
    ACTION_MENU_KEY,
    ACTION_SPECS_BY_ID,
    action_available,
    action_binding_label,
    action_for_input,
    action_for_key,
    key_physical_input,
    menu_action_specs,
    normalize_physical_input,
    reset_action_binding,
    sanitize_control_bindings,
    set_action_binding,
)
from game.casino_ui_runtime import ensure_casino_ui_state
from game.player_config import load_player_config, save_player_config
from game.report_runtime import build_progress_report as _build_progress_report
from game.release_runtime import debug_disabled_hint, debug_mode_enabled
from game.run_objectives import reveal_run_objective
from game.dialogue_runtime import (
    _dialog_backup_cursor_payload,
    _dialog_backup_mark_from_state,
    _disguise_role_label,
)
from game.drone_runtime import (
    drone_state_capabilities,
    drone_state_controlled_by_actor,
    drone_state_has_capability,
)
from game.drone_combat import drone_weapon_status
from game.drone_recon import (
    DRONE_LINKED_CAMERA_RADIUS,
    apply_linked_camera_knowledge,
    apply_linked_sensor_knowledge,
    clear_linked_camera_view,
    describe_drone_camera_cell,
    describe_drone_sensor_cell,
    drone_sensor_modes,
    linked_camera_status,
    linked_sensor_status,
)
from game.drone_sheet import (
    DRONE_SHEET_TABS,
    DRONE_SHEET_VISIBLE_SLOTS,
    drone_sheet_label,
    drone_sheet_records,
    drone_sheet_status_lines,
    drone_sheet_tab_rows,
    drop_drone_workshop_part,
    install_drone_module,
    move_drone_workshop_part_to_pack,
    paint_drone,
    remove_drone_module,
    swap_drone_battery,
    swap_drone_chassis,
    swap_drone_power_center,
    transfer_drone_cargo_to_player,
    transfer_player_cargo_to_drone,
)
from game.drone_workshop import (
    drone_workshop_for_actor,
    drone_workshop_summary,
    is_drone_workshop_part,
    move_inventory_part_to_workshop,
)
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
from game.location_presentation_runtime import (
    _build_known_locations_report,
    _build_known_people_report,
    _item_legend_line,
)
from game.service_runtime import _int_or_default
from game.system_support.combat_targeting_runtime import (
    _actor_is_direct_player_hostile,
    _entity_uses_melee_aim,
    _entity_visible_to_player,
    _first_targetable_entity_at,
    _weapon_ammo_type_label,
    _weapon_context_for_entity,
    _weapon_reserve_ammo,
)
from game.system_support.container_runtime import (
    ITEM_STOWED_CONTAINER_METADATA_KEY,
    _clear_inventory_container_assignments,
    _entry_stowed_container_instance,
    _inventory_entries_loose_for_container,
    _inventory_entries_stowed_in_container,
    _unlink_removed_item_from_gear,
)
from game.system_support.combat_pacing_runtime import (
    _combat_overlay_state,
    _combat_turn_pacing_active,
    _set_manual_combat_pacing,
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
from game.system_support.altered_state_runtime import bonus_move_available, spend_bonus_move
from game.system_support.player_feedback import _log_player_feedback
from game.system_support.throwable_runtime import throwable_summary_text
from game.status_ui_runtime import (
    _entity_status_move_speed_multiplier,
    _status_effect_label,
)
from game.ui_text_runtime import (
    _cycle_log_filter_id,
    _filtered_log_lines,
    _grid_distance,
    _line_text,
    _log_display_line,
    _log_filter_label,
    _log_filter_spec,
    _modal_body_widths,
    _modal_panel_width,
    _rich_line,
    _segment,
    _tick_duration_label,
    _wrap_display_lines,
    _wrap_text_lines,
)
from game.weapons import WEAPON_CATALOG, roll_weapon_instance, weapon_by_id
from ui.input_keys import (
    ENTER_KEYS,
    KEY_A1,
    KEY_A2,
    KEY_A3,
    KEY_B1,
    KEY_B2,
    KEY_B3,
    KEY_BACKSPACE,
    KEY_BACK_TAB,
    KEY_C1,
    KEY_C2,
    KEY_C3,
    KEY_DOWN,
    KEY_END,
    KEY_HOME,
    KEY_LEFT,
    KEY_PAGE_DOWN,
    KEY_PAGE_UP,
    KEY_RIGHT,
    KEY_UP,
)

def _facade():
    from game import systems as facade

    return facade


def _path_next_step(*args, **kwargs):
    return _facade()._path_next_step(*args, **kwargs)

def _property_access_summary(*args, **kwargs):
    return _facade()._property_access_summary(*args, **kwargs)

class InputSystem(System):

    def __init__(self, sim, view, player_eid):
        super().__init__(sim)
        self.view = view
        self.player_eid = player_eid
        self.runs_while_paused = True
        self.catalog = ITEM_CATALOG
        self.player_config_path = getattr(self.sim, "player_config_path", None)
        self.player_config = load_player_config(config_path=self.player_config_path)
        self.control_bindings = sanitize_control_bindings(self.player_config.get("control_bindings"))

        self.movement_keys = {
            KEY_UP: (0, -1),
            KEY_DOWN: (0, 1),
            KEY_LEFT: (-1, 0),
            KEY_RIGHT: (1, 0),
            ord("7"): (-1, -1),
            ord("8"): (0, -1),
            ord("9"): (1, -1),
            ord("4"): (-1, 0),
            ord("6"): (1, 0),
            ord("1"): (-1, 1),
            ord("2"): (0, 1),
            ord("3"): (1, 1),
            ord("w"): (0, -1),
            ord("s"): (0, 1),
            ord("a"): (-1, 0),
            ord("d"): (1, 0),
            ord("q"): (-1, -1),
            ord("e"): (1, -1),
            ord("z"): (-1, 1),
            ord("c"): (1, 1),
            ord("k"): (0, -1),
            ord("j"): (0, 1),
            ord("h"): (-1, 0),
            ord("l"): (1, 0),
        }
        for key_code, delta in (
            (KEY_A1, (-1, -1)),
            (KEY_A2, (0, -1)),
            (KEY_A3, (1, -1)),
            (KEY_B1, (-1, 0)),
            (KEY_B3, (1, 0)),
            (KEY_C1, (-1, 1)),
            (KEY_C2, (0, 1)),
            (KEY_C3, (1, 1)),
            (KEY_HOME, (-1, -1)),
            (KEY_PAGE_UP, (1, -1)),
            (KEY_END, (-1, 1)),
            (KEY_PAGE_DOWN, (1, 1)),
        ):
            if key_code is not None and int(key_code) >= 0:
                self.movement_keys[key_code] = delta
        self.wait_keys = {ord(" "), ord("5")}
        if KEY_B2 is not None and int(KEY_B2) >= 0:
            self.wait_keys.add(KEY_B2)
        self._canonical_movement_key_for_delta = {
            (-1, -1): ord("q"),
            (0, -1): ord("w"),
            (1, -1): ord("e"),
            (-1, 0): ord("a"),
            (1, 0): ord("d"),
            (-1, 1): ord("z"),
            (0, 1): ord("s"),
            (1, 1): ord("c"),
        }
        self._aim_hold_repeat = {
            "delta": None,
            "pressed_at": 0.0,
            "last_repeat_at": 0.0,
        }
        if not hasattr(self.sim, "aim_lock_ui"):
            self.sim.aim_lock_ui = {
                "active": False,
                "target_eid": None,
            }

        if not hasattr(self.sim, "inventory_ui"):
            self.sim.inventory_ui = {
                "panel_kind": "inventory",
                "title": "Inventory",
                "open": False,
                "property_id": None,
                "container_kind": None,
                "container_label": "Container",
                "container_instance_id": None,
                "container_capacity": None,
                "container_view": "pack",
                "cache_view": "pack",
                "note_text": "",
                "selected_index": 0,
                "inspect_text": "",
            }
        if not hasattr(self.sim, "trade_ui"):
            self.sim.trade_ui = {
                "open": False,
                "mode": "buy",
                "selected_index": 0,
                "rows": [],
                "inspect_text": "",
                "store_name": "",
                "property_id": None,
                "supply_note": "",
                "contact_note": "",
                "service_note": "",
                "service_eid": None,
            }
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
                "backup_cursor_mark": None,
                "backup_cursor_pending_topic": "",
            }
        ensure_casino_ui_state(self.sim)
        if not hasattr(self.sim, "help_ui"):
            self.sim.help_ui = {
                "open": False,
                "scroll": 0,
            }
        if not hasattr(self.sim, "character_ui"):
            self.sim.character_ui = {
                "open": False,
                "title": "Character Sheet",
                "pages": [],
                "page_index": 0,
                "page_label": "Summary",
                "page_scrolls": {},
                "lines": [],
                "scroll": 0,
            }
        if not hasattr(self.sim, "report_ui"):
            self.sim.report_ui = _report_debug_ui.default_report_ui_state()
        if not hasattr(self.sim, "log_ui"):
            self.sim.log_ui = {
                "open": False,
                "title": "Event Log",
                "lines": [],
                "scroll": 0,
                "view_filter": "all",
                "hud_filter": "priority",
            }
        if not hasattr(self.sim, "debug_ui"):
            self.sim.debug_ui = _report_debug_ui.default_debug_ui_state()
        if not hasattr(self.sim, "auto_walk_ui"):
            self.sim.auto_walk_ui = {
                "active": False,
                "target_x": 0,
                "target_y": 0,
                "target_z": 0,
                "target_name": "",
                "property_id": None,
                "last_step_at": 0.0,
            }
        if not hasattr(self.sim, "auto_drive_ui"):
            self.sim.auto_drive_ui = {
                "active": False,
                "target_chunk_x": 0,
                "target_chunk_y": 0,
                "target_name": "",
                "property_id": None,
                "marker_id": None,
                "last_step_at": 0.0,
            }
        if not hasattr(self.sim, "local_drive_ui"):
            self.sim.local_drive_ui = {
                "active": False,
                "last_step_at": 0.0,
            }
        if not hasattr(self.sim, "action_menu_ui"):
            self.sim.action_menu_ui = {
                "open": False,
                "selected_index": 0,
                "scroll": 0,
                "category": "all",
                "mode": "action",
                "pending_bind_action_id": "",
                "last_anchor_dx": 0,
                "last_anchor_dy": 1,
                "feedback": "",
            }
        if not hasattr(self.sim, "drone_command_ui"):
            self.sim.drone_command_ui = {
                "open": False,
                "selected_drone_eid": None,
                "eligible": [],
                "status_lines": [],
                "feedback": "",
                "camera_open": False,
                "camera_mode": "inspect",
                "camera_drone_eid": None,
                "camera_cursor_x": 0,
                "camera_cursor_y": 0,
                "camera_cursor_z": 0,
                "camera_visible": set(),
                "camera_radius": DRONE_LINKED_CAMERA_RADIUS,
                "camera_sensor_mode": "camera",
                "camera_contacts": tuple(),
                "camera_inspect_text": "",
            }
        if not hasattr(self.sim, "drone_sheet_ui"):
            self.sim.drone_sheet_ui = {
                "open": False,
                "selected_drone_eid": None,
                "eligible": [],
                "tab": "status",
                "selected_index": 0,
                "scroll": 0,
                "cargo_side": "pack",
                "module_side": "drone",
                "rows": [],
                "status_lines": [],
                "feedback": "",
            }

        self.sim.events.subscribe("move_blocked", self.on_move_blocked)
        self.sim.events.subscribe("zoom_mode_changed", self.on_zoom_mode_changed)
        self.sim.events.subscribe("combat_overlay_entered", self.on_combat_overlay_entered)
        self.sim.events.subscribe("vehicle_action_blocked", self.on_vehicle_action_blocked)
        self.sim.events.subscribe("vehicle_collision", self.on_vehicle_hard_stop)
        self.sim.events.subscribe("vehicle_crash", self.on_vehicle_hard_stop)
        self.sim.events.subscribe("drone_picked_up", self.on_drone_command_target_changed)
        self.sim.events.subscribe("drone_destroyed", self.on_drone_command_target_changed)
        self.sim.events.subscribe("chunk_unloaded", self.on_drone_command_target_changed)
        self.sim.events.subscribe("chunk_loaded", self.on_chunk_stream_changed)
        self.sim.events.subscribe("chunk_unloaded", self.on_chunk_stream_changed)
        self.sim.events.subscribe("chunk_focus_changed", self.on_chunk_stream_changed)

    def _inventory_state(self):
        state = getattr(self.sim, "inventory_ui", None)
        if state is None:
            state = {
                "panel_kind": "inventory",
                "title": "Inventory",
                "open": False,
                "property_id": None,
                "container_kind": None,
                "container_label": "Container",
                "container_instance_id": None,
                "container_capacity": None,
                "container_view": "pack",
                "cache_view": "pack",
                "note_text": "",
                "selected_index": 0,
                "inspect_text": "",
            }
            self.sim.inventory_ui = state
        if str(state.get("panel_kind", "")).strip().lower() == "cache":
            state["panel_kind"] = "container"
            state.setdefault("container_kind", "cache")
            state.setdefault("container_label", "Cache")
        if "container_view" not in state and "cache_view" in state:
            legacy_view = str(state.get("cache_view", "pack")).strip().lower() or "pack"
            state["container_view"] = "pack" if legacy_view == "pack" else "container"
        state.setdefault("panel_kind", "inventory")
        state.setdefault("title", "Inventory")
        state.setdefault("property_id", None)
        state.setdefault("container_kind", None)
        state.setdefault("container_instance_id", None)
        state.setdefault("container_capacity", None)
        if not str(state.get("container_label", "")).strip():
            container_kind = str(state.get("container_kind", "")).strip().lower()
            state["container_label"] = "Cache" if container_kind == "cache" else "Container"
        state.setdefault("container_view", "pack")
        state["cache_view"] = "pack" if str(state.get("container_view", "pack")).strip().lower() == "pack" else "cache"
        state.setdefault("note_text", "")
        return state

    def _trade_state(self):
        state = getattr(self.sim, "trade_ui", None)
        if state is None:
            state = {
                "open": False,
                "mode": "buy",
                "selected_index": 0,
                "rows": [],
                "inspect_text": "",
                "store_name": "",
                "property_id": None,
                "supply_note": "",
                "contact_note": "",
                "service_note": "",
                "service_eid": None,
            }
            self.sim.trade_ui = state
        return state

    def _dialog_state(self):
        state = getattr(self.sim, "dialog_ui", None)
        if state is None:
            state = {
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
            }
            self.sim.dialog_ui = state
        else:
            state.setdefault("kind", "conversation")
            state.setdefault("subtitle", "")
            state.setdefault("transcript", [])
            state.setdefault("topics", [])
            state.setdefault("selected_index", 0)
            state.setdefault("scroll", 0)
            state.setdefault("hint", "")
            state.setdefault("new_topic_ids", [])
            state.setdefault("close_pending", False)
            state.setdefault("property_id", None)
            state.setdefault("machine_action", None)
            state.setdefault("backup_cursor_mark", None)
            state.setdefault("backup_cursor_pending_topic", "")
        return state

    def _casino_state(self):
        return ensure_casino_ui_state(self.sim)

    def _look_state(self):
        state = getattr(self.sim, "look_ui", None)
        if state is None:
            state = {
                "active": False,
                "mode": "city",
                "purpose": "inspect",
                "x": 0,
                "y": 0,
                "z": 0,
                "chunk_x": 0,
                "chunk_y": 0,
                "inspect_text": "",
                "throw_item_instance_id": None,
                "throw_item_name": "",
                "controller_cursor": False,
            }
            self.sim.look_ui = state
        else:
            state.setdefault("purpose", "inspect")
            state.setdefault("throw_item_instance_id", None)
            state.setdefault("throw_item_name", "")
            state.setdefault("controller_cursor", False)
        return state

    def _aim_lock_state(self):
        state = getattr(self.sim, "aim_lock_ui", None)
        if not isinstance(state, dict):
            state = {
                "active": False,
                "target_eid": None,
            }
            self.sim.aim_lock_ui = state
        state.setdefault("active", False)
        state.setdefault("target_eid", None)
        return state

    def _overworld_view_only_for_player(self):
        records = getattr(self.sim, "overworld_view_only_by_eid", None)
        if not isinstance(records, dict):
            return False
        try:
            return bool(records.get(int(self.player_eid), False))
        except (TypeError, ValueError):
            return False

    def _player_in_vehicle(self):
        state = self.sim.ecs.get(VehicleState).get(self.player_eid)
        return bool(state and state.in_vehicle)

    def _help_state(self):
        state = getattr(self.sim, "help_ui", None)
        if state is None:
            state = {
                "open": False,
                "scroll": 0,
            }
            self.sim.help_ui = state
        state.setdefault("scroll", 0)
        return state

    def _character_state(self):
        state = getattr(self.sim, "character_ui", None)
        if state is None:
            state = {
                "open": False,
                "title": "Character Sheet",
                "pages": [],
                "page_index": 0,
                "page_label": "Summary",
                "page_scrolls": {},
                "lines": [],
                "scroll": 0,
            }
            self.sim.character_ui = state
        state.setdefault("pages", [])
        state.setdefault("page_index", 0)
        state.setdefault("page_label", "Summary")
        state.setdefault("page_scrolls", {})
        return state

    def _report_state(self):
        return _report_debug_ui.ensure_report_ui_state(self.sim)

    def _log_state(self):
        state = getattr(self.sim, "log_ui", None)
        if state is None:
            state = {
                "open": False,
                "title": "Event Log",
                "lines": [],
                "scroll": 0,
                "view_filter": "all",
                "hud_filter": "priority",
            }
            self.sim.log_ui = state
        else:
            state.setdefault("view_filter", "all")
            state.setdefault("hud_filter", "priority")
        return state

    def _debug_state(self):
        return _report_debug_ui.ensure_debug_ui_state(self.sim)

    def _auto_walk_state(self):
        state = getattr(self.sim, "auto_walk_ui", None)
        if not isinstance(state, dict):
            state = {
                "active": False,
                "target_x": 0,
                "target_y": 0,
                "target_z": 0,
                "target_name": "",
                "property_id": None,
                "last_step_at": 0.0,
            }
            self.sim.auto_walk_ui = state
        else:
            state.setdefault("active", False)
            state.setdefault("target_x", 0)
            state.setdefault("target_y", 0)
            state.setdefault("target_z", 0)
            state.setdefault("target_name", "")
            state.setdefault("property_id", None)
            state.setdefault("last_step_at", 0.0)
        return state

    def _auto_drive_state(self):
        state = getattr(self.sim, "auto_drive_ui", None)
        if not isinstance(state, dict):
            state = {
                "active": False,
                "target_chunk_x": 0,
                "target_chunk_y": 0,
                "target_name": "",
                "property_id": None,
                "marker_id": None,
                "last_step_at": 0.0,
            }
            self.sim.auto_drive_ui = state
        else:
            state.setdefault("active", False)
            state.setdefault("target_chunk_x", 0)
            state.setdefault("target_chunk_y", 0)
            state.setdefault("target_name", "")
            state.setdefault("property_id", None)
            state.setdefault("marker_id", None)
            state.setdefault("last_step_at", 0.0)
        return state

    def _local_drive_state(self):
        state = getattr(self.sim, "local_drive_ui", None)
        if not isinstance(state, dict):
            state = {
                "active": False,
                "last_step_at": 0.0,
            }
            self.sim.local_drive_ui = state
        else:
            state.setdefault("active", False)
            state.setdefault("last_step_at", 0.0)
        return state

    def _action_menu_state(self):
        state = getattr(self.sim, "action_menu_ui", None)
        if not isinstance(state, dict):
            state = {}
            self.sim.action_menu_ui = state
        state.setdefault("open", False)
        state.setdefault("selected_index", 0)
        state.setdefault("scroll", 0)
        state.setdefault("category", "all")
        state.setdefault("mode", "action")
        state.setdefault("pending_bind_action_id", "")
        state.setdefault("last_anchor_dx", 0)
        state.setdefault("last_anchor_dy", 1)
        state.setdefault("feedback", "")
        state.setdefault("last_input_kind", "key")
        return state

    def _drone_command_state(self):
        state = getattr(self.sim, "drone_command_ui", None)
        if not isinstance(state, dict):
            state = {}
            self.sim.drone_command_ui = state
        state.setdefault("open", False)
        state.setdefault("selected_drone_eid", None)
        state.setdefault("eligible", [])
        state.setdefault("status_lines", [])
        state.setdefault("feedback", "")
        state.setdefault("camera_open", False)
        state.setdefault("camera_mode", "inspect")
        state.setdefault("camera_drone_eid", None)
        state.setdefault("camera_cursor_x", 0)
        state.setdefault("camera_cursor_y", 0)
        state.setdefault("camera_cursor_z", 0)
        state.setdefault("camera_visible", set())
        state.setdefault("camera_radius", DRONE_LINKED_CAMERA_RADIUS)
        state.setdefault("camera_sensor_mode", "camera")
        state.setdefault("camera_contacts", tuple())
        state.setdefault("camera_inspect_text", "")
        return state

    def _drone_sheet_state(self):
        state = getattr(self.sim, "drone_sheet_ui", None)
        if not isinstance(state, dict):
            state = {}
            self.sim.drone_sheet_ui = state
        state.setdefault("open", False)
        state.setdefault("selected_drone_eid", None)
        state.setdefault("eligible", [])
        state.setdefault("tab", "status")
        if str(state.get("tab", "") or "").strip().lower() not in DRONE_SHEET_TABS:
            state["tab"] = "status"
        state.setdefault("selected_index", 0)
        state.setdefault("scroll", 0)
        state.setdefault("cargo_side", "pack")
        if str(state.get("cargo_side", "") or "").strip().lower() not in {"pack", "drone"}:
            state["cargo_side"] = "pack"
        state.setdefault("module_side", "drone")
        module_side = str(state.get("module_side", "") or "").strip().lower()
        if module_side == "pack":
            state["module_side"] = "bay"
        elif module_side not in {"bay", "drone"}:
            state["module_side"] = "drone"
        state.setdefault("rows", [])
        state.setdefault("status_lines", [])
        state.setdefault("feedback", "")
        return state

    def _drone_command_modal_open(self):
        aim_state = self._aim_lock_state()
        if bool(aim_state.get("active")) or aim_state.get("target_eid") is not None:
            return True
        if self._overworld_view_only_for_player():
            return True
        return any(
            bool(state.get("open"))
            for state in (
                self._inventory_state(),
                self._trade_state(),
                self._casino_state(),
                self._dialog_state(),
                self._help_state(),
                self._character_state(),
                self._report_state(),
                self._log_state(),
                self._debug_state(),
                self._action_menu_state(),
                self._drone_sheet_state(),
            )
            if isinstance(state, dict)
        ) or bool(self._look_state().get("active"))

    def _drone_sheet_modal_blocked(self):
        if self._drone_command_modal_open():
            return True
        return bool(self._drone_command_state().get("open"))

    def _drone_command_label(self, state):
        chassis_class = str(getattr(state, "chassis_class", "") or "").strip().upper()
        return f"{chassis_class}-class drone" if chassis_class else "deployed drone"

    def _drone_module_labels(self, state, *, limit=4):
        labels = []
        for module in tuple(getattr(state, "modules", ()) or ()):
            if not isinstance(module, dict):
                continue
            item_id = str(module.get("item_id", "") or "").strip().lower()
            if not item_id:
                continue
            labels.append(item_display_name(item_id, item_catalog=self.catalog))
        if len(labels) > int(limit):
            labels = labels[: int(limit)] + [f"+{len(labels) - int(limit)}"]
        return labels

    def _drone_cargo_line(self, state):
        cargo = [entry for entry in tuple(getattr(state, "cargo", ()) or ()) if isinstance(entry, dict)]
        if not cargo:
            return "Cargo: empty"
        labels = []
        for entry in cargo[:3]:
            item_id = str(entry.get("item_id", "") or "").strip().lower()
            if not item_id:
                continue
            qty = max(1, _int_or_default(entry.get("quantity"), 1))
            suffix = f" x{qty}" if qty > 1 else ""
            labels.append(f"{item_display_name(item_id, item_catalog=self.catalog)}{suffix}")
        if len(cargo) > 3:
            labels.append(f"+{len(cargo) - 3}")
        return "Cargo: " + (", ".join(labels) if labels else "loaded")

    def _drone_camera_status_line(self, camera):
        if not isinstance(camera, dict):
            return "Sensor: unavailable"
        if not bool(camera.get("ok")):
            reason = str(camera.get("reason", "") or "unavailable").replace("_", " ")
            return f"Sensor: unavailable ({reason})"
        sensor_kind = str(camera.get("sensor_kind", "camera") or "camera").strip().lower() or "camera"
        label = str(camera.get("sensor_label", sensor_kind) or sensor_kind).strip().lower() or sensor_kind
        report = "report gate ready" if bool(camera.get("can_live_report")) else "local view only"
        mode = camera.get("sensor_mode") if isinstance(camera.get("sensor_mode"), dict) else {}
        flags = []
        if bool(mode.get("mapping")):
            flags.append("mapping")
        if bool(mode.get("threat")):
            flags.append("threat")
        if bool(mode.get("visual_identity")):
            flags.append("visual")
        flag_text = ",".join(flags) if flags else report
        visible = len(camera.get("visible", ()) or ())
        radius = int(camera.get("radius", DRONE_LINKED_CAMERA_RADIUS) or DRONE_LINKED_CAMERA_RADIUS)
        if sensor_kind == "camera":
            return f"Camera: linked r{radius} | {visible} cells | {report}"
        contacts = len(tuple(camera.get("contacts", ()) or ()))
        contact_text = f" | {contacts} contacts" if contacts else ""
        return f"Sensor: {label} r{radius} | {visible} cells{contact_text} | {flag_text}"

    def _drone_weapon_status_line(self, state):
        status = drone_weapon_status(state, item_catalog=self.catalog, tick=int(getattr(self.sim, "tick", 0) or 0))
        weapons = [row for row in tuple(status.get("weapons", ()) or ()) if row.get("installed")]
        if not weapons:
            return "Weapon: none"
        parts = []
        for row in weapons[:2]:
            kind = str(row.get("weapon_kind", "weapon") or "weapon").strip().lower()
            resource = row.get("resource_amount")
            resource_label = str(row.get("resource_label", "charge") or "charge").strip()
            cooldown = _int_or_default(row.get("cooldown_remaining"), 0)
            suffix = f"{resource} {resource_label}" if resource is not None else resource_label
            if cooldown > 0:
                suffix += f", cd {cooldown}"
            parts.append(f"{kind}: {suffix}")
        if len(weapons) > 2:
            parts.append(f"+{len(weapons) - 2}")
        return "Weapon: " + "; ".join(parts)

    def _drone_status_lines(self, record):
        if not isinstance(record, dict):
            return []
        state = record.get("state")
        pos = record.get("position")
        if state is None or pos is None:
            return ["Drone command link lost."]
        capabilities = tuple(record.get("capabilities", ()) or ())
        modules = self._drone_module_labels(state)
        intent = str(getattr(state, "procedure_key", "") or getattr(state, "last_command", "") or "manual").strip().lower()
        if not intent:
            intent = "manual"
        cap_text = ", ".join(capabilities[:5]) if capabilities else "none"
        if len(capabilities) > 5:
            cap_text += f", +{len(capabilities) - 5}"
        module_text = ", ".join(modules) if modules else "none"
        return [
            f"{self._drone_command_label(state)} #{record.get('eid')} | dist {record.get('distance', 0)}",
            f"Pos {int(pos.x)},{int(pos.y)},{int(pos.z)} | battery {int(getattr(state, 'battery_charge', 0) or 0)}/{int(getattr(state, 'battery_charge_max', 0) or 0)} | hull {int(getattr(state, 'hull_hp', 0) or 0)}/{int(getattr(state, 'hull_hp_max', 0) or 0)}",
            f"Range {int(getattr(state, 'range_limit', 0) or 0)} | intent {intent}",
            self._drone_camera_status_line(record.get("camera")),
            self._drone_weapon_status_line(state),
            f"Capabilities: {cap_text}",
            f"Modules: {module_text}",
            self._drone_cargo_line(state),
        ]

    def _drone_camera_cursor_tuple(self):
        state = self._drone_command_state()
        return (
            int(state.get("camera_cursor_x", 0) or 0),
            int(state.get("camera_cursor_y", 0) or 0),
            int(state.get("camera_cursor_z", 0) or 0),
        )

    def _set_drone_camera_cursor(self, x, y, z):
        state = self._drone_command_state()
        state["camera_cursor_x"] = int(x)
        state["camera_cursor_y"] = int(y)
        state["camera_cursor_z"] = int(z)

    def _close_drone_camera_ui(self):
        state = self._drone_command_state()
        state["camera_open"] = False
        state["camera_mode"] = "inspect"
        state["camera_drone_eid"] = None
        state["camera_visible"] = set()
        state["camera_sensor_mode"] = "camera"
        state["camera_contacts"] = tuple()
        state["camera_inspect_text"] = ""
        clear_linked_camera_view(self.sim)
        return True

    def _sync_linked_drone_camera(self, record, *, announce_unavailable=False, visual_only=False):
        state = self._drone_command_state()
        if not isinstance(record, dict):
            if bool(state.get("camera_open")):
                self._close_drone_camera_ui()
            else:
                clear_linked_camera_view(self.sim)
            return {"ok": False, "reason": "selected_unavailable", "visible": set()}

        if visual_only:
            camera = apply_linked_camera_knowledge(
                self.sim,
                self.player_eid,
                record.get("eid"),
                radius=DRONE_LINKED_CAMERA_RADIUS,
                item_catalog=self.catalog,
            )
        else:
            camera = apply_linked_sensor_knowledge(
                self.sim,
                self.player_eid,
                record.get("eid"),
                preferred_sensor=state.get("camera_sensor_mode"),
                item_catalog=self.catalog,
            )
        record["camera"] = camera
        if not bool(camera.get("ok")):
            if bool(state.get("camera_open")):
                reason = str(camera.get("reason", "unavailable") or "unavailable").replace("_", " ")
                noun = "camera" if visual_only or str(state.get("camera_mode", "")).lower() == "attack" else "sensor"
                state["feedback"] = f"Drone {noun} link lost: {reason}."
                self._close_drone_camera_ui()
            return camera

        visible = set(camera.get("visible", set()) or set())
        pos = camera.get("position")
        state["camera_visible"] = visible
        state["camera_radius"] = int(camera.get("radius", DRONE_LINKED_CAMERA_RADIUS) or DRONE_LINKED_CAMERA_RADIUS)
        sensor_kind = str(camera.get("sensor_kind", "camera") or "camera").strip().lower() or "camera"
        state["camera_sensor_mode"] = sensor_kind
        state["camera_contacts"] = tuple(camera.get("contacts", ()) or ())
        if bool(state.get("camera_open")):
            if state.get("camera_drone_eid") != record.get("eid") and pos is not None:
                self._set_drone_camera_cursor(pos.x, pos.y, pos.z)
                state["camera_inspect_text"] = describe_drone_sensor_cell(
                    self.sim,
                    pos.x,
                    pos.y,
                    pos.z,
                    sensor_kind=sensor_kind,
                    contacts=state.get("camera_contacts"),
                )
            state["camera_drone_eid"] = record.get("eid")
            cursor = self._drone_camera_cursor_tuple()
            if cursor not in visible and pos is not None:
                self._set_drone_camera_cursor(pos.x, pos.y, pos.z)
                state["camera_inspect_text"] = describe_drone_sensor_cell(
                    self.sim,
                    pos.x,
                    pos.y,
                    pos.z,
                    sensor_kind=sensor_kind,
                    contacts=state.get("camera_contacts"),
                )
                if announce_unavailable:
                    state["feedback"] = "Drone sensor cursor returned to the link origin."
        return camera

    def _drone_command_records(self):
        player_pos = self.sim.ecs.get(Position).get(self.player_eid)
        if player_pos is None:
            return []
        positions = self.sim.ecs.get(Position)
        records = []
        for drone_eid, state in self.sim.ecs.get(DroneState).items():
            if str(getattr(state, "mode", "") or "").strip().lower() != "deployed":
                continue
            if not drone_state_controlled_by_actor(state, self.player_eid):
                continue
            if not drone_state_has_capability(state, "remote_control", item_catalog=self.catalog):
                continue
            pos = positions.get(drone_eid)
            if pos is None or int(pos.z) != int(player_pos.z):
                continue
            distance = _manhattan(player_pos.x, player_pos.y, pos.x, pos.y)
            capabilities = drone_state_capabilities(state, item_catalog=self.catalog)
            camera = linked_sensor_status(
                self.sim,
                self.player_eid,
                drone_eid,
                item_catalog=self.catalog,
            )
            records.append({
                "eid": drone_eid,
                "state": state,
                "position": pos,
                "distance": int(distance),
                "capabilities": capabilities,
                "camera": camera,
                "label": self._drone_command_label(state),
            })
        return sorted(records, key=lambda row: (int(row.get("distance", 0)), int(row.get("eid", 0))))

    def _refresh_drone_command_ui(self, *, announce_unavailable=False):
        state = self._drone_command_state()
        records = self._drone_command_records()
        state["eligible"] = [
            {"eid": record["eid"], "label": record["label"], "distance": record["distance"]}
            for record in records
        ]
        selected = state.get("selected_drone_eid")
        selected_record = next((record for record in records if record.get("eid") == selected), None)
        if selected_record is None and records:
            selected_record = records[0]
            state["selected_drone_eid"] = selected_record.get("eid")
            if bool(state.get("open")) and announce_unavailable:
                state["feedback"] = "Selected drone unavailable; switched to nearest commandable drone."
        if selected_record is None:
            state["selected_drone_eid"] = None
            state["status_lines"] = []
            self._close_drone_camera_ui()
            if bool(state.get("open")):
                state["open"] = False
                if announce_unavailable:
                    self.sim.emit(Event(
                        "drone_command_blocked",
                        eid=self.player_eid,
                        controller_eid=self.player_eid,
                        reason="selected_unavailable",
                    ))
            return None
        if bool(state.get("open")):
            self._sync_linked_drone_camera(selected_record, announce_unavailable=announce_unavailable)
        state["status_lines"] = self._drone_status_lines(selected_record)
        return selected_record

    def _open_drone_command_ui(self, zoom_mode=None):
        zoom_mode = str(zoom_mode if zoom_mode is not None else getattr(self.sim, "zoom_mode", "city")).strip().lower() or "city"
        state = self._drone_command_state()
        if zoom_mode == "overworld" or self._drone_command_modal_open():
            state["feedback"] = "Drone command is not available right now."
            self.sim.emit(Event("drone_command_blocked", eid=self.player_eid, controller_eid=self.player_eid, reason="ui_busy"))
            return True
        record = self._refresh_drone_command_ui()
        if record is None:
            state["feedback"] = "No commandable deployed drone."
            self.sim.emit(Event("drone_command_blocked", eid=self.player_eid, controller_eid=self.player_eid, reason="no_commandable_drone"))
            return True
        state["open"] = True
        self._sync_linked_drone_camera(record)
        state["status_lines"] = self._drone_status_lines(record)
        state["feedback"] = "Movement keys command the selected drone. [/] cycles. X links sensors."
        self.sim.emit(Event(
            "drone_command_opened",
            eid=self.player_eid,
            controller_eid=self.player_eid,
            drone_eid=record.get("eid"),
            chassis_class=getattr(record.get("state"), "chassis_class", None),
            count=len(state.get("eligible", ()) or ()),
        ))
        return True

    def _close_drone_command_ui(self):
        state = self._drone_command_state()
        self._close_drone_camera_ui()
        state["open"] = False
        state["feedback"] = ""
        return True

    def _cycle_drone_command_selection(self, step):
        state = self._drone_command_state()
        records = self._drone_command_records()
        if not records:
            self._refresh_drone_command_ui(announce_unavailable=True)
            return None
        selected = state.get("selected_drone_eid")
        index = next((idx for idx, record in enumerate(records) if record.get("eid") == selected), 0)
        index = (int(index) + int(step)) % len(records)
        state["selected_drone_eid"] = records[index].get("eid")
        state["feedback"] = f"Selected {records[index].get('label', 'drone')}."
        if bool(state.get("camera_open")):
            state["camera_drone_eid"] = None
        return self._refresh_drone_command_ui()

    def _selected_drone_command_record(self):
        return self._refresh_drone_command_ui(announce_unavailable=True)

    def _emit_drone_command_request(self, record, command, *, dx=0, dy=0, consume_turn=False):
        if not record:
            self.sim.emit(Event(
                "drone_command_blocked",
                eid=self.player_eid,
                controller_eid=self.player_eid,
                reason="selected_unavailable",
            ))
            return False
        self.sim.emit(Event(
            "drone_command_request",
            eid=self.player_eid,
            controller_eid=self.player_eid,
            drone_eid=record.get("eid"),
            command=command,
            dx=dx,
            dy=dy,
            consume_turn=bool(consume_turn),
        ))
        self._refresh_drone_command_ui(announce_unavailable=True)
        return True

    def _open_drone_camera_ui(self, record):
        state = self._drone_command_state()
        camera = self._sync_linked_drone_camera(record, announce_unavailable=True)
        if not bool(camera.get("ok")):
            reason = str(camera.get("reason", "unavailable") or "unavailable").replace("_", " ")
            state["feedback"] = f"Drone sensor unavailable: {reason}."
            self.sim.emit(Event(
                "drone_command_blocked",
                eid=self.player_eid,
                controller_eid=self.player_eid,
                drone_eid=(record or {}).get("eid") if isinstance(record, dict) else None,
                reason="sensor_unavailable",
            ))
            return True
        pos = camera.get("position")
        state["camera_open"] = True
        state["camera_mode"] = "inspect"
        state["camera_drone_eid"] = record.get("eid")
        sensor_kind = str(camera.get("sensor_kind", "camera") or "camera").strip().lower() or "camera"
        state["camera_sensor_mode"] = sensor_kind
        state["camera_contacts"] = tuple(camera.get("contacts", ()) or ())
        if pos is not None:
            self._set_drone_camera_cursor(pos.x, pos.y, pos.z)
            state["camera_inspect_text"] = describe_drone_sensor_cell(
                self.sim,
                pos.x,
                pos.y,
                pos.z,
                sensor_kind=sensor_kind,
                contacts=state.get("camera_contacts"),
            )
        state["feedback"] = f"Linked drone {sensor_kind if sensor_kind != 'camera' else 'camera'} active."
        return True

    def _open_drone_attack_ui(self, record):
        state = self._drone_command_state()
        if not isinstance(record, dict):
            state["feedback"] = "No selected drone can attack."
            return True
        weapon_status = drone_weapon_status(record.get("state"), item_catalog=self.catalog, tick=int(getattr(self.sim, "tick", 0) or 0))
        if not bool(weapon_status.get("armed")):
            state["feedback"] = "Selected drone has no armed module pair."
            self.sim.emit(Event(
                "drone_weapon_blocked",
                eid=self.player_eid,
                controller_eid=self.player_eid,
                drone_eid=record.get("eid"),
                reason="missing_weapon",
            ))
            return True
        camera = self._sync_linked_drone_camera(record, announce_unavailable=True, visual_only=True)
        if not bool(camera.get("ok")):
            reason = str(camera.get("reason", "unavailable") or "unavailable").replace("_", " ")
            state["feedback"] = f"Attack camera unavailable: {reason}."
            self.sim.emit(Event(
                "drone_weapon_blocked",
                eid=self.player_eid,
                controller_eid=self.player_eid,
                drone_eid=record.get("eid"),
                reason="camera_unavailable",
            ))
            return True
        pos = camera.get("position")
        state["camera_open"] = True
        state["camera_mode"] = "attack"
        state["camera_drone_eid"] = record.get("eid")
        if pos is not None:
            self._set_drone_camera_cursor(pos.x, pos.y, pos.z)
            state["camera_inspect_text"] = describe_drone_camera_cell(self.sim, pos.x, pos.y, pos.z)
        state["feedback"] = "Drone attack cursor active."
        return True

    def _drone_camera_cursor_visible(self, x, y, z):
        state = self._drone_command_state()
        visible = state.get("camera_visible")
        if not isinstance(visible, set):
            visible = set(visible or ())
            state["camera_visible"] = visible
        return (int(x), int(y), int(z)) in visible

    def _examine_drone_camera_cursor(self):
        state = self._drone_command_state()
        x, y, z = self._drone_camera_cursor_tuple()
        if not self._drone_camera_cursor_visible(x, y, z):
            noun = "camera" if str(state.get("camera_sensor_mode", "camera")).lower() == "camera" else "sensor"
            state["feedback"] = "Drone camera has no line of sight there." if noun == "camera" else "Drone sensor cannot read there."
            return True
        state["camera_inspect_text"] = describe_drone_sensor_cell(
            self.sim,
            x,
            y,
            z,
            sensor_kind=state.get("camera_sensor_mode"),
            contacts=state.get("camera_contacts"),
        )
        noun = "camera" if str(state.get("camera_sensor_mode", "camera")).lower() == "camera" else "sensor"
        state["feedback"] = f"Drone {noun} examined the cursor."
        return True

    def _fire_drone_attack_cursor(self):
        state = self._drone_command_state()
        record = self._selected_drone_command_record()
        if not isinstance(record, dict):
            state["feedback"] = "Selected drone is unavailable."
            return True
        x, y, z = self._drone_camera_cursor_tuple()
        if not self._drone_camera_cursor_visible(x, y, z):
            state["feedback"] = "Drone camera has no line of sight there."
            return True
        self.sim.emit(Event(
            "drone_weapon_fire_request",
            eid=self.player_eid,
            controller_eid=self.player_eid,
            drone_eid=record.get("eid"),
            target_x=x,
            target_y=y,
            target_z=z,
            weapon_kind="auto",
            consume_turn=True,
        ))
        state["feedback"] = "Drone weapon command sent."
        self._refresh_drone_command_ui(announce_unavailable=True)
        return True

    def _move_drone_camera_cursor(self, dx, dy):
        state = self._drone_command_state()
        x, y, z = self._drone_camera_cursor_tuple()
        nx = int(x) + int(dx)
        ny = int(y) + int(dy)
        if not self.sim.tilemap.in_bounds(nx, ny):
            state["feedback"] = "Drone sensor cursor hit the map edge."
            return True
        if not self._drone_camera_cursor_visible(nx, ny, z):
            noun = "camera LOS" if str(state.get("camera_sensor_mode", "camera")).lower() == "camera" else "sensor sweep"
            state["feedback"] = f"Drone {noun} does not reach there."
            return True
        self._set_drone_camera_cursor(nx, ny, z)
        state["camera_inspect_text"] = describe_drone_sensor_cell(
            self.sim,
            nx,
            ny,
            z,
            sensor_kind=state.get("camera_sensor_mode"),
            contacts=state.get("camera_contacts"),
        )
        state["feedback"] = "Drone sensor cursor moved."
        return True

    def _cycle_drone_sensor_mode(self, step=1):
        state = self._drone_command_state()
        if str(state.get("camera_mode", "inspect") or "inspect").strip().lower() == "attack":
            state["feedback"] = "Attack mode requires the camera."
            return True
        record = self._selected_drone_command_record()
        drone_state = (record or {}).get("state") if isinstance(record, dict) else None
        modes = list(drone_sensor_modes(drone_state, item_catalog=self.catalog))
        if len(modes) <= 1:
            state["feedback"] = "No alternate sensor mode installed."
            return True
        current = str(state.get("camera_sensor_mode", "") or "").strip().lower()
        index = next((idx for idx, mode in enumerate(modes) if str(mode.get("sensor_kind", "")) == current), 0)
        index = (index + int(step)) % len(modes)
        state["camera_sensor_mode"] = str(modes[index].get("sensor_kind", "") or "").strip().lower()
        status = self._sync_linked_drone_camera(record, announce_unavailable=True)
        label = str(status.get("sensor_label", state.get("camera_sensor_mode", "sensor")) or "sensor").strip().lower()
        state["feedback"] = f"Sensor mode: {label}."
        return True

    def _handle_drone_camera_input(self, physical_input, zoom_mode):
        state = self._drone_command_state()
        if not bool(state.get("camera_open")):
            return False
        key = self._input_key_code(physical_input)
        if str(zoom_mode).strip().lower() == "overworld":
            self._close_drone_command_ui()
            return True
        if key == 27:
            self._close_drone_camera_ui()
            state["feedback"] = "Returned to drone command."
            self._refresh_drone_command_ui(announce_unavailable=True)
            return True
        if key in (ord("q"), ord("Q"), ord("g"), ord("G")):
            self._close_drone_command_ui()
            return True
        if str(state.get("camera_mode", "inspect") or "inspect").strip().lower() == "attack" and key in ENTER_KEYS + (ord("a"), ord("A")):
            return self._fire_drone_attack_cursor()
        if key in (ord("s"), ord("S")):
            return self._cycle_drone_sensor_mode(1)
        if key in ENTER_KEYS or key in (ord("x"), ord("X")):
            return self._examine_drone_camera_cursor()
        movement_delta = self._input_movement_delta(physical_input)
        if movement_delta is not None:
            dx, dy = movement_delta
            return self._move_drone_camera_cursor(dx, dy)
        return True

    def _handle_drone_command_input(self, physical_input, zoom_mode):
        state = self._drone_command_state()
        if not bool(state.get("open")):
            return False
        if bool(state.get("camera_open")):
            return self._handle_drone_camera_input(physical_input, zoom_mode)
        key = self._input_key_code(physical_input)
        if str(zoom_mode).strip().lower() == "overworld":
            self._close_drone_command_ui()
            return True
        if key in (27, ord("q"), ord("Q"), ord("g"), ord("G")):
            self._close_drone_command_ui()
            return True
        if key in (ord("["), ord("{")):
            self._cycle_drone_command_selection(-1)
            return True
        if key in (ord("]"), ord("}")):
            self._cycle_drone_command_selection(1)
            return True
        if key in ENTER_KEYS or key in (ord("i"), ord("I")):
            self._refresh_drone_command_ui(announce_unavailable=True)
            return True
        record = self._selected_drone_command_record()
        if key in (ord("x"), ord("X")):
            self._open_drone_camera_ui(record)
            return True
        if key in (ord("a"), ord("A")) and bool(drone_weapon_status((record or {}).get("state"), item_catalog=self.catalog, tick=int(getattr(self.sim, "tick", 0) or 0)).get("armed")):
            self._open_drone_attack_ui(record)
            return True
        if key in (ord("H"),):
            self._emit_drone_command_request(record, "hold")
            return True
        if key in (ord("f"), ord("F")):
            self._emit_drone_command_request(record, "follow")
            return True
        if key in (ord("r"), ord("R")):
            self._emit_drone_command_request(record, "return")
            return True
        if key in (ord("m"), ord("M")):
            self._emit_drone_command_request(record, "mapping")
            return True
        movement_delta = self._input_movement_delta(physical_input)
        if movement_delta is not None:
            dx, dy = movement_delta
            self._emit_drone_command_request(record, "move", dx=dx, dy=dy, consume_turn=True)
            return True
        return True

    def _drone_sheet_records(self):
        return drone_sheet_records(self.sim, self.player_eid, item_catalog=self.catalog)

    def _drone_workshop_has_entries(self):
        workshop = drone_workshop_for_actor(
            self.sim,
            self.player_eid,
            create=True,
            item_catalog=self.catalog,
        )
        summary = drone_workshop_summary(workshop, item_catalog=self.catalog)
        return int(summary.get("chassis_used", 0) or 0) > 0 or int(summary.get("parts_used", 0) or 0) > 0

    def _refresh_drone_sheet_ui(self, *, announce_unavailable=False):
        state = self._drone_sheet_state()
        has_workshop_entries = self._drone_workshop_has_entries()
        records = self._drone_sheet_records()
        selected = state.get("selected_drone_eid")
        selected_record = next((record for record in records if record.get("eid") == selected), None)
        if selected_record is None and records:
            selected_record = records[0]
            state["selected_drone_eid"] = selected_record.get("eid")
            if bool(state.get("open")) and announce_unavailable:
                state["feedback"] = "Selected drone unavailable; switched to nearest manageable drone."
        if selected_record is None:
            state["selected_drone_eid"] = None
            state["eligible"] = []
            state["status_lines"] = []
            state["visible_start"] = 0
            state["tabs"] = tuple(DRONE_SHEET_TABS)
            if has_workshop_entries:
                state["tab"] = "parts"
                rows = list(drone_sheet_tab_rows(
                    self.sim,
                    self.player_eid,
                    {},
                    tab="parts",
                    cargo_side=state.get("cargo_side", "pack"),
                    module_side=state.get("module_side", "drone"),
                    item_catalog=self.catalog,
                ))
                state["rows"] = rows
                if rows:
                    state["selected_index"] = max(0, min(int(state.get("selected_index", 0) or 0), len(rows) - 1))
                else:
                    state["selected_index"] = 0
                state["scroll"] = max(0, min(int(state.get("scroll", 0) or 0), max(0, len(rows) - 1)))
                return None
            state["rows"] = []
            state["selected_index"] = 0
            state["scroll"] = 0
            if bool(state.get("open")):
                state["open"] = False
                if announce_unavailable:
                    self.sim.emit(Event(
                        "drone_sheet_blocked",
                        eid=self.player_eid,
                        controller_eid=self.player_eid,
                        reason="selected_unavailable",
                    ))
            return None

        selected_index = next((idx for idx, record in enumerate(records) if record.get("eid") == selected_record.get("eid")), 0)
        visible_start = max(0, min(selected_index, max(0, len(records) - DRONE_SHEET_VISIBLE_SLOTS)))
        if selected_index >= visible_start + DRONE_SHEET_VISIBLE_SLOTS:
            visible_start = selected_index - DRONE_SHEET_VISIBLE_SLOTS + 1
        state["eligible"] = [
            {
                "eid": record.get("eid"),
                "label": record.get("label"),
                "distance": record.get("distance", 0),
                "accessible": bool(record.get("accessible")),
                "selected": record.get("eid") == selected_record.get("eid"),
            }
            for record in records
        ]
        state["visible_start"] = int(visible_start)
        state["tabs"] = tuple(DRONE_SHEET_TABS)
        tab = str(state.get("tab", "status") or "status").strip().lower()
        if tab not in DRONE_SHEET_TABS:
            tab = "status"
            state["tab"] = tab
        rows = list(drone_sheet_tab_rows(
            self.sim,
            self.player_eid,
            selected_record,
            tab=tab,
            cargo_side=state.get("cargo_side", "pack"),
            module_side=state.get("module_side", "drone"),
            item_catalog=self.catalog,
        ))
        state["rows"] = rows
        state["status_lines"] = list(drone_sheet_status_lines(selected_record, item_catalog=self.catalog))
        if rows:
            state["selected_index"] = max(0, min(int(state.get("selected_index", 0) or 0), len(rows) - 1))
        else:
            state["selected_index"] = 0
        state["scroll"] = max(0, min(int(state.get("scroll", 0) or 0), max(0, len(rows) - 1)))
        return selected_record

    def _open_drone_sheet_ui(self, zoom_mode=None):
        zoom_mode = str(zoom_mode if zoom_mode is not None else getattr(self.sim, "zoom_mode", "city")).strip().lower() or "city"
        state = self._drone_sheet_state()
        if zoom_mode == "overworld" or self._drone_sheet_modal_blocked():
            state["feedback"] = "Drone sheet is not available right now."
            self.sim.emit(Event("drone_sheet_blocked", eid=self.player_eid, controller_eid=self.player_eid, reason="ui_busy"))
            return True
        has_workshop_entries = self._drone_workshop_has_entries()
        if not self._drone_sheet_records() and has_workshop_entries:
            state["tab"] = "parts"
        record = self._refresh_drone_sheet_ui()
        if record is None and not has_workshop_entries:
            state["feedback"] = "No deployed drone to manage."
            self.sim.emit(Event("drone_sheet_blocked", eid=self.player_eid, controller_eid=self.player_eid, reason="no_manageable_drone"))
            return True
        state["open"] = True
        state["feedback"] = "Drone workshop open." if record is None else "Drone sheet open."
        self.sim.emit(Event(
            "drone_sheet_opened",
            eid=self.player_eid,
            controller_eid=self.player_eid,
            drone_eid=record.get("eid") if isinstance(record, dict) else None,
            chassis_class=getattr(record.get("state"), "chassis_class", None) if isinstance(record, dict) else None,
            count=len(state.get("eligible", ()) or ()),
            workshop_only=record is None,
        ))
        return True

    def _close_drone_sheet_ui(self):
        state = self._drone_sheet_state()
        state["open"] = False
        state["feedback"] = ""
        return True

    def _cycle_drone_sheet_selection(self, step):
        state = self._drone_sheet_state()
        records = self._drone_sheet_records()
        if not records:
            self._refresh_drone_sheet_ui(announce_unavailable=True)
            return None
        selected = state.get("selected_drone_eid")
        index = next((idx for idx, record in enumerate(records) if record.get("eid") == selected), 0)
        index = (int(index) + int(step)) % len(records)
        state["selected_drone_eid"] = records[index].get("eid")
        state["selected_index"] = 0
        state["scroll"] = 0
        state["feedback"] = f"Selected {records[index].get('label', 'drone')}."
        return self._refresh_drone_sheet_ui()

    def _set_drone_sheet_tab(self, tab):
        state = self._drone_sheet_state()
        tab = str(tab or "").strip().lower()
        if tab not in DRONE_SHEET_TABS:
            return False
        state["tab"] = tab
        state["selected_index"] = 0
        state["scroll"] = 0
        state["feedback"] = f"Drone sheet: {tab}."
        self._refresh_drone_sheet_ui(announce_unavailable=True)
        return True

    def _toggle_drone_sheet_cargo_side(self):
        state = self._drone_sheet_state()
        state["cargo_side"] = "drone" if str(state.get("cargo_side", "pack")).strip().lower() == "pack" else "pack"
        state["selected_index"] = 0
        state["scroll"] = 0
        state["feedback"] = f"Cargo view: {'drone' if state['cargo_side'] == 'drone' else 'pack'}."
        self._refresh_drone_sheet_ui(announce_unavailable=True)
        return True

    def _toggle_drone_sheet_module_side(self):
        state = self._drone_sheet_state()
        state["module_side"] = "bay" if str(state.get("module_side", "drone")).strip().lower() == "drone" else "drone"
        state["selected_index"] = 0
        state["scroll"] = 0
        state["feedback"] = f"Module bay: {'workshop' if state['module_side'] == 'bay' else 'installed'}."
        self._refresh_drone_sheet_ui(announce_unavailable=True)
        return True

    def _selected_drone_sheet_record(self):
        return self._refresh_drone_sheet_ui(announce_unavailable=True)

    def _selected_drone_sheet_row(self):
        state = self._drone_sheet_state()
        rows = list(state.get("rows", ()) or ())
        if not rows:
            return None
        index = max(0, min(int(state.get("selected_index", 0) or 0), len(rows) - 1))
        state["selected_index"] = index
        return rows[index]

    def _emit_drone_sheet_blocked(self, record, reason, *, action=None):
        self.sim.emit(Event(
            "drone_sheet_blocked",
            eid=self.player_eid,
            controller_eid=self.player_eid,
            drone_eid=(record or {}).get("eid") if isinstance(record, dict) else None,
            chassis_class=getattr((record or {}).get("state"), "chassis_class", None) if isinstance(record, dict) else None,
            reason=str(reason or "blocked").strip().lower() or "blocked",
            action=str(action or "").strip().lower(),
        ))

    def _drone_sheet_item_name(self, result):
        entry = result.get("entry") if isinstance(result, dict) else None
        if isinstance(entry, dict):
            return item_display_name(entry.get("item_id"), metadata=entry.get("metadata"), item_catalog=self.catalog)
        item_id = result.get("new_battery_item_id") if isinstance(result, dict) else None
        return item_display_name(item_id, item_catalog=self.catalog) if item_id else "item"

    def _activate_selected_drone_sheet_row(self):
        state = self._drone_sheet_state()
        record = self._selected_drone_sheet_record()
        row = self._selected_drone_sheet_row()
        tab = str(state.get("tab", "status") or "status").strip().lower()
        if tab == "parts":
            if row is None:
                self._emit_drone_sheet_blocked(record, "workshop_part_unavailable", action="parts")
                return True
            if not bool(row.get("actionable", False)):
                state["feedback"] = "That workshop row is read-only."
                return True
            instance_id = str(row.get("instance_id", "") or "").strip()
            if not instance_id:
                state["feedback"] = "No workshop part selected."
                return True
            result = move_drone_workshop_part_to_pack(
                self.sim,
                self.player_eid,
                instance_id,
                item_catalog=self.catalog,
            )
            if bool(result.get("ok")):
                item_name = self._drone_sheet_item_name(result)
                state["feedback"] = f"Moved {item_name} to backpack."
                entry = result.get("entry") if isinstance(result.get("entry"), dict) else {}
                self.sim.emit(Event(
                    "drone_workshop_part_moved",
                    eid=self.player_eid,
                    controller_eid=self.player_eid,
                    direction="to_pack",
                    item_id=entry.get("item_id"),
                    item_name=item_name,
                    instance_id=entry.get("instance_id"),
                    quantity=entry.get("quantity", 1),
                ))
            else:
                reason = result.get("reason", "blocked")
                state["feedback"] = f"Workshop move blocked: {str(reason).replace('_', ' ')}."
                self._emit_drone_sheet_blocked(record, reason, action="parts")
            self._refresh_drone_sheet_ui(announce_unavailable=True)
            return True

        if record is None or row is None:
            self._emit_drone_sheet_blocked(record, "selected_unavailable")
            return True
        if not bool(row.get("actionable", False)):
            state["feedback"] = "That drone sheet row is read-only."
            return True

        if tab == "cargo":
            instance_id = str(row.get("instance_id", "") or "").strip()
            if not instance_id:
                state["feedback"] = "No cargo row selected."
                return True
            if str(state.get("cargo_side", "pack")).strip().lower() == "drone":
                result = transfer_drone_cargo_to_player(
                    self.sim,
                    self.player_eid,
                    record.get("eid"),
                    instance_id,
                    item_catalog=self.catalog,
                )
            else:
                result = transfer_player_cargo_to_drone(
                    self.sim,
                    self.player_eid,
                    record.get("eid"),
                    instance_id,
                    item_catalog=self.catalog,
                )
            if bool(result.get("ok")):
                item_name = self._drone_sheet_item_name(result)
                state["feedback"] = f"Transferred {item_name}."
                entry = result.get("entry") if isinstance(result.get("entry"), dict) else {}
                self.sim.emit(Event(
                    "drone_cargo_transferred",
                    eid=self.player_eid,
                    controller_eid=self.player_eid,
                    drone_eid=record.get("eid"),
                    chassis_class=getattr(record.get("state"), "chassis_class", None),
                    direction=result.get("direction"),
                    item_id=entry.get("item_id"),
                    quantity=entry.get("quantity", 1),
                    item_name=item_name,
                    used=result.get("used"),
                    capacity=result.get("capacity"),
                ))
            else:
                reason = result.get("reason", "blocked")
                state["feedback"] = f"Cargo transfer blocked: {str(reason).replace('_', ' ')}."
                self._emit_drone_sheet_blocked(record, reason, action="cargo")
            self._refresh_drone_sheet_ui(announce_unavailable=True)
            return True

        if tab == "battery":
            instance_id = str(row.get("instance_id", "") or "").strip()
            if not instance_id:
                state["feedback"] = "No spare battery selected."
                return True
            result = swap_drone_battery(
                self.sim,
                self.player_eid,
                record.get("eid"),
                instance_id,
                item_catalog=self.catalog,
            )
            if bool(result.get("ok")):
                item_name = self._drone_sheet_item_name(result)
                state["feedback"] = f"Swapped in {item_name}."
                self.sim.emit(Event(
                    "drone_battery_swapped",
                    eid=self.player_eid,
                    controller_eid=self.player_eid,
                    drone_eid=record.get("eid"),
                    chassis_class=getattr(record.get("state"), "chassis_class", None),
                    new_battery_item_id=result.get("new_battery_item_id"),
                    old_battery_item_id=result.get("old_battery_item_id"),
                    item_name=item_name,
                    battery_charge=result.get("battery_charge"),
                    battery_charge_max=result.get("battery_charge_max"),
                    previous=result.get("previous"),
                ))
            else:
                reason = result.get("reason", "blocked")
                state["feedback"] = f"Battery swap blocked: {str(reason).replace('_', ' ')}."
                self._emit_drone_sheet_blocked(record, reason, action="battery")
            self._refresh_drone_sheet_ui(announce_unavailable=True)
            return True

        if tab == "modules":
            action = str(row.get("action", "") or "").strip().lower()
            if action == "install_module":
                instance_id = str(row.get("instance_id", "") or "").strip()
                result = install_drone_module(
                    self.sim,
                    self.player_eid,
                    record.get("eid"),
                    instance_id,
                    item_catalog=self.catalog,
                )
                event_name = "drone_module_installed"
            elif action == "remove_module":
                result = remove_drone_module(
                    self.sim,
                    self.player_eid,
                    record.get("eid"),
                    row.get("module_index"),
                    item_catalog=self.catalog,
                )
                event_name = "drone_module_removed"
            else:
                state["feedback"] = "No module edit selected."
                return True
            if bool(result.get("ok")):
                item_name = self._drone_sheet_item_name(result)
                state["feedback"] = f"{'Installed' if event_name.endswith('installed') else 'Removed'} {item_name}."
                self.sim.emit(Event(
                    event_name,
                    eid=self.player_eid,
                    controller_eid=self.player_eid,
                    drone_eid=record.get("eid"),
                    chassis_class=getattr(record.get("state"), "chassis_class", None),
                    item_id=(result.get("entry") or {}).get("item_id") if isinstance(result.get("entry"), dict) else None,
                    item_name=item_name,
                    errors=tuple(result.get("errors", ()) or ()),
                ))
            else:
                reason = result.get("reason", "blocked")
                details = "; ".join(str(error) for error in result.get("errors", ()) if str(error).strip())
                state["feedback"] = f"Module edit blocked: {str(reason).replace('_', ' ')}{(': ' + details) if details else ''}."
                self._emit_drone_sheet_blocked(record, reason, action="modules")
            self._refresh_drone_sheet_ui(announce_unavailable=True)
            return True

        if tab == "schematic":
            action = str(row.get("action", "") or "").strip().lower()
            if action == "swap_chassis":
                result = swap_drone_chassis(
                    self.sim,
                    self.player_eid,
                    record.get("eid"),
                    str(row.get("instance_id", "") or "").strip(),
                    item_catalog=self.catalog,
                )
                event_name = "drone_chassis_swapped"
            elif action == "swap_power_center":
                result = swap_drone_power_center(
                    self.sim,
                    self.player_eid,
                    record.get("eid"),
                    str(row.get("instance_id", "") or "").strip(),
                    item_catalog=self.catalog,
                )
                event_name = "drone_power_core_swapped"
            elif action == "paint":
                result = paint_drone(
                    self.sim,
                    self.player_eid,
                    record.get("eid"),
                    row.get("paint_key"),
                    row.get("paint_color"),
                    item_catalog=self.catalog,
                )
                event_name = "drone_paint_changed"
            else:
                state["feedback"] = "No schematic edit selected."
                return True
            if bool(result.get("ok")):
                if event_name == "drone_paint_changed":
                    item_name = str(result.get("paint_color") or "paint")
                    state["feedback"] = f"Paint set to {item_name}."
                else:
                    item_name = self._drone_sheet_item_name(result)
                    state["feedback"] = f"Schematic updated: {item_name}."
                self.sim.emit(Event(
                    event_name,
                    eid=self.player_eid,
                    controller_eid=self.player_eid,
                    drone_eid=record.get("eid"),
                    chassis_class=getattr(record.get("state"), "chassis_class", None),
                    item_id=result.get("new_item_id"),
                    item_name=item_name,
                    paint_key=result.get("paint_key"),
                    paint_color=result.get("paint_color"),
                    old_item_id=result.get("old_item_id"),
                    errors=tuple(result.get("errors", ()) or ()),
                ))
            else:
                reason = result.get("reason", "blocked")
                details = "; ".join(str(error) for error in result.get("errors", ()) if str(error).strip())
                state["feedback"] = f"Schematic edit blocked: {str(reason).replace('_', ' ')}{(': ' + details) if details else ''}."
                self._emit_drone_sheet_blocked(record, reason, action="schematic")
            self._refresh_drone_sheet_ui(announce_unavailable=True)
            return True

        state["feedback"] = "That tab is read-only."
        return True

    def _drop_selected_drone_sheet_part(self):
        state = self._drone_sheet_state()
        if str(state.get("tab", "status") or "status").strip().lower() != "parts":
            return False
        record = self._selected_drone_sheet_record()
        row = self._selected_drone_sheet_row()
        if row is None or not bool(row.get("actionable", False)):
            state["feedback"] = "No workshop part selected."
            return True
        instance_id = str(row.get("instance_id", "") or "").strip()
        if not instance_id:
            state["feedback"] = "No workshop part selected."
            return True
        result = drop_drone_workshop_part(
            self.sim,
            self.player_eid,
            instance_id,
            item_catalog=self.catalog,
        )
        if bool(result.get("ok")):
            item_name = self._drone_sheet_item_name(result)
            state["feedback"] = f"Dropped {item_name}."
            entry = result.get("entry") if isinstance(result.get("entry"), dict) else {}
            self.sim.emit(Event(
                "drone_workshop_part_dropped",
                eid=self.player_eid,
                controller_eid=self.player_eid,
                item_id=entry.get("item_id"),
                item_name=item_name,
                instance_id=entry.get("instance_id"),
                quantity=entry.get("quantity", 1),
                ground_item_id=result.get("ground_item_id"),
            ))
        else:
            reason = result.get("reason", "blocked")
            state["feedback"] = f"Workshop drop blocked: {str(reason).replace('_', ' ')}."
            self._emit_drone_sheet_blocked(record, reason, action="parts")
        self._refresh_drone_sheet_ui(announce_unavailable=True)
        return True

    def _handle_drone_sheet_input(self, physical_input, zoom_mode):
        state = self._drone_sheet_state()
        if not bool(state.get("open")):
            return False
        key = self._input_key_code(physical_input)
        if str(zoom_mode).strip().lower() == "overworld":
            self._close_drone_sheet_ui()
            return True
        if key in (27, ord("q"), ord("Q"), ord("G")):
            self._close_drone_sheet_ui()
            return True
        if key in (ord("["), ord("{")):
            self._cycle_drone_sheet_selection(-1)
            return True
        if key in (ord("]"), ord("}")):
            self._cycle_drone_sheet_selection(1)
            return True
        if key in tuple(ord(str(idx)) for idx in range(1, len(DRONE_SHEET_TABS) + 1)):
            self._set_drone_sheet_tab(DRONE_SHEET_TABS[key - ord("1")])
            return True
        if key in (KEY_LEFT, ord("h"), ord("H")):
            if str(state.get("tab", "")).strip().lower() == "cargo":
                self._toggle_drone_sheet_cargo_side()
            elif str(state.get("tab", "")).strip().lower() == "modules":
                self._toggle_drone_sheet_module_side()
            else:
                current = DRONE_SHEET_TABS.index(str(state.get("tab", "status")).strip().lower())
                self._set_drone_sheet_tab(DRONE_SHEET_TABS[(current - 1) % len(DRONE_SHEET_TABS)])
            return True
        if key in (KEY_RIGHT, ord("l"), ord("L")):
            if str(state.get("tab", "")).strip().lower() == "cargo":
                self._toggle_drone_sheet_cargo_side()
            elif str(state.get("tab", "")).strip().lower() == "modules":
                self._toggle_drone_sheet_module_side()
            else:
                current = DRONE_SHEET_TABS.index(str(state.get("tab", "status")).strip().lower())
                self._set_drone_sheet_tab(DRONE_SHEET_TABS[(current + 1) % len(DRONE_SHEET_TABS)])
            return True
        if key in (ord("r"), ord("R")) and str(state.get("tab", "")).strip().lower() == "parts":
            return self._drop_selected_drone_sheet_part()
        rows = list(state.get("rows", ()) or ())
        if key in (KEY_UP, ord("k"), ord("K")):
            state["selected_index"] = max(0, int(state.get("selected_index", 0) or 0) - 1)
            state["scroll"] = min(int(state.get("scroll", 0) or 0), int(state["selected_index"]))
            return True
        if key in (KEY_DOWN, ord("j"), ord("J")):
            state["selected_index"] = min(max(0, len(rows) - 1), int(state.get("selected_index", 0) or 0) + 1)
            return True
        if key in ENTER_KEYS or key in (ord("u"), ord("U")):
            return self._activate_selected_drone_sheet_row()
        self._refresh_drone_sheet_ui(announce_unavailable=True)
        return True

    def _normalize_input_event(self, raw):
        physical = normalize_physical_input(raw)
        if physical:
            return physical
        if isinstance(raw, int):
            return key_physical_input(raw)
        return None

    def _input_key_code(self, physical):
        physical = self._normalize_input_event(physical)
        if not physical:
            return None
        kind = str(physical.get("kind", "") or "").strip().lower()
        has_modifiers = bool(physical.get("modifiers"))
        if kind == "key":
            try:
                return int(physical.get("code"))
            except (TypeError, ValueError):
                return None
        if kind == "button":
            code = str(physical.get("code", "") or "").strip().lower()
            if has_modifiers and code not in {"view", "select", "back", "guide", "start", "menu"}:
                return None
            if code == "south":
                return 10
            if code == "east":
                return 27
            if code in {"view", "select", "back"}:
                return ACTION_MENU_KEY
            if code == "left_shoulder":
                return ord("t") if self._player_in_vehicle() and not self._action_menu_state().get("open") else None
            if code == "west":
                return ord("b") if self._action_menu_state().get("open") else 127
            if code == "north":
                return ord("r") if self._action_menu_state().get("open") else ord("t")
        if kind == "axis" and str(physical.get("axis", "") or "").strip().lower() == "right_stick":
            return None
        try:
            dx = int(physical.get("dx", 0) or 0)
            dy = int(physical.get("dy", 0) or 0)
        except (AttributeError, TypeError, ValueError):
            return None
        dx = max(-1, min(1, dx))
        dy = max(-1, min(1, dy))
        if dx or dy:
            cardinal_arrow_keys = {
                (0, -1): KEY_UP,
                (0, 1): KEY_DOWN,
                (-1, 0): KEY_LEFT,
                (1, 0): KEY_RIGHT,
            }
            return cardinal_arrow_keys.get((dx, dy), self._canonical_movement_key_for_delta.get((dx, dy)))
        return None

    def _input_movement_delta(self, physical):
        physical = self._normalize_input_event(physical)
        if not physical:
            return None
        if physical.get("modifiers"):
            return None
        if str(physical.get("kind", "") or "").strip().lower() == "axis":
            axis = str(physical.get("axis", "") or "").strip().lower()
            if axis == "right_stick":
                return None
        key = self._input_key_code(physical)
        if key in self.movement_keys:
            return self.movement_keys[key]
        try:
            dx = int(physical.get("dx", 0) or 0)
            dy = int(physical.get("dy", 0) or 0)
        except (AttributeError, TypeError, ValueError):
            return None
        if dx == 0 and dy == 0:
            return None
        return (max(-1, min(1, dx)), max(-1, min(1, dy)))

    def _input_right_stick_delta(self, physical):
        physical = self._normalize_input_event(physical)
        if not physical:
            return None
        if str(physical.get("kind", "") or "").strip().lower() != "axis":
            return None
        if str(physical.get("axis", "") or "").strip().lower() != "right_stick":
            return None
        try:
            dx = int(physical.get("dx", 0) or 0)
            dy = int(physical.get("dy", 0) or 0)
        except (AttributeError, TypeError, ValueError):
            parts = str(physical.get("value", physical.get("direction", "")) or "").split(",", 1)
            if len(parts) != 2:
                return None
            try:
                dx = int(parts[0])
                dy = int(parts[1])
            except (TypeError, ValueError):
                return None
        dx = max(-1, min(1, dx))
        dy = max(-1, min(1, dy))
        if dx == 0 and dy == 0:
            return None
        return (dx, dy)

    def _input_is_left_stick_movement(self, physical):
        physical = self._normalize_input_event(physical)
        if not physical:
            return False
        if str(physical.get("kind", "") or "").strip().lower() != "axis":
            return False
        return str(physical.get("axis", "") or "").strip().lower() == "left_stick"

    def _input_is_controller(self, physical):
        physical = self._normalize_input_event(physical)
        return bool(physical and str(physical.get("kind", "") or "").strip().lower() != "key")

    def _record_recent_input_kind(self, physical):
        state = self._action_menu_state()
        state["last_input_kind"] = "controller" if self._input_is_controller(physical) else "key"

    def _reload_control_bindings(self):
        self.player_config = load_player_config(config_path=self.player_config_path)
        self.control_bindings = sanitize_control_bindings(self.player_config.get("control_bindings"))
        return self.control_bindings

    def _save_control_bindings(self, bindings):
        bindings = sanitize_control_bindings(bindings)
        self.control_bindings = bindings
        config = load_player_config(config_path=self.player_config_path)
        config["control_bindings"] = bindings
        self.player_config = config
        save_player_config(config, config_path=self.player_config_path)
        return bindings

    def _action_context(self, zoom_mode=None):
        mode = str(zoom_mode if zoom_mode is not None else getattr(self.sim, "zoom_mode", "city")).strip().lower()
        return "overworld" if mode == "overworld" else "local"

    def _action_for_physical_or_key(self, physical_input, key=None, *, zoom_mode=None):
        context = self._action_context(zoom_mode)
        action_id = action_for_input(self.control_bindings, physical_input, context=context)
        if action_id or key is None:
            return action_id
        return action_for_key(self.control_bindings, key, context=context)

    def _action_menu_rows(self, zoom_mode=None):
        context = self._action_context(zoom_mode)
        player_in_vehicle = self._player_in_vehicle()
        aim_lock_active = bool(self._aim_lock_state().get("active"))
        rows = []
        for spec in menu_action_specs(context=context):
            available, reason = action_available(
                spec.id,
                context=context,
                player_in_vehicle=player_in_vehicle,
                aim_lock_active=aim_lock_active,
            )
            rows.append({
                "id": spec.id,
                "label": spec.label,
                "category": spec.category,
                "binding": action_binding_label(self.control_bindings, spec.id),
                "available": bool(available),
                "reason": str(reason or ""),
                "description": spec.description,
                "rebindable": bool(spec.rebindable and not spec.protected),
            })
        return rows

    def _normalize_action_menu_selection(self, zoom_mode=None):
        state = self._action_menu_state()
        rows = self._action_menu_rows(zoom_mode)
        state["rows"] = rows
        if not rows:
            state["selected_index"] = 0
            state["scroll"] = 0
            return rows
        state["selected_index"] = max(0, min(int(state.get("selected_index", 0) or 0), len(rows) - 1))
        return rows

    def _record_action_anchor_delta(self, dx, dy):
        state = self._action_menu_state()
        try:
            dx = int(dx)
            dy = int(dy)
        except (TypeError, ValueError):
            return
        if dx == 0 and dy == 0:
            return
        state["last_anchor_dx"] = max(-1, min(1, dx))
        state["last_anchor_dy"] = max(-1, min(1, dy))

    def _open_action_menu(self, zoom_mode=None):
        state = self._action_menu_state()
        state["open"] = True
        state["mode"] = "action"
        state["pending_bind_action_id"] = ""
        state["feedback"] = ""
        self._normalize_action_menu_selection(zoom_mode)
        return True

    def _close_action_menu(self):
        state = self._action_menu_state()
        state["open"] = False
        state["mode"] = "action"
        state["pending_bind_action_id"] = ""
        state["feedback"] = ""
        return True

    def _selected_action_menu_row(self, zoom_mode=None):
        rows = self._normalize_action_menu_selection(zoom_mode)
        if not rows:
            return None
        state = self._action_menu_state()
        idx = int(state.get("selected_index", 0) or 0)
        if 0 <= idx < len(rows):
            return rows[idx]
        return None

    def _handle_action_menu_input(self, physical_input, zoom_mode):
        state = self._action_menu_state()
        if not bool(state.get("open")):
            return False
        physical = self._normalize_input_event(physical_input)
        key = self._input_key_code(physical)
        mode = str(state.get("mode", "action") or "action").strip().lower()
        if mode == "bind":
            if key in (27, ACTION_MENU_KEY):
                state["mode"] = "action"
                state["pending_bind_action_id"] = ""
                state["feedback"] = "Binding canceled."
                return True
            action_id = str(state.get("pending_bind_action_id", "") or "").strip()
            ok, message, bindings = set_action_binding(self.control_bindings, action_id, physical)
            if ok:
                self._save_control_bindings(bindings)
            state["mode"] = "action"
            state["pending_bind_action_id"] = ""
            state["feedback"] = message
            return True

        if key is None:
            return True
        if key in (27, ACTION_MENU_KEY, ord("q"), ord("Q")):
            self._close_action_menu()
            return True
        if key == ord("?"):
            self._help_state()["open"] = True
            return True
        rows = self._normalize_action_menu_selection(zoom_mode)
        if key in (KEY_UP, ord("k"), ord("K")):
            state["selected_index"] = max(0, int(state.get("selected_index", 0) or 0) - 1)
            self._next_input_event(collapse_burst=False)
            return True
        if key in (KEY_DOWN, ord("j"), ord("J")):
            state["selected_index"] = min(max(0, len(rows) - 1), int(state.get("selected_index", 0) or 0) + 1)
            self._next_input_event(collapse_burst=False)
            return True
        if key is not None:
            if ord("1") <= key <= ord("9"):
                state["selected_index"] = min(max(0, len(rows) - 1), key - ord("1"))
                return True
        row = self._selected_action_menu_row(zoom_mode)
        if key in (ord("b"), ord("B")):
            if not row:
                return True
            if not row.get("rebindable"):
                state["feedback"] = "That action is protected."
                return True
            state["mode"] = "bind"
            state["pending_bind_action_id"] = row.get("id", "")
            state["feedback"] = f"Press a key or button for {row.get('label', 'action')}."
            # Discard the key that just triggered the bind, duh!
            self._next_input_event(collapse_burst=False)
            return True
        if key in (ord("r"), ord("R")):
            if row:
                self._save_control_bindings(reset_action_binding(self.control_bindings, row.get("id")))
                spec = ACTION_SPECS_BY_ID.get(str(row.get("id", "")))
                state["feedback"] = f"{spec.label if spec else 'Action'} reset."
            return True
        if key in ENTER_KEYS or key in (ord("e"), ord("E"), ord(" ")):
            if not row:
                return True
            if not row.get("available", True):
                reason = str(row.get("reason", "") or "not available").strip()
                state["feedback"] = f"{row.get('label', 'Action')}: {reason}."
                return True
            self._close_action_menu()
            self._execute_action(row.get("id"), key=key, zoom_mode=zoom_mode)
            return True
        return True

    def _player_vehicle_state(self):
        return self.sim.ecs.get(VehicleState).get(self.player_eid)

    def _toggle_vehicle_headlights(self):
        vehicle_state = self._player_vehicle_state()
        if not vehicle_state or not bool(getattr(vehicle_state, "in_vehicle", False)):
            return False
        tick = int(getattr(self.sim, "tick", 0) or 0)
        if hasattr(vehicle_state, "toggle_headlights"):
            active = bool(vehicle_state.toggle_headlights(tick=tick))
        else:
            active = not bool(getattr(vehicle_state, "headlights_on", True))
            vehicle_state.headlights_on = active
            vehicle_state.last_changed_tick = tick
        self.sim.emit(Event(
            "vehicle_headlights_toggled",
            eid=self.player_eid,
            vehicle_id=str(getattr(vehicle_state, "active_vehicle_id", "") or "").strip(),
            headlights_on=active,
        ))
        _log_player_feedback(
            self.sim,
            "Headlights on." if active else "Headlights off.",
            kind="movement",
            dedupe_window=1,
            dedupe_key=f"vehicle_headlights:{int(active)}",
        )
        return True

    def _local_drive_repeat_interval(self):
        state = self._player_vehicle_state()
        try:
            speed = int(getattr(state, "speed", 0) or 0)
        except (TypeError, ValueError):
            speed = 0
        speed = max(1, min(4, speed))
        return float(max(0.08, min(0.24, 0.30 - (0.055 * speed))))

    def _time_pause_blocks_realtime_movement(self):
        reasons = getattr(self.sim, "pause_reasons", None)
        if isinstance(reasons, (set, list, tuple)):
            blocking_reasons = {
                str(reason or "").strip().lower()
                for reason in reasons
                if str(reason or "").strip()
            }
            blocking_reasons.discard("tick_throttle")
            return bool(blocking_reasons)
        if callable(getattr(self.sim, "is_time_paused", None)):
            return bool(self.sim.is_time_paused())
        return False

    def _local_drive_controls_blocked(self, *, zoom_mode=None):
        mode = str(zoom_mode if zoom_mode is not None else getattr(self.sim, "zoom_mode", "city")).strip().lower() or "city"
        if mode == "overworld":
            return True
        if self._time_pause_blocks_realtime_movement():
            return True
        overlay = getattr(self.sim, "combat_overlay", {})
        return bool(getattr(self.sim, "turn_based", False)) or bool(isinstance(overlay, dict) and overlay.get("active"))

    def _stop_local_drive(self, *, reason="stopped", announce=False, zero_speed=True):
        state = self._local_drive_state()
        if not state.get("active"):
            return False
        state["active"] = False
        state["last_step_at"] = 0.0
        if zero_speed:
            vehicle_state = self._player_vehicle_state()
            if vehicle_state is not None:
                if hasattr(vehicle_state, "set_speed"):
                    vehicle_state.set_speed(0, tick=getattr(self.sim, "tick", 0))
                else:
                    vehicle_state.speed = 0
        if announce:
            message = "Stopped driving."
            if reason == "combat":
                message = "Driving falls back to careful turns."
            elif reason == "blocked":
                message = "The vehicle stops."
            _log_player_feedback(
                self.sim,
                message,
                kind="movement",
                dedupe_window=2,
                dedupe_key=f"local_drive:{reason}",
            )
        return True

    def _sync_local_drive_after_vehicle_command(self, *, brake_tapped=False):
        state = self._local_drive_state()
        vehicle_state = self._player_vehicle_state()
        if self._local_drive_controls_blocked():
            self._stop_local_drive(reason="stopped", announce=False, zero_speed=False)
            return False
        if not vehicle_state or not bool(getattr(vehicle_state, "in_vehicle", False)):
            self._stop_local_drive(reason="stopped", announce=False)
            return False
        try:
            speed = int(getattr(vehicle_state, "speed", 0) or 0)
        except (TypeError, ValueError):
            speed = 0
        if brake_tapped:
            self._stop_local_drive(reason="stopped", announce=False)
            return False
        if speed <= 0:
            self._stop_local_drive(reason="stopped", announce=False)
            return False
        state["active"] = True
        state["last_step_at"] = time.monotonic()
        return True

    def _auto_walk_target_label(self):
        state = self._auto_walk_state()
        label = str(state.get("target_name", "") or "").strip()
        if label:
            return label
        return f"{int(state.get('target_x', 0))},{int(state.get('target_y', 0))}"

    def _auto_drive_target_label(self):
        state = self._auto_drive_state()
        label = str(state.get("target_name", "") or "").strip()
        if label:
            return label
        return f"{int(state.get('target_chunk_x', 0))},{int(state.get('target_chunk_y', 0))}"

    def _stop_auto_walk(self, *, reason="stopped", announce=False):
        state = self._auto_walk_state()
        if not state.get("active"):
            return False

        label = self._auto_walk_target_label()
        state["active"] = False
        state["last_step_at"] = 0.0

        if announce:
            message = f"Stopped walking to {label}."
            if reason == "arrived":
                message = f"Arrived near {label}."
            elif reason == "blocked":
                message = f"Route to {label} is blocked."
            elif reason == "combat":
                message = f"Stopped walking to {label}; combat started."
            _log_player_feedback(
                self.sim,
                message,
                kind="movement",
                dedupe_window=2,
                dedupe_key=f"autowalk:{reason}:{str(state.get('property_id') or label)}",
            )
        return True

    def _stop_auto_drive(self, *, reason="stopped", announce=False):
        state = self._auto_drive_state()
        if not state.get("active"):
            return False

        label = self._auto_drive_target_label()
        state["active"] = False
        state["last_step_at"] = 0.0

        if announce:
            message = f"Stopped driving to {label}."
            if reason == "arrived":
                message = f"Arrived at {label}."
            elif reason == "blocked":
                message = f"Road to {label} is blocked."
            elif reason == "combat":
                message = f"Stopped driving to {label}; combat started."
            _log_player_feedback(
                self.sim,
                message,
                kind="movement",
                dedupe_window=2,
                dedupe_key=f"autodrive:{reason}:{str(state.get('property_id') or state.get('marker_id') or label)}",
            )
        return True

    def _auto_walk_repeat_interval(self):
        speed = self._player_move_speed_multiplier()
        return float(max(0.05, min(0.20, 0.12 / max(0.25, float(speed)))))

    def _auto_drive_repeat_interval(self):
        return 0.18

    def _player_overworld_markers(self):
        markers_by_eid = getattr(self.sim, "overworld_markers_by_eid", {})
        if not isinstance(markers_by_eid, dict):
            return []
        raw_markers = markers_by_eid.get(self.player_eid, [])
        if not isinstance(raw_markers, list):
            return []
        return [marker for marker in raw_markers if isinstance(marker, dict)]

    def _preferred_overworld_marker(self):
        markers = self._player_overworld_markers()
        if not markers:
            return None
        return max(
            markers,
            key=lambda marker: (
                int(marker.get("updated_tick", marker.get("created_tick", 0))),
                int(marker.get("id", 0)),
            ),
        )

    def _find_overworld_marker(self, *, chunk=None, property_id=None):
        target_chunk = None
        if isinstance(chunk, (list, tuple)) and len(chunk) == 2:
            try:
                target_chunk = (int(chunk[0]), int(chunk[1]))
            except (TypeError, ValueError):
                target_chunk = None
        property_id = str(property_id or "").strip() or None

        for marker in self._player_overworld_markers():
            if property_id and str(marker.get("property_id", "") or "").strip() == property_id:
                return marker
            if target_chunk is None:
                continue
            chunk_value = marker.get("chunk")
            if not isinstance(chunk_value, (list, tuple)) or len(chunk_value) != 2:
                continue
            marker_chunk = (int(chunk_value[0]), int(chunk_value[1]))
            if marker_chunk == target_chunk:
                return marker
        return None

    def _start_overworld_drive_to_marker(self, marker):
        if not isinstance(marker, dict):
            return False

        chunk = marker.get("chunk")
        if not isinstance(chunk, (list, tuple)) or len(chunk) != 2:
            return False

        positions = self.sim.ecs.get(Position)
        pos = positions.get(self.player_eid)
        if not pos:
            return False

        current_zoom = str(getattr(self.sim, "zoom_mode", "city")).strip().lower() or "city"
        if current_zoom != "overworld":
            _log_player_feedback(
                self.sim,
                "Enter quick travel to drive to a marker.",
                kind="movement",
                dedupe_window=2,
                dedupe_key="autodrive:zoom_required",
            )
            return False

        overlay = getattr(self.sim, "combat_overlay", {})
        if bool(overlay.get("active")) or bool(getattr(self.sim, "turn_based", False)):
            _log_player_feedback(
                self.sim,
                "Cannot start driving assistance during combat.",
                kind="movement",
                dedupe_window=2,
                dedupe_key="autodrive:combat_blocked",
            )
            return False

        target_chunk = (int(chunk[0]), int(chunk[1]))
        current_chunk = self.sim.chunk_coords(pos.x, pos.y)
        label = str(marker.get("label", "") or "").strip() or f"M{int(marker.get('id', 0))}"

        self._stop_auto_walk(reason="stopped", announce=False)

        state = self._auto_drive_state()
        state["active"] = True
        state["target_chunk_x"] = target_chunk[0]
        state["target_chunk_y"] = target_chunk[1]
        state["target_name"] = label
        state["property_id"] = str(marker.get("property_id", "") or "").strip() or None
        state["marker_id"] = int(marker.get("id", 0)) if marker.get("id") is not None else None
        state["last_step_at"] = 0.0

        if current_chunk == target_chunk:
            self._stop_auto_drive(reason="arrived", announce=True)
            return True

        _log_player_feedback(
            self.sim,
            f"Driving to {self._auto_drive_target_label()}. Any key interrupts.",
            kind="movement",
            dedupe_window=2,
            dedupe_key=f"autodrive:start:{str(state.get('property_id') or state.get('marker_id') or label)}",
        )
        return True

    def _nearest_walkable_destination(self, target_x, target_y, target_z, *, radius=6):
        for r in range(0, max(0, int(radius)) + 1):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if r and abs(dx) != r and abs(dy) != r:
                        continue
                    nx = int(target_x) + int(dx)
                    ny = int(target_y) + int(dy)
                    traversable, _reason = _is_traversable_for(
                        self.sim,
                        self.player_eid,
                        nx,
                        ny,
                        int(target_z),
                    )
                    if traversable:
                        return (nx, ny)
        return None

    def _start_selected_known_location_walk(self):
        target = self._selected_known_location_target()
        if not target:
            return False

        positions = self.sim.ecs.get(Position)
        pos = positions.get(self.player_eid)
        if not pos:
            return False

        current_zoom = str(getattr(self.sim, "zoom_mode", "city")).strip().lower() or "city"
        target_x, target_y, target_z = target.get("focus", (pos.x, pos.y, pos.z))
        target_z = int(target_z)
        detail = str(self.sim.detail_for_xy(int(target_x), int(target_y))).strip().lower() or "unloaded"

        if current_zoom == "overworld":
            marked = self._mark_selected_known_location()
            if marked:
                self._close_report_ui()
                marker = self._find_overworld_marker(
                    chunk=target.get("chunk"),
                    property_id=target.get("property_id"),
                )
                self._start_overworld_drive_to_marker(marker)
            return bool(marked)

        if self._player_in_vehicle():
            marked = self._mark_selected_known_location()
            if marked:
                self._stop_auto_walk(reason="stopped", announce=False)
                self._stop_local_drive(reason="stopped", announce=False)
                self._close_report_ui()
                _log_player_feedback(
                    self.sim,
                    f"{target.get('name', 'Known location')} marked on the overworld map. Exit the vehicle to walk there, or use quick travel from an onramp.",
                    kind="movement",
                    dedupe_window=2,
                    dedupe_key=f"known_location:vehicle_walk:{str(target.get('property_id') or target.get('name') or target.get('chunk'))}",
                )
            return bool(marked)

        if detail == "unloaded":
            marked = self._mark_selected_known_location()
            if marked:
                self._close_report_ui()
                _log_player_feedback(
                    self.sim,
                    f"{target.get('name', 'Known location')} is outside loaded street detail; marked it on the overworld map.",
                    kind="movement",
                    dedupe_window=2,
                    dedupe_key=f"known_location:unloaded_walk:{str(target.get('property_id') or target.get('name') or target.get('chunk'))}",
                )
            return bool(marked)

        overlay = getattr(self.sim, "combat_overlay", {})
        if bool(overlay.get("active")) or bool(getattr(self.sim, "turn_based", False)):
            _log_player_feedback(
                self.sim,
                "Cannot start notebook walking during combat.",
                kind="movement",
                dedupe_window=2,
                dedupe_key="autowalk:combat_blocked",
            )
            return False

        if int(pos.z) != target_z:
            _log_player_feedback(
                self.sim,
                "Notebook walking only handles the current floor for now.",
                kind="movement",
                dedupe_window=2,
                dedupe_key="autowalk:floor_blocked",
            )
            return False

        self._stop_auto_drive(reason="stopped", announce=False)
        state = self._auto_walk_state()
        state["active"] = True
        state["target_x"] = int(target_x)
        state["target_y"] = int(target_y)
        state["target_z"] = int(target_z)
        state["target_name"] = str(target.get("name", "")).strip()
        state["property_id"] = str(target.get("property_id", "")).strip() or None
        state["last_step_at"] = 0.0

        self._close_report_ui()
        _log_player_feedback(
            self.sim,
            f"Walking to {self._auto_walk_target_label()}. Any key interrupts.",
            kind="movement",
            dedupe_window=2,
            dedupe_key=f"autowalk:start:{str(state.get('property_id') or state.get('target_name') or 'coords')}",
        )
        return True

    def _maybe_continue_auto_walk(
        self,
        *,
        zoom_mode,
        look_state=None,
        help_state=None,
        dialog_state=None,
        character_state=None,
        report_state=None,
        log_state=None,
        debug_state=None,
        inventory_state=None,
        trade_state=None,
        drone_sheet_state=None,
    ):
        state = self._auto_walk_state()
        if not state.get("active"):
            return False

        if (
            (help_state and help_state.get("open"))
            or (dialog_state and dialog_state.get("open"))
            or (character_state and character_state.get("open"))
            or (report_state and report_state.get("open"))
            or (log_state and log_state.get("open"))
            or (debug_state and debug_state.get("open"))
            or (inventory_state and inventory_state.get("open"))
            or (trade_state and trade_state.get("open"))
            or (drone_sheet_state and drone_sheet_state.get("open"))
            or (look_state and look_state.get("active"))
        ):
            return False

        if self._time_pause_blocks_realtime_movement():
            return False

        if str(zoom_mode).strip().lower() != "city":
            self._stop_auto_walk(reason="stopped", announce=False)
            return False

        overlay = getattr(self.sim, "combat_overlay", {})
        if bool(overlay.get("active")) or bool(getattr(self.sim, "turn_based", False)):
            self._stop_auto_walk(reason="combat", announce=False)
            return False

        positions = self.sim.ecs.get(Position)
        pos = positions.get(self.player_eid)
        if not pos:
            self._stop_auto_walk(reason="stopped", announce=False)
            return False

        target_z = int(state.get("target_z", pos.z))
        if int(pos.z) != target_z:
            self._stop_auto_walk(reason="blocked", announce=True)
            return True

        now = time.monotonic()
        if (float(now) - float(state.get("last_step_at", 0.0))) < self._auto_walk_repeat_interval():
            return False

        raw_target = (int(state.get("target_x", pos.x)), int(state.get("target_y", pos.y)))
        goal = raw_target
        if _grid_distance(pos.x, pos.y, goal[0], goal[1]) <= 6:
            nearby = self._nearest_walkable_destination(goal[0], goal[1], target_z, radius=6)
            if nearby is not None:
                goal = nearby

        if (int(pos.x), int(pos.y)) == goal or (int(pos.x), int(pos.y)) == raw_target:
            self._stop_auto_walk(reason="arrived", announce=True)
            return True

        step = _path_next_step(
            self.sim,
            self.player_eid,
            sx=int(pos.x),
            sy=int(pos.y),
            tx=int(goal[0]),
            ty=int(goal[1]),
            z=int(pos.z),
            max_nodes=4096,
        )
        if not step:
            self._stop_auto_walk(reason="blocked", announce=True)
            return True

        dx = int(step[0]) - int(pos.x)
        dy = int(step[1]) - int(pos.y)
        if dx == 0 and dy == 0:
            self._stop_auto_walk(reason="arrived", announce=True)
            return True

        state["last_step_at"] = float(now)
        self._emit_turn_action("move", dx=dx, dy=dy)
        return True

    def _maybe_continue_auto_drive(
        self,
        *,
        zoom_mode,
        look_state=None,
        help_state=None,
        dialog_state=None,
        character_state=None,
        report_state=None,
        log_state=None,
        debug_state=None,
        inventory_state=None,
        trade_state=None,
        drone_sheet_state=None,
    ):
        state = self._auto_drive_state()
        if not state.get("active"):
            return False

        if (
            (help_state and help_state.get("open"))
            or (dialog_state and dialog_state.get("open"))
            or (character_state and character_state.get("open"))
            or (report_state and report_state.get("open"))
            or (log_state and log_state.get("open"))
            or (debug_state and debug_state.get("open"))
            or (inventory_state and inventory_state.get("open"))
            or (trade_state and trade_state.get("open"))
            or (drone_sheet_state and drone_sheet_state.get("open"))
            or (look_state and look_state.get("active"))
        ):
            return False

        if self._time_pause_blocks_realtime_movement():
            return False

        if str(zoom_mode).strip().lower() != "overworld":
            self._stop_auto_drive(reason="stopped", announce=False)
            return False

        overlay = getattr(self.sim, "combat_overlay", {})
        if bool(overlay.get("active")) or bool(getattr(self.sim, "turn_based", False)):
            self._stop_auto_drive(reason="combat", announce=False)
            return False

        positions = self.sim.ecs.get(Position)
        pos = positions.get(self.player_eid)
        if not pos:
            self._stop_auto_drive(reason="stopped", announce=False)
            return False

        current_chunk = self.sim.chunk_coords(pos.x, pos.y)
        target_chunk = (
            int(state.get("target_chunk_x", current_chunk[0])),
            int(state.get("target_chunk_y", current_chunk[1])),
        )
        if current_chunk == target_chunk:
            self._stop_auto_drive(reason="arrived", announce=True)
            return True

        now = time.monotonic()
        if (float(now) - float(state.get("last_step_at", 0.0))) < self._auto_drive_repeat_interval():
            return False

        dx = 1 if target_chunk[0] > current_chunk[0] else -1 if target_chunk[0] < current_chunk[0] else 0
        dy = 1 if target_chunk[1] > current_chunk[1] else -1 if target_chunk[1] < current_chunk[1] else 0
        if dx == 0 and dy == 0:
            self._stop_auto_drive(reason="arrived", announce=True)
            return True

        state["last_step_at"] = float(now)
        self._emit_turn_action("overworld_travel", dx=dx, dy=dy)
        return True

    def _maybe_continue_local_drive(
        self,
        *,
        zoom_mode,
        look_state=None,
        help_state=None,
        dialog_state=None,
        character_state=None,
        report_state=None,
        log_state=None,
        debug_state=None,
        inventory_state=None,
        trade_state=None,
        drone_sheet_state=None,
    ):
        state = self._local_drive_state()
        if not state.get("active"):
            return False

        if (
            (help_state and help_state.get("open"))
            or (dialog_state and dialog_state.get("open"))
            or (character_state and character_state.get("open"))
            or (report_state and report_state.get("open"))
            or (log_state and log_state.get("open"))
            or (debug_state and debug_state.get("open"))
            or (inventory_state and inventory_state.get("open"))
            or (trade_state and trade_state.get("open"))
            or (drone_sheet_state and drone_sheet_state.get("open"))
            or (look_state and look_state.get("active"))
        ):
            return False

        if self._local_drive_controls_blocked(zoom_mode=zoom_mode):
            self._stop_local_drive(reason="combat", announce=False, zero_speed=False)
            return False

        vehicle_state = self._player_vehicle_state()
        if not vehicle_state or not bool(getattr(vehicle_state, "in_vehicle", False)):
            self._stop_local_drive(reason="stopped", announce=False)
            return False
        try:
            speed = int(getattr(vehicle_state, "speed", 0) or 0)
        except (TypeError, ValueError):
            speed = 0
        if speed <= 0:
            self._stop_local_drive(reason="stopped", announce=False)
            return False

        now = time.monotonic()
        if (float(now) - float(state.get("last_step_at", 0.0))) < self._local_drive_repeat_interval():
            return False

        state["last_step_at"] = float(now)
        self._emit_turn_action("vehicle_momentum")
        if int(getattr(vehicle_state, "speed", 0) or 0) <= 0:
            self._stop_local_drive(reason="stopped", announce=False)
        return True

    def _scroll_panel_body_dimensions(self):
        return _report_debug_ui.scroll_panel_body_dimensions(self.view, self.sim)

    def _character_panel_body_dimensions(self):
        screen_w, screen_h = self.view.size()
        try:
            hud_lines = int(getattr(self.sim, "hud_lines", 10))
        except (TypeError, ValueError):
            hud_lines = 10
        hud_lines = max(1, hud_lines)
        map_h = max(1, min(self.sim.tilemap.height, screen_h - hud_lines))
        map_w = max(1, min(int(getattr(self.sim.tilemap, "width", screen_w) or screen_w), int(screen_w)))
        panel_w = _modal_panel_width(map_w, fraction=0.75, min_width=48)
        panel_h = min(max(14, map_h - 1), map_h)
        panel_h = max(10, panel_h)
        _body_cell_w, body_w = _modal_body_widths(self.view, panel_w)
        body_h = max(1, panel_h - 6)
        return body_w, body_h

    def _refresh_report_ui(self, reset_scroll=False, kind=None):
        report_state = self._report_state()
        target_kind = str(kind or report_state.get("kind") or "progress").strip().lower() or "progress"
        if target_kind == "progress":
            reveal_run_objective(self.sim, source="ops_report")
        return _report_debug_ui.refresh_report_ui(
            self,
            reset_scroll=reset_scroll,
            kind=kind,
            build_known_locations_report_fn=lambda include_hidden: _build_known_locations_report(
                self.sim,
                self.player_eid,
                limit=None,
                include_hidden=include_hidden,
            ),
            build_known_people_report_fn=lambda: _build_known_people_report(
                self.sim,
                self.player_eid,
                limit=None,
            ),
            build_progress_report_fn=lambda: _build_progress_report(
                self.sim,
                self.player_eid,
                opportunity_limit=8,
            ),
            line_text_fn=_line_text,
            wrap_display_lines_fn=_wrap_display_lines,
        )

    def _refresh_known_locations_ui(self, reset_scroll=False):
        return self._refresh_report_ui(reset_scroll=reset_scroll, kind="known_locations")

    def _refresh_known_people_ui(self, reset_scroll=False):
        return self._refresh_report_ui(reset_scroll=reset_scroll, kind="known_people")

    def _close_report_ui(self):
        _report_debug_ui.close_report_ui(self._report_state())

    def _known_locations_list_height(self):
        _body_w, body_h = self._scroll_panel_body_dimensions()
        return _report_debug_ui.known_locations_list_height(body_h=body_h)

    def _clamp_known_locations_selection(self):
        _body_w, body_h = self._scroll_panel_body_dimensions()
        return _report_debug_ui.clamp_known_locations_selection(
            self._report_state(),
            body_h=body_h,
        )

    def _selected_known_location_row(self):
        _body_w, body_h = self._scroll_panel_body_dimensions()
        return _report_debug_ui.selected_known_location_row(
            self._report_state(),
            body_h=body_h,
        )

    def _selected_known_person_row(self):
        _body_w, body_h = self._scroll_panel_body_dimensions()
        return _report_debug_ui.selected_known_person_row(
            self._report_state(),
            body_h=body_h,
        )

    def _toggle_known_location_hidden_view(self):
        state = self._report_state()
        mode = str(state.get("filter_mode", "visible")).strip().lower() or "visible"
        state["filter_mode"] = "hidden" if mode != "hidden" else "visible"
        state["selected_index"] = 0
        state["selected_property_id"] = None
        return self._refresh_known_locations_ui(reset_scroll=True)

    def _toggle_selected_known_location_hidden(self):
        state = self._report_state()
        row = self._selected_known_location_row()
        if not row:
            return False

        knowledge = self.sim.ecs.get(PropertyKnowledge).get(self.player_eid)
        if not knowledge:
            return False

        property_id = str(row.get("property_id", "")).strip()
        if not property_id:
            return False

        state["selected_index"] = int(state.get("selected_index", 0))
        if knowledge.is_hidden(property_id):
            knowledge.unhide(property_id)
        else:
            knowledge.hide(property_id)
        return self._refresh_known_locations_ui(reset_scroll=False)

    def _selected_known_location_target(self):
        row = self._selected_known_location_row()
        if not row:
            return None

        property_id = str(row.get("property_id", "")).strip()
        if not property_id:
            return None

        prop = self.sim.properties.get(property_id)
        if not isinstance(prop, dict):
            return None

        focus = _property_focus_position(prop) or _property_display_position(prop)
        if focus is None:
            try:
                focus = (
                    int(prop.get("x", 0)),
                    int(prop.get("y", 0)),
                    int(prop.get("z", 0)),
                )
            except (TypeError, ValueError):
                return None

        try:
            x = int(focus[0])
            y = int(focus[1])
            z = int(focus[2]) if len(focus) > 2 else int(prop.get("z", 0))
        except (TypeError, ValueError, IndexError):
            return None

        chunk = self.sim.chunk_coords(x, y)
        return {
            "row": row,
            "property_id": property_id,
            "prop": prop,
            "name": str(row.get("name", prop.get("name", property_id))).strip() or property_id,
            "focus": (x, y, z),
            "chunk": (int(chunk[0]), int(chunk[1])),
        }

    def _inspect_selected_known_location(self):
        target = self._selected_known_location_target()
        if not target:
            return False

        positions = self.sim.ecs.get(Position)
        pos = positions.get(self.player_eid)
        if not pos:
            return False

        current_zoom = str(getattr(self.sim, "zoom_mode", "city")).strip().lower() or "city"
        target_chunk = tuple(target.get("chunk", self.sim.chunk_coords(pos.x, pos.y)))
        focus_x, focus_y, focus_z = target.get("focus", (pos.x, pos.y, pos.z))
        detail = str(self.sim.detail_for_xy(int(focus_x), int(focus_y))).strip().lower() or "unloaded"

        if current_zoom != "overworld" and detail == "unloaded":
            marked = self._mark_selected_known_location()
            if marked:
                self._close_report_ui()
                _log_player_feedback(
                    self.sim,
                    f"{target.get('name', 'Known location')} is known, but current street-level detail is not loaded; marked it on the overworld map.",
                    kind="movement",
                    dedupe_window=2,
                    dedupe_key=f"known_location:unloaded_inspect:{str(target.get('property_id') or target.get('name') or target.get('chunk'))}",
                )
            return bool(marked)

        self._close_report_ui()
        if current_zoom != "overworld":
            return self._activate_look_mode_at(
                "city",
                x=focus_x,
                y=focus_y,
                z=focus_z,
                purpose="inspect",
            )

        return self._activate_look_mode_at(
            "overworld",
            chunk_x=target_chunk[0],
            chunk_y=target_chunk[1],
            purpose="inspect",
        )

    def _mark_selected_known_location(self):
        target = self._selected_known_location_target()
        if not target:
            return False

        chunk_x, chunk_y = target.get("chunk", (0, 0))
        self._emit_player_action(
            "overworld_marker_set",
            consume_turn=False,
            target_chunk_x=int(chunk_x),
            target_chunk_y=int(chunk_y),
            marker_label=str(target.get("name", "")).strip(),
            property_id=str(target.get("property_id", "")).strip(),
        )
        return True

    def _report_display_lines(self):
        body_w, _body_h = self._scroll_panel_body_dimensions()
        return _report_debug_ui.report_display_lines(
            self._report_state(),
            body_w=body_w,
            line_text_fn=_line_text,
            wrap_display_lines_fn=_wrap_display_lines,
        )

    def _clamp_report_scroll(self):
        body_w, body_h = self._scroll_panel_body_dimensions()
        return _report_debug_ui.clamp_report_scroll(
            self._report_state(),
            body_w=body_w,
            body_h=body_h,
            line_text_fn=_line_text,
            wrap_display_lines_fn=_wrap_display_lines,
        )

    def _refresh_log_ui(self, reset_scroll=False, focus_end=True):
        state = self._log_state()
        previous_scroll = int(state.get("scroll", 0))
        raw_entries = list(getattr(self.sim.log, "entries", ()) or ())
        state["open"] = True
        state["title"] = "Event Log"
        state["lines"] = raw_entries
        if reset_scroll:
            if focus_end:
                display_lines = self._log_display_lines()
                _body_w, body_h = self._scroll_panel_body_dimensions()
                state["scroll"] = max(0, len(display_lines) - body_h)
            else:
                state["scroll"] = 0
        else:
            state["scroll"] = previous_scroll
        self._clamp_log_scroll()
        return True

    def _close_log_ui(self):
        state = self._log_state()
        state["open"] = False
        state["scroll"] = 0

    def _character_current_page(self):
        state = self._character_state()
        pages = list(state.get("pages", ()) or [])
        if not pages:
            return None
        page_index = max(0, min(int(state.get("page_index", 0)), len(pages) - 1))
        state["page_index"] = page_index
        return pages[page_index]

    def _set_character_page(self, page_index, *, reset_scroll=False):
        state = self._character_state()
        pages = list(state.get("pages", ()) or [])
        if not pages:
            state["page_index"] = 0
            state["page_label"] = "Summary"
            state["lines"] = ["No character data."]
            state["scroll"] = 0
            return False

        current_page = self._character_current_page()
        current_page_id = str((current_page or {}).get("id", "")).strip().lower()
        page_scrolls = dict(state.get("page_scrolls", {}) or {})
        if current_page_id:
            page_scrolls[current_page_id] = int(state.get("scroll", 0))

        page_index = max(0, min(int(page_index), len(pages) - 1))
        state["page_index"] = page_index
        page = pages[page_index]
        page_id = str(page.get("id", "")).strip().lower()
        state["page_label"] = str(page.get("label", "Page")).strip() or "Page"
        state["lines"] = list(page.get("lines", ()) or ()) or ["No character data."]
        state["page_scrolls"] = page_scrolls
        if reset_scroll:
            state["scroll"] = 0
        else:
            state["scroll"] = int(page_scrolls.get(page_id, 0))
        self._clamp_character_scroll()
        return True

    def _cycle_character_page(self, step=1):
        state = self._character_state()
        pages = list(state.get("pages", ()) or [])
        if len(pages) <= 1:
            return False
        next_index = (int(state.get("page_index", 0)) + int(step)) % len(pages)
        return self._set_character_page(next_index, reset_scroll=False)

    def _refresh_character_ui(self, reset_scroll=False):
        state = self._character_state()
        current_page = self._character_current_page()
        current_page_id = str((current_page or {}).get("id", "")).strip().lower()
        page_scrolls = {} if reset_scroll else dict(state.get("page_scrolls", {}) or {})
        if current_page_id and not reset_scroll:
            page_scrolls[current_page_id] = int(state.get("scroll", 0))
        state["open"] = True
        state["title"] = "Character Sheet"
        state["pages"] = list(
            _build_character_sheet_pages(
                self.sim,
                self.player_eid,
                duration_label_fn=_tick_duration_label,
            )
            or ()
        )
        state["page_scrolls"] = page_scrolls
        target_index = 0
        if not reset_scroll and current_page_id:
            for idx, page in enumerate(list(state.get("pages", ()) or ())):
                if str(page.get("id", "")).strip().lower() == current_page_id:
                    target_index = idx
                    break
        self._set_character_page(target_index, reset_scroll=reset_scroll)
        return True

    def _close_character_ui(self):
        state = self._character_state()
        current_page = self._character_current_page()
        current_page_id = str((current_page or {}).get("id", "")).strip().lower()
        if current_page_id:
            page_scrolls = dict(state.get("page_scrolls", {}) or {})
            page_scrolls[current_page_id] = int(state.get("scroll", 0))
            state["page_scrolls"] = page_scrolls
        state["open"] = False
        state["scroll"] = 0

    def _refresh_debug_ui(self, reset_scroll=False):
        if not debug_mode_enabled(self.sim):
            debug_disabled_hint(self.sim)
            return False
        return _report_debug_ui.refresh_debug_ui(
            self,
            reset_scroll=reset_scroll,
            build_debug_overlay_fn=lambda: _build_debug_overlay(
                self.sim,
                self.player_eid,
                duration_label_fn=_tick_duration_label,
                property_access_summary_fn=_property_access_summary,
            ),
            line_text_fn=_line_text,
            wrap_display_lines_fn=_wrap_display_lines,
        ) or True

    def _close_debug_ui(self):
        _report_debug_ui.close_debug_ui(self._debug_state())

    def _log_display_lines(self):
        state = self._log_state()
        raw_lines = list(state.get("lines", ()) or ())
        filter_id = state.get("view_filter", "all")
        raw_lines = _filtered_log_lines(raw_lines, filter_id)
        if not raw_lines:
            raw_lines = [f"No {_log_filter_label(filter_id).lower()} log entries yet."]

        body_w, _body_h = self._scroll_panel_body_dimensions()
        display_lines = []
        for raw in raw_lines:
            display_line = _log_display_line(raw)
            wrapped = _wrap_display_lines(display_line, body_w) if _line_text(display_line).strip() else [""]
            display_lines.extend(wrapped)
        return display_lines or [f"No {_log_filter_label(filter_id).lower()} log entries yet."]

    def _clamp_log_scroll(self):
        state = self._log_state()
        display_lines = self._log_display_lines()
        _body_w, body_h = self._scroll_panel_body_dimensions()
        max_scroll = max(0, len(display_lines) - body_h)
        state["scroll"] = max(0, min(int(state.get("scroll", 0)), max_scroll))
        return state["scroll"]

    def _character_display_lines(self):
        state = self._character_state()
        raw_lines = list(state.get("lines", ()) or ())
        if not raw_lines:
            raw_lines = ["No character data."]

        body_w, _body_h = self._character_panel_body_dimensions()
        display_lines = []
        for raw in raw_lines:
            layout_text = str(raw).replace(" | ", "   |   ")
            layout_line = _rich_line((_segment(layout_text),), text=layout_text)
            wrapped = _wrap_display_lines(layout_line, body_w) if layout_text.strip() else [""]
            display_lines.extend(wrapped)
        return display_lines or ["No character data."]

    def _clamp_character_scroll(self):
        state = self._character_state()
        display_lines = self._character_display_lines()
        _body_w, body_h = self._character_panel_body_dimensions()
        max_scroll = max(0, len(display_lines) - body_h)
        state["scroll"] = max(0, min(int(state.get("scroll", 0)), max_scroll))
        current_page = self._character_current_page()
        current_page_id = str((current_page or {}).get("id", "")).strip().lower()
        if current_page_id:
            page_scrolls = dict(state.get("page_scrolls", {}) or {})
            page_scrolls[current_page_id] = int(state.get("scroll", 0))
            state["page_scrolls"] = page_scrolls
        return state["scroll"]

    def _cycle_log_view_filter(self, step=1, reset_scroll=True):
        state = self._log_state()
        state["view_filter"] = _cycle_log_filter_id(state.get("view_filter", "all"), step=step)
        if reset_scroll:
            self._refresh_log_ui(reset_scroll=True, focus_end=True)
        else:
            self._clamp_log_scroll()
        return state["view_filter"]

    def _set_hud_log_filter(self, filter_id):
        state = self._log_state()
        state["hud_filter"] = _log_filter_spec(filter_id)["id"]
        return state["hud_filter"]

    def _debug_display_lines(self):
        body_w, _body_h = self._scroll_panel_body_dimensions()
        return _report_debug_ui.debug_display_lines(
            self._debug_state(),
            body_w=body_w,
            line_text_fn=_line_text,
            wrap_display_lines_fn=_wrap_display_lines,
        )

    def _clamp_debug_scroll(self):
        body_w, body_h = self._scroll_panel_body_dimensions()
        return _report_debug_ui.clamp_debug_scroll(
            self._debug_state(),
            body_w=body_w,
            body_h=body_h,
            line_text_fn=_line_text,
            wrap_display_lines_fn=_wrap_display_lines,
        )

    def _dialog_body_dimensions(self):
        body_w, body_h = self._scroll_panel_body_dimensions()
        transcript_h = max(1, body_h - 6)
        option_h = max(1, min(6, body_h - transcript_h))
        return body_w, transcript_h, option_h

    def _dialog_display_lines(self):
        state = self._dialog_state()
        raw_lines = list(state.get("transcript", ()) or ())
        if not raw_lines:
            raw_lines = ["No conversation yet."]
        body_w, _transcript_h, _option_h = self._dialog_body_dimensions()
        display_lines = []
        for raw in raw_lines:
            wrapped = _wrap_display_lines(raw, body_w) if _line_text(raw).strip() else [""]
            display_lines.extend(wrapped)
        return display_lines or ["No conversation yet."]

    def _clamp_dialog_scroll(self):
        state = self._dialog_state()
        display_lines = self._dialog_display_lines()
        _body_w, transcript_h, _option_h = self._dialog_body_dimensions()
        max_scroll = max(0, len(display_lines) - transcript_h)
        state["scroll"] = max(0, min(int(state.get("scroll", 0)), max_scroll))
        return state["scroll"]

    def _normalize_dialog_selection(self):
        state = self._dialog_state()
        topics = list(state.get("topics", ()) or ())
        if not topics:
            state["selected_index"] = 0
            return
        state["selected_index"] = max(0, min(int(state.get("selected_index", 0)), len(topics) - 1))

    def _selected_dialog_topic(self):
        self._normalize_dialog_selection()
        state = self._dialog_state()
        topics = list(state.get("topics", ()) or ())
        if not topics:
            return None
        idx = int(state.get("selected_index", 0))
        if idx < 0 or idx >= len(topics):
            return None
        return topics[idx]

    def _dialog_backup_mark(self):
        return _dialog_backup_mark_from_state(self._dialog_state())

    def _dialog_backup_mark_pending_topic(self):
        state = self._dialog_state()
        return str(state.get("backup_cursor_pending_topic", "") or "").strip().lower()

    def _dialog_backup_mark_selected_topic_id(self):
        topic = self._selected_dialog_topic()
        return str((topic or {}).get("id", "") or "").strip().lower()

    def _dialog_can_mark_backup_spot(self):
        state = self._dialog_state()
        if not state.get("open"):
            return False
        topic_ids = {
            str(row.get("id", "")).strip().lower()
            for row in list(state.get("topics", ()) or ())
            if isinstance(row, dict)
        }
        return bool(topic_ids & {"backup_orders", "backup_goto_wait", "backup_wait_return", "backup_kill"})

    def _activate_dialog_backup_marking(self, *, pending_topic=""):
        state = self._dialog_state()
        if not state.get("open"):
            return False
        npc_eid = state.get("npc_eid")
        if npc_eid is None:
            return False
        mark = self._dialog_backup_mark()
        player_pos = self.sim.ecs.get(Position).get(self.player_eid)
        if player_pos is None:
            return False
        target_x = int(mark.get("x", player_pos.x))
        target_y = int(mark.get("y", player_pos.y))
        target_z = int(mark.get("z", player_pos.z))
        state["backup_cursor_pending_topic"] = str(pending_topic or "").strip().lower()
        state["hint"] = "Mark a spot for the order."
        return self._activate_look_mode_at(
            "city",
            x=target_x,
            y=target_y,
            z=target_z,
            purpose="backup_order",
        )

    def _commit_dialog_backup_mark(self):
        look_state = self._look_state()
        dialog_state = self._dialog_state()
        npc_eid = dialog_state.get("npc_eid")
        payload = _dialog_backup_cursor_payload(
            self.sim,
            self.player_eid,
            npc_eid,
            look_state.get("x", 0),
            look_state.get("y", 0),
            look_state.get("z", 0),
        )
        pending_topic = self._dialog_backup_mark_pending_topic()
        dialog_state["backup_cursor_pending_topic"] = ""
        self._deactivate_look_mode()
        if not payload:
            dialog_state["hint"] = "That mark does not hold on this floor."
            return True
        dialog_state["backup_cursor_mark"] = dict(payload)
        dialog_state["hint"] = f"Marked {payload.get('label', 'the spot')}. Choose an order."
        if pending_topic:
            self.sim.emit(Event(
                "dialog_topic_request",
                eid=self.player_eid,
                npc_eid=npc_eid,
                topic_id=pending_topic,
            ))
        return True

    def _close_dialog_ui(self):
        self.sim.emit(Event("dialog_close_request", eid=self.player_eid))

    def _handle_casino_input(self, key):
        state = self._casino_state()
        if not bool(state.get("open")):
            return False

        if key in (ord("?"), ord("/")):
            self._help_state()["open"] = True
            return True

        if key in (27, ord("q"), ord("Q")):
            self.sim.emit(Event("casino_ui_action", eid=self.player_eid, action="back"))
            return True

        if key in (ord("o"), ord("O")):
            self.sim.emit(Event("casino_ui_action", eid=self.player_eid, action="back"))
            self._refresh_report_ui(reset_scroll=True)
            return True

        if key in (ord("y"), ord("Y")):
            self.sim.emit(Event("casino_ui_action", eid=self.player_eid, action="back"))
            self._refresh_known_locations_ui(reset_scroll=True)
            return True

        if key == ord("L"):
            self.sim.emit(Event("casino_ui_action", eid=self.player_eid, action="back"))
            self._refresh_log_ui(reset_scroll=True, focus_end=True)
            return True

        if key == ord("D"):
            if debug_mode_enabled(self.sim):
                self.sim.emit(Event("casino_ui_action", eid=self.player_eid, action="back"))
                self._refresh_debug_ui(reset_scroll=True)
            else:
                self._refresh_debug_ui(reset_scroll=True)
            return True

        if key == ord("\t"):
            self.sim.emit(Event("casino_ui_action", eid=self.player_eid, action="tab"))
            return True

        if key in (KEY_UP, ord("k"), ord("K")):
            self.sim.emit(Event("casino_ui_action", eid=self.player_eid, action="move", dx=0, dy=-1))
            return True

        if key in (KEY_DOWN, ord("j"), ord("J")):
            self.sim.emit(Event("casino_ui_action", eid=self.player_eid, action="move", dx=0, dy=1))
            return True

        if key in (KEY_LEFT, ord("h"), ord("H")):
            self.sim.emit(Event("casino_ui_action", eid=self.player_eid, action="move", dx=-1, dy=0))
            return True

        if key in (KEY_RIGHT, ord("l")):
            self.sim.emit(Event("casino_ui_action", eid=self.player_eid, action="move", dx=1, dy=0))
            return True

        if key == ord(" "):
            if bool(state.get("close_pending")):
                self.sim.emit(Event("casino_ui_action", eid=self.player_eid, action="back"))
            else:
                self.sim.emit(Event("casino_ui_action", eid=self.player_eid, action="primary"))
            return True

        key_backspace = KEY_BACKSPACE
        if key in (127, 8, key_backspace):
            self.sim.emit(Event("casino_ui_action", eid=self.player_eid, action="secondary"))
            return True

        if key in ENTER_KEYS or key in (ord("e"), ord("E")):
            self.sim.emit(Event("casino_ui_action", eid=self.player_eid, action="confirm"))
            return True

        return True

    def _handle_dialog_input(self, key):
        state = self._dialog_state()
        if not state.get("open"):
            return False
        dialog_kind = str(state.get("kind", "conversation") or "conversation").strip().lower()
        close_pending = bool(state.get("close_pending"))

        if key in (ord("?"), ord("/")):
            self._help_state()["open"] = True
            return True

        if dialog_kind in {"justice_surrender", "justice_questioning"}:
            if key in (27, ord("q"), ord("Q")):
                event_type = "justice_questioning_choice" if dialog_kind == "justice_questioning" else "justice_surrender_choice"
                choice_id = "refuse" if dialog_kind == "justice_questioning" else "resist"
                self.sim.emit(Event(
                    event_type,
                    eid=self.player_eid,
                    npc_eid=state.get("npc_eid"),
                    choice_id=choice_id,
                ))
                return True
            if key in (ord("o"), ord("O"), ord("y"), ord("Y"), ord("L"), ord("D"), ord("m"), ord("M")):
                return True

        if key in (27, ord("q"), ord("Q")):
            self._close_dialog_ui()
            return True

        if key in (ord("o"), ord("O")):
            self._close_dialog_ui()
            self._refresh_report_ui(reset_scroll=True)
            return True

        if key in (ord("y"), ord("Y")):
            self._close_dialog_ui()
            self._refresh_known_locations_ui(reset_scroll=True)
            return True

        if key == ord("L"):
            self._close_dialog_ui()
            self._refresh_log_ui(reset_scroll=True, focus_end=True)
            return True

        if key == ord("D"):
            if self._refresh_debug_ui(reset_scroll=True):
                self._close_dialog_ui()
            return True

        if key in (ord("x"), ord("X"), ord(";")) and dialog_kind == "conversation" and self._dialog_can_mark_backup_spot():
            self._activate_dialog_backup_marking()
            return True

        if close_pending and key == ord(" "):
            self._close_dialog_ui()
            return True

        if key in (ord("m"), ord("M")):
            if dialog_kind == "service_menu":
                return True
            topic = next(
                (row for row in list(state.get("topics", ()) or ()) if str(row.get("id", "")).strip().lower() == "trade"),
                None,
            )
            if topic:
                self.sim.emit(Event("dialog_topic_request", eid=self.player_eid, npc_eid=state.get("npc_eid"), topic_id="trade"))
            return True

        if key in (KEY_UP, ord("k"), ord("K")):
            state["selected_index"] = int(state.get("selected_index", 0)) - 1
            self._normalize_dialog_selection()
            return True

        if key in (KEY_DOWN, ord("j"), ord("J")):
            state["selected_index"] = int(state.get("selected_index", 0)) + 1
            self._normalize_dialog_selection()
            return True

        if ord("1") <= key <= ord("9"):
            state["selected_index"] = key - ord("1")
            self._normalize_dialog_selection()
            return True
        if key == ord("0"):
            state["selected_index"] = 9
            self._normalize_dialog_selection()
            return True

        key_home = KEY_HOME
        if key_home is not None and key == key_home:
            state["scroll"] = 0
            return True

        key_end = KEY_END
        if key_end is not None and key == key_end:
            display_lines = self._dialog_display_lines()
            _body_w, transcript_h, _option_h = self._dialog_body_dimensions()
            state["scroll"] = max(0, len(display_lines) - transcript_h)
            return True

        key_page_up = KEY_PAGE_UP
        if key_page_up is not None and key == key_page_up:
            state["scroll"] = int(state.get("scroll", 0)) - 6
            self._clamp_dialog_scroll()
            return True

        key_page_down = KEY_PAGE_DOWN
        if key_page_down is not None and key == key_page_down:
            state["scroll"] = int(state.get("scroll", 0)) + 6
            self._clamp_dialog_scroll()
            return True

        if key in ENTER_KEYS or key in (ord("e"), ord("E")):
            topic = self._selected_dialog_topic()
            if topic:
                topic_id = str(topic.get("id", "") or "").strip().lower()
                if dialog_kind == "justice_surrender":
                    self.sim.emit(Event(
                        "justice_surrender_choice",
                        eid=self.player_eid,
                        npc_eid=state.get("npc_eid"),
                        choice_id=topic.get("id"),
                    ))
                    return True
                if dialog_kind == "justice_questioning":
                    self.sim.emit(Event(
                        "justice_questioning_choice",
                        eid=self.player_eid,
                        npc_eid=state.get("npc_eid"),
                        choice_id=topic.get("id"),
                    ))
                    return True
                if dialog_kind == "service_menu":
                    self.sim.emit(Event(
                        "service_menu_execute_request",
                        eid=self.player_eid,
                        property_id=state.get("property_id"),
                        option_id=topic.get("id"),
                    ))
                    return True
                marked = self._dialog_backup_mark()
                if topic_id in {"backup_goto_wait", "backup_wait_return"} and not marked:
                    self._activate_dialog_backup_marking(pending_topic=topic_id)
                    return True
                if topic_id == "backup_kill" and not marked.get("target_eid"):
                    self._activate_dialog_backup_marking(pending_topic=topic_id)
                    return True
                self.sim.emit(Event(
                    "dialog_topic_request",
                    eid=self.player_eid,
                    npc_eid=state.get("npc_eid"),
                    topic_id=topic.get("id"),
                ))
            return True

        return True

    def _handle_report_input(self, key):
        return _report_debug_ui.handle_report_input(
            self,
            key,
            line_text_fn=_line_text,
            wrap_display_lines_fn=_wrap_display_lines,
        )

    def _handle_log_input(self, key):
        state = self._log_state()
        if not state.get("open"):
            return False

        if key in (ord("?"), ord("/")):
            self._help_state()["open"] = True
            return True

        if key in (ord("o"), ord("O")):
            self._close_log_ui()
            self._refresh_report_ui(reset_scroll=True)
            return True

        if key in (ord("y"), ord("Y")):
            self._close_log_ui()
            self._refresh_known_locations_ui(reset_scroll=True)
            return True

        if key in (ord("t"), ord("T")):
            self._cycle_log_view_filter(step=1, reset_scroll=True)
            return True

        if key in (ord("h"), ord("H")):
            self._set_hud_log_filter(state.get("view_filter", "all"))
            return True

        if key == ord("D"):
            if self._refresh_debug_ui(reset_scroll=True):
                self._close_log_ui()
            return True

        if key in (27, ord("l"), ord("L"), ord("q"), ord("Q")):
            self._close_log_ui()
            return True

        if key in (KEY_UP, ord("k"), ord("K")):
            state["scroll"] = int(state.get("scroll", 0)) - 1
            self._clamp_log_scroll()
            return True

        if key in (KEY_DOWN, ord("j"), ord("J")):
            state["scroll"] = int(state.get("scroll", 0)) + 1
            self._clamp_log_scroll()
            return True

        key_home = KEY_HOME
        if key_home is not None and key == key_home:
            state["scroll"] = 0
            return True

        key_end = KEY_END
        if key_end is not None and key == key_end:
            display_lines = self._log_display_lines()
            _body_w, body_h = self._scroll_panel_body_dimensions()
            state["scroll"] = max(0, len(display_lines) - body_h)
            return True

        key_page_up = KEY_PAGE_UP
        if key_page_up is not None and key == key_page_up:
            state["scroll"] = int(state.get("scroll", 0)) - 6
            self._clamp_log_scroll()
            return True

        key_page_down = KEY_PAGE_DOWN
        if key_page_down is not None and key == key_page_down:
            state["scroll"] = int(state.get("scroll", 0)) + 6
            self._clamp_log_scroll()
            return True

        return True

    def _handle_character_input(self, key):
        state = self._character_state()
        if not state.get("open"):
            return False

        if key in (ord("?"), ord("/")):
            self._help_state()["open"] = True
            return True

        if key in (ord("o"), ord("O")):
            self._close_character_ui()
            self._refresh_report_ui(reset_scroll=True)
            return True

        if key in (ord("y"), ord("Y")):
            self._close_character_ui()
            self._refresh_known_locations_ui(reset_scroll=True)
            return True

        if key == ord("L"):
            self._close_character_ui()
            self._refresh_log_ui(reset_scroll=True, focus_end=True)
            return True

        if key == ord("D"):
            if self._refresh_debug_ui(reset_scroll=True):
                self._close_character_ui()
            return True

        if ord("1") <= key <= ord("9"):
            page_index = key - ord("1")
            pages = list(state.get("pages", ()) or [])
            if 0 <= page_index < len(pages) and self._set_character_page(page_index, reset_scroll=False):
                return True

        key_left = KEY_LEFT
        if key_left is not None and key == key_left:
            self._cycle_character_page(step=-1)
            return True

        key_right = KEY_RIGHT
        if key_right is not None and key == key_right:
            self._cycle_character_page(step=1)
            return True

        key_back_tab = KEY_BACK_TAB
        if key_back_tab is not None and key == key_back_tab:
            self._cycle_character_page(step=-1)
            return True

        if key == ord("\t"):
            self._cycle_character_page(step=1)
            return True

        if key in (ord("+"), 27, ord("q"), ord("Q")):
            self._close_character_ui()
            return True

        if key in (KEY_UP, ord("k"), ord("K")):
            state["scroll"] = int(state.get("scroll", 0)) - 1
            self._clamp_character_scroll()
            return True

        if key in (KEY_DOWN, ord("j"), ord("J")):
            state["scroll"] = int(state.get("scroll", 0)) + 1
            self._clamp_character_scroll()
            return True

        key_home = KEY_HOME
        if key_home is not None and key == key_home:
            state["scroll"] = 0
            return True

        key_end = KEY_END
        if key_end is not None and key == key_end:
            display_lines = self._character_display_lines()
            _body_w, body_h = self._character_panel_body_dimensions()
            state["scroll"] = max(0, len(display_lines) - body_h)
            return True

        key_page_up = KEY_PAGE_UP
        if key_page_up is not None and key == key_page_up:
            state["scroll"] = int(state.get("scroll", 0)) - 6
            self._clamp_character_scroll()
            return True

        key_page_down = KEY_PAGE_DOWN
        if key_page_down is not None and key == key_page_down:
            state["scroll"] = int(state.get("scroll", 0)) + 6
            self._clamp_character_scroll()
            return True

        return True

    def _handle_debug_input(self, key):
        return _report_debug_ui.handle_debug_input(
            self,
            key,
            line_text_fn=_line_text,
            wrap_display_lines_fn=_wrap_display_lines,
        )

    def _sync_look_cursor_to_player(self, zoom_mode):
        positions = self.sim.ecs.get(Position)
        pos = positions.get(self.player_eid)
        if not pos:
            return False

        state = self._look_state()
        zoom_mode = str(zoom_mode).lower()
        state["mode"] = zoom_mode
        if zoom_mode == "overworld":
            cx, cy = self.sim.chunk_coords(pos.x, pos.y)
            state["chunk_x"] = int(cx)
            state["chunk_y"] = int(cy)
            state["z"] = 0
        else:
            state["x"] = int(pos.x)
            state["y"] = int(pos.y)
            state["z"] = int(pos.z)
        return True

    def _aim_target_eid_at_cursor(self):
        state = self._look_state()
        if str(state.get("mode", "city")).lower() != "city":
            return None

        return _first_targetable_entity_at(
            self.sim,
            int(state.get("x", 0)),
            int(state.get("y", 0)),
            int(state.get("z", 0)),
            exclude_eid=self.player_eid,
        )

    def _clear_aim_lock(self, *, release_pacing=True):
        state = self._aim_lock_state()
        had_lock = bool(state.get("active") or state.get("target_eid") is not None)
        state["active"] = False
        state["target_eid"] = None
        state.pop("target_x", None)
        state.pop("target_y", None)
        state.pop("target_z", None)
        if release_pacing:
            _set_manual_combat_pacing(self.sim, False)
        return had_lock

    def _aim_lock_target_position(self, target_eid=None):
        state = self._aim_lock_state()
        if target_eid is None:
            target_eid = state.get("target_eid")
        try:
            target_eid = int(target_eid)
        except (TypeError, ValueError):
            return None
        positions = self.sim.ecs.get(Position)
        target_pos = positions.get(target_eid)
        player_pos = positions.get(self.player_eid)
        if not target_pos or not player_pos:
            return None
        if int(target_pos.z) != int(player_pos.z):
            return None
        vitality = self.sim.ecs.get(Vitality).get(target_eid)
        if vitality and (bool(getattr(vitality, "downed", False)) or int(getattr(vitality, "hp", 1)) <= 0):
            return None
        if not _entity_visible_to_player(self.sim, self.player_eid, target_eid):
            return None
        return target_pos

    def _aim_lock_target_eid(self):
        state = self._aim_lock_state()
        if not bool(state.get("active")):
            return None
        target_eid = state.get("target_eid")
        target_pos = self._aim_lock_target_position(target_eid)
        if not target_pos:
            self._clear_aim_lock()
            return None
        state["target_x"] = int(target_pos.x)
        state["target_y"] = int(target_pos.y)
        state["target_z"] = int(target_pos.z)
        return int(target_eid)

    def _set_aim_lock_target(self, target_eid):
        target_pos = self._aim_lock_target_position(target_eid)
        if not target_pos:
            return False
        state = self._aim_lock_state()
        state["active"] = True
        state["target_eid"] = int(target_eid)
        state["target_x"] = int(target_pos.x)
        state["target_y"] = int(target_pos.y)
        state["target_z"] = int(target_pos.z)
        _set_manual_combat_pacing(self.sim, True)
        return True

    def _emit_locked_fire(self):
        target_eid = self._aim_lock_target_eid()
        if target_eid is None:
            self.sim.log.add("Aim: target lost.")
            return True
        target_pos = self._aim_lock_target_position(target_eid)
        if not target_pos:
            self.sim.log.add("Aim: target lost.")
            self._clear_aim_lock()
            return True
        self._emit_turn_action(
            "fire_weapon",
            manual_aim=False,
            target_eid=target_eid,
            target_x=int(target_pos.x),
            target_y=int(target_pos.y),
            target_z=int(target_pos.z),
        )
        return True

    def _emit_aimed_fire(self):
        state = self._look_state()
        if str(state.get("mode", "city")).lower() != "city":
            return False

        self._emit_turn_action(
            "fire_weapon",
            manual_aim=True,
            target_x=int(state.get("x", 0)),
            target_y=int(state.get("y", 0)),
            target_z=int(state.get("z", 0)),
            target_eid=self._aim_target_eid_at_cursor(),
        )
        return True

    def _emit_throw_item(self):
        state = self._look_state()
        if str(state.get("mode", "city")).lower() != "city":
            return False
        instance_id = str(state.get("throw_item_instance_id", "") or "").strip()
        if not instance_id:
            return False
        self.sim.turn_advance_requested = True
        self.sim.emit(Event(
            "throw_item_request",
            eid=self.player_eid,
            item_instance_id=instance_id,
            target_x=int(state.get("x", 0)),
            target_y=int(state.get("y", 0)),
            target_z=int(state.get("z", 0)),
            reason="inventory_panel",
        ))
        self._deactivate_look_mode()
        return True

    def _activate_throw_item_targeting(self, entry):
        if not isinstance(entry, dict):
            return False
        item_def = self.catalog.get(entry.get("item_id"), {})
        throw_profile = item_def.get("throw_profile") if isinstance(item_def.get("throw_profile"), dict) else None
        if not throw_profile:
            return False
        pos = self.sim.ecs.get(Position).get(self.player_eid)
        if not pos:
            return False
        target_x = int(pos.x) + 1 if self.sim.tilemap.in_bounds(int(pos.x) + 1, int(pos.y)) else int(pos.x)
        target_y = int(pos.y)
        item_name = item_display_name_for_actor(self.sim, self.player_eid, entry, item_catalog=self.catalog)
        self._close_inventory_ui()
        if not self._activate_look_mode_at("city", x=target_x, y=target_y, z=int(pos.z), purpose="throw"):
            return False
        state = self._look_state()
        state["throw_item_instance_id"] = str(entry.get("instance_id", "") or "").strip()
        state["throw_item_name"] = item_name
        summary = throwable_summary_text(throw_profile, include_consumed=True)
        state["inspect_text"] = f"Throwing {item_name}: {summary}. Enter throws; Esc cancels."
        return True

    def _aim_cycle_candidates(self):
        positions = self.sim.ecs.get(Position)
        ais = self.sim.ecs.get(AI)
        identities = self.sim.ecs.get(CreatureIdentity)
        vitalities = self.sim.ecs.get(Vitality)
        player_pos = positions.get(self.player_eid)
        if not player_pos:
            return []

        loadout, weapon, _instance = _weapon_context_for_entity(self.sim, self.player_eid)
        if _entity_uses_melee_aim(self.sim, self.player_eid):
            max_range = 1
        else:
            max_range = int(max(1, weapon.get("range", 1))) if weapon else 12

        candidates = []
        for other_eid, other_pos in positions.items():
            if int(other_eid) == int(self.player_eid):
                continue
            if not (ais.get(other_eid) or identities.get(other_eid) or vitalities.get(other_eid)):
                continue
            if not _entity_visible_to_player(self.sim, self.player_eid, other_eid):
                continue
            if not other_pos or int(other_pos.z) != int(player_pos.z):
                continue
            vitality = vitalities.get(other_eid)
            if vitality and (bool(getattr(vitality, "downed", False)) or int(getattr(vitality, "hp", 1)) <= 0):
                continue

            dist = _grid_distance(player_pos.x, player_pos.y, other_pos.x, other_pos.y)
            if dist <= 0 or dist > max_range:
                continue

            threat_rank = 0 if _actor_is_direct_player_hostile(self.sim, other_eid, player_eid=self.player_eid) else 1
            candidates.append((
                int(threat_rank),
                int(dist),
                int(other_pos.y),
                int(other_pos.x),
                int(other_eid),
            ))

        candidates.sort()
        return [eid for _threat, _dist, _y, _x, eid in candidates]

    def _cycle_aim_target_lock(self, step=1):
        candidates = self._aim_cycle_candidates()
        if not candidates:
            self.sim.log.add("Aim: no visible living target in range.")
            self._clear_aim_lock()
            return True

        state = self._aim_lock_state()
        current_eid = state.get("target_eid") if bool(state.get("active")) else None
        try:
            current_eid = int(current_eid)
        except (TypeError, ValueError):
            current_eid = None
        if current_eid in candidates:
            idx = (candidates.index(current_eid) + int(step or 1)) % len(candidates)
        else:
            idx = 0 if int(step or 1) >= 0 else len(candidates) - 1
        target_eid = candidates[idx]

        if not self._set_aim_lock_target(target_eid):
            self.sim.log.add("Aim: target lost.")
            return True
        return True

    def _cycle_aim_target(self, step=1):
        state = self._look_state()
        if str(state.get("mode", "city")).lower() != "city":
            return False

        if not _entity_uses_melee_aim(self.sim, self.player_eid):
            self._deactivate_look_mode()
            return self._cycle_aim_target_lock(step=step)

        candidates = self._aim_cycle_candidates()
        if not candidates:
            self.sim.log.add("Aim: no visible living target in range.")
            return True

        current_eid = self._aim_target_eid_at_cursor()
        if current_eid in candidates:
            idx = (candidates.index(current_eid) + int(step or 1)) % len(candidates)
        else:
            idx = 0 if int(step or 1) >= 0 else len(candidates) - 1
        target_eid = candidates[idx]

        target_pos = self.sim.ecs.get(Position).get(target_eid)
        if not target_pos:
            return True

        state["x"] = int(target_pos.x)
        state["y"] = int(target_pos.y)
        state["z"] = int(target_pos.z)
        self._emit_cursor_examine(announce=True)
        return True

    def _activate_firearm_free_aim(self, zoom_mode):
        if str(zoom_mode or "city").strip().lower() != "city":
            return self._activate_look_mode(zoom_mode=zoom_mode, purpose="aim")
        target_eid = self._aim_lock_target_eid()
        if target_eid is not None:
            target_pos = self._aim_lock_target_position(target_eid)
            if target_pos:
                return self._activate_look_mode_at(
                    "city",
                    x=int(target_pos.x),
                    y=int(target_pos.y),
                    z=int(target_pos.z),
                    purpose="aim",
                )
        return self._activate_look_mode(zoom_mode=zoom_mode, purpose="aim")

    def _emit_cursor_examine(self, announce=False):
        state = self._look_state()
        mode = str(state.get("mode", "city")).lower()
        payload = {
            "announce": bool(announce),
            "cursor_mode": mode,
        }
        if mode == "overworld":
            payload["cursor_chunk_x"] = int(state.get("chunk_x", 0))
            payload["cursor_chunk_y"] = int(state.get("chunk_y", 0))
        else:
            payload["cursor_x"] = int(state.get("x", 0))
            payload["cursor_y"] = int(state.get("y", 0))
            payload["cursor_z"] = int(state.get("z", 0))
        self._emit_player_action("examine_cursor", consume_turn=False, **payload)

    def _activate_look_mode_at(self, mode, *, x=None, y=None, z=0, chunk_x=None, chunk_y=None, purpose="inspect", controller_cursor=False):
        state = self._look_state()
        mode = str(mode or "city").lower()
        self._reset_aim_hold_repeat()
        state["mode"] = mode
        if mode == "overworld":
            if chunk_x is None or chunk_y is None:
                return False
            state["chunk_x"] = int(chunk_x)
            state["chunk_y"] = int(chunk_y)
            state["z"] = 0
        else:
            if x is None or y is None:
                return False
            state["x"] = int(x)
            state["y"] = int(y)
            state["z"] = int(z)

        state["active"] = True
        state["purpose"] = str(purpose or "inspect").lower()
        state["controller_cursor"] = bool(controller_cursor)
        state["inspect_text"] = ""
        _set_manual_combat_pacing(self.sim, mode == "city" and str(state.get("purpose", "inspect")).lower() == "aim")
        self.sim.emit(Event(
            "look_mode_toggled",
            eid=self.player_eid,
            active=True,
            mode=str(state.get("mode", "city")).lower(),
            purpose=str(state.get("purpose", "inspect")).lower(),
        ))
        self._emit_cursor_examine(announce=True)
        return True

    def _activate_look_mode(self, zoom_mode, purpose="inspect"):
        if not self._sync_look_cursor_to_player(zoom_mode):
            return False

        state = self._look_state()
        if str(state.get("mode", "city")).lower() == "overworld":
            return self._activate_look_mode_at(
                "overworld",
                chunk_x=int(state.get("chunk_x", 0)),
                chunk_y=int(state.get("chunk_y", 0)),
                purpose=purpose,
            )
        return self._activate_look_mode_at(
            "city",
            x=int(state.get("x", 0)),
            y=int(state.get("y", 0)),
            z=int(state.get("z", 0)),
            purpose=purpose,
        )

    def _right_stick_cursor_purpose(self):
        if self._aim_lock_state().get("active"):
            return "aim"
        overlay = _combat_overlay_state(self.sim)
        if bool(getattr(self.sim, "turn_based", False) or overlay.get("active")):
            return "aim"
        return "inspect" if _entity_uses_melee_aim(self.sim, self.player_eid) else "aim"

    def _handle_right_stick_cursor(self, delta, zoom_mode):
        if delta is None:
            return False
        zoom_mode = str(zoom_mode or "city").strip().lower() or "city"
        if zoom_mode != "city":
            return False
        try:
            dx = max(-1, min(1, int(delta[0])))
            dy = max(-1, min(1, int(delta[1])))
        except (TypeError, ValueError, IndexError):
            return False
        if dx == 0 and dy == 0:
            return False

        key = self._canonical_movement_key_for_delta.get((dx, dy))
        if key is None:
            return False

        state = self._look_state()
        if bool(state.get("active")) and str(state.get("mode", "city")).strip().lower() == "city":
            state["controller_cursor"] = True
            return self._handle_look_input(key, zoom_mode)

        positions = self.sim.ecs.get(Position)
        pos = positions.get(self.player_eid)
        if not pos:
            return False
        target_x = int(pos.x) + dx
        target_y = int(pos.y) + dy
        if not self.sim.tilemap.in_bounds(target_x, target_y):
            return False
        purpose = str(state.get("purpose", "") or "").strip().lower() if bool(state.get("active")) else ""
        if not purpose or purpose == "inspect":
            purpose = self._right_stick_cursor_purpose()
        return self._activate_look_mode_at(
            "city",
            x=target_x,
            y=target_y,
            z=int(pos.z),
            purpose=purpose,
            controller_cursor=True,
        )

    def _activate_overworld_browse_cursor(self, *, dx=0, dy=0, purpose="inspect"):
        positions = self.sim.ecs.get(Position)
        pos = positions.get(self.player_eid)
        if not pos:
            return False

        current_chunk = self.sim.chunk_coords(pos.x, pos.y)
        state = self._look_state()
        if bool(state.get("active")) and str(state.get("mode", "")).strip().lower() == "overworld":
            current_chunk = (
                int(state.get("chunk_x", current_chunk[0])),
                int(state.get("chunk_y", current_chunk[1])),
            )
        return self._activate_look_mode_at(
            "overworld",
            chunk_x=int(current_chunk[0]) + int(dx),
            chunk_y=int(current_chunk[1]) + int(dy),
            purpose=purpose,
        )

    def _stored_player_interact_direction(self):
        state = getattr(self.sim, "player_interact_directions", None)
        if not isinstance(state, dict):
            return None
        remembered = state.get(int(self.player_eid))
        if not isinstance(remembered, dict):
            return None
        direction = _normalized_direction(remembered.get("dx", 0), remembered.get("dy", 0))
        return None if direction == (0, 0) else direction

    def _default_adjacent_interact_cursor(self, pos):
        if pos is None:
            return None

        steps = [
            (0, -1),
            (1, 0),
            (0, 1),
            (-1, 0),
            (-1, -1),
            (1, -1),
            (1, 1),
            (-1, 1),
        ]
        preferred = self._stored_player_interact_direction()
        if preferred in steps:
            steps = [preferred] + [step for step in steps if step != preferred]

        best = None
        for index, (dx, dy) in enumerate(steps):
            x = int(pos.x) + int(dx)
            y = int(pos.y) + int(dy)
            z = int(pos.z)
            if not self.sim.tilemap.in_bounds(x, y):
                continue

            rank = 3
            if _operable_door_state_at(self.sim, x, y, z) is not None:
                rank = 0
            elif any(int(other_eid) != int(self.player_eid) for other_eid in self.sim.tilemap.entities_at(x, y, z)):
                rank = 1
            elif self.sim.property_at(x, y, z) or _property_covering(self.sim, x, y, z):
                rank = 2

            row = (rank, index, x, y, z)
            if best is None or row < best:
                best = row

        if best is None:
            for default_dx, default_dy in ([preferred] if preferred else []) + steps:
                if default_dx is None or default_dy is None:
                    continue
                x = int(pos.x) + int(default_dx)
                y = int(pos.y) + int(default_dy)
                if self.sim.tilemap.in_bounds(x, y):
                    return (int(x), int(y), int(pos.z))
            return None
        return (int(best[2]), int(best[3]), int(best[4]))

    def _talk_target_eid_at(self, x, y, z):
        try:
            x = int(x)
            y = int(y)
            z = int(z)
        except (TypeError, ValueError):
            return None
        positions = self.sim.ecs.get(Position)
        ais = self.sim.ecs.get(AI)
        players = self.sim.ecs.get(PlayerControlled)
        identities = self.sim.ecs.get(CreatureIdentity)
        occupations = self.sim.ecs.get(Occupation)
        candidates = []
        for other_eid in self.sim.tilemap.entities_at(x, y, z):
            if int(other_eid) == int(self.player_eid):
                continue
            if players.get(other_eid):
                continue
            if not ais.get(other_eid):
                continue
            other_pos = positions.get(other_eid)
            if not other_pos or int(other_pos.z) != z:
                continue
            identity = identities.get(other_eid)
            humanish = int(bool(identity and identity.taxonomy_class == "hominid"))
            has_job = int(bool(occupations.get(other_eid)))
            candidates.append((-humanish, -has_job, int(other_eid)))
        if not candidates:
            return None
        candidates.sort()
        return candidates[0][2]

    def _talk_target_is_visible(self, pos, target_x, target_y, target_z):
        if pos is None:
            return False
        try:
            target_x = int(target_x)
            target_y = int(target_y)
            target_z = int(target_z)
        except (TypeError, ValueError):
            return False
        if int(target_z) != int(pos.z):
            return False
        if _manhattan(pos.x, pos.y, target_x, target_y) > 2:
            return False
        return _has_line_of_sight(
            self.sim,
            int(pos.x),
            int(pos.y),
            int(pos.z),
            target_x,
            target_y,
            target_z,
        )

    def _default_talk_cursor(self, pos):
        if pos is None:
            return None
        positions = self.sim.ecs.get(Position)
        ais = self.sim.ecs.get(AI)
        players = self.sim.ecs.get(PlayerControlled)
        identities = self.sim.ecs.get(CreatureIdentity)
        occupations = self.sim.ecs.get(Occupation)
        candidates = []
        for other_eid, other_pos in positions.items():
            if other_eid == self.player_eid:
                continue
            if players.get(other_eid):
                continue
            if not ais.get(other_eid):
                continue
            if other_pos.z != pos.z:
                continue
            dist = _manhattan(pos.x, pos.y, other_pos.x, other_pos.y)
            if dist <= 0 or dist > 2:
                continue
            if not self._talk_target_is_visible(pos, other_pos.x, other_pos.y, other_pos.z):
                continue
            identity = identities.get(other_eid)
            humanish = int(bool(identity and identity.taxonomy_class == "hominid"))
            has_job = int(bool(occupations.get(other_eid)))
            sort_key = _interaction_target_order_key(
                pos.x,
                pos.y,
                other_pos.x,
                other_pos.y,
                stable_tiebreaker=(dist, -humanish, -has_job, int(other_eid)),
            )
            candidates.append((sort_key, int(other_pos.x), int(other_pos.y), int(other_pos.z)))
        if not candidates:
            return None
        candidates.sort(key=lambda row: row[0])
        return (candidates[0][1], candidates[0][2], candidates[0][3])

    def _activate_talk_helper(self, zoom_mode):
        if str(zoom_mode or "city").strip().lower() != "city":
            return False

        positions = self.sim.ecs.get(Position)
        pos = positions.get(self.player_eid)
        if pos is None:
            return False

        target = self._default_talk_cursor(pos)
        if target is None:
            return False

        return self._activate_look_mode_at(
            "city",
            x=int(target[0]),
            y=int(target[1]),
            z=int(target[2]),
            purpose="talk",
        )

    def _activate_adjacent_interact_helper(self, zoom_mode):
        if str(zoom_mode or "city").strip().lower() != "city":
            return False

        positions = self.sim.ecs.get(Position)
        pos = positions.get(self.player_eid)
        if pos is None:
            return False

        target = self._default_adjacent_interact_cursor(pos)
        if target is None:
            return False

        return self._activate_look_mode_at(
            "city",
            x=int(target[0]),
            y=int(target[1]),
            z=int(target[2]),
            purpose="interact",
        )

    def _deactivate_look_mode(self):
        state = self._look_state()
        if not state.get("active"):
            return False

        was_aim = str(state.get("purpose", "inspect")).lower() == "aim"
        self._reset_aim_hold_repeat()
        state["active"] = False
        state["inspect_text"] = ""
        state["throw_item_instance_id"] = None
        state["throw_item_name"] = ""
        state["controller_cursor"] = False
        if was_aim:
            self._clear_aim_lock(release_pacing=False)
            _set_manual_combat_pacing(self.sim, False)
        self.sim.emit(Event(
            "look_mode_toggled",
            eid=self.player_eid,
            active=False,
            mode=str(state.get("mode", "city")).lower(),
            purpose=str(state.get("purpose", "inspect")).lower(),
        ))
        state["purpose"] = "inspect"
        return True

    def _handle_look_input(self, key, zoom_mode):
        state = self._look_state()
        if not state.get("active"):
            return False

        mode = str(state.get("mode", "city")).lower()
        purpose = str(state.get("purpose", "inspect")).lower()
        zoom_mode = str(zoom_mode).lower()
        if mode != zoom_mode:
            if not self._sync_look_cursor_to_player(zoom_mode):
                return True
            mode = zoom_mode
            self._emit_cursor_examine(announce=False)

        if key == ord("?"):
            self._help_state()["open"] = True
            return True

        if key in (27, ord("Q")):
            if purpose == "backup_order":
                dialog_state = self._dialog_state()
                dialog_state["backup_cursor_pending_topic"] = ""
                dialog_state["hint"] = "Order mark canceled."
            if purpose == "interact" and key == 27:
                self._deactivate_look_mode()
                self._emit_turn_action("interact")
                return True
            self._deactivate_look_mode()
            return True

        if key == ord("T") and mode == "city":
            target_x = int(state.get("x", 0))
            target_y = int(state.get("y", 0))
            target_z = int(state.get("z", 0))
            target_eid = None
            if purpose == "aim":
                target_eid = _first_targetable_entity_at(
                    self.sim,
                    target_x,
                    target_y,
                    target_z,
                    exclude_eid=self.player_eid,
                )
            self._emit_player_action(
                "tactical_read",
                consume_turn=self._tactical_read_consumes_turn(),
                purpose=purpose,
                target_x=target_x,
                target_y=target_y,
                target_z=target_z,
                target_eid=target_eid,
            )
            return True

        if key in self.movement_keys:
            dx, dy = self.movement_keys[key]
            if mode == "overworld":
                state["chunk_x"] = int(state.get("chunk_x", 0)) + int(dx)
                state["chunk_y"] = int(state.get("chunk_y", 0)) + int(dy)
            else:
                nx = int(state.get("x", 0)) + int(dx)
                ny = int(state.get("y", 0)) + int(dy)
                if self.sim.tilemap.in_bounds(nx, ny):
                    if purpose == "interact":
                        player_pos = self.sim.ecs.get(Position).get(self.player_eid)
                        if player_pos:
                            tx = int(player_pos.x) + int(dx)
                            ty = int(player_pos.y) + int(dy)
                            if self.sim.tilemap.in_bounds(tx, ty):
                                state["x"] = tx
                                state["y"] = ty
                    elif purpose == "talk":
                        player_pos = self.sim.ecs.get(Position).get(self.player_eid)
                        if player_pos:
                            if _manhattan(player_pos.x, player_pos.y, nx, ny) <= 2:
                                state["x"] = nx
                                state["y"] = ny
                                state["z"] = int(player_pos.z)
                    elif purpose == "aim" and _entity_uses_melee_aim(self.sim, self.player_eid):
                        player_pos = self.sim.ecs.get(Position).get(self.player_eid)
                        if player_pos:
                            ddx = int(nx) - int(player_pos.x)
                            ddy = int(ny) - int(player_pos.y)
                            # Melee reticle is constrained to the 8 surrounding tiles.
                            if max(abs(ddx), abs(ddy)) == 1:
                                state["x"] = nx
                                state["y"] = ny
                        else:
                            state["x"] = nx
                            state["y"] = ny
                    else:
                        state["x"] = nx
                        state["y"] = ny
            if purpose == "aim":
                self._mark_aim_hold_direction(key)
            self._emit_cursor_examine(announce=False)
            return True

        if mode == "overworld" and key == ord("t"):
            self._deactivate_look_mode()
            self._emit_turn_action("zoom_city_enter")
            return True

        if purpose == "aim":
            if key in (ord("f"), ord("F")):
                self._cycle_aim_target(step=-1 if key == ord("F") else 1)
                return True
            if key == ord("\t") and not _entity_uses_melee_aim(self.sim, self.player_eid):
                self._deactivate_look_mode()
                return True
            if key in ENTER_KEYS:
                self._emit_aimed_fire()
                return True
            if key == ord("x"):
                self._emit_cursor_examine(announce=True)
                return True
            return True

        if purpose == "throw":
            if key in ENTER_KEYS:
                self._emit_throw_item()
                return True
            if key == ord("x"):
                self._emit_cursor_examine(announce=True)
                return True
            return True

        if purpose == "interact":
            if key == ord(";"):
                self._emit_turn_action(
                    "toggle_door_lock",
                    target_x=int(state.get("x", 0)),
                    target_y=int(state.get("y", 0)),
                    target_z=int(state.get("z", 0)),
                )
                self._deactivate_look_mode()
                return True
            if key in ENTER_KEYS or key == ord("'"):
                self._emit_turn_action(
                    "interact",
                    force_direction=True,
                    target_x=int(state.get("x", 0)),
                    target_y=int(state.get("y", 0)),
                    target_z=int(state.get("z", 0)),
                )
                self._deactivate_look_mode()
                return True
            if key == ord("x"):
                self._emit_cursor_examine(announce=True)
                return True
            return True

        if purpose == "talk":
            if key in ENTER_KEYS or key == ord("/"):
                target_x = int(state.get("x", 0))
                target_y = int(state.get("y", 0))
                target_z = int(state.get("z", 0))
                self._emit_player_action(
                    "talk",
                    consume_turn=False,
                    force_target=True,
                    target_eid=self._talk_target_eid_at(target_x, target_y, target_z),
                    target_x=target_x,
                    target_y=target_y,
                    target_z=target_z,
                )
                self._deactivate_look_mode()
                return True
            if key == ord("x"):
                self._emit_cursor_examine(announce=True)
                return True
            return True

        if purpose == "backup_order":
            if key in ENTER_KEYS or key in (ord("e"), ord("E")):
                self._commit_dialog_backup_mark()
                return True
            if key == ord("x"):
                self._emit_cursor_examine(announce=True)
                return True
            return True

        if key in ENTER_KEYS or key == ord("x"):
            self._emit_cursor_examine(announce=True)
            return True

        return True

    def _emit_player_action(self, action, consume_turn=False, **data):
        if consume_turn:
            self.sim.turn_advance_requested = True
        self.sim.emit(Event(
            "player_action",
            eid=self.player_eid,
            action=action,
            **data,
        ))

    def _emit_turn_action(self, action, **data):
        self._emit_player_action(action, consume_turn=True, **data)

    def _execute_action(self, action_id, *, key=None, zoom_mode=None):
        action_id = str(action_id or "").strip()
        zoom_mode = str(zoom_mode if zoom_mode is not None else getattr(self.sim, "zoom_mode", "city")).strip().lower() or "city"
        if not action_id:
            return False

        if action_id == "help":
            self._help_state()["open"] = True
            return True
        if action_id == "action_menu":
            return self._open_action_menu(zoom_mode)
        if action_id == "quit":
            self.sim.running = False
            self.sim.emit(Event("quit_requested", eid=self.player_eid))
            return True

        state = self._inventory_state()
        trade_state = self._trade_state()
        if action_id == "inventory" and not state.get("open") and not trade_state.get("open"):
            self._open_player_inventory_ui()
            return True
        if action_id == "character" and not state.get("open") and not trade_state.get("open"):
            self._refresh_character_ui(reset_scroll=True)
            return True
        if action_id == "operations" and not state.get("open") and not trade_state.get("open"):
            self._refresh_report_ui(reset_scroll=True)
            return True
        if action_id == "notebooks" and not state.get("open") and not trade_state.get("open"):
            self._refresh_known_locations_ui(reset_scroll=True)
            return True
        if action_id == "event_log" and not state.get("open") and not trade_state.get("open"):
            self._refresh_log_ui(reset_scroll=True, focus_end=True)
            return True
        if action_id == "debug" and not state.get("open") and not trade_state.get("open"):
            self._refresh_debug_ui(reset_scroll=True)
            return True

        if zoom_mode == "overworld":
            if action_id == "map_enter_local":
                self._emit_turn_action("zoom_city_enter")
                return True
            if action_id == "overworld_scan":
                self._emit_turn_action("scan")
                return True
            if action_id == "marker_add":
                self._emit_player_action("overworld_marker_add", consume_turn=False)
                return True
            if action_id == "marker_list":
                self._emit_player_action("overworld_marker_list", consume_turn=False)
                return True
            if action_id == "marker_nearest":
                self._emit_player_action("overworld_marker_nearest", consume_turn=False)
                return True
            if action_id == "drive_to_marker":
                marker = self._preferred_overworld_marker()
                if marker:
                    self._start_overworld_drive_to_marker(marker)
                else:
                    _log_player_feedback(
                        self.sim,
                        "No destination marker. Use M or notebook G first.",
                        kind="movement",
                        dedupe_window=2,
                        dedupe_key="autodrive:no_marker",
                    )
                return True
            if action_id == "wait":
                self._emit_turn_action("wait")
                return True
            return False

        if action_id == "map" and not state.get("open") and not trade_state.get("open"):
            self._emit_player_action("zoom_overworld", consume_turn=False)
            return True
        if action_id == "drone_command":
            return self._open_drone_command_ui(zoom_mode)
        if action_id == "drone_sheet":
            return self._open_drone_sheet_ui(zoom_mode)
        if action_id == "look":
            self._activate_look_mode(zoom_mode=zoom_mode, purpose="inspect")
            return True
        if action_id == "free_aim":
            if zoom_mode != "overworld":
                self._activate_firearm_free_aim(zoom_mode)
            return True
        if action_id == "fire_locked":
            if zoom_mode != "overworld" and self._aim_lock_state().get("active"):
                self._emit_locked_fire()
            return True
        if action_id == "tactical_read":
            self._emit_player_action("tactical_read", consume_turn=self._tactical_read_consumes_turn())
            return True
        if action_id == "map_enter_local":
            if self._player_in_vehicle():
                self._emit_turn_action("zoom_city_enter")
            return True
        if action_id == "vehicle_headlights":
            self._toggle_vehicle_headlights()
            return True
        if action_id == "floor_up":
            self._emit_turn_action("floor_change", dz=1)
            return True
        if action_id == "floor_down":
            self._emit_turn_action("floor_change", dz=-1)
            return True
        if action_id == "wait":
            self._emit_turn_action("wait")
            return True
        if action_id == "sneak":
            self._emit_turn_action("toggle_sneak")
            return True
        if action_id == "lock":
            self._emit_turn_action("toggle_door_lock")
            return True
        if action_id == "talk":
            if not self._activate_talk_helper(zoom_mode):
                self._emit_player_action("talk", consume_turn=False)
            return True
        if action_id == "service":
            self._emit_player_action("service_interact", consume_turn=False)
            return True
        if action_id == "interact":
            if not self._activate_adjacent_interact_helper(zoom_mode):
                self._emit_turn_action("interact")
            return True
        if action_id == "side_entry":
            self._emit_turn_action("side_entry")
            return True
        if action_id == "window_entry":
            self._emit_turn_action("window_entry")
            return True
        if action_id == "forced_breach":
            self._emit_turn_action("forced_breach")
            return True
        if action_id == "pickup":
            self._emit_turn_action("pickup_item")
            return True
        if action_id == "drop":
            self._emit_turn_action("drop_item")
            return True
        if action_id == "use_item":
            self._emit_turn_action("use_item")
            return True
        if action_id == "purchase_property":
            self._emit_turn_action("purchase_property")
            return True
        if action_id == "cover_hop":
            self._emit_turn_action("cover_hop")
            return True
        if action_id == "cover":
            self._emit_turn_action("toggle_cover")
            return True
        if action_id in {"aim_target_next", "aim_target_prev"}:
            step = -1 if action_id == "aim_target_prev" else 1
            if not _entity_uses_melee_aim(self.sim, self.player_eid) and zoom_mode != "overworld":
                self._cycle_aim_target_lock(step=step)
            else:
                self._activate_look_mode(zoom_mode=zoom_mode, purpose="aim")
            return True
        if action_id == "cycle_weapon":
            self._emit_turn_action("cycle_weapon")
            return True
        return False

    def _tactical_read_consumes_turn(self):
        overlay = _combat_overlay_state(self.sim)
        return bool(getattr(self.sim, "turn_based", False) or overlay.get("active"))

    def _player_inventory(self):
        return self.sim.ecs.get(Inventory).get(self.player_eid)

    def _player_modes(self):
        return self.sim.ecs.get(PlayerModeState).get(self.player_eid)

    def _inventory_panel_kind(self):
        state = self._inventory_state()
        return str(state.get("panel_kind", "inventory")).strip().lower() or "inventory"

    def _inventory_container_kind(self):
        state = self._inventory_state()
        kind = str(state.get("container_kind", "")).strip().lower()
        if kind:
            return kind
        if self._inventory_panel_kind() == "container":
            return "container"
        return None

    def _inventory_container_label(self):
        state = self._inventory_state()
        label = str(state.get("container_label", "")).strip()
        if label:
            return label
        if self._inventory_container_kind() == "cache":
            return "Cache"
        if self._inventory_container_kind() == "scene":
            return "Cargo"
        if self._inventory_container_kind() == "bones":
            return "Stash"
        if self._inventory_container_kind() == CAMPFIRE_HERB_CACHE_KIND:
            return "Herbs"
        return "Container"

    def _inventory_container_view(self):
        state = self._inventory_state()
        view = str(state.get("container_view", state.get("cache_view", "pack"))).strip().lower() or "pack"
        return "pack" if view == "pack" else "container"

    def _inventory_container_instance_id(self):
        state = self._inventory_state()
        token = str(state.get("container_instance_id", "") or "").strip()
        return token or None

    def _inventory_container_capacity(self):
        state = self._inventory_state()
        try:
            return int(max(0, _int_or_default(state.get("container_capacity"), 0)))
        except (TypeError, ValueError):
            return 0

    def _inventory_container_property(self):
        state = self._inventory_state()
        property_id = str(state.get("property_id", "") or "").strip()
        if not property_id:
            return None
        return self.sim.properties.get(property_id)

    def _equipped_container_entry(self, container_instance_id=None):
        current = getattr(self.sim, "equipped_container", None)
        if not isinstance(current, dict):
            return None
        active_instance_id = str(current.get("instance_id", "") or "").strip()
        target_instance_id = str(container_instance_id or active_instance_id or "").strip()
        if not target_instance_id or target_instance_id != active_instance_id:
            return None
        inventory = self._player_inventory()
        if not inventory:
            return None
        entry = inventory.find(instance_id=target_instance_id)
        if not entry:
            return None
        item_def = self.catalog.get(entry["item_id"], {})
        container_profile = item_def.get("container", {})
        if not isinstance(container_profile, dict) or _int_or_default(container_profile.get("bonus_slots"), 0) <= 0:
            return None
        return entry

    def _worn_container_entries(self, container_instance_id=None):
        entry = self._equipped_container_entry(container_instance_id)
        inventory = self._player_inventory()
        if not entry or not inventory:
            return []
        return list(_inventory_entries_stowed_in_container(inventory, entry.get("instance_id")))

    def _worn_container_pack_entries(self, container_instance_id=None):
        inventory = self._player_inventory()
        if not inventory:
            return []
        entry = self._equipped_container_entry(container_instance_id)
        if not entry:
            return list(inventory.items)
        return list(_inventory_entries_loose_for_container(inventory, entry.get("instance_id")))

    def _equipped_container_panel_note(self, entry):
        if not isinstance(entry, dict):
            return ""
        item_def = self.catalog.get(entry.get("item_id"), {})
        container_profile = item_def.get("container", {}) if isinstance(item_def.get("container"), dict) else {}
        bonus_slots = max(0, _int_or_default(container_profile.get("bonus_slots"), 0))
        if bonus_slots <= 0:
            return ""
        accepts_note = str(container_profile.get("accepts_note", "") or "").strip()
        note = f"Equipped +{bonus_slots} slots"
        if accepts_note:
            note += f"; accepts {accepts_note}"
        return note

    def _container_inventory_entries(self, property_id=None, *, container_kind=None):
        property_id = str(property_id or "").strip()
        if not property_id:
            return []
        container_kind = str(container_kind or self._inventory_container_kind() or "container").strip().lower() or "container"
        return _property_runtime_container_entries(
            self.sim,
            property_id,
            container_kind=container_kind,
        )

    def _inventory_panel_entries(self):
        if self._inventory_panel_kind() == "container":
            if self._inventory_container_kind() == "worn":
                if self._inventory_container_view() == "pack":
                    return self._worn_container_pack_entries(self._inventory_container_instance_id())
                return self._worn_container_entries(self._inventory_container_instance_id())
            if self._inventory_container_view() == "pack":
                inventory = self._player_inventory()
                entries = list(inventory.items) if inventory else []
                container_kind = self._inventory_container_kind()
                if container_kind == CAMPFIRE_HERB_CACHE_KIND:
                    return [
                        entry
                        for entry in entries
                        if entry_allowed_in_container(entry, container_kind=container_kind, item_catalog=self.catalog)
                    ]
                return entries
            container_prop = self._inventory_container_property()
            if not container_prop:
                return []
            return list(self._container_inventory_entries(
                container_prop.get("id"),
                container_kind=self._inventory_container_kind(),
            ))
        inventory = self._player_inventory()
        return list(inventory.items) if inventory else []

    def _cache_panel_mission_note(self, prop):
        if not isinstance(prop, dict):
            return ""
        property_id = str(prop.get("id", "") or "").strip()
        if not property_id:
            return ""
        cache_items = self._container_inventory_entries(property_id, container_kind="cache")
        for entry in cache_items:
            if not isinstance(entry, dict):
                continue
            metadata = entry.get("metadata", {}) if isinstance(entry.get("metadata"), dict) else {}
            if str(entry.get("owner_tag", "")).strip().lower() == "quest":
                return "Mission cache: retrieve assigned package"
            quest_kind = str(metadata.get("quest_kind", "")).strip().lower()
            if quest_kind:
                return f"Mission cache: {quest_kind.replace('_', ' ')}"
        return ""

    def _container_panel_note(self, prop, *, container_kind=None):
        container_kind = str(container_kind or self._inventory_container_kind() or "").strip().lower()
        if container_kind == "cache":
            return self._cache_panel_mission_note(prop)
        if container_kind == CAMPFIRE_HERB_CACHE_KIND:
            return campfire_herb_cache_note(self.sim, prop)
        if container_kind == "bones":
            metadata = prop.get("metadata") if isinstance((prop or {}).get("metadata"), dict) else {}
            note = str(metadata.get("bones_note", "") or "").strip()
            if note:
                return note
        metadata = prop.get("metadata") if isinstance((prop or {}).get("metadata"), dict) else {}
        note = str(metadata.get("container_note_text", "") or "").strip()
        if note:
            return note
        return ""

    def _set_inventory_panel_mode(
        self,
        *,
        panel_kind="inventory",
        title="Inventory",
        property_id=None,
        container_kind=None,
        container_label=None,
        container_instance_id=None,
        container_capacity=None,
        container_view=None,
        cache_view=None,
        note_text="",
        reset_selection=True,
        reset_inspect=True,
    ):
        state = self._inventory_state()
        state["panel_kind"] = str(panel_kind or "inventory").strip().lower() or "inventory"
        state["title"] = str(title or "Inventory").strip() or "Inventory"
        state["property_id"] = str(property_id or "").strip() or None
        normalized_kind = str(container_kind or "").strip().lower() or None
        state["container_kind"] = normalized_kind
        if container_view is None and cache_view is not None:
            container_view = "pack" if str(cache_view or "pack").strip().lower() == "pack" else "container"
        if container_label is None:
            if normalized_kind == "cache":
                container_label = "Cache"
            elif normalized_kind == "scene":
                container_label = "Cargo"
            elif normalized_kind == CAMPFIRE_HERB_CACHE_KIND:
                container_label = "Herbs"
            else:
                container_label = "Container"
        state["container_label"] = str(container_label or "Container").strip() or "Container"
        state["container_instance_id"] = str(container_instance_id or "").strip() or None
        state["container_capacity"] = (
            int(max(0, _int_or_default(container_capacity, 0)))
            if container_capacity is not None
            else None
        )
        if container_view is not None:
            normalized_view = str(container_view or "pack").strip().lower() or "pack"
            state["container_view"] = "pack" if normalized_view == "pack" else "container"
        state["cache_view"] = "pack" if str(state.get("container_view", "pack")).strip().lower() == "pack" else "cache"
        state["note_text"] = str(note_text or "").strip()
        if reset_selection:
            state["selected_index"] = 0
        if reset_inspect:
            state["inspect_text"] = ""

    def _emit_inventory_panel_toggled(self, *, open_state):
        state = self._inventory_state()
        self.sim.emit(Event(
            "inventory_panel_toggled",
            eid=self.player_eid,
            open=bool(open_state),
            panel_kind=str(state.get("panel_kind", "inventory")).strip().lower() or "inventory",
            title=str(state.get("title", "Inventory")).strip() or "Inventory",
            property_id=state.get("property_id"),
            container_kind=self._inventory_container_kind(),
            container_label=self._inventory_container_label(),
            container_instance_id=self._inventory_container_instance_id(),
        ))

    def _open_player_inventory_ui(self):
        self._set_inventory_panel_mode(
            panel_kind="inventory",
            title="Inventory",
            property_id=None,
            container_kind=None,
            container_label="Container",
            container_instance_id=None,
            container_capacity=None,
            container_view="pack",
            note_text="",
        )
        state = self._inventory_state()
        state["open"] = True
        self._normalize_inventory_selection()
        self._emit_inventory_panel_toggled(open_state=True)

    def _open_container_inventory_ui(
        self,
        prop,
        *,
        container_kind="container",
        container_label=None,
        container_instance_id=None,
        container_capacity=None,
        note_text="",
    ):
        if not isinstance(prop, dict):
            return False
        container_kind = str(container_kind or "container").strip().lower() or "container"
        if container_label is None:
            if container_kind == "cache":
                container_label = "Cache"
            elif container_kind == "scene":
                container_label = "Cargo"
            elif container_kind == CAMPFIRE_HERB_CACHE_KIND:
                container_label = "Herbs"
            else:
                container_label = "Container"
        if container_kind == CAMPFIRE_HERB_CACHE_KIND and container_capacity is None:
            container_capacity = CAMPFIRE_HERB_CACHE_CAPACITY
        container_name = str(prop.get("name", prop.get("id", container_label))).strip() or str(container_label)
        self._set_inventory_panel_mode(
            panel_kind="container",
            title=container_name,
            property_id=prop.get("id"),
            container_kind=container_kind,
            container_label=container_label,
            container_instance_id=container_instance_id,
            container_capacity=container_capacity,
            container_view="container",
            note_text=str(note_text or self._container_panel_note(prop, container_kind=container_kind)).strip(),
        )
        state = self._inventory_state()
        state["open"] = True
        self._normalize_inventory_selection()
        self._emit_inventory_panel_toggled(open_state=True)
        return True

    def _open_cache_inventory_ui(self, prop):
        return self._open_container_inventory_ui(
            prop,
            container_kind="cache",
            container_label="Cache",
            container_capacity=PlayerActionSystem.CACHE_MAX_STACKS,
        )

    def _open_equipped_container_item_ui(self, entry=None):
        entry = entry or self._selected_inventory_entry()
        if not isinstance(entry, dict):
            return False
        entry = self._equipped_container_entry(entry.get("instance_id"))
        if not entry:
            return False
        item_def = self.catalog.get(entry["item_id"], {})
        container_profile = item_def.get("container", {}) if isinstance(item_def.get("container"), dict) else {}
        bonus_slots = max(0, _int_or_default(container_profile.get("bonus_slots"), 0))
        if bonus_slots <= 0:
            return False
        item_name = item_display_name_for_actor(self.sim, self.player_eid, entry, item_catalog=self.catalog)
        return self._open_container_inventory_ui(
            {
                "id": entry.get("instance_id"),
                "name": item_name,
            },
            container_kind="worn",
            container_label=item_name,
            container_instance_id=entry.get("instance_id"),
            container_capacity=bonus_slots,
            note_text=self._equipped_container_panel_note(entry),
        )

    def _close_inventory_ui(self):
        state = self._inventory_state()
        was_open = bool(state.get("open"))
        state["open"] = False
        if was_open:
            self._emit_inventory_panel_toggled(open_state=False)
        self._set_inventory_panel_mode(
            panel_kind="inventory",
            title="Inventory",
            property_id=None,
            container_kind=None,
            container_label="Container",
            container_instance_id=None,
            container_capacity=None,
            container_view="pack",
            note_text="",
            reset_selection=False,
            reset_inspect=True,
        )

    def _toggle_container_inventory_view(self):
        if self._inventory_panel_kind() != "container":
            return False
        state = self._inventory_state()
        current = self._inventory_container_view()
        state["container_view"] = "pack" if current == "container" else "container"
        state["cache_view"] = "pack" if state["container_view"] == "pack" else "cache"
        state["selected_index"] = 0
        state["inspect_text"] = ""
        self._normalize_inventory_selection()
        return True

    def _toggle_cache_inventory_view(self):
        return self._toggle_container_inventory_view()

    def _normalize_inventory_selection(self):
        state = self._inventory_state()
        entries = self._inventory_panel_entries()
        if not entries:
            state["selected_index"] = 0
            return
        state["selected_index"] = max(0, min(int(state.get("selected_index", 0)), len(entries) - 1))

    def _selected_inventory_entry(self):
        self._normalize_inventory_selection()
        state = self._inventory_state()
        entries = self._inventory_panel_entries()
        if not entries:
            return None

        idx = int(state.get("selected_index", 0))
        if idx < 0 or idx >= len(entries):
            return None
        return entries[idx]

    def _normalize_trade_selection(self):
        state = self._trade_state()
        rows = list(state.get("rows", []))
        if not rows:
            state["selected_index"] = 0
            return
        state["selected_index"] = max(0, min(int(state.get("selected_index", 0)), len(rows) - 1))

    def _selected_trade_row(self):
        self._normalize_trade_selection()
        state = self._trade_state()
        rows = list(state.get("rows", []))
        if not rows:
            return None
        idx = int(state.get("selected_index", 0))
        if idx < 0 or idx >= len(rows):
            return None
        return rows[idx]

    def _inspect_selected_trade_row(self):
        state = self._trade_state()
        row = self._selected_trade_row()
        if not row:
            state["inspect_text"] = "No offers."
            return

        mode = str(state.get("mode", "buy"))
        if mode == "buy":
            interest_text = str(row.get("interest_label", "") or "").strip()
            risk_text = str(row.get("risk_label", "") or "").strip()
            extra_bits = [bit for bit in (interest_text, risk_text) if bit]
            extra_text = f"; {'; '.join(extra_bits)}" if extra_bits else ""
            state["inspect_text"] = _item_legend_line(
                row.get("item_id"),
                (
                    f"{row.get('item_name', row.get('item_id', 'item'))} "
                    f"price {int(row.get('price', 0))} credits "
                    f"stock {int(row.get('stock', 0))}"
                    f"{extra_text}"
                ),
            )
            return

        listed_text = "listed" if row.get("listed") else "unlisted"
        interest_text = str(row.get("interest_label", "") or "").strip()
        read_text = f"; {interest_text}" if interest_text else ""
        state["inspect_text"] = _item_legend_line(
            row.get("item_id"),
            (
                f"{row.get('item_name', row.get('item_id', 'item'))} "
                f"offer {int(row.get('price', 0))} credits ({listed_text}) "
                f"you carry {int(row.get('quantity', 0))}{read_text}"
            ),
        )

    def _inspect_selected_item(self):
        state = self._inventory_state()
        entry = self._selected_inventory_entry()
        if not entry:
            if self._inventory_panel_kind() == "container":
                view = self._inventory_container_view()
                note = str(state.get("note_text", "")).strip()
                if view == "container":
                    state["inspect_text"] = note or f"{self._inventory_container_label()} empty."
                else:
                    state["inspect_text"] = note or "Pack empty."
            else:
                state["inspect_text"] = "Inventory empty."
            self.sim.emit(Event(
                "inventory_inspected",
                eid=self.player_eid,
                empty=True,
                panel_kind=str(state.get("panel_kind", "inventory")).strip().lower() or "inventory",
                title=str(state.get("title", "Inventory")).strip() or "Inventory",
                container_kind=self._inventory_container_kind(),
                container_label=self._inventory_container_label(),
            ))
            return

        item_def = self.catalog.get(entry["item_id"], {})
        item_name = item_display_name_for_actor(self.sim, self.player_eid, entry, item_catalog=self.catalog)
        entry_instance_id = str(entry.get("instance_id", "") or "").strip() or None
        legal_status = item_def.get("legal_status", "legal")
        tags = list(item_def.get("tags", []))
        effects = list(item_def.get("effects", []))
        weapon_id = _item_weapon_id(item_def)
        armor = _item_armor_profile(item_def)

        identified = item_is_identified_for_actor(
            self.sim,
            self.player_eid,
            entry,
            item_catalog=self.catalog,
        )
        if not identified:
            appraise_item_for_actor(
                self.sim,
                self.player_eid,
                entry,
                item_catalog=self.catalog,
            )
            state["inspect_text"] = item_unknown_inspect_text_for_actor(
                self.sim,
                self.player_eid,
                entry,
                item_catalog=self.catalog,
            )
            self.sim.emit(Event(
                "inventory_inspected",
                eid=self.player_eid,
                item_id=entry["item_id"],
                item_name=item_name,
                quantity=entry["quantity"],
                legal_status="unknown",
                tags=[],
                effects=[],
                instance_id=entry_instance_id,
                identified=False,
                inspect_text=state["inspect_text"],
                panel_kind=str(state.get("panel_kind", "inventory")).strip().lower() or "inventory",
                title=str(state.get("title", "Inventory")).strip() or "Inventory",
                container_kind=self._inventory_container_kind(),
                container_label=self._inventory_container_label(),
            ))
            return

        effect_labels = []
        for effect in effects:
            etype = effect.get("type")
            if etype == "modify_need":
                need = effect.get("need")
                delta = effect.get("delta", 0)
                effect_labels.append(f"{need}:{delta:+}")
            elif etype == "restore_hp":
                delta = effect.get("delta", 0)
                effect_labels.append(f"hp:+{delta}")
            elif etype == "status":
                status = effect.get("status", "status")
                duration = effect.get("duration", 0)
                modifiers = effect.get("modifiers", {})
                effect_labels.append(
                    _status_effect_label(
                        status,
                        duration=duration,
                        modifiers=modifiers,
                        title=False,
                        limit=3,
                    )
                )

        substance_profile = item_def.get("substance_profile", {}) if isinstance(item_def.get("substance_profile"), dict) else {}
        if substance_profile.get("substance_id"):
            effect_labels.append("addictive")
            withdrawal_status = str(substance_profile.get("withdrawal_status", "") or "").strip().lower()
            if withdrawal_status:
                effect_labels.append(
                    f"withdrawal {_status_effect_label(withdrawal_status, title=False, limit=2)}"
                )

        if weapon_id:
            weapon = weapon_by_id(weapon_id)
            loadout = self.sim.ecs.get(WeaponLoadout).get(self.player_eid)
            equipped = bool(
                loadout
                and entry_instance_id
                and loadout.current_weapon() == weapon_id
                and isinstance(loadout.weapon_instances.get(weapon_id), dict)
                and str(loadout.weapon_instances[weapon_id].get("inventory_instance_id", "")).strip() == entry_instance_id
            )
            weapon_bits = [f"weapon dmg {int(weapon.get('base_damage', 0))}", f"rng {int(weapon.get('range', 1))}"]
            ammo_type = _weapon_ammo_type_label(weapon)
            if _weapon_uses_ammo(weapon):
                reserve = _weapon_reserve_ammo(loadout, weapon_id)
                if reserve is None and equipped and loadout:
                    reserve = int(loadout.reserve_ammo_value(
                        weapon_id,
                        default=_default_weapon_reserve_ammo(weapon),
                        instance_id=entry_instance_id,
                    ))
                if reserve is None:
                    weapon_bits.append(f"ammo {ammo_type}")
                else:
                    weapon_bits.append(f"ammo {ammo_type}:{reserve}")
            else:
                weapon_bits.append("ammo melee")
            if equipped:
                weapon_bits.append("equipped")
            effect_labels.extend(weapon_bits)

        if armor:
            armor_loadout = self.sim.ecs.get(ArmorLoadout).get(self.player_eid)
            reduction = int(round(float(armor.get("damage_reduction", 0.0)) * 100.0))
            armor_label = f"armor reduction {reduction}%"
            if armor_loadout and entry_instance_id and armor_loadout.is_equipped(entry_instance_id):
                armor_label += " equipped"
            effect_labels.append(armor_label)

        if is_appearance_item(entry, item_catalog=self.catalog):
            profile = appearance_metadata_for_entry(entry, item_catalog=self.catalog)
            slots = tuple(profile.get("slots", ()) or ())
            slot_text = "/".join(str(slot).replace("_", " ") for slot in slots) if slots else "slot?"
            color = str(profile.get("color", "") or "").strip()
            material = str(profile.get("material", "") or "").strip()
            style = str(profile.get("style", "") or "").strip()
            accent = str(profile.get("accent_color", "") or "").strip()
            wearable_bits = [f"wear {slot_text}"]
            if color or material or style:
                wearable_bits.append(" ".join(bit for bit in (style, color, material) if bit))
            if accent:
                wearable_bits.append(f"accent {accent}")
            if is_entry_worn(entry):
                wearable_bits.append("worn")
            effect_labels.extend(wearable_bits)

        disguise_profile = item_def.get("disguise", {}) if isinstance(item_def.get("disguise"), dict) else {}
        disguise_role_id = str(disguise_profile.get("role_id", "")).strip().lower()
        if disguise_role_id:
            disguise_bits = [f"disguise {_disguise_role_label(disguise_role_id)}"]
            active_disguise = getattr(self.sim, "disguise_state", None)
            if (
                isinstance(active_disguise, dict)
                and str(active_disguise.get("instance_id", "")).strip() == str(entry.get("instance_id", "")).strip()
            ):
                disguise_bits.append("equipped")
                strength_pct = int(round(max(0.0, float(active_disguise.get("strength", 0.0))) * 100.0))
                disguise_bits.append(f"{strength_pct}%")
            effect_labels.extend(disguise_bits)

        container_profile = item_def.get("container", {}) if isinstance(item_def.get("container"), dict) else {}
        bonus_slots = max(0, _int_or_default(container_profile.get("bonus_slots"), 0))
        if bonus_slots > 0:
            container_bits = [f"container +{bonus_slots}"]
            current_container = getattr(self.sim, "equipped_container", None)
            if isinstance(current_container, dict) and str(current_container.get("instance_id", "")).strip() == str(entry.get("instance_id", "")).strip():
                container_bits.append("equipped")
                stowed_count = len(self._worn_container_entries(entry.get("instance_id")))
                if stowed_count > 0:
                    container_bits.append(f"holds {stowed_count}")
            effect_labels.extend(container_bits)

        stowed_container_instance = _entry_stowed_container_instance(entry)
        current_container = getattr(self.sim, "equipped_container", None)
        if (
            stowed_container_instance
            and isinstance(current_container, dict)
            and str(current_container.get("instance_id", "")).strip() == stowed_container_instance
        ):
            container_name = str(current_container.get("item_name", "container") or "container").strip().lower() or "container"
            effect_labels.append(f"in {container_name}")

        throw_profile = item_def.get("throw_profile", {}) if isinstance(item_def.get("throw_profile"), dict) else {}
        if throw_profile:
            effect_labels.append(throwable_summary_text(throw_profile, include_consumed=True))

        effect_text = ", ".join(effect_labels) if effect_labels else "no active effect"
        state["inspect_text"] = _item_legend_line(
            entry["item_id"],
            f"{item_name} x{entry['quantity']} [{legal_status}] - {effect_text}",
        )

        self.sim.emit(Event(
            "inventory_inspected",
            eid=self.player_eid,
            item_id=entry["item_id"],
            item_name=item_name,
            quantity=entry["quantity"],
            legal_status=legal_status,
            tags=tags,
            effects=effects,
            instance_id=entry_instance_id,
            identified=True,
            inspect_text=state["inspect_text"],
            panel_kind=str(state.get("panel_kind", "inventory")).strip().lower() or "inventory",
            title=str(state.get("title", "Inventory")).strip() or "Inventory",
            container_kind=self._inventory_container_kind(),
            container_label=self._inventory_container_label(),
        ))

    def _handle_inventory_input(self, key):
        state = self._inventory_state()
        panel_kind = self._inventory_panel_kind()

        if key in (27, ord("i"), ord("I")):
            self._close_inventory_ui()
            return True

        if key in (ord("o"), ord("O")):
            self._close_inventory_ui()
            self._refresh_report_ui(reset_scroll=True)
            return True

        if key in (ord("y"), ord("Y")):
            self._close_inventory_ui()
            self._refresh_known_locations_ui(reset_scroll=True)
            return True

        if key == ord("L"):
            self._close_inventory_ui()
            self._refresh_log_ui(reset_scroll=True, focus_end=True)
            return True

        if key == ord("D"):
            if self._refresh_debug_ui(reset_scroll=True):
                self._close_inventory_ui()
            return True

        if panel_kind == "container" and key in (KEY_LEFT, KEY_RIGHT, ord("\t"), ord("["), ord("]")):
            self._toggle_container_inventory_view()
            return True

        choice = state.get("appearance_slot_choice") if isinstance(state.get("appearance_slot_choice"), dict) else None
        if choice:
            slots = tuple(choice.get("slots", ()) or ())
            selected_slot = None
            if key in (ord("1"), ord("l"), ord("L")) and len(slots) >= 1:
                selected_slot = str(slots[0])
            elif key in (ord("2"), ord("r"), ord("R")) and len(slots) >= 2:
                selected_slot = str(slots[1])
            elif key in (27, ord("q"), ord("Q")):
                state.pop("appearance_slot_choice", None)
                state["inspect_text"] = "Appearance slot choice cancelled."
                return True
            if selected_slot:
                state.pop("appearance_slot_choice", None)
                self.sim.turn_advance_requested = True
                self.sim.emit(Event(
                    "use_item_request",
                    eid=self.player_eid,
                    item_instance_id=choice.get("instance_id"),
                    preferred_appearance_slot=selected_slot,
                    reason="inventory_panel",
                ))
                return True
            labels = [
                f"{idx + 1} {APPEARANCE_SLOT_LABELS.get(slot, str(slot).replace('_', ' ').title())}"
                for idx, slot in enumerate(slots[:2])
            ]
            state["inspect_text"] = f"Choose slot: {' | '.join(labels)}."
            return True

        if key in (KEY_UP, ord("k"), ord("K")):
            state.pop("appearance_slot_choice", None)
            state["selected_index"] -= 1
            self._normalize_inventory_selection()
            return True

        if key in (KEY_DOWN, ord("j"), ord("J")):
            state.pop("appearance_slot_choice", None)
            state["selected_index"] += 1
            self._normalize_inventory_selection()
            return True
        if key is not None: #guard bad assumption
            if ord("1") <= key <= ord("9"):
                state.pop("appearance_slot_choice", None)
                state["selected_index"] = key - ord("1")
                self._normalize_inventory_selection()
                return True
            if key == ord("0"):
                state.pop("appearance_slot_choice", None)
                state["selected_index"] = 9
                self._normalize_inventory_selection()
                return True

        selected = self._selected_inventory_entry()
        if panel_kind == "container" and key in (ord("u"), ord("U")):
            self.sim.turn_advance_requested = True
            self.sim.emit(Event(
                "container_transfer_request",
                eid=self.player_eid,
                property_id=state.get("property_id"),
                container_kind=self._inventory_container_kind(),
                container_instance_id=self._inventory_container_instance_id(),
                container_view=self._inventory_container_view(),
                selected_index=int(state.get("selected_index", 0)),
                item_id=selected.get("item_id") if selected else None,
                instance_id=selected.get("instance_id") if selected else None,
            ))
            return True
        if panel_kind == "container" and key in (ord("r"), ord("R")):
            return True

        if key in (ord("u"), ord("U")):
            if selected:
                if (
                    panel_kind != "container"
                    and is_drone_workshop_part(selected.get("item_id"), item_catalog=self.catalog)
                ):
                    result = move_inventory_part_to_workshop(
                        self.sim,
                        self.player_eid,
                        selected.get("instance_id"),
                        item_catalog=self.catalog,
                    )
                    item_name = item_display_name_for_actor(
                        self.sim,
                        self.player_eid,
                        selected,
                        item_catalog=self.catalog,
                    )
                    if bool(result.get("ok")):
                        state["inspect_text"] = f"Stowed {item_name} in the drone workshop."
                        self.sim.emit(Event(
                            "drone_workshop_part_stowed",
                            eid=self.player_eid,
                            controller_eid=self.player_eid,
                            item_id=selected.get("item_id"),
                            item_name=item_name,
                            instance_id=selected.get("instance_id"),
                            quantity=selected.get("quantity", 1),
                        ))
                    else:
                        reason = str(result.get("reason", "blocked") or "blocked").replace("_", " ")
                        state["inspect_text"] = f"Drone workshop blocked: {reason}."
                        self.sim.emit(Event(
                            "drone_sheet_blocked",
                            eid=self.player_eid,
                            controller_eid=self.player_eid,
                            reason=result.get("reason", "blocked"),
                            action="inventory_stow",
                        ))
                    self._normalize_inventory_selection()
                    return True
                item_def = self.catalog.get(selected.get("item_id"), {})
                if isinstance(item_def.get("throw_profile"), dict):
                    self._activate_throw_item_targeting(selected)
                    return True
                if is_appearance_item(selected, item_catalog=self.catalog) and not is_entry_worn(selected):
                    profile = appearance_metadata_for_entry(selected, item_catalog=self.catalog)
                    slots = tuple(profile.get("slots", ()) or ())
                    if len(slots) > 1:
                        labels = [
                            f"{idx + 1} {APPEARANCE_SLOT_LABELS.get(slot, str(slot).replace('_', ' ').title())}"
                            for idx, slot in enumerate(slots[:2])
                        ]
                        state["appearance_slot_choice"] = {
                            "instance_id": selected["instance_id"],
                            "slots": slots[:2],
                        }
                        state["inspect_text"] = f"Choose slot: {' | '.join(labels)}."
                        return True
                self.sim.turn_advance_requested = True
                self.sim.emit(Event(
                    "use_item_request",
                    eid=self.player_eid,
                    item_instance_id=selected["instance_id"],
                    reason="inventory_panel",
                ))
            else:
                self.sim.turn_advance_requested = True
                self.sim.emit(Event("item_use_blocked", eid=self.player_eid, reason="no_usable_item"))
            return True

        if key in (ord("r"), ord("R")):
            self.sim.turn_advance_requested = True
            if selected:
                self.sim.emit(Event(
                    "drop_item_request",
                    eid=self.player_eid,
                    item_instance_id=selected["instance_id"],
                    reason="inventory_panel",
                ))
            else:
                self.sim.emit(Event("item_drop_blocked", eid=self.player_eid, reason="inventory_empty"))
            return True

        if key in ENTER_KEYS or key in (ord("e"), ord("E"), ord("x"), ord("X")):
            if panel_kind != "container" and self._open_equipped_container_item_ui(selected):
                return True
            self._inspect_selected_item()
            return True

        return False

    def _handle_trade_input(self, key):
        state = self._trade_state()

        if key in (27, ord("m"), ord("M")):
            self.sim.emit(Event("trade_panel_close_request", eid=self.player_eid))
            return True

        if key in (ord("o"), ord("O")):
            self.sim.emit(Event("trade_panel_close_request", eid=self.player_eid))
            self._refresh_report_ui(reset_scroll=True)
            return True

        if key in (ord("y"), ord("Y")):
            self.sim.emit(Event("trade_panel_close_request", eid=self.player_eid))
            self._refresh_known_locations_ui(reset_scroll=True)
            return True

        if key == ord("L"):
            self.sim.emit(Event("trade_panel_close_request", eid=self.player_eid))
            self._refresh_log_ui(reset_scroll=True, focus_end=True)
            return True

        if key == ord("D"):
            if debug_mode_enabled(self.sim):
                self.sim.emit(Event("trade_panel_close_request", eid=self.player_eid))
                self._refresh_debug_ui(reset_scroll=True)
            else:
                self._refresh_debug_ui(reset_scroll=True)
            return True

        if key in (KEY_UP, ord("k"), ord("K")):
            state["selected_index"] = int(state.get("selected_index", 0)) - 1
            self._normalize_trade_selection()
            self._inspect_selected_trade_row()
            return True

        if key in (KEY_DOWN, ord("j"), ord("J")):
            state["selected_index"] = int(state.get("selected_index", 0)) + 1
            self._normalize_trade_selection()
            self._inspect_selected_trade_row()
            return True

        if ord("1") <= key <= ord("9"):
            state["selected_index"] = key - ord("1")
            self._normalize_trade_selection()
            self._inspect_selected_trade_row()
            return True
        if key == ord("0"):
            state["selected_index"] = 9
            self._normalize_trade_selection()
            self._inspect_selected_trade_row()
            return True

        if key in (ord("b"), ord("B")):
            self.sim.emit(Event("trade_panel_mode_request", eid=self.player_eid, mode="buy"))
            return True

        if key in (ord("s"), ord("S")):
            self.sim.emit(Event("trade_panel_mode_request", eid=self.player_eid, mode="sell"))
            return True

        if key in (ord("x"), ord("X")):
            self._inspect_selected_trade_row()
            return True

        if key in ENTER_KEYS or key in (ord("e"), ord("E")):
            selected = self._selected_trade_row()
            self.sim.turn_advance_requested = True
            self.sim.emit(Event(
                "trade_execute_request",
                eid=self.player_eid,
                mode=state.get("mode", "buy"),
                selected_index=int(state.get("selected_index", 0)),
                item_id=selected.get("item_id") if selected else None,
                instance_id=selected.get("instance_id") if selected else None,
            ))
            return True

        return False

    def _player_move_speed_multiplier(self):
        return _entity_status_move_speed_multiplier(self.sim, self.player_eid)

    def _aim_repeat_timings(self):
        speed = self._player_move_speed_multiplier()
        initial_delay = max(0.04, min(0.28, 0.18 / max(0.25, float(speed))))
        repeat_interval = max(0.025, min(0.14, 0.075 / max(0.25, float(speed))))
        return float(initial_delay), float(repeat_interval)

    def _reset_aim_hold_repeat(self):
        self._aim_hold_repeat["delta"] = None
        self._aim_hold_repeat["pressed_at"] = 0.0
        self._aim_hold_repeat["last_repeat_at"] = 0.0

    def _mark_aim_hold_direction(self, key):
        delta = self.movement_keys.get(key)
        if not delta:
            self._reset_aim_hold_repeat()
            return
        now = time.monotonic()
        self._aim_hold_repeat["delta"] = (int(delta[0]), int(delta[1]))
        self._aim_hold_repeat["pressed_at"] = float(now)
        self._aim_hold_repeat["last_repeat_at"] = float(now)

    def _held_aim_repeat_key(self, look_state):
        if not look_state or not look_state.get("active"):
            self._reset_aim_hold_repeat()
            return None
        if bool(look_state.get("controller_cursor")):
            self._reset_aim_hold_repeat()
            return None
        if str(look_state.get("purpose", "inspect")).strip().lower() != "aim":
            self._reset_aim_hold_repeat()
            return None
        if str(look_state.get("mode", "city")).strip().lower() != "city":
            self._reset_aim_hold_repeat()
            return None

        held_delta_fn = getattr(self.view, "held_movement_delta", None)
        if not callable(held_delta_fn):
            return None

        held_delta = held_delta_fn()
        if not held_delta:
            self._reset_aim_hold_repeat()
            return None

        try:
            dx = int(held_delta[0])
            dy = int(held_delta[1])
        except (TypeError, ValueError, IndexError):
            self._reset_aim_hold_repeat()
            return None

        delta = (max(-1, min(1, dx)), max(-1, min(1, dy)))
        key = self._canonical_movement_key_for_delta.get(delta)
        if key is None:
            self._reset_aim_hold_repeat()
            return None

        now = time.monotonic()
        state = self._aim_hold_repeat
        if state.get("delta") != delta:
            state["delta"] = delta
            state["pressed_at"] = float(now)
            state["last_repeat_at"] = float(now)
            return None

        initial_delay, repeat_interval = self._aim_repeat_timings()
        if (float(now) - float(state.get("pressed_at", 0.0))) < initial_delay:
            return None
        if (float(now) - float(state.get("last_repeat_at", 0.0))) < repeat_interval:
            return None

        state["last_repeat_at"] = float(now)
        return key

    def _should_collapse_input_burst(self, *, look_state=None, help_state=None, dialog_state=None, character_state=None, report_state=None, log_state=None, debug_state=None, inventory_state=None, trade_state=None, drone_sheet_state=None):
        if help_state and help_state.get("open"):
            return False
        if dialog_state and dialog_state.get("open"):
            return False
        if character_state and character_state.get("open"):
            return False
        if report_state and report_state.get("open"):
            return False
        if log_state and log_state.get("open"):
            return False
        if debug_state and debug_state.get("open"):
            return False
        if inventory_state and inventory_state.get("open"):
            return False
        if trade_state and trade_state.get("open"):
            return False
        if drone_sheet_state and drone_sheet_state.get("open"):
            return False

        if look_state and look_state.get("active"):
            purpose = str(look_state.get("purpose", "inspect")).strip().lower() or "inspect"
            if purpose == "aim":
                return True

        return bool(getattr(self.sim, "turn_based", False))

    def _next_input_event(self, *, collapse_burst=False):
        if collapse_burst:
            drain_inputs = getattr(self.view, "drain_inputs", None)
            if callable(drain_inputs):
                inputs = [self._normalize_input_event(row) for row in drain_inputs()]
                inputs = [row for row in inputs if row is not None]
                if not inputs:
                    return None
                return inputs[-1]
            drain = getattr(self.view, "drain_keys", None)
            if callable(drain):
                keys = [key for key in drain() if key is not None]
                if not keys:
                    return None
                return key_physical_input(keys[-1])
        get_input = getattr(self.view, "get_input", None)
        if callable(get_input):
            return self._normalize_input_event(get_input())
        key = self.view.get_key()
        return key_physical_input(key) if key is not None else None

    def _next_input_key(self, *, collapse_burst=False):
        physical = self._next_input_event(collapse_burst=collapse_burst)
        return self._input_key_code(physical)

    def on_move_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        if self._auto_walk_state().get("active"):
            self._stop_auto_walk(reason="blocked", announce=False)

    def on_zoom_mode_changed(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        mode = str(event.data.get("mode", "city")).strip().lower() or "city"
        if self._auto_walk_state().get("active") and mode != "city":
            self._stop_auto_walk(reason="stopped", announce=False)
        if self._auto_drive_state().get("active") and mode != "overworld":
            self._stop_auto_drive(reason="stopped", announce=False)
        if self._local_drive_state().get("active") and mode == "overworld":
            self._stop_local_drive(reason="stopped", announce=False)

    def on_combat_overlay_entered(self, event):
        if self._auto_walk_state().get("active"):
            self._stop_auto_walk(reason="combat", announce=True)
        if self._auto_drive_state().get("active"):
            self._stop_auto_drive(reason="combat", announce=True)
        if self._local_drive_state().get("active"):
            self._stop_local_drive(reason="combat", announce=True, zero_speed=False)

    def on_vehicle_action_blocked(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        if self._auto_drive_state().get("active"):
            self._stop_auto_drive(reason="blocked", announce=False)
        if self._local_drive_state().get("active"):
            self._stop_local_drive(reason="blocked", announce=False)

    def on_vehicle_hard_stop(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        if self._local_drive_state().get("active"):
            self._stop_local_drive(reason="blocked", announce=False)

    def on_drone_command_target_changed(self, event):
        del event
        if bool(self._drone_command_state().get("open")):
            self._refresh_drone_command_ui(announce_unavailable=True)
        if bool(self._drone_sheet_state().get("open")):
            self._refresh_drone_sheet_ui(announce_unavailable=True)

    def on_chunk_stream_changed(self, event):
        del event
        state = self._report_state()
        if not bool(state.get("open")):
            return
        kind = str(state.get("kind", "progress")).strip().lower() or "progress"
        if kind == "known_locations":
            self._refresh_known_locations_ui(reset_scroll=False)
            return
        if kind != "known_people":
            return
        self._refresh_known_people_ui(reset_scroll=False)

    def update(self):

        state = self._inventory_state()
        trade_state = self._trade_state()
        dialog_state = self._dialog_state()
        look_state = self._look_state()
        help_state = self._help_state()
        character_state = self._character_state()
        report_state = self._report_state()
        log_state = self._log_state()
        debug_state = self._debug_state()
        action_menu_state = self._action_menu_state()
        drone_command_state = self._drone_command_state()
        drone_sheet_state = self._drone_sheet_state()
        zoom_mode = str(getattr(self.sim, "zoom_mode", "city")).lower()
        physical_input = self._next_input_event(
            collapse_burst=self._should_collapse_input_burst(
                look_state=look_state,
                help_state=help_state,
                dialog_state=dialog_state,
                character_state=character_state,
                report_state=report_state,
                log_state=log_state,
                debug_state=debug_state,
                inventory_state=state,
                trade_state=trade_state,
                drone_sheet_state=drone_sheet_state,
            )
        )
        key = self._input_key_code(physical_input)
        if physical_input is None and key is None:
            key = self._held_aim_repeat_key(look_state)
            physical_input = key_physical_input(key) if key is not None else None
        if physical_input is None and key is None:
            if drone_command_state.get("open"):
                self._refresh_drone_command_ui(announce_unavailable=True)
                return
            if drone_sheet_state.get("open"):
                self._refresh_drone_sheet_ui(announce_unavailable=True)
                return
            if action_menu_state.get("open"):
                return
            if self._maybe_continue_auto_walk(
                zoom_mode=zoom_mode,
                look_state=look_state,
                help_state=help_state,
                dialog_state=dialog_state,
                character_state=character_state,
                report_state=report_state,
                log_state=log_state,
                debug_state=debug_state,
                inventory_state=state,
                trade_state=trade_state,
                drone_sheet_state=drone_sheet_state,
            ):
                return
            if self._maybe_continue_local_drive(
                zoom_mode=zoom_mode,
                look_state=look_state,
                help_state=help_state,
                dialog_state=dialog_state,
                character_state=character_state,
                report_state=report_state,
                log_state=log_state,
                debug_state=debug_state,
                inventory_state=state,
                trade_state=trade_state,
                drone_sheet_state=drone_sheet_state,
            ):
                return
            if self._maybe_continue_auto_drive(
                zoom_mode=zoom_mode,
                look_state=look_state,
                help_state=help_state,
                dialog_state=dialog_state,
                character_state=character_state,
                report_state=report_state,
                log_state=log_state,
                debug_state=debug_state,
                inventory_state=state,
                trade_state=trade_state,
                drone_sheet_state=drone_sheet_state,
            ):
                return
            return

        self._record_recent_input_kind(physical_input)
        if self._auto_walk_state().get("active"):
            self._stop_auto_walk(reason="interrupted", announce=True)
        if self._auto_drive_state().get("active"):
            self._stop_auto_drive(reason="interrupted", announce=True)
        right_stick_delta = self._input_right_stick_delta(physical_input)
        movement_delta = self._input_movement_delta(physical_input)
        local_vehicle_key = (
            movement_delta is not None
            and zoom_mode != "overworld"
            and self._player_in_vehicle()
            and not self._local_drive_controls_blocked(zoom_mode=zoom_mode)
        )
        if self._local_drive_state().get("active") and not local_vehicle_key:
            self._stop_local_drive(reason="interrupted", announce=False)

        if help_state.get("open"):
            if key in ENTER_KEYS or key in (27, ord("?"), ord("q"), ord("Q")):
                help_state["open"] = False
                help_state["scroll"] = 0
            elif key in (KEY_UP, ord("k"), ord("K")):
                help_state["scroll"] = max(0, int(help_state.get("scroll", 0)) - 1)
            elif key in (KEY_DOWN, ord("j"), ord("J")):
                help_state["scroll"] = int(help_state.get("scroll", 0)) + 1
            elif key == KEY_HOME:
                help_state["scroll"] = 0
            elif key == KEY_END:
                help_state["scroll"] = 10**9
            elif key == KEY_PAGE_UP:
                help_state["scroll"] = max(0, int(help_state.get("scroll", 0)) - 6)
            elif key == KEY_PAGE_DOWN:
                help_state["scroll"] = int(help_state.get("scroll", 0)) + 6
            return

        if action_menu_state.get("open"):
            self._handle_action_menu_input(physical_input, zoom_mode)
            return

        if key == ord("?") and not look_state.get("active"):
            help_state["open"] = True
            return

        if drone_command_state.get("open"):
            self._handle_drone_command_input(physical_input, zoom_mode)
            return

        if drone_sheet_state.get("open"):
            self._handle_drone_sheet_input(physical_input, zoom_mode)
            return

        if look_state.get("active"):
            if right_stick_delta is not None:
                self._handle_right_stick_cursor(right_stick_delta, zoom_mode)
                return
            if (
                movement_delta is not None
                and bool(look_state.get("controller_cursor"))
                and self._input_is_left_stick_movement(physical_input)
            ):
                self._deactivate_look_mode()
                look_state = self._look_state()
            elif movement_delta is not None and bool(look_state.get("controller_cursor")) and self._input_is_controller(physical_input):
                return
            else:
                self._handle_look_input(key, zoom_mode)
                return
        if look_state.get("active"):
            self._handle_look_input(key, zoom_mode)
            return

        if self._casino_state().get("open"):
            self._handle_casino_input(key)
            return

        if dialog_state.get("open"):
            self._handle_dialog_input(key)
            return

        if character_state.get("open"):
            self._handle_character_input(key)
            return

        if report_state.get("open"):
            self._handle_report_input(key)
            return

        if log_state.get("open"):
            self._handle_log_input(key)
            return

        if debug_state.get("open"):
            self._handle_debug_input(key)
            return

        if key == 27 and self._aim_lock_state().get("active"):
            self._clear_aim_lock()
            return

        if state["open"]:
            if self._handle_inventory_input(key):
                return
            if key not in (ord("q"), ord("Q")):
                return

        if trade_state.get("open"):
            if self._handle_trade_input(key):
                return
            if key not in (ord("q"), ord("Q")):
                return

        if right_stick_delta is not None:
            if self._handle_right_stick_cursor(right_stick_delta, zoom_mode):
                return

        if key in ENTER_KEYS and zoom_mode != "overworld" and self._aim_lock_state().get("active"):
            self._emit_locked_fire()
            return

        if zoom_mode == "overworld":
            if movement_delta is not None:
                dx, dy = movement_delta
                self._record_action_anchor_delta(dx, dy)
                if self._overworld_view_only_for_player():
                    self._activate_overworld_browse_cursor(dx=dx, dy=dy, purpose="inspect")
                    return
                self._emit_turn_action("overworld_travel", dx=dx, dy=dy)
                return

            action_id = self._action_for_physical_or_key(physical_input, key, zoom_mode=zoom_mode)
            if action_id and self._execute_action(action_id, key=key, zoom_mode=zoom_mode):
                return

            if key == ACTION_MENU_KEY:
                self._open_action_menu(zoom_mode)
                return

            return

        if movement_delta is not None:
            dx, dy = movement_delta
            self._record_action_anchor_delta(dx, dy)
            action = "vehicle_move" if self._player_in_vehicle() else "move"
            consume_turn = True
            if action == "move" and bonus_move_available(self.sim, self.player_eid):
                spend_bonus_move(self.sim, self.player_eid, source="player_move")
                consume_turn = False
            self._emit_player_action(action, consume_turn=consume_turn, dx=dx, dy=dy)
            if action == "vehicle_move":
                self._sync_local_drive_after_vehicle_command(brake_tapped=dy > 0)
            return

        action_id = self._action_for_physical_or_key(physical_input, key, zoom_mode=zoom_mode)
        if action_id and self._execute_action(action_id, key=key, zoom_mode=zoom_mode):
            return

        if key == ACTION_MENU_KEY:
            self._open_action_menu(zoom_mode)
            return
