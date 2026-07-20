"""Shared stale opportunity snapshots and actor-held lead helpers."""

from __future__ import annotations

from collections import deque

from engine.visibility import has_line_of_sight as _has_line_of_sight
from game.components import AI, NPCOpportunityKnowledge, Position
from game.movement_runtime import _can_step_transition_for, _movement_planning_context
from game.property_runtime import (
    property_covering as _property_covering,
    property_entry_position as _property_entry_position,
    property_focus_position as _property_focus_position,
    property_is_public as _property_is_public,
    property_is_storefront as _property_is_storefront,
    site_services_for_property as _site_services_for_property,
)

_SURFACE_CACHE_TICKS = 60
_CHUNK_SNAPSHOT_CACHE_TICKS = 300
_MAX_LEADS_PER_KIND = 4
_DEFAULT_STALE_AFTER_TICKS = 90
_DEFAULT_EXPIRES_TICKS = 360
_REFRESH_ENTITY_KEY = "__entity__"

_MEDICAL_ARCHETYPES = frozenset({
    "backroom_clinic",
    "pharmacy",
    "biotech_clinic",
    "field_hospital",
    "tide_station",
    "herbalist_camp",
    "herbalist_shop",
})
_SALE_ARCHETYPES = frozenset({
    "pawn_shop",
    "chop_shop",
    "junk_market",
    "salvage_camp",
    "breaker_yard",
    "drydock_yard",
    "thrift_store",
    "backroom_market",
})
_RESIDENTIAL_ARCHETYPES = frozenset({
    "house",
    "apartment",
    "tenement",
    "hotel",
    "flophouse",
    "ruin_shelter",
    "barracks",
    "beacon_house",
    "survey_post",
    "field_camp",
    "ranger_hut",
})
_WORKLIKE_ARCHETYPES = frozenset({
    "warehouse",
    "contractor_office",
    "courier_office",
    "office",
    "tower",
    "factory",
    "garage",
    "workshop",
    "bank",
    "brokerage",
    "store",
    "clinic",
    "biotech_clinic",
})
_LODGING_SERVICES = frozenset({"rest", "shelter"})
_PATH_ROUTINE_STATES = frozenset({
    "selling_scavenged",
    "seeking_medical_aid",
    "seeking_safe_spot",
    "seeking_shelter",
    "patrolling",
    "working",
    "lounging",
    "socializing",
    "resting",
})


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _text(value):
    return str(value or "").strip()


def _normalize_lead_kinds(lead_kinds=None, lead_kind=None):
    values = []
    if lead_kinds is not None:
        iterable = lead_kinds if isinstance(lead_kinds, (tuple, list, set, frozenset)) else (lead_kinds,)
    elif lead_kind is not None:
        iterable = (lead_kind,)
    else:
        iterable = ()
    for raw in iterable:
        kind = _text(raw).lower()
        if kind and kind not in values:
            values.append(kind)
    return tuple(values)


def _runtime_state(sim):
    state = getattr(sim, "opportunity_runtime_state", None)
    if not isinstance(state, dict):
        state = {
            "surface_cache": {},
            "chunk_cache": {},
            "will_rethink": {},
        }
        sim.opportunity_runtime_state = state
    state.setdefault("surface_cache", {})
    state.setdefault("chunk_cache", {})
    state.setdefault("will_rethink", {})
    return state


def npc_opportunity_knowledge(sim, actor_eid, *, create=False):
    if actor_eid is None:
        return None
    knowledges = sim.ecs.get(NPCOpportunityKnowledge)
    knowledge = knowledges.get(actor_eid)
    if knowledge is None and create:
        knowledge = NPCOpportunityKnowledge()
        sim.ecs.add(actor_eid, knowledge)
    return knowledge


def schedule_will_rethink(sim, actor_eid, *, current_tick=None, delay_ticks=0):
    if actor_eid is None:
        return 0
    if current_tick is None:
        current_tick = _int(getattr(sim, "tick", 0), 0)
    next_tick = int(current_tick) + max(0, _int(delay_ticks, 0))
    _runtime_state(sim).setdefault("will_rethink", {})[_int(actor_eid)] = next_tick
    return next_tick


def will_rethink_due(sim, actor_eid, *, current_tick=None):
    if actor_eid is None:
        return True
    if current_tick is None:
        current_tick = _int(getattr(sim, "tick", 0), 0)
    next_tick = _runtime_state(sim).setdefault("will_rethink", {}).get(_int(actor_eid))
    if next_tick is None:
        return True
    return int(current_tick) >= _int(next_tick, 0)


