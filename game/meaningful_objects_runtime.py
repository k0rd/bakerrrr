"""Meaningful item-backed objects for NPCs, places, dreams, and rewards."""

from __future__ import annotations

import copy
import hashlib
import random
from collections.abc import Mapping
from typing import Any

from engine.events import Event

from game.components import AI, CreatureIdentity, Inventory, NPCMemory, Position, Vitality
from game.items import ITEM_CATALOG
from game.object_profile_runtime import (
    OBJECT_PROFILE_FAMILIES,
    OBJECT_PROFILE_SILHOUETTES,
    generated_object_profile,
    item_backed_fixture_metadata,
    object_profile_display_text,
    object_profile_effects,
    property_is_item_backed_fixture,
)
from game.system_support.awareness_runtime import observation_payload_for_position
from game.system_support.entity_naming import _entity_display_name
from game.system_support.offense_runtime import _emit_action_offense_event


MEANINGFUL_OBJECT_ITEM_ID = "meaningful_object"
MEANINGFUL_OBJECT_SCHEMA_VERSION = 1
DEFAULT_MEANINGFUL_OBJECT_CAPS = {
    "actor_fixtures": 1,
    "property_fixtures": 3,
    "chunk_fixtures": 12,
}

PERSONAL_OBJECT_FAMILIES = (
    "personal_home",
    "tokens_charms",
    "textiles",
    "paper_books",
    "tools_parts",
    "light_ritual",
    "nature_finds",
    "medical_herbal",
)

PLACE_OBJECT_FAMILIES = (
    "personal_home",
    "trade_work",
    "plants_pots",
    "light_ritual",
    "paper_books",
    "tools_parts",
    "medical_herbal",
    "containers",
    "nature_finds",
)


def _text(value: Any, default: str = "") -> str:
    text = str(value if value is not None else default).strip()
    return text


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _stable_seed(*parts: Any) -> int:
    payload = repr(parts).encode("utf-8", errors="replace")
    return int.from_bytes(hashlib.sha256(payload).digest()[:8], "big")


def meaningful_objects_state(sim: Any) -> dict[str, Any]:
    """Return normalized meaningful-object state, creating old-save defaults."""

    state = getattr(sim, "meaningful_objects", None)
    if not isinstance(state, dict):
        state = {}
        setattr(sim, "meaningful_objects", state)
    for key in ("objects", "actor_index", "place_index", "player_knowledge"):
        if not isinstance(state.get(key), dict):
            state[key] = {}
    if not hasattr(sim, "next_meaningful_object_id"):
        sim.next_meaningful_object_id = 1
    return state


def _next_object_id(sim: Any) -> str:
    current = max(1, _safe_int(getattr(sim, "next_meaningful_object_id", 1), 1))
    sim.next_meaningful_object_id = current + 1
    return f"meaningful-{current}"


def _actor_role(sim: Any, eid: int) -> str:
    ai = sim.ecs.get(AI).get(eid) if sim is not None else None
    return _text(getattr(ai, "role", ""), "person").lower() or "person"


def _actor_style_seed(sim: Any, eid: int) -> str:
    identity = sim.ecs.get(CreatureIdentity).get(eid) if sim is not None else None
    record = sim.entity_identity_record(eid) if sim is not None and hasattr(sim, "entity_identity_record") else None
    bits = [
        _text(getattr(identity, "creature_type", ""), "person"),
        _text(getattr(identity, "gender_identity", "")),
        _actor_role(sim, eid),
    ]
    if isinstance(record, dict):
        bits.extend(
            _text(record.get(key))
            for key in ("appearance_seed", "style", "home_property_id", "work_property_id")
            if _text(record.get(key))
        )
    return "|".join(bit for bit in bits if bit)


def _is_eligible_personal_actor(sim: Any, eid: Any) -> bool:
    try:
        eid = int(eid)
    except (TypeError, ValueError):
        return False
    if getattr(sim, "player_eid", None) == eid:
        return False
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    if not identity or _text(getattr(identity, "taxonomy_class", "")).lower() != "hominid":
        return False
    vitality = sim.ecs.get(Vitality).get(eid)
    if vitality is not None and (bool(getattr(vitality, "dead", False)) or bool(getattr(vitality, "downed", False))):
        return False
    return True


