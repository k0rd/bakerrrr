"""Dialogue pressure helpers for repeated and adjacent topic probing.

This module keeps the social-cost rules separate from the large interaction
system.  It does not decide whether a response succeeds; it labels related
questions and gives the menu a readable way to show when the player is pressing.
"""

from __future__ import annotations


TOPIC_FAMILIES = {
    # Identity / social read
    "name": "identity",
    "history": "identity",
    "roots": "rapport",
    "job": "identity",
    "job_feel": "rapport",
    "routine": "identity",
    "rapport": "rapport",
    "check_in": "rapport",
    "day_feel": "rapport",
    "off_shift": "rapport",
    "care_about": "rapport",
    "read_player": "rapport",
    # Workplace / organization
    "workplace": "workplace",
    "organization": "workplace",
    "supervisor": "workplace",
    "coworkers": "workplace",
    "people": "workplace",
    "where_place": "location_followup",
    "hire": "workplace",
    "hire_manager": "workplace",
    "hire_staff": "workplace",
    "fire": "workplace",
    # Property casing / prep
    "services": "property_prep",
    "hours": "property_prep",
    "owner": "property_prep",
    "security": "property_prep",
    "access": "property_prep",
    "entry": "property_prep",
    "keyholder": "property_prep",
    "weak_point": "property_prep",
    # Local trouble / opportunities
    "local": "local_intel",
    "street_talk": "local_intel",
    "social_incident": "local_intel",
    "social_business": "local_intel",
    "local_economy": "local_intel",
    "social_opportunity": "local_intel",
    "social_relationship": "local_intel",
    "concern": "local_intel",
    "detail": "local_intel",
    "opportunities": "local_intel",
    "fallout": "local_intel",
    "objective": "local_intel",
    "angle": "local_intel",
    "risk": "local_intel",
    "attention": "local_intel",
    # Social graph
    "contacts": "social_access",
    "introduction": "social_access",
    "vouch": "social_access",
    # Service locator topics are all adjacent enough to count as asking around.
    "service_fuel": "service_locator",
    "service_repair": "service_locator",
    "service_contractor": "service_locator",
    "service_banking": "service_locator",
    "service_insurance": "service_locator",
    "service_rest": "service_locator",
    "service_transit": "service_locator",
    "service_rail": "service_locator",
    "service_bus": "service_locator",
    "service_shuttle": "service_locator",
    "service_ferry": "service_locator",
    "service_intel": "service_locator",
    "service_trade": "service_locator",
    "service_discreet_trade": "service_locator",
    "service_street_doctor": "service_locator",
    "service_outfitter": "service_locator",
    "service_justice": "service_locator",
    "service_used_cars": "service_locator",
    "service_vehicle_fetch": "service_locator",
    "service_gaming": "service_locator",
}


def clean_topic_id(topic_id):
    return str(topic_id or "").strip().lower()


def dialogue_topic_family(topic_id):
    """Return the semantic bucket used for repeated-probing pressure."""
    topic_id = clean_topic_id(topic_id)
    if not topic_id:
        return ""
    return TOPIC_FAMILIES.get(topic_id, topic_id)


def dialogue_family_counts(memory):
    """Return a normalized mutable family-count map for a dialogue memory dict."""
    if not isinstance(memory, dict):
        return {}
    counts = memory.get("topic_family_counts")
    if not isinstance(counts, dict):
        counts = {}
        # Backfill from old per-topic counts so old saves get the new pressure
        # shape without a migration step.
        topic_counts = memory.get("topic_counts")
        if isinstance(topic_counts, dict):
            for topic_id, value in topic_counts.items():
                family = dialogue_topic_family(topic_id)
                if not family:
                    continue
                try:
                    count = max(0, int(value))
                except (TypeError, ValueError):
                    count = 0
                counts[family] = counts.get(family, 0) + count
        memory["topic_family_counts"] = counts
    return counts


def repeated_topic_label(base_label, *, topic_id="", repeat_slot=0, ask_count=0, family_count=0):
    """Make duplicate menu rows read like social pressure instead of fresh topics."""
    label = str(base_label or "").strip()
    if not label:
        return label
    topic_id = clean_topic_id(topic_id)
    repeat_slot = max(0, int(repeat_slot or 0))
    ask_count = max(0, int(ask_count or 0))
    family_count = max(0, int(family_count or 0))
    pressure = max(ask_count, family_count)
    stem = label[:-1].strip() if label.endswith("?") else label
    lower = stem[:1].lower() + stem[1:] if stem else stem

    if repeat_slot >= 2 or pressure >= 4:
        verb = "Keep pushing"
    elif ask_count >= 2 or pressure >= 3:
        verb = "Press them"
    else:
        verb = "Ask again"

    if topic_id in {"weird", "pry", "insult"}:
        return label
    if verb == "Keep pushing":
        return f"Keep pushing: {stem}."
    return f"{verb} about {lower}."


def repeat_pressure_score(*, ask_count=0, family_count=0):
    """Small scalar used by callers to fold adjacent-topic spam into severity."""
    ask_count = max(0, int(ask_count or 0))
    family_count = max(0, int(family_count or 0))
    if ask_count <= 1 and family_count <= 1:
        return 0.0
    return max(0, ask_count - 1) * 0.24 + max(0, family_count - ask_count) * 0.11
