import random

from game.components import (
    Occupation,
    OrganizationAffiliations,
    OrganizationPractices,
    OrganizationProfile,
    OrganizationVocabulary,
)
from game.org_names import generate_organization_name


RESIDENTIAL_ARCHETYPES = {
    "apartment",
    "house",
    "tenement",
    "hotel",
    "ranger_hut",
    "ruin_shelter",
    "field_camp",
    "survey_post",
    "beacon_house",
}
INSTITUTION_ARCHETYPES = {
    "armory",
    "barracks",
    "checkpoint",
    "command_center",
    "courthouse",
    "jail",
    "prison",
    "data_center",
    "lab",
    "office",
    "server_hub",
    "tower",
}
PUBLIC_OWNER_TAGS = {"", "city", "community", "none", "public", "unowned"}
CIVIC_DEPARTMENT_BY_ARCHETYPE = {
    "armory": ("civic_security", "Security Bureau"),
    "barracks": ("civic_security", "Security Bureau"),
    "checkpoint": ("civic_security", "Security Bureau"),
    "command_center": ("civic_admin", "Operations Office"),
    "courthouse": ("civic_justice", "Justice Office"),
    "jail": ("civic_corrections", "Corrections Department"),
    "prison": ("civic_corrections", "Corrections Department"),
    "dock_shack": ("civic_transit", "Transit Authority"),
    "ferry_post": ("civic_transit", "Transit Authority"),
    "metro_exchange": ("civic_transit", "Transit Authority"),
    "pump_house": ("civic_utility", "Utility Works"),
    "relay_post": ("civic_transit", "Transit Authority"),
    "tide_station": ("civic_utility", "Utility Works"),
}
MANAGER_ROLE_KEYWORDS = {
    "chief",
    "controller",
    "coordinator",
    "director",
    "executive",
    "lead",
    "manager",
    "quartermaster",
    "supervisor",
}
ORGANIZATION_KINDS = {
    "business",
    "civic",
    "institution",
    "gang",
    "crew",
    "criminal",
    "community",
    "other",
}
ORGANIZATION_KIND_ALIASES = {
    "organization": "other",
    "criminal_org": "criminal",
    "criminal_organization": "criminal",
    "community_group": "community",
    "municipal": "civic",
}
MEMBERSHIP_KINDS = {"ownership", "employment", "membership", "contract"}
SITE_LINK_KINDS = {"operates", "territory", "meeting_place", "safehouse", "service_host"}
RELATION_KINDS = {
    "ally",
    "rival",
    "oversight",
    "service",
    "represents",
    "bargains_with",
    "certifies",
    "affiliates_with",
}
DIRECTED_RELATION_KINDS = {"oversight", "service", "represents", "bargains_with", "certifies"}
RECIPROCAL_RELATION_KINDS = {"ally", "rival", "affiliates_with"}
PRIMARY_MEMBERSHIP_KINDS = ("ownership", "employment")
ORGANIZATION_VOCABULARY_KINDS = {
    "incident_notice",
    "site_brief",
    "subject_notice",
    "directive",
    "opportunity_lead",
}
ORGANIZATION_VOCABULARY_TARGET_SCOPES = {
    "organization",
    "property",
    "building",
    "link_kind",
    "role",
    "member",
}
ORGANIZATION_PRACTICE_KINDS = {
    "service_mutation",
    "skill_method",
    "operational_pattern",
    "field_discovery",
}
ORGANIZATION_VOCABULARY_SCOPE_ALIASES = {
    "site": "property",
    "site_property": "property",
    "site_building": "building",
    "member_role": "role",
}
DEFAULT_AUTHORITY_RANKS = {
    "owner": 0,
    "manager": 20,
    "staff": 50,
    "member": 70,
}
NON_SITE_CHUNK_ORGANIZATION_FACTIONS = {
    "coppers",
    "corpsec",
    "dock_union",
    "neon_gang",
    "syndicate",
}
ORGANIZATION_STRUCTURE_MODES = {"flat", "federated", "cell"}
ORGANIZATION_STRUCTURE_BY_KIND = {
    "business": "flat",
    "civic": "flat",
    "institution": "federated",
    "gang": "cell",
    "crew": "cell",
    "criminal": "cell",
    "community": "flat",
    "other": "flat",
}
ORGANIZATION_FAMILY_BY_TAG = {
    "municipal_root": "municipal",
    "coppers": "civic_security",
    "corpsec": "corporate",
    "dock_union": "labor_union",
    "union": "labor_union",
    "labor_union": "labor_union",
    "guild": "trade_guild",
    "trade_guild": "trade_guild",
    "professional_association": "trade_guild",
    "vigilante": "street_gang",
    "neon_gang": "street_gang",
    "syndicate": "criminal_network",
}
CORPORATE_BRANCH_ARCHETYPES = {
    "bank",
    "biotech_clinic",
    "brokerage",
    "co_working_hub",
    "contractor_office",
    "courier_office",
    "data_center",
    "media_lab",
    "office",
}
DOCK_UNION_AFFILIATE_ARCHETYPES = {
    "cold_storage",
    "contractor_office",
    "courier_office",
    "dock_shack",
    "drydock_yard",
    "ferry_post",
    "freight_depot",
    "metro_exchange",
    "relay_post",
    "tool_depot",
    "truck_stop",
    "warehouse",
}
NEON_GANG_CELL_ARCHETYPES = {
    "bar",
    "chop_shop",
    "flophouse",
    "junk_market",
    "nightclub",
    "pawn_shop",
    "street_kitchen",
}
SYNDICATE_CELL_ARCHETYPES = {
    "backroom_clinic",
    "brokerage",
    "courier_office",
    "hotel",
    "office",
    "pawn_shop",
    "warehouse",
}
CRIMINAL_SAFEHOUSE_ARCHETYPES = {"backroom_clinic", "flophouse", "hotel"}
CRIMINAL_MEETING_ARCHETYPES = {"bar", "gaming_hall", "junk_market", "music_venue", "nightclub", "pawn_shop", "pool_hall", "street_kitchen", "theater"}
CRIMINAL_SERVICE_HOST_ARCHETYPES = {"backroom_clinic", "brokerage", "chop_shop", "courier_office", "office", "pawn_shop", "warehouse"}
CRIMINAL_CELL_TITLES_BY_FAMILY = {
    "street_gang": {
        "owner": "cell lead",
        "manager": "lieutenant",
        "staff": "runner",
        "member": "runner",
    },
    "criminal_network": {
        "owner": "cell controller",
        "manager": "coordinator",
        "staff": "associate",
        "member": "associate",
    },
}
CRIMINAL_CELL_RANKS_BY_PRIMARY_ROLE = {
    "owner": 10,
    "manager": 30,
    "staff": 60,
    "member": 70,
}
STREET_GANG_FORMATION_REASONS = (
    "displacement",
    "massacre",
    "predation",
    "protection",
    "retaliation",
    "scarcity",
)
STREET_GANG_POSTURES = (
    "predatory",
    "smuggling",
    "territorial",
    "vigilante",
)
SERVICE_FIELD_DOMAIN_BY_SERVICE = {
    "banking": "finance",
    "insurance": "finance",
    "intel": "intel",
    "medical": "medical",
    "triage": "medical",
    "repair": "repair",
    "building_repair": "repair",
    "business_remodel": "property_services",
    "rest": "hospitality",
    "shelter": "hospitality",
    "fuel": "mobility",
    "vending": "retail",
    "underground_access": "criminal",
    "vehicle_fetch": "vehicle_trade",
    "vehicle_sales_new": "vehicle_trade",
    "vehicle_sales_used": "vehicle_trade",
    "rail_transit": "transit",
    "bus_transit": "transit",
    "shuttle_transit": "transit",
    "ferry_transit": "transit",
}
ARCHETYPE_FIELD_DOMAINS = {
    "auto_garage": ("repair", "mobility"),
    "backroom_clinic": ("medical",),
    "bank": ("finance",),
    "biotech_clinic": ("medical", "technology"),
    "brokerage": ("finance",),
    "cold_storage": ("logistics",),
    "contractor_office": ("property_services", "repair"),
    "co_working_hub": ("professional_services",),
    "courier_office": ("logistics", "transit"),
    "data_center": ("technology",),
    "dock_shack": ("maritime", "logistics"),
    "drydock_yard": ("maritime", "repair"),
    "factory": ("industrial",),
    "ferry_post": ("transit", "maritime"),
    "flophouse": ("criminal", "hospitality"),
    "freight_depot": ("logistics",),
    "hardware_store": ("repair", "retail"),
    "junk_market": ("trade", "criminal"),
    "media_lab": ("media", "technology"),
    "metro_exchange": ("transit",),
    "office": ("professional_services",),
    "pawn_shop": ("finance", "trade"),
    "pharmacy": ("medical", "retail"),
    "relay_post": ("transit", "intel"),
    "service_station": ("mobility", "repair"),
    "street_kitchen": ("trade",),
    "tool_depot": ("repair", "trade"),
    "truck_stop": ("logistics", "mobility"),
    "warehouse": ("logistics",),
    "chop_shop": ("repair", "criminal"),
}
CAREER_FIELD_KEYWORDS = {
    "finance": ("bank", "broker", "credit", "insurance", "teller", "capital"),
    "intel": ("intel", "signal", "archive", "records"),
    "logistics": ("courier", "dispatch", "forklift", "inventory", "manifest", "parcel", "route", "sort", "supply", "warehouse"),
    "maritime": ("dock", "ferry", "harbor", "pier", "ship", "tide"),
    "medical": ("clinic", "counselor", "med", "nurse", "lab", "screening"),
    "mobility": ("fuel", "motor", "driver", "yard_host"),
    "professional_services": ("advisory", "consult", "analyst", "coordinator", "manager", "office"),
    "property_services": ("contractor", "glazier", "mason", "property_repair", "shopfitter"),
    "repair": ("repair", "mechanic", "garage", "tech", "service_bay", "tool"),
    "technology": ("broadcast", "compute", "data", "editor", "media", "server", "studio", "technician"),
    "transit": ("agent", "controller", "inspector", "platform", "transit"),
    "trade": ("merchant", "counter", "sales"),
}
COLLECTIVE_MEMBERSHIP_ROLE_DEFAULTS = ("staff", "member")


def _text(value):
    return str(value or "").strip()


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _property_metadata(prop):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _property_archetype(prop):
    return _text(_property_metadata(prop).get("archetype")).lower()


def _normalize_org_kind(value, default="other"):
    kind = _text(value).lower().replace(" ", "_")
    kind = ORGANIZATION_KIND_ALIASES.get(kind, kind)
    if kind in ORGANIZATION_KINDS:
        return kind
    return default


def _normalize_membership_kind(value, default="membership"):
    kind = _text(value).lower().replace(" ", "_")
    if kind == "member":
        kind = "membership"
    if kind in MEMBERSHIP_KINDS:
        return kind
    return default


def _normalize_link_kind(value, default="operates"):
    kind = _text(value).lower().replace(" ", "_")
    if kind in SITE_LINK_KINDS:
        return kind
    return default


def _normalize_relation_kind(value, default="service"):
    kind = _text(value).lower().replace(" ", "_")
    if kind in RELATION_KINDS:
        return kind
    return default


def _normalize_vocabulary_kind(value, default="directive"):
    kind = _text(value).lower().replace(" ", "_")
    if kind in ORGANIZATION_VOCABULARY_KINDS:
        return kind
    return default


def _normalize_vocabulary_scope(value, default="organization"):
    scope = _text(value).lower().replace(" ", "_")
    scope = ORGANIZATION_VOCABULARY_SCOPE_ALIASES.get(scope, scope)
    if scope in ORGANIZATION_VOCABULARY_TARGET_SCOPES:
        return scope
    return default


def _normalize_membership_role(value, default="member"):
    role = _text(value).lower().replace(" ", "_")
    if role in {"owner", "manager", "staff", "member"}:
        return role
    if role in {"leader", "lieutenant", "grunt"}:
        return "member"
    return default


def _normalize_text_tuple(values):
    if isinstance(values, str):
        values = (values,)
    cleaned = {
        _text(value).lower().replace(" ", "_")
        for value in (values or ())
        if _text(value)
    }
    return tuple(sorted(cleaned))


def _normalize_actor_eid_tuple(values):
    if values is None:
        return ()
    if isinstance(values, (int, float)):
        values = (values,)
    cleaned = []
    for value in values or ():
        actor_eid = _safe_int(value, default=0)
        if actor_eid > 0 and actor_eid not in cleaned:
            cleaned.append(actor_eid)
    return tuple(sorted(cleaned))


def _normalize_org_eid_tuple(values):
    if values is None:
        return ()
    if isinstance(values, (int, float)):
        values = (values,)
    cleaned = []
    for value in values or ():
        organization_eid = _safe_int(value, default=0)
        if organization_eid > 0 and organization_eid not in cleaned:
            cleaned.append(organization_eid)
    return tuple(sorted(cleaned))


def _normalize_target_roles(values):
    if values is None:
        return ()
    if isinstance(values, str):
        values = (values,)
    cleaned = {
        _normalize_membership_role(value, default="")
        for value in (values or ())
    }
    cleaned.discard("")
    return tuple(sorted(cleaned))


def _normalize_priority(value, default=50):
    return max(0, min(100, _safe_int(value, default=default)))


def _default_authority_rank(role, fallback=70):
    return int(DEFAULT_AUTHORITY_RANKS.get(_normalize_membership_role(role), fallback))


def _slug(value):
    text = _text(value).lower()
    chars = []
    last_sep = False
    for ch in text:
        if ch.isalnum():
            chars.append(ch)
            last_sep = False
        elif not last_sep:
            chars.append("_")
            last_sep = True
    return "".join(chars).strip("_")


def _organization_index(sim):
    index = getattr(sim, "organization_index", None)
    if isinstance(index, dict):
        return index
    index = {}
    sim.organization_index = index
    return index


def _organization_seed_store(sim):
    store = getattr(sim, "organization_seed_records", None)
    if isinstance(store, dict):
        return store
    store = {}
    sim.organization_seed_records = store
    return store


def property_service_ids(prop):
    metadata = _property_metadata(prop)
    services = set()
    for field in ("finance_services", "site_services"):
        raw = metadata.get(field)
        if isinstance(raw, str):
            raw = (raw,)
        for value in raw or ():
            service_id = _text(value).lower().replace(" ", "_")
            if service_id:
                services.add(service_id)
    return tuple(sorted(services))


def property_field_domains(prop):
    metadata = _property_metadata(prop)
    domains = set()
    configured = metadata.get("organization_field_domains")
    if isinstance(configured, str):
        configured = (configured,)
    domains.update(_normalize_text_tuple(configured))
    for service_id in property_service_ids(prop):
        domain = SERVICE_FIELD_DOMAIN_BY_SERVICE.get(service_id)
        if domain:
            domains.add(domain)
    domains.update(ARCHETYPE_FIELD_DOMAINS.get(_property_archetype(prop), ()))
    if bool(metadata.get("dialogue_trade_only")) or _text(metadata.get("hidden_contact_kind")):
        domains.add("criminal")
    return tuple(sorted(_text(domain).lower().replace(" ", "_") for domain in domains if _text(domain)))


def career_field_domains(career):
    career_key = _text(career).lower().replace(" ", "_")
    if not career_key:
        return ()
    domains = set()
    for domain, keywords in CAREER_FIELD_KEYWORDS.items():
        if any(keyword in career_key for keyword in keywords):
            domains.add(domain)
    return tuple(sorted(domains))


def _district_text(district, key):
    if not isinstance(district, dict):
        return ""
    return _text(district.get(key))


def _district_scope_identity(district):
    scope_name = _district_text(district, "settlement_name") or _district_text(district, "region_name") or "Metro"
    scope_slug = _slug(scope_name) or "metro"
    return scope_name, scope_slug


def _tag_prefix_value(tags, prefix):
    prefix = _text(prefix).lower()
    if not prefix:
        return ""
    for tag in sorted(tags or ()):
        clean_tag = _text(tag).lower()
        if clean_tag.startswith(prefix):
            return clean_tag.split(":", 1)[1] if ":" in clean_tag else ""
    return ""


def _family_from_tags(tags):
    normalized = {
        _text(tag).lower().replace(" ", "_")
        for tag in (tags or ())
        if _text(tag)
    }
    for tag, family in ORGANIZATION_FAMILY_BY_TAG.items():
        if tag in normalized:
            return family
    return ""


def _merge_metadata_tags(metadata, field, *tags):
    if not isinstance(metadata, dict):
        return ()
    existing = metadata.get(field)
    merged = []
    if isinstance(existing, (list, tuple, set)):
        for tag in existing:
            clean_tag = _text(tag).lower().replace(" ", "_")
            if clean_tag and clean_tag not in merged:
                merged.append(clean_tag)
    for tag in tags:
        clean_tag = _text(tag).lower().replace(" ", "_")
        if clean_tag and clean_tag not in merged:
            merged.append(clean_tag)
    metadata[field] = tuple(merged)
    return metadata[field]


