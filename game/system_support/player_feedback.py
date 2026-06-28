"""Shared player-facing log helpers for tactile action feedback."""

from ui.text_attrs import A_BOLD


PLAYER_FEEDBACK_LOG_STYLES = {
    "location": {
        "channel": "general",
        "priority": "high",
        "dedupe_window": 6,
        "badge": "SITE",
        "badge_color": "property_fixture",
    },
    "movement": {
        "channel": "general",
        "priority": "high",
        "dedupe_window": 3,
        "badge": "MOVE",
        "badge_color": "player",
    },
    "pickup": {
        "channel": "general",
        "priority": "high",
        "dedupe_window": 2,
        "badge": "GET",
        "badge_color": "item_token",
    },
    "interaction": {
        "channel": "general",
        "priority": "high",
        "dedupe_window": 3,
        "badge": "ACT",
        "badge_color": "property_fixture",
    },
    "commerce": {
        "channel": "general",
        "priority": "high",
        "dedupe_window": 2,
        "badge": "CR",
        "badge_color": "item_token",
    },
    "craft": {
        "channel": "general",
        "priority": "high",
        "dedupe_window": 2,
        "badge": "MAKE",
        "badge_color": "item_tool",
    },
    "game": {
        "channel": "general",
        "priority": "high",
        "dedupe_window": 2,
        "badge": "PLAY",
        "badge_color": "casino_accent",
    },
}


def _segment(text, color=None, attrs=0, **extras):
    segment = {
        "text": str(text),
        "color": color,
        "attrs": int(attrs or 0),
    }
    for key, value in extras.items():
        segment[str(key)] = value
    return segment


def _player_feedback_style(kind):
    key = str(kind or "interaction").strip().lower() or "interaction"
    return dict(PLAYER_FEEDBACK_LOG_STYLES.get(key, PLAYER_FEEDBACK_LOG_STYLES["interaction"]))


def _log_player_feedback(
    sim,
    text,
    *,
    kind="interaction",
    channel=None,
    priority=None,
    dedupe_window=None,
    dedupe_key=None,
):
    spec = _player_feedback_style(kind)
    if channel is not None:
        spec["channel"] = channel
    if priority is not None:
        spec["priority"] = priority
    if dedupe_window is not None:
        spec["dedupe_window"] = dedupe_window
    plain_text = str(text)
    badge = str(spec.get("badge", "") or "").strip()
    badge_color = spec.get("badge_color")
    if badge:
        rich = [
            _segment("[", color="building_edge"),
            _segment(badge, color=badge_color, attrs=A_BOLD),
            _segment("] ", color="building_edge"),
            _segment(plain_text),
        ]
        sim.log.add_rich(
            rich,
            text=plain_text,
            channel=spec["channel"],
            priority=spec["priority"],
            dedupe_window=spec.get("dedupe_window"),
            dedupe_key=dedupe_key,
        )
        return
    sim.log.add(
        plain_text,
        channel=spec["channel"],
        priority=spec["priority"],
        dedupe_window=spec.get("dedupe_window"),
        dedupe_key=dedupe_key,
    )
