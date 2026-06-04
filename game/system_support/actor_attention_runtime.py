"""Runtime attention queues for NPC systems.

The helpers in this module keep expensive NPC systems actor-centric: rich logic
still runs near the player and hot sites, while offscreen coasting actors wait
for a due tick or resolve through compact seams.
"""

from __future__ import annotations

from collections import defaultdict

from game.components import (
    AI,
    MovementThrottle,
    NPCNeeds,
    NPCSettlement,
    PlayerAssets,
    PlayerControlled,
    Position,
    SuppressionState,
    Vitality,
)


ATTENTION_FAMILIES = ("will", "move", "settlement")
ATTENTION_SCOPES = ("full", "warm", "compressed", "dormant")

COMPRESSED_ACTIVE_STATES = {
    "chasing",
    "evading_authority",
    "helping_victim",
    "protecting",
    "reporting_incident",
    "seeking_medical_aid",
    "seeking_safe_spot",
    "seeking_safety",
    "seeking_shelter",
    "warning",
}

MOVING_STATES_FOR_ATTENTION = COMPRESSED_ACTIVE_STATES | {
    "casing_target",
    "committing_property_crime",
    "following",
    "holding",
    "investigating",
    "lounging",
    "patrolling",
    "rendezvousing_crew",
    "resting",
    "scavenging",
    "seeking_companionship",
    "seeking_criminal_affiliation",
    "seeking_social",
    "seeking_street_appraiser",
    "seeking_street_buyer",
    "selling_scavenged",
    "socializing",
    "soliciting_player",
    "working",
}

COMPRESSED_ROUTINE_MOVE_STATES = {
    "lounging",
    "patrolling",
    "resting",
    "scavenging",
    "seeking_companionship",
    "seeking_social",
    "selling_scavenged",
    "socializing",
    "working",
}

FULL_DISTANCE = 8
FULL_LOS_DISTANCE = 14
URGENT_DEFAULT_TTL = 12


def _empty_stats():
    return {
        "tick": -1,
        "scope_counts": {scope: 0 for scope in ATTENTION_SCOPES},
        "due_counts": {family: 0 for family in ATTENTION_FAMILIES},
        "urgent_counts": {family: 0 for family in ATTENTION_FAMILIES},
        "scheduled_counts": {family: 0 for family in ATTENTION_FAMILIES},
        "compact_resolved": {},
        "full_resolved": 0,
        "warm_resolved": 0,
        "dormant_skipped": 0,
        "settlement_cache_hits": 0,
        "settlement_cache_misses": 0,
    }


def _new_state():
    return {
        "sources_tick": None,
        "full_chunks": set(),
        "warm_chunks": set(),
        "chunk_reasons": {},
        "due": {family: {} for family in ATTENTION_FAMILIES},
        "due_membership": {family: {} for family in ATTENTION_FAMILIES},
        "due_reasons": {family: {} for family in ATTENTION_FAMILIES},
        "urgent": {family: {} for family in ATTENTION_FAMILIES},
        "urgent_reasons": {family: {} for family in ATTENTION_FAMILIES},
        "last_refresh_tick": None,
        "settlement_candidate_cache": {"home": {}, "work": {}, "arrival": {}},
        "stats": _empty_stats(),
    }


def actor_attention_state(sim):
    state = getattr(sim, "actor_attention_state", None)
    if not isinstance(state, dict):
        state = _new_state()
        sim.actor_attention_state = state
    state.setdefault("full_chunks", set())
    state.setdefault("warm_chunks", set())
    state.setdefault("chunk_reasons", {})
    state.setdefault("due", {})
    state.setdefault("due_membership", {})
    state.setdefault("due_reasons", {})
    state.setdefault("urgent", {})
    state.setdefault("urgent_reasons", {})
    for family in ATTENTION_FAMILIES:
        state["due"].setdefault(family, {})
        state["due_membership"].setdefault(family, {})
        state["due_reasons"].setdefault(family, {})
        state["urgent"].setdefault(family, {})
        state["urgent_reasons"].setdefault(family, {})
    cache = state.setdefault("settlement_candidate_cache", {})
    cache.setdefault("home", {})
    cache.setdefault("work", {})
    cache.setdefault("arrival", {})
    stats = state.get("stats")
    if not isinstance(stats, dict):
        state["stats"] = _empty_stats()
    return state


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _chunk_for_xy(sim, x, y):
    try:
        return tuple(sim.chunk_coords(int(x), int(y)))
    except (AttributeError, TypeError, ValueError):
        return None


