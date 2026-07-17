"""Data-only drone procedure programs and one-step VM runtime."""

from __future__ import annotations

from engine.events import Event

from game.components import Inventory, NPCWill, Position, Vitality
from game.drone_program_bindings import (
    default_program_bindings,
    describe_program_binding,
    resolve_program_binding,
)
from game.drone_procedures import cardinal_step_toward
from game.drone_recon import apply_autonomous_mapping_knowledge, drone_has_mapping_sensor
from game.drone_runtime import drone_state_has_capability
from game.items import item_display_name, item_inventory_slot_cost
from game.skills import actor_skill


DRONE_PROGRAM_SCHEMA_VERSION = 1
DRONE_CUSTOM_PROCEDURE_MODULE_ID = "drone_custom_procedure_module"
BLANK_PROCEDURE_FLASH_ITEM_ID = "blank_procedure_flash"
DRONE_PROGRAMMER_ITEM_ID = "drone_programmer"

DRONE_PROGRAM_VERBS = (
    "HOLD",
    "WAIT",
    "FOLLOW",
    "RETURN_HOME",
    "GO_TO",
    "PATROL",
    "SCAN",
    "WATCH",
    "MAP",
    "SEEK_ITEM",
    "PICK_UP",
    "DROP",
    "REPORT",
    "DISTRACT",
    "DISABLE_ALARM",
    "FIRE_IF_ALLOWED",
    "EVADE",
    "STOP",
    "GOTO",
    "IF",
)

DRONE_PROGRAM_PREDICATES = (
    "LOW_BATTERY",
    "LOW_HULL",
    "AT SITE",
    "AT HOME",
    "FOUND TARGET",
    "FOUND ITEM_TYPE",
    "SEES_HOSTILE",
    "CARGO_FULL",
    "CARGO_EMPTY",
    "WEAPON_READY",
    "STEP_FAILED",
    "LAST_ACTION_OK",
)

DRONE_PROGRAM_SLOT_TYPES = (
    "SITE",
    "AREA",
    "TARGET",
    "PERSON",
    "ITEM_TYPE",
    "ROUTE",
    "RETURN_TO",
)

DRONE_PROGRAM_STEP_LIMIT_BY_CLASS = {
    "A": 4,
    "B": 8,
    "C": 8,
    "D": 10,
    "E": 12,
}

DANGEROUS_DRONE_PROGRAM_VERBS = {"FIRE_IF_ALLOWED", "DISABLE_ALARM"}
DRONE_CARGO_SLOTS_PER_MODULE = 4


def _clean(value, default=""):
    text = str(value or "").strip()
    return text if text else str(default or "").strip()


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _program_id(value):
    return _clean(value).lower().replace(" ", "_").replace("-", "_")


def _verb(value):
    text = _clean(value).upper().replace("-", "_")
    if text == "RETURN":
        return "RETURN_HOME"
    if text == "IF_GOTO":
        return "IF"
    return text


def _predicate(value):
    text = _clean(value).upper().replace("-", " ")
    text_space = text.replace("_", " ")
    aliases = {
        "AT SITE": "AT SITE",
        "AT HOME": "AT HOME",
        "FOUND TARGET": "FOUND TARGET",
        "FOUND ITEM TYPE": "FOUND ITEM_TYPE",
        "FOUND ITEM_TYPE": "FOUND ITEM_TYPE",
        "SEES HOSTILE": "SEES_HOSTILE",
        "CARGO FULL": "CARGO_FULL",
        "CARGO EMPTY": "CARGO_EMPTY",
        "WEAPON READY": "WEAPON_READY",
        "STEP FAILED": "STEP_FAILED",
        "LAST ACTION OK": "LAST_ACTION_OK",
        "LOW BATTERY": "LOW_BATTERY",
        "LOW HULL": "LOW_HULL",
    }
    return aliases.get(text_space, aliases.get(text, text_space))


def _slot(value):
    return _clean(value).upper().replace("-", "_").replace(" ", "_")


def _line_number(value, default=0):
    return int(max(0, _int(value, default)))


def _position_tuple(value):
    if not isinstance(value, (list, tuple)) or len(value) < 3:
        return None
    try:
        return (int(value[0]), int(value[1]), int(value[2]))
    except (TypeError, ValueError):
        return None


def _normalize_line(raw, fallback_line):
    if not isinstance(raw, dict):
        return None
    op = _verb(raw.get("op") or raw.get("verb"))
    if not op:
        return None
    line = _line_number(raw.get("line"), fallback_line)
    normalized = {
        "line": line,
        "op": op,
    }
    if raw.get("slot") is not None:
        normalized["slot"] = _slot(raw.get("slot"))
    if raw.get("slot_type") is not None:
        normalized["slot_type"] = _slot(raw.get("slot_type"))
    if raw.get("item_type") is not None:
        normalized["item_type"] = _clean(raw.get("item_type")).lower()
    if raw.get("target") is not None:
        normalized["target"] = raw.get("target")
    if raw.get("predicate") is not None:
        normalized["predicate"] = _predicate(raw.get("predicate"))
    if raw.get("goto") is not None:
        normalized["goto"] = _line_number(raw.get("goto"))
    if raw.get("args") is not None:
        args = raw.get("args")
        if isinstance(args, dict):
            normalized["args"] = dict(args)
        elif isinstance(args, (list, tuple)):
            normalized["args"] = tuple(args)
        else:
            normalized["args"] = args
    return normalized


def normalize_drone_program(program=None, *, program_id=None, label=None, max_steps=None):
    """Normalize a data-only procedure program without executing anything."""

    source = dict(program or {}) if isinstance(program, dict) else {}
    pid = _program_id(program_id or source.get("id") or source.get("program_id") or "custom")
    title = _clean(label or source.get("label") or pid.replace("_", " ").title(), "Procedure")
    declared_slots = []
    for raw_slot in tuple(source.get("slots", ()) or ()):
        slot_key = _slot(raw_slot)
        if slot_key and slot_key in DRONE_PROGRAM_SLOT_TYPES and slot_key not in declared_slots:
            declared_slots.append(slot_key)

    raw_lines = source.get("lines", ())
    lines = []
    if isinstance(raw_lines, (list, tuple)):
        for idx, raw_line in enumerate(raw_lines):
            line = _normalize_line(raw_line, (idx + 1) * 10)
            if line:
                lines.append(line)
    lines.sort(key=lambda row: int(row.get("line", 0) or 0))

    normalized = {
        "schema_version": DRONE_PROGRAM_SCHEMA_VERSION,
        "id": pid,
        "label": title,
        "slots": tuple(declared_slots),
        "lines": tuple(lines),
    }
    if max_steps is not None:
        normalized["max_steps"] = int(max(1, _int(max_steps, 1)))
    errors = validate_drone_program(normalized, max_steps=max_steps)
    normalized["errors"] = tuple(errors)
    return normalized


