"""Shared cover validation and threat-position helpers."""

from game.components import AI, Position
from game.system_support.interaction_ordering import _direction_step, _manhattan

THREAT_STATES = {"protecting", "investigating"}


def _is_cover_state_valid(sim, pos, cover_state):
    if not cover_state.active:
        return False
    if not cover_state.source:
        return False

    sx, sy, sz = cover_state.source
    if sz != pos.z:
        return False
    if _manhattan(pos.x, pos.y, sx, sy) > 1:
        return False

    if cover_state.source_kind == "wall":
        tile = sim.tilemap.tile_at(sx, sy, sz)
        return bool(tile and not tile.walkable)

    if cover_state.source_kind == "property":
        prop = sim.property_at(sx, sy, sz)
        return bool(prop)

    return False


def _cover_threat_positions_by_floor(sim):
    """Snapshot cover-relevant actor positions once for a CoverSystem update."""

    positions = sim.ecs.get(Position)
    ais = sim.ecs.get(AI)
    by_floor = {}
    for other_eid, ai in ais.items():
        if ai.state not in THREAT_STATES:
            continue
        threat_pos = positions.get(other_eid)
        if not threat_pos:
            continue
        by_floor.setdefault(int(threat_pos.z), []).append(
            (other_eid, int(threat_pos.x), int(threat_pos.y))
        )
    return {floor: tuple(rows) for floor, rows in by_floor.items()}


def _threat_positions_for_entity(sim, eid, pos, radius=10, *, prepared_by_floor=None):
    if prepared_by_floor is None:
        positions = sim.ecs.get(Position)
        ais = sim.ecs.get(AI)
        candidates = (
            (other_eid, threat_pos.x, threat_pos.y)
            for other_eid, ai in ais.items()
            if ai.state in THREAT_STATES
            for threat_pos in (positions.get(other_eid),)
            if threat_pos is not None and threat_pos.z == pos.z
        )
    else:
        candidates = prepared_by_floor.get(int(pos.z), ())

    threats = []
    for other_eid, threat_x, threat_y in candidates:
        if other_eid == eid:
            continue
        dist = _manhattan(pos.x, pos.y, threat_x, threat_y)
        if dist > radius:
            continue

        threats.append((other_eid, dist, threat_x, threat_y))

    return threats


def _effective_cover_value(cover_state, entity_x, entity_y, threat_x, threat_y):
    if not cover_state.active:
        return 0.0

    base = float(max(0.0, min(0.95, cover_state.cover_value)))
    block_dir = cover_state.block_dir
    if not block_dir:
        return base * 0.55

    threat_dir = _direction_step(entity_x, entity_y, threat_x, threat_y)
    if threat_dir == block_dir:
        return base
    if threat_dir == (-block_dir[0], -block_dir[1]):
        return base * 0.2
    return base * 0.35
