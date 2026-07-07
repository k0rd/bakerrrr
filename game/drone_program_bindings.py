"""Symbolic binding choices and resolution for drone procedure programs."""

from __future__ import annotations

import json

from engine.visibility import has_line_of_sight

from game.components import ContactLedger, CreatureIdentity, Position, PropertyKnowledge, Vitality
from game.items import item_display_name
from game.location_presentation_runtime import _build_known_locations_report, _build_known_people_report


DRONE_PROGRAM_SLOT_TYPES = (
    "SITE",
    "AREA",
    "TARGET",
    "PERSON",
    "ITEM_TYPE",
    "ROUTE",
    "RETURN_TO",
)


def _clean(value, default=""):
    text = str(value or "").strip()
    return text if text else str(default or "").strip()


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _slot(value):
    return _clean(value).upper().replace("-", "_").replace(" ", "_")


def _position_tuple(value):
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    try:
        return (int(value[0]), int(value[1]), int(value[2]))
    except (TypeError, ValueError):
        return None


def _property_anchor(prop):
    if not isinstance(prop, dict):
        return None
    for keys in (("x", "y", "z"), ("center_x", "center_y", "z")):
        if all(key in prop for key in keys):
            return (_int(prop.get(keys[0])), _int(prop.get(keys[1])), _int(prop.get(keys[2])))
    return None


def _known_property(sim, player_eid, property_id):
    property_id = _clean(property_id)
    if not property_id:
        return None, None
    knowledge = sim.ecs.get(PropertyKnowledge).get(player_eid)
    known = knowledge.property_entry(property_id) if knowledge is not None else None
    prop = getattr(sim, "properties", {}).get(property_id)
    if not isinstance(known, dict) or not isinstance(prop, dict):
        return None, None
    return prop, known


def _known_person_entry(sim, player_eid, person_eid):
    ledger = sim.ecs.get(ContactLedger).get(player_eid)
    entry = ledger.person_entry(person_eid) if ledger is not None else None
    if not isinstance(entry, dict):
        return None
    if not bool(entry.get("met_directly")) and not bool(entry.get("introduced")):
        return None
    return entry


def _visible_to_player(sim, player_eid, target_eid):
    positions = sim.ecs.get(Position)
    player_pos = positions.get(player_eid)
    target_pos = positions.get(target_eid)
    if player_pos is None or target_pos is None:
        return False
    if int(player_pos.z) != int(target_pos.z):
        return False
    visible = getattr(sim, "visibility_state", {}).get("player_visible", set())
    if (int(target_pos.x), int(target_pos.y), int(target_pos.z)) in visible:
        return True
    distance = abs(int(player_pos.x) - int(target_pos.x)) + abs(int(player_pos.y) - int(target_pos.y))
    if distance > 10:
        return False
    return has_line_of_sight(sim, int(player_pos.x), int(player_pos.y), int(player_pos.z), int(target_pos.x), int(target_pos.y), int(target_pos.z))


def _entity_label(sim, eid, *, fallback="actor"):
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    if identity is not None:
        return _clean(identity.common_name or identity.creature_type or identity.descriptive_name(), fallback)
    return f"{fallback} #{eid}"


def describe_program_binding(binding):
    if isinstance(binding, dict):
        label = _clean(binding.get("label"))
        if label:
            return label
        kind = _clean(binding.get("kind"), "binding").lower()
        if kind in {"position", "site", "area", "return_to", "known_location"}:
            pos = _position_tuple(binding.get("target") or binding.get("position"))
            if pos:
                return f"{kind.replace('_', ' ')} {pos[0]},{pos[1]},{pos[2]}"
        if kind in {"entity", "person", "target", "known_person"}:
            return f"{kind.replace('_', ' ')} #{binding.get('eid') or binding.get('person_eid') or '?'}"
        if kind == "item_type":
            return _clean(binding.get("item_id") or binding.get("item_type"), "item type")
        if kind == "route":
            points = tuple(binding.get("points", ()) or ())
            return f"route {len(points)} point{'s' if len(points) != 1 else ''}"
        return kind or "binding"
    return _clean(binding, "unbound")