def validate_drone_program(program, *, max_steps=None):
    errors = []
    if not isinstance(program, dict):
        return ("program must be a mapping",)
    lines = tuple(program.get("lines", ()) or ())
    if not lines:
        errors.append("program requires at least one line")
        return tuple(errors)
    if max_steps is not None and len(lines) > int(max(1, _int(max_steps, 1))):
        errors.append(f"program length {len(lines)} exceeds limit {int(max_steps)}")
    seen = set()
    line_numbers = set()
    for line in lines:
        line_no = _line_number((line or {}).get("line"))
        if line_no <= 0:
            errors.append("program line requires a positive line number")
            continue
        if line_no in seen:
            errors.append(f"duplicate line {line_no}")
        seen.add(line_no)
        line_numbers.add(line_no)
    for line in lines:
        line_no = _line_number((line or {}).get("line"))
        op = _verb((line or {}).get("op"))
        if op not in DRONE_PROGRAM_VERBS:
            errors.append(f"line {line_no} uses unknown verb {op or '?'}")
            continue
        slot_key = _slot((line or {}).get("slot") or (line or {}).get("slot_type"))
        if slot_key and slot_key not in DRONE_PROGRAM_SLOT_TYPES:
            errors.append(f"line {line_no} uses invalid slot {slot_key}")
        if op == "GOTO":
            target = _line_number((line or {}).get("goto"))
            if target not in line_numbers:
                errors.append(f"line {line_no} jumps to missing line {target}")
        if op == "IF":
            pred = _predicate((line or {}).get("predicate"))
            target = _line_number((line or {}).get("goto"))
            if pred not in DRONE_PROGRAM_PREDICATES:
                errors.append(f"line {line_no} uses invalid predicate {pred or '?'}")
            if target not in line_numbers:
                errors.append(f"line {line_no} jumps to missing line {target}")
    return tuple(errors)


def render_drone_program_lines(program):
    program = normalize_drone_program(program)
    rendered = []
    for line in tuple(program.get("lines", ()) or ()):
        line_no = _line_number(line.get("line"))
        op = _verb(line.get("op"))
        if op == "GOTO":
            rendered.append(f"{line_no} GOTO {_line_number(line.get('goto'))}")
            continue
        if op == "IF":
            rendered.append(f"{line_no} IF {_predicate(line.get('predicate'))} GOTO {_line_number(line.get('goto'))}")
            continue
        slot_key = _slot(line.get("slot") or line.get("slot_type"))
        suffix = f" {slot_key}" if slot_key else ""
        item_type = _clean(line.get("item_type")).lower()
        if item_type:
            suffix = f" {item_type}"
        rendered.append(f"{line_no} {op}{suffix}")
    return tuple(rendered)


def _line_map(program):
    normalized = normalize_drone_program(program)
    return {int(line.get("line")): dict(line) for line in tuple(normalized.get("lines", ()) or ())}


def _first_line(program):
    lines = tuple(normalize_drone_program(program).get("lines", ()) or ())
    return int(lines[0].get("line", 10)) if lines else 10


def _next_line(program, current_line):
    lines = [int(line.get("line", 0) or 0) for line in tuple(normalize_drone_program(program).get("lines", ()) or ())]
    lines = [line for line in lines if line > 0]
    if not lines:
        return 10
    current = int(current_line or lines[0])
    for line in lines:
        if line > current:
            return line
    return lines[0]


def drone_program_step_limit(chassis_class):
    return int(DRONE_PROGRAM_STEP_LIMIT_BY_CLASS.get(_clean(chassis_class).upper(), 6))


def drone_program_limit_for_state(state):
    limit = drone_program_step_limit(getattr(state, "chassis_class", None))
    for module in tuple(getattr(state, "modules", ()) or ()):
        if not isinstance(module, dict):
            continue
        if _clean(module.get("item_id")).lower() != DRONE_CUSTOM_PROCEDURE_MODULE_ID:
            continue
        metadata = module.get("metadata") if isinstance(module.get("metadata"), dict) else {}
        if "max_steps" in metadata:
            limit = min(limit, int(max(1, _int(metadata.get("max_steps"), limit))))
    return limit


