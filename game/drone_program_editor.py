"""Menu-driven editing helpers for data-only drone procedure programs."""

from __future__ import annotations

from game.components import Inventory
from game.drone_program_bindings import describe_program_binding, program_binding_choices
from game.drone_programs import (
    DRONE_CUSTOM_PROCEDURE_MODULE_ID,
    DRONE_PROGRAM_PREDICATES,
    DRONE_PROGRAM_SLOT_TYPES,
    DRONE_PROGRAM_VERBS,
    actor_can_author_drone_program,
    built_in_drone_programs,
    drone_program_limit_for_state,
    normalize_drone_program,
    render_drone_program_lines,
    write_custom_drone_program_module,
)
from game.drone_workshop import drone_workshop_entries, drone_workshop_for_actor
from game.items import item_display_name


EDITOR_ACTION_PREFIX = "program_editor:"

LINE_VERB_DEFAULTS = {
    "GO_TO": {"slot": "SITE"},
    "PATROL": {"slot": "ROUTE"},
    "SCAN": {"slot": "AREA"},
    "WATCH": {"slot": "PERSON"},
    "MAP": {"slot": "AREA"},
    "SEEK_ITEM": {"slot": "ITEM_TYPE"},
    "PICK_UP": {"slot": "ITEM_TYPE"},
    "DROP": {"slot": "ITEM_TYPE"},
    "RETURN_HOME": {"slot": "RETURN_TO"},
    "IF": {"predicate": "LOW_BATTERY"},
}

SLOT_VERBS = {"GO_TO", "PATROL", "SCAN", "WATCH", "MAP", "SEEK_ITEM", "PICK_UP", "DROP", "RETURN_HOME"}
GOTO_VERBS = {"GOTO", "IF"}


def _clean(value, default=""):
    text = str(value or "").strip()
    return text if text else str(default or "").strip()


def _program_id(value):
    return _clean(value).lower().replace(" ", "_").replace("-", "_")


def _verb(value):
    return _clean(value).upper().replace("-", "_")


def _slot(value):
    return _clean(value).upper().replace("-", "_").replace(" ", "_")


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _line_numbers(program):
    return tuple(_int(line.get("line"), 0) for line in tuple((program or {}).get("lines", ()) or ()) if _int(line.get("line"), 0) > 0)


def _renumber_lines(lines):
    normalized = []
    old_to_new = {}
    for idx, raw in enumerate(tuple(lines or ())):
        line = dict(raw or {})
        old = _int(line.get("line"), (idx + 1) * 10)
        new = (idx + 1) * 10
        old_to_new[old] = new
        line["line"] = new
        normalized.append(line)
    valid = {line["line"] for line in normalized}
    for line in normalized:
        if _verb(line.get("op")) in GOTO_VERBS:
            target = old_to_new.get(_int(line.get("goto")), _int(line.get("goto")))
            if target not in valid:
                target = normalized[0]["line"] if normalized else 10
            line["goto"] = target
    return tuple(normalized)


def _line_for_verb(verb, *, line_no=10, goto=None):
    verb = _verb(verb) or "WAIT"
    row = {"line": int(max(10, _int(line_no, 10))), "op": verb}
    row.update(LINE_VERB_DEFAULTS.get(verb, {}))
    if verb in GOTO_VERBS:
        row["goto"] = int(max(10, _int(goto, 10)))
    return row


def _normalize_draft(program, *, max_steps=None, label=None):
    source = dict(program or {})
    lines = _renumber_lines(tuple(source.get("lines", ()) or ({"line": 10, "op": "WAIT"}, {"line": 20, "op": "STOP"})))
    source["lines"] = lines
    if label is not None:
        source["label"] = _clean(label, "Custom Routine")
    return normalize_drone_program(source, max_steps=max_steps)


def _editor_open(editor_state):
    return isinstance(editor_state, dict) and bool(editor_state.get("open"))


