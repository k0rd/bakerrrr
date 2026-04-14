from __future__ import annotations

import curses

from ui.input_keys import ENTER_KEYS, KEY_DOWN, KEY_UP


def default_report_ui_state():
    return {
        "open": False,
        "kind": "progress",
        "title": "Operations Report",
        "lines": [],
        "scroll": 0,
        "rows": [],
        "selected_index": 0,
        "selected_property_id": None,
        "filter_mode": "visible",
    }


def ensure_report_ui_state(sim):
    state = getattr(sim, "report_ui", None)
    if not isinstance(state, dict):
        state = default_report_ui_state()
        sim.report_ui = state
        return state

    state.setdefault("open", False)
    state.setdefault("kind", "progress")
    state.setdefault("title", "Operations Report")
    state.setdefault("lines", [])
    state.setdefault("scroll", 0)
    state.setdefault("rows", [])
    state.setdefault("selected_index", 0)
    state.setdefault("selected_property_id", None)
    state.setdefault("filter_mode", "visible")
    return state


def default_debug_ui_state():
    return {
        "open": False,
        "kind": "conversation",
        "title": "Debug Overlay",
        "property_id": None,
        "lines": [],
        "scroll": 0,
    }


def ensure_debug_ui_state(sim):
    state = getattr(sim, "debug_ui", None)
    if not isinstance(state, dict):
        state = default_debug_ui_state()
        sim.debug_ui = state
        return state

    state.setdefault("open", False)
    state.setdefault("kind", "conversation")
    state.setdefault("title", "Debug Overlay")
    state.setdefault("property_id", None)
    state.setdefault("lines", [])
    state.setdefault("scroll", 0)
    return state


def scroll_panel_body_dimensions(view, sim):
    screen_w, screen_h = view.size()
    try:
        hud_lines = int(getattr(sim, "hud_lines", 10))
    except (TypeError, ValueError):
        hud_lines = 10
    hud_lines = max(1, hud_lines)
    map_h = max(1, min(sim.tilemap.height, screen_h - hud_lines))
    panel_w = min(max(56, screen_w - 4), screen_w)
    panel_w = max(28, panel_w)
    panel_h = min(max(12, map_h - 1), map_h)
    panel_h = max(8, panel_h)
    body_w = max(8, int(view_text_wrap_width(view, panel_w - 4)))
    body_h = max(1, panel_h - 4)
    return body_w, body_h


def view_text_wrap_width(view, width):
    width = max(1, int(width))
    helper = getattr(view, "text_wrap_width", None)
    if callable(helper):
        try:
            resolved = int(helper(width))
        except (TypeError, ValueError):
            resolved = width
        return max(1, resolved)
    return width


def report_display_lines(state, *, body_w, line_text_fn, wrap_display_lines_fn):
    raw_lines = list((state or {}).get("lines", ()) or ())
    if not raw_lines:
        raw_lines = ["No report data."]

    display_lines = []
    for raw in raw_lines:
        wrapped = wrap_display_lines_fn(raw, body_w) if line_text_fn(raw).strip() else [""]
        display_lines.extend(wrapped)
    return display_lines or ["No report data."]


def clamp_report_scroll(state, *, body_w, body_h, line_text_fn, wrap_display_lines_fn):
    display_lines = report_display_lines(
        state,
        body_w=body_w,
        line_text_fn=line_text_fn,
        wrap_display_lines_fn=wrap_display_lines_fn,
    )
    max_scroll = max(0, len(display_lines) - body_h)
    state["scroll"] = max(0, min(int(state.get("scroll", 0)), max_scroll))
    return state["scroll"]


def known_locations_list_height(*, body_h):
    return max(1, int(body_h) - 5)


def clamp_known_locations_selection(state, *, body_h):
    rows = list((state or {}).get("rows", ()) or [])
    if not rows:
        state["selected_index"] = 0
        state["selected_property_id"] = None
        state["scroll"] = 0
        return 0

    selected_index = max(0, min(int(state.get("selected_index", 0)), len(rows) - 1))
    list_h = max(1, min(known_locations_list_height(body_h=body_h), len(rows)))
    max_scroll = max(0, len(rows) - list_h)
    scroll = max(0, min(int(state.get("scroll", 0)), max_scroll))
    if selected_index < scroll:
        scroll = selected_index
    elif selected_index >= scroll + list_h:
        scroll = selected_index - list_h + 1

    state["selected_index"] = selected_index
    state["selected_property_id"] = str(rows[selected_index].get("property_id", "")).strip() or None
    state["scroll"] = scroll
    return selected_index


