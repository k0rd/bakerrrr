"""Preflight-only wire connection shell for existing infrastructure fixtures."""

from __future__ import annotations

from collections.abc import Mapping

from engine.events import Event
from game.components import Inventory, Position
from game.items import ITEM_CATALOG, item_display_name
from game.property_runtime import property_linked_property_id
from game.skills import actor_skill
from game.wire_kit import provision_wire_state_from_interface, wire_state_for_actor
from game.wire_runtime import (
    is_wire_interface_item,
    normalize_wire_interface_metadata,
    wire_interface_profile_for_item,
)
from game.wire_consequences import wire_connection_blockers, wire_network_property, wire_security_lockout_status, wire_recovery_status
from game.wire_targets import (
    drone_wire_target_ref,
    property_wire_target_ref,
    resolve_wire_target,
    vehicle_wire_target_ref,
    wire_target_has_live_radio,
    wire_target_identity,
    wire_target_ref_from_connection,
)


WIRE_CONNECTION_TARGET_CLASSES = {"access_panel", "service_terminal", "vehicle_controller"}


def _clean_text(value, default=""):
    text = str(value or "").strip()
    return text if text else str(default or "").strip()


def _clean_id(value):
    return _clean_text(value).lower()


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _deliberate_service_terminal_wire_target(prop, metadata):
    if not isinstance(prop, Mapping):
        return False
    role = _clean_id(metadata.get("interaction_role"))
    fixture = _clean_id(metadata.get("fixture_type"))
    archetype = _clean_id(metadata.get("archetype"))
    services = {
        _clean_id(service)
        for service in tuple(metadata.get("finance_services", ()) or ())
        + tuple(metadata.get("site_services", ()) or ())
        + tuple(prop.get("services", ()) or ())
        if _clean_id(service)
    }
    return (
        role == "service_terminal"
        or fixture in {"service_terminal", "atm_kiosk", "banking_kiosk"}
        or archetype in {"atm_kiosk", "banking_kiosk"}
        or "banking" in services
    )


def wire_target_class_for_property(prop, *, deliberate=False):
    if not isinstance(prop, Mapping):
        return ""
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), Mapping) else {}
    if deliberate and _clean_id(prop.get("kind")) == "vehicle":
        return "vehicle_controller"
    explicit_role = _clean_id(metadata.get("interaction_role"))
    fixture_type = _clean_id(metadata.get("fixture_type"))
    target_class = explicit_role if explicit_role in WIRE_CONNECTION_TARGET_CLASSES else ""
    if not target_class and fixture_type in WIRE_CONNECTION_TARGET_CLASSES:
        target_class = fixture_type
    if target_class == "service_terminal":
        # Ordinary service/interact keeps ATM banking as the default. A
        # deliberate wire action can still jack into service kiosks and ATMs.
        linked_id = _clean_text(property_linked_property_id(prop))
        if linked_id or bool(metadata.get("wire_capable")) or bool(deliberate):
            return target_class
        return ""
    if target_class:
        return target_class
    if deliberate and _deliberate_service_terminal_wire_target(prop, metadata):
        return "service_terminal"
    return ""


def _inventory_entries(sim, actor_eid):
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if inventory is None:
        return ()
    from game.technical_research import apply_technical_research_to_entry

    for entry in tuple(getattr(inventory, "items", ()) or ()):
        apply_technical_research_to_entry(sim, actor_eid, entry, item_catalog=ITEM_CATALOG)
    return tuple(entry for entry in getattr(inventory, "items", ()) or () if isinstance(entry, Mapping))


def _entry_instance_id(entry):
    return str((entry or {}).get("instance_id", "") or "").strip()