BUILT_IN_DRONE_PROGRAMS = {
    "follow_operator": {
        "id": "follow_operator",
        "label": "Follow Operator",
        "slots": (),
        "lines": (
            {"line": 10, "op": "FOLLOW"},
        ),
    },
    "return_home": {
        "id": "return_home",
        "label": "Return Home",
        "slots": ("RETURN_TO",),
        "lines": (
            {"line": 10, "op": "RETURN_HOME"},
            {"line": 20, "op": "IF", "predicate": "AT HOME", "goto": 40},
            {"line": 30, "op": "GOTO", "goto": 10},
            {"line": 40, "op": "STOP"},
        ),
    },
    "map_area_loop": {
        "id": "map_area_loop",
        "label": "Map Area Loop",
        "slots": ("AREA",),
        "lines": (
            {"line": 10, "op": "SCAN", "slot": "AREA"},
            {"line": 20, "op": "MAP", "slot": "AREA"},
            {"line": 30, "op": "GOTO", "goto": 10},
        ),
    },
    "patrol_route": {
        "id": "patrol_route",
        "label": "Patrol Route",
        "slots": ("ROUTE",),
        "lines": (
            {"line": 10, "op": "PATROL", "slot": "ROUTE"},
            {"line": 20, "op": "GOTO", "goto": 10},
        ),
    },
    "watch_person": {
        "id": "watch_person",
        "label": "Watch Person",
        "slots": ("PERSON",),
        "lines": (
            {"line": 10, "op": "WATCH", "slot": "PERSON"},
            {"line": 20, "op": "REPORT"},
            {"line": 30, "op": "GOTO", "goto": 10},
        ),
    },
    "guard_zone": {
        "id": "guard_zone",
        "label": "Guard Zone",
        "slots": ("AREA",),
        "lines": (
            {"line": 10, "op": "WATCH", "slot": "AREA"},
            {"line": 20, "op": "IF", "predicate": "SEES_HOSTILE", "goto": 50},
            {"line": 30, "op": "REPORT"},
            {"line": 40, "op": "GOTO", "goto": 10},
            {"line": 50, "op": "FIRE_IF_ALLOWED"},
            {"line": 60, "op": "GOTO", "goto": 10},
        ),
    },
    "distract": {
        "id": "distract",
        "label": "Distract",
        "slots": (),
        "lines": (
            {"line": 10, "op": "DISTRACT"},
            {"line": 20, "op": "STOP"},
        ),
    },
    "disable_alarm": {
        "id": "disable_alarm",
        "label": "Disable Alarm",
        "slots": (),
        "lines": (
            {"line": 10, "op": "DISABLE_ALARM"},
            {"line": 20, "op": "STOP"},
        ),
    },
    "protect_operator": {
        "id": "protect_operator",
        "label": "Protect Operator",
        "slots": ("PERSON",),
        "lines": (
            {"line": 10, "op": "FOLLOW"},
            {"line": 20, "op": "WATCH", "slot": "PERSON"},
            {"line": 30, "op": "IF", "predicate": "SEES_HOSTILE", "goto": 50},
            {"line": 40, "op": "GOTO", "goto": 10},
            {"line": 50, "op": "FIRE_IF_ALLOWED"},
            {"line": 60, "op": "GOTO", "goto": 10},
        ),
    },
    "seek_item_and_return": {
        "id": "seek_item_and_return",
        "label": "Seek Item And Return",
        "slots": ("ITEM_TYPE", "RETURN_TO"),
        "lines": (
            {"line": 10, "op": "SEEK_ITEM", "slot": "ITEM_TYPE"},
            {"line": 20, "op": "IF", "predicate": "FOUND ITEM_TYPE", "goto": 40},
            {"line": 30, "op": "GOTO", "goto": 10},
            {"line": 40, "op": "PICK_UP", "slot": "ITEM_TYPE"},
            {"line": 50, "op": "RETURN_HOME"},
            {"line": 60, "op": "IF", "predicate": "AT HOME", "goto": 80},
            {"line": 70, "op": "GOTO", "goto": 50},
            {"line": 80, "op": "DROP"},
        ),
    },
}


def built_in_drone_program(program_id):
    program = BUILT_IN_DRONE_PROGRAMS.get(_program_id(program_id))
    return normalize_drone_program(program) if program else None


def built_in_drone_programs():
    return tuple(normalize_drone_program(program) for program in BUILT_IN_DRONE_PROGRAMS.values())


def drone_program_uses_dangerous_verbs(program):
    for line in tuple(normalize_drone_program(program).get("lines", ()) or ()):
        if _verb(line.get("op")) in DANGEROUS_DRONE_PROGRAM_VERBS:
            return True
    return False


def _module_item_ids(state):
    return {
        _clean(module.get("item_id")).lower()
        for module in tuple(getattr(state, "modules", ()) or ())
        if isinstance(module, dict)
    }


def installed_drone_program_cards(state, *, include_all=False):
    """Return routine cards exposed by installed procedure modules."""

    module_ids = _module_item_ids(state)
    cards = []
    if include_all or "drone_follow_procedure_module" in module_ids:
        cards.extend([
            built_in_drone_program("follow_operator"),
            built_in_drone_program("return_home"),
            built_in_drone_program("protect_operator"),
        ])
    if include_all or "drone_mapping_procedure_module" in module_ids:
        cards.extend([
            built_in_drone_program("map_area_loop"),
            built_in_drone_program("patrol_route"),
        ])
    if include_all or ({"drone_mapping_procedure_module", "drone_follow_procedure_module"} & module_ids):
        cards.extend([
            built_in_drone_program("guard_zone"),
            built_in_drone_program("watch_person"),
            built_in_drone_program("seek_item_and_return"),
        ])
    if include_all or "drone_speaker_module" in module_ids:
        cards.append(built_in_drone_program("distract"))
    if include_all or "drone_alarm_probe_module" in module_ids:
        cards.append(built_in_drone_program("disable_alarm"))
    for module in tuple(getattr(state, "modules", ()) or ()):
        if not isinstance(module, dict):
            continue
        if _clean(module.get("item_id")).lower() != DRONE_CUSTOM_PROCEDURE_MODULE_ID:
            continue
        metadata = module.get("metadata") if isinstance(module.get("metadata"), dict) else {}
        custom = normalize_drone_program(metadata.get("drone_program"), max_steps=metadata.get("max_steps"))
        if custom.get("lines"):
            cards.append(custom)
    unique = {}
    for card in cards:
        if isinstance(card, dict):
            unique[_program_id(card.get("id"))] = card
    return tuple(unique.values())


def active_drone_program(state):
    program = getattr(state, "procedure_program", None)
    if not isinstance(program, dict):
        return None
    normalized = normalize_drone_program(program)
    return normalized if normalized.get("lines") else None


def drone_program_status_lines(state):
    program = active_drone_program(state)
    status = _clean(getattr(state, "procedure_status", None), "idle")
    current = _line_number(getattr(state, "procedure_pc", None), _first_line(program or {})) if program else 0
    label = _clean((program or {}).get("label"), "No active routine") if program else "No active routine"
    lines = [f"Routine: {label}", f"Status: {status}"]
    if program:
        lines.append(f"Current line: {current}")
    reason = _clean(getattr(state, "procedure_last_reason", None))
    if reason:
        lines.append(f"Last block: {reason.replace('_', ' ')}")
    bindings = getattr(state, "procedure_bindings", None)
    if isinstance(bindings, dict) and bindings:
        for key in sorted(bindings):
            lines.append(f"{key}: {describe_program_binding(bindings.get(key))}")
    return tuple(lines)


