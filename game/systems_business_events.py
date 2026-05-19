"""Business-event runtime extracted from ``game/systems.py``.

This seam now carries both the business-event helper forest and the high-level
business pulse systems while ``game/systems.py`` remains the compatibility
facade for the rest of the project.
"""

import random

from engine.systems import System
from game.location_presentation_runtime import _location_building_category
from game.player_businesses import (
    player_business_customer_policy as _player_business_customer_policy,
    player_business_open_roles as _player_business_open_roles,
    player_business_summary as _player_business_summary,
)
from game.property_runtime import (
    building_id_from_property as _building_id_from_property,
    building_id_from_structure as _building_id_from_structure,
    clear_property_runtime_container_state as _clear_property_runtime_container_state,
    property_access_level as _property_access_level,
    property_is_public as _property_is_public,
    property_is_storefront as _property_is_storefront,
    property_metadata as _property_metadata,
    property_status_text as _property_status_text,
    property_runtime_container_entries as _property_runtime_container_entries,
)
from game.systems_business_reputation import property_business_reputation_snapshot, property_supports_business_reputation
from game.system_support.actor_runtime import _apply_downed_actor_state, _entity_is_downed
from game.system_support.ai_intent_runtime import _sync_ai_intent
from game.system_support.business_event_state import (
    _business_event_actor_note,
    _business_event_actor_state,
    _business_event_seed_state,
)
from game.system_support.entity_naming import _entity_display_name
from game import systems as _systems

_REQUIRED_SYSTEM_EXPORTS = (
    "AI",
    "INDUSTRIAL_ARCHETYPES",
    "ITEM_CATALOG",
    "MEDICAL_ARCHETYPES",
    "NIGHTLIFE_ARCHETYPES",
    "NPCNeeds",
    "NPCRoutine",
    "NPCSettlement",
    "NPCWill",
    "Occupation",
    "Position",
    "RESIDENTIAL_ARCHETYPES",
    "SALVAGE_ARCHETYPES",
    "STOREFRONT_ARCHETYPES",
    "StatusEffects",
    "TRANSIT_ARCHETYPES",
    "Vitality",
    "_NEWCOMER_LOCAL_CAP",
    "_active_business_scene_actor_ids",
    "_active_contractor_record",
    "_adjacent_street_tiles",
    "_business_event_chunk_population_target",
    "_business_scene_spillover_unsettled",
    "_chunk_entity_tallies",
    "_clamp",
    "_controller_access_requirement_text",
    "_dialogue_hours_text",
    "_give_item",
    "_is_business_scene_spillover",
    "_manhattan",
    "_organization_snapshot",
    "_property_access_controller",
    "_property_archetype",
    "_property_covering",
    "_property_focus_position",
    "_release_actor_to_newcomer",
    "_remember_property_lead_for_actor",
    "_spawn_human",
    "_world_hour",
    "actor_player_business_employment",
    "item_display_name",
    "organization_name",
    "property_organization_eid",
    "roll_vehicle_profile",
    "vehicle_metadata",
)

# These symbols are still defined in ``game.systems``. The import point in the
# monolith is intentionally placed after those helpers/constants exist.
globals().update({name: getattr(_systems, name) for name in _REQUIRED_SYSTEM_EXPORTS})


def _pick_property_roam_tile(*args, **kwargs):
    return _systems._pick_property_roam_tile(*args, **kwargs)
_BUSINESS_EVENT_SCENE_CAP = 1
_BUSINESS_EVENT_REGULAR_SCENE_CAP = 1
_BUSINESS_EVENT_RELEASE_CAP = _NEWCOMER_LOCAL_CAP + 1
_BUSINESS_EVENT_DELIVERY_PHASES = {
    "delivery_drop",
    "courier_stop",
    "supplier_drop",
    "delivery_run",
    "supply_run",
    "doorstep_drop",
    "takeout_arrival",
    "brief_pickup",
}
_BUSINESS_EVENT_QUEUE_PHASES = {
    "counter_queue",
    "crowd_spillover",
    "waiting_parties",
    "triage_spill",
    "last_call_spill",
    "visitor_screening",
    "booking_queue",
    "release_queue",
    "owner_screening",
}
_BUSINESS_EVENT_GATHERING_PHASES = {
    "paperwork_surge",
    "manifest_check",
    "regulars_spill",
    "grumbling_front",
}
_BUSINESS_EVENT_MEDICAL_RESPONSE_PHASES = {
    "street_triage",
}
_BUSINESS_EVENT_RESIDENTIAL_SOCIAL_PHASES = {
    "school_run",
    "neighbors_lingering",
}
_BUSINESS_EVENT_SETTLEMENT_PHASES = {
    "help_wanted_board",
    "clinic_outreach",
    "day_labor_call",
    "commuter_orientation",
    "tenant_meetup",
    "mutual_aid_table",
}
_BUSINESS_EVENT_HOSPITALITY_PRESSURE_PHASES = {
    "reset_scramble",
    "table_turnover",
    "barback_reset",
}
_BUSINESS_EVENT_OPERATIONAL_PRESSURE_PHASES = {
    "loading_push",
    "dispatch_surge",
    "boarding_crush",
    "arrival_handoff",
}
_BUSINESS_EVENT_AFTERMATH_PHASES = {
    "taped_off_front",
    "cleanup_detail",
    "candle_vigil",
}
_BUSINESS_EVENT_AFTERMATH_WITNESS_DELAY_HOURS = 24.0
_BUSINESS_EVENT_AFTERMATH_HAZARD_DELAY_HOURS = 0.18
_BUSINESS_EVENT_AFTERMATH_CLEANUP_HOURS = 48.0
_BUSINESS_EVENT_AFTERMATH_VIGIL_HOURS = 24.0
_BUSINESS_EVENT_AFTERMATH_CASUALTY_DURATION_HOURS = 72.0
_BUSINESS_EVENT_AFTERMATH_HAZARD_DURATION_HOURS = 6.0
_BUSINESS_EVENT_AFTERMATH_VIOLENCE_DURATION_HOURS = 60.0
_BUSINESS_EVENT_SHIFT_PHASES = {
    "staff_handoff",
    "shift_handoff",
    "shift_change",
    "gate_briefing",
    "chart_handoff",
    "quiet_handoff",
    "owner_closed_turnover",
    "guard_rotation",
    "custody_handoff",
    "maintenance_loop",
}
_BUSINESS_EVENT_RARE_PHASE_CHANCES = {
    "street_triage": 0.18,
}
_BUSINESS_EVENT_CROWD_FORWARD_PHASES = {
    "counter_queue",
    "crowd_spillover",
    "waiting_parties",
    "last_call_spill",
}
_BUSINESS_EVENT_BACKPRESSURE_PHASES = {
    "paperwork_surge",
    "shift_handoff",
    "reset_scramble",
    "table_turnover",
    "barback_reset",
    "courier_stop",
    "staff_handoff",
    "supplier_drop",
}
_BUSINESS_EVENT_REGULAR_CHUNK_HOURLY_CHANCE = 0.16
_BUSINESS_EVENT_SCENE_PROPERTY_COOLDOWN_HOURS = 4


def _business_event_scene_state(sim):
    state = getattr(sim, "business_event_scene_state", None)
    if isinstance(state, dict):
        state.setdefault("active", {})
        state.setdefault("cooldowns", {})
        return state
    state = {"active": {}, "cooldowns": {}}
    sim.business_event_scene_state = state
    return state