def _interface_record(entry, *, target_class, item_catalog=None):
    item_catalog = item_catalog or ITEM_CATALOG
    item_id = _clean_id((entry or {}).get("item_id"))
    if not is_wire_interface_item(item_id, item_catalog=item_catalog):
        return None
    profile = wire_interface_profile_for_item(item_id, item_catalog=item_catalog)
    if target_class not in set(profile.get("supported_target_classes", ()) or ()):
        return None
    metadata = normalize_wire_interface_metadata(
        dict((entry or {}).get("metadata") or {}),
        item_id=item_id,
        profile=profile,
    )
    quality_score = {"poor": 0, "standard": 1, "good": 2, "excellent": 3}.get(
        _clean_id(metadata.get("quality")),
        1,
    )
    score = (
        quality_score * 10
        + _int(metadata.get("warning_rating"), 0) * 3
        + _int(metadata.get("trace_resistance"), 0) * 2
        + _int(metadata.get("buffer_size"), 0)
        + _int(metadata.get("program_slots"), 0)
        - _int(metadata.get("signature_leakage"), 0)
        - _int(metadata.get("noise_floor"), 0)
        - _int(metadata.get("shock_risk"), 0)
    )
    return {
        "entry": dict(entry),
        "item_id": item_id,
        "instance_id": _entry_instance_id(entry),
        "name": item_display_name(item_id, metadata=metadata, item_catalog=item_catalog),
        "profile": profile,
        "metadata": metadata,
        "score": int(score),
    }


def compatible_wire_interface_records(sim, actor_eid, target_class, *, item_catalog=None):
    records = [
        record
        for record in (
            _interface_record(entry, target_class=target_class, item_catalog=item_catalog)
            for entry in _inventory_entries(sim, actor_eid)
        )
        if record is not None
    ]
    records.sort(key=lambda row: (-int(row.get("score", 0)), str(row.get("instance_id", ""))))
    return tuple(records)


def select_wire_interface_record(sim, actor_eid, target_class, *, preferred_instance_id=None, item_catalog=None):
    records = compatible_wire_interface_records(sim, actor_eid, target_class, item_catalog=item_catalog)
    preferred = str(preferred_instance_id or "").strip()
    if preferred:
        for record in records:
            if str(record.get("instance_id", "") or "") == preferred:
                return record
    return records[0] if records else None


def set_preferred_wire_interface(sim, actor_eid, instance_id, *, item_catalog=None):
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if inventory is None:
        return {"ok": False, "reason": "missing_inventory"}
    entry = inventory.find(instance_id=instance_id)
    if entry is None:
        return {"ok": False, "reason": "interface_unavailable"}
    item_id = _clean_id(entry.get("item_id"))
    if not is_wire_interface_item(item_id, item_catalog=item_catalog or ITEM_CATALOG):
        return {"ok": False, "reason": "not_wire_interface", "entry": dict(entry)}
    state = wire_state_for_actor(sim, actor_eid, create=True)
    state.equipped_interface_instance_id = str(instance_id or "").strip()
    provision_wire_state_from_interface(state, entry=entry, item_id=item_id, item_catalog=item_catalog or ITEM_CATALOG)
    state.last_wire_feedback = f"Preferred interface set to {item_display_name(item_id, metadata=entry.get('metadata'), item_catalog=item_catalog or ITEM_CATALOG)}."
    return {"ok": True, "reason": None, "entry": dict(entry), "wire_state": state}


def _actor_position(sim, actor_eid):
    return sim.ecs.get(Position).get(actor_eid)


def _reachable_fixture(sim, actor_eid, prop):
    pos = _actor_position(sim, actor_eid)
    if pos is None or not isinstance(prop, Mapping):
        return False
    try:
        if int(pos.z) != int(prop.get("z", pos.z)):
            return False
        dist = abs(int(pos.x) - int(prop.get("x", pos.x))) + abs(int(pos.y) - int(prop.get("y", pos.y)))
    except (TypeError, ValueError):
        return False
    return dist <= 1


def _reachable_target(sim, actor_eid, target, interface=None):
    pos = _actor_position(sim, actor_eid)
    if pos is None or not isinstance(target, Mapping):
        return False
    try:
        target_z = int(target.get("z", pos.z))
        distance = abs(int(pos.x) - int(target.get("x", pos.x))) + abs(int(pos.y) - int(target.get("y", pos.y)))
    except (TypeError, ValueError):
        return False
    if int(pos.z) != target_z:
        return False
    if str(target.get("kind", "property") or "property") == "drone":
        metadata = dict((interface or {}).get("metadata") or {}) if isinstance(interface, Mapping) else {}
        profile = dict((interface or {}).get("profile") or {}) if isinstance(interface, Mapping) else {}
        range_limit = _int(metadata.get("range"), _int(profile.get("range"), 0))
        return bool(range_limit > 0 and distance <= range_limit)
    return distance <= 1


