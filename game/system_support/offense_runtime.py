"""Shared offense profile and scoring helpers.

This module owns offense defaults, offense-profile loading, and the shared
helpers that turn actions into offense events or readable severity tiers.
"""

from __future__ import annotations

import json
from pathlib import Path

from engine.events import Event

from game.content_warnings import warn_content_fallback
from game.system_support.awareness_runtime import observation_payload_for_position


DEFAULT_ACTION_OFFENSE_BASE = {
    "move": 2,
    "cover_hop": 2,
    "floor_change": 3,
    "wait": 0,
    "interact": 14,
    "toggle_door_lock": 14,
    "pickup_item": 1,
    "drop_item": 0,
    "use_item": 6,
    "purchase_property": 4,
    "toggle_cover": 0,
    "toggle_sneak": 0,
    "melee_attack": 8,
    "fire_weapon": 18,
    "cycle_weapon": 0,
    "banking": 0,
    "insurance": 0,
    "trade_buy": 0,
    "trade_sell": 0,
    "overworld_travel": 0,
    "zoom_city_enter": 0,
    "zoom_overworld": 0,
    "scan": 0,
}

ASSAULT_OFFENSE_CONTEXTS = frozenset({
    "unarmed_assault",
    "melee_assault",
    "armed_assault",
})
WILDLIFE_OFFENSE_CONTEXTS = frozenset({
    "wildlife_harassment",
    "wildlife_hunting",
})
HOMICIDE_OFFENSE_CONTEXTS = frozenset({"homicide"})
VIOLENT_OFFENSE_CONTEXTS = ASSAULT_OFFENSE_CONTEXTS | frozenset({"explosive_discharge"}) | HOMICIDE_OFFENSE_CONTEXTS
OFFICIAL_REPORTABLE_OFFENSE_CONTEXTS = VIOLENT_OFFENSE_CONTEXTS | frozenset({
    "trespass",
    "tamper",
    "item_theft",
    "contraband_use",
})

DEFAULT_ACTION_OFFENSE_CONTEXT_BONUS = {
    "ordinary": 0,
    "trespass": 18,
    "tamper": 60,
    "not_for_sale_attempt": 10,
    "item_theft": 48,
    "contraband_use": 32,
    "unarmed_assault": 14,
    "melee_assault": 28,
    "armed_assault": 56,
    "wildlife_harassment": 2,
    "wildlife_hunting": 4,
    "explosive_discharge": 68,
    "homicide": 92,
}

DEFAULT_OFFENSE_TIERS = (
    {"label": "none", "max": 0},
    {"label": "low", "max": 14},
    {"label": "medium", "max": 34},
    {"label": "high", "max": 59},
    {"label": "severe", "max": 100},
)

DEFAULT_OFFENSE_NOTICE_RADIUS = {
    "base": 2,
    "min": 2,
    "max": 12,
    "step_divisor": 12,
}

OFFENSE_PROFILE_PATH = Path(__file__).resolve().parents[1] / "offense_profile.json"


