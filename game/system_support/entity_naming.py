"""Shared entity display-label helpers."""

from game.components import AI, CreatureIdentity


def _entity_display_name(sim, eid, title_case=False):
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    ai = sim.ecs.get(AI).get(eid)

    if identity:
        label = str(identity.display_name()).replace("_", " ").strip()
    elif ai:
        label = str(ai.role or "entity").replace("_", " ").strip()
    else:
        label = "entity"

    if not label:
        label = "entity"
    return label.title() if title_case else label