def _property_target_record(prop, *, target_class):
    if not isinstance(prop, Mapping):
        return None
    metadata = dict(prop.get("metadata") or {}) if isinstance(prop.get("metadata"), Mapping) else {}
    linked_id = _clean_text(property_linked_property_id(prop))
    is_vehicle = target_class == "vehicle_controller" and _clean_id(prop.get("kind")) == "vehicle"
    ref = (
        vehicle_wire_target_ref(prop, target_class=target_class)
        if is_vehicle
        else property_wire_target_ref(prop, target_class=target_class)
    )
    if not ref:
        return None
    return {
        "ref": ref,
        "identity": wire_target_identity(ref),
        "kind": "vehicle" if is_vehicle else "property",
        "target_class": target_class,
        "name": _clean_text(prop.get("name"), target_class.replace("_", " ") or "wire target"),
        "x": _int(prop.get("x"), 0),
        "y": _int(prop.get("y"), 0),
        "z": _int(prop.get("z"), 0),
        "metadata": metadata,
        "property": prop,
        "vehicle": prop if is_vehicle else None,
        "vehicle_id": _clean_text(prop.get("id")) if is_vehicle else "",
        "linked_property_id": linked_id,
        "source": prop,
    }


def _linked_target_status(sim, prop, target_class):
    linked_id = property_linked_property_id(prop)
    metadata = prop.get("metadata") if isinstance((prop or {}).get("metadata"), Mapping) else {}
    fixture_live = not bool(metadata.get("fixture_broken")) and metadata.get("fixture_usable") is not False
    if target_class == "access_panel":
        linked = getattr(sim, "properties", {}).get(str(linked_id)) if linked_id else None
        return {
            "linked_property_id": linked_id,
            "linked_live": bool(isinstance(linked, Mapping) and fixture_live),
            "fixture_live": bool(fixture_live),
            "label": _clean_text((linked or {}).get("name"), "linked site") if linked else "linked site",
        }
    return {
        "linked_property_id": linked_id,
        "linked_live": bool(fixture_live),
        "fixture_live": bool(fixture_live),
        "label": _clean_text(prop.get("name"), "service terminal"),
    }


def _service_terminal_context_hint(prop):
    metadata = prop.get("metadata") if isinstance((prop or {}).get("metadata"), Mapping) else {}
    fixture = _clean_id(metadata.get("fixture_type"))
    archetype = _clean_id(metadata.get("archetype"))
    services = {
        _clean_id(service)
        for service in tuple(metadata.get("finance_services", ()) or ())
        + tuple(metadata.get("site_services", ()) or ())
        + tuple((prop or {}).get("services", ()) or ())
        if _clean_id(service)
    }
    if fixture in {"atm_kiosk", "banking_kiosk"} or archetype in {"atm_kiosk", "banking_kiosk"} or "banking" in services:
        return "ATM wire presence: routine banking stays local; larger or sensitive transfers may expect an avatar-facing session."
    return ""


def _risk_phrase(value, *, warning_rating):
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = 0.0
    if warning_rating <= 1:
        if value <= 0:
            return "unknown"
        if value <= 1:
            return "unclear"
        return "noisy"
    if value <= 0:
        return "known low"
    if value <= 1:
        return "likely low"
    if value <= 2:
        return "unclear"
    return "likely high"