def _int_or_default(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _load_offense_profile(path=OFFENSE_PROFILE_PATH):
    profile = {
        "action_base": dict(DEFAULT_ACTION_OFFENSE_BASE),
        "context_bonus": dict(DEFAULT_ACTION_OFFENSE_CONTEXT_BONUS),
        "tiers": [dict(item) for item in DEFAULT_OFFENSE_TIERS],
        "notice_radius": dict(DEFAULT_OFFENSE_NOTICE_RADIUS),
    }

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        warn_content_fallback(path, "built-in offense profile defaults", exc=exc)
        return profile
    except (json.JSONDecodeError, OSError) as exc:
        warn_content_fallback(path, "built-in offense profile defaults", exc=exc)
        return profile

    if not isinstance(raw, dict):
        warn_content_fallback(path, "built-in offense profile defaults", problem="top-level JSON must be an object")
        return profile

    action_base = raw.get("action_base")
    if isinstance(action_base, dict):
        for key, value in action_base.items():
            if not isinstance(key, str):
                continue
            ivalue = _int_or_default(value, None)
            if ivalue is None:
                continue
            profile["action_base"][key] = max(0, min(100, ivalue))

    context_bonus = raw.get("context_bonus")
    if isinstance(context_bonus, dict):
        for key, value in context_bonus.items():
            if not isinstance(key, str):
                continue
            ivalue = _int_or_default(value, None)
            if ivalue is None:
                continue
            profile["context_bonus"][key] = max(0, min(100, ivalue))

    tiers = raw.get("tiers")
    if isinstance(tiers, list):
        parsed_tiers = []
        for item in tiers:
            if not isinstance(item, dict):
                continue
            label = item.get("label")
            max_value = _int_or_default(item.get("max"), None)
            if not isinstance(label, str) or max_value is None:
                continue
            label = label.strip().lower()
            if not label:
                continue
            parsed_tiers.append({
                "label": label,
                "max": max(0, min(100, max_value)),
            })
        if parsed_tiers:
            parsed_tiers.sort(key=lambda row: row["max"])
            profile["tiers"] = parsed_tiers

    radius = raw.get("notice_radius")
    if isinstance(radius, dict):
        base = _int_or_default(radius.get("base"), profile["notice_radius"]["base"])
        min_radius = _int_or_default(radius.get("min"), profile["notice_radius"]["min"])
        max_radius = _int_or_default(radius.get("max"), profile["notice_radius"]["max"])
        divisor = _int_or_default(
            radius.get("step_divisor"),
            profile["notice_radius"]["step_divisor"],
        )
        min_radius = max(1, min_radius)
        max_radius = max(min_radius, max_radius)
        divisor = max(1, divisor)
        profile["notice_radius"] = {
            "base": base,
            "min": min_radius,
            "max": max_radius,
            "step_divisor": divisor,
        }

    return profile


OFFENSE_PROFILE = _load_offense_profile()
ACTION_OFFENSE_BASE = OFFENSE_PROFILE["action_base"]
ACTION_OFFENSE_CONTEXT_BONUS = OFFENSE_PROFILE["context_bonus"]
OFFENSE_TIERS = OFFENSE_PROFILE["tiers"]
OFFENSE_NOTICE_RADIUS = OFFENSE_PROFILE["notice_radius"]


def _offense_tier(score):
    score = max(0, min(100, _int_or_default(score, 0)))
    for tier in OFFENSE_TIERS:
        if score <= tier["max"]:
            return tier["label"]
    if OFFENSE_TIERS:
        return OFFENSE_TIERS[-1]["label"]
    return "severe"


def _offense_notice_radius(score):
    score = max(0, min(100, _int_or_default(score, 0)))
    base = OFFENSE_NOTICE_RADIUS["base"]
    min_radius = OFFENSE_NOTICE_RADIUS["min"]
    max_radius = OFFENSE_NOTICE_RADIUS["max"]
    divisor = OFFENSE_NOTICE_RADIUS["step_divisor"]
    return max(min_radius, min(max_radius, base + (score // divisor)))


def _offense_score_for_action(action, context="ordinary"):
    base = ACTION_OFFENSE_BASE.get(action, 0)
    bonus = ACTION_OFFENSE_CONTEXT_BONUS.get(context, 0)
    return max(0, min(100, base + bonus))


def _emit_action_offense_event(sim, eid, action, x, y, z, context="ordinary", score=None, **extra):
    if score is None:
        score = _offense_score_for_action(action, context=context)
    if score <= 0:
        return

    payload = {
        "offender_eid": eid,
        "action": action,
        "context": context,
        "offense_score": score,
        "offense_tier": _offense_tier(score),
        "x": x,
        "y": y,
        "z": z,
        "radius": _offense_notice_radius(score),
    }
    if isinstance(extra, dict):
        payload.update(extra)
    if not any(
        key in payload
        for key in ("observer_eids", "accountable_observer_eids", "observation_channels", "witnessed", "witnesses")
    ):
        payload.update(
            observation_payload_for_position(
                sim,
                x,
                y,
                z,
                exclude_eid=eid,
                exclude_eids=(payload.get("victim_eid"), payload.get("excluded_observer_eids")),
                offender_eid=eid,
                observation_channels=("actor_witness",),
            )
        )
    sim.emit(Event("action_offense", **payload))