def clear_will_rethink(sim, actor_eid=None):
    state = _runtime_state(sim).setdefault("will_rethink", {})
    if actor_eid is None:
        state.clear()
        return
    state.pop(_int(actor_eid), None)


def _normalize_chunk(chunk):
    if not isinstance(chunk, (tuple, list)) or len(chunk) < 2:
        return None
    try:
        return (int(chunk[0]), int(chunk[1]))
    except (TypeError, ValueError):
        return None


def _lead_key(lead):
    if not isinstance(lead, dict):
        return ""
    property_id = _text(lead.get("property_id"))
    if property_id:
        return f"property:{property_id}"
    target = lead.get("target")
    if isinstance(target, (tuple, list)) and len(target) >= 3:
        return f"target:{_int(target[0])},{_int(target[1])},{_int(target[2])}"
    opportunity_tag = _text(lead.get("opportunity_tag"))
    if opportunity_tag:
        return f"tag:{opportunity_tag}"
    service_id = _text(lead.get("service_id"))
    if service_id:
        return f"service:{service_id}"
    return ""


def _clean_expired_leads(knowledge, *, current_tick):
    if knowledge is None:
        return
    leads_by_kind = getattr(knowledge, "leads_by_kind", None)
    if not isinstance(leads_by_kind, dict):
        knowledge.leads_by_kind = {}
        leads_by_kind = knowledge.leads_by_kind
    for kind, rows in tuple(leads_by_kind.items()):
        cleaned = []
        for row in tuple(rows or ()):
            if not isinstance(row, dict):
                continue
            expires_tick = _int(row.get("expires_tick"), 0)
            if expires_tick > 0 and int(current_tick) > expires_tick:
                continue
            cleaned.append(row)
        if cleaned:
            leads_by_kind[kind] = cleaned
        else:
            leads_by_kind.pop(kind, None)
    cooldowns = getattr(knowledge, "lead_cooldowns", None)
    if not isinstance(cooldowns, dict):
        knowledge.lead_cooldowns = {}
        cooldowns = knowledge.lead_cooldowns
    for kind, rows in tuple(cooldowns.items()):
        if not isinstance(rows, dict):
            cooldowns.pop(kind, None)
            continue
        cleaned = {
            key: tick
            for key, tick in rows.items()
            if _int(tick, 0) > int(current_tick)
        }
        if cleaned:
            cooldowns[kind] = cleaned
        else:
            cooldowns.pop(kind, None)