def clear_program_editor(editor_state):
    if isinstance(editor_state, dict):
        editor_state.clear()
    return {"ok": True}


def start_program_editor(editor_state, program=None, *, source_kind="new", source_instance_id=None, source_index=None, label=None, max_steps=None):
    if not isinstance(editor_state, dict):
        editor_state = {}
    draft = _normalize_draft(program or {
        "id": "custom_routine",
        "label": label or "Custom Routine",
        "lines": ({"line": 10, "op": "WAIT"}, {"line": 20, "op": "STOP"}),
    }, max_steps=max_steps, label=label)
    editor_state.clear()
    editor_state.update({
        "open": True,
        "mode": "draft",
        "source_kind": _clean(source_kind, "new"),
        "source_instance_id": _clean(source_instance_id),
        "source_index": None if source_index is None else int(source_index),
        "draft": {key: value for key, value in draft.items() if key != "errors"},
        "bindings": {},
        "selected_line_index": 0,
        "feedback": "",
        "dirty": False,
    })
    return editor_state


def _current_line(editor_state):
    draft = normalize_drone_program((editor_state or {}).get("draft"))
    lines = list(draft.get("lines", ()) or ())
    if not lines:
        return None, -1, lines
    index = max(0, min(_int((editor_state or {}).get("selected_line_index"), 0), len(lines) - 1))
    editor_state["selected_line_index"] = index
    return dict(lines[index]), index, lines


def _set_draft_lines(editor_state, lines):
    draft = dict((editor_state or {}).get("draft") or {})
    draft["lines"] = _renumber_lines(lines)
    normalized = normalize_drone_program(draft)
    editor_state["draft"] = {key: value for key, value in normalized.items() if key != "errors"}
    editor_state["dirty"] = True
    return normalized


def _set_mode(editor_state, mode, **extra):
    editor_state["mode"] = mode
    for key, value in extra.items():
        editor_state[key] = value
    return {"ok": True}


def _custom_module_program_from_entry(entry):
    metadata = entry.get("metadata") if isinstance(entry, dict) and isinstance(entry.get("metadata"), dict) else {}
    return normalize_drone_program(metadata.get("drone_program"), max_steps=metadata.get("max_steps"))


def _custom_program_sources(sim, player_eid, record, *, item_catalog=None):
    rows = []
    state = record.get("state") if isinstance(record, dict) else None
    for index, module in enumerate(tuple(getattr(state, "modules", ()) or ())):
        if not isinstance(module, dict):
            continue
        if _clean(module.get("item_id")).lower() != DRONE_CUSTOM_PROCEDURE_MODULE_ID:
            continue
        program = _custom_module_program_from_entry(module)
        if program.get("lines"):
            rows.append({
                "source_kind": "installed",
                "source_index": index,
                "source_instance_id": _clean(module.get("source_instance_id")),
                "program": program,
            })
    inventory = sim.ecs.get(Inventory).get(player_eid)
    for entry in tuple(getattr(inventory, "items", ()) or ()):
        if not isinstance(entry, dict) or _clean(entry.get("item_id")).lower() != DRONE_CUSTOM_PROCEDURE_MODULE_ID:
            continue
        program = _custom_module_program_from_entry(entry)
        if program.get("lines"):
            rows.append({
                "source_kind": "backpack",
                "source_instance_id": _clean(entry.get("instance_id")),
                "program": program,
            })
    workshop = drone_workshop_for_actor(sim, player_eid, create=True, item_catalog=item_catalog)
    for entry in tuple(drone_workshop_entries(workshop, kind="module", item_catalog=item_catalog)):
        if not isinstance(entry, dict) or _clean(entry.get("item_id")).lower() != DRONE_CUSTOM_PROCEDURE_MODULE_ID:
            continue
        program = _custom_module_program_from_entry(entry)
        if program.get("lines"):
            rows.append({
                "source_kind": "workshop",
                "source_instance_id": _clean(entry.get("instance_id")),
                "program": program,
            })
    return tuple(rows)


