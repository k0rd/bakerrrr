from __future__ import annotations

import curses

from game.components import Inventory, PlayerAssets, Position, PropertyKnowledge, VehicleState
from game.debug_overlay import current_or_nearby_property, organization_summary_rows
from game.final_operation import evaluate_final_operation
from game.objective_progress import (
    objective_progress_explain_delta,
    objective_progress_recent_history,
)
from game.opportunities import (
    evaluate_opportunity_facts,
    objective_focus_lines,
    opportunity_intel_for_observer,
    opportunity_distance_text,
    opportunity_known_count,
    refresh_dynamic_opportunities,
)
from game.property_keys import inventory_matching_property_key, property_lock_state
from game.property_access import property_access_controller, property_access_level
from game.property_runtime import (
    building_id_from_property,
    controller_access_requirement_text,
    property_display_position,
    property_focus_position,
    property_covering,
    property_infrastructure_role,
    property_is_public,
    property_is_storefront,
    property_is_vehicle,
    property_linked_building_id,
    property_linked_property_id,
    property_metadata,
    property_services,
    vehicle_fuel_values,
    vehicle_label,
    vehicle_profile_from_property,
)
from game.run_objectives import evaluate_run_objective
from game.run_pressure import pressure_snapshot


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


def _section_header_line(label, *, color="human"):
    label = str(label or "").strip().upper()
    bold = getattr(curses, "A_BOLD", 0)
    segments = [
        _segment(" "),
        _segment(label, color=color, attrs=bold),
        _segment(" "),
    ]
    return _rich_line(segments, text=f" {label} ")


def _labeled_line(label, value, *, label_color="building_edge", value_color=None):
    label = str(label or "").strip()
    value = str(value or "").strip()
    if not value:
        return ""
    bold = getattr(curses, "A_BOLD", 0)
    segments = [
        _segment(f"{label}: ", color=label_color, attrs=bold),
        _segment(value, color=value_color),
    ]
    return _rich_line(segments, text=f"{label}: {value}")


def _bullet_line(text, *, bullet="-", bullet_color="building_edge", text_color=None):
    text = str(text or "").strip()
    if not text:
        return ""
    bold = getattr(curses, "A_BOLD", 0)
    segments = [
        _segment(f"{str(bullet)[:1]} ", color=bullet_color, attrs=bold),
        _segment(text, color=text_color),
    ]
    return _rich_line(segments, text=f"{str(bullet)[:1]} {text}")


def _badge_line(badge, text, *, badge_color="human", text_color=None):
    text = str(text or "").strip()
    if not text:
        return ""
    badge = str(badge or "").strip().upper()
    bold = getattr(curses, "A_BOLD", 0)
    segments = [
        _segment("[", color="building_edge"),
        _segment(badge, color=badge_color, attrs=bold),
        _segment("] ", color="building_edge"),
        _segment(text, color=text_color),
    ]
    return _rich_line(segments, text=f"[{badge}] {text}")


def _heat_color(snapshot):
    tier = str((snapshot or {}).get("tier", "low")).strip().lower() or "low"
    if tier == "high":
        return "projectile"
    if tier == "medium":
        return "property_asset"
    return "scout"


def _opportunity_risk_color(risk):
    risk = str(risk or "").strip().lower() or "low"
    if risk == "high":
        return "projectile"
    if risk == "medium":
        return "property_asset"
    return "scout"


def _opportunity_report_line(row):
    row = row if isinstance(row, dict) else {}
    title = str(row.get("title", "Opportunity")).strip() or "Opportunity"
    dist_text = opportunity_distance_text(
        int(row.get("distance", 0)),
        str(row.get("direction", "HERE")).strip(),
    )
    risk = str(row.get("risk", "low")).strip().lower() or "low"
    intel_state = str(row.get("awareness_state", "heard")).strip().lower() or "heard"
    intel_percent = int(round(float(row.get("confidence", 0.0)) * 100.0))
    bold = getattr(curses, "A_BOLD", 0)
    segments = [
        _segment("[", color="building_edge"),
        _segment(risk.upper(), color=_opportunity_risk_color(risk), attrs=bold),
        _segment("] ", color="building_edge"),
        _segment(title, color="objective", attrs=bold),
        _segment(" | ", color="building_edge"),
        _segment(dist_text, color="player"),
        _segment(" | ", color="building_edge"),
        _segment(f"intel {intel_state} {intel_percent}%", color="property_service"),
    ]
    return _rich_line(
        segments,
        text=f"[{risk.upper()}] {title} | {dist_text} | intel {intel_state} {intel_percent}%",
    )


