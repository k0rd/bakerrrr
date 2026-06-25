"""Deterministic organization practice emergence from live branch activity."""

from __future__ import annotations

import random

from engine.systems import System
from game.components import OrganizationPracticeProgress, OrganizationProfile
from game.items import ITEM_CATALOG
from game.organizations import (
    organization_child_organizations,
    organization_policy_snapshot,
    organization_practice_progress_rows,
    organization_profile,
    property_field_domains,
    property_org_links,
    property_service_ids,
    record_organization_practice,
    record_organization_practice_progress,
)
from game.incident_runtime import incident_record
from game.system_support.awareness_runtime import event_observation_accountability
from game.vision_scene_runtime import event_is_vision_only


LINK_KIND_WEIGHTS = {
    "operates": 1.0,
    "service_host": 0.75,
    "meeting_place": 0.6,
    "safehouse": 0.75,
    "territory": 0.35,
}
EVALUATION_INTERVAL = 120
TIER1_THRESHOLD = 10.0
TIER2_THRESHOLD = 24.0
ROOT_PROMOTION_THRESHOLD = 40.0
COLLECTIVE_FAMILIES = {"labor_union", "trade_guild"}
CRIMINAL_FAMILIES = {"street_gang", "criminal_network"}
CORPORATE_FOCUS_KEYS = {"credential_discipline", "throughput_coordination", "quality_assurance"}
COLLECTIVE_FOCUS_KEYS = {"craft_stewardship", "crew_coordination", "mutual_support"}
CORPORATE_SCREENING_ARCHETYPES = {"bank", "brokerage", "office", "tower", "biotech_clinic", "data_center", "co_working_hub"}
CORPORATE_THROUGHPUT_ARCHETYPES = {"courier_office", "contractor_office", "warehouse", "office", "bank", "brokerage"}
COLLECTIVE_SKILLED_DOMAINS = {"repair", "medical", "logistics", "property_services", "transit", "professional_services"}
FOCUS_DOMAIN_DEFAULTS = {
    "covert_trade_quality": "criminal",
    "drug_batch_quality": "criminal",
    "repair_quality": "repair",
    "medical_restorative_quality": "medical",
    "watch_coordination": "protective",
    "equipment_readiness": "protective",
    "reporting_discipline": "protective",
    "credential_discipline": "finance",
    "throughput_coordination": "logistics",
    "quality_assurance": "professional_services",
    "craft_stewardship": "repair",
    "crew_coordination": "logistics",
    "mutual_support": "support",
}
PRACTICE_TEMPLATE_DEFS = {
    "cleaner_batch": {
        "label": "Cleaner batch routines",
        "summary": "Cleaner off-book routines raise stock consistency and make the branch's batches land cleaner.",
        "tier1": {
            "item_quality_shift": 1,
            "item_effect_scalar": 1.04,
            "trade_buy_price_mult": 1.03,
            "trade_stock_mult": 1.02,
            "intrusion_bonus": 0.15,
            "score_bonus": 0.1,
            "requirement_delta": -0.08,
            "tool_wear_mult": 0.94,
            "tamper_severity_mult": 0.95,
            "targeting_delta": 0.03,
        },
        "tier2": {
            "item_quality_shift": 1,
            "item_effect_scalar": 1.08,
            "trade_buy_price_mult": 1.06,
            "trade_stock_mult": 1.04,
            "intrusion_bonus": 0.28,
            "score_bonus": 0.22,
            "requirement_delta": -0.16,
            "tool_wear_mult": 0.88,
            "tamper_severity_mult": 0.9,
            "targeting_delta": 0.06,
        },
    },
    "potent_batch": {
        "label": "Potent batch routines",
        "summary": "The branch learns how to push hotter lots without fully losing control of the batch.",
        "tier1": {
            "item_quality_shift": 1,
            "item_effect_scalar": 1.08,
            "item_status_duration_scalar": 1.04,
            "trade_buy_price_mult": 1.05,
            "intrusion_bonus": 0.1,
            "mechanics_bonus": 0.12,
            "score_bonus": 0.08,
            "tool_wear_mult": 1.02,
            "tamper_severity_mult": 1.04,
            "quality_delta": 0.04,
        },
        "tier2": {
            "item_quality_shift": 1,
            "item_effect_scalar": 1.15,
            "item_status_duration_scalar": 1.08,
            "trade_buy_price_mult": 1.1,
            "intrusion_bonus": 0.2,
            "mechanics_bonus": 0.22,
            "score_bonus": 0.15,
            "tool_wear_mult": 1.05,
            "tamper_severity_mult": 1.08,
            "quality_delta": 0.08,
        },
    },
    "repair_efficiency": {
        "label": "Repair efficiency routine",
        "summary": "Repeat work turns into tighter parts pulls, better estimates, and cleaner repair throughput.",
        "tier1": {
            "service_quality_mult": 1.05,
            "service_cost_mult": 0.975,
            "item_quality_shift": 1,
        },
        "tier2": {
            "service_quality_mult": 1.1,
            "service_cost_mult": 0.95,
            "item_quality_shift": 1,
            "item_max_durability_bonus": 1,
        },
    },
    "clinic_triage": {
        "label": "Clinic triage routine",
        "summary": "Repeated field treatment sharpens the branch's restorative handling and triage flow.",
        "tier1": {
            "item_quality_shift": 1,
            "item_effect_scalar": 1.06,
            "item_status_duration_scalar": 1.03,
        },
        "tier2": {
            "item_quality_shift": 1,
            "item_effect_scalar": 1.12,
            "item_status_duration_scalar": 1.05,
        },
    },
    "watch_rotation": {
        "label": "Watch rotation discipline",
        "summary": "The branch keeps a tighter watch rota and passes trouble across more quickly.",
        "tier1": {
            "watchfulness_bonus": 6,
            "watch_priority_bonus": 4,
            "response_followthrough_bonus": 0.08,
            "report_conversion_bonus": 0.05,
        },
        "tier2": {
            "watchfulness_bonus": 12,
            "watch_priority_bonus": 8,
            "response_followthrough_bonus": 0.16,
            "report_conversion_bonus": 0.1,
        },
    },
    "readied_posse": {
        "label": "Readied response posture",
        "summary": "People tasked with protection hold better gear ready and turn up with less hesitation.",
        "tier1": {
            "watchfulness_bonus": 4,
            "response_readiness_tier": 1,
            "response_score_bonus": 4,
            "confrontation_posture_bonus": 0.08,
        },
        "tier2": {
            "watchfulness_bonus": 8,
            "response_readiness_tier": 2,
            "response_score_bonus": 8,
            "confrontation_posture_bonus": 0.16,
        },
    },
    "clean_reporting_chain": {
        "label": "Clean reporting chain",
        "summary": "Reports leave the block cleaner and official follow-up lands with less drift.",
        "tier1": {
            "watchfulness_bonus": 3,
            "report_conversion_bonus": 0.12,
            "dispatch_bonus": 0.08,
        },
        "tier2": {
            "watchfulness_bonus": 6,
            "report_conversion_bonus": 0.22,
            "dispatch_bonus": 0.15,
        },
    },
    "screening_protocol": {
        "label": "Credential-screening protocol",
        "summary": "The branch gets better at checking names, handling manifests, and moving known staff through the front without turning the site into a wall.",
        "tier1": {
            "screening_bias": 0.7,
            "paperwork_bias": 0.3,
            "manifest_bias": 0.25,
            "service_time_mult": 0.97,
        },
        "tier2": {
            "screening_bias": 1.15,
            "paperwork_bias": 0.48,
            "manifest_bias": 0.42,
            "service_time_mult": 0.92,
        },
    },
    "dispatch_protocol": {
        "label": "Dispatch protocol",
        "summary": "The branch starts moving work, routes, and handoffs with less wasted motion.",
        "tier1": {
            "dispatch_bias": 0.65,
            "handoff_bias": 0.35,
            "trade_stock_mult": 1.03,
            "trade_buy_price_mult": 0.98,
            "service_time_mult": 0.95,
            "service_cooldown_mult": 0.95,
        },
        "tier2": {
            "dispatch_bias": 1.05,
            "handoff_bias": 0.55,
            "trade_stock_mult": 1.08,
            "trade_buy_price_mult": 0.95,
            "service_time_mult": 0.9,
            "service_cooldown_mult": 0.9,
        },
    },
    "assurance_protocol": {
        "label": "Quality-assurance protocol",
        "summary": "Repeat work gets documented, checked, and delivered with fewer ragged edges.",
        "tier1": {
            "paperwork_bias": 0.2,
            "service_quality_mult": 1.05,
            "quality_delta": 0.04,
            "trade_stock_mult": 1.02,
        },
        "tier2": {
            "paperwork_bias": 0.35,
            "service_quality_mult": 1.1,
            "quality_delta": 0.08,
            "trade_stock_mult": 1.05,
            "item_quality_shift": 1,
        },
    },
    "craft_lineage": {
        "label": "Craft stewardship line",
        "summary": "A collective keeps techniques, shortcuts, and quality habits circulating across the floor.",
        "tier1": {
            "craft_bias": 0.6,
            "service_quality_mult": 1.04,
            "quality_delta": 0.04,
        },
        "tier2": {
            "craft_bias": 0.98,
            "service_quality_mult": 1.08,
            "quality_delta": 0.08,
            "item_quality_shift": 1,
        },
    },
    "crew_floor": {
        "label": "Crew-floor coordination",
        "summary": "A backed crew smooths handoffs, shares load, and keeps a thin shift from fully slipping.",
        "tier1": {
            "crew_bias": 0.72,
            "handoff_bias": 0.28,
            "staffing_relief_bonus": 0.12,
            "service_time_mult": 0.97,
        },
        "tier2": {
            "crew_bias": 1.05,
            "handoff_bias": 0.48,
            "staffing_relief_bonus": 0.22,
            "service_time_mult": 0.93,
        },
    },
    "aid_chain": {
        "label": "Mutual-support chain",
        "summary": "The collective learns how to keep help, names, and soft landings moving through a strained site.",
        "tier1": {
            "support_bias": 0.62,
            "aid_bias": 0.46,
            "service_softness_bonus": 0.08,
            "service_cost_mult": 0.98,
        },
        "tier2": {
            "support_bias": 0.94,
            "aid_bias": 0.74,
            "service_softness_bonus": 0.14,
            "service_cost_mult": 0.95,
        },
    },
}
FOCUS_PRACTICE_DEFS = {
    "covert_trade_quality": {
        "practice_kind": "operational_pattern",
        "item_tags": ("drug",),
        "realization_kinds": ("trade_purchase", "item_use"),
        "target_field_domains": ("criminal",),
        "template_candidates": ("cleaner_batch", "potent_batch"),
        "priority": 74,
    },
    "drug_batch_quality": {
        "practice_kind": "field_discovery",
        "item_tags": ("drug",),
        "realization_kinds": ("trade_purchase", "item_use"),
        "target_field_domains": ("criminal",),
        "template_candidates": ("potent_batch", "cleaner_batch"),
        "priority": 82,
    },
    "repair_quality": {
        "practice_kind": "service_mutation",
        "service_ids": ("repair", "building_repair"),
        "item_tags": ("tool",),
        "realization_kinds": ("trade_purchase", "service_outcome"),
        "target_field_domains": ("repair",),
        "template_candidates": ("repair_efficiency",),
        "priority": 80,
    },
    "medical_restorative_quality": {
        "practice_kind": "field_discovery",
        "item_tags": ("medical", "injectable"),
        "realization_kinds": ("trade_purchase", "item_use"),
        "target_field_domains": ("medical",),
        "template_candidates": ("clinic_triage",),
        "priority": 80,
    },
    "watch_coordination": {
        "practice_kind": "operational_pattern",
        "target_field_domains": ("protective",),
        "template_candidates": ("watch_rotation",),
        "priority": 78,
    },
    "equipment_readiness": {
        "practice_kind": "operational_pattern",
        "target_field_domains": ("protective",),
        "template_candidates": ("readied_posse",),
        "priority": 82,
    },
    "reporting_discipline": {
        "practice_kind": "operational_pattern",
        "target_field_domains": ("protective",),
        "template_candidates": ("clean_reporting_chain",),
        "priority": 76,
    },
    "credential_discipline": {
        "practice_kind": "operational_pattern",
        "target_field_domains": ("finance", "professional_services", "technology", "medical"),
        "template_candidates": ("screening_protocol",),
        "priority": 78,
    },
    "throughput_coordination": {
        "practice_kind": "operational_pattern",
        "target_field_domains": ("logistics", "transit", "property_services", "professional_services"),
        "template_candidates": ("dispatch_protocol",),
        "priority": 80,
    },
    "quality_assurance": {
        "practice_kind": "service_mutation",
        "target_field_domains": ("finance", "professional_services", "repair", "medical", "technology"),
        "template_candidates": ("assurance_protocol",),
        "priority": 82,
    },
    "craft_stewardship": {
        "practice_kind": "service_mutation",
        "target_field_domains": ("repair", "medical", "logistics", "property_services", "transit", "professional_services"),
        "template_candidates": ("craft_lineage",),
        "priority": 78,
    },
    "crew_coordination": {
        "practice_kind": "operational_pattern",
        "target_field_domains": ("logistics", "transit", "property_services", "professional_services"),
        "template_candidates": ("crew_floor",),
        "priority": 76,
    },
    "mutual_support": {
        "practice_kind": "operational_pattern",
        "target_field_domains": ("medical", "support"),
        "template_candidates": ("aid_chain",),
        "priority": 74,
    },
}


