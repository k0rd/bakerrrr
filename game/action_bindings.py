"""Shared action registry and keyboard binding helpers."""

from __future__ import annotations

from dataclasses import dataclass

from ui.input_keys import KEY_DOWN, KEY_LEFT, KEY_RIGHT, KEY_UP


ACTION_BINDINGS_VERSION = 1
ACTION_MENU_KEY = ord("\t")
PHYSICAL_INPUT_KINDS = frozenset({"key", "button", "axis", "hat"})
CONTROLLER_DEADZONE = 0.35
CONTROLLER_REPEAT_DELAY = 0.18
CONTROLLER_REPEAT_INTERVAL = 0.09

CONTROLLER_BUTTON_LABELS = {
    "south": "Button South",
    "east": "Button East",
    "west": "Button West",
    "north": "Button North",
    "view": "View",
    "select": "View",
    "back": "View",
    "guide": "Guide",
    "start": "Start",
    "menu": "Start",
    "left_shoulder": "Left Shoulder",
    "right_shoulder": "Right Shoulder",
    "left_stick": "Left Stick",
    "right_stick": "Right Stick",
    "dpad_up": "D-pad Up",
    "dpad_down": "D-pad Down",
    "dpad_left": "D-pad Left",
    "dpad_right": "D-pad Right",
}
CONTROLLER_AXIS_LABELS = {
    "left_x": "Left Stick X",
    "left_y": "Left Stick Y",
    "right_x": "Right Stick X",
    "right_y": "Right Stick Y",
    "left_trigger": "Left Trigger",
    "right_trigger": "Right Trigger",
}
PROTECTED_CONTROLLER_BUTTONS = frozenset({
    "south",
    "east",
    "view",
    "select",
    "back",
    "guide",
    "start",
    "menu",
    "left_shoulder",
    "dpad_up",
    "dpad_down",
    "dpad_left",
    "dpad_right",
})
PROTECTED_CONTROLLER_AXES = frozenset({"left_x", "left_y", "left_stick"})
PROTECTED_CONTROLLER_HATS = frozenset({"dpad", "hat0"})


@dataclass(frozen=True)
class ActionSpec:
    id: str
    label: str
    category: str
    default_keys: tuple[int, ...] = ()
    contexts: tuple[str, ...] = ("local",)
    rebindable: bool = True
    protected: bool = False
    menu: bool = True
    description: str = ""


