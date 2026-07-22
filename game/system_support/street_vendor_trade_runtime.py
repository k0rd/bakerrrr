"""Street-contact trade helpers.

This module keeps street commerce as a shared read model for dialogue and the
trade panel. It deliberately stays lighter than storefront trade: contacts can
buy, sell, or both, but they are not property-backed shops.
"""

from __future__ import annotations

import random
from collections.abc import Mapping

from game.components import BehaviorProfile, Inventory, Occupation, OrganizationAffiliations, Position
from game.drone_distribution import drone_distribution_metadata, drone_street_vendor_item_pool
from game.wire_distribution import wire_distribution_metadata, wire_street_vendor_item_pool
from game.wire_data_market import wire_data_street_sell_rows
from game.item_semantics import item_entry_is_critical_quest_item, item_legal_status as _item_legal_status, item_tags as _item_tags
from game.items import ITEM_CATALOG, is_credstick_item, item_display_name
from game.organizations import actor_org_memberships
from game.property_runtime import property_is_vehicle as _property_is_vehicle, vehicle_label as _vehicle_label
from game.system_support.npc_behavior_runtime import (
    BEHAVIOR_BUY_DESIRED_DRUG,
    BEHAVIOR_BUY_PLAYER_GOODS,
    BEHAVIOR_COMMIT_PLANNED_CRIME,
    BEHAVIOR_SEEK_CRIMINAL_AFFILIATION,
    _actor_behavior_value,
    _behavior_preference,
    _street_buy_candidate_rows_for_inventory,
    _street_buy_terms,
    _street_item_price,
)
from game.system_support.entity_naming import _entity_viewer_display_name


STREET_TRADE_SOURCE_KIND = "street_vendor"
STREET_TRADE_CRITICAL_QUEST_ITEM_COLOR = "inventory_critical_quest"

DRUG_STOCK_POOL = (
    "cocaine_bindle",
    "black_market_stim",
    "mdma_capsule",
    "lsd_blotter",
    "smoke_tab",
    "shiver_patch",
    "sedative_ampoule",
    "burner_serum",
)

AEROSOL_STOCK_POOL = (
    "dissociative_aerosol",
    "hallucinogen_aerosol",
    "tear_gas_canister",
    "toxic_aerosol_canister",
    "smoke_grenade",
)

CONTRABAND_STOCK_POOL = (
    "lockpick_kit",
    "glass_cutter",
    "hotwire_leads",
    "forged_badge",
    "cloned_thumb",
) + DRUG_STOCK_POOL + AEROSOL_STOCK_POOL

GUN_STOCK_POOL = (
    "holdout_pistol",
    "rust_revolver",
    "machine_pistol",
    "compact_smg",
    "sawed_off_shotgun",
    "light_ammo_box",
    "pocket_light_rounds",
    "buckshot_pouch",
    "shell_bandolier",
)

GANG_STOCK_POOL = (
    "lockpick_kit",
    "glass_cutter",
    "hotwire_leads",
    "forged_badge",
    "holdout_pistol",
    "rust_revolver",
    "shiv_knife",
    "compact_smg",
    "cocaine_bindle",
    "black_market_stim",
    "shiver_patch",
    "sedative_ampoule",
    "dissociative_aerosol",
    "toxic_aerosol_canister",
)

STREET_VENDOR_KINDS = {
    "drug_seeker",
    "drug_pusher",
    "alley_market",
    "friend_of_friend",
    "gang_fence",
    "vehicle_gun_vendor",
}


def _key(value) -> str:
    return str(value or "").strip().lower()


def _as_tuple(value):
    if value is None:
        return ()
    if isinstance(value, str):
        return (value,)
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(value)
    return (value,)