def _business_event_overrides(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        return {}
    overrides = traits.get("business_event_overrides")
    if isinstance(overrides, dict):
        return overrides
    return {}


def _business_event_regular_chunk_hourly_chance(sim):
    chance = _BUSINESS_EVENT_REGULAR_CHUNK_HOURLY_CHANCE
    overrides = _business_event_overrides(sim)
    if isinstance(overrides, dict) and "regular_chunk_hourly_chance" in overrides:
        try:
            chance = float(overrides.get("regular_chunk_hourly_chance", chance))
        except (TypeError, ValueError):
            chance = _BUSINESS_EVENT_REGULAR_CHUNK_HOURLY_CHANCE
    return max(0.0, min(1.0, float(chance)))


_BUILDING_PULSE_BUCKETS = 4


def _building_tick_snapshot(sim, *, bucket_count=_BUILDING_PULSE_BUCKETS):
    if sim is None:
        return {
            "ticks_per_hour": 600,
            "hour_tick": 0,
            "bucket": 0,
            "bucket_count": max(1, int(bucket_count)),
            "minute": 0,
        }

    world_traits = getattr(sim, "world_traits", {}) if sim is not None else {}
    clock = world_traits.get("clock", {}) if isinstance(world_traits, dict) else {}
    if not isinstance(clock, dict):
        clock = {}

    try:
        ticks_per_hour = int(clock.get("ticks_per_hour", 600))
    except (TypeError, ValueError):
        ticks_per_hour = 600
    ticks_per_hour = max(60, ticks_per_hour)

    bucket_count = max(1, int(bucket_count))
    tick = int(getattr(sim, "tick", 0) or 0)
    hour_tick = tick % ticks_per_hour
    bucket_span = max(1, ticks_per_hour // bucket_count)
    bucket = min(bucket_count - 1, hour_tick // bucket_span)
    minute = min(59, int((hour_tick * 60) / ticks_per_hour))
    return {
        "ticks_per_hour": ticks_per_hour,
        "hour_tick": hour_tick,
        "bucket": bucket,
        "bucket_count": bucket_count,
        "minute": minute,
    }


def _building_micro_event_pool(category, phase, *, open_now=False):
    category = str(category or "").strip().lower()
    phase = str(phase or "").strip().lower()
    if not phase or phase in {"after_hours", "locked_down", "quiet_hours", "quiet_interior"}:
        return ()

    if category in {"retail", "finance", "office"}:
        if phase == "opening":
            return (
                {
                    "phase": "delivery_drop",
                    "label": "delivery drop",
                    "street_label": "courier stop at the door",
                    "entry_sentence": "A delivery is briefly pulling motion toward the threshold and the back-room route behind it.",
                    "emphasis": "front",
                    "perimeter_bonus": 1.1,
                },
                {
                    "phase": "staff_handoff",
                    "label": "staff handoff",
                    "street_label": "staff cycling through the frontage",
                    "entry_sentence": "A short handoff is making the threshold feel busier than the customer side behind it.",
                    "emphasis": "admin",
                    "perimeter_bonus": 0.9,
                },
                {
                    "phase": "help_wanted_board",
                    "label": "help-wanted board",
                    "street_label": "job seekers checking a notice board",
                    "entry_sentence": "A small help-wanted knot has formed off the front, with people reading the posted shift needs before deciding whether to step in.",
                    "emphasis": "front",
                    "perimeter_bonus": 1.7,
                },
            )
        if phase == "rush":
            return (
                {
                    "phase": "counter_queue",
                    "label": "counter queue",
                    "street_label": "short line holding at the entrance",
                    "entry_sentence": "A short queue keeps forming and dissolving at the front, so the place feels like it is breathing in bursts instead of evenly.",
                    "emphasis": "front",
                    "perimeter_bonus": 2.1,
                },
                {
                    "phase": "courier_stop",
                    "label": "courier stop",
                    "street_label": "messenger traffic clipping the curb",
                    "entry_sentence": "A courier stop keeps interrupting the normal flow, pulling attention back toward the threshold every few minutes.",
                    "emphasis": "front",
                    "perimeter_bonus": 1.4,
                },
            )
        if phase in {"back_office", "steady_trade"}:
            return (
                {
                    "phase": "paperwork_surge",
                    "label": "paperwork surge",
                    "street_label": "front thinning while the back office catches up",
                    "entry_sentence": "The public rooms are quieter because a paperwork crunch is pulling more people deeper inside.",
                    "emphasis": "admin",
                    "perimeter_bonus": 0.1,
                },
                {
                    "phase": "shift_handoff",
                    "label": "shift handoff",
                    "street_label": "staff rotating through the frontage",
                    "entry_sentence": "A quick shift handoff is making the front edge feel more exposed than settled.",
                    "emphasis": "admin",
                    "perimeter_bonus": 1.0,
                },
            )

    if category in {"hospitality", "entertainment"}:
        if phase in {"prep", "cleanup"}:
            return (
                {
                    "phase": "supplier_drop",
                    "label": "supplier drop",
                    "street_label": "crates and carts near the service door",
                    "entry_sentence": "A supplier drop has the support loop briefly spilling out into public view.",
                    "emphasis": "work",
                    "perimeter_bonus": 0.8,
                },
                {
                    "phase": "reset_scramble",
                    "label": "reset scramble",
                    "street_label": "staff cutting hard between the front and the back",
                    "entry_sentence": "A reset scramble is keeping the place in short efficient loops rather than one smooth flow.",
                    "emphasis": "work",
                    "perimeter_bonus": 0.2,
                },
            )
        if phase in {"lunch_rush", "evening_crowd"}:
            return (
                {
                    "phase": "table_turnover",
                    "label": "table turnover",
                    "street_label": "staff threading hard through the front room",
                    "entry_sentence": "A turnover crunch is keeping the public rooms in constant motion, with barely any pause between one party and the next.",
                    "emphasis": "hospitality",
                    "perimeter_bonus": 0.3,
                },
                {
                    "phase": "crowd_spillover",
                    "label": "crowd spillover",
                    "street_label": "people bunching outside the door",
                    "entry_sentence": "A knot of people has started to spill back onto the sidewalk, making the place feel bigger than its footprint.",
                    "emphasis": "front",
                    "perimeter_bonus": 3.2,
                },
                {
                    "phase": "waiting_parties",
                    "label": "waiting parties",
                    "street_label": "small groups lingering just outside",
                    "entry_sentence": "Small waiting parties are collecting outside, turning the threshold into part of the room.",
                    "emphasis": "front",
                    "perimeter_bonus": 2.5,
                },
            )
        if phase == "late_buzz":
            return (
                {
                    "phase": "barback_reset",
                    "label": "barback reset",
                    "street_label": "staff shuttling between the door and the back",
                    "entry_sentence": "The late hour has compressed the motion here into short reset loops and quiet checks.",
                    "emphasis": "work",
                    "perimeter_bonus": 0.4,
                },
                {
                    "phase": "last_call_spill",
                    "label": "last-call spill",
                    "street_label": "slow exits and smokers outside",
                    "entry_sentence": "Last call is leaking onto the street in slow exits, smoke breaks, and people deciding whether they are really leaving.",
                    "emphasis": "front",
                    "perimeter_bonus": 3.4,
                },
            )

    if category in {"industrial", "transit"}:
        if phase == "receiving":
            return (
                {
                    "phase": "delivery_run",
                    "label": "delivery run",
                    "street_label": "truck-side handoffs at the curb",
                    "entry_sentence": "A delivery run has the site briefly organized around handoff rather than storage.",
                    "emphasis": "work",
                    "perimeter_bonus": 1.8,
                },
                {
                    "phase": "manifest_check",
                    "label": "manifest check",
                    "street_label": "crew pausing near the gate with clipboards",
                    "entry_sentence": "A manifest check has movement bunching near the edge of the site before it can spread deeper in.",
                    "emphasis": "admin",
                    "perimeter_bonus": 1.2,
                },
            )
        if phase in {"shift_work", "steady_ops"}:
            events = [
                {
                    "phase": "loading_push",
                    "label": "loading push",
                    "street_label": "freight moving in short bursts",
                    "entry_sentence": "A loading push is giving the place a start-stop tempo instead of a smooth hum.",
                    "emphasis": "work",
                    "perimeter_bonus": 0.8,
                },
                {
                    "phase": "dispatch_surge",
                    "label": "dispatch surge",
                    "street_label": "dispatch traffic clipping the frontage",
                    "entry_sentence": "A dispatch surge is briefly pulling operational attention back toward the edge of the site.",
                    "emphasis": "transit" if category == "transit" else "admin",
                    "perimeter_bonus": 1.1,
                },
            ]
            if category == "transit":
                events.append({
                    "phase": "boarding_crush",
                    "label": "boarding crush",
                    "street_label": "fares and boarding calls bunching at the stop",
                    "entry_sentence": "A boarding crush is turning the stop into a brief knot of fares, shouted destinations, and people trying not to miss the clean connection.",
                    "emphasis": "front",
                    "perimeter_bonus": 3.0,
                })
                events.append({
                    "phase": "commuter_orientation",
                    "label": "commuter orientation",
                    "street_label": "new arrivals sorting routes by the edge",
                    "entry_sentence": "A few new arrivals are sorting routes and work leads near the stop instead of committing to a direction yet.",
                    "emphasis": "transit",
                    "perimeter_bonus": 1.6,
                })
            else:
                events.append({
                    "phase": "day_labor_call",
                    "label": "day-labor call",
                    "street_label": "hands gathering around a crew list",
                    "entry_sentence": "A day-labor call is pulling loose workers toward the edge of the site, all names, short terms, and people hoping the shift sticks.",
                    "emphasis": "work",
                    "perimeter_bonus": 1.5,
                })
            return tuple(events)
        if phase == "handoff":
            events = [
                {
                    "phase": "shift_change",
                    "label": "shift change",
                    "street_label": "workers bunching near the entrance",
                    "entry_sentence": "A shift change has people collecting near the threshold longer than the building usually likes.",
                    "emphasis": "front",
                    "perimeter_bonus": 2.6,
                },
                {
                    "phase": "gate_briefing",
                    "label": "gate briefing",
                    "street_label": "supervisors stopping people just inside the gate",
                    "entry_sentence": "A quick gate briefing is turning the entrance into a temporary choke point.",
                    "emphasis": "admin",
                    "perimeter_bonus": 2.0,
                },
            ]
            if category == "transit":
                events.append({
                    "phase": "arrival_handoff",
                    "label": "arrival handoff",
                    "street_label": "incoming riders and pickups meeting at the edge",
                    "entry_sentence": "An arrival handoff is making the stop feel connected to somewhere farther out, with inbound riders, relief pickups, and quick onward directions all landing at once.",
                    "emphasis": "transit",
                    "perimeter_bonus": 2.4,
                })
            return tuple(events)

    if category == "medical":
        if phase == "intake":
            return (
                {
                    "phase": "triage_spill",
                    "label": "triage spill",
                    "street_label": "intake queue holding at the door",
                    "entry_sentence": "An intake queue is keeping more people near the threshold than the lobby was built to flatter.",
                    "emphasis": "front",
                    "perimeter_bonus": 2.2,
                },
                {
                    "phase": "chart_handoff",
                    "label": "chart handoff",
                    "street_label": "staff cutting brisk lines between desks",
                    "entry_sentence": "A chart handoff is pulling staff into short loops between the desk and the deeper rooms.",
                    "emphasis": "medical",
                    "perimeter_bonus": 0.6,
                },
                {
                    "phase": "clinic_outreach",
                    "label": "clinic outreach",
                    "street_label": "walk-ins checking in at an outreach table",
                    "entry_sentence": "An outreach table has made the front feel less like a door and more like a first safe stop for people trying to get steady.",
                    "emphasis": "medical",
                    "perimeter_bonus": 1.4,
                },
            )
        if phase in {"treatment", "night_watch"}:
            return (
                {
                    "phase": "supply_run",
                    "label": "supply run",
                    "street_label": "carts and staff slipping between doors",
                    "entry_sentence": "A supply run is briefly making the place feel more logistical than serene.",
                    "emphasis": "medical",
                    "perimeter_bonus": 0.4,
                },
                {
                    "phase": "quiet_handoff",
                    "label": "quiet handoff",
                    "street_label": "a subdued exchange near the front desk",
                    "entry_sentence": "A quiet handoff is briefly gathering staff near the front before they disappear deeper in again.",
                    "emphasis": "front",
                    "perimeter_bonus": 1.1,
                },
                {
                    "phase": "street_triage",
                    "label": "curbside triage",
                    "street_label": "medics stabilizing somebody outside",
                    "entry_sentence": "Emergency treatment has spilled right out to the threshold, where hurt bodies and clipped orders are suddenly visible from the street.",
                    "emphasis": "medical",
                    "perimeter_bonus": 1.8,
                },
            )

    if category == "secure":
        if phase == "intake":
            return (
                {
                    "phase": "visitor_screening",
                    "label": "visitor screening",
                    "street_label": "screening line bunching at the entrance",
                    "entry_sentence": "Visitor screening is briefly turning the front into a controlled queue.",
                    "emphasis": "front",
                    "perimeter_bonus": 2.4,
                },
                {
                    "phase": "booking_queue",
                    "label": "booking queue",
                    "street_label": "processing traffic holding near the desk",
                    "entry_sentence": "A booking queue is holding movement near the front longer than the building would like.",
                    "emphasis": "admin",
                    "perimeter_bonus": 1.9,
                },
            )
        if phase in {"controlled_ops", "night_watch"}:
            return (
                {
                    "phase": "guard_rotation",
                    "label": "guard rotation",
                    "street_label": "uniformed staff changing over by the gate",
                    "entry_sentence": "A guard rotation is briefly making the secure edge of the site more legible than usual.",
                    "emphasis": "admin",
                    "perimeter_bonus": 1.5,
                },
                {
                    "phase": "custody_handoff",
                    "label": "custody handoff",
                    "street_label": "staff clustering for a controlled handoff",
                    "entry_sentence": "A custody handoff has movement bunching where the building can keep eyes on all of it.",
                    "emphasis": "secure",
                    "perimeter_bonus": 1.3,
                },
            )
        if phase == "handoff":
            return (
                {
                    "phase": "custody_handoff",
                    "label": "custody handoff",
                    "street_label": "officers pausing at the secure threshold",
                    "entry_sentence": "A custody handoff is turning the entrance into a temporary checkpoint inside the checkpoint.",
                    "emphasis": "secure",
                    "perimeter_bonus": 2.1,
                },
                {
                    "phase": "release_queue",
                    "label": "release queue",
                    "street_label": "families and releases holding near the front",
                    "entry_sentence": "A release queue is making the building show more human traffic at the edge than it usually allows.",
                    "emphasis": "front",
                    "perimeter_bonus": 2.3,
                },
            )

    if category == "residential":
        if phase == "starting_day":
            return (
                {
                    "phase": "school_run",
                    "label": "school-run cluster",
                    "street_label": "families bunching at the stoop",
                    "entry_sentence": "For a few minutes the building is all keys, bags, and people trying not to be late.",
                    "emphasis": "front",
                    "perimeter_bonus": 1.6,
                },
                {
                    "phase": "doorstep_drop",
                    "label": "doorstep drop",
                    "street_label": "a courier hovering at the entrance",
                    "entry_sentence": "A doorstep drop has pulled attention back toward the entrance and whoever is hurrying to meet it.",
                    "emphasis": "front",
                    "perimeter_bonus": 1.1,
                },
            )
        if phase == "settled_evening":
            return (
                {
                    "phase": "neighbors_lingering",
                    "label": "neighbors lingering",
                    "street_label": "people talking just outside the entrance",
                    "entry_sentence": "The evening has spilled out to the threshold, where a few people are stretching conversation before heading in.",
                    "emphasis": "residential",
                    "perimeter_bonus": 1.5,
                },
                {
                    "phase": "takeout_arrival",
                    "label": "takeout arrival",
                    "street_label": "delivery arrivals at the curb",
                    "entry_sentence": "A takeout arrival is briefly making the front edge feel more social than private.",
                    "emphasis": "front",
                    "perimeter_bonus": 1.2,
                },
                {
                    "phase": "tenant_meetup",
                    "label": "tenant meetup",
                    "street_label": "a new tenant and neighbors comparing notes",
                    "entry_sentence": "A new tenant meetup has brought a few people down to the stoop, half introductions and half practical advice about the building.",
                    "emphasis": "residential",
                    "perimeter_bonus": 1.4,
                },
                {
                    "phase": "mutual_aid_table",
                    "label": "mutual aid table",
                    "street_label": "volunteers sharing supplies near the stoop",
                    "entry_sentence": "A small mutual aid table is making the frontage feel like a soft landing spot instead of a pass-through.",
                    "emphasis": "residential",
                    "perimeter_bonus": 1.6,
                },
            )

    if open_now or phase == "active_floor":
        return (
            {
                "phase": "brief_pickup",
                "label": "brief pickup stop",
                "street_label": "a short pickup lingering at the door",
                "entry_sentence": "A brief pickup is momentarily pulling activity back toward the entrance.",
                "emphasis": "front",
                "perimeter_bonus": 1.0,
            },
            {
                "phase": "maintenance_loop",
                "label": "maintenance loop",
                "street_label": "tools and staff slipping in and out",
                "entry_sentence": "A maintenance loop is making the place feel more improvised than settled.",
                "emphasis": "work",
                "perimeter_bonus": 0.6,
            },
            {
                "phase": "street_triage",
                "label": "street triage",
                "street_label": "someone being patched up near the entrance",
                "entry_sentence": "A sudden injury has turned the frontage into a rough treatment spot, with somebody working fast to keep a hurt person steady.",
                "emphasis": "front",
                "perimeter_bonus": 1.7,
            },
        )
    return ()


def _raw_building_micro_event_snapshot(sim, prop=None, structure=None, base_pulse=None):
    if sim is None:
        return {}

    prop = prop if isinstance(prop, dict) else None
    structure = structure if isinstance(structure, dict) else None
    base_pulse = base_pulse if isinstance(base_pulse, dict) else {}

    category = str(base_pulse.get("category", "") or "").strip().lower()
    phase = str(base_pulse.get("phase", "") or "").strip().lower()
    open_now = bool(base_pulse.get("open_now"))
    bucket = max(0, int(base_pulse.get("bucket", 0) or 0))
    hour = max(0, int(base_pulse.get("hour", 0) or 0))

    aftermath_event = _business_event_aftermath_micro_event(
        sim,
        prop=prop,
        structure=structure,
        base_pulse=base_pulse,
    )
    if isinstance(aftermath_event, dict) and str(aftermath_event.get("phase", "") or "").strip():
        return {
            "phase": str(aftermath_event.get("phase", "") or "").strip().lower(),
            "label": str(aftermath_event.get("label", "") or "").strip(),
            "street_label": str(aftermath_event.get("street_label", "") or "").strip(),
            "entry_sentence": str(aftermath_event.get("entry_sentence", "") or "").strip(),
            "emphasis": str(aftermath_event.get("emphasis", "") or "").strip().lower(),
            "perimeter_bonus": max(0.0, float(aftermath_event.get("perimeter_bonus", 0.0) or 0.0)),
        }
    player_business_event = _player_business_micro_event(
        sim,
        prop=prop,
        base_pulse=base_pulse,
    )
    if isinstance(player_business_event, dict) and str(player_business_event.get("phase", "") or "").strip():
        return {
            "phase": str(player_business_event.get("phase", "") or "").strip().lower(),
            "label": str(player_business_event.get("label", "") or "").strip(),
            "street_label": str(player_business_event.get("street_label", "") or "").strip(),
            "entry_sentence": str(player_business_event.get("entry_sentence", "") or "").strip(),
            "emphasis": str(player_business_event.get("emphasis", "") or "").strip().lower(),
            "perimeter_bonus": max(0.0, float(player_business_event.get("perimeter_bonus", 0.0) or 0.0)),
        }
    reputation_event = _business_reputation_micro_event(
        sim,
        prop=prop,
        base_pulse=base_pulse,
    )
    if isinstance(reputation_event, dict) and str(reputation_event.get("phase", "") or "").strip():
        return {
            "phase": str(reputation_event.get("phase", "") or "").strip().lower(),
            "label": str(reputation_event.get("label", "") or "").strip(),
            "street_label": str(reputation_event.get("street_label", "") or "").strip(),
            "entry_sentence": str(reputation_event.get("entry_sentence", "") or "").strip(),
            "emphasis": str(reputation_event.get("emphasis", "") or "").strip().lower(),
            "perimeter_bonus": max(0.0, float(reputation_event.get("perimeter_bonus", 0.0) or 0.0)),
        }
    events = list(_building_micro_event_pool(category, phase, open_now=open_now))
    if not events:
        return {}

    sceneable_events = []
    for event_item in events:
        if not isinstance(event_item, dict):
            continue
        event_phase = str(event_item.get("phase", "") or "").strip().lower()
        if _business_event_scene_blueprint(prop, {"event_phase": event_phase, "category": category}) is not None:
            sceneable_events.append(event_item)
    candidate_events = sceneable_events if sceneable_events else list(events)

    building_key = (
        _building_id_from_property(prop)
        or _building_id_from_structure(structure)
        or str((prop or {}).get("id", "") or "").strip()
    )
    seed = f"{getattr(sim, 'seed', 0)}:building-micro-event:{building_key}:{phase}:{hour}"
    rng = random.Random(seed)
    traffic_profile = _business_reputation_traffic_profile(sim, prop=prop, base_pulse=base_pulse)
    weighted_events = []
    has_bias = False
    if traffic_profile:
        for event_item in candidate_events:
            if not isinstance(event_item, dict):
                continue
            bias = float(_business_reputation_event_visibility_bias(event_item, traffic_profile) or 0.0)
            if abs(bias) > 1e-6:
                has_bias = True
            weight = max(0.05, 1.0 + bias)
            weighted_events.append((weight, event_item))
    if has_bias and weighted_events:
        total_weight = sum(max(0.0, float(weight)) for weight, _event_item in weighted_events)
        if total_weight > 0.0:
            pick = rng.random() * total_weight
            running = 0.0
            event = weighted_events[-1][1]
            for weight, event_item in weighted_events:
                running += max(0.0, float(weight))
                if pick <= running:
                    event = event_item
                    break
        else:
            event = rng.choice(candidate_events)
    else:
        event = rng.choice(candidate_events)
    if not isinstance(event, dict):
        return {}

    event_phase = str(event.get("phase", "") or "").strip().lower()
    if event_phase in _BUSINESS_EVENT_DELIVERY_PHASES:
        rarity_rng = random.Random(f"{getattr(sim, 'seed', 0)}:building-micro-event-rarity:{building_key}:{event_phase}:{hour}")
        if rarity_rng.random() > 0.35:
            return {}
    rare_phase_chance = _BUSINESS_EVENT_RARE_PHASE_CHANCES.get(event_phase)
    if rare_phase_chance is not None:
        rarity_rng = random.Random(f"{getattr(sim, 'seed', 0)}:building-micro-event-rarity:{building_key}:{event_phase}:{hour}")
        if rarity_rng.random() > float(rare_phase_chance):
            return {}

    outcome = {
        "phase": str(event.get("phase", "") or "").strip().lower(),
        "label": str(event.get("label", "") or "").strip(),
        "street_label": str(event.get("street_label", "") or "").strip(),
        "entry_sentence": str(event.get("entry_sentence", "") or "").strip(),
        "emphasis": str(event.get("emphasis", "") or "").strip().lower(),
        "perimeter_bonus": max(0.0, float(event.get("perimeter_bonus", 0.0) or 0.0)),
    }
    traffic_state = str(traffic_profile.get("state", "") or "").strip().lower()
    if traffic_state:
        outcome["traffic_state"] = traffic_state
        outcome["traffic_customer_delta"] = int(traffic_profile.get("customer_delta", 0) or 0)
    return outcome


def _building_regular_chunk_pulse_cache(sim):
    state = getattr(sim, "building_regular_chunk_pulse_cache", None)
    if not isinstance(state, dict):
        state = {}
        sim.building_regular_chunk_pulse_cache = state

    try:
        hour = int(_world_hour(sim)) % 24 if sim is not None else 0
    except (TypeError, ValueError):
        hour = 0
    token = (
        hour,
        len(getattr(sim, "properties", {}) or {}),
        int(_BUSINESS_EVENT_REGULAR_SCENE_CAP or 0),
    )
    if state.get("token") != token:
        state.clear()
        state["token"] = token
        state["winners"] = {}
    winners = state.get("winners")
    if not isinstance(winners, dict):
        winners = {}
        state["winners"] = winners
    return winners


def _player_business_scene_open_role_text(open_roles):
    roles = []
    for raw_role in tuple(open_roles or ()):
        role = str(raw_role or "").strip().lower()
        if role not in {"manager", "staff"} or role in roles:
            continue
        roles.append(role)
    if not roles:
        return ""
    if roles == ["manager"]:
        return "a manager"
    if roles == ["staff"]:
        return "more floor staff"
    return "a manager and more floor staff"


def _player_business_micro_event(sim, prop=None, base_pulse=None):
    if sim is None or not isinstance(prop, dict):
        return {}

    player_eid = getattr(sim, "player_eid", None)
    if player_eid is None:
        return {}
    owner_eid = prop.get("owner_eid")
    if owner_eid is None:
        return {}
    try:
        if int(owner_eid) != int(player_eid):
            return {}
    except (TypeError, ValueError):
        if owner_eid != player_eid:
            return {}

    if not (
        _property_is_storefront(prop)
        or _property_is_public(prop)
        or _property_access_level(prop) == "public"
    ):
        return {}

    summary = _player_business_summary(sim, prop)
    if not isinstance(summary, dict):
        return {}

    open_now = bool(summary.get("open_now")) if "open_now" in summary else bool((base_pulse or {}).get("open_now"))
    if not open_now:
        return {}

    customer_policy = str(summary.get("customer_policy", "") or _player_business_customer_policy(prop)).strip().lower() or "public"
    open_roles = tuple(_player_business_open_roles(sim, prop) or ())
    role_text = _player_business_scene_open_role_text(open_roles)
    staff_total = max(0, int(summary.get("staff_total", 0) or 0))
    note = str(summary.get("note", "") or "").strip().lower()

    if customer_policy == "closed" and staff_total > 0:
        return {
            "phase": "owner_closed_turnover",
            "label": "closed-door turnover",
            "street_label": "closed front, staff still turning the place over",
            "entry_sentence": "The business is closed to customers right now, but the frontage still shows a short internal turnover: staff slipping through, quick checks, and work that has not actually stopped.",
            "emphasis": "work",
            "perimeter_bonus": 1.65 if note in {"tight crew", "steady", "strong trade"} else 1.45,
        }

    if customer_policy == "staff_only":
        return {
            "phase": "owner_screening",
            "label": "screened entry",
            "street_label": "screened entry and short check-ins at the door",
            "entry_sentence": "The place is still doing business, but the front has tightened into a screened threshold where everyone gets sized up before they are let any deeper.",
            "emphasis": "front",
            "perimeter_bonus": 2.25,
        }

    if open_roles and customer_policy == "public":
        needed = role_text or "more help"
        return {
            "phase": "help_wanted_board",
            "label": "help wanted",
            "street_label": "job seekers bunching around a live hiring board",
            "entry_sentence": f"The owner has work posted out front because the floor still needs {needed}, and people are slowing down long enough to see whether the shift is real.",
            "emphasis": "front",
            "perimeter_bonus": 2.35 if "manager" in open_roles else 2.1,
        }

    return {}


def _business_reputation_micro_event(sim, prop=None, base_pulse=None):
    if sim is None or not isinstance(prop, dict):
        return {}
    if not property_supports_business_reputation(prop):
        return {}

    property_id = str(prop.get("id", "") or "").strip()
    if not property_id:
        return {}

    base_pulse = base_pulse if isinstance(base_pulse, dict) else {}
    if not bool(base_pulse.get("open_now")):
        return {}

    category = str(base_pulse.get("category", "") or "").strip().lower()
    if category in {"secure", "residential"}:
        return {}

    snapshot = property_business_reputation_snapshot(sim, property_id)
    awareness_count = max(0, int(snapshot.get("awareness_count", 0) or 0))
    if awareness_count < 3:
        return {}

    staple_score = float(snapshot.get("staple_score", 0.0) or 0.0)
    patronage_score = float(snapshot.get("patronage_score", 0.0) or 0.0)
    trouble_score = float(snapshot.get("trouble_score", 0.0) or 0.0)
    gouging_score = float(snapshot.get("gouging_score", 0.0) or 0.0)
    trust = float(snapshot.get("trust", 0.0) or 0.0)
    reliability = float(snapshot.get("reliability", 0.0) or 0.0)
    loyalty = float(snapshot.get("loyalty", 0.0) or 0.0)
    resentment = float(snapshot.get("resentment", 0.0) or 0.0)
    fear = float(snapshot.get("fear", 0.0) or 0.0)
    heat = float(snapshot.get("heat", 0.0) or 0.0)
    price_fairness = float(snapshot.get("price_fairness", 0.0) or 0.0)

    if (
        str(snapshot.get("reputation_state", "")).strip().lower() == "staple"
        and staple_score >= 0.39
        and patronage_score >= 0.37
    ):
        if category == "medical":
            street_label = "locals trusting the place enough to wait it out by the door"
            entry_sentence = (
                "People are lingering at the frontage because this is the kind of place the block actually trusts when something hurts or goes wrong."
            )
        elif category in {"hospitality", "entertainment"}:
            street_label = "regulars treating the frontage like part of the room"
            entry_sentence = (
                "A knot of regulars is hanging off the frontage because this place has started to feel like part of the neighborhood's ordinary rhythm."
            )
        else:
            street_label = "regulars bunching near the entrance without looking lost"
            entry_sentence = (
                "The same kinds of faces keep settling near the door because the place has built a reputation for actually coming through."
            )
        return {
            "phase": "regulars_spill",
            "label": "neighborhood staple",
            "street_label": street_label,
            "entry_sentence": entry_sentence,
            "emphasis": "front",
            "perimeter_bonus": 2.4 + min(1.2, (trust + reliability + loyalty) * 0.45),
            "reputation_state": "staple",
        }

    if (
        str(snapshot.get("reputation_state", "")).strip().lower() == "troubled"
        and (trouble_score >= 0.48 or gouging_score >= 0.46)
    ):
        if gouging_score >= max(0.46, trouble_score * 0.92) or resentment >= 0.36 or price_fairness <= -0.18:
            street_label = "people grumbling at the front about prices and whether it is still worth it"
            entry_sentence = (
                "A sour knot has formed near the door because enough people think the place has started charging harder than its reputation can cover."
            )
        elif heat >= 0.38 or fear >= 0.34:
            street_label = "a tense little knot holding just outside the door"
            entry_sentence = (
                "The frontage has that watchful, tense feel of a place people still use, but no longer trust without keeping one eye on the exit."
            )
        else:
            street_label = "customers and locals bunching into a grumbling doorstep knot"
            entry_sentence = (
                "Enough irritation has built up here that the frontage keeps turning into a short argument instead of a clean line."
            )
        return {
            "phase": "grumbling_front",
            "label": "front grumbling",
            "street_label": street_label,
            "entry_sentence": entry_sentence,
            "emphasis": "front",
            "perimeter_bonus": 1.9 + min(1.0, (resentment + heat + max(0.0, -price_fairness)) * 0.5),
            "reputation_state": "troubled",
        }

    return {}


def _business_reputation_traffic_profile(sim, prop=None, base_pulse=None):
    if sim is None or not isinstance(prop, dict):
        return {}
    if not property_supports_business_reputation(prop):
        return {}

    base_pulse = base_pulse if isinstance(base_pulse, dict) else {}
    if not bool(base_pulse.get("open_now")):
        return {}

    category = str(base_pulse.get("category", "") or "").strip().lower()
    if category not in {"retail", "finance", "office", "hospitality", "entertainment", "medical"}:
        return {}

    property_id = str(prop.get("id", "") or "").strip()
    if not property_id:
        return {}

    snapshot = property_business_reputation_snapshot(sim, property_id)
    awareness = max(
        float(snapshot.get("weighted_awareness", 0.0) or 0.0),
        float(int(snapshot.get("awareness_count", 0) or 0)),
    )
    if awareness < 2.0:
        return {}

    patronage = max(0.0, float(snapshot.get("patronage_score", 0.0) or 0.0))
    staple = max(0.0, float(snapshot.get("staple_score", 0.0) or 0.0))
    trouble = max(0.0, float(snapshot.get("trouble_score", 0.0) or 0.0))
    gouging = max(0.0, float(snapshot.get("gouging_score", 0.0) or 0.0))
    trust = max(0.0, float(snapshot.get("trust", 0.0) or 0.0))
    reliability = max(0.0, float(snapshot.get("reliability", 0.0) or 0.0))
    loyalty = max(0.0, float(snapshot.get("loyalty", 0.0) or 0.0))
    fear = max(0.0, float(snapshot.get("fear", 0.0) or 0.0))
    heat = max(0.0, float(snapshot.get("heat", 0.0) or 0.0))
    resentment = max(0.0, float(snapshot.get("resentment", 0.0) or 0.0))
    price_fairness = float(snapshot.get("price_fairness", 0.0) or 0.0)
    price_good = max(0.0, price_fairness)
    price_pain = max(0.0, -price_fairness)

    positive_pressure = max(
        0.0,
        (patronage * 0.74)
        + (staple * 0.18)
        + (trust * 0.08)
        + (reliability * 0.08)
        + (loyalty * 0.08)
        + (price_good * 0.06)
        - (trouble * 0.24)
        - (gouging * 0.18)
        - (fear * 0.14),
    )
    negative_pressure = max(
        0.0,
        (trouble * 0.56)
        + (gouging * 0.34)
        + (resentment * 0.08)
        + (heat * 0.08)
        + (fear * 0.08)
        + (price_pain * 0.16)
        - (patronage * 0.22)
        - (trust * 0.1)
        - (reliability * 0.06),
    )
    if positive_pressure < 0.26 and negative_pressure < 0.24:
        return {}

    state = ""
    customer_delta = 0
    visibility_bonus = 0.0
    if positive_pressure >= negative_pressure + 0.07:
        if positive_pressure >= 0.48:
            state = "surging"
            customer_delta = 1
        else:
            state = "steady_plus"
            customer_delta = 0
        visibility_bonus = 0.65 + (positive_pressure * 0.95)
    elif negative_pressure >= positive_pressure + 0.05:
        if negative_pressure >= 0.42:
            state = "patchy"
            customer_delta = -2
        else:
            state = "thin"
            customer_delta = -1
        visibility_bonus = -0.2 - (negative_pressure * 0.55)
    else:
        return {}

    return {
        "state": state,
        "positive_pressure": max(0.0, positive_pressure),
        "negative_pressure": max(0.0, negative_pressure),
        "visibility_bonus": float(visibility_bonus),
        "customer_delta": int(customer_delta),
    }


def _business_reputation_event_visibility_bias(event, profile):
    if not isinstance(event, dict) or not isinstance(profile, dict):
        return 0.0
    state = str(profile.get("state", "") or "").strip().lower()
    if not state:
        return 0.0
    event_phase = str(event.get("phase", "") or "").strip().lower()
    emphasis = str(event.get("emphasis", "") or "").strip().lower()
    positive_pressure = max(0.0, float(profile.get("positive_pressure", 0.0) or 0.0))
    negative_pressure = max(0.0, float(profile.get("negative_pressure", 0.0) or 0.0))

    if state in {"surging", "steady_plus"}:
        if event_phase in _BUSINESS_EVENT_CROWD_FORWARD_PHASES:
            return positive_pressure * 1.24
        if emphasis in {"front", "hospitality"}:
            return positive_pressure * 0.32
        if event_phase in _BUSINESS_EVENT_BACKPRESSURE_PHASES:
            return -(positive_pressure * 0.42)
        if emphasis in {"work", "admin"}:
            return -(positive_pressure * 0.16)
        return 0.0

    if state in {"patchy", "thin"}:
        if event_phase in _BUSINESS_EVENT_CROWD_FORWARD_PHASES:
            return -(negative_pressure * 1.3)
        if event_phase in _BUSINESS_EVENT_BACKPRESSURE_PHASES:
            return negative_pressure * 0.54
        if emphasis in {"front", "hospitality"}:
            return -(negative_pressure * 0.22)
        if emphasis in {"work", "admin"}:
            return negative_pressure * 0.12
    return 0.0


def _base_building_pulse_snapshot(sim, prop=None, structure=None):
    prop = prop if isinstance(prop, dict) else None
    structure = structure if isinstance(structure, dict) else None
    metadata = _property_metadata(prop)
    archetype = str(
        metadata.get("archetype", (structure or {}).get("archetype", "")) or ""
    ).strip().lower()
    category = _location_building_category(
        archetype,
        storefront=bool(prop and _property_is_storefront(prop)),
    )
    try:
        hour = int(_world_hour(sim)) % 24 if sim is not None else 12
    except (TypeError, ValueError):
        hour = 12
    tick_snapshot = _building_tick_snapshot(sim)
    bucket = int(tick_snapshot.get("bucket", 0) or 0)
    minute = int(tick_snapshot.get("minute", 0) or 0)

    status_text = ""
    if sim is not None and prop is not None:
        status_text = str(_property_status_text(sim, prop, hour=hour)).strip().lower()
    open_now = status_text == "open"

    phase = "steady"
    label = "steady rhythm"
    street_label = "steady foot traffic"
    entry_sentence = "The place is holding its ordinary rhythm right now."
    emphasis = "front" if open_now else "secure"

    if category in {"retail", "finance", "office"}:
        if open_now and 7 <= hour < 10:
            phase = "opening"
            label = "opening hour"
            street_label = "front waking up"
            entry_sentence = "At this hour the place feels like it is still gathering itself, with most of the motion collecting near the front."
            emphasis = "front"
        elif open_now and 11 <= hour < 14:
            phase = "rush"
            label = "midday rush"
            street_label = "traffic bunching at the front"
            entry_sentence = "Right now the place feels caught in a midday rush, with the front edge carrying more motion than the deeper rooms can fully hide."
            emphasis = "front"
        elif open_now and 15 <= hour < 18:
            phase = "back_office"
            label = "back-room churn"
            street_label = "quieter frontage, busier back rooms"
            entry_sentence = "The public face feels thinner right now while the real work slips deeper into the building."
            emphasis = "admin"
        elif open_now:
            phase = "steady_trade"
            label = "steady trade"
            street_label = "working pace at the front"
            entry_sentence = "The place is moving at working pace right now, more routine than spectacle."
            emphasis = "front"
        else:
            phase = "after_hours"
            label = "after hours"
            street_label = "dark front, watchful interior"
            entry_sentence = "At this hour the place feels more locked into itself than open to the street."
            emphasis = "secure"
    elif category in {"hospitality", "entertainment"}:
        if category == "hospitality" and 6 <= hour < 11:
            phase = "prep"
            label = "prep cycle"
            street_label = "setup and reset work"
            entry_sentence = "The public side is only part of the story right now; most of the energy feels like setup, cleanup, and short service loops."
            emphasis = "work"
        elif open_now and category == "hospitality" and 11 <= hour < 14:
            phase = "lunch_rush"
            label = "lunch rush"
            street_label = "crowd pressing the front"
            entry_sentence = "Right now the place feels caught in a meal rush, with the front doing everything it can to stay ahead of the back rooms."
            emphasis = "front"
        elif open_now and 17 <= hour < 23:
            phase = "evening_crowd"
            label = "evening crowd"
            street_label = "voices and traffic at the front"
            entry_sentence = "The building feels tilted toward the public rooms right now, as if the whole place is leaning into whoever just came through the door."
            emphasis = "hospitality"
        elif open_now and (hour >= 23 or hour < 3):
            phase = "late_buzz"
            label = "late buzz"
            street_label = "late traffic and lingering bodies"
            entry_sentence = "At this hour the place feels stretched into its late rhythm, all lingering voices, short service loops, and slower exits."
            emphasis = "front"
        elif open_now:
            phase = "cleanup"
            label = "cleanup cycle"
            street_label = "quiet front, active reset"
            entry_sentence = "The front is calmer right now, but the support spaces still feel busy with reset work."
            emphasis = "work"
        else:
            phase = "after_hours"
            label = "after hours"
            street_label = "shut frontage and faint after-hours motion"
            entry_sentence = "At this hour, without the public flow, the place feels more like a held interior than an invitation."
            emphasis = "secure"
    elif category in {"industrial", "transit"}:
        if 5 <= hour < 9:
            phase = "receiving"
            label = "receiving window"
            street_label = "handoff traffic and loading work"
            entry_sentence = "The building feels tuned to handoff right now, with short purposeful movement replacing any sense of lingering."
            emphasis = "work"
        elif open_now and 9 <= hour < 16:
            phase = "shift_work"
            label = "shift churn"
            street_label = "steady operational traffic"
            entry_sentence = "Everything here feels locked into active throughput right now: tasks landing, getting handled, and moving on."
            emphasis = "work"
        elif open_now and 16 <= hour < 19:
            phase = "handoff"
            label = "handoff hour"
            street_label = "between-shift movement"
            entry_sentence = "The place feels between shifts right now, all short exchanges, delayed exits, and one task handing off to the next."
            emphasis = "admin" if category == "industrial" else "transit"
        elif open_now:
            phase = "steady_ops"
            label = "steady operations"
            street_label = "working yard pace"
            entry_sentence = "The site feels busy in a practical way right now, more throughput than display."
            emphasis = "work"
        else:
            phase = "locked_down"
            label = "locked down"
            street_label = "quiet yard and sealed doors"
            entry_sentence = "At this hour the useful motion has dropped away, leaving the place feeling more controlled than alive."
            emphasis = "secure"
    elif category == "medical":
        if 7 <= hour < 10:
            phase = "intake"
            label = "intake wave"
            street_label = "people sorting at the front"
            entry_sentence = "Right now the place feels caught in intake, with movement clustering near the front before the deeper rooms can absorb it."
            emphasis = "front"
        elif 10 <= hour < 18:
            phase = "treatment"
            label = "treatment hours"
            street_label = "steady clinical traffic"
            entry_sentence = "The place is moving with procedural focus right now, all treatment rooms, short handoffs, and purposeful waiting."
            emphasis = "medical"
        elif open_now:
            phase = "night_watch"
            label = "night watch"
            street_label = "quiet entrance, active interior"
            entry_sentence = "At this hour the public edge is quiet, but the deeper rooms still feel actively watched."
            emphasis = "secure"
        else:
            phase = "after_hours"
            label = "after hours"
            street_label = "held quiet behind the threshold"
            entry_sentence = "At this hour the place feels more held in reserve than open to the street."
            emphasis = "secure"
    elif category == "secure":
        if 7 <= hour < 10:
            phase = "intake"
            label = "processing hour"
            street_label = "people being sorted at the secure front"
            entry_sentence = "The site feels caught in controlled processing right now, with movement stopping at the front before it can go anywhere else."
            emphasis = "front"
        elif 10 <= hour < 17:
            phase = "controlled_ops"
            label = "controlled operations"
            street_label = "guarded movement inside the perimeter"
            entry_sentence = "Everything here feels organized around observation, procedure, and slow deliberate motion."
            emphasis = "secure"
        elif 17 <= hour < 20:
            phase = "handoff"
            label = "custody turnover"
            street_label = "between-shift pressure at the gate"
            entry_sentence = "The place feels between watches right now, all clipped orders, delayed exits, and controlled handoffs."
            emphasis = "admin"
        else:
            phase = "night_watch"
            label = "night watch"
            street_label = "sealed frontage under watch"
            entry_sentence = "At this hour the site feels less closed than actively held, like the perimeter itself is still on duty."
            emphasis = "secure"
    elif category == "residential":
        if 6 <= hour < 9:
            phase = "starting_day"
            label = "starting day"
            street_label = "early household movement"
            entry_sentence = "The building feels like it is just pulling itself into the day, with routine doing more shaping than any formal design."
            emphasis = "residential"
        elif 18 <= hour < 23:
            phase = "settled_evening"
            label = "lived-in evening"
            street_label = "windows bright and people settling in"
            entry_sentence = "At this hour the place feels more lived-in than transactional, like routine has taken full possession of the rooms."
            emphasis = "residential"
        else:
            phase = "quiet_hours"
            label = "quiet hours"
            street_label = "low-light household quiet"
            entry_sentence = "The building has gone quiet in a way that suggests people have settled into it rather than left it."
            emphasis = "residential"
    else:
        if open_now:
            phase = "active_floor"
            label = "active floor"
            street_label = "front moving at work pace"
            entry_sentence = "The place feels active right now, with most of the motion staying close enough to the front to read from the threshold."
            emphasis = "front"
        else:
            phase = "quiet_interior"
            label = "quiet interior"
            street_label = "still frontage"
            entry_sentence = "The building feels quieter than empty right now, as if the useful activity has retreated deeper in."
            emphasis = "secure"

    pulse = {
        "phase": phase,
        "label": label,
        "street_label": street_label,
        "entry_sentence": entry_sentence,
        "emphasis": emphasis,
        "hour": hour,
        "minute": minute,
        "bucket": bucket,
        "category": category,
        "open_now": bool(open_now),
        "event_phase": "",
        "event_label": "",
        "perimeter_bonus": 0.0,
        "traffic_state": "",
        "traffic_customer_delta": 0,
    }
    return pulse


def _regular_building_micro_event_visible_property_ids(sim, chunk):
    if sim is None or not isinstance(chunk, (tuple, list)) or len(chunk) < 2:
        return ()
    try:
        chunk_key = (int(chunk[0]), int(chunk[1]))
    except (TypeError, ValueError):
        return ()

    winners = _building_regular_chunk_pulse_cache(sim)
    cached = winners.get(chunk_key)
    if cached is not None:
        return tuple(str(property_id or "").strip() for property_id in tuple(cached or ()) if str(property_id or "").strip())

    chance = _business_event_regular_chunk_hourly_chance(sim)
    if chance <= 0.0:
        winners[chunk_key] = ()
        return ()

    try:
        hour = int(_world_hour(sim)) % 24 if sim is not None else 0
    except (TypeError, ValueError):
        hour = 0
    activation_rng = random.Random(
        f"{getattr(sim, 'seed', 0)}:building-regular-chunk-active:{chunk_key[0]}:{chunk_key[1]}:{hour}"
    )
    if activation_rng.random() > chance:
        winners[chunk_key] = ()
        return ()

    candidates = []
    for prop in getattr(sim, "properties", {}).values():
        if not isinstance(prop, dict):
            continue
        if str(prop.get("kind", "") or "").strip().lower() != "building":
            continue
        try:
            prop_chunk = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
        except (TypeError, ValueError):
            continue
        if prop_chunk != chunk_key:
            continue

        base_pulse = _base_building_pulse_snapshot(sim, prop=prop)
        event = _raw_building_micro_event_snapshot(sim, prop=prop, base_pulse=base_pulse)
        event_phase = str(event.get("phase", "") or "").strip().lower()
        if not event_phase or event_phase in _BUSINESS_EVENT_AFTERMATH_PHASES:
            continue

        category = str(base_pulse.get("category", "") or "").strip().lower()
        if _business_event_scene_blueprint(prop, {"event_phase": event_phase, "category": category}) is None:
            continue

        property_id = str(prop.get("id", "") or "").strip()
        if not property_id:
            continue

        score = float(event.get("perimeter_bonus", 0.0) or 0.0)
        traffic_profile = _business_reputation_traffic_profile(sim, prop=prop, base_pulse=base_pulse)
        score += float(traffic_profile.get("visibility_bonus", 0.0) or 0.0)
        score += _business_reputation_event_visibility_bias(event, traffic_profile)
        if _property_is_storefront(prop) or _property_is_public(prop):
            score += 0.75
        if _property_access_level(prop) == "public":
            score += 0.35
        candidates.append((
            -score,
            event_phase,
            property_id,
        ))

    candidates.sort()
    visible_count = max(0, int(_BUSINESS_EVENT_REGULAR_SCENE_CAP or 0))
    visible_ids = tuple(
        str(candidate[2] or "").strip()
        for candidate in candidates[:visible_count]
        if str(candidate[2] or "").strip()
    )
    winners[chunk_key] = visible_ids
    return visible_ids


def _building_micro_event_snapshot(sim, prop=None, structure=None, base_pulse=None, *, respect_chunk_cap=True):
    event = _raw_building_micro_event_snapshot(sim, prop=prop, structure=structure, base_pulse=base_pulse)
    if not event or not respect_chunk_cap:
        return event

    prop = prop if isinstance(prop, dict) else None
    if prop is None or sim is None:
        return event

    event_phase = str(event.get("phase", "") or "").strip().lower()
    if not event_phase or event_phase in _BUSINESS_EVENT_AFTERMATH_PHASES:
        return event

    category = str(((base_pulse or {}) if isinstance(base_pulse, dict) else {}).get("category", "") or "").strip().lower()
    if _business_event_scene_blueprint(prop, {"event_phase": event_phase, "category": category}) is None:
        return event

    try:
        prop_chunk = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
    except (TypeError, ValueError):
        return event

    property_id = str(prop.get("id", "") or "").strip()
    if not property_id:
        return event
    visible_ids = _regular_building_micro_event_visible_property_ids(sim, prop_chunk)
    if property_id not in visible_ids:
        return {}
    return event


def _building_pulse_snapshot(sim, prop=None, structure=None, *, respect_chunk_cap=True):
    pulse = _base_building_pulse_snapshot(sim, prop=prop, structure=structure)
    base_label = str(pulse.get("label", "") or "").strip()
    base_entry_sentence = str(pulse.get("entry_sentence", "") or "").strip()
    event = _building_micro_event_snapshot(
        sim,
        prop=prop,
        structure=structure,
        base_pulse=pulse,
        respect_chunk_cap=respect_chunk_cap,
    )
    if event:
        event_label = str(event.get("label", "") or "").strip()
        if event_label:
            pulse["label"] = f"{base_label} + {event_label}"
            pulse["event_label"] = event_label
        event_street = str(event.get("street_label", "") or "").strip()
        if event_street:
            pulse["street_label"] = event_street
        event_sentence = str(event.get("entry_sentence", "") or "").strip()
        if event_sentence:
            pulse["entry_sentence"] = f"{base_entry_sentence} {event_sentence}".strip()
        event_emphasis = str(event.get("emphasis", "") or "").strip().lower()
        if event_emphasis:
            pulse["emphasis"] = event_emphasis
        pulse["event_phase"] = str(event.get("phase", "") or "").strip().lower()
        try:
            pulse["perimeter_bonus"] = max(0.0, float(event.get("perimeter_bonus", 0.0) or 0.0))
        except (TypeError, ValueError):
            pulse["perimeter_bonus"] = 0.0
        pulse["traffic_state"] = str(event.get("traffic_state", "") or "").strip().lower()
        try:
            pulse["traffic_customer_delta"] = int(event.get("traffic_customer_delta", 0) or 0)
        except (TypeError, ValueError):
            pulse["traffic_customer_delta"] = 0
    return pulse
def _next_business_event_seed_id(sim):
    state = _business_event_seed_state(sim)
    seed_id = f"bseed-{int(state.get('next_id', 1) or 1)}"
    state["next_id"] = int(state.get("next_id", 1) or 1) + 1
    return seed_id


def _business_event_ticks_per_hour(sim):
    world_traits = getattr(sim, "world_traits", {}) if sim is not None else {}
    clock = world_traits.get("clock", {}) if isinstance(world_traits, dict) else {}
    if not isinstance(clock, dict):
        clock = {}
    try:
        ticks_per_hour = int(clock.get("ticks_per_hour", 600))
    except (TypeError, ValueError):
        ticks_per_hour = 600
    return max(60, ticks_per_hour)


def _business_event_time_point_text(sim, *, offset_hours=2):
    try:
        hour = (int(_world_hour(sim)) + int(offset_hours)) % 24
    except (TypeError, ValueError):
        hour = 0
    window = _dialogue_hours_text((hour, (hour + 1) % 24))
    if " to " in window:
        return window.split(" to ", 1)[0]
    return window or "later"


def _business_event_property_category(sim, prop):
    if not isinstance(prop, dict):
        return ""
    category = str((_building_pulse_snapshot(sim, prop=prop) or {}).get("category", "") or "").strip().lower()
    if category:
        return category
    archetype = _property_archetype(prop)
    if archetype in MEDICAL_ARCHETYPES:
        return "medical"
    if archetype in TRANSIT_ARCHETYPES:
        return "transit"
    if archetype in INDUSTRIAL_ARCHETYPES or archetype in SALVAGE_ARCHETYPES:
        return "industrial"
    if archetype in NIGHTLIFE_ARCHETYPES:
        return "entertainment"
    if archetype in RESIDENTIAL_ARCHETYPES:
        return "residential"
    if archetype in STOREFRONT_ARCHETYPES:
        return "hospitality"
    return ""


def _business_event_aftermath_state(sim):
    state = getattr(sim, "business_event_aftermath_state", None)
    if isinstance(state, dict):
        properties = state.get("properties")
        if not isinstance(properties, dict):
            state["properties"] = {}
        return state
    state = {"properties": {}}
    sim.business_event_aftermath_state = state
    return state


def _prune_business_event_aftermath_state(sim):
    state = _business_event_aftermath_state(sim)
    properties = state.setdefault("properties", {})
    tick = int(getattr(sim, "tick", 0) or 0)
    for property_id, entry in list(properties.items()):
        if not isinstance(entry, dict):
            properties.pop(property_id, None)
            continue
        if str(property_id or "").strip() not in sim.properties:
            properties.pop(property_id, None)
            continue
        try:
            expires_tick = int(entry.get("expires_tick", tick) or tick)
        except (TypeError, ValueError):
            expires_tick = tick
        created_tick = entry.get("created_tick")
        try:
            created_tick = int(created_tick)
        except (TypeError, ValueError):
            created_tick = tick
        upgraded_expire = created_tick + _business_event_aftermath_duration_ticks(sim, entry)
        expires_tick = max(expires_tick, upgraded_expire)
        entry["expires_tick"] = expires_tick
        if tick > expires_tick:
            properties.pop(property_id, None)


def _business_event_aftermath_entry(sim, prop):
    if not isinstance(prop, dict):
        return None
    _prune_business_event_aftermath_state(sim)
    property_id = str(prop.get("id", "") or "").strip()
    if not property_id:
        return None
    entry = _business_event_aftermath_state(sim).setdefault("properties", {}).get(property_id)
    return entry if isinstance(entry, dict) else None


def _business_event_reactive_property_near(sim, x, y, z, *, radius=12):
    try:
        x = int(x)
        y = int(y)
        z = int(z)
    except (TypeError, ValueError):
        return None

    direct = _property_covering(sim, x, y, z) or sim.property_at(x, y, z)
    if isinstance(direct, dict) and str(direct.get("kind", "") or "").strip().lower() == "building":
        return direct

    target_chunk = sim.chunk_coords(x, y)
    best = None
    best_score = None
    for candidate in sim.properties.values():
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("kind", "") or "").strip().lower() != "building":
            continue
        try:
            cx = int(candidate.get("x", 0))
            cy = int(candidate.get("y", 0))
            cz = int(candidate.get("z", 0))
        except (TypeError, ValueError):
            continue
        if cz != z or sim.chunk_coords(cx, cy) != target_chunk:
            continue
        anchor = _business_event_frontage_anchor(sim, candidate) or _property_focus_position(candidate)
        if not isinstance(anchor, (tuple, list)) or len(anchor) < 3:
            continue
        distance = _manhattan(x, y, int(anchor[0]), int(anchor[1]))
        if distance > int(radius):
            continue
        access_level = _property_access_level(candidate)
        category = _business_event_property_category(sim, candidate)
        score = float(distance)
        if _property_is_storefront(candidate) or _property_is_public(candidate):
            score -= 0.8
        if access_level == "public":
            score -= 0.4
        if category == "residential":
            score -= 0.25
        if best is None or score < best_score:
            best = candidate
            best_score = score
    return best


def _business_event_aftermath_duration_ticks(sim, entry):
    ticks_per_hour = _business_event_ticks_per_hour(sim)
    incident_kind = str((entry or {}).get("incident_kind", "violence") or "violence").strip().lower() or "violence"
    try:
        casualty_count = int((entry or {}).get("casualty_count", 0) or 0)
    except (TypeError, ValueError):
        casualty_count = 0
    casualty_count = max(0, casualty_count)
    if casualty_count > 0:
        duration_hours = _BUSINESS_EVENT_AFTERMATH_CASUALTY_DURATION_HOURS
    elif incident_kind == "hazard":
        duration_hours = _BUSINESS_EVENT_AFTERMATH_HAZARD_DURATION_HOURS
    else:
        duration_hours = _BUSINESS_EVENT_AFTERMATH_VIOLENCE_DURATION_HOURS
    return int(ticks_per_hour * duration_hours)


def _record_business_event_aftermath(
    sim,
    *,
    x,
    y,
    z,
    incident_kind="violence",
    severity=0.4,
    casualty=False,
    serious=False,
    damage_kind="",
    prop=None,
):
    prop = prop if isinstance(prop, dict) else _business_event_reactive_property_near(sim, x, y, z)
    if not isinstance(prop, dict):
        return None

    property_id = str(prop.get("id", "") or "").strip()
    if not property_id:
        return None

    _prune_business_event_aftermath_state(sim)
    properties = _business_event_aftermath_state(sim).setdefault("properties", {})
    entry = dict(properties.get(property_id, {}) or {})
    tick = int(getattr(sim, "tick", 0) or 0)
    ticks_per_hour = _business_event_ticks_per_hour(sim)

    try:
        severity = max(0.18, min(1.0, float(severity)))
    except (TypeError, ValueError):
        severity = 0.4

    incident_kind = str(incident_kind or "violence").strip().lower() or "violence"
    damage_kind = str(damage_kind or "").strip().lower()
    created_tick = entry.get("created_tick")
    try:
        created_tick = int(created_tick)
    except (TypeError, ValueError):
        created_tick = tick

    casualty_count = max(0, int(entry.get("casualty_count", 0) or 0)) + (1 if casualty else 0)
    serious_count = max(0, int(entry.get("serious_count", 0) or 0)) + (1 if serious else 0)
    duration_ticks = _business_event_aftermath_duration_ticks(
        sim,
        {
            "incident_kind": incident_kind,
            "casualty_count": casualty_count,
        },
    )

    entry.update({
        "property_id": property_id,
        "building_id": _building_id_from_property(prop),
        "incident_kind": incident_kind,
        "damage_kind": damage_kind or str(entry.get("damage_kind", "") or "").strip().lower(),
        "severity": max(float(entry.get("severity", 0.0) or 0.0), severity),
        "casualty_count": casualty_count,
        "serious_count": serious_count,
        "created_tick": min(created_tick, tick),
        "last_tick": tick,
        "expires_tick": max(tick + duration_ticks, int(entry.get("expires_tick", 0) or 0)),
    })
    properties[property_id] = entry
    return entry


def _business_event_aftermath_micro_event(sim, prop=None, structure=None, base_pulse=None):
    if not isinstance(prop, dict):
        return {}
    entry = _business_event_aftermath_entry(sim, prop)
    if not isinstance(entry, dict):
        return {}

    category = str((base_pulse or {}).get("category", "") or "").strip().lower() or _business_event_property_category(sim, prop)
    tick = int(getattr(sim, "tick", 0) or 0)
    ticks_per_hour = _business_event_ticks_per_hour(sim)
    created_tick = entry.get("created_tick")
    try:
        created_tick = int(created_tick)
    except (TypeError, ValueError):
        created_tick = tick
    age_ticks = max(0, tick - created_tick)
    age_hours = float(age_ticks) / float(max(1, ticks_per_hour))
    incident_kind = str(entry.get("incident_kind", "violence") or "violence").strip().lower() or "violence"
    casualty_count = max(0, int(entry.get("casualty_count", 0) or 0))
    severity = max(0.18, min(1.0, float(entry.get("severity", 0.4) or 0.4)))

    if casualty_count > 0 and category == "residential" and age_hours >= _BUSINESS_EVENT_AFTERMATH_VIGIL_HOURS:
        return {
            "phase": "candle_vigil",
            "label": "candle vigil",
            "street_label": "candles and quiet voices at the entrance",
            "entry_sentence": "What happened here has already curdled into a quiet vigil, with candles, little offerings, and people speaking softly because louder would feel wrong.",
            "emphasis": "residential",
            "perimeter_bonus": 1.9 + (severity * 0.6),
        }
    if incident_kind == "hazard":
        if age_hours < _BUSINESS_EVENT_AFTERMATH_HAZARD_DELAY_HOURS:
            return {}
        return {
            "phase": "cleanup_detail",
            "label": "cleanup detail",
            "street_label": "cones and a cleanup crew at the entrance",
            "entry_sentence": "The frontage is being reset after recent trouble, all cones, short instructions, and workers trying to make the doorway usable again without pretending nothing happened.",
            "emphasis": "work",
            "perimeter_bonus": 1.55 + (severity * 0.45),
        }
    if age_hours >= _BUSINESS_EVENT_AFTERMATH_CLEANUP_HOURS:
        return {
            "phase": "cleanup_detail",
            "label": "cleanup detail",
            "street_label": "cones and a cleanup crew at the entrance",
            "entry_sentence": "The frontage is being reset after recent trouble, all cones, short instructions, and workers trying to make the doorway usable again without pretending nothing happened.",
            "emphasis": "work",
            "perimeter_bonus": 1.55 + (severity * 0.45),
        }
    if age_hours < _BUSINESS_EVENT_AFTERMATH_WITNESS_DELAY_HOURS:
        return {}
    return {
        "phase": "taped_off_front",
        "label": "taped-off frontage",
        "street_label": "tape and witnesses holding near the door",
        "entry_sentence": "Recent trouble has left the frontage half held in place, with tape, bystanders, and nobody quite ready to act like the doorway is ordinary again.",
        "emphasis": "front",
        "perimeter_bonus": 2.05 + (severity * 0.55),
    }


def _business_event_delivery_blueprint(category):
    category = str(category or "").strip().lower()
    if category == "medical":
        vehicle_name = "Clinic Courier Van"
        cargo_name = "Medical Supply Crates"
    elif category == "residential":
        vehicle_name = "Takeout Car"
        cargo_name = "Meal Carrier Crate"
    elif category in {"industrial", "transit"}:
        vehicle_name = "Supply Truck"
        cargo_name = "Freight Pallet"
    elif category in {"hospitality", "entertainment"}:
        vehicle_name = "Supplier Van"
        cargo_name = "Stock Dolly"
    else:
        vehicle_name = "Courier Van"
        cargo_name = "Parcel Stack"
    actor_specs = [
        {"role": "worker", "career": "courier", "linger_ticks": 8},
    ]
    if category in {"industrial", "medical", "transit"}:
        actor_specs.append({"role": "worker", "career": "receiver", "linger_ticks": 10})
    return {
        "scene_type": "delivery",
        "vehicle_name": vehicle_name,
        "fixture_name": cargo_name,
        "fixture_type": "delivery_cargo",
        "fixture_glyph": "c",
        "actor_specs": actor_specs,
        "keep_hours": 1,
        "release_budget": 0,
        "drift_preferred": False,
    }


def _business_event_gathering_blueprint(category):
    category = str(category or "").strip().lower()
    if category in {"hospitality", "entertainment"}:
        fixture_name = "Reserved Sign"
        fixture_type = "meeting_sign"
        fixture_glyph = "m"
        actor_specs = [
            {"role": "civilian", "career": "attendee", "linger_ticks": 18},
            {"role": "civilian", "career": "attendee", "linger_ticks": 18},
            {"role": "worker", "career": "host", "linger_ticks": 16},
        ]
    elif category in {"office", "finance"}:
        fixture_name = "Carpool Marker"
        fixture_type = "meeting_marker"
        fixture_glyph = "m"
        actor_specs = [
            {"role": "worker", "career": "attendee", "linger_ticks": 18},
            {"role": "worker", "career": "attendee", "linger_ticks": 18},
            {"role": "worker", "career": "attendee", "linger_ticks": 18},
        ]
    else:
        fixture_name = "Meeting Board"
        fixture_type = "meeting_board"
        fixture_glyph = "m"
        actor_specs = [
            {"role": "civilian", "career": "visitor", "linger_ticks": 18},
            {"role": "civilian", "career": "visitor", "linger_ticks": 18},
            {"role": "worker", "career": "coordinator", "linger_ticks": 16},
        ]
    return {
        "scene_type": "gathering",
        "fixture_name": fixture_name,
        "fixture_type": fixture_type,
        "fixture_glyph": fixture_glyph,
        "actor_specs": actor_specs,
        "keep_hours": 2,
        "release_budget": 1,
        "drift_preferred": True,
    }


def _business_event_inspection_blueprint(category):
    category = str(category or "").strip().lower()
    if category == "medical":
        fixture_name = "Inspection Clipboard"
        actor_specs = [
            {"role": "worker", "career": "inspector", "linger_ticks": 18},
            {"role": "worker", "career": "inspector", "linger_ticks": 18},
            {"role": "worker", "career": "site_rep", "linger_ticks": 16},
        ]
    elif category in {"office", "finance"}:
        fixture_name = "Audit Packet"
        actor_specs = [
            {"role": "worker", "career": "auditor", "linger_ticks": 18},
            {"role": "worker", "career": "auditor", "linger_ticks": 18},
            {"role": "worker", "career": "site_rep", "linger_ticks": 16},
        ]
    else:
        fixture_name = "Compliance Packet"
        actor_specs = [
            {"role": "worker", "career": "inspector", "linger_ticks": 18},
            {"role": "worker", "career": "inspector", "linger_ticks": 18},
            {"role": "worker", "career": "coordinator", "linger_ticks": 16},
        ]
    return {
        "scene_type": "gathering",
        "fixture_name": fixture_name,
        "fixture_type": "inspection_packet",
        "fixture_glyph": "i",
        "actor_specs": actor_specs,
        "keep_hours": 2,
        "release_budget": 1,
        "drift_preferred": False,
    }


def _business_event_admin_review_blueprint(category, *, event_phase=""):
    category = str(category or "").strip().lower()
    event_phase = str(event_phase or "").strip().lower()
    if event_phase == "regulars_spill":
        return {
            "scene_type": "gathering",
            "fixture_name": "Regulars Table",
            "fixture_type": "regulars_table",
            "fixture_glyph": "r",
            "actor_specs": [
                {"role": "civilian", "career": "regular", "linger_ticks": 22},
                {"role": "civilian", "career": "regular", "linger_ticks": 20},
                {"role": "worker", "career": "site_rep", "linger_ticks": 18, "site_affiliated": True},
            ],
            "keep_hours": 2,
            "release_budget": 0,
            "drift_preferred": True,
        }
    if event_phase == "grumbling_front":
        return {
            "scene_type": "gathering",
            "fixture_name": "Complaint Crate",
            "fixture_type": "complaint_board",
            "fixture_glyph": "g",
            "actor_specs": [
                {"role": "civilian", "career": "disgruntled_customer", "linger_ticks": 20},
                {"role": "civilian", "career": "regular", "linger_ticks": 18},
                {"role": "worker", "career": "site_rep", "linger_ticks": 16, "site_affiliated": True},
            ],
            "keep_hours": 1,
            "release_budget": 0,
            "drift_preferred": False,
        }
    if event_phase == "manifest_check":
        fixture_name = "Dispatch Clipboard" if category == "transit" else "Manifest Clipboard"
        fixture_type = "manifest_clipboard"
        fixture_glyph = "i"
        actor_specs = [
            {"role": "worker", "career": "dispatcher" if category == "transit" else "manifest_clerk", "linger_ticks": 16},
            {"role": "worker", "career": "site_rep", "linger_ticks": 14},
        ]
    elif category in {"office", "finance"}:
        fixture_name = "Audit Packet"
        fixture_type = "admin_packet"
        fixture_glyph = "i"
        actor_specs = [
            {"role": "worker", "career": "auditor", "linger_ticks": 16},
            {"role": "worker", "career": "site_rep", "linger_ticks": 14},
        ]
    elif category == "retail":
        fixture_name = "Receipt Binder"
        fixture_type = "admin_packet"
        fixture_glyph = "i"
        actor_specs = [
            {"role": "worker", "career": "review_clerk", "linger_ticks": 15},
            {"role": "worker", "career": "site_rep", "linger_ticks": 14},
        ]
    else:
        fixture_name = "Review Packet"
        fixture_type = "admin_packet"
        fixture_glyph = "i"
        actor_specs = [
            {"role": "worker", "career": "review_clerk", "linger_ticks": 15},
            {"role": "worker", "career": "site_rep", "linger_ticks": 14},
        ]
    return {
        "scene_type": "gathering",
        "fixture_name": fixture_name,
        "fixture_type": fixture_type,
        "fixture_glyph": fixture_glyph,
        "actor_specs": actor_specs,
        "keep_hours": 1,
        "release_budget": 0,
        "drift_preferred": False,
    }


def _business_event_medical_response_blueprint(category, *, event_phase=""):
    category = str(category or "").strip().lower()
    event_phase = str(event_phase or "").strip().lower()
    if event_phase != "street_triage":
        return None

    medical_site = category == "medical"
    medic_career = "triage_nurse" if medical_site else "combat_medic"
    victim_career = "patient" if medical_site else "injured_bystander"
    fixture_name = "Triage Kit" if medical_site else "Field Med Case"
    actor_specs = [
        {
            "role": "worker",
            "career": medic_career,
            "linger_ticks": 16,
            "site_affiliated": medical_site,
        },
        {
            "role": "civilian",
            "career": victim_career,
            "linger_ticks": 20,
            "fixed_position": True,
            "site_affiliated": False,
            "hp_ratio_range": (0.22, 0.48),
            "needs_overrides": {"safety": (10, 26), "energy": (18, 42)},
            "status_effects": (
                {
                    "status": "trauma_shocked",
                    "duration": 90,
                    "modifiers": {
                        "safety_tick_delta": -0.08,
                        "move_speed_mult": -0.28,
                    },
                },
            ),
        },
        {
            "role": "civilian",
            "career": victim_career,
            "linger_ticks": 20,
            "fixed_position": True,
            "site_affiliated": False,
            "hp_ratio_range": (0.34, 0.58),
            "needs_overrides": {"safety": (16, 32), "energy": (24, 48)},
            "status_effects": (
                {
                    "status": "trauma_shocked",
                    "duration": 72,
                    "modifiers": {
                        "safety_tick_delta": -0.06,
                        "move_speed_mult": -0.22,
                    },
                },
            ),
        },
    ]
    return {
        "scene_type": "gathering",
        "fixture_name": fixture_name,
        "fixture_type": "trauma_kit",
        "fixture_glyph": "h",
        "actor_specs": actor_specs,
        "keep_hours": 1,
        "release_budget": 0,
        "drift_preferred": False,
    }


def _business_event_residential_social_blueprint(category, *, event_phase=""):
    category = str(category or "").strip().lower()
    event_phase = str(event_phase or "").strip().lower()
    if event_phase == "school_run":
        return {
            "scene_type": "gathering",
            "fixture_name": "Backpack Cluster",
            "fixture_type": "school_bags",
            "fixture_glyph": "b",
            "actor_specs": [
                {"role": "civilian", "career": "guardian", "linger_ticks": 16},
                {"role": "civilian", "career": "student", "linger_ticks": 18, "fixed_position": True},
                {"role": "civilian", "career": "student", "linger_ticks": 18, "fixed_position": True},
            ],
            "keep_hours": 1,
            "release_budget": 0,
            "drift_preferred": False,
        }
    if event_phase == "neighbors_lingering":
        return {
            "scene_type": "gathering",
            "fixture_name": "Shared Cooler",
            "fixture_type": "stoop_cooler",
            "fixture_glyph": "c",
            "actor_specs": [
                {"role": "civilian", "career": "resident", "linger_ticks": 20},
                {"role": "civilian", "career": "resident", "linger_ticks": 20},
                {"role": "civilian", "career": "retiree", "linger_ticks": 24, "fixed_position": True},
            ],
            "keep_hours": 1,
            "release_budget": 0,
            "drift_preferred": False,
        }
    return None


def _business_event_settlement_blueprint(category, *, event_phase=""):
    category = str(category or "").strip().lower()
    event_phase = str(event_phase or "").strip().lower()
    if event_phase == "help_wanted_board":
        return {
            "scene_type": "gathering",
            "fixture_name": "Help-Wanted Board",
            "fixture_type": "help_wanted_board",
            "fixture_glyph": "j",
            "actor_specs": [
                {"role": "civilian", "career": "job_seeker", "linger_ticks": 20, "site_affiliated": False},
                {"role": "civilian", "career": "job_seeker", "linger_ticks": 18, "site_affiliated": False},
                {"role": "worker", "career": "hiring_lead", "linger_ticks": 16, "site_affiliated": True},
            ],
            "keep_hours": 2,
            "release_budget": 1,
            "drift_preferred": False,
        }
    if event_phase == "clinic_outreach":
        return {
            "scene_type": "gathering",
            "fixture_name": "Outreach Table",
            "fixture_type": "outreach_table",
            "fixture_glyph": "o",
            "actor_specs": [
                {"role": "civilian", "career": "walk_in_patient", "linger_ticks": 20, "site_affiliated": False},
                {"role": "civilian", "career": "caregiver", "linger_ticks": 18, "site_affiliated": False},
                {"role": "worker", "career": "outreach_nurse", "linger_ticks": 16, "site_affiliated": True},
            ],
            "keep_hours": 2,
            "release_budget": 1,
            "drift_preferred": False,
        }
    if event_phase == "day_labor_call":
        return {
            "scene_type": "gathering",
            "fixture_name": "Crew Call Sheet",
            "fixture_type": "crew_call_sheet",
            "fixture_glyph": "w",
            "actor_specs": [
                {"role": "civilian", "career": "day_laborer", "linger_ticks": 20, "site_affiliated": False},
                {"role": "civilian", "career": "day_laborer", "linger_ticks": 18, "site_affiliated": False},
                {"role": "worker", "career": "crew_lead", "linger_ticks": 16, "site_affiliated": True},
            ],
            "keep_hours": 2,
            "release_budget": 1,
            "drift_preferred": False,
        }
    if event_phase == "commuter_orientation":
        return {
            "scene_type": "gathering",
            "fixture_name": "Route Welcome Board",
            "fixture_type": "route_welcome_board",
            "fixture_glyph": "r",
            "actor_specs": [
                {"role": "civilian", "career": "new_arrival", "linger_ticks": 20, "site_affiliated": False},
                {"role": "civilian", "career": "commuter", "linger_ticks": 18, "site_affiliated": False},
                {"role": "worker", "career": "station_guide", "linger_ticks": 16, "site_affiliated": True},
            ],
            "keep_hours": 2,
            "release_budget": 1,
            "drift_preferred": True,
        }
    if event_phase == "tenant_meetup":
        return {
            "scene_type": "gathering",
            "fixture_name": "Tenant Welcome Box",
            "fixture_type": "tenant_welcome_box",
            "fixture_glyph": "t",
            "actor_specs": [
                {"role": "civilian", "career": "new_tenant", "linger_ticks": 22, "site_affiliated": False},
                {"role": "civilian", "career": "resident", "linger_ticks": 20, "site_affiliated": False},
                {"role": "civilian", "career": "building_rep", "linger_ticks": 18, "site_affiliated": True},
            ],
            "keep_hours": 2,
            "release_budget": 1,
            "drift_preferred": False,
        }
    if event_phase == "mutual_aid_table":
        return {
            "scene_type": "gathering",
            "fixture_name": "Mutual Aid Table",
            "fixture_type": "mutual_aid_table",
            "fixture_glyph": "a",
            "actor_specs": [
                {"role": "civilian", "career": "new_arrival", "linger_ticks": 22, "site_affiliated": False},
                {"role": "civilian", "career": "volunteer", "linger_ticks": 20, "site_affiliated": False},
                {"role": "civilian", "career": "neighbor", "linger_ticks": 18, "site_affiliated": False},
            ],
            "keep_hours": 2,
            "release_budget": 1,
            "drift_preferred": True,
        }
    return None


def _business_event_operational_pressure_blueprint(category, *, event_phase=""):
    category = str(category or "").strip().lower()
    event_phase = str(event_phase or "").strip().lower()
    if event_phase == "loading_push":
        fixture_name = "Freight Dolly" if category == "industrial" else "Load Dolly"
        return {
            "scene_type": "shift",
            "fixture_name": fixture_name,
            "fixture_type": "loading_dolly",
            "fixture_glyph": "f",
            "actor_specs": [
                {"role": "worker", "career": "loader", "linger_ticks": 10},
                {"role": "worker", "career": "dockhand", "linger_ticks": 10},
            ],
            "keep_hours": 1,
            "release_budget": 0,
            "drift_preferred": False,
        }
    if event_phase == "dispatch_surge":
        return {
            "scene_type": "shift",
            "fixture_name": "Dispatch Satchel" if category == "transit" else "Route Satchel",
            "fixture_type": "dispatch_satchel",
            "fixture_glyph": "s",
            "actor_specs": [
                {"role": "worker", "career": "dispatcher", "linger_ticks": 12},
                {"role": "worker", "career": "driver" if category == "transit" else "loader", "linger_ticks": 10},
            ],
            "keep_hours": 1,
            "release_budget": 0,
            "drift_preferred": False,
        }
    if event_phase == "boarding_crush":
        return {
            "scene_type": "shift",
            "fixture_name": "Fare Rack",
            "fixture_type": "fare_rack",
            "fixture_glyph": "r",
            "actor_specs": [
                {"role": "worker", "career": "dispatcher", "linger_ticks": 12},
                {"role": "worker", "career": "driver", "linger_ticks": 10},
                {"role": "civilian", "career": "commuter", "linger_ticks": 14},
            ],
            "keep_hours": 1,
            "release_budget": 0,
            "drift_preferred": False,
        }
    if event_phase == "arrival_handoff":
        return {
            "scene_type": "shift",
            "fixture_name": "Transfer Clipboard",
            "fixture_type": "transfer_clipboard",
            "fixture_glyph": "c",
            "actor_specs": [
                {"role": "worker", "career": "dispatcher", "linger_ticks": 12},
                {"role": "worker", "career": "driver", "linger_ticks": 10},
                {"role": "civilian", "career": "specialist", "linger_ticks": 16},
            ],
            "keep_hours": 1,
            "release_budget": 0,
            "drift_preferred": False,
        }
    return None


def _business_event_aftermath_blueprint(category, *, event_phase=""):
    category = str(category or "").strip().lower()
    event_phase = str(event_phase or "").strip().lower()
    if event_phase == "taped_off_front":
        if category == "residential":
            third_actor = {"role": "civilian", "career": "resident", "linger_ticks": 18, "fixed_position": True}
        elif category == "secure":
            third_actor = {"role": "guard", "career": "gate_guard", "linger_ticks": 16, "site_affiliated": True, "fixed_position": True}
        else:
            third_actor = {"role": "worker", "career": "site_rep", "linger_ticks": 16, "site_affiliated": True, "fixed_position": True}
        return {
            "scene_type": "gathering",
            "fixture_name": "Tape Stanchion",
            "fixture_type": "incident_tape",
            "fixture_glyph": "t",
            "actor_specs": [
                {"role": "civilian", "career": "witness", "linger_ticks": 18},
                {"role": "civilian", "career": "witness", "linger_ticks": 18},
                third_actor,
            ],
            "keep_hours": 1,
            "release_budget": 0,
            "drift_preferred": False,
        }
    if event_phase == "cleanup_detail":
        second_career = "sanitation_worker" if category in {"medical", "hospitality", "entertainment"} else "maintenance_tech"
        return {
            "scene_type": "shift",
            "fixture_name": "Cleanup Cart",
            "fixture_type": "cleanup_cart",
            "fixture_glyph": "c",
            "actor_specs": [
                {"role": "worker", "career": "cleanup_crew", "linger_ticks": 12},
                {"role": "worker", "career": second_career, "linger_ticks": 12},
            ],
            "keep_hours": 1,
            "release_budget": 0,
            "drift_preferred": False,
        }
    if event_phase == "candle_vigil":
        return {
            "scene_type": "gathering",
            "fixture_name": "Memorial Candles",
            "fixture_type": "memorial_candles",
            "fixture_glyph": "v",
            "actor_specs": [
                {"role": "civilian", "career": "resident", "linger_ticks": 22, "fixed_position": True},
                {"role": "civilian", "career": "mourner", "linger_ticks": 22, "fixed_position": True},
                {"role": "civilian", "career": "mourner", "linger_ticks": 20},
            ],
            "keep_hours": 2,
            "release_budget": 0,
            "drift_preferred": False,
        }
    return None


def _business_event_neighborhood_target(sim, prop, *, rng=None):
    if not isinstance(prop, dict):
        return None
    try:
        origin_x = int(prop.get("x", 0))
        origin_y = int(prop.get("y", 0))
        origin_z = int(prop.get("z", 0))
    except (TypeError, ValueError):
        return None

    origin_chunk = sim.chunk_coords(origin_x, origin_y)
    origin_id = str(prop.get("id", "") or "").strip()
    weighted = []
    for candidate in sim.properties.values():
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("kind", "") or "").strip().lower() != "building":
            continue
        candidate_id = str(candidate.get("id", "") or "").strip()
        if not candidate_id or candidate_id == origin_id:
            continue
        try:
            cx = int(candidate.get("x", 0))
            cy = int(candidate.get("y", 0))
            cz = int(candidate.get("z", 0))
        except (TypeError, ValueError):
            continue
        if sim.chunk_coords(cx, cy) != origin_chunk or cz != origin_z:
            continue
        distance = _manhattan(origin_x, origin_y, cx, cy)
        if distance < 3 or distance > 18:
            continue
        category = _business_event_property_category(sim, candidate)
        access_level = _property_access_level(candidate)
        score = max(0.2, 18.0 - float(distance))
        if _property_is_storefront(candidate) or _property_is_public(candidate):
            score += 2.0
        if access_level == "public":
            score += 2.4
        if category == "hospitality":
            score += 2.6
        elif category == "retail":
            score += 2.2
        elif category in {"medical", "transit", "civic"}:
            score += 1.3
        elif category in {"residential", "secure"}:
            score -= 1.6
        if score > 0.0:
            weighted.append((score, candidate))

    if not weighted:
        return None
    if rng is None:
        rng = random.Random(f"{getattr(sim, 'seed', 0)}:business-scene-neighborhood:{origin_id}")
    total = sum(weight for weight, _candidate in weighted)
    pick = rng.uniform(0.0, total)
    running = 0.0
    choice = weighted[-1][1]
    for weight, candidate in weighted:
        running += weight
        if pick <= running:
            choice = candidate
            break
    return choice


def _business_event_hospitality_pressure_blueprint(category, *, event_phase=""):
    category = str(category or "").strip().lower()
    event_phase = str(event_phase or "").strip().lower()
    if event_phase == "reset_scramble":
        return {
            "scene_type": "shift",
            "fixture_name": "Bus Tub",
            "fixture_type": "reset_cart",
            "fixture_glyph": "b",
            "actor_specs": [
                {"role": "worker", "career": "server", "linger_ticks": 10},
                {"role": "worker", "career": "dishwasher", "linger_ticks": 10},
            ],
            "keep_hours": 1,
            "release_budget": 0,
            "drift_preferred": False,
        }
    if event_phase == "table_turnover":
        return {
            "scene_type": "shift",
            "fixture_name": "Turnover Tray",
            "fixture_type": "turnover_tray",
            "fixture_glyph": "t",
            "actor_specs": [
                {"role": "worker", "career": "host", "linger_ticks": 9},
                {"role": "worker", "career": "server", "linger_ticks": 9},
                {"role": "worker", "career": "server", "linger_ticks": 9},
            ],
            "keep_hours": 1,
            "release_budget": 0,
            "drift_preferred": False,
        }
    if event_phase == "barback_reset":
        return {
            "scene_type": "shift",
            "fixture_name": "Restock Crate",
            "fixture_type": "barback_crate",
            "fixture_glyph": "r",
            "actor_specs": [
                {"role": "worker", "career": "bartender", "linger_ticks": 10},
                {"role": "worker", "career": "server", "linger_ticks": 10},
            ],
            "keep_hours": 1,
            "release_budget": 0,
            "drift_preferred": False,
        }
    return None


def _business_event_followup_target(sim, prop, *, scene_type="", category="", rng=None):
    if not isinstance(prop, dict):
        return None
    try:
        origin_x = int(prop.get("x", 0))
        origin_y = int(prop.get("y", 0))
        origin_z = int(prop.get("z", 0))
    except (TypeError, ValueError):
        return None

    origin_chunk = sim.chunk_coords(origin_x, origin_y)
    origin_id = str(prop.get("id", "") or "").strip()
    weighted = []
    for candidate in sim.properties.values():
        if not isinstance(candidate, dict):
            continue
        if str(candidate.get("kind", "") or "").strip().lower() != "building":
            continue
        candidate_id = str(candidate.get("id", "") or "").strip()
        if not candidate_id or candidate_id == origin_id:
            continue
        try:
            cx = int(candidate.get("x", 0))
            cy = int(candidate.get("y", 0))
            cz = int(candidate.get("z", 0))
        except (TypeError, ValueError):
            continue
        if sim.chunk_coords(cx, cy) != origin_chunk:
            continue
        distance = _manhattan(origin_x, origin_y, cx, cy)
        if distance < 3 or distance > 18:
            continue
        score = max(0.2, 18.5 - float(distance))
        candidate_category = _business_event_property_category(sim, candidate)
        if category and candidate_category == category:
            score += 3.0
        if _property_is_storefront(candidate) or _property_is_public(candidate):
            score += 1.4
        if scene_type == "delivery" and candidate_category in {"industrial", "transit", "medical", "hospitality"}:
            score += 1.8
        elif scene_type == "queue" and candidate_category in {"hospitality", "entertainment", "civic", "medical"}:
            score += 1.6
        elif scene_type == "shift" and candidate_category in {"industrial", "transit", "medical", "hospitality"}:
            score += 1.5
        if _property_access_level(candidate) == "public":
            score += 0.6
        if cz != origin_z:
            score -= 1.2
        if score > 0.0:
            weighted.append((score, candidate))

    if not weighted:
        return prop
    if rng is None:
        rng = random.Random(f"{getattr(sim, 'seed', 0)}:business-scene-followup:{origin_id}:{scene_type}:{category}")
    total = sum(weight for weight, _candidate in weighted)
    pick = rng.uniform(0.0, total)
    running = 0.0
    choice = weighted[-1][1]
    for weight, candidate in weighted:
        running += weight
        if pick <= running:
            choice = candidate
            break
    return choice


def _business_event_item_pool(scene_type, category, actor_spec):
    scene_type = str(scene_type or "").strip().lower()
    category = str(category or "").strip().lower()
    career = str((actor_spec or {}).get("career", "") or "").strip().lower()
    role = str((actor_spec or {}).get("role", "") or "").strip().lower()

    if scene_type == "delivery":
        if category == "medical":
            return ("med_gel", "micro_medkit", "trauma_foam", "hydration_salts")
        if category in {"industrial", "transit"}:
            return ("pocket_multitool", "battery_pack", "scrap_circuit", "protein_wrap")
        if category in {"hospitality", "entertainment", "residential"}:
            return ("protein_wrap", "street_ration", "meal_voucher", "bottled_water")
        return ("city_pass_token", "protein_wrap", "bottled_water", "transit_daypass")
    if scene_type == "queue":
        if career == "patient" or category == "medical":
            return ("hydration_salts", "med_gel", "calm_patch", "bottled_water")
        if role == "drunk" or career == "late_patron" or category == "entertainment":
            return ("spark_brew", "smoke_tab", "mint_strip", "city_pass_token")
        if category == "transit":
            return ("city_pass_token", "transit_daypass", "protein_wrap", "bottled_water")
        return ("meal_voucher", "city_pass_token", "protein_wrap", "bottled_water")
    if scene_type == "shift":
        if career in {"dispatcher", "manifest_clerk", "route_clerk"}:
            return ("credstick_chip", "city_pass_token", "transit_daypass", "caff_shot")
        if career in {"loader", "dockhand"}:
            return ("pocket_multitool", "battery_pack", "caff_shot", "protein_wrap")
        if career in {"commuter", "specialist", "traveler"}:
            return ("city_pass_token", "transit_daypass", "protein_wrap", "bottled_water")
        if career == "driver":
            return ("city_pass_token", "transit_daypass", "caff_shot", "protein_wrap")
        if career in {"cleanup_crew", "sanitation_worker", "maintenance_tech"}:
            return ("pocket_multitool", "bottled_water", "caff_shot", "calm_patch")
        if category == "medical":
            return ("med_gel", "focus_inhaler", "micro_medkit", "caff_shot")
        if category in {"industrial", "transit"}:
            return ("pocket_multitool", "battery_pack", "caff_shot", "protein_wrap")
        if category == "entertainment":
            return ("spark_brew", "mint_strip", "caff_shot", "protein_wrap")
        if category == "hospitality":
            return ("caff_shot", "meal_voucher", "mint_strip", "protein_wrap")
        return ("city_pass_token", "meal_voucher", "caff_shot", "protein_wrap")
    if scene_type == "gathering":
        if career in {"job_seeker", "hiring_lead"}:
            return ("city_pass_token", "caff_shot", "protein_wrap", "focus_inhaler")
        if career in {"walk_in_patient", "caregiver", "outreach_nurse"}:
            return ("hydration_salts", "calm_patch", "med_gel", "bottled_water")
        if career in {"day_laborer", "crew_lead"}:
            return ("pocket_multitool", "battery_pack", "protein_wrap", "caff_shot")
        if career in {"new_arrival", "commuter", "station_guide"}:
            return ("city_pass_token", "transit_daypass", "protein_wrap", "bottled_water")
        if career in {"new_tenant", "building_rep", "volunteer", "neighbor"}:
            return ("meal_voucher", "city_pass_token", "bottled_water", "calm_patch")
        if career in {"guardian", "student"}:
            return ("meal_voucher", "city_pass_token", "protein_wrap", "bottled_water")
        if career in {"resident", "retiree", "smoker"}:
            return ("spark_brew", "smoke_tab", "mint_strip", "city_pass_token")
        if career in {"witness", "mourner"}:
            return ("calm_patch", "bottled_water", "city_pass_token", "meal_voucher")
        if career in {"triage_nurse", "combat_medic", "trauma_doctor", "medic", "paramedic"}:
            return ("med_gel", "micro_medkit", "trauma_foam", "hydration_salts")
        if category in {"hospitality", "entertainment"}:
            return ("spark_brew", "meal_voucher", "mint_strip", "city_pass_token")
        if category in {"office", "finance"}:
            return ("credstick_chip", "city_pass_token", "focus_inhaler", "protein_wrap")
        return ("city_pass_token", "meal_voucher", "protein_wrap", "bottled_water")
    return ("street_ration", "city_pass_token", "protein_wrap", "bottled_water")


def _business_event_followup_anchor_fields(sim, prop):
    if not isinstance(prop, dict):
        return {}
    place_name = str(prop.get("name", prop.get("id", "the place"))).strip() or "the place"
    metadata = prop.get("metadata", {}) if isinstance(prop.get("metadata", {}), dict) else {}
    org_snapshot = _organization_snapshot(sim, prop=prop, ensure=True)
    organization_name = str(
        (org_snapshot or {}).get("organization_name", "")
        or metadata.get("organization_name", "")
        or ""
    ).strip()
    return {
        "anchor_site_name": place_name,
        "organization_name": organization_name,
    }


def _business_event_followup_target_label(anchor_fields):
    anchor_fields = anchor_fields if isinstance(anchor_fields, dict) else {}
    place_name = str(anchor_fields.get("anchor_site_name", "")).strip() or "the place"
    organization_name = str(anchor_fields.get("organization_name", "")).strip()
    if organization_name and organization_name.lower() != place_name.lower():
        return f"{place_name} for {organization_name}"
    return place_name


def _business_event_enrich_followup_opportunity(sim, opportunity, target_prop, *, contact_name="", contact_role=""):
    if not isinstance(opportunity, dict):
        return {}

    enriched = dict(opportunity)
    if isinstance(target_prop, dict):
        anchor_fields = _business_event_followup_anchor_fields(sim, target_prop)
        for key, value in anchor_fields.items():
            clean = str(value or "").strip()
            if clean and not str(enriched.get(key, "") or "").strip():
                enriched[key] = clean

        requirements = dict(enriched.get("requirements", {}) or {}) if isinstance(enriched.get("requirements", {}), dict) else {}
        property_id = str(target_prop.get("id", "") or "").strip()
        property_name = str(target_prop.get("name", property_id or "the place")).strip() or "the place"
        if property_id and not str(requirements.get("property_id", "") or "").strip():
            requirements["property_id"] = property_id
        if property_name and not str(requirements.get("property_name", "") or "").strip():
            requirements["property_name"] = property_name
        if "visit_chunk" not in requirements:
            chunk = tuple(enriched.get("chunk", ()) or ())
            if len(chunk) >= 2:
                try:
                    requirements["visit_chunk"] = (int(chunk[0]), int(chunk[1]))
                except (TypeError, ValueError):
                    pass
        if requirements:
            enriched["requirements"] = requirements

    contact_name = str(contact_name or "").strip()
    contact_role = str(contact_role or "").strip().lower()
    if contact_name and not str(enriched.get("contact_name", "") or "").strip():
        enriched["contact_name"] = contact_name
    if contact_role and not str(enriched.get("contact_role", "") or "").strip():
        enriched["contact_role"] = contact_role
    return enriched


def _business_event_followup_note(sim, scene, prop, actor_spec, *, rng):
    followup_seed_id = str((scene or {}).get("followup_seed_id", "") or "").strip()
    if followup_seed_id:
        seed = _business_event_seed_state(sim).get("active", {}).get(followup_seed_id)
        if isinstance(seed, dict):
            target_property_id = str(seed.get("target_property_id", "") or "").strip()
            target_prop = sim.properties.get(target_property_id) if target_property_id else None
            return {
                "seed_id": str(seed.get("seed_id", "") or "").strip(),
                "property_id": str(seed.get("source_property_id", "") or "").strip(),
                "target_property_id": target_property_id,
                "local_line": str(seed.get("local_line", "") or "").strip(),
                "detail_line": str(seed.get("detail_line", "") or "").strip(),
                "lead_kind": str(seed.get("lead_kind", "") or "").strip().lower(),
                "opportunity": _business_event_enrich_followup_opportunity(
                    sim,
                    dict(seed.get("opportunity", {}) or {}),
                    target_prop,
                ),
                "shared": bool(seed.get("shared")),
            }
    if not isinstance(prop, dict):
        return {}
    scene_type = str((scene or {}).get("scene_type", "") or "").strip().lower()
    category = str((scene or {}).get("category", "") or "").strip().lower()
    event_phase = str((scene or {}).get("event_phase", "") or "").strip().lower()
    traffic_state = str((scene or {}).get("traffic_state", "") or "").strip().lower()
    scene_id = str((scene or {}).get("scene_id", "") or "").strip()
    actor_spec = actor_spec if isinstance(actor_spec, dict) else {}
    role = str(actor_spec.get("role", "") or "").strip().lower()
    career = str(actor_spec.get("career", "") or "").strip().lower()
    current_name = str(prop.get("name", prop.get("id", "this place"))).strip() or "this place"
    controller = _property_access_controller(sim, prop)
    hours_text = _dialogue_hours_text(controller.get("opening_window")) if isinstance(controller, dict) else ""
    requirement = _controller_access_requirement_text(controller) if isinstance(controller, dict) else ""

    if event_phase == "owner_screening":
        if career == "door_host" or role == "worker":
            local_line = f"We are only waving people through {current_name} if they belong here right now."
        else:
            local_line = f"They are checking who belongs at {current_name} before they let anybody deeper in."
        if hours_text and requirement:
            detail_line = f"{current_name} is screening people at the door during {hours_text}. Anyone getting past the threshold still needs {requirement}."
        elif hours_text:
            detail_line = f"{current_name} is still open during {hours_text}, but the front has tightened into a short screening line."
        elif requirement:
            detail_line = f"{current_name} is trading behind a screened front. Anyone getting past the threshold still needs {requirement}."
        else:
            detail_line = f"The frontage at {current_name} has tightened into a screened threshold instead of an ordinary open door."
        return {
            "property_id": str(prop.get("id", "") or "").strip(),
            "target_property_id": str(prop.get("id", "") or "").strip(),
            "local_line": local_line,
            "detail_line": detail_line,
            "lead_kind": "access" if requirement else "hours",
            "shared": False,
        }

    if event_phase == "owner_closed_turnover":
        if role == "worker":
            local_line = f"We are closed to walk-ins while {current_name} turns the floor over and catches up."
        else:
            local_line = f"The place looks closed, but staff at {current_name} are clearly still working inside the shut front."
        if hours_text and requirement:
            detail_line = f"{current_name} is closed to customers for now, with staff still working through a short turnover during what is usually {hours_text}. Once it opens again the front wants {requirement}."
        elif hours_text:
            detail_line = f"{current_name} is closed to customers for now, but staff are still working through a short turnover during what is usually {hours_text}."
        elif requirement:
            detail_line = f"{current_name} is closed to customers for now, but the staff are still cycling through short internal tasks. When it opens again the front wants {requirement}."
        else:
            detail_line = f"{current_name} is closed to customers for now, but the staff are still cycling through short internal tasks behind the shut front."
        return {
            "property_id": str(prop.get("id", "") or "").strip(),
            "target_property_id": str(prop.get("id", "") or "").strip(),
            "local_line": local_line,
            "detail_line": detail_line,
            "lead_kind": "hours",
            "shared": False,
        }

    if event_phase == "paperwork_surge":
        if traffic_state in {"patchy", "thin"}:
            local_line = f"The front at {current_name} is thinner than it should be, so the paperwork side is getting all the blame."
        else:
            local_line = f"They are trying to clear a paperwork jam at {current_name} before the front side bogs down."
        if traffic_state in {"patchy", "thin"} and hours_text and requirement:
            detail_line = f"{current_name} is chewing through approvals during {hours_text}, but the public side is also running thin enough that the quiet feels noticeable. Once that breaks, the front still wants {requirement}."
        elif traffic_state in {"patchy", "thin"} and hours_text:
            detail_line = f"{current_name} is buried in review work during {hours_text}, and the front looks thinner than this hour ought to allow."
        elif traffic_state in {"patchy", "thin"} and requirement:
            detail_line = f"The staff here are buried in receipts and approvals, but the real tell is how thin the public side has gone. Once they catch up, the front still wants {requirement}."
        elif traffic_state in {"patchy", "thin"}:
            detail_line = f"The front looks quiet at {current_name} for two reasons: the staff are catching up on paperwork, and the public side is not pulling people the way it should."
        elif hours_text and requirement:
            detail_line = f"{current_name} is chewing through approvals during {hours_text}. After that the front wants {requirement}."
        elif hours_text:
            detail_line = f"{current_name} is buried in review work during {hours_text}, so the public side is thinning out."
        elif requirement:
            detail_line = f"The staff here are buried in receipts and approvals. Once they catch up, the front still wants {requirement}."
        else:
            detail_line = f"The front looks quiet because staff at {current_name} are stuck catching up on receipts, approvals, and back-office spill."
        return {
            "local_line": local_line,
            "detail_line": detail_line,
            "lead_kind": "access" if requirement else "hours",
            "shared": False,
        }

    if event_phase == "manifest_check":
        local_line = f"They are holding a manifest check at {current_name} until the paperwork lines up."
        if hours_text and requirement:
            detail_line = f"Nothing is moving cleanly through {current_name} before {hours_text} unless it clears {requirement}."
        elif hours_text:
            detail_line = f"The crew is matching the manifest against the next receiving window at {current_name}, which is around {hours_text}."
        elif requirement:
            detail_line = f"The clipboard says the next load only moves once it clears {requirement} at {current_name}."
        else:
            detail_line = f"The crew here is stuck matching freight to paperwork before anything else leaves the edge of {current_name}."
        return {
            "local_line": local_line,
            "detail_line": detail_line,
            "lead_kind": "access" if requirement else "hours",
            "shared": False,
        }

    if event_phase == "school_run":
        if career == "guardian":
            local_line = f"Mornings at {current_name} are all bags, keys, and people trying not to miss the run."
            detail_line = (
                f"Give this stoop a little time and it clears back out. Right now everybody at {current_name} is trying to get the kids moving before the morning hardens."
            )
        else:
            local_line = "Everybody is rushing because nobody wants to be the one who makes the whole morning late."
            detail_line = (
                f"This frontage only looks crowded because the building is all backpacks, lunch kits, and half-finished goodbyes for a few minutes."
            )
        return {
            "local_line": local_line,
            "detail_line": detail_line,
            "lead_kind": "hours",
            "shared": False,
        }

    if event_phase == "neighbors_lingering":
        neighborhood_target = _business_event_neighborhood_target(sim, prop, rng=rng)
        target_anchor = _business_event_followup_anchor_fields(sim, neighborhood_target) if isinstance(neighborhood_target, dict) else {}
        target_name = ""
        target_label = ""
        target_hours_text = ""
        target_requirement = ""
        target_property_id = ""
        if isinstance(neighborhood_target, dict):
            target_name = str(target_anchor.get("anchor_site_name", "")).strip() or (
                str(neighborhood_target.get("name", neighborhood_target.get("id", "the place"))).strip() or "the place"
            )
            target_label = _business_event_followup_target_label(target_anchor)
            target_property_id = str(neighborhood_target.get("id", "") or "").strip()
            target_controller = _property_access_controller(sim, neighborhood_target)
            if isinstance(target_controller, dict):
                target_hours_text = _dialogue_hours_text(target_controller.get("opening_window"))
                target_requirement = _controller_access_requirement_text(target_controller)
        if career == "retiree":
            local_line = f"We sit outside {current_name} most evenings and trade notes on who is still awake on the block."
        else:
            local_line = f"Nobody on this stoop is in a hurry to head in yet, so the talk turns into neighborhood gossip and who's still open."
        if target_name and target_hours_text and target_requirement:
            detail_line = f"If you need something nearby, people here keep pointing at {target_label or target_name}; they usually run during {target_hours_text}, though they still want {target_requirement}."
        elif target_name and target_hours_text:
            detail_line = f"If you need something nearby, the stoop keeps recommending {target_label or target_name}. They are usually moving during {target_hours_text}."
        elif target_name and target_requirement:
            detail_line = f"People here keep pointing at {target_label or target_name} for anything nearby, but they still want {target_requirement} when you hit the door."
        elif target_name:
            detail_line = f"Most nights this little stoop circle ends up recommending {target_label or target_name} to anyone still looking for something nearby."
        else:
            detail_line = f"This frontage only looks busy because the neighbors at {current_name} are stretching out the evening and swapping block gossip before they head upstairs."
        return {
            "property_id": str(prop.get("id", "") or "").strip(),
            "target_property_id": target_property_id,
            "local_line": local_line,
            "detail_line": detail_line,
            "lead_kind": "access" if target_requirement and not target_hours_text else "hours",
            "shared": False,
        }

    if event_phase in _BUSINESS_EVENT_SETTLEMENT_PHASES:
        lead_kind = "access" if requirement else "hours"
        if event_phase == "help_wanted_board":
            if career == "hiring_lead":
                local_line = f"We posted what {current_name} needs because people keep asking if there is real work here."
            else:
                local_line = f"I am checking whether {current_name} has a shift that can turn into something steadier."
            if hours_text and requirement:
                detail_line = f"The help-wanted board at {current_name} is live during {hours_text}, but anyone stepping past the front still needs {requirement}."
            elif hours_text:
                detail_line = f"The help-wanted board at {current_name} is pulling job seekers through during {hours_text}."
            elif requirement:
                detail_line = f"The posted shift at {current_name} looks real, but the front still wants {requirement} before anyone gets inside."
            else:
                detail_line = f"The board at {current_name} is less gossip than offer: names, hours, and enough work for someone new to try staying."
        elif event_phase == "clinic_outreach":
            if career == "outreach_nurse":
                local_line = f"We are catching walk-ins outside {current_name} before small problems turn into hard ones."
            else:
                local_line = f"The outreach table at {current_name} is the first place today that did not ask me to already be sorted."
            if hours_text and requirement:
                detail_line = f"{current_name} is running outreach during {hours_text}. After the table clears, the front still wants {requirement}."
            elif hours_text:
                detail_line = f"{current_name} is using this outreach window during {hours_text} to catch people who might otherwise keep drifting."
            elif requirement:
                detail_line = f"The outreach table is public-facing, but anything deeper inside {current_name} still wants {requirement}."
            else:
                detail_line = f"The outreach table at {current_name} is handing out enough care, water, and names that a few people may stick nearby."
        elif event_phase == "day_labor_call":
            if career == "crew_lead":
                local_line = f"We are filling the crew list at {current_name}; anyone useful gets a name on the board."
            else:
                local_line = f"I am waiting to see if the crew list at {current_name} turns into a real shift."
            if hours_text and requirement:
                detail_line = f"{current_name} is calling hands during {hours_text}, though the gate still wants {requirement}."
            elif hours_text:
                detail_line = f"{current_name} is calling day labor through this window during {hours_text}, with loose hands trying to become regular faces."
            elif requirement:
                detail_line = f"The crew list at {current_name} is open enough to attract workers, but the gate still wants {requirement}."
            else:
                detail_line = f"The call sheet at {current_name} is turning idle hands into a temporary crew, and temporary is sometimes how people start belonging."
        elif event_phase == "commuter_orientation":
            if career == "station_guide":
                local_line = f"We are helping new arrivals at {current_name} figure out which route leads to work, shelter, or somebody who owes them."
            else:
                local_line = f"I just came through {current_name}; I am still deciding whether this stop is where I start over."
            if hours_text and requirement:
                detail_line = f"{current_name} is orienting arrivals during {hours_text}, while the staffed side still wants {requirement}."
            elif hours_text:
                detail_line = f"The orientation board at {current_name} is active during {hours_text}, catching people before they drift past the useful exits."
            elif requirement:
                detail_line = f"The route board is public, but the staffed side of {current_name} still wants {requirement}."
            else:
                detail_line = f"The route board at {current_name} is catching new arrivals with enough directions that some of them may stop drifting."
        elif event_phase == "tenant_meetup":
            if career == "new_tenant":
                local_line = f"I am new around {current_name}, so I am learning which door sticks and which neighbor actually knows things."
            else:
                local_line = f"The meetup at {current_name} is mostly names, keys, and people making sure the new face has somewhere to land."
            detail_line = f"The stoop outside {current_name} is doing soft introductions right now, the kind that can turn a newcomer into a resident if the building has room."
        else:
            if career == "new_arrival":
                local_line = f"I stopped at the table outside {current_name} because it looked like the first useful place to ask what happens next."
            elif career == "volunteer":
                local_line = f"We set up outside {current_name} because people who need help usually need it before they find the right door."
            else:
                local_line = f"The table outside {current_name} is small, but it is enough to make people pause instead of drifting past."
            detail_line = f"The mutual aid table at {current_name} is moving food, water, names, and work tips through the frontage; some of those names may stay local."
        return {
            "local_line": local_line,
            "detail_line": detail_line,
            "lead_kind": lead_kind,
            "shared": False,
        }

    if event_phase == "reset_scramble":
        if career == "dishwasher":
            local_line = f"The only reason {current_name} looks calm is that everything dirty is getting shoved through reset right now."
        else:
            local_line = f"We are flipping {current_name} between waves before the next service push lands on us."
        if hours_text and requirement:
            detail_line = f"{current_name} keeps running these short reset loops during {hours_text}. Outside that window the front still wants {requirement}."
        elif hours_text:
            detail_line = f"{current_name} is in one of those brief reset windows during {hours_text}, where the staff are trying to clear plates and re-set the room before the next wave."
        elif requirement:
            detail_line = f"The crew is using a quiet minute to reset {current_name}, but the front still wants {requirement} once the next wave hits."
        else:
            detail_line = f"This is the between-waves scramble at {current_name}: clear the mess, reset the room, and pretend it was always under control."
        return {
            "local_line": local_line,
            "detail_line": detail_line,
            "lead_kind": "access" if requirement else "hours",
            "shared": False,
        }

    if event_phase == "table_turnover":
        if traffic_state in {"patchy", "thin"} and career == "host":
            local_line = f"We keep clearing tables at {current_name}, but the room is refilling in fits instead of waves."
        elif career == "host":
            local_line = f"We barely clear a table at {current_name} before the next party wants it."
        elif traffic_state in {"patchy", "thin"}:
            local_line = f"The room at {current_name} is still turning, but not every clean table is getting claimed as fast as it should."
        else:
            local_line = f"The room is turning over so fast nobody at {current_name} gets to admire a clean table for long."
        if traffic_state in {"patchy", "thin"} and hours_text and requirement:
            detail_line = f"{current_name} is still flipping tables during {hours_text}, but the room is not refilling cleanly. Once the softer rush loosens, the front still wants {requirement}."
        elif traffic_state in {"patchy", "thin"} and hours_text:
            detail_line = f"{current_name} is in turnover during {hours_text}, but the public room feels patchier than a true crush should."
        elif traffic_state in {"patchy", "thin"} and requirement:
            detail_line = f"They are trying to keep the room moving at {current_name}, but the next wave is landing unevenly. Once it settles, the front still wants {requirement}."
        elif traffic_state in {"patchy", "thin"}:
            detail_line = f"The public room at {current_name} is still turning tables, but not with the clean relentless pull a healthy rush usually has."
        elif hours_text and requirement:
            detail_line = f"{current_name} is in its turnover crush during {hours_text}. Once the rush loosens, the front still wants {requirement}."
        elif hours_text:
            detail_line = f"{current_name} is in its turnover crunch during {hours_text}, with staff flipping tables as fast as they clear."
        elif requirement:
            detail_line = f"They are trying to keep the room moving at {current_name}; once the rush breaks, the front still wants {requirement}."
        else:
            detail_line = f"The public room at {current_name} is stuck in that fast-turning stretch where every clean setting already belongs to the next party."
        return {
            "local_line": local_line,
            "detail_line": detail_line,
            "lead_kind": "access" if requirement else "hours",
            "shared": False,
        }

    if event_phase == "barback_reset":
        if traffic_state in {"patchy", "thin"} and career == "bartender":
            local_line = f"We are reloading {current_name}, but the late crowd is landing softer than a room like this should."
        elif career == "bartender":
            local_line = f"We are trying to reload {current_name} before the late side of the night notices the gaps."
        elif traffic_state in {"patchy", "thin"}:
            local_line = f"The late rhythm at {current_name} is still running, just not with the crowd pressure that usually hides the reset loop."
        else:
            local_line = f"The late rhythm here runs on ice, glass, and whoever can keep the reset loop moving."
        if traffic_state in {"patchy", "thin"} and hours_text and requirement:
            detail_line = f"{current_name} is running a late restock during {hours_text}, but the room feels softer than it should for this stretch. Once it steadies, the front still wants {requirement}."
        elif traffic_state in {"patchy", "thin"} and hours_text:
            detail_line = f"{current_name} is in a late reset pocket during {hours_text}, and the thinner-than-usual crowd is making the gaps easier to see."
        elif traffic_state in {"patchy", "thin"} and requirement:
            detail_line = f"They are reloading the late-service side of {current_name}, but the room is not pressing the front the way it usually would. The front still wants {requirement} once it steadies."
        elif traffic_state in {"patchy", "thin"}:
            detail_line = f"This is the late reset loop at {current_name}, but with enough slack in the room that the missing crowd is part of the story."
        elif hours_text and requirement:
            detail_line = f"{current_name} is running a late restock during {hours_text}. Once the room settles, the front still wants {requirement}."
        elif hours_text:
            detail_line = f"{current_name} is in a late reset pocket during {hours_text}, all glass runs, ice checks, and quick bottle counts."
        elif requirement:
            detail_line = f"They are reloading the late-service side of {current_name}, and the front still wants {requirement} once the room steadies."
        else:
            detail_line = f"This is the late reset loop at {current_name}: top off the glass, refill the ice, and keep the room from noticing what ran out."
        return {
            "local_line": local_line,
            "detail_line": detail_line,
            "lead_kind": "access" if requirement else "hours",
            "shared": False,
        }

    if event_phase == "loading_push":
        if career == "dockhand":
            local_line = f"The freight only looks chaotic at {current_name} because the crew is shoving it through in short bursts instead of letting it stack."
        else:
            local_line = f"We are trying to clear the load at {current_name} before the next burst lands on top of this one."
        if hours_text and requirement:
            detail_line = f"{current_name} is in a loading push during {hours_text}. Once the gate calms down, the front still wants {requirement}."
        elif hours_text:
            detail_line = f"{current_name} is in one of those short loading bursts during {hours_text}, where freight starts moving faster than anyone wants to narrate."
        elif requirement:
            detail_line = f"The crew is trying to keep freight from backing up at {current_name}, but the front still wants {requirement} once the push eases."
        else:
            detail_line = f"This is the kind of start-stop load pressure at {current_name} where everything moves in bursts and nobody trusts the stack to stay where it was."
        return {
            "local_line": local_line,
            "detail_line": detail_line,
            "lead_kind": "access" if requirement else "hours",
            "shared": False,
        }

    if event_phase == "boarding_crush":
        target_prop = _business_event_followup_target(
            sim,
            prop,
            scene_type="shift",
            category="transit" if category == "transit" else category,
            rng=rng,
        )
        target_anchor = _business_event_followup_anchor_fields(sim, target_prop) if isinstance(target_prop, dict) else {}
        target_name = str(target_anchor.get("anchor_site_name", "")).strip() if target_anchor else ""
        target_label = _business_event_followup_target_label(target_anchor) if target_anchor else target_name
        target_property_id = str(target_prop.get("id", "") or "").strip() if isinstance(target_prop, dict) else ""
        if target_property_id == str(prop.get("id", "") or "").strip():
            target_name = ""
            target_label = ""
            target_property_id = ""
        time_text = _business_event_time_point_text(sim, offset_hours=1 + rng.randint(0, 2))
        if career == "dispatcher":
            local_line = (
                f"We are trying to board {current_name} cleanly"
                + (
                    f" so the next connection for {target_name} holds at {time_text}."
                    if target_name
                    else " before the whole stop folds back on itself."
                )
            )
        elif career == "commuter":
            local_line = (
                f"If this line at {current_name} stalls, half the people here miss the clean window"
                + (f" for {target_name}." if target_name else ".")
            )
        else:
            local_line = (
                f"The stop only looks messy because {current_name} is trying to clear a boarding crush"
                + (f" toward {target_name}." if target_name else " before the posted run slips.")
            )
        if target_name and hours_text and requirement:
            detail_line = (
                f"{current_name} is boarding hard during {hours_text}. Staff keep calling {target_label or target_name} for around {time_text}, "
                f"but the stop still wants {requirement} while the line is hot."
            )
        elif target_name and hours_text:
            detail_line = f"{current_name} is in a boarding crush during {hours_text}, with the clean next connection toward {target_label or target_name} getting called for around {time_text}."
        elif target_name and requirement:
            detail_line = f"They are trying to clear this boarding crush at {current_name} without losing the {target_label or target_name} connection around {time_text}, and the stop still wants {requirement}."
        elif target_name:
            detail_line = f"Fare talk at {current_name} keeps circling back to {target_label or target_name} as the next clean connection once this boarding crush finally clears."
        elif hours_text and requirement:
            detail_line = f"{current_name} is boarding hard during {hours_text}, and the stop still wants {requirement} while fares, bags, and shouted directions knot up at the edge."
        elif hours_text:
            detail_line = f"{current_name} is in a boarding crush during {hours_text}, all clipped departure calls, fare checks, and people trying to hit the line before it closes."
        elif requirement:
            detail_line = f"The boarding crush at {current_name} has fares and bags bunching at the edge, and the stop still wants {requirement} once the pressure breaks."
        else:
            detail_line = f"This is a boarding crush at {current_name}: fare checks, destination calls, and a stop suddenly honest about how many lives are trying to move through it."

        opportunity = {}
        if isinstance(target_prop, dict) and target_property_id:
            target_chunk = sim.chunk_coords(int(target_prop.get("x", 0)), int(target_prop.get("y", 0)))
            opportunity = _business_event_enrich_followup_opportunity(sim, {
                "key": f"business_scene_followup:{scene_id}:{target_property_id}:boarding_crush",
                "title": f"Connection Lead: {target_name}",
                "summary": f"Boarding chatter at {current_name} points to a clean connection at {target_label or target_name} around {time_text}.",
                "kind": "lead_followup",
                "source": "business_scene",
                "chunk": target_chunk,
                "location": "lead",
                "playstyles": ("social", "economic", "stealth"),
                "reward": {"credits": 4, "intel": 2},
                "risk": "low",
                "pressure": "low",
                "requirements": {
                    "visit_chunk": target_chunk,
                    "property_id": target_property_id,
                    "property_name": target_name,
                },
                "status": "active",
                "seed_tick": int(getattr(sim, "tick", 0)),
            }, target_prop)
        return {
            "property_id": str(prop.get("id", "") or "").strip(),
            "target_property_id": target_property_id,
            "local_line": local_line,
            "detail_line": detail_line,
            "lead_kind": "access" if requirement else "hours",
            "opportunity": opportunity,
            "shared": False,
        }

    if event_phase == "arrival_handoff":
        target_prop = _business_event_followup_target(
            sim,
            prop,
            scene_type="delivery",
            category=category,
            rng=rng,
        )
        target_anchor = _business_event_followup_anchor_fields(sim, target_prop) if isinstance(target_prop, dict) else {}
        target_name = str(target_anchor.get("anchor_site_name", "")).strip() if target_anchor else ""
        target_label = _business_event_followup_target_label(target_anchor) if target_anchor else target_name
        target_property_id = str(target_prop.get("id", "") or "").strip() if isinstance(target_prop, dict) else ""
        if target_property_id == str(prop.get("id", "") or "").strip():
            target_name = ""
            target_label = ""
            target_property_id = ""
        target_controller = _property_access_controller(sim, target_prop) if isinstance(target_prop, dict) else None
        target_hours_text = _dialogue_hours_text(target_controller.get("opening_window")) if isinstance(target_controller, dict) else ""
        target_requirement = _controller_access_requirement_text(target_controller) if isinstance(target_controller, dict) else ""
        time_text = _business_event_time_point_text(sim, offset_hours=1 + rng.randint(1, 3))
        if career == "specialist":
            local_line = (
                f"I came through {current_name} because somebody farther in is short enough on hands to pay for the trip"
                + (f" to {target_name}." if target_name else ".")
            )
        elif career == "dispatcher":
            local_line = (
                f"This arrival is not meant to stay at {current_name}; we are turning it onward"
                + (f" to {target_name} once the handoff is clean." if target_name else " as soon as the handoff is clean.")
            )
        else:
            local_line = (
                f"They are meeting an incoming transfer at {current_name}"
                + (f" and pointing it toward {target_name} before the frontage clogs." if target_name else " before the frontage clogs.")
            )
        if target_name and target_hours_text and target_requirement:
            detail_line = f"The arrival board at {current_name} says the incoming relief for {target_label or target_name} should land around {time_text}. They usually move during {target_hours_text}, though they still want {target_requirement}."
        elif target_name and target_hours_text:
            detail_line = f"Transit chatter at {current_name} says the incoming transfer for {target_label or target_name} is supposed to land around {time_text}, and they usually receive it during {target_hours_text}."
        elif target_name and target_requirement:
            detail_line = f"Someone coming through {current_name} is supposed to push onward to {target_label or target_name} around {time_text}, but they still want {target_requirement} at the door."
        elif target_name:
            detail_line = f"Transit talk at {current_name} says this incoming handoff is bound for {target_label or target_name} around {time_text}, the kind of transfer that usually means somebody there is short on either staff or supplies."
        elif hours_text and requirement:
            detail_line = f"{current_name} is handling an arrival handoff during {hours_text}, and the stop still wants {requirement} while inbound riders, relief bags, and pickup chatter bunch at the edge."
        elif hours_text:
            detail_line = f"{current_name} is running an arrival handoff during {hours_text}, with incoming riders, quick greetings, and onward directions clipping the frontage."
        elif requirement:
            detail_line = f"Inbound riders and pickup chatter are bunching at {current_name}, and the stop still wants {requirement} once the handoff clears."
        else:
            detail_line = f"This is an arrival handoff at {current_name}: incoming riders, relief pickups, and the sense that somebody here came from farther out because they were needed."

        opportunity = {}
        if isinstance(target_prop, dict) and target_property_id:
            target_chunk = sim.chunk_coords(int(target_prop.get("x", 0)), int(target_prop.get("y", 0)))
            opportunity = _business_event_enrich_followup_opportunity(sim, {
                "key": f"business_scene_followup:{scene_id}:{target_property_id}:arrival_handoff",
                "title": f"Arrival Lead: {target_name}",
                "summary": f"Transit chatter says an incoming transfer through {current_name} is headed to {target_label or target_name} around {time_text}.",
                "kind": "lead_followup",
                "source": "business_scene",
                "chunk": target_chunk,
                "location": "lead",
                "playstyles": ("social", "economic", "stealth"),
                "reward": {"credits": 5, "intel": 3},
                "risk": "low",
                "pressure": "low",
                "requirements": {
                    "visit_chunk": target_chunk,
                    "property_id": target_property_id,
                    "property_name": target_name,
                },
                "status": "active",
                "seed_tick": int(getattr(sim, "tick", 0)),
            }, target_prop)
        return {
            "property_id": str(prop.get("id", "") or "").strip(),
            "target_property_id": target_property_id,
            "local_line": local_line,
            "detail_line": detail_line,
            "lead_kind": "access" if target_requirement else "hours",
            "opportunity": opportunity,
            "shared": False,
        }

    if event_phase == "dispatch_surge":
        target_prop = _business_event_followup_target(
            sim,
            prop,
            scene_type="shift",
            category=category,
            rng=rng,
        )
        target_anchor = _business_event_followup_anchor_fields(sim, target_prop) if isinstance(target_prop, dict) else {}
        target_name = str(target_anchor.get("anchor_site_name", "")).strip() if target_anchor else ""
        target_label = _business_event_followup_target_label(target_anchor) if target_anchor else target_name
        target_property_id = str(target_prop.get("id", "") or "").strip() if isinstance(target_prop, dict) else ""
        time_text = _business_event_time_point_text(sim, offset_hours=1 + rng.randint(1, 3))
        if career == "dispatcher":
            local_line = (
                f"Dispatch is trying to keep {current_name} from clogging up, "
                + (f"and the next handoff is pointed at {target_name} around {time_text}." if target_name else "with the next handoff already being called.")
            )
        else:
            local_line = (
                f"Everything here is being routed in a hurry, "
                + (f"with another stop lined up at {target_name} around {time_text}." if target_name else "and nobody wanting to be the reason the line stalls.")
            )
        if target_name and hours_text and requirement:
            detail_line = f"The dispatch board says {target_label or target_name} is the next useful stop after {current_name}, around {time_text}. Until then the front still wants {requirement}."
        elif target_name and hours_text:
            detail_line = f"Dispatch talk says the next useful handoff after {current_name} lands at {target_label or target_name} around {time_text}, while this window is still hot during {hours_text}."
        elif target_name and requirement:
            detail_line = f"They keep routing people from {current_name} toward {target_label or target_name} around {time_text}, but this frontage still wants {requirement} while the surge is live."
        elif target_name:
            detail_line = f"The dispatch chatter here keeps circling back to {target_label or target_name} as the next handoff once {current_name} finishes clearing the current burst."
        elif hours_text and requirement:
            detail_line = f"{current_name} is running a dispatch surge during {hours_text}, and the front still wants {requirement} while traffic is clipping the edge of the site."
        elif hours_text:
            detail_line = f"{current_name} is in a dispatch surge during {hours_text}, with routes getting called faster than the frontage can hide it."
        elif requirement:
            detail_line = f"The dispatch chatter at {current_name} is spilling outward, but the front still wants {requirement} while the site is routing the next burst."
        else:
            detail_line = f"This is a dispatch surge at {current_name}: route calls, clipped orders, and just enough edge traffic to make the site readable from the street."

        opportunity = {}
        if isinstance(target_prop, dict) and target_property_id:
            target_chunk = sim.chunk_coords(int(target_prop.get("x", 0)), int(target_prop.get("y", 0)))
            opportunity = _business_event_enrich_followup_opportunity(sim, {
                "key": f"business_scene_followup:{scene_id}:{target_property_id}:dispatch_surge",
                "title": f"Dispatch Lead: {target_name}",
                "summary": f"Dispatch chatter points to {target_label or target_name} around {time_text}.",
                "kind": "lead_followup",
                "source": "business_scene",
                "chunk": target_chunk,
                "location": "lead",
                "playstyles": ("social", "stealth", "economic"),
                "reward": {"credits": 5, "intel": 2},
                "risk": "low",
                "pressure": "low",
                "requirements": {
                    "visit_chunk": target_chunk,
                    "property_id": target_property_id,
                    "property_name": target_name,
                },
                "status": "active",
                "seed_tick": int(getattr(sim, "tick", 0)),
            }, target_prop)
        return {
            "property_id": str(prop.get("id", "") or "").strip(),
            "target_property_id": target_property_id,
            "local_line": local_line,
            "detail_line": detail_line,
            "lead_kind": "access" if requirement else "hours",
            "opportunity": opportunity,
            "shared": False,
        }

    if event_phase == "taped_off_front":
        aftermath = _business_event_aftermath_entry(sim, prop) or {}
        casualty_count = max(0, int(aftermath.get("casualty_count", 0) or 0))
        incident_kind = str(aftermath.get("incident_kind", "violence") or "violence").strip().lower() or "violence"
        if career == "site_rep":
            local_line = f"We are keeping the frontage at {current_name} held for a minute because what happened out here is still too fresh."
        elif career == "resident":
            local_line = f"Nobody near {current_name} is ready to shrug and walk off yet, so people keep clustering right here and trading what they saw."
        else:
            local_line = f"People are still held at the front of {current_name} because nobody wants to be the one who pretends this doorway is normal already."
        if casualty_count > 0 and hours_text and requirement:
            detail_line = f"Somebody died close enough to {current_name} that the door is still half held and the front still wants {requirement} once they let people flow again during {hours_text}."
        elif casualty_count > 0:
            detail_line = f"The doorway at {current_name} is still being held after a fatal scene close by, with tape and low voices keeping everyone from moving on yet."
        elif incident_kind == "hazard" and hours_text:
            detail_line = f"They have the front of {current_name} held because a bad spill or hazard just turned the doorway into a caution line during {hours_text}."
        elif incident_kind == "hazard":
            detail_line = f"The front of {current_name} is still half held because a nasty hazard turned the doorway into a caution line."
        elif hours_text and requirement:
            detail_line = f"Somebody got hurt close enough to {current_name} that the frontage is still half taped and the front still wants {requirement} once the hold loosens during {hours_text}."
        elif hours_text:
            detail_line = f"Somebody got hurt close enough to {current_name} that the frontage is still half taped while the place tries to settle back into its usual hours during {hours_text}."
        else:
            detail_line = f"Somebody got hurt close enough to {current_name} that the frontage is still all tape, witnesses, and people talking low instead of walking through."
        return {
            "local_line": local_line,
            "detail_line": detail_line,
            "lead_kind": "access" if requirement else "hours",
            "shared": False,
        }

    if event_phase == "cleanup_detail":
        aftermath = _business_event_aftermath_entry(sim, prop) or {}
        casualty_count = max(0, int(aftermath.get("casualty_count", 0) or 0))
        incident_kind = str(aftermath.get("incident_kind", "violence") or "violence").strip().lower() or "violence"
        if career in {"cleanup_crew", "sanitation_worker", "maintenance_tech"}:
            local_line = f"We are trying to clear the front of {current_name} and get it back to something people can step through."
        else:
            local_line = f"The people out here are not lingering for fun; they are trying to scrub the last of the trouble off {current_name}."
        if casualty_count > 0 and hours_text and requirement:
            detail_line = f"{current_name} is being reset after a fatal scene at the door. Once the cleanup crew finishes, the front still wants {requirement} during {hours_text}."
        elif casualty_count > 0:
            detail_line = f"The crew outside {current_name} is doing the slower kind of cleanup that only happens after somebody died close enough to leave the door feeling wrong."
        elif incident_kind == "hazard" and hours_text:
            detail_line = f"{current_name} is running a hazard cleanup at the frontage during {hours_text}, all cones, wipes, and workers trying to make the doorway usable again."
        elif incident_kind == "hazard":
            detail_line = f"The crew outside {current_name} is cleaning up a nasty hazard at the doorway before anybody trusts the frontage again."
        elif hours_text and requirement:
            detail_line = f"{current_name} is still clearing the frontage after somebody got hurt nearby. Once the cleanup crew peels off, the front still wants {requirement} during {hours_text}."
        else:
            detail_line = f"The crew outside {current_name} is scrubbing down the last visible signs of recent trouble so the doorway can pass for ordinary again."
        return {
            "local_line": local_line,
            "detail_line": detail_line,
            "lead_kind": "access" if requirement else "hours",
            "shared": False,
        }

    if event_phase == "candle_vigil":
        if career == "resident":
            local_line = f"People from {current_name} came out with candles because leaving this doorway dark felt worse."
        else:
            local_line = f"Nobody here is trying to turn this into a crowd; they just did not want what happened at {current_name} to pass without a mark."
        if hours_text and requirement:
            detail_line = f"The candles outside {current_name} are for somebody the block has not finished grieving yet. When the building settles back into hours during {hours_text}, the front still wants {requirement}."
        else:
            detail_line = f"The little vigil outside {current_name} is the block's way of admitting that what happened here still feels too fresh to walk past without stopping."
        return {
            "local_line": local_line,
            "detail_line": detail_line,
            "lead_kind": "hours",
            "shared": False,
        }

    if event_phase == "street_triage":
        if career in {"triage_nurse", "combat_medic", "trauma_doctor", "medic", "paramedic"} or role == "worker":
            local_line = f"We are trying to keep the hurt people outside {current_name} stable long enough to move them."
            if hours_text and requirement:
                detail_line = f"{current_name} is running curbside treatment during {hours_text}. After that the front still wants {requirement}."
            elif hours_text:
                detail_line = f"The medic is working the frontage at {current_name} because it is the fastest place to stabilize them during {hours_text}."
            elif requirement:
                detail_line = f"They pulled treatment out to the frontage at {current_name}; once the hurt are moving again, the front still wants {requirement}."
            else:
                detail_line = f"Somebody got torn up badly enough that the nearest workable patch of ground at {current_name} turned into a treatment spot."
        else:
            local_line = "They are trying to get me steady enough to move without dropping me."
            if hours_text:
                detail_line = f"They dragged me to {current_name} because it was the closest place someone could work on me during {hours_text}."
            else:
                detail_line = f"They hauled me over to {current_name} because it was the nearest place with enough light and room to stop the bleeding."
        return {
            "local_line": local_line,
            "detail_line": detail_line,
            "lead_kind": "access" if requirement else "hours",
            "shared": False,
        }

    if event_phase == "maintenance_loop":
        return {}

    chance = 0.38
    if scene_type == "delivery" and career in {"courier", "receiver"}:
        chance = 1.0 if career == "courier" else 0.62
    elif scene_type == "shift":
        chance = 0.58
    elif scene_type == "queue":
        if career == "late_patron":
            chance = 0.46
        elif career == "patient":
            chance = 0.34
        else:
            chance = 0.4
    if rng.random() > chance:
        return {}

    target_prop = _business_event_followup_target(
        sim,
        prop,
        scene_type=scene_type,
        category=category,
        rng=rng,
    )
    if not isinstance(target_prop, dict):
        return {}
    target_anchor = _business_event_followup_anchor_fields(sim, target_prop)
    target_name = str(target_anchor.get("anchor_site_name", "")).strip() or (
        str(target_prop.get("name", target_prop.get("id", "the place"))).strip() or "the place"
    )
    target_label = _business_event_followup_target_label(target_anchor)
    time_text = _business_event_time_point_text(sim, offset_hours=1 + rng.randint(1, 3))
    org_snapshot = _organization_snapshot(sim, prop=prop, ensure=True)
    org_name = str((org_snapshot or {}).get("organization_name", "") or "").strip()
    org_label = org_name or current_name

    if scene_type == "delivery":
        title = f"Next Drop: {target_name}"
        summary = f"Courier chatter points to another delivery at {target_label or target_name} around {time_text}."
        local_line = f"After this stop, somebody is supposed to hit {target_name} around {time_text}."
        detail_line = f"They are running one more drop after {current_name}: {target_label or target_name} around {time_text}."
        lead_kind = "hours"
        reward = {"credits": 6, "intel": 2}
    elif scene_type == "queue":
        if category in {"hospitality", "entertainment"}:
            title = f"Follow-Up Meet: {target_name}"
            summary = f"Crowd chatter around {current_name} points to a follow-up meet at {target_label or target_name} around {time_text}."
            local_line = (
                f"This crowd is riding a bigger win for {org_label}, and people keep pointing at {target_name} later."
            )
            detail_line = (
                f"Word is {org_label} just landed something worth celebrating, and a follow-up meet is supposed to hit "
                f"{target_label or target_name} around {time_text}."
            )
        else:
            title = f"Spillover Lead: {target_name}"
            summary = f"The line outside {current_name} sounds tied to another stop at {target_label or target_name} around {time_text}."
            local_line = f"Some of this line is going to peel off toward {target_name} around {time_text}."
            detail_line = f"People here keep saying the next useful stop after {current_name} is {target_label or target_name} around {time_text}."
        lead_kind = "hours"
        reward = {"credits": 4, "intel": 2}
    elif scene_type == "shift":
        title = f"Shift Lead: {target_name}"
        summary = f"Shift chatter says {target_label or target_name} gets the next handoff around {time_text}."
        local_line = f"People here keep talking about the next handoff at {target_name} around {time_text}."
        detail_line = f"Supervisor talk says the next handoff or check-in lands at {target_label or target_name} around {time_text}."
        lead_kind = "access"
        reward = {"credits": 5, "intel": 2}
    else:
        return {}

    target_chunk = sim.chunk_coords(int(target_prop.get("x", 0)), int(target_prop.get("y", 0)))
    opportunity = _business_event_enrich_followup_opportunity(sim, {
        "key": f"business_scene_followup:{scene_id}:{target_prop.get('id') or target_name.lower()}:{event_phase or scene_type}",
        "title": title,
        "summary": summary,
        "kind": "lead_followup",
        "source": "business_scene",
        "chunk": target_chunk,
        "location": "lead",
        "playstyles": ("social", "stealth", "economic"),
        "reward": reward,
        "risk": "low",
        "pressure": "low",
        "requirements": {
            "visit_chunk": target_chunk,
            "property_id": str(target_prop.get("id", "") or "").strip(),
            "property_name": target_name,
        },
        "status": "active",
        "seed_tick": int(getattr(sim, "tick", 0)),
    }, target_prop)
    return {
        "property_id": str(prop.get("id", "") or "").strip(),
        "target_property_id": str(target_prop.get("id", "") or "").strip(),
        "local_line": local_line,
        "detail_line": detail_line,
        "lead_kind": lead_kind,
        "opportunity": opportunity,
        "shared": False,
    }


def _business_event_followup_seed(sim, scene, prop, *, rng):
    if not isinstance(prop, dict):
        return None
    if str((scene or {}).get("source_kind", "") or "").strip().lower() == "seed":
        return None

    scene_type = str((scene or {}).get("scene_type", "") or "").strip().lower()
    category = str((scene or {}).get("category", "") or "").strip().lower()
    scene_id = str((scene or {}).get("scene_id", "") or "").strip()
    event_phase = str((scene or {}).get("event_phase", "") or "").strip().lower()
    if not scene_id:
        return None

    kind = ""
    title = ""
    summary = ""
    local_line = ""
    detail_line = ""
    lead_kind = "hours"
    reward = {"credits": 4, "intel": 1}
    blueprint = None
    offset_hours = 0
    duration_ticks = 0

    target_prop = None
    current_name = str(prop.get("name", prop.get("id", "this place"))).strip() or "this place"
    org_snapshot = _organization_snapshot(sim, prop=prop, ensure=True)
    org_name = str((org_snapshot or {}).get("organization_name", "") or "").strip()
    org_label = org_name or current_name

    if scene_type == "delivery":
        target_prop = _business_event_followup_target(
            sim,
            prop,
            scene_type="delivery",
            category=category,
            rng=rng,
        )
        if not isinstance(target_prop, dict):
            return None
        if str(target_prop.get("id", "") or "").strip() == str(prop.get("id", "") or "").strip():
            return None
        target_category = _business_event_property_category(sim, target_prop) or category
        target_anchor = _business_event_followup_anchor_fields(sim, target_prop)
        offset_hours = 1 + rng.randint(0, 2)
        duration_ticks = max(90, _business_event_ticks_per_hour(sim) // 2)
        time_text = _business_event_time_point_text(sim, offset_hours=offset_hours)
        target_name = str(target_anchor.get("anchor_site_name", "")).strip() or (
            str(target_prop.get("name", target_prop.get("id", "the place"))).strip() or "the place"
        )
        target_label = _business_event_followup_target_label(target_anchor)
        kind = "next_delivery"
        title = f"Next Drop: {target_name}"
        summary = f"Courier chatter points to another delivery at {target_label or target_name} around {time_text}."
        local_line = f"After this stop, somebody is supposed to hit {target_name} around {time_text}."
        detail_line = f"They are running one more drop after {current_name}: {target_label or target_name} around {time_text}."
        reward = {"credits": 6, "intel": 2}
        blueprint = _business_event_delivery_blueprint(target_category)
    elif scene_type == "queue" and category in {"hospitality", "entertainment", "retail", "office", "finance"}:
        target_prop = _business_event_followup_target(
            sim,
            prop,
            scene_type="queue",
            category=category,
            rng=rng,
        )
        if not isinstance(target_prop, dict):
            return None
        if str(target_prop.get("id", "") or "").strip() == str(prop.get("id", "") or "").strip():
            return None
        target_category = _business_event_property_category(sim, target_prop) or category
        target_anchor = _business_event_followup_anchor_fields(sim, target_prop)
        offset_hours = 2 + rng.randint(0, 3)
        duration_ticks = max(120, int(_business_event_ticks_per_hour(sim) * 0.75))
        time_text = _business_event_time_point_text(sim, offset_hours=offset_hours)
        target_name = str(target_anchor.get("anchor_site_name", "")).strip() or (
            str(target_prop.get("name", target_prop.get("id", "the place"))).strip() or "the place"
        )
        target_label = _business_event_followup_target_label(target_anchor)
        kind = "celebration_meet"
        title = f"Celebration Meet: {target_name}"
        summary = f"Crowd chatter around {current_name} points to a nearby meet at {target_label or target_name} around {time_text}."
        local_line = f"This crowd is riding a bigger win for {org_label}, and people keep pointing at {target_name} later."
        detail_line = (
            f"Word is {org_label} just landed something worth celebrating, and a follow-up meet is supposed to hit "
            f"{target_label or target_name} around {time_text}."
        )
        reward = {"credits": 5, "intel": 2}
        blueprint = _business_event_gathering_blueprint(target_category)
    else:
        return None

    if not isinstance(target_prop, dict) or not isinstance(blueprint, dict):
        return None

    target_chunk = sim.chunk_coords(int(target_prop.get("x", 0)), int(target_prop.get("y", 0)))
    seed_tick = int(getattr(sim, "tick", 0) or 0)
    start_tick = seed_tick + (offset_hours * _business_event_ticks_per_hour(sim))
    end_tick = start_tick + max(60, int(duration_ticks))
    target_name = str(target_prop.get("name", target_prop.get("id", "the place"))).strip() or "the place"
    target_property_id = str(target_prop.get("id", "") or "").strip()
    return {
        "key": f"business_seed:{scene_id}:{kind}:{target_property_id}:{event_phase or scene_type}",
        "source_scene_id": scene_id,
        "source_property_id": str(prop.get("id", "") or "").strip(),
        "target_property_id": target_property_id,
        "target_chunk": target_chunk,
        "kind": kind,
        "category": str(_business_event_property_category(sim, target_prop) or category).strip().lower(),
        "source_category": category,
        "start_tick": int(start_tick),
        "end_tick": int(end_tick),
        "created_tick": seed_tick,
        "depth": 1,
        "lead_kind": lead_kind,
        "local_line": local_line,
        "detail_line": detail_line,
        "shared": False,
        "blueprint": dict(blueprint),
        "priority_score": 18.0 if kind == "next_delivery" else 16.5,
        "opportunity": _business_event_enrich_followup_opportunity(sim, {
            "key": f"business_scene_followup:{scene_id}:{target_property_id}:{kind}",
            "title": title,
            "summary": summary,
            "kind": "lead_followup",
            "source": "business_scene",
            "chunk": target_chunk,
            "location": "lead",
            "playstyles": ("social", "stealth", "economic"),
            "reward": reward,
            "risk": "low",
            "pressure": "low",
            "requirements": {
                "visit_chunk": target_chunk,
                "property_id": target_property_id,
                "property_name": target_name,
            },
            "status": "active",
            "seed_tick": seed_tick,
        }, target_prop),
    }


def _business_event_consequence_seed(sim, scene, prop, seed, *, rng):
    scene = scene if isinstance(scene, dict) else {}
    prop = prop if isinstance(prop, dict) else None
    seed = seed if isinstance(seed, dict) else None
    if prop is None or seed is None:
        return None

    if int(seed.get("depth", 1) or 1) >= 2:
        return None

    kind = str(seed.get("kind", "") or "").strip().lower()
    category = str(seed.get("category", "") or "").strip().lower()
    archetype = _property_archetype(prop)
    is_medical_site = (
        archetype in MEDICAL_ARCHETYPES
        or "clinic" in archetype
        or "hospital" in archetype
    )
    consequence_category = category
    if is_medical_site:
        consequence_category = "medical"
    inspection_candidate = consequence_category in {"medical", "office", "finance"}
    if kind != "next_delivery" or not inspection_candidate:
        return None

    current_name = str(prop.get("name", prop.get("id", "this place"))).strip() or "this place"
    seed_id = str(seed.get("seed_id", "") or "").strip()
    if not seed_id:
        return None
    if rng is None:
        rng = random.Random(f"{getattr(sim, 'seed', 0)}:business-scene-consequence:{seed_id}")

    target_property_id = str(prop.get("id", "") or "").strip()
    if not target_property_id:
        return None

    offset_hours = 1 + rng.randint(0, 2)
    duration_ticks = max(120, int(_business_event_ticks_per_hour(sim) * 0.75))
    time_text = _business_event_time_point_text(sim, offset_hours=offset_hours)
    base_tick = max(int(seed.get("end_tick", 0) or 0), int(getattr(sim, "tick", 0) or 0))
    start_tick = base_tick + (offset_hours * _business_event_ticks_per_hour(sim))
    end_tick = start_tick + max(60, int(duration_ticks))
    blueprint = _business_event_inspection_blueprint(consequence_category)
    current_anchor = _business_event_followup_anchor_fields(sim, prop)
    return {
        "key": f"business_seed:{seed_id}:delivery_inspection:{target_property_id}:{category}",
        "source_scene_id": str(scene.get("scene_id", "") or "").strip(),
        "source_property_id": target_property_id,
        "target_property_id": target_property_id,
        "target_chunk": sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0))),
        "kind": "delivery_inspection",
        "category": consequence_category,
        "source_category": str(seed.get("source_category", category) or "").strip().lower(),
        "start_tick": int(start_tick),
        "end_tick": int(end_tick),
        "created_tick": int(getattr(sim, "tick", 0) or 0),
        "depth": int(seed.get("depth", 1) or 1) + 1,
        "lead_kind": "access",
        "local_line": f"The drop at {current_name} is drawing a quick inspection around {time_text}.",
        "detail_line": f"Word is the handoff at {current_name} is hot enough to pull inspectors around {time_text}.",
        "shared": False,
        "blueprint": dict(blueprint),
        "priority_score": 17.4,
        "parent_seed_id": seed_id,
        "opportunity": _business_event_enrich_followup_opportunity(sim, {
            "key": f"business_scene_followup:{seed_id}:{target_property_id}:delivery_inspection",
            "title": f"Inspection Check: {current_name}",
            "summary": f"The recent drop at {_business_event_followup_target_label(current_anchor)} is expected to draw a brief inspection around {time_text}.",
            "kind": "lead_followup",
            "source": "business_scene",
            "chunk": sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0))),
            "location": "lead",
            "playstyles": ("social", "stealth", "intel"),
            "reward": {"credits": 5, "intel": 3},
            "risk": "medium",
            "pressure": "medium",
            "requirements": {
                "visit_chunk": sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0))),
                "property_id": target_property_id,
                "property_name": current_name,
            },
            "status": "active",
            "seed_tick": int(getattr(sim, "tick", 0) or 0),
        }, prop),
    }


