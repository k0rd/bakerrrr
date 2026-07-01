import random

from game.components import (
    OrganizationCrimePlans,
    Occupation,
    OrganizationPracticeProgress,
    OrganizationAffiliations,
    OrganizationPractices,
    OrganizationProfile,
    OrganizationVocabulary,
    OrganizationWatchlists,
    Position,
)
from game.incident_runtime import incident_records
from game.items import (
    ITEM_CATALOG,
    ITEM_QUALITY_TIERS,
    item_condition_profile,
    item_metadata_has_scratch_roll,
    item_metadata_with_creation_seed,
    normalize_item_quality,
)
from game.org_names import generate_organization_name
from game.run_echoes import incident_echo_caution_for_property


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
    "corporation",
    "civic",
    "institution",
    "gang",
    "crew",
    "criminal",
    "community",
    "cult",
    "trade_group",
    "posse",
    "revenge_squad",
    "other",
}
ORGANIZATION_KIND_ALIASES = {
    "organization": "other",
    "corp": "corporation",
    "corporate": "corporation",
    "criminal_cell": "criminal",
    "criminal_org": "criminal",
    "criminal_organization": "criminal",
    "community_group": "community",
    "trade": "trade_group",
    "trade_org": "trade_group",
    "revenge": "revenge_squad",
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
ORGANIZATION_DIPLOMACY_STANCES = {
    "allied",
    "transactional",
    "neutral",
    "competitive",
    "hostile",
    "sacred_conflict",
}
ORGANIZATION_DIPLOMACY_RELATION_STANCES = {
    "ally": "allied",
    "affiliates_with": "allied",
    "oversight": "transactional",
    "service": "transactional",
    "represents": "transactional",
    "bargains_with": "transactional",
    "certifies": "transactional",
    "rival": "competitive",
}
ORGANIZATION_DIPLOMACY_SENSITIVE_TAGS = {
    "assigned_sex",
    "biological_sex",
    "biosex",
    "ethnicity",
    "race",
    "real_world_religion",
    "skin_color",
    "skin_tone",
}
ORGANIZATION_DIPLOMACY_SENSITIVE_PREFIXES = (
    "assigned_sex:",
    "biological_sex:",
    "biosex:",
    "ethnicity:",
    "race:",
    "real_world_religion:",
    "skin_color:",
    "skin_tone:",
)
ORGANIZATION_DIPLOMACY_MAX_PAIRS = 256
ORGANIZATION_DIPLOMACY_MAX_PRESSURES = 256
ORGANIZATION_DIPLOMACY_MAX_HISTORY = 12
ORGANIZATION_DIPLOMACY_DEFAULT_PRESSURE_TICKS = 12 * 600
ORGANIZATION_DIPLOMACY_INTERESTS_BY_KIND = {
    "business": {"property", "customers", "labor", "supply", "service_access", "reputation"},
    "corporation": {"property", "customers", "labor", "supply", "service_access", "reputation", "protection"},
    "civic": {"property", "service_access", "reputation", "relief", "enforcement_pressure", "protection"},
    "institution": {"property", "labor", "service_access", "reputation", "enforcement_pressure"},
    "gang": {"territory", "customers", "supply", "protection", "reputation", "revenge"},
    "crew": {"territory", "supply", "protection", "reputation", "revenge"},
    "criminal": {"territory", "customers", "supply", "protection", "service_access", "revenge"},
    "community": {"property", "labor", "relief", "reputation", "service_access"},
    "cult": {"devotion", "property", "reputation", "service_access", "protection"},
    "trade_group": {"labor", "supply", "service_access", "reputation", "relief"},
    "posse": {"protection", "revenge", "territory", "reputation"},
    "revenge_squad": {"revenge", "territory", "protection", "reputation"},
    "other": {"property", "reputation", "service_access"},
}
ORGANIZATION_DIPLOMACY_INTERESTS_BY_FAMILY = {
    "corporate": {"property", "customers", "labor", "supply", "service_access", "reputation"},
    "civic_security": {"protection", "enforcement_pressure", "reputation"},
    "labor_union": {"labor", "relief", "reputation", "service_access"},
    "trade_guild": {"labor", "supply", "service_access", "reputation"},
    "street_gang": {"territory", "customers", "supply", "protection", "revenge"},
    "criminal_network": {"territory", "customers", "supply", "service_access", "revenge"},
    "municipal": {"service_access", "relief", "enforcement_pressure", "reputation"},
}
ORGANIZATION_DIPLOMACY_PRESSURE_TITLES = {
    "allied": "Local Pact",
    "transactional": "Working Arrangement",
    "neutral": "Quiet Arrangement",
    "competitive": "Org Pressure",
    "hostile": "Org Hostility",
    "sacred_conflict": "Sacred Conflict",
}
ORGANIZATION_DIPLOMACY_PRESSURE_ACTIONS = {
    "allied": "watch the handoff, ask around, or use the calmer edge",
    "transactional": "read the arrangement, ask who benefits, or move on",
    "neutral": "watch the local posture or move on",
    "competitive": "watch the pressure line, ask carefully, or avoid becoming useful to either side",
    "hostile": "keep clear of the line, read uniforms and signs, or ask someone trusted",
    "sacred_conflict": "treat the devotion seriously, watch who reacts, or step away from the point of friction",
}
PROTECTIVE_EFFECT_KEYS = {
    "watchfulness_bonus",
    "watch_priority_bonus",
    "response_followthrough_bonus",
    "report_conversion_bonus",
    "dispatch_bonus",
    "response_readiness_tier",
    "response_score_bonus",
    "confrontation_posture_bonus",
}
WORKPLACE_EFFECT_KEYS = {
    "screening_bias",
    "paperwork_bias",
    "manifest_bias",
    "dispatch_bias",
    "handoff_bias",
    "craft_bias",
    "crew_bias",
    "support_bias",
    "aid_bias",
    "loading_bias",
    "service_softness_bonus",
    "staffing_relief_bonus",
    "service_quality_mult",
    "service_time_mult",
    "service_cooldown_mult",
    "service_cost_mult",
    "trade_stock_mult",
    "trade_buy_price_mult",
    "trade_sell_ratio_mult",
    "quality_delta",
    "item_quality_shift",
    "item_effect_scalar",
    "item_status_duration_scalar",
}
COLLECTIVE_ORG_FAMILIES = {"labor_union", "trade_guild"}
WORKPLACE_CORPORATE_PHASES = (
    "owner_screening",
    "paperwork_surge",
    "manifest_check",
    "dispatch_surge",
    "shift_handoff",
)
WORKPLACE_COLLECTIVE_PHASES = (
    "day_labor_call",
    "clinic_outreach",
    "mutual_aid_table",
    "loading_push",
    "shift_handoff",
)
PROTECTIVE_PRESSURE_RECENT_TICKS = 480
PROTECTIVE_PRESSURE_RESPONSE_TICKS = 240
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
ORGANIZATION_REALIZATION_KINDS = {
    "trade_purchase",
    "item_use",
    "service_outcome",
}
ORGANIZATION_WATCH_ACTIONS = {"watch", "deny_service", "deny_entry"}
ORGANIZATION_CRIME_PLAN_KINDS = {
    "petty_theft",
    "burglary",
    "covert_sale",
    "fence_run",
}
ORGANIZATION_CRIME_PLAN_METHODS = {
    "soft_target_sweep",
    "rear_entry_burglary",
    "covert_sale_handoff",
    "fence_run_handoff",
}
ORGANIZATION_CRIME_PLAN_METHOD_LABELS = {
    "soft_target_sweep": "soft-target sweep",
    "rear_entry_burglary": "rear-entry burglary",
    "covert_sale_handoff": "covert sale handoff",
    "fence_run_handoff": "fence handoff",
}
ORGANIZATION_CRIME_PLAN_STAGES = {
    "forming",
    "rendezvous",
    "executing",
    "disposing",
    "cooldown",
    "cancelled",
    "resolved",
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
    "corporation": "federated",
    "civic": "flat",
    "institution": "federated",
    "gang": "cell",
    "crew": "cell",
    "criminal": "cell",
    "community": "flat",
    "cult": "cell",
    "trade_group": "flat",
    "posse": "cell",
    "revenge_squad": "cell",
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
    "coach_transit": "transit",
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


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


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


def _normalize_realization_kind_tuple(values):
    cleaned = []
    for value in _normalize_text_tuple(values):
        if value in ORGANIZATION_REALIZATION_KINDS and value not in cleaned:
            cleaned.append(value)
    return tuple(cleaned)


def _normalize_item_id_tuple(values):
    return tuple(
        item_id
        for item_id in _normalize_text_tuple(values)
        if item_id in ITEM_CATALOG
    )


def _normalize_item_tag_tuple(values):
    cleaned = []
    for value in _normalize_text_tuple(values):
        if value and value not in cleaned:
            cleaned.append(value)
    return tuple(cleaned)


def _item_tags_for_id(item_id):
    item_def = ITEM_CATALOG.get(_text(item_id))
    if not isinstance(item_def, dict):
        return ()
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
    return tuple(sorted(tags))


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
    _hydrate_linked_branch_records_for_organization(sim, organization_eid)
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
    hydrate_branch=True,
):
    rows = _collect_property_org_vocabulary(
        sim,
        prop,
        organization_eid=organization_eid,
        active_only=active_only,
        vocabulary_kind=vocabulary_kind,
        current_tick=current_tick,
        include_future=include_future,
        include_expired=include_expired,
    )
    if hydrate_branch and isinstance(prop, dict):
        hydrate_property_organization_branches(
            sim,
            prop,
            organization_eid=organization_eid,
            current_tick=current_tick,
            active_only=active_only,
        )
    return rows


def _collect_property_org_vocabulary(
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
        "item_ids": _normalize_item_id_tuple(row.get("item_ids")),
        "item_tags": _normalize_item_tag_tuple(row.get("item_tags")),
        "realization_kinds": _normalize_realization_kind_tuple(row.get("realization_kinds")),
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
    item_ids=None,
    item_tags=None,
    realization_kinds=None,
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
            "item_ids": existing.get("item_ids") if item_ids is None else item_ids,
            "item_tags": existing.get("item_tags") if item_tags is None else item_tags,
            "realization_kinds": existing.get("realization_kinds")
            if realization_kinds is None
            else realization_kinds,
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
    _invalidate_organization_runtime_caches(sim)
    _hydrate_linked_branch_records_for_organization(sim, organization_eid)
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
    hydrate_branch=True,
):
    rows = _collect_property_org_practices(
        sim,
        prop,
        organization_eid=organization_eid,
        active_only=active_only,
        practice_kind=practice_kind,
        current_tick=current_tick,
        include_future=include_future,
        include_expired=include_expired,
    )
    if hydrate_branch and isinstance(prop, dict):
        hydrate_property_organization_branches(
            sim,
            prop,
            organization_eid=organization_eid,
            current_tick=current_tick,
            active_only=active_only,
        )
    return rows


def _collect_property_org_practices(
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


def _normalize_watch_action(value, default="watch"):
    action = _text(value).lower().replace(" ", "_")
    if action not in ORGANIZATION_WATCH_ACTIONS:
        action = _text(default).lower().replace(" ", "_")
    return action if action in ORGANIZATION_WATCH_ACTIONS else "watch"


def _normalize_watchlist_row(row, organization_eid=None, entry_id=None):
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
    return {
        "organization_eid": _safe_int(row.get("organization_eid"), default=organization_eid) or None,
        "entry_id": raw_entry_id or None,
        "entry_key": _text(row.get("entry_key")).lower().replace(" ", "_") or None,
        "subject_eid": _safe_int(
            row.get("subject_eid", row.get("subject_actor_eid")),
            default=0,
        ) or None,
        "action": _normalize_watch_action(row.get("action"), default="watch"),
        "reason": _text(row.get("reason")) or None,
        "source_kind": _text(row.get("source_kind")).lower().replace(" ", "_") or None,
        "source_eid": _safe_int(row.get("source_eid"), default=0) or None,
        "source_incident_id": _safe_int(
            row.get("source_incident_id", row.get("incident_id")),
            default=0,
        ) or None,
        "target_scope": target_scope,
        "target_property_id": target_property_id,
        "target_building_id": target_building_id,
        "target_link_kind": target_link_kind,
        "target_roles": target_roles,
        "target_member_eids": target_member_eids,
        **target_filters,
        "tags": _normalize_text_tuple(row.get("tags")),
        "priority": int(_normalize_priority(row.get("priority"), default=60)),
        "active": bool(row.get("active", True)),
        "effective_tick": _safe_int(
            row.get("effective_tick"),
            default=_safe_int(row.get("created_tick"), default=0),
        ),
        "expires_tick": expires_tick,
        "created_tick": _safe_int(row.get("created_tick"), default=0),
        "last_update_tick": _safe_int(
            row.get("last_update_tick"),
            default=_safe_int(row.get("created_tick"), default=0),
        ),
    }


def _sort_watchlist_rows(rows):
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                0 if bool(row.get("active", True)) else 1,
                0 if _text(row.get("action")).lower() == "deny_entry" else 1 if _text(row.get("action")).lower() == "deny_service" else 2,
                -int(row.get("priority", 60)),
                -int(row.get("last_update_tick", 0)),
                -int(row.get("created_tick", 0)),
                -_safe_int(row.get("entry_id"), default=0),
                _text(row.get("organization_name")).lower(),
            ),
        )
    )


def _trim_organization_watchlists(component):
    if component is None:
        return None
    if len(component.entries) <= int(component.max_entries):
        return component
    keep_ids = {
        int(row.get("entry_id"))
        for row in _sort_watchlist_rows(component.entries.values())[: int(component.max_entries)]
        if _safe_int(row.get("entry_id"), default=0) > 0
    }
    component.entries = {
        int(stored_entry_id): row
        for stored_entry_id, row in component.entries.items()
        if int(stored_entry_id) in keep_ids
    }
    return component


def _ensure_organization_watchlists_component(sim, organization_eid, *, create=False):
    if organization_eid is None:
        return None
    component = sim.ecs.get(OrganizationWatchlists).get(int(organization_eid))
    if component is None and create:
        component = OrganizationWatchlists()
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
        normalized = _normalize_watchlist_row(
            row,
            organization_eid=organization_eid,
            entry_id=stored_entry_id,
        )
        clean_entry_id = _safe_int(normalized.get("entry_id"), default=0)
        if clean_entry_id <= 0 or _safe_int(normalized.get("subject_eid"), default=0) <= 0:
            continue
        normalized["entry_id"] = int(clean_entry_id)
        entries[int(clean_entry_id)] = normalized
        max_entry_id = max(max_entry_id, int(clean_entry_id))
    component.entries = entries
    component.next_entry_id = max(int(component.next_entry_id), max_entry_id + 1)
    _trim_organization_watchlists(component)
    return component


def _find_organization_watchlist_entry_id(component, *, entry_id=None, entry_key=None):
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


