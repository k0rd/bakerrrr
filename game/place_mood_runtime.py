"""Derived place mood and ambient ritual helpers.

This module is intentionally read-only with respect to world state. It turns
already-existing property, scene, reputation, pressure, flora, and event facts
into compact presentation/mechanics hints for the business-scene layer.
"""

from __future__ import annotations

import random

from game.economy import strongest_local_trade_pressure_for_property
from game.organizations import local_protective_pressure_snapshot
from game.property_runtime import property_display_position, property_focus_position, property_metadata
from game.quiet_maintenance_runtime import quiet_maintenance_status
from game.systems_business_reputation import property_business_reputation_snapshot, property_supports_business_reputation
from game.underground_culture import culture_profile_for_property


PLACE_MOOD_FIELD_KEYS = (
    "place_mood_kind",
    "place_mood_label",
    "place_mood_reason",
    "place_mood_confidence",
    "place_mood_visible_cue",
    "place_mood_mechanical_tags",
    "place_mood_scene_bias",
)

PLACE_TEXTURE_FIELD_KEYS = (
    "place_texture_kind",
    "place_texture_label",
    "place_texture_reason",
    "place_texture_visible_cue",
    "place_texture_confidence",
    "place_texture_mechanical_tags",
    "place_texture_light_profile_hint",
    "rumor_weather_kind",
    "rumor_weather_label",
    "rumor_weather_summary",
    "rumor_weather_dialogue_bias",
)

AMBIENT_RITUAL_FIELD_KEYS = (
    "ambient_ritual_kind",
    "ambient_ritual_label",
    "ambient_ritual_summary",
    "ambient_ritual_action",
    "ambient_ritual_fixture_name",
    "ambient_ritual_fixture_type",
    "ambient_ritual_fixture_glyph",
    "ambient_ritual_fixture_color",
    "ambient_ritual_actor_line",
    "ambient_ritual_detail_line",
    "ambient_ritual_log_text",
    "ambient_ritual_mechanical_tags",
    "ambient_ritual_scene_bias",
)

RUMOR_WEATHER_KINDS = frozenset({
    "generous",
    "talking",
    "busy",
    "tired",
    "spooked",
    "watchful",
    "shut_tight",
})


def _text(value):
    return str(value or "").strip()


def _float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _slug(value):
    return _text(value).lower()


def _prop_id(prop):
    return _text((prop or {}).get("id"))


def _prop_name(prop):
    return _text((prop or {}).get("name")) or _prop_id(prop) or "the place"


def _prop_archetype(prop):
    metadata = property_metadata(prop) if isinstance(prop, dict) else {}
    return _slug(metadata.get("archetype") or (prop or {}).get("kind"))


def _prop_anchor(prop):
    anchor = property_focus_position(prop) or property_display_position(prop)
    if not isinstance(anchor, (tuple, list)) or len(anchor) < 3:
        return None
    try:
        return (int(anchor[0]), int(anchor[1]), int(anchor[2]))
    except (TypeError, ValueError):
        return None


def _position_tuple(sim, *, actor_eid=None, x=None, y=None, z=None):
    if actor_eid is not None and sim is not None:
        pos = None
        try:
            from game.components import Position

            pos = sim.ecs.get(Position).get(actor_eid)
        except Exception:
            pos = None
        if pos is not None:
            try:
                return (int(pos.x), int(pos.y), int(pos.z))
            except (TypeError, ValueError):
                return None
    if x is None or y is None:
        return None
    try:
        return (int(x), int(y), int(0 if z is None else z))
    except (TypeError, ValueError):
        return None


def _chunk_for(sim, anchor):
    if sim is None or anchor is None or not hasattr(sim, "chunk_coords"):
        return None
    try:
        return sim.chunk_coords(int(anchor[0]), int(anchor[1]))
    except (TypeError, ValueError):
        return None


def _active_business_scene_store(sim):
    state = getattr(sim, "business_event_scene_state", None)
    if not isinstance(state, dict):
        return {}
    active = state.get("active", {})
    return active if isinstance(active, dict) else {}


def _scene_anchor(scene, prop):
    anchor = (scene or {}).get("anchor") if isinstance(scene, dict) else None
    if isinstance(anchor, (tuple, list)) and len(anchor) >= 3:
        try:
            return (int(anchor[0]), int(anchor[1]), int(anchor[2]))
        except (TypeError, ValueError):
            pass
    return _prop_anchor(prop)


def _scene_live(scene):
    if not isinstance(scene, dict):
        return False
    status = _slug(scene.get("status") or scene.get("state"))
    if status in {"ended", "expired", "complete", "completed", "cancelled", "failed", "inactive"}:
        return False
    if bool(scene.get("dematerialized")) or bool(scene.get("ended")):
        return False
    return True


def _category_for(prop, pulse=None, scene=None):
    for source in (scene, pulse):
        if isinstance(source, dict):
            category = _slug(source.get("category"))
            if category:
                return category
    archetype = _prop_archetype(prop)
    if archetype in {"clinic", "hospital", "backroom_clinic", "herbalist_shop", "herbalist_camp", "butcher_shop"}:
        return "medical"
    if archetype in {"bar", "tavern", "roadhouse", "restaurant", "street_kitchen", "casino"}:
        return "hospitality"
    if archetype in {"station", "jail", "courthouse", "security_office", "watch_post"}:
        return "secure"
    if archetype in {"freight_depot", "breaker_yard", "salvage_camp", "drydock_yard", "work_shed", "pump_house"}:
        return "industrial"
    if archetype in {"relay_post", "truck_stop", "bus_stop", "ferry_terminal"}:
        return "transit"
    if "residential" in archetype or archetype in {"apartment", "residence", "shelter"}:
        return "residential"
    if archetype:
        return "retail"
    return "general"


def _scene_or_pulse_value(key, scene=None, pulse=None, default=""):
    if isinstance(scene, dict):
        value = scene.get(key)
        if value not in (None, ""):
            return value
    if isinstance(pulse, dict):
        value = pulse.get(key)
        if value not in (None, ""):
            return value
    return default


def _nearby_flora_count(sim, prop, *, radius=5):
    if sim is None or not isinstance(prop, dict):
        return 0
    anchor = _prop_anchor(prop)
    patches = getattr(sim, "flora_patches", None)
    if anchor is None or not isinstance(patches, dict):
        return 0
    ax, ay, az = anchor
    count = 0
    for record in patches.values():
        if not isinstance(record, dict):
            continue
        try:
            x = int(record.get("x", 0))
            y = int(record.get("y", 0))
            z = int(record.get("z", 0))
        except (TypeError, ValueError):
            continue
        if z != az:
            continue
        if abs(x - ax) + abs(y - ay) <= int(radius):
            count += 1
    return count


def _world_event_context_key(scene=None, pulse=None):
    return _slug(_scene_or_pulse_value("world_event_context_key", scene=scene, pulse=pulse))


def _mood_candidate(kind, label, reason, cue, score, *, tags=(), bias=0.0):
    return {
        "kind": _slug(kind),
        "label": _text(label),
        "reason": _text(reason),
        "visible_cue": _text(cue),
        "score": _float(score),
        "mechanical_tags": tuple(_slug(tag) for tag in tuple(tags or ()) if _text(tag)),
        "scene_bias": _float(bias),
    }


