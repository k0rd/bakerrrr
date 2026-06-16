"""Shared overworld memory, marker, and readout runtime."""

import curses

from engine.events import Event

from game.components import Position, PropertyKnowledge
from game.opportunities import opportunity_intel_for_observer, opportunity_source_label
from game.property_runtime import (
    property_is_vehicle as _property_is_vehicle,
)
from game.service_runtime import (
    OVERWORLD_AREA_COLORS,
    OVERWORLD_AREA_GLYPHS,
    OVERWORLD_DISTRICT_COLORS,
    OVERWORLD_DISTRICT_GLYPHS,
    OVERWORLD_TERRAIN_COLORS,
    OVERWORLD_TERRAIN_GLYPHS,
    _int_or_default,
    _legend_line,
    _overworld_render_style,
    _overworld_discovery_profile,
    _overworld_discovery_summary_bits,
    _overworld_identity_profile,
    _overworld_travel_tax_text,
    _overworld_travel_profile,
    _overworld_travel_summary_bits,
    _rich_line,
    _segment,
    _segments_text,
)
from game.property_runtime import vehicle_fuel_values as _vehicle_fuel_values
from game.system_support.interaction_ordering import _manhattan


def _chunk_tuple(chunk):
    if not isinstance(chunk, (list, tuple)) or len(chunk) != 2:
        return None
    try:
        return (int(chunk[0]), int(chunk[1]))
    except (TypeError, ValueError):
        return None


def _overworld_fill_semantic_id(area, district, terrain):
    area = str(area or "").strip().lower() or "city"
    district = str(district or "").strip().lower() or "residential"
    terrain = str(terrain or "").strip().lower()
    if area == "city":
        return f"overworld_fill_city_{district}"
    return f"overworld_fill_terrain_{terrain or area or 'wilds'}"


def _overworld_center_semantic_id(cx, cy, area, district, terrain, landmark, interest, loaded_chunks):
    area = str(area or "").strip().lower() or "city"
    district = str(district or "").strip().lower() or "residential"
    terrain = str(terrain or "").strip().lower()
    landmark = landmark if isinstance(landmark, dict) else {}
    interest = interest if isinstance(interest, dict) else {}
    loaded_chunks = loaded_chunks or ()

    if landmark.get("glyph"):
        return "overworld_landmark"
    if interest.get("show_on_map") and interest.get("glyph"):
        return "overworld_interest"
    if area == "city":
        if district:
            return f"overworld_district_{district}"
        return "overworld_area_city"
    if terrain:
        return f"overworld_terrain_{terrain}"
    return f"overworld_area_{area or 'wilds'}"


def _player_overworld_visit_state(sim, eid):
    state_by_eid = getattr(sim, "overworld_visit_state_by_eid", None)
    if not isinstance(state_by_eid, dict):
        state_by_eid = {}
        sim.overworld_visit_state_by_eid = state_by_eid
    visited = state_by_eid.get(eid)
    if isinstance(visited, set):
        return visited
    rebuilt = set()
    if isinstance(visited, (list, tuple)):
        for chunk in visited:
            normalized = _chunk_tuple(chunk)
            if normalized is not None:
                rebuilt.add(normalized)
    state_by_eid[eid] = rebuilt
    return rebuilt


def _overworld_view_only_for(sim, eid):
    records = getattr(sim, "overworld_view_only_by_eid", None)
    if not isinstance(records, dict):
        return False
    try:
        return bool(records.get(int(eid), False))
    except (TypeError, ValueError):
        return False


def _overworld_chunk_memory_state(sim, eid):
    state_by_eid = getattr(sim, "overworld_chunk_memory_by_eid", None)
    if not isinstance(state_by_eid, dict):
        state_by_eid = {}
        sim.overworld_chunk_memory_by_eid = state_by_eid

    memory = state_by_eid.get(eid)
    if isinstance(memory, dict):
        normalized = {}
        mutated = False
        for raw_chunk, payload in list(memory.items()):
            chunk = _chunk_tuple(raw_chunk)
            if chunk is None or not isinstance(payload, dict):
                mutated = True
                continue
            normalized[chunk] = payload
            if chunk != raw_chunk:
                mutated = True
        if mutated:
            state_by_eid[eid] = normalized
            return normalized
        return memory

    rebuilt = {}
    if isinstance(memory, (list, tuple)):
        for entry in memory:
            if not isinstance(entry, dict):
                continue
            chunk = _chunk_tuple(entry.get("chunk"))
            if chunk is None:
                continue
            rebuilt[chunk] = entry
    state_by_eid[eid] = rebuilt
    return rebuilt


def _overworld_render_style_from_snapshot(desc, interest=None, *, loaded=False):
    desc = desc if isinstance(desc, dict) else {}
    interest = interest if isinstance(interest, dict) else {}
    area_type = str(desc.get("area_type", "city")).strip().lower() or "city"
    district_type = str(desc.get("district_type", "unknown")).strip().lower() or "unknown"
    terrain_key = str(desc.get("terrain", "plain")).strip().lower() or "plain"
    landmark_here = desc.get("landmark")

    if isinstance(landmark_here, dict) and landmark_here.get("glyph"):
        glyph = str(landmark_here.get("glyph", "*"))[:1] or "*"
        color = landmark_here.get("color", "human")
    elif interest.get("show_on_map") and interest.get("glyph"):
        glyph = str(interest.get("glyph", "?"))[:1] or "?"
        color = str(interest.get("color", "human") or "human")
    elif area_type == "city":
        glyph = OVERWORLD_DISTRICT_GLYPHS.get(
            district_type,
            OVERWORLD_AREA_GLYPHS.get("city", "X"),
        )
        color = OVERWORLD_DISTRICT_COLORS.get(
            district_type,
            OVERWORLD_AREA_COLORS.get("city", "human"),
        )
    else:
        glyph = OVERWORLD_TERRAIN_GLYPHS.get(
            terrain_key,
            OVERWORLD_AREA_GLYPHS.get(area_type, "?"),
        )
        color = OVERWORLD_TERRAIN_COLORS.get(
            terrain_key,
            OVERWORLD_AREA_COLORS.get(area_type, "human"),
        )

    if str(glyph).isalpha():
        glyph = str(glyph).upper() if bool(loaded) else str(glyph).lower()
    return glyph, color