def activate_drone_program(state, program, *, bindings=None, controller_eid=None, drone_eid=None, sim=None):
    program = normalize_drone_program(program, max_steps=drone_program_limit_for_state(state))
    if program.get("errors"):
        return {"ok": False, "reason": "invalid_program", "errors": tuple(program.get("errors", ()))}
    if bindings is None and sim is not None:
        bindings = default_program_bindings(sim, controller_eid, drone_eid, state, program)
    state.procedure_program_id = program.get("id")
    state.procedure_program = {key: value for key, value in program.items() if key != "errors"}
    state.procedure_bindings = dict(bindings or {})
    state.procedure_pc = _first_line(program)
    state.procedure_status = "running"
    state.procedure_last_result = None
    state.procedure_last_reason = None
    state.procedure_last_tick = None
    state.procedure_key = program.get("id")
    state.last_command = "program"
    sync_drone_program_metadata(state)
    return {"ok": True, "reason": None, "program": dict(state.procedure_program)}


def stop_drone_program(state, *, reason="stopped"):
    state.procedure_status = "stopped"
    state.procedure_last_result = "stopped"
    state.procedure_last_reason = _clean(reason, "stopped").lower()
    state.procedure_key = None
    sync_drone_program_metadata(state)
    return {"ok": True, "reason": None}


def sync_drone_program_metadata(state):
    metadata = getattr(state, "source_metadata", None)
    if not isinstance(metadata, dict):
        metadata = {}
        state.source_metadata = metadata
    for attr in (
        "procedure_program_id",
        "procedure_program",
        "procedure_bindings",
        "procedure_pc",
        "procedure_status",
        "procedure_last_result",
        "procedure_last_reason",
        "procedure_last_tick",
    ):
        value = getattr(state, attr, None)
        if value is None:
            metadata.pop(attr, None)
        else:
            metadata[attr] = value


def _set_program_result(state, *, ok, reason=None, tick=0):
    state.procedure_last_result = "ok" if ok else "blocked"
    state.procedure_last_reason = None if ok else (_clean(reason, "blocked").lower() or "blocked")
    state.procedure_last_tick = int(tick or 0)
    sync_drone_program_metadata(state)


def _has_cargo_module(state):
    return drone_state_has_capability(state, "cargo")


def _cargo_capacity(state):
    count = 0
    for module in tuple(getattr(state, "modules", ()) or ()):
        if isinstance(module, dict) and _clean(module.get("item_id")).lower() == "drone_cargo_clamp_module":
            count += 1
    return count * DRONE_CARGO_SLOTS_PER_MODULE


def _cargo_used(state):
    return sum(item_inventory_slot_cost(entry) for entry in tuple(getattr(state, "cargo", ()) or ()) if isinstance(entry, dict))


def _item_type_for_line(sim, controller_eid, state, line):
    item_type = _clean(line.get("item_type")).lower()
    if item_type:
        return item_type
    slot_key = _slot(line.get("slot") or "ITEM_TYPE")
    resolved = resolve_program_binding(sim, controller_eid, state, slot_key, getattr(state, "procedure_bindings", None))
    if not resolved.get("ok"):
        return None
    return _clean(resolved.get("item_id"), "any").lower() or "any"


def _find_item_near(sim, pos, item_type, *, radius=6):
    if pos is None:
        return None
    matches = []
    for ground in tuple(sim.ground_items_in_radius(int(pos.x), int(pos.y), int(pos.z), r=radius)):
        if not isinstance(ground, dict):
            continue
        if item_type not in {"", "any"} and _clean(ground.get("item_id")).lower() != item_type:
            continue
        gx, gy, gz = _int(ground.get("x")), _int(ground.get("y")), _int(ground.get("z"))
        dist = abs(gx - int(pos.x)) + abs(gy - int(pos.y))
        matches.append((dist, str(ground.get("ground_item_id", "")), ground))
    matches.sort(key=lambda row: (row[0], row[1]))
    return matches[0][2] if matches else None


def _move_toward(drone_system, controller_eid, drone_eid, state, target):
    pos = drone_system.sim.ecs.get(Position).get(drone_eid)
    target = _position_tuple(target)
    if pos is None:
        return {"ok": False, "reason": "missing_position"}
    if target is None:
        return {"ok": False, "reason": "missing_target"}
    if int(pos.z) != int(target[2]):
        return {"ok": False, "reason": "wrong_floor"}
    if (int(pos.x), int(pos.y), int(pos.z)) == target:
        state.target = target
        return {"ok": True, "reason": None, "action": "arrived"}
    step = cardinal_step_toward((int(pos.x), int(pos.y)), target)
    if step is None:
        return {"ok": False, "reason": "no_step"}
    return drone_system.move_drone(controller_eid, drone_eid, step[0], step[1])


def _nearest_alarm_fixture(sim, pos, *, radius=1):
    if pos is None:
        return None
    matches = []
    for prop in tuple(getattr(sim, "properties", {}).values()):
        if not isinstance(prop, dict):
            continue
        metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
        role = _clean(metadata.get("interaction_role") or prop.get("interaction_role")).lower()
        fixture_type = _clean(metadata.get("fixture_type") or prop.get("fixture_type") or prop.get("archetype")).lower()
        if role != "alarm_target" and "alarm" not in fixture_type:
            continue
        target = _position_tuple((prop.get("x"), prop.get("y"), prop.get("z", 0)))
        if target is None or int(target[2]) != int(pos.z):
            continue
        distance = abs(int(target[0]) - int(pos.x)) + abs(int(target[1]) - int(pos.y))
        if distance <= int(max(0, radius)):
            matches.append((distance, str(prop.get("id", "")), prop))
    matches.sort(key=lambda row: (row[0], row[1]))
    return matches[0][2] if matches else None


def _route_target_for_state(state, resolved):
    points = tuple(resolved.get("points", ()) or ())
    if not points:
        return None
    metadata = getattr(state, "source_metadata", None)
    if not isinstance(metadata, dict):
        metadata = {}
        state.source_metadata = metadata
    index = _int(metadata.get("program_route_index"), 0)
    index = index % len(points)
    target = _position_tuple(points[index])
    if target is None:
        return None
    return target