def _chunk_for_pos(sim, pos):
    if pos is None:
        return None
    return _chunk_for_xy(sim, getattr(pos, "x", 0), getattr(pos, "y", 0))


def _normalize_chunk(chunk):
    if not isinstance(chunk, (tuple, list)) or len(chunk) < 2:
        return None
    try:
        return (int(chunk[0]), int(chunk[1]))
    except (TypeError, ValueError):
        return None


def _property_chunk(sim, prop):
    if not isinstance(prop, dict):
        return None
    metadata = prop.get("metadata", {}) if isinstance(prop.get("metadata"), dict) else {}
    chunk = _normalize_chunk(prop.get("chunk") or metadata.get("chunk"))
    if chunk is not None:
        return chunk
    return _chunk_for_xy(sim, prop.get("x", 0), prop.get("y", 0))


def _add_chunk_reason(reasons, chunk, reason):
    chunk = _normalize_chunk(chunk)
    if chunk is None:
        return
    bucket = reasons.setdefault(chunk, set())
    bucket.add(str(reason or "attention"))


def _active_player_chunk(sim):
    chunk = _normalize_chunk(getattr(sim, "active_chunk_coord", None))
    if chunk is not None:
        return chunk
    player_pos = _player_position(sim)
    return _chunk_for_pos(sim, player_pos)


def _player_position(sim):
    player_eid = getattr(sim, "player_eid", None)
    if player_eid is None:
        return None
    return sim.ecs.get(Position).get(player_eid)


def _manhattan(left_x, left_y, right_x, right_y):
    return abs(int(left_x) - int(right_x)) + abs(int(left_y) - int(right_y))


def _same_floor_player_distance(sim, pos):
    player_pos = _player_position(sim)
    if player_pos is None or pos is None:
        return None
    if int(getattr(player_pos, "z", 0) or 0) != int(getattr(pos, "z", 0) or 0):
        return None
    return _manhattan(
        getattr(pos, "x", 0),
        getattr(pos, "y", 0),
        getattr(player_pos, "x", 0),
        getattr(player_pos, "y", 0),
    )


def _has_player_los(sim, pos):
    player_pos = _player_position(sim)
    if player_pos is None or pos is None:
        return False
    try:
        from engine.visibility import has_line_of_sight

        return bool(
            has_line_of_sight(
                sim,
                int(getattr(pos, "x", 0)),
                int(getattr(pos, "y", 0)),
                int(getattr(pos, "z", 0)),
                int(getattr(player_pos, "x", 0)),
                int(getattr(player_pos, "y", 0)),
                int(getattr(player_pos, "z", 0)),
            )
        )
    except Exception:
        return False


def _detail_for_pos(sim, pos):
    if pos is None or not hasattr(sim, "detail_for_xy"):
        return "unloaded"
    try:
        return str(sim.detail_for_xy(int(pos.x), int(pos.y))).strip().lower() or "unloaded"
    except (TypeError, ValueError):
        return "unloaded"


def _dialogue_npc_eid(sim):
    dialog = getattr(sim, "dialog_ui", None)
    if not isinstance(dialog, dict) or not bool(dialog.get("open")):
        return None
    for key in ("npc_eid", "speaker_eid", "target_eid"):
        try:
            value = int(dialog.get(key))
        except (TypeError, ValueError):
            continue
        if value >= 0:
            return value
    return None


def _state_key(ai):
    return str(getattr(ai, "state", "") or "").strip().lower()


def _role_key(ai):
    return str(getattr(ai, "role", "") or "").strip().lower()


def _actor_has_critical_need(sim, eid):
    needs = sim.ecs.get(NPCNeeds).get(eid)
    if needs is None:
        return False
    if getattr(needs, "critical", None):
        return True
    try:
        if float(getattr(needs, "energy", 100.0) or 100.0) <= 18.0:
            return True
        if float(getattr(needs, "safety", 100.0) or 100.0) <= 18.0:
            return True
    except (TypeError, ValueError):
        return False
    return False