def _overworld_legend_line_from_snapshot(text, *, desc=None, interest=None, loaded=False):
    glyph, color = _overworld_render_style_from_snapshot(desc, interest, loaded=loaded)
    return _legend_line(text, glyph=glyph, color=color, attrs=getattr(curses, "A_BOLD", 0))


def _remember_overworld_chunk_memory(
    sim,
    eid,
    chunk,
    *,
    desc=None,
    interest=None,
    travel=None,
    discovery=None,
    identity=None,
    source="visit",
):
    chunk_key = _chunk_tuple(chunk)
    if chunk_key is None:
        return None
    cx, cy = chunk_key
    desc = dict(desc) if isinstance(desc, dict) else dict(sim.world.overworld_descriptor(cx, cy) or {})
    interest = dict(interest) if isinstance(interest, dict) else dict(sim.world.overworld_interest(cx, cy, descriptor=desc) or {})
    travel = dict(travel) if isinstance(travel, dict) else dict(_overworld_travel_profile(sim, cx, cy, desc=desc, interest=interest) or {})
    discovery = dict(discovery) if isinstance(discovery, dict) else dict(
        _overworld_discovery_profile(sim, cx, cy, desc=desc, interest=interest, travel=travel) or {}
    )
    identity = dict(identity) if isinstance(identity, dict) else dict(
        _overworld_identity_profile(sim, cx, cy, desc=desc, interest=interest, travel=travel, discovery=discovery) or {}
    )

    snapshot = {
        "chunk": chunk_key,
        "tick": int(getattr(sim, "tick", 0)),
        "source": str(source or "visit").strip().lower() or "visit",
        "desc": desc,
        "interest": interest,
        "travel": travel,
        "discovery": discovery,
        "identity": identity,
    }

    memory = _overworld_chunk_memory_state(sim, eid)
    existing = memory.get(chunk_key)
    if isinstance(existing, dict):
        priority = {
            "lead": 0,
            "marker": 0,
            "property": 0,
            "opportunity": 0,
            "scout": 1,
            "visit": 2,
            "current": 2,
        }
        existing_source = str(existing.get("source", "")).strip().lower()
        if priority.get(existing_source, 0) > priority.get(snapshot["source"], 0):
            snapshot["source"] = existing_source
    memory[chunk_key] = snapshot
    return snapshot


def _overworld_lead_summary(lead, *, limit=2):
    if not isinstance(lead, dict):
        return ""
    notes = [str(note).strip() for note in list(lead.get("notes", ())) if str(note).strip()]
    if not notes:
        return ""
    summary = "; ".join(notes[: max(1, int(limit))])
    remaining = max(0, len(notes) - max(1, int(limit)))
    if remaining > 0:
        summary += f" +{remaining} more"
    return summary


def _overworld_lead_chunks(sim, eid, *, current_chunk=None):
    current_chunk = _chunk_tuple(current_chunk)
    leads = {}

    def _add_lead(chunk, note, *, strength=0):
        chunk_key = _chunk_tuple(chunk)
        if chunk_key is None or chunk_key == current_chunk:
            return
        text = str(note or "").strip()
        if not text:
            return
        entry = leads.get(chunk_key)
        if not isinstance(entry, dict):
            entry = {"chunk": chunk_key, "strength": int(max(0, strength)), "notes": []}
            leads[chunk_key] = entry
        else:
            entry["strength"] = max(int(entry.get("strength", 0)), int(max(0, strength)))
        if text not in entry["notes"]:
            entry["notes"].append(text)

    markers_by_eid = getattr(sim, "overworld_markers_by_eid", None)
    if isinstance(markers_by_eid, dict):
        for marker in markers_by_eid.get(eid, ()):
            if not isinstance(marker, dict):
                continue
            chunk_key = _chunk_tuple(marker.get("chunk"))
            if chunk_key is None:
                continue
            marker_id = _int_or_default(marker.get("id"), 0)
            label = str(marker.get("label", "") or "").strip()
            marker_text = f"Marker M{marker_id}" if marker_id > 0 else "Marker"
            if label:
                marker_text += f" [{label}]"
            _add_lead(chunk_key, marker_text, strength=85)

    knowledge = sim.ecs.get(PropertyKnowledge).get(eid)
    known_map = knowledge.known if knowledge and isinstance(knowledge.known, dict) else {}
    hidden_ids = set()
    if knowledge:
        hidden_ids = {
            str(property_id).strip()
            for property_id in getattr(knowledge, "hidden_property_ids", ()) or ()
            if str(property_id).strip()
        }
    for property_id, known in known_map.items():
        property_id = str(property_id or "").strip()
        if not property_id or property_id in hidden_ids:
            continue
        prop = sim.properties.get(property_id)
        if not isinstance(prop, dict):
            continue
        chunk_key = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
        prop_name = str(prop.get("name", prop.get("id", "location"))).strip() or "location"
        known = known if isinstance(known, dict) else {}
        confidence = max(0.0, min(1.0, float(known.get("confidence", 0.0) or 0.0)))
        anchored = bool(known.get("anchored"))
        if _property_is_vehicle(prop):
            if int(prop.get("owner_eid", 0) or 0) == int(eid or 0) and str(prop.get("owner_tag", "")).strip().lower() == "player":
                note = f"Owned vehicle: {prop_name}"
                strength = 95
            else:
                note = f"Known vehicle: {prop_name}"
                strength = 80 if anchored else (65 if confidence >= 0.75 else 45)
        else:
            note = f"Known location: {prop_name}"
            strength = 80 if anchored else (60 if confidence >= 0.75 else 40)
        _add_lead(chunk_key, note, strength=strength)

    for prop in sim.properties.values():
        if not isinstance(prop, dict):
            continue
        if str(prop.get("kind", "")).strip().lower() != "vehicle":
            continue
        if int(prop.get("owner_eid", 0) or 0) != int(eid or 0):
            continue
        if str(prop.get("owner_tag", "")).strip().lower() != "player":
            continue
        chunk_key = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
        prop_name = str(prop.get("name", prop.get("id", "vehicle"))).strip() or "vehicle"
        _add_lead(chunk_key, f"Owned vehicle: {prop_name}", strength=100)

    traits = getattr(sim, "world_traits", None)
    opportunity_state = traits.get("opportunities") if isinstance(traits, dict) else None
    active = opportunity_state.get("active", ()) if isinstance(opportunity_state, dict) else ()
    for entry in active:
        if not isinstance(entry, dict):
            continue
        opportunity_id = _int_or_default(entry.get("id"), 0)
        if opportunity_id <= 0:
            continue
        intel = opportunity_intel_for_observer(sim, eid, opportunity_id)
        if not isinstance(intel, dict):
            continue
        chunk_key = _chunk_tuple(entry.get("chunk"))
        if chunk_key is None:
            continue
        awareness = str(intel.get("awareness_state", "heard")).strip().lower() or "heard"
        title = str(entry.get("title", entry.get("summary", "lead"))).strip() or "lead"
        source_label = opportunity_source_label(intel.get("source"), short=True)
        note = f"Opportunity: {title}"
        if source_label and source_label != "unknown":
            note += f" ({source_label})"
        _add_lead(chunk_key, note, strength=75 if awareness == "confirmed" else 55)

    return leads


