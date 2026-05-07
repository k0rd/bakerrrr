"""Shared witness and observer notice helpers."""

from game.components import Position


def _observer_support():
    from game import systems as _systems

    return _systems


def _watchers_for_position(sim, x, y, z, exclude_eid=None, offender_eid=None):
    positions = sim.ecs.get(Position)
    support = _observer_support()

    watchers = []
    for observer_eid, observer_pos in positions.items():
        if observer_eid == exclude_eid:
            continue
        if offender_eid is not None and support._observer_is_active_contractor_ally(sim, observer_eid, offender_eid):
            continue
        if int(observer_pos.z) != int(z):
            continue
        if support._observer_can_notice_position(sim, observer_eid, x, y, z):
            watchers.append(observer_eid)
    return watchers