def _watchlist_row_is_current(
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


def record_organization_watchlist(
    sim,
    *,
    organization_eid=None,
    organization_key=None,
    organization_name="",
    organization_kind="other",
    entry_id=None,
    entry_key=None,
    subject_eid=None,
    action="watch",
    reason=None,
    source_kind=None,
    source_eid=None,
    source_incident_id=None,
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
    if _safe_int(subject_eid, default=0) <= 0:
        return None
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
    component = _ensure_organization_watchlists_component(sim, organization_eid, create=True)
    if component is None:
        return None
    now_tick = _safe_int(getattr(sim, "tick", 0), default=0)
    matched_entry_id = _find_organization_watchlist_entry_id(
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
        target_scope = existing.get("target_scope", "organization")
    row = dict(existing)
    row.update(
        {
            "organization_eid": int(organization_eid),
            "entry_id": int(matched_entry_id),
            "entry_key": existing.get("entry_key") if entry_key is None else entry_key,
            "subject_eid": existing.get("subject_eid") if subject_eid is None else subject_eid,
            "action": existing.get("action", "watch") if action is None else action,
            "reason": existing.get("reason") if reason is None else reason,
            "source_kind": existing.get("source_kind") if source_kind is None else source_kind,
            "source_eid": existing.get("source_eid") if source_eid is None else source_eid,
            "source_incident_id": existing.get("source_incident_id") if source_incident_id is None else source_incident_id,
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
            "priority": existing.get("priority", 60) if priority is None else priority,
            "active": existing.get("active", True) if active is None else active,
            "effective_tick": effective_tick,
            "expires_tick": existing.get("expires_tick") if expires_tick is None else expires_tick,
            "created_tick": created_tick,
            "last_update_tick": now_tick,
        }
    )
    normalized = _normalize_watchlist_row(
        row,
        organization_eid=organization_eid,
        entry_id=matched_entry_id,
    )
    normalized_entry_id = _safe_int(normalized.get("entry_id"), default=0)
    if normalized_entry_id <= 0 or _safe_int(normalized.get("subject_eid"), default=0) <= 0:
        return None
    normalized["entry_id"] = int(normalized_entry_id)
    component.entries[int(normalized_entry_id)] = normalized
    component.next_entry_id = max(int(component.next_entry_id), int(normalized_entry_id) + 1)
    _trim_organization_watchlists(component)
    _invalidate_organization_runtime_caches(sim)
    _hydrate_linked_branch_records_for_organization(sim, organization_eid)
    return dict(normalized)


def organization_watchlist_rows(
    sim,
    organization_eid,
    *,
    subject_eid=None,
    active_only=True,
    current_tick=None,
    include_future=False,
    include_expired=False,
    include_ancestors=False,
    max_lineage_depth=8,
):
    requested_profile = organization_profile(sim, organization_eid)
    if requested_profile is None:
        return ()
    requested_subject_eid = _safe_int(subject_eid, default=0)
    current_tick = getattr(sim, "tick", 0) if current_tick is None else current_tick
    rows = []
    source_organization_eids = (
        _organization_lineage_eids(
            sim,
            organization_eid,
            include_self=True,
            max_depth=max_lineage_depth,
        )
        if include_ancestors
        else (int(organization_eid),)
    )
    for lineage_depth, source_organization_eid in enumerate(source_organization_eids):
        profile = organization_profile(sim, source_organization_eid)
        component = _ensure_organization_watchlists_component(
            sim,
            source_organization_eid,
            create=False,
        )
        if profile is None or component is None:
            continue
        for entry_id, row in component.entries.items():
            row = _normalize_watchlist_row(
                row,
                organization_eid=source_organization_eid,
                entry_id=entry_id,
            )
            if requested_subject_eid > 0 and _safe_int(row.get("subject_eid"), default=0) != requested_subject_eid:
                continue
            if not _watchlist_row_is_current(
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
    return _sort_watchlist_rows(rows)


def _watchlist_targets_property(sim, row, prop):
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


def _collect_property_org_watch_state(
    sim,
    prop,
    *,
    subject_eid=None,
    organization_eid=None,
    active_only=True,
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
        for row in organization_watchlist_rows(
            sim,
            linked_organization_eid,
            subject_eid=subject_eid,
            active_only=active_only,
            current_tick=current_tick,
            include_future=include_future,
            include_expired=include_expired,
            include_ancestors=True,
        ):
            scope = _normalize_vocabulary_scope(row.get("target_scope"), default="organization")
            if scope not in {"organization", "property", "building", "link_kind"}:
                continue
            if not _watchlist_targets_property(sim, row, prop):
                continue
            key = (int(row.get("organization_eid", 0)), int(row.get("entry_id", 0)))
            if key in seen:
                continue
            seen.add(key)
            rows.append({**row, "matched_link_kind": _text(link.get("link_kind")).lower() or None})
    return _sort_watchlist_rows(rows)


def property_org_watch_state(
    sim,
    prop,
    *,
    subject_eid=None,
    organization_eid=None,
    active_only=True,
    current_tick=None,
    include_future=False,
    include_expired=False,
    hydrate_branch=False,
):
    rows = _collect_property_org_watch_state(
        sim,
        prop,
        subject_eid=subject_eid,
        organization_eid=organization_eid,
        active_only=active_only,
        current_tick=current_tick,
        include_future=include_future,
        include_expired=include_expired,
    )
    if hydrate_branch and isinstance(prop, dict):
        hydrate_property_organization_branches(
            sim,
            prop,
            organization_eid=organization_eid,
            current_tick=current_tick,
            active_only=active_only,
        )
    return rows


def _watchlist_targets_membership(sim, row, actor_eid, membership):
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


def actor_org_watch_state(
    sim,
    actor_eid,
    *,
    organization_eid=None,
    subject_eid=None,
    active_only=True,
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
        for row in organization_watchlist_rows(
            sim,
            membership_org_eid,
            subject_eid=subject_eid,
            active_only=active_only,
            current_tick=current_tick,
            include_future=include_future,
            include_expired=include_expired,
            include_ancestors=True,
        ):
            if not _watchlist_targets_membership(sim, row, actor_eid, membership):
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
    return _sort_watchlist_rows(rows)


def _practice_bundle_notes(rows, *, limit=3):
    notes = []
    seen = set()
    for row in tuple(rows or ()):
        text = _text(row.get("summary") or row.get("label"))
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        notes.append(text)
        if len(notes) >= max(1, int(limit)):
            break
    return tuple(notes)


def _aggregate_practice_effect_modifiers(rows):
    modifiers = {}
    for row in tuple(rows or ()):
        effect_modifiers = row.get("effect_modifiers") if isinstance(row, dict) else None
        if not isinstance(effect_modifiers, dict):
            continue
        for raw_key, raw_value in effect_modifiers.items():
            key = _text(raw_key).lower().replace(" ", "_")
            if not key:
                continue
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            if key.endswith("_mult") or key.endswith("_scalar"):
                current = float(modifiers.get(key, 1.0))
                modifiers[key] = current * max(0.0, value)
            else:
                current = float(modifiers.get(key, 0.0))
                modifiers[key] = current + value
    return modifiers


def _practice_bundle(rows):
    rows = _sort_practice_rows(tuple(rows or ()))
    notes = _practice_bundle_notes(rows)
    return {
        "rows": rows,
        "count": len(rows),
        "entry_keys": tuple(_text(row.get("entry_key")) for row in rows if _text(row.get("entry_key"))),
        "effect_modifiers": _aggregate_practice_effect_modifiers(rows),
        "notes": notes,
        "note_text": "; ".join(notes),
    }


def property_service_practice_bundle(
    sim,
    prop,
    service_id,
    *,
    organization_eid=None,
    active_only=True,
    current_tick=None,
):
    if not isinstance(prop, dict):
        return _practice_bundle(())
    service_key = _text(service_id).lower().replace(" ", "_")
    rows = []
    for row in property_org_practices(
        sim,
        prop,
        organization_eid=organization_eid,
        active_only=active_only,
        current_tick=current_tick,
    ):
        kind = _text(row.get("kind")).lower()
        if kind not in {"service_mutation", "field_discovery"}:
            continue
        service_ids = set(_normalize_text_tuple(row.get("service_ids")))
        if service_ids and service_key not in service_ids:
            continue
        rows.append(row)
    return _practice_bundle(rows)


def property_trade_practice_bundle(
    sim,
    prop,
    *,
    domain_key=None,
    organization_eid=None,
    active_only=True,
    current_tick=None,
):
    if not isinstance(prop, dict):
        return _practice_bundle(())
    requested_domain = _text(domain_key).lower().replace(" ", "_")
    property_domains = set(property_field_domains(prop))
    if requested_domain:
        property_domains.add(requested_domain)
    property_services = set(property_service_ids(prop))
    rows = []
    for row in property_org_practices(
        sim,
        prop,
        organization_eid=organization_eid,
        active_only=active_only,
        current_tick=current_tick,
    ):
        kind = _text(row.get("kind")).lower()
        if kind not in {"service_mutation", "operational_pattern", "field_discovery"}:
            continue
        domain_match = _text(row.get("domain_key")).lower().replace(" ", "_")
        target_domains = set(_normalize_text_tuple(row.get("target_field_domains")))
        service_ids = set(_normalize_text_tuple(row.get("service_ids")))
        if requested_domain and domain_match and requested_domain != domain_match:
            continue
        if target_domains and not property_domains.intersection(target_domains):
            continue
        if service_ids and not property_services.intersection(service_ids):
            continue
        rows.append(row)
    return _practice_bundle(rows)


def local_operational_practice_bundle(
    sim,
    *,
    actor_eid=None,
    prop=None,
    organization_eid=None,
    active_only=True,
    current_tick=None,
):
    rows = []
    seen = set()
    if isinstance(prop, dict):
        for row in property_org_practices(
            sim,
            prop,
            organization_eid=organization_eid,
            active_only=active_only,
            current_tick=current_tick,
        ):
            kind = _text(row.get("kind")).lower()
            if kind not in {"operational_pattern", "skill_method", "field_discovery"}:
                continue
            key = (int(row.get("organization_eid", 0)), int(row.get("entry_id", 0)))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    if actor_eid is not None:
        for row in actor_org_practices(
            sim,
            actor_eid,
            organization_eid=organization_eid,
            active_only=active_only,
            current_tick=current_tick,
        ):
            kind = _text(row.get("kind")).lower()
            if kind not in {"operational_pattern", "skill_method", "field_discovery"}:
                continue
            key = (int(row.get("organization_eid", 0)), int(row.get("entry_id", 0)))
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)
    return _practice_bundle(rows)


def _practice_targets_item_realization(row, item_id, *, item_tags=(), realization_kind="trade_purchase"):
    row = row if isinstance(row, dict) else {}
    requested_item_id = _text(item_id)
    requested_tags = set(_normalize_item_tag_tuple(item_tags))
    row_item_ids = set(_normalize_item_id_tuple(row.get("item_ids")))
    row_item_tags = set(_normalize_item_tag_tuple(row.get("item_tags")))
    row_realization_kinds = set(_normalize_realization_kind_tuple(row.get("realization_kinds")))
    if row_item_ids and requested_item_id not in row_item_ids:
        return False
    if row_item_tags and not requested_tags.intersection(row_item_tags):
        return False
    if row_realization_kinds and _text(realization_kind).lower() not in row_realization_kinds:
        return False
    return True


def property_item_practice_bundle(
    sim,
    prop,
    item_id,
    *,
    current_tick=None,
    realization_kind="trade_purchase",
    organization_eid=None,
    active_only=True,
):
    if not isinstance(prop, dict):
        return _practice_bundle(())
    item_key = _text(item_id)
    if item_key not in ITEM_CATALOG:
        return _practice_bundle(())
    item_tags = _item_tags_for_id(item_key)
    rows = []
    for row in property_org_practices(
        sim,
        prop,
        organization_eid=organization_eid,
        active_only=active_only,
        current_tick=current_tick,
    ):
        kind = _text(row.get("kind")).lower()
        if kind not in {"service_mutation", "operational_pattern", "field_discovery"}:
            continue
        if not _practice_targets_item_realization(
            row,
            item_key,
            item_tags=item_tags,
            realization_kind=realization_kind,
        ):
            continue
        rows.append(row)
    return _practice_bundle(rows)


def _shift_item_quality(quality, shift):
    tiers = list(ITEM_QUALITY_TIERS)
    base_quality = normalize_item_quality(quality, default="standard")
    try:
        index = tiers.index(base_quality)
    except ValueError:
        index = tiers.index("standard")
    shifted = max(0, min(len(tiers) - 1, index + int(shift)))
    return tiers[shifted]


def realize_item_instance_metadata(
    item_id,
    base_metadata,
    *,
    practice_bundle,
    source_property_id,
    source_organization_eid,
    source_organization_key,
    source_practice_key,
    serial_seed,
):
    metadata = dict(base_metadata or {})
    serial_seed_text = _text(serial_seed)
    if not item_metadata_has_scratch_roll(item_id, metadata):
        metadata = item_metadata_with_creation_seed(item_id, metadata, serial_seed_text)
    bundle = practice_bundle if isinstance(practice_bundle, dict) else {}
    modifiers = dict(bundle.get("effect_modifiers", {}))
    if not modifiers and not source_property_id and not source_organization_eid and not source_practice_key:
        return metadata

    if _text(source_property_id):
        metadata["source_property_id"] = _text(source_property_id)
    if source_organization_eid is not None:
        clean_source_org_eid = _safe_int(source_organization_eid, default=0)
        if clean_source_org_eid > 0:
            metadata["source_organization_eid"] = clean_source_org_eid
    if _text(source_organization_key):
        metadata["source_organization_key"] = _text(source_organization_key)
    if _text(source_practice_key):
        metadata["source_practice_key"] = _text(source_practice_key)

    quality_shift = int(round(_safe_float(modifiers.get("item_quality_shift"), default=0.0)))
    if quality_shift:
        metadata["item_quality"] = _shift_item_quality(metadata.get("item_quality"), quality_shift)

    profile = item_condition_profile(item_id, item_catalog=ITEM_CATALOG)
    supports_durability = bool(profile.get("supports_durability"))
    max_durability_bonus = int(round(_safe_float(modifiers.get("item_max_durability_bonus"), default=0.0)))
    durability_bonus = int(round(_safe_float(modifiers.get("item_durability_bonus"), default=0.0)))
    if supports_durability or max_durability_bonus or durability_bonus:
        base_max_durability = _safe_int(
            metadata.get("item_max_durability"),
            default=_safe_int(profile.get("max_durability"), default=0),
        )
        if supports_durability and base_max_durability <= 0:
            base_max_durability = max(1, _safe_int(profile.get("max_durability"), default=1))
        if base_max_durability > 0 or max_durability_bonus:
            max_durability = max(1, base_max_durability + max_durability_bonus)
            metadata["item_max_durability"] = int(max_durability)
            current_durability = _safe_int(
                metadata.get("item_durability"),
                default=max_durability,
            )
            if durability_bonus:
                current_durability += durability_bonus
            else:
                current_durability = max(current_durability, max_durability)
            metadata["item_durability"] = max(0, min(int(max_durability), int(current_durability)))

    effect_scalar = _safe_float(modifiers.get("item_effect_scalar"), default=1.0)
    if abs(effect_scalar - 1.0) > 1e-6:
        metadata["item_effect_scalar"] = max(0.25, min(3.0, effect_scalar))
    positive_effect_scalar = _safe_float(
        modifiers.get("item_positive_effect_scalar"),
        default=effect_scalar,
    )
    if abs(positive_effect_scalar - effect_scalar) > 1e-6 or "item_positive_effect_scalar" in modifiers:
        metadata["item_positive_effect_scalar"] = max(0.25, min(3.0, positive_effect_scalar))
    negative_effect_scalar = _safe_float(
        modifiers.get("item_negative_effect_scalar"),
        default=effect_scalar,
    )
    if abs(negative_effect_scalar - effect_scalar) > 1e-6 or "item_negative_effect_scalar" in modifiers:
        metadata["item_negative_effect_scalar"] = max(0.25, min(3.0, negative_effect_scalar))

    duration_scalar = _safe_float(modifiers.get("item_status_duration_scalar"), default=1.0)
    if abs(duration_scalar - 1.0) > 1e-6:
        metadata["item_status_duration_scalar"] = max(0.25, min(3.0, duration_scalar))
    for need_key in ("energy", "safety", "social"):
        extra_delta = _safe_float(modifiers.get(f"item_extra_{need_key}_delta"), default=0.0)
        if abs(extra_delta) > 1e-6:
            metadata[f"item_extra_{need_key}_delta"] = max(-100.0, min(100.0, extra_delta))
    tool_wear_mult = _safe_float(modifiers.get("tool_wear_mult"), default=1.0)
    if abs(tool_wear_mult - 1.0) > 1e-6:
        metadata["tool_wear_mult"] = max(0.25, min(4.0, tool_wear_mult))
    tamper_severity_mult = _safe_float(modifiers.get("tamper_severity_mult"), default=1.0)
    if abs(tamper_severity_mult - 1.0) > 1e-6:
        metadata["tamper_severity_mult"] = max(0.25, min(4.0, tamper_severity_mult))

    return metadata


def _normalize_practice_progress_scope(value, default="branch"):
    scope = _text(value).lower().replace(" ", "_")
    if scope not in {"branch", "root"}:
        scope = default
    return scope


def _normalize_practice_progress_row(row, organization_eid=None, progress_key=None):
    row = dict(row or {})
    return {
        "organization_eid": _safe_int(row.get("organization_eid"), default=organization_eid) or None,
        "progress_key": _text(row.get("progress_key", progress_key)).lower().replace(" ", "_") or None,
        "branch_property_id": _text(row.get("branch_property_id")) or None,
        "branch_building_id": _text(row.get("branch_building_id")) or None,
        "domain_key": _text(row.get("domain_key")).lower().replace(" ", "_") or None,
        "focus_key": _text(row.get("focus_key")).lower().replace(" ", "_") or None,
        "scope": _normalize_practice_progress_scope(row.get("scope"), default="branch"),
        "activity_points": max(0.0, _safe_float(row.get("activity_points"), default=0.0)),
        "success_points": max(0.0, _safe_float(row.get("success_points"), default=0.0)),
        "failure_points": max(0.0, _safe_float(row.get("failure_points"), default=0.0)),
        "last_signal_tick": _safe_int(row.get("last_signal_tick"), default=0),
        "last_evaluated_tick": _safe_int(row.get("last_evaluated_tick"), default=0),
        "tier": max(0, min(2, _safe_int(row.get("tier"), default=0))),
        "promoted_to_parent": bool(row.get("promoted_to_parent", False)),
    }


def _ensure_organization_practice_progress_component(sim, organization_eid, *, create=False):
    if organization_eid is None:
        return None
    component = sim.ecs.get(OrganizationPracticeProgress).get(int(organization_eid))
    if component is None and create:
        component = OrganizationPracticeProgress()
        sim.ecs.add(int(organization_eid), component)
    if component is None:
        return None
    component.max_entries = max(8, _safe_int(getattr(component, "max_entries", 96), default=96))
    raw_entries = getattr(component, "entries", None)
    if not isinstance(raw_entries, dict):
        raw_entries = {}
    entries = {}
    for raw_key, row in raw_entries.items():
        normalized = _normalize_practice_progress_row(
            row,
            organization_eid=organization_eid,
            progress_key=raw_key,
        )
        progress_key = _text(normalized.get("progress_key"))
        if not progress_key:
            continue
        entries[progress_key] = normalized
    component.entries = entries
    return component


def _trim_organization_practice_progress(component):
    if component is None or len(component.entries) <= int(component.max_entries):
        return component
    kept = sorted(
        component.entries.values(),
        key=lambda row: (
            -_safe_float(row.get("activity_points"), default=0.0),
            -_safe_int(row.get("last_signal_tick"), default=0),
            _text(row.get("progress_key")),
        ),
    )[: int(component.max_entries)]
    component.entries = {
        _text(row.get("progress_key")): row
        for row in kept
        if _text(row.get("progress_key"))
    }
    return component


def record_organization_practice_progress(
    sim,
    *,
    organization_eid=None,
    organization_key=None,
    organization_name="",
    organization_kind="other",
    progress_key,
    branch_property_id=None,
    branch_building_id=None,
    domain_key=None,
    focus_key=None,
    scope="branch",
    activity_delta=0.0,
    success_delta=0.0,
    failure_delta=0.0,
    last_signal_tick=None,
    last_evaluated_tick=None,
    tier=None,
    promoted_to_parent=None,
):
    if organization_eid is None:
        organization_eid = ensure_organization(
            sim,
            organization_key=organization_key,
            organization_name=organization_name,
            organization_kind=organization_kind,
        )
    if organization_eid is None:
        return None
    component = _ensure_organization_practice_progress_component(sim, organization_eid, create=True)
    if component is None:
        return None
    clean_key = _text(progress_key).lower().replace(" ", "_")
    if not clean_key:
        return None
    now_tick = _safe_int(getattr(sim, "tick", 0), default=0)
    existing = dict(component.entries.get(clean_key, {}))
    has_delta = any(
        abs(_safe_float(value, default=0.0)) > 1e-6
        for value in (activity_delta, success_delta, failure_delta)
    )
    row = dict(existing)
    row.update(
        {
            "organization_eid": int(organization_eid),
            "progress_key": clean_key,
            "branch_property_id": existing.get("branch_property_id") if branch_property_id is None else branch_property_id,
            "branch_building_id": existing.get("branch_building_id") if branch_building_id is None else branch_building_id,
            "domain_key": existing.get("domain_key") if domain_key is None else domain_key,
            "focus_key": existing.get("focus_key") if focus_key is None else focus_key,
            "scope": existing.get("scope", "branch") if scope is None else scope,
            "activity_points": _safe_float(existing.get("activity_points"), default=0.0)
            + _safe_float(activity_delta, default=0.0),
            "success_points": _safe_float(existing.get("success_points"), default=0.0)
            + _safe_float(success_delta, default=0.0),
            "failure_points": _safe_float(existing.get("failure_points"), default=0.0)
            + _safe_float(failure_delta, default=0.0),
            "last_signal_tick": (
                existing.get("last_signal_tick", 0)
                if last_signal_tick is None and not has_delta
                else now_tick if last_signal_tick is None
                else last_signal_tick
            ),
            "last_evaluated_tick": existing.get("last_evaluated_tick", 0)
            if last_evaluated_tick is None
            else last_evaluated_tick,
            "tier": existing.get("tier", 0) if tier is None else tier,
            "promoted_to_parent": existing.get("promoted_to_parent", False)
            if promoted_to_parent is None
            else promoted_to_parent,
        }
    )
    normalized = _normalize_practice_progress_row(row, organization_eid=organization_eid, progress_key=clean_key)
    component.entries[clean_key] = normalized
    _trim_organization_practice_progress(component)
    return normalized


def organization_practice_progress_rows(
    sim,
    organization_eid,
    *,
    focus_key=None,
    domain_key=None,
    scope=None,
):
    component = _ensure_organization_practice_progress_component(sim, organization_eid, create=False)
    if component is None:
        return ()
    requested_focus = _text(focus_key).lower().replace(" ", "_")
    requested_domain = _text(domain_key).lower().replace(" ", "_")
    requested_scope = _normalize_practice_progress_scope(scope, default="branch") if scope is not None else None
    rows = []
    for row in component.entries.values():
        if requested_focus and _text(row.get("focus_key")).lower() != requested_focus:
            continue
        if requested_domain and _text(row.get("domain_key")).lower() != requested_domain:
            continue
        if requested_scope and _text(row.get("scope")).lower() != requested_scope:
            continue
        rows.append(dict(row))
    rows.sort(
        key=lambda row: (
            _text(row.get("scope")),
            _text(row.get("domain_key")),
            _text(row.get("focus_key")),
            _text(row.get("branch_property_id")),
            _text(row.get("progress_key")),
        )
    )
    return tuple(rows)


def _normalize_crime_plan_kind(value, default="petty_theft"):
    kind = _text(value).lower().replace(" ", "_")
    if kind not in ORGANIZATION_CRIME_PLAN_KINDS:
        kind = default
    return kind


def crime_plan_method_for_family(family, kind):
    family = _text(family).lower().replace(" ", "_")
    kind = _normalize_crime_plan_kind(kind, default="petty_theft")
    if family == "street_gang" and kind == "burglary":
        return "rear_entry_burglary"
    if family == "street_gang" and kind == "petty_theft":
        return "soft_target_sweep"
    if family == "criminal_network" and kind == "fence_run":
        return "fence_run_handoff"
    if family == "criminal_network" and kind == "covert_sale":
        return "covert_sale_handoff"
    return {
        "burglary": "rear_entry_burglary",
        "covert_sale": "covert_sale_handoff",
        "fence_run": "fence_run_handoff",
    }.get(kind, "soft_target_sweep")


def crime_plan_method_label(method_key, kind=None):
    method_key = _text(method_key).lower().replace(" ", "_")
    if method_key not in ORGANIZATION_CRIME_PLAN_METHODS:
        method_key = crime_plan_method_for_family("", kind)
    return ORGANIZATION_CRIME_PLAN_METHOD_LABELS.get(method_key, method_key.replace("_", " "))


def _normalize_crime_plan_method(value, *, kind=None, default=None):
    method = _text(value).lower().replace(" ", "_")
    if method not in ORGANIZATION_CRIME_PLAN_METHODS:
        method = _text(default).lower().replace(" ", "_")
    if method not in ORGANIZATION_CRIME_PLAN_METHODS:
        method = crime_plan_method_for_family("", kind)
    return method


def _normalize_crime_plan_stage(value, default="forming"):
    stage = _text(value).lower().replace(" ", "_")
    if stage not in ORGANIZATION_CRIME_PLAN_STAGES:
        stage = default
    return stage


def _normalize_crime_plan_row(row, organization_eid=None, entry_id=None):
    row = dict(row or {})
    kind = _normalize_crime_plan_kind(row.get("kind"), default="petty_theft")
    method_key = _normalize_crime_plan_method(row.get("method_key"), kind=kind)
    method_label = _text(row.get("method_label")) or crime_plan_method_label(method_key, kind=kind)
    assigned = row.get("assigned_member_eids")
    if isinstance(assigned, (list, tuple, set)):
        assigned_member_eids = tuple(
            sorted(
                {
                    _safe_int(value, default=0)
                    for value in assigned
                    if _safe_int(value, default=0) > 0
                }
            )
        )
    else:
        assigned_member_eids = ()
    created_tick = _safe_int(row.get("created_tick"), default=0)
    execute_after_tick = _safe_int(row.get("execute_after_tick"), default=created_tick)
    expires_tick = _safe_int(row.get("expires_tick"), default=execute_after_tick)
    last_update_tick = _safe_int(
        row.get("last_update_tick"),
        default=max(created_tick, execute_after_tick),
    )
    return {
        "entry_id": _safe_int(row.get("entry_id"), default=entry_id),
        "organization_eid": _safe_int(row.get("organization_eid"), default=organization_eid) or None,
        "plan_key": _text(row.get("plan_key")).lower().replace(" ", "_") or None,
        "kind": kind,
        "stage": _normalize_crime_plan_stage(row.get("stage"), default="forming"),
        "method_key": method_key,
        "method_label": method_label,
        "leader_eid": _safe_int(row.get("leader_eid"), default=0) or None,
        "assigned_member_eids": assigned_member_eids,
        "target_property_id": _text(row.get("target_property_id")) or None,
        "target_building_id": _text(row.get("target_building_id")) or None,
        "staging_property_id": _text(row.get("staging_property_id")) or None,
        "disposal_property_id": _text(row.get("disposal_property_id")) or None,
        "created_tick": created_tick,
        "execute_after_tick": execute_after_tick,
        "expires_tick": expires_tick,
        "required_member_count": max(1, _safe_int(row.get("required_member_count"), default=1)),
        "source_pressure": max(0.0, min(1.5, _safe_float(row.get("source_pressure"), default=0.0))),
        "observed_by_player_tick": _safe_int(row.get("observed_by_player_tick"), default=0) or None,
        "disruption_score": max(0.0, min(2.0, _safe_float(row.get("disruption_score"), default=0.0))),
        "last_disruption_reason": _text(row.get("last_disruption_reason")).lower().replace(" ", "_") or None,
        "last_update_tick": last_update_tick,
        "resolved_tick": _safe_int(row.get("resolved_tick"), default=0) or None,
        "result": _text(row.get("result")).lower().replace(" ", "_") or None,
        "summary": _text(row.get("summary")) or None,
    }


def _ensure_organization_crime_plan_component(sim, organization_eid, *, create=False):
    if organization_eid is None:
        return None
    component = sim.ecs.get(OrganizationCrimePlans).get(int(organization_eid))
    if component is None and create:
        component = OrganizationCrimePlans()
        sim.ecs.add(int(organization_eid), component)
    if component is None:
        return None
    component.max_entries = max(4, _safe_int(getattr(component, "max_entries", 24), default=24))
    component.next_entry_id = max(1, _safe_int(getattr(component, "next_entry_id", 1), default=1))
    raw_entries = getattr(component, "entries", None)
    if not isinstance(raw_entries, dict):
        raw_entries = {}
    entries = {}
    max_entry_id = 0
    for raw_key, row in raw_entries.items():
        normalized = _normalize_crime_plan_row(
            row,
            organization_eid=organization_eid,
            entry_id=raw_key,
        )
        plan_key = _text(normalized.get("plan_key"))
        if not plan_key:
            continue
        entries[plan_key] = normalized
        max_entry_id = max(max_entry_id, _safe_int(normalized.get("entry_id"), default=0))
    component.entries = entries
    component.next_entry_id = max(component.next_entry_id, max_entry_id + 1)
    return component


def _trim_organization_crime_plans(component):
    if component is None or len(component.entries) <= int(component.max_entries):
        return component
    kept = sorted(
        component.entries.values(),
        key=lambda row: (
            0 if _text(row.get("stage")).lower() not in {"cancelled", "resolved"} else 1,
            -_safe_int(row.get("last_update_tick"), default=0),
            -_safe_int(row.get("created_tick"), default=0),
            _text(row.get("plan_key")),
        ),
    )[: int(component.max_entries)]
    component.entries = {
        _text(row.get("plan_key")): row
        for row in kept
        if _text(row.get("plan_key"))
    }
    return component


def _refresh_crime_plan_briefings(sim, plan_row):
    if not isinstance(plan_row, dict):
        return None
    property_ids = tuple(
        property_id
        for property_id in (
            _text(plan_row.get("staging_property_id")),
            _text(plan_row.get("target_property_id")),
            _text(plan_row.get("disposal_property_id")),
        )
        if property_id
    )
    if property_ids:
        refresh_loaded_organization_branch_briefings(
            sim,
            property_ids=property_ids,
            reason="crime_plan_update",
        )
    for actor_eid in set(plan_row.get("assigned_member_eids", ())) | {
        _safe_int(plan_row.get("leader_eid"), default=0)
    }:
        if actor_eid > 0:
            refresh_actor_branch_briefing(sim, actor_eid, reason="crime_plan_update")
    return None


def record_organization_crime_plan(
    sim,
    *,
    organization_eid=None,
    organization_key=None,
    organization_name="",
    organization_kind="other",
    plan_key,
    kind="petty_theft",
    stage="forming",
    method_key=None,
    method_label=None,
    leader_eid=None,
    assigned_member_eids=(),
    target_property_id=None,
    target_building_id=None,
    staging_property_id=None,
    disposal_property_id=None,
    created_tick=None,
    execute_after_tick=None,
    expires_tick=None,
    required_member_count=1,
    source_pressure=0.0,
    observed_by_player_tick=None,
    disruption_score=None,
    last_disruption_reason=None,
    summary=None,
    resolved_tick=None,
    result=None,
):
    if organization_eid is None:
        organization_eid = ensure_organization(
            sim,
            organization_key=organization_key,
            organization_name=organization_name,
            organization_kind=organization_kind,
        )
    if organization_eid is None:
        return None
    component = _ensure_organization_crime_plan_component(sim, organization_eid, create=True)
    if component is None:
        return None
    clean_key = _text(plan_key).lower().replace(" ", "_")
    if not clean_key:
        return None
    now_tick = _safe_int(getattr(sim, "tick", 0), default=0)
    existing = dict(component.entries.get(clean_key, {}))
    entry_id = _safe_int(existing.get("entry_id"), default=0)
    if entry_id <= 0:
        entry_id = int(component.next_entry_id)
        component.next_entry_id += 1
    row = {
        **existing,
        "entry_id": entry_id,
        "organization_eid": int(organization_eid),
        "plan_key": clean_key,
        "kind": existing.get("kind", kind) if kind is None else kind,
        "stage": existing.get("stage", stage) if stage is None else stage,
        "method_key": existing.get("method_key") if method_key is None else method_key,
        "method_label": existing.get("method_label") if method_label is None else method_label,
        "leader_eid": existing.get("leader_eid") if leader_eid is None else leader_eid,
        "assigned_member_eids": existing.get("assigned_member_eids", assigned_member_eids)
        if assigned_member_eids is None
        else assigned_member_eids,
        "target_property_id": existing.get("target_property_id") if target_property_id is None else target_property_id,
        "target_building_id": existing.get("target_building_id") if target_building_id is None else target_building_id,
        "staging_property_id": existing.get("staging_property_id") if staging_property_id is None else staging_property_id,
        "disposal_property_id": existing.get("disposal_property_id") if disposal_property_id is None else disposal_property_id,
        "created_tick": existing.get("created_tick", now_tick) if created_tick is None else created_tick,
        "execute_after_tick": existing.get("execute_after_tick", now_tick) if execute_after_tick is None else execute_after_tick,
        "expires_tick": existing.get("expires_tick", now_tick + 120) if expires_tick is None else expires_tick,
        "required_member_count": existing.get("required_member_count", required_member_count)
        if required_member_count is None
        else required_member_count,
        "source_pressure": existing.get("source_pressure", source_pressure)
        if source_pressure is None
        else source_pressure,
        "observed_by_player_tick": existing.get("observed_by_player_tick")
        if observed_by_player_tick is None
        else observed_by_player_tick,
        "disruption_score": existing.get("disruption_score", disruption_score)
        if disruption_score is None
        else disruption_score,
        "last_disruption_reason": existing.get("last_disruption_reason")
        if last_disruption_reason is None
        else last_disruption_reason,
        "last_update_tick": now_tick,
        "resolved_tick": existing.get("resolved_tick") if resolved_tick is None else resolved_tick,
        "result": existing.get("result") if result is None else result,
        "summary": existing.get("summary") if summary is None else summary,
    }
    normalized = _normalize_crime_plan_row(row, organization_eid=organization_eid, entry_id=entry_id)
    component.entries[clean_key] = normalized
    _trim_organization_crime_plans(component)
    _refresh_crime_plan_briefings(sim, normalized)
    return dict(normalized)


def advance_organization_crime_plan(
    sim,
    organization_eid,
    plan_key,
    *,
    stage=None,
    method_key=None,
    method_label=None,
    leader_eid=None,
    assigned_member_eids=None,
    execute_after_tick=None,
    expires_tick=None,
    target_property_id=None,
    target_building_id=None,
    staging_property_id=None,
    disposal_property_id=None,
    required_member_count=None,
    source_pressure=None,
    observed_by_player_tick=None,
    disruption_score=None,
    last_disruption_reason=None,
    summary=None,
    resolved_tick=None,
    result=None,
):
    component = _ensure_organization_crime_plan_component(sim, organization_eid, create=False)
    if component is None:
        return None
    clean_key = _text(plan_key).lower().replace(" ", "_")
    existing = component.entries.get(clean_key)
    if not isinstance(existing, dict):
        return None
    return record_organization_crime_plan(
        sim,
        organization_eid=organization_eid,
        plan_key=clean_key,
        kind=existing.get("kind"),
        stage=existing.get("stage") if stage is None else stage,
        method_key=existing.get("method_key") if method_key is None else method_key,
        method_label=existing.get("method_label") if method_label is None else method_label,
        leader_eid=existing.get("leader_eid") if leader_eid is None else leader_eid,
        assigned_member_eids=existing.get("assigned_member_eids") if assigned_member_eids is None else assigned_member_eids,
        target_property_id=existing.get("target_property_id") if target_property_id is None else target_property_id,
        target_building_id=existing.get("target_building_id") if target_building_id is None else target_building_id,
        staging_property_id=existing.get("staging_property_id") if staging_property_id is None else staging_property_id,
        disposal_property_id=existing.get("disposal_property_id") if disposal_property_id is None else disposal_property_id,
        created_tick=existing.get("created_tick"),
        execute_after_tick=existing.get("execute_after_tick") if execute_after_tick is None else execute_after_tick,
        expires_tick=existing.get("expires_tick") if expires_tick is None else expires_tick,
        required_member_count=existing.get("required_member_count") if required_member_count is None else required_member_count,
        source_pressure=existing.get("source_pressure") if source_pressure is None else source_pressure,
        observed_by_player_tick=existing.get("observed_by_player_tick")
        if observed_by_player_tick is None
        else observed_by_player_tick,
        disruption_score=existing.get("disruption_score") if disruption_score is None else disruption_score,
        last_disruption_reason=existing.get("last_disruption_reason")
        if last_disruption_reason is None
        else last_disruption_reason,
        summary=existing.get("summary") if summary is None else summary,
        resolved_tick=existing.get("resolved_tick") if resolved_tick is None else resolved_tick,
        result=existing.get("result") if result is None else result,
    )


def cancel_organization_crime_plan(sim, organization_eid, plan_key, *, result="cancelled", resolved_tick=None, summary=None):
    return advance_organization_crime_plan(
        sim,
        organization_eid,
        plan_key,
        stage="cancelled",
        result=result,
        resolved_tick=_safe_int(getattr(sim, "tick", 0), default=0) if resolved_tick is None else resolved_tick,
        summary=summary,
    )


def organization_crime_plans(
    sim,
    organization_eid,
    *,
    stage=None,
    plan_kind=None,
    current_tick=None,
    include_inactive=False,
):
    component = _ensure_organization_crime_plan_component(sim, organization_eid, create=False)
    if component is None:
        return ()
    requested_stage = _normalize_crime_plan_stage(stage) if stage is not None else None
    requested_kind = _normalize_crime_plan_kind(plan_kind) if plan_kind is not None else None
    tick = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick, default=0)
    rows = []
    for row in component.entries.values():
        normalized = _normalize_crime_plan_row(row, organization_eid=organization_eid, entry_id=row.get("entry_id"))
        component.entries[_text(normalized.get("plan_key"))] = normalized
        if requested_stage and _text(normalized.get("stage")).lower() != requested_stage:
            continue
        if requested_kind and _text(normalized.get("kind")).lower() != requested_kind:
            continue
        if not include_inactive:
            if _text(normalized.get("stage")).lower() in {"cancelled", "resolved"}:
                continue
            expires_tick = _safe_int(normalized.get("expires_tick"), default=0)
            if expires_tick > 0 and tick > expires_tick and _text(normalized.get("stage")).lower() != "cooldown":
                continue
        rows.append(dict(normalized))
    rows.sort(
        key=lambda row: (
            0 if _text(row.get("stage")).lower() in {"executing", "disposing"} else 1,
            -_safe_int(row.get("last_update_tick"), default=0),
            _text(row.get("plan_key")),
        )
    )
    return tuple(rows)


def actor_assigned_crime_plans(sim, actor_eid, *, current_tick=None, include_inactive=False):
    actor_eid = _safe_int(actor_eid, default=0)
    if actor_eid <= 0:
        return ()
    rows = []
    for organization_eid in sim.ecs.get(OrganizationCrimePlans).keys():
        for row in organization_crime_plans(
            sim,
            organization_eid,
            current_tick=current_tick,
            include_inactive=include_inactive,
        ):
            assigned = set(row.get("assigned_member_eids", ()))
            if actor_eid != _safe_int(row.get("leader_eid"), default=0) and actor_eid not in assigned:
                continue
            profile = organization_profile(sim, organization_eid)
            rows.append(
                {
                    **row,
                    "organization_key": _text(getattr(profile, "key", "")),
                    "organization_name": _text(getattr(profile, "name", "")),
                    "organization_kind": _normalize_org_kind(getattr(profile, "kind", ""), default="other") if profile else "other",
                }
            )
    rows.sort(
        key=lambda row: (
            0 if _text(row.get("stage")).lower() == "executing" else 1,
            -_safe_int(row.get("last_update_tick"), default=0),
            _text(row.get("plan_key")),
        )
    )
    return tuple(rows)


def _organization_branch_state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    state = traits.get("organization_branch_hydration")
    if not isinstance(state, dict):
        state = {}
        traits["organization_branch_hydration"] = state
    records = state.get("records")
    if not isinstance(records, dict):
        records = {}
        state["records"] = records
    return state


def _organization_branch_key(organization_eid, *, property_id=None, building_id=None):
    organization_eid = _safe_int(organization_eid, default=0)
    property_id = _text(property_id)
    building_id = _text(building_id)
    if organization_eid <= 0 or (not property_id and not building_id):
        return None
    return f"{organization_eid}:{property_id or '-'}:{building_id or '-'}"


def _branch_effective_response_state(sim, *, property_id="", organization_eid=None, root_organization_eid=None, current_tick=None):
    property_id = _text(property_id)
    if not property_id:
        return {}
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        return {}
    response_state = traits.get("organization_response")
    if not isinstance(response_state, dict):
        return {}
    denials = response_state.get("property_denials")
    if not isinstance(denials, dict):
        return {}
    denial = denials.get(property_id)
    if not isinstance(denial, dict):
        return {}
    tick = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick, default=0)
    if tick > _safe_int(denial.get("service_denial_until_tick"), default=-1):
        return {}
    denial_org_eid = _safe_int(denial.get("organization_eid"), default=0)
    denial_root_eid = _safe_int(denial.get("root_organization_eid"), default=0)
    requested_org_eid = _safe_int(organization_eid, default=0)
    requested_root_eid = _safe_int(root_organization_eid, default=0)
    if requested_org_eid > 0 and denial_org_eid not in {0, requested_org_eid} and denial_root_eid not in {0, requested_root_eid}:
        return {}
    if requested_root_eid > 0 and denial_root_eid not in {0, requested_root_eid} and denial_org_eid not in {0, requested_org_eid}:
        return {}
    return {
        "response_reason": _text(denial.get("reason")) or None,
        "response_source_event": _text(denial.get("source_event")) or None,
        "response_watchfulness": _safe_int(denial.get("watchfulness"), default=0),
        "response_service_denial_until_tick": _safe_int(denial.get("service_denial_until_tick"), default=0) or None,
        "response_target_eid": _safe_int(denial.get("target_eid"), default=0) or None,
        "response_last_trigger_tick": _safe_int(denial.get("last_trigger_tick"), default=0) or None,
        "response_practice_note": _text(denial.get("practice_note")) or None,
    }


def organization_branch_records(
    sim,
    *,
    organization_eid=None,
    property_id=None,
    building_id=None,
    active_only=True,
):
    records = _organization_branch_state(sim).get("records", {})
    property_id = _text(property_id)
    building_id = _text(building_id)
    requested_org_eid = _safe_int(organization_eid, default=0)
    rows = []
    for branch_key, row in records.items():
        if not isinstance(row, dict):
            continue
        row = dict(row)
        if requested_org_eid > 0 and _safe_int(row.get("organization_eid"), default=0) != requested_org_eid:
            continue
        if property_id and _text(row.get("property_id")) != property_id:
            continue
        if building_id and _text(row.get("building_id")) != building_id:
            continue
        if active_only and not bool(row.get("active", True)):
            continue
        row["branch_key"] = _text(row.get("branch_key")) or _text(branch_key)
        rows.append(row)
    rows.sort(
        key=lambda row: (
            0 if bool(row.get("primary_operates", False)) else 1,
            _text(row.get("organization_name")).lower(),
            _safe_int(row.get("organization_eid"), default=0),
        )
    )
    return tuple(rows)


def hydrate_property_organization_branches(
    sim,
    prop,
    *,
    organization_eid=None,
    current_tick=None,
    active_only=True,
):
    if not isinstance(prop, dict):
        return ()
    metadata = _property_metadata(prop)
    property_id = _text(prop.get("id")) or None
    building_id = _text(metadata.get("building_id")) or _text(metadata.get("local_building_id")) or None
    if property_id is None and building_id is None:
        return ()

    requested_org_eid = _safe_int(organization_eid, default=0)
    grouped_links = {}
    for link in property_org_links(sim, prop, active_only=False):
        linked_org_eid = _safe_int(link.get("organization_eid"), default=0)
        if linked_org_eid <= 0:
            continue
        if requested_org_eid > 0 and linked_org_eid != requested_org_eid:
            continue
        grouped_links.setdefault(linked_org_eid, []).append(dict(link))

    state = _organization_branch_state(sim)
    records = state["records"]
    tick = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick, default=0)
    hydrated = []
    for linked_org_eid, link_rows in grouped_links.items():
        profile = organization_profile(sim, linked_org_eid)
        if profile is None:
            continue
        active_links = tuple(link for link in link_rows if bool(link.get("active", True)))
        branch_key = _organization_branch_key(
            linked_org_eid,
            property_id=property_id,
            building_id=building_id,
        )
        if branch_key is None:
            continue
        existing = records.get(branch_key)
        existing = dict(existing) if isinstance(existing, dict) else {}
        policy = organization_policy_snapshot(sim, organization_eid=linked_org_eid)
        vocabulary_rows = _collect_property_org_vocabulary(
            sim,
            prop,
            organization_eid=linked_org_eid,
            active_only=active_only,
            current_tick=tick,
            include_future=False,
            include_expired=False,
        ) if active_links else ()
        watchlist_rows = _collect_property_org_watch_state(
            sim,
            prop,
            subject_eid=None,
            organization_eid=linked_org_eid,
            active_only=active_only,
            current_tick=tick,
            include_future=False,
            include_expired=False,
        ) if active_links else ()
        practice_rows = _collect_property_org_practices(
            sim,
            prop,
            organization_eid=linked_org_eid,
            active_only=active_only,
            current_tick=tick,
            include_future=False,
            include_expired=False,
        ) if active_links else ()
        vocabulary_notes = _practice_bundle_notes(vocabulary_rows)
        practice_notes = _practice_bundle_notes(practice_rows)
        watchlist_latest_update_tick = max(
            (
                _safe_int(row.get("last_update_tick"), default=_safe_int(row.get("created_tick"), default=0))
                for row in watchlist_rows
            ),
            default=0,
        )
        vocabulary_latest_update_tick = max(
            (
                _safe_int(row.get("last_update_tick"), default=_safe_int(row.get("created_tick"), default=0))
                for row in vocabulary_rows
            ),
            default=0,
        )
        practice_latest_update_tick = max(
            (
                _safe_int(row.get("last_update_tick"), default=_safe_int(row.get("created_tick"), default=0))
                for row in practice_rows
            ),
            default=0,
        )
        root_org_eid = _safe_int(policy.get("root_organization_eid"), default=linked_org_eid) or linked_org_eid
        record = {
            "branch_key": branch_key,
            "organization_eid": int(linked_org_eid),
            "organization_key": _text(profile.key),
            "organization_name": _text(profile.name),
            "organization_kind": _normalize_org_kind(profile.kind, default="other"),
            "organization_family": _text(policy.get("family")) or None,
            "organization_structure": _text(policy.get("structure")) or None,
            "organization_role": _text(policy.get("org_role")) or None,
            "root_organization_eid": root_org_eid,
            "root_organization_key": _text(policy.get("root_organization_key")) or _text(profile.key),
            "root_organization_name": _text(policy.get("root_organization_name")) or _text(profile.name),
            "root_organization_kind": _text(policy.get("root_organization_kind")) or _normalize_org_kind(profile.kind, default="other"),
            "property_id": property_id,
            "building_id": building_id,
            "active": bool(active_links),
            "primary_operates": any(
                bool(link.get("primary", False)) and _text(link.get("link_kind")).lower() == "operates"
                for link in link_rows
            ),
            "link_kinds": tuple(
                sorted(
                    {
                        _text(link.get("link_kind")).lower()
                        for link in link_rows
                        if _text(link.get("link_kind"))
                    }
                )
            ),
            "service_ids": property_service_ids(prop),
            "field_domains": property_field_domains(prop),
            "watchlist_entry_ids": tuple(
                row.get("entry_id")
                for row in watchlist_rows
                if _safe_int(row.get("entry_id"), default=0) > 0
            ),
            "watchlist_entry_keys": tuple(
                _text(row.get("entry_key"))
                for row in watchlist_rows
                if _text(row.get("entry_key"))
            ),
            "watchlist_actions": tuple(
                sorted(
                    {
                        _text(row.get("action")).lower()
                        for row in watchlist_rows
                        if _text(row.get("action"))
                    }
                )
            ),
            "watchlist_count": len(watchlist_rows),
            "watchlist_latest_update_tick": int(watchlist_latest_update_tick),
            "vocabulary_entry_ids": tuple(
                row.get("entry_id")
                for row in vocabulary_rows
                if _safe_int(row.get("entry_id"), default=0) > 0
            ),
            "vocabulary_entry_keys": tuple(
                _text(row.get("entry_key"))
                for row in vocabulary_rows
                if _text(row.get("entry_key"))
            ),
            "vocabulary_kinds": tuple(
                sorted(
                    {
                        _text(row.get("kind")).lower()
                        for row in vocabulary_rows
                        if _text(row.get("kind"))
                    }
                )
            ),
            "vocabulary_count": len(vocabulary_rows),
            "vocabulary_note_text": "; ".join(vocabulary_notes),
            "vocabulary_latest_update_tick": int(vocabulary_latest_update_tick),
            "practice_entry_ids": tuple(
                row.get("entry_id")
                for row in practice_rows
                if _safe_int(row.get("entry_id"), default=0) > 0
            ),
            "practice_entry_keys": tuple(
                _text(row.get("entry_key"))
                for row in practice_rows
                if _text(row.get("entry_key"))
            ),
            "practice_kinds": tuple(
                sorted(
                    {
                        _text(row.get("kind")).lower()
                        for row in practice_rows
                        if _text(row.get("kind"))
                    }
                )
            ),
            "practice_count": len(practice_rows),
            "practice_note_text": "; ".join(practice_notes),
            "practice_latest_update_tick": int(practice_latest_update_tick),
            "practice_effect_modifiers": dict(_aggregate_practice_effect_modifiers(practice_rows)),
            "first_hydrated_tick": _safe_int(existing.get("first_hydrated_tick"), default=tick) or tick,
            "last_hydrated_tick": int(tick),
            "source_update_tick": int(
                max(
                    vocabulary_latest_update_tick,
                    practice_latest_update_tick,
                    watchlist_latest_update_tick,
                )
            ),
        }
        record.update(
            _branch_effective_response_state(
                sim,
                property_id=property_id or "",
                organization_eid=linked_org_eid,
                root_organization_eid=root_org_eid,
                current_tick=tick,
            )
        )
        records[branch_key] = record
        hydrated.append(dict(record))
    hydrated = tuple(
        sorted(
            hydrated,
            key=lambda row: (
                0 if bool(row.get("primary_operates", False)) else 1,
                _text(row.get("organization_name")).lower(),
                _safe_int(row.get("organization_eid"), default=0),
            ),
        )
    )
    if hydrated and property_id and not _organization_member_read_active(sim):
        refresh_loaded_organization_branch_briefings(
            sim,
            property_ids=(property_id,),
            reason="branch_hydrate",
        )
    return hydrated


def property_org_branch_hydration(
    sim,
    prop,
    *,
    organization_eid=None,
    current_tick=None,
    active_only=True,
    hydrate=True,
):
    if not isinstance(prop, dict):
        return ()
    if hydrate:
        return hydrate_property_organization_branches(
            sim,
            prop,
            organization_eid=organization_eid,
            current_tick=current_tick,
            active_only=active_only,
        )
    metadata = _property_metadata(prop)
    property_id = _text(prop.get("id")) or None
    building_id = _text(metadata.get("building_id")) or _text(metadata.get("local_building_id")) or None
    return organization_branch_records(
        sim,
        organization_eid=organization_eid,
        property_id=property_id,
        building_id=building_id,
        active_only=active_only,
    )


def _hydrate_linked_branch_records_for_organization(sim, organization_eid):
    target_org_eid = _safe_int(organization_eid, default=0)
    if target_org_eid <= 0:
        return ()
    target_org_eids = [target_org_eid]
    target_org_eids.extend(
        int(row.get("organization_eid", 0))
        for row in organization_child_organizations(sim, target_org_eid, recursive=True)
        if _safe_int(row.get("organization_eid"), default=0) > 0
    )
    props_by_id = {}
    for current_org_eid in target_org_eids:
        profile = organization_profile(sim, current_org_eid)
        if profile is None:
            continue
        for property_id in tuple(getattr(profile, "site_property_ids", ()) or ()):
            prop = sim.properties.get(property_id)
            if isinstance(prop, dict):
                props_by_id[_text(property_id)] = prop
    hydrated = []
    for prop in props_by_id.values():
        hydrated.extend(
            hydrate_property_organization_branches(
                sim,
                prop,
                current_tick=getattr(sim, "tick", 0),
                active_only=True,
            )
        )
    if props_by_id:
        refresh_loaded_organization_branch_briefings(
            sim,
            property_ids=tuple(props_by_id.keys()),
            reason="organization_refresh",
        )
    return tuple(hydrated)


def _organization_actor_briefing_state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    state = traits.get("organization_actor_briefings")
    if not isinstance(state, dict):
        state = {}
        traits["organization_actor_briefings"] = state
    packets = state.get("packets")
    if not isinstance(packets, dict):
        packets = {}
        state["packets"] = packets
    query_cache = state.get("query_cache")
    if not isinstance(query_cache, dict):
        query_cache = {}
        state["query_cache"] = query_cache
    return state


def _organization_member_read_active(sim):
    state = _organization_actor_briefing_state(sim)
    return _safe_int(state.get("member_read_depth"), default=0) > 0


def _organization_runtime_cache_state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    state = traits.get("organization_runtime_cache")
    if not isinstance(state, dict):
        state = {}
        traits["organization_runtime_cache"] = state
    sim_tick = _safe_int(getattr(sim, "tick", 0), default=0)
    if _safe_int(state.get("sim_tick"), default=-1) != sim_tick:
        state.clear()
        state["sim_tick"] = sim_tick
    for key in ("workplace_posture", "protective_pressure", "property_links", "access_posture"):
        cache = state.get(key)
        if not isinstance(cache, dict):
            cache = {}
            state[key] = cache
    return state


def _organization_runtime_property_cache_key(prop, *, actor_eid=None, current_tick=None):
    if not isinstance(prop, dict):
        return None
    metadata = _property_metadata(prop)
    return (
        _safe_int(current_tick, default=0),
        _text(prop.get("id")),
        _text(metadata.get("building_id")) or _text(metadata.get("local_building_id")),
        _safe_int(actor_eid, default=0),
    )


def _invalidate_organization_runtime_caches(sim):
    state = _organization_runtime_cache_state(sim)
    for key in ("workplace_posture", "protective_pressure", "property_links", "access_posture"):
        cache = state.get(key)
        if isinstance(cache, dict):
            cache.clear()


def _actor_branch_packet_key(actor_eid, organization_eid, *, property_id=None, building_id=None):
    actor_eid = _safe_int(actor_eid, default=0)
    organization_eid = _safe_int(organization_eid, default=0)
    property_id = _text(property_id)
    building_id = _text(building_id)
    if actor_eid <= 0 or organization_eid <= 0 or (not property_id and not building_id):
        return None
    return f"{actor_eid}:{organization_eid}:{property_id or '-'}:{building_id or '-'}"


def _briefing_note_texts(*groups, limit=6):
    notes = []
    seen = set()
    for group in groups:
        values = group if isinstance(group, (list, tuple)) else (group,)
        for value in values:
            text = _text(value)
            key = text.lower()
            if not text or key in seen:
                continue
            seen.add(key)
            notes.append(text)
            if len(notes) >= max(1, int(limit)):
                return tuple(notes)
    return tuple(notes)


def _relation_access_effect(kind):
    relation_kind = _text(kind).lower()
    if relation_kind == "oversight":
        return {
            "reason_tag": "oversight_access",
            "standing_floor": 0.86,
            "public_entry_grace": True,
            "service_grace": False,
            "guard_grace": True,
            "service_softness_bonus": 0.0,
            "staffing_relief_bonus": 0.0,
            "note": "Oversight access applies here.",
        }
    if relation_kind == "service":
        return {
            "reason_tag": "service_relation",
            "standing_floor": 0.0,
            "public_entry_grace": True,
            "service_grace": True,
            "guard_grace": True,
            "service_softness_bonus": 0.06,
            "staffing_relief_bonus": 0.0,
            "note": "Service affiliation softens the front here.",
        }
    if relation_kind == "represents":
        return {
            "reason_tag": "represented_access",
            "standing_floor": 0.0,
            "public_entry_grace": True,
            "service_grace": True,
            "guard_grace": True,
            "service_softness_bonus": 0.08,
            "staffing_relief_bonus": 0.05,
            "note": "Representation buys some front-door grace here.",
        }
    if relation_kind == "bargains_with":
        return {
            "reason_tag": "bargained_service",
            "standing_floor": 0.0,
            "public_entry_grace": False,
            "service_grace": True,
            "guard_grace": False,
            "service_softness_bonus": 0.1,
            "staffing_relief_bonus": 0.14,
            "note": "A bargaining line softens service friction here.",
        }
    return {
        "reason_tag": "",
        "standing_floor": 0.0,
        "public_entry_grace": False,
        "service_grace": False,
        "guard_grace": False,
        "service_softness_bonus": 0.0,
        "staffing_relief_bonus": 0.0,
        "note": "",
    }


def _organization_relation_access_rows(
    sim,
    actor_eid,
    prop,
    *,
    membership_organization_eid=None,
):
    if actor_eid is None or not isinstance(prop, dict):
        return ()
    property_target_eids = set()
    for link in property_org_links(sim, prop, active_only=True):
        linked_org_eid = _safe_int(link.get("organization_eid"), default=0)
        if linked_org_eid <= 0:
            continue
        property_target_eids.update(
            _organization_lineage_eids(
                sim,
                linked_org_eid,
                include_self=True,
                max_depth=8,
            )
        )
    if not property_target_eids:
        return ()
    requested_membership_org_eid = _safe_int(membership_organization_eid, default=0)
    rows = []
    seen = set()
    for membership in actor_org_memberships(sim, actor_eid, active_only=True):
        membership_org_eid = _safe_int(membership.get("organization_eid"), default=0)
        if membership_org_eid <= 0:
            continue
        if requested_membership_org_eid > 0 and membership_org_eid != requested_membership_org_eid:
            continue
        membership_lineage = _organization_lineage_eids(
            sim,
            membership_org_eid,
            include_self=True,
            max_depth=8,
        )
        for source_org_eid in membership_lineage:
            for relation in organization_relations(sim, source_org_eid, active_only=True):
                relation_kind = _text(relation.get("kind")).lower()
                if relation_kind not in {"oversight", "service", "represents", "bargains_with"}:
                    continue
                target_org_eid = _safe_int(relation.get("target_org_eid"), default=0)
                if target_org_eid <= 0 or target_org_eid not in property_target_eids:
                    continue
                effect = _relation_access_effect(relation_kind)
                key = (membership_org_eid, source_org_eid, target_org_eid, relation_kind)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        **relation,
                        **effect,
                        "actor_eid": int(actor_eid),
                        "membership_organization_eid": int(membership_org_eid),
                        "membership_role": _text(membership.get("role")).lower() or "member",
                        "membership_title": _text(membership.get("title")) or None,
                        "source_organization_eid": int(source_org_eid),
                    }
                )
        for source_org_eid in property_target_eids:
            for relation in organization_relations(sim, source_org_eid, active_only=True):
                relation_kind = _text(relation.get("kind")).lower()
                if relation_kind != "bargains_with":
                    continue
                target_org_eid = _safe_int(relation.get("target_org_eid"), default=0)
                if target_org_eid <= 0 or target_org_eid not in membership_lineage:
                    continue
                effect = _relation_access_effect(relation_kind)
                key = (membership_org_eid, source_org_eid, target_org_eid, relation_kind)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(
                    {
                        **relation,
                        **effect,
                        "actor_eid": int(actor_eid),
                        "membership_organization_eid": int(membership_org_eid),
                        "membership_role": _text(membership.get("role")).lower() or "member",
                        "membership_title": _text(membership.get("title")) or None,
                        "source_organization_eid": int(source_org_eid),
                    }
                )
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                0
                if _text(row.get("kind")).lower() == "oversight"
                else 1
                if _text(row.get("kind")).lower() == "service"
                else 2
                if _text(row.get("kind")).lower() == "represents"
                else 3,
                _text(row.get("organization_name")).lower(),
                _safe_int(row.get("target_org_eid"), default=0),
            ),
        )
    )


