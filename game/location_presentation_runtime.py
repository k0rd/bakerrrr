"""Shared property and location presentation helpers extracted from ``game.systems``."""

from __future__ import annotations

import curses

from engine.buildings import building_exterior_profile
from game.appearance import (
    creature_color_key as _appearance_creature_color_key,
    feature_tile_style as _appearance_feature_tile_style,
    ground_item_color as _appearance_ground_item_color,
    item_display_glyph as _appearance_item_display_glyph,
    property_render_snapshot as _appearance_property_render_snapshot,
)
from game.components import PropertyKnowledge
from game.dialogue_runtime import (
    _contact_benefit_labels,
    _dialogue_credential_mode_text,
    _dialogue_hours_text,
    _dialogue_human_join,
    _dialogue_security_tier_text,
    _infrastructure_target_property,
    _property_access_summary,
    _property_contact_entry,
)
from game.economy import item_market_bias, store_supply_profile
from game.items import ITEM_CATALOG, item_display_name
from game.meaningful_objects_runtime import meaningful_object_display_text
from game.object_profile_runtime import object_profile_display_text, property_is_item_backed_fixture
from game.opportunities import opportunity_intel_for_observer, tracked_target_surface_snapshot
from game.organization_presence import format_property_org_presence, format_visible_property_org_presence
from game.organizations import organization_name, property_organization_eid
from game.system_support.crime_plan_runtime import crime_plan_surface_rows
from game.population import (
    INDUSTRIAL_ARCHETYPES,
    MEDICAL_ARCHETYPES,
    NIGHTLIFE_ARCHETYPES,
    RESIDENTIAL_ARCHETYPES,
    SALVAGE_ARCHETYPES,
    SECURITY_ARCHETYPES,
    STOREFRONT_ARCHETYPES,
    TRANSIT_ARCHETYPES,
)
from game.property_access import (
    evaluate_property_access as _evaluate_property_access,
    property_access_controller as _property_access_controller,
    property_access_level as _property_access_level,
    property_apertures as _property_apertures,
)
from game.property_keys import property_lock_state
from game.property_runtime import (
    building_id_from_property as _building_id_from_property,
    building_id_from_structure as _building_id_from_structure,
    controller_access_requirement_text as _controller_access_requirement_text,
    controller_credential_short_label as _controller_credential_short_label,
    finance_services_for_property as _finance_services_for_property,
    property_covering as _property_covering,
    property_infrastructure_role as _property_infrastructure_role,
    property_is_public as _property_is_public,
    property_is_storefront as _property_is_storefront,
    property_metadata as _property_metadata,
    property_services as _property_services,
    property_signage as _property_signage,
    property_status_text as _property_status_text,
    site_services_for_property as _site_services_for_property,
    viewer_property_credential_status as _viewer_property_credential_status,
    viewer_revealed_building_id as _viewer_revealed_building_id,
)
from game.quick_travel_ramps import is_quick_travel_ramp_property
from game.report_runtime import (
    build_known_locations_report as _report_runtime_build_known_locations_report,
    build_known_people_report as _report_runtime_build_known_people_report,
)
from game.semantic_catalog import get_runtime_semantic_catalog
from game.service_runtime import _int_or_default, _storefront_service_profile
from game.skills import access_prep_skill_terms as _access_prep_skill_terms
from game.system_support.entity_naming import _entity_display_name
from game.system_support.interaction_ordering import _manhattan
from game.trade_system import TradeSystem
from game.ui_text_runtime import _legend_line
from game.status_ui_runtime import _floor_label


FINANCE_ARCHETYPES = {
    "bank",
    "brokerage",
    "pawn_shop",
}
ENTERTAINMENT_ARCHETYPES = NIGHTLIFE_ARCHETYPES | {
    "casino",
    "gallery",
}
HOSPITALITY_ARCHETYPES = {
    "bar",
    "flophouse",
    "hotel",
    "restaurant",
    "soup_kitchen",
    "street_kitchen",
    "tavern",
}
OFFICE_ARCHETYPES = {
    "co_working_hub",
    "media_lab",
    "office",
    "tower",
}
TRANSIT_BUILDING_ARCHETYPES = TRANSIT_ARCHETYPES | {
    "metro_exchange",
}

BUILDING_STREET_LABELS = {
    "arcade": "arcade frontage",
    "auto_garage": "garage frontage",
    "backroom_clinic": "clinic frontage",
    "bank": "bank branch",
    "bar": "bar frontage",
    "casino": "casino frontage",
    "checkpoint": "checkpoint",
    "corner_store": "corner storefront",
    "courthouse": "civic building",
    "jail": "city jail",
    "prison": "prison complex",
    "daycare": "daycare building",
    "gaming_hall": "gaming hall",
    "hotel": "hotel frontage",
    "junk_market": "market frontage",
    "laundromat": "laundromat",
    "metro_exchange": "exchange building",
    "music_venue": "music venue",
    "nightclub": "nightclub frontage",
    "office": "office building",
    "outfitter": "outfitter frontage",
    "pawn_shop": "pawn shop frontage",
    "pharmacy": "pharmacy frontage",
    "pump_house": "pump house",
    "relay_post": "relay post",
    "restaurant": "restaurant frontage",
    "roadhouse": "roadhouse",
    "ruin_shelter": "ruin shelter",
    "ranger_hut": "ranger hut",
    "salvage_camp": "salvage camp",
    "service_station": "service station",
    "server_hub": "utility block",
    "surplus_store": "surplus storefront",
    "survey_post": "survey post",
    "soup_kitchen": "soup kitchen",
    "tavern": "tavern frontage",
    "theater": "theater frontage",
    "thrift_store": "thrift storefront",
    "tide_station": "tide station",
    "tower": "tower block",
    "warehouse": "warehouse",
    "work_shed": "work shed",
    "field_camp": "field camp",
    "lookout_post": "lookout post",
    "dock_shack": "dock shack",
    "ferry_post": "ferry post",
    "net_house": "net house",
    "beacon_house": "beacon house",
}