def property_surface_snapshot(sim, prop, *, current_tick=None):
    if not isinstance(prop, dict):
        return None
    property_id = _text(prop.get("id"))
    if not property_id:
        return None
    if current_tick is None:
        current_tick = _int(getattr(sim, "tick", 0), 0)
    cache = _runtime_state(sim).setdefault("surface_cache", {})
    cached = cache.get(property_id)
    if isinstance(cached, dict) and _int(cached.get("expires_tick"), 0) >= int(current_tick):
        return cached.get("snapshot")

    focus = _property_focus_position(prop)
    if not isinstance(focus, (tuple, list)) or len(focus) < 3:
        fx = _int(prop.get("x"), 0)
        fy = _int(prop.get("y"), 0)
        fz = _int(prop.get("z"), 0)
        focus = (fx, fy, fz)
    else:
        focus = (_int(focus[0]), _int(focus[1]), _int(focus[2]))
    services = tuple(sorted({
        _text(service).lower()
        for service in tuple(_site_services_for_property(prop) or ())
        if _text(service)
    }))
    metadata = prop.get("metadata", {}) if isinstance(prop.get("metadata"), dict) else {}
    archetype = _text(metadata.get("archetype")).lower()
    is_public = bool(_property_is_public(prop))
    is_storefront = bool(_property_is_storefront(prop))
    owner_tag = _text(prop.get("owner_tag")).lower() or None
    kind = _text(prop.get("kind")).lower() or None
    access_level = _text(prop.get("access_level")).lower() or None
    chunk = (
        sim.chunk_coords(int(focus[0]), int(focus[1]))
        if hasattr(sim, "chunk_coords")
        else (int(focus[0]), int(focus[1]))
    )
    if _normalize_chunk(chunk) is None:
        chunk = (0, 0)
    else:
        chunk = _normalize_chunk(chunk)

    opportunity_tags = set()
    if set(services).intersection(_LODGING_SERVICES) or archetype in {"hotel", "flophouse"}:
        opportunity_tags.add("lodging")
    if archetype in _MEDICAL_ARCHETYPES or "medical" in services or "clinic" in archetype:
        opportunity_tags.add("medical")
    if archetype in _SALE_ARCHETYPES:
        opportunity_tags.add("scavenged_sale")
    if archetype in _RESIDENTIAL_ARCHETYPES or "lodging" in opportunity_tags:
        opportunity_tags.add("local_housing")
    if archetype in _WORKLIKE_ARCHETYPES or is_storefront or "medical" in opportunity_tags or "scavenged_sale" in opportunity_tags:
        opportunity_tags.add("local_workplace")
    if (
        "lodging" in opportunity_tags
        or "medical" in opportunity_tags
        or (kind == "building" and not is_storefront)
    ):
        opportunity_tags.add("safe_spot")

    world_hour = 12
    hour_reader = getattr(sim, "world_hour", None)
    if callable(hour_reader):
        world_hour = _int(hour_reader(), 12)
    elif hasattr(sim, "world") and hasattr(sim.world, "hour"):
        world_hour = _int(getattr(sim.world, "hour", 12), 12)
    open_hint = True
    if not is_public and not is_storefront and "lodging" not in opportunity_tags and "medical" not in opportunity_tags:
        open_hint = world_hour >= 7 and world_hour <= 20

    snapshot = {
        "property_id": property_id,
        "property_name": _text(prop.get("name") or property_id) or "site",
        "target": focus,
        "chunk": chunk,
        "kind": kind,
        "archetype": archetype,
        "owner_eid": prop.get("owner_eid"),
        "owner_tag": owner_tag,
        "access_level": access_level,
        "public_hint": bool(is_public),
        "storefront_hint": bool(is_storefront),
        "open_hint": bool(open_hint),
        "services": services,
        "opportunity_tags": tuple(sorted(opportunity_tags)),
        "quality_hint": 0.6 + (0.1 if is_public else 0.0) + (0.08 if is_storefront else 0.0),
        "risk_hint": 0.35 if is_public else (0.45 if is_storefront else 0.62),
    }
    cache[property_id] = {
        "expires_tick": int(current_tick) + _SURFACE_CACHE_TICKS,
        "snapshot": snapshot,
    }
    return snapshot


def nearby_opportunity_rows(sim, pos, *, radius, lead_kind=None, lead_kinds=None, current_tick=None):
    if pos is None:
        return []
    try:
        search_radius = max(1, int(radius))
    except (TypeError, ValueError):
        search_radius = 1
    rows = []
    wanted = set(_normalize_lead_kinds(lead_kinds, lead_kind))
    for prop in sim.properties_in_radius(int(pos.x), int(pos.y), int(pos.z), r=search_radius):
        row = property_surface_snapshot(sim, prop, current_tick=current_tick)
        if not isinstance(row, dict):
            continue
        target = row.get("target")
        if not isinstance(target, (tuple, list)) or len(target) < 3 or _int(target[2]) != _int(pos.z):
            continue
        if wanted and not (wanted & set(row.get("opportunity_tags", ()) or ())):
            continue
        rows.append(row)
    return rows


def _note_refresh_tick(knowledge, *, current_tick, lead_kinds=()):
    if knowledge is None:
        return
    if not isinstance(knowledge.last_refresh_tick_by_kind, dict):
        knowledge.last_refresh_tick_by_kind = {}
    knowledge.last_refresh_tick_by_kind[_REFRESH_ENTITY_KEY] = int(current_tick)
    for kind in tuple(lead_kinds or ()):
        clean_kind = _text(kind).lower()
        if clean_kind:
            knowledge.last_refresh_tick_by_kind[clean_kind] = int(current_tick)


def _recent_refresh_active(knowledge, *, current_tick, recency_ticks=0, lead_kinds=()):
    if knowledge is None:
        return False
    try:
        threshold = max(0, int(recency_ticks))
    except (TypeError, ValueError):
        threshold = 0
    if threshold <= 0:
        return False
    stamps = getattr(knowledge, "last_refresh_tick_by_kind", None)
    if not isinstance(stamps, dict):
        return False
    keys = [_REFRESH_ENTITY_KEY]
    keys.extend(tuple(lead_kinds or ()))
    latest = None
    for key in keys:
        if key not in stamps:
            continue
        tick = _int(stamps.get(key), -1)
        if latest is None or tick > latest:
            latest = tick
    if latest is None:
        return False
    return int(current_tick) - int(latest) < threshold


