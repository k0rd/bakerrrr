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
from game.property_runtime import property_is_vehicle, property_supports_business_relevance


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
SOCIAL_WARMTH_CHUNK_BUDGET = 3
BUILDING_WARMTH_CHUNK_BUDGET = 3
AREA_WARMTH_CHUNK_BUDGET = BUILDING_WARMTH_CHUNK_BUDGET
PLAYER_BUSINESS_WARMTH_SCORE = 2.4
PLAYER_VEHICLE_WARMTH_SCORE = 2.2
KNOWN_QUEST_GIVER_WARMTH_SCORE = 2.8
KNOWN_QUEST_TARGET_WARMTH_SCORE = 2.35
KNOWN_QUEST_LOCATION_WARMTH_SCORE = 2.25
SOCIAL_WARMTH_MIN_SCORE = 0.08
SOCIAL_WARMTH_MAX_SCORE = 3.0
SOCIAL_WARMTH_SPEND_FRACTION = 0.42
SOCIAL_WARMTH_SPEND_MIN = 0.24
SOCIAL_WARMTH_CHUNK_EXTRA_CAP = 0.45
SOCIAL_WARMTH_MAX_ROWS = 48


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
        "social_warmth_actors": 0,
        "area_warmth_areas": 0,
        "social_warmth_protected_chunks": 0,
        "area_warmth_protected_chunks": 0,
        "opportunity_protected_chunks": 0,
        "pursuit_protected_chunks": 0,
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
        "social_warmth": {},
        "area_warmth": {},
        "known_opportunity_actor_rows": {},
        "known_opportunity_area_rows": {},
        "social_warmth_protected_chunks": set(),
        "area_warmth_protected_chunks": set(),
        "opportunity_protected_chunks": set(),
        "social_warmth_last_protected": (),
        "area_warmth_last_protected": (),
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
    if not isinstance(state.get("social_warmth"), dict):
        state["social_warmth"] = {}
    if not isinstance(state.get("area_warmth"), dict):
        state["area_warmth"] = {}
    if not isinstance(state.get("known_opportunity_actor_rows"), dict):
        state["known_opportunity_actor_rows"] = {}
    if not isinstance(state.get("known_opportunity_area_rows"), dict):
        state["known_opportunity_area_rows"] = {}
    if not isinstance(state.get("social_warmth_protected_chunks"), set):
        state["social_warmth_protected_chunks"] = set(state.get("social_warmth_protected_chunks") or ())
    if not isinstance(state.get("area_warmth_protected_chunks"), set):
        state["area_warmth_protected_chunks"] = set(state.get("area_warmth_protected_chunks") or ())
    if not isinstance(state.get("opportunity_protected_chunks"), set):
        state["opportunity_protected_chunks"] = set(state.get("opportunity_protected_chunks") or ())
    state.setdefault("social_warmth_last_protected", ())
    state.setdefault("area_warmth_last_protected", ())
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


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _unit_float(value, default=0.0):
    return max(0.0, min(1.0, _safe_float(value, default)))


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


def _bond_strength_score(post_bond):
    if not isinstance(post_bond, dict):
        return 0.0
    trust = _unit_float(post_bond.get("trust"))
    closeness = _unit_float(post_bond.get("closeness"))
    protectiveness = _unit_float(post_bond.get("protectiveness"))
    kind = str(post_bond.get("kind", "") or "").strip().lower()
    kind_bonus = {
        "family": 0.22,
        "partner": 0.2,
        "friend": 0.16,
        "owner": 0.12,
        "workplace": 0.12,
        "coworker": 0.1,
        "neighbor": 0.04,
        "contact": 0.04,
        "local": 0.03,
    }.get(kind, 0.0)
    return min(1.0, (trust * 0.38) + (closeness * 0.34) + (protectiveness * 0.22) + kind_bonus)


def _social_warmth_rows(state):
    rows = state.setdefault("social_warmth", {})
    if not isinstance(rows, dict):
        rows = {}
        state["social_warmth"] = rows
    return rows


def _area_warmth_rows(state):
    rows = state.setdefault("area_warmth", {})
    if not isinstance(rows, dict):
        rows = {}
        state["area_warmth"] = rows
    return rows


