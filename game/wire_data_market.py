"""Wire data extraction and broker sale helpers."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from engine.events import Event
from game.components import PlayerAssets
from game.items import ITEM_CATALOG
from game.wire_consequences import wire_network_key, wire_network_property, wire_security_reset_delay
from game.wire_kit import wire_kit_add_entry, wire_kit_can_accept_entry, wire_kit_remove_entry, wire_state_for_actor
from game.wire_runtime import normalize_wire_entry_metadata, wire_entry_display_name, wire_profile_for_item


WIRE_DATA_SCHEMA_VERSION = 1
WIRE_DATA_ITEM_ID = "wire_data_cache"
WIRE_DATA_FAMILIES = (
    "payroll",
    "rota",
    "procurement",
    "customer_habits",
    "camera_fragment",
    "blackmail",
    "prototype_telemetry",
    "general",
)

_FAMILY_LABELS = {
    "payroll": "Payroll cache",
    "rota": "Rota cache",
    "procurement": "Procurement cache",
    "customer_habits": "Customer-habits cache",
    "camera_fragment": "Camera-fragment cache",
    "blackmail": "Blackmail cache",
    "prototype_telemetry": "Prototype-telemetry cache",
    "general": "General data cache",
}

_FAMILY_BUYER_TAGS = {
    "payroll": ("finance_broker", "corporate_rival"),
    "rota": ("finance_broker", "civic_buyer", "illicit_buyer"),
    "procurement": ("finance_broker", "corporate_rival", "civic_buyer"),
    "customer_habits": ("corporate_rival", "illicit_buyer"),
    "camera_fragment": ("media_buyer", "civic_buyer", "illicit_buyer"),
    "blackmail": ("media_buyer", "illicit_buyer"),
    "prototype_telemetry": ("corporate_rival", "tech_buyer"),
    "general": ("illicit_buyer",),
}

_SENSITIVITY_BY_FAMILY = {
    "payroll": 2,
    "rota": 1,
    "procurement": 2,
    "customer_habits": 2,
    "camera_fragment": 3,
    "blackmail": 4,
    "prototype_telemetry": 4,
    "general": 1,
}

_BROKER_PROFILES = {
    "finance": {
        "buyer_kind": "finance_broker",
        "buyer_tags": ("finance_broker",),
        "preferred": ("payroll", "procurement"),
        "adjacent": ("rota", "customer_habits", "prototype_telemetry"),
    },
    "corp_tech": {
        "buyer_kind": "corporate_tech_buyer",
        "buyer_tags": ("corporate_rival", "tech_buyer"),
        "preferred": ("prototype_telemetry", "procurement", "customer_habits"),
        "adjacent": ("payroll", "rota"),
    },
    "media_civic": {
        "buyer_kind": "media_civic_buyer",
        "buyer_tags": ("media_buyer", "civic_buyer"),
        "preferred": ("camera_fragment", "blackmail", "procurement"),
        "adjacent": ("payroll", "rota", "customer_habits"),
    },
    "illicit": {
        "buyer_kind": "illicit_data_buyer",
        "buyer_tags": ("illicit_buyer",),
        "preferred": ("blackmail", "customer_habits", "camera_fragment"),
        "adjacent": ("payroll", "rota", "procurement", "prototype_telemetry", "general"),
    },
}


def _text(value, default=""):
    text = str(value or "").strip()
    return text if text else str(default or "").strip()


def _key(value, default=""):
    return _text(value, default).lower()


def _int(value, default=0, *, minimum=None, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = int(default)
    if minimum is not None:
        number = max(int(minimum), number)
    if maximum is not None:
        number = min(int(maximum), number)
    return int(number)


def _string_tuple(values):
    if values is None:
        return ()
    if isinstance(values, str):
        values = (values,)
    if not isinstance(values, (list, tuple, set, frozenset)):
        return ()
    out = []
    for value in values:
        text = _key(value)
        if text:
            out.append(text)
    return tuple(dict.fromkeys(out))


def _prop_metadata(prop, *, create=False):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    if not isinstance(metadata, dict):
        if not create:
            return {}
        metadata = {}
        prop["metadata"] = metadata
    return metadata


def _stable_index(parts, count):
    if count <= 0:
        return 0
    digest = hashlib.sha256(":".join(str(part or "") for part in parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % int(count)


def _source_archetype(scene, prop):
    metadata = _prop_metadata(prop)
    return _key(
        metadata.get("archetype")
        or metadata.get("service_archetype")
        or (scene or {}).get("source_archetype")
        or (scene or {}).get("target_class"),
        "general",
    )


def _source_org(prop):
    metadata = _prop_metadata(prop)
    org_key = _key(
        prop.get("organization_key")
        or prop.get("owner_org_key")
        or prop.get("root_organization_key")
        or metadata.get("organization_key")
        or metadata.get("owner_org_key")
        or metadata.get("root_organization_key")
    )
    org_name = _text(
        prop.get("organization_name")
        or prop.get("owner_org_name")
        or prop.get("root_organization_name")
        or metadata.get("organization_name")
        or metadata.get("owner_org_name")
        or metadata.get("root_organization_name")
    )
    return org_key, org_name


def _records_node(scene, target=None):
    target = target if isinstance(target, Mapping) else {}
    node = target.get("node") if isinstance(target.get("node"), Mapping) else {}
    node_kind = _key(target.get("node_kind") or node.get("kind"))
    if node_kind == "records":
        return {
            "node_id": _text(node.get("node_id") or target.get("node_id"), "records"),
            "label": _text(node.get("label") or target.get("label"), "records node"),
        }
    avatar = dict((scene or {}).get("avatar") or {})
    ax = _int(avatar.get("x"), 0)
    ay = _int(avatar.get("y"), 0)
    for row in (scene or {}).get("nodes", ()) or ():
        if not isinstance(row, Mapping):
            continue
        if _key(row.get("kind")) != "records":
            continue
        if _int(row.get("x"), -999) == ax and _int(row.get("y"), -999) == ay:
            return {
                "node_id": _text(row.get("node_id"), "records"),
                "label": _text(row.get("label"), "records node"),
            }
    return None


def wire_data_extraction_key(scene, node=None):
    node = node if isinstance(node, Mapping) else {}
    return f"{wire_network_key(scene)}:records:{_text(node.get('node_id'), 'records')}"


def wire_data_cooldown_ticks(prop):
    return wire_security_reset_delay(prop)


def choose_wire_data_family(scene, prop):
    archetype = _source_archetype(scene, prop)
    metadata = _prop_metadata(prop)
    security = _int((scene or {}).get("security_tier") or metadata.get("security_tier") or metadata.get("security"), 1, minimum=0)
    owner_tag = _key(prop.get("owner_tag") or metadata.get("owner_tag"))
    org_key, _org_name = _source_org(prop)
    if archetype in {"bank", "brokerage", "employment_agency", "payroll_office"}:
        options = ("payroll", "procurement", "rota")
    elif archetype in {"data_center", "electronics_shop", "comms_shop", "drone_shop", "tower"}:
        options = ("prototype_telemetry", "procurement", "customer_habits")
    elif archetype in {"office", "contractor_office", "hardware_store", "tool_depot", "auto_garage"}:
        options = ("procurement", "payroll", "rota")
    elif archetype in {"media_lab", "courthouse", "city_hall", "civic_office"}:
        options = ("camera_fragment", "blackmail", "procurement")
    elif archetype in {"checkpoint", "armory", "security_office", "police_station", "jail", "prison"} or owner_tag in {"justice", "police", "military", "security"}:
        options = ("camera_fragment", "rota", "blackmail")
    elif archetype in {"casino", "bar", "nightclub", "hotel", "restaurant", "corner_store", "market"}:
        options = ("customer_habits", "payroll", "blackmail")
    elif security >= 4 or owner_tag in {"corp", "corporate"} or org_key:
        options = ("prototype_telemetry", "blackmail", "procurement")
    else:
        options = ("rota", "procurement", "customer_habits", "general")
    return options[_stable_index(((prop or {}).get("id", ""), (scene or {}).get("scene_id"), archetype, security), len(options))]


def wire_data_cache_metadata(sim, actor_eid, scene, node=None, *, item_catalog=None):
    prop = wire_network_property(sim, scene)
    node = node if isinstance(node, Mapping) else _records_node(scene)
    family = choose_wire_data_family(scene, prop if isinstance(prop, Mapping) else {})
    now = _int(getattr(sim, "tick", 0), 0)
    source_name = _text((prop or {}).get("name") or (scene or {}).get("linked_name") or (scene or {}).get("target_name"), "unknown site")
    source_id = _text((prop or {}).get("id") or (scene or {}).get("linked_property_id") or (scene or {}).get("target_property_id"))
    archetype = _source_archetype(scene, prop if isinstance(prop, Mapping) else {})
    org_key, org_name = _source_org(prop if isinstance(prop, Mapping) else {})
    source_security = 1
    if isinstance(prop, Mapping):
        source_security = (scene or {}).get("security_tier") or _prop_metadata(prop).get("security_tier") or _prop_metadata(prop).get("security")
    security = _int(source_security, 1, minimum=0)
    sensitivity = min(5, _SENSITIVITY_BY_FAMILY.get(family, 1) + (1 if security >= 4 else 0))
    freshness = max(1, min(5, 3 + (1 if security >= 3 else 0)))
    heat_risk = max(0, min(5, sensitivity + (1 if family in {"blackmail", "camera_fragment"} else 0)))
    legality = "illegal" if family in {"blackmail", "camera_fragment"} or heat_risk >= 5 else "restricted"
    display_name = f"{_FAMILY_LABELS.get(family, 'Data cache')}: {source_name}"
    metadata = {
        "wire_data_schema_version": WIRE_DATA_SCHEMA_VERSION,
        "data_family": family,
        "sensitivity": sensitivity,
        "freshness": freshness,
        "heat_risk": heat_risk,
        "legality": legality,
        "source_property_id": source_id,
        "source_property_name": source_name,
        "source_org_key": org_key,
        "source_org_name": org_name,
        "source_archetype": archetype,
        "captured_tick": now,
        "buyer_tags": _FAMILY_BUYER_TAGS.get(family, ("illicit_buyer",)),
        "evidence_links": (
            f"wire_scene:{_text((scene or {}).get('scene_id'), 'unknown')}",
            f"property:{source_id}" if source_id else "property:unknown",
        ),
        "display_name": display_name,
        "source_context": "wire_data_siphon",
        "storage_status": "wire_kit",
        "captured_by_eid": actor_eid,
        "records_node_id": _text((node or {}).get("node_id"), "records"),
        "network_key": wire_network_key(scene, prop),
    }
    return normalize_wire_entry_metadata(
        metadata,
        item_id=WIRE_DATA_ITEM_ID,
        profile=wire_profile_for_item(WIRE_DATA_ITEM_ID, item_catalog=item_catalog or ITEM_CATALOG),
    )


def wire_data_siphon_preflight(sim, actor_eid, scene, *, target=None, item_catalog=None):
    if not isinstance(scene, Mapping):
        return {"ok": False, "reason": "missing_scene"}
    node = _records_node(scene, target=target)
    if node is None:
        return {"ok": False, "reason": "wrong_records_node"}
    prop = wire_network_property(sim, scene)
    if not isinstance(prop, dict):
        return {"ok": False, "reason": "missing_data_source"}
    metadata = _prop_metadata(prop, create=False)
    marks = metadata.get("wire_data_extractions")
    if not isinstance(marks, dict):
        marks = {}
    key = wire_data_extraction_key(scene, node=node)
    now = _int(getattr(sim, "tick", 0), 0)
    previous = marks.get(key)
    if isinstance(previous, Mapping):
        cooldown = _int(previous.get("cooldown_ticks"), wire_data_cooldown_ticks(prop), minimum=1)
        last_tick = _int(previous.get("last_tick"), -cooldown, minimum=-cooldown)
        if now < last_tick + cooldown:
            return {
                "ok": False,
                "reason": "records_recently_drained",
                "remaining_ticks": (last_tick + cooldown) - now,
                "source_key": key,
            }
    state = wire_state_for_actor(sim, actor_eid, create=True)
    entry = {
        "instance_id": "wire-data-preview",
        "item_id": WIRE_DATA_ITEM_ID,
        "quantity": 1,
        "owner_eid": actor_eid,
        "owner_tag": "player",
        "metadata": wire_data_cache_metadata(sim, actor_eid, scene, node=node, item_catalog=item_catalog),
    }
    ok, reason = wire_kit_can_accept_entry(state, entry, item_catalog=item_catalog or ITEM_CATALOG)
    if not ok:
        return {"ok": False, "reason": reason or "wire_kit_full", "source_key": key}
    return {"ok": True, "reason": None, "source_key": key, "node": dict(node), "metadata": dict(entry["metadata"])}


def extract_wire_data_cache(sim, actor_eid, scene, *, target=None, item_catalog=None):
    preflight = wire_data_siphon_preflight(sim, actor_eid, scene, target=target, item_catalog=item_catalog)
    if not preflight.get("ok"):
        return preflight
    prop = wire_network_property(sim, scene)
    node = dict(preflight.get("node") or {})
    instance_factory = getattr(sim, "new_item_instance_id", None)
    instance_id = instance_factory() if callable(instance_factory) else f"wire-data-{getattr(sim, 'tick', 0)}"
    entry = {
        "instance_id": instance_id,
        "item_id": WIRE_DATA_ITEM_ID,
        "quantity": 1,
        "owner_eid": actor_eid,
        "owner_tag": "player",
        "metadata": dict(preflight.get("metadata") or wire_data_cache_metadata(sim, actor_eid, scene, node=node, item_catalog=item_catalog)),
    }
    state = wire_state_for_actor(sim, actor_eid, create=True)
    result = wire_kit_add_entry(state, entry, item_catalog=item_catalog or ITEM_CATALOG)
    if not result.get("ok"):
        return {"ok": False, "reason": result.get("reason", "wire_kit_full"), "entry": dict(entry)}
    now = _int(getattr(sim, "tick", 0), 0)
    metadata = _prop_metadata(prop, create=True)
    marks = metadata.get("wire_data_extractions")
    if not isinstance(marks, dict):
        marks = {}
        metadata["wire_data_extractions"] = marks
    source_key = str(preflight.get("source_key") or wire_data_extraction_key(scene, node=node))
    marks[source_key] = {
        "last_tick": now,
        "cooldown_ticks": wire_data_cooldown_ticks(prop),
        "family": entry["metadata"].get("data_family"),
        "instance_id": instance_id,
        "scene_id": (scene or {}).get("scene_id"),
    }
    sim.emit(Event(
        "wire_data_extracted",
        eid=actor_eid,
        item_id=WIRE_DATA_ITEM_ID,
        instance_id=instance_id,
        display_name=entry["metadata"].get("display_name", ""),
        data_family=entry["metadata"].get("data_family", ""),
        source_property_id=entry["metadata"].get("source_property_id", ""),
        source_property_name=entry["metadata"].get("source_property_name", ""),
        source_key=source_key,
    ))
    return {"ok": True, "reason": None, "entry": dict(result.get("entry") or entry), "source_key": source_key}


def wire_data_buyer_profile_for_store(prop=None, store=None):
    archetype = _key((store or {}).get("archetype") if isinstance(store, Mapping) else "")
    if not archetype and isinstance(prop, Mapping):
        archetype = _key(_prop_metadata(prop).get("archetype") or _prop_metadata(prop).get("service_archetype"))
    org_key, org_name = _source_org(prop if isinstance(prop, Mapping) else {})
    extra = {
        "context": archetype,
        "buyer_property_id": _text((prop or {}).get("id")) if isinstance(prop, Mapping) else "",
        "buyer_property_name": _text((prop or {}).get("name")) if isinstance(prop, Mapping) else "",
        "buyer_org_key": org_key,
        "buyer_org_name": org_name,
    }
    if archetype in {"bank", "brokerage"}:
        return dict(_BROKER_PROFILES["finance"], **extra)
    if archetype in {"office", "tower", "data_center", "electronics_shop", "comms_shop", "drone_shop"}:
        return dict(_BROKER_PROFILES["corp_tech"], **extra)
    if archetype in {"media_lab", "civic_office", "city_hall"}:
        return dict(_BROKER_PROFILES["media_civic"], **extra)
    if archetype in {"backroom_market", "pawn_shop", "junk_market", "chop_shop"}:
        return dict(_BROKER_PROFILES["illicit"], **extra)
    return None


def wire_data_buyer_profile_for_street(profile=None):
    profile = profile if isinstance(profile, Mapping) else {}
    vendor_kind = _key(profile.get("vendor_kind"))
    career = _key(profile.get("career"))
    org_key = _key(profile.get("organization_key") or profile.get("root_organization_key") or profile.get("org_key"))
    org_name = _text(profile.get("organization_name") or profile.get("root_organization_name") or profile.get("org_name"))
    extra = {
        "context": vendor_kind or career or "street",
        "buyer_org_key": org_key,
        "buyer_org_name": org_name,
    }
    if vendor_kind in {"gang_fence", "alley_market"}:
        return dict(_BROKER_PROFILES["illicit"], **extra)
    if vendor_kind in {"drug_pusher", "drug_seeker", "vehicle_gun_vendor", "friend_of_friend"}:
        return None
    if any(token in career for token in ("broker", "analyst", "banker", "accountant")):
        return dict(_BROKER_PROFILES["finance"], **extra)
    if any(token in career for token in ("journalist", "reporter", "civic", "activist")):
        return dict(_BROKER_PROFILES["media_civic"], **extra)
    if any(token in career for token in ("corp", "tech", "engineer", "fixer")):
        return dict(_BROKER_PROFILES["corp_tech"], **extra)
    return None


def wire_data_quote(entry, buyer_profile=None, *, tick=0, price_mult=1.0):
    metadata = dict((entry or {}).get("metadata") or {})
    buyer_profile = buyer_profile if isinstance(buyer_profile, Mapping) else None
    family = _key(metadata.get("data_family"), "general")
    sensitivity = _int(metadata.get("sensitivity"), 1, minimum=0, maximum=5)
    heat_risk = _int(metadata.get("heat_risk"), 0, minimum=0, maximum=5)
    freshness = _int(metadata.get("freshness"), 1, minimum=0, maximum=5)
    captured_tick = _int(metadata.get("captured_tick"), int(tick), minimum=0)
    age_steps = max(0, (_int(tick, 0, minimum=0) - captured_tick) // 1000)
    effective_freshness = max(0, freshness - age_steps)
    base_value = 18 + (sensitivity * 34) + (effective_freshness * 9) + (heat_risk * 13)
    legality = _key(metadata.get("legality"), "restricted")
    buyer_tags = set(_string_tuple(metadata.get("buyer_tags")))
    source_org_key = _key(metadata.get("source_org_key"))
    buyer_org_key = _key((buyer_profile or {}).get("buyer_org_key")) if isinstance(buyer_profile, Mapping) else ""
    org_context = ""
    if buyer_profile is None:
        interest = "refused"
        multiplier = 0.0
        reason = "no data broker here"
    else:
        profile_tags = set(_string_tuple(buyer_profile.get("buyer_tags")))
        preferred = set(_string_tuple(buyer_profile.get("preferred")))
        adjacent = set(_string_tuple(buyer_profile.get("adjacent")))
        if source_org_key and buyer_org_key and source_org_key == buyer_org_key:
            interest = "wanted"
            multiplier = 0.92 if family not in preferred else 1.04
            reason = "internal data recovery"
            org_context = "internal"
        elif source_org_key and buyer_org_key and source_org_key != buyer_org_key and family in {"payroll", "procurement", "customer_habits", "prototype_telemetry", "blackmail"}:
            interest = "wanted"
            multiplier = 1.24
            reason = "rival organization intelligence"
            org_context = "rival"
        elif family in preferred or buyer_tags.intersection(profile_tags):
            interest = "wanted"
            multiplier = 1.16
            reason = "matches broker demand"
        elif family in adjacent:
            interest = "adjacent"
            multiplier = 0.68
            reason = "adjacent data interest"
        else:
            interest = "refused"
            multiplier = 0.0
            reason = "wrong data buyer"
    price = int(max(1, round(base_value * multiplier * max(0.0, float(price_mult or 1.0))))) if multiplier > 0 else 0
    risk_label = ""
    if legality == "illegal":
        risk_label = "hot data"
    elif heat_risk >= 4:
        risk_label = "trace risk"
    elif legality == "restricted":
        risk_label = "restricted data"
    return {
        "price": price,
        "base_price": int(base_value),
        "interest": interest,
        "label": "wanted data" if interest == "wanted" else ("adjacent data" if interest == "adjacent" else "refused data"),
        "accepted": interest in {"wanted", "adjacent"},
        "reason": reason,
        "freshness": effective_freshness,
        "heat_risk": heat_risk,
        "risk_label": risk_label,
        "legality": legality,
        "data_family": family,
        "org_context": org_context,
    }


def _wire_data_entries(sim, actor_eid):
    state = wire_state_for_actor(sim, actor_eid, create=False)
    if state is None:
        return []
    rows = []
    for entry in getattr(state, "kit_entries", ()) or ():
        if not isinstance(entry, Mapping):
            continue
        if _key(entry.get("item_id")) != WIRE_DATA_ITEM_ID:
            continue
        profile = wire_profile_for_item(entry.get("item_id"), item_catalog=ITEM_CATALOG)
        if _key(profile.get("kind")) != "data_packet":
            continue
        rows.append(dict(entry))
    return rows


def _data_sell_row(entry, quote, *, row_context):
    metadata = dict(entry.get("metadata") or {})
    name = wire_entry_display_name(entry, item_catalog=ITEM_CATALOG)
    family = _key(metadata.get("data_family"), "general")
    return {
        "entry": dict(entry),
        "source_container": "wire_kit",
        "instance_id": entry.get("instance_id"),
        "item_id": WIRE_DATA_ITEM_ID,
        "item_name": name,
        "glyph": str(ITEM_CATALOG.get(WIRE_DATA_ITEM_ID, {}).get("glyph", ":") or ":")[:1],
        "quantity": 1,
        "price": int(max(1, quote.get("price", 1))),
        "base_price": int(max(1, quote.get("base_price", quote.get("price", 1)))),
        "listed": False,
        "action_label": "sell data",
        "purchase_interest": quote.get("interest"),
        "interest_label": quote.get("label"),
        "interest_known": True,
        "interest_actual": quote.get("interest"),
        "actual_label": quote.get("label"),
        "interest_actual_label": quote.get("label"),
        "row_color": "item_restricted" if quote.get("legality") == "illegal" else "item_tool",
        "interest_reason": quote.get("reason", ""),
        "interest_price_mult": 1.0,
        "interest_accepted": bool(quote.get("accepted")),
        "interest_pressure_weight": 0,
        "risk_label": quote.get("risk_label", ""),
        "trade_pressure_label": "broker",
        "trade_pressure_note": row_context,
        "trade_pressure_value": 0.0,
        "wire_data_family": family,
        "wire_data_freshness": quote.get("freshness"),
        "wire_data_heat_risk": quote.get("heat_risk"),
        "wire_data_org_context": quote.get("org_context", ""),
        "illegal": quote.get("legality") == "illegal",
    }


def wire_data_store_sell_rows(sim, actor_eid, prop=None, store=None, *, terms=None):
    buyer = wire_data_buyer_profile_for_store(prop, store)
    if buyer is None:
        return []
    sell_mult = float((terms or {}).get("sell_mult", 1.0) or 1.0) if isinstance(terms, Mapping) else 1.0
    rows = []
    for entry in _wire_data_entries(sim, actor_eid):
        quote = wire_data_quote(entry, buyer, tick=getattr(sim, "tick", 0), price_mult=sell_mult)
        if not quote.get("accepted"):
            continue
        rows.append(_data_sell_row(entry, quote, row_context=str(buyer.get("context", "broker"))))
    rows.sort(key=lambda row: (-int(row.get("price", 0)), row.get("wire_data_family", ""), row.get("instance_id", "")))
    return rows


def wire_data_street_sell_rows(sim, contact_eid, player_eid, profile=None):
    buyer = wire_data_buyer_profile_for_street(profile)
    if buyer is None:
        return []
    rows = []
    for entry in _wire_data_entries(sim, player_eid):
        quote = wire_data_quote(entry, buyer, tick=getattr(sim, "tick", 0), price_mult=1.0)
        if not quote.get("accepted"):
            continue
        row = _data_sell_row(entry, quote, row_context=str(buyer.get("context", "street")))
        row.update({
            "purchase_interest": "wanted",
            "interest_actual": "wanted",
            "interest_label": "broker wants data",
            "interest_actual_label": "broker wants data",
            "row_badge": "data",
            "source_kind": "street_vendor",
            "contact_eid": contact_eid,
        })
        rows.append(row)
    rows.sort(key=lambda row: (-int(row.get("price", 0)), row.get("wire_data_family", ""), row.get("instance_id", "")))
    return rows


def remove_wire_data_entry(sim, actor_eid, instance_id):
    state = wire_state_for_actor(sim, actor_eid, create=False)
    if state is None:
        return {"ok": False, "reason": "missing_wire_state"}
    entry = None
    for row in getattr(state, "kit_entries", ()) or ():
        if isinstance(row, Mapping) and _text(row.get("instance_id")) == _text(instance_id):
            entry = dict(row)
            break
    if entry is None or _key(entry.get("item_id")) != WIRE_DATA_ITEM_ID:
        return {"ok": False, "reason": "data_unavailable"}
    removed = wire_kit_remove_entry(state, instance_id)
    if removed is None:
        return {"ok": False, "reason": "data_remove_failed"}
    return {"ok": True, "reason": None, "entry": dict(removed)}


def sell_wire_data_entry(sim, actor_eid, instance_id, *, price=0, buyer_context=""):
    result = remove_wire_data_entry(sim, actor_eid, instance_id)
    if not result.get("ok"):
        return result
    assets = sim.ecs.get(PlayerAssets).get(actor_eid)
    if assets is None:
        state = wire_state_for_actor(sim, actor_eid, create=True)
        state.kit_entries.append(dict(result["entry"]))
        return {"ok": False, "reason": "missing_assets", "entry": dict(result["entry"])}
    payout = int(max(0, price or 0))
    assets.credits = int(getattr(assets, "credits", 0) or 0) + payout
    entry = dict(result["entry"])
    sim.emit(Event(
        "wire_data_sold",
        eid=actor_eid,
        instance_id=entry.get("instance_id"),
        item_id=entry.get("item_id"),
        item_name=wire_entry_display_name(entry, item_catalog=ITEM_CATALOG),
        price=payout,
        credits=assets.credits,
        buyer_context=buyer_context,
        data_family=(entry.get("metadata") or {}).get("data_family", ""),
    ))
    return {"ok": True, "reason": None, "entry": entry, "price": payout, "credits": assets.credits}
