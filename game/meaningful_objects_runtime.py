"""Meaningful item-backed objects for NPCs, places, dreams, and rewards."""

from __future__ import annotations

import copy
import hashlib
import random
from collections.abc import Mapping
from typing import Any

from engine.events import Event

from game.components import AI, CreatureIdentity, Inventory, NPCMemory, NPCSocial, NPCRoutine, NPCSettlement, Occupation, Position, Vitality
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
    for key in ("objects", "actor_index", "place_index", "player_knowledge", "cooldowns"):
        if not isinstance(state.get(key), dict):
            state[key] = {}
    if not hasattr(sim, "next_meaningful_object_id"):
        sim.next_meaningful_object_id = 1
    return state


def _cooldown_bucket(sim: Any, bucket: str) -> dict[str, int]:
    state = meaningful_objects_state(sim)
    cooldowns = state.setdefault("cooldowns", {})
    if not isinstance(cooldowns, dict):
        cooldowns = {}
        state["cooldowns"] = cooldowns
    bucket_key = _text(bucket, "general")
    rows = cooldowns.setdefault(bucket_key, {})
    if not isinstance(rows, dict):
        rows = {}
        cooldowns[bucket_key] = rows
    return rows


def meaningful_object_cooldown_ready(
    sim: Any,
    bucket: str,
    key: Any,
    *,
    cooldown_ticks: int,
    mark: bool = False,
) -> bool:
    """Return whether a meaningful-object presentation cooldown is ready."""

    rows = _cooldown_bucket(sim, bucket)
    key_text = _text(key)
    if not key_text:
        return False
    now = int(getattr(sim, "tick", 0) or 0)
    last = rows.get(key_text)
    try:
        last_tick = int(last)
    except (TypeError, ValueError):
        last_tick = -10**9
    ready = now - last_tick >= max(0, int(cooldown_ticks or 0))
    if mark and ready:
        rows[key_text] = now
    return ready


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


def meaningful_object_fixture_cue(sim: Any, prop: Mapping[str, Any], *, viewer_eid: Any = None) -> dict[str, Any]:
    """Return a non-ESP visible cue for a place object-backed fixture."""

    if not property_is_item_backed_fixture(prop):
        return {}
    context = _fixture_object_context(prop)
    if _text(context.get("source_kind")) != "place":
        return {}
    label = meaningful_object_display_text(sim, prop, viewer_eid=viewer_eid, include_learned=False)
    if not label:
        return {}
    meaning = _text(context.get("meaning_kind"), "place_habit").replace("_", " ")
    return {
        "meaningful_object_id": _text(context.get("meaningful_object_id")),
        "meaningful_object_label": label,
        "meaningful_object_summary": f"a kept {meaning} object is visible: {label}",
        "meaningful_object_action": "inspect the object or ask why it is kept here",
    }


def meaningful_object_entry_summary(sim: Any, object_id: Any, *, viewer_eid: Any = None) -> dict[str, Any]:
    """Return learned/unlearned display-safe summary fields for an object entry."""

    entry = meaningful_object_entry(sim, object_id)
    if not entry:
        return {}
    profile = entry.get("object_profile") if isinstance(entry.get("object_profile"), Mapping) else {}
    neutral = object_profile_display_text(profile, fallback_name="object")
    learned = object_meaning_learned(sim, entry.get("object_id"), viewer_eid=viewer_eid)
    source_kind = _text(entry.get("source_kind"))
    owner_eid = entry.get("owner_eid")
    source_property_id = _text(entry.get("source_property_id"))
    owner_name = ""
    source_property_name = ""
    if learned and owner_eid is not None:
        owner_name = _entity_display_name(sim, owner_eid, title_case=True)
    if learned and source_property_id:
        source_prop = getattr(sim, "properties", {}).get(source_property_id)
        if isinstance(source_prop, Mapping):
            source_property_name = _text(source_prop.get("name"), source_property_id)
    display = neutral
    if learned and owner_name:
        display = f"{neutral}, one of {owner_name}'s things"
    elif learned and source_property_name:
        display = f"{neutral}, a kept object from {source_property_name}"
    return {
        "object_id": _text(entry.get("object_id")),
        "object_label": neutral,
        "display_text": display,
        "learned": bool(learned),
        "source_kind": source_kind,
        "owner_eid": owner_eid,
        "owner_name": owner_name,
        "source_property_id": source_property_id,
        "source_property_name": source_property_name,
        "meaning_kind": _text(entry.get("meaning_kind")),
        "family": _text(profile.get("family")),
    }