def _overworld_chunk_knowledge(sim, eid, *, current_chunk=None):
    current = _chunk_tuple(current_chunk)
    if current is None and sim is not None and eid is not None:
        pos = sim.ecs.get(Position).get(eid)
        if pos:
            current = _chunk_tuple(sim.chunk_coords(pos.x, pos.y))
    if current is None:
        active = getattr(sim, "active_chunk_coord", None)
        current = _chunk_tuple(active) or (0, 0)

    visited = _player_overworld_visit_state(sim, eid)
    memory = _overworld_chunk_memory_state(sim, eid)
    leads = _overworld_lead_chunks(sim, eid, current_chunk=current)
    known_chunks = set(memory.keys()) | set(visited)
    known_chunks.add(current)
    live_adjacent = set()

    if (
        str(getattr(sim, "zoom_mode", "")).strip().lower() == "overworld"
        and not _overworld_view_only_for(sim, eid)
    ):
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                live_adjacent.add((int(current[0]) + dx, int(current[1]) + dy))

    for chunk_key in tuple(leads.keys()):
        if chunk_key in known_chunks:
            leads.pop(chunk_key, None)

    adjacent = set()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            if dx == 0 and dy == 0:
                continue
            candidate = (int(current[0]) + dx, int(current[1]) + dy)
            if candidate in live_adjacent:
                continue
            if candidate in known_chunks or candidate in leads:
                continue
            adjacent.add(candidate)

    return {
        "current_chunk": current,
        "visited_chunks": visited,
        "memory": memory,
        "live_adjacent_chunks": live_adjacent,
        "lead_chunks": leads,
        "adjacent_chunks": adjacent,
        "known_chunks": known_chunks,
    }


def _overworld_chunk_view(sim, eid, chunk, *, knowledge=None):
    chunk_key = _chunk_tuple(chunk)
    if chunk_key is None:
        return {"awareness": "unknown", "chunk": None}
    if knowledge is None:
        knowledge = _overworld_chunk_knowledge(sim, eid, current_chunk=chunk_key)

    current_chunk = _chunk_tuple(knowledge.get("current_chunk")) or chunk_key
    if chunk_key == current_chunk:
        cx, cy = chunk_key
        desc = dict(sim.world.overworld_descriptor(cx, cy) or {})
        interest = dict(sim.world.overworld_interest(cx, cy, descriptor=desc) or {})
        travel = dict(_overworld_travel_profile(sim, cx, cy, desc=desc, interest=interest) or {})
        discovery = dict(_overworld_discovery_profile(sim, cx, cy, desc=desc, interest=interest, travel=travel) or {})
        identity = dict(_overworld_identity_profile(sim, cx, cy, desc=desc, interest=interest, travel=travel, discovery=discovery) or {})
        snapshot = _remember_overworld_chunk_memory(
            sim,
            eid,
            chunk_key,
            desc=desc,
            interest=interest,
            travel=travel,
            discovery=discovery,
            identity=identity,
            source="current",
        )
        return {
            "awareness": "current",
            "chunk": chunk_key,
            "desc": desc,
            "interest": interest,
            "travel": travel,
            "discovery": discovery,
            "identity": identity,
            "snapshot": snapshot,
        }

    if chunk_key in knowledge.get("live_adjacent_chunks", set()):
        cx, cy = chunk_key
        desc = dict(sim.world.overworld_descriptor(cx, cy) or {})
        interest = dict(sim.world.overworld_interest(cx, cy, descriptor=desc) or {})
        travel = dict(_overworld_travel_profile(sim, cx, cy, desc=desc, interest=interest) or {})
        discovery = dict(_overworld_discovery_profile(sim, cx, cy, desc=desc, interest=interest, travel=travel) or {})
        identity = dict(_overworld_identity_profile(sim, cx, cy, desc=desc, interest=interest, travel=travel, discovery=discovery) or {})
        snapshot = _remember_overworld_chunk_memory(
            sim,
            eid,
            chunk_key,
            desc=desc,
            interest=interest,
            travel=travel,
            discovery=discovery,
            identity=identity,
            source="scout",
        )
        return {
            "awareness": "adjacent_live",
            "chunk": chunk_key,
            "desc": desc,
            "interest": interest,
            "travel": travel,
            "discovery": discovery,
            "identity": identity,
            "snapshot": snapshot,
        }

    memory = knowledge.get("memory", {}).get(chunk_key)
    if memory is None and chunk_key in knowledge.get("visited_chunks", set()):
        memory = _remember_overworld_chunk_memory(sim, eid, chunk_key, source="visit")
        knowledge.get("memory", {})[chunk_key] = memory
    if isinstance(memory, dict):
        desc = memory.get("desc") if isinstance(memory.get("desc"), dict) else {}
        interest = memory.get("interest") if isinstance(memory.get("interest"), dict) else {}
        travel = memory.get("travel") if isinstance(memory.get("travel"), dict) else {}
        discovery = memory.get("discovery") if isinstance(memory.get("discovery"), dict) else {}
        identity = memory.get("identity") if isinstance(memory.get("identity"), dict) else {}
        return {
            "awareness": "memory",
            "chunk": chunk_key,
            "desc": desc,
            "interest": interest,
            "travel": travel,
            "discovery": discovery,
            "identity": identity,
            "snapshot": memory,
        }

    lead = knowledge.get("lead_chunks", {}).get(chunk_key)
    if isinstance(lead, dict):
        return {
            "awareness": "lead",
            "chunk": chunk_key,
            "lead": lead,
        }

    if chunk_key in knowledge.get("adjacent_chunks", set()):
        return {
            "awareness": "adjacent",
            "chunk": chunk_key,
        }

    return {
        "awareness": "unknown",
        "chunk": chunk_key,
    }