def _text(value):
    return str(value or "").strip()


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _item_tags(item_id):
    item_def = ITEM_CATALOG.get(_text(item_id), {})
    tags = {
        _text(tag).lower()
        for tag in item_def.get("tags", ())
        if _text(tag)
    }
    appearance_family = _text(item_def.get("appearance_family")).lower()
    if appearance_family:
        tags.add(appearance_family)
    identification_profile = item_def.get("identification_profile")
    if isinstance(identification_profile, dict):
        family = _text(identification_profile.get("family")).lower()
        if family:
            tags.add(family)
    category = _text(item_def.get("category")).lower()
    if category:
        tags.add(category)
    if item_def.get("legal_status") == "illegal" and tags.intersection({"stimulant", "medical", "injectable"}):
        tags.add("drug")
    return tags


def _property_metadata(prop):
    metadata = prop.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _property_archetype(prop):
    metadata = _property_metadata(prop)
    return _text(metadata.get("archetype", (prop or {}).get("kind"))).lower()


def _covert_property(prop, links):
    metadata = _property_metadata(prop)
    if _text(metadata.get("hidden_contact_kind")):
        return True
    if _text(metadata.get("backroom_profile")) or _text(metadata.get("covert_hint")):
        return True
    if "criminal" in set(property_field_domains(prop)):
        return True
    for link in links:
        if _text((link.get("policy") or {}).get("family")).lower() in CRIMINAL_FAMILIES:
            return True
    return False


