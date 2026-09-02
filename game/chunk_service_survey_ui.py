"""Dedicated debug-only view of the authoritative neighborhood economy."""

from __future__ import annotations

from game.chunk_service_survey import chunk_service_survey_read, chunk_service_survey_state
from game.components import Position
from game.local_service_demand import (
    local_service_market_cache_stats,
    local_service_supply_coverage_read,
    neighborhood_service_market_read,
)
from game.neighborhood_housing import neighborhood_housing_read, neighborhood_housing_state
from game.neighborhood_businesses import neighborhood_business_read, neighborhood_business_state
from game.release_runtime import debug_mode_enabled
from game.report_debug_ui import clamp_debug_scroll, scroll_panel_body_dimensions
from game.service_category_registry import service_category_label
from ui.input_keys import (
    KEY_BACK_TAB,
    KEY_DOWN,
    KEY_END,
    KEY_HOME,
    KEY_LEFT,
    KEY_PAGE_DOWN,
    KEY_PAGE_UP,
    KEY_RIGHT,
    KEY_UP,
)


SERVICE_SURVEY_TABS = ("market", "housing", "business", "trace")


def default_service_survey_ui_state():
    return {
        "open": False,
        "tab": "market",
        "title": "Neighborhood Economy",
        "lines": [],
        "scroll": 0,
        "chunk": None,
        "follow_player": True,
        "seen_revision": (),
    }


def ensure_service_survey_ui_state(sim):
    state = getattr(sim, "service_survey_ui", None)
    if not isinstance(state, dict):
        state = default_service_survey_ui_state()
        sim.service_survey_ui = state
    for key, value in default_service_survey_ui_state().items():
        state.setdefault(key, value)
    if str(state.get("tab", "market")).lower() not in SERVICE_SURVEY_TABS:
        state["tab"] = "market"
    return state


def current_player_chunk(sim, player_eid):
    pos = sim.ecs.get(Position).get(player_eid)
    if pos is not None:
        return tuple(int(value) for value in sim.chunk_coords(int(pos.x), int(pos.y))[:2])
    active = getattr(sim, "active_chunk_coord", None)
    try:
        return (int(active[0]), int(active[1]))
    except (TypeError, ValueError, IndexError):
        return (0, 0)


def _signed(value):
    try:
        return f"{float(value):+.2f}"
    except (TypeError, ValueError):
        return "+0.00"


def _clock_label(sim, tick):
    if tick is None:
        return "not scheduled"
    traits = getattr(sim, "world_traits", {})
    clock = traits.get("clock", {}) if isinstance(traits, dict) else {}
    try:
        ticks_per_hour = max(60, int((clock or {}).get("ticks_per_hour", 600)))
        tick = int(tick)
    except (TypeError, ValueError):
        return "unknown"
    day_ticks = ticks_per_hour * 24
    day = tick // day_ticks
    hour_value = (tick % day_ticks) / float(ticks_per_hour)
    hour = int(hour_value)
    minute = int(round((hour_value - hour) * 60.0)) % 60
    return f"day {day}, {hour:02d}:{minute:02d} (t{tick})"


def _tab_title(active):
    labels = [f"[{tab.upper()}]" if tab == active else tab.upper() for tab in SERVICE_SURVEY_TABS]
    return f"Neighborhood Economy | {' '.join(labels)}"


def _revision_signature(sim):
    return (
        int(chunk_service_survey_state(sim, create=False).get("revision", 0) or 0),
        int(neighborhood_housing_state(sim, create=False).get("revision", 0) or 0),
        int(neighborhood_business_state(sim, create=False).get("revision", 0) or 0),
        int(local_service_market_cache_stats(sim).get("revision", 0) or 0),
    )


