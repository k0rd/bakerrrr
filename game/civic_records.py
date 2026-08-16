"""Jurisdictional public records exposed through civic service sites.

The registry is a view over canonical simulation state, not a second copy of
every NPC.  Live and streamed-out actors are read from ECS/chunk snapshots;
only issued licenses are stored here because those are records in their own
right.  Public reads deliberately omit private appearance, biology, social
memory, witness identity, and covert affiliations.
"""

from __future__ import annotations

from collections import Counter

from engine.events import Event
from game.components import (
    ContactLedger,
    CreatureIdentity,
    NPCSettlement,
    NPCRoutine,
    Occupation,
    OrganizationAffiliations,
    PlayerAssets,
    Position,
    PropertyPortfolio,
    Vitality,
)
from game.justice_identity_runtime import justice_identity_state
from game.justice_runtime import justice_snapshot, justice_summary_rows
from game.knowledge_notebook import note_person_notebook_mutation
from game.npc_relationships import current_relationship_for_actor
from game.organizations import organization_policy_snapshot, organization_profile


CIVIC_RECORDS_SERVICE_ID = "civic_records"
CIVIC_RECORDS_STATE_KEY = "civic_records"
PUBLIC_ORGANIZATION_KINDS = {
    "business",
    "corporation",
    "civic",
    "community",
    "institution",
    "trade_group",
}
LICENSE_STATUSES = {"active", "expired", "revoked", "suspended"}
LICENSE_FEES = {
    "hunting": 45,
    "cultivation": 40,
    "bounty": 125,
}
LICENSE_RESTRICTIONS = {
    "hunting": ("eligible game only", "declared seasons and culls only for protected species"),
    "cultivation": ("registered cultivation and plant commerce",),
    "bounty": (
        "matching posted alive-recovery assignments only",
        "limited pursuit, unarmed force, and custodial restraint",
        "no lethal force, explosives, property search, or collateral authority",
    ),
}


def _text(value):
    return str(value or "").strip()


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _property_metadata(prop):
    return prop.get("metadata", {}) if isinstance(prop, dict) and isinstance(prop.get("metadata"), dict) else {}


def _component_from_map(component_map, component_type):
    if not isinstance(component_map, dict):
        return None
    component = component_map.get(component_type)
    if component is not None:
        return component
    wanted = str(getattr(component_type, "__name__", component_type) or "")
    for raw_type, value in component_map.items():
        if str(getattr(raw_type, "__name__", raw_type) or "") == wanted:
            return value
    return None


def _saved_entity_components(sim):
    rows = {}
    for snapshot in tuple(getattr(sim, "chunk_saved_states", {}).values()):
        if not isinstance(snapshot, dict):
            continue
        entities = snapshot.get("entities", {})
        if not isinstance(entities, dict):
            continue
        for raw_eid, component_map in entities.items():
            eid = _int(raw_eid, -1)
            if eid > 0 and isinstance(component_map, dict):
                rows.setdefault(eid, component_map)
    return rows


def _properties_anywhere(sim):
    rows = {
        str(property_id): prop
        for property_id, prop in getattr(sim, "properties", {}).items()
        if isinstance(prop, dict)
    }
    for snapshot in tuple(getattr(sim, "chunk_saved_states", {}).values()):
        if not isinstance(snapshot, dict):
            continue
        for property_id, prop in dict(snapshot.get("properties", {}) or {}).items():
            if isinstance(prop, dict):
                rows.setdefault(str(property_id), prop)
    return rows


def _actor_component(sim, eid, component_type, saved_components):
    live = sim.ecs.get(component_type).get(eid)
    if live is not None:
        return live
    return _component_from_map(saved_components.get(int(eid)), component_type)


