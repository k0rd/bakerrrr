from __future__ import annotations

from game.components import Inventory
from game.items import ITEM_CATALOG


PROPERTY_KEY_ITEM_ID = "property_key"
PROPERTY_STAFF_BADGE_ITEM_ID = "access_badge"
PROPERTY_MANAGER_BADGE_ITEM_ID = "manager_badge"
PUBLIC_OWNER_TAGS = {"", "public", "city", "community", "neutral", "none", "unowned"}
PROPERTY_CREDENTIAL_ITEM_IDS = {
    "mechanical_key": PROPERTY_KEY_ITEM_ID,
    "staff_badge": PROPERTY_STAFF_BADGE_ITEM_ID,
    "manager_badge": PROPERTY_MANAGER_BADGE_ITEM_ID,
}
PROPERTY_CREDENTIAL_TIERS = {
    "mechanical_key": 1,
    "staff_badge": 2,
    "manager_badge": 3,
    "biometric_authorization": 4,
}
PROPERTY_CREDENTIAL_SUFFIXES = {
    "mechanical_key": "Key",
    "staff_badge": "Staff Badge",
    "manager_badge": "Manager Badge",
    "biometric_authorization": "Biometric Authorization",
}


def _int_or_default(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _text(value):
    return str(value or "").strip()


def _normalize_credential_kind(kind, default="mechanical_key"):
    text = _text(kind).lower()
    aliases = {
        "key": "mechanical_key",
        "property_key": "mechanical_key",
        "badge": "staff_badge",
        "access_badge": "staff_badge",
        "manager": "manager_badge",
        "manager_badge": "manager_badge",
        "staff": "staff_badge",
        "staff_badge": "staff_badge",
        "bio": "biometric_authorization",
        "biometric": "biometric_authorization",
        "biometric_authorization": "biometric_authorization",
    }
    if not text:
        return default
    return aliases.get(text, text)


def _normalized_allowed_kinds(allowed_kinds):
    if isinstance(allowed_kinds, str):
        raw = (allowed_kinds,)
    elif isinstance(allowed_kinds, (list, tuple, set)):
        raw = allowed_kinds
    else:
        raw = ()
    normalized = []
    for kind in raw:
        resolved = _normalize_credential_kind(kind, default="")
        if resolved:
            normalized.append(resolved)
    return tuple(sorted(set(normalized)))


def is_public_owner_tag(owner_tag):
    return _text(owner_tag).lower() in PUBLIC_OWNER_TAGS


def property_credential_item_id(credential_kind):
    return PROPERTY_CREDENTIAL_ITEM_IDS.get(_normalize_credential_kind(credential_kind, default=""), "")


def property_credential_uses_inventory(credential_kind):
    return bool(property_credential_item_id(credential_kind))


def property_credential_tier(credential_kind, default=None):
    resolved = _normalize_credential_kind(credential_kind, default="")
    fallback = PROPERTY_CREDENTIAL_TIERS.get("mechanical_key", 1) if default is None else default
    return max(1, min(5, _int_or_default(PROPERTY_CREDENTIAL_TIERS.get(resolved), fallback)))


def property_key_id_for(property_id=None, metadata=None, key_id=None):
    source = _text(key_id)
    data = metadata if isinstance(metadata, dict) else {}
    if not source:
        for field in ("property_key_id", "vehicle_id", "building_id"):
            source = _text(data.get(field))
            if source:
                break
    if not source:
        source = _text(property_id)
    if not source:
        return ""
    if source.startswith("key:"):
        return source
    return f"key:{source}"


def ensure_property_lock_metadata(
    metadata,
    *,
    property_id=None,
    property_name="",
    property_kind="property",
    locked=False,
    key_id=None,
    key_label=None,
    lock_tier=1,
):
    if not isinstance(metadata, dict):
        return {}

    resolved_key_id = property_key_id_for(property_id=property_id, metadata=metadata, key_id=key_id)
    if resolved_key_id:
        metadata["property_key_id"] = resolved_key_id

    label = _text(key_label) or _text(metadata.get("property_key_label")) or _text(property_name)
    if not label:
        label = _text(property_kind).replace("_", " ").title() or "Property"
    metadata["property_key_label"] = label
    metadata["property_locked"] = bool(locked)
    metadata["property_lock_tier"] = max(1, min(5, _int_or_default(lock_tier, metadata.get("property_lock_tier", 1))))
    return metadata


def ensure_property_lock(
    prop,
    *,
    locked=False,
    key_id=None,
    key_label=None,
    lock_tier=1,
):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        prop["metadata"] = metadata
    return ensure_property_lock_metadata(
        metadata,
        property_id=prop.get("id"),
        property_name=prop.get("name"),
        property_kind=prop.get("kind", "property"),
        locked=locked,
        key_id=key_id,
        key_label=key_label,
        lock_tier=lock_tier,
    )


def property_lock_state(prop):
    if not isinstance(prop, dict):
        return {
            "locked": False,
            "key_id": "",
            "key_label": "Property",
            "lock_tier": 1,
        }

    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    return {
        "locked": bool(metadata.get("property_locked", False)),
        "key_id": property_key_id_for(property_id=prop.get("id"), metadata=metadata, key_id=metadata.get("property_key_id")),
        "key_label": _text(metadata.get("property_key_label")) or _text(prop.get("name")) or "Property",
        "lock_tier": max(1, min(5, _int_or_default(metadata.get("property_lock_tier"), 1))),
    }


def property_key_item_metadata(prop):
    return property_credential_item_metadata(prop, credential_kind="mechanical_key")


def property_credential_item_metadata(
    prop,
    *,
    credential_kind="mechanical_key",
    holder_role="holder",
    credential_tier=None,
    display_name=None,
):
    if not isinstance(prop, dict):
        return {}
    state = property_lock_state(prop)
    label = _text(prop.get("name")) or state["key_label"] or "Property"
    resolved_kind = _normalize_credential_kind(credential_kind)
    resolved_tier = max(
        1,
        min(5, _int_or_default(credential_tier, property_credential_tier(resolved_kind))),
    )
    suffix = PROPERTY_CREDENTIAL_SUFFIXES.get(resolved_kind, "Credential")
    holder_role = _text(holder_role).lower() or "holder"
    custom_name = _text(display_name)
    if not custom_name:
        custom_name = f"{label} {suffix}"
    return {
        "property_id": prop.get("id"),
        "property_kind": _text(prop.get("kind")).lower() or "property",
        "property_name": label,
        "property_key_id": state["key_id"],
        "property_credential_kind": resolved_kind,
        "property_credential_tier": resolved_tier,
        "property_holder_role": holder_role,
        "display_name": custom_name,
    }


def entry_matches_property_key(entry, *, property_id=None, key_id=None):
    return entry_matches_property_credential(
        entry,
        property_id=property_id,
        key_id=key_id,
        allowed_kinds=("mechanical_key",),
    )


def entry_matches_property_credential(
    entry,
    *,
    property_id=None,
    key_id=None,
    allowed_kinds=None,
    minimum_tier=None,
):
    if not isinstance(entry, dict):
        return False
    metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
    entry_kind = _normalize_credential_kind(
        metadata.get("property_credential_kind") or _text(entry.get("item_id")).lower(),
        default="",
    )
    item_id = _text(entry.get("item_id")).lower()
    if item_id != property_credential_item_id(entry_kind):
        return False
    if _int_or_default(entry.get("quantity"), 0) <= 0:
        return False

    entry_key_id = property_key_id_for(property_id=metadata.get("property_id"), metadata=metadata, key_id=metadata.get("property_key_id"))
    target_key_id = property_key_id_for(property_id=property_id, key_id=key_id)
    if target_key_id:
        if entry_key_id != target_key_id:
            return False
    elif _text(property_id) and _text(metadata.get("property_id")) != _text(property_id):
        return False

    accepted = _normalized_allowed_kinds(allowed_kinds)
    if accepted and entry_kind not in accepted:
        return False

    entry_tier = max(1, min(5, _int_or_default(metadata.get("property_credential_tier"), property_credential_tier(entry_kind))))
    if minimum_tier is not None and entry_tier < max(1, _int_or_default(minimum_tier, 1)):
        return False
    return True


def inventory_matching_property_key(inventory, *, property_id=None, key_id=None):
    return inventory_matching_property_credential(
        inventory,
        property_id=property_id,
        key_id=key_id,
        allowed_kinds=("mechanical_key",),
    )


def inventory_matching_property_credential(
    inventory,
    *,
    property_id=None,
    key_id=None,
    allowed_kinds=None,
    minimum_tier=None,
):
    if not inventory:
        return None
    for entry in getattr(inventory, "items", ()):
        if entry_matches_property_credential(
            entry,
            property_id=property_id,
            key_id=key_id,
            allowed_kinds=allowed_kinds,
            minimum_tier=minimum_tier,
        ):
            return entry
    return None


def can_receive_property_key(sim, actor_eid, prop):
    return can_receive_property_credential(sim, actor_eid, prop, credential_kind="mechanical_key")


def can_receive_property_credential(sim, actor_eid, prop, *, credential_kind="mechanical_key", credential_tier=None):
    if sim is None or actor_eid is None or not isinstance(prop, dict):
        return False
    if not property_credential_uses_inventory(credential_kind):
        return True
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if not inventory:
        return False

    state = property_lock_state(prop)
    if inventory_matching_property_credential(
        inventory,
        property_id=prop.get("id"),
        key_id=state["key_id"],
        allowed_kinds=(credential_kind,),
        minimum_tier=credential_tier,
    ):
        return True
    return len(getattr(inventory, "items", ())) < int(getattr(inventory, "capacity", 0))


def ensure_actor_has_property_key(sim, actor_eid, prop, owner_tag="player"):
    return ensure_actor_has_property_credential(
        sim,
        actor_eid,
        prop,
        owner_tag=owner_tag,
        credential_kind="mechanical_key",
    )


def ensure_actor_has_property_credential(
    sim,
    actor_eid,
    prop,
    owner_tag="player",
    *,
    credential_kind="mechanical_key",
    holder_role="holder",
    credential_tier=None,
    display_name=None,
):
    if sim is None or actor_eid is None or not isinstance(prop, dict):
        return False, None, False
    resolved_kind = _normalize_credential_kind(credential_kind)
    if not property_credential_uses_inventory(resolved_kind):
        return True, None, False

    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if not inventory:
        return False, None, False

    state = property_lock_state(prop)
    if not state["key_id"]:
        return False, None, False

    existing = inventory_matching_property_credential(
        inventory,
        property_id=prop.get("id"),
        key_id=state["key_id"],
        allowed_kinds=(resolved_kind,),
        minimum_tier=credential_tier,
    )
    if existing:
        return True, existing.get("instance_id"), False

    item_id = property_credential_item_id(resolved_kind)
    item_def = ITEM_CATALOG.get(item_id, {
        "id": item_id,
        "stack_max": 1,
    })
    added, instance_id = inventory.add_item(
        item_id=item_id,
        quantity=1,
        stack_max=int(item_def.get("stack_max", 1)),
        instance_factory=sim.new_item_instance_id,
        owner_eid=actor_eid,
        owner_tag=owner_tag,
        metadata=property_credential_item_metadata(
            prop,
            credential_kind=resolved_kind,
            holder_role=holder_role,
            credential_tier=credential_tier,
            display_name=display_name,
        ),
    )
    return bool(added), instance_id, bool(added)


def remove_actor_property_key(sim, actor_eid, prop):
    return remove_actor_property_credential(
        sim,
        actor_eid,
        prop,
        credential_kind="mechanical_key",
    )


def remove_actor_property_credential(sim, actor_eid, prop, *, credential_kind="mechanical_key"):
    if sim is None or actor_eid is None or not isinstance(prop, dict):
        return False
    resolved_kind = _normalize_credential_kind(credential_kind)
    if not property_credential_uses_inventory(resolved_kind):
        return False

    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if not inventory:
        return False

    existing = inventory_matching_property_credential(
        inventory,
        property_id=prop.get("id"),
        key_id=property_lock_state(prop)["key_id"],
        allowed_kinds=(resolved_kind,),
    )
    if not existing:
        return False

    removed = inventory.remove_item(
        instance_id=existing.get("instance_id"),
        quantity=max(1, _int_or_default(existing.get("quantity"), 1)),
    )
    return bool(removed)


def remove_actor_property_credentials(sim, actor_eid, prop, *, allowed_kinds=None):
    if sim is None or actor_eid is None or not isinstance(prop, dict):
        return 0

    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if not inventory:
        return 0

    removed = 0
    for entry in list(getattr(inventory, "items", ())):
        if not entry_matches_property_credential(
            entry,
            property_id=prop.get("id"),
            key_id=property_lock_state(prop)["key_id"],
            allowed_kinds=allowed_kinds,
        ):
            continue
        quantity = max(1, _int_or_default(entry.get("quantity"), 1))
        if inventory.remove_item(instance_id=entry.get("instance_id"), quantity=quantity):
            removed += 1
    return removed


def sync_owned_property_key_state(
    sim,
    prop,
    *,
    lock_if_owned=True,
    lock_tier=1,
    key_label=None,
):
    if sim is None or not isinstance(prop, dict):
        return {
            "issued": False,
            "created": False,
            "locked": False,
            "key_required": False,
        }

    owner_eid = prop.get("owner_eid")
    owner_tag = _text(prop.get("owner_tag")).lower() or "npc"
    if owner_eid is None:
        return {
            "issued": False,
            "created": False,
            "locked": False,
            "key_required": False,
        }

    ensure_property_lock(
        prop,
        locked=bool(lock_if_owned),
        key_label=key_label,
        lock_tier=lock_tier,
    )
    issued, _instance_id, created = ensure_actor_has_property_key(
        sim,
        owner_eid,
        prop,
        owner_tag=owner_tag,
    )
    locked = bool(lock_if_owned)
    if locked and not issued:
        metadata = prop.get("metadata")
        if isinstance(metadata, dict):
            metadata["property_locked"] = False
        locked = False
    return {
        "issued": bool(issued),
        "created": bool(created),
        "locked": bool(locked),
        "key_required": bool(lock_if_owned),
    }