def _property_business_label(prop):
    metadata = _property_metadata(prop)
    return _text(metadata.get("business_name")) or _text(metadata.get("organization_name"))


def _corporate_domain_for_district(district, *, default="logistics"):
    district_type = _district_text(district, "district_type").lower()
    if district_type == "corporate":
        return "technology"
    if district_type == "downtown":
        return "finance"
    if district_type in {"industrial"}:
        return "logistics"
    if district_type in {"entertainment"}:
        return "hospitality"
    if district_type in {"military"}:
        return "security"
    return default


def _corporate_parent_defaults_for_property(prop, district):
    if not isinstance(prop, dict):
        return None
    metadata = _property_metadata(prop)
    if _text(metadata.get("parent_organization_key")):
        return None
    if _district_text(district, "dominant_faction").lower() != "corpsec":
        return None
    archetype = _property_archetype(prop)
    if archetype not in CORPORATE_BRANCH_ARCHETYPES:
        return None
    if not _property_business_label(prop):
        return None

    _scope_name, scope_slug = _district_scope_identity(district)
    domain_tag = _corporate_domain_for_district(district, default="technology")
    return {
        "parent_organization_key": f"business:corpsec:{scope_slug}",
        "parent_organization_name": "",
        "parent_organization_kind": "business",
        "parent_organization_tags": (
            "corpsec",
            "corporate",
            "org_role:root",
            "org_structure:federated",
            domain_tag,
            _district_text(district, "area_type").lower() or "city",
            _district_text(district, "district_type").lower() or "district",
        ),
        "organization_kind": "business",
        "organization_tags": (
            "corpsec_branch",
            "corporate_branch",
            "org_role:branch",
            archetype,
            domain_tag,
        ),
    }


def _normalize_affiliate_spec(spec):
    spec = dict(spec or {})
    return {
        "organization_key": _text(spec.get("organization_key")) or None,
        "organization_name": _text(spec.get("organization_name")) or None,
        "organization_kind": _normalize_org_kind(spec.get("organization_kind"), default="community"),
        "tags": _normalize_text_tuple(spec.get("tags")),
        "parent_organization_key": _text(spec.get("parent_organization_key")) or None,
        "link_kind": _normalize_link_kind(spec.get("link_kind"), default="service_host"),
        "relation_kind": _normalize_relation_kind(spec.get("relation_kind"), default="service")
        if _text(spec.get("relation_kind"))
        else None,
        "reverse_relation_kind": _normalize_relation_kind(spec.get("reverse_relation_kind"), default="service")
        if _text(spec.get("reverse_relation_kind"))
        else None,
        "membership_kind": _normalize_membership_kind(spec.get("membership_kind"), default="membership"),
        "membership_title": _text(spec.get("membership_title")) or None,
        "membership_roles": _normalize_target_roles(
            spec.get("membership_roles", spec.get("target_roles", COLLECTIVE_MEMBERSHIP_ROLE_DEFAULTS))
        ),
        "service_ids": _normalize_text_tuple(spec.get("service_ids")),
        "field_domains": _normalize_text_tuple(spec.get("field_domains")),
        "career_keywords": _normalize_text_tuple(spec.get("career_keywords")),
        "allow_owner_membership": bool(spec.get("allow_owner_membership", False)),
        "active": bool(spec.get("active", True)),
    }


def _merge_affiliate_specs(metadata, specs):
    if not isinstance(metadata, dict):
        return ()
    existing = metadata.get("affiliate_organizations")
    merged = []
    if isinstance(existing, (list, tuple, set)):
        for raw in existing:
            if not isinstance(raw, dict):
                continue
            normalized = _normalize_affiliate_spec(raw)
            if not normalized.get("organization_key"):
                continue
            merged.append(normalized)
    for raw in specs or ():
        if not isinstance(raw, dict):
            continue
        normalized = _normalize_affiliate_spec(raw)
        if not normalized.get("organization_key"):
            continue
        matched = False
        for index, existing_row in enumerate(merged):
            if (
                existing_row.get("organization_key") == normalized.get("organization_key")
                and existing_row.get("link_kind") == normalized.get("link_kind")
            ):
                merged[index] = {
                    **existing_row,
                    **{key: value for key, value in normalized.items() if value not in (None, (), "")},
                }
                matched = True
                break
        if not matched:
            merged.append(normalized)
    metadata["affiliate_organizations"] = tuple(merged)
    return metadata["affiliate_organizations"]


def _dock_union_affiliate_defaults_for_property(prop, district):
    if not isinstance(prop, dict):
        return ()
    if _district_text(district, "dominant_faction").lower() != "dock_union":
        return ()
    metadata = _property_metadata(prop)
    if bool(metadata.get("public")):
        return ()
    archetype = _property_archetype(prop)
    domains = set(property_field_domains(prop))
    if archetype not in DOCK_UNION_AFFILIATE_ARCHETYPES and not domains.intersection({"logistics", "maritime", "transit", "repair"}):
        return ()

    scope_name, scope_slug = _district_scope_identity(district)
    return (
        {
            "organization_key": f"community:dock_union:{scope_slug}",
            "organization_name": f"{scope_name} Dock Union".strip(),
            "organization_kind": "community",
            "tags": (
                "dock_union",
                "labor_union",
                "union",
                "labor",
                "org_role:root",
                "org_structure:flat",
            ),
            "link_kind": "service_host",
            "relation_kind": "represents",
            "reverse_relation_kind": "bargains_with",
            "membership_kind": "membership",
            "membership_title": "union member",
            "membership_roles": ("staff",),
            "service_ids": property_service_ids(prop),
            "field_domains": tuple(sorted(domains)),
            "career_keywords": ("dock", "dispatch", "courier", "warehouse", "route", "manifest", "repair", "transit"),
        },
    )


def _property_chunk_district(sim, prop):
    if sim is None or not isinstance(prop, dict):
        return {}
    world = getattr(sim, "world", None)
    if world is None or not hasattr(world, "get_chunk"):
        return {}
    try:
        x = int(prop.get("x", 0))
        y = int(prop.get("y", 0))
    except (TypeError, ValueError):
        return {}
    chunk_x, chunk_y = sim.chunk_coords(x, y)
    chunk = world.get_chunk(chunk_x, chunk_y)
    if not isinstance(chunk, dict):
        return {}
    district = chunk.get("district")
    return district if isinstance(district, dict) else {}


def _criminal_cell_link_kind(prop, *, default="meeting_place"):
    archetype = _property_archetype(prop)
    metadata = _property_metadata(prop)
    hidden_kind = _text(metadata.get("hidden_contact_kind")).lower()
    if archetype in CRIMINAL_SAFEHOUSE_ARCHETYPES or hidden_kind == "backroom_clinic":
        return "safehouse"
    if archetype in CRIMINAL_SERVICE_HOST_ARCHETYPES or bool(metadata.get("dialogue_trade_only")):
        return "service_host"
    if archetype in CRIMINAL_MEETING_ARCHETYPES:
        return "meeting_place"
    return default


def _criminal_cell_anchor_slug(prop):
    anchor = _property_business_label(prop) or _text(prop.get("name")) or _text(prop.get("id"))
    return _slug(anchor) or _slug(_text(prop.get("id"))) or "cell"


def _criminal_cell_name(prop, *, family="", link_kind="meeting_place"):
    anchor = _property_business_label(prop) or _text(prop.get("name")) or "Back Room"
    if family == "street_gang":
        suffix = "House" if link_kind == "safehouse" else "Crew"
        return f"{anchor} {suffix}".strip()
    if family == "criminal_network":
        suffix = "House" if link_kind == "safehouse" else "Ring" if link_kind == "service_host" else "Circle"
        return f"{anchor} {suffix}".strip()
    return f"{anchor} Cell".strip()


def _neon_gang_cell_affiliate_defaults_for_property(prop, district):
    if not isinstance(prop, dict):
        return ()
    if _district_text(district, "dominant_faction").lower() != "neon_gang":
        return ()
    metadata = _property_metadata(prop)
    if bool(metadata.get("public")):
        return ()
    archetype = _property_archetype(prop)
    if not (
        archetype in NEON_GANG_CELL_ARCHETYPES
        or bool(metadata.get("dialogue_trade_only"))
        or _text(metadata.get("hidden_contact_kind"))
    ):
        return ()
    scope_name, scope_slug = _district_scope_identity(district)
    root_key = f"gang:neon_gang:{scope_slug}"
    link_kind = _criminal_cell_link_kind(prop, default="meeting_place")
    cell_key = f"{root_key}:cell:{_criminal_cell_anchor_slug(prop)}"
    field_domains = set(property_field_domains(prop))
    field_domains.add("criminal")
    return (
        {
            "organization_key": cell_key,
            "organization_name": _criminal_cell_name(prop, family="street_gang", link_kind=link_kind),
            "organization_kind": "gang",
            "tags": (
                "neon_gang",
                "criminal",
                "street_gang",
                "org_role:cell",
                "org_structure:cell",
                f"cell_link:{link_kind}",
                _district_text(district, "area_type").lower() or "city",
                _district_text(district, "district_type").lower() or "district",
            ),
            "parent_organization_key": root_key,
            "link_kind": link_kind,
            "membership_kind": "membership",
            "membership_roles": ("owner", "manager", "staff"),
            "membership_title": "cell member",
            "allow_owner_membership": True,
            "service_ids": property_service_ids(prop),
            "field_domains": tuple(sorted(field_domains)),
        },
    )


def _syndicate_cell_affiliate_defaults_for_property(prop, district):
    if not isinstance(prop, dict):
        return ()
    if _district_text(district, "dominant_faction").lower() != "syndicate":
        return ()
    metadata = _property_metadata(prop)
    if bool(metadata.get("public")):
        return ()
    archetype = _property_archetype(prop)
    if not (
        archetype in SYNDICATE_CELL_ARCHETYPES
        or bool(metadata.get("dialogue_trade_only"))
        or _text(metadata.get("hidden_contact_kind"))
    ):
        return ()
    scope_name, scope_slug = _district_scope_identity(district)
    root_key = f"criminal:syndicate:{scope_slug}"
    link_kind = _criminal_cell_link_kind(prop, default="service_host")
    cell_key = f"{root_key}:cell:{_criminal_cell_anchor_slug(prop)}"
    field_domains = set(property_field_domains(prop))
    field_domains.update({"criminal", "trade"})
    return (
        {
            "organization_key": cell_key,
            "organization_name": _criminal_cell_name(prop, family="criminal_network", link_kind=link_kind),
            "organization_kind": "criminal",
            "tags": (
                "syndicate",
                "criminal",
                "network",
                "org_role:cell",
                "org_structure:cell",
                f"cell_link:{link_kind}",
                _district_text(district, "area_type").lower() or "city",
                _district_text(district, "district_type").lower() or "district",
            ),
            "parent_organization_key": root_key,
            "link_kind": link_kind,
            "membership_kind": "membership",
            "membership_roles": ("owner", "manager", "staff"),
            "membership_title": "cell associate",
            "allow_owner_membership": True,
            "service_ids": property_service_ids(prop),
            "field_domains": tuple(sorted(field_domains)),
        },
    )


def _criminal_family_affiliate_defaults_for_property(prop, district):
    specs = []
    specs.extend(_neon_gang_cell_affiliate_defaults_for_property(prop, district))
    specs.extend(_syndicate_cell_affiliate_defaults_for_property(prop, district))
    return tuple(specs)


def _street_gang_origin_tags(*, world_seed=0, organization_key=""):
    key = _text(organization_key) or "gang"
    rng = random.Random(f"{world_seed}:street-gang-origin:{key}")
    reason = str(rng.choice(STREET_GANG_FORMATION_REASONS)).strip().lower()
    posture = str(rng.choice(STREET_GANG_POSTURES)).strip().lower()
    tags = {f"formation_reason:{reason}", f"gang_posture:{posture}"}
    if posture == "vigilante":
        tags.add("vigilante")
    return tuple(sorted(tags))


def property_affiliate_organization_specs(prop):
    metadata = _property_metadata(prop)
    raw_specs = metadata.get("affiliate_organizations")
    if not isinstance(raw_specs, (list, tuple, set)):
        return ()
    rows = []
    seen = set()
    for raw in raw_specs:
        if not isinstance(raw, dict):
            continue
        normalized = _normalize_affiliate_spec(raw)
        key = (normalized.get("organization_key"), normalized.get("link_kind"))
        if not normalized.get("organization_key") or key in seen:
            continue
        seen.add(key)
        rows.append(normalized)
    return tuple(rows)


def _generated_chunk_organization_seeds(sim, chunk):
    if not isinstance(chunk, dict):
        return ()
    district = chunk.get("district") if isinstance(chunk.get("district"), dict) else {}
    dominant_faction = _district_text(district, "dominant_faction").lower()
    if dominant_faction not in NON_SITE_CHUNK_ORGANIZATION_FACTIONS:
        return ()

    scope_name, scope_slug = _district_scope_identity(district)
    district_type = _district_text(district, "district_type").lower()
    area_type = _district_text(district, "area_type").lower()
    world_seed = getattr(sim, "seed", 0)
    seeds = []

    def add_seed(
        *,
        organization_key,
        organization_name,
        organization_kind,
        tags,
        parent_organization_key=None,
    ):
        key = _text(organization_key)
        if not key:
            return
        normalized_tags = tuple(
            sorted(
                {
                    _text(tag).lower().replace(" ", "_")
                    for tag in (tags or ())
                    if _text(tag)
                }
            )
        )
        seeds.append(
            {
                "organization_key": key,
                "organization_name": _text(organization_name) or key,
                "organization_kind": _normalize_org_kind(organization_kind, default="other"),
                "tags": normalized_tags,
                "parent_organization_key": _text(parent_organization_key) or None,
            }
        )

    admin_root_key = ""
    if area_type == "city" or dominant_faction == "coppers":
        admin_root_key = f"civic_admin:{scope_slug}"
        add_seed(
            organization_key=admin_root_key,
            organization_name=f"{scope_name} Operations Office",
            organization_kind="civic",
            tags=("municipal_root", "org_role:root", "org_structure:federated", area_type, district_type),
        )

    if dominant_faction == "coppers":
        add_seed(
            organization_key=f"civic_security:{scope_slug}",
            organization_name=f"{scope_name} Security Bureau",
            organization_kind="civic",
            tags=("coppers", "security", "municipal", "org_role:department", area_type, district_type),
            parent_organization_key=admin_root_key or None,
        )
    elif dominant_faction == "dock_union":
        add_seed(
            organization_key=f"community:dock_union:{scope_slug}",
            organization_name=f"{scope_name} Dock Union",
            organization_kind="community",
            tags=("dock_union", "labor", "union", "org_role:root", "org_structure:flat", area_type, district_type),
        )
    elif dominant_faction == "neon_gang":
        add_seed(
            organization_key=f"gang:neon_gang:{scope_slug}",
            organization_name=generate_organization_name(
                world_seed=world_seed,
                organization_key=f"gang:neon_gang:{scope_slug}",
                style="gang",
                settlement_name=_district_text(district, "settlement_name"),
                region_name=_district_text(district, "region_name"),
            ),
            organization_kind="gang",
            tags=(
                "neon_gang",
                "criminal",
                "street_gang",
                "org_role:root",
                "org_structure:cell",
                area_type,
                district_type,
            ) + _street_gang_origin_tags(
                world_seed=world_seed,
                organization_key=f"gang:neon_gang:{scope_slug}",
            ),
        )
    elif dominant_faction == "syndicate":
        add_seed(
            organization_key=f"criminal:syndicate:{scope_slug}",
            organization_name=generate_organization_name(
                world_seed=world_seed,
                organization_key=f"criminal:syndicate:{scope_slug}",
                style="corporate",
                settlement_name=_district_text(district, "settlement_name"),
                region_name=_district_text(district, "region_name"),
                domain_key=_corporate_domain_for_district(district, default="finance"),
            ),
            organization_kind="criminal",
            tags=("syndicate", "criminal", "network", "org_role:root", "org_structure:cell", area_type, district_type),
        )
    elif dominant_faction == "corpsec":
        add_seed(
            organization_key=f"business:corpsec:{scope_slug}",
            organization_name=generate_organization_name(
                world_seed=world_seed,
                organization_key=f"business:corpsec:{scope_slug}",
                style="corporate",
                settlement_name=_district_text(district, "settlement_name"),
                region_name=_district_text(district, "region_name"),
                domain_key=_corporate_domain_for_district(district, default="technology"),
            ),
            organization_kind="business",
            tags=(
                "corpsec",
                "corporate",
                _corporate_domain_for_district(district, default="technology"),
                "org_role:root",
                "org_structure:federated",
                area_type,
                district_type,
            ),
        )

    return tuple(seeds)