def _ensure_business_event_consequence_seed_for_scene(sim, scene, prop, *, rng):
    scene = scene if isinstance(scene, dict) else {}
    prop = prop if isinstance(prop, dict) else None
    if prop is None:
        return None
    if str(scene.get("source_kind", "") or "").strip().lower() != "seed":
        return None

    seed_id = str(scene.get("seed_id", "") or "").strip()
    if not seed_id:
        return None
    state = _business_event_seed_state(sim)
    active = state.setdefault("active", {})
    seed = active.get(seed_id)
    if not isinstance(seed, dict):
        return None

    consequence_seed_id = str(seed.get("consequence_seed_id", "") or "").strip()
    if consequence_seed_id and consequence_seed_id in active:
        return active[consequence_seed_id]

    consequence = _business_event_consequence_seed(sim, scene, prop, seed, rng=rng)
    if not isinstance(consequence, dict):
        return None

    for existing in active.values():
        if not isinstance(existing, dict):
            continue
        if str(existing.get("key", "") or "").strip() == str(consequence.get("key", "") or "").strip():
            existing_seed_id = str(existing.get("seed_id", "") or "").strip()
            if existing_seed_id:
                seed["consequence_seed_id"] = existing_seed_id
            return existing

    consequence_seed_id = _next_business_event_seed_id(sim)
    consequence["seed_id"] = consequence_seed_id
    active[consequence_seed_id] = consequence
    seed["consequence_seed_id"] = consequence_seed_id
    return consequence


