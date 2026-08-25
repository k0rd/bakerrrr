"""Jurisdictional public records exposed through civic service sites.

The registry is a view over canonical simulation state, not a second copy of
every NPC.  Live and streamed-out actors are read from ECS/chunk snapshots;
only issued licenses are stored here because those are records in their own
right.  Public reads deliberately omit private appearance, biology, social
memory, witness identity, and covert affiliations.
"""

from __future__ import annotations

import random
from collections import Counter

from engine.events import Event
from game.components import (
    AI,
    ContactLedger,
    CreatureIdentity,
    FinancialProfile,
    Inventory,
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
from game.property_access import property_is_open, site_services_for_property
from game.property_runtime import property_focus_position
from game.system_support.npc_income_runtime import inventory_liquid_credits, spend_npc_wallet_credits


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
BOUNTY_LICENSE_MISUSE_SUSPENSION_THRESHOLD = 2
BOUNTY_LICENSE_CRITICAL_MISUSE_KINDS = {"armed_force", "explosive_force", "lethal_force"}
BOUNTY_LICENSE_REVIEW_HOURS = 6
NPC_CIVIC_LICENSE_APPLICATIONS_STATE_KEY = "npc_civic_license_applications"
NPC_CIVIC_LICENSE_APPLICATION_SCAN_TICKS = 600
NPC_CIVIC_LICENSE_APPLICATION_RADIUS = 64

# These are people whose authored work can actually cross one of the three
# licensed seams.  A credential is common at spawn, not guaranteed, so the
# world still contains expired paperwork, informal operators, and deliberate
# poachers.  Institutional wildlife officers are the exception: their job
# itself presupposes current field authority.
PROFESSIONAL_CIVIC_LICENSE_START_CHANCES = {
    "hunting": {
        "wildlife_ranger": 1.0,
        "game_warden": 1.0,
        "conservation_officer": 1.0,
        "wildlife_enforcement_officer": 1.0,
        "hunter": 0.76,
        "trapper": 0.68,
    },
    "cultivation": {
        "herbalist": 0.86,
        "field_herbalist": 0.84,
        "cultivator": 0.82,
        "gardener": 0.8,
        "botanist": 0.74,
        "caretaker": 0.56,
        "remedy_mixer": 0.52,
        "recipe_keeper": 0.42,
        "drying_shelf_clerk": 0.38,
        "forager": 0.36,
    },
    "bounty": {
        "bounty_hunter": 0.84,
        "bounty_coordinator": 0.78,
        "field_pickup_dispatcher": 0.7,
        "recovery_agent": 0.7,
    },
}
PROFESSIONAL_CIVIC_LICENSE_ISSUERS = {
    "hunting": ("civic_licensing:wildlife", "Regional Wildlife Office"),
    "cultivation": ("civic_licensing:cultivation", "Regional Cultivation Registry"),
    "bounty": ("civic_licensing:recovery", "Recovery Licensing Office"),
}
LICENSE_ISSUER_SERVICES = {
    "hunting": frozenset({"civic_records"}),
    "cultivation": frozenset({"civic_records"}),
    "bounty": frozenset({"bounty_jobs", "civic_records"}),
}


def _text(value):
    return str(value or "").strip()


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _ticks_per_hour(sim):
    clock = getattr(sim, "world_traits", {}).get("clock", {})
    return max(1, _int((clock or {}).get("ticks_per_hour"), 600))


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
    subject_eid = _int(subject_eid, -1)
    if subject_eid <= 0 or not wanted:
        return None
    record = civic_records_state(sim)["licenses"].get(f"{subject_eid}:{wanted}")
    if not isinstance(record, dict):
        return None
    row = dict(record)
    expires = row.get("expires_tick")
    now = _int(getattr(sim, "tick", 0), 0)
    if row.get("status") == "active" and expires is not None and _int(expires, 0) > 0 and now >= _int(expires, 0):
        row["status"] = "expired"
    return row


def civic_license_is_active(sim, subject_eid, license_kind):
    record = civic_license_record(sim, subject_eid, license_kind)
    return bool(record and _text(record.get("status")).lower() == "active")


def professional_civic_license_kinds(career):
    """Return credentials relevant to work this career can actually perform."""

    career = _text(career).lower().replace(" ", "_")
    return tuple(
        license_kind
        for license_kind, career_chances in PROFESSIONAL_CIVIC_LICENSE_START_CHANCES.items()
        if career in career_chances
    )


def npc_is_lawful_civic_license_applicant(sim, subject_eid):
    """Use conduct, rather than hidden moral omniscience, to gate applications."""

    subject_eid = _int(subject_eid, -1)
    if subject_eid <= 0 or subject_eid == _int(getattr(sim, "player_eid", None), -2):
        return False
    ai = sim.ecs.get(AI).get(subject_eid)
    if ai is None:
        return False
    legal = justice_snapshot(sim, subject_eid)
    return bool(
        _text(legal.get("wanted_tier", "clear")).lower() == "clear"
        and not bool(legal.get("in_custody", False))
    )


def seed_professional_civic_licenses(
    sim,
    subject_eid,
    *,
    career="",
    workplace_prop=None,
    seed_token="",
):
    """Seed plausible pre-existing credentials without charging a new-game fee."""

    subject_eid = _int(subject_eid, -1)
    if subject_eid <= 0 or not npc_is_lawful_civic_license_applicant(sim, subject_eid):
        return ()
    if not career:
        occupation = sim.ecs.get(Occupation).get(subject_eid)
        career = getattr(occupation, "career", "") if occupation is not None else ""
    career = _text(career).lower().replace(" ", "_")
    issued = []
    for license_kind in professional_civic_license_kinds(career):
        if civic_license_record(sim, subject_eid, license_kind) is not None:
            continue
        chance = float(PROFESSIONAL_CIVIC_LICENSE_START_CHANCES[license_kind][career])
        rng = random.Random(
            f"{getattr(sim, 'seed', 0)}:professional-civic-license:{seed_token}:{subject_eid}:{career}:{license_kind}"
        )
        if rng.random() >= chance:
            continue
        issuer_key, issuer_name = PROFESSIONAL_CIVIC_LICENSE_ISSUERS[license_kind]
        settlement = _property_settlement(sim, workplace_prop)
        if settlement:
            issuer_key = f"{issuer_key}:{settlement.lower().replace(' ', '_')}"
            issuer_name = f"{settlement} {issuer_name.replace('Regional ', '')}"
        record = record_civic_license(
            sim,
            subject_eid,
            license_kind,
            issuer_organization_key=issuer_key,
            issuer_name=issuer_name,
            restrictions=LICENSE_RESTRICTIONS.get(license_kind, ()),
            notes=("Professional credential already on file when this person entered the simulation.",),
        )
        if record is not None:
            issued.append(record)
    return tuple(issued)


def _npc_civic_license_application_state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    state = traits.get(NPC_CIVIC_LICENSE_APPLICATIONS_STATE_KEY)
    if not isinstance(state, dict):
        state = {}
        traits[NPC_CIVIC_LICENSE_APPLICATIONS_STATE_KEY] = state
    if not isinstance(state.get("applications"), dict):
        state["applications"] = {}
    if not isinstance(state.get("next_scan_ticks"), dict):
        state["next_scan_ticks"] = {}
    return state


def npc_civic_license_application_for_actor(sim, subject_eid):
    state = _npc_civic_license_application_state(sim)
    row = state["applications"].get(str(_int(subject_eid, -1)))
    return dict(row) if isinstance(row, dict) else None


def _actor_civic_payment_balance(sim, subject_eid):
    assets = sim.ecs.get(PlayerAssets).get(subject_eid)
    if assets is not None:
        credits = max(0, _int(getattr(assets, "credits", 0), 0))
        return {
            "kind": "player_assets",
            "total": credits,
            "wallet_credits": credits,
            "bank_balance": 0,
        }
    inventory = sim.ecs.get(Inventory).get(subject_eid)
    finance = sim.ecs.get(FinancialProfile).get(subject_eid)
    wallet = inventory_liquid_credits(inventory)
    bank = max(0, _int(getattr(finance, "bank_balance", 0), 0)) if finance is not None else 0
    return {
        "kind": "npc_finance",
        "total": wallet + bank,
        "wallet_credits": wallet,
        "bank_balance": bank,
    }


def _spend_actor_civic_credits(sim, subject_eid, amount):
    amount = max(0, _int(amount, 0))
    funds = _actor_civic_payment_balance(sim, subject_eid)
    if amount <= 0 or funds["total"] < amount:
        return False, funds
    if funds["kind"] == "player_assets":
        assets = sim.ecs.get(PlayerAssets).get(subject_eid)
        assets.credits = max(0, _int(getattr(assets, "credits", 0), 0) - amount)
        return True, _actor_civic_payment_balance(sim, subject_eid)
    inventory = sim.ecs.get(Inventory).get(subject_eid)
    wallet_spent = spend_npc_wallet_credits(inventory, min(amount, funds["wallet_credits"]))
    remaining = amount - wallet_spent
    if remaining > 0:
        finance = sim.ecs.get(FinancialProfile).get(subject_eid)
        if finance is None or _int(getattr(finance, "bank_balance", 0), 0) < remaining:
            return False, _actor_civic_payment_balance(sim, subject_eid)
        finance.bank_balance = max(0, _int(getattr(finance, "bank_balance", 0), 0) - remaining)
    return True, _actor_civic_payment_balance(sim, subject_eid)


def _property_issues_civic_license(prop, license_kind):
    offered = {
        _text(service).lower()
        for service in site_services_for_property(prop)
        if _text(service)
    }
    return bool(offered.intersection(LICENSE_ISSUER_SERVICES.get(license_kind, ())))


def _nearby_civic_license_issuer(sim, subject_eid, license_kind):
    pos = sim.ecs.get(Position).get(subject_eid)
    if pos is None:
        return None
    candidates = []
    for property_id, prop in tuple(getattr(sim, "properties", {}).items()):
        if not isinstance(prop, dict) or not _property_issues_civic_license(prop, license_kind):
            continue
        if property_is_open(sim, prop) is not True:
            continue
        target = property_focus_position(prop)
        if not isinstance(target, (tuple, list)) or len(target) < 2:
            continue
        tx = _int(target[0], 0)
        ty = _int(target[1], 0)
        tz = _int(target[2], _int(prop.get("z"), 0)) if len(target) >= 3 else _int(prop.get("z"), 0)
        if tz != _int(getattr(pos, "z", 0), 0):
            continue
        distance = abs(tx - _int(getattr(pos, "x", 0), 0)) + abs(ty - _int(getattr(pos, "y", 0), 0))
        if distance > NPC_CIVIC_LICENSE_APPLICATION_RADIUS:
            continue
        resolved_id = _text(prop.get("id") or property_id)
        if resolved_id:
            candidates.append((distance, resolved_id, prop, (tx, ty, tz)))
    if not candidates:
        return None
    _distance, property_id, prop, target = min(candidates, key=lambda row: (row[0], row[1]))
    return {"property_id": property_id, "property_name": _property_name({property_id: prop}, property_id), "target": target}


def begin_npc_civic_license_application(sim, subject_eid):
    """Choose a nearby open issuer; actual filing waits for physical arrival."""

    subject_eid = _int(subject_eid, -1)
    state = _npc_civic_license_application_state(sim)
    key = str(subject_eid)
    applications = state["applications"]
    current = applications.get(key)
    if isinstance(current, dict):
        license_kind = _text(current.get("license_kind")).lower()
        if license_kind and not civic_license_is_active(sim, subject_eid, license_kind):
            prop = getattr(sim, "properties", {}).get(_text(current.get("property_id")))
            if isinstance(prop, dict):
                return dict(current)
        applications.pop(key, None)
    if not npc_is_lawful_civic_license_applicant(sim, subject_eid):
        return None
    occupation = sim.ecs.get(Occupation).get(subject_eid)
    career = _text(getattr(occupation, "career", "")).lower().replace(" ", "_") if occupation is not None else ""
    needed = []
    now = _int(getattr(sim, "tick", 0), 0)
    for license_kind in professional_civic_license_kinds(career):
        record = civic_license_record(sim, subject_eid, license_kind)
        if record is not None and _text(record.get("status")).lower() == "active":
            continue
        if record is not None and _text(record.get("status")).lower() == "revoked":
            continue
        if record is not None and _text(record.get("status")).lower() == "suspended":
            if now < _int(record.get("review_eligible_tick"), now):
                continue
        needed.append(license_kind)
    if not needed:
        return None
    next_scan = _int(state["next_scan_ticks"].get(key), 0)
    if now < next_scan:
        return None
    state["next_scan_ticks"][key] = now + NPC_CIVIC_LICENSE_APPLICATION_SCAN_TICKS
    funds = _actor_civic_payment_balance(sim, subject_eid)
    for license_kind in needed:
        if funds["total"] < int(LICENSE_FEES[license_kind]):
            continue
        issuer = _nearby_civic_license_issuer(sim, subject_eid, license_kind)
        if issuer is None:
            continue
        application = {
            "subject_eid": subject_eid,
            "license_kind": license_kind,
            "property_id": issuer["property_id"],
            "property_name": issuer["property_name"],
            "target": tuple(issuer["target"]),
            "started_tick": now,
        }
        applications[key] = application
        sim.emit(Event(
            "npc_civic_license_application_started",
            npc_eid=subject_eid,
            license_kind=license_kind,
            property_id=issuer["property_id"],
            property_name=issuer["property_name"],
            target=tuple(issuer["target"]),
        ))
        return dict(application)
    return None


def complete_npc_civic_license_application(sim, subject_eid):
    """File a pending application only while the NPC is physically at its issuer."""

    subject_eid = _int(subject_eid, -1)
    state = _npc_civic_license_application_state(sim)
    key = str(subject_eid)
    application = state["applications"].get(key)
    if not isinstance(application, dict):
        return {"ok": False, "reason": "no_application"}
    prop = getattr(sim, "properties", {}).get(_text(application.get("property_id")))
    pos = sim.ecs.get(Position).get(subject_eid)
    target = application.get("target")
    if not isinstance(prop, dict) or pos is None or not isinstance(target, (tuple, list)) or len(target) < 2:
        state["applications"].pop(key, None)
        return {"ok": False, "reason": "issuer_unavailable"}
    tx, ty = _int(target[0], 0), _int(target[1], 0)
    tz = _int(target[2], 0) if len(target) >= 3 else _int(prop.get("z"), 0)
    distance = abs(tx - _int(getattr(pos, "x", 0), 0)) + abs(ty - _int(getattr(pos, "y", 0), 0))
    if tz != _int(getattr(pos, "z", 0), 0) or distance > 1:
        return {"ok": False, "reason": "not_arrived", "target": (tx, ty, tz)}
    if property_is_open(sim, prop) is not True:
        state["applications"].pop(key, None)
        return {"ok": False, "reason": "issuer_closed"}
    if not npc_is_lawful_civic_license_applicant(sim, subject_eid):
        state["applications"].pop(key, None)
        return {"ok": False, "reason": "justice_hold"}
    result = purchase_civic_license(
        sim,
        subject_eid,
        _text(application.get("license_kind")).lower(),
        prop=prop,
    )
    state["applications"].pop(key, None)
    result = dict(result)
    result["application"] = dict(application)
    if result.get("ok"):
        sim.emit(Event(
            "npc_civic_license_application_filed",
            npc_eid=subject_eid,
            license_kind=application.get("license_kind"),
            property_id=application.get("property_id"),
            property_name=application.get("property_name"),
            fee=result.get("fee"),
        ))
    return result


def record_civic_license_misuse(
    sim,
    subject_eid,
    license_kind,
    *,
    reason,
    action="",
    misuse_kind="",
    severity_score=0,
    target_eid=None,
    incident_id=None,
):
    """Attach one deduplicated review flag and adjudicate bounty misuse."""

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
        "misuse_kind": _text(misuse_kind).lower(),
        "severity_score": max(0, _int(severity_score, 0)),
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
        if reference["incident_id"] is not None and reference["incident_id"] >= 0:
            if _int(row.get("incident_id"), -2) == reference["incident_id"]:
                return dict(record)
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
    previous_status = _text(record.get("status", "active")).lower() or "active"
    critical_misuse = bool(
        license_kind == "bounty"
        and reference["misuse_kind"] in BOUNTY_LICENSE_CRITICAL_MISUSE_KINDS
    )
    suspension_threshold_met = bool(
        license_kind == "bounty"
        and int(record["misuse_count"]) >= BOUNTY_LICENSE_MISUSE_SUSPENSION_THRESHOLD
    )
    suspended_now = bool(
        previous_status == "active"
        and (critical_misuse or suspension_threshold_met)
    )
    if suspended_now:
        review_ticks = BOUNTY_LICENSE_REVIEW_HOURS * _ticks_per_hour(sim)
        record.update({
            "status": "suspended",
            "suspended_tick": now,
            "suspension_reason": reference["reason"],
            "suspension_misuse_kind": reference["misuse_kind"],
            "suspension_incident_id": reference["incident_id"],
            "review_eligible_tick": now + review_ticks,
        })
    sim.emit(Event(
        "civic_license_misuse_noted",
        subject_eid=subject_eid,
        license_kind=license_kind,
        reason=reference["reason"],
        action=reference["action"],
        target_eid=reference["target_eid"],
        incident_id=reference["incident_id"],
        misuse_count=int(record["misuse_count"]),
        misuse_kind=reference["misuse_kind"],
        severity_score=reference["severity_score"],
        status=_text(record.get("status", "active")).lower(),
    ))
    if suspended_now:
        sim.emit(Event(
            "civic_license_suspended",
            subject_eid=subject_eid,
            license_kind=license_kind,
            reason=reference["reason"],
            action=reference["action"],
            misuse_kind=reference["misuse_kind"],
            incident_id=reference["incident_id"],
            misuse_count=int(record["misuse_count"]),
            review_eligible_tick=int(record["review_eligible_tick"]),
            critical_misuse=critical_misuse,
        ))
    return dict(record)


def purchase_civic_license(sim, subject_eid, license_kind, *, prop=None):
    """Buy or renew one ordinary civic credential at an issuing office."""

    license_kind = _text(license_kind).lower().replace(" ", "_")
    if license_kind not in LICENSE_FEES:
        return {"ok": False, "reason": "unsupported", "license_kind": license_kind}
    existing = civic_license_record(sim, subject_eid, license_kind)
    existing_status = _text((existing or {}).get("status")).lower()
    if existing and existing_status == "active":
        return {
            "ok": False,
            "reason": "already_active",
            "license_kind": license_kind,
            "record": existing,
        }
    if existing and existing_status == "revoked":
        return {
            "ok": False,
            "reason": "revoked",
            "license_kind": license_kind,
            "record": existing,
        }
    if existing and existing_status == "suspended":
        now = _int(getattr(sim, "tick", 0), 0)
        review_eligible_tick = max(now, _int(existing.get("review_eligible_tick"), now))
        if now < review_eligible_tick:
            return {
                "ok": False,
                "reason": "suspended",
                "license_kind": license_kind,
                "review_eligible_tick": review_eligible_tick,
                "review_remaining_ticks": review_eligible_tick - now,
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
    funds = _actor_civic_payment_balance(sim, subject_eid)
    credits = int(funds["total"])
    fee = int(LICENSE_FEES[license_kind])
    if credits < fee:
        return {
            "ok": False,
            "reason": "no_credits",
            "license_kind": license_kind,
            "fee": fee,
            "credits": credits,
            "wallet_credits": int(funds["wallet_credits"]),
            "bank_balance": int(funds["bank_balance"]),
        }
    authority = civic_records_authority(sim, prop)
    paid, remaining_funds = _spend_actor_civic_credits(sim, subject_eid, fee)
    if not paid:
        return {
            "ok": False,
            "reason": "payment_failed",
            "license_kind": license_kind,
            "fee": fee,
            "credits": int(remaining_funds["total"]),
            "wallet_credits": int(remaining_funds["wallet_credits"]),
            "bank_balance": int(remaining_funds["bank_balance"]),
        }
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
        applicant_kind="player" if remaining_funds["kind"] == "player_assets" else "npc",
    ))
    return {
        "ok": True,
        "reason": "issued" if existing is None else "renewed",
        "license_kind": license_kind,
        "fee": fee,
        "credits": int(remaining_funds["total"]),
        "wallet_credits": int(remaining_funds["wallet_credits"]),
        "bank_balance": int(remaining_funds["bank_balance"]),
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
    people_by_eid = {
        _int(row.get("eid"), -1): row
        for row in records
        if isinstance(row, dict) and _int(row.get("eid"), -1) > 0
    }
    licenses = tuple(
        row
        for row in licenses
        if _int(row.get("subject_eid"), -1) in people_by_eid
    )
    counts = Counter(_text(row.get("license_kind")).replace("_", " ") for row in licenses if row.get("status") == "active")
    lines = [f"Permit ledger: {sum(counts.values())} active credential(s) across {len(records)} registered file(s)."]
    if counts:
        lines.extend(f"{kind.title()}: {count} active." for kind, count in sorted(counts.items()))
    else:
        lines.append("No active permits are filed yet.")
    filed_by_holder = {}
    for license_record in licenses:
        holder_eid = _int(license_record.get("subject_eid"), -1)
        filed_by_holder.setdefault(holder_eid, []).append(license_record)
    if filed_by_holder:
        lines.append("Filed holders:")
        holder_rows = []
        for holder_eid, holder_licenses in filed_by_holder.items():
            person = people_by_eid.get(holder_eid, {})
            name = _text(person.get("name")) or f"Registered person {holder_eid}"
            credentials = "; ".join(
                f"{_text(row.get('license_kind', 'license')).replace('_', ' ').title()} {_text(row.get('status', 'active')).replace('_', ' ')}"
                for row in sorted(holder_licenses, key=lambda item: _text(item.get("license_kind")))
            )
            holder_rows.append((name.lower(), f"{name}: {credentials}."))
        lines.extend(line for _sort_name, line in sorted(holder_rows))
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
    "BOUNTY_LICENSE_CRITICAL_MISUSE_KINDS",
    "BOUNTY_LICENSE_MISUSE_SUSPENSION_THRESHOLD",
    "BOUNTY_LICENSE_REVIEW_HOURS",
    "CIVIC_RECORDS_SERVICE_ID",
    "civic_census_lines",
    "civic_license_ledger_lines",
    "civic_license_is_active",
    "civic_license_record",
    "civic_license_records",
    "civic_people_records",
    "civic_person_record_lines",
    "civic_records_authority",
    "civic_records_state",
    "record_civic_license",
    "record_civic_license_misuse",
    "purchase_civic_license",
    "remember_civic_record_inspection",
]
