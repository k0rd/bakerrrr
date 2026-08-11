"""Shared combat overlay and turn-pacing state helpers."""


def _combat_overlay_state(sim):
    overlay = getattr(sim, "combat_overlay", None)
    if not isinstance(overlay, dict):
        overlay = {}
        sim.combat_overlay = overlay
    overlay.setdefault("active", False)
    overlay.setdefault("manual_pacing", False)
    overlay.setdefault("threat_count", 0)
    overlay.setdefault("direct_threat_count", 0)
    overlay.setdefault("ambient_threat_count", 0)
    overlay.setdefault("pursuit_target_count", 0)
    overlay.setdefault("recent_hit_target", None)
    overlay.setdefault("recent_player_drone_attacker", None)
    overlay.setdefault("nearest_threat_dist", None)
    overlay.setdefault("player_exposure", 1.0)
    return overlay


def _set_manual_combat_pacing(sim, active):
    overlay = _combat_overlay_state(sim)
    overlay["manual_pacing"] = bool(active)
    if active:
        sim.turn_based = True
    elif not bool(overlay.get("active")):
        sim.turn_based = False
    return overlay


def _combat_turn_pacing_active(sim):
    overlay = _combat_overlay_state(sim)
    return bool(getattr(sim, "turn_based", False) or overlay.get("active") or overlay.get("manual_pacing"))