def _ensure_business_event_seed_for_scene(sim, scene, prop, *, rng):
    scene = scene if isinstance(scene, dict) else {}
    followup_seed_id = str(scene.get("followup_seed_id", "") or "").strip()
    state = _business_event_seed_state(sim)
    active = state.setdefault("active", {})
    if followup_seed_id and followup_seed_id in active:
        return active[followup_seed_id]

    seed = _business_event_followup_seed(sim, scene, prop, rng=rng)
    if not isinstance(seed, dict):
        scene["followup_seed_id"] = ""
        return None

    for existing in active.values():
        if not isinstance(existing, dict):
            continue
        if str(existing.get("key", "") or "").strip() == str(seed.get("key", "") or "").strip():
            scene["followup_seed_id"] = str(existing.get("seed_id", "") or "").strip()
            return existing

    seed_id = _next_business_event_seed_id(sim)
    seed["seed_id"] = seed_id
    active[seed_id] = seed
    scene["followup_seed_id"] = seed_id
    return seed


def _prune_business_event_seeds(sim, *, active_scene_ids=()):
    state = _business_event_seed_state(sim)
    active = state.setdefault("active", {})
    live_scene_ids = {
        str(scene_id).strip()
        for scene_id in tuple(active_scene_ids or ())
        if str(scene_id).strip()
    }
    for seed_id, seed in list(active.items()):
        if not isinstance(seed, dict):
            active.pop(seed_id, None)
            continue
        source_property_id = str(seed.get("source_property_id", "") or "").strip()
        target_property_id = str(seed.get("target_property_id", "") or "").strip()
        if (source_property_id and source_property_id not in sim.properties) or not target_property_id or target_property_id not in sim.properties:
            active.pop(seed_id, None)
            continue
        if int(getattr(sim, "tick", 0) or 0) > int(seed.get("end_tick", 0) or 0) and f"seed:{seed_id}" not in live_scene_ids:
            active.pop(seed_id, None)

