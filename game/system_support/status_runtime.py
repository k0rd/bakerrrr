"""Shared status-effect modifier and pacing helpers."""

import math

from game.components import StatusEffects


def _float_or_default(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _status_effects_for(sim, eid):
    effects_map = sim.ecs.get(StatusEffects)
    if not effects_map:
        return None
    return effects_map.get(eid)


def _status_modifiers_for(sim, eid):
    effects = _status_effects_for(sim, eid)
    if not effects:
        return {}
    try:
        modifiers = effects.modifiers_sum()
    except AttributeError:
        return {}
    return modifiers if isinstance(modifiers, dict) else {}


def _status_modifier_total(sim, eid, key, default=0.0):
    modifiers = _status_modifiers_for(sim, eid)
    if not modifiers:
        return float(default)
    return _float_or_default(modifiers.get(key, default), default)


def _status_multiplier(sim, eid, key, *, base=1.0, minimum=0.0, maximum=3.0):
    factor = float(base) + _status_modifier_total(sim, eid, key, default=0.0)
    return max(float(minimum), min(float(maximum), float(factor)))


def _status_int_offset(sim, eid, key, default=0):
    return int(round(_status_modifier_total(sim, eid, key, default=default)))


def _status_tick_step(effects, key, delta):
    delta = _float_or_default(delta, 0.0)
    if abs(delta) <= 0.0001:
        return 0

    banks = getattr(effects, "_tick_banks", None)
    if not isinstance(banks, dict):
        banks = {}
        setattr(effects, "_tick_banks", banks)

    total = _float_or_default(banks.get(key, 0.0), 0.0) + delta
    whole = math.floor(total) if total >= 0.0 else math.ceil(total)
    banks[key] = total - float(whole)
    return int(whole)


def _npc_status_metric_args(sim, eid):
    steady = _status_modifier_total(sim, eid, "suppression_resist_mult", default=0.0)
    return {
        "pressure_mult": max(0.2, min(1.8, 1.0 - steady)),
        "retreat_bias_delta": _status_modifier_total(sim, eid, "retreat_bias_delta", default=0.0),
        "assault_bias_delta": _status_modifier_total(sim, eid, "assault_bias_delta", default=0.0),
    }
