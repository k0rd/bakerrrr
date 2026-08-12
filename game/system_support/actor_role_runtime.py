"""Separate actors' simulation roles from their player-facing roles."""


def actor_presentation_role(sim, eid, *, ai=None, occupation=None):
    """Return the role the world can honestly present for an actor.

    Bodyguards retain the guard AI role because tactical systems use it, but
    that implementation detail must not label them as justice personnel.
    """

    if sim is not None and getattr(sim, "ecs", None) is not None:
        if ai is None:
            from game.components import AI

            ai = sim.ecs.get(AI).get(eid)
        if occupation is None:
            from game.components import Occupation

            occupation = sim.ecs.get(Occupation).get(eid)

    career = str(getattr(occupation, "career", "") or "").strip().lower().replace(" ", "_")
    if career == "bodyguard":
        return "bodyguard"

    contractors = getattr(sim, "contractors", {}) if sim is not None else {}
    record = contractors.get(eid) if isinstance(contractors, dict) else None
    if record is None and isinstance(contractors, dict):
        record = contractors.get(str(eid))
    if isinstance(record, dict) and str(record.get("job", "") or "").strip().lower() == "bodyguard":
        return "bodyguard"

    return str(getattr(ai, "role", "") or "").strip().lower()


__all__ = ["actor_presentation_role"]