def _overworld_hud_lines(
    sim,
    cx,
    cy,
    *,
    desc,
    interest,
    travel,
    discovery,
    identity=None,
    markers=(),
    active_vehicle_prop=None,
):
    desc = desc if isinstance(desc, dict) else {}
    interest = interest if isinstance(interest, dict) else {}
    travel = travel if isinstance(travel, dict) else {}
    discovery = discovery if isinstance(discovery, dict) else {}
    identity = identity if isinstance(identity, dict) else {}
    markers = list(markers or ())

    bold = getattr(curses, "A_BOLD", 0)
    area = str(desc.get("area_type", "city")).strip().lower() or "city"
    district = str(desc.get("district_type", "residential")).strip().lower() or "residential"
    terrain = str(desc.get("terrain", "")).strip().lower()
    path = str(desc.get("path", "")).strip().lower() or "-"
    region_name = str(desc.get("region_name", "")).strip()
    settlement_name = str(desc.get("settlement_name", "")).strip()
    landmark = desc.get("landmark") or desc.get("nearest_landmark") or {}
    landmark_name = str((landmark or {}).get("name", "")).strip()
    interest_name = str(interest.get("detail", "")).strip()
    discovery_name = str(discovery.get("label", "")).strip()
    identity_name = str(identity.get("label", "")).strip()
    identity_hook = str(identity.get("hook", "")).strip()
    risk_name = str(travel.get("risk_label", "low")).strip() or "low"
    support_name = str(travel.get("support_label", "none")).strip() or "none"
    travel_tax = _overworld_travel_tax_text(travel)

    glyph, color = _overworld_render_style(sim, int(cx), int(cy))
    semantic_id = _overworld_center_semantic_id(
        int(cx),
        int(cy),
        area,
        district,
        terrain,
        landmark,
        interest,
        getattr(sim.world, "loaded_chunks", {}),
    )

    def _title(raw):
        text = str(raw or "").replace("_", " ").strip()
        return text.title() if text else ""

    nearest_marker_dist = None
    if markers:
        try:
            nearest_marker_dist = min(
                _manhattan(int(cx), int(cy), int(marker["chunk"][0]), int(marker["chunk"][1]))
                for marker in markers
            )
        except (KeyError, TypeError, ValueError, IndexError):
            nearest_marker_dist = None

    line_one = [
        _segment(glyph, color=color, attrs=bold, inline_glyph=True, semantic_id=semantic_id),
        _segment(" "),
        _segment(f"Chunk {int(cx)},{int(cy)}", color="player", attrs=bold),
        _segment("  "),
        _segment("Area ", color="human", attrs=bold),
        _segment(_title(area)),
    ]
    if area == "city":
        line_one.extend([
            _segment("  "),
            _segment("District ", color="human", attrs=bold),
            _segment(_title(district)),
        ])
    elif terrain:
        line_one.extend([
            _segment("  "),
            _segment("Terrain ", color="human", attrs=bold),
            _segment(_title(terrain)),
        ])
    if region_name:
        line_one.extend([
            _segment("  "),
            _segment("Region ", color="human", attrs=bold),
            _segment(region_name),
        ])
    if settlement_name:
        line_one.extend([
            _segment("  "),
            _segment("City ", color="human", attrs=bold),
            _segment(settlement_name),
        ])

    line_two = []

    def _append_pair(label, value, *, value_color=None):
        if not value:
            return
        if line_two:
            line_two.append(_segment("  "))
        line_two.append(_segment(f"{label} ", color="human", attrs=bold))
        line_two.append(_segment(str(value), color=value_color))

    _append_pair("Path", _title(path) if path != "-" else "-")
    _append_pair("Identity", _title(identity_name))
    _append_pair("Risk", _title(risk_name))
    _append_pair("Support", _title(support_name))
    _append_pair("Travel", travel_tax, value_color="player")
    if markers:
        near_text = f"{len(markers)} near {nearest_marker_dist if nearest_marker_dist is not None else '?'}c"
    else:
        near_text = "0"
    _append_pair("Markers", near_text, value_color="player" if markers else None)
    if active_vehicle_prop:
        fuel, fuel_capacity = _vehicle_fuel_values(active_vehicle_prop)
        _append_pair("Fuel", f"{fuel}/{fuel_capacity}")

    line_three = []
    facts = []
    if landmark_name:
        facts.append(("Landmark", landmark_name))
    if interest_name:
        facts.append(("POI", interest_name))
    if discovery_name:
        facts.append(("Opportunity", discovery_name))
    for idx, (label, value) in enumerate(facts):
        if idx > 0:
            line_three.append(_segment("  "))
        line_three.append(_segment(f"{label} ", color="human", attrs=bold))
        line_three.append(_segment(value))

    lines = [_rich_line(line_one)]
    if line_two:
        lines.append(_rich_line(line_two))
    if line_three:
        lines.append(_rich_line(line_three))
    if identity_hook:
        lines.append(_rich_line([
            _segment("Read ", color="human", attrs=bold),
            _segment(identity_hook, color="player"),
        ], text=f"Read {identity_hook}"))
    return lines