STAKEOUT_RADIUS = 3
STAKEOUT_REVEAL_INTERVAL = 8
STAKEOUT_MAX_REVEALS = 4
STAKEOUT_CONFIDENCE_CAP = 0.88


def _legacy_building_pulse_snapshot(sim, prop=None, structure=None, *, respect_chunk_cap=True):
    from game import systems as facade

    return facade._building_pulse_snapshot(
        sim,
        prop=prop,
        structure=structure,
        respect_chunk_cap=respect_chunk_cap,
    )


def _building_exterior_profile_for(info):
    if not isinstance(info, dict):
        return {}
    return building_exterior_profile(info)


def _tile_render_style(sim, tile, x, y, z=0, revealed_building_id=""):
    appearance = sim.appearance.tile(
        tile,
        x,
        y,
        z=z,
        revealed_building_id=revealed_building_id,
    )
    return appearance.glyph, appearance.color


def _item_display_glyph(item_def):
    return _appearance_item_display_glyph(item_def)


def _ground_item_color(item_def):
    return _appearance_ground_item_color(item_def)


def _item_reference_semantic_id(item_def):
    catalog = get_runtime_semantic_catalog()
    color_key = _ground_item_color(item_def)
    semantic_key = str(color_key or "").strip()
    semantics = getattr(catalog, "semantics", {})
    if semantic_key and isinstance(semantics, dict) and semantic_key in semantics:
        return semantic_key
    glyph = _item_display_glyph(item_def)
    return catalog.semantic_id_for(glyph, color_key, preferred_categories=("items",))


def _location_building_category(archetype, *, storefront=False):
    archetype = str(archetype or "").strip().lower()
    if archetype in FINANCE_ARCHETYPES:
        return "finance"
    if archetype in MEDICAL_ARCHETYPES:
        return "medical"
    if archetype in SECURITY_ARCHETYPES:
        return "secure"
    if archetype in INDUSTRIAL_ARCHETYPES or archetype in SALVAGE_ARCHETYPES:
        return "industrial"
    if archetype in ENTERTAINMENT_ARCHETYPES:
        return "entertainment"
    if archetype in HOSPITALITY_ARCHETYPES:
        return "hospitality"
    if archetype in RESIDENTIAL_ARCHETYPES or archetype in {"barracks", "hotel"}:
        return "residential"
    if archetype in TRANSIT_BUILDING_ARCHETYPES:
        return "transit"
    if archetype in OFFICE_ARCHETYPES:
        return "office"
    if storefront or archetype in STOREFRONT_ARCHETYPES:
        return "retail"
    return "general"


def _infrastructure_role_label(role):
    role_key = str(role or "").strip().lower()
    return {
        "access_panel": "access panel",
        "bones_stash": "stash",
        "run_echo_notice": "notice",
        "run_echo_stash": "stash",
        "security_post": "security post",
        "service_terminal": "service terminal",
    }.get(role_key, role_key.replace("_", " "))


def _property_interaction_modes(sim, prop, viewer_eid=None):
    if not isinstance(prop, dict):
        return ()

    access = _evaluate_property_access(sim, viewer_eid, prop)
    modes = []
    infrastructure_role = _property_infrastructure_role(prop)
    if property_is_item_backed_fixture(prop):
        metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
        if bool(metadata.get("pickup_allowed", True)):
            modes.append("pickup")
    if infrastructure_role == "access_panel":
        modes.append("panel")
    elif infrastructure_role == "security_post":
        modes.append("security")

    if _property_is_storefront(prop) and access.can_use_services:
        service = _storefront_service_profile(sim, prop)
        if service.get("available"):
            modes.append("trade")

    services = set(_finance_services_for_property(prop))
    if "banking" in services and access.can_use_services:
        modes.append("banking")
    if "insurance" in services and access.can_use_services:
        modes.append("insurance")
    for site_service in _site_services_for_property(prop):
        if access.can_use_services:
            modes.append(site_service)

    if viewer_eid is not None:
        owner_eid = prop.get("owner_eid")
        if owner_eid == viewer_eid or _property_is_public(prop) or access.standing >= 0.45:
            modes.append("inspect")

    return tuple(modes)