def place_mood_snapshot(sim, prop, *, scene=None, pulse=None):
    """Return a deterministic, derived mood read for a property/scene."""

    if not isinstance(prop, dict):
        return {}
    scene = scene if isinstance(scene, dict) else {}
    pulse = pulse if isinstance(pulse, dict) else {}
    category = _category_for(prop, pulse=pulse, scene=scene)
    phase = _slug(_scene_or_pulse_value("event_phase", scene=scene, pulse=pulse))
    owner_signal = _slug(_scene_or_pulse_value("owner_signal_kind", scene=scene, pulse=pulse))
    operating_style = _slug(_scene_or_pulse_value("operating_style_kind", scene=scene, pulse=pulse))
    customer_mix = _text(_scene_or_pulse_value("customer_mix_label", scene=scene, pulse=pulse))
    staff_mood = _text(_scene_or_pulse_value("staff_mood_label", scene=scene, pulse=pulse))
    world_event_key = _world_event_context_key(scene=scene, pulse=pulse)
    prop_name = _prop_name(prop)

    candidates = []
    candidates.append(_mood_candidate(
        "steady",
        "steady",
        f"{prop_name} is keeping its ordinary rhythm",
        "ordinary foot traffic and routine work are holding the place together",
        0.18,
        tags=("calm",),
        bias=0.02,
    ))

    if phase in {"regulars_spill", "mutual_aid_table", "tenant_meetup", "neighbors_lingering"}:
        candidates.append(_mood_candidate(
            "warm",
            "warm",
            f"{prop_name} has people treating it like part of their day",
            "familiar faces are lingering without looking lost",
            0.72,
            tags=("calm", "social"),
            bias=0.12,
        ))
    if phase in {"grumbling_front", "soft_front", "afterhours_aftermath", "taped_off_front", "street_triage"}:
        candidates.append(_mood_candidate(
            "strained",
            "strained",
            f"{prop_name} is carrying visible pressure at the frontage",
            "people keep watching the door, the street, or each other",
            0.76,
            tags=("strained", "social_pressure"),
            bias=0.16,
        ))
    if phase in {"block_watch", "owner_screening", "visitor_screening", "booking_queue", "security_sweep"} or owner_signal == "screened":
        candidates.append(_mood_candidate(
            "watched",
            "watched",
            f"{prop_name} has active eyes on the threshold",
            "the boundary is being checked instead of merely implied",
            0.82,
            tags=("watched", "boundary"),
            bias=0.18,
        ))
    if phase in {"aftermath_cleanup", "fire_response", "maintenance_loop"}:
        candidates.append(_mood_candidate(
            "repairing",
            "repairing",
            f"{prop_name} is being put back into working order",
            "tools, cleanup gear, or service talk are visible around the site",
            0.73,
            tags=("maintenance", "strained"),
            bias=0.13,
        ))
    maintenance = quiet_maintenance_status(sim, prop) if sim is not None else {}
    if isinstance(maintenance, dict) and maintenance.get("recent"):
        last_kind = _slug(maintenance.get("last_kind"))
        cue = _text(maintenance.get("visible_cue")) or "small practical care is visible"
        if last_kind == "minor_repair":
            candidates.append(_mood_candidate(
                "repairing",
                "mending",
                f"{prop_name} has fresh small maintenance work in view",
                cue,
                0.78,
                tags=("maintenance", "work"),
                bias=0.12,
            ))
        else:
            candidates.append(_mood_candidate(
                "kept",
                "kept",
                f"{prop_name} is showing recent care",
                cue,
                0.7,
                tags=("maintenance", "care", "calm"),
                bias=0.08,
            ))
    elif isinstance(maintenance, dict) and maintenance.get("neglected"):
        counts = maintenance.get("cultivation_counts") if isinstance(maintenance.get("cultivation_counts"), dict) else {}
        damage_count = int(maintenance.get("visible_damage_count", 0) or 0)
        if damage_count > 0:
            cue = "visible damage is still waiting for the stronger repair path"
        elif int(counts.get("failed", 0) or 0) > 0:
            cue = "some planted care has withered instead of recovering"
        else:
            cue = "the cared-for edge is starting to slip"
        candidates.append(_mood_candidate(
            "neglected",
            "neglected",
            f"{prop_name} has upkeep cues nobody has settled yet",
            cue,
            0.6 + min(0.16, float(max(damage_count, int(counts.get("failed", 0) or 0))) * 0.03),
            tags=("maintenance", "strained"),
            bias=0.09,
        ))
    if phase in {"candle_vigil", "street_triage", "clinic_outreach"}:
        candidates.append(_mood_candidate(
            "tender",
            "tender",
            f"{prop_name} is being handled with care in public",
            "people are moving softer around the visible setup",
            0.78,
            tags=("care", "social"),
            bias=0.11,
        ))
    if phase in {"delivery_run", "loading_push", "manifest_check", "dispatch_surge", "boarding_crush", "arrival_handoff"}:
        candidates.append(_mood_candidate(
            "hurried",
            "hurried",
            f"{prop_name} is catching route pressure",
            "hands, lists, and arrivals are moving faster than the room wants",
            0.67,
            tags=("work", "motion"),
            bias=0.09,
        ))

    if owner_signal in {"thin", "strained", "closed_off"} or operating_style in {"thin", "strained"}:
        cue = customer_mix or staff_mood or "the floor is not carrying itself cleanly"
        candidates.append(_mood_candidate(
            "neglected",
            "thin",
            f"{prop_name} is showing owner-side strain",
            cue,
            0.74,
            tags=("owner_read", "strained"),
            bias=0.14,
        ))
    if owner_signal in {"loyal", "curated"} or operating_style in {"loyal", "curated", "bargain"}:
        cue = customer_mix or staff_mood or "people seem to understand what this place is trying to be"
        candidates.append(_mood_candidate(
            "loyal",
            "loyal",
            f"{prop_name} has a coherent local read",
            cue,
            0.69,
            tags=("owner_read", "social", "calm"),
            bias=0.1,
        ))
    if owner_signal == "expensive" or operating_style == "expensive":
        candidates.append(_mood_candidate(
            "brittle",
            "brittle",
            f"{prop_name} has price tension at the edge",
            "customers are looking twice before they commit",
            0.7,
            tags=("strained", "owner_read"),
            bias=0.12,
        ))

    if world_event_key == "power_outage":
        candidates.append(_mood_candidate(
            "dimmed",
            "dimmed",
            f"{prop_name} is adjusting to a bad light situation",
            "lights and backup routines are shaping the frontage",
            0.81,
            tags=("maintenance", "watched"),
            bias=0.2,
        ))
    elif world_event_key == "supply_shortage":
        candidates.append(_mood_candidate(
            "short",
            "short",
            f"{prop_name} is feeling supply pressure",
            "people are noticing what is missing or being counted twice",
            0.74,
            tags=("shortage", "work"),
            bias=0.14,
        ))
    elif world_event_key == "faction_clash":
        candidates.append(_mood_candidate(
            "edged",
            "edged",
            f"{prop_name} is moving under outside pressure",
            "the scene feels careful in a way nobody is quite naming",
            0.72,
            tags=("watched", "strained"),
            bias=0.15,
        ))

    pressure = local_protective_pressure_snapshot(sim, prop) if sim is not None else {}
    if isinstance(pressure, dict) and pressure.get("active"):
        state_label = _text(pressure.get("state_label")) or "watch pressure"
        candidates.append(_mood_candidate(
            "watched",
            "watched",
            f"{prop_name} is under {state_label.lower()}",
            _text(pressure.get("summary")) or "local eyes are already organized here",
            0.8 + min(0.12, _float(pressure.get("watchfulness")) * 0.015),
            tags=("watched", "boundary"),
            bias=0.18,
        ))

    trade_pressure = strongest_local_trade_pressure_for_property(sim, prop, min_abs=3.0) if sim is not None else None
    if isinstance(trade_pressure, dict):
        value = _float(trade_pressure.get("value"))
        item_name = _text(trade_pressure.get("item_name")) or "stock"
        if value > 0:
            candidates.append(_mood_candidate(
                "overstocked",
                "well stocked",
                f"{prop_name} has plenty of {item_name} right now",
                "the shelves look heavier in one specific direction",
                0.63 + min(0.16, abs(value) * 0.02),
                tags=("stock", "oversupply"),
                bias=0.08,
            ))
        elif value < 0:
            candidates.append(_mood_candidate(
                "wanted",
                "wanted",
                f"{prop_name} is short on {item_name}",
                "the counter is paying more attention to that kind of supply",
                0.65 + min(0.16, abs(value) * 0.02),
                tags=("stock", "shortage"),
                bias=0.1,
            ))

    if property_supports_business_reputation(prop):
        snapshot = property_business_reputation_snapshot(sim, _prop_id(prop))
        if isinstance(snapshot, dict):
            staple = _float(snapshot.get("staple_score"))
            trouble = _float(snapshot.get("trouble_score")) + _float(snapshot.get("gouging_score"))
            loyalty = _float(snapshot.get("loyalty")) + _float(snapshot.get("trust"))
            fear = _float(snapshot.get("fear")) + _float(snapshot.get("heat"))
            if staple >= 0.34 or loyalty >= 0.55:
                candidates.append(_mood_candidate(
                    "warm",
                    "warm",
                    f"{prop_name} has earned familiar traffic",
                    _text(snapshot.get("community_note")) or "people seem to know how this place treats them",
                    0.64 + min(0.18, max(staple, loyalty * 0.5)),
                    tags=("social", "calm"),
                    bias=0.1,
                ))
            if trouble >= 0.42 or fear >= 0.5:
                candidates.append(_mood_candidate(
                    "strained",
                    "strained",
                    f"{prop_name} has a troubled local read",
                    _text(snapshot.get("community_note")) or "the room is being measured before anyone commits",
                    0.66 + min(0.18, max(trouble, fear * 0.5)),
                    tags=("strained", "watched"),
                    bias=0.14,
                ))

    if _nearby_flora_count(sim, prop) >= 2:
        candidates.append(_mood_candidate(
            "softened",
            "softened",
            f"{prop_name} has live greenery softening the edge",
            "plants and color are doing quiet work around the frontage",
            0.52,
            tags=("care", "calm"),
            bias=0.05,
        ))

    best = max(
        candidates,
        key=lambda row: (
            _float(row.get("score")),
            _slug(row.get("kind")),
            _text(row.get("reason")),
        ),
    )
    return {
        "mood_kind": best["kind"],
        "mood_label": best["label"],
        "mood_reason": best["reason"],
        "confidence": round(max(0.0, min(1.0, _float(best.get("score")))), 3),
        "mechanical_tags": tuple(best.get("mechanical_tags", ()) or ()),
        "visible_cue": best["visible_cue"],
        "scene_bias": round(max(0.0, min(0.24, _float(best.get("scene_bias")))), 3),
    }


