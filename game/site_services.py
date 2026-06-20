import random

from engine.events import Event
from engine.systems import System
from game.appearance_loadout import apply_appearance_service
from engine.underground import UNDERGROUND_ACCESS_SERVICE
from game.components import FinancialProfile, Inventory, NPCNeeds, PlayerAssets, Position, PropertyKnowledge, StatusEffects, VehicleState, Vitality
from game.items import ITEM_CATALOG, item_display_name
from game.opportunities import accept_service_job_offer, append_external_opportunity, opportunity_instruction_lines
from game.organization_response import property_vigilante_denial
from game.organizations import effective_org_access_posture, property_service_practice_bundle
from game.player_businesses import player_business_apply_remodel as _player_business_apply_remodel
from game.player_businesses import player_business_remodel_quote as _player_business_remodel_quote
from game.property_access import evaluate_property_access as _evaluate_property_access
from game.property_keys import can_receive_property_key, ensure_actor_has_property_key, ensure_property_lock
from game.property_runtime import (
    property_covering as _property_covering,
    property_is_vehicle as _property_is_vehicle,
    property_metadata as _property_metadata,
    property_power_cut_active as _property_power_cut_active,
    site_services_for_property as _site_services_for_property,
    vehicle_fuel_values as _vehicle_fuel_values,
    vehicle_label as _vehicle_label,
    vehicle_profile_from_property as _vehicle_profile_from_property,
)
from game.service_runtime import (
    CASINO_GAME_SERVICE_IDS,
    CASINO_PLINKO_LANE_COUNT,
    TRANSIT_SERVICE_IDS,
    _casino_apply_round_result,
    _casino_game_profile,
    _casino_plinko_resolve,
    _casino_round_seed,
    _casino_slots_resolve,
    _clamp,
    _int_or_default,
    _manhattan,
    _overworld_discovery_profile,
    _overworld_discovery_summary_bits,
    _overworld_legend_line,
    _overworld_travel_profile,
    _overworld_travel_summary_bits,
    _site_service_roll_index,
    _site_service_state,
    _transit_destinations as _shared_transit_destinations,
    _transit_payment_profile,
    _transit_service_profile,
    _transit_travel_ticks as _shared_transit_travel_ticks,
    _vehicle_sale_lookup_offer,
    _vehicle_sale_quality,
    _vehicle_sale_remove_offer,
)
from game.skills import (
    actor_skill as _actor_skill,
    intel_skill_terms as _intel_skill_terms,
    mobility_service_skill_terms as _mobility_service_skill_terms,
)
from game.system_support.building_repair_runtime import (
    owned_building_properties as _owned_building_properties,
    property_damage_summary as _property_damage_summary,
    repair_building_damage as _repair_building_damage,
)
from game.system_support.combat_targeting_runtime import QUIET_NOISE_CAUSES
from game.system_support.opportunity_knowledge_runtime import (
    rehydrate_entity_knowledge as _rehydrate_entity_knowledge,
)
from game.system_support.player_feedback import _log_player_feedback
from game.vehicles import vehicle_metadata


def _merge_practice_bundle(bundle, *, extra_modifiers=None, extra_note=""):
    bundle = dict(bundle or {})
    merged = dict(bundle.get("effect_modifiers", {}))
    for raw_key, raw_value in dict(extra_modifiers or {}).items():
        key = str(raw_key or "").strip().lower().replace(" ", "_")
        if not key:
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if key.endswith("_mult") or key.endswith("_scalar"):
            current = float(merged.get(key, 1.0))
            merged[key] = current * max(0.0, value)
        else:
            current = float(merged.get(key, 0.0))
            merged[key] = current + value
    notes = []
    for value in (bundle.get("note_text", ""), extra_note):
        text = str(value or "").strip()
        if text and text.lower() not in {note.lower() for note in notes}:
            notes.append(text)
    return {
        **bundle,
        "effect_modifiers": merged,
        "note_text": "; ".join(notes),
        "notes": tuple(notes),
    }


def _fixture_is_electronic(prop):
    """Return True when this property is an electronic fixture."""
    metadata = prop.get("metadata") or {} if isinstance(prop, dict) else {}
    fixture_kind = str(metadata.get("fixture_kind", "") or "").strip().lower()
    return fixture_kind in {"electronic", "electrical", "camera", "alarm"}


def _build_vending_item_pool():
    pool = []
    for item_id, item_def in ITEM_CATALOG.items():
        if not isinstance(item_def, dict):
            continue
        tags = {str(tag).strip().lower() for tag in item_def.get("tags", ()) if str(tag).strip()}
        if "consumable" not in tags:
            continue
        if str(item_def.get("legal_status", "legal")).strip().lower() != "legal":
            continue
        if "medical" in tags:
            continue
        if not tags.intersection({"food", "drink", "social", "energy"}):
            continue
        pool.append(str(item_id).strip().lower())
    return tuple(sorted(set(pool)))


VENDING_ITEM_POOL = _build_vending_item_pool()
RELAY_HIDDEN_CONTACT_LEAD_ITEMS = {
    "backroom_market": "backroom_card",
    "backroom_clinic": "clinic_scrap",
}


def _hidden_contact_lead_item_id(prop):
    metadata = _property_metadata(prop)
    archetype = str(metadata.get("archetype", "") or "").strip().lower()
    hidden_kind = str(metadata.get("hidden_contact_kind", "") or "").strip().lower()
    for key in (archetype, hidden_kind):
        if key in RELAY_HIDDEN_CONTACT_LEAD_ITEMS:
            return RELAY_HIDDEN_CONTACT_LEAD_ITEMS[key]
    return None


def _relay_watch_target_property(sim, prop):
    metadata = _property_metadata(prop)
    linked_property_id = str(metadata.get("linked_property_id", "") or "").strip()
    if not linked_property_id:
        return None
    target_prop = getattr(sim, "properties", {}).get(linked_property_id)
    if not isinstance(target_prop, dict):
        return None
    if str(target_prop.get("kind", "")).strip().lower() != "building":
        return None
    return target_prop


def _service_rehydrate_lead_kinds(service):
    service_key = str(service or "").strip().lower()
    if service_key in {"medical"}:
        return ("medical", "safe_spot")
    if service_key in {"rest", "shelter"}:
        return ("lodging", "local_housing", "safe_spot")
    return ()


def _default_live_timeskip_state():
    return {
        "active": False,
        "owner": "site_service",
        "kind": "",
        "service": "",
        "property_id": None,
        "property_name": "",
        "title": "",
        "footer": "",
        "started_tick": 0,
        "target_end_tick": 0,
        "elapsed_ticks": 0,
        "total_ticks": 0,
        "player_anchor": None,
        "recovery_plan": {"pulse_index": 0, "pulses": ()},
        "recovery_applied": {
            "hp_gain": 0,
            "energy_gain": 0,
            "safety_gain": 0,
            "social_gain": 0,
        },
        "planned_recovery": {
            "hp_gain": 0,
            "energy_gain": 0,
            "safety_gain": 0,
            "social_gain": 0,
        },
        "completed": False,
        "interrupted": False,
        "interruption_reason": "",
        "wake_cause": "",
        "wake_source_eid": None,
        "wake_x": None,
        "wake_y": None,
        "wake_z": None,
        "credits_spent": 0,
        "cooldown_ticks": 0,
        "well_rested_ticks": 0,
        "well_rested_granted": False,
        "practice_note": "",
        "source_status": "",
        "result_pending": False,
    }


def _split_total_across_pulses(total, pulse_count):
    total = max(0, int(total))
    pulse_count = max(1, int(pulse_count))
    base = total // pulse_count
    remainder = total % pulse_count
    return [base + (1 if idx < remainder else 0) for idx in range(pulse_count)]