def _market_lines(sim, chunk, row):
    market_rows = list(neighborhood_service_market_read(sim, chunk))
    cache = local_service_market_cache_stats(sim, chunk)
    coverage = [
        miss for miss in local_service_supply_coverage_read(sim)
        if tuple(miss.get("chunk", ()) or ()) == tuple(chunk)
    ]
    lines = [
        "AUTHORITATIVE MARKET — strict chunk boundary; travel is an explicit consumer action.",
        f"Chunk {chunk[0]},{chunk[1]} | supply cache r{cache['revision']} | indexed categories {cache['chunk_categories']}",
        f"Coverage misses here {len(coverage)} | global {cache['coverage_misses']} | indexed properties {cache['indexed_properties']}",
        "",
        "Category       mass lived miss resist supply pressure age/blend",
    ]
    for item in market_rows:
        topic_id = str(item.get("topic_id", "") or "")
        age = item.get("survey_age_days")
        age_text = "cold" if age is None else f"{float(age):.1f}d"
        lines.append(
            f"{service_category_label(topic_id)[:12]:<12} {float(item.get('survey_mass', 0.0) or 0.0):>4.1f} "
            f"{float(item.get('revealed_demand', 0.0) or 0.0):>5.2f} {float(item.get('unmet_checks', 0.0) or 0.0):>4.1f} "
            f"{float(item.get('resistance', 0.0) or 0.0):>5.2f} {float(item.get('effective_supply', 0.0) or 0.0):>5.2f} "
            f"{float(item.get('opportunity_pressure', 0.0) or 0.0):>7.2f} {age_text}/{float(item.get('survey_blend', 0.0) or 0.0):.2f}"
        )
    lines.extend(("", "Formula: mass + 1.25*lived + 1.75*miss + .25*log1p(amount) - .35*resistance; divided by effective supply."))
    for miss in coverage:
        lines.append(f"COVERAGE MISS {miss.get('property_id')} | {miss.get('archetype')} | {','.join(miss.get('services', ()) or ()) or 'no raw keys'}")
    return lines


def _housing_lines(sim, chunk):
    row = neighborhood_housing_read(sim, chunk)
    lines = [
        "AUTHORITATIVE HOUSING — temporary and workplace residence remains demand.",
        f"Chunk {chunk[0]},{chunk[1]} | capacity {row.get('capacity', 0)} | occupied {row.get('occupied', 0)} | vacancies {row.get('vacancies', 0)}",
        f"Pressure {float(row.get('pressure', 0.0) or 0.0):.2f} | rent index {float(row.get('rent_index', 1.0) or 1.0):.2f} | average daily cost {float(row.get('average_daily_cost', 0.0) or 0.0):.2f}",
        f"Unhoused {row.get('unhoused', 0)} | temporary {row.get('temporary', 0)} | worksite {row.get('worksite', 0)}",
        f"Growth streak {row.get('growth_streak', 0)}/3 | active conversion {row.get('conversion_plan_property_id') or 'none'}",
        "",
        f"Permanent sites: {', '.join(row.get('property_ids', ()) or ()) or 'none'}",
        f"Vacant capacity: {', '.join(row.get('vacant_property_ids', ()) or ()) or 'none'}",
        f"Temporary sites: {', '.join(row.get('temporary_property_ids', ()) or ()) or 'none'}",
        f"Convertible vacant buildings: {', '.join(row.get('convertible_property_ids', ()) or ()) or 'none'}",
    ]
    return lines