def opportunity_snapshot_for_chunk(sim, chunk, *, current_tick=None):
    chunk = _normalize_chunk(chunk)
    if chunk is None:
        return None
    if current_tick is None:
        current_tick = _int(getattr(sim, "tick", 0), 0)
    cache = _runtime_state(sim).setdefault("chunk_cache", {})
    cached = cache.get(chunk)
    if isinstance(cached, dict) and _int(cached.get("expires_tick"), 0) >= int(current_tick):
        return cached.get("snapshot")

    world = getattr(sim, "world", None)
    descriptor = world.overworld_descriptor(chunk[0], chunk[1]) if world is not None else {}
    world_chunk = world.get_chunk(chunk[0], chunk[1]) if world is not None else {}
    if not isinstance(descriptor, dict):
        descriptor = {}
    if not isinstance(world_chunk, dict):
        world_chunk = {}
    district = world_chunk.get("district", {}) if isinstance(world_chunk.get("district", {}), dict) else {}
    area_type = _text(district.get("area_type") or descriptor.get("area_type") or "city").lower() or "city"
    wealth = _int(district.get("wealth"), 5)
    security = _int(district.get("security_level"), 5)
    crime = _int(district.get("crime_rate"), 5)
    path_kind = _text(descriptor.get("path")).lower()
    loaded_property_ids = []
    tag_counts = {}
    seen_property_ids = set()

    def _ingest_prop(prop_id, prop):
        if not isinstance(prop, dict):
            return
        clean_id = _text(prop_id) or _text(prop.get("id"))
        if not clean_id or clean_id in seen_property_ids:
            return
        seen_property_ids.add(clean_id)
        loaded_property_ids.append(clean_id)
        row = property_surface_snapshot(sim, prop, current_tick=current_tick)
        for tag in tuple((row or {}).get("opportunity_tags", ()) or ()):
            tag_counts[tag] = _int(tag_counts.get(tag), 0) + 1

    for record in tuple(getattr(sim, "chunk_property_records", {}).get(chunk, ()) or ()):
        prop_id = _text((record or {}).get("id"))
        _ingest_prop(prop_id, sim.properties.get(prop_id))
    for prop_id, prop in tuple(getattr(sim, "properties", {}).items()):
        if not isinstance(prop, dict):
            continue
        try:
            prop_chunk = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
        except (TypeError, ValueError):
            continue
        if prop_chunk != chunk:
            continue
        _ingest_prop(prop_id, prop)
    score = (wealth * 0.28) + (security * 0.48) - (crime * 0.34)
    score += float(tag_counts.get("local_housing", 0) or 0) * 0.75
    score += float(tag_counts.get("local_workplace", 0) or 0) * 0.7
    score += float(tag_counts.get("medical", 0) or 0) * 0.18
    score += float(tag_counts.get("lodging", 0) or 0) * 0.25
    if path_kind in {"road", "freeway"}:
        score += 0.3
    snapshot = {
        "chunk": chunk,
        "area_type": area_type,
        "wealth": wealth,
        "security": security,
        "crime": crime,
        "path_kind": path_kind,
        "loaded_property_ids": tuple(loaded_property_ids),
        "tag_counts": dict(tag_counts),
        "score": float(score),
    }
    cache[chunk] = {
        "expires_tick": int(current_tick) + _CHUNK_SNAPSHOT_CACHE_TICKS,
        "snapshot": snapshot,
    }
    return snapshot