def selected_known_location_row(state, *, body_h):
    rows = list((state or {}).get("rows", ()) or [])
    if not rows:
        return None
    selected_index = clamp_known_locations_selection(state, body_h=body_h)
    if 0 <= selected_index < len(rows):
        return rows[selected_index]
    return None


def refresh_report_ui(
    host,
    *,
    reset_scroll=False,
    kind=None,
    build_known_locations_report_fn,
    build_progress_report_fn,
    line_text_fn,
    wrap_display_lines_fn,
):
    state = ensure_report_ui_state(host.sim)
    previous_scroll = int(state.get("scroll", 0))
    previous_index = int(state.get("selected_index", 0))
    previous_property_id = str(state.get("selected_property_id", "") or "").strip()
    next_kind = str(kind or state.get("kind", "progress")).strip().lower() or "progress"
    kind_changed = next_kind != str(state.get("kind", "progress")).strip().lower()
    if next_kind == "known_locations":
        filter_mode = str(state.get("filter_mode", "visible")).strip().lower() or "visible"
        if filter_mode not in {"visible", "hidden"}:
            filter_mode = "visible"
        state["filter_mode"] = filter_mode
        report = build_known_locations_report_fn(include_hidden=(filter_mode == "hidden"))
    else:
        next_kind = "progress"
        report = build_progress_report_fn()

    state["open"] = True
    state["kind"] = next_kind
    state["title"] = str(report.get("title", "Operations Report")).strip() or "Operations Report"
    state["lines"] = list(report.get("lines", ()) or ())
    state["rows"] = list(report.get("rows", ()) or ())

    body_w, body_h = scroll_panel_body_dimensions(host.view, host.sim)
    if next_kind == "known_locations":
        rows = state["rows"]
        if reset_scroll or kind_changed:
            selected_index = 0
            state["scroll"] = 0
        else:
            selected_index = max(0, min(previous_index, len(rows) - 1)) if rows else 0
            if previous_property_id:
                for idx, row in enumerate(rows):
                    if str(row.get("property_id", "")).strip() == previous_property_id:
                        selected_index = idx
                        break
        state["selected_index"] = selected_index
        clamp_known_locations_selection(state, body_h=body_h)
    else:
        state["selected_index"] = 0
        state["selected_property_id"] = None
        if reset_scroll or kind_changed:
            state["scroll"] = 0
        else:
            state["scroll"] = previous_scroll
        clamp_report_scroll(
            state,
            body_w=body_w,
            body_h=body_h,
            line_text_fn=line_text_fn,
            wrap_display_lines_fn=wrap_display_lines_fn,
        )
    return True


def close_report_ui(state):
    state["open"] = False
    state["scroll"] = 0


def debug_display_lines(state, *, body_w, line_text_fn, wrap_display_lines_fn):
    raw_lines = list((state or {}).get("lines", ()) or ())
    if not raw_lines:
        raw_lines = ["No debug data."]

    display_lines = []
    for raw in raw_lines:
        wrapped = wrap_display_lines_fn(raw, body_w) if line_text_fn(raw).strip() else [""]
        display_lines.extend(wrapped)
    return display_lines or ["No debug data."]


def clamp_debug_scroll(state, *, body_w, body_h, line_text_fn, wrap_display_lines_fn):
    display_lines = debug_display_lines(
        state,
        body_w=body_w,
        line_text_fn=line_text_fn,
        wrap_display_lines_fn=wrap_display_lines_fn,
    )
    max_scroll = max(0, len(display_lines) - body_h)
    state["scroll"] = max(0, min(int(state.get("scroll", 0)), max_scroll))
    return state["scroll"]


