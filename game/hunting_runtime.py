"""Shared hunting, carcass, and meat-preparation helpers."""

from __future__ import annotations

import copy
from typing import Iterable

from engine.events import Event
from engine.systems import System
from game.components import AnimalGenome, AnimalPhysicalProfile, CreatureIdentity, EcologyProfile, Inventory, PlayerAssets, Position
from game.civic_records import civic_license_is_active, civic_license_record
from game.ecology_registry import fauna_cull_active_for_run, fauna_population_snapshot
from game.fauna_genetics import animal_genome_payload
from game.items import ITEM_CATALOG, item_display_name
from game.system_support.awareness_runtime import observation_payload_for_position
from game.system_support.offense_runtime import _emit_action_offense_event
from game.system_support.interaction_ordering import _manhattan


RAW_MEAT_ITEM_ID = "raw_game_meat"
BAGGED_MEAT_ITEM_ID = "bagged_game_meat"
COOKED_MEAT_ITEM_ID = "cooked_game_meat"
PACKAGED_MEAT_ITEM_ID = "packaged_game_meat"
KILL_BAG_ITEM_ID = "kill_bag"
FIELD_KNIFE_ITEM_ID = "field_knife"

FIELD_DRESSING_TOOL_TAGS = {"knife", "blade"}
REDUCED_FIELD_DRESSING_TOOL_IDS = {"pocket_multitool"}
DIRECT_FIELD_DRESSING_TOOL_IDS = {FIELD_KNIFE_ITEM_ID, "trail_machete", "shiv_knife"}

SIZE_CLASS_ORDER = ("tiny", "small", "medium", "large", "huge")
BASE_MEAT_UNITS_BY_SIZE = {
    "tiny": 0,
    "small": 1,
    "medium": 2,
    "large": 4,
    "huge": 6,
}
HUNTABLE_SPECIES = {
    "deer",
    "boar",
    "feral_boar",
    "wild_hog",
    "black_bear",
    "bear",
    "cougar",
    "mountain_lion",
    "wolf",
    "gray_wolf",
    "coyote",
    "alligator",
}
HUNTABLE_TAXONOMY = {"ungulate"}
MEAT_INPUT_ITEM_IDS = {RAW_MEAT_ITEM_ID, BAGGED_MEAT_ITEM_ID}
COOKABLE_MEAT_ITEM_IDS = {RAW_MEAT_ITEM_ID, BAGGED_MEAT_ITEM_ID}


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


def _slug(value):
    return str(value or "").strip().lower().replace(" ", "_").replace("-", "_")


def animal_size_class_for_score(score, juvenile=False):
    """Return the coarse animal size class used by hunting and presentation."""
    score = _safe_float(score, 0.0)
    if score < 12.0:
        size_class = "tiny"
    elif score < 35.0:
        size_class = "small"
    elif score < 55.0:
        size_class = "medium"
    elif score < 80.0:
        size_class = "large"
    else:
        size_class = "huge"
    if juvenile:
        idx = max(0, SIZE_CLASS_ORDER.index(size_class) - 1)
        size_class = SIZE_CLASS_ORDER[idx]
    return size_class


def _animal_identity_payload(sim, animal_eid):
    identities = sim.ecs.get(CreatureIdentity)
    physicals = sim.ecs.get(AnimalPhysicalProfile)
    ecologies = sim.ecs.get(EcologyProfile)
    genomes = sim.ecs.get(AnimalGenome)
    identity = identities.get(animal_eid)
    physical = physicals.get(animal_eid)
    ecology = ecologies.get(animal_eid)
    genome = genomes.get(animal_eid)
    payload = {}
    if identity:
        payload.update({
            "creature_type": str(getattr(identity, "creature_type", "") or "").strip().lower(),
            "taxonomy_class": str(getattr(identity, "taxonomy_class", "") or "").strip().lower(),
            "species": str(getattr(identity, "species", "") or "").strip().lower(),
            "common_name": str(getattr(identity, "common_name", "") or "").strip(),
            "display_name": str(identity.display_name() or "").strip(),
        })
    if physical:
        payload.update({
            "size_score": float(getattr(physical, "size_score", 0.0) or 0.0),
            "juvenile": bool(getattr(physical, "juvenile", False)),
        })
    if ecology:
        payload["ecology_species"] = str(getattr(ecology, "species", "") or "").strip().lower()
    if genome:
        payload["fauna_genetics"] = animal_genome_payload(genome)
        payload["root_animal_id"] = str(getattr(genome, "root_animal_id", "") or "").strip().lower()
        payload["fauna_lineage_id"] = str(getattr(genome, "lineage_id", "") or "").strip().lower()
    return payload


