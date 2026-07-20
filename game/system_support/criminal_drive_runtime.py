"""Shared runtime helpers for criminal intent, targeting, and affiliation."""

from __future__ import annotations

from engine.derived_facts import cached_derived_fact
from engine.sites import site_entry_front_cell
from engine.events import Event
from game.components import (
    AI,
    CriminalDriveState,
    FinancialProfile,
    Inventory,
    NPCNeeds,
    NPCRoutine,
    Occupation,
    OrganizationCrimePlans,
    PlayerAssets,
    Position,
    Vitality,
)
from game.item_semantics import item_legal_status as _item_legal_status
from game.items import ITEM_CATALOG, credstick_total_credits, is_credstick_item
from game.item_valuation import item_fair_value
from game.justice_runtime import justice_snapshot
from game.organization_reputation import organization_instability_profile
from game.organizations import (
    actor_assigned_crime_plans,
    actor_org_memberships,
    assign_actor_organization,
    organization_policy_snapshot,
    organization_profile,
    property_field_domains,
    property_org_links,
)
from game.property_access import evaluate_property_access, property_access_level as _property_access_level
from game.property_runtime import property_focus_position as _property_focus_position, property_is_public as _property_is_public, property_metadata as _property_metadata
from game.skills import actor_skill, actor_tool_terms
from game.system_support.entity_naming import _entity_display_name
from game.system_support.interaction_ordering import _manhattan
from game.system_support.item_provenance_runtime import classify_item_claim
from game.system_support.settlement_runtime import _home_property


CRIMINAL_FAMILIES = {"street_gang", "criminal_network", "criminal"}
CRIMINAL_RECRUIT_LINK_KINDS = {"meeting_place", "safehouse", "service_host", "operates"}
TARGET_EXCLUDED_ARCHETYPES = {
    "shelter",
    "ruin_shelter",
    "pharmacy",
    "biotech_clinic",
    "field_hospital",
    "clinic",
    "hospital",
    "courthouse",
    "jail",
    "prison",
}
CRIME_TARGET_RADIUS = 14
AFFILIATION_RADIUS = 18
_ACTIVE_PLAN_UNSET = object()


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _text(value):
    return str(value or "").strip()


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def _criminal_drive_runtime_cache(sim, *, current_tick=None):
    if current_tick is None:
        current_tick = getattr(sim, "tick", 0)
    tick = _safe_int(current_tick, default=0)
    state = getattr(sim, "criminal_drive_runtime_cache", None)
    if not isinstance(state, dict) or _safe_int(state.get("tick"), default=-1) != tick:
        state = {
            "tick": tick,
            "nearby_buildings": {},
            "property_terms": {},
        }
        sim.criminal_drive_runtime_cache = state
    return state


def criminal_drive_state(sim, actor_eid, *, create=False):
    actor_eid = _safe_int(actor_eid, default=0)
    if actor_eid <= 0:
        return None
    state = sim.ecs.get(CriminalDriveState).get(actor_eid)
    if state is None and create:
        state = CriminalDriveState()
        sim.ecs.add(actor_eid, state)
    return state


def clear_criminal_drive_activity(state):
    if state is None:
        return None
    state.current_plan_key = None
    state.current_target_property_id = None
    state.current_target_ground_item_id = None
    state.current_target_building_id = None
    state.current_target_x = None
    state.current_target_y = None
    state.current_target_z = None
    state.current_disposal_property_id = None
    state.current_affiliation_target_property_id = None
    state.current_affiliation_organization_eid = None
    state.current_activity_kind = None
    state.current_activity_stage = None
    state.current_activity_summary = None
    return state


def _live_lodging_active(sim):
    live = getattr(sim, "live_timeskip", None)
    return isinstance(live, dict) and bool(live.get("active"))


def _actor_target_scan_signature(sim, actor_eid):
    pos = sim.ecs.get(Position).get(actor_eid)
    if pos is None:
        return None
    try:
        chunk = sim.chunk_coords(int(pos.x), int(pos.y))
    except Exception:
        chunk = None
    return (chunk, int(getattr(pos, "z", 0) or 0))


def _cached_target_scan(state, signature, *, current_tick, max_age):
    if state is None or signature is None:
        return None
    if getattr(state, "target_scan_signature", None) != signature:
        return None
    try:
        scan_tick = int(getattr(state, "target_scan_tick", 0) or 0)
    except (TypeError, ValueError):
        scan_tick = 0
    if int(current_tick) - int(scan_tick) > int(max_age):
        return None
    opportunistic = getattr(state, "cached_opportunistic_target", None)
    affiliations = getattr(state, "cached_affiliation_targets", ())
    if not isinstance(affiliations, tuple):
        affiliations = tuple(affiliations or ())
    return opportunistic if isinstance(opportunistic, dict) else None, affiliations


def _store_target_scan(state, signature, opportunistic_target, affiliation_targets, *, current_tick):
    if state is None:
        return
    state.target_scan_tick = int(current_tick)
    state.target_scan_signature = signature
    state.cached_opportunistic_target = dict(opportunistic_target) if isinstance(opportunistic_target, dict) else None
    if isinstance(affiliation_targets, tuple):
        state.cached_affiliation_targets = tuple(dict(row) for row in affiliation_targets if isinstance(row, dict))
    else:
        state.cached_affiliation_targets = tuple(dict(row) for row in tuple(affiliation_targets or ()) if isinstance(row, dict))


def _org_profile_tags(profile):
    return {
        _text(tag).lower()
        for tag in getattr(profile, "tags", ())
        if _text(tag)
    }