def _texture_candidate(kind, label, reason, cue, score, *, rumor_kind="", rumor_label="", rumor_summary="", dialogue_bias="", light_profile="", tags=()):
    return {
        "kind": _slug(kind),
        "label": _text(label),
        "reason": _text(reason),
        "visible_cue": _text(cue),
        "score": _float(score),
        "rumor_kind": _slug(rumor_kind or kind),
        "rumor_label": _text(rumor_label or label),
        "rumor_summary": _text(rumor_summary or reason),
        "dialogue_bias": _slug(dialogue_bias or rumor_kind or kind),
        "light_profile": _slug(light_profile),
        "mechanical_tags": tuple(_slug(tag) for tag in tuple(tags or ()) if _text(tag)),
    }


def local_texture_snapshot(sim, prop, *, mood=None, scene=None, pulse=None):
    """Return a compact read for social weather / local texture.

    This is a presentation helper. It does not create a row by itself; callers
    attach the fields only to concrete scene/property anchors.
    """

    if not isinstance(prop, dict):
        return {}
    scene = scene if isinstance(scene, dict) else {}
    pulse = pulse if isinstance(pulse, dict) else {}
    mood = mood if isinstance(mood, dict) else place_mood_snapshot(sim, prop, scene=scene, pulse=pulse)
    mood_kind = _slug(mood.get("mood_kind") or mood.get("kind"))
    mood_label = _text(mood.get("mood_label") or mood.get("label")) or mood_kind
    phase = _slug(_scene_or_pulse_value("event_phase", scene=scene, pulse=pulse))
    category = _category_for(prop, pulse=pulse, scene=scene)
    prop_name = _prop_name(prop)
    tags = set(_slug(tag) for tag in tuple(mood.get("mechanical_tags", ()) or ()) if _text(tag))
    candidates = [
        _texture_candidate(
            "ordinary",
            "ordinary",
            f"{prop_name} is giving off a readable {mood_label} rhythm",
            _text(mood.get("visible_cue")) or "the place is doing ordinary local work",
            0.18,
            rumor_kind="talking",
            rumor_label="talking",
            rumor_summary="people here will probably talk if you give them a clean reason",
            dialogue_bias="open",
            light_profile="",
            tags=("social",),
        )
    ]

    if mood_kind in {"warm", "loyal", "softened", "tender"} or tags.intersection({"calm", "care"}):
        candidates.append(_texture_candidate(
            "welcoming",
            "warm",
            f"{prop_name} has enough trust in the air for softer conversation",
            _text(mood.get("visible_cue")) or "people are leaving room for each other",
            0.62 + (0.08 if mood_kind in {"loyal", "tender"} else 0.0),
            rumor_kind="generous",
            rumor_label="generous",
            rumor_summary="the local talk is a little more giving than guarded",
            dialogue_bias="soft",
            light_profile="storefront_warm" if category in {"retail", "hospitality", "residential"} else "clinic_soft",
            tags=("social", "calm"),
        ))
    if mood_kind == "kept" or tags.intersection({"maintenance", "care"}) and mood_kind in {"kept", "softened"}:
        candidates.append(_texture_candidate(
            "kept",
            "kept",
            f"{prop_name} reads cared-for because someone is actually touching the details",
            _text(mood.get("visible_cue")) or "the visible edge has been reset with small competent hands",
            0.68,
            rumor_kind="generous",
            rumor_label="generous",
            rumor_summary="people here seem more willing to give the place a chance",
            dialogue_bias="soft",
            light_profile="storefront_warm" if category not in {"secure", "industrial"} else "security_cool",
            tags=("maintenance", "care"),
        ))
    if mood_kind == "neglected":
        candidates.append(_texture_candidate(
            "neglected",
            "neglected",
            f"{prop_name} is showing upkeep debt through concrete visible cues",
            _text(mood.get("visible_cue")) or "the place has visible care work waiting on it",
            0.72,
            rumor_kind="tired",
            rumor_label="tired",
            rumor_summary="people here notice what has not been put right yet",
            dialogue_bias="weary",
            light_profile="street_warm",
            tags=("maintenance", "strained"),
        ))
    if mood_kind in {"strained", "brittle", "edged"} or "strained" in tags:
        candidates.append(_texture_candidate(
            "strained",
            "strained",
            f"{prop_name} is making people measure words before they spend them",
            _text(mood.get("visible_cue")) or "people are watching tone as much as motion",
            0.7,
            rumor_kind="spooked",
            rumor_label="spooked",
            rumor_summary="the block is talking, but it is not relaxed about it",
            dialogue_bias="guarded",
            light_profile="emergency_red" if mood_kind == "edged" else "security_cool",
            tags=("strained", "watched"),
        ))
    if mood_kind in {"watched", "dimmed"} or "watched" in tags:
        candidates.append(_texture_candidate(
            "watched",
            "watched",
            f"{prop_name} feels watched because the boundary is actually being watched",
            _text(mood.get("visible_cue")) or "eyes keep returning to the same edge",
            0.76,
            rumor_kind="watchful",
            rumor_label="watchful",
            rumor_summary="people here notice movement before they explain it",
            dialogue_bias="guarded",
            light_profile="security_cool",
            tags=("watched", "boundary"),
        ))
    if mood_kind in {"hurried", "short", "wanted"} or phase in {"delivery_run", "loading_push", "dispatch_surge", "boarding_crush", "arrival_handoff"}:
        candidates.append(_texture_candidate(
            "busy",
            "busy",
            f"{prop_name} is being pulled into route pressure",
            _text(mood.get("visible_cue")) or "the visible work has more motion than patience",
            0.64,
            rumor_kind="busy",
            rumor_label="busy",
            rumor_summary="the useful talk is mixed into work and handoffs",
            dialogue_bias="work",
            light_profile="headlight_white" if category == "transit" else "storefront_warm",
            tags=("work", "motion"),
        ))
    if mood_kind != "kept" and (mood_kind == "repairing" or "maintenance" in tags or phase in {"maintenance_loop", "repair_lookover"}):
        candidates.append(_texture_candidate(
            "mending",
            "mending",
            f"{prop_name} is being nudged back into shape by small practical work",
            _text(mood.get("visible_cue")) or "tools and careful hands are visible around the site",
            0.69,
            rumor_kind="busy",
            rumor_label="busy",
            rumor_summary="the useful talk is happening between repairs",
            dialogue_bias="work",
            light_profile="storefront_warm" if category not in {"secure", "industrial", "transit"} else "security_cool",
            tags=("maintenance", "work"),
        ))
    if mood_kind in {"neglected", "overstocked"} or phase in {"afterhours_aftermath", "aftermath_cleanup"}:
        candidates.append(_texture_candidate(
            "tired",
            "tired",
            f"{prop_name} is showing the cost of staying useful",
            _text(mood.get("visible_cue")) or "the place has not fully shaken off its last hard hour",
            0.61,
            rumor_kind="tired",
            rumor_label="tired",
            rumor_summary="people here still have enough energy to notice, not enough to perform",
            dialogue_bias="weary",
            light_profile="street_warm",
            tags=("maintenance", "social"),
        ))
    if phase in {"block_watch", "owner_screening", "visitor_screening", "booking_queue", "security_sweep"}:
        candidates.append(_texture_candidate(
            "shut_tight",
            "shut tight",
            f"{prop_name} is narrowing who gets an easy answer",
            "answers are moving through checks, glances, and small silences",
            0.79,
            rumor_kind="shut_tight",
            rumor_label="shut tight",
            rumor_summary="people here may know things, but the first answer will be small",
            dialogue_bias="closed",
            light_profile="security_cool",
            tags=("watched", "boundary"),
        ))
    if phase in {"regulars_spill", "neighbors_lingering", "tenant_meetup", "mutual_aid_table"}:
        candidates.append(_texture_candidate(
            "talking",
            "talking",
            f"{prop_name} has ordinary talk doing useful work",
            "people are lingering long enough for a second answer",
            0.72,
            rumor_kind="talking",
            rumor_label="talking",
            rumor_summary="the local version is easier to catch here than most places",
            dialogue_bias="open",
            light_profile="storefront_warm",
            tags=("social", "calm"),
        ))

    best = max(
        candidates,
        key=lambda row: (
            _float(row.get("score")),
            _slug(row.get("kind")),
            _text(row.get("reason")),
        ),
    )
    return {
        "texture_kind": best["kind"],
        "texture_label": best["label"],
        "texture_reason": best["reason"],
        "visible_cue": best["visible_cue"],
        "confidence": round(max(0.0, min(1.0, _float(best.get("score")))), 3),
        "mechanical_tags": tuple(best.get("mechanical_tags", ()) or ()),
        "light_profile_hint": best["light_profile"],
        "rumor_weather_kind": best["rumor_kind"],
        "rumor_weather_label": best["rumor_label"],
        "rumor_weather_summary": best["rumor_summary"],
        "rumor_weather_dialogue_bias": best["dialogue_bias"],
    }


