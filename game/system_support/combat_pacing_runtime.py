"""Shared combat overlay and turn-pacing state helpers."""


def _combat_overlay_state(sim):
    overlay = getattr(sim, "combat_overlay", None)
    if not isinstance(overlay, dict):
        overlay = {}
        sim.combat_overlay = overlay
    overlay.setdefault("active", False)
    overlay.setdefault("manual_pacing", False)
    sources = overlay.get("manual_pacing_sources")
    if not isinstance(sources, dict):
        # Older saves only carry the effective flag. Treat it as the temporary
        # aim source so closing that aim state keeps its historical behavior.
        sources = {
            "aim": bool(overlay.get("manual_pacing")),
            "player_toggle": False,
        }
        overlay["manual_pacing_sources"] = sources
    sources.setdefault("aim", False)
    sources.setdefault("player_toggle", False)
    overlay.setdefault("threat_count", 0)
    overlay.setdefault("direct_threat_count", 0)
    overlay.setdefault("ambient_threat_count", 0)
    overlay.setdefault("pursuit_target_count", 0)
    overlay.setdefault("recent_hit_target", None)
    overlay.setdefault("recent_player_drone_attacker", None)
    overlay.setdefault("nearest_threat_dist", None)
    overlay.setdefault("player_exposure", 1.0)
    return overlay


def _set_manual_combat_pacing(sim, active, *, source="aim"):
    overlay = _combat_overlay_state(sim)
    source = str(source or "aim").strip().lower() or "aim"
    sources = overlay["manual_pacing_sources"]
    sources[source] = bool(active)
    overlay["manual_pacing"] = any(bool(value) for value in sources.values())
    if overlay["manual_pacing"] or bool(overlay.get("active")):
        sim.turn_based = True
    else:
        sim.turn_based = False
    return overlay


def _manual_combat_pacing_source_active(sim, source="aim"):
    overlay = _combat_overlay_state(sim)
    source = str(source or "aim").strip().lower() or "aim"
    return bool(overlay.get("manual_pacing_sources", {}).get(source))


def _combat_turn_pacing_active(sim):
    overlay = _combat_overlay_state(sim)
    return bool(getattr(sim, "turn_based", False) or overlay.get("active") or overlay.get("manual_pacing"))