def _wire_connection_preflight_target(sim, actor_eid, target, *, item_catalog=None, deliberate=False):
    item_catalog = item_catalog or ITEM_CATALOG
    if not isinstance(target, Mapping):
        return {
            "ok": False,
            "target_class": "",
            "target_ref": {},
            "target_identity": "",
            "target_property_id": "",
            "target_entity_id": None,
            "target_name": "wire target",
            "reachable": False,
            "interface": None,
            "compatible_interfaces": (),
            "reasons": ("target_unavailable",),
            "preview_lines": ("Target: unavailable.",),
            "target_status": {},
            "skills": {},
            "deliberate": bool(deliberate),
        }
    target_class = _clean_id(target.get("target_class"))
    target_ref = dict(target.get("ref") or {})
    target_identity = _clean_text(target.get("identity") or wire_target_identity(target_ref))
    state = wire_state_for_actor(sim, actor_eid, create=True)
    records = compatible_wire_interface_records(sim, actor_eid, target_class, item_catalog=item_catalog) if target_class else ()
    selected = select_wire_interface_record(
        sim,
        actor_eid,
        target_class,
        preferred_instance_id=getattr(state, "equipped_interface_instance_id", None),
        item_catalog=item_catalog,
    ) if target_class else None
    reachable = _reachable_target(sim, actor_eid, target, selected)
    if target.get("kind") == "property":
        prop = target.get("property") if isinstance(target.get("property"), Mapping) else {}
        target_status = _linked_target_status(sim, prop, target_class) if target_class else {}
    elif target.get("kind") == "vehicle":
        prop = target.get("property") if isinstance(target.get("property"), Mapping) else {}
        metadata = dict(target.get("metadata") or {})
        target_status = {
            "linked_property_id": "",
            "linked_live": True,
            "label": _clean_text(target.get("name"), "vehicle controller"),
            "vehicle_id": target.get("vehicle_id") or prop.get("id"),
            "locked": bool(metadata.get("property_locked", False)),
            "lock_tier": _int(metadata.get("property_lock_tier"), 1),
            "tracker_installed": bool(metadata.get("vehicle_tracker_installed", False)),
            "tracker_enabled": bool(metadata.get("vehicle_tracker_enabled", False)),
            "usable": bool(metadata.get("vehicle_usable", True)) and _int(metadata.get("durability"), 0) > 0,
        }
    else:
        target_status = {
            "linked_property_id": "",
            "linked_live": True,
            "label": _clean_text(target.get("name"), "deployed drone"),
            "drone_eid": target.get("drone_eid"),
            "stable_id": (target_ref or {}).get("stable_id", ""),
            "radio_live": wire_target_has_live_radio(target, tick=int(getattr(sim, "tick", 0) or 0)),
        }
    network_ref = {
        "target_property_id": str((target.get("property") or {}).get("id", "") or "") if target.get("kind") in {"property", "vehicle"} else "",
        "target_entity_id": target.get("drone_eid") if target.get("kind") == "drone" else None,
        "target_identity": target_identity,
        "target_class": target_class,
        "linked_property_id": target_status.get("linked_property_id", ""),
    }
    skills = {
        "intrusion": float(actor_skill(sim, actor_eid, "intrusion", default=5.0)),
        "mechanics": float(actor_skill(sim, actor_eid, "mechanics", default=5.0)),
        "perception": float(actor_skill(sim, actor_eid, "perception", default=5.0)),
    }
    reasons = []
    if not target_class:
        reasons.append("not_wire_target")
    if not reachable and (target.get("kind") != "drone" or selected is not None):
        reasons.append("out_of_range" if target.get("kind") == "drone" else "not_adjacent")
    if not selected:
        reasons.append("no_compatible_interface")
    if target_class == "access_panel" and not bool(target_status.get("linked_live")):
        reasons.append("target_offline" if not bool(target_status.get("fixture_live", True)) else "target_link_unclear")
    if target_class == "service_terminal" and not bool(target_status.get("fixture_live", True)):
        reasons.append("target_offline")
    if target.get("kind") == "drone" and not bool(target_status.get("radio_live")):
        reasons.append("target_radio_unavailable")
    for blocker in wire_connection_blockers(sim, actor_eid, network_ref):
        if blocker not in reasons:
            reasons.append(blocker)

    metadata = dict((selected or {}).get("metadata") or {})
    warning_rating = _int(metadata.get("warning_rating"), 0)
    target_label = _clean_text(target_status.get("label") or target.get("name"), "target")
    preview_lines = []
    if selected:
        quality = _clean_id(metadata.get("quality")) or "standard"
        manufacturer = _clean_text(metadata.get("manufacturer"), "unknown")
        preview_lines.append(f"Interface: {selected['name']} [{quality}, {manufacturer}]")
        preview_lines.append(
            "Signal: "
            f"trace { _risk_phrase(metadata.get('signature_leakage'), warning_rating=warning_rating) }, "
            f"shock { _risk_phrase(metadata.get('shock_risk'), warning_rating=warning_rating) }, "
            f"noise floor { _risk_phrase(metadata.get('noise_floor'), warning_rating=warning_rating) }"
        )
    else:
        preview_lines.append("Interface: none compatible in backpack.")
    if target_class:
        live_text = "known linked" if target_status.get("linked_live") else "link unclear"
        preview_lines.append(f"Target: {target_class.replace('_', ' ')} at {target_label}; {live_text}.")
    prop = target.get("property") if isinstance(target.get("property"), Mapping) else {}
    context_hint = _service_terminal_context_hint(prop) if target_class == "service_terminal" else ""
    if context_hint:
        preview_lines.append(context_hint)
    lockout = wire_security_lockout_status(sim, network_ref)
    if lockout.get("locked"):
        preview_lines.append(f"Network security: locked for {int(lockout.get('remaining', 0))} more ticks.")
    recovery = wire_recovery_status(sim, actor_eid)
    if recovery.get("active"):
        preview_lines.append(f"Body/interface recovery: {int(recovery.get('remaining', 0))} ticks remain.")
    if target.get("kind") == "drone":
        drone_metadata = dict(target.get("metadata") or {})
        battery = _int(drone_metadata.get("battery_charge"), 0)
        battery_max = _int(drone_metadata.get("battery_charge_max"), 0)
        procedure = _clean_text(drone_metadata.get("procedure_program_id") or drone_metadata.get("procedure_key"), "idle")
        preview_lines.append(f"Drone link: battery {battery}/{battery_max}; routine {procedure.replace('_', ' ')}.")
    elif target.get("kind") == "vehicle":
        vehicle_metadata = dict(target.get("metadata") or {})
        fuel = _int(vehicle_metadata.get("fuel"), 0)
        fuel_capacity = _int(vehicle_metadata.get("fuel_capacity"), 0)
        durability = _int(vehicle_metadata.get("durability"), 0)
        lock_label = "locked" if target_status.get("locked") else "unlocked"
        tracker_label = (
            "active" if target_status.get("tracker_enabled") else "standby"
        ) if target_status.get("tracker_installed") else "not installed"
        preview_lines.append(
            f"Vehicle bus: {lock_label}, tracker {tracker_label}, fuel {fuel}/{fuel_capacity}, condition {durability}/10."
        )
    if target.get("kind") != "vehicle" and target_class:
        from game.wire_data_market import wire_data_payoff_preview

        payoff_prop = wire_network_property(sim, network_ref)
        if not isinstance(payoff_prop, Mapping):
            payoff_prop = prop
        payoff_scene = dict(network_ref)
        payoff_scene.update({
            "scene_id": f"wire-preview:{target_identity}",
            "target_kind": _clean_id(target.get("kind")),
            "security_tier": _int((payoff_prop.get("metadata") or {}).get("security_tier"), 1) if isinstance(payoff_prop, Mapping) else 1,
        })
        payoff = wire_data_payoff_preview(payoff_scene, payoff_prop)
        if payoff:
            preview_lines.append(
                f"Payoff: {payoff.get('label', 'brokerable records')}; download works without software, while Decryptor Shell restores full fidelity and value."
            )
    if target_class == "access_panel":
        preview_lines.append("Physical leverage: door-latch and camera-loop programs can create short real-world windows.")
    elif target.get("kind") == "drone":
        preview_lines.append("Physical leverage: radio programs can disrupt or contest the live command link.")
    preview_lines.append(
        f"Skill read: intrusion {skills['intrusion']:.1f}, mechanics {skills['mechanics']:.1f}, perception {skills['perception']:.1f}."
    )
    if warning_rating <= 1 and selected:
        preview_lines.append("Warnings are noisy; cheap/cracked gear can only guess at danger.")

    return {
        "ok": bool(target_class and reachable and selected and not reasons),
        "target_class": target_class,
        "target_ref": target_ref,
        "target_identity": target_identity,
        "target_kind": _clean_id(target.get("kind")),
        "target_property_id": str((prop or {}).get("id", "") or ""),
        "target_entity_id": target.get("drone_eid") if target.get("kind") == "drone" else None,
        "target_name": _clean_text(target.get("name"), target_class.replace("_", " ") if target_class else "wire target"),
        "reachable": bool(reachable),
        "interface": selected,
        "compatible_interfaces": records,
        "reasons": tuple(reasons),
        "preview_lines": tuple(preview_lines),
        "target_status": target_status,
        "skills": skills,
        "deliberate": bool(deliberate),
    }


