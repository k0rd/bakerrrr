from __future__ import annotations

import hashlib
import random

from game.components import (
    AI,
    Collider,
    CreatureIdentity,
    Inventory,
    NPCNeeds,
    NPCSocial,
    NPCTraits,
    NPCWill,
    Occupation,
    PlayerAssets,
    Position,
    Render,
    Vitality,
)
from game.incident_runtime import incident_kind_label, incident_records
from game.items import ITEM_CATALOG

RUN_ECHOES_ARCHIVE_LIMIT = 64
RUN_ECHOES_MAX_INCIDENTS_PER_RUN = 3
RUN_ECHOES_MAX_BUSINESSES_PER_RUN = 2
RUN_ECHOES_MAX_REMNANTS_PER_RUN = 1
RUN_ECHOES_MAX_INCIDENT_SPAWNS_PER_RUN = 2
RUN_ECHOES_MAX_BUSINESS_SPAWNS_PER_RUN = 1
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


def _stamp_value(value):
    if isinstance(value, dict):
        return "{" + ",".join(
            f"{_text(key).casefold()}={_stamp_value(value[key])}"
            for key in sorted(value, key=lambda item: _text(item).casefold())
        ) + "}"
    if isinstance(value, (list, tuple, set, frozenset)):
        return "[" + ",".join(_stamp_value(item) for item in tuple(value)) + "]"
    return _text(value).casefold()


def _stable_stamp(prefix, *values):
    raw = "|".join(_stamp_value(value) for value in values)
    digest = hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()[:12]
    prefix = _text(prefix).lower() or "echo"
    return f"{prefix}:{digest}"


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


def _display_ref_text(value):
    text = _text(value)
    if "#" in text:
        prefix, suffix = text.rsplit("#", 1)
        if prefix.strip() and suffix.strip().isdigit():
            text = prefix.strip()
    return text


def _sentence_start(value):
    text = _text(value)
    if not text:
        return ""
    return text[:1].upper() + text[1:]


def _join_detail_bits(bits):
    cleaned = [_text(bit) for bit in tuple(bits or ()) if _text(bit)]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return f"{', '.join(cleaned[:-1])}, and {cleaned[-1]}"


def _incident_reference_parts(record):
    person_name = _display_ref_text(record.get("victim_name"))
    place_name = _display_ref_text(record.get("property_name"))
    return person_name, place_name


def _incident_reference_clause(record, *, place_preposition="at", place_first=True):
    person_name, place_name = _incident_reference_parts(record)
    place_preposition = _text(place_preposition) or "at"
    if person_name and place_name:
        if place_first:
            return f"{place_preposition} {place_name} involving {person_name}"
        return f"involving {person_name} {place_preposition} {place_name}"
    if place_name:
        return f"{place_preposition} {place_name}"
    if person_name:
        return f"involving {person_name}"
    return ""


def _incident_subject_text(record):
    person_name, place_name = _incident_reference_parts(record)
    if person_name and place_name:
        return f"{person_name} at {place_name}"
    if place_name:
        return place_name
    if person_name:
        return person_name
    return "an old case"


def _incident_bulletin_text(record):
    kind = _text(record.get("incident_kind")).replace("_", " ").strip().lower()
    place_ref = _incident_reference_clause(record, place_preposition="at", place_first=True)
    person_ref = _incident_reference_clause(record, place_preposition="at", place_first=False)
    around_ref = _incident_reference_clause(record, place_preposition="around", place_first=True)
    if kind == "action offense":
        if person_ref:
            return f"A remembered violent case {person_ref} still hangs over the city. The posting reads like an old warning, not a closed story."
        return "A remembered violent case still hangs over the city. The posting reads like an old warning, not a closed story."
    if kind == "property trespass":
        if place_ref:
            return f"A reported trespass {place_ref} still gets mentioned on public notices here."
        return "A reported trespass still gets mentioned on public notices here."
    if kind == "property tamper":
        if place_ref:
            return f"A tampering case {place_ref} still lingers in the public paperwork."
        return "A tampering case still lingers in the public paperwork."
    if kind == "item stolen":
        if around_ref:
            return f"A stolen-property case {around_ref} still lives on in posted caution notes."
        return "A stolen-property case still lives on in posted caution notes."
    if around_ref:
        return f"An old case {around_ref} still shows up in local notices."
    return "An old case still shows up in local notices."


def _incident_kind_display(record):
    label = _text(record.get("kind_label"))
    if label:
        return label
    return incident_kind_label(
        record.get("incident_kind"),
        action=record.get("action"),
        context=record.get("context"),
        tags=record.get("tags", ()),
    )