ACTION_SPECS = (
    ActionSpec("action_menu", "Action menu", "system", (ACTION_MENU_KEY,), contexts=("local", "overworld"), rebindable=False, protected=True, menu=False),
    ActionSpec("help", "Help", "system", (ord("?"),), contexts=("local", "overworld"), rebindable=False, protected=True),
    ActionSpec("look", "Look", "world", (ord("x"),), description="Open the look cursor."),
    ActionSpec("talk", "Talk", "world", (ord("/"),), description="Target someone to talk to."),
    ActionSpec("interact", "Interact", "world", (ord("'"),), description="Target a nearby thing to use."),
    ActionSpec("service", "Service", "world", (ord("."),), description="Use the service at your tile."),
    ActionSpec("lock", "Lock / unlock", "world", (ord(";"),), description="Lock or unlock a nearby door."),
    ActionSpec("pickup", "Pick up", "items", (ord(","),), description="Pick up nearby items."),
    ActionSpec("drop", "Drop", "items", (ord("r"), ord("R")), description="Drop from inventory."),
    ActionSpec("use_item", "Use / equip", "items", (ord("u"), ord("U")), description="Use, equip, stow, or throw an item."),
    ActionSpec("inventory", "Inventory", "items", (ord("i"), ord("I")), contexts=("local", "overworld")),
    ActionSpec("character", "Character sheet", "info", (ord("+"),), contexts=("local", "overworld")),
    ActionSpec("operations", "Operations report", "info", (ord("o"), ord("O")), contexts=("local", "overworld")),
    ActionSpec("notebooks", "Notebooks", "info", (ord("y"), ord("Y")), contexts=("local", "overworld")),
    ActionSpec("event_log", "Event log", "info", (ord("L"),), contexts=("local", "overworld")),
    ActionSpec("debug", "Debug overlay", "info", (ord("D"),), contexts=("local", "overworld"), description="Only opens in debug-enabled builds."),
    ActionSpec("map", "Map", "travel", (ord("X"),), description="Open local/overworld map view."),
    ActionSpec("map_enter_local", "Return to street", "travel", (ord("t"),), contexts=("local", "overworld")),
    ActionSpec("wait", "Wait", "world", (ord(" "), ord("5")), contexts=("local", "overworld")),
    ActionSpec("sneak", "Sneak", "caution", (ord("S"),)),
    ActionSpec("cover", "Take cover", "caution", (ord("C"),)),
    ActionSpec("cover_hop", "Hop cover", "caution", (ord("v"),)),
    ActionSpec("floor_up", "Go upstairs", "travel", (ord(">"), ord("]"))),
    ActionSpec("floor_down", "Go downstairs", "travel", (ord("<"), ord("["))),
    ActionSpec("aim_target_next", "Target next", "combat", (ord("f"),), description="Cycle target lock or open melee aim."),
    ActionSpec("aim_target_prev", "Target previous", "combat", (ord("F"),), description="Cycle target lock backward."),
    ActionSpec("free_aim", "Free aim", "combat", (), description="Open the aim cursor."),
    ActionSpec("fire_locked", "Fire locked target", "combat", (), description="Fire at the current aim lock."),
    ActionSpec("tactical_read", "Tactical read", "combat", (ord("T"),)),
    ActionSpec("cycle_weapon", "Cycle weapon", "combat", (ord("V"),)),
    ActionSpec("side_entry", "Door breach", "caution", (ord("J"),)),
    ActionSpec("window_entry", "Window entry", "caution", (ord("W"),)),
    ActionSpec("forced_breach", "Wall breach", "caution", (ord("K"),)),
    ActionSpec("purchase_property", "Buy property", "world", (ord("p"), ord("P"))),
    ActionSpec("vehicle_headlights", "Headlights", "vehicle", (ord("H"),), contexts=("local",)),
    ActionSpec("quit", "Save and quit", "system", (ord("Q"),), contexts=("local", "overworld"), rebindable=False, protected=True),
    ActionSpec("overworld_scan", "Scan map", "travel", (ord("x"),), contexts=("overworld",)),
    ActionSpec("marker_add", "Add marker", "travel", (ord("m"), ord("M")), contexts=("overworld",)),
    ActionSpec("marker_list", "List markers", "travel", (ord("l"),), contexts=("overworld",)),
    ActionSpec("marker_nearest", "Nearest marker", "travel", (ord("n"), ord("N")), contexts=("overworld",)),
    ActionSpec("drive_to_marker", "Drive to marker", "travel", (ord("g"), ord("G")), contexts=("overworld",)),
)

ACTION_SPECS_BY_ID = {spec.id: spec for spec in ACTION_SPECS}


def _movement_key_codes():
    keys = {
        KEY_UP,
        KEY_DOWN,
        KEY_LEFT,
        KEY_RIGHT,
        ord("7"),
        ord("8"),
        ord("9"),
        ord("4"),
        ord("6"),
        ord("1"),
        ord("2"),
        ord("3"),
        ord("w"),
        ord("s"),
        ord("a"),
        ord("d"),
        ord("q"),
        ord("e"),
        ord("z"),
        ord("c"),
        ord("k"),
        ord("j"),
        ord("h"),
        ord("l"),
    }
    return frozenset(int(key) for key in keys if key is not None)


PROTECTED_KEY_CODES = frozenset({
    ACTION_MENU_KEY,
    10,
    13,
    27,
    127,
    ord("?"),
}) | _movement_key_codes()


def default_control_bindings():
    return {
        "version": ACTION_BINDINGS_VERSION,
        "bindings": {},
    }


def normalize_physical_input(raw):
    if isinstance(raw, int):
        return {"kind": "key", "code": int(raw)}
    if not isinstance(raw, dict):
        return None
    kind = str(raw.get("kind", "") or "").strip().lower()
    if kind not in PHYSICAL_INPUT_KINDS:
        return None
    cleaned = {"kind": kind}
    if kind == "key":
        try:
            cleaned["code"] = int(raw.get("code"))
        except (TypeError, ValueError):
            return None
    else:
        for field in ("code", "axis", "hat", "value", "direction", "device_guid", "dx", "dy", "source"):
            if field in raw:
                cleaned[field] = raw.get(field)
        if "code" not in cleaned and kind == "button":
            return None
        if kind == "button":
            cleaned["code"] = str(cleaned.get("code", "")).strip().lower() if not isinstance(cleaned.get("code"), int) else int(cleaned.get("code"))
        elif kind == "axis":
            cleaned["axis"] = str(cleaned.get("axis", "")).strip().lower() if not isinstance(cleaned.get("axis"), int) else int(cleaned.get("axis"))
            if not str(cleaned.get("axis", "")).strip():
                return None
            direction = str(cleaned.get("direction", cleaned.get("value", "")) or "").strip().lower()
            if direction:
                cleaned["direction"] = direction
                cleaned["value"] = direction
        elif kind == "hat":
            cleaned["hat"] = str(cleaned.get("hat", "hat0") or "hat0").strip().lower()
            value = cleaned.get("value")
            if isinstance(value, (list, tuple)) and len(value) >= 2:
                cleaned["value"] = f"{int(value[0])},{int(value[1])}"
            else:
                cleaned["value"] = str(value or cleaned.get("direction", "") or "").strip().lower()
            if "direction" in cleaned:
                cleaned["direction"] = str(cleaned.get("direction", "") or "").strip().lower()
    return cleaned


