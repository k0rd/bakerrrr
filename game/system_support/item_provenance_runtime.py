"""Shared item claim, provenance, and justice-inspection helpers."""

from __future__ import annotations

import random

from game.components import IncidentKnowledge, Inventory, Occupation
from game.incident_runtime import incident_record, incident_records
from game.item_semantics import item_legal_status, item_tags
from game.organizations import actor_org_memberships, occupation_targets_property
from game.property_access import evaluate_property_access
from game.property_runtime import property_covering


CLAIM_PUBLIC_FREE = "public_free"
CLAIM_MERCHANDISE = "merchandise"
CLAIM_PRIVATE_EFFECT = "private_effect"
CLAIM_STAFF_SUPPLY = "staff_supply"
CLAIM_SCENE_SALVAGE = "scene_salvage"

CLAIM_CLASSES = {
    CLAIM_PUBLIC_FREE,
    CLAIM_MERCHANDISE,
    CLAIM_PRIVATE_EFFECT,
    CLAIM_STAFF_SUPPLY,
    CLAIM_SCENE_SALVAGE,
}

PUBLIC_OWNER_TAGS = {"", "public", "unowned", "city", "none", "neutral"}
SALVAGE_OWNER_TAGS = {"bones", "scene", "cache", "opportunity_reward"}
SCENE_SALVAGE_CONTEXTS = {"scene_salvage", "cache", "bones", "salvage", "cache_withdraw"}
MERCHANDISE_CONTEXTS = {"store_stock", "trade_purchase", "trade_stock"}
PRIVATE_CONTEXTS = {"actor_drop", "corpse_loot", "corpse_drop", "personal_drop"}


def _text(value):
    return str(value or "").strip()


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _normalize_claim_class(value, default=CLAIM_PUBLIC_FREE):
    key = _text(value).lower()
    if key in CLAIM_CLASSES:
        return key
    if default is None:
        return None
    return str(default or CLAIM_PUBLIC_FREE)


def _property_for_item(sim, item_entry):
    if sim is None:
        return None
    if not isinstance(item_entry, dict):
        return None
    x = item_entry.get("x")
    y = item_entry.get("y")
    z = item_entry.get("z", 0)
    try:
        return property_covering(sim, int(x), int(y), int(z))
    except (TypeError, ValueError):
        return None


def _property_owner_tag(prop):
    return _text((prop or {}).get("owner_tag")).lower()


def _entry_metadata(entry):
    metadata = entry.get("metadata") if isinstance((entry or {}).get("metadata"), dict) else {}
    return dict(metadata)


def _set_optional_metadata(metadata, key, value):
    if not isinstance(metadata, dict):
        return metadata
    if isinstance(value, str):
        clean = value.strip()
        if clean:
            metadata[key] = clean
        else:
            metadata.pop(key, None)
        return metadata
    if value is None:
        metadata.pop(key, None)
        return metadata
    metadata[key] = value
    return metadata


def _actor_has_site_authority(sim, actor_eid, prop):
    if actor_eid is None or not isinstance(prop, dict):
        return False
    try:
        actor_eid = int(actor_eid)
    except (TypeError, ValueError):
        return False
    if prop.get("owner_eid") == actor_eid:
        return True
    occupation = sim.ecs.get(Occupation).get(actor_eid)
    if occupation_targets_property(prop, occupation):
        return True
    property_id = _text(prop.get("id"))
    building_id = _text((prop.get("metadata") or {}).get("building_id")) if isinstance(prop.get("metadata"), dict) else ""
    for membership in actor_org_memberships(sim, actor_eid, active_only=True):
        site_property_id = _text(membership.get("site_property_id"))
        site_building_id = _text(membership.get("site_building_id"))
        if property_id and site_property_id == property_id:
            return True
        if building_id and site_building_id == building_id:
            return True
    return False