def _briefing_branch_packets(sim, actor_eid, prop=None):
    state = _organization_actor_briefing_state(sim)
    property_id = _text((prop or {}).get("id")) if isinstance(prop, dict) else ""
    packets = []
    for row in state.get("packets", {}).values():
        if not isinstance(row, dict):
            continue
        if _safe_int(row.get("actor_eid"), default=0) != _safe_int(actor_eid, default=0):
            continue
        if property_id and _text(row.get("property_id")) != property_id:
            continue
        packets.append(dict(row))
    packets.sort(
        key=lambda row: (
            int(row.get("authority_rank", 70)),
            _text(row.get("organization_name")).lower(),
            _safe_int(row.get("organization_eid"), default=0),
        )
    )
    return tuple(packets)


def _briefing_query_cache_key(actor_eid, prop=None):
    actor_eid = _safe_int(actor_eid, default=0)
    property_id = _text((prop or {}).get("id")) if isinstance(prop, dict) else ""
    return f"{actor_eid}:{property_id or '-'}"


def _briefing_packets_token(packets):
    return tuple(
        (
            _text(packet.get("packet_key")),
            packet.get("packet_token"),
            _safe_int(packet.get("source_update_tick"), default=0),
        )
        for packet in tuple(packets or ())
        if isinstance(packet, dict)
    )