def _actor_is_urgent(sim, eid, ai=None, pos=None):
    if sim.ecs.get(PlayerControlled).get(eid) is not None:
        return True
    vitality = sim.ecs.get(Vitality).get(eid)
    if vitality is not None and bool(getattr(vitality, "downed", False)):
        return True
    suppression = sim.ecs.get(SuppressionState).get(eid)
    if suppression is not None and bool(getattr(suppression, "surrendered", False)):
        return True
    if _actor_has_critical_need(sim, eid):
        return True
    ai = ai if ai is not None else sim.ecs.get(AI).get(eid)
    state = _state_key(ai)
    if _role_key(ai) == "wildlife":
        return True
    if state in COMPRESSED_ACTIVE_STATES:
        return True
    player_eid = getattr(sim, "player_eid", None)
    if player_eid is not None and getattr(ai, "target_eid", None) == player_eid:
        return True
    return False


def _settlement_active(newcomer):
    if newcomer is None:
        return False
    housing = str(getattr(newcomer, "housing_status", "") or "").strip().lower()
    employment = str(getattr(newcomer, "employment_status", "") or "").strip().lower()
    if housing in {"unhoused", "drifting", "lodging", "shelter"}:
        return True
    if employment != "employed":
        return True
    if str(getattr(newcomer, "life_review_stage", "") or "").strip():
        return True
    if str(getattr(newcomer, "life_goal", "") or "").strip().lower() not in {"", "holding_steady"}:
        return True
    return False


def _collect_attention_sources(sim, state):
    full_chunks = set()
    warm_chunks = set()
    chunk_reasons = {}

    active = _active_player_chunk(sim)
    if active is not None:
        full_chunks.add(active)
        _add_chunk_reason(chunk_reasons, active, "player")

    player_eid = getattr(sim, "player_eid", None)
    if player_eid is not None:
        assets = sim.ecs.get(PlayerAssets).get(player_eid)
        owned_ids = {
            str(raw).strip()
            for raw in tuple(getattr(assets, "owned_property_ids", ()) or ())
            if str(raw).strip()
        } if assets is not None else set()
        for prop_id in sorted(owned_ids):
            prop = getattr(sim, "properties", {}).get(prop_id)
            chunk = _property_chunk(sim, prop)
            if chunk is not None:
                warm_chunks.add(chunk)
                _add_chunk_reason(chunk_reasons, chunk, "player_business")

    opportunities = getattr(sim, "world_traits", {}).get("opportunities", {})
    tracked = opportunities.get("tracked_targets", {}) if isinstance(opportunities, dict) else {}
    if isinstance(tracked, dict):
        for row in tuple(tracked.values()):
            if not isinstance(row, dict):
                continue
            chunk = _normalize_chunk(row.get("chunk"))
            if chunk is None:
                prop = getattr(sim, "properties", {}).get(str(row.get("property_id", "") or "").strip())
                chunk = _property_chunk(sim, prop)
            if chunk is None:
                continue
            warm_chunks.add(chunk)
            reason = str(row.get("tracking_reason", "") or "opportunity").strip() or "opportunity"
            _add_chunk_reason(chunk_reasons, chunk, f"opportunity:{reason}")

    try:
        from game.system_support.fire_runtime import fire_protected_chunks

        for chunk in tuple(fire_protected_chunks(sim) or ()):
            chunk = _normalize_chunk(chunk)
            if chunk is not None:
                warm_chunks.add(chunk)
                _add_chunk_reason(chunk_reasons, chunk, "fire")
    except Exception:
        pass

    try:
        from game.incident_runtime import incident_registry

        now = _safe_int(getattr(sim, "tick", 0), 0)
        for incident in tuple((incident_registry(sim) or {}).values()):
            if not isinstance(incident, dict):
                continue
            tick = _safe_int(
                incident.get("last_tick", incident.get("tick", incident.get("created_tick", now))),
                now,
            )
            if now - tick > 900:
                continue
            chunk = _normalize_chunk(incident.get("chunk"))
            if chunk is None:
                x = incident.get("x", incident.get("scene_x", incident.get("target_x")))
                y = incident.get("y", incident.get("scene_y", incident.get("target_y")))
                if x is not None and y is not None:
                    chunk = _chunk_for_xy(sim, x, y)
            if chunk is not None:
                warm_chunks.add(chunk)
                _add_chunk_reason(chunk_reasons, chunk, "incident")
    except Exception:
        pass

    state["full_chunks"] = full_chunks
    state["warm_chunks"] = warm_chunks - full_chunks
    state["chunk_reasons"] = chunk_reasons
    state["sources_tick"] = _safe_int(getattr(sim, "tick", 0), 0)