def _prune_social_warmth(sim, state=None, *, live_only=False):
    state = actor_attention_state(sim) if state is None else state
    rows = _social_warmth_rows(state)
    positions = sim.ecs.get(Position) if live_only else None
    for raw_eid, row in tuple(rows.items()):
        try:
            eid = int(raw_eid)
        except (TypeError, ValueError):
            rows.pop(raw_eid, None)
            continue
        if not isinstance(row, dict):
            rows.pop(raw_eid, None)
            continue
        score = _safe_float(row.get("score"), 0.0)
        if score < SOCIAL_WARMTH_MIN_SCORE:
            rows.pop(raw_eid, None)
            continue
        if live_only and positions.get(eid) is None:
            rows.pop(raw_eid, None)
    if len(rows) <= SOCIAL_WARMTH_MAX_ROWS:
        return
    ordered = sorted(
        (
            (_safe_float(row.get("score"), 0.0), raw_eid)
            for raw_eid, row in rows.items()
            if isinstance(row, dict)
        ),
        key=lambda item: (-item[0], str(item[1])),
    )
    keep = {raw_eid for _score, raw_eid in ordered[:SOCIAL_WARMTH_MAX_ROWS]}
    for raw_eid in tuple(rows.keys()):
        if raw_eid not in keep:
            rows.pop(raw_eid, None)


def _prune_area_warmth(sim, state=None):
    state = actor_attention_state(sim) if state is None else state
    rows = _area_warmth_rows(state)
    for key, row in tuple(rows.items()):
        if not isinstance(row, dict):
            rows.pop(key, None)
            continue
        chunk = _normalize_chunk(row.get("chunk"))
        if chunk is None:
            rows.pop(key, None)
            continue
        score = _safe_float(row.get("score"), 0.0)
        if score < SOCIAL_WARMTH_MIN_SCORE:
            rows.pop(key, None)
            continue
        row["chunk"] = chunk
    if len(rows) <= SOCIAL_WARMTH_MAX_ROWS:
        return
    ordered = sorted(
        (
            (_safe_float(row.get("score"), 0.0), key)
            for key, row in rows.items()
            if isinstance(row, dict)
        ),
        key=lambda item: (-item[0], str(item[1])),
    )
    keep = {key for _score, key in ordered[:SOCIAL_WARMTH_MAX_ROWS]}
    for key in tuple(rows.keys()):
        if key not in keep:
            rows.pop(key, None)


def record_actor_social_warmth(
    sim,
    actor_eid,
    other_eid=None,
    reason="",
    trust_delta=0,
    closeness_delta=0,
    protectiveness_delta=0,
    post_bond=None,
):
    """Record runtime-only warmth for an actor after a meaningful bond change."""

    try:
        actor_id = int(actor_eid)
    except (TypeError, ValueError):
        return False
    player_eid = getattr(sim, "player_eid", None)
    try:
        if player_eid is not None and actor_id == int(player_eid):
            return False
    except (TypeError, ValueError):
        pass

    delta_score = (
        abs(_safe_float(trust_delta, 0.0)) * 0.9
        + abs(_safe_float(closeness_delta, 0.0)) * 0.8
        + abs(_safe_float(protectiveness_delta, 0.0)) * 0.55
    )
    if delta_score < 0.0001:
        return False

    bond_strength = _bond_strength_score(post_bond)
    bump = max(0.05, delta_score * (1.0 + bond_strength) + min(0.4, bond_strength * 0.22))
    state = actor_attention_state(sim)
    rows = _social_warmth_rows(state)
    existing = rows.get(actor_id)
    if not isinstance(existing, dict):
        existing = rows.get(str(actor_id), {})
    if not isinstance(existing, dict):
        existing = {}
    old_score = _safe_float(existing.get("score"), 0.0)
    new_score = min(SOCIAL_WARMTH_MAX_SCORE, old_score + bump)
    try:
        other_id = int(other_eid) if other_eid is not None else None
    except (TypeError, ValueError):
        other_id = None
    reason_text = str(reason or "").strip().lower() or "social_bond"
    old_reason_score = _safe_float(existing.get("reason_score"), 0.0)
    if old_reason_score > bump and str(existing.get("reason", "") or "").strip():
        reason_text = str(existing.get("reason", "") or "").strip().lower()
        reason_score = old_reason_score
    else:
        reason_score = bump
    row = {
        "actor_eid": actor_id,
        "other_eid": other_id,
        "score": new_score,
        "peak_score": max(_safe_float(existing.get("peak_score"), 0.0), new_score),
        "reason": reason_text,
        "reason_score": reason_score,
        "change_score": delta_score,
        "bond_strength": bond_strength,
        "last_tick": _safe_int(getattr(sim, "tick", 0), 0),
        "spend_count": _safe_int(existing.get("spend_count"), 0),
    }
    rows.pop(str(actor_id), None)
    rows[actor_id] = row
    _prune_social_warmth(sim, state)
    return True