def _access_prep_detail_lines(sim, viewer_eid, prop, *, controller=None, reveal_tier=None):
    if not isinstance(prop, dict) or str(prop.get("kind", "")).strip().lower() != "building":
        return ()

    if controller is None:
        controller = _property_access_controller(sim, prop)
    if not isinstance(controller, dict):
        return ()

    if reveal_tier is None:
        terms = _access_prep_skill_terms(sim, viewer_eid)
        reveal_tier = _int_or_default(terms.get("reveal_tier"), 0)
    reveal_tier = max(0, int(reveal_tier))
    if reveal_tier <= 0:
        return ()

    lines = []
    detail_bits = []
    controller_kind = str(controller.get("kind", "") or "").strip().lower()
    if controller_kind and controller_kind != "none":
        detail_bits.append("ctrl:" + controller_kind.replace("_", " "))
    mode_text = _dialogue_credential_mode_text(controller.get("credential_mode"))
    if mode_text:
        detail_bits.append("mode:" + mode_text)
    hours_text = _dialogue_hours_text(controller.get("opening_window"))
    if hours_text:
        detail_bits.append("hours:" + hours_text)
    requirement = _controller_access_requirement_text(controller)
    if requirement:
        detail_bits.append("req:" + requirement)
    if detail_bits:
        lines.append("Prep detail: " + "  ".join(detail_bits))

    if reveal_tier < 2:
        return tuple(lines)

    metadata = _property_metadata(prop)
    followup_bits = []
    panel_id = str(metadata.get("access_panel_property_id", "") or "").strip()
    if panel_id and sim.properties.get(panel_id):
        followup_bits.append("panel:street")
    terminal_id = str(metadata.get("service_terminal_property_id", "") or "").strip()
    if terminal_id:
        terminal = sim.properties.get(terminal_id)
        if isinstance(terminal, dict):
            terminal_services = [
                str(service).strip().lower()
                for service in list(_property_services(terminal) or ())
                if str(service).strip()
            ]
            if terminal_services:
                followup_bits.append("terminal:" + ",".join(terminal_services[:3]))
            else:
                followup_bits.append("terminal:street")

    alternate_labels = []
    ordinary_count = 0
    for aperture in _property_apertures(prop):
        kind = str(aperture.get("kind", "") or "").strip().lower()
        ordinary = bool(aperture.get("ordinary"))
        if ordinary:
            ordinary_count += 1
            continue
        label = kind.replace("_", " ").strip()
        if label and label not in alternate_labels:
            alternate_labels.append(label)
    if alternate_labels:
        followup_bits.append("alternates:" + _dialogue_human_join(alternate_labels[:3]))
    elif ordinary_count > 0:
        if ordinary_count == 1:
            followup_bits.append("entry:ordinary door")
        else:
            followup_bits.append(f"entry:{ordinary_count} ordinary doors")

    if followup_bits:
        lines.append("Prep detail: " + "  ".join(followup_bits))
    return tuple(lines)


def _property_contact_hint(sim, viewer_eid, prop):
    entry = _property_contact_entry(sim, viewer_eid, prop)
    if not entry:
        return ""

    source_eid = entry.get("source_eid")
    source_name = _entity_display_name(sim, source_eid, title_case=True) if source_eid is not None else ""
    standing = float(entry.get("standing", 0.0))
    benefits = entry.get("benefits", ())
    labels = _contact_benefit_labels(benefits)

    if labels == ["local name"]:
        if source_name:
            lead = f"contact:{source_name} knows people here"
        else:
            lead = "contact:someone knows people here"
    elif source_name:
        lead = f"contact:{source_name} can vouch here"
    else:
        lead = "contact:someone can vouch here"

    if labels:
        lead += f" ({', '.join(labels)})"
    elif standing >= 0.7:
        lead += " (solid local lead)"
    return lead


def _build_known_locations_report(sim, player_eid, limit=None, include_hidden=False):
    return _report_runtime_build_known_locations_report(
        sim,
        player_eid,
        limit=limit,
        include_hidden=include_hidden,
        entity_display_name_fn=_entity_display_name,
        hours_text_fn=_dialogue_hours_text,
        security_tier_text_fn=_dialogue_security_tier_text,
        human_join_fn=_dialogue_human_join,
        infrastructure_target_property_fn=_infrastructure_target_property,
        infrastructure_role_label_fn=_infrastructure_role_label,
        storefront_illegal_goods_signal_fn=_storefront_illegal_goods_signal,
        property_legend_line_fn=_property_legend_line,
    )


def _build_known_people_report(sim, player_eid, limit=None):
    return _report_runtime_build_known_people_report(
        sim,
        player_eid,
        limit=limit,
    )


def _active_property_opportunities(sim, prop_id):
    prop_key = str(prop_id or "").strip()
    if not prop_key:
        return ()
    opp_state = getattr(sim, "world_traits", {}).get("opportunities", {})
    active = []
    for entry in opp_state.get("active", ()):
        if not isinstance(entry, dict):
            continue
        requirements = entry.get("requirements", {}) if isinstance(entry.get("requirements", {}), dict) else {}
        property_matches = {
            str(requirements.get("property_id", "")).strip(),
            str(requirements.get("pickup_property_id", "")).strip(),
            str(requirements.get("delivery_property_id", "")).strip(),
        }
        property_matches.discard("")
        if prop_key not in property_matches:
            continue
        active.append(entry)
    return tuple(active)