def _payload_species_tokens(payload):
    tokens = set()
    for key in ("ecology_species", "common_name", "species", "display_name"):
        raw = payload.get(key)
        if raw:
            tokens.add(_slug(raw))
    species = str(payload.get("species", "") or "")
    if species:
        bits = species.replace("_", " ").split()
        if bits:
            tokens.add(_slug(bits[-1]))
    return {token for token in tokens if token}


def _payload_huntable(payload):
    creature_type = str(payload.get("creature_type", "") or "").strip().lower()
    if creature_type and creature_type != "animal":
        return False
    size_class = animal_size_class_for_score(payload.get("size_score", 0.0), juvenile=bool(payload.get("juvenile", False)))
    if BASE_MEAT_UNITS_BY_SIZE.get(size_class, 0) <= 0:
        return False
    taxonomy = str(payload.get("taxonomy_class", "") or "").strip().lower()
    if str(payload.get("root_animal_id", "") or "").strip():
        return True
    if taxonomy in HUNTABLE_TAXONOMY:
        return True
    return bool(_payload_species_tokens(payload).intersection(HUNTABLE_SPECIES))


def hunting_yield_profile(sim, animal_eid=None, *, payload=None):
    payload = dict(payload or (_animal_identity_payload(sim, animal_eid) if animal_eid is not None else {}))
    if not _payload_huntable(payload):
        return None
    size_class = animal_size_class_for_score(payload.get("size_score", 0.0), juvenile=bool(payload.get("juvenile", False)))
    base_units = int(BASE_MEAT_UNITS_BY_SIZE.get(size_class, 0))
    if base_units <= 0:
        return None
    species_label = (
        str(payload.get("common_name", "") or "").strip()
        or str(payload.get("display_name", "") or "").strip()
        or str(payload.get("ecology_species", "") or "").replace("_", " ").strip()
        or "wildlife"
    )
    return {
        "animal_size_class": size_class,
        "base_units": base_units,
        "species_label": species_label,
        "species_key": sorted(_payload_species_tokens(payload))[0] if _payload_species_tokens(payload) else "wildlife",
        "taxonomy_class": str(payload.get("taxonomy_class", "") or "").strip().lower() or "other",
        "size_score": float(_safe_float(payload.get("size_score", 0.0), 0.0)),
        "juvenile": bool(payload.get("juvenile", False)),
        "root_animal_id": str(payload.get("root_animal_id", "") or "").strip().lower(),
        "fauna_lineage_id": str(payload.get("fauna_lineage_id", "") or "").strip().lower(),
        "fauna_genetics": copy.deepcopy(dict(payload.get("fauna_genetics") or {})),
    }