class SiteServiceSystem(System):

    SHELTER_COOLDOWN_TICKS = 180
    SHELTER_STAY_HOURS = 6
    INTEL_COOLDOWN_TICKS = 45
    INTEL_RADIUS = 2
    FUEL_UNIT_PRICE = 3
    REPAIR_POINT_PRICE = 18
    VENDING_BASE_COST = 6
    REST_COST = 25
    REST_STAY_HOURS = 8
    REST_COOLDOWN_TICKS = 1800
    REST_WELL_RESTED_TICKS = 900
    FETCH_BASE_COST = 15
    FETCH_DISTANCE_MULT = 4
    FETCH_EMPTY_SURCHARGE = 20
    FETCH_DELIVERY_TICKS = 600
    RAIL_CITY_TOKEN_MAX_DISTANCE = 4

    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        if not hasattr(self.sim, "site_service_state"):
            self.sim.site_service_state = {
                "cooldowns": {},
            }
        if not hasattr(self.sim, "pending_vehicle_deliveries"):
            self.sim.pending_vehicle_deliveries = []
        if not isinstance(getattr(self.sim, "live_timeskip", None), dict):
            self.sim.live_timeskip = _default_live_timeskip_state()
        else:
            state = _default_live_timeskip_state()
            state.update(dict(getattr(self.sim, "live_timeskip", {}) or {}))
            self.sim.live_timeskip = state
        self.sim.events.subscribe("property_interact", self.on_property_interact)
        self.sim.events.subscribe("site_service_request", self.on_site_service_request)
        self.sim.events.subscribe("site_service_started", self.on_site_service_started)
        self.sim.events.subscribe("noise", self.on_noise)
        self.sim.events.subscribe("entity_damaged", self.on_entity_damaged)
        self.sim.events.subscribe("player_killed", self.on_player_killed)
        self.sim.events.subscribe("actor_detained", self.on_actor_detained)
        self.sim.events.subscribe("justice_booking_completed", self.on_justice_booking_completed)

    def _state(self):
        return _site_service_state(self.sim)

    def _live_timeskip_state(self):
        state = getattr(self.sim, "live_timeskip", None)
        if not isinstance(state, dict):
            state = _default_live_timeskip_state()
            self.sim.live_timeskip = state
        else:
            defaults = _default_live_timeskip_state()
            for key, value in defaults.items():
                state.setdefault(key, value if not isinstance(value, dict) else dict(value))
        return state

    def _reset_live_timeskip_state(self):
        state = self._live_timeskip_state()
        state.clear()
        state.update(_default_live_timeskip_state())
        return state

    def _current_player_position(self):
        return self.sim.ecs.get(Position).get(self.player_eid)

    def _live_timeskip_priority(self, reason):
        reason_key = str(reason or "").strip().lower()
        priorities = {
            "player_killed": 100,
            "justice_booking_completed": 90,
            "actor_detained": 85,
            "entity_damaged": 80,
            "justice_surrender": 70,
            "justice_questioning": 70,
            "woken_by_noise": 40,
        }
        return int(priorities.get(reason_key, 10))

    def _mark_live_timeskip_interruption(self, reason, *, wake_cause="", wake_source_eid=None, wake_x=None, wake_y=None, wake_z=None):
        state = self._live_timeskip_state()
        if not bool(state.get("active")) and not bool(state.get("result_pending")):
            return False
        reason_key = str(reason or "").strip().lower() or "interrupted"
        current_reason = str(state.get("interruption_reason", "") or "").strip().lower()
        if current_reason and self._live_timeskip_priority(current_reason) > self._live_timeskip_priority(reason_key):
            return False
        state["active"] = False
        state["completed"] = False
        state["interrupted"] = True
        state["interruption_reason"] = reason_key
        state["result_pending"] = True
        if wake_cause:
            state["wake_cause"] = str(wake_cause or "").strip().lower()
        if wake_source_eid is not None:
            state["wake_source_eid"] = wake_source_eid
        if wake_x is not None:
            state["wake_x"] = int(wake_x)
        if wake_y is not None:
            state["wake_y"] = int(wake_y)
        if wake_z is not None:
            state["wake_z"] = int(wake_z)
        return True

    def _mark_live_timeskip_complete(self):
        state = self._live_timeskip_state()
        if not bool(state.get("active")):
            return False
        state["active"] = False
        state["completed"] = True
        state["interrupted"] = False
        state["interruption_reason"] = ""
        state["result_pending"] = True
        return True

    def _lodging_recovery_pulses(self, *, total_ticks, hp_gain=0, energy_gain=0, safety_gain=0, social_gain=0):
        total_ticks = max(1, int(total_ticks))
        ticks_per_hour = self._ticks_per_hour()
        pulse_count = max(1, int((total_ticks + ticks_per_hour - 1) // ticks_per_hour))
        hp_parts = _split_total_across_pulses(hp_gain, pulse_count)
        energy_parts = _split_total_across_pulses(energy_gain, pulse_count)
        safety_parts = _split_total_across_pulses(safety_gain, pulse_count)
        social_parts = _split_total_across_pulses(social_gain, pulse_count)
        pulses = []
        for idx in range(pulse_count):
            pulse_tick = int(getattr(self.sim, "tick", 0)) + int(round((total_ticks * float(idx + 1)) / float(pulse_count)))
            pulses.append({
                "at_tick": pulse_tick,
                "hp_gain": int(hp_parts[idx]),
                "energy_gain": int(energy_parts[idx]),
                "safety_gain": int(safety_parts[idx]),
                "social_gain": int(social_parts[idx]),
            })
        return tuple(pulses)

    def _apply_live_timeskip_recovery_pulse(self, pulse):
        pulse = dict(pulse or {})
        state = self._live_timeskip_state()
        needs = self.sim.ecs.get(NPCNeeds).get(self.player_eid)
        vitality = self.sim.ecs.get(Vitality).get(self.player_eid)
        applied = state.get("recovery_applied", {})
        hp_gain = max(0, int(pulse.get("hp_gain", 0) or 0))
        energy_gain = max(0, int(pulse.get("energy_gain", 0) or 0))
        safety_gain = max(0, int(pulse.get("safety_gain", 0) or 0))
        social_gain = max(0, int(pulse.get("social_gain", 0) or 0))
        if needs:
            if energy_gain > 0:
                needs.energy = _clamp(float(needs.energy) + energy_gain)
            if safety_gain > 0:
                needs.safety = _clamp(float(needs.safety) + safety_gain)
            if social_gain > 0:
                needs.social = _clamp(float(needs.social) + social_gain)
        if vitality and hp_gain > 0:
            vitality.hp = min(int(vitality.max_hp), int(vitality.hp) + hp_gain)
        applied["hp_gain"] = int(applied.get("hp_gain", 0) or 0) + hp_gain
        applied["energy_gain"] = int(applied.get("energy_gain", 0) or 0) + energy_gain
        applied["safety_gain"] = int(applied.get("safety_gain", 0) or 0) + safety_gain
        applied["social_gain"] = int(applied.get("social_gain", 0) or 0) + social_gain
        state["recovery_applied"] = applied

    def _begin_live_lodging(
        self,
        *,
        eid,
        prop,
        service,
        stay_ticks,
        cooldown_ticks,
        hp_gain=0,
        energy_gain=0,
        safety_gain=0,
        social_gain=0,
        credits_spent=0,
        practice_note="",
        well_rested_ticks=0,
    ):
        pos = self._current_player_position()
        focus_x = None
        focus_y = None
        if pos is not None:
            focus_x = int(pos.x)
            focus_y = int(pos.y)
        elif isinstance(prop, dict):
            try:
                focus_x = int(prop.get("x", 0) or 0)
                focus_y = int(prop.get("y", 0) or 0)
            except (TypeError, ValueError):
                focus_x = None
                focus_y = None
        if focus_x is not None and focus_y is not None:
            self.sim.stream_world(focus_x, focus_y)
            self.sim.ensure_loaded_chunk_terrain()

        state = self._reset_live_timeskip_state()
        started_tick = int(getattr(self.sim, "tick", 0))
        pulses = self._lodging_recovery_pulses(
            total_ticks=stay_ticks,
            hp_gain=hp_gain,
            energy_gain=energy_gain,
            safety_gain=safety_gain,
            social_gain=social_gain,
        )
        state.update({
            "active": True,
            "owner": "site_service",
            "kind": "lodging",
            "service": str(service or "").strip().lower(),
            "property_id": prop.get("id"),
            "property_name": prop.get("name", prop.get("id", "site")),
            "title": "",
            "footer": "The city keeps moving without you.",
            "started_tick": started_tick,
            "target_end_tick": started_tick + max(1, int(stay_ticks)),
            "elapsed_ticks": 0,
            "total_ticks": max(1, int(stay_ticks)),
            "player_anchor": (int(pos.x), int(pos.y), int(pos.z)) if pos is not None else None,
            "recovery_plan": {
                "pulse_index": 0,
                "pulses": pulses,
            },
            "planned_recovery": {
                "hp_gain": int(hp_gain),
                "energy_gain": int(energy_gain),
                "safety_gain": int(safety_gain),
                "social_gain": int(social_gain),
            },
            "recovery_applied": {
                "hp_gain": 0,
                "energy_gain": 0,
                "safety_gain": 0,
                "social_gain": 0,
            },
            "completed": False,
            "interrupted": False,
            "interruption_reason": "",
            "wake_cause": "",
            "wake_source_eid": None,
            "wake_x": None,
            "wake_y": None,
            "wake_z": None,
            "credits_spent": int(credits_spent),
            "cooldown_ticks": int(cooldown_ticks),
            "well_rested_ticks": int(well_rested_ticks),
            "well_rested_granted": False,
            "practice_note": str(practice_note or "").strip(),
            "source_status": "",
            "result_pending": False,
        })
        self.sim.emit(Event(
            "site_service_started",
            eid=eid,
            property_id=prop.get("id"),
            property_name=prop.get("name", prop.get("id", "site")),
            service=service,
            time_advanced_ticks=int(stay_ticks),
            live_timeskip=True,
        ))
        return state

    def _live_timeskip_blocking_dialog_kind(self):
        dialog_state = getattr(self.sim, "dialog_ui", None)
        if not isinstance(dialog_state, dict) or not bool(dialog_state.get("open")):
            return ""
        kind = str(dialog_state.get("kind", "") or "").strip().lower()
        if kind in {"justice_surrender", "justice_questioning"}:
            return kind
        return ""

    def on_site_service_started(self, event):
        # Convenience seam for callers that need to react to live-lodging start.
        return None

    def on_noise(self, event):
        state = self._live_timeskip_state()
        if not bool(state.get("active")):
            return
        cause = str(event.data.get("cause", "") or "").strip().lower()
        if not cause or cause in QUIET_NOISE_CAUSES:
            return
        pos = self._current_player_position()
        if pos is None:
            return
        try:
            nx = int(event.data.get("x"))
            ny = int(event.data.get("y"))
            nz = int(event.data.get("z", pos.z))
            radius = max(1, int(event.data.get("radius", 0) or 0))
        except (TypeError, ValueError):
            return
        if int(pos.z) != nz:
            return
        distance = _manhattan(int(pos.x), int(pos.y), nx, ny)
        if distance > radius:
            return
        perception = _actor_skill(self.sim, self.player_eid, "perception")
        try:
            perception = float(perception)
        except (TypeError, ValueError):
            perception = 5.0
        cause_bonus = {
            "fire_weapon": 2.0,
            "gunshot": 2.0,
            "window_shot": 2.0,
            "fire": 1.5,
            "melee_attack": 0.75,
        }.get(cause, 0.5)
        effective_loudness = float(radius) + float(cause_bonus) - float(distance)
        wake_chance = _clamp(
            0.10 + (effective_loudness * 0.09) + ((perception - 5.0) * 0.04),
            0.0,
            0.95,
        )
        seed = (
            f"{getattr(self.sim, 'seed', 0)}:lodging-wake:{int(getattr(self.sim, 'tick', 0))}:"
            f"{state.get('service', '')}:{cause}:{nx}:{ny}:{nz}:{radius}"
        )
        if random.Random(seed).random() >= float(wake_chance):
            return
        self._mark_live_timeskip_interruption(
            "woken_by_noise",
            wake_cause=cause,
            wake_source_eid=event.data.get("source_eid"),
            wake_x=nx,
            wake_y=ny,
            wake_z=nz,
        )

    def on_entity_damaged(self, event):
        if event.data.get("target_eid") != self.player_eid:
            return
        self._mark_live_timeskip_interruption("entity_damaged")

    def on_player_killed(self, event):
        if event.data.get("target_eid") != self.player_eid:
            return
        self._mark_live_timeskip_interruption("player_killed")

    def on_actor_detained(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        self._mark_live_timeskip_interruption("actor_detained")

    def on_justice_booking_completed(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        self._mark_live_timeskip_interruption("justice_booking_completed")

    def after_live_timeskip_tick(self):
        state = self._live_timeskip_state()
        if not bool(state.get("active")) and not bool(state.get("result_pending")):
            return False
        started_tick = int(state.get("started_tick", 0) or 0)
        total_ticks = max(0, int(state.get("total_ticks", 0) or 0))
        elapsed = max(0, min(total_ticks, int(getattr(self.sim, "tick", 0)) - started_tick))
        state["elapsed_ticks"] = max(int(state.get("elapsed_ticks", 0) or 0), elapsed)
        if not bool(state.get("active")):
            return False
        dialog_kind = self._live_timeskip_blocking_dialog_kind()
        if dialog_kind:
            self._mark_live_timeskip_interruption(dialog_kind)
            return True
        if int(getattr(self.sim, "tick", 0)) >= int(state.get("target_end_tick", 0) or 0):
            self._mark_live_timeskip_complete()
            return True
        return False

    def finalize_live_timeskip_result_if_ready(self):
        state = self._live_timeskip_state()
        if not bool(state.get("result_pending")):
            return False
        if self._live_timeskip_blocking_dialog_kind():
            return False
        vitality = self.sim.ecs.get(Vitality).get(self.player_eid)
        if vitality and (bool(vitality.downed) or int(vitality.hp) <= 0):
            self._reset_live_timeskip_state()
            return False
        owner = str(state.get("owner", "site_service") or "site_service").strip().lower()
        kind = str(state.get("kind", "") or "").strip().lower()
        if owner == "altered_state" or kind == "drug_blackout":
            self.sim.emit(Event(
                "drug_blackout_resolved",
                eid=self.player_eid,
                source_status=str(state.get("source_status", "") or "").strip(),
                duration_ticks=int(state.get("total_ticks", 0) or 0),
                time_advanced_ticks=int(state.get("elapsed_ticks", 0) or 0),
                completed=bool(state.get("completed")),
                interrupted=bool(state.get("interrupted")),
                interruption_reason=str(state.get("interruption_reason", "") or "").strip().lower(),
                wake_cause=str(state.get("wake_cause", "") or "").strip().lower(),
            ))
            self._reset_live_timeskip_state()
            return True
        effects = self.sim.ecs.get(StatusEffects).get(self.player_eid)
        if bool(state.get("completed")) and str(state.get("service", "")).strip().lower() == "rest" and effects:
            effects.add(
                "well_rested",
                int(state.get("well_rested_ticks", self.REST_WELL_RESTED_TICKS) or self.REST_WELL_RESTED_TICKS),
                modifiers={
                    "perception_buff": 0.8,
                    "athletics_buff": 0.5,
                    "energy_tick_delta": 0.01,
                },
            )
            state["well_rested_granted"] = True

        pos = self._current_player_position()
        center = None
        if pos is None and state.get("player_anchor"):
            anchor = tuple(state.get("player_anchor") or ())
            if len(anchor) >= 3:
                center = (int(anchor[0]), int(anchor[1]), int(anchor[2]))
        _rehydrate_entity_knowledge(
            self.sim,
            self.player_eid,
            center=center,
            radius=20,
            search_radius=10,
            current_tick=int(getattr(self.sim, "tick", 0)),
            reason=f"service_{state.get('service', '')}",
            force_routine_rethink=True,
            lead_kinds=_service_rehydrate_lead_kinds(state.get("service", "")),
        )

        recovery = dict(state.get("recovery_applied", {}) or {})
        self.sim.emit(Event(
            "site_service_used",
            eid=self.player_eid,
            property_id=state.get("property_id"),
            property_name=state.get("property_name", state.get("property_id", "site")),
            service=state.get("service"),
            hp_gain=int(recovery.get("hp_gain", 0) or 0),
            energy_gain=int(recovery.get("energy_gain", 0) or 0),
            safety_gain=int(recovery.get("safety_gain", 0) or 0),
            social_gain=int(recovery.get("social_gain", 0) or 0),
            credits_spent=int(state.get("credits_spent", 0) or 0),
            cooldown_ticks=int(state.get("cooldown_ticks", 0) or 0),
            time_advanced_ticks=int(state.get("elapsed_ticks", 0) or 0),
            practice_note=str(state.get("practice_note", "") or "").strip(),
            completed=bool(state.get("completed")),
            interrupted=bool(state.get("interrupted")),
            interruption_reason=str(state.get("interruption_reason", "") or "").strip().lower(),
            wake_cause=str(state.get("wake_cause", "") or "").strip().lower(),
            well_rested_ticks=int(state.get("well_rested_ticks", 0) or 0),
            well_rested_granted=bool(state.get("well_rested_granted")),
        ))
        self._reset_live_timeskip_state()
        return True

    def _cooldown_key(self, eid, prop, service):
        return (int(eid), str(prop.get("id")), str(service).strip().lower())

    def _service_ready_in(self, eid, prop, service):
        cooldowns = self._state()["cooldowns"]
        ready_tick = int(cooldowns.get(self._cooldown_key(eid, prop, service), 0))
        return max(0, ready_tick - int(self.sim.tick))

    def _set_service_cooldown(self, eid, prop, service, duration):
        cooldowns = self._state()["cooldowns"]
        cooldowns[self._cooldown_key(eid, prop, service)] = int(self.sim.tick) + max(1, int(duration))

    def _relay_hidden_contact_awards(self):
        state = self._state()
        awards = state.get("relay_hidden_contact_awards")
        if not isinstance(awards, dict):
            awards = {}
            state["relay_hidden_contact_awards"] = awards
        return awards

    def _relay_opportunity_awards(self):
        state = self._state()
        awards = state.get("relay_opportunity_awards")
        if not isinstance(awards, dict):
            awards = {}
            state["relay_opportunity_awards"] = awards
        return awards

    def _next_service_roll_index(self, eid, prop, service):
        return _site_service_roll_index(self.sim, eid, prop, service)

    def _service_practice_bundle(self, eid, prop, service):
        bundle = property_service_practice_bundle(
            self.sim,
            prop,
            service,
            current_tick=getattr(self.sim, "tick", 0),
        )
        posture = effective_org_access_posture(
            self.sim,
            eid,
            prop,
            current_tick=getattr(self.sim, "tick", 0),
        )
        softness = float(posture.get("service_softness_bonus", 0.0) or 0.0)
        if softness <= 0.0:
            return bundle
        extra_modifiers = {
            "service_cost_mult": max(0.88, 1.0 - (softness * 0.28)),
            "service_cooldown_mult": max(0.9, 1.0 - (softness * 0.22)),
        }
        return _merge_practice_bundle(
            bundle,
            extra_modifiers=extra_modifiers,
            extra_note=str(posture.get("note_text", "") or "").strip(),
        )

    def _service_time_mult(self, modifiers):
        modifiers = modifiers if isinstance(modifiers, dict) else {}
        explicit = modifiers.get("service_time_mult")
        if explicit is not None:
            try:
                return max(0.4, min(2.5, float(explicit)))
            except (TypeError, ValueError):
                return 1.0
        try:
            speed = float(modifiers.get("service_speed_mult", 1.0) or 1.0)
        except (TypeError, ValueError):
            speed = 1.0
        if speed <= 0.0:
            return 1.0
        return max(0.4, min(2.5, 1.0 / speed))

    def _service_quality_mult(self, modifiers):
        modifiers = modifiers if isinstance(modifiers, dict) else {}
        try:
            quality_mult = float(modifiers.get("service_quality_mult", 1.0) or 1.0)
        except (TypeError, ValueError):
            quality_mult = 1.0
        try:
            quality_delta = float(modifiers.get("quality_delta", 0.0) or 0.0)
        except (TypeError, ValueError):
            quality_delta = 0.0
        return max(0.5, min(1.8, quality_mult + quality_delta))

    def _service_cost_mult(self, modifiers):
        modifiers = modifiers if isinstance(modifiers, dict) else {}
        try:
            value = float(modifiers.get("service_cost_mult", 1.0) or 1.0)
        except (TypeError, ValueError):
            value = 1.0
        return max(0.5, min(2.0, value))

    def _service_cooldown_mult(self, modifiers):
        modifiers = modifiers if isinstance(modifiers, dict) else {}
        try:
            value = float(modifiers.get("service_cooldown_mult", 1.0) or 1.0)
        except (TypeError, ValueError):
            value = 1.0
        return max(0.5, min(2.5, value))

    def _position_for(self, eid):
        return self.sim.ecs.get(Position).get(eid)

    def _assets_for(self, eid):
        return self.sim.ecs.get(PlayerAssets).get(eid)

    def _knowledge_for(self, eid):
        return self.sim.ecs.get(PropertyKnowledge).get(eid)

    def _finance_profile_for(self, eid):
        return self.sim.ecs.get(FinancialProfile).get(eid)

    def _inventory_for(self, eid):
        return self.sim.ecs.get(Inventory).get(eid)

    def _vehicle_state_for(self, eid):
        return self.sim.ecs.get(VehicleState).get(eid)

    def _service_destination(self, prop, service):
        metadata = _property_metadata(prop)
        destinations = metadata.get("site_service_destinations")
        if not isinstance(destinations, dict):
            return None
        destination = destinations.get(str(service or "").strip().lower())
        return dict(destination) if isinstance(destination, dict) else None

    def _linked_access_destination_available(self, destination):
        if not isinstance(destination, dict):
            return False
        try:
            dest_x = int(destination.get("x"))
            dest_y = int(destination.get("y"))
            dest_z = int(destination.get("z", 0))
        except (TypeError, ValueError):
            return False
        self.sim.stream_world(dest_x, dest_y)
        self.sim.ensure_loaded_chunk_terrain()
        tile = self.sim.tilemap.tile_at(dest_x, dest_y, dest_z)
        if tile and tile.walkable:
            return True
        return self._find_walkable_near(dest_x, dest_y, z=dest_z, radius=4) is not None

    def _underground_property_for_destination(self, x, y, z):
        prop = self.sim.property_at(x, y, z)
        if isinstance(prop, dict) and str(prop.get("kind", "")).strip().lower() == "building":
            return prop
        if isinstance(prop, dict):
            linked_property_id = str(_property_metadata(prop).get("linked_property_id", "") or "").strip()
            linked_prop = getattr(self.sim, "properties", {}).get(linked_property_id)
            if isinstance(linked_prop, dict) and str(linked_prop.get("kind", "")).strip().lower() == "building":
                return linked_prop
        covered = _property_covering(self.sim, x, y, z)
        if isinstance(covered, dict) and str(covered.get("kind", "")).strip().lower() == "building":
            return covered
        return None

    def _underground_destination_has_verified_return_path(self, x, y, z):
        underpass_prop = self._underground_property_for_destination(x, y, z)
        if not isinstance(underpass_prop, dict):
            return False
        underpass_id = str(underpass_prop.get("id", "") or "").strip()
        if not underpass_id:
            return False
        for candidate in tuple(getattr(self.sim, "properties", {}).values()):
            metadata = _property_metadata(candidate)
            if str(metadata.get("linked_property_id", "") or "").strip() != underpass_id:
                continue
            if str(metadata.get("fixture_type", "") or "").strip().lower() != "underpass_stairs":
                continue
            destination = self._service_destination(candidate, UNDERGROUND_ACCESS_SERVICE)
            if not isinstance(destination, dict):
                continue
            try:
                dest_z = int(destination.get("z", z))
            except (TypeError, ValueError):
                continue
            if dest_z < 0:
                continue
            if self._linked_access_destination_available(destination):
                return True
        return False

    def _allows_physical_service_interact(self, prop):
        if not isinstance(prop, dict):
            return False
        metadata = _property_metadata(prop)
        fixture_type = str(metadata.get("fixture_type", "") or "").strip().lower()
        if fixture_type not in {"underpass_stairs", "street_stairwell", "underpass_stairwell"}:
            return False
        services = {
            str(service).strip().lower()
            for service in tuple(_site_services_for_property(prop) or ())
            if str(service).strip()
        }
        return UNDERGROUND_ACCESS_SERVICE in services

    def _inventory_item_count(self, eid, item_id):
        inventory = self._inventory_for(eid)
        if not inventory:
            return 0
        item_id = str(item_id or "").strip().lower()
        if not item_id:
            return 0
        return sum(
            int(entry.get("quantity", 0) or 0)
            for entry in list(getattr(inventory, "items", ()) or ())
            if str(entry.get("item_id", "") or "").strip().lower() == item_id
        )

    def _consume_inventory_item(self, eid, item_id, quantity=1):
        inventory = self._inventory_for(eid)
        if not inventory:
            return None
        return inventory.remove_item(
            item_id=str(item_id or "").strip().lower(),
            quantity=max(1, int(quantity)),
        )

    def _liquid_credits_for(self, eid):
        assets = self._assets_for(eid)
        if assets is not None:
            return max(0, int(getattr(assets, "credits", 0) or 0))
        profile = self._finance_profile_for(eid)
        if profile is not None:
            return max(0, int(getattr(profile, "bank_balance", 0) or 0))
        return 0

    def _spend_liquid_credits(self, eid, amount):
        amount = max(0, int(amount))
        if amount <= 0:
            return True, 0
        assets = self._assets_for(eid)
        if assets is not None:
            credits = max(0, int(getattr(assets, "credits", 0) or 0))
            if credits < amount:
                return False, credits
            assets.credits = max(0, credits - amount)
            return True, int(assets.credits)
        profile = self._finance_profile_for(eid)
        if profile is not None:
            bank_balance = max(0, int(getattr(profile, "bank_balance", 0) or 0))
            if bank_balance < amount:
                return False, bank_balance
            profile.bank_balance = max(0, bank_balance - amount)
            return True, int(profile.bank_balance)
        return False, 0

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

    def _advance_time_for_service(self, eid, prop, service, ticks):
        ticks = max(0, int(ticks))
        if ticks <= 0:
            return 0

        prop_name = prop.get("name", prop.get("id", "site"))
        pos = self.sim.ecs.get(Position).get(eid)
        advanced_ticks = int(self.sim.advance_time(
            ticks,
            reason="site_service",
            eid=eid,
            property_id=prop.get("id"),
            property_name=prop_name,
            service=service,
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
        center = None
        if pos is None and isinstance(prop, dict):
            center = (
                int(prop.get("x", 0) or 0),
                int(prop.get("y", 0) or 0),
                int(prop.get("z", 0) or 0),
            )
        _rehydrate_entity_knowledge(
            self.sim,
            eid,
            center=center,
            radius=20,
            search_radius=10,
            current_tick=int(getattr(self.sim, "tick", 0)),
            reason=f"service_{service}",
            force_routine_rethink=True,
            lead_kinds=_service_rehydrate_lead_kinds(service),
        )
        return advanced_ticks

    def _choose_vending_item(self, eid, prop):
        if not VENDING_ITEM_POOL:
            return None
        roll_index = self._next_service_roll_index(eid, prop, "vending")
        seed_token = (
            f"vending:{int(getattr(self.sim, 'seed', 0) or 0)}:{int(eid)}:"
            f"{str(prop.get('id', 'fixture')).strip()}:{int(roll_index)}"
        )
        rng = random.Random(seed_token)
        item_id = VENDING_ITEM_POOL[rng.randrange(len(VENDING_ITEM_POOL))]
        return ITEM_CATALOG.get(item_id)

    def _vending_price_for(self, item_def):
        tags = {str(tag).strip().lower() for tag in item_def.get("tags", ()) if str(tag).strip()}
        price = int(self.VENDING_BASE_COST)
        if "food" in tags:
            price += 2
        if "drink" in tags:
            price += 1
        if "social" in tags:
            price += 1
        if "energy" in tags:
            price += 1
        return max(4, int(price))

    def _active_vehicle_property(self, eid, pos=None, radius=2):
        state = self._vehicle_state_for(eid)
        if state and state.active_vehicle_id:
            prop = self.sim.properties.get(state.active_vehicle_id)
            if _property_is_vehicle(prop):
                return prop

        if pos is None:
            return None

        best = None
        best_dist = 999999
        for prop in self.sim.properties_in_radius(pos.x, pos.y, pos.z, r=radius):
            if not _property_is_vehicle(prop):
                continue
            if prop.get("owner_eid") != eid and str(prop.get("owner_tag", "")).strip().lower() != "player":
                continue
            dist = _manhattan(pos.x, pos.y, int(prop.get("x", 0)), int(prop.get("y", 0)))
            if dist < best_dist:
                best = prop
                best_dist = dist
        if best and state:
            state.set_active_vehicle(best.get("id"), tick=self.sim.tick)
        return best

    def _vehicle_spawn_tile_near(self, x, y, z=0, radius=6):
        x = int(x)
        y = int(y)
        z = int(z)
        if (
            self.sim.tilemap.is_walkable(x, y, z)
            and self.sim.structure_at(x, y, z) is None
            and not self.sim.property_at(x, y, z)
        ):
            return x, y

        for r in range(1, max(1, int(radius)) + 1):
            for dy in range(-r, r + 1):
                for dx in range(-r, r + 1):
                    if max(abs(dx), abs(dy)) != r:
                        continue
                    nx = x + dx
                    ny = y + dy
                    if self.sim.detail_for_xy(nx, ny) == "unloaded":
                        continue
                    if self.sim.structure_at(nx, ny, z):
                        continue
                    if self.sim.property_at(nx, ny, z):
                        continue
                    if self.sim.tilemap.is_walkable(nx, ny, z):
                        return nx, ny
        return None

    def _find_walkable_near(self, x, y, z=0, radius=8):
        x = int(x)
        y = int(y)
        z = int(z)
        if self.sim.tilemap.is_walkable(x, y, z):
            return x, y
        for ring in range(1, max(1, int(radius)) + 1):
            for dy in range(-ring, ring + 1):
                for dx in range(-ring, ring + 1):
                    if abs(dx) != ring and abs(dy) != ring:
                        continue
                    nx = x + dx
                    ny = y + dy
                    if self.sim.detail_for_xy(nx, ny) == "unloaded":
                        continue
                    if self.sim.tilemap.is_walkable(nx, ny, z):
                        return nx, ny
        return x, y

    def _entry_front_cell(self, entry):
        if not isinstance(entry, dict):
            return None
        try:
            x = int(entry.get("x"))
            y = int(entry.get("y"))
            z = int(entry.get("z", 0))
        except (TypeError, ValueError):
            return None

        side = str(entry.get("side", "south") or "south").strip().lower() or "south"
        deltas = {
            "north": (0, -1),
            "south": (0, 1),
            "west": (-1, 0),
            "east": (1, 0),
        }
        dx, dy = deltas.get(side, (0, 1))
        return x + dx, y + dy, z

    def _transit_destination_property(self, destination):
        destination = destination if isinstance(destination, dict) else {}
        property_id = str(destination.get("property_id", "") or "").strip()
        if property_id:
            prop = self.sim.properties.get(property_id)
            if isinstance(prop, dict):
                return prop

        node_id = str(destination.get("node_id", "") or "").strip()
        building_id = str(destination.get("building_id", "") or "").strip()
        if not building_id and node_id.startswith("building:"):
            building_id = str(node_id.partition(":")[2] or "").strip()
        if building_id:
            for prop in tuple(self.sim.properties.values()):
                metadata = _property_metadata(prop)
                if str(metadata.get("building_id", "") or "").strip() == building_id:
                    return prop

        if not node_id.startswith("site:"):
            return None

        parts = node_id.split(":", 4)
        if len(parts) != 5:
            return None

        _prefix, chunk_x, chunk_y, site_kind, site_id = parts
        try:
            chunk = (int(chunk_x), int(chunk_y))
        except (TypeError, ValueError):
            return None

        site_kind = str(site_kind or "").strip().lower()
        site_id = str(site_id or "").strip()
        if not site_kind or not site_id:
            return None

        for prop in tuple(self.sim.properties.values()):
            metadata = _property_metadata(prop)
            if tuple(metadata.get("chunk", ()) or ()) != chunk:
                continue
            prop_site_kind = str(metadata.get("site_kind", metadata.get("archetype", "")) or "").strip().lower()
            if prop_site_kind != site_kind:
                continue
            if str(metadata.get("site_id", "") or "").strip() != site_id:
                continue
            return prop
        return None

    def _find_transit_landing_near(self, eid, x, y, z=0, radius=8, destination=None):
        x = int(x)
        y = int(y)
        z = int(z)
        radius = max(1, int(radius))

        destination_prop = self._transit_destination_property(destination)
        anchor_x = x
        anchor_y = y
        if isinstance(destination_prop, dict):
            entry = dict(_property_metadata(destination_prop).get("entry", {}) or {})
            front_cell = self._entry_front_cell(entry)
            if front_cell is not None:
                anchor_x = int(front_cell[0])
                anchor_y = int(front_cell[1])
                z = int(front_cell[2])

        best = None
        best_score = None
        for ring in range(0, radius + 1):
            for dy in range(-ring, ring + 1):
                for dx in range(-ring, ring + 1):
                    if ring and abs(dx) != ring and abs(dy) != ring:
                        continue
                    nx = anchor_x + dx
                    ny = anchor_y + dy
                    if self.sim.detail_for_xy(nx, ny) == "unloaded":
                        continue
                    if not self.sim.tilemap.is_walkable(nx, ny, z):
                        continue

                    covered = self.sim.property_covering(nx, ny, z)
                    covered_access = None
                    if covered is not None:
                        covered_access = _evaluate_property_access(self.sim, eid, covered, x=nx, y=ny, z=z)

                    destination_access = None
                    if destination_prop is not None:
                        destination_access = _evaluate_property_access(
                            self.sim,
                            eid,
                            destination_prop,
                            x=nx,
                            y=ny,
                            z=z,
                        )

                    severity_score = max(
                        int(getattr(covered_access, "severity_score", 0) or 0),
                        int(getattr(destination_access, "severity_score", 0) or 0),
                    )
                    inside_destination = bool(getattr(destination_access, "inside_bounds", False))
                    inside_cover = bool(getattr(covered_access, "inside_bounds", False))
                    occupied = any(
                        int(other_eid) != int(eid)
                        for other_eid in self.sim.tilemap.entities_at(nx, ny, z)
                    )
                    score = (
                        1 if severity_score > 0 else 0,
                        1 if inside_destination else 0,
                        1 if inside_cover else 0,
                        1 if self.sim.structure_at(nx, ny, z) is not None else 0,
                        1 if covered is not None else 0,
                        1 if occupied else 0,
                        severity_score,
                        _manhattan(anchor_x, anchor_y, nx, ny),
                        _manhattan(x, y, nx, ny),
                        int(ny),
                        int(nx),
                    )
                    if best_score is None or score < best_score:
                        best = (int(nx), int(ny))
                        best_score = score

        if best is not None:
            return best
        return self._find_walkable_near(x, y, z, radius=radius)

    def _move_entity(self, eid, pos, new_x, new_y, new_z, *, reason="site_service"):
        old_x = int(pos.x)
        old_y = int(pos.y)
        old_z = int(pos.z)
        new_x = int(new_x)
        new_y = int(new_y)
        new_z = int(new_z)
        if (old_x, old_y, old_z) == (new_x, new_y, new_z):
            return
        self.sim.tilemap.move_entity(
            eid,
            oldx=old_x,
            oldy=old_y,
            oldz=old_z,
            newx=new_x,
            newy=new_y,
            newz=new_z,
        )
        pos.x = new_x
        pos.y = new_y
        pos.z = new_z
        self.sim.emit(Event(
            "entity_moved",
            eid=eid,
            old_x=old_x,
            old_y=old_y,
            old_z=old_z,
            x=new_x,
            y=new_y,
            z=new_z,
            reason=str(reason or "site_service").strip().lower() or "site_service",
        ))

    def _world_streamer(self):
        for system in tuple(getattr(self.sim, "systems", ()) or ()):
            if hasattr(system, "_ensure_chunk_properties") and hasattr(system, "_ensure_chunk_population"):
                return system
        return None

    def _apply_fuel_service(self, eid, prop, pos):
        vehicle_prop = self._active_vehicle_property(eid, pos=pos, radius=2)
        if not vehicle_prop:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="fuel",
                reason="no_vehicle",
            ))
            return

        fuel, fuel_capacity = _vehicle_fuel_values(vehicle_prop)
        missing = max(0, fuel_capacity - fuel)
        if missing <= 0:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="fuel",
                reason="tank_full",
                vehicle_name=_vehicle_label(vehicle_prop),
                fuel=int(fuel),
                fuel_capacity=int(fuel_capacity),
            ))
            return

        profile = _vehicle_profile_from_property(vehicle_prop)
        fuel_efficiency = max(1, min(10, _int_or_default(profile.get("fuel_efficiency"), 5)))
        base_unit_price = max(1, int(round(float(self.FUEL_UNIT_PRICE) - (float(fuel_efficiency) * 0.12))))
        skill_terms = _mobility_service_skill_terms(self.sim, eid)
        unit_price = max(1, int(round(float(base_unit_price) * float(skill_terms.get("price_mult", 1.0)))))
        skill_note = str(skill_terms.get("note", "") or "").strip() if unit_price < base_unit_price else ""
        assets = self._assets_for(eid)
        credits = int(getattr(assets, "credits", 0)) if assets else 0
        affordable = min(missing, credits // unit_price if unit_price > 0 else 0)
        if affordable <= 0:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="fuel",
                reason="no_credits",
                cost=unit_price,
                credits=credits,
                vehicle_name=_vehicle_label(vehicle_prop),
                fuel=int(fuel),
                fuel_capacity=int(fuel_capacity),
            ))
            return

        credits_spent = int(affordable * unit_price)
        if assets:
            assets.credits = max(0, int(assets.credits) - credits_spent)

        metadata = _property_metadata(vehicle_prop)
        metadata["fuel"] = int(fuel + affordable)
        new_fuel, fuel_capacity = _vehicle_fuel_values(vehicle_prop)
        self.sim.emit(Event(
            "site_service_used",
            eid=eid,
            property_id=prop["id"],
            property_name=prop.get("name", prop["id"]),
            service="fuel",
            fuel_gain=int(affordable),
            base_unit_price=int(base_unit_price),
            unit_price=int(unit_price),
            base_credits_spent=int(affordable * base_unit_price),
            credits_spent=int(credits_spent),
            fuel=int(new_fuel),
            fuel_capacity=int(fuel_capacity),
            vehicle_id=vehicle_prop.get("id"),
            vehicle_name=_vehicle_label(vehicle_prop),
            skill_note=skill_note,
        ))

    def _apply_repair_service(self, eid, prop, pos):
        vehicle_prop = self._active_vehicle_property(eid, pos=pos, radius=2)
        if not vehicle_prop:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="repair",
                reason="no_vehicle",
            ))
            return

        profile = _vehicle_profile_from_property(vehicle_prop)
        durability = max(0, min(10, _int_or_default(profile.get("durability"), 5)))
        max_durability = 10
        missing = max(0, max_durability - durability)
        if missing <= 0:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="repair",
                reason="fully_repaired",
                vehicle_name=_vehicle_label(vehicle_prop),
                durability=int(durability),
                durability_max=int(max_durability),
            ))
            return

        power = max(1, min(10, _int_or_default(profile.get("power"), 5)))
        base_unit_price = max(8, int(self.REPAIR_POINT_PRICE) + max(0, int(power) - 4))
        practice = self._service_practice_bundle(eid, prop, "repair")
        practice_modifiers = dict(practice.get("effect_modifiers", {}))
        skill_terms = _mobility_service_skill_terms(self.sim, eid)
        price_mult = float(skill_terms.get("price_mult", 1.0)) * self._service_cost_mult(practice_modifiers)
        unit_price = max(1, int(round(float(base_unit_price) * price_mult)))
        skill_note = str(skill_terms.get("note", "") or "").strip() if unit_price < base_unit_price else ""
        practice_note = str(practice.get("note_text", "") or "").strip()
        assets = self._assets_for(eid)
        credits = int(getattr(assets, "credits", 0)) if assets else 0
        affordable = min(missing, credits // unit_price if unit_price > 0 else 0)
        if affordable <= 0:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="repair",
                reason="no_credits",
                cost=unit_price,
                credits=credits,
                vehicle_name=_vehicle_label(vehicle_prop),
                durability=int(durability),
                durability_max=int(max_durability),
            ))
            return

        credits_spent = int(affordable * unit_price)
        if assets:
            assets.credits = max(0, int(assets.credits) - credits_spent)

        metadata = _property_metadata(vehicle_prop)
        durability_gain = max(1, int(round(float(affordable) * self._service_quality_mult(practice_modifiers))))
        metadata["durability"] = int(min(max_durability, durability + durability_gain))
        metadata["vehicle_usable"] = True
        metadata["vehicle_broken"] = False
        new_durability = max(0, min(max_durability, _int_or_default(metadata.get("durability"), durability)))
        self.sim.emit(Event(
            "site_service_used",
            eid=eid,
            property_id=prop["id"],
            property_name=prop.get("name", prop["id"]),
            service="repair",
            durability_gain=int(durability_gain),
            durability_before=int(durability),
            durability=int(new_durability),
            durability_max=int(max_durability),
            base_unit_price=int(base_unit_price),
            unit_price=int(unit_price),
            base_credits_spent=int(affordable * base_unit_price),
            credits_spent=int(credits_spent),
            vehicle_id=vehicle_prop.get("id"),
            vehicle_name=_vehicle_label(vehicle_prop),
            skill_note=skill_note,
            practice_note=practice_note,
        ))

    def _owned_building_target(self, eid, target_property_id):
        target_property_id = str(target_property_id or "").strip()
        if not target_property_id:
            return None
        for owned_prop in _owned_building_properties(self.sim, eid):
            if str(owned_prop.get("id", "")).strip() == target_property_id:
                return owned_prop
        return None

    def _apply_building_repair_service(self, eid, prop, request=None):
        request = request if isinstance(request, dict) else {}
        target_property_id = str(request.get("target_property_id", "") or "").strip()
        target_prop = self._owned_building_target(eid, target_property_id)
        if not isinstance(target_prop, dict):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="building_repair",
                reason="invalid_target",
            ))
            return

        summary = _property_damage_summary(self.sim, target_prop)
        damage_count = int(summary.get("damage_count", 0) or 0)
        if damage_count <= 0:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="building_repair",
                reason="no_damage",
                target_property_id=target_prop.get("id"),
                target_property_name=target_prop.get("name", target_prop.get("id")),
            ))
            return

        practice = self._service_practice_bundle(eid, prop, "building_repair")
        practice_modifiers = dict(practice.get("effect_modifiers", {}))
        quoted_cost = int(round(int(summary.get("cost", 0) or 0) * self._service_cost_mult(practice_modifiers)))
        credits = self._liquid_credits_for(eid)
        if credits < quoted_cost:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="building_repair",
                reason="no_credits",
                cost=int(quoted_cost),
                credits=int(credits),
                target_property_id=target_prop.get("id"),
                target_property_name=target_prop.get("name", target_prop.get("id")),
                damage_count=damage_count,
            ))
            return

        spent, credits_after = self._spend_liquid_credits(eid, quoted_cost)
        if not spent:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="building_repair",
                reason="no_credits",
                cost=int(quoted_cost),
                credits=int(credits_after),
                target_property_id=target_prop.get("id"),
                target_property_name=target_prop.get("name", target_prop.get("id")),
                damage_count=damage_count,
            ))
            return

        repaired = _repair_building_damage(self.sim, target_prop)
        self.sim.emit(Event(
            "site_service_used",
            eid=eid,
            property_id=prop["id"],
            property_name=prop.get("name", prop["id"]),
            service="building_repair",
            target_property_id=target_prop.get("id"),
            target_property_name=target_prop.get("name", target_prop.get("id")),
            damage_count=int(repaired.get("damage_count", damage_count) or damage_count),
            restored_count=int(repaired.get("restored_count", damage_count) or damage_count),
            window_count=int(repaired.get("window_count", 0) or 0),
            door_count=int(repaired.get("door_count", 0) or 0),
            wall_count=int(repaired.get("wall_count", 0) or 0),
            credits_spent=int(quoted_cost),
            credits_after=int(credits_after),
            practice_note=str(practice.get("note_text", "") or "").strip(),
        ))

    def _apply_business_remodel_service(self, eid, prop, request=None):
        request = request if isinstance(request, dict) else {}
        target_property_id = str(request.get("target_property_id", "") or "").strip()
        target_archetype = str(request.get("target_archetype", "") or "").strip().lower()
        target_prop = self._owned_building_target(eid, target_property_id)
        if not isinstance(target_prop, dict):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="business_remodel",
                reason="invalid_target",
            ))
            return

        quote = _player_business_remodel_quote(target_prop, target_archetype)
        if not isinstance(quote, dict):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="business_remodel",
                reason="invalid_target",
                target_property_id=target_prop.get("id"),
                target_property_name=target_prop.get("name", target_prop.get("id")),
            ))
            return

        quoted_cost = int(quote.get("cost", 0) or 0)
        credits = self._liquid_credits_for(eid)
        if credits < quoted_cost:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="business_remodel",
                reason="no_credits",
                cost=int(quoted_cost),
                credits=int(credits),
                target_property_id=target_prop.get("id"),
                target_property_name=target_prop.get("name", target_prop.get("id")),
                target_archetype=str(quote.get("target_archetype", target_archetype)).strip().lower(),
                target_label=str(quote.get("target_label", target_archetype)).strip(),
            ))
            return

        spent, credits_after = self._spend_liquid_credits(eid, quoted_cost)
        if not spent:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="business_remodel",
                reason="no_credits",
                cost=int(quoted_cost),
                credits=int(credits_after),
                target_property_id=target_prop.get("id"),
                target_property_name=target_prop.get("name", target_prop.get("id")),
                target_archetype=str(quote.get("target_archetype", target_archetype)).strip().lower(),
                target_label=str(quote.get("target_label", target_archetype)).strip(),
            ))
            return

        remodel = _player_business_apply_remodel(self.sim, target_prop, target_archetype)
        if not isinstance(remodel, dict):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="business_remodel",
                reason="invalid_target",
                target_property_id=target_prop.get("id"),
                target_property_name=target_prop.get("name", target_prop.get("id")),
            ))
            return

        self.sim.emit(Event(
            "site_service_used",
            eid=eid,
            property_id=prop["id"],
            property_name=prop.get("name", prop["id"]),
            service="business_remodel",
            target_property_id=target_prop.get("id"),
            target_property_name=target_prop.get("name", target_prop.get("id")),
            target_archetype=str(remodel.get("target_archetype", target_archetype)).strip().lower(),
            target_label=str(remodel.get("target_label", target_archetype)).strip(),
            rarity_label=str(remodel.get("rarity_label", "")).strip(),
            credits_spent=int(quoted_cost),
            credits_after=int(credits_after),
            site_services=tuple(remodel.get("site_services", ()) or ()),
            finance_services=tuple(remodel.get("finance_services", ()) or ()),
        ))

    def _apply_vending_service(self, eid, prop):
        item_def = self._choose_vending_item(eid, prop)
        if not isinstance(item_def, dict):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="vending",
                reason="unavailable",
            ))
            return

        item_id = str(item_def.get("id", "")).strip().lower()
        item_name = item_display_name(item_id, item_catalog=ITEM_CATALOG)
        price = self._vending_price_for(item_def)
        assets = self._assets_for(eid)
        credits = int(getattr(assets, "credits", 0)) if assets else 0
        if credits < price:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="vending",
                reason="no_credits",
                cost=int(price),
                credits=int(credits),
                item_id=item_id,
                item_name=item_name,
            ))
            return

        inventory = self._inventory_for(eid)
        if inventory is None:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="vending",
                reason="inventory_full",
                item_id=item_id,
                item_name=item_name,
            ))
            return

        added, instance_id = inventory.add_item(
            item_id,
            quantity=1,
            stack_max=max(1, int(item_def.get("stack_max", 1))),
            instance_factory=getattr(self.sim, "new_item_instance_id", None),
            owner_eid=eid,
            owner_tag="player",
        )
        if not added:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="vending",
                reason="inventory_full",
                item_id=item_id,
                item_name=item_name,
            ))
            return

        if assets:
            assets.credits = max(0, int(assets.credits) - int(price))

        self.sim.emit(Event(
            "site_service_used",
            eid=eid,
            property_id=prop["id"],
            property_name=prop.get("name", prop["id"]),
            service="vending",
            item_id=item_id,
            item_name=item_name,
            instance_id=str(instance_id or "").strip(),
            credits_spent=int(price),
        ))

    def _apply_vehicle_sale(self, eid, prop, pos, quality, request=None):
        quality = _vehicle_sale_quality(quality)
        request = dict(request or {}) if isinstance(request, dict) else {}
        requested_offering_id = str(request.get("offering_id", "") or "").strip().lower()
        selected_offer = _vehicle_sale_lookup_offer(
            self.sim,
            prop,
            quality,
            offering_id=requested_offering_id,
        )
        if (
            not isinstance(selected_offer, dict)
            or (
                requested_offering_id
                and str(selected_offer.get("offering_id", "")).strip().lower() != requested_offering_id
            )
        ):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=f"vehicle_sales_{quality}",
                reason="unavailable",
            ))
            return

        base_price = int(max(80, _int_or_default(selected_offer.get("price"), 500)))
        skill_terms = _mobility_service_skill_terms(self.sim, eid)
        price = int(max(80, round(float(base_price) * float(skill_terms.get("price_mult", 1.0)))))
        skill_note = str(skill_terms.get("note", "") or "").strip() if price < base_price else ""

        assets = self._assets_for(eid)
        credits = int(getattr(assets, "credits", 0)) if assets else 0
        if credits < price:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=f"vehicle_sales_{quality}",
                reason="no_credits",
                cost=price,
                credits=credits,
            ))
            return

        spawn_tile = self._vehicle_spawn_tile_near(pos.x, pos.y, z=pos.z, radius=6)
        if not spawn_tile:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=f"vehicle_sales_{quality}",
                reason="no_space",
            ))
            return

        sx, sy = spawn_tile
        chunk_coord = self.sim.chunk_coords(sx, sy)
        vehicle_name = str(selected_offer.get("vehicle_name", "Vehicle")).strip() or "Vehicle"
        vehicle_token = (
            f"veh:purchase:{chunk_coord[0]}:{chunk_coord[1]}:{self.sim.tick}:{quality}:"
            f"{str(selected_offer.get('offering_id', 'offer')).strip() or 'offer'}"
        )
        profile = {
            "quality": quality,
            "paint": str(selected_offer.get("paint", "")).strip(),
            "make": str(selected_offer.get("make", "Unknown")).strip() or "Unknown",
            "model": str(selected_offer.get("model", "Vehicle")).strip() or "Vehicle",
            "vehicle_class": str(selected_offer.get("vehicle_class", "sedan")).strip().lower() or "sedan",
            "power": max(1, min(10, _int_or_default(selected_offer.get("power"), 5))),
            "durability": max(1, min(10, _int_or_default(selected_offer.get("durability"), 5))),
            "fuel_efficiency": max(1, min(10, _int_or_default(selected_offer.get("fuel_efficiency"), 5))),
            "fuel_capacity": max(10, _int_or_default(selected_offer.get("fuel_capacity"), 60)),
            "fuel": max(0, _int_or_default(selected_offer.get("fuel"), _int_or_default(selected_offer.get("fuel_capacity"), 60))),
            "price": price,
            "glyph": str(selected_offer.get("glyph", "&"))[:1] or "&",
        }
        metadata = vehicle_metadata(
            profile,
            chunk=chunk_coord,
            owner_tag="player",
            display_color=str(selected_offer.get("display_color", "")).strip() or "vehicle_player",
            locked=True,
            key_id=vehicle_token,
            key_label=vehicle_name,
            lock_tier=3 if quality == "new" else 2,
        )
        metadata["vehicle_id"] = vehicle_token
        preview_prop = {
            "id": vehicle_token,
            "name": vehicle_name,
            "kind": "vehicle",
            "metadata": metadata,
        }
        if not can_receive_property_key(self.sim, eid, preview_prop):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=f"vehicle_sales_{quality}",
                reason="key_storage_full",
            ))
            return
        vehicle_id = self.sim.register_property(
            name=vehicle_name,
            kind="vehicle",
            x=int(sx),
            y=int(sy),
            z=int(pos.z),
            owner_eid=eid,
            owner_tag="player",
            metadata=metadata,
        )
        self.sim.chunk_property_records.setdefault(chunk_coord, []).append({
            "id": vehicle_id,
            "kind": "vehicle",
            "x": int(sx),
            "y": int(sy),
            "z": int(pos.z),
            "archetype": "vehicle",
            "building_id": None,
        })
        vehicle_prop = self.sim.properties.get(vehicle_id)
        key_ok, _instance_id, _created = ensure_actor_has_property_key(self.sim, eid, vehicle_prop, owner_tag="player")
        if not key_ok and vehicle_prop:
            ensure_property_lock(vehicle_prop, locked=False)

        if assets:
            assets.credits = max(0, int(assets.credits) - int(price))
        _vehicle_sale_remove_offer(self.sim, prop, quality, selected_offer.get("offering_id"))
        vehicle_state = self._vehicle_state_for(eid)
        if vehicle_state and not vehicle_state.active_vehicle_id:
            vehicle_state.set_active_vehicle(vehicle_id, tick=self.sim.tick)

        self.sim.emit(Event(
            "site_service_used",
            eid=eid,
            property_id=prop["id"],
            property_name=prop.get("name", prop["id"]),
            service=f"vehicle_sales_{quality}",
            vehicle_id=vehicle_id,
            vehicle_name=vehicle_name,
            base_price=int(base_price),
            price=int(price),
            quality=quality,
            offering_id=str(selected_offer.get("offering_id", "")).strip(),
            vehicle_class=str(profile.get("vehicle_class", "sedan")).strip().lower() or "sedan",
            power=int(profile.get("power", 5)),
            durability=int(profile.get("durability", 5)),
            fuel_efficiency=int(profile.get("fuel_efficiency", 5)),
            fuel=int(profile.get("fuel", 0)),
            fuel_capacity=int(profile.get("fuel_capacity", 0)),
            key_issued=bool(key_ok),
            skill_note=skill_note,
        ))

    def _chunk_direction(self, from_chunk, to_chunk):
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

    def _choose_site_service(self, eid, prop):
        services = list(_site_services_for_property(prop))
        if not services:
            return None

        pos = self._position_for(eid)
        vehicle_prop = self._active_vehicle_property(eid, pos=pos, radius=2) if pos else None
        if "fuel" in services and vehicle_prop:
            fuel, fuel_capacity = _vehicle_fuel_values(vehicle_prop)
            if fuel < max(4, int(round(float(fuel_capacity) * 0.92))):
                return "fuel"
        if "repair" in services and vehicle_prop:
            durability = max(0, min(10, _int_or_default(_vehicle_profile_from_property(vehicle_prop).get("durability"), 5)))
            if durability < 9:
                return "repair"

        needs = self.sim.ecs.get(NPCNeeds).get(eid)
        vitality = self.sim.ecs.get(Vitality).get(eid)
        wants_shelter = False
        if needs:
            wants_shelter = (
                float(needs.energy) < 82.0
                or float(needs.safety) < 78.0
                or float(needs.social) < 52.0
            )
        if vitality and int(vitality.hp) < int(vitality.max_hp):
            wants_shelter = True

        if "vehicle_sales_new" in services:
            return "vehicle_sales_new"
        if "vehicle_sales_used" in services:
            return "vehicle_sales_used"
        if "rest" in services and wants_shelter:
            return "rest"
        if "shelter" in services and wants_shelter:
            return "shelter"
        if "vehicle_fetch" in services:
            return "vehicle_fetch"
        if "intel" in services:
            return "intel"
        if "fuel" in services and vehicle_prop:
            return "fuel"
        return services[0]

    def _apply_casino_game(self, eid, prop, service, request=None):
        service = str(service or "").strip().lower()
        profile = _casino_game_profile(service)
        if not profile:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=service,
                reason="unavailable",
            ))
            return

        raw_wager = 0 if not isinstance(request, dict) else request.get("wager", 0)
        try:
            wager = int(raw_wager)
        except (TypeError, ValueError):
            wager = 0
        valid_wagers = {int(amount) for amount in profile.get("bet_options", ())}
        if wager <= 0 or (valid_wagers and wager not in valid_wagers):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=service,
                reason="invalid_wager",
                wager=wager,
            ))
            return
        round_result = dict(request.get("round_result", {}) or {}) if isinstance(request, dict) else {}
        if not round_result:
            roll_index = self._next_service_roll_index(eid, prop, service)
            seed_token = _casino_round_seed(self.sim, eid, prop, service, wager, roll_index)
            if service == "slots":
                round_result = _casino_slots_resolve(seed_token, wager)
            elif service == "plinko":
                drop_lane = CASINO_PLINKO_LANE_COUNT // 2
                if isinstance(request, dict):
                    try:
                        drop_lane = int(request.get("drop_lane", drop_lane))
                    except (TypeError, ValueError):
                        drop_lane = CASINO_PLINKO_LANE_COUNT // 2
                round_result = _casino_plinko_resolve(seed_token, wager, drop_lane)
            else:
                self.sim.emit(Event(
                    "site_service_blocked",
                    eid=eid,
                    property_id=prop["id"],
                    property_name=prop.get("name", prop["id"]),
                    service=service,
                    reason="invalid_round",
                ))
                return

        payload, blocked = _casino_apply_round_result(self.sim, eid, prop, service, round_result)
        if blocked:
            self.sim.emit(Event("site_service_blocked", **blocked))
            return
        self.sim.emit(Event("site_service_used", **payload))

    def _run_site_service(self, eid, prop, pos, service, request=None):
        service = str(service or "").strip().lower()
        # Electronic fixtures are offline when their power supply is cut.
        if _fixture_is_electronic(prop) and _property_power_cut_active(self.sim, prop):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=service,
                reason="power_cut",
            ))
            _log_player_feedback(
                self.sim,
                f"The {prop.get('name', 'terminal')} is offline — power is out.",
                kind="interaction",
            )
            return True
        if service == UNDERGROUND_ACCESS_SERVICE:
            self._apply_linked_access_service(eid, prop, pos, service)
            return True
        if service == "shelter":
            self._apply_shelter(eid, prop)
            return True
        if service == "rest":
            self._apply_rest(eid, prop)
            return True
        if service == "intel":
            self._emit_intel(eid, prop, pos)
            return True
        if service in CASINO_GAME_SERVICE_IDS:
            self._apply_casino_game(eid, prop, service, request=request)
            return True
        if service == "vending":
            self._apply_vending_service(eid, prop)
            return True
        if service == "fuel":
            self._apply_fuel_service(eid, prop, pos)
            return True
        if service == "repair":
            self._apply_repair_service(eid, prop, pos)
            return True
        if service == "building_repair":
            self._apply_building_repair_service(eid, prop, request=request)
            return True
        if service == "business_remodel":
            self._apply_business_remodel_service(eid, prop, request=request)
            return True
        if service == "appearance_style":
            self._apply_appearance_style_service(eid, prop, request=request)
            return True
        if service in {"courier_jobs", "agency_jobs", "bounty_jobs"}:
            self._apply_service_job_board(eid, prop, service, request=request)
            return True
        if service in TRANSIT_SERVICE_IDS:
            self._apply_transit_service(eid, prop, pos, service, request=request)
            return True
        if service == "vehicle_sales_new":
            self._apply_vehicle_sale(eid, prop, pos, quality="new", request=request)
            return True
        if service == "vehicle_sales_used":
            self._apply_vehicle_sale(eid, prop, pos, quality="used", request=request)
            return True
        if service == "vehicle_fetch":
            self._apply_vehicle_fetch(eid, prop, pos)
            return True
        return False

    def _apply_service_job_board(self, eid, prop, service, request=None):
        request = request if isinstance(request, dict) else {}
        job_key = str(request.get("job_key", "") or "").strip()
        if not job_key:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=service,
                reason="no_job_selected",
            ))
            return False
        entry = accept_service_job_offer(self.sim, eid, prop, service, job_key, return_blocked=True)
        if isinstance(entry, dict) and bool(entry.get("blocked")):
            message = str(entry.get("message", "") or "That job posting is no longer available.").strip()
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=service,
                reason=str(entry.get("reason", "job_unavailable") or "job_unavailable").strip(),
                lines=(message,),
            ))
            return False
        if not isinstance(entry, dict):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=service,
                reason="job_unavailable",
            ))
            return False
        lines = list(opportunity_instruction_lines(self.sim, entry))
        if str(entry.get("kind", "")).strip().lower() == "bounty_capture":
            lines.append("A field restraint jab was issued. Use it on the downed or surrendered target.")
        if not lines:
            lines = [str(entry.get("summary", "Job accepted.")).strip() or "Job accepted."]
        self.sim.emit(Event(
            "site_service_used",
            eid=eid,
            property_id=prop["id"],
            property_name=prop.get("name", prop["id"]),
            service=service,
            headline="Job accepted.",
            lines=tuple(lines),
            opportunity_id=int(entry.get("id", 0) or 0),
            opportunity_key=str(entry.get("key", "") or "").strip(),
        ))
        return True

    def _apply_appearance_style_service(self, eid, prop, request=None):
        request = request if isinstance(request, dict) else {}
        style_kind = str(request.get("style_kind", "") or "").strip().lower()
        style_value = str(request.get("style_value", "") or "").strip().lower()
        result = apply_appearance_service(
            self.sim,
            eid,
            kind=style_kind,
            value=style_value,
            prop=prop,
        )
        if not bool(getattr(result, "ok", False)):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="appearance_style",
                reason=getattr(result, "reason", "invalid_style"),
            ))
            return False
        label = style_kind.replace("_", " ").title()
        value = style_value.replace("_", " ").title()
        self.sim.emit(Event(
            "site_service_used",
            eid=eid,
            property_id=prop["id"],
            property_name=prop.get("name", prop["id"]),
            service="appearance_style",
            headline="Styling updated.",
            lines=(f"{label}: {value}.", "Your character-sheet appearance has been updated."),
            style_kind=style_kind,
            style_value=style_value,
        ))
        return True

    def _apply_shelter(self, eid, prop):
        ready_in = self._service_ready_in(eid, prop, "shelter")
        if ready_in > 0:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="shelter",
                reason="cooldown",
                ready_in=ready_in,
            ))
            return

        needs = self.sim.ecs.get(NPCNeeds).get(eid)
        vitality = self.sim.ecs.get(Vitality).get(eid)
        energy_gain = safety_gain = social_gain = hp_gain = 0

        if needs:
            if float(needs.energy) < 95.0:
                energy_gain = min(18, max(4, int(round((100.0 - float(needs.energy)) * 0.32))))
            if float(needs.safety) < 92.0:
                safety_gain = min(14, max(3, int(round((100.0 - float(needs.safety)) * 0.24))))
            if float(needs.social) < 70.0:
                social_gain = min(8, max(2, int(round((72.0 - float(needs.social)) * 0.18))))

        if vitality and int(vitality.hp) < int(vitality.max_hp):
            hp_gain = min(2, int(vitality.max_hp) - int(vitality.hp))

        if energy_gain <= 0 and safety_gain <= 0 and social_gain <= 0 and hp_gain <= 0:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="shelter",
                reason="no_need",
            ))
            return

        self._set_service_cooldown(eid, prop, "shelter", self.SHELTER_COOLDOWN_TICKS)
        stay_ticks = self._hours_to_ticks(self.SHELTER_STAY_HOURS)
        self._begin_live_lodging(
            eid=eid,
            prop=prop,
            service="shelter",
            stay_ticks=stay_ticks,
            cooldown_ticks=self.SHELTER_COOLDOWN_TICKS,
            hp_gain=hp_gain,
            energy_gain=energy_gain,
            safety_gain=safety_gain,
            social_gain=social_gain,
        )

    def _apply_rest(self, eid, prop):
        ready_in = self._service_ready_in(eid, prop, "rest")
        if ready_in > 0:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="rest",
                reason="cooldown",
                ready_in=ready_in,
            ))
            return

        practice = self._service_practice_bundle(eid, prop, "rest")
        practice_modifiers = dict(practice.get("effect_modifiers", {}))
        practice_note = str(practice.get("note_text", "") or "").strip()
        rest_cost = max(1, int(round(float(self.REST_COST) * self._service_cost_mult(practice_modifiers))))
        assets = self._assets_for(eid)
        credits = int(getattr(assets, "credits", 0)) if assets else 0
        if credits < rest_cost:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="rest",
                reason="no_credits",
                cost=rest_cost,
                credits=credits,
            ))
            return

        needs = self.sim.ecs.get(NPCNeeds).get(eid)
        vitality = self.sim.ecs.get(Vitality).get(eid)
        energy_gain = safety_gain = social_gain = hp_gain = 0
        quality_mult = self._service_quality_mult(practice_modifiers)

        if needs:
            energy_gain = min(60, max(10, int(round(((100.0 - float(needs.energy)) * 0.7) * quality_mult))))
            safety_gain = min(45, max(8, int(round(((100.0 - float(needs.safety)) * 0.55) * quality_mult))))
            social_gain = min(18, max(3, int(round(((75.0 - float(needs.social)) * 0.25) * quality_mult))))

        if vitality:
            missing_hp = max(0, int(vitality.max_hp) - int(vitality.hp))
            hp_gain = min(missing_hp, max(5, int(round((missing_hp * 0.6) * quality_mult))))

        if assets:
            assets.credits = max(0, int(assets.credits) - int(rest_cost))

        cooldown_ticks = max(1, int(round(float(self.REST_COOLDOWN_TICKS) * self._service_cooldown_mult(practice_modifiers))))
        self._set_service_cooldown(eid, prop, "rest", cooldown_ticks)
        stay_ticks = max(1, int(round(float(self._hours_to_ticks(self.REST_STAY_HOURS)) * self._service_time_mult(practice_modifiers))))
        self._begin_live_lodging(
            eid=eid,
            prop=prop,
            service="rest",
            stay_ticks=stay_ticks,
            cooldown_ticks=cooldown_ticks,
            hp_gain=hp_gain,
            energy_gain=energy_gain,
            safety_gain=safety_gain,
            social_gain=social_gain,
            credits_spent=rest_cost,
            practice_note=practice_note,
            well_rested_ticks=self.REST_WELL_RESTED_TICKS,
        )

    def _transit_destinations(self, prop, service):
        service = str(service or "").strip().lower()
        if service not in TRANSIT_SERVICE_IDS:
            return ()
        return _shared_transit_destinations(self.sim, prop, service)

    def _transit_travel_ticks(self, service, distance):
        service = str(service or "").strip().lower()
        if service not in TRANSIT_SERVICE_IDS:
            service = "rail_transit"
        return _shared_transit_travel_ticks(self.sim, service, distance)

    def _apply_transit_service(self, eid, prop, pos, service, request=None):
        request = request if isinstance(request, dict) else {}
        service = str(service or "").strip().lower()
        profile = _transit_service_profile(service) or {}
        title = str(profile.get("title", service)).strip() or str(service or "Transit").replace("_", " ").title()
        vehicle_state = self._vehicle_state_for(eid)
        if vehicle_state and bool(getattr(vehicle_state, "in_vehicle", False)):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=service,
                reason="leave_vehicle",
            ))
            return

        destinations = list(self._transit_destinations(prop, service) or ())
        if not destinations:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=service,
                reason="no_destinations",
            ))
            return

        requested_chunk = request.get("destination_chunk")
        if isinstance(requested_chunk, (list, tuple)) and len(requested_chunk) >= 2:
            try:
                requested_chunk = (int(requested_chunk[0]), int(requested_chunk[1]))
            except (TypeError, ValueError):
                requested_chunk = None
        else:
            requested_chunk = None
        requested_node_id = str(request.get("destination_node_id", "") or "").strip()
        requested_building_id = str(request.get("destination_building_id", "") or "").strip()

        selected = None
        for destination in destinations:
            destination_node_id = str(destination.get("node_id", "") or "").strip()
            destination_chunk = tuple(destination.get("chunk", ()) or ())
            destination_building_id = str(destination.get("building_id", "") or "").strip()
            if requested_node_id and destination_node_id == requested_node_id:
                selected = destination
                break
            if requested_building_id and destination_building_id == requested_building_id:
                selected = destination
                break
            if requested_chunk and destination_chunk == requested_chunk:
                selected = destination
                break
        if not isinstance(selected, dict):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=service,
                reason="invalid_destination",
            ))
            return

        city_tokens = self._inventory_item_count(eid, "city_pass_token")
        daypasses = self._inventory_item_count(eid, "transit_daypass")
        skill_terms = _mobility_service_skill_terms(self.sim, eid)
        payment = _transit_payment_profile(
            service,
            selected.get("distance", 1),
            price_mult=skill_terms.get("price_mult", 1.0),
            city_tokens=city_tokens,
            daypasses=daypasses,
        )
        fare_mode = str(payment.get("fare_mode", "credits")).strip().lower() or "credits"
        token_cost = max(0, int(payment.get("token_cost", 0) or 0))
        assets = self._assets_for(eid)
        credits = int(getattr(assets, "credits", 0)) if assets else 0
        credits_spent = 0

        if fare_mode == "transit_daypass":
            self._consume_inventory_item(eid, "transit_daypass", quantity=1)
        elif fare_mode == "city_pass_token":
            if city_tokens < token_cost:
                self.sim.emit(Event(
                    "site_service_blocked",
                    eid=eid,
                    property_id=prop["id"],
                    property_name=prop.get("name", prop["id"]),
                    service=service,
                    reason="no_tokens",
                    token_cost=token_cost,
                    city_tokens=city_tokens,
                    daypasses=daypasses,
                    destination_name=selected.get("destination_name", selected.get("station_name", "")),
                ))
                return
            self._consume_inventory_item(eid, "city_pass_token", quantity=token_cost)
        else:
            fare_cost = int(payment.get("cost", 0) or 0)
            if credits < fare_cost:
                self.sim.emit(Event(
                    "site_service_blocked",
                    eid=eid,
                    property_id=prop["id"],
                    property_name=prop.get("name", prop["id"]),
                    service=service,
                    reason="no_credits",
                    cost=fare_cost,
                    credits=credits,
                    destination_name=selected.get("destination_name", selected.get("station_name", "")),
                ))
                return
            if assets:
                assets.credits = max(0, int(assets.credits) - fare_cost)
            credits_spent = fare_cost

        travel_ticks = self._transit_travel_ticks(service, selected.get("distance", 1))
        advanced_ticks = self._advance_time_for_service(eid, prop, service, travel_ticks)

        dest_x = int(selected.get("entry_x", pos.x))
        dest_y = int(selected.get("entry_y", pos.y))
        dest_z = int(selected.get("entry_z", 0))
        self.sim.stream_world(dest_x, dest_y)
        self.sim.ensure_loaded_chunk_terrain()
        landing_x, landing_y = self._find_transit_landing_near(
            eid,
            dest_x,
            dest_y,
            dest_z,
            radius=6,
            destination=selected,
        )
        self._move_entity(eid, pos, landing_x, landing_y, dest_z, reason=service)

        world_streamer = self._world_streamer()
        if world_streamer is not None:
            world_streamer.update()
            landing_x, landing_y = self._find_transit_landing_near(
                eid,
                dest_x,
                dest_y,
                dest_z,
                radius=6,
                destination=selected,
            )
            self._move_entity(eid, pos, landing_x, landing_y, dest_z, reason=service)

        skill_note = ""
        if fare_mode == "credits" and int(payment.get("base_cost", 0) or 0) > int(payment.get("cost", 0) or 0):
            skill_note = str(skill_terms.get("note", "") or "").strip()

        self.sim.emit(Event(
            "site_service_used",
            eid=eid,
            property_id=prop["id"],
            property_name=prop.get("name", prop["id"]),
            service=service,
            destination_name=str(selected.get("destination_name", selected.get("station_name", title))) or title,
            destination_chunk=tuple(selected.get("chunk", ()) or ()),
            destination_node_id=str(selected.get("node_id", "") or "").strip(),
            destination_building_id=str(selected.get("building_id", "") or "").strip(),
            distance=int(selected.get("distance", 0) or 0),
            fare_mode=fare_mode,
            credits_spent=int(credits_spent),
            token_cost=int(token_cost),
            base_credits_spent=int(payment.get("base_cost", 0) or 0),
            skill_note=skill_note,
            time_advanced_ticks=int(advanced_ticks),
        ))

    def _apply_linked_access_service(self, eid, prop, pos, service):
        service = str(service or "").strip().lower()
        destination = self._service_destination(prop, service)
        if not isinstance(destination, dict):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=service,
                reason="unavailable",
            ))
            return

        vehicle_state = self._vehicle_state_for(eid)
        if vehicle_state and bool(getattr(vehicle_state, "in_vehicle", False)):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=service,
                reason="leave_vehicle",
            ))
            return

        try:
            dest_x = int(destination.get("x", pos.x))
            dest_y = int(destination.get("y", pos.y))
            dest_z = int(destination.get("z", pos.z))
        except (TypeError, ValueError):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=service,
                reason="invalid_destination",
            ))
            return

        travel_ticks = max(0, int(destination.get("travel_ticks", 0) or 0))
        advanced_ticks = self._advance_time_for_service(eid, prop, service, travel_ticks) if travel_ticks > 0 else 0

        self.sim.stream_world(dest_x, dest_y)
        self.sim.ensure_loaded_chunk_terrain()
        landing_x, landing_y = dest_x, dest_y
        tile = self.sim.tilemap.tile_at(dest_x, dest_y, dest_z)
        if not tile or not tile.walkable:
            landing = self._find_walkable_near(dest_x, dest_y, z=dest_z, radius=4)
            if landing is None:
                self.sim.emit(Event(
                    "site_service_blocked",
                    eid=eid,
                    property_id=prop["id"],
                    property_name=prop.get("name", prop["id"]),
                    service=service,
                    reason="no_destination_tile",
                ))
                return
            landing_x, landing_y = landing

        if (
            service == UNDERGROUND_ACCESS_SERVICE
            and int(dest_z) < 0
            and not self._underground_destination_has_verified_return_path(landing_x, landing_y, dest_z)
        ):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=service,
                reason="no_return_path",
            ))
            return

        self._move_entity(eid, pos, landing_x, landing_y, dest_z, reason=service)

        world_streamer = self._world_streamer()
        if world_streamer is not None:
            world_streamer.update()

        self.sim.emit(Event(
            "site_service_used",
            eid=eid,
            property_id=prop["id"],
            property_name=prop.get("name", prop["id"]),
            service=service,
            destination_name=str(destination.get("destination_name", "the passage")).strip() or "the passage",
            destination_x=int(landing_x),
            destination_y=int(landing_y),
            destination_z=int(dest_z),
            time_advanced_ticks=int(advanced_ticks),
        ))

    def _apply_rail_transit(self, eid, prop, pos, request=None):
        self._apply_transit_service(eid, prop, pos, "rail_transit", request=request)

    def _player_vehicle_properties(self, eid):
        assets = self._assets_for(eid)
        if not assets:
            return []
        vehicles = []
        for pid in assets.owned_property_ids:
            prop = self.sim.properties.get(pid)
            if prop and _property_is_vehicle(prop):
                vehicles.append(prop)
        return vehicles

    def _apply_vehicle_fetch(self, eid, prop, pos):
        vehicles = self._player_vehicle_properties(eid)
        if not vehicles:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="vehicle_fetch",
                reason="no_vehicle",
            ))
            return

        player_chunk = self.sim.chunk_coords(pos.x, pos.y)
        best = None
        best_dist = -1
        for vp in vehicles:
            vx = int(vp.get("x", 0))
            vy = int(vp.get("y", 0))
            vc = self.sim.chunk_coords(vx, vy)
            dist = abs(vc[0] - player_chunk[0]) + abs(vc[1] - player_chunk[1])
            if dist > best_dist:
                best = vp
                best_dist = dist

        if best is None:
            return

        fuel, fuel_capacity = _vehicle_fuel_values(best)
        distance_cost = max(0, best_dist) * self.FETCH_DISTANCE_MULT
        empty_surcharge = self.FETCH_EMPTY_SURCHARGE if fuel <= 0 else 0
        base_total_cost = self.FETCH_BASE_COST + distance_cost + empty_surcharge
        skill_terms = _mobility_service_skill_terms(self.sim, eid)
        total_cost = max(1, int(round(float(base_total_cost) * float(skill_terms.get("price_mult", 1.0)))))
        skill_note = str(skill_terms.get("note", "") or "").strip() if total_cost < base_total_cost else ""

        assets = self._assets_for(eid)
        credits = int(getattr(assets, "credits", 0)) if assets else 0
        if credits < total_cost:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="vehicle_fetch",
                reason="no_credits",
                cost=total_cost,
                credits=credits,
                vehicle_name=_vehicle_label(best),
            ))
            return

        if assets:
            assets.credits = max(0, int(assets.credits) - int(total_cost))

        delivery_tick = int(self.sim.tick) + self.FETCH_DELIVERY_TICKS
        delivery = {
            "vehicle_id": best.get("id"),
            "vehicle_name": _vehicle_label(best),
            "eid": eid,
            "site_prop_id": prop.get("id"),
            "site_prop_name": prop.get("name", prop["id"]),
            "target_x": int(pos.x),
            "target_y": int(pos.y),
            "target_z": int(pos.z),
            "ready_at_tick": delivery_tick,
        }
        self.sim.pending_vehicle_deliveries.append(delivery)

        self.sim.emit(Event(
            "site_service_used",
            eid=eid,
            property_id=prop["id"],
            property_name=prop.get("name", prop["id"]),
            service="vehicle_fetch",
            vehicle_id=best.get("id"),
            vehicle_name=_vehicle_label(best),
            base_credits_spent=int(base_total_cost),
            credits_spent=total_cost,
            distance=best_dist,
            empty_surcharge=empty_surcharge,
            delivery_ticks=self.FETCH_DELIVERY_TICKS,
            skill_note=skill_note,
        ))

    def update(self):
        state = self._live_timeskip_state()
        if bool(state.get("result_pending")) and not bool(state.get("active")):
            self.finalize_live_timeskip_result_if_ready()
        if bool(state.get("active")):
            plan = state.get("recovery_plan", {}) if isinstance(state.get("recovery_plan"), dict) else {}
            pulses = tuple(plan.get("pulses", ()) or ())
            pulse_index = max(0, int(plan.get("pulse_index", 0) or 0))
            next_tick = int(getattr(self.sim, "tick", 0)) + 1
            while pulse_index < len(pulses):
                pulse = pulses[pulse_index] if isinstance(pulses[pulse_index], dict) else {}
                if next_tick < int(pulse.get("at_tick", 0) or 0):
                    break
                self._apply_live_timeskip_recovery_pulse(pulse)
                pulse_index += 1
            plan["pulse_index"] = pulse_index
            state["recovery_plan"] = plan

        deliveries = getattr(self.sim, "pending_vehicle_deliveries", None)
        if not deliveries:
            return
        completed = []
        for idx, delivery in enumerate(deliveries):
            if int(self.sim.tick) < int(delivery.get("ready_at_tick", 0)):
                continue
            vehicle_prop = self.sim.properties.get(delivery.get("vehicle_id"))
            if not vehicle_prop:
                completed.append(idx)
                continue
            tx = int(delivery.get("target_x", 0))
            ty = int(delivery.get("target_y", 0))
            tz = int(delivery.get("target_z", 0))
            spawn = self._vehicle_spawn_tile_near(tx, ty, z=tz, radius=8)
            if not spawn:
                spawn = (tx, ty)
            sx, sy = spawn
            moved = self.sim.move_property(vehicle_prop.get("id"), sx, sy, tz)
            if not moved:
                vehicle_prop["x"] = sx
                vehicle_prop["y"] = sy
                vehicle_prop["z"] = tz
                self.sim.rebuild_spatial_indexes()
            eid = delivery.get("eid")
            vehicle_state = self._vehicle_state_for(eid) if eid else None
            if vehicle_state and not vehicle_state.active_vehicle_id:
                vehicle_state.set_active_vehicle(vehicle_prop.get("id"), tick=self.sim.tick)
            self.sim.emit(Event(
                "vehicle_delivered",
                eid=eid,
                vehicle_id=vehicle_prop.get("id"),
                vehicle_name=delivery.get("vehicle_name", "vehicle"),
                site_prop_name=delivery.get("site_prop_name", "site"),
                x=sx,
                y=sy,
                z=tz,
            ))
            completed.append(idx)
        for idx in reversed(completed):
            deliveries.pop(idx)

    def _intel_lines(self, origin_chunk, *, radius=None, line_limit=4, detail_level=0):
        radius = max(1, int(self.INTEL_RADIUS if radius is None else radius))
        line_limit = max(1, int(line_limit))
        detail_level = max(0, int(detail_level))
        candidates = []
        ox, oy = origin_chunk
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                if dx == 0 and dy == 0:
                    continue
                dist = _manhattan(0, 0, dx, dy)
                if dist > radius:
                    continue

                cx = ox + dx
                cy = oy + dy
                desc = self.sim.world.overworld_descriptor(cx, cy)
                interest = self.sim.world.overworld_interest(cx, cy, descriptor=desc)
                landmark = desc.get("landmark") or {}
                landmark_name = str(landmark.get("name", "")).strip()
                interest_detail = str(interest.get("detail", "")).strip()
                path = str(desc.get("path", "")).strip()

                if not landmark_name and not interest_detail and not path:
                    continue

                area_type = str(desc.get("area_type", "city")).strip().lower() or "city"
                terrain = str(desc.get("terrain", area_type)).replace("_", " ").strip()
                score = int(interest.get("prominence", 0)) * 3
                if landmark_name:
                    score += 4
                if path:
                    score += 1

                bits = [
                    f"{self._chunk_direction(origin_chunk, (cx, cy))} {dist}c",
                    f"{area_type}/{terrain}",
                ]
                if path:
                    bits.append(f"path:{path}")
                if landmark_name:
                    bits.append(f"landmark:{landmark_name}")
                if interest_detail:
                    bits.append(f"poi:{interest_detail}")
                if detail_level >= 1:
                    bits.extend(_overworld_travel_summary_bits(_overworld_travel_profile(self.sim, cx, cy, desc=desc, interest=interest)))
                    bits.extend(_overworld_discovery_summary_bits(_overworld_discovery_profile(self.sim, cx, cy, desc=desc, interest=interest, travel=_overworld_travel_profile(self.sim, cx, cy, desc=desc, interest=interest))))
                if detail_level >= 2:
                    region_name = str(desc.get("region_name", "")).strip()
                    settlement_name = str(desc.get("settlement_name", "")).strip()
                    if region_name:
                        bits.append(f"region:{region_name}")
                    if settlement_name:
                        bits.append(f"city:{settlement_name}")

                text = " ".join(bit for bit in bits if bit)
                candidates.append((
                    -score,
                    dist,
                    cx,
                    cy,
                    _overworld_legend_line(self.sim, cx, cy, text),
                ))

        candidates.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
        return [row[4] for row in candidates[:line_limit]]

    def _relay_hidden_contact_candidate(self, eid, prop):
        if str(_property_metadata(prop).get("lead_mode", "") or "").strip().lower() != "hidden_contact_note":
            return None

        relay_id = str(prop.get("id", "") or "").strip()
        if not relay_id:
            return None
        if (int(eid), relay_id) in self._relay_hidden_contact_awards():
            return None

        knowledge = self._knowledge_for(eid)
        relay_chunk = self.sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
        relay_x = int(prop.get("x", 0))
        relay_y = int(prop.get("y", 0))
        candidates = []
        for candidate in getattr(self.sim, "properties", {}).values():
            if not isinstance(candidate, dict):
                continue
            candidate_id = str(candidate.get("id", "") or "").strip()
            if not candidate_id or candidate_id == relay_id:
                continue

            item_id = _hidden_contact_lead_item_id(candidate)
            if not item_id:
                continue

            metadata = _property_metadata(candidate)
            if not bool(metadata.get("is_storefront")):
                continue
            if not bool(metadata.get("dialogue_trade_only")):
                continue
            if bool(metadata.get("public", True)):
                continue
            if knowledge and candidate_id in knowledge.known:
                continue

            chunk = self.sim.chunk_coords(int(candidate.get("x", 0)), int(candidate.get("y", 0)))
            chunk_distance = abs(int(chunk[0]) - int(relay_chunk[0])) + abs(int(chunk[1]) - int(relay_chunk[1]))
            if chunk_distance > 6:
                continue
            tile_distance = _manhattan(relay_x, relay_y, int(candidate.get("x", 0)), int(candidate.get("y", 0)))
            candidates.append((
                chunk_distance,
                tile_distance,
                str(candidate.get("name", "") or "").strip().lower(),
                candidate_id,
                candidate,
                item_id,
            ))

        if not candidates:
            return None

        candidates.sort(key=lambda row: (row[0], row[1], row[2], row[3]))
        _chunk_distance, _tile_distance, _name, _candidate_id, target_prop, item_id = candidates[0]
        return target_prop, item_id

    def _grant_relay_hidden_contact_lead(self, eid, prop, pos):
        picked = self._relay_hidden_contact_candidate(eid, prop)
        if not picked:
            return None

        target_prop, item_id = picked
        item_def = ITEM_CATALOG.get(item_id, {}) if isinstance(ITEM_CATALOG.get(item_id), dict) else {}
        item_name = item_display_name(item_id, item_catalog=ITEM_CATALOG)
        target_metadata = _property_metadata(target_prop)
        metadata = {
            "source_property_id": str(target_prop.get("id", "") or "").strip(),
            "relay_property_id": str(prop.get("id", "") or "").strip(),
            "placement_zone": "relay_dead_drop",
            "hidden_contact_kind": (
                str(target_metadata.get("hidden_contact_kind", "") or "").strip().lower()
                or str(target_metadata.get("archetype", "") or "").strip().lower()
                or None
            ),
            "backroom_profile": str(target_metadata.get("backroom_profile", "") or "").strip().lower() or None,
            "covert_hint": str(target_metadata.get("covert_hint", "") or "").strip() or None,
        }

        delivery = None
        inventory = self._inventory_for(eid)
        if inventory is not None:
            added, _instance_id = inventory.add_item(
                item_id,
                quantity=1,
                stack_max=max(1, int(item_def.get("stack_max", 1) or 1)),
                instance_factory=getattr(self.sim, "new_item_instance_id", None),
                owner_eid=eid,
                owner_tag="player",
                metadata=metadata,
            )
            if added:
                delivery = "inventory"

        if delivery is None:
            ground_id = self.sim.register_ground_item(
                item_id=item_id,
                x=int(pos.x),
                y=int(pos.y),
                z=int(pos.z),
                quantity=1,
                owner_eid=None,
                owner_tag="city",
                metadata=metadata,
            )
            if not ground_id:
                return None
            delivery = "ground"

        self._relay_hidden_contact_awards()[(int(eid), str(prop.get("id", "") or "").strip())] = {
            "target_property_id": str(target_prop.get("id", "") or "").strip(),
            "item_id": item_id,
            "delivery": delivery,
            "tick": int(self.sim.tick),
        }
        return {
            "item_id": item_id,
            "item_name": item_name,
            "delivery": delivery,
            "target_property_id": str(target_prop.get("id", "") or "").strip(),
            "target_property_name": str(target_prop.get("name", target_prop.get("id", "hidden contact"))).strip() or "hidden contact",
        }

    def _relay_watch_key(self, prop):
        relay_id = str(prop.get("id", "") or "").strip()
        target_prop = _relay_watch_target_property(self.sim, prop)
        target_property_id = str((target_prop or {}).get("id", "") or "").strip()
        if not relay_id or not target_property_id:
            return ""
        return f"underground_relay_watch:{relay_id}:{target_property_id}"

    def _find_active_opportunity_by_key(self, key):
        key = str(key or "").strip().lower()
        if not key:
            return None
        state = getattr(self.sim, "world_traits", {}).get("opportunities", {})
        if not isinstance(state, dict):
            return None
        for entry in tuple(state.get("active", ()) or ()):
            if not isinstance(entry, dict):
                continue
            if str(entry.get("key", "") or "").strip().lower() == key:
                return entry
        return None

    def _grant_relay_opportunity_lead(self, eid, prop):
        if str(_property_metadata(prop).get("lead_mode", "") or "").strip().lower() != "hidden_contact_note":
            return None

        relay_id = str(prop.get("id", "") or "").strip()
        if not relay_id:
            return None
        if (int(eid), relay_id) in self._relay_opportunity_awards():
            return None

        target_prop = _relay_watch_target_property(self.sim, prop)
        if not isinstance(target_prop, dict):
            return None

        key = self._relay_watch_key(prop)
        if not key:
            return None

        existing = self._find_active_opportunity_by_key(key)
        if isinstance(existing, dict):
            self._relay_opportunity_awards()[(int(eid), relay_id)] = {
                "opportunity_id": int(existing.get("id", 0) or 0),
                "target_property_id": str(target_prop.get("id", "") or "").strip(),
                "tick": int(self.sim.tick),
            }
            return {
                "opportunity_id": int(existing.get("id", 0) or 0),
                "title": str(existing.get("title", "Relay Watch")).strip() or "Relay Watch",
                "property_id": str(target_prop.get("id", "") or "").strip(),
                "property_name": str(target_prop.get("name", target_prop.get("id", "underpass"))).strip() or "underpass",
            }

        try:
            chunk = self.sim.chunk_coords(int(target_prop.get("x", 0)), int(target_prop.get("y", 0)))
        except (TypeError, ValueError):
            return None
        relay_name = str(prop.get("name", "Signal Relay")).strip() or "Signal Relay"
        target_name = str(target_prop.get("name", target_prop.get("id", "underpass"))).strip() or "underpass"
        entry = append_external_opportunity(
            self.sim,
            {
                "key": key,
                "title": "Relay Watch",
                "summary": (
                    f"{relay_name} keeps catching repeat traffic through {target_name}. "
                    f"Hold a quiet watch there and sort the real pattern from the noise."
                ),
                "kind": "relay_watch",
                "source": "intel",
                "chunk": chunk,
                "location": "lead",
                "playstyles": ("stealth", "social", "economic"),
                "reward": {"credits": 8, "intel": 2},
                "risk": "low",
                "pressure": "low",
                "requirements": {
                    "visit_chunk": chunk,
                    "property_id": str(target_prop.get("id", "") or "").strip(),
                },
                "status": "active",
                "seed_tick": int(getattr(self.sim, "tick", 0)),
            },
            observer_eid=eid,
            awareness_state="heard",
            confidence=0.68,
            source="intel",
        )
        if not isinstance(entry, dict):
            return None

        self._relay_opportunity_awards()[(int(eid), relay_id)] = {
            "opportunity_id": int(entry.get("id", 0) or 0),
            "target_property_id": str(target_prop.get("id", "") or "").strip(),
            "tick": int(self.sim.tick),
        }
        return {
            "opportunity_id": int(entry.get("id", 0) or 0),
            "title": str(entry.get("title", "Relay Watch")).strip() or "Relay Watch",
            "property_id": str(target_prop.get("id", "") or "").strip(),
            "property_name": target_name,
        }

    def _emit_intel(self, eid, prop, pos):
        ready_in = self._service_ready_in(eid, prop, "intel")
        if ready_in > 0:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="intel",
                reason="cooldown",
                ready_in=ready_in,
            ))
            return

        origin_chunk = self.sim.chunk_coords(pos.x, pos.y)
        terms = _intel_skill_terms(self.sim, eid)
        radius = int(self.INTEL_RADIUS) + int(terms.get("radius_bonus", 0))
        line_limit = int(terms.get("line_limit", 4))
        detail_level = int(terms.get("detail_level", 0))
        lines = self._intel_lines(
            origin_chunk,
            radius=radius,
            line_limit=line_limit,
            detail_level=detail_level,
        )
        lead_reward = self._grant_relay_hidden_contact_lead(eid, prop, pos)
        opportunity_reward = self._grant_relay_opportunity_lead(eid, prop)
        if not lines and not lead_reward and not opportunity_reward:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service="intel",
                reason="no_leads",
            ))
            return

        self._set_service_cooldown(eid, prop, "intel", self.INTEL_COOLDOWN_TICKS)
        self.sim.emit(Event(
            "site_intel_report",
            eid=eid,
            property_id=prop["id"],
            property_name=prop.get("name", prop["id"]),
            service="intel",
            lines=lines,
            radius=radius,
            display_limit=line_limit,
            detail_level=detail_level,
            skill_note=str(terms.get("note", "") or "").strip(),
            lead_item_id=None if not lead_reward else lead_reward.get("item_id"),
            lead_item_name=None if not lead_reward else lead_reward.get("item_name"),
            lead_delivery=None if not lead_reward else lead_reward.get("delivery"),
            lead_property_id=None if not lead_reward else lead_reward.get("target_property_id"),
            lead_property_name=None if not lead_reward else lead_reward.get("target_property_name"),
            lead_opportunity_id=None if not opportunity_reward else opportunity_reward.get("opportunity_id"),
            lead_opportunity_title=None if not opportunity_reward else opportunity_reward.get("title"),
            lead_opportunity_property_id=None if not opportunity_reward else opportunity_reward.get("property_id"),
            lead_opportunity_property_name=None if not opportunity_reward else opportunity_reward.get("property_name"),
        ))

    def on_property_interact(self, event):
        eid = event.data.get("eid")
        if eid != self.player_eid:
            return
        if bool(event.data.get("handled")):
            return
        interaction_mode = str(event.data.get("interaction_mode", "") or "").strip().lower()
        prop = self.sim.properties.get(event.data.get("property_id"))
        if interaction_mode and interaction_mode != "service":
            if interaction_mode != "physical" or not self._allows_physical_service_interact(prop):
                return

        if not prop:
            return

        services = _site_services_for_property(prop)
        if not services:
            return

        pos = self._position_for(eid)
        if not pos:
            return

        access = _evaluate_property_access(
            self.sim,
            eid,
            prop,
            x=pos.x,
            y=pos.y,
            z=pos.z,
        )
        if not access.can_use_services:
            if access.organization_denied_service or access.organization_denied_entry:
                return
            return

        service = self._choose_site_service(eid, prop)
        event.data["opportunity_handoff_ready"] = True
        self._run_site_service(eid, prop, pos, service, request=event.data)

    def on_site_service_request(self, event):
        eid = event.data.get("eid")
        if eid is None:
            return

        prop = self.sim.properties.get(event.data.get("property_id"))
        service = str(event.data.get("service", "") or "").strip().lower()
        if not prop or service not in set(_site_services_for_property(prop)):
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=event.data.get("property_id"),
                property_name=str(event.data.get("property_name", "site") or "site"),
                service=service,
                reason="unavailable",
            ))
            return

        pos = self._position_for(eid)
        if not pos:
            return

        access = _evaluate_property_access(
            self.sim,
            eid,
            prop,
            x=pos.x,
            y=pos.y,
            z=pos.z,
        )
        if not access.can_use_services:
            if access.organization_denied_service or access.organization_denied_entry:
                denial = property_vigilante_denial(self.sim, prop, viewer_eid=eid)
                self.sim.emit(Event(
                    "site_service_blocked",
                    eid=eid,
                    property_id=prop["id"],
                    property_name=prop.get("name", prop["id"]),
                    service=service,
                    reason="organization_denial",
                    organization_key=(denial or {}).get("root_organization_key") or (denial or {}).get("organization_key"),
                    organization_name=(denial or {}).get("root_organization_name") or (denial or {}).get("organization_name"),
                    denial_reason=(denial or {}).get("reason") or access.organization_note,
                ))
                return
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=service,
                reason="unavailable",
            ))
            return

        denial = property_vigilante_denial(self.sim, prop, viewer_eid=eid)
        if denial is not None:
            self.sim.emit(Event(
                "site_service_blocked",
                eid=eid,
                property_id=prop["id"],
                property_name=prop.get("name", prop["id"]),
                service=service,
                reason="organization_denial",
                organization_key=denial.get("root_organization_key") or denial.get("organization_key"),
                organization_name=denial.get("root_organization_name") or denial.get("organization_name"),
                denial_reason=denial.get("reason"),
            ))
            return

        self._run_site_service(eid, prop, pos, service, request=event.data)


__all__ = ["SiteServiceSystem"]
