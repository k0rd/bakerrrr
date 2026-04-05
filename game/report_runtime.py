from __future__ import annotations

import curses

from game.components import PlayerAssets, PropertyKnowledge, VehicleState
from game.debug_overlay import current_or_nearby_property, organization_summary_rows
from game.final_operation import evaluate_final_operation
from game.objective_progress import (
    objective_progress_explain_delta,
    objective_progress_recent_history,
)
from game.opportunities import (
    evaluate_opportunity_facts,
    objective_focus_lines,
    opportunity_distance_text,
    opportunity_known_count,
    refresh_dynamic_opportunities,
)
from game.property_access import property_access_controller, property_access_level
from game.property_runtime import (
    controller_access_requirement_text,
    property_display_position,
    property_focus_position,
    property_infrastructure_role,
    property_is_public,
    property_is_storefront,
    property_is_vehicle,
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

    fact_lines = [
        "Your owned vehicle." if owned else "Known vehicle.",
    ]
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