def refresh_actor_branch_briefing(sim, actor_eid, prop=None, reason=""):
    actor_eid = _safe_int(actor_eid, default=0)
    if actor_eid <= 0:
        return ()
    memberships = actor_org_memberships(sim, actor_eid, active_only=True)
    props = []
    if isinstance(prop, dict):
        props.append(prop)
    else:
        seen_property_ids = set()
        for membership in memberships:
            property_id = _text(membership.get("site_property_id"))
            if not property_id or property_id in seen_property_ids:
                continue
            candidate = sim.properties.get(property_id)
            if not isinstance(candidate, dict):
                continue
            seen_property_ids.add(property_id)
            props.append(candidate)
    state = _organization_actor_briefing_state(sim)
    state.get("query_cache", {}).clear()
    packets = state["packets"]
    if not props:
        stale_keys = [
            packet_key
            for packet_key, row in packets.items()
            if _safe_int((row or {}).get("actor_eid"), default=0) == actor_eid
        ]
        for packet_key in stale_keys:
            packets.pop(packet_key, None)
        return ()

    if not memberships:
        stale_keys = [
            packet_key
            for packet_key, row in packets.items()
            if _safe_int((row or {}).get("actor_eid"), default=0) == actor_eid
        ]
        for packet_key in stale_keys:
            packets.pop(packet_key, None)
        return ()

    built_keys = set()
    built_packets = []
    for current_prop in props:
        property_id = _text(current_prop.get("id"))
        building_id = _text(_property_metadata(current_prop).get("building_id")) or _text(_property_metadata(current_prop).get("local_building_id"))
        workplace_posture = local_workplace_org_posture(
            sim,
            current_prop,
            actor_eid=actor_eid,
            current_tick=getattr(sim, "tick", 0),
        )
        workplace_lineage_eids = set()
        for linked_org_eid in tuple(workplace_posture.get("corporate_org_eids", ())) + tuple(workplace_posture.get("collective_org_eids", ())):
            workplace_lineage_eids.update(
                _organization_lineage_eids(
                    sim,
                    linked_org_eid,
                    include_self=True,
                    max_depth=8,
                )
            )
        for membership in memberships:
            membership_org_eid = _safe_int(membership.get("organization_eid"), default=0)
            if membership_org_eid <= 0 or not _membership_targets_property(current_prop, membership_org_eid, membership):
                continue
            branch_rows = property_org_branch_hydration(
                sim,
                current_prop,
                organization_eid=membership_org_eid,
                current_tick=getattr(sim, "tick", 0),
                active_only=True,
                hydrate=False,
            )
            if not branch_rows:
                branch_rows = property_org_branch_hydration(
                    sim,
                    current_prop,
                    organization_eid=membership_org_eid,
                    current_tick=getattr(sim, "tick", 0),
                    active_only=True,
                    hydrate=True,
                )
            branch_row = next(
                (
                    row
                    for row in branch_rows
                    if _safe_int(row.get("organization_eid"), default=0) == membership_org_eid
                ),
                None,
            )
            if not isinstance(branch_row, dict):
                continue
            directive_rows = [
                row
                for row in actor_org_vocabulary(
                    sim,
                    actor_eid,
                    organization_eid=membership_org_eid,
                    active_only=True,
                    current_tick=getattr(sim, "tick", 0),
                )
                if _text(row.get("kind")).lower() in {"directive", "site_brief", "subject_notice"}
            ]
            watch_rows = list(
                actor_org_watch_state(
                    sim,
                    actor_eid,
                    organization_eid=membership_org_eid,
                    active_only=True,
                    current_tick=getattr(sim, "tick", 0),
                )
            )
            practice_bundle = local_operational_practice_bundle(
                sim,
                actor_eid=actor_eid,
                prop=current_prop,
                organization_eid=membership_org_eid,
                active_only=True,
                current_tick=getattr(sim, "tick", 0),
            )
            crime_plan_rows = [
                row
                for row in actor_assigned_crime_plans(
                    sim,
                    actor_eid,
                    current_tick=getattr(sim, "tick", 0),
                )
                if _safe_int(row.get("organization_eid"), default=0) == membership_org_eid
                and property_id in {
                    _text(row.get("target_property_id")),
                    _text(row.get("staging_property_id")),
                    _text(row.get("disposal_property_id")),
                }
            ]
            relation_rows = list(
                _organization_relation_access_rows(
                    sim,
                    actor_eid,
                    current_prop,
                    membership_organization_eid=membership_org_eid,
                )
            )
            response_watchfulness = _safe_int(branch_row.get("response_watchfulness"), default=0)
            response_reason = _text(branch_row.get("response_reason")).replace("_", " ")
            response_note = _text(branch_row.get("response_practice_note"))
            if not response_note and response_watchfulness > 0:
                response_note = f"Branch is on alert after {response_reason or 'recent trouble'}."
            workplace_notes = ()
            if membership_org_eid in workplace_lineage_eids:
                workplace_notes = tuple(workplace_posture.get("note_texts", ()) or ())
            note_texts = _briefing_note_texts(
                _practice_bundle_notes(directive_rows, limit=3),
                tuple(_text(row.get("reason")) for row in watch_rows),
                practice_bundle.get("note_text"),
                response_note,
                workplace_notes,
                tuple(_text(row.get("note")) for row in relation_rows),
                tuple(
                    f"Active crew plan: {_text(row.get('kind')).replace('_', ' ')} ({_text(row.get('stage')).replace('_', ' ')})"
                    for row in crime_plan_rows
                ),
            )
            directive_entry_keys = tuple(
                _text(row.get("entry_key"))
                for row in directive_rows
                if _text(row.get("entry_key"))
            )
            watch_entry_keys = tuple(
                _text(row.get("entry_key"))
                for row in watch_rows
                if _text(row.get("entry_key"))
            )
            relation_token = tuple(
                f"{_text(row.get('kind'))}:{_safe_int(row.get('source_organization_eid'), default=0)}:{_safe_int(row.get('target_org_eid'), default=0)}"
                for row in relation_rows
            )
            crime_plan_token = tuple(
                f"{_text(row.get('plan_key'))}:{_text(row.get('stage'))}:{_text(row.get('kind'))}"
                for row in crime_plan_rows
            )
            packet_token = (
                int(branch_row.get("source_update_tick", 0)),
                int(branch_row.get("response_last_trigger_tick") or 0),
                tuple(sorted(directive_entry_keys)),
                tuple(sorted(watch_entry_keys)),
                relation_token,
                crime_plan_token,
                _text(membership.get("role")).lower(),
                _text(membership.get("title")).lower(),
                int(membership.get("authority_rank", 70)),
            )
            packet_key = _actor_branch_packet_key(
                actor_eid,
                membership_org_eid,
                property_id=property_id,
                building_id=building_id,
            )
            if packet_key is None:
                continue
            built_keys.add(packet_key)
            packet = {
                "packet_key": packet_key,
                "actor_eid": int(actor_eid),
                "organization_eid": int(membership_org_eid),
                "organization_key": _text(membership.get("organization_key")),
                "organization_name": _text(membership.get("organization_name")),
                "root_organization_eid": _safe_int(branch_row.get("root_organization_eid"), default=membership_org_eid),
                "root_organization_key": _text(branch_row.get("root_organization_key")),
                "root_organization_name": _text(branch_row.get("root_organization_name")),
                "branch_key": _text(branch_row.get("branch_key")),
                "property_id": property_id or None,
                "building_id": building_id or None,
                "membership_role": _text(membership.get("role")).lower() or "member",
                "membership_kind": _text(membership.get("kind")).lower() or "membership",
                "membership_title": _text(membership.get("title")) or None,
                "membership_primary": bool(membership.get("primary", False)),
                "authority_rank": int(membership.get("authority_rank", 70)),
                "directive_rows": tuple(directive_rows),
                "directive_entry_keys": directive_entry_keys,
                "watch_rows": tuple(watch_rows),
                "watch_entry_keys": watch_entry_keys,
                "crime_plan_rows": tuple(crime_plan_rows),
                "crime_plan_keys": tuple(
                    _text(row.get("plan_key"))
                    for row in crime_plan_rows
                    if _text(row.get("plan_key"))
                ),
                "practice_note_text": _text(practice_bundle.get("note_text")) or None,
                "practice_effect_modifiers": dict(practice_bundle.get("effect_modifiers", {})),
                "branch_note_text": _text(branch_row.get("vocabulary_note_text")) or None,
                "workplace_state_label": _text(workplace_posture.get("dominant_label")) or None,
                "workplace_note_text": "; ".join(workplace_notes) if workplace_notes else None,
                "response_watchfulness": response_watchfulness,
                "response_service_denial_until_tick": _safe_int(branch_row.get("response_service_denial_until_tick"), default=0) or None,
                "response_target_eid": _safe_int(branch_row.get("response_target_eid"), default=0) or None,
                "response_note_text": response_note or None,
                "access_grace_rows": tuple(relation_rows),
                "access_grace_reasons": tuple(
                    _text(row.get("reason_tag"))
                    for row in relation_rows
                    if _text(row.get("reason_tag"))
                ),
                "note_texts": note_texts,
                "note_text": "; ".join(note_texts),
                "source_update_tick": int(
                    max(
                        _safe_int(branch_row.get("source_update_tick"), default=0),
                        _safe_int(branch_row.get("response_last_trigger_tick"), default=0),
                    )
                ),
                "cache_reason": _text(reason) or None,
                "packet_token": packet_token,
            }
            packets[packet_key] = packet
            built_packets.append(dict(packet))
        stale_keys = [
            packet_key
            for packet_key, row in packets.items()
            if _safe_int((row or {}).get("actor_eid"), default=0) == actor_eid
            and _text((row or {}).get("property_id")) == property_id
            and packet_key not in built_keys
        ]
        for packet_key in stale_keys:
            packets.pop(packet_key, None)
    return tuple(
        sorted(
            built_packets,
            key=lambda row: (
                int(row.get("authority_rank", 70)),
                _text(row.get("organization_name")).lower(),
                _safe_int(row.get("organization_eid"), default=0),
            ),
        )
    )