def remember_opportunity_lead(
    sim,
    actor_eid,
    lead_kind,
    lead,
    *,
    source_kind="surface_snapshot",
    stale_after_ticks=None,
    expires_ticks=None,
):
    knowledge = npc_opportunity_knowledge(sim, actor_eid, create=True)
    if knowledge is None or not isinstance(lead, dict):
        return None
    current_tick = _int(getattr(sim, "tick", 0), 0)
    _clean_expired_leads(knowledge, current_tick=current_tick)
    kind = _text(lead_kind).lower()
    if not kind:
        return None
    stale_after_ticks = _int(stale_after_ticks, _DEFAULT_STALE_AFTER_TICKS)
    expires_ticks = _int(expires_ticks, _DEFAULT_EXPIRES_TICKS)
    row = dict(lead)
    row["lead_kind"] = kind
    row["property_id"] = _text(row.get("property_id")) or None
    row["target"] = tuple(row.get("target", ())) if isinstance(row.get("target"), (tuple, list)) else row.get("target")
    row["chunk"] = _normalize_chunk(row.get("chunk")) or (
        sim.chunk_coords(_int(row["target"][0]), _int(row["target"][1]))
        if isinstance(row.get("target"), tuple) and len(row.get("target")) >= 2 and hasattr(sim, "chunk_coords")
        else None
    )
    row["service_id"] = _text(row.get("service_id")) or None
    row["opportunity_tag"] = _text(row.get("opportunity_tag")) or None
    row["confidence"] = max(0.0, min(1.0, _float(row.get("confidence"), 0.55)))
    row["source_kind"] = _text(source_kind or row.get("source_kind")).lower() or "surface_snapshot"
    row["learned_tick"] = current_tick
    row["stale_after_tick"] = current_tick + max(1, stale_after_ticks)
    row["expires_tick"] = current_tick + max(2, expires_ticks)
    row["verification_required"] = bool(row.get("verification_required", True))

    leads = list(getattr(knowledge, "leads_by_kind", {}).get(kind, []) or [])
    lead_key = _lead_key(row)
    leads = [existing for existing in leads if _lead_key(existing) != lead_key]
    leads.append(row)
    leads.sort(
        key=lambda existing: (
            _float(existing.get("score"), 0.0),
            _float(existing.get("confidence"), 0.0),
            _int(existing.get("learned_tick"), 0),
        ),
        reverse=True,
    )
    knowledge.leads_by_kind[kind] = leads[:_MAX_LEADS_PER_KIND]
    knowledge.last_refresh_tick_by_kind[kind] = current_tick
    return row


def best_opportunity_lead(sim, actor_eid, lead_kind, *, current_tick=None):
    knowledge = npc_opportunity_knowledge(sim, actor_eid, create=False)
    if knowledge is None:
        return None
    if current_tick is None:
        current_tick = _int(getattr(sim, "tick", 0), 0)
    _clean_expired_leads(knowledge, current_tick=current_tick)
    kind = _text(lead_kind).lower()
    if not kind:
        return None
    leads = list(getattr(knowledge, "leads_by_kind", {}).get(kind, []) or [])
    cooldowns = getattr(knowledge, "lead_cooldowns", {}) or {}
    kind_cooldowns = cooldowns.get(kind, {}) if isinstance(cooldowns, dict) else {}
    viable = []
    for lead in leads:
        if not isinstance(lead, dict):
            continue
        lead_key = _lead_key(lead)
        if _int(kind_cooldowns.get(lead_key), 0) > int(current_tick):
            continue
        viable.append(lead)
    if not viable:
        return None
    return dict(viable[0])