def _ritual_candidate(kind, label, summary, action, fixture_name, fixture_type, glyph, color, score, *, actor_line="", detail_line="", log_text="", tags=(), bias=0.0):
    return {
        "kind": _slug(kind),
        "label": _text(label),
        "summary": _text(summary),
        "action": _text(action),
        "fixture_name": _text(fixture_name),
        "fixture_type": _slug(fixture_type),
        "fixture_glyph": (_text(glyph) or "r")[:1],
        "fixture_color": _text(color) or "property_service",
        "score": _float(score),
        "actor_line": _text(actor_line),
        "detail_line": _text(detail_line),
        "log_text": _text(log_text),
        "mechanical_tags": tuple(_slug(tag) for tag in tuple(tags or ()) if _text(tag)),
        "scene_bias": _float(bias),
    }


_RITUAL_VARIANTS = {
    "counter_wipe": (
        {
            "fixture_name": "Wiping Cloth",
            "actor_line": "I keep wiping this spot because people read a place by what it lets stay dirty.",
            "detail_line": "{place} is being kept presentable in small motions, not grand ones.",
        },
        {
            "fixture_name": "Damp Rag",
            "actor_line": "Same counter, same hands, different mess. That is most of the job.",
            "detail_line": "The wipe-down at {place} is less about polish than control.",
        },
        {
            "fixture_name": "Counter Cloth",
            "actor_line": "A clean edge makes people act like they know where to stand.",
            "detail_line": "{place} is using a small reset to keep the public side from fraying.",
        },
    ),
    "shelf_straightening": (
        {
            "fixture_name": "Straightened Shelf",
            "actor_line": "If the shelves look honest, people ask fewer questions.",
            "detail_line": "The shelf work at {place} says more about supply than the sign does.",
        },
        {
            "fixture_name": "Squared Shelf",
            "actor_line": "You can tell what people fear running out of by what they keep facing forward.",
            "detail_line": "{place} is turning supply pressure into neat rows.",
        },
        {
            "fixture_name": "Fronted Stock",
            "actor_line": "Somebody always notices the empty gap before they notice the full shelf.",
            "detail_line": "The little stock ritual at {place} is trying to make the room read steady.",
        },
    ),
    "guard_door_check": (
        {
            "fixture_name": "Door Check Mark",
            "actor_line": "Door looks boring until somebody makes it interesting.",
            "detail_line": "{place} has people checking the boundary before trouble gets a vote.",
            "log_text": "Someone checks the door line at {place}.",
        },
        {
            "fixture_name": "Threshold Mark",
            "actor_line": "I like a door that tells me the truth before I have to ask twice.",
            "detail_line": "The threshold at {place} is being watched as a habit, not a performance.",
            "log_text": "A threshold check tightens at {place}.",
        },
        {
            "fixture_name": "Door Ledger",
            "actor_line": "People think the list is the rule. The habit is the rule.",
            "detail_line": "{place} is tracking the edge where public becomes someone else's problem.",
            "log_text": "Someone marks the door routine at {place}.",
        },
    ),
    "manifest_check": (
        {
            "fixture_name": "Checked Manifest",
            "actor_line": "Manifest says what should happen. Street says what actually did.",
            "detail_line": "The list work at {place} is tying visible movement to a route or counter.",
            "log_text": "A manifest gets checked at {place}.",
        },
        {
            "fixture_name": "Route List",
            "actor_line": "Every route has one clean version and one version with weather on it.",
            "detail_line": "{place} is comparing paperwork to the motion outside.",
            "log_text": "Someone checks a route list at {place}.",
        },
        {
            "fixture_name": "Cargo Tally",
            "actor_line": "Count it before it leaves, count it when it lands, still miss the important part.",
            "detail_line": "The tally at {place} is giving the traffic a visible rhythm.",
            "log_text": "A cargo tally gets checked at {place}.",
        },
    ),
    "repair_lookover": (
        {
            "fixture_name": "Tool Check",
            "actor_line": "You learn the shape of trouble by checking the same loose bit twice.",
            "detail_line": "{place} has a maintenance read: small checks before a bigger failure.",
            "log_text": "Someone checks a loose bit of the frontage at {place}.",
        },
        {
            "fixture_name": "Service Tag",
            "actor_line": "If it rattles today, it complains tomorrow.",
            "detail_line": "{place} is being listened to like a machine with moods.",
            "log_text": "A service tag gets turned over at {place}.",
        },
        {
            "fixture_name": "Loose Screw",
            "actor_line": "Never trust the part that only behaves when people are watching.",
            "detail_line": "The repair habit at {place} is small enough to miss and useful enough to matter.",
            "log_text": "Someone fusses with a worn fitting at {place}.",
        },
    ),
    "smoke_break": (
        {
            "fixture_name": "Smoke Can",
            "actor_line": "Breaks tell you whether the room is kind or just profitable.",
            "detail_line": "The break outside {place} is small, but it is where the shift exhales.",
        },
        {
            "fixture_name": "Back-Step Cup",
            "actor_line": "You learn more from five quiet minutes out here than an hour under the lights.",
            "detail_line": "{place} has a little exhale point where staff and regulars trade the weather.",
        },
        {
            "fixture_name": "Ash Tin",
            "actor_line": "Nobody calls it a meeting if everybody looks tired enough.",
            "detail_line": "The pause at {place} is doing social work under a very small roof.",
        },
    ),
    "neighbor_linger": (
        {
            "fixture_name": "Shared Cup",
            "actor_line": "People say hallway like it is empty. It never is.",
            "detail_line": "{place} has the kind of lingering that teaches door habits.",
        },
        {
            "fixture_name": "Borrowed Chair",
            "actor_line": "You sit here long enough and the building starts telling on itself.",
            "detail_line": "The linger at {place} is not official, which is why it knows things.",
        },
        {
            "fixture_name": "Cooler Lid",
            "actor_line": "Everybody says they are just passing through. Nobody passes through this slowly.",
            "detail_line": "{place} is turning shared space into a soft checkpoint.",
        },
    ),
    "staff_meal": (
        {
            "fixture_name": "Staff Cup",
            "actor_line": "You eat where the shift lets you, not where you would pick.",
            "detail_line": "The staff bite at {place} says the work has not fully let go.",
        },
        {
            "fixture_name": "Half Wrap",
            "actor_line": "If I sit down proper, somebody will need me. That is the law of counters.",
            "detail_line": "{place} has staff catching food between obligations.",
        },
        {
            "fixture_name": "Break Plate",
            "actor_line": "Best meal is the one nobody calls you away from. So, not this one.",
            "detail_line": "The break plate at {place} makes the schedule visible.",
        },
    ),
    "shrine_vigil_pause": (
        {
            "fixture_name": "Quiet Offering",
            "actor_line": "Some things stay because somebody keeps returning to them.",
            "detail_line": "The pause at {place} is a memory ritual, not a performance.",
            "log_text": "Someone pauses by the offering at {place}.",
        },
        {
            "fixture_name": "Ribbon Note",
            "actor_line": "Names get quieter if nobody stops for them.",
            "detail_line": "{place} is holding a small public memory in the open.",
            "log_text": "Someone touches a small memorial note at {place}.",
        },
        {
            "fixture_name": "Candle Stub",
            "actor_line": "A little light does not fix anything. People still bring it.",
            "detail_line": "The vigil habit at {place} keeps grief from becoming just street furniture.",
            "log_text": "Someone checks a candle stub at {place}.",
        },
    ),
    "driver_walkaround": (
        {
            "fixture_name": "Route Chalk",
            "actor_line": "Wheels lie less if you walk around them first.",
            "detail_line": "The route habit at {place} is about leaving clean, not leaving fast.",
            "log_text": "Someone walks the route edge at {place}.",
        },
        {
            "fixture_name": "Tire Mark",
            "actor_line": "If the road gets a vote, I want to hear it before we move.",
            "detail_line": "{place} has a travel ritual built out of looking twice.",
            "log_text": "A route hand checks the tires at {place}.",
        },
        {
            "fixture_name": "Mirror Check",
            "actor_line": "Most mistakes are already visible before the engine starts.",
            "detail_line": "The walkaround at {place} makes departure feel deliberate.",
            "log_text": "Someone checks a mirror line at {place}.",
        },
    ),
    "plant_tending": (
        {
            "fixture_name": "Watered Planter",
            "actor_line": "Plants do not care what the block thinks. That helps.",
            "detail_line": "The plant care at {place} makes the place feel handled, not just used.",
            "log_text": "Someone tends a small plant at {place}.",
        },
        {
            "fixture_name": "Misted Leaves",
            "actor_line": "This one complains quietly. Better than people, some days.",
            "detail_line": "{place} has a little green care ritual at the edge.",
            "log_text": "Someone mists a plant at {place}.",
        },
        {
            "fixture_name": "Trimmed Stem",
            "actor_line": "You keep one living thing neat and the room remembers how.",
            "detail_line": "The plant habit at {place} softens the hard edge without asking permission.",
            "log_text": "Someone trims a small plant at {place}.",
        },
    ),
    "quiet_opening": (
        {
            "fixture_name": "Routine Mark",
            "actor_line": "A place falls apart when nobody does the small boring part.",
            "detail_line": "{place} is being held together by ordinary routine.",
        },
        {
            "fixture_name": "Turned Sign",
            "actor_line": "Open and closed are easy. Ready is the hard part.",
            "detail_line": "{place} is making itself legible one small habit at a time.",
        },
        {
            "fixture_name": "Swept Threshold",
            "actor_line": "Threshold gets the first lie and the first truth of the day.",
            "detail_line": "The quiet routine at {place} is how the room announces itself.",
        },
    ),
}