def actor_branch_briefing_packet(sim, actor_eid, prop=None, current_tick=None):
    del current_tick
    state = _organization_actor_briefing_state(sim)
    query_cache = state.get("query_cache", {})
    cache_key = _briefing_query_cache_key(actor_eid, prop=prop)
    packets = _briefing_branch_packets(sim, actor_eid, prop=prop)
    if not packets:
        packets = refresh_actor_branch_briefing(sim, actor_eid, prop=prop, reason="query")
    if not packets:
        empty_packet = {
            "actor_eid": _safe_int(actor_eid, default=0) or None,
            "property_id": _text((prop or {}).get("id")) if isinstance(prop, dict) else None,
            "building_id": _text(_property_metadata(prop).get("building_id")) if isinstance(prop, dict) else None,
            "packet_count": 0,
            "organization_eids": (),
            "organization_keys": (),
            "directive_rows": (),
            "watch_rows": (),
            "access_grace_rows": (),
            "crime_plan_rows": (),
            "practice_note_texts": (),
            "response_watchfulness": 0,
            "note_texts": (),
            "note_text": "",
            "source_update_tick": 0,
            "branch_packets": (),
        }
        query_cache[cache_key] = {
            "packet_tokens": (),
            "packet": empty_packet,
        }
        return empty_packet
    packet_tokens = _briefing_packets_token(packets)
    cached = query_cache.get(cache_key)
    if isinstance(cached, dict) and cached.get("packet_tokens") == packet_tokens:
        cached_packet = cached.get("packet")
        if isinstance(cached_packet, dict):
            return cached_packet
    directive_rows = []
    watch_rows = []
    access_rows = []
    crime_plan_rows = []
    seen_directives = set()
    seen_watch = set()
    seen_access = set()
    seen_plan_rows = set()
    organization_eids = []
    organization_keys = []
    note_texts = []
    practice_note_texts = []
    response_watchfulness = 0
    source_update_tick = 0
    property_id = _text((prop or {}).get("id")) if isinstance(prop, dict) else ""
    building_id = ""
    for packet in packets:
        if not building_id:
            building_id = _text(packet.get("building_id"))
        response_watchfulness = max(
            response_watchfulness,
            _safe_int(packet.get("response_watchfulness"), default=0),
        )
        source_update_tick = max(
            source_update_tick,
            _safe_int(packet.get("source_update_tick"), default=0),
        )
        organization_eid = _safe_int(packet.get("organization_eid"), default=0)
        if organization_eid > 0 and organization_eid not in organization_eids:
            organization_eids.append(organization_eid)
        organization_key = _text(packet.get("organization_key"))
        if organization_key and organization_key not in organization_keys:
            organization_keys.append(organization_key)
        practice_note = _text(packet.get("practice_note_text"))
        if practice_note:
            practice_note_texts.append(practice_note)
        for text in packet.get("note_texts", ()) or ():
            clean_text = _text(text)
            if clean_text:
                note_texts.append(clean_text)
        for row in packet.get("directive_rows", ()) or ():
            key = (int(row.get("organization_eid", 0)), int(row.get("entry_id", 0)))
            if key in seen_directives:
                continue
            seen_directives.add(key)
            directive_rows.append(dict(row))
        for row in packet.get("watch_rows", ()) or ():
            key = (int(row.get("organization_eid", 0)), int(row.get("entry_id", 0)))
            if key in seen_watch:
                continue
            seen_watch.add(key)
            watch_rows.append(dict(row))
        for row in packet.get("access_grace_rows", ()) or ():
            key = (
                _text(row.get("kind")),
                _safe_int(row.get("source_organization_eid"), default=0),
                _safe_int(row.get("target_org_eid"), default=0),
            )
            if key in seen_access:
                continue
            seen_access.add(key)
            access_rows.append(dict(row))
        for row in packet.get("crime_plan_rows", ()) or ():
            key = (
                _text(row.get("plan_key")),
                _safe_int(row.get("organization_eid"), default=0),
            )
            if key in seen_plan_rows:
                continue
            seen_plan_rows.add(key)
            crime_plan_rows.append(dict(row))
    merged_notes = _briefing_note_texts(note_texts, practice_note_texts)
    result = {
        "actor_eid": _safe_int(actor_eid, default=0) or None,
        "property_id": property_id or (_text(packets[0].get("property_id")) if packets else None),
        "building_id": building_id or None,
        "packet_count": len(packets),
        "organization_eids": tuple(organization_eids),
        "organization_keys": tuple(organization_keys),
        "directive_rows": _sort_vocabulary_rows(directive_rows),
        "watch_rows": _sort_watchlist_rows(watch_rows),
        "access_grace_rows": tuple(access_rows),
        "crime_plan_rows": tuple(
            sorted(
                crime_plan_rows,
                key=lambda row: (
                    _text(row.get("stage")).lower(),
                    _text(row.get("kind")).lower(),
                    _text(row.get("plan_key")),
                ),
            )
        ),
        "practice_note_texts": tuple(_briefing_note_texts(practice_note_texts)),
        "response_watchfulness": int(response_watchfulness),
        "note_texts": merged_notes,
        "note_text": "; ".join(merged_notes),
        "source_update_tick": int(source_update_tick),
        "branch_packets": packets,
    }
    query_cache[cache_key] = {
        "packet_tokens": packet_tokens,
        "packet": result,
    }
    return result


def _workplace_practice_rows(sim, prop, *, current_tick=None):
    rows = []
    for row in property_org_practices(
        sim,
        prop,
        active_only=True,
        current_tick=current_tick,
        hydrate_branch=False,
    ):
        modifiers = row.get("effect_modifiers") if isinstance(row.get("effect_modifiers"), dict) else {}
        modifier_keys = {
            _text(key).lower().replace(" ", "_")
            for key in modifiers.keys()
            if _text(key)
        }
        if not modifier_keys.intersection(WORKPLACE_EFFECT_KEYS):
            continue
        local_org_eid = _safe_int(
            row.get("requested_organization_eid"),
            default=_safe_int(row.get("organization_eid"), default=0),
        )
        policy = organization_policy_snapshot(sim, local_org_eid) if local_org_eid > 0 else None
        family = _text((policy or {}).get("family")).lower()
        if family == "corporate":
            posture_family = "corporate"
        elif family in COLLECTIVE_ORG_FAMILIES:
            posture_family = "collective"
        else:
            continue
        rows.append(
            {
                **row,
                "local_organization_eid": local_org_eid,
                "posture_family": posture_family,
            }
        )
    return _sort_practice_rows(rows)


def _workplace_relation_rows(sim, prop):
    if not isinstance(prop, dict):
        return ()
    linked_eids = {
        _safe_int(link.get("organization_eid"), default=0)
        for link in property_org_links(sim, prop, active_only=True)
        if _safe_int(link.get("organization_eid"), default=0) > 0
    }
    if not linked_eids:
        return ()
    rows = []
    seen = set()
    for source_org_eid in linked_eids:
        for relation in organization_relations(sim, source_org_eid, active_only=True):
            relation_kind = _text(relation.get("kind")).lower()
            if relation_kind not in {"represents", "bargains_with"}:
                continue
            target_org_eid = _safe_int(relation.get("target_org_eid"), default=0)
            if target_org_eid <= 0 or target_org_eid not in linked_eids:
                continue
            key = (source_org_eid, target_org_eid, relation_kind)
            if key in seen:
                continue
            seen.add(key)
            effect = _relation_access_effect(relation_kind)
            rows.append(
                {
                    **relation,
                    **effect,
                    "source_organization_eid": int(source_org_eid),
                    "target_org_eid": int(target_org_eid),
                }
            )
    return tuple(
        sorted(
            rows,
            key=lambda row: (
                0 if _text(row.get("kind")).lower() == "represents" else 1,
                _text(row.get("organization_name")).lower(),
                _safe_int(row.get("target_org_eid"), default=0),
            ),
        )
    )


def _workplace_allowed_phases(prop):
    metadata = _property_metadata(prop) if isinstance(prop, dict) else {}
    archetype = _text(metadata.get("archetype", (prop or {}).get("kind"))).lower()
    domains = set(property_field_domains(prop)) if isinstance(prop, dict) else set()
    services = set(property_service_ids(prop)) if isinstance(prop, dict) else set()
    phases = set()

    if archetype in {"bank", "brokerage", "office", "tower", "biotech_clinic", "data_center", "co_working_hub"} or domains.intersection({"finance", "professional_services", "technology"}):
        phases.update({"owner_screening", "paperwork_surge", "shift_handoff"})
    if archetype in {"courier_office", "contractor_office", "warehouse"} or domains.intersection({"logistics", "transit", "repair", "property_services"}):
        phases.update({"manifest_check", "dispatch_surge", "loading_push", "day_labor_call", "shift_handoff"})
    if domains.intersection({"medical", "support"}) or archetype in {"clinic", "biotech_clinic"} or services.intersection({"rest", "shelter"}):
        phases.update({"clinic_outreach", "mutual_aid_table", "shift_handoff"})
    if bool(metadata.get("public")) or _text(metadata.get("customer_policy")).lower() == "public":
        phases.update({"owner_screening", "shift_handoff"})
    if not phases:
        phases.add("shift_handoff")
    return phases


def _workplace_phase_label(phase):
    phase_key = _text(phase).lower()
    if phase_key == "owner_screening":
        return "Screened Entry"
    if phase_key == "paperwork_surge":
        return "Paperwork Surge"
    if phase_key == "manifest_check":
        return "Manifest Check"
    if phase_key == "dispatch_surge":
        return "Dispatch Surge"
    if phase_key == "shift_handoff":
        return "Shift Handoff"
    if phase_key == "day_labor_call":
        return "Crew Call"
    if phase_key == "clinic_outreach":
        return "Clinic Outreach"
    if phase_key == "mutual_aid_table":
        return "Mutual Aid Table"
    if phase_key == "loading_push":
        return "Loading Push"
    return phase_key.replace("_", " ").title()


def _actor_has_corporate_lineage_grace(sim, actor_eid, corporate_org_eids):
    actor_eid = _safe_int(actor_eid, default=0)
    if actor_eid <= 0:
        return False
    target_lineage = set()
    for organization_eid in tuple(corporate_org_eids or ()):
        target_lineage.update(
            _organization_lineage_eids(
                sim,
                organization_eid,
                include_self=True,
                max_depth=8,
            )
        )
    if not target_lineage:
        return False
    for membership in actor_org_memberships(sim, actor_eid, active_only=True):
        membership_org_eid = _safe_int(membership.get("organization_eid"), default=0)
        if membership_org_eid <= 0:
            continue
        policy = organization_policy_snapshot(sim, membership_org_eid)
        if _text((policy or {}).get("family")).lower() != "corporate":
            continue
        lineage = set(
            _organization_lineage_eids(
                sim,
                membership_org_eid,
                include_self=True,
                max_depth=8,
            )
        )
        if lineage.intersection(target_lineage):
            return True
    return False