def hunting_legality_snapshot(sim, actor_eid, animal_eid=None, *, payload=None, x=None, y=None, z=0):
    """Resolve contextual hunting permission without creating an offense."""

    profile = hunting_yield_profile(sim, animal_eid=animal_eid, payload=payload)
    if profile is None:
        return {
            "legal": True,
            "reason": "not_regulated_game",
            "context": "wildlife_encounter",
            "offense_score": 0,
            "permit_verified": False,
            "license_status": "not_applicable",
            "inspection_grade": "not_applicable",
            "population_status": "unmanaged",
            "population_abundance": 100,
            "ecology_value_multiplier": 1.0,
        }
    license_record = civic_license_record(sim, actor_eid, "hunting") if actor_eid is not None else None
    license_status = str((license_record or {}).get("status", "unlicensed") or "unlicensed").strip().lower()
    permit_verified = civic_license_is_active(sim, actor_eid, "hunting") if actor_eid is not None else False
    native_id = str(profile.get("fauna_lineage_id", "") or "").strip().lower()
    population = fauna_population_snapshot(sim, native_id)
    cull_active = bool(native_id and fauna_cull_active_for_run(sim, native_id))

    if x is None or y is None:
        pos = sim.ecs.get(Position).get(animal_eid) if animal_eid is not None else None
        if pos is not None:
            x, y, z = int(pos.x), int(pos.y), int(pos.z)
    area_type = "unknown"
    if x is not None and y is not None and getattr(sim, "world", None) is not None:
        try:
            cx, cy = sim.chunk_coords(int(x), int(y))
            area_type = str(sim.world.overworld_descriptor(cx, cy).get("area_type", "unknown") or "unknown").strip().lower()
        except Exception:
            area_type = "unknown"
    property_id = None
    if x is not None and y is not None and hasattr(sim, "property_covering"):
        try:
            property_id = (sim.property_covering(int(x), int(y), int(z)) or {}).get("id")
        except (TypeError, ValueError):
            property_id = None

    population_status = str(population.get("status", "unmanaged") or "unmanaged").strip().lower()
    protected_without_order = population_status in {"endangered", "protected", "extinct"} and not cull_active
    unsafe_area = bool(property_id) or area_type == "city"
    if protected_without_order:
        legal = False
        reason = "protected_line"
        context = "protected_wildlife_hunting"
        score = 64 if population_status in {"protected", "extinct"} else 42
        inspection_grade = "suspicious"
    elif unsafe_area:
        legal = False
        reason = "unsafe_area"
        context = "unsafe_hunting"
        score = 34
        inspection_grade = "suspicious"
    elif not permit_verified:
        legal = False
        reason = "license_required"
        context = "unlicensed_hunting"
        score = 24
        inspection_grade = "uncertified"
    else:
        legal = True
        reason = "active_cull" if cull_active else "licensed_game"
        context = "wildlife_hunting"
        score = 0
        inspection_grade = "clean"
    return {
        "legal": bool(legal),
        "reason": reason,
        "context": context,
        "offense_score": int(score),
        "permit_verified": bool(permit_verified and legal),
        "license_status": license_status,
        "inspection_grade": inspection_grade,
        "fauna_lineage_id": native_id,
        "population_status": population_status,
        "population_abundance": int(population.get("abundance", 100) or 0),
        "ecology_value_multiplier": float(population.get("value_multiplier", 1.0) or 1.0),
        "cull_active": cull_active,
        "area_type": area_type,
        "property_id": property_id,
    }


def _hunting_state(sim):
    state = getattr(sim, "hunting_carcasses", None)
    if not isinstance(state, dict):
        state = {}
        sim.hunting_carcasses = state
    if not hasattr(sim, "next_hunting_carcass_id"):
        sim.next_hunting_carcass_id = 1
    return state


def _new_carcass_id(sim):
    try:
        next_id = int(getattr(sim, "next_hunting_carcass_id", 1))
    except (TypeError, ValueError):
        next_id = 1
    sim.next_hunting_carcass_id = next_id + 1
    return f"carcass-{next_id}"


def create_hunting_carcass(sim, *, animal_eid=None, x=0, y=0, z=0, source_eid=None, payload=None):
    profile = hunting_yield_profile(sim, animal_eid=animal_eid, payload=payload)
    if not profile:
        return None
    legality = hunting_legality_snapshot(
        sim,
        source_eid,
        animal_eid=animal_eid,
        payload=payload,
        x=x,
        y=y,
        z=z,
    )
    state = _hunting_state(sim)
    carcass_id = _new_carcass_id(sim)
    record = {
        "carcass_id": carcass_id,
        "animal_eid": animal_eid,
        "animal_name": str((payload or {}).get("target_name", "") or profile.get("species_label") or "wildlife").strip(),
        "species_label": profile["species_label"],
        "species_key": profile["species_key"],
        "taxonomy_class": profile["taxonomy_class"],
        "size_score": profile["size_score"],
        "animal_size_class": profile["animal_size_class"],
        "base_units": int(profile["base_units"]),
        "root_animal_id": profile.get("root_animal_id"),
        "fauna_lineage_id": profile.get("fauna_lineage_id"),
        "fauna_genetics": copy.deepcopy(dict(profile.get("fauna_genetics") or {})),
        "x": int(x),
        "y": int(y),
        "z": int(z),
        "source_eid": source_eid,
        "created_tick": _safe_int(getattr(sim, "tick", 0), 0),
        "hunt_legality": copy.deepcopy(dict(legality)),
        "harvested": False,
    }
    state[carcass_id] = record
    sim.emit(Event("hunting_carcass_created", **record))
    return record


def hunting_carcasses_at(sim, x, y, z=0, *, include_harvested=False):
    state = _hunting_state(sim)
    rows = []
    for record in state.values():
        if not include_harvested and bool(record.get("harvested")):
            continue
        if int(record.get("x", 0)) == int(x) and int(record.get("y", 0)) == int(y) and int(record.get("z", 0)) == int(z):
            rows.append(record)
    return sorted(rows, key=lambda row: str(row.get("carcass_id", "")))


