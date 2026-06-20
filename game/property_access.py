import random
from dataclasses import dataclass

from game.components import ContactLedger, Inventory, NPCSocial, NPCRoutine, Occupation, PlayerAssets, PropertyPortfolio
from game.justice_runtime import custody_release_grace_active as _custody_release_grace_active
from game.organizations import (
    effective_org_access_posture,
    occupation_targets_property,
    property_org_members,
    workplace_targets_property,
)
from game.property_keys import inventory_matching_property_credential, property_lock_state


DEFAULT_START_HOUR = 9
DEFAULT_TICKS_PER_HOUR = 600
ALWAYS_OPEN_SITE_SERVICES = {"rest", "shelter"}

STOREFRONT_ARCHETYPE_HINTS = {
    "accessory_shop",
    "bait_shop",
    "barbershop",
    "bottom_shop",
    "breaker_yard",
    "casino",
    "clothing_superstore",
    "corner_store",
    "restaurant",
    "pawn_shop",
    "backroom_clinic",
    "nightclub",
    "arcade",
    "bar",
    "auto_garage",
    "bookshop",
    "daycare",
    "flophouse",
    "gallery",
    "hardware_store",
    "laundromat",
    "karaoke_box",
    "pharmacy",
    "pool_hall",
    "hotel",
    "chop_shop",
    "junk_market",
    "outfitter",
    "roadhouse",
    "soup_kitchen",
    "surplus_store",
    "service_station",
    "street_kitchen",
    "tavern",
    "theater",
    "thrift_store",
    "tool_depot",
    "music_venue",
    "gaming_hall",
    "dock_shack",
    "drydock_yard",
    "dress_shop",
    "hair_studio",
    "headwear_shop",
    "herbalist_camp",
    "jewelry_shop",
    "makeup_counter",
    "outerwear_shop",
    "salon",
    "salvage_camp",
    "shoe_shop",
    "tattoo_parlor",
    "top_shop",
    "truck_stop",
    "employment_agency",
    "bounty_office",
}

FINANCE_SERVICE_FALLBACKS = {
    "bank": ("banking", "insurance"),
    "brokerage": ("banking", "insurance"),
    "office": ("insurance",),
    "tower": ("insurance",),
    "pawn_shop": ("insurance",),
    "backroom_clinic": ("insurance",),
}

RESTRICTED_ARCHETYPES = {
    "armory",
    "barracks",
    "checkpoint",
    "command_center",
    "data_center",
    "jail",
    "prison",
    "server_hub",
    "supply_bunker",
}

JUSTICE_CUSTODY_ARCHETYPES = {
    "courthouse",
    "jail",
    "prison",
}

PUBLIC_HOURS_BY_ARCHETYPE = {
    "accessory_shop": (10, 20),
    "arcade": (11, 23),
    "auto_garage": (8, 19),
    "bank": (9, 17),
    "bar": (16, 2),
    "barbershop": (9, 19),
    "backroom_clinic": (10, 20),
    "bookshop": (9, 20),
    "bottom_shop": (10, 20),
    "bounty_office": (9, 18),
    "breaker_yard": (8, 18),
    "brokerage": (8, 18),
    "casino": (12, 4),
    "clothing_superstore": (9, 21),
    "corner_store": (6, 23),
    "contractor_office": (7, 19),
    "courier_office": (7, 19),
    "daycare": (7, 18),
    "dress_shop": (10, 20),
    "drydock_yard": (7, 18),
    "employment_agency": (8, 18),
    "flophouse": (0, 24),
    "gallery": (11, 20),
    "gaming_hall": (12, 3),
    "hair_studio": (9, 20),
    "hardware_store": (8, 19),
    "headwear_shop": (10, 20),
    "hotel": (0, 24),
    "jewelry_shop": (10, 20),
    "junk_market": (9, 18),
    "karaoke_box": (17, 2),
    "laundromat": (6, 22),
    "makeup_counter": (10, 21),
    "metro_exchange": (5, 24),
    "music_venue": (18, 2),
    "nightclub": (18, 3),
    "outerwear_shop": (10, 20),
    "outfitter": (8, 19),
    "pawn_shop": (10, 19),
    "pharmacy": (8, 21),
    "pool_hall": (12, 2),
    "recruitment_office": (8, 18),
    "relay_post": (6, 22),
    "restaurant": (7, 22),
    "roadhouse": (6, 23),
    "salon": (9, 20),
    "salvage_camp": (8, 18),
    "service_station": (5, 24),
    "shoe_shop": (10, 20),
    "soup_kitchen": (10, 19),
    "street_kitchen": (11, 23),
    "surplus_store": (9, 18),
    "tattoo_parlor": (11, 22),
    "tavern": (14, 2),
    "theater": (14, 23),
    "thrift_store": (9, 19),
    "truck_stop": (0, 24),
    "tool_depot": (7, 19),
    "top_shop": (10, 20),
    "work_shed": (8, 18),
    "pump_house": (8, 17),
    "net_house": (7, 18),
    "dock_shack": (6, 19),
    "ferry_post": (5, 20),
    "tide_station": (6, 18),
}

