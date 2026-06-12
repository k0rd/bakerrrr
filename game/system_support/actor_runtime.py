"""Shared actor state and coarse-detail scheduling helpers."""

from game.components import AI, Collider, CreatureIdentity, NPCWill, Render, Vitality


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


def _recover_downed_actor_state(sim, eid, *, tick=None, min_hp=1):
    if sim is None or eid is None:
        return False
    vitality = sim.ecs.get(Vitality).get(eid)
    if vitality is None:
        return False

    try:
        max_hp = max(1, int(getattr(vitality, "max_hp", 1) or 1))
    except (TypeError, ValueError):
        max_hp = 1
    try:
        hp = int(getattr(vitality, "hp", 0) or 0)
    except (TypeError, ValueError):
        hp = 0
    try:
        min_hp = max(1, int(min_hp))
    except (TypeError, ValueError):
        min_hp = 1
    vitality.hp = max(1, min(max_hp, max(hp, min_hp)))
    vitality.downed = False
    vitality.downed_tick = None
    setattr(vitality, "death_reason", "")
    setattr(vitality, "death_reported_tick", None)

    collider = sim.ecs.get(Collider).get(eid)
    if collider:
        collider.blocks = True

    ai = sim.ecs.get(AI).get(eid)
    if ai and str(getattr(ai, "state", "") or "").strip().lower() == "downed":
        ai.state = "idle"
        ai.target = None
        ai.target_eid = None

    will = sim.ecs.get(NPCWill).get(eid)
    if will and str(getattr(will, "intent", "") or "").strip().lower() == "downed":
        will.intent = "idle"
        will.score = 0.0
        will.target = None
        will.target_eid = None
        will.last_tick = int(getattr(sim, "tick", 0) if tick is None else tick)

    render = sim.ecs.get(Render).get(eid)
    if render and str(getattr(render, "glyph", "") or "")[:1] == "x":
        try:
            from game.appearance import entity_default_snapshot

            identity = sim.ecs.get(CreatureIdentity).get(eid)
            player_eid = getattr(sim, "player_eid", None)
            player_controlled = player_eid is not None and int(player_eid) == int(eid)
            defaults = entity_default_snapshot(
                identity,
                role=str(getattr(ai, "role", "") or "").strip().lower(),
                player=player_controlled,
                seed=getattr(sim, "seed", None),
                eid=eid,
                sim=sim,
            )
            render.set_appearance(
                glyph=defaults.glyph,
                color=defaults.color,
                semantic_id=defaults.semantic_id,
                layer=defaults.layer,
                priority=defaults.priority,
            )
        except Exception:  # noqa: BLE001 - recovery should not fail because cosmetics did
            render.glyph = "@"

    return True


def _detail_tick_allowed(sim, pos, eid, coarse_divisor=3):
    detail = sim.detail_for_xy(pos.x, pos.y)
    if detail == "unloaded":
        return False
    if detail == "coarse" and ((sim.tick + eid) % coarse_divisor != 0):
        return False
    return True
