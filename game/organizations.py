from game.components import Occupation, OrganizationAffiliations, OrganizationProfile


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


def _text(value):
    return str(value or "").strip()


def _property_metadata(prop):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _property_archetype(prop):
    return _text(_property_metadata(prop).get("archetype")).lower()


def _normalize_org_kind(value, default="business"):
    kind = _text(value).lower()
    if not kind:
        return default
    return kind.replace(" ", "_")


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


def _district_text(district, key):
    if not isinstance(district, dict):
        return ""
    return _text(district.get(key))


def seed_property_organization_defaults(prop, district=None):
    if not isinstance(prop, dict):
        return False

    metadata = _property_metadata(prop)
    if _text(metadata.get("organization_key")):
        return False

    archetype = _property_archetype(prop)
    owner_tag = _text(prop.get("owner_tag")).lower()
    if owner_tag not in PUBLIC_OWNER_TAGS:
        return False

    department = CIVIC_DEPARTMENT_BY_ARCHETYPE.get(archetype)
    if not department:
        return False

    scope_name = _district_text(district, "settlement_name") or _district_text(district, "region_name") or "Metro"
    scope_slug = _slug(scope_name) or "metro"
    department_key, department_name = department

    metadata["organization_key"] = f"{department_key}:{scope_slug}"
    if not _text(metadata.get("organization_name")):
        metadata["organization_name"] = f"{scope_name} {department_name}".strip()
    if not _text(metadata.get("organization_kind")):
        metadata["organization_kind"] = "civic"
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
    return sim.ecs.get(OrganizationProfile).get(int(organization_eid))


def organization_name(sim, organization_eid, fallback=""):
    profile = organization_profile(sim, organization_eid)
    if profile and _text(getattr(profile, "name", "")):
        return _text(profile.name)
    return _text(fallback)


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


def ensure_property_organization(sim, prop):
    if not property_supports_organization(prop):
        return None

    metadata = _property_metadata(prop)
    existing = property_organization_eid(sim, prop, ensure=False)
    if existing is not None:
        profile = organization_profile(sim, existing)
        if profile:
            profile.site_property_ids.add(_text(prop.get("id")))
            building_id = _text(metadata.get("building_id"))
            if building_id:
                profile.site_building_ids.add(building_id)
            metadata["organization_name"] = _text(profile.name)
            metadata["organization_kind"] = _normalize_org_kind(profile.kind, default="business")
            return existing

    key = _organization_key_for_property(prop)
    if not key:
        return None

    index = _organization_index(sim)
    organization_eid = index.get(key)
    profile = organization_profile(sim, organization_eid) if organization_eid is not None else None
    if not profile:
        organization_eid = sim.ecs.create()
        profile = OrganizationProfile(
            name=_organization_name_for_property(prop),
            kind=_organization_kind_for_property(prop),
            key=key,
            tags=_organization_tags_for_property(prop, _organization_kind_for_property(prop)),
        )
        sim.ecs.add(organization_eid, profile)
        index[key] = organization_eid

    profile.site_property_ids.add(_text(prop.get("id")))
    building_id = _text(metadata.get("building_id"))
    if building_id:
        profile.site_building_ids.add(building_id)

    metadata["organization_eid"] = int(organization_eid)
    metadata["organization_key"] = _text(getattr(profile, "key", key)) or key
    metadata["organization_name"] = _text(getattr(profile, "name", "")) or _organization_name_for_property(prop)
    metadata["organization_kind"] = _normalize_org_kind(getattr(profile, "kind", ""), default="business")
    return organization_eid


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
            return "owner" if configured == "owner" else configured

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

    if organization_eid is None:
        return None

    role = _authority_role_from_workplace(
        workplace,
        career=getattr(occupation, "career", ""),
        owner_eid=prop.get("owner_eid") if isinstance(prop, dict) else None,
        actor_eid=actor_eid,
    )

    affiliations = _ensure_actor_affiliations(sim, actor_eid)
    profile = organization_profile(sim, organization_eid)
    site_building_id = _text(workplace.get("building_id"))
    membership = affiliations.memberships.get(int(organization_eid))
    memberships_kind = "ownership" if role == "owner" else "employment"
    affiliations.assign(
        organization_eid=int(organization_eid),
        role=role,
        kind=memberships_kind,
        site_property_id=_text(property_id),
        site_building_id=site_building_id,
        title=_text(getattr(occupation, "career", "")),
        active=True,
    )
    if profile:
        profile.member_eids.add(int(actor_eid))
        workplace["organization_eid"] = int(organization_eid)
        workplace["organization_key"] = _text(profile.key)
        workplace["organization_kind"] = _normalize_org_kind(profile.kind, default="business")
        workplace["organization_name"] = _text(profile.name)
    elif membership:
        workplace["organization_eid"] = int(organization_eid)

    return organization_eid


def _membership_targets_property(prop, organization_eid, membership):
    if not isinstance(membership, dict):
        return False
    try:
        member_org_eid = int(membership.get("organization_eid"))
    except (TypeError, ValueError):
        return False
    if int(organization_eid) != member_org_eid:
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
            occupation = occupations.get(actor_eid)
            candidates[int(actor_eid)] = {
                "eid": int(actor_eid),
                "role": _text(membership.get("role", "member")).lower() or "member",
                "kind": _text(membership.get("kind", "member")).lower() or "member",
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
        candidates[int(actor_eid)] = {
            "eid": int(actor_eid),
            "role": _authority_role_from_workplace(
                workplace,
                career=getattr(occupation, "career", ""),
                owner_eid=prop.get("owner_eid"),
                actor_eid=actor_eid,
            ),
            "kind": "employment",
            "occupation": occupation,
            "organization_eid": int(organization_eid) if organization_eid is not None else None,
            "source": "workplace",
        }

    ordered = sorted(
        candidates.values(),
        key=lambda row: (
            0 if row["role"] == "owner" else 1 if row["role"] == "manager" else 2,
            row["eid"],
        ),
    )
    return tuple(ordered)