def refresh_debug_ui(
    host,
    *,
    reset_scroll=False,
    build_debug_overlay_fn,
    line_text_fn,
    wrap_display_lines_fn,
):
    state = ensure_debug_ui_state(host.sim)
    previous_scroll = int(state.get("scroll", 0))
    debug_panel = build_debug_overlay_fn()
    state["open"] = True
    state["title"] = str(debug_panel.get("title", "Debug Overlay")).strip() or "Debug Overlay"
    state["lines"] = list(debug_panel.get("lines", ()) or ())
    state["scroll"] = 0 if reset_scroll else previous_scroll
    body_w, body_h = scroll_panel_body_dimensions(host.view, host.sim)
    clamp_debug_scroll(
        state,
        body_w=body_w,
        body_h=body_h,
        line_text_fn=line_text_fn,
        wrap_display_lines_fn=wrap_display_lines_fn,
    )
    return True


def close_debug_ui(state):
    state["open"] = False
    state["scroll"] = 0


def handle_report_input(host, key, *, line_text_fn, wrap_display_lines_fn):
    state = ensure_report_ui_state(host.sim)
    if not state.get("open"):
        return False
    report_kind = str(state.get("kind", "progress")).strip().lower() or "progress"

    if key in (ord("?"), ord("/")):
        host._help_state()["open"] = True
        return True

    if key in (ord("o"), ord("O")):
        if report_kind == "progress":
            host._close_report_ui()
        else:
            host._refresh_report_ui(reset_scroll=True, kind="progress")
        return True

    if key in (ord("y"), ord("Y")):
        if report_kind == "known_locations":
            host._close_report_ui()
        else:
            host._refresh_known_locations_ui(reset_scroll=True)
        return True

    if key == ord("L"):
        host._close_report_ui()
        host._refresh_log_ui(reset_scroll=True, focus_end=True)
        return True

    if key == ord("D"):
        host._close_report_ui()
        host._refresh_debug_ui(reset_scroll=True)
        return True

    if key in (27, ord("q"), ord("Q")):
        host._close_report_ui()
        return True

    key_home = getattr(curses, "KEY_HOME", None)
    key_end = getattr(curses, "KEY_END", None)
    key_page_up = getattr(curses, "KEY_PPAGE", None)
    key_page_down = getattr(curses, "KEY_NPAGE", None)
    body_w, body_h = scroll_panel_body_dimensions(host.view, host.sim)

    if report_kind == "known_locations":
        if key in ENTER_KEYS or key in (ord("e"), ord("E"), ord("x"), ord("X")):
            host._inspect_selected_known_location()
            return True

        if key in (ord("g"), ord("G")):
            host._start_selected_known_location_walk()
            return True

        if key in (ord("m"), ord("M")):
            host._mark_selected_known_location()
            return True

        if key in (ord("h"), ord("H")):
            host._toggle_known_location_hidden_view()
            return True

        if key in (ord("r"), ord("R")):
            host._toggle_selected_known_location_hidden()
            return True

        if key in (KEY_UP, ord("k"), ord("K")):
            state["selected_index"] = int(state.get("selected_index", 0)) - 1
            clamp_known_locations_selection(state, body_h=body_h)
            return True

        if key in (KEY_DOWN, ord("j"), ord("J")):
            state["selected_index"] = int(state.get("selected_index", 0)) + 1
            clamp_known_locations_selection(state, body_h=body_h)
            return True

        if key_home is not None and key == key_home:
            state["selected_index"] = 0
            clamp_known_locations_selection(state, body_h=body_h)
            return True

        if key_end is not None and key == key_end:
            state["selected_index"] = max(0, len(list(state.get("rows", ()) or ())) - 1)
            clamp_known_locations_selection(state, body_h=body_h)
            return True

        step = max(1, known_locations_list_height(body_h=body_h) - 1)
        if key_page_up is not None and key == key_page_up:
            state["selected_index"] = int(state.get("selected_index", 0)) - step
            clamp_known_locations_selection(state, body_h=body_h)
            return True

        if key_page_down is not None and key == key_page_down:
            state["selected_index"] = int(state.get("selected_index", 0)) + step
            clamp_known_locations_selection(state, body_h=body_h)
            return True
        return True

    if key in (KEY_UP, ord("k"), ord("K")):
        state["scroll"] = int(state.get("scroll", 0)) - 1
        clamp_report_scroll(
            state,
            body_w=body_w,
            body_h=body_h,
            line_text_fn=line_text_fn,
            wrap_display_lines_fn=wrap_display_lines_fn,
        )
        return True

    if key in (KEY_DOWN, ord("j"), ord("J")):
        state["scroll"] = int(state.get("scroll", 0)) + 1
        clamp_report_scroll(
            state,
            body_w=body_w,
            body_h=body_h,
            line_text_fn=line_text_fn,
            wrap_display_lines_fn=wrap_display_lines_fn,
        )
        return True

    if key_home is not None and key == key_home:
        state["scroll"] = 0
        return True

    if key_end is not None and key == key_end:
        state["scroll"] = max(
            0,
            len(
                report_display_lines(
                    state,
                    body_w=body_w,
                    line_text_fn=line_text_fn,
                    wrap_display_lines_fn=wrap_display_lines_fn,
                )
            ) - 1,
        )
        return True

    if key_page_up is not None and key == key_page_up:
        state["scroll"] = int(state.get("scroll", 0)) - 6
        clamp_report_scroll(
            state,
            body_w=body_w,
            body_h=body_h,
            line_text_fn=line_text_fn,
            wrap_display_lines_fn=wrap_display_lines_fn,
        )
        return True

    if key_page_down is not None and key == key_page_down:
        state["scroll"] = int(state.get("scroll", 0)) + 6
        clamp_report_scroll(
            state,
            body_w=body_w,
            body_h=body_h,
            line_text_fn=line_text_fn,
            wrap_display_lines_fn=wrap_display_lines_fn,
        )
        return True

    return True