def _due_delay_for_scope(scope, state_key, *, family):
    state_key = str(state_key or "").strip().lower()
    if family == "settlement":
        if scope == "full":
            return 30
        if scope == "warm":
            return 60
        if scope == "compressed":
            return 120
        return 300
    if family == "move":
        if state_key in {"protecting", "chasing", "seeking_safety", "evading_authority"}:
            return 2 if scope in {"full", "warm"} else 6
        if state_key in {"reporting_incident", "helping_victim", "warning"}:
            return 6 if scope in {"full", "warm"} else 12
        if state_key in {"seeking_medical_aid", "seeking_safe_spot", "seeking_shelter"}:
            return 12 if scope in {"full", "warm"} else 24
        if scope == "warm":
            return 30
        if scope == "compressed":
            return 120
        return 300
    if state_key in {"protecting", "chasing", "seeking_safety", "evading_authority"}:
        return 2 if scope in {"full", "warm"} else 6
    if state_key in {"reporting_incident", "helping_victim", "warning"}:
        return 6 if scope in {"full", "warm"} else 12
    if state_key in {"seeking_medical_aid", "seeking_safe_spot", "seeking_shelter"}:
        return 12 if scope in {"full", "warm"} else 24
    if scope == "full":
        return 0
    if scope == "warm":
        return 30
    if scope == "compressed":
        return 120
    return 300


def schedule_actor_due(sim, eid, family, delay_ticks=0, reason=""):
    family = str(family or "").strip().lower()
    if family not in ATTENTION_FAMILIES:
        return None
    try:
        eid = int(eid)
    except (TypeError, ValueError):
        return None
    state = actor_attention_state(sim)
    now = _safe_int(getattr(sim, "tick", 0), 0)
    due_tick = max(0, now + _safe_int(delay_ticks, 0))
    membership = state["due_membership"][family]
    old_tick = membership.get(eid)
    if old_tick == due_tick:
        return due_tick
    if old_tick is not None:
        bucket = state["due"][family].get(old_tick)
        if isinstance(bucket, set):
            bucket.discard(eid)
            if not bucket:
                state["due"][family].pop(old_tick, None)
    state["due"][family].setdefault(due_tick, set()).add(eid)
    membership[eid] = due_tick
    state["due_reasons"][family][eid] = str(reason or "")
    state["stats"].setdefault("scheduled_counts", {}).setdefault(family, 0)
    state["stats"]["scheduled_counts"][family] += 1
    return due_tick


def clear_actor_attention(sim, eid=None, family=None):
    state = actor_attention_state(sim)
    families = ATTENTION_FAMILIES if family in {None, "all"} else (str(family).strip().lower(),)
    if eid is None:
        for fam in families:
            if fam not in ATTENTION_FAMILIES:
                continue
            state["due"][fam].clear()
            state["due_membership"][fam].clear()
            state["due_reasons"][fam].clear()
            state["urgent"][fam].clear()
            state["urgent_reasons"][fam].clear()
        return True
    try:
        eid = int(eid)
    except (TypeError, ValueError):
        return False
    cleared = False
    for fam in families:
        if fam not in ATTENTION_FAMILIES:
            continue
        old_tick = state["due_membership"][fam].pop(eid, None)
        if old_tick is not None:
            bucket = state["due"][fam].get(old_tick)
            if isinstance(bucket, set):
                bucket.discard(eid)
                if not bucket:
                    state["due"][fam].pop(old_tick, None)
            cleared = True
        state["due_reasons"][fam].pop(eid, None)
        state["urgent"][fam].pop(eid, None)
        state["urgent_reasons"][fam].pop(eid, None)
    return cleared


def mark_actor_urgent(sim, eid, family="all", reason="", ttl_ticks=URGENT_DEFAULT_TTL):
    try:
        eid = int(eid)
    except (TypeError, ValueError):
        return False
    state = actor_attention_state(sim)
    families = ATTENTION_FAMILIES if family in {None, "", "all"} else (str(family).strip().lower(),)
    now = _safe_int(getattr(sim, "tick", 0), 0)
    until_tick = now + max(1, _safe_int(ttl_ticks, URGENT_DEFAULT_TTL))
    marked = False
    for fam in families:
        if fam not in ATTENTION_FAMILIES:
            continue
        state["urgent"][fam][eid] = until_tick
        state["urgent_reasons"][fam][eid] = str(reason or "")
        schedule_actor_due(sim, eid, fam, delay_ticks=0, reason=reason or "urgent")
        marked = True
    return marked