def input_signature(raw):
    physical = normalize_physical_input(raw)
    if not physical:
        return ""
    kind = str(physical.get("kind", "") or "").strip().lower()
    if kind == "key":
        return f"key:{int(physical.get('code'))}"
    if kind == "button":
        return f"button:{physical.get('device_guid', '')}:{physical.get('code')}"
    if kind == "axis":
        return f"axis:{physical.get('device_guid', '')}:{physical.get('axis')}:{physical.get('value', physical.get('direction', ''))}"
    if kind == "hat":
        return f"hat:{physical.get('device_guid', '')}:{physical.get('hat')}:{physical.get('value', physical.get('direction', ''))}"
    return ""


def is_protected_physical_input(raw):
    physical = normalize_physical_input(raw)
    if not physical:
        return True
    kind = str(physical.get("kind", "") or "").strip().lower()
    if kind == "key":
        return int(physical.get("code")) in PROTECTED_KEY_CODES
    if kind == "button":
        code = physical.get("code")
        if isinstance(code, int):
            return False
        return str(code or "").strip().lower() in PROTECTED_CONTROLLER_BUTTONS
    if kind == "axis":
        axis = physical.get("axis")
        if isinstance(axis, int):
            return False
        return str(axis or "").strip().lower() in PROTECTED_CONTROLLER_AXES
    if kind == "hat":
        return str(physical.get("hat", "") or "").strip().lower() in PROTECTED_CONTROLLER_HATS
    return True


def key_physical_input(key_code):
    try:
        return {"kind": "key", "code": int(key_code)}
    except (TypeError, ValueError):
        return None


def sanitize_control_bindings(raw):
    state = default_control_bindings()
    if not isinstance(raw, dict):
        return state
    bindings = raw.get("bindings", raw.get("keys", {}))
    if not isinstance(bindings, dict):
        return state
    cleaned = {}
    for action_id, raw_inputs in bindings.items():
        action_id = str(action_id or "").strip()
        spec = ACTION_SPECS_BY_ID.get(action_id)
        if spec is None or not spec.rebindable:
            continue
        if isinstance(raw_inputs, dict) or isinstance(raw_inputs, int):
            raw_inputs = [raw_inputs]
        if not isinstance(raw_inputs, (list, tuple)):
            continue
        rows = []
        seen = set()
        for raw_input in raw_inputs:
            physical = normalize_physical_input(raw_input)
            signature = input_signature(physical)
            if not physical or not signature or signature in seen:
                continue
            if is_protected_physical_input(physical):
                continue
            seen.add(signature)
            rows.append(physical)
        if rows:
            cleaned[action_id] = rows
    state["bindings"] = cleaned
    return state


def action_default_inputs(action_id):
    spec = ACTION_SPECS_BY_ID.get(str(action_id or ""))
    if not spec:
        return ()
    return tuple(key_physical_input(code) for code in spec.default_keys if key_physical_input(code))


def action_custom_inputs(bindings_state, action_id):
    state = sanitize_control_bindings(bindings_state)
    return tuple(state.get("bindings", {}).get(str(action_id or ""), ()) or ())


def action_effective_inputs(bindings_state, action_id):
    custom = action_custom_inputs(bindings_state, action_id)
    if custom:
        return custom
    return action_default_inputs(action_id)


def key_label(key_code):
    try:
        key_code = int(key_code)
    except (TypeError, ValueError):
        return "?"
    special = {
        ACTION_MENU_KEY: "Tab",
        10: "Enter",
        13: "Enter",
        27: "Esc",
        32: "Space",
        127: "Backspace",
        KEY_UP: "Up",
        KEY_DOWN: "Down",
        KEY_LEFT: "Left",
        KEY_RIGHT: "Right",
    }
    if key_code in special:
        return special[key_code]
    if 32 <= key_code <= 126:
        return chr(key_code)
    return f"Key {key_code}"