def _family_for_actor(sim: Any, eid: int, rng: random.Random) -> str:
    role = _actor_role(sim, eid)
    weighted = []
    if any(word in role for word in ("guard", "security", "watch", "justice")):
        weighted.extend(("tokens_charms", "tools_parts", "light_ritual", "paper_books"))
    if any(word in role for word in ("medic", "doctor", "herbal", "remedy", "clinic")):
        weighted.extend(("medical_herbal", "nature_finds", "paper_books", "light_ritual"))
    if any(word in role for word in ("clerk", "merchant", "bartender", "dealer", "counter")):
        weighted.extend(("trade_work", "tokens_charms", "personal_home", "paper_books"))
    if any(word in role for word in ("driver", "courier", "mechanic", "worker", "repair")):
        weighted.extend(("tools_parts", "trade_work", "tokens_charms", "textiles"))
    if any(word in role for word in ("gardener", "forager", "ranger", "hunter")):
        weighted.extend(("nature_finds", "plants_pots", "medical_herbal", "tools_parts"))
    weighted.extend(PERSONAL_OBJECT_FAMILIES)
    choices = tuple(family for family in weighted if family in OBJECT_PROFILE_FAMILIES)
    return rng.choice(choices or PERSONAL_OBJECT_FAMILIES)


def _family_for_place(context: Mapping[str, Any] | None, rng: random.Random) -> str:
    context = context if isinstance(context, Mapping) else {}
    archetype = _text(context.get("archetype") or context.get("place_kind")).lower()
    ritual = _text(context.get("ritual_kind")).lower()
    weighted = []
    if any(word in archetype for word in ("herbal", "garden", "clinic")) or "plant" in ritual:
        weighted.extend(("plants_pots", "medical_herbal", "nature_finds", "light_ritual"))
    if any(word in archetype for word in ("store", "market", "shop", "office", "counter")):
        weighted.extend(("trade_work", "paper_books", "containers", "tokens_charms"))
    if any(word in archetype for word in ("home", "residence", "shelter", "lodging")):
        weighted.extend(("personal_home", "textiles", "light_ritual", "plants_pots"))
    if any(word in ritual for word in ("repair", "manifest", "shelf", "driver")):
        weighted.extend(("tools_parts", "trade_work", "paper_books"))
    weighted.extend(PLACE_OBJECT_FAMILIES)
    choices = tuple(family for family in weighted if family in OBJECT_PROFILE_FAMILIES)
    return rng.choice(choices or PLACE_OBJECT_FAMILIES)


def _profile_with_display(seed: Any, family: str) -> dict[str, Any]:
    profile = generated_object_profile(seed, family=family)
    profile["placeable"] = True
    profile["pickup_allowed"] = True
    profile["display_name"] = ""
    profile.setdefault("future_tags", [])
    return profile


def ensure_actor_personal_object(sim: Any, actor_eid: Any, *, create: bool = True) -> dict[str, Any] | None:
    """Return an NPC's hidden personal-object entry, creating it lazily."""

    state = meaningful_objects_state(sim)
    try:
        actor_eid = int(actor_eid)
    except (TypeError, ValueError):
        return None
    key = str(actor_eid)
    existing_id = _text(state["actor_index"].get(key))
    if existing_id and isinstance(state["objects"].get(existing_id), dict):
        return state["objects"][existing_id]
    if not create or not _is_eligible_personal_actor(sim, actor_eid):
        return None
    seed = _stable_seed("actor-object", getattr(sim, "seed", 0), actor_eid, _actor_style_seed(sim, actor_eid))
    rng = random.Random(seed)
    family = _family_for_actor(sim, actor_eid, rng)
    profile = _profile_with_display(seed, family)
    object_id = _next_object_id(sim)
    entry = {
        "schema_version": MEANINGFUL_OBJECT_SCHEMA_VERSION,
        "object_id": object_id,
        "source_kind": "actor",
        "owner_eid": int(actor_eid),
        "source_property_id": "",
        "object_profile": profile,
        "meaning_kind": rng.choice(("keepsake", "work_token", "comfort", "habit", "private_charm")),
        "created_tick": int(getattr(sim, "tick", 0) or 0),
        "materialized_property_ids": [],
        "lineage": {
            "seed": int(seed),
            "role": _actor_role(sim, actor_eid),
            "family": family,
        },
    }
    state["objects"][object_id] = entry
    state["actor_index"][key] = object_id
    return entry