def _incident_echo_title(record):
    kind = _incident_kind_display(record)
    incident_kind = _text(record.get("incident_kind")).lower()
    if incident_kind == "action_offense" and kind == "trouble":
        kind = "violence"
    if not kind:
        kind = "incident"

    if incident_kind == "action_offense":
        ref = _incident_reference_clause(record, place_preposition="at", place_first=False)
    elif kind == "theft":
        ref = _incident_reference_clause(record, place_preposition="around", place_first=True)
    else:
        ref = _incident_reference_clause(record, place_preposition="at", place_first=True)
    title = _sentence_start(kind)
    if ref:
        return f"{title} {ref}"
    return f"{title} incident"


def _incident_echo_why_bits(record):
    kind = _incident_kind_display(record)
    if _text(record.get("incident_kind")).lower() == "action_offense" and kind == "trouble":
        kind = "violence"
    severity = _safe_int(record.get("severity"), default=0)
    if severity >= 70:
        bits = [f"severe {kind}"]
    elif severity >= 45:
        bits = [f"serious {kind}"]
    elif severity >= 25:
        bits = [f"noticeable {kind}"]
    elif severity > 0:
        bits = [f"low-level {kind}"]
    else:
        bits = [kind or "incident"]

    if bool(record.get("officially_reported")):
        bits.append("official report")
    propagation = _safe_int(record.get("propagation_depth"), default=0)
    if propagation >= 2:
        bits.append("repeated local talk")
    elif propagation == 1:
        bits.append("local rumor")
    accountable = _safe_int(record.get("accountable_observer_count"), default=0)
    observed = _safe_int(record.get("observer_count"), default=0)
    if accountable > 1:
        bits.append(f"seen by {accountable} accountable witnesses")
    elif accountable == 1:
        bits.append("seen by an accountable witness")
    elif observed > 1:
        bits.append(f"seen by {observed} witnesses")
    elif observed == 1:
        bits.append("seen by a witness")

    organization_name = _text(record.get("organization_name"))
    property_name = _display_ref_text(record.get("property_name"))
    if organization_name:
        bits.append(f"tied to {organization_name}")
    elif property_name:
        bits.append(f"tied to {property_name}")
    else:
        settlement_name = _text(record.get("settlement_name"))
        district_type = _text(record.get("district_type")).replace("_", " ")
        if settlement_name:
            bits.append(f"remembered in {settlement_name}")
        elif district_type:
            bits.append(f"remembered in the {district_type} district")
    return tuple(bits)


def _incident_echo_epilogue_line(record, *, strongest=False):
    prefix = "Strongest incident echo" if strongest else "Incident echo"
    title = _incident_echo_title(record)
    why = _join_detail_bits(_incident_echo_why_bits(record))
    line = f"  {prefix}: {title}."
    if why:
        line += f" Why it carries: {why}."
    return line


def _incident_rumor_text(record):
    kind = _text(record.get("incident_kind")).replace("_", " ").strip().lower()
    place_ref = _incident_reference_clause(record, place_preposition="at", place_first=True)
    person_ref = _incident_reference_clause(record, place_preposition="at", place_first=False)
    around_ref = _incident_reference_clause(record, place_preposition="around", place_first=True)
    if kind == "action offense":
        if person_ref:
            return f"People still talk about the violence {person_ref}."
        return "People still talk about an old violent case."
    if kind == "property trespass":
        if place_ref:
            return f"People still remember the trespass {place_ref}."
        return "People still remember an old trespass."
    if kind == "property tamper":
        if place_ref:
            return f"People still mention the tampering {place_ref}."
        return "People still mention an old tampering case."
    if kind == "item stolen":
        if around_ref:
            return f"People still talk about the theft {around_ref}."
        return "People still talk about an old theft."
    if around_ref:
        return f"People still trade stories about an old case {around_ref}."
    return "People still trade stories about an old case."


def _incident_summary_text(record):
    kind = _text(record.get("incident_kind")).replace("_", " ").strip().lower()
    place_ref = _incident_reference_clause(record, place_preposition="at", place_first=True)
    person_ref = _incident_reference_clause(record, place_preposition="at", place_first=False)
    around_ref = _incident_reference_clause(record, place_preposition="around", place_first=True)
    if kind == "action offense":
        if person_ref:
            return f"Violence {person_ref} stayed with the city."
        return "Violence stayed with the city."
    if kind == "property trespass":
        if place_ref:
            return f"Trespass {place_ref} still echoes locally."
        return "Trespass still echoes locally."
    if kind == "property tamper":
        if place_ref:
            return f"Tampering {place_ref} still echoes locally."
        return "Tampering still echoes locally."
    if kind == "item stolen":
        if around_ref:
            return f"A theft {around_ref} still echoes locally."
        return "A theft still echoes locally."
    if around_ref:
        return f"A case {around_ref} still echoes locally."
    return "A case still echoes locally."