def _apply_ritual_variant(sim, prop, ritual, seed):
    ritual = dict(ritual or {})
    variants = _RITUAL_VARIANTS.get(_slug(ritual.get("kind")), ())
    if not variants:
        return ritual
    rng = random.Random(f"{seed}:variant")
    variant = dict(variants[int(rng.random() * len(variants)) % len(variants)])
    place = _prop_name(prop)
    for key, value in variant.items():
        text = _text(value)
        if not text:
            continue
        ritual[key] = text.format(place=place)
    return ritual


def ambient_ritual_snapshot(sim, prop, *, mood=None, scene=None, pulse=None):
    """Return one small visible habit that can ride an existing scene."""

    if not isinstance(prop, dict):
        return {}
    scene = scene if isinstance(scene, dict) else {}
    pulse = pulse if isinstance(pulse, dict) else {}
    mood = mood if isinstance(mood, dict) else place_mood_snapshot(sim, prop, scene=scene, pulse=pulse)
    mood_kind = _slug(mood.get("mood_kind") or mood.get("kind"))
    category = _category_for(prop, pulse=pulse, scene=scene)
    phase = _slug(_scene_or_pulse_value("event_phase", scene=scene, pulse=pulse))
    prop_name = _prop_name(prop)
    culture = culture_profile_for_property(sim, prop)

    candidates = []
    if category in {"retail", "hospitality", "finance", "office"} or phase in {"opening", "reset_scramble", "table_turnover"}:
        candidates.append(_ritual_candidate(
            "counter_wipe",
            "counter wipe",
            "someone is wiping the public edge down and resetting the little things",
            "watch the reset or ask what keeps getting touched",
            "Wiping Cloth",
            "ritual_counter_wipe",
            "w",
            "floor_clean",
            0.42 + (0.18 if mood_kind in {"warm", "steady", "loyal"} else 0.0),
            actor_line=f"I keep wiping this spot because people read a place by what it lets stay dirty.",
            detail_line=f"{prop_name} is being kept presentable in small motions, not grand ones.",
            tags=("calm", "service"),
            bias=0.04,
        ))
    if category == "retail" or phase in {"help_wanted_board", "grumbling_front"}:
        candidates.append(_ritual_candidate(
            "shelf_straightening",
            "shelf straightening",
            "stock is being squared up where customers can see the care or the strain",
            "read the shelf habit or ask what keeps moving",
            "Straightened Shelf",
            "ritual_shelf_straighten",
            "s",
            "item_tool",
            0.47 + (0.17 if mood_kind in {"wanted", "overstocked", "neglected"} else 0.0),
            actor_line="If the shelves look honest, people ask fewer questions.",
            detail_line=f"The shelf work at {prop_name} says more about supply than the sign does.",
            tags=("stock", "service"),
            bias=0.06,
        ))
    if category in {"secure", "industrial"} or phase in {"owner_screening", "block_watch", "visitor_screening", "booking_queue"} or mood_kind == "watched":
        candidates.append(_ritual_candidate(
            "guard_door_check",
            "door check",
            "the threshold is being checked by habit, not just by policy",
            "watch the check or respect the boundary",
            "Door Check Mark",
            "ritual_door_check",
            "d",
            "hazard_warning",
            0.55 + (0.24 if mood_kind == "watched" else 0.0),
            actor_line="Door looks boring until somebody makes it interesting.",
            detail_line=f"{prop_name} has people checking the boundary before trouble gets a vote.",
            log_text=f"Someone checks the door line at {prop_name}.",
            tags=("watched", "boundary"),
            bias=0.09,
        ))
    if category in {"industrial", "transit"} or phase in {"manifest_check", "loading_push", "dispatch_surge", "delivery_run", "boarding_crush", "arrival_handoff"}:
        candidates.append(_ritual_candidate(
            "manifest_check",
            "manifest check",
            "a list is being checked twice against the physical motion around it",
            "inspect the list rhythm or ask what is late",
            "Checked Manifest",
            "ritual_manifest_check",
            "m",
            "property_service",
            0.52 + (0.16 if mood_kind in {"hurried", "short"} else 0.0),
            actor_line="Manifest says what should happen. Street says what actually did.",
            detail_line=f"The list work at {prop_name} is tying visible movement to a route or counter.",
            log_text=f"A manifest gets checked at {prop_name}.",
            tags=("work", "motion"),
            bias=0.07,
        ))
    if category in {"industrial", "secure", "medical"} or phase in {"maintenance_loop", "aftermath_cleanup", "fire_response"} or mood_kind in {"repairing", "dimmed"}:
        candidates.append(_ritual_candidate(
            "repair_lookover",
            "repair lookover",
            "somebody is checking what still holds and what is about to fail",
            "read the tool marks or ask what broke first",
            "Tool Check",
            "ritual_repair_lookover",
            "t",
            "item_tool",
            0.52 + (0.21 if mood_kind in {"repairing", "dimmed"} else 0.0),
            actor_line="You learn the shape of trouble by checking the same loose bit twice.",
            detail_line=f"{prop_name} has a maintenance read: small checks before a bigger failure.",
            log_text=f"Someone checks a loose bit of the frontage at {prop_name}.",
            tags=("maintenance",),
            bias=0.08,
        ))
    if category in {"hospitality", "entertainment"} or phase in {"late_buzz", "barback_reset", "last_call_spill"}:
        candidates.append(_ritual_candidate(
            "smoke_break",
            "smoke break",
            "a short break has turned into a tiny public weather report",
            "listen from the edge or ask what the shift burned through",
            "Smoke Can",
            "ritual_smoke_break",
            "a",
            "floor_grit",
            0.45 + (0.14 if phase in {"late_buzz", "last_call_spill"} else 0.0),
            actor_line="Breaks tell you whether the room is kind or just profitable.",
            detail_line=f"The break outside {prop_name} is small, but it is where the shift exhales.",
            tags=("social",),
            bias=0.04,
        ))
    if category == "residential" or phase in {"neighbors_lingering", "tenant_meetup", "mutual_aid_table"}:
        candidates.append(_ritual_candidate(
            "neighbor_linger",
            "neighbor linger",
            "neighbors are keeping a shared edge warm without calling it a meeting",
            "listen for building habits or ask what everyone knows",
            "Shared Cup",
            "ritual_neighbor_linger",
            "c",
            "property_home",
            0.5 + (0.18 if mood_kind in {"warm", "softened"} else 0.0),
            actor_line="People say hallway like it is empty. It never is.",
            detail_line=f"{prop_name} has the kind of lingering that teaches door habits.",
            tags=("social", "calm"),
            bias=0.06,
        ))
    if category in {"hospitality", "retail"} or phase in {"shift_handoff", "owner_closed_turnover"}:
        candidates.append(_ritual_candidate(
            "staff_meal",
            "staff bite",
            "staff are taking a fast bite where the schedule can still reach them",
            "ask about the shift or watch who gets called back first",
            "Staff Cup",
            "ritual_staff_meal",
            "u",
            "item_food",
            0.36 + (0.14 if mood_kind in {"hurried", "neglected"} else 0.0),
            actor_line="You eat where the shift lets you, not where you would pick.",
            detail_line=f"The staff bite at {prop_name} says the work has not fully let go.",
            tags=("work", "social"),
            bias=0.04,
        ))
    if phase in {"candle_vigil", "afterhours_aftermath", "taped_off_front"} or mood_kind == "tender":
        candidates.append(_ritual_candidate(
            "shrine_vigil_pause",
            "vigil pause",
            "someone is pausing at a small public memory before moving on",
            "listen softly or leave the offering alone",
            "Quiet Offering",
            "ritual_vigil_pause",
            "*",
            "flora_flower_white",
            0.66 + (0.16 if mood_kind == "tender" else 0.0),
            actor_line="Some things stay because somebody keeps returning to them.",
            detail_line=f"The pause at {prop_name} is a memory ritual, not a performance.",
            log_text=f"Someone pauses by the offering at {prop_name}.",
            tags=("care", "social"),
            bias=0.05,
        ))
    if phase in {"delivery_run", "dispatch_surge", "boarding_crush", "arrival_handoff"} or category == "transit":
        candidates.append(_ritual_candidate(
            "driver_walkaround",
            "driver walkaround",
            "a driver or route hand is checking the vehicle edge before motion resumes",
            "watch the route habit or ask what gets missed",
            "Route Chalk",
            "ritual_driver_walkaround",
            "r",
            "vehicle_light",
            0.5 + (0.16 if mood_kind == "hurried" else 0.0),
            actor_line="Wheels lie less if you walk around them first.",
            detail_line=f"The route habit at {prop_name} is about leaving clean, not leaving fast.",
            log_text=f"Someone walks the route edge at {prop_name}.",
            tags=("motion", "work"),
            bias=0.07,
        ))
    if category in {"medical", "residential", "retail"} and (_nearby_flora_count(sim, prop) or _prop_archetype(prop) in {"herbalist_shop", "herbalist_camp", "salon", "florist"}):
        candidates.append(_ritual_candidate(
            "plant_tending",
            "plant tending",
            "a plant is being fussed over at the edge of the work",
            "look at the care habit or ask who keeps it alive",
            "Watered Planter",
            "ritual_plant_tending",
            "'",
            "flora_flower_pink",
            0.5 + (0.19 if mood_kind in {"softened", "tender", "warm"} else 0.0),
            actor_line="Plants do not care what the block thinks. That helps.",
            detail_line=f"The plant care at {prop_name} makes the place feel handled, not just used.",
            log_text=f"Someone tends a small plant at {prop_name}.",
            tags=("care", "calm"),
            bias=0.05,
        ))
    ancestral_word = _text(culture.get("ancestral_word")).capitalize()
    if ancestral_word:
        ritual_mode = _slug(culture.get("ritual_mode")) or "heelbeat"
        culture_hour = _scene_or_pulse_value("hour", scene=scene, pulse=pulse, default="")
        culture_rng = random.Random(
            f"{getattr(sim, 'seed', 0)}:ancestral-ritual:{_prop_id(prop)}:{culture_hour}:{phase}"
        )
        culture_score = 0.64 if culture_rng.random() < 0.3 else 0.18
        ritual_shapes = {
            "heelbeat": (
                "heelbeat call",
                "a familiar call lands with two practiced heel strikes",
                "watch the answering step or leave the rhythm room",
                "Scuffed Heel Marks",
            ),
            "turnstep": (
                "turnstep call",
                "a familiar call cuts through a quick half-turn and planted step",
                "watch the turn settle or give it room",
                "Turnworn Floor",
            ),
            "handbeat": (
                "handbeat call",
                "a familiar call lands inside a short palm rhythm",
                "listen for the answering beat or let it pass",
                "Handbeat Rail",
            ),
            "shoulder_sway": (
                "sway call",
                "a familiar call pulls a small shoulder-sway through the room",
                "watch the sway answer or keep moving",
                "Swayworn Edge",
            ),
            "stomp_circle": (
                "stomp call",
                "a familiar call is answered by a hard step at the circle's edge",
                "watch the circle answer or stay beyond it",
                "Stompworn Ring",
            ),
            "cross_step": (
                "cross-step call",
                "a familiar call folds into a quick crossing step",
                "watch the crossing step or leave a clear edge",
                "Crossed Step Marks",
            ),
            "palm_rhythm": (
                "palm-call rhythm",
                "a familiar call rides a muted rhythm against the nearest hard edge",
                "listen for the return or let the rhythm pass",
                "Rhythm-Worn Rail",
            ),
            "half_turn": (
                "half-turn call",
                "a familiar call is punctuated by a half-turn and a planted foot",
                "watch the turn answer or give it room",
                "Half-Turn Scuff",
            ),
        }
        ritual_label, ritual_summary, ritual_action, fixture_name = ritual_shapes.get(
            ritual_mode,
            ritual_shapes["heelbeat"],
        )
        candidates.append(_ritual_candidate(
            "ancestral_step",
            ritual_label,
            f"{ancestral_word} rings out; {ritual_summary}",
            ritual_action,
            fixture_name,
            "ritual_ancestral_step",
            "~",
            "ritual_violet",
            culture_score + (0.06 if mood_kind in {"warm", "loyal", "softened"} else 0.0),
            actor_line=f"{ancestral_word}! The old beat still fits.",
            detail_line=f"At {prop_name}, the call and answering step fit together like an old habit.",
            log_text=f"Someone calls {ancestral_word} and marks a practiced step at {prop_name}.",
            tags=("culture", "social"),
            bias=0.05,
        ))

    if not candidates:
        candidates.append(_ritual_candidate(
            "quiet_opening",
            "quiet routine",
            "a small opening-and-closing habit is keeping the place legible",
            "watch the routine or ask who usually handles it",
            "Routine Mark",
            "ritual_quiet_routine",
            ".",
            "property_service",
            0.25,
            actor_line="A place falls apart when nobody does the small boring part.",
            detail_line=f"{prop_name} is being held together by ordinary routine.",
            tags=("calm", "work"),
            bias=0.02,
        ))

    seed = (
        f"{getattr(sim, 'seed', 0)}:ambient-ritual:{_prop_id(prop)}:"
        f"{phase}:{mood_kind}:{_scene_or_pulse_value('hour', scene=scene, pulse=pulse, default='')}"
    )
    rng = random.Random(seed)
    jittered = []
    for candidate in candidates:
        jittered.append((candidate["score"] + rng.random() * 0.035, candidate))
    best = max(jittered, key=lambda row: (row[0], row[1]["kind"]))[1]
    best = _apply_ritual_variant(sim, prop, best, seed)
    log_text = best["log_text"]
    if log_text:
        log_rng = random.Random(f"{seed}:log:{best['kind']}")
        if log_rng.random() > 0.38:
            log_text = ""
    return {
        "ritual_kind": best["kind"],
        "ritual_label": best["label"],
        "summary": best["summary"],
        "action": best["action"],
        "fixture_name": best["fixture_name"],
        "fixture_type": best["fixture_type"],
        "fixture_glyph": best["fixture_glyph"],
        "fixture_color": best["fixture_color"],
        "actor_line": best["actor_line"],
        "detail_line": best["detail_line"],
        "log_text": log_text,
        "mechanical_tags": tuple(best.get("mechanical_tags", ()) or ()),
        "scene_bias": round(max(0.0, min(0.14, _float(best.get("scene_bias")))), 3),
    }