def physical_input_label(raw):
    physical = normalize_physical_input(raw)
    if not physical:
        return "unbound"
    kind = physical.get("kind")
    if kind == "key":
        return key_label(physical.get("code"))
    if kind == "button":
        code = physical.get("code")
        if isinstance(code, str):
            return CONTROLLER_BUTTON_LABELS.get(code, f"Button {code.replace('_', ' ').title()}")
        return f"Button {code}"
    if kind == "axis":
        axis = physical.get("axis")
        direction = str(physical.get("value", physical.get("direction", "")) or "").strip()
        if isinstance(axis, str):
            label = CONTROLLER_AXIS_LABELS.get(axis, f"Axis {axis.replace('_', ' ').title()}")
        else:
            label = f"Axis {axis}"
        return f"{label} {direction}".strip()
    if kind == "hat":
        value = str(physical.get("value", physical.get("direction", "")) or "").strip()
        return f"D-pad {value.replace('_', ' ').title()}".strip() if str(physical.get("hat")) == "dpad" else f"Hat {physical.get('hat')} {value}".strip()
    return "input"


def action_binding_label(bindings_state, action_id):
    inputs = action_effective_inputs(bindings_state, action_id)
    if not inputs:
        return "unbound"
    return "/".join(physical_input_label(row) for row in inputs[:2])


def action_for_input(bindings_state, physical_input, *, context="local"):
    physical = normalize_physical_input(physical_input)
    signature = input_signature(physical)
    if not signature:
        return None
    state = sanitize_control_bindings(bindings_state)
    context = str(context or "local").strip().lower() or "local"
    custom_owner = None
    for action_id, rows in state.get("bindings", {}).items():
        spec = ACTION_SPECS_BY_ID.get(action_id)
        if not spec or context not in spec.contexts:
            continue
        if any(input_signature(row) == signature for row in rows):
            custom_owner = action_id
            break
    if custom_owner:
        return custom_owner
    # If a custom binding owns this key in any context, it shadows defaults so
    # reshuffling keys works predictably without rewriting every default row.
    for rows in state.get("bindings", {}).values():
        if any(input_signature(row) == signature for row in rows):
            return None
    for spec in ACTION_SPECS:
        if context not in spec.contexts:
            continue
        if any(input_signature(row) == signature for row in action_default_inputs(spec.id)):
            return spec.id
    return None


def action_for_key(bindings_state, key_code, *, context="local"):
    return action_for_input(bindings_state, key_physical_input(key_code), context=context)


def set_action_binding(bindings_state, action_id, physical_input):
    action_id = str(action_id or "").strip()
    spec = ACTION_SPECS_BY_ID.get(action_id)
    if spec is None:
        return False, "Unknown action.", sanitize_control_bindings(bindings_state)
    if not spec.rebindable or spec.protected:
        return False, f"{spec.label} is protected.", sanitize_control_bindings(bindings_state)
    physical = normalize_physical_input(physical_input)
    if not physical:
        return False, "That input cannot be bound.", sanitize_control_bindings(bindings_state)
    if is_protected_physical_input(physical):
        return False, f"{physical_input_label(physical)} is protected.", sanitize_control_bindings(bindings_state)
    signature = input_signature(physical)
    state = sanitize_control_bindings(bindings_state)
    for other_action_id, rows in list(state.get("bindings", {}).items()):
        kept = [row for row in rows if input_signature(row) != signature]
        if kept:
            state["bindings"][other_action_id] = kept
        else:
            state["bindings"].pop(other_action_id, None)
    state["bindings"][action_id] = [physical]
    return True, f"{spec.label} bound to {physical_input_label(physical)}.", state


def reset_action_binding(bindings_state, action_id):
    state = sanitize_control_bindings(bindings_state)
    state.get("bindings", {}).pop(str(action_id or "").strip(), None)
    return state


def menu_action_specs(*, context="local"):
    context = str(context or "local").strip().lower() or "local"
    return tuple(spec for spec in ACTION_SPECS if spec.menu and context in spec.contexts)


def action_available(action_id, *, context="local", player_in_vehicle=False, aim_lock_active=False):
    action_id = str(action_id or "").strip()
    context = str(context or "local").strip().lower() or "local"
    spec = ACTION_SPECS_BY_ID.get(action_id)
    if not spec:
        return False, "unknown"
    if context not in spec.contexts:
        return False, "not here"
    if action_id == "vehicle_headlights" and not player_in_vehicle:
        return False, "need vehicle"
    if action_id == "map_enter_local" and context == "local" and not player_in_vehicle:
        return False, "need vehicle"
    if action_id == "fire_locked" and not aim_lock_active:
        return False, "no lock"
    return True, ""