def _normalize_site_link_row(row, organization_eid=None):
    row = dict(row or {})
    link_kind = _normalize_link_kind(row.get("link_kind"), default="operates")
    primary = bool(row.get("primary", link_kind == "operates"))
    if link_kind != "operates":
        primary = False
    return {
        "organization_eid": _safe_int(row.get("organization_eid"), default=organization_eid) or None,
        "property_id": _text(row.get("property_id")) or None,
        "building_id": _text(row.get("building_id")) or None,
        "link_kind": link_kind,
        "primary": bool(primary),
        "active": bool(row.get("active", True)),
    }


def _normalize_relation_row(row):
    row = dict(row or {})
    kind = _normalize_relation_kind(row.get("kind"), default="service")
    directed = bool(row.get("directed", kind in DIRECTED_RELATION_KINDS))
    if kind in DIRECTED_RELATION_KINDS:
        directed = True
    if kind in RECIPROCAL_RELATION_KINDS:
        directed = False
    return {
        "target_org_eid": _safe_int(row.get("target_org_eid"), default=0) or None,
        "kind": kind,
        "active": bool(row.get("active", True)),
        "directed": bool(directed),
    }


def _normalize_membership_row(row, organization_eid=None):
    row = dict(row or {})
    role = _normalize_membership_role(row.get("role"), default="member")
    authority_rank = _safe_int(row.get("authority_rank"), default=_default_authority_rank(role))
    supervisor_eid = _safe_int(row.get("supervisor_eid"), default=0) or None
    return {
        "organization_eid": _safe_int(row.get("organization_eid"), default=organization_eid) or None,
        "role": role,
        "kind": _normalize_membership_kind(row.get("kind"), default="membership"),
        "site_property_id": _text(row.get("site_property_id")) or None,
        "site_building_id": _text(row.get("site_building_id")) or None,
        "title": _text(row.get("title")) or None,
        "primary": bool(row.get("primary", False)),
        "authority_rank": int(authority_rank),
        "supervisor_eid": supervisor_eid,
        "active": bool(row.get("active", True)),
    }


def _ensure_profile_state(profile):
    if profile is None:
        return None
    profile.name = _text(getattr(profile, "name", "")) or "Organization"
    profile.kind = _normalize_org_kind(getattr(profile, "kind", ""), default="other")
    profile.key = _text(getattr(profile, "key", ""))
    profile.tags = {
        _normalize_org_kind(tag, default=_text(tag).lower().replace(" ", "_"))
        if _text(tag).lower().replace(" ", "_") in ORGANIZATION_KINDS
        else _text(tag).lower().replace(" ", "_")
        for tag in getattr(profile, "tags", ())
        if _text(tag)
    }
    profile.parent_org_eid = _safe_int(getattr(profile, "parent_org_eid", None), default=0) or None
    profile.site_property_ids = set(_text(value) for value in getattr(profile, "site_property_ids", ()) if _text(value))
    profile.site_building_ids = set(_text(value) for value in getattr(profile, "site_building_ids", ()) if _text(value))
    profile.member_eids = set(_safe_int(value, default=0) for value in getattr(profile, "member_eids", ()) if _safe_int(value, default=0) > 0)
    raw_links = getattr(profile, "site_links", None)
    if not isinstance(raw_links, list):
        raw_links = []
    profile.site_links = [_normalize_site_link_row(row) for row in raw_links if isinstance(row, dict)]
    raw_relations = getattr(profile, "relations", None)
    if not isinstance(raw_relations, list):
        raw_relations = []
    profile.relations = [_normalize_relation_row(row) for row in raw_relations if isinstance(row, dict)]
    _refresh_profile_site_caches(profile)
    return profile


def _refresh_profile_site_caches(profile):
    if profile is None:
        return None
    profile.site_property_ids = {
        _text(row.get("property_id"))
        for row in profile.site_links
        if bool(row.get("active", True)) and _text(row.get("property_id"))
    }
    profile.site_building_ids = {
        _text(row.get("building_id"))
        for row in profile.site_links
        if bool(row.get("active", True)) and _text(row.get("building_id"))
    }
    return profile


def _refresh_profile_member_cache(sim, organization_eid):
    profile = organization_profile(sim, organization_eid)
    if profile is None:
        return None
    members = set()
    for actor_eid, affiliations in sim.ecs.get(OrganizationAffiliations).items():
        if not affiliations or not isinstance(getattr(affiliations, "memberships", None), dict):
            continue
        row = affiliations.memberships.get(int(organization_eid))
        if not isinstance(row, dict):
            continue
        row = _normalize_membership_row(row, organization_eid=organization_eid)
        affiliations.memberships[int(organization_eid)] = row
        if bool(row.get("active", True)):
            members.add(int(actor_eid))
    profile.member_eids = members
    return profile


def rebuild_organization_index(sim):
    index = _organization_index(sim)
    index.clear()
    for organization_eid, profile in sim.ecs.get(OrganizationProfile).items():
        profile = _ensure_profile_state(profile)
        if profile and _text(profile.key):
            index[_text(profile.key)] = int(organization_eid)
    return index


def register_organization_seed(
    sim,
    *,
    organization_key,
    organization_name="",
    organization_kind="other",
    tags=None,
    parent_organization_key=None,
):
    key = _text(organization_key)
    if not key:
        return None
    seed = {
        "organization_key": key,
        "organization_name": _text(organization_name) or key,
        "organization_kind": _normalize_org_kind(organization_kind, default="other"),
        "tags": tuple(
            sorted(
                {
                    _text(tag).lower().replace(" ", "_")
                    for tag in (tags or ())
                    if _text(tag)
                }
            )
        ),
        "parent_organization_key": _text(parent_organization_key) or None,
    }
    _organization_seed_store(sim)[key] = seed
    return dict(seed)


def seed_organizations(sim, seeds):
    if not isinstance(seeds, (list, tuple)):
        return ()
    registered = []
    for raw in seeds:
        if not isinstance(raw, dict):
            continue
        seed = register_organization_seed(
            sim,
            organization_key=raw.get("organization_key"),
            organization_name=raw.get("organization_name"),
            organization_kind=raw.get("organization_kind"),
            tags=raw.get("tags"),
            parent_organization_key=raw.get("parent_organization_key"),
        )
        if seed:
            registered.append(seed)
    created = []
    for seed in registered:
        organization_eid = ensure_organization(
            sim,
            organization_key=seed.get("organization_key"),
            organization_name=seed.get("organization_name"),
            organization_kind=seed.get("organization_kind"),
            tags=seed.get("tags"),
            parent_organization_key=seed.get("parent_organization_key"),
        )
        if organization_eid is not None:
            created.append(int(organization_eid))
    return tuple(created)


def seed_chunk_organizations(sim, chunk):
    return seed_organizations(sim, _generated_chunk_organization_seeds(sim, chunk))


def seed_property_organization_defaults(prop, district=None):
    if not isinstance(prop, dict):
        return False

    metadata = _property_metadata(prop)
    changed = False

    affiliate_defaults = _dock_union_affiliate_defaults_for_property(prop, district)
    affiliate_defaults += _criminal_family_affiliate_defaults_for_property(prop, district)
    if affiliate_defaults:
        before = tuple(property_affiliate_organization_specs(prop))
        after = tuple(_merge_affiliate_specs(metadata, affiliate_defaults))
        if after != before:
            changed = True

    corporate_defaults = _corporate_parent_defaults_for_property(prop, district)
    if corporate_defaults:
        for field, value in corporate_defaults.items():
            if field == "organization_tags":
                _merge_metadata_tags(metadata, field, *(value or ()))
                changed = True
                continue
            if field == "parent_organization_tags":
                _merge_metadata_tags(metadata, field, *(value or ()))
                changed = True
                continue
            if field == "organization_kind":
                if not _text(metadata.get("organization_kind")):
                    metadata["organization_kind"] = _normalize_org_kind(value, default="business")
                    changed = True
                continue
            if not _text(metadata.get(field)):
                metadata[field] = value
                changed = True

    if _text(metadata.get("organization_key")):
        return changed

    archetype = _property_archetype(prop)
    owner_tag = _text(prop.get("owner_tag")).lower()
    if owner_tag not in PUBLIC_OWNER_TAGS:
        return changed

    department = CIVIC_DEPARTMENT_BY_ARCHETYPE.get(archetype)
    if not department:
        return changed

    scope_name = _district_text(district, "settlement_name") or _district_text(district, "region_name") or "Metro"
    scope_slug = _slug(scope_name) or "metro"
    department_key, department_name = department

    metadata["organization_key"] = f"{department_key}:{scope_slug}"
    if not _text(metadata.get("organization_name")):
        metadata["organization_name"] = f"{scope_name} {department_name}".strip()
    if not _text(metadata.get("organization_kind")):
        metadata["organization_kind"] = "civic"
    if department_key != "civic_admin" and not _text(metadata.get("parent_organization_key")):
        metadata["parent_organization_key"] = f"civic_admin:{scope_slug}"
    if _text(metadata.get("parent_organization_key")):
        if not _text(metadata.get("parent_organization_name")):
            metadata["parent_organization_name"] = f"{scope_name} Operations Office".strip()
        if not _text(metadata.get("parent_organization_kind")):
            metadata["parent_organization_kind"] = "civic"
        if not isinstance(metadata.get("parent_organization_tags"), (list, tuple, set)):
            metadata["parent_organization_tags"] = (
                "municipal_root",
                "org_role:root",
                "org_structure:federated",
                _district_text(district, "area_type").lower() or "city",
                _district_text(district, "district_type").lower() or "district",
            )
    return True


def _organization_key_for_property(prop):
    metadata = _property_metadata(prop)
    configured = _text(metadata.get("organization_key"))
    if configured:
        return configured

    shared_name = _text(metadata.get("business_name")) or _text(metadata.get("organization_name"))
    if shared_name:
        slug = _slug(shared_name)
        if slug:
            return f"org:{slug}"

    property_id = _text(prop.get("id"))
    if property_id:
        return f"site:{property_id}"

    building_id = _text(metadata.get("building_id"))
    if building_id:
        return f"building:{building_id}"

    return ""


def _organization_kind_for_property(prop):
    metadata = _property_metadata(prop)
    configured = _normalize_org_kind(metadata.get("organization_kind"), default="")
    if configured:
        return configured

    archetype = _property_archetype(prop)
    owner_tag = _text(prop.get("owner_tag")).lower()
    if archetype in INSTITUTION_ARCHETYPES:
        return "institution"
    if owner_tag in PUBLIC_OWNER_TAGS:
        return "civic"
    return "business"


def _organization_name_for_property(prop):
    metadata = _property_metadata(prop)
    explicit = _text(metadata.get("organization_name"))
    if explicit:
        return explicit

    business_name = _text(metadata.get("business_name"))
    if business_name:
        return business_name

    return _text(prop.get("name")) or "Organization"


def _organization_tags_for_property(prop, kind):
    metadata = _property_metadata(prop)
    configured_tags = metadata.get("organization_tags")
    configured_role = ""
    if isinstance(configured_tags, (list, tuple, set)):
        configured_role = _tag_prefix_value(configured_tags, "org_role:")
    tags = {
        _normalize_org_kind(kind, default="business"),
        _text(prop.get("kind")).lower() or "property",
    }

    archetype = _property_archetype(prop)
    if archetype:
        tags.add(archetype)
    if bool(metadata.get("is_storefront")):
        tags.add("storefront")
    if bool(metadata.get("public")):
        tags.add("public")

    finance_services = metadata.get("finance_services", ())
    if isinstance(finance_services, (list, tuple, set)) and finance_services:
        tags.add("finance")
    site_services = metadata.get("site_services", ())
    if isinstance(site_services, (list, tuple, set)) and site_services:
        tags.add("services")
    parent_organization_key = _text(metadata.get("parent_organization_key"))
    if parent_organization_key and not configured_role:
        tags.add("org_role:department" if _normalize_org_kind(kind, default="other") == "civic" else "org_role:operator")
    if isinstance(configured_tags, (list, tuple, set)):
        tags.update(
            _text(tag).lower().replace(" ", "_")
            for tag in configured_tags
            if _text(tag)
        )
    for domain in property_field_domains(prop):
        tags.add(f"field:{domain}")
    for service_id in property_service_ids(prop):
        tags.add(f"service:{service_id}")

    return tuple(sorted(tag for tag in tags if tag))


def property_supports_organization(prop):
    if not isinstance(prop, dict):
        return False
    if _text(prop.get("kind")).lower() != "building":
        return False

    metadata = _property_metadata(prop)
    if _text(metadata.get("organization_key")) or _text(metadata.get("organization_name")):
        return True

    archetype = _property_archetype(prop)
    finance_services = metadata.get("finance_services", ())
    site_services = metadata.get("site_services", ())
    has_services = bool(finance_services) or bool(site_services)
    if (
        archetype in RESIDENTIAL_ARCHETYPES
        and not bool(metadata.get("is_storefront"))
        and not has_services
        and not _text(metadata.get("business_name"))
    ):
        return False
    return True


def organization_profile(sim, organization_eid):
    if organization_eid is None:
        return None
    profile = sim.ecs.get(OrganizationProfile).get(int(organization_eid))
    return _ensure_profile_state(profile)


def organization_name(sim, organization_eid, fallback=""):
    profile = organization_profile(sim, organization_eid)
    if profile and _text(getattr(profile, "name", "")):
        return _text(profile.name)
    return _text(fallback)


def organization_eid_for_key(sim, organization_key):
    key = _text(organization_key)
    if not key:
        return None
    index = _organization_index(sim)
    organization_eid = index.get(key)
    if organization_eid is not None and organization_profile(sim, organization_eid) is not None:
        return int(organization_eid)
    rebuild_organization_index(sim)
    organization_eid = index.get(key)
    if organization_eid is not None and organization_profile(sim, organization_eid) is not None:
        return int(organization_eid)
    return None


def organization_ancestor_chain(sim, organization_eid, *, include_self=False, max_depth=8):
    profile = organization_profile(sim, organization_eid)
    if profile is None:
        return ()
    rows = []
    seen = set()
    current_eid = int(organization_eid) if include_self else (_safe_int(profile.parent_org_eid, default=0) or None)
    depth = 0
    while current_eid is not None and depth < int(max_depth):
        current_eid = _safe_int(current_eid, default=0) or None
        if current_eid is None or current_eid in seen:
            break
        seen.add(int(current_eid))
        current_profile = organization_profile(sim, current_eid)
        if current_profile is None:
            break
        rows.append(
            {
                "organization_eid": int(current_eid),
                "organization_key": _text(current_profile.key),
                "organization_name": _text(current_profile.name),
                "organization_kind": _normalize_org_kind(current_profile.kind, default="other"),
                "depth": int(depth if include_self else depth + 1),
                "parent_org_eid": _safe_int(current_profile.parent_org_eid, default=0) or None,
            }
        )
        current_eid = current_profile.parent_org_eid
        depth += 1
    return tuple(rows)


def _organization_lineage_eids(sim, organization_eid, *, include_self=True, max_depth=8):
    if organization_eid is None:
        return ()
    eids = []
    if include_self:
        eids.append(int(organization_eid))
    eids.extend(int(row.get("organization_eid", 0)) for row in organization_ancestor_chain(sim, organization_eid, include_self=False, max_depth=max_depth))
    cleaned = []
    for eid in eids:
        if eid > 0 and eid not in cleaned:
            cleaned.append(eid)
    return tuple(cleaned)


def organization_root_eid(sim, organization_eid, *, max_depth=8):
    lineage = _organization_lineage_eids(sim, organization_eid, include_self=True, max_depth=max_depth)
    if not lineage:
        return None
    return int(lineage[-1])


def organization_child_organizations(sim, organization_eid, *, recursive=False):
    if organization_eid is None:
        return ()
    target_eid = int(organization_eid)
    rows = []
    pending = [target_eid]
    seen_parents = set()
    seen_children = set()
    while pending:
        parent_eid = pending.pop(0)
        if parent_eid in seen_parents:
            continue
        seen_parents.add(parent_eid)
        for child_eid, profile in sim.ecs.get(OrganizationProfile).items():
            profile = organization_profile(sim, child_eid)
            if profile is None or _safe_int(profile.parent_org_eid, default=0) != int(parent_eid):
                continue
            child_eid = int(child_eid)
            if child_eid in seen_children:
                continue
            seen_children.add(child_eid)
            rows.append(
                {
                    "organization_eid": child_eid,
                    "organization_key": _text(profile.key),
                    "organization_name": _text(profile.name),
                    "organization_kind": _normalize_org_kind(profile.kind, default="other"),
                    "parent_org_eid": _safe_int(profile.parent_org_eid, default=0) or None,
                }
            )
            if recursive:
                pending.append(child_eid)
    rows.sort(
        key=lambda row: (
            _text(row.get("organization_name")).lower(),
            _safe_int(row.get("organization_eid"), default=0),
        )
    )
    return tuple(rows)