def default_program_bindings(sim, controller_eid, drone_eid, state, program):
    bindings = {}
    slots = tuple((program or {}).get("slots", ()) or ())
    home = _position_tuple(getattr(state, "home", None))
    positions = sim.ecs.get(Position)
    drone_pos = positions.get(drone_eid)
    controller_pos = positions.get(controller_eid)
    if "RETURN_TO" in slots and home:
        bindings["RETURN_TO"] = {"kind": "return_to", "target": home, "label": "drone home"}
    if "AREA" in slots and home:
        bindings["AREA"] = {"kind": "area", "target": home, "label": "drone home area"}
    if "SITE" in slots and home:
        bindings["SITE"] = {"kind": "site", "target": home, "label": "drone home site"}
    if "PERSON" in slots and controller_eid is not None:
        bindings["PERSON"] = {"kind": "person", "eid": controller_eid, "label": "operator"}
    if "TARGET" in slots and getattr(state, "target_eid", None) is not None:
        bindings["TARGET"] = {"kind": "target", "eid": getattr(state, "target_eid"), "label": "current target"}
    if "ITEM_TYPE" in slots:
        bindings["ITEM_TYPE"] = {"kind": "item_type", "item_id": "any", "label": "any item"}
    if "ROUTE" in slots:
        origin = _position_tuple((getattr(drone_pos, "x", None), getattr(drone_pos, "y", None), getattr(drone_pos, "z", None))) if drone_pos is not None else home
        if origin is not None:
            x, y, z = origin
            bindings["ROUTE"] = {
                "kind": "route",
                "points": ((x, y, z), (x + 1, y, z), (x + 1, y + 1, z), (x, y + 1, z)),
                "label": "small loop from drone",
            }
        elif controller_pos is not None:
            x, y, z = int(controller_pos.x), int(controller_pos.y), int(controller_pos.z)
            bindings["ROUTE"] = {"kind": "route", "points": ((x, y, z),), "label": "operator point"}
    return bindings


