from __future__ import annotations


MAX_RESERVE_BONUS = 420
MAX_NETWORK_MARKS = 36
MAX_INTEL_MARKS = 36
MAX_HISTORY = 40


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits

    state = traits.get("objective_progress")
    if not isinstance(state, dict):
        state = {}
        traits["objective_progress"] = state

    state["reserve_bonus_credits"] = max(0, min(MAX_RESERVE_BONUS, _safe_int(state.get("reserve_bonus_credits"), default=0)))
    state["network_marks"] = max(0, min(MAX_NETWORK_MARKS, _safe_int(state.get("network_marks"), default=0)))
    state["intel_marks"] = max(0, min(MAX_INTEL_MARKS, _safe_int(state.get("intel_marks"), default=0)))

    channel_counts = state.get("channel_counts")
    if not isinstance(channel_counts, dict):
        channel_counts = {}
        state["channel_counts"] = channel_counts

    history = state.get("history")
    if not isinstance(history, list):
        history = []
        state["history"] = history
    if len(history) > MAX_HISTORY:
        del history[:-MAX_HISTORY]
    return state


def _objective_id(sim):
    traits = getattr(sim, "world_traits", {})
    if not isinstance(traits, dict):
        return ""
    objective = traits.get("run_objective", {})
    if not isinstance(objective, dict):
        return ""
    return str(objective.get("id", "")).strip().lower()


def award_objective_progress(
    sim,
    *,
    channel,
    reserve_bonus_credits=0,
    network_marks=0,
    intel_marks=0,
    reason="",
    source_event="",
):
    state = _state(sim)
    reserve_delta = max(0, _safe_int(reserve_bonus_credits, default=0))
    network_delta = max(0, _safe_int(network_marks, default=0))
    intel_delta = max(0, _safe_int(intel_marks, default=0))
    if reserve_delta <= 0 and network_delta <= 0 and intel_delta <= 0:
        return None

    before_reserve = int(state["reserve_bonus_credits"])
    before_network = int(state["network_marks"])
    before_intel = int(state["intel_marks"])

    state["reserve_bonus_credits"] = max(0, min(MAX_RESERVE_BONUS, before_reserve + reserve_delta))
    state["network_marks"] = max(0, min(MAX_NETWORK_MARKS, before_network + network_delta))
    state["intel_marks"] = max(0, min(MAX_INTEL_MARKS, before_intel + intel_delta))

    actual = {
        "reserve_bonus_credits": int(state["reserve_bonus_credits"] - before_reserve),
        "network_marks": int(state["network_marks"] - before_network),
        "intel_marks": int(state["intel_marks"] - before_intel),
    }
    if (
        actual["reserve_bonus_credits"] <= 0
        and actual["network_marks"] <= 0
        and actual["intel_marks"] <= 0
    ):
        return None

    key = str(channel or "").strip().lower() or "unknown"
    counts = state["channel_counts"]
    counts[key] = int(max(0, _safe_int(counts.get(key), default=0))) + 1

    entry = {
        "tick": _safe_int(getattr(sim, "tick", 0), default=0),
        "channel": key,
        "objective_id": _objective_id(sim),
        "reserve_bonus_credits": actual["reserve_bonus_credits"],
        "network_marks": actual["network_marks"],
        "intel_marks": actual["intel_marks"],
    }
    if reason:
        entry["reason"] = str(reason).strip()
    if source_event:
        entry["source_event"] = str(source_event).strip()
    state["history"].append(entry)
    if len(state["history"]) > MAX_HISTORY:
        del state["history"][:-MAX_HISTORY]

    totals = {
        "reserve_bonus_credits": int(state["reserve_bonus_credits"]),
        "network_marks": int(state["network_marks"]),
        "intel_marks": int(state["intel_marks"]),
    }
    return {
        "channel": key,
        "objective_id": _objective_id(sim),
        "delta": actual,
        "totals": totals,
        "reason": entry.get("reason", ""),
        "source_event": entry.get("source_event", ""),
    }