def wire_connection_preflight(sim, actor_eid, prop, *, item_catalog=None, deliberate=False):
    target_class = wire_target_class_for_property(prop, deliberate=deliberate)
    target = _property_target_record(prop, target_class=target_class) if target_class else None
    return _wire_connection_preflight_target(
        sim,
        actor_eid,
        target,
        item_catalog=item_catalog,
        deliberate=deliberate,
    )


def wire_connection_preflight_ref(sim, actor_eid, target_ref, *, item_catalog=None, deliberate=False):
    target = resolve_wire_target(sim, target_ref)
    return _wire_connection_preflight_target(
        sim,
        actor_eid,
        target,
        item_catalog=item_catalog,
        deliberate=deliberate,
    )


def _active_connection_matches_ref(state, target_ref):
    active = getattr(state, "active_connection", None)
    if not isinstance(active, Mapping):
        return False
    return bool(
        wire_target_identity(wire_target_ref_from_connection(active))
        and wire_target_identity(wire_target_ref_from_connection(active)) == wire_target_identity(target_ref)
    )


def _wire_connection_rows_for_target(sim, actor_eid, target, *, item_catalog=None, deliberate=False):
    state = wire_state_for_actor(sim, actor_eid, create=True)
    preflight = _wire_connection_preflight_target(
        sim,
        actor_eid,
        target,
        item_catalog=item_catalog,
        deliberate=deliberate,
    )
    target_ref = preflight.get("target_ref") if isinstance(preflight.get("target_ref"), Mapping) else {}
    connected = _active_connection_matches_ref(state, target_ref)
    target_class = str(preflight.get("target_class", "") or "")
    target_kind = str(preflight.get("target_kind", "") or "")
    rows = []
    if target_kind in {"property", "vehicle"}:
        if target_kind == "vehicle":
            normal_label = "Normal vehicle use"
        else:
            normal_label = "Normal panel use" if target_class == "access_panel" else "Normal service use"
        rows.append({"action": "normal_use", "label": f"{normal_label}: run the existing fixture behavior."})
    rows.append({"action": "preview", "label": "Connect preview: " + "; ".join(preflight.get("preview_lines", ())[:2])})
    if target_kind == "drone" and not connected:
        from game.wire_drone_bridge import drone_wire_shell_rows

        rows.extend(
            row
            for row in drone_wire_shell_rows(sim, actor_eid, target_ref)
            if row.get("action") == "drone_restore_link"
        )
    if connected:
        if target_kind == "drone":
            from game.wire_drone_bridge import drone_wire_shell_rows

            rows.extend(drone_wire_shell_rows(sim, actor_eid, target_ref))
        elif target_kind == "vehicle":
            from game.wire_vehicle_bridge import vehicle_wire_shell_rows

            rows.extend(vehicle_wire_shell_rows(sim, actor_eid, target_ref))
        rows.append({"action": "enter_wire_scene", "label": "Enter wire layer: project the local systems graph."})
        rows.append({"action": "disconnect", "label": f"Disconnect from {preflight.get('target_name', 'target')}."})
    else:
        reason = ", ".join(str(reason).replace("_", " ") for reason in preflight.get("reasons", ()) or ())
        suffix = "" if preflight.get("ok") else f" [{reason or 'blocked'}]"
        rows.append({"action": "connect", "label": f"Connect to shell{suffix}."})
    interface = preflight.get("interface")
    if interface:
        rows.append({"action": "cycle_interface", "label": f"Preferred interface: {interface.get('name')} (cycle)."})
    else:
        rows.append({"action": "cycle_interface", "label": "Preferred interface: none compatible."})
    rows.append({"action": "close", "label": "Close."})
    return rows, preflight