def _advance_route_if_arrived(state, resolved, pos):
    points = tuple(resolved.get("points", ()) or ())
    if not points or pos is None:
        return None
    metadata = getattr(state, "source_metadata", None)
    if not isinstance(metadata, dict):
        metadata = {}
        state.source_metadata = metadata
    index = _int(metadata.get("program_route_index"), 0) % len(points)
    target = _position_tuple(points[index])
    if target is not None and (int(pos.x), int(pos.y), int(pos.z)) == target:
        index = (index + 1) % len(points)
        metadata["program_route_index"] = index
    return _position_tuple(points[index])


def _hostile_target_near(sim, controller_eid, drone_eid, state, *, target_eid=None, target_pos=None, radius=8):
    positions = sim.ecs.get(Position)
    drone_pos = positions.get(drone_eid)
    if drone_pos is None:
        return None
    candidates = []
    if target_eid is not None:
        candidates.append(target_eid)
    state_target = getattr(state, "target_eid", None)
    if state_target is not None:
        candidates.append(state_target)
    for eid, will in sim.ecs.get(NPCWill).items():
        if eid in {controller_eid, drone_eid}:
            continue
        if getattr(will, "target_eid", None) in {controller_eid, getattr(state, "owner_eid", None)}:
            candidates.append(eid)
    seen = set()
    ranked = []
    excluded = {controller_eid, drone_eid, getattr(state, "owner_eid", None), getattr(state, "controller_eid", None)}
    for eid in candidates:
        if eid is None or eid in seen or eid in excluded:
            continue
        seen.add(eid)
        pos = positions.get(eid)
        if pos is None or int(pos.z) != int(drone_pos.z):
            continue
        if target_pos is not None:
            resolved_target = _position_tuple(target_pos)
            if resolved_target is not None and int(pos.z) == int(resolved_target[2]):
                if abs(int(pos.x) - int(resolved_target[0])) + abs(int(pos.y) - int(resolved_target[1])) > radius:
                    continue
        distance = abs(int(pos.x) - int(drone_pos.x)) + abs(int(pos.y) - int(drone_pos.y))
        if distance <= int(max(1, radius)):
            ranked.append((distance, eid))
    ranked.sort(key=lambda row: (row[0], row[1]))
    return ranked[0][1] if ranked else None