def _business_event_frontage_anchor(sim, prop):
    if not isinstance(prop, dict):
        return None
    metadata = _property_metadata(prop)
    entry = metadata.get("entry") if isinstance(metadata.get("entry"), dict) else None
    if entry is not None:
        try:
            anchor_source = (
                int(entry.get("x")),
                int(entry.get("y")),
                int(entry.get("z", prop.get("z", 0))),
            )
        except (TypeError, ValueError):
            anchor_source = None
    else:
        anchor_source = _property_focus_position(prop)
    if anchor_source is None:
        return None

    candidates = _adjacent_street_tiles(sim, anchor_source)
    if candidates:
        return candidates[0]
    if (
        sim.tilemap.is_walkable(int(anchor_source[0]), int(anchor_source[1]), int(anchor_source[2]))
        and not sim.structure_at(int(anchor_source[0]), int(anchor_source[1]), int(anchor_source[2]))
        and not sim.property_covering(int(anchor_source[0]), int(anchor_source[1]), int(anchor_source[2]))
    ):
        return (int(anchor_source[0]), int(anchor_source[1]), int(anchor_source[2]))
    return None


def _business_event_seed_scene_specs(sim, active_chunk, player_pos):
    if active_chunk is None or player_pos is None:
        return []
    specs = []
    tick = int(getattr(sim, "tick", 0) or 0)
    for seed in _business_event_seed_state(sim).get("active", {}).values():
        if not isinstance(seed, dict):
            continue
        if tick < int(seed.get("start_tick", 0) or 0) or tick > int(seed.get("end_tick", 0) or 0):
            continue
        target_property_id = str(seed.get("target_property_id", "") or "").strip()
        if not target_property_id:
            continue
        prop = sim.properties.get(target_property_id)
        if not isinstance(prop, dict):
            continue
        try:
            prop_chunk = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
        except (TypeError, ValueError):
            continue
        if prop_chunk != active_chunk:
            continue
        if sim.detail_for_xy(int(prop.get("x", 0)), int(prop.get("y", 0))) == "unloaded":
            continue
        anchor = _business_event_frontage_anchor(sim, prop)
        if anchor is None:
            continue
        if _manhattan(player_pos.x, player_pos.y, anchor[0], anchor[1]) <= 1:
            continue
        blueprint = dict(seed.get("blueprint", {}) or {})
        if not blueprint:
            continue
        distance = _manhattan(player_pos.x, player_pos.y, anchor[0], anchor[1])
        specs.append({
            "scene_id": f"seed:{str(seed.get('seed_id', '') or '').strip()}",
            "property_id": target_property_id,
            "prop": prop,
            "pulse": {
                "category": str(seed.get("category", "") or "").strip().lower(),
                "event_phase": str(seed.get("kind", "") or "").strip().lower(),
            },
            "anchor": anchor,
            "score": float(seed.get("priority_score", 16.0) or 16.0) - (float(distance) * 0.02),
            "blueprint": blueprint,
            "chunk": active_chunk,
            "seed_id": str(seed.get("seed_id", "") or "").strip(),
            "source_kind": "seed",
        })
    return specs