def _overworld_edge_legend_lines(
    sim,
    current_chunk,
    *,
    desc,
    interest,
    markers=(),
    look_ui=None,
):
    desc = desc if isinstance(desc, dict) else {}
    interest = interest if isinstance(interest, dict) else {}
    look_ui = look_ui if isinstance(look_ui, dict) else {}
    markers = list(markers or ())
    bold = getattr(curses, "A_BOLD", 0)

    cx = int(current_chunk[0])
    cy = int(current_chunk[1])
    area = str(desc.get("area_type", "city")).strip().lower() or "city"
    district = str(desc.get("district_type", "residential")).strip().lower() or "residential"
    terrain = str(desc.get("terrain", "")).strip().lower()
    region_name = str(desc.get("region_name", "")).strip()
    settlement_name = str(desc.get("settlement_name", "")).strip()
    glyph, color = _overworld_render_style(sim, cx, cy)
    semantic_id = _overworld_center_semantic_id(
        cx,
        cy,
        area,
        district,
        terrain,
        desc.get("landmark"),
        interest,
        getattr(sim.world, "loaded_chunks", {}),
    )

    def _title(raw):
        text = str(raw or "").replace("_", " ").strip()
        return text.title() if text else ""

    header_segments = [
        _segment(" "),
        _segment(glyph, color=color, attrs=bold, inline_glyph=True, semantic_id=semantic_id),
        _segment(" "),
        _segment("Overworld", color="player", attrs=bold),
        _segment("  "),
        _segment(f"Here {cx},{cy}", color="human", attrs=bold),
    ]
    place_label = _title(district if area == "city" else terrain or area)
    if place_label:
        header_segments.extend([
            _segment("  "),
            _segment(place_label),
        ])
    if region_name:
        header_segments.extend([
            _segment("  "),
            _segment(region_name),
        ])
    if settlement_name:
        header_segments.extend([
            _segment("  "),
            _segment(settlement_name),
        ])
    if bool(look_ui.get("active")) and str(look_ui.get("mode", "")).lower() == "overworld":
        cursor_cx = int(look_ui.get("chunk_x", cx))
        cursor_cy = int(look_ui.get("chunk_y", cy))
        if (cursor_cx, cursor_cy) != (cx, cy):
            header_segments.extend([
                _segment("  "),
                _segment(f"Cursor {cursor_cx},{cursor_cy}", color="player", attrs=bold),
            ])
    header_segments.append(_segment(" "))

    player_eid = getattr(sim, "player_eid", None)
    view_only = False
    records = getattr(sim, "overworld_view_only_by_eid", None)
    if isinstance(records, dict) and player_eid is not None:
        try:
            view_only = bool(records.get(int(player_eid), False))
        except (TypeError, ValueError):
            view_only = False

    footer_segments = [
        _segment("Map: " if view_only else "Quick travel: ", color="human", attrs=bold),
        _segment("!", color="player", attrs=bold, inline_glyph=True, semantic_id="overworld_marker_nearest"),
        _segment(" nearest  "),
        _segment("4", color="human", inline_glyph=True, semantic_id="overworld_marker"),
        _segment(f" markers:{len(markers)}  "),
        _segment("bright=loaded dim=distant  "),
        _segment("move browse  X look  Enter inspect  M mark  l list  N nearest  t exit" if view_only else "8-way travel  G drive marker  M mark  l list  N nearest  t local"),
    ]

    return (
        _rich_line(header_segments, text=_segments_text(header_segments)),
        _rich_line(footer_segments, text=_segments_text(footer_segments)),
    )