def _run_verb(drone_system, controller_eid, drone_eid, state, line):
    sim = drone_system.sim
    op = _verb(line.get("op"))
    pos = sim.ecs.get(Position).get(drone_eid)
    metadata = getattr(state, "source_metadata", None)
    if not isinstance(metadata, dict):
        metadata = {}
        state.source_metadata = metadata

    if op in {"HOLD", "WAIT"}:
        return {"ok": True, "reason": None, "action": op.lower()}
    if op == "FOLLOW":
        target_pos = sim.ecs.get(Position).get(getattr(state, "target_eid", None) or controller_eid)
        if target_pos is None:
            return {"ok": False, "reason": "missing_target"}
        target = (int(target_pos.x), int(target_pos.y), int(target_pos.z))
        state.target = target
        state.target_eid = getattr(state, "target_eid", None) or controller_eid
        if pos is not None and abs(int(pos.x) - target[0]) + abs(int(pos.y) - target[1]) <= 1 and int(pos.z) == target[2]:
            return {"ok": True, "reason": None, "action": "follow_hold"}
        return _move_toward(drone_system, controller_eid, drone_eid, state, target)
    if op == "RETURN_HOME":
        home = _position_tuple(getattr(state, "home", None))
        if home is None:
            resolved = resolve_program_binding(sim, controller_eid, state, "RETURN_TO", getattr(state, "procedure_bindings", None))
            home = resolved.get("target") if resolved.get("ok") else None
        if home is None:
            return {"ok": False, "reason": "missing_home"}
        state.target = home
        return _move_toward(drone_system, controller_eid, drone_eid, state, home)
    if op in {"GO_TO", "PATROL"}:
        slot_key = _slot(line.get("slot") or ("ROUTE" if op == "PATROL" else "SITE"))
        resolved = resolve_program_binding(sim, controller_eid, state, slot_key, getattr(state, "procedure_bindings", None))
        if not resolved.get("ok"):
            return {"ok": False, "reason": resolved.get("reason", "missing_binding")}
        target = resolved.get("target")
        if op == "PATROL" and resolved.get("kind") == "route":
            target = _advance_route_if_arrived(state, resolved, pos) or _route_target_for_state(state, resolved)
        return _move_toward(drone_system, controller_eid, drone_eid, state, target)
    if op in {"SCAN", "MAP"}:
        if not drone_has_mapping_sensor(state):
            return {"ok": False, "reason": "no_mapping_sensor"}
        result = apply_autonomous_mapping_knowledge(sim, controller_eid, drone_eid)
        if not result.get("ok"):
            return {"ok": False, "reason": result.get("reason", "blocked")}
        metadata["autonomous_mapping_last_visible"] = len(set(result.get("visible", set()) or set()))
        metadata["autonomous_mapping_last_learned"] = int(max(0, _int(result.get("learned_count"), 0)))
        return {"ok": True, "reason": None, "action": "map", "learned_count": metadata["autonomous_mapping_last_learned"]}
    if op == "WATCH":
        slot_key = _slot(line.get("slot") or "TARGET")
        resolved = resolve_program_binding(sim, controller_eid, state, slot_key, getattr(state, "procedure_bindings", None))
        target_eid = resolved.get("eid") if resolved.get("ok") and resolved.get("kind") == "entity" else getattr(state, "target_eid", None)
        target_pos = resolved.get("target") if resolved.get("ok") else None
        hostile = _hostile_target_near(
            sim,
            controller_eid,
            drone_eid,
            state,
            target_eid=target_eid,
            target_pos=target_pos,
            radius=int(max(6, getattr(state, "range_limit", 0) or 0)),
        )
        if hostile is not None:
            metadata["program_seen_hostile_eid"] = hostile
            state.target_eid = hostile
        else:
            metadata.pop("program_seen_hostile_eid", None)
        return {"ok": True, "reason": None, "action": "watch"}
    if op == "SEEK_ITEM":
        if not _has_cargo_module(state):
            return {"ok": False, "reason": "no_cargo_module"}
        item_type = _item_type_for_line(sim, controller_eid, state, line)
        if item_type is None:
            return {"ok": False, "reason": "missing_item_type"}
        ground = _find_item_near(sim, pos, item_type)
        if ground is None:
            metadata.pop("program_found_item_ground_id", None)
            metadata.pop("program_found_item_type", None)
            return {"ok": True, "reason": None, "action": "seek_item", "found": False}
        metadata["program_found_item_ground_id"] = str(ground.get("ground_item_id", ""))
        metadata["program_found_item_type"] = _clean(ground.get("item_id")).lower()
        target = (_int(ground.get("x")), _int(ground.get("y")), _int(ground.get("z")))
        state.target = target
        if pos is not None and (int(pos.x), int(pos.y), int(pos.z)) != target:
            return _move_toward(drone_system, controller_eid, drone_eid, state, target)
        return {"ok": True, "reason": None, "action": "seek_item", "found": True}
    if op == "PICK_UP":
        if not _has_cargo_module(state):
            return {"ok": False, "reason": "no_cargo_module"}
        capacity = _cargo_capacity(state)
        if capacity <= 0:
            return {"ok": False, "reason": "no_cargo_module"}
        item_type = _item_type_for_line(sim, controller_eid, state, line) or "any"
        if pos is None:
            return {"ok": False, "reason": "missing_position"}
        for ground in tuple(sim.ground_items_at(int(pos.x), int(pos.y), int(pos.z))):
            if item_type not in {"", "any"} and _clean(ground.get("item_id")).lower() != item_type:
                continue
            if _cargo_used(state) + item_inventory_slot_cost(ground) > capacity:
                return {"ok": False, "reason": "cargo_full"}
            removed = sim.remove_ground_item(ground.get("ground_item_id"))
            if removed is None:
                return {"ok": False, "reason": "item_unavailable"}
            state.cargo.append({
                "instance_id": str(removed.get("instance_id", "") or ""),
                "item_id": _clean(removed.get("item_id")).lower(),
                "quantity": int(max(1, _int(removed.get("quantity"), 1))),
                "owner_eid": removed.get("owner_eid"),
                "owner_tag": removed.get("owner_tag"),
                "metadata": dict(removed.get("metadata") or {}),
            })
            metadata["cargo"] = list(state.cargo)
            return {"ok": True, "reason": None, "action": "pick_up"}
        return {"ok": False, "reason": "item_unavailable"}
    if op == "DROP":
        if pos is None:
            return {"ok": False, "reason": "missing_position"}
        if not list(getattr(state, "cargo", ()) or ()):
            return {"ok": False, "reason": "cargo_empty"}
        item_type = _item_type_for_line(sim, controller_eid, state, line) or ""
        index = 0
        if item_type not in {"", "any"}:
            for idx, candidate in enumerate(tuple(getattr(state, "cargo", ()) or ())):
                if isinstance(candidate, dict) and _clean(candidate.get("item_id")).lower() == item_type:
                    index = idx
                    break
        entry = dict(state.cargo.pop(index))
        sim.register_ground_item(
            entry.get("item_id"),
            int(pos.x),
            int(pos.y),
            int(pos.z),
            quantity=int(max(1, _int(entry.get("quantity"), 1))),
            owner_eid=entry.get("owner_eid"),
            owner_tag=entry.get("owner_tag"),
            instance_id=entry.get("instance_id") or None,
            metadata=dict(entry.get("metadata") or {}),
        )
        metadata["cargo"] = list(state.cargo)
        return {"ok": True, "reason": None, "action": "drop"}
    if op == "REPORT":
        from game.drone_runtime import drone_link_disruption_status

        if drone_link_disruption_status(state, tick=int(getattr(sim, "tick", 0) or 0)).get("active"):
            return {"ok": False, "reason": "link_disrupted"}
        if not (drone_state_has_capability(state, "radio") or drone_state_has_capability(state, "comms")):
            return {"ok": False, "reason": "no_radio"}
        sim.emit(Event("drone_program_reported", eid=controller_eid, controller_eid=controller_eid, drone_eid=drone_eid))
        return {"ok": True, "reason": None, "action": "report"}
    if op == "DISTRACT":
        if not drone_state_has_capability(state, "speaker"):
            return {"ok": False, "reason": "no_speaker"}
        if pos is None:
            return {"ok": False, "reason": "missing_position"}
        sim.emit(Event(
            "noise",
            source_eid=drone_eid,
            x=int(pos.x),
            y=int(pos.y),
            z=int(pos.z),
            radius=6,
            cause="drone_distract",
        ))
        sim.emit(Event("drone_program_distracted", eid=controller_eid, controller_eid=controller_eid, drone_eid=drone_eid, x=int(pos.x), y=int(pos.y), z=int(pos.z)))
        return {"ok": True, "reason": None, "action": "distract"}
    if op == "DISABLE_ALARM":
        if not drone_state_has_capability(state, "alarm_probe"):
            return {"ok": False, "reason": "no_alarm_probe"}
        if pos is None:
            return {"ok": False, "reason": "missing_position"}
        prop = _nearest_alarm_fixture(sim, pos, radius=1)
        if not isinstance(prop, dict):
            return {"ok": False, "reason": "no_alarm_target"}
        prop_id = _clean(prop.get("id"))
        disabled = getattr(sim, "camera_disabled", None)
        if not isinstance(disabled, dict):
            sim.camera_disabled = {}
            disabled = sim.camera_disabled
        now = int(getattr(sim, "tick", 0) or 0)
        disabled_until = now + 150 + (int(getattr(sim, "seed", 0) or 0) % 40)
        disabled[prop_id] = disabled_until
        sim.emit(Event(
            "alarm_disabled",
            eid=controller_eid,
            source_eid=drone_eid,
            drone_eid=drone_eid,
            property_id=prop_id,
            disabled_until=disabled_until,
        ))
        sim.emit(Event(
            "drone_program_alarm_disabled",
            eid=controller_eid,
            controller_eid=controller_eid,
            drone_eid=drone_eid,
            property_id=prop_id,
            disabled_until=disabled_until,
        ))
        return {"ok": True, "reason": None, "action": "disable_alarm"}
    if op == "FIRE_IF_ALLOWED":
        target_eid = getattr(state, "target_eid", None) or metadata.get("program_seen_hostile_eid")
        if target_eid is None:
            return {"ok": False, "reason": "missing_target"}
        return drone_system.fire_drone_weapon(
            controller_eid,
            drone_eid,
            target_eid=target_eid,
            require_remote=False,
            require_camera=True,
            consume_turn=False,
        )
    if op == "EVADE":
        if pos is None:
            return {"ok": False, "reason": "missing_position"}
        for dx, dy in ((-1, 0), (0, -1), (1, 0), (0, 1)):
            result = drone_system.move_drone(controller_eid, drone_eid, dx, dy)
            if result.get("ok"):
                return result
        return {"ok": False, "reason": "no_step"}
    if op == "STOP":
        state.procedure_status = "stopped"
        return {"ok": True, "reason": None, "action": "stop"}
    return {"ok": False, "reason": "unknown_verb"}