def _observer_ids_from_payload(payload: Mapping[str, Any] | None) -> set[int]:
    ids: set[int] = set()
    payload = payload if isinstance(payload, Mapping) else {}
    for key in ("accountable_observer_eids", "observer_eids", "witnesses"):
        values = payload.get(key)
        if not isinstance(values, (list, tuple, set)):
            continue
        for value in values:
            try:
                ids.add(int(value))
            except (TypeError, ValueError):
                continue
    return ids


def _bond_score(sim: Any, left_eid: Any, right_eid: Any) -> float:
    try:
        left = int(left_eid)
        right = int(right_eid)
    except (TypeError, ValueError):
        return 0.0
    social = sim.ecs.get(NPCSocial).get(left) if sim is not None else None
    bonds = getattr(social, "bonds", None)
    if not isinstance(bonds, dict):
        return 0.0
    bond = bonds.get(right)
    if not isinstance(bond, dict):
        bond = bonds.get(str(right))
    if not isinstance(bond, dict):
        return 0.0
    closeness = float(bond.get("closeness", 0.0) or 0.0)
    trust = float(bond.get("trust", 0.0) or 0.0)
    protectiveness = float(bond.get("protectiveness", 0.0) or 0.0)
    return max(0.0, min(1.0, (closeness * 0.38) + (trust * 0.3) + (protectiveness * 0.32)))