def organization_policy_snapshot(sim, organization_eid=None, *, organization_key=None, prop=None):
    if organization_eid is None and organization_key is not None:
        organization_eid = ensure_organization(sim, organization_key=organization_key)
    if organization_eid is None and isinstance(prop, dict):
        organization_eid = property_organization_eid(sim, prop, ensure=True)
    profile = organization_profile(sim, organization_eid)
    if profile is None:
        return None

    root_eid = organization_root_eid(sim, organization_eid) or int(organization_eid)
    root_profile = organization_profile(sim, root_eid)
    current_tags = set(getattr(profile, "tags", ()) or ())
    root_tags = set(getattr(root_profile, "tags", ()) or ()) if root_profile else set(current_tags)

    structure = _tag_prefix_value(current_tags, "org_structure:")
    if not structure:
        structure = _tag_prefix_value(root_tags, "org_structure:")
    if structure not in ORGANIZATION_STRUCTURE_MODES:
        structure = ORGANIZATION_STRUCTURE_BY_KIND.get(
            _normalize_org_kind(getattr(root_profile, "kind", getattr(profile, "kind", "")), default="other"),
            "flat",
        )

    family = (
        _family_from_tags(current_tags)
        or _family_from_tags(root_tags)
        or (
            "street_gang"
            if _normalize_org_kind(getattr(root_profile, "kind", getattr(profile, "kind", "")), default="other") in {"gang", "crew"}
            else "criminal_network"
            if _normalize_org_kind(getattr(root_profile, "kind", getattr(profile, "kind", "")), default="other") == "criminal"
            else _normalize_org_kind(getattr(root_profile, "kind", getattr(profile, "kind", "")), default="other")
        )
    )

    role = _tag_prefix_value(current_tags, "org_role:")
    if not role:
        if int(root_eid) == int(organization_eid):
            role = "root"
        elif family == "municipal":
            role = "department"
        elif structure == "cell":
            role = "cell"
        else:
            role = "operator"

    return {
        "organization_eid": int(organization_eid),
        "organization_key": _text(profile.key),
        "organization_name": _text(profile.name),
        "organization_kind": _normalize_org_kind(profile.kind, default="other"),
        "family": family,
        "structure": structure,
        "org_role": role,
        "root_organization_eid": int(root_eid),
        "root_organization_key": _text(getattr(root_profile, "key", "")),
        "root_organization_name": _text(getattr(root_profile, "name", "")),
        "root_organization_kind": _normalize_org_kind(getattr(root_profile, "kind", ""), default="other") if root_profile else "other",
        "ancestor_chain": organization_ancestor_chain(sim, organization_eid, include_self=False),
    }


def ensure_organization(
    sim,
    *,
    organization_key=None,
    organization_name="",
    organization_kind="other",
    tags=None,
    parent_organization_key=None,
    parent_org_eid=None,
):
    key = _text(organization_key)
    name = _text(organization_name)
    kind = _normalize_org_kind(organization_kind, default="other")
    store = _organization_seed_store(sim)
    seed = store.get(key) if key else None

    if not key and name:
        key = f"org:{_slug(name)}" if _slug(name) else ""
        seed = store.get(key) if key else None
    if seed:
        if not name:
            name = _text(seed.get("organization_name"))
        if kind == "other":
            kind = _normalize_org_kind(seed.get("organization_kind"), default="other")
        if tags is None:
            tags = seed.get("tags")
        if not parent_organization_key:
            parent_organization_key = seed.get("parent_organization_key")
    if not key:
        return None

    if parent_org_eid is None and _text(parent_organization_key):
        parent_org_eid = ensure_organization(sim, organization_key=parent_organization_key)

    index = _organization_index(sim)
    organization_eid = index.get(key)
    profile = organization_profile(sim, organization_eid) if organization_eid is not None else None
    if profile is None and organization_eid is None:
        rebuild_organization_index(sim)
        organization_eid = index.get(key)
        profile = organization_profile(sim, organization_eid) if organization_eid is not None else None

    if profile is None:
        organization_eid = sim.ecs.create()
        profile = OrganizationProfile(
            name=name or key,
            kind=kind,
            key=key,
            tags=tags or (),
            parent_org_eid=parent_org_eid,
        )
        sim.ecs.add(organization_eid, profile)
        profile = organization_profile(sim, organization_eid)
    else:
        if name:
            profile.name = name
        if kind:
            profile.kind = kind
        if tags:
            profile.tags.update(
                _text(tag).lower().replace(" ", "_")
                for tag in tags
                if _text(tag)
            )
        if parent_org_eid is not None:
            profile.parent_org_eid = int(parent_org_eid)

    index[key] = int(organization_eid)
    if key and (seed or name or tags or parent_organization_key):
        register_organization_seed(
            sim,
            organization_key=key,
            organization_name=profile.name,
            organization_kind=profile.kind,
            tags=sorted(profile.tags),
            parent_organization_key=parent_organization_key or (
                organization_profile(sim, profile.parent_org_eid).key if profile.parent_org_eid else None
            ),
        )
    return int(organization_eid)


def _normalize_org_kind_tuple(values):
    if values is None:
        return ()
    if isinstance(values, str):
        values = (values,)
    cleaned = []
    for value in values or ():
        kind = _normalize_org_kind(value, default="")
        if kind and kind not in cleaned:
            cleaned.append(kind)
    return tuple(sorted(cleaned))


def _normalize_target_filters(row):
    row = dict(row or {})
    return {
        "target_affiliated_org_eids": _normalize_org_eid_tuple(
            row.get("target_affiliated_org_eids", row.get("target_employer_org_eids"))
        ),
        "target_affiliated_org_keys": _normalize_text_tuple(
            row.get("target_affiliated_org_keys", row.get("target_employer_org_keys"))
        ),
        "target_affiliated_org_kinds": _normalize_org_kind_tuple(
            row.get("target_affiliated_org_kinds", row.get("target_employer_org_kinds"))
        ),
        "target_affiliated_org_tags": _normalize_text_tuple(
            row.get("target_affiliated_org_tags", row.get("target_employer_org_tags"))
        ),
        "target_titles": _normalize_text_tuple(row.get("target_titles")),
        "target_careers": _normalize_text_tuple(row.get("target_careers")),
        "target_service_ids": _normalize_text_tuple(row.get("target_service_ids")),
        "target_field_domains": _normalize_text_tuple(row.get("target_field_domains")),
    }


def _normalize_vocabulary_row(row, organization_eid=None, entry_id=None):
    row = dict(row or {})
    raw_entry_id = _safe_int(row.get("entry_id"), default=entry_id or 0)
    target_scope = _normalize_vocabulary_scope(row.get("target_scope"), default="organization")
    target_property_id = _text(row.get("target_property_id")) or None
    target_building_id = _text(row.get("target_building_id")) or None
    target_link_kind_text = _text(row.get("target_link_kind"))
    target_link_kind = (
        _normalize_link_kind(target_link_kind_text, default="operates")
        if target_link_kind_text
        else None
    )
    target_roles = _normalize_target_roles(row.get("target_roles"))
    target_member_eids = _normalize_actor_eid_tuple(row.get("target_member_eids"))
    target_filters = _normalize_target_filters(row)

    if target_scope == "property" and target_property_id is None:
        target_property_id = _text(row.get("subject_property_id")) or None
    if target_scope == "building" and target_building_id is None:
        target_building_id = _text(row.get("subject_building_id")) or None
    if target_scope == "property" and target_property_id is None:
        target_scope = "organization"
    elif target_scope == "building" and target_building_id is None:
        target_scope = "organization"
    elif target_scope == "link_kind" and target_link_kind is None:
        target_scope = "organization"
    elif target_scope == "role" and not target_roles:
        target_scope = "organization"
    elif target_scope == "member" and not target_member_eids:
        target_scope = "organization"

    raw_expires_tick = row.get("expires_tick")
    expires_tick = (
        _safe_int(raw_expires_tick, default=0)
        if raw_expires_tick not in (None, "")
        else None
    )
    return {
        "organization_eid": _safe_int(row.get("organization_eid"), default=organization_eid) or None,
        "entry_id": raw_entry_id or None,
        "entry_key": _text(row.get("entry_key")).lower().replace(" ", "_") or None,
        "kind": _normalize_vocabulary_kind(row.get("kind", row.get("vocabulary_kind")), default="directive"),
        "topic_key": _text(row.get("topic_key")).lower().replace(" ", "_") or None,
        "label": _text(row.get("label")) or None,
        "summary": _text(row.get("summary")) or None,
        "source_kind": _text(row.get("source_kind")).lower().replace(" ", "_") or None,
        "source_eid": _safe_int(row.get("source_eid"), default=0) or None,
        "incident_id": _safe_int(row.get("incident_id"), default=0) or None,
        "subject_actor_eid": _safe_int(row.get("subject_actor_eid"), default=0) or None,
        "subject_property_id": _text(row.get("subject_property_id")) or None,
        "subject_building_id": _text(row.get("subject_building_id")) or None,
        "target_scope": target_scope,
        "target_property_id": target_property_id,
        "target_building_id": target_building_id,
        "target_link_kind": target_link_kind,
        "target_roles": target_roles,
        "target_member_eids": target_member_eids,
        **target_filters,
        "tags": _normalize_text_tuple(row.get("tags")),
        "priority": int(_normalize_priority(row.get("priority"), default=50)),
        "active": bool(row.get("active", True)),
        "effective_tick": _safe_int(row.get("effective_tick"), default=_safe_int(row.get("created_tick"), default=0)),
        "expires_tick": expires_tick,
        "created_tick": _safe_int(row.get("created_tick"), default=0),
        "last_update_tick": _safe_int(row.get("last_update_tick"), default=_safe_int(row.get("created_tick"), default=0)),
    }


def _sort_vocabulary_rows(rows):
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                0 if bool(row.get("active", True)) else 1,
                -int(row.get("priority", 50)),
                -int(row.get("last_update_tick", 0)),
                -int(row.get("created_tick", 0)),
                -_safe_int(row.get("entry_id"), default=0),
                _text(row.get("organization_name")).lower(),
            ),
        )
    )


def _trim_organization_vocabulary(component):
    if component is None:
        return None
    if len(component.entries) <= int(component.max_entries):
        return component
    keep_ids = {
        int(row.get("entry_id"))
        for row in _sort_vocabulary_rows(component.entries.values())[: int(component.max_entries)]
        if _safe_int(row.get("entry_id"), default=0) > 0
    }
    component.entries = {
        int(entry_id): row
        for entry_id, row in component.entries.items()
        if int(entry_id) in keep_ids
    }
    return component


def _ensure_organization_vocabulary_component(sim, organization_eid, *, create=False):
    if organization_eid is None:
        return None
    component = sim.ecs.get(OrganizationVocabulary).get(int(organization_eid))
    if component is None and create:
        component = OrganizationVocabulary()
        sim.ecs.add(int(organization_eid), component)
    if component is None:
        return None

    component.max_entries = max(8, _safe_int(getattr(component, "max_entries", 64), default=64))
    component.next_entry_id = max(1, _safe_int(getattr(component, "next_entry_id", 1), default=1))
    raw_entries = getattr(component, "entries", None)
    if not isinstance(raw_entries, dict):
        raw_entries = {}
    entries = {}
    max_entry_id = 0
    for stored_entry_id, row in raw_entries.items():
        normalized = _normalize_vocabulary_row(
            row,
            organization_eid=organization_eid,
            entry_id=stored_entry_id,
        )
        clean_entry_id = _safe_int(normalized.get("entry_id"), default=0)
        if clean_entry_id <= 0:
            continue
        normalized["entry_id"] = int(clean_entry_id)
        entries[int(clean_entry_id)] = normalized
        max_entry_id = max(max_entry_id, int(clean_entry_id))
    component.entries = entries
    component.next_entry_id = max(int(component.next_entry_id), max_entry_id + 1)
    _trim_organization_vocabulary(component)
    return component


def _find_organization_vocabulary_entry_id(component, *, entry_id=None, entry_key=None):
    if component is None:
        return None
    clean_entry_id = _safe_int(entry_id, default=0)
    if clean_entry_id > 0 and clean_entry_id in component.entries:
        return int(clean_entry_id)
    key = _text(entry_key).lower().replace(" ", "_")
    if not key:
        return None
    for stored_entry_id, row in component.entries.items():
        if _text(row.get("entry_key")).lower().replace(" ", "_") == key:
            return int(stored_entry_id)
    return None


def _vocabulary_row_is_current(
    row,
    *,
    current_tick=0,
    active_only=True,
    include_future=False,
    include_expired=False,
):
    if not isinstance(row, dict):
        return False
    if active_only and not bool(row.get("active", True)):
        return False
    now_tick = _safe_int(current_tick, default=0)
    if not include_future and now_tick < _safe_int(row.get("effective_tick"), default=0):
        return False
    expires_tick = row.get("expires_tick")
    if not include_expired and expires_tick is not None and now_tick > _safe_int(expires_tick, default=now_tick):
        return False
    return True


def record_organization_vocabulary(
    sim,
    *,
    organization_eid=None,
    organization_key=None,
    organization_name="",
    organization_kind="other",
    vocabulary_kind=None,
    entry_id=None,
    entry_key=None,
    topic_key=None,
    label=None,
    summary=None,
    source_kind=None,
    source_eid=None,
    incident_id=None,
    subject_actor_eid=None,
    subject_property_id=None,
    subject_building_id=None,
    target_scope=None,
    target_property_id=None,
    target_building_id=None,
    target_link_kind=None,
    target_roles=None,
    target_member_eids=None,
    target_affiliated_org_eids=None,
    target_affiliated_org_keys=None,
    target_affiliated_org_kinds=None,
    target_affiliated_org_tags=None,
    target_titles=None,
    target_careers=None,
    target_service_ids=None,
    target_field_domains=None,
    tags=None,
    priority=None,
    active=None,
    effective_tick=None,
    expires_tick=None,
    created_tick=None,
):
    if organization_eid is None:
        organization_eid = ensure_organization(
            sim,
            organization_key=organization_key,
            organization_name=organization_name,
            organization_kind=organization_kind,
        )
    profile = organization_profile(sim, organization_eid)
    if profile is None:
        return None

    component = _ensure_organization_vocabulary_component(sim, organization_eid, create=True)
    if component is None:
        return None

    now_tick = _safe_int(getattr(sim, "tick", 0), default=0)
    matched_entry_id = _find_organization_vocabulary_entry_id(
        component,
        entry_id=entry_id,
        entry_key=entry_key,
    )
    existing = (
        dict(component.entries.get(int(matched_entry_id)))
        if matched_entry_id is not None and int(matched_entry_id) in component.entries
        else {}
    )
    if matched_entry_id is None:
        matched_entry_id = _safe_int(entry_id, default=0) or int(component.next_entry_id)

    if created_tick is None:
        created_tick = existing.get("created_tick", now_tick)
    if effective_tick is None:
        effective_tick = existing.get("effective_tick", created_tick)
    if target_scope is None:
        if existing:
            target_scope = existing.get("target_scope")
        elif target_property_id or subject_property_id:
            target_scope = "property"
        elif target_building_id or subject_building_id:
            target_scope = "building"
        elif target_link_kind:
            target_scope = "link_kind"
        elif target_roles:
            target_scope = "role"
        elif target_member_eids:
            target_scope = "member"
        else:
            target_scope = "organization"
    if target_property_id is None and existing:
        target_property_id = existing.get("target_property_id")
    if target_building_id is None and existing:
        target_building_id = existing.get("target_building_id")
    if target_link_kind is None and existing:
        target_link_kind = existing.get("target_link_kind")
    if target_roles is None and existing:
        target_roles = existing.get("target_roles")
    if target_member_eids is None and existing:
        target_member_eids = existing.get("target_member_eids")
    if target_affiliated_org_eids is None and existing:
        target_affiliated_org_eids = existing.get("target_affiliated_org_eids")
    if target_affiliated_org_keys is None and existing:
        target_affiliated_org_keys = existing.get("target_affiliated_org_keys")
    if target_affiliated_org_kinds is None and existing:
        target_affiliated_org_kinds = existing.get("target_affiliated_org_kinds")
    if target_affiliated_org_tags is None and existing:
        target_affiliated_org_tags = existing.get("target_affiliated_org_tags")
    if target_titles is None and existing:
        target_titles = existing.get("target_titles")
    if target_careers is None and existing:
        target_careers = existing.get("target_careers")
    if target_service_ids is None and existing:
        target_service_ids = existing.get("target_service_ids")
    if target_field_domains is None and existing:
        target_field_domains = existing.get("target_field_domains")
    if tags is None:
        tags = existing.get("tags")
    else:
        combined_tags = set(existing.get("tags", ()))
        combined_tags.update(_normalize_text_tuple(tags))
        tags = tuple(sorted(combined_tags))

    row = dict(existing)
    row.update(
        {
            "organization_eid": int(organization_eid),
            "entry_id": int(matched_entry_id),
            "entry_key": existing.get("entry_key") if entry_key is None else entry_key,
            "kind": existing.get("kind", "directive") if vocabulary_kind is None else vocabulary_kind,
            "topic_key": existing.get("topic_key") if topic_key is None else topic_key,
            "label": existing.get("label") if label is None else label,
            "summary": existing.get("summary") if summary is None else summary,
            "source_kind": existing.get("source_kind") if source_kind is None else source_kind,
            "source_eid": existing.get("source_eid") if source_eid is None else source_eid,
            "incident_id": existing.get("incident_id") if incident_id is None else incident_id,
            "subject_actor_eid": existing.get("subject_actor_eid") if subject_actor_eid is None else subject_actor_eid,
            "subject_property_id": existing.get("subject_property_id")
            if subject_property_id is None
            else subject_property_id,
            "subject_building_id": existing.get("subject_building_id")
            if subject_building_id is None
            else subject_building_id,
            "target_scope": target_scope,
            "target_property_id": target_property_id,
            "target_building_id": target_building_id,
            "target_link_kind": target_link_kind,
            "target_roles": target_roles,
            "target_member_eids": target_member_eids,
            "target_affiliated_org_eids": target_affiliated_org_eids,
            "target_affiliated_org_keys": target_affiliated_org_keys,
            "target_affiliated_org_kinds": target_affiliated_org_kinds,
            "target_affiliated_org_tags": target_affiliated_org_tags,
            "target_titles": target_titles,
            "target_careers": target_careers,
            "target_service_ids": target_service_ids,
            "target_field_domains": target_field_domains,
            "tags": tags,
            "priority": existing.get("priority", 50) if priority is None else priority,
            "active": existing.get("active", True) if active is None else active,
            "effective_tick": effective_tick,
            "expires_tick": existing.get("expires_tick") if expires_tick is None else expires_tick,
            "created_tick": created_tick,
            "last_update_tick": now_tick,
        }
    )
    normalized = _normalize_vocabulary_row(
        row,
        organization_eid=organization_eid,
        entry_id=matched_entry_id,
    )
    normalized_entry_id = _safe_int(normalized.get("entry_id"), default=0)
    if normalized_entry_id <= 0:
        return None
    normalized["entry_id"] = int(normalized_entry_id)
    component.entries[int(normalized_entry_id)] = normalized
    component.next_entry_id = max(int(component.next_entry_id), int(normalized_entry_id) + 1)
    _trim_organization_vocabulary(component)
    return dict(normalized)


