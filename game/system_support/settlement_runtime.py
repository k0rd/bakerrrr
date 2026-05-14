"""Shared settlement and chunk-population helpers."""

from game.property_runtime import property_covering as _property_covering


def _home_property(sim, routine=None):
    home = getattr(routine, "home", None)
    if isinstance(home, (list, tuple)) and len(home) >= 3:
        prop = _property_covering(sim, int(home[0]), int(home[1]), int(home[2]))
        if prop:
            return prop
    return None


def _property_chunk_key(sim, prop):
    if not isinstance(prop, dict):
        return None
    try:
        return sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
    except (TypeError, ValueError):
        return None


def _track_entity_in_chunk_population(sim, eid, *, chunk=None):
    if eid is None:
        return None
    if not hasattr(sim, "chunk_population_records") or not isinstance(getattr(sim, "chunk_population_records", None), dict):
        sim.chunk_population_records = {}
    if not hasattr(sim, "chunk_population_baselines") or not isinstance(getattr(sim, "chunk_population_baselines", None), dict):
        sim.chunk_population_baselines = {}
    tracker = getattr(sim, "track_population_entity", None)
    if callable(tracker):
        return tracker(eid, chunk=chunk)
    return None
