"""Bounded streaming support for deliberate observation and pursuit.

Only chunks already selected for unload are inspected, through the maintained
chunk entity index.  A small number of still-live pursuit chunks may remain
coarse-loaded; overflow and elapsed pursuits use explicit archive/restore
transitions instead of simulated hidden footsteps.
"""

from __future__ import annotations

from game.components import AI, DroneState, NPCWill
from game.purposeful_observation import (
    is_purposeful_observation,
    mark_purposeful_observation_offscreen,
    observation_context_purpose,
    purposeful_observation_live_until,
    settle_purposeful_observation_offscreen,
)


PURSUIT_STREAMING_CHUNK_BUDGET = 3
AI_CONTEXT_FIELDS = ("investigation_context", "observation_context")
CONTRACTOR_CONTEXT_FIELDS = ("formation_observation", "follow_observation")

_PURPOSE_PRIORITY = {
    "justice_detention": 90,
    "justice_report_search": 86,
    "justice_identity_check": 82,
    "visible_sneak": 78,
    "bodyguard_formation": 72,
    "hired_backup": 68,
    "peaceful_follow": 64,
    "social_companion": 60,
    "bodyguard_threat_watch": 58,
    "criminal_casing": 52,
    "bounty_pickup": 48,
    "drone_threat_watch": 76,
    "drone_person_watch": 66,
}


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _chunk_key(value):
    if not isinstance(value, (tuple, list)) or len(value) < 2:
        return None
    try:
        return (int(value[0]), int(value[1]))
    except (TypeError, ValueError):
        return None


def _state(sim):
    state = getattr(sim, "pursuit_streaming_state", None)
    if not isinstance(state, dict):
        state = {}
        sim.pursuit_streaming_state = state
    if not isinstance(state.get("protected_chunks"), set):
        state["protected_chunks"] = set(state.get("protected_chunks") or ())
    state.setdefault("protected_reasons", {})
    state.setdefault("last_rows", ())
    state.setdefault("stats", {})
    return state


def pursuit_streaming_state(sim):
    return _state(sim)


def _actor_context_slots(sim, eid):
    ai = sim.ecs.get(AI).get(eid)
    if ai is not None:
        for field in AI_CONTEXT_FIELDS:
            context = getattr(ai, field, None)
            if is_purposeful_observation(context):
                yield ("ai", field, ai, context)
    contractors = getattr(sim, "contractors", {})
    rec = contractors.get(eid) if isinstance(contractors, dict) else None
    if isinstance(rec, dict):
        for field in CONTRACTOR_CONTEXT_FIELDS:
            context = rec.get(field)
            if is_purposeful_observation(context):
                yield ("contractor", field, rec, context)
    drone = sim.ecs.get(DroneState).get(eid)
    if drone is not None:
        context = getattr(drone, "observation_context", None)
        if is_purposeful_observation(context):
            yield ("drone", "observation_context", drone, context)


def _assign_context(owner_kind, field, owner, context):
    if owner_kind in {"ai", "drone"}:
        setattr(owner, field, context)
    else:
        owner[field] = context


def _focus_distance(sim, chunk):
    focus = getattr(getattr(sim, "world", None), "focus", None)
    focus = _chunk_key(focus)
    if focus is None:
        focus = _chunk_key(getattr(sim, "active_chunk_coord", None))
    if focus is None:
        return 0
    return max(abs(int(chunk[0]) - focus[0]), abs(int(chunk[1]) - focus[1]))


def _context_rank(context, *, now):
    purpose = observation_context_purpose(context)
    search = context.get("search_state") if isinstance(context.get("search_state"), dict) else {}
    search_active = search.get("active") is True
    live_until = purposeful_observation_live_until(context)
    remaining = max(0, _safe_int(live_until, now) - now)
    updated = max(
        _safe_int(context.get("updated_tick"), 0),
        _safe_int(context.get("last_seen_tick"), 0),
        _safe_int(context.get("started_tick"), 0),
    )
    return (
        1 if search_active else 0,
        _PURPOSE_PRIORITY.get(purpose, 40),
        min(240, remaining),
        updated,
    )


