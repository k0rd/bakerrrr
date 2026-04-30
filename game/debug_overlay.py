from __future__ import annotations

import curses

from game.components import FinancialProfile, Inventory, NPCNeeds, PlayerAssets, Position, VehicleState
from game.final_operation import evaluate_final_operation
from game.lighting import lighting_state, update_lighting_state
from game.opportunities import evaluate_opportunity_facts
from game.organization_reputation import organization_snapshot, top_organization_snapshots
from game.property_access import property_access_controller, property_access_level, property_status_text
from game.property_runtime import (
    controller_credential_short_label,
    finance_services_for_property,
    property_covering,
    property_for_action,
    property_is_vehicle,
    property_metadata,
    site_services_for_property,
    vehicle_fuel_values,
    vehicle_label,
    viewer_property_credential_status,
)
from game.run_objectives import evaluate_run_objective
from game.run_pressure import pressure_snapshot
from game.service_runtime import _overworld_discovery_profile, _overworld_travel_profile
from game.skill_ui import skill_debug_lines


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


def _heat_color(tier):
    value = str(tier or "").strip().lower() or "low"
    if value == "high":
        return "projectile"
    if value == "medium":
        return "property_asset"
    return "scout"


def _int_or_default(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _ambient_pct(value, default=1.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    return max(0, min(100, int(round(number * 100.0))))


def current_or_nearby_property(sim, player_eid, radius=1):
    pos = sim.ecs.get(Position).get(player_eid) if sim is not None else None
    if not pos:
        return None
    prop = property_covering(sim, pos.x, pos.y, pos.z)
    if prop is not None:
        return prop
    return property_for_action(sim, pos, radius=radius)


def organization_snapshot_line(snapshot):
    if not isinstance(snapshot, dict):
        return ""
    name = str(snapshot.get("name", "Organization")).strip() or "Organization"
    standing = float(snapshot.get("standing", 0.0))
    standing_tier = str(snapshot.get("standing_tier", "neutral")).strip().lower() or "neutral"
    heat = int(snapshot.get("heat", 0))
    heat_tier = str(snapshot.get("heat_tier", "quiet")).strip().lower() or "quiet"
    site_count = max(0, int(snapshot.get("site_count", 0)))
    return (
        f"{name} | standing {standing_tier} {standing:+.2f} | "
        f"heat {heat_tier} {heat} | sites {site_count}"
    )


def organization_summary_rows(sim, *, current_prop=None):
    rows = []

    current_snapshot = organization_snapshot(sim, prop=current_prop, ensure=True) if current_prop else None
    if current_snapshot is not None:
        rows.append(f"Current: {organization_snapshot_line(current_snapshot)}")

    hot_rows = [
        row for row in top_organization_snapshots(sim, limit=3, sort_by="heat")
        if int(row.get("heat", 0)) > 0
    ]
    if hot_rows:
        rows.append(
            "Heat: "
            + " || ".join(
                f"{str(row.get('name', 'Organization')).strip() or 'Organization'} "
                f"{str(row.get('heat_tier', 'quiet')).strip().lower() or 'quiet'} "
                f"{int(row.get('heat', 0))}"
                for row in hot_rows
            )
        )

    best_rows = top_organization_snapshots(sim, limit=2, sort_by="positive_standing")
    if best_rows:
        rows.append(
            "Best standing: "
            + " || ".join(
                f"{str(row.get('name', 'Organization')).strip() or 'Organization'} "
                f"{str(row.get('standing_tier', 'neutral')).strip().lower() or 'neutral'} "
                f"{float(row.get('standing', 0.0)):+.2f}"
                for row in best_rows
            )
        )

    worst_rows = top_organization_snapshots(sim, limit=2, sort_by="negative_standing")
    if worst_rows:
        rows.append(
            "Worst standing: "
            + " || ".join(
                f"{str(row.get('name', 'Organization')).strip() or 'Organization'} "
                f"{str(row.get('standing_tier', 'neutral')).strip().lower() or 'neutral'} "
                f"{float(row.get('standing', 0.0)):+.2f}"
                for row in worst_rows
            )
        )

    return rows


def build_debug_overlay(
    sim,
    player_eid,
    *,
    duration_label_fn,
    property_access_summary_fn,
):
    positions = sim.ecs.get(Position)
    player_pos = positions.get(player_eid)
    zoom_mode = str(getattr(sim, "zoom_mode", "city")).strip().lower() or "city"
    active_z = int(player_pos.z) if player_pos else 0
    tick = int(getattr(sim, "tick", 0))
    seed = getattr(sim, "seed", "?")

    current_lighting = lighting_state(sim)
    if int(current_lighting.get("tick", -1)) != tick:
        current_lighting = update_lighting_state(sim, player_pos=player_pos)

    visibility_state = getattr(sim, "visibility_state", {})
    player_visible = visibility_state.get("player_visible", set()) if isinstance(visibility_state, dict) else set()
    player_explored = visibility_state.get("player_explored", set()) if isinstance(visibility_state, dict) else set()
    if not isinstance(player_visible, set):
        player_visible = set(player_visible or ())
    if not isinstance(player_explored, set):
        player_explored = set(player_explored or ())
    observers = visibility_state.get("observers", {}) if isinstance(visibility_state, dict) else {}
    if not isinstance(observers, dict):
        observers = {}

    outside_pct = _ambient_pct(current_lighting.get("outside_ambient", 1.0))
    player_pct = _ambient_pct(current_lighting.get("player_ambient", current_lighting.get("outside_ambient", 1.0)))

    world = getattr(sim, "world", None)
    loaded_chunks = getattr(world, "loaded_chunks", {}) if world is not None else {}
    if not isinstance(loaded_chunks, dict):
        loaded_chunks = {}
    chunk_detail = getattr(sim, "chunk_detail", {})
    if not isinstance(chunk_detail, dict):
        chunk_detail = {}
    active_chunk = getattr(sim, "active_chunk", {})
    if not isinstance(active_chunk, dict):
        active_chunk = {}
    district = active_chunk.get("district", {}) if isinstance(active_chunk, dict) else {}
    if not isinstance(district, dict):
        district = {}
    area_type = str(district.get("area_type", "city")).strip().lower() or "city"
    district_type = str(district.get("district_type", "unknown")).strip().lower() or "unknown"
    security = str(district.get("security_level", "?")).strip() or "?"

    pressure = pressure_snapshot(sim)
    pressure_effects = pressure.get("effects", {}) if isinstance(pressure, dict) else {}
    stealth_state = getattr(sim, "player_stealth_state", {})
    if not isinstance(stealth_state, dict):
        stealth_state = {}
    witness_labels = [str(label).strip() for label in stealth_state.get("witness_labels", ()) if str(label).strip()]

    assets = sim.ecs.get(PlayerAssets).get(player_eid)
    finance = sim.ecs.get(FinancialProfile).get(player_eid)
    inventory = sim.ecs.get(Inventory).get(player_eid)
    needs = sim.ecs.get(NPCNeeds).get(player_eid)
    vehicle_state = sim.ecs.get(VehicleState).get(player_eid)
    active_vehicle_prop = None
    if vehicle_state and vehicle_state.active_vehicle_id:
        maybe_vehicle = sim.properties.get(vehicle_state.active_vehicle_id)
        if property_is_vehicle(maybe_vehicle):
            active_vehicle_prop = maybe_vehicle

    objective_eval = evaluate_run_objective(sim, player_eid)
    final_operation_eval = evaluate_final_operation(sim, player_eid)
    opportunity_rows = evaluate_opportunity_facts(
        sim,
        player_eid,
        limit=1,
        observer_eid=player_eid,
    )
    inventory_summary = f"Inventory {inventory.slot_count() if inventory else 0}/{inventory.capacity if inventory else 0}"
    if needs:
        needs_summary = f"{inventory_summary} | Needs E{needs.energy:.0f}/S{needs.safety:.0f}/So{needs.social:.0f}"
    else:
        needs_summary = f"{inventory_summary} | Needs -"

    lines = [
        _section_header_line("Runtime", color="player"),
        (
            f"Tick {tick} | Seed {seed} | Zoom {zoom_mode} | "
            f"Layer {'overworld' if zoom_mode == 'overworld' else active_z}"
        ),
    ]

    if player_pos:
        chunk_x, chunk_y = sim.chunk_coords(player_pos.x, player_pos.y)
        detail = sim.detail_for_xy(player_pos.x, player_pos.y)
        lines.append(
            f"Player tile {player_pos.x},{player_pos.y},{player_pos.z} | "
            f"Chunk {chunk_x},{chunk_y} | Detail {detail}"
        )
    else:
        chunk_x = chunk_y = 0
        lines.append("Player position unavailable.")

    realized_count = len(getattr(sim, "realized_chunks", ()))
    saved_chunk_count = len(getattr(sim, "chunk_saved_states", {}))
    lines.append(
        f"World loaded {len(loaded_chunks)} | Active {sum(1 for detail in chunk_detail.values() if detail == 'active')} | "
        f"Realized {realized_count} | Saved {saved_chunk_count}"
    )
    lines.append(
        f"Entities {len(positions)} | Floor {len(sim.tilemap.entities_on_floor(active_z))} | "
        f"Properties {len(getattr(sim, 'properties', {}))} | Ground {len(getattr(sim, 'ground_items', {}))} | "
        f"Projectiles {len(getattr(sim, 'projectiles', {}))}"
    )

    lines.extend([
        "",
        _section_header_line("Light / Visibility", color="feature_window"),
        (
            f"Time {str(current_lighting.get('time_label', '--:--')).strip() or '--:--'} | "
            f"Phase {str(current_lighting.get('phase', 'day')).strip().lower() or 'day'} | "
            f"Outside {outside_pct}% | Player {'in' if current_lighting.get('player_inside') else 'out'} {player_pct}%"
        ),
        (
            f"Sight radius {int(visibility_state.get('player_radius', 0)) if isinstance(visibility_state, dict) else 0} | "
            f"Visible {len(player_visible)} | Explored {len(player_explored)} | Observers {len(observers)}"
        ),
        (
            f"Stealth hidden {'yes' if stealth_state.get('hidden') else 'no'} | "
            f"Witnesses {int(stealth_state.get('witness_count', 0))} | "
            f"Seen by {', '.join(witness_labels) if witness_labels else '-'}"
        ),
    ])

    lines.extend([
        "",
        _section_header_line("Player / World", color="player"),
        (
            f"District {area_type}/{district_type} | Security {security} | "
            f"Credits {assets.credits if assets else 0} | Bank {finance.bank_balance if finance else 0} | "
            f"Debt {(finance.total_debt() if finance and hasattr(finance, 'total_debt') else getattr(finance, 'debt_balance', 0) if finance else 0)}"
        ),
        needs_summary,
    ])
    for raw in skill_debug_lines(sim, player_eid, duration_label_fn=duration_label_fn):
        text = _line_text(raw).strip()
        if not text:
            lines.append("")
            continue
        if text == "SKILLS":
            lines.append(_section_header_line("Skills", color="property_service"))
            continue
        if text.startswith("Birth tilt "):
            lines.append(_bullet_line(text, bullet="+", bullet_color="player"))
            continue
        lines.append(_bullet_line(text, bullet="-", bullet_color="building_edge"))

    if active_vehicle_prop:
        fuel, fuel_capacity = vehicle_fuel_values(active_vehicle_prop)
        lines.append(_badge_line(
            "Vehicle",
            f"{vehicle_label(active_vehicle_prop)} | Fuel {fuel}/{fuel_capacity} | "
            f"Mode {'driving' if vehicle_state and vehicle_state.in_vehicle else 'parked'}",
            badge_color="vehicle_player",
        ))

    prop = current_or_nearby_property(sim, player_eid, radius=1)
    prop_scope = "Current" if (player_pos and prop is not None and property_covering(sim, player_pos.x, player_pos.y, player_pos.z) is prop) else "Nearby"
    if prop is None:
        prop_scope = "Current"
    lines.extend(["", _section_header_line("Property", color="property_fixture")])
    if prop is not None:
        prop_name = str(prop.get("name", prop.get("id", "property"))).strip() or "property"
        prop_archetype = str(
            property_metadata(prop).get("archetype", prop.get("kind", "property"))
        ).strip().replace("_", " ") or "property"
        access_level = property_access_level(prop)
        access_modes = property_access_summary_fn(sim, prop, viewer_eid=player_eid)
        controller = property_access_controller(sim, prop)
        controller_kind = str(controller.get("kind", "none")).strip().replace("_", " ") or "none"
        open_now = controller.get("open_now")
        open_text = "-"
        if open_now is True:
            open_text = "open"
        elif open_now is False:
            open_text = "closed"
        lines.append(
            f"{prop_scope} property {prop_name} | {prop_archetype} | "
            f"{property_status_text(sim, prop)} | access {access_level}"
        )
        lines.append(
            f"Modes {access_modes or '-'} | Viewer credential {viewer_property_credential_status(sim, player_eid, prop) or '-'} | "
            f"Controller {controller_kind}/{controller_credential_short_label(controller)} "
            f"t{max(1, _int_or_default(controller.get('required_credential_tier'), 1))} "
            f"sec{max(1, _int_or_default(controller.get('security_tier'), 1))} {open_text} "
            f"auth {len(tuple(controller.get('authorized_holders', ()) or ()))}"
        )
        if controller.get("intrusion_active"):
            intrusion_label = str(controller.get("intrusion_label", "") or "intrusion").strip() or "intrusion"
            source_item_id = str(controller.get("intrusion_source_item_id", "") or "").strip().lower()
            source_text = f" via {source_item_id}" if source_item_id else ""
            lines.append(
                f"Intrusion {intrusion_label} | t{int(controller.get('intrusion_until_tick', 0) or 0)} "
                f"({int(controller.get('intrusion_remaining_ticks', 0) or 0)} left){source_text}"
            )
        service_bits = list(finance_services_for_property(prop)) + list(site_services_for_property(prop))
        if service_bits:
            lines.append("Services " + ", ".join(service_bits))
        org_snapshot = organization_snapshot(sim, prop=prop, ensure=True)
        if org_snapshot is not None:
            lines.append("Org " + organization_snapshot_line(org_snapshot))
    else:
        lines.append("No current or adjacent property anchor.")

    if zoom_mode == "overworld" and player_pos and world is not None:
        desc = world.overworld_descriptor(chunk_x, chunk_y)
        interest = world.overworld_interest(chunk_x, chunk_y, descriptor=desc)
        travel = _overworld_travel_profile(sim, chunk_x, chunk_y, desc=desc, interest=interest)
        discovery = _overworld_discovery_profile(sim, chunk_x, chunk_y, desc=desc, interest=interest, travel=travel)
        landmark = desc.get("landmark") or desc.get("nearest_landmark") or {}
        lines.extend([
            "",
            _section_header_line("Overworld", color="objective"),
            (
                f"Region {str(desc.get('region_name', '')).strip() or '-'} | "
                f"Settlement {str(desc.get('settlement_name', '')).strip() or '-'} | "
                f"Terrain {str(desc.get('terrain', '')).strip() or '-'} | "
                f"Path {str(desc.get('path', '')).strip() or '-'}"
            ),
            (
                f"Landmark {str(landmark.get('name', '')).strip() or '-'} | "
                f"POI {str(interest.get('detail', '')).strip() or '-'} | "
                f"Discovery {str(discovery.get('label', '')).strip() or '-'} | "
                f"Risk {str(travel.get('risk_label', 'low')).strip() or 'low'} | "
                f"Support {str(travel.get('support_label', 'none')).strip() or 'none'}"
            ),
        ])

    lines.extend([
        "",
        _section_header_line("Run Loop", color=_heat_color(pressure.get("tier"))),
        _badge_line(
            "Heat",
            f"{str(pressure.get('tier', 'low')).strip().lower() or 'low'} {int(pressure.get('attention', 0))} | "
            f"Peak {int(pressure.get('peak_attention', 0))} | "
            f"Last+ {int(pressure.get('last_raise_tick', -10000))} | "
            f"Last- {int(pressure.get('last_decay_tick', -10000))} | "
            f"Mitigations {int(pressure.get('mitigation_count', 0))}",
            badge_color=_heat_color(pressure.get("tier")),
        ),
        (
            f"Effects suspicion x{float(pressure_effects.get('suspicion_mult', 1.0)):.2f} | "
            f"goodwill x{float(pressure_effects.get('goodwill_mult', 1.0)):.2f} | "
            f"buy x{float(pressure_effects.get('trade_buy_mult', 1.0)):.2f} | "
            f"sell x{float(pressure_effects.get('trade_sell_mult', 1.0)):.2f} | "
            f"insurance x{float(pressure_effects.get('insurance_premium_mult', 1.0)):.2f}"
        ),
    ])

    organization_lines = organization_summary_rows(sim, current_prop=prop)
    lines.extend([
        "",
        _section_header_line("Organizations", color="guard"),
    ])
    if organization_lines:
        lines.extend(
            _bullet_line(line, bullet="-", bullet_color="guard")
            for line in organization_lines
            if str(line).strip()
        )
    else:
        lines.append("No organization heat or standing established yet.")

    lines.extend(["", _section_header_line("Mission", color="objective")])
    if objective_eval:
        lines.append(_badge_line(
            "Objective",
            str(objective_eval.get('title', 'Run Objective')).strip() or 'Run Objective',
            badge_color="objective",
        ))
        objective_status = str(objective_eval.get("summary_line", "")).strip()
        if objective_status:
            lines.append(_bullet_line(f"Status: {objective_status}", bullet="-", bullet_color="objective"))
        objective_next = str(objective_eval.get("next_step", "")).strip()
        if objective_next:
            lines.append(_bullet_line(f"Next: {objective_next}", bullet=">", bullet_color="player"))
    else:
        lines.append("Objective none seeded.")

    if final_operation_eval:
        final_status = str(final_operation_eval.get("summary_line", "")).strip()
        final_next = str(final_operation_eval.get("next_step", "")).strip()
        lines.append(_badge_line("Final", final_status or "ready", badge_color="projectile"))
        if final_next:
            lines.append(_bullet_line(f"Next: {final_next}", bullet=">", bullet_color="player"))
    else:
        lines.append("Final op: locked.")

    if opportunity_rows:
        row = opportunity_rows[0]
        title = str(row.get("title", "Opportunity")).strip() or "Opportunity"
        summary = str(row.get("summary", "")).strip()
        best = list(row.get("best_fits", ()) or ())
        lines.append(_badge_line("Opportunity", title, badge_color="property_asset"))
        if summary:
            lines.append(_bullet_line(summary, bullet="-", bullet_color="property_asset"))
        if best:
            lines.append(
                _bullet_line(
                    "Best fits " + ", ".join(str(bit).strip() for bit in best if str(bit).strip()),
                    bullet=">",
                    bullet_color="property_service",
                )
            )
    else:
        lines.append("Opportunity none visible.")

    return {
        "title": "Debug Overlay",
        "lines": lines,
    }