def ensure_place_meaningful_object(
    sim: Any,
    property_id: str,
    *,
    context: Mapping[str, Any] | None = None,
    family: str | None = None,
    create: bool = True,
) -> dict[str, Any] | None:
    state = meaningful_objects_state(sim)
    property_id = _text(property_id)
    if not property_id:
        return None
    bucket = state["place_index"].setdefault(property_id, [])
    if not isinstance(bucket, list):
        bucket = []
        state["place_index"][property_id] = bucket
    for object_id in tuple(bucket):
        entry = state["objects"].get(_text(object_id))
        if isinstance(entry, dict):
            return entry
    if not create:
        return None
    prop = getattr(sim, "properties", {}).get(property_id)
    seed = _stable_seed("place-object", getattr(sim, "seed", 0), property_id, context or {})
    rng = random.Random(seed)
    family_key = family if family in OBJECT_PROFILE_FAMILIES else _family_for_place(
        {
            **(context if isinstance(context, Mapping) else {}),
            "archetype": ((prop or {}).get("metadata") or {}).get("archetype") if isinstance((prop or {}).get("metadata"), dict) else "",
            "place_kind": (prop or {}).get("kind"),
        },
        rng,
    )
    profile = _profile_with_display(seed, family_key)
    object_id = _next_object_id(sim)
    entry = {
        "schema_version": MEANINGFUL_OBJECT_SCHEMA_VERSION,
        "object_id": object_id,
        "source_kind": "place",
        "owner_eid": None,
        "source_property_id": property_id,
        "object_profile": profile,
        "meaning_kind": _text((context or {}).get("ritual_kind"), "place_habit"),
        "created_tick": int(getattr(sim, "tick", 0) or 0),
        "materialized_property_ids": [],
        "lineage": {
            "seed": int(seed),
            "family": family_key,
            "property_id": property_id,
        },
    }
    state["objects"][object_id] = entry
    bucket.append(object_id)
    return entry


def meaningful_object_entry(sim: Any, object_id: Any) -> dict[str, Any] | None:
    state = meaningful_objects_state(sim)
    row = state["objects"].get(_text(object_id))
    return row if isinstance(row, dict) else None


def _object_context(entry: Mapping[str, Any], *, placement_source: str, property_id: str = "") -> dict[str, Any]:
    source_property_id = _text(property_id) or _text(entry.get("source_property_id"))
    return {
        "schema_version": MEANINGFUL_OBJECT_SCHEMA_VERSION,
        "meaningful_object_id": _text(entry.get("object_id")),
        "source_kind": _text(entry.get("source_kind")),
        "owner_eid": entry.get("owner_eid"),
        "source_property_id": source_property_id,
        "meaning_kind": _text(entry.get("meaning_kind")),
        "placement_source": _text(placement_source, "meaningful_object"),
    }