class PlayerOverworldRuntime:
    def __init__(self, action_system):
        self.action_system = action_system
        self.sim = action_system.sim

    def _overworld_markers_for(self, eid):
        markers_by_eid = getattr(self.sim, "overworld_markers_by_eid", None)
        if not isinstance(markers_by_eid, dict):
            markers_by_eid = {}
            self.sim.overworld_markers_by_eid = markers_by_eid

        markers = markers_by_eid.get(eid)
        if not isinstance(markers, list):
            markers = []
            markers_by_eid[eid] = markers
        return markers

    def _next_overworld_marker_id(self, eid):
        counters = getattr(self.sim, "next_overworld_marker_id_by_eid", None)
        if not isinstance(counters, dict):
            counters = {}
            self.sim.next_overworld_marker_id_by_eid = counters

        next_id = int(counters.get(eid, 1))
        if next_id < 1:
            next_id = 1
        counters[eid] = next_id + 1
        return next_id

    def _marker_descriptor(self, chunk):
        cx, cy = chunk
        desc = self.sim.world.overworld_descriptor(cx, cy)
        interest = self.sim.world.overworld_interest(cx, cy, descriptor=desc)
        travel = _overworld_travel_profile(self.sim, cx, cy, desc=desc, interest=interest)
        discovery = _overworld_discovery_profile(self.sim, cx, cy, desc=desc, interest=interest, travel=travel)
        identity = _overworld_identity_profile(
            self.sim,
            cx,
            cy,
            desc=desc,
            interest=interest,
            travel=travel,
            discovery=discovery,
        )
        area_type = str(desc.get("area_type", "city"))
        district_type = str(desc.get("district_type", "unknown"))
        terrain = str(desc.get("terrain", "plain")).replace("_", " ").strip()
        path = str(desc.get("path", "")).strip()
        region_name = str(desc.get("region_name", "")).strip()
        settlement_name = str(desc.get("settlement_name", "")).strip()
        landmark = desc.get("landmark") or desc.get("nearest_landmark") or {}
        landmark_name = str(landmark.get("name", "")).strip()
        return (
            area_type,
            district_type,
            terrain,
            path,
            landmark_name,
            region_name,
            settlement_name,
            str(interest.get("detail", "")).strip(),
            travel,
            discovery,
            str(identity.get("label", "")).strip(),
            str(identity.get("hook", "")).strip(),
        )

    def _chunk_direction(self, from_chunk, to_chunk):
        dx = int(to_chunk[0]) - int(from_chunk[0])
        dy = int(to_chunk[1]) - int(from_chunk[1])
        parts = []
        if dy < 0:
            parts.append("N")
        elif dy > 0:
            parts.append("S")
        if dx > 0:
            parts.append("E")
        elif dx < 0:
            parts.append("W")
        return "".join(parts) if parts else "HERE"

    def _overworld_chunk_inspect_line(self, eid, origin_chunk, chunk, *, label=None, knowledge=None):
        chunk_key = _chunk_tuple(chunk) or (0, 0)
        cx = int(chunk_key[0])
        cy = int(chunk_key[1])
        origin_chunk = _chunk_tuple(origin_chunk) or chunk_key
        knowledge = knowledge if isinstance(knowledge, dict) else _overworld_chunk_knowledge(
            self.sim,
            eid,
            current_chunk=origin_chunk,
        )
        view = _overworld_chunk_view(self.sim, eid, chunk_key, knowledge=knowledge)
        awareness = str(view.get("awareness", "unknown")).strip().lower() or "unknown"
        dist = _manhattan(origin_chunk[0], origin_chunk[1], cx, cy)
        direction = self._chunk_direction(origin_chunk, chunk_key)
        prefix = f"{str(label).strip()} " if str(label).strip() else ""

        marker_id = None
        for marker in self._overworld_markers_for(eid):
            marker_chunk = _chunk_tuple(marker.get("chunk"))
            if marker_chunk != chunk_key:
                continue
            marker_id = _int_or_default(marker.get("id"), 0)
            break

        if awareness in {"current", "memory", "adjacent_live"}:
            desc = view.get("desc") if isinstance(view.get("desc"), dict) else {}
            interest = view.get("interest") if isinstance(view.get("interest"), dict) else {}
            travel = view.get("travel") if isinstance(view.get("travel"), dict) else {}
            discovery = view.get("discovery") if isinstance(view.get("discovery"), dict) else {}
            identity = view.get("identity") if isinstance(view.get("identity"), dict) else {}
            area_type = str(desc.get("area_type", "city"))
            district_type = str(desc.get("district_type", "unknown"))
            terrain_key = str(desc.get("terrain", "plain")).strip().lower()
            terrain = terrain_key.replace("_", " ").strip()
            path = str(desc.get("path", "")).strip()
            region_name = str(desc.get("region_name", "")).strip()
            settlement_name = str(desc.get("settlement_name", "")).strip()
            landmark = desc.get("landmark") or desc.get("nearest_landmark") or {}
            landmark_name = str(landmark.get("name", "")).strip()
            identity_label = str(identity.get("label", "")).strip()
            identity_hook = str(identity.get("hook", "")).strip()
            interest_detail = str(interest.get("detail", "")).strip()

            bits = [
                f"{prefix}({cx},{cy}) {dist}c {direction}",
                f"{area_type}/{district_type}",
                f"terr:{terrain}",
            ]
            if path:
                bits.append(f"path:{path}")
            if landmark_name:
                bits.append(f"landmark:{landmark_name}")
            if region_name:
                bits.append(f"region:{region_name}")
            if settlement_name:
                bits.append(f"city:{settlement_name}")
            if identity_label:
                bits.append(f"id:{identity_label}")
            if interest_detail:
                bits.append(f"poi:{interest_detail}")
            bits.extend(_overworld_travel_summary_bits(travel))
            bits.extend(_overworld_discovery_summary_bits(discovery))
            if awareness == "memory":
                bits.append("memory")
            if identity_hook:
                bits.append(f"read:{identity_hook}")
            if marker_id:
                bits.append(f"marker:M{marker_id}")
            return _overworld_legend_line_from_snapshot(
                " ".join(bits),
                desc=desc,
                interest=interest,
                loaded=awareness in {"current", "adjacent_live"},
            )

        if awareness == "lead":
            summary = _overworld_lead_summary(view.get("lead"))
            bits = [f"{prefix}({cx},{cy}) {dist}c {direction}", "lead"]
            if summary:
                bits.append(summary)
            if marker_id:
                bits.append(f"marker:M{marker_id}")
            return _legend_line(" ".join(bits), glyph="?", color="player", attrs=getattr(curses, "A_BOLD", 0))

        if awareness == "adjacent":
            bits = [f"{prefix}({cx},{cy}) {dist}c {direction}", "adjacent unknown"]
            if marker_id:
                bits.append(f"marker:M{marker_id}")
            return _legend_line(" ".join(bits), glyph="?", color="human")

        bits = [f"{prefix}({cx},{cy}) {dist}c {direction}", "unknown"]
        if marker_id:
            bits.append(f"marker:M{marker_id}")
        return _legend_line(" ".join(bits), glyph="?", color="human")

    def _marker_line(self, eid, marker, origin_chunk, *, knowledge=None):
        marker_id = int(marker.get("id", 0))
        chunk = marker.get("chunk", (0, 0))
        cx = int(chunk[0])
        cy = int(chunk[1])
        label = str(marker.get("label", "") or "").strip()
        dist = _manhattan(origin_chunk[0], origin_chunk[1], cx, cy)
        direction = self._chunk_direction(origin_chunk, (cx, cy))
        label_text = f" [{label}]" if label else ""
        knowledge = knowledge if isinstance(knowledge, dict) else _overworld_chunk_knowledge(
            self.sim,
            eid,
            current_chunk=origin_chunk,
        )
        view = _overworld_chunk_view(self.sim, eid, (cx, cy), knowledge=knowledge)
        awareness = str(view.get("awareness", "unknown")).strip().lower() or "unknown"

        if awareness in {"current", "memory", "adjacent_live"}:
            desc = view.get("desc") if isinstance(view.get("desc"), dict) else {}
            interest = view.get("interest") if isinstance(view.get("interest"), dict) else {}
            travel = view.get("travel") if isinstance(view.get("travel"), dict) else {}
            discovery = view.get("discovery") if isinstance(view.get("discovery"), dict) else {}
            identity = view.get("identity") if isinstance(view.get("identity"), dict) else {}
            area_type = str(desc.get("area_type", "city"))
            district_type = str(desc.get("district_type", "unknown"))
            terrain = str(desc.get("terrain", "plain")).replace("_", " ").strip()
            path = str(desc.get("path", "")).strip()
            landmark = desc.get("landmark") or desc.get("nearest_landmark") or {}
            landmark_name = str(landmark.get("name", "")).strip()
            region_name = str(desc.get("region_name", "")).strip()
            settlement_name = str(desc.get("settlement_name", "")).strip()
            interest_detail = str(interest.get("detail", "")).strip()
            identity_label = str(identity.get("label", "")).strip()
            identity_hook = str(identity.get("hook", "")).strip()
            path_text = f" path:{path}" if path else ""
            landmark_text = f" landmark:{landmark_name}" if landmark_name else ""
            region_text = f" region:{region_name}" if region_name else ""
            settlement_text = f" city:{settlement_name}" if settlement_name else ""
            interest_text = f" poi:{interest_detail}" if interest_detail else ""
            identity_text = f" id:{identity_label}" if identity_label else ""
            hook_text = f" read:{identity_hook}" if identity_hook else ""
            summary_bits = list(_overworld_travel_summary_bits(travel)) + list(_overworld_discovery_summary_bits(discovery))
            travel_text = f" {' '.join(summary_bits)}" if summary_bits else ""
            memory_text = " memory" if awareness == "memory" else ""
            return (
                dist,
                marker_id,
                f"M{marker_id}{label_text} ({cx},{cy}) {dist}c {direction} "
                f"{area_type}/{district_type} terr:{terrain}"
                f"{path_text}{landmark_text}{identity_text}{interest_text}{region_text}{settlement_text}{travel_text}{hook_text}{memory_text}",
            )

        if awareness == "lead":
            summary = _overworld_lead_summary(view.get("lead")) or "known lead"
            return (
                dist,
                marker_id,
                f"M{marker_id}{label_text} ({cx},{cy}) {dist}c {direction} lead:{summary}",
            )

        if awareness == "adjacent":
            return (
                dist,
                marker_id,
                f"M{marker_id}{label_text} ({cx},{cy}) {dist}c {direction} adjacent unknown",
            )

        return (
            dist,
            marker_id,
            f"M{marker_id}{label_text} ({cx},{cy}) {dist}c {direction} unknown",
        )

    def _set_overworld_marker(self, eid, chunk, *, label="", property_id=None):
        try:
            target_chunk = (int(chunk[0]), int(chunk[1]))
        except (TypeError, ValueError, IndexError):
            return False

        markers = self._overworld_markers_for(eid)
        marker_label = str(label or "").strip()
        property_id = str(property_id or "").strip() or None

        existing = None
        old_chunk = None
        if property_id:
            for marker in markers:
                if str(marker.get("property_id", "") or "").strip() != property_id:
                    continue
                chunk_value = marker.get("chunk")
                if isinstance(chunk_value, (list, tuple)) and len(chunk_value) == 2:
                    old_chunk = (int(chunk_value[0]), int(chunk_value[1]))
                existing = marker
                break

        if existing is None:
            for marker in markers:
                chunk_value = marker.get("chunk")
                if not isinstance(chunk_value, (list, tuple)) or len(chunk_value) != 2:
                    continue
                marker_chunk = (int(chunk_value[0]), int(chunk_value[1]))
                if marker_chunk != target_chunk:
                    continue
                existing = marker
                old_chunk = marker_chunk
                break

        (
            area_type,
            district_type,
            terrain,
            path,
            landmark,
            region_name,
            settlement_name,
            interest_detail,
            travel,
            discovery,
            identity_label,
            identity_hook,
        ) = self._marker_descriptor(target_chunk)
        if existing is not None:
            existing["chunk"] = target_chunk
            existing["updated_tick"] = self.sim.tick
            if marker_label:
                existing["label"] = marker_label
            if property_id:
                existing["property_id"] = property_id
            elif marker_label and not str(existing.get("property_id", "") or "").strip():
                existing["property_id"] = None

            self.sim.emit(Event(
                "overworld_marker_updated",
                eid=eid,
                marker_id=int(existing.get("id", 0)),
                chunk=target_chunk,
                old_chunk=old_chunk,
                retargeted=bool(old_chunk and tuple(old_chunk) != tuple(target_chunk)),
                marker_label=marker_label or str(existing.get("label", "") or "").strip(),
                property_id=property_id,
                area_type=area_type,
                district_type=district_type,
                terrain=terrain,
                path=path,
                landmark=landmark,
                region_name=region_name,
                settlement_name=settlement_name,
                interest=interest_detail,
                identity=identity_label,
                identity_hook=identity_hook,
                risk=travel.get("risk_label"),
                support=travel.get("support_label"),
                energy_cost=int(travel.get("energy_cost", 0)),
                safety_cost=int(travel.get("safety_cost", 0)),
                social_cost=int(travel.get("social_cost", 0)),
                discovery=str(discovery.get("label", "")).strip(),
                total=len(markers),
            ))
            return True

        marker_id = self._next_overworld_marker_id(eid)
        markers.append({
            "id": marker_id,
            "chunk": target_chunk,
            "label": marker_label or None,
            "property_id": property_id,
            "created_tick": self.sim.tick,
            "updated_tick": self.sim.tick,
        })
        self.sim.emit(Event(
            "overworld_marker_added",
            eid=eid,
            marker_id=marker_id,
            chunk=target_chunk,
            marker_label=marker_label,
            property_id=property_id,
            area_type=area_type,
            district_type=district_type,
            terrain=terrain,
            path=path,
            landmark=landmark,
            region_name=region_name,
            settlement_name=settlement_name,
            interest=interest_detail,
            identity=identity_label,
            identity_hook=identity_hook,
            risk=travel.get("risk_label"),
            support=travel.get("support_label"),
            energy_cost=int(travel.get("energy_cost", 0)),
            safety_cost=int(travel.get("safety_cost", 0)),
            social_cost=int(travel.get("social_cost", 0)),
            discovery=str(discovery.get("label", "")).strip(),
            total=len(markers),
        ))
        return True

    def _handle_overworld_marker_add(self, eid, pos):
        current_chunk = self.sim.chunk_coords(pos.x, pos.y)
        self._set_overworld_marker(eid=eid, chunk=current_chunk)

    def _handle_overworld_marker_list(self, eid, pos, limit=8):
        markers = self._overworld_markers_for(eid)
        if not markers:
            self.sim.emit(Event("overworld_marker_none", eid=eid))
            return

        origin_chunk = self.sim.chunk_coords(pos.x, pos.y)
        knowledge = _overworld_chunk_knowledge(self.sim, eid, current_chunk=origin_chunk)
        rows = []
        for marker in markers:
            chunk = marker.get("chunk")
            if not isinstance(chunk, (list, tuple)) or len(chunk) != 2:
                continue
            rows.append(self._marker_line(eid, marker, origin_chunk, knowledge=knowledge))

        if not rows:
            self.sim.emit(Event("overworld_marker_none", eid=eid))
            return

        rows.sort(key=lambda row: (row[0], row[1]))
        lines = [row[2] for row in rows[: max(1, int(limit))]]
        remaining = max(0, len(rows) - len(lines))
        self.sim.emit(Event(
            "overworld_marker_report",
            eid=eid,
            title=f"Markers ({len(rows)})",
            lines=lines,
            remaining=remaining,
        ))

    def _handle_overworld_marker_nearest(self, eid, pos):
        markers = self._overworld_markers_for(eid)
        if not markers:
            self.sim.emit(Event("overworld_marker_none", eid=eid))
            return

        origin_chunk = self.sim.chunk_coords(pos.x, pos.y)
        knowledge = _overworld_chunk_knowledge(self.sim, eid, current_chunk=origin_chunk)
        rows = []
        for marker in markers:
            chunk = marker.get("chunk")
            if not isinstance(chunk, (list, tuple)) or len(chunk) != 2:
                continue
            rows.append(self._marker_line(eid, marker, origin_chunk, knowledge=knowledge))

        if not rows:
            self.sim.emit(Event("overworld_marker_none", eid=eid))
            return

        rows.sort(key=lambda row: (row[0], row[1]))
        self.sim.emit(Event(
            "overworld_marker_report",
            eid=eid,
            title="Nearest marker",
            lines=[rows[0][2]],
            remaining=0,
        ))

    def _describe_overworld_cursor(self, eid, pos, cx, cy):
        origin_chunk = self.sim.chunk_coords(pos.x, pos.y)
        knowledge = _overworld_chunk_knowledge(self.sim, eid, current_chunk=origin_chunk)
        return self._overworld_chunk_inspect_line(
            eid,
            origin_chunk,
            (int(cx), int(cy)),
            knowledge=knowledge,
        )

    def handle_player_action(self, action, eid, pos, *, zoom_mode, event):
        if action == "overworld_marker_add":
            if zoom_mode != "overworld":
                return True
            self._handle_overworld_marker_add(eid=eid, pos=pos)
            return True

        if action == "overworld_marker_set":
            self._set_overworld_marker(
                eid=eid,
                chunk=(
                    event.data.get("target_chunk_x", 0),
                    event.data.get("target_chunk_y", 0),
                ),
                label=str(event.data.get("marker_label", "")).strip(),
                property_id=str(event.data.get("property_id", "")).strip(),
            )
            return True

        if action == "overworld_marker_list":
            if zoom_mode != "overworld":
                return True
            self._handle_overworld_marker_list(eid=eid, pos=pos, limit=8)
            return True

        if action == "overworld_marker_nearest":
            if zoom_mode != "overworld":
                return True
            self._handle_overworld_marker_nearest(eid=eid, pos=pos)
            return True

        return False

    def handle_cursor_examine(self, eid, pos, event, *, announce=False, purpose="inspect"):
        default_cx, default_cy = self.sim.chunk_coords(pos.x, pos.y)
        cx = int(event.data.get("cursor_chunk_x", default_cx))
        cy = int(event.data.get("cursor_chunk_y", default_cy))
        look_state = getattr(self.sim, "look_ui", None)
        if not isinstance(look_state, dict):
            look_state = {}
            self.sim.look_ui = look_state
        look_state["chunk_x"] = cx
        look_state["chunk_y"] = cy
        text = self._describe_overworld_cursor(eid=eid, pos=pos, cx=cx, cy=cy)
        self.action_system._set_look_inspect_text(text)
        self.sim.emit(Event(
            "cursor_examined",
            eid=eid,
            mode="overworld",
            purpose=purpose,
            cx=cx,
            cy=cy,
            text=text,
            announce=announce,
        ))

    def handle_scan_action(self, eid, pos):
        cx, cy = self.sim.chunk_coords(pos.x, pos.y)
        sampled = [
            ("Here", cx, cy),
            ("North", cx, cy - 1),
            ("East", cx + 1, cy),
            ("South", cx, cy + 1),
            ("West", cx - 1, cy),
        ]
        knowledge = _overworld_chunk_knowledge(self.sim, eid, current_chunk=(cx, cy))
        lines = []
        for label, qx, qy in sampled:
            lines.append(self._overworld_chunk_inspect_line(
                eid,
                (cx, cy),
                (qx, qy),
                label=label,
                knowledge=knowledge,
            ))

        self.sim.emit(Event(
            "scan_report",
            eid=eid,
            mode="overworld",
            lines=lines,
        ))
