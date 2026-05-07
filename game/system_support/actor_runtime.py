"""Shared actor state and coarse-detail scheduling helpers."""

from game.components import AI, NPCWill, Vitality


def _entity_is_downed(sim, eid):
    if sim is None or eid is None:
        return False
    vitality = sim.ecs.get(Vitality).get(eid)
    return bool(vitality and bool(getattr(vitality, "downed", False)))


def _apply_downed_actor_state(sim, eid, *, tick=None):
    if not _entity_is_downed(sim, eid):
        return False
    ai = sim.ecs.get(AI).get(eid)
    if ai:
        ai.state = "downed"
        ai.target = None
        ai.target_eid = None
    will = sim.ecs.get(NPCWill).get(eid)
    if will:
        will.intent = "downed"
        will.score = max(float(getattr(will, "score", 0.0) or 0.0), 100.0)
        will.target = None
        will.target_eid = None
        will.last_tick = int(getattr(sim, "tick", 0) if tick is None else tick)
    return True


def _detail_tick_allowed(sim, pos, eid, coarse_divisor=3):
    detail = sim.detail_for_xy(pos.x, pos.y)
    if detail == "unloaded":
        return False
    if detail == "coarse" and ((sim.tick + eid) % coarse_divisor != 0):
        return False
    return True
