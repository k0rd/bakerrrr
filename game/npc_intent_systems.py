"""Extracted systems from ``game.systems``: NPCNeedsSystem, NPCWillSystem, NPCInvestigateSystem."""

import random
from engine.events import Event
from engine.systems import System
from engine.visibility import has_line_of_sight as _has_line_of_sight
from game.checks import (
    crime_read_summary as _crime_read_summary,
    crime_sensitivity as _crime_sensitivity,
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
    CriminalDriveState,
    MovementThrottle,
    NPCMemory,
    NPCNeeds,
    NPCOpportunityKnowledge,
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
from game.organizations import organization_profile
from game.npc_relationships import (
    maybe_progress_relationship_after_socialized as _maybe_progress_relationship_after_socialized,
    record_partner_combat_witnesses as _record_partner_combat_witnesses,
    should_block_solo_vehicle_for_partner as _should_block_solo_vehicle_for_partner,
)
from game.named_scars_runtime import maybe_record_named_scar_from_damage
from game.npc_self_protection_runtime import (
    active_self_protection_action,
    apply_self_protection_quirk,
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
from game.property_door_wait import DoorWaitSystem, _actor_in_live_combat, _door_knock_attempt
from game.quick_travel_ramps import local_interactions_suspended_for_actor
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
from game.system_support.altered_state_runtime import bonus_move_available, control_lapse_active, spend_bonus_move
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
from game.service_runtime import _clamp
from game.system_support.actor_runtime import (
    _apply_downed_actor_state,
    _detail_tick_allowed,
    _entity_is_downed,
)
from game.system_support.ai_intent_runtime import _sync_ai_intent
from game.system_support.actor_attention_runtime import (
    attention_scope_for_actor as _attention_scope_for_actor,
    clear_actor_attention as _clear_actor_attention,
    mark_actor_urgent as _mark_actor_urgent,
    note_attention_resolution as _note_attention_resolution,
    pop_due_actors as _pop_due_actors,
    refresh_actor_attention as _refresh_actor_attention,
    record_actor_social_warmth as _record_actor_social_warmth,
    schedule_actor_due as _schedule_actor_due,
)
from game.outfit_impression import apply_visible_outfit_social_offset
from game.criminal_justice_runtime import _noise_merits_attention
from game.dialogue_runtime import (
    _active_contractor_record,
    _contractor_order_target_from_record,
    _peek_npc_initiated_dialogue,
    _pop_npc_initiated_dialogue,
    _workplace_property,
)
from game.system_support.entity_naming import _entity_display_name
from game.system_support.interaction_ordering import (
    _direction_step,
    _interaction_target_order_key,
    _manhattan,
    _normalized_direction,
)
from game.system_support.opportunity_knowledge_runtime import (
    active_target as _active_opportunity_target,
    clear_active_target as _clear_opportunity_active_target,
    clear_will_rethink as _clear_will_rethink,
    invalidate_active_target_path as _invalidate_opportunity_active_target_path,
    next_active_target_step as _next_opportunity_active_target_step,
    remember_active_target as _remember_opportunity_active_target,
    remember_opportunity_lead as _remember_opportunity_lead,
    schedule_will_rethink as _schedule_will_rethink,
    will_rethink_due as _will_rethink_due,
)
from game.opportunities import (
    active_service_job_claim_for_actor as _active_service_job_claim_for_actor,
    advance_service_job_board_claims as _advance_service_job_board_claims,
    mark_service_job_claim_arrival as _mark_service_job_claim_arrival,
    npc_claim_service_job_from_board as _npc_claim_service_job_from_board,
    service_job_claim_target as _service_job_claim_target,
)
from game.vehicle_motion import (
    active_vehicle_property as _active_vehicle_property_for_state,
    clamp_vehicle_speed as _clamp_vehicle_speed,
    ensure_vehicle_motion_state as _ensure_vehicle_motion_state,
    local_route_accessible_at as _vehicle_route_accessible_at,
    set_vehicle_heading as _set_vehicle_heading,
    set_vehicle_speed as _set_vehicle_speed,
    sync_vehicle_property_position as _sync_vehicle_property_position,
    try_vehicle_step as _try_vehicle_step,
    vehicle_heading_label as _vehicle_heading_label,
    vehicle_heading_tuple as _vehicle_heading_tuple,
    vehicle_top_speed as _vehicle_top_speed,
)
from game.system_support.social_knowledge_runtime import hydrate_relationship_social_knowledge
from game.system_support.access_runtime import _attempt_locked_property_entry_with_sim
from game.system_support.criminal_drive_runtime import (
    active_plan_for_actor,
    attempt_criminal_affiliation,
    criminal_drive_state,
    criminal_affiliation_targets,
    find_registered_item_system,
    nearest_target_ground_item,
)
from game.system_support.npc_behavior_runtime import (
    BEHAVIOR_APPRAISE_STREET_GOODS,
    BEHAVIOR_AVOID_AUTHORITIES,
    BEHAVIOR_COLLECT_GROUND_CREDITS,
    BEHAVIOR_COMMIT_OPPORTUNISTIC_CRIME,
    BEHAVIOR_COMMIT_PLANNED_CRIME,
    BEHAVIOR_AVOID_THREAT,
    BEHAVIOR_BUY_DESIRED_DRUG,
    BEHAVIOR_BUY_PLAYER_GOODS,
    BEHAVIOR_BUY_PRACTICAL_GEAR,
    BEHAVIOR_BUY_PROVISIONS,
    BEHAVIOR_BUY_QUIRKY_ITEMS,
    BEHAVIOR_ENFORCE_JUSTICE,
    BEHAVIOR_FOLLOW_DUTY,
    BEHAVIOR_INITIATE_DIALOGUE,
    BEHAVIOR_PROTECT_ALLIES,
    BEHAVIOR_SCAVENGE_LOOSE_ITEMS,
    BEHAVIOR_SELL_SCAVENGED_ITEMS,
    BEHAVIOR_SEEK_CRIMINAL_AFFILIATION,
    BEHAVIOR_SEEK_SHELTER,
    BEHAVIOR_SEEK_SOCIAL_CONTACT,
    BEHAVIOR_SEEK_MEDICAL_AID,
    _actor_behavior_value,
    _behavior_live_street_heat,
    _behavior_preference,
    _collect_ground_items_at_actor,
    _effective_behavior_value,
    _find_authority_avoidance_target,
    _find_lodging_target,
    _find_medical_aid_target,
    _find_shopping_target,
    _find_safe_spot_target,
    _find_scavenged_sale_target,
    _find_ground_credit_target,
    _find_scavenge_ground_item_target,
    _inventory_scavenge_sale_rows,
    _inventory_contraband_heat,
    _npc_try_consume_nutrition,
    _pick_social_venue as _behavior_pick_social_venue,
    _receive_lodging_at_actor,
    _receive_medical_aid_at_actor,
    _receive_nutrition_at_actor,
    _receive_safe_spot_at_actor,
    _resolve_npc_shopping_at_actor,
    _resolve_street_buy_between_actors,
    _resolve_street_appraise_between_actors,
    _sell_scavenged_inventory_at_actor,
    _street_appraise_candidates_for_actor,
    _street_appraise_capabilities,
    _street_buy_candidate_rows_for_actor,
    _street_buy_interest_profile,
    _street_buy_terms,
)
from game.system_support.settlement_runtime import _home_property
from game.system_support.status_runtime import (
    SURVIVAL_CRITICAL_LEVEL,
    SURVIVAL_LOW_LEVEL,
    SURVIVAL_SEVERE_LEVEL,
    _ensure_survival_needs,
    _npc_status_metric_args,
    _survival_pressure_snapshot,
    _status_int_offset,
    _status_modifier_total,
    _status_multiplier,
    _status_tick_step,
)


def _crime_plan_event_fields(sim, actor_eid, plan_key):
    plan_key = str(plan_key or "").strip()
    if not plan_key:
        return {}
    plan = active_plan_for_actor(sim, actor_eid, current_tick=getattr(sim, "tick", 0))
    if not isinstance(plan, dict) or str(plan.get("plan_key", "") or "").strip() != plan_key:
        return {}
    return {
        "plan_method_key": str(plan.get("method_key", "") or "").strip() or None,
        "plan_method_label": str(plan.get("method_label", "") or "").strip() or None,
        "plan_stage": str(plan.get("stage", "") or "").strip().lower() or None,
    }


_FACADE_MODULE = None
_WILDLIFE_MODULE = None


def _facade():
    global _FACADE_MODULE
    if _FACADE_MODULE is None:
        from game import systems as facade

        _FACADE_MODULE = facade
    return _FACADE_MODULE


def _int_or_default(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _wildlife_module():
    global _WILDLIFE_MODULE
    if _WILDLIFE_MODULE is None:
        from game import systems_wildlife as wildlife

        _WILDLIFE_MODULE = wildlife
    return _WILDLIFE_MODULE


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

NOISE_INTERRUPT_PROTECTED_STATES = frozenset({
    "protecting",
    "seeking_safety",
    "chasing",
})

_WILL_COASTING_STATES = frozenset({
    "selling_scavenged",
    "seeking_medical_aid",
    "seeking_safe_spot",
    "seeking_shelter",
    "patrolling",
    "working",
    "lounging",
    "socializing",
    "shopping",
    "resting",
})

_WILL_COASTING_TICKS = {
    "selling_scavenged": 48,
    "seeking_medical_aid": 42,
    "seeking_safe_spot": 56,
    "seeking_shelter": 56,
    "patrolling": 120,
    "working": 120,
    "lounging": 150,
    "socializing": 96,
    "shopping": 84,
    "resting": 180,
}

_WILL_PLAYER_PROXIMITY_RADIUS = 4


def _routine_will_hold_ticks(state):
    return int(max(0, _WILL_COASTING_TICKS.get(str(state or "").strip().lower(), 0)))


def _actor_is_active_street_trade_contact(sim, eid):
    state = getattr(sim, "trade_ui", None)
    if not isinstance(state, dict) or not bool(state.get("open")):
        return False
    if str(state.get("source_kind", "") or "").strip().lower() != "street_vendor":
        return False
    try:
        return int(state.get("contact_eid")) == int(eid)
    except (TypeError, ValueError):
        return False


def _should_skip_live_will_update(sim, eid, ai, will, needs, pos, *, player_pos=None, suppression=None):
    if ai is None or will is None or needs is None or pos is None:
        return False
    state = str(getattr(ai, "state", "") or "").strip().lower()
    if str(getattr(ai, "role", "") or "").strip().lower() == "wildlife":
        return False
    if suppression is not None and bool(getattr(suppression, "surrendered", False)):
        return False
    if state not in _WILL_COASTING_STATES:
        return False
    if getattr(ai, "target", None) is None or getattr(ai, "target_eid", None) is not None:
        return False
    critical = getattr(needs, "critical", None)
    if critical:
        return False
    if float(getattr(needs, "energy", 100.0) or 100.0) <= 18.0:
        return False
    if float(getattr(needs, "safety", 100.0) or 100.0) <= 18.0:
        return False
    if player_pos is not None and int(getattr(player_pos, "z", 0) or 0) == int(getattr(pos, "z", 0) or 0):
        if (
            _manhattan(int(pos.x), int(pos.y), int(player_pos.x), int(player_pos.y)) <= _WILL_PLAYER_PROXIMITY_RADIUS
            and _has_line_of_sight(
                sim,
                int(pos.x),
                int(pos.y),
                int(pos.z),
                int(player_pos.x),
                int(player_pos.y),
                int(player_pos.z),
            )
        ):
            return False
    return not _will_rethink_due(sim, eid, current_tick=getattr(sim, "tick", 0))

def _emit_move_access_events(*args, **kwargs):
    return _facade()._emit_move_access_events(*args, **kwargs)

def _entity_status_move_speed_multiplier(*args, **kwargs):
    return _facade()._entity_status_move_speed_multiplier(*args, **kwargs)

def _fb_prop(*args, **kwargs):
    return _facade()._fb_prop(*args, **kwargs)

def _guard_grace_suppresses_memory_entry(*args, **kwargs):
    return _facade()._guard_grace_suppresses_memory_entry(*args, **kwargs)

def _known_threat_position_for_npc(*args, **kwargs):
    return _facade()._known_threat_position_for_npc(*args, **kwargs)

def _memory_visible(*args, **kwargs):
    return _facade()._memory_visible(*args, **kwargs)

def _npc_actor_impression(*args, **kwargs):
    return _facade()._npc_actor_impression(*args, **kwargs)

def _npc_combat_metrics(*args, **kwargs):
    return _facade()._npc_combat_metrics(*args, **kwargs)

def _path_next_step(*args, **kwargs):
    return _facade()._path_next_step(*args, **kwargs)

def _pick_npc_combat_position(*args, **kwargs):
    return _facade()._pick_npc_combat_position(*args, **kwargs)

def _pick_npc_retreat_target(*args, **kwargs):
    return _facade()._pick_npc_retreat_target(*args, **kwargs)

def _pick_property_roam_tile(*args, **kwargs):
    return _facade()._pick_property_roam_tile(*args, **kwargs)

def _pick_social_venue(*args, **kwargs):
    return _behavior_pick_social_venue(*args, **kwargs)

def _resolve_ai_target(*args, **kwargs):
    return _facade()._resolve_ai_target(*args, **kwargs)

def _sa(*args, **kwargs):
    return _facade()._sa(*args, **kwargs)

def _strongest_memory_entry(*args, **kwargs):
    return _facade()._strongest_memory_entry(*args, **kwargs)

def _sv_focus(*args, **kwargs):
    return _facade()._sv_focus(*args, **kwargs)

def _sync_npc_cover_against_threat(*args, **kwargs):
    return _facade()._sync_npc_cover_against_threat(*args, **kwargs)

def _weapon_context_for_entity(*args, **kwargs):
    return _facade()._weapon_context_for_entity(*args, **kwargs)

def _actors_use_wildlife_social(*args, **kwargs):
    return _wildlife_module()._actors_use_wildlife_social(*args, **kwargs)


def _animal_ecology_profile_for_actor(*args, **kwargs):
    return _wildlife_module()._animal_ecology_profile_for_actor(*args, **kwargs)


def _pick_wildlife_escape_target(*args, **kwargs):
    return _wildlife_module()._pick_wildlife_escape_target(*args, **kwargs)


def _pick_wildlife_patrol_target(*args, **kwargs):
    return _wildlife_module()._pick_wildlife_patrol_target(*args, **kwargs)


def _relocate_indoor_wildlife_outdoors(*args, **kwargs):
    return _wildlife_module()._relocate_indoor_wildlife_outdoors(*args, **kwargs)


def _sync_wildlife_bond_pair(*args, **kwargs):
    return _wildlife_module()._sync_wildlife_bond_pair(*args, **kwargs)


def _wildlife_ecology_intent(*args, **kwargs):
    return _wildlife_module()._wildlife_ecology_intent(*args, **kwargs)


def _wildlife_recent_damage_reaction(*args, **kwargs):
    return _wildlife_module()._wildlife_recent_damage_reaction(*args, **kwargs)


def _wildlife_damage_reaction_blocks_noise(*args, **kwargs):
    return _wildlife_module()._wildlife_damage_reaction_blocks_noise(*args, **kwargs)


def _wildlife_home_position(*args, **kwargs):
    return _wildlife_module()._wildlife_home_position(*args, **kwargs)


def _wildlife_is_active(*args, **kwargs):
    return _wildlife_module()._wildlife_is_active(*args, **kwargs)


def _wildlife_social_intent(*args, **kwargs):
    return _wildlife_module()._wildlife_social_intent(*args, **kwargs)


BEHAVIOR_TIP_HEAT = "behavior_tip_heat"
BEHAVIOR_TIP_MEDICAL = "behavior_tip_medical"
BEHAVIOR_TIP_SHELTER = "behavior_tip_shelter"
BEHAVIOR_TIP_SAFE_SPOT = "behavior_tip_safe_spot"
BEHAVIOR_TIP_STREET_BUY = "behavior_tip_street_buy"
BEHAVIOR_TIP_STREET_APPRAISE = "behavior_tip_street_appraise"
BEHAVIOR_TIP_HIDDEN_TRADE = "behavior_tip_hidden_trade"
BEHAVIOR_TIP_HIDDEN_CLINIC = "behavior_tip_hidden_clinic"
BEHAVIOR_TIP_MAX_AGE = 180
BEHAVIOR_TIP_RADIUS = 6
BEHAVIOR_TIP_COOLDOWN = 120
HIDDEN_CONTACT_REFERRAL_RADIUS = 12
HIDDEN_CONTACT_REFERRAL_MIN_SCORE = 0.86
BEHAVIOR_TIP_SHARE_TARGET_LIMITS = {
    BEHAVIOR_TIP_STREET_BUY: 2,
    BEHAVIOR_TIP_STREET_APPRAISE: 2,
}


def _recent_behavior_tip(memory, kind, *, now, max_age=BEHAVIOR_TIP_MAX_AGE):
    current_tick = int(now or 0)

    def _fresh(entry):
        try:
            age = max(0, current_tick - int(entry.get("tick", current_tick) or current_tick))
        except (TypeError, ValueError):
            age = max_age + 1
        return age <= int(max_age)

    return _strongest_memory_entry(memory, kind, predicate=_fresh)


def _behavior_tip_share_target_limit(tip_kind):
    tip_kind = str(tip_kind or "").strip().lower()
    try:
        limit = int(BEHAVIOR_TIP_SHARE_TARGET_LIMITS.get(tip_kind, 1) or 1)
    except (TypeError, ValueError):
        limit = 1
    return max(1, min(3, limit))


def _plan_explicit_behavior_tip_shares(sim, source_eid, pos, tip_kind, payload, strength, *, cooldowns=None, tick=0):
    tip_kind = str(tip_kind or "").strip().lower()
    payload = payload if isinstance(payload, dict) else {}
    if not pos or not tip_kind or not payload:
        return ()

    ais = sim.ecs.get(AI)
    positions = sim.ecs.get(Position)
    memories = sim.ecs.get(NPCMemory)
    socials = sim.ecs.get(NPCSocial)
    source_social = socials.get(source_eid)
    candidates = []
    for target_eid, target_ai in ais.items():
        if target_eid == source_eid or target_eid == getattr(sim, "player_eid", None):
            continue
        if str(getattr(target_ai, "role", "") or "").strip().lower() == "wildlife":
            continue
        target_pos = positions.get(target_eid)
        target_memory = memories.get(target_eid)
        if not target_pos or not target_memory or int(target_pos.z) != int(pos.z):
            continue
        distance = _manhattan(pos.x, pos.y, target_pos.x, target_pos.y)
        if distance <= 0 or distance > BEHAVIOR_TIP_RADIUS:
            continue
        interest = _behavior_tip_interest(sim, target_eid, tip_kind, payload=payload)
        if interest <= 0.0:
            continue
        existing = _recent_behavior_tip(target_memory, tip_kind, now=tick, max_age=BEHAVIOR_TIP_MAX_AGE)
        if existing is not None:
            existing_data = existing.get("data", {}) if isinstance(existing.get("data"), dict) else {}
            if (
                str(existing_data.get("property_id", "") or "").strip() == str(payload.get("property_id", "") or "").strip()
                and str(existing_data.get("buyer_eid", "") or "").strip() == str(payload.get("buyer_eid", "") or "").strip()
                and str(existing_data.get("appraiser_eid", "") or "").strip() == str(payload.get("appraiser_eid", "") or "").strip()
            ):
                if float(existing.get("strength", 0.0) or 0.0) >= float(strength) - 0.04:
                    continue
        anchor = str(
            payload.get("property_id")
            or payload.get("buyer_eid")
            or payload.get("appraiser_eid")
            or f"{int(payload.get('x', pos.x))}:{int(payload.get('y', pos.y))}:{int(payload.get('z', pos.z))}"
        )
        if isinstance(cooldowns, dict):
            last_tick = int(cooldowns.get((int(source_eid), int(target_eid), tip_kind, anchor), -10_000) or -10_000)
            if int(tick) - last_tick < BEHAVIOR_TIP_COOLDOWN:
                continue
        bond_bonus = 0.0
        if source_social is not None:
            bond = getattr(source_social, "bonds", {}).get(target_eid)
            if isinstance(bond, dict):
                bond_bonus = (float(bond.get("trust", 0.0) or 0.0) * 6.0) + (float(bond.get("closeness", 0.0) or 0.0) * 4.0)
        score = interest + bond_bonus + max(0.0, (BEHAVIOR_TIP_RADIUS + 1 - distance) * 3.2)
        candidates.append({
            "kind": tip_kind,
            "target_eid": int(target_eid),
            "strength": float(strength),
            "payload": dict(payload),
            "anchor": anchor,
            "distance": int(distance),
            "score": float(score),
        })
    if not candidates:
        return ()

    candidates.sort(
        key=lambda row: (
            -float(row.get("score", 0.0) or 0.0),
            -float(row.get("strength", 0.0) or 0.0),
            int(row.get("distance", 0) or 0),
            int(row.get("target_eid", 0) or 0),
        )
    )
    limit = _behavior_tip_share_target_limit(tip_kind)
    return tuple(
        {
            "kind": str(row.get("kind", "")).strip().lower(),
            "target_eid": int(row.get("target_eid", 0) or 0),
            "strength": float(row.get("strength", 0.0) or 0.0),
            "payload": dict(row.get("payload") or {}),
            "anchor": str(row.get("anchor", "")).strip(),
        }
        for row in candidates[:limit]
    )


def _hidden_contact_referral_rows(sim, source_eid, pos, *, current_prop=None, workplace_prop=None, home_prop=None, occupation=None):
    if source_eid is None or not pos:
        return ()

    career_text = str(getattr(occupation, "career", "") or "").strip().lower()
    ref_property_ids = set()
    ref_building_ids = set()
    for ref in (current_prop, workplace_prop, home_prop):
        if not isinstance(ref, dict):
            continue
        ref_id = str(ref.get("id", "") or "").strip()
        if ref_id:
            ref_property_ids.add(ref_id)
        ref_meta = _property_metadata(ref)
        ref_building_id = str(ref_meta.get("building_id", "") or ref_id).strip()
        if ref_building_id:
            ref_building_ids.add(ref_building_id)

    best_by_kind = {}
    for prop in tuple(sim.properties.values()):
        if not isinstance(prop, dict):
            continue
        metadata = _property_metadata(prop)
        hidden_kind = str(metadata.get("hidden_contact_kind", "") or "").strip().lower()
        if hidden_kind not in {"backroom_market", "backroom_clinic"}:
            continue
        focus = _property_focus_position(prop)
        if not focus:
            continue
        fx, fy, fz = focus
        if int(fz) != int(pos.z):
            continue

        property_id = str(prop.get("id", "") or "").strip()
        if not property_id:
            continue
        linked_property_id = str(metadata.get("linked_property_id", "") or "").strip()
        property_building_id = str(metadata.get("building_id", "") or property_id).strip()
        linked_building_id = str(metadata.get("linked_building_id", "") or "").strip()
        distance = _manhattan(pos.x, pos.y, int(fx), int(fy))
        local_link = bool(
            prop.get("owner_eid") == source_eid
            or property_id in ref_property_ids
            or (linked_property_id and linked_property_id in ref_property_ids)
            or (property_building_id and property_building_id in ref_building_ids)
            or (linked_building_id and linked_building_id in ref_building_ids)
        )
        if not local_link and distance > HIDDEN_CONTACT_REFERRAL_RADIUS:
            continue

        score = 0.0
        if prop.get("owner_eid") == source_eid:
            score += 1.38
        if property_id in ref_property_ids:
            score += 1.12
        if linked_property_id and linked_property_id in ref_property_ids:
            score += 0.96
        if property_building_id and property_building_id in ref_building_ids:
            score += 0.7
        if linked_building_id and linked_building_id in ref_building_ids:
            score += 0.62
        if local_link:
            score += max(0.0, 0.28 - (distance * 0.02))
        else:
            score += max(0.0, 0.18 - (distance * 0.015))
        if hidden_kind == "backroom_clinic" and any(
            token in career_text for token in ("doctor", "medic", "nurse", "orderly", "paramedic", "street doc", "triage")
        ):
            score += 0.42
        if hidden_kind == "backroom_market" and any(
            token in career_text for token in ("broker", "dealer", "fence", "pawnbroker", "shopkeeper", "vendor", "bartender", "fixer")
        ):
            score += 0.36
        if score < HIDDEN_CONTACT_REFERRAL_MIN_SCORE:
            continue

        tip_kind = BEHAVIOR_TIP_HIDDEN_CLINIC if hidden_kind == "backroom_clinic" else BEHAVIOR_TIP_HIDDEN_TRADE
        lead_kind = "service_medical" if hidden_kind == "backroom_clinic" else "service_trade"
        row = {
            "tip_kind": tip_kind,
            "hidden_contact_kind": hidden_kind,
            "lead_kind": lead_kind,
            "property_id": property_id,
            "property_name": str(prop.get("name", property_id)).strip() or property_id,
            "x": int(fx),
            "y": int(fy),
            "z": int(fz),
            "score": float(score),
            "strength": max(0.42, min(0.92, 0.24 + (score * 0.28))),
        }
        prior = best_by_kind.get(hidden_kind)
        if prior is None or float(row.get("score", 0.0) or 0.0) > float(prior.get("score", 0.0) or 0.0):
            best_by_kind[hidden_kind] = row
    rows = tuple(best_by_kind[kind] for kind in sorted(best_by_kind.keys()))
    return rows


def _plan_hidden_contact_referral_shares(sim, source_eid, pos, *, current_prop=None, workplace_prop=None, home_prop=None, occupation=None, cooldowns=None, tick=0):
    rows = _hidden_contact_referral_rows(
        sim,
        source_eid,
        pos,
        current_prop=current_prop,
        workplace_prop=workplace_prop,
        home_prop=home_prop,
        occupation=occupation,
    )
    if not rows:
        return ()
    planned = []
    for row in rows:
        payload = {
            "property_id": row.get("property_id"),
            "property_name": row.get("property_name"),
            "hidden_contact_kind": row.get("hidden_contact_kind"),
            "lead_kind": row.get("lead_kind"),
            "x": int(row.get("x", pos.x) or pos.x),
            "y": int(row.get("y", pos.y) or pos.y),
            "z": int(row.get("z", pos.z) or pos.z),
        }
        shares = _plan_explicit_behavior_tip_shares(
            sim,
            source_eid,
            pos,
            str(row.get("tip_kind", "")).strip().lower(),
            payload,
            float(row.get("strength", 0.0) or 0.0),
            cooldowns=cooldowns,
            tick=tick,
        )
        planned.extend(shares)
    return tuple(planned)


def _retreat_target_from_warning(sim, pos, warning_pos, *, max_stride=4):
    if not pos or not isinstance(warning_pos, (tuple, list)) or len(warning_pos) < 2:
        return None
    wx = int(warning_pos[0])
    wy = int(warning_pos[1])
    dx = int(pos.x) - wx
    dy = int(pos.y) - wy
    if dx == 0 and dy == 0:
        chooser = random.Random(
            f"{getattr(sim, 'seed', 0)}:heat-tip-retreat:{int(pos.x)}:{int(pos.y)}:{int(getattr(sim, 'tick', 0))}"
        )
        if chooser.random() < 0.5:
            dx = 1
        else:
            dy = 1
    step_x = 1 if dx >= 0 else -1
    step_y = 1 if dy >= 0 else -1
    for stride in range(int(max(1, max_stride)), 0, -1):
        nx = int(pos.x) + (step_x * stride)
        ny = int(pos.y) + (step_y * stride)
        if sim.tilemap.is_walkable(nx, ny, int(pos.z)):
            return (nx, ny, int(pos.z))
    return None


def _live_target_position(sim, target_eid, *, positions=None, vitalities=None, z=None):
    if sim is None or target_eid is None:
        return None
    if local_interactions_suspended_for_actor(sim, target_eid):
        return None
    positions = positions or sim.ecs.get(Position)
    vitalities = vitalities or sim.ecs.get(Vitality)
    target_pos = positions.get(target_eid)
    if target_pos is None:
        return None
    if z is not None and int(target_pos.z) != int(z):
        return None
    target_vitality = vitalities.get(target_eid)
    if target_vitality and bool(getattr(target_vitality, "downed", False)):
        return None
    return target_pos


def _npc_live_threat_context(
    sim,
    eid,
    pos,
    *,
    target_eid=None,
    memory=None,
    needs=None,
    traits=None,
    vitality=None,
    suppression=None,
    max_steps=5,
):
    if sim is None or pos is None:
        return None
    threat_focus = _known_threat_position_for_npc(
        sim,
        eid,
        pos,
        target_eid=target_eid,
        memory=memory,
        radius=12,
    )
    if threat_focus is None:
        return None
    _loadout, held_weapon, _instance = _weapon_context_for_entity(sim, eid)
    metrics = _npc_combat_metrics(
        needs=needs,
        traits=traits or NPCTraits(),
        vitality=vitality,
        suppression=suppression,
        weapon=held_weapon,
        **_npc_status_metric_args(sim, eid),
    )
    retreat_target = _pick_npc_retreat_target(
        sim,
        eid,
        pos,
        threat_focus,
        metrics=metrics,
        max_steps=max_steps,
    )
    return {
        "threat_focus": threat_focus,
        "metrics": metrics,
        "retreat_target": retreat_target,
    }


def _find_tipped_street_buyer_target(sim, actor_eid, pos, tip_data):
    if not pos or not isinstance(tip_data, dict):
        return None
    buyer_eid = tip_data.get("buyer_eid")
    if buyer_eid is None or int(buyer_eid) == int(actor_eid):
        return None

    positions = sim.ecs.get(Position)
    buyer_pos = positions.get(buyer_eid)
    if not buyer_pos or int(buyer_pos.z) != int(pos.z):
        return None

    occupation = sim.ecs.get(Occupation).get(buyer_eid)
    career = str(getattr(occupation, "career", "") or "").strip().lower()
    district_type = ""
    world = getattr(sim, "world", None)
    if world is not None:
        chunk = world.get_chunk(*sim.chunk_coords(buyer_pos.x, buyer_pos.y))
        district = chunk.get("district", {}) if isinstance(chunk, dict) else {}
        if not isinstance(district, dict):
            district = {}
        district_type = str(district.get("district_type", "") or "").strip().lower()

    rows = _street_buy_candidate_rows_for_actor(
        sim,
        buyer_eid,
        actor_eid,
        district_type=district_type,
        career=career,
    )
    if not rows:
        return None

    total_offer = sum(int(row.get("price", 0) or 0) for row in rows)
    distance = _manhattan(pos.x, pos.y, buyer_pos.x, buyer_pos.y)
    score = max(0.0, (total_offer * 0.34) + 12.0 - (distance * 1.7))
    desired_item_id = str((tip_data or {}).get("desired_item_id", "") or "").strip().lower()
    if desired_item_id and any(bool(row.get("desired")) for row in rows):
        score += 10.0
    return {
        "buyer_eid": int(buyer_eid),
        "target": (int(buyer_pos.x), int(buyer_pos.y), int(buyer_pos.z)),
        "distance": int(distance),
        "score": float(score),
        "desired_item_id": desired_item_id,
        "rows": tuple(rows),
    }


def _find_tipped_street_appraiser_target(sim, actor_eid, pos, tip_data):
    if not pos or not isinstance(tip_data, dict):
        return None
    appraiser_eid = tip_data.get("appraiser_eid")
    if appraiser_eid is None or int(appraiser_eid) == int(actor_eid):
        return None

    positions = sim.ecs.get(Position)
    appraiser_pos = positions.get(appraiser_eid)
    if not appraiser_pos or int(appraiser_pos.z) != int(pos.z):
        return None

    candidates = _street_appraise_candidates_for_actor(sim, appraiser_eid, actor_eid)
    identify_count = len(candidates.get("identify", ()) or ())
    appraise_count = len(candidates.get("appraise", ()) or ())
    if identify_count <= 0 and appraise_count <= 0:
        return None

    distance = _manhattan(pos.x, pos.y, appraiser_pos.x, appraiser_pos.y)
    score = max(0.0, 16.0 + (identify_count * 18.0) + (appraise_count * 12.0) - (distance * 1.45))
    return {
        "appraiser_eid": int(appraiser_eid),
        "target": (int(appraiser_pos.x), int(appraiser_pos.y), int(appraiser_pos.z)),
        "distance": int(distance),
        "score": float(score),
        "identify_count": int(identify_count),
        "appraise_count": int(appraise_count),
    }


def _find_tipped_safe_spot_target(sim, actor_eid, pos, tip_data):
    if not pos or not isinstance(tip_data, dict):
        return None
    property_id = str(tip_data.get("property_id", "") or "").strip()
    if not property_id:
        return None
    prop = sim.properties.get(property_id)
    focus = _property_focus_position(prop) if isinstance(prop, dict) else None
    if isinstance(focus, (tuple, list)) and len(focus) >= 3:
        _remember_opportunity_lead(
            sim,
            actor_eid,
            "safe_spot",
            {
                "property_id": property_id,
                "property_name": str((prop or {}).get("name", property_id)).strip() or property_id,
                "target": (int(focus[0]), int(focus[1]), int(focus[2])),
                "chunk": sim.chunk_coords(int(focus[0]), int(focus[1])) if hasattr(sim, "chunk_coords") else None,
                "confidence": 0.72,
                "service_id": "tip",
                "opportunity_tag": "safe_spot",
                "verification_required": True,
            },
            source_kind="behavior_tip",
            stale_after_ticks=180,
            expires_ticks=540,
        )
    target = _find_safe_spot_target(
        sim,
        actor_eid,
        pos,
        preferred_property_id=property_id,
        preferred_score_bonus=18.0,
    )
    if not target or str(target.get("property_id", "") or "").strip() != property_id:
        return None
    resolved = dict(target)
    safe_kind = str(tip_data.get("safe_kind", "") or "").strip().lower()
    service = str(tip_data.get("service", "") or "").strip().lower()
    if safe_kind:
        resolved["safe_kind"] = safe_kind
    if service:
        resolved["service"] = service
    return resolved


def _behavior_tip_interest(sim, target_eid, tip_kind, payload=None):
    needs = sim.ecs.get(NPCNeeds).get(target_eid)
    traits = sim.ecs.get(NPCTraits).get(target_eid) or NPCTraits()
    vitality = sim.ecs.get(Vitality).get(target_eid)

    if tip_kind == BEHAVIOR_TIP_MEDICAL:
        if vitality is None or bool(getattr(vitality, "downed", False)):
            return 0.0
        max_hp = max(1, int(getattr(vitality, "max_hp", 1) or 1))
        hp = max(0, int(getattr(vitality, "hp", max_hp) or max_hp))
        health_gap = max(0.0, 1.0 - (float(hp) / float(max_hp)))
        if health_gap <= 0.05:
            return 0.0
        medical_drive = _effective_behavior_value(
            sim,
            target_eid,
            BEHAVIOR_SEEK_MEDICAL_AID,
            traits=traits,
            needs=needs,
            vitality=vitality,
        )
        return float((health_gap * 80.0) + (medical_drive * 22.0))

    if tip_kind == BEHAVIOR_TIP_SHELTER:
        routine = sim.ecs.get(NPCRoutine).get(target_eid)
        home = getattr(routine, "home", None) if routine else None
        energy_gap = max(0.0, (100.0 - float(getattr(needs, "energy", 85.0) or 85.0)) / 100.0) if needs else 0.0
        safety_gap = max(0.0, (100.0 - float(getattr(needs, "safety", 85.0) or 85.0)) / 100.0) if needs else 0.0
        social_gap = max(0.0, (100.0 - float(getattr(needs, "social", 70.0) or 70.0)) / 100.0) if needs else 0.0
        night_bonus = 0.18 if (_world_hour(sim) >= 21 or _world_hour(sim) < 6) else 0.0
        if max(energy_gap, safety_gap, social_gap, night_bonus) <= 0.08 and home:
            return 0.0
        shelter_drive = _effective_behavior_value(
            sim,
            target_eid,
            BEHAVIOR_SEEK_SHELTER,
            traits=traits,
            needs=needs,
            vitality=vitality,
        )
        homeless_bonus = 0.28 if not home else 0.0
        return float((energy_gap * 46.0) + (safety_gap * 38.0) + (social_gap * 8.0) + (night_bonus * 22.0) + (shelter_drive * 18.0) + (homeless_bonus * 20.0))

    if tip_kind == BEHAVIOR_TIP_HEAT:
        avoid_drive = _effective_behavior_value(
            sim,
            target_eid,
            BEHAVIOR_AVOID_AUTHORITIES,
            traits=traits,
            needs=needs,
            justice=sim.ecs.get(JusticeProfile).get(target_eid),
        )
        live_heat = _behavior_live_street_heat(sim, target_eid)
        if live_heat < 0.08 and avoid_drive < 0.08:
            return 0.0
        return float((live_heat * 52.0) + (avoid_drive * 18.0))

    if tip_kind == BEHAVIOR_TIP_SAFE_SPOT:
        payload = payload if isinstance(payload, dict) else {}
        pos = sim.ecs.get(Position).get(target_eid)
        if pos is None:
            return 0.0
        target = _find_tipped_safe_spot_target(sim, target_eid, pos, payload)
        if not target:
            return 0.0
        return float(min(94.0, float(target.get("score", 0.0) or 0.0) + 12.0))

    if tip_kind == BEHAVIOR_TIP_STREET_BUY:
        payload = payload if isinstance(payload, dict) else {}
        buyer_eid = payload.get("buyer_eid")
        if buyer_eid is None or int(buyer_eid) == int(target_eid):
            return 0.0
        occupation = sim.ecs.get(Occupation).get(buyer_eid)
        career = str(getattr(occupation, "career", "") or "").strip().lower()
        district_type = ""
        buyer_pos = sim.ecs.get(Position).get(buyer_eid)
        world = getattr(sim, "world", None)
        if buyer_pos is not None and world is not None:
            chunk = world.get_chunk(*sim.chunk_coords(buyer_pos.x, buyer_pos.y))
            district = chunk.get("district", {}) if isinstance(chunk, dict) else {}
            if not isinstance(district, dict):
                district = {}
            district_type = str(district.get("district_type", "") or "").strip().lower()
        rows = _street_buy_candidate_rows_for_actor(
            sim,
            buyer_eid,
            target_eid,
            district_type=district_type,
            career=career,
        )
        if not rows:
            return 0.0
        total_offer = sum(int(row.get("price", 0) or 0) for row in rows)
        desired_bonus = 10.0 if any(bool(row.get("desired")) for row in rows) else 0.0
        return float(min(96.0, (total_offer * 0.58) + (len(rows) * 6.0) + desired_bonus))

    if tip_kind == BEHAVIOR_TIP_STREET_APPRAISE:
        payload = payload if isinstance(payload, dict) else {}
        appraiser_eid = payload.get("appraiser_eid")
        if appraiser_eid is None or int(appraiser_eid) == int(target_eid):
            return 0.0
        candidates = _street_appraise_candidates_for_actor(sim, appraiser_eid, target_eid)
        identify_count = len(candidates.get("identify", ()) or ())
        appraise_count = len(candidates.get("appraise", ()) or ())
        if identify_count <= 0 and appraise_count <= 0:
            return 0.0
        return float(min(92.0, (identify_count * 22.0) + (appraise_count * 16.0) + 10.0))

    if tip_kind == BEHAVIOR_TIP_HIDDEN_CLINIC:
        payload = payload if isinstance(payload, dict) else {}
        property_id = str(payload.get("property_id", "") or "").strip()
        if not property_id:
            return 0.0
        prop = sim.properties.get(property_id)
        metadata = _property_metadata(prop)
        if str(metadata.get("hidden_contact_kind", "") or "").strip().lower() != "backroom_clinic":
            return 0.0
        pos = sim.ecs.get(Position).get(target_eid)
        if pos is None:
            return 0.0
        target = _property_focus_position(prop)
        if not target or int(target[2]) != int(pos.z):
            return 0.0
        if vitality is None or bool(getattr(vitality, "downed", False)):
            return 0.0
        max_hp = max(1, int(getattr(vitality, "max_hp", 1) or 1))
        hp = max(0, int(getattr(vitality, "hp", max_hp) or max_hp))
        health_gap = max(0.0, 1.0 - (float(hp) / float(max_hp)))
        if health_gap <= 0.08:
            return 0.0
        medical_drive = _effective_behavior_value(
            sim,
            target_eid,
            BEHAVIOR_SEEK_MEDICAL_AID,
            traits=traits,
            needs=needs,
            vitality=vitality,
        )
        distance = _manhattan(int(pos.x), int(pos.y), int(target[0]), int(target[1]))
        return float(min(94.0, (health_gap * 82.0) + (medical_drive * 18.0) + max(0.0, 12.0 - distance)))

    if tip_kind == BEHAVIOR_TIP_HIDDEN_TRADE:
        payload = payload if isinstance(payload, dict) else {}
        property_id = str(payload.get("property_id", "") or "").strip()
        if not property_id:
            return 0.0
        prop = sim.properties.get(property_id)
        metadata = _property_metadata(prop)
        if str(metadata.get("hidden_contact_kind", "") or "").strip().lower() != "backroom_market":
            return 0.0
        pos = sim.ecs.get(Position).get(target_eid)
        if pos is None:
            return 0.0
        target = _property_focus_position(prop)
        if not target or int(target[2]) != int(pos.z):
            return 0.0
        sale_rows = _inventory_scavenge_sale_rows(sim, target_eid)
        if not sale_rows:
            return 0.0
        total_value = sum(float(row.get("value", 0.0) or 0.0) for row in sale_rows)
        if total_value <= 0.0:
            return 0.0
        sell_drive = _effective_behavior_value(
            sim,
            target_eid,
            BEHAVIOR_SELL_SCAVENGED_ITEMS,
            traits=traits,
            needs=needs,
        )
        distance = _manhattan(int(pos.x), int(pos.y), int(target[0]), int(target[1]))
        contraband_bonus = _inventory_contraband_heat(sim, target_eid) * 18.0
        return float(min(95.0, (total_value * 0.42) + (len(sale_rows) * 5.0) + contraband_bonus + (sell_drive * 12.0) + max(0.0, 10.0 - distance)))

    return 0.0


def _plan_behavior_tip_shares(sim, source_eid, pos, intent, *, medical_target=None, shelter_target=None, avoidance_target=None, safe_spot_share=None, street_buy_share=None, street_appraise_share=None, cooldowns=None, tick=0):
    if not pos:
        return ()
    intent = str(intent or "").strip().lower()
    if intent == "seeking_medical_aid" and isinstance(medical_target, dict):
        tip_kind = BEHAVIOR_TIP_MEDICAL
        payload = {
            "property_id": medical_target.get("property_id"),
            "property_name": medical_target.get("property_name"),
            "x": int(medical_target["target"][0]),
            "y": int(medical_target["target"][1]),
            "z": int(medical_target["target"][2]),
        }
        strength = max(0.22, min(0.92, float(medical_target.get("score", 0.0) or 0.0) / 100.0))
    elif intent == "seeking_shelter" and isinstance(shelter_target, dict):
        tip_kind = BEHAVIOR_TIP_SHELTER
        payload = {
            "property_id": shelter_target.get("property_id"),
            "property_name": shelter_target.get("property_name"),
            "service": shelter_target.get("service"),
            "x": int(shelter_target["target"][0]),
            "y": int(shelter_target["target"][1]),
            "z": int(shelter_target["target"][2]),
        }
        strength = max(0.2, min(0.9, float(shelter_target.get("score", 0.0) or 0.0) / 100.0))
    elif intent == "evading_authority" and isinstance(avoidance_target, dict):
        authority_pos = avoidance_target.get("authority_pos") or (pos.x, pos.y, pos.z)
        tip_kind = BEHAVIOR_TIP_HEAT
        payload = {
            "authority_eid": avoidance_target.get("authority_eid"),
            "x": int(authority_pos[0]),
            "y": int(authority_pos[1]),
            "z": int(authority_pos[2]) if len(authority_pos) >= 3 else int(pos.z),
        }
        strength = max(0.24, min(0.94, float(avoidance_target.get("score", 0.0) or 0.0) / 100.0))
    elif isinstance(safe_spot_share, dict) and intent not in {"protecting", "seeking_safety", "chasing", "warning", "helping_victim", "reporting_incident", "ejecting_target", "leaving_property"}:
        tip_kind = BEHAVIOR_TIP_SAFE_SPOT
        payload = {
            "property_id": safe_spot_share.get("property_id"),
            "property_name": safe_spot_share.get("property_name"),
            "safe_kind": safe_spot_share.get("safe_kind"),
            "service": safe_spot_share.get("service"),
            "x": int(safe_spot_share["target"][0]),
            "y": int(safe_spot_share["target"][1]),
            "z": int(safe_spot_share["target"][2]),
        }
        strength = max(0.22, min(0.9, float(safe_spot_share.get("score", 0.0) or 0.0) / 100.0))
    elif isinstance(street_buy_share, dict) and intent not in {"protecting", "seeking_safety", "chasing", "warning", "helping_victim", "reporting_incident", "ejecting_target", "leaving_property"}:
        desired_item_id = str(street_buy_share.get("desired_item_id", "") or "").strip().lower()
        tip_kind = BEHAVIOR_TIP_STREET_BUY
        payload = {
            "buyer_eid": int(source_eid),
            "desired_item_id": desired_item_id,
            "x": int(pos.x),
            "y": int(pos.y),
            "z": int(pos.z),
        }
        strength = max(
            0.22,
            min(
                0.88,
                0.18
                + (float(street_buy_share.get("buy_desired_drug", 0.0) or 0.0) * 0.5)
                + (float(street_buy_share.get("buy_player_goods", 0.0) or 0.0) * 0.32),
            ),
        )
    elif isinstance(street_appraise_share, dict) and intent not in {"protecting", "seeking_safety", "chasing", "warning", "helping_victim", "reporting_incident", "ejecting_target", "leaving_property"}:
        tip_kind = BEHAVIOR_TIP_STREET_APPRAISE
        payload = {
            "appraiser_eid": int(source_eid),
            "x": int(pos.x),
            "y": int(pos.y),
            "z": int(pos.z),
        }
        strength = max(
            0.2,
            min(
                0.86,
                0.16
                + (float(street_appraise_share.get("identify_strength", 0.0) or 0.0) * 0.42)
                + (float(street_appraise_share.get("appraise_strength", 0.0) or 0.0) * 0.34),
            ),
        )
    else:
        return ()

    return _plan_explicit_behavior_tip_shares(
        sim,
        source_eid,
        pos,
        tip_kind,
        payload,
        strength,
        cooldowns=cooldowns,
        tick=tick,
    )


def _plan_behavior_tip_share(sim, source_eid, pos, intent, *, medical_target=None, shelter_target=None, avoidance_target=None, safe_spot_share=None, street_buy_share=None, street_appraise_share=None, cooldowns=None, tick=0):
    shares = _plan_behavior_tip_shares(
        sim,
        source_eid,
        pos,
        intent,
        medical_target=medical_target,
        shelter_target=shelter_target,
        avoidance_target=avoidance_target,
        safe_spot_share=safe_spot_share,
        street_buy_share=street_buy_share,
        street_appraise_share=street_appraise_share,
        cooldowns=cooldowns,
        tick=tick,
    )
    return shares[0] if shares else None


def _apply_behavior_tip_shares(sim, pending, *, cooldowns=None, tick=0):
    if not pending:
        return 0
    memories = sim.ecs.get(NPCMemory)
    applied = 0
    current_tick = int(tick or 0)
    for share in pending:
        if not isinstance(share, dict):
            continue
        target_eid = share.get("target_eid")
        target_memory = memories.get(target_eid)
        if target_memory is None:
            continue
        payload = dict(share.get("payload") or {})
        payload["source_eid"] = int(share.get("source_eid"))
        payload["via"] = "peer_tip"
        target_memory.remember(
            tick=int(tick or 0),
            kind=str(share.get("kind", "")).strip().lower(),
            strength=float(share.get("strength", 0.0) or 0.0),
            **payload,
        )
        if isinstance(cooldowns, dict):
            cooldowns[(
                int(share.get("source_eid")),
                int(target_eid),
                str(share.get("kind", "")).strip().lower(),
                str(share.get("anchor", "")).strip(),
            )] = current_tick
        _schedule_will_rethink(
            sim,
            int(target_eid),
            current_tick=current_tick,
            delay_ticks=0,
        )
        sim.emit(Event(
            "npc_behavior_tip_shared",
            source_eid=int(share.get("source_eid")),
            target_eid=int(target_eid),
            tip_kind=str(share.get("kind", "")).strip().lower(),
            strength=round(float(share.get("strength", 0.0) or 0.0), 3),
            property_id=payload.get("property_id"),
            property_name=payload.get("property_name"),
            x=payload.get("x"),
            y=payload.get("y"),
            z=payload.get("z"),
        ))
        applied += 1
    return applied

class NPCNeedsSystem(System):

    CRITICAL_LEVEL = 30.0
    STABLE_LEVEL = 45.0
    SURVIVAL_STABLE_LEVEL = SURVIVAL_LOW_LEVEL
    DEPRIVATION_DAMAGE_INTERVAL = 18
    HUNGER_DRAIN_PER_TICK = 0.006
    THIRST_DRAIN_PER_TICK = 0.011
    ACTIVE_HUNGER_DRAIN_BONUS = 0.002
    ACTIVE_THIRST_DRAIN_BONUS = 0.004
    RESTING_SURVIVAL_DRAIN_MULT = 0.75

    def _sync_threshold(self, eid, needs, key, value, *, critical_level=None, stable_level=None):
        critical_level = self.CRITICAL_LEVEL if critical_level is None else float(critical_level)
        stable_level = self.STABLE_LEVEL if stable_level is None else float(stable_level)
        if value < critical_level and key not in needs.critical:
            needs.critical.add(key)
            self.sim.emit(Event("npc_need_critical", npc_eid=eid, need=key, value=value))
            if key in {"hunger", "thirst"}:
                _mark_actor_urgent(self.sim, eid, family="will", reason=f"need:{key}", ttl_ticks=20)
                _schedule_actor_due(self.sim, eid, "will", delay_ticks=0, reason=f"need:{key}")
                _schedule_will_rethink(self.sim, eid, current_tick=getattr(self.sim, "tick", 0), delay_ticks=0)

        if value > stable_level and key in needs.critical:
            needs.critical.remove(key)
            self.sim.emit(Event("npc_need_stabilized", npc_eid=eid, need=key, value=value))

    def _active_deprivation_damage_allowed(self, eid, pos):
        if eid == getattr(self.sim, "player_eid", None):
            return True
        if pos is None:
            return False
        try:
            return str(self.sim.detail_for_xy(pos.x, pos.y)).strip().lower() == "active"
        except Exception:
            return False

    def _deprivation_damage_ready(self, eid):
        current_tick = int(getattr(self.sim, "tick", 0) or 0)
        cooldowns = getattr(self.sim, "deprivation_damage_cooldowns", None)
        if not isinstance(cooldowns, dict):
            cooldowns = {}
            setattr(self.sim, "deprivation_damage_cooldowns", cooldowns)
        try:
            next_tick = int(cooldowns.get(int(eid), 0) or 0)
        except (TypeError, ValueError):
            next_tick = 0
        if current_tick < next_tick:
            return False
        cooldowns[int(eid)] = current_tick + int(self.DEPRIVATION_DAMAGE_INTERVAL)
        return True

    def _deprivation_damage_amount(self, snapshot):
        hunger = snapshot.get("hunger", 100.0)
        thirst = snapshot.get("thirst", 100.0)
        hunger = 100.0 if hunger is None else float(hunger)
        thirst = 100.0 if thirst is None else float(thirst)
        worst = min(hunger, thirst)
        severity = max(0.0, min(1.0, (SURVIVAL_SEVERE_LEVEL - worst) / max(1.0, SURVIVAL_SEVERE_LEVEL)))
        damage = 1 + int(round(severity * 2.0))
        if hunger < SURVIVAL_SEVERE_LEVEL and thirst < SURVIVAL_SEVERE_LEVEL:
            damage += 1
        return int(max(1, min(4, damage)))

    def _apply_deprivation_damage(self, eid, pos, vitality, snapshot):
        if vitality is None or bool(getattr(vitality, "downed", False)):
            return False
        if not self._active_deprivation_damage_allowed(eid, pos):
            return False
        if not self._deprivation_damage_ready(eid):
            return False

        reason = str(snapshot.get("reason", "") or "deprivation").strip().lower() or "deprivation"
        damage = self._deprivation_damage_amount(snapshot)
        max_hp = max(1, int(getattr(vitality, "max_hp", 1) or 1))
        before_hp = max(0, int(getattr(vitality, "hp", max_hp) or max_hp))
        after_hp = max(0, before_hp - damage)
        vitality.hp = int(after_hp)
        x = int(getattr(pos, "x", 0) or 0) if pos is not None else 0
        y = int(getattr(pos, "y", 0) or 0) if pos is not None else 0
        z = int(getattr(pos, "z", 0) or 0) if pos is not None else 0

        self.sim.emit(Event(
            "entity_damaged",
            target_eid=eid,
            source_eid=None,
            weapon_id=reason,
            damage_kind="deprivation",
            reason=reason,
            raw_damage=damage,
            damage=damage,
            cover_absorb=0.0,
            armor_absorb=0.0,
            hp=int(vitality.hp),
            max_hp=max_hp,
            x=x,
            y=y,
            z=z,
        ))
        self.sim.emit(Event(
            "actor_deprivation_damage",
            target_eid=eid,
            reason=reason,
            damage=damage,
            hp=int(vitality.hp),
            max_hp=max_hp,
            hunger=round(float(snapshot.get("hunger", 0.0) or 0.0), 2),
            thirst=round(float(snapshot.get("thirst", 0.0) or 0.0), 2),
            x=x,
            y=y,
            z=z,
        ))
        if vitality.hp > 0:
            return True

        vitality.downed_count += 1
        setattr(vitality, "last_attacker_eid", None)
        setattr(vitality, "death_reason", reason)
        vitality.downed = True
        vitality.downed_tick = int(getattr(self.sim, "tick", 0) or 0)

        if eid == getattr(self.sim, "player_eid", None):
            self.sim.emit(Event(
                "player_killed",
                target_eid=eid,
                source_eid=None,
                source_name="",
                weapon_id=reason,
                reason=reason,
                damage_kind="deprivation",
                x=x,
                y=y,
                z=z,
            ))
            return True

        _apply_downed_actor_state(self.sim, eid, tick=getattr(self.sim, "tick", 0))
        collider = self.sim.ecs.get(Collider).get(eid)
        if collider:
            collider.blocks = False
        render = self.sim.ecs.get(Render).get(eid)
        if render:
            render.glyph = "x"
        self.sim.emit(Event(
            "npc_downed",
            target_eid=eid,
            source_eid=None,
            reason=reason,
            damage_kind="deprivation",
            x=x,
            y=y,
            z=z,
        ))
        return True

    def update(self):
        needs_map = self.sim.ecs.get(NPCNeeds)
        ais = self.sim.ecs.get(AI)
        positions = self.sim.ecs.get(Position)
        vitalities = self.sim.ecs.get(Vitality)

        for eid, needs in needs_map.items():
            pos = positions.get(eid)
            if pos and not _detail_tick_allowed(self.sim, pos, eid, coarse_divisor=3):
                continue
            _ensure_survival_needs(needs)
            _npc_try_consume_nutrition(self.sim, eid, needs)

            ai = ais.get(eid)
            state = ai.state if ai else "idle"

            needs.energy = _clamp(needs.energy - 0.07)
            needs.social = _clamp(needs.social - 0.05)
            hunger_drain = self.HUNGER_DRAIN_PER_TICK
            thirst_drain = self.THIRST_DRAIN_PER_TICK
            if state in {
                "working",
                "investigating",
                "protecting",
                "seeking_safety",
                "chasing",
                "casing_target",
                "committing_property_crime",
            }:
                hunger_drain += self.ACTIVE_HUNGER_DRAIN_BONUS
                thirst_drain += self.ACTIVE_THIRST_DRAIN_BONUS
            if state in {"resting", "socializing", "lounging"}:
                hunger_drain *= self.RESTING_SURVIVAL_DRAIN_MULT
                thirst_drain *= self.RESTING_SURVIVAL_DRAIN_MULT
            current_hunger = getattr(needs, "hunger", 86.0)
            current_thirst = getattr(needs, "thirst", 90.0)
            current_hunger = 86.0 if current_hunger is None else float(current_hunger)
            current_thirst = 90.0 if current_thirst is None else float(current_thirst)
            needs.hunger = _clamp(current_hunger - hunger_drain)
            needs.thirst = _clamp(current_thirst - thirst_drain)

            if state in {"investigating", "protecting", "seeking_safety"}:
                needs.safety = _clamp(needs.safety - 0.08)
                needs.energy = _clamp(needs.energy - 0.03)
            else:
                needs.safety = _clamp(needs.safety + 0.03)

            if state in {"seeking_social", "seeking_companionship"}:
                needs.social = _clamp(needs.social + 0.25)

            if state == "resting":
                needs.energy = _clamp(needs.energy + 0.35)

            pressure = _survival_pressure_snapshot(needs)
            hunger_pressure = float(pressure.get("hunger_pressure", 0.0) or 0.0)
            thirst_pressure = float(pressure.get("thirst_pressure", 0.0) or 0.0)
            if hunger_pressure or thirst_pressure:
                needs.energy = _clamp(needs.energy - ((hunger_pressure * 0.026) + (thirst_pressure * 0.04)))
                if float(getattr(needs, "hunger", 100.0) if getattr(needs, "hunger", None) is not None else 100.0) < SURVIVAL_CRITICAL_LEVEL:
                    needs.social = _clamp(needs.social - 0.018)
                    needs.safety = _clamp(needs.safety - 0.012)
                if float(getattr(needs, "thirst", 100.0) if getattr(needs, "thirst", None) is not None else 100.0) < SURVIVAL_CRITICAL_LEVEL:
                    needs.safety = _clamp(needs.safety - 0.028)
                if pressure.get("severe"):
                    self._apply_deprivation_damage(eid, pos, vitalities.get(eid), pressure)

            self._sync_threshold(eid, needs, "energy", needs.energy)
            self._sync_threshold(eid, needs, "safety", needs.safety)
            self._sync_threshold(eid, needs, "social", needs.social)
            self._sync_threshold(
                eid,
                needs,
                "hunger",
                needs.hunger,
                critical_level=SURVIVAL_CRITICAL_LEVEL,
                stable_level=self.SURVIVAL_STABLE_LEVEL,
            )
            self._sync_threshold(
                eid,
                needs,
                "thirst",
                needs.thirst,
                critical_level=SURVIVAL_CRITICAL_LEVEL,
                stable_level=self.SURVIVAL_STABLE_LEVEL,
            )

class NPCWillSystem(System):

    LIVE_TIMESKIP_URGENT_STATES = {
        "investigating",
        "protecting",
        "following",
        "holding",
        "helping_victim",
        "reporting_incident",
        "warning",
        "ejecting_target",
        "leaving_property",
        "chasing",
        "evading_authority",
        "seeking_safety",
        "seeking_medical_aid",
        "seeking_safe_spot",
        "seeking_shelter",
        "casing_target",
        "committing_property_crime",
        "rendezvousing_crew",
        "seeking_criminal_affiliation",
        "soliciting_player",
    }

    def __init__(self, sim):
        super().__init__(sim)
        self.sim.events.subscribe("entity_damaged", self.on_entity_damaged)
        self.sim.events.subscribe("npc_intent_changed", self.on_npc_intent_changed)

    def _live_timeskip_active(self):
        state = getattr(self.sim, "live_timeskip", None)
        return isinstance(state, dict) and bool(state.get("active"))

    def on_npc_intent_changed(self, event):
        data = getattr(event, "data", {}) or {}
        try:
            npc_eid = int(data.get("npc_eid"))
        except (TypeError, ValueError):
            return
        intent = str(data.get("intent", "") or "").strip().lower()
        if intent in self.LIVE_TIMESKIP_URGENT_STATES:
            _mark_actor_urgent(self.sim, npc_eid, family="will", reason=f"intent:{intent}", ttl_ticks=12)
            _schedule_actor_due(self.sim, npc_eid, "will", delay_ticks=0, reason=f"intent:{intent}")

    def on_entity_damaged(self, event):
        source_eid = event.data.get("source_eid")
        target_eid = event.data.get("target_eid")
        try:
            source_eid = int(source_eid)
            target_eid = int(target_eid)
            damage = int(event.data.get("damage", 0) or 0)
        except (TypeError, ValueError):
            return
        if damage <= 0 or source_eid == target_eid:
            return
        _record_partner_combat_witnesses(
            self.sim,
            source_eid,
            target_eid,
            damage=damage,
            x=event.data.get("x"),
            y=event.data.get("y"),
            z=event.data.get("z"),
        )
        if target_eid == getattr(self.sim, "player_eid", None):
            return

        ais = self.sim.ecs.get(AI)
        ai = ais.get(target_eid)
        if ai is None:
            return
        if str(getattr(ai, "role", "") or "").strip().lower() == "wildlife":
            return

        positions = self.sim.ecs.get(Position)
        target_pos = positions.get(target_eid)
        source_pos = positions.get(source_eid)
        if target_pos is None or source_pos is None or int(target_pos.z) != int(source_pos.z):
            return
        vitality = self.sim.ecs.get(Vitality).get(target_eid)
        if vitality is not None and bool(getattr(vitality, "downed", False)):
            return
        maybe_record_named_scar_from_damage(self.sim, target_eid, event)

        needs = self.sim.ecs.get(NPCNeeds).get(target_eid)
        if needs is not None:
            needs.safety = _clamp(float(getattr(needs, "safety", 100.0) or 100.0) - min(14.0, 4.0 + float(damage)))

        memory = self.sim.ecs.get(NPCMemory).get(target_eid)
        impact = min(1.0, 0.36 + (float(damage) / 18.0))
        if memory is not None:
            memory.remember(
                tick=int(getattr(self.sim, "tick", 0)),
                kind="threat",
                strength=impact,
                source_eid=source_eid,
                target_eid=target_eid,
                x=int(source_pos.x),
                y=int(source_pos.y),
                z=int(source_pos.z),
                damage=damage,
                damage_kind=str(event.data.get("damage_kind", "harm") or "harm"),
                via="direct_damage",
            )
            memory.remember(
                tick=int(getattr(self.sim, "tick", 0)),
                kind="actor_reputation",
                strength=impact,
                actor_eid=source_eid,
                approval=-0.82,
                target_eid=target_eid,
                damage=damage,
                damage_kind=str(event.data.get("damage_kind", "harm") or "harm"),
                via="direct_damage",
            )

        will = self.sim.ecs.get(NPCWill).get(target_eid)
        if will is None:
            will = NPCWill()
            self.sim.ecs.add(target_eid, will)

        traits = self.sim.ecs.get(NPCTraits).get(target_eid) or NPCTraits()
        suppression = self.sim.ecs.get(SuppressionState).get(target_eid)
        threat_context = _npc_live_threat_context(
            self.sim,
            target_eid,
            target_pos,
            target_eid=source_eid,
            memory=memory,
            needs=needs,
            traits=traits,
            vitality=vitality,
            suppression=suppression,
            max_steps=5,
        )
        metrics = (threat_context or {}).get("metrics", {}) if isinstance(threat_context, dict) else {}
        retreat_target = (threat_context or {}).get("retreat_target") if isinstance(threat_context, dict) else None
        retreat_bias = float((metrics or {}).get("retreat_bias", 0.0) or 0.0)
        assault_bias = float((metrics or {}).get("assault_bias", 0.0) or 0.0)
        source_target = (int(source_pos.x), int(source_pos.y), int(source_pos.z))

        if retreat_target and retreat_bias >= max(0.42, assault_bias + 0.08):
            safety_score = min(96.0, 68.0 + (retreat_bias * 26.0) + min(12.0, float(damage)))
            self._set_intent(
                target_eid,
                ai,
                will,
                "seeking_safety",
                safety_score,
                target=retreat_target,
                target_eid=source_eid,
            )
            quirk_row = apply_self_protection_quirk(
                self.sim,
                target_eid,
                ai=ai,
                pos=target_pos,
                reason="seeking_safety",
                target=retreat_target,
                threat_eid=source_eid,
                threat_pos=source_target,
                damage=damage,
            )
            action = quirk_row.get("action") if isinstance(quirk_row, dict) else {}
            quirk = str(quirk_row.get("quirk", "") or "").strip().lower() if isinstance(quirk_row, dict) else ""
            action_target = action.get("target") if isinstance(action, dict) else None
            if quirk == "stand_ground" and retreat_bias < 0.78 and float(damage) < 18.0:
                self._set_intent(
                    target_eid,
                    ai,
                    will,
                    "protecting",
                    max(safety_score, min(96.0, 70.0 + (assault_bias * 20.0))),
                    target=source_target,
                    target_eid=source_eid,
                )
            elif quirk in {"hide_behind_counter", "slip_out_back", "shelter_with_crowd", "freeze", "look_busy"} and isinstance(action_target, (tuple, list)) and len(action_target) >= 3:
                self._set_intent(
                    target_eid,
                    ai,
                    will,
                    "seeking_safety",
                    safety_score,
                    target=(int(action_target[0]), int(action_target[1]), int(action_target[2])),
                    target_eid=source_eid,
                )
        else:
            protect_score = min(96.0, 66.0 + (assault_bias * 24.0) + min(14.0, float(damage)))
            self._set_intent(
                target_eid,
                ai,
                will,
                "protecting",
                protect_score,
                target=source_target,
                target_eid=source_eid,
            )
            quirk_row = apply_self_protection_quirk(
                self.sim,
                target_eid,
                ai=ai,
                pos=target_pos,
                reason="standing_ground",
                target=source_target,
                threat_eid=source_eid,
                threat_pos=source_target,
                damage=damage,
            )
            action = quirk_row.get("action") if isinstance(quirk_row, dict) else {}
            quirk = str(quirk_row.get("quirk", "") or "").strip().lower() if isinstance(quirk_row, dict) else ""
            action_target = action.get("target") if isinstance(action, dict) else None
            if quirk in {"hide_behind_counter", "slip_out_back", "shelter_with_crowd", "freeze", "look_busy", "stand_ground"} and isinstance(action_target, (tuple, list)) and len(action_target) >= 3:
                self._set_intent(
                    target_eid,
                    ai,
                    will,
                    "protecting",
                    protect_score,
                    target=(int(action_target[0]), int(action_target[1]), int(action_target[2])),
                    target_eid=source_eid,
                )
        _schedule_will_rethink(self.sim, target_eid, current_tick=getattr(self.sim, "tick", 0), delay_ticks=0)
        _mark_actor_urgent(self.sim, target_eid, family="will", reason="direct_damage", ttl_ticks=18)
        _mark_actor_urgent(self.sim, target_eid, family="move", reason="direct_damage", ttl_ticks=18)
        _schedule_actor_due(self.sim, target_eid, "will", delay_ticks=0, reason="direct_damage")
        _schedule_actor_due(self.sim, target_eid, "move", delay_ticks=0, reason="direct_damage")

    def _live_timeskip_will_urgent(self, eid, ai, needs, pos, vitality, suppression, *, player_pos=None):
        if ai is None or needs is None or pos is None:
            return True
        if vitality is not None and bool(getattr(vitality, "downed", False)):
            return True
        state = str(getattr(ai, "state", "") or "").strip().lower()
        role = str(getattr(ai, "role", "") or "").strip().lower()
        if role == "wildlife":
            return True
        if suppression is not None and bool(getattr(suppression, "surrendered", False)):
            return True
        if state in self.LIVE_TIMESKIP_URGENT_STATES:
            return True
        if getattr(ai, "target_eid", None) is not None:
            return True
        if getattr(needs, "critical", None):
            return True
        if float(getattr(needs, "energy", 100.0) or 100.0) <= 18.0:
            return True
        if float(getattr(needs, "safety", 100.0) or 100.0) <= 18.0:
            return True
        if player_pos is not None and int(getattr(player_pos, "z", 0) or 0) == int(getattr(pos, "z", 0) or 0):
            if _manhattan(int(pos.x), int(pos.y), int(player_pos.x), int(player_pos.y)) <= _WILL_PLAYER_PROXIMITY_RADIUS:
                return _has_line_of_sight(
                    self.sim,
                    int(pos.x),
                    int(pos.y),
                    int(pos.z),
                    int(player_pos.x),
                    int(player_pos.y),
                    int(player_pos.z),
                )
        return False

    def _live_timeskip_will_recheck_delay(self, ai, needs, vitality, suppression):
        if vitality is not None and bool(getattr(vitality, "downed", False)):
            return 1
        if suppression is not None and bool(getattr(suppression, "surrendered", False)):
            return 4
        if getattr(needs, "critical", None):
            return 2
        if float(getattr(needs, "energy", 100.0) or 100.0) <= 18.0:
            return 2
        if float(getattr(needs, "safety", 100.0) or 100.0) <= 18.0:
            return 2
        state = str(getattr(ai, "state", "") or "").strip().lower()
        if state in {"protecting", "seeking_safety", "chasing"}:
            return 4
        if state in {"reporting_incident", "helping_victim", "warning", "ejecting_target", "leaving_property"}:
            return 6
        if state in {"seeking_medical_aid", "seeking_safe_spot", "seeking_shelter"}:
            return 10
        if state in {"casing_target", "committing_property_crime", "rendezvousing_crew", "seeking_criminal_affiliation"}:
            return 12
        return 18

    def _attention_will_recheck_delay(self, eid, ai, needs, vitality, suppression, *, scope="compressed", urgent=False):
        delay = int(self._live_timeskip_will_recheck_delay(ai, needs, vitality, suppression))
        scope = str(scope or "").strip().lower()
        state = str(getattr(ai, "state", "") or "").strip().lower()
        if urgent:
            return max(1, delay)
        if scope == "full":
            return max(2, min(delay, 12))
        if scope == "warm":
            if state in {"protecting", "chasing", "seeking_safety", "reporting_incident", "helping_victim", "warning", "ejecting_target", "leaving_property"}:
                return max(90, delay)
            return max(240, delay)
        if scope == "compressed":
            if state in {"seeking_medical_aid", "seeking_safe_spot", "seeking_shelter"}:
                return max(120, delay)
            if state in {"protecting", "chasing", "seeking_safety", "reporting_incident", "helping_victim", "warning", "ejecting_target", "leaving_property"}:
                return max(120, delay)
            return max(300, delay)
        return 300

    def _live_timeskip_will_candidate_ids(
        self,
        ais,
        positions,
        needs_map,
        wills,
        vitalities,
        suppressions,
        *,
        player_pos=None,
    ):
        ids = []
        for eid, ai in tuple(ais.items()):
            pos = positions.get(eid)
            needs = needs_map.get(eid)
            will = wills.get(eid)
            if pos is None or needs is None or will is None:
                continue
            suppression = suppressions.get(eid)
            vitality = vitalities.get(eid)
            if self._live_timeskip_will_urgent(eid, ai, needs, pos, vitality, suppression, player_pos=player_pos):
                if _will_rethink_due(self.sim, eid, current_tick=getattr(self.sim, "tick", 0)):
                    ids.append(int(eid))
                    _schedule_will_rethink(
                        self.sim,
                        eid,
                        current_tick=getattr(self.sim, "tick", 0),
                        delay_ticks=self._live_timeskip_will_recheck_delay(ai, needs, vitality, suppression),
                    )
                continue
            if _will_rethink_due(self.sim, eid, current_tick=getattr(self.sim, "tick", 0)):
                ids.append(int(eid))
        return tuple(sorted(set(ids)))

    def _set_intent(self, eid, ai, will, intent, score, target=None, target_eid=None):
        active_target_states = {
            "selling_scavenged": "scavenged_sale",
            "seeking_medical_aid": "medical",
            "seeking_safe_spot": "safe_spot",
            "seeking_shelter": "lodging",
            "patrolling": "routine",
            "working": "routine",
            "lounging": "routine",
            "socializing": "routine",
            "shopping": "shopping",
            "resting": "routine",
        }
        if _entity_is_downed(self.sim, eid):
            _apply_downed_actor_state(self.sim, eid, tick=self.sim.tick)
            return
        previous = (ai.state, ai.target, ai.target_eid)
        next_state = (intent, target, target_eid)
        if previous == next_state and will.intent == intent:
            will.score = score
            will.target = target
            will.target_eid = target_eid
            will.last_tick = self.sim.tick
            if intent in active_target_states and isinstance(target, (tuple, list)):
                _remember_opportunity_active_target(
                    self.sim,
                    eid,
                    intent,
                    target,
                    lead_kind=active_target_states.get(intent),
                    timeout_ticks=180,
                )
                hold_ticks = _routine_will_hold_ticks(intent)
                if hold_ticks > 0:
                    _schedule_will_rethink(
                        self.sim,
                        eid,
                        current_tick=self.sim.tick,
                        delay_ticks=hold_ticks,
                    )
            else:
                _clear_will_rethink(self.sim, eid)
            return

        ai.state = intent
        ai.target = target
        ai.target_eid = target_eid

        will.intent = intent
        will.score = score
        will.target = target
        will.target_eid = target_eid
        will.last_tick = self.sim.tick

        if previous[0] != intent and previous[0]:
            _clear_opportunity_active_target(self.sim, eid, previous[0])
        if intent in active_target_states and isinstance(target, (tuple, list)):
            _remember_opportunity_active_target(
                self.sim,
                eid,
                intent,
                target,
                lead_kind=active_target_states.get(intent),
                timeout_ticks=180,
            )
            hold_ticks = _routine_will_hold_ticks(intent)
            if hold_ticks > 0:
                _schedule_will_rethink(
                    self.sim,
                    eid,
                    current_tick=self.sim.tick,
                    delay_ticks=hold_ticks,
                )
        elif intent == "idle":
            _clear_opportunity_active_target(self.sim, eid)
            _clear_will_rethink(self.sim, eid)
        else:
            _clear_will_rethink(self.sim, eid)

        self.sim.emit(Event(
            "npc_intent_changed",
            npc_eid=eid,
            intent=intent,
            score=round(score, 2),
            target=target,
            target_eid=target_eid,
        ))
        if intent in {"casing_target", "committing_property_crime", "rendezvousing_crew", "seeking_criminal_affiliation"}:
            drive = criminal_drive_state(self.sim, eid, create=False)
            plan_key = str(getattr(drive, "current_plan_key", "") or "").strip() if drive is not None else ""
            try:
                organization_eid = int(getattr(drive, "current_affiliation_organization_eid", 0) or 0) or None
            except (TypeError, ValueError):
                organization_eid = None
            if organization_eid is None and plan_key:
                active_plan = active_plan_for_actor(self.sim, eid, current_tick=self.sim.tick)
                if isinstance(active_plan, dict) and str(active_plan.get("plan_key", "") or "").strip() == plan_key:
                    try:
                        organization_eid = int(active_plan.get("organization_eid", 0) or 0) or None
                    except (TypeError, ValueError):
                        organization_eid = None
            organization_name = ""
            organization_key = ""
            organization_kind = ""
            plan_fields = _crime_plan_event_fields(self.sim, eid, plan_key)
            if organization_eid is not None:
                profile = organization_profile(self.sim, organization_eid)
                if profile is not None:
                    organization_name = str(getattr(profile, "name", "") or "").strip()
                    organization_key = str(getattr(profile, "key", "") or "").strip()
                    organization_kind = str(getattr(profile, "kind", "") or "").strip().lower()
            self.sim.emit(Event(
                "npc_crime_attempt_started",
                npc_eid=eid,
                intent=intent,
                score=round(score, 2),
                target=target,
                target_eid=target_eid,
                plan_key=plan_key or None,
                property_id=str(getattr(drive, "current_target_property_id", "") or "").strip() or None,
                organization_eid=organization_eid,
                organization_name=organization_name or None,
                organization_key=organization_key or None,
                organization_kind=organization_kind or None,
                **plan_fields,
                summary=str(getattr(drive, "current_activity_summary", "") or "").strip() or None,
                x=int(target[0]) if isinstance(target, (list, tuple)) and len(target) >= 1 else None,
                y=int(target[1]) if isinstance(target, (list, tuple)) and len(target) >= 2 else None,
                z=int(target[2]) if isinstance(target, (list, tuple)) and len(target) >= 3 else None,
            ))

    def update(self):
        ais = self.sim.ecs.get(AI)
        positions = self.sim.ecs.get(Position)
        needs_map = self.sim.ecs.get(NPCNeeds)
        traits_map = self.sim.ecs.get(NPCTraits)
        wills = self.sim.ecs.get(NPCWill)
        wildlife_behaviors = self.sim.ecs.get(WildlifeBehavior)
        memories = self.sim.ecs.get(NPCMemory)
        socials = self.sim.ecs.get(NPCSocial)
        routines = self.sim.ecs.get(NPCRoutine)
        occupations = self.sim.ecs.get(Occupation)
        portfolios = self.sim.ecs.get(PropertyPortfolio)
        justices = self.sim.ecs.get(JusticeProfile)
        identities = self.sim.ecs.get(CreatureIdentity)
        vitalities = self.sim.ecs.get(Vitality)
        suppressions = self.sim.ecs.get(SuppressionState)
        criminal_drives = self.sim.ecs.get(CriminalDriveState)
        player_eid = getattr(self.sim, "player_eid", None)
        player_pos = positions.get(player_eid)
        live_timeskip_active = self._live_timeskip_active()
        dialog_state = getattr(self.sim, "dialog_ui", None)
        dialog_open = bool(dialog_state.get("open")) if isinstance(dialog_state, dict) else False
        dialog_cooldowns = getattr(self.sim, "npc_dialogue_cooldowns", None)
        if not isinstance(dialog_cooldowns, dict):
            dialog_cooldowns = {}
            self.sim.npc_dialogue_cooldowns = dialog_cooldowns
        tip_cooldowns = getattr(self.sim, "npc_behavior_tip_cooldowns", None)
        if not isinstance(tip_cooldowns, dict):
            tip_cooldowns = {}
            self.sim.npc_behavior_tip_cooldowns = tip_cooldowns
        pending_behavior_tips = []
        completed_service_claims = _advance_service_job_board_claims(self.sim)
        if completed_service_claims and player_pos is not None and hasattr(self.sim, "log"):
            for claim in completed_service_claims[:3]:
                npc_pos = positions.get(int(claim.get("claimant_eid", 0) or 0))
                if npc_pos is None or int(npc_pos.z) != int(player_pos.z):
                    continue
                if _manhattan(int(npc_pos.x), int(npc_pos.y), int(player_pos.x), int(player_pos.y)) > 14:
                    continue
                claimant = str(claim.get("claimant_name", "") or "Someone").strip() or "Someone"
                target_name = str(claim.get("target_property_name", "") or "the posting").strip() or "the posting"
                self.sim.log.add(
                    f"{claimant} finishes posted work for {target_name}.",
                    channel="opportunity",
                    priority="normal",
                )

        _refresh_actor_attention(self.sim, player_eid=player_eid)
        if live_timeskip_active:
            due_eids = _pop_due_actors(self.sim, "will", current_tick=getattr(self.sim, "tick", 0))
            ai_items = [
                (eid, ais[eid])
                for eid in due_eids
                if eid in ais
            ]
        else:
            ai_items = tuple(ais.items())

        for eid, ai in ai_items:
            pos = positions.get(eid)
            if not pos:
                continue
            vitality = vitalities.get(eid)
            if vitality and vitality.downed:
                continue
            if not _detail_tick_allowed(self.sim, pos, eid, coarse_divisor=3):
                continue

            needs = needs_map.get(eid)
            will = wills.get(eid)
            if not needs or not will:
                continue

            suppression = suppressions.get(eid)
            live_will_urgent = live_timeskip_active and self._live_timeskip_will_urgent(
                eid,
                ai,
                needs,
                pos,
                vitalities.get(eid),
                suppression,
                player_pos=player_pos,
            )
            if live_timeskip_active:
                scope_info = _attention_scope_for_actor(self.sim, eid, pos=pos, ai=ai)
                scope = str((scope_info or {}).get("scope", "compressed") or "compressed")
                recheck_delay = self._attention_will_recheck_delay(
                    eid,
                    ai,
                    needs,
                    vitalities.get(eid),
                    suppression,
                    scope=scope,
                    urgent=bool(live_will_urgent),
                )
                _schedule_will_rethink(
                    self.sim,
                    eid,
                    current_tick=getattr(self.sim, "tick", 0),
                    delay_ticks=recheck_delay,
                )
                _schedule_actor_due(
                    self.sim,
                    eid,
                    "will",
                    delay_ticks=recheck_delay,
                    reason=f"{scope}:will_recheck",
                )
                if (
                    not live_will_urgent
                    and scope == "compressed"
                    and str(getattr(ai, "state", "") or "").strip().lower()
                    in {
                        "idle",
                        "lounging",
                        "patrolling",
                        "resting",
                        "scavenging",
                        "seeking_companionship",
                        "seeking_social",
                        "selling_scavenged",
                        "socializing",
                        "working",
                    }
                ):
                    continue
            if not live_will_urgent and _should_skip_live_will_update(
                self.sim,
                eid,
                ai,
                will,
                needs,
                pos,
                player_pos=player_pos,
                suppression=suppression,
            ):
                continue

            routine = routines.get(eid)
            if suppression and suppression.surrendered:
                peaceful_rec = _active_contractor_record(
                    self.sim,
                    eid,
                    ally_eid=player_eid,
                    jobs={"surrendered"},
                )
                if peaceful_rec:
                    if ai.state not in {"following", "holding"} or ai.target is None:
                        ai.state = "holding"
                        ai.target = _contractor_order_target_from_record(peaceful_rec) or (int(pos.x), int(pos.y), int(pos.z))
                        ai.target_eid = None
                    will.intent = str(ai.state or "holding").strip().lower() or "holding"
                    will.target = ai.target
                    will.target_eid = ai.target_eid
                else:
                    if ai.state != "surrendered":
                        ai.state = "surrendered"
                        ai.target = None
                        ai.target_eid = None
                    will.intent = "surrendered"
                will.last_tick = self.sim.tick
                continue

            wildlife = wildlife_behaviors.get(eid)
            if str(getattr(ai, "role", "") or "").strip().lower() == "wildlife" and wildlife:
                _relocate_indoor_wildlife_outdoors(self.sim, eid, pos, routine)
                home = _wildlife_home_position(pos, routine)
                damage_reaction = _wildlife_recent_damage_reaction(self.sim, eid)
                if damage_reaction:
                    reaction_intent = str(damage_reaction.get("intent", "") or "").strip().lower()
                    reaction_target = damage_reaction.get("target")
                    reaction_target_eid = damage_reaction.get("target_eid")
                    if reaction_target_eid is not None:
                        live_target_pos = positions.get(reaction_target_eid)
                        if live_target_pos is not None and int(live_target_pos.z) == int(pos.z):
                            reaction_target = (
                                int(live_target_pos.x),
                                int(live_target_pos.y),
                                int(live_target_pos.z),
                            )
                        elif reaction_intent != "holding":
                            reaction_target_eid = None
                    if reaction_intent in {"protecting", "chasing", "holding", "seeking_safety"} and reaction_target:
                        self._set_intent(
                            eid,
                            ai,
                            will,
                            reaction_intent,
                            float(damage_reaction.get("score", 78.0) or 78.0),
                            reaction_target,
                            reaction_target_eid,
                        )
                        continue
                if ai.state == "seeking_safety" and ai.target:
                    try:
                        safety_age = int(self.sim.tick) - int(getattr(will, "last_tick", -1) or -1)
                    except (TypeError, ValueError):
                        safety_age = 0
                    target = ai.target if isinstance(ai.target, (tuple, list)) and len(ai.target) >= 2 else None
                    near_target = bool(target and _manhattan(pos.x, pos.y, int(target[0]), int(target[1])) <= 1)
                    if not near_target and safety_age < 12:
                        self._set_intent(eid, ai, will, "seeking_safety", 86.0, ai.target, None)
                        continue
                    ai.state = "idle"
                    ai.target = None
                    ai.target_eid = None

                ecology_intent = _wildlife_ecology_intent(
                    self.sim,
                    eid,
                    pos,
                    routine,
                    wildlife,
                    identities.get(eid),
                    needs,
                )
                if ecology_intent:
                    self._set_intent(
                        eid,
                        ai,
                        will,
                        ecology_intent["intent"],
                        ecology_intent["score"],
                        ecology_intent["target"],
                        ecology_intent["target_eid"],
                    )
                    continue

                social_intent = _wildlife_social_intent(
                    self.sim,
                    eid,
                    pos,
                    identities.get(eid),
                    _animal_ecology_profile_for_actor(self.sim, eid),
                    needs,
                )
                if social_intent:
                    self._set_intent(
                        eid,
                        ai,
                        will,
                        social_intent["intent"],
                        social_intent["score"],
                        social_intent["target"],
                        social_intent["target_eid"],
                    )
                    continue

                current_hour = _world_hour(self.sim)
                active_now = _wildlife_is_active(wildlife, current_hour)
                rest_threshold = 42.0 + (float(getattr(wildlife, "rest_bias", 0.3) or 0.3) * 24.0)
                linger_rng = random.Random(f"{self.sim.seed}:{eid}:{self.sim.tick}:wildlife_linger")
                should_linger = (
                    home is not None
                    and _manhattan(pos.x, pos.y, home[0], home[1]) <= 1
                    and ai.state == "resting"
                    and linger_rng.random() < max(0.08, float(getattr(wildlife, "rest_bias", 0.3)) * 0.45)
                )

                if not active_now or needs.energy <= rest_threshold or should_linger:
                    self._set_intent(
                        eid,
                        ai,
                        will,
                        "resting",
                        48.0 + max(0.0, 100.0 - float(needs.energy)),
                        home or (pos.x, pos.y, pos.z),
                        None,
                    )
                    continue

                if ai.state == "patrolling" and ai.target:
                    self._set_intent(eid, ai, will, "patrolling", 24.0, ai.target, None)
                    continue

                patrol_target = _pick_wildlife_patrol_target(
                    self.sim,
                    eid,
                    pos,
                    routine,
                    wildlife,
                    identities.get(eid),
                )
                if patrol_target and home and patrol_target != home:
                    self._set_intent(eid, ai, will, "patrolling", 24.0, patrol_target, None)
                else:
                    self._set_intent(
                        eid,
                        ai,
                        will,
                        "resting",
                        18.0,
                        home or (pos.x, pos.y, pos.z),
                        None,
                    )
                continue

            traits = traits_map.get(eid) or NPCTraits()
            memory = memories.get(eid)
            social = socials.get(eid)
            occupation = occupations.get(eid)
            portfolio = portfolios.get(eid)
            medical_tip = _recent_behavior_tip(memory, BEHAVIOR_TIP_MEDICAL, now=self.sim.tick)
            shelter_tip = _recent_behavior_tip(memory, BEHAVIOR_TIP_SHELTER, now=self.sim.tick)
            safe_spot_tip = _recent_behavior_tip(memory, BEHAVIOR_TIP_SAFE_SPOT, now=self.sim.tick)
            heat_tip = _recent_behavior_tip(memory, BEHAVIOR_TIP_HEAT, now=self.sim.tick)
            street_buy_tip = _recent_behavior_tip(memory, BEHAVIOR_TIP_STREET_BUY, now=self.sim.tick)
            street_appraise_tip = _recent_behavior_tip(memory, BEHAVIOR_TIP_STREET_APPRAISE, now=self.sim.tick)
            hidden_trade_tip = _recent_behavior_tip(memory, BEHAVIOR_TIP_HIDDEN_TRADE, now=self.sim.tick)
            hidden_clinic_tip = _recent_behavior_tip(memory, BEHAVIOR_TIP_HIDDEN_CLINIC, now=self.sim.tick)
            medical_target = None
            shelter_target = None
            avoidance_target = None
            safe_spot_share = None
            street_buy_target = None
            street_buy_share = None
            street_appraise_target = None
            street_appraise_share = None

            def _memory_visible(entry):
                return not _guard_grace_suppresses_memory_entry(
                    self.sim,
                    eid,
                    entry,
                    player_eid,
                )

            # Higher-priority external states can preempt intent planning.
            if ai.state == "investigating" and ai.target:
                will.intent = "investigating"
                will.target = ai.target
                will.target_eid = ai.target_eid
                will.last_tick = self.sim.tick
                continue

            if ai.state == "following" and ai.target:
                will.intent = "following"
                will.target = ai.target
                will.target_eid = ai.target_eid
                will.last_tick = self.sim.tick
                continue

            if ai.state == "holding" and ai.target:
                will.intent = "holding"
                will.target = ai.target
                will.target_eid = ai.target_eid
                will.last_tick = self.sim.tick
                continue

            # Observed incident response intents are assigned by
            # ObservedIncidentResponseSystem. Preserve them here so the
            # ordinary needs/duty planner does not immediately stomp them.
            if ai.state in {"reporting_incident", "helping_victim", "warning", "ejecting_target", "leaving_property"} and ai.target:
                will.intent = ai.state
                will.target = ai.target
                will.target_eid = ai.target_eid
                will.last_tick = self.sim.tick
                continue

            if ai.state == "seeking_social" and ai.target and ai.target_eid is not None:
                urgent_social_interrupt = (
                    _strongest_memory_entry(memory, "threat", predicate=_memory_visible)
                    or _strongest_memory_entry(memory, "ally_threatened", predicate=_memory_visible)
                    or _strongest_memory_entry(memory, "conflict_side", predicate=_memory_visible)
                    or _strongest_memory_entry(memory, "property_threat", predicate=_memory_visible)
                )
                if not urgent_social_interrupt:
                    will.intent = "seeking_social"
                    will.target = ai.target
                    will.target_eid = ai.target_eid
                    will.last_tick = self.sim.tick
                    continue

            drive_state = criminal_drives.get(eid)
            if ai.state in {"casing_target", "committing_property_crime", "rendezvousing_crew", "seeking_criminal_affiliation"} and ai.target:
                cooldown_until = int(getattr(drive_state, "cooldown_until_tick", 0) or 0) if drive_state is not None else 0
                preserve_crime_state = cooldown_until <= int(self.sim.tick)
                active_plan = active_plan_for_actor(self.sim, eid, current_tick=self.sim.tick) if preserve_crime_state else None
                active_plan_stage = str((active_plan or {}).get("stage", "") or "").strip().lower()
                if ai.state == "rendezvousing_crew" and active_plan_stage not in {"forming", "rendezvous"}:
                    preserve_crime_state = False
                elif ai.state == "committing_property_crime" and active_plan_stage in {"forming", "rendezvous"}:
                    preserve_crime_state = False
                if preserve_crime_state:
                    will.intent = ai.state
                    will.target = ai.target
                    will.target_eid = ai.target_eid
                    will.last_tick = self.sim.tick
                    continue

            active_threat_context = None
            if ai.state in {"protecting", "seeking_safety"} and (ai.target or ai.target_eid is not None):
                active_threat_context = _npc_live_threat_context(
                    self.sim,
                    eid,
                    pos,
                    target_eid=ai.target_eid,
                    memory=memory,
                    needs=needs,
                    traits=traits,
                    vitality=vitality,
                    suppression=suppression,
                    max_steps=5,
                )

            if ai.state == "seeking_safety" and ai.target:
                if getattr(ai, "incident_id", None) is not None or active_threat_context:
                    retreat_target = None
                    if active_threat_context:
                        retreat_target = active_threat_context.get("retreat_target")
                        if retreat_target is None:
                            threat_focus = active_threat_context.get("threat_focus")
                            current_target = tuple(ai.target or ())
                            if (
                                threat_focus
                                and len(current_target) >= 3
                                and int(current_target[2]) == int(pos.z)
                                and _manhattan(int(current_target[0]), int(current_target[1]), threat_focus[0], threat_focus[1])
                                > _manhattan(int(pos.x), int(pos.y), threat_focus[0], threat_focus[1])
                            ):
                                retreat_target = (
                                    int(current_target[0]),
                                    int(current_target[1]),
                                    int(current_target[2]),
                                )
                    else:
                        retreat_target = ai.target
                    if retreat_target and retreat_target != (int(pos.x), int(pos.y), int(pos.z)):
                        retreat_bias = float(((active_threat_context or {}).get("metrics") or {}).get("retreat_bias", 0.55) or 0.55)
                        self._set_intent(
                            eid,
                            ai,
                            will,
                            "seeking_safety",
                            max(82.0, 68.0 + (retreat_bias * 26.0)),
                            retreat_target,
                            ai.target_eid,
                        )
                        continue

            if ai.state == "protecting" and (ai.target or ai.target_eid is not None):
                recent_threat = memory.strongest("ally_threatened") if memory else None
                recent_property = _strongest_memory_entry(
                    memory,
                    "property_threat",
                    predicate=_memory_visible,
                )
                live_target = _live_target_position(
                    self.sim,
                    ai.target_eid,
                    positions=positions,
                    vitalities=vitalities,
                    z=pos.z,
                )
                if live_target or (recent_threat and recent_threat["strength"] > 0.25) or (
                    recent_property and recent_property["strength"] > 0.25
                ):
                    threat_focus = (active_threat_context or {}).get("threat_focus")
                    metrics = (active_threat_context or {}).get("metrics")
                    if metrics is None:
                        _loadout, held_weapon, _instance = _weapon_context_for_entity(self.sim, eid)
                        metrics = _npc_combat_metrics(
                            needs=needs,
                            traits=traits,
                            vitality=vitality,
                            suppression=suppression,
                            weapon=held_weapon,
                            **_npc_status_metric_args(self.sim, eid),
                        )
                    if threat_focus is None and live_target is not None:
                        threat_focus = (int(live_target.x), int(live_target.y), int(live_target.z))
                    role_key = str(getattr(ai, "role", "") or "").strip().lower()
                    retreat_threshold = 0.62 if role_key in {"guard", "scout"} and metrics["has_ranged"] else 0.46
                    should_seek_safety = bool(
                        threat_focus
                        and (
                            (suppression and suppression.pinned())
                            or metrics["retreat_bias"] >= retreat_threshold
                            or (
                                not metrics["has_ranged"]
                                and metrics["retreat_bias"] >= 0.34
                                and (
                                    (suppression and suppression.shaken())
                                    or metrics["hp_ratio"] < 0.6
                                )
                            )
                        )
                    )
                    if should_seek_safety:
                        retreat_target = (active_threat_context or {}).get("retreat_target")
                        if retreat_target and retreat_target != (int(pos.x), int(pos.y), int(pos.z)):
                            self._set_intent(
                                eid,
                                ai,
                                will,
                                "seeking_safety",
                                max(82.0, 68.0 + (metrics["retreat_bias"] * 26.0)),
                                retreat_target,
                                ai.target_eid,
                            )
                            continue
                    # Pinned NPCs stay put instead of advancing.
                    if suppression and suppression.pinned():
                        self._set_intent(
                            eid,
                            ai,
                            will,
                            "protecting",
                            max(76.0, 66.0 + (metrics["assault_bias"] * 10.0)),
                            (int(pos.x), int(pos.y), int(pos.z)),
                            ai.target_eid,
                        )
                        continue
                    protect_target = threat_focus or ai.target or (int(pos.x), int(pos.y), int(pos.z))
                    self._set_intent(
                        eid,
                        ai,
                        will,
                        "protecting",
                        max(74.0, 70.0 + (metrics["assault_bias"] * 12.0) - (metrics["retreat_bias"] * 6.0)),
                        protect_target,
                        ai.target_eid,
                    )
                    continue

            active_service_claim = _active_service_job_claim_for_actor(self.sim, eid)
            if isinstance(active_service_claim, dict):
                service_target = _service_job_claim_target(self.sim, active_service_claim)
                if service_target is not None:
                    active_service_claim["target"] = service_target
                    self._set_intent(eid, ai, will, "working", 58.0, service_target, None)
                    _mark_actor_urgent(self.sim, eid, family="move", reason="service_job", ttl_ticks=18)
                    _mark_actor_urgent(self.sim, eid, family="will", reason="service_job", ttl_ticks=18)
                    _schedule_actor_due(self.sim, eid, "move", delay_ticks=0, reason="service_job")
                    _schedule_actor_due(self.sim, eid, "will", delay_ticks=12, reason="service_job")
                    continue

            if str(getattr(ai, "state", "") or "").strip().lower() in {
                "idle",
                "lounging",
                "patrolling",
                "resting",
                "scavenging",
                "seeking_companionship",
                "seeking_social",
                "selling_scavenged",
                "socializing",
                "working",
            }:
                claimed_service_job = _npc_claim_service_job_from_board(self.sim, eid)
                if isinstance(claimed_service_job, dict):
                    service_target = _service_job_claim_target(self.sim, claimed_service_job)
                    if service_target is not None:
                        claimed_service_job["target"] = service_target
                        if player_pos is not None and int(pos.z) == int(player_pos.z):
                            if _manhattan(int(pos.x), int(pos.y), int(player_pos.x), int(player_pos.y)) <= 14 and hasattr(self.sim, "log"):
                                claimant = str(claimed_service_job.get("claimant_name", "") or "Someone").strip() or "Someone"
                                target_name = str(claimed_service_job.get("target_property_name", "") or "the posting").strip() or "the posting"
                                self.sim.log.add(
                                    f"{claimant} takes posted work for {target_name}.",
                                    channel="opportunity",
                                    priority="normal",
                                )
                        self._set_intent(eid, ai, will, "working", 58.0, service_target, None)
                        _mark_actor_urgent(self.sim, eid, family="move", reason="service_job_claimed", ttl_ticks=18)
                        _mark_actor_urgent(self.sim, eid, family="will", reason="service_job_claimed", ttl_ticks=18)
                        _schedule_actor_due(self.sim, eid, "move", delay_ticks=0, reason="service_job_claimed")
                        _schedule_actor_due(self.sim, eid, "will", delay_ticks=12, reason="service_job_claimed")
                        continue

            best_intent = "idle"
            best_score = 0.0
            best_target = None
            best_target_eid = None
            best_shopping_target = None

            if memory:
                property_threat = _strongest_memory_entry(
                    memory,
                    "property_threat",
                    predicate=_memory_visible,
                )
            else:
                property_threat = None

            if property_threat:
                threatened_property = property_threat["data"].get("property_id")
                threatened_prop = self.sim.properties.get(threatened_property) if threatened_property else None
                _, claim_reason = _property_claim_reason(
                    self.sim,
                    eid,
                    threatened_prop,
                    x=pos.x,
                    y=pos.y,
                    z=pos.z,
                    min_standing=0.58,
                )
                if claim_reason:
                    best_intent = "protecting"
                    best_score = min(95.0, 76.0 + (property_threat["strength"] * 18.0))
                    focus = _property_focus_position(threatened_prop) if threatened_prop else None
                    if focus:
                        best_target = focus
                    else:
                        best_target = (
                            property_threat["data"].get("x", pos.x),
                            property_threat["data"].get("y", pos.y),
                            property_threat["data"].get("z", pos.z),
                        )
                    best_target_eid = property_threat["data"].get("offender_eid")

            ally_threat = _strongest_memory_entry(
                memory,
                "ally_threatened",
                predicate=_memory_visible,
            )
            if ally_threat:
                protect_allies = _effective_behavior_value(
                    self.sim,
                    eid,
                    BEHAVIOR_PROTECT_ALLIES,
                    traits=traits,
                )
                threat_strength = float(ally_threat.get("strength", 0.0) or 0.0)
                threat_data = ally_threat.get("data", {}) if isinstance(ally_threat.get("data"), dict) else {}
                ally_eid = threat_data.get("ally_eid")
                against_eid = threat_data.get("against_eid")
                against_pos = positions.get(against_eid) if against_eid is not None else None
                ally_bond = social.bonds.get(ally_eid) if social and ally_eid is not None else {}
                protectiveness = float((ally_bond or {}).get("protectiveness", 0.0) or 0.0)
                trust = float((ally_bond or {}).get("trust", 0.0) or 0.0)
                protect_drive = (
                    (threat_strength * 48.0)
                    + (protectiveness * 22.0)
                    + (trust * 10.0)
                    + (protect_allies * 24.0)
                )
                if against_pos and int(against_pos.z) == int(pos.z):
                    if protect_drive > best_score and (
                        threat_strength >= 0.24
                        or protectiveness >= 0.62
                        or protect_allies >= 0.65
                    ):
                        best_intent = "protecting"
                        best_score = min(96.0, protect_drive)
                        best_target = (against_pos.x, against_pos.y, against_pos.z)
                        best_target_eid = against_eid

            conflict_side = _strongest_memory_entry(
                memory,
                "conflict_side",
                predicate=_memory_visible,
            )
            if conflict_side:
                protect_allies = _effective_behavior_value(
                    self.sim,
                    eid,
                    BEHAVIOR_PROTECT_ALLIES,
                    traits=traits,
                )
                side_strength = float(conflict_side.get("strength", 0.0) or 0.0)
                side_data = conflict_side.get("data", {}) if isinstance(conflict_side.get("data"), dict) else {}
                side_eid = side_data.get("side_eid")
                against_eid = side_data.get("against_eid")
                side_pos = positions.get(side_eid) if side_eid is not None else None
                against_pos = positions.get(against_eid) if against_eid is not None else None
                side_impression = _npc_actor_impression(self.sim, eid, side_eid, memory=memory, social=social)
                against_impression = _npc_actor_impression(self.sim, eid, against_eid, memory=memory, social=social)
                commit_ready = (
                    side_strength >= 0.38
                    or protect_allies >= 0.58
                    or side_impression >= 0.58
                    or against_impression <= -0.58
                )
                protect_drive = (
                    (side_strength * 54.0)
                    + (max(0.0, side_impression) * 18.0)
                    + (max(0.0, -against_impression) * 16.0)
                    + (protect_allies * 22.0)
                )
                if against_pos and int(against_pos.z) == int(pos.z) and commit_ready and protect_drive > best_score:
                    best_intent = "protecting"
                    best_score = min(96.0, protect_drive)
                    best_target = (against_pos.x, against_pos.y, against_pos.z)
                    best_target_eid = against_eid
                elif side_pos and int(side_pos.z) == int(pos.z):
                    investigate_score = max(18.0, side_strength * 48.0)
                    if investigate_score > best_score:
                        best_intent = "investigating"
                        best_score = investigate_score
                        best_target = (side_pos.x, side_pos.y, side_pos.z)
                        best_target_eid = side_eid

            offense = _strongest_memory_entry(
                memory,
                "offense",
                predicate=_memory_visible,
            )
            if offense:
                offense_strength = offense["strength"]
                offense_data = offense["data"]
                offender_eid = offense_data.get("offender_eid")
                offender_pos = positions.get(offender_eid) if offender_eid is not None else None
                justice = justices.get(eid)
                crime_sensitivity = _crime_sensitivity(justice, default=0.5)
                justice_behavior = _effective_behavior_value(
                    self.sim,
                    eid,
                    BEHAVIOR_ENFORCE_JUSTICE,
                    traits=traits,
                    justice=justice,
                )

                justice_drive = 24.0 + (justice_behavior * 56.0) + (crime_sensitivity * 10.0)

                protect_threshold = max(0.24, 0.5 - (crime_sensitivity * 0.12))
                investigate_threshold = max(0.18, 0.34 - (crime_sensitivity * 0.1))

                if offender_pos and offender_pos.z == pos.z:
                    if offense_strength >= protect_threshold and justice_drive > best_score:
                        best_intent = "protecting"
                        best_score = min(95.0, justice_drive + (offense_strength * 35.0))
                        best_target = (offender_pos.x, offender_pos.y, offender_pos.z)
                        best_target_eid = offender_eid
                    elif (
                        offense_strength >= investigate_threshold
                        and justice_behavior >= 0.32
                        and (offense_strength * 60.0) > best_score
                    ):
                        best_intent = "investigating"
                        best_score = offense_strength * 60.0
                        best_target = (offender_pos.x, offender_pos.y, offender_pos.z)
                        best_target_eid = offender_eid

            avoid_threat = _effective_behavior_value(
                self.sim,
                eid,
                BEHAVIOR_AVOID_THREAT,
                traits=traits,
                needs=needs,
            )
            safety_pressure = (100.0 - needs.safety) * (0.5 + (avoid_threat * 0.75))
            threat = memory.strongest("threat") if memory else None
            if threat and safety_pressure > best_score:
                threat_data = threat.get("data", {}) if isinstance(threat.get("data"), dict) else {}
                threat_source_eid = threat_data.get("source_eid")
                if threat_source_eid is None:
                    threat_source_eid = threat_data.get("offender_eid")
                threat_context = _npc_live_threat_context(
                    self.sim,
                    eid,
                    pos,
                    target_eid=threat_source_eid,
                    memory=memory,
                    needs=needs,
                    traits=traits,
                    vitality=vitality,
                    suppression=suppression,
                    max_steps=5,
                )
                retreat_target = (threat_context or {}).get("retreat_target")
                if retreat_target and retreat_target != (int(pos.x), int(pos.y), int(pos.z)):
                    best_intent = "seeking_safety"
                    best_score = safety_pressure
                    best_target = retreat_target
                    best_target_eid = threat_source_eid

            seek_medical_aid = _effective_behavior_value(
                self.sim,
                eid,
                BEHAVIOR_SEEK_MEDICAL_AID,
                traits=traits,
                needs=needs,
                vitality=vitality,
            )
            medical_tip_data = medical_tip.get("data", {}) if isinstance(medical_tip, dict) else {}
            medical_tip_strength = float(medical_tip.get("strength", 0.0) or 0.0) if isinstance(medical_tip, dict) else 0.0
            medical_tip_property_id = str(medical_tip_data.get("property_id", "") or "").strip() if isinstance(medical_tip_data, dict) else ""
            hidden_clinic_tip_data = hidden_clinic_tip.get("data", {}) if isinstance(hidden_clinic_tip, dict) else {}
            hidden_clinic_tip_strength = float(hidden_clinic_tip.get("strength", 0.0) or 0.0) if isinstance(hidden_clinic_tip, dict) else 0.0
            hidden_clinic_property_id = str(hidden_clinic_tip_data.get("property_id", "") or "").strip() if isinstance(hidden_clinic_tip_data, dict) else ""
            for property_id, lead_kind, service_id in (
                (medical_tip_property_id, "medical", "medical"),
                (hidden_clinic_property_id, "medical", "medical"),
            ):
                prop = self.sim.properties.get(property_id) if property_id else None
                focus = _property_focus_position(prop) if isinstance(prop, dict) else None
                if isinstance(focus, (tuple, list)) and len(focus) >= 3:
                    _remember_opportunity_lead(
                        self.sim,
                        eid,
                        lead_kind,
                        {
                            "property_id": property_id,
                            "property_name": str(prop.get("name", property_id)).strip() or property_id,
                            "target": (int(focus[0]), int(focus[1]), int(focus[2])),
                            "chunk": self.sim.chunk_coords(int(focus[0]), int(focus[1])) if hasattr(self.sim, "chunk_coords") else None,
                            "confidence": 0.72,
                            "service_id": service_id,
                            "opportunity_tag": lead_kind,
                            "verification_required": True,
                        },
                        source_kind="behavior_tip",
                        stale_after_ticks=180,
                        expires_ticks=540,
                    )
            if seek_medical_aid >= 0.08 or medical_tip is not None or hidden_clinic_tip is not None:
                medical_target = _find_medical_aid_target(
                    self.sim,
                    eid,
                    pos,
                    preferred_property_id=medical_tip_property_id or None,
                    preferred_score_bonus=18.0 * medical_tip_strength,
                )
                hidden_clinic_target = None
                if hidden_clinic_property_id:
                    hidden_clinic_target = _find_medical_aid_target(
                        self.sim,
                        eid,
                        pos,
                        preferred_property_id=hidden_clinic_property_id,
                        preferred_score_bonus=22.0 * hidden_clinic_tip_strength,
                    )
                if medical_target:
                    medical_score = float(medical_target.get("score", 0.0) or 0.0) * (
                        0.4 + (seek_medical_aid * 0.9)
                    )
                    if medical_tip_property_id and medical_target.get("property_id") == medical_tip_property_id:
                        medical_score += 10.0 + (medical_tip_strength * 22.0)
                    if ai.state == "seeking_medical_aid" and ai.target == medical_target.get("target"):
                        medical_score += 4.0
                    if medical_score > best_score:
                        best_intent = "seeking_medical_aid"
                        best_score = medical_score
                        best_target = medical_target["target"]
                        best_target_eid = None
                if hidden_clinic_target:
                    hidden_clinic_score = float(hidden_clinic_target.get("score", 0.0) or 0.0) * (
                        0.42 + (seek_medical_aid * 0.92)
                    )
                    if hidden_clinic_property_id and hidden_clinic_target.get("property_id") == hidden_clinic_property_id:
                        hidden_clinic_score += 12.0 + (hidden_clinic_tip_strength * 24.0)
                    if ai.state == "seeking_medical_aid" and ai.target == hidden_clinic_target.get("target"):
                        hidden_clinic_score += 4.0
                    if hidden_clinic_score > best_score:
                        medical_target = hidden_clinic_target
                        best_intent = "seeking_medical_aid"
                        best_score = hidden_clinic_score
                        best_target = hidden_clinic_target["target"]
                        best_target_eid = None

            seek_shelter = _effective_behavior_value(
                self.sim,
                eid,
                BEHAVIOR_SEEK_SHELTER,
                traits=traits,
                needs=needs,
                vitality=vitality,
            )
            shelter_tip_data = shelter_tip.get("data", {}) if isinstance(shelter_tip, dict) else {}
            shelter_tip_strength = float(shelter_tip.get("strength", 0.0) or 0.0) if isinstance(shelter_tip, dict) else 0.0
            shelter_tip_property_id = str(shelter_tip_data.get("property_id", "") or "").strip() if isinstance(shelter_tip_data, dict) else ""
            shelter_prop = self.sim.properties.get(shelter_tip_property_id) if shelter_tip_property_id else None
            shelter_focus = _property_focus_position(shelter_prop) if isinstance(shelter_prop, dict) else None
            if isinstance(shelter_focus, (tuple, list)) and len(shelter_focus) >= 3:
                _remember_opportunity_lead(
                    self.sim,
                    eid,
                    "lodging",
                    {
                        "property_id": shelter_tip_property_id,
                        "property_name": str(shelter_prop.get("name", shelter_tip_property_id)).strip() or shelter_tip_property_id,
                        "target": (int(shelter_focus[0]), int(shelter_focus[1]), int(shelter_focus[2])),
                        "chunk": self.sim.chunk_coords(int(shelter_focus[0]), int(shelter_focus[1])) if hasattr(self.sim, "chunk_coords") else None,
                        "confidence": 0.7,
                        "service_id": "shelter",
                        "opportunity_tag": "lodging",
                        "verification_required": True,
                    },
                    source_kind="behavior_tip",
                    stale_after_ticks=180,
                    expires_ticks=540,
                )
            if seek_shelter >= 0.08 or shelter_tip is not None:
                shelter_target = _find_lodging_target(
                    self.sim,
                    eid,
                    pos,
                    preferred_property_id=shelter_tip_property_id or None,
                    preferred_score_bonus=16.0 * shelter_tip_strength,
                )
                if shelter_target:
                    shelter_score = float(shelter_target.get("score", 0.0) or 0.0) * (
                        0.4 + (seek_shelter * 0.92)
                    )
                    if shelter_tip_property_id and shelter_target.get("property_id") == shelter_tip_property_id:
                        shelter_score += 9.0 + (shelter_tip_strength * 20.0)
                    if ai.state == "seeking_shelter" and ai.target == shelter_target.get("target"):
                        shelter_score += 4.0
                    if routine and getattr(routine, "home", None):
                        shelter_score *= 0.8
                    if shelter_score > best_score:
                        best_intent = "seeking_shelter"
                        best_score = shelter_score
                        best_target = shelter_target["target"]
                        best_target_eid = None

            if isinstance(shelter_target, dict):
                safe_spot_share = {
                    "property_id": shelter_target.get("property_id"),
                    "property_name": shelter_target.get("property_name"),
                    "target": shelter_target.get("target"),
                    "service": shelter_target.get("service"),
                    "safe_kind": "lodging",
                    "score": float(shelter_target.get("score", 0.0) or 0.0),
                }
            if isinstance(medical_target, dict):
                medical_safe_score = float(medical_target.get("score", 0.0) or 0.0)
                if safe_spot_share is None or medical_safe_score > float(safe_spot_share.get("score", 0.0) or 0.0):
                    safe_spot_share = {
                        "property_id": medical_target.get("property_id"),
                        "property_name": medical_target.get("property_name"),
                        "target": medical_target.get("target"),
                        "service": "medical",
                        "safe_kind": "medical",
                        "score": medical_safe_score,
                    }

            safe_spot_tip_data = safe_spot_tip.get("data", {}) if isinstance(safe_spot_tip, dict) else {}
            safe_spot_tip_strength = float(safe_spot_tip.get("strength", 0.0) or 0.0) if isinstance(safe_spot_tip, dict) else 0.0
            if safe_spot_tip is not None:
                safe_spot_target = _find_tipped_safe_spot_target(self.sim, eid, pos, safe_spot_tip_data)
                if safe_spot_target:
                    live_heat = _behavior_live_street_heat(self.sim, eid)
                    safe_spot_intent = "seeking_safe_spot"
                    safe_kind = str(safe_spot_target.get("safe_kind", "") or "").strip().lower()
                    if safe_kind == "medical":
                        safe_spot_intent = "seeking_medical_aid"
                    elif safe_kind == "lodging" and live_heat < 0.12:
                        safe_spot_intent = "seeking_shelter"
                    safe_spot_score = float(safe_spot_target.get("score", 0.0) or 0.0)
                    safe_spot_score += safe_spot_tip_strength * 28.0
                    safe_spot_score += live_heat * 20.0
                    if ai.state == safe_spot_intent and ai.target == safe_spot_target.get("target"):
                        safe_spot_score += 4.0
                    if safe_spot_score > best_score:
                        best_intent = safe_spot_intent
                        best_score = safe_spot_score
                        best_target = safe_spot_target["target"]
                        best_target_eid = None

            seek_social_contact = _effective_behavior_value(
                self.sim,
                eid,
                BEHAVIOR_SEEK_SOCIAL_CONTACT,
                traits=traits,
                needs=needs,
            )
            social_pressure = (100.0 - needs.social) * (0.35 + (seek_social_contact * 1.05))
            workplace_prop = _workplace_property(self.sim, occupation=occupation, routine=routine)
            home_prop = _home_property(self.sim, routine=routine)
            current_prop = _property_covering(self.sim, pos.x, pos.y, pos.z)
            work_active = work_shift_active(
                self.sim,
                occupation=occupation,
                workplace_prop=workplace_prop,
                role=ai.role,
            )
            district_type = ""
            world = getattr(self.sim, "world", None)
            if world is not None:
                chunk = world.get_chunk(*self.sim.chunk_coords(pos.x, pos.y))
                district = chunk.get("district", {}) if isinstance(chunk, dict) else {}
                if not isinstance(district, dict):
                    district = {}
                district_type = str(district.get("district_type", "") or "").strip().lower()
            career = str(getattr(occupation, "career", "") or "").strip().lower()

            collect_ground_credits = _effective_behavior_value(
                self.sim,
                eid,
                BEHAVIOR_COLLECT_GROUND_CREDITS,
                traits=traits,
                needs=needs,
            )
            scavenge_loose_items = _effective_behavior_value(
                self.sim,
                eid,
                BEHAVIOR_SCAVENGE_LOOSE_ITEMS,
                traits=traits,
                needs=needs,
            )
            sell_scavenged_items = _effective_behavior_value(
                self.sim,
                eid,
                BEHAVIOR_SELL_SCAVENGED_ITEMS,
                traits=traits,
                needs=needs,
            )
            hidden_trade_tip_data = hidden_trade_tip.get("data", {}) if isinstance(hidden_trade_tip, dict) else {}
            hidden_trade_tip_strength = float(hidden_trade_tip.get("strength", 0.0) or 0.0) if isinstance(hidden_trade_tip, dict) else 0.0
            hidden_trade_property_id = str(hidden_trade_tip_data.get("property_id", "") or "").strip() if isinstance(hidden_trade_tip_data, dict) else ""
            hidden_trade_prop = self.sim.properties.get(hidden_trade_property_id) if hidden_trade_property_id else None
            hidden_trade_focus = _property_focus_position(hidden_trade_prop) if isinstance(hidden_trade_prop, dict) else None
            if isinstance(hidden_trade_focus, (tuple, list)) and len(hidden_trade_focus) >= 3:
                _remember_opportunity_lead(
                    self.sim,
                    eid,
                    "scavenged_sale",
                    {
                        "property_id": hidden_trade_property_id,
                        "property_name": str(hidden_trade_prop.get("name", hidden_trade_property_id)).strip() or hidden_trade_property_id,
                        "target": (int(hidden_trade_focus[0]), int(hidden_trade_focus[1]), int(hidden_trade_focus[2])),
                        "chunk": self.sim.chunk_coords(int(hidden_trade_focus[0]), int(hidden_trade_focus[1])) if hasattr(self.sim, "chunk_coords") else None,
                        "confidence": 0.74,
                        "service_id": "trade_sell",
                        "opportunity_tag": "scavenged_sale",
                        "verification_required": True,
                    },
                    source_kind="behavior_tip",
                    stale_after_ticks=180,
                    expires_ticks=540,
                )
            if collect_ground_credits >= 0.05:
                scavenging_target = _find_ground_credit_target(self.sim, eid, pos)
                if scavenging_target:
                    scavenging_score = float(scavenging_target.get("score", 0.0) or 0.0) * (
                        0.45 + (collect_ground_credits * 0.9)
                    )
                    if work_active:
                        scavenging_score *= 0.55
                    if ai.state == "scavenging" and ai.target == scavenging_target.get("target"):
                        scavenging_score += 4.0
                    if scavenging_score > best_score:
                        best_intent = "scavenging"
                        best_score = scavenging_score
                        best_target = scavenging_target["target"]
                        best_target_eid = None

            if scavenge_loose_items >= 0.05:
                item_target = _find_scavenge_ground_item_target(self.sim, eid, pos)
                if item_target:
                    item_score = float(item_target.get("score", 0.0) or 0.0) * (
                        0.4 + (scavenge_loose_items * 0.95)
                    )
                    if work_active:
                        item_score *= 0.55
                    if ai.state == "scavenging" and ai.target == item_target.get("target"):
                        item_score += 4.0
                    if item_score > best_score:
                        best_intent = "scavenging"
                        best_score = item_score
                        best_target = item_target["target"]
                        best_target_eid = None

            if sell_scavenged_items >= 0.05 or hidden_trade_tip is not None:
                sale_target = _find_scavenged_sale_target(
                    self.sim,
                    eid,
                    pos,
                    preferred_property_id=hidden_trade_property_id or None,
                    preferred_score_bonus=20.0 * hidden_trade_tip_strength,
                )
                if sale_target:
                    sale_score = float(sale_target.get("score", 0.0) or 0.0) * (
                        0.5 + (sell_scavenged_items * 1.15)
                    )
                    if hidden_trade_property_id and sale_target.get("property_id") == hidden_trade_property_id:
                        sale_score += 10.0 + (hidden_trade_tip_strength * 22.0)
                    if work_active and (
                        workplace_prop is not None
                        or (occupation and getattr(occupation, "workplace", None))
                        or (routine and getattr(routine, "work", None))
                    ):
                        sale_score *= 0.6
                    if ai.state == "selling_scavenged" and ai.target == sale_target.get("target"):
                        sale_score += 4.0
                    if sale_score > best_score:
                        best_intent = "selling_scavenged"
                        best_score = sale_score
                        best_target = sale_target["target"]
                        best_target_eid = None

            buy_provisions = _effective_behavior_value(
                self.sim,
                eid,
                BEHAVIOR_BUY_PROVISIONS,
                traits=traits,
                needs=needs,
                vitality=vitality,
            )
            buy_practical_gear = _effective_behavior_value(
                self.sim,
                eid,
                BEHAVIOR_BUY_PRACTICAL_GEAR,
                traits=traits,
                needs=needs,
                vitality=vitality,
            )
            buy_quirky_items = _effective_behavior_value(
                self.sim,
                eid,
                BEHAVIOR_BUY_QUIRKY_ITEMS,
                traits=traits,
                needs=needs,
                vitality=vitality,
            )
            if max(buy_provisions, buy_practical_gear, buy_quirky_items) >= 0.05:
                shopping_target = _find_shopping_target(
                    self.sim,
                    eid,
                    pos,
                    work_active=work_active,
                )
                if shopping_target:
                    motive = str(shopping_target.get("motive", "") or "").strip().lower()
                    motive_bias = {
                        BEHAVIOR_BUY_PROVISIONS: buy_provisions,
                        BEHAVIOR_BUY_PRACTICAL_GEAR: buy_practical_gear,
                        BEHAVIOR_BUY_QUIRKY_ITEMS: buy_quirky_items,
                    }.get(motive, max(buy_provisions, buy_practical_gear, buy_quirky_items))
                    shopping_score = float(shopping_target.get("score", 0.0) or 0.0) * (0.72 + (motive_bias * 0.48))
                    if ai.state == "shopping" and ai.target == shopping_target.get("target"):
                        shopping_score += 5.0
                    if shopping_score > best_score:
                        best_intent = "shopping"
                        best_score = shopping_score
                        best_target = shopping_target["target"]
                        best_target_eid = None
                        best_shopping_target = shopping_target

            street_buy_tip_data = street_buy_tip.get("data", {}) if isinstance(street_buy_tip, dict) else {}
            street_buy_tip_strength = float(street_buy_tip.get("strength", 0.0) or 0.0) if isinstance(street_buy_tip, dict) else 0.0
            if street_buy_tip is not None:
                street_buy_target = _find_tipped_street_buyer_target(
                    self.sim,
                    eid,
                    pos,
                    street_buy_tip_data,
                )
                if street_buy_target:
                    street_buy_score = (
                        float(street_buy_target.get("score", 0.0) or 0.0)
                        + (street_buy_tip_strength * 22.0)
                    )
                    if work_active:
                        street_buy_score *= 0.84
                    if ai.state == "seeking_street_buyer" and ai.target_eid == street_buy_target.get("buyer_eid"):
                        street_buy_score += 4.0
                    if street_buy_score > best_score:
                        best_intent = "seeking_street_buyer"
                        best_score = street_buy_score
                        best_target = street_buy_target["target"]
                        best_target_eid = street_buy_target.get("buyer_eid")

            street_appraise_tip_data = street_appraise_tip.get("data", {}) if isinstance(street_appraise_tip, dict) else {}
            street_appraise_tip_strength = float(street_appraise_tip.get("strength", 0.0) or 0.0) if isinstance(street_appraise_tip, dict) else 0.0
            if street_appraise_tip is not None:
                street_appraise_target = _find_tipped_street_appraiser_target(
                    self.sim,
                    eid,
                    pos,
                    street_appraise_tip_data,
                )
                if street_appraise_target:
                    appraise_score = (
                        float(street_appraise_target.get("score", 0.0) or 0.0)
                        + (street_appraise_tip_strength * 26.0)
                    )
                    if work_active:
                        appraise_score *= 0.86
                    if ai.state == "seeking_street_appraiser" and ai.target_eid == street_appraise_target.get("appraiser_eid"):
                        appraise_score += 4.0
                    if appraise_score > best_score:
                        best_intent = "seeking_street_appraiser"
                        best_score = appraise_score
                        best_target = street_appraise_target["target"]
                        best_target_eid = street_appraise_target.get("appraiser_eid")

            avoid_authorities = _effective_behavior_value(
                self.sim,
                eid,
                BEHAVIOR_AVOID_AUTHORITIES,
                traits=traits,
                needs=needs,
                justice=justices.get(eid),
            )
            heat_tip_data = heat_tip.get("data", {}) if isinstance(heat_tip, dict) else {}
            heat_tip_strength = float(heat_tip.get("strength", 0.0) or 0.0) if isinstance(heat_tip, dict) else 0.0
            if avoid_authorities >= 0.08 or heat_tip is not None:
                inventory_heat = _inventory_contraband_heat(self.sim, eid)
                street_heat = max(
                    _actor_behavior_value(self.sim, eid, BEHAVIOR_BUY_DESIRED_DRUG, 0.0),
                    _actor_behavior_value(self.sim, eid, BEHAVIOR_BUY_PLAYER_GOODS, 0.0),
                    _actor_behavior_value(self.sim, eid, BEHAVIOR_APPRAISE_STREET_GOODS, 0.0) * 0.8,
                )
                authority_heat = max(float(inventory_heat), float(street_heat) * 0.72, heat_tip_strength * 0.62)
                if authority_heat >= 0.12 or heat_tip is not None:
                    avoidance_target = _find_authority_avoidance_target(self.sim, eid, pos)
                    if avoidance_target is None and isinstance(heat_tip_data, dict):
                        warning_z = int(heat_tip_data.get("z", pos.z) or pos.z)
                        if warning_z == int(pos.z):
                            retreat_target = _retreat_target_from_warning(
                                self.sim,
                                pos,
                                (
                                    int(heat_tip_data.get("x", pos.x) or pos.x),
                                    int(heat_tip_data.get("y", pos.y) or pos.y),
                                    warning_z,
                                ),
                            )
                            if retreat_target:
                                avoidance_target = {
                                    "authority_eid": heat_tip_data.get("authority_eid"),
                                    "authority_pos": (
                                        int(heat_tip_data.get("x", pos.x) or pos.x),
                                        int(heat_tip_data.get("y", pos.y) or pos.y),
                                        warning_z,
                                    ),
                                    "distance": int(_manhattan(pos.x, pos.y, int(heat_tip_data.get("x", pos.x) or pos.x), int(heat_tip_data.get("y", pos.y) or pos.y))),
                                    "score": 12.0 + (heat_tip_strength * 22.0),
                                    "target": retreat_target,
                                }
                    if avoidance_target:
                        avoidance_score = (
                            float(avoidance_target.get("score", 0.0) or 0.0) * (0.35 + (avoid_authorities * 0.95))
                        ) + (authority_heat * 28.0)
                        if heat_tip is not None:
                            # Peer heat warnings should be strong enough to push
                            # suspicious NPCs off their default routine for at
                            # least a short-lived evasive response.
                            avoidance_score += 14.0 + (heat_tip_strength * 18.0) + (authority_heat * 12.0)
                        if ai.state == "evading_authority":
                            avoidance_score += 4.0
                        if avoidance_score > best_score:
                            best_intent = "evading_authority"
                            best_score = avoidance_score
                            best_target = avoidance_target["target"]
                            best_target_eid = avoidance_target.get("authority_eid")

            if drive_state is not None and int(getattr(drive_state, "cooldown_until_tick", 0) or 0) <= int(self.sim.tick):
                planned_behavior = _effective_behavior_value(
                    self.sim,
                    eid,
                    BEHAVIOR_COMMIT_PLANNED_CRIME,
                    traits=traits,
                    needs=needs,
                    vitality=vitality,
                )
                opportunistic_behavior = _effective_behavior_value(
                    self.sim,
                    eid,
                    BEHAVIOR_COMMIT_OPPORTUNISTIC_CRIME,
                    traits=traits,
                    needs=needs,
                    vitality=vitality,
                )
                affiliation_behavior = _effective_behavior_value(
                    self.sim,
                    eid,
                    BEHAVIOR_SEEK_CRIMINAL_AFFILIATION,
                    traits=traits,
                    needs=needs,
                    vitality=vitality,
                )
                active_plan = active_plan_for_actor(self.sim, eid, current_tick=self.sim.tick)
                if isinstance(active_plan, dict):
                    stage = str(active_plan.get("stage", "") or "").strip().lower()
                    if stage in {"forming", "rendezvous"}:
                        property_id = str(active_plan.get("staging_property_id", "") or "").strip()
                    elif stage == "disposing":
                        property_id = str(active_plan.get("disposal_property_id", "") or "").strip() or str(active_plan.get("target_property_id", "") or "").strip()
                    else:
                        property_id = str(active_plan.get("target_property_id", "") or "").strip()
                    target_prop = self.sim.properties.get(property_id) if property_id else None
                    target_focus = _property_focus_position(target_prop) if isinstance(target_prop, dict) else None
                    plan_score = float(getattr(drive_state, "planned_crime_score", 0.0) or 0.0) * (0.35 + (planned_behavior * 0.7))
                    if stage in {"forming", "rendezvous"}:
                        plan_score += 8.0
                        plan_intent = "rendezvousing_crew"
                    else:
                        plan_intent = "committing_property_crime"
                    if target_focus and plan_score > best_score:
                        best_intent = plan_intent
                        best_score = plan_score
                        best_target = target_focus
                        best_target_eid = None
                else:
                    affiliation_target_property_id = str(getattr(drive_state, "current_affiliation_target_property_id", "") or "").strip()
                    affiliation_target_prop = self.sim.properties.get(affiliation_target_property_id) if affiliation_target_property_id else None
                    affiliation_focus = _property_focus_position(affiliation_target_prop) if isinstance(affiliation_target_prop, dict) else None
                    affiliation_score = float(getattr(drive_state, "affiliation_seek_score", 0.0) or 0.0) * (0.4 + (affiliation_behavior * 0.75))
                    if (
                        affiliation_focus
                        and affiliation_score > best_score
                        and float(getattr(drive_state, "pressure", 0.0) or 0.0) >= 0.36
                        and float(getattr(drive_state, "confidence", 0.0) or 0.0) <= 0.68
                    ):
                        best_intent = "seeking_criminal_affiliation"
                        best_score = affiliation_score
                        best_target = affiliation_focus
                        best_target_eid = None

                    crime_x = getattr(drive_state, "current_target_x", None)
                    crime_y = getattr(drive_state, "current_target_y", None)
                    crime_z = getattr(drive_state, "current_target_z", None)
                    if crime_x is not None and crime_y is not None and crime_z is not None:
                        opportunistic_score = float(getattr(drive_state, "opportunistic_crime_score", 0.0) or 0.0) * (
                            0.42 + (opportunistic_behavior * 0.68)
                        )
                        if float(getattr(drive_state, "confidence", 0.0) or 0.0) < 0.46:
                            intent = "casing_target"
                            opportunistic_score *= 0.92
                        else:
                            intent = "committing_property_crime"
                        if opportunistic_score > best_score:
                            best_intent = intent
                            best_score = opportunistic_score
                            best_target = (int(crime_x), int(crime_y), int(crime_z))
                            best_target_eid = None

            street_buy_terms = _street_buy_terms(
                self.sim,
                eid,
                district_type=district_type,
                career=career,
            )
            if street_buy_terms:
                street_buy_share = {
                    "buy_desired_drug": float(street_buy_terms.get("buy_desired_drug", 0.0) or 0.0),
                    "buy_player_goods": float(street_buy_terms.get("buy_player_goods", 0.0) or 0.0),
                    "desired_item_id": str(street_buy_terms.get("desired_item_id", "") or "").strip().lower(),
                }
            appraise_caps = _street_appraise_capabilities(self.sim, eid)
            if appraise_caps:
                street_appraise_share = {
                    "identify_strength": float(appraise_caps.get("identify_strength", 0.0) or 0.0),
                    "appraise_strength": float(appraise_caps.get("appraise_strength", 0.0) or 0.0),
                }

            if (
                player_eid is not None
                and player_eid != eid
                and player_pos is not None
                and int(player_pos.z) == int(pos.z)
                and not dialog_open
                and int(dialog_cooldowns.get(eid, 0) or 0) <= int(self.sim.tick)
            ):
                pending_dialogue = _peek_npc_initiated_dialogue(self.sim, eid)
                if isinstance(pending_dialogue, dict):
                    try:
                        dialog_radius = max(2, int(pending_dialogue.get("radius", 6) or 6))
                    except (TypeError, ValueError):
                        dialog_radius = 6
                    distance = _manhattan(pos.x, pos.y, player_pos.x, player_pos.y)
                    if distance <= dialog_radius:
                        solicitation_score = 24.0 + (max(0, dialog_radius + 1 - distance) * 3.6)
                        if ai.state == "soliciting_player" and ai.target_eid == player_eid:
                            solicitation_score += 6.0
                        if solicitation_score > best_score:
                            best_intent = "soliciting_player"
                            best_score = solicitation_score
                            best_target = (player_pos.x, player_pos.y, player_pos.z)
                            best_target_eid = player_eid

                street_buy_profile = _street_buy_interest_profile(
                    self.sim,
                    eid,
                    player_eid,
                    district_type=district_type,
                    career=career,
                )
                if street_buy_profile:
                    initiate_dialogue = _effective_behavior_value(
                        self.sim,
                        eid,
                        BEHAVIOR_INITIATE_DIALOGUE,
                        traits=traits,
                        needs=needs,
                    )
                    desired_name = str(street_buy_profile.get("desired_name", "") or "").strip()
                    player_has_match = bool(street_buy_profile.get("player_has_match"))
                    player_has_desired = bool(street_buy_profile.get("player_has_desired"))
                    has_reason = bool(
                        desired_name
                        or player_has_match
                        or player_has_desired
                        or float(street_buy_profile.get("buy_player_goods", 0.0) or 0.0) >= 0.3
                    )
                    dialogue_radius = int(max(
                        2,
                        _behavior_preference(self.sim, eid, "initiate_dialogue_radius", 5) or 5,
                    ))
                    if not player_has_match and not player_has_desired:
                        dialogue_radius = min(dialogue_radius, 3)
                    distance = _manhattan(pos.x, pos.y, player_pos.x, player_pos.y)
                    if has_reason and initiate_dialogue >= 0.08 and distance <= dialogue_radius:
                        solicitation_score = (
                            16.0
                            + (initiate_dialogue * 34.0)
                            + (float(street_buy_profile.get("buy_desired_drug", 0.0) or 0.0) * 18.0)
                            + (float(street_buy_profile.get("buy_player_goods", 0.0) or 0.0) * 12.0)
                            + max(0.0, (dialogue_radius + 1 - distance) * 3.5)
                        )
                        if player_has_desired:
                            solicitation_score += 26.0
                        elif player_has_match:
                            solicitation_score += 16.0
                        elif desired_name:
                            solicitation_score += 8.0
                        if work_active:
                            solicitation_score *= 0.82
                        if ai.state == "soliciting_player" and ai.target_eid == player_eid:
                            solicitation_score += 5.0
                        if solicitation_score > best_score:
                            best_intent = "soliciting_player"
                            best_score = solicitation_score
                            best_target = (player_pos.x, player_pos.y, player_pos.z)
                            best_target_eid = player_eid

            if social and social_pressure > best_score:
                bond_eid = social.strongest_bond(min_closeness=0.35)
                bond_pos = positions.get(bond_eid)
                if bond_pos and bond_pos.z == pos.z:
                    best_intent = "seeking_social"
                    best_score = social_pressure
                    best_target = (bond_pos.x, bond_pos.y, bond_pos.z)
                    best_target_eid = bond_eid

            energy_pressure = (100.0 - needs.energy) * (0.8 + (traits.discipline * 0.25))
            if routine and routine.home and energy_pressure > best_score:
                hx, hy, hz = routine.home
                if hz == pos.z:
                    best_intent = "resting"
                    best_score = energy_pressure
                    best_target = routine.home
                    best_target_eid = None

            raw_hunger = getattr(needs, "hunger", 100.0)
            raw_thirst = getattr(needs, "thirst", 100.0)
            hunger_value = float(raw_hunger if raw_hunger is not None else 100.0)
            thirst_value = float(raw_thirst if raw_thirst is not None else 100.0)
            nutrition_need = ""
            nutrition_pressure = 0.0
            if hunger_value < 55.0 or thirst_value < 55.0:
                hunger_gap = max(0.0, 60.0 - hunger_value)
                thirst_gap = max(0.0, 60.0 - thirst_value)
                nutrition_pressure = max(hunger_gap * 0.82, thirst_gap * 0.96)
                if hunger_value < 30.0 or thirst_value < 30.0:
                    nutrition_pressure += 18.0
                nutrition_need = "thirst" if thirst_gap >= hunger_gap else "hunger"
            social_venue_pressure = (100.0 - needs.social) * (0.3 + (seek_social_contact * 0.95))
            venue_pressure = max(social_venue_pressure, nutrition_pressure)
            nutrition_breaks_work = hunger_value < 30.0 or thirst_value < 30.0
            if (not work_active or nutrition_breaks_work) and venue_pressure > best_score:
                own_prop_id = None
                if occupation and isinstance(getattr(occupation, "workplace", None), dict):
                    own_prop_id = occupation.workplace.get("property_id")
                if ai.state == "socializing" and ai.target is not None:
                    best_intent = "socializing"
                    best_score = venue_pressure
                    best_target = ai.target
                    best_target_eid = None
                else:
                    _sv_prop, _sv_focus = _pick_social_venue(
                        self.sim, pos.x, pos.y, pos.z, eid,
                        own_prop_id=own_prop_id,
                        nutrition=nutrition_need,
                    )
                    if _sv_focus:
                        needs.social = _clamp(needs.social + 0.15)
                        best_intent = "socializing"
                        best_score = venue_pressure
                        best_target = _sv_focus
                        best_target_eid = None

            # scoring_anchor: used only for the "how far from duty" distance bonus.
            # duty_anchor:    fixed patrol target (guards/scouts only).
            # roam_prop/roam_intent: property to roam freely (workers/civilians/home).
            duty_anchor = None
            roam_prop = None
            roam_intent = None
            scoring_anchor = None
            if workplace_prop and work_active:
                scoring_anchor = _property_focus_position(workplace_prop)
                if ai.role not in {"guard", "scout"}:
                    roam_prop = workplace_prop
                    roam_intent = "working"
                else:
                    duty_anchor = scoring_anchor
            elif routine and routine.work and work_active:
                scoring_anchor = routine.work
                duty_anchor = routine.work
            elif home_prop:
                scoring_anchor = _property_focus_position(home_prop)
                roam_prop = home_prop
                roam_intent = "lounging"
            elif routine and routine.home:
                scoring_anchor = routine.home
                duty_anchor = routine.home

            if not scoring_anchor and not roam_prop and occupation and occupation.workplace:
                property_id = occupation.workplace.get("property_id")
                _fb_prop = self.sim.properties.get(property_id) if property_id else None
                if _fb_prop:
                    scoring_anchor = _property_focus_position(_fb_prop)
                    duty_anchor = scoring_anchor

            follow_duty = _effective_behavior_value(
                self.sim,
                eid,
                BEHAVIOR_FOLLOW_DUTY,
                traits=traits,
                needs=needs,
            )
            duty_score = follow_duty * 45.0
            _sa = scoring_anchor or duty_anchor
            if _sa and follow_duty >= 0.08:
                ax, ay, az = _sa
                if az == pos.z:
                    duty_score += min(20.0, _manhattan(pos.x, pos.y, ax, ay) * 2.5)
                    if duty_score > best_score:
                        if roam_prop and roam_intent:
                            # Keep in-progress roam target; only pick a new tile when
                            # NPCInvestigateSystem cleared it on arrival.
                            if ai.state == roam_intent and ai.target is not None:
                                best_intent = roam_intent
                                best_score = duty_score
                                best_target = ai.target
                                best_target_eid = None
                            else:
                                roam_tile = _pick_property_roam_tile(
                                    self.sim,
                                    roam_prop,
                                    eid,
                                    role=ai.role,
                                    intent=roam_intent,
                                )
                                best_intent = roam_intent
                                best_score = duty_score
                                best_target = roam_tile or scoring_anchor
                                best_target_eid = None
                        else:
                            best_intent = "patrolling"
                            best_score = duty_score
                            best_target = duty_anchor
                            best_target_eid = None

            if best_intent == "idle":
                self._set_intent(eid, ai, will, "idle", 0.0, None, None)
            else:
                self._set_intent(
                    eid,
                    ai,
                    will,
                    best_intent,
                    best_score,
                    best_target,
                    best_target_eid,
                )
            if best_intent == "shopping" and isinstance(best_shopping_target, dict):
                ai.shopping_property_id = best_shopping_target.get("property_id")
                ai.shopping_item_id = best_shopping_target.get("item_id")
                ai.shopping_motive = best_shopping_target.get("motive")
                ai.shopping_quirk_id = best_shopping_target.get("quirk_id")
                ai.shopping_impulse = bool(best_shopping_target.get("impulse", False))
            elif str(getattr(ai, "state", "") or "").strip().lower() != "shopping":
                for attr in ("shopping_property_id", "shopping_item_id", "shopping_motive", "shopping_quirk_id", "shopping_impulse"):
                    if hasattr(ai, attr):
                        delattr(ai, attr)
            if live_timeskip_active and best_intent == "idle":
                _schedule_will_rethink(
                    self.sim,
                    eid,
                    current_tick=self.sim.tick,
                    delay_ticks=30,
                )

            queued_tips = _plan_behavior_tip_shares(
                self.sim,
                eid,
                pos,
                best_intent,
                medical_target=medical_target,
                shelter_target=shelter_target,
                avoidance_target=avoidance_target,
                safe_spot_share=None,
                street_buy_share=street_buy_share,
                street_appraise_share=street_appraise_share,
                cooldowns=tip_cooldowns,
                tick=self.sim.tick,
            )
            for queued_tip in queued_tips:
                queued_tip["source_eid"] = int(eid)
                pending_behavior_tips.append(queued_tip)
            hidden_contact_tips = _plan_hidden_contact_referral_shares(
                self.sim,
                eid,
                pos,
                current_prop=current_prop,
                workplace_prop=workplace_prop,
                home_prop=home_prop,
                occupation=occupation,
                cooldowns=tip_cooldowns,
                tick=self.sim.tick,
            )
            for hidden_tip in hidden_contact_tips:
                hidden_tip["source_eid"] = int(eid)
                pending_behavior_tips.append(hidden_tip)
            if best_intent in {"seeking_shelter", "seeking_medical_aid", "evading_authority"} and isinstance(safe_spot_share, dict):
                safe_tips = _plan_behavior_tip_shares(
                    self.sim,
                    eid,
                    pos,
                    "seeking_safe_spot",
                    safe_spot_share=safe_spot_share,
                    cooldowns=tip_cooldowns,
                    tick=self.sim.tick,
                )
                for safe_tip in safe_tips:
                    safe_tip["source_eid"] = int(eid)
                    pending_behavior_tips.append(safe_tip)

        _apply_behavior_tip_shares(
            self.sim,
            pending_behavior_tips,
            cooldowns=tip_cooldowns,
            tick=self.sim.tick,
        )

class NPCInvestigateSystem(System):

    COMMUTE_STATES = {
        "working",
        "lounging",
        "socializing",
        "shopping",
        "resting",
        "patrolling",
    }
    COMMUTE_VEHICLE_RADIUS = 5
    COMMUTE_OWNED_VEHICLE_RADIUS = 14
    COMMUTE_MIN_TARGET_DISTANCE = 7
    COMMUTE_ROUTE_STOP_MIN_DISTANCE = 5
    COMMUTE_ROUTE_STOP_MAX_DISTANCE = 10
    COMMUTE_ROUTE_STOP_RADIUS = COMMUTE_ROUTE_STOP_MAX_DISTANCE

    DEFAULT_MOVE_COOLDOWNS = {
        "investigating": 2,
        "protecting": 1,
        "helping_victim": 1,
        "reporting_incident": 2,
        "warning": 1,
        "ejecting_target": 1,
        "leaving_property": 1,
        "chasing": 1,
        "scavenging": 2,
        "selling_scavenged": 2,
        "casing_target": 2,
        "committing_property_crime": 2,
        "rendezvousing_crew": 2,
        "seeking_criminal_affiliation": 2,
        "evading_authority": 1,
        "seeking_street_buyer": 2,
        "seeking_street_appraiser": 2,
        "soliciting_player": 2,
        "following": 1,
        "holding": 1,
        "seeking_social": 2,
        "seeking_companionship": 2,
        "seeking_safety": 1,
        "seeking_medical_aid": 2,
        "seeking_safe_spot": 2,
        "seeking_shelter": 2,
        "patrolling": 3,
        "working": 3,
        "lounging": 4,
        "socializing": 3,
        "shopping": 3,
        "resting": 4,
    }
    MOVING_STATES = {
        "investigating",
        "protecting",
        "helping_victim",
        "reporting_incident",
        "warning",
        "ejecting_target",
        "leaving_property",
        "chasing",
        "scavenging",
        "selling_scavenged",
        "casing_target",
        "committing_property_crime",
        "rendezvousing_crew",
        "seeking_criminal_affiliation",
        "evading_authority",
        "seeking_street_buyer",
        "seeking_street_appraiser",
        "soliciting_player",
        "following",
        "holding",
        "seeking_social",
        "seeking_companionship",
        "seeking_safety",
        "seeking_medical_aid",
        "seeking_safe_spot",
        "seeking_shelter",
        "patrolling",
        "working",
        "lounging",
        "socializing",
        "shopping",
        "resting",
    }
    BONUS_MOVE_STATES = {
        "chasing",
        "protecting",
        "ejecting_target",
        "leaving_property",
        "seeking_safety",
        "reporting_incident",
        "helping_victim",
        "warning",
        "evading_authority",
    }

    def __init__(self, sim):
        super().__init__(sim)
        self.sim.events.subscribe("noise", self.on_noise)
        self.sim.events.subscribe("npc_intent_changed", self.on_npc_intent_changed)
        self.next_move_tick = {}
        self._live_timeskip_stride_phase = 0
        self._move_due_by_tick = {}
        self._move_due_membership = {}
        self._urgent_move_eids = set()
        self._live_no_path_cache = {}

    def _live_timeskip_active(self):
        state = getattr(self.sim, "live_timeskip", None)
        return isinstance(state, dict) and bool(state.get("active"))

    def _try_bonus_move_step(self, eid, ai, *, target, positions, noise_profiles, vehicle_step=False):
        if vehicle_step:
            return False
        if str(getattr(ai, "state", "") or "").strip().lower() not in self.BONUS_MOVE_STATES:
            return False
        if not bonus_move_available(self.sim, eid):
            return False
        pos = positions.get(eid)
        if not pos:
            return False
        try:
            tx, ty, tz = int(target[0]), int(target[1]), int(target[2])
        except (TypeError, ValueError, IndexError):
            return False
        if int(pos.z) != tz:
            return False
        if int(pos.x) == tx and int(pos.y) == ty:
            return False
        step = _path_next_step(
            self.sim,
            eid,
            sx=int(pos.x),
            sy=int(pos.y),
            tx=tx,
            ty=ty,
            z=int(pos.z),
            max_nodes=256,
        )
        if not step:
            return False
        spend_bonus_move(self.sim, eid, source="npc_move")
        origin_x = int(pos.x)
        origin_y = int(pos.y)
        origin_z = int(pos.z)
        moved, _blocked_reason = try_move_entity(
            self.sim,
            eid=eid,
            new_x=int(step[0]),
            new_y=int(step[1]),
            new_z=int(pos.z),
            reason="npc_bonus_step",
        )
        if not moved:
            return False
        profile = noise_profiles.get(eid)
        noise_radius = int(max(1, getattr(profile, "move_radius", 4)))
        self.sim.emit(Event(
            "noise",
            source_eid=eid,
            x=int(pos.x),
            y=int(pos.y),
            z=int(pos.z),
            radius=noise_radius,
            cause="move",
        ))
        _emit_move_access_events(
            self.sim,
            eid=eid,
            action="move",
            origin_x=origin_x,
            origin_y=origin_y,
            origin_z=origin_z,
            target_x=int(pos.x),
            target_y=int(pos.y),
            target_z=int(pos.z),
            emit_clear_offense=False,
        )
        return True

    def _normalize_due_tick(self, value):
        try:
            return max(0, int(value))
        except (TypeError, ValueError):
            return 0

    def _schedule_move_due(self, eid, due_tick):
        try:
            eid = int(eid)
        except (TypeError, ValueError):
            return None
        due_tick = self._normalize_due_tick(due_tick)
        old_tick = self._move_due_membership.get(eid)
        if old_tick == due_tick:
            return due_tick
        if old_tick is not None:
            old_bucket = self._move_due_by_tick.get(old_tick)
            if isinstance(old_bucket, set):
                old_bucket.discard(eid)
                if not old_bucket:
                    self._move_due_by_tick.pop(old_tick, None)
        self._move_due_by_tick.setdefault(due_tick, set()).add(eid)
        self._move_due_membership[eid] = due_tick
        delay = max(0, int(due_tick) - int(getattr(self.sim, "tick", 0) or 0))
        _schedule_actor_due(self.sim, eid, "move", delay_ticks=delay, reason="npc_move")
        return due_tick

    def _unschedule_move_due(self, eid):
        try:
            eid = int(eid)
        except (TypeError, ValueError):
            return False
        old_tick = self._move_due_membership.pop(eid, None)
        if old_tick is None:
            return False
        bucket = self._move_due_by_tick.get(old_tick)
        if isinstance(bucket, set):
            bucket.discard(eid)
            if not bucket:
                self._move_due_by_tick.pop(old_tick, None)
        self._urgent_move_eids.discard(eid)
        self._live_no_path_cache.pop(eid, None)
        _clear_actor_attention(self.sim, eid, family="move")
        return True

    def _live_no_path_signature(self, eid, ai, pos, target):
        if ai is None or pos is None or target is None:
            return None
        try:
            tx, ty, tz = target
        except (TypeError, ValueError):
            return None
        return (
            str(getattr(ai, "state", "") or "").strip().lower(),
            int(getattr(pos, "x", 0)),
            int(getattr(pos, "y", 0)),
            int(getattr(pos, "z", 0)),
            int(tx),
            int(ty),
            int(tz),
            getattr(ai, "target_eid", None),
        )

    def _live_no_path_cached(self, eid, ai, pos, target):
        if not self._live_timeskip_active():
            return False
        signature = self._live_no_path_signature(eid, ai, pos, target)
        if signature is None:
            return False
        cached = self._live_no_path_cache.get(int(eid))
        if not isinstance(cached, dict):
            return False
        if cached.get("signature") != signature:
            self._live_no_path_cache.pop(int(eid), None)
            return False
        return int(getattr(self.sim, "tick", 0) or 0) < int(cached.get("until_tick", 0) or 0)

    def _note_live_no_path(self, eid, ai, pos, target, *, delay_ticks=30):
        if not self._live_timeskip_active():
            return
        signature = self._live_no_path_signature(eid, ai, pos, target)
        if signature is None:
            return
        self._live_no_path_cache[int(eid)] = {
            "signature": signature,
            "until_tick": int(getattr(self.sim, "tick", 0) or 0) + int(max(1, delay_ticks)),
        }

    def _clear_live_no_path(self, eid):
        try:
            self._live_no_path_cache.pop(int(eid), None)
        except (TypeError, ValueError):
            return

    def _current_next_move_tick(self, eid, throttle):
        if throttle is not None:
            return self._normalize_due_tick(getattr(throttle, "next_move_tick", 0))
        return self._normalize_due_tick(self.next_move_tick.get(eid, 0))

    def _resync_live_move_due(self, ais, positions, move_throttles):
        if not self._live_timeskip_active():
            self._move_due_by_tick.clear()
            self._move_due_membership.clear()
            self._urgent_move_eids.clear()
            return
        for eid, ai in tuple(ais.items()):
            state = str(getattr(ai, "state", "") or "").strip().lower()
            if state not in self.MOVING_STATES or positions.get(eid) is None:
                self._unschedule_move_due(eid)
                continue
            if getattr(ai, "target", None) is None and getattr(ai, "target_eid", None) is None:
                self._unschedule_move_due(eid)
                continue
            next_tick = self._current_next_move_tick(eid, move_throttles.get(eid))
            self._schedule_move_due(eid, next_tick)

    def _pop_due_move_eids(self):
        tick = self._normalize_due_tick(getattr(self.sim, "tick", 0))
        ready = set()
        for due_tick in sorted(raw for raw in self._move_due_by_tick.keys() if int(raw) <= tick):
            bucket = self._move_due_by_tick.pop(due_tick, set())
            for eid in tuple(bucket or ()):
                if self._move_due_membership.get(eid) == due_tick:
                    self._move_due_membership.pop(eid, None)
                ready.add(eid)
        ready.update(_pop_due_actors(self.sim, "move", current_tick=tick))
        return ready

    def on_npc_intent_changed(self, event):
        data = getattr(event, "data", {}) or {}
        npc_eid = data.get("npc_eid")
        try:
            npc_eid = int(npc_eid)
        except (TypeError, ValueError):
            return
        intent = str(data.get("intent", "") or "").strip().lower()
        if intent in self.MOVING_STATES:
            routine_defer = self._live_timeskip_active() and intent in {
                "lounging",
                "patrolling",
                "resting",
                "scavenging",
                "seeking_companionship",
                "seeking_social",
                "selling_scavenged",
                "socializing",
                "working",
            }
            if routine_defer:
                self._schedule_move_due(npc_eid, int(getattr(self.sim, "tick", 0) or 0) + 120)
            else:
                self._urgent_move_eids.add(npc_eid)
                _mark_actor_urgent(self.sim, npc_eid, family="move", reason=f"intent:{intent}", ttl_ticks=12)
                if intent in NPCWillSystem.LIVE_TIMESKIP_URGENT_STATES:
                    _mark_actor_urgent(self.sim, npc_eid, family="will", reason=f"intent:{intent}", ttl_ticks=12)
                self._schedule_move_due(npc_eid, getattr(self.sim, "tick", 0))
        else:
            self._unschedule_move_due(npc_eid)

    def on_noise(self, event):
        source_eid = event.data["source_eid"]
        nx = event.data["x"]
        ny = event.data["y"]
        nz = event.data["z"]
        radius = event.data["radius"]
        cause = event.data.get("cause")

        ais = self.sim.ecs.get(AI)
        positions = self.sim.ecs.get(Position)
        needs_map = self.sim.ecs.get(NPCNeeds)
        routines = self.sim.ecs.get(NPCRoutine)
        wills = self.sim.ecs.get(NPCWill)
        wildlife_behaviors = self.sim.ecs.get(WildlifeBehavior)
        vehicle_states = self.sim.ecs.get(VehicleState)

        for eid, ai in ais.items():
            if eid == source_eid:
                continue
            if _entity_is_downed(self.sim, eid):
                _apply_downed_actor_state(self.sim, eid, tick=self.sim.tick)
                continue

            pos = positions.get(eid)
            if not pos or pos.z != nz:
                continue

            if _manhattan(pos.x, pos.y, nx, ny) > radius:
                continue

            if str(getattr(ai, "role", "") or "").strip().lower() == "wildlife":
                behavior = wildlife_behaviors.get(eid)
                if not behavior or str(cause or "").strip().lower() in QUIET_NOISE_CAUSES:
                    continue
                if _wildlife_damage_reaction_blocks_noise(self.sim, eid, source_eid=source_eid, cause=cause):
                    continue
                escape_target = _pick_wildlife_escape_target(
                    self.sim,
                    pos,
                    (nx, ny, nz),
                    routines.get(eid),
                    behavior,
                )
                if not escape_target:
                    continue
                needs = needs_map.get(eid)
                if needs:
                    needs.safety = _clamp(needs.safety - 4.5)
                _sync_ai_intent(
                    ai,
                    wills.get(eid),
                    self.sim.tick,
                    "seeking_safety",
                    score=82.0,
                    target=escape_target,
                    target_eid=None,
                )
                self._urgent_move_eids.add(int(eid))
                _mark_actor_urgent(self.sim, eid, family="move", reason="noise:wildlife", ttl_ticks=12)
                _mark_actor_urgent(self.sim, eid, family="will", reason="noise:wildlife", ttl_ticks=12)
                self._schedule_move_due(eid, getattr(self.sim, "tick", 0))
                continue

            vehicle_state = vehicle_states.get(eid)
            if (
                vehicle_state is not None
                and bool(getattr(vehicle_state, "in_vehicle", False))
                and str(cause or "").strip().lower() in {"move", "vehicle_move"}
            ):
                continue

            if not _noise_merits_attention(self.sim, eid, source_eid, nx, ny, nz, cause):
                continue

            state = str(getattr(ai, "state", "") or "").strip().lower()
            will = wills.get(eid)
            intent = str(getattr(will, "intent", "") or "").strip().lower() if will is not None else ""
            if (
                state in NOISE_INTERRUPT_PROTECTED_STATES
                or intent in NOISE_INTERRUPT_PROTECTED_STATES
                or _actor_in_live_combat(self.sim, eid)
            ):
                continue

            ai.state = "investigating"
            ai.target = (nx, ny, nz)
            ai.target_eid = None
            self._urgent_move_eids.add(int(eid))
            _mark_actor_urgent(self.sim, eid, family="move", reason="noise", ttl_ticks=12)
            _mark_actor_urgent(self.sim, eid, family="will", reason="noise", ttl_ticks=12)
            self._schedule_move_due(eid, getattr(self.sim, "tick", 0))

            self.sim.emit(Event(
                "npc_investigate",
                npc_eid=eid,
                source_eid=source_eid,
                x=nx,
                y=ny,
                z=nz,
                cause=cause,
                target_eid=event.data.get("target_eid"),
            ))

    def _move_actor_position_direct(self, eid, pos, target):
        if pos is None or not isinstance(target, (tuple, list)) or len(target) < 3:
            return False
        try:
            nx, ny, nz = int(target[0]), int(target[1]), int(target[2])
        except (TypeError, ValueError):
            return False
        if not self.sim.tilemap.in_bounds(nx, ny):
            return False
        self.sim.tilemap.move_entity(
            eid,
            oldx=int(pos.x),
            oldy=int(pos.y),
            oldz=int(pos.z),
            newx=nx,
            newy=ny,
            newz=nz,
        )
        pos.x = nx
        pos.y = ny
        pos.z = nz
        return True

    def _finish_compact_movement(self, eid, ai, kind, *, target=None):
        ai.state = "idle"
        ai.target = None
        ai.target_eid = None
        if hasattr(ai, "incident_id") and kind in {"reporting_incident", "helping_victim", "warning"}:
            ai.incident_id = None
        _clear_opportunity_active_target(self.sim, eid, kind)
        _clear_actor_attention(self.sim, eid, family="move")
        _schedule_actor_due(self.sim, eid, "will", delay_ticks=0, reason=f"compact:{kind}")
        _schedule_will_rethink(self.sim, eid, current_tick=getattr(self.sim, "tick", 0), delay_ticks=0)
        _note_attention_resolution(self.sim, "compressed", kind, compact=True)
        self.sim.emit(Event(
            "npc_compact_movement_resolved",
            npc_eid=int(eid),
            resolution=str(kind),
            x=int(target[0]) if isinstance(target, (tuple, list)) and len(target) >= 1 else None,
            y=int(target[1]) if isinstance(target, (tuple, list)) and len(target) >= 2 else None,
            z=int(target[2]) if isinstance(target, (tuple, list)) and len(target) >= 3 else None,
        ))

    def _compact_resolve_offscreen_movement(
        self,
        eid,
        ai,
        pos,
        target,
        *,
        memories,
        needs_map,
        traits_map,
        vitalities,
        suppressions,
    ):
        if not self._live_timeskip_active():
            return False
        scope_info = _attention_scope_for_actor(self.sim, eid, pos=pos, ai=ai)
        scope = str((scope_info or {}).get("scope", "") or "").strip().lower()
        if scope != "compressed":
            return False
        if pos is None or not isinstance(target, (tuple, list)) or len(target) < 3:
            return False
        try:
            tx, ty, tz = int(target[0]), int(target[1]), int(target[2])
        except (TypeError, ValueError):
            return False
        if int(pos.z) != tz:
            return False
        state = str(getattr(ai, "state", "") or "").strip().lower()

        if state == "seeking_safety":
            live_threat = _npc_live_threat_context(
                self.sim,
                eid,
                pos,
                target_eid=ai.target_eid,
                memory=memories.get(eid),
                needs=needs_map.get(eid),
                traits=traits_map.get(eid) or NPCTraits(),
                vitality=vitalities.get(eid),
                suppression=suppressions.get(eid),
                max_steps=5,
            )
            if live_threat:
                return False
            needs = needs_map.get(eid)
            if needs:
                needs.safety = _clamp(float(getattr(needs, "safety", 70.0) or 70.0) + 6.0)
                if float(getattr(needs, "energy", 100.0) or 100.0) <= 55.0:
                    needs.energy = _clamp(float(getattr(needs, "energy", 70.0) or 70.0) + 2.0)
            ai.state = "resting" if needs and float(getattr(needs, "energy", 100.0) or 100.0) <= 62.0 else "idle"
            ai.target = None
            ai.target_eid = None
            _clear_actor_attention(self.sim, eid, family="move")
            _schedule_actor_due(self.sim, eid, "will", delay_ticks=6, reason="compact:safety_settled")
            _schedule_will_rethink(self.sim, eid, current_tick=getattr(self.sim, "tick", 0), delay_ticks=6)
            _note_attention_resolution(self.sim, "compressed", "seeking_safety", compact=True)
            self.sim.emit(Event(
                "npc_compact_movement_resolved",
                npc_eid=int(eid),
                resolution="seeking_safety",
                x=int(pos.x),
                y=int(pos.y),
                z=int(pos.z),
            ))
            return True

        if state in {"reporting_incident", "helping_victim", "warning", "ejecting_target", "leaving_property"}:
            if not self._move_actor_position_direct(eid, pos, (tx, ty, tz)):
                return False
            if state == "reporting_incident":
                self.sim.emit(Event(
                    "npc_report_arrived",
                    npc_eid=eid,
                    incident_id=getattr(ai, "incident_id", None),
                    x=tx,
                    y=ty,
                    z=tz,
                    compressed=True,
                ))
            elif state == "helping_victim":
                self.sim.emit(Event(
                    "npc_help_arrived",
                    npc_eid=eid,
                    incident_id=getattr(ai, "incident_id", None),
                    target_eid=ai.target_eid,
                    x=tx,
                    y=ty,
                    z=tz,
                    compressed=True,
                ))
            elif state == "warning":
                self.sim.emit(Event(
                    "npc_warning_arrived",
                    npc_eid=eid,
                    incident_id=getattr(ai, "incident_id", None),
                    x=tx,
                    y=ty,
                    z=tz,
                    compressed=True,
                ))
            self._finish_compact_movement(eid, ai, state, target=(tx, ty, tz))
            return True

        if state in {"seeking_medical_aid", "seeking_safe_spot", "seeking_shelter"}:
            if not self._move_actor_position_direct(eid, pos, (tx, ty, tz)):
                return False
            if state == "seeking_medical_aid":
                _receive_medical_aid_at_actor(self.sim, eid, pos)
            elif state == "seeking_safe_spot":
                _receive_safe_spot_at_actor(self.sim, eid, pos)
            else:
                _receive_lodging_at_actor(self.sim, eid, pos)
            self._finish_compact_movement(eid, ai, state, target=(tx, ty, tz))
            return True

        return False

    def _defer_compressed_routine_movement(self, eid, ai, pos):
        if not self._live_timeskip_active() or pos is None:
            return False
        state = str(getattr(ai, "state", "") or "").strip().lower()
        if state not in {
            "lounging",
            "patrolling",
            "resting",
            "scavenging",
            "seeking_companionship",
            "seeking_social",
            "selling_scavenged",
            "socializing",
            "working",
        }:
            return False
        scope_info = _attention_scope_for_actor(self.sim, eid, pos=pos, ai=ai)
        if str((scope_info or {}).get("scope", "") or "").strip().lower() != "compressed":
            return False
        self._schedule_move_due(eid, int(getattr(self.sim, "tick", 0) or 0) + 120)
        return True

    def _npc_vehicle_should_miss_turn(self, eid, pos, vehicle_prop, *, speed=0, turning=False):
        forced = getattr(self.sim, "npc_vehicle_force_crash_eids", set())
        if isinstance(forced, (set, frozenset, list, tuple)) and eid in forced:
            return True
        try:
            override = getattr(self.sim, "npc_vehicle_crash_chance_override")
        except AttributeError:
            override = None
        if override is not None:
            try:
                chance = max(0.0, min(1.0, float(override)))
            except (TypeError, ValueError):
                chance = 0.0
        else:
            profile = _vehicle_profile_from_property(vehicle_prop) or {}
            durability = max(1, min(10, _int_or_default(profile.get("durability"), 5)))
            speed = max(0, int(speed or 0))
            chance = 0.0008 + (0.0010 * max(0, speed - 1))
            if turning:
                chance += 0.0025
            if durability <= 4:
                chance += (5 - durability) * 0.001
        if chance <= 0.0:
            return False
        roll = random.Random(
            f"{getattr(self.sim, 'seed', 0)}:npc_vehicle_miss:{int(eid)}:{int(getattr(self.sim, 'tick', 0))}:{int(getattr(pos, 'x', 0))}:{int(getattr(pos, 'y', 0))}"
        ).random()
        return roll < chance

    def _clear_npc_vehicle_commute(self, ai):
        for attr in (
            "vehicle_commute_phase",
            "vehicle_commute_vehicle_id",
            "vehicle_commute_final_target",
            "vehicle_commute_route_target",
            "vehicle_commute_original_state",
            "vehicle_commute_started_tick",
        ):
            if hasattr(ai, attr):
                delattr(ai, attr)

    def _exit_npc_vehicle_at_position(self, eid, pos):
        state = self.sim.ecs.get(VehicleState).get(eid)
        if state is None or not bool(getattr(state, "in_vehicle", False)):
            return None
        vehicle_id = str(getattr(state, "active_vehicle_id", "") or "").strip()
        vehicle_prop = _active_vehicle_property_for_state(self.sim, state)
        _set_vehicle_speed(state, 0, tick=getattr(self.sim, "tick", 0))
        state.set_in_vehicle(False, tick=getattr(self.sim, "tick", 0))
        if _property_is_vehicle(vehicle_prop) and pos is not None:
            _sync_vehicle_property_position(self.sim, vehicle_prop, int(pos.x), int(pos.y), int(pos.z))
            vehicle_id = str(vehicle_prop.get("id", vehicle_id) or vehicle_id)
        return vehicle_id or None

    def _abandon_npc_vehicle_commute(self, eid, ai, pos, *, reason="abandoned"):
        if pos is None:
            return False
        vehicle_id = str(getattr(ai, "vehicle_commute_vehicle_id", "") or "").strip()
        active_vehicle_id = self._exit_npc_vehicle_at_position(eid, pos)
        if active_vehicle_id:
            vehicle_id = active_vehicle_id

        final_target = self._tuple3(getattr(ai, "vehicle_commute_final_target", None))
        if final_target is None:
            final_target = self._tuple3(getattr(ai, "target", None))
        original_state = str(getattr(ai, "vehicle_commute_original_state", "") or "").strip().lower()
        self._clear_npc_vehicle_commute(ai)

        if final_target is not None and int(final_target[2]) == int(pos.z) and (
            int(final_target[0]) != int(pos.x) or int(final_target[1]) != int(pos.y)
        ):
            ai.state = original_state or "patrolling"
            ai.target = final_target
        else:
            ai.state = "idle"
            ai.target = None
        ai.target_eid = None

        self.sim.emit(Event(
            "npc_vehicle_commute_abandoned",
            npc_eid=int(eid),
            vehicle_id=vehicle_id or None,
            reason=str(reason or "abandoned"),
            final_target=final_target,
            x=int(pos.x),
            y=int(pos.y),
            z=int(pos.z),
        ))
        return True

    def _invalid_vehicle_occupancy_reason(self, eid, ai, pos):
        state = self.sim.ecs.get(VehicleState).get(eid)
        if state is None or not bool(getattr(state, "in_vehicle", False)):
            return ""
        state_name = str(getattr(ai, "state", "") or "").strip().lower()
        phase = str(getattr(ai, "vehicle_commute_phase", "") or "").strip().lower()
        if state_name in {"holding", "lounging", "resting", "socializing", "seeking_social", "seeking_companionship"}:
            return f"{state_name}_in_vehicle"
        if state_name not in self.MOVING_STATES:
            return "idle_in_vehicle"
        target = self._tuple3(_resolve_ai_target(self.sim, ai))
        if target is None or int(target[2]) != int(pos.z):
            return "vehicle_without_destination"
        if phase != "drive" and int(target[0]) == int(pos.x) and int(target[1]) == int(pos.y):
            return "vehicle_at_destination"
        vehicle_prop = _active_vehicle_property_for_state(self.sim, state)
        if not _property_is_vehicle(vehicle_prop):
            return "missing_vehicle"
        fuel, _capacity = _vehicle_fuel_values(vehicle_prop)
        if int(fuel) <= 0:
            return "out_of_fuel"
        metadata = _property_metadata(vehicle_prop)
        medium = str(metadata.get("vehicle_medium", metadata.get("medium", getattr(state, "medium", "land"))) or "land").strip().lower()
        if medium != "land":
            return "unsupported_vehicle_medium"
        vehicle_id = str(vehicle_prop.get("id", "") or "").strip()
        if not _vehicle_route_accessible_at(
            self.sim,
            int(pos.x),
            int(pos.y),
            int(pos.z),
            ignore_property_id=vehicle_id or None,
            medium="land",
        ):
            return "route_required"
        return ""

    def _tuple3(self, value):
        if not isinstance(value, (tuple, list)) or len(value) < 3:
            return None
        try:
            return int(value[0]), int(value[1]), int(value[2])
        except (TypeError, ValueError):
            return None

    def _vehicle_position_tuple(self, prop):
        if not _property_is_vehicle(prop):
            return None
        try:
            return int(prop.get("x", 0)), int(prop.get("y", 0)), int(prop.get("z", 0))
        except (TypeError, ValueError):
            return None

    def _vehicle_commute_owner_kind(self, eid, vehicle_prop):
        if not _property_is_vehicle(vehicle_prop):
            return None
        owner_eid = vehicle_prop.get("owner_eid")
        metadata = _property_metadata(vehicle_prop)
        assigned_eid = metadata.get("npc_commute_driver_eid")
        if owner_eid not in {None, "", 0}:
            try:
                if int(owner_eid) != int(eid):
                    return None
                return "owned"
            except (TypeError, ValueError):
                return None
        elif assigned_eid not in {None, "", 0}:
            try:
                if int(assigned_eid) != int(eid):
                    return None
                return "owned"
            except (TypeError, ValueError):
                return None
        owner_tag = str(vehicle_prop.get("owner_tag", metadata.get("vehicle_owner_tag", "")) or "").strip().lower()
        if owner_tag in {"player", "justice", "police", "npc"}:
            return None
        if owner_tag in {"", "public", "private", "unowned", "none", "neutral", "city"}:
            return "unowned"
        return None

    def _vehicle_commute_usable_for(self, eid, vehicle_prop, pos, *, allow_unowned=False):
        if not _property_is_vehicle(vehicle_prop) or pos is None:
            return False
        owner_kind = self._vehicle_commute_owner_kind(eid, vehicle_prop)
        if owner_kind is None or (owner_kind == "unowned" and not allow_unowned):
            return False
        vehicle_pos = self._vehicle_position_tuple(vehicle_prop)
        if vehicle_pos is None or int(vehicle_pos[2]) != int(pos.z):
            return False
        metadata = _property_metadata(vehicle_prop)
        medium = str(metadata.get("vehicle_medium", metadata.get("medium", "land")) or "land").strip().lower()
        if medium != "land":
            return False
        fuel, _capacity = _vehicle_fuel_values(vehicle_prop)
        if int(fuel) <= 0 or _vehicle_top_speed(vehicle_prop) <= 0:
            return False
        vehicle_id = str(vehicle_prop.get("id", "") or "").strip()
        return _vehicle_route_accessible_at(
            self.sim,
            vehicle_pos[0],
            vehicle_pos[1],
            vehicle_pos[2],
            ignore_property_id=vehicle_id,
            medium="land",
        )

    def _claim_commute_vehicle_for(self, eid, vehicle_prop):
        if self._vehicle_commute_owner_kind(eid, vehicle_prop) != "unowned":
            return False
        vehicle_id = str((vehicle_prop or {}).get("id", "") or "").strip()
        if not vehicle_id:
            return False
        vehicle_prop["owner_eid"] = int(eid)
        vehicle_prop["owner_tag"] = "npc"
        self.sim.property_registry_dirty = True
        metadata = _property_metadata(vehicle_prop)
        metadata["vehicle_owner_tag"] = "npc"
        metadata["npc_commute_driver_eid"] = int(eid)
        metadata["npc_commute_vehicle"] = True
        return True

    def _commute_vehicle_candidates(self, eid, pos):
        ids = set()
        portfolio = self.sim.ecs.get(PropertyPortfolio).get(eid)
        if portfolio is not None:
            ids.update(str(raw).strip() for raw in tuple(getattr(portfolio, "owned_property_ids", ()) or ()) if str(raw).strip())
        state = self.sim.ecs.get(VehicleState).get(eid)
        if state is not None:
            for raw in (getattr(state, "active_vehicle_id", None), getattr(state, "last_vehicle_id", None)):
                if str(raw or "").strip():
                    ids.add(str(raw).strip())

        rows = []
        seen = set()
        for property_id in ids:
            prop = self.sim.properties.get(property_id)
            if not self._vehicle_commute_usable_for(eid, prop, pos):
                continue
            vehicle_pos = self._vehicle_position_tuple(prop)
            if vehicle_pos is None:
                continue
            distance = _manhattan(int(pos.x), int(pos.y), vehicle_pos[0], vehicle_pos[1])
            if distance > self.COMMUTE_OWNED_VEHICLE_RADIUS:
                continue
            rows.append((0, int(distance), str(prop.get("name", "") or ""), str(prop.get("id", "") or ""), prop, False))
            seen.add(str(prop.get("id", "") or ""))

        for prop in self.sim.properties.values():
            if not _property_is_vehicle(prop):
                continue
            prop_id = str(prop.get("id", "") or "").strip()
            if not prop_id or prop_id in seen:
                continue
            owner_kind = self._vehicle_commute_owner_kind(eid, prop)
            if owner_kind == "owned":
                allow_unowned = False
                max_distance = self.COMMUTE_OWNED_VEHICLE_RADIUS
                priority = 0
                claim = False
            elif owner_kind == "unowned":
                allow_unowned = True
                max_distance = self.COMMUTE_VEHICLE_RADIUS
                priority = 1
                claim = True
            else:
                continue
            if not self._vehicle_commute_usable_for(eid, prop, pos, allow_unowned=allow_unowned):
                continue
            vehicle_pos = self._vehicle_position_tuple(prop)
            if vehicle_pos is None:
                continue
            distance = _manhattan(int(pos.x), int(pos.y), vehicle_pos[0], vehicle_pos[1])
            if distance <= max_distance:
                rows.append((priority, int(distance), str(prop.get("name", "") or ""), prop_id, prop, claim))
        rows.sort()
        return [(row[-2], bool(row[-1])) for row in rows]

    def _route_tile_clear_for_commute(self, x, y, z, *, vehicle_id="", driver_eid=None):
        if not _vehicle_route_accessible_at(
            self.sim,
            int(x),
            int(y),
            int(z),
            ignore_property_id=str(vehicle_id or "").strip() or None,
            medium="land",
        ):
            return False
        occupants = set(self.sim.tilemap.entities_at(int(x), int(y), int(z)) or ())
        if driver_eid is not None:
            try:
                occupants.discard(int(driver_eid))
            except (TypeError, ValueError):
                pass
        return not occupants

    def _vehicle_route_next_step(self, eid, start, goal, vehicle_id, *, max_nodes=384):
        start = self._tuple3(start)
        goal = self._tuple3(goal)
        if start is None or goal is None or int(start[2]) != int(goal[2]):
            return None
        if start[:2] == goal[:2]:
            return None
        z = int(start[2])
        if not self._route_tile_clear_for_commute(start[0], start[1], z, vehicle_id=vehicle_id, driver_eid=eid):
            return None
        if not self._route_tile_clear_for_commute(goal[0], goal[1], z, vehicle_id=vehicle_id, driver_eid=eid):
            return None

        start2 = (int(start[0]), int(start[1]))
        goal2 = (int(goal[0]), int(goal[1]))
        parents = {start2: None}
        queue = [start2]
        index = 0
        best = start2
        best_distance = _manhattan(start2[0], start2[1], goal2[0], goal2[1])
        while index < len(queue) and len(parents) < int(max_nodes):
            cx, cy = queue[index]
            index += 1
            if (cx, cy) == goal2:
                best = goal2
                break
            for dx, dy in ((0, -1), (1, 0), (0, 1), (-1, 0)):
                nx = cx + dx
                ny = cy + dy
                node = (nx, ny)
                if node in parents:
                    continue
                if not self._route_tile_clear_for_commute(nx, ny, z, vehicle_id=vehicle_id, driver_eid=eid):
                    continue
                parents[node] = (cx, cy)
                queue.append(node)
                distance = _manhattan(nx, ny, goal2[0], goal2[1])
                if distance < best_distance:
                    best = node
                    best_distance = distance
        if best == start2:
            return None
        cursor = best
        while parents.get(cursor) is not None and parents[cursor] != start2:
            cursor = parents[cursor]
        return cursor

    def _route_stop_near_target(self, eid, start, final_target, vehicle_id):
        start = self._tuple3(start)
        final_target = self._tuple3(final_target)
        if start is None or final_target is None or int(start[2]) != int(final_target[2]):
            return None
        fx, fy, fz = final_target
        candidates = []
        min_stop = max(1, int(self.COMMUTE_ROUTE_STOP_MIN_DISTANCE))
        max_stop = max(min_stop, int(self.COMMUTE_ROUTE_STOP_MAX_DISTANCE))
        for walk_distance in range(min_stop, max_stop + 1):
            ring_candidates = []
            for dx in range(-walk_distance, walk_distance + 1):
                dy_abs = walk_distance - abs(dx)
                dy_values = (0,) if dy_abs == 0 else (-dy_abs, dy_abs)
                for dy in dy_values:
                    if abs(dx) + abs(dy) != walk_distance:
                        continue
                    x = int(fx) + dx
                    y = int(fy) + dy
                    if not self._route_tile_clear_for_commute(x, y, fz, vehicle_id=vehicle_id, driver_eid=eid):
                        continue
                    if self._vehicle_route_next_step(eid, start, (x, y, fz), vehicle_id) is None and (int(start[0]), int(start[1])) != (x, y):
                        continue
                    drive_distance = _manhattan(int(start[0]), int(start[1]), x, y)
                    ring_candidates.append((int(walk_distance), -int(drive_distance), int(x), int(y), int(fz)))
            if ring_candidates:
                candidates.extend(ring_candidates)
                break
        if not candidates:
            return None
        candidates.sort()
        return candidates[0][2], candidates[0][3], candidates[0][4]

    def _maybe_start_vehicle_commute(self, eid, ai, pos, target, *, routine_path_state=False):
        if getattr(ai, "vehicle_commute_phase", None):
            return None
        state_name = str(getattr(ai, "state", "") or "").strip().lower()
        if state_name not in self.COMMUTE_STATES or not routine_path_state:
            return None
        target = self._tuple3(target)
        if target is None or int(target[2]) != int(pos.z):
            return None
        if _manhattan(int(pos.x), int(pos.y), target[0], target[1]) < self.COMMUTE_MIN_TARGET_DISTANCE:
            return None
        vehicle_state = self.sim.ecs.get(VehicleState).get(eid)
        if vehicle_state is not None and bool(getattr(vehicle_state, "in_vehicle", False)):
            return None
        if _should_block_solo_vehicle_for_partner(self.sim, eid, target):
            return None

        for vehicle_prop, claim_vehicle in self._commute_vehicle_candidates(eid, pos):
            vehicle_pos = self._vehicle_position_tuple(vehicle_prop)
            if vehicle_pos is None:
                continue
            vehicle_id = str(vehicle_prop.get("id", "") or "").strip()
            route_stop = self._route_stop_near_target(eid, vehicle_pos, target, vehicle_id)
            if route_stop is None:
                continue
            if claim_vehicle and not self._claim_commute_vehicle_for(eid, vehicle_prop):
                continue
            ai.vehicle_commute_phase = "walk_to_vehicle"
            ai.vehicle_commute_vehicle_id = vehicle_id
            ai.vehicle_commute_final_target = target
            ai.vehicle_commute_route_target = route_stop
            ai.vehicle_commute_original_state = state_name
            ai.vehicle_commute_started_tick = int(getattr(self.sim, "tick", 0) or 0)
            ai.target = vehicle_pos
            ai.target_eid = None
            self.sim.emit(Event(
                "npc_vehicle_commute_started",
                npc_eid=int(eid),
                vehicle_id=vehicle_id,
                final_target=target,
                route_target=route_stop,
                x=int(pos.x),
                y=int(pos.y),
                z=int(pos.z),
            ))
            return vehicle_pos
        return None

    def _maybe_enter_commute_vehicle(self, eid, ai, pos):
        if str(getattr(ai, "vehicle_commute_phase", "") or "").strip().lower() != "walk_to_vehicle":
            return False
        vehicle_id = str(getattr(ai, "vehicle_commute_vehicle_id", "") or "").strip()
        vehicle_prop = self.sim.properties.get(vehicle_id)
        if not self._vehicle_commute_usable_for(eid, vehicle_prop, pos):
            self._abandon_npc_vehicle_commute(eid, ai, pos, reason="vehicle_unusable_before_entry")
            return False
        vehicle_pos = self._vehicle_position_tuple(vehicle_prop)
        route_target = self._tuple3(getattr(ai, "vehicle_commute_route_target", None))
        final_target = self._tuple3(getattr(ai, "vehicle_commute_final_target", None))
        if vehicle_pos is None or route_target is None or final_target is None:
            self._abandon_npc_vehicle_commute(eid, ai, pos, reason="missing_commute_target")
            return False
        if (int(pos.x), int(pos.y), int(pos.z)) != vehicle_pos:
            return False
        state = self.sim.ecs.get(VehicleState).get(eid)
        if state is None:
            state = VehicleState()
            self.sim.ecs.add(eid, state)
        state.set_active_vehicle(vehicle_id, tick=getattr(self.sim, "tick", 0))
        state.set_in_vehicle(True, tick=getattr(self.sim, "tick", 0))
        dx = 1 if route_target[0] > int(pos.x) else -1 if route_target[0] < int(pos.x) else 0
        dy = 1 if route_target[1] > int(pos.y) else -1 if route_target[1] < int(pos.y) else 0
        state.set_heading(dx, dy, tick=getattr(self.sim, "tick", 0))
        ai.vehicle_commute_phase = "drive"
        ai.target = route_target
        ai.target_eid = None
        self.sim.emit(Event(
            "npc_vehicle_commute_entered",
            npc_eid=int(eid),
            vehicle_id=vehicle_id,
            final_target=final_target,
            route_target=route_target,
            x=int(pos.x),
            y=int(pos.y),
            z=int(pos.z),
        ))
        return True

    def _maybe_finish_vehicle_commute_drive(self, eid, ai, pos):
        if str(getattr(ai, "vehicle_commute_phase", "") or "").strip().lower() != "drive":
            return False
        route_target = self._tuple3(getattr(ai, "vehicle_commute_route_target", None))
        final_target = self._tuple3(getattr(ai, "vehicle_commute_final_target", None))
        if route_target is None or final_target is None:
            self._abandon_npc_vehicle_commute(eid, ai, pos, reason="missing_commute_target")
            return False
        if (int(pos.x), int(pos.y), int(pos.z)) != route_target:
            return False
        state = self.sim.ecs.get(VehicleState).get(eid)
        if state is not None:
            _set_vehicle_speed(state, 0, tick=getattr(self.sim, "tick", 0))
            state.set_in_vehicle(False, tick=getattr(self.sim, "tick", 0))
            vehicle_prop = _active_vehicle_property_for_state(self.sim, state)
            if _property_is_vehicle(vehicle_prop):
                _sync_vehicle_property_position(self.sim, vehicle_prop, int(pos.x), int(pos.y), int(pos.z))
        vehicle_id = str(getattr(ai, "vehicle_commute_vehicle_id", "") or "").strip()
        original_state = str(getattr(ai, "vehicle_commute_original_state", "") or "").strip().lower()
        self._clear_npc_vehicle_commute(ai)
        ai.state = original_state or "patrolling"
        ai.target = final_target
        ai.target_eid = None
        self.sim.emit(Event(
            "npc_vehicle_commute_parked",
            npc_eid=int(eid),
            vehicle_id=vehicle_id or None,
            final_target=final_target,
            x=int(pos.x),
            y=int(pos.y),
            z=int(pos.z),
        ))
        return True

    def _try_npc_vehicle_route_step(self, eid, pos, step):
        if not step:
            return None
        state = _ensure_vehicle_motion_state(self.sim.ecs.get(VehicleState).get(eid))
        if not state or not bool(getattr(state, "in_vehicle", False)):
            return None
        vehicle_prop = _active_vehicle_property_for_state(self.sim, state)
        if not _property_is_vehicle(vehicle_prop):
            return None

        medium = str(getattr(state, "medium", "land") or "land").strip().lower() or "land"
        if medium != "land":
            return None

        nx, ny = int(step[0]), int(step[1])
        origin_x = int(pos.x)
        origin_y = int(pos.y)
        origin_z = int(pos.z)
        vehicle_id = vehicle_prop.get("id")
        if not _vehicle_route_accessible_at(
            self.sim,
            origin_x,
            origin_y,
            origin_z,
            ignore_property_id=vehicle_id,
            medium="land",
        ):
            _set_vehicle_speed(state, 0, tick=self.sim.tick)
            return False, "route_required", origin_x, origin_y, origin_z
        if not _vehicle_route_accessible_at(
            self.sim,
            nx,
            ny,
            origin_z,
            ignore_property_id=vehicle_id,
            medium="land",
        ):
            _set_vehicle_speed(state, 0, tick=self.sim.tick)
            return False, "route_required", origin_x, origin_y, origin_z

        fuel, fuel_capacity = _vehicle_fuel_values(vehicle_prop)
        if int(fuel) <= 0:
            _set_vehicle_speed(state, 0, tick=self.sim.tick)
            return False, "out_of_fuel", origin_x, origin_y, origin_z

        dx = 1 if nx > origin_x else -1 if nx < origin_x else 0
        dy = 1 if ny > origin_y else -1 if ny < origin_y else 0
        if dx == 0 and dy == 0:
            return False, "blocked_tile", origin_x, origin_y, origin_z

        top_speed = _vehicle_top_speed(vehicle_prop)
        current_speed = _clamp_vehicle_speed(vehicle_prop, getattr(state, "speed", 0))
        _set_vehicle_speed(state, current_speed, tick=self.sim.tick, vehicle_prop=vehicle_prop)
        current_heading = _vehicle_heading_tuple(state)
        desired_heading = (dx, dy)
        turning = current_heading != desired_heading
        if turning and current_speed > 1:
            _set_vehicle_heading(state, dx, dy, tick=self.sim.tick)
            _set_vehicle_speed(state, current_speed - 1, tick=self.sim.tick, vehicle_prop=vehicle_prop)
            self.sim.emit(Event(
                "vehicle_local_controlled",
                eid=eid,
                npc_eid=eid,
                vehicle_id=vehicle_id,
                vehicle_name=_vehicle_label(vehicle_prop),
                action="brake_turn",
                x=origin_x,
                y=origin_y,
                z=origin_z,
                fuel=fuel,
                fuel_capacity=fuel_capacity,
                heading_dx=dx,
                heading_dy=dy,
                heading=_vehicle_heading_label(state),
                speed=int(getattr(state, "speed", 0) or 0),
                top_speed=int(top_speed),
                cruise_active=int(getattr(state, "speed", 0) or 0) > 0,
            ))
            return True, None, origin_x, origin_y, origin_z

        miss_turn = self._npc_vehicle_should_miss_turn(
            eid,
            pos,
            vehicle_prop,
            speed=current_speed,
            turning=turning,
        )
        if not miss_turn:
            _set_vehicle_heading(state, dx, dy, tick=self.sim.tick)
        elif current_speed <= 0:
            _set_vehicle_heading(state, dx, dy, tick=self.sim.tick)

        if current_speed <= 0:
            current_speed = 1
        elif not turning and current_speed < top_speed:
            current_speed += 1
        _set_vehicle_speed(state, current_speed, tick=self.sim.tick, vehicle_prop=vehicle_prop)
        _sync_vehicle_property_position(self.sim, vehicle_prop, origin_x, origin_y, origin_z)
        heading_dx, heading_dy = _vehicle_heading_tuple(state)
        drive_target_x = origin_x + int(heading_dx)
        drive_target_y = origin_y + int(heading_dy)
        moved, blocked_reason = _try_vehicle_step(
            self.sim,
            eid,
            vehicle_prop,
            drive_target_x,
            drive_target_y,
            origin_z,
            speed=max(1, int(getattr(state, "speed", 0) or 0)),
            reason="npc_vehicle_move",
        )
        if not moved:
            _set_vehicle_speed(state, 0, tick=self.sim.tick)
            return False, blocked_reason or "blocked_tile", origin_x, origin_y, origin_z

        self.sim.emit(Event(
            "vehicle_local_moved",
            eid=eid,
            npc_eid=eid,
            vehicle_id=vehicle_id,
            vehicle_name=_vehicle_label(vehicle_prop),
            old_x=origin_x,
            old_y=origin_y,
            old_z=origin_z,
            x=int(pos.x),
            y=int(pos.y),
            z=int(pos.z),
            fuel=fuel,
            fuel_capacity=fuel_capacity,
            heading_dx=heading_dx,
            heading_dy=heading_dy,
            heading=_vehicle_heading_label(state),
            speed=int(getattr(state, "speed", 0) or 0),
            top_speed=int(top_speed),
            cruise_active=int(getattr(state, "speed", 0) or 0) > 0,
            reason="npc_vehicle_move",
        ))
        return True, None, origin_x, origin_y, origin_z

    def update(self):
        ais = self.sim.ecs.get(AI)
        positions = self.sim.ecs.get(Position)
        needs_map = self.sim.ecs.get(NPCNeeds)
        socials = self.sim.ecs.get(NPCSocial)
        move_throttles = self.sim.ecs.get(MovementThrottle)
        wills = self.sim.ecs.get(NPCWill)
        effects_map = self.sim.ecs.get(StatusEffects)
        noise_profiles = self.sim.ecs.get(NoiseProfile)
        memories = self.sim.ecs.get(NPCMemory)
        traits_map = self.sim.ecs.get(NPCTraits)
        weapon_profiles = self.sim.ecs.get(WeaponUseProfile)
        vitalities = self.sim.ecs.get(Vitality)
        suppressions = self.sim.ecs.get(SuppressionState)
        occupations = self.sim.ecs.get(Occupation)
        live_timeskip = getattr(self.sim, "live_timeskip", None)
        live_timeskip_active = isinstance(live_timeskip, dict) and bool(live_timeskip.get("active"))
        global_stride = 1 if live_timeskip_active else int(max(1, getattr(self.sim, "npc_move_tick_stride", 1)))
        stride_phase_tick = int(getattr(self.sim, "tick", 0))
        if live_timeskip_active and global_stride > 1:
            stride_phase_tick = int(self._live_timeskip_stride_phase)
            self._live_timeskip_stride_phase = (int(self._live_timeskip_stride_phase) + 1) % global_stride
        elif not live_timeskip_active:
            self._live_timeskip_stride_phase = 0
        player_eid = getattr(self.sim, "player_eid", None)
        player_pos = positions.get(player_eid)
        dialog_cooldowns = getattr(self.sim, "npc_dialogue_cooldowns", None)
        if not isinstance(dialog_cooldowns, dict):
            dialog_cooldowns = {}
            self.sim.npc_dialogue_cooldowns = dialog_cooldowns

        _refresh_actor_attention(self.sim, player_eid=player_eid)
        if live_timeskip_active:
            candidate_eids = self._pop_due_move_eids()
            candidate_eids.update(self._urgent_move_eids)
            self._urgent_move_eids.clear()
            ai_items = [(eid, ais[eid]) for eid in sorted(candidate_eids) if eid in ais]
        else:
            ai_items = tuple(ais.items())

        for eid, ai in ai_items:
            pos = positions.get(eid)
            if not pos:
                if live_timeskip_active:
                    self._unschedule_move_due(eid)
                continue
            if _entity_is_downed(self.sim, eid):
                _apply_downed_actor_state(self.sim, eid, tick=self.sim.tick)
                if live_timeskip_active:
                    self._unschedule_move_due(eid)
                continue
            if _actor_is_active_street_trade_contact(self.sim, eid):
                throttle = move_throttles.get(eid)
                next_tick = int(self.sim.tick) + 1
                if throttle:
                    throttle.next_move_tick = max(int(getattr(throttle, "next_move_tick", 0) or 0), next_tick)
                else:
                    self.next_move_tick[eid] = max(self.next_move_tick.get(eid, 0), next_tick)
                if live_timeskip_active:
                    self._schedule_move_due(eid, next_tick)
                continue
            invalid_vehicle_reason = self._invalid_vehicle_occupancy_reason(eid, ai, pos)
            if invalid_vehicle_reason:
                self._abandon_npc_vehicle_commute(eid, ai, pos, reason=invalid_vehicle_reason)
                throttle = move_throttles.get(eid)
                if throttle:
                    throttle.next_move_tick = max(int(getattr(throttle, "next_move_tick", 0) or 0), int(self.sim.tick) + 1)
                else:
                    self.next_move_tick[eid] = max(self.next_move_tick.get(eid, 0), int(self.sim.tick) + 1)
                if live_timeskip_active:
                    self._schedule_move_due(eid, int(getattr(self.sim, "tick", 0)) + 1)
                continue
            if ai.state not in self.MOVING_STATES:
                if live_timeskip_active:
                    self._unschedule_move_due(eid)
                continue
            if local_interactions_suspended_for_actor(self.sim, getattr(ai, "target_eid", None)):
                ai.state = "idle"
                ai.target = None
                ai.target_eid = None
                will = wills.get(eid)
                if will is not None:
                    will.intent = "idle"
                    will.target = None
                    will.target_eid = None
                if live_timeskip_active:
                    self._unschedule_move_due(eid)
                continue
            throttle = move_throttles.get(eid)
            if control_lapse_active(self.sim, eid):
                if throttle:
                    throttle.next_move_tick = max(throttle.next_move_tick, int(self.sim.tick) + 1)
                else:
                    self.next_move_tick[eid] = max(self.next_move_tick.get(eid, 0), int(self.sim.tick) + 1)
                continue

            if global_stride > 1 and ((stride_phase_tick + eid) % global_stride != 0):
                continue

            if not _detail_tick_allowed(self.sim, pos, eid, coarse_divisor=3):
                if live_timeskip_active:
                    self._schedule_move_due(eid, int(getattr(self.sim, "tick", 0)) + 1)
                continue

            status_speed_mult = _entity_status_move_speed_multiplier(self.sim, eid)

            next_move_tick = throttle.next_move_tick if throttle else self.next_move_tick.get(eid, 0)
            if self.sim.tick < next_move_tick:
                if live_timeskip_active:
                    self._schedule_move_due(eid, next_move_tick)
                continue

            target = _resolve_ai_target(self.sim, ai)
            if not target:
                if live_timeskip_active:
                    self._unschedule_move_due(eid)
                continue

            if self._defer_compressed_routine_movement(eid, ai, pos):
                continue

            tx, ty, tz = target
            threat_focus = None
            quirk_target_override = False
            quirk_action = active_self_protection_action(self.sim, eid, current_tick=self.sim.tick)
            if isinstance(quirk_action, dict) and quirk_action:
                action_name = str(quirk_action.get("action", "") or "").strip().lower()
                try:
                    action_until = int(quirk_action.get("until_tick", 0) or 0)
                except (TypeError, ValueError):
                    action_until = 0
                if action_name in {"freeze", "look_busy"} and action_until > int(self.sim.tick):
                    next_tick = min(action_until, int(self.sim.tick) + 1)
                    if throttle:
                        throttle.next_move_tick = max(int(getattr(throttle, "next_move_tick", 0) or 0), next_tick)
                    else:
                        self.next_move_tick[eid] = max(self.next_move_tick.get(eid, 0), next_tick)
                    if live_timeskip_active:
                        self._schedule_move_due(eid, next_tick)
                    continue
                action_target = quirk_action.get("target")
                if action_name in {"hide_behind_counter", "slip_out_back", "shelter_with_crowd", "stand_ground"} and isinstance(action_target, (tuple, list)) and len(action_target) >= 3:
                    try:
                        ax, ay, az = int(action_target[0]), int(action_target[1]), int(action_target[2])
                    except (TypeError, ValueError):
                        ax = ay = az = None
                    if ax is not None and int(az) == int(pos.z):
                        tx, ty, tz = ax, ay, az
                        quirk_target_override = True
            if ai.state == "protecting" and ai.target_eid is not None:
                threat_focus = _known_threat_position_for_npc(
                    self.sim,
                    eid,
                    pos,
                    target_eid=ai.target_eid,
                    memory=memories.get(eid),
                    radius=12,
                )
                if threat_focus:
                    _loadout, held_weapon, _instance = _weapon_context_for_entity(self.sim, eid)
                    metrics = _npc_combat_metrics(
                        needs=needs_map.get(eid),
                        traits=traits_map.get(eid) or NPCTraits(),
                        vitality=vitalities.get(eid),
                        suppression=suppressions.get(eid),
                        weapon=held_weapon,
                        **_npc_status_metric_args(self.sim, eid),
                    )
                    if not quirk_target_override:
                        tactical_target = _pick_npc_combat_position(
                            self.sim,
                            eid,
                            pos,
                            Position(threat_focus[0], threat_focus[1], threat_focus[2]),
                            weapon=held_weapon,
                            profile=weapon_profiles.get(eid),
                            metrics=metrics,
                            target_eid=ai.target_eid,
                        )
                        if tactical_target:
                            tx = int(tactical_target["x"])
                            ty = int(tactical_target["y"])
                            tz = int(tactical_target["z"])

            if pos.z != tz:
                ai.state = "idle"
                ai.target = None
                ai.target_eid = None
                if live_timeskip_active:
                    self._unschedule_move_due(eid)
                continue

            if self._compact_resolve_offscreen_movement(
                eid,
                ai,
                pos,
                (tx, ty, tz),
                memories=memories,
                needs_map=needs_map,
                traits_map=traits_map,
                vitalities=vitalities,
                suppressions=suppressions,
            ):
                continue

            routine_path_state = ai.state in {
                "selling_scavenged",
                "seeking_medical_aid",
                "seeking_safe_spot",
                "seeking_shelter",
                "patrolling",
                "working",
                "lounging",
                "socializing",
                "shopping",
                "resting",
            }
            commute_target = self._maybe_start_vehicle_commute(
                eid,
                ai,
                pos,
                (tx, ty, tz),
                routine_path_state=routine_path_state,
            )
            if commute_target is not None:
                tx, ty, tz = commute_target

            hold_cooldown = (
                throttle.cooldown_for(ai.state, status_multiplier=status_speed_mult)
                if throttle
                else int(max(1, round(
                    float(max(1, self.DEFAULT_MOVE_COOLDOWNS.get(ai.state, 2))) / status_speed_mult
                )))
            )
            if ai.state == "protecting" and threat_focus and pos.x == tx and pos.y == ty:
                _sync_npc_cover_against_threat(
                    self.sim,
                    eid,
                    pos,
                    threat_focus,
                    tick=self.sim.tick,
                    min_effect=0.16,
                )
                if throttle:
                    throttle.next_move_tick = self.sim.tick + hold_cooldown
                else:
                    self.next_move_tick[eid] = self.sim.tick + hold_cooldown
                continue

            if ai.state == "chasing" and ai.target_eid is not None and _manhattan(pos.x, pos.y, tx, ty) <= 1:
                if throttle:
                    throttle.next_move_tick = self.sim.tick + max(1, hold_cooldown)
                else:
                    self.next_move_tick[eid] = self.sim.tick + max(1, hold_cooldown)
                continue

            if self._maybe_enter_commute_vehicle(eid, ai, pos) or self._maybe_finish_vehicle_commute_drive(eid, ai, pos):
                if throttle:
                    throttle.next_move_tick = self.sim.tick + 1
                else:
                    self.next_move_tick[eid] = self.sim.tick + 1
                continue

            if pos.x == tx and pos.y == ty:
                drive_state = criminal_drive_state(self.sim, eid, create=False)
                if ai.state == "casing_target":
                    if drive_state is not None:
                        drive_state.current_activity_stage = "cased"
                        drive_state.cooldown_until_tick = max(
                            int(self.sim.tick) + 8,
                            int(getattr(drive_state, "cooldown_until_tick", 0) or 0),
                        )
                    ai.state = "idle"
                    ai.target = None
                    ai.target_eid = None
                    plan_key = str(getattr(drive_state, "current_plan_key", "") or "").strip()
                    self.sim.emit(Event(
                        "npc_crime_attempt_resolved",
                        npc_eid=eid,
                        success=False,
                        reason="cased_target",
                        plan_key=plan_key or None,
                        **_crime_plan_event_fields(self.sim, eid, plan_key),
                        x=tx,
                        y=ty,
                        z=tz,
                    ))
                    if throttle:
                        throttle.next_move_tick = self.sim.tick + 1
                    else:
                        self.next_move_tick[eid] = self.sim.tick + 1
                    continue

                if ai.state == "seeking_criminal_affiliation":
                    if drive_state is not None:
                        result = attempt_criminal_affiliation(
                            self.sim,
                            eid,
                            organization_eid=getattr(drive_state, "current_affiliation_organization_eid", None),
                            property_id=getattr(drive_state, "current_affiliation_target_property_id", None),
                            current_tick=self.sim.tick,
                        )
                        success = bool((result or {}).get("accepted"))
                        drive_state.last_affiliation_seek_tick = int(self.sim.tick)
                        drive_state.cooldown_until_tick = int(self.sim.tick) + (24 if success else 40)
                        if not success:
                            drive_state.last_failure_tick = int(self.sim.tick)
                    ai.state = "idle"
                    ai.target = None
                    ai.target_eid = None
                    if throttle:
                        throttle.next_move_tick = self.sim.tick + 1
                    else:
                        self.next_move_tick[eid] = self.sim.tick + 1
                    continue

                if ai.state == "rendezvousing_crew":
                    if drive_state is not None:
                        drive_state.current_activity_stage = "rendezvous"
                    ai.target = (pos.x, pos.y, pos.z)
                    if throttle:
                        throttle.next_move_tick = self.sim.tick + hold_cooldown
                    else:
                        self.next_move_tick[eid] = self.sim.tick + hold_cooldown
                    continue

                if ai.state == "committing_property_crime":
                    item_system = find_registered_item_system(self.sim)
                    ground_item = nearest_target_ground_item(
                        self.sim,
                        getattr(drive_state, "current_target_property_id", None) if drive_state is not None else None,
                        ground_item_id=getattr(drive_state, "current_target_ground_item_id", None) if drive_state is not None else None,
                    )
                    before_ground_id = str((ground_item or {}).get("ground_item_id", "") or "").strip()
                    if item_system is not None and isinstance(ground_item, dict):
                        item_system._handle_pickup(
                            eid,
                            int(ground_item.get("x", pos.x) or pos.x),
                            int(ground_item.get("y", pos.y) or pos.y),
                            int(ground_item.get("z", pos.z) or pos.z),
                        )
                    after_exists = bool(before_ground_id and before_ground_id in getattr(self.sim, "ground_items", {}))
                    if before_ground_id and not after_exists:
                        ai.state = "idle"
                        ai.target = None
                        ai.target_eid = None
                    else:
                        plan_key = str(getattr(drive_state, "current_plan_key", "") or "").strip() if drive_state is not None else ""
                        self.sim.emit(Event(
                            "npc_crime_attempt_resolved",
                            npc_eid=eid,
                            success=False,
                            reason="no_loot",
                            plan_key=plan_key or None,
                            **_crime_plan_event_fields(self.sim, eid, plan_key),
                            x=tx,
                            y=ty,
                            z=tz,
                        ))
                        ai.state = "idle"
                        ai.target = None
                        ai.target_eid = None
                    if throttle:
                        throttle.next_move_tick = self.sim.tick + 1
                    else:
                        self.next_move_tick[eid] = self.sim.tick + 1
                    continue

                if ai.state == "resting":
                    needs = needs_map.get(eid)
                    if needs:
                        needs.energy = _clamp(needs.energy + 0.55)

                if ai.state == "investigating":
                    self.sim.emit(Event("npc_investigation_complete", npc_eid=eid, x=tx, y=ty, z=tz))

                if ai.state == "scavenging":
                    _collect_ground_items_at_actor(self.sim, eid, pos)
                if ai.state == "selling_scavenged":
                    memory = memories.get(eid)
                    hidden_trade_tip = _recent_behavior_tip(memory, BEHAVIOR_TIP_HIDDEN_TRADE, now=self.sim.tick)
                    hidden_trade_tip_data = hidden_trade_tip.get("data", {}) if isinstance(hidden_trade_tip, dict) else {}
                    hidden_trade_property_id = str(hidden_trade_tip_data.get("property_id", "") or "").strip() if isinstance(hidden_trade_tip_data, dict) else ""
                    _sell_scavenged_inventory_at_actor(
                        self.sim,
                        eid,
                        pos,
                        preferred_property_id=hidden_trade_property_id or None,
                    )
                if ai.state == "seeking_street_buyer" and ai.target_eid is not None:
                    buyer_eid = ai.target_eid
                    buyer_pos = positions.get(buyer_eid)
                    if buyer_pos and int(buyer_pos.z) == int(pos.z) and _manhattan(pos.x, pos.y, buyer_pos.x, buyer_pos.y) <= 1:
                        occupation = occupations.get(buyer_eid)
                        career = str(getattr(occupation, "career", "") or "").strip().lower()
                        district_type = ""
                        world = getattr(self.sim, "world", None)
                        if world is not None:
                            chunk = world.get_chunk(*self.sim.chunk_coords(buyer_pos.x, buyer_pos.y))
                            district = chunk.get("district", {}) if isinstance(chunk, dict) else {}
                            if not isinstance(district, dict):
                                district = {}
                            district_type = str(district.get("district_type", "") or "").strip().lower()
                        _resolve_street_buy_between_actors(
                            self.sim,
                            buyer_eid,
                            eid,
                            district_type=district_type,
                            career=career,
                        )
                if ai.state == "seeking_street_appraiser" and ai.target_eid is not None:
                    appraiser_eid = ai.target_eid
                    appraiser_pos = positions.get(appraiser_eid)
                    if appraiser_pos and int(appraiser_pos.z) == int(pos.z) and _manhattan(pos.x, pos.y, appraiser_pos.x, appraiser_pos.y) <= 1:
                        _resolve_street_appraise_between_actors(
                            self.sim,
                            appraiser_eid,
                            eid,
                        )
                if ai.state == "seeking_medical_aid":
                    memory = memories.get(eid)
                    hidden_clinic_tip = _recent_behavior_tip(memory, BEHAVIOR_TIP_HIDDEN_CLINIC, now=self.sim.tick)
                    hidden_clinic_tip_data = hidden_clinic_tip.get("data", {}) if isinstance(hidden_clinic_tip, dict) else {}
                    hidden_clinic_property_id = str(hidden_clinic_tip_data.get("property_id", "") or "").strip() if isinstance(hidden_clinic_tip_data, dict) else ""
                    _receive_medical_aid_at_actor(
                        self.sim,
                        eid,
                        pos,
                        preferred_property_id=hidden_clinic_property_id or None,
                    )
                if ai.state == "seeking_safe_spot":
                    _receive_safe_spot_at_actor(self.sim, eid, pos)
                if ai.state == "seeking_shelter":
                    _receive_lodging_at_actor(self.sim, eid, pos)
                if ai.state == "shopping":
                    _resolve_npc_shopping_at_actor(
                        self.sim,
                        eid,
                        pos,
                        preferred_property_id=getattr(ai, "shopping_property_id", None),
                        preferred_item_id=getattr(ai, "shopping_item_id", None),
                        motive=getattr(ai, "shopping_motive", ""),
                        quirk_id=getattr(ai, "shopping_quirk_id", ""),
                        impulse=bool(getattr(ai, "shopping_impulse", False)),
                    )
                    for attr in ("shopping_property_id", "shopping_item_id", "shopping_motive", "shopping_quirk_id", "shopping_impulse"):
                        if hasattr(ai, attr):
                            delattr(ai, attr)

                if ai.state == "reporting_incident":
                    self.sim.emit(Event(
                        "npc_report_arrived",
                        npc_eid=eid,
                        incident_id=getattr(ai, "incident_id", None),
                        x=tx,
                        y=ty,
                        z=tz,
                    ))

                if ai.state == "helping_victim":
                    self.sim.emit(Event(
                        "npc_help_arrived",
                        npc_eid=eid,
                        incident_id=getattr(ai, "incident_id", None),
                        target_eid=ai.target_eid,
                        x=tx,
                        y=ty,
                        z=tz,
                    ))

                if ai.state == "warning":
                    self.sim.emit(Event(
                        "npc_warning_arrived",
                        npc_eid=eid,
                        incident_id=getattr(ai, "incident_id", None),
                        x=tx,
                        y=ty,
                        z=tz,
                    ))

                if ai.state == "protecting":
                    self.sim.emit(Event("npc_guarding_target", npc_eid=eid, target_eid=ai.target_eid, x=tx, y=ty, z=tz))

                if ai.state == "socializing":
                    arrived_prop = _property_covering(self.sim, tx, ty, tz) or _property_covering(self.sim, pos.x, pos.y, pos.z)
                    if isinstance(arrived_prop, dict) and str(arrived_prop.get("id", "") or "").strip():
                        _receive_nutrition_at_actor(self.sim, eid, pos, prop=arrived_prop)
                        self.sim.emit(Event(
                            "npc_social_venue_visited",
                            npc_eid=eid,
                            property_id=arrived_prop.get("id"),
                            source_eid=eid,
                        ))
                if ai.state == "seeking_safety":
                    memory = memories.get(eid)
                    live_threat = _npc_live_threat_context(
                        self.sim,
                        eid,
                        pos,
                        target_eid=ai.target_eid,
                        memory=memory,
                        needs=needs_map.get(eid),
                        traits=traits_map.get(eid) or NPCTraits(),
                        vitality=vitalities.get(eid),
                        suppression=suppressions.get(eid),
                        max_steps=5,
                    )
                    if live_threat:
                        ai.target = (int(pos.x), int(pos.y), int(pos.z))
                    else:
                        ai.state = "idle"
                        ai.target = None
                        ai.target_eid = None
                elif ai.state in {"working", "lounging", "socializing"}:
                    if ai.state == "working":
                        service_claim = _mark_service_job_claim_arrival(self.sim, eid, pos)
                        if isinstance(service_claim, dict):
                            service_target = _service_job_claim_target(self.sim, service_claim) or (int(pos.x), int(pos.y), int(pos.z))
                            ai.target = service_target
                            ai.target_eid = None
                            will = wills.get(eid)
                            if will is not None:
                                will.intent = "working"
                            _mark_actor_urgent(self.sim, eid, family="move", reason="service_job_waiting", ttl_ticks=18)
                            _mark_actor_urgent(self.sim, eid, family="will", reason="service_job_waiting", ttl_ticks=18)
                            _schedule_actor_due(self.sim, eid, "move", delay_ticks=max(1, hold_cooldown), reason="service_job_waiting")
                            _schedule_actor_due(self.sim, eid, "will", delay_ticks=12, reason="service_job_waiting")
                            if throttle:
                                throttle.next_move_tick = self.sim.tick + max(1, hold_cooldown)
                            else:
                                self.next_move_tick[eid] = self.sim.tick + max(1, hold_cooldown)
                            continue
                    # Arrived at roam tile; clear target so will system picks a new one.
                    _clear_opportunity_active_target(self.sim, eid, ai.state)
                    ai.target = None
                elif ai.state not in {"protecting", "resting", "following", "holding"}:
                    _clear_opportunity_active_target(self.sim, eid, ai.state)
                    ai.state = "idle"
                    ai.target = None
                    ai.target_eid = None
                arrival_cooldown = hold_cooldown if ai.state in {"resting", "protecting", "following", "holding", "seeking_safety"} else 1
                if live_timeskip_active and ai.state == "seeking_safety":
                    arrival_cooldown = max(int(arrival_cooldown), 6)
                if throttle:
                    throttle.next_move_tick = self.sim.tick + arrival_cooldown
                else:
                    self.next_move_tick[eid] = self.sim.tick + arrival_cooldown
                continue

            if ai.state == "working" and _manhattan(pos.x, pos.y, tx, ty) <= 1:
                service_claim = _mark_service_job_claim_arrival(self.sim, eid, pos)
                if isinstance(service_claim, dict):
                    service_target = _service_job_claim_target(self.sim, service_claim) or (int(pos.x), int(pos.y), int(pos.z))
                    ai.target = service_target
                    ai.target_eid = None
                    will = wills.get(eid)
                    if will is not None:
                        will.intent = "working"
                    _mark_actor_urgent(self.sim, eid, family="move", reason="service_job_waiting", ttl_ticks=18)
                    _mark_actor_urgent(self.sim, eid, family="will", reason="service_job_waiting", ttl_ticks=18)
                    _schedule_actor_due(self.sim, eid, "move", delay_ticks=max(1, hold_cooldown), reason="service_job_waiting")
                    _schedule_actor_due(self.sim, eid, "will", delay_ticks=12, reason="service_job_waiting")
                    if throttle:
                        throttle.next_move_tick = self.sim.tick + max(1, hold_cooldown)
                    else:
                        self.next_move_tick[eid] = self.sim.tick + max(1, hold_cooldown)
                    continue

            if ai.state in {"investigating", "seeking_social", "seeking_companionship", "protecting", "reporting_incident", "helping_victim", "warning", "ejecting_target", "leaving_property", "soliciting_player", "seeking_street_buyer", "seeking_street_appraiser"} and _manhattan(pos.x, pos.y, tx, ty) <= 1:
                if ai.state == "reporting_incident":
                    self.sim.emit(Event(
                        "npc_report_arrived",
                        npc_eid=eid,
                        incident_id=getattr(ai, "incident_id", None),
                        x=pos.x,
                        y=pos.y,
                        z=tz,
                    ))
                    if str(ai.state or "").strip().lower() == "reporting_incident":
                        ai.state = "idle"
                        ai.target = None
                        ai.target_eid = None
                elif ai.state == "helping_victim":
                    self.sim.emit(Event(
                        "npc_help_arrived",
                        npc_eid=eid,
                        incident_id=getattr(ai, "incident_id", None),
                        target_eid=ai.target_eid,
                        x=pos.x,
                        y=pos.y,
                        z=tz,
                    ))
                    ai.state = "idle"
                    ai.target = None
                    ai.target_eid = None
                elif ai.state == "warning":
                    self.sim.emit(Event(
                        "npc_warning_arrived",
                        npc_eid=eid,
                        incident_id=getattr(ai, "incident_id", None),
                        x=pos.x,
                        y=pos.y,
                        z=tz,
                    ))
                    ai.state = "idle"
                    ai.target = None
                    ai.target_eid = None
                elif ai.state == "investigating":
                    ai.state = "idle"
                    ai.target = None
                    ai.target_eid = None
                    self.sim.emit(Event("npc_investigation_complete", npc_eid=eid, x=pos.x, y=pos.y, z=tz))
                elif ai.state == "soliciting_player":
                    pending_dialogue = _pop_npc_initiated_dialogue(self.sim, eid)
                    prompt_lines = ()
                    highlight_topic_ids = ()
                    cooldown = None
                    metadata = {}
                    if isinstance(pending_dialogue, dict):
                        raw_prompt_lines = pending_dialogue.get("prompt_lines", ())
                        if isinstance(raw_prompt_lines, str):
                            prompt_lines = (raw_prompt_lines,)
                        else:
                            prompt_lines = tuple(raw_prompt_lines or ())
                        raw_highlights = pending_dialogue.get("highlight_topic_ids", ())
                        if isinstance(raw_highlights, str):
                            highlight_topic_ids = (raw_highlights,)
                        else:
                            highlight_topic_ids = tuple(raw_highlights or ())
                        cooldown = pending_dialogue.get("cooldown")
                        metadata = dict(pending_dialogue.get("metadata", {})) if isinstance(pending_dialogue.get("metadata"), dict) else {}

                    if not prompt_lines:
                        occupation = occupations.get(eid)
                        career = str(getattr(occupation, "career", "") or "").strip().lower()
                        district_type = ""
                        world = getattr(self.sim, "world", None)
                        if world is not None:
                            chunk = world.get_chunk(*self.sim.chunk_coords(pos.x, pos.y))
                            district = chunk.get("district", {}) if isinstance(chunk, dict) else {}
                            if not isinstance(district, dict):
                                district = {}
                            district_type = str(district.get("district_type", "") or "").strip().lower()
                        interest = None
                        if player_eid is not None and player_pos is not None and int(player_pos.z) == int(pos.z):
                            interest = _street_buy_interest_profile(
                                self.sim,
                                eid,
                                player_eid,
                                district_type=district_type,
                                career=career,
                            )
                        if interest:
                            desired_name = str(interest.get("desired_name", "") or "").strip()
                            if interest.get("player_has_desired") and desired_name:
                                prompt_lines = (f"You carrying any {desired_name}? I'll pay for it.",)
                            elif interest.get("player_has_generic_match") and desired_name:
                                prompt_lines = (f"I'm looking for {desired_name}, but if you've got other hot stock I can look it over.",)
                            elif desired_name:
                                prompt_lines = (f"If you run across any {desired_name}, find me. I'm buying.",)
                            elif interest.get("player_has_match"):
                                prompt_lines = ("You carrying anything worth moving? I can pay.",)
                            highlight_topic_ids = ("street_buy",)

                    if cooldown is None:
                        cooldown = max(
                            60,
                            _behavior_preference(self.sim, eid, "initiate_dialogue_cooldown", 240) or 240,
                        )
                    dialog_cooldowns[eid] = int(self.sim.tick) + int(max(0, int(cooldown or 0)))
                    if prompt_lines and player_eid is not None:
                        self.sim.emit(Event(
                            "npc_dialogue_request",
                            eid=player_eid,
                            npc_eid=eid,
                            prompt_lines=prompt_lines,
                            highlight_topic_ids=highlight_topic_ids,
                        ))
                        event_type = str(metadata.get("event_type", "") or "").strip()
                        event_data = dict(metadata.get("event_data", {})) if isinstance(metadata.get("event_data"), dict) else {}
                        if event_type:
                            payload = dict(event_data)
                            payload.setdefault("npc_eid", eid)
                            self.sim.emit(Event(event_type, **payload))
                    ai.state = "idle"
                    ai.target = None
                    ai.target_eid = None
                elif ai.state == "seeking_street_buyer":
                    buyer_eid = ai.target_eid
                    buyer_pos = positions.get(buyer_eid) if buyer_eid is not None else None
                    if buyer_pos and int(buyer_pos.z) == int(pos.z):
                        occupation = occupations.get(buyer_eid)
                        career = str(getattr(occupation, "career", "") or "").strip().lower()
                        district_type = ""
                        world = getattr(self.sim, "world", None)
                        if world is not None:
                            chunk = world.get_chunk(*self.sim.chunk_coords(buyer_pos.x, buyer_pos.y))
                            district = chunk.get("district", {}) if isinstance(chunk, dict) else {}
                            if not isinstance(district, dict):
                                district = {}
                            district_type = str(district.get("district_type", "") or "").strip().lower()
                        _resolve_street_buy_between_actors(
                            self.sim,
                            buyer_eid,
                            eid,
                            district_type=district_type,
                            career=career,
                        )
                    ai.state = "idle"
                    ai.target = None
                    ai.target_eid = None
                elif ai.state == "seeking_street_appraiser":
                    appraiser_eid = ai.target_eid
                    appraiser_pos = positions.get(appraiser_eid) if appraiser_eid is not None else None
                    if appraiser_pos and int(appraiser_pos.z) == int(pos.z):
                        _resolve_street_appraise_between_actors(
                            self.sim,
                            appraiser_eid,
                            eid,
                        )
                    ai.state = "idle"
                    ai.target = None
                    ai.target_eid = None
                elif ai.state == "seeking_social":
                    partner_eid = ai.target_eid
                    needs = needs_map.get(eid)
                    if needs:
                        needs.social = _clamp(needs.social + 0.8)
                    partner_needs = needs_map.get(partner_eid)
                    if partner_needs:
                        partner_needs.social = _clamp(partner_needs.social + 0.45)
                    relation = "friend"
                    tone = "gossip"
                    social = socials.get(eid)
                    partner_social = socials.get(partner_eid)
                    bond = social.bonds.get(partner_eid) if social else None
                    if bond:
                        relation = str(bond.get("kind", "friend")).strip().lower() or "friend"
                        old_closeness = float(bond.get("closeness", 0.0) or 0.0)
                        old_trust = float(bond.get("trust", 0.0) or 0.0)
                        offset = apply_visible_outfit_social_offset(
                            self.sim,
                            eid,
                            partner_eid,
                            trust_delta=0.015,
                            closeness_delta=0.025,
                            context="npc_socialized",
                        )
                        bond["closeness"] = min(
                            1.0,
                            float(bond.get("closeness", 0.0)) + float(offset.get("closeness_delta", 0.025)),
                        )
                        bond["trust"] = min(
                            1.0,
                            float(bond.get("trust", 0.0)) + float(offset.get("trust_delta", 0.015)),
                        )
                        _record_actor_social_warmth(
                            self.sim,
                            eid,
                            other_eid=partner_eid,
                            reason="npc_socialized",
                            trust_delta=float(bond.get("trust", 0.0) or 0.0) - old_trust,
                            closeness_delta=float(bond.get("closeness", 0.0) or 0.0) - old_closeness,
                            post_bond=bond,
                        )
                    if partner_social and eid in partner_social.bonds:
                        reverse = partner_social.bonds[eid]
                        old_closeness = float(reverse.get("closeness", 0.0) or 0.0)
                        old_trust = float(reverse.get("trust", 0.0) or 0.0)
                        reverse_offset = apply_visible_outfit_social_offset(
                            self.sim,
                            partner_eid,
                            eid,
                            trust_delta=0.012,
                            closeness_delta=0.02,
                            context="npc_socialized",
                        )
                        reverse["closeness"] = min(
                            1.0,
                            float(reverse.get("closeness", 0.0)) + float(reverse_offset.get("closeness_delta", 0.02)),
                        )
                        reverse["trust"] = min(
                            1.0,
                            float(reverse.get("trust", 0.0)) + float(reverse_offset.get("trust_delta", 0.012)),
                        )
                        _record_actor_social_warmth(
                            self.sim,
                            partner_eid,
                            other_eid=eid,
                            reason="npc_socialized",
                            trust_delta=float(reverse.get("trust", 0.0) or 0.0) - old_trust,
                            closeness_delta=float(reverse.get("closeness", 0.0) or 0.0) - old_closeness,
                            post_bond=reverse,
                        )
                    hydrate_relationship_social_knowledge(
                        self.sim,
                        eid,
                        partner_eid=partner_eid,
                        source_event="seeking_social_bond",
                    )
                    if partner_eid is not None:
                        hydrate_relationship_social_knowledge(
                            self.sim,
                            partner_eid,
                            partner_eid=eid,
                            source_event="seeking_social_bond",
                        )
                    relationship_update = _maybe_progress_relationship_after_socialized(self.sim, eid, partner_eid)
                    partner_ai = ais.get(partner_eid)
                    roles = {
                        str(ai.role or "").strip().lower(),
                        str(getattr(partner_ai, "role", "") or "").strip().lower(),
                    }
                    if "drunk" in roles:
                        tone = "rambling"
                    elif "thief" in roles:
                        tone = "conspiring"
                    elif relation in {"family", "partner"} or relationship_update:
                        tone = "check_in"
                    social_dynamics = getattr(self.sim, "npc_social_dynamics_system", None)
                    chatter = None
                    if social_dynamics is not None:
                        chatter = social_dynamics._social_chatter_payload(
                            eid,
                            partner_eid,
                            relation,
                            tone,
                        )
                    self.sim.emit(Event(
                        "npc_socialized",
                        npc_eid=eid,
                        partner_eid=partner_eid,
                        relation=relation,
                        tone=tone,
                        x=pos.x,
                        y=pos.y,
                        z=tz,
                        topic=(chatter or {}).get("topic", ""),
                        quote=(chatter or {}).get("quote", ""),
                        summary=(chatter or {}).get("summary", ""),
                        detail=(chatter or {}).get("detail", ""),
                        channel=(chatter or {}).get("channel", "social"),
                        priority=(chatter or {}).get("priority", "low"),
                        opportunity_id=(chatter or {}).get("opportunity_id"),
                        incident_id=(chatter or {}).get("incident_id"),
                        property_id=(chatter or {}).get("property_id"),
                        actor_eid=(chatter or {}).get("actor_eid"),
                        other_eid=(chatter or {}).get("other_eid"),
                        relationship_kind=(chatter or {}).get("relationship_kind", ""),
                        social_knowledge_key=(chatter or {}).get("social_knowledge_key", ""),
                        source_domain=(chatter or {}).get("source_domain", ""),
                        confidence_hint=(chatter or {}).get("confidence_hint", 0.0),
                        property_lead_kind=(chatter or {}).get("property_lead_kind", ""),
                    ))
                    ai.state = "idle"
                    ai.target = None
                    ai.target_eid = None
                elif ai.state == "seeking_companionship":
                    partner_eid = ai.target_eid
                    if partner_eid is not None and _actors_use_wildlife_social(self.sim, eid, partner_eid):
                        needs = needs_map.get(eid)
                        if needs:
                            needs.social = _clamp(needs.social + 0.9)
                        partner_needs = needs_map.get(partner_eid)
                        if partner_needs:
                            partner_needs.social = _clamp(partner_needs.social + 0.3)
                        bond_strength = _sync_wildlife_bond_pair(
                            self.sim,
                            eid,
                            partner_eid,
                            kind="companion",
                            closeness_delta=0.09,
                            trust_delta=0.07,
                            comfort_delta=0.08,
                        )
                        self.sim.emit(Event(
                            "animal_socialized",
                            eid=eid,
                            partner_eid=partner_eid,
                            x=pos.x,
                            y=pos.y,
                            z=tz,
                            kind="companionship",
                            bond_strength=round(bond_strength, 3),
                            summary=f"{_entity_display_name(self.sim, eid, title_case=True) or 'An animal'} keeps close to {_entity_display_name(self.sim, partner_eid, title_case=True) or 'a companion'}",
                        ))
                    ai.state = "idle"
                    ai.target = None
                    ai.target_eid = None
                elif ai.state == "protecting":
                    self.sim.emit(Event("npc_guarding_target", npc_eid=eid, target_eid=ai.target_eid, x=pos.x, y=pos.y, z=tz))
                else:
                    ai.target = (pos.x, pos.y, pos.z)
                if throttle:
                    throttle.next_move_tick = self.sim.tick + 1
                else:
                    self.next_move_tick[eid] = self.sim.tick + 1
                continue

            routine_path_state = ai.state in {
                "selling_scavenged",
                "seeking_medical_aid",
                "seeking_safe_spot",
                "seeking_shelter",
                "patrolling",
                "working",
                "lounging",
                "socializing",
                "shopping",
                "resting",
            }
            step = None
            path_suppressed = live_timeskip_active and self._live_no_path_cached(eid, ai, pos, (tx, ty, tz))
            commute_phase = str(getattr(ai, "vehicle_commute_phase", "") or "").strip().lower()
            if commute_phase == "drive":
                step = self._vehicle_route_next_step(
                    eid,
                    (int(pos.x), int(pos.y), int(pos.z)),
                    (tx, ty, tz),
                    str(getattr(ai, "vehicle_commute_vehicle_id", "") or "").strip(),
                )
            if step is None and commute_phase != "drive" and routine_path_state and not path_suppressed:
                step = _next_opportunity_active_target_step(
                    self.sim,
                    eid,
                    ai.state,
                    pos,
                    (tx, ty, tz),
                    max_nodes=256,
                )
            if step is None and commute_phase != "drive" and not path_suppressed:
                step = _path_next_step(
                    self.sim,
                    eid=eid,
                    sx=pos.x,
                    sy=pos.y,
                    tx=tx,
                    ty=ty,
                    z=pos.z,
                    max_nodes=192 if routine_path_state else 512,
                )

            if not step and _manhattan(pos.x, pos.y, tx, ty) <= 1:
                direct_reason = _closed_door_move_block_reason(
                    self.sim,
                    eid,
                    tx,
                    ty,
                    tz,
                )
                if str(direct_reason or "").strip().lower() in {"locked_property", "closed_property", "door_access_denied"}:
                    if ai.state == "committing_property_crime":
                        crime_prop = self.sim.properties.get(str(getattr(criminal_drive_state(self.sim, eid, create=False), "current_target_property_id", "") or "").strip())
                        if isinstance(crime_prop, dict):
                            success, method = _attempt_locked_property_entry_with_sim(
                                self.sim,
                                eid,
                                crime_prop,
                                target_x=tx,
                                target_y=ty,
                                target_z=tz,
                            )
                            if success:
                                if throttle:
                                    throttle.next_move_tick = max(throttle.next_move_tick, self.sim.tick + 1)
                                else:
                                    self.next_move_tick[eid] = max(self.next_move_tick.get(eid, 0), self.sim.tick + 1)
                                continue
                            plan_key = str(getattr(criminal_drive_state(self.sim, eid, create=False), "current_plan_key", "") or "").strip()
                            self.sim.emit(Event(
                                "npc_crime_attempt_resolved",
                                npc_eid=eid,
                                success=False,
                                reason=str(method or direct_reason or "locked_property"),
                                plan_key=plan_key or None,
                                **_crime_plan_event_fields(self.sim, eid, plan_key),
                                x=tx,
                                y=ty,
                                z=tz,
                            ))
                            ai.state = "idle"
                            ai.target = None
                            ai.target_eid = None
                            if throttle:
                                throttle.next_move_tick = max(throttle.next_move_tick, self.sim.tick + 1)
                            else:
                                self.next_move_tick[eid] = max(self.next_move_tick.get(eid, 0), self.sim.tick + 1)
                            continue
                    knock = _door_knock_attempt(
                        self.sim,
                        eid,
                        tx,
                        ty,
                        tz,
                        reason=direct_reason,
                        source="npc_move",
                    )
                    if bool((knock or {}).get("handled")):
                        if throttle:
                            throttle.next_move_tick = max(throttle.next_move_tick, self.sim.tick + 1)
                        else:
                            self.next_move_tick[eid] = max(self.next_move_tick.get(eid, 0), self.sim.tick + 1)
                        continue

            moved = False
            blocked_reason = None
            vehicle_step = False
            if step:
                nx, ny = step
                origin_x = int(pos.x)
                origin_y = int(pos.y)
                origin_z = int(pos.z)
                vehicle_result = self._try_npc_vehicle_route_step(eid, pos, step)
                if vehicle_result is None:
                    moved, blocked_reason = try_move_entity(
                        self.sim,
                        eid=eid,
                        new_x=nx,
                        new_y=ny,
                        new_z=pos.z,
                        reason="npc_step",
                    )
                else:
                    moved, blocked_reason, origin_x, origin_y, origin_z = vehicle_result
                    vehicle_step = True

            cooldown = hold_cooldown
            if not moved:
                current_vehicle_state = self.sim.ecs.get(VehicleState).get(eid)
                if vehicle_step or bool(current_vehicle_state and getattr(current_vehicle_state, "in_vehicle", False)):
                    self._abandon_npc_vehicle_commute(
                        eid,
                        ai,
                        pos,
                        reason=str(blocked_reason or ("vehicle_blocked" if vehicle_step else "vehicle_no_path")),
                    )
                    if throttle:
                        throttle.next_move_tick = max(throttle.next_move_tick, self.sim.tick + 1)
                    else:
                        self.next_move_tick[eid] = max(self.next_move_tick.get(eid, 0), self.sim.tick + 1)
                    continue
                if routine_path_state:
                    _invalidate_opportunity_active_target_path(self.sim, eid, ai.state)
                knock_handled = False
                if step and str(blocked_reason or "").strip().lower() in {"locked_property", "closed_property", "door_access_denied"}:
                    if ai.state == "committing_property_crime":
                        crime_prop = self.sim.properties.get(str(getattr(criminal_drive_state(self.sim, eid, create=False), "current_target_property_id", "") or "").strip())
                        if isinstance(crime_prop, dict):
                            success, method = _attempt_locked_property_entry_with_sim(
                                self.sim,
                                eid,
                                crime_prop,
                                target_x=nx,
                                target_y=ny,
                                target_z=pos.z,
                            )
                            if success:
                                if throttle:
                                    throttle.next_move_tick = max(throttle.next_move_tick, self.sim.tick + 1)
                                else:
                                    self.next_move_tick[eid] = max(self.next_move_tick.get(eid, 0), self.sim.tick + 1)
                                continue
                            plan_key = str(getattr(criminal_drive_state(self.sim, eid, create=False), "current_plan_key", "") or "").strip()
                            self.sim.emit(Event(
                                "npc_crime_attempt_resolved",
                                npc_eid=eid,
                                success=False,
                                reason=str(method or blocked_reason or "locked_property"),
                                plan_key=plan_key or None,
                                **_crime_plan_event_fields(self.sim, eid, plan_key),
                                x=nx,
                                y=ny,
                                z=pos.z,
                            ))
                            ai.state = "idle"
                            ai.target = None
                            ai.target_eid = None
                            if throttle:
                                throttle.next_move_tick = max(throttle.next_move_tick, self.sim.tick + 1)
                            else:
                                self.next_move_tick[eid] = max(self.next_move_tick.get(eid, 0), self.sim.tick + 1)
                            continue
                    knock = _door_knock_attempt(
                        self.sim,
                        eid,
                        nx,
                        ny,
                        pos.z,
                        reason=blocked_reason,
                        source="npc_move",
                    )
                    knock_handled = bool((knock or {}).get("handled"))
                if ai.state == "protecting" and threat_focus:
                    _sync_npc_cover_against_threat(
                        self.sim,
                        eid,
                        pos,
                        threat_focus,
                        tick=self.sim.tick,
                        min_effect=0.16,
                    )
                if not knock_handled:
                    self.sim.emit(Event("npc_move_blocked", npc_eid=eid, x=pos.x, y=pos.y, z=pos.z))
                retry_cooldown = 1
                if live_timeskip_active:
                    blocked_key = str(blocked_reason or "").strip().lower()
                    if not step:
                        if ai.state in {
                            "seeking_safety",
                            "evading_authority",
                            "chasing",
                            "protecting",
                            "reporting_incident",
                            "helping_victim",
                            "warning",
                            "ejecting_target",
                            "leaving_property",
                            "seeking_medical_aid",
                            "seeking_safe_spot",
                            "seeking_shelter",
                        }:
                            retry_cooldown = max(int(hold_cooldown), 6)
                        elif routine_path_state:
                            retry_cooldown = max(int(hold_cooldown), 10)
                        else:
                            retry_cooldown = max(int(hold_cooldown), 8)
                        self._note_live_no_path(eid, ai, pos, (tx, ty, tz), delay_ticks=max(retry_cooldown, 30))
                    elif blocked_key == "active_fire":
                        retry_cooldown = max(int(hold_cooldown), 6)
                if throttle:
                    throttle.next_move_tick = max(throttle.next_move_tick, self.sim.tick + retry_cooldown)
                else:
                    self.next_move_tick[eid] = max(self.next_move_tick.get(eid, 0), self.sim.tick + retry_cooldown)
                continue

            profile = noise_profiles.get(eid)
            noise_radius = int(max(1, getattr(profile, "move_radius", 4)))
            if vehicle_step:
                noise_radius = max(noise_radius, 6)
            self.sim.emit(Event(
                "noise",
                source_eid=eid,
                x=int(pos.x),
                y=int(pos.y),
                z=int(pos.z),
                radius=noise_radius,
                cause="vehicle_move" if vehicle_step else "move",
            ))
            _emit_move_access_events(
                self.sim,
                eid=eid,
                action="move",
                origin_x=origin_x,
                origin_y=origin_y,
                origin_z=origin_z,
                target_x=int(pos.x),
                target_y=int(pos.y),
                target_z=int(pos.z),
                emit_clear_offense=False,
            )
            if ai.state == "protecting" and threat_focus:
                _sync_npc_cover_against_threat(
                    self.sim,
                    eid,
                    pos,
                    threat_focus,
                    tick=self.sim.tick,
                    min_effect=0.16,
                )
            bonus_moved = self._try_bonus_move_step(
                eid,
                ai,
                target=(tx, ty, tz),
                positions=positions,
                noise_profiles=noise_profiles,
                vehicle_step=vehicle_step,
            )
            if bonus_moved and ai.state == "protecting" and threat_focus:
                bonus_pos = positions.get(eid)
                if bonus_pos:
                    _sync_npc_cover_against_threat(
                        self.sim,
                        eid,
                        bonus_pos,
                        threat_focus,
                        tick=self.sim.tick,
                        min_effect=0.16,
                    )

            if throttle:
                throttle.next_move_tick = self.sim.tick + cooldown
            else:
                self.next_move_tick[eid] = self.sim.tick + cooldown
            self._clear_live_no_path(eid)
