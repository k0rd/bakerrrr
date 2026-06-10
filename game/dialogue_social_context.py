"""Pure social-context read helpers for NPC dialogue routing."""


DIALOGUE_SOCIAL_CONTEXT_BANDS = (
    "stranger",
    "introduced",
    "met",
    "familiar",
    "coworker",
    "trusted_coworker",
    "trusted_local",
    "protective",
    "friend",
    "family",
    "partner",
    "guarded",
)


def _unit(value, default=0.0):
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return float(default)


def _count(value):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return 0


def dialogue_social_context_read(context):
    """Return a compact, recomputable dialogue routing read from saved context."""
    context = context if isinstance(context, dict) else {}
    bond = context.get("bond") if isinstance(context.get("bond"), dict) else {}
    kind = str(bond.get("kind", "") or "").strip().lower()
    trust = _unit(bond.get("trust", 0.0))
    closeness = _unit(bond.get("closeness", 0.0))
    protectiveness = _unit(bond.get("protectiveness", 0.0))
    relationship_score = max(
        _unit(context.get("social_standing", 0.0)),
        (trust * 0.45) + (closeness * 0.35) + (protectiveness * 0.2),
    )
    opened_count = _count(context.get("opened_count", 0))
    met_directly = bool(context.get("met_directly"))
    history = bool(context.get("relationship_has_nontrivial_history")) or bool(context.get("relationship_history"))
    pressure_tier = str(context.get("pressure_tier", "low") or "low").strip().lower() or "low"
    recent_offense = bool(context.get("recent_offense"))
    guarded = bool(context.get("guarded"))
    introduced = bool(context.get("intro_entry")) or bool(context.get("intro_source_name"))

    band = "stranger"
    reason = "no direct history"
    if guarded or recent_offense:
        band = "guarded"
        reason = "recent offense or guarded boundary"
    elif not met_directly and opened_count <= 0:
        band = "introduced" if introduced else "stranger"
        reason = "introduced lead" if introduced else "first contact"
    elif kind in {"family", "partner"} and relationship_score >= 0.48:
        band = kind
        reason = f"{kind} bond"
    elif kind == "friend" and relationship_score >= 0.52:
        band = "friend"
        reason = "friend bond"
    elif kind == "coworker":
        trusted_work = (
            relationship_score >= 0.5
            and (
                trust >= 0.6
                or closeness >= 0.56
                or protectiveness >= 0.62
                or history
            )
            and (met_directly or opened_count > 0 or history)
        )
        band = "trusted_coworker" if trusted_work else "coworker"
        reason = "trusted coworker bond" if trusted_work else "workplace bond"
    elif met_directly and protectiveness >= 0.62:
        band = "protective"
        reason = "protective bond"
    elif met_directly and relationship_score >= 0.62:
        band = "trusted_local"
        reason = "trusted local standing"
    elif met_directly and relationship_score >= 0.42:
        band = "familiar"
        reason = "direct familiarity"
    elif met_directly or opened_count > 0:
        band = "met"
        reason = "direct contact"

    can_deep = (
        met_directly
        and opened_count >= 2
        and pressure_tier != "high"
        and band not in {"guarded", "stranger", "introduced", "met", "coworker"}
        and relationship_score >= 0.46
    )
    can_read_player = (
        can_deep
        and relationship_score >= 0.56
        and band in {"trusted_coworker", "trusted_local", "protective", "friend", "family", "partner"}
    )
    can_check_in = (
        met_directly
        and history
        and pressure_tier != "high"
        and band != "guarded"
    )
    return {
        "band": band,
        "reason": reason,
        "kind": kind,
        "trust": trust,
        "closeness": closeness,
        "protectiveness": protectiveness,
        "score": relationship_score,
        "met_directly": met_directly,
        "opened_count": opened_count,
        "has_history": history,
        "pressure_tier": pressure_tier,
        "deep_topics_ok": can_deep,
        "read_player_ok": can_read_player,
        "check_in_ok": can_check_in,
        "pressure_tight": pressure_tier in {"medium", "high"},
    }