def record_area_warmth(
    sim,
    chunk=None,
    x=None,
    y=None,
    reason="",
    score_delta=0.0,
    source_kind="",
    source_id=None,
):
    """Record runtime-only warmth for a directly observed place or scene."""

    area_chunk = _normalize_chunk(chunk)
    if area_chunk is None:
        area_chunk = _chunk_for_xy(sim, x, y)
    if area_chunk is None:
        return False

    bump = _safe_float(score_delta, 0.0)
    if bump <= 0.0:
        return False

    reason_text = str(reason or "").strip().lower() or "area"
    source_kind_text = str(source_kind or "").strip().lower()
    source_id_text = "" if source_id is None else str(source_id).strip()
    if source_kind_text and source_id_text:
        key = f"{source_kind_text}:{source_id_text}"
    else:
        key = f"{area_chunk[0]},{area_chunk[1]}:{reason_text}"

    state = actor_attention_state(sim)
    rows = _area_warmth_rows(state)
    existing = rows.get(key, {})
    if not isinstance(existing, dict):
        existing = {}
    old_score = _safe_float(existing.get("score"), 0.0)
    new_score = min(SOCIAL_WARMTH_MAX_SCORE, old_score + bump)
    old_reason_score = _safe_float(existing.get("reason_score"), 0.0)
    if old_reason_score > bump and str(existing.get("reason", "") or "").strip():
        reason_text = str(existing.get("reason", "") or "").strip().lower()
        reason_score = old_reason_score
    else:
        reason_score = bump
    rows[key] = {
        "chunk": area_chunk,
        "score": new_score,
        "peak_score": max(_safe_float(existing.get("peak_score"), 0.0), new_score),
        "reason": reason_text,
        "reason_score": reason_score,
        "source_kind": source_kind_text,
        "source_id": source_id_text,
        "last_tick": _safe_int(getattr(sim, "tick", 0), 0),
        "spend_count": _safe_int(existing.get("spend_count"), 0),
    }
    _prune_area_warmth(sim, state)
    return True


def _live_social_warmth_rows(sim, state=None):
    state = actor_attention_state(sim) if state is None else state
    _prune_social_warmth(sim, state, live_only=True)
    rows = _social_warmth_rows(state)
    positions = sim.ecs.get(Position)
    live = []
    for raw_eid, row in tuple(rows.items()):
        try:
            eid = int(raw_eid)
        except (TypeError, ValueError):
            continue
        if not isinstance(row, dict):
            continue
        pos = positions.get(eid)
        if pos is None:
            continue
        score = _safe_float(row.get("score"), 0.0)
        if score < SOCIAL_WARMTH_MIN_SCORE:
            continue
        live.append((eid, pos, score, row))
    live_by_eid = {eid: (eid, pos, score, row) for eid, pos, score, row in live}
    known_actor_rows, _known_area_rows = _known_opportunity_attention_rows(sim)
    for eid, pos, score, row in known_actor_rows:
        existing = live_by_eid.get(eid)
        if existing is None or float(score) > float(existing[2]):
            live_by_eid[eid] = (eid, pos, score, row)
    return tuple(live_by_eid[eid] for eid in sorted(live_by_eid))


def _live_area_warmth_rows(sim, state=None):
    state = actor_attention_state(sim) if state is None else state
    _prune_area_warmth(sim, state)
    rows = _area_warmth_rows(state)
    live = []
    for key, row in tuple(rows.items()):
        if not isinstance(row, dict):
            continue
        chunk = _normalize_chunk(row.get("chunk"))
        if chunk is None:
            continue
        score = _safe_float(row.get("score"), 0.0)
        if score < SOCIAL_WARMTH_MIN_SCORE:
            continue
        live.append((str(key), chunk, score, row))
    live_by_key = {str(key): (str(key), chunk, score, row) for key, chunk, score, row in live}
    _known_actor_rows, known_area_rows = _known_opportunity_attention_rows(sim)
    for key, chunk, score, row in known_area_rows:
        existing = live_by_key.get(str(key))
        if existing is None or float(score) > float(existing[2]):
            live_by_key[str(key)] = (str(key), chunk, score, row)
    return tuple(live_by_key[key] for key in sorted(live_by_key))