def nearest_hunting_carcass(sim, x, y, z=0, *, radius=1, preferred_dir=None, exact_direction=False):
    state = _hunting_state(sim)
    candidates = []
    target = None
    if exact_direction and isinstance(preferred_dir, tuple) and len(preferred_dir) >= 2:
        dx = _safe_int(preferred_dir[0], 0)
        dy = _safe_int(preferred_dir[1], 0)
        if dx or dy:
            target = (int(x) + dx, int(y) + dy, int(z))
    for record in state.values():
        if bool(record.get("harvested")):
            continue
        rx, ry, rz = int(record.get("x", 0)), int(record.get("y", 0)), int(record.get("z", 0))
        if int(rz) != int(z):
            continue
        if target is not None and (rx, ry, rz) != target:
            continue
        if target is not None:
            dist = max(abs(int(x) - rx), abs(int(y) - ry))
        else:
            dist = _manhattan(int(x), int(y), rx, ry)
        if dist > int(radius):
            continue
        candidates.append((dist, str(record.get("carcass_id", "")), record))
    if not candidates:
        return None
    candidates.sort(key=lambda row: (row[0], row[1]))
    return candidates[0][2]


def hunting_carcass_look_text(record):
    if not isinstance(record, dict) or bool(record.get("harvested")):
        return ""
    size_class = str(record.get("animal_size_class", "") or "animal").replace("_", " ")
    species = str(record.get("species_label", "") or record.get("animal_name", "") or "wildlife").strip()
    units = int(record.get("base_units", 0) or 0)
    claim_note = "; hunter claim" if record.get("claimed_by_event_id") else ""
    if units <= 0:
        return f"carcass:{size_class} {species}{claim_note}; no usable cuts"
    return f"carcass:{size_class} {species}{claim_note}; field dress with a blade, about {units} meat"


def _inventory_for(sim, eid):
    return sim.ecs.get(Inventory).get(eid)


def _entry_tags(item_id):
    item = ITEM_CATALOG.get(str(item_id or "").strip().lower(), {})
    return {str(tag).strip().lower() for tag in tuple(item.get("tags", ()) or ()) if str(tag).strip()}


def _field_dressing_tool(inventory):
    if not inventory:
        return None
    fallback = None
    for entry in tuple(getattr(inventory, "items", ()) or ()):
        item_id = str(entry.get("item_id", "") or "").strip().lower()
        tags = _entry_tags(item_id)
        if item_id in DIRECT_FIELD_DRESSING_TOOL_IDS or tags.intersection(FIELD_DRESSING_TOOL_TAGS):
            return {"item_id": item_id, "quality": 1.0}
        if item_id in REDUCED_FIELD_DRESSING_TOOL_IDS and fallback is None:
            fallback = {"item_id": item_id, "quality": 0.65}
    return fallback


def _has_kill_bag(inventory):
    if not inventory:
        return False
    return any(str(entry.get("item_id", "") or "").strip().lower() == KILL_BAG_ITEM_ID for entry in tuple(inventory.items or ()))


def _clone_inventory(inventory):
    clone = Inventory(capacity=getattr(inventory, "capacity", 10))
    clone.items = copy.deepcopy(list(getattr(inventory, "items", ()) or ()))
    return clone


def _inventory_owner_for(sim, eid):
    if eid == getattr(sim, "player_eid", None):
        return eid, "player"
    return eid, "npc"


def _emit_claimed_carcass_take_events(sim, eid, record, *, output_item_id, output_item_name, quantity):
    if not isinstance(record, dict) or not record.get("claimed_by_event_id"):
        return
    claimed_hunter = record.get("claimed_by_hunter_eid")
    try:
        if claimed_hunter is not None and int(claimed_hunter) == int(eid):
            return
    except (TypeError, ValueError):
        pass

    x = _safe_int(record.get("x"), 0)
    y = _safe_int(record.get("y"), 0)
    z = _safe_int(record.get("z"), 0)
    observation = observation_payload_for_position(
        sim,
        x,
        y,
        z,
        exclude_eid=eid,
        offender_eid=eid,
        observation_channels=("actor_witness",),
    )
    property_id = str(record.get("claimed_property_id", "") or "").strip() or None
    property_name = str(record.get("claim_label", "") or "hunter claim").strip() or "hunter claim"
    sim.emit(Event(
        "item_stolen",
        offender_eid=eid,
        item_id=output_item_id,
        item_name=output_item_name,
        quantity=max(1, int(quantity)),
        owner_eid=claimed_hunter,
        owner_tag=str(record.get("claimed_by_org", "") or "hunter_party").strip() or "hunter_party",
        property_id=property_id,
        property_name=property_name,
        x=x,
        y=y,
        z=z,
        source_context="claimed_hunting_carcass",
        **observation,
    ))
    _emit_action_offense_event(
        sim,
        eid,
        "pickup_item",
        x,
        y,
        z,
        context="item_theft",
        item_id=output_item_id,
        item_name=output_item_name,
        property_id=property_id,
        property_name=property_name,
        source_context="claimed_hunting_carcass",
        **observation,
    )


