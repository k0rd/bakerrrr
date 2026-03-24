"""Shared visibility helpers for player FOV and observer checks."""

from __future__ import annotations


def _to_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _grid_distance(ax, ay, bx, by):
    return max(abs(int(ax) - int(bx)), abs(int(ay) - int(by)))


def _line_points(ax, ay, bx, by):
    x0 = int(ax)
    y0 = int(ay)
    x1 = int(bx)
    y1 = int(by)

    points = []
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    while True:
        points.append((x0, y0))
        if x0 == x1 and y0 == y1:
            break
        e2 = err * 2
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy

    return points


def _is_loaded(sim, x, y):
    detail = str(sim.detail_for_xy(int(x), int(y))).strip().lower()
    return detail != "unloaded"


def has_line_of_sight(sim, ax, ay, az, bx, by, bz):
    ax = _to_int(ax)
    ay = _to_int(ay)
    az = _to_int(az)
    bx = _to_int(bx)
    by = _to_int(by)
    bz = _to_int(bz)

    if az != bz:
        return False
    if (ax, ay) == (bx, by):
        return True
    if not _is_loaded(sim, ax, ay) or not _is_loaded(sim, bx, by):
        return False

    for px, py in _line_points(ax, ay, bx, by)[1:-1]:
        if not _is_loaded(sim, px, py):
            return False
        tile = sim.tilemap.tile_at(px, py, az)
        if tile and not bool(tile.transparent):
            return False
    return True


def fov_positions(sim, x, y, z, radius):
    x = _to_int(x)
    y = _to_int(y)
    z = _to_int(z)
    radius = max(1, _to_int(radius, default=8))

    visible = set()
    visible.add((x, y, z))

    for ny in range(y - radius, y + radius + 1):
        for nx in range(x - radius, x + radius + 1):
            if not sim.tilemap.in_bounds(nx, ny):
                continue
            if _grid_distance(x, y, nx, ny) > radius:
                continue
            if not _is_loaded(sim, nx, ny):
                continue
            if has_line_of_sight(sim, x, y, z, nx, ny, z):
                visible.add((nx, ny, z))

    return visible


def visibility_state(sim):
    state = getattr(sim, "visibility_state", None)
    if isinstance(state, dict):
        return state

    state = {
        "tick": -1,
        "observers": {},
        "player_eid": None,
        "player_origin": None,
        "player_radius": 0,
        "player_visible": set(),
        "player_explored": set(),
    }
    sim.visibility_state = state
    return state


def _begin_tick(sim, state):
    tick = _to_int(getattr(sim, "tick", 0))
    if _to_int(state.get("tick", -1), default=-1) == tick:
        return

    state["tick"] = tick
    state["observers"] = {}


def observer_visible_positions(sim, observer_eid, x, y, z, radius):
    state = visibility_state(sim)
    _begin_tick(sim, state)

    observer_key = _to_int(observer_eid, default=-1)
    ox = _to_int(x)
    oy = _to_int(y)
    oz = _to_int(z)
    radius = max(1, _to_int(radius, default=8))

    cached = state["observers"].get(observer_key)
    if isinstance(cached, dict):
        if (
            _to_int(cached.get("x"), default=10**9) == ox
            and _to_int(cached.get("y"), default=10**9) == oy
            and _to_int(cached.get("z"), default=10**9) == oz
            and _to_int(cached.get("radius"), default=-1) == radius
        ):
            visible = cached.get("visible")
            if isinstance(visible, set):
                return visible

    visible = fov_positions(sim, ox, oy, oz, radius)
    state["observers"][observer_key] = {
        "x": ox,
        "y": oy,
        "z": oz,
        "radius": radius,
        "visible": visible,
    }
    return visible


def observer_can_see_position(sim, observer_eid, observer_x, observer_y, observer_z, target_x, target_y, target_z, radius):
    target_x = _to_int(target_x)
    target_y = _to_int(target_y)
    target_z = _to_int(target_z)
    observer_z = _to_int(observer_z)
    if observer_z != target_z:
        return False

    visible = observer_visible_positions(
        sim,
        observer_eid=observer_eid,
        x=observer_x,
        y=observer_y,
        z=observer_z,
        radius=radius,
    )
    return (target_x, target_y, target_z) in visible


def update_player_visibility(sim, player_eid, x, y, z, radius):
    state = visibility_state(sim)
    _begin_tick(sim, state)

    visible = observer_visible_positions(
        sim,
        observer_eid=player_eid,
        x=x,
        y=y,
        z=z,
        radius=radius,
    )

    explored = state.get("player_explored")
    if not isinstance(explored, set):
        explored = set()
    explored.update(visible)

    state["player_eid"] = player_eid
    state["player_origin"] = (_to_int(x), _to_int(y), _to_int(z))
    state["player_radius"] = max(1, _to_int(radius, default=8))
    state["player_visible"] = set(visible)
    state["player_explored"] = explored
    return visible