NEUTRAL_STANDING_REASONS = {"", "none", "open_business", "public_space"}
AUTO_CONTROLLER_OWNER_TAGS = {"", "public", "city", "community", "neutral", "none", "unowned"}
ALWAYS_PUBLIC_ARCHETYPES = {"metro_exchange"}
COMMON_AREA_ROOM_KINDS = frozenset({
    "aisle",
    "entry",
    "foyer",
    "lobby",
    "hall",
    "hallway",
    "corridor",
    "concourse",
    "commons",
    "stair",
    "stairs",
    "stairwell",
    "elevator",
    "elevator_lobby",
    "service_corridor",
    "service_hall",
    "market_aisle",
    "market_hall",
    "shared_yard",
    "utility_corridor",
    "service_basement",
    "maintenance_tunnel",
    "yard",
    "drain_junction",
    "platform",
})
BADGE_CONTROLLER_ARCHETYPES = {
    "armory",
    "bank",
    "barracks",
    "brokerage",
    "checkpoint",
    "courthouse",
    "hotel",
    "jail",
    "lab",
    "media_lab",
    "office",
    "pharmacy",
    "prison",
    "tower",
}
BIOMETRIC_CONTROLLER_ARCHETYPES = {
    "command_center",
    "data_center",
    "server_hub",
}
MANAGER_CAREER_KEYWORDS = {
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
VALID_CREDENTIAL_MODES = {"mechanical_key", "badge", "biometric"}
VALID_STOREFRONT_SERVICE_MODES = {"automated", "staffed"}
CONTROLLER_INTRUSION_PROFILES = {
    "badge_spoof": {
        "label": "badge spoof",
        "credential_mode": "badge",
        "security_tier_delta": -1,
        "required_tier_delta": -1,
        "open_override": True,
        "grants_actor_access": True,
        "standing": 0.82,
        "standing_reason": "spoofed_badge",
    },
    "biometric_jam": {
        "label": "biometric jam",
        "credential_mode": "biometric",
        "security_tier_delta": -2,
        "required_tier_delta": -1,
        "open_override": True,
        "grants_actor_access": False,
        "standing": 0.0,
        "standing_reason": "",
    },
    "schedule_latch": {
        "label": "schedule latch",
        "credential_mode": "mechanical_key",
        "security_tier_delta": -1,
        "required_tier_delta": -1,
        "open_override": True,
        "grants_actor_access": False,
        "standing": 0.0,
        "standing_reason": "",
    },
    "relay_latch": {
        "label": "relay latch",
        "credential_mode": "mechanical_key",
        "security_tier_delta": -1,
        "required_tier_delta": -1,
        "open_override": True,
        "grants_actor_access": False,
        "standing": 0.0,
        "standing_reason": "",
    },
}

DEFAULT_SITE_SERVICES_BY_ARCHETYPE = {
    "barbershop": ("appearance_style",),
    "casino": ("slots", "video_poker", "keno", "roulette", "craps", "baccarat", "three_card_poker", "casino_holdem", "plinko", "twenty_one"),
    "contractor_office": ("building_repair", "business_remodel"),
    "courier_office": ("courier_jobs",),
    "dock_shack": ("shuttle_transit", "ferry_transit"),
    "employment_agency": ("agency_jobs",),
    "ferry_post": ("intel", "ferry_transit"),
    "flophouse": ("rest",),
    "gaming_hall": ("video_poker", "keno", "roulette", "craps", "baccarat", "three_card_poker"),
    "hair_studio": ("appearance_style",),
    "hotel": ("rest",),
    "makeup_counter": ("appearance_style",),
    "metro_exchange": ("rail_transit", "bus_transit"),
    "relay_post": ("bus_transit", "shuttle_transit"),
    "recruitment_office": ("agency_jobs",),
    "roadhouse": ("shuttle_transit",),
    "salon": ("appearance_style",),
    "bounty_office": ("bounty_jobs",),
    "service_station": ("fuel", "repair", "vending"),
    "tavern": ("intel",),
    "tide_station": ("intel", "ferry_transit"),
    "truck_stop": ("bus_transit", "shuttle_transit"),
}
OPTIONAL_SITE_SERVICES_BY_ARCHETYPE = {
    "tavern": {
        "chance": 0.34,
        "bundles": (
            (("video_poker",), 7),
            (("keno",), 5),
            (("slots",), 4),
            (("video_poker", "keno"), 2),
            (("slots", "video_poker"), 1),
        ),
    },
    "corner_store": {
        "chance": 0.18,
        "bundles": (
            (("keno",), 7),
            (("slots",), 5),
            (("video_poker",), 2),
        ),
    },
    "pawn_shop": {
        "chance": 0.14,
        "bundles": (
            (("video_poker",), 6),
            (("slots",), 3),
            (("keno",), 2),
        ),
    },
    "restaurant": {
        "chance": 0.06,
        "bundles": (
            (("keno",), 4),
            (("video_poker",), 3),
            (("slots",), 1),
        ),
    },
    "salvage_camp": {
        "chance": 0.58,
        "bundles": (
            (("repair", "intel"), 8),
            (("repair",), 6),
            (("vehicle_fetch", "repair"), 3),
            (("building_repair", "intel"), 2),
        ),
    },
    "breaker_yard": {
        "chance": 0.52,
        "bundles": (
            (("repair",), 7),
            (("vehicle_fetch", "repair"), 4),
            (("intel", "repair"), 3),
            (("building_repair",), 2),
        ),
    },
    "drydock_yard": {
        "chance": 0.46,
        "bundles": (
            (("repair", "intel"), 6),
            (("repair",), 5),
            (("building_repair",), 2),
        ),
    },
    "work_shed": {
        "chance": 0.34,
        "bundles": (
            (("repair",), 6),
            (("building_repair",), 3),
            (("intel",), 2),
        ),
    },
    "pump_house": {
        "chance": 0.28,
        "bundles": (
            (("intel",), 6),
            (("repair",), 3),
            (("building_repair",), 2),
        ),
    },
    "net_house": {
        "chance": 0.32,
        "bundles": (
            (("intel",), 6),
            (("vending",), 3),
            (("repair",), 2),
        ),
    },
}
RARE_UNRELATED_BUSINESS_SERVICE_CHANCE = 0.015
RARE_UNRELATED_BUSINESS_SERVICE_WEIGHTS = (
    ("video_poker", 8),
    ("keno", 7),
    ("slots", 5),
    ("intel", 5),
    ("rest", 3),
    ("repair", 3),
    ("fuel", 2),
    ("vehicle_fetch", 2),
)
_RARE_UNRELATED_SERVICE_EXCLUDED_ARCHETYPES = frozenset({
    "casino",
    "dock_shack",
    "ferry_post",
    "gaming_hall",
    "metro_exchange",
    "relay_post",
    "tide_station",
    "truck_stop",
})


def _clamp_unit(value, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    return max(0.0, min(1.0, number))


def _int_or_default(value, default):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _dedupe_service_ids(services):
    ordered = []
    seen = set()
    for service in tuple(services or ()):
        key = str(service).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return tuple(ordered)


def _property_metadata(prop):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _clean_key(value):
    return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")


def _property_id(prop):
    return str((prop or {}).get("id", "") or "").strip() if isinstance(prop, dict) else ""


def _property_building_id(prop):
    metadata = _property_metadata(prop)
    return str(metadata.get("building_id", "") or "").strip()


def _normalize_key_set(raw):
    if isinstance(raw, str):
        return frozenset({_clean_key(raw)} if _clean_key(raw) else ())
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(_clean_key(value) for value in raw if _clean_key(value))


def _shape_cells_2d(metadata, key):
    if not isinstance(metadata, dict):
        return frozenset()
    raw = metadata.get(key)
    if not isinstance(raw, (list, tuple, set, frozenset)):
        return frozenset()

    cells = set()
    for cell in raw:
        if isinstance(cell, dict):
            try:
                cells.add((int(cell.get("x")), int(cell.get("y"))))
            except (TypeError, ValueError):
                continue
        elif isinstance(cell, (list, tuple)) and len(cell) >= 2:
            try:
                cells.add((int(cell[0]), int(cell[1])))
            except (TypeError, ValueError):
                continue
    return frozenset(cells)


def _party_rep_proxy_actor(sim, actor_eid):
    if sim is None or actor_eid is None:
        return actor_eid
    contractors = getattr(sim, "contractors", {})
    if not isinstance(contractors, dict):
        return actor_eid
    tick = int(getattr(sim, "tick", 0))
    for key, rec in contractors.items():
        try:
            same_actor = int(key) == int(actor_eid)
        except (TypeError, ValueError):
            same_actor = key == actor_eid
        if not same_actor or not isinstance(rec, dict):
            continue
        if int(rec.get("until", 0) or 0) <= tick:
            continue
        job = str(rec.get("job", "") or "").strip().lower()
        if job not in {"backup", "party"}:
            continue
        return rec.get("ally_eid", getattr(sim, "player_eid", actor_eid))
    return actor_eid


def _property_archetype(prop):
    return str(_property_metadata(prop).get("archetype", "") or "").strip().lower()


def _player_business_customer_policy(prop):
    metadata = _property_metadata(prop)
    state = metadata.get("player_business")
    if not isinstance(state, dict):
        return "public"
    clean = str(state.get("customer_policy", "") or "").strip().lower().replace("-", "_").replace(" ", "_")
    if clean not in {"public", "staff_only", "closed"}:
        return "public"
    return clean


def finance_services_for_property(prop):
    metadata = _property_metadata(prop)
    configured = metadata.get("finance_services", [])
    services = []
    if isinstance(configured, (list, tuple, set)):
        services = [str(service).strip().lower() for service in configured if str(service).strip()]
    elif isinstance(configured, str) and configured.strip():
        services = [configured.strip().lower()]

    if services:
        return tuple(sorted(set(services)))

    archetype = str(metadata.get("archetype", "") or "").strip().lower()
    if archetype and archetype in FINANCE_SERVICE_FALLBACKS:
        return tuple(FINANCE_SERVICE_FALLBACKS[archetype])
    return ()


def _optional_site_service_seed_token(prop):
    metadata = _property_metadata(prop)
    configured = str(metadata.get("site_service_seed_token", "") or "").strip()
    if configured:
        return configured

    parts = []
    building_id = str(metadata.get("building_id", "") or "").strip()
    if building_id:
        parts.append(building_id)

    local_building_id = str(metadata.get("local_building_id", "") or "").strip()
    chunk = metadata.get("chunk")
    if local_building_id and isinstance(chunk, (list, tuple)) and len(chunk) >= 2:
        parts.append(f"{int(chunk[0])}:{int(chunk[1])}:building:{local_building_id}")

    site_kind = str(metadata.get("site_kind", "") or "").strip().lower()
    site_id = str(metadata.get("site_id", "") or "").strip()
    if site_kind and site_id and isinstance(chunk, (list, tuple)) and len(chunk) >= 2:
        parts.append(f"{int(chunk[0])}:{int(chunk[1])}:site:{site_kind}:{site_id}")

    prop_id = str(prop.get("id", "") or "").strip()
    if prop_id:
        parts.append(prop_id)

    name = str(prop.get("name", "") or "").strip()
    if name:
        parts.append(name)

    try:
        x = int(prop.get("x"))
        y = int(prop.get("y"))
        z = int(prop.get("z", 0))
        parts.append(f"{x}:{y}:{z}")
    except (TypeError, ValueError):
        pass

    return "|".join(parts)


def _roll_optional_site_services(archetype, *, seed_token=""):
    key = str(archetype or "").strip().lower()
    if not key or not str(seed_token).strip():
        return ()

    profile = OPTIONAL_SITE_SERVICES_BY_ARCHETYPE.get(key)
    if not isinstance(profile, dict):
        return ()

    rng = random.Random(f"optional-site-services:{key}:{seed_token}")
    chance = _clamp_unit(profile.get("chance", 0.0))
    if chance <= 0.0 or rng.random() >= chance:
        return ()

    bundles = []
    total_weight = 0
    for bundle, weight in tuple(profile.get("bundles", ()) or ()):
        clean_bundle = _dedupe_service_ids(bundle)
        try:
            clean_weight = int(weight)
        except (TypeError, ValueError):
            continue
        if not clean_bundle or clean_weight <= 0:
            continue
        bundles.append((clean_bundle, clean_weight))
        total_weight += clean_weight
    if total_weight <= 0:
        return ()

    pick = rng.randrange(total_weight)
    cursor = 0
    for bundle, weight in bundles:
        cursor += weight
        if pick < cursor:
            return bundle
    return bundles[-1][0]


def _eligible_for_rare_unrelated_site_service(archetype):
    key = str(archetype or "").strip().lower()
    if not key or key in _RARE_UNRELATED_SERVICE_EXCLUDED_ARCHETYPES:
        return False
    return key in STOREFRONT_ARCHETYPE_HINTS or key in FINANCE_SERVICE_FALLBACKS


def _roll_rare_unrelated_site_service(archetype, *, seed_token="", existing=()):
    key = str(archetype or "").strip().lower()
    if not _eligible_for_rare_unrelated_site_service(key) or not str(seed_token).strip():
        return ()

    rng = random.Random(f"rare-unrelated-site-service:{key}:{seed_token}")
    if rng.random() >= RARE_UNRELATED_BUSINESS_SERVICE_CHANCE:
        return ()

    blocked = set(_dedupe_service_ids(existing))
    options = []
    total_weight = 0
    for service, weight in RARE_UNRELATED_BUSINESS_SERVICE_WEIGHTS:
        clean_service = str(service).strip().lower()
        if not clean_service or clean_service in blocked:
            continue
        try:
            clean_weight = int(weight)
        except (TypeError, ValueError):
            continue
        if clean_weight <= 0:
            continue
        options.append((clean_service, clean_weight))
        total_weight += clean_weight
    if total_weight <= 0:
        return ()

    pick = rng.randrange(total_weight)
    cursor = 0
    for service, weight in options:
        cursor += weight
        if pick < cursor:
            return (service,)
    return (options[-1][0],)


def default_site_services_for_archetype(archetype, *, seed_token=""):
    key = str(archetype or "").strip().lower()
    base = list(DEFAULT_SITE_SERVICES_BY_ARCHETYPE.get(key, ()))
    if str(seed_token).strip():
        base.extend(_roll_optional_site_services(key, seed_token=seed_token))
        base.extend(_roll_rare_unrelated_site_service(key, seed_token=seed_token, existing=base))
    return _dedupe_service_ids(base)


def site_services_for_property(prop):
    metadata = _property_metadata(prop)
    configured = metadata.get("site_services", [])
    services = []
    if isinstance(configured, (list, tuple, set)):
        services = [str(service).strip().lower() for service in configured if str(service).strip()]
    elif isinstance(configured, str) and configured.strip():
        services = [configured.strip().lower()]

    if not services:
        services = list(default_site_services_for_archetype(
            metadata.get("archetype"),
            seed_token=_optional_site_service_seed_token(prop),
        ))

    return _dedupe_service_ids(services)


def _property_offers_lodging_or_shelter(prop):
    services = {
        str(service).strip().lower()
        for service in site_services_for_property(prop)
        if str(service).strip()
    }
    return bool(services.intersection(ALWAYS_OPEN_SITE_SERVICES))


def property_is_storefront(prop):
    metadata = _property_metadata(prop)
    if bool(metadata.get("is_storefront")):
        return True

    archetype = str(metadata.get("archetype", "") or "").strip().lower()
    return archetype in STOREFRONT_ARCHETYPE_HINTS


def storefront_service_mode(prop):
    if not property_is_storefront(prop):
        return ""

    metadata = _property_metadata(prop)
    configured = str(metadata.get("storefront_service_mode", "") or "").strip().lower()
    if configured in VALID_STOREFRONT_SERVICE_MODES:
        return configured
    return "staffed"


def property_is_public(prop):
    metadata = _property_metadata(prop)
    if bool(metadata.get("public")):
        return True
    if _property_archetype(prop) in ALWAYS_PUBLIC_ARCHETYPES:
        return True

    owner_tag = str(prop.get("owner_tag", "") or "").strip().lower()
    return owner_tag == "public"


def property_access_level(prop):
    archetype = _property_archetype(prop)
    if archetype in RESTRICTED_ARCHETYPES:
        return "restricted"
    if property_is_public(prop):
        return "public"
    if _property_offers_lodging_or_shelter(prop):
        return "public"
    if property_is_storefront(prop) or finance_services_for_property(prop):
        return "public"
    return "protected"


def _property_ids_at_position(sim, x, y, z):
    if sim is None:
        return ()
    try:
        key = (int(x), int(y), int(z))
    except (TypeError, ValueError):
        return ()

    matched = []
    seen = set()
    for attr in ("property_anchor_index", "property_cover_index"):
        index = getattr(sim, attr, {})
        if not isinstance(index, dict):
            continue
        for raw_id in tuple(index.get(key, ()) or ()):
            property_id = str(raw_id or "").strip()
            if not property_id or property_id in seen:
                continue
            seen.add(property_id)
            matched.append(property_id)

    orderer = getattr(sim, "_ordered_property_ids", None)
    if callable(orderer):
        try:
            return tuple(orderer(matched))
        except Exception:
            return tuple(matched)
    return tuple(matched)


def _structure_context_for_position(sim, x, y, z):
    structure = None
    if sim is not None and hasattr(sim, "structure_at"):
        try:
            structure = sim.structure_at(int(x), int(y), int(z))
        except (TypeError, ValueError):
            structure = None
    structure = structure if isinstance(structure, dict) else {}
    building_id = str(structure.get("building_id", "") or "").strip()
    room_kind = _clean_key(structure.get("room_kind", ""))
    common_area_kind = _clean_key(structure.get("common_area_kind", ""))
    if not common_area_kind and room_kind in COMMON_AREA_ROOM_KINDS:
        common_area_kind = room_kind
    return structure, building_id, room_kind, common_area_kind


def _common_area_kind_for_property(prop, *, room_kind="", common_area_kind=""):
    metadata = _property_metadata(prop)
    room_kind = _clean_key(room_kind)
    common_area_kind = _clean_key(common_area_kind)

    configured_rooms = set()
    for key in ("common_area_room_kinds", "common_room_kinds", "shared_area_room_kinds"):
        configured_rooms.update(_normalize_key_set(metadata.get(key)))
    if room_kind and room_kind in configured_rooms:
        return common_area_kind or room_kind

    configured_kind = _clean_key(metadata.get("common_area_kind"))
    if configured_kind and (not common_area_kind or configured_kind == common_area_kind):
        return configured_kind
    configured_kinds = set()
    for key in ("common_area_kinds", "shared_area_kinds"):
        configured_kinds.update(_normalize_key_set(metadata.get(key)))
    if common_area_kind and common_area_kind in configured_kinds:
        return common_area_kind
    if room_kind and room_kind in configured_kinds:
        return room_kind

    return ""


def _looks_like_property_interest_spec(row):
    if not isinstance(row, dict):
        return False
    keys = {
        "property_id",
        "property_ids",
        "target_property_id",
        "target_property_ids",
        "source_property_id",
        "interest_kind",
        "authority_reason",
        "reason",
        "room_kind",
        "room_kinds",
        "common_area_kind",
        "common_area_kinds",
        "bounds",
        "cells",
    }
    return any(key in row for key in keys)


def _iter_shared_area_interest_specs(prop):
    metadata = _property_metadata(prop)
    raw = metadata.get("shared_area_interests")
    if not raw:
        return ()

    specs = []
    if isinstance(raw, dict):
        if _looks_like_property_interest_spec(raw):
            specs.append(dict(raw))
        else:
            for area_key, value in raw.items():
                area_kind = _clean_key(area_key)
                if isinstance(value, dict):
                    rows = [value] if _looks_like_property_interest_spec(value) else tuple(value.values())
                elif isinstance(value, (list, tuple, set, frozenset)):
                    rows = tuple(value)
                elif value:
                    rows = ({},)
                else:
                    rows = ()
                for row in rows:
                    spec = dict(row) if isinstance(row, dict) else {}
                    if area_kind and not (
                        spec.get("common_area_kind")
                        or spec.get("common_area_kinds")
                        or spec.get("room_kind")
                        or spec.get("room_kinds")
                    ):
                        spec["common_area_kind"] = area_kind
                    specs.append(spec)
    elif isinstance(raw, (list, tuple, set, frozenset)):
        for row in raw:
            if isinstance(row, dict):
                specs.append(dict(row))

    return tuple(specs)


def _interest_cells_match(raw_cells, x, y, z):
    if not isinstance(raw_cells, (list, tuple, set, frozenset)):
        return True
    for cell in raw_cells:
        try:
            if isinstance(cell, dict):
                cx = int(cell.get("x"))
                cy = int(cell.get("y"))
                cz = int(cell.get("z", z))
            elif isinstance(cell, (list, tuple)) and len(cell) >= 2:
                cx = int(cell[0])
                cy = int(cell[1])
                cz = int(cell[2]) if len(cell) >= 3 else int(z)
            else:
                continue
        except (TypeError, ValueError):
            continue
        if (cx, cy, cz) == (int(x), int(y), int(z)):
            return True
    return False


def _interest_bounds_match(raw_bounds, x, y, z):
    if not isinstance(raw_bounds, dict):
        return True
    try:
        left = int(raw_bounds.get("left", raw_bounds.get("x1", x)))
        right = int(raw_bounds.get("right", raw_bounds.get("x2", x)))
        top = int(raw_bounds.get("top", raw_bounds.get("y1", y)))
        bottom = int(raw_bounds.get("bottom", raw_bounds.get("y2", y)))
        min_z = int(raw_bounds.get("min_z", raw_bounds.get("z", z)))
        max_z = int(raw_bounds.get("max_z", raw_bounds.get("z", z)))
    except (TypeError, ValueError):
        return False
    if left > right:
        left, right = right, left
    if top > bottom:
        top, bottom = bottom, top
    if min_z > max_z:
        min_z, max_z = max_z, min_z
    return left <= int(x) <= right and top <= int(y) <= bottom and min_z <= int(z) <= max_z


def _shared_area_interest_matches(spec, *, x, y, z, building_id="", room_kind="", common_area_kind="", source_prop=None):
    if not isinstance(spec, dict):
        return False

    spec_building = str(spec.get("building_id", "") or spec.get("target_building_id", "") or "").strip()
    source_building = _property_building_id(source_prop)
    if spec_building and spec_building != str(building_id or "").strip():
        return False
    if not spec_building and source_building and building_id and source_building != building_id:
        return False

    room_kinds = set()
    room_kinds.update(_normalize_key_set(spec.get("room_kind")))
    room_kinds.update(_normalize_key_set(spec.get("room_kinds")))
    if room_kinds and _clean_key(room_kind) not in room_kinds:
        return False

    area_kinds = set()
    area_kinds.update(_normalize_key_set(spec.get("common_area_kind")))
    area_kinds.update(_normalize_key_set(spec.get("common_area_kinds")))
    area_kinds.update(_normalize_key_set(spec.get("area_kind")))
    area_kinds.update(_normalize_key_set(spec.get("area_kinds")))
    if area_kinds and _clean_key(common_area_kind) not in area_kinds and _clean_key(room_kind) not in area_kinds:
        return False

    if not _interest_cells_match(spec.get("cells"), x, y, z):
        return False
    if not _interest_bounds_match(spec.get("bounds"), x, y, z):
        return False

    has_location_filter = bool(room_kinds or area_kinds or spec.get("cells") or spec.get("bounds") or spec_building)
    return has_location_filter or bool(common_area_kind)


def _coerce_bool(value, default=True):
    if value is None:
        return bool(default)
    if isinstance(value, str):
        clean = value.strip().lower()
        if clean in {"1", "true", "yes", "y", "on"}:
            return True
        if clean in {"0", "false", "no", "n", "off"}:
            return False
    return bool(value)


def _interest_property_ids_from_spec(spec, source_prop):
    ids = []
    for key in ("property_id", "target_property_id", "source_property_id"):
        property_id = str((spec or {}).get(key, "") or "").strip() if isinstance(spec, dict) else ""
        if property_id:
            ids.append(property_id)
    for key in ("property_ids", "target_property_ids"):
        raw = (spec or {}).get(key) if isinstance(spec, dict) else None
        if isinstance(raw, str):
            raw_values = (raw,)
        elif isinstance(raw, (list, tuple, set, frozenset)):
            raw_values = tuple(raw)
        else:
            raw_values = ()
        for value in raw_values:
            property_id = str(value or "").strip()
            if property_id:
                ids.append(property_id)
    if not ids:
        property_id = _property_id(source_prop)
        if property_id:
            ids.append(property_id)
    return tuple(dict.fromkeys(ids))


def _interest_row(property_id, *, source_property_id="", spec=None, common_area_kind="", implicit=False):
    spec = spec if isinstance(spec, dict) else {}
    try:
        standing_bonus = float(spec.get("standing_bonus", 0.12 if implicit else 0.08) or 0.0)
    except (TypeError, ValueError):
        standing_bonus = 0.12 if implicit else 0.08
    reason = _clean_key(spec.get("authority_reason") or spec.get("reason"))
    return {
        "property_id": str(property_id or "").strip(),
        "interest_kind": _clean_key(spec.get("interest_kind")) or ("implicit_common_area" if implicit else "shared_common_area"),
        "authority_reason": reason or "shared_interest",
        "standing_bonus": max(0.0, min(1.0, standing_bonus)),
        "protects": _coerce_bool(spec.get("protects"), True),
        "warns": _coerce_bool(spec.get("warns"), True),
        "source_property_id": str(source_property_id or "").strip() or None,
        "common_area_kind": _clean_key(common_area_kind),
    }


def shared_property_interests_for_position(sim, x, y, z=0, *, primary_prop=None):
    """Return property interest rows for a common/shared area without changing access."""

    if sim is None:
        return ()
    try:
        x = int(x)
        y = int(y)
        z = int(z)
    except (TypeError, ValueError):
        return ()

    _structure, building_id, room_kind, common_area_kind = _structure_context_for_position(sim, x, y, z)
    primary_building_id = _property_building_id(primary_prop)
    if not building_id:
        building_id = primary_building_id

    candidate_ids = list(_property_ids_at_position(sim, x, y, z))
    primary_id = _property_id(primary_prop)
    if primary_id and primary_id not in candidate_ids:
        candidate_ids.append(primary_id)

    if building_id and common_area_kind:
        for property_id, prop in getattr(sim, "properties", {}).items():
            if property_id in candidate_ids:
                continue
            if _property_building_id(prop) == building_id:
                candidate_ids.append(property_id)

    rows = []
    seen = set()
    properties = getattr(sim, "properties", {})
    for property_id in candidate_ids:
        prop = properties.get(property_id)
        if not isinstance(prop, dict):
            continue
        source_property_id = _property_id(prop)
        prop_building_id = _property_building_id(prop)
        if building_id and prop_building_id and prop_building_id != building_id:
            continue

        implicit_kind = _common_area_kind_for_property(prop, room_kind=room_kind, common_area_kind=common_area_kind)
        if implicit_kind and common_area_kind:
            key = (source_property_id, source_property_id, implicit_kind)
            if key not in seen:
                seen.add(key)
                rows.append(_interest_row(
                    source_property_id,
                    source_property_id=source_property_id,
                    common_area_kind=implicit_kind,
                    implicit=True,
                ))

        for spec in _iter_shared_area_interest_specs(prop):
            if not _shared_area_interest_matches(
                spec,
                x=x,
                y=y,
                z=z,
                building_id=building_id,
                room_kind=room_kind,
                common_area_kind=common_area_kind,
                source_prop=prop,
            ):
                continue
            row_area_kind = (
                _clean_key(spec.get("common_area_kind"))
                or _clean_key(spec.get("area_kind"))
                or common_area_kind
                or room_kind
            )
            for target_property_id in _interest_property_ids_from_spec(spec, prop):
                key = (target_property_id, source_property_id, row_area_kind)
                if key in seen:
                    continue
                seen.add(key)
                rows.append(_interest_row(
                    target_property_id,
                    source_property_id=source_property_id,
                    spec=spec,
                    common_area_kind=row_area_kind,
                ))

    return tuple(row for row in rows if row.get("property_id"))


def shared_property_interest_event_payload(interests):
    rows = tuple(row for row in tuple(interests or ()) if isinstance(row, dict) and row.get("property_id"))
    property_ids = tuple(dict.fromkeys(str(row.get("property_id", "") or "").strip() for row in rows if row.get("property_id")))
    reasons = tuple(
        f"{str(row.get('property_id', '') or '').strip()}:{_clean_key(row.get('authority_reason')) or 'shared_interest'}"
        for row in rows
    )
    common_area_kind = ""
    for row in rows:
        common_area_kind = _clean_key(row.get("common_area_kind"))
        if common_area_kind:
            break
    return {
        "interest_property_ids": property_ids,
        "interest_reasons": reasons,
        "common_area_kind": common_area_kind,
    }


def world_hour(sim):
    world_traits = getattr(sim, "world_traits", {}) if sim is not None else {}
    clock = world_traits.get("clock", {}) if isinstance(world_traits, dict) else {}
    if not isinstance(clock, dict):
        clock = {}

    try:
        start_hour = int(clock.get("start_hour", DEFAULT_START_HOUR))
    except (TypeError, ValueError):
        start_hour = DEFAULT_START_HOUR

    try:
        ticks_per_hour = int(clock.get("ticks_per_hour", DEFAULT_TICKS_PER_HOUR))
    except (TypeError, ValueError):
        ticks_per_hour = DEFAULT_TICKS_PER_HOUR

    ticks_per_hour = max(60, ticks_per_hour)
    return (start_hour + (int(getattr(sim, "tick", 0)) // ticks_per_hour)) % 24


def _default_open_window_for(prop):
    if _property_offers_lodging_or_shelter(prop):
        return (0, 24)
    metadata = _property_metadata(prop)
    archetype = str(metadata.get("archetype", "") or "").strip().lower()
    if (
        property_is_public(prop)
        and not property_is_storefront(prop)
        and not finance_services_for_property(prop)
        and not site_services_for_property(prop)
    ):
        return (0, 24)
    if archetype in PUBLIC_HOURS_BY_ARCHETYPE:
        return PUBLIC_HOURS_BY_ARCHETYPE[archetype]
    if property_is_storefront(prop) or finance_services_for_property(prop):
        return (8, 19)
    return None


def _open_window_duration_hours(opening):
    normalized = _normalize_open_window(opening)
    if normalized is None:
        return 0
    start_hour, end_hour = normalized
    if start_hour == end_hour:
        return 24
    return (end_hour - start_hour) % 24


def _property_default_hours_should_jitter(prop):
    if not isinstance(prop, dict):
        return False

    metadata = _property_metadata(prop)
    if metadata.get("business_hours_jitter") is False:
        return False

    if str(metadata.get("business_name") or "").strip():
        return True
    if property_is_storefront(prop):
        return True
    if finance_services_for_property(prop):
        return True
    return False


def _jittered_default_open_window(sim, prop, opening):
    normalized = _normalize_open_window(opening)
    if normalized is None:
        return None
    if sim is None or not _property_default_hours_should_jitter(prop):
        return normalized
    if _open_window_duration_hours(normalized) >= 24:
        return normalized

    metadata = _property_metadata(prop)
    stable_bits = (
        getattr(sim, "seed", 0),
        metadata.get("building_id"),
        metadata.get("local_building_id"),
        metadata.get("business_name"),
        prop.get("name"),
        metadata.get("chunk"),
        prop.get("x"),
        prop.get("y"),
        prop.get("z", 0),
    )
    stable_key = "|".join(str(bit) for bit in stable_bits)
    offset = random.Random(f"{stable_key}:default_hours_jitter").choice((-1, 0, 0, 1))
    start_hour, end_hour = normalized
    return ((start_hour + offset) % 24, (end_hour + offset) % 24)


def _normalize_open_window(window):
    if not isinstance(window, (list, tuple)) or len(window) < 2:
        return None
    try:
        start = int(window[0]) % 24
        end = int(window[1]) % 24
    except (TypeError, ValueError):
        return None
    return (start, end)


def _hour_in_window(hour, opening):
    if opening is None:
        return None

    start_hour, end_hour = opening
    start_hour = int(start_hour) % 24
    end_hour = int(end_hour) % 24
    hour = int(hour) % 24

    if start_hour == end_hour:
        return True
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


def _occupation_matches_property(prop, occupation):
    return occupation_targets_property(prop, occupation)


def _occupation_authority_role(occupation):
    if not occupation:
        return "staff"
    workplace = getattr(occupation, "workplace", None)
    if isinstance(workplace, dict):
        configured = str(
            workplace.get("authority_role", workplace.get("access_role", ""))
            or ""
        ).strip().lower()
        if configured in {"owner", "manager", "staff"}:
            return configured
    career = str(getattr(occupation, "career", "") or "").strip().lower()
    if any(keyword in career for keyword in MANAGER_CAREER_KEYWORDS):
        return "manager"
    return "staff"


def _occupation_open_window(occupation):
    if not occupation:
        return None
    start = getattr(occupation, "shift_start", None)
    end = getattr(occupation, "shift_end", None)
    if start is None or end is None:
        return None
    return _normalize_open_window((start, end))


def _controller_mode_for(prop, access_level):
    metadata = _property_metadata(prop)
    configured = str(metadata.get("access_controller_credential_mode", "") or "").strip().lower()
    if configured in VALID_CREDENTIAL_MODES:
        return configured

    archetype = _property_archetype(prop)
    if archetype in BIOMETRIC_CONTROLLER_ARCHETYPES:
        return "biometric"
    if archetype in BADGE_CONTROLLER_ARCHETYPES or access_level == "restricted":
        return "badge"
    return "mechanical_key"


def _controller_required_tier(prop, credential_mode):
    metadata = _property_metadata(prop)
    configured = _int_or_default(metadata.get("access_controller_required_tier"), 0)
    if configured > 0:
        return max(1, min(5, configured))
    defaults = {
        "mechanical_key": 1,
        "badge": 2,
        "biometric": 3,
    }
    return defaults.get(str(credential_mode or "").strip().lower(), 1)


def _controller_security_tier(prop, access_level, credential_mode):
    metadata = _property_metadata(prop)
    configured = _int_or_default(metadata.get("access_controller_security_tier"), 0)
    if configured > 0:
        return max(1, min(5, configured))

    archetype = _property_archetype(prop)
    security_features = metadata.get("security_features", ())
    feature_bonus = 0
    if isinstance(security_features, (list, tuple, set)):
        feature_bonus = min(1, len([feature for feature in security_features if str(feature).strip()]))

    base_by_mode = {
        "mechanical_key": 1,
        "badge": 2,
        "biometric": 4,
    }
    base = base_by_mode.get(str(credential_mode or "").strip().lower(), 1)
    if access_level == "restricted":
        base += 1
    if archetype in {"bank", "tower", "armory", "checkpoint", "brokerage", "jail", "prison", "supply_bunker"}:
        base = max(base, 3)
    return max(1, min(5, base + feature_bonus))


def _accepted_credentials_for_mode(credential_mode):
    mode = str(credential_mode or "").strip().lower()
    if mode == "badge":
        return ("staff_badge", "manager_badge")
    if mode == "biometric":
        return ("biometric_authorization",)
    return ("mechanical_key",)


def clear_controller_intrusion(prop):
    metadata = _property_metadata(prop)
    if not metadata:
        return False
    changed = False
    for key in (
        "controller_intrusion_mode",
        "controller_intrusion_until_tick",
        "controller_intrusion_actor_eid",
        "controller_intrusion_source_item_id",
        "controller_intrusion_method",
        "controller_intrusion_security_tier_delta",
        "controller_intrusion_required_tier_delta",
    ):
        if key in metadata:
            metadata.pop(key, None)
            changed = True
    return changed


def controller_intrusion_state(sim, prop):
    if not isinstance(prop, dict):
        return {
            "active": False,
            "mode": "",
            "label": "",
            "credential_mode": "",
            "actor_eid": None,
            "source_item_id": "",
            "method": "",
            "until_tick": 0,
            "remaining_ticks": 0,
            "security_tier_delta": 0,
            "required_tier_delta": 0,
            "open_override": False,
            "grants_actor_access": False,
            "standing": 0.0,
            "standing_reason": "",
        }

    metadata = _property_metadata(prop)
    mode = str(metadata.get("controller_intrusion_mode", "") or "").strip().lower()
    profile = CONTROLLER_INTRUSION_PROFILES.get(mode)
    if profile is None:
        clear_controller_intrusion(prop)
        return controller_intrusion_state(sim, None)

    tick = int(getattr(sim, "tick", 0) if sim is not None else 0)
    until_tick = max(0, _int_or_default(metadata.get("controller_intrusion_until_tick"), 0))
    if until_tick <= tick:
        clear_controller_intrusion(prop)
        return controller_intrusion_state(sim, None)

    actor_eid = metadata.get("controller_intrusion_actor_eid")
    try:
        actor_eid = int(actor_eid) if actor_eid is not None else None
    except (TypeError, ValueError):
        actor_eid = None

    return {
        "active": True,
        "mode": mode,
        "label": str(profile.get("label", mode.replace("_", " "))).strip() or mode.replace("_", " "),
        "credential_mode": str(profile.get("credential_mode", "") or "").strip().lower(),
        "actor_eid": actor_eid,
        "source_item_id": str(metadata.get("controller_intrusion_source_item_id", "") or "").strip().lower(),
        "method": str(metadata.get("controller_intrusion_method", mode) or mode).strip().lower(),
        "until_tick": until_tick,
        "remaining_ticks": max(0, until_tick - tick),
        "security_tier_delta": _int_or_default(
            metadata.get("controller_intrusion_security_tier_delta"),
            profile.get("security_tier_delta", 0),
        ),
        "required_tier_delta": _int_or_default(
            metadata.get("controller_intrusion_required_tier_delta"),
            profile.get("required_tier_delta", 0),
        ),
        "open_override": bool(profile.get("open_override", False)),
        "grants_actor_access": bool(profile.get("grants_actor_access", False)),
        "standing": float(profile.get("standing", 0.0) or 0.0),
        "standing_reason": str(profile.get("standing_reason", "") or "").strip().lower(),
    }


def apply_controller_intrusion(
    prop,
    *,
    mode,
    tick=0,
    duration=0,
    actor_eid=None,
    source_item_id="",
    method="",
):
    if not isinstance(prop, dict):
        return False
    mode_key = str(mode or "").strip().lower()
    profile = CONTROLLER_INTRUSION_PROFILES.get(mode_key)
    duration_ticks = max(0, _int_or_default(duration, 0))
    if profile is None or duration_ticks <= 0:
        return clear_controller_intrusion(prop)

    metadata = _property_metadata(prop)
    until_tick = max(1, _int_or_default(tick, 0) + duration_ticks)
    metadata["controller_intrusion_mode"] = mode_key
    metadata["controller_intrusion_until_tick"] = int(until_tick)
    metadata["controller_intrusion_method"] = (
        str(method or mode_key).strip().lower() or mode_key
    )
    metadata["controller_intrusion_security_tier_delta"] = int(profile.get("security_tier_delta", 0) or 0)
    metadata["controller_intrusion_required_tier_delta"] = int(profile.get("required_tier_delta", 0) or 0)
    if actor_eid is not None:
        metadata["controller_intrusion_actor_eid"] = int(actor_eid)
    else:
        metadata.pop("controller_intrusion_actor_eid", None)
    if str(source_item_id or "").strip():
        metadata["controller_intrusion_source_item_id"] = str(source_item_id).strip().lower()
    else:
        metadata.pop("controller_intrusion_source_item_id", None)
    return True


def controller_intrusion_access_for_actor(sim, actor_eid, prop):
    state = controller_intrusion_state(sim, prop)
    if not state["active"] or actor_eid is None or not state["grants_actor_access"]:
        return None
    intrusion_actor_eid = state.get("actor_eid")
    if intrusion_actor_eid is not None and int(intrusion_actor_eid) != int(actor_eid):
        return None
    return {
        "mode": str(state.get("credential_mode", "") or "").strip().lower() or "badge",
        "reason": str(state.get("standing_reason", "") or "").strip().lower() or "spoofed_access",
    }


def _holder_credential_for_role(role, credential_mode):
    resolved_role = str(role or "staff").strip().lower() or "staff"
    mode = str(credential_mode or "mechanical_key").strip().lower() or "mechanical_key"
    if mode == "badge":
        if resolved_role in {"owner", "manager"}:
            return "manager_badge", 3
        return "staff_badge", 2
    if mode == "biometric":
        if resolved_role in {"owner", "manager"}:
            return "biometric_authorization", 4
        return "biometric_authorization", 3
    return "mechanical_key", 1


def _authorized_holders_for_property(sim, prop, owner_eid, credential_mode):
    holders = []
    seen = set()

    def add_holder(holder_eid, role):
        if holder_eid is None or holder_eid in seen:
            return
        credential_kind, credential_tier = _holder_credential_for_role(role, credential_mode)
        holders.append({
            "eid": int(holder_eid),
            "role": str(role or "staff").strip().lower() or "staff",
            "credential_kind": credential_kind,
            "credential_tier": int(credential_tier),
        })
        seen.add(holder_eid)

    if owner_eid is not None:
        add_holder(owner_eid, "owner")

    for member in property_org_members(sim, prop):
        actor_eid = member.get("eid")
        if actor_eid == owner_eid:
            continue
        occupation = member.get("occupation")
        role = str(member.get("role", "") or "").strip().lower()
        if role not in {"owner", "manager", "staff"}:
            role = _occupation_authority_role(occupation)
        add_holder(actor_eid, role)

    holders.sort(key=lambda holder: (0 if holder["role"] == "owner" else 1 if holder["role"] == "manager" else 2, holder["eid"]))
    return tuple(holders)


def _controller_fixture_label(kind, credential_mode):
    mode = str(credential_mode or "").strip().lower()
    controller_kind = str(kind or "").strip().lower()
    if mode == "biometric":
        return "biometric reader"
    if mode == "badge":
        return "badge reader"
    if controller_kind in {"auto_timer", "auto_lock"}:
        return "timed access relay"
    if controller_kind == "owner_schedule":
        return "schedule lock controller"
    return "mechanical lock"


def property_access_controller(sim, prop, hour=None):
    if not isinstance(prop, dict):
        return {
            "kind": "none",
            "authority_eid": None,
            "authority_tag": "",
            "authority_role": "",
            "opening_window": None,
            "open_now": None,
            "managed_lock": False,
            "fixture_label": "",
            "electronic": False,
            "schedule_source": "",
            "credential_mode": "mechanical_key",
            "accepted_credentials": ("mechanical_key",),
            "required_credential_tier": 1,
            "security_tier": 1,
            "authorized_holders": (),
            "intrusion_active": False,
            "intrusion_mode": "",
            "intrusion_label": "",
            "intrusion_method": "",
            "intrusion_until_tick": 0,
            "intrusion_remaining_ticks": 0,
            "intrusion_actor_eid": None,
            "intrusion_source_item_id": "",
        }

    metadata = _property_metadata(prop)
    owner_eid = prop.get("owner_eid")
    owner_tag = str(prop.get("owner_tag", "") or "").strip().lower()
    access_level = property_access_level(prop)
    public_facing = bool(
        property_is_public(prop)
        or property_is_storefront(prop)
        or finance_services_for_property(prop)
        or site_services_for_property(prop)
    )
    always_open_lodging = _property_offers_lodging_or_shelter(prop)
    configured_kind = str(metadata.get("access_controller_kind", "") or "").strip().lower()
    configured_window = _normalize_open_window(metadata.get("access_controller_hours"))
    default_window = configured_window or _jittered_default_open_window(sim, prop, _default_open_window_for(prop))

    if configured_kind:
        kind = configured_kind
    elif owner_eid is not None and public_facing:
        kind = "owner_schedule"
    elif owner_eid is not None:
        kind = "owner_keyed"
    elif public_facing or owner_tag in AUTO_CONTROLLER_OWNER_TAGS:
        kind = "auto_timer" if default_window is not None else "auto_lock"
    else:
        kind = "auto_lock"

    credential_mode = _controller_mode_for(prop, access_level)
    required_credential_tier = _controller_required_tier(prop, credential_mode)
    security_tier = _controller_security_tier(prop, access_level, credential_mode)
    authorized_holders = _authorized_holders_for_property(sim, prop, owner_eid, credential_mode)
    authority_role = "owner" if owner_eid is not None else ("auto" if kind in {"auto_timer", "auto_lock"} else "")

    opening_window = None
    schedule_source = ""
    if always_open_lodging:
        opening_window = (0, 24)
        schedule_source = "always_open"
    elif kind == "owner_schedule":
        owner_occ = sim.ecs.get(Occupation).get(owner_eid) if sim is not None and owner_eid is not None else None
        owner_window = _occupation_open_window(owner_occ)
        if owner_window and _occupation_matches_property(prop, owner_occ):
            opening_window = owner_window
            schedule_source = "owner_shift"
        elif owner_window:
            opening_window = owner_window
            schedule_source = "owner_shift"
        elif default_window is not None:
            opening_window = default_window
            schedule_source = "default_hours"
    elif kind == "auto_timer":
        opening_window = default_window
        if opening_window is not None:
            schedule_source = "timer"

    if hour is None:
        hour = world_hour(sim) if sim is not None else DEFAULT_START_HOUR
    hour = int(hour) % 24

    open_now = None
    if opening_window is not None:
        open_now = bool(_hour_in_window(hour, opening_window))
    elif kind == "auto_lock":
        open_now = False

    intrusion = controller_intrusion_state(sim, prop)
    if intrusion["active"]:
        required_credential_tier = max(1, required_credential_tier + int(intrusion.get("required_tier_delta", 0)))
        security_tier = max(1, security_tier + int(intrusion.get("security_tier_delta", 0)))
        if intrusion.get("open_override"):
            open_now = True

    return {
        "kind": kind,
        "authority_eid": owner_eid,
        "authority_tag": owner_tag,
        "authority_role": authority_role,
        "opening_window": opening_window,
        "open_now": open_now,
        "managed_lock": kind in {"owner_schedule", "auto_timer", "auto_lock"},
        "fixture_label": _controller_fixture_label(kind, credential_mode),
        "electronic": credential_mode in {"badge", "biometric"} or kind in {"owner_schedule", "auto_timer", "auto_lock"},
        "schedule_source": schedule_source,
        "credential_mode": credential_mode,
        "accepted_credentials": _accepted_credentials_for_mode(credential_mode),
        "required_credential_tier": required_credential_tier,
        "security_tier": security_tier,
        "authorized_holders": authorized_holders,
        "intrusion_active": bool(intrusion.get("active")),
        "intrusion_mode": str(intrusion.get("mode", "") or "").strip().lower(),
        "intrusion_label": str(intrusion.get("label", "") or "").strip(),
        "intrusion_method": str(intrusion.get("method", "") or "").strip().lower(),
        "intrusion_until_tick": int(intrusion.get("until_tick", 0) or 0),
        "intrusion_remaining_ticks": int(intrusion.get("remaining_ticks", 0) or 0),
        "intrusion_actor_eid": intrusion.get("actor_eid"),
        "intrusion_source_item_id": str(intrusion.get("source_item_id", "") or "").strip().lower(),
    }


def sync_property_access_controller(sim, prop, hour=None):
    if not isinstance(prop, dict):
        return property_access_controller(sim, prop, hour=hour)

    metadata = _property_metadata(prop)
    controller = property_access_controller(sim, prop, hour=hour)
    metadata["access_controller_kind"] = controller["kind"]
    metadata["access_controller_authority_role"] = controller["authority_role"]
    metadata["access_controller_fixture"] = controller["fixture_label"]
    metadata["access_controller_electronic"] = bool(controller["electronic"])
    metadata["access_controller_credential_mode"] = controller["credential_mode"]
    metadata["access_controller_required_tier"] = int(controller["required_credential_tier"])
    metadata["access_controller_security_tier"] = int(controller["security_tier"])
    metadata["access_controller_accepted_credentials"] = list(controller["accepted_credentials"])
    metadata["access_authorized_holders"] = [
        {
            "eid": int(holder.get("eid")),
            "role": str(holder.get("role", "staff")),
            "credential_kind": str(holder.get("credential_kind", "mechanical_key")),
            "credential_tier": int(holder.get("credential_tier", 1)),
        }
        for holder in controller["authorized_holders"]
        if holder.get("eid") is not None
    ]
    if controller["opening_window"] is not None:
        metadata["access_controller_hours"] = list(controller["opening_window"])
    else:
        metadata.pop("access_controller_hours", None)
    if controller["schedule_source"]:
        metadata["access_controller_schedule_source"] = controller["schedule_source"]
    else:
        metadata.pop("access_controller_schedule_source", None)
    if controller["authority_eid"] is not None:
        metadata["access_controller_authority_eid"] = int(controller["authority_eid"])
    else:
        metadata.pop("access_controller_authority_eid", None)
    if controller["managed_lock"] and controller["open_now"] is not None:
        metadata["property_locked"] = not bool(controller["open_now"])
    return controller


def property_is_open(sim, prop, hour=None):
    opening = property_open_window(sim, prop)
    if opening is None:
        return None
    if hour is None:
        hour = world_hour(sim)
    return bool(_hour_in_window(hour, opening))


def property_open_window(sim, prop):
    return property_access_controller(sim, prop).get("opening_window")


def property_status_text(sim, prop, hour=None):
    is_open = property_is_open(sim, prop, hour=hour)
    if is_open is None:
        return "private"
    return "open" if is_open else "closed"


def _position_within_property(prop, x=None, y=None, z=None):
    if x is None or y is None:
        return False

    try:
        x = int(x)
        y = int(y)
        z = int(prop.get("z", 0) if z is None else z)
    except (TypeError, ValueError):
        return False

    metadata = _property_metadata(prop)
    explicit_cells = _shape_cells_2d(metadata, "footprint_cells")
    excluded_cells = _shape_cells_2d(metadata, "footprint_excluded_cells")
    footprint = metadata.get("footprint")
    if isinstance(footprint, dict):
        try:
            left = int(footprint.get("left"))
            right = int(footprint.get("right"))
            top = int(footprint.get("top"))
            bottom = int(footprint.get("bottom"))
            base_z = int(prop.get("z", 0))
            floors = max(1, int(metadata.get("floors", 1)))
        except (TypeError, ValueError):
            left = right = top = bottom = None
            base_z = floors = None
        else:
            if not (base_z <= z < base_z + floors):
                return False
            if explicit_cells:
                return (x, y) in explicit_cells
            if left <= x <= right and top <= y <= bottom and (x, y) not in excluded_cells:
                return True

    try:
        exact_match = (
            int(prop.get("x")) == x
            and int(prop.get("y")) == y
            and int(prop.get("z", 0)) == z
        )
        if not exact_match:
            return False
        if explicit_cells:
            return (x, y) in explicit_cells
        return (x, y) not in excluded_cells
    except (TypeError, ValueError):
        return False


def _player_owns_property(sim, actor_eid, prop):
    if actor_eid is None or not prop:
        return False
    if prop.get("owner_eid") == actor_eid:
        return True

    assets = sim.ecs.get(PlayerAssets).get(actor_eid)
    if assets and prop["id"] in assets.owned_property_ids:
        return True

    portfolio = sim.ecs.get(PropertyPortfolio).get(actor_eid)
    if portfolio and prop["id"] in portfolio.owned_property_ids:
        return True

    return False


def _credential_holder_standing(sim, actor_eid, prop):
    if actor_eid is None or not prop:
        return 0.0, ""

    intrusion_access = controller_intrusion_access_for_actor(sim, actor_eid, prop)
    if intrusion_access:
        intrusion = controller_intrusion_state(sim, prop)
        return float(intrusion.get("standing", 0.0) or 0.0), (
            str(intrusion.get("standing_reason", "") or "").strip().lower()
            or str(intrusion_access.get("reason", "") or "").strip().lower()
        )

    controller = property_access_controller(sim, prop)
    required_tier = max(1, _int_or_default(controller.get("required_credential_tier"), 1))
    accepted_credentials = controller.get("accepted_credentials", ())
    inventory = sim.ecs.get(Inventory).get(actor_eid)
    lock_state = property_lock_state(prop)
    if lock_state["key_id"] and inventory:
        entry = inventory_matching_property_credential(
            inventory,
            property_id=prop.get("id"),
            key_id=lock_state["key_id"],
            allowed_kinds=accepted_credentials,
            minimum_tier=required_tier,
        )
        if entry:
            return 0.94, "credential_holder"

    if str(controller.get("credential_mode", "")).strip().lower() == "biometric":
        for holder in controller.get("authorized_holders", ()):
            if holder.get("eid") != actor_eid:
                continue
            if _int_or_default(holder.get("credential_tier"), 0) >= required_tier:
                return 0.96, "credential_holder"
    return 0.0, ""


def _employment_standing(sim, actor_eid, prop):
    if actor_eid is None or not prop:
        return 0.0

    occupation = sim.ecs.get(Occupation).get(actor_eid)
    if not occupation:
        return 0.0

    workplace = occupation.workplace
    if not workplace_targets_property(prop, workplace):
        return 0.0
    property_id = workplace.get("property_id")
    return 0.92 if property_id and property_id == prop.get("id") else 0.86


def _anchor_matches_property(prop, anchor):
    if not isinstance(anchor, (list, tuple)) or len(anchor) < 3:
        return False

    try:
        ax = int(anchor[0])
        ay = int(anchor[1])
        az = int(anchor[2])
    except (TypeError, ValueError):
        return False

    if _position_within_property(prop, x=ax, y=ay, z=az):
        return True

    metadata = _property_metadata(prop)
    entry = metadata.get("entry")
    if isinstance(entry, dict):
        try:
            ex = int(entry.get("x"))
            ey = int(entry.get("y"))
            ez = int(entry.get("z", prop.get("z", 0)))
        except (TypeError, ValueError):
            return False
        return (ax, ay, az) == (ex, ey, ez)

    return False


def _routine_standing(sim, actor_eid, prop):
    if actor_eid is None or not prop:
        return 0.0, ""

    routine = sim.ecs.get(NPCRoutine).get(actor_eid)
    if not routine:
        return 0.0, ""

    if _anchor_matches_property(prop, getattr(routine, "home", None)):
        return 0.94, "resident"
    if _anchor_matches_property(prop, getattr(routine, "work", None)):
        return 0.88, "employee"
    return 0.0, ""


def _contact_cover(sim, actor_eid, prop):
    if actor_eid is None or not prop:
        return 0.0, ""

    ledger = sim.ecs.get(ContactLedger).get(actor_eid)
    if not ledger:
        return 0.0, ""

    entry = ledger.by_property.get(prop["id"])
    if not entry:
        return 0.0, ""

    standing = _clamp_unit(entry.get("standing", 0.5), default=0.5)
    benefits = {str(bit).strip().lower() for bit in entry.get("benefits", ()) if str(bit).strip()}
    cover = 0.22 + (standing * 0.38)
    if "soft_access" in benefits:
        cover += 0.18
    return min(0.82, cover), "contact"


def _door_service_courtesy(sim, actor_eid, prop):
    if actor_eid is None or not isinstance(prop, dict):
        return False

    state = getattr(sim, "door_service_courtesies", None)
    if not isinstance(state, dict):
        return False

    property_id = str(prop.get("id", "") or "").strip()
    if not property_id:
        return False

    current_tick = int(getattr(sim, "tick", 0))
    key = (int(actor_eid), property_id)
    grant = state.get(key)
    if not isinstance(grant, dict):
        return False
    if int(grant.get("until_tick", 0) or 0) <= current_tick:
        state.pop(key, None)
        return False
    return bool(grant.get("allow_services", False))


def _bond_cover(sim, actor_eid, owner_eid):
    if actor_eid is None or owner_eid is None or actor_eid == owner_eid:
        return 0.0, ""

    social = sim.ecs.get(NPCSocial).get(actor_eid)
    if not social:
        return 0.0, ""

    bond = social.bonds.get(owner_eid)
    if not bond:
        return 0.0, ""

    cover = (
        (_clamp_unit(bond.get("trust", 0.0)) * 0.5)
        + (_clamp_unit(bond.get("closeness", 0.0)) * 0.35)
        + (_clamp_unit(bond.get("protectiveness", 0.0)) * 0.15)
    )
    kind = str(bond.get("kind", "") or "").strip().lower()
    if kind in {"family", "partner"}:
        cover += 0.12
    return min(0.92, cover), kind or "relationship"


def _standing_candidate(best_score, best_reason, score, reason):
    if score > best_score:
        return score, reason
    return best_score, best_reason


@dataclass(frozen=True)
class PropertyAccessResult:
    property_id: str | None
    access_level: str
    inside_bounds: bool
    public_facing: bool
    current_hour: int
    opening_window: tuple[int, int] | None
    currently_open: bool | None
    standing: float
    social_cover: float
    temporal_legitimacy: float
    standing_reason: str
    permitted: bool
    can_use_services: bool
    severity_score: int
    severity_label: str
    organization_watchfulness: int = 0
    organization_note: str = ""
    organization_reason_tags: tuple[str, ...] = ()
    organization_denied_entry: bool = False
    organization_denied_service: bool = False
    organization_guard_grace: bool = False


@dataclass(frozen=True)
class PropertyIngressResult:
    property_id: str | None
    from_inside: bool
    to_inside: bool
    entered_bounds: bool
    ingress_kind: str
    aperture_kind: str
    breach_severity: float


def property_apertures(prop):
    metadata = _property_metadata(prop)
    raw_apertures = metadata.get("apertures")
    apertures = []

    if isinstance(raw_apertures, (list, tuple)):
        candidates = raw_apertures
    else:
        entry = metadata.get("entry")
        candidates = (entry,) if isinstance(entry, dict) else ()

    for aperture in candidates:
        if not isinstance(aperture, dict):
            continue

        try:
            ax = int(aperture.get("x"))
            ay = int(aperture.get("y"))
            az = int(aperture.get("z", prop.get("z", 0)))
        except (TypeError, ValueError):
            continue

        kind = str(aperture.get("kind", "door") or "door").strip().lower()
        side = str(aperture.get("side", "") or "").strip().lower()
        ordinary = bool(aperture.get("ordinary", kind == "door"))
        apertures.append({
            "x": ax,
            "y": ay,
            "z": az,
            "kind": kind,
            "side": side,
            "ordinary": ordinary,
        })

    return tuple(apertures)


def _boundary_tile(prop, x, y, z):
    metadata = _property_metadata(prop)
    footprint = metadata.get("footprint")
    if not isinstance(footprint, dict):
        return False

    try:
        left = int(footprint.get("left"))
        right = int(footprint.get("right"))
        top = int(footprint.get("top"))
        bottom = int(footprint.get("bottom"))
        base_z = int(prop.get("z", 0))
        floors = max(1, int(metadata.get("floors", 1)))
        x = int(x)
        y = int(y)
        z = int(z)
    except (TypeError, ValueError):
        return False

    if not (base_z <= z < base_z + floors and left <= x <= right and top <= y <= bottom):
        return False
    return x in {left, right} or y in {top, bottom}


def property_ingress_context(prop, from_x=None, from_y=None, from_z=None, to_x=None, to_y=None, to_z=None):
    to_inside = _position_within_property(prop, x=to_x, y=to_y, z=to_z)
    from_inside = _position_within_property(prop, x=from_x, y=from_y, z=from_z)
    entered_bounds = bool(to_inside and not from_inside)

    if not to_inside:
        return PropertyIngressResult(
            property_id=prop.get("id") if isinstance(prop, dict) else None,
            from_inside=bool(from_inside),
            to_inside=False,
            entered_bounds=False,
            ingress_kind="outside",
            aperture_kind="",
            breach_severity=0.0,
        )

    if from_inside:
        return PropertyIngressResult(
            property_id=prop.get("id") if isinstance(prop, dict) else None,
            from_inside=True,
            to_inside=True,
            entered_bounds=False,
            ingress_kind="internal",
            aperture_kind="",
            breach_severity=0.0,
        )

    try:
        tx = int(to_x)
        ty = int(to_y)
        tz = int(to_z if to_z is not None else prop.get("z", 0))
    except (TypeError, ValueError, AttributeError):
        tx = ty = tz = None

    for aperture in property_apertures(prop):
        if (tx, ty, tz) != (aperture["x"], aperture["y"], aperture["z"]):
            continue

        if aperture["ordinary"]:
            return PropertyIngressResult(
                property_id=prop.get("id") if isinstance(prop, dict) else None,
                from_inside=False,
                to_inside=True,
                entered_bounds=True,
                ingress_kind="ordinary_entry",
                aperture_kind=aperture["kind"],
                breach_severity=0.0,
            )

        kind = aperture["kind"]
        if kind in {"window", "skylight"}:
            severity = 0.45
        elif kind in {"side_door", "service_door", "employee_door"}:
            severity = 0.22
        else:
            severity = 0.32

        return PropertyIngressResult(
            property_id=prop.get("id") if isinstance(prop, dict) else None,
            from_inside=False,
            to_inside=True,
            entered_bounds=True,
            ingress_kind="alternate_aperture",
            aperture_kind=kind,
            breach_severity=severity,
        )

    ingress_kind = "boundary_breach" if _boundary_tile(prop, tx, ty, tz) else "deep_breach"
    breach_severity = 0.58 if ingress_kind == "boundary_breach" else 0.82
    return PropertyIngressResult(
        property_id=prop.get("id") if isinstance(prop, dict) else None,
        from_inside=False,
        to_inside=True,
        entered_bounds=True,
        ingress_kind=ingress_kind,
        aperture_kind="",
        breach_severity=breach_severity,
    )


def evaluate_property_access(sim, actor_eid, prop, x=None, y=None, z=None, breach_severity=0.0):
    if not prop:
        return PropertyAccessResult(
            property_id=None,
            access_level="public",
            inside_bounds=False,
            public_facing=False,
            current_hour=world_hour(sim),
            opening_window=None,
            currently_open=None,
            standing=0.0,
            social_cover=0.0,
            temporal_legitimacy=1.0,
            standing_reason="none",
            permitted=True,
            can_use_services=False,
            severity_score=0,
            severity_label="clear",
        )

    access_level = property_access_level(prop)
    public_facing = access_level == "public"
    hour = world_hour(sim)
    opening_window = property_open_window(sim, prop)
    currently_open = property_is_open(sim, prop, hour=hour)
    inside_bounds = _position_within_property(prop, x=x, y=y, z=z)
    archetype = str((prop.get("metadata", {}) or {}).get("archetype", "")).strip().lower()

    if inside_bounds and archetype in JUSTICE_CUSTODY_ARCHETYPES:
        state = getattr(sim, "world_traits", None)
        state = state.get("criminal_justice") if isinstance(state, dict) else None
        offenders = state.get("offenders") if isinstance(state, dict) else None
        try:
            offender_key = str(int(actor_eid))
        except (TypeError, ValueError):
            offender_key = None
        record = offenders.get(offender_key) if offender_key and isinstance(offenders, dict) else None
        if isinstance(record, dict) and bool(record.get("in_custody", False)):
            return PropertyAccessResult(
                property_id=prop.get("id"),
                access_level=access_level,
                inside_bounds=True,
                public_facing=access_level == "public",
                current_hour=hour,
                opening_window=opening_window,
                currently_open=currently_open,
                standing=1.0,
                social_cover=0.0,
                temporal_legitimacy=1.0,
                standing_reason="lawful_custody",
                permitted=True,
                can_use_services=False,
                severity_score=0,
                severity_label="clear",
            )
        if _custody_release_grace_active(sim, actor_eid, prop.get("id")):
            return PropertyAccessResult(
                property_id=prop.get("id"),
                access_level=access_level,
                inside_bounds=True,
                public_facing=access_level == "public",
                current_hour=hour,
                opening_window=opening_window,
                currently_open=currently_open,
                standing=1.0,
                social_cover=0.0,
                temporal_legitimacy=1.0,
                standing_reason="custody_release",
                permitted=True,
                can_use_services=False,
                severity_score=0,
                severity_label="clear",
            )

    standing = 0.0
    standing_reason = "none"
    social_cover = 0.0
    social_actor_eid = _party_rep_proxy_actor(sim, actor_eid)

    owner_authority = bool(
        _player_owns_property(sim, actor_eid, prop)
        or (
            social_actor_eid != actor_eid
            and _player_owns_property(sim, social_actor_eid, prop)
        )
    )
    if owner_authority:
        standing, standing_reason = 1.0, "owner"
    else:
        key_score, key_reason = _credential_holder_standing(sim, actor_eid, prop)
        standing, standing_reason = _standing_candidate(
            standing,
            standing_reason,
            key_score,
            key_reason or standing_reason,
        )
        routine_score, routine_reason = _routine_standing(sim, actor_eid, prop)
        standing, standing_reason = _standing_candidate(
            standing,
            standing_reason,
            routine_score,
            routine_reason or standing_reason,
        )
        employee_score = _employment_standing(sim, actor_eid, prop)
        standing, standing_reason = _standing_candidate(
            standing,
            standing_reason,
            employee_score,
            "employee" if employee_score > 0.0 else standing_reason,
        )

        owner_eid = prop.get("owner_eid")
        social_reason = standing_reason
        social_candidates = []
        for candidate_eid in dict.fromkeys(eid for eid in (actor_eid, social_actor_eid) if eid is not None):
            contact_cover, contact_reason = _contact_cover(sim, candidate_eid, prop)
            bond_cover, bond_reason = _bond_cover(sim, candidate_eid, owner_eid)
            candidate_cover = max(contact_cover, bond_cover)
            candidate_reason = contact_reason if contact_cover >= bond_cover else bond_reason
            social_candidates.append((candidate_cover, candidate_reason))
        if social_candidates:
            social_cover, social_reason = max(
                social_candidates,
                key=lambda row: (float(row[0]), str(row[1] or "")),
            )
        standing, standing_reason = _standing_candidate(
            standing,
            standing_reason,
            social_cover,
            social_reason or standing_reason,
        )

        if access_level == "public":
            if currently_open is False:
                standing, standing_reason = _standing_candidate(
                    standing,
                    standing_reason,
                    0.0,
                    standing_reason,
                )
            else:
                public_score = 0.86 if opening_window == (0, 24) else 0.72
                public_reason = "public_space" if opening_window == (0, 24) else "open_business"
                standing, standing_reason = _standing_candidate(
                    standing,
                    standing_reason,
                    public_score,
                    public_reason,
                )

    if access_level == "public":
        if currently_open is False:
            permission_threshold = 0.75
            temporal_legitimacy = 0.18
        else:
            permission_threshold = 0.3
            temporal_legitimacy = 1.0
    elif access_level == "restricted":
        permission_threshold = 0.78
        temporal_legitimacy = 0.5
    else:
        permission_threshold = 0.62
        temporal_legitimacy = 0.5

    org_posture = effective_org_access_posture(
        sim,
        actor_eid,
        prop,
        current_tick=getattr(sim, "tick", 0),
    )
    if owner_authority and (
        bool(org_posture.get("deny_entry"))
        or bool(org_posture.get("deny_service"))
    ):
        org_posture = dict(org_posture)
        org_posture["deny_entry"] = False
        org_posture["deny_service"] = False
    org_reason_tags = tuple(org_posture.get("reason_tags", ()) or ())
    if "oversight_access" in org_reason_tags:
        org_reason = "oversight"
    elif "service_relation" in org_reason_tags:
        org_reason = "service_partner"
    elif "represented_access" in org_reason_tags:
        org_reason = "represented"
    else:
        org_reason = "organization"
    if float(org_posture.get("standing_floor", 0.0) or 0.0) > 0.0:
        standing, standing_reason = _standing_candidate(
            standing,
            standing_reason,
            float(org_posture.get("standing_floor", 0.0) or 0.0),
            org_reason,
        )
    if (
        public_facing
        and currently_open is not False
        and bool(org_posture.get("public_entry_grace"))
    ):
        standing, standing_reason = _standing_candidate(
            standing,
            standing_reason,
            max(float(permission_threshold), 0.34),
            org_reason,
        )

    permitted = standing >= permission_threshold
    can_use_services = bool(
        public_facing
        and (
            (currently_open is not False and permitted)
            or standing_reason in {"owner", "employee", "credential_holder"}
        )
    )
    customer_policy = "public"
    if _player_owns_property(sim, getattr(sim, "player_eid", None), prop):
        customer_policy = _player_business_customer_policy(prop)
    if can_use_services and customer_policy in {"staff_only", "closed"}:
        can_use_services = standing_reason in {"owner", "employee", "credential_holder"}
    if (
        not can_use_services
        and public_facing
        and _door_service_courtesy(sim, actor_eid, prop)
    ):
        can_use_services = True
    if (
        not can_use_services
        and public_facing
        and currently_open is not False
        and bool(org_posture.get("service_grace"))
        and not bool(org_posture.get("deny_entry"))
    ):
        can_use_services = True
    if bool(org_posture.get("deny_entry")):
        permitted = False
        can_use_services = False
    elif bool(org_posture.get("deny_service")):
        can_use_services = False

    severity_score = 0
    if inside_bounds and not permitted:
        if access_level == "public":
            base = 11 if currently_open is False else 7
        elif access_level == "restricted":
            base = 30
        else:
            base = 21

        temporal_penalty = int(round((1.0 - temporal_legitimacy) * 10.0))
        social_relief = int(round(social_cover * 12.0))
        breach_penalty = int(round(max(0.0, float(breach_severity)) * 18.0))
        severity_score = max(4, min(80, base + temporal_penalty + breach_penalty - social_relief))
    if inside_bounds and bool(org_posture.get("deny_entry")):
        severity_score = max(
            severity_score,
            min(
                80,
                18 + int(round(float(org_posture.get("watchfulness", 0) or 0) * 0.35)),
            ),
        )
    elif inside_bounds and severity_score > 0 and int(org_posture.get("watchfulness", 0) or 0) > 0:
        severity_score = max(
            severity_score,
            min(
                80,
                severity_score + int(round(float(org_posture.get("watchfulness", 0) or 0) * 0.08)),
            ),
        )

    if severity_score <= 0:
        severity_label = "clear"
    elif severity_score < 15:
        severity_label = "suspicious"
    elif severity_score < 30:
        severity_label = "trespass"
    else:
        severity_label = "serious_trespass"

    return PropertyAccessResult(
        property_id=prop.get("id"),
        access_level=access_level,
        inside_bounds=inside_bounds,
        public_facing=public_facing,
        current_hour=hour,
        opening_window=opening_window,
        currently_open=currently_open,
        standing=standing,
        social_cover=social_cover,
        temporal_legitimacy=temporal_legitimacy,
        standing_reason=standing_reason,
        permitted=permitted,
        can_use_services=can_use_services,
        severity_score=severity_score,
        severity_label=severity_label,
        organization_watchfulness=int(org_posture.get("watchfulness", 0) or 0),
        organization_note=str(org_posture.get("note_text", "") or ""),
        organization_reason_tags=org_reason_tags,
        organization_denied_entry=bool(org_posture.get("deny_entry")),
        organization_denied_service=bool(org_posture.get("deny_service")),
        organization_guard_grace=bool(org_posture.get("guard_grace")),
    )


def organization_guard_grace_active(sim, actor_eid, prop, current_tick=None):
    posture = effective_org_access_posture(
        sim,
        actor_eid,
        prop,
        current_tick=current_tick,
    )
    return bool(posture.get("guard_grace")) and not bool(posture.get("deny_entry"))


def property_claim_reason(sim, actor_eid, prop, x=None, y=None, z=None, min_standing=0.58):
    access = evaluate_property_access(sim, actor_eid, prop, x=x, y=y, z=z)
    reason = str(access.standing_reason or "").strip().lower()
    if access.standing < float(min_standing):
        return access, ""
    if reason in NEUTRAL_STANDING_REASONS:
        return access, ""
    return access, reason or "authorized"
