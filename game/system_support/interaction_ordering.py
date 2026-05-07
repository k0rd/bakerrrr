"""Shared grid-direction and interaction-target ordering helpers."""


def _manhattan(ax, ay, bx, by):
    return abs(int(ax) - int(bx)) + abs(int(ay) - int(by))


def _direction_step(from_x, from_y, to_x, to_y):
    dx = to_x - from_x
    dy = to_y - from_y

    if abs(dx) >= abs(dy):
        if dx > 0:
            return (1, 0)
        if dx < 0:
            return (-1, 0)

    if dy > 0:
        return (0, 1)
    if dy < 0:
        return (0, -1)

    return (0, 0)


def _normalized_direction(dx, dy):
    try:
        dx = int(dx)
    except (TypeError, ValueError):
        dx = 0
    try:
        dy = int(dy)
    except (TypeError, ValueError):
        dy = 0
    if dx > 0:
        dx = 1
    elif dx < 0:
        dx = -1
    if dy > 0:
        dy = 1
    elif dy < 0:
        dy = -1
    return (dx, dy)


def _interaction_target_order_key(origin_x, origin_y, target_x, target_y, *, preferred_dir=None, stable_tiebreaker=()):
    origin_x = int(origin_x)
    origin_y = int(origin_y)
    target_x = int(target_x)
    target_y = int(target_y)
    dist = _manhattan(origin_x, origin_y, target_x, target_y)
    if not isinstance(stable_tiebreaker, tuple):
        stable_tiebreaker = (stable_tiebreaker,)
    if dist <= 0:
        return (0, 0, 0, 0) + stable_tiebreaker

    preferred = None
    if preferred_dir is not None:
        try:
            preferred = _normalized_direction(preferred_dir[0], preferred_dir[1])
        except (TypeError, ValueError, IndexError):
            preferred = None
        if preferred == (0, 0):
            preferred = None

    if preferred is not None:
        step = _normalized_direction(target_x - origin_x, target_y - origin_y)
        alignment = (step[0] * preferred[0]) + (step[1] * preferred[1])
        mismatch = abs(step[0] - preferred[0]) + abs(step[1] - preferred[1])
        return (1, -alignment, mismatch, dist) + stable_tiebreaker

    return (1, 0, 0, dist) + stable_tiebreaker
