from __future__ import annotations

import random

from game.components import Inventory, PlayerAssets, Position
from game.incident_runtime import incident_records
from game.items import ITEM_CATALOG

RUN_ECHOES_ARCHIVE_LIMIT = 64
RUN_ECHOES_MAX_INCIDENTS_PER_RUN = 3
RUN_ECHOES_MAX_REMNANTS_PER_RUN = 1
RUN_ECHOES_MAX_INCIDENT_SPAWNS_PER_RUN = 2
RUN_ECHOES_MAX_REMNANT_SPAWNS_PER_RUN = 1
RUN_ECHOES_SPAWN_CHANCE = 0.12
_CARDINAL_STEPS = ((1, 0), (-1, 0), (0, 1), (0, -1))
_ANCHOR_STEPS = (
    (0, 0),
    (1, 0),
    (-1, 0),
    (0, 1),
    (0, -1),
    (1, 1),
    (-1, 1),
    (1, -1),
    (-1, -1),
    (2, 0),
    (-2, 0),
    (0, 2),
    (0, -2),
)


def _text(value):
    return str(value or "").strip()


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _chunk_key(chunk):
    if isinstance(chunk, dict):
        try:
            return (int(chunk.get("cx", 0)), int(chunk.get("cy", 0)))
        except (TypeError, ValueError):
            return None
    if isinstance(chunk, (tuple, list)) and len(chunk) >= 2:
        try:
            return (int(chunk[0]), int(chunk[1]))
        except (TypeError, ValueError):
            return None
    return None


def _player_position(sim, player_eid):
    if sim is None or player_eid is None:
        return None
    return sim.ecs.get(Position).get(player_eid)


def _property_metadata(prop):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _record_area_profile(sim, chunk_key):
    if sim is None or chunk_key is None or getattr(sim, "world", None) is None:
        return {
            "area_type": "",
            "district_type": "",
            "region_name": "",
            "settlement_name": "",
        }
    desc = sim.world.overworld_descriptor(chunk_key[0], chunk_key[1])
    return {
        "area_type": _text(desc.get("area_type")).lower(),
        "district_type": _text(desc.get("district_type")).lower(),
        "region_name": _text(desc.get("region_name")),
        "settlement_name": _text(desc.get("settlement_name")),
    }


def _append_chunk_property_record(sim, chunk_key, prop_id, kind, x, y, z, archetype):
    records = getattr(sim, "chunk_property_records", None)
    if not isinstance(records, dict):
        sim.chunk_property_records = {}
        records = sim.chunk_property_records
    chunk_rows = records.setdefault(chunk_key, [])
    chunk_rows.append({
        "id": prop_id,
        "kind": kind,
        "x": x,
        "y": y,
        "z": z,
        "archetype": archetype,
        "building_id": None,
    })


def _item_row_score(entry):
    entry = dict(entry or {})
    item_id = _text(entry.get("item_id")).lower()
    item_def = ITEM_CATALOG.get(item_id, {})
    score = 0
    if item_def.get("weapon_id"):
        score += 120
    if item_def.get("armor"):
        score += 100
    if item_def.get("disguise"):
        score += 90
    if item_def.get("container"):
        score += 80
    if item_def.get("tool_profiles"):
        score += 65
    if item_def.get("effects"):
        score += 55
    tags = {
        str(tag).strip().lower()
        for tag in item_def.get("tags", ())
        if str(tag).strip()
    }
    if "ammo" in tags:
        score += 35
    if "tool" in tags:
        score += 30
    score += min(6, _safe_int(entry.get("quantity"), default=1))
    return score