def _social_warmth_reason_for_actor(sim, state, eid):
    known_rows = state.get("known_opportunity_actor_rows", {})
    known_row = known_rows.get(eid) if isinstance(known_rows, dict) else None
    if not isinstance(known_row, dict) and isinstance(known_rows, dict):
        known_row = known_rows.get(str(eid))
    if isinstance(known_row, dict):
        reason = str(known_row.get("reason", "known_opportunity_target") or "known_opportunity_target").strip().lower()
        return f"social_warmth:{reason}"
    row = _social_warmth_rows(state).get(eid)
    if not isinstance(row, dict):
        row = _social_warmth_rows(state).get(str(eid))
    if not isinstance(row, dict):
        return None
    score = _safe_float(row.get("score"), 0.0)
    if score < SOCIAL_WARMTH_MIN_SCORE:
        return None
    reason = str(row.get("reason", "") or "").strip().lower() or "social_bond"
    return f"social_warmth:{reason}"


def social_warm_actor_eids(sim):
    return tuple(sorted(eid for eid, _pos, _score, _row in _live_social_warmth_rows(sim)))


def _spend_warmth_row(rows, key):
    row = rows.get(key)
    if not isinstance(row, dict):
        row = rows.get(str(key))
    if not isinstance(row, dict):
        return None
    score = _safe_float(row.get("score"), 0.0)
    spend = max(SOCIAL_WARMTH_SPEND_MIN, score * SOCIAL_WARMTH_SPEND_FRACTION)
    remaining = max(0.0, score - spend)
    if remaining < SOCIAL_WARMTH_MIN_SCORE:
        rows.pop(key, None)
        rows.pop(str(key), None)
        return 0.0
    row["score"] = remaining
    row["reason_score"] = min(_safe_float(row.get("reason_score"), remaining), remaining)
    row["spend_count"] = _safe_int(row.get("spend_count"), 0) + 1
    rows.pop(str(key), None)
    rows[key] = row
    return remaining


def _spend_social_warmth_row(rows, eid):
    return _spend_warmth_row(rows, eid)


def _warmth_item(kind, key, chunk, score, row, *, actor_eid=None, no_spend=False):
    reason = str((row or {}).get("reason", "") or "").strip().lower()
    if not reason:
        reason = "social_bond" if kind == "actor" else "area"
    item = {
        "kind": str(kind),
        "key": key,
        "chunk": chunk,
        "score": float(score),
        "row": row,
        "reason": reason,
        "priority": 0 if kind == "actor" else 1,
        "no_spend": bool(no_spend),
    }
    if actor_eid is not None:
        item["actor_eid"] = int(actor_eid)
    return item


def _rank_warmth_candidates(by_chunk):
    ranked = []
    for chunk, warm_rows in by_chunk.items():
        if not warm_rows:
            continue
        warm_rows = sorted(warm_rows, key=lambda item: (-float(item["score"]), int(item["priority"]), str(item["key"])))
        top_row = warm_rows[0]
        top_score = float(top_row["score"])
        extra = sum(float(item["score"]) for item in warm_rows[1:])
        chunk_score = top_score + min(SOCIAL_WARMTH_CHUNK_EXTRA_CAP, extra * 0.25)
        ranked.append({
            "chunk_score": float(chunk_score),
            "chunk": chunk,
            "top": top_row,
            "items": tuple(warm_rows),
            "actor_count": sum(1 for item in warm_rows if item["kind"] == "actor"),
            "area_count": sum(1 for item in warm_rows if item["kind"] == "area"),
        })
    return sorted(
        ranked,
        key=lambda item: (-float(item["chunk_score"]), int(item["top"]["priority"]), item["chunk"]),
    )


def _selected_warmth_last_row(selected_row):
    chunk = selected_row["chunk"]
    top = selected_row["top"]
    reason = str(top.get("reason", "") or "").strip().lower()
    last_row = {
        "kind": str(top.get("kind", "actor") or "actor"),
        "chunk": chunk,
        "score": float(selected_row["chunk_score"]),
        "top_score": float(top["score"]),
        "actor_count": int(selected_row["actor_count"]),
        "area_count": int(selected_row["area_count"]),
        "reason": reason or ("social_bond" if top.get("kind") == "actor" else "area"),
    }
    if top.get("kind") == "actor":
        last_row["actor_eid"] = int(top.get("actor_eid", top.get("key")))
    else:
        last_row["area_key"] = str(top.get("key", ""))
    return last_row