def _inventory_can_accept(inventory, item_id, quantity, *, metadata=None, owner_eid=None, owner_tag=None):
    if not inventory:
        return False
    item_def = ITEM_CATALOG.get(str(item_id or "").strip().lower(), {})
    clone = _clone_inventory(inventory)
    added, _instance_id = clone.add_item(
        item_id,
        quantity=max(1, int(quantity)),
        stack_max=max(1, int(item_def.get("stack_max", 1) or 1)),
        owner_eid=owner_eid,
        owner_tag=owner_tag,
        metadata=metadata or {},
    )
    return bool(added)


def _add_inventory_item(sim, inventory, item_id, quantity, *, metadata=None, owner_eid=None, owner_tag=None):
    item_def = ITEM_CATALOG.get(str(item_id or "").strip().lower(), {})
    return inventory.add_item(
        item_id,
        quantity=max(1, int(quantity)),
        stack_max=max(1, int(item_def.get("stack_max", 1) or 1)),
        instance_factory=sim.new_item_instance_id,
        owner_eid=owner_eid,
        owner_tag=owner_tag,
        metadata=metadata or {},
    )


def field_dress_carcass(sim, eid, carcass_id=None):
    inventory = _inventory_for(sim, eid)
    if not inventory:
        sim.emit(Event("hunting_carcass_blocked", eid=eid, carcass_id=carcass_id, reason="no_inventory"))
        return False
    state = _hunting_state(sim)
    record = state.get(str(carcass_id or "").strip())
    if not record or bool(record.get("harvested")):
        sim.emit(Event("hunting_carcass_blocked", eid=eid, carcass_id=carcass_id, reason="unavailable"))
        return False
    tool = _field_dressing_tool(inventory)
    if not tool:
        sim.emit(Event("hunting_carcass_blocked", eid=eid, carcass_id=record.get("carcass_id"), reason="no_tool", animal_name=record.get("animal_name")))
        return False
    base_units = max(0, int(record.get("base_units", 0) or 0))
    if base_units <= 0:
        sim.emit(Event("hunting_carcass_blocked", eid=eid, carcass_id=record.get("carcass_id"), reason="no_usable_meat", animal_name=record.get("animal_name")))
        return False
    quality = float(tool.get("quality", 1.0) or 1.0)
    quantity = max(1, int(base_units if quality >= 0.95 else round(base_units * 0.65)))
    kill_bag = _has_kill_bag(inventory)
    if kill_bag and base_units >= 2:
        quantity += 1
    output_item_id = BAGGED_MEAT_ITEM_ID if kill_bag else RAW_MEAT_ITEM_ID
    hunt_legality = record.get("hunt_legality") if isinstance(record.get("hunt_legality"), dict) else {}
    inspection_grade = str(hunt_legality.get("inspection_grade", "uncertified") or "uncertified").strip().lower()
    permit_verified = bool(hunt_legality.get("permit_verified", False))
    legal_status = "legal" if inspection_grade == "clean" else "illegal" if inspection_grade == "suspicious" else "restricted"
    metadata = {
        "source": "hunting",
        "source_context": "field_dressed",
        "animal_name": record.get("animal_name"),
        "animal_species": record.get("species_label"),
        "animal_size_class": record.get("animal_size_class"),
        "field_dressed_tick": _safe_int(getattr(sim, "tick", 0), 0),
        "field_dressing_tool": tool.get("item_id"),
        "kill_bag_used": bool(kill_bag),
        "hunter_eid": record.get("source_eid"),
        "permit_verified": permit_verified,
        "hunting_license_status": hunt_legality.get("license_status", "unlicensed"),
        "inspection_grade": inspection_grade,
        "legal_status": legal_status,
        "hunting_legality_reason": hunt_legality.get("reason", "unknown"),
        "hunting_context": hunt_legality.get("context", "unlicensed_hunting"),
        "source_fauna_population_status": hunt_legality.get("population_status", "unmanaged"),
        "source_fauna_abundance": int(hunt_legality.get("population_abundance", 100) or 0),
        "ecology_value_multiplier": float(hunt_legality.get("ecology_value_multiplier", 1.0) or 1.0),
        "cull_active_at_hunt": bool(hunt_legality.get("cull_active", False)),
        "source_fauna_root_animal_id": record.get("root_animal_id"),
        "source_fauna_lineage_id": record.get("fauna_lineage_id"),
        "source_fauna_genetics": copy.deepcopy(dict(record.get("fauna_genetics") or {})),
    }
    owner_eid, owner_tag = _inventory_owner_for(sim, eid)
    if not _inventory_can_accept(inventory, output_item_id, quantity, metadata=metadata, owner_eid=owner_eid, owner_tag=owner_tag):
        sim.emit(Event(
            "hunting_carcass_blocked",
            eid=eid,
            carcass_id=record.get("carcass_id"),
            animal_name=record.get("animal_name"),
            reason="inventory_full",
            output_item_id=output_item_id,
            quantity=quantity,
        ))
        return False
    added, _instance_id = _add_inventory_item(sim, inventory, output_item_id, quantity, metadata=metadata, owner_eid=owner_eid, owner_tag=owner_tag)
    if not added:
        sim.emit(Event("hunting_carcass_blocked", eid=eid, carcass_id=record.get("carcass_id"), reason="inventory_full"))
        return False
    record["harvested"] = True
    record["harvested_tick"] = _safe_int(getattr(sim, "tick", 0), 0)
    record["harvested_by_eid"] = eid
    record["output_item_id"] = output_item_id
    record["output_quantity"] = int(quantity)
    output_item_name = item_display_name(output_item_id, metadata=metadata, item_catalog=ITEM_CATALOG)
    _emit_claimed_carcass_take_events(
        sim,
        eid,
        record,
        output_item_id=output_item_id,
        output_item_name=output_item_name,
        quantity=int(quantity),
    )
    sim.emit(Event(
        "hunting_carcass_harvested",
        eid=eid,
        carcass_id=record.get("carcass_id"),
        animal_name=record.get("animal_name"),
        species_label=record.get("species_label"),
        animal_size_class=record.get("animal_size_class"),
        output_item_id=output_item_id,
        output_item_name=output_item_name,
        quantity=int(quantity),
        tool_item_id=tool.get("item_id"),
        kill_bag_used=bool(kill_bag),
        permit_verified=permit_verified,
        inspection_grade=inspection_grade,
        hunting_legality_reason=hunt_legality.get("reason", "unknown"),
    ))
    return True