def pop_due_actors(sim, family, *, current_tick=None, limit=None):
    family = str(family or "").strip().lower()
    if family not in ATTENTION_FAMILIES:
        return tuple()
    state = actor_attention_state(sim)
    tick = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick, 0)
    ready = set()
    due = state["due"][family]
    membership = state["due_membership"][family]
    for due_tick in sorted(raw for raw in tuple(due.keys()) if int(raw) <= tick):
        bucket = due.pop(due_tick, set())
        for eid in tuple(bucket or ()):
            if membership.get(eid) == due_tick:
                membership.pop(eid, None)
            ready.add(int(eid))
    urgent = state["urgent"][family]
    for eid, until_tick in tuple(urgent.items()):
        if int(until_tick) < tick:
            urgent.pop(eid, None)
            state["urgent_reasons"][family].pop(eid, None)
            continue
        ready.add(int(eid))
        urgent.pop(eid, None)
        state["urgent_reasons"][family].pop(eid, None)
    ordered = tuple(sorted(ready))
    if limit is not None:
        ordered = ordered[: max(0, int(limit))]
    stats = state["stats"]
    stats.setdefault("due_counts", {}).setdefault(family, 0)
    stats["due_counts"][family] += len(ordered)
    return ordered


def attention_scope_for_actor(sim, eid, *, pos=None, ai=None):
    state = actor_attention_state(sim)
    try:
        eid = int(eid)
    except (TypeError, ValueError):
        return {"scope": "dormant", "reasons": ("invalid_actor",)}
    positions = sim.ecs.get(Position)
    pos = pos if pos is not None else positions.get(eid)
    ai = ai if ai is not None else sim.ecs.get(AI).get(eid)
    reasons = []
    player_eid = getattr(sim, "player_eid", None)
    if eid == player_eid or sim.ecs.get(PlayerControlled).get(eid) is not None:
        return {"scope": "full", "reasons": ("player",)}
    if _dialogue_npc_eid(sim) == eid:
        return {"scope": "full", "reasons": ("dialogue",)}
    if pos is None:
        return {"scope": "dormant", "reasons": ("no_position",)}
    chunk = _chunk_for_pos(sim, pos)
    if chunk in state.get("full_chunks", set()):
        reasons.append("player_chunk")
    distance = _same_floor_player_distance(sim, pos)
    if distance is not None and distance <= FULL_DISTANCE:
        reasons.append("player_proximity")
    elif distance is not None and distance <= FULL_LOS_DISTANCE and _has_player_los(sim, pos):
        reasons.append("player_los")
    if player_eid is not None and getattr(ai, "target_eid", None) == player_eid:
        reasons.append("targets_player")
    if _actor_is_urgent(sim, eid, ai=ai, pos=pos) and distance is not None and distance <= FULL_LOS_DISTANCE:
        reasons.append("urgent_near_player")
    if reasons:
        return {"scope": "full", "reasons": tuple(sorted(set(reasons)))}

    warm_chunks = state.get("warm_chunks", set())
    if chunk in warm_chunks:
        chunk_reasons = state.get("chunk_reasons", {}).get(chunk, set())
        warm_reasons = tuple(sorted(str(reason) for reason in tuple(chunk_reasons or ()) if str(reason).strip()))
        return {"scope": "warm", "reasons": warm_reasons or ("warm_chunk",)}

    state_key = _state_key(ai)
    newcomer = sim.ecs.get(NPCSettlement).get(eid)
    if state_key in COMPRESSED_ACTIVE_STATES or _settlement_active(newcomer):
        return {"scope": "compressed", "reasons": (state_key or "active_goal",)}
    if _actor_has_critical_need(sim, eid):
        return {"scope": "compressed", "reasons": ("critical_need",)}
    return {"scope": "dormant", "reasons": ("coasting",)}