def _owned_property_warmth_rows(sim):
    player_eid = getattr(sim, "player_eid", None)
    if player_eid is None:
        return tuple()
    assets = sim.ecs.get(PlayerAssets).get(player_eid)
    if assets is None:
        return tuple()
    owned_ids = {
        str(raw).strip()
        for raw in tuple(getattr(assets, "owned_property_ids", ()) or ())
        if str(raw).strip()
    }
    if not owned_ids:
        return tuple()

    rows = []
    for prop_id in sorted(owned_ids):
        prop = getattr(sim, "properties", {}).get(prop_id)
        if property_supports_business_relevance(prop):
            reason = "player_business"
            score = PLAYER_BUSINESS_WARMTH_SCORE
        elif property_is_vehicle(prop):
            reason = "player_vehicle"
            score = PLAYER_VEHICLE_WARMTH_SCORE
        else:
            continue
        chunk = _property_chunk(sim, prop)
        if chunk is None:
            continue
        key = f"{reason}:{prop_id}"
        row = {
            "chunk": chunk,
            "score": score,
            "peak_score": score,
            "reason": reason,
            "reason_score": score,
            "source_kind": reason,
            "source_id": prop_id,
            "last_tick": _safe_int(getattr(sim, "tick", 0), 0),
            "spend_count": 0,
        }
        rows.append((key, chunk, score, row))
    return tuple(rows)


def _known_opportunity_attention_rows(sim):
    """Return actor/place anchors for active opportunities known to the player."""
    player_eid = getattr(sim, "player_eid", None)
    if player_eid is None:
        return tuple(), tuple()
    opportunities = getattr(sim, "world_traits", {}).get("opportunities", {})
    if not isinstance(opportunities, dict):
        return tuple(), tuple()
    intel_by_observer = opportunities.get("intel_by_observer", {})
    player_intel = intel_by_observer.get(str(player_eid), {}) if isinstance(intel_by_observer, dict) else {}
    if not isinstance(player_intel, dict):
        player_intel = {}

    positions = sim.ecs.get(Position)
    actor_anchors = {}
    area_anchors = {}
    for entry in tuple(opportunities.get("active", ()) or ()):
        if not isinstance(entry, dict):
            continue
        opportunity_id = _safe_int(entry.get("id"), 0)
        intel = player_intel.get(str(opportunity_id)) if opportunity_id > 0 else None
        awareness = str((intel or {}).get("awareness_state", "") or "").strip().lower() if isinstance(intel, dict) else ""
        requirements = entry.get("requirements", {}) if isinstance(entry.get("requirements"), dict) else {}
        known = awareness in {"heard", "confirmed"}
        known = known or _safe_int(entry.get("first_player_known_tick"), -1) >= 0
        known = known or bool(requirements.get("player_accepted"))
        if not known:
            continue
        issuer = entry.get("issuer", {}) if isinstance(entry.get("issuer"), dict) else {}
        giver_eid = _safe_int(requirements.get("giver_npc_eid"), 0)
        if giver_eid <= 0:
            giver_eid = _safe_int(issuer.get("npc_eid"), 0)
        if giver_eid > 0 and giver_eid != _safe_int(player_eid, -1):
            actor_anchors[giver_eid] = {
                "score": KNOWN_QUEST_GIVER_WARMTH_SCORE,
                "reason": "known_quest_giver",
                "opportunity_id": opportunity_id,
            }

        target_eids = set()
        for key in ("kill_target_eid", "bounty_target_eid", "interact_npc_eid", "pickup_interact_npc_eid"):
            target_eid = _safe_int(requirements.get(key), 0)
            if (
                target_eid > 0
                and target_eid != _safe_int(player_eid, -1)
                and positions.get(target_eid) is not None
            ):
                target_eids.add(target_eid)
        for target_eid in target_eids:
            existing = actor_anchors.get(target_eid)
            if not isinstance(existing, dict) or _safe_float(existing.get("score"), 0.0) < KNOWN_QUEST_TARGET_WARMTH_SCORE:
                actor_anchors[target_eid] = {
                    "score": KNOWN_QUEST_TARGET_WARMTH_SCORE,
                    "reason": "known_opportunity_target",
                    "opportunity_id": opportunity_id,
                }

        if target_eids:
            continue
        chunk = _normalize_chunk(requirements.get("visit_chunk")) or _normalize_chunk(entry.get("chunk"))
        if chunk is None:
            property_id = str(requirements.get("property_id", "") or "").strip()
            prop = getattr(sim, "properties", {}).get(property_id)
            chunk = _property_chunk(sim, prop)
        if chunk is None:
            continue
        key = f"known_opportunity:{opportunity_id}"
        area_anchors[key] = {
            "chunk": chunk,
            "score": KNOWN_QUEST_LOCATION_WARMTH_SCORE,
            "reason": "known_opportunity_location",
            "opportunity_id": opportunity_id,
        }

    actor_rows = []
    now = _safe_int(getattr(sim, "tick", 0), 0)
    for actor_eid in sorted(actor_anchors):
        pos = positions.get(actor_eid)
        if pos is None:
            continue
        anchor = actor_anchors[actor_eid]
        score = _safe_float(anchor.get("score"), 0.0)
        row = {
            "actor_eid": actor_eid,
            "other_eid": _safe_int(player_eid, 0),
            "score": score,
            "peak_score": score,
            "reason": str(anchor.get("reason", "known_opportunity_target")),
            "reason_score": score,
            "change_score": 0.0,
            "bond_strength": 0.0,
            "last_tick": now,
            "spend_count": 0,
            "no_spend": True,
            "opportunity_ids": (int(anchor.get("opportunity_id", 0)),),
        }
        actor_rows.append((actor_eid, pos, score, row))

    area_rows = []
    for key in sorted(area_anchors):
        anchor = area_anchors[key]
        chunk = _normalize_chunk(anchor.get("chunk"))
        if chunk is None:
            continue
        score = _safe_float(anchor.get("score"), 0.0)
        row = {
            "chunk": chunk,
            "score": score,
            "peak_score": score,
            "reason": "known_opportunity_location",
            "reason_score": score,
            "source_kind": "known_opportunity",
            "source_id": str(anchor.get("opportunity_id", "")),
            "last_tick": now,
            "spend_count": 0,
            "no_spend": True,
        }
        area_rows.append((key, chunk, score, row))
    return tuple(actor_rows), tuple(area_rows)


