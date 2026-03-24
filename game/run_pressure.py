from __future__ import annotations


MAX_ATTENTION = 100
MAX_HISTORY = 64

TIER_EFFECTS = {
    "low": {
        "suspicion_mult": 1.0,
        "goodwill_mult": 1.0,
        "trade_buy_mult": 1.0,
        "trade_sell_mult": 1.0,
        "insurance_premium_mult": 1.0,
        "defense_severity_bias": 0,
        "protect_threshold_shift": 0,
    },
    "medium": {
        "suspicion_mult": 1.12,
        "goodwill_mult": 0.88,
        "trade_buy_mult": 1.04,
        "trade_sell_mult": 0.97,
        "insurance_premium_mult": 1.06,
        "defense_severity_bias": 1,
        "protect_threshold_shift": 1,
    },
    "high": {
        "suspicion_mult": 1.26,
        "goodwill_mult": 0.74,
        "trade_buy_mult": 1.1,
        "trade_sell_mult": 0.93,
        "insurance_premium_mult": 1.12,
        "defense_severity_bias": 3,
        "protect_threshold_shift": 2,
    },
}


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def pressure_tier_for(value):
    number = max(0, min(MAX_ATTENTION, _safe_int(value, default=0)))
    if number >= 70:
        return "high"
    if number >= 35:
        return "medium"
    return "low"


def _state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits

    state = traits.get("run_pressure")
    if not isinstance(state, dict):
        state = {}
        traits["run_pressure"] = state

    attention = max(0, min(MAX_ATTENTION, _safe_int(state.get("attention"), default=0)))
    state["attention"] = attention
    state["peak_attention"] = max(attention, _safe_int(state.get("peak_attention"), default=attention))
    state["tier"] = pressure_tier_for(attention)
    state["last_raise_tick"] = _safe_int(state.get("last_raise_tick"), default=-10_000)
    state["last_decay_tick"] = _safe_int(state.get("last_decay_tick"), default=-10_000)
    state["last_change_tick"] = _safe_int(state.get("last_change_tick"), default=-10_000)
    state["mitigation_count"] = max(0, _safe_int(state.get("mitigation_count"), default=0))

    history = state.get("history")
    if not isinstance(history, list):
        history = []
        state["history"] = history
    if len(history) > MAX_HISTORY:
        del history[:-MAX_HISTORY]
    return state


def pressure_snapshot(sim):
    state = _state(sim)
    attention = int(state["attention"])
    tier = pressure_tier_for(attention)
    return {
        "attention": attention,
        "tier": tier,
        "peak_attention": int(state["peak_attention"]),
        "last_raise_tick": int(state["last_raise_tick"]),
        "last_decay_tick": int(state["last_decay_tick"]),
        "last_change_tick": int(state["last_change_tick"]),
        "mitigation_count": int(state["mitigation_count"]),
        "effects": dict(TIER_EFFECTS.get(tier, TIER_EFFECTS["low"])),
    }


def pressure_effects(sim):
    return dict(pressure_snapshot(sim).get("effects", {}))


def apply_pressure_delta(
    sim,
    *,
    delta,
    source,
    reason="",
    source_event="",
):
    state = _state(sim)
    delta = _safe_int(delta, default=0)
    if delta == 0:
        return None

    tick = _safe_int(getattr(sim, "tick", 0), default=0)
    before = int(state["attention"])
    before_tier = pressure_tier_for(before)
    after = max(0, min(MAX_ATTENTION, before + delta))
    actual = int(after - before)
    if actual == 0:
        return None

    after_tier = pressure_tier_for(after)
    state["attention"] = after
    state["peak_attention"] = max(int(state["peak_attention"]), after)
    state["tier"] = after_tier
    state["last_change_tick"] = tick
    if actual > 0:
        state["last_raise_tick"] = tick
    else:
        state["last_decay_tick"] = tick

    key = str(source or "unknown").strip().lower() or "unknown"
    if actual < 0 and key in {"shelter", "banking", "insurance", "lay_low", "passive_decay"}:
        state["mitigation_count"] = int(state["mitigation_count"]) + 1

    entry = {
        "tick": tick,
        "source": key,
        "delta": actual,
        "before": before,
        "after": after,
        "before_tier": before_tier,
        "after_tier": after_tier,
    }
    if reason:
        entry["reason"] = str(reason).strip()
    if source_event:
        entry["source_event"] = str(source_event).strip()
    state["history"].append(entry)
    if len(state["history"]) > MAX_HISTORY:
        del state["history"][:-MAX_HISTORY]

    return {
        "delta": actual,
        "before": before,
        "after": after,
        "before_tier": before_tier,
        "after_tier": after_tier,
        "tier_changed": before_tier != after_tier,
        "source": key,
        "reason": entry.get("reason", ""),
        "source_event": entry.get("source_event", ""),
    }