def _eligible_meat_entries(inventory, allowed_item_ids: Iterable[str]):
    allowed = {str(item_id or "").strip().lower() for item_id in allowed_item_ids}
    rows = []
    if not inventory:
        return rows
    for entry in tuple(getattr(inventory, "items", ()) or ()):
        item_id = str(entry.get("item_id", "") or "").strip().lower()
        if item_id in allowed:
            rows.append(entry)
    return rows


def _meat_provenance_signature(entry):
    metadata = entry.get("metadata") if isinstance((entry or {}).get("metadata"), dict) else {}
    return (
        bool(metadata.get("permit_verified", False)),
        str(metadata.get("inspection_grade", "uncertified") or "uncertified").strip().lower(),
        str(metadata.get("legal_status", "restricted") or "restricted").strip().lower(),
        _safe_int(metadata.get("hunter_eid"), -1),
        str(metadata.get("animal_species", "") or "").strip().lower(),
        str(metadata.get("source_fauna_lineage_id", "") or "").strip().lower(),
        str(metadata.get("source_fauna_population_status", "unmanaged") or "unmanaged").strip().lower(),
        _safe_int(metadata.get("source_fauna_abundance"), 100),
        float(metadata.get("ecology_value_multiplier", 1.0) or 1.0),
        bool(metadata.get("cull_active_at_hunt", False)),
    )


def _matching_meat_provenance(entries, source_entry):
    signature = _meat_provenance_signature(source_entry)
    return [entry for entry in entries if _meat_provenance_signature(entry) == signature]


