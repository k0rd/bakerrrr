import random
from dataclasses import dataclass

from game.components import ContactLedger, Inventory, NPCSocial, NPCRoutine, Occupation, PlayerAssets, PropertyPortfolio
from game.organizations import occupation_targets_property, property_org_members, workplace_targets_property
from game.property_keys import inventory_matching_property_credential, property_lock_state


DEFAULT_START_HOUR = 9
DEFAULT_TICKS_PER_HOUR = 600

STOREFRONT_ARCHETYPE_HINTS = {
    "casino",
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
    "roadhouse",
    "soup_kitchen",
    "street_kitchen",
    "tavern",
    "theater",
    "tool_depot",
    "music_venue",
    "gaming_hall",
    "dock_shack",
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
    "server_hub",
    "supply_bunker",
}

PUBLIC_HOURS_BY_ARCHETYPE = {
    "arcade": (11, 23),
    "auto_garage": (8, 19),
    "bank": (9, 17),
    "bar": (16, 2),
    "backroom_clinic": (10, 20),
    "bookshop": (9, 20),
    "brokerage": (8, 18),
    "casino": (12, 4),
    "corner_store": (6, 23),
    "courier_office": (7, 19),
    "daycare": (7, 18),
    "flophouse": (0, 24),
    "gallery": (11, 20),
    "gaming_hall": (12, 3),
    "hardware_store": (8, 19),
    "hotel": (0, 24),
    "junk_market": (9, 18),
    "karaoke_box": (17, 2),
    "laundromat": (6, 22),
    "metro_exchange": (5, 24),
    "music_venue": (18, 2),
    "nightclub": (18, 3),
    "pawn_shop": (10, 19),
    "pharmacy": (8, 21),
    "pool_hall": (12, 2),
    "recruitment_office": (8, 18),
    "relay_post": (6, 22),
    "restaurant": (7, 22),
    "roadhouse": (6, 23),
    "soup_kitchen": (10, 19),
    "street_kitchen": (11, 23),
    "tavern": (14, 2),
    "theater": (14, 23),
    "tool_depot": (7, 19),
    "dock_shack": (6, 19),
    "ferry_post": (5, 20),
    "tide_station": (6, 18),
}

NEUTRAL_STANDING_REASONS = {"", "none", "open_business", "public_space"}
AUTO_CONTROLLER_OWNER_TAGS = {"", "public", "city", "community", "neutral", "none", "unowned"}
BADGE_CONTROLLER_ARCHETYPES = {
    "armory",
    "bank",
    "barracks",
    "brokerage",
    "checkpoint",
    "courthouse",
    "hotel",
    "lab",
    "media_lab",
    "office",
    "pharmacy",
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
    "casino": ("slots", "casino_holdem", "plinko", "twenty_one"),
    "flophouse": ("rest",),
    "hotel": ("rest",),
    "tavern": ("intel",),
}


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


def _property_metadata(prop):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _property_archetype(prop):
    return str(_property_metadata(prop).get("archetype", "") or "").strip().lower()


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


def default_site_services_for_archetype(archetype):
    key = str(archetype or "").strip().lower()
    return tuple(DEFAULT_SITE_SERVICES_BY_ARCHETYPE.get(key, ()))


def site_services_for_property(prop):
    metadata = _property_metadata(prop)
    configured = metadata.get("site_services", [])
    services = []
    if isinstance(configured, (list, tuple, set)):
        services = [str(service).strip().lower() for service in configured if str(service).strip()]
    elif isinstance(configured, str) and configured.strip():
        services = [configured.strip().lower()]

    if not services:
        services = list(default_site_services_for_archetype(metadata.get("archetype")))

    ordered = []
    seen = set()
    for service in services:
        key = str(service).strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        ordered.append(key)
    return tuple(ordered)


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

    owner_tag = str(prop.get("owner_tag", "") or "").strip().lower()
    return owner_tag == "public"


def property_access_level(prop):
    archetype = _property_archetype(prop)
    if archetype in RESTRICTED_ARCHETYPES:
        return "restricted"
    if property_is_public(prop):
        return "public"
    if property_is_storefront(prop) or finance_services_for_property(prop):
        return "public"
    return "protected"


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
    if archetype in {"bank", "tower", "armory", "checkpoint", "brokerage", "supply_bunker"}:
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
    if kind == "owner_schedule":
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
            if base_z <= z < base_z + floors and left <= x <= right and top <= y <= bottom:
                return True

    try:
        return (
            int(prop.get("x")) == x
            and int(prop.get("y")) == y
            and int(prop.get("z", 0)) == z
        )
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

    standing = 0.0
    standing_reason = "none"
    social_cover = 0.0

    if _player_owns_property(sim, actor_eid, prop):
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
        contact_cover, contact_reason = _contact_cover(sim, actor_eid, prop)
        bond_cover, bond_reason = _bond_cover(sim, actor_eid, owner_eid)
        social_cover = max(contact_cover, bond_cover)
        social_reason = contact_reason if contact_cover >= bond_cover else bond_reason
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

    permitted = standing >= permission_threshold
    can_use_services = bool(
        public_facing
        and (
            (currently_open is not False and permitted)
            or standing_reason in {"owner", "employee", "credential_holder"}
        )
    )

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
    )


def property_claim_reason(sim, actor_eid, prop, x=None, y=None, z=None, min_standing=0.58):
    access = evaluate_property_access(sim, actor_eid, prop, x=x, y=y, z=z)
    reason = str(access.standing_reason or "").strip().lower()
    if access.standing < float(min_standing):
        return access, ""
    if reason in NEUTRAL_STANDING_REASONS:
        return access, ""
    return access, reason or "authorized"