def classify_item_claim(sim, item_entry, *, prop=None, source_context=None, default_claim_class=None):
    entry = item_entry if isinstance(item_entry, dict) else {}
    metadata = _entry_metadata(entry)
    prop = prop if isinstance(prop, dict) else _property_for_item(sim, entry)
    owner_eid = entry.get("owner_eid", metadata.get("source_owner_eid"))
    owner_tag = _text(entry.get("owner_tag", metadata.get("source_owner_tag"))).lower()
    source_context = _text(source_context or metadata.get("source_context")).lower()

    explicit = _normalize_claim_class(metadata.get("claim_class"), default=None)
    if explicit in CLAIM_CLASSES:
        claim_class = explicit
    elif source_context in PRIVATE_CONTEXTS:
        claim_class = CLAIM_PRIVATE_EFFECT
    elif source_context in SCENE_SALVAGE_CONTEXTS or owner_tag in SALVAGE_OWNER_TAGS:
        claim_class = CLAIM_SCENE_SALVAGE
    elif source_context in MERCHANDISE_CONTEXTS:
        claim_class = CLAIM_MERCHANDISE
    elif owner_eid is not None or owner_tag in {"player", "npc", "private"}:
        claim_class = CLAIM_PRIVATE_EFFECT
    elif sim is not None and isinstance(prop, dict):
        owner_tag_prop = _property_owner_tag(prop)
        if owner_tag_prop in PUBLIC_OWNER_TAGS and owner_eid is None:
            claim_class = CLAIM_PUBLIC_FREE
        else:
            access = None
            try:
                access = evaluate_property_access(
                    sim,
                    entry.get("owner_eid"),
                    prop,
                    x=entry.get("x", prop.get("x")),
                    y=entry.get("y", prop.get("y")),
                    z=entry.get("z", prop.get("z", 0)),
                )
            except Exception:
                access = None
            public_facing = bool(getattr(access, "public_facing", False) or getattr(access, "currently_open", False))
            claim_class = CLAIM_MERCHANDISE if public_facing else CLAIM_STAFF_SUPPLY
    elif owner_tag in PUBLIC_OWNER_TAGS:
        claim_class = CLAIM_PUBLIC_FREE
    else:
        claim_class = _normalize_claim_class(default_claim_class, default=CLAIM_PUBLIC_FREE)

    source_owner_eid = metadata.get("source_owner_eid", owner_eid)
    source_owner_tag = _text(metadata.get("source_owner_tag", owner_tag)).lower()
    source_actor_eid = metadata.get("source_actor_eid", source_owner_eid)
    source_property_id = _text(metadata.get("source_property_id") or metadata.get("stolen_property_id") or ((prop or {}).get("id")))
    source_org_eid = metadata.get("source_organization_eid")
    latent_claim_violation = bool(metadata.get("latent_claim_violation", False))

    return {
        "claim_class": claim_class,
        "source_owner_eid": source_owner_eid,
        "source_owner_tag": source_owner_tag,
        "source_property_id": source_property_id or None,
        "source_organization_eid": source_org_eid,
        "source_actor_eid": source_actor_eid,
        "source_incident_id": metadata.get("source_incident_id"),
        "source_victim_eid": metadata.get("source_victim_eid"),
        "source_context": source_context or None,
        "latent_claim_violation": latent_claim_violation,
        "last_transfer_tick": metadata.get("last_transfer_tick"),
        "last_transfer_kind": _text(metadata.get("last_transfer_kind")).lower() or None,
        "last_holder_eid": metadata.get("last_holder_eid"),
    }