def _business_event_scene_fixture_interaction(sim, scene, prop, *, fixture_type="", rng):
    scene = scene if isinstance(scene, dict) else {}
    prop = prop if isinstance(prop, dict) else None
    if prop is None:
        return {}
    scene_type = str(scene.get("scene_type", "") or "").strip().lower()
    fixture_type = str(fixture_type or "").strip().lower()
    category = str(scene.get("category", "") or "").strip().lower()
    event_phase = str(scene.get("event_phase", "") or "").strip().lower()
    source_kind = str(scene.get("source_kind", "") or "").strip().lower()
    allow_pulse_cache = source_kind == "pulse" and event_phase in (
        _BUSINESS_EVENT_GATHERING_PHASES
        | _BUSINESS_EVENT_MEDICAL_RESPONSE_PHASES
        | _BUSINESS_EVENT_RESIDENTIAL_SOCIAL_PHASES
        | _BUSINESS_EVENT_SETTLEMENT_PHASES
        | _BUSINESS_EVENT_HOSPITALITY_PRESSURE_PHASES
        | _BUSINESS_EVENT_OPERATIONAL_PRESSURE_PHASES
        | _BUSINESS_EVENT_AFTERMATH_PHASES
    )
    if source_kind != "seed" and not allow_pulse_cache:
        return {}
    prop_name = str(prop.get("name", prop.get("id", "the site"))).strip() or "the site"
    controller = _property_access_controller(sim, prop)
    hours_text = _dialogue_hours_text(controller.get("opening_window")) if isinstance(controller, dict) else ""
    requirement = _controller_access_requirement_text(controller) if isinstance(controller, dict) else ""
    container_label = "Cargo"
    note = ""
    pool = []
    item_count = 1
    read_only_reason = "You can pull from the loose cargo, but this is no place to stash your own gear."

    if scene_type == "delivery" and fixture_type == "delivery_cargo":
        if hours_text and requirement:
            note = f"Manifest: {prop_name} takes receiving during {hours_text}. After that they want {requirement}."
        elif hours_text:
            note = f"Manifest: {prop_name} is expecting receiving during {hours_text}."
        elif requirement:
            note = f"Manifest: {prop_name} usually wants {requirement} at the handoff door."
        else:
            note = f"Manifest: {prop_name} is tagged for a quick curbside handoff."
        pool = [
            item_id
            for item_id in _business_event_item_pool(
                "delivery",
                category,
                {"role": "worker", "career": "courier"},
            )
            if item_id in ITEM_CATALOG
        ]
        if category in {"medical", "industrial", "transit"} or rng.random() < 0.45:
            item_count += 1
    elif scene_type == "shift" and fixture_type in {"reset_cart", "turnover_tray", "barback_crate", "loading_dolly", "dispatch_satchel", "cleanup_cart", "fare_rack", "transfer_clipboard"}:
        if fixture_type == "reset_cart" or event_phase == "reset_scramble":
            container_label = "Bus Tub"
            if hours_text and requirement:
                note = (
                    f"Bus tub: {prop_name} is between service waves during {hours_text}, clearing plates and resetting the room. "
                    f"After that the front still wants {requirement}."
                )
            elif hours_text:
                note = f"Bus tub: {prop_name} is in a short reset scramble during {hours_text}, trying to clear plates and re-set the room before the next wave."
            elif requirement:
                note = f"Bus tub: {prop_name} is using a quiet minute to reset the room, but the front still wants {requirement} when the next wave lands."
            else:
                note = f"Bus tub: {prop_name} is caught in a between-waves reset, all dirty plates, quick wipes, and the staff trying to get ahead of the next push."
            pool = [item_id for item_id in ("protein_wrap", "bottled_water", "caff_shot", "mint_strip") if item_id in ITEM_CATALOG]
            if rng.random() < 0.45:
                item_count += 1
            read_only_reason = "You can pocket something from the reset cart, but turning the staff bus tub into your personal locker would be a fast way to get noticed."
        elif fixture_type == "turnover_tray" or event_phase == "table_turnover":
            container_label = "Turnover Tray"
            if hours_text and requirement:
                note = (
                    f"Turnover tray: {prop_name} is flipping tables hard during {hours_text}. "
                    f"Once the rush loosens, the front still wants {requirement}."
                )
            elif hours_text:
                note = f"Turnover tray: {prop_name} is in a table-turnover crush during {hours_text}, with clean settings barely lasting long enough to count."
            elif requirement:
                note = f"Turnover tray: the crew at {prop_name} is trying to keep the room moving, and the front still wants {requirement} when the rush breaks."
            else:
                note = f"Turnover tray: {prop_name} is in that hard-turning stretch where every clean setting already belongs to the next party."
            pool = [item_id for item_id in ("meal_voucher", "caff_shot", "mint_strip", "bottled_water") if item_id in ITEM_CATALOG]
            item_count += 1
            read_only_reason = "You can pull something from the turnover tray, but stashing your own gear in active table reset kit would be asking for trouble."
        elif fixture_type == "barback_crate" or event_phase == "barback_reset":
            container_label = "Restock Crate"
            if hours_text and requirement:
                note = (
                    f"Restock crate: {prop_name} is running a late reload during {hours_text}, topping off glass and bottles. "
                    f"After that the front still wants {requirement}."
                )
            elif hours_text:
                note = f"Restock crate: {prop_name} is in a late barback reset during {hours_text}, all glass runs, ice checks, and quick bottle counts."
            elif requirement:
                note = f"Restock crate: the late-service side of {prop_name} is being reloaded, and the front still wants {requirement} once the room steadies."
            else:
                note = f"Restock crate: {prop_name} is running a late reset loop of glass, ice, and bottles to keep the room from noticing what ran low."
            pool = [item_id for item_id in ("spark_brew", "mint_strip", "caff_shot", "protein_wrap") if item_id in ITEM_CATALOG]
            item_count += 1
            if category == "entertainment":
                item_count += 1
            read_only_reason = "You can pull something from the restock crate, but using live bar reset stock as your stash would get ugly fast."
        elif fixture_type == "loading_dolly" or event_phase == "loading_push":
            container_label = "Freight Dolly"
            if hours_text and requirement:
                note = (
                    f"Freight dolly: {prop_name} is in a loading push during {hours_text}, clearing freight in short bursts. "
                    f"After that the front still wants {requirement}."
                )
            elif hours_text:
                note = f"Freight dolly: {prop_name} is in a short loading burst during {hours_text}, with cargo moving in start-stop pushes instead of a clean flow."
            elif requirement:
                note = f"Freight dolly: the crew at {prop_name} is trying to keep cargo from stacking up, but the front still wants {requirement} while the push is live."
            else:
                note = f"Freight dolly: {prop_name} is under load pressure, all clipped pushes, shifting stacks, and the crew trying to keep the next burst from landing on the last one."
            pool = [item_id for item_id in ("pocket_multitool", "battery_pack", "protein_wrap", "caff_shot") if item_id in ITEM_CATALOG]
            item_count += 1
            if category == "transit":
                pool.extend(item_id for item_id in ("city_pass_token", "transit_daypass") if item_id in ITEM_CATALOG)
            read_only_reason = "You can pull something from the freight dolly, but using live load gear as your own stash would slow the crew down fast."
        elif fixture_type == "fare_rack" or event_phase == "boarding_crush":
            container_label = "Fare Rack"
            boarding_target = _business_event_followup_target(
                sim,
                prop,
                scene_type="shift",
                category="transit" if category == "transit" else category,
                rng=rng,
            )
            target_name = str(boarding_target.get("name", boarding_target.get("id", "the place"))).strip() if isinstance(boarding_target, dict) else ""
            if str((boarding_target or {}).get("id", "") or "").strip() == str(prop.get("id", "") or "").strip():
                target_name = ""
            time_text = _business_event_time_point_text(sim, offset_hours=1 + rng.randint(0, 2))
            if target_name and hours_text and requirement:
                note = (
                    f"Fare rack: {prop_name} is in a boarding crush during {hours_text}, with posted connections for {target_name} around {time_text}. "
                    f"The stop still wants {requirement} while fares and bags knot up at the edge."
                )
            elif target_name and hours_text:
                note = f"Fare rack: {prop_name} is boarding hard during {hours_text}, with clipped departure calls and the clean next connection toward {target_name} posted for around {time_text}."
            elif target_name and requirement:
                note = f"Fare rack: the line at {prop_name} is trying not to miss the {target_name} connection around {time_text}, and the stop still wants {requirement} while the crush is live."
            elif target_name:
                note = f"Fare rack: tokens, daypasses, and scratched route notes at {prop_name} keep circling back to {target_name} as the next clean connection once boarding clears."
            elif hours_text and requirement:
                note = f"Fare rack: {prop_name} is in a boarding crush during {hours_text}, and the stop still wants {requirement} while fares, bags, and shouted destinations bunch at the edge."
            elif hours_text:
                note = f"Fare rack: {prop_name} is boarding hard during {hours_text}, all fares, clipped calls, and people trying to hit the line before it slips."
            elif requirement:
                note = f"Fare rack: the stop at {prop_name} is under boarding pressure, and it still wants {requirement} once the line unclenches."
            else:
                note = f"Fare rack: {prop_name} is under a boarding crush, all tokens, passes, and route scribbles from people trying not to miss the clean run."
            pool = [item_id for item_id in ("city_pass_token", "transit_daypass", "protein_wrap", "bottled_water") if item_id in ITEM_CATALOG]
            item_count += 1
            read_only_reason = "You can pocket something from the fare rack, but turning live boarding supplies into your personal stash would stall the stop fast."
        elif fixture_type == "transfer_clipboard" or event_phase == "arrival_handoff":
            container_label = "Transfer Clipboard"
            arrival_target = _business_event_followup_target(
                sim,
                prop,
                scene_type="delivery",
                category=category,
                rng=rng,
            )
            target_name = str(arrival_target.get("name", arrival_target.get("id", "the place"))).strip() if isinstance(arrival_target, dict) else ""
            if str((arrival_target or {}).get("id", "") or "").strip() == str(prop.get("id", "") or "").strip():
                target_name = ""
            time_text = _business_event_time_point_text(sim, offset_hours=1 + rng.randint(1, 3))
            if target_name and hours_text and requirement:
                note = (
                    f"Transfer clipboard: {prop_name} is handling an arrival handoff during {hours_text}, with an incoming relief run marked for {target_name} around {time_text}. "
                    f"The stop still wants {requirement} while the pickup is live."
                )
            elif target_name and hours_text:
                note = f"Transfer clipboard: {prop_name} is running an arrival handoff during {hours_text}, with an incoming rider or relief bag marked onward to {target_name} around {time_text}."
            elif target_name and requirement:
                note = f"Transfer clipboard: somebody coming through {prop_name} is tagged for {target_name} around {time_text}, and the stop still wants {requirement} while the handoff clears."
            elif target_name:
                note = f"Transfer clipboard: arrival notes at {prop_name} keep pointing toward {target_name} around {time_text}, the kind of onward handoff that usually means somebody there needs either staff or supplies."
            elif hours_text and requirement:
                note = f"Transfer clipboard: {prop_name} is handling an arrival handoff during {hours_text}, and the stop still wants {requirement} while inbound riders and pickup chatter bunch at the edge."
            elif hours_text:
                note = f"Transfer clipboard: {prop_name} is in an arrival handoff during {hours_text}, all incoming riders, clipped greetings, and onward directions."
            elif requirement:
                note = f"Transfer clipboard: inbound riders and pickup chatter are bunching at {prop_name}, and the stop still wants {requirement} once the handoff clears."
            else:
                note = f"Transfer clipboard: {prop_name} is handling an arrival handoff, all incoming names, onward notes, and the sense that somebody here came from farther out because they were needed."
            pool = [item_id for item_id in ("credstick_chip", "city_pass_token", "transit_daypass", "bottled_water") if item_id in ITEM_CATALOG]
            item_count += 1
            read_only_reason = "You can pocket something from the transfer clipboard, but using live arrival paperwork as your own stash would get remembered fast."
        elif fixture_type == "cleanup_cart" or event_phase == "cleanup_detail":
            container_label = "Cleanup Cart"
            aftermath = _business_event_aftermath_entry(sim, prop) or {}
            casualty_count = max(0, int(aftermath.get("casualty_count", 0) or 0))
            incident_kind = str(aftermath.get("incident_kind", "violence") or "violence").strip().lower() or "violence"
            if casualty_count > 0 and hours_text and requirement:
                note = (
                    f"Cleanup cart: {prop_name} is being reset after a fatal scene at the door during {hours_text}. "
                    f"Once the crew clears off, the front still wants {requirement}."
                )
            elif casualty_count > 0:
                note = f"Cleanup cart: the frontage at {prop_name} is being reset after a fatal scene, all gloves, wipes, and workers trying not to talk louder than they need to."
            elif incident_kind == "hazard" and hours_text:
                note = f"Cleanup cart: {prop_name} is running a hazard cleanup during {hours_text}, with cones and supplies keeping the door half-held."
            elif incident_kind == "hazard":
                note = f"Cleanup cart: the frontage at {prop_name} is being scrubbed down after a nasty hazard turned the doorway into a caution line."
            elif hours_text and requirement:
                note = (
                    f"Cleanup cart: {prop_name} is clearing the frontage after somebody got hurt nearby during {hours_text}. "
                    f"After that the front still wants {requirement}."
                )
            else:
                note = f"Cleanup cart: the crew at {prop_name} is trying to scrub the last visible signs of recent trouble off the doorway."
            pool = [item_id for item_id in ("bottled_water", "calm_patch", "caff_shot", "pocket_multitool") if item_id in ITEM_CATALOG]
            item_count += 1
            read_only_reason = "You can pull something from the cleanup cart, but turning active recovery gear into your personal stash would get remembered fast."
        else:
            container_label = "Dispatch Satchel"
            dispatch_target = _business_event_followup_target(
                sim,
                prop,
                scene_type="shift",
                category=category,
                rng=rng,
            )
            target_name = str(dispatch_target.get("name", dispatch_target.get("id", "the place"))).strip() if isinstance(dispatch_target, dict) else ""
            time_text = _business_event_time_point_text(sim, offset_hours=1 + rng.randint(1, 3))
            if target_name and hours_text and requirement:
                note = (
                    f"Dispatch satchel: route slips at {prop_name} keep pointing toward {target_name} around {time_text}, "
                    f"while this frontage is still hot during {hours_text} and still wants {requirement}."
                )
            elif target_name and hours_text:
                note = f"Dispatch satchel: clipped route slips at {prop_name} point toward {target_name} around {time_text}, while this window is live during {hours_text}."
            elif target_name and requirement:
                note = f"Dispatch satchel: somebody at {prop_name} has marked {target_name} for the next handoff around {time_text}, but this edge still wants {requirement}."
            elif target_name:
                note = f"Dispatch satchel: the route slips here keep circling back to {target_name} as the next handoff once {prop_name} clears the current surge."
            elif hours_text and requirement:
                note = f"Dispatch satchel: {prop_name} is routing the next burst during {hours_text}, and the front still wants {requirement} while the board is hot."
            elif hours_text:
                note = f"Dispatch satchel: {prop_name} is in a dispatch surge during {hours_text}, with route notes and clipped orders spilling closer to the street."
            elif requirement:
                note = f"Dispatch satchel: clipped orders are spilling outward at {prop_name}, and the front still wants {requirement} while the surge is live."
            else:
                note = f"Dispatch satchel: {prop_name} is under a dispatch surge, all route slips, clipped orders, and edge traffic that should have stayed deeper inside."
            pool = [item_id for item_id in ("credstick_chip", "city_pass_token", "transit_daypass", "caff_shot") if item_id in ITEM_CATALOG]
            item_count += 1
            read_only_reason = "You can lift something from the dispatch satchel, but stuffing your own gear into live route paperwork would be a good way to get remembered."
    elif scene_type == "gathering" and fixture_type in {"meeting_sign", "meeting_marker", "meeting_board", "inspection_packet", "admin_packet", "manifest_clipboard", "trauma_kit", "school_bags", "stoop_cooler", "incident_tape", "memorial_candles", "help_wanted_board", "outreach_table", "crew_call_sheet", "route_welcome_board", "tenant_welcome_box", "mutual_aid_table", "regulars_table", "complaint_board"}:
        org_snapshot = _organization_snapshot(sim, prop=prop, ensure=True)
        org_name = str((org_snapshot or {}).get("organization_name", "") or "").strip()
        org_label = org_name or prop_name
        if fixture_type == "school_bags" or event_phase == "school_run":
            container_label = "Backpack Cluster"
        elif fixture_type == "stoop_cooler" or event_phase == "neighbors_lingering":
            container_label = "Shared Cooler"
        elif fixture_type == "incident_tape" or event_phase == "taped_off_front":
            container_label = "Tape Stanchion"
        elif fixture_type == "memorial_candles" or event_phase == "candle_vigil":
            container_label = "Memorial Candles"
        elif fixture_type == "trauma_kit" or event_phase == "street_triage":
            container_label = "Triage Kit" if category == "medical" else "Field Med Case"
        elif fixture_type == "help_wanted_board" or event_phase == "help_wanted_board":
            container_label = "Help-Wanted Board"
        elif fixture_type == "outreach_table" or event_phase == "clinic_outreach":
            container_label = "Outreach Table"
        elif fixture_type == "crew_call_sheet" or event_phase == "day_labor_call":
            container_label = "Crew Call Sheet"
        elif fixture_type == "route_welcome_board" or event_phase == "commuter_orientation":
            container_label = "Route Welcome Board"
        elif fixture_type == "tenant_welcome_box" or event_phase == "tenant_meetup":
            container_label = "Tenant Welcome Box"
        elif fixture_type == "mutual_aid_table" or event_phase == "mutual_aid_table":
            container_label = "Mutual Aid Table"
        elif fixture_type == "regulars_table" or event_phase == "regulars_spill":
            container_label = "Regulars Table"
        elif fixture_type == "complaint_board" or event_phase == "grumbling_front":
            container_label = "Complaint Crate"
        elif fixture_type == "manifest_clipboard" or event_phase == "manifest_check":
            container_label = "Manifest Clipboard"
        elif fixture_type == "admin_packet" or event_phase == "paperwork_surge":
            container_label = "Audit Packet" if category in {"office", "finance"} else "Receipt Binder"
        elif fixture_type == "inspection_packet" or event_phase == "delivery_inspection":
            container_label = "Inspection Packet"
        elif fixture_type == "meeting_sign":
            container_label = "Guest List"
        elif fixture_type == "meeting_marker":
            container_label = "Briefing Kit"
        else:
            container_label = "Meeting Packet"
        if event_phase == "school_run" and hours_text:
            note = f"Backpack cluster: {prop_name} is in its morning school-run crush during {hours_text}, all half-zipped bags and rushed checklists."
        elif event_phase == "school_run":
            note = f"Backpack cluster: {prop_name} is caught in a short morning burst of bags, lunch kits, and people trying not to be the reason everyone is late."
        elif event_phase == "neighbors_lingering":
            neighborhood_target = _business_event_neighborhood_target(sim, prop, rng=rng)
            target_name = ""
            target_hours_text = ""
            target_requirement = ""
            if isinstance(neighborhood_target, dict):
                target_name = str(neighborhood_target.get("name", neighborhood_target.get("id", "the place"))).strip() or "the place"
                target_controller = _property_access_controller(sim, neighborhood_target)
                if isinstance(target_controller, dict):
                    target_hours_text = _dialogue_hours_text(target_controller.get("opening_window"))
                    target_requirement = _controller_access_requirement_text(target_controller)
            if target_name and target_hours_text and target_requirement:
                note = (
                    f"Shared cooler: {prop_name} has spilled into stoop talk, and somebody keeps repeating that {target_name} usually runs during {target_hours_text}. "
                    f"They still want {target_requirement} at the door."
                )
            elif target_name and target_hours_text:
                note = f"Shared cooler: {prop_name} has spilled into stoop talk, and somebody keeps repeating that {target_name} is usually moving during {target_hours_text}."
            elif target_name and target_requirement:
                note = f"Shared cooler: the evening stoop circle outside {prop_name} keeps pointing at {target_name}, though they still want {target_requirement} at the door."
            elif target_name:
                note = f"Shared cooler: the neighbors outside {prop_name} keep turning the conversation back toward {target_name} whenever anyone asks what is still worth walking to."
            else:
                note = f"Shared cooler: {prop_name} has spilled into a little evening stoop circle of drinks, cigarettes, and block gossip before everyone heads back up."
        elif event_phase == "taped_off_front":
            aftermath = _business_event_aftermath_entry(sim, prop) or {}
            casualty_count = max(0, int(aftermath.get("casualty_count", 0) or 0))
            incident_kind = str(aftermath.get("incident_kind", "violence") or "violence").strip().lower() or "violence"
            if casualty_count > 0 and hours_text and requirement:
                note = (
                    f"Tape stanchion: {prop_name} is still half held after a fatal scene at the door during {hours_text}. "
                    f"When the hold loosens, the front still wants {requirement}."
                )
            elif casualty_count > 0:
                note = f"Tape stanchion: {prop_name} still has the doorway half taped after somebody died close enough to make the front feel wrong."
            elif incident_kind == "hazard" and hours_text:
                note = f"Tape stanchion: {prop_name} is holding the door because a fresh hazard turned the frontage into a caution line during {hours_text}."
            elif incident_kind == "hazard":
                note = f"Tape stanchion: the doorway at {prop_name} is still held because a nasty hazard has not finished being made safe."
            elif hours_text and requirement:
                note = f"Tape stanchion: somebody got hurt close enough to {prop_name} that the frontage is still half taped during {hours_text}, and the front still wants {requirement} once it settles."
            else:
                note = f"Tape stanchion: somebody got hurt close enough to {prop_name} that the frontage is still all tape, low voices, and people not ready to move on yet."
        elif event_phase == "candle_vigil":
            if hours_text and requirement:
                note = (
                    f"Memorial candles: people outside {prop_name} keep leaving quiet offerings for somebody the block has not finished grieving. "
                    f"When the building settles during {hours_text}, the front still wants {requirement}."
                )
            else:
                note = f"Memorial candles: people outside {prop_name} keep leaving quiet offerings because what happened here still feels too fresh to pass without stopping."
        elif event_phase == "street_triage" and hours_text and requirement:
            note = (
                f"Triage kit: {prop_name} is running curbside treatment during {hours_text}. "
                f"After that the front still wants {requirement}."
            )
        elif event_phase == "street_triage" and hours_text:
            note = f"Triage kit: somebody got hurt badly enough that {prop_name} pulled treatment out to the frontage during {hours_text}."
        elif event_phase == "street_triage" and requirement:
            note = f"Triage kit: the medic is stabilizing someone outside {prop_name}; once that clears, the front still wants {requirement}."
        elif event_phase == "street_triage":
            note = f"Triage kit: the frontage at {prop_name} is serving as a temporary treatment spot while a medic tries to stabilize the injured."
        elif event_phase == "help_wanted_board" and hours_text and requirement:
            note = f"Help-wanted board: {prop_name} is taking names during {hours_text}, but anyone stepping past the front still needs {requirement}."
        elif event_phase == "help_wanted_board" and hours_text:
            note = f"Help-wanted board: {prop_name} is taking names during {hours_text}, with job seekers checking whether a shift can become steady."
        elif event_phase == "help_wanted_board" and requirement:
            note = f"Help-wanted board: {prop_name} has work posted, but the front still wants {requirement} before anyone gets inside."
        elif event_phase == "help_wanted_board":
            note = f"Help-wanted board: {prop_name} has names, hours, and enough posted work for somebody new to try staying nearby."
        elif event_phase == "clinic_outreach" and hours_text and requirement:
            note = f"Outreach table: {prop_name} is catching walk-ins during {hours_text}. Deeper access still wants {requirement}."
        elif event_phase == "clinic_outreach" and hours_text:
            note = f"Outreach table: {prop_name} is catching walk-ins during {hours_text}, handing out enough care that people stop drifting for a minute."
        elif event_phase == "clinic_outreach" and requirement:
            note = f"Outreach table: {prop_name} is public-facing for now, but anything deeper still wants {requirement}."
        elif event_phase == "clinic_outreach":
            note = f"Outreach table: {prop_name} is moving care, water, and names through the frontage for people trying to get steady."
        elif event_phase == "day_labor_call" and hours_text and requirement:
            note = f"Crew call sheet: {prop_name} is filling a work list during {hours_text}, though the gate still wants {requirement}."
        elif event_phase == "day_labor_call" and hours_text:
            note = f"Crew call sheet: {prop_name} is calling hands during {hours_text}, with loose workers hoping the shift sticks."
        elif event_phase == "day_labor_call" and requirement:
            note = f"Crew call sheet: the work list at {prop_name} is open enough to draw laborers, but the gate still wants {requirement}."
        elif event_phase == "day_labor_call":
            note = f"Crew call sheet: {prop_name} is turning idle hands into a temporary crew, and temporary is sometimes how people start belonging."
        elif event_phase == "commuter_orientation" and hours_text and requirement:
            note = f"Route welcome board: {prop_name} is orienting arrivals during {hours_text}, while staffed access still wants {requirement}."
        elif event_phase == "commuter_orientation" and hours_text:
            note = f"Route welcome board: {prop_name} is catching new arrivals during {hours_text}, pointing them toward work, shelter, and onward routes."
        elif event_phase == "commuter_orientation" and requirement:
            note = f"Route welcome board: public route notes are open at {prop_name}, but staffed access still wants {requirement}."
        elif event_phase == "commuter_orientation":
            note = f"Route welcome board: {prop_name} is catching new arrivals with enough directions that some of them may stop drifting."
        elif event_phase == "tenant_meetup":
            note = f"Tenant welcome box: {prop_name} has a small stoop meetup going, all keys, names, repairs, and practical advice for someone new to the building."
        elif event_phase == "mutual_aid_table":
            note = f"Mutual aid table: {prop_name} is moving food, water, names, and work tips through the frontage; some of those names may stay local."
        elif event_phase == "regulars_spill" and hours_text and requirement:
            note = (
                f"Regulars table: people are treating {prop_name} like the kind of place the block has started trusting to come through during {hours_text}. "
                f"Anyone moving deeper still has to clear {requirement}."
            )
        elif event_phase == "regulars_spill" and hours_text:
            note = f"Regulars table: the same faces keep gathering at {prop_name} during {hours_text} because the block has started trusting the place to come through."
        elif event_phase == "regulars_spill" and requirement:
            note = f"Regulars table: the frontage at {prop_name} has become a familiar, trusted stop, though anyone stepping deeper still has to clear {requirement}."
        elif event_phase == "regulars_spill":
            note = f"Regulars table: {prop_name} has started reading like a trusted neighborhood staple, with familiar faces treating the frontage like part of the room."
        elif event_phase == "grumbling_front" and hours_text and requirement:
            note = (
                f"Complaint crate: people are grumbling outside {prop_name} during {hours_text}, whether about the prices, the pressure, or the way the front has gone sharp. "
                f"Anyone pushing deeper still has to clear {requirement}."
            )
        elif event_phase == "grumbling_front" and hours_text:
            note = f"Complaint crate: the knot outside {prop_name} is all low complaints and side-eye during {hours_text}, the way a useful place starts sounding when locals think it is slipping."
        elif event_phase == "grumbling_front" and requirement:
            note = f"Complaint crate: people keep bunching up outside {prop_name} to complain, but anyone going deeper still has to clear {requirement}."
        elif event_phase == "grumbling_front":
            note = f"Complaint crate: enough irritation has built up around {prop_name} that the frontage keeps turning into a short grumbling knot instead of a clean line."
        elif event_phase == "paperwork_surge" and hours_text and requirement:
            note = (
                f"Audit packet: {prop_name} is chewing through a paperwork surge during {hours_text}. "
                f"After that the front wants {requirement}."
            )
        elif event_phase == "paperwork_surge" and hours_text:
            note = f"Audit packet: {prop_name} is buried in approvals and receipts during {hours_text}."
        elif event_phase == "paperwork_surge" and requirement:
            note = f"Audit packet: {prop_name} is clearing a paperwork jam, and the front still wants {requirement}."
        elif event_phase == "paperwork_surge":
            note = f"Audit packet: {prop_name} is trying to clear a back-office jam before the front side catches it."
        elif event_phase == "manifest_check" and hours_text and requirement:
            note = (
                f"Manifest clipboard: {prop_name} is holding freight against the paperwork during {hours_text}. "
                f"Anything after that still wants {requirement}."
            )
        elif event_phase == "manifest_check" and hours_text:
            note = f"Manifest clipboard: {prop_name} is matching the next receiving window during {hours_text}."
        elif event_phase == "manifest_check" and requirement:
            note = f"Manifest clipboard: loads at {prop_name} are not supposed to move until they clear {requirement}."
        elif event_phase == "manifest_check":
            note = f"Manifest clipboard: the crew at {prop_name} is matching freight to paperwork before anything else moves."
        elif event_phase == "delivery_inspection" and hours_text and requirement:
            note = (
                f"Inspection packet: {prop_name} is drawing a quick review during {hours_text}. "
                f"After that the front wants {requirement}."
            )
        elif event_phase == "delivery_inspection" and hours_text:
            note = f"Inspection packet: {prop_name} is drawing a quick review during {hours_text}."
        elif event_phase == "delivery_inspection" and requirement:
            note = f"Inspection packet: the follow-up review at {prop_name} expects {requirement} on the way in."
        elif event_phase == "delivery_inspection":
            note = f"Inspection packet: the last drop at {prop_name} is pulling a quiet review team back to the site."
        elif hours_text and requirement:
            note = (
                f"Guest list: {prop_name} is holding a quiet follow-up for {org_label} during {hours_text}. "
                f"After that the front wants {requirement}."
            )
        elif hours_text:
            note = f"Guest list: {prop_name} is holding a private follow-up for {org_label} during {hours_text}."
        elif requirement:
            note = f"Guest list: invitees at {prop_name} are expected to clear {requirement} on the way in."
        else:
            note = f"Guest list: {prop_name} is set for a low-profile follow-up tied to {org_label}."
        if event_phase == "school_run":
            pool = [
                item_id
                for item_id in ("meal_voucher", "city_pass_token", "protein_wrap", "bottled_water")
                if item_id in ITEM_CATALOG
            ]
            if rng.random() < 0.45:
                item_count += 1
            read_only_reason = "You can lift something from the bag pile, but stuffing your own gear into a family's morning school mess would be a terrible idea."
        elif event_phase == "neighbors_lingering":
            pool = [
                item_id
                for item_id in ("spark_brew", "smoke_tab", "mint_strip", "bottled_water", "city_pass_token")
                if item_id in ITEM_CATALOG
            ]
            item_count += 1
            read_only_reason = "You can pocket something from the shared cooler, but using a neighbor hangout as your personal stash would not stay friendly for long."
        elif event_phase == "taped_off_front":
            pool = [
                item_id
                for item_id in ("calm_patch", "bottled_water", "city_pass_token", "meal_voucher")
                if item_id in ITEM_CATALOG
            ]
            item_count += 1
            read_only_reason = "You can pocket something left near the taped frontage, but turning an active incident hold into your own stash would be bleak and obvious."
        elif event_phase == "candle_vigil":
            pool = [
                item_id
                for item_id in ("calm_patch", "bottled_water", "meal_voucher", "city_pass_token")
                if item_id in ITEM_CATALOG
            ]
            item_count += 1
            read_only_reason = "You can take something left near the vigil, but using a memorial as your personal stash would be cold enough to get remembered."
        elif event_phase == "street_triage":
            pool = [
                item_id
                for item_id in ("med_gel", "micro_medkit", "trauma_foam", "hydration_salts", "calm_patch")
                if item_id in ITEM_CATALOG
            ]
            item_count += 1
            if category == "medical":
                item_count += 1
            read_only_reason = "You can lift emergency supplies from the kit, but this treatment cache is not a safe place to stash your own gear."
        elif event_phase == "help_wanted_board":
            pool = [item_id for item_id in ("city_pass_token", "caff_shot", "protein_wrap", "focus_inhaler") if item_id in ITEM_CATALOG]
            item_count += 1
            read_only_reason = "You can take something clipped to the job board, but this is not a place to stash your own gear."
        elif event_phase == "clinic_outreach":
            pool = [item_id for item_id in ("hydration_salts", "calm_patch", "med_gel", "bottled_water") if item_id in ITEM_CATALOG]
            item_count += 1
            read_only_reason = "You can pull from the outreach table, but using public care supplies as your personal stash would get noticed."
        elif event_phase == "day_labor_call":
            pool = [item_id for item_id in ("pocket_multitool", "battery_pack", "protein_wrap", "caff_shot") if item_id in ITEM_CATALOG]
            item_count += 1
            read_only_reason = "You can lift something from the crew call sheet, but live work gear is not your personal locker."
        elif event_phase == "commuter_orientation":
            pool = [item_id for item_id in ("city_pass_token", "transit_daypass", "protein_wrap", "bottled_water") if item_id in ITEM_CATALOG]
            item_count += 1
            read_only_reason = "You can pocket something from the route board, but using arrival supplies as a stash would stall the guide table."
        elif event_phase == "tenant_meetup":
            pool = [item_id for item_id in ("meal_voucher", "city_pass_token", "bottled_water", "calm_patch") if item_id in ITEM_CATALOG]
            item_count += 1
            read_only_reason = "You can take something from the welcome box, but turning a tenant meetup into storage would sour the room fast."
        elif event_phase == "mutual_aid_table":
            pool = [item_id for item_id in ("meal_voucher", "bottled_water", "calm_patch", "city_pass_token") if item_id in ITEM_CATALOG]
            item_count += 1
            read_only_reason = "You can take from the aid table, but using it as a private stash would get remembered."
        elif event_phase == "regulars_spill":
            pool = [item_id for item_id in ("spark_brew", "bottled_water", "mint_strip", "city_pass_token", "meal_voucher") if item_id in ITEM_CATALOG]
            item_count += 1
            read_only_reason = "You can pocket something from the regulars table, but using a neighborhood staple as your private stash would sour a place people actually care about."
        elif event_phase == "grumbling_front":
            pool = [item_id for item_id in ("spark_brew", "calm_patch", "bottled_water", "city_pass_token") if item_id in ITEM_CATALOG]
            item_count += 1
            read_only_reason = "You can pull something from the complaint crate, but turning a live grumbling knot into your own stash would be a fast way to get remembered for the wrong reason."
        elif event_phase == "paperwork_surge":
            packet_pool = ("credstick_chip", "city_pass_token", "focus_inhaler", "protein_wrap")
            pool = [item_id for item_id in packet_pool if item_id in ITEM_CATALOG]
            if category in {"office", "finance"}:
                item_count += 1
            read_only_reason = "You can lift something from the review packet, but this stack is not for storing your own gear."
        elif event_phase == "manifest_check":
            packet_pool = ("pocket_multitool", "battery_pack", "caff_shot", "protein_wrap")
            pool = [item_id for item_id in packet_pool if item_id in ITEM_CATALOG]
            if category in {"industrial", "transit"}:
                item_count += 1
            read_only_reason = "You can pull something from the manifest cart, but this clipboard stash is not yours to use as a locker."
        else:
            pool = [
                item_id
                for item_id in _business_event_item_pool(
                    "gathering",
                    category,
                    {"role": "worker", "career": "host"},
                )
                if item_id in ITEM_CATALOG
            ]
            if category in {"office", "finance", "hospitality", "entertainment"} or rng.random() < 0.35:
                item_count += 1
            read_only_reason = "You can pocket something from the meeting setup, but there is nowhere to stash your own gear here."
    else:
        return {}

    unique_pool = list(dict.fromkeys(pool))
    if not unique_pool:
        return {}
    if rng is None:
        rng = random.Random(f"{getattr(sim, 'seed', 0)}:business-scene-cache:{scene.get('scene_id', '')}")
    rng.shuffle(unique_pool)
    loot_entries = []
    for item_id in unique_pool[:max(1, min(len(unique_pool), item_count))]:
        loot_entries.append({
            "instance_id": sim.new_item_instance_id(),
            "item_id": item_id,
            "quantity": 1,
            "name": item_display_name(item_id, item_catalog=ITEM_CATALOG),
            "metadata": {
                "business_scene_id": str(scene.get("scene_id", "") or "").strip(),
                "business_scene_loot": True,
            },
            "owner_eid": None,
            "owner_tag": "scene",
        })

    return {
        "property_metadata": {
            "interaction_role": "business_scene_cache",
            "container_kind": "scene",
            "container_label": container_label,
            "container_note_text": note,
            "container_read_only": True,
            "container_read_only_reason": read_only_reason,
        },
        "loot_entries": loot_entries,
    }