def program_editor_entry_rows(sim, player_eid, record, *, item_catalog=None):
    rows = [{
        "id": "program_editor:section",
        "label": "Editor",
        "actionable": False,
    }, {
        "id": "program_editor:new",
        "label": "New custom routine from blank flash",
        "action": "program_editor:start_new",
        "actionable": True,
    }]
    for program in built_in_drone_programs():
        rows.append({
            "id": f"program_editor:copy:{program.get('id')}",
            "label": f"Copy built-in to editor: {program.get('label')}",
            "action": "program_editor:start_copy",
            "program": program,
            "actionable": True,
        })
    for source in _custom_program_sources(sim, player_eid, record, item_catalog=item_catalog):
        program = source.get("program") or {}
        rows.append({
            "id": f"program_editor:edit:{source.get('source_kind')}:{source.get('source_instance_id') or source.get('source_index')}",
            "label": f"Edit custom {source.get('source_kind')}: {program.get('label')}",
            "action": "program_editor:start_edit",
            "program": program,
            "source_kind": source.get("source_kind"),
            "source_instance_id": source.get("source_instance_id"),
            "source_index": source.get("source_index"),
            "actionable": True,
        })
    return rows


def _draft_rows(editor_state, sim, player_eid, record, *, item_catalog=None):
    state = record.get("state") if isinstance(record, dict) else None
    limit = drone_program_limit_for_state(state)
    draft = _normalize_draft((editor_state or {}).get("draft"), max_steps=limit)
    lines = tuple(draft.get("lines", ()) or ())
    errors = tuple(draft.get("errors", ()) or ())
    rows = [{
        "id": "program_editor:header",
        "label": f"Editing: {draft.get('label')} | {len(lines)}/{limit} lines | {'dirty' if editor_state.get('dirty') else 'saved draft'}",
        "actionable": False,
    }]
    if errors:
        rows.append({"id": "program_editor:errors", "label": "Blocks: " + "; ".join(errors), "actionable": False})
    rows.extend([
        {"id": "program_editor:save", "label": "Save custom procedure module", "action": "program_editor:save", "actionable": True},
        {"id": "program_editor:activate", "label": "Activate draft with current bindings", "action": "program_editor:activate", "actionable": not bool(errors)},
    ])
    slots = tuple(draft.get("slots", ()) or ())
    if slots:
        rows.append({"id": "program_editor:bindings", "label": "Bindings", "actionable": False})
        bindings = editor_state.get("bindings") if isinstance(editor_state.get("bindings"), dict) else {}
        for slot in slots:
            rows.append({
                "id": f"program_editor:bind:{slot}",
                "label": f"Bind {slot}: {describe_program_binding(bindings.get(slot))}",
                "action": "program_editor:choose_binding",
                "slot": slot,
                "actionable": True,
            })
    rows.append({"id": "program_editor:lines", "label": "Lines", "actionable": False})
    rendered = render_drone_program_lines(draft)
    selected = max(0, min(_int(editor_state.get("selected_line_index"), 0), max(0, len(lines) - 1)))
    for idx, text in enumerate(rendered):
        rows.append({
            "id": f"program_editor:line:{idx}",
            "label": f"{'* ' if idx == selected else ''}{text} | Enter edit",
            "action": "program_editor:open_line",
            "line_index": idx,
            "actionable": True,
        })
    rows.append({"id": "program_editor:append", "label": "Append WAIT line", "action": "program_editor:append_line", "actionable": len(lines) < limit})
    rows.append({"id": "program_editor:close", "label": "Close editor", "action": "program_editor:close", "actionable": True})
    return rows