def resolve_program_binding(sim, controller_eid, state, slot_key, bindings=None):
    slot_key = _slot(slot_key)
    binding = (bindings or {}).get(slot_key) if isinstance(bindings, dict) else None
    if binding is None:
        return {"ok": False, "reason": "missing_binding", "slot": slot_key}
    if not isinstance(binding, dict):
        if slot_key == "ITEM_TYPE":
            return {"ok": True, "kind": "item_type", "item_id": _clean(binding).lower() or "any", "slot": slot_key}
        return {"ok": False, "reason": "invalid_binding", "slot": slot_key}

    kind = _clean(binding.get("kind")).lower()
    controller_pos = sim.ecs.get(Position).get(controller_eid)
    if kind in {"position", "site", "area", "return_to"}:
        target = _position_tuple(binding.get("target") or binding.get("position"))
        if target is None:
            return {"ok": False, "reason": "stale_binding", "slot": slot_key}
        if controller_pos is not None and int(controller_pos.z) != int(target[2]):
            return {"ok": False, "reason": "wrong_floor", "slot": slot_key}
        return {"ok": True, "kind": "position", "target": target, "slot": slot_key, "label": describe_program_binding(binding)}
    if kind == "known_location":
        property_id = _clean(binding.get("property_id"))
        prop, _known = _known_property(sim, controller_eid, property_id)
        if prop is None:
            return {"ok": False, "reason": "unknown_binding", "slot": slot_key}
        target = _property_anchor(prop)
        if target is None:
            return {"ok": False, "reason": "stale_binding", "slot": slot_key}
        if controller_pos is not None and int(controller_pos.z) != int(target[2]):
            return {"ok": False, "reason": "wrong_floor", "slot": slot_key}
        return {"ok": True, "kind": "position", "target": target, "slot": slot_key, "property_id": property_id, "label": describe_program_binding(binding)}
    if kind in {"entity", "person", "target"}:
        eid = binding.get("eid")
        pos = sim.ecs.get(Position).get(eid)
        if pos is None:
            return {"ok": False, "reason": "stale_binding", "slot": slot_key}
        if controller_pos is not None and int(controller_pos.z) != int(pos.z):
            return {"ok": False, "reason": "wrong_floor", "slot": slot_key}
        return {"ok": True, "kind": "entity", "eid": eid, "target": (int(pos.x), int(pos.y), int(pos.z)), "slot": slot_key, "label": describe_program_binding(binding)}
    if kind == "known_person":
        person_eid = binding.get("person_eid", binding.get("eid"))
        if _known_person_entry(sim, controller_eid, person_eid) is None:
            return {"ok": False, "reason": "unknown_binding", "slot": slot_key}
        pos = sim.ecs.get(Position).get(person_eid)
        if pos is None:
            return {"ok": False, "reason": "stale_binding", "slot": slot_key}
        if controller_pos is not None and int(controller_pos.z) != int(pos.z):
            return {"ok": False, "reason": "wrong_floor", "slot": slot_key}
        return {"ok": True, "kind": "entity", "eid": person_eid, "target": (int(pos.x), int(pos.y), int(pos.z)), "slot": slot_key, "label": describe_program_binding(binding)}
    if kind == "item_type":
        item_id = _clean(binding.get("item_id") or binding.get("item_type")).lower() or "any"
        return {"ok": True, "kind": "item_type", "item_id": item_id, "slot": slot_key, "label": describe_program_binding(binding)}
    if kind == "route":
        points = []
        for point in tuple(binding.get("points", ()) or ()):
            pos = _position_tuple(point)
            if pos is not None:
                points.append(pos)
        if not points:
            return {"ok": False, "reason": "stale_binding", "slot": slot_key}
        if controller_pos is not None:
            floor = int(controller_pos.z)
            if any(int(point[2]) != floor for point in points):
                return {"ok": False, "reason": "wrong_floor", "slot": slot_key}
        return {"ok": True, "kind": "route", "points": tuple(points), "target": points[0], "slot": slot_key, "label": describe_program_binding(binding)}
    return {"ok": False, "reason": "invalid_binding", "slot": slot_key}


def _location_choices(sim, player_eid):
    report = _build_known_locations_report(sim, player_eid, include_hidden=False)
    rows = []
    for row in tuple((report or {}).get("rows", ()) or ()):
        property_id = _clean(row.get("property_id"))
        prop, _known = _known_property(sim, player_eid, property_id)
        target = _property_anchor(prop)
        if not property_id or target is None:
            continue
        name = _clean(row.get("name") or row.get("legend_line"), property_id)
        rows.append({
            "label": f"Known location: {name}",
            "binding": {"kind": "known_location", "property_id": property_id, "label": name},
        })
    return rows


def _person_choices(sim, player_eid):
    report = _build_known_people_report(sim, player_eid)
    rows = []
    for row in tuple((report or {}).get("rows", ()) or ()):
        person_eid = row.get("person_eid")
        if _known_person_entry(sim, player_eid, person_eid) is None:
            continue
        name = _clean(row.get("name") or row.get("appearance_summary"), f"person #{person_eid}")
        rows.append({
            "label": f"Known person: {name}",
            "binding": {"kind": "known_person", "person_eid": person_eid, "label": name},
        })
    return rows


def _visible_actor_choices(sim, player_eid):
    rows = []
    for eid, pos in sim.ecs.get(Position).items():
        if eid == player_eid:
            continue
        if sim.ecs.get(Vitality).get(eid) is None and sim.ecs.get(CreatureIdentity).get(eid) is None:
            continue
        if not _visible_to_player(sim, player_eid, eid):
            continue
        rows.append({
            "label": f"Visible actor: {_entity_label(sim, eid)} #{eid}",
            "binding": {"kind": "entity", "eid": eid, "label": _entity_label(sim, eid)},
        })
    rows.sort(key=lambda row: str(row.get("label", "")).lower())
    return rows