def _identity_record(sim, eid, saved_components):
    identity = _actor_component(sim, eid, CreatureIdentity, saved_components)
    if identity is not None:
        record = {
            "eid": int(eid),
            "personal_name": _text(getattr(identity, "personal_name", "")),
            "display_name": _text(identity.display_name() if hasattr(identity, "display_name") else getattr(identity, "personal_name", "")),
            "gender_identity": _text(getattr(identity, "gender_identity", "")).lower(),
            "pronoun_set": _text(getattr(identity, "pronoun_set", "")).lower(),
            "creature_type": _text(getattr(identity, "creature_type", "")).lower(),
            "taxonomy_class": _text(getattr(identity, "taxonomy_class", "")).lower(),
        }
        return record
    resolver = getattr(sim, "entity_identity_record", None)
    record = resolver(eid) if callable(resolver) else None
    return dict(record) if isinstance(record, dict) else None


def _human_identity_record(record):
    if not isinstance(record, dict):
        return False
    creature_type = _text(record.get("creature_type")).lower()
    taxonomy = _text(record.get("taxonomy_class")).lower()
    return creature_type == "human" or taxonomy == "hominid"


def _all_registered_human_eids(sim, saved_components):
    eids = set()
    eids.update(_int(eid, -1) for eid in sim.ecs.get(CreatureIdentity).keys())
    eids.update(saved_components.keys())
    for roster in tuple(getattr(sim, "chunk_population_records", {}).values()):
        eids.update(_int(eid, -1) for eid in tuple(roster or ()))
    traits = getattr(sim, "world_traits", {}) if isinstance(getattr(sim, "world_traits", None), dict) else {}
    killed = traits.get("killed_npc_eids", ())
    if isinstance(killed, (list, tuple, set)):
        eids.update(_int(eid, -1) for eid in killed)
    player_eid = getattr(sim, "player_eid", None)
    if player_eid is not None:
        eids.add(_int(player_eid, -1))
    return tuple(sorted(eid for eid in eids if eid > 0 and _human_identity_record(_identity_record(sim, eid, saved_components))))


def _property_id_from_reference(value):
    if isinstance(value, dict):
        return _text(value.get("property_id") or value.get("id"))
    return _text(value)


def _property_name(properties, property_id, default=""):
    property_id = _text(property_id)
    prop = properties.get(property_id)
    if not isinstance(prop, dict):
        return _text(default) or property_id
    metadata = _property_metadata(prop)
    return _text(metadata.get("business_name") or prop.get("name") or prop.get("id")) or _text(default)


def _settlement_for_position(sim, x, y):
    try:
        chunk = sim.chunk_coords(int(x), int(y))
    except (AttributeError, TypeError, ValueError):
        return ""
    loaded = getattr(getattr(sim, "world", None), "loaded_chunks", {}) or {}
    chunk_data = loaded.get(chunk) if isinstance(loaded, dict) else None
    if isinstance(chunk_data, dict):
        district = chunk_data.get("district") if isinstance(chunk_data.get("district"), dict) else chunk_data
        settlement = _text(district.get("settlement_name"))
        if settlement:
            return settlement
    descriptor_fn = getattr(getattr(sim, "world", None), "overworld_descriptor", None)
    if callable(descriptor_fn):
        descriptor = descriptor_fn(*chunk)
        if isinstance(descriptor, dict):
            return _text(descriptor.get("settlement_name"))
    return ""


def _property_settlement(sim, prop):
    if not isinstance(prop, dict):
        return ""
    metadata = _property_metadata(prop)
    settlement = _text(metadata.get("settlement_name"))
    if settlement:
        return settlement
    return _settlement_for_position(sim, prop.get("x", 0), prop.get("y", 0))


def civic_records_authority(sim, prop):
    policy = organization_policy_snapshot(sim, prop=prop) if isinstance(prop, dict) else None
    policy = policy if isinstance(policy, dict) else {}
    office_name = _text(policy.get("organization_name")) or _text((prop or {}).get("name")) or "Civic Records Office"
    authority_name = _text(policy.get("root_organization_name")) or office_name
    return {
        "office_name": office_name,
        "authority_name": authority_name,
        "organization_eid": policy.get("organization_eid"),
        "organization_key": _text(policy.get("organization_key")),
        "root_organization_eid": policy.get("root_organization_eid"),
        "root_organization_key": _text(policy.get("root_organization_key")),
        "settlement_name": _property_settlement(sim, prop),
    }