def _nearest_stakeable_property(sim, pos):
    if pos is None:
        return None
    nearby = sim.properties_in_radius(pos.x, pos.y, pos.z, r=STAKEOUT_RADIUS)
    candidates = [
        prop for prop in nearby
        if str(prop.get("kind", "")).strip().lower() == "building"
        and _active_property_opportunities(sim, prop.get("id"))
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda p: _manhattan(pos.x, pos.y, p["x"], p["y"]))


def _stakeout_property_opportunity_stats(sim, observer_eid, prop_id):
    prop_key = str(prop_id or "").strip()
    active = list(_active_property_opportunities(sim, prop_id))
    if not active:
        return None

    least_confidence = 2.0
    unknown_count = 0
    for entry in active:
        oid = int(entry.get("id", 0) or 0)
        if oid <= 0:
            continue
        intel = opportunity_intel_for_observer(sim, observer_eid, oid)
        if intel is None:
            unknown_count += 1
            least_confidence = min(least_confidence, 0.0)
            continue
        least_confidence = min(
            least_confidence,
            max(0.0, float(intel.get("confidence", 0.0) or 0.0)),
        )

    if least_confidence > 1.0:
        least_confidence = 0.0

    return {
        "count": len(active),
        "unknown_count": unknown_count,
        "least_confidence": max(0.0, min(1.0, float(least_confidence))),
        "mapped": unknown_count <= 0 and least_confidence >= (STAKEOUT_CONFIDENCE_CAP - 0.01),
        "tracked_surface": tracked_target_surface_snapshot(
            sim,
            prop_key,
            player_eid=observer_eid,
        ),
    }


def _stakeout_progress_snapshot(sim, observer_eid, pos, *, require_hidden=False):
    if pos is None:
        return None
    stealth_state = getattr(sim, "player_stealth_state", {})
    hidden = bool(stealth_state.get("hidden")) if isinstance(stealth_state, dict) else False
    if require_hidden and not hidden:
        return None
    target_prop = _nearest_stakeable_property(sim, pos)
    if not isinstance(target_prop, dict):
        return None
    prop_id = str(target_prop.get("id", "")).strip()
    stats = _stakeout_property_opportunity_stats(sim, observer_eid, prop_id)
    if not isinstance(stats, dict):
        return None

    state = getattr(sim, "stakeout_state", None)
    active = isinstance(state, dict) and str(state.get("prop_id", "")).strip() == prop_id
    ticks = _int_or_default((state or {}).get("ticks", 0), 0) if active else 0
    reveals_done = _int_or_default((state or {}).get("reveals_done", 0), 0) if active else 0
    progress_mod = ticks % STAKEOUT_REVEAL_INTERVAL
    next_reveal_in = (
        STAKEOUT_REVEAL_INTERVAL
        if progress_mod == 0
        else (STAKEOUT_REVEAL_INTERVAL - progress_mod)
    )
    return {
        "property_id": prop_id,
        "property_name": str(target_prop.get("name", prop_id or "target site")).strip() or "target site",
        "hidden": hidden,
        "active": active,
        "ready": hidden,
        "ticks": max(0, ticks),
        "reveals_done": max(0, reveals_done),
        "max_reveals": STAKEOUT_MAX_REVEALS,
        "next_reveal_in": max(1, next_reveal_in),
        **stats,
    }


def _property_legend_line(prop, text, active_quest_target=None):
    appearance = _appearance_property_render_snapshot(
        prop,
        active_quest_target=active_quest_target,
    )
    return _legend_line(
        text,
        glyph=appearance.glyph,
        color=appearance.color,
        attrs=getattr(curses, "A_BOLD", 0),
        semantic_id=appearance.semantic_id,
    )


def _item_reference_line(item_id, text, prefix=""):
    item_def = ITEM_CATALOG.get(item_id, {})
    glyph = _item_display_glyph(item_def)
    color = _ground_item_color(item_def)
    semantic_id = _item_reference_semantic_id(item_def)
    return _legend_line(
        text,
        glyph=glyph,
        color=color,
        prefix=prefix,
        attrs=getattr(curses, "A_BOLD", 0),
        semantic_id=semantic_id,
    )


def _item_legend_line(item_id, text):
    return _item_reference_line(item_id, text)


def _creature_color_key(identity, *, role="", cat_color_map=None):
    return _appearance_creature_color_key(identity, role=role)


def _entity_render_style(sim, eid, player_eid=None):
    return sim.appearance.entity(eid, player_eid=player_eid)


def _entity_legend_line(sim, eid, text, player_eid=None):
    appearance = _entity_render_style(sim, eid, player_eid=player_eid)
    return _legend_line(
        text,
        glyph=appearance.glyph,
        color=appearance.color,
        attrs=getattr(curses, "A_BOLD", 0),
    )