def place_mood_scene_fields(mood):
    mood = mood if isinstance(mood, dict) else {}
    if not mood:
        return {}
    tags = tuple(_slug(tag) for tag in tuple(mood.get("mechanical_tags", ()) or ()) if _text(tag))
    return {
        "place_mood_kind": _slug(mood.get("mood_kind") or mood.get("kind")),
        "place_mood_label": _text(mood.get("mood_label") or mood.get("label")),
        "place_mood_reason": _text(mood.get("mood_reason") or mood.get("reason")),
        "place_mood_confidence": round(max(0.0, min(1.0, _float(mood.get("confidence")))), 3),
        "place_mood_visible_cue": _text(mood.get("visible_cue")),
        "place_mood_mechanical_tags": tuple(tags),
        "place_mood_scene_bias": round(max(0.0, min(0.24, _float(mood.get("scene_bias")))), 3),
    }


def ambient_ritual_scene_fields(ritual):
    ritual = ritual if isinstance(ritual, dict) else {}
    if not ritual:
        return {}
    tags = tuple(_slug(tag) for tag in tuple(ritual.get("mechanical_tags", ()) or ()) if _text(tag))
    return {
        "ambient_ritual_kind": _slug(ritual.get("ritual_kind") or ritual.get("kind")),
        "ambient_ritual_label": _text(ritual.get("ritual_label") or ritual.get("label")),
        "ambient_ritual_summary": _text(ritual.get("summary")),
        "ambient_ritual_action": _text(ritual.get("action")),
        "ambient_ritual_fixture_name": _text(ritual.get("fixture_name")),
        "ambient_ritual_fixture_type": _slug(ritual.get("fixture_type")),
        "ambient_ritual_fixture_glyph": (_text(ritual.get("fixture_glyph")) or "r")[:1],
        "ambient_ritual_fixture_color": _text(ritual.get("fixture_color")),
        "ambient_ritual_actor_line": _text(ritual.get("actor_line")),
        "ambient_ritual_detail_line": _text(ritual.get("detail_line")),
        "ambient_ritual_log_text": _text(ritual.get("log_text")),
        "ambient_ritual_mechanical_tags": tuple(tags),
        "ambient_ritual_scene_bias": round(max(0.0, min(0.14, _float(ritual.get("scene_bias")))), 3),
    }