def _business_event_seed_scene_actor_note(sim, scene, prop, actor_spec, *, rng):
    scene = scene if isinstance(scene, dict) else {}
    prop = prop if isinstance(prop, dict) else None
    actor_spec = actor_spec if isinstance(actor_spec, dict) else {}
    if prop is None:
        return {}
    if str(scene.get("source_kind", "") or "").strip().lower() != "seed":
        return {}

    scene_seed_id = str(scene.get("seed_id", "") or "").strip()
    if scene_seed_id:
        current_seed = _business_event_seed_state(sim).get("active", {}).get(scene_seed_id)
        if isinstance(current_seed, dict):
            consequence_seed_id = str(current_seed.get("consequence_seed_id", "") or "").strip()
            consequence_seed = _business_event_seed_state(sim).get("active", {}).get(consequence_seed_id)
            if isinstance(consequence_seed, dict):
                target_property_id = str(consequence_seed.get("target_property_id", "") or "").strip()
                target_prop = sim.properties.get(target_property_id) if target_property_id else None
                return {
                    "seed_id": consequence_seed_id,
                    "property_id": str(consequence_seed.get("source_property_id", "") or "").strip(),
                    "target_property_id": target_property_id,
                    "local_line": str(consequence_seed.get("local_line", "") or "").strip(),
                    "detail_line": str(consequence_seed.get("detail_line", "") or "").strip(),
                    "lead_kind": str(consequence_seed.get("lead_kind", "") or "").strip().lower(),
                    "opportunity": _business_event_enrich_followup_opportunity(
                        sim,
                        dict(consequence_seed.get("opportunity", {}) or {}),
                        target_prop,
                    ),
                    "shared": bool(consequence_seed.get("shared")),
                }

    scene_type = str(scene.get("scene_type", "") or "").strip().lower()
    event_phase = str(scene.get("event_phase", "") or "").strip().lower()
    role = str(actor_spec.get("role", "") or "").strip().lower()
    career = str(actor_spec.get("career", "") or "").strip().lower()
    prop_name = str(prop.get("name", prop.get("id", "the site"))).strip() or "the site"
    controller = _property_access_controller(sim, prop)
    hours_text = _dialogue_hours_text(controller.get("opening_window")) if isinstance(controller, dict) else ""
    requirement = _controller_access_requirement_text(controller) if isinstance(controller, dict) else ""

    if scene_type == "delivery":
        if career == "courier":
            local_line = f"This stop is live now, and {prop_name} is supposed to clear the handoff before the window closes."
            detail_line = (
                f"They are trying to keep the drop at {prop_name} moving cleanly"
                + (f" during {hours_text}." if hours_text else ".")
            )
        else:
            local_line = f"{prop_name} is expecting a quick receiving handoff right now."
            detail_line = (
                f"The receiver is trying to keep {prop_name} quiet through the drop"
                + (f" during {hours_text}." if hours_text else ".")
            )
        if requirement:
            detail_line = detail_line[:-1] + f" After that they want {requirement}."
        lead_kind = "hours"
    elif scene_type == "gathering":
        org_snapshot = _organization_snapshot(sim, prop=prop, ensure=True)
        org_name = str((org_snapshot or {}).get("organization_name", "") or "").strip()
        org_label = org_name or prop_name
        if event_phase == "regulars_spill":
            if career in {"site_rep", "host", "coordinator"} or role == "worker":
                local_line = f"The same faces keep coming back to {prop_name} because it has started feeling dependable."
                detail_line = (
                    f"The frontage at {prop_name} has turned into a regular stop for people who trust it to come through"
                    + (f" during {hours_text}." if hours_text else ".")
                )
            else:
                local_line = f"I keep circling back to {prop_name} because it is one of the few places that usually feels worth the stop."
                detail_line = (
                    f"People around here have started treating {prop_name} like part of the neighborhood's ordinary rhythm"
                    + (f" during {hours_text}." if hours_text else ".")
                )
        elif event_phase == "grumbling_front":
            if career in {"site_rep", "host", "coordinator"} or role == "worker":
                local_line = f"The front at {prop_name} keeps getting hung up on complaints, and nobody wants it to tip into a bigger problem."
                detail_line = (
                    f"People keep bunching up at {prop_name} to grumble about the prices, the pressure, or the way the front has gone sharp"
                    + (f" during {hours_text}." if hours_text else ".")
                )
            else:
                local_line = f"People still use {prop_name}, but more of them are starting to talk like the place is slipping."
                detail_line = (
                    f"The knot at the frontage is not random; it is the sound a useful place makes when locals start doubting what it costs them"
                    + (f" during {hours_text}." if hours_text else ".")
                )
        elif event_phase == "delivery_inspection":
            local_line = f"The last drop here is pulling a quick inspection back to {prop_name}."
            detail_line = (
                f"Inspectors are expected to cycle through {prop_name}"
                + (f" during {hours_text}." if hours_text else ".")
            )
        elif career in {"host", "coordinator"} or role == "worker":
            local_line = f"They are holding a quiet follow-up for {org_label} at {prop_name} right now."
            detail_line = (
                f"The host is trying to keep arrivals moving through {prop_name}"
                + (f" during {hours_text}." if hours_text else ".")
            )
        else:
            local_line = f"People here keep treating {prop_name} like the follow-up stop for {org_label}."
            detail_line = (
                f"This crowd is not random. They are here for a private meet tied to {org_label}"
                + (f" during {hours_text}." if hours_text else ".")
            )
        if requirement:
            detail_line = detail_line[:-1] + f" The front still wants {requirement}."
        lead_kind = "access" if requirement else "hours"
    else:
        return {}

    return {
        "property_id": str(prop.get("id", "") or "").strip(),
        "target_property_id": str(prop.get("id", "") or "").strip(),
        "local_line": local_line,
        "detail_line": detail_line,
        "lead_kind": lead_kind,
        "shared": False,
    }


def _business_event_scene_blueprint(prop, pulse):
    prop = prop if isinstance(prop, dict) else None
    pulse = pulse if isinstance(pulse, dict) else {}
    event_phase = str(pulse.get("event_phase", "") or "").strip().lower()
    category = str(pulse.get("category", "") or "").strip().lower()
    traffic_state = str(pulse.get("traffic_state", "") or "").strip().lower()
    try:
        traffic_customer_delta = int(pulse.get("traffic_customer_delta", 0) or 0)
    except (TypeError, ValueError):
        traffic_customer_delta = 0
    if not event_phase:
        return None

    if event_phase in _BUSINESS_EVENT_DELIVERY_PHASES:
        return _business_event_delivery_blueprint(category)

    if event_phase in _BUSINESS_EVENT_QUEUE_PHASES:
        if event_phase == "owner_screening":
            fixture_name = "Door Roster"
            fixture_type = "queue_marker"
            fixture_glyph = "q"
            actor_specs = [
                {"role": "civilian", "career": "visitor", "linger_ticks": 18},
                {"role": "civilian", "career": "visitor", "linger_ticks": 16},
                {"role": "worker", "career": "door_host", "linger_ticks": 16, "site_affiliated": True},
            ]
        elif category == "secure" and event_phase in {"visitor_screening", "booking_queue", "release_queue"}:
            if event_phase == "visitor_screening":
                fixture_name = "Screening Rail"
                actor_specs = [{"role": "civilian", "career": "visitor", "linger_ticks": 18} for _ in range(3)]
            elif event_phase == "release_queue":
                fixture_name = "Release Bench"
                actor_specs = [{"role": "civilian", "career": "visitor", "linger_ticks": 18} for _ in range(2)]
            else:
                fixture_name = "Booking Desk"
                actor_specs = [{"role": "civilian", "career": "visitor", "linger_ticks": 16} for _ in range(2)]
            fixture_type = "queue_marker"
            fixture_glyph = "q"
        elif event_phase == "triage_spill":
            fixture_name = "Intake Bench"
            fixture_type = "triage_bench"
            fixture_glyph = "h"
            actor_specs = [{"role": "civilian", "career": "patient", "linger_ticks": 16} for _ in range(3)]
        elif event_phase == "last_call_spill":
            fixture_name = "Ash Can"
            fixture_type = "smoke_can"
            fixture_glyph = "a"
            actor_specs = [{"role": "drunk", "career": "late_patron", "linger_ticks": 14} for _ in range(3)]
        else:
            fixture_name = "Queue Stand"
            fixture_type = "queue_marker"
            fixture_glyph = "q"
            count = 3 if event_phase in {"crowd_spillover", "waiting_parties"} else 2
            actor_specs = [{"role": "civilian", "career": "visitor", "linger_ticks": 18} for _ in range(count)]
        if event_phase in _BUSINESS_EVENT_CROWD_FORWARD_PHASES:
            if traffic_state in {"surging", "steady_plus"} and traffic_customer_delta >= 0:
                bonus_count = 1 if traffic_state == "surging" else 0
                for _ in range(max(0, bonus_count)):
                    actor_specs.append({
                        "role": "civilian",
                        "career": "regular" if event_phase in {"crowd_spillover", "waiting_parties", "last_call_spill"} else "visitor",
                        "linger_ticks": 20 if event_phase in {"crowd_spillover", "waiting_parties", "last_call_spill"} else 18,
                    })
            elif traffic_state in {"patchy", "thin"} and traffic_customer_delta < 0:
                trim = min(max(1, len(actor_specs) - 1), abs(int(traffic_customer_delta)))
                while trim > 0 and len(actor_specs) > 1:
                    actor_specs.pop()
                    trim -= 1
                if actor_specs:
                    actor_specs[0]["linger_ticks"] = max(12, int(actor_specs[0].get("linger_ticks", 18) or 18) - 4)
        return {
            "scene_type": "queue",
            "fixture_name": fixture_name,
            "fixture_type": fixture_type,
            "fixture_glyph": fixture_glyph,
            "actor_specs": actor_specs,
            "keep_hours": 2,
            "release_budget": 1,
            "drift_preferred": True,
        }

    if event_phase in _BUSINESS_EVENT_MEDICAL_RESPONSE_PHASES:
        return _business_event_medical_response_blueprint(category, event_phase=event_phase)

    if event_phase in _BUSINESS_EVENT_RESIDENTIAL_SOCIAL_PHASES:
        return _business_event_residential_social_blueprint(category, event_phase=event_phase)

    if event_phase in _BUSINESS_EVENT_SETTLEMENT_PHASES:
        return _business_event_settlement_blueprint(category, event_phase=event_phase)

    if event_phase in _BUSINESS_EVENT_HOSPITALITY_PRESSURE_PHASES:
        return _business_event_hospitality_pressure_blueprint(category, event_phase=event_phase)

    if event_phase in _BUSINESS_EVENT_OPERATIONAL_PRESSURE_PHASES:
        return _business_event_operational_pressure_blueprint(category, event_phase=event_phase)

    if event_phase in _BUSINESS_EVENT_AFTERMATH_PHASES:
        return _business_event_aftermath_blueprint(category, event_phase=event_phase)

    if event_phase in _BUSINESS_EVENT_GATHERING_PHASES:
        return _business_event_admin_review_blueprint(category, event_phase=event_phase)

    if event_phase in _BUSINESS_EVENT_SHIFT_PHASES:
        if event_phase == "owner_closed_turnover":
            return {
                "scene_type": "shift",
                "fixture_name": "Closed Sign",
                "fixture_type": "shift_board",
                "fixture_glyph": "n",
                "actor_specs": [
                    {"role": "worker", "career": "closing_staff", "linger_ticks": 14, "site_affiliated": True},
                    {"role": "worker", "career": "shift_worker", "linger_ticks": 12, "site_affiliated": True},
                ],
                "keep_hours": 1,
                "release_budget": 0,
                "drift_preferred": False,
            }
        if event_phase == "maintenance_loop":
            actor_specs = [
                {"role": "worker", "career": "maintenance_tech", "linger_ticks": 14},
            ]
            if category in {"hospitality", "entertainment", "industrial", "medical", "transit"}:
                actor_specs.append({"role": "worker", "career": "maintenance_tech", "linger_ticks": 14})
            return {
                "scene_type": "shift",
                "fixture_name": "Tool Cart" if category not in {"industrial", "transit"} else "Service Cart",
                "fixture_type": "service_cart",
                "fixture_glyph": "t",
                "actor_specs": actor_specs,
                "keep_hours": 1,
                "release_budget": 0,
                "drift_preferred": False,
            }
        if category == "secure":
            fixture_name = "Duty Board"
            fixture_type = "shift_board"
            fixture_glyph = "n"
            if event_phase == "guard_rotation":
                actor_specs = [
                    {"role": "guard", "career": "shift_sergeant", "linger_ticks": 16},
                    {"role": "guard", "career": "gate_guard", "linger_ticks": 16},
                ]
            else:
                actor_specs = [
                    {"role": "guard", "career": "transport_officer", "linger_ticks": 16},
                    {"role": "worker", "career": "release_clerk", "linger_ticks": 14},
                ]
        else:
            fixture_name = "Shift Cart" if category in {"industrial", "transit"} else "Notice Board"
            fixture_type = "shift_cart" if category in {"industrial", "transit"} else "shift_board"
            fixture_glyph = "t" if category in {"industrial", "transit"} else "n"
            actor_count = 2 if category in {"industrial", "transit", "medical"} else 1
            actor_specs = [{"role": "worker", "career": "shift_worker", "linger_ticks": 14} for _ in range(actor_count)]
        return {
            "scene_type": "shift",
            "fixture_name": fixture_name,
            "fixture_type": fixture_type,
            "fixture_glyph": fixture_glyph,
            "actor_specs": actor_specs,
            "keep_hours": 2,
            "release_budget": 1,
            "drift_preferred": False,
        }
    return None