def handle_debug_input(host, key, *, line_text_fn, wrap_display_lines_fn):
    state = ensure_debug_ui_state(host.sim)
    if not state.get("open"):
        return False

    if key in (ord("?"), ord("/")):
        host._help_state()["open"] = True
        return True

    if key in (ord("o"), ord("O")):
        host._close_debug_ui()
        host._refresh_report_ui(reset_scroll=True)
        return True

    if key in (ord("y"), ord("Y")):
        host._close_debug_ui()
        host._refresh_known_locations_ui(reset_scroll=True)
        return True

    if key == ord("L"):
        host._close_debug_ui()
        host._refresh_log_ui(reset_scroll=True, focus_end=True)
        return True

    if key in (27, ord("d"), ord("D"), ord("q"), ord("Q")):
        host._close_debug_ui()
        return True

    body_w, body_h = scroll_panel_body_dimensions(host.view, host.sim)

    if key in (KEY_UP, ord("k"), ord("K")):
        state["scroll"] = int(state.get("scroll", 0)) - 1
        clamp_debug_scroll(
            state,
            body_w=body_w,
            body_h=body_h,
            line_text_fn=line_text_fn,
            wrap_display_lines_fn=wrap_display_lines_fn,
        )
        return True

    if key in (KEY_DOWN, ord("j"), ord("J")):
        state["scroll"] = int(state.get("scroll", 0)) + 1
        clamp_debug_scroll(
            state,
            body_w=body_w,
            body_h=body_h,
            line_text_fn=line_text_fn,
            wrap_display_lines_fn=wrap_display_lines_fn,
        )
        return True

    key_home = getattr(curses, "KEY_HOME", None)
    if key_home is not None and key == key_home:
        state["scroll"] = 0
        return True

    key_end = getattr(curses, "KEY_END", None)
    if key_end is not None and key == key_end:
        display_lines = debug_display_lines(
            state,
            body_w=body_w,
            line_text_fn=line_text_fn,
            wrap_display_lines_fn=wrap_display_lines_fn,
        )
        state["scroll"] = max(0, len(display_lines) - body_h)
        return True

    key_page_up = getattr(curses, "KEY_PPAGE", None)
    if key_page_up is not None and key == key_page_up:
        state["scroll"] = int(state.get("scroll", 0)) - 6
        clamp_debug_scroll(
            state,
            body_w=body_w,
            body_h=body_h,
            line_text_fn=line_text_fn,
            wrap_display_lines_fn=wrap_display_lines_fn,
        )
        return True

    key_page_down = getattr(curses, "KEY_NPAGE", None)
    if key_page_down is not None and key == key_page_down:
        state["scroll"] = int(state.get("scroll", 0)) + 6
        clamp_debug_scroll(
            state,
            body_w=body_w,
            body_h=body_h,
            line_text_fn=line_text_fn,
            wrap_display_lines_fn=wrap_display_lines_fn,
        )
        return True

    return True