def _player_business_owner_name(sim):
    character_name = _text(getattr(sim, "character_name", "")) or _text(getattr(sim, "world_traits", {}).get("character_name"))
    return character_name or "the prior owner"


def _property_owned_by_player(sim, prop, player_eid):
    if sim is None or player_eid is None or not isinstance(prop, dict):
        return False
    try:
        if prop.get("owner_eid") is not None and int(prop.get("owner_eid")) == int(player_eid):
            return True
    except (TypeError, ValueError):
        pass
    if _text(prop.get("owner_tag")).lower() == "player":
        return True
    assets = sim.ecs.get(PlayerAssets).get(player_eid)
    return bool(assets and _text(prop.get("id")) in getattr(assets, "owned_property_ids", set()))


def _business_echo_score(snapshot):
    if not isinstance(snapshot, dict):
        return 0
    score = 22
    signal = _text(snapshot.get("owner_signal_kind")).lower()
    if signal:
        score += {
            "closed_off": 30,
            "screened": 24,
            "thin": 26,
            "expensive": 24,
            "strained": 28,
            "loyal": 22,
        }.get(signal, 16)
    if _safe_int(snapshot.get("staff_total"), default=0) <= 0:
        score += 12
    if _safe_int(snapshot.get("unpaid_wages"), default=0) > 0:
        score += 18
    if _safe_int(snapshot.get("unpaid_upkeep"), default=0) > 0:
        score += 10
    score += min(14, abs(_safe_int(snapshot.get("last_footfall_delta_pct"), default=0)) // 2)
    score += min(14, abs(_safe_int(snapshot.get("last_churn_delta_pct"), default=0)) // 2)
    score += min(12, _safe_int(snapshot.get("last_reputation_awareness"), default=0) * 2)
    score += min(12, _safe_int(snapshot.get("direct_sale_count"), default=0) * 2)
    if _safe_int(snapshot.get("account_balance"), default=0) > 0:
        score += min(10, _safe_int(snapshot.get("account_balance"), default=0) // 25)
    return int(score)


def _actor_display_name(sim, actor_eid):
    try:
        actor_eid = int(actor_eid)
    except (TypeError, ValueError):
        return ""
    identity = sim.ecs.get(CreatureIdentity).get(actor_eid)
    if identity is not None:
        return _text(identity.display_name())
    ai = sim.ecs.get(AI).get(actor_eid)
    return _text(getattr(ai, "role", ""))


def _unique_ints(values):
    rows = []
    seen = set()
    for raw in tuple(values or ()):
        if raw is None:
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value in seen:
            continue
        seen.add(value)
        rows.append(value)
    return tuple(rows)


def _compact_dict(row):
    compact = {}
    for key, value in dict(row or {}).items():
        if value in (None, "", (), [], {}):
            continue
        compact[key] = value
    return compact


def _entity_echo_descriptor(sim, actor_eid, *, relation=""):
    try:
        actor_eid = int(actor_eid)
    except (TypeError, ValueError):
        return {}
    if sim is None:
        return {}
    identity = sim.ecs.get(CreatureIdentity).get(actor_eid)
    ai = sim.ecs.get(AI).get(actor_eid)
    occupation = sim.ecs.get(Occupation).get(actor_eid)
    descriptor = {"relation": _text(relation).lower()}
    if identity is not None:
        descriptor.update({
            "name": _display_ref_text(identity.display_name()),
            "common_name": _text(getattr(identity, "common_name", "")),
            "creature_type": _text(getattr(identity, "creature_type", "")).lower(),
            "taxonomy_class": _text(getattr(identity, "taxonomy_class", "")).lower(),
            "species": _text(getattr(identity, "species", "")).lower(),
        })
    elif ai is not None:
        descriptor["name"] = _text(getattr(ai, "role", ""))
    if ai is not None:
        descriptor["role"] = _text(getattr(ai, "role", "")).lower()
    if occupation is not None:
        descriptor["career"] = _text(getattr(occupation, "career", "")).lower()
        workplace = getattr(occupation, "workplace", None)
        if isinstance(workplace, dict):
            descriptor["workplace_name"] = (
                _text(workplace.get("business_name"))
                or _text(workplace.get("property_name"))
                or _text(workplace.get("store_name"))
            )
    return _compact_dict(descriptor)


def _incident_subject_descriptors(sim, incident):
    rows = []
    victim_eid = incident.get("victim_eid")
    victim = _entity_echo_descriptor(sim, victim_eid, relation="victim") if victim_eid is not None else {}
    victim_name = _display_ref_text(incident.get("victim_name"))
    if not victim and victim_name:
        victim = {"relation": "victim", "name": victim_name}
    elif victim_name and not _text(victim.get("name")):
        victim["name"] = victim_name
    if victim:
        rows.append(_compact_dict(victim))

    target_eid = incident.get("target_eid")
    if target_eid is not None and _safe_int(target_eid, default=-1) != _safe_int(victim_eid, default=-2):
        target = _entity_echo_descriptor(sim, target_eid, relation="target")
        target_name = _display_ref_text(incident.get("target_name"))
        if not target and target_name:
            target = {"relation": "target", "name": target_name}
        elif target_name and not _text(target.get("name")):
            target["name"] = target_name
        if target:
            rows.append(_compact_dict(target))
    return tuple(rows)


def _incident_observer_snapshot(sim, incident):
    observer_ids = set(_unique_ints(incident.get("observer_eids", ())))
    accountable_ids = set(_unique_ints(incident.get("accountable_observer_eids", ())))
    all_observers = tuple(sorted(observer_ids | accountable_ids))
    channels = tuple(sorted({
        _text(channel).lower()
        for channel in tuple(incident.get("observation_channels", ()) or ())
        if _text(channel)
    }))
    descriptors = []
    ordered = tuple(sorted(accountable_ids)) + tuple(eid for eid in all_observers if eid not in accountable_ids)
    seen = set()
    for observer_eid in ordered:
        if observer_eid in seen:
            continue
        seen.add(observer_eid)
        relation = "accountable_witness" if observer_eid in accountable_ids else "witness"
        descriptor = _entity_echo_descriptor(sim, observer_eid, relation=relation)
        if descriptor:
            descriptors.append(descriptor)
        if len(descriptors) >= 3:
            break
    return {
        "count": len(all_observers),
        "accountable_count": len(accountable_ids),
        "channels": channels,
        "descriptors": tuple(descriptors),
    }


def _footprint_profile(prop):
    if not isinstance(prop, dict):
        return {}
    metadata = _property_metadata(prop)
    footprint = metadata.get("footprint")
    if not isinstance(footprint, dict):
        return {}
    try:
        left = int(footprint.get("left"))
        right = int(footprint.get("right"))
        top = int(footprint.get("top"))
        bottom = int(footprint.get("bottom"))
    except (TypeError, ValueError):
        return {}
    width = max(1, right - left + 1)
    height = max(1, bottom - top + 1)
    return {
        "shape": "rectangle",
        "width": int(width),
        "height": int(height),
        "area": int(width * height),
        "floors": max(1, _safe_int(metadata.get("floors"), default=1)),
        "basement_levels": max(0, _safe_int(metadata.get("basement_levels"), default=0)),
    }


def _band_for_offset(offset, length):
    try:
        offset = int(offset)
        length = max(1, int(length))
    except (TypeError, ValueError):
        return ""
    if length <= 2:
        return "center"
    third = length / 3.0
    if offset < third:
        return "near_edge"
    if offset >= third * 2:
        return "far_edge"
    return "center"


def _scene_position_profile(prop, incident):
    if not isinstance(prop, dict):
        return {}
    metadata = _property_metadata(prop)
    footprint = metadata.get("footprint")
    if not isinstance(footprint, dict):
        return {}
    try:
        x = int(incident.get("x"))
        y = int(incident.get("y"))
        z = int(incident.get("z", 0))
        left = int(footprint.get("left"))
        right = int(footprint.get("right"))
        top = int(footprint.get("top"))
        bottom = int(footprint.get("bottom"))
        base_z = int(prop.get("z", 0))
    except (TypeError, ValueError):
        return {}
    if not (left <= x <= right and top <= y <= bottom):
        return {}
    width = max(1, right - left + 1)
    height = max(1, bottom - top + 1)
    x_offset = x - left
    y_offset = y - top
    return {
        "x_offset": int(x_offset),
        "y_offset": int(y_offset),
        "z_offset": int(z - base_z),
        "x_band": _band_for_offset(x_offset, width),
        "y_band": _band_for_offset(y_offset, height),
    }


def _structure_scene_profile(sim, incident):
    try:
        x = int(incident.get("x"))
        y = int(incident.get("y"))
        z = int(incident.get("z", 0))
    except (TypeError, ValueError):
        return {}
    if sim is None or not hasattr(sim, "structure_at"):
        return {}
    try:
        info = sim.structure_at(x, y, z)
    except Exception:
        return {}
    if not isinstance(info, dict):
        return {}
    allowed = (
        "room_kind",
        "common_area_kind",
        "aperture_kind",
        "ingress_kind",
        "span_kind",
        "site_kind",
    )
    return _compact_dict({
        key: _text(info.get(key)).lower()
        for key in allowed
        if _text(info.get(key))
    })


def _incident_scene_snapshot(sim, incident, prop_ctx, *, subjects=(), observers=None):
    prop = prop_ctx.get("prop") if isinstance(prop_ctx, dict) else None
    place = _compact_dict({
        "name": _display_ref_text((prop_ctx or {}).get("property_name")),
        "archetype": _text((prop_ctx or {}).get("property_archetype")).lower(),
        "property_kind": _text((prop_ctx or {}).get("property_kind")).lower(),
        "organization_name": _text((prop_ctx or {}).get("organization_name")),
        "footprint": _footprint_profile(prop),
    })
    structure = _structure_scene_profile(sim, incident)
    position = _scene_position_profile(prop, incident)
    scene = _compact_dict({
        "place": place,
        "structure": structure,
        "position": position,
        "kind": _text(incident.get("kind")).lower(),
        "kind_label": incident_kind_label(
            _text(incident.get("kind")).lower() or "incident",
            action=incident.get("action"),
            context=incident.get("context"),
            tags=incident.get("tags", ()),
        ),
    })
    scene["scene_stamp"] = _stable_stamp(
        "scene",
        scene.get("kind"),
        scene.get("kind_label"),
        place,
        structure,
        position,
        tuple(subjects or ()),
        {
            "observer_count": _safe_int((observers or {}).get("count"), default=0),
            "accountable_count": _safe_int((observers or {}).get("accountable_count"), default=0),
            "channels": tuple((observers or {}).get("channels", ()) or ()),
        },
    )
    return scene


def _business_staff_snapshot(sim, state, *, limit=3):
    if not isinstance(state, dict):
        return ()
    roles = state.get("staff_roles")
    roles = roles if isinstance(roles, dict) else {}
    rows = []
    for raw_eid in tuple(state.get("staff_roster", ()) or ()):
        actor_eid = _safe_int(raw_eid, default=0)
        if actor_eid <= 0:
            continue
        name = _actor_display_name(sim, actor_eid)
        if not name:
            continue
        role = _text(roles.get(str(actor_eid))).lower() or "staff"
        occupation = sim.ecs.get(Occupation).get(actor_eid)
        career = _text(getattr(occupation, "career", "")) or role
        rows.append({
            "name": name,
            "role": role,
            "career": career,
        })
        if len(rows) >= int(limit):
            break
    return tuple(rows)


def _business_echo_line(record, *, mode="summary"):
    owner_name = _text(record.get("owner_name")) or "the prior owner"
    business_name = _text(record.get("business_name")) or _text(record.get("property_name")) or "a business"
    cue = _text(record.get("player_business_cue"))
    reason = _text(record.get("owner_signal_reason"))
    note = _text(record.get("business_note"))
    if mode == "bulletin":
        detail = reason or cue or note or "old owner choices still color the storefront"
        staff_rows = tuple(row for row in tuple(record.get("staff_rows", ()) or ()) if isinstance(row, dict))
        if staff_rows:
            names = ", ".join(_text(row.get("name")) for row in staff_rows[:2] if _text(row.get("name")))
            if names:
                detail = f"{detail} Former staff still named in the talk: {names}"
        return f"A note about {business_name} still points back to {owner_name}: {detail}."
    if mode == "rumor":
        if cue:
            return f"People still talk about {business_name} running {cue} under {owner_name}."
        return f"People still bring up how {business_name} ran under {owner_name}."
    if cue:
        return f"{owner_name}'s {business_name} stayed {cue}."
    if note:
        return f"{owner_name}'s {business_name} left a {note} read behind."
    return f"{owner_name}'s {business_name} stayed in local business talk."


def _dedupe_business_echo_records(records):
    unique = []
    seen = set()
    for record in tuple(records or ()):
        if not isinstance(record, dict):
            continue
        key = _text(record.get("property_id")) or _text(record.get("business_name")).casefold()
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        unique.append(record)
    return tuple(unique)


def _incident_echo_summary_key(record):
    summary = " ".join(_text((record or {}).get("summary")).split()).casefold()
    if summary:
        return summary
    return _text((record or {}).get("echo_id")).casefold()


def _dedupe_incident_echo_records(records):
    unique = []
    seen = set()
    for record in tuple(records or ()):
        if not isinstance(record, dict):
            continue
        key = _incident_echo_summary_key(record)
        if key and key in seen:
            continue
        if key:
            seen.add(key)
        unique.append(record)
    return tuple(unique)


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
        "property_kind": _text((prop or {}).get("kind")),
        "property_archetype": property_archetype,
        "organization_name": organization_name,
        "prop": prop,
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
        subjects = _incident_subject_descriptors(sim, incident)
        observers = _incident_observer_snapshot(sim, incident)
        scene = _incident_scene_snapshot(sim, incident, prop_ctx, subjects=subjects, observers=observers)
        caution_bias = max(4, min(12, int(round(float(score) / 22.0))))
        incident_kind = _text(incident.get("kind")).lower() or "incident"
        action = _text(incident.get("action")).lower()
        context = _text(incident.get("context")).lower()
        tags = tuple(
            _text(tag).lower()
            for tag in tuple(incident.get("tags", ()) or ())
            if _text(tag)
        )
        observed_tick = _safe_int(
            incident.get("last_observed_tick"),
            default=_safe_int(getattr(sim, "tick", 0), default=0),
        )
        echo_id = _stable_stamp(
            "incident",
            scene,
            incident_kind,
            action,
            context,
            tags,
            _safe_int(incident.get("severity"), default=0),
            observed_tick,
            _text(outcome).lower(),
        )
        record = {
            "echo_id": echo_id,
            "family": "incident_echo",
            "incident_kind": incident_kind,
            "action": action,
            "context": context,
            "tags": tags,
            "kind_label": incident_kind_label(
                incident_kind,
                action=action,
                context=context,
                tags=tags,
            ),
            "summary": "",
            "bulletin_text": "",
            "rumor_text": "",
            "severity": _safe_int(incident.get("severity"), default=0),
            "officially_reported": bool(incident.get("officially_reported") or incident.get("justice_accounted")),
            "propagation_depth": max(
                _safe_int(incident.get("current_propagation"), default=0),
                _safe_int(incident.get("max_propagation"), default=0),
            ),
            "victim_name": _display_ref_text(incident.get("victim_name")),
            "subject_name": _display_ref_text(incident.get("victim_name")) or _display_ref_text(incident.get("property_name")),
            "subjects": subjects,
            "observers": observers,
            "observer_count": _safe_int(observers.get("count"), default=0),
            "accountable_observer_count": _safe_int(observers.get("accountable_count"), default=0),
            "observation_channels": tuple(observers.get("channels", ()) or ()),
            "scene": scene,
            "scene_stamp": _text(scene.get("scene_stamp")),
            "property_name": prop_ctx["property_name"],
            "property_archetype": prop_ctx["property_archetype"],
            "organization_name": prop_ctx["organization_name"],
            "run_outcome": _text(outcome).lower(),
            "tick": observed_tick,
            "caution_bias": caution_bias,
            **area,
        }
        record["summary"] = _incident_summary_text(record)
        record["bulletin_text"] = _incident_bulletin_text(record)
        record["rumor_text"] = _incident_rumor_text(record)
        records.append(record)
    return records


def _build_business_echo_records(sim, player_eid, *, outcome=""):
    if sim is None or player_eid is None:
        return []
    try:
        from game.player_businesses import player_business_state, player_business_status_snapshot
    except Exception:
        return []

    ranked = []
    owner_name = _player_business_owner_name(sim)
    for prop in tuple(getattr(sim, "properties", {}).values()):
        if not isinstance(prop, dict) or not _property_owned_by_player(sim, prop, player_eid):
            continue
        snapshot = player_business_status_snapshot(sim, prop)
        if not isinstance(snapshot, dict):
            continue
        state = player_business_state(prop, create=False)
        score = _business_echo_score(snapshot)
        if score < 24:
            continue
        ranked.append((score, _text(prop.get("id")), prop, snapshot))

    ranked.sort(key=lambda row: (row[0], row[1]), reverse=True)
    records = []
    for score, _property_id, prop, snapshot in ranked[:RUN_ECHOES_MAX_BUSINESSES_PER_RUN]:
        x = prop.get("x")
        y = prop.get("y")
        chunk_key = None
        if x is not None and y is not None:
            try:
                chunk_key = sim.chunk_coords(int(x), int(y))
            except Exception:
                chunk_key = None
        area = _record_area_profile(sim, chunk_key)
        metadata = _property_metadata(prop)
        property_archetype = _text(metadata.get("archetype", prop.get("kind"))).lower()
        organization_name = _text(metadata.get("organization_name")) or _text(metadata.get("business_name"))
        record = {
            "echo_id": f"business:{getattr(sim, 'seed', 'seed')}:{_text(prop.get('id'))}:{_safe_int(getattr(sim, 'tick', 0), default=0)}",
            "family": "business_echo",
            "summary": "",
            "bulletin_text": "",
            "rumor_text": "",
            "property_id": _text(prop.get("id")),
            "property_name": _text(prop.get("name")),
            "property_archetype": property_archetype,
            "organization_name": organization_name,
            "business_name": _text(snapshot.get("business_name")) or _text(metadata.get("business_name")) or _text(prop.get("name")),
            "owner_name": owner_name,
            "player_business_cue": _text(snapshot.get("player_business_cue")),
            "owner_signal_kind": _text(snapshot.get("owner_signal_kind")),
            "owner_signal_reason": _text(snapshot.get("owner_signal_reason")),
            "business_note": _text(snapshot.get("note")),
            "staff_rows": _business_staff_snapshot(sim, state),
            "customer_policy": _text(snapshot.get("customer_policy")),
            "hours_mode": _text(snapshot.get("hours_mode")),
            "markup_mode": _text(snapshot.get("markup_mode")),
            "staff_total": _safe_int(snapshot.get("staff_total"), default=0),
            "required_staff": _safe_int(snapshot.get("required_staff"), default=0),
            "account_balance": _safe_int(snapshot.get("account_balance"), default=0),
            "run_outcome": _text(outcome).lower(),
            "tick": _safe_int(getattr(sim, "tick", 0), default=0),
            "caution_bias": max(2, min(10, int(round(float(score) / 18.0)))),
            **area,
        }
        record["summary"] = _business_echo_line(record, mode="summary")
        record["bulletin_text"] = _business_echo_line(record, mode="bulletin")
        record["rumor_text"] = _business_echo_line(record, mode="rumor")
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
    from game.tutorial import tutorial_no_persistence

    if tutorial_no_persistence(sim):
        return {
            "lines": ["Tutorial run: no run echoes were archived."],
            "records": [],
        }
    from engine.persistence import append_run_echo_record

    runtime = prime_run_echoes_runtime(sim)
    archive_path = runtime.get("archive_path")
    incident_records_to_archive = _dedupe_incident_echo_records(_build_incident_echo_records(sim, outcome=outcome))
    business_records_to_archive = _dedupe_business_echo_records(_build_business_echo_records(sim, player_eid, outcome=outcome))
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
    for record in [
        *incident_records_to_archive[:RUN_ECHOES_MAX_INCIDENTS_PER_RUN],
        *business_records_to_archive[:RUN_ECHOES_MAX_BUSINESSES_PER_RUN],
        *remnant_records[:RUN_ECHOES_MAX_REMNANTS_PER_RUN],
    ]:
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
        lines.append(_incident_echo_epilogue_line(strongest, strongest=True))
        for record in incident_records_to_archive[1:]:
            lines.append(_incident_echo_epilogue_line(record))
    for record in business_records_to_archive:
        lines.append(f"  Business echo: {_text(record.get('summary'))}")
    if remnant_records:
        lines.append(f"  Remnant echo: {_text(remnant_records[0].get('summary'))}")
    if not incident_records_to_archive and not business_records_to_archive and not remnant_records:
        lines.append("  Nothing strong enough will echo forward this time.")
    lines.append(
        "  Failed-run bones: "
        + ("a separate grave and stash record were archived." if bones_archived else "no failed-run bones were archived.")
    )
    return {
        "records": tuple(archived),
        "lines": tuple(lines),
        "incident_records": tuple(incident_records_to_archive),
        "business_records": tuple(business_records_to_archive),
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
    runtime["spawn_counts"].setdefault("incident_echo", 0)
    runtime["spawn_counts"].setdefault("business_echo", 0)
    runtime["spawn_counts"].setdefault("remnant_echo", 0)
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
        "run_echo_scene_stamp": _text(record.get("scene_stamp")),
        "run_echo_scene": dict(record.get("scene") or {}) if isinstance(record.get("scene"), dict) else {},
        "run_echo_subjects": tuple(record.get("subjects", ()) or ()),
        "run_echo_observers": dict(record.get("observers") or {}) if isinstance(record.get("observers"), dict) else {},
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
        "scene_stamp": _text(metadata.get("run_echo_scene_stamp")),
        "scene": dict(metadata.get("run_echo_scene") or {}),
        "subjects": tuple(metadata.get("run_echo_subjects", ()) or ()),
        "observers": dict(metadata.get("run_echo_observers") or {}),
        "summary": _text(record.get("summary")),
        "rumor_text": _text(record.get("rumor_text")),
        "caution_bias": _safe_int(record.get("caution_bias"), default=0),
    }


def _business_notice_name(record):
    business_name = _text(record.get("business_name")) or _text(record.get("property_name"))
    if business_name:
        return f"{business_name} Callback"
    return "Old Business Notice"


def _spawn_business_echo_staff_actor(sim, chunk_key, record, rng, *, target_prop=None):
    staff_rows = [row for row in tuple(record.get("staff_rows", ()) or ()) if isinstance(row, dict)]
    if not staff_rows:
        return None
    anchor = _pick_chunk_open_tile(sim, chunk_key, rng)
    if anchor is None:
        return None
    staff = rng.choice(staff_rows)
    name = _text(staff.get("name")) or "former staffer"
    role = _text(staff.get("role")).lower() or "staff"
    career = _text(staff.get("career")) or ("manager" if role == "manager" else "worker")
    workplace = {
        "property_id": _text((target_prop or {}).get("id")) or _text(record.get("property_id")),
        "business_name": _text(record.get("business_name")),
        "prior_business_name": _text(record.get("business_name")),
        "prior_owner_name": _text(record.get("owner_name")),
        "run_echo_id": _text(record.get("echo_id")),
        "run_echo_family": "business_echo",
        "former_role": role,
    }
    eid = sim.ecs.create()
    pos = Position(anchor[0], anchor[1], anchor[2])
    for component in (
        pos,
        Render("w", color="npc", semantic_id="human", priority=2),
        CreatureIdentity(
            taxonomy_class="hominid",
            species="homo sapiens",
            creature_type="human",
            common_name="former staff",
            personal_name=name,
        ),
        AI("worker"),
        Collider(blocks=True),
        Occupation(career=career, workplace=workplace),
        NPCNeeds(energy=78, safety=70, social=72),
        NPCTraits(bravery=0.48, empathy=0.58, loyalty=0.62, discipline=0.56),
        NPCWill(),
        NPCSocial(),
        Vitality(max_hp=72),
    ):
        sim.ecs.add(eid, component)
    sim.tilemap.add_entity(eid, pos.x, pos.y, pos.z)
    return {
        "eid": eid,
        "name": name,
        "role": role,
        "career": career,
        "x": pos.x,
        "y": pos.y,
        "z": pos.z,
    }


def _seed_business_notice(sim, chunk_key, record, rng):
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
        "container_label": "Business Notice",
        "container_note_text": _text(record.get("bulletin_text")),
        "run_echo_id": _text(record.get("echo_id")),
        "run_echo_family": "business_echo",
        "run_echo_summary": _text(record.get("summary")),
        "run_echo_rumor_text": _text(record.get("rumor_text")),
        "run_echo_caution_bias": _safe_int(record.get("caution_bias"), default=0),
        "run_echo_target_property_id": _text((target_prop or {}).get("id")) or _text(record.get("property_id")),
        "run_echo_target_archetype": _text(record.get("property_archetype")).lower(),
        "run_echo_organization_name": _text(record.get("organization_name")),
        "run_echo_business_name": _text(record.get("business_name")),
        "run_echo_owner_name": _text(record.get("owner_name")),
    }
    prop_id = sim.register_property(
        _business_notice_name(record),
        "fixture",
        anchor[0],
        anchor[1],
        anchor[2],
        owner_tag="public",
        metadata=metadata,
    )
    _append_chunk_property_record(sim, chunk_key, prop_id, "fixture", anchor[0], anchor[1], anchor[2], "run_echo_notice")
    staff_spawn = _spawn_business_echo_staff_actor(sim, chunk_key, record, rng, target_prop=target_prop)
    return {
        "echo_id": _text(record.get("echo_id")),
        "family": "business_echo",
        "spawn_property_id": prop_id,
        "spawn_actor_eid": (staff_spawn or {}).get("eid"),
        "spawn_actor_name": _text((staff_spawn or {}).get("name")),
        "target_property_id": _text(metadata.get("run_echo_target_property_id")),
        "target_archetype": _text(metadata.get("run_echo_target_archetype")),
        "organization_name": _text(metadata.get("run_echo_organization_name")),
        "business_name": _text(record.get("business_name")),
        "owner_name": _text(record.get("owner_name")),
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
    from game.tutorial import tutorial_no_persistence

    if tutorial_no_persistence(sim):
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
    spawn_counts = runtime.setdefault("spawn_counts", {"incident_echo": 0, "business_echo": 0, "remnant_echo": 0})
    spawn_counts.setdefault("incident_echo", 0)
    spawn_counts.setdefault("business_echo", 0)
    spawn_counts.setdefault("remnant_echo", 0)
    rng = random.Random(f"{getattr(sim, 'seed', 'seed')}:run_echo:{chunk_key[0]}:{chunk_key[1]}")
    if not force and rng.random() > RUN_ECHOES_SPAWN_CHANCE:
        return None

    active_rows = []
    chunk_data = sim.world.get_chunk(chunk_key[0], chunk_key[1]) if getattr(sim, "world", None) is not None else {}
    for family, limit, seeder in (
        ("incident_echo", RUN_ECHOES_MAX_INCIDENT_SPAWNS_PER_RUN, _seed_incident_notice),
        ("business_echo", RUN_ECHOES_MAX_BUSINESS_SPAWNS_PER_RUN, _seed_business_notice),
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