def wire_connection_rows(sim, actor_eid, prop, *, item_catalog=None, deliberate=False):
    target_class = wire_target_class_for_property(prop, deliberate=deliberate)
    target = _property_target_record(prop, target_class=target_class) if target_class else None
    return _wire_connection_rows_for_target(
        sim,
        actor_eid,
        target,
        item_catalog=item_catalog,
        deliberate=deliberate,
    )


def refresh_wire_connection_ui(sim, actor_eid, *, item_catalog=None):
    state = getattr(sim, "wire_connection_ui", None)
    if not isinstance(state, dict) or not bool(state.get("open")):
        return []
    target_ref = state.get("target_ref") if isinstance(state.get("target_ref"), Mapping) else {}
    if not target_ref and state.get("property_id"):
        target_ref = {
            "kind": "property",
            "property_id": state.get("property_id"),
            "target_class": state.get("target_class"),
        }
    target = resolve_wire_target(sim, target_ref)
    if not isinstance(target, Mapping):
        state["open"] = False
        disconnect_wire_connection(sim, actor_eid, reason="target_unloaded")
        return []
    state["target_ref"] = dict(target.get("ref") or target_ref)
    state["property_id"] = str((target.get("property") or {}).get("id", "") or "") if target.get("kind") in {"property", "vehicle"} else ""
    state["target_entity_id"] = target.get("drone_eid") if target.get("kind") == "drone" else None
    rows, preflight = _wire_connection_rows_for_target(
        sim,
        actor_eid,
        target,
        item_catalog=item_catalog,
        deliberate=bool(state.get("deliberate")),
    )
    state["rows"] = rows
    state["preflight"] = preflight
    state["status_lines"] = list(preflight.get("preview_lines", ()) or ())
    if rows:
        state["selected_index"] = max(0, min(_int(state.get("selected_index"), 0), len(rows) - 1))
    else:
        state["selected_index"] = 0
    return rows