def _policy_family(sim, organization_eid):
    policy = organization_policy_snapshot(sim, organization_eid=organization_eid)
    if isinstance(policy, dict):
        family = _text(policy.get("family")).lower()
        if family:
            return family
    profile = organization_profile(sim, organization_eid)
    tags = _org_profile_tags(profile)
    for family_tag in ("street_gang", "criminal_network", "criminal", "labor_union", "trade_guild"):
        if family_tag in tags:
            return family_tag
    return _text(getattr(profile, "kind", "")).lower() or "other"


def _organization_is_vigilante(sim, organization_eid):
    profile = organization_profile(sim, organization_eid)
    if profile is None:
        return False
    tags = _org_profile_tags(profile)
    return "gang_posture:vigilante" in tags


def actor_criminal_memberships(sim, actor_eid, *, include_vigilante=False):
    rows = []
    for membership in actor_org_memberships(sim, actor_eid, active_only=True):
        organization_eid = _safe_int(membership.get("organization_eid"), default=0)
        if organization_eid <= 0:
            continue
        family = _policy_family(sim, organization_eid)
        if family not in CRIMINAL_FAMILIES:
            continue
        if not include_vigilante and _organization_is_vigilante(sim, organization_eid):
            continue
        profile = organization_profile(sim, organization_eid)
        rows.append(
            {
                **membership,
                "organization_eid": organization_eid,
                "family": family,
                "organization_name": _text(getattr(profile, "name", "")) or "Organization",
                "organization_key": _text(getattr(profile, "key", "")),
            }
        )
    rows.sort(
        key=lambda row: (
            int(row.get("authority_rank", 70)),
            _text(row.get("organization_name")).lower(),
            _safe_int(row.get("organization_eid"), default=0),
        )
    )
    return tuple(rows)


def _actor_wallet_pressure(sim, actor_eid):
    credits = 0
    assets = sim.ecs.get(PlayerAssets).get(actor_eid)
    if assets is not None:
        credits += max(0, _safe_int(getattr(assets, "credits", 0), default=0))
    finance = sim.ecs.get(FinancialProfile).get(actor_eid)
    debt = 0
    if finance is not None:
        credits += max(0, _safe_int(getattr(finance, "bank_balance", 0), default=0))
        debt = max(0, _safe_int(getattr(finance, "debt_balance", 0), default=0))
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if inventory is not None:
        for entry in inventory.items:
            item_id = _text(entry.get("item_id")).lower()
            if not item_id or int(entry.get("quantity", 0) or 0) <= 0:
                continue
            if is_credstick_item(item_id):
                credits += max(
                    0,
                    int(
                        credstick_total_credits(
                            quantity=entry.get("quantity", 1),
                            metadata=entry.get("metadata"),
                        )
                    ),
                )
    scarcity = _clamp((40.0 - min(40.0, float(credits))) / 40.0)
    debt_pressure = _clamp(float(debt) / 180.0)
    return {
        "credits": int(credits),
        "debt": int(debt),
        "scarcity": float(scarcity),
        "debt_pressure": float(debt_pressure),
    }


def _actor_anchor_profile(sim, actor_eid):
    occupation = sim.ecs.get(Occupation).get(actor_eid)
    routine = sim.ecs.get(NPCRoutine).get(actor_eid)
    home_prop = _home_property(sim, actor_eid)
    workplace = getattr(occupation, "workplace", None) if occupation is not None else None
    work_property_id = _text((workplace or {}).get("property_id")) if isinstance(workplace, dict) else ""
    home_property_id = _text((home_prop or {}).get("id"))
    work_anchor = 1.0 if work_property_id else 0.0
    home_anchor = 1.0 if home_property_id else 0.0
    routine_anchor = 0.0
    if routine is not None and (getattr(routine, "work", None) or getattr(routine, "home", None)):
        routine_anchor = 0.5
    anchor_strength = _clamp((work_anchor * 0.5) + (home_anchor * 0.35) + (routine_anchor * 0.15))
    return {
        "home_property_id": home_property_id or None,
        "work_property_id": work_property_id or None,
        "anchor_strength": float(anchor_strength),
    }


def _actor_primary_org_site_ids(sim, actor_eid):
    property_ids = set()
    for membership in actor_org_memberships(sim, actor_eid, active_only=True):
        property_id = _text(membership.get("site_property_id"))
        if property_id:
            property_ids.add(property_id)
    return property_ids


