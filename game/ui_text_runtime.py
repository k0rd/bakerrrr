"""Shared UI text, log, and wrapping helpers."""

import curses
import textwrap


def _int_or_default(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _tick_duration_label(sim, ticks):
    try:
        total_ticks = int(ticks)
    except (TypeError, ValueError):
        total_ticks = 0
    total_ticks = max(0, total_ticks)
    if total_ticks <= 0:
        return "0t"

    world_traits = getattr(sim, "world_traits", {})
    clock = world_traits.get("clock", {}) if isinstance(world_traits, dict) else {}
    try:
        ticks_per_hour = int(clock.get("ticks_per_hour", 600))
    except (TypeError, ValueError, AttributeError):
        ticks_per_hour = 600
    ticks_per_hour = max(60, ticks_per_hour)

    hours = total_ticks / float(ticks_per_hour)
    if hours >= 1.0:
        rounded = round(hours, 1)
        if abs(rounded - int(rounded)) < 0.05:
            return f"{int(round(rounded))}h"
        return f"{rounded:.1f}h"
    return f"{total_ticks}t"


def _grid_distance(ax, ay, bx, by):
    return max(abs(ax - bx), abs(ay - by))


def _segment(text, color=None, attrs=0, **extras):
    segment = {
        "text": str(text),
        "color": color,
        "attrs": int(attrs or 0),
    }
    for key, value in extras.items():
        segment[str(key)] = value
    return segment


def _segments_text(segments):
    return "".join(str(segment.get("text", "")) for segment in segments or () if isinstance(segment, dict))


def _rich_line(segments, text=None):
    normalized = []
    for segment in segments or ():
        if not isinstance(segment, dict):
            continue
        seg_text = str(segment.get("text", ""))
        if not seg_text:
            continue
        extras = {
            key: value
            for key, value in segment.items()
            if key not in {"text", "color", "attrs"}
        }
        normalized.append(_segment(
            seg_text,
            color=segment.get("color"),
            attrs=segment.get("attrs", 0),
            **extras,
        ))
    plain = str(text) if text is not None else _segments_text(normalized)
    return {
        "text": plain,
        "segments": normalized,
    }


def _line_text(line):
    if isinstance(line, dict):
        return str(line.get("text", ""))
    return str(line)


def _line_segments(line):
    if isinstance(line, dict):
        segments = line.get("segments")
        if isinstance(segments, list):
            return segments
    segments = getattr(line, "segments", None)
    if isinstance(segments, list):
        return segments
    return None


LOG_PRIORITY_LOW = 0
LOG_PRIORITY_NORMAL = 1
LOG_PRIORITY_HIGH = 2
LOG_PRIORITY_CRITICAL = 3

LOG_FILTER_PRESETS = (
    {
        "id": "all",
        "label": "All",
        "channels": None,
        "min_priority": LOG_PRIORITY_LOW,
    },
    {
        "id": "priority",
        "label": "Priority",
        "channels": None,
        "min_priority": LOG_PRIORITY_HIGH,
    },
    {
        "id": "mission",
        "label": "Mission",
        "channels": {"mission", "opportunity"},
        "min_priority": LOG_PRIORITY_LOW,
    },
    {
        "id": "combat",
        "label": "Combat/Aggro",
        "channels": {"combat", "alerts"},
        "min_priority": LOG_PRIORITY_LOW,
    },
    {
        "id": "status",
        "label": "Status",
        "channels": {"status"},
        "min_priority": LOG_PRIORITY_LOW,
    },
)


def _line_channel(line):
    if isinstance(line, dict):
        value = str(line.get("channel", "general") or "general").strip().lower()
        return value or "general"
    return "general"


def _line_priority(line):
    if isinstance(line, dict):
        try:
            return int(line.get("priority", LOG_PRIORITY_NORMAL))
        except (TypeError, ValueError):
            return LOG_PRIORITY_NORMAL
    return LOG_PRIORITY_NORMAL


def _line_tick(line):
    if isinstance(line, dict):
        value = line.get("tick")
        try:
            return None if value is None else int(value)
        except (TypeError, ValueError):
            return None
    return None


def _line_sequence(line):
    if isinstance(line, dict):
        try:
            return int(line.get("sequence", 0))
        except (TypeError, ValueError):
            return 0
    return 0


def _log_filter_spec(filter_id):
    current = str(filter_id or "all").strip().lower() or "all"
    for spec in LOG_FILTER_PRESETS:
        if spec["id"] == current:
            return spec
    return LOG_FILTER_PRESETS[0]


def _log_filter_ids():
    return [spec["id"] for spec in LOG_FILTER_PRESETS]


def _log_filter_label(filter_id):
    return _log_filter_spec(filter_id)["label"]


def _cycle_log_filter_id(filter_id, step=1):
    filter_ids = _log_filter_ids()
    if not filter_ids:
        return "all"
    current = str(filter_id or "all").strip().lower() or "all"
    try:
        index = filter_ids.index(current)
    except ValueError:
        index = 0
    return filter_ids[(index + int(step)) % len(filter_ids)]


def _sorted_log_lines(lines):
    return sorted(
        list(lines or ()),
        key=lambda line: (
            -1 if _line_tick(line) is None else _line_tick(line),
            _line_priority(line),
            _line_sequence(line),
        ),
    )


def _line_matches_log_filter(line, filter_id):
    spec = _log_filter_spec(filter_id)
    if _line_priority(line) < int(spec.get("min_priority", LOG_PRIORITY_LOW)):
        return False
    channels = spec.get("channels")
    if channels is not None and _line_channel(line) not in set(channels):
        return False
    return True


def _filtered_log_lines(lines, filter_id):
    return [line for line in _sorted_log_lines(lines) if _line_matches_log_filter(line, filter_id)]


def _log_prefix(line):
    priority = _line_priority(line)
    if priority >= LOG_PRIORITY_CRITICAL:
        return "!! "
    if priority >= LOG_PRIORITY_HIGH:
        return "! "
    return "- "


def _log_display_line(line):
    segments = _line_segments(line)
    if segments:
        return _rich_line(segments, text=_line_text(line))

    prefix = _log_prefix(line)
    priority = _line_priority(line)
    if priority >= LOG_PRIORITY_CRITICAL:
        prefix_color = "projectile"
    elif priority >= LOG_PRIORITY_HIGH:
        prefix_color = "property_asset"
    else:
        prefix_color = "building_edge"
    prefix_attrs = getattr(curses, "A_BOLD", 0) if priority >= LOG_PRIORITY_HIGH else 0
    prefixed_segments = [
        _segment(prefix, color=prefix_color, attrs=prefix_attrs),
        _segment(_line_text(line)),
    ]
    return _rich_line(prefixed_segments, text=prefix + _line_text(line))


def _hud_log_lines(lines, filter_id, budget):
    budget = max(0, int(budget))
    if budget <= 0:
        return []

    filtered = list(_filtered_log_lines(lines, filter_id))
    if not filtered:
        return []

    indexed = list(enumerate(filtered))
    recent_budget = indexed[-budget:]
    recent_indexes = {idx for idx, _line in recent_budget}
    recent_min_priority = min(
        (_line_priority(line) for _idx, line in recent_budget),
        default=LOG_PRIORITY_LOW,
    )
    sticky_indexes = []
    sticky_limit = min(2, budget)
    sticky_window = indexed[-max(budget * 4, 12):]
    for idx, line in reversed(sticky_window):
        line_priority = _line_priority(line)
        if line_priority < LOG_PRIORITY_HIGH:
            continue
        if idx in recent_indexes or idx in sticky_indexes:
            continue
        if line_priority <= recent_min_priority:
            continue
        sticky_indexes.insert(0, idx)
        if len(sticky_indexes) >= sticky_limit:
            break

    selected_indexes = list(sticky_indexes)
    for idx, _line in recent_budget:
        if idx not in selected_indexes:
            selected_indexes.append(idx)

    sticky_set = set(sticky_indexes)
    while len(selected_indexes) > budget:
        removed = False
        for pos, idx in enumerate(selected_indexes):
            if idx in sticky_set:
                continue
            del selected_indexes[pos]
            removed = True
            break
        if not removed:
            selected_indexes = selected_indexes[-budget:]
            break
    return [filtered[idx] for idx in selected_indexes]


def _line_with_prefix(line, prefix):
    prefix = str(prefix)
    segments = _line_segments(line)
    if not segments:
        return prefix + _line_text(line)
    prefixed = [_segment(prefix)]
    prefixed.extend(segments)
    return _rich_line(prefixed, text=prefix + _line_text(line))


def _line_with_suffix(line, suffix):
    suffix = str(suffix)
    if not suffix:
        return line
    segments = _line_segments(line)
    if not segments:
        return _line_text(line) + suffix
    appended = list(segments)
    appended.append(_segment(suffix))
    return _rich_line(appended, text=_line_text(line) + suffix)


def _legend_line(text, glyph=None, color=None, prefix="", attrs=0, semantic_id=None):
    segments = []
    plain = ""
    prefix = str(prefix)
    if prefix:
        segments.append(_segment(prefix))
        plain += prefix
    glyph_text = str(glyph)[:1] if glyph not in (None, "") else ""
    if glyph_text:
        extras = {"inline_glyph": True}
        if semantic_id:
            extras["semantic_id"] = str(semantic_id)
        segments.append(_segment(glyph_text, color=color, attrs=attrs, **extras))
        plain += glyph_text
        if text:
            segments.append(_segment(" "))
            plain += " "
    text = str(text)
    if text:
        segments.append(_segment(text))
        plain += text
    return _rich_line(segments, text=plain)


def _bullet_display_line(text, *, bullet="-", bullet_color="building_edge", text_color=None):
    text = str(text or "").strip()
    if not text:
        return ""
    bold = getattr(curses, "A_BOLD", 0)
    segments = [
        _segment(f"{str(bullet)[:1]} ", color=bullet_color, attrs=bold),
        _segment(text, color=text_color),
    ]
    return _rich_line(segments, text=f"{str(bullet)[:1]} {text}")


def _known_location_summary_bit_color(bit):
    label = str(bit or "").strip().lower()
    if not label:
        return None
    if "confirmed" in label:
        return "property_service"
    if "owned" in label:
        return "player"
    if label.endswith("lead") or "lead" in label:
        return "objective"
    if label.startswith("services "):
        return "property_service"
    if "vehicle" in label:
        return "vehicle_player"
    return "human"


def _business_sentiment_color(key):
    label = str(key or "").strip().lower()
    if label == "staple":
        return "player"
    if label == "chill":
        return "property_service"
    if label == "quality_plus":
        return "property_service"
    if label == "quality_minus":
        return "projectile"
    if label == "gouging":
        return "objective"
    if label == "troubled":
        return "projectile"
    return "human"


def _known_location_business_sentiment_line(row):
    row = row if isinstance(row, dict) else {}
    designations = [
        designation
        for designation in tuple(row.get("business_sentiment_designations", ()) or ())
        if isinstance(designation, dict)
        and str(designation.get("symbol", "")).strip()
        and str(designation.get("label", "")).strip()
    ]
    if not designations:
        return ""
    bold = getattr(curses, "A_BOLD", 0)
    segments = [
        _segment("Street read: ", color="building_edge", attrs=bold),
    ]
    for idx, designation in enumerate(designations):
        if idx:
            segments.append(_segment(" | ", color="building_edge"))
        symbol = str(designation.get("symbol", "")).strip()
        label = str(designation.get("label", "")).strip()
        color = _business_sentiment_color(designation.get("key"))
        segments.append(_segment(symbol, color=color, attrs=bold))
        segments.append(_segment(f" {label}", color="human"))
    return _rich_line(segments, text=_segments_text(segments))


def _known_location_business_reputation_scope_line(row):
    row = row if isinstance(row, dict) else {}
    scope = row.get("business_reputation_scope", {}) if isinstance(row.get("business_reputation_scope", {}), dict) else {}
    label = str(scope.get("label", "")).strip()
    if not label:
        return ""
    bold = getattr(curses, "A_BOLD", 0)
    segments = [
        _segment("Street reach: ", color="building_edge", attrs=bold),
        _segment(label, color="objective"),
    ]
    return _rich_line(segments, text=_segments_text(segments))


def _known_location_business_sentiment_legend_line():
    bold = getattr(curses, "A_BOLD", 0)
    entries = (
        ("*", "staple", "staple"),
        ("~", "chill", "chill"),
        ("+", "quality_plus", "quality"),
        ("-", "quality_minus", "rough"),
        ("$", "gouging", "gouger"),
        ("!", "troubled", "trouble"),
    )
    segments = [
        _segment("Legend: ", color="building_edge", attrs=bold),
    ]
    for idx, (symbol, key, label) in enumerate(entries):
        if idx:
            segments.append(_segment(" | ", color="building_edge"))
        segments.append(_segment(symbol, color=_business_sentiment_color(key), attrs=bold))
        segments.append(_segment(f" {label}", color="human"))
    return _rich_line(segments, text=_segments_text(segments))


def _known_location_summary_line(row):
    row = row if isinstance(row, dict) else {}
    confidence = int(round(float(row.get("confidence", 0.0)) * 100.0))
    summary_bits = [
        str(bit).strip()
        for bit in row.get("summary_bits", ())
        if str(bit).strip()
    ]
    bold = getattr(curses, "A_BOLD", 0)
    segments = [
        _segment(f"{confidence}% confident", color="player", attrs=bold),
    ]
    for bit in summary_bits:
        segments.append(_segment(" | ", color="building_edge"))
        segments.append(_segment(bit, color=_known_location_summary_bit_color(bit)))
    return _rich_line(segments, text=_segments_text(segments))


def _known_location_detail_lines(row):
    row = row if isinstance(row, dict) else {}
    lines = []
    legend_line = row.get("legend_line")
    if isinstance(legend_line, dict):
        lines.append(legend_line)
    else:
        name = str(row.get("name", "location")).strip() or "location"
        coords = str(row.get("coords", "coords unknown")).strip() or "coords unknown"
        lines.append(f"{name} @ {coords}")
    lines.append(_known_location_summary_line(row))
    sentiment_line = _known_location_business_sentiment_line(row)
    if sentiment_line:
        lines.append(sentiment_line)
    scope_line = _known_location_business_reputation_scope_line(row)
    if scope_line:
        lines.append(scope_line)
    if sentiment_line:
        lines.append(_known_location_business_sentiment_legend_line())
    for fact in row.get("fact_lines", ()):
        bullet = _bullet_display_line(fact, bullet="-", bullet_color="building_edge")
        if bullet:
            lines.append(bullet)
    return lines


def _known_location_list_line(row, *, ordinal=1, selected=False):
    row = row if isinstance(row, dict) else {}
    base_line = row.get("legend_line")
    if not isinstance(base_line, dict):
        name = str(row.get("name", "location")).strip() or "location"
        coords = str(row.get("coords", "coords unknown")).strip() or "coords unknown"
        base_line = f"{name} @ {coords}"

    confidence = max(0, min(100, int(round(float(row.get("confidence", 0.0)) * 100.0))))
    marker_color = "player" if selected else "building_edge"
    marker_attrs = getattr(curses, "A_BOLD", 0) if selected else 0
    confidence_color = "property_service" if confidence >= 80 else ("property_asset" if confidence >= 50 else "projectile")

    segments = [
        _segment(">" if selected else " ", color=marker_color, attrs=marker_attrs),
        _segment(f"{max(1, int(ordinal)):02d} ", color="building_edge", attrs=marker_attrs),
    ]
    base_segments = _line_segments(base_line)
    if base_segments:
        segments.extend(base_segments)
    else:
        segments.append(_segment(_line_text(base_line)))
    segments.extend([
        _segment(" | ", color="building_edge"),
        _segment(f"{confidence}%", color=confidence_color, attrs=marker_attrs),
    ])
    designations = [
        designation
        for designation in tuple(row.get("business_sentiment_designations", ()) or ())
        if isinstance(designation, dict) and str(designation.get("symbol", "")).strip()
    ]
    if designations:
        segments.append(_segment(" | ", color="building_edge"))
        segments.append(_segment("rep ", color="building_edge", attrs=marker_attrs))
        for designation in designations[:3]:
            segments.append(_segment(
                str(designation.get("symbol", "")).strip()[:2],
                color=_business_sentiment_color(designation.get("key")),
                attrs=marker_attrs or getattr(curses, "A_BOLD", 0),
            ))
    return _rich_line(segments, text=f"{'>' if selected else ' '}{max(1, int(ordinal)):02d} {_line_text(base_line)} | {confidence}%{' | rep ' + ''.join(str(designation.get('symbol', '')).strip()[:2] for designation in designations[:3]) if designations else ''}")


def _known_person_detail_lines(row):
    row = row if isinstance(row, dict) else {}
    name = str(row.get("name", "<unknown>")).strip() or "<unknown>"
    appearance = str(row.get("appearance_description", "<unknown>")).strip() or "<unknown>"
    relationship = str(row.get("relationship_detail", "<unknown>")).strip() or "<unknown>"
    connection = str(row.get("connection_text", "<unknown>")).strip() or "<unknown>"
    history_lines = tuple(row.get("history_lines", ()) or ())

    lines = [name]
    lines.append(f"Appearance: {appearance}")
    lines.append(f"How they seem to feel about you: {relationship}")
    lines.append(f"Connection: {connection}")
    lines.append("Shared history:")
    for history in history_lines or ("<unknown>",):
        bullet = _bullet_display_line(history, bullet="-", bullet_color="building_edge")
        if bullet:
            lines.append(bullet)
    for fact in row.get("fact_lines", ()):
        bullet = _bullet_display_line(fact, bullet="-", bullet_color="building_edge")
        if bullet:
            lines.append(bullet)
    return lines


def _known_person_list_line(row, *, ordinal=1, selected=False):
    row = row if isinstance(row, dict) else {}
    name = str(row.get("name", "<unknown>")).strip() or "<unknown>"
    appearance = str(row.get("appearance_summary", "<unknown>")).strip() or "<unknown>"
    relationship = str(row.get("relationship_summary", "<unknown>")).strip() or "<unknown>"
    marker_color = "player" if selected else "building_edge"
    marker_attrs = getattr(curses, "A_BOLD", 0) if selected else 0
    name_color = "human" if name != "<unknown>" else "building_edge"
    appearance_color = "property_asset" if appearance != "<unknown>" else "building_edge"
    relationship_color = "property_service" if relationship not in {"<unknown>", "do not trust you", "on edge around you"} else (
        "projectile" if relationship in {"do not trust you", "on edge around you"} else "building_edge"
    )

    segments = [
        _segment(">" if selected else " ", color=marker_color, attrs=marker_attrs),
        _segment(f"{max(1, int(ordinal)):02d} ", color="building_edge", attrs=marker_attrs),
        _segment(name, color=name_color, attrs=marker_attrs),
        _segment(" | ", color="building_edge"),
        _segment(appearance, color=appearance_color),
        _segment(" | ", color="building_edge"),
        _segment(relationship, color=relationship_color),
    ]
    plain = f"{'>' if selected else ' '}{max(1, int(ordinal)):02d} {name} | {appearance} | {relationship}"
    return _rich_line(segments, text=plain)


def _wrap_text_lines(text, width):
    width = max(1, int(width))
    raw = _line_text(text)
    if not raw:
        return [""]

    lines = []
    for paragraph in str(raw).splitlines() or [""]:
        wrapped = textwrap.wrap(
            paragraph,
            width=width,
            break_long_words=True,
            break_on_hyphens=False,
            replace_whitespace=False,
            drop_whitespace=True,
        )
        if not wrapped:
            wrapped = [""]
        lines.extend(wrapped)
    return lines or [""]


def _segments_to_styled_chars(segments):
    chars = []
    for segment in segments or ():
        if isinstance(segment, dict):
            text = str(segment.get("text", ""))
            color = segment.get("color")
            attrs = int(segment.get("attrs", 0) or 0)
            extras = {
                key: value
                for key, value in segment.items()
                if key not in {"text", "color", "attrs"}
            }
        else:
            text = str(segment)
            color = None
            attrs = 0
            extras = {}
        for char in text:
            chars.append((char, color, attrs, dict(extras)))
    return chars


def _styled_chars_to_segments(chars):
    if not chars:
        return []

    grouped = []
    current_text = []
    current_color = None
    current_attrs = 0
    current_extras = {}

    for entry in chars:
        if len(entry) >= 4:
            char, color, attrs, extras = entry
        else:
            char, color, attrs = entry
            extras = {}
        extras = dict(extras or {})
        if current_text and (color != current_color or attrs != current_attrs or extras != current_extras):
            grouped.append(_segment("".join(current_text), color=current_color, attrs=current_attrs, **current_extras))
            current_text = [char]
            current_color = color
            current_attrs = attrs
            current_extras = extras
            continue

        if not current_text:
            current_color = color
            current_attrs = attrs
            current_extras = extras
        current_text.append(char)

    if current_text:
        grouped.append(_segment("".join(current_text), color=current_color, attrs=current_attrs, **current_extras))
    return grouped


def _wrap_segment_lines(segments, width):
    width = max(1, int(width))
    chars = _segments_to_styled_chars(segments)
    if not chars:
        return [[]]

    wrapped = []
    remaining = list(chars)

    while remaining:
        if len(remaining) <= width:
            line_chars = remaining
            remaining = []
        else:
            break_at = None
            for idx in range(width - 1, -1, -1):
                if remaining[idx][0].isspace():
                    break_at = idx
                    break

            if break_at is not None and any(not remaining[i][0].isspace() for i in range(break_at)):
                line_chars = remaining[:break_at]
                remaining = remaining[break_at + 1:]
            else:
                line_chars = remaining[:width]
                remaining = remaining[width:]

        while line_chars and line_chars[-1][0].isspace():
            line_chars.pop()
        while remaining and remaining[0][0].isspace():
            remaining.pop(0)

        wrapped.append(_styled_chars_to_segments(line_chars))

    return wrapped or [[]]


def _wrap_display_lines(line, width, max_lines=None):
    segments = _line_segments(line)
    if segments:
        lines = [_rich_line(wrapped) for wrapped in _wrap_segment_lines(segments, width)]
    else:
        lines = _wrap_text_lines(_line_text(line), width)

    if max_lines is not None:
        lines = lines[: max(0, int(max_lines))]
    return lines or [""]


def _clip_display_line(line, width):
    width = max(0, int(width))
    if width <= 0:
        return ""

    segments = _line_segments(line)
    plain = _line_text(line)
    if not segments:
        if len(plain) <= width:
            return plain
        if width <= 3:
            return plain[:width]
        return plain[: width - 3] + "..."

    if len(plain) <= width:
        return _rich_line(segments, text=plain)

    if width <= 3:
        clipped_chars = _segments_to_styled_chars(segments)[:width]
        clipped_segments = _styled_chars_to_segments(clipped_chars)
        return _rich_line(clipped_segments, text=plain[:width])

    clipped_chars = _segments_to_styled_chars(segments)[: width - 3]
    clipped_segments = _styled_chars_to_segments(clipped_chars)
    clipped_segments.append(_segment("..."))
    return _rich_line(clipped_segments, text=plain[: width - 3] + "...")


def _view_text_wrap_width(view, width):
    width = max(1, int(width))
    helper = getattr(view, "text_wrap_width", None)
    if callable(helper):
        try:
            resolved = int(helper(width))
        except (TypeError, ValueError):
            resolved = width
        return max(1, resolved)
    return width


def _flow_text_chunks(chunks, width, gap="  ", max_lines=None):
    width = max(1, int(width))
    lines = []
    current = ""

    for raw_chunk in chunks or ():
        chunk = str(raw_chunk).strip()
        if not chunk:
            continue

        candidate = chunk if not current else f"{current}{gap}{chunk}"
        if len(candidate) <= width:
            current = candidate
            continue

        if current:
            lines.append(current)
            if max_lines is not None and len(lines) >= max_lines:
                return lines[:max_lines]
            current = ""

        wrapped = _wrap_text_lines(chunk, width)
        if len(wrapped) == 1:
            current = wrapped[0]
            continue

        lines.extend(wrapped[:-1])
        if max_lines is not None and len(lines) >= max_lines:
            return lines[:max_lines]
        current = wrapped[-1]

    if current or not lines:
        lines.append(current)

    if max_lines is not None:
        lines = lines[:max_lines]
    return lines or [""]


def _fit_wrapped_sections(sections, max_rows):
    max_rows = max(1, int(max_rows))
    normalized = []
    total_rows = 0

    for section in sections or ():
        lines = list(section.get("lines", []) or [])
        if not lines:
            continue

        min_lines = max(0, min(int(section.get("min_lines", 0)), len(lines)))
        trim_priority = int(section.get("trim_priority", 0))
        normalized.append({
            "lines": lines,
            "min_lines": min_lines,
            "trim_priority": trim_priority,
        })
        total_rows += len(lines)

    if total_rows <= max_rows:
        return normalized

    while total_rows > max_rows:
        trimmed = False
        for section in sorted(normalized, key=lambda entry: entry["trim_priority"], reverse=True):
            if len(section["lines"]) <= section["min_lines"]:
                continue
            section["lines"].pop()
            total_rows -= 1
            trimmed = True
            if total_rows <= max_rows:
                break
        if not trimmed:
            break

    return normalized


def _mode_line(
    mode_state=None,
    cover=None,
    look_active=False,
    aim_active=False,
    turn_mode=False,
    stealth_state=None,
    intrusion_state=None,
):
    bold = getattr(curses, "A_BOLD", 0)
    segments = [_segment("Modes: ")]

    badges = []
    if mode_state and getattr(mode_state, "sneak", False):
        badges.append(("SNEAK", "scout"))
    if mode_state and getattr(mode_state, "hidden", False):
        badges.append(("HIDDEN", "player"))
    intrusion_state = intrusion_state if isinstance(intrusion_state, dict) else {}
    intrusion_active = bool(intrusion_state.get("active"))
    intrusion_severity = str(intrusion_state.get("severity_label", "clear") or "clear").strip().lower()
    if intrusion_active:
        intrusion_badge = {
            "suspicious": ("SUSPICIOUS", "human"),
            "trespass": ("TRESPASS", "projectile"),
            "serious_trespass": ("HOSTILE", "projectile"),
        }.get(intrusion_severity, ("TRESPASS", "projectile"))
        badges.append(intrusion_badge)
    if cover and getattr(cover, "active", False):
        badges.append(("COVER", "guard"))
    if bool(aim_active):
        badges.append(("AIM", "projectile"))
    elif bool(look_active):
        badges.append(("LOOK", "objective"))
    if bool(turn_mode):
        badges.append(("TURN", "projectile"))

    if not badges:
        segments.append(_segment("-"))
        return _rich_line(segments, text=_segments_text(segments))

    for index, (label, color) in enumerate(badges):
        if index:
            segments.append(_segment(" "))
        segments.append(_segment("["))
        segments.append(_segment(label, color=color, attrs=bold))
        segments.append(_segment("]"))

    if intrusion_active:
        status_text = str(intrusion_state.get("status_text", "") or "").strip().lower()
        if status_text:
            prefix = {
                "suspicious": "suspicious",
                "trespass": "trespass",
                "serious_trespass": "hostile",
            }.get(intrusion_severity, "trespass")
            segments.append(_segment("  "))
            color = "projectile" if str(status_text).startswith("seen:") else "scout"
            segments.append(_segment(f"{prefix}:{status_text}", color=color))
    elif mode_state and getattr(mode_state, "sneak", False):
        stealth_state = stealth_state if isinstance(stealth_state, dict) else {}
        hidden = bool(stealth_state.get("hidden"))
        witness_count = int(stealth_state.get("witness_count", 0))
        witness_labels = list(stealth_state.get("witness_labels", ()))
        segments.append(_segment("  "))
        if hidden:
            segments.append(_segment("unseen", color="scout"))
        elif witness_count > 0:
            if witness_count == 1 and witness_labels:
                summary = f"seen:{witness_labels[0]}"
            elif witness_labels:
                summary = f"seen:{witness_labels[0]}+{witness_count - 1}"
            else:
                summary = f"seen:{witness_count}"
            segments.append(_segment(summary, color="projectile"))
        else:
            segments.append(_segment("searching", color="human"))

    return _rich_line(segments, text=_segments_text(segments))