def _candidate_link_rows(sim, prop):
    rows = []
    for link in property_org_links(sim, prop, active_only=True):
        organization_eid = _safe_int(link.get("organization_eid"), default=0)
        if organization_eid <= 0:
            continue
        profile = organization_profile(sim, organization_eid)
        if profile is None:
            continue
        rows.append(
            {
                **link,
                "policy": organization_policy_snapshot(sim, organization_eid),
                "tags": set(getattr(profile, "tags", ()) or ()),
            }
        )
    return tuple(rows)


def _has_family_link(links, family):
    family_key = _text(family).lower()
    return any(
        _text((row.get("policy") or {}).get("family")).lower() == family_key
        for row in tuple(links or ())
    )


def _collective_matches_domain(row, domain_key, prop_domains):
    family = _text((row.get("policy") or {}).get("family")).lower()
    if family not in COLLECTIVE_FAMILIES:
        return False
    return not domain_key or domain_key in set(prop_domains)


def _corporate_matches_focus(row):
    return _text((row.get("policy") or {}).get("family")).lower() == "corporate"


def _protective_matches_focus(sim, row):
    policy = row.get("policy") if isinstance(row.get("policy"), dict) else {}
    family = _text(policy.get("family")).lower()
    if family == "municipal":
        return True
    if family != "street_gang":
        return False
    root_eid = _safe_int(policy.get("root_organization_eid"), default=_safe_int(policy.get("organization_eid"), default=0))
    if root_eid <= 0:
        return False
    root_profile = organization_profile(sim, root_eid)
    root_tags = {
        _text(tag).lower()
        for tag in getattr(root_profile, "tags", ()) or ()
        if _text(tag)
    }
    return "gang_posture:vigilante" in root_tags


def _corporate_focus_eligible(prop, focus_key, links):
    if not isinstance(prop, dict) or not _has_family_link(links, "corporate"):
        return False
    domains = set(property_field_domains(prop))
    archetype = _property_archetype(prop)
    if focus_key == "credential_discipline":
        return archetype in CORPORATE_SCREENING_ARCHETYPES or domains.intersection({"finance", "professional_services", "technology", "medical"})
    if focus_key == "throughput_coordination":
        return archetype in CORPORATE_THROUGHPUT_ARCHETYPES or domains.intersection({"logistics", "transit", "property_services", "professional_services"})
    if focus_key == "quality_assurance":
        return domains.intersection({"finance", "professional_services", "repair", "medical", "technology"}) or archetype in CORPORATE_THROUGHPUT_ARCHETYPES.union(CORPORATE_SCREENING_ARCHETYPES)
    return False


def _collective_focus_eligible(prop, focus_key, links):
    if not isinstance(prop, dict) or not _has_family_link(links, "labor_union") and not _has_family_link(links, "trade_guild"):
        return False
    domains = set(property_field_domains(prop))
    archetype = _property_archetype(prop)
    if focus_key == "craft_stewardship":
        return bool(domains.intersection(COLLECTIVE_SKILLED_DOMAINS)) or archetype in {"contractor_office", "courier_office", "warehouse", "biotech_clinic"}
    if focus_key == "crew_coordination":
        return bool(domains.intersection({"logistics", "transit", "property_services", "professional_services"})) or archetype in {"contractor_office", "courier_office", "warehouse", "office"}
    if focus_key == "mutual_support":
        return bool(domains.intersection({"medical", "support"})) or archetype in {"biotech_clinic", "clinic", "hospital"}
    return False


def _focus_targets_for_property(sim, prop, *, focus_key, domain_key, item_id="", item_tags=(), owner_transfer=False):
    if not isinstance(prop, dict) or owner_transfer:
        return ()
    prop_domains = set(property_field_domains(prop))
    links = _candidate_link_rows(sim, prop)
    if not links:
        return ()

    rows = []
    seen = set()
    is_covert = _covert_property(prop, links)
    include_primary = focus_key not in COLLECTIVE_FOCUS_KEYS
    primary_added = False

    if include_primary:
        for link in links:
            if _text(link.get("link_kind")).lower() != "operates" or not bool(link.get("primary", False)):
                continue
            organization_eid = _safe_int(link.get("organization_eid"), default=0)
            if organization_eid <= 0:
                continue
            rows.append(
                {
                    "organization_eid": organization_eid,
                    "link_kind": "operates",
                    "weight": LINK_KIND_WEIGHTS["operates"],
                    "policy": link.get("policy"),
                    "property_id": _text(prop.get("id")),
                    "building_id": _text(_property_metadata(prop).get("building_id")),
                }
            )
            seen.add(organization_eid)
            primary_added = True
            break

    for link in links:
        organization_eid = _safe_int(link.get("organization_eid"), default=0)
        if organization_eid <= 0 or organization_eid in seen:
            continue
        link_kind = _text(link.get("link_kind")).lower()
        weight = _safe_float(LINK_KIND_WEIGHTS.get(link_kind), default=0.0)
        if weight <= 0.0:
            continue
        family = _text((link.get("policy") or {}).get("family")).lower()
        include = False
        if focus_key in {"covert_trade_quality", "drug_batch_quality"}:
            include = family in CRIMINAL_FAMILIES and (link_kind != "territory" or is_covert)
        elif focus_key in {"repair_quality", "medical_restorative_quality"}:
            include = _collective_matches_domain(link, domain_key, prop_domains)
        elif focus_key in {"watch_coordination", "equipment_readiness", "reporting_discipline"}:
            include = _protective_matches_focus(sim, link)
        elif focus_key in CORPORATE_FOCUS_KEYS:
            include = _corporate_matches_focus(link)
        elif focus_key in COLLECTIVE_FOCUS_KEYS:
            include = _collective_matches_domain(link, domain_key, prop_domains)
        if not include:
            continue
        rows.append(
            {
                "organization_eid": organization_eid,
                "link_kind": link_kind,
                "weight": weight,
                "policy": link.get("policy"),
                "property_id": _text(prop.get("id")),
                "building_id": _text(_property_metadata(prop).get("building_id")),
            }
        )
        seen.add(organization_eid)

    if not primary_added and rows:
        rows.sort(key=lambda row: (-_safe_float(row.get("weight"), default=0.0), _safe_int(row.get("organization_eid"), default=0)))
    return tuple(rows)