def _chunk_key_for(sim: Any, x: int, y: int) -> str:
    try:
        chunk = sim.chunk_coords(int(x), int(y))
    except Exception:
        chunk = (int(x) // max(1, int(getattr(sim, "chunk_size", 16) or 16)), int(y) // max(1, int(getattr(sim, "chunk_size", 16) or 16)))
    return f"{int(chunk[0])},{int(chunk[1])}"


def _fixture_object_context(prop: Mapping[str, Any] | None) -> dict[str, Any]:
    metadata = prop.get("metadata") if isinstance((prop or {}).get("metadata"), Mapping) else {}
    context = metadata.get("object_context") if isinstance(metadata.get("object_context"), Mapping) else {}
    if context:
        return dict(context)
    source_metadata = metadata.get("source_item_metadata") if isinstance(metadata.get("source_item_metadata"), Mapping) else {}
    context = source_metadata.get("object_context") if isinstance(source_metadata.get("object_context"), Mapping) else {}
    return dict(context) if context else {}


def _meaningful_fixture_props(sim: Any) -> list[dict[str, Any]]:
    rows = []
    for prop in tuple(getattr(sim, "properties", {}).values()):
        if not property_is_item_backed_fixture(prop):
            continue
        context = _fixture_object_context(prop)
        if _text(context.get("meaningful_object_id")):
            rows.append(prop)
    return rows


def _cap_counts(sim: Any, *, x: int, y: int, property_id: str = "", actor_eid: Any = None) -> dict[str, int]:
    chunk_key = _chunk_key_for(sim, x, y)
    counts = {"chunk": 0, "property": 0, "actor": 0}
    for prop in _meaningful_fixture_props(sim):
        context = _fixture_object_context(prop)
        px = _safe_int(prop.get("x"), 0)
        py = _safe_int(prop.get("y"), 0)
        if _chunk_key_for(sim, px, py) == chunk_key:
            counts["chunk"] += 1
        if property_id and _text(context.get("source_property_id")) == property_id:
            counts["property"] += 1
        if actor_eid is not None and context.get("owner_eid") is not None:
            try:
                if int(context.get("owner_eid")) == int(actor_eid):
                    counts["actor"] += 1
            except (TypeError, ValueError):
                pass
    return counts


def _tile_allows_object(sim: Any, x: int, y: int, z: int) -> tuple[bool, str]:
    tile = sim.tilemap.tile_at(int(x), int(y), int(z)) if hasattr(sim, "tilemap") else None
    if tile is None:
        return False, "no_tile"
    if not bool(getattr(tile, "walkable", False)):
        return False, "blocked_tile"
    if hasattr(sim, "property_at") and sim.property_at(int(x), int(y), int(z)):
        return False, "occupied_fixture"
    if hasattr(sim, "ground_items_at") and sim.ground_items_at(int(x), int(y), z=int(z)):
        return False, "ground_item_present"
    return True, ""


def materialize_meaningful_object_fixture(
    sim: Any,
    object_id: Any,
    x: int,
    y: int,
    z: int = 0,
    *,
    source_property_id: str = "",
    placement_source: str = "meaningful_object",
    enforce_caps: bool = True,
) -> dict[str, Any]:
    """Create a visible item-backed fixture for a meaningful object."""

    entry = meaningful_object_entry(sim, object_id)
    if not isinstance(entry, dict):
        return {"ok": False, "reason": "missing_object"}
    x, y, z = int(x), int(y), int(z)
    ok, reason = _tile_allows_object(sim, x, y, z)
    if not ok:
        return {"ok": False, "reason": reason}
    source_property_id = _text(source_property_id or entry.get("source_property_id"))
    owner_eid = entry.get("owner_eid")
    if enforce_caps:
        counts = _cap_counts(sim, x=x, y=y, property_id=source_property_id, actor_eid=owner_eid)
        if owner_eid is not None and counts["actor"] >= DEFAULT_MEANINGFUL_OBJECT_CAPS["actor_fixtures"]:
            return {"ok": False, "reason": "actor_cap"}
        if source_property_id and counts["property"] >= DEFAULT_MEANINGFUL_OBJECT_CAPS["property_fixtures"]:
            return {"ok": False, "reason": "property_cap"}
        if counts["chunk"] >= DEFAULT_MEANINGFUL_OBJECT_CAPS["chunk_fixtures"]:
            return {"ok": False, "reason": "chunk_cap"}

    item_def = dict(ITEM_CATALOG.get(MEANINGFUL_OBJECT_ITEM_ID, {}))
    if not item_def:
        return {"ok": False, "reason": "missing_item_def"}
    profile = copy.deepcopy(entry.get("object_profile") if isinstance(entry.get("object_profile"), Mapping) else {})
    context = _object_context(entry, placement_source=placement_source, property_id=source_property_id)
    item_entry = {
        "item_id": MEANINGFUL_OBJECT_ITEM_ID,
        "instance_id": f"{MEANINGFUL_OBJECT_ITEM_ID}:{entry['object_id']}",
        "quantity": 1,
        "owner_eid": owner_eid,
        "owner_tag": "npc" if owner_eid is not None else "public",
        "metadata": {
            "object_profile": profile,
            "object_context": context,
            "meaningful_object_id": entry["object_id"],
            "source_context": "personal_object" if owner_eid is not None else "place_object",
            "visual_seed": f"{entry['object_id']}:{placement_source}",
        },
    }
    metadata = item_backed_fixture_metadata(item_entry, item_def, tick=int(getattr(sim, "tick", 0) or 0), source=placement_source)
    metadata["object_context"] = copy.deepcopy(context)
    metadata["meaningful_object_id"] = entry["object_id"]
    metadata["public"] = owner_eid is None
    metadata["source_item_owner_eid"] = owner_eid
    metadata["source_item_owner_tag"] = "npc" if owner_eid is not None else "public"
    metadata["source_item_metadata"]["object_context"] = copy.deepcopy(context)
    metadata["source_item_metadata"]["meaningful_object_id"] = entry["object_id"]
    metadata["source_item_metadata"]["source_context"] = "personal_object" if owner_eid is not None else "place_object"
    metadata["pickup_allowed"] = bool(profile.get("pickup_allowed", True))
    name = object_profile_display_text(profile, fallback_name=item_def.get("name", "Object"))
    property_id = sim.register_property(
        name=name or "Object",
        kind="fixture",
        x=x,
        y=y,
        z=z,
        owner_eid=owner_eid,
        owner_tag="npc" if owner_eid is not None else "public",
        metadata=metadata,
    )
    materialized = entry.setdefault("materialized_property_ids", [])
    if isinstance(materialized, list) and property_id not in materialized:
        materialized.append(property_id)
    return {"ok": True, "property_id": property_id, "object_id": entry["object_id"], "metadata": metadata}


def materialize_actor_personal_object_near(
    sim: Any,
    actor_eid: Any,
    x: int,
    y: int,
    z: int = 0,
    *,
    source_property_id: str = "",
    placement_source: str = "personal_object",
) -> dict[str, Any]:
    entry = ensure_actor_personal_object(sim, actor_eid)
    if not entry:
        return {"ok": False, "reason": "ineligible_actor"}
    return materialize_meaningful_object_fixture(
        sim,
        entry["object_id"],
        x,
        y,
        z,
        source_property_id=source_property_id,
        placement_source=placement_source,
    )


def materialize_place_object_near(
    sim: Any,
    property_id: str,
    x: int,
    y: int,
    z: int = 0,
    *,
    context: Mapping[str, Any] | None = None,
    placement_source: str = "place_object",
) -> dict[str, Any]:
    entry = ensure_place_meaningful_object(sim, property_id, context=context)
    if not entry:
        return {"ok": False, "reason": "missing_place_object"}
    return materialize_meaningful_object_fixture(
        sim,
        entry["object_id"],
        x,
        y,
        z,
        source_property_id=property_id,
        placement_source=placement_source,
    )


def _fixture_sort_key(sim: Any, actor_eid: Any, pos: Position, prop: Mapping[str, Any]) -> tuple:
    px = _safe_int(prop.get("x"), 0)
    py = _safe_int(prop.get("y"), 0)
    return (
        max(abs(px - int(pos.x)), abs(py - int(pos.y))),
        abs(px - int(pos.x)) + abs(py - int(pos.y)),
        str(prop.get("id", "")),
    )


def nearest_item_backed_object_fixture(
    sim: Any,
    actor_eid: Any,
    pos: Position,
    *,
    preferred_dir: tuple[int, int] | None = None,
    exact_direction: bool = False,
) -> dict[str, Any] | None:
    if pos is None:
        return None
    nearby = list(sim.properties_in_radius(int(pos.x), int(pos.y), int(pos.z), r=1))
    if exact_direction:
        if not isinstance(preferred_dir, tuple) or len(preferred_dir) < 2:
            return None
        dx = _safe_int(preferred_dir[0], 0)
        dy = _safe_int(preferred_dir[1], 0)
        if dx == 0 and dy == 0:
            return None
        target_x = int(pos.x) + dx
        target_y = int(pos.y) + dy
        nearby = [
            prop
            for prop in nearby
            if _safe_int(prop.get("x"), 0) == target_x
            and _safe_int(prop.get("y"), 0) == target_y
            and _safe_int(prop.get("z"), int(pos.z)) == int(pos.z)
        ]
    candidates = [
        prop
        for prop in nearby
        if property_is_item_backed_fixture(prop)
        and bool((prop.get("metadata") if isinstance(prop.get("metadata"), Mapping) else {}).get("pickup_allowed", True))
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda prop: _fixture_sort_key(sim, actor_eid, pos, prop))
    return candidates[0]


def object_meaning_learned(sim: Any, object_id: Any, *, viewer_eid: Any = None) -> bool:
    state = meaningful_objects_state(sim)
    object_id = _text(object_id)
    if not object_id:
        return False
    viewer_key = str(viewer_eid if viewer_eid is not None else getattr(sim, "player_eid", "player"))
    knowledge = state["player_knowledge"].get(viewer_key)
    if not isinstance(knowledge, dict):
        return False
    return object_id in knowledge


def learn_meaningful_object(
    sim: Any,
    object_id: Any,
    *,
    viewer_eid: Any = None,
    source: str = "unknown",
    witness_eid: Any = None,
) -> dict[str, Any] | None:
    entry = meaningful_object_entry(sim, object_id)
    if not entry:
        return None
    viewer_key = str(viewer_eid if viewer_eid is not None else getattr(sim, "player_eid", "player"))
    state = meaningful_objects_state(sim)
    bucket = state["player_knowledge"].setdefault(viewer_key, {})
    if not isinstance(bucket, dict):
        bucket = {}
        state["player_knowledge"][viewer_key] = bucket
    learned = {
        "object_id": entry["object_id"],
        "source": _text(source, "unknown"),
        "learned_tick": int(getattr(sim, "tick", 0) or 0),
        "witness_eid": witness_eid,
        "source_kind": _text(entry.get("source_kind")),
        "owner_eid": entry.get("owner_eid"),
        "source_property_id": _text(entry.get("source_property_id")),
        "meaning_kind": _text(entry.get("meaning_kind")),
    }
    bucket[entry["object_id"]] = learned
    sim.emit(Event("meaningful_object_learned", eid=viewer_eid, object_id=entry["object_id"], source=source, witness_eid=witness_eid))
    return learned


def meaningful_object_display_text(
    sim: Any,
    prop: Mapping[str, Any],
    *,
    viewer_eid: Any = None,
    include_learned: bool = True,
) -> str:
    metadata = prop.get("metadata") if isinstance((prop or {}).get("metadata"), Mapping) else {}
    profile = metadata.get("object_profile") if isinstance(metadata.get("object_profile"), Mapping) else {}
    fallback = _text(prop.get("name"), "object")
    neutral = object_profile_display_text(profile, fallback_name=fallback)
    context = _fixture_object_context(prop)
    object_id = _text(context.get("meaningful_object_id") or metadata.get("meaningful_object_id"))
    if not include_learned or not object_id or not object_meaning_learned(sim, object_id, viewer_eid=viewer_eid):
        return neutral
    owner_eid = context.get("owner_eid")
    if owner_eid is not None:
        owner_name = _entity_display_name(sim, owner_eid, title_case=False)
        return f"{neutral}, one of {owner_name}'s things"
    source_property_id = _text(context.get("source_property_id"))
    prop_name = ""
    if source_property_id:
        source_prop = getattr(sim, "properties", {}).get(source_property_id)
        prop_name = _text((source_prop or {}).get("name"))
    if prop_name:
        return f"{neutral}, a kept object from {prop_name}"
    return neutral


def _owner_can_notice_pickup(sim: Any, owner_eid: Any, x: int, y: int, z: int, *, actor_eid: Any = None) -> bool:
    if owner_eid is None:
        return False
    try:
        owner_eid = int(owner_eid)
    except (TypeError, ValueError):
        return False
    owner_pos = sim.ecs.get(Position).get(owner_eid)
    if owner_pos is None or int(owner_pos.z) != int(z):
        return False
    if max(abs(int(owner_pos.x) - int(x)), abs(int(owner_pos.y) - int(y))) > 8:
        return False
    observation = observation_payload_for_position(
        sim,
        int(x),
        int(y),
        int(z),
        exclude_eid=actor_eid,
        offender_eid=actor_eid,
        observation_channels=("actor_witness",),
    )
    for key in ("accountable_observer_eids", "observer_eids", "witnesses"):
        values = observation.get(key)
        if isinstance(values, (list, tuple, set)) and owner_eid in {int(value) for value in values if str(value).lstrip("-").isdigit()}:
            return True
    return False


def pickup_meaningful_object_fixture(sim: Any, actor_eid: Any, property_id: str) -> dict[str, Any]:
    """Pick up an item-backed fixture and apply meaningful-object provenance."""

    prop = getattr(sim, "properties", {}).get(str(property_id))
    if not property_is_item_backed_fixture(prop):
        return {"ok": False, "reason": "not_item_backed_fixture"}
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if inventory is None:
        return {"ok": False, "reason": "no_inventory"}
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), Mapping) else {}
    context = _fixture_object_context(prop)
    owner_eid = context.get("owner_eid")
    source_kind = _text(context.get("source_kind"))
    object_id = _text(context.get("meaningful_object_id") or metadata.get("meaningful_object_id"))
    is_personal_theft = owner_eid is not None and str(owner_eid) != str(actor_eid)
    x = _safe_int(prop.get("x"), 0)
    y = _safe_int(prop.get("y"), 0)
    z = _safe_int(prop.get("z"), 0)

    from game.object_profile_runtime import pickup_item_backed_fixture

    result = pickup_item_backed_fixture(sim, inventory, str(property_id), item_catalog=ITEM_CATALOG)
    if not result.get("ok"):
        return result

    entry = inventory.find(instance_id=result.get("instance_id")) if result.get("instance_id") else None
    item_name = "object"
    if isinstance(entry, dict):
        entry_metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        entry_metadata["object_context"] = copy.deepcopy(context)
        entry_metadata["meaningful_object_id"] = object_id
        if is_personal_theft:
            entry_metadata["source_owner_eid"] = owner_eid
            entry_metadata["source_owner_tag"] = "npc"
            entry_metadata["source_context"] = "personal_object_pickup"
            entry_metadata["direct_theft"] = True
            entry_metadata["justice_stolen"] = True
            entry_metadata["stolen_tick"] = int(getattr(sim, "tick", 0) or 0)
        else:
            entry_metadata.setdefault("source_context", "place_object_pickup" if source_kind == "place" else "object_pickup")
        entry["metadata"] = entry_metadata
        item_name = object_profile_display_text(entry_metadata.get("object_profile"), fallback_name="object")

    sim.emit(Event(
        "item_backed_fixture_picked_up",
        eid=actor_eid,
        property_id=str(property_id),
        item_id=result.get("item_id"),
        instance_id=result.get("instance_id"),
        item_name=item_name,
        object_id=object_id or None,
        x=x,
        y=y,
        z=z,
    ))

    if not is_personal_theft:
        return {**result, "object_id": object_id, "theft": False, "item_name": item_name}

    observation = observation_payload_for_position(
        sim,
        x,
        y,
        z,
        exclude_eid=actor_eid,
        offender_eid=actor_eid,
        observation_channels=("actor_witness",),
    )
    sim.emit(Event(
        "item_stolen",
        offender_eid=actor_eid,
        item_id=result.get("item_id"),
        item_name=item_name,
        owner_eid=owner_eid,
        owner_tag="npc",
        property_id=context.get("source_property_id") or None,
        object_id=object_id or None,
        x=x,
        y=y,
        z=z,
        **observation,
    ))
    _emit_action_offense_event(
        sim,
        actor_eid,
        "pickup_item",
        x,
        y,
        z,
        context="item_theft",
        property_id=context.get("source_property_id") or None,
        object_id=object_id or None,
        **observation,
    )
    witnessed_by_owner = _owner_can_notice_pickup(sim, owner_eid, x, y, z, actor_eid=actor_eid)
    if witnessed_by_owner and object_id:
        learn_meaningful_object(sim, object_id, viewer_eid=getattr(sim, "player_eid", actor_eid), source="owner_reaction", witness_eid=owner_eid)
        owner_name = _entity_display_name(sim, owner_eid, title_case=False)
        sim.emit(Event(
            "meaningful_object_owner_reaction",
            eid=owner_eid,
            offender_eid=actor_eid,
            object_id=object_id,
            item_name=item_name,
            owner_name=owner_name,
            x=x,
            y=y,
            z=z,
        ))
        memory = sim.ecs.get(NPCMemory).get(owner_eid)
        if memory is not None:
            memory.remember(
                int(getattr(sim, "tick", 0) or 0),
                "personal_object_taken",
                strength=1.0,
                offender_eid=actor_eid,
                object_id=object_id,
                item_name=item_name,
            )
    return {
        **result,
        "object_id": object_id,
        "theft": True,
        "witnessed_by_owner": bool(witnessed_by_owner),
        "item_name": item_name,
    }