def _clip_text(text, width):
    text = str(text or "")
    if width <= 0:
        return ""
    if len(text) <= width:
        return text
    if width <= 3:
        return text[:width]
    return text[: width - 3] + "..."


def _draw_box(view, panel_x, panel_y, panel_w, panel_h):
    if panel_w < 2 or panel_h < 2:
        return
    top = "+" + ("-" * (panel_w - 2)) + "+"
    mid = "|" + (" " * (panel_w - 2)) + "|"
    bot = "+" + ("-" * (panel_w - 2)) + "+"
    view.draw_text(panel_x, panel_y, top)
    for row in range(1, panel_h - 1):
        view.draw_text(panel_x, panel_y + row, mid)
    view.draw_text(panel_x, panel_y + panel_h - 1, bot)


def _centered_scroll_panel_geometry(screen_w, map_h):
    panel_w = min(max(56, screen_w - 4), screen_w)
    panel_w = max(28, panel_w)
    panel_h = min(max(12, map_h - 1), map_h)
    panel_h = max(8, panel_h)
    panel_x = max(0, (screen_w - panel_w) // 2)
    panel_y = max(0, (map_h - panel_h) // 2)
    return panel_x, panel_y, panel_w, panel_h


def draw_report_modal(
    view,
    report_ui,
    *,
    screen_w,
    map_h,
    view_text_wrap_width_fn,
    draw_display_line_fn,
    clip_display_line_fn,
    wrap_display_lines_fn,
    line_text_fn,
    known_location_list_line_fn,
    known_location_detail_lines_fn,
):
    panel_x, panel_y, panel_w, panel_h = _centered_scroll_panel_geometry(screen_w, map_h)
    _draw_box(view, panel_x, panel_y, panel_w, panel_h)

    title = str(report_ui.get("title", "Operations Report")).strip() or "Operations Report"
    view.draw_text(panel_x + 2, panel_y + 1, _clip_text(f" {title} ", panel_w - 4))

    body_w = max(8, int(view_text_wrap_width_fn(view, panel_w - 4)))
    body_h = max(1, panel_h - 4)
    report_kind = str(report_ui.get("kind", "progress")).strip().lower() or "progress"
    if report_kind == "known_locations":
        rows = list(report_ui.get("rows", ()) or ())
        filter_mode = str(report_ui.get("filter_mode", "visible")).strip().lower() or "visible"
        selected_index = max(0, min(int(report_ui.get("selected_index", 0)), len(rows) - 1)) if rows else 0
        report_ui["selected_index"] = selected_index
        row_count = len(rows)
        detail_reserve = 8 if rows else 4
        list_h = max(1, min(max(1, row_count), max(1, body_h - detail_reserve)))
        max_scroll = max(0, len(rows) - list_h)
        scroll = max(0, min(int(report_ui.get("scroll", 0)), max_scroll))
        if rows:
            if selected_index < scroll:
                scroll = selected_index
            elif selected_index >= scroll + list_h:
                scroll = selected_index - list_h + 1
        else:
            scroll = 0
        report_ui["scroll"] = scroll

        mode_label = "hidden" if filter_mode == "hidden" else "active"
        count_label = f"{len(rows)} {mode_label}"
        recency_label = "sorted by last revised"
        view.draw_text(panel_x + 2, panel_y + 2, _clip_text(f"{count_label} | {recency_label}", panel_w - 4))

        list_y = panel_y + 3
        visible_rows = rows[scroll: scroll + list_h]
        for idx, row in enumerate(visible_rows):
            absolute = scroll + idx
            entry_line = known_location_list_line_fn(
                row,
                ordinal=absolute + 1,
                selected=(absolute == selected_index),
            )
            draw_display_line_fn(
                panel_x + 1,
                list_y + idx,
                clip_display_line_fn(entry_line, panel_w - 2),
                panel_w - 2,
            )

        if not rows:
            empty_text = "(no hidden locations)" if filter_mode == "hidden" else "(no known locations)"
            view.draw_text(panel_x + 2, list_y, _clip_text(empty_text, panel_w - 4))

        detail_y = list_y + list_h + 1
        detail_h = max(1, (panel_y + panel_h - 2) - detail_y)
        detail_lines = []
        if rows:
            row = rows[selected_index]
            detail_lines.extend(known_location_detail_lines_fn(row))
        else:
            detail_lines.append("Nothing selected.")
            detail_lines.append("Press H to switch between active and hidden notebook entries.")

        display_detail_lines = []
        for raw in detail_lines:
            wrapped = wrap_display_lines_fn(raw, panel_w - 4) if line_text_fn(raw).strip() else [""]
            display_detail_lines.extend(wrapped)
        visible_detail_lines = display_detail_lines[:detail_h]
        for idx, line in enumerate(visible_detail_lines):
            draw_display_line_fn(
                panel_x + 2,
                detail_y + idx,
                clip_display_line_fn(line, panel_w - 4),
                panel_w - 4,
            )

        footer_bits = []
        if scroll > 0:
            footer_bits.append("more above")
        if scroll + list_h < len(rows):
            footer_bits.append("more below")
        footer = " | ".join(footer_bits) if footer_bits else ""
        action_verb = "restore" if filter_mode == "hidden" else "hide"
        action_tail = f"Enter inspect | G go | M mark | R {action_verb} | H hidden | Y close | O ops | L log | D debug | ? help"
        footer = f"{footer} | {action_tail}" if footer else action_tail
    else:
        display_lines = report_display_lines(
            report_ui,
            body_w=body_w,
            line_text_fn=line_text_fn,
            wrap_display_lines_fn=wrap_display_lines_fn,
        )
        scroll = max(0, min(int(report_ui.get("scroll", 0)), len(display_lines) - 1))
        report_ui["scroll"] = scroll
        visible_lines = display_lines[scroll: scroll + body_h]

        for idx, line in enumerate(visible_lines[:body_h]):
            draw_display_line_fn(
                panel_x + 2,
                panel_y + 2 + idx,
                clip_display_line_fn(line, body_w),
                body_w,
            )

        footer_bits = []
        if scroll > 0:
            footer_bits.append("more above")
        if scroll + body_h < len(display_lines):
            footer_bits.append("more below")
        footer = " | ".join(footer_bits) if footer_bits else ""
        action_tail = "O close | Y locations | L log | D debug | ? help"
        footer = f"{footer} | {action_tail}" if footer else f"{action_tail} | Up/Down scroll"

    view.draw_text(panel_x + 2, panel_y + panel_h - 2, _clip_text(footer, panel_w - 4))


def draw_debug_modal(
    view,
    debug_ui,
    *,
    screen_w,
    map_h,
    view_text_wrap_width_fn,
    draw_display_line_fn,
    clip_display_line_fn,
    wrap_display_lines_fn,
    line_text_fn,
):
    panel_x, panel_y, panel_w, panel_h = _centered_scroll_panel_geometry(screen_w, map_h)
    _draw_box(view, panel_x, panel_y, panel_w, panel_h)

    title = str(debug_ui.get("title", "Debug Overlay")).strip() or "Debug Overlay"
    view.draw_text(panel_x + 2, panel_y + 1, _clip_text(f" {title} ", panel_w - 4))

    body_w = max(8, int(view_text_wrap_width_fn(view, panel_w - 4)))
    body_h = max(1, panel_h - 4)
    display_lines = debug_display_lines(
        debug_ui,
        body_w=body_w,
        line_text_fn=line_text_fn,
        wrap_display_lines_fn=wrap_display_lines_fn,
    )
    max_scroll = max(0, len(display_lines) - body_h)
    scroll = max(0, min(int(debug_ui.get("scroll", 0)), max_scroll))
    debug_ui["scroll"] = scroll
    visible_lines = display_lines[scroll: scroll + body_h]

    for idx, line in enumerate(visible_lines[:body_h]):
        draw_display_line_fn(
            panel_x + 2,
            panel_y + 2 + idx,
            clip_display_line_fn(line, body_w),
            body_w,
        )

    footer_bits = []
    if scroll > 0:
        footer_bits.append("more above")
    if scroll + body_h < len(display_lines):
        footer_bits.append("more below")
    footer = " | ".join(footer_bits) if footer_bits else ""
    footer = (
        f"{footer} | D close | O ops | Y locations | L log | ? help"
        if footer
        else "D close | O ops | Y locations | L log | Up/Down scroll | ? help"
    )
    view.draw_text(panel_x + 2, panel_y + panel_h - 2, _clip_text(footer, panel_w - 4))