def _tile_label(sim, tile, x, y, z=0):
    if not tile:
        return "open ground"

    feature_style = _appearance_feature_tile_style(sim, tile, x, y, z)
    if feature_style:
        return feature_style[2]

    glyph = str(tile.glyph)[:1] or "."
    structure = sim.structure_at(x, y, z) if hasattr(sim, "structure_at") else None
    if not tile.walkable and glyph == "#" and _building_id_from_structure(structure):
        return "building wall"
    if tile.walkable and glyph == "." and _building_id_from_structure(structure):
        return "building interior"
    if glyph == "B":
        return "building wall"
    if glyph == "b":
        return "building interior"
    if glyph == "#":
        return "rough barrier"
    if glyph == ",":
        return "brush or ground cover"
    if glyph == "^":
        return "rock outcrop"
    if glyph == "~":
        return "water"
    if glyph == "_":
        return "shore or salt flats"
    if glyph == "=":
        return "road"
    if glyph == '"':
        return "window"
    if glyph == ".":
        return "open ground"
    return f"tile:{glyph}"


def _tile_legend_line(sim, x, y, z, text):
    tile = sim.tilemap.tile_at(x, y, z)
    glyph, color = _tile_render_style(sim, tile, x, y, z)
    return _legend_line(text, glyph=glyph, color=color, attrs=getattr(curses, "A_BOLD", 0))


def _building_street_label(prop):
    metadata = _property_metadata(prop)
    archetype = str(metadata.get("archetype", "") or "").strip().lower()
    if archetype in BUILDING_STREET_LABELS:
        return BUILDING_STREET_LABELS[archetype]
    if archetype:
        return f"{archetype.replace('_', ' ')} building"
    return "building exterior"


def _building_frontage_bits(prop):
    apertures = _property_apertures(prop)
    bits = []
    profile = _building_exterior_profile_for(_property_metadata(prop))
    frontage = str(profile.get("frontage", "") or "").strip()
    if frontage and frontage != "plain frontage":
        bits.append(frontage)
    if any(bool(aperture.get("ordinary")) for aperture in apertures):
        bits.append("front door")
    if any(
        str(aperture.get("kind", "")).strip().lower() in {"service_door", "employee_door", "side_door"}
        for aperture in apertures
    ):
        bits.append("side/service door")
    window_count = sum(
        1
        for aperture in apertures
        if str(aperture.get("kind", "")).strip().lower() in {"window", "skylight"}
    )
    exterior_class = str(profile.get("class", "") or "").strip().lower()
    if window_count == 1:
        if exterior_class == "industrial":
            bits.append("single service window")
        else:
            bits.append("1 window")
    elif window_count > 1:
        if exterior_class == "storefront":
            bits.append(f"{window_count} display windows")
        elif exterior_class == "residential":
            bits.append(f"{window_count} home windows")
        elif exterior_class == "corporate":
            bits.append(f"{window_count} office windows")
        elif exterior_class == "civic":
            bits.append(f"{window_count} public windows")
        elif exterior_class == "entertainment":
            bits.append(f"{window_count} venue windows")
        else:
            bits.append(f"{window_count} windows")
    elif exterior_class == "secure":
        bits.append("few exterior openings")
    return bits


def _building_street_summary(sim, prop):
    if not prop:
        return ""

    metadata = _property_metadata(prop)
    pulse = _legacy_building_pulse_snapshot(sim, prop=prop)
    profile = _building_exterior_profile_for(metadata)
    bits = [_building_street_label(prop)]
    access_level = _property_access_level(prop)
    if access_level == "public":
        bits.append(_property_status_text(sim, prop))
    elif access_level == "restricted":
        bits.append("restricted")
    else:
        bits.append("protected")

    try:
        floors = int(metadata.get("floors", 1))
    except (TypeError, ValueError):
        floors = 1
    if floors > 1:
        bits.append(f"{floors} floors")
    pulse_street = str(pulse.get("street_label", "") or "").strip()
    if pulse_street:
        bits.append("activity:" + pulse_street)

    bits.extend(_building_frontage_bits(prop))

    signage = _property_signage(prop)
    sign_text = str(signage.get("text", "") or "").strip() if signage else ""
    if sign_text:
        bits.append(f"sign:{sign_text}")
    elif str(profile.get("class", "") or "").strip().lower() in {"industrial", "secure"}:
        bits.append("no public sign")

    return ", ".join(bit for bit in bits if bit)


