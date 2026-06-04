"""Shared status-effect modifier and pacing helpers."""

import math

from game.components import NPCNeeds, StatusEffects


SURVIVAL_HUNGER_DEFAULT = 86.0
SURVIVAL_THIRST_DEFAULT = 90.0
SURVIVAL_LOW_LEVEL = 60.0
SURVIVAL_CRITICAL_LEVEL = 30.0
SURVIVAL_SEVERE_LEVEL = 10.0


def _float_or_default(value, default):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clamp_need(value):
    return max(0.0, min(100.0, _float_or_default(value, 0.0)))


def _ensure_survival_needs(needs):
    if needs is None:
        return None
    if not hasattr(needs, "hunger"):
        needs.hunger = float(SURVIVAL_HUNGER_DEFAULT)
    if not hasattr(needs, "thirst"):
        needs.thirst = float(SURVIVAL_THIRST_DEFAULT)
    if not isinstance(getattr(needs, "critical", None), set):
        needs.critical = set(getattr(needs, "critical", set()) or set())
    needs.hunger = _clamp_need(getattr(needs, "hunger", SURVIVAL_HUNGER_DEFAULT))
    needs.thirst = _clamp_need(getattr(needs, "thirst", SURVIVAL_THIRST_DEFAULT))
    return needs


def _survival_pressure_snapshot(needs):
    needs = _ensure_survival_needs(needs)
    if needs is None:
        return {
            "hunger": SURVIVAL_HUNGER_DEFAULT,
            "thirst": SURVIVAL_THIRST_DEFAULT,
            "hunger_pressure": 0.0,
            "thirst_pressure": 0.0,
            "severe": False,
            "reason": "",
        }
    hunger = _clamp_need(getattr(needs, "hunger", SURVIVAL_HUNGER_DEFAULT))
    thirst = _clamp_need(getattr(needs, "thirst", SURVIVAL_THIRST_DEFAULT))
    hunger_pressure = max(0.0, (SURVIVAL_LOW_LEVEL - hunger) / SURVIVAL_LOW_LEVEL)
    thirst_pressure = max(0.0, (SURVIVAL_LOW_LEVEL - thirst) / SURVIVAL_LOW_LEVEL)
    severe_hunger = hunger < SURVIVAL_SEVERE_LEVEL
    severe_thirst = thirst < SURVIVAL_SEVERE_LEVEL
    if severe_hunger and severe_thirst:
        reason = "deprivation"
    elif severe_thirst:
        reason = "dehydration"
    elif severe_hunger:
        reason = "starvation"
    else:
        reason = ""
    return {
        "hunger": hunger,
        "thirst": thirst,
        "hunger_pressure": max(0.0, min(1.0, hunger_pressure)),
        "thirst_pressure": max(0.0, min(1.0, thirst_pressure)),
        "severe": bool(severe_hunger or severe_thirst),
        "reason": reason,
    }


def _survival_need_modifiers(needs):
    snapshot = _survival_pressure_snapshot(needs)
    hunger_pressure = float(snapshot.get("hunger_pressure", 0.0) or 0.0)
    thirst_pressure = float(snapshot.get("thirst_pressure", 0.0) or 0.0)
    if hunger_pressure <= 0.0001 and thirst_pressure <= 0.0001:
        return {}
    return {
        "move_speed_mult": -((thirst_pressure * 0.18) + (hunger_pressure * 0.10)),
        "ranged_accuracy_mult": -((thirst_pressure * 0.28) + (hunger_pressure * 0.10)),
        "melee_damage_mult": -((hunger_pressure * 0.24) + (thirst_pressure * 0.08)),
        "weapon_cooldown_mult": (hunger_pressure * 0.20) + (thirst_pressure * 0.12),
        "melee_cooldown_mult": (hunger_pressure * 0.16) + (thirst_pressure * 0.10),
        "incoming_damage_mult": (thirst_pressure * 0.18) + (hunger_pressure * 0.10),
        "suppression_resist_mult": -((thirst_pressure * 0.24) + (hunger_pressure * 0.08)),
        "assault_bias_delta": -((hunger_pressure * 0.18) + (thirst_pressure * 0.08)),
        "retreat_bias_delta": (hunger_pressure * 0.22) + (thirst_pressure * 0.16),
    }


def _status_effects_for(sim, eid):
    effects_map = sim.ecs.get(StatusEffects)
    if not effects_map:
        return None
    return effects_map.get(eid)


def _status_modifiers_for(sim, eid):
    effects = _status_effects_for(sim, eid)
    modifiers = {}
    if not effects:
        modifiers = {}
    else:
        try:
            raw_modifiers = effects.modifiers_sum()
        except AttributeError:
            raw_modifiers = {}
        modifiers = dict(raw_modifiers) if isinstance(raw_modifiers, dict) else {}

    needs_map = sim.ecs.get(NPCNeeds) if sim is not None else None
    needs = needs_map.get(eid) if needs_map else None
    for key, value in _survival_need_modifiers(needs).items():
        modifiers[key] = _float_or_default(modifiers.get(key, 0.0), 0.0) + float(value)
    return modifiers


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
