"""Person-specific coercion backed by acquired wire blackmail records.

Leverage is intentionally separate from friendship and ordinary contact standing.
Compliance can produce a useful obligation while still damaging trust and building
fear, resentment, and future retaliation pressure.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from engine.events import Event
from game.components import (
    AI,
    ContactLedger,
    FinancialProfile,
    Inventory,
    NPCMemory,
    NPCTraits,
    PlayerAssets,
    Position,
)
from game.items import ITEM_CATALOG, is_credstick_item, item_display_name, item_inventory_slot_cost
from game.property_access import (
    apply_controller_intrusion,
    grant_controller_access_record,
    property_access_controller,
    property_apertures,
    sync_property_access_controller,
)
from game.property_keys import (
    inventory_matching_property_credential,
    property_lock_state,
)
from game.property_doors import _set_property_apertures_locked
from game.property_runtime import (
    building_id_from_property,
    controller_holder_for_actor,
    property_covering,
    property_infrastructure_role,
    property_is_storefront,
    property_linked_building_id,
    property_linked_property_id,
)
from game.system_support.container_runtime import _unlink_removed_item_from_gear
from game.system_support.npc_income_runtime import inventory_liquid_credits, spend_npc_wallet_credits


WIRE_DATA_ITEM_ID = "wire_data_cache"
LEVERAGE_SCHEMA_VERSION = 2
LEVERAGE_TRADE_DURATION = 480
LEVERAGE_LOOK_AWAY_DURATION = 180
LEVERAGE_DISTRACTION_DURATION = 90
LEVERAGE_ACCESS_DURATION = 240
LEVERAGE_CAMERA_DURATION = 180
LEVERAGE_RECORD_DURATION = 360

LEVERAGE_DEMANDS = (
    "credits",
    "trade_terms",
    "look_away",
    "distraction",
    "access_window",
    "credentials",
    "disable_camera",
    "hand_over_item",
    "falsify_record",
    "arrange_meeting",
)

_DEMAND_BURDEN = {
    "credits": 0.92,
    "trade_terms": 1.12,
    "look_away": 1.18,
    "distraction": 1.08,
    "access_window": 1.26,
    "credentials": 1.38,
    "disable_camera": 1.36,
    "hand_over_item": 1.14,
    "falsify_record": 1.5,
    "arrange_meeting": 1.08,
}

_NON_ITEM_DEMAND_IDS = {
    WIRE_DATA_ITEM_ID,
    "credstick_chip",
    "property_key",
    "access_badge",
    "manager_badge",
}


def _text(value):
    return str(value or "").strip()


def _key(value):
    return _text(value).lower()


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


def _stable_unit(*parts):
    digest = hashlib.sha256(":".join(str(part or "") for part in parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16) / float(0xFFFFFFFF)


def _root(sim, *, create=False):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        if not create:
            return None
        traits = {}
        sim.world_traits = traits
    root = traits.get("person_leverage")
    if not isinstance(root, dict):
        if not create:
            return None
        root = {"schema_version": LEVERAGE_SCHEMA_VERSION, "actors": {}}
        traits["person_leverage"] = root
    if not isinstance(root.get("actors"), dict):
        root["actors"] = {}
    return root


def _actor_state(sim, actor_eid, *, create=False):
    root = _root(sim, create=create)
    if root is None:
        return None
    actors = root["actors"]
    actor_key = str(_int(actor_eid, 0))
    state = actors.get(actor_key)
    if not isinstance(state, dict):
        if not create:
            return None
        state = {"records": {}}
        actors[actor_key] = state
    if not isinstance(state.get("records"), dict):
        state["records"] = {}
    return state


def _record_for_packet(sim, actor_eid, subject_eid, packet, *, create=False):
    packet_id = _text((packet or {}).get("instance_id"))
    if not packet_id:
        return None
    state = _actor_state(sim, actor_eid, create=create)
    if state is None:
        return None
    record = state["records"].get(packet_id)
    if not isinstance(record, dict):
        if not create:
            return None
        metadata = dict((packet or {}).get("metadata") or {})
        record = {
            "packet_instance_id": packet_id,
            "subject_eid": _int(subject_eid, 0),
            "subject_name": _text(metadata.get("subject_name")),
            "source_property_id": _text(metadata.get("source_property_id")),
            "pressure_fact_key": _key(metadata.get("pressure_fact_key")),
            "pressure_fact_summary": _text(metadata.get("pressure_fact_summary")),
            "pressure_audience": _text(metadata.get("pressure_audience")),
            "outcomes": {},
            "active_effects": {},
            "fear": 0.0,
            "resentment": 0.0,
            "retaliation_pressure": 0.0,
        }
        state["records"][packet_id] = record
    if not isinstance(record.get("outcomes"), dict):
        record["outcomes"] = {}
    if not isinstance(record.get("active_effects"), dict):
        record["active_effects"] = {}
    return record


def blackmail_entries_for_subject(sim, actor_eid, subject_eid):
    from game.wire_kit import wire_state_for_actor

    state = wire_state_for_actor(sim, actor_eid, create=False)
    if state is None:
        return ()
    rows = []
    for entry in tuple(getattr(state, "kit_entries", ()) or ()):
        if not isinstance(entry, Mapping) or _key(entry.get("item_id")) != WIRE_DATA_ITEM_ID:
            continue
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), Mapping) else {}
        if _key(metadata.get("data_family")) != "blackmail" or _key(metadata.get("subject_kind")) != "person":
            continue
        if _int(metadata.get("subject_eid"), -1) != _int(subject_eid, -2):
            continue
        rows.append(dict(entry))
    rows.sort(
        key=lambda row: (
            -_int((row.get("metadata") or {}).get("pressure_strength"), 0),
            -_int((row.get("metadata") or {}).get("freshness"), 0),
            _text(row.get("instance_id")),
        )
    )
    return tuple(rows)


def _property_candidates(sim, packet, *, current_prop=None, workplace_prop=None, owned_prop=None):
    candidates = []
    seen = set()
    source_id = _text((packet.get("metadata") or {}).get("source_property_id")) if isinstance(packet, Mapping) else ""
    source_prop = sim.properties.get(source_id) if source_id else None
    for prop in (current_prop, workplace_prop, owned_prop, source_prop):
        if not isinstance(prop, Mapping):
            continue
        property_id = _text(prop.get("id"))
        if not property_id or property_id in seen:
            continue
        seen.add(property_id)
        candidates.append(prop)
    return tuple(candidates)


def _subject_authority(packet, prop, *, current_prop=None, workplace_prop=None, owned_prop=None):
    if not isinstance(prop, Mapping):
        return False
    metadata = dict((packet or {}).get("metadata") or {})
    relation = _key(metadata.get("subject_relation"))
    source_id = _text(metadata.get("source_property_id"))
    prop_id = _text(prop.get("id"))
    if relation in {"owner", "manager", "guard", "employee", "organization_member"} and prop_id == source_id:
        return True
    if isinstance(workplace_prop, Mapping) and _text(workplace_prop.get("id")) == prop_id:
        return True
    if isinstance(owned_prop, Mapping) and _text(owned_prop.get("id")) == prop_id:
        return True
    return False


def _demand_property(
    sim,
    packet,
    demand,
    *,
    current_prop=None,
    workplace_prop=None,
    owned_prop=None,
    trade_available=False,
):
    for prop in _property_candidates(
        sim,
        packet,
        current_prop=current_prop,
        workplace_prop=workplace_prop,
        owned_prop=owned_prop,
    ):
        if not _subject_authority(
            packet,
            prop,
            current_prop=current_prop,
            workplace_prop=workplace_prop,
            owned_prop=owned_prop,
        ):
            continue
        if demand == "trade_terms" and not property_is_storefront(prop):
            continue
        if demand == "trade_terms" and not (
            bool(trade_available)
            or (isinstance(current_prop, Mapping) and _text(current_prop.get("id")) == _text(prop.get("id")))
        ):
            continue
        return prop
    return None


def _property_name(prop):
    return _text((prop or {}).get("name")) or _text((prop or {}).get("id")) or "the property"


def _subject_property_role(packet, prop, subject_eid, controller=None):
    controller = controller if isinstance(controller, Mapping) else {}
    holder = controller_holder_for_actor(controller, subject_eid)
    if isinstance(holder, Mapping):
        return _key(holder.get("role")) or "staff", dict(holder)
    metadata = dict((packet or {}).get("metadata") or {})
    if _text(metadata.get("source_property_id")) == _text((prop or {}).get("id")):
        relation = _key(metadata.get("subject_relation"))
        if relation in {"owner", "manager", "guard", "employee", "organization_member"}:
            return relation, None
    return "", None


def _property_capability_candidates(
    sim,
    packet,
    subject_eid,
    *,
    current_prop=None,
    workplace_prop=None,
    owned_prop=None,
):
    rows = []
    for prop in _property_candidates(
        sim,
        packet,
        current_prop=current_prop,
        workplace_prop=workplace_prop,
        owned_prop=owned_prop,
    ):
        if not _subject_authority(
            packet,
            prop,
            current_prop=current_prop,
            workplace_prop=workplace_prop,
            owned_prop=owned_prop,
        ):
            continue
        controller = property_access_controller(sim, prop)
        role, holder = _subject_property_role(packet, prop, subject_eid, controller=controller)
        if not role:
            continue
        rows.append({
            "prop": prop,
            "controller": controller,
            "role": role,
            "holder": holder,
        })
    return tuple(rows)


def _access_window_capability(property_rows):
    for row in property_rows:
        prop = row["prop"]
        controller = row["controller"]
        if row.get("holder") is None and row.get("role") not in {"owner", "manager", "guard"}:
            continue
        apertures = tuple(property_apertures(prop))
        lock_state = property_lock_state(prop)
        if not (
            apertures
            or bool(lock_state.get("locked"))
            or bool(controller.get("managed_lock"))
            or bool(controller.get("electronic"))
        ):
            continue
        return {
            "property_id": _text(prop.get("id")),
            "property_name": _property_name(prop),
            "controller_kind": _key(controller.get("kind")),
            "credential_mode": _key(controller.get("credential_mode")),
            "fixture_label": _text(controller.get("fixture_label")) or "access controller",
        }
    return None


def _credential_capability(sim, actor_eid, subject_eid, property_rows):
    subject_inventory = sim.ecs.get(Inventory).get(subject_eid)
    actor_inventory = sim.ecs.get(Inventory).get(actor_eid)
    if subject_inventory is None or actor_inventory is None:
        return None
    for row in property_rows:
        prop = row["prop"]
        holder = row.get("holder")
        if not isinstance(holder, Mapping):
            continue
        credential_kind = _key(holder.get("credential_kind"))
        if not credential_kind or credential_kind == "biometric_authorization":
            continue
        lock_state = property_lock_state(prop)
        entry = inventory_matching_property_credential(
            subject_inventory,
            property_id=prop.get("id"),
            key_id=lock_state.get("key_id"),
            allowed_kinds=(credential_kind,),
            minimum_tier=holder.get("credential_tier"),
        )
        if not entry:
            continue
        if inventory_matching_property_credential(
            actor_inventory,
            property_id=prop.get("id"),
            key_id=lock_state.get("key_id"),
            allowed_kinds=(credential_kind,),
            minimum_tier=holder.get("credential_tier"),
        ):
            continue
        if int(actor_inventory.slot_count()) + int(item_inventory_slot_cost(entry)) > int(actor_inventory.capacity):
            continue
        return {
            "property_id": _text(prop.get("id")),
            "property_name": _property_name(prop),
            "instance_id": _text(entry.get("instance_id")),
            "item_id": _key(entry.get("item_id")),
            "item_name": item_display_name(entry.get("item_id"), item_catalog=ITEM_CATALOG),
            "credential_kind": credential_kind,
            "credential_tier": _int(holder.get("credential_tier"), 1),
        }
    return None


def _fixture_matches_property(sim, fixture, prop):
    if not isinstance(fixture, Mapping) or not isinstance(prop, Mapping):
        return False
    property_id = _text(prop.get("id"))
    if not property_id:
        return False
    if _text(fixture.get("id")) == property_id:
        return True
    if _text(property_linked_property_id(fixture)) == property_id:
        return True
    building_id = _text(building_id_from_property(prop))
    if building_id and _text(property_linked_building_id(fixture)) == building_id:
        return True
    try:
        fx = int(fixture.get("x", 0))
        fy = int(fixture.get("y", 0))
        fz = int(fixture.get("z", 0))
    except (TypeError, ValueError):
        return False
    covering = property_covering(sim, fx, fy, fz)
    if isinstance(covering, Mapping) and _text(covering.get("id")) == property_id:
        return True
    cover_index = getattr(sim, "property_cover_index", {})
    return isinstance(cover_index, Mapping) and property_id in {
        _text(value) for value in tuple(cover_index.get((fx, fy, fz), ()) or ())
    }


def _camera_capability(sim, property_rows):
    cameras = tuple(
        prop
        for prop in getattr(sim, "properties", {}).values()
        if _key(property_infrastructure_role(prop)) == "camera_target"
    )
    now = _int(getattr(sim, "tick", 0), 0)
    disabled = getattr(sim, "camera_disabled", {})
    for row in property_rows:
        if row.get("role") not in {"owner", "manager", "guard"}:
            continue
        prop = row["prop"]
        for camera in cameras:
            camera_id = _text(camera.get("id"))
            if not camera_id or not _fixture_matches_property(sim, camera, prop):
                continue
            if isinstance(disabled, Mapping) and _int(disabled.get(camera_id), 0) > now:
                continue
            return {
                "property_id": _text(prop.get("id")),
                "property_name": _property_name(prop),
                "camera_id": camera_id,
                "camera_name": _property_name(camera),
            }
    return None


def _record_capability(property_rows):
    for row in property_rows:
        if row.get("role") not in {"owner", "manager"}:
            continue
        prop = row["prop"]
        controller = row["controller"]
        return {
            "property_id": _text(prop.get("id")),
            "property_name": _property_name(prop),
            "fixture_label": _text(controller.get("fixture_label")) or "access records",
        }
    return None


def _item_value(entry):
    item = ITEM_CATALOG.get(_key((entry or {}).get("item_id")), {})
    for key in ("value", "base_value", "price"):
        if item.get(key) is not None:
            return max(0, _int(item.get(key), 0))
    return 0


def _item_capability(sim, actor_eid, subject_eid):
    subject_inventory = sim.ecs.get(Inventory).get(subject_eid)
    actor_inventory = sim.ecs.get(Inventory).get(actor_eid)
    if subject_inventory is None or actor_inventory is None:
        return None
    candidates = []
    for entry in tuple(getattr(subject_inventory, "items", ()) or ()):
        item_id = _key(entry.get("item_id"))
        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), Mapping) else {}
        item = ITEM_CATALOG.get(item_id, {})
        tags = {_key(tag) for tag in tuple(item.get("tags", ()) or ()) if _key(tag)}
        if not item_id or item_id in _NON_ITEM_DEMAND_IDS or is_credstick_item(item_id):
            continue
        if "container" in tags or isinstance(item.get("container_profile"), Mapping):
            continue
        if _text(metadata.get("stowed_in_container")):
            continue
        if int(actor_inventory.slot_count()) + int(item_inventory_slot_cost(entry)) > int(actor_inventory.capacity):
            continue
        candidates.append(entry)
    if not candidates:
        return None
    candidates.sort(key=lambda entry: (-_item_value(entry), item_display_name(entry.get("item_id"), item_catalog=ITEM_CATALOG).lower(), _text(entry.get("instance_id"))))
    entry = candidates[0]
    return {
        "instance_id": _text(entry.get("instance_id")),
        "item_id": _key(entry.get("item_id")),
        "item_name": item_display_name(entry.get("item_id"), item_catalog=ITEM_CATALOG),
        "quantity": 1,
    }


def _meeting_capability(sim, actor_eid, subject_eid, social_leads):
    if sim.ecs.get(ContactLedger).get(actor_eid) is None:
        return None
    rows = []
    for lead in tuple(social_leads or ()):
        if not isinstance(lead, Mapping) or lead.get("eid") in {None, actor_eid, subject_eid}:
            continue
        name = _text(lead.get("name"))
        if not name:
            continue
        existing = sim.ecs.get(ContactLedger).get(actor_eid).person_entry(lead.get("eid"))
        if isinstance(existing, Mapping) and bool(existing.get("introduced", False)):
            continue
        rows.append(dict(lead))
    if not rows:
        return None
    rows.sort(key=lambda lead: (-_float(lead.get("score"), 0.0), _text(lead.get("name")).lower(), _int(lead.get("eid"), 0)))
    lead = rows[0]
    return {
        "lead_eid": lead.get("eid"),
        "lead_name": _text(lead.get("name")),
        "relation_kind": _key(lead.get("relation_kind")) or "contact",
        "relation_text": _text(lead.get("relation_text")) or "contact",
        "property_id": _text(lead.get("property_id")),
        "place_name": _text(lead.get("place_name")),
    }


def _transfer_inventory_entry(sim, actor_eid, subject_eid, capability, *, transfer_kind):
    source = sim.ecs.get(Inventory).get(subject_eid)
    destination = sim.ecs.get(Inventory).get(actor_eid)
    instance_id = _text((capability or {}).get("instance_id"))
    if source is None or destination is None or not instance_id:
        return None
    removed = source.remove_item(instance_id=instance_id, quantity=max(1, _int((capability or {}).get("quantity"), 1)))
    if not removed:
        return None
    item_id = _key(removed.get("item_id"))
    item = ITEM_CATALOG.get(item_id, {})
    metadata = dict(removed.get("metadata") or {})
    metadata.update({
        "last_transfer_tick": _int(getattr(sim, "tick", 0), 0),
        "last_transfer_kind": _key(transfer_kind),
        "last_holder_eid": actor_eid,
        "coerced_from_eid": subject_eid,
    })
    destination_instance_id = None if source.find(instance_id=instance_id) else removed.get("instance_id")
    added, added_instance_id = destination.add_item(
        item_id=item_id,
        quantity=max(1, _int(removed.get("quantity"), 1)),
        stack_max=max(1, _int(item.get("stack_max"), 1)),
        instance_id=destination_instance_id,
        instance_factory=sim.new_item_instance_id,
        owner_eid=actor_eid,
        owner_tag="player",
        metadata=metadata,
    )
    if not added:
        source.add_item(
            item_id=item_id,
            quantity=max(1, _int(removed.get("quantity"), 1)),
            stack_max=max(1, _int(item.get("stack_max"), 1)),
            instance_id=removed.get("instance_id"),
            instance_factory=sim.new_item_instance_id,
            owner_eid=removed.get("owner_eid"),
            owner_tag=removed.get("owner_tag"),
            metadata=removed.get("metadata"),
        )
        return None
    _unlink_removed_item_from_gear(sim, subject_eid, removed, item_catalog=ITEM_CATALOG)
    return {
        "item_id": item_id,
        "item_name": item_display_name(item_id, item_catalog=ITEM_CATALOG),
        "instance_id": _text(added_instance_id),
        "quantity": max(1, _int(removed.get("quantity"), 1)),
    }


def _npc_funds(sim, subject_eid):
    inventory = sim.ecs.get(Inventory).get(subject_eid)
    carried = inventory_liquid_credits(inventory)
    finance = sim.ecs.get(FinancialProfile).get(subject_eid)
    banked = max(0, _int(getattr(finance, "bank_balance", 0), 0)) if finance is not None else 0
    return inventory, finance, int(carried), int(banked)


def _credits_demand_amount(sim, subject_eid, metadata):
    _inventory, _finance, carried, banked = _npc_funds(sim, subject_eid)
    available = carried + banked
    if available <= 0:
        return 0
    strength = max(1, min(5, _int(metadata.get("pressure_strength"), metadata.get("sensitivity", 1))))
    desired = 14 + (strength * 10) + (_int(metadata.get("subject_value"), 1) * 4)
    return int(max(1, min(available, desired, 96)))


def _dialogue_base(sim, actor_eid, subject_eid):
    entries = blackmail_entries_for_subject(sim, actor_eid, subject_eid)
    if not entries:
        return {"leverage_available": False}
    packet = entries[0]
    metadata = dict(packet.get("metadata") or {})
    record = _record_for_packet(sim, actor_eid, subject_eid, packet, create=False) or {}
    outcomes = record.get("outcomes") if isinstance(record.get("outcomes"), dict) else {}
    return {
        "leverage_available": True,
        "leverage_packet": packet,
        "leverage_packet_instance_id": _text(packet.get("instance_id")),
        "leverage_subject_name": _text(metadata.get("subject_name")),
        "leverage_fact": _text(metadata.get("pressure_fact_summary"),) or _text(metadata.get("record_summary")),
        "leverage_audience": _text(metadata.get("pressure_audience")) or "the people who matter to you",
        "leverage_strength": max(1, min(5, _int(metadata.get("pressure_strength"), metadata.get("sensitivity", 1)))),
        "leverage_outcomes": dict(outcomes),
    }


def person_leverage_dialogue_context(
    sim,
    actor_eid,
    subject_eid,
    *,
    current_prop=None,
    workplace_prop=None,
    owned_prop=None,
    trade_available=False,
    social_leads=(),
):
    context = _dialogue_base(sim, actor_eid, subject_eid)
    if not context.get("leverage_available"):
        return context
    packet = context["leverage_packet"]
    metadata = dict(packet.get("metadata") or {})
    outcomes = context.get("leverage_outcomes", {})
    credits = _credits_demand_amount(sim, subject_eid, metadata)
    terms_prop = _demand_property(
        sim,
        packet,
        "trade_terms",
        current_prop=current_prop,
        workplace_prop=workplace_prop,
        owned_prop=owned_prop,
        trade_available=trade_available,
    )
    grace_prop = _demand_property(
        sim,
        packet,
        "look_away",
        current_prop=current_prop,
        workplace_prop=workplace_prop,
        owned_prop=owned_prop,
        trade_available=trade_available,
    )
    contractors = getattr(sim, "contractors", {})
    active_job = contractors.get(subject_eid) if isinstance(contractors, dict) else None
    can_act = sim.ecs.get(AI).get(subject_eid) is not None and sim.ecs.get(Position).get(subject_eid) is not None
    property_rows = _property_capability_candidates(
        sim,
        packet,
        subject_eid,
        current_prop=current_prop,
        workplace_prop=workplace_prop,
        owned_prop=owned_prop,
    )
    access_capability = _access_window_capability(property_rows)
    credential_capability = _credential_capability(sim, actor_eid, subject_eid, property_rows)
    camera_capability = _camera_capability(sim, property_rows)
    item_capability = _item_capability(sim, actor_eid, subject_eid)
    record_capability = _record_capability(property_rows)
    meeting_capability = _meeting_capability(sim, actor_eid, subject_eid, social_leads)
    context.update({
        "leverage_credits_available": bool(credits > 0 and "credits" not in outcomes),
        "leverage_credits_amount": int(credits),
        "leverage_trade_terms_available": bool(terms_prop is not None and "trade_terms" not in outcomes),
        "leverage_trade_property_id": _text((terms_prop or {}).get("id")),
        "leverage_trade_property_name": _text((terms_prop or {}).get("name")) or "this counter",
        "leverage_look_away_available": bool(grace_prop is not None and "look_away" not in outcomes),
        "leverage_look_away_property_id": _text((grace_prop or {}).get("id")),
        "leverage_look_away_property_name": _text((grace_prop or {}).get("name")) or "this place",
        "leverage_distraction_available": bool(can_act and not isinstance(active_job, Mapping) and "distraction" not in outcomes),
        "leverage_distraction_duration": LEVERAGE_DISTRACTION_DURATION,
        "leverage_access_window_available": bool(access_capability and "access_window" not in outcomes),
        "leverage_access_property_id": _text((access_capability or {}).get("property_id")),
        "leverage_access_property_name": _text((access_capability or {}).get("property_name")) or "this place",
        "leverage_access_fixture_label": _text((access_capability or {}).get("fixture_label")) or "access controller",
        "leverage_credentials_available": bool(credential_capability and "credentials" not in outcomes),
        "leverage_credential_property_id": _text((credential_capability or {}).get("property_id")),
        "leverage_credential_property_name": _text((credential_capability or {}).get("property_name")) or "this place",
        "leverage_credential_item_name": _text((credential_capability or {}).get("item_name")) or "credential",
        "leverage_disable_camera_available": bool(camera_capability and "disable_camera" not in outcomes),
        "leverage_camera_property_id": _text((camera_capability or {}).get("property_id")),
        "leverage_camera_property_name": _text((camera_capability or {}).get("property_name")) or "this place",
        "leverage_camera_id": _text((camera_capability or {}).get("camera_id")),
        "leverage_camera_name": _text((camera_capability or {}).get("camera_name")) or "camera",
        "leverage_hand_over_item_available": bool(item_capability and "hand_over_item" not in outcomes),
        "leverage_item_name": _text((item_capability or {}).get("item_name")) or "item",
        "leverage_falsify_record_available": bool(record_capability and "falsify_record" not in outcomes),
        "leverage_record_property_id": _text((record_capability or {}).get("property_id")),
        "leverage_record_property_name": _text((record_capability or {}).get("property_name")) or "this place",
        "leverage_record_fixture_label": _text((record_capability or {}).get("fixture_label")) or "access records",
        "leverage_arrange_meeting_available": bool(meeting_capability and "arrange_meeting" not in outcomes),
        "leverage_meeting_lead_eid": (meeting_capability or {}).get("lead_eid"),
        "leverage_meeting_lead_name": _text((meeting_capability or {}).get("lead_name")) or "your contact",
        "leverage_meeting_relation": _text((meeting_capability or {}).get("relation_text")) or "contact",
        "leverage_capabilities": {
            "access_window": dict(access_capability or {}),
            "credentials": dict(credential_capability or {}),
            "disable_camera": dict(camera_capability or {}),
            "hand_over_item": dict(item_capability or {}),
            "falsify_record": dict(record_capability or {}),
            "arrange_meeting": dict(meeting_capability or {}),
        },
    })
    return context


def _compliance_score(sim, subject_eid, packet, demand, record):
    metadata = dict((packet or {}).get("metadata") or {})
    strength = max(1, min(5, _int(metadata.get("pressure_strength"), metadata.get("sensitivity", 1))))
    subject_value = max(1, min(5, _int(metadata.get("subject_value"), 1)))
    freshness = max(0, min(5, _int(metadata.get("freshness"), 1)))
    leverage = (strength * 0.34) + (subject_value * 0.11) + (freshness * 0.07)

    traits = sim.ecs.get(NPCTraits).get(subject_eid)
    bravery = max(0.0, min(1.0, _float(getattr(traits, "bravery", 0.5), 0.5)))
    discipline = max(0.0, min(1.0, _float(getattr(traits, "discipline", 0.5), 0.5)))
    loyalty = max(0.0, min(1.0, _float(getattr(traits, "loyalty", 0.5), 0.5)))
    institutional_cost = 1.0 if demand in {
        "trade_terms",
        "look_away",
        "access_window",
        "credentials",
        "disable_camera",
        "falsify_record",
    } else 0.35
    prior_outcomes = len(record.get("outcomes", {}) or {}) if isinstance(record, Mapping) else 0
    resistance = (
        _DEMAND_BURDEN.get(demand, 1.2)
        + (bravery * 0.46)
        + (discipline * 0.38)
        + (loyalty * 0.32 * institutional_cost)
        + (prior_outcomes * 0.28)
    )
    jitter = (_stable_unit(getattr(sim, "seed", 0), subject_eid, packet.get("instance_id"), demand) - 0.5) * 0.28
    return float(leverage + jitter), float(resistance)


def _remember_subject_pressure(sim, actor_eid, subject_eid, *, demand, complied, packet, record, property_id=""):
    memory = sim.ecs.get(NPCMemory).get(subject_eid)
    if memory is None:
        memory = NPCMemory()
        sim.ecs.add(subject_eid, memory)
    strength = max(0.25, min(1.0, 0.42 + (_float(record.get("fear"), 0.0) * 0.32)))
    memory.remember(
        getattr(sim, "tick", 0),
        "blackmailed",
        strength=strength,
        offender_eid=actor_eid,
        demand=demand,
        complied=bool(complied),
        packet_instance_id=_text(packet.get("instance_id")),
        property_id=_text(property_id),
        pressure_fact_key=_key(record.get("pressure_fact_key")),
    )


def resolve_person_leverage_demand(
    sim,
    actor_eid,
    subject_eid,
    demand,
    *,
    current_prop=None,
    workplace_prop=None,
    owned_prop=None,
    trade_available=False,
    social_leads=(),
):
    demand = _key(demand)
    if demand not in LEVERAGE_DEMANDS:
        return {"ok": False, "reason": "unknown_leverage_demand"}
    context = person_leverage_dialogue_context(
        sim,
        actor_eid,
        subject_eid,
        current_prop=current_prop,
        workplace_prop=workplace_prop,
        owned_prop=owned_prop,
        trade_available=trade_available,
        social_leads=social_leads,
    )
    if not context.get("leverage_available"):
        return {"ok": False, "reason": "matching_blackmail_unavailable"}
    availability_key = {
        "credits": "leverage_credits_available",
        "trade_terms": "leverage_trade_terms_available",
        "look_away": "leverage_look_away_available",
        "distraction": "leverage_distraction_available",
        "access_window": "leverage_access_window_available",
        "credentials": "leverage_credentials_available",
        "disable_camera": "leverage_disable_camera_available",
        "hand_over_item": "leverage_hand_over_item_available",
        "falsify_record": "leverage_falsify_record_available",
        "arrange_meeting": "leverage_arrange_meeting_available",
    }[demand]
    if not context.get(availability_key):
        return {"ok": False, "reason": "leverage_demand_unavailable", "demand": demand}

    packet = context["leverage_packet"]
    record = _record_for_packet(sim, actor_eid, subject_eid, packet, create=True)
    if demand in record["outcomes"]:
        return {"ok": False, "reason": "leverage_demand_already_resolved", "demand": demand}
    leverage_score, resistance_score = _compliance_score(sim, subject_eid, packet, demand, record)
    complied = bool(leverage_score >= resistance_score)
    now = _int(getattr(sim, "tick", 0), 0)
    property_id = ""
    property_name = ""
    effect = {}
    payout = 0

    if complied and demand == "credits":
        requested = max(1, _int(context.get("leverage_credits_amount"), 1))
        assets = sim.ecs.get(PlayerAssets).get(actor_eid)
        if assets is None:
            complied = False
        else:
            inventory, finance, _carried, _banked = _npc_funds(sim, subject_eid)
            wallet_paid = spend_npc_wallet_credits(inventory, requested)
            remaining = max(0, requested - wallet_paid)
            bank_paid = 0
            if finance is not None and remaining > 0:
                bank_paid = min(remaining, max(0, _int(getattr(finance, "bank_balance", 0), 0)))
                finance.bank_balance = max(0, _int(getattr(finance, "bank_balance", 0), 0) - bank_paid)
            payout = int(wallet_paid + bank_paid)
            if payout <= 0:
                complied = False
            else:
                assets.credits = _int(getattr(assets, "credits", 0), 0) + payout
                effect = {"kind": "credits", "amount": payout, "wallet_paid": wallet_paid, "bank_paid": bank_paid}
    elif complied and demand == "trade_terms":
        property_id = _text(context.get("leverage_trade_property_id"))
        property_name = _text(context.get("leverage_trade_property_name"))
        effect = {
            "kind": "trade_terms",
            "property_id": property_id,
            "property_name": property_name,
            "buy_mult": 0.84,
            "sell_mult": 1.12,
            "expires_tick": now + LEVERAGE_TRADE_DURATION,
        }
        record["active_effects"]["trade_terms"] = dict(effect)
    elif complied and demand == "look_away":
        property_id = _text(context.get("leverage_look_away_property_id"))
        property_name = _text(context.get("leverage_look_away_property_name"))
        from game.dialogue_runtime import grant_dialogue_guard_grace

        prop = sim.properties.get(property_id)
        complied = bool(
            prop
            and grant_dialogue_guard_grace(
                sim,
                subject_eid,
                prop,
                duration=LEVERAGE_LOOK_AWAY_DURATION,
                tactic="blackmail",
            )
        )
        if complied:
            effect = {
                "kind": "look_away",
                "property_id": property_id,
                "property_name": property_name,
                "expires_tick": now + LEVERAGE_LOOK_AWAY_DURATION,
            }
            record["active_effects"]["look_away"] = dict(effect)
    elif complied and demand == "distraction":
        effect = {
            "kind": "distraction",
            "duration": LEVERAGE_DISTRACTION_DURATION,
            "expires_tick": now + LEVERAGE_DISTRACTION_DURATION,
        }
        record["active_effects"]["distraction"] = dict(effect)
    elif complied and demand == "access_window":
        capability = dict((context.get("leverage_capabilities") or {}).get("access_window") or {})
        property_id = _text(capability.get("property_id"))
        property_name = _text(capability.get("property_name"))
        prop = sim.properties.get(property_id)
        controller = property_access_controller(sim, prop) if isinstance(prop, Mapping) else {}
        credential_mode = _key(controller.get("credential_mode"))
        if credential_mode == "biometric":
            mode = "biometric_jam"
        elif _key(controller.get("kind")) in {"owner_schedule", "auto_timer"}:
            mode = "schedule_latch"
        else:
            mode = "relay_latch"
        complied = bool(
            prop
            and apply_controller_intrusion(
                prop,
                mode=mode,
                tick=now,
                duration=LEVERAGE_ACCESS_DURATION,
                actor_eid=actor_eid,
                method="coerced_access_window",
            )
        )
        if complied:
            refreshed_controller = sync_property_access_controller(sim, prop)
            _set_property_apertures_locked(
                sim,
                prop,
                locked=refreshed_controller.get("open_now") is not True,
                auto_managed=refreshed_controller.get("managed_lock"),
            )
            effect = {
                "kind": "access_window",
                "property_id": property_id,
                "property_name": property_name,
                "controller_mode": mode,
                "expires_tick": now + LEVERAGE_ACCESS_DURATION,
            }
            record["active_effects"]["access_window"] = dict(effect)
    elif complied and demand == "credentials":
        capability = dict((context.get("leverage_capabilities") or {}).get("credentials") or {})
        transfer = _transfer_inventory_entry(
            sim,
            actor_eid,
            subject_eid,
            capability,
            transfer_kind="coerced_credential_handover",
        )
        complied = bool(transfer)
        property_id = _text(capability.get("property_id"))
        property_name = _text(capability.get("property_name"))
        if complied:
            effect = {
                "kind": "credentials",
                "property_id": property_id,
                "property_name": property_name,
                "credential_kind": _key(capability.get("credential_kind")),
                "credential_tier": _int(capability.get("credential_tier"), 1),
                **dict(transfer),
            }
    elif complied and demand == "disable_camera":
        capability = dict((context.get("leverage_capabilities") or {}).get("disable_camera") or {})
        camera_id = _text(capability.get("camera_id"))
        property_id = _text(capability.get("property_id"))
        property_name = _text(capability.get("property_name"))
        camera = sim.properties.get(camera_id)
        if not isinstance(getattr(sim, "camera_disabled", None), dict):
            sim.camera_disabled = {}
        complied = bool(camera and camera_id)
        if complied:
            disabled_until = now + LEVERAGE_CAMERA_DURATION
            sim.camera_disabled[camera_id] = disabled_until
            effect = {
                "kind": "disable_camera",
                "property_id": property_id,
                "property_name": property_name,
                "camera_id": camera_id,
                "camera_name": _text(capability.get("camera_name")) or _property_name(camera),
                "expires_tick": disabled_until,
            }
            record["active_effects"]["disable_camera"] = dict(effect)
            sim.emit(Event(
                "camera_disabled",
                eid=subject_eid,
                coercer_eid=actor_eid,
                property_id=camera_id,
                linked_property_id=property_id,
                disabled_until=disabled_until,
                source="person_leverage",
            ))
    elif complied and demand == "hand_over_item":
        capability = dict((context.get("leverage_capabilities") or {}).get("hand_over_item") or {})
        transfer = _transfer_inventory_entry(
            sim,
            actor_eid,
            subject_eid,
            capability,
            transfer_kind="coerced_item_handover",
        )
        complied = bool(transfer)
        if complied:
            effect = {"kind": "hand_over_item", **dict(transfer)}
    elif complied and demand == "falsify_record":
        capability = dict((context.get("leverage_capabilities") or {}).get("falsify_record") or {})
        property_id = _text(capability.get("property_id"))
        property_name = _text(capability.get("property_name"))
        prop = sim.properties.get(property_id)
        complied = bool(prop and grant_controller_access_record(
            prop,
            actor_eid,
            tick=now,
            duration=LEVERAGE_RECORD_DURATION,
            source="coerced_record_falsification",
            issued_by_eid=subject_eid,
        ))
        if complied:
            effect = {
                "kind": "falsify_record",
                "property_id": property_id,
                "property_name": property_name,
                "actor_eid": actor_eid,
                "expires_tick": now + LEVERAGE_RECORD_DURATION,
            }
            record["active_effects"]["falsify_record"] = dict(effect)
    elif complied and demand == "arrange_meeting":
        capability = dict((context.get("leverage_capabilities") or {}).get("arrange_meeting") or {})
        complied = bool(capability.get("lead_eid") is not None and _text(capability.get("lead_name")))
        property_id = _text(capability.get("property_id"))
        if complied:
            effect = {
                "kind": "arrange_meeting",
                "lead_eid": capability.get("lead_eid"),
                "lead_name": _text(capability.get("lead_name")),
                "relation_kind": _key(capability.get("relation_kind")) or "contact",
                "relation_text": _text(capability.get("relation_text")) or "contact",
                "property_id": property_id,
                "place_name": _text(capability.get("place_name")),
            }

    record["fear"] = min(1.0, _float(record.get("fear"), 0.0) + (0.18 if complied else 0.06))
    record["resentment"] = min(1.0, _float(record.get("resentment"), 0.0) + (0.13 if complied else 0.19))
    record["retaliation_pressure"] = min(
        1.0,
        _float(record.get("retaliation_pressure"), 0.0) + (0.12 if complied else 0.2),
    )
    record["last_demand_tick"] = now
    record["outcomes"][demand] = {
        "demand": demand,
        "complied": bool(complied),
        "tick": now,
        "leverage_score": round(leverage_score, 4),
        "resistance_score": round(resistance_score, 4),
        "property_id": property_id,
        "effect": dict(effect),
    }
    _remember_subject_pressure(
        sim,
        actor_eid,
        subject_eid,
        demand=demand,
        complied=complied,
        packet=packet,
        record=record,
        property_id=property_id,
    )
    sim.emit(Event(
        "person_leverage_resolved",
        eid=actor_eid,
        subject_eid=subject_eid,
        packet_instance_id=packet.get("instance_id"),
        demand=demand,
        complied=bool(complied),
        payout=int(payout),
        property_id=property_id,
        property_name=property_name,
        effect=dict(effect),
        fear=record.get("fear", 0.0),
        resentment=record.get("resentment", 0.0),
        retaliation_pressure=record.get("retaliation_pressure", 0.0),
    ))
    return {
        "ok": True,
        "reason": None,
        "complied": bool(complied),
        "demand": demand,
        "payout": int(payout),
        "property_id": property_id,
        "property_name": property_name,
        "effect": dict(effect),
        "record": dict(record),
        "packet": dict(packet),
    }


def coerced_trade_terms(sim, actor_eid, prop):
    property_id = _text((prop or {}).get("id")) if isinstance(prop, Mapping) else ""
    if not property_id:
        return {"active": False, "buy_mult": 1.0, "sell_mult": 1.0, "note": "", "source_eid": None}
    state = _actor_state(sim, actor_eid, create=False)
    if state is None:
        return {"active": False, "buy_mult": 1.0, "sell_mult": 1.0, "note": "", "source_eid": None}
    now = _int(getattr(sim, "tick", 0), 0)
    active = []
    for record in tuple(state.get("records", {}).values()):
        if not isinstance(record, Mapping):
            continue
        effect = (record.get("active_effects") or {}).get("trade_terms")
        if not isinstance(effect, Mapping) or _text(effect.get("property_id")) != property_id:
            continue
        if _int(effect.get("expires_tick"), -1) < now:
            continue
        active.append((record, effect))
    if not active:
        return {"active": False, "buy_mult": 1.0, "sell_mult": 1.0, "note": "", "source_eid": None}
    record, effect = sorted(active, key=lambda row: _int(row[1].get("expires_tick"), 0), reverse=True)[0]
    subject_name = _text(record.get("subject_name")) or "Pressured staff"
    return {
        "active": True,
        "buy_mult": max(0.75, min(1.0, _float(effect.get("buy_mult"), 1.0))),
        "sell_mult": max(1.0, min(1.2, _float(effect.get("sell_mult"), 1.0))),
        "note": f"{subject_name}: coerced counter terms",
        "source_eid": record.get("subject_eid"),
        "expires_tick": _int(effect.get("expires_tick"), now),
    }


def person_leverage_records(sim, actor_eid, *, subject_eid=None):
    state = _actor_state(sim, actor_eid, create=False)
    if state is None:
        return ()
    rows = []
    for record in tuple(state.get("records", {}).values()):
        if not isinstance(record, Mapping):
            continue
        if subject_eid is not None and _int(record.get("subject_eid"), -1) != _int(subject_eid, -2):
            continue
        rows.append(dict(record))
    rows.sort(key=lambda row: (_int(row.get("subject_eid"), 0), _text(row.get("packet_instance_id"))))
    return tuple(rows)