def _local_workplace_org_posture_base(sim, prop, *, current_tick=None):
    if not isinstance(prop, dict):
        return {
            "active": False,
            "dominant_phase": "",
            "dominant_label": "",
            "scene_biases": {},
            "service_softness_bonus": 0.0,
            "staffing_relief_bonus": 0.0,
            "staffing_pressure": 0.0,
            "note_texts": (),
            "note_text": "",
            "reason_tags": (),
            "open_roles": (),
            "corporate_rows": (),
            "collective_rows": (),
            "relation_rows": (),
            "corporate_org_eids": (),
            "collective_org_eids": (),
            "dominant_score": 0.0,
        }

    tick = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick, default=0)
    cache_state = _organization_runtime_cache_state(sim)
    cache = cache_state.get("workplace_posture", {})
    cache_key = _organization_runtime_property_cache_key(prop, current_tick=tick)
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return cached

    practice_rows = _workplace_practice_rows(sim, prop, current_tick=tick)
    corporate_rows = [row for row in practice_rows if _text(row.get("posture_family")) == "corporate"]
    collective_rows = [row for row in practice_rows if _text(row.get("posture_family")) == "collective"]
    relation_rows = list(_workplace_relation_rows(sim, prop))
    corporate_modifiers = _aggregate_practice_effect_modifiers(corporate_rows)
    collective_modifiers = _aggregate_practice_effect_modifiers(collective_rows)

    try:
        from game.organization_reputation import organization_instability_profile
    except Exception:
        organization_instability_profile = None
    try:
        from game.player_businesses import player_business_status_snapshot
    except Exception:
        player_business_status_snapshot = None

    instability = (
        organization_instability_profile(sim, prop=prop, ensure=True)
        if callable(organization_instability_profile)
        else {}
    ) or {}
    business_snapshot = (
        player_business_status_snapshot(sim, prop)
        if callable(player_business_status_snapshot)
        else None
    )
    business_snapshot = business_snapshot if isinstance(business_snapshot, dict) else {}

    open_roles = tuple(
        _text(role).lower()
        for role in tuple(business_snapshot.get("open_roles", ()) or ())
        if _text(role)
    )
    required_staff = max(0, _safe_int(business_snapshot.get("required_staff"), default=0))
    staff_total = max(0, _safe_int(business_snapshot.get("staff_total"), default=0))
    shortage = max(0, required_staff - staff_total) if required_staff > 0 else 0
    staffing_pressure = 0.0
    if required_staff > 0:
        staffing_pressure = max(staffing_pressure, min(1.0, float(shortage) / float(required_staff)))
    if open_roles:
        staffing_pressure = max(staffing_pressure, min(1.0, 0.28 + (0.16 * len(open_roles))))
    if bool(instability.get("underrepresented", False)):
        staffing_pressure = max(
            staffing_pressure,
            min(
                1.0,
                0.24 + (_safe_float(instability.get("coverage_pressure"), default=0.0) * 0.75),
            ),
        )

    staffing_relief_bonus = _safe_float(collective_modifiers.get("staffing_relief_bonus"), default=0.0)
    staffing_relief_bonus += sum(
        _safe_float(row.get("staffing_relief_bonus"), default=0.0)
        for row in relation_rows
    )
    if staffing_relief_bonus > 0.0:
        staffing_pressure = max(0.0, staffing_pressure - min(0.4, staffing_relief_bonus))

    service_softness_bonus = _safe_float(collective_modifiers.get("service_softness_bonus"), default=0.0)
    service_softness_bonus += sum(
        _safe_float(row.get("service_softness_bonus"), default=0.0)
        for row in relation_rows
    )

    scene_biases = {}
    allowed_phases = _workplace_allowed_phases(prop)
    scene_biases["owner_screening"] = _safe_float(corporate_modifiers.get("screening_bias"), default=0.0)
    scene_biases["paperwork_surge"] = _safe_float(corporate_modifiers.get("paperwork_bias"), default=0.0)
    scene_biases["manifest_check"] = _safe_float(corporate_modifiers.get("manifest_bias"), default=0.0)
    scene_biases["dispatch_surge"] = _safe_float(corporate_modifiers.get("dispatch_bias"), default=0.0)
    scene_biases["shift_handoff"] = _safe_float(corporate_modifiers.get("handoff_bias"), default=0.0) + _safe_float(collective_modifiers.get("handoff_bias"), default=0.0)
    scene_biases["day_labor_call"] = _safe_float(collective_modifiers.get("crew_bias"), default=0.0)
    scene_biases["clinic_outreach"] = _safe_float(collective_modifiers.get("support_bias"), default=0.0)
    scene_biases["mutual_aid_table"] = _safe_float(collective_modifiers.get("aid_bias"), default=0.0)
    scene_biases["loading_push"] = _safe_float(collective_modifiers.get("loading_bias"), default=0.0)

    if staffing_pressure > 0.0:
        scene_biases["day_labor_call"] = scene_biases.get("day_labor_call", 0.0) + (staffing_pressure * 0.75)
        scene_biases["loading_push"] = scene_biases.get("loading_push", 0.0) + (staffing_pressure * 0.45)
        scene_biases["shift_handoff"] = scene_biases.get("shift_handoff", 0.0) + (staffing_pressure * 0.25)
    if service_softness_bonus > 0.0:
        scene_biases["clinic_outreach"] = scene_biases.get("clinic_outreach", 0.0) + min(0.4, service_softness_bonus * 1.5)
        scene_biases["mutual_aid_table"] = scene_biases.get("mutual_aid_table", 0.0) + min(0.35, service_softness_bonus * 1.2)

    filtered_scene_biases = {
        phase: float(score)
        for phase, score in scene_biases.items()
        if phase in allowed_phases and float(score) > 0.0
    }
    dominant_phase = ""
    dominant_score = 0.0
    for phase, score in filtered_scene_biases.items():
        if score > dominant_score:
            dominant_phase = phase
            dominant_score = float(score)

    corporate_org_eids = tuple(
        sorted(
            {
                _safe_int(row.get("local_organization_eid"), default=0)
                for row in corporate_rows
                if _safe_int(row.get("local_organization_eid"), default=0) > 0
            }
        )
    )

    corporate_notes = list(_practice_bundle_notes(corporate_rows, limit=2))
    collective_notes = list(_practice_bundle_notes(collective_rows, limit=2))
    relation_notes = [
        _text(row.get("note"))
        for row in relation_rows
        if _text(row.get("note"))
    ]
    if corporate_rows and scene_biases.get("owner_screening", 0.0) >= 0.45:
        corporate_notes.append("The front is running tighter screening and manifest habits than usual.")
    if collective_rows and staffing_relief_bonus > 0.0:
        collective_notes.append("Collective backing is helping keep the floor together under staffing strain.")
    elif collective_rows and service_softness_bonus > 0.0:
        collective_notes.append("Collective support is making the front read softer and more coordinated.")
    if collective_rows and open_roles:
        collective_notes.append("Open roles are visible, but the crew is trying to hold the shift together.")

    reason_tags = []
    if corporate_rows:
        reason_tags.append("corporate_discipline")
    if collective_rows:
        reason_tags.append("collective_support")
    if relation_rows:
        reason_tags.append("collective_relations")
    if staffing_pressure > 0.0:
        reason_tags.append("staffing_pressure")

    note_texts = _briefing_note_texts(corporate_notes, collective_notes, relation_notes)
    result = {
        "active": bool(corporate_rows or collective_rows or relation_rows),
        "corporate_rows": tuple(corporate_rows),
        "collective_rows": tuple(collective_rows),
        "relation_rows": tuple(relation_rows),
        "corporate_org_eids": corporate_org_eids,
        "collective_org_eids": tuple(
            sorted(
                {
                    _safe_int(row.get("local_organization_eid"), default=0)
                    for row in collective_rows
                    if _safe_int(row.get("local_organization_eid"), default=0) > 0
                }
            )
        ),
        "service_softness_bonus": float(service_softness_bonus),
        "staffing_relief_bonus": float(staffing_relief_bonus),
        "staffing_pressure": float(staffing_pressure),
        "open_roles": tuple(open_roles),
        "dominant_phase": dominant_phase,
        "dominant_label": _workplace_phase_label(dominant_phase) if dominant_phase else "",
        "dominant_score": float(dominant_score),
        "scene_biases": dict(filtered_scene_biases),
        "reason_tags": tuple(reason_tags),
        "note_texts": note_texts,
        "note_text": "; ".join(note_texts),
    }
    if cache_key is not None:
        cache[cache_key] = result
    return result


def local_workplace_org_posture(sim, prop, *, actor_eid=None, current_tick=None):
    if not isinstance(prop, dict):
        return {
            "active": False,
            "dominant_phase": "",
            "dominant_label": "",
            "scene_biases": {},
            "screening_grace": False,
            "service_softness_bonus": 0.0,
            "staffing_relief_bonus": 0.0,
            "staffing_pressure": 0.0,
            "note_texts": (),
            "note_text": "",
            "reason_tags": (),
            "open_roles": (),
            "corporate_rows": (),
            "collective_rows": (),
            "relation_rows": (),
            "corporate_org_eids": (),
            "collective_org_eids": (),
            "dominant_score": 0.0,
        }

    tick = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick, default=0)
    actor_eid = _safe_int(actor_eid, default=0)
    cache_state = _organization_runtime_cache_state(sim)
    cache = cache_state.get("workplace_posture", {})
    cache_key = _organization_runtime_property_cache_key(
        prop,
        actor_eid=actor_eid,
        current_tick=tick,
    )
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return cached

    base = _local_workplace_org_posture_base(sim, prop, current_tick=tick)
    screening_grace = bool(base.get("corporate_rows")) and actor_eid > 0 and float(base.get("dominant_score", 0.0) or 0.0) >= 0.55 and _actor_has_corporate_lineage_grace(
        sim,
        actor_eid,
        base.get("corporate_org_eids", ()),
    )
    base_note_texts = tuple(base.get("note_texts", ()) or ())
    if screening_grace:
        base_note_texts = tuple(
            note
            for note in base_note_texts
            if note != "The front is running tighter screening and manifest habits than usual."
        )
        note_texts = _briefing_note_texts(
            ("Corporate branch staff can clear the front desk with less friction here.",),
            base_note_texts,
        )
    else:
        note_texts = base_note_texts

    result = dict(base)
    result["screening_grace"] = bool(screening_grace)
    result["note_texts"] = tuple(note_texts)
    result["note_text"] = "; ".join(note_texts)
    if cache_key is not None:
        cache[cache_key] = result
    return result


def _legacy_property_denial_state(sim, prop, *, viewer_eid=None, current_tick=None):
    if not isinstance(prop, dict):
        return None
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        return None
    response_state = traits.get("organization_response")
    if not isinstance(response_state, dict):
        return None
    denials = response_state.get("property_denials")
    if not isinstance(denials, dict):
        return None
    property_id = _text(prop.get("id"))
    denial = denials.get(property_id)
    if not isinstance(denial, dict):
        return None
    tick = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick, default=0)
    if tick > _safe_int(denial.get("service_denial_until_tick"), default=-1):
        return None
    target_eid = _safe_int(denial.get("target_eid"), default=0) or None
    if viewer_eid is not None and target_eid not in {None, _safe_int(viewer_eid, default=0) or None}:
        return None
    return dict(denial)


def _protective_incident_matches_property(sim, incident, prop):
    if not isinstance(incident, dict) or not isinstance(prop, dict):
        return False
    property_id = _text(prop.get("id"))
    if property_id and property_id == _text(incident.get("property_id")):
        return True
    prop_building_id = _text(_property_metadata(prop).get("building_id"))
    if not prop_building_id:
        return False
    incident_prop = sim.properties.get(_text(incident.get("property_id")))
    if not isinstance(incident_prop, dict):
        return False
    return prop_building_id == _text(_property_metadata(incident_prop).get("building_id"))


def _organization_is_vigilante(sim, policy):
    if not isinstance(policy, dict):
        return False
    if _text(policy.get("family")).lower() != "street_gang":
        return False
    root_eid = _safe_int(
        policy.get("root_organization_eid"),
        default=_safe_int(policy.get("organization_eid"), default=0),
    )
    if root_eid <= 0:
        return False
    root_profile = organization_profile(sim, root_eid)
    root_tags = {
        _text(tag).lower()
        for tag in getattr(root_profile, "tags", ()) or ()
        if _text(tag)
    }
    return "gang_posture:vigilante" in root_tags


def _protective_practice_rows(sim, prop, *, current_tick=None):
    rows = []
    for row in property_org_practices(
        sim,
        prop,
        active_only=True,
        current_tick=current_tick,
        hydrate_branch=False,
    ):
        modifiers = row.get("effect_modifiers") if isinstance(row.get("effect_modifiers"), dict) else {}
        if not any(_text(key).lower() in PROTECTIVE_EFFECT_KEYS for key in modifiers.keys()):
            continue
        local_org_eid = _safe_int(
            row.get("requested_organization_eid"),
            default=_safe_int(row.get("organization_eid"), default=0),
        )
        policy = organization_policy_snapshot(sim, local_org_eid) if local_org_eid > 0 else None
        family = _text((policy or {}).get("family")).lower()
        if family == "municipal":
            protective_family = "civic"
        elif _organization_is_vigilante(sim, policy):
            protective_family = "vigilante"
        else:
            continue
        rows.append(
            {
                **row,
                "local_organization_eid": local_org_eid,
                "protective_family": protective_family,
            }
        )
    return _sort_practice_rows(rows)


def _recent_protective_history_rows(sim, prop, *, current_tick=None, max_age=PROTECTIVE_PRESSURE_RESPONSE_TICKS):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict) or not isinstance(prop, dict):
        return ()
    state = traits.get("organization_response")
    if not isinstance(state, dict):
        return ()
    history = state.get("history")
    if not isinstance(history, list):
        return ()
    tick = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick, default=0)
    property_id = _text(prop.get("id"))
    return tuple(
        dict(row)
        for row in history
        if isinstance(row, dict)
        and _text(row.get("property_id")) == property_id
        and tick - _safe_int(row.get("tick"), default=-10_000) <= int(max_age)
    )


def _recent_official_incidents_for_property(sim, prop, *, current_tick=None, max_age=PROTECTIVE_PRESSURE_RECENT_TICKS):
    tick = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick, default=0)
    rows = []
    for incident in incident_records(sim):
        if not isinstance(incident, dict):
            continue
        if not bool(incident.get("officially_reported") or incident.get("justice_accounted")):
            continue
        if not _protective_incident_matches_property(sim, incident, prop):
            continue
        report_tick = max(
            _safe_int(incident.get("justice_accounted_tick"), default=0),
            _safe_int(incident.get("reported_tick"), default=0),
            _safe_int(incident.get("last_observed_tick"), default=0),
        )
        if tick - report_tick > int(max_age):
            continue
        rows.append(dict(incident))
    return tuple(rows)


def local_protective_pressure_snapshot(sim, prop, *, current_tick=None):
    if not isinstance(prop, dict):
        return {
            "active": False,
            "state_key": "",
            "state_label": "",
            "summary": "",
            "action": "",
            "watchfulness": 0,
            "reason_tags": (),
            "note_texts": (),
            "note_text": "",
            "official_incident_count": 0,
            "recent_response_count": 0,
            "recent_dispatch_count": 0,
        }
    tick = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick, default=0)
    cache_state = _organization_runtime_cache_state(sim)
    cache = cache_state.get("protective_pressure", {})
    cache_key = _organization_runtime_property_cache_key(prop, current_tick=tick)
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return cached
    metadata = _property_metadata(prop)
    archetype = _text(metadata.get("archetype", prop.get("kind"))).lower()
    watch_rows = property_org_watch_state(sim, prop, active_only=True, current_tick=tick)
    denial_rows = [
        row for row in watch_rows
        if _text(row.get("action")).lower() in {"deny_service", "deny_entry"}
    ]
    legacy_denial = _legacy_property_denial_state(sim, prop, current_tick=tick)
    practice_rows = _protective_practice_rows(sim, prop, current_tick=tick)
    vigilante_rows = [row for row in practice_rows if _text(row.get("protective_family")) == "vigilante"]
    civic_rows = [row for row in practice_rows if _text(row.get("protective_family")) == "civic"]
    vigilante_modifiers = _aggregate_practice_effect_modifiers(vigilante_rows)
    civic_modifiers = _aggregate_practice_effect_modifiers(civic_rows)
    official_incidents = _recent_official_incidents_for_property(sim, prop, current_tick=tick)
    violent_count = sum(
        1
        for incident in official_incidents
        if _text(incident.get("kind")).lower() == "action_offense"
    )
    dispatch_count = sum(
        1
        for incident in official_incidents
        if max(
            _safe_int(incident.get("dispatch_active_tick"), default=-10_000),
            _safe_int(incident.get("dispatch_pending_tick"), default=-10_000),
        ) >= tick - PROTECTIVE_PRESSURE_RESPONSE_TICKS
    )
    response_rows = _recent_protective_history_rows(sim, prop, current_tick=tick)
    echo_caution = incident_echo_caution_for_property(sim, prop)
    watchfulness = 0
    for row in watch_rows:
        action = _text(row.get("action")).lower()
        base = _safe_int(row.get("priority"), default=60)
        if action == "deny_entry":
            watchfulness = max(watchfulness, min(100, base + 18))
        elif action == "deny_service":
            watchfulness = max(watchfulness, min(100, base + 10))
        else:
            watchfulness = max(watchfulness, min(100, base))
    if isinstance(legacy_denial, dict):
        watchfulness = max(watchfulness, _safe_int(legacy_denial.get("watchfulness"), default=0))
    watchfulness_bonus = int(round(
        _safe_float(vigilante_modifiers.get("watchfulness_bonus"), default=0.0)
        + _safe_float(civic_modifiers.get("watchfulness_bonus"), default=0.0)
        + _safe_float(vigilante_modifiers.get("watch_priority_bonus"), default=0.0)
        + _safe_float(civic_modifiers.get("watch_priority_bonus"), default=0.0)
    ))
    official_pressure = min(
        26,
        (len(official_incidents) * 4)
        + (violent_count * 4)
        + (dispatch_count * 5)
        + (len(response_rows) * 4),
    )
    echo_watchfulness_bonus = _safe_int(echo_caution.get("watchfulness_bonus"), default=0)
    watchfulness = max(
        watchfulness,
        min(100, watchfulness + watchfulness_bonus + official_pressure + echo_watchfulness_bonus),
    )
    readiness_tier = int(
        max(
            0,
            round(_safe_float(vigilante_modifiers.get("response_readiness_tier"), default=0.0)),
            round(_safe_float(civic_modifiers.get("response_readiness_tier"), default=0.0)),
        )
    )
    response_score_bonus = float(vigilante_modifiers.get("response_score_bonus", 0.0) or 0.0) + float(civic_modifiers.get("response_score_bonus", 0.0) or 0.0)
    confrontation_posture = float(vigilante_modifiers.get("confrontation_posture_bonus", 0.0) or 0.0) + float(civic_modifiers.get("confrontation_posture_bonus", 0.0) or 0.0)
    report_conversion_bonus = float(vigilante_modifiers.get("report_conversion_bonus", 0.0) or 0.0) + float(civic_modifiers.get("report_conversion_bonus", 0.0) or 0.0)
    dispatch_bonus = float(vigilante_modifiers.get("dispatch_bonus", 0.0) or 0.0) + float(civic_modifiers.get("dispatch_bonus", 0.0) or 0.0)
    followthrough_bonus = float(vigilante_modifiers.get("response_followthrough_bonus", 0.0) or 0.0) + float(civic_modifiers.get("response_followthrough_bonus", 0.0) or 0.0)
    note_texts = _practice_bundle_notes(practice_rows, limit=3)
    state_key = ""
    state_label = ""
    summary = ""
    action = ""
    if archetype == "checkpoint" and (civic_rows or dispatch_count > 0 or len(official_incidents) > 0) and watchfulness >= 14:
        state_key = "checkpoint_questioning"
        state_label = "Checkpoint Questioning"
        summary = "guards are slowing entries, asking harder questions, and holding the lane tighter than usual"
        action = "expect scrutiny at the gate or look for a softer route"
    elif (vigilante_rows or denial_rows or response_rows) and watchfulness >= 14:
        state_key = "block_watch_active"
        state_label = "Block Watch Active"
        summary = "locals are watching exits, sharing names, and tightening service against trouble"
        action = "respect the boundary, talk your way through, or press the block at a cost"
    elif (civic_rows or dispatch_count > 0 or len(official_incidents) >= 2) and watchfulness >= 16:
        state_key = "justice_sweep"
        state_label = "Justice Sweep"
        summary = "official responders are working the area harder and keeping follow-up close at hand"
        action = "expect faster scrutiny, tighter frontage reads, and less slack"
    elif watchfulness >= 10 or len(official_incidents) > 0 or watch_rows:
        state_key = "residents_on_alert"
        state_label = "Residents on Alert"
        summary = "people nearby are reading the block carefully and treating trouble like it might return"
        action = "move carefully, ask around, or wait for the block to cool"
    reason_tags = []
    if denial_rows:
        reason_tags.append("watch_denial")
    if vigilante_rows:
        reason_tags.append("vigilante_readiness")
    if civic_rows:
        reason_tags.append("civic_readiness")
    if dispatch_count > 0:
        reason_tags.append("recent_dispatch")
    if official_incidents:
        reason_tags.append("official_incidents")
    if response_rows:
        reason_tags.append("recent_response")
    if bool(echo_caution.get("active")):
        reason_tags.append("incident_echo")
        note_texts = _briefing_note_texts(note_texts, tuple(echo_caution.get("note_texts", ()) or ()))
    merged_notes = _briefing_note_texts(note_texts)
    result = {
        "active": bool(state_key),
        "state_key": state_key,
        "state_label": state_label,
        "summary": summary,
        "action": action,
        "watchfulness": int(watchfulness),
        "official_incident_count": len(official_incidents),
        "violent_incident_count": int(violent_count),
        "recent_response_count": len(response_rows),
        "recent_dispatch_count": int(dispatch_count),
        "active_watch_count": len(watch_rows),
        "active_denial_count": len(denial_rows) + (1 if isinstance(legacy_denial, dict) else 0),
        "response_readiness_tier": int(readiness_tier),
        "response_score_bonus": float(response_score_bonus),
        "confrontation_posture_bonus": float(confrontation_posture),
        "report_conversion_bonus": float(report_conversion_bonus),
        "dispatch_bonus": float(dispatch_bonus),
        "response_followthrough_bonus": float(followthrough_bonus),
        "incident_echo_count": _safe_int(echo_caution.get("incident_echo_count"), default=0),
        "reason_tags": tuple(reason_tags),
        "note_texts": merged_notes,
        "note_text": "; ".join(merged_notes),
    }
    if cache_key is not None:
        cache[cache_key] = result
    return result