def open_wire_connection_shell(sim, actor_eid, prop, *, interaction_mode="physical", item_catalog=None, deliberate=False):
    target_class = wire_target_class_for_property(prop, deliberate=deliberate)
    if not target_class:
        return False
    target_ref = (
        vehicle_wire_target_ref(prop, target_class=target_class)
        if target_class == "vehicle_controller"
        else property_wire_target_ref(prop, target_class=target_class)
    )
    state = getattr(sim, "wire_connection_ui", None)
    if not isinstance(state, dict):
        state = {}
        sim.wire_connection_ui = state
    state.update({
        "open": True,
        "property_id": str(prop.get("id", "") or ""),
        "target_entity_id": None,
        "target_ref": target_ref,
        "interaction_mode": str(interaction_mode or "physical").strip().lower() or "physical",
        "target_class": target_class,
        "deliberate": bool(deliberate),
        "selected_index": 0,
        "scroll": 0,
        "feedback": "Wire shell ready.",
    })
    refresh_wire_connection_ui(sim, actor_eid, item_catalog=item_catalog)
    sim.emit(Event("wire_connection_opened", eid=actor_eid, property_id=prop.get("id"), target_class=target_class))
    return True


def open_wire_drone_connection_shell(sim, actor_eid, drone_eid, *, item_catalog=None):
    target_ref = drone_wire_target_ref(sim, drone_eid)
    target = resolve_wire_target(sim, target_ref)
    if not isinstance(target, Mapping):
        return False
    state = getattr(sim, "wire_connection_ui", None)
    if not isinstance(state, dict):
        state = {}
        sim.wire_connection_ui = state
    state.update({
        "open": True,
        "property_id": "",
        "target_entity_id": target.get("drone_eid"),
        "target_ref": dict(target.get("ref") or target_ref),
        "interaction_mode": "wire_remote",
        "target_class": "drone_radio",
        "deliberate": True,
        "selected_index": 0,
        "scroll": 0,
        "feedback": "Drone radio handshake ready.",
    })
    refresh_wire_connection_ui(sim, actor_eid, item_catalog=item_catalog)
    sim.emit(Event(
        "wire_connection_opened",
        eid=actor_eid,
        target_entity_id=target.get("drone_eid"),
        target_stable_id=(target.get("ref") or {}).get("stable_id"),
        target_class="drone_radio",
    ))
    return True


def open_wire_vehicle_connection_shell(sim, actor_eid, vehicle_prop, *, item_catalog=None):
    if not isinstance(vehicle_prop, Mapping) or _clean_id(vehicle_prop.get("kind")) != "vehicle":
        return False
    return open_wire_connection_shell(
        sim,
        actor_eid,
        vehicle_prop,
        interaction_mode="wire_vehicle",
        item_catalog=item_catalog,
        deliberate=True,
    )


def close_wire_connection_shell(sim):
    state = getattr(sim, "wire_connection_ui", None)
    if isinstance(state, dict):
        state["open"] = False
        state["scroll"] = 0
    return True


def connect_wire_target(sim, actor_eid, prop, *, item_catalog=None, deliberate=False):
    preflight = wire_connection_preflight(sim, actor_eid, prop, item_catalog=item_catalog, deliberate=deliberate)
    return _connect_wire_preflight(sim, actor_eid, preflight, item_catalog=item_catalog, deliberate=deliberate)


