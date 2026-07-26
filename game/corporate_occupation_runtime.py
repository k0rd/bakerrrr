"""Active corporate neighborhood control built on durable corporate presence.

Presence answers *where* a corporation has accumulated real holdings.  This
module answers what those holdings do to the street: visible surveillance,
shared branch scrutiny, captured supply terms, labor pressure, security
details, and physical counterplay.  None of those effects replaces ownership,
trade, organization watchlists, or ordinary property damage; it translates a
corporate footprint into inputs those systems already understand.
"""

from __future__ import annotations

from hashlib import blake2b
import random

from engine.events import Event
from engine.systems import System
from engine.visibility import has_line_of_sight
from game.bodyguard_runtime import create_bodyguard_detail_for_principal
from game.components import NPCTraits, PlayerModeState, Position, Vitality, WeaponLoadout
from game.corporate_expansion_runtime import corporate_expansion_profile
from game.corporate_presence import (
    corporate_neighborhood_presence_rows,
    corporate_organization_for_property,
)
from game.organization_production import organization_manufacturing_identity
from game.organization_reputation import organization_snapshot
from game.organizations import (
    actor_org_memberships,
    assign_actor_organization,
    link_property_organization,
    organization_policy_snapshot,
    organization_profile,
    property_org_links,
    record_organization_watchlist,
)
from game.property_runtime import property_focus_position
from game.run_pressure import apply_pressure_delta, pressure_snapshot
from game.system_support.security_disguise_runtime import _security_fixture_is_online
from game.weapons import weapon_by_id


CORPORATE_OCCUPATION_SCHEMA_VERSION = 1
CORPORATE_OCCUPATION_REFRESH_INTERVAL = 120
CORPORATE_SENSOR_SCAN_COOLDOWN = 5
CORPORATE_SCRUTINY_DECAY_DELAY = 42
CORPORATE_SCRUTINY_DECAY_PER_REFRESH = 0.16
CORPORATE_SENSOR_REPAIR_MIN_TICKS = 520
CORPORATE_SENSOR_REPAIR_MAX_TICKS = 880
CORPORATE_DISRUPTION_TICKS = 780
CORPORATE_MAX_HISTORY = 80

CORPORATE_SENSOR_COUNTS = {
    0: 0,
    1: 0,
    2: 1,
    3: 2,
    4: 3,
}

CORPORATE_DOCTRINES = {
    "compliance_blanket": {
        "key": "credential_grid",
        "label": "Credential Grid",
        "surveillance": 0.9,
        "exclusivity": 0.42,
        "labor_pressure": 0.48,
        "enforcement": 0.84,
        "public_read": "credential checks and standardized security repeat from frontage to frontage",
    },
    "lifestyle_saturation": {
        "key": "consumer_capture",
        "label": "Consumer Capture",
        "surveillance": 0.52,
        "exclusivity": 0.94,
        "labor_pressure": 0.58,
        "enforcement": 0.46,
        "public_read": "preferred products, preferred payment, and preferred employers are becoming the same choice",
    },
    "connected_corridor": {
        "key": "signal_dragnet",
        "label": "Signal Dragnet",
        "surveillance": 1.0,
        "exclusivity": 0.7,
        "labor_pressure": 0.5,
        "enforcement": 0.64,
        "public_read": "street hardware is sharing one branded signal and one memory of who passes through",
    },
    "redevelopment_campaign": {
        "key": "asset_control",
        "label": "Asset Control",
        "surveillance": 0.62,
        "exclusivity": 0.76,
        "labor_pressure": 0.86,
        "enforcement": 0.72,
        "public_read": "leases, staffing, deliveries, and security are being made to answer to one redevelopment plan",
    },
}

CORPORATE_TRADE_ACTION_PRESSURE = {
    "service_exclusivity": 0.34,
    "supply_pressure": 0.42,
    "pricing_pressure": 0.38,
    "fake_inspection": 0.2,
    "intimidation": 0.24,
    "hostile_rumor": 0.18,
}

CORPORATE_LABOR_ACTION_PRESSURE = {
    "staff_poaching": 0.48,
    "fake_inspection": 0.2,
    "intimidation": 0.38,
    "hostile_rumor": 0.18,
    "supply_pressure": 0.12,
}


CORPORATE_LIVED_BENEFITS = {
    "credential_grid": (
        "Once your credentials clear, their branches stop making every door a negotiation.",
        "Their security answers when a branch calls, and people with a clean badge get the benefit of that.",
        "The rules repeat from one branch to the next, which is useful when you are tired of guessing what a door wants.",
    ),
    "consumer_capture": (
        "Their counters get the deep deliveries first, so the thing you came for is more likely to be on the shelf.",
        "They put work, shopping, and services close enough together that people can get through a day without crossing the city.",
        "If you already buy what they sell, the preferred terms can make the whole block feel easier.",
    ),
    "signal_dragnet": (
        "One credential carries across their branches, and the next counter already knows the useful part of your record.",
        "Their connected counters are quick about recognizing regulars and keeping routine business moving.",
        "When the network likes you, their doors and service desks waste very little of your time.",
    ),
    "asset_control": (
        "Their signs are where the steadier shifts and fuller deliveries tend to collect.",
        "They can keep several counters supplied and staffed when a lone owner would be scrambling.",
        "For somebody who needs predictable work more than independence, they make a convincing offer.",
    ),
}


CORPORATE_LIVED_COSTS = {
    "credential_grid": (
        "One mark on your record can follow you from one branch door to the next.",
        "The same rules that make entry predictable make a bad credential hard to escape.",
        "People without the right badge spend a lot of time proving they belong in places they already use.",
    ),
    "consumer_capture": (
        "Their cheap, full counters leave independent shelves paying more for less.",
        "The discounts get less friendly once their competitors have been starved out.",
        "Work, shopping, and payment all start pointing at the same logo, which makes walking away expensive.",
    ),
    "signal_dragnet": (
        "Their cameras share a memory, so trouble at one frontage can close doors somewhere else.",
        "A harmless mistake stops being local once every branch can remember it.",
        "The network is convenient right up until it decides you are the part that does not belong.",
    ),
    "asset_control": (
        "They lean on leases, deliveries, and staff until independence costs more than surrender.",
        "A business can keep its old name while every decision behind the counter starts answering to them.",
        "The steadier shifts come with fewer places left to work outside their plan.",
    ),
}


def _text(value):
    return str(value or "").strip()


def _key(value):
    return _text(value).lower().replace(" ", "_")


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


def _clamp(value, low=0.0, high=1.0):
    return max(float(low), min(float(high), float(value)))


def _hash_int(*parts):
    payload = "|".join(_text(part) for part in parts).encode("utf-8")
    return int.from_bytes(blake2b(payload, digest_size=12).digest(), "big")


def _metadata(prop):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        prop["metadata"] = metadata
    return metadata