class BusinessPulseAftermathSystem(System):
    def __init__(self, sim):
        super().__init__(sim)
        self.runs_without_turn = True
        self.sim.events.subscribe("entity_damaged", self.on_entity_damaged)
        self.sim.events.subscribe("npc_killed", self.on_npc_killed)
        self.sim.events.subscribe("player_killed", self.on_player_killed)
        self.sim.events.subscribe("creature_hazard_triggered", self.on_creature_hazard_triggered)

    def _record(self, *, x, y, z, incident_kind="violence", severity=0.4, casualty=False, serious=False, damage_kind=""):
        return _record_business_event_aftermath(
            self.sim,
            x=x,
            y=y,
            z=z,
            incident_kind=incident_kind,
            severity=severity,
            casualty=casualty,
            serious=serious,
            damage_kind=damage_kind,
        )

    def on_entity_damaged(self, event):
        x = event.data.get("x")
        y = event.data.get("y")
        z = event.data.get("z")
        if x is None or y is None or z is None:
            return
        try:
            damage = int(event.data.get("damage", 0) or 0)
            hp = int(event.data.get("hp", 0) or 0)
            max_hp = max(1, int(event.data.get("max_hp", 1) or 1))
        except (TypeError, ValueError):
            return
        damage_kind = str(event.data.get("damage_kind", "harm") or "harm").strip().lower() or "harm"
        violent = damage_kind in {"ballistic", "explosive", "melee"}
        if violent:
            serious = damage >= max(3, max_hp // 5) or hp <= max(1, max_hp // 3)
            severity = 0.24 + min(0.56, float(damage) / float(max_hp))
            if hp <= 0:
                severity += 0.18
            self._record(
                x=x,
                y=y,
                z=z,
                incident_kind="violence",
                severity=severity,
                casualty=False,
                serious=serious,
                damage_kind=damage_kind,
            )
            return
        if damage < max(2, max_hp // 6):
            return
        severity = 0.22 + min(0.48, float(damage) / float(max_hp))
        self._record(
            x=x,
            y=y,
            z=z,
            incident_kind="hazard",
            severity=severity,
            casualty=False,
            serious=hp <= max(1, max_hp // 2),
            damage_kind=damage_kind,
        )

    def on_npc_killed(self, event):
        x = event.data.get("x")
        y = event.data.get("y")
        z = event.data.get("z")
        if x is None or y is None or z is None:
            return
        reason = str(event.data.get("reason", "killed") or "killed").strip().lower() or "killed"
        incident_kind = "hazard" if reason in {"burned", "creature_hazard", "toxin", "condition"} else "violence"
        self._record(
            x=x,
            y=y,
            z=z,
            incident_kind=incident_kind,
            severity=0.92,
            casualty=True,
            serious=True,
            damage_kind=reason,
        )

    def on_player_killed(self, event):
        x = event.data.get("x")
        y = event.data.get("y")
        z = event.data.get("z")
        if x is None or y is None or z is None:
            return
        damage_kind = str(event.data.get("damage_kind", "lethal_damage") or "lethal_damage").strip().lower() or "lethal_damage"
        incident_kind = "hazard" if damage_kind in {"condition", "toxin"} else "violence"
        self._record(
            x=x,
            y=y,
            z=z,
            incident_kind=incident_kind,
            severity=0.98,
            casualty=True,
            serious=True,
            damage_kind=damage_kind,
        )

    def on_creature_hazard_triggered(self, event):
        x = event.data.get("x")
        y = event.data.get("y")
        z = event.data.get("z", 0)
        if x is None or y is None:
            return
        self._record(
            x=x,
            y=y,
            z=z,
            incident_kind="hazard",
            severity=0.58,
            casualty=False,
            serious=True,
            damage_kind="creature_hazard",
        )

    def update(self):
        _prune_business_event_aftermath_state(self.sim)


class BusinessPulseSceneSystem(System):
    def __init__(self, sim, player_eid):
        super().__init__(sim)
        self.player_eid = player_eid
        self.runs_without_turn = True

    def _active_chunk_coord(self):
        coord = getattr(self.sim, "active_chunk_coord", None)
        if not isinstance(coord, (tuple, list)) or len(coord) != 2:
            return None
        try:
            return (int(coord[0]), int(coord[1]))
        except (TypeError, ValueError):
            return None

    def _player_pos(self):
        return self.sim.ecs.get(Position).get(self.player_eid)

    def _scene_id_for(self, prop, pulse):
        property_id = str((prop or {}).get("id", "") or "").strip()
        event_phase = str((pulse or {}).get("event_phase", "") or "").strip().lower()
        if not property_id or not event_phase:
            return ""
        return f"business:{property_id}:{event_phase}"

    def _anchor_support_tiles(self, anchor, *, reserved=None, limit=4):
        tiles = []
        if isinstance(anchor, (tuple, list)) and len(anchor) >= 3:
            tile = (int(anchor[0]), int(anchor[1]), int(anchor[2]))
            if (
                self.sim.tilemap.is_walkable(tile[0], tile[1], tile[2])
                and not self.sim.structure_at(tile[0], tile[1], tile[2])
                and not self.sim.property_covering(tile[0], tile[1], tile[2])
                and not self.sim.tilemap.entities_at(tile[0], tile[1], tile[2])
            ):
                tiles.append(tile)
        for tile in _adjacent_street_tiles(self.sim, anchor, reserved=reserved):
            if tile not in tiles:
                tiles.append(tile)
            if len(tiles) >= int(limit):
                break
        return tiles

    def _open_air_support_tiles(self, origin, *, reserved=None, min_radius=1, max_radius=4, limit=8):
        if not isinstance(origin, (tuple, list)) or len(origin) < 3:
            return []
        reserved = {
            (int(pos[0]), int(pos[1]), int(pos[2]))
            for pos in (reserved or ())
            if isinstance(pos, (tuple, list)) and len(pos) >= 3
        }
        ox, oy, oz = int(origin[0]), int(origin[1]), int(origin[2])
        tiles = []
        start_radius = max(int(min_radius), 1)
        end_radius = max(int(max_radius), start_radius)
        for radius in range(end_radius, start_radius - 1, -1):
            ring_tiles = []
            for dy in range(-radius, radius + 1):
                for dx in range(-radius, radius + 1):
                    if max(abs(dx), abs(dy)) != radius:
                        continue
                    nx, ny = ox + dx, oy + dy
                    pos = (nx, ny, oz)
                    if pos in reserved:
                        continue
                    if not self.sim.tilemap.is_walkable(nx, ny, oz):
                        continue
                    if self.sim.structure_at(nx, ny, oz):
                        continue
                    if self.sim.property_covering(nx, ny, oz):
                        continue
                    if self.sim.property_at(nx, ny, oz):
                        continue
                    if self.sim.tilemap.entities_at(nx, ny, oz):
                        continue
                    ring_tiles.append(pos)
            for tile in sorted(
                ring_tiles,
                key=lambda pos: (-_manhattan(ox, oy, pos[0], pos[1]), pos[1], pos[0]),
            ):
                if tile not in tiles:
                    tiles.append(tile)
                if len(tiles) >= int(limit):
                    return tiles
        return tiles

    def _candidate_scene_specs(self):
        active_chunk = self._active_chunk_coord()
        player_pos = self._player_pos()
        if active_chunk is None or player_pos is None:
            return []

        active = _business_event_scene_state(self.sim).get("active", {})
        active_scene_by_property = {}
        for active_scene_id, active_scene in active.items():
            property_id = str((active_scene or {}).get("property_id", "") or "").strip()
            if property_id:
                active_scene_by_property[property_id] = str(active_scene_id or "").strip()
        candidates = []
        for prop in self.sim.properties.values():
            if not isinstance(prop, dict):
                continue
            if str(prop.get("kind", "") or "").strip().lower() != "building":
                continue
            try:
                prop_chunk = self.sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
            except (TypeError, ValueError):
                continue
            if prop_chunk != active_chunk:
                continue
            if self.sim.detail_for_xy(int(prop.get("x", 0)), int(prop.get("y", 0))) == "unloaded":
                continue

            pulse = _building_pulse_snapshot(self.sim, prop=prop, respect_chunk_cap=False)
            blueprint = _business_event_scene_blueprint(prop, pulse)
            if blueprint is None:
                continue

            anchor = _business_event_frontage_anchor(self.sim, prop)
            if anchor is None:
                continue
            if _manhattan(player_pos.x, player_pos.y, anchor[0], anchor[1]) <= 1:
                continue

            scene_id = self._scene_id_for(prop, pulse)
            if not scene_id:
                continue
            property_id = str(prop.get("id", "") or "").strip()
            event_phase = str((pulse or {}).get("event_phase", "") or "").strip().lower()
            if event_phase and event_phase not in _BUSINESS_EVENT_AFTERMATH_PHASES:
                visible_ids = _regular_building_micro_event_visible_property_ids(self.sim, active_chunk)
                if property_id not in visible_ids:
                    continue
            active_scene_id = active_scene_by_property.get(property_id, "")
            if active_scene_id and active_scene_id != scene_id:
                continue
            if event_phase not in _BUSINESS_EVENT_AFTERMATH_PHASES and self._scene_property_on_cooldown(property_id):
                continue
            score = float(pulse.get("perimeter_bonus", 0.0) or 0.0)
            if _property_is_storefront(prop) or _property_is_public(prop):
                score += 0.75
            if _property_access_level(prop) == "public":
                score += 0.35
            if event_phase in _BUSINESS_EVENT_SETTLEMENT_PHASES and self._chunk_release_headroom(active_chunk) > 0:
                score += 0.9
            score -= float(_manhattan(player_pos.x, player_pos.y, anchor[0], anchor[1])) * 0.045
            if scene_id in active:
                score += 0.55
            candidates.append({
                "scene_id": scene_id,
                "property_id": str(prop.get("id", "") or "").strip(),
                "prop": prop,
                "pulse": pulse,
                "anchor": anchor,
                "score": score,
                "blueprint": blueprint,
                "chunk": active_chunk,
            })

        candidates.extend(_business_event_seed_scene_specs(self.sim, active_chunk, player_pos))

        candidates.sort(
            key=lambda row: (
                -float(row.get("score", 0.0) or 0.0),
                str((row.get("pulse") or {}).get("event_phase", "") or ""),
                str(row.get("property_id", "") or ""),
            )
        )
        priority_candidates = []
        regular_candidates = []
        for candidate in candidates:
            pulse = candidate.get("pulse") or {}
            event_phase = str(pulse.get("event_phase", "") or "").strip().lower()
            source_kind = str(candidate.get("source_kind", "pulse") or "pulse").strip().lower()
            if source_kind == "seed" or event_phase in _BUSINESS_EVENT_AFTERMATH_PHASES:
                priority_candidates.append(candidate)
            else:
                regular_candidates.append(candidate)

        selected = []

        def _can_place(candidate):
            anchor = candidate["anchor"]
            return not any(
                _manhattan(anchor[0], anchor[1], other["anchor"][0], other["anchor"][1]) <= 4
                for other in selected
            )

        for candidate in priority_candidates:
            if len(selected) >= _BUSINESS_EVENT_SCENE_CAP:
                break
            if not _can_place(candidate):
                continue
            selected.append(candidate)

        regular_selected = 0
        for candidate in regular_candidates:
            if len(selected) >= _BUSINESS_EVENT_SCENE_CAP:
                break
            if regular_selected >= _BUSINESS_EVENT_REGULAR_SCENE_CAP:
                break
            if not _can_place(candidate):
                continue
            selected.append(candidate)
            regular_selected += 1
        return selected

    def _register_scene_fixture(self, scene, pos, *, name, fixture_type, glyph, color="building_roof_storefront", extra_metadata=None):
        if not isinstance(pos, (tuple, list)) or len(pos) < 3:
            return None
        x, y, z = int(pos[0]), int(pos[1]), int(pos[2])
        if self.sim.property_at(x, y, z) or self.sim.property_covering(x, y, z):
            return None
        prop = self.sim.properties.get(str(scene.get("property_id", "") or "").strip())
        linked_building_id = _building_id_from_property(prop) if isinstance(prop, dict) else ""
        metadata = {
            "archetype": "street_fixture",
            "fixture_type": str(fixture_type).strip().lower() or "street_fixture",
            "public": True,
            "display_glyph": str(glyph)[:1] or "f",
            "display_color": str(color).strip() or "building_roof_storefront",
            "cover_kind": "low",
            "cover_value": 0.22,
            "business_scene_id": str(scene.get("scene_id", "") or "").strip(),
            "business_scene_phase": str(scene.get("event_phase", "") or "").strip().lower(),
            "linked_property_id": str(scene.get("property_id", "") or "").strip() or None,
            "linked_building_id": linked_building_id or None,
        }
        if isinstance(extra_metadata, dict):
            metadata.update(dict(extra_metadata))
        property_id = self.sim.register_property(
            name=str(name).strip() or "Street Fixture",
            kind="fixture",
            x=x,
            y=y,
            z=z,
            owner_eid=None,
            owner_tag="public",
            metadata=metadata,
        )
        scene["spawned_property_ids"].append(property_id)
        return property_id

    def _register_scene_vehicle(self, scene, pos, *, name, rng):
        if not isinstance(pos, (tuple, list)) or len(pos) < 3:
            return None
        x, y, z = int(pos[0]), int(pos[1]), int(pos[2])
        if self.sim.property_at(x, y, z) or self.sim.property_covering(x, y, z):
            return None
        prop = self.sim.properties.get(str(scene.get("property_id", "") or "").strip())
        linked_building_id = _building_id_from_property(prop) if isinstance(prop, dict) else ""

        profile = roll_vehicle_profile(rng, quality="used")
        profile["make"] = "Transit"
        profile["model"] = "Courier"
        profile["vehicle_class"] = "van"
        metadata = vehicle_metadata(
            profile,
            chunk=self.sim.chunk_coords(x, y),
            owner_tag="public",
            display_color="vehicle_paint_white",
            locked=True,
            lock_tier=1,
        )
        metadata.update({
            "vehicle_usable": False,
            "business_scene_id": str(scene.get("scene_id", "") or "").strip(),
            "business_scene_phase": str(scene.get("event_phase", "") or "").strip().lower(),
            "cover_kind": "low",
            "cover_value": 0.54,
            "linked_property_id": str(scene.get("property_id", "") or "").strip() or None,
            "linked_building_id": linked_building_id or None,
        })
        property_id = self.sim.register_property(
            name=str(name).strip() or "Delivery Van",
            kind="vehicle",
            x=x,
            y=y,
            z=z,
            owner_eid=None,
            owner_tag="public",
            metadata=metadata,
        )
        scene["spawned_property_ids"].append(property_id)
        return property_id

    def _scene_property(self, scene):
        property_id = str((scene or {}).get("property_id", "") or "").strip()
        if not property_id:
            return None
        return self.sim.properties.get(property_id)

    def _decorate_scene_actor(self, scene, actor_spec, eid, *, rng):
        prop = self._scene_property(scene)
        if eid is None:
            return
        actor_spec = actor_spec if isinstance(actor_spec, dict) else {}
        source_kind = str(scene.get("source_kind", "") or "").strip().lower()
        event_phase = str(scene.get("event_phase", "") or "").strip().lower()
        role = str(actor_spec.get("role", "") or "").strip().lower()
        career = str(actor_spec.get("career", "") or "").strip().lower()
        site_affiliated = career in {"receiver", "shift_worker"} or (
            role == "worker" and str(scene.get("scene_type", "") or "").strip().lower() == "shift"
        )
        if event_phase in _BUSINESS_EVENT_GATHERING_PHASES and role == "worker":
            site_affiliated = True
        if source_kind == "seed" and role == "worker":
            site_affiliated = True
        explicit_site_affiliated = actor_spec.get("site_affiliated")
        if explicit_site_affiliated is not None:
            site_affiliated = bool(explicit_site_affiliated)

        occupation = self.sim.ecs.get(Occupation).get(eid)
        routine = self.sim.ecs.get(NPCRoutine).get(eid)
        if site_affiliated and occupation and isinstance(prop, dict):
            workplace = {"property_id": str(prop.get("id", "") or "").strip()}
            organization_eid = property_organization_eid(self.sim, prop)
            if organization_eid is not None:
                workplace["organization_eid"] = int(organization_eid)
            occupation.workplace = workplace
            controller = _property_access_controller(self.sim, prop)
            opening_window = controller.get("opening_window") if isinstance(controller, dict) else None
            if isinstance(opening_window, (tuple, list)) and len(opening_window) >= 2:
                occupation.shift_start = int(opening_window[0]) % 24
                occupation.shift_end = int(opening_window[1]) % 24
            if routine:
                routine.work = tuple(scene.get("anchor", routine.work)) if scene.get("anchor") else routine.work

        vitality = self.sim.ecs.get(Vitality).get(eid)
        hp_ratio_range = actor_spec.get("hp_ratio_range")
        if vitality and isinstance(hp_ratio_range, (tuple, list)) and len(hp_ratio_range) >= 2:
            try:
                low = max(0.05, min(1.0, float(hp_ratio_range[0])))
                high = max(low, min(1.0, float(hp_ratio_range[1])))
            except (TypeError, ValueError):
                low = high = None
            if low is not None and high is not None:
                target_ratio = rng.uniform(low, high)
                max_hp = max(1, int(getattr(vitality, "max_hp", 1) or 1))
                target_hp = int(round(max_hp * target_ratio))
                if max_hp > 1:
                    target_hp = min(max_hp - 1, target_hp)
                vitality.hp = max(1, min(max_hp, max(1, target_hp)))
                vitality.downed = False

        needs = self.sim.ecs.get(NPCNeeds).get(eid)
        needs_overrides = actor_spec.get("needs_overrides")
        if needs and isinstance(needs_overrides, dict):
            for need_name, raw_value in needs_overrides.items():
                if not hasattr(needs, str(need_name)):
                    continue
                value = raw_value
                if isinstance(raw_value, (tuple, list)) and len(raw_value) >= 2:
                    try:
                        low = float(raw_value[0])
                        high = float(raw_value[1])
                    except (TypeError, ValueError):
                        continue
                    value = rng.uniform(min(low, high), max(low, high))
                try:
                    setattr(needs, str(need_name), _clamp(float(value)))
                except (TypeError, ValueError):
                    continue

        statuses = self.sim.ecs.get(StatusEffects).get(eid)
        status_effects = actor_spec.get("status_effects")
        if statuses and isinstance(status_effects, (tuple, list)):
            for effect in status_effects:
                if not isinstance(effect, dict):
                    continue
                status_name = str(effect.get("status", "") or "").strip()
                if not status_name:
                    continue
                try:
                    duration = int(effect.get("duration", 1) or 1)
                except (TypeError, ValueError):
                    duration = 1
                statuses.add(
                    status=status_name,
                    duration=max(1, duration),
                    modifiers=dict(effect.get("modifiers", {}) or {}),
                )

        pool = [
            item_id
            for item_id in _business_event_item_pool(
                scene.get("scene_type"),
                scene.get("category"),
                actor_spec,
            )
            if item_id in ITEM_CATALOG
        ]
        extra_item_count = 0
        if pool:
            extra_item_count = 1
            if str(scene.get("scene_type", "") or "").strip().lower() == "delivery" and rng.random() < 0.55:
                extra_item_count += 1
            elif site_affiliated and rng.random() < 0.3:
                extra_item_count += 1
        carried_item_ids = []
        for _ in range(max(0, extra_item_count)):
            item_id = rng.choice(pool)
            if _give_item(self.sim, eid, item_id, quantity=1):
                carried_item_ids.append(item_id)

        note = {
            "scene_id": str(scene.get("scene_id", "") or "").strip(),
            "property_id": str(scene.get("property_id", "") or "").strip(),
            "scene_type": str(scene.get("scene_type", "") or "").strip().lower(),
            "category": str(scene.get("category", "") or "").strip().lower(),
            "event_phase": str(scene.get("event_phase", "") or "").strip().lower(),
            "role": role,
            "career": career,
            "site_affiliated": bool(site_affiliated),
            "carried_item_ids": tuple(carried_item_ids),
        }
        intel_note = {}
        if source_kind == "seed":
            intel_note = _business_event_seed_scene_actor_note(self.sim, scene, prop, actor_spec, rng=rng)
        else:
            intel_note = _business_event_followup_note(self.sim, scene, prop, actor_spec, rng=rng)
        if intel_note:
            followup_property_id = str(intel_note.get("target_property_id", "") or "").strip()
            followup_prop = self.sim.properties.get(followup_property_id) if followup_property_id else None
            followup_contact_role = str(career or role or "").strip().lower()
            followup_opportunity = _business_event_enrich_followup_opportunity(
                self.sim,
                dict(intel_note.get("opportunity", {}) or {}),
                followup_prop,
                contact_name=_entity_display_name(self.sim, eid, title_case=True),
                contact_role=followup_contact_role,
            )
            note.update({
                "followup_seed_id": str(intel_note.get("seed_id", "") or "").strip(),
                "local_line": str(intel_note.get("local_line", "") or "").strip(),
                "detail_line": str(intel_note.get("detail_line", "") or "").strip(),
                "followup_opportunity": followup_opportunity,
                "followup_property_id": followup_property_id,
                "followup_lead_kind": str(intel_note.get("lead_kind", "") or "").strip().lower(),
                "followup_shared": bool(intel_note.get("shared")),
            })

        if isinstance(prop, dict):
            _remember_property_lead_for_actor(
                self.sim,
                eid,
                prop,
                source_eid=None,
                lead_kind=str(note.get("followup_lead_kind", "") or "hours").strip().lower() or "hours",
                confidence=0.84 if site_affiliated else 0.66,
            )
        followup_property_id = str(note.get("followup_property_id", "") or "").strip()
        if followup_property_id:
            followup_prop = self.sim.properties.get(followup_property_id)
            if isinstance(followup_prop, dict):
                _remember_property_lead_for_actor(
                    self.sim,
                    eid,
                    followup_prop,
                    source_eid=None,
                    lead_kind=str(note.get("followup_lead_kind", "") or "hours").strip().lower() or "hours",
                    confidence=0.62,
                )

        _business_event_actor_state(self.sim)[int(eid)] = note

    def _spawn_scene_actor(self, scene, actor_spec, *, spawn_pos, route_points, rng):
        if not isinstance(spawn_pos, (tuple, list)) or len(spawn_pos) < 3:
            return None
        route_points = [
            (int(point[0]), int(point[1]), int(point[2]))
            for point in tuple(route_points or ())
            if isinstance(point, (tuple, list)) and len(point) >= 3
        ]
        if not route_points:
            route_points = [(int(spawn_pos[0]), int(spawn_pos[1]), int(spawn_pos[2]))]
        unique_points = []
        for point in route_points:
            if point not in unique_points:
                unique_points.append(point)

        role = str((actor_spec or {}).get("role", "civilian") or "civilian").strip().lower() or "civilian"
        career = str((actor_spec or {}).get("career", role) or role).strip().lower() or role
        eid = _spawn_human(
            self.sim,
            rng,
            role,
            (int(spawn_pos[0]), int(spawn_pos[1]), int(spawn_pos[2])),
            career=career,
            home=unique_points[0],
        )
        ai = self.sim.ecs.get(AI).get(eid)
        will = self.sim.ecs.get(NPCWill).get(eid)
        if ai and will:
            _sync_ai_intent(ai, will, self.sim.tick, "holding", target=unique_points[0], target_eid=None)
        scene["spawned_entity_ids"].append(eid)
        scene["actor_routes"][eid] = {
            "points": unique_points,
            "index": 0,
            "next_switch_tick": int(self.sim.tick) + int((actor_spec or {}).get("linger_ticks", 18) or 18),
            "linger_ticks": max(4, int((actor_spec or {}).get("linger_ticks", 18) or 18)),
        }
        self._decorate_scene_actor(scene, actor_spec, eid, rng=rng)
        return eid

    def _set_scene_actor_route(self, scene, eid, points):
        route = (scene.get("actor_routes", {}) if isinstance(scene, dict) else {}).get(eid)
        if not isinstance(route, dict):
            return
        cleaned = []
        for point in tuple(points or ()):
            if not isinstance(point, (tuple, list)) or len(point) < 3:
                continue
            normalized = (int(point[0]), int(point[1]), int(point[2]))
            if normalized not in cleaned:
                cleaned.append(normalized)
        if not cleaned:
            return
        route["points"] = cleaned
        route["index"] = 0
        route["next_switch_tick"] = int(self.sim.tick) + int(route.get("linger_ticks", 18) or 18)
        ai = self.sim.ecs.get(AI).get(eid)
        will = self.sim.ecs.get(NPCWill).get(eid)
        if ai:
            _sync_ai_intent(ai, will, self.sim.tick, "holding", target=cleaned[0], target_eid=None)

    def _scene_property_on_cooldown(self, property_id):
        property_id = str(property_id or "").strip()
        if not property_id:
            return False
        cooldowns = _business_event_scene_state(self.sim).get("cooldowns", {})
        if not isinstance(cooldowns, dict):
            return False
        end_tick = cooldowns.get(property_id)
        if end_tick is None:
            return False
        try:
            elapsed = int(self.sim.tick) - int(end_tick)
        except (TypeError, ValueError):
            return False
        if elapsed < 0:
            return False
        cooldown_ticks = _business_event_ticks_per_hour(self.sim) * _BUSINESS_EVENT_SCENE_PROPERTY_COOLDOWN_HOURS
        return elapsed < cooldown_ticks

    def _materialize_delivery_scene(self, scene, blueprint, rng):
        anchor = scene["anchor"]
        scene_prop = self._scene_property(scene)
        reserved = {anchor}

        vehicle_tiles = self._open_air_support_tiles(
            anchor,
            reserved=reserved,
            min_radius=3,
            max_radius=6,
            limit=8,
        )
        if not vehicle_tiles:
            vehicle_tiles = self._anchor_support_tiles(anchor, reserved=reserved, limit=5)
        vehicle_tile = vehicle_tiles[0] if vehicle_tiles else None
        if vehicle_tile is not None:
            self._register_scene_vehicle(scene, vehicle_tile, name=blueprint.get("vehicle_name", "Delivery Van"), rng=rng)
            reserved.add(vehicle_tile)

        cargo_tiles = []
        if vehicle_tile is not None:
            cargo_tiles = self._open_air_support_tiles(
                vehicle_tile,
                reserved=reserved,
                min_radius=1,
                max_radius=2,
                limit=4,
            )
        if not cargo_tiles:
            cargo_tiles = self._anchor_support_tiles(anchor, reserved=reserved, limit=6)
        cargo_tile = cargo_tiles[0] if cargo_tiles else None
        if cargo_tile is not None:
            interaction = _business_event_scene_fixture_interaction(
                self.sim,
                scene,
                scene_prop,
                fixture_type=blueprint.get("fixture_type", "delivery_cargo"),
                rng=rng,
            )
            cargo_property_id = self._register_scene_fixture(
                scene,
                cargo_tile,
                name=blueprint.get("fixture_name", "Parcel Stack"),
                fixture_type=blueprint.get("fixture_type", "delivery_cargo"),
                glyph=blueprint.get("fixture_glyph", "c"),
                extra_metadata=(interaction or {}).get("property_metadata"),
            )
            if cargo_property_id and isinstance(interaction, dict):
                container_kind = str(((interaction.get("property_metadata") or {}).get("container_kind", "scene"))).strip().lower() or "scene"
                loot_entries = [
                    dict(entry)
                    for entry in list(interaction.get("loot_entries", ()) or ())
                    if isinstance(entry, dict)
                ]
                if loot_entries:
                    container_entries = _property_runtime_container_entries(
                        self.sim,
                        cargo_property_id,
                        container_kind=container_kind,
                    )
                    container_entries[:] = loot_entries
            reserved.add(cargo_tile)

        actor_specs = list(blueprint.get("actor_specs", ()) or ())[:2]
        for index, actor_spec in enumerate(actor_specs):
            fallback_tile = cargo_tile or vehicle_tile or anchor
            route_seed = -int((self.sim.tick * 10) + index + 1)
            role = str((actor_spec or {}).get("role", "worker") or "worker").strip().lower() or "worker"
            intent = "working" if role == "worker" else "waiting"
            interior_target = (
                _pick_property_roam_tile(self.sim, scene_prop, route_seed, role=role, intent=intent)
                if scene_prop is not None
                else None
            )

            if index == 0 and vehicle_tile is not None:
                spawn_pos = vehicle_tile
                route_points = []
                if interior_target is not None and tuple(interior_target) != tuple(spawn_pos):
                    route_points.append(interior_target)
                if cargo_tile is not None and tuple(cargo_tile) != tuple(spawn_pos):
                    route_points.append(cargo_tile)
                route_points.append(vehicle_tile)
            else:
                spawn_pos = interior_target if interior_target is not None else fallback_tile
                route_points = []
                if cargo_tile is not None:
                    route_points.append(cargo_tile)
                elif vehicle_tile is not None:
                    route_points.append(vehicle_tile)
                if interior_target is not None:
                    route_points.append(interior_target)
                elif not route_points:
                    route_points.append(spawn_pos)
            eid = self._spawn_scene_actor(scene, actor_spec, spawn_pos=spawn_pos, route_points=route_points, rng=rng)
            if eid is not None:
                if index == 0:
                    courier_route = []
                    if interior_target is not None:
                        courier_route.append(interior_target)
                    if cargo_tile is not None:
                        courier_route.append(cargo_tile)
                    if vehicle_tile is not None:
                        courier_route.append(vehicle_tile)
                    self._set_scene_actor_route(scene, eid, courier_route)
                else:
                    receiver_route = []
                    if cargo_tile is not None:
                        receiver_route.append(cargo_tile)
                    elif vehicle_tile is not None:
                        receiver_route.append(vehicle_tile)
                    if interior_target is not None:
                        receiver_route.append(interior_target)
                    self._set_scene_actor_route(scene, eid, receiver_route)
                reserved.add((int(spawn_pos[0]), int(spawn_pos[1]), int(spawn_pos[2])))

    def _materialize_queue_scene(self, scene, blueprint, rng):
        anchor = scene["anchor"]
        reserved = {anchor}
        support_tiles = self._anchor_support_tiles(anchor, reserved=reserved, limit=6)
        fixture_tile = support_tiles[0] if support_tiles else None
        if fixture_tile is not None:
            self._register_scene_fixture(
                scene,
                fixture_tile,
                name=blueprint.get("fixture_name", "Queue Stand"),
                fixture_type=blueprint.get("fixture_type", "queue_marker"),
                glyph=blueprint.get("fixture_glyph", "q"),
            )
            reserved.add(fixture_tile)

        linger_tiles = [anchor] + self._anchor_support_tiles(anchor, reserved=reserved, limit=8)
        actor_specs = list(blueprint.get("actor_specs", ()) or ())
        for index, actor_spec in enumerate(actor_specs):
            spawn_pos = linger_tiles[index % len(linger_tiles)]
            route_points = [spawn_pos]
            if len(linger_tiles) > 1:
                route_points.append(linger_tiles[(index + 1) % len(linger_tiles)])
            eid = self._spawn_scene_actor(scene, actor_spec, spawn_pos=spawn_pos, route_points=route_points, rng=rng)
            if eid is not None:
                reserved.add((int(spawn_pos[0]), int(spawn_pos[1]), int(spawn_pos[2])))

    def _materialize_shift_scene(self, scene, blueprint, rng):
        anchor = scene["anchor"]
        reserved = {anchor}
        support_tiles = self._anchor_support_tiles(anchor, reserved=reserved, limit=6)
        fixture_tile = support_tiles[0] if support_tiles else None
        if fixture_tile is not None:
            scene_prop = self._scene_property(scene)
            interaction = _business_event_scene_fixture_interaction(
                self.sim,
                scene,
                scene_prop,
                fixture_type=blueprint.get("fixture_type", "shift_board"),
                rng=rng,
            )
            fixture_property_id = self._register_scene_fixture(
                scene,
                fixture_tile,
                name=blueprint.get("fixture_name", "Notice Board"),
                fixture_type=blueprint.get("fixture_type", "shift_board"),
                glyph=blueprint.get("fixture_glyph", "n"),
                extra_metadata=(interaction or {}).get("property_metadata"),
            )
            if fixture_property_id and isinstance(interaction, dict):
                container_kind = str(((interaction.get("property_metadata") or {}).get("container_kind", "scene"))).strip().lower() or "scene"
                loot_entries = [
                    dict(entry)
                    for entry in list(interaction.get("loot_entries", ()) or ())
                    if isinstance(entry, dict)
                ]
                if loot_entries:
                    container_entries = _property_runtime_container_entries(
                        self.sim,
                        fixture_property_id,
                        container_kind=container_kind,
                    )
                    container_entries[:] = loot_entries
            reserved.add(fixture_tile)

        cluster_tiles = [anchor] + self._anchor_support_tiles(anchor, reserved=reserved, limit=8)
        actor_specs = list(blueprint.get("actor_specs", ()) or ())
        for index, actor_spec in enumerate(actor_specs):
            spawn_pos = cluster_tiles[index % len(cluster_tiles)]
            route_points = [spawn_pos]
            if len(cluster_tiles) > 1:
                route_points.append(cluster_tiles[(index + 1) % len(cluster_tiles)])
            eid = self._spawn_scene_actor(scene, actor_spec, spawn_pos=spawn_pos, route_points=route_points, rng=rng)
            if eid is not None:
                reserved.add((int(spawn_pos[0]), int(spawn_pos[1]), int(spawn_pos[2])))

    def _materialize_gathering_scene(self, scene, blueprint, rng):
        anchor = scene["anchor"]
        reserved = {anchor}
        support_tiles = self._anchor_support_tiles(anchor, reserved=reserved, limit=6)
        fixture_tile = support_tiles[0] if support_tiles else None
        if fixture_tile is not None:
            scene_prop = self._scene_property(scene)
            interaction = _business_event_scene_fixture_interaction(
                self.sim,
                scene,
                scene_prop,
                fixture_type=blueprint.get("fixture_type", "meeting_board"),
                rng=rng,
            )
            fixture_property_id = self._register_scene_fixture(
                scene,
                fixture_tile,
                name=blueprint.get("fixture_name", "Meeting Board"),
                fixture_type=blueprint.get("fixture_type", "meeting_board"),
                glyph=blueprint.get("fixture_glyph", "m"),
                extra_metadata=(interaction or {}).get("property_metadata"),
            )
            if fixture_property_id and isinstance(interaction, dict):
                container_kind = str(((interaction.get("property_metadata") or {}).get("container_kind", "scene"))).strip().lower() or "scene"
                loot_entries = [
                    dict(entry)
                    for entry in list(interaction.get("loot_entries", ()) or ())
                    if isinstance(entry, dict)
                ]
                if loot_entries:
                    container_entries = _property_runtime_container_entries(
                        self.sim,
                        fixture_property_id,
                        container_kind=container_kind,
                    )
                    container_entries[:] = loot_entries
            reserved.add(fixture_tile)

        cluster_tiles = [anchor] + self._anchor_support_tiles(anchor, reserved=reserved, limit=8)
        actor_specs = list(blueprint.get("actor_specs", ()) or ())
        for index, actor_spec in enumerate(actor_specs):
            spawn_pos = cluster_tiles[index % len(cluster_tiles)]
            route_points = [spawn_pos]
            if not bool((actor_spec or {}).get("fixed_position")) and len(cluster_tiles) > 1:
                route_points.append(cluster_tiles[(index + 1) % len(cluster_tiles)])
            eid = self._spawn_scene_actor(scene, actor_spec, spawn_pos=spawn_pos, route_points=route_points, rng=rng)
            if eid is not None:
                reserved.add((int(spawn_pos[0]), int(spawn_pos[1]), int(spawn_pos[2])))

    def _materialize_scene(self, spec):
        blueprint = spec["blueprint"]
        scene = {
            "scene_id": spec["scene_id"],
            "property_id": spec["property_id"],
            "chunk": spec["chunk"],
            "category": str((spec.get("pulse") or {}).get("category", "") or "").strip().lower(),
            "event_phase": str((spec.get("pulse") or {}).get("event_phase", "") or "").strip().lower(),
            "traffic_state": str((spec.get("pulse") or {}).get("traffic_state", "") or "").strip().lower(),
            "scene_type": str(blueprint.get("scene_type", "") or "").strip().lower(),
            "source_kind": str(spec.get("source_kind", "pulse") or "pulse").strip().lower(),
            "seed_id": str(spec.get("seed_id", "") or "").strip(),
            "anchor": tuple(spec["anchor"]),
            "spawned_entity_ids": [],
            "spawned_property_ids": [],
            "actor_routes": {},
            "release_budget": max(0, int(blueprint.get("release_budget", 0) or 0)),
            "drift_preferred": bool(blueprint.get("drift_preferred", False)),
            "keep_hours": max(1, int(blueprint.get("keep_hours", 2) or 2)),
            "pulse_hour": max(0, int((spec.get("pulse") or {}).get("hour", 0) or 0)),
        }
        rng = random.Random(f"{self.sim.seed}:business-scene:{scene['scene_id']}")
        prop = self._scene_property(scene)
        if scene["source_kind"] != "seed":
            if prop is not None:
                _ensure_business_event_seed_for_scene(self.sim, scene, prop, rng=rng)
        elif prop is not None:
            _ensure_business_event_consequence_seed_for_scene(self.sim, scene, prop, rng=rng)
        if scene["scene_type"] == "delivery":
            self._materialize_delivery_scene(scene, blueprint, rng)
        elif scene["scene_type"] == "queue":
            self._materialize_queue_scene(scene, blueprint, rng)
        elif scene["scene_type"] == "shift":
            self._materialize_shift_scene(scene, blueprint, rng)
        elif scene["scene_type"] == "gathering":
            self._materialize_gathering_scene(scene, blueprint, rng)
        if scene["spawned_entity_ids"] or scene["spawned_property_ids"]:
            _business_event_scene_state(self.sim)["active"][scene["scene_id"]] = scene

    def _release_scene_actor(self, scene, eid):
        source = (
            f"business_scene:{str(scene.get('scene_type', '') or '').strip().lower()}:"
            f"{str(scene.get('event_phase', '') or '').strip().lower()}:"
            f"{str(scene.get('property_id', '') or '').strip()}"
        )
        released = _release_actor_to_newcomer(
            self.sim,
            eid,
            origin=source,
            arrived_tick=self.sim.tick,
            drift_preferred=bool(scene.get("drift_preferred", False)),
        )
        return released is not None

    def _scene_actor_in_active_dialogue(self, eid):
        dialog_ui = getattr(self.sim, "dialog_ui", None)
        if not isinstance(dialog_ui, dict) or not bool(dialog_ui.get("open")):
            return False
        npc_eid = dialog_ui.get("npc_eid")
        try:
            return int(npc_eid) == int(eid)
        except (TypeError, ValueError):
            return npc_eid == eid

    def _scene_actor_in_live_combat(self, eid):
        ai = self.sim.ecs.get(AI).get(eid)
        if ai and str(ai.state or "").strip().lower() == "protecting":
            return True

        will = self.sim.ecs.get(NPCWill).get(eid)
        if will and str(will.intent or "").strip().lower() == "protecting":
            return True

        for other_eid, other_ai in self.sim.ecs.get(AI).items():
            if int(other_eid) == int(eid):
                continue
            if str(getattr(other_ai, "state", "") or "").strip().lower() != "protecting":
                continue
            try:
                if int(getattr(other_ai, "target_eid", None)) == int(eid):
                    return True
            except (TypeError, ValueError):
                if getattr(other_ai, "target_eid", None) == eid:
                    return True

        for other_eid, other_will in self.sim.ecs.get(NPCWill).items():
            if int(other_eid) == int(eid):
                continue
            if str(getattr(other_will, "intent", "") or "").strip().lower() != "protecting":
                continue
            try:
                if int(getattr(other_will, "target_eid", None)) == int(eid):
                    return True
            except (TypeError, ValueError):
                if getattr(other_will, "target_eid", None) == eid:
                    return True

        return False

    def _scene_actor_preservation_mode(self, eid):
        if eid is None or self.sim.ecs.get(Position).get(eid) is None:
            return ""
        if _active_contractor_record(self.sim, eid, ally_eid=self.player_eid) is not None:
            return "keep_hired"
        if actor_player_business_employment(self.sim, eid, owner_eid=self.player_eid) is not None:
            return "keep_hired"
        if self._scene_actor_in_live_combat(eid):
            return "keep_combat"
        if self._scene_actor_in_active_dialogue(eid):
            return "release_dialogue"
        return ""

    def _prepare_preserved_scene_actor(self, eid, mode):
        if str(mode or "").strip().lower() != "keep_hired":
            return
        if actor_player_business_employment(self.sim, eid, owner_eid=self.player_eid) is None:
            return

        ai = self.sim.ecs.get(AI).get(eid)
        if ai and str(ai.state or "").strip().lower() == "holding" and ai.target_eid is None:
            ai.state = "idle"
            ai.target = None
            ai.target_eid = None

        will = self.sim.ecs.get(NPCWill).get(eid)
        if will and str(will.intent or "").strip().lower() == "holding" and will.target_eid is None:
            will.intent = "idle"
            will.score = 0.0
            will.target = None
            will.target_eid = None
            will.last_tick = self.sim.tick

    def _chunk_population_target(self, chunk):
        return max(0, int(_business_event_chunk_population_target(self.sim, chunk) or 0))

    def _chunk_release_headroom(self, chunk, *, tallies=None):
        if not isinstance(chunk, (tuple, list)) or len(chunk) < 2:
            return 0
        try:
            key = (int(chunk[0]), int(chunk[1]))
        except (TypeError, ValueError):
            return 0
        tallies = tallies if isinstance(tallies, dict) else _chunk_entity_tallies(self.sim)
        tally = tallies.get(key, {}) if isinstance(tallies, dict) else {}
        persistent_entities = max(0, int((tally or {}).get("persistent_entities", 0) or 0))
        unsettled_spillover = max(0, int((tally or {}).get("business_scene_unsettled", 0) or 0))
        population_headroom = max(0, self._chunk_population_target(key) - persistent_entities)
        spillover_headroom = max(0, _BUSINESS_EVENT_RELEASE_CAP - unsettled_spillover)
        return max(0, min(population_headroom, spillover_headroom))

    def _chunk_spillover_cleanup_candidates(self, chunk):
        if not isinstance(chunk, (tuple, list)) or len(chunk) < 2:
            return []
        try:
            key = (int(chunk[0]), int(chunk[1]))
        except (TypeError, ValueError):
            return []

        active_actor_ids = _active_business_scene_actor_ids(self.sim)
        positions = self.sim.ecs.get(Position)
        player_pos = self._player_pos()
        candidates = []
        for eid, newcomer in list(self.sim.ecs.get(NPCSettlement).items()):
            if not _is_business_scene_spillover(newcomer) or not _business_scene_spillover_unsettled(newcomer):
                continue
            try:
                int_eid = int(eid)
            except (TypeError, ValueError):
                continue
            if int_eid in active_actor_ids:
                continue
            pos = positions.get(int_eid)
            if pos is None:
                continue
            try:
                actor_chunk = self.sim.chunk_coords(int(pos.x), int(pos.y))
            except (TypeError, ValueError):
                continue
            if actor_chunk != key:
                continue
            if self._scene_actor_preservation_mode(int_eid):
                continue
            distance_to_player = 9999
            if player_pos is not None and int(player_pos.z) == int(pos.z):
                distance_to_player = _manhattan(int(pos.x), int(pos.y), int(player_pos.x), int(player_pos.y))
                if distance_to_player <= 6:
                    continue
            candidates.append((
                int(getattr(newcomer, "arrived_tick", 0) or 0),
                -int(distance_to_player),
                int_eid,
            ))
        candidates.sort()
        return [eid for _arrived_tick, _neg_distance, eid in candidates]

    def _prune_chunk_spillover(self, chunk, *, tallies=None):
        if not isinstance(chunk, (tuple, list)) or len(chunk) < 2:
            return
        try:
            key = (int(chunk[0]), int(chunk[1]))
        except (TypeError, ValueError):
            return
        tallies = tallies if isinstance(tallies, dict) else _chunk_entity_tallies(self.sim)
        tally = tallies.get(key, {}) if isinstance(tallies, dict) else {}
        persistent_entities = max(0, int((tally or {}).get("persistent_entities", 0) or 0))
        unsettled_spillover = max(0, int((tally or {}).get("business_scene_unsettled", 0) or 0))
        if persistent_entities <= self._chunk_population_target(key) and unsettled_spillover <= _BUSINESS_EVENT_RELEASE_CAP:
            return

        trim_count = max(
            max(0, persistent_entities - self._chunk_population_target(key)),
            max(0, unsettled_spillover - _BUSINESS_EVENT_RELEASE_CAP),
        )
        if trim_count <= 0:
            return

        for eid in self._chunk_spillover_cleanup_candidates(key)[:trim_count]:
            _business_event_actor_state(self.sim).pop(int(eid), None)
            self.sim.remove_entity(int(eid))

    def _scene_release_targets(self, scene, *, preserve_modes=None, chunk_tallies=None):
        actor_ids = [
            int(eid)
            for eid in list(scene.get("spawned_entity_ids", ()) or ())
            if self.sim.ecs.get(Position).get(eid) is not None
        ]
        if not actor_ids:
            return set()

        preserve_modes = dict(preserve_modes or {})
        forced_release = {
            int(eid)
            for eid, mode in preserve_modes.items()
            if str(mode or "").strip().lower() == "release_dialogue"
        }
        actor_ids = [
            int(eid)
            for eid in actor_ids
            if not str(preserve_modes.get(int(eid), "") or "").strip().lower().startswith("keep_")
            and int(eid) not in forced_release
        ]

        release_headroom = self._chunk_release_headroom(scene.get("chunk"), tallies=chunk_tallies)
        budget = min(
            len(actor_ids),
            max(0, int(scene.get("release_budget", 0) or 0)),
            max(0, int(release_headroom)),
        )
        if budget <= 0:
            return forced_release

        actor_state = _business_event_actor_state(self.sim)
        ranked = []
        for index, eid in enumerate(actor_ids):
            note = actor_state.get(int(eid), {}) if isinstance(actor_state, dict) else {}
            local_line = str((note or {}).get("local_line", "") or "").strip()
            detail_line = str((note or {}).get("detail_line", "") or "").strip()
            followup_seed_id = str((note or {}).get("followup_seed_id", "") or "").strip()
            followup_opportunity = (note or {}).get("followup_opportunity", {})
            ranked.append((
                -int(bool(followup_seed_id)),
                -int(isinstance(followup_opportunity, dict) and bool(followup_opportunity)),
                -int(bool(local_line or detail_line)),
                index,
                int(eid),
            ))
        ranked.sort()
        return forced_release | {eid for *_score, eid in ranked[:budget]}

    def _dematerialize_scene(self, scene, *, chunk_tallies=None):
        property_id = str(scene.get("property_id", "") or "").strip()
        if property_id:
            _business_event_scene_state(self.sim).setdefault("cooldowns", {})[property_id] = int(self.sim.tick)
        for property_id in list(scene.get("spawned_property_ids", ())):
            prop = self.sim.properties.get(property_id)
            if prop is None:
                continue
            _clear_property_runtime_container_state(self.sim, property_id)
            self.sim.remove_property(property_id)

        preserve_modes = {
            int(eid): self._scene_actor_preservation_mode(eid)
            for eid in list(scene.get("spawned_entity_ids", ()) or ())
        }
        release_targets = self._scene_release_targets(scene, preserve_modes=preserve_modes, chunk_tallies=chunk_tallies)
        for eid in list(scene.get("spawned_entity_ids", ())):
            mode = str(preserve_modes.get(int(eid), "") or "").strip().lower()
            if mode.startswith("keep_"):
                self._prepare_preserved_scene_actor(int(eid), mode)
                continue
            if int(eid) in release_targets and self._release_scene_actor(scene, eid):
                continue
            _business_event_actor_state(self.sim).pop(int(eid), None)
            self.sim.remove_entity(eid)

    def _update_scene_actor_routes(self, scene):
        positions = self.sim.ecs.get(Position)
        ais = self.sim.ecs.get(AI)
        wills = self.sim.ecs.get(NPCWill)
        for eid, route in list(scene.get("actor_routes", {}).items()):
            pos = positions.get(eid)
            ai = ais.get(eid)
            if not pos or not ai:
                continue
            preserve_mode = self._scene_actor_preservation_mode(eid)
            if preserve_mode:
                if str(preserve_mode).strip().lower().startswith("keep_"):
                    self._prepare_preserved_scene_actor(int(eid), preserve_mode)
                continue
            if _entity_is_downed(self.sim, eid):
                _apply_downed_actor_state(self.sim, eid, tick=self.sim.tick)
                continue
            points = [
                (int(point[0]), int(point[1]), int(point[2]))
                for point in tuple(route.get("points", ()) or ())
                if isinstance(point, (tuple, list)) and len(point) >= 3
            ]
            if not points:
                continue
            index = int(route.get("index", 0) or 0) % len(points)
            target = points[index]
            if (int(pos.x), int(pos.y), int(pos.z)) == target and len(points) > 1:
                if int(self.sim.tick) >= int(route.get("next_switch_tick", 0) or 0):
                    index = (index + 1) % len(points)
                    route["index"] = index
                    route["next_switch_tick"] = int(self.sim.tick) + int(route.get("linger_ticks", 18) or 18)
                    target = points[index]
            if ai.state != "holding" or tuple(ai.target or ()) != tuple(target) or ai.target_eid is not None:
                _sync_ai_intent(ai, wills.get(eid), self.sim.tick, "holding", target=target, target_eid=None)

    def _scene_should_keep(self, scene):
        if not isinstance(scene, dict):
            return False
        pulse_hour = int(scene.get("pulse_hour", 0) or 0)
        keep_hours = max(1, int(scene.get("keep_hours", 2) or 2))
        try:
            current_hour = int(_world_hour(self.sim)) % 24
        except (TypeError, ValueError):
            current_hour = 0
        forward_diff = (current_hour - pulse_hour) % 24
        backward_diff = (pulse_hour - current_hour) % 24
        min_diff = min(forward_diff, backward_diff)
        return min_diff < keep_hours

    def update(self):
        active_chunk = self._active_chunk_coord()
        player_pos = self._player_pos()
        state = _business_event_scene_state(self.sim)
        active = state.setdefault("active", {})
        chunk_tallies = _chunk_entity_tallies(self.sim)
        _prune_business_event_seeds(self.sim, active_scene_ids=active.keys())

        if active_chunk is None or player_pos is None:
            for scene in list(active.values()):
                self._dematerialize_scene(scene, chunk_tallies=chunk_tallies)
            active.clear()
            _prune_business_event_seeds(self.sim, active_scene_ids=())
            return

        desired_specs = self._candidate_scene_specs()
        desired_ids = {spec["scene_id"] for spec in desired_specs}

        for scene_id in list(active.keys()):
            if scene_id in desired_ids:
                continue
            scene = active.get(scene_id)
            if scene is not None and self._scene_should_keep(scene):
                continue
            scene = active.pop(scene_id)
            self._dematerialize_scene(scene, chunk_tallies=chunk_tallies)

        for spec in desired_specs:
            if spec["scene_id"] in active:
                continue
            self._materialize_scene(spec)

        chunk_tallies = _chunk_entity_tallies(self.sim)
        for scene in list(active.values()):
            self._update_scene_actor_routes(scene)
        self._prune_chunk_spillover(active_chunk, tallies=chunk_tallies)
        _prune_business_event_seeds(self.sim, active_scene_ids=active.keys())
