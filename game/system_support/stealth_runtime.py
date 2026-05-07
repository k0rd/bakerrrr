"""Shared player stealth visibility helpers."""

from game.components import PlayerModeState
from game.system_support.awareness_runtime import _watchers_for_position


def _player_hidden_status(sim, eid, x, y, z):
    modes = sim.ecs.get(PlayerModeState).get(eid)
    if not modes or not modes.sneak:
        return False, []
    if str(getattr(sim, "zoom_mode", "city")).lower() == "overworld":
        return False, []

    watchers = _watchers_for_position(sim, x, y, z, exclude_eid=eid)
    return len(watchers) == 0, watchers