def _remove_meat_quantity(inventory, entries, quantity):
    remaining = max(0, int(quantity))
    removed = 0
    for entry in list(entries):
        if remaining <= 0:
            break
        amount = min(remaining, max(0, int(entry.get("quantity", 1) or 1)))
        if amount <= 0:
            continue
        removed_entry = inventory.remove_item(instance_id=entry.get("instance_id"), quantity=amount)
        if removed_entry:
            removed += int(removed_entry.get("quantity", amount) or amount)
            remaining -= int(removed_entry.get("quantity", amount) or amount)
    return removed


def _clone_after_removing(inventory, entries, quantity):
    clone = _clone_inventory(inventory)
    clone_entries_by_instance = {
        str(entry.get("instance_id", "")): entry
        for entry in tuple(getattr(clone, "items", ()) or ())
    }
    remaining = max(0, int(quantity))
    for entry in entries:
        if remaining <= 0:
            break
        iid = str(entry.get("instance_id", ""))
        clone_entry = clone_entries_by_instance.get(iid)
        if not clone_entry:
            continue
        amount = min(remaining, max(0, int(clone_entry.get("quantity", 1) or 1)))
        if amount <= 0:
            continue
        clone.remove_item(instance_id=clone_entry.get("instance_id"), quantity=amount)
        remaining -= amount
    return clone


def convert_meat_stack(sim, eid, mode, *, max_units=None):
    mode = str(mode or "").strip().lower()
    inventory = _inventory_for(sim, eid)
    if not inventory:
        return {"ok": False, "reason": "no_inventory"}
    if mode == "campfire_cook":
        available_entries = _eligible_meat_entries(inventory, COOKABLE_MEAT_ITEM_IDS)
        if not available_entries:
            return {"ok": False, "reason": "no_meat"}
        entries = _matching_meat_provenance(available_entries, available_entries[0])
        input_units = sum(max(0, int(entry.get("quantity", 1) or 1)) for entry in entries)
        if max_units is not None:
            input_units = min(input_units, max(1, int(max_units)))
        output_units = max(1, int(round(float(input_units) * 0.65)))
        output_item_id = COOKED_MEAT_ITEM_ID
        credits_spent = 0
    elif mode == "butcher_prepare":
        available_entries = _eligible_meat_entries(inventory, MEAT_INPUT_ITEM_IDS)
        if not available_entries:
            return {"ok": False, "reason": "no_meat"}
        eligible_entries = []
        refused = []
        for entry in available_entries:
            metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
            if not bool(metadata.get("permit_verified")) or str(metadata.get("inspection_grade", "uncertified") or "uncertified").strip().lower() != "clean":
                refused.append(entry)
            else:
                eligible_entries.append(entry)
        if not eligible_entries:
            refused_meta = refused[0].get("metadata") if isinstance(refused[0].get("metadata"), dict) else {}
            return {
                "ok": False,
                "reason": "uncertified_meat",
                "inspection_grade": str(refused_meta.get("inspection_grade", "uncertified") or "uncertified").strip().lower(),
                "animal_name": refused_meta.get("animal_name") or refused_meta.get("animal_species"),
            }
        entries = _matching_meat_provenance(eligible_entries, eligible_entries[0])
        total_units = sum(max(0, int(entry.get("quantity", 1) or 1)) for entry in entries)
        assets = sim.ecs.get(PlayerAssets).get(eid)
        credits = max(0, int(getattr(assets, "credits", 0) if assets else 0))
        fee_per_unit = 3
        affordable_units = credits // fee_per_unit
        input_units = min(total_units, affordable_units)
        if max_units is not None:
            input_units = min(input_units, max(1, int(max_units)))
        if input_units <= 0:
            return {"ok": False, "reason": "no_credits", "cost": min(total_units, 1) * fee_per_unit, "credits": credits}
        output_units = int(input_units)
        output_item_id = PACKAGED_MEAT_ITEM_ID
        credits_spent = int(input_units) * fee_per_unit
    else:
        return {"ok": False, "reason": "unavailable"}
    if input_units <= 0 or output_units <= 0:
        return {"ok": False, "reason": "no_meat"}
    source_metadata = entries[0].get("metadata") if entries and isinstance(entries[0].get("metadata"), dict) else {}
    metadata = {
        "source": "hunting",
        "source_context": mode,
        "processed_tick": _safe_int(getattr(sim, "tick", 0), 0),
        "input_units": int(input_units),
        "legal_status": str(source_metadata.get("legal_status", "restricted") or "restricted").strip().lower(),
        "permit_verified": bool(source_metadata.get("permit_verified", False)),
        "inspection_grade": str(source_metadata.get("inspection_grade", "uncertified") or "uncertified").strip().lower(),
        "hunter_eid": source_metadata.get("hunter_eid"),
        "hunting_license_status": source_metadata.get("hunting_license_status"),
        "hunting_legality_reason": source_metadata.get("hunting_legality_reason"),
        "hunting_context": source_metadata.get("hunting_context"),
        "animal_name": source_metadata.get("animal_name"),
        "animal_species": source_metadata.get("animal_species"),
        "source_fauna_root_animal_id": source_metadata.get("source_fauna_root_animal_id"),
        "source_fauna_lineage_id": source_metadata.get("source_fauna_lineage_id"),
        "source_fauna_genetics": copy.deepcopy(dict(source_metadata.get("source_fauna_genetics") or {})),
        "source_fauna_population_status": source_metadata.get("source_fauna_population_status", "unmanaged"),
        "source_fauna_abundance": int(source_metadata.get("source_fauna_abundance", 100) or 0),
        "ecology_value_multiplier": float(source_metadata.get("ecology_value_multiplier", 1.0) or 1.0),
        "cull_active_at_hunt": bool(source_metadata.get("cull_active_at_hunt", False)),
    }
    owner_eid, owner_tag = _inventory_owner_for(sim, eid)
    clone = _clone_after_removing(inventory, entries, input_units)
    item_def = ITEM_CATALOG.get(output_item_id, {})
    clone_added, _clone_instance = clone.add_item(
        output_item_id,
        quantity=int(output_units),
        stack_max=max(1, int(item_def.get("stack_max", 1) or 1)),
        owner_eid=owner_eid,
        owner_tag=owner_tag,
        metadata=metadata,
    )
    if not clone_added:
        return {"ok": False, "reason": "inventory_full", "output_item_id": output_item_id, "quantity": int(output_units)}
    removed = _remove_meat_quantity(inventory, entries, input_units)
    if removed < input_units:
        return {"ok": False, "reason": "lost_input"}
    assets = sim.ecs.get(PlayerAssets).get(eid)
    if credits_spent and assets:
        assets.credits = max(0, int(getattr(assets, "credits", 0)) - int(credits_spent))
    added, _instance = _add_inventory_item(sim, inventory, output_item_id, output_units, metadata=metadata, owner_eid=owner_eid, owner_tag=owner_tag)
    if not added:
        return {"ok": False, "reason": "inventory_full", "output_item_id": output_item_id, "quantity": int(output_units)}
    return {
        "ok": True,
        "mode": mode,
        "input_units": int(input_units),
        "output_units": int(output_units),
        "output_item_id": output_item_id,
        "output_item_name": item_display_name(output_item_id, metadata=metadata, item_catalog=ITEM_CATALOG),
        "credits_spent": int(credits_spent),
    }