def stamp_item_provenance(
    sim,
    item_entry,
    *,
    prop=None,
    source_context=None,
    claim_class=None,
    source_owner_eid=None,
    source_owner_tag=None,
    source_property_id=None,
    source_organization_eid=None,
    source_actor_eid=None,
    source_incident_id=None,
    source_victim_eid=None,
    latent_claim_violation=None,
    last_transfer_tick=None,
    last_transfer_kind=None,
    last_holder_eid=None,
):
    entry = item_entry if isinstance(item_entry, dict) else {}
    metadata = _entry_metadata(entry)
    base = classify_item_claim(
        sim,
        {
            **entry,
            "metadata": metadata,
        },
        prop=prop,
        source_context=source_context,
        default_claim_class=claim_class,
    )
    if claim_class is not None:
        base["claim_class"] = _normalize_claim_class(claim_class, default=base["claim_class"])
    if source_owner_eid is not None:
        base["source_owner_eid"] = source_owner_eid
    if source_owner_tag is not None:
        base["source_owner_tag"] = _text(source_owner_tag).lower() or None
    if source_property_id is not None:
        base["source_property_id"] = _text(source_property_id) or None
    if source_organization_eid is not None:
        base["source_organization_eid"] = source_organization_eid
    if source_actor_eid is not None:
        base["source_actor_eid"] = source_actor_eid
    if source_incident_id is not None:
        base["source_incident_id"] = source_incident_id
    if source_victim_eid is not None:
        base["source_victim_eid"] = source_victim_eid
    if source_context is not None:
        base["source_context"] = _text(source_context).lower() or None
    if latent_claim_violation is not None:
        base["latent_claim_violation"] = bool(latent_claim_violation)
    if last_transfer_tick is not None:
        base["last_transfer_tick"] = _safe_int(last_transfer_tick, default=0)
    if last_transfer_kind is not None:
        base["last_transfer_kind"] = _text(last_transfer_kind).lower() or None
    if last_holder_eid is not None:
        base["last_holder_eid"] = last_holder_eid

    metadata["claim_class"] = base["claim_class"]
    _set_optional_metadata(metadata, "source_owner_eid", base.get("source_owner_eid"))
    _set_optional_metadata(metadata, "source_owner_tag", base.get("source_owner_tag"))
    _set_optional_metadata(metadata, "source_property_id", base.get("source_property_id"))
    _set_optional_metadata(metadata, "source_organization_eid", base.get("source_organization_eid"))
    _set_optional_metadata(metadata, "source_actor_eid", base.get("source_actor_eid"))
    _set_optional_metadata(metadata, "source_incident_id", base.get("source_incident_id"))
    _set_optional_metadata(metadata, "source_victim_eid", base.get("source_victim_eid"))
    _set_optional_metadata(metadata, "source_context", base.get("source_context"))
    metadata["latent_claim_violation"] = bool(base.get("latent_claim_violation"))
    _set_optional_metadata(metadata, "last_transfer_tick", base.get("last_transfer_tick"))
    _set_optional_metadata(metadata, "last_transfer_kind", base.get("last_transfer_kind"))
    _set_optional_metadata(metadata, "last_holder_eid", base.get("last_holder_eid"))
    return metadata


def item_entitlement_for_actor(sim, actor_eid, item_entry, *, prop=None, source_context=None):
    entry = item_entry if isinstance(item_entry, dict) else {}
    prop = prop if isinstance(prop, dict) else _property_for_item(sim, entry)
    claim = classify_item_claim(sim, entry, prop=prop, source_context=source_context)
    claim_class = claim["claim_class"]
    metadata = _entry_metadata(entry)
    source_owner_eid = claim.get("source_owner_eid")
    source_actor_eid = claim.get("source_actor_eid")

    authorized = False
    reason = "claimed"
    if claim_class in {CLAIM_PUBLIC_FREE, CLAIM_SCENE_SALVAGE}:
        authorized = True
        reason = "claimable"
    elif source_owner_eid is not None and int(source_owner_eid) == _safe_int(actor_eid, default=-1):
        authorized = True
        reason = "owner"
    elif source_actor_eid is not None and int(source_actor_eid) == _safe_int(actor_eid, default=-1):
        authorized = True
        reason = "source_owner"
    elif claim_class in {CLAIM_MERCHANDISE, CLAIM_STAFF_SUPPLY} and isinstance(prop, dict) and _actor_has_site_authority(sim, actor_eid, prop):
        authorized = True
        reason = "site_authority"
    elif claim_class == CLAIM_PRIVATE_EFFECT and isinstance(prop, dict) and _actor_has_site_authority(sim, actor_eid, prop):
        authorized = True
        reason = "authorized_handling"

    latent_claim_violation = bool(claim.get("latent_claim_violation", False))
    if not authorized and claim_class not in {CLAIM_PUBLIC_FREE, CLAIM_SCENE_SALVAGE}:
        latent_claim_violation = True

    return {
        **claim,
        "authorized": bool(authorized),
        "lawful_take": bool(authorized),
        "latent_claim_violation": bool(latent_claim_violation),
        "reason": reason,
        "property_id": _text((prop or {}).get("id")) or None,
        "property_name": _text((prop or {}).get("name")) or None,
        "owner_eid": entry.get("owner_eid"),
        "owner_tag": _text(entry.get("owner_tag")).lower() or None,
        "metadata": metadata,
    }