def _business_lines(sim, chunk):
    state = neighborhood_business_state(sim, create=False)
    counters = state.get("counters", {}) if isinstance(state, dict) else {}
    rows = neighborhood_business_read(sim, chunk)
    lines = [
        "AUTHORITATIVE BUSINESS — daily indexed queue; player and protected capabilities cannot mutate.",
        f"Chunk {chunk[0]},{chunk[1]} | businesses {len(rows)} | reviews {int(counters.get('reviews', 0) or 0)} | max batch {int(counters.get('max_review_batch', 0) or 0)} | stale heap {int(counters.get('stale_heap_rows', 0) or 0)}",
        "",
    ]
    if not rows:
        lines.append("No indexed economic businesses in this chunk.")
    for item in rows:
        runtime = item.get("runtime", {}) if isinstance(item.get("runtime"), dict) else {}
        result = item.get("last_result", {}) if isinstance(item.get("last_result"), dict) else {}
        read = runtime.get("last_market_read", {}) if isinstance(runtime.get("last_market_read"), dict) else {}
        plan = item.get("plan", {}) if isinstance(item.get("plan"), dict) else {}
        guards = "/".join(name for name, enabled in (("player", item.get("player_protected")), ("essential", item.get("capability_protected"))) if enabled) or "autonomous"
        lines.extend((
            f"{item.get('name')} [{item.get('archetype') or 'business'}] {item.get('property_id')} | {guards}",
            f"  profit {float(result.get('profit', 0.0) or 0.0):+.1f} ema {float(runtime.get('profit_ema', 0.0) or 0.0):+.2f} | failure {float(runtime.get('failure_ema', 0.0) or 0.0):.2f} | reliability {float(result.get('reliability', 0.0) or 0.0):.2f}",
            f"  market actual {float(read.get('actual_signal', 0.0) or 0.0):.2f} perceived {float(read.get('perceived_signal', 0.0) or 0.0):.2f} manager {float(read.get('manager_fit', 0.0) or 0.0):.1f}",
            f"  state {'closed/listed' if item.get('closed') else 'open'} | plan {plan.get('kind', 'none')} {plan.get('status', '')} {plan.get('target_archetype', '')}",
            "",
        ))
    return lines


def _trace_lines(sim, chunk, row):
    lines = [
        "ECONOMY TRACE — bounded survey and mutation history; opening this view never creates work.",
        f"Chunk {chunk[0]},{chunk[1]} | newest rounds first",
        "",
    ]
    trace = list(row.get("trace", ()) or ())
    if not trace:
        lines.append("No completed survey rounds in this chunk yet.")
        lines.append("")
    for sample in reversed(trace):
        top = ", ".join(
            f"{service_category_label(topic_id)} {_signed(score)}"
            for topic_id, score in tuple(sample.get("top", ()) or ())[:5]
        )
        contexts = ", ".join(
            f"{name}:{count}"
            for name, count in dict(sample.get("contexts", {}) or {}).items()
        ) or "none"
        lines.extend((
            f"{_clock_label(sim, sample.get('tick'))} | respondents {int(sample.get('respondents', 0) or 0)} "
            f"| slot {int(sample.get('scheduled_slot', -1))} | delay {int(sample.get('delay_ticks', 0) or 0)}t",
            f"  context: {contexts}",
            f"  leading: {top or 'none'}",
            "",
        ))
    events = list((neighborhood_business_state(sim, create=False).get("events", ()) or ()))
    lines.append("Business/ownership consequences (newest first):")
    if not events:
        lines.append("  none")
    for event in reversed(events[-24:]):
        lines.append(f"  t{event.get('tick', 0)} {event.get('kind')} | {event.get('property_id', '')} | {event.get('target_archetype', event.get('reason', ''))}")
    return lines


def refresh_service_survey_ui(sim, player_eid, *, reset_scroll=False, tab=None):
    """Rebuild debug lines strictly from cached survey/economic reads."""

    state = ensure_service_survey_ui_state(sim)
    if tab in SERVICE_SURVEY_TABS:
        state["tab"] = tab
    chunk = current_player_chunk(sim, player_eid) if state.get("follow_player", True) else state.get("chunk")
    try:
        chunk = (int(chunk[0]), int(chunk[1]))
    except (TypeError, ValueError, IndexError):
        chunk = current_player_chunk(sim, player_eid)
    row = chunk_service_survey_read(sim, chunk)
    active_tab = str(state.get("tab", "market"))
    if active_tab == "housing":
        lines = _housing_lines(sim, chunk)
    elif active_tab == "business":
        lines = _business_lines(sim, chunk)
    elif active_tab == "trace":
        lines = _trace_lines(sim, chunk, row)
    else:
        active_tab = "market"
        lines = _market_lines(sim, chunk, row)
    lines.insert(1, f"View: {'following player chunk' if state.get('follow_player', True) else 'frozen on this chunk'}")
    state.update({
        "open": True,
        "tab": active_tab,
        "title": _tab_title(active_tab),
        "lines": lines,
        "chunk": chunk,
        "seen_revision": _revision_signature(sim),
    })
    if reset_scroll:
        state["scroll"] = 0
    return state


