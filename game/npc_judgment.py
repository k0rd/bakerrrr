"""NPC judgment helper.

This module provides a small, deterministic, NPC-facing layer that takes
neutral opportunity facts and converts them into a set of judgment signals
(urgency / invitation / tone hints) that dialogue can use.

The goal is to keep opportunity data neutral and stable, while letting NPCs
express their own evaluation of how important a given opportunity is.
"""

import random


def _clamp(value, lo=0.0, hi=1.0):
    try:
        v = float(value)
    except (TypeError, ValueError):
        return float(lo)
    return max(float(lo), min(float(hi), v))


def _risk_score(risk_label):
    risk = str(risk_label or "").strip().lower()
    return {
        "calm": 0.0,
        "low": 0.1,
        "exposed": 0.45,
        "hazardous": 0.85,
    }.get(risk, 0.15)


def _reward_score(reward):
    # Normalize a rough score from reward components.
    if not isinstance(reward, dict):
        return 0.0
    credits = max(0, int(reward.get("credits", 0)))
    standing = max(0, int(reward.get("standing", 0)))
    intel = max(0, int(reward.get("intel", 0)))
    # Scale everything to ~0..1 range.
    credit_score = min(1.0, credits / 40.0)
    standing_score = min(1.0, standing / 4.0)
    intel_score = min(1.0, intel / 6.0)
    return (credit_score * 0.6) + (standing_score * 0.2) + (intel_score * 0.2)


def _distance_score(distance):
    return max(0.0, min(1.0, 1.0 - (float(distance) / 12.0)))


def _pressure_score(pressure_tier):
    tier = str(pressure_tier or "").strip().lower()
    return {
        "low": 0.0,
        "medium": 0.25,
        "high": 0.5,
    }.get(tier, 0.0)


def _map_to_urgency(score):
    if score >= 0.70:
        return "high"
    if score >= 0.35:
        return "medium"
    return "low"


def evaluate_opportunity_judgment(
    sim,
    npc_eid,
    opportunity_fact,
    *,
    pressure_tier="low",
    rapport=0.0,
    tone="",
    seed=None,
):
    """Evaluate an NPC-facing judgment for a single opportunity.

    Returns a dict with fields like `urgency`, `invitation`, `voice_tone`, and
    a `reason` string for debugging.
    """

    # Keep deterministic per NPC + opportunity.
    base_seed = seed if seed is not None else f"{getattr(sim, 'seed', 0)}"  # fallback
    uid = f"{base_seed}:npc-judgment:{npc_eid}:{opportunity_fact.get('id', 0)}"
    rnd = random.Random(uid)

    # Basic scoring.
    risk = str(opportunity_fact.get("risk", "low")).strip().lower()
    distance = int(opportunity_fact.get("distance", 0) or 0)
    reward = opportunity_fact.get("reward", {})

    risk_s = _risk_score(risk)
    reward_s = _reward_score(reward)
    distance_s = _distance_score(distance)
    pressure_s = _pressure_score(pressure_tier)

    # Combine into a single urgency inference.
    # More reward, more risk, less distance, and more pressure increases urgency.
    urgency_raw = (reward_s * 0.45) + (risk_s * 0.35) + (distance_s * 0.15) + (pressure_s * 0.05)
    urgency = _map_to_urgency(urgency_raw)

    # Invitation: should the NPC mention it at all?
    # Higher rapport and higher urgency make it more likely.
    score = urgency_raw + (min(1.0, max(0.0, float(rapport))) * 0.25)
    if score > 0.75:
        invitation = "mention"
    elif score > 0.40:
        invitation = "consider"
    else:
        invitation = "pass"

    # Voice tone hints.
    if urgency == "high":
        voice_tone = "eager"
    elif urgency == "medium":
        voice_tone = "cautious"
    else:
        voice_tone = "dry"

    # Add a deterministic “flavor” note for template selection.
    flavor = rnd.choice(["sharp", "flat", "neutral"])

    return {
        "opportunity_id": int(opportunity_fact.get("id", 0) or 0),
        "urgency": urgency,
        "invitation": invitation,
        "voice_tone": voice_tone,
        "flavor": flavor,
        "reason": (
            f"urgency=({urgency_raw:.2f},{urgency}) risk={risk} "
            f"reward={reward_s:.2f} dist={distance} press={pressure_tier}"
        ),
    }