def _property_chunk(sim, prop):
    if not isinstance(prop, dict):
        return None
    chunk = _metadata(prop).get("chunk")
    if isinstance(chunk, (tuple, list)) and len(chunk) >= 2:
        try:
            return (int(chunk[0]), int(chunk[1]))
        except (TypeError, ValueError):
            pass
    try:
        return tuple(sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0))))
    except (AttributeError, TypeError, ValueError):
        return None


def _occupation_state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    state = traits.get("corporate_occupation")
    if not isinstance(state, dict):
        state = {}
        traits["corporate_occupation"] = state
    state["schema_version"] = CORPORATE_OCCUPATION_SCHEMA_VERSION
    if not isinstance(state.get("neighborhoods"), dict):
        state["neighborhoods"] = {}
    if not isinstance(state.get("history"), list):
        state["history"] = []
    if len(state["history"]) > CORPORATE_MAX_HISTORY:
        del state["history"][:-CORPORATE_MAX_HISTORY]
    return state


def ensure_corporate_occupation_state(sim):
    return _occupation_state(sim)


def _presence_key(presence):
    return _text((presence or {}).get("presence_key"))


def _active_disruptions(row, *, current_tick):
    active = []
    for raw in tuple((row or {}).get("disruptions", ()) or ()):
        if not isinstance(raw, dict):
            continue
        expires_tick = _safe_int(raw.get("expires_tick"), 0)
        if expires_tick > 0 and expires_tick < int(current_tick):
            continue
        amount = max(0.0, _safe_float(raw.get("amount"), 0.0))
        if amount <= 0.0:
            continue
        active.append({**raw, "amount": round(amount, 3)})
    active.sort(key=lambda entry: (_safe_int(entry.get("created_tick"), 0), _text(entry.get("disruption_key"))))
    return active[-24:]