def _predicate_value(sim, controller_eid, drone_eid, state, predicate):
    predicate = _predicate(predicate)
    pos = sim.ecs.get(Position).get(drone_eid)
    metadata = getattr(state, "source_metadata", {}) if isinstance(getattr(state, "source_metadata", None), dict) else {}
    if predicate == "LOW_BATTERY":
        maximum = int(max(1, _int(getattr(state, "battery_charge_max", 1), 1)))
        return int(getattr(state, "battery_charge", 0) or 0) <= max(2, maximum // 5)
    if predicate == "LOW_HULL":
        vitality = sim.ecs.get(Vitality).get(drone_eid)
        hp = _int(getattr(vitality, "hp", getattr(state, "hull_hp", 0)), 0)
        hp_max = int(max(1, _int(getattr(vitality, "max_hp", getattr(state, "hull_hp_max", 1)), 1)))
        return hp <= max(1, hp_max // 3)
    if predicate in {"AT SITE", "AT HOME"}:
        target = _position_tuple(getattr(state, "home", None))
        if predicate == "AT SITE":
            resolved = resolve_program_binding(sim, controller_eid, state, "SITE", getattr(state, "procedure_bindings", None))
            target = resolved.get("target") if resolved.get("ok") else target
        return pos is not None and target is not None and (int(pos.x), int(pos.y), int(pos.z)) == target
    if predicate == "FOUND TARGET":
        return bool(getattr(state, "target_eid", None) or metadata.get("program_seen_hostile_eid"))
    if predicate == "FOUND ITEM_TYPE":
        return bool(metadata.get("program_found_item_ground_id") or metadata.get("program_found_item_type"))
    if predicate == "SEES_HOSTILE":
        return bool(metadata.get("program_seen_hostile_eid"))
    if predicate == "CARGO_FULL":
        capacity = _cargo_capacity(state)
        return capacity > 0 and _cargo_used(state) >= capacity
    if predicate == "CARGO_EMPTY":
        return not bool(list(getattr(state, "cargo", ()) or ()))
    if predicate == "WEAPON_READY":
        from game.drone_combat import drone_weapon_status

        status = drone_weapon_status(state, tick=int(getattr(sim, "tick", 0) or 0))
        return bool(status.get("armed"))
    if predicate == "STEP_FAILED":
        return _clean(getattr(state, "procedure_last_result", None)) == "blocked"
    if predicate == "LAST_ACTION_OK":
        return _clean(getattr(state, "procedure_last_result", None)) == "ok"
    return False


def run_drone_program_step(drone_system, controller_eid, drone_eid, state):
    program = active_drone_program(state)
    if program is None:
        return {"ok": True, "reason": "no_program"}
    if _clean(getattr(state, "procedure_status", None)).lower() not in {"", "running", "blocked"}:
        return {"ok": True, "reason": "not_running", "program_id": program.get("id")}
    tick = int(getattr(drone_system.sim, "tick", 0) or 0)
    if getattr(state, "procedure_last_tick", None) == tick:
        return {"ok": True, "reason": "already_ran", "program_id": program.get("id")}
    errors = validate_drone_program(program, max_steps=drone_program_limit_for_state(state))
    if errors:
        state.procedure_status = "blocked"
        _set_program_result(state, ok=False, reason="invalid_program", tick=tick)
        return drone_system._procedure_blocked(controller_eid, drone_eid, state, program.get("id"), "invalid_program", errors=tuple(errors))

    pc = _line_number(getattr(state, "procedure_pc", None), _first_line(program))
    line = _line_map(program).get(pc)
    if line is None:
        pc = _first_line(program)
        line = _line_map(program).get(pc)
    op = _verb((line or {}).get("op"))
    if op == "GOTO":
        state.procedure_pc = _line_number(line.get("goto"), _first_line(program))
        state.procedure_status = "running"
        _set_program_result(state, ok=True, tick=tick)
        return drone_system._procedure_ran(controller_eid, drone_eid, state, program.get("id"), action="goto", line=pc, goto=state.procedure_pc)
    if op == "IF":
        taken = _predicate_value(drone_system.sim, controller_eid, drone_eid, state, line.get("predicate"))
        state.procedure_pc = _line_number(line.get("goto"), _first_line(program)) if taken else _next_line(program, pc)
        state.procedure_status = "running"
        _set_program_result(state, ok=True, tick=tick)
        return drone_system._procedure_ran(
            controller_eid,
            drone_eid,
            state,
            program.get("id"),
            action="if_goto",
            line=pc,
            predicate=_predicate(line.get("predicate")),
            taken=bool(taken),
            goto=state.procedure_pc,
        )

    result = _run_verb(drone_system, controller_eid, drone_eid, state, line)
    ok = bool(result.get("ok"))
    if ok:
        state.procedure_pc = _next_line(program, pc)
        if op == "STOP" or _clean(getattr(state, "procedure_status", None)).lower() == "stopped":
            state.procedure_status = "stopped"
        else:
            state.procedure_status = "running"
        _set_program_result(state, ok=True, tick=tick)
        return drone_system._procedure_ran(controller_eid, drone_eid, state, program.get("id"), action=result.get("action", op.lower()), line=pc)
    state.procedure_status = "blocked"
    _set_program_result(state, ok=False, reason=result.get("reason", "blocked"), tick=tick)
    return drone_system._procedure_blocked(controller_eid, drone_eid, state, program.get("id"), result.get("reason", "blocked"), line=pc)


def actor_can_author_drone_program(sim, actor_eid, program=None):
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    has_programmer = bool(inventory and inventory.find(item_id=DRONE_PROGRAMMER_ITEM_ID))
    if not has_programmer:
        return {"ok": False, "reason": "missing_programmer"}
    mechanics = float(actor_skill(sim, actor_eid, "mechanics", default=5.0))
    intrusion = float(actor_skill(sim, actor_eid, "intrusion", default=5.0))
    if max(mechanics, intrusion) < 6.0:
        return {"ok": False, "reason": "skill_too_low", "mechanics": mechanics, "intrusion": intrusion}
    if program is not None and drone_program_uses_dangerous_verbs(program) and intrusion < 7.0:
        return {"ok": False, "reason": "intrusion_too_low", "mechanics": mechanics, "intrusion": intrusion}
    return {"ok": True, "reason": None, "mechanics": mechanics, "intrusion": intrusion}


def write_custom_drone_program_module(sim, actor_eid, program, *, item_catalog=None, flash_instance_id=None):
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    if inventory is None:
        return {"ok": False, "reason": "missing_inventory"}
    program = normalize_drone_program(program)
    if program.get("errors"):
        return {"ok": False, "reason": "invalid_program", "errors": tuple(program.get("errors", ()))}
    gate = actor_can_author_drone_program(sim, actor_eid, program)
    if not gate.get("ok"):
        return gate
    flash = inventory.find(instance_id=flash_instance_id) if flash_instance_id else inventory.find(item_id=BLANK_PROCEDURE_FLASH_ITEM_ID)
    if flash is None:
        return {"ok": False, "reason": "missing_blank_flash"}
    item_def = (item_catalog or {}).get(DRONE_CUSTOM_PROCEDURE_MODULE_ID, {}) if isinstance(item_catalog, dict) else {}
    metadata = {
        "drone_program": {key: value for key, value in program.items() if key != "errors"},
        "display_name": f"Procedure: {program.get('label')}",
        "source_context": "player_authored_drone_program",
        "max_steps": int(max(1, len(program.get("lines", ()) or ()))),
    }
    removed = inventory.remove_item(instance_id=flash.get("instance_id"), quantity=1)
    if removed is None:
        return {"ok": False, "reason": "flash_remove_failed"}
    added, instance_id = inventory.add_item(
        DRONE_CUSTOM_PROCEDURE_MODULE_ID,
        quantity=1,
        stack_max=int(max(1, _int(item_def.get("stack_max"), 1))),
        instance_factory=getattr(sim, "new_item_instance_id", None),
        owner_eid=actor_eid,
        owner_tag="player" if getattr(sim, "player_eid", None) == actor_eid else None,
        metadata=metadata,
    )
    if not added:
        inventory.items.append(dict(removed))
        return {"ok": False, "reason": "inventory_full"}
    entry = inventory.find(instance_id=instance_id)
    sim.emit(Event(
        "drone_program_written",
        eid=actor_eid,
        controller_eid=actor_eid,
        program_id=program.get("id"),
        program_label=program.get("label"),
        item_name=item_display_name(DRONE_CUSTOM_PROCEDURE_MODULE_ID, metadata=metadata, item_catalog=item_catalog),
        instance_id=instance_id,
    ))
    return {"ok": True, "reason": None, "entry": dict(entry or {}), "program": program, "removed_flash": dict(removed)}


def drone_program_sheet_rows(sim, player_eid, record, *, item_catalog=None, editor_state=None):
    state = record.get("state") if isinstance(record, dict) else None
    if state is None:
        return [{"id": "empty", "label": "No drone selected.", "actionable": False}]
    if isinstance(editor_state, dict) and bool(editor_state.get("open")):
        from game.drone_program_editor import drone_program_editor_rows

        rows = list(drone_program_editor_rows(editor_state, sim, player_eid, record, item_catalog=item_catalog))
        if rows:
            return rows
    rows = []
    for idx, line in enumerate(drone_program_status_lines(state)):
        rows.append({"id": f"program_status:{idx}", "label": line, "actionable": False})
    active = active_drone_program(state)
    if active is not None and _clean(getattr(state, "procedure_status", None)).lower() in {"running", "blocked"}:
        rows.append({"id": "program:stop", "label": "Stop active routine", "action": "stop_program", "actionable": True})
    cards = installed_drone_program_cards(state)
    limit = drone_program_limit_for_state(state)
    rows.append({"id": "program:cards", "label": f"Installed routine cards ({len(cards)} available, {limit} line limit)", "actionable": False})
    for program in cards:
        errors = validate_drone_program(program, max_steps=limit)
        label = f"Activate: {program.get('label')}"
        if errors:
            label += f" | blocked: {', '.join(errors)}"
        rows.append({
            "id": f"program:activate:{program.get('id')}",
            "label": label,
            "action": "activate_program",
            "program_id": program.get("id"),
            "program": program,
            "actionable": not bool(errors),
        })
    inventory = sim.ecs.get(Inventory).get(player_eid)
    has_flash = bool(inventory and inventory.find(item_id=BLANK_PROCEDURE_FLASH_ITEM_ID))
    for program_id in ("follow_operator", "map_area_loop", "guard_zone", "seek_item_and_return"):
        program = built_in_drone_program(program_id)
        gate = actor_can_author_drone_program(sim, player_eid, program) if has_flash else {"ok": False, "reason": "missing_blank_flash"}
        rows.append({
            "id": f"program:write:{program_id}",
            "label": f"Write flash: {program.get('label')} ({'ready' if gate.get('ok') else str(gate.get('reason', 'blocked')).replace('_', ' ')})",
            "action": "write_program",
            "program_id": program_id,
            "program": program,
            "actionable": bool(gate.get("ok")),
        })
    from game.drone_program_editor import program_editor_entry_rows

    rows.extend(program_editor_entry_rows(sim, player_eid, record, item_catalog=item_catalog))
    return rows