def _seed_actor_due_if_needed(sim, eid, scope, ai, newcomer):
    state = actor_attention_state(sim)
    state_key = _state_key(ai)
    if state["due_membership"]["will"].get(eid) is None and scope in {"full", "warm", "compressed"}:
        schedule_actor_due(
            sim,
            eid,
            "will",
            delay_ticks=_due_delay_for_scope(scope, state_key, family="will"),
            reason=f"{scope}:will",
        )
    if (
        state_key in MOVING_STATES_FOR_ATTENTION
        and (getattr(ai, "target", None) is not None or getattr(ai, "target_eid", None) is not None)
        and state["due_membership"]["move"].get(eid) is None
        and scope in {"full", "warm", "compressed"}
    ):
        throttle = sim.ecs.get(MovementThrottle).get(eid)
        if scope == "compressed" and state_key in COMPRESSED_ROUTINE_MOVE_STATES:
            delay = _due_delay_for_scope(scope, state_key, family="move")
        elif throttle is not None and scope == "full":
            delay = max(0, _safe_int(getattr(throttle, "next_move_tick", 0), 0) - _safe_int(getattr(sim, "tick", 0), 0))
        else:
            delay = _due_delay_for_scope(scope, state_key, family="move")
        schedule_actor_due(sim, eid, "move", delay_ticks=delay, reason=f"{scope}:move")
    if newcomer is not None and _settlement_active(newcomer) and state["due_membership"]["settlement"].get(eid) is None:
        schedule_actor_due(
            sim,
            eid,
            "settlement",
            delay_ticks=_due_delay_for_scope(scope, state_key, family="settlement"),
            reason=f"{scope}:settlement",
        )


def refresh_actor_attention(sim, *, player_eid=None):
    state = actor_attention_state(sim)
    tick = _safe_int(getattr(sim, "tick", 0), 0)
    if player_eid is not None:
        sim.player_eid = player_eid
    last_refresh = state.get("last_refresh_tick")
    live_timeskip = getattr(sim, "live_timeskip", None)
    refresh_interval = 60 if isinstance(live_timeskip, dict) and bool(live_timeskip.get("active")) else 1
    if last_refresh is not None and tick - _safe_int(last_refresh, -10_000) < refresh_interval:
        return state
    _collect_attention_sources(sim, state)
    stats = _empty_stats()
    stats["tick"] = tick
    ais = sim.ecs.get(AI)
    positions = sim.ecs.get(Position)
    settlements = sim.ecs.get(NPCSettlement)
    eids = set(positions.keys()) | set(ais.keys()) | set(settlements.keys())
    for eid in tuple(sorted(int(raw) for raw in eids if raw is not None)):
        ai = ais.get(eid)
        pos = positions.get(eid)
        scope_info = attention_scope_for_actor(sim, eid, pos=pos, ai=ai)
        scope = str(scope_info.get("scope", "dormant") or "dormant")
        if scope not in ATTENTION_SCOPES:
            scope = "dormant"
        stats["scope_counts"][scope] += 1
        if scope == "dormant":
            stats["dormant_skipped"] += 1
            clear_actor_attention(sim, eid, family="move")
        _seed_actor_due_if_needed(sim, eid, scope, ai, settlements.get(eid))
    for family in ATTENTION_FAMILIES:
        stats["due_counts"][family] = sum(len(bucket or ()) for bucket in state["due"][family].values())
        stats["urgent_counts"][family] = len(state["urgent"][family])
    state["stats"] = stats
    state["last_refresh_tick"] = tick
    return state


def note_attention_resolution(sim, scope, kind, *, compact=False):
    state = actor_attention_state(sim)
    stats = state.setdefault("stats", _empty_stats())
    scope = str(scope or "").strip().lower()
    if compact:
        bucket = stats.setdefault("compact_resolved", {})
        key = str(kind or "unknown").strip().lower() or "unknown"
        bucket[key] = int(bucket.get(key, 0) or 0) + 1
    elif scope == "full":
        stats["full_resolved"] = int(stats.get("full_resolved", 0) or 0) + 1
    elif scope == "warm":
        stats["warm_resolved"] = int(stats.get("warm_resolved", 0) or 0) + 1


def note_settlement_cache(sim, *, hit):
    state = actor_attention_state(sim)
    stats = state.setdefault("stats", _empty_stats())
    key = "settlement_cache_hits" if hit else "settlement_cache_misses"
    stats[key] = int(stats.get(key, 0) or 0) + 1


def attention_stats(sim):
    return dict(actor_attention_state(sim).get("stats", {}) or {})
