"""Extracted systems from ``game.systems``: NPCNeedsSystem, NPCWillSystem, NPCInvestigateSystem."""

import random
from engine.events import Event
from engine.systems import System
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
from game.service_runtime import _clamp
from game.system_support.actor_runtime import (
    _apply_downed_actor_state,
    _detail_tick_allowed,
    _entity_is_downed,
)
from game.system_support.ai_intent_runtime import _sync_ai_intent
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
from game.system_support.npc_behavior_runtime import (
    BEHAVIOR_APPRAISE_STREET_GOODS,
    BEHAVIOR_AVOID_AUTHORITIES,
    BEHAVIOR_COLLECT_GROUND_CREDITS,
    BEHAVIOR_AVOID_THREAT,
    BEHAVIOR_BUY_DESIRED_DRUG,
    BEHAVIOR_BUY_PLAYER_GOODS,
    BEHAVIOR_ENFORCE_JUSTICE,
    BEHAVIOR_FOLLOW_DUTY,
    BEHAVIOR_INITIATE_DIALOGUE,
    BEHAVIOR_PROTECT_ALLIES,
    BEHAVIOR_SCAVENGE_LOOSE_ITEMS,
    BEHAVIOR_SELL_SCAVENGED_ITEMS,
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
    _find_safe_spot_target,
    _find_scavenged_sale_target,
    _find_ground_credit_target,
    _find_scavenge_ground_item_target,
    _inventory_scavenge_sale_rows,
    _inventory_contraband_heat,
    _pick_social_venue as _behavior_pick_social_venue,
    _receive_lodging_at_actor,
    _receive_medical_aid_at_actor,
    _receive_safe_spot_at_actor,
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
    _npc_status_metric_args,
    _status_int_offset,
    _status_modifier_total,
    _status_multiplier,
    _status_tick_step,
)
def _facade():
    from game import systems as facade

    return facade


def _wildlife_module():
    from game import systems_wildlife as wildlife

    return wildlife


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
    target = _find_safe_spot_target(
        sim,
        actor_eid,
        pos,
        preferred_property_id=property_id,
        preferred_score_bonus=18.0,
    )
    if not target or str(target.get("property_id", "") or "").strip() != property_id:
        return None
    return target


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
    elif isinstance(safe_spot_share, dict) and intent not in {"protecting", "seeking_safety", "chasing", "warning", "helping_victim", "reporting_incident"}:
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
    elif isinstance(street_buy_share, dict) and intent not in {"protecting", "seeking_safety", "chasing", "warning", "helping_victim", "reporting_incident"}:
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
    elif isinstance(street_appraise_share, dict) and intent not in {"protecting", "seeking_safety", "chasing", "warning", "helping_victim", "reporting_incident"}:
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
            )] = int(tick or 0)
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

    def _sync_threshold(self, eid, needs, key, value):
        if value < self.CRITICAL_LEVEL and key not in needs.critical:
            needs.critical.add(key)
            self.sim.emit(Event("npc_need_critical", npc_eid=eid, need=key, value=value))

        if value > self.STABLE_LEVEL and key in needs.critical:
            needs.critical.remove(key)
            self.sim.emit(Event("npc_need_stabilized", npc_eid=eid, need=key, value=value))

    def update(self):
        needs_map = self.sim.ecs.get(NPCNeeds)
        ais = self.sim.ecs.get(AI)
        positions = self.sim.ecs.get(Position)

        for eid, needs in needs_map.items():
            pos = positions.get(eid)
            if pos and not _detail_tick_allowed(self.sim, pos, eid, coarse_divisor=3):
                continue

            ai = ais.get(eid)
            state = ai.state if ai else "idle"

            needs.energy = _clamp(needs.energy - 0.07)
            needs.social = _clamp(needs.social - 0.05)

            if state in {"investigating", "protecting", "seeking_safety"}:
                needs.safety = _clamp(needs.safety - 0.08)
                needs.energy = _clamp(needs.energy - 0.03)
            else:
                needs.safety = _clamp(needs.safety + 0.03)

            if state in {"seeking_social", "seeking_companionship"}:
                needs.social = _clamp(needs.social + 0.25)

            if state == "resting":
                needs.energy = _clamp(needs.energy + 0.35)

            self._sync_threshold(eid, needs, "energy", needs.energy)
            self._sync_threshold(eid, needs, "safety", needs.safety)
            self._sync_threshold(eid, needs, "social", needs.social)