def _nearby_building_properties(sim, x, y, z, *, radius, current_tick=None):
    cache = _criminal_drive_runtime_cache(sim, current_tick=current_tick)
    try:
        chunk = sim.chunk_coords(int(x), int(y))
    except (TypeError, ValueError):
        chunk = None
    key = (chunk, _safe_int(z, default=0), _safe_int(radius, default=0))
    cached = cache.get("nearby_buildings", {}).get(key)
    if isinstance(cached, tuple):
        return cached

    rows = []
    seen = set()
    chunk_records = getattr(sim, "chunk_property_records", {})
    if chunk is not None and isinstance(chunk_records, dict) and chunk_records:
        chunk_radius = max(0, int((_safe_int(radius, default=0) + max(1, int(getattr(sim, "chunk_size", 16) or 16)) - 1) // max(1, int(getattr(sim, "chunk_size", 16) or 16))))
        for cx in range(int(chunk[0]) - chunk_radius, int(chunk[0]) + chunk_radius + 1):
            for cy in range(int(chunk[1]) - chunk_radius, int(chunk[1]) + chunk_radius + 1):
                for record in tuple(chunk_records.get((cx, cy), ()) or ()):
                    if not isinstance(record, dict):
                        continue
                    property_id = _text(record.get("id"))
                    if not property_id or property_id in seen:
                        continue
                    prop = sim.properties.get(property_id)
                    if not isinstance(prop, dict):
                        continue
                    if _text(prop.get("kind")).lower() != "building":
                        continue
                    try:
                        if _safe_int(prop.get("z"), default=0) != _safe_int(z, default=0):
                            continue
                    except Exception:
                        continue
                    seen.add(property_id)
                    rows.append(prop)
    if not rows:
        for prop in sim.properties.values():
            if not isinstance(prop, dict):
                continue
            if _text(prop.get("kind")).lower() != "building":
                continue
            property_id = _text(prop.get("id"))
            if not property_id or property_id in seen:
                continue
            if _safe_int(prop.get("z"), default=0) != _safe_int(z, default=0):
                continue
            seen.add(property_id)
            rows.append(prop)

    rows = tuple(sorted(rows, key=lambda prop: _text(prop.get("id")).lower()))
    cache.setdefault("nearby_buildings", {})[key] = rows
    return rows


def _ground_item_base_value(ground, *, sim=None, prop=None):
    if not isinstance(ground, dict):
        return 0.0
    item_id = _text(ground.get("item_id")).lower()
    if not item_id:
        return 0.0
    base = float(item_fair_value(item_id, ground.get("metadata"), item_catalog=ITEM_CATALOG))
    quantity = max(1, _safe_int(ground.get("quantity"), default=1))
    claim_class = str(classify_item_claim(sim, ground, prop=prop).get("claim_class", "") or "").strip().lower()
    if claim_class in {"public_free", "scene_salvage"}:
        base *= 0.28
    elif claim_class == "merchandise":
        base *= 1.12
    elif claim_class == "staff_supply":
        base *= 0.92
    elif claim_class == "private_effect":
        base *= 1.0
    return base * float(quantity)


def _property_footprint(prop):
    metadata = _property_metadata(prop)
    footprint = metadata.get("footprint")
    if not isinstance(footprint, dict):
        return None
    try:
        left = int(footprint.get("left"))
        right = int(footprint.get("right"))
        top = int(footprint.get("top"))
        bottom = int(footprint.get("bottom"))
    except (TypeError, ValueError):
        return None
    return left, right, top, bottom


def _ground_items_for_property(sim, prop):
    footprint = _property_footprint(prop)
    if footprint is None:
        return ()
    left, right, top, bottom = footprint
    base_z = int(prop.get("z", 0) or 0)
    rows = []
    for ground in getattr(sim, "ground_items", {}).values():
        try:
            x = int(ground.get("x"))
            y = int(ground.get("y"))
            z = int(ground.get("z", base_z))
        except (TypeError, ValueError):
            continue
        if z != base_z or not (left <= x <= right and top <= y <= bottom):
            continue
        rows.append(ground)
    rows.sort(
        key=lambda row: (
            -_ground_item_base_value(row, sim=sim, prop=prop),
            _text(row.get("ground_item_id")),
        )
    )
    return tuple(rows)


def _property_guard_count(sim, prop):
    footprint = _property_footprint(prop)
    if footprint is None:
        return 0
    left, right, top, bottom = footprint
    base_z = int(prop.get("z", 0) or 0)
    count = 0
    positions = sim.ecs.get(Position)
    ais = sim.ecs.get(AI)
    for eid, pos in positions.items():
        if int(getattr(pos, "z", base_z)) != base_z:
            continue
        if not (left <= int(pos.x) <= right and top <= int(pos.y) <= bottom):
            continue
        role = _text(getattr(ais.get(eid), "role", "")).lower()
        if role in {"guard", "scout"}:
            count += 1
    return count


def _property_camera_presence(prop):
    metadata = _property_metadata(prop)
    controller = metadata.get("access_controller")
    if isinstance(controller, dict):
        try:
            return 1 if int(controller.get("camera_count", 0) or 0) > 0 else 0
        except (TypeError, ValueError):
            return 0
    return 1 if bool(metadata.get("camera_network")) else 0


def _property_covert_fit(prop):
    metadata = _property_metadata(prop)
    if _text(metadata.get("hidden_contact_kind")):
        return 1.0
    if _text(metadata.get("backroom_profile")) or _text(metadata.get("covert_hint")):
        return 0.9
    domains = set(property_field_domains(prop))
    if "criminal" in domains:
        return 0.8
    return 0.0


def _shared_crime_property_terms(sim, prop, *, current_tick=None):
    if not isinstance(prop, dict):
        return None
    property_id = _text(prop.get("id"))
    if not property_id:
        return None
    cache = _criminal_drive_runtime_cache(sim, current_tick=current_tick)
    terms_cache = cache.setdefault("property_terms", {})
    cached = terms_cache.get(property_id)
    if isinstance(cached, dict):
        return cached

    focus = _property_focus_position(prop)
    if not focus:
        terms = {"property_id": property_id, "focus": None}
        terms_cache[property_id] = terms
        return terms

    ground_items = _ground_items_for_property(sim, prop)
    visible_value = sum(_ground_item_base_value(row, sim=sim, prop=prop) for row in ground_items[:4])
    valuable_item = ground_items[0] if ground_items else None
    instability = organization_instability_profile(sim, prop=prop, ensure=True)
    terms = {
        "property_id": property_id,
        "focus": (int(focus[0]), int(focus[1]), int(focus[2])),
        "archetype": _text(_property_metadata(prop).get("archetype")).lower(),
        "ground_items": ground_items,
        "visible_value": float(visible_value),
        "valuable_item": valuable_item if isinstance(valuable_item, dict) else None,
        "guard_count": int(_property_guard_count(sim, prop)),
        "camera_count": int(_property_camera_presence(prop)),
        "covert_fit": float(_property_covert_fit(prop)),
        "underrepresented": bool((instability or {}).get("underrepresented")),
    }
    terms_cache[property_id] = terms
    return terms


def crime_target_profile(sim, actor_eid, prop, *, plan_kind="petty_theft", current_tick=None):
    if actor_eid is None or not isinstance(prop, dict):
        return None
    property_id = _text(prop.get("id"))
    if not property_id:
        return None
    shared_terms = _shared_crime_property_terms(sim, prop, current_tick=current_tick)
    if not isinstance(shared_terms, dict):
        return None
    metadata = _property_metadata(prop)
    archetype = _text(shared_terms.get("archetype") or metadata.get("archetype")).lower()
    if archetype in TARGET_EXCLUDED_ARCHETYPES:
        return None

    anchor_profile = _actor_anchor_profile(sim, actor_eid)
    if property_id and property_id in {anchor_profile.get("home_property_id"), anchor_profile.get("work_property_id")}:
        return None
    if property_id in _actor_primary_org_site_ids(sim, actor_eid) and _text(plan_kind).lower() not in {"covert_sale", "fence_run"}:
        return None

    focus = shared_terms.get("focus")
    if not focus:
        return None
    ground_items = tuple(shared_terms.get("ground_items", ()) or ())
    if _text(plan_kind).lower() in {"petty_theft", "burglary"} and not ground_items:
        return None
    fx, fy, fz = focus
    if current_tick is None:
        current_tick = getattr(sim, "tick", 0)
    access = evaluate_property_access(sim, actor_eid, prop, x=fx, y=fy, z=fz)
    visible_value = float(shared_terms.get("visible_value", 0.0) or 0.0)
    valuable_item = shared_terms.get("valuable_item") if isinstance(shared_terms.get("valuable_item"), dict) else None
    guard_count = _safe_int(shared_terms.get("guard_count"), default=0)
    camera_count = _safe_int(shared_terms.get("camera_count"), default=0)
    covert_fit = _safe_float(shared_terms.get("covert_fit"), default=0.0)
    underrepresented = bool(shared_terms.get("underrepresented"))

    currently_open = bool(getattr(access, "currently_open", False))
    public_facing = bool(getattr(access, "public_facing", False))
    access_level = _text(getattr(access, "access_level", "")).lower() or _property_access_level(prop)
    permitted = bool(getattr(access, "permitted", False))
    watchfulness = _safe_int(getattr(access, "organization_watchfulness", 0), default=0)
    offhours_bonus = 0.18 if not currently_open else 0.0
    undercoverage_bonus = 0.12 if underrepresented else 0.0

    ingress_difficulty = 0.18
    if access_level == "protected":
        ingress_difficulty += 0.24
    elif access_level == "restricted":
        ingress_difficulty += 0.42
    if not permitted:
        ingress_difficulty += 0.16
    ingress_difficulty += min(0.24, guard_count * 0.09)
    ingress_difficulty += min(0.18, camera_count * 0.08)
    ingress_difficulty = _clamp(ingress_difficulty, 0.0, 1.4)

    exposure = 0.06
    if public_facing:
        exposure += 0.12
    if currently_open:
        exposure += 0.18
    exposure += min(0.26, watchfulness * 0.035)
    exposure += min(0.2, guard_count * 0.08)
    exposure += min(0.12, camera_count * 0.06)
    exposure = _clamp(exposure, 0.0, 1.2)

    softness = _clamp(1.0 - (ingress_difficulty * 0.62) - (exposure * 0.34) + offhours_bonus + undercoverage_bonus, 0.0, 1.0)
    exit_quality = _clamp(0.45 + (0.18 if public_facing else 0.0) + (0.14 if not currently_open else 0.0), 0.0, 1.0)
    value = _clamp((visible_value / 80.0) + (0.2 if valuable_item is not None else 0.0), 0.0, 2.0)
    if not ground_items and _text(plan_kind).lower() in {"petty_theft", "burglary"}:
        value *= 0.35
    score = (softness * 28.0) + (value * 22.0) + (exit_quality * 10.0) + (covert_fit * 6.0) - (exposure * 16.0)

    target_x, target_y, target_z = fx, fy, fz
    target_ground_item_id = None
    if valuable_item is not None:
        target_ground_item_id = _text(valuable_item.get("ground_item_id")) or None
        target_x = _safe_int(valuable_item.get("x"), default=fx)
        target_y = _safe_int(valuable_item.get("y"), default=fy)
        target_z = _safe_int(valuable_item.get("z"), default=fz)

    casing_x, casing_y, casing_z = int(fx), int(fy), int(fz)
    entry = metadata.get("entry") if isinstance(metadata.get("entry"), dict) else None
    entry_front = site_entry_front_cell(entry)
    if entry_front is not None:
        front_x, front_y, front_z = int(entry_front[0]), int(entry_front[1]), int(entry_front[2])
        if sim.tilemap.in_bounds(front_x, front_y) and sim.tilemap.is_walkable(front_x, front_y, front_z):
            casing_x, casing_y, casing_z = front_x, front_y, front_z

    return {
        "property_id": property_id,
        "property_name": _text(prop.get("name")) or property_id,
        "x": int(target_x),
        "y": int(target_y),
        "z": int(target_z),
        "target_ground_item_id": target_ground_item_id,
        "casing_x": int(casing_x),
        "casing_y": int(casing_y),
        "casing_z": int(casing_z),
        "softness": float(softness),
        "value": float(value),
        "exposure": float(exposure),
        "ingress_difficulty": float(ingress_difficulty),
        "exit_quality": float(exit_quality),
        "covert_fit": float(covert_fit),
        "currently_open": currently_open,
        "access_level": access_level,
        "public_facing": public_facing,
        "watchfulness": int(watchfulness),
        "guard_count": int(guard_count),
        "camera_count": int(camera_count),
        "score": float(score),
        "requires_entry": bool(valuable_item is not None and (target_x, target_y) != (fx, fy)),
    }


def choose_crime_target(sim, actor_eid, *, plan_kind="petty_theft", radius=CRIME_TARGET_RADIUS):
    positions = sim.ecs.get(Position)
    pos = positions.get(actor_eid)
    if pos is None:
        return None
    rows = []
    current_tick = getattr(sim, "tick", 0)
    for prop in _nearby_building_properties(sim, pos.x, pos.y, pos.z, radius=radius, current_tick=current_tick):
        focus = _shared_crime_property_terms(sim, prop, current_tick=current_tick).get("focus")
        if not focus:
            continue
        if _manhattan(int(pos.x), int(pos.y), int(focus[0]), int(focus[1])) > int(radius):
            continue
        profile = crime_target_profile(sim, actor_eid, prop, plan_kind=plan_kind, current_tick=current_tick)
        if not isinstance(profile, dict):
            continue
        distance = _manhattan(int(pos.x), int(pos.y), int(profile.get("x", focus[0])), int(profile.get("y", focus[1])))
        profile["distance"] = int(distance)
        profile["score"] -= min(10.0, float(distance) * 0.75)
        rows.append(profile)
    rows.sort(
        key=lambda row: (
            -float(row.get("score", 0.0)),
            float(row.get("exposure", 0.0)),
            int(row.get("distance", 9999)),
            _text(row.get("property_id")),
        )
    )
    return rows[0] if rows and float(rows[0].get("score", 0.0)) >= 8.0 else None


def criminal_affiliation_targets(sim, actor_eid, *, radius=AFFILIATION_RADIUS):
    positions = sim.ecs.get(Position)
    pos = positions.get(actor_eid)
    if pos is None:
        return ()
    current_membership_ids = {
        _safe_int(row.get("organization_eid"), default=0)
        for row in actor_criminal_memberships(sim, actor_eid, include_vigilante=True)
    }
    rows = []
    seen = set()
    current_tick = getattr(sim, "tick", 0)
    for prop in _nearby_building_properties(sim, pos.x, pos.y, pos.z, radius=radius, current_tick=current_tick):
        focus = _shared_crime_property_terms(sim, prop, current_tick=current_tick).get("focus")
        if not focus or int(focus[2]) != int(pos.z):
            continue
        distance = _manhattan(int(pos.x), int(pos.y), int(focus[0]), int(focus[1]))
        if distance > int(radius):
            continue
        for link in property_org_links(sim, prop, active_only=True):
            organization_eid = _safe_int(link.get("organization_eid"), default=0)
            if organization_eid <= 0 or organization_eid in current_membership_ids:
                continue
            family = _policy_family(sim, organization_eid)
            if family not in CRIMINAL_FAMILIES or _organization_is_vigilante(sim, organization_eid):
                continue
            link_kind = _text(link.get("link_kind")).lower()
            if link_kind not in CRIMINAL_RECRUIT_LINK_KINDS:
                continue
            if (organization_eid, _text(prop.get("id"))) in seen:
                continue
            seen.add((organization_eid, _text(prop.get("id"))))
            profile = organization_profile(sim, organization_eid)
            instability = organization_instability_profile(sim, organization_eid=organization_eid, ensure=True)
            pressure = float((instability or {}).get("operational_pressure", 0.0) or 0.0)
            score = (pressure * 22.0) + (8.0 if bool((instability or {}).get("underrepresented")) else 0.0) - (distance * 0.65)
            if link_kind in {"meeting_place", "safehouse"}:
                score += 5.0
            rows.append(
                {
                    "organization_eid": organization_eid,
                    "organization_name": _text(getattr(profile, "name", "")) or "Organization",
                    "organization_key": _text(getattr(profile, "key", "")),
                    "family": family,
                    "property_id": _text(prop.get("id")) or None,
                    "x": int(focus[0]),
                    "y": int(focus[1]),
                    "z": int(focus[2]),
                    "distance": int(distance),
                    "score": float(score),
                    "link_kind": link_kind,
                    "operational_pressure": pressure,
                }
            )
    rows.sort(
        key=lambda row: (
            -float(row.get("score", 0.0)),
            int(row.get("distance", 9999)),
            _text(row.get("organization_name")).lower(),
        )
    )
    return tuple(row for row in rows if float(row.get("score", 0.0)) >= 4.0)


def attempt_criminal_affiliation(sim, actor_eid, *, organization_eid, property_id=None, current_tick=None):
    actor_eid = _safe_int(actor_eid, default=0)
    organization_eid = _safe_int(organization_eid, default=0)
    if actor_eid <= 0 or organization_eid <= 0:
        return None
    if _organization_is_vigilante(sim, organization_eid):
        return {
            "accepted": False,
            "reason": "vigilante_org",
            "organization_eid": organization_eid,
            "property_id": _text(property_id) or None,
        }
    if current_tick is None:
        current_tick = getattr(sim, "tick", 0)
    state = criminal_drive_state(sim, actor_eid, create=True)
    drive_pressure = _clamp(_safe_float(getattr(state, "pressure", 0.0), default=0.0))
    drive_confidence = _clamp(_safe_float(getattr(state, "confidence", 0.0), default=0.0))
    affiliation_interest = _clamp(_safe_float(getattr(state, "affiliation_interest", 0.0), default=0.0))
    from game.system_support.npc_behavior_runtime import (
        BEHAVIOR_COMMIT_OPPORTUNISTIC_CRIME,
        BEHAVIOR_COMMIT_PLANNED_CRIME,
        BEHAVIOR_SEEK_CRIMINAL_AFFILIATION,
        _actor_behavior_value,
    )
    criminal_tendency = _clamp(
        max(
            _safe_float(_actor_behavior_value(sim, actor_eid, BEHAVIOR_SEEK_CRIMINAL_AFFILIATION, 0.0), default=0.0),
            _safe_float(_actor_behavior_value(sim, actor_eid, BEHAVIOR_COMMIT_OPPORTUNISTIC_CRIME, 0.0), default=0.0) * 0.7,
            _safe_float(_actor_behavior_value(sim, actor_eid, BEHAVIOR_COMMIT_PLANNED_CRIME, 0.0), default=0.0) * 0.7,
        )
    )
    instability = organization_instability_profile(sim, organization_eid=organization_eid, ensure=True)
    org_pressure = _clamp(_safe_float((instability or {}).get("operational_pressure", 0.0), default=0.0))
    underrepresented_bonus = 0.12 if bool((instability or {}).get("underrepresented")) else 0.0
    justice = justice_snapshot(sim, actor_eid)
    heat_penalty = min(0.4, float(justice.get("active_score", 0) or 0) / 90.0)
    anchor_penalty = _actor_anchor_profile(sim, actor_eid)["anchor_strength"] * 0.28
    accept_score = _clamp(
        (drive_pressure * 0.3)
        + ((1.0 - drive_confidence) * 0.14)
        + (affiliation_interest * 0.26)
        + (criminal_tendency * 0.14)
        + (org_pressure * 0.18)
        + underrepresented_bonus
        - heat_penalty
        - anchor_penalty,
        0.0,
        1.25,
    )
    accepted = accept_score >= 0.5
    profile = organization_profile(sim, organization_eid)
    role = "member"
    title = "associate"
    family = _policy_family(sim, organization_eid)
    if family == "street_gang":
        title = "runner"
    elif family == "criminal_network":
        title = "associate"
    if accepted:
        assign_actor_organization(
            sim,
            actor_eid,
            organization_eid=organization_eid,
            role=role,
            kind="membership",
            title=title,
            primary=False,
            authority_rank=70,
            site_property_id=property_id,
            active=True,
        )
    result = {
        "accepted": bool(accepted),
        "reason": "accepted" if accepted else "cold_reception",
        "organization_eid": organization_eid,
        "organization_name": _text(getattr(profile, "name", "")) or "Organization",
        "organization_key": _text(getattr(profile, "key", "")),
        "family": family,
        "property_id": _text(property_id) or None,
        "score": float(accept_score),
        "tick": _safe_int(current_tick, default=0),
    }
    sim.emit(
        Event(
            "npc_affiliation_attempt_resolved",
            npc_eid=actor_eid,
            accepted=bool(accepted),
            organization_eid=organization_eid,
            organization_name=result["organization_name"],
            organization_key=result["organization_key"],
            family=family,
            property_id=result["property_id"],
            score=round(float(accept_score), 3),
            x=None,
            y=None,
            z=None,
        )
    )
    return result


def active_plan_for_actor(sim, actor_eid, *, current_tick=None):
    actor_eid = _safe_int(actor_eid, default=0)
    if actor_eid <= 0:
        return None
    rows = active_crime_plan_actor_index(sim, current_tick=current_tick).get(actor_eid, ())
    return rows[0] if rows else None


def _crime_plan_rows_for_organization(sim, organization_eid, *, profile=None, current_tick=None):
    from game.organizations import organization_crime_plans

    if profile is None:
        profile = organization_profile(sim, organization_eid)
    rows = []
    for row in organization_crime_plans(
        sim,
        organization_eid,
        current_tick=current_tick,
        include_inactive=False,
    ):
        rows.append(
            {
                **row,
                "organization_key": _text(getattr(profile, "key", "")),
                "organization_name": _text(getattr(profile, "name", "")),
                "organization_kind": _text(getattr(profile, "kind", "")) if profile else "other",
            }
        )
    return tuple(rows)


def active_crime_plan_actor_index(sim, *, current_tick=None):
    if current_tick is None:
        current_tick = getattr(sim, "tick", 0)
    tick = _safe_int(current_tick, default=0)

    def build_index():
        index = {}
        plan_components = sim.ecs.get(OrganizationCrimePlans)
        for organization_eid in tuple(plan_components.keys()):
            profile = organization_profile(sim, organization_eid)
            for row in _crime_plan_rows_for_organization(
                sim,
                organization_eid,
                profile=profile,
                current_tick=tick,
            ):
                actor_ids = {
                    _safe_int(row.get("leader_eid"), default=0),
                    *{
                        _safe_int(actor_eid, default=0)
                        for actor_eid in tuple(row.get("assigned_member_eids", ()) or ())
                    },
                } - {0}
                for actor_id in actor_ids:
                    index.setdefault(int(actor_id), []).append(dict(row))
        for rows in index.values():
            rows.sort(
                key=lambda row: (
                    0 if _text(row.get("stage")).lower() == "executing" else 1,
                    -_safe_int(row.get("last_update_tick"), default=0),
                    _text(row.get("plan_key")),
                )
            )
        return index

    return cached_derived_fact(
        sim,
        "organization_crime_plans.actor_index",
        "all",
        build_index,
        domains=("organization_crime_plans",),
        signature=(tick,),
        max_entries=1,
    )


def find_registered_item_system(sim):
    for system in getattr(sim, "systems", ()):
        if hasattr(system, "_handle_pickup") and system.__class__.__name__ == "ItemSystem":
            return system
    return None


def nearest_target_ground_item(sim, property_id, *, ground_item_id=None):
    if ground_item_id:
        row = getattr(sim, "ground_items", {}).get(_text(ground_item_id))
        if isinstance(row, dict):
            return row
    prop = sim.properties.get(_text(property_id))
    if not isinstance(prop, dict):
        return None
    rows = _ground_items_for_property(sim, prop)
    return rows[0] if rows else None


def criminal_activity_summary(intent, *, plan_kind="", method_label="", property_name="", organization_name=""):
    intent_key = _text(intent).lower()
    property_name = _text(property_name)
    organization_name = _text(organization_name)
    plan_kind = _text(plan_kind).replace("_", " ")
    method_label = _text(method_label)
    plan_text = method_label or plan_kind
    if intent_key == "casing_target":
        return f"casing {property_name or 'a target'}".strip()
    if intent_key == "rendezvousing_crew":
        if plan_text:
            return f"rendezvousing for {plan_text}"
        return f"meeting up with {organization_name or 'the crew'}".strip()
    if intent_key == "seeking_criminal_affiliation":
        return f"looking for a way into {organization_name or 'a crew'}".strip()
    if plan_text:
        return f"working a {plan_text}".strip()
    if property_name:
        return f"working {property_name}".strip()
    return "working a target"


def update_criminal_drive_state(sim, actor_eid, *, current_tick=None, active_plan=_ACTIVE_PLAN_UNSET):
    actor_eid = _safe_int(actor_eid, default=0)
    if actor_eid <= 0:
        return None
    if current_tick is None:
        current_tick = getattr(sim, "tick", 0)
    state = criminal_drive_state(sim, actor_eid, create=True)
    needs = sim.ecs.get(NPCNeeds).get(actor_eid)
    vitality = sim.ecs.get(Vitality).get(actor_eid)
    safety_gap = _clamp((100.0 - float(getattr(needs, "safety", 80.0) or 80.0)) / 100.0)
    energy_gap = _clamp((100.0 - float(getattr(needs, "energy", 80.0) or 80.0)) / 100.0)
    social_gap = _clamp((100.0 - float(getattr(needs, "social", 70.0) or 70.0)) / 100.0)
    health_gap = 0.0
    if vitality is not None:
        max_hp = max(1, _safe_int(getattr(vitality, "max_hp", 1), default=1))
        hp = max(0, _safe_int(getattr(vitality, "hp", max_hp), default=max_hp))
        health_gap = _clamp(1.0 - (float(hp) / float(max_hp)))
    wallet = _actor_wallet_pressure(sim, actor_eid)
    justice = justice_snapshot(sim, actor_eid)
    justice_heat = _clamp(float(justice.get("active_score", 0) or 0) / 36.0)
    anchor_strength = _actor_anchor_profile(sim, actor_eid)["anchor_strength"]
    criminal_rows = actor_criminal_memberships(sim, actor_eid)
    criminal_pull = 0.0
    for row in criminal_rows[:2]:
        instability = organization_instability_profile(
            sim,
            organization_eid=_safe_int(row.get("organization_eid"), default=0),
            ensure=True,
        )
        criminal_pull = max(criminal_pull, _safe_float((instability or {}).get("operational_pressure"), default=0.0))

    tool_terms = actor_tool_terms(sim, actor_eid, "mechanical_lock")
    tool_support = 0.16 if bool(tool_terms.get("enabled")) else 0.0
    confidence_skill = _clamp((actor_skill(sim, actor_eid, "intrusion") - 4.0) / 8.0)
    streetwise_skill = _clamp((actor_skill(sim, actor_eid, "streetwise") - 4.0) / 8.0)

    recent_success = 0.12 if _safe_int(getattr(state, "last_success_tick", 0), default=0) and (int(current_tick) - int(state.last_success_tick)) <= 180 else 0.0
    recent_failure = 0.16 if _safe_int(getattr(state, "last_failure_tick", 0), default=0) and (int(current_tick) - int(state.last_failure_tick)) <= 180 else 0.0

    pressure = _clamp(
        (safety_gap * 0.18)
        + (energy_gap * 0.08)
        + (social_gap * 0.06)
        + (health_gap * 0.08)
        + (wallet["scarcity"] * 0.26)
        + (wallet["debt_pressure"] * 0.16)
        + (criminal_pull * 0.14)
        + recent_failure
        - (recent_success * 0.35)
        - (anchor_strength * 0.24),
        0.0,
        1.0,
    )
    confidence = _clamp(
        (confidence_skill * 0.34)
        + (streetwise_skill * 0.18)
        + tool_support
        + recent_success
        - recent_failure
        - (justice_heat * 0.22)
        - (health_gap * 0.08),
        0.0,
        1.0,
    )
    affiliation_interest = _clamp(
        (pressure * 0.34)
        + ((1.0 - confidence) * 0.18)
        + (criminal_pull * 0.24)
        + (social_gap * 0.06)
        - (anchor_strength * 0.2),
        0.0,
        1.0,
    )

    from game.system_support.npc_behavior_runtime import (
        BEHAVIOR_COMMIT_OPPORTUNISTIC_CRIME,
        BEHAVIOR_COMMIT_PLANNED_CRIME,
        BEHAVIOR_SEEK_CRIMINAL_AFFILIATION,
        _actor_behavior_value,
    )

    opportunistic_base = _actor_behavior_value(sim, actor_eid, BEHAVIOR_COMMIT_OPPORTUNISTIC_CRIME, 0.0)
    planned_base = _actor_behavior_value(sim, actor_eid, BEHAVIOR_COMMIT_PLANNED_CRIME, 0.0)
    affiliation_base = _actor_behavior_value(sim, actor_eid, BEHAVIOR_SEEK_CRIMINAL_AFFILIATION, 0.0)

    if active_plan is _ACTIVE_PLAN_UNSET:
        active_plan = active_plan_for_actor(sim, actor_eid, current_tick=current_tick)
    should_scan_targets = not bool(active_plan)
    should_scan_targets = should_scan_targets and (
        bool(criminal_rows)
        or float(pressure) >= 0.32
        or float(affiliation_interest) >= 0.34
        or float(opportunistic_base) >= 0.18
        or float(planned_base) >= 0.18
        or float(affiliation_base) >= 0.18
    )

    opportunistic_target = None
    affiliation_target = ()
    if should_scan_targets:
        target_signature = _actor_target_scan_signature(sim, actor_eid)
        cached_scan = _cached_target_scan(
            state,
            target_signature,
            current_tick=current_tick,
            max_age=48 if _live_lodging_active(sim) else 10,
        )
        if cached_scan is not None:
            opportunistic_target, affiliation_target = cached_scan
        else:
            opportunistic_target = choose_crime_target(sim, actor_eid, plan_kind="petty_theft")
            affiliation_target = criminal_affiliation_targets(sim, actor_eid)
            _store_target_scan(
                state,
                target_signature,
                opportunistic_target,
                affiliation_target,
                current_tick=current_tick,
            )
    state.pressure = float(pressure)
    state.confidence = float(confidence)
    state.affiliation_interest = float(affiliation_interest)
    state.last_eval_tick = int(current_tick)

    state.opportunistic_crime_score = max(
        0.0,
        (opportunistic_base * 42.0)
        + (pressure * 26.0)
        + (confidence * 12.0)
        + float((opportunistic_target or {}).get("score", 0.0) or 0.0)
        - (justice_heat * 12.0)
        - (anchor_strength * 14.0),
    )
    state.planned_crime_score = max(
        0.0,
        (planned_base * 40.0)
        + (pressure * 16.0)
        + (confidence * 10.0)
        + (26.0 if isinstance(active_plan, dict) else 0.0)
        + (criminal_pull * 10.0)
        - (justice_heat * 10.0)
        - (anchor_strength * 10.0),
    )
    state.affiliation_seek_score = max(
        0.0,
        (affiliation_base * 36.0)
        + (affiliation_interest * 30.0)
        + ((1.0 - confidence) * 8.0)
        + (8.0 if affiliation_target else 0.0)
        - (justice_heat * 8.0)
        - (anchor_strength * 12.0),
    )

    clear_criminal_drive_activity(state)
    if isinstance(active_plan, dict):
        stage = _text(active_plan.get("stage")).lower() or "forming"
        if stage in {"forming", "rendezvous"}:
            plan_property_id = _text(active_plan.get("staging_property_id")) or _text(active_plan.get("target_property_id"))
        elif stage == "disposing":
            plan_property_id = _text(active_plan.get("disposal_property_id")) or _text(active_plan.get("target_property_id"))
        else:
            plan_property_id = _text(active_plan.get("target_property_id")) or _text(active_plan.get("disposal_property_id"))
        target_prop = sim.properties.get(plan_property_id)
        focus = _property_focus_position(target_prop) if isinstance(target_prop, dict) else None
        state.current_plan_key = _text(active_plan.get("plan_key")) or None
        state.current_target_property_id = plan_property_id or None
        state.current_disposal_property_id = _text(active_plan.get("disposal_property_id")) or None
        state.current_activity_kind = _text(active_plan.get("kind")).lower() or "crew_job"
        state.current_activity_stage = stage or None
        state.current_activity_summary = criminal_activity_summary(
            "rendezvousing_crew" if stage in {"forming", "rendezvous"} else "committing_property_crime",
            plan_kind=_text(active_plan.get("kind")),
            method_label=_text(active_plan.get("method_label")),
            property_name=_text((target_prop or {}).get("name")),
            organization_name=_text(active_plan.get("organization_name")),
        )
        if focus:
            state.current_target_x = int(focus[0])
            state.current_target_y = int(focus[1])
            state.current_target_z = int(focus[2])
    elif isinstance(opportunistic_target, dict):
        state.current_target_property_id = _text(opportunistic_target.get("property_id")) or None
        state.current_target_ground_item_id = _text(opportunistic_target.get("target_ground_item_id")) or None
        if float(confidence) < 0.46:
            state.current_target_x = _safe_int(opportunistic_target.get("casing_x"), default=opportunistic_target.get("x", 0))
            state.current_target_y = _safe_int(opportunistic_target.get("casing_y"), default=opportunistic_target.get("y", 0))
            state.current_target_z = _safe_int(opportunistic_target.get("casing_z"), default=opportunistic_target.get("z", 0))
        else:
            state.current_target_x = _safe_int(opportunistic_target.get("x"), default=0)
            state.current_target_y = _safe_int(opportunistic_target.get("y"), default=0)
            state.current_target_z = _safe_int(opportunistic_target.get("z"), default=0)
        state.current_activity_kind = "opportunistic_theft"
        state.current_activity_stage = "targeting"
        state.current_activity_summary = criminal_activity_summary(
            "committing_property_crime",
            property_name=_text(opportunistic_target.get("property_name")),
        )

    if affiliation_target:
        target = affiliation_target[0]
        state.current_affiliation_target_property_id = _text(target.get("property_id")) or None
        state.current_affiliation_organization_eid = _safe_int(target.get("organization_eid"), default=0) or None

    return state