def organization_vocabulary_entries(
    sim,
    organization_eid,
    *,
    active_only=True,
    vocabulary_kind=None,
    current_tick=None,
    include_future=False,
    include_expired=False,
    include_ancestors=False,
    max_lineage_depth=8,
):
    requested_profile = organization_profile(sim, organization_eid)
    if requested_profile is None:
        return ()
    current_tick = getattr(sim, "tick", 0) if current_tick is None else current_tick
    requested_kind = ""
    if vocabulary_kind is not None:
        requested_kind = _text(vocabulary_kind).lower().replace(" ", "_")
        if requested_kind not in ORGANIZATION_VOCABULARY_KINDS:
            return ()

    rows = []
    source_organization_eids = _organization_lineage_eids(
        sim,
        organization_eid,
        include_self=True,
        max_depth=max_lineage_depth,
    ) if include_ancestors else (int(organization_eid),)

    for lineage_depth, source_organization_eid in enumerate(source_organization_eids):
        profile = organization_profile(sim, source_organization_eid)
        component = _ensure_organization_vocabulary_component(sim, source_organization_eid, create=False)
        if profile is None or component is None:
            continue
        for entry_id, row in component.entries.items():
            row = _normalize_vocabulary_row(row, organization_eid=source_organization_eid, entry_id=entry_id)
            if requested_kind and row.get("kind") != requested_kind:
                continue
            if not _vocabulary_row_is_current(
                row,
                current_tick=current_tick,
                active_only=active_only,
                include_future=include_future,
                include_expired=include_expired,
            ):
                continue
            rows.append(
                {
                    **row,
                    "organization_eid": int(source_organization_eid),
                    "organization_key": _text(profile.key),
                    "organization_name": _text(profile.name),
                    "organization_kind": _normalize_org_kind(profile.kind, default="other"),
                    "requested_organization_eid": int(organization_eid),
                    "requested_organization_key": _text(requested_profile.key),
                    "requested_organization_name": _text(requested_profile.name),
                    "requested_organization_kind": _normalize_org_kind(requested_profile.kind, default="other"),
                    "lineage_depth": int(lineage_depth),
                }
    )
    return _sort_vocabulary_rows(rows)


def _property_affiliated_org_rows(sim, prop):
    rows = []
    for link in property_org_links(sim, prop, active_only=True):
        profile = organization_profile(sim, link.get("organization_eid"))
        rows.append(
            {
                "organization_eid": _safe_int(link.get("organization_eid"), default=0) or None,
                "organization_key": _text(link.get("organization_key")),
                "organization_kind": _normalize_org_kind(link.get("organization_kind"), default="other"),
                "organization_tags": tuple(sorted(getattr(profile, "tags", ()) or ())) if profile else (),
            }
        )
    return tuple(rows)


def _row_targets_affiliated_orgs(row, org_rows):
    target_eids = set(_normalize_org_eid_tuple(row.get("target_affiliated_org_eids")))
    target_keys = set(_normalize_text_tuple(row.get("target_affiliated_org_keys")))
    target_kinds = set(_normalize_org_kind_tuple(row.get("target_affiliated_org_kinds")))
    target_tags = set(_normalize_text_tuple(row.get("target_affiliated_org_tags")))
    if not any((target_eids, target_keys, target_kinds, target_tags)):
        return True
    for org_row in org_rows or ():
        org_eid = _safe_int(org_row.get("organization_eid"), default=0)
        org_key = _text(org_row.get("organization_key")).lower().replace(" ", "_")
        org_kind = _normalize_org_kind(org_row.get("organization_kind"), default="other")
        org_tags = set(_normalize_text_tuple(org_row.get("organization_tags")))
        if target_eids and org_eid not in target_eids:
            continue
        if target_keys and org_key not in target_keys:
            continue
        if target_kinds and org_kind not in target_kinds:
            continue
        if target_tags and not org_tags.intersection(target_tags):
            continue
        return True
    return False


def _row_targets_property_filters(sim, row, prop):
    service_targets = set(_normalize_text_tuple(row.get("target_service_ids")))
    domain_targets = set(_normalize_text_tuple(row.get("target_field_domains")))
    if service_targets and not set(property_service_ids(prop)).intersection(service_targets):
        return False
    if domain_targets and not set(property_field_domains(prop)).intersection(domain_targets):
        return False
    return _row_targets_affiliated_orgs(row, _property_affiliated_org_rows(sim, prop))


def _vocabulary_targets_property(sim, row, prop):
    if not isinstance(row, dict) or not isinstance(prop, dict):
        return False
    scope = _normalize_vocabulary_scope(row.get("target_scope"), default="organization")
    if scope == "organization":
        return _row_targets_property_filters(sim, row, prop)
    if scope == "property":
        return _text(row.get("target_property_id")) == _text(prop.get("id")) and _row_targets_property_filters(sim, row, prop)
    metadata = _property_metadata(prop)
    building_ids = {
        _text(metadata.get("building_id")),
        _text(metadata.get("local_building_id")),
    }
    if scope == "building":
        return _text(row.get("target_building_id")) in building_ids and _row_targets_property_filters(sim, row, prop)
    if scope == "link_kind":
        target_link_kind = _text(row.get("target_link_kind")).lower()
        organization_eid = _safe_int(
            row.get("requested_organization_eid"),
            default=_safe_int(row.get("organization_eid"), default=0),
        )
        return any(
            int(link.get("organization_eid", -1)) == organization_eid
            and _text(link.get("link_kind")).lower() == target_link_kind
            for link in property_org_links(sim, prop, active_only=True)
        ) and _row_targets_property_filters(sim, row, prop)
    return False


def property_org_vocabulary(
    sim,
    prop,
    *,
    organization_eid=None,
    active_only=True,
    vocabulary_kind=None,
    current_tick=None,
    include_future=False,
    include_expired=False,
):
    if not isinstance(prop, dict):
        return ()
    rows = []
    seen = set()
    links = property_org_links(sim, prop, active_only=active_only)
    for link in links:
        linked_organization_eid = _safe_int(link.get("organization_eid"), default=0)
        if linked_organization_eid <= 0:
            continue
        if organization_eid is not None and linked_organization_eid != int(organization_eid):
            continue
        for row in organization_vocabulary_entries(
            sim,
            linked_organization_eid,
            active_only=active_only,
            vocabulary_kind=vocabulary_kind,
            current_tick=current_tick,
            include_future=include_future,
            include_expired=include_expired,
            include_ancestors=True,
        ):
            scope = _normalize_vocabulary_scope(row.get("target_scope"), default="organization")
            if scope not in {"organization", "property", "building", "link_kind"}:
                continue
            if not _vocabulary_targets_property(sim, row, prop):
                continue
            key = (int(row.get("organization_eid", 0)), int(row.get("entry_id", 0)))
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    **row,
                    "matched_link_kind": _text(link.get("link_kind")).lower() or None,
                }
            )
    return _sort_vocabulary_rows(rows)


def _membership_link_kinds(sim, membership):
    property_id = _text((membership or {}).get("site_property_id"))
    organization_eid = _safe_int((membership or {}).get("organization_eid"), default=0)
    if not property_id or organization_eid <= 0:
        return ()
    prop = sim.properties.get(property_id)
    if not isinstance(prop, dict):
        return ()
    return tuple(
        sorted(
            {
                _text(link.get("link_kind")).lower()
                for link in property_org_links(sim, prop, active_only=True)
                if _safe_int(link.get("organization_eid"), default=0) == organization_eid
                and _text(link.get("link_kind"))
            }
        )
    )


def _actor_affiliated_org_rows(sim, actor_eid, membership):
    current_org_eid = _safe_int((membership or {}).get("organization_eid"), default=0)
    rows = []
    for row in actor_org_memberships(sim, actor_eid, active_only=True):
        organization_eid = _safe_int(row.get("organization_eid"), default=0)
        if organization_eid <= 0 or organization_eid == current_org_eid:
            continue
        profile = organization_profile(sim, organization_eid)
        rows.append(
            {
                "organization_eid": organization_eid,
                "organization_key": _text(row.get("organization_key")),
                "organization_kind": _normalize_org_kind(row.get("organization_kind"), default="other"),
                "organization_tags": tuple(sorted(getattr(profile, "tags", ()) or ())) if profile else (),
            }
        )
    return tuple(rows)


def _row_targets_membership_filters(sim, row, actor_eid, membership):
    membership_title = _text(membership.get("title")).lower().replace(" ", "_")
    target_titles = set(_normalize_text_tuple(row.get("target_titles")))
    if target_titles and membership_title not in target_titles:
        return False

    occupation = sim.ecs.get(Occupation).get(actor_eid)
    career_key = _text(getattr(occupation, "career", "")).lower().replace(" ", "_")
    target_careers = set(_normalize_text_tuple(row.get("target_careers")))
    if target_careers and career_key not in target_careers:
        return False

    prop = None
    property_id = _text(membership.get("site_property_id"))
    if property_id:
        prop = sim.properties.get(property_id)
    target_services = set(_normalize_text_tuple(row.get("target_service_ids")))
    if target_services and (not isinstance(prop, dict) or not set(property_service_ids(prop)).intersection(target_services)):
        return False
    target_domains = set(_normalize_text_tuple(row.get("target_field_domains")))
    if target_domains:
        actor_domains = set(career_field_domains(getattr(occupation, "career", "")))
        if isinstance(prop, dict):
            actor_domains.update(property_field_domains(prop))
        if not actor_domains.intersection(target_domains):
            return False

    return _row_targets_affiliated_orgs(row, _actor_affiliated_org_rows(sim, actor_eid, membership))


def _vocabulary_targets_membership(sim, row, actor_eid, membership):
    if not isinstance(row, dict) or not isinstance(membership, dict):
        return False
    scope = _normalize_vocabulary_scope(row.get("target_scope"), default="organization")
    if scope == "organization":
        return _row_targets_membership_filters(sim, row, actor_eid, membership)
    if scope == "property":
        return _text(row.get("target_property_id")) == _text(membership.get("site_property_id")) and _row_targets_membership_filters(sim, row, actor_eid, membership)
    if scope == "building":
        return _text(row.get("target_building_id")) == _text(membership.get("site_building_id")) and _row_targets_membership_filters(sim, row, actor_eid, membership)
    if scope == "role":
        return _text(membership.get("role")).lower() in set(row.get("target_roles", ())) and _row_targets_membership_filters(sim, row, actor_eid, membership)
    if scope == "member":
        return int(actor_eid) in set(_normalize_actor_eid_tuple(row.get("target_member_eids"))) and _row_targets_membership_filters(sim, row, actor_eid, membership)
    if scope == "link_kind":
        return _text(row.get("target_link_kind")).lower() in set(_membership_link_kinds(sim, membership)) and _row_targets_membership_filters(sim, row, actor_eid, membership)
    return False


def actor_org_vocabulary(
    sim,
    actor_eid,
    *,
    organization_eid=None,
    active_only=True,
    vocabulary_kind=None,
    current_tick=None,
    include_future=False,
    include_expired=False,
):
    memberships = actor_org_memberships(sim, actor_eid, active_only=active_only)
    rows = []
    seen = set()
    for membership in memberships:
        membership_org_eid = _safe_int(membership.get("organization_eid"), default=0)
        if membership_org_eid <= 0:
            continue
        if organization_eid is not None and membership_org_eid != int(organization_eid):
            continue
        for row in organization_vocabulary_entries(
            sim,
            membership_org_eid,
            active_only=active_only,
            vocabulary_kind=vocabulary_kind,
            current_tick=current_tick,
            include_future=include_future,
            include_expired=include_expired,
            include_ancestors=True,
        ):
            if not _vocabulary_targets_membership(sim, row, actor_eid, membership):
                continue
            key = (int(row.get("organization_eid", 0)), int(row.get("entry_id", 0)))
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    **row,
                    "membership_role": _text(membership.get("role")).lower() or "member",
                    "membership_kind": _text(membership.get("kind")).lower() or "membership",
                    "membership_primary": bool(membership.get("primary", False)),
                    "membership_site_property_id": _text(membership.get("site_property_id")) or None,
                    "membership_site_building_id": _text(membership.get("site_building_id")) or None,
                }
            )
    return _sort_vocabulary_rows(rows)


