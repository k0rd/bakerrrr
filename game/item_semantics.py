"""Item semantic helpers for canonical item truth vs actor-facing interpretation.

This is intentionally a thin abstraction layer. It centralizes common item
questions so gameplay systems do not hard-code item ids or raw JSON shapes.

Current scope:
- canonical tags/category/legal status
- appearance-family metadata seam for later unidentified items
- inventory scans by semantic tag/id
- actor-facing display hook that can later route through per-actor knowledge
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

from game.items import ITEM_CATALOG, item_display_name


LEGAL_STATUSES = {"legal", "restricted", "suspicious", "illegal", "stolen", "unknown"}
PHONE_TAGS = {"phone", "cellular", "communication", "radio", "comms"}
PHONE_ITEM_IDS = {"mobile_phone", "burner_phone", "unregistered_mobile_phone", "cell_phone", "phone", "radio", "walkie_talkie"}


def _key(value) -> str:
    return str(value or "").strip().lower()


def _entry_item_id(item_or_entry) -> str:
    if isinstance(item_or_entry, Mapping):
        return _key(item_or_entry.get("item_id") or item_or_entry.get("id"))
    return _key(item_or_entry)


def _entry_metadata(item_or_entry) -> dict:
    if isinstance(item_or_entry, Mapping) and isinstance(item_or_entry.get("metadata"), Mapping):
        return dict(item_or_entry.get("metadata") or {})
    return {}


def item_def(item_or_entry, item_catalog=None) -> dict:
    catalog = item_catalog or ITEM_CATALOG
    return dict(catalog.get(_entry_item_id(item_or_entry), {}) or {})


def item_tags(item_or_entry, item_catalog=None) -> set[str]:
    raw = item_def(item_or_entry, item_catalog=item_catalog).get("tags", ())
    return {_key(tag) for tag in raw if _key(tag)}


def has_item_tag(item_or_entry, tags, item_catalog=None) -> bool:
    wanted = {_key(tag) for tag in (tags if isinstance(tags, Iterable) and not isinstance(tags, str) else (tags,)) if _key(tag)}
    return bool(wanted and item_tags(item_or_entry, item_catalog=item_catalog).intersection(wanted))


def item_category(item_or_entry, item_catalog=None) -> str:
    return _key(item_def(item_or_entry, item_catalog=item_catalog).get("category")) or "misc"


def item_legal_status(item_or_entry, item_catalog=None) -> str:
    status = _key(_entry_metadata(item_or_entry).get("legal_status")) or _key(item_def(item_or_entry, item_catalog=item_catalog).get("legal_status"))
    return status if status in LEGAL_STATUSES else "unknown"


def item_appearance_family(item_or_entry, item_catalog=None) -> str:
    return _key(item_def(item_or_entry, item_catalog=item_catalog).get("appearance_family"))


def item_appearance_slots(item_or_entry, item_catalog=None) -> tuple[str, ...]:
    raw = item_def(item_or_entry, item_catalog=item_catalog).get("appearance_slots", ())
    if not isinstance(raw, (list, tuple)):
        return ()
    return tuple(_key(slot) for slot in raw if _key(slot))


def item_runtime_property(item_or_entry, key, default=None):
    metadata = _entry_metadata(item_or_entry)
    return metadata.get(str(key), default)


def item_display_name_for_actor(sim, actor_eid, item_or_entry, *, identified=None, item_catalog=None) -> str:
    """Return what an actor should call an item.

    Today this delegates to canonical display. Later this is the seam for
    per-actor item knowledge and seed-rotated unidentified appearances.
    """
    item_id = _entry_item_id(item_or_entry)
    metadata = _entry_metadata(item_or_entry)
    perceived = ""
    if isinstance(metadata, Mapping):
        perceived = str(metadata.get("perceived_name", "") or "").strip()
    if perceived and identified is False:
        return perceived
    return item_display_name(item_id, metadata=metadata, item_catalog=item_catalog or ITEM_CATALOG)


def is_phone_item(item_or_entry, item_catalog=None) -> bool:
    item_id = _entry_item_id(item_or_entry)
    return item_id in PHONE_ITEM_IDS or has_item_tag(item_or_entry, PHONE_TAGS, item_catalog=item_catalog)


def inventory_has_item_matching(inventory, *, tags=(), item_ids=(), item_catalog=None) -> bool:
    if not inventory:
        return False
    wanted_ids = {_key(item_id) for item_id in item_ids if _key(item_id)}
    wanted_tags = {_key(tag) for tag in tags if _key(tag)}
    for entry in getattr(inventory, "items", ()) or ():
        item_id = _entry_item_id(entry)
        if wanted_ids and item_id in wanted_ids:
            return True
        if wanted_tags and has_item_tag(entry, wanted_tags, item_catalog=item_catalog):
            return True
    return False


def inventory_has_phone(inventory, item_catalog=None) -> bool:
    return inventory_has_item_matching(inventory, tags=PHONE_TAGS, item_ids=PHONE_ITEM_IDS, item_catalog=item_catalog)