def _property_summary(sim, prop, viewer_eid=None, x=None, y=None, z=None):
    if not prop:
        return "property"

    metadata = _property_metadata(prop)
    kind = str(prop.get("kind", "property")).strip().lower() or "property"
    archetype = str(metadata.get("archetype", "")).strip().lower()
    if property_is_item_backed_fixture(prop):
        profile = metadata.get("object_profile") if isinstance(metadata.get("object_profile"), dict) else {}
        text = meaningful_object_display_text(sim, prop, viewer_eid=viewer_eid)
        if not text:
            text = object_profile_display_text(profile, fallback_name=prop.get("name", "object"))
        if bool(metadata.get("ambient_ritual")):
            handle = str(prop.get("name", "") or "").strip()
            if handle and handle.lower() not in text.lower():
                text = f"{handle} ({text})"
        bits = [text, "[fixture/item-backed object]"]
        description = str(metadata.get("display_description", "") or "").strip()
        if description and description.lower() != text.lower():
            bits.append(description)
        pickup_allowed = bool(metadata.get("pickup_allowed", True))
        bits.append("pickup:yes" if pickup_allowed else "pickup:no")
        rarity = str(profile.get("rarity", "") or "").strip().lower()
        if rarity and rarity != "common":
            bits.append(f"rarity:{rarity}")
        return " ".join(bit for bit in bits if bit)
    infrastructure_role = _property_infrastructure_role(prop)
    infrastructure_target = _infrastructure_target_property(sim, prop) if infrastructure_role else None
    owner_eid = prop.get("owner_eid")
    owner_tag = prop.get("owner_tag")

    if owner_eid == viewer_eid:
        owner_text = "you"
    elif owner_eid is not None:
        owner_text = _entity_display_name(sim, owner_eid, title_case=False)
    else:
        owner_text = str(owner_tag or "unowned")

    bits = [str(prop.get("name", prop.get("id", "property"))).strip() or "property"]
    label = kind if not archetype else f"{kind}/{archetype}"
    bits.append(f"[{label}]")
    if is_quick_travel_ramp_property(prop):
        bits.append("quick travel entrance")
    organization_eid = property_organization_eid(sim, prop, ensure=(kind == "building"))
    organization_text = organization_name(sim, organization_eid)
    if organization_text and organization_text.lower() != bits[0].lower():
        bits.append(f"org:{organization_text}")
    visible_presence = format_visible_property_org_presence(sim, prop)
    if visible_presence:
        bits.append(f"orgs:{visible_presence}")
    elif not organization_text:
        primary_presence = format_property_org_presence(sim, prop, include_primary=True, max_rows=1)
        if primary_presence:
            bits.append(f"orgs:{primary_presence}")
    if kind == "building":
        building_id = _building_id_from_property(prop)
        revealed_building_id = _viewer_revealed_building_id(
            sim,
            viewer_eid,
            z=z if z is not None else prop.get("z", 0),
        )
        bits.append("interior" if building_id and building_id == revealed_building_id else "exterior")
        pulse_label = str(_legacy_building_pulse_snapshot(sim, prop=prop).get("label", "") or "").strip()
        if pulse_label:
            bits.append("pulse:" + pulse_label)
    if infrastructure_role:
        bits.append("role:" + _infrastructure_role_label(infrastructure_role))
        if infrastructure_target:
            target_name = str(
                infrastructure_target.get("name", infrastructure_target.get("id", "property"))
            ).strip() or "property"
            bits.append("target:" + target_name)
    bits.append(f"owner:{owner_text}")
    access = _evaluate_property_access(sim, viewer_eid, prop, x=x, y=y, z=z)
    access_text = access.access_level
    if access.currently_open is not None:
        access_text = f"{access_text}/{_property_status_text(sim, prop, hour=access.current_hour)}"
    bits.append(access_text)
    room_access_level = str(getattr(access, "room_access_level", "") or "").strip().lower()
    room_kind = str(getattr(access, "room_kind", "") or "").strip().lower()
    if room_kind and room_access_level and room_access_level != "property":
        bits.append(f"room_access:{room_access_level.replace('_', ' ')}")
    room_hint = _room_curiosity_hint_for_tile(prop, room_kind=room_kind, x=x, y=y, z=z)
    if room_hint:
        bits.append("room_hint:" + room_hint)
    if _property_is_storefront(prop):
        service = _storefront_service_profile(sim, prop)
        service_label = str(service.get("summary_label", "")).strip()
        if service_label:
            bits.append(f"trade:{service_label}")
    lock_source = infrastructure_target if infrastructure_role == "access_panel" and infrastructure_target else prop
    lock_state = property_lock_state(lock_source)
    controller = None
    credential_status = ""
    if str(lock_source.get("kind", "")).strip().lower() == "building":
        controller = _property_access_controller(sim, lock_source)
    if lock_state["key_id"]:
        bits.append(f"lock:{'locked' if lock_state['locked'] else 'unlocked'}")
        if controller:
            bits.append("req:" + _controller_credential_short_label(controller))
        credential_status = _viewer_property_credential_status(sim, viewer_eid, lock_source)
        if credential_status and kind != "vehicle":
            bits.append("cred:" + credential_status)
    if str(lock_source.get("kind", "")).strip().lower() == "building":
        controller_kind = str(controller.get("kind", "") or "").strip().lower()
        if controller_kind in {"owner_schedule", "auto_timer", "auto_lock"}:
            bits.append("ctrl:" + controller_kind.replace("_", " "))

    if kind == "vehicle":
        from game.property_runtime import vehicle_fuel_values as _vehicle_fuel_values
        from game.property_runtime import vehicle_profile_from_property as _vehicle_profile_from_property

        profile = _vehicle_profile_from_property(prop)
        owned_vehicle = (
            prop.get("owner_eid") == viewer_eid
            or str(prop.get("owner_tag", "") or "").strip().lower() == "player"
        )
        if owned_vehicle:
            bits.append("owned")
        if lock_state["key_id"]:
            if credential_status == "held":
                bits.append("key:held")
            elif owned_vehicle:
                bits.append("key:missing")
        if profile:
            fuel, fuel_capacity = _vehicle_fuel_values(prop)
            bits.append(f"class:{profile['vehicle_class']}")
            bits.append(
                f"stats:p{int(profile['power'])}/d{int(profile['durability'])}/e{int(profile['fuel_efficiency'])}"
            )
            bits.append(f"fuel:{fuel}/{fuel_capacity}")
        return " ".join(bits)

    access_modes = _property_access_summary(sim, prop, viewer_eid=viewer_eid)
    if access_modes:
        bits.append("access:" + access_modes)

    services = _property_services(prop)
    if services:
        bits.append("services:" + ",".join(services))

    if access.standing_reason and access.standing_reason not in {"none", "open_business", "public_space"}:
        bits.append(f"standing:{access.standing_reason}")

    cover_kind = str(metadata.get("cover_kind", "") or "").strip().lower()
    if cover_kind in {"none", "low", "full"}:
        try:
            cover_value = int(float(metadata.get("cover_value", 0.0)) * 100)
        except (TypeError, ValueError):
            cover_value = 0
        cover_value = max(0, min(99, cover_value))
        bits.append(f"cover:{cover_kind}:{cover_value}%")

    floors = metadata.get("floors")
    try:
        floors = int(floors)
    except (TypeError, ValueError):
        floors = None
    if floors and floors > 1:
        bits.append(f"floors:{floors}")

    rooms = metadata.get("rooms")
    if isinstance(rooms, (list, tuple)) and rooms:
        bits.append(f"rooms:{len(rooms)}")

    signage = _property_signage(prop)
    if signage:
        sign_text = str(signage.get("text", "") or "").strip()
        if sign_text and sign_text.lower() != bits[0].lower():
            bits.append(f"sign:{sign_text}")

    purchase_cost = metadata.get("purchase_cost")
    try:
        purchase_cost = int(purchase_cost)
    except (TypeError, ValueError):
        purchase_cost = None
    if purchase_cost is not None:
        bits.append(f"cost:{purchase_cost}")

    return " ".join(bits)