def refresh_service_survey_ui_if_stale(sim, player_eid):
    state = ensure_service_survey_ui_state(sim)
    if not debug_mode_enabled(sim):
        state["open"] = False
        return state
    if not state.get("open"):
        return state
    chunk = current_player_chunk(sim, player_eid) if state.get("follow_player", True) else state.get("chunk")
    if tuple(state.get("seen_revision", ())) != _revision_signature(sim) or tuple(state.get("chunk") or ()) != tuple(chunk or ()):
        refresh_service_survey_ui(sim, player_eid, reset_scroll=False)
    return state


def close_service_survey_ui(state):
    state["open"] = False
    state["scroll"] = 0


def _cycle_tab(host, step):
    state = ensure_service_survey_ui_state(host.sim)
    current = str(state.get("tab", "market"))
    index = SERVICE_SURVEY_TABS.index(current) if current in SERVICE_SURVEY_TABS else 0
    host._refresh_service_survey_ui(reset_scroll=True, tab=SERVICE_SURVEY_TABS[(index + int(step)) % len(SERVICE_SURVEY_TABS)])


def handle_service_survey_input(host, key, *, line_text_fn, wrap_display_lines_fn):
    state = ensure_service_survey_ui_state(host.sim)
    if not state.get("open"):
        return False
    if key in (27, ord("q"), ord("Q"), ord("e"), ord("E")):
        host._close_service_survey_ui()
        return True
    if key in (ord("d"), ord("D")):
        host._close_service_survey_ui()
        host._refresh_debug_ui(reset_scroll=True)
        return True
    if key in (ord("?"), ord("/")):
        host._help_state()["open"] = True
        return True
    if key in (9, KEY_RIGHT):
        _cycle_tab(host, 1)
        return True
    if key in (KEY_BACK_TAB, KEY_LEFT):
        _cycle_tab(host, -1)
        return True
    if key in (ord("1"), ord("2"), ord("3"), ord("4")):
        host._refresh_service_survey_ui(reset_scroll=True, tab=SERVICE_SURVEY_TABS[key - ord("1")])
        return True
    if key in (ord("f"), ord("F")):
        state["follow_player"] = not bool(state.get("follow_player", True))
        host._refresh_service_survey_ui(reset_scroll=False)
        return True
    if key in (ord("r"), ord("R")):
        host._refresh_service_survey_ui(reset_scroll=False)
        return True

    body_w, body_h = scroll_panel_body_dimensions(host.view, host.sim)
    if key in (KEY_UP, ord("k"), ord("K")):
        state["scroll"] = int(state.get("scroll", 0)) - 1
    elif key in (KEY_DOWN, ord("j"), ord("J")):
        state["scroll"] = int(state.get("scroll", 0)) + 1
    elif key == KEY_HOME:
        state["scroll"] = 0
        return True
    elif key == KEY_END:
        state["scroll"] = 10**9
    elif key == KEY_PAGE_UP:
        state["scroll"] = int(state.get("scroll", 0)) - 6
    elif key == KEY_PAGE_DOWN:
        state["scroll"] = int(state.get("scroll", 0)) + 6
    else:
        return True
    clamp_debug_scroll(
        state,
        body_w=body_w,
        body_h=body_h,
        line_text_fn=line_text_fn,
        wrap_display_lines_fn=wrap_display_lines_fn,
    )
    return True