def _normalize_practice_row(row, organization_eid=None, entry_id=None):
    row = dict(row or {})
    raw_entry_id = _safe_int(row.get("entry_id"), default=entry_id or 0)
    target_scope = _normalize_vocabulary_scope(row.get("target_scope"), default="organization")
    target_property_id = _text(row.get("target_property_id")) or None
    target_building_id = _text(row.get("target_building_id")) or None
    target_link_kind_text = _text(row.get("target_link_kind"))
    target_link_kind = (
        _normalize_link_kind(target_link_kind_text, default="operates")
        if target_link_kind_text
        else None
    )
    target_roles = _normalize_target_roles(row.get("target_roles"))
    target_member_eids = _normalize_actor_eid_tuple(row.get("target_member_eids"))
    target_filters = _normalize_target_filters(row)
    if target_scope == "property" and target_property_id is None:
        target_scope = "organization"
    elif target_scope == "building" and target_building_id is None:
        target_scope = "organization"
    elif target_scope == "link_kind" and target_link_kind is None:
        target_scope = "organization"
    elif target_scope == "role" and not target_roles:
        target_scope = "organization"
    elif target_scope == "member" and not target_member_eids:
        target_scope = "organization"
    raw_expires_tick = row.get("expires_tick")
    expires_tick = (
        _safe_int(raw_expires_tick, default=0)
        if raw_expires_tick not in (None, "")
        else None
    )
    effect_modifiers = row.get("effect_modifiers")
    if not isinstance(effect_modifiers, dict):
        effect_modifiers = {}
    kind = _text(row.get("kind", row.get("practice_kind"))).lower().replace(" ", "_")
    if kind not in ORGANIZATION_PRACTICE_KINDS:
        kind = "operational_pattern"
    return {
        "organization_eid": _safe_int(row.get("organization_eid"), default=organization_eid) or None,
        "entry_id": raw_entry_id or None,
        "entry_key": _text(row.get("entry_key")).lower().replace(" ", "_") or None,
        "kind": kind,
        "domain_key": _text(row.get("domain_key")).lower().replace(" ", "_") or None,
        "label": _text(row.get("label")) or None,
        "summary": _text(row.get("summary")) or None,
        "source_kind": _text(row.get("source_kind")).lower().replace(" ", "_") or None,
        "source_eid": _safe_int(row.get("source_eid"), default=0) or None,
        "discovery_key": _text(row.get("discovery_key")).lower().replace(" ", "_") or None,
        "service_ids": _normalize_text_tuple(row.get("service_ids")),
        "skill_ids": _normalize_text_tuple(row.get("skill_ids")),
        "effect_modifiers": dict(effect_modifiers),
        "target_scope": target_scope,
        "target_property_id": target_property_id,
        "target_building_id": target_building_id,
        "target_link_kind": target_link_kind,
        "target_roles": target_roles,
        "target_member_eids": target_member_eids,
        **target_filters,
        "tags": _normalize_text_tuple(row.get("tags")),
        "priority": int(_normalize_priority(row.get("priority"), default=50)),
        "active": bool(row.get("active", True)),
        "effective_tick": _safe_int(row.get("effective_tick"), default=_safe_int(row.get("created_tick"), default=0)),
        "expires_tick": expires_tick,
        "created_tick": _safe_int(row.get("created_tick"), default=0),
        "last_update_tick": _safe_int(row.get("last_update_tick"), default=_safe_int(row.get("created_tick"), default=0)),
    }


def _sort_practice_rows(rows):
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                0 if bool(row.get("active", True)) else 1,
                -int(row.get("priority", 50)),
                -int(row.get("last_update_tick", 0)),
                -int(row.get("created_tick", 0)),
                -_safe_int(row.get("entry_id"), default=0),
                _text(row.get("organization_name")).lower(),
            ),
        )
    )


def _trim_organization_practices(component):
    if component is None:
        return None
    if len(component.entries) <= int(component.max_entries):
        return component
    keep_ids = {
        int(row.get("entry_id"))
        for row in _sort_practice_rows(component.entries.values())[: int(component.max_entries)]
        if _safe_int(row.get("entry_id"), default=0) > 0
    }
    component.entries = {
        int(stored_entry_id): row
        for stored_entry_id, row in component.entries.items()
        if int(stored_entry_id) in keep_ids
    }
    return component


def _ensure_organization_practices_component(sim, organization_eid, *, create=False):
    if organization_eid is None:
        return None
    component = sim.ecs.get(OrganizationPractices).get(int(organization_eid))
    if component is None and create:
        component = OrganizationPractices()
        sim.ecs.add(int(organization_eid), component)
    if component is None:
        return None
    component.max_entries = max(8, _safe_int(getattr(component, "max_entries", 48), default=48))
    component.next_entry_id = max(1, _safe_int(getattr(component, "next_entry_id", 1), default=1))
    raw_entries = getattr(component, "entries", None)
    if not isinstance(raw_entries, dict):
        raw_entries = {}
    entries = {}
    max_entry_id = 0
    for stored_entry_id, row in raw_entries.items():
        normalized = _normalize_practice_row(
            row,
            organization_eid=organization_eid,
            entry_id=stored_entry_id,
        )
        if normalized.get("kind") not in ORGANIZATION_PRACTICE_KINDS:
            continue
        clean_entry_id = _safe_int(normalized.get("entry_id"), default=0)
        if clean_entry_id <= 0:
            continue
        normalized["entry_id"] = int(clean_entry_id)
        entries[int(clean_entry_id)] = normalized
        max_entry_id = max(max_entry_id, int(clean_entry_id))
    component.entries = entries
    component.next_entry_id = max(int(component.next_entry_id), max_entry_id + 1)
    _trim_organization_practices(component)
    return component


def _find_organization_practice_entry_id(component, *, entry_id=None, entry_key=None):
    if component is None:
        return None
    clean_entry_id = _safe_int(entry_id, default=0)
    if clean_entry_id > 0 and clean_entry_id in component.entries:
        return int(clean_entry_id)
    key = _text(entry_key).lower().replace(" ", "_")
    if not key:
        return None
    for stored_entry_id, row in component.entries.items():
        if _text(row.get("entry_key")).lower().replace(" ", "_") == key:
            return int(stored_entry_id)
    return None


def _practice_row_is_current(
    row,
    *,
    current_tick=0,
    active_only=True,
    include_future=False,
    include_expired=False,
):
    if not isinstance(row, dict):
        return False
    if active_only and not bool(row.get("active", True)):
        return False
    now_tick = _safe_int(current_tick, default=0)
    if not include_future and now_tick < _safe_int(row.get("effective_tick"), default=0):
        return False
    expires_tick = row.get("expires_tick")
    if not include_expired and expires_tick is not None and now_tick > _safe_int(expires_tick, default=now_tick):
        return False
    return True


def record_organization_practice(
    sim,
    *,
    organization_eid=None,
    organization_key=None,
    organization_name="",
    organization_kind="other",
    practice_kind=None,
    entry_id=None,
    entry_key=None,
    domain_key=None,
    label=None,
    summary=None,
    source_kind=None,
    source_eid=None,
    discovery_key=None,
    service_ids=None,
    skill_ids=None,
    effect_modifiers=None,
    target_scope=None,
    target_property_id=None,
    target_building_id=None,
    target_link_kind=None,
    target_roles=None,
    target_member_eids=None,
    target_affiliated_org_eids=None,
    target_affiliated_org_keys=None,
    target_affiliated_org_kinds=None,
    target_affiliated_org_tags=None,
    target_titles=None,
    target_careers=None,
    target_service_ids=None,
    target_field_domains=None,
    tags=None,
    priority=None,
    active=None,
    effective_tick=None,
    expires_tick=None,
    created_tick=None,
):
    if organization_eid is None:
        organization_eid = ensure_organization(
            sim,
            organization_key=organization_key,
            organization_name=organization_name,
            organization_kind=organization_kind,
        )
    profile = organization_profile(sim, organization_eid)
    if profile is None:
        return None
    component = _ensure_organization_practices_component(sim, organization_eid, create=True)
    if component is None:
        return None
    now_tick = _safe_int(getattr(sim, "tick", 0), default=0)
    matched_entry_id = _find_organization_practice_entry_id(component, entry_id=entry_id, entry_key=entry_key)
    existing = (
        dict(component.entries.get(int(matched_entry_id)))
        if matched_entry_id is not None and int(matched_entry_id) in component.entries
        else {}
    )
    if matched_entry_id is None:
        matched_entry_id = _safe_int(entry_id, default=0) or int(component.next_entry_id)
    if created_tick is None:
        created_tick = existing.get("created_tick", now_tick)
    if effective_tick is None:
        effective_tick = existing.get("effective_tick", created_tick)
    if target_scope is None:
        target_scope = existing.get("target_scope", "organization")
    row = dict(existing)
    row.update(
        {
            "organization_eid": int(organization_eid),
            "entry_id": int(matched_entry_id),
            "entry_key": existing.get("entry_key") if entry_key is None else entry_key,
            "kind": existing.get("kind", "operational_pattern") if practice_kind is None else practice_kind,
            "domain_key": existing.get("domain_key") if domain_key is None else domain_key,
            "label": existing.get("label") if label is None else label,
            "summary": existing.get("summary") if summary is None else summary,
            "source_kind": existing.get("source_kind") if source_kind is None else source_kind,
            "source_eid": existing.get("source_eid") if source_eid is None else source_eid,
            "discovery_key": existing.get("discovery_key") if discovery_key is None else discovery_key,
            "service_ids": existing.get("service_ids") if service_ids is None else service_ids,
            "skill_ids": existing.get("skill_ids") if skill_ids is None else skill_ids,
            "effect_modifiers": existing.get("effect_modifiers", {}) if effect_modifiers is None else effect_modifiers,
            "target_scope": target_scope,
            "target_property_id": existing.get("target_property_id") if target_property_id is None else target_property_id,
            "target_building_id": existing.get("target_building_id") if target_building_id is None else target_building_id,
            "target_link_kind": existing.get("target_link_kind") if target_link_kind is None else target_link_kind,
            "target_roles": existing.get("target_roles") if target_roles is None else target_roles,
            "target_member_eids": existing.get("target_member_eids") if target_member_eids is None else target_member_eids,
            "target_affiliated_org_eids": existing.get("target_affiliated_org_eids")
            if target_affiliated_org_eids is None
            else target_affiliated_org_eids,
            "target_affiliated_org_keys": existing.get("target_affiliated_org_keys")
            if target_affiliated_org_keys is None
            else target_affiliated_org_keys,
            "target_affiliated_org_kinds": existing.get("target_affiliated_org_kinds")
            if target_affiliated_org_kinds is None
            else target_affiliated_org_kinds,
            "target_affiliated_org_tags": existing.get("target_affiliated_org_tags")
            if target_affiliated_org_tags is None
            else target_affiliated_org_tags,
            "target_titles": existing.get("target_titles") if target_titles is None else target_titles,
            "target_careers": existing.get("target_careers") if target_careers is None else target_careers,
            "target_service_ids": existing.get("target_service_ids") if target_service_ids is None else target_service_ids,
            "target_field_domains": existing.get("target_field_domains")
            if target_field_domains is None
            else target_field_domains,
            "tags": existing.get("tags") if tags is None else tags,
            "priority": existing.get("priority", 50) if priority is None else priority,
            "active": existing.get("active", True) if active is None else active,
            "effective_tick": effective_tick,
            "expires_tick": existing.get("expires_tick") if expires_tick is None else expires_tick,
            "created_tick": created_tick,
            "last_update_tick": now_tick,
        }
    )
    normalized = _normalize_practice_row(row, organization_eid=organization_eid, entry_id=matched_entry_id)
    if normalized.get("kind") not in ORGANIZATION_PRACTICE_KINDS:
        return None
    normalized_entry_id = _safe_int(normalized.get("entry_id"), default=0)
    if normalized_entry_id <= 0:
        return None
    normalized["entry_id"] = int(normalized_entry_id)
    component.entries[int(normalized_entry_id)] = normalized
    component.next_entry_id = max(int(component.next_entry_id), int(normalized_entry_id) + 1)
    _trim_organization_practices(component)
    return dict(normalized)


def organization_practices(
    sim,
    organization_eid,
    *,
    active_only=True,
    practice_kind=None,
    current_tick=None,
    include_future=False,
    include_expired=False,
    include_ancestors=False,
    max_lineage_depth=8,
):
    requested_profile = organization_profile(sim, organization_eid)
    if requested_profile is None:
        return ()
    current_tick = getattr(sim, "tick", 0) if current_tick is None else current_tick
    requested_kind = _text(practice_kind).lower().replace(" ", "_")
    if requested_kind and requested_kind not in ORGANIZATION_PRACTICE_KINDS:
        return ()
    rows = []
    source_organization_eids = (
        _organization_lineage_eids(sim, organization_eid, include_self=True, max_depth=max_lineage_depth)
        if include_ancestors
        else (int(organization_eid),)
    )
    for lineage_depth, source_organization_eid in enumerate(source_organization_eids):
        profile = organization_profile(sim, source_organization_eid)
        component = _ensure_organization_practices_component(sim, source_organization_eid, create=False)
        if profile is None or component is None:
            continue
        for entry_id, row in component.entries.items():
            row = _normalize_practice_row(row, organization_eid=source_organization_eid, entry_id=entry_id)
            if requested_kind and row.get("kind") != requested_kind:
                continue
            if not _practice_row_is_current(
                row,
                current_tick=current_tick,
                active_only=active_only,
                include_future=include_future,
                include_expired=include_expired,
            ):
                continue
            rows.append(
                {
                    **row,
                    "organization_eid": int(source_organization_eid),
                    "organization_key": _text(profile.key),
                    "organization_name": _text(profile.name),
                    "organization_kind": _normalize_org_kind(profile.kind, default="other"),
                    "requested_organization_eid": int(organization_eid),
                    "requested_organization_key": _text(requested_profile.key),
                    "requested_organization_name": _text(requested_profile.name),
                    "requested_organization_kind": _normalize_org_kind(requested_profile.kind, default="other"),
                    "lineage_depth": int(lineage_depth),
                }
            )
    return _sort_practice_rows(rows)


def _practice_targets_property(sim, row, prop):
    if not isinstance(row, dict) or not isinstance(prop, dict):
        return False
    scope = _normalize_vocabulary_scope(row.get("target_scope"), default="organization")
    if scope == "organization":
        return _row_targets_property_filters(sim, row, prop)
    if scope == "property":
        return _text(row.get("target_property_id")) == _text(prop.get("id")) and _row_targets_property_filters(sim, row, prop)
    metadata = _property_metadata(prop)
    building_ids = {
        _text(metadata.get("building_id")),
        _text(metadata.get("local_building_id")),
    }
    if scope == "building":
        return _text(row.get("target_building_id")) in building_ids and _row_targets_property_filters(sim, row, prop)
    if scope == "link_kind":
        target_link_kind = _text(row.get("target_link_kind")).lower()
        organization_eid = _safe_int(
            row.get("requested_organization_eid"),
            default=_safe_int(row.get("organization_eid"), default=0),
        )
        return any(
            int(link.get("organization_eid", -1)) == organization_eid
            and _text(link.get("link_kind")).lower() == target_link_kind
            for link in property_org_links(sim, prop, active_only=True)
        ) and _row_targets_property_filters(sim, row, prop)
    return False


def property_org_practices(
    sim,
    prop,
    *,
    organization_eid=None,
    active_only=True,
    practice_kind=None,
    current_tick=None,
    include_future=False,
    include_expired=False,
):
    if not isinstance(prop, dict):
        return ()
    rows = []
    seen = set()
    for link in property_org_links(sim, prop, active_only=active_only):
        linked_organization_eid = _safe_int(link.get("organization_eid"), default=0)
        if linked_organization_eid <= 0:
            continue
        if organization_eid is not None and linked_organization_eid != int(organization_eid):
            continue
        for row in organization_practices(
            sim,
            linked_organization_eid,
            active_only=active_only,
            practice_kind=practice_kind,
            current_tick=current_tick,
            include_future=include_future,
            include_expired=include_expired,
            include_ancestors=True,
        ):
            scope = _normalize_vocabulary_scope(row.get("target_scope"), default="organization")
            if scope not in {"organization", "property", "building", "link_kind"}:
                continue
            if not _practice_targets_property(sim, row, prop):
                continue
            key = (int(row.get("organization_eid", 0)), int(row.get("entry_id", 0)))
            if key in seen:
                continue
            seen.add(key)
            rows.append({**row, "matched_link_kind": _text(link.get("link_kind")).lower() or None})
    return _sort_practice_rows(rows)


def _practice_targets_membership(sim, row, actor_eid, membership):
    if not isinstance(row, dict) or not isinstance(membership, dict):
        return False
    scope = _normalize_vocabulary_scope(row.get("target_scope"), default="organization")
    if scope == "organization":
        return _row_targets_membership_filters(sim, row, actor_eid, membership)
    if scope == "property":
        return _text(row.get("target_property_id")) == _text(membership.get("site_property_id")) and _row_targets_membership_filters(sim, row, actor_eid, membership)
    if scope == "building":
        return _text(row.get("target_building_id")) == _text(membership.get("site_building_id")) and _row_targets_membership_filters(sim, row, actor_eid, membership)
    if scope == "role":
        return _text(membership.get("role")).lower() in set(row.get("target_roles", ())) and _row_targets_membership_filters(sim, row, actor_eid, membership)
    if scope == "member":
        return int(actor_eid) in set(_normalize_actor_eid_tuple(row.get("target_member_eids"))) and _row_targets_membership_filters(sim, row, actor_eid, membership)
    if scope == "link_kind":
        return _text(row.get("target_link_kind")).lower() in set(_membership_link_kinds(sim, membership)) and _row_targets_membership_filters(sim, row, actor_eid, membership)
    return False