def _structure_summary(info):
    if not isinstance(info, dict):
        return ""

    name = str(info.get("name", "building")).strip() or "building"
    archetype = str(info.get("archetype", "")).strip().lower()
    room_kind = str(info.get("room_kind", "")).strip().lower()
    try:
        floor = int(info.get("floor", 0))
    except (TypeError, ValueError):
        floor = 0
    try:
        floors = int(info.get("floors", 1))
    except (TypeError, ValueError):
        floors = 1
    try:
        basement_levels = int(info.get("basement_levels", 0))
    except (TypeError, ValueError):
        basement_levels = 0
    try:
        total_levels = int(info.get("total_levels", floors + basement_levels))
    except (TypeError, ValueError):
        total_levels = floors + basement_levels

    bits = [name]
    if archetype and archetype not in name.lower():
        bits.append(f"[{archetype}]")
    if total_levels > 1:
        bits.append(f"floor:{_floor_label(floor)}/{total_levels}")
    if room_kind:
        bits.append("room:" + room_kind.replace("_", " "))

    rooms = info.get("rooms")
    if isinstance(rooms, (list, tuple)) and rooms:
        preview = ", ".join(str(room).replace("_", " ") for room in rooms[:2])
        if len(rooms) > 2:
            preview += f" +{len(rooms) - 2}"
        bits.append(f"plan:{preview}")

    return " ".join(bit for bit in bits if bit)


def _location_description_snapshot(sim, x, y, z):
    if sim is None or x is None or y is None or z is None:
        return {
            "prop": None,
            "structure": None,
            "building_token": "",
            "room_token": "",
        }

    try:
        x = int(x)
        y = int(y)
        z = int(z)
    except (TypeError, ValueError):
        return {
            "prop": None,
            "structure": None,
            "building_token": "",
            "room_token": "",
        }

    structure = sim.structure_at(x, y, z) if hasattr(sim, "structure_at") else None
    prop = _property_covering(sim, x, y, z)
    prop_kind = str((prop or {}).get("kind", "") or "").strip().lower()
    building_token = _building_id_from_property(prop) if prop_kind == "building" else ""
    if not building_token:
        building_token = _building_id_from_structure(structure)

    room_kind = str((structure or {}).get("room_kind", "") or "").strip().lower()
    room_token = ""
    if room_kind:
        try:
            floor = int((structure or {}).get("floor", z))
        except (TypeError, ValueError):
            floor = int(z)
        room_token = f"{building_token}:{floor}:{room_kind}" if building_token else f"{floor}:{room_kind}"

    return {
        "prop": prop if isinstance(prop, dict) else None,
        "structure": structure if isinstance(structure, dict) else None,
        "building_token": str(building_token or "").strip(),
        "room_token": room_token,
    }


def _room_curiosity_hint_for_tile(prop, *, room_kind="", x=None, y=None, z=None):
    metadata = _property_metadata(prop)
    rows = metadata.get("room_curiosities") if isinstance(metadata, dict) else None
    if not isinstance(rows, (list, tuple)):
        return ""
    room_kind = str(room_kind or "").strip().lower()
    try:
        x = int(x) if x is not None else None
        y = int(y) if y is not None else None
        z = int(z) if z is not None else None
    except (TypeError, ValueError):
        x = y = z = None
    candidates = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_room = str(row.get("room_kind", "") or "").strip().lower()
        if row_room and room_kind and row_room != room_kind:
            continue
        try:
            row_floor = int(row.get("floor", z if z is not None else 0))
        except (TypeError, ValueError):
            row_floor = z
        if z is not None and row_floor is not None and int(row_floor) != int(z):
            continue
        try:
            row_x = int(row.get("x")) if row.get("x") is not None else None
            row_y = int(row.get("y")) if row.get("y") is not None else None
        except (TypeError, ValueError):
            row_x = row_y = None
        if row_x is not None and row_y is not None and x is not None and y is not None:
            if abs(row_x - x) + abs(row_y - y) > 2:
                continue
        signal = str(row.get("room_curiosity_signal", "") or "").strip()
        if signal:
            candidates.append(signal)
    return candidates[0] if candidates else ""