def civic_records_state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    state = traits.get(CIVIC_RECORDS_STATE_KEY)
    if not isinstance(state, dict):
        state = {}
        traits[CIVIC_RECORDS_STATE_KEY] = state
    state.setdefault("version", 1)
    if not isinstance(state.get("licenses"), dict):
        state["licenses"] = {}
    return state


def record_civic_license(
    sim,
    subject_eid,
    license_kind,
    *,
    status="active",
    issuer_organization_key="",
    issuer_name="",
    issued_tick=None,
    expires_tick=None,
    restrictions=(),
    notes=(),
):
    """Issue or amend a durable civic credential for future license systems."""

    subject_eid = _int(subject_eid, -1)
    license_kind = _text(license_kind).lower().replace(" ", "_")
    status = _text(status).lower() or "active"
    if subject_eid <= 0 or not license_kind or status not in LICENSE_STATUSES:
        return None
    now = _int(getattr(sim, "tick", 0), 0)
    if issued_tick is None:
        issued_tick = now
    record = {
        "subject_eid": subject_eid,
        "license_kind": license_kind,
        "status": status,
        "issuer_organization_key": _text(issuer_organization_key),
        "issuer_name": _text(issuer_name),
        "issued_tick": _int(issued_tick, now),
        "expires_tick": _int(expires_tick, 0) if expires_tick is not None else None,
        "restrictions": tuple(sorted({_text(value) for value in tuple(restrictions or ()) if _text(value)})),
        "notes": tuple(_text(value) for value in tuple(notes or ()) if _text(value)),
        "updated_tick": now,
    }
    key = f"{subject_eid}:{license_kind}"
    civic_records_state(sim)["licenses"][key] = record
    return dict(record)


def civic_license_records(sim, subject_eid=None):
    now = _int(getattr(sim, "tick", 0), 0)
    wanted = _int(subject_eid, -1) if subject_eid is not None else None
    rows = []
    for record in civic_records_state(sim)["licenses"].values():
        if not isinstance(record, dict):
            continue
        eid = _int(record.get("subject_eid"), -1)
        if wanted is not None and eid != wanted:
            continue
        row = dict(record)
        expires = row.get("expires_tick")
        if row.get("status") == "active" and expires is not None and _int(expires, 0) > 0 and now >= _int(expires, 0):
            row["status"] = "expired"
        rows.append(row)
    rows.sort(key=lambda row: (_text(row.get("license_kind")), _int(row.get("subject_eid"), 0)))
    return tuple(rows)


def civic_license_record(sim, subject_eid, license_kind):
    wanted = _text(license_kind).lower().replace(" ", "_")
    for record in civic_license_records(sim, subject_eid):
        if _text(record.get("license_kind")).lower() == wanted:
            return dict(record)
    return None


def civic_license_is_active(sim, subject_eid, license_kind):
    record = civic_license_record(sim, subject_eid, license_kind)
    return bool(record and _text(record.get("status")).lower() == "active")


