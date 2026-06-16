"""Shared console-plus-view final notices."""

from __future__ import annotations

import sys
import textwrap
import time

from ui.input_keys import (
    ENTER_KEYS,
    KEY_DOWN,
    KEY_END,
    KEY_HOME,
    KEY_PAGE_DOWN,
    KEY_PAGE_UP,
    KEY_UP,
)


DISMISS_KEYS = set(ENTER_KEYS) | {27, ord("q"), ord("Q")}


def _as_lines(lines):
    result = []
    for raw in lines or ():
        text = str(raw).rstrip()
        if text:
            result.append(text)
    return result


def _stream_for(name):
    return sys.stderr if str(name or "").strip().lower() == "stderr" else sys.stdout


def _print_notice(title, lines, *, stream="stdout"):
    target = _stream_for(stream)
    header = str(title or "Notice").strip() or "Notice"
    print(header, file=target)
    for line in _as_lines(lines):
        print(f"- {line}", file=target)


def _view_size(view):
    try:
        width, height = view.size()
        return max(24, int(width)), max(10, int(height))
    except Exception:
        return 80, 24


def _wrap_notice_lines(lines, width):
    wrapped = []
    body_width = max(20, int(width))
    for raw in _as_lines(lines):
        chunks = textwrap.wrap(raw, width=body_width, replace_whitespace=False, drop_whitespace=True)
        wrapped.extend(chunks or [""])
    return wrapped


def _notice_modal_geometry(width, height):
    width = max(24, int(width))
    height = max(10, int(height))
    panel_w = max(32, min(width - 4, int(round(width * 0.75))))
    panel_h = max(9, min(height - 2, int(round(height * 0.75))))
    left = max(0, (width - panel_w) // 2)
    top = max(0, (height - panel_h) // 2)
    body_w = max(20, panel_w - 4)
    body_h = max(1, panel_h - 5)
    return {
        "panel_w": panel_w,
        "panel_h": panel_h,
        "left": left,
        "top": top,
        "body_w": body_w,
        "body_h": body_h,
    }


def _draw_modal(view, title, lines, *, scroll=0):
    width, height = _view_size(view)
    geometry = _notice_modal_geometry(width, height)
    panel_w = geometry["panel_w"]
    panel_h = geometry["panel_h"]
    left = geometry["left"]
    top = geometry["top"]
    body_w = geometry["body_w"]
    body_h = geometry["body_h"]
    wrapped = _wrap_notice_lines(lines, body_w)
    max_scroll = max(0, len(wrapped) - body_h)
    scroll = max(0, min(int(scroll), max_scroll))

    clear = getattr(view, "clear", None)
    if callable(clear):
        clear()
    draw = getattr(view, "draw_text", None)
    if not callable(draw):
        return max_scroll

    title = str(title or "Notice").strip() or "Notice"
    try:
        draw(left, top, "+" + "-" * (panel_w - 2) + "+", color="objective")
        draw(left, top + 1, "|" + " " * (panel_w - 2) + "|", color="objective")
        draw(left + 2, top + 1, title[:body_w], color="objective")
        draw(left, top + 2, "+" + "-" * (panel_w - 2) + "+", color="objective")
        for row in range(body_h):
            y = top + 3 + row
            draw(left, y, "|" + " " * (panel_w - 2) + "|", color="default")
            index = scroll + row
            if 0 <= index < len(wrapped):
                draw(left + 2, y, wrapped[index][:body_w], color="default")
        footer = "Up/Down scroll  PgUp/PgDn page  Home/End jump  Enter/Esc/Q close"
        if max_scroll > 0:
            footer = f"{scroll + 1}-{min(len(wrapped), scroll + body_h)}/{len(wrapped)}  " + footer
        draw(left, top + panel_h - 2, "|" + " " * (panel_w - 2) + "|", color="objective")
        draw(left + 2, top + panel_h - 2, footer[:body_w], color="scout")
        draw(left, top + panel_h - 1, "+" + "-" * (panel_w - 2) + "+", color="objective")
    except Exception:
        return max_scroll

    refresh = getattr(view, "refresh", None)
    if callable(refresh):
        refresh()
    return max_scroll


def show_final_notice(view=None, *, title="Notice", lines=(), severity="info", stream="stdout", wait=True, print_notice=True):
    lines = _as_lines(lines)
    if print_notice:
        _print_notice(title, lines, stream=stream)
    if view is None:
        return False
    if not callable(getattr(view, "draw_text", None)) or not callable(getattr(view, "refresh", None)):
        return False

    scroll = 0
    max_scroll = _draw_modal(view, title, lines, scroll=scroll)
    if not wait or not callable(getattr(view, "get_key", None)):
        return True

    get_key = getattr(view, "get_key")
    pump_window = getattr(view, "pump_window", None)
    while True:
        if callable(pump_window):
            pump_window()
        key = get_key()
        if key is None:
            time.sleep(0.02)
            continue
        if key in DISMISS_KEYS:
            return True
        if key == KEY_UP:
            scroll = max(0, scroll - 1)
        elif key == KEY_DOWN:
            scroll = min(max_scroll, scroll + 1)
        elif key == KEY_PAGE_UP:
            scroll = max(0, scroll - 8)
        elif key == KEY_PAGE_DOWN:
            scroll = min(max_scroll, scroll + 8)
        elif key == KEY_HOME:
            scroll = 0
        elif key == KEY_END:
            scroll = max_scroll
        else:
            continue
        max_scroll = _draw_modal(view, title, lines, scroll=scroll)


def run_end_notice(run_end):
    if not isinstance(run_end, dict) or not bool(run_end.get("show_post_curses")):
        return None
    outcome = str(run_end.get("outcome", "unknown")).strip().upper()
    reason = str(run_end.get("reason", "")).strip().replace("_", " ")
    objective_title = str(run_end.get("objective_title", "Run")).strip() or "Run"
    tick = int(run_end.get("tick", 0) or 0)
    title = f"RUN {outcome} @ tick {tick}: {objective_title}"
    if reason:
        title += f" [{reason}]"
    return {
        "title": title,
        "lines": _as_lines(run_end.get("summary_lines", ())),
        "severity": "info",
        "stream": "stdout",
    }


def show_run_end_notice(view, run_end, *, wait=True, print_notice=True):
    notice = run_end_notice(run_end)
    if not notice:
        return False
    shown = show_final_notice(view, wait=wait, print_notice=print_notice, **notice)
    if isinstance(run_end, dict):
        run_end["final_notice_printed"] = bool(print_notice)
        run_end["final_notice_rendered"] = bool(shown)
    return shown