def actor_org_practices(
    sim,
    actor_eid,
    *,
    organization_eid=None,
    active_only=True,
    practice_kind=None,
    current_tick=None,
    include_future=False,
    include_expired=False,
):
    memberships = actor_org_memberships(sim, actor_eid, active_only=active_only)
    rows = []
    seen = set()
    for membership in memberships:
        membership_org_eid = _safe_int(membership.get("organization_eid"), default=0)
        if membership_org_eid <= 0:
            continue
        if organization_eid is not None and membership_org_eid != int(organization_eid):
            continue
        for row in organization_practices(
            sim,
            membership_org_eid,
            active_only=active_only,
            practice_kind=practice_kind,
            current_tick=current_tick,
            include_future=include_future,
            include_expired=include_expired,
            include_ancestors=True,
        ):
            if not _practice_targets_membership(sim, row, actor_eid, membership):
                continue
            key = (int(row.get("organization_eid", 0)), int(row.get("entry_id", 0)))
            if key in seen:
                continue
            seen.add(key)
            rows.append(
                {
                    **row,
                    "membership_role": _text(membership.get("role")).lower() or "member",
                    "membership_kind": _text(membership.get("kind")).lower() or "membership",
                    "membership_primary": bool(membership.get("primary", False)),
                    "membership_site_property_id": _text(membership.get("site_property_id")) or None,
                    "membership_site_building_id": _text(membership.get("site_building_id")) or None,
                }
            )
    return _sort_practice_rows(rows)


def property_organization_eid(sim, prop, ensure=False):
    if not isinstance(prop, dict):
        return None
    metadata = _property_metadata(prop)
    raw_eid = metadata.get("organization_eid")
    try:
        organization_eid = int(raw_eid)
    except (TypeError, ValueError):
        organization_eid = None

    if organization_eid is not None and organization_profile(sim, organization_eid):
        return organization_eid
    if ensure:
        return ensure_property_organization(sim, prop)
    return None


def _site_link_matches_property(prop, row):
    if not isinstance(prop, dict) or not isinstance(row, dict):
        return False
    row = _normalize_site_link_row(row)
    property_id = _text(prop.get("id"))
    metadata = _property_metadata(prop)
    building_ids = {
        _text(metadata.get("building_id")),
        _text(metadata.get("local_building_id")),
    }
    if row.get("property_id") and row.get("property_id") == property_id:
        return True
    if row.get("building_id") and row.get("building_id") in building_ids:
        return True
    return False


def _upsert_profile_site_link(profile, row):
    row = _normalize_site_link_row(row, organization_eid=row.get("organization_eid"))
    for index, existing in enumerate(profile.site_links):
        existing = _normalize_site_link_row(existing, organization_eid=row.get("organization_eid"))
        if (
            existing.get("property_id") == row.get("property_id")
            and existing.get("building_id") == row.get("building_id")
            and existing.get("link_kind") == row.get("link_kind")
        ):
            profile.site_links[index] = row
            _refresh_profile_site_caches(profile)
            return row
    profile.site_links.append(row)
    _refresh_profile_site_caches(profile)
    return row


def _clear_other_primary_operates(sim, prop, *, keep_org_eid=None):
    for organization_eid, profile in sim.ecs.get(OrganizationProfile).items():
        profile = organization_profile(sim, organization_eid)
        changed = False
        for index, row in enumerate(list(profile.site_links)):
            row = _normalize_site_link_row(row, organization_eid=organization_eid)
            if not _site_link_matches_property(prop, row):
                continue
            if row.get("link_kind") != "operates":
                continue
            if keep_org_eid is not None and int(organization_eid) == int(keep_org_eid):
                continue
            row["active"] = False
            row["primary"] = False
            profile.site_links[index] = row
            changed = True
        if changed:
            _refresh_profile_site_caches(profile)


def link_property_organization(
    sim,
    prop,
    *,
    organization_eid=None,
    organization_key=None,
    organization_name=None,
    organization_kind=None,
    tags=None,
    parent_organization_key=None,
    link_kind="operates",
    primary=None,
    active=True,
):
    if not isinstance(prop, dict):
        return None

    metadata = _property_metadata(prop)
    if organization_eid is None:
        organization_eid = ensure_organization(
            sim,
            organization_key=organization_key or _organization_key_for_property(prop),
            organization_name=organization_name or _organization_name_for_property(prop),
            organization_kind=organization_kind or _organization_kind_for_property(prop),
            tags=tags or _organization_tags_for_property(prop, organization_kind or _organization_kind_for_property(prop)),
            parent_organization_key=parent_organization_key,
        )
    profile = organization_profile(sim, organization_eid)
    if profile is None:
        return None

    link_kind = _normalize_link_kind(link_kind, default="operates")
    if primary is None:
        primary = link_kind == "operates"
    primary = bool(primary) if link_kind == "operates" else False
    if primary and bool(active):
        _clear_other_primary_operates(sim, prop, keep_org_eid=organization_eid)

    property_id = _text(prop.get("id")) or None
    building_id = _text(metadata.get("building_id")) or _text(metadata.get("local_building_id")) or None
    row = _upsert_profile_site_link(
        profile,
        {
            "organization_eid": int(organization_eid),
            "property_id": property_id,
            "building_id": building_id,
            "link_kind": link_kind,
            "primary": primary,
            "active": bool(active),
        },
    )

    if bool(active) and primary and link_kind == "operates":
        metadata["organization_eid"] = int(organization_eid)
        metadata["organization_key"] = _text(profile.key)
        metadata["organization_name"] = _text(profile.name)
        metadata["organization_kind"] = _normalize_org_kind(profile.kind, default="business")
    return dict(row)


def property_org_links(sim, prop, *, active_only=True):
    if not isinstance(prop, dict):
        return ()
    primary_org_eid = property_organization_eid(sim, prop, ensure=False)
    if primary_org_eid is not None:
        profile = organization_profile(sim, primary_org_eid)
        if profile is not None and not any(
            _site_link_matches_property(prop, row)
            and _normalize_site_link_row(row, organization_eid=primary_org_eid).get("link_kind") == "operates"
            and bool(_normalize_site_link_row(row, organization_eid=primary_org_eid).get("primary", False))
            and bool(_normalize_site_link_row(row, organization_eid=primary_org_eid).get("active", True))
            for row in profile.site_links
        ):
            link_property_organization(sim, prop, organization_eid=primary_org_eid, link_kind="operates", primary=True, active=True)

    rows = []
    for organization_eid, profile in sim.ecs.get(OrganizationProfile).items():
        profile = organization_profile(sim, organization_eid)
        for row in profile.site_links:
            row = _normalize_site_link_row(row, organization_eid=organization_eid)
            if active_only and not bool(row.get("active", True)):
                continue
            if not _site_link_matches_property(prop, row):
                continue
            rows.append({
                **row,
                "organization_key": _text(profile.key),
                "organization_name": _text(profile.name),
                "organization_kind": _normalize_org_kind(profile.kind, default="other"),
            })
    rows.sort(
        key=lambda row: (
            0 if row.get("primary") else 1,
            0 if row.get("link_kind") == "operates" else 1,
            _text(row.get("link_kind")),
            _text(row.get("organization_name")).lower(),
            _safe_int(row.get("organization_eid"), default=0),
        )
    )
    return tuple(rows)


def _upsert_profile_relation(profile, row):
    row = _normalize_relation_row(row)
    for index, existing in enumerate(profile.relations):
        existing = _normalize_relation_row(existing)
        if (
            existing.get("target_org_eid") == row.get("target_org_eid")
            and existing.get("kind") == row.get("kind")
        ):
            profile.relations[index] = row
            return row
    profile.relations.append(row)
    return row


def relate_organizations(
    sim,
    *,
    source_org_eid=None,
    source_organization_key=None,
    source_organization_name="",
    source_organization_kind="other",
    target_org_eid=None,
    target_organization_key=None,
    target_organization_name="",
    target_organization_kind="other",
    relation_kind,
    active=True,
    directed=None,
):
    source_org_eid = source_org_eid or ensure_organization(
        sim,
        organization_key=source_organization_key,
        organization_name=source_organization_name,
        organization_kind=source_organization_kind,
    )
    target_org_eid = target_org_eid or ensure_organization(
        sim,
        organization_key=target_organization_key,
        organization_name=target_organization_name,
        organization_kind=target_organization_kind,
    )
    source_profile = organization_profile(sim, source_org_eid)
    target_profile = organization_profile(sim, target_org_eid)
    if source_profile is None or target_profile is None:
        return None

    relation_kind = _normalize_relation_kind(relation_kind, default="service")
    if directed is None:
        directed = relation_kind in DIRECTED_RELATION_KINDS
    if relation_kind in RECIPROCAL_RELATION_KINDS:
        directed = False
    elif relation_kind in DIRECTED_RELATION_KINDS:
        directed = True

    row = _upsert_profile_relation(
        source_profile,
        {
            "target_org_eid": int(target_org_eid),
            "kind": relation_kind,
            "active": bool(active),
            "directed": bool(directed),
        },
    )
    if relation_kind in RECIPROCAL_RELATION_KINDS and int(source_org_eid) != int(target_org_eid):
        _upsert_profile_relation(
            target_profile,
            {
                "target_org_eid": int(source_org_eid),
                "kind": relation_kind,
                "active": bool(active),
                "directed": False,
            },
        )
    return dict(row)


def organization_relations(sim, organization_eid, *, active_only=True, relation_kind=None):
    profile = organization_profile(sim, organization_eid)
    if profile is None:
        return ()
    relation_kind = _normalize_relation_kind(relation_kind, default="") if relation_kind else ""
    rows = []
    for row in profile.relations:
        row = _normalize_relation_row(row)
        if active_only and not bool(row.get("active", True)):
            continue
        if relation_kind and row.get("kind") != relation_kind:
            continue
        target_profile = organization_profile(sim, row.get("target_org_eid"))
        rows.append({
            **row,
            "organization_eid": int(organization_eid),
            "organization_key": _text(profile.key),
            "organization_name": _text(profile.name),
            "organization_kind": _normalize_org_kind(profile.kind, default="other"),
            "target_organization_key": _text(getattr(target_profile, "key", "")),
            "target_organization_name": _text(getattr(target_profile, "name", "")),
            "target_organization_kind": _normalize_org_kind(getattr(target_profile, "kind", ""), default="other") if target_profile else "other",
        })
    rows.sort(
        key=lambda row: (
            _text(row.get("kind")),
            _text(row.get("target_organization_name")).lower(),
            _safe_int(row.get("target_org_eid"), default=0),
        )
    )
    return tuple(rows)


def sync_property_collective_affiliations(sim, prop):
    if not isinstance(prop, dict):
        return ()
    metadata = _property_metadata(prop)
    district = _property_chunk_district(sim, prop)
    if district:
        seed_chunk_organizations(sim, {"district": district})
    if not property_affiliate_organization_specs(prop):
        dynamic_specs = tuple(_dock_union_affiliate_defaults_for_property(prop, district)) + tuple(
            _criminal_family_affiliate_defaults_for_property(prop, district)
        )
        if dynamic_specs:
            _merge_affiliate_specs(metadata, dynamic_specs)
    primary_org_eid = property_organization_eid(sim, prop, ensure=False)
    specs = property_affiliate_organization_specs(prop)
    created = []
    for spec in specs:
        organization_eid = ensure_organization(
            sim,
            organization_key=spec.get("organization_key"),
            organization_name=spec.get("organization_name"),
            organization_kind=spec.get("organization_kind", "community"),
            tags=spec.get("tags"),
            parent_organization_key=spec.get("parent_organization_key"),
        )
        if organization_eid is None:
            continue
        link_property_organization(
            sim,
            prop,
            organization_eid=organization_eid,
            link_kind=spec.get("link_kind", "service_host"),
            active=bool(spec.get("active", True)),
        )
        if primary_org_eid is not None and int(primary_org_eid) != int(organization_eid):
            if spec.get("relation_kind"):
                relate_organizations(
                    sim,
                    source_org_eid=organization_eid,
                    target_org_eid=primary_org_eid,
                    relation_kind=spec.get("relation_kind"),
                    active=bool(spec.get("active", True)),
                )
            if spec.get("reverse_relation_kind"):
                relate_organizations(
                    sim,
                    source_org_eid=primary_org_eid,
                    target_org_eid=organization_eid,
                    relation_kind=spec.get("reverse_relation_kind"),
                    active=bool(spec.get("active", True)),
                )
        created.append(int(organization_eid))
    return tuple(created)


def ensure_property_organization(sim, prop):
    if not property_supports_organization(prop):
        return None

    metadata = _property_metadata(prop)
    parent_organization_key = metadata.get("parent_organization_key")
    parent_organization_name = metadata.get("parent_organization_name")
    parent_organization_kind = metadata.get("parent_organization_kind")
    parent_organization_tags = metadata.get("parent_organization_tags")
    if _text(parent_organization_key):
        if organization_eid_for_key(sim, parent_organization_key) is None:
            ensure_organization(
                sim,
                organization_key=parent_organization_key,
                organization_name=parent_organization_name,
                organization_kind=parent_organization_kind or "civic",
                tags=parent_organization_tags,
            )
    existing = property_organization_eid(sim, prop, ensure=False)
    if existing is not None and organization_profile(sim, existing):
        ensure_organization(
            sim,
            organization_key=getattr(organization_profile(sim, existing), "key", None),
            parent_organization_key=parent_organization_key,
        )
        link_property_organization(sim, prop, organization_eid=existing, link_kind="operates", primary=True, active=True)
        sync_property_collective_affiliations(sim, prop)
        metadata["organization_name"] = organization_name(sim, existing, fallback=_organization_name_for_property(prop))
        metadata["organization_kind"] = _normalize_org_kind(
            getattr(organization_profile(sim, existing), "kind", ""),
            default="business",
        )
        return existing

    organization_eid = ensure_organization(
        sim,
        organization_key=_organization_key_for_property(prop),
        organization_name=_organization_name_for_property(prop),
        organization_kind=_organization_kind_for_property(prop),
        tags=_organization_tags_for_property(prop, _organization_kind_for_property(prop)),
        parent_organization_key=parent_organization_key,
    )
    if organization_eid is None:
        return None
    link_property_organization(sim, prop, organization_eid=organization_eid, link_kind="operates", primary=True, active=True)
    sync_property_collective_affiliations(sim, prop)
    return int(organization_eid)


def workplace_targets_property(prop, workplace):
    if not prop or not isinstance(workplace, dict):
        return False

    property_id = workplace.get("property_id")
    if property_id and property_id == prop.get("id"):
        return True

    building_id = workplace.get("building_id")
    metadata = _property_metadata(prop)
    if building_id and building_id == metadata.get("building_id"):
        return True
    if building_id and building_id == metadata.get("local_building_id"):
        return True
    return False


def occupation_targets_property(prop, occupation):
    if not occupation:
        return False
    return workplace_targets_property(prop, getattr(occupation, "workplace", None))


def _authority_role_from_workplace(workplace, career="", owner_eid=None, actor_eid=None):
    if isinstance(workplace, dict):
        configured = _text(
            workplace.get("authority_role", workplace.get("access_role", ""))
        ).lower()
        if configured in {"owner", "manager", "staff", "member"}:
            return configured

    if owner_eid is not None and actor_eid is not None and int(owner_eid) == int(actor_eid):
        return "owner"

    career_text = _text(career).lower()
    if any(keyword in career_text for keyword in MANAGER_ROLE_KEYWORDS):
        return "manager"
    return "staff"


def _ensure_actor_affiliations(sim, actor_eid):
    component = sim.ecs.get(OrganizationAffiliations).get(actor_eid)
    if component:
        return component
    component = OrganizationAffiliations()
    sim.ecs.add(actor_eid, component)
    return component


def _reconcile_primary_memberships(affiliations):
    if not affiliations or not isinstance(getattr(affiliations, "memberships", None), dict):
        return None
    normalized = {}
    for organization_eid, row in list(affiliations.memberships.items()):
        normalized[int(organization_eid)] = _normalize_membership_row(row, organization_eid=organization_eid)
    affiliations.memberships = normalized

    active_rows = [
        (organization_eid, row)
        for organization_eid, row in affiliations.memberships.items()
        if bool(row.get("active", True))
    ]
    if not active_rows:
        return affiliations

    explicit = [
        (organization_eid, row)
        for organization_eid, row in active_rows
        if bool(row.get("primary", False))
    ]
    if explicit:
        explicit.sort(key=lambda item: (int(item[1].get("authority_rank", 70)), int(item[0])))
        keeper = int(explicit[0][0])
    else:
        preferred = [
            (organization_eid, row)
            for organization_eid, row in active_rows
            if row.get("kind") in PRIMARY_MEMBERSHIP_KINDS
        ]
        ranked = preferred or active_rows
        ranked.sort(
            key=lambda item: (
                0 if item[1].get("kind") == "ownership" else 1 if item[1].get("kind") == "employment" else 2,
                int(item[1].get("authority_rank", 70)),
                int(item[0]),
            )
        )
        keeper = int(ranked[0][0])

    for organization_eid, row in affiliations.memberships.items():
        row["primary"] = bool(row.get("active", True) and int(organization_eid) == keeper)
    return affiliations