def record_civic_license_misuse(
    sim,
    subject_eid,
    license_kind,
    *,
    reason,
    action="",
    target_eid=None,
    incident_id=None,
):
    """Attach one deduplicated official review flag to a civic credential."""

    subject_eid = _int(subject_eid, -1)
    license_kind = _text(license_kind).lower().replace(" ", "_")
    key = f"{subject_eid}:{license_kind}"
    record = civic_records_state(sim)["licenses"].get(key)
    if subject_eid <= 0 or not isinstance(record, dict):
        return None
    now = _int(getattr(sim, "tick", 0), 0)
    reference = {
        "tick": now,
        "reason": _text(reason),
        "action": _text(action).lower(),
        "target_eid": _int(target_eid, -1) if target_eid is not None else None,
        "incident_id": _int(incident_id, -1) if incident_id is not None else None,
    }
    dedupe_key = (
        reference["incident_id"],
        reference["action"],
        reference["target_eid"],
        reference["reason"],
    )
    existing = [row for row in tuple(record.get("misuse_refs", ()) or ()) if isinstance(row, dict)]
    for row in existing:
        row_key = (
            row.get("incident_id"),
            _text(row.get("action")).lower(),
            row.get("target_eid"),
            _text(row.get("reason")),
        )
        if row_key == dedupe_key:
            return dict(record)
    existing.append(reference)
    record["misuse_refs"] = tuple(existing[-16:])
    record["misuse_count"] = len(existing)
    record["last_misuse_tick"] = now
    record["updated_tick"] = now
    sim.emit(Event(
        "civic_license_misuse_noted",
        subject_eid=subject_eid,
        license_kind=license_kind,
        reason=reference["reason"],
        action=reference["action"],
        target_eid=reference["target_eid"],
        incident_id=reference["incident_id"],
        misuse_count=int(record["misuse_count"]),
    ))
    return dict(record)


def purchase_civic_license(sim, subject_eid, license_kind, *, prop=None):
    """Buy or renew one ordinary civic credential at an issuing office."""

    license_kind = _text(license_kind).lower().replace(" ", "_")
    if license_kind not in LICENSE_FEES:
        return {"ok": False, "reason": "unsupported", "license_kind": license_kind}
    existing = civic_license_record(sim, subject_eid, license_kind)
    if existing and _text(existing.get("status")).lower() == "active":
        return {
            "ok": False,
            "reason": "already_active",
            "license_kind": license_kind,
            "record": existing,
        }
    if license_kind == "bounty":
        legal = justice_snapshot(sim, subject_eid)
        tier = _text(legal.get("wanted_tier", "clear")).lower() or "clear"
        if tier != "clear":
            return {
                "ok": False,
                "reason": "justice_hold",
                "license_kind": license_kind,
                "wanted_tier": tier,
            }
    assets = sim.ecs.get(PlayerAssets).get(subject_eid)
    credits = max(0, _int(getattr(assets, "credits", 0), 0)) if assets is not None else 0
    fee = int(LICENSE_FEES[license_kind])
    if assets is None or credits < fee:
        return {
            "ok": False,
            "reason": "no_credits",
            "license_kind": license_kind,
            "fee": fee,
            "credits": credits,
        }
    authority = civic_records_authority(sim, prop)
    assets.credits = credits - fee
    record = record_civic_license(
        sim,
        subject_eid,
        license_kind,
        status="active",
        issuer_organization_key=authority.get("root_organization_key") or authority.get("organization_key"),
        issuer_name=authority.get("authority_name") or authority.get("office_name"),
        restrictions=LICENSE_RESTRICTIONS.get(license_kind, ()),
    )
    sim.emit(Event(
        "civic_license_issued",
        subject_eid=subject_eid,
        license_kind=license_kind,
        fee=fee,
        issuer_name=authority.get("authority_name") or authority.get("office_name"),
        issuer_organization_key=authority.get("root_organization_key") or authority.get("organization_key"),
        renewed=existing is not None,
    ))
    return {
        "ok": True,
        "reason": "issued" if existing is None else "renewed",
        "license_kind": license_kind,
        "fee": fee,
        "credits": int(assets.credits),
        "record": record,
    }