def _credible_pickup_witness(
    sim: Any,
    owner_eid: Any,
    x: int,
    y: int,
    z: int,
    *,
    actor_eid: Any = None,
    observation: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if owner_eid is None:
        return {}
    try:
        owner_eid = int(owner_eid)
    except (TypeError, ValueError):
        return {}
    observation = observation if isinstance(observation, Mapping) else observation_payload_for_position(
        sim,
        int(x),
        int(y),
        int(z),
        exclude_eid=actor_eid,
        offender_eid=actor_eid,
        observation_channels=("actor_witness",),
    )
    observer_ids = _observer_ids_from_payload(observation)
    owner_pos = sim.ecs.get(Position).get(owner_eid)
    if (
        owner_eid in observer_ids
        and owner_pos is not None
        and int(owner_pos.z) == int(z)
        and max(abs(int(owner_pos.x) - int(x)), abs(int(owner_pos.y) - int(y))) <= 8
    ):
        return {"witness_eid": owner_eid, "witness_relation": "owner", "owner_eid": owner_eid, "bond_score": 1.0}
    candidates = []
    for witness_eid in observer_ids:
        if witness_eid == owner_eid:
            continue
        witness_pos = sim.ecs.get(Position).get(witness_eid)
        if witness_pos is None or int(witness_pos.z) != int(z):
            continue
        score = max(_bond_score(sim, witness_eid, owner_eid), _bond_score(sim, owner_eid, witness_eid))
        if score >= 0.55:
            candidates.append((score, witness_eid))
    if not candidates:
        return {}
    candidates.sort(reverse=True)
    return {
        "witness_eid": int(candidates[0][1]),
        "witness_relation": "bonded_witness",
        "owner_eid": owner_eid,
        "bond_score": round(float(candidates[0][0]), 4),
    }


def meaningful_object_owner_reaction_text(sim: Any, event_data: Mapping[str, Any]) -> dict[str, str]:
    """Build deterministic owner/witness reaction copy for the event log."""

    event_data = event_data if isinstance(event_data, Mapping) else {}
    speaker_eid = event_data.get("witness_eid", event_data.get("eid"))
    owner_eid = event_data.get("owner_eid")
    item_name = _text(event_data.get("item_name"), "that")
    owner_name = _text(event_data.get("owner_name"))
    if not owner_name and owner_eid is not None:
        owner_name = _entity_display_name(sim, owner_eid, title_case=True)
    relation = _text(event_data.get("witness_relation"), "owner")
    object_id = _text(event_data.get("object_id"))
    rng = random.Random(_stable_seed("meaningful-object-bark", getattr(sim, "seed", 0), object_id, speaker_eid, owner_eid, item_name, relation))
    if relation == "bonded_witness" and str(speaker_eid) != str(owner_eid):
        owner_bit = owner_name or "someone here"
        banks = {
            "protective": (
                f"Hey. That belongs to {owner_bit}. Put it back.",
                f"Leave {owner_bit}'s {item_name} where it was.",
                f"That is not yours. {owner_bit} keeps track of that.",
                f"Careful. {owner_bit} will know if that walks off.",
            ),
            "guarded": (
                f"I know that piece. It is {owner_bit}'s.",
                f"That has a home here. Do not pocket it.",
                f"You are picking up the wrong kind of keepsake.",
                f"That one matters to {owner_bit}. Set it down.",
            ),
        }
        tone = rng.choice(tuple(banks))
        quote = rng.choice(banks[tone])
        nearby = f"Someone nearby objects as you take {item_name}."
        other_floor = f"Someone on another floor objects as you take {item_name}."
        return {"quote": quote, "nearby_audio": nearby, "other_floor_audio": other_floor, "tone": tone}
    banks = {
        "angry": (
            f"Put that back. {item_name.capitalize()} is mine.",
            f"No. You do not walk off with my {item_name}.",
            f"Hands off. That is one of mine.",
            f"You picked the wrong little thing to steal.",
        ),
        "hurt": (
            f"Careful with that. It is one of mine.",
            f"That is not stock. It matters to me.",
            f"I notice when that moves. Put it down.",
            f"Some things are small and still not spare.",
        ),
        "startled": (
            f"Hey, wait. That is mine.",
            f"Hold up. Why are you taking that?",
            f"That does not leave with you.",
            f"Stop. I keep that for a reason.",
        ),
        "guarded": (
            f"You do not know what that is. Leave it.",
            f"That piece stays where I can see it.",
            f"Do not make me explain why I keep that.",
            f"Set it back and we can both keep this small.",
        ),
        "weary": (
            f"Not that too. Put it back.",
            f"I am tired of losing small things. Leave it.",
            f"That one has survived enough. Do not add yourself to it.",
            f"Just set it down. Please.",
        ),
        "protective": (
            f"Back off from that.",
            f"That is mine to keep, not yours to test.",
            f"You are not taking that from me.",
            f"Move your hand away from my {item_name}.",
        ),
    }
    tone = rng.choice(tuple(banks))
    quote = rng.choice(banks[tone])
    nearby = f"Someone nearby reacts sharply as you take {item_name}."
    other_floor = f"Someone on another floor reacts sharply as you take {item_name}."
    return {"quote": quote, "nearby_audio": nearby, "other_floor_audio": other_floor, "tone": tone}


def _npc_relevant_to_property(sim: Any, npc_eid: Any, property_id: str) -> bool:
    property_id = _text(property_id)
    if not property_id:
        return False
    try:
        npc_eid = int(npc_eid)
    except (TypeError, ValueError):
        return False
    occupation = sim.ecs.get(Occupation).get(npc_eid)
    workplace = getattr(occupation, "workplace", None)
    if isinstance(workplace, Mapping) and _text(workplace.get("property_id")) == property_id:
        return True
    routine = sim.ecs.get(NPCRoutine).get(npc_eid)
    for point in (getattr(routine, "home", None), getattr(routine, "work", None)):
        if isinstance(point, (tuple, list)) and len(point) >= 3:
            try:
                prop = sim.property_covering(int(point[0]), int(point[1]), int(point[2]))
            except Exception:
                prop = None
            if isinstance(prop, Mapping) and _text(prop.get("id")) == property_id:
                return True
    settlement = sim.ecs.get(NPCSettlement).get(npc_eid)
    if settlement is not None and property_id in {
        _text(getattr(settlement, "home_property_id", "")),
        _text(getattr(settlement, "work_property_id", "")),
    }:
        return True
    return False


def meaningful_object_dialogue_context(sim: Any, npc_eid: Any, *, viewer_eid: Any = None) -> dict[str, Any]:
    """Return learned object context this NPC may talk about."""

    state = meaningful_objects_state(sim)
    viewer_key = str(viewer_eid if viewer_eid is not None else getattr(sim, "player_eid", "player"))
    knowledge = state["player_knowledge"].get(viewer_key)
    if not isinstance(knowledge, dict):
        return {"available": False}
    try:
        npc_eid_int = int(npc_eid)
    except (TypeError, ValueError):
        npc_eid_int = npc_eid
    candidates = []
    for object_id, learned in tuple(knowledge.items()):
        entry = meaningful_object_entry(sim, object_id)
        if not entry:
            continue
        source_kind = _text(entry.get("source_kind"))
        relation = ""
        priority = 99
        if source_kind == "actor":
            try:
                if int(entry.get("owner_eid")) == int(npc_eid_int):
                    relation = "owner"
                    priority = 0
            except (TypeError, ValueError):
                relation = ""
        elif source_kind == "place" and _npc_relevant_to_property(sim, npc_eid_int, _text(entry.get("source_property_id"))):
            relation = "place_stakeholder"
            priority = 1
        if not relation:
            continue
        learned_tick = _safe_int((learned or {}).get("learned_tick"), 0) if isinstance(learned, Mapping) else 0
        summary = meaningful_object_entry_summary(sim, entry.get("object_id"), viewer_eid=viewer_eid)
        candidates.append((priority, -learned_tick, summary, relation, learned))
    if not candidates:
        return {"available": False}
    candidates.sort(key=lambda row: (row[0], row[1], row[2].get("object_id", "")))
    _priority, _neg_tick, summary, relation, learned = candidates[0]
    source = _text((learned or {}).get("source"), "learned") if isinstance(learned, Mapping) else "learned"
    dialogue_key = f"{npc_eid_int}:{summary.get('object_id')}"
    return {
        "available": True,
        "relation": relation,
        "source": source,
        "dialogue_key": dialogue_key,
        **summary,
    }


def meaningful_object_owner_dialogue_reveal(
    sim: Any,
    owner_eid: Any,
    *,
    viewer_eid: Any = None,
    source: str = "owner_dialogue",
) -> dict[str, Any] | None:
    """Reveal an existing owner object through a legitimate owner dialogue path."""

    entry = ensure_actor_personal_object(sim, owner_eid, create=False)
    if not entry:
        return None
    object_id = _text(entry.get("object_id"))
    if object_meaning_learned(sim, object_id, viewer_eid=viewer_eid):
        return None
    learned = learn_meaningful_object(sim, object_id, viewer_eid=viewer_eid, source=source, witness_eid=owner_eid)
    if not learned:
        return None
    return meaningful_object_entry_summary(sim, object_id, viewer_eid=viewer_eid)


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
    witness = _credible_pickup_witness(sim, owner_eid, x, y, z, actor_eid=actor_eid, observation=observation)
    witnessed_by_owner = bool(witness and witness.get("witness_relation") == "owner")
    witnessed_by_relevant_actor = bool(witness)
    if witnessed_by_relevant_actor and object_id:
        witness_eid = witness.get("witness_eid")
        witness_relation = _text(witness.get("witness_relation"), "owner")
        learn_meaningful_object(
            sim,
            object_id,
            viewer_eid=getattr(sim, "player_eid", actor_eid),
            source="owner_reaction" if witness_relation == "owner" else "protective_witness",
            witness_eid=witness_eid,
        )
        owner_name = _entity_display_name(sim, owner_eid, title_case=True)
        cooldown_key = f"{object_id}:{actor_eid}:{witness_eid}"
        if meaningful_object_cooldown_ready(sim, "owner_reactions", cooldown_key, cooldown_ticks=45, mark=True):
            sim.emit(Event(
                "meaningful_object_owner_reaction",
                eid=witness_eid,
                witness_eid=witness_eid,
                witness_relation=witness_relation,
                owner_eid=owner_eid,
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
        if witness_eid is not None and str(witness_eid) != str(owner_eid):
            witness_memory = sim.ecs.get(NPCMemory).get(witness_eid)
            if witness_memory is not None:
                witness_memory.remember(
                    int(getattr(sim, "tick", 0) or 0),
                    "personal_object_theft_witnessed",
                    strength=0.72,
                    offender_eid=actor_eid,
                    owner_eid=owner_eid,
                    object_id=object_id,
                    item_name=item_name,
                )
    return {
        **result,
        "object_id": object_id,
        "theft": True,
        "witnessed_by_owner": bool(witnessed_by_owner),
        "witnessed_by_relevant_actor": bool(witnessed_by_relevant_actor),
        "witness_eid": witness.get("witness_eid") if witness else None,
        "witness_relation": _text(witness.get("witness_relation")) if witness else "",
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
            "mood_anchor": _text(entry.get("meaning_kind")),
            "label_hidden": True,
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
    facilitator = source_payload.get("facilitator_context")
    facilitator = facilitator if isinstance(facilitator, Mapping) else {}
    facilitator_text = " ".join(
        _text(value).lower()
        for value in (
            facilitator.get("role"),
            facilitator.get("role_id"),
            facilitator.get("career"),
            facilitator.get("domain"),
            facilitator.get("archetype"),
            facilitator.get("service"),
            " ".join(str(tag) for tag in facilitator.get("style_tags", ()) if str(tag).strip())
            if isinstance(facilitator.get("style_tags"), (list, tuple, set)) else "",
        )
        if _text(value)
    )
    seed = _stable_seed(
        "reward-object-profile",
        reward_id,
        source_payload.get("seed"),
        source_payload.get("objective"),
        source_payload.get("outcome"),
        family_hint,
        facilitator,
    )
    rng = random.Random(seed)
    facilitator_family = ""
    if any(word in facilitator_text for word in ("medic", "doctor", "herbal", "clinic", "remedy")):
        facilitator_family = "medical_herbal"
    elif any(word in facilitator_text for word in ("courier", "driver", "mechanic", "repair", "worker")):
        facilitator_family = "tools_parts"
    elif any(word in facilitator_text for word in ("clerk", "merchant", "dealer", "counter", "market")):
        facilitator_family = "trade_work"
    elif any(word in facilitator_text for word in ("guard", "security", "justice", "watch")):
        facilitator_family = "tokens_charms"
    elif any(word in facilitator_text for word in ("garden", "forager", "ranger", "hunter", "flora")):
        facilitator_family = "nature_finds"
    if facilitator_family in OBJECT_PROFILE_FAMILIES:
        family = facilitator_family
    elif family_hint in OBJECT_PROFILE_FAMILIES:
        family = family_hint
    else:
        family = rng.choice(
            ("tokens_charms", "paper_books", "tools_parts", "personal_home", "nature_finds", "medical_herbal", "light_ritual")
        )
    profile = _profile_with_display(seed, family)
    profile["rarity"] = "unique"
    profile["future_tags"] = tuple(sorted(set(profile.get("future_tags", ())) | {"run_reward", "keepsake"}))
    return profile