class NPCWillSystem(System):

    def _set_intent(self, eid, ai, will, intent, score, target=None, target_eid=None):
        if _entity_is_downed(self.sim, eid):
            _apply_downed_actor_state(self.sim, eid, tick=self.sim.tick)
            return
        previous = (ai.state, ai.target, ai.target_eid)
        next_state = (intent, target, target_eid)
        if previous == next_state and will.intent == intent:
            return

        ai.state = intent
        ai.target = target
        ai.target_eid = target_eid

        will.intent = intent
        will.score = score
        will.target = target
        will.target_eid = target_eid
        will.last_tick = self.sim.tick

        self.sim.emit(Event(
            "npc_intent_changed",
            npc_eid=eid,
            intent=intent,
            score=round(score, 2),
            target=target,
            target_eid=target_eid,
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
        player_eid = getattr(self.sim, "player_eid", None)
        player_pos = positions.get(player_eid)
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

        for eid, ai in ais.items():
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

            routine = routines.get(eid)
            suppression = self.sim.ecs.get(SuppressionState).get(eid)
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
                if ai.state == "seeking_safety" and ai.target:
                    self._set_intent(eid, ai, will, "seeking_safety", 86.0, ai.target, None)
                    continue

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
            if ai.state in {"reporting_incident", "helping_victim", "warning"} and ai.target:
                will.intent = ai.state
                will.target = ai.target
                will.target_eid = ai.target_eid
                will.last_tick = self.sim.tick
                continue

            if ai.state == "seeking_safety" and ai.target and getattr(ai, "incident_id", None) is not None:
                will.intent = ai.state
                will.target = ai.target
                will.target_eid = ai.target_eid
                will.last_tick = self.sim.tick
                continue

            if ai.state == "protecting" and ai.target:
                recent_threat = memory.strongest("ally_threatened") if memory else None
                recent_property = _strongest_memory_entry(
                    memory,
                    "property_threat",
                    predicate=_memory_visible,
                )
                if (recent_threat and recent_threat["strength"] > 0.25) or (
                    recent_property and recent_property["strength"] > 0.25
                ):
                    threat_focus = _known_threat_position_for_npc(
                        self.sim,
                        eid,
                        pos,
                        target_eid=ai.target_eid,
                        memory=memory,
                        radius=12,
                    )
                    _loadout, held_weapon, _instance = _weapon_context_for_entity(self.sim, eid)
                    metrics = _npc_combat_metrics(
                        needs=needs,
                        traits=traits,
                        vitality=vitality,
                        suppression=suppression,
                        weapon=held_weapon,
                        **_npc_status_metric_args(self.sim, eid),
                    )
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
                        retreat_target = _pick_npc_retreat_target(
                            self.sim,
                            eid,
                            pos,
                            threat_focus,
                            metrics=metrics,
                            max_steps=5,
                        )
                        if retreat_target and retreat_target != (int(pos.x), int(pos.y), int(pos.z)):
                            self._set_intent(
                                eid,
                                ai,
                                will,
                                "seeking_safety",
                                max(82.0, 68.0 + (metrics["retreat_bias"] * 26.0)),
                                retreat_target,
                                None,
                            )
                            continue
                    # Pinned NPCs stay put instead of advancing.
                    if suppression and suppression.pinned():
                        will.intent = "protecting"
                        will.target = (pos.x, pos.y, pos.z)
                        will.target_eid = ai.target_eid
                        will.last_tick = self.sim.tick
                        continue
                    will.intent = "protecting"
                    will.target = ai.target
                    will.target_eid = ai.target_eid
                    will.last_tick = self.sim.tick
                    continue

            best_intent = "idle"
            best_score = 0.0
            best_target = None
            best_target_eid = None

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
                tx = threat["data"].get("x", pos.x)
                ty = threat["data"].get("y", pos.y)
                tz = threat["data"].get("z", pos.z)
                if tz == pos.z:
                    dx = 1 if pos.x - tx >= 0 else -1
                    dy = 1 if pos.y - ty >= 0 else -1
                    safe_x = pos.x + (dx * 4)
                    safe_y = pos.y + (dy * 4)
                    best_intent = "seeking_safety"
                    best_score = safety_pressure
                    best_target = (safe_x, safe_y, pos.z)
                    best_target_eid = None

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

            social_venue_pressure = (100.0 - needs.social) * (0.3 + (seek_social_contact * 0.95))
            if not work_active and social_venue_pressure > best_score:
                own_prop_id = None
                if occupation and isinstance(getattr(occupation, "workplace", None), dict):
                    own_prop_id = occupation.workplace.get("property_id")
                if ai.state == "socializing" and ai.target is not None:
                    best_intent = "socializing"
                    best_score = social_venue_pressure
                    best_target = ai.target
                    best_target_eid = None
                else:
                    _sv_prop, _sv_focus = _pick_social_venue(
                        self.sim, pos.x, pos.y, pos.z, eid,
                        own_prop_id=own_prop_id,
                    )
                    if _sv_focus:
                        needs.social = _clamp(needs.social + 0.15)
                        best_intent = "socializing"
                        best_score = social_venue_pressure
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

    DEFAULT_MOVE_COOLDOWNS = {
        "investigating": 2,
        "protecting": 1,
        "helping_victim": 1,
        "reporting_incident": 2,
        "warning": 1,
        "chasing": 1,
        "scavenging": 2,
        "selling_scavenged": 2,
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
        "resting": 4,
    }

    def __init__(self, sim):
        super().__init__(sim)
        self.sim.events.subscribe("noise", self.on_noise)
        self.next_move_tick = {}

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
                continue

            if not _noise_merits_attention(self.sim, eid, source_eid, nx, ny, nz, cause):
                continue

            ai.state = "investigating"
            ai.target = (nx, ny, nz)

            self.sim.emit(Event(
                "npc_investigate",
                npc_eid=eid,
                source_eid=source_eid,
                x=nx,
                y=ny,
                z=nz,
            ))

    def update(self):
        ais = self.sim.ecs.get(AI)
        positions = self.sim.ecs.get(Position)
        needs_map = self.sim.ecs.get(NPCNeeds)
        socials = self.sim.ecs.get(NPCSocial)
        move_throttles = self.sim.ecs.get(MovementThrottle)
        effects_map = self.sim.ecs.get(StatusEffects)
        noise_profiles = self.sim.ecs.get(NoiseProfile)
        memories = self.sim.ecs.get(NPCMemory)
        traits_map = self.sim.ecs.get(NPCTraits)
        weapon_profiles = self.sim.ecs.get(WeaponUseProfile)
        vitalities = self.sim.ecs.get(Vitality)
        suppressions = self.sim.ecs.get(SuppressionState)
        occupations = self.sim.ecs.get(Occupation)
        global_stride = int(max(1, getattr(self.sim, "npc_move_tick_stride", 1)))
        player_eid = getattr(self.sim, "player_eid", None)
        player_pos = positions.get(player_eid)
        dialog_cooldowns = getattr(self.sim, "npc_dialogue_cooldowns", None)
        if not isinstance(dialog_cooldowns, dict):
            dialog_cooldowns = {}
            self.sim.npc_dialogue_cooldowns = dialog_cooldowns

        moving_states = {
            "investigating",
            "protecting",
            "helping_victim",
            "reporting_incident",
            "warning",
            "chasing",
            "scavenging",
            "selling_scavenged",
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
            "resting",
        }

        for eid, ai in ais.items():
            if ai.state not in moving_states:
                continue

            pos = positions.get(eid)
            if not pos:
                continue
            if _entity_is_downed(self.sim, eid):
                _apply_downed_actor_state(self.sim, eid, tick=self.sim.tick)
                continue

            if global_stride > 1 and ((self.sim.tick + eid) % global_stride != 0):
                continue

            if not _detail_tick_allowed(self.sim, pos, eid, coarse_divisor=3):
                continue

            memory = memories.get(eid)
            hidden_trade_tip = _recent_behavior_tip(memory, BEHAVIOR_TIP_HIDDEN_TRADE, now=self.sim.tick)
            hidden_trade_tip_data = hidden_trade_tip.get("data", {}) if isinstance(hidden_trade_tip, dict) else {}
            hidden_trade_property_id = str(hidden_trade_tip_data.get("property_id", "") or "").strip() if isinstance(hidden_trade_tip_data, dict) else ""
            hidden_clinic_tip = _recent_behavior_tip(memory, BEHAVIOR_TIP_HIDDEN_CLINIC, now=self.sim.tick)
            hidden_clinic_tip_data = hidden_clinic_tip.get("data", {}) if isinstance(hidden_clinic_tip, dict) else {}
            hidden_clinic_property_id = str(hidden_clinic_tip_data.get("property_id", "") or "").strip() if isinstance(hidden_clinic_tip_data, dict) else ""

            throttle = move_throttles.get(eid)
            status_speed_mult = _entity_status_move_speed_multiplier(self.sim, eid)

            next_move_tick = throttle.next_move_tick if throttle else self.next_move_tick.get(eid, 0)
            if self.sim.tick < next_move_tick:
                continue

            target = _resolve_ai_target(self.sim, ai)
            if not target:
                continue

            tx, ty, tz = target
            threat_focus = None
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
                continue

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

            if pos.x == tx and pos.y == ty:
                if ai.state == "resting":
                    needs = needs_map.get(eid)
                    if needs:
                        needs.energy = _clamp(needs.energy + 0.55)

                if ai.state == "investigating":
                    self.sim.emit(Event("npc_investigation_complete", npc_eid=eid, x=tx, y=ty, z=tz))

                if ai.state == "scavenging":
                    _collect_ground_items_at_actor(self.sim, eid, pos)
                if ai.state == "selling_scavenged":
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
                        self.sim.emit(Event(
                            "npc_social_venue_visited",
                            npc_eid=eid,
                            property_id=arrived_prop.get("id"),
                            source_eid=eid,
                        ))
                if ai.state in {"working", "lounging", "socializing"}:
                    # Arrived at roam tile; clear target so will system picks a new one.
                    ai.target = None
                elif ai.state not in {"protecting", "resting", "following", "holding"}:
                    ai.state = "idle"
                    ai.target = None
                    ai.target_eid = None
                if throttle:
                    throttle.next_move_tick = self.sim.tick + 1
                else:
                    self.next_move_tick[eid] = self.sim.tick + 1
                continue

            if ai.state in {"investigating", "seeking_social", "seeking_companionship", "protecting", "reporting_incident", "helping_victim", "warning", "soliciting_player", "seeking_street_buyer", "seeking_street_appraiser"} and _manhattan(pos.x, pos.y, tx, ty) <= 1:
                if ai.state == "reporting_incident":
                    self.sim.emit(Event(
                        "npc_report_arrived",
                        npc_eid=eid,
                        incident_id=getattr(ai, "incident_id", None),
                        x=pos.x,
                        y=pos.y,
                        z=tz,
                    ))
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
                        bond["closeness"] = min(1.0, float(bond.get("closeness", 0.0)) + 0.025)
                        bond["trust"] = min(1.0, float(bond.get("trust", 0.0)) + 0.015)
                    if partner_social and eid in partner_social.bonds:
                        reverse = partner_social.bonds[eid]
                        reverse["closeness"] = min(1.0, float(reverse.get("closeness", 0.0)) + 0.02)
                        reverse["trust"] = min(1.0, float(reverse.get("trust", 0.0)) + 0.012)
                    partner_ai = ais.get(partner_eid)
                    roles = {
                        str(ai.role or "").strip().lower(),
                        str(getattr(partner_ai, "role", "") or "").strip().lower(),
                    }
                    if "drunk" in roles:
                        tone = "rambling"
                    elif "thief" in roles:
                        tone = "conspiring"
                    elif relation in {"family", "partner"}:
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
                        property_id=(chatter or {}).get("property_id"),
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

            step = _path_next_step(
                self.sim,
                eid=eid,
                sx=pos.x,
                sy=pos.y,
                tx=tx,
                ty=ty,
                z=pos.z,
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
            if step:
                nx, ny = step
                origin_x = int(pos.x)
                origin_y = int(pos.y)
                origin_z = int(pos.z)
                moved, blocked_reason = try_move_entity(
                    self.sim,
                    eid=eid,
                    new_x=nx,
                    new_y=ny,
                    new_z=pos.z,
                    reason="npc_step",
                )

            cooldown = hold_cooldown
            if not moved:
                knock_handled = False
                if step and str(blocked_reason or "").strip().lower() in {"locked_property", "closed_property", "door_access_denied"}:
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
                if throttle:
                    throttle.next_move_tick = max(throttle.next_move_tick, self.sim.tick + 1)
                else:
                    self.next_move_tick[eid] = max(self.next_move_tick.get(eid, 0), self.sim.tick + 1)
                continue

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
            if ai.state == "protecting" and threat_focus:
                _sync_npc_cover_against_threat(
                    self.sim,
                    eid,
                    pos,
                    threat_focus,
                    tick=self.sim.tick,
                    min_effect=0.16,
                )

            if throttle:
                throttle.next_move_tick = self.sim.tick + cooldown
            else:
                self.next_move_tick[eid] = self.sim.tick + cooldown