def _line_menu_rows(editor_state):
    line, index, lines = _current_line(editor_state)
    if line is None:
        return [{"id": "program_editor:empty", "label": "No line selected.", "action": "program_editor:back", "actionable": True}]
    op = _verb(line.get("op"))
    rows = [{
        "id": "program_editor:line_header",
        "label": f"Line {line.get('line')}: {render_drone_program_lines({'lines': (line,)})[0]}",
        "actionable": False,
    }, {
        "id": "program_editor:choose_verb",
        "label": f"Verb: {op}",
        "action": "program_editor:choose_verb",
        "actionable": True,
    }]
    if op in SLOT_VERBS:
        rows.append({
            "id": "program_editor:choose_slot",
            "label": f"Slot: {_slot(line.get('slot') or LINE_VERB_DEFAULTS.get(op, {}).get('slot', '')) or '(none)'}",
            "action": "program_editor:choose_slot",
            "actionable": True,
        })
    if op == "IF":
        rows.append({
            "id": "program_editor:choose_predicate",
            "label": f"Predicate: {_clean(line.get('predicate'), 'LOW_BATTERY')}",
            "action": "program_editor:choose_predicate",
            "actionable": True,
        })
    if op in GOTO_VERBS:
        rows.append({
            "id": "program_editor:choose_goto",
            "label": f"Goto: {_int(line.get('goto'), lines[0].get('line') if lines else 10)}",
            "action": "program_editor:choose_goto",
            "actionable": True,
        })
    rows.extend([
        {"id": "program_editor:insert_after", "label": "Insert WAIT after this line", "action": "program_editor:insert_after", "actionable": True},
        {"id": "program_editor:move_up", "label": "Move line up", "action": "program_editor:move_up", "actionable": index > 0},
        {"id": "program_editor:move_down", "label": "Move line down", "action": "program_editor:move_down", "actionable": index < len(lines) - 1},
        {"id": "program_editor:delete", "label": "Delete line", "action": "program_editor:delete_line", "actionable": len(lines) > 1},
        {"id": "program_editor:back", "label": "Back to draft", "action": "program_editor:back", "actionable": True},
    ])
    return rows


def _choice_rows(editor_state, record, *, mode, choices):
    line, _index, _lines = _current_line(editor_state)
    header = {
        "choose_verb": "Choose verb",
        "choose_slot": "Choose slot",
        "choose_predicate": "Choose predicate",
        "choose_goto": "Choose GOTO target",
    }.get(mode, "Choose")
    rows = [{"id": "program_editor:choice_header", "label": header, "actionable": False}]
    for value in choices:
        rows.append({
            "id": f"program_editor:{mode}:{value}",
            "label": str(value),
            "action": f"program_editor:set_{mode.replace('choose_', '')}",
            "value": value,
            "actionable": True,
        })
    rows.append({"id": "program_editor:back", "label": "Back", "action": "program_editor:back", "actionable": True})
    del line, record
    return rows


def _binding_rows(editor_state, sim, player_eid, record, *, item_catalog=None):
    slot = _slot(editor_state.get("binding_slot"))
    state = record.get("state") if isinstance(record, dict) else None
    drone_eid = record.get("eid") if isinstance(record, dict) else None
    rows = [{"id": "program_editor:binding_header", "label": f"Bind {slot}", "actionable": False}]
    for idx, choice in enumerate(program_binding_choices(sim, player_eid, drone_eid, state, slot, item_catalog=item_catalog)):
        rows.append({
            "id": f"program_editor:binding:{idx}",
            "label": choice.get("label", describe_program_binding(choice.get("binding"))),
            "action": "program_editor:set_binding",
            "slot": slot,
            "binding": dict(choice.get("binding") or {}),
            "actionable": True,
        })
    if len(rows) == 1:
        rows.append({"id": "program_editor:no_bindings", "label": "No eligible binding choices.", "actionable": False})
    rows.append({"id": "program_editor:back", "label": "Back", "action": "program_editor:back", "actionable": True})
    return rows