def _safe_float(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _safe_int(value, default=0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _pressure_score(value) -> int:
    tier = _key(value)
    if tier in {"high", "hot", "red"}:
        return 2
    if tier in {"medium", "med", "warm", "yellow"}:
        return 1
    return 0


def _heat_tolerance_score(value) -> int:
    if isinstance(value, (int, float)):
        return max(0, min(2, int(value)))
    tier = _key(value)
    if tier in {"high", "hot", "red"}:
        return 2
    if tier in {"medium", "med", "warm", "yellow", "tolerant"}:
        return 1
    return 0


def _context_standing(context) -> float:
    if not isinstance(context, Mapping):
        return 0.0
    return max(
        _safe_float(context.get("contact_standing"), 0.0),
        _safe_float(context.get("social_standing"), 0.0),
        _safe_float(context.get("rapport"), 0.0),
    )


def _pusher_pressure_gate(vendor_kind, prefs, context):
    if _key(vendor_kind) != "drug_pusher":
        return {
            "blocked": False,
            "blocked_reason": "",
            "pusher_refusal_reason": "",
            "heat_tolerance": _key(prefs.get("heat_tolerance") or prefs.get("street_heat_tolerance")),
        }
    pressure = _pressure_score(context.get("pressure_tier"))
    attention = _safe_int(context.get("pressure_attention"), 0)
    tolerance = _heat_tolerance_score(prefs.get("heat_tolerance", prefs.get("street_heat_tolerance", "low")))
    trusted = _context_standing(context) >= 0.58
    extreme_attention = attention >= 94
    tense_attention = attention >= 90
    if extreme_attention and not (trusted and tolerance >= 2 and attention < 94):
        return {
            "blocked": True,
            "blocked_reason": "ambient_heat",
            "pusher_refusal_reason": "too_hot",
            "heat_tolerance": "high",
            "pressure_attention": attention,
        }
    if tense_attention and not (trusted or tolerance >= 1):
        return {
            "blocked": True,
            "blocked_reason": "ambient_heat",
            "pusher_refusal_reason": "wary_heat",
            "heat_tolerance": "medium" if tolerance >= 1 else "low",
            "pressure_attention": attention,
        }
    return {
        "blocked": False,
        "blocked_reason": "",
        "pusher_refusal_reason": "",
        "heat_tolerance": "medium" if tolerance >= 1 or trusted else "low",
        "pressure_attention": attention,
    }


def _career(sim, eid) -> str:
    occupation = sim.ecs.get(Occupation).get(eid) if sim is not None else None
    return _key(getattr(occupation, "career", ""))


def _inventory(sim, eid):
    return sim.ecs.get(Inventory).get(eid) if sim is not None else None


def _position(sim, eid):
    return sim.ecs.get(Position).get(eid) if sim is not None else None


def _behavior_preferences(sim, eid) -> dict:
    profile = sim.ecs.get(BehaviorProfile).get(eid) if sim is not None else None
    preferences = getattr(profile, "preferences", None)
    return dict(preferences) if isinstance(preferences, dict) else {}


def _criminal_affiliation_profile(sim, eid) -> dict:
    rows = ()
    try:
        rows = actor_org_memberships(sim, eid, active_only=True)
    except Exception:  # noqa: BLE001 - profile reads should not break dialogue
        rows = ()
    gang = False
    criminal = False
    names = []
    for row in tuple(rows or ()):
        kind = _key(row.get("organization_kind"))
        key = _key(row.get("organization_key"))
        name = str(row.get("organization_name", "") or "").strip()
        text = " ".join(bit for bit in (kind, key, name.lower()) if bit)
        if kind in {"gang", "crew"} or "gang" in text or "street_gang" in text:
            gang = True
        if gang or "criminal" in text or "syndicate" in text or "smuggl" in text:
            criminal = True
        if name:
            names.append(name)
    if not criminal:
        affiliations = sim.ecs.get(OrganizationAffiliations).get(eid) if sim is not None else None
        criminal = bool(affiliations and getattr(affiliations, "memberships", None))
    return {
        "gang_affiliated": bool(gang),
        "criminal_affiliated": bool(criminal),
        "organization_names": tuple(names[:2]),
    }


def _nearby_vehicle_profile(sim, eid, *, radius=2) -> dict:
    pos = _position(sim, eid)
    if pos is None:
        return {}
    best = None
    for prop in getattr(sim, "properties", {}).values():
        if not isinstance(prop, Mapping) or not _property_is_vehicle(prop):
            continue
        if _safe_int(prop.get("z"), _safe_int(getattr(pos, "z", 0))) != _safe_int(getattr(pos, "z", 0)):
            continue
        dist = abs(_safe_int(prop.get("x")) - int(pos.x)) + abs(_safe_int(prop.get("y")) - int(pos.y))
        if dist > int(radius):
            continue
        if best is None or dist < best[0]:
            best = (dist, prop)
    if best is None:
        return {}
    prop = best[1]
    return {
        "near_vehicle": True,
        "vehicle_id": str(prop.get("id", "") or "").strip(),
        "vehicle_name": _vehicle_label(prop),
        "distance": int(best[0]),
    }


def _stock_pool_for_kind(vendor_kind):
    kind = _key(vendor_kind)
    if kind == "drug_pusher":
        return DRUG_STOCK_POOL
    if kind == "vehicle_gun_vendor":
        return GUN_STOCK_POOL + drone_street_vendor_item_pool(kind) + wire_street_vendor_item_pool(kind)
    if kind == "gang_fence":
        return GANG_STOCK_POOL + drone_street_vendor_item_pool(kind) + wire_street_vendor_item_pool(kind)
    if kind == "alley_market":
        return (
            "lockpick_kit",
            "glass_cutter",
            "hotwire_leads",
            "forged_badge",
            "cloned_thumb",
            "smoke_grenade",
            "tear_gas_canister",
            "holdout_pistol",
            "rust_revolver",
        ) + drone_street_vendor_item_pool(kind) + wire_street_vendor_item_pool(kind)
    if kind == "friend_of_friend":
        return (
            "smoke_tab",
            "mdma_capsule",
            "lockpick_kit",
            "hotwire_leads",
            "forged_badge",
        )
    return ()


def _stock_count_for_kind(vendor_kind):
    kind = _key(vendor_kind)
    if kind == "vehicle_gun_vendor":
        return 3
    if kind == "gang_fence":
        return 4
    if kind == "alley_market":
        return 3
    if kind == "friend_of_friend":
        return 2
    if kind == "drug_pusher":
        return 2
    return 0


def _sell_price_mult_for_kind(vendor_kind, *, entry=None):
    kind = _key(vendor_kind)
    metadata = entry.get("metadata") if isinstance(entry, Mapping) and isinstance(entry.get("metadata"), Mapping) else {}
    hot = bool(metadata.get("street_vendor_hot") or metadata.get("latent_claim_violation"))
    if kind == "gang_fence":
        return 0.72 if hot else 0.88
    if kind == "alley_market":
        return 0.82 if hot else 1.05
    if kind == "friend_of_friend":
        return 0.95 if hot else 1.12
    if kind == "vehicle_gun_vendor":
        return 1.22
    if kind == "drug_pusher":
        return 1.34
    return 1.0


def _buy_note_for_kind(vendor_kind):
    kind = _key(vendor_kind)
    if kind == "gang_fence":
        return "gang contact; hot/stolen goods move cheap"
    if kind == "vehicle_gun_vendor":
        return "vehicle-side arms trade"
    if kind == "drug_pusher":
        return "street drug stock; heat changes the handoff"
    if kind == "alley_market":
        return "alley market stock"
    if kind == "friend_of_friend":
        return "quiet friend-of-friend stock"
    return "street contact"


def _sell_note_for_kind(vendor_kind):
    kind = _key(vendor_kind)
    if kind == "drug_seeker":
        return "looking for specific stock"
    if kind == "drug_pusher":
        return "moves drug stock, but heat can close the window"
    if kind == "gang_fence":
        return "will move contraband and hot/stolen goods"
    if kind == "vehicle_gun_vendor":
        return "will move weapons and ammunition"
    if kind == "alley_market":
        return "broad street buyer"
    return "quiet street buyer"


def _infer_vendor_kind(sim, contact_eid, *, context=None):
    prefs = _behavior_preferences(sim, contact_eid)
    explicit = _key(prefs.get("street_vendor_kind") or prefs.get("vendor_kind"))
    if explicit in STREET_VENDOR_KINDS:
        return explicit

    career = _career(sim, contact_eid)
    org = _criminal_affiliation_profile(sim, contact_eid)
    vehicle = _nearby_vehicle_profile(sim, contact_eid)
    buy_desired = _actor_behavior_value(sim, contact_eid, BEHAVIOR_BUY_DESIRED_DRUG, 0.0)
    buy_goods = _actor_behavior_value(sim, contact_eid, BEHAVIOR_BUY_PLAYER_GOODS, 0.0)
    planned_crime = _actor_behavior_value(sim, contact_eid, BEHAVIOR_COMMIT_PLANNED_CRIME, 0.0)
    affiliation = _actor_behavior_value(sim, contact_eid, BEHAVIOR_SEEK_CRIMINAL_AFFILIATION, 0.0)

    if vehicle.get("near_vehicle") and any(token in career for token in ("gun", "arms", "weapon", "smuggler", "runner", "fence")):
        return "vehicle_gun_vendor"
    if org.get("gang_affiliated"):
        return "gang_fence"
    if any(token in career for token in ("dealer", "pusher")):
        return "drug_pusher"
    if any(token in career for token in ("gun", "arms", "weapon")):
        return "vehicle_gun_vendor" if vehicle.get("near_vehicle") else "alley_market"
    if any(token in career for token in ("fence", "fixer", "black_market", "broker", "smuggler")):
        return "gang_fence" if org.get("criminal_affiliated") else "alley_market"
    if max(planned_crime, affiliation) >= 0.55:
        return "gang_fence" if org.get("criminal_affiliated") else "alley_market"
    if buy_desired >= 0.2 and buy_goods < 0.35:
        return "drug_seeker"
    if buy_desired >= 0.55:
        return "drug_pusher"
    return ""


def street_vendor_sell_interest_terms(sim, contact_eid, *, district_type="", career=""):
    terms = _street_buy_terms(sim, contact_eid, district_type=district_type, career=career)
    if not isinstance(terms, dict):
        return None
    return dict(terms)


def street_vendor_sell_rows(sim, contact_eid, player_eid, profile=None):
    inventory = _inventory(sim, player_eid)
    if inventory is None:
        return []
    profile = profile or street_vendor_contact_profile(sim, contact_eid, player_eid)
    terms = profile.get("sell_terms") if isinstance(profile, Mapping) else None
    if not isinstance(terms, dict):
        return []
    district_type = _key((profile or {}).get("district_type"))
    career = _key((profile or {}).get("career"))
    rows = _street_buy_candidate_rows_for_inventory(
        sim,
        contact_eid,
        inventory,
        district_type=district_type,
        career=career,
        terms=terms,
    )
    out = []
    for row in rows:
        item_id = _key(row.get("item_id"))
        if not item_id:
            continue
        source_entry = row.get("entry") if isinstance(row.get("entry"), Mapping) else row
        tags = _item_tags(source_entry, item_catalog=ITEM_CATALOG)
        if "experimental" in tags or "aerosol_trap" in tags:
            continue
        illegal = bool(row.get("illegal"))
        desired = bool(row.get("desired"))
        label = "premium wanted" if desired else _sell_note_for_kind((profile or {}).get("vendor_kind"))
        row_color = "property_service" if desired else ("item_illegal" if illegal else "item_tool")
        if item_entry_is_critical_quest_item(source_entry):
            row_color = STREET_TRADE_CRITICAL_QUEST_ITEM_COLOR
        out.append({
            **dict(row),
            "glyph": str(ITEM_CATALOG.get(item_id, {}).get("glyph", "*") or "*")[:1],
            "listed": False,
            "purchase_interest": "wanted",
            "interest_label": label,
            "interest_known": True,
            "interest_actual": "wanted",
            "interest_actual_label": label,
            "row_color": row_color,
            "row_badge": "premium" if desired else ("contraband" if illegal else "wanted"),
            "risk_label": "contraband risk" if illegal else "",
            "source_kind": STREET_TRADE_SOURCE_KIND,
        })
    out.extend(wire_data_street_sell_rows(sim, contact_eid, player_eid, profile=profile))
    return out


def _entry_is_vendor_stock(entry):
    metadata = entry.get("metadata") if isinstance(entry, Mapping) and isinstance(entry.get("metadata"), Mapping) else {}
    return bool(metadata.get("street_vendor_stock") or metadata.get("street_vendor_sellable"))


def _stock_entry_label(entry):
    metadata = entry.get("metadata") if isinstance(entry, Mapping) and isinstance(entry.get("metadata"), Mapping) else {}
    if metadata.get("street_vendor_hot"):
        return "hot/stolen discount"
    if _item_legal_status(entry, item_catalog=ITEM_CATALOG) in {"illegal", "stolen"}:
        return "contraband risk"
    if _item_legal_status(entry, item_catalog=ITEM_CATALOG) == "restricted":
        return "restricted street stock"
    return "street stock"


def _stock_entry_color(entry):
    metadata = entry.get("metadata") if isinstance(entry, Mapping) and isinstance(entry.get("metadata"), Mapping) else {}
    if metadata.get("street_vendor_hot"):
        return "item_restricted"
    if _item_legal_status(entry, item_catalog=ITEM_CATALOG) in {"illegal", "stolen"}:
        return "item_illegal"
    if _item_legal_status(entry, item_catalog=ITEM_CATALOG) == "restricted":
        return "item_restricted"
    return "property_service"


def street_vendor_buy_rows(sim, contact_eid, player_eid, profile=None):
    inventory = _inventory(sim, contact_eid)
    if inventory is None:
        return []
    profile = profile or street_vendor_contact_profile(sim, contact_eid, player_eid)
    vendor_kind = _key((profile or {}).get("vendor_kind"))
    rows = []
    for entry in list(getattr(inventory, "items", ()) or ()):
        item_id = _key(entry.get("item_id"))
        if not item_id or is_credstick_item(item_id):
            continue
        if not _entry_is_vendor_stock(entry):
            continue
        stock = max(1, _safe_int(entry.get("quantity"), 1))
        unit_entry = {**dict(entry), "quantity": 1}
        price = _street_item_price(unit_entry, mult=_sell_price_mult_for_kind(vendor_kind, entry=entry))
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        hot = bool(metadata.get("street_vendor_hot") or metadata.get("latent_claim_violation"))
        illegal = _item_legal_status(entry, item_catalog=ITEM_CATALOG) in {"illegal", "stolen"}
        label = _stock_entry_label(entry)
        rows.append({
            "entry": entry,
            "instance_id": entry.get("instance_id"),
            "item_id": item_id,
            "item_name": item_display_name(item_id, metadata=entry.get("metadata"), item_catalog=ITEM_CATALOG),
            "glyph": str(ITEM_CATALOG.get(item_id, {}).get("glyph", "*") or "*")[:1],
            "price": int(max(1, price)),
            "base_price": int(max(1, _street_item_price(unit_entry, mult=1.0))),
            "stock": int(stock),
            "interest_label": label,
            "interest_known": True,
            "purchase_interest": "street_stock",
            "row_color": _stock_entry_color(entry),
            "row_badge": "hot" if hot else ("contraband" if illegal else "stock"),
            "risk_label": "stolen risk" if hot else ("contraband risk" if illegal else ""),
            "hot": bool(hot),
            "illegal": bool(illegal),
            "source_kind": STREET_TRADE_SOURCE_KIND,
        })
    rows.sort(key=lambda row: (int(row.get("price", 0)), str(row.get("item_id", "")), str(row.get("instance_id", ""))))
    return rows


def street_vendor_contact_profile(sim, contact_eid, player_eid, *, context=None):
    context = context if isinstance(context, Mapping) else {}
    guarded = bool(context.get("guarded"))
    district_type = _key(context.get("district_type"))
    career = _key(context.get("career")) or _career(sim, contact_eid)
    prefs = _behavior_preferences(sim, contact_eid)
    vendor_kind = _infer_vendor_kind(sim, contact_eid, context=context)
    vehicle = _nearby_vehicle_profile(sim, contact_eid)
    org = _criminal_affiliation_profile(sim, contact_eid)
    pressure_gate = _pusher_pressure_gate(vendor_kind, prefs, context)
    pressure_blocked = bool(pressure_gate.get("blocked"))
    terms = street_vendor_sell_interest_terms(sim, contact_eid, district_type=district_type, career=career)
    sell_rows = []
    if terms and not guarded and not pressure_blocked:
        inventory = _inventory(sim, player_eid)
        sell_rows = _street_buy_candidate_rows_for_inventory(
            sim,
            contact_eid,
            inventory,
            district_type=district_type,
            career=career,
            terms=terms,
        ) if inventory is not None else []

    explicit_modes = {
        _key(value)
        for value in _as_tuple(prefs.get("street_vendor_modes"))
        if _key(value) in {"buy", "sell"}
    }
    stock_pool = tuple(_key(item_id) for item_id in _as_tuple(prefs.get("street_sell_item_ids")) if _key(item_id)) or _stock_pool_for_kind(vendor_kind)
    current_buy_rows = street_vendor_buy_rows(sim, contact_eid, player_eid, {"vendor_kind": vendor_kind}) if not guarded and not pressure_blocked else []

    available = []
    if not guarded and not pressure_blocked and (sell_rows or "sell" in explicit_modes):
        available.append("sell")
    if not guarded and not pressure_blocked and (current_buy_rows or stock_pool or "buy" in explicit_modes):
        available.append("buy")

    if explicit_modes:
        available = [mode for mode in ("sell", "buy") if mode in explicit_modes and mode in set(available)]

    if "sell" in available and sell_rows:
        default_mode = "sell"
    elif "buy" in available:
        default_mode = "buy"
    elif available:
        default_mode = available[0]
    else:
        default_mode = "sell"

    contact_label = _entity_viewer_display_name(
        sim,
        contact_eid,
        viewer_eid=player_eid,
        title_case=True,
    )
    notes = []
    if "sell" in available:
        notes.append(_sell_note_for_kind(vendor_kind))
    if "buy" in available:
        notes.append(_buy_note_for_kind(vendor_kind))
    if vehicle.get("near_vehicle") and vendor_kind == "vehicle_gun_vendor":
        notes.append(f"near {vehicle.get('vehicle_name')}")
    organization_names = tuple(org.get("organization_names", ()) or ())
    if organization_names and vendor_kind == "gang_fence":
        notes.append(f"{organization_names[0]} connected")
    if pressure_gate.get("pusher_refusal_reason") == "too_hot":
        notes.append("too much attention for a handoff")
    elif pressure_gate.get("pusher_refusal_reason") == "wary_heat":
        notes.append("wary of the attention")

    return {
        "available": bool(available),
        "contact_eid": contact_eid,
        "contact_name": contact_label,
        "vendor_kind": vendor_kind,
        "available_modes": tuple(available),
        "default_mode": default_mode,
        "district_type": district_type,
        "career": career,
        "guarded": guarded,
        "sell_terms": terms,
        "sell_row_count": len(sell_rows),
        "stock_pool": tuple(item_id for item_id in stock_pool if item_id in ITEM_CATALOG),
        "stock_count": _safe_int(prefs.get("street_stock_count"), _stock_count_for_kind(vendor_kind)),
        "stock_note": _buy_note_for_kind(vendor_kind),
        "sell_note": _sell_note_for_kind(vendor_kind),
        "contact_note": "; ".join(bit for bit in notes if bit),
        "blocked_reason": str(pressure_gate.get("blocked_reason", "") or ""),
        "pusher_refusal_reason": str(pressure_gate.get("pusher_refusal_reason", "") or ""),
        "heat_tolerance": str(pressure_gate.get("heat_tolerance", "") or ""),
        "pressure_tier": _key(context.get("pressure_tier")),
        "pressure_attention": _safe_int(context.get("pressure_attention"), 0),
        "gang_affiliated": bool(org.get("gang_affiliated")),
        "criminal_affiliated": bool(org.get("criminal_affiliated")),
        "near_vehicle": bool(vehicle.get("near_vehicle")),
        "vehicle_name": str(vehicle.get("vehicle_name", "") or "").strip(),
    }


def ensure_street_vendor_stock(sim, contact_eid, player_eid, profile=None):
    profile = dict(profile or street_vendor_contact_profile(sim, contact_eid, player_eid))
    inventory = _inventory(sim, contact_eid)
    if inventory is None:
        inventory = Inventory(capacity=8)
        sim.ecs.add(contact_eid, inventory)
    seeded = getattr(sim, "street_vendor_stock_seeded", None)
    if not isinstance(seeded, dict):
        seeded = {}
        sim.street_vendor_stock_seeded = seeded
    seed_key = str(contact_eid)
    if seeded.get(seed_key):
        return profile
    pool = [item_id for item_id in tuple(profile.get("stock_pool", ()) or ()) if item_id in ITEM_CATALOG]
    if not pool:
        seeded[seed_key] = True
        return profile
    count = max(0, min(6, _safe_int(profile.get("stock_count"), 0)))
    if count <= 0:
        seeded[seed_key] = True
        return profile
    rng = random.Random(f"{getattr(sim, 'seed', 0)}:street-vendor-stock:{contact_eid}:{profile.get('vendor_kind')}:{len(pool)}")
    rng.shuffle(pool)
    for idx, item_id in enumerate(pool[:count]):
        item_def = ITEM_CATALOG.get(item_id, {})
        stack_max = max(1, _safe_int(item_def.get("stack_max"), 1))
        quantity = 1
        if stack_max > 1 and idx == 0:
            quantity = min(stack_max, 2 + rng.randrange(2))
        vendor_kind = _key(profile.get("vendor_kind"))
        hot = bool(
            vendor_kind in {"gang_fence", "alley_market"}
            and (idx == 0 if vendor_kind == "gang_fence" else rng.random() < 0.42)
        )
        metadata = {
            "street_vendor_stock": True,
            "street_vendor_kind": vendor_kind,
            "street_vendor_seed_tick": int(getattr(sim, "tick", 0)),
            "source_context": "street_vendor_stock",
            "source_actor_eid": contact_eid,
            "last_transfer_tick": int(getattr(sim, "tick", 0)),
            "last_transfer_kind": "street_vendor_stock",
            "last_holder_eid": contact_eid,
        }
        if hot:
            metadata.update({
                "street_vendor_hot": True,
                "latent_claim_violation": True,
                "source_context": "street_vendor_hot_goods",
                "source_owner_tag": "unknown",
                "stolen": True,
            })
        metadata = drone_distribution_metadata(
            item_id,
            metadata,
            source_context="street_vendor_stock",
            distribution_context=vendor_kind,
            seed_token=f"{getattr(sim, 'seed', 0)}:{contact_eid}:{idx}",
            item_catalog=ITEM_CATALOG,
        )
        metadata = wire_distribution_metadata(
            item_id,
            metadata,
            source_context="street_vendor_stock",
            distribution_context=vendor_kind,
            seed_token=f"{getattr(sim, 'seed', 0)}:{contact_eid}:{idx}",
            item_catalog=ITEM_CATALOG,
        )
        inventory.add_item(
            item_id=item_id,
            quantity=quantity,
            stack_max=stack_max,
            instance_factory=sim.new_item_instance_id,
            owner_eid=contact_eid,
            owner_tag="npc",
            metadata=metadata,
        )
    seeded[seed_key] = True
    return profile
