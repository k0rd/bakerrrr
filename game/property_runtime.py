"""Shared property, vehicle, and controller runtime helpers.

This module holds the pure helper cluster that used to live inside
``game/systems.py`` so systems can share one focused seam without keeping the
main behavior file as a dumping ground for every property-adjacent utility.
"""

from game.components import Inventory, Position, PropertyKnowledge
from game.knowledge_notebook import note_property_notebook_mutation
from game.property_access import (
    controller_intrusion_access_for_actor as _controller_intrusion_access_for_actor,
    finance_services_for_property as _finance_services_for_property_base,
    property_access_controller as _property_access_controller,
    property_access_level as _property_access_level,
    property_apertures as _property_apertures,
    property_is_public as _property_is_public_base,
    property_is_storefront as _property_is_storefront_base,
    property_status_text as _property_status_text,
    site_services_for_property as _site_services_for_property_base,
    storefront_service_mode as _storefront_service_mode_base,
)
from game.property_keys import (
    inventory_matching_property_credential,
    inventory_matching_property_key,
    property_lock_state,
)


def _int_or_default(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _manhattan(x1, y1, x2, y2):
    return abs(int(x1) - int(x2)) + abs(int(y1) - int(y2))


def property_is_public(prop):
    return _property_is_public_base(prop)


def property_metadata(prop):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def resolve_property_record(sim, property_id, *, include_saved=True):
    if sim is None:
        return None
    clean_id = str(property_id or "").strip()
    if not clean_id:
        return None
    prop = getattr(sim, "properties", {}).get(clean_id)
    if isinstance(prop, dict):
        return prop
    if not include_saved:
        return None
    for snapshot in tuple(getattr(sim, "chunk_saved_states", {}).values()):
        if not isinstance(snapshot, dict):
            continue
        props = snapshot.get("properties")
        if not isinstance(props, dict):
            continue
        prop = props.get(clean_id)
        if isinstance(prop, dict):
            return prop
    for records in tuple(getattr(sim, "chunk_property_records", {}).values()):
        for row in tuple(records or ()):
            if isinstance(row, dict) and str(row.get("id", "")).strip() == clean_id:
                return row
    return None


def property_is_vehicle(prop):
    if not isinstance(prop, dict):
        return False
    return str(prop.get("kind", "")).strip().lower() == "vehicle"


def vehicle_profile_from_property(prop):
    metadata = property_metadata(prop)
    if not property_is_vehicle(prop):
        return {}
    durability = _int_or_default(metadata.get("durability"), 5)
    return {
        "make": str(metadata.get("vehicle_make", "Unknown")).strip() or "Unknown",
        "model": str(metadata.get("vehicle_model", "Vehicle")).strip() or "Vehicle",
        "vehicle_class": str(metadata.get("vehicle_class", "sedan")).strip().lower() or "sedan",
        "quality": str(metadata.get("vehicle_quality", "used")).strip().lower() or "used",
        "power": _int_or_default(metadata.get("power"), 5),
        "durability": durability,
        "fuel_efficiency": _int_or_default(metadata.get("fuel_efficiency"), 5),
        "fuel_capacity": _int_or_default(metadata.get("fuel_capacity"), 60),
        "fuel": _int_or_default(metadata.get("fuel"), _int_or_default(metadata.get("fuel_capacity"), 60)),
        "usable": bool(metadata.get("vehicle_usable", True)) and int(durability) > 0,
    }


def vehicle_label(prop):
    profile = vehicle_profile_from_property(prop)
    if not profile:
        return str(prop.get("name", "vehicle")).strip() or "vehicle"
    return f"{profile['make']} {profile['model']}"


def vehicle_fuel_values(prop):
    profile = vehicle_profile_from_property(prop)
    capacity = _int_or_default(profile.get("fuel_capacity"), 60)
    capacity = max(10, min(500, capacity))
    fuel = _int_or_default(profile.get("fuel"), capacity)
    fuel = max(0, min(capacity, fuel))
    return fuel, capacity


def controller_holder_for_actor(controller, actor_eid):
    if actor_eid is None or not isinstance(controller, dict):
        return None
    for holder in controller.get("authorized_holders", ()):
        if holder.get("eid") == actor_eid:
            return holder
    return None


def controller_credential_short_label(controller):
    mode = str(controller.get("credential_mode", "") or "").strip().lower()
    if mode == "badge":
        return "badge"
    if mode == "biometric":
        return "bio"
    return "key"


def controller_access_requirement_text(controller):
    mode = str(controller.get("credential_mode", "") or "").strip().lower()
    if mode == "badge":
        return "a valid badge"
    if mode == "biometric":
        return "recognized biometric authorization"
    kind = str(controller.get("kind", "") or "").strip().lower()
    if kind == "owner_schedule":
        return "the live schedule window or the matching key"
    if kind == "auto_timer":
        return "the live relay window or the matching key"
    return "the matching key"


def viewer_property_credential_status(sim, viewer_eid, prop):
    if viewer_eid is None or not isinstance(prop, dict):
        return ""
    inventory = sim.ecs.get(Inventory).get(viewer_eid)
    state = property_lock_state(prop)
    if not state["key_id"]:
        return ""

    kind = str(prop.get("kind", "")).strip().lower()
    if kind == "building":
        if _controller_intrusion_access_for_actor(sim, viewer_eid, prop):
            return "spoofed"
        controller = _property_access_controller(sim, prop)
        required_tier = max(1, _int_or_default(controller.get("required_credential_tier"), 1))
        if inventory and inventory_matching_property_credential(
            inventory,
            property_id=prop.get("id"),
            key_id=state["key_id"],
            allowed_kinds=controller.get("accepted_credentials", ()),
            minimum_tier=required_tier,
        ):
            return "held"
        if str(controller.get("credential_mode", "")).strip().lower() == "biometric":
            holder = controller_holder_for_actor(controller, viewer_eid)
            if holder and _int_or_default(holder.get("credential_tier"), 0) >= required_tier:
                return "enrolled"
        return ""

    if not inventory:
        return ""
    if inventory_matching_property_key(
        inventory,
        property_id=prop.get("id"),
        key_id=state["key_id"],
    ) is not None:
        return "held"
    return ""


def property_entry_position(prop):
    if not isinstance(prop, dict):
        return None

    entry = property_metadata(prop).get("entry")
    if isinstance(entry, dict):
        try:
            return (
                int(entry.get("x")),
                int(entry.get("y")),
                int(entry.get("z", prop.get("z", 0))),
            )
        except (TypeError, ValueError):
            pass

    try:
        return (int(prop["x"]), int(prop["y"]), int(prop.get("z", 0)))
    except (TypeError, ValueError, KeyError):
        return None


def property_aperture_at(prop, x, y, z=0):
    if not isinstance(prop, dict):
        return None

    try:
        x = int(x)
        y = int(y)
        z = int(z)
    except (TypeError, ValueError):
        return None

    for aperture in _property_apertures(prop):
        if (x, y, z) == (
            int(aperture.get("x", -999999)),
            int(aperture.get("y", -999999)),
            int(aperture.get("z", prop.get("z", 0))),
        ):
            return aperture
    return None


def property_signage(prop):
    signage = property_metadata(prop).get("signage")
    return signage if isinstance(signage, dict) else None


def property_display_position(prop, active_quest_target=None):
    if not isinstance(prop, dict):
        return None

    kind = str(prop.get("kind", "property")).strip().lower() or "property"
    if kind != "building":
        try:
            return (int(prop["x"]), int(prop["y"]), int(prop.get("z", 0)))
        except (TypeError, ValueError, KeyError):
            return None

    signage = property_signage(prop)
    if signage:
        try:
            return (
                int(signage.get("x")),
                int(signage.get("y")),
                int(signage.get("z", prop.get("z", 0))),
            )
        except (TypeError, ValueError):
            pass

    if prop.get("id") == active_quest_target:
        return property_entry_position(prop)
    return None


def building_id_from_property(prop):
    metadata = property_metadata(prop)
    building_id = metadata.get("building_id")
    return str(building_id).strip() if building_id not in (None, "") else ""


def building_id_from_structure(info):
    if not isinstance(info, dict):
        return ""
    building_id = info.get("building_id")
    return str(building_id).strip() if building_id not in (None, "") else ""


def viewer_revealed_building_id(sim, viewer_eid, z=None):
    if viewer_eid is None:
        return ""

    pos = sim.ecs.get(Position).get(viewer_eid)
    if not pos:
        return ""
    if z is not None and int(pos.z) != int(z):
        return ""

    structure = sim.structure_at(pos.x, pos.y, pos.z) if hasattr(sim, "structure_at") else None
    building_id = building_id_from_structure(structure)
    if building_id:
        return building_id

    prop = property_covering(sim, pos.x, pos.y, pos.z)
    return building_id_from_property(prop)


def property_focus_position(prop):
    entry = property_entry_position(prop)
    if entry is not None:
        return entry
    return property_display_position(prop)


def property_covering(sim, x, y, z=0):
    if hasattr(sim, "property_covering"):
        return sim.property_covering(x, y, z)
    return sim.property_at(x, y, z)


def property_power_cut_active(sim, prop, *, tick=None):
    if sim is None or not isinstance(prop, dict):
        return False
    power_cuts = getattr(sim, "fixture_power_cuts", {})
    if not isinstance(power_cuts, dict) or not power_cuts:
        return False
    if tick is None:
        tick = _int_or_default(getattr(sim, "tick", 0), 0)
    else:
        tick = _int_or_default(tick, _int_or_default(getattr(sim, "tick", 0), 0))

    prop_id = str(prop.get("id", "") or "").strip()
    if prop_id and _int_or_default(power_cuts.get(prop_id), 0) > tick:
        return True

    cover_index = getattr(sim, "property_cover_index", {})
    if not isinstance(cover_index, dict):
        return False
    prop_x = _int_or_default(prop.get("x"), 0)
    prop_y = _int_or_default(prop.get("y"), 0)
    prop_z = _int_or_default(prop.get("z"), 0)
    for covered_pid in tuple(cover_index.get((prop_x, prop_y, prop_z), ()) or ()):
        if _int_or_default(power_cuts.get(covered_pid), 0) > tick:
            return True
    return False


def property_enclosing_structure(sim, x, y, z=0, *, prop=None):
    try:
        key = (int(x), int(y), int(z))
    except (TypeError, ValueError):
        return None

    def _is_structured(candidate):
        if not isinstance(candidate, dict):
            return False
        kind = str(candidate.get("kind", "") or "").strip().lower()
        if kind == "building":
            return True
        metadata = property_metadata(candidate)
        if isinstance(metadata.get("footprint"), dict):
            return True
        footprint_cells = metadata.get("footprint_cells")
        return isinstance(footprint_cells, (list, tuple, set, frozenset)) and bool(footprint_cells)

    seen = set()
    candidates = []
    for candidate in (prop, property_covering(sim, key[0], key[1], key[2])):
        if not isinstance(candidate, dict):
            continue
        candidate_id = str(candidate.get("id", "") or "").strip()
        if candidate_id and candidate_id in seen:
            continue
        if candidate_id:
            seen.add(candidate_id)
        candidates.append(candidate)

    cover_index = getattr(sim, "property_cover_index", {})
    indexed_candidates = []
    if isinstance(cover_index, dict):
        for property_id in tuple(cover_index.get(key, ()) or ()):
            candidate = getattr(sim, "properties", {}).get(property_id)
            candidate_id = str((candidate or {}).get("id", "") or "").strip()
            if candidate_id and candidate_id in seen:
                continue
            if candidate_id:
                seen.add(candidate_id)
            indexed_candidates.append(candidate)

    structure = None
    if sim is not None and hasattr(sim, "structure_at"):
        try:
            structure = sim.structure_at(key[0], key[1], key[2])
        except (TypeError, ValueError):
            structure = None
    structure = structure if isinstance(structure, dict) else {}
    room_kind = str(structure.get("room_kind", "") or "").strip().lower()
    common_area_kind = str(structure.get("common_area_kind", "") or "").strip().lower()
    if room_kind or common_area_kind:
        common_candidates = []
        for candidate in candidates + indexed_candidates:
            if not _is_structured(candidate):
                continue
            metadata = property_metadata(candidate)
            common_rooms = {
                str(value or "").strip().lower()
                for value in tuple(metadata.get("common_area_room_kinds", ()) or ())
                if str(value or "").strip()
            }
            common_kinds = {
                str(value or "").strip().lower()
                for value in tuple(metadata.get("common_area_kinds", ()) or ())
                if str(value or "").strip()
            }
            configured_kind = str(metadata.get("common_area_kind", "") or "").strip().lower()
            if (
                (room_kind and room_kind in common_rooms)
                or (common_area_kind and common_area_kind in common_kinds)
                or (common_area_kind and configured_kind == common_area_kind)
            ):
                common_candidates.append(candidate)
        if common_candidates:
            common_candidates.sort(
                key=lambda candidate: (
                    0 if bool(property_metadata(candidate).get("span_parent")) else 1,
                    0 if property_is_public(candidate) else 1,
                    1 if str(property_metadata(candidate).get("span_child_kind", "") or "").strip() else 0,
                    str(candidate.get("id", "") or ""),
                )
            )
            return common_candidates[0]

    for candidate in candidates:
        if _is_structured(candidate):
            return candidate

    if not isinstance(cover_index, dict):
        return None

    for candidate in indexed_candidates:
        if _is_structured(candidate):
            return candidate
    return None


def property_distance(x, y, prop):
    focus = property_focus_position(prop)
    if focus is not None:
        return _manhattan(int(x), int(y), focus[0], focus[1])

    try:
        return _manhattan(int(x), int(y), int(prop["x"]), int(prop["y"]))
    except (TypeError, ValueError, KeyError):
        return 999999


def property_is_storefront(prop):
    return _property_is_storefront_base(prop)


def site_services_for_property(prop):
    return _site_services_for_property_base(prop)


def storefront_service_mode(prop):
    return _storefront_service_mode_base(prop)


def finance_services_for_property(prop):
    return _finance_services_for_property_base(prop)


def property_supports_business_relevance(prop, *, include_assets=False):
    if not isinstance(prop, dict):
        return False
    kind = str(prop.get("kind", "") or "").strip().lower()
    allowed_kinds = {"building", "asset"} if include_assets else {"building"}
    if kind not in allowed_kinds:
        return False
    metadata = property_metadata(prop)
    return bool(
        property_is_storefront(prop)
        or finance_services_for_property(prop)
        or site_services_for_property(prop)
        or str(metadata.get("business_name", "") or "").strip()
    )


def property_fixture_type(prop):
    metadata = property_metadata(prop)
    return str(metadata.get("fixture_type", metadata.get("archetype", "")) or "").strip().lower()


def property_cover_intended(prop):
    if not isinstance(prop, dict):
        return False
    kind = str(prop.get("kind", "") or "").strip().lower()
    if kind not in {"fixture", "asset"}:
        return False

    metadata = property_metadata(prop)
    if bool(metadata.get("cover_intended")):
        return True

    # Keep older saves readable without requiring metadata migration.
    return property_fixture_type(prop) in {
        "bench",
        "bus_stop",
        "planter_box",
        "drift_fence",
    }


def property_services(prop):
    services = []
    for service in finance_services_for_property(prop):
        label = str(service).strip().lower()
        if label and label not in services:
            services.append(label)
    for service in site_services_for_property(prop):
        label = str(service).strip().lower()
        if label and label not in services:
            services.append(label)
    return tuple(services)


def property_infrastructure_role(prop):
    metadata = property_metadata(prop)
    configured = str(metadata.get("interaction_role", "") or "").strip().lower()
    if configured:
        return configured

    kind = str(prop.get("kind", "")).strip().lower()
    if kind not in {"fixture", "asset"}:
        return ""

    fixture_type = property_fixture_type(prop)
    if fixture_type == "security_booth":
        return "security_post"
    if property_services(prop):
        return "service_terminal"
    return ""


def property_linked_property_id(prop):
    metadata = property_metadata(prop)
    value = metadata.get("linked_property_id")
    return str(value).strip() if value not in (None, "") else ""


def property_linked_building_id(prop):
    metadata = property_metadata(prop)
    value = metadata.get("linked_building_id")
    return str(value).strip() if value not in (None, "") else ""


def property_for_action(sim, pos, radius=1):
    prop = property_covering(sim, pos.x, pos.y, pos.z)
    if prop:
        return prop

    nearby = sim.properties_in_radius(pos.x, pos.y, pos.z, r=radius)
    if not nearby:
        return None

    nearby = sorted(
        nearby,
        key=lambda current: _manhattan(pos.x, pos.y, current["x"], current["y"]),
    )
    return nearby[0]


def property_access_level(prop):
    return _property_access_level(prop)


def property_status_text(sim, prop, hour=None):
    return _property_status_text(sim, prop, hour=hour)


def remember_property_lead_for_actor(
    sim,
    viewer_eid,
    prop,
    *,
    source_eid=None,
    lead_kind=None,
    confidence=0.5,
    hidden=None,
    anchored=None,
    anchor_kind=None,
):
    if viewer_eid is None or not prop:
        return False
    knowledge = sim.ecs.get(PropertyKnowledge).get(viewer_eid)
    if not knowledge:
        return False
    existing = knowledge.known.get(prop["id"])
    prior_entry = dict(existing) if isinstance(existing, dict) else None
    prior_conf = float(existing.get("confidence", 0.0)) if existing else 0.0
    prior_source = existing.get("source_eid") if existing else None
    prior_kind = str(existing.get("lead_kind", "") or "").strip().lower() if existing else ""
    prior_hidden = bool(knowledge.is_hidden(prop["id"]))
    knowledge.remember(
        prop["id"],
        owner_eid=prop.get("owner_eid"),
        owner_tag=prop.get("owner_tag"),
        confidence=confidence,
        tick=int(getattr(sim, "tick", 0)),
        source_eid=source_eid,
        lead_kind=lead_kind,
        anchored=anchored,
        anchor_kind=anchor_kind,
    )
    hidden_changed = False
    if hidden is True:
        hidden_changed = bool(knowledge.hide(prop["id"]))
    elif hidden is False:
        hidden_changed = bool(knowledge.unhide(prop["id"]))
    current_hidden = bool(knowledge.is_hidden(prop["id"]))
    current_entry = knowledge.known.get(prop["id"])
    current_conf = float(current_entry.get("confidence", 0.0)) if isinstance(current_entry, dict) else 0.0
    current_source = current_entry.get("source_eid") if isinstance(current_entry, dict) else None
    current_kind = str(current_entry.get("lead_kind", "") or "").strip().lower() if isinstance(current_entry, dict) else ""
    changed = (
        existing is None
        or prior_conf + 0.001 < current_conf
        or prior_source != current_source
        or prior_kind != current_kind
        or (prior_entry or {}).get("owner_eid") != (current_entry or {}).get("owner_eid")
        or (prior_entry or {}).get("owner_tag") != (current_entry or {}).get("owner_tag")
        or bool((prior_entry or {}).get("anchored")) != bool((current_entry or {}).get("anchored"))
        or (prior_entry or {}).get("anchor_kind") != (current_entry or {}).get("anchor_kind")
        or prior_hidden != current_hidden
        or hidden_changed
    )
    if changed:
        note_property_notebook_mutation(
            sim,
            viewer_eid,
            prop,
            before=prior_entry,
            after=current_entry,
            hidden_before=prior_hidden,
            hidden_after=current_hidden,
        )
    return changed


def ensure_runtime_container_entry_instance_ids(sim, entries):
    if not isinstance(entries, list):
        return entries
    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        if str(entry.get("instance_id", "") or "").strip():
            continue
        normalized = dict(entry)
        normalized["instance_id"] = sim.new_item_instance_id()
        entries[idx] = normalized
    return entries


def property_runtime_container_entries(sim, property_id, *, container_kind="container"):
    property_id = str(property_id or "").strip()
    if not property_id:
        return []
    container_kind = str(container_kind or "container").strip().lower() or "container"
    if container_kind == "cache":
        inventories = getattr(sim, "cache_inventories", None)
        if not isinstance(inventories, dict):
            sim.cache_inventories = {}
            inventories = sim.cache_inventories
        return ensure_runtime_container_entry_instance_ids(sim, inventories.setdefault(property_id, []))
    inventories_by_kind = getattr(sim, "container_inventories", None)
    if not isinstance(inventories_by_kind, dict):
        sim.container_inventories = {}
        inventories_by_kind = sim.container_inventories
    inventories = inventories_by_kind.setdefault(container_kind, {})
    if not isinstance(inventories, dict):
        inventories = {}
        inventories_by_kind[container_kind] = inventories
    return ensure_runtime_container_entry_instance_ids(sim, inventories.setdefault(property_id, []))


def property_runtime_container_entry_snapshot(sim, property_id, *, container_kind="container"):
    return list(property_runtime_container_entries(sim, property_id, container_kind=container_kind))


def property_runtime_container_entry_count(sim, property_id, *, container_kind="container"):
    return len(property_runtime_container_entries(sim, property_id, container_kind=container_kind))


def clear_property_runtime_container_state(sim, property_id):
    property_id = str(property_id or "").strip()
    if not property_id:
        return

    inventories = getattr(sim, "cache_inventories", None)
    if isinstance(inventories, dict):
        inventories.pop(property_id, None)

    inventories_by_kind = getattr(sim, "container_inventories", None)
    if isinstance(inventories_by_kind, dict):
        for store in inventories_by_kind.values():
            if isinstance(store, dict):
                store.pop(property_id, None)

    inventory_ui = getattr(sim, "inventory_ui", None)
    if (
        isinstance(inventory_ui, dict)
        and str(inventory_ui.get("panel_kind", "")).strip().lower() == "container"
        and str(inventory_ui.get("property_id", "") or "").strip() == property_id
    ):
        inventory_ui.update({
            "open": False,
            "panel_kind": "inventory",
            "title": "Inventory",
            "property_id": None,
            "container_kind": None,
            "container_label": "Container",
            "container_instance_id": None,
            "container_capacity": None,
            "container_view": "pack",
            "cache_view": "pack",
            "selected_index": 0,
            "inspect_text": "",
            "note_text": "",
        })
