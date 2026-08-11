"""Shared state helpers and host metadata for the casino overlay."""

from __future__ import annotations


CASINO_FLOOR_ARCHETYPES = frozenset({"casino", "gaming_hall"})
CASINO_MACHINE_SERVICE_IDS = (
    "slots",
    "video_poker",
    "keno",
    "plinko",
    "crash",
)
CASINO_TABLE_SERVICE_IDS = (
    "roulette",
    "craps",
    "baccarat",
    "three_card_poker",
    "casino_holdem",
    "texas_holdem_cash",
    "twenty_one",
    "three_bones",
    "bloom_cards",
)


def casino_host_style(prop):
    archetype = str(((prop or {}).get("metadata", {}) or {}).get("archetype", "")).strip().lower()
    if archetype in CASINO_FLOOR_ARCHETYPES:
        return "floor"
    return "standalone_machine"


def default_casino_ui_state():
    return {
        "open": False,
        "mode": "floor",
        "host_style": "floor",
        "property_id": None,
        "title": "Casino",
        "subtitle": "",
        "body_lines": [],
        "body_focus_line": -1,
        "body_scroll": 0,
        "body_scroll_max": 0,
        "body_page_size": 1,
        "body_scroll_manual": False,
        "rail_lines": [],
        "rows": [],
        "selected_index": 0,
        "hint": "",
        "close_pending": False,
        "floor_page": "games",
        "service": "",
        "session": None,
        "art": None,
        "return_to": "",
        "return_option_id": "",
    }


def ensure_casino_ui_state(sim):
    state = getattr(sim, "casino_ui", None)
    if not isinstance(state, dict):
        state = default_casino_ui_state()
        sim.casino_ui = state
    state.setdefault("open", False)
    state.setdefault("mode", "floor")
    state.setdefault("host_style", "floor")
    state.setdefault("property_id", None)
    state.setdefault("title", "Casino")
    state.setdefault("subtitle", "")
    state.setdefault("body_lines", [])
    state.setdefault("body_focus_line", -1)
    state.setdefault("body_scroll", 0)
    state.setdefault("body_scroll_max", 0)
    state.setdefault("body_page_size", 1)
    state.setdefault("body_scroll_manual", False)
    state.setdefault("rail_lines", [])
    state.setdefault("rows", [])
    state.setdefault("selected_index", 0)
    state.setdefault("hint", "")
    state.setdefault("close_pending", False)
    state.setdefault("floor_page", "games")
    state.setdefault("service", "")
    state.setdefault("session", None)
    state.setdefault("art", None)
    state.setdefault("return_to", "")
    state.setdefault("return_option_id", "")
    return state
