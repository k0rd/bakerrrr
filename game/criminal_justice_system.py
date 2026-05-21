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
from engine.events import Event
from game.items import (
    ITEM_CATALOG,
    apply_item_durability_loss,
    credstick_total_credits,
    is_credstick_item,
    item_display_name,
    merge_item_stack_metadata,
    prepare_item_stack_metadata,
)
from engine.systems import System
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
    _grant_custody_release_grace,
    _justice_booking_anchor_for,
    _justice_held_property_snapshot,
    _justice_restitution_snapshot,
    _justice_snapshot,
    _justice_summary_rows,
    _mark_justice_in_custody,
    _record_justice_booking_completion,
    _record_justice_incident,
    _record_justice_restitution_claim,
    _release_justice_from_custody,
    _replace_justice_held_property,
    _store_justice_held_property,
)
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
from game.system_support.awareness_runtime import _watchers_for_position
from game.player_businesses import (
    actor_player_business_employment,
    fire_actor_from_player_business,
    hire_actor_into_player_business,
    player_business_role_fit,
    player_business_staffing_targets,
)
from game.incident_runtime import incident_record
import random

THREAT_STATES = {"protecting", "investigating"}


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
        return int(max(base, min(240, round(base + (score * per_score)))) + restitution_due)

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
            "restitution_due": int(snapshot.get("restitution_due", 0) or 0),
            "restitution_property_count": int(snapshot.get("restitution_property_count", 0) or 0),
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
        restitution_due = int(snapshot.get("restitution_due", 0) or 0)
        restitution_property_count = int(snapshot.get("restitution_property_count", 0) or 0)
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
        _record_justice_booking_completion(
            self.sim,
            self.player_eid,
            property_id=(booking_prop or {}).get("id") if isinstance(booking_prop, dict) else None,
            property_name=(booking_prop or {}).get("name") if isinstance(booking_prop, dict) else None,
            hold_ticks=int(hold_ticks),
            fine_due=int(fine_due),
            fine_paid=int(fine_result.get("fine_paid", 0) or 0),
            debt_added=int(fine_result.get("debt_added", 0) or 0),
            seized_entries=tuple(confiscation.get("held_entries", ()) or ()) + tuple(confiscation.get("forfeited_entries", ()) or ()),
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
            before_score=int(snapshot.get("active_score", 0) or 0),
            after_score=int((release_change or {}).get("after_score", 0) or 0),
            fine_due=int(fine_due),
            restitution_due=int(restitution_due),
            restitution_property_count=int(restitution_property_count),
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
        if not witnessed:
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
        if not witnessed:
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
        if witnessed and isinstance(prop, dict):
            self._record_structural_restitution_claim(
                offender_eid,
                prop,
                damage_tick=int(getattr(self.sim, "tick", 0)),
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
        if self._player_surrender_prompt_open() and self._player_bookable_snapshot() is None:
            self._close_player_surrender_prompt()
        if self._player_bookable_snapshot() is None:
            self._clear_player_surrender_offer_records()
        for change in _decay_justice_records(self.sim):
            self._emit_change_events(change, source_event="justice_decay", reason=str(change.get("reason", "cooldown")))
        self._process_guard_initiated_player_arrest()
        self._process_pending_detentions()
        self._process_resolved_npc_custody()