def _known_opportunity_chunks(sim):
    actor_rows, area_rows = _known_opportunity_attention_rows(sim)
    chunks = set()
    for _eid, pos, _score, _row in actor_rows:
        chunk = _chunk_for_pos(sim, pos)
        if chunk is not None:
            chunks.add(chunk)
    for _key, chunk, _score, _row in area_rows:
        chunk = _normalize_chunk(chunk)
        if chunk is not None:
            chunks.add(chunk)
    return set(chunks)


def social_warmth_protected_chunks(sim, unload_candidates, *, budget=SOCIAL_WARMTH_CHUNK_BUDGET):
    state = actor_attention_state(sim)
    candidates = {
        chunk
        for chunk in (_normalize_chunk(raw) for raw in tuple(unload_candidates or ()))
        if chunk is not None
    }
    state["social_warmth_protected_chunks"] = set()
    state["social_warmth_last_protected"] = ()
    if not candidates:
        return set()
    try:
        budget = int(budget)
    except (TypeError, ValueError):
        budget = SOCIAL_WARMTH_CHUNK_BUDGET
    if budget <= 0:
        return set()

    by_chunk = defaultdict(list)
    for eid, pos, score, row in _live_social_warmth_rows(sim, state):
        chunk = _chunk_for_pos(sim, pos)
        if chunk not in candidates:
            continue
        by_chunk[chunk].append(
            _warmth_item(
                "actor",
                eid,
                chunk,
                score,
                row,
                actor_eid=eid,
                no_spend=bool(row.get("no_spend")),
            )
        )

    selected = _rank_warmth_candidates(by_chunk)[:budget]
    protected = {item["chunk"] for item in selected}
    social_rows = _social_warmth_rows(state)
    last = []
    for selected_row in selected:
        last.append(_selected_warmth_last_row(selected_row))
        for item in selected_row["items"]:
            if not bool(item.get("no_spend")):
                _spend_social_warmth_row(social_rows, item["key"])
    state["social_warmth_protected_chunks"] = protected
    state["social_warmth_last_protected"] = tuple(last)
    _prune_social_warmth(sim, state, live_only=True)
    return set(protected)