def rehydrate_opportunity_knowledge(
    sim,
    *,
    actor_eids=None,
    center=None,
    radius=18,
    search_radius=10,
    current_tick=None,
    reason="pause",
    force_routine_rethink=False,
    lead_kinds=None,
    skip_recent_ticks=0,
):
    if current_tick is None:
        current_tick = _int(getattr(sim, "tick", 0), 0)
    positions = sim.ecs.get(Position)
    ais = sim.ecs.get(AI)
    reason_key = _text(reason).lower() or "pause"
    try:
        radius = max(1, int(radius))
    except (TypeError, ValueError):
        radius = 18
    try:
        search_radius = max(1, int(search_radius))
    except (TypeError, ValueError):
        search_radius = 10
    try:
        skip_recent_ticks = max(0, int(skip_recent_ticks))
    except (TypeError, ValueError):
        skip_recent_ticks = 0
    wanted_kinds = _normalize_lead_kinds(lead_kinds)

    center_pos = None
    if isinstance(center, (tuple, list)) and len(center) >= 3:
        center_pos = (_int(center[0]), _int(center[1]), _int(center[2]))

    candidate_ids = []
    if actor_eids is not None:
        seen = set()
        for raw_eid in tuple(actor_eids or ()):
            eid = _int(raw_eid, 0)
            if eid <= 0 or eid in seen:
                continue
            seen.add(eid)
            candidate_ids.append(eid)
    else:
        for eid, ai in ais.items():
            if not isinstance(ai, AI):
                continue
            role = _text(getattr(ai, "role", "")).lower()
            if role == "wildlife":
                continue
            candidate_ids.append(int(eid))

    actors = 0
    leads = 0
    skipped_recent = 0
    warmed_chunks = set()
    for eid in candidate_ids:
        pos = positions.get(eid)
        if pos is None:
            continue
        if center_pos is not None:
            if _int(pos.z) != center_pos[2]:
                continue
            if abs(_int(pos.x) - center_pos[0]) + abs(_int(pos.y) - center_pos[1]) > radius:
                continue
        knowledge = npc_opportunity_knowledge(sim, eid, create=False)
        if skip_recent_ticks > 0 and _recent_refresh_active(
            knowledge,
            current_tick=current_tick,
            recency_ticks=skip_recent_ticks,
            lead_kinds=wanted_kinds,
        ):
            skipped_recent += 1
            continue
        chunk = sim.chunk_coords(_int(pos.x), _int(pos.y)) if hasattr(sim, "chunk_coords") else None
        if chunk is not None:
            warmed_chunks.add((_int(chunk[0]), _int(chunk[1])))
            opportunity_snapshot_for_chunk(sim, chunk, current_tick=current_tick)
        rows = nearby_opportunity_rows(
            sim,
            pos,
            radius=search_radius,
            lead_kinds=wanted_kinds,
            current_tick=current_tick,
        )
        actors += 1
        if force_routine_rethink:
            clear_will_rethink(sim, eid)
        refreshed_kinds = set(wanted_kinds)
        for row in rows:
            tags = tuple(row.get("opportunity_tags", ()) or ())
            for tag in tags:
                if wanted_kinds and tag not in wanted_kinds:
                    continue
                remembered = remember_opportunity_lead(
                    sim,
                    eid,
                    tag,
                    row,
                    source_kind=f"rehydrate_{reason_key}",
                    stale_after_ticks=180,
                    expires_ticks=720,
                )
                if remembered is not None:
                    leads += 1
                    refreshed_kinds.add(tag)
        knowledge = npc_opportunity_knowledge(sim, eid, create=True)
        _note_refresh_tick(
            knowledge,
            current_tick=current_tick,
            lead_kinds=refreshed_kinds,
        )
    if center_pos is not None and hasattr(sim, "chunk_coords"):
        center_chunk = sim.chunk_coords(center_pos[0], center_pos[1])
        opportunity_snapshot_for_chunk(sim, center_chunk, current_tick=current_tick)
        warmed_chunks.add((_int(center_chunk[0]), _int(center_chunk[1])))
    return {
        "actors": actors,
        "leads": leads,
        "chunks": len(warmed_chunks),
        "reason": reason_key,
        "skipped_recent": skipped_recent,
        "lead_kinds": wanted_kinds,
    }


def rehydrate_entity_knowledge(
    sim,
    actor_eid,
    *,
    center=None,
    radius=18,
    search_radius=10,
    current_tick=None,
    reason="entity_refresh",
    force_routine_rethink=False,
    lead_kinds=None,
    skip_recent_ticks=0,
):
    eid = _int(actor_eid, 0)
    if eid <= 0:
        return None
    pos = sim.ecs.get(Position).get(eid)
    if pos is not None:
        center = (_int(pos.x), _int(pos.y), _int(pos.z))
    elif not (isinstance(center, (tuple, list)) and len(center) >= 3):
        return None
    summary = rehydrate_opportunity_knowledge(
        sim,
        actor_eids=(eid,),
        center=center,
        radius=radius,
        search_radius=search_radius,
        current_tick=current_tick,
        reason=reason,
        force_routine_rethink=force_routine_rethink,
        lead_kinds=lead_kinds,
        skip_recent_ticks=skip_recent_ticks,
    )
    if isinstance(summary, dict):
        summary["actor_eid"] = eid
    return summary


def mark_opportunity_failure(sim, actor_eid, lead_kind, *, lead=None, cooldown_ticks=180, reason="failed_verification"):
    knowledge = npc_opportunity_knowledge(sim, actor_eid, create=True)
    if knowledge is None:
        return
    current_tick = _int(getattr(sim, "tick", 0), 0)
    kind = _text(lead_kind).lower()
    if not kind:
        return
    lead = dict(lead or {})
    key = _lead_key(lead)
    if key:
        if not isinstance(knowledge.failed_target_keys, dict):
            knowledge.failed_target_keys = {}
        state = knowledge.failed_target_keys.get(key)
        count = 0
        if isinstance(state, dict):
            count = _int(state.get("count"), 0)
        knowledge.failed_target_keys[key] = {
            "tick": current_tick,
            "count": count + 1,
            "reason": _text(reason).lower() or "failed_verification",
            "lead_kind": kind,
        }
        if not isinstance(knowledge.lead_cooldowns, dict):
            knowledge.lead_cooldowns = {}
        knowledge.lead_cooldowns.setdefault(kind, {})
        knowledge.lead_cooldowns[kind][key] = current_tick + max(1, _int(cooldown_ticks, 180))
    leads = list(getattr(knowledge, "leads_by_kind", {}).get(kind, []) or [])
    if key:
        leads = [row for row in leads if _lead_key(row) != key]
    knowledge.leads_by_kind[kind] = leads