def _progress_key(*, focus_key, domain_key, property_id="", building_id="", scope="branch"):
    return ":".join(
        [
            _text(scope).lower() or "branch",
            _text(focus_key).lower() or "focus",
            _text(domain_key).lower() or "domain",
            _text(property_id) or "-",
            _text(building_id) or "-",
        ]
    )


def _focus_domain_key(prop, fallback):
    domains = set(property_field_domains(prop))
    if fallback in domains:
        return fallback
    if fallback == "criminal" and domains.intersection({"criminal", "trade"}):
        return "criminal"
    return fallback


def _best_domain_key(prop, *preferred):
    domains = set(property_field_domains(prop))
    for candidate in preferred:
        clean = _text(candidate).lower()
        if clean and clean in domains:
            return clean
    for candidate in preferred:
        clean = _text(candidate).lower()
        if clean:
            return clean
    for candidate in sorted(domains):
        if candidate:
            return candidate
    return ""


def _record_property_signal(
    sim,
    prop,
    *,
    focus_key,
    domain_key,
    activity_points,
    success_points,
    item_id="",
    item_tags=(),
    owner_transfer=False,
):
    for row in _focus_targets_for_property(
        sim,
        prop,
        focus_key=focus_key,
        domain_key=domain_key,
        item_id=item_id,
        item_tags=item_tags,
        owner_transfer=owner_transfer,
    ):
        weight = _safe_float(row.get("weight"), default=0.0)
        if weight <= 0.0:
            continue
        progress_key = _progress_key(
            focus_key=focus_key,
            domain_key=domain_key,
            property_id=row.get("property_id"),
            building_id=row.get("building_id"),
            scope="branch",
        )
        record_organization_practice_progress(
            sim,
            organization_eid=row.get("organization_eid"),
            progress_key=progress_key,
            branch_property_id=row.get("property_id"),
            branch_building_id=row.get("building_id"),
            domain_key=domain_key,
            focus_key=focus_key,
            scope="branch",
            activity_delta=activity_points * weight,
            success_delta=success_points * weight,
        )


def _source_signal_targets(sim, *, source_property_id="", source_organization_eid=None, domain_key="", focus_key=""):
    property_id = _text(source_property_id)
    prop = sim.properties.get(property_id) if property_id else None
    if isinstance(prop, dict):
        rows = list(
            _focus_targets_for_property(
                sim,
                prop,
                focus_key=focus_key,
                domain_key=domain_key,
            )
        )
        if rows:
            return tuple(rows)
    organization_eid = _safe_int(source_organization_eid, default=0)
    if organization_eid <= 0:
        return ()
    return (
        {
            "organization_eid": organization_eid,
            "link_kind": "operates",
            "weight": 1.0,
            "policy": organization_policy_snapshot(sim, organization_eid),
            "property_id": property_id or None,
            "building_id": _text((prop or {}).get("metadata", {}).get("building_id")) if isinstance(prop, dict) else None,
        },
    )


def _deterministic_template_name(sim, *, focus_key, progress_key, tier, policy=None, prop=None):
    definition = FOCUS_PRACTICE_DEFS.get(_text(focus_key).lower())
    if not isinstance(definition, dict):
        return None
    candidates = list(definition.get("template_candidates", ()))
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    policy = policy if isinstance(policy, dict) else {}
    metadata = _property_metadata(prop) if isinstance(prop, dict) else {}
    family = _text(policy.get("family")).lower()
    covert_temper = _text(metadata.get("backroom_profile")).lower()
    if "rough" in covert_temper or "hungry" in covert_temper or family in CRIMINAL_FAMILIES:
        candidates = list(reversed(candidates))
    rng = random.Random(
        f"{getattr(sim, 'seed', 0)}:org-practice-template:{_text(progress_key)}:{int(tier)}:{family}:{covert_temper}"
    )
    return str(rng.choice(candidates)).strip()


def _domain_item_tags(domain_key):
    domain = _text(domain_key).lower()
    if domain == "repair":
        return ("tool",)
    if domain == "medical":
        return ("medical", "injectable")
    if domain in {"criminal", "vice"}:
        return ("drug",)
    return ()


def _practice_row_payload(sim, *, organization_eid, row, tier, scope):
    focus_key = _text(row.get("focus_key")).lower()
    domain_key = _text(row.get("domain_key")).lower() or FOCUS_DOMAIN_DEFAULTS.get(focus_key, "")
    definition = FOCUS_PRACTICE_DEFS.get(focus_key, {})
    policy = organization_policy_snapshot(sim, organization_eid) or {}
    prop = sim.properties.get(_text(row.get("branch_property_id")))
    template_name = _deterministic_template_name(
        sim,
        focus_key=focus_key,
        progress_key=row.get("progress_key"),
        tier=tier,
        policy=policy,
        prop=prop,
    )
    template = PRACTICE_TEMPLATE_DEFS.get(template_name or "", {})
    tier_key = "tier2" if int(tier) >= 2 else "tier1"
    target_scope = "organization" if scope == "root" else "property"
    entry_scope = "root" if scope == "root" else "branch"
    entry_key = f"{entry_scope}_emergence:{focus_key}:{domain_key}:{_text(row.get('branch_property_id')) or _text(policy.get('organization_key'))}"
    target_field_domains = definition.get("target_field_domains", (domain_key,))
    if _text(domain_key).lower() == "protective":
        target_field_domains = ()
    service_ids = definition.get("service_ids", ()) or ()
    if not service_ids and isinstance(prop, dict) and definition.get("practice_kind") == "service_mutation":
        service_ids = tuple(property_service_ids(prop))
    item_tags = definition.get("item_tags", ()) or _domain_item_tags(domain_key)
    return {
        "entry_key": entry_key,
        "practice_kind": definition.get("practice_kind", "field_discovery"),
        "domain_key": domain_key,
        "label": template.get("label") or focus_key.replace("_", " ").title(),
        "summary": template.get("summary") or focus_key.replace("_", " "),
        "source_kind": "practice_progression",
        "discovery_key": _text(row.get("progress_key")),
        "service_ids": service_ids,
        "item_tags": item_tags,
        "realization_kinds": definition.get("realization_kinds", ()),
        "effect_modifiers": dict(template.get(tier_key, {})),
        "target_scope": target_scope,
        "target_property_id": None if target_scope == "organization" else _text(row.get("branch_property_id")) or None,
        "target_building_id": None if target_scope == "organization" else _text(row.get("branch_building_id")) or None,
        "target_field_domains": target_field_domains,
        "priority": int(definition.get("priority", 70)) + (6 if int(tier) >= 2 else 0),
        "active": True,
    }


