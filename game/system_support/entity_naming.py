"""Shared entity display-label helpers."""

from game.components import AI, CreatureIdentity


def _entity_display_name_from_record(record):
    if not isinstance(record, dict):
        return ""
    for key in (
        "display_name",
        "personal_name",
        "common_name",
        "species",
        "role",
        "creature_type",
        "taxonomy_class",
    ):
        label = str(record.get(key, "") or "").replace("_", " ").strip()
        if label:
            return label
    return ""


def _entity_display_name(sim, eid, title_case=False):
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    ai = sim.ecs.get(AI).get(eid)

    if identity:
        label = str(identity.display_name()).replace("_", " ").strip()
    elif ai:
        label = str(ai.role or "entity").replace("_", " ").strip()
    elif hasattr(sim, "entity_identity_record"):
        label = _entity_display_name_from_record(sim.entity_identity_record(eid))
    else:
        label = "entity"

    if not label:
        label = "entity"
    return label.title() if title_case else label
