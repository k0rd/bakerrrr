from __future__ import annotations

import random

from game.components import Position
from game.run_objectives import evaluate_run_objective


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _chunk_tuple(value):
    if not isinstance(value, (list, tuple)) or len(value) != 2:
        return None
    try:
        return (int(value[0]), int(value[1]))
    except (TypeError, ValueError):
        return None


def _manhattan(a, b):
    if not a or not b:
        return 0
    return abs(int(a[0]) - int(b[0])) + abs(int(a[1]) - int(b[1]))


def _risk_score(label):
    label = str(label or "").strip().lower()
    return {"low": 1, "exposed": 2, "hazardous": 3}.get(label, 1)


def _state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits

    state = traits.get("final_operation")
    if not isinstance(state, dict):
        state = {}
        traits["final_operation"] = state

    state["unlocked"] = bool(state.get("unlocked", False))
    state["completed"] = bool(state.get("completed", False))
    state["failed"] = bool(state.get("failed", False))
    state["unlock_tick"] = _safe_int(state.get("unlock_tick"), default=-1)
    state["complete_tick"] = _safe_int(state.get("complete_tick"), default=-1)
    state["fail_tick"] = _safe_int(state.get("fail_tick"), default=-1)
    state["fail_reason"] = str(state.get("fail_reason", "")).strip().lower()
    state["objective_id"] = str(state.get("objective_id", "")).strip().lower()
    state["objective_title"] = str(state.get("objective_title", "")).strip()
    target_chunk = _chunk_tuple(state.get("target_chunk"))
    state["target_chunk"] = target_chunk
    state["target_label"] = str(state.get("target_label", "")).strip()
    summary = state.get("summary")
    if not isinstance(summary, dict):
        summary = {}
    state["summary"] = summary
    return state


def _current_chunk(sim, player_eid):
    pos = sim.ecs.get(Position).get(player_eid) if sim is not None else None
    if pos:
        cx, cy = sim.chunk_coords(pos.x, pos.y)
        return (int(cx), int(cy))
    active = getattr(sim, "active_chunk_coord", None)
    return _chunk_tuple(active) or (0, 0)


def _target_label(sim, chunk):
    cx, cy = chunk
    desc = sim.world.overworld_descriptor(cx, cy)
    interest = sim.world.overworld_interest(cx, cy, descriptor=desc)
    detail = str(interest.get("detail", "")).strip()
    if detail:
        return detail
    settlement = str(desc.get("settlement_name", "")).strip()
    if settlement:
        return settlement
    district = str(desc.get("district_type", "")).strip().replace("_", " ")
    area = str(desc.get("area_type", "")).strip().replace("_", " ")
    if district:
        return f"{area}/{district}" if area else district
    return area or f"chunk {cx},{cy}"


def _pick_target_chunk(sim, player_eid, rng):
    origin = _current_chunk(sim, player_eid)
    traits = getattr(sim, "world_traits", {}) if sim is not None else {}
    opportunities = traits.get("opportunities", {}) if isinstance(traits, dict) else {}
    active = opportunities.get("active", ()) if isinstance(opportunities, dict) else ()

    scored = []
    seen = set()
    for entry in active if isinstance(active, list) else ():
        if not isinstance(entry, dict):
            continue
        chunk = _chunk_tuple(entry.get("chunk"))
        if not chunk:
            continue
        if chunk in seen:
            continue
        seen.add(chunk)
        dist = _manhattan(origin, chunk)
        if dist < 3:
            continue
        risk = _risk_score(entry.get("risk", "low"))
        source = str(entry.get("source", "unknown")).strip().lower()
        source_bonus = 2 if source in {"overworld_tag", "intel"} else 1
        score = (dist * 4) + (risk * 3) + source_bonus
        scored.append((score, dist, risk, chunk))

    if scored:
        scored.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
        top = scored[:3]
        return rng.choice(top)[3]

    fallback = []
    for radius in range(4, 10):
        for dy in range(-radius, radius + 1):
            dx = radius - abs(dy)
            for sign in (-1, 1):
                cx = origin[0] + (dx * sign)
                cy = origin[1] + dy
                chunk = (cx, cy)
                if chunk in seen:
                    continue
                desc = sim.world.overworld_descriptor(cx, cy)
                interest = sim.world.overworld_interest(cx, cy, descriptor=desc)
                prominence = _safe_int(interest.get("prominence"), default=0)
                area = str(desc.get("area_type", "city")).strip().lower() or "city"
                area_bonus = 2 if area != "city" else 1
                score = (radius * 3) + (prominence * 2) + area_bonus
                fallback.append((score, radius, chunk))
    if fallback:
        fallback.sort(key=lambda row: (row[0], row[1]), reverse=True)
        return rng.choice(fallback[:6])[2]
    return origin