def _public_affiliations(sim, eid, affiliations):
    rows = []
    memberships = getattr(affiliations, "memberships", {}) if affiliations is not None else {}
    for raw_org_eid, membership in dict(memberships or {}).items():
        if not isinstance(membership, dict) or not bool(membership.get("active", True)):
            continue
        org_eid = _int(membership.get("organization_eid", raw_org_eid), -1)
        profile = organization_profile(sim, org_eid)
        if profile is None or _text(getattr(profile, "kind", "")).lower() not in PUBLIC_ORGANIZATION_KINDS:
            continue
        rows.append({
            "organization_eid": org_eid,
            "organization_name": _text(getattr(profile, "name", "")) or "Organization",
            "organization_kind": _text(getattr(profile, "kind", "")).lower(),
            "role": _text(membership.get("title") or membership.get("role") or "member").replace("_", " "),
            "primary": bool(membership.get("primary", False)),
        })
    rows.sort(key=lambda row: (not row.get("primary"), _text(row.get("organization_name")).lower()))
    return tuple(rows)


def _case_bookkeeping(cases, eid):
    corrected = 0
    resolved = 0
    provisional = 0
    for case in cases:
        if not isinstance(case, dict):
            continue
        if _int(case.get("resolved_subject_eid"), -1) == int(eid):
            resolved += 1
        for row in tuple(case.get("provisional_attributions", ()) or ()):
            if not isinstance(row, dict) or _int(row.get("actor_eid"), -1) != int(eid):
                continue
            status = _text(row.get("status", "active")).lower()
            if status == "misidentified" and bool(row.get("correction_applied", False)):
                corrected += 1
            elif status == "active":
                provisional += 1
    return {"corrected_case_count": corrected, "resolved_case_count": resolved, "provisional_case_count": provisional}