def area_warmth_protected_chunks(sim, unload_candidates, *, budget=BUILDING_WARMTH_CHUNK_BUDGET):
    state = actor_attention_state(sim)
    candidates = {
        chunk
        for chunk in (_normalize_chunk(raw) for raw in tuple(unload_candidates or ()))
        if chunk is not None
    }
    state["area_warmth_protected_chunks"] = set()
    state["area_warmth_last_protected"] = ()
    if not candidates:
        return set()
    try:
        budget = int(budget)
    except (TypeError, ValueError):
        budget = BUILDING_WARMTH_CHUNK_BUDGET
    if budget <= 0:
        return set()

    by_chunk = defaultdict(list)
    for key, chunk, score, row in _live_area_warmth_rows(sim, state):
        if chunk not in candidates:
            continue
        by_chunk[chunk].append(
            _warmth_item("area", key, chunk, score, row, no_spend=bool(row.get("no_spend")))
        )
    for key, chunk, score, row in _owned_property_warmth_rows(sim):
        if chunk not in candidates:
            continue
        by_chunk[chunk].append(_warmth_item("area", key, chunk, score, row, no_spend=True))

    selected = _rank_warmth_candidates(by_chunk)[:budget]
    protected = {item["chunk"] for item in selected}
    area_rows = _area_warmth_rows(state)
    last = []
    for selected_row in selected:
        last.append(_selected_warmth_last_row(selected_row))
        for item in selected_row["items"]:
            if not bool(item.get("no_spend")):
                _spend_warmth_row(area_rows, item["key"])
    state["area_warmth_protected_chunks"] = protected
    state["area_warmth_last_protected"] = tuple(last)
    _prune_area_warmth(sim, state)
    return set(protected)


def warmth_protected_chunks(
    sim,
    unload_candidates,
    *,
    social_budget=SOCIAL_WARMTH_CHUNK_BUDGET,
    building_budget=BUILDING_WARMTH_CHUNK_BUDGET,
    area_budget=None,
    budget=None,
):
    if budget is not None:
        social_budget = budget
        building_budget = budget
    elif area_budget is not None:
        building_budget = area_budget
    candidates = {
        chunk
        for chunk in (_normalize_chunk(raw) for raw in tuple(unload_candidates or ()))
        if chunk is not None
    }
    opportunity_protected = _known_opportunity_chunks(sim) & candidates
    remaining = candidates - opportunity_protected
    social_protected = social_warmth_protected_chunks(sim, remaining, budget=social_budget)
    area_protected = area_warmth_protected_chunks(sim, remaining, budget=building_budget)
    state = actor_attention_state(sim)
    state["opportunity_protected_chunks"] = set(opportunity_protected)
    return set(opportunity_protected) | set(social_protected) | set(area_protected)


def warmth_debug_summary(sim, *, limit=1):
    state = actor_attention_state(sim)
    live_actor_rows = tuple(_live_social_warmth_rows(sim, state))
    live_area_rows = tuple(_live_area_warmth_rows(sim, state))
    owned_property_rows = tuple(_owned_property_warmth_rows(sim))
    social_protected = state.get("social_warmth_protected_chunks", set())
    if not isinstance(social_protected, set):
        social_protected = set(social_protected or ())
    area_protected = state.get("area_warmth_protected_chunks", set())
    if not isinstance(area_protected, set):
        area_protected = set(area_protected or ())
    opportunity_protected = state.get("opportunity_protected_chunks", set())
    if not isinstance(opportunity_protected, set):
        opportunity_protected = set(opportunity_protected or ())
    protected = set(social_protected) | set(area_protected) | set(opportunity_protected)
    combined = []
    for eid, pos, score, row in live_actor_rows:
        combined.append(
            _warmth_item(
                "actor",
                eid,
                _chunk_for_pos(sim, pos),
                score,
                row,
                actor_eid=eid,
                no_spend=bool(row.get("no_spend")),
            )
        )
    for key, chunk, score, row in live_area_rows:
        combined.append(
            _warmth_item("area", key, chunk, score, row, no_spend=bool(row.get("no_spend")))
        )
    for key, chunk, score, row in owned_property_rows:
        combined.append(_warmth_item("area", key, chunk, score, row, no_spend=True))
    owned_business_count = sum(1 for _key, _chunk, _score, row in owned_property_rows if row.get("reason") == "player_business")
    owned_vehicle_count = sum(1 for _key, _chunk, _score, row in owned_property_rows if row.get("reason") == "player_vehicle")
    combined = sorted(combined, key=lambda item: (-float(item["score"]), int(item["priority"]), str(item["key"])))
    top = []
    for item in combined[: max(0, int(limit))]:
        row = {
            "kind": item["kind"],
            "chunk": item["chunk"],
            "score": float(item["score"]),
            "reason": str(item.get("reason", "") or "").strip().lower(),
        }
        if item["kind"] == "actor":
            row["actor_eid"] = int(item["actor_eid"])
        else:
            row["area_key"] = str(item["key"])
        top.append(row)
    return {
        "actor_count": len(live_actor_rows),
        "area_count": len(live_area_rows) + len(owned_property_rows),
        "owned_business_count": owned_business_count,
        "owned_vehicle_count": owned_vehicle_count,
        "protected_count": len(protected),
        "social_protected_count": len(social_protected),
        "area_protected_count": len(area_protected),
        "opportunity_protected_count": len(opportunity_protected),
        "social_budget": SOCIAL_WARMTH_CHUNK_BUDGET,
        "building_budget": BUILDING_WARMTH_CHUNK_BUDGET,
        "top": tuple(top),
        "last_protected": tuple(state.get("social_warmth_last_protected", ()) or ())
        + tuple(state.get("area_warmth_last_protected", ()) or ()),
        "social_last_protected": tuple(state.get("social_warmth_last_protected", ()) or ()),
        "area_last_protected": tuple(state.get("area_warmth_last_protected", ()) or ()),
    }


