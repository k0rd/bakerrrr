"""Shared player-controlled pause state for input and presentation."""


MANUAL_PAUSE_REASON = "manual_pause"


def manual_pause_active(sim):
    reasons = getattr(sim, "pause_reasons", ())
    if not isinstance(reasons, (set, list, tuple, frozenset)):
        return False
    return MANUAL_PAUSE_REASON in {
        str(reason or "").strip().lower()
        for reason in reasons
        if str(reason or "").strip()
    }


def manual_pause_state(sim):
    state = getattr(sim, "manual_pause_ui", None)
    if not isinstance(state, dict):
        state = {}
        sim.manual_pause_ui = state
    state["active"] = manual_pause_active(sim)
    state.setdefault("binding_label", "unbound")
    return state


def set_manual_pause(sim, active, *, binding_label=None):
    active = bool(active)
    setter = getattr(sim, "set_time_paused", None)
    if callable(setter):
        setter(active, reason=MANUAL_PAUSE_REASON)
    else:
        reasons = getattr(sim, "pause_reasons", None)
        if not isinstance(reasons, set):
            reasons = set()
            sim.pause_reasons = reasons
        if active:
            reasons.add(MANUAL_PAUSE_REASON)
        else:
            reasons.discard(MANUAL_PAUSE_REASON)

    state = manual_pause_state(sim)
    state["active"] = active
    if binding_label is not None:
        state["binding_label"] = str(binding_label or "unbound").strip() or "unbound"
    return state