def _snapshot_remnant_item_rows(sim, player_eid):
    inventory = sim.ecs.get(Inventory).get(player_eid) if sim is not None else None
    entries = list(inventory.items) if inventory else []
    rows = []
    used_item_ids = set()
    for entry in sorted(entries, key=lambda row: (_item_row_score(row), _text(row.get("item_id"))), reverse=True):
        item_id = _text(entry.get("item_id")).lower()
        if not item_id or item_id in used_item_ids:
            continue
        item_def = ITEM_CATALOG.get(item_id, {})
        stack_max = max(1, _safe_int(item_def.get("stack_max"), default=1))
        quantity = max(1, _safe_int(entry.get("quantity"), default=1))
        rows.append({
            "item_id": item_id,
            "quantity": 1 if stack_max <= 1 else min(quantity, min(stack_max, 3)),
            "metadata": dict(entry.get("metadata") or {}),
            "owner_eid": None,
            "owner_tag": "cache",
        })
        used_item_ids.add(item_id)
        if len(rows) >= 5:
            break
    assets = sim.ecs.get(PlayerAssets).get(player_eid) if sim is not None else None
    credits = max(0, _safe_int(getattr(assets, "credits", 0), default=0)) if assets is not None else 0
    chip_count = min(4, max(0, credits // 60))
    if chip_count > 0 and len(rows) < 5 and "credstick_chip" not in used_item_ids:
        rows.append({
            "item_id": "credstick_chip",
            "quantity": chip_count,
            "metadata": {"source": "run_echo"},
            "owner_eid": None,
            "owner_tag": "cache",
        })
    return rows


def _echo_notice_name(record):
    incident_kind = _text(record.get("incident_kind")).replace("_", " ").strip().lower()
    if "action offense" in incident_kind:
        return "Case Bulletin"
    if "trespass" in incident_kind:
        return "Caution Posting"
    if "stolen" in incident_kind or "theft" in incident_kind:
        return "Theft Notice"
    return "Public Notice"


def _incident_subject_text(record):
    victim_name = _text(record.get("victim_name"))
    property_name = _text(record.get("property_name"))
    if victim_name and property_name:
        return f"{victim_name} at {property_name}"
    if property_name:
        return property_name
    if victim_name:
        return victim_name
    return "that case"


def _incident_bulletin_text(record):
    kind = _text(record.get("incident_kind")).replace("_", " ").strip().lower()
    subject = _incident_subject_text(record)
    if kind == "action offense":
        return f"A remembered violent case still hangs over {subject}. The posting reads like an old warning, not a closed story."
    if kind == "property_trespass":
        return f"A reported trespass at {subject} still gets mentioned on public notices here."
    if kind == "property_tamper":
        return f"A tampering case at {subject} still lingers in the public paperwork."
    if kind == "item_stolen":
        return f"A stolen-property case around {subject} still lives on in posted caution notes."
    return f"An old case around {subject} still shows up in local notices."


def _incident_rumor_text(record):
    kind = _text(record.get("incident_kind")).replace("_", " ").strip().lower()
    subject = _incident_subject_text(record)
    if kind == "action offense":
        return f"People still talk about the violence at {subject}."
    if kind == "property_trespass":
        return f"People still remember who crossed the line at {subject}."
    if kind == "property_tamper":
        return f"People still mention someone trying to work over {subject}."
    if kind == "item_stolen":
        return f"People still talk about what disappeared around {subject}."
    return f"People still trade stories about what happened around {subject}."


def _incident_summary_text(record):
    kind = _text(record.get("incident_kind")).replace("_", " ").strip().lower()
    subject = _incident_subject_text(record)
    if kind == "action offense":
        return f"Violence at {subject} stayed with the city."
    if kind == "property_trespass":
        return f"Trespass at {subject} still echoes locally."
    if kind == "property_tamper":
        return f"Tampering at {subject} still echoes locally."
    if kind == "item_stolen":
        return f"A theft around {subject} still echoes locally."
    return f"A case around {subject} still echoes locally."


def _incident_dispatch_weight(ledger, incident_id):
    if ledger is None or incident_id is None:
        return 0
    total = 0
    for kind, base in (
        ("dispatch_started", 4),
        ("dispatch_arrived", 3),
        ("dispatch_queued", 2),
        ("authority_report", 3),
        ("look_away", 1),
        ("alarm_blocked", 1),
        ("alarm_cut", 1),
    ):
        for fact in tuple(getattr(ledger, "by_kind", {}).get(kind, ()) or ()):
            if _safe_int((fact.data or {}).get("incident_id"), default=0) == int(incident_id):
                total += base
    return total


def _incident_echo_score(incident, *, ledger=None):
    severity = max(0, min(100, _safe_int(incident.get("severity"), default=0)))
    official = bool(incident.get("officially_reported") or incident.get("justice_accounted"))
    propagation = max(
        _safe_int(incident.get("current_propagation"), default=0),
        _safe_int(incident.get("max_propagation"), default=0),
    )
    violent = _text(incident.get("kind")) == "action_offense"
    killed = "death" in {_text(tag).lower() for tag in tuple(incident.get("tags", ()) or ())}
    named = 0
    if _text(incident.get("victim_name")):
        named += 1
    if _text(incident.get("property_name")):
        named += 1
    score = severity
    if official:
        score += 30
    if violent:
        score += 24
    if killed:
        score += 18
    score += propagation * 8
    score += named * 5
    score += _incident_dispatch_weight(ledger, _safe_int(incident.get("id"), default=0))
    return score


def _incident_property_context(sim, incident):
    property_id = _text(incident.get("property_id"))
    prop = sim.properties.get(property_id) if property_id else None
    metadata = _property_metadata(prop)
    property_archetype = _text(metadata.get("archetype", (prop or {}).get("kind"))).lower()
    organization_name = _text(metadata.get("organization_name"))
    if not organization_name:
        organization_name = _text(metadata.get("business_name"))
    return {
        "property_id": property_id,
        "property_name": _text(incident.get("property_name")) or _text((prop or {}).get("name")),
        "property_archetype": property_archetype,
        "organization_name": organization_name,
    }


def _build_incident_echo_records(sim, *, outcome=""):
    ledger = getattr(sim, "run_epilogue_ledger", None)
    ranked = []
    for incident in incident_records(sim):
        if not isinstance(incident, dict):
            continue
        severity = _safe_int(incident.get("severity"), default=0)
        official = bool(incident.get("officially_reported") or incident.get("justice_accounted"))
        propagation = max(
            _safe_int(incident.get("current_propagation"), default=0),
            _safe_int(incident.get("max_propagation"), default=0),
        )
        violent = _text(incident.get("kind")) == "action_offense"
        if not any((
            official,
            violent and severity >= 45,
            propagation >= 2,
            severity >= 70,
        )):
            continue
        score = _incident_echo_score(incident, ledger=ledger)
        ranked.append((score, _safe_int(incident.get("id"), default=0), incident))

    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    records = []
    for score, incident_id, incident in ranked[:RUN_ECHOES_MAX_INCIDENTS_PER_RUN]:
        x = incident.get("x")
        y = incident.get("y")
        chunk_key = None
        if x is not None and y is not None:
            try:
                chunk_key = sim.chunk_coords(int(x), int(y))
            except Exception:
                chunk_key = None
        area = _record_area_profile(sim, chunk_key)
        prop_ctx = _incident_property_context(sim, incident)
        caution_bias = max(4, min(12, int(round(float(score) / 22.0))))
        record = {
            "echo_id": f"incident:{getattr(sim, 'seed', 'seed')}:{incident_id}:{_safe_int(getattr(sim, 'tick', 0), default=0)}",
            "family": "incident_echo",
            "incident_id": incident_id,
            "incident_kind": _text(incident.get("kind")).lower() or "incident",
            "summary": "",
            "bulletin_text": "",
            "rumor_text": "",
            "severity": _safe_int(incident.get("severity"), default=0),
            "officially_reported": bool(incident.get("officially_reported") or incident.get("justice_accounted")),
            "propagation_depth": max(
                _safe_int(incident.get("current_propagation"), default=0),
                _safe_int(incident.get("max_propagation"), default=0),
            ),
            "victim_name": _text(incident.get("victim_name")),
            "subject_name": _text(incident.get("victim_name")) or _text(incident.get("property_name")),
            "property_name": prop_ctx["property_name"],
            "property_id": prop_ctx["property_id"],
            "property_archetype": prop_ctx["property_archetype"],
            "organization_name": prop_ctx["organization_name"],
            "run_outcome": _text(outcome).lower(),
            "tick": _safe_int(incident.get("last_observed_tick"), default=_safe_int(getattr(sim, "tick", 0), default=0)),
            "caution_bias": caution_bias,
            **area,
        }
        record["summary"] = _incident_summary_text(record)
        record["bulletin_text"] = _incident_bulletin_text(record)
        record["rumor_text"] = _incident_rumor_text(record)
        records.append(record)
    return records


def _build_successful_remnant_echo_record(sim, player_eid, *, outcome="", objective_title=""):
    if _text(outcome).lower() == "failed":
        return None
    pos = _player_position(sim, player_eid)
    if pos is None:
        return None
    item_rows = _snapshot_remnant_item_rows(sim, player_eid)
    if not item_rows:
        return None
    chunk_key = sim.chunk_coords(int(pos.x), int(pos.y))
    area = _record_area_profile(sim, chunk_key)
    prop = sim.property_covering(int(pos.x), int(pos.y), int(pos.z)) if hasattr(sim, "property_covering") else None
    metadata = _property_metadata(prop)
    property_name = _text((prop or {}).get("name"))
    property_archetype = _text(metadata.get("archetype", (prop or {}).get("kind"))).lower()
    character_name = _text(getattr(sim, "character_name", "")) or _text(getattr(sim, "world_traits", {}).get("character_name")) or "a runner"
    stash_name = f"Retired Drop from {character_name}"
    note_bits = [f"Someone left this after {character_name}'s run."]
    if objective_title:
        note_bits.append(f"The note still mentions {objective_title}.")
    if property_name:
        note_bits.append(f"It traces back to {property_name}.")
    note_text = " ".join(note_bits)
    summary = f"A retired stash from {character_name} may resurface later."
    return {
        "echo_id": f"remnant:{getattr(sim, 'seed', 'seed')}:{_safe_int(getattr(sim, 'tick', 0), default=0)}",
        "family": "remnant_echo",
        "summary": summary,
        "note_text": note_text,
        "stash_name": stash_name,
        "item_rows": item_rows,
        "property_name": property_name,
        "property_archetype": property_archetype,
        "objective_title": _text(objective_title),
        "run_outcome": _text(outcome).lower(),
        "tick": _safe_int(getattr(sim, "tick", 0), default=0),
        **area,
    }


def archive_run_echoes(sim, player_eid, *, outcome="", reason="", objective_title="", summary_lines=()):
    del reason, summary_lines
    from engine.persistence import append_run_echo_record

    runtime = prime_run_echoes_runtime(sim)
    archive_path = runtime.get("archive_path")
    incident_records_to_archive = _build_incident_echo_records(sim, outcome=outcome)
    remnant_records = []
    remnant = _build_successful_remnant_echo_record(
        sim,
        player_eid,
        outcome=outcome,
        objective_title=objective_title,
    )
    if isinstance(remnant, dict):
        remnant_records.append(remnant)
    archived = []
    for record in [*incident_records_to_archive[:RUN_ECHOES_MAX_INCIDENTS_PER_RUN], *remnant_records[:RUN_ECHOES_MAX_REMNANTS_PER_RUN]]:
        append_run_echo_record(record, archive_path=archive_path, max_records=RUN_ECHOES_ARCHIVE_LIMIT)
        archived.append(record)
    if archived:
        existing = {
            _text(row.get("echo_id")): dict(row)
            for row in tuple(runtime.get("records", ()) or ())
            if isinstance(row, dict)
        }
        for record in archived:
            existing[_text(record.get("echo_id"))] = dict(record)
        runtime["records"] = list(existing.values())[-RUN_ECHOES_ARCHIVE_LIMIT:]

    run_end = getattr(sim, "world_traits", {}).get("run_end", {}) if isinstance(getattr(sim, "world_traits", None), dict) else {}
    bones_archived = bool(run_end.get("bones_record_id") or run_end.get("bones_archived"))
    lines = ["What may carry forward:"]
    if incident_records_to_archive:
        strongest = incident_records_to_archive[0]
        lines.append(f"  Strongest incident echo: {_text(strongest.get('summary'))}")
        for record in incident_records_to_archive:
            lines.append(f"  Incident echo: {_text(record.get('summary'))}")
    if remnant_records:
        lines.append(f"  Remnant echo: {_text(remnant_records[0].get('summary'))}")
    if not incident_records_to_archive and not remnant_records:
        lines.append("  Nothing strong enough will echo forward this time.")
    lines.append(
        "  Failed-run bones: "
        + ("a separate grave and stash record were archived." if bones_archived else "no failed-run bones were archived.")
    )
    return {
        "records": tuple(archived),
        "lines": tuple(lines),
        "incident_records": tuple(incident_records_to_archive),
        "remnant_record": remnant_records[0] if remnant_records else None,
    }


def prime_run_echoes_runtime(sim, *, archive_path=None):
    from engine.persistence import load_run_echoes_archive

    if sim is None:
        return {"records": []}
    runtime = getattr(sim, "run_echoes_runtime", None)
    if not isinstance(runtime, dict):
        runtime = {}
        sim.run_echoes_runtime = runtime
    if archive_path is not None:
        runtime["archive_path"] = str(archive_path)
    runtime.setdefault("attempted_chunks", set())
    runtime.setdefault("spawned_echo_ids", set())
    runtime.setdefault("spawn_counts", {"incident_echo": 0, "remnant_echo": 0})
    runtime.setdefault("active_spawns_by_chunk", {})
    if not isinstance(runtime.get("records"), list):
        runtime["records"] = load_run_echoes_archive(archive_path=runtime.get("archive_path"))
    return runtime


def _chunk_records(sim, chunk_key):
    records = getattr(sim, "chunk_property_records", {})
    rows = list(records.get(chunk_key, ()) or ())
    props = []
    for row in rows:
        prop = sim.properties.get(str((row or {}).get("id", "")).strip())
        if isinstance(prop, dict):
            props.append(prop)
    return props


def _record_match_score(record, chunk, *, prop=None):
    if not isinstance(record, dict):
        return -1
    district = chunk.get("district", {}) if isinstance(chunk, dict) else {}
    chunk_area = _text(district.get("area_type")).lower()
    chunk_district = _text(district.get("district_type")).lower()
    score = 0
    if chunk_area and _text(record.get("area_type")).lower() == chunk_area:
        score += 3
    if chunk_district and _text(record.get("district_type")).lower() == chunk_district:
        score += 2
    if isinstance(prop, dict):
        metadata = _property_metadata(prop)
        archetype = _text(metadata.get("archetype", prop.get("kind"))).lower()
        if archetype and archetype == _text(record.get("property_archetype")).lower():
            score += 5
        organization_name = _text(metadata.get("organization_name")) or _text(metadata.get("business_name"))
        if organization_name and organization_name.lower() == _text(record.get("organization_name")).lower():
            score += 4
    return score


def _best_target_property(sim, chunk_key, record):
    chunk = sim.world.get_chunk(chunk_key[0], chunk_key[1]) if getattr(sim, "world", None) is not None else {}
    best = None
    best_score = -1
    for prop in _chunk_records(sim, chunk_key):
        score = _record_match_score(record, chunk, prop=prop)
        if score > best_score:
            best = prop
            best_score = score
    return best, best_score


def _is_empty_walkable_tile(sim, x, y, z=0):
    tile = sim.tilemap.tile_at(x, y, z) if sim is not None else None
    if not tile or not bool(getattr(tile, "walkable", False)):
        return False
    if getattr(sim, "property_at", None) and sim.property_at(x, y, z):
        return False
    if getattr(sim, "property_covering", None) and sim.property_covering(x, y, z):
        return False
    return True


def _anchor_near_property(sim, prop):
    if not isinstance(prop, dict):
        return None
    base_x = _safe_int(prop.get("x"), default=0)
    base_y = _safe_int(prop.get("y"), default=0)
    base_z = _safe_int(prop.get("z"), default=0)
    for dx, dy in _ANCHOR_STEPS:
        x = base_x + dx
        y = base_y + dy
        if _is_empty_walkable_tile(sim, x, y, base_z):
            return (x, y, base_z)
    return None


def _pick_chunk_open_tile(sim, chunk_key, rng):
    origin_x, origin_y = sim.chunk_origin(*chunk_key)
    size = max(8, _safe_int(getattr(sim, "chunk_size", 16), default=16))
    candidates = []
    for y in range(origin_y + 1, origin_y + size - 1):
        for x in range(origin_x + 1, origin_x + size - 1):
            if _is_empty_walkable_tile(sim, x, y, 0):
                score = 0
                tile = sim.tilemap.tile_at(x, y, 0)
                if str(getattr(tile, "glyph", "")).strip() in {"=", ":"}:
                    score += 2
                candidates.append((score, x, y, 0))
    if not candidates:
        return None
    best = max(score for score, *_rest in candidates)
    finalists = [row[1:] for row in candidates if row[0] == best]
    return rng.choice(finalists)


def _seed_incident_notice(sim, chunk_key, record, rng):
    target_prop, _score = _best_target_property(sim, chunk_key, record)
    anchor = _anchor_near_property(sim, target_prop) if isinstance(target_prop, dict) else None
    if anchor is None:
        anchor = _pick_chunk_open_tile(sim, chunk_key, rng)
    if anchor is None:
        return None
    metadata = {
        "archetype": "run_echo_notice",
        "fixture_type": "run_echo_notice",
        "interaction_role": "run_echo_notice",
        "chunk": chunk_key,
        "public": True,
        "display_glyph": "!",
        "display_color": "property_fixture",
        "container_kind": "container",
        "container_label": "Bulletin",
        "container_note_text": _text(record.get("bulletin_text")),
        "run_echo_id": _text(record.get("echo_id")),
        "run_echo_family": "incident_echo",
        "run_echo_summary": _text(record.get("summary")),
        "run_echo_rumor_text": _text(record.get("rumor_text")),
        "run_echo_caution_bias": _safe_int(record.get("caution_bias"), default=0),
        "run_echo_target_property_id": _text((target_prop or {}).get("id")) or _text(record.get("property_id")),
        "run_echo_target_archetype": _text(record.get("property_archetype")).lower(),
        "run_echo_organization_name": _text(record.get("organization_name")),
    }
    prop_id = sim.register_property(
        _echo_notice_name(record),
        "fixture",
        anchor[0],
        anchor[1],
        anchor[2],
        owner_tag="public",
        metadata=metadata,
    )
    _append_chunk_property_record(sim, chunk_key, prop_id, "fixture", anchor[0], anchor[1], anchor[2], "run_echo_notice")
    return {
        "echo_id": _text(record.get("echo_id")),
        "family": "incident_echo",
        "spawn_property_id": prop_id,
        "target_property_id": _text(metadata.get("run_echo_target_property_id")),
        "target_archetype": _text(metadata.get("run_echo_target_archetype")),
        "organization_name": _text(metadata.get("run_echo_organization_name")),
        "summary": _text(record.get("summary")),
        "rumor_text": _text(record.get("rumor_text")),
        "caution_bias": _safe_int(record.get("caution_bias"), default=0),
    }


def _seed_remnant_stash(sim, chunk_key, record, rng):
    anchor = _pick_chunk_open_tile(sim, chunk_key, rng)
    if anchor is None:
        return None
    metadata = {
        "archetype": "run_echo_stash",
        "fixture_type": "run_echo_stash",
        "interaction_role": "run_echo_stash",
        "fixture_kind": "cache",
        "container_kind": "cache",
        "container_label": "Stash",
        "container_note_text": _text(record.get("note_text")),
        "chunk": chunk_key,
        "public": True,
        "display_glyph": "j",
        "display_color": "property_asset",
        "run_echo_id": _text(record.get("echo_id")),
        "run_echo_family": "remnant_echo",
        "run_echo_summary": _text(record.get("summary")),
    }
    prop_id = sim.register_property(
        _text(record.get("stash_name")) or "Retired Stash",
        "asset",
        anchor[0],
        anchor[1],
        anchor[2],
        owner_tag="public",
        metadata=metadata,
    )
    _append_chunk_property_record(sim, chunk_key, prop_id, "asset", anchor[0], anchor[1], anchor[2], "run_echo_stash")
    from game.property_runtime import property_runtime_container_entries

    entries = property_runtime_container_entries(sim, prop_id, container_kind="cache")
    entries[:] = [
        {
            "item_id": _text(entry.get("item_id")).lower(),
            "quantity": max(1, _safe_int(entry.get("quantity"), default=1)),
            "metadata": dict(entry.get("metadata") or {}),
            "owner_eid": None,
            "owner_tag": _text(entry.get("owner_tag")) or "cache",
        }
        for entry in tuple(record.get("item_rows", ()) or ())
        if _text((entry or {}).get("item_id"))
    ]
    return {
        "echo_id": _text(record.get("echo_id")),
        "family": "remnant_echo",
        "spawn_property_id": prop_id,
        "target_property_id": "",
        "target_archetype": _text(record.get("property_archetype")).lower(),
        "organization_name": "",
        "summary": _text(record.get("summary")),
        "rumor_text": "",
        "caution_bias": 0,
    }


def maybe_seed_run_echo_for_chunk(sim, chunk, *, force=False):
    chunk_key = _chunk_key(chunk)
    if sim is None or chunk_key is None:
        return None
    runtime = prime_run_echoes_runtime(sim)
    attempted = runtime.setdefault("attempted_chunks", set())
    if chunk_key in attempted:
        return None
    attempted.add(chunk_key)

    records = [row for row in runtime.get("records", ()) if isinstance(row, dict)]
    if not records:
        return None
    used_ids = runtime.setdefault("spawned_echo_ids", set())
    spawn_counts = runtime.setdefault("spawn_counts", {"incident_echo": 0, "remnant_echo": 0})
    rng = random.Random(f"{getattr(sim, 'seed', 'seed')}:run_echo:{chunk_key[0]}:{chunk_key[1]}")
    if not force and rng.random() > RUN_ECHOES_SPAWN_CHANCE:
        return None

    active_rows = []
    chunk_data = sim.world.get_chunk(chunk_key[0], chunk_key[1]) if getattr(sim, "world", None) is not None else {}
    for family, limit, seeder in (
        ("incident_echo", RUN_ECHOES_MAX_INCIDENT_SPAWNS_PER_RUN, _seed_incident_notice),
        ("remnant_echo", RUN_ECHOES_MAX_REMNANT_SPAWNS_PER_RUN, _seed_remnant_stash),
    ):
        if _safe_int(spawn_counts.get(family), default=0) >= int(limit):
            continue
        eligible = [
            record
            for record in records
            if _text(record.get("family")).lower() == family
            and _text(record.get("echo_id")) not in used_ids
        ]
        if not eligible:
            continue
        scored = []
        for record in eligible:
            target_prop, target_score = _best_target_property(sim, chunk_key, record)
            base_score = _record_match_score(record, chunk_data, prop=target_prop)
            scored.append((max(base_score, target_score), _text(record.get("echo_id")), record))
        scored.sort(key=lambda row: (row[0], row[1]), reverse=True)
        best_score = scored[0][0]
        finalists = [row[2] for row in scored if row[0] == best_score]
        chosen = rng.choice(finalists)
        seeded = seeder(sim, chunk_key, chosen, rng)
        if not isinstance(seeded, dict):
            continue
        used_ids.add(_text(chosen.get("echo_id")))
        spawn_counts[family] = _safe_int(spawn_counts.get(family), default=0) + 1
        active_rows.append(seeded)

    if not active_rows:
        return None
    by_chunk = runtime.setdefault("active_spawns_by_chunk", {})
    existing = list(by_chunk.get(chunk_key, ()) or ())
    existing.extend(active_rows)
    by_chunk[chunk_key] = existing
    return {
        "chunk": chunk_key,
        "spawns": tuple(active_rows),
    }


def active_run_echo_spawns_for_chunk(sim, chunk, *, family=None):
    chunk_key = _chunk_key(chunk)
    if sim is None or chunk_key is None:
        return ()
    runtime = prime_run_echoes_runtime(sim)
    rows = []
    for row in tuple((runtime.get("active_spawns_by_chunk", {}) or {}).get(chunk_key, ()) or ()):
        if not isinstance(row, dict):
            continue
        if family and _text(row.get("family")).lower() != _text(family).lower():
            continue
        rows.append(dict(row))
    return tuple(rows)


def strongest_active_run_echo_for_chunk(sim, chunk, *, family=None):
    rows = list(active_run_echo_spawns_for_chunk(sim, chunk, family=family))
    if not rows:
        return None
    rows.sort(
        key=lambda row: (
            _safe_int(row.get("caution_bias"), default=0),
            1 if _text(row.get("family")).lower() == "incident_echo" else 0,
            _text(row.get("echo_id")),
        ),
        reverse=True,
    )
    return rows[0]


def incident_echo_caution_for_property(sim, prop):
    if not isinstance(prop, dict):
        return {"active": False, "watchfulness_bonus": 0, "note_texts": (), "incident_echo_count": 0}
    try:
        chunk_key = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
    except Exception:
        return {"active": False, "watchfulness_bonus": 0, "note_texts": (), "incident_echo_count": 0}
    active = active_run_echo_spawns_for_chunk(sim, chunk_key, family="incident_echo")
    if not active:
        return {"active": False, "watchfulness_bonus": 0, "note_texts": (), "incident_echo_count": 0}
    metadata = _property_metadata(prop)
    prop_id = _text(prop.get("id"))
    archetype = _text(metadata.get("archetype", prop.get("kind"))).lower()
    organization_name = (_text(metadata.get("organization_name")) or _text(metadata.get("business_name"))).lower()
    bonus = 0
    count = 0
    notes = []
    for row in active:
        row_bonus = _safe_int(row.get("caution_bias"), default=0)
        target_id = _text(row.get("target_property_id"))
        target_archetype = _text(row.get("target_archetype")).lower()
        target_org = _text(row.get("organization_name")).lower()
        if target_id and target_id == prop_id:
            matched = row_bonus
        elif target_org and organization_name and target_org == organization_name:
            matched = max(2, row_bonus - 2)
        elif target_archetype and archetype and target_archetype == archetype:
            matched = max(1, row_bonus - 3)
        else:
            matched = max(1, row_bonus - 5)
        bonus = max(bonus, matched)
        count += 1
        summary = _text(row.get("summary"))
        if summary:
            notes.append(summary)
    if bonus <= 0:
        return {"active": False, "watchfulness_bonus": 0, "note_texts": (), "incident_echo_count": count}
    note_texts = tuple(notes[:2]) if notes else ("A remembered case still makes the block read a little tighter.",)
    return {
        "active": True,
        "watchfulness_bonus": int(bonus),
        "note_texts": note_texts,
        "incident_echo_count": int(count),
    }