def ensure_final_operation_unlocked(sim, player_eid, objective_eval=None):
    state = _state(sim)
    if state["unlocked"] or state["completed"] or state["failed"]:
        return None

    if not isinstance(objective_eval, dict):
        objective_eval = evaluate_run_objective(sim, player_eid)
    if not objective_eval or not bool(objective_eval.get("completed")):
        return None

    objective_id = str(objective_eval.get("id", "")).strip().lower()
    objective_title = str(objective_eval.get("title", "Run Objective")).strip() or "Run Objective"
    seed = f"{getattr(sim, 'seed', 'seed')}:final_op:{objective_id}:{getattr(sim, 'tick', 0)}"
    rng = random.Random(seed)
    target_chunk = _pick_target_chunk(sim, player_eid, rng=rng)
    target_label = _target_label(sim, target_chunk)

    state["unlocked"] = True
    state["unlock_tick"] = _safe_int(getattr(sim, "tick", 0), default=0)
    state["objective_id"] = objective_id
    state["objective_title"] = objective_title
    state["target_chunk"] = target_chunk
    state["target_label"] = target_label
    return {
        "objective_id": objective_id,
        "objective_title": objective_title,
        "target_chunk": target_chunk,
        "target_label": target_label,
    }


def evaluate_final_operation(sim, player_eid):
    state = _state(sim)
    if not state["unlocked"]:
        return None

    target = _chunk_tuple(state.get("target_chunk"))
    current = _current_chunk(sim, player_eid)
    if not target:
        target = current
    distance = _manhattan(current, target)
    unlocked = bool(state["unlocked"])
    completed = bool(state["completed"])

    if completed:
        summary_line = "Final operation complete."
        next_step = "Run completed. Review summary."
    elif state["failed"]:
        summary_line = "Final operation failed."
        next_step = "Run failed."
    else:
        summary_line = (
            f"Final operation: reach chunk ({target[0]},{target[1]}) "
            f"[{state.get('target_label', 'target')}] ({distance}c)."
        )
        next_step = "Travel to target chunk and enter local area."

    return {
        "unlocked": unlocked,
        "completed": completed,
        "target_chunk": target,
        "target_label": state.get("target_label", ""),
        "distance": distance,
        "summary_line": summary_line,
        "next_step": next_step,
    }


def _summary_lines(sim, player_eid, state):
    traits = getattr(sim, "world_traits", {}) if sim is not None else {}
    opportunities = traits.get("opportunities", {}) if isinstance(traits, dict) else {}
    run_pressure = traits.get("run_pressure", {}) if isinstance(traits, dict) else {}
    objective_progress = traits.get("objective_progress", {}) if isinstance(traits, dict) else {}
    visited_map = getattr(sim, "overworld_visit_state_by_eid", {})
    visited = visited_map.get(player_eid, set()) if isinstance(visited_map, dict) else set()
    if not isinstance(visited, (set, list, tuple)):
        visited = set()

    completed_opps = opportunities.get("completed", ()) if isinstance(opportunities, dict) else ()
    pressure_peak = _safe_int(run_pressure.get("peak_attention"), default=0) if isinstance(run_pressure, dict) else 0
    reserve_bonus = _safe_int(objective_progress.get("reserve_bonus_credits"), default=0) if isinstance(objective_progress, dict) else 0
    intel_bonus = _safe_int(objective_progress.get("intel_marks"), default=0) if isinstance(objective_progress, dict) else 0
    network_bonus = _safe_int(objective_progress.get("network_marks"), default=0) if isinstance(objective_progress, dict) else 0

    return [
        f"Final operation complete: {state.get('objective_title', 'Run Objective')}.",
        f"Run ticks: {_safe_int(getattr(sim, 'tick', 0), default=0)}.",
        f"Travel footprint: {len(visited)} chunks visited.",
        f"Opportunities completed: {len(completed_opps) if isinstance(completed_opps, list) else 0}.",
        f"Peak attention: {pressure_peak}.",
        f"Objective bonus track: reserve {reserve_bonus}, network {network_bonus}, intel {intel_bonus}.",
    ]