def dream_object_props_for_scene(
    sim: Any,
    dream_actors: tuple[Mapping[str, Any], ...] | list[Mapping[str, Any]],
    *,
    rng: random.Random,
    width: int,
    height: int,
    limit: int = 5,
) -> tuple[dict[str, Any], ...]:
    """Return dream-only prop render rows from known or warmed NPC objects."""

    props = []
    occupied = {
        (int(actor.get("x", 0) or 0), int(actor.get("y", 0) or 0))
        for actor in dream_actors
        if isinstance(actor, Mapping)
    }
    for actor in tuple(dream_actors or ()):
        if not isinstance(actor, Mapping):
            continue
        source_eid = actor.get("source_eid")
        entry = ensure_actor_personal_object(sim, source_eid, create=True) if source_eid is not None else None
        if not entry:
            continue
        profile = entry.get("object_profile") if isinstance(entry.get("object_profile"), Mapping) else {}
        family = _text(profile.get("family"), "personal_home")
        silhouettes = OBJECT_PROFILE_SILHOUETTES.get(family, ("object",))
        ax = _safe_int(actor.get("x"), width // 2)
        ay = _safe_int(actor.get("y"), height // 2)
        candidates = [
            (ax + dx, ay + dy)
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, 1), (1, -1), (-1, -1))
            if 1 <= ax + dx < max(1, width - 1) and 1 <= ay + dy < max(1, height - 1)
        ]
        rng.shuffle(candidates)
        chosen = None
        for cell in candidates:
            if cell in occupied:
                continue
            chosen = cell
            break
        if chosen is None:
            continue
        occupied.add(chosen)
        signature_seed = _stable_seed("dream-prop", entry.get("object_id"), actor.get("dream_actor_id"), rng.random())
        profile_copy = copy.deepcopy(dict(profile))
        if not _text(profile_copy.get("silhouette")) and silhouettes:
            profile_copy["silhouette"] = silhouettes[0]
        props.append({
            "dream_prop_id": f"prop-{len(props) + 1}",
            "source_eid": source_eid,
            "object_id": entry.get("object_id"),
            "x": chosen[0],
            "y": chosen[1],
            "glyph": _text(profile_copy.get("display_glyph"), "o")[:1] or "o",
            "color": _text(profile_copy.get("display_color"), "world_object_home"),
            "semantic_id": f"world_object_{_text(profile_copy.get('family'), 'personal_home')}",
            "effects": tuple(object_profile_effects(profile_copy)),
            "visual_seed": int(signature_seed & 0xFFFF_FFFF),
            "vision_only": True,
            "consequence_ineligible": True,
        })
        if len(props) >= int(limit):
            break
    return tuple(props)


def reward_object_profile(source_payload: Mapping[str, Any] | None, reward_id: str, *, family_hint: str = "") -> dict[str, Any]:
    """Build an owner-free object profile for generated reward keepsake items."""

    source_payload = source_payload if isinstance(source_payload, Mapping) else {}
    seed = _stable_seed(
        "reward-object-profile",
        reward_id,
        source_payload.get("seed"),
        source_payload.get("objective"),
        source_payload.get("outcome"),
        family_hint,
    )
    rng = random.Random(seed)
    family = family_hint if family_hint in OBJECT_PROFILE_FAMILIES else rng.choice(
        ("tokens_charms", "paper_books", "tools_parts", "personal_home", "nature_finds", "medical_herbal", "light_ritual")
    )
    profile = _profile_with_display(seed, family)
    profile["rarity"] = "unique"
    profile["future_tags"] = tuple(sorted(set(profile.get("future_tags", ())) | {"run_reward", "keepsake"}))
    return profile
