"""Directional, site-anchored organization supply agreements.

Agreements are intentionally concrete: a supplier, a receiver, a commodity,
and two real properties.  They can therefore author goods, appear in local
reports, and be damaged by ordinary events at either end of the route.
"""

from __future__ import annotations

from hashlib import blake2b
import random

from engine.events import Event
from engine.systems import System
from game.components import OrganizationProfile
from game.organizations import (
    actor_org_memberships,
    organization_policy_snapshot,
    organization_profile,
    property_organization_eid,
    record_organization_pressure,
    record_organization_relationship,
)


ORGANIZATION_SUPPLY_SCHEMA_VERSION = 1
ORGANIZATION_SUPPLY_INTERVAL = 900
ORGANIZATION_SUPPLY_DEFAULT_CADENCE = 1200
ORGANIZATION_SUPPLY_MAX_AGREEMENTS = 96

DRONE_COMMODITIES = frozenset({"drone", "drones", "drone_parts", "security_drones"})
WIRE_COMMODITIES = frozenset({"wire_gear", "wire_interfaces", "electronics", "signal_hardware"})


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


def _hash_int(*parts):
    payload = "|".join(_text(part) for part in parts).encode("utf-8")
    return int.from_bytes(blake2b(payload, digest_size=12).digest(), "big")


def _state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    state = traits.get("organization_supply")
    if not isinstance(state, dict):
        state = {}
        traits["organization_supply"] = state
    state["schema_version"] = ORGANIZATION_SUPPLY_SCHEMA_VERSION
    if not isinstance(state.get("agreements"), dict):
        state["agreements"] = {}
    state["next_agreement_id"] = max(1, _safe_int(state.get("next_agreement_id"), 1))
    state["last_seed_tick"] = _safe_int(state.get("last_seed_tick"), -1)
    state["last_update_tick"] = _safe_int(state.get("last_update_tick"), -1)
    state["seed_signature"] = _text(state.get("seed_signature"))
    return state


def ensure_organization_supply_state(sim):
    state = _state(sim)
    for agreement_id in tuple(state["agreements"]):
        row = _normalize_agreement(sim, agreement_id, state["agreements"].get(agreement_id))
        if row is None:
            state["agreements"].pop(agreement_id, None)
        else:
            state["agreements"][agreement_id] = row
    if len(state["agreements"]) > ORGANIZATION_SUPPLY_MAX_AGREEMENTS:
        ranked = sorted(
            state["agreements"].values(),
            key=lambda row: (_safe_int(row.get("last_delivery_tick"), -1), _text(row.get("agreement_id"))),
        )
        for row in ranked[: len(ranked) - ORGANIZATION_SUPPLY_MAX_AGREEMENTS]:
            state["agreements"].pop(row["agreement_id"], None)
    return state


def _org_ref(sim, organization_eid):
    organization_eid = _safe_int(organization_eid, 0)
    profile = organization_profile(sim, organization_eid) if organization_eid > 0 else None
    if profile is None:
        return None
    policy = organization_policy_snapshot(sim, organization_eid=organization_eid) or {}
    return {
        "organization_eid": organization_eid,
        "organization_key": _text(getattr(profile, "key", "")),
        "organization_name": _text(getattr(profile, "name", "")) or "Organization",
        "organization_kind": _key(getattr(profile, "kind", "")) or "other",
        "family": _key(policy.get("family")) or _key(getattr(profile, "kind", "")) or "other",
    }


def _property_ref(sim, property_id):
    property_id = _text(property_id)
    prop = getattr(sim, "properties", {}).get(property_id)
    if not property_id or not isinstance(prop, dict):
        return None
    return {
        "property_id": property_id,
        "property_name": _text(prop.get("name") or property_id),
    }


def _agreement_status(disruption, active=True):
    if not active:
        return "ended"
    disruption = max(0, min(100, _safe_int(disruption, 0)))
    if disruption >= 80:
        return "suspended"
    if disruption >= 40:
        return "strained"
    return "active"