def civic_people_records(sim, prop=None):
    saved = _saved_entity_components(sim)
    properties = _properties_anywhere(sim)
    authority = civic_records_authority(sim, prop)
    scope_settlement = _text(authority.get("settlement_name"))
    traits = getattr(sim, "world_traits", {}) if isinstance(getattr(sim, "world_traits", None), dict) else {}
    killed = {
        _int(eid, -1)
        for eid in tuple(traits.get("killed_npc_eids", ()) or ())
    } if isinstance(traits.get("killed_npc_eids", ()), (list, tuple, set)) else set()
    cases = tuple(justice_identity_state(sim).get("cases", {}).values())
    records = []
    for eid in _all_registered_human_eids(sim, saved):
        identity = _identity_record(sim, eid, saved) or {}
        name = _text(identity.get("personal_name") or identity.get("display_name"))
        if not name:
            continue
        settlement = _actor_component(sim, eid, NPCSettlement, saved)
        routine = _actor_component(sim, eid, NPCRoutine, saved)
        occupation = _actor_component(sim, eid, Occupation, saved)
        vitality = _actor_component(sim, eid, Vitality, saved)
        affiliations = _actor_component(sim, eid, OrganizationAffiliations, saved)
        portfolio = _actor_component(sim, eid, PropertyPortfolio, saved)

        home_id = _text(getattr(settlement, "home_property_id", "")) if settlement is not None else ""
        if not home_id and routine is not None:
            home_id = _property_id_from_reference(getattr(routine, "home", None))
        work_id = ""
        if occupation is not None:
            work_id = _property_id_from_reference(getattr(occupation, "workplace", None))
        if not work_id and settlement is not None:
            work_id = _text(getattr(settlement, "work_property_id", ""))

        position = sim.ecs.get(Position).get(eid)
        if position is None:
            position = _component_from_map(saved.get(eid), Position)
        record_settlement = _property_settlement(sim, properties.get(home_id) or properties.get(work_id))
        if not record_settlement and position is not None:
            record_settlement = _settlement_for_position(sim, getattr(position, "x", 0), getattr(position, "y", 0))
        if scope_settlement and record_settlement and scope_settlement.lower() != record_settlement.lower():
            continue

        legal = justice_snapshot(sim, eid)
        deceased = eid in killed or bool(getattr(vitality, "dead", False))
        in_custody = bool(legal.get("in_custody", False)) and not deceased
        housing_status = _text(getattr(settlement, "housing_status", "")) if settlement is not None else ("housed" if home_id else "unhoused")
        employment_status = _text(getattr(settlement, "employment_status", "")) if settlement is not None else ("employed" if occupation is not None and work_id else "unemployed")
        career = _text(getattr(occupation, "career", "")) if occupation is not None else ""
        shift_start = getattr(occupation, "shift_start", None) if occupation is not None else None
        shift_end = getattr(occupation, "shift_end", None) if occupation is not None else None
        public_affiliations = _public_affiliations(sim, eid, affiliations)
        owned_ids = tuple(sorted(_text(value) for value in getattr(portfolio, "owned_property_ids", set()) if _text(value))) if portfolio is not None else ()
        licenses = civic_license_records(sim, eid)
        record = {
            "eid": eid,
            "name": name,
            "identity_snapshot": {
                "personal_name": name,
                "display_name": name,
                "gender_identity": _text(identity.get("gender_identity")).lower(),
                "pronoun_set": _text(identity.get("pronoun_set")).lower(),
                "creature_type": "human",
                "taxonomy_class": "hominid",
            },
            "status": "deceased" if deceased else "in_custody" if in_custody else "registered",
            "settlement_name": record_settlement or scope_settlement,
            "housing_status": housing_status or ("housed" if home_id else "unhoused"),
            "employment_status": employment_status or ("employed" if work_id else "unemployed"),
            "home_property_id": home_id,
            "home_name": _property_name(properties, home_id, "registered residence") if home_id else "",
            "work_property_id": work_id,
            "work_name": _property_name(properties, work_id, "registered workplace") if work_id else "",
            "career": career,
            "shift_start": shift_start,
            "shift_end": shift_end,
            "origin": _text(getattr(settlement, "origin", "")) if settlement is not None else "",
            "arrived_tick": _int(getattr(settlement, "arrived_tick", 0), 0) if settlement is not None else 0,
            "affiliations": public_affiliations,
            "owned_property_ids": owned_ids,
            "owned_property_names": tuple(_property_name(properties, property_id, property_id) for property_id in owned_ids),
            "licenses": licenses,
            "legal_tier": _text(legal.get("wanted_tier", "clear")).lower() or "clear",
            "active_legal_score": _int(legal.get("active_score", 0), 0),
            "last_exoneration_case_id": _text(legal.get("last_exoneration_case_id")),
            **_case_bookkeeping(cases, eid),
        }
        records.append(record)

    by_eid = {row["eid"]: row for row in records}
    home_counts = Counter(row.get("home_property_id") for row in records if row.get("home_property_id") and row.get("status") != "deceased")
    for row in records:
        row["household_count"] = int(home_counts.get(row.get("home_property_id"), 0))
        relationship = current_relationship_for_actor(sim, row["eid"], minimum_stage="spouse")
        spouse_eid = None
        if relationship and _text(relationship.get("stage")).lower() == "spouse":
            left = _int(relationship.get("left_eid"), -1)
            right = _int(relationship.get("right_eid"), -1)
            spouse_eid = right if left == row["eid"] else left if right == row["eid"] else None
        row["spouse_eid"] = spouse_eid
        row["spouse_name"] = _text((by_eid.get(spouse_eid) or {}).get("name")) if spouse_eid else ""
    records.sort(key=lambda row: (_text(row.get("name")).lower(), int(row.get("eid", 0))))
    return tuple(records)


def civic_census_lines(sim, prop=None, records=None):
    records = tuple(records if records is not None else civic_people_records(sim, prop))
    living = [row for row in records if row.get("status") != "deceased"]
    housed = sum(1 for row in living if row.get("home_property_id") or row.get("housing_status") == "housed")
    employed = sum(1 for row in living if row.get("work_property_id") or row.get("employment_status") == "employed")
    custody = sum(1 for row in living if row.get("status") == "in_custody")
    deceased = len(records) - len(living)
    households = len({row.get("home_property_id") for row in living if row.get("home_property_id")})
    civic_workers = sum(1 for row in living if any(aff.get("organization_kind") == "civic" for aff in row.get("affiliations", ())))
    licenses = civic_license_records(sim)
    active_licenses = sum(1 for row in licenses if row.get("status") == "active")
    authority = civic_records_authority(sim, prop)
    scope = _text(authority.get("settlement_name")) or "local jurisdiction"
    return (
        f"Census scope: {scope} under {authority['authority_name']}.",
        f"Registered people {len(living)} | housed {housed} | employed {employed} | in custody {custody}.",
        f"Households {households} | civic workers {civic_workers} | deceased records {deceased}.",
        f"Active licenses and permits {active_licenses}; ecology and recovery credentials file through this ledger.",
    )


