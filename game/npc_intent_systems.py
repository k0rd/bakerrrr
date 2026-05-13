"""Extracted systems from ``game.systems``: NPCNeedsSystem, NPCWillSystem, NPCInvestigateSystem."""

import random
from engine.events import Event
from engine.systems import System
from game.checks import (
    crime_read_summary as _crime_read_summary,
    crime_sensitivity as _crime_sensitivity,
    justice_level as _justice_level,
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
from game.system_support.actor_runtime import (
    _apply_downed_actor_state,
    _detail_tick_allowed,
    _entity_is_downed,
)
from game.system_support.entity_naming import _entity_display_name
from game.system_support.interaction_ordering import (
    _direction_step,
    _interaction_target_order_key,
    _manhattan,
    _normalized_direction,
)
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


def _home_property(sim, routine=None):
    home = getattr(routine, "home", None)
    if isinstance(home, (list, tuple)) and len(home) >= 3:
        prop = _property_covering(sim, int(home[0]), int(home[1]), int(home[2]))
        if prop:
            return prop
    return None


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

def _active_contractor_record(*args, **kwargs):
    return _facade()._active_contractor_record(*args, **kwargs)

def _clamp(*args, **kwargs):
    return _facade()._clamp(*args, **kwargs)

def _contractor_order_target_from_record(*args, **kwargs):
    return _facade()._contractor_order_target_from_record(*args, **kwargs)

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

def _noise_merits_attention(*args, **kwargs):
    return _facade()._noise_merits_attention(*args, **kwargs)

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
    return _facade()._pick_social_venue(*args, **kwargs)

def _resolve_ai_target(*args, **kwargs):
    return _facade()._resolve_ai_target(*args, **kwargs)

def _sa(*args, **kwargs):
    return _facade()._sa(*args, **kwargs)

def _strongest_memory_entry(*args, **kwargs):
    return _facade()._strongest_memory_entry(*args, **kwargs)

def _sv_focus(*args, **kwargs):
    return _facade()._sv_focus(*args, **kwargs)

def _sync_ai_intent(*args, **kwargs):
    return _facade()._sync_ai_intent(*args, **kwargs)

def _sync_npc_cover_against_threat(*args, **kwargs):
    return _facade()._sync_npc_cover_against_threat(*args, **kwargs)

def _weapon_context_for_entity(*args, **kwargs):
    return _facade()._weapon_context_for_entity(*args, **kwargs)

def _workplace_property(*args, **kwargs):
    return _facade()._workplace_property(*args, **kwargs)


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
                    + (traits.loyalty * 14.0)
                    + (traits.empathy * 9.0)
                )
                if against_pos and int(against_pos.z) == int(pos.z):
                    if protect_drive > best_score and (threat_strength >= 0.24 or protectiveness >= 0.62):
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
                    or traits.bravery >= 0.58
                    or traits.loyalty >= 0.72
                    or traits.empathy >= 0.76
                    or side_impression >= 0.58
                    or against_impression <= -0.58
                )
                protect_drive = (
                    (side_strength * 54.0)
                    + (max(0.0, side_impression) * 18.0)
                    + (max(0.0, -against_impression) * 16.0)
                    + (traits.bravery * 10.0)
                    + (traits.loyalty * 8.0)
                    + (traits.empathy * 6.0)
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

                justice_drive = 0.0
                if justice:
                    justice_drive = (_justice_level(justice) * 52.0) + (crime_sensitivity * 20.0)
                    if justice.enforce_all:
                        justice_drive += 18.0
                    justice_drive *= max(0.25, 1.0 - (_clamp(justice.corruption, lo=0.0, hi=1.0) * 0.6))
                else:
                    justice_drive = 36.0 + (crime_sensitivity * 12.0)

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
                        and traits.bravery >= 0.45
                        and (offense_strength * 60.0) > best_score
                    ):
                        best_intent = "investigating"
                        best_score = offense_strength * 60.0
                        best_target = (offender_pos.x, offender_pos.y, offender_pos.z)
                        best_target_eid = offender_eid

            safety_pressure = (100.0 - needs.safety) * (1.2 - (traits.bravery * 0.7))
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

            social_pressure = (100.0 - needs.social) * (0.7 + (traits.empathy * 0.6))
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

            workplace_prop = _workplace_property(self.sim, occupation=occupation, routine=routine)
            home_prop = _home_property(self.sim, routine=routine)
            work_active = work_shift_active(
                self.sim,
                occupation=occupation,
                workplace_prop=workplace_prop,
                role=ai.role,
            )

            social_venue_pressure = (100.0 - needs.social) * (0.55 + (traits.empathy * 0.45))
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

            duty_score = traits.discipline * 45.0
            _sa = scoring_anchor or duty_anchor
            if ai.role in {"guard", "scout", "worker", "civilian", "thief"} and _sa:
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

class NPCInvestigateSystem(System):

    DEFAULT_MOVE_COOLDOWNS = {
        "investigating": 2,
        "protecting": 1,
        "helping_victim": 1,
        "reporting_incident": 2,
        "warning": 1,
        "chasing": 1,
        "scavenging": 2,
        "following": 1,
        "holding": 1,
        "seeking_social": 2,
        "seeking_companionship": 2,
        "seeking_safety": 1,
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
        global_stride = int(max(1, getattr(self.sim, "npc_move_tick_stride", 1)))

        moving_states = {
            "investigating",
            "protecting",
            "helping_victim",
            "reporting_incident",
            "warning",
            "chasing",
            "scavenging",
            "following",
            "holding",
            "seeking_social",
            "seeking_companionship",
            "seeking_safety",
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

            if ai.state in {"investigating", "seeking_social", "seeking_companionship", "protecting", "reporting_incident", "helping_victim", "warning"} and _manhattan(pos.x, pos.y, tx, ty) <= 1:
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