def _normalize_agreement(sim, agreement_id, row):
    if not isinstance(row, dict):
        return None
    supplier = _org_ref(sim, row.get("supplier_org_eid"))
    receiver = _org_ref(sim, row.get("receiver_org_eid"))
    source = _property_ref(sim, row.get("source_property_id"))
    destination = _property_ref(sim, row.get("destination_property_id"))
    commodity = _key(row.get("commodity"))
    if supplier is None or receiver is None or source is None or destination is None or not commodity:
        return None
    disruption = max(0, min(100, _safe_int(row.get("disruption"), 0)))
    active = bool(row.get("active", True))
    cadence = max(120, _safe_int(row.get("cadence_ticks"), ORGANIZATION_SUPPLY_DEFAULT_CADENCE))
    result = dict(row)
    result.update({
        "schema_version": ORGANIZATION_SUPPLY_SCHEMA_VERSION,
        "agreement_id": _text(row.get("agreement_id")) or _text(agreement_id),
        "supplier_org_eid": supplier["organization_eid"],
        "supplier_org_key": supplier["organization_key"],
        "supplier_name": supplier["organization_name"],
        "supplier_family": supplier["family"],
        "receiver_org_eid": receiver["organization_eid"],
        "receiver_org_key": receiver["organization_key"],
        "receiver_name": receiver["organization_name"],
        "receiver_family": receiver["family"],
        "source_property_id": source["property_id"],
        "source_property_name": source["property_name"],
        "destination_property_id": destination["property_id"],
        "destination_property_name": destination["property_name"],
        "commodity": commodity,
        "purpose": _key(row.get("purpose")) or "trade",
        "direction": "supplier_to_receiver",
        "cadence_ticks": cadence,
        "next_delivery_tick": max(0, _safe_int(row.get("next_delivery_tick"), 0)),
        "last_delivery_tick": _safe_int(row.get("last_delivery_tick"), -1),
        "deliveries": max(0, _safe_int(row.get("deliveries"), 0)),
        "disruption": disruption,
        "flow_percent": max(0, 100 - disruption),
        "active": active,
        "status": _agreement_status(disruption, active=active),
        "visible": bool(row.get("visible", True)),
        "created_tick": max(0, _safe_int(row.get("created_tick"), 0)),
        "last_disruption_tick": _safe_int(row.get("last_disruption_tick"), -1),
        "last_disruption_reason": _key(row.get("last_disruption_reason")),
        "loop_id": _text(row.get("loop_id")),
    })
    history = row.get("history") if isinstance(row.get("history"), list) else []
    result["history"] = [dict(entry) for entry in history if isinstance(entry, dict)][-12:]
    return result


def _agreement_signature(supplier_org_eid, receiver_org_eid, commodity, source_property_id, destination_property_id):
    return ":".join((
        str(_safe_int(supplier_org_eid, 0)), str(_safe_int(receiver_org_eid, 0)),
        _key(commodity), _text(source_property_id), _text(destination_property_id),
    ))