def _license_line(record):
    kind = _text(record.get("license_kind", "license")).replace("_", " ").title()
    status = _text(record.get("status", "active")).replace("_", " ")
    issuer = _text(record.get("issuer_name") or record.get("issuer_organization_key"))
    restrictions = tuple(record.get("restrictions", ()) or ())
    line = f"{kind}: {status}"
    if issuer:
        line += f"; issued by {issuer}"
    if restrictions:
        line += f"; restrictions {', '.join(str(value) for value in restrictions)}"
    misuse_count = max(0, _int(record.get("misuse_count"), 0))
    if misuse_count:
        line += f"; official review flags {misuse_count}"
    return line + "."


def civic_license_ledger_lines(sim, prop=None, subject_eid=None, records=None):
    records = tuple(records if records is not None else civic_people_records(sim, prop))
    licenses = civic_license_records(sim, subject_eid)
    if subject_eid is not None:
        if licenses:
            return tuple(_license_line(row) for row in licenses)
        return ("No civic credentials are currently filed for this person.",)
    counts = Counter(_text(row.get("license_kind")).replace("_", " ") for row in licenses if row.get("status") == "active")
    lines = [f"Permit ledger: {sum(counts.values())} active credential(s) across {len(records)} registered file(s)."]
    if counts:
        lines.extend(f"{kind.title()}: {count} active." for kind, count in sorted(counts.items()))
    else:
        lines.append("No active permits are filed yet.")
    lines.append("Ecology and posted-recovery systems can issue, suspend, revoke, and verify credentials through this ledger.")
    return tuple(lines)