def _reported_incidents(sim, *, inspector_eid=None):
    if inspector_eid is not None:
        try:
            inspector_eid = int(inspector_eid)
        except (TypeError, ValueError):
            inspector_eid = None
    if inspector_eid is not None:
        knowledge = sim.ecs.get(IncidentKnowledge).get(inspector_eid)
        if isinstance(knowledge, IncidentKnowledge) and isinstance(getattr(knowledge, "records", None), dict):
            known_rows = []
            for incident_id, knowledge_row in knowledge.records.items():
                incident = incident_record(sim, incident_id)
                if not isinstance(incident, dict):
                    continue
                if not bool(incident.get("officially_reported") or incident.get("justice_accounted")):
                    continue
                category = _text((knowledge_row or {}).get("category")).lower()
                if category != "official":
                    continue
                known_rows.append(incident)
            if known_rows:
                return tuple(
                    row
                    for row in sorted(
                        known_rows,
                        key=lambda incident: (
                            _safe_int(incident.get("justice_accounted_tick", incident.get("reported_tick", incident.get("last_observed_tick", 0))), default=0),
                            _safe_int(incident.get("id"), default=0),
                        ),
                        reverse=True,
                    )
                )
    rows = []
    for incident in incident_records(sim):
        if not isinstance(incident, dict):
            continue
        if not bool(incident.get("officially_reported") or incident.get("justice_accounted")):
            continue
        rows.append(incident)
    return tuple(rows)


def _reported_incident_pairs(sim, *, inspector_eid=None):
    if inspector_eid is not None:
        try:
            inspector_eid = int(inspector_eid)
        except (TypeError, ValueError):
            inspector_eid = None
    if inspector_eid is not None:
        knowledge = sim.ecs.get(IncidentKnowledge).get(inspector_eid)
        if isinstance(knowledge, IncidentKnowledge) and isinstance(getattr(knowledge, "records", None), dict):
            pairs = []
            for incident in _reported_incidents(sim, inspector_eid=inspector_eid):
                if not isinstance(incident, dict):
                    continue
                pairs.append((incident, knowledge.records.get(_safe_int(incident.get("id"), default=0))))
            if pairs:
                return tuple(pairs)
    return tuple((incident, None) for incident in _reported_incidents(sim))


def _exact_official_item_link_match(item_entry, knowledge_row):
    if not isinstance(knowledge_row, dict) or not isinstance(item_entry, dict):
        return None
    target_instance_id = _text(item_entry.get("instance_id"))
    if not target_instance_id:
        return None
    for raw_row in tuple(knowledge_row.get("official_item_links", ()) or ()):
        if not isinstance(raw_row, dict):
            continue
        if _text(raw_row.get("instance_id")) != target_instance_id:
            continue
        return {
            "instance_id": target_instance_id,
            "item_id": _text(raw_row.get("item_id")).lower() or None,
            "link_kind": _text(raw_row.get("link_kind")).lower() or None,
            "property_id": _text(raw_row.get("property_id")) or None,
            "victim_eid": raw_row.get("victim_eid"),
            "summary_label": _text(raw_row.get("summary_label")) or None,
        }
    return None


def _match_reason_label(match_reason):
    reason_key = _text(match_reason).lower()
    return {
        "victim_inventory": "victim personal effects",
        "precombat_stolen_from_victim": "property taken during the assault",
        "scene_claimed": "claimed scene property",
        "scene_residue": "scene residue",
    }.get(reason_key, "")


def _match_label(match):
    match = match if isinstance(match, dict) else {}
    summary = _text(match.get("summary"))
    reason_label = _match_reason_label(match.get("match_reason"))
    if summary and reason_label and reason_label.lower() not in summary.lower():
        return f"{summary} ({reason_label})"
    return summary or reason_label or "reported incident"