def place_texture_scene_fields(texture):
    texture = texture if isinstance(texture, dict) else {}
    if not texture:
        return {}
    tags = tuple(_slug(tag) for tag in tuple(texture.get("mechanical_tags", ()) or ()) if _text(tag))
    return {
        "place_texture_kind": _slug(texture.get("texture_kind") or texture.get("kind")),
        "place_texture_label": _text(texture.get("texture_label") or texture.get("label")),
        "place_texture_reason": _text(texture.get("texture_reason") or texture.get("reason")),
        "place_texture_visible_cue": _text(texture.get("visible_cue")),
        "place_texture_confidence": round(max(0.0, min(1.0, _float(texture.get("confidence")))), 3),
        "place_texture_mechanical_tags": tuple(tags),
        "place_texture_light_profile_hint": _slug(texture.get("light_profile_hint")),
        "rumor_weather_kind": _slug(texture.get("rumor_weather_kind")),
        "rumor_weather_label": _text(texture.get("rumor_weather_label")),
        "rumor_weather_summary": _text(texture.get("rumor_weather_summary")),
        "rumor_weather_dialogue_bias": _slug(texture.get("rumor_weather_dialogue_bias")),
    }


def strongest_rumor_weather_anchor(
    sim,
    *,
    actor_eid=None,
    viewer_eid=None,
    x=None,
    y=None,
    z=None,
    radius=12,
    current_chunk_only=True,
):
    """Return the strongest concrete current-chunk rumor-weather anchor.

    This helper is intentionally a consumer read over active scene/property
    facts. It never creates social weather on its own.
    """

    if sim is None:
        return {}
    origin = _position_tuple(sim, actor_eid=actor_eid, x=x, y=y, z=z)
    if origin is None and viewer_eid is not None:
        origin = _position_tuple(sim, actor_eid=viewer_eid)
    if origin is None:
        return {}
    origin_chunk = _chunk_for(sim, origin)
    try:
        radius_value = max(0, int(radius))
    except (TypeError, ValueError):
        radius_value = 12

    best = None
    best_score = float("-inf")
    for raw_scene_id, scene in _active_business_scene_store(sim).items():
        if not _scene_live(scene):
            continue
        property_id = _text(scene.get("property_id"))
        if not property_id:
            continue
        prop = getattr(sim, "properties", {}).get(property_id)
        if not isinstance(prop, dict):
            continue
        anchor = _scene_anchor(scene, prop)
        if anchor is None:
            continue
        if int(anchor[2]) != int(origin[2]):
            continue
        if current_chunk_only and origin_chunk is not None and _chunk_for(sim, anchor) != origin_chunk:
            continue
        distance = abs(int(anchor[0]) - int(origin[0])) + abs(int(anchor[1]) - int(origin[1]))
        if radius_value and distance > radius_value:
            continue

        fields = public_place_mood_fields(scene)
        if not fields.get("rumor_weather_kind"):
            fields.update(annotate_place_mood_and_ritual(sim, prop, scene=scene))
        kind = _slug(fields.get("rumor_weather_kind"))
        if kind not in RUMOR_WEATHER_KINDS:
            continue
        confidence = _float(fields.get("place_texture_confidence"), 0.48)
        cue = (
            _text(fields.get("place_texture_visible_cue"))
            or _text(fields.get("place_mood_visible_cue"))
            or _text(fields.get("rumor_weather_summary"))
        )
        score = (
            confidence
            + max(0.0, 0.24 - (float(distance) * 0.018))
            + (0.04 if _text(scene.get("ambient_ritual_kind")) else 0.0)
        )
        scene_id = _text(scene.get("scene_id")) or _text(raw_scene_id)
        row = {
            "rumor_weather_kind": kind,
            "rumor_weather_label": _text(fields.get("rumor_weather_label")) or kind.replace("_", " "),
            "rumor_weather_summary": _text(fields.get("rumor_weather_summary")),
            "dialogue_bias": _slug(fields.get("rumor_weather_dialogue_bias")) or kind,
            "visible_cue": cue,
            "place_texture_kind": _slug(fields.get("place_texture_kind")),
            "place_texture_label": _text(fields.get("place_texture_label")),
            "property_id": property_id,
            "property_name": _prop_name(prop),
            "scene_id": scene_id,
            "source_kind": _slug(scene.get("source_kind")) or "business_scene",
            "event_phase": _slug(scene.get("event_phase")),
            "anchor": (int(anchor[0]), int(anchor[1]), int(anchor[2])),
            "distance": int(distance),
            "confidence": round(max(0.0, min(1.0, confidence)), 3),
        }
        if best is None or score > best_score:
            best = row
            best_score = score
    return best or {}


def annotate_place_mood_and_ritual(sim, prop, *, scene=None, pulse=None):
    """Return scene/pulse fields for the current derived mood and ritual."""

    mood = place_mood_snapshot(sim, prop, scene=scene, pulse=pulse)
    texture = local_texture_snapshot(sim, prop, mood=mood, scene=scene, pulse=pulse)
    ritual = ambient_ritual_snapshot(sim, prop, mood=mood, scene=scene, pulse=pulse)
    fields = {}
    fields.update(place_mood_scene_fields(mood))
    fields.update(place_texture_scene_fields(texture))
    fields.update(ambient_ritual_scene_fields(ritual))
    return fields


def public_place_mood_fields(source):
    """Return serializable mood/ritual fields copied from a pulse or scene."""

    if not isinstance(source, dict):
        return {}
    fields = {}
    for key in PLACE_MOOD_FIELD_KEYS + PLACE_TEXTURE_FIELD_KEYS + AMBIENT_RITUAL_FIELD_KEYS:
        value = source.get(key)
        if value in (None, "", (), []):
            continue
        fields[key] = value
    return fields
