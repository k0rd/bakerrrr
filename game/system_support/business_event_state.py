"""Shared business-event state helpers."""


def _business_event_actor_state(sim):
    state = getattr(sim, "business_event_actor_state", None)
    if isinstance(state, dict):
        return state
    state = {}
    sim.business_event_actor_state = state
    return state


def _business_event_actor_note(sim, eid):
    try:
        key = int(eid)
    except (TypeError, ValueError):
        return None
    return _business_event_actor_state(sim).get(key)


def _business_event_seed_state(sim):
    state = getattr(sim, "business_event_seed_state", None)
    if isinstance(state, dict):
        state.setdefault("active", {})
        state["next_id"] = max(1, int(state.get("next_id", 1) or 1))
        return state
    state = {"active": {}, "next_id": 1}
    sim.business_event_seed_state = state
    return state
