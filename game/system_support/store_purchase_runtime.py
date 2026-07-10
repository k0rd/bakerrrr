"""Storefront buyback interest helpers.

This module keeps shop buyback policy as a shared read model so trade rows,
sell execution, and dialogue can all describe the same store behavior.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from game.components import NPCSocial, PlayerAssets
from game.drone_runtime import drone_profile_for_item
from game.economy import item_trade_pressure_bias
from game.items import ITEM_CATALOG
from game.wire_runtime import wire_profile_for_item


INTEREST_WANTED = "wanted"
INTEREST_ADJACENT = "adjacent"
INTEREST_UNUSUAL = "unusual"
INTEREST_REFUSED = "refused"

INTEREST_LABELS = {
    INTEREST_WANTED: "wanted here",
    INTEREST_ADJACENT: "they may take this cheap",
    INTEREST_UNUSUAL: "unusual ask",
    INTEREST_REFUSED: "not their line",
}

INTEREST_COLORS = {
    INTEREST_WANTED: "property_service",
    INTEREST_ADJACENT: "item_tool",
    INTEREST_UNUSUAL: "item_restricted",
    INTEREST_REFUSED: "item_illegal",
}

BROAD_BUYER_ARCHETYPES = {
    "pawn_shop",
    "backroom_market",
    "chop_shop",
    "junk_market",
    "salvage_camp",
    "breaker_yard",
    "drydock_yard",
}

SHADY_BUYER_ARCHETYPES = {
    "backroom_market",
    "backroom_clinic",
    "chop_shop",
    "junk_market",
    "nightclub",
    "pawn_shop",
}

TACTICAL_BUYER_ARCHETYPES = {
    "surplus_store",
    "outfitter",
    "hardware_store",
    "tool_depot",
    "auto_garage",
    "drone_shop",
    "chop_shop",
    "pawn_shop",
    "backroom_market",
}

DANGEROUS_TAGS = {"weapon", "ammo", "throwable", "tactical", "armor", "trap", "aerosol_trap"}

STYLE_BUYER_ARCHETYPES = {
    "top_shop",
    "bottom_shop",
    "dress_shop",
    "shoe_shop",
    "outerwear_shop",
    "headwear_shop",
    "jewelry_shop",
    "accessory_shop",
    "clothing_superstore",
    "salon",
    "barbershop",
    "hair_studio",
    "makeup_counter",
}


def canonical_store_item_id(item_id):
    key = str(item_id or "").strip().lower()
    if key == "burner_phone":
        return "phone"
    return key


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _property_metadata(prop):
    if isinstance(prop, Mapping) and isinstance(prop.get("metadata"), Mapping):
        return prop.get("metadata") or {}
    return {}


def store_archetype(prop=None, store=None):
    if isinstance(store, Mapping):
        text = str(store.get("archetype", "") or "").strip().lower()
        if text:
            return text
    metadata = _property_metadata(prop)
    return str(metadata.get("archetype", "") or "").strip().lower()


def _item_def(item_id):
    key = str(item_id or "").strip().lower()
    return ITEM_CATALOG.get(key) or ITEM_CATALOG.get(canonical_store_item_id(key)) or {}


def item_purchase_tags(item_id, entry=None):
    item_def = _item_def(item_id)
    tags = {
        str(tag or "").strip().lower()
        for tag in item_def.get("tags", ()) or ()
        if str(tag or "").strip()
    }
    category = str(item_def.get("category", "") or "").strip().lower()
    if category:
        tags.add(category)
    legal_status = str(item_def.get("legal_status", "legal") or "legal").strip().lower()
    if legal_status:
        tags.add(legal_status)
    if canonical_store_item_id(item_id) == "phone":
        tags.update({"phone", "communication", "device"})
    drone_profile = drone_profile_for_item(item_id, item_catalog=ITEM_CATALOG)
    drone_kind = str(drone_profile.get("kind", "") or "").strip().lower()
    if drone_kind:
        tags.update({"drone", "device"})
        if drone_kind == "assembly":
            tags.update({"drone_assembly", "tool", "restricted"})
        elif drone_kind == "chassis":
            tags.update({"drone_part", "part", "tool"})
        elif drone_kind == "power_center":
            tags.update({"drone_part", "part", "device", "battery", "tool"})
        elif drone_kind == "battery":
            tags.update({"drone_part", "part", "battery", "tool"})
        elif drone_kind == "module":
            tags.update({"drone_part", "drone_module", "part", "device"})
            tags.update(str(capability or "").strip().lower() for capability in drone_profile.get("capabilities", ()) if str(capability or "").strip())
    if isinstance(item_def.get("armor"), Mapping):
        tags.update({"armor", "wearable"})
    if isinstance(item_def.get("disguise"), Mapping):
        tags.update({"disguise", "wearable", "clothing"})
    if isinstance(item_def.get("throw_profile"), Mapping):
        tags.add("throwable")
    metadata = entry.get("metadata") if isinstance(entry, Mapping) and isinstance(entry.get("metadata"), Mapping) else {}
    instance_tags = metadata.get("tags") or metadata.get("instance_tags") or ()
    for tag in instance_tags if isinstance(instance_tags, (list, tuple, set)) else ():
        text = str(tag or "").strip().lower()
        if text:
            tags.add(text)
    if bool(metadata.get("illegal")):
        tags.add("illegal")
    if bool(metadata.get("stolen")):
        tags.add("stolen")
    wire_profile = wire_profile_for_item(item_id, item_catalog=ITEM_CATALOG)
    wire_kind = str(wire_profile.get("kind", "") or "").strip().lower()
    if wire_kind:
        tags.update({"wire", "device"})
        if wire_kind == "data_packet":
            family = str((metadata.get("data_family") or wire_profile.get("data_family") or "general") or "general").strip().lower()
            tags.update({"wire_data", "data", "data_packet", family})
            for tag in metadata.get("buyer_tags") or wire_profile.get("buyer_tags") or ():
                text = str(tag or "").strip().lower()
                if text:
                    tags.add(text)
        elif wire_kind == "program":
            tags.update({"wire_program", "software", "tool"})
        elif wire_kind in {"credential", "license"}:
            tags.update({"wire_access", "credential"})
    return tags


def item_is_dangerous(item_id, entry=None):
    return bool(item_purchase_tags(item_id, entry).intersection(DANGEROUS_TAGS))


def _profile_for_archetype(archetype):
    profile = {
        "summary": "general supplies and a few practical goods",
        "wanted": {"token", "cash", "credit", "phone", "communication"},
        "adjacent": {"food", "drink", "medical", "tool", "clothing"},
        "refuse_dangerous": False,
    }
    if archetype == "butcher_shop":
        profile.update({
            "summary": "raw game meat, prepared cuts, packaged meat, and field dressing gear",
            "wanted": {"food", "meat", "raw_meat", "field_dressed", "packaged_meat", "hunting"},
            "adjacent": {"tool", "blade", "survival", "medical", "drink"},
            "refuse_dangerous": True,
        })
    elif archetype in {"corner_store", "restaurant", "soup_kitchen", "street_kitchen", "daycare", "hotel", "flophouse"}:
        profile.update({
            "summary": "food, drinks, vouchers, and small counter goods",
            "wanted": {"food", "drink", "meal", "voucher", "token", "social"},
            "adjacent": {"medical", "safety", "survival", "phone", "communication", "meat", "packaged_meat"},
            "refuse_dangerous": True,
        })
    elif archetype in {"bar", "nightclub", "roadhouse", "tavern", "pool_hall", "karaoke_box", "music_venue"}:
        profile.update({
            "summary": "drinks, social goods, tokens, and nightlife stock",
            "wanted": {"drink", "social", "token", "drug", "stimulant", "phone", "communication"},
            "adjacent": {"food", "medical", "clothing", "meat", "packaged_meat"},
            "refuse_dangerous": True,
        })
    elif archetype in {"pharmacy", "backroom_clinic", "herbalist_camp", "herbalist_shop"}:
        profile.update({
            "summary": "medical supplies, remedies, and usable clinic stock",
            "wanted": {"medical", "safety", "injectable", "drug", "consumable", "herbal_ingredient", "plant_material", "herbal_medicine"},
            "adjacent": {"food", "drink", "survival", "tool", "gardening", "herbal"},
            "refuse_dangerous": True,
        })
    elif archetype in {"hardware_store", "tool_depot", "auto_garage", "service_station", "salvage_camp", "breaker_yard", "drydock_yard"}:
        profile.update({
            "summary": "tools, parts, batteries, circuits, work gear, and practical repair supplies",
            "wanted": {"tool", "device", "communication", "phone", "battery", "circuit", "scrap", "armor", "wearable", "safety"},
            "adjacent": {"medical", "food", "drink", "ammo", "throwable", "tactical"},
            "refuse_dangerous": False,
        })
    elif archetype in {"electronics_shop", "comms_shop"}:
        profile.update({
            "summary": "phones, radios, electronics, drone sensors, batteries, and small device parts",
            "wanted": {"device", "communication", "phone", "battery", "circuit", "drone", "drone_part", "drone_module", "tool"},
            "adjacent": {"paper", "token", "cash", "credit", "medical", "survival"},
            "refuse_dangerous": True,
        })
    elif archetype == "drone_shop":
        profile.update({
            "summary": "drone chassis, modules, power centers, batteries, sensors, and repairable device parts",
            "wanted": {"drone", "drone_part", "drone_module", "drone_assembly", "device", "battery", "circuit", "tool", "communication", "phone"},
            "adjacent": {"armor", "tactical", "survival", "medical", "cash", "credit"},
            "refuse_dangerous": False,
        })
    elif archetype in {"bank", "brokerage"}:
        profile.update({
            "summary": "finance records, payroll packets, procurement traces, and clean wire tools",
            "wanted": {"wire_data", "data", "payroll", "procurement", "finance_broker", "wire_program", "software"},
            "adjacent": {"device", "communication", "credential", "customer_habits", "prototype_telemetry"},
            "refuse_dangerous": True,
        })
    elif archetype in {"office", "tower", "data_center", "media_lab"}:
        profile.update({
            "summary": "wire software, brokerable data, records tooling, and technical devices",
            "wanted": {"wire_data", "data", "prototype_telemetry", "procurement", "customer_habits", "camera_fragment", "wire_program", "software", "device"},
            "adjacent": {"communication", "credential", "payroll", "blackmail", "tool"},
            "refuse_dangerous": archetype != "data_center",
        })
    elif archetype in STYLE_BUYER_ARCHETYPES:
        profile.update({
            "summary": "clothing, accessories, wearable style goods, and light counter stock",
            "wanted": {"clothing", "wearable", "disguise", "social", "fashion", "jewelry"},
            "adjacent": {"token", "food", "drink", "medical", "phone", "communication"},
            "refuse_dangerous": True,
        })
    elif archetype == "tattoo_parlor":
        profile.update({
            "summary": "tattoo appointments, clean style goods, and small counter stock",
            "wanted": {"service", "appearance"},
            "adjacent": {"clothing", "wearable", "fashion", "jewelry", "social"},
            "refuse_dangerous": True,
            "service_counter": True,
        })
    elif archetype == "casino":
        profile.update({
            "summary": "game tokens, cards, drinks, and small entertainment-counter goods",
            "wanted": {"token", "social", "cash", "credit", "drink", "book", "paper"},
            "adjacent": {"food", "phone", "communication", "junk"},
            "refuse_dangerous": True,
        })
    elif archetype in {"courier_office", "employment_agency", "recruitment_office", "bounty_office"}:
        profile.update({
            "summary": "paperwork, phones, tokens, and job-counter supplies",
            "wanted": {"paper", "book", "phone", "communication", "token", "cash", "credit", "social"},
            "adjacent": {"food", "drink", "medical", "tool", "safety"},
            "refuse_dangerous": True,
            "service_counter": True,
        })
    elif archetype in {"outfitter", "bait_shop", "dock_shack"}:
        profile.update({
            "summary": "outdoor gear, blades, field food, ammo, and survival supplies",
            "wanted": {"tool", "weapon", "melee", "blade", "ammo", "survival", "armor", "wearable", "clothing", "medical"},
            "adjacent": {"food", "drink", "device", "phone", "communication", "social"},
            "refuse_dangerous": False,
        })
    elif archetype == "surplus_store":
        profile.update({
            "summary": "weapons, ammo, armor, uniforms, tactical gear, and field supplies",
            "wanted": {"weapon", "ammo", "armor", "throwable", "tactical", "wearable", "clothing", "tool", "survival", "medical"},
            "adjacent": {"food", "drink", "phone", "communication", "device"},
            "refuse_dangerous": False,
        })
    elif archetype == "thrift_store":
        profile.update({
            "summary": "clothing, wearable cover, odd tokens, and cheap household goods",
            "wanted": {"clothing", "wearable", "disguise", "token", "junk", "social", "phone", "communication"},
            "adjacent": {"tool", "medical", "food", "drink"},
            "refuse_dangerous": True,
        })
    elif archetype in {"arcade", "gaming_hall", "theater", "gallery", "bookshop", "laundromat"}:
        profile.update({
            "summary": "tokens, social goods, books, cards, and light counter stock",
            "wanted": {"token", "social", "junk", "book", "paper", "food", "drink"},
            "adjacent": {"phone", "communication", "clothing", "medical"},
            "refuse_dangerous": True,
        })
    elif archetype in BROAD_BUYER_ARCHETYPES:
        profile.update({
            "summary": "broad practical goods, valuables, tools, weapons, phones, and off-list stock",
            "wanted": {"token", "cash", "credit", "tool", "device", "communication", "phone", "weapon", "ammo", "armor", "wearable", "medical", "drug", "throwable"},
            "adjacent": {"food", "drink", "clothing", "social", "junk"},
            "refuse_dangerous": False,
        })
    return profile


def _store_stock_item_ids(store):
    ids = set()
    if isinstance(store, Mapping):
        for entry in store.get("entries", ()) or ():
            if isinstance(entry, Mapping):
                item_id = canonical_store_item_id(entry.get("item_id"))
                if item_id:
                    ids.add(item_id)
    return ids


def _relation_score(sim, service_eid, actor_eid):
    if sim is None or service_eid is None or actor_eid is None:
        return 0.0
    socials = sim.ecs.get(NPCSocial)
    social = socials.get(service_eid) if socials else None
    bond = social.bonds.get(actor_eid) if social and isinstance(getattr(social, "bonds", None), dict) else None
    if not isinstance(bond, Mapping):
        return 0.0
    trust = _safe_float(bond.get("trust"), 0.0)
    closeness = _safe_float(bond.get("closeness"), 0.0)
    protect = _safe_float(bond.get("protectiveness"), 0.0)
    return max(0.0, min(1.0, (trust * 0.46) + (closeness * 0.36) + (protect * 0.18)))


def _actor_skill(sim, actor_eid, skill_id, default=5.0):
    try:
        from game.skills import actor_skill

        return float(actor_skill(sim, actor_eid, skill_id, default=default))
    except Exception:  # noqa: BLE001 - policy reads should degrade harmlessly
        return float(default)


def _player_owns_store(sim, actor_eid, prop):
    if not isinstance(prop, Mapping) or actor_eid is None:
        return False
    try:
        if int(prop.get("owner_eid") or 0) == int(actor_eid):
            return True
    except (TypeError, ValueError):
        if prop.get("owner_eid") == actor_eid:
            return True
    assets = sim.ecs.get(PlayerAssets).get(actor_eid) if sim is not None else None
    return bool(assets and str(prop.get("id", "") or "").strip() in getattr(assets, "owned_property_ids", set()))


def _stable_unit(*parts):
    key = ":".join(str(part or "") for part in parts)
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / 0xFFFFFFFF


def visible_store_interest(actual, *, sim=None, actor_eid=None, prop=None, entry=None):
    streetwise = _actor_skill(sim, actor_eid, "streetwise", default=5.0)
    if streetwise >= 6.0 or actual in {INTEREST_WANTED, INTEREST_REFUSED}:
        return actual, True
    if streetwise >= 4.0:
        if actual == INTEREST_ADJACENT:
            return actual, True
        return INTEREST_ADJACENT, False
    token = _stable_unit(
        getattr(sim, "seed", 0),
        actor_eid,
        (prop or {}).get("id") if isinstance(prop, Mapping) else "",
        (entry or {}).get("instance_id") if isinstance(entry, Mapping) else "",
        (entry or {}).get("item_id") if isinstance(entry, Mapping) else "",
    )
    if actual == INTEREST_ADJACENT and token < 0.35:
        return INTEREST_UNUSUAL, False
    if actual == INTEREST_UNUSUAL and token < 0.55:
        return INTEREST_ADJACENT, False
    return actual, actual != INTEREST_UNUSUAL


def unusual_sale_allowed(sim, actor_eid, prop, entry, *, service_eid=None):
    if _player_owns_store(sim, actor_eid, prop):
        return True
    streetwise = _actor_skill(sim, actor_eid, "streetwise", default=5.0)
    conversation = _actor_skill(sim, actor_eid, "conversation", default=5.0)
    relation = _relation_score(sim, service_eid, actor_eid)
    tags = item_purchase_tags((entry or {}).get("item_id"), entry)
    score = ((streetwise - 5.0) * 0.12) + ((conversation - 5.0) * 0.08) + (relation * 0.36)
    if "restricted" in tags:
        score -= 0.16
    if "illegal" in tags or "stolen" in tags:
        score -= 0.34
    if item_is_dangerous((entry or {}).get("item_id"), entry):
        score -= 0.08
    return score >= 0.18


def _homemade_trap_sale_allowed(sim, actor_eid, prop, entry, *, archetype="", service_eid=None):
    if archetype not in BROAD_BUYER_ARCHETYPES and archetype not in SHADY_BUYER_ARCHETYPES:
        return False
    token = _stable_unit(
        getattr(sim, "seed", 0),
        "homemade_aerosol_trap",
        actor_eid,
        service_eid,
        (prop or {}).get("id") if isinstance(prop, Mapping) else "",
        (entry or {}).get("instance_id") if isinstance(entry, Mapping) else "",
        (entry or {}).get("item_id") if isinstance(entry, Mapping) else "",
    )
    return token < 0.18


def classify_store_purchase_interest(sim, actor_eid, prop, store, entry, *, service_eid=None):
    item_id = str((entry or {}).get("item_id", "") or "").strip().lower()
    item_key = canonical_store_item_id(item_id)
    archetype = store_archetype(prop, store)
    profile = _profile_for_archetype(archetype)
    tags = item_purchase_tags(item_id, entry)
    stock_ids = _store_stock_item_ids(store)
    listed = bool(item_key and item_key in stock_ids)
    dangerous = bool(tags.intersection(DANGEROUS_TAGS))
    illegal = bool(tags.intersection({"illegal", "stolen"}))
    restricted = "restricted" in tags
    experimental = "experimental" in tags
    homemade_aerosol_trap = "aerosol_trap" in tags and "homemade" in tags

    if _player_owns_store(sim, actor_eid, prop):
        actual = INTEREST_WANTED
        price_mult = 1.0
        reason = "owner shelf transfer"
    elif homemade_aerosol_trap:
        if _homemade_trap_sale_allowed(sim, actor_eid, prop, entry, archetype=archetype, service_eid=service_eid):
            actual = INTEREST_UNUSUAL
            price_mult = 0.24
            reason = "least-discerning counter might risk homemade trap stock"
        else:
            actual = INTEREST_REFUSED
            price_mult = 0.0
            reason = "homemade aerosol traps are not trusted stock"
    elif experimental:
        actual = INTEREST_REFUSED
        price_mult = 0.0
        reason = "homemade experimental stock has no trusted buyer"
    elif listed:
        actual = INTEREST_WANTED
        price_mult = 1.0
        reason = "already stocked"
    elif bool(profile.get("service_counter")) and not tags.intersection(profile["wanted"]):
        actual = INTEREST_REFUSED
        price_mult = 0.0
        reason = "service counter does not buy carried stock"
    elif archetype in BROAD_BUYER_ARCHETYPES:
        actual = INTEREST_WANTED if tags.intersection(profile["wanted"]) else INTEREST_ADJACENT
        price_mult = 0.86 if actual == INTEREST_WANTED else 0.68
        reason = "broad buyer"
    elif illegal and archetype not in SHADY_BUYER_ARCHETYPES:
        actual = INTEREST_REFUSED
        price_mult = 0.0
        reason = "too hot for this counter"
    elif restricted and dangerous and archetype not in TACTICAL_BUYER_ARCHETYPES:
        actual = INTEREST_REFUSED
        price_mult = 0.0
        reason = "too dangerous for this counter"
    elif dangerous and bool(profile.get("refuse_dangerous")):
        actual = INTEREST_REFUSED
        price_mult = 0.0
        reason = "wrong counter for gear like this"
    elif tags.intersection(profile["wanted"]):
        actual = INTEREST_WANTED
        price_mult = 1.0
        reason = "matches shop stock"
    elif tags.intersection(profile["adjacent"]):
        actual = INTEREST_ADJACENT
        price_mult = 0.62
        reason = "adjacent to shop stock"
    else:
        actual = INTEREST_UNUSUAL
        price_mult = 0.35
        reason = "unusual for this shop"

    if homemade_aerosol_trap and actual == INTEREST_UNUSUAL:
        accepted = True
    elif actual == INTEREST_UNUSUAL and not unusual_sale_allowed(sim, actor_eid, prop, entry, service_eid=service_eid):
        accepted = False
    else:
        accepted = actual != INTEREST_REFUSED

    visible, known = visible_store_interest(actual, sim=sim, actor_eid=actor_eid, prop=prop, entry=entry)
    pressure_weight = 0
    if actual == INTEREST_REFUSED:
        pressure_weight = 2 if illegal or dangerous else 1
    elif actual == INTEREST_UNUSUAL and not accepted:
        pressure_weight = 2 if illegal or dangerous else 1
    risk_label = ""
    if "stolen" in tags:
        risk_label = "stolen risk"
    elif "illegal" in tags:
        risk_label = "contraband"
    elif homemade_aerosol_trap:
        risk_label = "homemade contraband"
    elif restricted:
        risk_label = "restricted"
    elif experimental:
        risk_label = "experimental"
    elif dangerous:
        risk_label = "dangerous goods"

    pressure_label = ""
    pressure_note = ""
    pressure_value = 0.0
    if sim is not None and actual != INTEREST_REFUSED and isinstance(prop, Mapping):
        pressure = item_trade_pressure_bias(sim, prop, item_id)
        pressure_label = str(pressure.get("label", "") or "").strip()
        pressure_note = str(pressure.get("note", "") or "").strip()
        try:
            pressure_value = float(pressure.get("value", 0.0) or 0.0)
        except (TypeError, ValueError):
            pressure_value = 0.0
        try:
            price_mult *= float(pressure.get("sell_price_mult", 1.0) or 1.0)
        except (TypeError, ValueError):
            pass
        if pressure_label:
            reason = f"{reason}; {pressure_note or pressure_label}"

    visible_label = INTEREST_LABELS.get(visible, INTEREST_LABELS[INTEREST_UNUSUAL])
    actual_label = INTEREST_LABELS.get(actual, INTEREST_LABELS[INTEREST_UNUSUAL])
    if pressure_label and actual != INTEREST_REFUSED:
        visible_label = f"{visible_label}; {pressure_label}"
        actual_label = f"{actual_label}; {pressure_label}"

    return {
        "purchase_interest": visible,
        "interest_actual": actual,
        "interest_known": bool(known),
        "interest_label": visible_label,
        "actual_label": actual_label,
        "row_color": INTEREST_COLORS.get(visible, "item_restricted"),
        "price_mult": float(price_mult),
        "accepted": bool(accepted),
        "listed": bool(listed),
        "reason": reason,
        "profile_summary": str(profile.get("summary", "")).strip(),
        "pressure_weight": int(max(0, pressure_weight)),
        "can_attempt": actual in {INTEREST_WANTED, INTEREST_ADJACENT, INTEREST_UNUSUAL},
        "dangerous": bool(dangerous),
        "illegal": bool(illegal),
        "restricted": bool(restricted),
        "risk_label": risk_label,
        "trade_pressure_label": pressure_label,
        "trade_pressure_note": pressure_note,
        "trade_pressure_value": round(float(pressure_value), 3),
    }


def store_purchase_policy_summary(prop=None, store=None):
    archetype = store_archetype(prop, store)
    profile = _profile_for_archetype(archetype)
    summary = str(profile.get("summary", "")).strip() or "ordinary goods"
    if archetype in BROAD_BUYER_ARCHETYPES:
        return f"This place is a broad buyer: {summary}. They may still price strange goods cautiously."
    if bool(profile.get("refuse_dangerous")):
        return f"This place usually buys {summary}. Gear that looks dangerous or wildly mismatched usually stays off their counter."
    return f"This place usually buys {summary}. Off-list goods may get a low offer if the worker likes the ask."