def pursuit_protected_chunks(sim, unload_candidates=(), *, budget=PURSUIT_STREAMING_CHUNK_BUDGET):
    """Retain the highest-value live pursuit chunks without a global scan."""

    state = _state(sim)
    candidates = {
        chunk
        for chunk in (_chunk_key(raw) for raw in tuple(unload_candidates or ()))
        if chunk is not None
    }
    state["protected_chunks"] = set()
    state["protected_reasons"] = {}
    state["last_rows"] = ()
    now = _safe_int(getattr(sim, "tick", 0), 0)
    stats = {
        "tick": now,
        "candidate_chunk_count": len(candidates),
        "indexed_actor_count": 0,
        "context_count": 0,
        "eligible_context_count": 0,
        "protected_chunk_count": 0,
    }
    state["stats"] = stats
    try:
        budget = max(0, int(budget))
    except (TypeError, ValueError):
        budget = PURSUIT_STREAMING_CHUNK_BUDGET
    if not candidates or budget <= 0:
        return set()

    rows = []
    for chunk in sorted(candidates):
        best = None
        reasons = set()
        for eid in tuple(sim.entity_ids_in_chunk(chunk) or ()):
            stats["indexed_actor_count"] += 1
            for _owner_kind, _field, _owner, context in _actor_context_slots(sim, int(eid)):
                stats["context_count"] += 1
                if not is_purposeful_observation(context, active_only=True):
                    continue
                live_until = purposeful_observation_live_until(context)
                if live_until is None or now > int(live_until):
                    continue
                stats["eligible_context_count"] += 1
                purpose = observation_context_purpose(context) or "purposeful_observation"
                reasons.add(purpose)
                rank = _context_rank(context, now=now)
                candidate = (rank, -int(eid), purpose, int(eid), int(live_until))
                if best is None or candidate > best:
                    best = candidate
        if best is None:
            continue
        rank, _negative_eid, purpose, eid, live_until = best
        rows.append({
            "chunk": chunk,
            "rank": rank,
            "distance": _focus_distance(sim, chunk),
            "purpose": purpose,
            "actor_eid": eid,
            "live_until_tick": live_until,
            "reasons": tuple(sorted(reasons)),
        })

    rows.sort(
        key=lambda row: (
            -row["rank"][0],
            -row["rank"][1],
            -row["rank"][2],
            -row["rank"][3],
            row["distance"],
            row["chunk"],
        )
    )
    selected = rows[:budget]
    protected = {row["chunk"] for row in selected}
    state["protected_chunks"] = set(protected)
    state["protected_reasons"] = {
        row["chunk"]: tuple(row["reasons"])
        for row in selected
    }
    state["last_rows"] = tuple(dict(row) for row in selected)
    stats["protected_chunk_count"] = len(protected)
    return protected


def prepare_pursuit_chunk_unload(sim, chunk):
    """Tag pursuit contexts just before their actor enters a chunk snapshot."""

    key = _chunk_key(chunk)
    if key is None:
        return {"chunk": None, "marked_contexts": 0, "marked_actors": ()}
    now = _safe_int(getattr(sim, "tick", 0), 0)
    marked = 0
    actors = set()
    for eid in tuple(sim.entity_ids_in_chunk(key) or ()):
        for owner_kind, field, owner, context in tuple(_actor_context_slots(sim, int(eid))):
            updated = mark_purposeful_observation_offscreen(
                context,
                current_tick=now,
                chunk=key,
            )
            if updated is context:
                continue
            _assign_context(owner_kind, field, owner, updated)
            marked += 1
            actors.add(int(eid))
    return {
        "chunk": key,
        "marked_contexts": marked,
        "marked_actors": tuple(sorted(actors)),
    }


def settle_pursuit_chunk_restore(sim, chunk, restored_eids):
    """Settle every restored observation once, preserving unsimulated routes."""

    key = _chunk_key(chunk)
    now = _safe_int(getattr(sim, "tick", 0), 0)
    resumed = 0
    expired = 0
    settled_actors = set()
    for raw_eid in tuple(restored_eids or ()):
        try:
            eid = int(raw_eid)
        except (TypeError, ValueError):
            continue
        ai = sim.ecs.get(AI).get(eid)
        for owner_kind, field, owner, context in tuple(_actor_context_slots(sim, eid)):
            updated, status = settle_purposeful_observation_offscreen(
                sim,
                context,
                current_tick=now,
            )
            if status == "unchanged":
                continue
            _assign_context(owner_kind, field, owner, updated)
            settled_actors.add(eid)
            if status == "resumed":
                resumed += 1
            elif status == "expired":
                expired += 1
        if ai is not None and str(getattr(ai, "state", "") or "").strip().lower() == "investigating":
            has_active_investigation = any(
                is_purposeful_observation(getattr(ai, field, None), active_only=True)
                for field in AI_CONTEXT_FIELDS
            )
            if not has_active_investigation:
                ai.state = "idle"
                ai.target = None
                ai.target_eid = None
                will = sim.ecs.get(NPCWill).get(eid)
                if will is not None and str(getattr(will, "intent", "") or "").strip().lower() == "investigating":
                    will.intent = "idle"
                    will.target = None
                    will.target_eid = None
                    will.last_tick = now
        drone = sim.ecs.get(DroneState).get(eid)
        if drone is not None and not is_purposeful_observation(
            getattr(drone, "observation_context", None),
            active_only=True,
        ):
            metadata = getattr(drone, "source_metadata", None)
            if isinstance(metadata, dict):
                metadata.pop("program_seen_hostile_eid", None)
                metadata["drone_watch_phase"] = "lost"

    attention = getattr(sim, "actor_attention_state", None)
    if isinstance(attention, dict) and settled_actors:
        attention["last_refresh_tick"] = None
    return {
        "chunk": key,
        "resumed_contexts": resumed,
        "expired_contexts": expired,
        "settled_actors": tuple(sorted(settled_actors)),
    }


__all__ = [
    "PURSUIT_STREAMING_CHUNK_BUDGET",
    "prepare_pursuit_chunk_unload",
    "pursuit_protected_chunks",
    "pursuit_streaming_state",
    "settle_pursuit_chunk_restore",
]
