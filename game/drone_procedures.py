"""Legacy direct-command intents for autonomous drone behavior.

Richer authored routines such as patrol, watch, retrieve, distract, and alarm
work live exclusively in :mod:`game.drone_programs`. Keeping this registry
limited to direct command intents prevents the legacy runner from advertising a
second, mostly-stubbed procedure language.
"""

from __future__ import annotations

from game.drone_runtime import drone_state_has_capability


LEGACY_DRONE_INTENT_REGISTRY = {
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
}

# Compatibility name for callers that imported the original registry.
DRONE_PROCEDURE_REGISTRY = LEGACY_DRONE_INTENT_REGISTRY

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
    """Return whether ``key`` is executable by the legacy intent runner."""

    return bool(drone_procedure_definition(key))


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