def drone_program_editor_rows(editor_state, sim, player_eid, record, *, item_catalog=None):
    if not _editor_open(editor_state):
        return ()
    mode = _clean(editor_state.get("mode"), "draft")
    if mode == "line_menu":
        return tuple(_line_menu_rows(editor_state))
    if mode == "choose_verb":
        return tuple(_choice_rows(editor_state, record, mode=mode, choices=DRONE_PROGRAM_VERBS))
    if mode == "choose_slot":
        return tuple(_choice_rows(editor_state, record, mode=mode, choices=DRONE_PROGRAM_SLOT_TYPES))
    if mode == "choose_predicate":
        return tuple(_choice_rows(editor_state, record, mode=mode, choices=DRONE_PROGRAM_PREDICATES))
    if mode == "choose_goto":
        draft = normalize_drone_program(editor_state.get("draft"))
        return tuple(_choice_rows(editor_state, record, mode=mode, choices=_line_numbers(draft)))
    if mode == "bind_slot":
        return tuple(_binding_rows(editor_state, sim, player_eid, record, item_catalog=item_catalog))
    return tuple(_draft_rows(editor_state, sim, player_eid, record, item_catalog=item_catalog))


def _module_metadata(program):
    program = normalize_drone_program(program)
    return {
        "drone_program": {key: value for key, value in program.items() if key != "errors"},
        "display_name": f"Procedure: {program.get('label')}",
        "source_context": "player_authored_drone_program",
        "max_steps": int(max(1, len(program.get("lines", ()) or ()))),
    }


def _update_existing_custom_module(sim, player_eid, record, editor_state, program, *, item_catalog=None):
    gate = actor_can_author_drone_program(sim, player_eid, program)
    if not gate.get("ok"):
        return gate
    source_kind = _clean(editor_state.get("source_kind"), "new")
    source_instance_id = _clean(editor_state.get("source_instance_id"))
    source_index = editor_state.get("source_index")
    metadata = _module_metadata(program)
    if source_kind == "installed":
        state = record.get("state") if isinstance(record, dict) else None
        modules = list(getattr(state, "modules", ()) or ())
        target_index = None
        if source_index is not None and 0 <= int(source_index) < len(modules):
            target_index = int(source_index)
        elif source_instance_id:
            for idx, module in enumerate(modules):
                if _clean(module.get("source_instance_id")) == source_instance_id:
                    target_index = idx
                    break
        if target_index is None:
            return {"ok": False, "reason": "custom_module_unavailable"}
        module = dict(modules[target_index])
        module["metadata"] = metadata
        modules[target_index] = module
        state.modules = modules
        state.source_metadata["modules"] = [dict(entry) for entry in modules if isinstance(entry, dict)]
        return {"ok": True, "reason": None, "entry": dict(module), "program": program}
    if source_kind == "backpack":
        inventory = sim.ecs.get(Inventory).get(player_eid)
        entry = inventory.find(instance_id=source_instance_id) if inventory is not None else None
        if entry is None:
            return {"ok": False, "reason": "custom_module_unavailable"}
        entry["metadata"] = metadata
        return {"ok": True, "reason": None, "entry": dict(entry), "program": program}
    if source_kind == "workshop":
        workshop = drone_workshop_for_actor(sim, player_eid, create=True, item_catalog=item_catalog)
        for entry in getattr(workshop, "parts", ()) or ():
            if not isinstance(entry, dict):
                continue
            if _clean(entry.get("instance_id")) != source_instance_id:
                continue
            if _clean(entry.get("item_id")).lower() != DRONE_CUSTOM_PROCEDURE_MODULE_ID:
                continue
            entry["metadata"] = metadata
            return {"ok": True, "reason": None, "entry": dict(entry), "program": program}
        return {"ok": False, "reason": "custom_module_unavailable"}
    return write_custom_drone_program_module(sim, player_eid, program, item_catalog=item_catalog)