class OrganizationPracticeEvolutionSystem(System):
    """Turns repeated branch activity into persistent org practice rows."""

    def __init__(self, sim, refresh_interval=EVALUATION_INTERVAL):
        super().__init__(sim)
        self.refresh_interval = max(30, int(refresh_interval))
        self.sim.events.subscribe("trade_bought", self.on_trade_bought)
        self.sim.events.subscribe("trade_sold", self.on_trade_sold)
        self.sim.events.subscribe("site_service_used", self.on_site_service_used)
        self.sim.events.subscribe("item_used", self.on_item_used)
        self.sim.events.subscribe("bank_transaction", self.on_bank_transaction)
        self.sim.events.subscribe("insurance_policy_purchased", self.on_insurance_policy_purchased)
        self.sim.events.subscribe("property_trespass", self.on_property_trespass)
        self.sim.events.subscribe("property_tamper", self.on_property_tamper)
        self.sim.events.subscribe("item_stolen", self.on_item_stolen)
        self.sim.events.subscribe("action_offense", self.on_action_offense)
        self.sim.events.subscribe("incident_authority_reported", self.on_incident_authority_reported)
        self.sim.events.subscribe("organization_vigilante_response", self.on_organization_vigilante_response)
        self.sim.events.subscribe("justice_booking_completed", self.on_justice_booking_completed)

    def _trade_property(self, event):
        property_id = _text(event.data.get("property_id"))
        return self.sim.properties.get(property_id)

    def _property_for_data(self, data):
        if not isinstance(data, dict):
            return None
        property_id = _text(data.get("property_id"))
        if property_id:
            prop = self.sim.properties.get(property_id)
            if isinstance(prop, dict):
                return prop
        try:
            x = int(data.get("x"))
            y = int(data.get("y"))
            z = int(data.get("z", 0))
        except (TypeError, ValueError):
            return None
        return self.sim.property_covering(x, y, z) if hasattr(self.sim, "property_covering") else None

    def _record_protective_signal(self, prop, *, focus_key, activity_points, success_points):
        if not isinstance(prop, dict):
            return
        _record_property_signal(
            self.sim,
            prop,
            focus_key=focus_key,
            domain_key="protective",
            activity_points=activity_points,
            success_points=success_points,
        )

    def _record_corporate_signal(self, prop, *, focus_key, domain_key, activity_points, success_points, item_id="", item_tags=()):
        if not isinstance(prop, dict):
            return
        links = _candidate_link_rows(self.sim, prop)
        if not _corporate_focus_eligible(prop, focus_key, links):
            return
        _record_property_signal(
            self.sim,
            prop,
            focus_key=focus_key,
            domain_key=domain_key,
            activity_points=activity_points,
            success_points=success_points,
            item_id=item_id,
            item_tags=item_tags,
        )

    def _record_collective_signal(self, prop, *, focus_key, domain_key, activity_points, success_points, item_id="", item_tags=()):
        if not isinstance(prop, dict):
            return
        links = _candidate_link_rows(self.sim, prop)
        if not _collective_focus_eligible(prop, focus_key, links):
            return
        _record_property_signal(
            self.sim,
            prop,
            focus_key=focus_key,
            domain_key=domain_key,
            activity_points=activity_points,
            success_points=success_points,
            item_id=item_id,
            item_tags=item_tags,
        )

    def _loaded_property(self, prop):
        if not isinstance(prop, dict):
            return False
        try:
            detail = self.sim.detail_for_xy(int(prop.get("x", 0)), int(prop.get("y", 0)))
        except Exception:
            return True
        return detail != "unloaded"

    def _collective_staffing_candidate_properties(self):
        loaded_props = []
        props_by_id = {}
        props_by_building_id = {}
        for prop in self.sim.properties.values():
            if not isinstance(prop, dict) or not self._loaded_property(prop):
                continue
            prop_id = _text(prop.get("id"))
            if prop_id:
                props_by_id[prop_id] = prop
            metadata = _property_metadata(prop)
            for building_id in (
                _text(metadata.get("building_id")),
                _text(metadata.get("local_building_id")),
            ):
                if building_id:
                    props_by_building_id.setdefault(building_id, prop)
            loaded_props.append(prop)

        candidates = {}
        for organization_eid, _profile_component in tuple(self.sim.ecs.get(OrganizationProfile).items()):
            policy = organization_policy_snapshot(self.sim, organization_eid) or {}
            if _text(policy.get("family")).lower() not in COLLECTIVE_FAMILIES:
                continue
            profile = organization_profile(self.sim, organization_eid)
            if profile is None:
                continue
            for raw_link in tuple(getattr(profile, "site_links", ()) or ()):
                if not isinstance(raw_link, dict) or not bool(raw_link.get("active", True)):
                    continue
                prop = props_by_id.get(_text(raw_link.get("property_id")))
                if prop is None:
                    prop = props_by_building_id.get(_text(raw_link.get("building_id")))
                if isinstance(prop, dict):
                    prop_id = _text(prop.get("id"))
                    if prop_id:
                        candidates[prop_id] = prop

        for prop in loaded_props:
            prop_id = _text(prop.get("id"))
            if not prop_id or prop_id in candidates:
                continue
            organization_eid = _safe_int(_property_metadata(prop).get("organization_eid"), default=0)
            if organization_eid <= 0:
                continue
            policy = organization_policy_snapshot(self.sim, organization_eid) or {}
            if _text(policy.get("family")).lower() in COLLECTIVE_FAMILIES:
                candidates[prop_id] = prop

        return tuple(candidates[key] for key in sorted(candidates))

    def _periodic_collective_staffing_signals(self, tick):
        if tick <= 0 or tick % self.refresh_interval != 0:
            return
        try:
            from game.organization_reputation import organization_instability_profile
        except Exception:
            organization_instability_profile = None
        try:
            from game.player_businesses import player_business_status_snapshot
        except Exception:
            player_business_status_snapshot = None

        for prop in self._collective_staffing_candidate_properties():
            links = _candidate_link_rows(self.sim, prop)
            if not _has_family_link(links, "labor_union") and not _has_family_link(links, "trade_guild"):
                continue
            business_snapshot = (
                player_business_status_snapshot(self.sim, prop)
                if callable(player_business_status_snapshot)
                else None
            )
            business_snapshot = business_snapshot if isinstance(business_snapshot, dict) else {}
            instability = (
                organization_instability_profile(self.sim, prop=prop, ensure=True)
                if callable(organization_instability_profile)
                else {}
            ) or {}
            required_staff = max(0, _safe_int(business_snapshot.get("required_staff"), default=0))
            staff_total = max(0, _safe_int(business_snapshot.get("staff_total"), default=0))
            open_roles = tuple(
                _text(role).lower()
                for role in tuple(business_snapshot.get("open_roles", ()) or ())
                if _text(role)
            )
            shortage = max(0, required_staff - staff_total) if required_staff > 0 else 0
            staffing_pressure = 0.0
            if required_staff > 0:
                staffing_pressure = max(staffing_pressure, min(1.0, float(shortage) / float(required_staff)))
            if open_roles:
                staffing_pressure = max(staffing_pressure, min(1.0, 0.28 + (0.16 * len(open_roles))))
            if bool(instability.get("underrepresented", False)):
                staffing_pressure = max(
                    staffing_pressure,
                    min(1.0, 0.22 + (_safe_float(instability.get("coverage_pressure"), default=0.0) * 0.75)),
                )
            if staffing_pressure <= 0.0:
                continue
            self._record_collective_signal(
                prop,
                focus_key="crew_coordination",
                domain_key=_focus_domain_key(prop, "logistics"),
                activity_points=1.0 + (staffing_pressure * 1.2),
                success_points=1.0 + (staffing_pressure * 1.2),
            )
            if "medical" in set(property_field_domains(prop)):
                self._record_collective_signal(
                    prop,
                    focus_key="mutual_support",
                    domain_key=_focus_domain_key(prop, "support"),
                    activity_points=0.8 + staffing_pressure,
                    success_points=0.8 + staffing_pressure,
                )

    def _accountable(self, event, *, offender_eid=None):
        observation = event_observation_accountability(
            self.sim,
            event,
            offender_eid=offender_eid,
            default_channels=("actor_witness",),
        )
        return bool(observation.get("has_accountable_observation"))

    def on_trade_bought(self, event):
        if bool(event.data.get("owner_transfer", False)):
            return
        prop = self._trade_property(event)
        if not isinstance(prop, dict):
            return
        item_id = _text(event.data.get("item_id"))
        tags = _item_tags(item_id)
        is_covert = _covert_property(prop, _candidate_link_rows(self.sim, prop))
        if is_covert:
            domain_key = _focus_domain_key(prop, "criminal")
            points = 2.0 if is_covert else 1.0
            _record_property_signal(
                self.sim,
                prop,
                focus_key="covert_trade_quality",
                domain_key=domain_key,
                activity_points=points,
                success_points=points,
                item_id=item_id,
                item_tags=tags,
            )
        if "drug" in tags and is_covert:
            domain_key = _focus_domain_key(prop, "criminal")
            _record_property_signal(
                self.sim,
                prop,
                focus_key="drug_batch_quality",
                domain_key=domain_key,
                activity_points=2.0,
                success_points=2.0,
                item_id=item_id,
                item_tags=tags,
            )
        if "tool" in tags and "repair" in set(property_field_domains(prop)):
            _record_property_signal(
                self.sim,
                prop,
                focus_key="repair_quality",
                domain_key="repair",
                activity_points=1.0,
                success_points=1.0,
                item_id=item_id,
                item_tags=tags,
            )
        self._record_corporate_signal(
            prop,
            focus_key="throughput_coordination",
            domain_key=_best_domain_key(prop, "logistics", "professional_services", "finance"),
            activity_points=1.0,
            success_points=1.0,
            item_id=item_id,
            item_tags=tags,
        )
        self._record_corporate_signal(
            prop,
            focus_key="quality_assurance",
            domain_key=_best_domain_key(prop, "repair", "medical", "professional_services", "finance"),
            activity_points=1.0,
            success_points=1.0,
            item_id=item_id,
            item_tags=tags,
        )
        self._record_collective_signal(
            prop,
            focus_key="craft_stewardship",
            domain_key=_best_domain_key(prop, "repair", "medical", "logistics", "professional_services"),
            activity_points=1.0,
            success_points=1.0,
            item_id=item_id,
            item_tags=tags,
        )
        self._record_collective_signal(
            prop,
            focus_key="crew_coordination",
            domain_key=_best_domain_key(prop, "logistics", "property_services", "professional_services"),
            activity_points=0.8,
            success_points=0.8,
            item_id=item_id,
            item_tags=tags,
        )
        if tags.intersection({"medical", "injectable"}):
            self._record_collective_signal(
                prop,
                focus_key="mutual_support",
                domain_key=_best_domain_key(prop, "medical", "support"),
                activity_points=1.0,
                success_points=1.0,
                item_id=item_id,
                item_tags=tags,
            )
        if tags.intersection({"medical", "injectable"}) and "medical" in set(property_field_domains(prop)):
            _record_property_signal(
                self.sim,
                prop,
                focus_key="medical_restorative_quality",
                domain_key="medical",
                activity_points=1.0,
                success_points=1.0,
                item_id=item_id,
                item_tags=tags,
            )

    def on_trade_sold(self, event):
        if bool(event.data.get("owner_transfer", False)):
            return
        prop = self._trade_property(event)
        if not isinstance(prop, dict):
            return
        item_id = _text(event.data.get("item_id"))
        tags = _item_tags(item_id)
        is_covert = _covert_property(prop, _candidate_link_rows(self.sim, prop))
        if is_covert:
            domain_key = _focus_domain_key(prop, "criminal")
            _record_property_signal(
                self.sim,
                prop,
                focus_key="covert_trade_quality",
                domain_key=domain_key,
                activity_points=2.0,
                success_points=2.0,
                item_id=item_id,
                item_tags=tags,
            )
        if "drug" in tags and is_covert:
            domain_key = _focus_domain_key(prop, "criminal")
            _record_property_signal(
                self.sim,
                prop,
                focus_key="drug_batch_quality",
                domain_key=domain_key,
                activity_points=2.0,
                success_points=2.0,
                item_id=item_id,
                item_tags=tags,
            )
        if "tool" in tags and "repair" in set(property_field_domains(prop)):
            _record_property_signal(
                self.sim,
                prop,
                focus_key="repair_quality",
                domain_key="repair",
                activity_points=1.0,
                success_points=1.0,
                item_id=item_id,
                item_tags=tags,
            )
        self._record_corporate_signal(
            prop,
            focus_key="throughput_coordination",
            domain_key=_best_domain_key(prop, "logistics", "professional_services", "finance"),
            activity_points=1.5,
            success_points=1.5,
            item_id=item_id,
            item_tags=tags,
        )
        self._record_corporate_signal(
            prop,
            focus_key="quality_assurance",
            domain_key=_best_domain_key(prop, "repair", "medical", "professional_services", "finance"),
            activity_points=1.0,
            success_points=1.0,
            item_id=item_id,
            item_tags=tags,
        )
        self._record_collective_signal(
            prop,
            focus_key="craft_stewardship",
            domain_key=_best_domain_key(prop, "repair", "medical", "logistics", "professional_services"),
            activity_points=1.0,
            success_points=1.0,
            item_id=item_id,
            item_tags=tags,
        )
        self._record_collective_signal(
            prop,
            focus_key="crew_coordination",
            domain_key=_best_domain_key(prop, "logistics", "property_services", "professional_services"),
            activity_points=1.0,
            success_points=1.0,
            item_id=item_id,
            item_tags=tags,
        )
        if tags.intersection({"medical", "injectable"}):
            self._record_collective_signal(
                prop,
                focus_key="mutual_support",
                domain_key=_best_domain_key(prop, "medical", "support"),
                activity_points=1.0,
                success_points=1.0,
                item_id=item_id,
                item_tags=tags,
            )

    def on_site_service_used(self, event):
        property_id = _text(event.data.get("property_id"))
        prop = self.sim.properties.get(property_id)
        if not isinstance(prop, dict):
            return
        service = _text(event.data.get("service")).lower()
        if service == "repair":
            _record_property_signal(
                self.sim,
                prop,
                focus_key="repair_quality",
                domain_key="repair",
                activity_points=2.0,
                success_points=2.0,
            )
        elif service == "building_repair":
            _record_property_signal(
                self.sim,
                prop,
                focus_key="repair_quality",
                domain_key="repair",
                activity_points=3.0,
                success_points=3.0,
            )
        self._record_corporate_signal(
            prop,
            focus_key="credential_discipline",
            domain_key=_best_domain_key(prop, "finance", "professional_services", "medical"),
            activity_points=1.5 if service in {"banking", "insurance"} else 1.0,
            success_points=1.5 if service in {"banking", "insurance"} else 1.0,
        )
        self._record_corporate_signal(
            prop,
            focus_key="throughput_coordination",
            domain_key=_best_domain_key(prop, "logistics", "professional_services", "property_services"),
            activity_points=1.0,
            success_points=1.0,
        )
        self._record_corporate_signal(
            prop,
            focus_key="quality_assurance",
            domain_key=_best_domain_key(prop, "repair", "medical", "professional_services", "finance"),
            activity_points=1.5 if service in {"repair", "building_repair", "rest"} else 1.0,
            success_points=1.5 if service in {"repair", "building_repair", "rest"} else 1.0,
        )
        self._record_collective_signal(
            prop,
            focus_key="craft_stewardship",
            domain_key=_best_domain_key(prop, "repair", "medical", "logistics", "professional_services"),
            activity_points=1.2,
            success_points=1.2,
        )
        self._record_collective_signal(
            prop,
            focus_key="crew_coordination",
            domain_key=_best_domain_key(prop, "logistics", "property_services", "professional_services"),
            activity_points=1.0,
            success_points=1.0,
        )
        if service in {"rest", "shelter"} or "medical" in set(property_field_domains(prop)):
            self._record_collective_signal(
                prop,
                focus_key="mutual_support",
                domain_key=_best_domain_key(prop, "medical", "support"),
                activity_points=1.4,
                success_points=1.4,
            )

    def on_item_used(self, event):
        applied = event.data.get("applied")
        if not isinstance(applied, list):
            return
        if not any(
            isinstance(effect, dict)
            and _text(effect.get("type")).lower() == "restore_hp"
            and _safe_int(effect.get("delta"), default=0) > 0
            for effect in applied
        ):
            return
        metadata = event.data.get("item_metadata")
        if not isinstance(metadata, dict):
            return
        source_org_eid = _safe_int(metadata.get("source_organization_eid"), default=0)
        source_property_id = _text(metadata.get("source_property_id"))
        if source_org_eid <= 0 and not source_property_id:
            return
        for row in _source_signal_targets(
            self.sim,
            source_property_id=source_property_id,
            source_organization_eid=source_org_eid,
            domain_key="medical",
            focus_key="medical_restorative_quality",
        ):
            weight = _safe_float(row.get("weight"), default=0.0)
            if weight <= 0.0:
                continue
            record_organization_practice_progress(
                self.sim,
                organization_eid=row.get("organization_eid"),
                progress_key=_progress_key(
                    focus_key="medical_restorative_quality",
                    domain_key="medical",
                    property_id=row.get("property_id"),
                    building_id=row.get("building_id"),
                    scope="branch",
                ),
                branch_property_id=row.get("property_id"),
                branch_building_id=row.get("building_id"),
                domain_key="medical",
                focus_key="medical_restorative_quality",
                scope="branch",
                activity_delta=2.0 * weight,
                success_delta=2.0 * weight,
            )
        source_prop = self.sim.properties.get(source_property_id) if source_property_id else None
        if isinstance(source_prop, dict):
            self._record_collective_signal(
                source_prop,
                focus_key="mutual_support",
                domain_key=_best_domain_key(source_prop, "medical", "support"),
                activity_points=1.4,
                success_points=1.4,
            )

    def on_bank_transaction(self, event):
        prop = self._trade_property(event)
        if not isinstance(prop, dict):
            return
        self._record_corporate_signal(
            prop,
            focus_key="credential_discipline",
            domain_key=_best_domain_key(prop, "finance", "professional_services"),
            activity_points=2.0,
            success_points=2.0,
        )
        self._record_corporate_signal(
            prop,
            focus_key="quality_assurance",
            domain_key=_best_domain_key(prop, "finance", "professional_services"),
            activity_points=1.0,
            success_points=1.0,
        )

    def on_insurance_policy_purchased(self, event):
        prop = self._trade_property(event)
        if not isinstance(prop, dict):
            return
        self._record_corporate_signal(
            prop,
            focus_key="credential_discipline",
            domain_key=_best_domain_key(prop, "finance", "professional_services"),
            activity_points=2.0,
            success_points=2.0,
        )
        self._record_corporate_signal(
            prop,
            focus_key="quality_assurance",
            domain_key=_best_domain_key(prop, "finance", "professional_services"),
            activity_points=1.0,
            success_points=1.0,
        )

    def on_property_trespass(self, event):
        if event_is_vision_only(event):
            return
        if not self._accountable(event, offender_eid=event.data.get("offender_eid")):
            return
        prop = self._property_for_data(event.data)
        if not isinstance(prop, dict):
            return
        self._record_protective_signal(prop, focus_key="watch_coordination", activity_points=1.5, success_points=1.5)

    def on_property_tamper(self, event):
        if event_is_vision_only(event):
            return
        if not self._accountable(event, offender_eid=event.data.get("offender_eid")):
            return
        prop = self._property_for_data(event.data)
        if not isinstance(prop, dict):
            return
        self._record_protective_signal(prop, focus_key="watch_coordination", activity_points=2.0, success_points=2.0)
        self._record_protective_signal(prop, focus_key="equipment_readiness", activity_points=1.0, success_points=1.0)

    def on_item_stolen(self, event):
        if event_is_vision_only(event):
            return
        if not self._accountable(event, offender_eid=event.data.get("offender_eid")):
            return
        prop = self._property_for_data(event.data)
        if not isinstance(prop, dict):
            return
        self._record_protective_signal(prop, focus_key="watch_coordination", activity_points=2.5, success_points=2.5)
        self._record_protective_signal(prop, focus_key="reporting_discipline", activity_points=1.0, success_points=1.0)

    def on_action_offense(self, event):
        if event_is_vision_only(event):
            return
        context = _text(event.data.get("context")).lower()
        if context not in {"unarmed_assault", "melee_assault", "armed_assault", "explosive_discharge", "homicide"}:
            return
        if not self._accountable(event, offender_eid=event.data.get("offender_eid")):
            return
        prop = self._property_for_data(event.data)
        if not isinstance(prop, dict):
            return
        self._record_protective_signal(prop, focus_key="watch_coordination", activity_points=3.0, success_points=3.0)
        self._record_protective_signal(prop, focus_key="equipment_readiness", activity_points=2.0, success_points=2.0)
        self._record_protective_signal(prop, focus_key="reporting_discipline", activity_points=1.0, success_points=1.0)

    def on_incident_authority_reported(self, event):
        if event_is_vision_only(event):
            return
        incident = incident_record(self.sim, event.data.get("incident_id"))
        if not isinstance(incident, dict):
            return
        if event_is_vision_only(incident):
            return
        prop = self._property_for_data(incident)
        if not isinstance(prop, dict):
            return
        self._record_protective_signal(prop, focus_key="reporting_discipline", activity_points=2.0, success_points=2.0)
        kind = _text(incident.get("kind")).lower()
        if kind in {"property_trespass", "property_tamper", "item_stolen", "action_offense"}:
            self._record_protective_signal(prop, focus_key="watch_coordination", activity_points=1.5, success_points=1.5)

    def on_organization_vigilante_response(self, event):
        prop = self._property_for_data(event.data)
        if not isinstance(prop, dict):
            return
        self._record_protective_signal(prop, focus_key="watch_coordination", activity_points=2.0, success_points=2.0)
        self._record_protective_signal(prop, focus_key="equipment_readiness", activity_points=1.5, success_points=1.5)

    def on_justice_booking_completed(self, event):
        property_id = _text(event.data.get("property_id"))
        prop = self.sim.properties.get(property_id) if property_id else None
        if not isinstance(prop, dict):
            return
        self._record_protective_signal(prop, focus_key="reporting_discipline", activity_points=2.0, success_points=2.0)
        self._record_protective_signal(prop, focus_key="equipment_readiness", activity_points=2.0, success_points=2.0)

    def _evaluate_branch_row(self, organization_eid, row, tick):
        total_points = _safe_float(row.get("activity_points"), default=0.0)
        current_tier = _safe_int(row.get("tier"), default=0)
        target_tier = 2 if total_points >= TIER2_THRESHOLD else 1 if total_points >= TIER1_THRESHOLD else 0
        if target_tier > current_tier:
            payload = _practice_row_payload(
                self.sim,
                organization_eid=organization_eid,
                row=row,
                tier=target_tier,
                scope="branch",
            )
            record_organization_practice(
                self.sim,
                organization_eid=organization_eid,
                entry_key=payload.get("entry_key"),
                practice_kind=payload.get("practice_kind"),
                domain_key=payload.get("domain_key"),
                label=payload.get("label"),
                summary=payload.get("summary"),
                source_kind=payload.get("source_kind"),
                discovery_key=payload.get("discovery_key"),
                service_ids=payload.get("service_ids"),
                item_tags=payload.get("item_tags"),
                realization_kinds=payload.get("realization_kinds"),
                effect_modifiers=payload.get("effect_modifiers"),
                target_scope=payload.get("target_scope"),
                target_property_id=payload.get("target_property_id"),
                target_building_id=payload.get("target_building_id"),
                target_field_domains=payload.get("target_field_domains"),
                priority=payload.get("priority"),
                active=True,
            )
        record_organization_practice_progress(
            self.sim,
            organization_eid=organization_eid,
            progress_key=row.get("progress_key"),
            last_evaluated_tick=tick,
            tier=target_tier,
        )
        return target_tier

    def _promotable_child_rows(self, parent_eid, *, focus_key, domain_key):
        child_ids = {
            _safe_int(row.get("organization_eid"), default=0)
            for row in organization_child_organizations(self.sim, parent_eid, recursive=False)
        }
        rows = []
        for child_eid in child_ids:
            if child_eid <= 0:
                continue
            for row in organization_practice_progress_rows(
                self.sim,
                child_eid,
                focus_key=focus_key,
                domain_key=domain_key,
                scope="branch",
            ):
                rows.append((child_eid, row))
        return tuple(rows)

    def _maybe_promote_branch_row(self, organization_eid, row):
        profile = organization_profile(self.sim, organization_eid)
        parent_eid = _safe_int(getattr(profile, "parent_org_eid", 0), default=0) if profile else 0
        if parent_eid <= 0:
            return
        if bool(row.get("promoted_to_parent", False)):
            return
        focus_key = _text(row.get("focus_key")).lower()
        domain_key = _text(row.get("domain_key")).lower()
        siblings = self._promotable_child_rows(parent_eid, focus_key=focus_key, domain_key=domain_key)
        strong_branch = _safe_float(row.get("activity_points"), default=0.0) >= ROOT_PROMOTION_THRESHOLD
        tier2_children = {
            child_eid
            for child_eid, child_row in siblings
            if _safe_int(child_row.get("tier"), default=0) >= 2
        }
        if not strong_branch and len(tier2_children) < 2:
            return

        payload = _practice_row_payload(
            self.sim,
            organization_eid=parent_eid,
            row=row,
            tier=2,
            scope="root",
        )
        root_entry_key = f"root_emergence:{focus_key}:{domain_key}:{parent_eid}"
        record_organization_practice(
            self.sim,
            organization_eid=parent_eid,
            entry_key=root_entry_key,
            practice_kind=payload.get("practice_kind"),
            domain_key=payload.get("domain_key"),
            label=payload.get("label"),
            summary=payload.get("summary"),
            source_kind=payload.get("source_kind"),
            discovery_key=payload.get("discovery_key"),
            service_ids=payload.get("service_ids"),
            item_tags=payload.get("item_tags"),
            realization_kinds=payload.get("realization_kinds"),
            effect_modifiers=payload.get("effect_modifiers"),
            target_scope="organization",
            target_field_domains=payload.get("target_field_domains"),
            priority=payload.get("priority"),
            active=True,
        )
        for child_eid, child_row in siblings:
            if _safe_int(child_row.get("tier"), default=0) < 2 and _safe_float(child_row.get("activity_points"), default=0.0) < ROOT_PROMOTION_THRESHOLD:
                continue
            record_organization_practice_progress(
                self.sim,
                organization_eid=child_eid,
                progress_key=child_row.get("progress_key"),
                promoted_to_parent=True,
            )

    def update(self):
        tick = _safe_int(getattr(self.sim, "tick", 0), default=0)
        self._periodic_collective_staffing_signals(tick)
        for organization_eid, _component in self.sim.ecs.get(OrganizationPracticeProgress).items():
            rows = organization_practice_progress_rows(self.sim, organization_eid, scope="branch")
            for row in rows:
                if tick - _safe_int(row.get("last_evaluated_tick"), default=0) < self.refresh_interval:
                    continue
                tier = self._evaluate_branch_row(organization_eid, row, tick)
                if int(tier) >= 2:
                    refreshed_rows = organization_practice_progress_rows(
                        self.sim,
                        organization_eid,
                        focus_key=row.get("focus_key"),
                        domain_key=row.get("domain_key"),
                        scope="branch",
                    )
                    target_row = next(
                        (
                            candidate
                            for candidate in refreshed_rows
                            if _text(candidate.get("progress_key")) == _text(row.get("progress_key"))
                        ),
                        row,
                    )
                    self._maybe_promote_branch_row(organization_eid, target_row)