def note_opportunity_success(sim, actor_eid, lead_kind, *, lead=None):
    knowledge = npc_opportunity_knowledge(sim, actor_eid, create=True)
    if knowledge is None:
        return
    kind = _text(lead_kind).lower()
    if not kind:
        return
    key = _lead_key(lead or {})
    if key and isinstance(getattr(knowledge, "lead_cooldowns", None), dict):
        kind_cooldowns = knowledge.lead_cooldowns.get(kind)
        if isinstance(kind_cooldowns, dict):
            kind_cooldowns.pop(key, None)


def remember_active_target(sim, actor_eid, state, target, *, property_id=None, lead_kind=None, timeout_ticks=120):
    knowledge = npc_opportunity_knowledge(sim, actor_eid, create=True)
    if knowledge is None:
        return None
    state_key = _text(state).lower()
    if not state_key:
        return None
    current_tick = _int(getattr(sim, "tick", 0), 0)
    row = {
        "state": state_key,
        "target": tuple(target) if isinstance(target, (tuple, list)) else target,
        "property_id": _text(property_id) or None,
        "lead_kind": _text(lead_kind).lower() or None,
        "expires_tick": current_tick + max(1, _int(timeout_ticks, 120)),
    }
    previous = knowledge.active_targets.get(state_key)
    if isinstance(previous, dict):
        path_goal = previous.get("path_goal")
        if path_goal == row.get("target"):
            row["path_nodes"] = previous.get("path_nodes")
            row["path_goal"] = previous.get("path_goal")
    knowledge.active_targets[state_key] = row
    return row


def active_target(sim, actor_eid, state, *, current_tick=None):
    knowledge = npc_opportunity_knowledge(sim, actor_eid, create=False)
    if knowledge is None:
        return None
    state_key = _text(state).lower()
    if not state_key:
        return None
    row = getattr(knowledge, "active_targets", {}).get(state_key)
    if not isinstance(row, dict):
        return None
    if current_tick is None:
        current_tick = _int(getattr(sim, "tick", 0), 0)
    if _int(row.get("expires_tick"), 0) < int(current_tick):
        knowledge.active_targets.pop(state_key, None)
        return None
    return row


def clear_active_target(sim, actor_eid, state=None):
    knowledge = npc_opportunity_knowledge(sim, actor_eid, create=False)
    if knowledge is None:
        return
    if state is None:
        knowledge.active_targets.clear()
        return
    state_key = _text(state).lower()
    if state_key:
        knowledge.active_targets.pop(state_key, None)


def invalidate_active_target_path(sim, actor_eid, state):
    row = active_target(sim, actor_eid, state)
    if not isinstance(row, dict):
        return
    row.pop("path_nodes", None)
    row.pop("path_goal", None)


def _reconstruct_path(parents, best):
    chain = []
    cursor = best
    while cursor is not None:
        chain.append(cursor)
        cursor = parents.get(cursor)
    chain.reverse()
    return chain


def _build_path_nodes(sim, eid, sx, sy, tx, ty, z, *, max_nodes=512, planning_context=None):
    start = (int(sx), int(sy))
    goal = (int(tx), int(ty))
    if start == goal:
        return [start]
    queue = deque([start])
    parents = {start: None}
    best = start
    best_score = abs(int(sx) - int(tx)) + abs(int(sy) - int(ty))
    while queue and len(parents) < max_nodes:
        cx, cy = queue.popleft()
        if (cx, cy) == goal:
            best = goal
            break
        for dx, dy in (
            (0, -1),
            (1, 0),
            (0, 1),
            (-1, 0),
            (-1, -1),
            (1, -1),
            (-1, 1),
            (1, 1),
        ):
            nx = cx + dx
            ny = cy + dy
            node = (nx, ny)
            if node in parents:
                continue
            step_ok, _ = _can_step_transition_for(
                sim,
                moving_eid=eid,
                from_x=cx,
                from_y=cy,
                to_x=nx,
                to_y=ny,
                z=z,
                planning_context=planning_context,
            )
            if not step_ok:
                continue
            parents[node] = (cx, cy)
            queue.append(node)
            score = abs(nx - int(tx)) + abs(ny - int(ty))
            if score < best_score:
                best = node
                best_score = score
    if best == start:
        return None
    return _reconstruct_path(parents, best)