def _item_type_choices(sim, player_eid, *, item_catalog=None):
    del player_eid
    rows = [{"label": "Any item", "binding": {"kind": "item_type", "item_id": "any", "label": "any item"}}]
    seen = {"any"}
    visible = getattr(sim, "visibility_state", {}).get("player_visible", set())
    for ground in tuple(getattr(sim, "ground_items", {}).values()):
        if not isinstance(ground, dict):
            continue
        pos = (_int(ground.get("x")), _int(ground.get("y")), _int(ground.get("z")))
        if visible and pos not in visible:
            continue
        item_id = _clean(ground.get("item_id")).lower()
        if not item_id or item_id in seen:
            continue
        seen.add(item_id)
        rows.append({"label": f"Visible item type: {item_display_name(item_id, item_catalog=item_catalog)}", "binding": {"kind": "item_type", "item_id": item_id, "label": item_display_name(item_id, item_catalog=item_catalog)}})
    rows.sort(key=lambda row: str(row.get("label", "")).lower())
    return rows


def _position_choices(sim, player_eid, drone_eid, state):
    rows = []
    positions = sim.ecs.get(Position)
    for label, eid in (("Operator position", player_eid), ("Drone position", drone_eid)):
        pos = positions.get(eid)
        if pos is None:
            continue
        target = (int(pos.x), int(pos.y), int(pos.z))
        rows.append({"label": label, "binding": {"kind": "position", "target": target, "label": label.lower()}})
    home = _position_tuple(getattr(state, "home", None))
    if home is not None:
        rows.append({"label": "Drone home", "binding": {"kind": "return_to", "target": home, "label": "drone home"}})
    return rows


def _route_choices(sim, player_eid, drone_eid, state):
    choices = []
    positions = sim.ecs.get(Position)
    for label, eid in (("Small loop from drone", drone_eid), ("Small loop from operator", player_eid)):
        pos = positions.get(eid)
        if pos is None:
            continue
        x, y, z = int(pos.x), int(pos.y), int(pos.z)
        points = ((x, y, z), (x + 1, y, z), (x + 1, y + 1, z), (x, y + 1, z))
        choices.append({"label": label, "binding": {"kind": "route", "points": points, "label": label.lower()}})
    home = _position_tuple(getattr(state, "home", None))
    player_pos = positions.get(player_eid)
    if home is not None and player_pos is not None and int(player_pos.z) == int(home[2]):
        choices.append({
            "label": "Operator to drone home",
            "binding": {
                "kind": "route",
                "points": ((int(player_pos.x), int(player_pos.y), int(player_pos.z)), home),
                "label": "operator to drone home",
            },
        })
    return choices


def program_binding_choices(sim, player_eid, drone_eid, state, slot_key, *, item_catalog=None):
    slot_key = _slot(slot_key)
    if slot_key not in DRONE_PROGRAM_SLOT_TYPES:
        return ()
    rows = []
    if slot_key in {"SITE", "AREA", "RETURN_TO"}:
        rows.extend(_position_choices(sim, player_eid, drone_eid, state))
        rows.extend(_location_choices(sim, player_eid))
    elif slot_key in {"PERSON", "TARGET"}:
        rows.append({"label": "Operator", "binding": {"kind": "person", "eid": player_eid, "label": "operator"}})
        rows.extend(_person_choices(sim, player_eid))
        rows.extend(_visible_actor_choices(sim, player_eid))
        target_eid = getattr(state, "target_eid", None)
        if target_eid is not None:
            rows.append({"label": f"Current drone target: {_entity_label(sim, target_eid)}", "binding": {"kind": "target", "eid": target_eid, "label": "current drone target"}})
    elif slot_key == "ITEM_TYPE":
        rows.extend(_item_type_choices(sim, player_eid, item_catalog=item_catalog))
    elif slot_key == "ROUTE":
        rows.extend(_route_choices(sim, player_eid, drone_eid, state))
    deduped = []
    seen = set()
    for idx, row in enumerate(rows):
        binding = row.get("binding") if isinstance(row, dict) else None
        try:
            key = json.dumps(binding, sort_keys=True)
        except (TypeError, ValueError):
            key = repr(binding) if isinstance(binding, dict) else str(idx)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return tuple(deduped)