def effective_org_access_posture(sim, actor_eid, prop, current_tick=None):
    if actor_eid is None or not isinstance(prop, dict):
        return {
            "briefing": {},
            "watch_rows": (),
            "relation_rows": (),
            "workplace_posture": {},
            "deny_entry": False,
            "deny_service": False,
            "watch_only": False,
            "watchfulness": 0,
            "standing_floor": 0.0,
            "public_entry_grace": False,
            "service_grace": False,
            "guard_grace": False,
            "service_softness_bonus": 0.0,
            "reason_tags": (),
            "note_text": "",
            "legacy_denial": None,
        }
    tick = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick, default=0)
    actor_eid = _safe_int(actor_eid, default=0)
    cache_state = _organization_runtime_cache_state(sim)
    cache = cache_state.get("access_posture", {})
    cache_key = _organization_runtime_property_cache_key(
        prop,
        actor_eid=actor_eid,
        current_tick=tick,
    )
    cached = cache.get(cache_key)
    if isinstance(cached, dict):
        return cached
    briefing = actor_branch_briefing_packet(sim, actor_eid, prop=prop, current_tick=tick)
    watch_rows = property_org_watch_state(
        sim,
        prop,
        subject_eid=actor_eid,
        active_only=True,
        current_tick=tick,
    )
    relation_rows = _organization_relation_access_rows(sim, actor_eid, prop)
    workplace = local_workplace_org_posture(
        sim,
        prop,
        actor_eid=actor_eid,
        current_tick=tick,
    )
    legacy_denial = _legacy_property_denial_state(
        sim,
        prop,
        viewer_eid=actor_eid,
        current_tick=tick,
    )

    deny_entry = False
    deny_service = False
    watch_only = False
    watchfulness = 0
    standing_floor = 0.0
    public_entry_grace = False
    service_grace = False
    guard_grace = False
    service_softness_bonus = 0.0
    reason_tags = []
    note_texts = []

    for row in relation_rows:
        standing_floor = max(standing_floor, float(row.get("standing_floor", 0.0) or 0.0))
        public_entry_grace = bool(public_entry_grace or row.get("public_entry_grace"))
        service_grace = bool(service_grace or row.get("service_grace"))
        guard_grace = bool(guard_grace or row.get("guard_grace"))
        service_softness_bonus = max(
            service_softness_bonus,
            _safe_float(row.get("service_softness_bonus"), default=0.0),
        )
        reason_tag = _text(row.get("reason_tag"))
        if reason_tag and reason_tag not in reason_tags:
            reason_tags.append(reason_tag)
        note = _text(row.get("note"))
        if note:
            note_texts.append(note)

    for row in watch_rows:
        action = _text(row.get("action")).lower()
        if action == "deny_entry":
            deny_entry = True
            deny_service = True
            watch_only = True
            watchfulness = max(watchfulness, min(100, int(row.get("priority", 60)) + 18))
        elif action == "deny_service":
            deny_service = True
            watch_only = True
            watchfulness = max(watchfulness, min(100, int(row.get("priority", 60)) + 10))
        else:
            watch_only = True
            watchfulness = max(watchfulness, min(100, int(row.get("priority", 60))))
        reason = _text(row.get("reason"))
        if reason:
            note_texts.append(reason)

    if isinstance(legacy_denial, dict):
        deny_service = True
        watch_only = True
        watchfulness = max(watchfulness, _safe_int(legacy_denial.get("watchfulness"), default=0))
        legacy_reason = _text(legacy_denial.get("reason"))
        if legacy_reason and "organization_denial" not in reason_tags:
            reason_tags.append("organization_denial")
        if legacy_reason:
            note_texts.append(legacy_reason.replace("_", " "))

    if briefing.get("response_watchfulness"):
        watchfulness = max(watchfulness, _safe_int(briefing.get("response_watchfulness"), default=0))
    protective = local_protective_pressure_snapshot(sim, prop, current_tick=tick)
    if bool(workplace.get("screening_grace")):
        public_entry_grace = True
        standing_floor = max(standing_floor, 0.42)
        if "corporate_screening" not in reason_tags:
            reason_tags.append("corporate_screening")
    workplace_softness = _safe_float(workplace.get("service_softness_bonus"), default=0.0)
    if workplace_softness > 0.0 and (service_grace or bool(briefing.get("packet_count"))):
        service_softness_bonus = max(service_softness_bonus, workplace_softness)
        if "collective_softness" not in reason_tags:
            reason_tags.append("collective_softness")
    if protective.get("watchfulness"):
        watchfulness = max(watchfulness, _safe_int(protective.get("watchfulness"), default=0))
    if protective.get("state_key") and "protective_pressure" not in reason_tags:
        reason_tags.append("protective_pressure")
    if protective.get("state_label"):
        note_texts.append(_text(protective.get("state_label")))
    if protective.get("summary"):
        note_texts.append(_text(protective.get("summary")))
    if workplace.get("dominant_label") and "workplace_posture" not in reason_tags:
        reason_tags.append("workplace_posture")
    if workplace.get("dominant_label"):
        note_texts.append(_text(workplace.get("dominant_label")))
    if workplace.get("note_text"):
        note_texts.append(_text(workplace.get("note_text")))
    note_texts.extend(briefing.get("note_texts", ()) or ())
    merged_notes = _briefing_note_texts(note_texts)
    result = {
        "briefing": briefing,
        "watch_rows": tuple(watch_rows),
        "relation_rows": tuple(relation_rows),
        "workplace_posture": dict(workplace) if isinstance(workplace, dict) else {},
        "deny_entry": bool(deny_entry),
        "deny_service": bool(deny_service),
        "watch_only": bool(watch_only),
        "watchfulness": int(watchfulness),
        "standing_floor": float(standing_floor),
        "public_entry_grace": bool(public_entry_grace),
        "service_grace": bool(service_grace),
        "guard_grace": bool(guard_grace),
        "service_softness_bonus": float(service_softness_bonus),
        "reason_tags": tuple(reason_tags),
        "note_text": "; ".join(merged_notes),
        "note_texts": merged_notes,
        "legacy_denial": dict(legacy_denial) if isinstance(legacy_denial, dict) else None,
        "protective_pressure": dict(protective) if isinstance(protective, dict) else {},
    }
    if cache_key is not None:
        cache[cache_key] = result
    return result


def organization_guard_grace_active(sim, actor_eid, prop, current_tick=None):
    posture = effective_org_access_posture(
        sim,
        actor_eid,
        prop,
        current_tick=current_tick,
    )
    return bool(posture.get("guard_grace")) and not bool(posture.get("deny_entry"))


def refresh_loaded_organization_branch_briefings(sim, *, property_ids=None, reason=""):
    state = _organization_actor_briefing_state(sim)
    if bool(state.get("refreshing", False)):
        return ()
    state["refreshing"] = True
    properties = []
    seen_property_ids = set()
    try:
        for property_id in property_ids or ():
            prop = sim.properties.get(property_id)
            if not isinstance(prop, dict):
                continue
            clean_property_id = _text(prop.get("id"))
            if not clean_property_id or clean_property_id in seen_property_ids:
                continue
            seen_property_ids.add(clean_property_id)
            properties.append(prop)
        refreshed = []
        positions = sim.ecs.get(Position)
        for prop in properties:
            if not property_org_links(sim, prop, active_only=True):
                continue
            for row in property_org_members(sim, prop):
                actor_eid = _safe_int(row.get("eid"), default=0)
                if actor_eid <= 0 or positions.get(actor_eid) is None:
                    continue
                refreshed.extend(
                    refresh_actor_branch_briefing(
                        sim,
                        actor_eid,
                        prop=prop,
                        reason=reason or "property_refresh",
                    )
                )
        return tuple(refreshed)
    finally:
        state["refreshing"] = False


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
    row_property_id = _text(row.get("property_id"))
    if row_property_id:
        return row_property_id == property_id
    if row.get("building_id") and row.get("building_id") in building_ids:
        return True
    return False


def _profile_has_active_primary_operates_link(profile, prop, organization_eid):
    if profile is None:
        return False
    for row in tuple(getattr(profile, "site_links", ()) or ()):
        normalized = _normalize_site_link_row(row, organization_eid=organization_eid)
        if not _site_link_matches_property(prop, normalized):
            continue
        if normalized.get("link_kind") != "operates":
            continue
        if not bool(normalized.get("primary", False)):
            continue
        if not bool(normalized.get("active", True)):
            continue
        return True
    return False


def _property_org_link_index(sim, *, active_only=True, cache=None):
    cache_state = _organization_runtime_cache_state(sim)
    if not isinstance(cache, dict):
        cache = cache_state.get("property_links", {})
    index_key = ("__link_index__", bool(active_only))
    cached = cache.get(index_key)
    if isinstance(cached, dict):
        return cached

    by_property = {}
    by_building = {}
    for organization_eid, _profile_component in sim.ecs.get(OrganizationProfile).items():
        profile = organization_profile(sim, organization_eid)
        if profile is None:
            continue
        for raw_row in tuple(getattr(profile, "site_links", ()) or ()):
            row = _normalize_site_link_row(raw_row, organization_eid=organization_eid)
            if active_only and not bool(row.get("active", True)):
                continue
            enriched = {
                **row,
                "organization_key": _text(profile.key),
                "organization_name": _text(profile.name),
                "organization_kind": _normalize_org_kind(profile.kind, default="other"),
            }
            property_id = _text(row.get("property_id"))
            building_id = _text(row.get("building_id"))
            if property_id:
                by_property.setdefault(property_id, []).append(enriched)
            if building_id:
                by_building.setdefault(building_id, []).append(enriched)

    result = {
        "by_property": by_property,
        "by_building": by_building,
    }
    cache[index_key] = result
    return result


def _synthetic_primary_property_org_link(sim, prop, organization_eid):
    if not isinstance(prop, dict):
        return None
    organization_eid = _safe_int(organization_eid, default=0)
    if organization_eid <= 0:
        return None
    profile = organization_profile(sim, organization_eid)
    if profile is None:
        return None
    metadata = _property_metadata(prop)
    row = _normalize_site_link_row(
        {
            "organization_eid": int(organization_eid),
            "property_id": _text(prop.get("id")) or None,
            "building_id": _text(metadata.get("building_id")) or _text(metadata.get("local_building_id")) or None,
            "link_kind": "operates",
            "primary": True,
            "active": True,
        },
        organization_eid=organization_eid,
    )
    return {
        **row,
        "organization_key": _text(profile.key),
        "organization_name": _text(profile.name),
        "organization_kind": _normalize_org_kind(profile.kind, default="other"),
    }


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
    _invalidate_organization_runtime_caches(sim)
    if not _organization_member_read_active(sim):
        hydrate_property_organization_branches(
            sim,
            prop,
            organization_eid=organization_eid,
            current_tick=getattr(sim, "tick", 0),
            active_only=True,
        )
    return dict(row)


def property_org_links(sim, prop, *, active_only=True):
    if not isinstance(prop, dict):
        return ()
    metadata = _property_metadata(prop)
    cache_key = (
        _text(prop.get("id")),
        _text(metadata.get("building_id")) or _text(metadata.get("local_building_id")),
        bool(active_only),
    )
    cache_state = _organization_runtime_cache_state(sim)
    cache = cache_state.get("property_links", {})
    cached = cache.get(cache_key)
    if isinstance(cached, tuple):
        return cached
    synthetic_primary = None
    primary_org_eid = property_organization_eid(sim, prop, ensure=False)
    if primary_org_eid is not None:
        profile = organization_profile(sim, primary_org_eid)
        if profile is not None and not _profile_has_active_primary_operates_link(profile, prop, primary_org_eid):
            synthetic_primary = _synthetic_primary_property_org_link(sim, prop, primary_org_eid)

    link_index = _property_org_link_index(sim, active_only=active_only, cache=cache)
    property_id = _text(prop.get("id"))
    building_ids = {
        _text(metadata.get("building_id")),
        _text(metadata.get("local_building_id")),
    } - {""}
    rows = []
    seen = set()

    def _append_link_row(row):
        if not isinstance(row, dict):
            return
        key = (
            _safe_int(row.get("organization_eid"), default=0),
            _text(row.get("property_id")),
            _text(row.get("building_id")),
            _text(row.get("link_kind")),
        )
        if key in seen:
            return
        seen.add(key)
        rows.append(dict(row))

    if isinstance(synthetic_primary, dict) and (not active_only or bool(synthetic_primary.get("active", True))):
        _append_link_row(synthetic_primary)
    for row in tuple(link_index.get("by_property", {}).get(property_id, ()) if property_id else ()):
        _append_link_row(row)
    for building_id in sorted(building_ids):
        for row in tuple(link_index.get("by_building", {}).get(building_id, ())):
            if _text(row.get("property_id")):
                continue
            _append_link_row(row)
    rows.sort(
        key=lambda row: (
            0 if row.get("primary") else 1,
            0 if row.get("link_kind") == "operates" else 1,
            _text(row.get("link_kind")),
            _text(row.get("organization_name")).lower(),
            _safe_int(row.get("organization_eid"), default=0),
        )
    )
    result = tuple(rows)
    cache[cache_key] = result
    return result


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


def _normalize_diplomacy_stance(value, default="neutral"):
    stance = _text(value).lower().replace(" ", "_")
    if stance in ORGANIZATION_DIPLOMACY_STANCES:
        return stance
    return default


def _diplomacy_tag_is_allowed(tag):
    tag = _text(tag).lower().replace(" ", "_")
    if not tag:
        return False
    if tag in ORGANIZATION_DIPLOMACY_SENSITIVE_TAGS:
        return False
    if any(tag.startswith(prefix) for prefix in ORGANIZATION_DIPLOMACY_SENSITIVE_PREFIXES):
        return False
    return True


def normalize_organization_diplomacy_tags(values):
    """Normalize reason/compatibility tags while excluding harmful doctrine axes."""

    if isinstance(values, str):
        values = (values,)
    cleaned = []
    for value in values or ():
        tag = _text(value).lower().replace(" ", "_")
        if not _diplomacy_tag_is_allowed(tag):
            continue
        if tag not in cleaned:
            cleaned.append(tag)
    return tuple(sorted(cleaned))


def _organization_diplomacy_state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    state = traits.get("organization_diplomacy")
    if not isinstance(state, dict):
        state = {}
        traits["organization_diplomacy"] = state
    pairs = state.get("pairs")
    if not isinstance(pairs, dict):
        pairs = {}
        state["pairs"] = pairs
    pressures = state.get("pressures")
    if not isinstance(pressures, dict):
        pressures = {}
        state["pressures"] = pressures
    cooldowns = state.get("cooldowns")
    if not isinstance(cooldowns, dict):
        cooldowns = {}
        state["cooldowns"] = cooldowns
    state["next_pressure_id"] = max(1, _safe_int(state.get("next_pressure_id"), default=1))
    return state


def _organization_pair_key(org_a_eid, org_b_eid):
    a = _safe_int(org_a_eid, default=0)
    b = _safe_int(org_b_eid, default=0)
    if a <= 0 or b <= 0 or a == b:
        return ""
    low, high = sorted((a, b))
    return f"{low}:{high}"


def _diplomacy_org_ref(sim, organization_eid):
    profile = organization_profile(sim, organization_eid)
    if profile is None:
        return None
    policy = organization_policy_snapshot(sim, organization_eid=organization_eid) or {}
    return {
        "organization_eid": int(organization_eid),
        "organization_key": _text(getattr(profile, "key", "")),
        "organization_name": _text(getattr(profile, "name", "")) or "Organization",
        "organization_kind": _normalize_org_kind(getattr(profile, "kind", ""), default="other"),
        "family": _text(policy.get("family")).lower()
        or _family_from_tags(getattr(profile, "tags", ()) or ())
        or _normalize_org_kind(getattr(profile, "kind", ""), default="other"),
        "tags": tuple(sorted(getattr(profile, "tags", ()) or ())),
    }


def organization_interest_profile(sim, organization_eid):
    """Return the shared interest/compatibility read for an organization."""

    ref = _diplomacy_org_ref(sim, organization_eid)
    if ref is None:
        return {
            "organization_eid": None,
            "organization_key": "",
            "organization_name": "",
            "organization_kind": "other",
            "family": "other",
            "interests": (),
            "compatibility_tags": (),
        }
    interests = set(ORGANIZATION_DIPLOMACY_INTERESTS_BY_KIND.get(ref["organization_kind"], ()))
    interests.update(ORGANIZATION_DIPLOMACY_INTERESTS_BY_FAMILY.get(ref["family"], ()))
    compatibility_tags = set()
    for raw_tag in ref.get("tags", ()):
        tag = _text(raw_tag).lower().replace(" ", "_")
        if not _diplomacy_tag_is_allowed(tag):
            continue
        compatibility_tags.add(tag)
        if tag.startswith("interest:"):
            interest = tag.split(":", 1)[1]
            if _diplomacy_tag_is_allowed(interest):
                interests.add(interest)
        elif tag.startswith("devotion:"):
            interests.add("devotion")
            compatibility_tags.add("devotion")
        elif tag.startswith("territory:"):
            interests.add("territory")
        elif tag.startswith("service:"):
            interests.add("service_access")
        elif tag in {"corporate", "corpsec"}:
            interests.update(ORGANIZATION_DIPLOMACY_INTERESTS_BY_FAMILY.get("corporate", ()))
        elif tag in {"union", "labor_union"}:
            interests.update(ORGANIZATION_DIPLOMACY_INTERESTS_BY_FAMILY.get("labor_union", ()))
        elif tag in {"guild", "trade_guild"}:
            interests.update(ORGANIZATION_DIPLOMACY_INTERESTS_BY_FAMILY.get("trade_guild", ()))
        elif tag in {"street_gang", "vigilante"}:
            interests.update(ORGANIZATION_DIPLOMACY_INTERESTS_BY_FAMILY.get("street_gang", ()))
    return {
        **ref,
        "interests": tuple(sorted(normalize_organization_diplomacy_tags(interests))),
        "compatibility_tags": tuple(sorted(normalize_organization_diplomacy_tags(compatibility_tags))),
    }


def organization_compatibility_read(sim, org_a_eid, org_b_eid):
    """Return a non-moral, non-demographic compatibility read for two orgs."""

    a = organization_interest_profile(sim, org_a_eid)
    b = organization_interest_profile(sim, org_b_eid)
    a_interests = set(a.get("interests", ()) or ())
    b_interests = set(b.get("interests", ()) or ())
    a_tags = set(a.get("compatibility_tags", ()) or ())
    b_tags = set(b.get("compatibility_tags", ()) or ())
    shared_interests = tuple(sorted(a_interests & b_interests))
    shared_tags = tuple(sorted(normalize_organization_diplomacy_tags(a_tags & b_tags)))
    pressure_interests = tuple(sorted((a_interests | b_interests) & {"property", "territory", "customers", "devotion", "revenge", "protection"}))
    return {
        "org_a": a,
        "org_b": b,
        "shared_interests": shared_interests,
        "shared_tags": shared_tags,
        "pressure_interests": pressure_interests,
        "reason_tags": tuple(sorted(set(shared_interests) | set(shared_tags))),
    }