def _effective_tier(raw_tier, disruption):
    raw_tier = max(0, min(4, _safe_int(raw_tier, 0)))
    if raw_tier <= 1:
        return raw_tier
    lost = int(max(0.0, float(disruption)) // 1.0)
    return max(1, raw_tier - lost)


def corporate_occupation_doctrine(sim, corporate_org_eid, presence=None):
    campaign = _key((presence or {}).get("campaign_kind")) or "redevelopment_campaign"
    base = dict(CORPORATE_DOCTRINES.get(campaign, CORPORATE_DOCTRINES["redevelopment_campaign"]))
    expansion = corporate_expansion_profile(sim, corporate_org_eid)
    aggression = _clamp(expansion.get("aggression", 0.22))
    deniable = _clamp(expansion.get("deniable_pressure", 0.12))
    tags = {_key(tag) for tag in tuple(expansion.get("tags", ()) or ()) if _key(tag)}
    base["surveillance"] = round(_clamp(base["surveillance"] + ((aggression - 0.22) * 0.16), 0.2, 1.0), 3)
    base["exclusivity"] = round(_clamp(base["exclusivity"] + (0.08 if "hostile_takeover" in tags else 0.0), 0.2, 1.0), 3)
    base["labor_pressure"] = round(_clamp(base["labor_pressure"] + (0.1 if "interest:labor" in tags else 0.0), 0.2, 1.0), 3)
    base["enforcement"] = round(_clamp(base["enforcement"] + ((aggression - 0.22) * 0.34), 0.2, 1.0), 3)
    base["deniable_pressure"] = round(deniable, 3)
    base["force_style"] = "contractor_screen" if deniable >= 0.34 else "branded_security"
    return base


def _sensor_candidates(sim, presence):
    properties = getattr(sim, "properties", {})
    candidates = []
    for property_id in tuple(presence.get("branded_fixture_ids", ()) or ()) + tuple(presence.get("anchor_property_ids", ()) or ()):
        prop = properties.get(_text(property_id))
        if isinstance(prop, dict):
            focus = property_focus_position(prop)
            if focus is None:
                focus = (prop.get("x", 0), prop.get("y", 0), prop.get("z", 0))
            try:
                candidates.append((int(focus[0]), int(focus[1]), int(focus[2]), _text(prop.get("id"))))
            except (TypeError, ValueError, IndexError):
                continue
    return candidates


def _sensor_position(sim, presence, sensor_index, reserved):
    chunk = tuple(presence.get("chunk", ()))
    sources = _sensor_candidates(sim, presence)
    if not sources:
        return None
    offsets = ((0, -1), (1, 0), (0, 1), (-1, 0), (1, -1), (-1, -1), (1, 1), (-1, 1), (0, 0))
    seed = _hash_int(getattr(sim, "seed", 0), presence.get("corporate_org_eid"), chunk, sensor_index, "street-optic")
    rng = random.Random(seed)
    rng.shuffle(sources)
    shuffled_offsets = list(offsets)
    rng.shuffle(shuffled_offsets)
    anchor_index = getattr(sim, "property_anchor_index", {})
    for sx, sy, sz, source_id in sources:
        for dx, dy in shuffled_offsets:
            x, y, z = sx + dx, sy + dy, sz
            cell = (x, y, z)
            if cell in reserved:
                continue
            try:
                if tuple(sim.chunk_coords(x, y)) != chunk:
                    continue
            except (AttributeError, TypeError, ValueError):
                continue
            tile = getattr(sim, "tilemap", None).tile_at(x, y, z) if getattr(sim, "tilemap", None) is not None else None
            if tile is not None and not bool(getattr(tile, "walkable", False)):
                continue
            anchored = tuple(anchor_index.get(cell, ()) or ())
            if any(
                not bool(_metadata(getattr(sim, "properties", {}).get(prop_id)).get("corporate_surveillance_node"))
                for prop_id in anchored
                if isinstance(getattr(sim, "properties", {}).get(prop_id), dict)
            ):
                continue
            return (x, y, z, source_id)
    return None


def _create_sensor(sim, presence, doctrine, sensor_index, reserved):
    position = _sensor_position(sim, presence, sensor_index, reserved)
    if position is None:
        return None
    x, y, z, source_property_id = position
    org_eid = _safe_int(presence.get("corporate_org_eid"), 0)
    identity = organization_manufacturing_identity(sim, org_eid)
    brand = _text(identity.get("manufacturer")) or _text(presence.get("corporate_org_name")) or "Corporate"
    motif = _text(identity.get("product_motif")) or "house mark"
    radius = max(5, min(11, 4 + _safe_int(presence.get("tier"), 1) + int(round(doctrine.get("surveillance", 0.5) * 2.0))))
    metadata = {
        "archetype": "wall_camera",
        "fixture_type": "wall_camera",
        "interaction_role": "camera_target",
        "display_glyph": "c",
        "display_color": _text(identity.get("primary_render_key")) or "property_asset",
        "display_description": (
            f"A {brand} street optic watches the corridor from a {motif} housing. "
            "Its cabling disappears into the neighborhood's sponsored infrastructure."
        ),
        "public": False,
        "access_level": "restricted",
        "attackable": True,
        "damageable": True,
        "fixture_integrity_max": 24 + (_safe_int(presence.get("tier"), 1) * 4),
        "fixture_integrity": 24 + (_safe_int(presence.get("tier"), 1) * 4),
        "fixture_armor": 3 + int(round(doctrine.get("enforcement", 0.5) * 3.0)),
        "fixture_usable": True,
        "detection_radius": radius,
        "corporate_surveillance_node": True,
        "corporate_surveillance_active": True,
        "corporate_occupation_key": _presence_key(presence),
        "corporate_organization_eid": org_eid,
        "corporate_doctrine_key": doctrine.get("key"),
        "corporate_sensor_index": int(sensor_index),
        "corporate_sensor_source_property_id": source_property_id,
        "linked_property_id": source_property_id,
        "chunk": tuple(presence.get("chunk", ())),
    }
    property_id = sim.register_property(
        name=f"{brand} Street Optic",
        kind="asset",
        x=x,
        y=y,
        z=z,
        owner_tag=_text(presence.get("corporate_org_key")) or "corporate",
        metadata=metadata,
    )
    prop = sim.properties.get(property_id)
    if isinstance(prop, dict):
        link_property_organization(
            sim,
            prop,
            organization_eid=org_eid,
            link_kind="oversight",
            primary=False,
            active=True,
        )
    return property_id


def _sync_sensors(sim, presence, row, doctrine, *, materialize):
    properties = getattr(sim, "properties", {})
    org_eid = _safe_int(presence.get("corporate_org_eid"), 0)
    chunk = tuple(presence.get("chunk", ()))
    existing_ids = []
    for property_id in tuple(row.get("sensor_property_ids", ()) or ()):
        prop = properties.get(_text(property_id))
        if isinstance(prop, dict) and bool(_metadata(prop).get("corporate_surveillance_node")):
            existing_ids.append(_text(property_id))
    for prop in properties.values():
        metadata = _metadata(prop)
        if not bool(metadata.get("corporate_surveillance_node")):
            continue
        if _safe_int(metadata.get("corporate_organization_eid"), 0) != org_eid:
            continue
        if tuple(metadata.get("chunk", ())) != chunk:
            continue
        property_id = _text(prop.get("id"))
        if property_id and property_id not in existing_ids:
            existing_ids.append(property_id)

    desired = CORPORATE_SENSOR_COUNTS.get(max(0, min(4, _safe_int(presence.get("tier"), 0))), 0)
    reserved = {
        (_safe_int(properties[property_id].get("x"), 0), _safe_int(properties[property_id].get("y"), 0), _safe_int(properties[property_id].get("z"), 0))
        for property_id in existing_ids
        if isinstance(properties.get(property_id), dict)
    }
    if materialize:
        while len(existing_ids) < desired:
            created = _create_sensor(sim, presence, doctrine, len(existing_ids), reserved)
            if not created:
                break
            existing_ids.append(created)
            prop = properties.get(created)
            if isinstance(prop, dict):
                reserved.add((_safe_int(prop.get("x"), 0), _safe_int(prop.get("y"), 0), _safe_int(prop.get("z"), 0)))

    for index, property_id in enumerate(existing_ids):
        prop = properties.get(property_id)
        if not isinstance(prop, dict):
            continue
        metadata = _metadata(prop)
        metadata["corporate_surveillance_active"] = bool(index < desired)
        metadata["corporate_occupation_key"] = _presence_key(presence)
        metadata["corporate_doctrine_key"] = doctrine.get("key")
    return tuple(existing_ids)


def sync_corporate_occupation(sim, presence, *, materialize=True):
    if not isinstance(presence, dict) or not _presence_key(presence):
        return None
    state = ensure_corporate_occupation_state(sim)
    key = _presence_key(presence)
    previous = state["neighborhoods"].get(key)
    previous = dict(previous) if isinstance(previous, dict) else {}
    now = _safe_int(getattr(sim, "tick", 0), 0)
    disruptions = _active_disruptions(previous, current_tick=now)
    disruption = round(sum(_safe_float(entry.get("amount"), 0.0) for entry in disruptions), 3)
    raw_tier = _safe_int(presence.get("tier"), 0)
    doctrine = corporate_occupation_doctrine(sim, presence.get("corporate_org_eid"), presence)
    row = {
        "occupation_key": key,
        "presence_key": key,
        "corporate_org_eid": _safe_int(presence.get("corporate_org_eid"), 0),
        "corporate_org_key": _text(presence.get("corporate_org_key")),
        "corporate_org_name": _text(presence.get("corporate_org_name")) or "Corporate organization",
        "chunk": tuple(presence.get("chunk", ())),
        "raw_tier": raw_tier,
        "raw_tier_key": _key(presence.get("tier_key")),
        "raw_tier_label": _text(presence.get("tier_label")),
        "effective_tier": _effective_tier(raw_tier, disruption),
        "doctrine": doctrine,
        "disruption": disruption,
        "disruptions": disruptions,
        "sensor_property_ids": tuple(previous.get("sensor_property_ids", ()) or ()),
        "scrutiny": dict(previous.get("scrutiny", {})) if isinstance(previous.get("scrutiny"), dict) else {},
        "security_principal_eid": previous.get("security_principal_eid"),
        "security_guard_eids": tuple(previous.get("security_guard_eids", ()) or ()),
        "security_last_deployed_tick": _safe_int(previous.get("security_last_deployed_tick"), 0),
        "created_tick": _safe_int(previous.get("created_tick"), now),
        "last_update_tick": now,
        "active": bool(raw_tier > 0),
    }
    row["sensor_property_ids"] = _sync_sensors(sim, presence, row, doctrine, materialize=materialize)
    state["neighborhoods"][key] = row
    for property_id in tuple(presence.get("anchor_property_ids", ()) or ()):
        prop = getattr(sim, "properties", {}).get(property_id)
        if not isinstance(prop, dict):
            continue
        metadata = _metadata(prop)
        metadata["corporate_occupation"] = {
            "organization_eid": row["corporate_org_eid"],
            "organization_name": row["corporate_org_name"],
            "doctrine_key": doctrine.get("key"),
            "doctrine_label": doctrine.get("label"),
            "effective_tier": row["effective_tier"],
            "public_read": doctrine.get("public_read"),
        }
    return dict(row)


def sync_all_corporate_occupations(sim, *, materialize=True):
    rows = []
    for presence in corporate_neighborhood_presence_rows(sim, active_only=True):
        row = sync_corporate_occupation(sim, presence, materialize=materialize)
        if row:
            rows.append(row)
    return tuple(rows)


def corporate_occupation_rows(sim, *, corporate_org_eid=None, chunk=None, active_only=True):
    state = ensure_corporate_occupation_state(sim)
    wanted_org = _safe_int(corporate_org_eid, 0) if corporate_org_eid is not None else 0
    wanted_chunk = tuple(chunk) if isinstance(chunk, (tuple, list)) and len(chunk) >= 2 else None
    rows = []
    for raw in state.get("neighborhoods", {}).values():
        if not isinstance(raw, dict):
            continue
        row = dict(raw)
        if active_only and not bool(row.get("active", True)):
            continue
        if wanted_org > 0 and _safe_int(row.get("corporate_org_eid"), 0) != wanted_org:
            continue
        if wanted_chunk is not None and tuple(row.get("chunk", ())) != wanted_chunk:
            continue
        rows.append(row)
    rows.sort(key=lambda row: (-_safe_int(row.get("effective_tier"), 0), -_safe_int(row.get("raw_tier"), 0), -_safe_float((row.get("doctrine") or {}).get("exclusivity"), 0.0), _text(row.get("corporate_org_name")).lower()))
    return tuple(rows)


def _ensure_occupation_rows_for_chunk(sim, chunk):
    rows = corporate_occupation_rows(sim, chunk=chunk)
    if rows:
        return rows
    for presence in corporate_neighborhood_presence_rows(sim, chunk=chunk, active_only=True):
        sync_corporate_occupation(sim, presence, materialize=False)
    return corporate_occupation_rows(sim, chunk=chunk)


def dominant_corporate_occupation_for_property(sim, prop):
    chunk = _property_chunk(sim, prop)
    if chunk is None:
        return None
    rows = _ensure_occupation_rows_for_chunk(sim, chunk)
    return dict(rows[0]) if rows else None


def _property_aligned_with(sim, prop, corporate_org_eid):
    if not isinstance(prop, dict):
        return False
    direct = corporate_organization_for_property(sim, prop)
    if direct is not None and int(direct) == int(corporate_org_eid):
        return True
    for link in property_org_links(sim, prop, active_only=True):
        policy = organization_policy_snapshot(sim, link.get("organization_eid")) or {}
        root = _safe_int(policy.get("root_organization_eid"), link.get("organization_eid") or 0)
        if root == int(corporate_org_eid):
            return True
    return False


def _active_target_pressure(sim, prop, corporate_org_eid, pressure_map):
    state = getattr(sim, "world_traits", {}).get("corporate_expansion", {})
    actions = state.get("actions", {}) if isinstance(state, dict) else {}
    now = _safe_int(getattr(sim, "tick", 0), 0)
    property_id = _text((prop or {}).get("id"))
    total = 0.0
    kinds = []
    for raw in actions.values() if isinstance(actions, dict) else ():
        if not isinstance(raw, dict):
            continue
        if _safe_int(raw.get("corporate_org_eid"), 0) != int(corporate_org_eid):
            continue
        if _text(raw.get("property_id")) != property_id:
            continue
        if _safe_int(raw.get("expires_tick"), now + 1) < now:
            continue
        kind = _key(raw.get("action_kind"))
        amount = _safe_float(pressure_map.get(kind), 0.0)
        if amount <= 0.0:
            continue
        total += amount
        kinds.append(kind)
    return min(0.8, total), tuple(sorted(set(kinds)))


def corporate_trade_terms_for_property(sim, prop):
    row = dominant_corporate_occupation_for_property(sim, prop)
    neutral = {
        "active": False,
        "corporate_org_eid": None,
        "brand": "",
        "aligned": False,
        "effective_tier": 0,
        "buy_price_mult": 1.0,
        "stock_mult": 1.0,
        "sell_ratio_mult": 1.0,
        "note": "",
        "pressure_actions": (),
    }
    if not isinstance(row, dict) or _safe_int(row.get("effective_tier"), 0) < 2:
        return neutral
    org_eid = _safe_int(row.get("corporate_org_eid"), 0)
    doctrine = dict(row.get("doctrine") or {})
    aligned = _property_aligned_with(sim, prop, org_eid)
    tier_factor = max(0.0, float(_safe_int(row.get("effective_tier"), 0) - 1))
    action_pressure, action_kinds = _active_target_pressure(sim, prop, org_eid, CORPORATE_TRADE_ACTION_PRESSURE)
    exclusivity = _clamp(doctrine.get("exclusivity", 0.5))
    intensity = min(3.2, (tier_factor * exclusivity) + action_pressure)
    identity = organization_manufacturing_identity(sim, org_eid)
    brand = _text(identity.get("manufacturer")) or _text(row.get("corporate_org_name"))
    if aligned:
        stock_mult = 1.0 + min(0.34, 0.07 * intensity)
        price_mult = 1.0 + (min(0.08, 0.025 * intensity) if doctrine.get("key") == "consumer_capture" else -min(0.06, 0.018 * intensity))
        sell_ratio_mult = 1.0 - min(0.08, 0.02 * intensity)
        note = f"{brand} contract stock is running deep here"
    else:
        stock_mult = 1.0 - min(0.42, 0.1 * intensity)
        price_mult = 1.0 + min(0.2, 0.048 * intensity)
        sell_ratio_mult = 1.0 - min(0.24, 0.055 * intensity)
        note = f"{brand} distribution terms are squeezing independent shelves"
    return {
        "active": True,
        "corporate_org_eid": org_eid,
        "corporate_org_name": row.get("corporate_org_name"),
        "brand": brand,
        "aligned": aligned,
        "effective_tier": _safe_int(row.get("effective_tier"), 0),
        "doctrine_key": doctrine.get("key"),
        "buy_price_mult": round(max(0.8, min(1.25, price_mult)), 4),
        "stock_mult": round(max(0.5, min(1.4, stock_mult)), 4),
        "sell_ratio_mult": round(max(0.7, min(1.12, sell_ratio_mult)), 4),
        "note": note,
        "pressure_actions": action_kinds,
    }


def corporate_labor_terms_for_property(sim, prop):
    row = dominant_corporate_occupation_for_property(sim, prop)
    if not isinstance(row, dict) or _safe_int(row.get("effective_tier"), 0) < 2:
        return {"active": False, "premium_units": 0, "brand": "", "note": ""}
    org_eid = _safe_int(row.get("corporate_org_eid"), 0)
    if _property_aligned_with(sim, prop, org_eid):
        return {"active": True, "premium_units": 0, "brand": "", "note": "", "aligned": True}
    doctrine = dict(row.get("doctrine") or {})
    action_pressure, action_kinds = _active_target_pressure(sim, prop, org_eid, CORPORATE_LABOR_ACTION_PRESSURE)
    intensity = ((_safe_int(row.get("effective_tier"), 0) - 1) * _clamp(doctrine.get("labor_pressure", 0.5))) + action_pressure
    premium_units = max(1, min(4, int(round(intensity))))
    identity = organization_manufacturing_identity(sim, org_eid)
    brand = _text(identity.get("manufacturer")) or _text(row.get("corporate_org_name"))
    return {
        "active": True,
        "aligned": False,
        "corporate_org_eid": org_eid,
        "brand": brand,
        "premium_units": premium_units,
        "note": f"{brand} is pulling wages and dependable workers toward its own counters",
        "pressure_actions": action_kinds,
    }


def record_corporate_disruption(
    sim,
    *,
    corporate_org_eid,
    chunk,
    amount,
    reason,
    source_property_id="",
    source_eid=None,
    expires_tick=None,
):
    rows = corporate_occupation_rows(sim, corporate_org_eid=corporate_org_eid, chunk=chunk)
    if not rows:
        for presence in corporate_neighborhood_presence_rows(sim, corporate_org_eid=corporate_org_eid, chunk=chunk):
            sync_corporate_occupation(sim, presence, materialize=False)
        rows = corporate_occupation_rows(sim, corporate_org_eid=corporate_org_eid, chunk=chunk)
    if not rows:
        return None
    state = ensure_corporate_occupation_state(sim)
    row = dict(state["neighborhoods"].get(rows[0]["occupation_key"], rows[0]))
    now = _safe_int(getattr(sim, "tick", 0), 0)
    if expires_tick is None:
        expires_tick = now + CORPORATE_DISRUPTION_TICKS
    disruption_key = f"{_key(reason)}:{_text(source_property_id) or '-'}:{now}"
    disruptions = _active_disruptions(row, current_tick=now)
    disruptions.append({
        "disruption_key": disruption_key,
        "amount": round(max(0.0, _safe_float(amount, 0.0)), 3),
        "reason": _key(reason),
        "source_property_id": _text(source_property_id) or None,
        "source_eid": source_eid,
        "created_tick": now,
        "expires_tick": _safe_int(expires_tick, now + CORPORATE_DISRUPTION_TICKS),
    })
    row["disruptions"] = disruptions[-24:]
    row["disruption"] = round(sum(_safe_float(entry.get("amount"), 0.0) for entry in row["disruptions"]), 3)
    before_tier = _safe_int(row.get("effective_tier"), row.get("raw_tier", 0))
    row["effective_tier"] = _effective_tier(row.get("raw_tier", 0), row["disruption"])
    row["last_update_tick"] = now
    state["neighborhoods"][row["occupation_key"]] = row
    history = state["history"]
    history.append({
        "tick": now,
        "kind": "disruption",
        "organization_eid": int(corporate_org_eid),
        "chunk": tuple(chunk),
        "reason": _key(reason),
        "source_property_id": _text(source_property_id) or None,
        "effective_tier_before": before_tier,
        "effective_tier": row["effective_tier"],
    })
    if len(history) > CORPORATE_MAX_HISTORY:
        del history[:-CORPORATE_MAX_HISTORY]
    profile = organization_profile(sim, corporate_org_eid)
    sim.emit(Event(
        "corporate_occupation_disrupted",
        eid=source_eid,
        organization_eid=int(corporate_org_eid),
        organization_name=_text(getattr(profile, "name", "")) or row.get("corporate_org_name"),
        chunk=tuple(chunk),
        reason=_key(reason),
        source_property_id=_text(source_property_id) or None,
        disruption=round(row["disruption"], 3),
        effective_tier_before=before_tier,
        effective_tier=row["effective_tier"],
    ))
    return dict(row)


def _sensor_is_live(sim, prop):
    if not isinstance(prop, dict):
        return False
    metadata = _metadata(prop)
    if not bool(metadata.get("corporate_surveillance_node")) or not bool(metadata.get("corporate_surveillance_active", True)):
        return False
    if bool(metadata.get("fixture_broken")) or not bool(metadata.get("fixture_usable", True)):
        return False
    return bool(_security_fixture_is_online(sim, prop, tick=_safe_int(getattr(sim, "tick", 0), 0)))


def _player_weapon_scrutiny(sim, player_eid):
    loadout = sim.ecs.get(WeaponLoadout).get(player_eid)
    weapon_id = loadout.current_weapon() if loadout and callable(getattr(loadout, "current_weapon", None)) else None
    if not weapon_id:
        return 0.0
    weapon = weapon_by_id(weapon_id)
    tags = {_key(tag) for tag in tuple(weapon.get("tags", ()) or ()) if _key(tag)}
    if tags.intersection({"firearm", "gun", "explosive", "launcher"}):
        return 0.22
    if tags.intersection({"melee", "weapon"}):
        return 0.08
    return 0.04


def _scrutiny_action(scrutiny, threshold, org_heat, effective_tier):
    if org_heat >= 46 and effective_tier >= 4 and scrutiny >= threshold:
        return "deny_entry"
    if (org_heat >= 18 or scrutiny >= threshold * 2.0) and effective_tier >= 3:
        return "deny_service"
    if scrutiny >= threshold:
        return "watch"
    return ""


def process_corporate_surveillance_for_player(sim, player_eid):
    pos = sim.ecs.get(Position).get(player_eid)
    if pos is None:
        return ()
    chunk = tuple(sim.chunk_coords(int(pos.x), int(pos.y)))
    rows = _ensure_occupation_rows_for_chunk(sim, chunk)
    if not rows:
        return ()
    state = ensure_corporate_occupation_state(sim)
    now = _safe_int(getattr(sim, "tick", 0), 0)
    results = []
    pressure = pressure_snapshot(sim)
    mode = sim.ecs.get(PlayerModeState).get(player_eid)
    for snapshot in rows:
        if _safe_int(snapshot.get("effective_tier"), 0) < 2:
            continue
        row = state["neighborhoods"].get(snapshot["occupation_key"])
        if not isinstance(row, dict):
            continue
        scrutiny_state = row.setdefault("scrutiny", {})
        subject_key = str(int(player_eid))
        subject = scrutiny_state.get(subject_key)
        subject = dict(subject) if isinstance(subject, dict) else {}
        last_scan = _safe_int(subject.get("last_scan_tick"), -10_000)
        if now - last_scan < CORPORATE_SENSOR_SCAN_COOLDOWN:
            continue
        seen_by = []
        properties = getattr(sim, "properties", {})
        for property_id in tuple(row.get("sensor_property_ids", ()) or ()):
            prop = properties.get(property_id)
            if not _sensor_is_live(sim, prop):
                continue
            radius = max(1, _safe_int(_metadata(prop).get("detection_radius"), 6))
            sx, sy, sz = _safe_int(prop.get("x"), 0), _safe_int(prop.get("y"), 0), _safe_int(prop.get("z"), 0)
            if sz != int(pos.z) or abs(sx - int(pos.x)) + abs(sy - int(pos.y)) > radius:
                continue
            if not has_line_of_sight(sim, sx, sy, sz, int(pos.x), int(pos.y), int(pos.z)):
                continue
            seen_by.append(prop)
        if not seen_by:
            continue

        org_eid = _safe_int(row.get("corporate_org_eid"), 0)
        reputation = organization_snapshot(sim, organization_eid=org_eid, ensure=True) or {}
        org_heat = max(0, _safe_int(reputation.get("heat"), 0))
        standing = _safe_float(reputation.get("standing"), 0.0)
        doctrine = dict(row.get("doctrine") or {})
        increment = 0.08 + (_clamp(doctrine.get("surveillance", 0.5)) * 0.12)
        increment += _player_weapon_scrutiny(sim, player_eid)
        if mode is not None and bool(getattr(mode, "sneak", False)):
            increment += 0.13
        increment += min(0.16, _safe_int(pressure.get("attention"), 0) / 625.0)
        increment += min(0.32, org_heat / 180.0)
        increment *= 1.0 - min(0.38, max(0.0, standing) * 0.3)
        value = max(0.0, _safe_float(subject.get("value"), 0.0)) + increment
        threshold = 0.82 + (max(0.0, standing) * 0.34)
        previous_action = _key(subject.get("action"))
        action = _scrutiny_action(value, threshold, org_heat, _safe_int(row.get("effective_tier"), 0))
        subject.update({
            "subject_eid": int(player_eid),
            "value": round(value, 3),
            "threshold": round(threshold, 3),
            "action": action or previous_action,
            "last_scan_tick": now,
            "last_seen_tick": now,
            "sensor_property_ids": tuple(_text(prop.get("id")) for prop in seen_by),
        })
        scrutiny_state[subject_key] = subject
        row["scrutiny"] = scrutiny_state
        state["neighborhoods"][row["occupation_key"]] = row
        duration = {"watch": 260, "deny_service": 420, "deny_entry": 560}.get(action, 240)
        action_changed = bool(action and action != previous_action)
        watchlist_refresh_due = bool(
            action
            and now - _safe_int(subject.get("last_watchlist_tick"), -10_000) >= max(80, duration // 2)
        )
        if action_changed or watchlist_refresh_due:
            watch = record_organization_watchlist(
                sim,
                organization_eid=org_eid,
                entry_key=f"corporate_sensor_{player_eid}",
                subject_eid=player_eid,
                action=action,
                reason="corporate_sensor_scrutiny",
                source_kind="corporate_occupation",
                source_eid=None,
                target_scope="organization",
                tags=("corporate_occupation", doctrine.get("key"), "surveillance"),
                priority={"watch": 62, "deny_service": 76, "deny_entry": 88}.get(action, 60),
                effective_tick=now,
                expires_tick=now + duration,
                active=True,
            )
            subject["last_watchlist_tick"] = now
            scrutiny_state[subject_key] = subject
            if action_changed and action in {"deny_service", "deny_entry"}:
                apply_pressure_delta(
                    sim,
                    delta=1 if action == "deny_service" else 2,
                    source="corporate_surveillance",
                    reason=f"{row.get('corporate_org_key') or org_eid}:{action}",
                    source_event="corporate_scrutiny_changed",
                )
            if action_changed:
                first_sensor = seen_by[0]
                sim.emit(Event(
                    "corporate_scrutiny_changed",
                    eid=player_eid,
                    organization_eid=org_eid,
                    organization_name=row.get("corporate_org_name"),
                    brand=(organization_manufacturing_identity(sim, org_eid).get("manufacturer") or row.get("corporate_org_name")),
                    chunk=chunk,
                    action=action,
                    previous_action=previous_action,
                    scrutiny=round(value, 3),
                    sensor_property_id=first_sensor.get("id"),
                    sensor_name=first_sensor.get("name"),
                    watchlist_entry_id=(watch or {}).get("entry_id"),
                    x=int(pos.x),
                    y=int(pos.y),
                    z=int(pos.z),
                ))
        results.append({"organization_eid": org_eid, "action": action, "scrutiny": round(value, 3), "seen_by": tuple(prop.get("id") for prop in seen_by)})
    return tuple(results)


def _actor_matches_corporate_root(sim, actor_eid, root_org_eid):
    for membership in actor_org_memberships(sim, actor_eid, active_only=True):
        policy = organization_policy_snapshot(sim, membership.get("organization_eid")) or {}
        root = _safe_int(policy.get("root_organization_eid"), membership.get("organization_eid") or 0)
        if root == int(root_org_eid):
            return True
    return False


def corporate_lived_dialogue_context(sim, actor_eid, *, workplace_prop=None, current_prop=None):
    """Return public, lived corporate pressure suitable for NPC conversation.

    This deliberately exposes consequences rather than hidden organization
    scores.  The same occupation row that drives stock, labor, surveillance,
    and security supplies both the attraction and the cost; speaker traits and
    affiliation only shape how candidly those facts are framed.
    """
    candidates = []

    def _add_candidate(prop, source):
        if not isinstance(prop, dict):
            return
        row = dominant_corporate_occupation_for_property(sim, prop)
        if not isinstance(row, dict) or _safe_int(row.get("effective_tier"), 0) < 2:
            return
        candidates.append((source, row))

    _add_candidate(workplace_prop, "workplace")
    _add_candidate(current_prop, "current")
    pos = sim.ecs.get(Position).get(actor_eid) if actor_eid is not None else None
    if pos is not None:
        chunk = tuple(sim.chunk_coords(int(pos.x), int(pos.y)))
        for row in _ensure_occupation_rows_for_chunk(sim, chunk):
            if isinstance(row, dict) and _safe_int(row.get("effective_tier"), 0) >= 2:
                candidates.append(("local", row))

    unique = {}
    for source, row in candidates:
        key = _text(row.get("occupation_key"))
        if not key:
            continue
        org_eid = _safe_int(row.get("corporate_org_eid"), 0)
        member = bool(actor_eid is not None and org_eid > 0 and _actor_matches_corporate_root(sim, actor_eid, org_eid))
        workplace_aligned = bool(
            isinstance(workplace_prop, dict)
            and org_eid > 0
            and _property_aligned_with(sim, workplace_prop, org_eid)
        )
        source_rank = {"workplace": 3, "current": 2, "local": 1}.get(source, 0)
        score = (100 if member else 0) + (40 if workplace_aligned else 0) + (source_rank * 5) + _safe_int(row.get("effective_tier"), 0)
        previous = unique.get(key)
        if previous is None or score > previous[0]:
            unique[key] = (score, source, row, member, workplace_aligned)
    if not unique:
        return {"available": False}

    _score, source, row, member, workplace_aligned = max(
        unique.values(),
        key=lambda entry: (entry[0], _text(entry[2].get("corporate_org_name")).lower()),
    )
    org_eid = _safe_int(row.get("corporate_org_eid"), 0)
    doctrine = dict(row.get("doctrine") or {})
    doctrine_key = _key(doctrine.get("key")) or "asset_control"
    identity = organization_manufacturing_identity(sim, org_eid)
    brand = _text(identity.get("manufacturer")) or _text(row.get("corporate_org_name")) or "the corporation"

    if member:
        viewpoint = "member"
    elif workplace_aligned:
        viewpoint = "affiliate"
    elif isinstance(workplace_prop, dict):
        viewpoint = "independent"
    else:
        viewpoint = "local"

    traits = sim.ecs.get(NPCTraits).get(actor_eid) if actor_eid is not None else None
    loyalty = _clamp(getattr(traits, "loyalty", 0.5))
    discipline = _clamp(getattr(traits, "discipline", 0.5))
    empathy = _clamp(getattr(traits, "empathy", 0.5))
    support = (0.58 if member else (0.38 if workplace_aligned else 0.18))
    support += (loyalty - 0.5) * 0.42
    support += (discipline - 0.5) * 0.2
    support -= (empathy - 0.5) * (0.2 if viewpoint in {"independent", "local"} else 0.08)
    support = _clamp(support)
    stance = "loyal" if support >= 0.58 else ("critical" if support <= 0.24 else "conflicted")

    benefits = list(CORPORATE_LIVED_BENEFITS.get(doctrine_key, CORPORATE_LIVED_BENEFITS["asset_control"]))
    costs = list(CORPORATE_LIVED_COSTS.get(doctrine_key, CORPORATE_LIVED_COSTS["asset_control"]))
    trade_prop = workplace_prop if isinstance(workplace_prop, dict) else current_prop
    if isinstance(trade_prop, dict):
        trade_terms = corporate_trade_terms_for_property(sim, trade_prop)
        if trade_terms.get("active") and trade_terms.get("aligned") and float(trade_terms.get("stock_mult", 1.0) or 1.0) > 1.0:
            benefits.append(f"{brand} contract counters usually have more stock to choose from.")
        elif trade_terms.get("active") and not trade_terms.get("aligned"):
            costs.append(f"Independent counters around {brand} territory pay more for thinner deliveries.")
        labor_terms = corporate_labor_terms_for_property(sim, trade_prop)
        if labor_terms.get("active") and not labor_terms.get("aligned") and int(labor_terms.get("premium_units", 0) or 0) > 0:
            costs.append(f"Independent employers have to bid harder just to keep workers from leaving for {brand}.")

    def _ordered_facts(values, salt):
        cleaned = tuple(dict.fromkeys(_text(value) for value in values if _text(value)))
        if len(cleaned) <= 1:
            return cleaned
        start = _hash_int(getattr(sim, "seed", 0), actor_eid, row.get("occupation_key"), salt) % len(cleaned)
        return cleaned[start:] + cleaned[:start]

    benefits = _ordered_facts(benefits, "benefits")
    costs = _ordered_facts(costs, "costs")
    public_read = _text(doctrine.get("public_read"))
    local_here = bool(
        pos is not None
        and tuple(row.get("chunk", ())) == tuple(sim.chunk_coords(int(pos.x), int(pos.y)))
    )
    return {
        "available": bool(benefits and costs),
        "organization_eid": org_eid,
        "organization_name": _text(row.get("corporate_org_name")) or brand,
        "brand": brand,
        "occupation_key": _text(row.get("occupation_key")),
        "effective_tier": _safe_int(row.get("effective_tier"), 0),
        "tier_label": _text(row.get("raw_tier_label")),
        "doctrine_key": doctrine_key,
        "doctrine_label": _text(doctrine.get("label")),
        "public_read": public_read,
        "source": source,
        "local_here": local_here,
        "viewpoint": viewpoint,
        "stance": stance,
        "member": member,
        "workplace_aligned": workplace_aligned,
        "support": round(support, 3),
        "benefits": benefits,
        "costs": costs,
        "benefit": benefits[0] if benefits else "",
        "benefit_alt": benefits[1] if len(benefits) > 1 else "",
        "cost": costs[0] if costs else "",
        "cost_alt": costs[1] if len(costs) > 1 else "",
    }


def _corporate_principal_in_chunk(sim, row):
    org_eid = _safe_int(row.get("corporate_org_eid"), 0)
    chunk = tuple(row.get("chunk", ()))
    positions = sim.ecs.get(Position)
    vitalities = sim.ecs.get(Vitality)
    candidates = []
    for actor_eid, pos in positions.items():
        if actor_eid == getattr(sim, "player_eid", None):
            continue
        vitality = vitalities.get(actor_eid)
        if vitality is not None and (_safe_int(getattr(vitality, "hp", 0), 0) <= 0 or bool(getattr(vitality, "downed", False))):
            continue
        if tuple(sim.chunk_coords(int(pos.x), int(pos.y))) != chunk:
            continue
        if not _actor_matches_corporate_root(sim, actor_eid, org_eid):
            continue
        memberships = actor_org_memberships(sim, actor_eid, active_only=True)
        rank = min((_safe_int(membership.get("authority_rank"), 70) for membership in memberships), default=70)
        candidates.append((rank, int(actor_eid)))
    return sorted(candidates)[0][1] if candidates else None


def ensure_corporate_security_detail(sim, row):
    if not isinstance(row, dict) or _safe_int(row.get("effective_tier"), 0) < 3:
        return None
    org_eid = _safe_int(row.get("corporate_org_eid"), 0)
    reputation = organization_snapshot(sim, organization_eid=org_eid, ensure=True) or {}
    heat = _safe_int(reputation.get("heat"), 0)
    scrutiny_actions = {_key(value.get("action")) for value in (row.get("scrutiny", {}) or {}).values() if isinstance(value, dict)}
    if _safe_int(row.get("effective_tier"), 0) < 4 and heat < 12 and not scrutiny_actions.intersection({"deny_service", "deny_entry"}):
        return None
    living_guards = []
    for guard_eid in tuple(row.get("security_guard_eids", ()) or ()):
        vitality = sim.ecs.get(Vitality).get(guard_eid)
        if vitality is not None and _safe_int(getattr(vitality, "hp", 0), 0) > 0 and not bool(getattr(vitality, "downed", False)):
            living_guards.append(int(guard_eid))
    if living_guards:
        return {"ok": True, "existing": True, "guard_eids": tuple(living_guards), "principal_eid": row.get("security_principal_eid")}
    principal = _corporate_principal_in_chunk(sim, row)
    if principal is None:
        return None
    provider = None
    for property_id in tuple(
        next(
            (presence.get("anchor_property_ids", ()) for presence in corporate_neighborhood_presence_rows(sim, corporate_org_eid=org_eid, chunk=row.get("chunk"))),
            (),
        )
        or ()
    ):
        candidate = getattr(sim, "properties", {}).get(property_id)
        if isinstance(candidate, dict):
            provider = candidate
            break
    doctrine = dict(row.get("doctrine") or {})
    count = 2 if _safe_int(row.get("effective_tier"), 0) >= 4 and doctrine.get("enforcement", 0.0) >= 0.68 else 1
    result = create_bodyguard_detail_for_principal(
        sim,
        principal,
        provider,
        count=count,
        tier="pair" if count > 1 else "solo",
        hired_by_eid=principal,
        source_kind="corporate_contractor" if doctrine.get("force_style") == "contractor_screen" else "corporate_security",
        source_id=row.get("occupation_key"),
    )
    if not result.get("ok"):
        return result
    state = ensure_corporate_occupation_state(sim)
    stored = state["neighborhoods"].get(row.get("occupation_key"))
    if not isinstance(stored, dict):
        stored = dict(row)
    guard_eids = tuple(result.get("guard_eids", ()) or ())
    stored["security_principal_eid"] = int(principal)
    stored["security_guard_eids"] = guard_eids
    stored["security_last_deployed_tick"] = _safe_int(getattr(sim, "tick", 0), 0)
    state["neighborhoods"][stored["occupation_key"]] = stored
    if doctrine.get("force_style") != "contractor_screen":
        site_property_id = _text((provider or {}).get("id")) or None
        for guard_eid in guard_eids:
            assign_actor_organization(
                sim,
                guard_eid,
                organization_eid=org_eid,
                role="security",
                kind="employment",
                title="corporate security",
                primary=False,
                authority_rank=58,
                site_property_id=site_property_id,
                active=True,
            )
    sim.emit(Event(
        "corporate_security_detail_deployed",
        organization_eid=org_eid,
        organization_name=row.get("corporate_org_name"),
        chunk=tuple(row.get("chunk", ())),
        principal_eid=principal,
        guard_eids=guard_eids,
        guard_count=len(guard_eids),
        force_style=doctrine.get("force_style"),
        provider_property_id=(provider or {}).get("id"),
        provider_property_name=(provider or {}).get("name"),
    ))
    return result


class CorporateOccupationSystem(System):
    """Bounded materialization and event response for corporate territory."""

    def __init__(self, sim, player_eid, refresh_interval=CORPORATE_OCCUPATION_REFRESH_INTERVAL):
        super().__init__(sim)
        self.player_eid = player_eid
        self.refresh_interval = max(30, _safe_int(refresh_interval, CORPORATE_OCCUPATION_REFRESH_INTERVAL))
        self._next_refresh_tick = 0
        self.sim.events.subscribe("player_action", self.on_player_action)
        self.sim.events.subscribe("camera_disabled", self.on_camera_disabled)
        self.sim.events.subscribe("physical_object_broken", self.on_physical_object_broken)

    def on_player_action(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        if _key(event.data.get("action")) not in {"move", "wait", "interact", "pickup_item", "use_item", "toggle_sneak"}:
            return
        process_corporate_surveillance_for_player(self.sim, self.player_eid)

    def _disrupt_sensor(self, prop, *, amount, reason, source_eid=None, expires_tick=None):
        if not isinstance(prop, dict):
            return None
        metadata = _metadata(prop)
        if not bool(metadata.get("corporate_surveillance_node")):
            return None
        org_eid = _safe_int(metadata.get("corporate_organization_eid"), 0)
        chunk = _property_chunk(self.sim, prop)
        if org_eid <= 0 or chunk is None:
            return None
        return record_corporate_disruption(
            self.sim,
            corporate_org_eid=org_eid,
            chunk=chunk,
            amount=amount,
            reason=reason,
            source_property_id=prop.get("id"),
            source_eid=source_eid,
            expires_tick=expires_tick,
        )

    def on_camera_disabled(self, event):
        prop = getattr(self.sim, "properties", {}).get(_text(event.data.get("property_id")))
        self._disrupt_sensor(
            prop,
            amount=0.62,
            reason="sensor_blinded",
            source_eid=event.data.get("eid"),
            expires_tick=event.data.get("disabled_until"),
        )

    def on_physical_object_broken(self, event):
        prop = getattr(self.sim, "properties", {}).get(_text(event.data.get("property_id")))
        if not isinstance(prop, dict):
            return
        metadata = _metadata(prop)
        if bool(metadata.get("corporate_surveillance_node")):
            now = _safe_int(getattr(self.sim, "tick", 0), 0)
            rng = random.Random(f"{getattr(self.sim, 'seed', 0)}:{prop.get('id')}:{now}:corporate-repair")
            metadata["corporate_repair_due_tick"] = now + rng.randint(CORPORATE_SENSOR_REPAIR_MIN_TICKS, CORPORATE_SENSOR_REPAIR_MAX_TICKS)
            self._disrupt_sensor(prop, amount=1.2, reason="sensor_destroyed", source_eid=event.data.get("source_eid"))
            return
        branding = metadata.get("corporate_branding")
        if isinstance(branding, dict):
            org_eid = _safe_int(branding.get("organization_eid"), 0)
            chunk = _property_chunk(self.sim, prop)
            if org_eid > 0 and chunk is not None:
                record_corporate_disruption(
                    self.sim,
                    corporate_org_eid=org_eid,
                    chunk=chunk,
                    amount=0.38,
                    reason="sponsored_fixture_destroyed",
                    source_property_id=prop.get("id"),
                    source_eid=event.data.get("source_eid"),
                )

    def _decay_scrutiny(self, row, *, now):
        scrutiny = row.get("scrutiny")
        if not isinstance(scrutiny, dict):
            return
        for subject_key, raw in tuple(scrutiny.items()):
            if not isinstance(raw, dict):
                scrutiny.pop(subject_key, None)
                continue
            if now - _safe_int(raw.get("last_seen_tick"), now) < CORPORATE_SCRUTINY_DECAY_DELAY:
                continue
            value = max(0.0, _safe_float(raw.get("value"), 0.0) - CORPORATE_SCRUTINY_DECAY_PER_REFRESH)
            raw["value"] = round(value, 3)
            if value < _safe_float(raw.get("threshold"), 0.82) * 0.72:
                raw["action"] = ""
            if value <= 0.0:
                scrutiny.pop(subject_key, None)

    def _repair_due_sensors(self, row, *, now):
        properties = getattr(self.sim, "properties", {})
        for property_id in tuple(row.get("sensor_property_ids", ()) or ()):
            prop = properties.get(property_id)
            if not isinstance(prop, dict):
                continue
            metadata = _metadata(prop)
            if not bool(metadata.get("fixture_broken")):
                continue
            repair_due = _safe_int(metadata.get("corporate_repair_due_tick"), 0)
            if repair_due <= 0 or now < repair_due:
                continue
            maximum = max(1, _safe_int(metadata.get("fixture_integrity_max"), 28))
            metadata["fixture_integrity"] = maximum
            metadata["fixture_broken"] = False
            metadata["fixture_usable"] = True
            metadata["corporate_repair_due_tick"] = 0
            self.sim.emit(Event(
                "corporate_sensor_restored",
                organization_eid=row.get("corporate_org_eid"),
                organization_name=row.get("corporate_org_name"),
                chunk=tuple(row.get("chunk", ())),
                property_id=property_id,
                property_name=prop.get("name"),
                x=prop.get("x"),
                y=prop.get("y"),
                z=prop.get("z"),
            ))

    def update(self):
        now = _safe_int(getattr(self.sim, "tick", 0), 0)
        if now < self._next_refresh_tick:
            return
        self._next_refresh_tick = now + self.refresh_interval
        rows = sync_all_corporate_occupations(self.sim, materialize=True)
        state = ensure_corporate_occupation_state(self.sim)
        for snapshot in rows:
            row = state["neighborhoods"].get(snapshot.get("occupation_key"))
            if not isinstance(row, dict):
                continue
            self._decay_scrutiny(row, now=now)
            self._repair_due_sensors(row, now=now)
            ensure_corporate_security_detail(self.sim, row)


__all__ = [
    "CorporateOccupationSystem",
    "corporate_labor_terms_for_property",
    "corporate_lived_dialogue_context",
    "corporate_occupation_doctrine",
    "corporate_occupation_rows",
    "corporate_trade_terms_for_property",
    "dominant_corporate_occupation_for_property",
    "ensure_corporate_occupation_state",
    "ensure_corporate_security_detail",
    "process_corporate_surveillance_for_player",
    "record_corporate_disruption",
    "sync_all_corporate_occupations",
    "sync_corporate_occupation",
]