def social_warmth_debug_summary(sim, *, limit=1):
    return warmth_debug_summary(sim, limit=limit)


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
                if property_supports_business_relevance(prop):
                    reason = "player_business"
                elif property_is_vehicle(prop):
                    reason = "player_vehicle"
                else:
                    reason = "player_property"
                _add_chunk_reason(chunk_reasons, chunk, reason)

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

    known_actor_rows, known_area_rows = _known_opportunity_attention_rows(sim)
    state["known_opportunity_actor_rows"] = {
        int(eid): dict(row)
        for eid, _pos, _score, row in known_actor_rows
    }
    state["known_opportunity_area_rows"] = {
        str(key): dict(row)
        for key, _chunk, _score, row in known_area_rows
    }
    for _eid, pos, _score, row in known_actor_rows:
        if str(row.get("reason", "") or "").strip().lower() != "known_opportunity_target":
            continue
        chunk = _chunk_for_pos(sim, pos)
        if chunk is not None:
            warm_chunks.add(chunk)
            _add_chunk_reason(chunk_reasons, chunk, "known_opportunity_target")
    for _key, chunk, _score, row in known_area_rows:
        warm_chunks.add(chunk)
        _add_chunk_reason(chunk_reasons, chunk, str(row.get("reason", "known_opportunity_location")))

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
        from game.pursuit_streaming_runtime import pursuit_streaming_state

        pursuit_state = pursuit_streaming_state(sim)
        pursuit_reasons = pursuit_state.get("protected_reasons", {})
        for chunk in tuple(pursuit_state.get("protected_chunks", set()) or ()):
            chunk = _normalize_chunk(chunk)
            if chunk is None:
                continue
            warm_chunks.add(chunk)
            reasons = pursuit_reasons.get(chunk, ()) if isinstance(pursuit_reasons, dict) else ()
            if reasons:
                for reason in tuple(reasons):
                    _add_chunk_reason(chunk_reasons, chunk, f"pursuit:{reason}")
            else:
                _add_chunk_reason(chunk_reasons, chunk, "pursuit")
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

    social_warmth_reason = _social_warmth_reason_for_actor(sim, state, eid)
    if social_warmth_reason:
        return {"scope": "warm", "reasons": (social_warmth_reason,)}

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
    stats["social_warmth_actors"] = len(social_warm_actor_eids(sim))
    owned_property_rows = tuple(_owned_property_warmth_rows(sim))
    stats["area_warmth_areas"] = len(_live_area_warmth_rows(sim, state)) + len(owned_property_rows)
    stats["owned_business_warmth_areas"] = sum(1 for _key, _chunk, _score, row in owned_property_rows if row.get("reason") == "player_business")
    stats["owned_vehicle_warmth_areas"] = sum(1 for _key, _chunk, _score, row in owned_property_rows if row.get("reason") == "player_vehicle")
    protected = state.get("social_warmth_protected_chunks", set())
    stats["social_warmth_protected_chunks"] = len(protected if isinstance(protected, set) else set(protected or ()))
    protected = state.get("area_warmth_protected_chunks", set())
    stats["area_warmth_protected_chunks"] = len(protected if isinstance(protected, set) else set(protected or ()))
    protected = state.get("opportunity_protected_chunks", set())
    stats["opportunity_protected_chunks"] = len(protected if isinstance(protected, set) else set(protected or ()))
    try:
        from game.pursuit_streaming_runtime import pursuit_streaming_state

        protected = pursuit_streaming_state(sim).get("protected_chunks", set())
        stats["pursuit_protected_chunks"] = len(protected if isinstance(protected, set) else set(protected or ()))
    except Exception:
        stats["pursuit_protected_chunks"] = 0
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
