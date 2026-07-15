"""Shared procedure vocabulary for autonomous drone behavior."""

from __future__ import annotations

from game.drone_runtime import drone_state_has_capability


DRONE_PROCEDURE_REGISTRY = {
    "hold": {
        "label": "hold position",
        "capabilities": (),
    },
    "follow": {
        "label": "follow owner",
        "capabilities": ("follow",),
    },
    "return": {
        "label": "return home",
        "capabilities": (),
    },
    "mapping": {
        "label": "map nearby area",
        "capabilities": ("mapping",),
    },
    "scout": {
        "label": "scout target point",
        "capabilities": ("mapping",),
    },
    "watch_doorway": {
        "label": "watch doorway",
        "capabilities": ("camera",),
        "implemented": False,
    },
    "watch_person": {
        "label": "watch person",
        "capabilities": ("camera",),
        "implemented": False,
    },
    "retrieve_item": {
        "label": "retrieve item",
        "capabilities": ("cargo",),
        "implemented": False,
    },
    "carry_item_to_owner": {
        "label": "carry item to owner",
        "capabilities": ("cargo",),
        "implemented": False,
    },
    "distract": {
        "label": "distract/noise",
        "capabilities": ("speaker",),
        "implemented": False,
    },
    "disable_alarm": {
        "label": "disable alarm panel",
        "capabilities": ("alarm_probe",),
        "implemented": False,
    },
    "search_room": {
        "label": "search room",
        "capabilities": ("mapping",),
        "implemented": False,
    },
    "patrol": {
        "label": "patrol small route",
        "capabilities": ("mapping",),
        "implemented": False,
    },
    "flee": {
        "label": "flee/evade",
        "capabilities": (),
        "implemented": False,
    },
}

DRONE_PROCEDURE_ALIASES = {
    "": "",
    "none": "",
    "manual": "",
    "map": "mapping",
    "recon": "mapping",
    "mapping_procedure": "mapping",
    "follow_owner": "follow",
    "return_home": "return",
    "home": "return",
    "watch": "watch_doorway",
    "watch_door": "watch_doorway",
    "retrieve": "retrieve_item",
    "carry": "carry_item_to_owner",
    "noise": "distract",
    "alarm": "disable_alarm",
    "evade": "flee",
}


def normalize_drone_procedure_key(value):
    key = str(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    key = DRONE_PROCEDURE_ALIASES.get(key, key)
    return key if key in DRONE_PROCEDURE_REGISTRY else key


def drone_procedure_definition(key):
    key = normalize_drone_procedure_key(key)
    return dict(DRONE_PROCEDURE_REGISTRY.get(key, {}))


def drone_procedure_label(key):
    definition = drone_procedure_definition(key)
    return str(definition.get("label", key or "manual") or key or "manual")


def drone_procedure_implemented(key):
    definition = drone_procedure_definition(key)
    return bool(definition) and bool(definition.get("implemented", True))


def drone_procedure_missing_capability(state, key, *, item_catalog=None):
    definition = drone_procedure_definition(key)
    if not definition:
        return "unknown_procedure"
    for capability in tuple(definition.get("capabilities", ()) or ()):
        if not drone_state_has_capability(state, capability, item_catalog=item_catalog):
            return f"missing_{capability}"
    return None


def default_drone_procedure_key(state, *, item_catalog=None):
    """Return the built-in procedure implied by installed procedure modules."""

    if state is None:
        return ""
    if drone_state_has_capability(state, "follow", item_catalog=item_catalog):
        return "follow"
    has_mapping = drone_state_has_capability(state, "mapping", item_catalog=item_catalog)
    has_sensor = drone_state_has_capability(state, "mapping_sensor", item_catalog=item_catalog)
    has_radio = (
        drone_state_has_capability(state, "radio", item_catalog=item_catalog)
        or drone_state_has_capability(state, "comms", item_catalog=item_catalog)
    )
    if has_mapping and has_sensor and has_radio:
        return "mapping"
    return ""


def cardinal_step_toward(start, target):
    if not isinstance(start, (list, tuple)) or not isinstance(target, (list, tuple)):
        return None
    if len(start) < 2 or len(target) < 2:
        return None
    sx, sy = int(start[0]), int(start[1])
    tx, ty = int(target[0]), int(target[1])
    dx = tx - sx
    dy = ty - sy
    if dx == 0 and dy == 0:
        return None
    if abs(dx) >= abs(dy) and dx != 0:
        return (1 if dx > 0 else -1, 0)
    if dy != 0:
        return (0, 1 if dy > 0 else -1)
    return None