def match_item_against_reported_crime(sim, item_entry, *, offender_eid=None, inspector_eid=None):
    entry = item_entry if isinstance(item_entry, dict) else {}
    metadata = _entry_metadata(entry)
    source_incident_id = _safe_int(metadata.get("source_incident_id"), default=0)
    source_property_id = _text(metadata.get("source_property_id"))
    source_victim_eid = metadata.get("source_victim_eid")
    source_owner_eid = metadata.get("source_owner_eid")
    source_actor_eid = metadata.get("source_actor_eid")

    best = None
    best_rank = None
    for incident, knowledge_row in _reported_incident_pairs(sim, inspector_eid=inspector_eid):
        incident_id = _safe_int(incident.get("id"), default=0)
        if incident_id <= 0:
            continue
        kind = _text(incident.get("kind")).lower()
        severity = _safe_int(incident.get("severity"), default=0)
        report_tick = _safe_int(
            incident.get("reported_tick", incident.get("justice_accounted_tick", incident.get("last_observed_tick", 0))),
            default=0,
        )

        match_kind = ""
        match_reason = ""
        exact_link = _exact_official_item_link_match(entry, knowledge_row)
        if exact_link:
            match_kind = "reported_stolen" if kind == "item_stolen" else "incident_evidence"
            match_reason = _text(exact_link.get("link_kind")).lower()
        if source_incident_id > 0 and incident_id == source_incident_id:
            match_kind = "reported_stolen" if kind == "item_stolen" else "incident_evidence"
        elif kind == "item_stolen":
            if source_property_id and source_property_id == _text(incident.get("property_id")):
                match_kind = "reported_stolen"
            elif source_owner_eid is not None and incident.get("owner_eid") is not None and int(source_owner_eid) == int(incident.get("owner_eid")):
                match_kind = "reported_stolen"
        else:
            violent = kind == "action_offense" and _text(incident.get("context")).lower() in {
                "unarmed_assault",
                "melee_assault",
                "armed_assault",
                "explosive_discharge",
            }
            if violent:
                if source_victim_eid is not None and incident.get("victim_eid") is not None and int(source_victim_eid) == int(incident.get("victim_eid")):
                    match_kind = "incident_evidence"
                elif source_actor_eid is not None and incident.get("victim_eid") is not None and int(source_actor_eid) == int(incident.get("victim_eid")):
                    match_kind = "incident_evidence"
                elif source_property_id and source_property_id == _text(incident.get("property_id")) and source_owner_eid is not None:
                    match_kind = "incident_evidence"

        if not match_kind:
            continue
        exact_rank = 1 if exact_link else 0
        reason_rank = {
            "victim_inventory": 4,
            "precombat_stolen_from_victim": 4,
            "scene_claimed": 3,
            "scene_residue": 2,
        }.get(match_reason, 0)
        rank = (
            exact_rank,
            1 if match_kind == "incident_evidence" else 0,
            reason_rank,
            severity,
            report_tick,
            incident_id,
        )
        if best_rank is None or rank > best_rank:
            label = _text(
                (exact_link or {}).get("summary_label")
                or incident.get("victim_name")
                or incident.get("note")
                or incident.get("property_name")
                or incident.get("kind")
            ).strip()
            best = {
                "match_kind": match_kind,
                "match_reason": match_reason or None,
                "incident_id": incident_id,
                "incident_kind": kind,
                "summary": label or "reported incident",
                "violent": bool(match_kind == "incident_evidence"),
                "property_id": _text(incident.get("property_id")) or None,
                "victim_eid": incident.get("victim_eid"),
            }
            best_rank = rank
    return best