def civic_person_record_lines(sim, record, *, viewer_eid=None):
    if not isinstance(record, dict):
        return ("That civic record is unavailable.",)
    eid = _int(record.get("eid"), -1)
    identity = record.get("identity_snapshot") if isinstance(record.get("identity_snapshot"), dict) else {}
    pronouns = _text(identity.get("pronoun_set"))
    gender = _text(identity.get("gender_identity"))
    identity_bits = [bit for bit in (gender, pronouns) if bit]
    lines = [f"{record.get('name', 'Unknown person')} | civic status {str(record.get('status', 'registered')).replace('_', ' ')}."]
    if identity_bits:
        lines.append("Identity: " + " | ".join(identity_bits) + ".")
    settlement = _text(record.get("settlement_name"))
    origin = _text(record.get("origin")).replace("_", " ")
    registration = f"Registration: {str(record.get('housing_status', 'unhoused')).replace('_', ' ')}, {str(record.get('employment_status', 'unemployed')).replace('_', ' ')}"
    if settlement:
        registration += f" in {settlement}"
    if origin:
        registration += f"; origin {origin}"
    lines.append(registration + ".")
    if record.get("home_name"):
        household = _int(record.get("household_count"), 0)
        lines.append(f"Residence: {record['home_name']}" + (f" | household {household}." if household > 0 else "."))
    else:
        lines.append("Residence: no fixed address filed.")
    if record.get("career") or record.get("work_name"):
        career = _text(record.get("career")).replace("_", " ") or "worker"
        work_name = _text(record.get("work_name")) or "workplace on file"
        shift_start = record.get("shift_start")
        shift_end = record.get("shift_end")
        shift = f" | shift {int(shift_start):02d}:00-{int(shift_end):02d}:00" if shift_start is not None and shift_end is not None else ""
        lines.append(f"Employment: {career} at {work_name}{shift}.")
    else:
        lines.append("Employment: none filed.")
    if record.get("spouse_name"):
        lines.append(f"Civil status: married to {record['spouse_name']}.")
    affiliations = tuple(record.get("affiliations", ()) or ())
    if affiliations:
        labels = [f"{row.get('organization_name')} ({row.get('role', 'member')})" for row in affiliations[:4]]
        lines.append("Public affiliations: " + "; ".join(labels) + ".")
    owned = tuple(record.get("owned_property_names", ()) or ())
    if owned:
        lines.append("Registered property interests: " + ", ".join(owned[:4]) + ".")
    if record.get("status") == "deceased":
        lines.append("Vital record: deceased. The file remains in the historical census.")
    else:
        if _int(record.get("active_legal_score"), 0) > 0 or record.get("status") == "in_custody":
            lines.append(f"Public justice docket: {str(record.get('legal_tier', 'attention')).replace('_', ' ')}.")
        else:
            lines.append("Public justice docket: no active legal pressure.")
        if _int(record.get("corrected_case_count"), 0) > 0 or record.get("last_exoneration_case_id"):
            count = max(1, _int(record.get("corrected_case_count"), 0))
            lines.append(f"Case amendment: {count} provisional identification correction{'s' if count != 1 else ''} filed; the mistaken allegation is historical, not active.")
        if _int(record.get("provisional_case_count"), 0) > 0:
            lines.append("Public docket note: a provisional attribution remains unresolved and is not a confirmed identity finding.")
    lines.extend(civic_license_ledger_lines(sim, subject_eid=eid))
    if viewer_eid is not None and _int(viewer_eid, -2) == eid:
        lines.append("Your detailed legal read follows:")
        lines.extend(justice_summary_rows(sim, eid))
    lines.append("Private biology, appearance, witness identities, social history, and covert affiliations are not part of the public file.")
    return tuple(lines)


def remember_civic_record_inspection(sim, viewer_eid, record, *, property_id=None):
    if not isinstance(record, dict):
        return False
    subject_eid = _int(record.get("eid"), -1)
    viewer_eid = _int(viewer_eid, -1)
    if subject_eid <= 0 or viewer_eid <= 0 or subject_eid == viewer_eid:
        return False
    ledger = sim.ecs.get(ContactLedger).get(viewer_eid)
    if ledger is None:
        ledger = ContactLedger()
        sim.ecs.add(viewer_eid, ledger)
    existing = ledger.person_entry(subject_eid)
    benefits = {"known_name", "civic_record"}
    if isinstance(existing, dict):
        benefits.update(existing.get("benefits", ()))
    now = _int(getattr(sim, "tick", 0), 0)
    ledger.remember_person(
        subject_eid,
        source_eid=None,
        relation_kind=None if isinstance(existing, dict) else "civic_record",
        standing=0.0,
        tick=now,
        property_id=_text(property_id) or None,
        benefits=benefits,
        introduced=False,
        met_directly=False,
        identity_snapshot=dict(record.get("identity_snapshot") or {}),
    )
    ledger.remember_person_episode(
        subject_eid,
        kind="civic_record_inspected",
        tick=now,
        valence="neutral",
        summary=f"You inspected the public civic file for {record.get('name', 'this person')}.",
        property_id=_text(property_id) or None,
        source_topic="civic_records",
        dedupe_window=0,
    )
    note_person_notebook_mutation(
        sim,
        viewer_eid,
        subject_eid,
        before=dict(existing) if isinstance(existing, dict) else None,
        after=ledger.person_entry(subject_eid),
    )
    return True


__all__ = [
    "CIVIC_RECORDS_SERVICE_ID",
    "civic_census_lines",
    "civic_license_ledger_lines",
    "civic_license_records",
    "civic_people_records",
    "civic_person_record_lines",
    "civic_records_authority",
    "civic_records_state",
    "record_civic_license",
    "record_civic_license_misuse",
    "remember_civic_record_inspection",
]