class HuntingCarcassSystem(System):
    """Creates saved carcass records from eligible wildlife death events."""

    def __init__(self, sim):
        super().__init__(sim)
        self.sim.events.subscribe("npc_killed", self.on_npc_killed)
        self.runs_without_turn = True

    def on_npc_killed(self, event):
        payload = dict(event.data.get("animal_payload", {}) or {})
        if not payload:
            return
        payload["target_name"] = event.data.get("target_name")
        create_hunting_carcass(
            self.sim,
            animal_eid=event.data.get("target_eid"),
            x=event.data.get("x", 0),
            y=event.data.get("y", 0),
            z=event.data.get("z", 0),
            source_eid=event.data.get("source_eid"),
            payload=payload,
        )


__all__ = [
    "BAGGED_MEAT_ITEM_ID",
    "COOKED_MEAT_ITEM_ID",
    "FIELD_KNIFE_ITEM_ID",
    "HuntingCarcassSystem",
    "KILL_BAG_ITEM_ID",
    "PACKAGED_MEAT_ITEM_ID",
    "RAW_MEAT_ITEM_ID",
    "animal_size_class_for_score",
    "convert_meat_stack",
    "create_hunting_carcass",
    "field_dress_carcass",
    "hunting_carcass_look_text",
    "hunting_carcasses_at",
    "hunting_legality_snapshot",
    "hunting_yield_profile",
    "nearest_hunting_carcass",
]