def evaluate_inventory_for_justice(sim, offender_eid, *, current_tick=None, inventory=None, update_inventory=True, inspector_eid=None):
    if current_tick is None:
        current_tick = _safe_int(getattr(sim, "tick", 0), default=0)
    actor_inventory = inventory
    if actor_inventory is None:
        actor_inventory = sim.ecs.get(Inventory).get(offender_eid)
    if actor_inventory is None:
        return {
            "lawful": (),
            "contraband": (),
            "latent_claim_violation": (),
            "reported_stolen": (),
            "incident_evidence": (),
            "counts": {
                "lawful": 0,
                "contraband": 0,
                "latent_claim_violation": 0,
                "reported_stolen": 0,
                "incident_evidence": 0,
            },
            "severity_bucket": "clear",
            "match_summaries": (),
            "incident_match_labels": (),
            "incident_match_reasons": (),
        }

    buckets = {
        "lawful": [],
        "contraband": [],
        "latent_claim_violation": [],
        "reported_stolen": [],
        "incident_evidence": [],
    }
    summaries = []
    match_labels = []
    match_reasons = []

    for entry in list(getattr(actor_inventory, "items", ()) or ()):
        item_id = _text(entry.get("item_id")).lower()
        metadata = _entry_metadata(entry)
        legal_status = _text(item_legal_status(entry)).lower() or "legal"
        contraband = legal_status in {"illegal", "restricted"}
        claim = classify_item_claim(sim, entry)
        should_attempt_match = bool(
            claim.get("latent_claim_violation")
            or metadata.get("source_incident_id")
            or metadata.get("source_victim_eid")
        )
        match = (
            match_item_against_reported_crime(
                sim,
                entry,
                offender_eid=offender_eid,
                inspector_eid=inspector_eid,
            )
            if should_attempt_match
            else None
        )
        target_bucket = "lawful"
        if bool(metadata.get("justice_incident_evidence")):
            target_bucket = "incident_evidence"
        elif bool(metadata.get("justice_reported_stolen")) or (bool(metadata.get("justice_stolen")) and not bool(metadata.get("latent_claim_violation"))):
            target_bucket = "reported_stolen"
        elif match and match.get("match_kind") == "incident_evidence":
            target_bucket = "incident_evidence"
        elif match and match.get("match_kind") == "reported_stolen":
            target_bucket = "reported_stolen"
        elif contraband:
            target_bucket = "contraband"
        elif claim.get("latent_claim_violation"):
            target_bucket = "latent_claim_violation"

        updated_metadata = dict(metadata)
        if match:
            if match.get("match_kind") == "reported_stolen":
                updated_metadata["justice_reported_stolen"] = True
            elif match.get("match_kind") == "incident_evidence":
                updated_metadata["justice_incident_evidence"] = True
            updated_metadata["justice_discovered_tick"] = int(current_tick)
            updated_metadata["justice_discovered_from_incident_id"] = int(match.get("incident_id", 0) or 0)
            if update_inventory and hasattr(actor_inventory, "update_item_metadata"):
                actor_inventory.update_item_metadata(entry.get("instance_id"), updated_metadata, replace=True)

        row = {
            "instance_id": entry.get("instance_id"),
            "item_id": item_id,
            "quantity": max(1, _safe_int(entry.get("quantity"), default=1)),
            "metadata": updated_metadata,
            "legal_status": legal_status,
            "claim_class": claim.get("claim_class"),
            "match": dict(match) if isinstance(match, dict) else None,
        }
        buckets[target_bucket].append(row)
        if match:
            label = _match_label(match)
            if label:
                summaries.append(str(match.get("summary", label)).strip())
                match_labels.append(label)
            reason = _text(match.get("match_reason")).lower()
            if reason:
                match_reasons.append(reason)

    counts = {
        key: int(sum(max(1, _safe_int(row.get("quantity"), default=1)) for row in rows))
        for key, rows in buckets.items()
    }
    if counts["incident_evidence"] > 0:
        severity_bucket = "violent_evidence"
    elif counts["reported_stolen"] > 0:
        severity_bucket = "property_crime"
    elif counts["contraband"] > 0:
        severity_bucket = "contraband"
    elif counts["latent_claim_violation"] > 0:
        severity_bucket = "latent_claim"
    else:
        severity_bucket = "clear"
    return {
        **{key: tuple(value) for key, value in buckets.items()},
        "counts": counts,
        "severity_bucket": severity_bucket,
        "match_summaries": tuple(dict.fromkeys(summary for summary in summaries if summary))[:4],
        "incident_match_labels": tuple(dict.fromkeys(label for label in match_labels if label))[:4],
        "incident_match_reasons": tuple(dict.fromkeys(reason for reason in match_reasons if reason))[:4],
    }


def justice_enforcement_profile(sim, *, jurisdiction_key="", source_property_id="", source_property_name="", offender_eid=None):
    seed = f"{getattr(sim, 'seed', '')}:justice-enforcement:{_text(jurisdiction_key).lower()}:{_text(source_property_id).lower()}:{_text(source_property_name).lower()}"
    rng = random.Random(seed)
    baseline = 0.34 + (rng.random() * 0.32)
    moderation = 0.0
    prop = sim.properties.get(source_property_id) if _text(source_property_id) else None
    if isinstance(prop, dict):
        owner_tag = _property_owner_tag(prop)
        if owner_tag in {"public", "city"}:
            moderation += 0.05
        metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
        archetype = _text(metadata.get("archetype", prop.get("kind"))).lower()
        if archetype in {"community_center", "library", "shelter", "clinic", "church"}:
            moderation += 0.08
    strictness = max(0.18, min(0.92, baseline - moderation))
    return {
        "strictness": float(strictness),
        "lenient": bool(strictness <= 0.42),
        "citation_pref": bool(strictness <= 0.54),
        "keep_contraband_possible": bool(strictness <= 0.34),
    }
