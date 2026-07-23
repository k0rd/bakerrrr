"""Wire data extraction and broker sale helpers."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping

from engine.events import Event
from game.components import (
    AI,
    ContactLedger,
    CreatureIdentity,
    Inventory,
    NPCSettlement,
    Occupation,
    PlayerAssets,
    Position,
)
from game.items import ITEM_CATALOG
from game.knowledge_notebook import note_person_notebook_mutation
from game.wire_consequences import wire_network_key, wire_network_property, wire_security_reset_delay
from game.wire_kit import wire_kit_add_entry, wire_kit_can_accept_entry, wire_kit_remove_entry, wire_state_for_actor
from game.wire_runtime import normalize_wire_entry_metadata, wire_entry_display_name, wire_profile_for_item


WIRE_DATA_SCHEMA_VERSION = 1
WIRE_DATA_ITEM_ID = "wire_data_cache"
WIRE_DATA_FAMILIES = (
    "payroll",
    "rota",
    "procurement",
    "customer_habits",
    "camera_fragment",
    "personal_records",
    "blackmail",
    "drone_mod_plan",
    "electronics_schematic",
    "software_source",
    "prototype_telemetry",
    "general",
)

_FAMILY_LABELS = {
    "payroll": "Payroll cache",
    "rota": "Rota cache",
    "procurement": "Procurement cache",
    "customer_habits": "Customer-habits cache",
    "camera_fragment": "Camera-fragment cache",
    "personal_records": "Personal-records cache",
    "blackmail": "Blackmail cache",
    "drone_mod_plan": "Drone modification plan",
    "electronics_schematic": "Electronics schematic",
    "software_source": "Software source package",
    "prototype_telemetry": "Prototype-telemetry cache",
    "general": "General data cache",
}

_FAMILY_BUYER_TAGS = {
    "payroll": ("finance_broker", "corporate_rival"),
    "rota": ("finance_broker", "civic_buyer", "illicit_buyer"),
    "procurement": ("finance_broker", "corporate_rival", "civic_buyer"),
    "customer_habits": ("corporate_rival", "illicit_buyer"),
    "camera_fragment": ("media_buyer", "civic_buyer", "illicit_buyer"),
    "personal_records": ("finance_broker", "media_buyer", "civic_buyer", "illicit_buyer"),
    "blackmail": ("media_buyer", "illicit_buyer"),
    "drone_mod_plan": ("corporate_rival", "tech_buyer"),
    "electronics_schematic": ("corporate_rival", "tech_buyer", "illicit_buyer"),
    "software_source": ("corporate_rival", "tech_buyer", "illicit_buyer"),
    "prototype_telemetry": ("corporate_rival", "tech_buyer"),
    "general": ("illicit_buyer",),
}

_SENSITIVITY_BY_FAMILY = {
    "payroll": 2,
    "rota": 1,
    "procurement": 2,
    "customer_habits": 2,
    "camera_fragment": 3,
    "personal_records": 3,
    "blackmail": 4,
    "drone_mod_plan": 4,
    "electronics_schematic": 3,
    "software_source": 4,
    "prototype_telemetry": 4,
    "general": 1,
}

_PERSONAL_RECORD_RELATION_WEIGHT = {
    "owner": 96,
    "manager": 92,
    "guard": 66,
    "employee": 76,
    "organization_member": 70,
    "resident": 52,
    "customer": 58,
    "visitor": 46,
    "local": 30,
}

_SUBJECT_VALUE_BY_RELATION = {
    "owner": 5,
    "manager": 4,
    "guard": 3,
    "organization_member": 3,
    "employee": 2,
    "customer": 2,
    "resident": 2,
    "visitor": 1,
    "local": 1,
}

_BROKER_PROFILES = {
    "finance": {
        "buyer_kind": "finance_broker",
        "buyer_tags": ("finance_broker",),
        "preferred": ("payroll", "procurement"),
        "adjacent": ("rota", "customer_habits", "prototype_telemetry"),
    },
    "corp_tech": {
        "buyer_kind": "corporate_tech_buyer",
        "buyer_tags": ("corporate_rival", "tech_buyer"),
        "preferred": ("prototype_telemetry", "drone_mod_plan", "electronics_schematic", "software_source", "procurement", "customer_habits"),
        "adjacent": ("payroll", "rota"),
    },
    "media_civic": {
        "buyer_kind": "media_civic_buyer",
        "buyer_tags": ("media_buyer", "civic_buyer"),
        "preferred": ("camera_fragment", "blackmail", "procurement"),
        "adjacent": ("payroll", "rota", "customer_habits", "personal_records"),
    },
    "illicit": {
        "buyer_kind": "illicit_data_buyer",
        "buyer_tags": ("illicit_buyer",),
        "preferred": ("blackmail", "personal_records", "customer_habits", "camera_fragment"),
        "adjacent": ("payroll", "rota", "procurement", "prototype_telemetry", "general"),
    },
}


def _text(value, default=""):
    text = str(value or "").strip()
    return text if text else str(default or "").strip()


def _key(value, default=""):
    return _text(value, default).lower()


def _int(value, default=0, *, minimum=None, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = int(default)
    if minimum is not None:
        number = max(int(minimum), number)
    if maximum is not None:
        number = min(int(maximum), number)
    return int(number)


def _string_tuple(values):
    if values is None:
        return ()
    if isinstance(values, str):
        values = (values,)
    if not isinstance(values, (list, tuple, set, frozenset)):
        return ()
    out = []
    for value in values:
        text = _key(value)
        if text:
            out.append(text)
    return tuple(dict.fromkeys(out))


def _prop_metadata(prop, *, create=False):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    if not isinstance(metadata, dict):
        if not create:
            return {}
        metadata = {}
        prop["metadata"] = metadata
    return metadata


def _stable_index(parts, count):
    if count <= 0:
        return 0
    digest = hashlib.sha256(":".join(str(part or "") for part in parts).encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % int(count)


def _source_archetype(scene, prop):
    metadata = _prop_metadata(prop)
    return _key(
        metadata.get("archetype")
        or metadata.get("service_archetype")
        or (scene or {}).get("source_archetype")
        or (scene or {}).get("target_class"),
        "general",
    )


def _source_org(prop):
    metadata = _prop_metadata(prop)
    org_key = _key(
        prop.get("organization_key")
        or prop.get("owner_org_key")
        or prop.get("root_organization_key")
        or metadata.get("organization_key")
        or metadata.get("owner_org_key")
        or metadata.get("root_organization_key")
    )
    org_name = _text(
        prop.get("organization_name")
        or prop.get("owner_org_name")
        or prop.get("root_organization_name")
        or metadata.get("organization_name")
        or metadata.get("owner_org_name")
        or metadata.get("root_organization_name")
    )
    return org_key, org_name


def _person_identity_snapshot(sim, eid):
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    ai = sim.ecs.get(AI).get(eid)
    if identity is None:
        return None
    creature_type = _key(getattr(identity, "creature_type", ""))
    taxonomy = _key(getattr(identity, "taxonomy_class", ""))
    if creature_type != "human" and taxonomy != "hominid":
        return None
    role = _key(getattr(ai, "role", "")) if ai is not None else ""
    if role == "wildlife":
        return None
    remember = getattr(sim, "remember_entity_identity", None)
    record = remember(eid, reason="wire_data_subject") if callable(remember) else None
    if not isinstance(record, Mapping):
        resolver = getattr(sim, "entity_identity_record", None)
        record = resolver(eid) if callable(resolver) else None
    if not isinstance(record, Mapping):
        return None
    snapshot = {
        key: record.get(key)
        for key in ("eid", "display_name", "personal_name", "common_name", "role", "pronoun_set")
        if record.get(key) not in (None, "")
    }
    name = _text(snapshot.get("personal_name") or snapshot.get("display_name"))
    if not name:
        return None
    snapshot["eid"] = _int(eid, 0)
    snapshot["display_name"] = name
    return snapshot


def _subject_membership_rows(sim, eid):
    try:
        from game.organizations import actor_org_memberships

        return tuple(actor_org_memberships(sim, eid, active_only=True) or ())
    except (ImportError, TypeError, ValueError):
        return ()


def _source_property_member_rows(sim, prop):
    try:
        from game.organizations import property_org_members

        return tuple(property_org_members(sim, prop) or ())
    except (ImportError, TypeError, ValueError):
        return ()


def _subject_relation_for_candidate(sim, eid, prop, *, member_row=None, source_org_key=""):
    prop_id = _text((prop or {}).get("id"))
    if (prop or {}).get("owner_eid") is not None:
        try:
            if int((prop or {}).get("owner_eid")) == int(eid):
                return "owner", "", source_org_key, _text((prop or {}).get("organization_name"))
        except (TypeError, ValueError):
            pass

    member_row = member_row if isinstance(member_row, Mapping) else {}
    role = _key(member_row.get("role"))
    title = _text(member_row.get("title"))
    if role in {"owner", "proprietor"}:
        relation = "owner"
    elif role in {"manager", "supervisor", "director", "executive", "officer"}:
        relation = "manager"
    elif role in {"guard", "security", "enforcer", "watch"}:
        relation = "guard"
    elif member_row:
        relation = "employee" if _key(member_row.get("kind")) in {"employment", "ownership"} or role in {"staff", "worker", "employee"} else "organization_member"
    else:
        relation = ""

    occupation = sim.ecs.get(Occupation).get(eid)
    settlement = sim.ecs.get(NPCSettlement).get(eid)
    career = _text(getattr(occupation, "career", "")) if occupation is not None else ""
    if not relation and settlement is not None and _text(getattr(settlement, "work_property_id", "")) == prop_id:
        relation = "employee"

    matched_org_key = _key(member_row.get("organization_key"))
    matched_org_name = _text(member_row.get("organization_name"))
    if source_org_key and not matched_org_key:
        for membership in _subject_membership_rows(sim, eid):
            if _key(membership.get("organization_key")) != source_org_key:
                continue
            matched_org_key = source_org_key
            matched_org_name = _text(membership.get("organization_name"))
            title = title or _text(membership.get("title"))
            if not relation:
                relation = "organization_member"
            break

    pos = sim.ecs.get(Position).get(eid)
    inside_source = False
    if pos is not None:
        covering = sim.property_covering(pos.x, pos.y, pos.z) if hasattr(sim, "property_covering") else None
        inside_source = isinstance(covering, Mapping) and _text(covering.get("id")) == prop_id
    if not relation and settlement is not None and _text(getattr(settlement, "home_property_id", "")) == prop_id:
        relation = "resident"
    if not relation and inside_source:
        relation = "visitor"
    if not relation:
        relation = "local"
    return relation, title or career, matched_org_key, matched_org_name


def choose_wire_data_subject(sim, scene, prop, family):
    """Choose a real, plausibly recorded person for a siphoned data packet."""
    if sim is None or not isinstance(prop, Mapping):
        return None
    source_org_key, source_org_name = _source_org(prop)
    source_x = _int(prop.get("x"), 0)
    source_y = _int(prop.get("y"), 0)
    source_z = _int(prop.get("z"), 0)
    try:
        player_eid = int(getattr(sim, "player_eid", -1))
    except (TypeError, ValueError):
        player_eid = -1

    member_rows = {}
    candidate_eids = set()
    for row in _source_property_member_rows(sim, prop):
        try:
            eid = int(row.get("eid"))
        except (TypeError, ValueError, AttributeError):
            continue
        member_rows[eid] = dict(row)
        candidate_eids.add(eid)
    owner_eid = prop.get("owner_eid")
    try:
        if owner_eid is not None:
            candidate_eids.add(int(owner_eid))
    except (TypeError, ValueError):
        pass

    local_radius = max(16, min(48, int(getattr(sim, "chunk_size", 16) or 16) * 2))
    nearby = getattr(sim, "entity_ids_in_radius", None)
    if callable(nearby):
        candidate_eids.update(nearby(source_x, source_y, source_z, local_radius))
    else:
        candidate_eids.update(sim.ecs.get(Position).keys())

    weights = _PERSONAL_RECORD_RELATION_WEIGHT
    candidates = []
    for eid in sorted(candidate_eids):
        if int(eid) == player_eid:
            continue
        identity = _person_identity_snapshot(sim, eid)
        if not identity:
            continue
        pos = sim.ecs.get(Position).get(eid)
        distance = local_radius + 1
        if pos is not None:
            if int(getattr(pos, "z", source_z)) == source_z:
                distance = abs(int(pos.x) - source_x) + abs(int(pos.y) - source_y)
        relation, title, subject_org_key, subject_org_name = _subject_relation_for_candidate(
            sim,
            eid,
            prop,
            member_row=member_rows.get(eid),
            source_org_key=source_org_key,
        )
        proximity_bonus = max(0, 28 - min(28, int(distance)))
        if relation in {"owner", "manager", "employee", "guard", "organization_member"}:
            proximity_bonus //= 3
        score = int(weights.get(relation, 0)) + int(proximity_bonus)
        role = _key(identity.get("role"))
        career = _key(getattr(sim.ecs.get(Occupation).get(eid), "career", ""))
        if _key(family) == "blackmail" and any(token in f"{role} {career}" for token in ("executive", "director", "manager", "politician", "officer")):
            score += 14
        subject_value = int(_SUBJECT_VALUE_BY_RELATION.get(relation, 1))
        if any(token in f"{role} {career}" for token in ("executive", "director", "chief", "manager", "owner")):
            subject_value = max(subject_value, 4)
        candidates.append({
            "subject_kind": "person",
            "subject_eid": int(eid),
            "subject_name": _text(identity.get("display_name")),
            "subject_role": role or career or _key(identity.get("common_name"), "person"),
            "subject_title": title,
            "subject_relation": relation,
            "subject_org_key": subject_org_key or source_org_key,
            "subject_org_name": subject_org_name or source_org_name,
            "subject_value": max(1, min(5, subject_value)),
            "subject_identity": dict(identity),
            "subject_distance_at_capture": int(distance) if distance <= local_radius else None,
            "score": int(score),
        })
    if not candidates:
        return None
    best_score = max(int(row.get("score", 0)) for row in candidates)
    top_band = [row for row in candidates if int(row.get("score", 0)) >= best_score - 8]
    chosen = dict(top_band[_stable_index((getattr(sim, "seed", 0), (scene or {}).get("scene_id"), prop.get("id"), family, "subject"), len(top_band))])
    chosen.pop("score", None)
    return chosen


def _technical_data_subject(sim, scene, prop, family):
    family = _key(family)
    if family == "drone_mod_plan":
        target_kind = "drone_module"
        candidates = [
            (item_id, item)
            for item_id, item in ITEM_CATALOG.items()
            if isinstance(item, Mapping)
            and _key((item.get("drone_profile") or {}).get("kind")) == "module"
        ]
    elif family == "software_source":
        target_kind = "wire_program"
        candidates = [
            (item_id, item)
            for item_id, item in ITEM_CATALOG.items()
            if isinstance(item, Mapping)
            and _key((item.get("wire_profile") or {}).get("kind")) == "program"
        ]
    else:
        target_kind = "wire_interface"
        candidates = [
            (item_id, item)
            for item_id, item in ITEM_CATALOG.items()
            if isinstance(item, Mapping)
            and bool((item.get("wire_interface_profile") or {}).get("kind"))
        ]
    candidates.sort(key=lambda row: str(row[0]))
    if not candidates:
        return None
    index = _stable_index(
        (getattr(sim, "seed", 0), (scene or {}).get("scene_id"), (prop or {}).get("id"), family, "technical_target"),
        len(candidates),
    )
    target_id, target_item = candidates[index]
    target_name = _text(target_item.get("name"), str(target_id).replace("_", " ").title())
    if target_kind == "drone_module":
        profile = dict(target_item.get("drone_profile") or {})
        if _int(profile.get("sensor_range"), 0) > 0:
            effect_key = "sensor_range"
            effect_delta = 2
            effect_label = "extends sensor range by 2"
        elif _int(profile.get("active_draw"), 0) > 0:
            effect_key = "active_draw"
            effect_delta = -1
            effect_label = "reduces active power draw by 1"
        else:
            effect_key = "weight"
            effect_delta = -1
            effect_label = "reduces module weight by 1"
        subject_kind = "design"
    elif target_kind == "wire_program":
        profile = dict(target_item.get("wire_profile") or {})
        effect_options = []
        if _int(profile.get("trace_cost"), 0) > 0:
            effect_options.append(("trace_cost", -1, "reduces trace cost by 1"))
        if _int(profile.get("noise"), 0) > 0:
            effect_options.append(("noise", -1, "reduces program noise by 1"))
        if _int(profile.get("reload_ticks"), 0) > 0:
            effect_options.append(("reload_ticks", -1, "reduces reload time by 1 tick"))
        effect_options.append(("durability_max", 1, "adds 1 durability"))
        effect_key, effect_delta, effect_label = effect_options[
            _stable_index((target_id, (prop or {}).get("id"), "software_effect"), len(effect_options))
        ]
        subject_kind = "software"
    else:
        profile = dict(target_item.get("wire_interface_profile") or {})
        effect_options = [("buffer_size", 2, "adds 2 buffer capacity")]
        if _int(profile.get("trace_resistance"), 0) < 5:
            effect_options.append(("trace_resistance", 1, "adds 1 trace resistance"))
        if _int(profile.get("noise_floor"), 0) > 0:
            effect_options.append(("noise_floor", -1, "reduces interface noise floor by 1"))
        if _int(profile.get("warning_rating"), 0) < 5:
            effect_options.append(("warning_rating", 1, "adds 1 warning rating"))
        effect_key, effect_delta, effect_label = effect_options[
            _stable_index((target_id, (prop or {}).get("id"), "interface_effect"), len(effect_options))
        ]
        subject_kind = "design"
    return {
        "subject_kind": subject_kind,
        "subject_id": str(target_id),
        "subject_name": target_name,
        "subject_role": target_kind,
        "subject_relation": "technical_target",
        "subject_value": 4,
        "research_target_kind": target_kind,
        "research_target_item_id": str(target_id),
        "research_effect_key": effect_key,
        "research_effect_delta": int(effect_delta),
        "research_effect_label": effect_label,
        "research_consumable": True,
    }


def wire_data_subject_metadata(sim, scene, prop, family):
    family = _key(family, "general")
    source_id = _text((prop or {}).get("id"))
    source_name = _text((prop or {}).get("name"), "unknown site")
    org_key, org_name = _source_org(prop if isinstance(prop, Mapping) else {})
    if family in {"personal_records", "blackmail"}:
        person = choose_wire_data_subject(sim, scene, prop, family)
        if person:
            return person
    if family in {"drone_mod_plan", "electronics_schematic", "software_source"}:
        technical = _technical_data_subject(sim, scene, prop, family)
        if technical:
            return technical
    if family == "payroll":
        return {
            "subject_kind": "organization" if org_key else "site",
            "subject_id": org_key or source_id,
            "subject_name": org_name or source_name,
            "subject_relation": "payroll_ledger",
            "subject_org_key": org_key,
            "subject_org_name": org_name,
            "subject_value": 3,
        }
    if family == "procurement":
        return {
            "subject_kind": "organization" if org_key else "contract_set",
            "subject_id": org_key or f"{source_id}:contracts",
            "subject_name": f"{org_name or source_name} purchasing contracts",
            "subject_relation": "procurement_contracts",
            "subject_org_key": org_key,
            "subject_org_name": org_name,
            "subject_value": 3,
        }
    if family == "customer_habits":
        return {
            "subject_kind": "cohort",
            "subject_id": f"{source_id}:customers",
            "subject_name": f"{source_name} customer cohort",
            "subject_relation": "customer_cohort",
            "subject_value": 2,
        }
    if family == "camera_fragment":
        return {
            "subject_kind": "surveillance",
            "subject_id": f"{source_id}:camera",
            "subject_name": f"{source_name} surveillance window",
            "subject_relation": "camera_record",
            "subject_value": 3,
        }
    if family == "prototype_telemetry":
        return {
            "subject_kind": "system",
            "subject_id": f"{source_id}:prototype",
            "subject_name": f"{source_name} prototype system",
            "subject_relation": "prototype_system",
            "subject_value": 4,
        }
    return {
        "subject_kind": "site",
        "subject_id": source_id,
        "subject_name": source_name,
        "subject_relation": "source_site",
        "subject_value": 1,
    }


def _blackmail_pressure_metadata(sim, scene, prop, subject):
    if not isinstance(subject, Mapping) or _key(subject.get("subject_kind")) != "person":
        return {}
    subject_name = _text(subject.get("subject_name"), "the subject")
    relation = _key(subject.get("subject_relation"))
    role = _key(subject.get("subject_role"))
    source_name = _text((prop or {}).get("name"), "the source")
    workplace_weighted = relation in {"owner", "manager", "guard", "employee", "organization_member"}
    if workplace_weighted or any(token in role for token in ("manager", "guard", "officer", "worker")):
        options = (
            (
                "falsified_security_report",
                f"The records show {subject_name} falsified a security report at {source_name}.",
                "their employer and the people they blamed",
                5,
            ),
            (
                "diverted_stock",
                f"The records tie {subject_name} to stock diverted out of {source_name}.",
                "their employer and coworkers",
                4,
            ),
            (
                "undeclared_payoff",
                f"The records document an undeclared payoff accepted by {subject_name} through {source_name}.",
                "their employer and investigators",
                5,
            ),
            (
                "prohibited_contact",
                f"The records prove {subject_name} maintained a prohibited private contact through {source_name}.",
                "their organization and the contact's enemies",
                4,
            ),
        )
    else:
        options = (
            (
                "undeclared_payoff",
                f"The records document an undeclared payoff accepted by {subject_name}.",
                "the people who rely on them and investigators",
                4,
            ),
            (
                "contraband_link",
                f"The records connect {subject_name} to a concealed contraband exchange at {source_name}.",
                "investigators and their close contacts",
                5,
            ),
            (
                "false_identity_filing",
                f"The records show {subject_name} used a false identity filing at {source_name}.",
                "officials and anyone depending on that identity",
                4,
            ),
        )
    chosen = options[
        _stable_index(
            (
                getattr(sim, "seed", 0),
                (scene or {}).get("scene_id"),
                (prop or {}).get("id"),
                subject.get("subject_eid"),
                "blackmail_fact",
            ),
            len(options),
        )
    ]
    return {
        "pressure_fact_key": chosen[0],
        "pressure_fact_summary": chosen[1],
        "pressure_audience": chosen[2],
        "pressure_strength": int(chosen[3]),
        "evidence_exclusivity": "unreleased",
    }


def _wire_subject_record_summary(family, subject_name, source_name, *, subject_kind=""):
    subject_name = _text(subject_name, "the records subject")
    source_name = _text(source_name, "the source")
    family = _key(family, "general")
    summaries = {
        "payroll": f"Payroll, deductions, and payment routing for {subject_name}.",
        "rota": f"Shift rotations and coverage gaps for {source_name}.",
        "procurement": f"Purchasing approvals and supplier traffic in {subject_name}.",
        "customer_habits": f"Visits, purchases, and routine patterns across {subject_name}.",
        "camera_fragment": f"Timestamped movement footage from {subject_name}.",
        "personal_records": f"Private records identifying {subject_name} at {source_name}.",
        "blackmail": f"Compromising private records tied to {subject_name} and {source_name}.",
        "drone_mod_plan": f"Modification drawings for {subject_name}, recovered from {source_name}.",
        "electronics_schematic": f"Engineering notes for {subject_name}, recovered from {source_name}.",
        "software_source": f"Source and profiling notes for {subject_name}, recovered from {source_name}.",
        "prototype_telemetry": f"Prototype access and test-use telemetry for {subject_name}.",
        "general": f"Linked records concerning {subject_name} at {source_name}.",
    }
    return summaries.get(family, summaries["general"])


def _records_node(scene, target=None):
    target = target if isinstance(target, Mapping) else {}
    node = target.get("node") if isinstance(target.get("node"), Mapping) else {}
    node_kind = _key(target.get("node_kind") or node.get("kind"))
    if node_kind == "records":
        return {
            "node_id": _text(node.get("node_id") or target.get("node_id"), "records"),
            "label": _text(node.get("label") or target.get("label"), "records node"),
        }
    avatar = dict((scene or {}).get("avatar") or {})
    ax = _int(avatar.get("x"), 0)
    ay = _int(avatar.get("y"), 0)
    for row in (scene or {}).get("nodes", ()) or ():
        if not isinstance(row, Mapping):
            continue
        if _key(row.get("kind")) != "records":
            continue
        if _int(row.get("x"), -999) == ax and _int(row.get("y"), -999) == ay:
            return {
                "node_id": _text(row.get("node_id"), "records"),
                "label": _text(row.get("label"), "records node"),
            }
    return None


def wire_data_extraction_key(scene, node=None):
    node = node if isinstance(node, Mapping) else {}
    return f"{wire_network_key(scene)}:records:{_text(node.get('node_id'), 'records')}"


def wire_data_cooldown_ticks(prop):
    return wire_security_reset_delay(prop)


def choose_wire_data_family(scene, prop):
    archetype = _source_archetype(scene, prop)
    metadata = _prop_metadata(prop)
    authored_family = _key(metadata.get("wire_data_family"))
    if authored_family in WIRE_DATA_FAMILIES:
        return authored_family
    security = _int((scene or {}).get("security_tier") or metadata.get("security_tier") or metadata.get("security"), 1, minimum=0)
    owner_tag = _key(prop.get("owner_tag") or metadata.get("owner_tag"))
    org_key, _org_name = _source_org(prop)
    if archetype in {"bank", "brokerage", "employment_agency", "payroll_office"}:
        options = ("payroll", "procurement", "rota", "personal_records")
    elif archetype == "drone_shop":
        options = ("drone_mod_plan", "electronics_schematic", "software_source", "procurement", "personal_records")
    elif archetype in {"electronics_shop", "comms_shop", "wire_shop"}:
        options = ("electronics_schematic", "software_source", "prototype_telemetry", "procurement", "personal_records")
    elif archetype in {"data_center", "tower"}:
        options = ("software_source", "prototype_telemetry", "procurement", "customer_habits", "personal_records")
    elif archetype in {"office", "contractor_office", "hardware_store", "tool_depot", "auto_garage"}:
        options = ("procurement", "payroll", "rota", "personal_records")
    elif archetype in {"media_lab", "courthouse", "city_hall", "civic_office"}:
        options = ("camera_fragment", "blackmail", "procurement", "personal_records")
    elif archetype in {"checkpoint", "armory", "security_office", "police_station", "jail", "prison"} or owner_tag in {"justice", "police", "military", "security"}:
        options = ("camera_fragment", "rota", "blackmail", "personal_records")
    elif archetype in {"casino", "bar", "nightclub", "hotel", "restaurant", "corner_store", "market"}:
        options = ("customer_habits", "payroll", "blackmail", "personal_records")
    elif security >= 4 or owner_tag in {"corp", "corporate"} or org_key:
        options = ("prototype_telemetry", "blackmail", "procurement", "personal_records")
    else:
        options = ("rota", "procurement", "customer_habits", "personal_records", "general")
    return options[_stable_index(((prop or {}).get("id", ""), (scene or {}).get("scene_id"), archetype, security), len(options))]


def wire_data_cache_metadata(sim, actor_eid, scene, node=None, *, item_catalog=None):
    prop = wire_network_property(sim, scene)
    node = node if isinstance(node, Mapping) else _records_node(scene)
    family = choose_wire_data_family(scene, prop if isinstance(prop, Mapping) else {})
    now = _int(getattr(sim, "tick", 0), 0)
    source_name = _text((prop or {}).get("name") or (scene or {}).get("linked_name") or (scene or {}).get("target_name"), "unknown site")
    source_id = _text((prop or {}).get("id") or (scene or {}).get("linked_property_id") or (scene or {}).get("target_property_id"))
    archetype = _source_archetype(scene, prop if isinstance(prop, Mapping) else {})
    org_key, org_name = _source_org(prop if isinstance(prop, Mapping) else {})
    source_security = 1
    if isinstance(prop, Mapping):
        source_security = (scene or {}).get("security_tier") or _prop_metadata(prop).get("security_tier") or _prop_metadata(prop).get("security")
    security = _int(source_security, 1, minimum=0)
    sensitivity = min(5, _SENSITIVITY_BY_FAMILY.get(family, 1) + (1 if security >= 4 else 0))
    freshness = max(1, min(5, 3 + (1 if security >= 3 else 0)))
    heat_risk = max(0, min(5, sensitivity + (1 if family in {"blackmail", "camera_fragment"} else 0)))
    legality = "illegal" if family in {"blackmail", "camera_fragment"} or heat_risk >= 5 else "restricted"
    subject = wire_data_subject_metadata(sim, scene, prop if isinstance(prop, Mapping) else {}, family)
    if family == "blackmail" and subject:
        subject = dict(subject)
        subject.update(_blackmail_pressure_metadata(sim, scene, prop if isinstance(prop, Mapping) else {}, subject))
    subject_name = _text((subject or {}).get("subject_name"))
    display_name = (
        f"{_FAMILY_LABELS.get(family, 'Data cache')}: {subject_name} / {source_name}"
        if subject_name
        else f"{_FAMILY_LABELS.get(family, 'Data cache')}: {source_name}"
    )
    evidence_links = [
        f"wire_scene:{_text((scene or {}).get('scene_id'), 'unknown')}",
        f"property:{source_id}" if source_id else "property:unknown",
    ]
    if subject and subject.get("subject_eid") is not None:
        evidence_links.append(f"entity:{subject.get('subject_eid')}")
    elif subject and subject.get("subject_id"):
        evidence_links.append(f"subject:{_key(subject.get('subject_kind'), 'record')}:{subject.get('subject_id')}")
    metadata = {
        "wire_data_schema_version": WIRE_DATA_SCHEMA_VERSION,
        "data_family": family,
        "sensitivity": sensitivity,
        "freshness": freshness,
        "heat_risk": heat_risk,
        "legality": legality,
        "source_property_id": source_id,
        "source_property_name": source_name,
        "source_org_key": org_key,
        "source_org_name": org_name,
        "source_archetype": archetype,
        "captured_tick": now,
        "buyer_tags": _FAMILY_BUYER_TAGS.get(family, ("illicit_buyer",)),
        "evidence_links": tuple(evidence_links),
        "display_name": display_name,
        "subject_kind": _key((subject or {}).get("subject_kind"), "site"),
        "record_summary": _wire_subject_record_summary(
            family,
            subject_name,
            source_name,
            subject_kind=_key((subject or {}).get("subject_kind")),
        ),
        "source_context": "wire_data_siphon",
        "storage_status": "wire_kit",
        "captured_by_eid": actor_eid,
        "records_node_id": _text((node or {}).get("node_id"), "records"),
        "network_key": wire_network_key(scene, prop),
    }
    if subject:
        metadata.update(subject)
    if family == "blackmail" and metadata.get("pressure_fact_summary"):
        metadata["record_summary"] = _text(metadata.get("pressure_fact_summary"))
    return normalize_wire_entry_metadata(
        metadata,
        item_id=WIRE_DATA_ITEM_ID,
        profile=wire_profile_for_item(WIRE_DATA_ITEM_ID, item_catalog=item_catalog or ITEM_CATALOG),
    )


def wire_data_siphon_preflight(sim, actor_eid, scene, *, target=None, item_catalog=None):
    if not isinstance(scene, Mapping):
        return {"ok": False, "reason": "missing_scene"}
    node = _records_node(scene, target=target)
    if node is None:
        return {"ok": False, "reason": "wrong_records_node"}
    prop = wire_network_property(sim, scene)
    if not isinstance(prop, dict):
        return {"ok": False, "reason": "missing_data_source"}
    metadata = _prop_metadata(prop, create=False)
    marks = metadata.get("wire_data_extractions")
    if not isinstance(marks, dict):
        marks = {}
    key = wire_data_extraction_key(scene, node=node)
    now = _int(getattr(sim, "tick", 0), 0)
    previous = marks.get(key)
    if isinstance(previous, Mapping):
        cooldown = _int(previous.get("cooldown_ticks"), wire_data_cooldown_ticks(prop), minimum=1)
        last_tick = _int(previous.get("last_tick"), -cooldown, minimum=-cooldown)
        if now < last_tick + cooldown:
            return {
                "ok": False,
                "reason": "records_recently_drained",
                "remaining_ticks": (last_tick + cooldown) - now,
                "source_key": key,
            }
    state = wire_state_for_actor(sim, actor_eid, create=True)
    entry = {
        "instance_id": "wire-data-preview",
        "item_id": WIRE_DATA_ITEM_ID,
        "quantity": 1,
        "owner_eid": actor_eid,
        "owner_tag": "player",
        "metadata": wire_data_cache_metadata(sim, actor_eid, scene, node=node, item_catalog=item_catalog),
    }
    ok, reason = wire_kit_can_accept_entry(state, entry, item_catalog=item_catalog or ITEM_CATALOG)
    if not ok:
        return {"ok": False, "reason": reason or "wire_kit_full", "source_key": key}
    return {"ok": True, "reason": None, "source_key": key, "node": dict(node), "metadata": dict(entry["metadata"])}


def _remember_wire_data_subject(sim, actor_eid, metadata):
    if not isinstance(metadata, Mapping) or _key(metadata.get("subject_kind")) != "person":
        return False
    subject_eid = metadata.get("subject_eid")
    try:
        subject_eid = int(subject_eid)
    except (TypeError, ValueError):
        return False
    ledgers = sim.ecs.get(ContactLedger)
    ledger = ledgers.get(actor_eid)
    if ledger is None:
        ledger = ContactLedger()
        sim.ecs.add(actor_eid, ledger)
    existing = ledger.person_entry(subject_eid)
    now = _int(getattr(sim, "tick", 0), 0)
    source_id = _text(metadata.get("source_property_id")) or None
    subject_name = _text(metadata.get("subject_name"), "someone")
    source_name = _text(metadata.get("source_property_name"), "a records system")
    ledger.remember_person(
        subject_eid,
        source_eid=None,
        relation_kind=None if isinstance(existing, Mapping) else "wire_record",
        standing=0.0,
        tick=now,
        property_id=source_id,
        benefits={"known_name", "wire_record"},
        introduced=False,
        met_directly=False,
        identity_snapshot=dict(metadata.get("subject_identity") or {}),
    )
    ledger.remember_person_episode(
        subject_eid,
        kind="wire_record_acquired",
        tick=now,
        valence="neutral",
        summary=f"You pulled records tying {subject_name} to {source_name}.",
        property_id=source_id,
        source_topic="wire_data",
        dedupe_window=0,
    )
    note_person_notebook_mutation(
        sim,
        actor_eid,
        subject_eid,
        before=dict(existing) if isinstance(existing, Mapping) else None,
        after=ledger.person_entry(subject_eid),
    )
    return True


def extract_wire_data_cache(sim, actor_eid, scene, *, target=None, item_catalog=None):
    preflight = wire_data_siphon_preflight(sim, actor_eid, scene, target=target, item_catalog=item_catalog)
    if not preflight.get("ok"):
        return preflight
    prop = wire_network_property(sim, scene)
    node = dict(preflight.get("node") or {})
    instance_factory = getattr(sim, "new_item_instance_id", None)
    instance_id = instance_factory() if callable(instance_factory) else f"wire-data-{getattr(sim, 'tick', 0)}"
    entry = {
        "instance_id": instance_id,
        "item_id": WIRE_DATA_ITEM_ID,
        "quantity": 1,
        "owner_eid": actor_eid,
        "owner_tag": "player",
        "metadata": dict(preflight.get("metadata") or wire_data_cache_metadata(sim, actor_eid, scene, node=node, item_catalog=item_catalog)),
    }
    state = wire_state_for_actor(sim, actor_eid, create=True)
    result = wire_kit_add_entry(state, entry, item_catalog=item_catalog or ITEM_CATALOG)
    if not result.get("ok"):
        return {"ok": False, "reason": result.get("reason", "wire_kit_full"), "entry": dict(entry)}
    now = _int(getattr(sim, "tick", 0), 0)
    metadata = _prop_metadata(prop, create=True)
    marks = metadata.get("wire_data_extractions")
    if not isinstance(marks, dict):
        marks = {}
        metadata["wire_data_extractions"] = marks
    source_key = str(preflight.get("source_key") or wire_data_extraction_key(scene, node=node))
    marks[source_key] = {
        "last_tick": now,
        "cooldown_ticks": wire_data_cooldown_ticks(prop),
        "family": entry["metadata"].get("data_family"),
        "instance_id": instance_id,
        "scene_id": (scene or {}).get("scene_id"),
        "subject_eid": entry["metadata"].get("subject_eid"),
        "subject_name": entry["metadata"].get("subject_name", ""),
    }
    _remember_wire_data_subject(sim, actor_eid, entry["metadata"])
    sim.emit(Event(
        "wire_data_extracted",
        eid=actor_eid,
        item_id=WIRE_DATA_ITEM_ID,
        instance_id=instance_id,
        display_name=entry["metadata"].get("display_name", ""),
        data_family=entry["metadata"].get("data_family", ""),
        source_property_id=entry["metadata"].get("source_property_id", ""),
        source_property_name=entry["metadata"].get("source_property_name", ""),
        subject_eid=entry["metadata"].get("subject_eid"),
        subject_name=entry["metadata"].get("subject_name", ""),
        subject_role=entry["metadata"].get("subject_role", ""),
        subject_relation=entry["metadata"].get("subject_relation", ""),
        source_key=source_key,
    ))
    return {"ok": True, "reason": None, "entry": dict(result.get("entry") or entry), "source_key": source_key}


def wire_data_buyer_profile_for_store(prop=None, store=None):
    archetype = _key((store or {}).get("archetype") if isinstance(store, Mapping) else "")
    if not archetype and isinstance(prop, Mapping):
        archetype = _key(_prop_metadata(prop).get("archetype") or _prop_metadata(prop).get("service_archetype"))
    org_key, org_name = _source_org(prop if isinstance(prop, Mapping) else {})
    extra = {
        "context": archetype,
        "buyer_property_id": _text((prop or {}).get("id")) if isinstance(prop, Mapping) else "",
        "buyer_property_name": _text((prop or {}).get("name")) if isinstance(prop, Mapping) else "",
        "buyer_org_key": org_key,
        "buyer_org_name": org_name,
    }
    if archetype in {"bank", "brokerage"}:
        return dict(_BROKER_PROFILES["finance"], **extra)
    if archetype in {"office", "tower", "data_center", "electronics_shop", "comms_shop", "drone_shop", "wire_shop"}:
        return dict(_BROKER_PROFILES["corp_tech"], **extra)
    if archetype in {"media_lab", "civic_office", "city_hall"}:
        return dict(_BROKER_PROFILES["media_civic"], **extra)
    if archetype in {"backroom_market", "pawn_shop", "junk_market", "chop_shop"}:
        return dict(_BROKER_PROFILES["illicit"], **extra)
    return None


def wire_data_buyer_profile_for_street(profile=None):
    profile = profile if isinstance(profile, Mapping) else {}
    vendor_kind = _key(profile.get("vendor_kind"))
    career = _key(profile.get("career"))
    org_key = _key(profile.get("organization_key") or profile.get("root_organization_key") or profile.get("org_key"))
    org_name = _text(profile.get("organization_name") or profile.get("root_organization_name") or profile.get("org_name"))
    extra = {
        "context": vendor_kind or career or "street",
        "buyer_org_key": org_key,
        "buyer_org_name": org_name,
    }
    if vendor_kind in {"gang_fence", "alley_market"}:
        return dict(_BROKER_PROFILES["illicit"], **extra)
    if vendor_kind in {"drug_pusher", "drug_seeker", "vehicle_gun_vendor", "friend_of_friend"}:
        return None
    if any(token in career for token in ("broker", "analyst", "banker", "accountant")):
        return dict(_BROKER_PROFILES["finance"], **extra)
    if any(token in career for token in ("journalist", "reporter", "civic", "activist")):
        return dict(_BROKER_PROFILES["media_civic"], **extra)
    if any(token in career for token in ("corp", "tech", "engineer", "fixer")):
        return dict(_BROKER_PROFILES["corp_tech"], **extra)
    return None


def wire_data_quote(entry, buyer_profile=None, *, tick=0, price_mult=1.0):
    metadata = dict((entry or {}).get("metadata") or {})
    buyer_profile = buyer_profile if isinstance(buyer_profile, Mapping) else None
    family = _key(metadata.get("data_family"), "general")
    sensitivity = _int(metadata.get("sensitivity"), 1, minimum=0, maximum=5)
    heat_risk = _int(metadata.get("heat_risk"), 0, minimum=0, maximum=5)
    freshness = _int(metadata.get("freshness"), 1, minimum=0, maximum=5)
    captured_tick = _int(metadata.get("captured_tick"), int(tick), minimum=0)
    age_steps = max(0, (_int(tick, 0, minimum=0) - captured_tick) // 1000)
    effective_freshness = max(0, freshness - age_steps)
    subject_value = _int(metadata.get("subject_value"), 0, minimum=0, maximum=5)
    subject_name = _text(metadata.get("subject_name"))
    base_value = 18 + (sensitivity * 34) + (effective_freshness * 9) + (heat_risk * 13) + (subject_value * 12)
    legality = _key(metadata.get("legality"), "restricted")
    buyer_tags = set(_string_tuple(metadata.get("buyer_tags")))
    source_org_key = _key(metadata.get("source_org_key"))
    buyer_org_key = _key((buyer_profile or {}).get("buyer_org_key")) if isinstance(buyer_profile, Mapping) else ""
    org_context = ""
    if buyer_profile is None:
        interest = "refused"
        multiplier = 0.0
        reason = "no data broker here"
    else:
        profile_tags = set(_string_tuple(buyer_profile.get("buyer_tags")))
        preferred = set(_string_tuple(buyer_profile.get("preferred")))
        adjacent = set(_string_tuple(buyer_profile.get("adjacent")))
        if source_org_key and buyer_org_key and source_org_key == buyer_org_key:
            interest = "wanted"
            multiplier = 0.92 if family not in preferred else 1.04
            reason = f"internal recovery tied to {subject_name}" if subject_name else "internal data recovery"
            org_context = "internal"
        elif source_org_key and buyer_org_key and source_org_key != buyer_org_key and family in {
            "payroll",
            "procurement",
            "customer_habits",
            "personal_records",
            "prototype_telemetry",
            "drone_mod_plan",
            "electronics_schematic",
            "software_source",
            "blackmail",
        }:
            interest = "wanted"
            multiplier = 1.24
            reason = f"rival intelligence on {subject_name}" if subject_name else "rival organization intelligence"
            org_context = "rival"
        elif family in preferred or buyer_tags.intersection(profile_tags):
            interest = "wanted"
            multiplier = 1.16
            reason = "matches broker demand"
        elif family in adjacent:
            interest = "adjacent"
            multiplier = 0.68
            reason = "adjacent data interest"
        else:
            interest = "refused"
            multiplier = 0.0
            reason = "wrong data buyer"
    price = int(max(1, round(base_value * multiplier * max(0.0, float(price_mult or 1.0))))) if multiplier > 0 else 0
    risk_label = ""
    if legality == "illegal":
        risk_label = "hot data"
    elif heat_risk >= 4:
        risk_label = "trace risk"
    elif legality == "restricted":
        risk_label = "restricted data"
    return {
        "price": price,
        "base_price": int(base_value),
        "interest": interest,
        "label": "wanted data" if interest == "wanted" else ("adjacent data" if interest == "adjacent" else "refused data"),
        "accepted": interest in {"wanted", "adjacent"},
        "reason": reason,
        "freshness": effective_freshness,
        "heat_risk": heat_risk,
        "risk_label": risk_label,
        "legality": legality,
        "data_family": family,
        "org_context": org_context,
        "subject_eid": metadata.get("subject_eid"),
        "subject_name": subject_name,
        "subject_role": _key(metadata.get("subject_role")),
        "subject_relation": _key(metadata.get("subject_relation")),
        "subject_value": subject_value,
    }


def _wire_data_entries(sim, actor_eid):
    state = wire_state_for_actor(sim, actor_eid, create=False)
    if state is None:
        return []
    rows = []
    for entry in getattr(state, "kit_entries", ()) or ():
        if not isinstance(entry, Mapping):
            continue
        if _key(entry.get("item_id")) != WIRE_DATA_ITEM_ID:
            continue
        profile = wire_profile_for_item(entry.get("item_id"), item_catalog=ITEM_CATALOG)
        if _key(profile.get("kind")) != "data_packet":
            continue
        rows.append(dict(entry))
    return rows


def _data_sell_row(entry, quote, *, row_context):
    metadata = dict(entry.get("metadata") or {})
    name = wire_entry_display_name(entry, item_catalog=ITEM_CATALOG)
    family = _key(metadata.get("data_family"), "general")
    return {
        "entry": dict(entry),
        "source_container": "wire_kit",
        "instance_id": entry.get("instance_id"),
        "item_id": WIRE_DATA_ITEM_ID,
        "item_name": name,
        "glyph": str(ITEM_CATALOG.get(WIRE_DATA_ITEM_ID, {}).get("glyph", ":") or ":")[:1],
        "quantity": 1,
        "price": int(max(1, quote.get("price", 1))),
        "base_price": int(max(1, quote.get("base_price", quote.get("price", 1)))),
        "listed": False,
        "action_label": "sell data",
        "purchase_interest": quote.get("interest"),
        "interest_label": quote.get("label"),
        "interest_known": True,
        "interest_actual": quote.get("interest"),
        "actual_label": quote.get("label"),
        "interest_actual_label": quote.get("label"),
        "row_color": "item_restricted" if quote.get("legality") == "illegal" else "item_tool",
        "interest_reason": quote.get("reason", ""),
        "interest_price_mult": 1.0,
        "interest_accepted": bool(quote.get("accepted")),
        "interest_pressure_weight": 0,
        "risk_label": quote.get("risk_label", ""),
        "trade_pressure_label": "broker",
        "trade_pressure_note": row_context,
        "trade_pressure_value": 0.0,
        "wire_data_family": family,
        "wire_data_freshness": quote.get("freshness"),
        "wire_data_heat_risk": quote.get("heat_risk"),
        "wire_data_org_context": quote.get("org_context", ""),
        "wire_data_subject_eid": metadata.get("subject_eid"),
        "wire_data_subject_name": _text(metadata.get("subject_name")),
        "wire_data_subject_role": _key(metadata.get("subject_role")),
        "wire_data_subject_relation": _key(metadata.get("subject_relation")),
        "wire_data_subject_value": _int(metadata.get("subject_value"), 0, minimum=0, maximum=5),
        "wire_data_record_summary": _text(metadata.get("record_summary")),
        "illegal": quote.get("legality") == "illegal",
    }


def wire_data_store_sell_rows(sim, actor_eid, prop=None, store=None, *, terms=None):
    buyer = wire_data_buyer_profile_for_store(prop, store)
    if buyer is None:
        return []
    sell_mult = float((terms or {}).get("sell_mult", 1.0) or 1.0) if isinstance(terms, Mapping) else 1.0
    rows = []
    for entry in _wire_data_entries(sim, actor_eid):
        quote = wire_data_quote(entry, buyer, tick=getattr(sim, "tick", 0), price_mult=sell_mult)
        if not quote.get("accepted"):
            continue
        rows.append(_data_sell_row(entry, quote, row_context=str(buyer.get("context", "broker"))))
    rows.sort(key=lambda row: (-int(row.get("price", 0)), row.get("wire_data_family", ""), row.get("instance_id", "")))
    return rows


def wire_data_street_sell_rows(sim, contact_eid, player_eid, profile=None):
    buyer = wire_data_buyer_profile_for_street(profile)
    if buyer is None:
        return []
    rows = []
    for entry in _wire_data_entries(sim, player_eid):
        quote = wire_data_quote(entry, buyer, tick=getattr(sim, "tick", 0), price_mult=1.0)
        if not quote.get("accepted"):
            continue
        row = _data_sell_row(entry, quote, row_context=str(buyer.get("context", "street")))
        row.update({
            "purchase_interest": "wanted",
            "interest_actual": "wanted",
            "interest_label": "broker wants data",
            "interest_actual_label": "broker wants data",
            "row_badge": "data",
            "source_kind": "street_vendor",
            "contact_eid": contact_eid,
        })
        rows.append(row)
    rows.sort(key=lambda row: (-int(row.get("price", 0)), row.get("wire_data_family", ""), row.get("instance_id", "")))
    return rows


def remove_wire_data_entry(sim, actor_eid, instance_id):
    state = wire_state_for_actor(sim, actor_eid, create=False)
    if state is None:
        return {"ok": False, "reason": "missing_wire_state"}
    entry = None
    for row in getattr(state, "kit_entries", ()) or ():
        if isinstance(row, Mapping) and _text(row.get("instance_id")) == _text(instance_id):
            entry = dict(row)
            break
    if entry is None or _key(entry.get("item_id")) != WIRE_DATA_ITEM_ID:
        return {"ok": False, "reason": "data_unavailable"}
    removed = wire_kit_remove_entry(state, instance_id)
    if removed is None:
        return {"ok": False, "reason": "data_remove_failed"}
    return {"ok": True, "reason": None, "entry": dict(removed)}


def study_wire_data_entry(sim, actor_eid, instance_id, *, item_catalog=None):
    item_catalog = item_catalog or ITEM_CATALOG
    state = wire_state_for_actor(sim, actor_eid, create=False)
    if state is None:
        return {"ok": False, "reason": "missing_wire_state"}
    entry = next(
        (
            dict(row)
            for row in tuple(getattr(state, "kit_entries", ()) or ())
            if isinstance(row, Mapping) and _text(row.get("instance_id")) == _text(instance_id)
        ),
        None,
    )
    metadata = dict((entry or {}).get("metadata") or {})
    if not entry or _key(entry.get("item_id")) != WIRE_DATA_ITEM_ID or not bool(metadata.get("research_consumable")):
        return {"ok": False, "reason": "data_not_researchable"}

    from game.technical_research import (
        apply_technical_research_to_entry,
        record_technical_research,
        technical_research_rows,
        technical_research_unlock_key,
    )

    unlock_key = technical_research_unlock_key(metadata)
    if any(_text(row.get("key")) == unlock_key for row in technical_research_rows(sim, actor_eid)):
        return {"ok": False, "reason": "research_already_known", "entry": entry}

    removed = remove_wire_data_entry(sim, actor_eid, instance_id)
    if not removed.get("ok"):
        return removed
    learned = record_technical_research(sim, actor_eid, metadata)
    if not learned.get("ok"):
        state.kit_entries.append(dict(removed["entry"]))
        return {"ok": False, "reason": learned.get("reason", "research_failed"), "entry": dict(removed["entry"])}

    affected = 0
    state = wire_state_for_actor(sim, actor_eid, create=True)
    for row in tuple(getattr(state, "kit_entries", ()) or ()) + tuple(getattr(state, "ram_slots", ()) or ()):
        if apply_technical_research_to_entry(sim, actor_eid, row, item_catalog=item_catalog):
            affected += 1
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    for row in tuple(getattr(inventory, "items", ()) or ()) if inventory is not None else ():
        if apply_technical_research_to_entry(sim, actor_eid, row, item_catalog=item_catalog):
            affected += 1

    try:
        from game.drone_workshop import drone_workshop_for_actor

        workshop = drone_workshop_for_actor(sim, actor_eid, create=False, item_catalog=item_catalog)
    except (ImportError, TypeError, ValueError):
        workshop = None
    if workshop is not None:
        for row in tuple(getattr(workshop, "parts", ()) or ()) + tuple(getattr(workshop, "chassis_slots", ()) or ()):
            if apply_technical_research_to_entry(sim, actor_eid, row, item_catalog=item_catalog):
                affected += 1

    from game.components import DroneState

    for _drone_eid, drone_state in sim.ecs.get(DroneState).items():
        owner_eid = getattr(drone_state, "owner_eid", None)
        controller_eid = getattr(drone_state, "controller_eid", None)
        if actor_eid not in {owner_eid, controller_eid} and "player" not in {
            _key(getattr(drone_state, "owner_tag", "")),
            _key(getattr(drone_state, "controller_tag", "")),
        }:
            continue
        for module in tuple(getattr(drone_state, "modules", ()) or ()):
            if apply_technical_research_to_entry(sim, actor_eid, module, item_catalog=item_catalog):
                affected += 1

    try:
        from game.wire_kit import refresh_wire_state_interface_capacity

        refresh_wire_state_interface_capacity(sim, actor_eid, state, item_catalog=item_catalog)
    except (ImportError, TypeError, ValueError):
        pass

    record = dict(learned.get("record") or {})
    sim.emit(Event(
        "wire_data_researched",
        eid=actor_eid,
        instance_id=instance_id,
        data_family=metadata.get("data_family", ""),
        subject_kind=metadata.get("subject_kind", ""),
        subject_id=metadata.get("subject_id", ""),
        subject_name=metadata.get("subject_name", ""),
        target_kind=record.get("target_kind", ""),
        target_item_id=record.get("target_item_id", ""),
        effect_key=record.get("effect_key", ""),
        effect_delta=record.get("effect_delta", 0),
        effect_label=record.get("effect_label", ""),
        affected_entries=affected,
    ))
    return {
        "ok": True,
        "reason": None,
        "entry": dict(removed["entry"]),
        "research": record,
        "affected_entries": affected,
        "feedback": f"Studied {record.get('target_name') or metadata.get('subject_name')}: {record.get('effect_label') or 'technical improvement learned'}.",
    }


def sell_wire_data_entry(sim, actor_eid, instance_id, *, price=0, buyer_context=""):
    result = remove_wire_data_entry(sim, actor_eid, instance_id)
    if not result.get("ok"):
        return result
    assets = sim.ecs.get(PlayerAssets).get(actor_eid)
    if assets is None:
        state = wire_state_for_actor(sim, actor_eid, create=True)
        state.kit_entries.append(dict(result["entry"]))
        return {"ok": False, "reason": "missing_assets", "entry": dict(result["entry"])}
    payout = int(max(0, price or 0))
    assets.credits = int(getattr(assets, "credits", 0) or 0) + payout
    entry = dict(result["entry"])
    sim.emit(Event(
        "wire_data_sold",
        eid=actor_eid,
        instance_id=entry.get("instance_id"),
        item_id=entry.get("item_id"),
        item_name=wire_entry_display_name(entry, item_catalog=ITEM_CATALOG),
        price=payout,
        credits=assets.credits,
        buyer_context=buyer_context,
        data_family=(entry.get("metadata") or {}).get("data_family", ""),
        subject_eid=(entry.get("metadata") or {}).get("subject_eid"),
        subject_name=(entry.get("metadata") or {}).get("subject_name", ""),
        subject_role=(entry.get("metadata") or {}).get("subject_role", ""),
        subject_relation=(entry.get("metadata") or {}).get("subject_relation", ""),
    ))
    return {"ok": True, "reason": None, "entry": entry, "price": payout, "credits": assets.credits}