def _int_or_default(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _pressure_report_line(snapshot):
    snapshot = snapshot if isinstance(snapshot, dict) else {}
    tier = str(snapshot.get("tier", "low")).strip().lower() or "low"
    attention = max(0, _int_or_default(snapshot.get("attention"), 0))
    if tier == "high":
        return (
            f"Heat {tier} {attention}. Local defenders escalate faster and "
            "services get tighter."
        )
    if tier == "medium":
        return (
            f"Heat {tier} {attention}. Social and trade routes stay tighter "
            "until attention cools."
        )
    return f"Heat {tier} {attention}. Local response is near baseline."


STAKEOUT_REVEAL_INTERVAL = 8
STAKEOUT_MAX_REVEALS = 4
STAKEOUT_CONFIDENCE_CAP = 0.88


def _disguise_role_label(role_id, *, title_case=False):
    role_key = str(role_id or "").strip().lower()
    if not role_key:
        label = "cover"
    elif role_key == "guard":
        label = "guard"
    elif role_key == "worker":
        label = "worker"
    else:
        label = role_key.replace("_", " ")
    return label.title() if title_case else label


def _property_known_record(sim, player_eid, property_id):
    knowledge = sim.ecs.get(PropertyKnowledge).get(player_eid) if sim is not None else None
    if not knowledge:
        return None
    known = getattr(knowledge, "known", {})
    if not isinstance(known, dict):
        return None
    record = known.get(str(property_id or "").strip())
    return record if isinstance(record, dict) else None


def _security_fixture_temporarily_disabled_until(sim, prop):
    if not isinstance(prop, dict):
        return 0
    disabled = getattr(sim, "camera_disabled", {})
    if not isinstance(disabled, dict):
        return 0
    return _int_or_default(disabled.get(prop.get("id"), 0), 0)


def _property_power_cut_until(sim, prop, *, tick=None):
    if not isinstance(prop, dict):
        return 0
    if tick is None:
        tick = _int_or_default(getattr(sim, "tick", 0), 0)
    power_cuts = getattr(sim, "fixture_power_cuts", {})
    if not isinstance(power_cuts, dict):
        return 0

    best_until = 0
    prop_id = str(prop.get("id", "")).strip()
    if prop_id:
        best_until = max(best_until, _int_or_default(power_cuts.get(prop_id), 0))

    cover_index = getattr(sim, "property_cover_index", {})
    if isinstance(cover_index, dict):
        try:
            key = (
                int(prop.get("x", 0)),
                int(prop.get("y", 0)),
                int(prop.get("z", 0)),
            )
        except (TypeError, ValueError):
            key = None
        if key is not None:
            for covered_id in cover_index.get(key, ()):
                best_until = max(best_until, _int_or_default(power_cuts.get(covered_id), 0))

    return best_until if best_until > int(tick) else 0


def _security_fixture_matches_target(sim, prop, *, target_property_id="", target_building_id=""):
    if not isinstance(prop, dict):
        return False
    target_property_id = str(target_property_id or "").strip()
    if not target_property_id:
        return False
    if str(prop.get("id", "")).strip() == target_property_id:
        return True
    if property_linked_property_id(prop) == target_property_id:
        return True
    if target_building_id and property_linked_building_id(prop) == target_building_id:
        return True
    px = _int_or_default(prop.get("x"), 0)
    py = _int_or_default(prop.get("y"), 0)
    pz = _int_or_default(prop.get("z"), 0)
    covered = property_covering(
        sim,
        px,
        py,
        pz,
    )
    if isinstance(covered, dict) and str(covered.get("id", "")).strip() == target_property_id:
        return True
    cover_index = getattr(sim, "property_cover_index", {})
    if not isinstance(cover_index, dict):
        return False
    key = (px, py, pz)
    return target_property_id in {str(pid).strip() for pid in cover_index.get(key, ())}


def _target_security_snapshot(sim, target_prop):
    if not isinstance(target_prop, dict):
        return None
    tick = _int_or_default(getattr(sim, "tick", 0), 0)
    target_property_id = str(target_prop.get("id", "")).strip()
    target_building_id = building_id_from_property(target_prop)
    power_cut_until = _property_power_cut_until(sim, target_prop, tick=tick)

    cameras_total = 0
    cameras_offline = 0
    alarms_total = 0
    alarms_offline = 0
    for prop in getattr(sim, "properties", {}).values():
        role = str(property_infrastructure_role(prop) or "").strip().lower()
        if role not in {"camera_target", "alarm_target"}:
            continue
        if not _security_fixture_matches_target(
            sim,
            prop,
            target_property_id=target_property_id,
            target_building_id=target_building_id,
        ):
            continue
        offline_until = max(
            _security_fixture_temporarily_disabled_until(sim, prop),
            _property_power_cut_until(sim, prop, tick=tick),
        )
        offline = offline_until > tick
        if role == "camera_target":
            cameras_total += 1
            if offline:
                cameras_offline += 1
        else:
            alarms_total += 1
            if offline:
                alarms_offline += 1

    return {
        "power_cut_until": power_cut_until,
        "cameras_total": cameras_total,
        "cameras_offline": cameras_offline,
        "alarms_total": alarms_total,
        "alarms_offline": alarms_offline,
    }


def _global_security_disruption_snapshot(sim):
    tick = _int_or_default(getattr(sim, "tick", 0), 0)
    power_sites = set()
    power_cuts = getattr(sim, "fixture_power_cuts", {})
    if isinstance(power_cuts, dict):
        for prop_id, until in power_cuts.items():
            if _int_or_default(until, 0) <= tick:
                continue
            prop = getattr(sim, "properties", {}).get(prop_id)
            if isinstance(prop, dict) and str(prop.get("kind", "")).strip().lower() == "building":
                power_sites.add(str(prop_id).strip())

    cameras_offline = 0
    alarms_offline = 0
    for prop in getattr(sim, "properties", {}).values():
        role = str(property_infrastructure_role(prop) or "").strip().lower()
        if role not in {"camera_target", "alarm_target"}:
            continue
        offline_until = max(
            _security_fixture_temporarily_disabled_until(sim, prop),
            _property_power_cut_until(sim, prop, tick=tick),
        )
        if offline_until <= tick:
            continue
        if role == "camera_target":
            cameras_offline += 1
        else:
            alarms_offline += 1

    return {
        "power_site_count": len(power_sites),
        "cameras_offline": cameras_offline,
        "alarms_offline": alarms_offline,
    }


def _property_opportunity_prep(sim, player_eid, property_id):
    property_id = str(property_id or "").strip()
    if not property_id:
        return None
    opp_state = getattr(sim, "world_traits", {}).get("opportunities", {})
    active = []
    unknown_count = 0
    least_confidence = 2.0
    for entry in opp_state.get("active", ()):
        if not isinstance(entry, dict):
            continue
        requirements = entry.get("requirements", {}) if isinstance(entry.get("requirements"), dict) else {}
        if str(requirements.get("property_id", "")).strip() != property_id:
            continue
        active.append(entry)
        opportunity_id = _int_or_default(entry.get("id"), 0)
        intel = opportunity_intel_for_observer(sim, player_eid, opportunity_id) if opportunity_id > 0 else None
        if intel is None:
            unknown_count += 1
            least_confidence = min(least_confidence, 0.0)
            continue
        least_confidence = min(
            least_confidence,
            max(0.0, float(intel.get("confidence", 0.0) or 0.0)),
        )

    if not active:
        return None
    if least_confidence > 1.0:
        least_confidence = 0.0

    return {
        "count": len(active),
        "unknown_count": unknown_count,
        "least_confidence": max(0.0, min(1.0, float(least_confidence))),
        "mapped": unknown_count <= 0 and least_confidence >= (STAKEOUT_CONFIDENCE_CAP - 0.01),
    }


def _active_stakeout_snapshot(sim):
    state = getattr(sim, "stakeout_state", None)
    if not isinstance(state, dict):
        return None
    prop_id = str(state.get("prop_id", "")).strip()
    if not prop_id:
        return None
    prop = getattr(sim, "properties", {}).get(prop_id)
    prop_name = str((prop or {}).get("name", prop_id or "target site")).strip() or "target site"
    ticks = max(0, _int_or_default(state.get("ticks"), 0))
    reveals_done = max(0, _int_or_default(state.get("reveals_done"), 0))
    progress_mod = ticks % STAKEOUT_REVEAL_INTERVAL
    next_reveal_in = (
        STAKEOUT_REVEAL_INTERVAL
        if progress_mod == 0
        else (STAKEOUT_REVEAL_INTERVAL - progress_mod)
    )
    return {
        "property_id": prop_id,
        "property_name": prop_name,
        "ticks": ticks,
        "reveals_done": reveals_done,
        "max_reveals": STAKEOUT_MAX_REVEALS,
        "next_reveal_in": max(1, next_reveal_in),
    }


def _prep_report_lines(sim, player_eid, final_operation_eval):
    lines = []
    target_reason = ""
    target_quality = ""
    target_value_bonus = 0
    target_intel_score = 0
    target_entry_label = ""
    target_entry_detail = ""
    disguise = getattr(sim, "disguise_state", None)
    if isinstance(disguise, dict):
        item_name = str(disguise.get("item_name", disguise.get("item_id", "cover"))).strip() or "cover"
        role_text = _disguise_role_label(disguise.get("role_id"), title_case=True)
        strength_pct = int(round(max(0.0, float(disguise.get("strength", 0.0) or 0.0)) * 100.0))
        lines.append(
            f"Cover active: {item_name} ({role_text}, {max(0, strength_pct)}%). Cameras need scrutiny before burning it."
        )

    target_prop = None
    target_property_id = ""
    target_name = ""
    if isinstance(final_operation_eval, dict):
        target_property_id = str(final_operation_eval.get("target_property_id", "")).strip()
        if target_property_id:
            target_prop = getattr(sim, "properties", {}).get(target_property_id)
        target_name = str(final_operation_eval.get("target_property_name", "")).strip()
        target_reason = str(final_operation_eval.get("target_reason", "")).strip()
        target_quality = str(final_operation_eval.get("target_quality_label", "")).strip()
        target_value_bonus = _int_or_default(final_operation_eval.get("target_value_bonus"), 0)
        target_intel_score = _int_or_default(final_operation_eval.get("target_intel_score"), 0)
        target_entry_label = str(final_operation_eval.get("target_entry_label", "")).strip()
        target_entry_detail = str(final_operation_eval.get("target_entry_detail", "")).strip()
    if isinstance(target_prop, dict):
        target_name = str(target_prop.get("name", target_prop.get("id", "target site"))).strip() or "target site"

    active_stakeout = _active_stakeout_snapshot(sim)
    if isinstance(active_stakeout, dict):
        target_prefix = (
            "Target stakeout"
            if str(active_stakeout.get("property_id", "")).strip() == target_property_id
            else "Stakeout"
        )
        lines.append(
            f"{target_prefix}: {active_stakeout['property_name']} "
            f"{active_stakeout['reveals_done']}/{active_stakeout['max_reveals']} reveals logged, "
            f"next pass in {active_stakeout['next_reveal_in']}t."
        )

    target_line_added = False
    if isinstance(target_prop, dict):
        intel = _property_opportunity_prep(sim, player_eid, target_prop.get("id"))
        known = _property_known_record(sim, player_eid, target_prop.get("id"))
        if isinstance(intel, dict):
            thread_label = "thread" if int(intel.get("count", 0)) == 1 else "threads"
            if bool(intel.get("mapped")):
                lines.append(
                    f"Target intel: {target_name} is mapped across {int(intel.get('count', 0))} lead {thread_label}."
                )
            else:
                confidence_pct = int(round(float(intel.get("least_confidence", 0.0) or 0.0) * 100.0))
                lines.append(
                    f"Target intel: {target_name} is only partly mapped "
                    f"({int(intel.get('count', 0))} lead {thread_label}, {max(0, confidence_pct)}% floor). "
                    "More site intel should sharpen the hit."
                )
            target_line_added = True
        elif isinstance(known, dict):
            confidence_pct = int(round(float(known.get("confidence", 0.0) or 0.0) * 100.0))
            lines.append(
                f"Target intel: {target_name} location confidence {max(0, confidence_pct)}%."
            )
            target_line_added = True

        security = _target_security_snapshot(sim, target_prop)
        if isinstance(security, dict):
            power_cut_until = _int_or_default(security.get("power_cut_until"), 0)
            tick = _int_or_default(getattr(sim, "tick", 0), 0)
            if power_cut_until > tick:
                lines.append(
                    f"Security edge: {target_name} is on blackout for {power_cut_until - tick}t. "
                    "Cameras, alarms, and night glow stay down."
                )
                target_line_added = True
            elif int(security.get("cameras_offline", 0)) or int(security.get("alarms_offline", 0)):
                bits = []
                cameras_total = int(security.get("cameras_total", 0))
                alarms_total = int(security.get("alarms_total", 0))
                if cameras_total:
                    bits.append(
                        f"cameras {int(security.get('cameras_offline', 0))}/{cameras_total} dark"
                    )
                if alarms_total:
                    bits.append(
                        f"alarms {int(security.get('alarms_offline', 0))}/{alarms_total} down"
                    )
                if bits:
                    lines.append(f"Security edge: {target_name} has " + " and ".join(bits) + ".")
                    target_line_added = True
            elif (
                int(security.get("cameras_total", 0)) > 0
                or int(security.get("alarms_total", 0)) > 0
            ):
                lines.append(f"Security edge: {target_name} security still reads live.")
                target_line_added = True

        if target_name and target_intel_score > 0:
            reason_text = target_reason or "site lead"
            quality_text = target_quality or "working"
            mark_text = "richer mark" if target_value_bonus >= 2 else "cleaner mark" if target_value_bonus >= 1 else "right mark"
            lines.append(
                f"Final job edge: {quality_text} intel via {reason_text} is steering the hit toward the {mark_text} at {target_name}."
            )
            target_line_added = True

        if target_entry_detail:
            if target_entry_label:
                lines.append(f"Entry plan: {target_entry_label}. {target_entry_detail}")
            else:
                lines.append(f"Entry plan: {target_entry_detail}")
            target_line_added = True

    if not target_line_added and isinstance(final_operation_eval, dict):
        objective_progress = getattr(sim, "world_traits", {}).get("objective_progress", {})
        intel_marks = _int_or_default(objective_progress.get("intel_marks"), 0) if isinstance(objective_progress, dict) else 0
        if intel_marks > 0 and not target_name:
            lines.append(
                f"Intel track: {intel_marks}. Better-known sites should sharpen the retrieval target once you enter the chunk."
            )
        elif target_name:
            lines.append(f"Target prep: {target_name} still needs mapped intel or softened site security.")
        elif not lines:
            lines.append("Prep still thin. No live cover, mapped target intel, or softened site security yet.")

    if not isinstance(target_prop, dict):
        disruption = _global_security_disruption_snapshot(sim)
        if (
            int(disruption.get("power_site_count", 0)) > 0
            or int(disruption.get("cameras_offline", 0)) > 0
            or int(disruption.get("alarms_offline", 0)) > 0
        ):
            bits = []
            if int(disruption.get("power_site_count", 0)) > 0:
                bits.append(f"{int(disruption.get('power_site_count', 0))} site blackout")
            if int(disruption.get("cameras_offline", 0)) > 0:
                bits.append(f"{int(disruption.get('cameras_offline', 0))} camera dark")
            if int(disruption.get("alarms_offline", 0)) > 0:
                bits.append(f"{int(disruption.get('alarms_offline', 0))} alarm down")
            lines.append("Security edge: " + ", ".join(bits) + ".")

    deduped = []
    seen = set()
    for line in lines:
        text = str(line or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped


def build_progress_report(sim, player_eid, opportunity_limit=8):
    refresh_dynamic_opportunities(sim, player_eid)
    objective_eval = evaluate_run_objective(sim, player_eid)
    final_operation_eval = evaluate_final_operation(sim, player_eid)
    capped_opp_limit = max(3, int(opportunity_limit))
    opportunity_rows = evaluate_opportunity_facts(
        sim,
        player_eid,
        limit=capped_opp_limit,
        observer_eid=player_eid,
    )
    opportunity_count = opportunity_known_count(sim, player_eid, observer_eid=player_eid)
    pressure = pressure_snapshot(sim)

    lines = []

    if objective_eval:
        title = str(objective_eval.get("title", "Run Objective")).strip() or "Run Objective"
        summary = str(objective_eval.get("summary", "")).strip()
        status = str(objective_eval.get("summary_line", "")).strip()
        next_step = str(objective_eval.get("next_step", "")).strip()
        why_lines = list(objective_eval.get("why_lines", ()) or ())
        how_lines = list(objective_eval.get("how_lines", ()) or ())
        activity_lines = list(objective_eval.get("activity_lines", ()) or ())
        lines.append(_section_header_line("Objective", color="objective"))
        lines.append(_badge_line("RUN", title, badge_color="objective"))
        if summary:
            lines.append(summary)
        if status:
            lines.append(_labeled_line("Status", status, value_color="human"))
        if next_step:
            lines.append(_labeled_line("Next", next_step, label_color="player", value_color="player"))
        if why_lines:
            lines.append("")
            lines.append(_section_header_line("Why This Run", color="property_service"))
            lines.extend(
                _bullet_line(str(line).strip(), bullet_color="property_service")
                for line in why_lines
                if str(line).strip()
            )
        if how_lines:
            lines.append("")
            lines.append(_section_header_line("How It Advances", color="player"))
            lines.extend(
                _bullet_line(str(line).strip(), bullet_color="player")
                for line in how_lines
                if str(line).strip()
            )
        if activity_lines:
            lines.append("")
            lines.append(_section_header_line("Best Ways To Push It", color="property_asset"))
            lines.extend(
                _bullet_line(str(line).strip(), bullet=">", bullet_color="property_asset")
                for line in activity_lines
                if str(line).strip()
            )

        recent_history = objective_progress_recent_history(sim, limit=4)
        if recent_history:
            recent_lines = []
            for entry in recent_history:
                bits = objective_progress_explain_delta(
                    objective_eval.get("id", ""),
                    entry,
                )
                if not bits:
                    continue
                channel = str(entry.get("channel", "action")).strip().replace("_", " ")
                reason = str(entry.get("reason", "")).strip().replace("_", " ")
                suffix = f" ({reason})" if reason else ""
                recent_lines.append(f"{channel}: {', '.join(bits)}{suffix}.")
            if recent_lines:
                lines.append("")
                lines.append(_section_header_line("Recent Objective Gains", color="property_service"))
                lines.extend(
                    _bullet_line(line, bullet="+", bullet_color="property_service")
                    for line in recent_lines
                )

        focus_lines = objective_focus_lines(sim, player_eid, objective_eval.get("id", ""), limit=3)
        if focus_lines:
            lines.append("")
            lines.append(_section_header_line("Best Current Fits", color="property_asset"))
            lines.extend(
                _bullet_line(str(line).strip(), bullet=">", bullet_color="property_asset")
                for line in focus_lines
                if str(line).strip()
            )

    if final_operation_eval:
        status = str(final_operation_eval.get("summary_line", "")).strip()
        next_step = str(final_operation_eval.get("next_step", "")).strip()
        lines.append("")
        lines.append(_section_header_line("Final Operation", color="projectile"))
        if status:
            lines.append(_badge_line("FIN", status, badge_color="projectile"))
        if next_step:
            lines.append(_labeled_line("Next", next_step, label_color="player", value_color="player"))

    prep_lines = _prep_report_lines(sim, player_eid, final_operation_eval)
    if prep_lines:
        lines.append("")
        lines.append(_section_header_line("Prep", color="scout"))
        lines.extend(
            _bullet_line(line, bullet=">", bullet_color="scout")
            for line in prep_lines
            if str(line).strip()
        )

    lines.append("")
    lines.append(_section_header_line("Pressure", color=_heat_color(pressure)))
    lines.append(_badge_line("Heat", _pressure_report_line(pressure), badge_color=_heat_color(pressure)))

    organization_lines = organization_summary_rows(
        sim,
        current_prop=current_or_nearby_property(sim, player_eid, radius=1),
    )
    lines.append("")
    lines.append(_section_header_line("Organizations", color="guard"))
    if organization_lines:
        lines.extend(
            _bullet_line(str(line).strip(), bullet="-", bullet_color="guard")
            for line in organization_lines
            if str(line).strip()
        )
    else:
        lines.append("No organization heat or standing established yet.")

    remaining = max(0, int(opportunity_count) - len(opportunity_rows))
    if opportunity_rows:
        nearest = opportunity_rows[0]
        nearest_dist_text = opportunity_distance_text(
            int(nearest.get("distance", 0)),
            str(nearest.get("direction", "HERE")).strip(),
        )
        summary = (
            f"Opp {int(opportunity_count)} known | nearest "
            f"{str(nearest.get('title', 'Opportunity')).strip()} "
            f"{nearest_dist_text}"
        )
    else:
        summary = "Opp 0 known"

    opportunity_lines = []
    for row in opportunity_rows:
        dist_text = opportunity_distance_text(
            int(row.get("distance", 0)),
            str(row.get("direction", "HERE")).strip(),
        )
        opportunity_lines.append(_opportunity_report_line(row))
    lines.append("")
    lines.append(_section_header_line("Opportunities", color="property_asset"))
    if summary:
        lines.append(_badge_line("Opp", summary, badge_color="property_asset"))
    if opportunity_lines:
        lines.extend(opportunity_lines)
        if remaining > 0:
            lines.append(f"... and {remaining} more.")
    else:
        lines.append("No active opportunities.")

    return {
        "title": "Operations Report",
        "lines": lines,
    }


def _known_location_coords_text(prop):
    focus = property_focus_position(prop) or property_display_position(prop)
    if focus is None:
        try:
            focus = (
                int(prop.get("x")),
                int(prop.get("y")),
                int(prop.get("z", 0)),
            )
        except (TypeError, ValueError):
            focus = None
    if focus is None:
        return "coords unknown"

    x, y, z = focus
    if int(z) != 0:
        return f"{int(x)},{int(y)},{int(z)}"
    return f"{int(x)},{int(y)}"


def _known_location_summary_bits(prop, known):
    bits = []
    if bool((known or {}).get("anchored")):
        bits.append("confirmed")
    metadata = property_metadata(prop)
    archetype = str(metadata.get("archetype", prop.get("kind", "location"))).strip().replace("_", " ")
    if archetype:
        bits.append(archetype)

    lead_kind = str((known or {}).get("lead_kind", "") or "").strip().lower()
    lead_label = {
        "owner": "owner lead",
        "workplace": "work lead",
        "hours": "hours lead",
        "access": "access lead",
        "security": "security lead",
        "contraband": "contraband lead",
        "service_fuel": "fuel lead",
        "service_repair": "repair lead",
        "service_banking": "banking lead",
        "service_insurance": "insurance lead",
        "service_rest": "lodging lead",
        "service_intel": "intel lead",
        "service_trade": "trade lead",
        "service_used_cars": "used-vehicle lead",
        "service_vehicle_fetch": "vehicle-retrieval lead",
        "service_gaming": "gaming lead",
    }.get(lead_kind, "")
    if lead_label:
        bits.append(lead_label)

    services = [
        str(service).strip().replace("_", " ")
        for service in property_services(prop)
        if str(service).strip()
    ]
    if services:
        bits.append("services " + ", ".join(services[:2]))

    return bits


def _known_location_fact_lines(
    sim,
    player_eid,
    prop,
    known,
    *,
    entity_display_name_fn,
    hours_text_fn,
    security_tier_text_fn,
    human_join_fn,
    infrastructure_target_property_fn,
    infrastructure_role_label_fn,
    storefront_illegal_goods_signal_fn,
):
    facts = []
    known = known if isinstance(known, dict) else {}
    confidence = max(0.0, min(1.0, float(known.get("confidence", 0.0) or 0.0)))
    lead_kind = str(known.get("lead_kind", "") or "").strip().lower()
    source_eid = known.get("source_eid")
    source_name = entity_display_name_fn(sim, source_eid, title_case=True) if source_eid is not None else ""

    controller = property_access_controller(sim, prop)
    access_level = str(property_access_level(prop) or "private").strip().lower() or "private"
    hours_text = hours_text_fn(controller.get("opening_window")) if isinstance(controller, dict) else ""
    requirement = controller_access_requirement_text(controller) if isinstance(controller, dict) else "the matching key"
    security_text = security_tier_text_fn(controller.get("security_tier")) if isinstance(controller, dict) else "security"
    infrastructure_role = property_infrastructure_role(prop)
    kind = str(prop.get("kind", "") or "").strip().lower()
    metadata = property_metadata(prop)
    fixture_label = str(metadata.get("fixture_type", metadata.get("archetype", kind or "property")) or "").strip().replace("_", " ")

    owner_eid = prop.get("owner_eid")
    owner_tag = str(prop.get("owner_tag", "") or "").strip().lower()
    owner_name = entity_display_name_fn(sim, owner_eid, title_case=True) if owner_eid is not None else ""
    if owner_eid == player_eid:
        facts.append("You own this location.")
    elif lead_kind == "owner":
        if owner_name:
            facts.append(f"Owner: {owner_name}.")
        elif owner_tag:
            facts.append(f"Controlled by {owner_tag.replace('_', ' ')}.")

    if lead_kind == "workplace" and source_name:
        facts.append(f"{source_name} works here.")

    if lead_kind == "hours" and hours_text:
        facts.append(f"Public hours: {hours_text}.")

    if lead_kind in {"access", "security"}:
        if access_level == "public" and hours_text:
            facts.append(f"Public during {hours_text}; after hours needs {requirement}.")
        else:
            facts.append(f"Entry runs {access_level}; needs {requirement}.")
        facts.append(f"Security reads as {security_text}.")

    if lead_kind == "contraband":
        signal = storefront_illegal_goods_signal_fn(sim, prop)
        examples = tuple(
            str(label).strip()
            for label in (signal or {}).get("examples", ())
            if str(label).strip()
        )
        if examples:
            facts.append(f"Rumored hot goods: {human_join_fn(examples[:2])}.")
        else:
            facts.append("Rumored to move illegal goods.")

    if confidence >= 0.82 and not any(line.startswith("Owner:") or line.startswith("Controlled by") for line in facts):
        if owner_eid is not None and owner_name:
            facts.append(f"Owner: {owner_name}.")
        elif owner_tag and not property_is_public(prop):
            facts.append(f"Control: {owner_tag.replace('_', ' ')}.")

    if confidence >= 0.8 and not any("Public hours:" in line for line in facts) and hours_text:
        facts.append(f"Public hours: {hours_text}.")

    if confidence >= 0.76 and not any("Security reads as" in line for line in facts):
        if access_level == "public":
            facts.append(f"Access: public-facing, {security_text}.")
        else:
            facts.append(f"Access: {access_level}; {security_text}.")

    if not facts:
        if infrastructure_role:
            target = infrastructure_target_property_fn(sim, prop)
            role_label = infrastructure_role_label_fn(infrastructure_role)
            if isinstance(target, dict):
                target_name = str(target.get("name", target.get("id", "site"))).strip() or "site"
                facts.append(f"Known {role_label} for {target_name}.")
            else:
                facts.append(f"Known {role_label}.")
        elif kind in {"asset", "fixture"}:
            facts.append(f"Known {fixture_label or kind}.")
        elif property_is_storefront(prop):
            facts.append("Known storefront.")
        elif property_is_public(prop):
            facts.append("Known public-facing location.")
        else:
            facts.append(f"Known {access_level} location.")

    deduped = []
    seen = set()
    for line in facts:
        text = str(line).strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped[:4]


def _known_vehicle_report_row(
    sim,
    player_eid,
    prop,
    *,
    known=None,
    hidden=False,
    confidence=None,
    tick=None,
    first_tick=None,
    anchored=None,
    property_legend_line_fn=None,
):
    if not property_is_vehicle(prop):
        return None

    known = known if isinstance(known, dict) else {}
    vehicle_id = str(prop.get("id", "")).strip() or None
    assets = sim.ecs.get(PlayerAssets).get(player_eid)
    owned = bool(
        prop.get("owner_eid") == player_eid
        or str(prop.get("owner_tag", "") or "").strip().lower() == "player"
        or (assets and vehicle_id and vehicle_id in getattr(assets, "owned_property_ids", set()))
    )

    if confidence is None:
        try:
            confidence = float(known.get("confidence", 0.0) or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
    confidence = max(0.0, min(1.0, float(confidence)))

    if anchored is None:
        anchored = bool(known.get("anchored"))

    row_tick = _int_or_default(known.get("tick"), _int_or_default(tick, 0))
    row_first_tick = _int_or_default(known.get("first_tick"), _int_or_default(first_tick, row_tick))

    fuel, fuel_capacity = vehicle_fuel_values(prop)
    profile = vehicle_profile_from_property(prop)
    vehicle_class = str(profile.get("vehicle_class", "") or "").strip().replace("_", " ")
    quality = str(profile.get("quality", "") or "").strip().replace("_", " ")
    vehicle_state = sim.ecs.get(VehicleState).get(player_eid)
    inventory = sim.ecs.get(Inventory).get(player_eid)
    player_pos = sim.ecs.get(Position).get(player_eid)
    vehicle_chunk = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
    player_chunk = sim.chunk_coords(int(player_pos.x), int(player_pos.y)) if player_pos else None
    lock_state = property_lock_state(prop)
    has_key = bool(
        lock_state["key_id"]
        and inventory_matching_property_key(
            inventory,
            property_id=prop.get("id"),
            key_id=lock_state["key_id"],
        ) is not None
    )
    active_vehicle_id = str(getattr(vehicle_state, "active_vehicle_id", "") or "").strip()
    last_vehicle_id = str(getattr(vehicle_state, "last_vehicle_id", "") or "").strip()
    active = bool(vehicle_id and vehicle_id == active_vehicle_id)
    last_driven = bool(vehicle_id and vehicle_id == last_vehicle_id and not active)
    hotwired = bool(property_metadata(prop).get("vehicle_hotwired"))

    fact_lines = [
        (
            "Your active vehicle."
            if active and owned
            else "Your last driven vehicle."
            if last_driven and owned
            else "Your owned vehicle."
            if owned
            else "Known vehicle."
        ),
    ]
    if player_chunk is not None:
        if vehicle_chunk == player_chunk:
            fact_lines.append("In your current chunk.")
        else:
            fact_lines.append(f"Offsite in chunk ({vehicle_chunk[0]}, {vehicle_chunk[1]}).")
    if lock_state["key_id"]:
        if has_key:
            fact_lines.append("Key on hand.")
        elif owned:
            fact_lines.append("No matching key on hand.")
    if hotwired and not lock_state["locked"]:
        fact_lines.append("Hotwired and unlocked.")
    elif lock_state["key_id"]:
        fact_lines.append("Locked." if lock_state["locked"] else "Unlocked.")
    if fuel_capacity > 0 or fuel > 0:
        fact_lines.append(f"Fuel {fuel}/{fuel_capacity}.")
    if vehicle_class and quality:
        fact_lines.append(f"{quality.title()} {vehicle_class}.")
    elif vehicle_class:
        fact_lines.append(f"{vehicle_class.title()}.")
    elif quality:
        fact_lines.append(f"{quality.title()} condition.")

    summary_bits = []
    if anchored or owned or confidence >= 0.95:
        summary_bits.append("confirmed")
    summary_bits.append("owned vehicle" if owned else "vehicle")
    if active and owned:
        summary_bits.append("active")
    elif last_driven and owned:
        summary_bits.append("last driven")
    if player_chunk is not None:
        summary_bits.append("current chunk" if vehicle_chunk == player_chunk else "offsite")
    if quality:
        summary_bits.append(quality)
    if vehicle_class:
        summary_bits.append(vehicle_class)

    return {
        "property_id": vehicle_id or str(prop.get("id", "")),
        "name": vehicle_label(prop),
        "coords": _known_location_coords_text(prop),
        "legend_line": (
            property_legend_line_fn(prop, f"{vehicle_label(prop)} @ {_known_location_coords_text(prop)}")
            if callable(property_legend_line_fn)
            else None
        ),
        "confidence": confidence,
        "tick": row_tick,
        "first_tick": row_first_tick,
        "anchored": bool(anchored or owned),
        "hidden": bool(hidden),
        "summary_bits": summary_bits,
        "fact_lines": fact_lines,
    }


def build_known_locations_report(
    sim,
    player_eid,
    *,
    limit=None,
    include_hidden=False,
    entity_display_name_fn,
    hours_text_fn,
    security_tier_text_fn,
    human_join_fn,
    infrastructure_target_property_fn,
    infrastructure_role_label_fn,
    storefront_illegal_goods_signal_fn,
    property_legend_line_fn=None,
):
    knowledge = sim.ecs.get(PropertyKnowledge).get(player_eid)
    known_map = knowledge.known if knowledge and isinstance(knowledge.known, dict) else {}
    hidden_ids = set()
    if knowledge:
        hidden_ids = {
            str(property_id).strip()
            for property_id in getattr(knowledge, "hidden_property_ids", ()) or ()
            if str(property_id).strip()
        }
    rows = []
    seen_property_ids = set()

    for property_id, known in known_map.items():
        prop = sim.properties.get(property_id)
        if not isinstance(prop, dict):
            continue
        property_id = str(prop.get("id", property_id)).strip() or str(property_id).strip()
        hidden = property_id in hidden_ids
        if include_hidden != hidden:
            continue
        known = known if isinstance(known, dict) else {}
        anchored = bool(known.get("anchored"))
        confidence = max(0.0, min(1.0, float(known.get("confidence", 0.0) or 0.0)))

        if property_is_vehicle(prop):
            vehicle_row = _known_vehicle_report_row(
                sim,
                player_eid,
                prop,
                known=known,
                hidden=hidden,
                confidence=confidence,
                tick=_int_or_default(known.get("tick"), 0),
                first_tick=_int_or_default(known.get("first_tick"), _int_or_default(known.get("tick"), 0)),
                anchored=anchored,
                property_legend_line_fn=property_legend_line_fn,
            )
            if vehicle_row:
                rows.append(vehicle_row)
                seen_property_ids.add(property_id)
            continue

        name = str(prop.get("name", prop.get("id", "location"))).strip() or "location"
        summary_bits = _known_location_summary_bits(prop, known)
        fact_lines = _known_location_fact_lines(
            sim,
            player_eid,
            prop,
            known,
            entity_display_name_fn=entity_display_name_fn,
            hours_text_fn=hours_text_fn,
            security_tier_text_fn=security_tier_text_fn,
            human_join_fn=human_join_fn,
            infrastructure_target_property_fn=infrastructure_target_property_fn,
            infrastructure_role_label_fn=infrastructure_role_label_fn,
            storefront_illegal_goods_signal_fn=storefront_illegal_goods_signal_fn,
        )
        rows.append({
            "property_id": str(prop.get("id", property_id)),
            "name": name,
            "coords": _known_location_coords_text(prop),
            "legend_line": (
                property_legend_line_fn(prop, f"{name} @ {_known_location_coords_text(prop)}")
                if callable(property_legend_line_fn)
                else None
            ),
            "confidence": confidence,
            "tick": _int_or_default(known.get("tick"), 0),
            "first_tick": _int_or_default(known.get("first_tick"), _int_or_default(known.get("tick"), 0)),
            "anchored": anchored,
            "hidden": hidden,
            "summary_bits": summary_bits,
            "fact_lines": fact_lines,
        })
        seen_property_ids.add(property_id)

    vehicle_state = sim.ecs.get(VehicleState).get(player_eid)
    assets = sim.ecs.get(PlayerAssets).get(player_eid)
    candidate_ids = []
    if assets:
        for raw_vehicle_id in sorted(getattr(assets, "owned_property_ids", ()) or ()):
            vehicle_id = str(raw_vehicle_id or "").strip()
            if vehicle_id and vehicle_id not in candidate_ids:
                candidate_ids.append(vehicle_id)
    if vehicle_state:
        for raw_vehicle_id in (
            getattr(vehicle_state, "active_vehicle_id", None),
            getattr(vehicle_state, "last_vehicle_id", None),
        ):
            vehicle_id = str(raw_vehicle_id or "").strip()
            if vehicle_id and vehicle_id not in candidate_ids:
                candidate_ids.append(vehicle_id)

    for vehicle_id in candidate_ids:
        if vehicle_id in seen_property_ids:
            continue
        prop = sim.properties.get(vehicle_id)
        if not property_is_vehicle(prop):
            continue
        hidden = vehicle_id in hidden_ids
        if include_hidden != hidden:
            continue
        owned = bool(
            prop.get("owner_eid") == player_eid
            or str(prop.get("owner_tag", "") or "").strip().lower() == "player"
            or (assets and vehicle_id in assets.owned_property_ids)
        )
        if not owned:
            continue
        vehicle_tick = int(getattr(vehicle_state, "last_changed_tick", getattr(sim, "tick", 0)) or 0)
        vehicle_row = _known_vehicle_report_row(
            sim,
            player_eid,
            prop,
            hidden=hidden,
            confidence=1.0,
            tick=vehicle_tick,
            first_tick=vehicle_tick,
            anchored=True,
            property_legend_line_fn=property_legend_line_fn,
        )
        if vehicle_row:
            rows.append(vehicle_row)
            seen_property_ids.add(vehicle_id)

    rows.sort(
        key=lambda row: (
            -int(row.get("tick", 0)),
            -float(row.get("confidence", 0.0)),
            str(row.get("name", "")).lower(),
            str(row.get("coords", "")).lower(),
            str(row.get("property_id", "")).lower(),
        )
    )

    total_count = len(rows)
    if limit is not None:
        rows = rows[: max(1, int(limit))]

    title = "Hidden Locations" if include_hidden else "Known Locations"
    lines = [
        "Places you have some solid read on through talk, rumor, ownership, or access leads.",
        "",
    ]

    if not rows:
        empty_label = "hidden locations" if include_hidden else "known locations"
        lines.extend([
            f"No {empty_label} right now.",
            "Talk to people, overhear chatter, or learn access details to start filling this notebook." if not include_hidden else "Press H in the notebook to go back to the active list.",
        ])
        return {
            "title": title,
            "lines": lines,
            "rows": [],
        }

    if include_hidden:
        lines.append(f"{total_count} location{'s' if total_count != 1 else ''} hidden.")
    else:
        lines.append(f"{total_count} location{'s' if total_count != 1 else ''} tracked.")
    lines.append("")
    for row in rows:
        legend_line = row.get("legend_line")
        if legend_line:
            lines.append(legend_line)
        else:
            lines.append(f"{row['name']} @ {row['coords']}")
        summary_bits = [f"{int(round(float(row.get('confidence', 0.0)) * 100.0))}% confident"]
        summary_bits.extend(str(bit).strip() for bit in row.get("summary_bits", ()) if str(bit).strip())
        lines.append(" | ".join(summary_bits))
        for fact in row.get("fact_lines", ()):
            lines.append(f"- {fact}")
        lines.append("")

    if total_count > len(rows):
        lines.append(f"... and {total_count - len(rows)} more locations.")

    return {
        "title": title,
        "lines": lines,
        "rows": rows,
    }