def actor_org_memberships(sim, actor_eid, *, active_only=False):
    component = sim.ecs.get(OrganizationAffiliations).get(actor_eid)
    if not component or not isinstance(getattr(component, "memberships", None), dict):
        return ()
    _reconcile_primary_memberships(component)
    rows = []
    for organization_eid, row in component.memberships.items():
        row = _normalize_membership_row(row, organization_eid=organization_eid)
        component.memberships[int(organization_eid)] = row
        if active_only and not bool(row.get("active", True)):
            continue
        profile = organization_profile(sim, organization_eid)
        rows.append({
            **row,
            "organization_key": _text(getattr(profile, "key", "")),
            "organization_name": _text(getattr(profile, "name", "")),
            "organization_kind": _normalize_org_kind(getattr(profile, "kind", ""), default="other") if profile else "other",
        })
    rows.sort(
        key=lambda row: (
            0 if bool(row.get("primary", False)) else 1,
            0 if bool(row.get("active", True)) else 1,
            int(row.get("authority_rank", 70)),
            _text(row.get("organization_name")).lower(),
            _safe_int(row.get("organization_eid"), default=0),
        )
    )
    return tuple(rows)


def primary_actor_membership(sim, actor_eid, *, organization_eid=None):
    memberships = actor_org_memberships(sim, actor_eid, active_only=False)
    if organization_eid is not None:
        for row in memberships:
            if int(row.get("organization_eid", -1)) == int(organization_eid):
                return dict(row)
        return None
    for row in memberships:
        if bool(row.get("active", True)) and bool(row.get("primary", False)):
            return dict(row)
    for row in memberships:
        if bool(row.get("active", True)):
            return dict(row)
    return None


def assign_actor_organization(
    sim,
    actor_eid,
    *,
    organization_eid=None,
    organization_key=None,
    organization_name="",
    organization_kind="other",
    tags=None,
    parent_organization_key=None,
    role="member",
    kind="membership",
    title=None,
    primary=None,
    authority_rank=None,
    supervisor_eid=None,
    site_property_id=None,
    site_building_id=None,
    active=True,
):
    if actor_eid is None:
        return None
    if organization_eid is None:
        organization_eid = ensure_organization(
            sim,
            organization_key=organization_key,
            organization_name=organization_name,
            organization_kind=organization_kind,
            tags=tags,
            parent_organization_key=parent_organization_key,
        )
    profile = organization_profile(sim, organization_eid)
    if profile is None:
        return None

    role = _normalize_membership_role(role, default="member")
    kind = _normalize_membership_kind(kind, default="membership")
    if authority_rank is None:
        authority_rank = _default_authority_rank(role)
    affiliations = _ensure_actor_affiliations(sim, actor_eid)
    if primary is None:
        primary = False
    affiliations.assign(
        organization_eid=int(organization_eid),
        role=role,
        kind=kind,
        site_property_id=_text(site_property_id),
        site_building_id=_text(site_building_id),
        title=_text(title),
        primary=bool(primary),
        authority_rank=int(authority_rank),
        supervisor_eid=supervisor_eid,
        active=bool(active),
    )
    if bool(active):
        profile.member_eids.add(int(actor_eid))
    else:
        profile.member_eids.discard(int(actor_eid))
    _reconcile_primary_memberships(affiliations)
    _refresh_profile_member_cache(sim, organization_eid)
    return int(organization_eid)


def _property_matches_affiliate_spec(prop, spec):
    if not isinstance(prop, dict):
        return False
    service_ids = set(property_service_ids(prop))
    field_domains = set(property_field_domains(prop))
    target_services = set(spec.get("service_ids", ()))
    target_domains = set(spec.get("field_domains", ()))
    if target_services and not service_ids.intersection(target_services):
        return False
    if target_domains and not field_domains.intersection(target_domains):
        return False
    return True


def _career_matches_affiliate_spec(career, spec):
    keywords = set(spec.get("career_keywords", ()))
    if not keywords:
        return True
    career_key = _text(career).lower().replace(" ", "_")
    if not career_key:
        return False
    return any(keyword in career_key for keyword in keywords)


def _workplace_collective_specs(sim, prop):
    specs = list(property_affiliate_organization_specs(prop))
    seen = {
        (spec.get("organization_key"), spec.get("link_kind"))
        for spec in specs
        if spec.get("organization_key")
    }
    for link in property_org_links(sim, prop, active_only=True):
        if link.get("link_kind") == "operates":
            continue
        policy = organization_policy_snapshot(sim, link.get("organization_eid"))
        if not policy or policy.get("family") not in {"labor_union", "trade_guild", "street_gang", "criminal_network"}:
            continue
        key = (_text(link.get("organization_key")) or None, _text(link.get("link_kind")) or None)
        if key in seen or not key[0]:
            continue
        profile = organization_profile(sim, link.get("organization_eid"))
        if profile is None:
            continue
        specs.append(
            _normalize_affiliate_spec(
                {
                    "organization_key": getattr(profile, "key", ""),
                    "organization_name": getattr(profile, "name", ""),
                    "organization_kind": getattr(profile, "kind", "community"),
                    "tags": tuple(getattr(profile, "tags", ()) or ()),
                    "link_kind": link.get("link_kind"),
                    "membership_kind": "membership",
                    "membership_roles": COLLECTIVE_MEMBERSHIP_ROLE_DEFAULTS,
                    "service_ids": property_service_ids(prop),
                    "field_domains": property_field_domains(prop),
                }
            )
        )
        seen.add(key)
    return tuple(specs)


def _site_operator_supervisor_eid(sim, workplace_prop, actor_eid, *, primary_role):
    owner_eid = None
    manager_eid = None
    occupations = sim.ecs.get(Occupation)
    for candidate_eid, occupation in occupations.items():
        if int(candidate_eid) == int(actor_eid):
            continue
        if not occupation_targets_property(workplace_prop, occupation):
            continue
        role = _authority_role_from_workplace(
            getattr(occupation, "workplace", None),
            career=getattr(occupation, "career", ""),
            owner_eid=workplace_prop.get("owner_eid"),
            actor_eid=candidate_eid,
        )
        if role == "owner" and owner_eid is None:
            owner_eid = int(candidate_eid)
        elif role == "manager" and manager_eid is None:
            manager_eid = int(candidate_eid)
    if primary_role == "manager":
        return owner_eid
    if primary_role == "staff":
        return manager_eid or owner_eid
    return None


def _collective_membership_assignment(sim, actor_eid, workplace_prop, spec, *, primary_membership=None, occupation=None):
    primary_role = _text((primary_membership or {}).get("role")).lower() or "member"
    organization_eid = ensure_organization(
        sim,
        organization_key=spec.get("organization_key"),
        organization_name=spec.get("organization_name") or spec.get("organization_key"),
        organization_kind=spec.get("organization_kind", "community"),
        tags=spec.get("tags"),
        parent_organization_key=spec.get("parent_organization_key"),
    )
    policy = organization_policy_snapshot(sim, organization_eid)
    if policy and policy.get("family") in {"street_gang", "criminal_network"} and policy.get("org_role") == "cell":
        family = policy.get("family")
        title = CRIMINAL_CELL_TITLES_BY_FAMILY.get(family, {}).get(
            primary_role,
            CRIMINAL_CELL_TITLES_BY_FAMILY.get(family, {}).get("member", "cell member"),
        )
        authority_rank = CRIMINAL_CELL_RANKS_BY_PRIMARY_ROLE.get(primary_role, CRIMINAL_CELL_RANKS_BY_PRIMARY_ROLE["member"])
        supervisor_eid = _site_operator_supervisor_eid(sim, workplace_prop, actor_eid, primary_role=primary_role)
        return {
            "organization_eid": organization_eid,
            "role": "member",
            "kind": spec.get("membership_kind", "membership"),
            "title": title,
            "authority_rank": authority_rank,
            "supervisor_eid": supervisor_eid,
        }
    return {
        "organization_eid": organization_eid,
        "role": "member",
        "kind": spec.get("membership_kind", "membership"),
        "title": spec.get("membership_title") or _text(getattr(occupation, "career", "")) or "member",
        "authority_rank": None,
        "supervisor_eid": None,
    }


def sync_actor_collective_affiliations(
    sim,
    actor_eid,
    *,
    occupation=None,
    workplace_prop=None,
    primary_membership=None,
):
    if actor_eid is None or not isinstance(workplace_prop, dict):
        return ()
    if occupation is None:
        occupation = sim.ecs.get(Occupation).get(actor_eid)
    if primary_membership is None:
        primary_membership = primary_actor_membership(sim, actor_eid)
    primary_role = _text((primary_membership or {}).get("role")).lower() or "member"

    created = []
    for spec in _workplace_collective_specs(sim, workplace_prop):
        if primary_role == "owner" and not bool(spec.get("allow_owner_membership", False)):
            continue
        membership_roles = set(spec.get("membership_roles", ()))
        if membership_roles and primary_role not in membership_roles:
            continue
        if not _property_matches_affiliate_spec(workplace_prop, spec):
            continue
        if not _career_matches_affiliate_spec(getattr(occupation, "career", ""), spec):
            continue
        assignment = _collective_membership_assignment(
            sim,
            actor_eid,
            workplace_prop,
            spec,
            primary_membership=primary_membership,
            occupation=occupation,
        )
        organization_eid = assign_actor_organization(
            sim,
            actor_eid,
            organization_eid=assignment.get("organization_eid"),
            role=assignment.get("role", "member"),
            kind=assignment.get("kind", spec.get("membership_kind", "membership")),
            title=assignment.get("title"),
            primary=False,
            authority_rank=assignment.get("authority_rank"),
            supervisor_eid=assignment.get("supervisor_eid"),
            site_property_id=workplace_prop.get("id"),
            site_building_id=_property_metadata(workplace_prop).get("building_id"),
            active=bool(spec.get("active", True)),
        )
        if organization_eid is not None:
            created.append(int(organization_eid))
    return tuple(created)


def sync_actor_organization_affiliations(sim, actor_eid, occupation=None):
    if actor_eid is None:
        return None
    if occupation is None:
        occupation = sim.ecs.get(Occupation).get(actor_eid)
    if not occupation:
        return None

    workplace = getattr(occupation, "workplace", None)
    if not isinstance(workplace, dict):
        return None

    property_id = workplace.get("property_id")
    prop = sim.properties.get(property_id) if property_id else None
    organization_eid = None
    if prop:
        organization_eid = ensure_property_organization(sim, prop)
    else:
        raw_eid = workplace.get("organization_eid")
        try:
            organization_eid = int(raw_eid)
        except (TypeError, ValueError):
            organization_eid = None
        if organization_eid is not None and not organization_profile(sim, organization_eid):
            organization_eid = None
        if organization_eid is None and _text(workplace.get("organization_key")):
            organization_eid = ensure_organization(
                sim,
                organization_key=workplace.get("organization_key"),
                organization_name=workplace.get("organization_name"),
                organization_kind=workplace.get("organization_kind"),
                tags=workplace.get("organization_tags"),
                parent_organization_key=workplace.get("parent_organization_key"),
            )

    if organization_eid is None:
        return None

    role = _authority_role_from_workplace(
        workplace,
        career=getattr(occupation, "career", ""),
        owner_eid=prop.get("owner_eid") if isinstance(prop, dict) else None,
        actor_eid=actor_eid,
    )
    memberships_kind = "ownership" if role == "owner" else "employment"
    organization_eid = assign_actor_organization(
        sim,
        actor_eid,
        organization_eid=organization_eid,
        role=role,
        kind=memberships_kind,
        title=_text(getattr(occupation, "career", "")),
        primary=bool(workplace.get("organization_primary", False)),
        authority_rank=workplace.get("authority_rank"),
        supervisor_eid=workplace.get("supervisor_eid"),
        site_property_id=_text(property_id),
        site_building_id=_text(workplace.get("building_id")),
        active=True,
    )
    profile = organization_profile(sim, organization_eid)
    if profile:
        workplace["organization_eid"] = int(organization_eid)
        workplace["organization_key"] = _text(profile.key)
        workplace["organization_kind"] = _normalize_org_kind(profile.kind, default="business")
        workplace["organization_name"] = _text(profile.name)
    primary_membership = primary_actor_membership(sim, actor_eid, organization_eid=organization_eid)
    if prop:
        sync_actor_collective_affiliations(
            sim,
            actor_eid,
            occupation=occupation,
            workplace_prop=prop,
            primary_membership=primary_membership,
        )
    return organization_eid


def org_supervisor_chain(sim, actor_eid, *, organization_eid=None, max_depth=6):
    membership = primary_actor_membership(sim, actor_eid, organization_eid=organization_eid)
    if not membership:
        return ()
    current_supervisor = membership.get("supervisor_eid")
    organization_eid = membership.get("organization_eid")
    chain = []
    seen = {int(actor_eid)}
    depth = 0
    while current_supervisor is not None and depth < int(max_depth):
        supervisor_eid = _safe_int(current_supervisor, default=0)
        if supervisor_eid <= 0 or supervisor_eid in seen:
            break
        seen.add(supervisor_eid)
        supervisor_membership = primary_actor_membership(sim, supervisor_eid, organization_eid=organization_eid)
        if not supervisor_membership:
            break
        chain.append({
            "eid": int(supervisor_eid),
            "organization_eid": int(organization_eid),
            "role": _text(supervisor_membership.get("role")).lower() or "member",
            "title": _text(supervisor_membership.get("title")) or None,
            "authority_rank": int(supervisor_membership.get("authority_rank", 70)),
        })
        current_supervisor = supervisor_membership.get("supervisor_eid")
        depth += 1
    return tuple(chain)


def _membership_targets_property(prop, organization_eid, membership):
    if not isinstance(membership, dict):
        return False
    membership = _normalize_membership_row(membership, organization_eid=organization_eid)
    if int(organization_eid) != int(membership.get("organization_eid", -1)):
        return False
    if not bool(membership.get("active", True)):
        return False

    site_property_id = _text(membership.get("site_property_id"))
    if site_property_id and site_property_id == _text(prop.get("id")):
        return True

    site_building_id = _text(membership.get("site_building_id"))
    metadata = _property_metadata(prop)
    building_ids = {
        _text(metadata.get("building_id")),
        _text(metadata.get("local_building_id")),
    }
    if site_building_id and site_building_id in building_ids:
        return True
    return False


def property_org_members(sim, prop):
    organization_eid = property_organization_eid(sim, prop, ensure=True)
    occupations = sim.ecs.get(Occupation)
    affiliations_map = sim.ecs.get(OrganizationAffiliations)
    candidates = {}

    if organization_eid is not None:
        for actor_eid, affiliations in affiliations_map.items():
            membership = affiliations.memberships.get(int(organization_eid)) if affiliations else None
            if not _membership_targets_property(prop, organization_eid, membership):
                continue
            membership = _normalize_membership_row(membership, organization_eid=organization_eid)
            affiliations.memberships[int(organization_eid)] = membership
            occupation = occupations.get(actor_eid)
            candidates[int(actor_eid)] = {
                "eid": int(actor_eid),
                "role": _text(membership.get("role")).lower() or "member",
                "kind": _text(membership.get("kind")).lower() or "membership",
                "title": _text(membership.get("title")) or None,
                "primary": bool(membership.get("primary", False)),
                "authority_rank": int(membership.get("authority_rank", 70)),
                "supervisor_eid": membership.get("supervisor_eid"),
                "occupation": occupation,
                "organization_eid": int(organization_eid),
                "source": "affiliation",
            }

    for actor_eid, occupation in occupations.items():
        if not occupation_targets_property(prop, occupation):
            continue
        if organization_eid is not None and actor_eid not in candidates:
            sync_actor_organization_affiliations(sim, actor_eid, occupation=occupation)
        if actor_eid in candidates:
            continue
        workplace = getattr(occupation, "workplace", None)
        role = _authority_role_from_workplace(
            workplace,
            career=getattr(occupation, "career", ""),
            owner_eid=prop.get("owner_eid"),
            actor_eid=actor_eid,
        )
        candidates[int(actor_eid)] = {
            "eid": int(actor_eid),
            "role": role,
            "kind": "employment",
            "title": _text(getattr(occupation, "career", "")) or None,
            "primary": False,
            "authority_rank": _default_authority_rank(role),
            "supervisor_eid": _safe_int((workplace or {}).get("supervisor_eid"), default=0) or None,
            "occupation": occupation,
            "organization_eid": int(organization_eid) if organization_eid is not None else None,
            "source": "workplace",
        }

    ordered = sorted(
        candidates.values(),
        key=lambda row: (
            int(row.get("authority_rank", 70)),
            0 if row.get("role") == "owner" else 1 if row.get("role") == "manager" else 2,
            int(row.get("eid", 0)),
        ),
    )
    return tuple(ordered)