def connect_wire_target_ref(sim, actor_eid, target_ref, *, item_catalog=None, deliberate=False):
    preflight = wire_connection_preflight_ref(
        sim,
        actor_eid,
        target_ref,
        item_catalog=item_catalog,
        deliberate=deliberate,
    )
    return _connect_wire_preflight(sim, actor_eid, preflight, item_catalog=item_catalog, deliberate=deliberate)


def _connect_wire_preflight(sim, actor_eid, preflight, *, item_catalog=None, deliberate=False):
    state = wire_state_for_actor(sim, actor_eid, create=True)
    if not preflight.get("ok"):
        reason = (preflight.get("reasons") or ("blocked",))[0]
        state.last_wire_feedback = f"Connection blocked: {str(reason).replace('_', ' ')}."
        return {"ok": False, "reason": reason, "preflight": preflight}
    interface = preflight.get("interface") or {}
    state.equipped_interface_instance_id = str(interface.get("instance_id", "") or "") or getattr(state, "equipped_interface_instance_id", None)
    provision_wire_state_from_interface(
        state,
        item_id=interface.get("item_id"),
        metadata=interface.get("metadata") if isinstance(interface.get("metadata"), Mapping) else {},
        item_catalog=item_catalog or ITEM_CATALOG,
    )
    state.active_connection = {
        "status": "shell_connected",
        "target_ref": dict(preflight.get("target_ref") or {}),
        "target_identity": str(preflight.get("target_identity", "") or ""),
        "target_property_id": str(preflight.get("target_property_id", "") or ""),
        "target_entity_id": preflight.get("target_entity_id"),
        "target_stable_id": str((preflight.get("target_ref") or {}).get("stable_id", "") or ""),
        "target_name": preflight.get("target_name", ""),
        "target_class": preflight.get("target_class", ""),
        "linked_property_id": preflight.get("target_status", {}).get("linked_property_id", ""),
        "interface_instance_id": str(interface.get("instance_id", "") or ""),
        "interface_item_id": str(interface.get("item_id", "") or ""),
        "deliberate": bool(deliberate),
        "connected_tick": int(getattr(sim, "tick", 0)),
    }
    state.connection_status = "shell_connected"
    state.last_wire_feedback = f"Connected to {preflight.get('target_name', 'fixture')} shell."
    sim.emit(Event(
        "wire_connection_connected",
        eid=actor_eid,
        property_id=preflight.get("target_property_id") or None,
        target_entity_id=preflight.get("target_entity_id"),
        target_identity=preflight.get("target_identity"),
        target_class=preflight.get("target_class"),
        interface_instance_id=interface.get("instance_id"),
    ))
    return {"ok": True, "reason": None, "preflight": preflight, "connection": dict(state.active_connection)}


def disconnect_wire_connection(sim, actor_eid, *, reason="manual"):
    state = wire_state_for_actor(sim, actor_eid, create=False)
    if state is None:
        return {"ok": False, "reason": "missing_wire_state"}
    had_connection = isinstance(getattr(state, "active_connection", None), Mapping)
    state.active_connection = None
    state.active_scene = None
    state.connection_status = "offline"
    state.last_wire_feedback = "Disconnected." if had_connection else "No active wire connection."
    scene_ui = getattr(sim, "wire_scene_ui", None)
    if isinstance(scene_ui, dict):
        scene_ui["open"] = False
    if had_connection:
        sim.emit(Event("wire_connection_disconnected", eid=actor_eid, reason=reason))
    return {"ok": True, "reason": None, "had_connection": had_connection}


def active_wire_connection_stale(sim, actor_eid):
    state = wire_state_for_actor(sim, actor_eid, create=False)
    active = getattr(state, "active_connection", None) if state is not None else None
    if not isinstance(active, Mapping):
        return False
    target = resolve_wire_target(sim, wire_target_ref_from_connection(active))
    if not isinstance(target, Mapping):
        return True
    selected = select_wire_interface_record(
        sim,
        actor_eid,
        str(active.get("target_class", "") or ""),
        preferred_instance_id=active.get("interface_instance_id"),
        item_catalog=ITEM_CATALOG,
    )
    if not _reachable_target(sim, actor_eid, target, selected):
        return True
    if target.get("kind") == "drone" and not wire_target_has_live_radio(target, tick=int(getattr(sim, "tick", 0) or 0)):
        return True
    return False