def _failure_summary_lines(sim, player_eid, state):
    traits = getattr(sim, "world_traits", {}) if sim is not None else {}
    opportunities = traits.get("opportunities", {}) if isinstance(traits, dict) else {}
    run_pressure = traits.get("run_pressure", {}) if isinstance(traits, dict) else {}
    visited_map = getattr(sim, "overworld_visit_state_by_eid", {})
    visited = visited_map.get(player_eid, set()) if isinstance(visited_map, dict) else set()
    if not isinstance(visited, (set, list, tuple)):
        visited = set()

    completed_opps = opportunities.get("completed", ()) if isinstance(opportunities, dict) else ()
    pressure_peak = _safe_int(run_pressure.get("peak_attention"), default=0) if isinstance(run_pressure, dict) else 0
    fail_reason = str(state.get("fail_reason", "")).strip().replace("_", " ")
    reason_suffix = f" ({fail_reason})" if fail_reason else ""

    return [
        f"Final operation failed: {state.get('objective_title', 'Run Objective')}{reason_suffix}.",
        f"Run ticks: {_safe_int(getattr(sim, 'tick', 0), default=0)}.",
        f"Travel footprint: {len(visited)} chunks visited.",
        f"Opportunities completed: {len(completed_opps) if isinstance(completed_opps, list) else 0}.",
        f"Peak attention: {pressure_peak}.",
    ]


def try_complete_final_operation(sim, player_eid):
    state = _state(sim)
    if not state["unlocked"] or state["completed"] or state["failed"]:
        return None

    target = _chunk_tuple(state.get("target_chunk"))
    current = _current_chunk(sim, player_eid)
    if not target or not current or target != current:
        return None
    if str(getattr(sim, "zoom_mode", "city")).strip().lower() == "overworld":
        return None

    state["completed"] = True
    state["complete_tick"] = _safe_int(getattr(sim, "tick", 0), default=0)
    lines = _summary_lines(sim, player_eid, state)
    state["summary"] = {
        "lines": list(lines),
        "tick": int(state["complete_tick"]),
    }
    return {
        "objective_id": state.get("objective_id", ""),
        "objective_title": state.get("objective_title", ""),
        "target_chunk": target,
        "target_label": state.get("target_label", ""),
        "complete_tick": int(state["complete_tick"]),
        "summary_lines": lines,
    }


def try_fail_final_operation(sim, player_eid, reason=""):
    state = _state(sim)
    if not state["unlocked"] or state["completed"] or state["failed"]:
        return None

    state["failed"] = True
    state["fail_tick"] = _safe_int(getattr(sim, "tick", 0), default=0)
    state["fail_reason"] = str(reason or "").strip().lower()
    lines = _failure_summary_lines(sim, player_eid, state)
    state["summary"] = {
        "lines": list(lines),
        "tick": int(state["fail_tick"]),
        "failed": True,
    }
    return {
        "objective_id": state.get("objective_id", ""),
        "objective_title": state.get("objective_title", ""),
        "target_chunk": _chunk_tuple(state.get("target_chunk")) or (0, 0),
        "target_label": state.get("target_label", ""),
        "fail_tick": int(state["fail_tick"]),
        "fail_reason": state.get("fail_reason", ""),
        "summary_lines": lines,
    }