def _greedy_visible_step(sim, eid, sx, sy, tx, ty, z, *, planning_context=None):
    if not _has_line_of_sight(sim, int(sx), int(sy), int(z), int(tx), int(ty), int(z)):
        return None
    candidates = []
    for dx, dy in (
        (0, -1),
        (1, 0),
        (0, 1),
        (-1, 0),
        (-1, -1),
        (1, -1),
        (-1, 1),
        (1, 1),
    ):
        nx = int(sx) + dx
        ny = int(sy) + dy
        if (nx, ny) == (int(sx), int(sy)):
            continue
        score = abs(nx - int(tx)) + abs(ny - int(ty))
        candidates.append((score, nx, ny))
    candidates.sort(key=lambda row: row[0])
    for _score, nx, ny in candidates:
        step_ok, _ = _can_step_transition_for(
            sim,
            moving_eid=eid,
            from_x=int(sx),
            from_y=int(sy),
            to_x=int(nx),
            to_y=int(ny),
            z=int(z),
            planning_context=planning_context,
        )
        if step_ok:
            return (int(nx), int(ny))
    return None


def _routine_movement_goal(sim, pos, target):
    if pos is None or not isinstance(target, (tuple, list)) or len(target) < 3:
        return None
    goal = (_int(target[0]), _int(target[1]), _int(target[2]))
    actor_prop = _property_covering(sim, _int(pos.x), _int(pos.y), _int(pos.z))
    target_prop = _property_covering(sim, goal[0], goal[1], goal[2])
    if not isinstance(target_prop, dict):
        return goal
    actor_prop_id = _text((actor_prop or {}).get("id")).lower()
    target_prop_id = _text(target_prop.get("id")).lower()
    if actor_prop_id and actor_prop_id == target_prop_id:
        return goal
    entry = _property_entry_position(target_prop)
    if isinstance(entry, (tuple, list)) and len(entry) >= 3:
        return (_int(entry[0]), _int(entry[1]), _int(entry[2]))
    return goal


def next_active_target_step(sim, actor_eid, state, pos, target, *, max_nodes=512):
    state_key = _text(state).lower()
    if state_key not in _PATH_ROUTINE_STATES:
        return None
    if pos is None or not isinstance(target, (tuple, list)) or len(target) < 3:
        return None
    row = remember_active_target(sim, actor_eid, state_key, target, timeout_ticks=180)
    if not isinstance(row, dict):
        return None
    goal = _routine_movement_goal(sim, pos, target)
    if goal is None:
        return None
    current_xy = (_int(pos.x), _int(pos.y))
    planning_context = _movement_planning_context(sim, actor_eid)
    direct_step = _greedy_visible_step(
        sim,
        actor_eid,
        _int(pos.x),
        _int(pos.y),
        goal[0],
        goal[1],
        _int(pos.z),
        planning_context=planning_context,
    )
    if direct_step is not None:
        row["path_nodes"] = None
        row["path_goal"] = goal
        return direct_step
    path_nodes = row.get("path_nodes")
    if isinstance(path_nodes, list) and row.get("path_goal") == goal:
        normalized = [
            (_int(node[0]), _int(node[1]))
            for node in tuple(path_nodes or ())
            if isinstance(node, (tuple, list)) and len(node) >= 2
        ]
        if current_xy in normalized:
            index = normalized.index(current_xy)
            if index + 1 < len(normalized):
                next_xy = normalized[index + 1]
                row["path_nodes"] = normalized[index:]
                return next_xy
    rebuilt = _build_path_nodes(
        sim,
        actor_eid,
        _int(pos.x),
        _int(pos.y),
        goal[0],
        goal[1],
        _int(pos.z),
        max_nodes=max_nodes,
        planning_context=planning_context,
    )
    if not rebuilt or len(rebuilt) < 2:
        row["path_nodes"] = None
        row["path_goal"] = goal
        return None
    row["path_nodes"] = rebuilt
    row["path_goal"] = goal
    return rebuilt[1]
