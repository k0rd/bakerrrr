"""Extracted systems from ``game.systems``: NPCInteractionSystem."""

from game.components import (
    AI,
    AnimalMemory,
    AnimalBehaviorContext,
    AnimalPhysicalProfile,
    AnimalSocialProfile,
    ArmorLoadout,
    BehaviorProfile,
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
from game.system_support.opportunity_knowledge_runtime import (
    rehydrate_entity_knowledge as _rehydrate_entity_knowledge,
)
from engine.events import Event
from game.items import (
    ITEM_CATALOG,
    apply_item_durability_loss,
    credstick_total_credits,
    is_credstick_item,
    item_display_name,
    item_instance_condition,
    merge_item_stack_metadata,
    prepare_item_stack_metadata,
)
from game.item_semantics import (
    appraise_item_for_actor,
    identify_item_for_actor,
    item_category,
    item_is_appraised_for_actor,
    item_is_identified_for_actor,
    item_legal_status,
    item_requires_identification,
    item_tags,
)
from game.human_identity import (
    conjugate_present,
    is_human_identity,
    player_address_term,
    pronoun_format_slots,
)
from game.human_description import human_conversation_description
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
from game.run_echoes import strongest_active_run_echo_for_chunk
from engine.systems import System
from game.skills import (
    access_prep_skill_terms as _access_prep_skill_terms,
    actor_skill as _actor_skill,
    dialogue_prep_skill_terms as _dialogue_prep_skill_terms,
    scan_skill_terms as _scan_skill_terms,
    skill_label as _skill_label,
    trade_skill_terms as _trade_skill_terms,
)
from game.system_support.actor_runtime import (
    _apply_downed_actor_state,
    _detail_tick_allowed,
    _entity_is_downed,
)
from game.system_support.ai_intent_runtime import _sync_ai_intent
from game.system_support.business_event_state import (
    _business_event_actor_note,
    _business_event_actor_state,
    _business_event_seed_state,
)
from game.system_support.container_runtime import _unlink_removed_item_from_gear
from game.run_pressure import (
    apply_pressure_delta as _apply_pressure_delta,
    pressure_effects as _pressure_effects,
    pressure_snapshot as _pressure_snapshot,
)
from game.dialogue_shape import (
    build_dialogue_shape as _build_dialogue_shape,
    build_rapport_shape as _build_rapport_shape,
    relationship_anchor_episode as _relationship_anchor_episode,
    relationship_episode_records as _relationship_episode_records,
    relationship_read_profile as _relationship_read_profile,
    social_reaction_narration as _social_reaction_narration,
    shaped_concern_line as _shaped_concern_line,
    shaped_local_line as _shaped_local_line,
    shaped_opening_lines as _shaped_opening_lines,
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
from game.checks import (
    crime_read_summary as _crime_read_summary,
    crime_sensitivity as _crime_sensitivity,
    justice_level as _justice_level,
    rumor_truth_read as _rumor_truth_read,
    social_read_axes as _social_read_axes,
)
from game.property_access import (
    PropertyIngressResult,
    _boundary_tile as _property_boundary_tile,
    apply_controller_intrusion as _apply_controller_intrusion,
    controller_intrusion_access_for_actor as _controller_intrusion_access_for_actor,
    controller_intrusion_state as _controller_intrusion_state,
    default_site_services_for_archetype as _default_site_services_for_archetype,
    _property_archetype,
    organization_guard_grace_active as _organization_guard_grace_active,
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
from game.dialogue_pressure import (
    dialogue_family_counts as _dialogue_family_counts,
    dialogue_topic_family as _dialogue_topic_family,
    repeated_topic_label as _repeated_topic_label,
    repeat_pressure_score as _repeat_pressure_score,
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
from game.system_support.entity_naming import _entity_display_name
from game.criminal_justice_runtime import _justice_snapshot
from game.system_support.interaction_ordering import (
    _direction_step,
    _interaction_target_order_key,
    _manhattan,
    _normalized_direction,
)
from game.system_support.npc_behavior_runtime import (
    BEHAVIOR_APPRAISE_STREET_GOODS,
    BEHAVIOR_BUY_DESIRED_DRUG,
    BEHAVIOR_BUY_PLAYER_GOODS,
    BEHAVIOR_IDENTIFY_STREET_DRUGS,
    _actor_behavior_value,
    _resolve_street_appraise_between_actors,
    _street_appraise_candidates_for_actor,
    _street_buy_candidate_rows_for_inventory,
    _street_buy_terms,
    _street_item_price,
    _street_item_value,
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
from game.system_support.settlement_runtime import _home_property
from game.player_businesses import (
    actor_player_business_employment,
    fire_actor_from_player_business,
    hire_actor_into_player_business,
    player_business_role_fit,
    player_business_staffing_targets,
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
from game.npc_judgment import evaluate_opportunity_judgment
from game.run_objectives import evaluate_visible_run_objective, reveal_run_objective
from game.organizations import (
    ensure_property_organization,
    local_protective_pressure_snapshot,
    occupation_targets_property,
    organization_name,
    primary_actor_membership,
    property_org_members,
    property_organization_eid,
    seed_property_organization_defaults,
    sync_actor_organization_affiliations,
)
import random
import re
from engine.sites import layout_chunk_site, site_gameplay_profile
from game.vehicles import (
    generate_chunk_vehicle_records,
    roll_vehicle_profile,
    vehicle_metadata,
    vehicle_services_for_archetype,
)

THREAT_STATES = {"protecting", "investigating"}


class NPCInteractionSystem(System):

    STATE_TEXT = {
        "idle": "between tasks",
        "patrolling": "on patrol",
        "resting": "taking it easy",
        "investigating": "watching the area",
        "protecting": "covering someone",
        "following": "watching your back",
        "holding": "holding position",
        "reporting_incident": "reporting trouble",
        "casing_target": "casing the block",
        "committing_property_crime": "working a soft target",
        "rendezvousing_crew": "waiting on a crew handoff",
        "evading_authority": "keeping clear of the law",
        "seeking_criminal_affiliation": "looking for a crew",
        "seeking_street_buyer": "trying to move some stock",
        "seeking_street_appraiser": "looking for someone to size up their stock",
        "seeking_social": "looking for company",
        "seeking_companionship": "sticking close to a companion",
        "soliciting_player": "trying to make a buy",
        "seeking_safety": "keeping their distance",
        "seeking_medical_aid": "trying to get patched up",
        "seeking_safe_spot": "looking for somewhere to lie low",
        "seeking_shelter": "looking for a place to crash",
        "surrendered": "standing down",
    }
    ROOT_TOPICS = {
        "name",
        "job",
        "rapport",
        "check_in",
        "local",
        "opportunities",
        "attention",
        "contacts",
        "where_place",
        "hire",
        "fire",
        "trade",
        "street_appraise",
        "street_buy",
        "street_buy_accept",
        "street_buy_next",
        "street_buy_decline",
        "bye",
        "purpose",
        "apologize",
        "leave",
    }
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
        "street_buy",
        "street_buy_accept",
        "street_buy_next",
        "street_buy_decline",
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
    CHECK_IN_MIN_HOURS = 1.0
    SENSITIVE_INFO_TOPICS = {"keyholder", "weak_point"}
    SENSITIVE_INFO_TRUSTED_BONDS = {"friend", "family", "partner", "coworker", "owner", "workplace", "job_issuer"}
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
        "service_contractor": {
            "services": ("building_repair", "business_remodel"),
            "service_label": "contractor",
            "offer_label": "building repair or remodel",
            "lead_kind": "service_contractor",
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
        "service_discreet_trade": {
            "services": (),
            "service_label": "discreet seller",
            "offer_label": "quiet trade",
            "lead_kind": "service_trade",
            "archetypes": ("backroom_market",),
            "covert": True,
            "hidden_lead": True,
            "local_summary": "If you need quiet trade, {names_text} is the kind of door people mention in this chunk.",
            "near_summary": "Nearest discreet seller I know is {distance_phrase} at {names_text}.",
        },
        "service_street_doctor": {
            "services": (),
            "service_label": "quiet doctor",
            "offer_label": "off-book medical help",
            "lead_kind": "service_medical",
            "archetypes": ("backroom_clinic",),
            "covert": True,
            "hidden_lead": True,
            "local_summary": "If you need help without paperwork, {names_text} is the kind of door people use in this chunk.",
            "near_summary": "Nearest quiet doctor I know is {distance_phrase} at {names_text}.",
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
                "street_buy_offer": None,
                "street_buy_skipped_instance_ids": [],
            }
        if not hasattr(self.sim, "dialogue_history"):
            self.sim.dialogue_history = {}
        if not hasattr(self.sim, "dialogue_guard_grace"):
            self.sim.dialogue_guard_grace = {}
        if not hasattr(self, "payoff_cooldown_ticks"):
            self.payoff_cooldown_ticks = {}
        if not hasattr(self, "fence_cooldown_ticks"):
            self.fence_cooldown_ticks = {}
        if not isinstance(getattr(self.sim, "npc_dialogue_cooldowns", None), dict):
            self.sim.npc_dialogue_cooldowns = {}
        self.sim.events.subscribe("npc_interact", self.on_npc_interact)
        self.sim.events.subscribe("npc_dialogue_request", self.on_npc_dialogue_request)
        self.sim.events.subscribe("dialog_topic_request", self.on_dialog_topic_request)
        self.sim.events.subscribe("dialog_close_request", self.on_dialog_close_request)
        self.sim.events.subscribe("npc_warn_property", self.on_npc_warn_property)
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
                "street_buy_offer": None,
                "street_buy_skipped_instance_ids": [],
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
            state.setdefault("street_buy_offer", None)
            state.setdefault("street_buy_skipped_instance_ids", [])
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
        return _dialogue_guard_grace_active(self.sim, npc_eid, prop) or _organization_guard_grace_active(
            self.sim,
            self.player_eid,
            prop,
        )

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
        self._promote_dialogue_bond_if_ready(bond)
        return bond

    def _promote_dialogue_bond_if_ready(self, bond):
        if not isinstance(bond, dict):
            return bond
        kind = str(bond.get("kind", "") or "").strip().lower() or "neighbor"
        if kind not in {"neighbor", "coworker", "contact", "local"}:
            return bond
        trust = float(bond.get("trust", 0.0) or 0.0)
        closeness = float(bond.get("closeness", 0.0) or 0.0)
        if trust < 0.62 or closeness < 0.58:
            return bond
        bond["kind"] = "friend"
        bond["protectiveness"] = max(
            float(bond.get("protectiveness", 0.18) or 0.18),
            NPCSocial.DEFAULT_PROTECT.get("friend", 0.7),
        )
        return bond

    def _recently_interacted(self, npc_eid):
        key = (self.player_eid, int(npc_eid))
        last_tick = int(self.last_interaction_tick.get(key, -999999))
        return (self.sim.tick - last_tick) < self.repeat_cooldown

    def _mark_interacted(self, npc_eid):
        self.last_interaction_tick[(self.player_eid, int(npc_eid))] = self.sim.tick

    def _npc_dialogue_cooldown_map(self):
        cooldowns = getattr(self.sim, "npc_dialogue_cooldowns", None)
        if not isinstance(cooldowns, dict):
            cooldowns = {}
            self.sim.npc_dialogue_cooldowns = cooldowns
        return cooldowns

    def _set_dialogue_cooldown(self, npc_eid, duration):
        if npc_eid is None:
            return
        self._npc_dialogue_cooldown_map()[int(npc_eid)] = int(self.sim.tick) + max(0, int(duration or 0))

    def _state_text(self, ai):
        if not ai:
            return "hard to read"
        state = str(ai.state or "idle").strip().lower() or "idle"
        if state == "holding":
            try:
                incident_id = int(getattr(ai, "incident_id", None))
            except (TypeError, ValueError):
                incident_id = -1
            if incident_id >= 0:
                return "making a call"
        if state in {"investigating", "protecting", "reporting_incident"}:
            pos = self.sim.ecs.get(Position).get(getattr(ai, "eid", None)) if hasattr(ai, "eid") else None
            if pos is None:
                for candidate_eid, candidate_ai in self.sim.ecs.get(AI).items():
                    if candidate_ai is ai:
                        pos = self.sim.ecs.get(Position).get(candidate_eid)
                        break
            if pos is not None:
                prop = _property_covering(self.sim, pos.x, pos.y, pos.z)
                if not isinstance(prop, dict) and hasattr(self.sim, "property_at"):
                    prop = self.sim.property_at(pos.x, pos.y, pos.z)
                pressure = local_protective_pressure_snapshot(self.sim, prop) if isinstance(prop, dict) else {}
                label = str((pressure or {}).get("state_label", "") or "").strip()
                if state == "investigating":
                    if label == "Checkpoint Questioning":
                        return "working checkpoint questions"
                    if label == "Justice Sweep":
                        return "working a justice sweep"
                    if label == "Block Watch Active":
                        return "watching the block"
                    if label == "Residents on Alert":
                        return "reading the block"
                elif state == "protecting":
                    if label == "Block Watch Active":
                        return "holding a watch line"
                    if label == "Justice Sweep":
                        return "backing the sweep"
                elif state == "reporting_incident" and label:
                    return "calling in the scene"
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

    def _remember_player_property_lead(self, prop, source_eid, lead_kind, confidence, *, hidden=None):
        changed = _remember_property_lead_for_actor(
            self.sim,
            self.player_eid,
            prop,
            source_eid=source_eid,
            lead_kind=lead_kind,
            confidence=confidence,
            hidden=hidden,
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

    def _person_identity_snapshot(self, person_eid, *, identity=None):
        if person_eid is None:
            return None
        if identity is None:
            identity = self.sim.ecs.get(CreatureIdentity).get(person_eid)
        if identity is None:
            return None
        snapshot = {
            "personal_name": str(getattr(identity, "personal_name", "") or "").strip(),
            "common_name": str(getattr(identity, "common_name", "") or "").strip(),
            "gender_identity": str(getattr(identity, "gender_identity", "") or "").strip().lower(),
            "creature_type": str(getattr(identity, "creature_type", "") or "").strip().lower(),
            "taxonomy_class": str(getattr(identity, "taxonomy_class", "") or "").strip().lower(),
        }
        if not any(snapshot.values()):
            return None
        return snapshot

    def _remember_player_person_contact(
        self,
        person_eid,
        *,
        source_eid,
        relation_kind,
        standing,
        property_id=None,
        introduced=False,
        met_directly=None,
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
        prior_met = bool(existing.get("met_directly", False)) if existing else False
        prior_benefits = set(existing.get("benefits", ())) if existing else set()
        prior_snapshot = existing.get("identity_snapshot") if existing else None
        next_benefits = {str(bit).strip().lower() for bit in benefits if str(bit).strip()}
        snapshot = self._person_identity_snapshot(person_eid)
        effective_source = prior_source if source_eid is None else source_eid
        effective_relation = prior_relation if relation_kind is None else (str(relation_kind or "").strip().lower())
        effective_property = prior_property if property_id is None else property_id
        effective_intro = prior_intro or bool(introduced)
        effective_met = prior_met if met_directly is None else bool(met_directly)
        effective_benefits = set(prior_benefits)
        effective_benefits.update(next_benefits)
        effective_snapshot = prior_snapshot if snapshot is None else snapshot
        first_met_tick = existing.get("first_met_tick") if existing else None
        last_met_tick = existing.get("last_met_tick") if existing else None
        if met_directly:
            if first_met_tick is None:
                first_met_tick = int(self.sim.tick)
            last_met_tick = int(self.sim.tick)
        ledger.remember_person(
            person_eid,
            source_eid=source_eid,
            relation_kind=relation_kind,
            standing=standing,
            tick=self.sim.tick,
            property_id=property_id,
            benefits=next_benefits,
            introduced=introduced,
            met_directly=met_directly,
            first_met_tick=first_met_tick,
            last_met_tick=last_met_tick,
            identity_snapshot=snapshot,
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
            or prior_source != effective_source
            or prior_relation != effective_relation
            or prior_property != effective_property
            or prior_intro != effective_intro
            or prior_met != effective_met
            or effective_benefits != prior_benefits
            or prior_snapshot != effective_snapshot
            or (prior_standing < 0.66 <= float(standing))
        )

    def _remember_direct_human_meeting(self, context):
        if not isinstance(context, dict):
            return False
        npc_eid = context.get("npc_eid")
        identity = context.get("identity")
        if npc_eid is None or not is_human_identity(identity):
            return False
        existing = self._player_person_contact_entry(npc_eid) or {}
        bond = context.get("bond") or self._bond_snapshot(npc_eid) or {}
        relation_kind = None
        if not existing:
            relation_kind = str(bond.get("kind", "") or "contact").strip().lower() or "contact"
        standing = max(0.18, min(0.24, float(context.get("contact_standing", 0.0) or 0.0)))
        prop = (
            context.get("current_prop")
            or context.get("workplace_prop")
            or context.get("owned_prop")
            or context.get("home_prop")
        )
        property_id = str(prop.get("id", "") or "").strip() if isinstance(prop, dict) else None
        changed = self._remember_player_person_contact(
            npc_eid,
            source_eid=None,
            relation_kind=relation_kind,
            standing=standing,
            property_id=property_id or None,
            introduced=False,
            met_directly=True,
            benefits={"known_name"},
        )
        self._remember_player_relationship_episode(
            npc_eid,
            kind="met_directly",
            valence="neutral",
            summary="You have spoken directly.",
            property_id=property_id or None,
            source_topic="greet",
            relation_kind=relation_kind or "contact",
            standing=standing,
            met_directly=True,
            benefits={"known_name"},
        )
        return changed

    def _remember_player_relationship_episode(
        self,
        person_eid,
        *,
        kind,
        valence="neutral",
        summary="",
        property_id=None,
        other_person_eid=None,
        source_topic=None,
        source_eid=None,
        relation_kind=None,
        standing=0.0,
        introduced=False,
        met_directly=None,
        benefits=(),
    ):
        if person_eid is None:
            return False
        self._remember_player_person_contact(
            person_eid,
            source_eid=source_eid,
            relation_kind=relation_kind,
            standing=standing,
            property_id=property_id,
            introduced=introduced,
            met_directly=met_directly,
            benefits=benefits,
        )
        ledger = self.sim.ecs.get(ContactLedger).get(self.player_eid)
        if ledger is None:
            return False
        return ledger.remember_person_episode(
            person_eid,
            kind=kind,
            tick=self.sim.tick,
            valence=valence,
            summary=summary,
            property_id=property_id,
            other_person_eid=other_person_eid,
            source_topic=source_topic,
        )

    def _player_relationship_anchor(self, person_eid, *, entry=None, tone="neutral"):
        if person_eid is None:
            return None
        entry = entry if isinstance(entry, dict) else self._player_person_contact_entry(person_eid)
        if not isinstance(entry, dict):
            return None
        return _relationship_anchor_episode(entry, tone=tone)

    def _player_relationship_history(self, person_eid, *, entry=None, include_trivial=False, limit=None):
        if person_eid is None:
            return ()
        entry = entry if isinstance(entry, dict) else self._player_person_contact_entry(person_eid)
        if not isinstance(entry, dict):
            return ()
        return tuple(_relationship_episode_records(entry, include_trivial=include_trivial, limit=limit))

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

    def _ticks_per_hour(self):
        world_traits = getattr(self.sim, "world_traits", {}) or {}
        clock = world_traits.get("clock", {}) if isinstance(world_traits, dict) else {}
        if not isinstance(clock, dict):
            clock = {}
        try:
            ticks_per_hour = int(clock.get("ticks_per_hour", 600))
        except (TypeError, ValueError):
            ticks_per_hour = 600
        return max(60, ticks_per_hour)

    def _check_in_elapsed_ticks(self, context):
        entry = context.get("person_entry") if isinstance(context, dict) else None
        if not isinstance(entry, dict):
            return 0
        raw_last_met_tick = entry.get("last_met_tick")
        if raw_last_met_tick is None:
            raw_last_met_tick = entry.get("tick")
        if raw_last_met_tick is None:
            return 0
        last_met_tick = _int_or_default(raw_last_met_tick, 0)
        return max(0, int(self.sim.tick) - int(last_met_tick))

    def _sensitive_info_threshold(self, context, topic_id):
        topic_id = str(topic_id or "").strip().lower() or "keyholder"
        base = {
            "keyholder": 0.56,
            "weak_point": 0.62,
        }.get(topic_id, 0.56)
        role = str(context.get("pressure_role", "") or self._dialogue_pressure_role(context)).strip().lower() or "local"
        extra = {
            "guard": 0.1,
            "worker": 0.08,
            "merchant": 0.05,
            "neighbor": -0.02,
            "chaotic": -0.06,
        }.get(role, 0.0)
        if bool(context.get("workplace_here")):
            extra += 0.03
        if context.get("recent_offense"):
            extra += 0.08
        if str(context.get("pressure_tier", "low")).strip().lower() == "high":
            extra += 0.05
        elif str(context.get("pressure_tier", "low")).strip().lower() == "medium":
            extra += 0.02
        return max(0.32, min(0.92, base + extra))

    def _sensitive_info_topic_available(self, context, topic_id):
        if not isinstance(context, dict):
            return False
        topic_id = str(topic_id or "").strip().lower()
        if topic_id not in self.SENSITIVE_INFO_TOPICS:
            return True
        if bool(context.get("guarded")) or not bool(context.get("human", True)):
            return False
        if not isinstance(context.get("owner_place"), dict):
            return False

        bond = context.get("bond") if isinstance(context.get("bond"), dict) else {}
        bond_kind = str(bond.get("kind", "") or "").strip().lower()
        trust = max(0.0, min(1.0, float(bond.get("trust", 0.0) or 0.0)))
        closeness = max(0.0, min(1.0, float(bond.get("closeness", 0.0) or 0.0)))
        standing = max(
            max(0.0, min(1.0, float(context.get("social_standing", 0.0) or 0.0))),
            max(0.0, min(1.0, float(context.get("contact_standing", 0.0) or 0.0))),
            max(0.0, min(1.0, float(context.get("intro_standing", 0.0) or 0.0))),
        )
        relationship_score = max(standing, (trust * 0.6) + (closeness * 0.4))
        threshold = self._sensitive_info_threshold(context, topic_id)
        opened_count = max(0, int(context.get("opened_count", 0) or 0))

        if bond_kind in self.SENSITIVE_INFO_TRUSTED_BONDS:
            if opened_count <= 0 and standing < threshold:
                return False
            return relationship_score >= max(0.36, threshold - 0.08)

        if not bool(context.get("met_directly")):
            return False
        if opened_count < 2:
            return False
        return relationship_score >= threshold

    def _sensitive_info_block_line(self, context, topic_id):
        topic_id = str(topic_id or "").strip().lower()
        place_name = str(context.get("owner_place_name", "")).strip() or "the place"
        if topic_id == "weak_point":
            return f"I am not mapping the soft seam in {place_name} for someone I barely know."
        return f"I am not naming who carries the real access around {place_name} unless I know you better."

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
            "objective_focus_rows": (),
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
        terminal = list(opp_state.get("completed", ())) + list(opp_state.get("failed", ()))
        terminal.sort(
            key=lambda entry: max(
                _int_or_default((entry or {}).get("completed_tick"), -10_000),
                _int_or_default((entry or {}).get("failed_tick"), -10_000),
            ),
            reverse=True,
        )
        for entry in terminal:
            if not isinstance(entry, dict):
                continue
            if str(entry.get("kind", "")).strip().lower() not in self.SIDE_JOB_KINDS:
                continue
            issuer = entry.get("issuer", {}) if isinstance(entry.get("issuer"), dict) else {}
            if _int_or_default(issuer.get("npc_eid"), 0) != npc_int:
                continue
            terminal_tick = max(
                _int_or_default(entry.get("completed_tick"), -10_000),
                _int_or_default(entry.get("failed_tick"), -10_000),
            )
            if self.sim.tick - terminal_tick < self.SIDE_JOB_COOLDOWN_TICKS:
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
        self._promote_dialogue_bond_if_ready(bond)
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

    def _human_identity_for_reference(self, *, eid=None, personal_name=""):
        identities = self.sim.ecs.get(CreatureIdentity)
        if eid is not None:
            identity = identities.get(eid)
            if is_human_identity(identity):
                return identity
        name_text = str(personal_name or "").strip().casefold()
        if not name_text:
            return None
        for _, identity in list(identities.items()):
            if not is_human_identity(identity):
                continue
            candidate_name = str(getattr(identity, "personal_name", "") or "").strip().casefold()
            if candidate_name == name_text:
                return identity
        return None

    def _human_reference_seed_token(self, *, eid=None, personal_name=""):
        if eid is not None:
            return f"{self.sim.seed}:human-reference:{eid}"
        return f"{self.sim.seed}:human-reference:{str(personal_name or '').strip()}"

    def _human_pronoun_slots(self, *, eid=None, personal_name="", prefix="person"):
        identity = self._human_identity_for_reference(eid=eid, personal_name=personal_name)
        return pronoun_format_slots(
            identity,
            prefix=prefix,
            personal_name=personal_name,
            seed_token=self._human_reference_seed_token(eid=eid, personal_name=personal_name),
        )

    def _human_present_verb(self, verb, *, eid=None, personal_name=""):
        identity = self._human_identity_for_reference(eid=eid, personal_name=personal_name)
        return conjugate_present(
            identity,
            verb,
            personal_name=personal_name,
            seed_token=self._human_reference_seed_token(eid=eid, personal_name=personal_name),
        )

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
        spec = self._service_locator_spec(topic_id) or {}
        if bool(spec.get("covert")):
            return self._covert_service_locator_topic_available(context, spec)
        if topic_id == "service_justice":
            return self._justice_locator_topic_available(context)
        return not bool(context.get("guarded"))

    def _covert_service_locator_context_score(self, context, spec):
        if not isinstance(context, dict) or bool(context.get("guarded")) or not bool(context.get("human", True)):
            return -1.0
        spec = spec if isinstance(spec, dict) else {}
        archetypes = self._service_locator_archetypes(spec)
        bond = context.get("bond") if isinstance(context.get("bond"), dict) else {}
        trust = float(bond.get("trust", 0.0) or 0.0)
        closeness = float(bond.get("closeness", 0.0) or 0.0)
        standing = max(
            float(context.get("social_standing", 0.0) or 0.0),
            float(context.get("contact_standing", 0.0) or 0.0),
            float(context.get("intro_standing", 0.0) or 0.0),
        )
        role_id = str(context.get("role_id", "") or "").strip().lower()
        career_text = str(context.get("career_text", "") or "").strip().lower()
        organization_kind = str(context.get("organization_kind", "") or "").strip().lower()
        score = (trust * 0.72) + (closeness * 0.48) + (standing * 0.42)
        if organization_kind in {"gang", "crew", "criminal"}:
            score += 0.55
        if role_id in {"thief", "scout"}:
            score += 0.32
        if any(
            token in career_text
            for token in (
                "bartender",
                "bouncer",
                "courier",
                "dealer",
                "drifter",
                "fixer",
                "janitor",
                "mechanic",
                "runner",
                "scavenger",
                "smuggler",
            )
        ):
            score += 0.34
        if bool(context.get("fence_available")):
            score += 0.24
        if bool(context.get("street_buy_available")):
            score += 0.24
        if bool(context.get("street_appraise_available")):
            score += 0.18
        if bool(context.get("hire_runner_available")):
            score += 0.18

        for ref in (
            context.get("current_prop"),
            context.get("workplace_prop"),
            context.get("owner_place"),
            context.get("home_prop"),
        ):
            if _property_archetype(ref) in archetypes:
                score += 0.82
                break

        if "backroom_clinic" in archetypes and any(
            token in career_text for token in ("doctor", "medic", "nurse", "orderly", "paramedic", "triage")
        ):
            score += 0.42
        if "backroom_market" in archetypes and any(
            token in career_text for token in ("broker", "dealer", "fence", "pawnbroker", "shopkeeper", "vendor")
        ):
            score += 0.36
        return score

    def _covert_service_locator_topic_available(self, context, spec):
        return self._covert_service_locator_context_score(context, spec) >= 0.58

    def _covert_service_locator_prop_score(self, prop, context, spec):
        if not isinstance(prop, dict):
            return -1.0
        base_score = self._covert_service_locator_context_score(context, spec)
        if base_score < 0.58:
            return -1.0
        metadata = _property_metadata(prop)
        if bool(metadata.get("public", True)):
            return -1.0
        score = base_score
        npc_eid = context.get("npc_eid")
        if npc_eid is not None and prop.get("owner_eid") == npc_eid:
            score += 1.35

        linked_property_id = str(metadata.get("linked_property_id", "") or "").strip()
        linked_building_id = str(metadata.get("linked_building_id", "") or "").strip()
        for ref in (
            context.get("current_prop"),
            context.get("workplace_prop"),
            context.get("owner_place"),
            context.get("home_prop"),
        ):
            if not isinstance(ref, dict):
                continue
            ref_id = str(ref.get("id", "") or "").strip()
            ref_building_id = str(_property_metadata(ref).get("building_id", "") or ref_id).strip()
            if linked_property_id and linked_property_id == ref_id:
                score += 1.05
            if linked_building_id and linked_building_id == ref_building_id:
                score += 0.72
        return score

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

    def _service_locator_rows(self, services, *, radius=None, context=None):
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
            covert_score = 0.0
            if bool(spec.get("covert")):
                covert_score = self._covert_service_locator_prop_score(prop, context, spec)
                if covert_score < 0.0:
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
                "covert_score": float(covert_score),
            })
        rows.sort(
            key=lambda row: (
                int(row["chunk_distance"]),
                -float(row.get("covert_score", 0.0) or 0.0),
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

    def _covert_service_locator_caution(self, spec, lead_prop):
        if not bool((spec or {}).get("covert")) or not isinstance(lead_prop, dict):
            return ""
        hint = str(_property_metadata(lead_prop).get("covert_hint", "") or "").strip()
        if not hint:
            return ""
        if hint[-1] not in ".!?":
            hint = f"{hint}."
        return hint

    def _service_locator_summary(self, context, topic_id):
        spec = self._service_locator_spec(topic_id)
        if not isinstance(spec, dict):
            return {"summary": "", "service_label": "service", "lead_prop": None}

        service_label = str(spec.get("service_label", "service")).strip() or "service"
        offer_label = str(spec.get("offer_label", service_label)).strip() or service_label
        local_template = str(spec.get("local_summary", "")).strip()
        near_template = str(spec.get("near_summary", "")).strip()
        rows = list(self._service_locator_rows(spec, radius=self.SERVICE_LOCATOR_SEARCH_RADIUS, context=context))
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
                caution = self._covert_service_locator_caution(spec, lead_prop)
                if caution:
                    summary = f"{summary} {caution}" if summary else caution
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
            caution = self._covert_service_locator_caution(spec, lead_prop)
            if caution:
                summary = f"{summary} {caution}" if summary else caution
            return {
                "summary": summary,
                "service_label": service_label,
                "lead_prop": lead_prop,
            }

        if bool(spec.get("covert")):
            return {"summary": "", "service_label": service_label, "lead_prop": None}

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

    _STREET_ITEM_VALUE = {
        "weapon": 46,
        "firearm": 46,
        "launcher": 74,
        "armor": 30,
        "tool": 24,
        "device": 20,
        "communication": 20,
        "medical": 20,
        "ammo": 18,
        "token": 10,
        "access": 28,
        "stimulant": 22,
        "drug": 24,
    }
    _STREET_ITEM_OVERRIDES = {
        "cocaine_bindle": 32,
        "mdma_capsule": 30,
        "lsd_blotter": 26,
        "black_market_stim": 28,
        "methamphetamine": 34,
        "fentanyl_patch": 30,
        "ketamine_vial": 30,
        "heroin_syringe": 32,
    }
    _STREET_DEFAULT_VALUE = 14
    _FENCE_ITEM_VALUE = {
        "weapon": 50, "firearm": 50, "gear": 32, "armor": 32,
        "tool": 24, "access": 28, "stimulant": 18, "drug": 18,
    }
    _FENCE_DEFAULT_VALUE = 14

    def _street_behavior_profile(self, npc_eid):
        return self.sim.ecs.get(BehaviorProfile).get(npc_eid)

    def _street_behavior_preference(self, npc_eid, key, default=None):
        profile = self._street_behavior_profile(npc_eid)
        if not profile:
            return default
        preferences = getattr(profile, "preferences", None)
        if not isinstance(preferences, dict):
            return default
        return preferences.get(key, default)

    def _street_item_value(self, item_id):
        return int(_street_item_value(item_id))

    def _street_item_price(self, entry, *, mult=1.0):
        return int(_street_item_price(entry, mult=mult))

    def _street_buy_terms_for(self, npc_eid, context):
        district_type = str((context or {}).get("district_type", "") or "").strip().lower()
        occupation = context.get("occupation") if isinstance(context, dict) else None
        career = str(getattr(occupation, "career", "") or "").strip().lower()
        return _street_buy_terms(
            self.sim,
            npc_eid,
            district_type=district_type,
            career=career,
        )

    def _street_buy_candidate_rows(self, npc_eid, context):
        inventory = self.sim.ecs.get(Inventory).get(self.player_eid)
        if not inventory:
            return []
        district_type = str((context or {}).get("district_type", "") or "").strip().lower()
        occupation = context.get("occupation") if isinstance(context, dict) else None
        career = str(getattr(occupation, "career", "") or "").strip().lower()
        rows = _street_buy_candidate_rows_for_inventory(
            self.sim,
            npc_eid,
            inventory,
            district_type=district_type,
            career=career,
        )
        skipped = self._street_buy_skipped_instance_ids()
        if not skipped:
            return rows
        filtered = []
        for row in rows:
            if bool(row.get("desired")):
                filtered.append(row)
                continue
            instance_key = self._street_buy_instance_key(row.get("instance_id"))
            if instance_key and instance_key in skipped:
                continue
            filtered.append(row)
        return filtered

    def _street_buy_preview(self, npc_eid, context):
        rows = self._street_buy_candidate_rows(npc_eid, context)
        if not rows:
            return ""
        top = rows[0]
        desired_item_id = str((self._street_buy_terms_for(npc_eid, context) or {}).get("desired_item_id", "") or "").strip().lower()
        if desired_item_id and any(bool(row.get("desired")) for row in rows):
            desired_name = item_display_name(desired_item_id, item_catalog=ITEM_CATALOG)
            return f"Wants {desired_name}; top offer about {int(top.get('price', 0))} credits."
        if desired_item_id:
            desired_name = item_display_name(desired_item_id, item_catalog=ITEM_CATALOG)
            return f"Asked for {desired_name}, but can look over other stock; top offer about {int(top.get('price', 0))} credits."
        return f"Will move {len(rows)} item(s); top offer about {int(top.get('price', 0))} credits."

    def _street_buy_available_for(self, npc_eid, context):
        if context.get("guarded"):
            return False
        return bool(self._street_buy_candidate_rows(npc_eid, context))

    def _street_buy_offer_state(self, npc_eid=None):
        state = self._dialog_ui_state()
        offer = state.get("street_buy_offer")
        if not isinstance(offer, dict):
            return None
        if npc_eid is not None and offer.get("npc_eid") != npc_eid:
            return None
        return dict(offer)

    def _clear_street_buy_offer(self):
        self._dialog_ui_state()["street_buy_offer"] = None

    def _street_buy_instance_key(self, instance_id):
        return str(instance_id or "").strip()

    def _street_buy_skipped_instance_ids(self):
        state = self._dialog_ui_state()
        raw = state.get("street_buy_skipped_instance_ids", ())
        if isinstance(raw, str):
            raw = (raw,)
        return {
            self._street_buy_instance_key(instance_id)
            for instance_id in tuple(raw or ())
            if self._street_buy_instance_key(instance_id)
        }

    def _remember_street_buy_skipped_offer(self, offer):
        if not isinstance(offer, dict):
            return
        offer_kind = str(offer.get("kind", "")).strip().lower()
        if offer_kind not in {"pivot", "generic"}:
            return
        skipped = self._street_buy_skipped_instance_ids()
        for row in tuple(offer.get("rows", ()) or ()):
            key = self._street_buy_instance_key((row or {}).get("instance_id"))
            if key:
                skipped.add(key)
        self._dialog_ui_state()["street_buy_skipped_instance_ids"] = sorted(skipped)

    def _street_buy_offer_item_text(self, offer, *, limit=3):
        if not isinstance(offer, dict):
            return "that stock"
        item_names = [
            str(name).strip()
            for name in tuple(offer.get("item_names", ()) or ())
            if str(name).strip()
        ]
        if not item_names:
            return "that stock"
        shown = item_names[:max(1, int(limit))]
        text = _dialogue_human_join(tuple(shown))
        extra_count = max(0, int(offer.get("item_count", len(item_names)) or 0) - len(shown))
        if extra_count > 0:
            text = f"{text}, and {extra_count} more item" + ("s" if extra_count != 1 else "")
        return text

    def _street_buy_offer_accept_label(self, offer):
        if not isinstance(offer, dict):
            return "Sell it."
        payout = int(max(0, offer.get("total_payout", 0) or 0))
        payout_text = f"{payout} credits" if payout > 0 else "the posted price"
        desired_name = str(offer.get("desired_name", "") or "").strip()
        if str(offer.get("kind", "")).strip().lower() == "desired" and desired_name:
            quantity = int(max(1, offer.get("quantity_total", 1) or 1))
            noun = f"the {desired_name} batch" if quantity > 1 else f"the {desired_name}"
            return f"Sell {noun} for {payout_text}."
        return f"Sell {self._street_buy_offer_item_text(offer)} for {payout_text}."

    def _street_buy_offer_next_available(self, offer):
        if not isinstance(offer, dict):
            return False
        offer_kind = str(offer.get("kind", "")).strip().lower()
        if offer_kind not in {"pivot", "generic"}:
            return False
        return int(offer.get("remaining_match_count", 0) or 0) > 0

    def _street_buy_offer_next_label(self, offer):
        if not self._street_buy_offer_next_available(offer):
            return ""
        next_item_name = str(offer.get("next_item_name", "") or "").strip()
        if next_item_name:
            return f"What about {next_item_name}?"
        return "What about the next item?"

    def _build_street_buy_offer(self, npc_eid, context):
        rows = self._street_buy_candidate_rows(npc_eid, context)
        if not rows:
            return None
        terms = self._street_buy_terms_for(npc_eid, context) or {}
        desired_item_id = str(terms.get("desired_item_id", "") or "").strip().lower()
        desired_name = item_display_name(desired_item_id, item_catalog=ITEM_CATALOG) if desired_item_id else ""
        desired_rows = [dict(row) for row in rows if bool(row.get("desired"))]
        generic_rows = [dict(row) for row in rows if not bool(row.get("desired"))]
        if desired_rows:
            offer_rows = desired_rows
            offer_kind = "desired"
            next_item_name = ""
        elif generic_rows:
            offer_rows = [generic_rows[0]]
            offer_kind = "pivot" if desired_name else "generic"
            next_item_name = ""
            if len(generic_rows) > 1:
                next_item_name = str(generic_rows[1].get("item_name", generic_rows[1].get("item_id", "stock"))).strip()
        else:
            return None
        total_payout = sum(int(max(0, row.get("price", 0) or 0)) for row in offer_rows)
        if total_payout <= 0:
            return None
        item_names = tuple(
            str(row.get("item_name", row.get("item_id", "stock"))).strip()
            for row in offer_rows
            if str(row.get("item_name", row.get("item_id", "stock"))).strip()
        )
        quantity_total = sum(int(max(1, row.get("quantity", 1) or 1)) for row in offer_rows)
        return {
            "npc_eid": npc_eid,
            "kind": offer_kind,
            "desired_item_id": desired_item_id,
            "desired_name": desired_name,
            "total_payout": int(total_payout),
            "item_count": len(offer_rows),
            "quantity_total": int(quantity_total),
            "item_names": item_names,
            "next_item_name": next_item_name,
            "remaining_match_count": max(0, len(rows) - len(offer_rows)),
            "rows": tuple(
                {
                    "instance_id": row.get("instance_id"),
                    "item_id": str(row.get("item_id", "") or "").strip().lower(),
                    "item_name": str(row.get("item_name", row.get("item_id", "stock"))).strip(),
                    "quantity": int(max(1, row.get("quantity", 1) or 1)),
                    "price": int(max(0, row.get("price", 0) or 0)),
                    "illegal": bool(row.get("illegal")),
                    "desired": bool(row.get("desired")),
                }
                for row in offer_rows
            ),
        }

    def _street_buy_offer_line(self, offer):
        if not isinstance(offer, dict):
            return "That stock is not moving cleanly enough for me to touch it."
        payout = int(max(0, offer.get("total_payout", 0) or 0))
        desired_name = str(offer.get("desired_name", "") or "").strip()
        item_text = self._street_buy_offer_item_text(offer)
        offer_kind = str(offer.get("kind", "")).strip().lower()
        remaining_match_count = int(offer.get("remaining_match_count", 0) or 0)
        if offer_kind == "desired" and desired_name:
            quantity = int(max(1, offer.get("quantity_total", 1) or 1))
            unit_text = "the batch" if quantity > 1 else "it"
            line = f"That is exactly the {desired_name} I was looking for. {payout} credits for {unit_text}."
            if remaining_match_count > 0:
                line += " If you want to move anything else after that, I can take another look."
            return line
        if offer_kind == "pivot" and desired_name:
            line = f"That is not the {desired_name} I asked for. Looking over what you're carrying, I can move {item_text}. {payout} credits for it."
            if remaining_match_count > 0:
                line += " If you want to move anything else after that, I can take another look."
            return line
        line = f"I can move {item_text}. {payout} credits for it."
        if remaining_match_count > 0:
            line += " If you want to move anything else after that, I can take another look."
        return line

    def _execute_street_buy_offer(self, npc_eid, context, offer):
        inventory = self.sim.ecs.get(Inventory).get(self.player_eid)
        assets = self.sim.ecs.get(PlayerAssets).get(self.player_eid)
        if not inventory or not assets:
            return {"npc_lines": ["You do not have the stock on you right now."]}

        total_payout = 0
        sold_rows = []
        illegal_units = 0
        for row in tuple((offer or {}).get("rows", ()) or ()):
            quantity = int(max(1, row.get("quantity", 1) or 1))
            removed = inventory.remove_item(instance_id=row.get("instance_id"), quantity=quantity)
            if not removed:
                continue
            gear_changes = _unlink_removed_item_from_gear(self.sim, self.player_eid, removed, item_catalog=ITEM_CATALOG)
            if gear_changes.get("armor_name"):
                self.sim.emit(Event(
                    "armor_removed",
                    eid=self.player_eid,
                    item_id=gear_changes.get("armor_item_id"),
                    armor_name=gear_changes["armor_name"],
                    reason="street_sold",
                ))
            if gear_changes.get("weapon_id"):
                self.sim.emit(Event(
                    "weapon_removed",
                    eid=self.player_eid,
                    weapon_id=gear_changes["weapon_id"],
                    weapon_name=gear_changes["weapon_name"],
                    reason="street_sold",
                ))
            if gear_changes.get("disguise_name"):
                self.sim.emit(Event(
                    "disguise_removed",
                    eid=self.player_eid,
                    item_id=gear_changes.get("disguise_item_id"),
                    item_name=gear_changes["disguise_name"],
                    reason="street_sold",
                ))
            if gear_changes.get("container_name"):
                self.sim.emit(Event(
                    "container_removed",
                    eid=self.player_eid,
                    item_id=gear_changes.get("container_item_id"),
                    item_name=gear_changes["container_name"],
                    reason="street_sold",
                ))
            total_payout += int(row.get("price", 0) or 0)
            illegal_units += quantity if bool(row.get("illegal")) else 0
            sold_rows.append({
                "item_id": str(row.get("item_id", "") or "").strip().lower(),
                "item_name": str(row.get("item_name", row.get("item_id", "stock"))).strip(),
                "quantity": int(quantity),
            })

        if total_payout <= 0 or not sold_rows:
            return {"npc_lines": ["Leave it. You are not carrying the stock we were talking about anymore."]}

        assets.credits += int(total_payout)
        desired_item_id = str((offer or {}).get("desired_item_id", "") or "").strip().lower()
        if illegal_units > 0:
            player_pos = self.sim.ecs.get(Position).get(self.player_eid)
            if player_pos:
                score = min(28, 10 + (illegal_units * 4) + (6 if desired_item_id else 0))
                _emit_action_offense_event(
                    self.sim,
                    self.player_eid,
                    "trade_sell",
                    player_pos.x,
                    player_pos.y,
                    player_pos.z,
                    context="contraband_use",
                    score=score,
                )
        self._shift_dialogue_bond(
            npc_eid,
            trust_delta=0.04,
            closeness_delta=0.02,
            guarded=False,
        )
        self.sim.emit(Event(
            "street_buy_transaction",
            eid=self.player_eid,
            npc_eid=npc_eid,
            payout=int(total_payout),
            item_count=len(sold_rows),
            illegal_units=int(illegal_units),
            desired_item_id=desired_item_id,
            sold_items=tuple(
                {
                    "item_id": str(row.get("item_id", "") or "").strip().lower(),
                    "quantity": int(max(1, row.get("quantity", 1) or 1)),
                }
                for row in sold_rows
                if str(row.get("item_id", "") or "").strip()
            ),
            credits=int(getattr(assets, "credits", 0) or 0),
        ))

        sold_names = [
            str(row.get("item_name", row.get("item_id", "stock"))).strip()
            for row in sold_rows[:3]
            if str(row.get("item_name", row.get("item_id", "stock"))).strip()
        ]
        if desired_item_id and any(str(row.get("item_id", "")).strip().lower() == desired_item_id for row in sold_rows):
            desired_name = item_display_name(desired_item_id, item_catalog=ITEM_CATALOG)
            line = f"Done. {int(total_payout)} credits for the {desired_name}. Keep your head down."
        elif sold_names:
            line = f"Done. {int(total_payout)} credits for { _dialogue_human_join(tuple(sold_names)) }."
        else:
            line = f"Done. {int(total_payout)} credits for the stock."
        return {"npc_lines": [line]}

    def _street_appraise_candidates(self, npc_eid):
        return _street_appraise_candidates_for_actor(
            self.sim,
            npc_eid,
            self.player_eid,
        )

    def _street_appraise_preview(self, npc_eid):
        candidates = self._street_appraise_candidates(npc_eid)
        identify_count = len(candidates.get("identify", ()))
        appraise_count = len(candidates.get("appraise", ()))
        bits = []
        if identify_count:
            bits.append(f"{identify_count} unknown street item" + ("s" if identify_count != 1 else ""))
        if appraise_count:
            bits.append(f"{appraise_count} appraisal target" + ("s" if appraise_count != 1 else ""))
        return ", ".join(bits)

    def _street_appraise_available_for(self, npc_eid, context):
        if context.get("guarded"):
            return False
        candidates = self._street_appraise_candidates(npc_eid)
        return bool(candidates.get("identify") or candidates.get("appraise"))

    def _resolve_street_appraise_topic(self, context, *, topic_id, ask_count):
        npc_eid = context.get("npc_eid")
        result = _resolve_street_appraise_between_actors(
            self.sim,
            npc_eid,
            self.player_eid,
        )
        if result is None:
            identify_count = 0
            appraise_count = 0
            identified_names = []
        else:
            identify_count = int(result.get("identify_count", 0) or 0)
            appraise_count = int(result.get("appraise_count", 0) or 0)
            identified_names = list(result.get("identified_item_names", ()) or ())
        if identify_count <= 0 and appraise_count <= 0:
            return {
                "npc_lines": [
                    "There is nothing in that stock I can read better than you already can."
                ]
            }

        bits = []
        if identified_names:
            named = _dialogue_human_join(tuple(identified_names[:3]))
            if identify_count > 3:
                named = f"{named}, and the rest of the batch"
            bits.append(f"That reads as {named}.")
        elif identify_count > 0:
            bits.append(f"I sorted out {identify_count} street item" + ("s." if identify_count != 1 else "."))
        if appraise_count > 0:
            bits.append(f"I also sized up {appraise_count} piece" + ("s" if appraise_count != 1 else "") + " of gear.")
        line = " ".join(bit for bit in bits if bit).strip()
        if not line:
            line = "I gave the stock a quick read for you."
        return {"npc_lines": [line]}

    def _resolve_street_buy_topic(self, context, *, topic_id, ask_count):
        npc_eid = context.get("npc_eid")
        offer = self._build_street_buy_offer(npc_eid, context)
        if not offer:
            self._clear_street_buy_offer()
            return {"npc_lines": ["Not tonight. You are not carrying anything I want to move."]}
        self._dialog_ui_state()["street_buy_offer"] = offer
        return {"npc_lines": [self._street_buy_offer_line(offer)]}

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
        return max(self._FENCE_DEFAULT_VALUE, self._street_item_value(item_id))

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
            service = _storefront_service_profile(self.sim, prop)
            if not service.get("available"):
                continue
            if service.get("service_eid") not in {None, npc_eid}:
                continue
            access = _evaluate_property_access(
                self.sim,
                self.player_eid,
                prop,
                x=player_pos.x,
                y=player_pos.y,
                z=player_pos.z,
            )
            dialogue_trade_only = bool(_property_metadata(prop).get("dialogue_trade_only"))
            if (
                not access.can_use_services
                and not (
                    dialogue_trade_only
                    and int(player_pos.z) == int(prop.get("z", player_pos.z))
                    and _property_distance(player_pos.x, player_pos.y, prop) <= 2
                )
            ):
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
        membership_row = primary_actor_membership(self.sim, npc_eid, organization_eid=organization_eid)
        organization_role = str(
            (membership_row or {}).get("role")
            or (self_member or {}).get("role")
            or ""
        ).strip().lower()
        if not organization_role and workplace_prop and workplace_prop.get("owner_eid") == npc_eid:
            organization_role = "owner"

        supervisor_row = None
        supervisor_eid = (membership_row or {}).get("supervisor_eid")
        if supervisor_eid is not None:
            supervisor_row = member_by_eid.get(int(supervisor_eid))
        if organization_role == "owner":
            supervisor_row = self_member
        elif supervisor_row is None:
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
        supervisor_eid_value = None
        if supervisor_row:
            try:
                supervisor_eid_value = int(supervisor_row.get("eid"))
            except (TypeError, ValueError):
                supervisor_eid_value = supervisor_row.get("eid")
            supervisor_name = _entity_display_name(self.sim, supervisor_row.get("eid"), title_case=True)
            supervisor_role = str(supervisor_row.get("role", "") or "").strip().lower()

        return {
            "organization_eid": organization_eid,
            "organization_name": organization_text,
            "organization_kind": organization_kind,
            "organization_role": organization_role,
            "supervisor_eid": supervisor_eid_value,
            "supervisor_name": supervisor_name,
            "supervisor_role": supervisor_role,
            "coworker_names": tuple(coworker_names),
            "coworker_count": len(coworker_names),
            "member_count": len(members),
        }

    def _dialogue_context(self, npc_eid, *, bond=None, allow_distant=False):
        positions = self.sim.ecs.get(Position)
        npc_pos = positions.get(npc_eid)
        player_pos = positions.get(self.player_eid)
        if not npc_pos or not player_pos or npc_pos.z != player_pos.z:
            return None
        dx = abs(int(player_pos.x) - int(npc_pos.x))
        dy = abs(int(player_pos.y) - int(npc_pos.y))
        max_range = 2 if allow_distant else 1
        if max(dx, dy) > max_range:
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
        opened_count = max(0, int(dialogue_memory.get("opened_count", 0) or 0))
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
        met_directly = bool((intro_entry or {}).get("met_directly", False))
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
        other_eid = None
        if primary_social_lead:
            other_eid = primary_social_lead.get("eid")
            other_name = str(primary_social_lead.get("name", "")).strip()
            other_relation = str(primary_social_lead.get("relation_text", "")).strip() or "contact"
        intro_source_name = ""
        if intro_entry:
            intro_source_name = _entity_display_name(self.sim, intro_entry.get("source_eid"), title_case=True)
        player_profile = self._player_profile()
        rumor_line = self._memory_line(memory, player_profile)
        objective_eval = evaluate_visible_run_objective(self.sim, self.player_eid)
        objective_title = str((objective_eval or {}).get("title", "")).strip()
        objective_next_step = str((objective_eval or {}).get("next_step", "")).strip()
        objective_summary_line = str((objective_eval or {}).get("summary_line", "")).strip()
        objective_why_lines = tuple(str(line).strip() for line in list((objective_eval or {}).get("why_lines", ()) or ()) if str(line).strip())
        objective_how_lines = tuple(str(line).strip() for line in list((objective_eval or {}).get("how_lines", ()) or ()) if str(line).strip())
        objective_activity_lines = tuple(str(line).strip() for line in list((objective_eval or {}).get("activity_lines", ()) or ()) if str(line).strip())
        objective_focus = ()
        objective_focus_rows = ()
        if objective_eval:
            from game.opportunities import objective_focus_facts

            focus_facts = objective_focus_facts(
                self.sim,
                self.player_eid,
                (objective_eval or {}).get("id", ""),
                limit=3,
            )
            focus_lines = []
            normalized_focus_rows = []
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
                    line = f"{title} {distance_phrase}: {reason}."
                else:
                    line = f"{title} {distance_phrase}."
                focus_lines.append(line)
                normalized_focus_rows.append({
                    **dict(row),
                    "line": line,
                })
            objective_focus = tuple(line for line in focus_lines if line)
            objective_focus_rows = tuple(normalized_focus_rows)
        final_operation_eval = evaluate_visible_final_operation(self.sim, self.player_eid)
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
            "objective_focus_rows": objective_focus_rows,
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
        active_run_echo = self._active_run_echo_for_dialogue_context(npc_pos, current_prop=current_prop)
        run_echo_line = self._run_echo_local_line(
            active_run_echo,
            role_id=role_id,
            guarded=guarded,
            owner_place_name=owner_place_name,
            workplace_name=str(workplace_prop.get("name", workplace_prop.get("id", "place"))).strip() if workplace_prop else "",
            home_name=str(home_prop.get("name", home_prop.get("id", "home"))).strip() if home_prop else "",
        )
        run_echo_history_line = self._run_echo_history_line(
            active_run_echo,
            role_id=role_id,
            guarded=guarded,
            owner_place_name=owner_place_name,
            workplace_name=str(workplace_prop.get("name", workplace_prop.get("id", "place"))).strip() if workplace_prop else "",
            home_name=str(home_prop.get("name", home_prop.get("id", "home"))).strip() if home_prop else "",
        )
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
        elif run_echo_line:
            local_source = "run_echo"
            detail_line = run_echo_line
            detail_label = "What do people remember?"
        elif other_name:
            local_source = "other"
            other_slots = self._human_pronoun_slots(
                eid=other_eid,
                personal_name=other_name,
                prefix="other",
            )
            other_hear = self._human_present_verb(
                "hear",
                eid=other_eid,
                personal_name=other_name,
            )
            detail_line = f"Try {other_name}. {other_slots['other_subject_cap']} {other_hear} more than I do."
        trade_context = self._trade_context(npc_eid, workplace_prop, current_prop)
        street_context = {
            "npc_eid": npc_eid,
            "occupation": occupation,
            "district_type": district_type,
            "guarded": guarded,
        }
        street_appraise_available = self._street_appraise_available_for(npc_eid, street_context)
        street_appraise_preview = self._street_appraise_preview(npc_eid) if street_appraise_available else ""
        street_buy_available = self._street_buy_available_for(npc_eid, street_context)
        street_buy_preview = self._street_buy_preview(npc_eid, street_context) if street_buy_available else ""
        street_buy_terms = self._street_buy_terms_for(npc_eid, street_context) if street_buy_available else None
        street_buy_rows = self._street_buy_candidate_rows(npc_eid, street_context) if street_buy_available else []
        street_buy_hint = ""
        if isinstance(street_buy_terms, dict):
            desired_item_id = str(street_buy_terms.get("desired_item_id", "") or "").strip().lower()
            if desired_item_id and any(bool(row.get("desired")) for row in street_buy_rows):
                street_buy_hint = item_display_name(desired_item_id, item_catalog=ITEM_CATALOG)
        street_buy_offer = self._street_buy_offer_state(npc_eid)
        street_buy_offer_pending = isinstance(street_buy_offer, dict)
        street_buy_offer_accept_label = self._street_buy_offer_accept_label(street_buy_offer) if street_buy_offer_pending else ""
        street_buy_offer_next_available = self._street_buy_offer_next_available(street_buy_offer) if street_buy_offer_pending else False
        street_buy_offer_next_label = self._street_buy_offer_next_label(street_buy_offer) if street_buy_offer_next_available else ""
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
            "street_appraise_available": street_appraise_available,
            "street_appraise_preview": street_appraise_preview,
            "street_buy_available": street_buy_available,
            "street_buy_preview": street_buy_preview,
            "street_buy_hint": street_buy_hint,
            "street_buy_offer_pending": street_buy_offer_pending,
            "street_buy_offer_accept_label": street_buy_offer_accept_label,
            "street_buy_offer_next_available": street_buy_offer_next_available,
            "street_buy_offer_next_label": street_buy_offer_next_label,
            "street_buy_offer_decline_label": "Pass on that offer.",
            "hire_runner_available": self._hire_runner_available_for(npc_eid, contact_standing, guarded),
            "hire_runner_cost": self.CONTRACTOR_COST,
            "hire_runner_hours": f"{max(1, self.CONTRACTOR_DURATION // 60)} hours",
            "contact_standing": contact_standing,
            "intro_standing": intro_standing,
            "social_standing": social_standing,
            "opened_count": opened_count,
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
            "supervisor_eid": organization.get("supervisor_eid"),
            "supervisor_name": str(organization.get("supervisor_name", "")).strip(),
            "supervisor_role": str(organization.get("supervisor_role", "")).strip().lower(),
            "coworker_names": tuple(organization.get("coworker_names", ()) or ()),
            "coworker_count": int(organization.get("coworker_count", 0) or 0),
            "organization_member_count": int(organization.get("member_count", 0) or 0),
            "home_name": str(home_prop.get("name", home_prop.get("id", "home"))).strip() if home_prop else "",
            "workplace_name": str(workplace_prop.get("name", workplace_prop.get("id", "place"))).strip() if workplace_prop else "",
            "workplace_here": workplace_here,
            "owner_eid": owner_place.get("owner_eid") if isinstance(owner_place, dict) else None,
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
            "met_directly": met_directly,
            "intro_source_name": intro_source_name,
            "other_eid": other_eid,
            "other_name": other_name,
            "other_relation": other_relation,
            "rumor_line": rumor_line,
            "active_run_echo": dict(active_run_echo) if isinstance(active_run_echo, dict) else {},
            "run_echo_line": run_echo_line,
            "run_echo_history_line": run_echo_history_line,
            "objective_id": str((objective_eval or {}).get("id", "")).strip().lower(),
            "run_objective_visible": bool(objective_eval),
            "objective_title": objective_title,
            "objective_next_step": objective_next_step,
            "objective_summary_line": objective_summary_line,
            "objective_why_lines": objective_why_lines,
            "objective_how_lines": objective_how_lines,
            "objective_activity_lines": objective_activity_lines,
            "objective_focus_lines": objective_focus,
            "objective_focus_rows": objective_focus_rows,
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
        person_entry = self._player_person_contact_entry(npc_eid)
        relationship_history = self._player_relationship_history(npc_eid, entry=person_entry, limit=3)
        relationship_anchor = self._player_relationship_anchor(npc_eid, entry=person_entry, tone=tone)
        context.update({
            "person_entry": person_entry if isinstance(person_entry, dict) else None,
            "relationship_history": relationship_history,
            "relationship_has_nontrivial_history": bool(relationship_history),
            "relationship_anchor_episode": dict(relationship_anchor) if isinstance(relationship_anchor, dict) else None,
        })
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
        context["rapport_shape"] = _build_rapport_shape(self.sim, npc_eid, context=context)
        return context

    def _active_run_echo_for_dialogue_context(self, npc_pos, *, current_prop=None):
        chunk_key = None
        if isinstance(current_prop, dict):
            try:
                chunk_key = self.sim.chunk_coords(int(current_prop.get("x", 0)), int(current_prop.get("y", 0)))
            except Exception:
                chunk_key = None
        if chunk_key is None and npc_pos is not None:
            try:
                chunk_key = self.sim.chunk_coords(int(npc_pos.x), int(npc_pos.y))
            except Exception:
                chunk_key = None
        if chunk_key is None:
            return None
        return strongest_active_run_echo_for_chunk(self.sim, chunk_key)

    def _run_echo_case_label(self, echo):
        if not isinstance(echo, dict):
            return ""
        for key in ("property_name", "subject_name", "victim_name", "summary"):
            value = str(echo.get(key, "") or "").strip()
            if value:
                return value
        return "that old case"

    def _run_echo_local_line(
        self,
        echo,
        *,
        role_id="",
        guarded=False,
        owner_place_name="",
        workplace_name="",
        home_name="",
    ):
        if not isinstance(echo, dict):
            return ""
        rumor_text = str(echo.get("rumor_text", "") or "").strip()
        summary = str(echo.get("summary", "") or "").strip()
        case_label = self._run_echo_case_label(echo)
        role_id = str(role_id or "").strip().lower()
        if guarded or role_id in {"guard", "scout", "cop", "peace_officer", "security"}:
            place_name = str(owner_place_name or workplace_name or "the block").strip()
            return f"{rumor_text or summary} Since then people around {place_name} read strangers a little harder."
        if workplace_name:
            return f"{rumor_text or summary} It still comes up around {workplace_name}."
        if home_name:
            return f"{rumor_text or summary} People around {home_name} still bring it up."
        if rumor_text:
            return rumor_text
        if summary:
            return summary
        return f"People here still bring up {case_label}."

    def _run_echo_history_line(
        self,
        echo,
        *,
        role_id="",
        guarded=False,
        owner_place_name="",
        workplace_name="",
        home_name="",
    ):
        if not isinstance(echo, dict):
            return ""
        case_label = self._run_echo_case_label(echo)
        role_id = str(role_id or "").strip().lower()
        if guarded or role_id in {"guard", "scout", "cop", "peace_officer", "security"}:
            place_name = str(owner_place_name or workplace_name or "this block").strip()
            return f"I was around when {case_label} made {place_name} feel tighter."
        if workplace_name:
            return f"I have been here long enough to remember when people at {workplace_name} started talking about {case_label} like a warning."
        if home_name:
            return f"I have been here long enough to remember when {case_label} started sticking to {home_name}."
        return f"I have been here long enough to remember when {case_label} started sticking to the block."

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
        run_echo_history_line = str(context.get("run_echo_history_line", "")).strip()
        base_line = ""
        if context.get("guarded") and owner_place_name:
            base_line = f"I have been around {owner_place_name} long enough to know who belongs near it."
        elif workplace_name and home_name and workplace_name.lower() != home_name.lower():
            base_line = f"Long enough that {workplace_name} is work and {home_name} is home."
        elif home_name:
            base_line = f"Long enough that {home_name} feels like home."
        elif workplace_name:
            base_line = f"Long enough that {workplace_name} stopped feeling new."
        elif owner_place_name:
            base_line = f"Long enough to know the rhythm around {owner_place_name}."
        elif other_name:
            base_line = f"Long enough to know {other_name} and a few other faces."
        else:
            base_line = "Long enough to recognize the regulars."
        if run_echo_history_line:
            return f"{base_line} {run_echo_history_line}"
        return base_line

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
        owner_eid = context.get("owner_eid")
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
                owner_slots = self._human_pronoun_slots(
                    eid=owner_eid,
                    personal_name=owner_name,
                    prefix="owner",
                )
                if career_text:
                    return f"{owner_name} owns {workplace_name}. I do {career_text} work for {owner_slots['owner_object']}."
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
        supervisor_eid = context.get("supervisor_eid")
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
                supervisor_slots = self._human_pronoun_slots(
                    eid=supervisor_eid,
                    personal_name=supervisor_name,
                    prefix="supervisor",
                )
                if workplace_name:
                    return f"{supervisor_name} owns {workplace_name}. Big calls go through {supervisor_slots['supervisor_object']}."
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
        lead_slots = self._human_pronoun_slots(
            eid=lead.get("eid"),
            personal_name=name,
            prefix="lead",
        )
        lead_do = self._human_present_verb(
            "do",
            eid=lead.get("eid"),
            personal_name=name,
        )

        if relation_text and career_text and place_name and place_role == "workplace":
            return f"{name} is my {relation_text} and does {career_text} work at {place_name}."
        if relation_text and place_name and place_role == "home":
            return f"{name} is my {relation_text} from around {place_name}."
        if relation_text and place_name and place_role == "workplace":
            return f"{name} is my {relation_text} over at {place_name}."
        if relation_text and career_text:
            return f"{name} is my {relation_text}, and {lead_slots['lead_subject']} {lead_do} {career_text} work."
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

    def _rapport_place_name(self, context):
        for key in ("workplace_name", "owner_place_name", "home_name"):
            value = str(context.get(key, "")).strip()
            if value:
                return value
        return "this part of town"

    def _rapport_day_note(self, context):
        shape = context.get("rapport_shape") if isinstance(context.get("rapport_shape"), dict) else {}
        mood = str(shape.get("day_mood", "steady") or "steady").strip().lower() or "steady"
        place = self._rapport_place_name(context)
        if mood == "frayed":
            return f"{place} has been running sharp enough to get under the skin."
        if mood == "tired":
            return "Long enough that I can feel it in my shoulders."
        if mood == "light":
            return "Lighter than most, for once."
        if mood == "warm":
            return "Better than I expected, honestly."
        return "Busy, but clean enough to stay ahead of it."

    def _rapport_job_note(self, context):
        shape = context.get("rapport_shape") if isinstance(context.get("rapport_shape"), dict) else {}
        attitude = str(shape.get("work_attitude", "practical") or "practical").strip().lower() or "practical"
        career_text = str(context.get("career_text", "")).strip() or "work"
        if attitude == "proud":
            return f"I take the {career_text} work seriously, even when it tries my patience."
        if attitude == "duty_bound":
            return f"Somebody has to hold the line on {career_text} work, so I do."
        if attitude == "worn":
            return f"It keeps me moving, but {career_text} work can take more out of a person than it gives back."
        if attitude == "restless":
            return f"I can do the {career_text} work, though I do not always want my whole life to calcify around it."
        if attitude == "stuck":
            return f"It pays, and some days that is the kindest thing I can say about {career_text} work."
        if attitude == "improvised":
            return "It changes day to day, and I make my peace with that."
        return f"It is {career_text} work. I do it well and I go home when I can."

    def _rapport_roots_note(self, context):
        shape = context.get("rapport_shape") if isinstance(context.get("rapport_shape"), dict) else {}
        attachment = float(shape.get("local_attachment", 0.5) or 0.5)
        home_name = str(context.get("home_name", "")).strip()
        workplace_name = str(context.get("workplace_name", "")).strip()
        if attachment >= 0.72 and home_name:
            return f"{home_name} is part of it. You stay somewhere long enough and it starts staking a claim back."
        if attachment >= 0.58 and workplace_name and home_name and workplace_name.lower() != home_name.lower():
            return f"Somewhere between {workplace_name} and {home_name}, this place stopped feeling temporary."
        if attachment <= 0.3:
            return "Maybe I just never found the right moment to pull loose."
        if workplace_name:
            return f"Work, habit, and a few faces around {workplace_name}. That is usually how roots sneak up on you."
        return "People, habit, and the fact that leaving is easier in theory than in practice."

    def _rapport_off_shift_note(self, context):
        shape = context.get("rapport_shape") if isinstance(context.get("rapport_shape"), dict) else {}
        playfulness = float(shape.get("playfulness", 0.5) or 0.5)
        home_name = str(context.get("home_name", "")).strip()
        workplace_name = str(context.get("workplace_name", "")).strip()
        if playfulness >= 0.66:
            return "I walk, eat something decent, and try to remember the day belongs to me for an hour."
        if home_name:
            return f"I usually head back toward {home_name} and let the noise burn off."
        if workplace_name:
            return f"I get clear of {workplace_name} long enough to hear myself think again."
        return "I keep it quiet if I can and let the day peel off on its own."

    def _rapport_care_note(self, context):
        shape = context.get("rapport_shape") if isinstance(context.get("rapport_shape"), dict) else {}
        pride = float(shape.get("profession_pride", 0.5) or 0.5)
        attachment = float(shape.get("local_attachment", 0.5) or 0.5)
        if pride >= 0.68 and attachment >= 0.6:
            return "I care about doing the work right and not leaving the people around me to eat the cost of sloppy hands."
        if attachment >= 0.68:
            return "I care whether the people around here get to breathe easy, even when nobody is paying me to care."
        if pride >= 0.68:
            return "I care about the work landing clean and my name meaning something decent at the end of it."
        return "A few people, a little quiet, and getting through the week with my name still feeling like mine."

    def _relationship_anchor_episode_for_context(self, context):
        anchor = context.get("relationship_anchor_episode") if isinstance(context, dict) else None
        return anchor if isinstance(anchor, dict) else None

    def _relationship_anchor_opening_line(self, context):
        anchor = self._relationship_anchor_episode_for_context(context)
        if not anchor:
            return ""
        kind = str(anchor.get("kind", "") or "").strip().lower()
        tone = str(context.get("tone", "neutral") or "neutral").strip().lower() or "neutral"
        if kind == "warned_me_off":
            return "We have had this talk before. Keep it cleaner this time."
        if kind == "i_pushed_too_far":
            return "Last time you pushed too far. Do not make me drag us back there."
        if kind == "i_insulted_them":
            return "Last time you took a cheap shot. I have not misplaced that."
        if kind == "offered_vouch":
            return "You handled yourself well enough that I still remember offering my name beside yours."
        if kind == "offered_introduction":
            return "Good to see you again. Last time I offered to put you in touch with someone useful."
        if kind == "offered_contact":
            return "Good to see you again. I still remember pointing you toward a useful name."
        if kind == "opened_up_personally":
            return "Good to see you again. Last time you asked something real and I answered it."
        if kind == "told_me_how_they_see_me":
            return "Good to see you again. I was plain with you last time, and that still counts for something."
        if kind in {"opened_up_about_work", "opened_up_about_roots"}:
            return "Good to see you again. I remember where we left the last real conversation."
        return ""

    def _relationship_anchor_check_in_note(self, context):
        anchor = self._relationship_anchor_episode_for_context(context)
        if not anchor:
            return "Same city, same weather in the bones. I am still here."
        kind = str(anchor.get("kind", "") or "").strip().lower()
        if kind == "opened_up_about_work":
            return "Better than when we last talked about work, or at least steadier."
        if kind == "opened_up_about_roots":
            return "About the same. The place still has its hooks in me."
        if kind == "opened_up_personally":
            return "A little steadier than last time, which is enough to call a win."
        if kind == "told_me_how_they_see_me":
            return "About the same, maybe clearer around the edges than I was last time."
        if kind == "offered_contact":
            return "I have been all right. Still trying to point my attention where it helps."
        if kind == "offered_introduction":
            return "Not bad. Still trying to keep the useful lines between people from snapping."
        if kind == "offered_vouch":
            return "Holding together. I do not offer my name lightly, so I still think about who earns it."
        if kind == "warned_me_off":
            return "Quieter than the last time we crossed paths, which suits me."
        if kind == "i_pushed_too_far":
            return "Better than the last conversation ended, and I would like to keep it that way."
        if kind == "i_insulted_them":
            return "Steadier than the mood you caught me in last time."
        return "Still upright. That counts."

    def _relationship_anchor_social_preface(self, context, topic_id, *, outcome=""):
        anchor = self._relationship_anchor_episode_for_context(context)
        if not anchor:
            return ""
        topic_id = str(topic_id or "").strip().lower()
        outcome = str(outcome or "").strip().lower()
        if outcome not in {"open", "warm", "reserved", "rebuff"}:
            outcome = ""
        kind = str(anchor.get("kind", "") or "").strip().lower()
        if kind in {"warned_me_off", "i_pushed_too_far", "i_insulted_them"}:
            if topic_id in {"read_player", "care_about"}:
                return "We are not talking on a blank slate."
            if topic_id in {"contacts", "introduction", "vouch"} and outcome in {"reserved", "rebuff"}:
                return "After last time, I am keeping this measured."
            return ""
        if topic_id == "read_player" and kind == "told_me_how_they_see_me":
            return "I was already plain with you once."
        if topic_id == "care_about" and kind in {"opened_up_personally", "opened_up_about_roots", "opened_up_about_work"}:
            return "You have asked me real questions before."
        if topic_id == "contacts" and kind in {"offered_contact", "offered_introduction"}:
            return "You have heard me point toward useful people before."
        if topic_id == "introduction" and kind == "offered_introduction":
            return "This is not the first time I have been willing to make that bridge."
        if topic_id == "vouch" and kind == "offered_vouch":
            return "You already know I do not put my name next to just anyone."
        return ""

    def _rapport_relationship_notes(self, context):
        npc_eid = context.get("npc_eid")
        entry = self._player_person_contact_entry(npc_eid) if npc_eid is not None else None
        profile = _relationship_read_profile(self.sim, self.player_eid, npc_eid, entry)
        anchor_preface = self._relationship_anchor_social_preface(context, "read_player", outcome="open")
        read_key = str(profile.get("read_key", "unknown") or "unknown").strip().lower() or "unknown"
        note_map = {
            "family": "I think of you as family.",
            "partner": "You read like a partner to me, plain and simple.",
            "friend": "You read like a friend.",
            "trusted_coworker": "You read like somebody I could work beside and trust.",
            "trusted_local": "You read like a familiar local I can trust.",
            "protective": "I catch myself looking out for you.",
            "trust": "I trust you more than I expected to.",
            "comfortable": "You do not put me on edge, and that counts.",
            "wary": "You make me keep one hand on the rail.",
            "distrust": "I do not trust you.",
            "unknown": "I am still working that out.",
        }
        warm_map = {
            "family": "I think of you as family, and I do not say that lightly.",
            "partner": "You read like a real partner to me, not just somebody passing through.",
            "friend": "You read like a friend to me, and that is not a cheap word.",
            "trusted_coworker": "You read like someone I could trust beside me when the floor goes bad.",
            "trusted_local": "You read like one of ours, in the good sense.",
            "protective": "I catch myself looking out for you before I even mean to.",
            "trust": "I trust you more than I expected to, which is not nothing.",
            "comfortable": "You do not put me on edge, and that goes farther than you might think.",
            "wary": "You still make me watch myself around you.",
            "distrust": "I do not trust you, and I would rather be plain than pretty about it.",
            "unknown": "I have a read on you, but it is still more outline than person.",
        }
        base_note = note_map.get(read_key, note_map["unknown"])
        warm_note = warm_map.get(read_key, warm_map["unknown"])
        if anchor_preface:
            base_note = f"{anchor_preface} {base_note}"
            warm_note = f"{anchor_preface} {warm_note}"
        return {
            "profile": profile,
            "note": base_note,
            "warm_note": warm_note,
        }

    def _rapport_render_context(self, context):
        rendered = dict(context or {})
        relationship = self._rapport_relationship_notes(context)
        extras = {
            "rapport_place": self._rapport_place_name(context),
            "rapport_day_note": self._rapport_day_note(context),
            "rapport_job_note": self._rapport_job_note(context),
            "rapport_roots_note": self._rapport_roots_note(context),
            "rapport_off_shift_note": self._rapport_off_shift_note(context),
            "rapport_care_note": self._rapport_care_note(context),
            "rapport_check_in_note": self._relationship_anchor_check_in_note(context),
            "rapport_read_note": relationship["note"],
            "rapport_read_warm_note": relationship["warm_note"],
        }
        for key, value in tuple(extras.items()):
            text = str(value or "").strip()
            rendered[key] = text
            rendered[f"{key}_lc"] = _dialogue_lower_start(text)
        rendered["rapport_relationship_profile"] = relationship["profile"]
        return rendered

    def _rapport_topic_available(self, context, topic_id):
        topic_id = str(topic_id or "").strip().lower()
        if not bool(context.get("human", True)) or bool(context.get("guarded")):
            return False
        if topic_id == "rapport":
            return not bool(context.get("door_answering"))
        if topic_id == "check_in":
            min_elapsed = max(60, int(round(float(self.CHECK_IN_MIN_HOURS) * float(self._ticks_per_hour()))))
            return (
                bool(context.get("met_directly"))
                and bool(context.get("relationship_has_nontrivial_history"))
                and str(context.get("pressure_tier", "low")).strip().lower() != "high"
                and self._check_in_elapsed_ticks(context) >= min_elapsed
            )
        if topic_id == "job_feel":
            return bool(str(context.get("career_text", "")).strip())
        if topic_id == "roots":
            return bool(self._history_summary(context))
        if topic_id == "off_shift":
            return bool(self._rapport_off_shift_note(context))
        if topic_id == "care_about":
            return (
                float(context.get("social_standing", 0.0) or 0.0) >= 0.46
                and int(context.get("opened_count", 0) or 0) >= 2
                and str(context.get("pressure_tier", "low")).strip().lower() != "high"
            )
        if topic_id == "read_player":
            return (
                float(context.get("social_standing", 0.0) or 0.0) >= 0.58
                and bool(context.get("met_directly"))
                and int(context.get("opened_count", 0) or 0) >= 2
            )
        return True

    def _rapport_topic_outcome(self, context, topic_id, *, ask_count=1):
        shape = context.get("rapport_shape") if isinstance(context.get("rapport_shape"), dict) else {}
        chattiness = float(shape.get("chattiness", 0.5) or 0.5)
        privacy = float(shape.get("privacy", 0.5) or 0.5)
        pride = float(shape.get("profession_pride", 0.5) or 0.5)
        attachment = float(shape.get("local_attachment", 0.5) or 0.5)
        playfulness = float(shape.get("playfulness", 0.5) or 0.5)
        mood = str(shape.get("day_mood", "steady") or "steady").strip().lower() or "steady"
        attitude = str(shape.get("work_attitude", "practical") or "practical").strip().lower() or "practical"

        bond = context.get("bond") if isinstance(context.get("bond"), dict) else self._bond_snapshot(context.get("npc_eid")) or {}
        trust = float(bond.get("trust", 0.0) or 0.0)
        closeness = float(bond.get("closeness", 0.0) or 0.0)
        standing = float(context.get("social_standing", 0.0) or 0.0)
        tone = str(context.get("tone", "neutral") or "neutral").strip().lower() or "neutral"
        pressure_tier = str(context.get("pressure_tier", "low") or "low").strip().lower() or "low"
        pressure_penalty = {"low": 0.0, "medium": 0.06, "high": 0.14}.get(pressure_tier, 0.0)

        needs = context.get("npc_needs") or NPCNeeds()
        social_hunger = max(0.0, min(1.0, (52.0 - float(getattr(needs, "social", 55.0) or 55.0)) / 52.0))
        fatigue = max(0.0, min(1.0, (46.0 - float(getattr(needs, "energy", 60.0) or 60.0)) / 46.0))
        safety_stress = max(0.0, min(1.0, (54.0 - float(getattr(needs, "safety", 70.0) or 70.0)) / 54.0))

        if topic_id == "check_in" and not self._rapport_topic_available(context, topic_id):
            return "rebuff"
        if topic_id == "care_about" and not self._rapport_topic_available(context, topic_id):
            return "rebuff"
        if topic_id == "read_player" and not self._rapport_topic_available(context, topic_id):
            return "rebuff"

        mood_bonus = {
            "frayed": -0.07,
            "tired": -0.04,
            "steady": 0.0,
            "light": 0.04,
            "warm": 0.08,
        }.get(mood, 0.0)
        attitude_bonus = {
            "proud": 0.08,
            "duty_bound": 0.06,
            "practical": 0.02,
            "restless": -0.01,
            "stuck": -0.03,
            "worn": -0.05,
            "improvised": 0.0,
        }.get(attitude, 0.0)

        if topic_id in {"rapport", "day_feel", "off_shift"}:
            score = 0.22 + (chattiness * 0.3) + (playfulness * 0.14) + (social_hunger * 0.14) + (standing * 0.14)
            score += mood_bonus - (privacy * 0.1) - (fatigue * 0.08) - (safety_stress * 0.1)
        elif topic_id == "check_in":
            anchor = self._relationship_anchor_episode_for_context(context) or {}
            valence = str(anchor.get("valence", "neutral") or "neutral").strip().lower() or "neutral"
            score = 0.24 + (chattiness * 0.18) + (trust * 0.18) + (closeness * 0.14) + (social_hunger * 0.12)
            score += mood_bonus - (privacy * 0.08) - (fatigue * 0.08) - (safety_stress * 0.08)
            if valence == "positive":
                score += 0.08
            elif valence == "negative":
                score -= 0.08
        elif topic_id == "job_feel":
            score = 0.2 + (pride * 0.34) + (standing * 0.16) + (trust * 0.12)
            score += attitude_bonus - (privacy * 0.08) - (fatigue * 0.08)
        elif topic_id == "roots":
            score = 0.18 + (attachment * 0.3) + (standing * 0.18) + (trust * 0.14)
            score -= (privacy * 0.16) + (safety_stress * 0.06)
        elif topic_id == "care_about":
            score = 0.08 + (standing * 0.26) + (trust * 0.24) + (closeness * 0.12) + (attachment * 0.08) + (pride * 0.08)
            score -= (privacy * 0.26) + (safety_stress * 0.08)
        elif topic_id == "read_player":
            relationship = self._rapport_relationship_notes(context)
            read_key = str((relationship.get("profile") or {}).get("read_key", "unknown") or "unknown").strip().lower()
            score = 0.16 + (standing * 0.22) + (trust * 0.18) + (closeness * 0.16) - (privacy * 0.14)
            if read_key in {"friend", "family", "partner", "trusted_coworker", "trusted_local", "protective"}:
                score += 0.08
            elif read_key in {"wary", "distrust"}:
                score -= 0.06
        else:
            score = 0.28

        if tone == "friendly":
            score += 0.05
        elif tone == "wary":
            score -= 0.1
        score -= pressure_penalty
        score -= max(0, int(ask_count) - 1) * (0.04 if topic_id in {"care_about", "read_player"} else 0.025)
        score = max(0.0, min(1.0, score))

        warm_threshold = 0.7 if topic_id in {"care_about", "read_player"} else 0.64
        open_threshold = 0.5 if topic_id in {"care_about", "read_player"} else 0.42
        reserved_threshold = 0.32 if topic_id in {"care_about", "read_player"} else 0.24

        if topic_id == "read_player":
            read_key = str(self._rapport_relationship_notes(context).get("profile", {}).get("read_key", "unknown") or "unknown").strip().lower()
            if read_key in {"wary", "distrust", "unknown"}:
                warm_threshold = 1.1

        if score >= warm_threshold:
            return "warm"
        if score >= open_threshold:
            return "open"
        if score >= reserved_threshold:
            return "reserved"
        return "rebuff"

    def _remember_bonding_dialogue_memory(self, npc_eid, *, approval=0.0, strength=0.0):
        memory = self.sim.ecs.get(NPCMemory).get(npc_eid)
        if memory is None or abs(float(approval)) < 0.01 or float(strength) <= 0.0:
            return
        strength = max(0.08, min(0.4, float(strength)))
        approval = max(-1.0, min(1.0, float(approval)))
        memory.remember(
            self.sim.tick,
            kind="actor_reputation",
            strength=strength,
            actor_eid=self.player_eid,
            approval=approval,
            via="bonding_dialogue",
        )
        if approval > 0.0:
            memory.remember(
                self.sim.tick,
                kind="player_reputation",
                strength=max(0.1, strength * 0.82),
                player_eid=self.player_eid,
                approval=approval,
                via="bonding_dialogue",
            )

    def _rapport_bond_delta(self, topic_id, outcome):
        topic_id = str(topic_id or "").strip().lower()
        outcome = str(outcome or "").strip().lower()
        deeper = topic_id in {"care_about", "read_player"}
        if outcome == "open":
            return (0.012, 0.02) if deeper else (0.008, 0.015)
        if outcome == "warm":
            return (0.02, 0.03) if deeper else (0.014, 0.024)
        if outcome == "rebuff":
            return (-0.015, -0.008) if deeper else (-0.01, 0.0)
        return (0.0, 0.0)

    def _dialogue_rapport_reaction_line(self, context, topic_id, *, ask_count=1, outcome="reserved"):
        rendered_context = self._rapport_render_context(context)
        fallback_order = {
            "warm": ("warm", "open", "reserved"),
            "open": ("open", "reserved"),
            "reserved": ("reserved",),
            "rebuff": ("rebuff", "reserved"),
        }.get(str(outcome or "reserved").strip().lower(), ("reserved",))
        for candidate in fallback_order:
            line = _dialogue_topic_player_reaction_line(
                topic_id,
                seed=self.sim.seed,
                npc_eid=context.get("npc_eid"),
                count=ask_count,
                outcome=candidate,
                context=rendered_context,
            )
            if str(line or "").strip():
                return line
        return ""

    def _resolve_rapport_topic(self, context, topic_id, *, ask_count=1):
        topic_id = str(topic_id or "").strip().lower()
        outcome = self._rapport_topic_outcome(context, topic_id, ask_count=ask_count)
        line = self._dialogue_rapport_reaction_line(
            context,
            topic_id,
            ask_count=ask_count,
            outcome=outcome,
        )
        trust_delta, closeness_delta = self._rapport_bond_delta(topic_id, outcome)
        if outcome in {"open", "warm", "rebuff"}:
            self._shift_dialogue_bond(
                context["npc_eid"],
                trust_delta=trust_delta,
                closeness_delta=closeness_delta,
                guarded=False,
            )
        if outcome == "warm":
            self._remember_bonding_dialogue_memory(
                context["npc_eid"],
                approval=0.22 if topic_id in {"care_about", "read_player"} else 0.16,
                strength=0.22 if topic_id in {"care_about", "read_player"} else 0.16,
            )
        elif outcome == "rebuff":
            self._remember_bonding_dialogue_memory(
                context["npc_eid"],
                approval=-0.18 if topic_id in {"care_about", "read_player"} else -0.1,
                strength=0.16 if topic_id in {"care_about", "read_player"} else 0.1,
            )

        close_dialog = False
        if outcome == "rebuff" and topic_id in {"care_about", "read_player"} and ask_count >= 2:
            close_dialog = True
            self._emit_dialogue_offended(
                context["npc_eid"],
                context_id=f"dialogue_{topic_id}",
                perceived=0.34,
                offense_score=10,
            )
        elif outcome == "rebuff" and topic_id in {"care_about", "read_player"}:
            self._emit_dialogue_offended(
                context["npc_eid"],
                context_id=f"dialogue_{topic_id}",
                perceived=0.18,
                offense_score=6,
            )

        if not line:
            if outcome == "rebuff":
                line = "That is more personal than I want to go right now."
            elif outcome == "warm":
                line = "You asked that in a way I can answer honestly."
            elif outcome == "open":
                line = "Fair question."
            else:
                line = "Maybe another time."
        preface = self._relationship_anchor_social_preface(context, topic_id, outcome=outcome)
        npc_lines = [text for text in (preface, line) if str(text or "").strip()]

        if outcome in {"open", "warm"}:
            property_id = ""
            current_prop = context.get("current_prop")
            if isinstance(current_prop, dict):
                property_id = str(current_prop.get("id", "") or "").strip()
            episode_map = {
                "job_feel": ("opened_up_about_work", "positive", "They opened up a little about how the work sits with them."),
                "roots": ("opened_up_about_roots", "positive", "They spoke a little about what keeps them here."),
                "care_about": ("opened_up_personally", "positive", "They opened up about what matters to them."),
                "read_player": ("told_me_how_they_see_me", "positive", "They told you how they seem to read you."),
            }
            episode_bits = episode_map.get(topic_id)
            if episode_bits:
                self._remember_player_relationship_episode(
                    context["npc_eid"],
                    kind=episode_bits[0],
                    valence=episode_bits[1],
                    summary=episode_bits[2],
                    property_id=property_id or None,
                    source_topic=topic_id,
                    relation_kind=(context.get("bond") or {}).get("kind"),
                    standing=float(context.get("contact_standing", 0.0) or 0.0),
                    met_directly=True,
                    benefits={"known_name"},
                )

        return {
            "npc_lines": npc_lines,
            "close": bool(close_dialog),
            "social_outcome": outcome,
        }

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
                    return f"across town, in the general vicinity of {spoken_dir}"
                return f"across town {dir_to_phrase}"
            return "across town"

        if distance <= 6:
            if can_use_direction:
                return f"not far off, probably to {spoken_dir}"
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
                return f"{km_phrase} or so, somewhere to {spoken_dir}"
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
            contact_slots = self._human_pronoun_slots(personal_name=contact_name, prefix="contact")
            contact_set = self._human_present_verb("set", personal_name=contact_name)
            return f"Start by reading {contact_name} at {place_name}; {contact_slots['contact_subject']} {contact_set} the rhythm."
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

    def _objective_focus_line_for_opportunity(self, context, row=None):
        context = context if isinstance(context, dict) else {}
        focus_rows = [
            dict(focus)
            for focus in tuple(context.get("objective_focus_rows", ()) or ())
            if isinstance(focus, dict)
        ]
        if not focus_rows:
            return ""
        target_id = 0
        if isinstance(row, dict):
            try:
                target_id = int(row.get("id", 0) or 0)
            except (TypeError, ValueError):
                target_id = 0
        if target_id <= 0:
            try:
                target_id = int(context.get("primary_opportunity_id", 0) or 0)
            except (TypeError, ValueError):
                target_id = 0
        if target_id <= 0:
            return ""
        for focus in focus_rows:
            try:
                focus_id = int(focus.get("id", 0) or 0)
            except (TypeError, ValueError):
                focus_id = 0
            if focus_id == target_id:
                return str(focus.get("line", focus.get("phrase", ""))).strip()
        return ""

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
                focus_line = self._objective_focus_line_for_opportunity(context, row)
                if focus_line:
                    base = f"{base} {focus_line}"
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

            focus_line = self._objective_focus_line_for_opportunity(context, row)
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
            other_name = str(context.get("other_name", "")).strip()
            other_slots = self._human_pronoun_slots(
                eid=context.get("other_eid"),
                personal_name=other_name,
                prefix="other",
            )
            other_admit = self._human_present_verb(
                "admit",
                eid=context.get("other_eid"),
                personal_name=other_name,
            )
            return f"{other_name} stays close to more of the local trouble than {other_slots['other_subject']} {other_admit}."
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
        if tactic == "pry" and outcome in {"wary", "fail"}:
            self._remember_player_relationship_episode(
                npc_eid,
                kind="i_pushed_too_far",
                valence="negative",
                summary="You pushed too far and they closed up.",
                source_topic=tactic,
                relation_kind=(context.get("bond") or {}).get("kind"),
                standing=float(context.get("contact_standing", 0.0) or 0.0),
                met_directly=bool(context.get("met_directly")),
                benefits={"known_name"} if self._player_knows_person_name(npc_eid) else (),
            )
        elif tactic == "insult" and outcome in {"wary", "fail"}:
            self._remember_player_relationship_episode(
                npc_eid,
                kind="i_insulted_them",
                valence="negative",
                summary="You insulted them and it landed badly.",
                source_topic=tactic,
                relation_kind=(context.get("bond") or {}).get("kind"),
                standing=float(context.get("contact_standing", 0.0) or 0.0),
                met_directly=bool(context.get("met_directly")),
                benefits={"known_name"} if self._player_knows_person_name(npc_eid) else (),
            )
        return {
            "npc_lines": [line],
            "close": bool(close_dialog),
            "social_misstep": tactic,
            "social_outcome": outcome,
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

    def _dialogue_narration_line(self, text):
        return str(text or "").strip()

    def _dialogue_social_reaction_line(self, context, topic_id, *, ask_count=1, outcome=""):
        npc_eid = context.get("npc_eid") if isinstance(context, dict) else None
        if npc_eid is None:
            return ""
        reaction_context = dict(context or {})
        reaction_context["opened_count"] = int(self._dialogue_memory(npc_eid).get("opened_count", 0))
        line = _social_reaction_narration(
            self.sim,
            npc_eid,
            topic_id=topic_id,
            outcome=outcome,
            ask_count=ask_count,
            context=reaction_context,
            rapport_shape=reaction_context.get("rapport_shape"),
        )
        return self._dialogue_narration_line(line)

    def _dialogue_human_narration_line(self, context):
        identity = context.get("identity")
        if not is_human_identity(identity):
            return ""
        return self._dialogue_narration_line(
            human_conversation_description(
                getattr(self.sim, "seed", 0),
                eid=context.get("npc_eid"),
                identity=identity,
                personal_name=getattr(identity, "personal_name", ""),
            )
        )

    def _player_dialogue_identity(self):
        if self.sim is None or self.player_eid is None:
            return None
        identities = self.sim.ecs.get(CreatureIdentity)
        return identities.get(self.player_eid) if identities is not None else None

    def _player_dialogue_address_term(self):
        return str(player_address_term(self._player_dialogue_identity(), default="nonbinary") or "").strip()

    def _authority_player_address_line(self, context, *, open_count=0):
        player_term = self._player_dialogue_address_term()
        if not player_term:
            return ""
        role_id = str(context.get("role_id", "") or "").strip().lower()
        workplace_archetype = str(context.get("workplace_archetype", "") or "").strip().lower()
        owner_place_archetype = str(context.get("owner_place_archetype", "") or "").strip().lower()
        pressure_role = str(self._dialogue_pressure_role(context) or "").strip().lower()
        authority_like = (
            role_id in {"guard", "cop", "peace_officer", "security", "scout"}
            or pressure_role == "guard"
            or workplace_archetype in set(self.JUSTICE_LOCATOR_ARCHETYPES)
            or owner_place_archetype in set(self.JUSTICE_LOCATOR_ARCHETYPES)
        )
        if not authority_like:
            return ""
        variants = (
            "Questions first, {player_address}.",
            "Easy, {player_address}.",
            "Hold there, {player_address}.",
            "Keep it clean, {player_address}.",
        )
        rng = random.Random(
            f"{getattr(self.sim, 'seed', 0)}:player-address:{context.get('npc_eid', 0)}:{open_count}:{role_id}:{pressure_role}"
        )
        return rng.choice(variants).format(player_address=player_term)

    def _dialogue_opening_lines_with_narration(self, context, lines):
        resolved = [str(line).strip() for line in tuple(lines or ()) if str(line).strip()]
        narration = self._dialogue_human_narration_line(context)
        if narration:
            return [narration] + [line for line in resolved if line]
        return resolved

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
            return self._dialogue_opening_lines_with_narration(context, [
                self._dialogue_npc_line(
                    context["npc_name"],
                    "Okay. I dropped it. Just tell me where you want me.",
                )
            ])
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
            return self._dialogue_opening_lines_with_narration(context, lines)
        if context.get("guarded"):
            first = self._say(
                "greet_guarded",
                context,
                topic_id="greet",
                count=open_count,
                npc_name=context["npc_name"],
            )
            lines = [self._dialogue_npc_line(context["npc_name"], first)]
            address_line = self._authority_player_address_line(context, open_count=open_count)
            if address_line:
                lines.append(self._dialogue_npc_line(context["npc_name"], address_line))
            if context.get("trespass_prop"):
                prop_name = str(context["trespass_prop"].get("name", context["trespass_prop"].get("id", "property"))).strip() or "property"
                lines.append(self._dialogue_npc_line(context["npc_name"], f"You should not be hanging around {prop_name}."))
            elif context.get("recent_offense"):
                action = str(context["recent_offense"].get("data", {}).get("action", "trouble")).replace("_", " ").strip() or "trouble"
                lines.append(self._dialogue_npc_line(context["npc_name"], f"I still remember your {action}."))
            anchor_line = self._relationship_anchor_opening_line(context)
            if anchor_line:
                lines.append(self._dialogue_npc_line(context["npc_name"], anchor_line))
            return self._dialogue_opening_lines_with_narration(context, lines)
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
        anchor_line = self._relationship_anchor_opening_line(context)
        if anchor_line:
            lines.append(self._dialogue_npc_line(context["npc_name"], anchor_line))
        for shaped_line in _shaped_opening_lines(context, limit=1):
            formatted = self._dialogue_npc_line(context["npc_name"], shaped_line)
            if formatted and formatted not in lines:
                lines.append(formatted)
        return self._dialogue_opening_lines_with_narration(context, lines)

    def _available_dialog_topics(self, context):
        available = []
        unlocked = set(self._dialogue_memory(context["npc_eid"])["unlocked_topics"])
        if bool(context.get("run_objective_visible")) and (
            str(context.get("final_operation_summary_line", "")).strip()
            or str(context.get("final_operation_target_property_id", "")).strip()
            or str(context.get("final_operation_target_entry_detail", "")).strip()
        ):
            unlocked.update({"objective", "angle", "risk"})
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
            if topic_id == "street_appraise" and not context.get("street_appraise_available"):
                continue
            if topic_id == "street_buy" and (not context.get("street_buy_available") or context.get("street_buy_offer_pending")):
                continue
            if topic_id == "street_buy_next" and (
                not context.get("street_buy_offer_pending")
                or not context.get("street_buy_offer_next_available")
            ):
                continue
            if topic_id in {"street_buy_accept", "street_buy_decline"} and not context.get("street_buy_offer_pending"):
                continue
            if topic_id in {"rapport", "check_in", "day_feel", "job_feel", "roots", "off_shift", "care_about", "read_player"} and not self._rapport_topic_available(context, topic_id):
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
            if topic_id in self.SENSITIVE_INFO_TOPICS and not self._sensitive_info_topic_available(context, topic_id):
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
            if topic_id == "street_appraise" and not context.get("street_appraise_available"):
                continue
            if topic_id == "street_buy" and not context.get("street_buy_available"):
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
            memory = self._dialogue_memory(context["npc_eid"])
            ask_count = self._dialogue_topic_count(context["npc_eid"], topic_id)
            total_asked = self._dialogue_total_topics_asked(context["npc_eid"])
            previous_topic_id = str(memory.get("last_topic_id", "")).strip().lower()
            next_count = ask_count + 1
            label = _dialogue_topic_menu_label(
                topic_id,
                seed=self.sim.seed,
                npc_eid=context.get("npc_eid"),
                count=next_count,
                context=context,
                previous_topic_id=previous_topic_id,
                total_asked=total_asked,
                opened_count=int(memory.get("opened_count", 0) or 0),
            )
            available.append({
                "id": topic_id,
                "label": label,
                "player_line": _dialogue_topic_player_line(
                    topic_id,
                    seed=self.sim.seed,
                    npc_eid=context.get("npc_eid"),
                    count=next_count,
                    context=context,
                    previous_topic_id=previous_topic_id,
                    total_asked=total_asked + 1,
                    line_override=label,
                ),
            })
        return self._augment_repeat_dialogue_rows(context, available)

    def _prioritize_dialog_topics(self, topics, highlight_topic_ids=()):
        highlight = {
            str(topic_id or "").strip().lower()
            for topic_id in tuple(highlight_topic_ids or ())
            if str(topic_id or "").strip()
        }
        if not highlight:
            return list(topics or ())

        preferred = []
        remainder = []
        seen = set()
        for row in list(topics or ()):
            topic_id = str((row or {}).get("id", "") or "").strip().lower()
            if topic_id in highlight and topic_id not in seen:
                preferred.append(row)
                seen.add(topic_id)
            else:
                remainder.append(row)
        return preferred + remainder

    def _open_dialogue(self, context, *, prompt_lines=(), highlight_topic_ids=()):
        memory = self._dialogue_memory(context["npc_eid"])
        state = self._dialog_ui_state()
        transcript = self._dialogue_opening_lines(context)
        for raw_line in tuple(prompt_lines or ()):
            line = str(raw_line or "").strip()
            if not line:
                continue
            formatted = self._dialogue_npc_line(context["npc_name"], line)
            if formatted and formatted not in transcript:
                transcript.append(formatted)
        self.sim.set_time_paused(True, reason="dialog")
        current_tick = int(getattr(self.sim, "tick", 0))
        _rehydrate_entity_knowledge(
            self.sim,
            self.player_eid,
            radius=18,
            search_radius=10,
            current_tick=current_tick,
            reason="dialog_open",
        )
        _rehydrate_entity_knowledge(
            self.sim,
            context["npc_eid"],
            radius=18,
            search_radius=10,
            current_tick=current_tick,
            reason="dialog_open",
        )
        state.update({
            "open": True,
            "kind": "conversation",
            "npc_eid": context["npc_eid"],
            "property_id": None,
            "title": f"Conversation: {context['npc_name']}",
            "subtitle": context.get("subtitle", ""),
            "transcript": transcript,
            "topics": self._prioritize_dialog_topics(
                self._available_dialog_topics(context),
                highlight_topic_ids=highlight_topic_ids,
            ),
            "selected_index": 0,
            "scroll": 0,
            "hint": self._dialogue_hint_text(context),
            "new_topic_ids": [],
            "close_pending": False,
            "street_buy_offer": None,
            "street_buy_skipped_instance_ids": [],
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
            "street_buy_offer": None,
            "street_buy_skipped_instance_ids": [],
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
            "street_buy_offer": None,
            "street_buy_skipped_instance_ids": [],
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
        self._remember_player_relationship_episode(
            lead.get("eid"),
            kind="introduced_to_me",
            valence="neutral",
            summary=f"You were introduced to {lead.get('name', 'someone')} by {context['npc_name']}.",
            property_id=lead.get("property_id"),
            other_person_eid=context["npc_eid"],
            source_topic="introduction",
            source_eid=context["npc_eid"],
            relation_kind=lead.get("relation_kind"),
            standing=standing,
            introduced=True,
            benefits={"known_name"},
        )

        return {
            "lead": lead,
            "standing": standing,
            "newly_learned": bool(changed),
            "contact_context": self._introduction_context_text(lead),
        }

    def _dialogue_contact_response(self, context, *, vouch=False):
        topic_id = "vouch" if vouch else "contacts"
        ask_count = self._dialogue_topic_count(context["npc_eid"], topic_id)
        standing = float(context.get("contact_standing", 0.0) or 0.0)
        preface = self._relationship_anchor_social_preface(context, topic_id, outcome="open")
        if context.get("guarded"):
            bank_id = "contacts_hard_no"
            return {
                "line": self._say(bank_id, context, topic_id=topic_id, count=ask_count, npc_name=context["npc_name"]),
                "social_outcome": "rebuff",
            }
        if self._pressure_contact_blocked(context, "vouch" if vouch else "contact"):
            bank_id = self._pressure_contact_bank("vouch_caution_no" if vouch else "contacts_caution_no", context)
            return {
                "line": self._say(bank_id, context, topic_id=topic_id, count=ask_count, npc_name=context["npc_name"]),
                "social_outcome": "reserved",
            }
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
                    outcome = "reserved"
                else:
                    bank_id = "vouch_offer" if ask_count <= 1 else "vouch_repeat"
                    outcome = "warm" if standing >= 0.62 else "open"
            else:
                if self._pressure_offer_is_cautious(context, "contact"):
                    bank_id = self._pressure_contact_bank("contacts_offer_caution", context)
                    outcome = "reserved"
                else:
                    bank_id = "contacts_offer" if ask_count <= 1 else "contacts_repeat"
                    outcome = "warm" if standing >= 0.64 else "open"
            return {
                "line": self._say(
                    bank_id,
                    context,
                    topic_id=topic_id,
                    count=ask_count,
                    npc_name=context["npc_name"],
                    contact_place=prop_name,
                ),
                "social_outcome": outcome,
                "preface": preface,
                "episode_kind": "offered_vouch" if vouch else "offered_contact",
                "episode_summary": "They offered to vouch for you." if vouch else "They pointed you toward a useful contact.",
            }
        if not vouch:
            target = self._introduction_target(context)
            if target:
                if self._pressure_contact_blocked(context, "introduction"):
                    return {
                        "line": self._say("contacts_caution_no", context, topic_id=topic_id, count=ask_count, npc_name=context["npc_name"]),
                        "social_outcome": "reserved",
                    }
                bank_id = "contacts_person_hint" if ask_count <= 1 else "contacts_person_repeat"
                return {
                    "line": self._say(
                        bank_id,
                        context,
                        topic_id=topic_id,
                        count=ask_count,
                        contact_name=target.get("name", "someone"),
                        contact_context=self._introduction_context_text(target),
                        **self._human_pronoun_slots(
                            eid=target.get("eid"),
                            personal_name=target.get("name", "someone"),
                            prefix="contact",
                        ),
                    ),
                    "social_outcome": "warm" if standing >= 0.62 else "open",
                    "preface": preface,
                    "episode_kind": "offered_contact",
                    "episode_summary": "They pointed you toward someone useful to know.",
                }
        bank_id = "vouch_soft_no" if vouch else "contacts_soft_no"
        return {
            "line": self._say(bank_id, context, topic_id=topic_id, count=ask_count, npc_name=context["npc_name"]),
            "social_outcome": "reserved",
        }

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
        if topic_id == "roots":
            return self._resolve_rapport_topic(context, topic_id, ask_count=ask_count)
        if topic_id == "job":
            if context.get("career_text"):
                bank_id = "job_first" if ask_count <= 1 else "job_repeat"
                return {"npc_lines": [self._say(bank_id, context, topic_id=topic_id, count=ask_count, career_text=context["career_text"])]}
            return {"npc_lines": [self._say("job_none", context, topic_id=topic_id, count=ask_count)]}
        if topic_id == "job_feel":
            return self._resolve_rapport_topic(context, topic_id, ask_count=ask_count)
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
        if topic_id == "rapport":
            return self._resolve_rapport_topic(context, topic_id, ask_count=ask_count)
        if topic_id == "check_in":
            return self._resolve_rapport_topic(context, topic_id, ask_count=ask_count)
        if topic_id == "day_feel":
            return self._resolve_rapport_topic(context, topic_id, ask_count=ask_count)
        if topic_id == "off_shift":
            return self._resolve_rapport_topic(context, topic_id, ask_count=ask_count)
        if topic_id == "care_about":
            return self._resolve_rapport_topic(context, topic_id, ask_count=ask_count)
        if topic_id == "read_player":
            return self._resolve_rapport_topic(context, topic_id, ask_count=ask_count)
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
                    social_outcome = "reserved"
                else:
                    bank_id = "introduction_offer" if ask_count <= 1 else "introduction_repeat"
                    social_outcome = "warm" if float(offer.get("standing", 0.0) or 0.0) >= 0.62 else "open"
                self._remember_player_relationship_episode(
                    npc_eid,
                    kind="offered_introduction",
                    valence="positive",
                    summary=f"They offered to introduce you to {lead.get('name', 'someone')}.",
                    property_id=str(lead.get("property_id", "") or "").strip() or None,
                    other_person_eid=lead.get("eid"),
                    source_topic=topic_id,
                    relation_kind=(context.get("bond") or {}).get("kind"),
                    standing=float(offer.get("standing", 0.0) or 0.0),
                    met_directly=True,
                    benefits={"known_name"},
                )
                return {
                    "npc_lines": [
                        text
                        for text in (
                            self._relationship_anchor_social_preface(context, topic_id, outcome=social_outcome),
                            self._say(
                                bank_id,
                                context,
                                topic_id=topic_id,
                                count=ask_count,
                                contact_name=lead.get("name", "someone"),
                                contact_context=offer.get("contact_context", "someone worth meeting"),
                                **self._human_pronoun_slots(
                                    eid=lead.get("eid"),
                                    personal_name=lead.get("name", "someone"),
                                    prefix="contact",
                                ),
                            ),
                        )
                        if str(text or "").strip()
                    ],
                    "social_outcome": social_outcome,
                }
            if self._pressure_contact_blocked(context, "introduction"):
                return {
                    "npc_lines": [self._say("introduction_caution_no", context, topic_id=topic_id, count=ask_count)],
                    "social_outcome": "reserved",
                }
            return {
                "npc_lines": [self._say("introduction_soft_no", context, topic_id=topic_id, count=ask_count)],
                "social_outcome": "reserved",
            }
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
                    hidden=True if bool(spec.get("hidden_lead")) else None,
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
            if not self._sensitive_info_topic_available(context, topic_id):
                return {"npc_lines": [self._sensitive_info_block_line(context, topic_id)]}
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
            if not self._sensitive_info_topic_available(context, topic_id):
                return {"npc_lines": [self._sensitive_info_block_line(context, topic_id)]}
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
                line = self._say(
                    "local_other_bond",
                    context,
                    topic_id=topic_id,
                    count=ask_count,
                    other_name=context["other_name"],
                    other_hear=self._human_present_verb(
                        "hear",
                        eid=context.get("other_eid"),
                        personal_name=context.get("other_name", ""),
                    ),
                    **self._human_pronoun_slots(
                        eid=context.get("other_eid"),
                        personal_name=context.get("other_name", ""),
                        prefix="other",
                    ),
                )
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
                reveal_run_objective(self.sim, source="dialogue_opportunities")
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
            contact_response = self._dialogue_contact_response(context, vouch=False)
            if contact_response.get("episode_kind") and contact_response.get("social_outcome") in {"open", "warm", "reserved"}:
                place = context.get("workplace_prop") or context.get("owned_prop") or context.get("current_prop")
                property_id = str(place.get("id", "") or "").strip() if isinstance(place, dict) else ""
                self._remember_player_relationship_episode(
                    npc_eid,
                    kind=contact_response.get("episode_kind"),
                    valence="positive",
                    summary=str(contact_response.get("episode_summary", "")).strip(),
                    property_id=property_id or None,
                    source_topic=topic_id,
                    relation_kind=(context.get("bond") or {}).get("kind"),
                    standing=float(context.get("contact_standing", 0.0) or 0.0),
                    met_directly=True,
                    benefits={"known_name"},
                )
            return {
                "npc_lines": [
                    text
                    for text in (
                        contact_response.get("preface", ""),
                        contact_response.get("line", ""),
                    )
                    if str(text or "").strip()
                ],
                "social_outcome": contact_response.get("social_outcome", ""),
            }
        if topic_id == "vouch":
            contact_response = self._dialogue_contact_response(context, vouch=True)
            if contact_response.get("episode_kind") and contact_response.get("social_outcome") in {"open", "warm", "reserved"}:
                place = context.get("workplace_prop") or context.get("owned_prop") or context.get("current_prop")
                property_id = str(place.get("id", "") or "").strip() if isinstance(place, dict) else ""
                self._remember_player_relationship_episode(
                    npc_eid,
                    kind=contact_response.get("episode_kind"),
                    valence="positive",
                    summary=str(contact_response.get("episode_summary", "")).strip(),
                    property_id=property_id or None,
                    source_topic=topic_id,
                    relation_kind=(context.get("bond") or {}).get("kind"),
                    standing=float(context.get("contact_standing", 0.0) or 0.0),
                    met_directly=True,
                    benefits={"known_name"},
                )
            return {
                "npc_lines": [
                    text
                    for text in (
                        contact_response.get("preface", ""),
                        contact_response.get("line", ""),
                    )
                    if str(text or "").strip()
                ],
                "social_outcome": contact_response.get("social_outcome", ""),
            }
        if topic_id == "trade":
            if context.get("trade_context"):
                bank_id = self._pressure_contact_bank("trade_yes_caution", context) if self._pressure_offer_is_cautious(context, "trade") else "trade_yes"
                line = self._say(bank_id, context, topic_id=topic_id, count=ask_count)
                return {"npc_lines": [line], "open_trade": True, "trade_property_id": context["trade_context"].get("property_id")}
            return {"npc_lines": [self._say("trade_no", context, topic_id=topic_id, count=ask_count)]}
        if topic_id == "street_appraise":
            return self._resolve_street_appraise_topic(context, topic_id=topic_id, ask_count=ask_count)
        if topic_id == "street_buy":
            return self._resolve_street_buy_topic(context, topic_id=topic_id, ask_count=ask_count)
        if topic_id == "street_buy_accept":
            offer = self._street_buy_offer_state(npc_eid)
            self._clear_street_buy_offer()
            if not offer:
                return {"npc_lines": ["No. We do not have a price on the table right now."]}
            return self._execute_street_buy_offer(npc_eid, context, offer)
        if topic_id == "street_buy_next":
            offer = self._street_buy_offer_state(npc_eid)
            if not offer:
                return {"npc_lines": ["No. We do not have another item on deck right now."]}
            has_next_offer = self._street_buy_offer_next_available(offer)
            self._remember_street_buy_skipped_offer(offer)
            self._clear_street_buy_offer()
            if not has_next_offer:
                return {"npc_lines": ["That is the rest of what I would move tonight."]}
            return self._resolve_street_buy_topic(context, topic_id="street_buy", ask_count=ask_count)
        if topic_id == "street_buy_decline":
            had_offer = self._street_buy_offer_state(npc_eid)
            has_next_offer = self._street_buy_offer_next_available(had_offer)
            self._remember_street_buy_skipped_offer(had_offer)
            self._clear_street_buy_offer()
            if had_offer:
                if has_next_offer:
                    return {"npc_lines": ["Fine. Keep it. If you want me to look over the rest, ask."]}
                return {"npc_lines": ["Fine. Keep it moving unless you want to make a different offer."]}
            return {"npc_lines": ["Then we do not have business right now."]}
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

    def _append_dialogue_response(self, context, topic_id, response, *, previous_topic_id="", player_line_override=""):
        state = self._dialog_ui_state()
        transcript = list(state.get("transcript", ()) or ())
        player_line = str(player_line_override or "").strip()
        ask_count = self._dialogue_topic_count(context.get("npc_eid"), topic_id)
        if not player_line:
            player_line = _dialogue_topic_player_line(
                topic_id,
                seed=getattr(self.sim, "seed", 0),
                npc_eid=context.get("npc_eid"),
                count=ask_count,
                context=context,
                previous_topic_id=previous_topic_id,
                total_asked=self._dialogue_total_topics_asked(context.get("npc_eid")),
            )
        transcript.append(
            self._dialogue_player_line(player_line)
        )
        social_outcome = str(response.get("social_outcome", "") or "").strip().lower()
        if social_outcome:
            narration = self._dialogue_social_reaction_line(
                context,
                str(response.get("social_reaction_topic_id", topic_id) or topic_id),
                ask_count=ask_count,
                outcome=social_outcome,
            )
            if narration:
                transcript.append(narration)
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

    def _start_dialogue_with_npc(self, npc_eid, *, prompt_lines=(), highlight_topic_ids=(), allow_distant=False):
        if npc_eid is None:
            return False
        self._remember_opportunity_npc_interaction(npc_eid)
        context = self._dialogue_context(npc_eid, allow_distant=allow_distant)
        if not context:
            return False
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
        self._set_dialogue_cooldown(npc_eid, 120)
        player_needs = self.sim.ecs.get(NPCNeeds).get(self.player_eid)
        if fresh and not context.get("guarded"):
            rapport = self._conversation_rapport()
            social_gain = min(2.4, 0.55 + (rapport * 1.1))
            if player_needs:
                player_needs.social = _clamp(player_needs.social + social_gain)
            if context.get("npc_needs"):
                context["npc_needs"].social = _clamp(context["npc_needs"].social + max(0.25, social_gain * 0.45))
        context = self._dialogue_context(npc_eid, bond=bond, allow_distant=allow_distant)
        if not context:
            return False
        if not context.get("human"):
            self._emit_simple_npc_interaction(context)
            return False
        self._remember_direct_human_meeting(context)
        self._open_dialogue(
            context,
            prompt_lines=prompt_lines,
            highlight_topic_ids=highlight_topic_ids,
        )
        self.sim.emit(Event(
            "npc_interacted",
            eid=self.player_eid,
            npc_eid=npc_eid,
            lines=(),
            guarded=bool(context.get("guarded")),
            dialog_modal=True,
            initiated_by_npc=bool(tuple(prompt_lines or ())),
        ))
        return True

    def on_npc_interact(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        self._start_dialogue_with_npc(
            event.data.get("npc_eid"),
            allow_distant=bool(event.data.get("allow_distant")),
        )

    def on_npc_dialogue_request(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        npc_eid = event.data.get("npc_eid")
        if npc_eid is None:
            return
        state = self._dialog_ui_state()
        if state.get("open"):
            return

        raw_prompt_lines = event.data.get("prompt_lines", ())
        if isinstance(raw_prompt_lines, str):
            prompt_lines = (raw_prompt_lines,)
        else:
            prompt_lines = tuple(raw_prompt_lines or ())

        raw_highlights = event.data.get("highlight_topic_ids", ())
        if isinstance(raw_highlights, str):
            highlight_topic_ids = (raw_highlights,)
        else:
            highlight_topic_ids = tuple(raw_highlights or ())

        self._start_dialogue_with_npc(
            npc_eid,
            prompt_lines=prompt_lines,
            highlight_topic_ids=highlight_topic_ids,
        )

    def on_npc_warn_property(self, event):
        if event.data.get("offender_eid") != self.player_eid:
            return
        npc_eid = event.data.get("npc_eid")
        identity = self.sim.ecs.get(CreatureIdentity).get(npc_eid) if npc_eid is not None else None
        if npc_eid is None or not is_human_identity(identity):
            return
        bond = self._bond_snapshot(npc_eid) or {}
        prop = self.sim.properties.get(str(event.data.get("property_id", "") or "").strip())
        property_id = str((prop or {}).get("id", "") or "").strip() if isinstance(prop, dict) else ""
        property_name = str((prop or {}).get("name", property_id or "the place")).strip() if isinstance(prop, dict) else "the place"
        standing = max(0.08, float(self._contact_standing(bond, 0.0) or 0.0) * 0.4)
        self._remember_player_relationship_episode(
            npc_eid,
            kind="warned_me_off",
            valence="negative",
            summary=f"They warned you away from {property_name}.",
            property_id=property_id or None,
            source_topic="warn_property",
            relation_kind=str(bond.get("kind", "") or "local").strip().lower() or "local",
            standing=standing,
            met_directly=False,
        )

    def _relationship_dialogue_request(self, context):
        if not isinstance(context, dict):
            return None
        if not bool(context.get("human")) or bool(context.get("door_answering")) or bool(context.get("peaceful_orders_only")):
            return None
        if bool(context.get("guarded")):
            return None
        pressure_tier = str(context.get("pressure_tier", "low") or "low").strip().lower() or "low"
        if pressure_tier == "high":
            return None
        tone = str(context.get("tone", "neutral") or "neutral").strip().lower() or "neutral"
        bond = context.get("bond") or self._bond_snapshot(context.get("npc_eid")) or {}
        trust = float(bond.get("trust", 0.0) or 0.0)
        closeness = float(bond.get("closeness", 0.0) or 0.0)
        standing = float(context.get("contact_standing", 0.0) or 0.0)
        anchor = self._relationship_anchor_episode_for_context(context) or {}
        anchor_kind = str(anchor.get("kind", "") or "").strip().lower()
        anchor_valence = str(anchor.get("valence", "neutral") or "neutral").strip().lower() or "neutral"

        if self._rapport_topic_available(context, "check_in") and anchor_valence == "negative" and tone in {"wary", "neutral"}:
            prompt = "We should keep last time in mind if we are talking again."
            return {"prompt_lines": (prompt,), "highlight_topic_ids": ("check_in",), "score": 0.62}
        if self._rapport_topic_available(context, "check_in") and (tone == "friendly" or trust >= 0.44 or closeness >= 0.4):
            prompt = "Good to see you again. We can pick up where we left it."
            if anchor_kind == "offered_vouch":
                prompt = "Good to see you again. If you want to pick that thread back up, ask."
            return {"prompt_lines": (prompt,), "highlight_topic_ids": ("check_in",), "score": 0.76 + (trust * 0.08) + (closeness * 0.05)}
        if context.get("social_leads") and standing >= 0.5:
            prompt = "If you still need a useful name around here, ask."
            return {"prompt_lines": (prompt,), "highlight_topic_ids": ("contacts",), "score": 0.58 + (standing * 0.06)}
        if context.get("run_objective_visible") or context.get("opportunity_summary"):
            prompt = "If you are still looking for a line, I might have one."
            return {"prompt_lines": (prompt,), "highlight_topic_ids": ("opportunities",), "score": 0.5 + (trust * 0.04)}
        return None

    def _tick_relationship_dialogue_requests(self):
        state = self._dialog_ui_state()
        if state.get("open") or self.player_eid is None:
            return
        player_pos = self.sim.ecs.get(Position).get(self.player_eid)
        if not player_pos:
            return
        positions = self.sim.ecs.get(Position)
        cooldowns = self._npc_dialogue_cooldown_map()
        best = None
        for npc_eid, ai in self.sim.ecs.get(AI).items():
            if npc_eid == self.player_eid or ai is None:
                continue
            if int(cooldowns.get(int(npc_eid), 0) or 0) > int(self.sim.tick):
                continue
            if self._recently_interacted(npc_eid):
                continue
            pos = positions.get(npc_eid)
            if not pos or int(pos.z) != int(player_pos.z):
                continue
            distance = _manhattan(pos.x, pos.y, player_pos.x, player_pos.y)
            if distance > 4:
                continue
            if str(getattr(ai, "state", "") or "").strip().lower() in THREAT_STATES:
                continue
            if getattr(ai, "target_eid", None) == self.player_eid:
                continue
            context = self._dialogue_context(npc_eid, allow_distant=True)
            if not context:
                continue
            request = self._relationship_dialogue_request(context)
            if not isinstance(request, dict):
                continue
            score = float(request.get("score", 0.0) or 0.0) - (distance * 0.05)
            if score <= 0.0:
                continue
            roll = random.Random(
                f"{self.sim.seed}:relationship-dialogue-request:{npc_eid}:{self.sim.tick // 30}:{distance}:{request.get('highlight_topic_ids', ())}"
            ).random()
            chance = max(0.0, min(0.74, score))
            if roll > chance:
                continue
            if best is None or score > best[0]:
                best = (score, int(npc_eid), request)
        if best is None:
            return
        _score, npc_eid, request = best
        self._set_dialogue_cooldown(npc_eid, 240)
        self.sim.emit(Event(
            "npc_dialogue_request",
            eid=self.player_eid,
            npc_eid=npc_eid,
            prompt_lines=tuple(request.get("prompt_lines", ()) or ()),
            highlight_topic_ids=tuple(request.get("highlight_topic_ids", ()) or ()),
        ))

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
        player_line_override = ""
        if isinstance(selected_row, dict) and str(selected_row.get("id", "")).strip().lower() == topic_id:
            player_line_override = str(selected_row.get("player_line") or selected_row.get("label") or "").strip()
        self._append_dialogue_response(
            context,
            topic_id,
            response,
            previous_topic_id=previous_topic_id,
            player_line_override=player_line_override,
        )
        refreshed = self._dialogue_context(npc_eid)
        if not refreshed:
            self._close_dialog()
            return
        state["subtitle"] = refreshed.get("subtitle", "")
        pending_street_buy_offer = bool(refreshed.get("street_buy_offer_pending"))
        highlight_topic_ids = ("street_buy_accept", "street_buy_next", "street_buy_decline") if pending_street_buy_offer else ()
        state["topics"] = self._prioritize_dialog_topics(
            self._available_dialog_topics(refreshed),
            highlight_topic_ids=highlight_topic_ids,
        )
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
        preferred_row = selected_row
        if topic_id in {"street_buy", "street_buy_next"} and pending_street_buy_offer:
            preferred_row = next(
                (
                    row
                    for row in list(state.get("topics", ()) or ())
                    if str(row.get("id", "")).strip().lower() == "street_buy_accept"
                ),
                preferred_row,
            )
        self._restore_dialog_selection(
            state.get("topics", ()),
            preferred_row=preferred_row,
            fallback_index=previous_index,
        )
        state["scroll"] = max(0, len(list(state.get("transcript", ()) or ())) - 1)
        if response.get("open_trade"):
            self._close_dialog()
            trade_property_id = str(response.get("trade_property_id", "") or "").strip()
            trade_prop = self.sim.properties.get(trade_property_id) if trade_property_id else None
            if isinstance(trade_prop, dict) and bool(_property_metadata(trade_prop).get("dialogue_trade_only")):
                self.sim.emit(Event("trade_panel_open_request", eid=self.player_eid, mode="buy", property_id=trade_property_id))
            elif isinstance(trade_prop, dict):
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
        self._tick_relationship_dialogue_requests()
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
