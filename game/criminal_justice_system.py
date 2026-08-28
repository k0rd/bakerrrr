"""Extracted systems from ``game.systems``: CriminalJusticeSystem."""

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
    IncidentKnowledge,
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
from collections import Counter, deque
from copy import deepcopy
from engine.events import Event
from game.items import (
    CREDSTICK_ITEM_ID,
    ITEM_CATALOG,
    apply_item_durability_loss,
    credstick_total_credits,
    is_credstick_item,
    item_display_name,
    merge_item_stack_metadata,
    prepare_item_stack_metadata,
)
from game.appearance_loadout import (
    APPEARANCE_METADATA_KEY,
    APPEARANCE_SLOT_METADATA_KEY,
    APPEARANCE_WORN_METADATA_KEY,
    COSMETIC_COLOR_KEYS,
    appearance_loadout_for,
    cosmetic_variant_metadata,
    mark_inventory_instance_worn,
)
from game.item_semantics import inventory_has_phone
from game.incident_silencing import incident_case_cooperation_withheld
from game.dialogue_runtime import player_modal_active as _player_modal_active
from game.quick_travel_ramps import map_mode_active
from engine.systems import System
from game.system_support.offense_runtime import (
    ACTION_OFFENSE_BASE,
    ACTION_OFFENSE_CONTEXT_BONUS,
    ASSAULT_OFFENSE_CONTEXTS,
    CIVIC_WILDLIFE_OFFENSE_CONTEXTS,
    OFFICIAL_REPORTABLE_OFFENSE_CONTEXTS,
    PUBLIC_ORDER_OFFENSE_CONTEXTS,
    VIOLENT_OFFENSE_CONTEXTS,
    WITNESS_TAMPERING_OFFENSE_CONTEXTS,
    _emit_action_offense_event,
    _offense_notice_radius,
    _offense_score_for_action,
    _offense_tier,
)
from game.world_progression_systems import WorldStreamingSystem
from game.property_door_wait import DoorWaitSystem, _actor_in_live_combat, _door_knock_attempt
from game.checks import (
    crime_read_summary as _crime_read_summary,
    crime_sensitivity as _crime_sensitivity,
    justice_level as _justice_level,
    rumor_truth_read as _rumor_truth_read,
    social_read_axes as _social_read_axes,
)
from game.criminal_justice_runtime import (
    _clear_justice_restitution_claims,
    _decay_justice_records,
    _exonerate_provisional_justice_case,
    _grant_custody_release_grace,
    _justice_booking_anchor_for,
    _justice_held_property_snapshot,
    _justice_provisional_incident_rows,
    _justice_restitution_snapshot,
    _justice_snapshot,
    _justice_summary_rows,
    _mark_justice_in_custody,
    _observer_is_active_bodyguard,
    _record_justice_booking_completion,
    _record_justice_incident,
    _record_justice_questioning_resolution,
    _record_justice_restitution_claim,
    _release_justice_from_custody,
    _replace_justice_held_property,
    _store_justice_held_property,
    _set_provisional_justice_active_contribution,
    _justice_wanted_tier_for,
)
from game.justice_identity_runtime import (
    independent_supporting_reporter_eids,
    justice_case_for_incident,
    justice_case_recently_checked,
    justice_case_event_payload,
    justice_identity_state,
    provisional_attribution_read,
    record_justice_case_encounter,
    record_justice_identity_report,
    record_provisional_justice_attribution,
    subject_account_resolves_identity,
    unresolved_case_matches_for_actor,
)
from game.identity_evidence import (
    actor_identity_snapshot,
    build_witness_subject_account,
    description_match_score,
    preferred_subject_account,
    remember_presented_identity,
    subject_description_summary,
    transmitted_subject_account,
)
from game.justice_runtime import jurisdiction_for_position
from game.system_support.entity_naming import _entity_display_name
from game.system_support.actor_runtime import (
    _apply_downed_actor_state,
    _detail_tick_allowed,
    _entity_is_downed,
)
from game.system_support.ai_intent_runtime import _sync_ai_intent
from game.system_support.building_repair_runtime import (
    damage_record_repair_cost as _damage_record_repair_cost,
    property_damage_records as _property_damage_records,
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
from game.system_support.settlement_runtime import (
    _property_chunk_key,
    _track_entity_in_chunk_population,
)
from game.system_support.opportunity_knowledge_runtime import (
    rehydrate_entity_knowledge as _rehydrate_entity_knowledge,
)
from game.system_support.interaction_ordering import (
    _direction_step,
    _interaction_target_order_key,
    _manhattan,
    _normalized_direction,
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
    _trespass_label_from_score,
)
from engine.visibility import (
    has_line_of_sight as _shared_has_line_of_sight,
    observer_can_see_position as _shared_observer_can_see_position,
    update_player_visibility as _update_player_visibility,
)
from game.system_support.container_runtime import (
    ITEM_STOWED_CONTAINER_METADATA_KEY,
    _clear_inventory_container_assignments,
    _entry_stowed_container_instance,
    _inventory_entries_loose_for_container,
    _inventory_entries_stowed_in_container,
    _unlink_removed_item_from_gear,
)
from game.system_support.awareness_runtime import event_observation_accountability
from game.system_support.item_provenance_runtime import (
    evaluate_inventory_for_justice,
    justice_enforcement_profile,
)
from game.justice_force_runtime import (
    classify_lawful_force,
    force_payload,
    mitigated_force_severity,
)
from game.bounty_authority import bounty_action_authority, bounty_authority_from_stamped_data
from game.civic_records import record_civic_license_misuse
from game.purposeful_observation import (
    advance_purposeful_actor_observation,
    begin_purposeful_anchor_observation,
    begin_purposeful_report_search,
    finish_purposeful_observation,
    is_purposeful_observation,
    observation_purpose_profile,
    observation_watch_position,
    record_purposeful_canvas_contact,
    reject_purposeful_candidate,
    refresh_purposeful_observation,
)
from game.vision_scene_runtime import event_is_vision_only
from game.organizations import local_protective_pressure_snapshot
from game.skills import actor_skill
from game.player_businesses import (
    actor_player_business_employment,
    fire_actor_from_player_business,
    hire_actor_into_player_business,
    player_business_role_fit,
    player_business_staffing_targets,
)
from game.incident_runtime import incident_record, mark_incident_registry_changed
import random

THREAT_STATES = {"protecting", "investigating"}


class CriminalJusticeSystem(System):

    DETENTION_QUEUE_WINDOW = 30
    SCENE_APPREHENSION_WINDOW = 120
    NPC_WANTED_PICKUP_WINDOW = 180
    DETENTION_RADIUS = 10
    JUSTICE_SITE_SEARCH_RADIUS = 24
    PLAYER_BOOKING_RELEASE_GRACE_TICKS = 18
    SURRENDER_PROMPT_COOLDOWN_TICKS = 180
    SURRENDER_DIALOG_KIND = "justice_surrender"
    QUESTIONING_DIALOG_KIND = "justice_questioning"
    IDENTITY_CHECK_DIALOG_KIND = "justice_identity_check"
    CASE_CANVAS_DIALOG_KIND = "justice_case_canvas"
    BOOKING_ARCHETYPES = ("jail", "courthouse")
    JUSTICE_DEBT_KEY = "justice_fines"
    EVIDENCE_SURCHARGE_PER_ITEM = 35
    HOMICIDE_SEVERITY_SCORE = 96
    PLAYER_HOMICIDE_BOOKING_SURCHARGE = 120
    JUSTICE_RELEASE_JUMPSUIT_ITEM_ID = "orange_jumpsuit"
    JUSTICE_RELEASE_JUMPSUIT_SLOT = "full_body"
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
    PLAYER_IDENTITY_CHECK_NOTICE_RADIUS = 8
    PLAYER_IDENTITY_CHECK_PROMPT_RADIUS = 1
    PLAYER_IDENTITY_CHECK_SCAN_TICKS = 3
    IDENTITY_REFUSAL_SEVERITY = 24
    IDENTITY_DECEPTION_SEVERITY = 28
    JUSTICE_DETENTION_NOTICE_RADIUS = 10
    JUSTICE_DETENTION_CONTACT_RADIUS = 1
    BOUNTY_PICKUP_DISPATCH_RADIUS = 80
    BOUNTY_PICKUP_VERIFY_RADIUS = 3
    BOOKING_HOURS_BY_TIER = {
        "questioning": 1.0,
        "wanted": 3.0,
        "arrest_on_sight": 6.0,
    }
    EXONERATED_BOOKING_REVIEW_HOURS = 0.5
    NPC_BOOKING_HOURS_BY_TIER = {
        "wanted": 4.0,
        "arrest_on_sight": 8.0,
    }

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.pending_detentions = self._pending_detention_records()
        self.player_surrender_prompt = None
        self._next_player_identity_check_tick = 0
        self._streaming_system = None
        self.sim.events.subscribe("property_trespass", self.on_property_trespass)
        self.sim.events.subscribe("property_tamper", self.on_property_tamper)
        self.sim.events.subscribe("property_doorway_obstruction", self.on_property_doorway_obstruction)
        self.sim.events.subscribe("item_stolen", self.on_item_stolen)
        self.sim.events.subscribe("action_offense", self.on_action_offense)
        self.sim.events.subscribe("npc_killed", self.on_npc_killed)
        self.sim.events.subscribe("justice_mutual_fight_observed", self.on_justice_mutual_fight_observed)
        self.sim.events.subscribe("incident_authority_reported", self.on_incident_authority_reported)
        self.sim.events.subscribe("property_interact", self.on_property_interact)
        self.sim.events.subscribe("npc_interact", self.on_npc_interact)
        self.sim.events.subscribe("npc_surrendered", self.on_npc_surrendered)
        self.sim.events.subscribe("bounty_pickup_dispatch_requested", self.on_bounty_pickup_dispatch_requested)
        self.sim.events.subscribe("justice_surrender_choice", self.on_justice_surrender_choice)
        self.sim.events.subscribe("justice_questioning_choice", self.on_justice_questioning_choice)
        self.sim.events.subscribe("justice_identity_check_choice", self.on_justice_identity_check_choice)
        self.sim.events.subscribe("justice_case_canvas_choice", self.on_justice_case_canvas_choice)
        self.sim.events.subscribe("justice_report_candidate_contact", self.on_justice_report_candidate_contact)
        self.sim.events.subscribe("justice_case_canvas_contact", self.on_justice_case_canvas_contact)
        self.sim.events.subscribe("actor_detained", self.on_actor_detained_case_correction)

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

    def _pending_detention_records(self):
        state = self._justice_state()
        records = state.get("pending_detentions")
        if not isinstance(records, dict):
            records = {}
            state["pending_detentions"] = records
        return records

    def _identity_check_approach_records(self):
        state = self._justice_state()
        records = state.get("identity_check_approaches")
        if not isinstance(records, dict):
            records = {}
            state["identity_check_approaches"] = records
        return records

    def _detention_approach_records(self):
        state = self._justice_state()
        records = state.get("detention_approaches")
        if not isinstance(records, dict):
            records = {}
            state["detention_approaches"] = records
        return records

    def _scene_apprehension_records(self):
        state = self._justice_state()
        records = state.get("scene_apprehensions")
        if not isinstance(records, dict):
            records = {}
            state["scene_apprehensions"] = records
        return records

    def _bounty_pickup_records(self):
        state = self._justice_state()
        records = state.get("bounty_pickups")
        if not isinstance(records, dict):
            records = {}
            state["bounty_pickups"] = records
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
        provisional=False,
        source_case_id=None,
        source_incident_id=None,
        attribution_basis="",
        repeat_scope="",
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
            provisional=provisional,
            source_case_id=source_case_id,
            source_incident_id=source_incident_id,
            attribution_basis=attribution_basis,
            repeat_scope=repeat_scope,
        )
        if change is not None:
            self._emit_change_events(change, source_event=source_event, reason=incident_type)
            self._queue_npc_wanted_detention(change, reason=incident_type)
        return change

    def _mutual_fight_context_label(self, context):
        key = str(context or "").strip().lower()
        return {
            "unarmed_assault": "unarmed blows",
            "melee_assault": "armed melee",
            "armed_assault": "firearms",
            "explosive_discharge": "explosives or rockets",
        }.get(key, key.replace("_", " ") or "violence")

    def _latest_mutual_fight_questioning_payload(self, offender_eid=None):
        offender_eid = self.player_eid if offender_eid is None else offender_eid
        state = getattr(self.sim, "world_traits", None)
        if not isinstance(state, dict):
            return {}
        rows = state.get("justice_mutual_fight_questioning")
        if not isinstance(rows, dict):
            return {}
        row = rows.get(str(offender_eid))
        return dict(row) if isinstance(row, dict) else {}

    def _remember_mutual_fight_questioning_payload(self, offender_eid, payload):
        if offender_eid is None or not isinstance(payload, dict):
            return
        state = getattr(self.sim, "world_traits", None)
        if not isinstance(state, dict):
            self.sim.world_traits = {}
            state = self.sim.world_traits
        rows = state.setdefault("justice_mutual_fight_questioning", {})
        if not isinstance(rows, dict):
            rows = {}
            state["justice_mutual_fight_questioning"] = rows
        rows[str(offender_eid)] = dict(payload)

    def _mutual_fight_questioning_lines(self, offender_eid=None):
        payload = self._latest_mutual_fight_questioning_payload(offender_eid)
        if not payload:
            return []
        incident_id = payload.get("incident_id")
        context_label = self._mutual_fight_context_label(payload.get("context"))
        witness_count = int(payload.get("witness_count", 0) or 0)
        other_eid = payload.get("other_participant_eid")
        if other_eid is not None:
            other_text = " with the other person"
        else:
            other_text = ""
        lines = [
            f"Officer read: they saw blows both ways{other_text}; weapon level: {context_label}.",
        ]
        if incident_id:
            if witness_count > 1:
                lines.append(f"They have {witness_count} firsthand statement(s) tied to incident #{incident_id}.")
            else:
                lines.append(f"They have one firsthand statement tied to incident #{incident_id}.")
        return lines

    def _humanoid_participants(self, participant_eids):
        results = []
        ais = self.sim.ecs.get(AI)
        identities = self.sim.ecs.get(CreatureIdentity)
        for eid in tuple(participant_eids or ()):
            try:
                value = int(eid)
            except (TypeError, ValueError):
                continue
            ai = ais.get(value)
            role = str(getattr(ai, "role", "") or "").strip().lower()
            if role == "wildlife":
                continue
            identity = identities.get(value)
            taxonomy = str(getattr(identity, "taxonomy_class", "") or "").strip().lower()
            creature_type = str(getattr(identity, "creature_type", "") or "").strip().lower()
            if taxonomy in {"machine", "vehicle"} or creature_type in {"animal", "machine"}:
                continue
            if value not in results:
                results.append(value)
        return tuple(results)

    def _event_accountability(self, event, *, offender_eid=None, allow_position_backfill=False):
        return event_observation_accountability(
            self.sim,
            event,
            offender_eid=offender_eid,
            default_channels=("actor_witness",),
            use_legacy_witness_fallback=False,
            allow_position_backfill=bool(allow_position_backfill),
        )

    def _event_has_justice_report_channel(self, event, *, offender_eid=None, allow_position_backfill=False):
        observation = self._event_accountability(
            event,
            offender_eid=offender_eid,
            allow_position_backfill=allow_position_backfill,
        )
        report_channels = {
            str(channel or "").strip().lower()
            for channel in tuple(observation.get("accountable_observation_channels", ()) or ())
        }
        if report_channels.intersection({"authority_report", "official_report", "camera_owner_feed"}):
            return True
        if "actor_witness" not in report_channels:
            return False
        for observer_eid in tuple(observation.get("accountable_observer_eids", ()) or ()):
            enforcer, _law_drive, _priority = self._actor_is_enforcer(observer_eid)
            if enforcer and self._actor_has_report_device(observer_eid):
                return True
        return False

    def _actor_has_report_device(self, eid):
        inventory = self.sim.ecs.get(Inventory).get(eid)
        return inventory_has_phone(inventory, item_catalog=ITEM_CATALOG)

    def _firsthand_account_for(self, observer_eid, offender_eid):
        enforcer, _law_drive, _priority = self._actor_is_enforcer(observer_eid)
        source_kind = "expert_justice_witness" if enforcer else "witnessed"
        return build_witness_subject_account(
            self.sim,
            observer_eid,
            offender_eid,
            source_kind=source_kind,
            confidence=1.0,
        )

    def _agency_visual_identity_account(self, incident, report_data):
        """Resolve a transmitted visual record against registered identity.

        The witness still owns only their visual account.  This upgrade exists
        solely inside justice casework after a real phone photograph or fixed
        camera-network frame arrives. A strongly obscured face or an actor
        without a registered personal name remains unresolved. Drone feeds do
        not gain stored-footage semantics through this path.
        """

        account = deepcopy(report_data.get("subject_account")) if isinstance(report_data.get("subject_account"), dict) else None
        if not isinstance(incident, dict) or not isinstance(account, dict):
            return account
        method = str(report_data.get("method", "") or "").strip().lower()
        phone_photo = method == "cell_phone"
        fixed_camera_frame = bool(
            method == "camera_network"
            and report_data.get("fixed_camera_frame")
            and str(report_data.get("visual_source_kind", "") or "").strip().lower() == "camera"
            and report_data.get("visual_source_eid") is None
        )
        if not phone_photo and not fixed_camera_frame:
            return account
        observation = account.get("observation") if isinstance(account.get("observation"), dict) else {}
        if not isinstance(account.get("description"), dict) or not account.get("description"):
            return account
        if phone_photo and not (
            bool(observation.get("durable_visual_reference", False))
            and bool(observation.get("exact_description", False))
        ):
            return account
        if float(observation.get("face_visibility", 0.0) or 0.0) < 0.52:
            return account
        subject_eid = incident.get("primary_actor_eid")
        try:
            subject_eid = int(subject_eid)
        except (TypeError, ValueError):
            return account
        identity = actor_identity_snapshot(self.sim, subject_eid) or {}
        name = str(identity.get("personal_name", "") or "").strip()
        taxonomy = str(identity.get("taxonomy_class", "") or "").strip().lower()
        creature_type = str(identity.get("creature_type", "") or "").strip().lower()
        if not name or (taxonomy and taxonomy != "hominid") or (creature_type and creature_type != "human"):
            return account

        if fixed_camera_frame:
            observation = dict(observation)
            observation.update({
                "durable_visual_reference": True,
                "description_basis": "fixed_camera_frame",
                "transmitted_visual_method": "camera_network",
            })
            account["observation"] = observation
        account.update({
            "identification": "verified",
            "suspect_eid": subject_eid,
            "presented_name": name,
            "identity_confidence": 0.97,
            "agency_resolution": {
                "basis": "photo_registry_match" if phone_photo else "camera_registry_match",
                "matched_tick": int(getattr(self.sim, "tick", 0)),
                "source_method": method,
                "confidence": 0.97,
            },
        })
        return account

    def _firsthand_scene_enforcers(self, event, offender_eid, *, observation=None, include_victim=False):
        observation = observation if isinstance(observation, dict) else self._event_accountability(
            event,
            offender_eid=offender_eid,
        )
        channels = {
            str(channel or "").strip().lower()
            for channel in tuple(observation.get("accountable_observation_channels", ()) or ())
        }
        candidates = []
        if "actor_witness" in channels:
            candidates.extend(tuple(observation.get("accountable_observer_eids", ()) or ()))
        if include_victim:
            victim_eid = event.data.get("victim_eid", event.data.get("target_eid"))
            if victim_eid is not None:
                candidates.append(victim_eid)

        results = []
        for raw_eid in candidates:
            try:
                observer_eid = int(raw_eid)
            except (TypeError, ValueError):
                continue
            if observer_eid == int(offender_eid) or observer_eid in results:
                continue
            enforcer, _law_drive, _priority = self._actor_is_enforcer(observer_eid)
            if enforcer:
                results.append(observer_eid)
        return tuple(results)

    def _resolve_actionable_event_subject(
        self,
        event,
        offender_eid,
        *,
        observation=None,
        include_victim=False,
        allow_position_backfill=False,
    ):
        """Resolve a name when possible, while preserving live body continuity.

        An officer does not need to know a legal identity to stop the exact
        person they just witnessed.  Unknown subjects stay scene-bound until
        contact; a report may separately distribute their description.
        """

        observation = observation if isinstance(observation, dict) else self._event_accountability(
            event,
            offender_eid=offender_eid,
            allow_position_backfill=allow_position_backfill,
        )
        scene_enforcers = self._firsthand_scene_enforcers(
            event,
            offender_eid,
            observation=observation,
            include_victim=include_victim,
        )
        resolved_eid = None
        if self._event_has_justice_report_channel(
            event,
            offender_eid=offender_eid,
            allow_position_backfill=allow_position_backfill,
        ):
            resolved_eid = self._resolve_reportable_event_subject(event, offender_eid)
        if resolved_eid is None:
            for observer_eid in scene_enforcers:
                resolved_eid = subject_account_resolves_identity(
                    self._firsthand_account_for(observer_eid, offender_eid)
                )
                if resolved_eid is not None:
                    break
        return resolved_eid, scene_enforcers

    def _mark_incident_accounted(self, incident_id, field="justice_accounted"):
        incident = incident_record(self.sim, incident_id)
        if not isinstance(incident, dict):
            return None
        incident[str(field or "justice_accounted")] = True
        incident["justice_accounted_tick"] = int(getattr(self.sim, "tick", 0))
        mark_incident_registry_changed(self.sim)
        return incident

    def _emit_identity_case_change(self, case, *, changed=False, newly_resolved=False):
        if newly_resolved and isinstance(case, dict):
            self._resolve_case_provisional_aftermath(case)
        payload = justice_case_event_payload(case)
        if not changed or not payload:
            return payload
        self.sim.emit(Event(
            "justice_identity_case_updated",
            newly_resolved=bool(newly_resolved),
            **payload,
        ))
        if not payload.get("resolved_subject_eid") and payload.get("subject_identification") != "unknown":
            self.sim.emit(Event("justice_description_distributed", **payload))
        return payload

    def _resolve_reportable_event_subject(self, event, offender_eid):
        """Open/update the event's identity case from actual observer accounts."""

        incident_id = event.data.get("knowledge_incident_id", event.data.get("incident_id"))
        incident = incident_record(self.sim, incident_id)
        direct_account = event.data.get("subject_account") if isinstance(event.data.get("subject_account"), dict) else None
        if not isinstance(incident, dict):
            if isinstance(direct_account, dict):
                return subject_account_resolves_identity(direct_account)
            for raw_observer_eid in tuple(event.data.get("accountable_observer_eids", event.data.get("observer_eids", ())) or ()):
                try:
                    observer_eid = int(raw_observer_eid)
                except (TypeError, ValueError):
                    continue
                account = self._firsthand_account_for(observer_eid, offender_eid)
                resolved = subject_account_resolves_identity(account)
                if resolved is not None:
                    return resolved
            return None
        observers = tuple(event.data.get("accountable_observer_eids", event.data.get("observer_eids", ())) or ())
        best_account = {}
        last_case = None
        if isinstance(direct_account, dict):
            best_account = dict(direct_account)
            case, changed, newly_resolved = record_justice_identity_report(
                self.sim,
                incident,
                {
                    "incident_id": incident_id,
                    "reporter_eid": event.data.get("reporter_eid", event.data.get("npc_eid")),
                    "method": event.data.get("method", "official_identification"),
                    "subject_account": direct_account,
                },
            )
            last_case = case
            self._emit_identity_case_change(case, changed=changed, newly_resolved=newly_resolved)
        for raw_observer_eid in observers:
            try:
                observer_eid = int(raw_observer_eid)
            except (TypeError, ValueError):
                continue
            knowledge = self.sim.ecs.get(IncidentKnowledge).get(observer_eid)
            record = knowledge.records.get(int(incident_id)) if knowledge is not None else None
            account = (record or {}).get("subject_account") if isinstance((record or {}).get("subject_account"), dict) else None
            firsthand_account = self._firsthand_account_for(observer_eid, offender_eid)
            account = preferred_subject_account(account, firsthand_account)
            if isinstance(record, dict):
                record["subject_account"] = dict(account)
            best_account = preferred_subject_account(best_account, account)
            case, changed, newly_resolved = record_justice_identity_report(
                self.sim,
                incident,
                {
                    "incident_id": incident_id,
                    "reporter_eid": observer_eid,
                    "method": "direct_justice_witness",
                    "subject_account": account,
                },
            )
            last_case = case
            self._emit_identity_case_change(case, changed=changed, newly_resolved=newly_resolved)
        if not observers and isinstance(event.data.get("subject_account"), dict):
            best_account = dict(event.data.get("subject_account"))
            case, changed, newly_resolved = record_justice_identity_report(
                self.sim,
                incident,
                {
                    "incident_id": incident_id,
                    "reporter_eid": event.data.get("reporter_eid", event.data.get("npc_eid")),
                    "method": event.data.get("method", "official_report"),
                    "subject_account": best_account,
                },
            )
            last_case = case
            self._emit_identity_case_change(case, changed=changed, newly_resolved=newly_resolved)
        payload = justice_case_event_payload(last_case)
        incident["officially_reported"] = True
        incident.setdefault("reported_tick", int(getattr(self.sim, "tick", 0)))
        incident["justice_identity_case_id"] = payload.get("case_id")
        resolved_eid = payload.get("resolved_subject_eid")
        incident["justice_identity_unresolved"] = resolved_eid is None
        mark_incident_registry_changed(self.sim)
        return resolved_eid

    def _queue_npc_wanted_detention(self, change, *, reason="justice_record"):
        if not isinstance(change, dict):
            return False
        try:
            offender_eid = int(change.get("eid"))
        except (TypeError, ValueError):
            return False
        if offender_eid <= 0 or offender_eid == self.player_eid:
            return False
        positions = self.sim.ecs.get(Position)
        if positions.get(offender_eid) is None:
            return False
        snapshot = _justice_snapshot(self.sim, offender_eid)
        if bool(snapshot.get("in_custody", False)):
            return False
        tier = str(snapshot.get("wanted_tier", change.get("after_tier", "clear")) or "clear").strip().lower()
        if tier not in {"wanted", "arrest_on_sight"}:
            return False

        tick = int(getattr(self.sim, "tick", 0))
        window = max(int(self.DETENTION_QUEUE_WINDOW), int(self.NPC_WANTED_PICKUP_WINDOW))
        expires_at = tick + window
        current_expires = self.pending_detentions.get(offender_eid)
        if current_expires is not None and int(current_expires) >= int(expires_at):
            return False
        self.pending_detentions[offender_eid] = int(expires_at)
        self.sim.emit(Event(
            "npc_detention_queued",
            eid=offender_eid,
            wanted_tier=tier,
            before_tier=str(change.get("before_tier", "clear") or "clear").strip().lower() or "clear",
            after_tier=str(change.get("after_tier", tier) or tier).strip().lower() or tier,
            before_score=int(change.get("before_score", 0) or 0),
            after_score=int(change.get("after_score", 0) or 0),
            source_event=str((change.get("incident") or {}).get("source_event", "") or "").strip().lower(),
            reason=str(reason or "justice_record").strip().lower(),
            expires_at=int(expires_at),
        ))
        return True

    def _violent_offense_allowed(self, offender_eid, context):
        if context not in VIOLENT_OFFENSE_CONTEXTS:
            return True
        return offender_eid == self.player_eid

    def _remember_force_context(self, offender_eid, force_read, *, data=None):
        if offender_eid is None or not isinstance(force_read, dict):
            return
        state = getattr(self.sim, "world_traits", None)
        if not isinstance(state, dict):
            self.sim.world_traits = {}
            state = self.sim.world_traits
        force_state = state.setdefault("justice_force_contexts", {})
        if not isinstance(force_state, dict):
            force_state = {}
            state["justice_force_contexts"] = force_state
        payload = force_payload(force_read)
        payload["recordable"] = bool(force_read.get("recordable", True))
        payload["suppressed"] = bool(force_read.get("suppressed", False))
        if isinstance(data, dict):
            for field in ("target_eid", "victim_eid", "context", "action"):
                value = data.get(field)
                if value not in (None, "", ()):
                    payload[field] = value
        payload["tick"] = int(getattr(self.sim, "tick", 0))
        force_state[str(offender_eid)] = payload

    def _record_bounty_misuse_review(self, offender_eid, force_read, *, data=None, factual_offender_eid=None):
        if offender_eid is None or not isinstance(force_read, dict):
            return None
        if not bool(force_read.get("bounty_credential_misuse")):
            return None
        if factual_offender_eid is not None and not self._same_eid_value(offender_eid, factual_offender_eid):
            # A mistaken identity case can carry the assault allegation, but it
            # must not silently edit another person's identity-bound license.
            return None
        data = data if isinstance(data, dict) else {}
        return record_civic_license_misuse(
            self.sim,
            offender_eid,
            "bounty",
            reason=str(force_read.get("bounty_authority_reason", force_read.get("force_reason", "outside posted authority")) or "outside posted authority").strip(),
            action=str(data.get("action", force_read.get("bounty_action_kind", "force")) or "force").strip().lower(),
            misuse_kind=str(force_read.get("bounty_action_kind", "") or "").strip().lower(),
            severity_score=data.get("offense_score", data.get("severity_score", data.get("severity", 0))),
            target_eid=data.get("target_eid", data.get("victim_eid")),
            incident_id=data.get("knowledge_incident_id", data.get("incident_id")),
        )

    def _latest_force_context_row(self, offender_eid=None):
        offender_eid = self.player_eid if offender_eid is None else offender_eid
        state = getattr(self.sim, "world_traits", None)
        if not isinstance(state, dict):
            return {}
        force_state = state.get("justice_force_contexts")
        if not isinstance(force_state, dict):
            return {}
        row = force_state.get(str(offender_eid))
        return dict(row) if isinstance(row, dict) else {}

    def _latest_force_context(self, offender_eid=None):
        row = self._latest_force_context_row(offender_eid)
        if not row:
            return {"force_context": "unclear", "force_reason": "", "severity_mitigation": 0}
        return force_payload(row)

    def _force_event_payload(self, offender_eid):
        return self._latest_force_context(offender_eid)

    def _force_context_line(self, offender_eid=None):
        payload = self._latest_force_context(self.player_eid if offender_eid is None else offender_eid)
        context = str(payload.get("force_context", "unclear") or "unclear").strip().lower()
        reason = str(payload.get("force_reason", "") or "").strip()
        if bool(payload.get("bounty_credential_misuse")):
            return f"Credential read: the posted recovery did not cover that force ({reason})." if reason else "Credential read: the posted recovery did not cover that force."
        if context == "bounty_recovery":
            return f"Recovery read: the force stayed inside a matching posted pickup ({reason})." if reason else "Recovery read: the force stayed inside a matching posted pickup."
        if context == "lawful_defense":
            return f"Force read: they read the violence as self-defense ({reason})." if reason else "Force read: they read the violence as self-defense."
        if context == "defense_of_property":
            return f"Force read: they read the violence as property defense ({reason})." if reason else "Force read: they read the violence as property defense."
        if context == "defense_of_other":
            return f"Force read: they read the violence as defense of another person ({reason})." if reason else "Force read: they read the violence as defense of another person."
        if context == "mutual_fight":
            return f"Force read: they read the violence as a mutual fight ({reason})." if reason else "Force read: they read the violence as a mutual fight."
        if context == "criminal_attack":
            return f"Force read: they do not have a defensive threat in the observed scene ({reason})." if reason else "Force read: they do not have a defensive threat in the observed scene."
        return ""

    def _questioning_skill_bonus(self, choice_id):
        choice_id = str(choice_id or "").strip().lower()
        if choice_id not in {"explain", "deflect"}:
            return 0.0
        conversation = float(actor_skill(self.sim, self.player_eid, "conversation", default=5.0))
        streetwise = float(actor_skill(self.sim, self.player_eid, "streetwise", default=5.0))
        score = (conversation * 0.58) + (streetwise * 0.42)
        if choice_id == "explain":
            return max(0.0, min(0.16, (score - 5.0) * 0.04))
        return max(0.0, min(0.08, (score - 6.0) * 0.025))

    def _player_case_misdirection_options(self, incident_id):
        """Return event-time people the player can honestly remember describing.

        Participant accounts are frozen when the incident is learned.  Reading
        only that one bounded record keeps this dialogue from recovering a
        person's current clothes, location, or canonical identity by scanning
        the live world.
        """

        try:
            incident_id = int(incident_id)
        except (TypeError, ValueError):
            return ()
        knowledge = self.sim.ecs.get(IncidentKnowledge).get(self.player_eid)
        record = knowledge.records.get(incident_id) if knowledge is not None else None
        participants = record.get("participant_accounts") if isinstance(record, dict) else None
        if not isinstance(participants, dict):
            return ()

        rows = []
        for raw_role in sorted(participants):
            role = str(raw_role or "").strip().lower().replace(" ", "_")
            if not role.startswith(("witness_", "bystander_")):
                continue
            account = participants.get(raw_role)
            description = account.get("description") if isinstance(account, dict) else None
            if not isinstance(description, dict) or not description:
                continue
            summary = subject_description_summary(description)
            if summary == "a person with few reliable visual details":
                continue
            topic_id = f"misdirect_{role}"
            rows.append({
                "topic_id": topic_id,
                "role": role,
                "role_label": role.replace("_", " "),
                "description_summary": summary,
                "account": deepcopy(account),
            })
        return tuple(rows)

    def _justice_misdirection_read(self, npc_eid, prompt, option, case):
        """Resolve a bounded social contest without consuming global RNG state."""

        prompt = prompt if isinstance(prompt, dict) else {}
        option = option if isinstance(option, dict) else {}
        case = case if isinstance(case, dict) else {}
        match = prompt.get("match") if isinstance(prompt.get("match"), dict) else {}
        account = option.get("account") if isinstance(option.get("account"), dict) else {}
        observation = account.get("observation") if isinstance(account.get("observation"), dict) else {}

        conversation = float(actor_skill(self.sim, self.player_eid, "conversation", default=5.0))
        player_streetwise = float(actor_skill(self.sim, self.player_eid, "streetwise", default=5.0))
        officer_perception = float(actor_skill(self.sim, npc_eid, "perception", default=5.0))
        officer_streetwise = float(actor_skill(self.sim, npc_eid, "streetwise", default=5.0))
        player_score = ((conversation * 0.56) + (player_streetwise * 0.44)) / 10.0
        officer_score = ((officer_perception * 0.62) + (officer_streetwise * 0.38)) / 10.0

        source_credibility = 0.0
        framed_resistance = 0.0
        social = self.sim.ecs.get(NPCSocial).get(npc_eid)
        bonds = social.bonds if isinstance(social, NPCSocial) and isinstance(social.bonds, dict) else {}
        player_bond = bonds.get(self.player_eid)
        if isinstance(player_bond, dict):
            trust = max(0.0, min(1.0, float(player_bond.get("trust", 0.5) or 0.0)))
            closeness = max(0.0, min(1.0, float(player_bond.get("closeness", 0.5) or 0.0)))
            source_credibility = ((trust - 0.5) * 0.14) + ((closeness - 0.5) * 0.05)
        try:
            framed_eid = int(account.get("suspect_eid")) if account.get("suspect_eid") is not None else None
        except (TypeError, ValueError):
            framed_eid = None
        framed_bond = bonds.get(framed_eid) if framed_eid is not None else None
        if isinstance(framed_bond, dict):
            trust = max(0.0, min(1.0, float(framed_bond.get("trust", 0.0) or 0.0)))
            protectiveness = max(0.0, min(1.0, float(framed_bond.get("protectiveness", 0.0) or 0.0)))
            framed_resistance = (trust * 0.08) + (protectiveness * 0.07)

        memory_quality = max(0.0, min(1.0, float(observation.get("quality", 0.5) or 0.0)))
        match_score = max(0.0, min(1.0, float(match.get("score", 0.0) or 0.0)))
        evidence_weight = max(0.0, min(1.0, float(match.get("evidence_weight", 0.0) or 0.0)))
        conflict_relief = min(0.12, max(0, int(case.get("report_conflict_count", 0) or 0)) * 0.04)
        chance = (
            0.56
            + ((player_score - officer_score) * 0.50)
            + ((memory_quality - 0.5) * 0.14)
            + source_credibility
            + conflict_relief
            - (max(0.0, match_score - 0.62) * 0.20)
            - (max(0.0, evidence_weight - 0.28) * 0.16)
            - framed_resistance
        )
        chance = max(0.06, min(0.92, chance))
        roll = random.Random(
            f"{self.sim.seed}:justice-misdirection:{prompt.get('case_id')}:{int(npc_eid or 0)}:"
            f"{int(prompt.get('opened_tick', getattr(self.sim, 'tick', 0)) or 0)}:{option.get('role', '')}"
        ).random()
        return {
            "succeeded": bool(roll < chance),
            "chance": round(chance, 3),
            "roll": round(roll, 3),
            "memory_quality": round(memory_quality, 3),
            "source_credibility": round(source_credibility, 3),
            "framed_resistance": round(framed_resistance, 3),
        }

    def _justice_misdirection_account(self, option, read):
        option = option if isinstance(option, dict) else {}
        source = option.get("account") if isinstance(option.get("account"), dict) else {}
        claim = {
            "identification": "described",
            "suspect_eid": None,
            "presented_name": "",
            "identity_confidence": 0.0,
            "description": source.get("description") if isinstance(source.get("description"), dict) else {},
            "observation": source.get("observation") if isinstance(source.get("observation"), dict) else {},
        }
        confidence = 0.72 + (max(0.0, min(1.0, float((read or {}).get("memory_quality", 0.5) or 0.0))) * 0.18)
        return transmitted_subject_account(
            claim,
            channel="player_misdirection",
            source_eid=self.player_eid,
            confidence=confidence,
            propagation_depth=0,
            preserve_reporter_account=False,
        )

    def _record_player_case_misdirection_attempt(self, case, npc_eid, option, read, *, accepted):
        if not isinstance(case, dict):
            return None
        option = option if isinstance(option, dict) else {}
        read = read if isinstance(read, dict) else {}
        row = {
            "tick": int(getattr(self.sim, "tick", 0)),
            "actor_eid": int(self.player_eid),
            "officer_eid": int(npc_eid) if npc_eid is not None else -1,
            "role": str(option.get("role", "") or ""),
            "description_summary": str(option.get("description_summary", "") or ""),
            "accepted": bool(accepted),
            "chance": float(read.get("chance", 0.0) or 0.0),
            "roll": float(read.get("roll", 0.0) or 0.0),
        }
        attempts = list(case.get("misdirection_attempts", ()) or ())
        attempts.append(row)
        case["misdirection_attempts"] = attempts[-16:]
        return row

    def _accept_player_case_misdirection(self, npc_eid, prompt, option, read):
        """Record the believed statement and give this officer a real false lead."""

        prompt = prompt if isinstance(prompt, dict) else {}
        option = option if isinstance(option, dict) else {}
        incident_id = prompt.get("incident_id")
        incident = incident_record(self.sim, incident_id)
        if not isinstance(incident, dict):
            return None
        account = self._justice_misdirection_account(option, read)
        prompt_kind = str(prompt.get("kind", "") or "").strip().lower()
        lead_source = (
            "player_identity_check"
            if prompt_kind == self.IDENTITY_CHECK_DIALOG_KIND
            else "player_investigator_interview"
        )
        case, changed, newly_resolved = record_justice_identity_report(
            self.sim,
            incident,
            {
                "incident_id": incident_id,
                "reporter_eid": self.player_eid,
                "method": f"{lead_source}_misdirection_{option.get('role', 'person')}",
                "subject_account": account,
            },
        )
        if not isinstance(case, dict):
            return None

        # This is not canonical truth.  It is the account the active
        # investigator accepted, and later reports may contradict or replace
        # it through the ordinary evidence path.
        case["best_subject_account"] = deepcopy(account)
        case["last_accepted_lead_source"] = lead_source
        case["last_accepted_lead_reporter_eid"] = int(self.player_eid)
        case["last_accepted_lead_tick"] = int(getattr(self.sim, "tick", 0))
        self._record_player_case_misdirection_attempt(
            case,
            npc_eid,
            option,
            read,
            accepted=True,
        )
        self._emit_identity_case_change(case, changed=changed, newly_resolved=newly_resolved)

        ai = self.sim.ecs.get(AI).get(npc_eid)
        officer_pos = self._position_for(npc_eid)
        if ai is not None and officer_pos is not None:
            try:
                reported_position = (
                    int(case.get("x")),
                    int(case.get("y")),
                    int(case.get("z", 0) or 0),
                )
            except (TypeError, ValueError):
                reported_position = None
            if reported_position is not None:
                current_position = (int(officer_pos.x), int(officer_pos.y), int(officer_pos.z))
                context = begin_purposeful_report_search(
                    self.sim,
                    npc_eid,
                    reported_position,
                    subject_account=account,
                    incident_id=incident_id,
                    reporter_eid=self.player_eid,
                    knowledge_channel=lead_source,
                    approach_position=current_position,
                    report_conflict_count=case.get("report_conflict_count", 0),
                    canvas_enabled=True,
                    canvas_until_exhausted=True,
                    casework_kind=str(prompt.get("casework_kind", "") or "").strip().lower() or "patrol_canvas",
                )
                context["rejected_candidate_eids"] = (int(self.player_eid),)
                context["canvassed_eids"] = (int(self.player_eid),)
                ai.investigation_context = context
                ai.state = "investigating"
                ai.target = current_position
                ai.target_eid = None
                ai.incident_id = int(incident_id)
                ai.response_role = "peace_dispatched"
                ai.suppress_report_for_incident_id = int(incident_id)
                will = self.sim.ecs.get(NPCWill).get(npc_eid)
                if will is not None:
                    will.intent = "investigating"
                    will.score = max(62.0, float(getattr(will, "score", 0.0) or 0.0))
                    will.target = current_position
                    will.target_eid = None
                    will.last_tick = int(getattr(self.sim, "tick", 0))

        self.sim.emit(Event(
            "justice_false_lead_accepted",
            eid=self.player_eid,
            officer_eid=npc_eid,
            incident_id=incident_id,
            case_id=case.get("case_id"),
            framed_role=option.get("role"),
            description_summary=option.get("description_summary"),
        ))
        return account

    def _incident_type_from_context(self, context):
        return {
            "contraband_trade": "contraband",
            "contraband_use": "contraband",
            "unarmed_assault": "unarmed_assault",
            "melee_assault": "melee_assault",
            "armed_assault": "armed_assault",
            "explosive_discharge": "explosive_discharge",
            "homicide": "homicide",
            "unlicensed_hunting": "hunting_violation",
            "unsafe_hunting": "hunting_violation",
            "protected_wildlife_hunting": "protected_species_violation",
        }.get(context, context)

    def _provisional_case_crime_profile(self, case, incident):
        """Return the factual offense profile that a mistaken attribution may use."""

        if not isinstance(case, dict) or not isinstance(incident, dict):
            return None
        severity = max(0, int(incident.get("severity", case.get("severity", 0)) or 0))
        if severity <= 0:
            return None
        kind = str(incident.get("kind", case.get("kind", "")) or "").strip().lower()
        profile = {
            "incident_type": "",
            "source_event": kind,
            "severity": severity,
            "note": str(incident.get("note", kind) or kind).strip(),
        }
        if kind in {"camera_alert", "property_trespass"}:
            profile.update(incident_type="trespass", source_event="property_trespass")
        elif kind == "property_tamper":
            profile.update(incident_type="tamper", source_event="property_tamper")
        elif kind == "item_stolen":
            profile.update(incident_type="theft", source_event="item_stolen")
        elif kind == "homicide":
            actual_eid = incident.get("primary_actor_eid")
            if actual_eid is None:
                return None
            homicide_data = dict(incident)
            homicide_data.setdefault("context", "homicide")
            homicide_data.setdefault("action", "homicide")
            homicide_data.setdefault("target_eid", incident.get("victim_eid"))
            force_read = self._homicide_force_read(homicide_data, actual_eid)
            severity = mitigated_force_severity(max(self.HOMICIDE_SEVERITY_SCORE, severity), force_read)
            if severity <= 0:
                return None
            profile.update(incident_type="homicide", source_event="npc_killed", severity=severity)
        elif kind == "action_offense":
            context = str(incident.get("context", case.get("context", "")) or "").strip().lower()
            if not context:
                context = str(incident.get("merge_subject", case.get("merge_subject", "")) or "").split(":")[-1].strip().lower()
            if context not in {
                "contraband_trade",
                "contraband_use",
                *VIOLENT_OFFENSE_CONTEXTS,
                *CIVIC_WILDLIFE_OFFENSE_CONTEXTS,
                *WITNESS_TAMPERING_OFFENSE_CONTEXTS,
                *PUBLIC_ORDER_OFFENSE_CONTEXTS,
            }:
                return None
            if context in VIOLENT_OFFENSE_CONTEXTS:
                actual_eid = incident.get("primary_actor_eid")
                if actual_eid is None:
                    return None
                force_read = classify_lawful_force(self.sim, incident, offender_eid=actual_eid)
                severity = mitigated_force_severity(severity, force_read)
                if severity <= 0:
                    return None
            profile.update(
                incident_type=self._incident_type_from_context(context),
                source_event="action_offense",
                severity=severity,
                note=f"{str(incident.get('action', 'action') or 'action').strip().lower()}/{context}",
            )
        else:
            return None
        if profile.get("incident_type") not in {
            "trespass", "tamper", "theft", "contraband", "unarmed_assault", "melee_assault",
            "armed_assault", "explosive_discharge", "homicide", "hunting_violation", "protected_species_violation",
            "witness_intimidation", "witness_bribery",
            "indecent_exposure",
        }:
            return None
        return profile

    def _record_provisional_attribution_consequence(
        self,
        case,
        actor_eid,
        *,
        officer_eid=None,
        match=None,
        read=None,
        disposition="provisional_suspect",
    ):
        if not isinstance(case, dict):
            return None
        profile = case.get("provisional_crime_profile") if isinstance(case.get("provisional_crime_profile"), dict) else None
        if not isinstance(profile, dict):
            return None
        attribution = record_provisional_justice_attribution(
            self.sim,
            case.get("incident_id"),
            actor_eid=actor_eid,
            officer_eid=officer_eid,
            match=match,
            read=read,
            disposition=disposition,
        )
        if not isinstance(attribution, dict):
            return None
        if bool(attribution.get("justice_record_created", False)):
            return attribution.get("justice_change") if isinstance(attribution.get("justice_change"), dict) else None
        change = self._record_incident(
            actor_eid,
            incident_type=profile.get("incident_type"),
            severity=int(profile.get("severity", case.get("severity", 0)) or 0),
            source_event="provisional_identity_attribution",
            property_id=case.get("property_id"),
            x=case.get("x"),
            y=case.get("y"),
            witnessed=True,
            note=f"provisional {profile.get('source_event', 'incident')} attribution; factual incident #{case.get('incident_id')}",
            provisional=True,
            source_case_id=case.get("case_id"),
            source_incident_id=case.get("incident_id"),
            attribution_basis="nearby_reported_description_match",
        )
        attribution["justice_record_created"] = change is not None
        attribution["justice_change"] = dict(change) if isinstance(change, dict) else None
        attribution["punishment_status"] = "pending" if change is not None else "not_created"
        self.sim.emit(Event(
            "justice_provisional_attribution",
            eid=actor_eid,
            officer_eid=officer_eid,
            incident_id=case.get("incident_id"),
            case_id=case.get("case_id"),
            disposition=disposition,
            match_score=float((match or {}).get("score", 0.0) or 0.0),
            scene_distance=(read or {}).get("scene_distance"),
            age_ticks=(read or {}).get("age_ticks"),
            justice_record_created=change is not None,
            canonical_identity_resolved=False,
            wrongful_risk=True,
        ))
        return change

    def _active_case_attribution_for(self, case, actor_eid):
        if not isinstance(case, dict):
            return None
        for row in reversed(tuple(case.get("provisional_attributions", ()) or ())):
            if not isinstance(row, dict):
                continue
            try:
                same_actor = int(row.get("actor_eid")) == int(actor_eid)
            except (TypeError, ValueError):
                same_actor = False
            if same_actor and str(row.get("status", "active") or "active").strip().lower() == "active":
                return row
        return None

    def _snapshot_without_provisional_attribution(self, snapshot, attribution):
        adjusted = dict(snapshot or {})
        change = attribution.get("justice_change") if isinstance((attribution or {}).get("justice_change"), dict) else {}
        incident = change.get("incident") if isinstance(change.get("incident"), dict) else {}
        contribution = int(
            max(
                0,
                incident.get("active_contribution", incident.get("weight", 0)) or 0,
            )
        )
        score = max(0, int(adjusted.get("active_score", 0) or 0) - contribution)
        adjusted["active_score"] = int(score)
        adjusted["wanted_tier"] = _justice_wanted_tier_for(score)
        if str(incident.get("type", "") or "").strip().lower() == "homicide":
            adjusted["homicide_count"] = max(0, int(adjusted.get("homicide_count", 0) or 0) - 1)
        return adjusted

    def _provisional_player_fine_share(self, snapshot, attribution):
        snapshot = dict(snapshot or {})
        adjusted = self._snapshot_without_provisional_attribution(snapshot, attribution or {})
        current_base = self._player_base_fine_amount(snapshot) if int(snapshot.get("active_score", 0) or 0) >= 6 else 0
        adjusted_base = self._player_base_fine_amount(adjusted) if int(adjusted.get("active_score", 0) or 0) >= 6 else 0
        current_homicide = self._player_homicide_surcharge(snapshot)
        adjusted_homicide = self._player_homicide_surcharge(adjusted)
        return max(0, int(current_base + current_homicide - adjusted_base - adjusted_homicide))

    def _provisional_npc_fine_share(self, snapshot, attribution):
        snapshot = dict(snapshot or {})
        adjusted = self._snapshot_without_provisional_attribution(snapshot, attribution or {})
        current = dict(snapshot)
        current["restitution_due"] = 0
        adjusted["restitution_due"] = 0
        current_due = self._npc_fine_amount(current) if int(current.get("active_score", 0) or 0) >= 6 else 0
        adjusted_due = self._npc_fine_amount(adjusted) if int(adjusted.get("active_score", 0) or 0) >= 6 else 0
        return max(0, int(current_due - adjusted_due))

    def _record_player_provisional_booking_outcome(
        self,
        case,
        attribution,
        *,
        snapshot,
        hold_ticks,
        fine_due,
        fine_result,
        release_change,
    ):
        if not isinstance(case, dict) or not isinstance(attribution, dict):
            return
        wrongful_due = min(
            max(0, int(fine_due or 0)),
            self._provisional_player_fine_share(snapshot, attribution),
        )
        fine_result = fine_result if isinstance(fine_result, dict) else {}
        attribution["financial_outcome"] = {
            "fine_due": int(max(0, fine_due or 0)),
            "wrongful_fine_due": int(wrongful_due),
            "fine_paid": int(max(0, fine_result.get("fine_paid", 0) or 0)),
            "debt_added": int(max(0, fine_result.get("debt_added", 0) or 0)),
            "hold_ticks_served": int(max(0, hold_ticks or 0)),
            "booking_tick": int(getattr(self.sim, "tick", 0) or 0),
        }
        adjusted = self._snapshot_without_provisional_attribution(snapshot, attribution)
        total_release = int((release_change or {}).get("after_score", 0) or 0)
        unrelated_release = int(self._booking_release_score(adjusted))
        residual = max(0, total_release - unrelated_release)
        _set_provisional_justice_active_contribution(
            self.sim,
            self.player_eid,
            case.get("case_id"),
            residual,
        )
        change = attribution.get("justice_change") if isinstance(attribution.get("justice_change"), dict) else {}
        incident = change.get("incident") if isinstance(change.get("incident"), dict) else None
        if isinstance(incident, dict):
            incident["active_contribution"] = int(residual)

    def _booking_provisional_adjudication(self, case, attribution, inspection):
        """Decide a fallible case at booking without resolving hidden identity."""

        if not isinstance(case, dict) or not isinstance(attribution, dict):
            return {
                "applicable": False,
                "status": "ordinary_booking",
                "convicted": True,
                "exonerated": False,
                "strength": 1.0,
                "reasons": (),
            }
        match = attribution.get("match") if isinstance(attribution.get("match"), dict) else {}
        read = provisional_attribution_read(
            self.sim,
            case,
            self.player_eid,
            match=match,
        )
        counts = inspection.get("counts") if isinstance((inspection or {}).get("counts"), dict) else {}
        profile = case.get("provisional_crime_profile") if isinstance(case.get("provisional_crime_profile"), dict) else {}
        incident_type = str(profile.get("incident_type", "") or "").strip().lower()
        incident_evidence = max(0, int(counts.get("incident_evidence", 0) or 0))
        stolen_evidence = max(0, int(counts.get("reported_stolen", 0) or 0)) if incident_type == "theft" else 0
        physical_evidence_count = incident_evidence + stolen_evidence
        conflicts = tuple(read.get("conflicting_cues", ()) or ())
        physical_support = bool(
            physical_evidence_count > 0
            and float(read.get("match_score", 0.0) or 0.0) >= 0.70
            and len(conflicts) < 2
        )
        strength = max(
            float(read.get("adjudication_strength", 0.0) or 0.0),
            0.86 if physical_support else 0.0,
        )
        convicted = bool(read.get("convictable", False) or physical_support)
        reasons = list(tuple(read.get("adjudication_reasons", ()) or ()))
        if physical_support:
            reasons = ["incident_specific_physical_evidence"]
        status = "convicted_on_booking_evidence" if convicted else "exonerated_at_booking_review"
        attribution["booking_read"] = deepcopy(read)
        attribution["booking_physical_evidence_count"] = int(physical_evidence_count)
        attribution["adjudication_strength"] = round(float(strength), 3)
        attribution["adjudication_status"] = status
        attribution["adjudication_tick"] = int(getattr(self.sim, "tick", 0) or 0)
        legal_change = None
        if convicted:
            attribution["punishment_status"] = "convicted_at_booking"
            convictions = list(case.get("evidentiary_convictions", ()) or ())
            if not any(
                isinstance(row, dict)
                and int(row.get("actor_eid", -1) or -1) == int(self.player_eid)
                and str(row.get("status", "active") or "active").strip().lower() == "active"
                for row in convictions
            ):
                convictions.append({
                    "tick": int(getattr(self.sim, "tick", 0) or 0),
                    "actor_eid": int(self.player_eid),
                    "officer_eid": int(attribution.get("officer_eid", -1) or -1),
                    "evidence_strength": round(float(strength), 3),
                    "wrongful_risk": True,
                    "status": "active",
                })
                case["evidentiary_convictions"] = convictions[-12:]
        else:
            legal_change = _exonerate_provisional_justice_case(
                self.sim,
                self.player_eid,
                case.get("case_id"),
            )
            attribution["status"] = "exonerated_at_booking"
            attribution["punishment_status"] = "exonerated_at_booking"
            case["provisional_status"] = "exonerated_at_booking"
            self.pending_detentions.pop(int(self.player_eid), None)
            if isinstance(legal_change, dict):
                self._emit_change_events(
                    legal_change,
                    source_event="justice_booking_adjudication",
                    reason="booking_exoneration",
                )
        case["updated_tick"] = int(getattr(self.sim, "tick", 0) or 0)
        result = {
            "applicable": True,
            "status": status,
            "convicted": convicted,
            "exonerated": not convicted,
            "strength": round(float(strength), 3),
            "reasons": tuple(reasons),
            "physical_evidence_count": int(physical_evidence_count),
            "legal_change": legal_change,
        }
        self.sim.emit(Event(
            "justice_booking_adjudicated",
            eid=self.player_eid,
            officer_eid=attribution.get("officer_eid"),
            case_id=case.get("case_id"),
            incident_id=case.get("incident_id"),
            canonical_identity_resolved=False,
            wrongful_risk=bool(convicted),
            **{key: value for key, value in result.items() if key != "legal_change"},
        ))
        return result

    def _refund_player_exoneration(self, attribution):
        financial = attribution.get("financial_outcome") if isinstance((attribution or {}).get("financial_outcome"), dict) else {}
        wrongful_due = max(0, int(financial.get("wrongful_fine_due", 0) or 0))
        direct_paid = max(0, int(financial.get("fine_paid", 0) or 0))
        debt_assessed = min(wrongful_due, max(0, int(financial.get("debt_added", 0) or 0)))
        debt_cancelled = 0
        profile = self._player_finance_profile(create=False)
        if profile is not None and debt_assessed > 0:
            pay_debt = getattr(profile, "pay_debt", None)
            if callable(pay_debt):
                debt_cancelled = int(pay_debt(self.JUSTICE_DEBT_KEY, debt_assessed) or 0)
        paid_debt_estimate = max(0, debt_assessed - debt_cancelled)
        refund = min(
            max(0, wrongful_due - debt_cancelled),
            direct_paid + paid_debt_estimate,
        )
        destination = ""
        if refund > 0:
            if profile is not None:
                profile.bank_balance = int(max(0, getattr(profile, "bank_balance", 0) or 0)) + int(refund)
                destination = "bank"
            else:
                assets = self._player_assets(create=True)
                assets.credits = int(max(0, getattr(assets, "credits", 0) or 0)) + int(refund)
                destination = "wallet"
        financial["debt_cancelled"] = int(debt_cancelled)
        financial["fine_refunded"] = int(refund)
        financial["refund_destination"] = destination
        attribution["financial_outcome"] = financial
        return {
            "fine_refunded": int(refund),
            "debt_cancelled": int(debt_cancelled),
            "refund_destination": destination,
            "hold_ticks_served": int(max(0, financial.get("hold_ticks_served", 0) or 0)),
        }

    def _npc_exoneration_refund_records(self):
        traits = getattr(self.sim, "world_traits", None)
        if not isinstance(traits, dict):
            self.sim.world_traits = {}
            traits = self.sim.world_traits
        records = traits.get("justice_exoneration_refunds")
        if not isinstance(records, dict):
            records = {}
            traits["justice_exoneration_refunds"] = records
        return records

    def _credit_npc_inventory_refund(self, actor_eid, amount):
        amount = max(0, int(amount or 0))
        if amount <= 0:
            return 0
        inventory = self.sim.ecs.get(Inventory).get(actor_eid)
        if inventory is None:
            return 0
        for entry in tuple(getattr(inventory, "items", ()) or ()):
            if not is_credstick_item(entry.get("item_id")):
                continue
            metadata = dict(entry.get("metadata") or {})
            current = credstick_total_credits(
                quantity=entry.get("quantity", 1),
                metadata=metadata,
            )
            metadata["stored_credits"] = int(current + amount)
            metadata["source"] = "justice_exoneration_refund"
            entry["metadata"] = metadata
            return int(amount)
        item_def = ITEM_CATALOG.get(CREDSTICK_ITEM_ID, {})
        added, _instance_id = inventory.add_item(
            CREDSTICK_ITEM_ID,
            quantity=1,
            stack_max=max(1, int(item_def.get("stack_max", 1) or 1)),
            instance_factory=self.sim.new_item_instance_id,
            owner_eid=actor_eid,
            owner_tag="npc",
            metadata={"stored_credits": int(amount), "source": "justice_exoneration_refund"},
        )
        return int(amount) if added else 0

    def _credit_npc_exoneration_refund(self, actor_eid, amount, *, target_wallet=None, case_id=""):
        amount = max(0, int(amount or 0))
        target_wallet = max(0, int(target_wallet if target_wallet is not None else amount))
        if amount <= 0:
            return {"fine_refunded": 0, "credits_delivered": 0, "refund_pending": False}
        inventory = self.sim.ecs.get(Inventory).get(actor_eid)
        current = self._inventory_cash_total_from_entries(getattr(inventory, "items", ())) if inventory is not None else None
        delivered = 0
        if current is not None:
            delivered = self._credit_npc_inventory_refund(actor_eid, min(amount, max(0, target_wallet - current)))
            current += delivered
        pending = current is None or current < target_wallet
        key = str(int(actor_eid))
        records = self._npc_exoneration_refund_records()
        if pending:
            existing = records.get(key) if isinstance(records.get(key), dict) else {}
            records[key] = {
                "eid": int(actor_eid),
                "case_id": str(case_id or existing.get("case_id", "") or "").strip(),
                "target_wallet_credits": max(target_wallet, int(existing.get("target_wallet_credits", 0) or 0)),
                "fine_refunded": max(amount, int(existing.get("fine_refunded", 0) or 0)),
                "created_tick": int(existing.get("created_tick", getattr(self.sim, "tick", 0)) or 0),
            }
        else:
            records.pop(key, None)
        return {
            "fine_refunded": int(amount),
            "credits_delivered": int(delivered),
            "refund_pending": bool(pending),
            "target_wallet_credits": int(target_wallet),
        }

    def _process_pending_npc_exoneration_refunds(self):
        records = self._npc_exoneration_refund_records()
        if not records:
            return 0
        delivered_count = 0
        for key, record in list(records.items()):
            if not isinstance(record, dict):
                records.pop(key, None)
                continue
            actor_eid = int(record.get("eid", key) or 0)
            inventory = self.sim.ecs.get(Inventory).get(actor_eid)
            if inventory is None:
                continue
            target = max(0, int(record.get("target_wallet_credits", 0) or 0))
            current = self._inventory_cash_total_from_entries(getattr(inventory, "items", ()))
            delivered = self._credit_npc_inventory_refund(actor_eid, max(0, target - current))
            after = self._inventory_cash_total_from_entries(getattr(inventory, "items", ()))
            if after < target:
                continue
            records.pop(key, None)
            delivered_count += 1
            self.sim.emit(Event(
                "justice_exoneration_refund_delivered",
                eid=actor_eid,
                case_id=record.get("case_id"),
                fine_refunded=int(record.get("fine_refunded", 0) or 0),
                credits_delivered=int(delivered),
                wallet_credits_after=int(after),
            ))
        return delivered_count

    def _npc_exoneration_memory_records(self):
        traits = getattr(self.sim, "world_traits", None)
        if not isinstance(traits, dict):
            self.sim.world_traits = {}
            traits = self.sim.world_traits
        records = traits.get("justice_exoneration_memories")
        if not isinstance(records, dict):
            records = {}
            traits["justice_exoneration_memories"] = records
        return records

    def _apply_wrongful_justice_memory(self, actor_eid, record):
        memories = self.sim.ecs.get(NPCMemory)
        memory = memories.get(actor_eid) if memories is not None else None
        if memory is None:
            return False
        memory.remember(
            tick=int(record.get("tick", getattr(self.sim, "tick", 0)) or 0),
            kind="wrongful_justice_attribution",
            strength=0.94,
            case_id=record.get("case_id"),
            incident_id=record.get("incident_id"),
            officer_eid=record.get("officer_eid"),
            reporter_eids=tuple(record.get("reporter_eids", ()) or ()),
            actual_offender_eid=record.get("actual_offender_eid"),
            fine_refunded=int(record.get("fine_refunded", 0) or 0),
            hold_ticks_served=int(record.get("hold_ticks_served", 0) or 0),
        )
        social = self.sim.ecs.get(NPCSocial).get(actor_eid)
        if social is None:
            return True
        officer_eid = record.get("officer_eid")
        reporter_eids = tuple(record.get("reporter_eids", ()) or ())
        actual_eid = record.get("actual_offender_eid")
        penalties = {}
        if officer_eid not in {None, -1, actor_eid}:
            penalties[officer_eid] = max(penalties.get(officer_eid, 0.0), 0.22)
        for reporter_eid in reporter_eids:
            if reporter_eid != actor_eid:
                penalties[reporter_eid] = max(penalties.get(reporter_eid, 0.0), 0.18)
        if actual_eid not in {None, actor_eid}:
            penalties[actual_eid] = max(penalties.get(actual_eid, 0.0), 0.3)
        for target_eid, penalty in penalties.items():
            bond = social.bonds.get(target_eid) if isinstance(getattr(social, "bonds", None), dict) else None
            if not isinstance(bond, dict):
                continue
            bond["trust"] = max(0.0, float(bond.get("trust", 0.0) or 0.0) - float(penalty))
            bond["closeness"] = max(0.0, float(bond.get("closeness", 0.0) or 0.0) - (float(penalty) * 0.35))
        return True

    def _remember_wrongful_justice_outcome(self, actor_eid, case, attribution):
        if actor_eid == self.player_eid:
            return
        reporter_eids = []
        for row in tuple(case.get("reports", ()) or ()):
            if not isinstance(row, dict):
                continue
            try:
                reporter_eid = int(row.get("reporter_eid"))
            except (TypeError, ValueError):
                continue
            if reporter_eid > 0 and reporter_eid not in reporter_eids:
                reporter_eids.append(reporter_eid)
        outcome = attribution.get("correction_outcome") if isinstance(attribution.get("correction_outcome"), dict) else {}
        record = {
            "eid": int(actor_eid),
            "tick": int(getattr(self.sim, "tick", 0) or 0),
            "case_id": case.get("case_id"),
            "incident_id": case.get("incident_id"),
            "officer_eid": attribution.get("officer_eid"),
            "reporter_eids": tuple(reporter_eids),
            "actual_offender_eid": case.get("resolved_subject_eid"),
            "fine_refunded": int(outcome.get("fine_refunded", 0) or 0),
            "hold_ticks_served": int(outcome.get("hold_ticks_served", 0) or 0),
        }
        key = str(int(actor_eid))
        records = self._npc_exoneration_memory_records()
        records[key] = record
        if self._apply_wrongful_justice_memory(actor_eid, record):
            records.pop(key, None)

    def _process_pending_npc_exoneration_memories(self):
        records = self._npc_exoneration_memory_records()
        if not records:
            return 0
        applied = 0
        for key, record in list(records.items()):
            if not isinstance(record, dict):
                records.pop(key, None)
                continue
            try:
                actor_eid = int(record.get("eid", key))
            except (TypeError, ValueError):
                records.pop(key, None)
                continue
            if not self._apply_wrongful_justice_memory(actor_eid, record):
                continue
            records.pop(key, None)
            applied += 1
        return applied

    def _actual_offender_secured_for_case(self, case):
        """Require physical custody before a conviction can be overturned."""

        if not isinstance(case, dict):
            return False
        actual_eid = case.get("resolved_subject_eid")
        try:
            actual_eid = int(actual_eid)
        except (TypeError, ValueError):
            return False
        snapshot = _justice_snapshot(self.sim, actual_eid)
        if bool(snapshot.get("in_custody", False)):
            return True
        custody = self._npc_custody_records().get(str(actual_eid))
        return bool(isinstance(custody, dict) and custody.get("active", False))

    def on_actor_detained_case_correction(self, event):
        """Revisit only cases whose newly proven offender was just secured."""

        try:
            detained_eid = int(event.data.get("eid"))
        except (TypeError, ValueError):
            return
        for case in tuple(justice_identity_state(self.sim).get("cases", {}).values()):
            if not isinstance(case, dict):
                continue
            try:
                actual_eid = int(case.get("resolved_subject_eid"))
            except (TypeError, ValueError):
                continue
            if actual_eid != detained_eid:
                continue
            self._resolve_case_provisional_aftermath(case)

    def _resolve_case_provisional_aftermath(self, case):
        if not isinstance(case, dict) or not bool(case.get("misidentification_confirmed", False)):
            return ()
        if not self._actual_offender_secured_for_case(case):
            case["correction_status"] = "pending_actual_offender_capture"
            return ()
        outcomes = []
        tick = int(getattr(self.sim, "tick", 0) or 0)
        for attribution in tuple(case.get("provisional_attributions", ()) or ()):
            if not isinstance(attribution, dict):
                continue
            if str(attribution.get("status", "") or "").strip().lower() not in {
                "misidentified",
                "misidentified_pending_capture",
            }:
                continue
            if bool(attribution.get("correction_applied", False)):
                continue
            actor_eid = int(attribution.get("actor_eid", -1) or -1)
            if actor_eid <= 0:
                continue
            legal_change = _exonerate_provisional_justice_case(
                self.sim,
                actor_eid,
                case.get("case_id"),
            )
            self.pending_detentions.pop(actor_eid, None)
            finance = self._refund_player_exoneration(attribution) if actor_eid == self.player_eid else {
                "fine_refunded": 0,
                "debt_cancelled": 0,
                "refund_destination": "",
                "hold_ticks_served": int(((attribution.get("financial_outcome") or {}).get("hold_ticks_served", 0)) or 0),
            }
            released = False
            if actor_eid == self.player_eid:
                snapshot = _justice_snapshot(self.sim, actor_eid)
                if bool(snapshot.get("in_custody", False)) and str(snapshot.get("wanted_tier", "clear") or "clear") not in {"wanted", "arrest_on_sight"}:
                    pos = self._position_for(actor_eid)
                    release_change = _release_justice_from_custody(
                        self.sim,
                        actor_eid,
                        new_score=int(snapshot.get("active_score", 0) or 0),
                        x=getattr(pos, "x", 0),
                        y=getattr(pos, "y", 0),
                    )
                    self._emit_change_events(release_change, source_event="justice_misidentification_corrected", reason="exoneration")
                    released = True
            else:
                custody = self._npc_custody_records().get(str(actor_eid))
                financial = attribution.get("financial_outcome") if isinstance(attribution.get("financial_outcome"), dict) else {}
                custody_case = (
                    (custody.get("provisional_cases") or {}).get(str(case.get("case_id", "") or ""), {})
                    if isinstance(custody, dict)
                    else {}
                )
                if isinstance(custody, dict) and isinstance(custody_case, dict):
                    financial["fine_due"] = max(
                        int(max(0, financial.get("fine_due", 0) or 0)),
                        int(max(0, custody.get("fine_due", 0) or 0)),
                    )
                    financial["wrongful_fine_due"] = max(
                        int(max(0, financial.get("wrongful_fine_due", 0) or 0)),
                        int(max(0, custody_case.get("wrongful_fine_due", 0) or 0)),
                    )
                    financial["fine_paid"] = max(
                        int(max(0, financial.get("fine_paid", 0) or 0)),
                        int(max(0, custody.get("fine_paid", 0) or 0)),
                    )
                    financial["debt_added"] = int(max(0, financial.get("debt_added", 0) or 0))
                    financial["hold_ticks_served"] = max(
                        int(max(0, financial.get("hold_ticks_served", 0) or 0)),
                        max(
                            0,
                            int(custody.get("released_tick", tick))
                            - int(custody.get("start_tick", tick)),
                        ),
                    )
                wrongful_due = max(0, int(financial.get("wrongful_fine_due", 0) or 0))
                paid = min(wrongful_due, max(0, int(financial.get("fine_paid", 0) or 0)))
                refund_read = self._credit_npc_exoneration_refund(
                    actor_eid,
                    paid,
                    target_wallet=(custody or {}).get("wallet_credits_before", paid) if isinstance(custody, dict) else paid,
                    case_id=case.get("case_id"),
                )
                finance.update({
                    "fine_refunded": int(refund_read.get("fine_refunded", 0) or 0),
                    "refund_pending": bool(refund_read.get("refund_pending", False)),
                    "credits_delivered": int(refund_read.get("credits_delivered", 0) or 0),
                    "hold_ticks_served": int(max(0, financial.get("hold_ticks_served", 0) or 0)),
                })
                financial["fine_refunded"] = int(refund_read.get("fine_refunded", 0) or 0)
                financial["refund_pending"] = bool(refund_read.get("refund_pending", False))
                attribution["financial_outcome"] = financial
                if isinstance(custody, dict) and bool(custody.get("active", False)):
                    snapshot = _justice_snapshot(self.sim, actor_eid)
                    tier = _justice_wanted_tier_for(int(snapshot.get("active_score", 0) or 0))
                    if tier not in {"wanted", "arrest_on_sight"}:
                        custody["active"] = False
                        custody["released_tick"] = tick
                        custody["release_reason"] = "misidentification_exoneration"
                        custody["fine_due"] = 0
                        custody["fine_paid"] = 0
                        finance["hold_ticks_served"] = max(0, tick - int(custody.get("start_tick", tick)))
                        release_change = _release_justice_from_custody(
                            self.sim,
                            actor_eid,
                            new_score=int(snapshot.get("active_score", 0) or 0),
                            x=custody.get("booking_x"),
                            y=custody.get("booking_y"),
                        )
                        self._release_npc_from_custody(actor_eid, custody)
                        self._emit_change_events(release_change, source_event="justice_misidentification_corrected", reason="exoneration")
                        released = True
                financial["hold_ticks_served"] = int(max(0, finance.get("hold_ticks_served", 0) or 0))
                financial["fine_refunded"] = int(finance.get("fine_refunded", 0) or 0)
                attribution["financial_outcome"] = financial
            outcome = {
                "actor_eid": actor_eid,
                "tick": tick,
                "score_removed": int((legal_change or {}).get("score_removed", 0) or 0),
                "after_score": int((legal_change or {}).get("after_score", 0) or 0),
                "released": bool(released),
                **finance,
            }
            attribution["correction_applied"] = True
            attribution["status"] = "misidentified"
            attribution["adjudication_status"] = "conviction_overturned_after_actual_offender_capture"
            attribution["correction_tick"] = tick
            attribution["correction_outcome"] = dict(outcome)
            attribution["punishment_status"] = "exonerated_after_misidentification"
            self._remember_wrongful_justice_outcome(actor_eid, case, attribution)
            self.sim.emit(Event(
                "justice_misidentification_corrected",
                eid=actor_eid,
                actual_offender_eid=case.get("resolved_subject_eid"),
                case_id=case.get("case_id"),
                incident_id=case.get("incident_id"),
                jurisdiction_name=case.get("jurisdiction_name", "Justice Office"),
                property_id=case.get("property_id"),
                x=case.get("x"),
                y=case.get("y"),
                z=case.get("z"),
                **outcome,
            ))
            outcomes.append(outcome)
        case["correction_outcomes"] = list(case.get("correction_outcomes", ()) or ()) + outcomes
        case["correction_status"] = "complete" if outcomes else case.get("correction_status", "pending")
        if outcomes:
            corrected_eids = {int(row.get("actor_eid", -1) or -1) for row in outcomes}
            for conviction in tuple(case.get("evidentiary_convictions", ()) or ()):
                if not isinstance(conviction, dict):
                    continue
                if int(conviction.get("actor_eid", -1) or -1) not in corrected_eids:
                    continue
                conviction["status"] = "overturned_after_actual_offender_capture"
                conviction["overturned_tick"] = tick
            case["correction_completed_tick"] = tick
            case["updated_tick"] = tick
        return tuple(outcomes)

    def _same_eid_value(self, left, right):
        if left is None or right is None:
            return False
        try:
            return int(left) == int(right)
        except (TypeError, ValueError):
            return str(left) == str(right)

    def _homicide_force_read(self, data, offender_eid):
        data = data if isinstance(data, dict) else {}
        reason = str(data.get("reason", "") or "").strip().lower()
        if "executed" in reason or "downed" in reason:
            bounty_read = bounty_authority_from_stamped_data(data)
            if not isinstance(bounty_read, dict):
                bounty_read = bounty_action_authority(
                    self.sim,
                    offender_eid,
                    data.get("target_eid", data.get("victim_eid")),
                    action="homicide",
                    context="homicide",
                )
            return {
                "force_context": "criminal_attack",
                "force_reason": "the victim was already downed; a recovery credential never authorizes execution" if bool((bounty_read or {}).get("bounty_authority_relevant")) else "the victim was already downed",
                "severity_mitigation": 0,
                "severity_adjustment": int((bounty_read or {}).get("bounty_severity_adjustment", 0) or 0),
                "recordable": True,
                "suppressed": False,
                **dict(bounty_read or {}),
            }

        target_eid = data.get("target_eid", data.get("victim_eid"))
        latest = self._latest_force_context_row(offender_eid)
        latest_target = latest.get("target_eid", latest.get("victim_eid"))
        latest_context = str(latest.get("force_context", "") or "").strip().lower()
        latest_tick = int(latest.get("tick", -10_000) or -10_000)
        current_tick = int(getattr(self.sim, "tick", 0))
        if (
            latest
            and self._same_eid_value(latest_target, target_eid)
            and current_tick - latest_tick <= max(120, self._ticks_per_hour())
            and latest_context in {"lawful_defense", "defense_of_property", "defense_of_other"}
        ):
            payload = dict(latest)
            prior_reason = str(payload.get("force_reason", "") or "").strip()
            payload["force_reason"] = (
                f"{prior_reason}; the death followed the same defensive force"
                if prior_reason
                else "the death followed the same defensive force"
            )
            payload["recordable"] = bool(payload.get("recordable", False))
            payload["suppressed"] = bool(payload.get("suppressed", True))
            payload["severity_mitigation"] = payload.get("severity_mitigation", 1.0)
            return payload

        homicide_data = dict(data)
        homicide_data.setdefault("context", "homicide")
        homicide_data.setdefault("offender_eid", offender_eid)
        return classify_lawful_force(self.sim, homicide_data, offender_eid=offender_eid)

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
        self._rehydrate_local_opportunity_knowledge(
            source_prop=self.sim.properties.get(property_id) if property_id else None,
            reason="justice_booking",
            force_routine_rethink=True,
        )
        return advanced_ticks

    def _rehydrate_local_opportunity_knowledge(self, *, source_prop=None, reason="dialog", force_routine_rethink=False):
        center = None
        if isinstance(source_prop, dict):
            center = (
                int(source_prop.get("x", 0) or 0),
                int(source_prop.get("y", 0) or 0),
                int(source_prop.get("z", 0) or 0),
            )
        return _rehydrate_entity_knowledge(
            self.sim,
            self.player_eid,
            center=center,
            radius=20,
            search_radius=10,
            current_tick=int(getattr(self.sim, "tick", 0)),
            reason=reason,
            force_routine_rethink=force_routine_rethink,
        )

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
        if _observer_is_active_bodyguard(self.sim, eid):
            return False, 0.0, 0

        law_drive = 0.0
        if profile:
            if profile.corruption > 0.82 and not profile.enforce_all:
                return False, 0.0, 0
            law_drive = (_justice_level(profile) * 0.65) + (_crime_sensitivity(profile) * 0.35)

        explicit_enforcer = bool(
            (profile and profile.enforce_all)
            or role == "guard"
            or any(
                token in career
                for token in (
                    "guard", "corrections", "deputy", "bailiff", "sergeant",
                    "detective", "investigator", "inspector", "ranger", "warden",
                    "conservation", "wildlife_enforcement",
                )
            )
        )
        if not explicit_enforcer and law_drive < 0.78:
            return False, law_drive, 0

        priority = 0
        if profile and profile.enforce_all:
            priority += 3
        if role == "guard":
            priority += 2
        if any(token in career for token in ("corrections", "deputy", "bailiff", "sergeant", "detective", "investigator", "inspector", "ranger", "warden", "conservation", "wildlife_enforcement")):
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

    def _deferred_player_contact_records(self):
        records = getattr(self.sim, "justice_deferred_player_contacts", None)
        if not isinstance(records, dict):
            records = {}
            self.sim.justice_deferred_player_contacts = records
        return records

    def _defer_player_contact(self, event_type, data):
        payload = dict(data or {})
        if event_type == "justice_report_candidate_contact":
            contact_eid = payload.get("officer_eid")
            actor_eid = payload.get("candidate_eid")
        else:
            contact_eid = payload.get("investigator_eid")
            actor_eid = payload.get("actor_eid")
        key = ":".join(
            str(value)
            for value in (
                event_type,
                contact_eid,
                actor_eid,
                payload.get("incident_id"),
            )
        )
        self._deferred_player_contact_records()[key] = {
            "event_type": str(event_type),
            "data": payload,
            "queued_tick": int(getattr(self.sim, "tick", 0) or 0),
        }
        return True

    def _clear_deferred_player_contact_pending(self, event_type, data):
        payload = data if isinstance(data, dict) else {}
        if event_type == "justice_report_candidate_contact":
            contact_eid = payload.get("officer_eid")
            pending_key = "contact_pending"
        else:
            contact_eid = payload.get("investigator_eid")
            pending_key = "canvas_contact_pending"
        _ai, context = self._received_report_context(contact_eid, payload.get("incident_id"))
        if context is None:
            return
        updated = dict(context)
        updated[pending_key] = False
        self._resume_received_report_route(contact_eid, updated)

    def _deferred_player_contact_still_adjacent(self, event_type, data):
        payload = data if isinstance(data, dict) else {}
        if event_type == "justice_report_candidate_contact":
            contact_eid = payload.get("officer_eid")
            actor_eid = payload.get("candidate_eid")
        else:
            contact_eid = payload.get("investigator_eid")
            actor_eid = payload.get("actor_eid")
        if contact_eid is None or actor_eid is None:
            return False
        try:
            if int(actor_eid) != int(self.player_eid):
                return False
        except (TypeError, ValueError):
            return False
        contact_pos = self._position_for(contact_eid)
        player_pos = self._position_for(self.player_eid)
        if contact_pos is None or player_pos is None or _entity_is_downed(self.sim, contact_eid):
            return False
        return bool(
            int(contact_pos.z) == int(player_pos.z)
            and _manhattan(contact_pos.x, contact_pos.y, player_pos.x, player_pos.y) <= 1
        )

    def _resume_deferred_player_contact(self):
        if _player_modal_active(self.sim):
            return False
        records = self._deferred_player_contact_records()
        ordered = sorted(
            tuple(records.items()),
            key=lambda row: (
                int((row[1] or {}).get("queued_tick", 0) or 0) if isinstance(row[1], dict) else 0,
                str(row[0]),
            ),
        )
        for key, record in ordered:
            records.pop(key, None)
            if not isinstance(record, dict):
                continue
            event_type = str(record.get("event_type", "") or "").strip()
            data = record.get("data") if isinstance(record.get("data"), dict) else {}
            if event_type not in {"justice_report_candidate_contact", "justice_case_canvas_contact"}:
                continue
            if not self._deferred_player_contact_still_adjacent(event_type, data):
                self._clear_deferred_player_contact_pending(event_type, data)
                continue
            self.sim.emit(Event(event_type, **data))
            return True
        return False

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
        return bool(state.get("open")) and str(state.get("kind", "")).strip().lower() in {
            self.SURRENDER_DIALOG_KIND,
            self.QUESTIONING_DIALOG_KIND,
            self.IDENTITY_CHECK_DIALOG_KIND,
            self.CASE_CANVAS_DIALOG_KIND,
        }

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

    def _player_restitution_snapshot(self):
        return _justice_restitution_snapshot(self.sim, self.player_eid)

    def _clear_restitution_claims(self, offender_eid):
        return _clear_justice_restitution_claims(self.sim, offender_eid)

    def _record_structural_restitution_claim(self, offender_eid, prop, *, damage_tick=None):
        if offender_eid is None or not isinstance(prop, dict):
            return None
        if str(prop.get("kind", "")).strip().lower() != "building":
            return None
        existing_claims = self._player_restitution_snapshot() if int(offender_eid) == int(self.player_eid) else _justice_restitution_snapshot(self.sim, offender_eid)
        existing_keys = set()
        target_property_id = str(prop.get("id", "") or "").strip()
        for entry in tuple(existing_claims.get("entries", ()) or ()):
            if not isinstance(entry, dict):
                continue
            entry_property_id = str(entry.get("property_id", "") or "").strip()
            if target_property_id and entry_property_id != target_property_id:
                continue
            existing_keys.update(str(key).strip() for key in tuple(entry.get("damage_keys", ()) or ()) if str(key).strip())
        records = tuple(
            _property_damage_records(
                self.sim,
                prop,
                offender_eid=offender_eid,
                damage_tick=damage_tick,
            )
        )
        if not records:
            return None
        damage_keys = []
        damage_count = 0
        window_count = 0
        door_count = 0
        wall_count = 0
        total_amount = 0
        for record in records:
            if not isinstance(record, dict):
                continue
            key = f"{int(record.get('x', 0))}:{int(record.get('y', 0))}:{int(record.get('z', 0))}"
            if key in existing_keys:
                continue
            damage_keys.append(key)
            damage_count += 1
            repair_kind = str(record.get("repair_kind", "") or "").strip().lower()
            if repair_kind == "window":
                window_count += 1
            elif repair_kind == "door":
                door_count += 1
            else:
                wall_count += 1
            total_amount += int(_damage_record_repair_cost(prop, record))
        if damage_count <= 0 or total_amount <= 0:
            return None
        return _record_justice_restitution_claim(
            self.sim,
            offender_eid,
            property_id=prop.get("id"),
            property_name=prop.get("name"),
            amount=int(total_amount),
            damage_keys=tuple(damage_keys),
            damage_count=int(damage_count),
            window_count=int(window_count),
            door_count=int(door_count),
            wall_count=int(wall_count),
        )

    def _present_justice_result(self, title, lines, *, property_id=None, subtitle=""):
        state = self._dialog_ui_state()
        cleaned = [str(line).strip() for line in list(lines or ()) if str(line).strip()]
        if not cleaned:
            cleaned = ["Nothing is on file right now."]
        self.sim.set_time_paused(True, reason="dialog")
        self._rehydrate_local_opportunity_knowledge(
            source_prop=self.sim.properties.get(property_id) if property_id else None,
            reason="justice_dialog",
        )
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
            "hint": "? help",
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
        stolen = bool(metadata.get("justice_reported_stolen") or (metadata.get("justice_stolen") and not metadata.get("latent_claim_violation")))
        incident_evidence = bool(metadata.get("justice_incident_evidence"))
        latent_claim = bool(metadata.get("latent_claim_violation"))
        objective_protected = bool(metadata.get("final_operation_target"))
        if not objective_protected:
            try:
                objective_protected = int(metadata.get("quest_opportunity_id", 0) or 0) > 0
            except (TypeError, ValueError):
                objective_protected = False

        hold_for_release = bool(objective_protected or ((weapon or restricted) and not (illegal or stolen or incident_evidence)))
        forfeit = bool((illegal or stolen or incident_evidence) and not objective_protected)
        seized = bool(weapon or contraband or stolen or incident_evidence or objective_protected)
        if forfeit:
            disposition = "forfeit"
            disposition_label = "forfeited/confiscated"
        elif hold_for_release:
            disposition = "hold_for_release"
            disposition_label = "held for release"
        else:
            disposition = "ignore_for_now"
            disposition_label = "left with you"

        reason_labels = []
        if objective_protected:
            reason_labels.append("required objective item")
        if incident_evidence and not objective_protected:
            reason_labels.append("reported incident evidence")
        if stolen and not objective_protected:
            reason_labels.append("officially matched stolen property")
        if illegal and not objective_protected:
            reason_labels.append("illegal contraband")
        if restricted and not (illegal or stolen or incident_evidence):
            reason_labels.append("restricted but releasable gear")
        if weapon and not (illegal or stolen or incident_evidence):
            reason_labels.append("legal weapon held for release")
        if not reason_labels:
            if latent_claim:
                reason_labels.append("suspicious property without an official match")
            else:
                reason_labels.append("lawful personal property")
        reason_labels = tuple(dict.fromkeys(label for label in reason_labels if str(label).strip()))
        return {
            "item_id": item_id,
            "weapon": weapon,
            "illegal": illegal,
            "restricted": restricted,
            "contraband": contraband,
            "stolen": stolen,
            "incident_evidence": incident_evidence,
            "latent_claim_violation": latent_claim,
            "objective_protected": objective_protected,
            "hold_for_release": hold_for_release,
            "forfeit": forfeit,
            "seized": seized,
            "disposition": disposition,
            "disposition_label": disposition_label,
            "reason_labels": reason_labels,
            "reason_text": ", ".join(reason_labels),
        }

    def _label_list_text(self, labels, *, limit=3):
        cleaned = [str(label).strip() for label in list(labels or ()) if str(label).strip()]
        if not cleaned:
            return ""
        return ", ".join(tuple(dict.fromkeys(cleaned))[:max(1, int(limit or 1))])

    def _reason_list_text(self, labels, *, limit=3):
        cleaned = [str(label).strip() for label in list(labels or ()) if str(label).strip()]
        if not cleaned:
            return ""
        return ", ".join(tuple(dict.fromkeys(cleaned))[:max(1, int(limit or 1))])

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
        lines = list(self._justice_case_review_lines(current_prop=current_prop) or ())
        lines.extend(list(_justice_summary_rows(self.sim, self.player_eid) or ()))
        debt_balance = int(self._player_justice_debt_balance())
        held = self._player_held_property_snapshot()
        held_site_name = str(held.get("property_name", "") or "").strip()
        held_site_id = str(held.get("property_id", "") or "").strip()
        current_property_id = str(current_prop.get("id", "") or "").strip() if current_prop else ""
        if held_site_id and held_site_name and current_property_id and held_site_id != current_property_id:
            lines.append(f"Released property is logged at {held_site_name}.")
        if debt_balance > 0:
            lines.append("Any justice desk or banking service can take a justice-debt payment.")
        return [str(line).strip() for line in lines if str(line).strip()]

    def _justice_case_review_lines(self, *, current_prop=None):
        snapshot = _justice_snapshot(self.sim, self.player_eid)
        held = self._player_held_property_snapshot()
        restitution = self._player_restitution_snapshot()
        tier = str(snapshot.get("wanted_tier", "clear") or "clear").strip().lower() or "clear"
        score = int(snapshot.get("active_score", 0) or 0)
        incident_count = int(snapshot.get("incident_count", 0) or 0)
        debt_balance = int(self._player_justice_debt_balance())
        restitution_due = int(restitution.get("total_due", restitution.get("amount_due", 0)) or 0)
        held_count = int(held.get("item_count", 0) or 0)
        lines = [f"Case review: {tier.replace('_', ' ')} ({score}) | incident(s) {incident_count}."]
        if debt_balance > 0:
            lines.append(f"Justice debt: {debt_balance}c.")
        if restitution_due > 0:
            lines.append(f"Restitution: {restitution_due}c.")
        inspected = []
        reported = int(snapshot.get("last_inspected_reported_stolen_count", 0) or 0)
        latent = int(snapshot.get("last_inspected_latent_claim_count", 0) or 0)
        if reported > 0:
            inspected.append(f"{reported} reported stolen")
        if latent > 0:
            inspected.append(f"{latent} suspicious")
        if inspected:
            lines.append(f"Strongest evidence read: {', '.join(inspected)}.")
        if held_count > 0:
            held_site = str(held.get("property_name", "") or "").strip() or "the property locker"
            lines.append(f"Held property: {held_count} item(s) at {held_site}.")
            current_id = str((current_prop or {}).get("id", "") or "").strip() if isinstance(current_prop, dict) else ""
            held_id = str(held.get("property_id", "") or "").strip()
            if held_id and current_id and held_id != current_id:
                lines.append(f"Release blocker: correct locker is {held_site}.")
            if debt_balance > 0:
                lines.append(f"Release blocker: {debt_balance}c justice debt.")
        return lines

    def _pay_player_justice_debt_at_desk(self, prop, *, amount=None):
        profile = self._player_finance_profile(create=False)
        assets = self._player_assets(create=False)
        debt_balance = int(self._player_justice_debt_balance())
        if profile is None or debt_balance <= 0:
            return {"paid": 0, "debt_balance": debt_balance, "reason": "no_debt_balance"}
        requested = debt_balance if amount is None else int(max(0, amount or 0))
        wallet_available = int(max(0, getattr(assets, "credits", 0) or 0)) if assets is not None else 0
        bank_available = int(max(0, getattr(profile, "bank_balance", 0) or 0))
        liquid = int(wallet_available + bank_available)
        if requested <= 0:
            return {"paid": 0, "debt_balance": debt_balance, "reason": "invalid_amount"}
        if liquid <= 0:
            return {"paid": 0, "debt_balance": debt_balance, "reason": "insufficient_liquid_funds", "available_liquid": 0}
        payment = min(int(requested), int(debt_balance), int(liquid))
        wallet_paid = min(wallet_available, payment)
        if assets is not None:
            assets.credits = int(max(0, wallet_available - wallet_paid))
        remaining = max(0, payment - wallet_paid)
        bank_paid = min(bank_available, remaining)
        profile.bank_balance = int(max(0, bank_available - bank_paid))
        pay_debt = getattr(profile, "pay_debt", None)
        paid = int(pay_debt(self.JUSTICE_DEBT_KEY, int(wallet_paid + bank_paid)) if callable(pay_debt) else wallet_paid + bank_paid)
        debt_after = int(self._player_justice_debt_balance())
        self.sim.emit(Event(
            "bank_transaction",
            eid=self.player_eid,
            property_id=(prop or {}).get("id") if isinstance(prop, dict) else None,
            provider_name=str((prop or {}).get("name", "Justice Desk") if isinstance(prop, dict) else "Justice Desk").strip() or "Justice Desk",
            kind="debt_payment",
            amount=int(paid),
            requested_amount=int(requested),
            wallet_debt_paid=int(wallet_paid),
            bank_debt_paid=int(bank_paid),
            wallet_credits=int(getattr(assets, "credits", 0) or 0) if assets is not None else 0,
            bank_balance=int(getattr(profile, "bank_balance", 0) or 0),
            debt_key=self.JUSTICE_DEBT_KEY,
            debt_balance=int(debt_after),
            account_kind="personal",
        ))
        return {
            "paid": int(paid),
            "wallet_paid": int(wallet_paid),
            "bank_paid": int(bank_paid),
            "debt_balance": int(debt_after),
            "reason": "paid" if paid > 0 else "blocked",
        }

    def _justice_desk_debt_lines(self, payment):
        payment = payment if isinstance(payment, dict) else {}
        paid = int(payment.get("paid", 0) or 0)
        debt_balance = int(payment.get("debt_balance", 0) or 0)
        reason = str(payment.get("reason", "") or "").strip().lower()
        if paid > 0:
            return [f"Paid {paid}c toward justice debt. Remaining debt: {debt_balance}c."]
        if reason == "insufficient_liquid_funds":
            return [f"Justice debt remains {debt_balance}c; no liquid funds are available here."]
        if reason == "no_debt_balance":
            return []
        return [f"Justice debt remains {debt_balance}c."]

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
        restitution_due = max(0, int(snapshot.get("restitution_due", 0) or 0))
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
        return int(max(base, min(180, round(base + (score * per_score)))) + restitution_due)

    def _player_fine_amount(self, snapshot):
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        tier = str(snapshot.get("wanted_tier", "clear")).strip().lower() or "clear"
        score = max(0, int(snapshot.get("active_score", 0) or 0))
        restitution_due = max(0, int(snapshot.get("restitution_due", 0) or 0))
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
        return int(
            max(base, min(240, round(base + (score * per_score))))
            + restitution_due
            + self._player_homicide_surcharge(snapshot)
        )

    def _player_base_fine_amount(self, snapshot):
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

    def _player_homicide_surcharge(self, snapshot):
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        count = max(0, int(snapshot.get("homicide_count", 0) or 0))
        if count <= 0:
            return 0
        return int(min(600, count * self.PLAYER_HOMICIDE_BOOKING_SURCHARGE))

    def _player_penalty_breakdown(self, snapshot, *, fine_due=0, fine_result=None, evidence_surcharge=0, multiplier=1.0, disposition=""):
        snapshot = snapshot if isinstance(snapshot, dict) else {}
        fine_result = fine_result if isinstance(fine_result, dict) else {}
        base_fine = int(self._player_base_fine_amount(snapshot))
        restitution_due = max(0, int(snapshot.get("restitution_due", 0) or 0))
        homicide_count = max(0, int(snapshot.get("homicide_count", 0) or 0))
        homicide_surcharge = int(self._player_homicide_surcharge(snapshot))
        fine_due = int(max(0, fine_due or 0))
        return {
            "disposition": str(disposition or "").strip().lower(),
            "base_fine": int(base_fine),
            "fine_multiplier": float(round(float(multiplier or 0.0), 3)),
            "restitution_due": int(restitution_due),
            "homicide_count": int(homicide_count),
            "homicide_surcharge": int(homicide_surcharge),
            "evidence_surcharge": int(max(0, evidence_surcharge or 0)),
            "fine_due": int(fine_due),
            "fine_paid": int(fine_result.get("fine_paid", 0) or 0),
            "cash_paid": int(fine_result.get("cash_fine_paid", 0) or 0),
            "wallet_paid": int(fine_result.get("wallet_fine_paid", 0) or 0),
            "bank_paid": int(fine_result.get("bank_fine_paid", 0) or 0),
            "debt_added": int(fine_result.get("debt_added", 0) or 0),
            "fine_outstanding": int(fine_result.get("fine_outstanding", 0) or 0),
            "debt_balance_before": int(fine_result.get("debt_balance_before", self._player_justice_debt_balance()) or 0),
            "debt_balance_after": int(fine_result.get("debt_balance_after", self._player_justice_debt_balance()) or 0),
        }

    def _payment_result_text(self, fine_result):
        fine_result = fine_result if isinstance(fine_result, dict) else {}
        paid = int(fine_result.get("fine_paid", 0) or 0)
        debt_added = int(fine_result.get("debt_added", 0) or 0)
        payment_bits = []
        if int(fine_result.get("cash_fine_paid", 0) or 0) > 0:
            payment_bits.append(f"{int(fine_result.get('cash_fine_paid', 0) or 0)}c carried")
        if int(fine_result.get("wallet_fine_paid", 0) or 0) > 0:
            payment_bits.append(f"{int(fine_result.get('wallet_fine_paid', 0) or 0)}c wallet")
        if int(fine_result.get("bank_fine_paid", 0) or 0) > 0:
            payment_bits.append(f"{int(fine_result.get('bank_fine_paid', 0) or 0)}c bank")
        pieces = []
        if paid > 0:
            pieces.append(f"paid {paid}c" + (f" ({', '.join(payment_bits)})" if payment_bits else ""))
        if debt_added > 0:
            pieces.append(f"{debt_added}c filed as justice debt")
        return "; ".join(pieces)

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
        held_units = int(manifest.get("held_units", 0) or 0)
        forfeited_units = int(manifest.get("forfeited_units", 0) or 0)
        held_labels = self._label_list_text(manifest.get("held_labels", ()))
        forfeited_labels = self._label_list_text(manifest.get("forfeited_labels", ()))
        held_reasons = self._reason_list_text(manifest.get("held_reason_labels", ()))
        forfeited_reasons = self._reason_list_text(manifest.get("forfeited_reason_labels", ()))
        if held_units <= 0 and forfeited_units <= 0:
            return "Legal belongings stay with you unless a search finds contraband, reported stolen property, or evidence."

        parts = []
        if held_units > 0:
            text = f" held for release: {held_units} item(s)"
            if held_labels:
                text += f" ({held_labels})"
            if held_reasons:
                text += f" because {held_reasons}"
            parts.append(text.strip())
        if forfeited_units > 0:
            text = f" forfeited/confiscated: {forfeited_units} item(s)"
            if forfeited_labels:
                text += f" ({forfeited_labels})"
            if forfeited_reasons:
                text += f" because {forfeited_reasons}"
            parts.append(text.strip())
        summary = "Booking seizure preview: " + "; ".join(parts) + "."
        if held_units > 0:
            summary += " Held property can be reclaimed at the booking desk once any justice debt is clear."
        return summary

    def _inspection_match_labels(self, inspection):
        inspection = inspection if isinstance(inspection, dict) else {}
        return tuple(
            str(value).strip()
            for value in tuple(inspection.get("incident_match_labels", ()) or ())
            if str(value).strip()
        )[:4]

    def _inspection_match_reasons(self, inspection):
        inspection = inspection if isinstance(inspection, dict) else {}
        return tuple(
            str(value).strip().lower()
            for value in tuple(inspection.get("incident_match_reasons", ()) or ())
            if str(value).strip()
        )[:4]

    def _match_reason_text(self, match_reason):
        reason_key = str(match_reason or "").strip().lower()
        return {
            "victim_inventory": "victim personal effects",
            "precombat_stolen_from_victim": "property taken during the assault",
            "scene_claimed": "claimed scene property",
            "scene_residue": "scene residue",
        }.get(reason_key, "")

    def _strongest_inspection_match_text(self, inspection):
        labels = self._inspection_match_labels(inspection)
        reasons = self._inspection_match_reasons(inspection)
        if labels:
            return labels[0]
        if reasons:
            return self._match_reason_text(reasons[0]) or reasons[0].replace("_", " ")
        return ""

    def _inspection_evidence_surcharge(self, inspection):
        inspection = inspection if isinstance(inspection, dict) else {}
        counts = inspection.get("counts") if isinstance(inspection.get("counts"), dict) else {}
        evidence_count = max(0, int(counts.get("incident_evidence", 0) or 0))
        if evidence_count <= 0:
            return 0
        return int(evidence_count) * int(self.EVIDENCE_SURCHARGE_PER_ITEM)

    def _stolen_intent_read_text(self, inspection):
        labels = tuple((inspection or {}).get("stolen_intent_labels", ()) or ())
        mapping = {
            "direct_theft": "direct theft",
            "known_hot_purchase": "knowingly risky hot purchase",
            "fenced_possession": "fenced possession",
            "reported_match": "reported-property match",
            "unclear_possession": "unclear possession",
        }
        reads = [
            mapping.get(str(label).strip().lower(), str(label).strip().lower().replace("_", " "))
            for label in labels
            if str(label).strip()
        ]
        return ", ".join(tuple(dict.fromkeys(reads))[:3])

    def _inspection_summary_text(self, inspection):
        inspection = inspection if isinstance(inspection, dict) else {}
        counts = inspection.get("counts") if isinstance(inspection.get("counts"), dict) else {}
        reported_stolen = int(counts.get("reported_stolen", 0) or 0)
        incident_evidence = int(counts.get("incident_evidence", 0) or 0)
        contraband = int(counts.get("contraband", 0) or 0)
        latent = int(counts.get("latent_claim_violation", 0) or 0)
        strongest_match = self._strongest_inspection_match_text(inspection)
        if incident_evidence > 0:
            if strongest_match:
                return (
                    f"Search match: {incident_evidence} item(s) tie you to a reported violent incident. "
                    f"Strongest read: {strongest_match}."
                )
            return f"Search match: {incident_evidence} item(s) tie you to a reported violent incident."
        if reported_stolen > 0:
            if strongest_match:
                text = (
                    f"Search match: {reported_stolen} item(s) match reported stolen property. "
                    f"Strongest read: {strongest_match}."
                )
                intent_read = self._stolen_intent_read_text(inspection)
                if intent_read:
                    text += f" Intent read: {intent_read}."
                return text
            intent_read = self._stolen_intent_read_text(inspection)
            if intent_read:
                return f"Search match: {reported_stolen} item(s) match reported stolen property. Intent read: {intent_read}."
            return f"Search match: {reported_stolen} item(s) match reported stolen property."
        if contraband > 0:
            return f"Search result: {contraband} contraband item(s) on you."
        if latent > 0:
            return f"Search result: {latent} item(s) look wrongfully taken but are not yet matched to a reported crime."
        return "Search result: nothing actionable beyond your current stop."

    def _inspect_actor_inventory(self, offender_eid, *, update_inventory=True, inspector_eid=None):
        if inspector_eid is None:
            inspector_eid = self._find_detaining_enforcer(offender_eid)
        inspection = evaluate_inventory_for_justice(
            self.sim,
            offender_eid,
            current_tick=int(getattr(self.sim, "tick", 0)),
            update_inventory=bool(update_inventory),
            inspector_eid=inspector_eid,
        )
        counts = inspection.get("counts", {}) if isinstance(inspection, dict) else {}
        self.sim.emit(Event(
            "justice_inventory_inspected",
            eid=offender_eid,
            inspector_eid=inspector_eid,
            lawful_count=int(counts.get("lawful", 0) or 0),
            contraband_count=int(counts.get("contraband", 0) or 0),
            latent_claim_count=int(counts.get("latent_claim_violation", 0) or 0),
            reported_stolen_count=int(counts.get("reported_stolen", 0) or 0),
            incident_evidence_count=int(counts.get("incident_evidence", 0) or 0),
            severity_bucket=str(inspection.get("severity_bucket", "clear") or "clear").strip().lower(),
            match_summaries=tuple(inspection.get("match_summaries", ()) or ()),
            incident_match_labels=self._inspection_match_labels(inspection),
            incident_match_reasons=self._inspection_match_reasons(inspection),
            stolen_intent_labels=tuple(inspection.get("stolen_intent_labels", ()) or ()),
            stolen_intent_counts=dict(inspection.get("stolen_intent_counts", {}) or {}),
            evidence_surcharge=int(self._inspection_evidence_surcharge(inspection)),
        ))
        return inspection

    def _justice_enforcement_profile(self, *, snapshot=None, source_prop=None):
        source_prop = source_prop if isinstance(source_prop, dict) else None
        snapshot = snapshot if isinstance(snapshot, dict) else self._player_bookable_snapshot() or _justice_snapshot(self.sim, self.player_eid)
        jurisdiction_key = str((snapshot or {}).get("last_jurisdiction_key", "") or "").strip().lower()
        return justice_enforcement_profile(
            self.sim,
            jurisdiction_key=jurisdiction_key,
            source_property_id=(source_prop or {}).get("id"),
            source_property_name=(source_prop or {}).get("name"),
            offender_eid=self.player_eid,
        )

    def _questioning_hold_property(self, source_prop=None):
        source_prop = source_prop if isinstance(source_prop, dict) else None
        if self._booking_property_allowed(source_prop):
            return source_prop
        player_pos = self._position_for(self.player_eid)
        if player_pos is None:
            return source_prop if self._booking_property_allowed(source_prop) else None
        anchor = self._player_booking_anchor(player_pos)
        origin_x = int((anchor or {}).get("x", player_pos.x) or player_pos.x)
        origin_y = int((anchor or {}).get("y", player_pos.y) or player_pos.y)
        return self._find_booking_property(source_prop=source_prop, origin_x=origin_x, origin_y=origin_y)

    def _remove_inventory_rows(self, eid, rows, *, reason="confiscated", held_prop=None):
        inventory = self.sim.ecs.get(Inventory).get(eid)
        if inventory is None:
            return {
                "entries": (),
                "labels": (),
                "count": 0,
                "held_entries": (),
                "held_labels": (),
                "held_count": 0,
                "forfeited_entries": (),
                "forfeited_labels": (),
                "forfeited_count": 0,
                "held_reason_labels": (),
                "forfeited_reason_labels": (),
                "reason_labels": (),
            }
        removed_entries = []
        labels = []
        held_entries = []
        held_labels = []
        forfeited_entries = []
        forfeited_labels = []
        held_reason_labels = []
        forfeited_reason_labels = []
        for row in tuple(rows or ()):
            if not isinstance(row, dict):
                continue
            quantity = max(1, int(row.get("quantity", 1) or 1))
            removed = inventory.remove_item(instance_id=row.get("instance_id"), quantity=quantity)
            if not removed:
                continue
            item_id = str(removed.get("item_id", "") or "").strip().lower()
            metadata = removed.get("metadata") if isinstance(removed.get("metadata"), dict) else {}
            item_name = item_display_name(item_id, metadata=metadata, item_catalog=ITEM_CATALOG)
            policy = self._justice_item_hold_policy(removed)
            entry_payload = {
                "instance_id": removed.get("instance_id"),
                "item_id": item_id,
                "quantity": max(1, int(removed.get("quantity", 1) or 1)),
                "owner_eid": removed.get("owner_eid"),
                "owner_tag": removed.get("owner_tag"),
                "metadata": dict(metadata),
            }
            removed_entries.append(dict(removed))
            labels.append(item_name)
            if bool(policy.get("hold_for_release")):
                held_entries.append(entry_payload)
                held_labels.append(item_name)
                held_reason_labels.extend(tuple(policy.get("reason_labels", ()) or ()))
            elif bool(policy.get("forfeit")):
                forfeited_entries.append(entry_payload)
                forfeited_labels.append(item_name)
                forfeited_reason_labels.extend(tuple(policy.get("reason_labels", ()) or ()))
            self._emit_removed_gear_events(eid, removed, reason=reason)
        if eid == self.player_eid and held_entries:
            _store_justice_held_property(
                self.sim,
                self.player_eid,
                property_id=(held_prop or {}).get("id") if isinstance(held_prop, dict) else None,
                property_name=(held_prop or {}).get("name") if isinstance(held_prop, dict) else None,
                entries=held_entries,
            )
        held_count = int(sum(max(1, int(entry.get("quantity", 1) or 1)) for entry in held_entries))
        forfeited_count = int(sum(max(1, int(entry.get("quantity", 1) or 1)) for entry in forfeited_entries))
        reason_labels = tuple(dict.fromkeys(
            str(label).strip()
            for label in list(held_reason_labels) + list(forfeited_reason_labels)
            if str(label).strip()
        ))
        return {
            "entries": tuple(removed_entries),
            "labels": tuple(dict.fromkeys(label for label in labels if str(label).strip()))[:4],
            "count": int(sum(max(1, int(entry.get("quantity", 1) or 1)) for entry in removed_entries)),
            "held_entries": tuple(held_entries),
            "held_labels": tuple(dict.fromkeys(label for label in held_labels if str(label).strip()))[:4],
            "held_count": int(held_count),
            "forfeited_entries": tuple(forfeited_entries),
            "forfeited_labels": tuple(dict.fromkeys(label for label in forfeited_labels if str(label).strip()))[:4],
            "forfeited_count": int(forfeited_count),
            "held_reason_labels": tuple(dict.fromkeys(label for label in held_reason_labels if str(label).strip()))[:4],
            "forfeited_reason_labels": tuple(dict.fromkeys(label for label in forfeited_reason_labels if str(label).strip()))[:4],
            "reason_labels": reason_labels[:4],
        }

    def _open_player_questioning_prompt(self, npc_eid=None, *, snapshot=None, source_prop=None):
        if _player_modal_active(self.sim):
            return False
        snapshot = snapshot if isinstance(snapshot, dict) else self._player_bookable_snapshot()
        if snapshot is None:
            return False
        source_prop = self._resolve_prompt_source_property(source_prop)
        anchor = self._player_booking_anchor(self._position_for(self.player_eid))
        jurisdiction_name = str((anchor or {}).get("jurisdiction_name", "Justice Office") or "Justice Office").strip() or "Justice Office"
        incident = (snapshot or {}).get("latest_incident") if isinstance((snapshot or {}).get("latest_incident"), dict) else {}
        cause = str(incident.get("label", "your record") or "your record").strip().lower()
        protective = (
            local_protective_pressure_snapshot(
                self.sim,
                source_prop,
                current_tick=int(getattr(self.sim, "tick", 0)),
            )
            if isinstance(source_prop, dict)
            else {}
        )
        posture_line = ""
        if isinstance(protective, dict) and str(protective.get("state_label", "")).strip():
            posture_line = (
                f"Local posture: {str(protective.get('state_label')).strip()} - "
                f"{str(protective.get('summary', '')).strip() or 'the area is already on alert'}."
            )
        mutual_fight_lines = self._mutual_fight_questioning_lines(self.player_eid)
        latest_force = self._latest_force_context_row(self.player_eid)
        credential_review_line = (
            self._force_context_line(self.player_eid)
            if bool(latest_force.get("bounty_credential_misuse"))
            else ""
        )
        state = self._dialog_ui_state()
        self.sim.set_time_paused(True, reason="dialog")
        self._rehydrate_local_opportunity_knowledge(
            source_prop=source_prop,
            reason="justice_questioning",
        )
        state.update({
            "open": True,
            "kind": self.QUESTIONING_DIALOG_KIND,
            "npc_eid": npc_eid,
            "property_id": source_prop.get("id") if isinstance(source_prop, dict) else None,
            "title": f"Questioning: {_entity_display_name(self.sim, npc_eid, title_case=True) or 'Officer'}" if npc_eid else "Questioning: Justice Desk",
            "subtitle": jurisdiction_name,
            "transcript": [
                f"{jurisdiction_name} wants to question you about {cause}.",
                *([posture_line] if posture_line else []),
                *mutual_fight_lines,
                *([credential_review_line] if credential_review_line else []),
                "Cooperate and they will search what you are carrying before deciding what happens next.",
                "Refusal will escalate to custody.",
            ],
            "topics": [
                {"id": "cooperate", "label": "Cooperate fully"},
                {"id": "explain", "label": "Explain plainly"},
                {"id": "deflect", "label": "Deflect"},
                {"id": "refuse", "label": "Refuse"},
            ],
            "selected_index": 0,
            "scroll": 0,
            "hint": "E choose | Esc refuse | ? help",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
        })
        self.player_surrender_prompt = {
            "kind": self.QUESTIONING_DIALOG_KIND,
            "npc_eid": npc_eid,
            "source_prop_id": source_prop.get("id") if isinstance(source_prop, dict) else None,
            "opened_tick": int(getattr(self.sim, "tick", 0)),
            "jurisdiction_key": str((anchor or {}).get("jurisdiction_key", "") or "").strip().lower(),
            "jurisdiction_name": jurisdiction_name,
        }
        if npc_eid is not None:
            self._mark_officer_surrender_prompt_opened(npc_eid)
        return True

    def _player_unresolved_identity_match(self):
        player_pos = self._position_for(self.player_eid)
        if player_pos is None:
            return None
        jurisdiction = jurisdiction_for_position(self.sim, x=player_pos.x, y=player_pos.y)
        matches = unresolved_case_matches_for_actor(
            self.sim,
            self.player_eid,
            jurisdiction_key=str(jurisdiction.get("key", "") or "").strip().lower(),
        )
        tick = int(getattr(self.sim, "tick", 0))
        for row in matches:
            case = row.get("case") if isinstance(row.get("case"), dict) else None
            if case is None:
                continue
            if justice_case_recently_checked(case, self.player_eid, current_tick=tick):
                continue
            return row
        return None

    def _investigative_contact_match(self, case, report_account, close_account):
        report_description = report_account.get("description") if isinstance((report_account or {}).get("description"), dict) else {}
        close_description = close_account.get("description") if isinstance((close_account or {}).get("description"), dict) else {}
        match = dict(description_match_score(report_description, close_description))
        if float(match.get("score", 0.0) or 0.0) < 0.74:
            return match

        context_text = " ".join(
            str((case or {}).get(key, "") or "").strip().lower()
            for key in ("kind", "action", "context", "merge_subject")
        )
        weapon = close_description.get("weapon") if isinstance(close_description.get("weapon"), dict) else {}
        weapon_id = str(weapon.get("item_id", "") or "").strip().lower()
        weapon_label = str(weapon.get("label", "") or "").strip().lower()
        item_def = ITEM_CATALOG.get(weapon_id, {})
        weapon_tags = _item_tags(item_def)
        firearm = bool(
            {"handgun", "shotgun", "rifle", "smg", "firearm", "gun"} & weapon_tags
            or any(token in weapon_label for token in ("pistol", "revolver", "rifle", "shotgun", "smg", "firearm", " gun"))
        )
        armed = bool(weapon_id or weapon_label)
        gunfire_case = any(token in context_text for token in ("fire_weapon", "gunfire", "gunshot", "shooting", "firearm"))
        armed_case = any(token in context_text for token in ("armed_assault", "melee_assault", "homicide"))
        contextual = list(tuple(match.get("contextual_cues", ()) or ()))
        if firearm and gunfire_case:
            contextual.append("equipped firearm after nearby gunfire")
            match["score"] = round(min(1.0, float(match.get("score", 0.0) or 0.0) + 0.04), 3)
            match["evidence_weight"] = round(min(1.0, float(match.get("evidence_weight", 0.0) or 0.0) + 0.14), 3)
        elif armed and armed_case:
            contextual.append("equipped weapon near the reported violence")
            match["score"] = round(min(1.0, float(match.get("score", 0.0) or 0.0) + 0.025), 3)
            match["evidence_weight"] = round(min(1.0, float(match.get("evidence_weight", 0.0) or 0.0) + 0.08), 3)

        if len(independent_supporting_reporter_eids(case)) >= 2 and int((case or {}).get("report_conflict_count", 0) or 0) <= 0:
            contextual.append("independent witness descriptions agree")
            match["evidence_weight"] = round(min(1.0, float(match.get("evidence_weight", 0.0) or 0.0) + 0.08), 3)
        matched = list(tuple(match.get("matched_cues", ()) or ()))
        matched.extend(contextual)
        match["matched_cues"] = tuple(dict.fromkeys(matched))
        match["contextual_cues"] = tuple(dict.fromkeys(contextual))
        match["plausible"] = bool(
            float(match.get("score", 0.0) or 0.0) >= 0.62
            and float(match.get("evidence_weight", 0.0) or 0.0) >= 0.28
        )
        return match

    def _received_report_context(self, officer_eid, incident_id):
        ai = self.sim.ecs.get(AI).get(officer_eid)
        context = getattr(ai, "investigation_context", None) if ai is not None else None
        if not is_purposeful_observation(context, purpose="justice_report_search", active_only=True):
            return ai, None
        try:
            same_incident = int(context.get("incident_id")) == int(incident_id)
        except (TypeError, ValueError):
            same_incident = False
        return (ai, context) if same_incident else (ai, None)

    def _resume_received_report_route(self, officer_eid, context):
        ai = self.sim.ecs.get(AI).get(officer_eid)
        will = self.sim.ecs.get(NPCWill).get(officer_eid)
        if ai is None or not isinstance(context, dict):
            return False
        search = context.get("search_state") if isinstance(context.get("search_state"), dict) else {}
        waypoints = tuple(tuple(row) for row in tuple(search.get("waypoints", ()) or ()) if isinstance(row, (tuple, list)) and len(row) >= 3)
        index = max(0, int(search.get("waypoint_index", 0) or 0))
        target = waypoints[index] if index < len(waypoints) else context.get("last_seen_position")
        ai.investigation_context = context
        ai.target = tuple(target) if target is not None else None
        ai.target_eid = None
        if will is not None:
            will.intent = "investigating"
            will.target = ai.target
            will.target_eid = None
            will.last_tick = int(self.sim.tick)
        return True

    def _finish_received_report_search(self, officer_eid, context, *, reason, subject_eid=None):
        ai = self.sim.ecs.get(AI).get(officer_eid)
        will = self.sim.ecs.get(NPCWill).get(officer_eid)
        if ai is None:
            return False
        ai.investigation_context = finish_purposeful_observation(
            context,
            current_tick=self.sim.tick,
            reason=reason,
        )
        ai.state = "idle"
        ai.target = None
        ai.target_eid = None
        if will is not None:
            will.intent = "idle"
            will.target = None
            will.target_eid = None
            will.last_tick = int(self.sim.tick)
        pos = self._position_for(officer_eid)
        self.sim.emit(Event(
            "npc_investigation_complete",
            npc_eid=officer_eid,
            subject_eid=subject_eid,
            incident_id=(context or {}).get("incident_id"),
            purpose="justice_report_search",
            reason=reason,
            x=getattr(pos, "x", None),
            y=getattr(pos, "y", None),
            z=getattr(pos, "z", None),
        ))
        return True

    def on_justice_report_candidate_contact(self, event):
        officer_eid = event.data.get("officer_eid")
        candidate_eid = event.data.get("candidate_eid")
        incident_id = event.data.get("incident_id")
        if officer_eid is None or candidate_eid is None:
            return
        ai, context = self._received_report_context(officer_eid, incident_id)
        case = justice_case_for_incident(self.sim, incident_id)
        if ai is None or context is None or not isinstance(case, dict):
            return
        if str(case.get("status", "") or "").strip().lower() != "unresolved":
            self._finish_received_report_search(officer_eid, context, reason="case_resolved")
            return
        if int(candidate_eid) == int(self.player_eid) and _player_modal_active(self.sim):
            self._defer_player_contact(event.type, event.data)
            return
        report_account = context.get("subject_account") if isinstance(context.get("subject_account"), dict) else {}
        close_account = build_witness_subject_account(
            self.sim,
            officer_eid,
            candidate_eid,
            source_kind="authority_contact",
            confidence=1.0,
        )
        match = self._investigative_contact_match(case, report_account, close_account)
        alleged_eid = report_account.get("suspect_eid")
        recognized_eid = close_account.get("suspect_eid")
        try:
            identity_conflict = bool(
                alleged_eid is not None
                and recognized_eid is not None
                and int(alleged_eid) != int(recognized_eid)
            )
        except (TypeError, ValueError):
            identity_conflict = False
        plausible = bool(
            not identity_conflict
            and match.get("plausible", False)
            and float(match.get("score", 0.0) or 0.0) >= float(context.get("candidate_min_score", 0.64) or 0.64)
            and float(match.get("evidence_weight", 0.0) or 0.0) >= float(context.get("candidate_min_evidence", 0.28) or 0.28)
        )
        if not plausible:
            reason = "recognized_identity_contradiction" if identity_conflict else "close_contact_contradiction"
            updated = reject_purposeful_candidate(
                self.sim,
                context,
                candidate_eid=candidate_eid,
                reason=reason,
                match=match,
            )
            self._resume_received_report_route(officer_eid, updated)
            self.sim.emit(Event(
                "justice_report_candidate_released",
                officer_eid=officer_eid,
                candidate_eid=candidate_eid,
                incident_id=incident_id,
                reason=reason,
            ))
            return

        read = provisional_attribution_read(self.sim, case, candidate_eid, match=match)
        record_justice_case_encounter(
            self.sim,
            incident_id,
            actor_eid=candidate_eid,
            officer_eid=officer_eid,
            choice_id="contact",
            outcome="questioned_from_reported_description",
            match=match,
        )
        if int(candidate_eid) == int(self.player_eid):
            opened = self._open_player_identity_check_prompt(
                officer_eid,
                {"case": case, "match": match},
            )
            if not opened:
                updated = dict(context)
                updated["contact_pending"] = False
                self._resume_received_report_route(officer_eid, updated)
                return
            self._finish_received_report_search(
                officer_eid,
                context,
                reason="candidate_questioned",
                subject_eid=candidate_eid,
            )
            return

        change = None
        if bool(read.get("detainable", read.get("eligible", False))):
            disposition = "evidence_supported_conviction" if bool(read.get("convictable", False)) else "investigator_scene_attribution"
            change = self._record_provisional_attribution_consequence(
                case,
                candidate_eid,
                officer_eid=officer_eid,
                match=match,
                read=read,
                disposition=disposition,
            )
        self.sim.emit(Event(
            "justice_report_candidate_questioned",
            officer_eid=officer_eid,
            candidate_eid=candidate_eid,
            incident_id=incident_id,
            evidence_strength=float(read.get("evidence_strength", 0.0) or 0.0),
            suspicion_supported=bool(read.get("detainable", False)),
            conviction_supported=bool(read.get("convictable", False)),
            detained=isinstance(change, dict),
        ))
        self._finish_received_report_search(
            officer_eid,
            context,
            reason="candidate_questioned",
            subject_eid=candidate_eid,
        )

    def _record_investigator_canvas_contact(self, investigator_eid, actor_eid, incident_id, *, outcome, supplied_account=False):
        ai, context = self._received_report_context(investigator_eid, incident_id)
        if ai is None or context is None:
            return None
        updated = record_purposeful_canvas_contact(
            self.sim,
            context,
            actor_eid=actor_eid,
            outcome=outcome,
            supplied_account=supplied_account,
        )
        self.sim.emit(Event(
            "justice_case_canvas_interviewed",
            investigator_eid=investigator_eid,
            actor_eid=actor_eid,
            incident_id=incident_id,
            outcome=outcome,
            supplied_account=bool(supplied_account),
        ))
        case = justice_case_for_incident(self.sim, incident_id)
        if supplied_account and isinstance(case, dict):
            # Duplicate dispatch is deliberately suppressed, so the responder
            # already carrying the case must adopt useful field testimony.
            best_account = case.get("best_subject_account") if isinstance(case.get("best_subject_account"), dict) else {}
            description = best_account.get("description") if isinstance(best_account.get("description"), dict) else {}
            if description:
                refreshed = dict(updated)
                refreshed["subject_account"] = transmitted_subject_account(
                    best_account,
                    channel="investigator_followup",
                    source_eid=actor_eid,
                    confidence=0.98,
                    propagation_depth=1,
                    preserve_reporter_account=False,
                )
                refreshed["knowledge_channel"] = "investigator_followup"
                refreshed["lead_refresh_count"] = max(0, int(updated.get("lead_refresh_count", 0) or 0)) + 1
                refreshed["last_lead_refresh_tick"] = int(getattr(self.sim, "tick", 0) or 0)
                updated = refreshed
        if isinstance(case, dict) and str(case.get("status", "") or "").strip().lower() != "unresolved":
            self._finish_received_report_search(investigator_eid, updated, reason="case_resolved")
        else:
            self._resume_received_report_route(investigator_eid, updated)
        return updated

    def _formalize_canvas_account(self, investigator_eid, actor_eid, incident_id, record):
        account = record.get("subject_account") if isinstance((record or {}).get("subject_account"), dict) else None
        if not isinstance(account, dict):
            return False
        carried = transmitted_subject_account(
            account,
            channel="investigator_interview",
            source_eid=actor_eid,
            confidence=float((record or {}).get("confidence", 1.0) or 1.0),
            propagation_depth=int((record or {}).get("propagation_depth", 0) or 0),
            preserve_reporter_account=True,
        )
        self.sim.emit(Event(
            "incident_authority_reported",
            incident_id=incident_id,
            npc_eid=actor_eid,
            reporter_eid=actor_eid,
            received_by_eid=investigator_eid,
            method="investigator_interview",
            subject_account=carried,
        ))
        return True

    def on_justice_case_canvas_contact(self, event):
        investigator_eid = event.data.get("investigator_eid")
        actor_eid = event.data.get("actor_eid")
        incident_id = event.data.get("incident_id")
        if investigator_eid is None or actor_eid is None:
            return
        _ai, context = self._received_report_context(investigator_eid, incident_id)
        if context is None:
            return
        if int(actor_eid) == int(self.player_eid):
            if _player_modal_active(self.sim):
                self._defer_player_contact(event.type, event.data)
                return
            case = justice_case_for_incident(self.sim, incident_id) or {}
            kind = str(case.get("kind", "incident") or "incident").strip().replace("_", " ")
            casework_kind = str(context.get("casework_kind", "investigator_canvas") or "investigator_canvas").strip().lower()
            investigator_name = _entity_display_name(self.sim, investigator_eid, title_case=True) or "Investigator"
            if casework_kind == "wildlife_enforcement_canvas":
                opening_lines = [
                    f'The wildlife officer stops beside you. "I am following up on a reported hunt near here."',
                    '"Did you see a hunter, an animal, or a carcass?"',
                ]
                subtitle = "Wildlife Enforcement"
            elif casework_kind == "arson_investigation_canvas":
                opening_lines = [
                    f'The fire investigator stops beside you. "I am checking how the fire near here began."',
                    '"Did you see anyone enter, leave, or handle anything near the first smoke?"',
                ]
                subtitle = "Fire Investigation"
            elif casework_kind == "patrol_canvas":
                opening_lines = [
                    f'The officer stops beside you. "I am following up on a reported {kind} near here."',
                    '"Did you see or hear anything?"',
                ]
                subtitle = str(case.get("jurisdiction_name", "Justice Office") or "Justice Office")
            else:
                opening_lines = [
                    f'The investigator stops beside you. "I am asking around about a reported {kind} near here."',
                    '"Did you see or hear anything?"',
                ]
                subtitle = str(case.get("jurisdiction_name", "Justice Office") or "Justice Office")
            misdirection_options = self._player_case_misdirection_options(incident_id)
            topics = [{"id": "share", "label": "Tell them what you saw"}]
            topics.extend(
                {
                    "id": row["topic_id"],
                    "label": f"Say the culprit was {row['description_summary']}",
                }
                for row in misdirection_options
            )
            topics.extend([
                {"id": "nothing", "label": "Say you saw nothing"},
                {"id": "decline", "label": "Decline to answer"},
            ])
            state = self._dialog_ui_state()
            self.sim.set_time_paused(True, reason="dialog")
            state.update({
                "open": True,
                "kind": self.CASE_CANVAS_DIALOG_KIND,
                "npc_eid": investigator_eid,
                "property_id": case.get("property_id") or None,
                "title": f"Questions: {investigator_name}",
                "subtitle": subtitle,
                "transcript": opening_lines,
                "topics": topics,
                "selected_index": 0,
                "scroll": 0,
                "hint": "? help",
                "new_topic_ids": [],
                "close_pending": False,
                "machine_action": None,
            })
            self.player_surrender_prompt = {
                "kind": self.CASE_CANVAS_DIALOG_KIND,
                "npc_eid": investigator_eid,
                "incident_id": int(incident_id),
                "casework_kind": casework_kind,
                "property_id": case.get("property_id") or None,
                "jurisdiction_name": subtitle,
                "case_id": case.get("case_id"),
                "opened_tick": int(getattr(self.sim, "tick", 0)),
                "misdirection_options": {
                    row["topic_id"]: deepcopy(row)
                    for row in misdirection_options
                },
            }
            return

        knowledge = self.sim.ecs.get(IncidentKnowledge).get(actor_eid)
        record = knowledge.records.get(int(incident_id)) if knowledge is not None else None
        if incident_case_cooperation_withheld(self.sim, actor_eid, incident_id):
            self._record_investigator_canvas_contact(
                investigator_eid,
                actor_eid,
                incident_id,
                outcome="statement_withheld",
                supplied_account=False,
            )
            return
        supplied = self._formalize_canvas_account(investigator_eid, actor_eid, incident_id, record) if isinstance(record, dict) else False
        self._record_investigator_canvas_contact(
            investigator_eid,
            actor_eid,
            incident_id,
            outcome="statement_supplied" if supplied else "nothing_known",
            supplied_account=supplied,
        )

    def on_justice_case_canvas_choice(self, event):
        if event.data.get("eid") != self.player_eid or not self._player_surrender_prompt_open():
            return
        prompt = self.player_surrender_prompt if isinstance(self.player_surrender_prompt, dict) else {}
        if str(prompt.get("kind", "") or "").strip().lower() != self.CASE_CANVAS_DIALOG_KIND:
            return
        choice = str(event.data.get("choice_id", "") or "").strip().lower() or "decline"
        investigator_eid = prompt.get("npc_eid")
        incident_id = prompt.get("incident_id")
        casework_kind = str(prompt.get("casework_kind", "investigator_canvas") or "investigator_canvas").strip().lower()
        options = prompt.get("misdirection_options") if isinstance(prompt.get("misdirection_options"), dict) else {}
        misdirection_option = options.get(choice)
        deception_attempted = isinstance(misdirection_option, dict)
        case = justice_case_for_incident(self.sim, incident_id)
        if deception_attempted and not isinstance(case, dict):
            deception_attempted = False
            misdirection_option = None
            choice = "decline"
        supplied = False
        deception_read = {}
        deception_succeeded = False
        if choice == "share":
            knowledge = self.sim.ecs.get(IncidentKnowledge).get(self.player_eid)
            record = knowledge.records.get(int(incident_id)) if knowledge is not None else None
            supplied = self._formalize_canvas_account(
                investigator_eid,
                self.player_eid,
                incident_id,
                record,
            ) if isinstance(record, dict) else False
        elif deception_attempted and isinstance(case, dict):
            deception_read = self._justice_misdirection_read(
                investigator_eid,
                prompt,
                misdirection_option,
                case,
            )
            if bool(deception_read.get("succeeded", False)):
                supplied = isinstance(
                    self._accept_player_case_misdirection(
                        investigator_eid,
                        prompt,
                        misdirection_option,
                        deception_read,
                    ),
                    dict,
                )
                deception_succeeded = supplied
            if not deception_succeeded:
                self._record_player_case_misdirection_attempt(
                    case,
                    investigator_eid,
                    misdirection_option,
                    deception_read,
                    accepted=False,
                )
        elif choice not in {"share", "nothing", "decline"}:
            choice = "decline"
        self._close_player_surrender_prompt()
        contact_outcome = (
            "misdirection_accepted"
            if deception_succeeded
            else "misdirection_rejected"
            if deception_attempted
            else "statement_supplied"
            if supplied
            else "nothing_known"
            if choice == "nothing" or choice == "share"
            else "declined"
        )
        self._record_investigator_canvas_contact(
            investigator_eid,
            self.player_eid,
            incident_id,
            outcome=contact_outcome,
            supplied_account=supplied,
        )
        obstruction_change = None
        if deception_attempted and not deception_succeeded:
            obstruction_change = self._escalate_player_identity_deception(
                by_eid=investigator_eid,
                prompt=prompt,
            )
        if deception_attempted:
            self.sim.emit(Event(
                "justice_case_canvas_misdirection_resolved",
                eid=self.player_eid,
                investigator_eid=investigator_eid,
                incident_id=incident_id,
                case_id=prompt.get("case_id"),
                outcome=contact_outcome,
                succeeded=deception_succeeded,
                obstruction_offense=isinstance(obstruction_change, dict),
                framed_role=(misdirection_option or {}).get("role"),
                claimed_description=(misdirection_option or {}).get("description_summary"),
            ))
        role_label = "wildlife officer" if casework_kind == "wildlife_enforcement_canvas" else "fire investigator" if casework_kind == "arson_investigation_canvas" else "officer" if casework_kind == "patrol_canvas" else "investigator"
        if deception_attempted:
            claimed_description = str(misdirection_option.get("description_summary", "someone else") or "someone else")
            if deception_succeeded:
                lines = [
                    f"You say the culprit was {claimed_description}.",
                    f"The {role_label} accepts the description and follows the lead.",
                ]
                title = f"{role_label.title()} Takes the Lead"
            else:
                lines = [
                    f"You try to put the incident on {claimed_description}.",
                    f"The {role_label} catches the false account, records obstruction, and moves to detain you.",
                ]
                title = "Obstruction Recorded"
        else:
            lines = {
                "share": [
                    f"You tell the {role_label} what you remember." if supplied else "You have nothing useful to add.",
                    f"The {role_label} makes a note and moves on.",
                ],
                "nothing": [f"You say you saw nothing. The {role_label} makes a note and moves on."],
                "decline": [f"You decline to answer. The {role_label} moves on."],
            }.get(choice, [f"You decline to answer. The {role_label} moves on."])
            title = f"{role_label.title()} Moves On"
        self._present_justice_result(
            title,
            lines,
            property_id=prompt.get("property_id"),
            subtitle=prompt.get("jurisdiction_name", "Justice Office"),
        )

    def _open_player_identity_check_prompt(self, npc_eid, match_row):
        if _player_modal_active(self.sim):
            return False
        if npc_eid is None or not isinstance(match_row, dict):
            return False
        case = match_row.get("case") if isinstance(match_row.get("case"), dict) else {}
        match = match_row.get("match") if isinstance(match_row.get("match"), dict) else {}
        account = case.get("best_subject_account") if isinstance(case.get("best_subject_account"), dict) else {}
        description = account.get("description") if isinstance(account.get("description"), dict) else {}
        incident_id = case.get("incident_id")
        if incident_id is None:
            return False
        kind = str(case.get("kind", "incident") or "incident").strip().replace("_", " ")
        summary = subject_description_summary(description)
        cues = [str(cue).strip() for cue in tuple(match.get("matched_cues", ()) or ()) if str(cue).strip()]
        provisional_read = provisional_attribution_read(self.sim, case, self.player_eid, match=match)
        enforcer, _law_drive, _priority = self._actor_is_enforcer(npc_eid)
        formal_identity_demand = bool(
            enforcer
            and str(case.get("status", "") or "").strip().lower() == "unresolved"
            and bool(case.get("factual_incident", False))
            and bool(match.get("plausible", False))
            and float(match.get("score", 0.0) or 0.0) >= 0.62
        )
        jurisdiction_name = str(case.get("jurisdiction_name", "Justice Office") or "Justice Office").strip() or "Justice Office"
        npc_ai = self.sim.ecs.get(AI).get(npc_eid)
        investigation_context = getattr(npc_ai, "investigation_context", None) if npc_ai is not None else None
        casework_kind = str((investigation_context or {}).get("casework_kind", "") or "").strip().lower()
        weapon_line = (
            "The officer's attention lingers on the weapon in your hand."
            if any("weapon" in cue or "firearm" in cue for cue in cues)
            else ""
        )
        if casework_kind == "wildlife_enforcement_canvas":
            authority_label = "wildlife officer"
            jurisdiction_name = "Wildlife Enforcement"
            opening = '"I am following up on a reported hunt near here."'
        elif casework_kind == "arson_investigation_canvas":
            authority_label = "fire investigator"
            jurisdiction_name = "Fire Investigation"
            opening = '"I am looking into how the fire near here began."'
        else:
            authority_label = "officer"
            opening = f'"I am looking into a reported {kind} near here."'
        transcript = [
            f"The {authority_label} steps into your path. {opening}",
            f'"A witness described {summary}. You match enough of it that I need your name and where you have been."',
        ]
        if formal_identity_demand:
            transcript.append('"This is a formal identity demand. Refusing to identify yourself is an offense."')
        if weapon_line:
            transcript.insert(1, weapon_line)
        misdirection_options = self._player_case_misdirection_options(incident_id)
        topics = [
            {"id": "identify", "label": "Give your name"},
            {"id": "explain", "label": "Give your name and explain"},
        ]
        topics.extend(
            {
                "id": row["topic_id"],
                "label": f"Give your name; accuse {row['description_summary']}",
            }
            for row in misdirection_options
        )
        topics.append({
            "id": "decline",
            "label": "Refuse to identify" if formal_identity_demand else "Decline the questions",
        })
        state = self._dialog_ui_state()
        self.sim.set_time_paused(True, reason="dialog")
        state.update({
            "open": True,
            "kind": self.IDENTITY_CHECK_DIALOG_KIND,
            "npc_eid": npc_eid,
            "property_id": case.get("property_id") or None,
            "title": f"Identity Check: {_entity_display_name(self.sim, npc_eid, title_case=True) or authority_label.title()}",
            "subtitle": jurisdiction_name,
            "transcript": transcript,
            "topics": topics,
            "selected_index": 0,
            "scroll": 0,
            "hint": "? help",
            "new_topic_ids": [],
            "close_pending": False,
            "machine_action": None,
        })
        self.player_surrender_prompt = {
            "kind": self.IDENTITY_CHECK_DIALOG_KIND,
            "npc_eid": npc_eid,
            "incident_id": int(incident_id),
            "case_id": case.get("case_id"),
            "match": dict(match),
            "provisional_read": dict(provisional_read),
            "property_id": case.get("property_id") or None,
            "opened_tick": int(getattr(self.sim, "tick", 0)),
            "jurisdiction_key": str(case.get("jurisdiction_key", "") or "").strip().lower(),
            "jurisdiction_name": jurisdiction_name,
            "casework_kind": casework_kind,
            "formal_identity_demand": formal_identity_demand,
            "misdirection_options": {
                row["topic_id"]: deepcopy(row)
                for row in misdirection_options
            },
        }
        return True

    def _resolve_player_identity_check_choice(self, choice_id, *, prompt):
        prompt = prompt if isinstance(prompt, dict) else {}
        choice = str(choice_id or "").strip().lower() or "decline"
        misdirection_options = (
            prompt.get("misdirection_options")
            if isinstance(prompt.get("misdirection_options"), dict)
            else {}
        )
        misdirection_option = misdirection_options.get(choice)
        deception_attempted = isinstance(misdirection_option, dict)
        if choice not in {"identify", "explain", "decline"} and not deception_attempted:
            choice = "decline"
        npc_eid = prompt.get("npc_eid")
        incident_id = prompt.get("incident_id")
        match = prompt.get("match") if isinstance(prompt.get("match"), dict) else {}
        provisional_read = prompt.get("provisional_read") if isinstance(prompt.get("provisional_read"), dict) else {}
        case = justice_case_for_incident(self.sim, incident_id)
        identity = actor_identity_snapshot(self.sim, self.player_eid) or {}
        identity_supplied = choice in {"identify", "explain"} or deception_attempted
        presented_name = str(identity.get("personal_name", "") or "").strip() if identity_supplied else ""
        if identity_supplied and npc_eid is not None:
            remember_presented_identity(
                self.sim,
                npc_eid,
                self.player_eid,
                source_eid=self.player_eid,
                relation_kind="identity_check",
                standing=0.0,
                met_directly=True,
                benefits=("known_name", "justice_contact"),
                tick=int(getattr(self.sim, "tick", 0)),
            )

        deception_read = {}
        deception_succeeded = False
        accepted_account = None
        if deception_attempted and isinstance(case, dict):
            deception_read = self._justice_misdirection_read(
                npc_eid,
                prompt,
                misdirection_option,
                case,
            )
            deception_succeeded = bool(deception_read.get("succeeded", False))
            if deception_succeeded:
                accepted_account = self._accept_player_case_misdirection(
                    npc_eid,
                    prompt,
                    misdirection_option,
                    deception_read,
                )
                deception_succeeded = isinstance(accepted_account, dict)
            if not deception_succeeded:
                self._record_player_case_misdirection_attempt(
                    case,
                    npc_eid,
                    misdirection_option,
                    deception_read,
                    accepted=False,
                )

        detainable = bool(
            provisional_read.get("detainable", provisional_read.get("eligible", False))
        ) and isinstance(case, dict)
        explanation_succeeded = False
        if detainable and choice == "explain" and not bool(provisional_read.get("convictable", False)):
            skill_defense = 0.72 + float(self._questioning_skill_bonus("explain"))
            scene_distance = provisional_read.get("scene_distance")
            age_ticks = provisional_read.get("age_ticks")
            scene_distance = 12.0 if scene_distance is None else float(scene_distance)
            age_ticks = 240.0 if age_ticks is None else float(age_ticks)
            proximity = max(0.0, 1.0 - (scene_distance / 12.0))
            freshness = max(0.0, 1.0 - (age_ticks / 240.0))
            evidence_pressure = (
                0.68
                + max(0.0, float(provisional_read.get("match_score", 0.70) or 0.70) - 0.70) * 0.34
                + proximity * 0.025
                + freshness * 0.02
            )
            explanation_succeeded = skill_defense >= evidence_pressure
        provisional_punishment = bool(detainable and not explanation_succeeded and not deception_succeeded)
        identity_refusal_offense = bool(
            choice == "decline"
            and bool(prompt.get("formal_identity_demand", False))
        )
        obstruction_offense = bool(deception_attempted and not deception_succeeded)
        if deception_attempted:
            outcome = (
                "misdirection_accepted"
                if deception_succeeded
                else "misdirection_rejected_for_booking"
                if provisional_punishment
                else "misdirection_rejected_obstruction"
            )
        else:
            outcome = (
                "refusal_and_suspicion_detention"
                if provisional_punishment and identity_refusal_offense
                else "provisionally_attributed_for_booking"
                if provisional_punishment
                else "failure_to_identify_recorded"
                if identity_refusal_offense
                else {
                    "identify": "identity_supplied_without_charge",
                    "explain": "explanation_accepted_without_charge" if explanation_succeeded else "explanation_noted_without_charge",
                    "decline": "declined_without_charge",
                }[choice]
            )
        record_justice_case_encounter(
            self.sim,
            incident_id,
            actor_eid=self.player_eid,
            officer_eid=npc_eid,
            choice_id=choice,
            outcome=outcome,
            match=match,
            presented_name=presented_name,
        )
        provisional_change = None
        if provisional_punishment:
            provisional_change = self._record_provisional_attribution_consequence(
                case,
                self.player_eid,
                officer_eid=npc_eid,
                match=match,
                read=provisional_read,
                disposition=f"player_identity_check_{choice}",
            )
        refusal_change = None
        if identity_refusal_offense:
            refusal_change = self._escalate_player_identity_refusal(
                by_eid=npc_eid,
                prompt=prompt,
            )
        obstruction_change = None
        if obstruction_offense:
            obstruction_change = self._escalate_player_identity_deception(
                by_eid=npc_eid,
                prompt=prompt,
            )
        self.sim.emit(Event(
            "justice_identity_check_resolved",
            eid=self.player_eid,
            officer_eid=npc_eid,
            incident_id=incident_id,
            case_id=prompt.get("case_id"),
            choice_id=choice,
            outcome=outcome,
            presented_name=presented_name,
            match_score=float(match.get("score", 0.0) or 0.0),
            justice_record_created=(
                isinstance(provisional_change, dict)
                or isinstance(refusal_change, dict)
                or isinstance(obstruction_change, dict)
            ),
            provisional_attribution=provisional_punishment,
            formal_identity_demand=bool(prompt.get("formal_identity_demand", False)),
            identity_refusal_offense=identity_refusal_offense,
            deception_attempted=deception_attempted,
            deception_succeeded=deception_succeeded,
            obstruction_offense=obstruction_offense,
            framed_role=(misdirection_option or {}).get("role"),
            claimed_description=(misdirection_option or {}).get("description_summary"),
            canonical_identity_resolved=False,
        ))
        if provisional_punishment:
            if isinstance(provisional_change, dict):
                source_prop = self.sim.properties.get(str(prompt.get("property_id", "") or ""))
                attribution = self._active_case_attribution_for(case, self.player_eid)
                booked = self._book_player(
                    by_eid=npc_eid,
                    source_prop=source_prop,
                    provisional_case=case,
                    provisional_attribution=attribution,
                )
                for row in reversed(tuple(case.get("provisional_attributions", ()) or ())):
                    if isinstance(row, dict) and row.get("actor_eid") == self.player_eid:
                        if str(row.get("adjudication_status", "") or "").strip().lower() == "exonerated_at_booking_review":
                            row["punishment_status"] = "exonerated_at_booking"
                        else:
                            row["punishment_status"] = "booked" if booked else "justice_record_active"
                        break
                return bool(booked or provisional_change)
        casework_kind = str(prompt.get("casework_kind", "") or "").strip().lower()
        authority_label = "wildlife officer" if casework_kind == "wildlife_enforcement_canvas" else "fire investigator" if casework_kind == "arson_investigation_canvas" else "officer"
        if deception_attempted:
            claimed_description = str(misdirection_option.get("description_summary", "someone else") or "someone else")
            if deception_succeeded:
                lines = [
                    f"You give your name, then say the person they want was {claimed_description}.",
                    f"The {authority_label} accepts the description and turns the search toward it.",
                ]
                title = f"{authority_label.title()} Takes the Lead"
            else:
                lines = [
                    f"You give your name, then try to put the reported act on {claimed_description}.",
                    f"The {authority_label} catches the false account, records obstruction, and moves to detain you.",
                ]
                title = "Obstruction Recorded"
        else:
            lines = {
                "identify": [
                    f"You give the name {presented_name or 'you use'}. The {authority_label} writes it down.",
                    f"After another look, the {authority_label} steps aside.",
                ],
                "explain": [
                    f"You give your name and explain where you have been. The {authority_label} listens and makes a note.",
                    f"The {authority_label} steps aside." if explanation_succeeded else f"After another look, the {authority_label} steps aside.",
                ],
                "decline": [
                    (
                        f"You refuse to identify yourself. The {authority_label} records failure to identify and moves to detain you."
                        if identity_refusal_offense
                        else f"You decline to answer. The {authority_label} watches you for a moment, makes a note, and steps aside."
                    ),
                ],
            }[choice]
            title = "Identity Refusal Recorded" if identity_refusal_offense else f"{authority_label.title()} Steps Aside"
        self._present_justice_result(
            title,
            lines,
            subtitle=str(prompt.get("jurisdiction_name", "Justice Office") or "Justice Office"),
        )
        return True

    def _resolve_player_questioning_choice(self, choice_id, *, by_eid=None, source_prop=None, snapshot=None):
        snapshot = snapshot if isinstance(snapshot, dict) else self._player_bookable_snapshot()
        if snapshot is None:
            return False
        choice_id = str(choice_id or "").strip().lower() or "refuse"
        if choice_id == "refuse":
            self.sim.emit(Event(
                "justice_questioning_resolved",
                eid=self.player_eid,
                outcome="custody_escalation",
                cooperation_score=0.0,
                severity_bucket="refusal",
            ))
            self._record_incident(
                self.player_eid,
                incident_type="resisting_custody",
                severity=max(18, int(snapshot.get("active_score", 0) or 0) + 8),
                source_event="justice_questioning_choice",
                property_id=(source_prop or {}).get("id") if isinstance(source_prop, dict) else None,
                x=getattr(self._position_for(self.player_eid), "x", 0),
                y=getattr(self._position_for(self.player_eid), "y", 0),
                witnessed=True,
                note="questioning_refusal",
            )
            _record_justice_questioning_resolution(
                self.sim,
                self.player_eid,
                disposition="custody_escalation",
                inspected_counts={},
                kept_contraband_count=0,
                match_summaries=(),
            )
            self._escalate_player_surrender_refusal(by_eid=by_eid, source_prop=source_prop, snapshot=snapshot)
            return True

        cooperation_score = {
            "cooperate": 1.0,
            "explain": 0.82,
            "deflect": 0.38,
        }.get(choice_id, 0.0)
        cooperation_score = min(1.0, max(0.0, float(cooperation_score) + self._questioning_skill_bonus(choice_id)))
        inspection = self._inspect_actor_inventory(self.player_eid, update_inventory=True, inspector_eid=by_eid)
        counts = inspection.get("counts", {}) if isinstance(inspection, dict) else {}
        severity_bucket = str(inspection.get("severity_bucket", "clear") or "clear").strip().lower()
        profile = self._justice_enforcement_profile(snapshot=snapshot, source_prop=source_prop)
        match_labels = self._inspection_match_labels(inspection)
        match_reasons = self._inspection_match_reasons(inspection)
        stolen_intent_labels = tuple(inspection.get("stolen_intent_labels", ()) or ()) if isinstance(inspection, dict) else ()
        stolen_intent_counts = dict(inspection.get("stolen_intent_counts", {}) or {}) if isinstance(inspection, dict) else {}
        force_context = self._force_event_payload(self.player_eid)
        evidence_surcharge = int(self._inspection_evidence_surcharge(inspection))
        protective = (
            local_protective_pressure_snapshot(
                self.sim,
                source_prop,
                current_tick=int(getattr(self.sim, "tick", 0)),
            )
            if isinstance(source_prop, dict)
            else {}
        )
        disposition = "release_warning"
        kept_contraband_count = 0
        confiscation = {
            "entries": (),
            "labels": (),
            "count": 0,
            "held_entries": (),
            "held_labels": (),
            "held_count": 0,
            "forfeited_entries": (),
            "forfeited_labels": (),
            "forfeited_count": 0,
            "held_reason_labels": (),
            "forfeited_reason_labels": (),
            "reason_labels": (),
        }
        held_prop = self._questioning_hold_property(source_prop)
        held_prop_name = str((held_prop or {}).get("name", "Justice Office") if isinstance(held_prop, dict) else "Justice Office").strip() or "Justice Office"
        fine_multiplier = 0.0

        if severity_bucket == "violent_evidence":
            disposition = "full_booking"
        elif int(counts.get("reported_stolen", 0) or 0) > 0:
            disposition = "full_booking"
        elif int(counts.get("contraband", 0) or 0) > 0:
            contraband_rows = tuple(inspection.get("contraband", ()) or ())
            if cooperation_score >= 0.98 and profile.get("keep_contraband_possible") and int(counts.get("reported_stolen", 0) or 0) <= 0 and int(counts.get("incident_evidence", 0) or 0) <= 0 and int(counts.get("latent_claim_violation", 0) or 0) <= 0:
                disposition = "release_keep_items"
                kept_contraband_count = int(counts.get("contraband", 0) or 0)
            elif cooperation_score >= 0.76 and profile.get("citation_pref"):
                disposition = "citation_confiscation"
                confiscation = self._remove_inventory_rows(self.player_eid, contraband_rows, reason="citation_confiscated", held_prop=held_prop)
            else:
                disposition = "fine_confiscation"
                confiscation = self._remove_inventory_rows(self.player_eid, contraband_rows, reason="fine_confiscated", held_prop=held_prop)
        elif int(counts.get("latent_claim_violation", 0) or 0) > 0:
            disposition = "release_warning" if cooperation_score >= 0.75 else "fine_confiscation"

        if disposition == "full_booking":
            _record_justice_questioning_resolution(
                self.sim,
                self.player_eid,
                disposition=disposition,
                inspected_counts=counts,
                kept_contraband_count=kept_contraband_count,
                match_summaries=inspection.get("match_summaries", ()),
                match_labels=match_labels,
                match_reasons=match_reasons,
                evidence_surcharge=evidence_surcharge,
            )
            self.sim.emit(Event(
                "justice_questioning_resolved",
                eid=self.player_eid,
                outcome=disposition,
                cooperation_score=round(float(cooperation_score), 2),
                severity_bucket=severity_bucket,
                contraband_count=int(counts.get("contraband", 0) or 0),
                latent_claim_count=int(counts.get("latent_claim_violation", 0) or 0),
                reported_stolen_count=int(counts.get("reported_stolen", 0) or 0),
                incident_evidence_count=int(counts.get("incident_evidence", 0) or 0),
                kept_contraband_count=int(kept_contraband_count),
                confiscated_item_count=0,
                confiscated_labels=(),
                penalty_breakdown=self._player_penalty_breakdown(
                    snapshot,
                    fine_due=0,
                    evidence_surcharge=evidence_surcharge,
                    multiplier=0.0,
                    disposition=disposition,
                ),
                match_summaries=tuple(inspection.get("match_summaries", ()) or ()),
                incident_match_labels=match_labels,
                incident_match_reasons=match_reasons,
                stolen_intent_labels=stolen_intent_labels,
                stolen_intent_counts=stolen_intent_counts,
                **force_context,
                evidence_surcharge=evidence_surcharge,
                protective_posture_label=str((protective or {}).get("state_label", "") or "").strip(),
            ))
            return self._book_player(
                by_eid=by_eid,
                source_prop=source_prop,
                inspection=inspection,
                questioning_disposition=disposition,
            )

        fine_due = 0
        current_debt_balance = int(self._player_justice_debt_balance())
        fine_result = {
            "fine_paid": 0,
            "cash_fine_paid": 0,
            "wallet_fine_paid": 0,
            "bank_fine_paid": 0,
            "debt_added": 0,
            "fine_outstanding": 0,
            "wallet_credits_before": 0,
            "wallet_credits_after": 0,
            "asset_credits_before": 0,
            "asset_credits_after": 0,
            "bank_balance_before": 0,
            "bank_balance_after": 0,
            "debt_balance_before": current_debt_balance,
            "debt_balance_after": current_debt_balance,
        }
        if disposition in {"citation_confiscation", "fine_confiscation"} or int(counts.get("reported_stolen", 0) or 0) > 0:
            base_fine = int(self._player_fine_amount(snapshot))
            if disposition == "citation_confiscation":
                fine_multiplier = 0.25
                fine_due = max(10, int(round(base_fine * 0.25)))
            elif disposition == "fine_confiscation":
                fine_multiplier = 0.5
                fine_due = max(20, int(round(base_fine * 0.5)))
            else:
                fine_multiplier = 0.6
                fine_due = max(30, int(round(base_fine * 0.6)))
            fine_result = self._collect_player_fine(fine_due)
        penalty_breakdown = self._player_penalty_breakdown(
            snapshot,
            fine_due=fine_due,
            fine_result=fine_result,
            evidence_surcharge=evidence_surcharge,
            multiplier=fine_multiplier,
            disposition=disposition,
        )

        _record_justice_questioning_resolution(
            self.sim,
            self.player_eid,
            disposition=disposition,
            inspected_counts=counts,
            kept_contraband_count=kept_contraband_count,
            match_summaries=inspection.get("match_summaries", ()),
            match_labels=match_labels,
            match_reasons=match_reasons,
            evidence_surcharge=evidence_surcharge,
        )
        self.sim.emit(Event(
            "justice_questioning_resolved",
            eid=self.player_eid,
            outcome=disposition,
            cooperation_score=round(float(cooperation_score), 2),
            severity_bucket=severity_bucket,
            contraband_count=int(counts.get("contraband", 0) or 0),
            latent_claim_count=int(counts.get("latent_claim_violation", 0) or 0),
            reported_stolen_count=int(counts.get("reported_stolen", 0) or 0),
            incident_evidence_count=int(counts.get("incident_evidence", 0) or 0),
            kept_contraband_count=int(kept_contraband_count),
            confiscated_item_count=int(confiscation.get("count", 0) or 0),
            confiscated_labels=tuple(confiscation.get("labels", ()) or ()),
            held_item_count=int(confiscation.get("held_count", 0) or 0),
            held_labels=tuple(confiscation.get("held_labels", ()) or ()),
            forfeited_item_count=int(confiscation.get("forfeited_count", 0) or 0),
            forfeited_labels=tuple(confiscation.get("forfeited_labels", ()) or ()),
            held_reason_labels=tuple(confiscation.get("held_reason_labels", ()) or ()),
            forfeited_reason_labels=tuple(confiscation.get("forfeited_reason_labels", ()) or ()),
            penalty_breakdown=penalty_breakdown,
            fine_due=int(fine_due),
            fine_paid=int(fine_result.get("fine_paid", 0) or 0),
            cash_fine_paid=int(fine_result.get("cash_fine_paid", 0) or 0),
            wallet_fine_paid=int(fine_result.get("wallet_fine_paid", 0) or 0),
            bank_fine_paid=int(fine_result.get("bank_fine_paid", 0) or 0),
            debt_added=int(fine_result.get("debt_added", 0) or 0),
            fine_outstanding=int(fine_result.get("fine_outstanding", 0) or 0),
            match_summaries=tuple(inspection.get("match_summaries", ()) or ()),
            incident_match_labels=match_labels,
            incident_match_reasons=match_reasons,
            stolen_intent_labels=stolen_intent_labels,
            stolen_intent_counts=stolen_intent_counts,
            **force_context,
            evidence_surcharge=evidence_surcharge,
            protective_posture_label=str((protective or {}).get("state_label", "") or "").strip(),
        ))

        player_pos = self._position_for(self.player_eid)
        release_change = _release_justice_from_custody(
            self.sim,
            self.player_eid,
            new_score=0,
            x=getattr(player_pos, "x", 0),
            y=getattr(player_pos, "y", 0),
        )
        self._emit_change_events(release_change, source_event="justice_questioning_resolved", reason=disposition)
        lines = [
            self._inspection_summary_text(inspection),
        ]
        force_line = self._force_context_line(self.player_eid)
        if force_line:
            lines.append(force_line)
        strongest_match = self._strongest_inspection_match_text(inspection)
        if strongest_match:
            lines.append(f"Recorded match: {strongest_match}.")
        if evidence_surcharge > 0:
            lines.append(f"Evidence surcharge if booked: {evidence_surcharge}c.")
        protective_label = str((protective or {}).get("state_label", "") or "").strip()
        protective_summary = str((protective or {}).get("summary", "") or "").strip()
        if protective_label:
            if protective_summary:
                lines.append(f"{protective_label}: {protective_summary}.")
            else:
                lines.append(f"{protective_label} is already in effect here.")
        if disposition == "release_keep_items":
            lines.append("They let the low-severity contraband go this time.")
        elif disposition == "release_warning":
            lines.append("You are warned and released.")
        elif disposition == "citation_confiscation":
            payment_text = self._payment_result_text(fine_result)
            lines.append(f"Citation issued for {fine_due}c" + (f"; {payment_text}." if payment_text else "."))
        elif disposition == "fine_confiscation":
            payment_text = self._payment_result_text(fine_result)
            lines.append(f"Fine issued for {fine_due}c" + (f"; {payment_text}." if payment_text else "."))
        held_count = int(confiscation.get("held_count", 0) or 0)
        forfeited_count = int(confiscation.get("forfeited_count", 0) or 0)
        if held_count > 0:
            held_label_text = self._label_list_text(confiscation.get("held_labels", ()))
            held_reason_text = self._reason_list_text(confiscation.get("held_reason_labels", ()))
            line = f"Held for release at {held_prop_name}: {held_count} item(s)"
            if held_label_text:
                line += f" ({held_label_text})"
            if held_reason_text:
                line += f" because {held_reason_text}"
            lines.append(line + ".")
        if forfeited_count > 0:
            forfeited_label_text = self._label_list_text(confiscation.get("forfeited_labels", ()))
            forfeited_reason_text = self._reason_list_text(confiscation.get("forfeited_reason_labels", ()))
            line = f"Forfeited/confiscated: {forfeited_count} item(s)"
            if forfeited_label_text:
                line += f" ({forfeited_label_text})"
            if forfeited_reason_text:
                line += f" because {forfeited_reason_text}"
            lines.append(line + ".")
        self._present_justice_result(
            "Questioning Resolved",
            lines,
            property_id=(source_prop or {}).get("id") if isinstance(source_prop, dict) else None,
            subtitle=str((source_prop or {}).get("name", "") if isinstance(source_prop, dict) else "").strip(),
        )
        return True

    def _open_player_surrender_prompt(self, npc_eid, *, snapshot=None, source_prop=None, respect_cooldown=False):
        if _player_modal_active(self.sim):
            return False
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
        restitution_due = max(0, int(snapshot.get("restitution_due", 0) or 0))
        restitution_sites = max(0, int(snapshot.get("restitution_property_count", 0) or 0))
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
        if restitution_due > 0:
            site_phrase = "site" if restitution_sites == 1 else "sites"
            booking_line += f" That includes {restitution_due}c restitution for damaged property across {restitution_sites} {site_phrase}."

        state = self._dialog_ui_state()
        self.sim.set_time_paused(True, reason="dialog")
        self._rehydrate_local_opportunity_knowledge(
            source_prop=source_prop,
            reason="justice_surrender",
        )
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

    def _open_player_justice_prompt(self, npc_eid=None, *, snapshot=None, source_prop=None, respect_cooldown=False):
        snapshot = snapshot if isinstance(snapshot, dict) else self._player_bookable_snapshot()
        if snapshot is None:
            return False
        tier = str(snapshot.get("wanted_tier", "clear")).strip().lower() or "clear"
        if tier == "questioning":
            if respect_cooldown and npc_eid is not None and self._officer_surrender_offer_on_cooldown(npc_eid):
                return False
            return self._open_player_questioning_prompt(npc_eid, snapshot=snapshot, source_prop=source_prop)
        return self._open_player_surrender_prompt(
            npc_eid,
            snapshot=snapshot,
            source_prop=source_prop,
            respect_cooldown=respect_cooldown,
        )

    def _close_player_surrender_prompt(self):
        state = self._dialog_ui_state()
        if bool(state.get("open")) and str(state.get("kind", "")).strip().lower() in {
            self.SURRENDER_DIALOG_KIND,
            self.QUESTIONING_DIALOG_KIND,
            self.IDENTITY_CHECK_DIALOG_KIND,
            self.CASE_CANVAS_DIALOG_KIND,
        }:
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
        for eid in self.sim.entity_ids_in_radius(
            player_pos.x,
            player_pos.y,
            player_pos.z,
            radius,
        ):
            pos = positions.get(eid)
            if pos is None:
                continue
            if eid == self.player_eid or pos.z != player_pos.z:
                continue
            dist = _manhattan(pos.x, pos.y, player_pos.x, player_pos.y)
            if dist <= 0 or dist > radius:
                continue
            enforcer, law_drive, priority = self._actor_is_enforcer(eid)
            if not enforcer:
                continue
            if self._justice_response_interrupted(eid, response_role="justice_detention"):
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

    def _escalate_player_identity_offense(
        self,
        *,
        by_eid=None,
        prompt=None,
        incident_type,
        severity,
        source_event,
        note_kind,
        event_type,
        threat_type,
        ingress_kind,
    ):
        """Turn a witnessed identity-check offense into bounded custody pressure."""

        prompt = prompt if isinstance(prompt, dict) else {}
        player_pos = self._position_for(self.player_eid)
        if player_pos is None:
            return None
        property_id = str(prompt.get("property_id", "") or "").strip() or None
        change = self._record_incident(
            self.player_eid,
            incident_type=incident_type,
            severity=int(severity),
            source_event=source_event,
            property_id=property_id,
            x=player_pos.x,
            y=player_pos.y,
            witnessed=True,
            note=f"{note_kind}/case_{prompt.get('case_id') or prompt.get('incident_id') or 'unknown'}",
        )

        target = (int(player_pos.x), int(player_pos.y), int(player_pos.z))
        enforcers = self._justice_enforcers_near_player(
            primary_eid=by_eid,
            radius=max(self.DETENTION_RADIUS + 2, 10),
        )
        primary = int(by_eid) if by_eid is not None else (enforcers[0] if enforcers else None)
        for enforcer_eid in enforcers:
            ai = self.sim.ecs.get(AI).get(enforcer_eid)
            will = self.sim.ecs.get(NPCWill).get(enforcer_eid)
            if ai is not None and will is not None:
                _sync_ai_intent(
                    ai,
                    will,
                    self.sim.tick,
                    "investigating",
                    score=86.0,
                    target=target,
                    target_eid=self.player_eid,
                )
                ai.response_role = "justice_detention"
                continue
            if ai is not None:
                ai.state = "investigating"
                ai.target = target
                ai.target_eid = self.player_eid
                ai.response_role = "justice_detention"
            if will is not None:
                will.intent = "investigating"
                will.score = 86.0
                will.target = target
                will.target_eid = self.player_eid
                will.last_tick = self.sim.tick

        self.sim.emit(Event(
            event_type,
            eid=self.player_eid,
            officer_eid=primary,
            incident_id=prompt.get("incident_id"),
            case_id=prompt.get("case_id"),
            x=target[0],
            y=target[1],
            z=target[2],
            custody_pressure=bool(enforcers),
        ))
        if primary is not None:
            self.sim.emit(Event(
                "npc_defend_property",
                npc_eid=primary,
                offender_eid=self.player_eid,
                property_id=property_id,
                owner_eid=None,
                defender_reason="law",
                threat_type=threat_type,
                severity_label=incident_type,
                ingress_kind=ingress_kind,
                aperture_kind="",
                ingress_method=ingress_kind,
            ))
        return change

    def _escalate_player_identity_refusal(self, *, by_eid=None, prompt=None):
        return self._escalate_player_identity_offense(
            by_eid=by_eid,
            prompt=prompt,
            incident_type="failure_to_identify",
            severity=self.IDENTITY_REFUSAL_SEVERITY,
            source_event="justice_identity_check_choice",
            note_kind="formal_identity_demand",
            event_type="justice_identity_refusal_recorded",
            threat_type="justice_identity_refusal",
            ingress_kind="identity_refusal",
        )

    def _escalate_player_identity_deception(self, *, by_eid=None, prompt=None):
        return self._escalate_player_identity_offense(
            by_eid=by_eid,
            prompt=prompt,
            incident_type="obstruction",
            severity=self.IDENTITY_DECEPTION_SEVERITY,
            source_event="justice_identity_check_deception",
            note_kind="false_identity_check_statement",
            event_type="justice_identity_deception_detected",
            threat_type="justice_identity_deception",
            ingress_kind="identity_deception",
        )

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
                        membership["primary"] = False
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
        provisional_cases = {}
        for incident in _justice_provisional_incident_rows(self.sim, offender_eid, active_only=True):
            case_id = str(incident.get("source_case_id", "") or "").strip()
            incident_id = incident.get("source_incident_id")
            case = justice_case_for_incident(self.sim, incident_id)
            attribution = self._active_case_attribution_for(case, offender_eid)
            if not case_id or not isinstance(attribution, dict):
                continue
            adjusted = self._snapshot_without_provisional_attribution(snapshot, attribution)
            total_release = int(self._booking_release_score(snapshot))
            unrelated_release = int(self._booking_release_score(adjusted))
            provisional_cases[case_id] = {
                "incident_id": incident_id,
                "wrongful_fine_due": int(self._provisional_npc_fine_share(snapshot, attribution)),
                "residual_active_contribution": max(0, total_release - unrelated_release),
            }
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
            "restitution_due": int(snapshot.get("restitution_due", 0) or 0),
            "restitution_property_count": int(snapshot.get("restitution_property_count", 0) or 0),
            "fine_paid": 0,
            "wallet_credits_before": int(wallet_before),
            "wallet_credits_after": int(wallet_before),
            "inventory_items": inventory_items,
            "provisional_cases": provisional_cases,
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
        for eid in self.sim.entity_ids_in_radius(
            player_pos.x,
            player_pos.y,
            player_pos.z,
            radius,
        ):
            pos = positions.get(eid)
            if pos is None:
                continue
            if eid == self.player_eid or pos.z != player_pos.z:
                continue
            dist = _manhattan(pos.x, pos.y, player_pos.x, player_pos.y)
            if dist <= 0 or dist > radius:
                continue
            enforcer, law_drive, priority = self._actor_is_enforcer(eid)
            if not enforcer:
                continue
            if self._justice_response_interrupted(eid, response_role="justice_detention"):
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

    def _player_confiscation_manifest(self, *, remove=False, inspection=None, keep_contraband=False):
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
                "incident_evidence_units": 0,
                "weapon_units": 0,
                "ignored_units": 0,
                "held_entries": (),
                "forfeited_entries": (),
                "labels": (),
                "held_labels": (),
                "forfeited_labels": (),
                "ignored_labels": (),
                "held_reason_labels": (),
                "forfeited_reason_labels": (),
                "ignored_reason_labels": (),
                "evidence_worn_clothing_removed": False,
                "evidence_worn_clothing_labels": (),
            }

        confiscated_units = 0
        held_units = 0
        forfeited_units = 0
        illegal_units = 0
        restricted_units = 0
        contraband_units = 0
        stolen_units = 0
        incident_evidence_units = 0
        weapon_units = 0
        ignored_units = 0
        labels = []
        held_labels = []
        forfeited_labels = []
        ignored_labels = []
        held_reason_labels = []
        forfeited_reason_labels = []
        ignored_reason_labels = []
        held_entries = []
        forfeited_entries = []
        evidence_worn_clothing_labels = []
        inspection = inspection if isinstance(inspection, dict) else (
            self._inspect_actor_inventory(self.player_eid, update_inventory=True) if remove else {}
        )
        bucket_by_instance = {}
        for bucket_name in ("contraband", "latent_claim_violation", "reported_stolen", "incident_evidence", "lawful"):
            for row in tuple(inspection.get(bucket_name, ()) or ()):
                instance_id = str(row.get("instance_id", "") or "").strip()
                if instance_id:
                    bucket_by_instance[instance_id] = bucket_name
        for entry in list(getattr(inventory, "items", ()) or ()):
            hold_policy = self._justice_item_hold_policy(entry)
            bucket_name = bucket_by_instance.get(str(entry.get("instance_id", "") or "").strip(), "")
            quantity = max(1, int(entry.get("quantity", 1) or 1))
            item_id = str(entry.get("item_id", "") or "").strip().lower()
            metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
            item_name = item_display_name(item_id, metadata=metadata, item_catalog=ITEM_CATALOG)
            was_worn_evidence_clothing = self._entry_is_worn_evidence_clothing(entry, hold_policy)
            if bucket_name == "latent_claim_violation" and not hold_policy.get("objective_protected"):
                ignored_units += quantity
                ignored_labels.append(item_name)
                ignored_reason_labels.extend(tuple(hold_policy.get("reason_labels", ()) or ()))
                continue
            if keep_contraband and bucket_name == "contraband" and not hold_policy.get("stolen") and not hold_policy.get("incident_evidence"):
                ignored_units += quantity
                ignored_labels.append(item_name)
                ignored_reason_labels.append("released under local questioning policy")
                continue
            if not bool(hold_policy.get("seized")):
                ignored_units += quantity
                ignored_labels.append(item_name)
                ignored_reason_labels.extend(tuple(hold_policy.get("reason_labels", ()) or ()))
                continue

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
                held_reason_labels.extend(tuple(hold_policy.get("reason_labels", ()) or ()))
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
                forfeited_reason_labels.extend(tuple(hold_policy.get("reason_labels", ()) or ()))
            if bool(hold_policy.get("illegal")):
                illegal_units += removed_qty
            if bool(hold_policy.get("restricted")):
                restricted_units += removed_qty
            if bool(hold_policy.get("contraband")):
                contraband_units += removed_qty
            if bool(hold_policy.get("stolen")):
                stolen_units += removed_qty
            if bool(hold_policy.get("incident_evidence")):
                incident_evidence_units += removed_qty
            if bool(hold_policy.get("weapon")):
                weapon_units += removed_qty
            labels.append(item_name)
            if remove:
                if was_worn_evidence_clothing:
                    evidence_worn_clothing_labels.append(item_name)
                self._emit_removed_gear_events(self.player_eid, removed, reason="confiscated")

        deduped_labels = tuple(dict.fromkeys(label for label in labels if str(label).strip()))
        deduped_held_labels = tuple(dict.fromkeys(label for label in held_labels if str(label).strip()))
        deduped_forfeited_labels = tuple(dict.fromkeys(label for label in forfeited_labels if str(label).strip()))
        deduped_ignored_labels = tuple(dict.fromkeys(label for label in ignored_labels if str(label).strip()))
        deduped_held_reasons = tuple(dict.fromkeys(label for label in held_reason_labels if str(label).strip()))
        deduped_forfeited_reasons = tuple(dict.fromkeys(label for label in forfeited_reason_labels if str(label).strip()))
        deduped_ignored_reasons = tuple(dict.fromkeys(label for label in ignored_reason_labels if str(label).strip()))
        deduped_evidence_worn_clothing = tuple(dict.fromkeys(label for label in evidence_worn_clothing_labels if str(label).strip()))
        return {
            "confiscated_units": confiscated_units,
            "held_units": held_units,
            "forfeited_units": forfeited_units,
            "illegal_units": illegal_units,
            "restricted_units": restricted_units,
            "contraband_units": contraband_units,
            "stolen_units": stolen_units,
            "incident_evidence_units": incident_evidence_units,
            "weapon_units": weapon_units,
            "ignored_units": ignored_units,
            "held_entries": tuple(held_entries),
            "forfeited_entries": tuple(forfeited_entries),
            "labels": deduped_labels[:4],
            "held_labels": deduped_held_labels[:4],
            "forfeited_labels": deduped_forfeited_labels[:4],
            "ignored_labels": deduped_ignored_labels[:4],
            "held_reason_labels": deduped_held_reasons[:4],
            "forfeited_reason_labels": deduped_forfeited_reasons[:4],
            "ignored_reason_labels": deduped_ignored_reasons[:4],
            "evidence_worn_clothing_removed": bool(deduped_evidence_worn_clothing),
            "evidence_worn_clothing_labels": deduped_evidence_worn_clothing[:4],
        }

    def _entry_is_worn_evidence_clothing(self, entry, hold_policy):
        if not isinstance(entry, dict) or not isinstance(hold_policy, dict):
            return False
        if not bool(hold_policy.get("incident_evidence")):
            return False
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        if not bool(metadata.get(APPEARANCE_WORN_METADATA_KEY)):
            return False
        item_id = str(entry.get("item_id", "") or "").strip().lower()
        item_def = ITEM_CATALOG.get(item_id, {})
        tags = {
            str(tag).strip().lower()
            for tag in tuple(item_def.get("tags", ()) or ())
            if str(tag).strip()
        }
        if "clothing" not in tags and "cosmetic" not in tags:
            return False
        nested = metadata.get(APPEARANCE_METADATA_KEY) if isinstance(metadata.get(APPEARANCE_METADATA_KEY), dict) else {}
        slots = metadata.get("appearance_slots") or nested.get("slots") or item_def.get("appearance_slots") or ()
        slots = {
            str(slot).strip().lower()
            for slot in tuple(slots or ())
            if str(slot).strip()
        }
        worn_slot = str(metadata.get(APPEARANCE_SLOT_METADATA_KEY, "") or "").strip().lower()
        if worn_slot:
            slots.add(worn_slot)
        return bool(slots.intersection({"full_body", "top", "bottom"}))

    def _justice_release_jumpsuit_metadata(self, *, booking_prop=None):
        metadata = cosmetic_variant_metadata(
            self.JUSTICE_RELEASE_JUMPSUIT_ITEM_ID,
            seed_token=f"booking-release:{getattr(self.sim, 'seed', 0)}:{getattr(self.sim, 'tick', 0)}:{self.player_eid}",
            item_catalog=ITEM_CATALOG,
            sim=self.sim,
        )
        metadata = dict(metadata or {})
        accent = COSMETIC_COLOR_KEYS.get("safety_orange", "clothing_orange")
        nested = dict(metadata.get(APPEARANCE_METADATA_KEY) or {})
        nested.update({
            "type": self.JUSTICE_RELEASE_JUMPSUIT_ITEM_ID,
            "label": "jumpsuit",
            "slots": [self.JUSTICE_RELEASE_JUMPSUIT_SLOT],
            "color": "safety_orange",
            "color_word": "safety_orange",
            "material": "cotton",
            "style": "issued",
            "accent_color": accent,
            "worn_slot": self.JUSTICE_RELEASE_JUMPSUIT_SLOT,
        })
        metadata.update({
            "appearance_type": self.JUSTICE_RELEASE_JUMPSUIT_ITEM_ID,
            "appearance_label": "jumpsuit",
            "appearance_slots": [self.JUSTICE_RELEASE_JUMPSUIT_SLOT],
            "color": "safety_orange",
            "color_word": "safety_orange",
            "material": "cotton",
            "style": "issued",
            "accent_color": accent,
            "display_name": "Issued Orange Jumpsuit",
            APPEARANCE_METADATA_KEY: nested,
            APPEARANCE_WORN_METADATA_KEY: True,
            APPEARANCE_SLOT_METADATA_KEY: self.JUSTICE_RELEASE_JUMPSUIT_SLOT,
            "justice_issued": True,
            "justice_issue_reason": "evidence_clothing_release",
            "justice_booking_tick": int(getattr(self.sim, "tick", 0) or 0),
        })
        if isinstance(booking_prop, dict):
            metadata["justice_booking_property_id"] = booking_prop.get("id")
            metadata["justice_booking_property_name"] = booking_prop.get("name")
        return metadata

    def _force_clear_player_jumpsuit_conflicts(self):
        loadout = appearance_loadout_for(self.sim, self.player_eid, create=True)
        if loadout is None:
            return
        for slot in ("full_body", "top", "bottom"):
            instance_id = str(loadout.slots.get(slot) or "").strip()
            if instance_id:
                mark_inventory_instance_worn(self.sim, self.player_eid, instance_id, worn=False)
            loadout.slots[slot] = None

    def _issue_booking_jumpsuit_if_needed(self, confiscation, *, booking_prop=None):
        if not isinstance(confiscation, dict):
            return {}
        if not bool(confiscation.get("evidence_worn_clothing_removed")):
            return {}
        inventory = self.sim.ecs.get(Inventory).get(self.player_eid)
        item_def = ITEM_CATALOG.get(self.JUSTICE_RELEASE_JUMPSUIT_ITEM_ID, {})
        if inventory is None or not item_def:
            return {
                "issued": False,
                "reason": "missing_inventory_or_item",
            }
        self._force_clear_player_jumpsuit_conflicts()
        metadata = self._justice_release_jumpsuit_metadata(booking_prop=booking_prop)
        added, instance_id = inventory.add_item(
            item_id=self.JUSTICE_RELEASE_JUMPSUIT_ITEM_ID,
            quantity=1,
            stack_max=item_def.get("stack_max", 1),
            instance_factory=self.sim.new_item_instance_id,
            owner_eid=self.player_eid,
            owner_tag="player",
            metadata=metadata,
        )
        if not added or not instance_id:
            return {
                "issued": False,
                "reason": "inventory_full",
            }
        loadout = appearance_loadout_for(self.sim, self.player_eid, create=True)
        if loadout is not None:
            loadout.slots[self.JUSTICE_RELEASE_JUMPSUIT_SLOT] = str(instance_id)
        item_name = item_display_name(
            self.JUSTICE_RELEASE_JUMPSUIT_ITEM_ID,
            metadata=metadata,
            item_catalog=ITEM_CATALOG,
        )
        self.sim.emit(Event(
            "appearance_item_equipped",
            eid=self.player_eid,
            item_id=self.JUSTICE_RELEASE_JUMPSUIT_ITEM_ID,
            instance_id=str(instance_id),
            item_name=item_name,
            slot=self.JUSTICE_RELEASE_JUMPSUIT_SLOT,
            reason="justice_booking_release",
        ))
        return {
            "issued": True,
            "item_id": self.JUSTICE_RELEASE_JUMPSUIT_ITEM_ID,
            "instance_id": str(instance_id),
            "item_name": item_name,
            "reason": "evidence_clothing_removed",
        }

    def _confiscate_player_inventory(self, *, booking_prop=None, inspection=None, keep_contraband=False):
        manifest = self._player_confiscation_manifest(remove=True, inspection=inspection, keep_contraband=keep_contraband)
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

    def _booking_result_lines(
        self,
        *,
        booking_prop=None,
        hold_ticks=0,
        fine_due=0,
        fine_result=None,
        penalty_breakdown=None,
        confiscation=None,
        restitution_due=0,
        restitution_property_count=0,
        evidence_surcharge=0,
    ):
        booking_name = str((booking_prop or {}).get("name", "Justice Office") if isinstance(booking_prop, dict) else "Justice Office").strip() or "Justice Office"
        fine_result = fine_result if isinstance(fine_result, dict) else {}
        penalty_breakdown = penalty_breakdown if isinstance(penalty_breakdown, dict) else {}
        confiscation = confiscation if isinstance(confiscation, dict) else {}
        hold_hours = round(float(hold_ticks) / float(self._ticks_per_hour()), 2) if int(hold_ticks or 0) > 0 else 0.0
        lines = [f"Processed at {booking_name}."]
        if hold_hours > 0:
            lines.append(f"Custody time served: about {hold_hours:g}h.")
        force_line = self._force_context_line(self.player_eid)
        if force_line:
            lines.append(force_line)

        fine_due = int(max(0, fine_due or 0))
        if fine_due > 0:
            penalty_parts = []
            base_fine = int(penalty_breakdown.get("base_fine", 0) or 0)
            if base_fine > 0:
                penalty_parts.append(f"{base_fine}c base fine")
            restitution_due = int(max(0, restitution_due or 0))
            if restitution_due > 0:
                penalty_parts.append(f"{restitution_due}c restitution")
            homicide_surcharge = int(max(0, penalty_breakdown.get("homicide_surcharge", 0) or 0))
            homicide_count = int(max(0, penalty_breakdown.get("homicide_count", 0) or 0))
            if homicide_surcharge > 0:
                count_text = f" for {homicide_count} homicide record(s)" if homicide_count > 0 else ""
                penalty_parts.append(f"{homicide_surcharge}c homicide penalty{count_text}")
            evidence_surcharge = int(max(0, evidence_surcharge or 0))
            if evidence_surcharge > 0:
                penalty_parts.append(f"{evidence_surcharge}c evidence surcharge")
            lines.append(f"Penalty assessed: {fine_due}c" + (f" ({', '.join(penalty_parts)})." if penalty_parts else "."))
            payment_text = self._payment_result_text(fine_result)
            if payment_text:
                lines.append(payment_text[0].upper() + payment_text[1:] + ".")
            debt_after = int(fine_result.get("debt_balance_after", 0) or 0)
            if debt_after > 0:
                lines.append(f"Current justice debt: {debt_after}c.")

        restitution_due = int(max(0, restitution_due or 0))
        if restitution_due > 0:
            site_word = "site" if int(restitution_property_count or 0) == 1 else "sites"
            lines.append(f"Restitution is based on exact recorded repair cost across {int(restitution_property_count or 0)} damaged {site_word}.")

        held_count = int(confiscation.get("held_units", 0) or 0)
        forfeited_count = int(confiscation.get("forfeited_units", 0) or 0)
        ignored_count = int(confiscation.get("ignored_units", 0) or 0)
        if held_count > 0:
            held_labels = self._label_list_text(confiscation.get("held_labels", ()))
            held_reasons = self._reason_list_text(confiscation.get("held_reason_labels", ()))
            line = f"Held for release at {booking_name}: {held_count} item(s)"
            if held_labels:
                line += f" ({held_labels})"
            if held_reasons:
                line += f" because {held_reasons}"
            lines.append(line + ".")
        if forfeited_count > 0:
            forfeited_labels = self._label_list_text(confiscation.get("forfeited_labels", ()))
            forfeited_reasons = self._reason_list_text(confiscation.get("forfeited_reason_labels", ()))
            line = f"Forfeited/confiscated: {forfeited_count} item(s)"
            if forfeited_labels:
                line += f" ({forfeited_labels})"
            if forfeited_reasons:
                line += f" because {forfeited_reasons}"
            lines.append(line + ".")
        if ignored_count > 0:
            ignored_labels = self._label_list_text(confiscation.get("ignored_labels", ()))
            ignored_reasons = self._reason_list_text(confiscation.get("ignored_reason_labels", ()))
            line = f"Left with you after search: {ignored_count} item(s)"
            if ignored_labels:
                line += f" ({ignored_labels})"
            if ignored_reasons:
                line += f" because {ignored_reasons}"
            lines.append(line + ".")
        if bool(confiscation.get("booking_jumpsuit_issued")):
            item_name = str(confiscation.get("booking_jumpsuit_item_name", "") or "").strip() or "orange jumpsuit"
            item_phrase = item_name[:1].lower() + item_name[1:] if item_name else "orange jumpsuit"
            if not item_phrase.lower().startswith(("a ", "an ")):
                item_phrase = f"an {item_phrase}"
            evidence_labels = self._label_list_text(confiscation.get("evidence_worn_clothing_labels", ()))
            line = f"Discharged in {item_phrase}"
            if evidence_labels:
                line += f" after evidence clothing was held ({evidence_labels})"
            lines.append(line + ".")
        if held_count <= 0 and forfeited_count <= 0:
            lines.append("No property was held or forfeited.")

        if held_count > 0:
            debt_after = int(fine_result.get("debt_balance_after", 0) or 0)
            if debt_after > 0:
                lines.append(f"Settle {debt_after}c justice debt before reclaiming held property at {booking_name}.")
            else:
                lines.append(f"Return to {booking_name} to reclaim held property.")
        return lines

    def _book_player(
        self,
        *,
        by_eid=None,
        source_prop=None,
        inspection=None,
        questioning_disposition="",
        provisional_case=None,
        provisional_attribution=None,
    ):
        snapshot = self._player_bookable_snapshot()
        player_pos = self._position_for(self.player_eid)
        if snapshot is None or player_pos is None:
            return False
        initial_snapshot = dict(snapshot)
        inspection = inspection if isinstance(inspection, dict) else self._inspect_actor_inventory(
            self.player_eid,
            update_inventory=True,
            inspector_eid=by_eid,
        )
        adjudication = self._booking_provisional_adjudication(
            provisional_case,
            provisional_attribution,
            inspection,
        )
        penalty_snapshot = (
            _justice_snapshot(self.sim, self.player_eid)
            if bool(adjudication.get("exonerated", False))
            else snapshot
        )
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

        counts = inspection.get("counts", {}) if isinstance(inspection, dict) else {}
        match_labels = self._inspection_match_labels(inspection)
        match_reasons = self._inspection_match_reasons(inspection)
        stolen_intent_labels = tuple(inspection.get("stolen_intent_labels", ()) or ()) if isinstance(inspection, dict) else ()
        stolen_intent_counts = dict(inspection.get("stolen_intent_counts", {}) or {}) if isinstance(inspection, dict) else {}
        force_context = self._force_event_payload(self.player_eid)
        evidence_surcharge = int(self._inspection_evidence_surcharge(inspection))
        homicide_surcharge = int(self._player_homicide_surcharge(penalty_snapshot))
        homicide_count = int(max(0, penalty_snapshot.get("homicide_count", 0) or 0))
        protective = (
            local_protective_pressure_snapshot(
                self.sim,
                source_prop,
                current_tick=int(getattr(self.sim, "tick", 0)),
            )
            if isinstance(source_prop, dict)
            else {}
        )
        confiscation = self._confiscate_player_inventory(booking_prop=booking_prop, inspection=inspection)
        jumpsuit_issue = self._issue_booking_jumpsuit_if_needed(confiscation, booking_prop=booking_prop)
        if bool(jumpsuit_issue.get("issued")):
            confiscation["booking_jumpsuit_issued"] = True
            confiscation["booking_jumpsuit_item_id"] = jumpsuit_issue.get("item_id")
            confiscation["booking_jumpsuit_instance_id"] = jumpsuit_issue.get("instance_id")
            confiscation["booking_jumpsuit_item_name"] = jumpsuit_issue.get("item_name")
        elif jumpsuit_issue:
            confiscation["booking_jumpsuit_issue_failed"] = True
            confiscation["booking_jumpsuit_issue_reason"] = jumpsuit_issue.get("reason")
        fine_due = (
            int(self._player_fine_amount(penalty_snapshot)) + int(evidence_surcharge)
            if int(penalty_snapshot.get("active_score", 0) or 0) >= 6
            else 0
        )
        restitution_due = int(penalty_snapshot.get("restitution_due", 0) or 0)
        restitution_property_count = int(penalty_snapshot.get("restitution_property_count", 0) or 0)
        fine_result = self._collect_player_fine(fine_due)
        penalty_breakdown = self._player_penalty_breakdown(
            penalty_snapshot,
            fine_due=fine_due,
            fine_result=fine_result,
            evidence_surcharge=evidence_surcharge,
            multiplier=1.0,
            disposition="booking",
        )
        hold_hours = (
            float(self.EXONERATED_BOOKING_REVIEW_HOURS)
            if bool(adjudication.get("exonerated", False))
            else float(self.BOOKING_HOURS_BY_TIER.get(starting_tier, 1.0))
        )
        hold_ticks = self._advance_time_for_booking(
            self._hours_to_ticks(hold_hours),
            property_id=(booking_prop or {}).get("id") if isinstance(booking_prop, dict) else None,
            property_name=(booking_prop or {}).get("name", "Justice Office") if isinstance(booking_prop, dict) else "Justice Office",
            held_by_eid=by_eid,
        )
        release_change = _release_justice_from_custody(
            self.sim,
            self.player_eid,
            new_score=self._booking_release_score(penalty_snapshot),
            x=booking_x,
            y=booking_y,
        )
        if isinstance(booking_prop, dict):
            self._grant_player_release_grace(booking_prop, reason="booking_release")
        _record_justice_booking_completion(
            self.sim,
            self.player_eid,
            property_id=(booking_prop or {}).get("id") if isinstance(booking_prop, dict) else None,
            property_name=(booking_prop or {}).get("name") if isinstance(booking_prop, dict) else None,
            hold_ticks=int(hold_ticks),
            fine_due=int(fine_due),
            fine_paid=int(fine_result.get("fine_paid", 0) or 0),
            debt_added=int(fine_result.get("debt_added", 0) or 0),
            evidence_surcharge=int(evidence_surcharge),
            seized_entries=tuple(confiscation.get("held_entries", ()) or ()) + tuple(confiscation.get("forfeited_entries", ()) or ()),
        )
        self._record_player_provisional_booking_outcome(
            provisional_case,
            provisional_attribution,
            snapshot=initial_snapshot,
            hold_ticks=hold_ticks,
            fine_due=fine_due,
            fine_result=fine_result,
            release_change=release_change,
        )
        self._clear_restitution_claims(self.player_eid)
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
            before_score=int(initial_snapshot.get("active_score", 0) or 0),
            after_score=int((release_change or {}).get("after_score", 0) or 0),
            fine_due=int(fine_due),
            restitution_due=int(restitution_due),
            restitution_property_count=int(restitution_property_count),
            homicide_count=int(homicide_count),
            homicide_surcharge=int(homicide_surcharge),
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
            incident_evidence_item_count=int(confiscation.get("incident_evidence_units", 0) or 0),
            weapon_item_count=int(confiscation.get("weapon_units", 0) or 0),
            confiscated_labels=tuple(confiscation.get("labels", ()) or ()),
            held_labels=tuple(confiscation.get("held_labels", ()) or ()),
            forfeited_labels=tuple(confiscation.get("forfeited_labels", ()) or ()),
            inspected_contraband_count=int(counts.get("contraband", 0) or 0),
            inspected_latent_claim_count=int(counts.get("latent_claim_violation", 0) or 0),
            inspected_reported_stolen_count=int(counts.get("reported_stolen", 0) or 0),
            inspected_incident_evidence_count=int(counts.get("incident_evidence", 0) or 0),
            adjudication_status=str(adjudication.get("status", "ordinary_booking") or "ordinary_booking"),
            adjudication_strength=float(adjudication.get("strength", 0.0) or 0.0),
            adjudication_reasons=tuple(adjudication.get("reasons", ()) or ()),
            booking_exonerated=bool(adjudication.get("exonerated", False)),
            canonical_identity_resolved=False if bool(adjudication.get("applicable", False)) else None,
            questioning_disposition=str(questioning_disposition or "").strip().lower(),
            incident_match_labels=match_labels,
            incident_match_reasons=match_reasons,
            stolen_intent_labels=stolen_intent_labels,
            stolen_intent_counts=stolen_intent_counts,
            **force_context,
            evidence_surcharge=int(evidence_surcharge),
            penalty_breakdown=penalty_breakdown,
            protective_posture_label=str((protective or {}).get("state_label", "") or "").strip(),
            held_property_id=(booking_prop or {}).get("id") if isinstance(booking_prop, dict) else None,
            held_property_name=str((booking_prop or {}).get("name", "Justice Office") if isinstance(booking_prop, dict) else "Justice Office").strip() or "Justice Office",
            held_entries=tuple(confiscation.get("held_entries", ()) or ()),
            forfeited_entries=tuple(confiscation.get("forfeited_entries", ()) or ()),
            seized_entries=tuple(confiscation.get("held_entries", ()) or ()) + tuple(confiscation.get("forfeited_entries", ()) or ()),
            held_reason_labels=tuple(confiscation.get("held_reason_labels", ()) or ()),
            forfeited_reason_labels=tuple(confiscation.get("forfeited_reason_labels", ()) or ()),
            evidence_worn_clothing_labels=tuple(confiscation.get("evidence_worn_clothing_labels", ()) or ()),
            booking_jumpsuit_issued=bool(confiscation.get("booking_jumpsuit_issued")),
            booking_jumpsuit_item_id=str(confiscation.get("booking_jumpsuit_item_id", "") or ""),
            booking_jumpsuit_item_name=str(confiscation.get("booking_jumpsuit_item_name", "") or ""),
            ignored_item_count=int(confiscation.get("ignored_units", 0) or 0),
            ignored_labels=tuple(confiscation.get("ignored_labels", ()) or ()),
            ignored_reason_labels=tuple(confiscation.get("ignored_reason_labels", ()) or ()),
            booking_anchor_x=int(anchor_x),
            booking_anchor_y=int(anchor_y),
            booking_anchor_fallback=bool((anchor or {}).get("fallback", False)),
            booking_anchor_jurisdiction_key=str((anchor or {}).get("jurisdiction_key", "") or "").strip().lower(),
            booking_anchor_jurisdiction_name=str((anchor or {}).get("jurisdiction_name", "Justice Office") or "Justice Office").strip() or "Justice Office",
            x=booking_x,
            y=booking_y,
            z=booking_z,
        ))
        result_lines = self._booking_result_lines(
            booking_prop=booking_prop,
            hold_ticks=hold_ticks,
            fine_due=fine_due,
            fine_result=fine_result,
            penalty_breakdown=penalty_breakdown,
            confiscation=confiscation,
            restitution_due=restitution_due,
            restitution_property_count=restitution_property_count,
            evidence_surcharge=evidence_surcharge,
        )
        if bool(adjudication.get("exonerated", False)):
            result_lines.insert(1, "Booking review did not support the reported charge. You are released from that allegation.")
        elif bool(adjudication.get("applicable", False)):
            result_lines.insert(1, "Witness statements and available evidence support a conviction on the reported charge.")
        self._present_justice_result(
            "Released After Booking Review" if bool(adjudication.get("exonerated", False)) else "Booking Complete",
            result_lines,
            property_id=(booking_prop or {}).get("id") if isinstance(booking_prop, dict) else None,
            subtitle=str((booking_prop or {}).get("name", "Justice Office") if isinstance(booking_prop, dict) else "Justice Office").strip() or "Justice Office",
        )
        return True

    def _justice_response_interrupted(self, enforcer_eid, *, response_role):
        ai = self.sim.ecs.get(AI).get(enforcer_eid)
        if ai is None or _entity_is_downed(self.sim, enforcer_eid):
            return True
        current_role = str(getattr(ai, "response_role", "") or "").strip().lower()
        if current_role and current_role != str(response_role or "").strip().lower():
            return True
        if _actor_in_live_combat(self.sim, enforcer_eid):
            return True
        state = str(getattr(ai, "state", "idle") or "idle").strip().lower()
        return state in {
            "protecting",
            "chasing",
            "reporting_incident",
            "helping_victim",
            "seeking_safety",
            "holding",
            "following",
            "warning",
            "ejecting_target",
            "leaving_property",
            "surrendered",
        }

    def _queue_scene_apprehension(self, offender_eid, enforcer_eids, offense):
        try:
            offender_eid = int(offender_eid)
        except (TypeError, ValueError):
            return False
        responders = []
        for raw_eid in tuple(enforcer_eids or ()):
            try:
                responder_eid = int(raw_eid)
            except (TypeError, ValueError):
                continue
            if responder_eid != offender_eid and responder_eid not in responders:
                responders.append(responder_eid)
        if not responders or not isinstance(offense, dict):
            return False

        records = self._scene_apprehension_records()
        key = str(offender_eid)
        tick = int(getattr(self.sim, "tick", 0))
        record = records.get(key)
        if not isinstance(record, dict):
            record = {
                "offender_eid": offender_eid,
                "responder_eids": [],
                "offenses": [],
                "started_tick": tick,
            }
            records[key] = record
        known_responders = list(record.get("responder_eids", ()) or ())
        for responder_eid in responders:
            if responder_eid not in known_responders:
                known_responders.append(responder_eid)
        record["responder_eids"] = known_responders[:6]
        record["expires_at"] = tick + int(self.SCENE_APPREHENSION_WINDOW)

        incident_id = offense.get("knowledge_incident_id")
        signature = (
            str(offense.get("source_event", "") or "").strip().lower(),
            str(offense.get("incident_type", "") or "").strip().lower(),
            str(offense.get("property_id", "") or "").strip(),
            int(incident_id or 0),
        )
        offenses = list(record.get("offenses", ()) or ())
        existing_signatures = {
            (
                str(row.get("source_event", "") or "").strip().lower(),
                str(row.get("incident_type", "") or "").strip().lower(),
                str(row.get("property_id", "") or "").strip(),
                int(row.get("knowledge_incident_id", 0) or 0),
            )
            for row in offenses
            if isinstance(row, dict)
        }
        added = signature not in existing_signatures
        if added:
            offenses.append(dict(offense))
            record["offenses"] = offenses[-8:]
            self.sim.emit(Event(
                "justice_scene_apprehension_authorized",
                offender_eid=offender_eid,
                officer_eids=tuple(responders),
                incident_id=incident_id,
                incident_type=signature[1],
                identity_resolved=False,
                x=offense.get("x"),
                y=offense.get("y"),
                z=offense.get("z", 0),
            ))
        return True

    def _clear_scene_apprehension(self, offender_eid, *, reason="ended"):
        record = self._scene_apprehension_records().pop(str(int(offender_eid)), None)
        if not isinstance(record, dict):
            return False
        for raw_eid in tuple(record.get("responder_eids", ()) or ()):
            try:
                responder_eid = int(raw_eid)
            except (TypeError, ValueError):
                continue
            ai = self.sim.ecs.get(AI).get(responder_eid)
            will = self.sim.ecs.get(NPCWill).get(responder_eid)
            if ai is None or str(getattr(ai, "response_role", "") or "").strip().lower() != "justice_scene_apprehension":
                continue
            context = getattr(ai, "investigation_context", None)
            if is_purposeful_observation(context, purpose="justice_detention"):
                ai.investigation_context = finish_purposeful_observation(
                    context,
                    current_tick=self.sim.tick,
                    reason=reason,
                )
            ai.response_role = None
            ai.incident_id = None
            if str(getattr(ai, "state", "idle") or "idle").strip().lower() in {"idle", "investigating"}:
                _sync_ai_intent(ai, will, self.sim.tick, "idle", score=0.0, target=None, target_eid=None)
        self.sim.emit(Event(
            "justice_scene_apprehension_ended",
            offender_eid=int(offender_eid),
            reason=str(reason or "ended").strip().lower(),
        ))
        return True

    def _record_scene_apprehension_offenses(self, record):
        offender_eid = int(record.get("offender_eid"))
        latest_change = None
        for offense in tuple(record.get("offenses", ()) or ()):
            if not isinstance(offense, dict):
                continue
            incident_id = offense.get("knowledge_incident_id")
            source_incident = incident_record(self.sim, incident_id)
            if isinstance(source_incident, dict) and bool(source_incident.get("justice_accounted", False)):
                continue
            change = self._record_incident(
                offender_eid,
                incident_type=offense.get("incident_type"),
                severity=int(offense.get("severity", 0) or 0),
                source_event=offense.get("source_event"),
                property_id=offense.get("property_id"),
                x=offense.get("x"),
                y=offense.get("y"),
                witnessed=True,
                note=offense.get("note", ""),
            )
            if change is None:
                continue
            latest_change = change
            self._mark_incident_accounted(incident_id)
            if bool(offense.get("structural_restitution", False)):
                prop = self.sim.properties.get(str(offense.get("property_id", "") or ""))
                if isinstance(prop, dict):
                    self._record_structural_restitution_claim(
                        offender_eid,
                        prop,
                        damage_tick=int(getattr(self.sim, "tick", 0)),
                    )
            force_read = offense.get("force_read") if isinstance(offense.get("force_read"), dict) else None
            if force_read is not None:
                force_data = dict(offense.get("force_data") or {}) if isinstance(offense.get("force_data"), dict) else {}
                force_data.setdefault("severity", offense.get("severity", 0))
                self._record_bounty_misuse_review(
                    offender_eid,
                    force_read,
                    data=force_data,
                    factual_offender_eid=offender_eid,
                )
        return latest_change

    def _scene_apprehension_responder(self, record):
        for raw_eid in tuple(record.get("responder_eids", ()) or ()):
            try:
                responder_eid = int(raw_eid)
            except (TypeError, ValueError):
                continue
            if self._position_for(responder_eid) is None or _entity_is_downed(self.sim, responder_eid):
                continue
            return responder_eid
        return None

    def _scene_apprehension_response_interrupted(self, responder_eid):
        ai = self.sim.ecs.get(AI).get(responder_eid)
        if ai is None or _entity_is_downed(self.sim, responder_eid):
            return True
        if _actor_in_live_combat(self.sim, responder_eid):
            return True
        response_role = str(getattr(ai, "response_role", "") or "").strip().lower()
        if response_role not in {
            "",
            "justice_scene_apprehension",
            "reporting_incident",
            "helping_victim",
            "seeking_safety",
            "warning",
        }:
            return True
        state = str(getattr(ai, "state", "idle") or "idle").strip().lower()
        return state in {
            "protecting",
            "chasing",
            "holding",
            "following",
            "ejecting_target",
            "leaving_property",
            "surrendered",
        }

    def _advance_scene_apprehension(self, offender_eid, record):
        tick = int(getattr(self.sim, "tick", 0))
        if tick > int(record.get("expires_at", tick) or tick):
            self._clear_scene_apprehension(offender_eid, reason="scene_window_expired")
            return False
        offender_pos = self._position_for(offender_eid)
        if offender_pos is None:
            self._clear_scene_apprehension(offender_eid, reason="target_unavailable")
            return False
        snapshot = _justice_snapshot(self.sim, offender_eid)
        if bool(snapshot.get("in_custody", False)):
            self._clear_scene_apprehension(offender_eid, reason="already_in_custody")
            return False

        responder_eid = self._scene_apprehension_responder(record)
        if responder_eid is None:
            self._clear_scene_apprehension(offender_eid, reason="no_firsthand_officer")
            return False
        if self._scene_apprehension_response_interrupted(responder_eid):
            return True
        ai = self.sim.ecs.get(AI).get(responder_eid)
        will = self.sim.ecs.get(NPCWill).get(responder_eid)
        if ai is None or will is None:
            self._clear_scene_apprehension(offender_eid, reason="invalid_responder")
            return False

        context, contact, target = self._purposeful_actor_approach(
            responder_eid,
            offender_eid,
            purpose="justice_detention",
            existing=getattr(ai, "investigation_context", None),
            notice_radius=self.JUSTICE_DETENTION_NOTICE_RADIUS,
            capture_subject_account=True,
        )
        ai.investigation_context = context
        responder_pos = self._position_for(responder_eid)
        at_contact = bool(
            contact == "visible"
            and responder_pos is not None
            and _manhattan(responder_pos.x, responder_pos.y, offender_pos.x, offender_pos.y)
            <= int(self.JUSTICE_DETENTION_CONTACT_RADIUS)
        )
        if at_contact:
            self._record_scene_apprehension_offenses(record)
            snapshot = _justice_snapshot(self.sim, offender_eid)
            tier = str(snapshot.get("wanted_tier", "clear") or "clear").strip().lower()
            self.sim.emit(Event(
                "justice_scene_suspect_stopped",
                offender_eid=int(offender_eid),
                officer_eid=int(responder_eid),
                wanted_tier=tier,
                identity_resolved=False,
            ))
            if offender_eid == self.player_eid:
                if self._player_surrender_prompt_open() or _actor_in_live_combat(self.sim, self.player_eid):
                    return True
                opened = bool(self._open_player_justice_prompt(responder_eid, snapshot=snapshot, respect_cooldown=False))
                if opened:
                    self._clear_scene_apprehension(offender_eid, reason="scene_contact_prompted")
                return opened
            if tier in {"wanted", "arrest_on_sight"}:
                detained = self._complete_pending_npc_detention(offender_eid, responder_eid, snapshot=snapshot)
                if detained:
                    self._clear_scene_apprehension(offender_eid, reason="scene_contact_detained")
                return detained
            self._clear_scene_apprehension(offender_eid, reason="scene_contact_questioned")
            return True

        if target is None:
            self._clear_scene_apprehension(offender_eid, reason="lost_contact")
            return False
        was_approaching = str(getattr(ai, "response_role", "") or "").strip().lower() == "justice_scene_apprehension"
        _sync_ai_intent(
            ai,
            will,
            self.sim.tick,
            "investigating",
            score=90.0,
            target=target,
            target_eid=None,
        )
        ai.response_role = "justice_scene_apprehension"
        ai.incident_id = next(
            (
                row.get("knowledge_incident_id")
                for row in reversed(tuple(record.get("offenses", ()) or ()))
                if isinstance(row, dict) and row.get("knowledge_incident_id") is not None
            ),
            None,
        )
        if not was_approaching:
            self.sim.emit(Event(
                "justice_scene_apprehension_started",
                npc_eid=int(responder_eid),
                target_eid=int(offender_eid),
                x=target[0],
                y=target[1],
                z=target[2],
            ))
        return True

    def _process_scene_apprehensions(self):
        handled_player = False
        records = self._scene_apprehension_records()
        for raw_eid, record in tuple(records.items()):
            try:
                offender_eid = int(raw_eid)
            except (TypeError, ValueError):
                records.pop(raw_eid, None)
                continue
            if not isinstance(record, dict):
                records.pop(raw_eid, None)
                continue
            handled = self._advance_scene_apprehension(offender_eid, record)
            if offender_eid == self.player_eid:
                handled_player = bool(handled) or handled_player
        return handled_player

    def _find_detaining_enforcer(self, offender_eid, *, radius=None, preferred_eid=None):
        positions = self.sim.ecs.get(Position)
        offender_pos = positions.get(offender_eid)
        if offender_pos is None:
            return None

        radius = max(0, int(self.DETENTION_RADIUS if radius is None else radius))
        best = None
        best_rank = None
        nearby_eids = self.sim.entity_ids_in_radius(
            offender_pos.x,
            offender_pos.y,
            offender_pos.z,
            radius,
        )
        for eid in nearby_eids:
            pos = positions.get(eid)
            if pos is None:
                continue
            if eid == offender_eid or pos.z != offender_pos.z:
                continue
            dist = _manhattan(pos.x, pos.y, offender_pos.x, offender_pos.y)
            if dist > radius:
                continue

            enforcer, law_drive, priority = self._actor_is_enforcer(eid)
            if not enforcer:
                continue
            if self._justice_response_interrupted(eid, response_role="justice_detention"):
                continue
            if not _shared_observer_can_see_position(
                self.sim,
                observer_eid=eid,
                observer_x=pos.x,
                observer_y=pos.y,
                observer_z=pos.z,
                target_x=offender_pos.x,
                target_y=offender_pos.y,
                target_z=offender_pos.z,
                radius=max(4, radius + 2),
            ):
                continue
            rank = (0 if preferred_eid is not None and int(eid) == int(preferred_eid) else 1, dist, -priority, -law_drive, int(eid))
            if best_rank is None or rank < best_rank:
                best = int(eid)
                best_rank = rank
        return best

    def _complete_pending_npc_detention(self, offender_eid, held_by_eid, *, snapshot=None):
        pos = self._position_for(offender_eid)
        if pos is None or held_by_eid is None:
            return False
        snapshot = snapshot if isinstance(snapshot, dict) else _justice_snapshot(self.sim, offender_eid)
        if bool(snapshot.get("in_custody", False)):
            return False
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
        return True

    def on_property_trespass(self, event):
        if event_is_vision_only(event):
            return
        offender_eid = event.data.get("offender_eid")
        if offender_eid is None:
            return
        observation = self._event_accountability(event, offender_eid=offender_eid)
        if not bool(observation.get("has_accountable_observation")):
            return
        resolved_eid, scene_enforcers = self._resolve_actionable_event_subject(
            event,
            offender_eid,
            observation=observation,
        )
        if resolved_eid is None:
            self._queue_scene_apprehension(
                offender_eid,
                scene_enforcers,
                {
                    "incident_type": "trespass",
                    "severity": int(event.data.get("severity_score", 0) or 0),
                    "source_event": "property_trespass",
                    "property_id": event.data.get("property_id"),
                    "x": event.data.get("x"),
                    "y": event.data.get("y"),
                    "z": event.data.get("z", 0),
                    "note": str(event.data.get("severity_label", "trespass") or "").strip().lower(),
                    "knowledge_incident_id": event.data.get("knowledge_incident_id"),
                },
            )
            return
        offender_eid = resolved_eid
        change = self._record_incident(
            offender_eid,
            incident_type="trespass",
            severity=int(event.data.get("severity_score", 0) or 0),
            source_event="property_trespass",
            property_id=event.data.get("property_id"),
            x=event.data.get("x"),
            y=event.data.get("y"),
            witnessed=True,
            note=str(event.data.get("severity_label", "trespass") or "").strip().lower(),
        )
        if change is not None:
            self._mark_incident_accounted(event.data.get("knowledge_incident_id"))

    def on_property_tamper(self, event):
        if event_is_vision_only(event):
            return
        offender_eid = event.data.get("offender_eid")
        if offender_eid is None:
            return
        property_id = str(event.data.get("property_id", "") or "").strip()
        prop = self.sim.properties.get(property_id) if property_id else None
        observation = self._event_accountability(event, offender_eid=offender_eid)
        if not bool(observation.get("has_accountable_observation")):
            return
        resolved_eid, scene_enforcers = self._resolve_actionable_event_subject(
            event,
            offender_eid,
            observation=observation,
        )
        if resolved_eid is None:
            self._queue_scene_apprehension(
                offender_eid,
                scene_enforcers,
                {
                    "incident_type": "tamper",
                    "severity": int(event.data.get("severity_score", 0) or 0),
                    "source_event": "property_tamper",
                    "property_id": property_id,
                    "x": event.data.get("x"),
                    "y": event.data.get("y"),
                    "z": event.data.get("z", 0),
                    "note": "property_tamper",
                    "knowledge_incident_id": event.data.get("knowledge_incident_id"),
                    "structural_restitution": True,
                },
            )
            return
        offender_eid = resolved_eid
        change = self._record_incident(
            offender_eid,
            incident_type="tamper",
            severity=int(event.data.get("severity_score", 0) or 0),
            source_event="property_tamper",
            property_id=property_id,
            x=event.data.get("x"),
            y=event.data.get("y"),
            witnessed=True,
            note="property_tamper",
        )
        if change is not None:
            self._mark_incident_accounted(event.data.get("knowledge_incident_id"))
        if change is not None and isinstance(prop, dict):
            self._record_structural_restitution_claim(
                offender_eid,
                prop,
                damage_tick=int(getattr(self.sim, "tick", 0)),
            )

    def on_property_doorway_obstruction(self, event):
        offender_eid = event.data.get("offender_eid")
        if offender_eid is None:
            return
        observer_eids = []
        positions = self.sim.ecs.get(Position)
        try:
            target_x = int(event.data.get("x"))
            target_y = int(event.data.get("y"))
            target_z = int(event.data.get("z", 0))
        except (TypeError, ValueError):
            return
        for raw_eid in tuple(event.data.get("observer_eids", ()) or ()):
            try:
                observer_eid = int(raw_eid)
            except (TypeError, ValueError):
                continue
            enforcer, _law_drive, _priority = self._actor_is_enforcer(observer_eid)
            if not enforcer:
                continue
            observer_pos = positions.get(observer_eid)
            if observer_pos is None:
                continue
            if not _shared_observer_can_see_position(
                self.sim,
                observer_eid,
                int(observer_pos.x),
                int(observer_pos.y),
                int(observer_pos.z),
                target_x,
                target_y,
                target_z,
                radius=8,
            ):
                continue
            observer_eids.append(observer_eid)
        if not observer_eids:
            return
        severity = int(event.data.get("severity_score", 28) or 28)
        self._record_incident(
            offender_eid,
            incident_type="obstruction",
            severity=severity,
            source_event="property_doorway_obstruction",
            property_id=event.data.get("property_id"),
            x=event.data.get("x"),
            y=event.data.get("y"),
            witnessed=True,
            note="blocking_entry",
        )

    def on_item_stolen(self, event):
        if event_is_vision_only(event):
            return
        offender_eid = event.data.get("offender_eid")
        if offender_eid is None:
            return
        observation = self._event_accountability(event, offender_eid=offender_eid)
        if not bool(observation.get("has_accountable_observation")):
            return
        resolved_eid, scene_enforcers = self._resolve_actionable_event_subject(
            event,
            offender_eid,
            observation=observation,
        )
        if resolved_eid is None:
            self._queue_scene_apprehension(
                offender_eid,
                scene_enforcers,
                {
                    "incident_type": "theft",
                    "severity": 72,
                    "source_event": "item_stolen",
                    "property_id": event.data.get("property_id"),
                    "x": event.data.get("x"),
                    "y": event.data.get("y"),
                    "z": event.data.get("z", 0),
                    "note": str(event.data.get("item_name", event.data.get("item_id", "item")) or "").strip(),
                    "knowledge_incident_id": event.data.get("knowledge_incident_id"),
                },
            )
            return
        offender_eid = resolved_eid
        change = self._record_incident(
            offender_eid,
            incident_type="theft",
            severity=72,
            source_event="item_stolen",
            property_id=event.data.get("property_id"),
            x=event.data.get("x"),
            y=event.data.get("y"),
            witnessed=True,
            note=str(event.data.get("item_name", event.data.get("item_id", "item")) or "").strip(),
        )
        if change is not None:
            self._mark_incident_accounted(event.data.get("knowledge_incident_id"))

    def on_action_offense(self, event):
        if event_is_vision_only(event):
            return
        offender_eid = event.data.get("offender_eid")
        if offender_eid is None:
            return
        factual_offender_eid = offender_eid
        context = str(event.data.get("context", "ordinary") or "").strip().lower() or "ordinary"
        if context not in {
            "contraband_trade",
            "contraband_use",
            *VIOLENT_OFFENSE_CONTEXTS,
            *CIVIC_WILDLIFE_OFFENSE_CONTEXTS,
            *WITNESS_TAMPERING_OFFENSE_CONTEXTS,
            *PUBLIC_ORDER_OFFENSE_CONTEXTS,
        }:
            return
        observation = self._event_accountability(event, offender_eid=offender_eid)
        scene_enforcers = self._firsthand_scene_enforcers(
            event,
            offender_eid,
            observation=observation,
            include_victim=context in VIOLENT_OFFENSE_CONTEXTS,
        )
        if not bool(observation.get("has_accountable_observation")) and not scene_enforcers:
            return
        force_read = None
        severity = int(event.data.get("offense_score", 0) or 0)
        if context in VIOLENT_OFFENSE_CONTEXTS:
            force_read = classify_lawful_force(self.sim, event.data, offender_eid=offender_eid)
            self._remember_force_context(offender_eid, force_read, data=event.data)
            self.sim.emit(Event(
                "justice_force_classified",
                eid=offender_eid,
                action=str(event.data.get("action", "action") or "action").strip().lower(),
                context=context,
                recordable=bool(force_read.get("recordable", True)),
                suppressed=bool(force_read.get("suppressed", False)),
                **force_payload(force_read),
            ))
            severity = mitigated_force_severity(severity, force_read)
            if severity <= 0:
                return
        resolved_eid, scene_enforcers = self._resolve_actionable_event_subject(
            event,
            offender_eid,
            observation=observation,
            include_victim=context in VIOLENT_OFFENSE_CONTEXTS,
        )
        if resolved_eid is None:
            self._queue_scene_apprehension(
                offender_eid,
                scene_enforcers,
                {
                    "incident_type": self._incident_type_from_context(context),
                    "severity": severity,
                    "source_event": "action_offense",
                    "x": event.data.get("x"),
                    "y": event.data.get("y"),
                    "z": event.data.get("z", 0),
                    "note": f"{str(event.data.get('action', 'action') or '').strip().lower()}/{context}/{(force_read or {}).get('force_context', '')}".strip("/"),
                    "knowledge_incident_id": event.data.get("knowledge_incident_id"),
                    "force_read": dict(force_read) if isinstance(force_read, dict) else None,
                    "force_data": {
                        field: event.data.get(field)
                        for field in ("target_eid", "victim_eid", "context", "action")
                        if event.data.get(field) not in (None, "", ())
                    },
                },
            )
            return
        offender_eid = resolved_eid
        if force_read is not None:
            self._record_bounty_misuse_review(
                offender_eid,
                force_read,
                data=event.data,
                factual_offender_eid=factual_offender_eid,
            )
        incident_type = self._incident_type_from_context(context)
        change = self._record_incident(
            offender_eid,
            incident_type=incident_type,
            severity=severity,
            source_event="action_offense",
            x=event.data.get("x"),
            y=event.data.get("y"),
            witnessed=True,
            note=f"{str(event.data.get('action', 'action') or '').strip().lower()}/{context}/{(force_read or {}).get('force_context', '')}".strip("/"),
            repeat_scope=(
                f"observer:{int(event.data.get('exposure_observer_eid'))}"
                if context in PUBLIC_ORDER_OFFENSE_CONTEXTS and event.data.get("exposure_observer_eid") is not None
                else ""
            ),
        )
        if change is not None:
            self._mark_incident_accounted(event.data.get("knowledge_incident_id"))

    def on_justice_mutual_fight_observed(self, event):
        if event_is_vision_only(event):
            return
        incident_id = event.data.get("incident_id")
        participants = tuple(event.data.get("participant_eids", ()) or ())
        cleaned_participants = []
        for eid in participants:
            try:
                value = int(eid)
            except (TypeError, ValueError):
                continue
            if value > 0 and value not in cleaned_participants:
                cleaned_participants.append(value)
        if len(cleaned_participants) < 2:
            return

        context = str(event.data.get("context", "unarmed_assault") or "unarmed_assault").strip().lower()
        if context not in VIOLENT_OFFENSE_CONTEXTS:
            context = "unarmed_assault"
        incident_type = self._incident_type_from_context(context)
        severity = max(18, int(event.data.get("severity", 0) or 0))
        witness_eids = tuple(event.data.get("witness_eids", ()) or ())
        observer_eid = event.data.get("observer_eid")
        witness_count = max(len(witness_eids), 1 if observer_eid is not None else 0)
        context_label = self._mutual_fight_context_label(context)

        changes = []
        for offender_eid in cleaned_participants:
            other_participants = [eid for eid in cleaned_participants if eid != offender_eid]
            other_eid = other_participants[0] if other_participants else None
            payload = {
                "incident_id": incident_id,
                "observer_eid": observer_eid,
                "participant_eids": tuple(cleaned_participants),
                "other_participant_eid": other_eid,
                "context": context,
                "weapon_seriousness": context_label,
                "witness_eids": witness_eids,
                "witness_count": int(witness_count),
                "tick": int(getattr(self.sim, "tick", 0)),
            }
            self._remember_mutual_fight_questioning_payload(offender_eid, payload)
            change = self._record_incident(
                offender_eid,
                incident_type=incident_type,
                severity=severity,
                source_event="mutual_fight_observed",
                x=event.data.get("x"),
                y=event.data.get("y"),
                witnessed=True,
                note=f"mutual_fight/{context}/{context_label}/incident_{incident_id}/witnesses_{witness_count}",
            )
            if change is not None:
                changes.append(change)

        if changes:
            ordered_eids = self._humanoid_participants(cleaned_participants)
            if ordered_eids:
                self.sim.emit(Event(
                    "justice_mutual_fight_unready_ordered",
                    incident_id=incident_id,
                    officer_eid=observer_eid,
                    participant_eids=ordered_eids,
                    context=context,
                    weapon_seriousness=context_label,
                    x=event.data.get("x"),
                    y=event.data.get("y"),
                    z=event.data.get("z"),
                ))
            self.sim.emit(Event(
                "justice_mutual_fight_questioning_recorded",
                incident_id=incident_id,
                observer_eid=observer_eid,
                participant_eids=tuple(cleaned_participants),
                context=context,
                weapon_seriousness=context_label,
                witness_eids=witness_eids,
                witness_count=int(witness_count),
                change_count=len(changes),
            ))

    def on_npc_killed(self, event):
        if event_is_vision_only(event):
            return
        if isinstance(event.data.get("animal_payload"), dict) and event.data.get("animal_payload"):
            return
        offender_eid = event.data.get("offender_eid", event.data.get("source_eid"))
        if offender_eid is None:
            return
        factual_offender_eid = offender_eid
        event.data.setdefault("offender_eid", offender_eid)
        event.data.setdefault("victim_eid", event.data.get("target_eid"))
        event.data.setdefault("context", "homicide")
        event.data.setdefault("action", "homicide")
        observation = self._event_accountability(
            event,
            offender_eid=offender_eid,
            allow_position_backfill=True,
        )
        if not bool(observation.get("has_accountable_observation")):
            return
        force_read = self._homicide_force_read(event.data, offender_eid)
        self._remember_force_context(offender_eid, force_read, data=event.data)
        self.sim.emit(Event(
            "justice_force_classified",
            eid=offender_eid,
            action="homicide",
            context="homicide",
            recordable=bool(force_read.get("recordable", True)),
            suppressed=bool(force_read.get("suppressed", False)),
            **force_payload(force_read),
        ))
        severity = mitigated_force_severity(self.HOMICIDE_SEVERITY_SCORE, force_read)
        if severity <= 0:
            self._mark_incident_accounted(event.data.get("knowledge_incident_id"), field="justice_force_reviewed")
            return
        resolved_eid, scene_enforcers = self._resolve_actionable_event_subject(
            event,
            offender_eid,
            observation=observation,
            allow_position_backfill=True,
        )
        if resolved_eid is None:
            self._queue_scene_apprehension(
                offender_eid,
                scene_enforcers,
                {
                    "incident_type": "homicide",
                    "severity": severity,
                    "source_event": "npc_killed",
                    "x": event.data.get("x"),
                    "y": event.data.get("y"),
                    "z": event.data.get("z", 0),
                    "note": f"homicide/{str(event.data.get('target_name', '') or '').strip()}/{str(event.data.get('reason', '') or '').strip().lower()}/{force_read.get('force_context', '')}".strip("/"),
                    "knowledge_incident_id": event.data.get("knowledge_incident_id"),
                    "force_read": dict(force_read),
                    "force_data": {
                        field: event.data.get(field)
                        for field in ("target_eid", "victim_eid", "context", "action")
                        if event.data.get(field) not in (None, "", ())
                    },
                },
            )
            return
        offender_eid = resolved_eid
        self._record_bounty_misuse_review(
            offender_eid,
            force_read,
            data=event.data,
            factual_offender_eid=factual_offender_eid,
        )
        change = self._record_incident(
            offender_eid,
            incident_type="homicide",
            severity=severity,
            source_event="npc_killed",
            x=event.data.get("x"),
            y=event.data.get("y"),
            witnessed=True,
            note=f"homicide/{str(event.data.get('target_name', '') or '').strip()}/{str(event.data.get('reason', '') or '').strip().lower()}/{force_read.get('force_context', '')}".strip("/"),
        )
        if change is not None:
            self._mark_incident_accounted(event.data.get("knowledge_incident_id"))

    def on_incident_authority_reported(self, event):
        if event_is_vision_only(event):
            return
        incident = incident_record(self.sim, event.data.get("incident_id"))
        if not isinstance(incident, dict):
            return
        if event_is_vision_only(incident):
            return
        report_data = dict(event.data)
        report_data["subject_account"] = self._agency_visual_identity_account(
            incident,
            report_data,
        )
        case, case_changed, newly_resolved = record_justice_identity_report(
            self.sim,
            incident,
            report_data,
        )
        case_payload = justice_case_event_payload(case)
        incident["officially_reported"] = True
        incident.setdefault("reported_tick", int(getattr(self.sim, "tick", 0)))
        incident.setdefault("reported_by_eid", event.data.get("reporter_eid", event.data.get("npc_eid")))
        mark_incident_registry_changed(self.sim)
        crime_profile = self._provisional_case_crime_profile(case, incident)
        if isinstance(case, dict):
            case["provisional_crime_profile"] = dict(crime_profile) if isinstance(crime_profile, dict) else None
            case["provisional_crime_actionable"] = isinstance(crime_profile, dict)
        self._emit_identity_case_change(case, changed=case_changed, newly_resolved=newly_resolved)
        if bool(incident.get("justice_accounted")):
            return
        offender_eid = case_payload.get("resolved_subject_eid")
        if offender_eid is None:
            incident["justice_identity_unresolved"] = True
            incident["justice_identity_case_id"] = case_payload.get("case_id")
            return
        incident["justice_identity_unresolved"] = False
        incident["justice_identity_case_id"] = case_payload.get("case_id")
        for attribution in tuple((case or {}).get("provisional_attributions", ()) or ()):
            if not isinstance(attribution, dict):
                continue
            try:
                same_actor = int(attribution.get("actor_eid")) == int(offender_eid)
            except (TypeError, ValueError):
                same_actor = False
            if same_actor and bool(attribution.get("justice_record_created", False)):
                self._mark_incident_accounted(incident.get("id"))
                attribution["punishment_status"] = "confirmed_attribution"
                return
        report_observation = self._event_accountability(
            event,
            offender_eid=offender_eid,
        )
        if not bool(report_observation.get("has_accountable_observation")):
            return
        incident_kind = str(incident.get("kind", "") or "").strip().lower()
        severity_score = int(incident.get("severity", 0) or 0)
        if severity_score <= 0:
            return
        if incident_kind == "camera_alert":
            change = self._record_incident(
                offender_eid,
                incident_type="trespass",
                severity=severity_score,
                source_event="property_trespass",
                property_id=incident.get("property_id"),
                x=incident.get("x"),
                y=incident.get("y"),
                witnessed=True,
                note=str(incident.get("note", "camera_alert") or "camera_alert").strip().lower(),
            )
        elif incident_kind == "property_trespass":
            change = self._record_incident(
                offender_eid,
                incident_type="trespass",
                severity=severity_score,
                source_event="property_trespass",
                property_id=incident.get("property_id"),
                x=incident.get("x"),
                y=incident.get("y"),
                witnessed=True,
                note=str(incident.get("note", "trespass") or "trespass").strip().lower(),
            )
        elif incident_kind == "property_tamper":
            change = self._record_incident(
                offender_eid,
                incident_type="tamper",
                severity=severity_score,
                source_event="property_tamper",
                property_id=incident.get("property_id"),
                x=incident.get("x"),
                y=incident.get("y"),
                witnessed=True,
                note="property_tamper",
            )
            property_id = str(incident.get("property_id", "") or "").strip()
            prop = self.sim.properties.get(property_id) if property_id else None
            if change is not None and isinstance(prop, dict):
                self._record_structural_restitution_claim(
                    offender_eid,
                    prop,
                    damage_tick=int(getattr(self.sim, "tick", 0)),
                )
        elif incident_kind == "item_stolen":
            change = self._record_incident(
                offender_eid,
                incident_type="theft",
                severity=severity_score,
                source_event="item_stolen",
                property_id=incident.get("property_id"),
                x=incident.get("x"),
                y=incident.get("y"),
                witnessed=True,
                note=str(incident.get("note", incident.get("item_name", "item")) or "item").strip(),
            )
        elif incident_kind == "homicide":
            homicide_data = dict(incident)
            homicide_data.setdefault("context", "homicide")
            homicide_data.setdefault("action", "homicide")
            homicide_data.setdefault("target_eid", incident.get("victim_eid"))
            force_read = self._homicide_force_read(homicide_data, offender_eid)
            self._remember_force_context(offender_eid, force_read, data=homicide_data)
            self.sim.emit(Event(
                "justice_force_classified",
                eid=offender_eid,
                action="homicide",
                context="homicide",
                recordable=bool(force_read.get("recordable", True)),
                suppressed=bool(force_read.get("suppressed", False)),
                **force_payload(force_read),
            ))
            effective_severity = mitigated_force_severity(
                max(self.HOMICIDE_SEVERITY_SCORE, severity_score),
                force_read,
            )
            if effective_severity <= 0:
                self._mark_incident_accounted(incident.get("id"), field="justice_force_reviewed")
                return
            self._record_bounty_misuse_review(
                offender_eid,
                force_read,
                data=incident,
                factual_offender_eid=incident.get("primary_actor_eid"),
            )
            change = self._record_incident(
                offender_eid,
                incident_type="homicide",
                severity=effective_severity,
                source_event="npc_killed",
                x=incident.get("x"),
                y=incident.get("y"),
                witnessed=True,
                note=f"homicide/{str(incident.get('victim_name', incident.get('target_name', '')) or '').strip()}/{force_read.get('force_context', '')}".strip("/"),
            )
        elif incident_kind == "action_offense":
            context = str(incident.get("context", "") or "").strip().lower() or str(incident.get("merge_subject", "") or "").split(":")[-1].strip().lower()
            if context not in {
                "contraband_trade",
                "contraband_use",
                *VIOLENT_OFFENSE_CONTEXTS,
                *CIVIC_WILDLIFE_OFFENSE_CONTEXTS,
                *WITNESS_TAMPERING_OFFENSE_CONTEXTS,
                *PUBLIC_ORDER_OFFENSE_CONTEXTS,
            }:
                return
            force_read = None
            effective_severity = severity_score
            if context in VIOLENT_OFFENSE_CONTEXTS:
                force_read = classify_lawful_force(self.sim, incident, offender_eid=offender_eid)
                self._remember_force_context(offender_eid, force_read, data=incident)
                self.sim.emit(Event(
                    "justice_force_classified",
                    eid=offender_eid,
                    action=str(incident.get("action", "action") or "action").strip().lower(),
                    context=context,
                    recordable=bool(force_read.get("recordable", True)),
                    suppressed=bool(force_read.get("suppressed", False)),
                    **force_payload(force_read),
                ))
                effective_severity = mitigated_force_severity(effective_severity, force_read)
                if effective_severity <= 0:
                    self._mark_incident_accounted(incident.get("id"), field="justice_force_reviewed")
                    return
                self._record_bounty_misuse_review(
                    offender_eid,
                    force_read,
                    data=incident,
                    factual_offender_eid=incident.get("primary_actor_eid"),
                )
            change = self._record_incident(
                offender_eid,
                incident_type=self._incident_type_from_context(context),
                severity=effective_severity,
                source_event="action_offense",
                x=incident.get("x"),
                y=incident.get("y"),
                witnessed=True,
                note=f"{str(incident.get('action', 'action') or '').strip().lower()}/{context}/{(force_read or {}).get('force_context', '')}".strip("/"),
                repeat_scope=(
                    f"observer:{int(incident.get('exposure_observer_eid'))}"
                    if context in PUBLIC_ORDER_OFFENSE_CONTEXTS and incident.get("exposure_observer_eid") is not None
                    else ""
                ),
            )
        else:
            return
        if change is not None:
            self._mark_incident_accounted(incident.get("id"))

    def on_property_interact(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        if bool(event.data.get("handled")):
            return
        interaction_mode = str(event.data.get("interaction_mode", "") or "").strip().lower()
        if interaction_mode == "service":
            return
        prop = self.sim.properties.get(event.data.get("property_id"))
        if not self._booking_property_allowed(prop):
            return
        snapshot = self._player_bookable_snapshot()
        if snapshot is not None:
            tier = str(snapshot.get("wanted_tier", "clear")).strip().lower() or "clear"
            if tier == "questioning":
                if self._open_player_questioning_prompt(None, snapshot=snapshot, source_prop=prop):
                    event.data["handled"] = True
                return
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
        payment_lines = []
        if debt_balance > 0:
            payment = self._pay_player_justice_debt_at_desk(prop)
            payment_lines = self._justice_desk_debt_lines(payment)
            debt_balance = int(self._player_justice_debt_balance())

        if held_count > 0 and held_property_id and held_property_id != current_property_id:
            lines = [
                "This desk is not holding your seized property.",
                *self._justice_status_lines(current_prop=prop),
                *payment_lines,
            ]
            if held_property_name:
                if debt_balance > 0:
                    lines.append(f"The correct property locker is at {held_property_name}, but release is blocked until {debt_balance}c justice debt is cleared.")
                else:
                    lines.append(f"The correct property locker is at {held_property_name}.")
            self._present_justice_result(title, lines, property_id=prop.get("id"))
            return

        if held_count > 0 and debt_balance > 0:
            lines = [
                f"Release is blocked until your {debt_balance}c justice debt is cleared.",
                *self._justice_status_lines(current_prop=prop),
                *payment_lines,
            ]
            if held_property_name:
                lines.append(f"Your held property is logged at {held_property_name}.")
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
            lines = list(payment_lines) + lines
            self._present_justice_result(title, lines, property_id=prop.get("id"))
            return

        if payment_lines:
            self._present_justice_result(title, [*self._justice_status_lines(current_prop=prop), *payment_lines], property_id=prop.get("id"))
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
        if map_mode_active(self.sim):
            return
        if _actor_in_live_combat(self.sim, self.player_eid):
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
        snapshot = self._player_bookable_snapshot()
        identity_match = None if snapshot is not None else self._player_unresolved_identity_match()
        if snapshot is None and identity_match is None:
            return

        # Depending on system registration order, the ordinary talk handler
        # may already have opened this exact player-initiated conversation.
        # It is safe to hand that one interaction to justice; an unrelated
        # modal must remain untouched.
        state = self._dialog_ui_state()
        if (
            bool(state.get("open"))
            and str(state.get("kind", "conversation") or "conversation").strip().lower() == "conversation"
            and state.get("npc_eid") == npc_eid
        ):
            self.sim.set_time_paused(False, reason="dialog")
            self._reset_dialog_ui(state)

        opened = (
            self._open_player_justice_prompt(npc_eid, snapshot=snapshot, respect_cooldown=False)
            if snapshot is not None
            else self._open_player_identity_check_prompt(npc_eid, identity_match)
        )
        if opened:
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

    def on_justice_questioning_choice(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        if not self._player_surrender_prompt_open():
            return
        prompt = self.player_surrender_prompt if isinstance(self.player_surrender_prompt, dict) else {}
        if str(prompt.get("kind", "")).strip().lower() != self.QUESTIONING_DIALOG_KIND:
            return
        by_eid = prompt.get("npc_eid", event.data.get("npc_eid"))
        source_prop = self.sim.properties.get(prompt.get("source_prop_id")) if prompt.get("source_prop_id") else None
        snapshot = self._player_bookable_snapshot()
        choice_id = str(event.data.get("choice_id", "") or "").strip().lower() or "refuse"
        self._close_player_surrender_prompt()
        self._resolve_player_questioning_choice(choice_id, by_eid=by_eid, source_prop=source_prop, snapshot=snapshot)

    def on_justice_identity_check_choice(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        if not self._player_surrender_prompt_open():
            return
        prompt = self.player_surrender_prompt if isinstance(self.player_surrender_prompt, dict) else {}
        if str(prompt.get("kind", "")).strip().lower() != self.IDENTITY_CHECK_DIALOG_KIND:
            return
        choice_id = str(event.data.get("choice_id", "") or "").strip().lower() or "decline"
        self._close_player_surrender_prompt()
        self._resolve_player_identity_check_choice(choice_id, prompt=prompt)

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

    def _clear_detention_approach(self, offender_eid, *, reason="ended"):
        records = self._detention_approach_records()
        record = records.pop(str(int(offender_eid)), None)
        if not isinstance(record, dict):
            return
        responder_eid = record.get("responder_eid")
        try:
            responder_eid = int(responder_eid)
        except (TypeError, ValueError):
            return
        ai = self.sim.ecs.get(AI).get(responder_eid)
        will = self.sim.ecs.get(NPCWill).get(responder_eid)
        if ai is None or str(getattr(ai, "response_role", "") or "").strip().lower() != "justice_detention":
            return
        context = getattr(ai, "investigation_context", None)
        if is_purposeful_observation(context, purpose="justice_detention"):
            ai.investigation_context = finish_purposeful_observation(
                context,
                current_tick=self.sim.tick,
                reason=reason,
            )
        ai.response_role = None
        ai.incident_id = None
        if str(getattr(ai, "state", "") or "").strip().lower() in {"idle", "investigating"}:
            _sync_ai_intent(ai, will, self.sim.tick, "idle", score=0.0, target=None, target_eid=None)

    def _advance_or_assign_detention_approach(self, offender_eid):
        records = self._detention_approach_records()
        key = str(int(offender_eid))
        record = records.get(key)
        if not isinstance(record, dict):
            responder_eid = self._find_detaining_enforcer(
                offender_eid,
                radius=self.JUSTICE_DETENTION_NOTICE_RADIUS,
            )
            if responder_eid is None:
                return None
            record = {
                "offender_eid": int(offender_eid),
                "responder_eid": int(responder_eid),
                "started_tick": int(getattr(self.sim, "tick", 0)),
            }
            records[key] = record
        try:
            responder_eid = int(record.get("responder_eid"))
        except (TypeError, ValueError):
            records.pop(key, None)
            return None
        ai = self.sim.ecs.get(AI).get(responder_eid)
        will = self.sim.ecs.get(NPCWill).get(responder_eid)
        if ai is None or will is None or self._position_for(offender_eid) is None:
            self._clear_detention_approach(offender_eid, reason="invalid_target")
            return None
        if self._justice_response_interrupted(responder_eid, response_role="justice_detention"):
            return None
        context, contact, target = self._purposeful_actor_approach(
            responder_eid,
            offender_eid,
            purpose="justice_detention",
            existing=getattr(ai, "investigation_context", None),
            notice_radius=self.JUSTICE_DETENTION_NOTICE_RADIUS,
            capture_subject_account=False,
        )
        ai.investigation_context = context
        responder_pos = self._position_for(responder_eid)
        offender_pos = self._position_for(offender_eid)
        if contact == "visible" and responder_pos is not None and offender_pos is not None:
            if _manhattan(responder_pos.x, responder_pos.y, offender_pos.x, offender_pos.y) <= int(self.JUSTICE_DETENTION_CONTACT_RADIUS):
                return responder_eid
        if target is None:
            self._clear_detention_approach(offender_eid, reason="lost_contact")
            return None
        was_approaching = str(getattr(ai, "response_role", "") or "").strip().lower() == "justice_detention"
        _sync_ai_intent(
            ai,
            will,
            self.sim.tick,
            "investigating",
            score=88.0,
            target=target,
            target_eid=None,
        )
        ai.response_role = "justice_detention"
        if not was_approaching:
            self.sim.emit(Event(
                "justice_detention_approach_started",
                npc_eid=responder_eid,
                target_eid=offender_eid,
                x=target[0],
                y=target[1],
                z=target[2],
            ))
        return None

    def _bounty_target_is_restrained(self, target_eid):
        suppression = self.sim.ecs.get(SuppressionState).get(target_eid)
        if bool(getattr(suppression, "surrendered", False)):
            return True
        ai = self.sim.ecs.get(AI).get(target_eid)
        return str(getattr(ai, "state", "") or "").strip().lower() == "surrendered"

    def _clear_bounty_pickup(self, target_eid, *, reason="ended"):
        records = self._bounty_pickup_records()
        record = records.pop(str(int(target_eid)), None)
        if not isinstance(record, dict):
            return
        responder_eid = record.get("responder_eid")
        try:
            responder_eid = int(responder_eid)
        except (TypeError, ValueError):
            responder_eid = None
        ai = self.sim.ecs.get(AI).get(responder_eid) if responder_eid is not None else None
        will = self.sim.ecs.get(NPCWill).get(responder_eid) if responder_eid is not None else None
        if ai is not None and str(getattr(ai, "response_role", "") or "").strip().lower() == "bounty_pickup":
            context = getattr(ai, "investigation_context", None)
            if is_purposeful_observation(context, purpose="bounty_pickup"):
                ai.investigation_context = finish_purposeful_observation(
                    context,
                    current_tick=self.sim.tick,
                    reason=reason,
                )
            ai.response_role = None
            ai.incident_id = None
            if str(getattr(ai, "state", "") or "").strip().lower() in {"idle", "investigating"}:
                _sync_ai_intent(ai, will, self.sim.tick, "idle", score=0.0, target=None, target_eid=None)
        self.sim.emit(Event(
            "bounty_pickup_ended",
            target_eid=int(target_eid),
            responder_eid=responder_eid,
            reason=str(reason or "ended").strip().lower(),
        ))

    def _assign_bounty_pickup_responder(self, record):
        if not isinstance(record, dict):
            return False
        reported = record.get("reported_position")
        if not isinstance(reported, (tuple, list)) or len(reported) < 3:
            return False
        try:
            rx, ry, rz = int(reported[0]), int(reported[1]), int(reported[2])
        except (TypeError, ValueError):
            return False
        positions = self.sim.ecs.get(Position)
        candidates = []
        for eid in self.sim.entity_ids_in_radius(rx, ry, rz, self.BOUNTY_PICKUP_DISPATCH_RADIUS):
            pos = positions.get(eid)
            if pos is None or int(pos.z) != rz or int(eid) == int(record.get("target_eid", -1) or -1):
                continue
            enforcer, law_drive, priority = self._actor_is_enforcer(eid)
            if not enforcer or self._justice_response_interrupted(eid, response_role="bounty_pickup"):
                continue
            if self.sim.ecs.get(NPCWill).get(eid) is None:
                continue
            distance = _manhattan(pos.x, pos.y, rx, ry)
            if distance > int(self.BOUNTY_PICKUP_DISPATCH_RADIUS):
                continue
            candidates.append((distance, -priority, -law_drive, int(eid)))
        if not candidates:
            return False
        for _distance, _priority, _law_drive, responder_eid in sorted(candidates):
            try:
                context = begin_purposeful_anchor_observation(
                    self.sim,
                    responder_eid,
                    (rx, ry, rz),
                    purpose="bounty_pickup",
                    anchor_kind="reported_bounty_pickup",
                    anchor_id=record.get("opportunity_id"),
                )
            except ValueError:
                continue
            ai = self.sim.ecs.get(AI).get(responder_eid)
            will = self.sim.ecs.get(NPCWill).get(responder_eid)
            if ai is None or will is None:
                continue
            target = tuple(context.get("watch_position", (rx, ry, rz)))
            ai.investigation_context = context
            _sync_ai_intent(ai, will, self.sim.tick, "investigating", score=86.0, target=target, target_eid=None)
            ai.response_role = "bounty_pickup"
            ai.incident_id = None
            record["responder_eid"] = int(responder_eid)
            record["assigned_tick"] = int(getattr(self.sim, "tick", 0))
            record["state"] = "en_route"
            self.sim.emit(Event(
                "bounty_pickup_responder_assigned",
                target_eid=int(record.get("target_eid")),
                responder_eid=int(responder_eid),
                x=rx,
                y=ry,
                z=rz,
            ))
            return True
        return False

    def _process_bounty_pickups(self):
        tick = int(getattr(self.sim, "tick", 0))
        records = self._bounty_pickup_records()
        for raw_target_eid, record in tuple(records.items()):
            try:
                target_eid = int(raw_target_eid)
            except (TypeError, ValueError):
                records.pop(raw_target_eid, None)
                continue
            if not isinstance(record, dict):
                records.pop(raw_target_eid, None)
                continue
            if tick > int(record.get("expires_at", tick) or tick):
                self._clear_bounty_pickup(target_eid, reason="pickup_expired")
                continue
            snapshot = _justice_snapshot(self.sim, target_eid)
            if bool(snapshot.get("in_custody", False)):
                self._clear_bounty_pickup(target_eid, reason="already_in_custody")
                continue
            target_pos = self._position_for(target_eid)
            if target_pos is None or str(snapshot.get("wanted_tier", "clear") or "clear").strip().lower() not in {"wanted", "arrest_on_sight"}:
                self._clear_bounty_pickup(target_eid, reason="target_unavailable")
                continue
            responder_eid = record.get("responder_eid")
            try:
                responder_eid = int(responder_eid) if responder_eid is not None else None
            except (TypeError, ValueError):
                responder_eid = None
            if responder_eid is None or self.sim.ecs.get(AI).get(responder_eid) is None:
                if tick >= int(record.get("next_assignment_tick", 0) or 0):
                    if not self._assign_bounty_pickup_responder(record):
                        record["next_assignment_tick"] = tick + 12
                continue
            if self._justice_response_interrupted(responder_eid, response_role="bounty_pickup"):
                continue
            responder_pos = self._position_for(responder_eid)
            ai = self.sim.ecs.get(AI).get(responder_eid)
            will = self.sim.ecs.get(NPCWill).get(responder_eid)
            if responder_pos is None or ai is None or will is None:
                record["responder_eid"] = None
                record["next_assignment_tick"] = tick + 3
                continue
            distance = _manhattan(responder_pos.x, responder_pos.y, target_pos.x, target_pos.y)
            visible = (
                int(responder_pos.z) == int(target_pos.z)
                and distance <= int(self.BOUNTY_PICKUP_VERIFY_RADIUS)
                and _shared_observer_can_see_position(
                    self.sim,
                    observer_eid=responder_eid,
                    observer_x=responder_pos.x,
                    observer_y=responder_pos.y,
                    observer_z=responder_pos.z,
                    target_x=target_pos.x,
                    target_y=target_pos.y,
                    target_z=target_pos.z,
                    radius=max(4, int(self.BOUNTY_PICKUP_VERIFY_RADIUS) + 2),
                )
            )
            if visible:
                if not self._bounty_target_is_restrained(target_eid):
                    self._clear_bounty_pickup(target_eid, reason="restraint_not_verified")
                    continue
                context, _contact, target = self._purposeful_actor_approach(
                    responder_eid,
                    target_eid,
                    purpose="bounty_pickup",
                    existing=getattr(ai, "investigation_context", None),
                    notice_radius=self.BOUNTY_PICKUP_VERIFY_RADIUS,
                    capture_subject_account=False,
                )
                ai.investigation_context = context
                if distance <= int(self.JUSTICE_DETENTION_CONTACT_RADIUS):
                    if self._complete_pending_npc_detention(target_eid, responder_eid, snapshot=snapshot):
                        self._clear_bounty_pickup(target_eid, reason="pickup_verified")
                    continue
                if target is not None:
                    _sync_ai_intent(ai, will, tick, "investigating", score=90.0, target=target, target_eid=None)
                    ai.response_role = "bounty_pickup"
                    record["state"] = "target_verified"
                continue

            reported = record.get("reported_position")
            watch_position = None
            context = getattr(ai, "investigation_context", None)
            if is_purposeful_observation(context, purpose="bounty_pickup"):
                watch_position = context.get("watch_position")
            if not isinstance(watch_position, (tuple, list)) or len(watch_position) < 3:
                watch_position = reported
            try:
                watch_position = (int(watch_position[0]), int(watch_position[1]), int(watch_position[2]))
            except (TypeError, ValueError, IndexError):
                self._clear_bounty_pickup(target_eid, reason="invalid_reported_position")
                continue
            if _manhattan(responder_pos.x, responder_pos.y, watch_position[0], watch_position[1]) <= 1:
                arrived_tick = record.get("arrived_tick")
                if arrived_tick is None:
                    record["arrived_tick"] = tick
                    record["state"] = "verifying_report"
                    self.sim.emit(Event(
                        "bounty_pickup_responder_arrived",
                        target_eid=target_eid,
                        responder_eid=responder_eid,
                        x=watch_position[0],
                        y=watch_position[1],
                        z=watch_position[2],
                    ))
                grace = max(0, int(observation_purpose_profile("bounty_pickup").get("lost_contact_grace_ticks", 0) or 0))
                if tick - int(record.get("arrived_tick", tick) or tick) > grace:
                    self._clear_bounty_pickup(target_eid, reason="target_not_verified")
                continue
            _sync_ai_intent(ai, will, tick, "investigating", score=86.0, target=watch_position, target_eid=None)
            ai.response_role = "bounty_pickup"

    def on_bounty_pickup_dispatch_requested(self, event):
        offender_eid = event.data.get("target_eid")
        if offender_eid in {None, self.player_eid}:
            return
        try:
            offender_eid = int(offender_eid)
        except (TypeError, ValueError):
            return
        snapshot = _justice_snapshot(self.sim, offender_eid)
        if bool(snapshot.get("in_custody", False)):
            return
        pos = self._position_for(offender_eid)
        if pos is None:
            return
        try:
            reported_position = (
                int(event.data.get("x", pos.x)),
                int(event.data.get("y", pos.y)),
                int(event.data.get("z", pos.z)),
            )
        except (TypeError, ValueError):
            reported_position = (int(pos.x), int(pos.y), int(pos.z))
        tick = int(getattr(self.sim, "tick", 0))
        expires_at = tick + max(int(self.DETENTION_QUEUE_WINDOW * 2), 90)
        self.pending_detentions[offender_eid] = expires_at
        # A caller-supplied pickup location is now the responder's only lawful
        # location lead.  Retire any older generic detention approach so it
        # cannot keep steering another officer toward stale/live target state
        # in parallel with this dedicated dispatch.
        self._clear_detention_approach(offender_eid, reason="bounty_pickup_called")
        record = {
            "target_eid": int(offender_eid),
            "requested_by_eid": event.data.get("eid"),
            "opportunity_id": int(event.data.get("opportunity_id", 0) or 0),
            "target_name": str(event.data.get("target_name", "the target") or "the target").strip() or "the target",
            "reported_position": reported_position,
            "requested_tick": tick,
            "expires_at": expires_at,
            "responder_eid": None,
            "next_assignment_tick": tick,
            "state": "requested",
        }
        self._bounty_pickup_records()[str(int(offender_eid))] = record
        self._assign_bounty_pickup_responder(record)

    def _process_pending_detentions(self):
        positions = self.sim.ecs.get(Position)
        tick = int(getattr(self.sim, "tick", 0))
        for offender_eid, expires_at in list(self.pending_detentions.items()):
            if tick > int(expires_at):
                self.pending_detentions.pop(int(offender_eid), None)
                self._clear_detention_approach(offender_eid, reason="detention_window_expired")
                self._clear_bounty_pickup(offender_eid, reason="pickup_expired")
                continue
            pos = positions.get(offender_eid)
            if pos is None:
                self.pending_detentions.pop(int(offender_eid), None)
                self._clear_detention_approach(offender_eid, reason="target_unavailable")
                self._clear_bounty_pickup(offender_eid, reason="target_unavailable")
                continue
            snapshot = _justice_snapshot(self.sim, offender_eid)
            if bool(snapshot.get("in_custody", False)):
                self.pending_detentions.pop(int(offender_eid), None)
                self._clear_detention_approach(offender_eid, reason="already_in_custody")
                self._clear_bounty_pickup(offender_eid, reason="already_in_custody")
                continue
            if str(snapshot.get("wanted_tier", "clear")).strip().lower() not in {"wanted", "arrest_on_sight"}:
                self.pending_detentions.pop(int(offender_eid), None)
                self._clear_detention_approach(offender_eid, reason="record_cleared")
                self._clear_bounty_pickup(offender_eid, reason="record_cleared")
                continue
            if str(int(offender_eid)) in self._bounty_pickup_records():
                continue

            approach_record = self._detention_approach_records().get(str(int(offender_eid)))
            preferred_eid = approach_record.get("responder_eid") if isinstance(approach_record, dict) else None
            held_by_eid = self._find_detaining_enforcer(
                offender_eid,
                radius=self.JUSTICE_DETENTION_CONTACT_RADIUS,
                preferred_eid=preferred_eid,
            )
            if held_by_eid is None:
                held_by_eid = self._advance_or_assign_detention_approach(offender_eid)
            if held_by_eid is None:
                continue
            if self._complete_pending_npc_detention(offender_eid, held_by_eid, snapshot=snapshot):
                self._clear_detention_approach(offender_eid, reason="custody_verified")

    def _process_guard_initiated_player_arrest(self):
        if map_mode_active(self.sim):
            return False
        snapshot = self._player_bookable_snapshot()
        if snapshot is None:
            self._clear_detention_approach(self.player_eid, reason="player_record_clear")
            return False
        if self._player_surrender_prompt_open():
            return False
        if _actor_in_live_combat(self.sim, self.player_eid):
            return False
        held_by_eid = self._find_auto_arrest_enforcer(snapshot)
        if held_by_eid is None:
            held_by_eid = self._advance_or_assign_detention_approach(self.player_eid)
            if held_by_eid is None:
                return False
        opened = bool(self._open_player_justice_prompt(held_by_eid, snapshot=snapshot, respect_cooldown=True))
        if opened:
            self._clear_detention_approach(self.player_eid, reason="surrender_prompt_opened")
        return opened

    def _identity_check_case_id(self, match_row):
        if not isinstance(match_row, dict):
            return None
        case = match_row.get("case") if isinstance(match_row.get("case"), dict) else {}
        try:
            return int(case.get("incident_id"))
        except (TypeError, ValueError):
            return None

    def _find_identity_check_enforcer(self, match_row):
        player_pos = self._position_for(self.player_eid)
        incident_id = self._identity_check_case_id(match_row)
        if (
            player_pos is None
            or (match_row is not None and incident_id is None)
            or _entity_is_downed(self.sim, self.player_eid)
        ):
            return None

        positions = self.sim.ecs.get(Position)
        ais = self.sim.ecs.get(AI)
        wills = self.sim.ecs.get(NPCWill)
        radius = int(self.PLAYER_IDENTITY_CHECK_NOTICE_RADIUS)
        best = None
        best_rank = None
        nearby_eids = self.sim.entity_ids_in_radius(
            player_pos.x,
            player_pos.y,
            player_pos.z,
            radius,
        )
        for eid in nearby_eids:
            pos = positions.get(eid)
            if pos is None:
                continue
            if eid == self.player_eid or int(pos.z) != int(player_pos.z):
                continue
            dist = _manhattan(pos.x, pos.y, player_pos.x, player_pos.y)
            if dist <= 0 or dist > radius or _entity_is_downed(self.sim, eid):
                continue
            enforcer, law_drive, priority = self._actor_is_enforcer(eid)
            if not enforcer:
                continue
            ai = ais.get(eid)
            will = wills.get(eid)
            if ai is None or will is None:
                continue
            response_role = str(getattr(ai, "response_role", "") or "").strip().lower()
            assigned_incident = getattr(ai, "incident_id", None)
            try:
                assigned_incident = int(assigned_incident) if assigned_incident is not None else None
            except (TypeError, ValueError):
                assigned_incident = None
            already_approaching = (
                incident_id is not None
                and response_role == "identity_check"
                and assigned_incident == incident_id
            )
            busy_state = str(getattr(ai, "state", "idle") or "idle").strip().lower()
            if not already_approaching:
                if busy_state in {
                    "protecting",
                    "reporting_incident",
                    "helping_victim",
                    "seeking_safety",
                    "holding",
                    "following",
                    "ejecting_target",
                    "leaving_property",
                }:
                    continue
                if (
                    incident_id is not None
                    and busy_state == "investigating"
                    and assigned_incident not in {None, incident_id}
                ):
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
            rank = (0 if already_approaching else 1, dist, -priority, -law_drive, int(eid))
            if best_rank is None or rank < best_rank:
                best = int(eid)
                best_rank = rank
        return best

    def _clear_identity_check_approach(self, enforcer_eid):
        self._identity_check_approach_records().pop(str(int(enforcer_eid)), None)
        ai = self.sim.ecs.get(AI).get(enforcer_eid)
        will = self.sim.ecs.get(NPCWill).get(enforcer_eid)
        if ai is None or str(getattr(ai, "response_role", "") or "").strip().lower() != "identity_check":
            return
        context = getattr(ai, "investigation_context", None)
        if is_purposeful_observation(context, purpose="justice_identity_check"):
            ai.investigation_context = finish_purposeful_observation(
                context,
                current_tick=self.sim.tick,
                reason="identity_check_ended",
            )
        ai.response_role = None
        ai.incident_id = None
        _sync_ai_intent(
            ai,
            will,
            self.sim.tick,
            "idle",
            score=0.0,
            target=None,
            target_eid=None,
        )

    def _purposeful_actor_approach(
        self,
        observer_eid,
        subject_eid,
        *,
        purpose,
        existing=None,
        notice_radius,
        capture_subject_account=False,
    ):
        return advance_purposeful_actor_observation(
            self.sim,
            observer_eid,
            subject_eid,
            purpose=purpose,
            existing=existing,
            sight_radius=max(1, int(notice_radius)),
            capture_subject_account=bool(capture_subject_account),
            include_subject_account=bool(capture_subject_account),
        )

    def _start_identity_check_approach(self, enforcer_eid, match_row):
        incident_id = self._identity_check_case_id(match_row)
        if incident_id is None:
            return False
        self._identity_check_approach_records()[str(int(enforcer_eid))] = {
            "enforcer_eid": int(enforcer_eid),
            "incident_id": int(incident_id),
            "started_tick": int(getattr(self.sim, "tick", 0)),
        }
        return bool(self._advance_identity_check_approach(enforcer_eid))

    def _advance_identity_check_approach(self, enforcer_eid):
        records = self._identity_check_approach_records()
        record = records.get(str(int(enforcer_eid)))
        if not isinstance(record, dict):
            return False
        ai = self.sim.ecs.get(AI).get(enforcer_eid)
        will = self.sim.ecs.get(NPCWill).get(enforcer_eid)
        if ai is None or will is None or _entity_is_downed(self.sim, enforcer_eid):
            records.pop(str(int(enforcer_eid)), None)
            return False
        if self._player_bookable_snapshot() is not None:
            self._clear_identity_check_approach(enforcer_eid)
            return False
        if _actor_in_live_combat(self.sim, enforcer_eid) or _actor_in_live_combat(self.sim, self.player_eid):
            return True
        busy_state = str(getattr(ai, "state", "idle") or "idle").strip().lower()
        response_role = str(getattr(ai, "response_role", "") or "").strip().lower()
        if response_role not in {"", "identity_check"} or busy_state in {
            "protecting",
            "reporting_incident",
            "helping_victim",
            "seeking_safety",
            "warning",
            "ejecting_target",
            "leaving_property",
        }:
            return True

        incident_id = int(record.get("incident_id", -1) or -1)
        case = justice_case_for_incident(self.sim, incident_id)
        if not isinstance(case, dict) or str(case.get("status", "unresolved") or "unresolved").strip().lower() != "unresolved":
            self._clear_identity_check_approach(enforcer_eid)
            return False
        context = getattr(ai, "investigation_context", None)
        context, contact, target = self._purposeful_actor_approach(
            enforcer_eid,
            self.player_eid,
            purpose="justice_identity_check",
            existing=context,
            notice_radius=self.PLAYER_IDENTITY_CHECK_NOTICE_RADIUS,
            capture_subject_account=True,
        )
        ai.investigation_context = context
        if contact == "visible":
            match_row = self._player_unresolved_identity_match()
            if self._identity_check_case_id(match_row) != incident_id:
                self._clear_identity_check_approach(enforcer_eid)
                return False
            player_pos = self._position_for(self.player_eid)
            enforcer_pos = self._position_for(enforcer_eid)
            if player_pos is None or enforcer_pos is None:
                self._clear_identity_check_approach(enforcer_eid)
                return False
            distance = _manhattan(enforcer_pos.x, enforcer_pos.y, player_pos.x, player_pos.y)
            if distance <= int(self.PLAYER_IDENTITY_CHECK_PROMPT_RADIUS):
                opened = bool(self._open_player_identity_check_prompt(enforcer_eid, match_row))
                if opened:
                    self._clear_identity_check_approach(enforcer_eid)
                return opened
        if target is None:
            self._clear_identity_check_approach(enforcer_eid)
            return False

        was_approaching = response_role == "identity_check"
        _sync_ai_intent(
            ai,
            will,
            self.sim.tick,
            "investigating",
            score=82.0,
            target=target,
            target_eid=None,
        )
        ai.incident_id = incident_id
        ai.response_role = "identity_check"
        if not was_approaching:
            observer_pos = self._position_for(enforcer_eid)
            player_pos = self._position_for(self.player_eid)
            distance = (
                _manhattan(observer_pos.x, observer_pos.y, player_pos.x, player_pos.y)
                if observer_pos is not None and player_pos is not None
                else 0
            )
            self.sim.emit(Event(
                "justice_identity_check_approach_started",
                npc_eid=enforcer_eid,
                eid=self.player_eid,
                incident_id=incident_id,
                distance=distance,
            ))
        return True

    def _advance_identity_check_approaches(self):
        records = self._identity_check_approach_records()
        if not records:
            return False
        handled = False
        for raw_eid in tuple(records):
            try:
                enforcer_eid = int(raw_eid)
            except (TypeError, ValueError):
                records.pop(raw_eid, None)
                continue
            handled = bool(self._advance_identity_check_approach(enforcer_eid)) or handled
        return handled

    def _process_guard_initiated_player_identity_check(self):
        if map_mode_active(self.sim):
            return False
        if self._player_surrender_prompt_open() or bool(self._dialog_ui_state().get("open", False)):
            return False
        if self._player_bookable_snapshot() is not None or _actor_in_live_combat(self.sim, self.player_eid):
            return False
        if self._advance_identity_check_approaches():
            return True
        tick = int(getattr(self.sim, "tick", 0))
        if tick < int(self._next_player_identity_check_tick):
            return False
        self._next_player_identity_check_tick = tick + int(self.PLAYER_IDENTITY_CHECK_SCAN_TICKS)

        # Most ticks have no nearby officer. Use the maintained local entity
        # index to prove there is a possible encounter before comparing the
        # player's current appearance against any unresolved case records.
        if self._find_identity_check_enforcer(None) is None:
            return False
        match_row = self._player_unresolved_identity_match()
        if match_row is None:
            return False
        enforcer_eid = self._find_identity_check_enforcer(match_row)
        if enforcer_eid is None:
            return False
        return self._start_identity_check_approach(enforcer_eid, match_row)

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
            remaining_paid = int(max(0, fine_paid))
            for case_id, case_read in dict(record.get("provisional_cases", {}) or {}).items():
                case_read = case_read if isinstance(case_read, dict) else {}
                case = justice_case_for_incident(self.sim, case_read.get("incident_id"))
                attribution = self._active_case_attribution_for(case, record.get("eid"))
                if not isinstance(attribution, dict):
                    continue
                wrongful_due = min(
                    int(max(0, record.get("fine_due", 0) or 0)),
                    int(max(0, case_read.get("wrongful_fine_due", 0) or 0)),
                )
                wrongful_paid = min(wrongful_due, remaining_paid)
                remaining_paid = max(0, remaining_paid - wrongful_paid)
                attribution["financial_outcome"] = {
                    "fine_due": int(max(0, record.get("fine_due", 0) or 0)),
                    "wrongful_fine_due": int(wrongful_due),
                    "fine_paid": int(wrongful_paid),
                    "debt_added": 0,
                    "hold_ticks_served": int(max(0, tick - int(record.get("start_tick", tick)))),
                    "booking_tick": int(record.get("start_tick", tick)),
                    "released_tick": int(tick),
                }
                residual = int(max(0, case_read.get("residual_active_contribution", 0) or 0))
                _set_provisional_justice_active_contribution(
                    self.sim,
                    record.get("eid"),
                    case_id,
                    residual,
                )
                change = attribution.get("justice_change") if isinstance(attribution.get("justice_change"), dict) else {}
                incident = change.get("incident") if isinstance(change.get("incident"), dict) else None
                if isinstance(incident, dict):
                    incident["active_contribution"] = residual
            self._clear_restitution_claims(int(record.get("eid", 0) or 0))

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
                restitution_due=int(record.get("restitution_due", 0) or 0),
                restitution_property_count=int(record.get("restitution_property_count", 0) or 0),
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
        if self._resume_deferred_player_contact():
            return
        if self._player_surrender_prompt_open() and self._player_bookable_snapshot() is None:
            self._close_player_surrender_prompt()
        if self._player_bookable_snapshot() is None:
            self._clear_player_surrender_offer_records()
        for change in _decay_justice_records(self.sim):
            self._emit_change_events(change, source_event="justice_decay", reason=str(change.get("reason", "cooldown")))
        scene_player_handled = self._process_scene_apprehensions()
        arrest_started = False if scene_player_handled else self._process_guard_initiated_player_arrest()
        if not arrest_started and not scene_player_handled:
            self._process_guard_initiated_player_identity_check()
        self._process_bounty_pickups()
        self._process_pending_detentions()
        self._process_resolved_npc_custody()
        self._process_pending_npc_exoneration_refunds()
        self._process_pending_npc_exoneration_memories()
