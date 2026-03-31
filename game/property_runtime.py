"""Shared property, vehicle, and controller runtime helpers.

This module holds the pure helper cluster that used to live inside
``game/systems.py`` so systems can share one focused seam without keeping the
main behavior file as a dumping ground for every property-adjacent utility.
"""

from game.components import Inventory, Position
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


def property_is_vehicle(prop):
    if not isinstance(prop, dict):
        return False
    return str(prop.get("kind", "")).strip().lower() == "vehicle"


def vehicle_profile_from_property(prop):
    metadata = property_metadata(prop)
    if not property_is_vehicle(prop):
        return {}
    return {
        "make": str(metadata.get("vehicle_make", "Unknown")).strip() or "Unknown",
        "model": str(metadata.get("vehicle_model", "Vehicle")).strip() or "Vehicle",
        "vehicle_class": str(metadata.get("vehicle_class", "sedan")).strip().lower() or "sedan",
        "quality": str(metadata.get("vehicle_quality", "used")).strip().lower() or "used",
        "power": _int_or_default(metadata.get("power"), 5),
        "durability": _int_or_default(metadata.get("durability"), 5),
        "fuel_efficiency": _int_or_default(metadata.get("fuel_efficiency"), 5),
        "fuel_capacity": _int_or_default(metadata.get("fuel_capacity"), 60),
        "fuel": _int_or_default(metadata.get("fuel"), _int_or_default(metadata.get("fuel_capacity"), 60)),
        "usable": bool(metadata.get("vehicle_usable", True)),
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


def property_fixture_type(prop):
    metadata = property_metadata(prop)
    return str(metadata.get("fixture_type", metadata.get("archetype", "")) or "").strip().lower()


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