def objective_metric_bonuses(sim, objective_id):
    state = _state(sim)
    objective_id = str(objective_id or "").strip().lower()
    reserve = int(state["reserve_bonus_credits"])
    network = int(state["network_marks"])
    intel = int(state["intel_marks"])

    bonuses = {
        "reserve_credits": 0,
        "contact_count": 0,
        "intel_leads": 0,
    }
    if objective_id == "debt_exit":
        bonuses["reserve_credits"] = reserve
    elif objective_id == "networked_extraction":
        bonuses["contact_count"] = network // 2
        bonuses["reserve_credits"] = reserve // 2
    elif objective_id == "high_value_retrieval":
        bonuses["intel_leads"] = intel // 2
    bonuses["raw"] = {
        "reserve_bonus_credits": reserve,
        "network_marks": network,
        "intel_marks": intel,
    }
    return bonuses


def objective_progress_snapshot(sim):
    state = _state(sim)
    return {
        "reserve_bonus_credits": int(state["reserve_bonus_credits"]),
        "network_marks": int(state["network_marks"]),
        "intel_marks": int(state["intel_marks"]),
        "channel_counts": dict(state.get("channel_counts", {})),
        "history": [dict(entry) for entry in state.get("history", ()) if isinstance(entry, dict)],
    }


def objective_progress_recent_history(sim, limit=5):
    limit = max(0, _safe_int(limit, default=5))
    history = objective_progress_snapshot(sim).get("history", [])
    if limit <= 0:
        return []
    return list(reversed(history[-limit:]))


def objective_progress_effects(objective_id, delta):
    objective_id = str(objective_id or "").strip().lower()
    payload = dict(delta or {}) if isinstance(delta, dict) else {}
    reserve = max(0, _safe_int(payload.get("reserve_bonus_credits"), default=0))
    network = max(0, _safe_int(payload.get("network_marks"), default=0))
    intel = max(0, _safe_int(payload.get("intel_marks"), default=0))
    effects = {
        "reserve_credits": 0,
        "contact_count": 0,
        "intel_leads": 0,
    }
    if objective_id == "debt_exit":
        effects["reserve_credits"] = reserve
    elif objective_id == "networked_extraction":
        effects["reserve_credits"] = reserve // 2
        effects["contact_count"] = network // 2
    elif objective_id == "high_value_retrieval":
        effects["intel_leads"] = intel // 2
    return effects


def objective_progress_explain_delta(objective_id, delta):
    objective_id = str(objective_id or "").strip().lower()
    payload = dict(delta or {}) if isinstance(delta, dict) else {}
    reserve = max(0, _safe_int(payload.get("reserve_bonus_credits"), default=0))
    network = max(0, _safe_int(payload.get("network_marks"), default=0))
    intel = max(0, _safe_int(payload.get("intel_marks"), default=0))
    effects = objective_progress_effects(objective_id, payload)
    bits = []

    if objective_id == "debt_exit":
        if reserve > 0:
            bits.append(f"reserve +{effects['reserve_credits']}")
        return bits

    if objective_id == "networked_extraction":
        if network > 0:
            contacts = effects["contact_count"]
            if contacts > 0:
                bits.append(f"contacts +{contacts} from network marks +{network}")
            else:
                bits.append(f"network marks +{network} (2 = +1 contact)")
        if reserve > 0:
            reserve_effect = effects["reserve_credits"]
            if reserve_effect > 0:
                bits.append(f"reserve +{reserve_effect} from support +{reserve}")
            else:
                bits.append(f"reserve support +{reserve} (2 = +1 reserve)")
        return bits

    if objective_id == "high_value_retrieval":
        if intel > 0:
            leads = effects["intel_leads"]
            if leads > 0:
                bits.append(f"leads +{leads} from intel marks +{intel}")
            else:
                bits.append(f"intel marks +{intel} (2 = +1 lead)")
        return bits

    return bits