def save_program_editor(sim, player_eid, record, editor_state, *, item_catalog=None):
    state = record.get("state") if isinstance(record, dict) else None
    limit = drone_program_limit_for_state(state)
    program = _normalize_draft(editor_state.get("draft"), max_steps=limit)
    if program.get("errors"):
        return {"ok": False, "reason": "invalid_program", "errors": tuple(program.get("errors", ()))}
    source_kind = _clean(editor_state.get("source_kind"), "new")
    if source_kind in {"installed", "backpack", "workshop"}:
        result = _update_existing_custom_module(sim, player_eid, record, editor_state, program, item_catalog=item_catalog)
    else:
        result = write_custom_drone_program_module(sim, player_eid, program, item_catalog=item_catalog)
    if result.get("ok"):
        editor_state["dirty"] = False
        editor_state["feedback"] = "saved"
    return result


def handle_program_editor_action(sim, player_eid, record, editor_state, row, *, item_catalog=None):
    if not isinstance(editor_state, dict):
        return {"ok": False, "reason": "missing_editor"}
    action = _clean((row or {}).get("action")).lower()
    if action == "program_editor:start_new":
        start_program_editor(editor_state, None, source_kind="new", label="Custom Routine", max_steps=drone_program_limit_for_state((record or {}).get("state")))
        return {"ok": True, "reason": None, "feedback": "Started new custom routine."}
    if action == "program_editor:start_copy":
        program = normalize_drone_program((row or {}).get("program"))
        label = f"Custom {program.get('label')}"
        start_program_editor(editor_state, program, source_kind="copy", label=label, max_steps=drone_program_limit_for_state((record or {}).get("state")))
        return {"ok": True, "reason": None, "feedback": f"Copied {program.get('label')} into editor."}
    if action == "program_editor:start_edit":
        start_program_editor(
            editor_state,
            (row or {}).get("program"),
            source_kind=(row or {}).get("source_kind"),
            source_instance_id=(row or {}).get("source_instance_id"),
            source_index=(row or {}).get("source_index"),
            max_steps=drone_program_limit_for_state((record or {}).get("state")),
        )
        return {"ok": True, "reason": None, "feedback": "Editing custom routine."}
    if action == "program_editor:close":
        clear_program_editor(editor_state)
        return {"ok": True, "reason": None, "feedback": "Editor closed."}
    if action == "program_editor:back":
        mode = _clean(editor_state.get("mode"), "draft")
        if mode in {"choose_verb", "choose_slot", "choose_predicate", "choose_goto"}:
            return _set_mode(editor_state, "line_menu")
        if mode == "bind_slot":
            return _set_mode(editor_state, "draft")
        if mode == "line_menu":
            return _set_mode(editor_state, "draft")
        clear_program_editor(editor_state)
        return {"ok": True, "reason": None, "feedback": "Editor closed."}
    if action == "program_editor:open_line":
        editor_state["selected_line_index"] = _int((row or {}).get("line_index"), 0)
        return _set_mode(editor_state, "line_menu")
    if action in {"program_editor:append_line", "program_editor:insert_after"}:
        draft = normalize_drone_program(editor_state.get("draft"))
        lines = list(draft.get("lines", ()) or ())
        limit = drone_program_limit_for_state((record or {}).get("state"))
        if len(lines) >= limit:
            return {"ok": False, "reason": "line_limit"}
        if action.endswith("append_line"):
            lines.append(_line_for_verb("WAIT", line_no=(len(lines) + 1) * 10))
            editor_state["selected_line_index"] = len(lines) - 1
        else:
            _line, index, lines = _current_line(editor_state)
            lines.insert(index + 1, _line_for_verb("WAIT", line_no=(index + 2) * 10))
            editor_state["selected_line_index"] = index + 1
        _set_draft_lines(editor_state, lines)
        return {"ok": True, "reason": None, "feedback": "Line inserted."}
    if action == "program_editor:delete_line":
        _line, index, lines = _current_line(editor_state)
        if len(lines) <= 1:
            return {"ok": False, "reason": "last_line"}
        lines.pop(index)
        editor_state["selected_line_index"] = max(0, min(index, len(lines) - 1))
        _set_draft_lines(editor_state, lines)
        return _set_mode(editor_state, "draft")
    if action in {"program_editor:move_up", "program_editor:move_down"}:
        _line, index, lines = _current_line(editor_state)
        new_index = index - 1 if action.endswith("move_up") else index + 1
        if new_index < 0 or new_index >= len(lines):
            return {"ok": False, "reason": "line_edge"}
        lines[index], lines[new_index] = lines[new_index], lines[index]
        editor_state["selected_line_index"] = new_index
        _set_draft_lines(editor_state, lines)
        return {"ok": True, "reason": None, "feedback": "Line moved."}
    if action in {"program_editor:choose_verb", "program_editor:choose_slot", "program_editor:choose_predicate", "program_editor:choose_goto"}:
        return _set_mode(editor_state, action.replace("program_editor:", ""))
    if action == "program_editor:set_verb":
        verb = _verb((row or {}).get("value")) or "WAIT"
        _line, index, lines = _current_line(editor_state)
        goto = lines[0].get("line") if lines else 10
        lines[index] = _line_for_verb(verb, line_no=lines[index].get("line", 10), goto=goto)
        _set_draft_lines(editor_state, lines)
        return _set_mode(editor_state, "line_menu")
    if action == "program_editor:set_slot":
        slot = _slot((row or {}).get("value"))
        _line, index, lines = _current_line(editor_state)
        lines[index]["slot"] = slot
        _set_draft_lines(editor_state, lines)
        return _set_mode(editor_state, "line_menu")
    if action == "program_editor:set_predicate":
        pred = _clean((row or {}).get("value")).upper()
        _line, index, lines = _current_line(editor_state)
        lines[index]["predicate"] = pred
        _set_draft_lines(editor_state, lines)
        return _set_mode(editor_state, "line_menu")
    if action == "program_editor:set_goto":
        _line, index, lines = _current_line(editor_state)
        lines[index]["goto"] = _int((row or {}).get("value"), lines[0].get("line") if lines else 10)
        _set_draft_lines(editor_state, lines)
        return _set_mode(editor_state, "line_menu")
    if action == "program_editor:choose_binding":
        return _set_mode(editor_state, "bind_slot", binding_slot=_slot((row or {}).get("slot")))
    if action == "program_editor:set_binding":
        slot = _slot((row or {}).get("slot"))
        bindings = editor_state.get("bindings") if isinstance(editor_state.get("bindings"), dict) else {}
        bindings[slot] = dict((row or {}).get("binding") or {})
        editor_state["bindings"] = bindings
        editor_state["dirty"] = True
        return _set_mode(editor_state, "draft")
    if action == "program_editor:save":
        return save_program_editor(sim, player_eid, record, editor_state, item_catalog=item_catalog)
    if action == "program_editor:activate":
        program = _normalize_draft(editor_state.get("draft"), max_steps=drone_program_limit_for_state((record or {}).get("state")))
        if program.get("errors"):
            return {"ok": False, "reason": "invalid_program", "errors": tuple(program.get("errors", ()))}
        return {"ok": True, "reason": None, "program": program, "feedback": "Draft ready to activate."}
    return {"ok": False, "reason": "unknown_editor_action"}


def editor_feedback_for_result(result, *, item_catalog=None):
    if not isinstance(result, dict):
        return "Editor action blocked."
    if result.get("ok"):
        if result.get("feedback"):
            return str(result.get("feedback"))
        entry = result.get("entry")
        if isinstance(entry, dict):
            return f"Saved {item_display_name(entry.get('item_id'), metadata=entry.get('metadata'), item_catalog=item_catalog)}."
        return "Editor updated."
    reason = _clean(result.get("reason"), "blocked").replace("_", " ")
    errors = "; ".join(str(error) for error in result.get("errors", ()) if str(error).strip())
    return f"Editor blocked: {reason}{(': ' + errors) if errors else ''}."