def create_supply_agreement(
    sim,
    *,
    supplier_org_eid,
    receiver_org_eid,
    commodity,
    source_property_id,
    destination_property_id,
    purpose="trade",
    cadence_ticks=ORGANIZATION_SUPPLY_DEFAULT_CADENCE,
    visible=True,
    loop_id="",
):
    """Create/reuse a directional agreement anchored to two real sites."""

    supplier_org_eid = _safe_int(supplier_org_eid, 0)
    receiver_org_eid = _safe_int(receiver_org_eid, 0)
    if supplier_org_eid <= 0 or receiver_org_eid <= 0 or supplier_org_eid == receiver_org_eid:
        return None
    if _org_ref(sim, supplier_org_eid) is None or _org_ref(sim, receiver_org_eid) is None:
        return None
    if _property_ref(sim, source_property_id) is None or _property_ref(sim, destination_property_id) is None:
        return None
    commodity = _key(commodity)
    if not commodity:
        return None
    state = ensure_organization_supply_state(sim)
    signature = _agreement_signature(
        supplier_org_eid, receiver_org_eid, commodity, source_property_id, destination_property_id,
    )
    for existing in state["agreements"].values():
        if _text(existing.get("signature")) == signature:
            return dict(existing)

    serial = state["next_agreement_id"]
    state["next_agreement_id"] = serial + 1
    agreement_id = f"supply-{serial}"
    tick = _safe_int(getattr(sim, "tick", 0), 0)
    jitter = _hash_int(getattr(sim, "seed", 0), signature) % max(1, int(cadence_ticks) // 3)
    row = _normalize_agreement(sim, agreement_id, {
        "agreement_id": agreement_id,
        "signature": signature,
        "supplier_org_eid": supplier_org_eid,
        "receiver_org_eid": receiver_org_eid,
        "commodity": commodity,
        "source_property_id": _text(source_property_id),
        "destination_property_id": _text(destination_property_id),
        "purpose": purpose,
        "cadence_ticks": cadence_ticks,
        "next_delivery_tick": tick + 120 + int(jitter),
        "created_tick": tick,
        "visible": bool(visible),
        "active": True,
        "loop_id": loop_id,
        "history": [{"tick": tick, "kind": "agreement_created"}],
    })
    if row is None:
        return None
    state["agreements"][agreement_id] = row
    reason_tags = ("supply", commodity, _key(purpose))
    record_organization_relationship(
        sim,
        org_a_eid=supplier_org_eid,
        org_b_eid=receiver_org_eid,
        stance="transactional",
        confidence=0.62,
        reason_tags=reason_tags,
        source_event="supply_agreement",
        anchor_property_id=destination_property_id,
        visible=visible,
        visible_cue=f"marked consignments from {row['supplier_name']} are arriving for {row['receiver_name']}",
    )
    _surface_agreement(sim, row, source_event="supply_agreement")
    sim.emit(Event("organization_supply_agreement_created", **_event_payload(row)))
    return dict(row)


def _event_payload(row):
    return {
        "agreement_id": row.get("agreement_id"),
        "supplier_org_eid": row.get("supplier_org_eid"),
        "supplier_name": row.get("supplier_name"),
        "receiver_org_eid": row.get("receiver_org_eid"),
        "receiver_name": row.get("receiver_name"),
        "commodity": row.get("commodity"),
        "source_property_id": row.get("source_property_id"),
        "destination_property_id": row.get("destination_property_id"),
        "purpose": row.get("purpose"),
        "status": row.get("status"),
        "flow_percent": row.get("flow_percent"),
    }


def _surface_agreement(sim, row, *, source_event):
    if not bool(row.get("visible", True)):
        return
    commodity = _text(row.get("commodity")).replace("_", " ")
    status = _text(row.get("status")) or "active"
    if status == "suspended":
        cue = f"the {commodity} handoff from {row['supplier_name']} has stopped amid damaged routing and missing consignments"
        stance = "hostile"
    elif status == "strained":
        cue = f"late and mismatched {commodity} consignments show strain between {row['supplier_name']} and {row['receiver_name']}"
        stance = "competitive"
    else:
        cue = f"marked {commodity} consignments from {row['supplier_name']} are being received for {row['receiver_name']}"
        stance = "transactional"
    record_organization_pressure(
        sim,
        organization_eid=row["receiver_org_eid"],
        related_org_eid=row["supplier_org_eid"],
        pressure_kind=f"supply_{status}",
        stance=stance,
        reason_tags=("supply", row["commodity"], row["purpose"]),
        anchor_property_id=row["destination_property_id"],
        visible=True,
        visible_cue=cue,
        confidence=0.74,
        source_event=source_event,
        expires_tick=_safe_int(getattr(sim, "tick", 0), 0) + max(600, row["cadence_ticks"] * 2),
        pressure_key=f"organization_supply:{row['agreement_id']}:destination",
    )
    if status == "suspended":
        source_cue = f"idle pallets and reroute notices show the {commodity} line to {row['receiver_name']} has stopped"
    elif status == "strained":
        source_cue = f"held {commodity} crates and repeated recounts show the route to {row['receiver_name']} is slipping"
    else:
        source_cue = f"marked {commodity} consignments are staged outbound for {row['receiver_name']}"
    record_organization_pressure(
        sim,
        organization_eid=row["supplier_org_eid"],
        related_org_eid=row["receiver_org_eid"],
        pressure_kind=f"supply_{status}",
        stance=stance,
        reason_tags=("supply", row["commodity"], row["purpose"]),
        anchor_property_id=row["source_property_id"],
        visible=True,
        visible_cue=source_cue,
        confidence=0.72,
        source_event=source_event,
        expires_tick=_safe_int(getattr(sim, "tick", 0), 0) + max(600, row["cadence_ticks"] * 2),
        pressure_key=f"organization_supply:{row['agreement_id']}:source",
    )


def organization_supply_rows(
    sim,
    *,
    supplier_org_eid=None,
    receiver_org_eid=None,
    property_id=None,
    commodity=None,
    active_only=True,
    visible_only=False,
):
    state = ensure_organization_supply_state(sim)
    supplier_org_eid = _safe_int(supplier_org_eid, 0) or None
    receiver_org_eid = _safe_int(receiver_org_eid, 0) or None
    property_id = _text(property_id)
    commodity = _key(commodity)
    rows = []
    for row in state["agreements"].values():
        if active_only and not bool(row.get("active", True)):
            continue
        if visible_only and not bool(row.get("visible", True)):
            continue
        if supplier_org_eid and row.get("supplier_org_eid") != supplier_org_eid:
            continue
        if receiver_org_eid and row.get("receiver_org_eid") != receiver_org_eid:
            continue
        if property_id and property_id not in {row.get("source_property_id"), row.get("destination_property_id")}:
            continue
        if commodity and row.get("commodity") != commodity:
            continue
        rows.append(dict(row))
    rows.sort(key=lambda row: (_text(row.get("status")), _text(row.get("commodity")), _text(row.get("agreement_id"))))
    return tuple(rows)


def organization_supply_summary(row):
    if not isinstance(row, dict):
        return ""
    arrow = "->"
    commodity = _text(row.get("commodity")).replace("_", " ") or "goods"
    status = _text(row.get("status")) or "active"
    return (
        f"{row.get('supplier_name', 'supplier')} {arrow} {row.get('receiver_name', 'receiver')} | "
        f"{commodity} | {row.get('source_property_name', 'source')} to "
        f"{row.get('destination_property_name', 'destination')} | {status}, flow {int(row.get('flow_percent', 0))}%"
    )


def _profile_site_ids(sim, organization_eid):
    profile = organization_profile(sim, organization_eid)
    if profile is None:
        return ()
    ids = set(_text(value) for value in getattr(profile, "site_property_ids", ()) or () if _text(value))
    for link in getattr(profile, "site_links", ()) or ():
        if isinstance(link, dict) and bool(link.get("active", True)) and _text(link.get("property_id")):
            ids.add(_text(link.get("property_id")))
    return tuple(sorted(value for value in ids if isinstance(getattr(sim, "properties", {}).get(value), dict)))


def _site_score(sim, property_id, tokens):
    prop = getattr(sim, "properties", {}).get(property_id, {})
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    text = " ".join((
        _key(prop.get("name")), _key(prop.get("kind")), _key(metadata.get("archetype")),
        " ".join(_key(value) for value in metadata.get("site_services", ()) or ()),
    ))
    return sum(4 for token in tokens if token in text)


def _best_site(sim, organization_eid, tokens=()):
    ids = _profile_site_ids(sim, organization_eid)
    if not ids:
        return ""
    return sorted(ids, key=lambda property_id: (-_site_score(sim, property_id, tokens), property_id))[0]


def _family_rows(sim, family):
    rows = []
    for organization_eid in tuple(getattr(sim, "ecs").get(OrganizationProfile)):
        ref = _org_ref(sim, organization_eid)
        if ref is None:
            continue
        tags = {_key(tag) for tag in getattr(organization_profile(sim, organization_eid), "tags", ()) or ()}
        is_match = ref["family"] == family
        if family == "corporate":
            is_match = is_match or ref["organization_kind"] in {"corporation", "corporate"} or bool(tags & {"corporate", "corpsec"})
        elif family == "street_gang":
            is_match = is_match or ref["organization_kind"] in {"gang", "crew"} or bool(tags & {"gang", "street_gang"})
        elif family == "cult":
            is_match = is_match or ref["organization_kind"] == "cult" or "cult" in tags
        site_ids = _profile_site_ids(sim, organization_eid)
        if is_match and site_ids:
            rows.append({**ref, "site_ids": site_ids})
    rows.sort(key=lambda row: (row["organization_name"].lower(), row["organization_eid"]))
    return rows


def _cult_site_rows(sim):
    rows = []
    for cult in (getattr(sim, "cults", {}) or {}).get("cults", {}).values():
        if not isinstance(cult, dict) or bool(cult.get("disbanded")):
            continue
        org_eid = _safe_int(cult.get("organization_eid"), 0)
        meeting = cult.get("meeting") if isinstance(cult.get("meeting"), dict) else {}
        property_id = _text(meeting.get("property_id"))
        if _org_ref(sim, org_eid) is None or _property_ref(sim, property_id) is None:
            continue
        rows.append({"organization_eid": org_eid, "property_id": property_id, "cult": cult})
    return rows


def _supply_seed_signature(sim):
    org_parts = []
    for organization_eid, profile in tuple(getattr(sim, "ecs").get(OrganizationProfile).items()):
        site_ids = set(_text(value) for value in getattr(profile, "site_property_ids", ()) or () if _text(value))
        site_ids.update(
            _text(link.get("property_id"))
            for link in getattr(profile, "site_links", ()) or ()
            if isinstance(link, dict) and bool(link.get("active", True)) and _text(link.get("property_id"))
        )
        org_parts.append(f"{int(organization_eid)}:{','.join(sorted(site_ids))}")
    cult_parts = []
    for cult in (getattr(sim, "cults", {}) or {}).get("cults", {}).values():
        if isinstance(cult, dict) and not bool(cult.get("disbanded")):
            meeting = cult.get("meeting") if isinstance(cult.get("meeting"), dict) else {}
            cult_parts.append(f"{_safe_int(cult.get('organization_eid'), 0)}:{_text(meeting.get('property_id'))}")
    return f"{_hash_int(*sorted(org_parts), *sorted(cult_parts)):x}"


def seed_organization_supply_agreements(sim):
    """Seed bounded proof loops once their real organizations/sites exist."""

    state = _state(sim)
    seed_signature = _supply_seed_signature(sim)
    if seed_signature and seed_signature == _text(state.get("seed_signature")):
        return ()
    created = []
    corporations = _family_rows(sim, "corporate")
    gangs = _family_rows(sim, "street_gang")
    if corporations:
        for gang in gangs:
            destination = _best_site(sim, gang["organization_eid"], ("front", "fence", "safehouse", "gang"))
            if not destination:
                continue
            supplier = corporations[_hash_int(getattr(sim, "seed", 0), "gang-drone-supplier", gang["organization_eid"]) % len(corporations)]
            source = _best_site(sim, supplier["organization_eid"], ("drone", "electronic", "industrial", "security", "data"))
            row = create_supply_agreement(
                sim,
                supplier_org_eid=supplier["organization_eid"],
                receiver_org_eid=gang["organization_eid"],
                commodity="drone_parts",
                source_property_id=source,
                destination_property_id=destination,
                purpose="gang_drone_supply",
                cadence_ticks=1080,
            )
            if row and row.get("created_tick") == _safe_int(getattr(sim, "tick", 0), 0):
                created.append(row)

        for cult_row in _cult_site_rows(sim):
            cult_org_eid = cult_row["organization_eid"]
            cult_site = cult_row["property_id"]
            supplier = corporations[_hash_int(getattr(sim, "seed", 0), "cult-market-supplier", cult_org_eid) % len(corporations)]
            corp_site = _best_site(sim, supplier["organization_eid"], ("store", "office", "market", "electronic", "media"))
            if not corp_site:
                continue
            loop_id = f"consumer-loyalty:{supplier['organization_eid']}:{cult_org_eid}"
            goods = create_supply_agreement(
                sim,
                supplier_org_eid=supplier["organization_eid"],
                receiver_org_eid=cult_org_eid,
                commodity="status_goods",
                source_property_id=corp_site,
                destination_property_id=cult_site,
                purpose="consumer_loyalty",
                cadence_ticks=1320,
                loop_id=loop_id,
            )
            loyalty = create_supply_agreement(
                sim,
                supplier_org_eid=cult_org_eid,
                receiver_org_eid=supplier["organization_eid"],
                commodity="committed_customers",
                source_property_id=cult_site,
                destination_property_id=corp_site,
                purpose="loyalty_consumerism",
                cadence_ticks=1320,
                loop_id=loop_id,
            )
            for row in (goods, loyalty):
                if row and row.get("created_tick") == _safe_int(getattr(sim, "tick", 0), 0):
                    created.append(row)
    state["last_seed_tick"] = _safe_int(getattr(sim, "tick", 0), 0)
    state["seed_signature"] = seed_signature
    return tuple(created)


def _root_membership_eids(sim, actor_eid):
    eids = set()
    for row in actor_org_memberships(sim, actor_eid, active_only=True):
        eid = _safe_int(row.get("organization_eid"), 0)
        if eid <= 0:
            continue
        eids.add(eid)
        policy = organization_policy_snapshot(sim, organization_eid=eid) or {}
        root_eid = _safe_int(policy.get("root_organization_eid"), 0)
        if root_eid > 0:
            eids.add(root_eid)
    return eids


def drone_supply_agreement_for_actor(sim, actor_eid):
    membership_eids = _root_membership_eids(sim, actor_eid)
    if not membership_eids:
        return None
    candidates = []
    for row in organization_supply_rows(sim, active_only=True):
        if row.get("commodity") not in DRONE_COMMODITIES or row.get("status") == "suspended":
            continue
        receiver = row.get("receiver_org_eid")
        receiver_policy = organization_policy_snapshot(sim, organization_eid=receiver) or {}
        receiver_root = _safe_int(receiver_policy.get("root_organization_eid"), receiver)
        if receiver in membership_eids or receiver_root in membership_eids:
            candidates.append(row)
    if not candidates:
        return None
    return sorted(candidates, key=lambda row: (-_safe_int(row.get("flow_percent"), 0), _text(row.get("agreement_id"))))[0]


def manufacturing_organization_for_property(sim, prop, *, commodity=""):
    if not isinstance(prop, dict):
        return None
    property_id = _text(prop.get("id"))
    commodity = _key(commodity)
    candidates = []
    for row in organization_supply_rows(sim, property_id=property_id, active_only=True):
        if row.get("status") == "suspended":
            continue
        if commodity == "wire" and row.get("commodity") not in WIRE_COMMODITIES:
            continue
        if row.get("destination_property_id") == property_id:
            candidates.append(row)
    if candidates:
        candidates.sort(key=lambda row: (-_safe_int(row.get("flow_percent"), 0), _text(row.get("agreement_id"))))
        return _safe_int(candidates[0].get("supplier_org_eid"), 0) or None
    return property_organization_eid(sim, prop, ensure=False)


def disrupt_supply_agreement(sim, agreement_id, *, severity, reason, actor_eid=None, property_id=""):
    state = ensure_organization_supply_state(sim)
    row = state["agreements"].get(_text(agreement_id))
    if not isinstance(row, dict) or not bool(row.get("active", True)):
        return None
    tick = _safe_int(getattr(sim, "tick", 0), 0)
    old_status = row.get("status")
    row["disruption"] = min(100, max(0, _safe_int(row.get("disruption"), 0) + max(1, _safe_int(severity, 1))))
    row["flow_percent"] = max(0, 100 - row["disruption"])
    row["status"] = _agreement_status(row["disruption"], active=True)
    row["last_disruption_tick"] = tick
    row["last_disruption_reason"] = _key(reason)
    row["next_delivery_tick"] = max(_safe_int(row.get("next_delivery_tick"), tick), tick + row["cadence_ticks"] // 2)
    row.setdefault("history", []).append({
        "tick": tick,
        "kind": "disruption",
        "reason": _key(reason),
        "severity": max(1, _safe_int(severity, 1)),
        "property_id": _text(property_id),
        "actor_eid": _safe_int(actor_eid, 0) or None,
    })
    row["history"] = row["history"][-12:]
    state["agreements"][row["agreement_id"]] = row
    _surface_agreement(sim, row, source_event="organization_supply_disrupted")
    sim.emit(Event(
        "organization_supply_disrupted",
        **_event_payload(row),
        actor_eid=_safe_int(actor_eid, 0) or None,
        property_id=_text(property_id),
        reason=_key(reason),
        severity=max(1, _safe_int(severity, 1)),
        status_changed=old_status != row["status"],
    ))
    return dict(row)


def _apply_delivery_effect(sim, row):
    cult_state = getattr(sim, "cults", None)
    if not isinstance(cult_state, dict):
        return
    cults = cult_state.get("cults") if isinstance(cult_state.get("cults"), dict) else {}
    if row.get("purpose") == "consumer_loyalty":
        for cult in cults.values():
            if _safe_int(cult.get("organization_eid"), 0) != row.get("receiver_org_eid"):
                continue
            market = cult.setdefault("consumerism", {})
            market["goods_received"] = max(0, _safe_int(market.get("goods_received"), 0)) + 1
            market["loyalty_pressure"] = min(100, max(0, _safe_int(market.get("loyalty_pressure"), 0)) + max(1, row["flow_percent"] // 25))
            market["last_supplier_org_eid"] = row.get("supplier_org_eid")
            market["last_delivery_tick"] = _safe_int(getattr(sim, "tick", 0), 0)
    elif row.get("purpose") == "loyalty_consumerism":
        state = _state(sim)
        market = state.setdefault("consumer_markets", {}).setdefault(str(row.get("receiver_org_eid")), {})
        market["committed_customer_deliveries"] = max(0, _safe_int(market.get("committed_customer_deliveries"), 0)) + 1
        market["loyalty_value"] = max(0, _safe_int(market.get("loyalty_value"), 0)) + max(1, row["flow_percent"] // 20)
        market["last_delivery_tick"] = _safe_int(getattr(sim, "tick", 0), 0)


def advance_organization_supply(sim):
    state = ensure_organization_supply_state(sim)
    tick = _safe_int(getattr(sim, "tick", 0), 0)
    delivered = []
    for row in state["agreements"].values():
        if not bool(row.get("active", True)):
            continue
        if row.get("status") == "suspended":
            # Routes heal slowly enough that deliberate repeated disruption is
            # meaningful, but they do not become permanent dead simulation.
            row["disruption"] = max(0, row["disruption"] - 2)
            row["flow_percent"] = 100 - row["disruption"]
            row["status"] = _agreement_status(row["disruption"], active=True)
            _surface_agreement(sim, row, source_event="organization_supply_recovery")
            continue
        if tick < _safe_int(row.get("next_delivery_tick"), 0):
            continue
        row["deliveries"] = _safe_int(row.get("deliveries"), 0) + 1
        row["last_delivery_tick"] = tick
        row["next_delivery_tick"] = tick + row["cadence_ticks"]
        row["disruption"] = max(0, row["disruption"] - 4)
        row["flow_percent"] = 100 - row["disruption"]
        row["status"] = _agreement_status(row["disruption"], active=True)
        row.setdefault("history", []).append({"tick": tick, "kind": "delivery", "flow_percent": row["flow_percent"]})
        row["history"] = row["history"][-12:]
        _apply_delivery_effect(sim, row)
        _surface_agreement(sim, row, source_event="organization_supply_delivery")
        sim.emit(Event("organization_supply_delivery", **_event_payload(row), delivery_number=row["deliveries"]))
        delivered.append(dict(row))
    state["last_update_tick"] = tick
    return tuple(delivered)


class OrganizationSupplySystem(System):
    def __init__(self, sim):
        self.sim = sim
        self._last_update_tick = -999999
        ensure_organization_supply_state(sim)
        sim.events.subscribe("property_tamper", self.on_property_tamper)
        sim.events.subscribe("item_stolen", self.on_item_stolen)
        sim.events.subscribe("action_offense", self.on_action_offense)

    def update(self):
        tick = _safe_int(getattr(self.sim, "tick", 0), 0)
        if tick - self._last_update_tick < ORGANIZATION_SUPPLY_INTERVAL:
            return
        self._last_update_tick = tick
        seed_organization_supply_agreements(self.sim)
        advance_organization_supply(self.sim)

    def _property_id_for_event(self, event):
        property_id = _text(event.data.get("property_id"))
        if property_id and isinstance(getattr(self.sim, "properties", {}).get(property_id), dict):
            return property_id
        try:
            prop = self.sim.property_covering(int(event.data.get("x")), int(event.data.get("y")), int(event.data.get("z", 0)))
        except (TypeError, ValueError, AttributeError):
            prop = None
        return _text((prop or {}).get("id"))

    def _disrupt_at_event(self, event, severity, reason):
        property_id = self._property_id_for_event(event)
        if not property_id:
            return ()
        changed = []
        for row in organization_supply_rows(self.sim, property_id=property_id, active_only=True):
            result = disrupt_supply_agreement(
                self.sim,
                row["agreement_id"],
                severity=severity,
                reason=reason,
                actor_eid=event.data.get("offender_eid") or event.data.get("eid"),
                property_id=property_id,
            )
            if result:
                changed.append(result)
        return tuple(changed)

    def on_property_tamper(self, event):
        self._disrupt_at_event(event, 18, "property_tamper")

    def on_item_stolen(self, event):
        self._disrupt_at_event(event, 12, "item_stolen")

    def on_action_offense(self, event):
        context = _key(event.data.get("context"))
        if context not in {"arson", "explosive_discharge", "vehicle_impact", "homicide"}:
            return
        self._disrupt_at_event(event, 24 if context != "homicide" else 10, context)


__all__ = [
    "DRONE_COMMODITIES",
    "WIRE_COMMODITIES",
    "OrganizationSupplySystem",
    "advance_organization_supply",
    "create_supply_agreement",
    "disrupt_supply_agreement",
    "drone_supply_agreement_for_actor",
    "ensure_organization_supply_state",
    "manufacturing_organization_for_property",
    "organization_supply_rows",
    "organization_supply_summary",
    "seed_organization_supply_agreements",
]