def _normalize_diplomacy_pair_row(sim, pair_key, row, *, current_tick=None, include_profiles=True):
    if not isinstance(row, dict):
        return None
    tick = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick, default=0)
    org_a = _safe_int(row.get("org_a_eid"), default=0)
    org_b = _safe_int(row.get("org_b_eid"), default=0)
    if org_a <= 0 or org_b <= 0 or org_a == org_b:
        return None
    expires_tick = _safe_int(row.get("expires_tick"), default=0) or None
    active = bool(row.get("active", True)) and not (expires_tick is not None and expires_tick <= tick)
    history = row.get("recent_history")
    if not isinstance(history, list):
        history = []
    history = [dict(entry) for entry in history if isinstance(entry, dict)][-ORGANIZATION_DIPLOMACY_MAX_HISTORY:]
    result = {
        "pair_key": _text(row.get("pair_key")) or pair_key or _organization_pair_key(org_a, org_b),
        "org_a_eid": int(org_a),
        "org_b_eid": int(org_b),
        "stance": _normalize_diplomacy_stance(row.get("stance")),
        "confidence": max(0.0, min(1.0, _safe_float(row.get("confidence"), default=0.0))),
        "reason_tags": normalize_organization_diplomacy_tags(row.get("reason_tags", ())),
        "last_update_tick": _safe_int(row.get("last_update_tick"), default=tick),
        "expires_tick": expires_tick,
        "active": bool(active),
        "recent_history": tuple(history),
    }
    if include_profiles:
        a_ref = _diplomacy_org_ref(sim, org_a) or {}
        b_ref = _diplomacy_org_ref(sim, org_b) or {}
        result.update({
            "org_a_key": _text(a_ref.get("organization_key")),
            "org_a_name": _text(a_ref.get("organization_name")) or f"org {org_a}",
            "org_a_kind": _text(a_ref.get("organization_kind")) or "other",
            "org_b_key": _text(b_ref.get("organization_key")),
            "org_b_name": _text(b_ref.get("organization_name")) or f"org {org_b}",
            "org_b_kind": _text(b_ref.get("organization_kind")) or "other",
        })
    return result


def _normalize_pressure_row(sim, pressure_key, row, *, current_tick=None):
    if not isinstance(row, dict):
        return None
    tick = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick, default=0)
    organization_eid = _safe_int(row.get("organization_eid"), default=0)
    if organization_eid <= 0 or organization_profile(sim, organization_eid) is None:
        return None
    expires_tick = _safe_int(row.get("expires_tick"), default=0) or None
    active = bool(row.get("active", True)) and not (expires_tick is not None and expires_tick <= tick)
    related_org_eid = _safe_int(row.get("related_org_eid"), default=0) or None
    ref = _diplomacy_org_ref(sim, organization_eid) or {}
    related_ref = _diplomacy_org_ref(sim, related_org_eid) if related_org_eid else None
    stance = _normalize_diplomacy_stance(row.get("stance"))
    pressure_kind = _text(row.get("pressure_kind")).lower().replace(" ", "_") or stance
    property_id = _text(row.get("anchor_property_id"))
    scene_id = _text(row.get("anchor_scene_id"))
    actor_eid = _safe_int(row.get("anchor_actor_eid"), default=0) or None
    has_anchor = bool(property_id or scene_id or actor_eid)
    return {
        "pressure_key": _text(row.get("pressure_key")) or pressure_key,
        "organization_eid": int(organization_eid),
        "organization_key": _text(ref.get("organization_key")),
        "organization_name": _text(ref.get("organization_name")) or "Organization",
        "organization_kind": _text(ref.get("organization_kind")) or "other",
        "related_org_eid": int(related_org_eid) if related_org_eid else None,
        "related_organization_key": _text((related_ref or {}).get("organization_key")),
        "related_organization_name": _text((related_ref or {}).get("organization_name")),
        "related_organization_kind": _text((related_ref or {}).get("organization_kind")),
        "stance": stance,
        "pressure_kind": pressure_kind,
        "confidence": max(0.0, min(1.0, _safe_float(row.get("confidence"), default=0.0))),
        "reason_tags": normalize_organization_diplomacy_tags(row.get("reason_tags", ())),
        "anchor_property_id": property_id,
        "anchor_scene_id": scene_id,
        "anchor_actor_eid": actor_eid,
        "visible": bool(row.get("visible", False)),
        "visible_cue": _text(row.get("visible_cue")),
        "source_event": _text(row.get("source_event")),
        "last_update_tick": _safe_int(row.get("last_update_tick"), default=tick),
        "expires_tick": expires_tick,
        "active": bool(active and has_anchor),
    }


def _prune_organization_diplomacy_state(sim, *, current_tick=None):
    state = _organization_diplomacy_state(sim)
    tick = _safe_int(getattr(sim, "tick", 0) if current_tick is None else current_tick, default=0)
    pairs = state.get("pairs", {})
    for key in tuple(pairs.keys()):
        row = _normalize_diplomacy_pair_row(sim, key, pairs.get(key), current_tick=tick, include_profiles=False)
        if row is None or not row.get("active"):
            pairs.pop(key, None)
            continue
        stored = dict(pairs.get(key) or {})
        history = list(row.get("recent_history", ()) or ())
        stored["recent_history"] = [dict(entry) for entry in history[-ORGANIZATION_DIPLOMACY_MAX_HISTORY:]]
        stored["reason_tags"] = list(row.get("reason_tags", ()) or ())
        pairs[key] = stored
    if len(pairs) > ORGANIZATION_DIPLOMACY_MAX_PAIRS:
        ranked = sorted(
            pairs.items(),
            key=lambda item: _safe_int((item[1] or {}).get("last_update_tick"), default=-10_000),
        )
        for key, _row in ranked[: len(pairs) - ORGANIZATION_DIPLOMACY_MAX_PAIRS]:
            pairs.pop(key, None)

    pressures = state.get("pressures", {})
    for key in tuple(pressures.keys()):
        row = _normalize_pressure_row(sim, key, pressures.get(key), current_tick=tick)
        if row is None or not row.get("active"):
            pressures.pop(key, None)
    if len(pressures) > ORGANIZATION_DIPLOMACY_MAX_PRESSURES:
        ranked = sorted(
            pressures.items(),
            key=lambda item: (
                _safe_float((item[1] or {}).get("confidence"), default=0.0),
                _safe_int((item[1] or {}).get("last_update_tick"), default=-10_000),
            ),
        )
        for key, _row in ranked[: len(pressures) - ORGANIZATION_DIPLOMACY_MAX_PRESSURES]:
            pressures.pop(key, None)

    cooldowns = state.get("cooldowns", {})
    for key, value in tuple(cooldowns.items()):
        if _safe_int(value, default=0) <= tick:
            cooldowns.pop(key, None)
    return state


def ensure_organization_diplomacy_state(sim):
    return _prune_organization_diplomacy_state(sim)


def record_organization_pressure(
    sim,
    *,
    organization_eid,
    pressure_kind,
    stance="neutral",
    reason_tags=(),
    related_org_eid=None,
    anchor_property_id=None,
    anchor_scene_id=None,
    anchor_actor_eid=None,
    visible=True,
    visible_cue="",
    confidence=0.5,
    source_event="",
    expires_tick=None,
    pressure_key=None,
):
    organization_eid = _safe_int(organization_eid, default=0)
    if organization_eid <= 0 or organization_profile(sim, organization_eid) is None:
        return None
    property_id = _text(anchor_property_id)
    scene_id = _text(anchor_scene_id)
    actor_eid = _safe_int(anchor_actor_eid, default=0) or None
    if not (property_id or scene_id or actor_eid):
        return None

    state = _prune_organization_diplomacy_state(sim)
    tick = _safe_int(getattr(sim, "tick", 0), default=0)
    stance = _normalize_diplomacy_stance(stance)
    pressure_kind = _text(pressure_kind).lower().replace(" ", "_") or stance
    reason_tags = normalize_organization_diplomacy_tags(reason_tags)
    if expires_tick is None:
        expires_tick = tick + ORGANIZATION_DIPLOMACY_DEFAULT_PRESSURE_TICKS
    expires_tick = _safe_int(expires_tick, default=0) or None
    related_org_eid = _safe_int(related_org_eid, default=0) or None
    if pressure_key is None:
        pressure_key = ":".join(
            _text(part)
            for part in (
                "org_pressure",
                organization_eid,
                related_org_eid or 0,
                pressure_kind,
                property_id or "-",
                scene_id or "-",
                actor_eid or 0,
            )
        )
    pressure_key = _text(pressure_key)
    row = {
        "pressure_key": pressure_key,
        "organization_eid": int(organization_eid),
        "related_org_eid": int(related_org_eid) if related_org_eid else None,
        "stance": stance,
        "pressure_kind": pressure_kind,
        "confidence": max(0.0, min(1.0, _safe_float(confidence, default=0.5))),
        "reason_tags": list(reason_tags),
        "anchor_property_id": property_id,
        "anchor_scene_id": scene_id,
        "anchor_actor_eid": actor_eid,
        "visible": bool(visible),
        "visible_cue": _text(visible_cue),
        "source_event": _text(source_event),
        "last_update_tick": tick,
        "expires_tick": expires_tick,
        "active": True,
    }
    state["pressures"][pressure_key] = row
    return _normalize_pressure_row(sim, pressure_key, row)


def _pressure_visible_cue_for_stance(stance, reason_tags=()):
    reason_tags = set(normalize_organization_diplomacy_tags(reason_tags))
    if stance == "sacred_conflict":
        if "flora_devotion" in reason_tags or "devotion_flora" in reason_tags:
            return "people are watching a plant or garden like it matters more than trade"
        if "animal_devotion" in reason_tags or "devotion_animal" in reason_tags:
            return "people are measuring the street by how it treats a particular animal"
        return "the visible friction feels devotional, not merely commercial"
    if stance == "hostile":
        return "uniforms, guards, or signage make the line feel unfriendly"
    if stance == "competitive":
        return "staff and regulars are reading the other side of the block carefully"
    if stance == "transactional":
        return "handoffs and service habits make the arrangement visible"
    if stance == "allied":
        return "the posture looks coordinated instead of merely neighborly"
    return "the frontage carries a quiet organizational read"


def record_organization_relationship(
    sim,
    *,
    org_a_eid,
    org_b_eid,
    stance,
    confidence=0.5,
    reason_tags=(),
    source_event="",
    anchor_property_id=None,
    anchor_scene_id=None,
    anchor_actor_eid=None,
    visible=False,
    visible_cue="",
    expires_tick=None,
    cooldown_ticks=0,
):
    org_a_eid = _safe_int(org_a_eid, default=0)
    org_b_eid = _safe_int(org_b_eid, default=0)
    if organization_profile(sim, org_a_eid) is None or organization_profile(sim, org_b_eid) is None:
        return None
    pair_key = _organization_pair_key(org_a_eid, org_b_eid)
    if not pair_key:
        return None

    state = _prune_organization_diplomacy_state(sim)
    tick = _safe_int(getattr(sim, "tick", 0), default=0)
    stance = _normalize_diplomacy_stance(stance)
    reason_tags = normalize_organization_diplomacy_tags(reason_tags)
    source_event = _text(source_event) or "organization_relationship"
    cooldown_key = ""
    cooldown_ticks = max(0, _safe_int(cooldown_ticks, default=0))
    if cooldown_ticks:
        cooldown_key = f"{pair_key}:{source_event}:{_text(anchor_property_id)}:{_text(anchor_scene_id)}:{','.join(reason_tags)}"
        if _safe_int(state.get("cooldowns", {}).get(cooldown_key), default=0) > tick:
            return organization_relationship_snapshot(sim, org_a_eid, org_b_eid)

    existing = _normalize_diplomacy_pair_row(
        sim,
        pair_key,
        state.get("pairs", {}).get(pair_key),
        current_tick=tick,
        include_profiles=False,
    )
    history = list((existing or {}).get("recent_history", ()) or ())
    previous_stance = _text((existing or {}).get("stance"))
    existing_reasons = set((existing or {}).get("reason_tags", ()) or ())
    merged_reasons = tuple(sorted(existing_reasons | set(reason_tags)))
    confidence = max(0.0, min(1.0, _safe_float(confidence, default=0.5)))
    if existing and previous_stance == stance:
        confidence = min(1.0, max(confidence, _safe_float(existing.get("confidence"), default=0.0) + 0.03))
    history.append({
        "tick": int(tick),
        "source_event": source_event,
        "stance": stance,
        "reason_tags": tuple(reason_tags),
        "anchor_property_id": _text(anchor_property_id),
        "anchor_scene_id": _text(anchor_scene_id),
        "anchor_actor_eid": _safe_int(anchor_actor_eid, default=0) or None,
    })
    row = {
        "pair_key": pair_key,
        "org_a_eid": min(int(org_a_eid), int(org_b_eid)),
        "org_b_eid": max(int(org_a_eid), int(org_b_eid)),
        "stance": stance,
        "confidence": confidence,
        "reason_tags": list(merged_reasons),
        "recent_history": [dict(entry) for entry in history[-ORGANIZATION_DIPLOMACY_MAX_HISTORY:]],
        "last_update_tick": int(tick),
        "expires_tick": _safe_int(expires_tick, default=0) or None,
        "active": True,
    }
    state["pairs"][pair_key] = row
    if cooldown_key:
        state["cooldowns"][cooldown_key] = tick + cooldown_ticks

    if visible and (_text(anchor_property_id) or _text(anchor_scene_id) or _safe_int(anchor_actor_eid, default=0)):
        cue = _text(visible_cue) or _pressure_visible_cue_for_stance(stance, reason_tags)
        record_organization_pressure(
            sim,
            organization_eid=row["org_a_eid"],
            related_org_eid=row["org_b_eid"],
            pressure_kind=f"diplomacy_{stance}",
            stance=stance,
            reason_tags=reason_tags,
            anchor_property_id=anchor_property_id,
            anchor_scene_id=anchor_scene_id,
            anchor_actor_eid=anchor_actor_eid,
            visible=True,
            visible_cue=cue,
            confidence=confidence,
            source_event=source_event,
            expires_tick=expires_tick,
            pressure_key=f"org_relationship:{pair_key}:{_text(anchor_property_id) or _text(anchor_scene_id) or _safe_int(anchor_actor_eid, default=0)}",
        )
    return organization_relationship_snapshot(sim, org_a_eid, org_b_eid)


def organization_relationship_snapshot(sim, org_a_eid, org_b_eid, *, include_inactive=False):
    state = _prune_organization_diplomacy_state(sim)
    pair_key = _organization_pair_key(org_a_eid, org_b_eid)
    if not pair_key:
        return None
    row = _normalize_diplomacy_pair_row(sim, pair_key, state.get("pairs", {}).get(pair_key))
    if row is None:
        return None
    if not include_inactive and not row.get("active"):
        return None
    return row


def organization_relationship_rows(sim, organization_eid=None, *, stance=None, active_only=True):
    state = _prune_organization_diplomacy_state(sim)
    organization_eid = _safe_int(organization_eid, default=0) or None
    stance = _normalize_diplomacy_stance(stance, default="") if stance else ""
    rows = []
    for key, raw in state.get("pairs", {}).items():
        row = _normalize_diplomacy_pair_row(sim, key, raw)
        if row is None:
            continue
        if active_only and not row.get("active"):
            continue
        if organization_eid and organization_eid not in {row.get("org_a_eid"), row.get("org_b_eid")}:
            continue
        if stance and row.get("stance") != stance:
            continue
        rows.append(row)
    rows.sort(
        key=lambda row: (
            _text(row.get("stance")),
            -_safe_float(row.get("confidence"), default=0.0),
            _safe_int(row.get("org_a_eid"), default=0),
            _safe_int(row.get("org_b_eid"), default=0),
        )
    )
    return tuple(rows)


def organization_pressure_rows(sim, *, property_id=None, scene_id=None, actor_eid=None, visible_only=True, active_only=True):
    state = _prune_organization_diplomacy_state(sim)
    property_id = _text(property_id)
    scene_id = _text(scene_id)
    actor_eid = _safe_int(actor_eid, default=0) or None
    rows = []
    for key, raw in state.get("pressures", {}).items():
        row = _normalize_pressure_row(sim, key, raw)
        if row is None:
            continue
        if active_only and not row.get("active"):
            continue
        if visible_only and not row.get("visible"):
            continue
        if property_id and row.get("anchor_property_id") != property_id:
            continue
        if scene_id and row.get("anchor_scene_id") != scene_id:
            continue
        if actor_eid and row.get("anchor_actor_eid") != actor_eid:
            continue
        rows.append(row)
    rows.sort(
        key=lambda row: (
            -_safe_float(row.get("confidence"), default=0.0),
            -_safe_int(row.get("last_update_tick"), default=0),
            _text(row.get("pressure_kind")),
        )
    )
    return tuple(rows)


def organization_pressure_for_property(sim, prop, *, min_confidence=0.2):
    if not isinstance(prop, dict):
        return None
    property_id = _text(prop.get("id"))
    if not property_id:
        return None
    for row in organization_pressure_rows(sim, property_id=property_id, visible_only=True, active_only=True):
        if _safe_float(row.get("confidence"), default=0.0) >= float(min_confidence):
            return row
    return None


def organization_pressure_summary(row):
    if not isinstance(row, dict):
        return None
    stance = _normalize_diplomacy_stance(row.get("stance"))
    title = ORGANIZATION_DIPLOMACY_PRESSURE_TITLES.get(stance, "Org Pressure")
    visible_cue = _text(row.get("visible_cue")) or _pressure_visible_cue_for_stance(stance, row.get("reason_tags", ()))
    summary = f"{visible_cue}"
    action = ORGANIZATION_DIPLOMACY_PRESSURE_ACTIONS.get(stance, "ask around, read the posture, or move on")
    return {
        "title": title,
        "summary": summary,
        "action": action,
        "stance": stance,
        "pressure_kind": _text(row.get("pressure_kind")),
        "confidence": max(0.0, min(1.0, _safe_float(row.get("confidence"), default=0.0))),
    }


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
    stance = ORGANIZATION_DIPLOMACY_RELATION_STANCES.get(relation_kind)
    if bool(active) and stance:
        record_organization_relationship(
            sim,
            org_a_eid=source_org_eid,
            org_b_eid=target_org_eid,
            stance=stance,
            confidence=0.48 if relation_kind in {"ally", "rival", "affiliates_with"} else 0.38,
            reason_tags=(f"relation:{relation_kind}",),
            source_event=f"relation:{relation_kind}",
            visible=False,
            cooldown_ticks=0,
        )
    _invalidate_organization_runtime_caches(sim)
    _hydrate_linked_branch_records_for_organization(sim, source_org_eid)
    if int(target_org_eid) != int(source_org_eid):
        _hydrate_linked_branch_records_for_organization(sim, target_org_eid)
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
    existing_profile = organization_profile(sim, existing) if existing is not None else None
    if existing is not None and existing_profile:
        ensure_organization(
            sim,
            organization_key=getattr(existing_profile, "key", None),
            parent_organization_key=parent_organization_key,
        )
        if not _profile_has_active_primary_operates_link(existing_profile, prop, existing):
            link_property_organization(sim, prop, organization_eid=existing, link_kind="operates", primary=True, active=True)
            existing_profile = organization_profile(sim, existing)
        sync_property_collective_affiliations(sim, prop)
        metadata["organization_name"] = organization_name(sim, existing, fallback=_organization_name_for_property(prop))
        metadata["organization_kind"] = _normalize_org_kind(
            getattr(existing_profile, "kind", ""),
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
    if property_id:
        return property_id == prop.get("id")

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
    _invalidate_organization_runtime_caches(sim)
    property_id = _text(site_property_id)
    prop = sim.properties.get(property_id) if property_id else None
    briefing_state = _organization_actor_briefing_state(sim)
    if not _organization_member_read_active(sim) and not bool(briefing_state.get("refreshing", False)):
        refresh_actor_branch_briefing(
            sim,
            actor_eid,
            prop=prop if isinstance(prop, dict) else None,
            reason="membership_update",
        )
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
        organization_eid = property_organization_eid(sim, prop, ensure=False)
        if organization_eid is None:
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
    if site_property_id:
        return site_property_id == _text(prop.get("id"))

    site_building_id = _text(membership.get("site_building_id"))
    metadata = _property_metadata(prop)
    building_ids = {
        _text(metadata.get("building_id")),
        _text(metadata.get("local_building_id")),
    }
    if site_building_id and site_building_id in building_ids:
        return True
    return False


def _property_org_members_impl(sim, prop):
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


def property_org_members(sim, prop):
    state = _organization_actor_briefing_state(sim)
    depth = max(0, _safe_int(state.get("member_read_depth"), default=0))
    state["member_read_depth"] = depth + 1
    try:
        return _property_org_members_impl(sim, prop)
    finally:
        current = max(0, _safe_int(state.get("member_read_depth"), default=1) - 1)
        if current > 0:
            state["member_read_depth"] = current
        else:
            state.pop("member_read_depth", None)