def _property_knowledge_hint(sim, viewer_eid, prop):
    if not prop or viewer_eid is None:
        return ""

    knowledge = sim.ecs.get(PropertyKnowledge).get(viewer_eid)
    if not knowledge:
        return ""

    known = knowledge.known.get(prop["id"])
    if not known or float(known.get("confidence", 0.0)) < 0.5:
        return ""

    source_eid = known.get("source_eid")
    source_name = ""
    if source_eid is not None:
        source_name = _entity_display_name(sim, source_eid, title_case=True)

    lead_kind = str(known.get("lead_kind", "") or "").strip().lower()
    if lead_kind == "workplace":
        return f"known:{source_name} works here" if source_name else "known:workplace"
    if lead_kind == "owner":
        return f"known:{source_name} owns this" if source_name else "known:owner"
    if lead_kind == "hours":
        return f"known:{source_name} mentioned public hours" if source_name else "known:hours"
    if lead_kind == "location":
        return f"known:{source_name} placed this on your map" if source_name else "known:location"
    if lead_kind == "organization_presence":
        return "known:organization presence"
    if lead_kind == "crew_activity":
        crew_rows = crime_plan_surface_rows(sim, prop=prop)
        if crew_rows:
            return "known:crew activity"
        return "known:crew activity (no live detail)"
    if lead_kind in {"access", "security"}:
        return f"known:{source_name} mentioned access" if source_name else "known:access"
    if lead_kind == "contraband":
        return f"known:{source_name} mentioned hot goods" if source_name else "known:contraband"

    owner_eid = known.get("owner_eid")
    if owner_eid == viewer_eid:
        return "known:your property"
    if owner_eid is not None:
        return "known:privately owned"

    owner_tag = str(known.get("owner_tag", "") or "").strip().lower()
    if owner_tag:
        return f"known:{owner_tag}"
    return ""


def _storefront_illegal_goods_signal(sim, prop):
    if not prop or not _property_is_storefront(prop):
        return None
    metadata = prop.get("metadata", {}) if isinstance(prop.get("metadata", {}), dict) else {}
    archetype = str(metadata.get("archetype", "")).strip().lower()
    if not archetype:
        return None

    profile = dict(getattr(TradeSystem, "STORE_PROFILES", {}).get(archetype, {}))
    weighted_pool = list(profile.get("item_pool", ()))
    if not weighted_pool:
        return None

    stores = getattr(sim, "stores", {})
    store_state = stores.get(prop.get("id")) if isinstance(stores, dict) else None
    actual_examples = []
    if isinstance(store_state, dict):
        for entry in store_state.get("entries", ()):
            item_id = str(entry.get("item_id", "")).strip().lower()
            if int(entry.get("stock", 0) or 0) <= 0:
                continue
            item_def = ITEM_CATALOG.get(item_id, {})
            if str(item_def.get("legal_status", "legal")).strip().lower() != "illegal":
                continue
            actual_examples.append(item_display_name(item_id))
    if actual_examples:
        unique_examples = []
        seen = set()
        for label in actual_examples:
            clean = str(label).strip()
            if not clean or clean in seen:
                continue
            seen.add(clean)
            unique_examples.append(clean)
        return {
            "confidence": 0.78,
            "examples": tuple(unique_examples[:3]),
            "source": "live_stock",
            "archetype": archetype,
        }

    market_profile = store_supply_profile(sim, prop)
    illegal_weight = 0.0
    total_weight = 0.0
    example_rows = []
    for item_id, weight in weighted_pool:
        item_def = ITEM_CATALOG.get(item_id, {})
        legal_status = str(item_def.get("legal_status", "legal")).strip().lower()
        if legal_status not in {"legal", "restricted", "illegal"}:
            legal_status = "legal"
        bias = item_market_bias(item_id, market_profile)
        adjusted_weight = max(0.0, float(weight) * max(0.1, float(bias.get("weight_mult", 1.0))))
        total_weight += adjusted_weight
        if legal_status != "illegal":
            continue
        illegal_weight += adjusted_weight
        example_rows.append((adjusted_weight, item_display_name(item_id)))
    if total_weight <= 0.0 or illegal_weight <= 0.0:
        return None

    example_rows.sort(key=lambda row: (-row[0], row[1]))
    examples = []
    seen = set()
    for _weight, label in example_rows:
        clean = str(label).strip()
        if not clean or clean in seen:
            continue
        seen.add(clean)
        examples.append(clean)
        if len(examples) >= 3:
            break

    ratio = illegal_weight / total_weight
    if ratio < 0.14:
        return None
    return {
        "confidence": min(0.74, 0.48 + (ratio * 0.6)),
        "examples": tuple(examples),
        "source": "market_profile",
        "archetype": archetype,
    }
