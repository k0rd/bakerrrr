"""Fictional cult organization runtime.

Cult membership is social/organizational state, not justice state.  V1 keeps
law enforcement out of cult truth while letting cults recruit, dress, meet,
shun, and protect their own devotions through ordinary actor behavior.
"""

from __future__ import annotations

import random

from engine.events import Event
from engine.systems import System
from engine.visibility import has_line_of_sight
from game.appearance_loadout import (
    APPEARANCE_METADATA_KEY,
    APPEARANCE_SLOT_METADATA_KEY,
    APPEARANCE_WORN_METADATA_KEY,
    cosmetic_variant_metadata,
    equip_appearance_item,
    unequip_appearance_slot,
)
from game.bodyguard_runtime import (
    active_bodyguard_contracts,
    create_bodyguard_detail_for_principal,
    fire_bodyguard_contract,
    protection_channel_id_for_assignment,
)
from game.components import (
    AI,
    CreatureIdentity,
    Inventory,
    NPCNeeds,
    NPCSocial,
    NPCSettlement,
    NPCWill,
    Occupation,
    PlayerAssets,
    Position,
    Vitality,
)
from game.flora_runtime import load_flora_catalog
from game.human_identity import normalize_gender_identity
from game.items import ITEM_CATALOG, item_display_name
from game.organizations import (
    assign_actor_organization,
    ensure_organization,
    link_property_organization,
    property_org_members,
    property_service_ids,
)
from game.property_runtime import property_is_storefront, property_services
from game.skills import actor_skill
from game.service_runtime import _manhattan
from game.system_support.actor_attention_runtime import mark_actor_urgent
from game.system_support.ai_intent_runtime import _sync_ai_intent


CULT_KIND = "cult"
CULT_SERVICE_IDS = frozenset({
    "cult_contact",
    "cult_conversion",
    "cult_donation",
    "cult_uniform_replacement",
    "cult_meeting_info",
    "cult_leader_audience",
    "cult_leave",
})
CULT_UPDATE_INTERVAL = 37
CULT_PLAYER_GRACE_TICKS = 24 * 600
CULT_MEETING_DURATION_TICKS = 150
CULT_RECRUIT_COOLDOWN_TICKS = 420
CULT_OFFICIAL_OUTREACH_COOLDOWN_TICKS = 210
CULT_PROPAGATION_LIMIT = 8
CULT_MEMBERS_PER_OFFICIAL = 4
CULT_NONMEMBER_SERVICE_TAX_MULT = 1.35

_OFFICIAL_TITLES = (
    "keeper",
    "speaker",
    "reader",
    "steward",
    "warden",
    "tender",
    "guide",
    "celebrant",
    "custodian",
    "priest",
)
_CULT_NOUNS = (
    "circle",
    "house",
    "lamp",
    "path",
    "veil",
    "thread",
    "choir",
    "table",
    "market",
    "door",
    "hour",
    "hand",
)
_CULT_ADJECTIVES = (
    "Quiet",
    "Violet",
    "Lantern",
    "Glass",
    "Amber",
    "Low",
    "Green",
    "Third",
    "Open",
    "Hushed",
    "Copper",
    "Moonlace",
)
_ANIMAL_TARGETS = (
    ("pier_rat", "pier rats"),
    ("marsh_hare", "marsh hares"),
    ("ridge_crow", "ridge crows"),
    ("glass_fox", "glass foxes"),
    ("field_dog", "field dogs"),
    ("river_moth", "river moths"),
)
_OBJECT_TARGETS = (
    ("brass_ring", "brass rings"),
    ("blue_mug", "blue mugs"),
    ("red_hat", "red hats"),
    ("silver_key", "silver keys"),
    ("plain_book", "plain books"),
    ("white_thread", "white thread"),
)
_COLOR_TARGETS = (
    ("purple", "purple"),
    ("white", "white"),
    ("green", "green"),
    ("gold", "gold"),
    ("red", "red"),
    ("blue", "blue"),
    ("black", "black"),
)
_UNIFORM_COLORS = (
    "purple",
    "white",
    "green",
    "gold",
    "red",
    "blue",
    "black",
    "charcoal",
    "violet",
    "amber",
)
_UNIFORM_ACCENTS = ("white", "gold", "black", "silver", "purple", "red", "green")
_UNIFORM_TOPS = ("tee", "button_up", "blouse")
_UNIFORM_BOTTOMS = ("trousers", "skirt")
_UNIFORM_MARKERS = ("bandana", "cap", "scarf", "necklace")
_JUSTICE_ROLE_TOKENS = ("justice", "officer", "sheriff", "deputy", "copper", "law", "jail", "court")


def _clean_text(value):
    return str(value or "").strip()


def _key(value):
    return _clean_text(value).lower().replace(" ", "_")


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _state(sim):
    state = getattr(sim, "cults", None)
    if not isinstance(state, dict):
        state = {}
        setattr(sim, "cults", state)
    state.setdefault("version", 1)
    state.setdefault("seeded", False)
    state.setdefault("cults", {})
    state.setdefault("actor_index", {})
    state.setdefault("property_index", {})
    state.setdefault("player_knowledge", {})
    state.setdefault("grievances", {})
    state.setdefault("cooldowns", {})
    state.setdefault("next_cult_id", 1)
    return state


def ensure_cult_state(sim):
    return _state(sim)


def _next_cult_id(sim):
    state = _state(sim)
    next_id = max(1, _safe_int(state.get("next_cult_id"), 1))
    state["next_cult_id"] = next_id + 1
    return f"cult-{next_id}"


def _actor_index_row(sim, actor_eid):
    state = _state(sim)
    key = str(actor_eid)
    row = state["actor_index"].get(key)
    if not isinstance(row, dict):
        row = {"active": [], "shunned": []}
        state["actor_index"][key] = row
    row.setdefault("active", [])
    row.setdefault("shunned", [])
    return row


def actor_cult_ids(sim, actor_eid, *, active_only=True):
    row = _actor_index_row(sim, actor_eid)
    ids = tuple(str(cult_id) for cult_id in tuple(row.get("active", ()) or ()) if str(cult_id))
    if active_only:
        cults = _state(sim).get("cults", {})
        return tuple(cult_id for cult_id in ids if _cult_active(cults.get(cult_id)))
    return ids


def actor_is_cult_member(sim, actor_eid, cult_id):
    return str(cult_id or "") in set(actor_cult_ids(sim, actor_eid))


def actor_is_shunned_by_cult(sim, actor_eid, cult_id):
    row = _actor_index_row(sim, actor_eid)
    return str(cult_id or "") in set(str(value) for value in tuple(row.get("shunned", ()) or ()))


def _cult_active(cult):
    return isinstance(cult, dict) and not bool(cult.get("disbanded")) and _clean_text(cult.get("cult_id"))


def _entity_name(sim, eid, default="someone"):
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    name = _clean_text(getattr(identity, "personal_name", ""))
    return name or default


def _property_name(prop, default="meeting place"):
    if not isinstance(prop, dict):
        return default
    return _clean_text(prop.get("name") or prop.get("id")) or default


def _actor_is_player(sim, eid):
    return eid is not None and int(eid) == _safe_int(getattr(sim, "player_eid", -999999), -999999)


def _is_human_actor(sim, eid):
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    if identity is None:
        return False
    if _key(getattr(identity, "taxonomy_class", "")) not in {"", "hominid"}:
        return False
    return _key(getattr(identity, "creature_type", "")) in {"", "human"}


def _is_living_actor(sim, eid):
    vitality = sim.ecs.get(Vitality).get(eid)
    return vitality is None or int(getattr(vitality, "hp", 1) or 0) > 0


def _actor_is_justice_aligned(sim, eid):
    ai = sim.ecs.get(AI).get(eid)
    occupation = sim.ecs.get(Occupation).get(eid)
    role = _key(getattr(ai, "role", ""))
    career = _key(getattr(occupation, "career", ""))
    text = f"{role} {career}"
    return any(token in text for token in _JUSTICE_ROLE_TOKENS)


def actor_eligible_for_cult(sim, eid):
    if eid is None or _actor_is_player(sim, eid):
        return False
    if not _is_human_actor(sim, eid) or not _is_living_actor(sim, eid):
        return False
    if _actor_is_justice_aligned(sim, eid):
        return False
    return True


def _eligible_humans(sim):
    rows = []
    for eid in sim.ecs.get(Position).keys():
        if actor_eligible_for_cult(sim, eid):
            rows.append(int(eid))
    return tuple(sorted(rows))


def _cult_name(rng):
    adjective = rng.choice(_CULT_ADJECTIVES)
    noun = rng.choice(_CULT_NOUNS)
    forms = (
        f"The {adjective} {noun.title()}",
        f"{adjective} {noun.title()} Society",
        f"The {noun.title()} of {adjective} Hands",
        f"{adjective} Table",
        f"The {adjective} Hour",
    )
    return rng.choice(forms)


def _flora_target(rng):
    catalog = load_flora_catalog()
    rows = [
        (plant_id, row)
        for plant_id, row in sorted(catalog.items())
        if isinstance(row, dict) and row.get("name")
    ]
    if not rows:
        return ("blush_aster", "blush aster")
    plant_id, row = rng.choice(rows)
    return (_key(plant_id), _clean_text(row.get("name")) or str(plant_id).replace("_", " "))


def _devotion_profile(rng):
    family = rng.choice((
        "leader",
        "animal",
        "flora",
        "object",
        "color",
        "place",
        "ritual",
        "silence",
        "weather",
    ))
    if family == "animal":
        target_key, label = rng.choice(_ANIMAL_TARGETS)
    elif family == "flora":
        target_key, label = _flora_target(rng)
    elif family == "object":
        target_key, label = rng.choice(_OBJECT_TARGETS)
    elif family == "color":
        target_key, label = rng.choice(_COLOR_TARGETS)
    elif family == "place":
        target_key, label = rng.choice((("locked_doors", "locked doors"), ("upper_rooms", "upper rooms"), ("old_markets", "old markets"), ("back_halls", "back halls")))
    elif family == "ritual":
        target_key, label = rng.choice((("quiet_meals", "quiet meals"), ("opened_windows", "opened windows"), ("counted_steps", "counted steps"), ("clean_counters", "clean counters")))
    elif family == "silence":
        target_key, label = rng.choice((("kept_silence", "kept silence"), ("unanswered_knocks", "unanswered knocks"), ("soft_speech", "soft speech")))
    elif family == "weather":
        target_key, label = rng.choice((("dry_rain", "dry rain"), ("morning_fog", "morning fog"), ("red_light", "red light"), ("warm_wind", "warm wind")))
    else:
        target_key, label = ("leader", "the leader")
    return {
        "family": family,
        "target_key": target_key,
        "label": label,
        "public_line": f"devotion to {label}",
    }


def _uniform_profile(rng, devotion):
    primary = rng.choice(_UNIFORM_COLORS)
    accent = rng.choice(tuple(color for color in _UNIFORM_ACCENTS if color != primary) or _UNIFORM_ACCENTS)
    marker = rng.choice(_UNIFORM_MARKERS)
    bottom = rng.choice(_UNIFORM_BOTTOMS)
    top = rng.choice(_UNIFORM_TOPS)
    if devotion.get("family") == "color":
        primary = devotion.get("target_key") or primary
    return {
        "primary_color": primary,
        "accent_color": accent,
        "top_item_id": top,
        "bottom_item_id": bottom,
        "shoe_item_id": rng.choice(("boots", "sneakers")),
        "marker_item_id": marker,
        "label": f"{primary} with {accent} mark",
    }


def _cult_profile_for_seed(sim, cult_id, leader_eid):
    rng = random.Random(f"{getattr(sim, 'seed', 0)}:cult-profile:{cult_id}:{leader_eid}")
    devotion = _devotion_profile(rng)
    name = _cult_name(rng)
    title = rng.choice(_OFFICIAL_TITLES)
    meeting_hour = rng.choice((0, 3, 4, 5, 13, 18, 22))
    severity = rng.choice(("soft", "strict", "fervent"))
    recruitment = rng.choice(("gentle", "hungry", "fervent", "sheltering"))
    uniform = _uniform_profile(rng, devotion)
    return {
        "name": name,
        "official_title": title,
        "devotion": devotion,
        "uniform": uniform,
        "meeting_hour": meeting_hour,
        "severity": severity,
        "recruitment_style": recruitment,
        "leader_known": rng.random() < 0.42,
    }


def _property_for_actor(sim, eid):
    pos = sim.ecs.get(Position).get(eid)
    if pos is None:
        return None
    from game.property_runtime import property_covering

    return property_covering(sim, int(pos.x), int(pos.y), int(pos.z))


def _property_center(prop):
    if not isinstance(prop, dict):
        return (0, 0, 0)
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
    footprint = metadata.get("footprint") if isinstance(metadata.get("footprint"), dict) else {}
    if footprint:
        try:
            x = (int(footprint.get("left")) + int(footprint.get("right"))) // 2
            y = (int(footprint.get("top")) + int(footprint.get("bottom"))) // 2
            z = int(prop.get("z", 0) or 0)
            return (x, y, z)
        except (TypeError, ValueError):
            pass
    return (_safe_int(prop.get("x"), 0), _safe_int(prop.get("y"), 0), _safe_int(prop.get("z"), 0))


def _actor_at_property(sim, eid, prop, *, radius=6):
    if not isinstance(prop, dict):
        return False
    pos = sim.ecs.get(Position).get(eid)
    if pos is None:
        return False
    if int(pos.z) != _safe_int(prop.get("z"), 0):
        return False
    current = _property_for_actor(sim, eid)
    if isinstance(current, dict) and _clean_text(current.get("id")) == _clean_text(prop.get("id")):
        return True
    x, y, _z = _property_center(prop)
    return _manhattan(int(pos.x), int(pos.y), int(x), int(y)) <= int(radius)


def _property_from_id(sim, property_id):
    prop_id = _clean_text(property_id)
    if not prop_id:
        return None
    prop = sim.properties.get(prop_id)
    return prop if isinstance(prop, dict) else None


def _workplace_property_id(occupation):
    if occupation is None:
        return ""
    workplace = getattr(occupation, "workplace", None)
    if isinstance(workplace, dict):
        return _clean_text(workplace.get("property_id"))
    if isinstance(workplace, str):
        return _clean_text(workplace)
    return ""


def _member_work_property(sim, eid):
    settlement = sim.ecs.get(NPCSettlement).get(eid)
    if settlement is not None:
        prop = _property_from_id(sim, getattr(settlement, "work_property_id", ""))
        if isinstance(prop, dict):
            return prop
    occupation = sim.ecs.get(Occupation).get(eid)
    return _property_from_id(sim, _workplace_property_id(occupation))


def _member_home_property(sim, eid):
    settlement = sim.ecs.get(NPCSettlement).get(eid)
    if settlement is None:
        return None
    return _property_from_id(sim, getattr(settlement, "home_property_id", ""))


def _member_anchor_property(sim, eid):
    prop = _member_work_property(sim, eid)
    if isinstance(prop, dict):
        return prop
    prop = _member_home_property(sim, eid)
    if isinstance(prop, dict):
        return prop
    return _property_for_actor(sim, eid)


def _property_chunk_key(sim, prop):
    if not isinstance(prop, dict):
        return None
    x, y, _z = _property_center(prop)
    return sim.chunk_coords(int(x), int(y))


def _active_cult_rows(cult, *, roles=None, exclude_roles=()):
    wanted = {_key(role) for role in tuple(roles or ()) if _key(role)}
    excluded = {_key(role) for role in tuple(exclude_roles or ()) if _key(role)}
    rows = []
    for raw_eid, row in dict(cult.get("members", {}) or {}).items():
        if not isinstance(row, dict) or not bool(row.get("active", True)):
            continue
        role = _key(row.get("role")) or "member"
        if wanted and role not in wanted:
            continue
        if excluded and role in excluded:
            continue
        eid = _safe_int(raw_eid, -1)
        if eid <= 0:
            continue
        rows.append((eid, row))
    return tuple(sorted(rows, key=lambda pair: pair[0]))


def _refresh_membership_counts(cult):
    counts = {"leader": 0, "official": 0, "member": 0, "bodyguard": 0, "active": 0}
    for _eid, row in _active_cult_rows(cult):
        role = _key(row.get("role")) or "member"
        if role not in counts:
            counts[role] = 0
        counts[role] += 1
        counts["active"] += 1
    cult["membership_counts"] = counts
    return counts


def _membership_counts(cult):
    counts = cult.get("membership_counts")
    if not isinstance(counts, dict):
        counts = _refresh_membership_counts(cult)
    return counts


def _set_role_lists_from_members(cult):
    leaders = []
    officials = []
    members = []
    bodyguards = []
    for eid, row in _active_cult_rows(cult):
        role = _key(row.get("role")) or "member"
        if role == "leader":
            leaders.append(eid)
        elif role == "official":
            officials.append(eid)
        elif role == "bodyguard":
            bodyguards.append(eid)
        else:
            members.append(eid)
    if leaders:
        cult["leader_eid"] = int(leaders[0])
    cult["official_eids"] = tuple(sorted(officials))
    cult["member_eids"] = tuple(sorted(members))
    cult["bodyguard_eids"] = tuple(sorted(bodyguards))
    _refresh_membership_counts(cult)


def _active_official_count(cult):
    return _safe_int(_membership_counts(cult).get("official"), 0)


def _ordinary_member_count(cult):
    return _safe_int(_membership_counts(cult).get("member"), 0)


def _official_target_count(cult):
    count = _ordinary_member_count(cult)
    if count <= 0:
        return 0
    return (count + CULT_MEMBERS_PER_OFFICIAL - 1) // CULT_MEMBERS_PER_OFFICIAL


def _meeting_property(sim, cult):
    return _property_from_id(sim, cult.get("meeting", {}).get("property_id"))


def _coverage_property_for_promotion(sim, cult, promoted_eid):
    meeting_prop_id = _clean_text(cult.get("meeting", {}).get("property_id"))
    official_counts = {}
    for _eid, row in _active_cult_rows(cult, roles=("official",)):
        prop_id = _clean_text(row.get("coverage_property_id") or row.get("site_property_id"))
        prop = _property_from_id(sim, prop_id)
        chunk = _property_chunk_key(sim, prop)
        if chunk is not None:
            official_counts[chunk] = official_counts.get(chunk, 0) + 1

    regions = {}
    for eid, _row in _active_cult_rows(cult, roles=("member",)):
        work_prop = _member_work_property(sim, eid)
        home_prop = _member_home_property(sim, eid)
        current_prop = _property_for_actor(sim, eid)
        anchor_prop = work_prop or home_prop or current_prop
        chunk = _property_chunk_key(sim, anchor_prop)
        if chunk is None:
            continue
        row = regions.setdefault(chunk, {
            "chunk": chunk,
            "member_count": 0,
            "work_props": {},
            "home_props": {},
            "current_props": {},
            "host_eids": {},
        })
        row["member_count"] += 1
        for bucket_name, prop in (("work_props", work_prop), ("home_props", home_prop), ("current_props", current_prop)):
            if not isinstance(prop, dict):
                continue
            prop_id = _clean_text(prop.get("id"))
            if not prop_id:
                continue
            if bucket_name == "current_props" and prop_id == meeting_prop_id:
                continue
            bucket = row[bucket_name]
            bucket[prop_id] = bucket.get(prop_id, 0) + 1
            if bucket_name == "home_props":
                row["host_eids"].setdefault(prop_id, eid)

    best_region = None
    best_region_score = None
    for chunk, row in regions.items():
        count = int(row.get("member_count", 0))
        score = count - (int(official_counts.get(chunk, 0)) * CULT_MEMBERS_PER_OFFICIAL)
        sort_key = (score, count, -abs(chunk[0]), -abs(chunk[1]), str(chunk))
        if best_region is None or sort_key > best_region_score:
            best_region = row
            best_region_score = sort_key
    if not best_region:
        prop = _meeting_property(sim, cult)
        if isinstance(prop, dict):
            return {
                "property_id": _clean_text(prop.get("id")),
                "property_name": _property_name(prop, "meeting place"),
                "member_count": 0,
                "official_count": 0,
                "score": 0,
                "coverage_kind": "meeting_fallback",
            }
        return {}

    def _pick_prop(bucket):
        if not isinstance(bucket, dict) or not bucket:
            return None
        prop_id, count = sorted(bucket.items(), key=lambda item: (int(item[1]), _clean_text(item[0])), reverse=True)[0]
        prop = _property_from_id(sim, prop_id)
        if not isinstance(prop, dict):
            return None
        return prop, int(count)

    picked = _pick_prop(best_region.get("work_props"))
    coverage_kind = "member_work"
    if picked is None:
        picked = _pick_prop(best_region.get("home_props"))
        coverage_kind = "member_home_host"
    if picked is None:
        picked = _pick_prop(best_region.get("current_props"))
        coverage_kind = "member_current"
    if picked is None:
        prop = _meeting_property(sim, cult)
        if isinstance(prop, dict):
            picked = (prop, 0)
            coverage_kind = "meeting_fallback"
    if picked is None:
        return {}

    prop, prop_count = picked
    prop_id = _clean_text(prop.get("id"))
    host_prop_id = ""
    host_eid = None
    home_pick = _pick_prop(best_region.get("home_props"))
    if home_pick is not None:
        host_prop, _host_count = home_pick
        host_prop_id = _clean_text(host_prop.get("id"))
        host_eid = best_region.get("host_eids", {}).get(host_prop_id)
    if coverage_kind == "member_home_host":
        host_prop_id = prop_id
        host_eid = best_region.get("host_eids", {}).get(prop_id)

    chunk = best_region.get("chunk")
    score = int(best_region.get("member_count", 0)) - (int(official_counts.get(chunk, 0)) * CULT_MEMBERS_PER_OFFICIAL)
    return {
        "property_id": prop_id,
        "property_name": _property_name(prop, "coverage site"),
        "member_count": int(best_region.get("member_count", prop_count) or prop_count),
        "official_count": int(official_counts.get(chunk, 0)),
        "score": int(score),
        "coverage_kind": coverage_kind,
        "host_actor_eid": int(host_eid) if host_eid is not None else None,
        "host_property_id": host_prop_id,
        "host_property_name": _property_name(_property_from_id(sim, host_prop_id), "member home") if host_prop_id else "",
        "chunk": chunk,
    }


def _meeting_property_for(sim, leader_eid, officials=()):
    for eid in (leader_eid,) + tuple(officials or ()):
        prop = _property_for_actor(sim, eid)
        if isinstance(prop, dict):
            return prop
    props = [
        prop
        for prop in sim.properties.values()
        if isinstance(prop, dict) and _key(prop.get("kind")) == "building"
    ]
    return sorted(props, key=lambda prop: _clean_text(prop.get("id")))[0] if props else None


def _create_cult(sim, *, leader_eid, officials=(), members=(), cult_id=None):
    cult_id = cult_id or _next_cult_id(sim)
    profile = _cult_profile_for_seed(sim, cult_id, leader_eid)
    meeting_prop = _meeting_property_for(sim, leader_eid, officials=officials)
    org_eid = ensure_organization(
        sim,
        organization_key=f"cult:{cult_id}",
        organization_name=profile["name"],
        organization_kind=CULT_KIND,
        tags=("cult", "fictional", _key(profile["devotion"].get("family")), f"devotion:{_key(profile['devotion'].get('target_key'))}"),
    )
    cult = {
        "cult_id": cult_id,
        "organization_eid": org_eid,
        "name": profile["name"],
        "leader_eid": int(leader_eid),
        "leader_known": bool(profile.get("leader_known")),
        "official_eids": tuple(int(eid) for eid in officials),
        "member_eids": tuple(int(eid) for eid in members),
        "bodyguard_eids": (),
        "official_title": profile["official_title"],
        "devotion": dict(profile["devotion"]),
        "uniform": dict(profile["uniform"]),
        "meeting": {
            "property_id": meeting_prop.get("id") if isinstance(meeting_prop, dict) else "",
            "property_name": _property_name(meeting_prop, "meeting place"),
            "hour": int(profile["meeting_hour"]),
            "last_day": -1,
            "active_until_tick": 0,
        },
        "severity": profile["severity"],
        "recruitment_style": profile["recruitment_style"],
        "members": {},
        "shunned_eids": {},
        "pending_grievances": [],
        "known_grievances": [],
        "created_tick": _safe_int(getattr(sim, "tick", 0), 0),
        "membership_counts": {"leader": 0, "official": 0, "member": 0, "bodyguard": 0, "active": 0},
        "crisis": {},
        "disbanded": False,
    }
    _state(sim)["cults"][cult_id] = cult
    if isinstance(meeting_prop, dict):
        _state(sim)["property_index"].setdefault(_clean_text(meeting_prop.get("id")), [])
        if cult_id not in _state(sim)["property_index"][_clean_text(meeting_prop.get("id"))]:
            _state(sim)["property_index"][_clean_text(meeting_prop.get("id"))].append(cult_id)
    join_cult(sim, leader_eid, cult_id, role="leader", title="leader", issue_uniform=True, auto_equip=True, allow_player_multi=True)
    for eid in officials:
        join_cult(sim, eid, cult_id, role="official", title=profile["official_title"], issue_uniform=True, auto_equip=True)
    for eid in members:
        join_cult(sim, eid, cult_id, role="member", title="member", issue_uniform=True, auto_equip=True)
    bodyguards = create_bodyguard_detail_for_principal(
        sim,
        leader_eid,
        meeting_prop,
        count=2,
        tier="pair",
        hired_by_eid=leader_eid,
        source_kind="cult",
        source_id=cult_id,
    )
    if bodyguards.get("ok"):
        cult["bodyguard_eids"] = tuple(bodyguards.get("guard_eids", ()) or ())
        for guard_eid in cult["bodyguard_eids"]:
            join_cult(sim, guard_eid, cult_id, role="bodyguard", title="bodyguard", issue_uniform=False, auto_equip=False)
    _set_role_lists_from_members(cult)
    sim.emit(Event(
        "cult_seeded",
        cult_id=cult_id,
        cult_name=cult["name"],
        organization_eid=org_eid,
        leader_eid=leader_eid,
        meeting_property_id=cult["meeting"].get("property_id"),
        devotion_family=cult["devotion"].get("family"),
        devotion_label=cult["devotion"].get("label"),
    ))
    return cult


def seed_cults_if_needed(sim, *, force=False, target_count=None):
    state = _state(sim)
    if state.get("seeded") and not force:
        return ()
    if not force:
        state["seeded"] = True
    rng = random.Random(f"{getattr(sim, 'seed', 0)}:cult-seed")
    if not force and rng.random() > 0.28:
        return ()
    target_count = int(target_count) if target_count is not None else (1 + (1 if rng.random() < 0.08 else 0))
    candidates = list(_eligible_humans(sim))
    created = []
    for _idx in range(max(0, target_count)):
        available = [eid for eid in candidates if not actor_cult_ids(sim, eid)]
        if len(available) < 3:
            break
        leader = rng.choice(available)
        available.remove(leader)
        official_count = min(len(available), rng.choice((1, 1, 2, 3)))
        officials = tuple(rng.sample(available, official_count))
        for eid in officials:
            if eid in available:
                available.remove(eid)
        member_count = min(len(available), rng.choice((1, 2, 3, 4, 5)))
        members = tuple(rng.sample(available, member_count)) if member_count > 0 else ()
        cult = _create_cult(sim, leader_eid=leader, officials=officials, members=members)
        created.append(cult)
        for eid in (leader,) + officials + members:
            if eid in candidates:
                candidates.remove(eid)
    return tuple(created)


def _membership_row(cult, actor_eid):
    if not isinstance(cult, dict):
        return None
    return cult.setdefault("members", {}).get(str(actor_eid))


def cult_for_property(sim, prop):
    if not isinstance(prop, dict):
        return None
    prop_id = _clean_text(prop.get("id"))
    cult_ids = tuple(_state(sim).get("property_index", {}).get(prop_id, ()) or ())
    for cult_id in cult_ids:
        cult = _state(sim).get("cults", {}).get(cult_id)
        if _cult_active(cult):
            return cult
    for cult in _state(sim).get("cults", {}).values():
        if _cult_active(cult) and _clean_text(cult.get("meeting", {}).get("property_id")) == prop_id:
            return cult
    return None


def cult_property_association(sim, prop):
    cult = cult_for_property(sim, prop)
    if not _cult_active(cult) or not isinstance(prop, dict):
        return {}
    prop_id = _clean_text(prop.get("id"))
    if not prop_id:
        return {}
    meeting_id = _clean_text(cult.get("meeting", {}).get("property_id"))
    if prop_id == meeting_id:
        return {"cult": cult, "kind": "meeting", "always_contact": True}
    for raw_eid, row in dict(cult.get("members", {}) or {}).items():
        if not isinstance(row, dict) or not bool(row.get("active", True)):
            continue
        if _clean_text(row.get("absorbed_service_property_id")) == prop_id:
            role = _key(row.get("role"))
            row_eid = _safe_int(raw_eid, 0)
            official_eid = _safe_int(row.get("absorbed_by_official_eid"), 0)
            service_actor_eid = row_eid
            if role == "official":
                official_eid = row_eid
                service_actor_eid = _safe_int(row.get("service_site_recruit_eid"), 0)
            return {
                "cult": cult,
                "kind": "absorbed_service",
                "official_eid": official_eid,
                "service_actor_eid": service_actor_eid,
                "always_contact": True,
            }
        if _clean_text(row.get("coverage_property_id")) == prop_id:
            return {"cult": cult, "kind": "coverage", "official_eid": _safe_int(raw_eid, 0), "always_contact": True}
    return {}


def cult_service_cost_multiplier(sim, prop, actor_eid):
    assoc = cult_property_association(sim, prop)
    cult = assoc.get("cult") if isinstance(assoc, dict) else None
    if not _cult_active(cult):
        return 1.0
    if actor_eid is not None and actor_is_cult_member(sim, actor_eid, cult.get("cult_id")):
        return 1.0
    return CULT_NONMEMBER_SERVICE_TAX_MULT


def player_knows_cult(sim, actor_eid, cult):
    if not _cult_active(cult):
        return False
    if actor_is_cult_member(sim, actor_eid, cult.get("cult_id")):
        return True
    knowledge = _state(sim).get("player_knowledge", {})
    row = knowledge.get(str(actor_eid), {}) if isinstance(knowledge, dict) else {}
    return str(cult.get("cult_id")) in set(row.get("known_cults", ()) or ())


def mark_cult_known(sim, actor_eid, cult_id, *, source="seen"):
    state = _state(sim)
    row = state["player_knowledge"].setdefault(str(actor_eid), {"known_cults": [], "sources": {}})
    row.setdefault("known_cults", [])
    if cult_id not in row["known_cults"]:
        row["known_cults"].append(cult_id)
    row.setdefault("sources", {})[cult_id] = _clean_text(source) or "seen"


def _slots_for_item(item_id):
    profile = ITEM_CATALOG.get(item_id, {}) if isinstance(ITEM_CATALOG, dict) else {}
    slots = tuple(profile.get("appearance_slots", ()) or profile.get("slots", ()) or ())
    if slots:
        return slots
    return {
        "tee": ("top",),
        "button_up": ("top",),
        "blouse": ("top",),
        "trousers": ("bottom",),
        "skirt": ("bottom",),
        "dress": ("full_body",),
        "boots": ("shoes",),
        "sneakers": ("shoes",),
        "bandana": ("hat",),
        "cap": ("hat",),
        "scarf": ("necklace",),
        "necklace": ("necklace",),
    }.get(_key(item_id), ())


def _metadata_for_uniform_piece(sim, eid, cult, item_id, slot, *, seed_token=""):
    uniform = dict(cult.get("uniform", {}) or {})
    primary = _clean_text(uniform.get("primary_color")) or "purple"
    accent = _clean_text(uniform.get("accent_color")) or "white"
    metadata = cosmetic_variant_metadata(item_id, seed_token=seed_token, item_catalog=ITEM_CATALOG)
    nested = dict(metadata.get(APPEARANCE_METADATA_KEY) or {})
    nested["color"] = primary
    nested["accent_color"] = accent
    nested["cult_id"] = cult.get("cult_id")
    nested["cult_name"] = cult.get("name")
    nested["cult_uniform"] = True
    nested["worn_slot"] = slot
    metadata[APPEARANCE_METADATA_KEY] = nested
    metadata["color"] = primary
    metadata["accent_color"] = accent
    metadata["cult_id"] = cult.get("cult_id")
    metadata["cult_name"] = cult.get("name")
    metadata["cult_uniform"] = True
    metadata["appearance_slot"] = slot
    metadata["source"] = "cult_uniform"
    metadata["display_name"] = f"{primary.title()} {item_display_name(item_id, metadata=metadata, item_catalog=ITEM_CATALOG)}"
    return metadata


def cult_uniform_piece_specs(sim, eid, cult):
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    gender = normalize_gender_identity(getattr(identity, "gender_identity", ""), default="nonbinary") if identity else "nonbinary"
    uniform = dict(cult.get("uniform", {}) or {})
    top = _key(uniform.get("top_item_id")) or "tee"
    bottom = _key(uniform.get("bottom_item_id")) or "trousers"
    if top == "blouse" and gender == "man":
        top = "button_up"
    if top == "button_up" and gender == "woman" and _key(uniform.get("top_item_id")) == "blouse":
        top = "blouse"
    if bottom == "skirt" and gender == "man":
        bottom = "trousers"
    marker = _key(uniform.get("marker_item_id")) or "bandana"
    pieces = [top, bottom, _key(uniform.get("shoe_item_id")) or "boots", marker]
    specs = []
    seen_slots = set()
    for item_id in pieces:
        if item_id not in ITEM_CATALOG:
            continue
        slots = _slots_for_item(item_id)
        slot = slots[0] if slots else ""
        if not slot or slot in seen_slots:
            continue
        seen_slots.add(slot)
        specs.append((item_id, slot))
    return tuple(specs)


def issue_cult_uniform(sim, eid, cult, *, auto_equip=False, free=True):
    inventory = sim.ecs.get(Inventory).get(eid)
    if inventory is None:
        return {"ok": False, "reason": "no_inventory", "items": (), "missing": ()}
    issued = []
    missing = []
    for item_id, slot in cult_uniform_piece_specs(sim, eid, cult):
        item_def = ITEM_CATALOG.get(item_id, {})
        metadata = _metadata_for_uniform_piece(
            sim,
            eid,
            cult,
            item_id,
            slot,
            seed_token=f"{getattr(sim, 'seed', 0)}:{cult.get('cult_id')}:{eid}:{item_id}:{slot}",
        )
        added, instance_id = inventory.add_item(
            item_id=item_id,
            quantity=1,
            stack_max=int(item_def.get("stack_max", 1) or 1),
            instance_factory=sim.new_item_instance_id,
            owner_eid=eid,
            owner_tag="player" if _actor_is_player(sim, eid) else "npc",
            metadata=metadata,
        )
        if not added or not instance_id:
            missing.append({"item_id": item_id, "slot": slot})
            continue
        if auto_equip:
            try:
                unequip_appearance_slot(sim, eid, slot)
            except Exception:
                pass
            equip_appearance_item(sim, eid, instance_id, preferred_slot=slot)
        issued.append({
            "item_id": item_id,
            "slot": slot,
            "instance_id": instance_id,
            "item_name": item_display_name(item_id, metadata=metadata, item_catalog=ITEM_CATALOG),
        })
    return {"ok": True, "items": tuple(issued), "missing": tuple(missing), "free": bool(free)}


def _actor_has_uniform_piece(sim, eid, cult, slot):
    inventory = sim.ecs.get(Inventory).get(eid)
    if inventory is None:
        return False
    for entry in tuple(getattr(inventory, "items", ()) or ()):
        metadata = entry.get("metadata") if isinstance(entry, dict) else {}
        if not isinstance(metadata, dict):
            continue
        if _clean_text(metadata.get("cult_id")) != _clean_text(cult.get("cult_id")):
            continue
        if not bool(metadata.get(APPEARANCE_WORN_METADATA_KEY)):
            continue
        nested = metadata.get(APPEARANCE_METADATA_KEY)
        worn_slot = _clean_text(metadata.get(APPEARANCE_SLOT_METADATA_KEY) or (nested or {}).get("worn_slot"))
        if worn_slot == slot:
            return True
    return False


def actor_in_cult_uniform(sim, eid, cult):
    for _item_id, slot in cult_uniform_piece_specs(sim, eid, cult):
        if not _actor_has_uniform_piece(sim, eid, cult, slot):
            return False
    return True


def join_cult(
    sim,
    actor_eid,
    cult_id,
    *,
    role="member",
    title="member",
    issue_uniform=True,
    auto_equip=False,
    allow_player_multi=False,
):
    state = _state(sim)
    cult = state.get("cults", {}).get(str(cult_id))
    if not _cult_active(cult):
        return {"ok": False, "reason": "invalid_cult"}
    is_player = _actor_is_player(sim, actor_eid)
    if not is_player and not allow_player_multi:
        existing = [cid for cid in actor_cult_ids(sim, actor_eid) if cid != cult_id]
        if existing:
            return {"ok": False, "reason": "npc_already_in_cult", "cult_id": existing[0]}
    if actor_is_shunned_by_cult(sim, actor_eid, cult_id):
        return {"ok": False, "reason": "shunned", "cult_id": cult_id}
    role = _key(role) or "member"
    tick = _safe_int(getattr(sim, "tick", 0), 0)
    row = {
        "actor_eid": int(actor_eid),
        "role": role,
        "title": _clean_text(title) or role,
        "joined_tick": tick,
        "active": True,
        "grace_until_tick": tick + CULT_PLAYER_GRACE_TICKS if is_player else tick,
        "uniform_missing": [],
    }
    cult.setdefault("members", {})[str(actor_eid)] = row
    if role == "leader":
        cult["leader_eid"] = int(actor_eid)
    elif role == "official":
        officials = list(cult.get("official_eids", ()) or ())
        if int(actor_eid) not in officials:
            officials.append(int(actor_eid))
            cult["official_eids"] = tuple(sorted(officials))
    elif role == "bodyguard":
        guards = list(cult.get("bodyguard_eids", ()) or ())
        if int(actor_eid) not in guards:
            guards.append(int(actor_eid))
            cult["bodyguard_eids"] = tuple(sorted(guards))
    else:
        members = list(cult.get("member_eids", ()) or ())
        if int(actor_eid) not in members:
            members.append(int(actor_eid))
            cult["member_eids"] = tuple(sorted(members))
    _set_role_lists_from_members(cult)
    idx = _actor_index_row(sim, actor_eid)
    if cult_id not in idx["active"]:
        idx["active"].append(cult_id)
    assign_actor_organization(
        sim,
        actor_eid,
        organization_eid=cult.get("organization_eid"),
        organization_name=cult.get("name"),
        organization_kind=CULT_KIND,
        tags=("cult",),
        role=role,
        kind="membership",
        title=row["title"],
        primary=False,
        authority_rank={"leader": 5, "official": 25, "bodyguard": 35, "member": 70}.get(role, 70),
        site_property_id=cult.get("meeting", {}).get("property_id"),
        active=True,
    )
    uniform = {"items": (), "missing": ()}
    if issue_uniform:
        uniform = issue_cult_uniform(sim, actor_eid, cult, auto_equip=bool(auto_equip), free=True)
        row["uniform_missing"] = list(uniform.get("missing", ()) or ())
    if is_player:
        mark_cult_known(sim, actor_eid, cult_id, source="joined")
    sim.emit(Event(
        "cult_joined",
        eid=actor_eid,
        cult_id=cult_id,
        cult_name=cult.get("name"),
        role=role,
        title=row["title"],
        grace_until_tick=row["grace_until_tick"],
        issued_items=tuple(uniform.get("items", ()) or ()),
        missing_items=tuple(uniform.get("missing", ()) or ()),
        player_visible=_actor_is_player(sim, actor_eid),
    ))
    return {"ok": True, "cult_id": cult_id, "membership": row, "uniform": uniform}


def leave_cult(sim, actor_eid, cult_id, *, reason="left"):
    cult = _state(sim).get("cults", {}).get(str(cult_id))
    if not _cult_active(cult):
        return {"ok": False, "reason": "invalid_cult"}
    row = cult.setdefault("members", {}).get(str(actor_eid))
    if not isinstance(row, dict) or not bool(row.get("active", True)):
        return {"ok": False, "reason": "not_member"}
    row["active"] = False
    row["left_tick"] = _safe_int(getattr(sim, "tick", 0), 0)
    row["left_reason"] = _clean_text(reason) or "left"
    _set_role_lists_from_members(cult)
    idx = _actor_index_row(sim, actor_eid)
    idx["active"] = [cid for cid in idx.get("active", []) if cid != cult_id]
    record_cult_grievance(sim, cult_id, actor_eid, violation_kind="left_cult", witness_eid=None, immediate=True)
    return {"ok": True, "cult_id": cult_id}


def _nearby_cult_member_witnesses(sim, cult, x, y, z, *, exclude_eid=None, radius=10):
    witnesses = []
    positions = sim.ecs.get(Position)
    for raw_eid, member in dict(cult.get("members", {}) or {}).items():
        if not isinstance(member, dict) or not bool(member.get("active", True)):
            continue
        eid = _safe_int(raw_eid, -1)
        if eid <= 0 or eid == exclude_eid:
            continue
        pos = positions.get(eid)
        if pos is None or int(pos.z) != int(z):
            continue
        if _manhattan(int(pos.x), int(pos.y), int(x), int(y)) > radius:
            continue
        if has_line_of_sight(sim, int(pos.x), int(pos.y), int(pos.z), int(x), int(y), int(z)):
            witnesses.append(eid)
    return tuple(witnesses)


def record_cult_grievance(sim, cult_id, actor_eid, *, violation_kind, witness_eid=None, target_label="", immediate=False):
    cult = _state(sim).get("cults", {}).get(str(cult_id))
    if not _cult_active(cult):
        return None
    tick = _safe_int(getattr(sim, "tick", 0), 0)
    grievance_id = f"{cult_id}:grievance:{len(_state(sim)['grievances']) + 1}"
    row = {
        "grievance_id": grievance_id,
        "cult_id": cult_id,
        "actor_eid": int(actor_eid) if actor_eid is not None else None,
        "violation_kind": _key(violation_kind),
        "target_label": _clean_text(target_label),
        "witness_eid": int(witness_eid) if witness_eid is not None else None,
        "created_tick": tick,
        "propagated": False,
    }
    _state(sim)["grievances"][grievance_id] = row
    cult.setdefault("pending_grievances", []).append(grievance_id)
    if immediate:
        _mark_actor_shunned(sim, cult, actor_eid, grievance_id=grievance_id)
    sim.emit(Event(
        "cult_grievance_recorded",
        cult_id=cult_id,
        cult_name=cult.get("name"),
        actor_eid=actor_eid,
        witness_eid=witness_eid,
        violation_kind=row["violation_kind"],
        target_label=row["target_label"],
        grievance_id=grievance_id,
    ))
    return row


def _mark_actor_shunned(sim, cult, actor_eid, *, grievance_id=""):
    if actor_eid is None:
        return False
    cult_id = _clean_text(cult.get("cult_id"))
    cult.setdefault("shunned_eids", {})[str(actor_eid)] = {
        "actor_eid": int(actor_eid),
        "since_tick": _safe_int(getattr(sim, "tick", 0), 0),
        "grievance_id": _clean_text(grievance_id),
    }
    idx = _actor_index_row(sim, actor_eid)
    if cult_id not in idx["shunned"]:
        idx["shunned"].append(cult_id)
    sim.emit(Event(
        "cult_shunned",
        cult_id=cult_id,
        cult_name=cult.get("name"),
        actor_eid=actor_eid,
        grievance_id=grievance_id,
    ))
    return True


def propagate_cult_grievances(sim, cult):
    if not _cult_active(cult):
        return ()
    propagated = []
    pending = list(cult.get("pending_grievances", ()) or ())
    for grievance_id in pending[:CULT_PROPAGATION_LIMIT]:
        grievance = _state(sim).get("grievances", {}).get(grievance_id)
        if not isinstance(grievance, dict) or grievance.get("propagated"):
            continue
        grievance["propagated"] = True
        grievance["propagated_tick"] = _safe_int(getattr(sim, "tick", 0), 0)
        cult.setdefault("known_grievances", []).append(grievance_id)
        _mark_actor_shunned(sim, cult, grievance.get("actor_eid"), grievance_id=grievance_id)
        propagated.append(grievance_id)
    cult["pending_grievances"] = [gid for gid in pending if gid not in set(propagated)]
    return tuple(propagated)


def _world_day_hour(sim):
    clock = getattr(sim, "world_traits", {}).get("clock", {}) if isinstance(getattr(sim, "world_traits", None), dict) else {}
    ticks_per_hour = max(1, _safe_int(clock.get("ticks_per_hour"), 600))
    start_hour = _safe_int(clock.get("start_hour"), 8)
    tick = _safe_int(getattr(sim, "tick", 0), 0)
    total_hours = start_hour + (tick // ticks_per_hour)
    return total_hours // 24, total_hours % 24


def cult_services_for_property(sim, prop, *, actor_eid=None):
    cult = cult_for_property(sim, prop)
    if not _cult_active(cult):
        return ()
    cult_id = cult.get("cult_id")
    if actor_eid is not None and actor_is_shunned_by_cult(sim, actor_eid, cult_id):
        return ("cult_contact",)
    if actor_eid is not None and actor_is_cult_member(sim, actor_eid, cult_id):
        return ("cult_contact", "cult_donation", "cult_uniform_replacement", "cult_meeting_info", "cult_leader_audience", "cult_leave")
    return ("cult_conversion", "cult_donation")


def _cult_service_lines(sim, actor_eid, cult, service):
    devotion = dict(cult.get("devotion", {}) or {})
    meeting = dict(cult.get("meeting", {}) or {})
    uniform = dict(cult.get("uniform", {}) or {})
    service = _key(service)
    if service == "cult_contact":
        return (
            f"{cult.get('name')} keeps its contact here.",
            f"The posted shape is {devotion.get('public_line', 'a private devotion')}; dress reads {uniform.get('label', 'matched clothes')}.",
        )
    if service == "cult_conversion":
        return (
            f"{cult.get('name')} offers membership.",
            f"Code: {devotion.get('public_line', 'follow the circle')}. Uniform: {uniform.get('label', 'matched clothes')}.",
            "Joining provides the outfit as real clothing. You get 24 hours before members treat dress-code failure as a violation.",
            "Leaving or breaking the code in front of members can get you shunned from cult business.",
        )
    if service == "cult_meeting_info":
        return (
            f"Meeting: {meeting.get('property_name', 'the meeting place')} around {int(meeting.get('hour', 0)):02d}:00.",
            "Members know the door. Outsiders mostly see the clothes and the traffic.",
        )
    if service == "cult_leader_audience":
        if cult.get("leader_known"):
            return (f"The leader is {_entity_name(sim, cult.get('leader_eid'), 'known to the circle')}. Audience is still by favor, not by demand.",)
        return ("The leader is not presented to every new face. Officials decide when a voice reaches the center.",)
    return (f"{cult.get('name')} handles the request.",)


def apply_cult_service(sim, actor_eid, prop, service, request=None):
    service = _key(service)
    cult = cult_for_property(sim, prop)
    if not _cult_active(cult):
        return {"ok": False, "reason": "no_cult", "service": service}
    cult_id = cult.get("cult_id")
    if actor_is_shunned_by_cult(sim, actor_eid, cult_id):
        return {
            "ok": False,
            "reason": "shunned",
            "service": service,
            "cult_id": cult_id,
            "cult_name": cult.get("name"),
            "lines": (
                f"{cult.get('name')} will not do business with you.",
                "Their people have carried the grievance through the circle.",
            ),
        }
    if service == "cult_conversion":
        if actor_is_cult_member(sim, actor_eid, cult_id):
            return {"ok": True, "service": service, "cult_id": cult_id, "cult_name": cult.get("name"), "lines": ("You are already counted among them.",)}
        result = join_cult(
            sim,
            actor_eid,
            cult_id,
            role="member",
            title="member",
            issue_uniform=True,
            auto_equip=False,
            allow_player_multi=_actor_is_player(sim, actor_eid),
        )
        if not result.get("ok"):
            return {"ok": False, "reason": result.get("reason", "blocked"), "service": service, "cult_id": cult_id, "cult_name": cult.get("name")}
        lines = list(_cult_service_lines(sim, actor_eid, cult, service))
        uniform = result.get("uniform", {}) if isinstance(result.get("uniform"), dict) else {}
        issued = tuple(uniform.get("items", ()) or ())
        missing = tuple(uniform.get("missing", ()) or ())
        if issued:
            lines.append("Received: " + ", ".join(str(row.get("item_name", row.get("item_id"))) for row in issued) + ".")
        if missing:
            lines.append("Your bag was full for part of the uniform. Come back within the 24-hour grace and they will issue the missing pieces free.")
        sim.emit(Event("cult_player_conversion" if _actor_is_player(sim, actor_eid) else "cult_npc_conversion", eid=actor_eid, cult_id=cult_id, cult_name=cult.get("name")))
        return {"ok": True, "service": service, "cult_id": cult_id, "cult_name": cult.get("name"), "lines": tuple(lines)}
    if service == "cult_uniform_replacement":
        if not actor_is_cult_member(sim, actor_eid, cult_id):
            return {"ok": False, "reason": "not_member", "service": service, "cult_id": cult_id, "cult_name": cult.get("name")}
        row = _membership_row(cult, actor_eid) or {}
        tick = _safe_int(getattr(sim, "tick", 0), 0)
        free = tick <= _safe_int(row.get("grace_until_tick"), 0)
        cost = 0 if free else 18
        assets = sim.ecs.get(PlayerAssets).get(actor_eid)
        if cost > 0 and (assets is None or int(getattr(assets, "credits", 0) or 0) < cost):
            return {"ok": False, "reason": "no_credits", "service": service, "cult_id": cult_id, "cult_name": cult.get("name"), "cost": cost, "credits": int(getattr(assets, "credits", 0) or 0) if assets else 0}
        if cost > 0:
            assets.credits = max(0, int(getattr(assets, "credits", 0) or 0) - cost)
        uniform = issue_cult_uniform(sim, actor_eid, cult, auto_equip=False, free=free)
        lines = [f"{cult.get('name')} issues replacement dress pieces."]
        if cost:
            lines.append(f"Replacement cost {cost}c.")
        if uniform.get("missing"):
            lines.append("Your bag is still too full for every piece.")
        return {"ok": True, "service": service, "cult_id": cult_id, "cult_name": cult.get("name"), "lines": tuple(lines), "credits_spent": cost}
    if service == "cult_donation":
        cost = 12 if actor_is_cult_member(sim, actor_eid, cult_id) else 35
        assets = sim.ecs.get(PlayerAssets).get(actor_eid)
        if assets is None or int(getattr(assets, "credits", 0) or 0) < cost:
            return {"ok": False, "reason": "no_credits", "service": service, "cult_id": cult_id, "cult_name": cult.get("name"), "cost": cost, "credits": int(getattr(assets, "credits", 0) or 0) if assets else 0}
        assets.credits = max(0, int(getattr(assets, "credits", 0) or 0) - cost)
        cult["donations"] = int(cult.get("donations", 0) or 0) + cost
        return {"ok": True, "service": service, "cult_id": cult_id, "cult_name": cult.get("name"), "lines": (f"You give {cost}c to {cult.get('name')}.", "An official records the gift without making it feel optional."), "credits_spent": cost}
    if service == "cult_leave":
        result = leave_cult(sim, actor_eid, cult_id, reason="voluntary")
        if not result.get("ok"):
            return {"ok": False, "reason": result.get("reason", "blocked"), "service": service, "cult_id": cult_id, "cult_name": cult.get("name")}
        return {"ok": True, "service": service, "cult_id": cult_id, "cult_name": cult.get("name"), "lines": (f"You step out of {cult.get('name')}.", "The circle will remember the exit while the leader still stands.")}
    return {"ok": True, "service": service, "cult_id": cult_id, "cult_name": cult.get("name"), "lines": _cult_service_lines(sim, actor_eid, cult, service)}


def _actor_need_score(sim, eid):
    needs = sim.ecs.get(NPCNeeds).get(eid)
    if needs is None:
        return 0.0
    hunger = 100.0 - float(getattr(needs, "hunger", 100.0) or 100.0)
    thirst = 100.0 - float(getattr(needs, "thirst", 100.0) or 100.0)
    sleep = 100.0 - float(getattr(needs, "sleep", 100.0) or 100.0)
    return max(0.0, min(1.0, (hunger + thirst + sleep) / 240.0))


def cult_propensity(sim, eid):
    return random.Random(f"{getattr(sim, 'seed', 0)}:cult-propensity:{eid}").random()


def _recruitment_score(sim, cult, recruiter_eid, candidate_eid):
    if not actor_eligible_for_cult(sim, candidate_eid):
        return -1.0
    if actor_cult_ids(sim, candidate_eid):
        return -1.0
    if actor_is_shunned_by_cult(sim, candidate_eid, cult.get("cult_id")):
        return -1.0
    recruiter_social = sim.ecs.get(NPCSocial).get(recruiter_eid)
    bond = recruiter_social.bonds.get(candidate_eid, {}) if recruiter_social and hasattr(recruiter_social, "bonds") else {}
    closeness = float((bond or {}).get("closeness", 0.0) or 0.0)
    trust = float((bond or {}).get("trust", 0.0) or 0.0)
    need = _actor_need_score(sim, candidate_eid)
    propensity = cult_propensity(sim, candidate_eid)
    style_bonus = {"sheltering": 0.14, "hungry": 0.18, "fervent": 0.08, "gentle": 0.04}.get(_key(cult.get("recruitment_style")), 0.0)
    return (propensity * 0.46) + (need * 0.28) + (closeness * 0.13) + (trust * 0.08) + style_bonus


def _same_chunk(sim, a, b):
    return sim.chunk_coords(int(a.x), int(a.y)) == sim.chunk_coords(int(b.x), int(b.y))


def _try_recruit_nearby(sim, cult, recruiter_eid):
    rec_key = f"recruit:{cult.get('cult_id')}:{recruiter_eid}"
    cooldowns = _state(sim).setdefault("cooldowns", {})
    tick = _safe_int(getattr(sim, "tick", 0), 0)
    if tick < _safe_int(cooldowns.get(rec_key), 0):
        return None
    recruiter_pos = sim.ecs.get(Position).get(recruiter_eid)
    if recruiter_pos is None:
        return None
    best = None
    best_score = 0.0
    for candidate_eid, pos in sim.ecs.get(Position).items():
        if candidate_eid == recruiter_eid or candidate_eid == getattr(sim, "player_eid", None):
            continue
        if pos is None or int(pos.z) != int(recruiter_pos.z):
            continue
        if not _same_chunk(sim, recruiter_pos, pos) or _manhattan(recruiter_pos.x, recruiter_pos.y, pos.x, pos.y) > 8:
            continue
        if not has_line_of_sight(sim, int(recruiter_pos.x), int(recruiter_pos.y), int(recruiter_pos.z), int(pos.x), int(pos.y), int(pos.z)):
            continue
        score = _recruitment_score(sim, cult, recruiter_eid, candidate_eid)
        if score > best_score:
            best = candidate_eid
            best_score = score
    cooldowns[rec_key] = tick + CULT_RECRUIT_COOLDOWN_TICKS
    if best is None or best_score < 0.62:
        return None
    result = join_cult(sim, best, cult.get("cult_id"), role="member", title="member", issue_uniform=True, auto_equip=True)
    if result.get("ok"):
        sim.emit(Event(
            "cult_recruited_npc",
            cult_id=cult.get("cult_id"),
            cult_name=cult.get("name"),
            recruiter_eid=recruiter_eid,
            recruit_eid=best,
            score=round(best_score, 3),
        ))
        return best
    return None


def _candidate_promotion_score(sim, cult, eid, row):
    joined_tick = _safe_int(row.get("joined_tick"), 0)
    tenure = max(0, _safe_int(getattr(sim, "tick", 0), 0) - joined_tick) / 600.0
    uniform_bonus = 0.16 if actor_in_cult_uniform(sim, eid, cult) else 0.0
    rng = random.Random(f"{getattr(sim, 'seed', 0)}:cult-promotion:{cult.get('cult_id')}:{eid}:{joined_tick}")
    return (
        cult_propensity(sim, eid) * 0.48
        + min(0.22, tenure * 0.018)
        + uniform_bonus
        + (rng.random() * 0.08)
    )


def _promote_cult_official(sim, cult, eid, coverage):
    row = cult.setdefault("members", {}).get(str(eid))
    if not isinstance(row, dict) or not bool(row.get("active", True)):
        return None
    tick = _safe_int(getattr(sim, "tick", 0), 0)
    title = _clean_text(cult.get("official_title")) or "keeper"
    prop_id = _clean_text(coverage.get("property_id")) if isinstance(coverage, dict) else ""
    prop_name = _clean_text(coverage.get("property_name")) if isinstance(coverage, dict) else ""
    prop = _property_from_id(sim, prop_id)
    if isinstance(prop, dict):
        prop_name = prop_name or _property_name(prop, "coverage site")
        index = _state(sim).setdefault("property_index", {})
        index.setdefault(prop_id, [])
        if cult.get("cult_id") not in index[prop_id]:
            index[prop_id].append(cult.get("cult_id"))
    row["role"] = "official"
    row["title"] = title
    row["promoted_tick"] = tick
    row["promoted_by_leader_eid"] = _safe_int(cult.get("leader_eid"), 0) or None
    row["coverage_property_id"] = prop_id
    row["coverage_property_name"] = prop_name
    row["coverage_member_count"] = _safe_int((coverage or {}).get("member_count"), 0)
    row["coverage_reason"] = "membership_density"
    row["coverage_kind"] = _clean_text((coverage or {}).get("coverage_kind")) or "member_density"
    row["coverage_host_actor_eid"] = _safe_int((coverage or {}).get("host_actor_eid"), 0) or None
    row["coverage_host_property_id"] = _clean_text((coverage or {}).get("host_property_id"))
    row["coverage_host_property_name"] = _clean_text((coverage or {}).get("host_property_name"))
    _set_role_lists_from_members(cult)
    assign_actor_organization(
        sim,
        eid,
        organization_eid=cult.get("organization_eid"),
        organization_name=cult.get("name"),
        organization_kind=CULT_KIND,
        tags=("cult",),
        role="official",
        kind="membership",
        title=title,
        primary=False,
        authority_rank=25,
        supervisor_eid=_safe_int(cult.get("leader_eid"), 0) or None,
        site_property_id=prop_id or cult.get("meeting", {}).get("property_id"),
        active=True,
    )
    if isinstance(prop, dict):
        target = _property_center(prop)
        ai = sim.ecs.get(AI).get(eid)
        will = sim.ecs.get(NPCWill).get(eid)
        if ai is not None:
            _sync_ai_intent(ai, will, tick, "cult_official_coverage", score=62.0, target=target)
            mark_actor_urgent(sim, eid, reason="cult_official_coverage", ttl_ticks=120)
    sim.emit(Event(
        "cult_official_promoted",
        cult_id=cult.get("cult_id"),
        cult_name=cult.get("name"),
        leader_eid=cult.get("leader_eid"),
        official_eid=eid,
        official_title=title,
        property_id=prop_id,
        property_name=prop_name,
        member_count=row.get("coverage_member_count", 0),
        coverage_kind=row.get("coverage_kind"),
        host_actor_eid=row.get("coverage_host_actor_eid"),
        host_property_id=row.get("coverage_host_property_id"),
        host_property_name=row.get("coverage_host_property_name"),
        official_count=_active_official_count(cult),
        target_official_count=_official_target_count(cult),
    ))
    return row


def _property_supports_service_site(prop):
    if not isinstance(prop, dict):
        return False
    kind = _key(prop.get("kind"))
    if kind != "building":
        return False
    if property_services(prop):
        return True
    if property_is_storefront(prop):
        return True
    return bool(tuple(property_service_ids(prop) or ()))


def _service_site_controller_candidates(sim, prop):
    rows = []
    seen = set()
    members = tuple(property_org_members(sim, prop) or ())
    service_rows = [
        row for row in members
        if isinstance(row, dict) and _safe_int(row.get("eid"), 0) > 0
    ]
    for row in service_rows:
        eid = _safe_int(row.get("eid"), 0)
        if eid <= 0 or eid in seen:
            continue
        seen.add(eid)
        role = _key(row.get("role")) or "staff"
        control = role in {"owner", "manager"} or len(service_rows) == 1
        if not control:
            continue
        rows.append({
            "eid": eid,
            "role": role if role in {"owner", "manager", "staff"} else "staff",
            "sole_employee": len(service_rows) == 1,
            "source": row.get("source", "workplace"),
        })
    owner_eid = prop.get("owner_eid") if isinstance(prop, dict) else None
    if owner_eid is not None:
        eid = _safe_int(owner_eid, 0)
        if eid > 0 and eid not in seen:
            rows.append({"eid": eid, "role": "owner", "sole_employee": False, "source": "owner"})
    return tuple(sorted(rows, key=lambda row: (0 if row.get("role") == "owner" else 1 if row.get("role") == "manager" else 2, int(row.get("eid", 0)))))


def _cult_region_service_sites(sim, cult, official_row):
    coverage_prop = _property_from_id(sim, official_row.get("coverage_property_id"))
    host_prop = _property_from_id(sim, official_row.get("coverage_host_property_id"))
    anchor = coverage_prop or host_prop or _meeting_property(sim, cult)
    region = _property_chunk_key(sim, anchor)
    if region is None:
        return ()
    rows = []
    meeting_id = _clean_text(cult.get("meeting", {}).get("property_id"))
    for prop in tuple(getattr(sim, "properties", {}).values()):
        if not isinstance(prop, dict) or _clean_text(prop.get("id")) == meeting_id:
            continue
        if _property_chunk_key(sim, prop) != region:
            continue
        if not _property_supports_service_site(prop):
            continue
        if cult_property_association(sim, prop).get("kind") == "absorbed_service":
            continue
        controllers = _service_site_controller_candidates(sim, prop)
        if not controllers:
            continue
        rows.append((prop, controllers))
    return tuple(sorted(rows, key=lambda row: (_clean_text(row[0].get("id")), _property_name(row[0]))))


def _official_outreach_score(sim, cult, official_eid, candidate_eid, candidate_row):
    base = _recruitment_score(sim, cult, official_eid, candidate_eid)
    if base < 0.0:
        return -1.0
    conversation = actor_skill(sim, official_eid, "conversation", default=5.0)
    streetwise = actor_skill(sim, official_eid, "streetwise", default=5.0)
    official_bonus = max(-0.08, min(0.24, ((conversation - 5.0) * 0.035) + ((streetwise - 5.0) * 0.025)))
    role_bonus = {"owner": -0.03, "manager": 0.02, "staff": 0.07}.get(_key(candidate_row.get("role")), 0.0)
    if bool(candidate_row.get("sole_employee")):
        role_bonus += 0.05
    return base + official_bonus + role_bonus


def _set_cult_workplace_on_occupation(sim, eid, prop, cult, *, role="staff"):
    occupation = sim.ecs.get(Occupation).get(eid)
    if occupation is None:
        return False
    workplace = getattr(occupation, "workplace", None)
    if not isinstance(workplace, dict):
        workplace = {"property_id": prop.get("id")} if isinstance(prop, dict) else {}
    workplace["property_id"] = _clean_text(prop.get("id"))
    workplace["organization_eid"] = cult.get("organization_eid")
    workplace["organization_key"] = f"cult:{cult.get('cult_id')}"
    workplace["organization_name"] = cult.get("name")
    workplace["organization_kind"] = CULT_KIND
    workplace["organization_tags"] = ("cult",)
    workplace["authority_role"] = _key(role) if _key(role) in {"owner", "manager", "staff"} else "staff"
    occupation.workplace = workplace
    return True


def _absorb_cult_service_site(sim, cult, official_eid, target_eid, prop, candidate_row, score):
    cult_id = _clean_text(cult.get("cult_id"))
    prop_id = _clean_text(prop.get("id"))
    if not cult_id or not prop_id:
        return None
    result = {"ok": True}
    if not actor_is_cult_member(sim, target_eid, cult_id):
        result = join_cult(sim, target_eid, cult_id, role="member", title="member", issue_uniform=True, auto_equip=True)
        if not result.get("ok"):
            return None
    tick = _safe_int(getattr(sim, "tick", 0), 0)
    role = _key(candidate_row.get("role")) or "staff"
    link_property_organization(
        sim,
        prop,
        organization_eid=cult.get("organization_eid"),
        organization_name=cult.get("name"),
        organization_kind=CULT_KIND,
        tags=("cult",),
        link_kind="operates",
        primary=True,
        active=True,
    )
    metadata = prop.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        prop["metadata"] = metadata
    metadata["cult_association"] = {
        "cult_id": cult_id,
        "kind": "absorbed_service",
        "official_eid": int(official_eid),
        "service_actor_eid": int(target_eid),
        "absorbed_tick": tick,
        "nonmember_service_cost_mult": CULT_NONMEMBER_SERVICE_TAX_MULT,
    }
    index = _state(sim).setdefault("property_index", {})
    index.setdefault(prop_id, [])
    if cult_id not in index[prop_id]:
        index[prop_id].append(cult_id)
    cult.setdefault("absorbed_service_sites", {})[prop_id] = {
        "property_id": prop_id,
        "property_name": _property_name(prop, "service site"),
        "official_eid": int(official_eid),
        "service_actor_eid": int(target_eid),
        "absorbed_tick": tick,
        "candidate_role": role,
        "score": round(float(score), 3),
    }
    target_row = cult.setdefault("members", {}).get(str(target_eid))
    if isinstance(target_row, dict):
        target_row["absorbed_service_property_id"] = prop_id
        target_row["absorbed_service_property_name"] = _property_name(prop, "service site")
        target_row["absorbed_by_official_eid"] = int(official_eid)
        target_row["absorbed_service_tick"] = tick
        target_row["service_site_role"] = role
    official_row = cult.setdefault("members", {}).get(str(official_eid))
    if isinstance(official_row, dict):
        official_row["absorbed_service_property_id"] = prop_id
        official_row["absorbed_service_property_name"] = _property_name(prop, "service site")
        official_row["coverage_property_id"] = prop_id
        official_row["coverage_property_name"] = _property_name(prop, "service site")
        official_row["coverage_kind"] = "absorbed_service"
        official_row["service_site_recruit_eid"] = int(target_eid)
        official_row["service_site_absorbed_tick"] = tick
    _set_cult_workplace_on_occupation(sim, target_eid, prop, cult, role=role)
    _set_cult_workplace_on_occupation(sim, official_eid, prop, cult, role="staff")
    for eid, assign_role, title, rank in (
        (target_eid, "member", "member", 70),
        (official_eid, "official", _clean_text(cult.get("official_title")) or "keeper", 25),
    ):
        assign_actor_organization(
            sim,
            eid,
            organization_eid=cult.get("organization_eid"),
            organization_name=cult.get("name"),
            organization_kind=CULT_KIND,
            tags=("cult",),
            role=assign_role,
            kind="membership",
            title=title,
            primary=False,
            authority_rank=rank,
            supervisor_eid=_safe_int(cult.get("leader_eid"), 0) or None,
            site_property_id=prop_id,
            active=True,
        )
    settlement = sim.ecs.get(NPCSettlement).get(official_eid)
    if settlement is None:
        settlement = NPCSettlement(phase="settled", housing_status="housed")
        sim.ecs.add(official_eid, settlement)
    settlement.home_property_id = prop_id
    settlement.work_property_id = prop_id
    target = _property_center(prop)
    ai = sim.ecs.get(AI).get(official_eid)
    will = sim.ecs.get(NPCWill).get(official_eid)
    if ai is not None:
        _sync_ai_intent(ai, will, tick, "cult_service_contact", score=58.0, target=target)
        mark_actor_urgent(sim, official_eid, reason="cult_service_contact", ttl_ticks=120)
    sim.emit(Event(
        "cult_service_site_absorbed",
        cult_id=cult_id,
        cult_name=cult.get("name"),
        official_eid=official_eid,
        recruit_eid=target_eid,
        property_id=prop_id,
        property_name=_property_name(prop, "service site"),
        candidate_role=role,
        score=round(float(score), 3),
    ))
    return cult["absorbed_service_sites"][prop_id]


def _official_arrival_host_property(sim, row):
    prop = _property_from_id(sim, row.get("coverage_host_property_id"))
    if isinstance(prop, dict):
        return prop
    prop = _property_from_id(sim, row.get("coverage_property_id"))
    if isinstance(prop, dict):
        return prop
    return None


def _official_ready_for_outreach(sim, cult, official_eid, row):
    if _clean_text(row.get("absorbed_service_property_id")):
        return False
    host_prop = _official_arrival_host_property(sim, row)
    if not isinstance(host_prop, dict):
        return False
    tick = _safe_int(getattr(sim, "tick", 0), 0)
    if not row.get("coverage_arrived_tick"):
        if not _actor_at_property(sim, official_eid, host_prop, radius=7):
            return False
        row["coverage_arrived_tick"] = tick
        row["hosted_property_id"] = _clean_text(host_prop.get("id"))
        row["hosted_property_name"] = _property_name(host_prop, "host site")
        settlement = sim.ecs.get(NPCSettlement).get(official_eid)
        if settlement is None:
            settlement = NPCSettlement(phase="settled", housing_status="housed")
            sim.ecs.add(official_eid, settlement)
        settlement.home_property_id = _clean_text(host_prop.get("id"))
        if not _clean_text(getattr(settlement, "work_property_id", "")):
            settlement.work_property_id = _clean_text(host_prop.get("id"))
        sim.emit(Event(
            "cult_official_arrived",
            cult_id=cult.get("cult_id"),
            cult_name=cult.get("name"),
            official_eid=official_eid,
            property_id=host_prop.get("id"),
            property_name=_property_name(host_prop, "host site"),
        ))
    return tick >= _safe_int(row.get("next_service_outreach_tick"), 0)


def _try_official_service_outreach(sim, cult, official_eid, row):
    tick = _safe_int(getattr(sim, "tick", 0), 0)
    if not _official_ready_for_outreach(sim, cult, official_eid, row):
        return None
    row["next_service_outreach_tick"] = tick + CULT_OFFICIAL_OUTREACH_COOLDOWN_TICKS
    candidates = []
    for prop, controller_rows in _cult_region_service_sites(sim, cult, row):
        for controller in controller_rows:
            candidate_eid = _safe_int(controller.get("eid"), 0)
            if candidate_eid <= 0 or candidate_eid == official_eid or _actor_is_player(sim, candidate_eid):
                continue
            if not actor_eligible_for_cult(sim, candidate_eid):
                continue
            existing = tuple(actor_cult_ids(sim, candidate_eid) or ())
            if existing and cult.get("cult_id") not in existing:
                continue
            score = _official_outreach_score(sim, cult, official_eid, candidate_eid, controller)
            if score < 0.72:
                continue
            candidates.append((score, -candidate_eid, prop, controller))
    if not candidates:
        return None
    score, _neg_eid, prop, controller = sorted(candidates, reverse=True)[0]
    return _absorb_cult_service_site(sim, cult, official_eid, _safe_int(controller.get("eid"), 0), prop, controller, score)


def _devotion_matches_animal(cult, sim, animal_eid):
    devotion = dict(cult.get("devotion", {}) or {})
    if _key(devotion.get("family")) != "animal":
        return False
    identity = sim.ecs.get(CreatureIdentity).get(animal_eid)
    if identity is None:
        return False
    tokens = {
        _key(getattr(identity, "common_name", "")),
        _key(getattr(identity, "species", "")),
        _key(getattr(identity, "creature_type", "")),
    }
    target = _key(devotion.get("target_key"))
    if target in tokens:
        return True
    label = _key(devotion.get("label"))
    return any(token and (token in target or target in token or token in label) for token in tokens)


def _devotion_matches_flora(cult, plant_id, plant_name=""):
    devotion = dict(cult.get("devotion", {}) or {})
    if _key(devotion.get("family")) != "flora":
        return False
    target = _key(devotion.get("target_key"))
    return target in {_key(plant_id), _key(plant_name)}


def _cult_member_defends(sim, cult, witness_eid, offender_eid, *, reason):
    severity = _key(cult.get("severity"))
    rng = random.Random(f"{getattr(sim, 'seed', 0)}:cult-defend:{cult.get('cult_id')}:{witness_eid}:{offender_eid}:{reason}:{getattr(sim, 'tick', 0) // 30}")
    violent = severity == "fervent" and rng.random() < 0.46
    if not violent:
        sim.emit(Event(
            "cult_devotion_warning",
            cult_id=cult.get("cult_id"),
            cult_name=cult.get("name"),
            witness_eid=witness_eid,
            offender_eid=offender_eid,
            reason=reason,
            response="warning",
        ))
        return False
    witness_pos = sim.ecs.get(Position).get(witness_eid)
    offender_pos = sim.ecs.get(Position).get(offender_eid)
    ai = sim.ecs.get(AI).get(witness_eid)
    will = sim.ecs.get(NPCWill).get(witness_eid)
    if witness_pos is None or offender_pos is None or ai is None:
        return False
    _sync_ai_intent(
        ai,
        will,
        _safe_int(getattr(sim, "tick", 0), 0),
        "protecting",
        score=84.0,
        target=(int(offender_pos.x), int(offender_pos.y), int(offender_pos.z)),
        target_eid=offender_eid,
    )
    mark_actor_urgent(sim, witness_eid, reason="cult_devotion_defense", ttl_ticks=36)
    sim.emit(Event(
        "cult_devotion_warning",
        cult_id=cult.get("cult_id"),
        cult_name=cult.get("name"),
        witness_eid=witness_eid,
        offender_eid=offender_eid,
        reason=reason,
        response="force",
    ))
    return True


def _meeting_active(cult, tick):
    return _safe_int(cult.get("meeting", {}).get("active_until_tick"), 0) >= _safe_int(tick, 0)


def cult_local_situation_rows(sim, *, player_pos=None, player_eid=None):
    rows = []
    tick = _safe_int(getattr(sim, "tick", 0), 0)
    for cult in _state(sim).get("cults", {}).values():
        if not _cult_active(cult) or not _meeting_active(cult, tick):
            continue
        meeting = dict(cult.get("meeting", {}) or {})
        prop = sim.properties.get(_clean_text(meeting.get("property_id")))
        if not isinstance(prop, dict):
            continue
        px = _safe_int(prop.get("x"), 0)
        py = _safe_int(prop.get("y"), 0)
        pz = _safe_int(prop.get("z"), 0)
        if player_pos is not None:
            if sim.chunk_coords(px, py) != sim.chunk_coords(int(player_pos.x), int(player_pos.y)):
                continue
        known = player_eid is not None and player_knows_cult(sim, player_eid, cult)
        uniform = dict(cult.get("uniform", {}) or {})
        devotion = dict(cult.get("devotion", {}) or {})
        if known:
            summary = f"{cult.get('name')} is gathering here"
            action = f"meeting around {int(meeting.get('hour', 0)):02d}:00; {devotion.get('public_line', 'their code')}"
        else:
            summary = f"people in matching {uniform.get('label', 'clothes')} are gathering here"
            action = "watch the traffic, or talk to someone wearing the same mark"
        rows.append({
            "scene_id": f"cult_meeting:{cult.get('cult_id')}",
            "source_kind": "cult_meeting",
            "scene_type": "cult_meeting",
            "title": "Circle Gathering" if known else "Matching Clothes",
            "summary": summary,
            "action": action,
            "anchor": (px, py, pz),
            "property_id": prop.get("id"),
            "property_name": _property_name(prop),
            "x": px,
            "y": py,
            "z": pz,
            "distance": (
                abs(px - int(player_pos.x)) + abs(py - int(player_pos.y))
                if player_pos is not None else 0
            ),
            "priority": 45,
            "cult_id": cult.get("cult_id") if known else "",
            "cult_known": bool(known),
        })
    return tuple(rows)


class CultSystem(System):
    def __init__(self, sim):
        self.sim = sim
        self._last_update_tick = -999999
        ensure_cult_state(sim)
        sim.events.subscribe("entity_damaged", self.on_entity_damaged)
        sim.events.subscribe("npc_killed", self.on_npc_killed)
        sim.events.subscribe("actor_detained", self.on_actor_detained)
        sim.events.subscribe("flora_harvested", self.on_flora_harvested)

    def update(self):
        tick = _safe_int(getattr(self.sim, "tick", 0), 0)
        if tick - self._last_update_tick < CULT_UPDATE_INTERVAL:
            return
        self._last_update_tick = tick
        seed_cults_if_needed(self.sim)
        self._update_meetings()
        self._update_official_promotions()
        self._update_official_service_outreach()
        self._update_recruitment()

    def _update_meetings(self):
        day, hour = _world_day_hour(self.sim)
        tick = _safe_int(getattr(self.sim, "tick", 0), 0)
        for cult in _state(self.sim).get("cults", {}).values():
            if not _cult_active(cult):
                continue
            meeting = cult.setdefault("meeting", {})
            if int(meeting.get("hour", -1)) != int(hour):
                continue
            if int(meeting.get("last_day", -9999)) == int(day):
                continue
            meeting["last_day"] = int(day)
            meeting["active_until_tick"] = tick + CULT_MEETING_DURATION_TICKS
            propagated = propagate_cult_grievances(self.sim, cult)
            self.sim.emit(Event(
                "cult_meeting_started",
                cult_id=cult.get("cult_id"),
                cult_name=cult.get("name"),
                property_id=meeting.get("property_id"),
                property_name=meeting.get("property_name"),
                propagated_grievances=tuple(propagated),
            ))
            self._route_members_to_meeting(cult)

    def _route_members_to_meeting(self, cult):
        prop = self.sim.properties.get(_clean_text(cult.get("meeting", {}).get("property_id")))
        if not isinstance(prop, dict):
            return
        target = (_safe_int(prop.get("x"), 0), _safe_int(prop.get("y"), 0), _safe_int(prop.get("z"), 0))
        for raw_eid, member in dict(cult.get("members", {}) or {}).items():
            if not isinstance(member, dict) or not bool(member.get("active", True)):
                continue
            if _key(member.get("role")) == "bodyguard":
                continue
            eid = _safe_int(raw_eid, -1)
            if eid <= 0 or eid == getattr(self.sim, "player_eid", None):
                continue
            ai = self.sim.ecs.get(AI).get(eid)
            will = self.sim.ecs.get(NPCWill).get(eid)
            pos = self.sim.ecs.get(Position).get(eid)
            if ai is None or pos is None:
                continue
            if _key(getattr(ai, "state", "")) in {"protecting", "attacking", "fighting", "seeking_safety"}:
                continue
            _sync_ai_intent(ai, will, _safe_int(getattr(self.sim, "tick", 0), 0), "cult_meeting", score=48.0, target=target)
            mark_actor_urgent(self.sim, eid, reason="cult_meeting", ttl_ticks=80)

    def _update_official_promotions(self):
        day, _hour = _world_day_hour(self.sim)
        tick = _safe_int(getattr(self.sim, "tick", 0), 0)
        for cult in _state(self.sim).get("cults", {}).values():
            if not _cult_active(cult):
                continue
            target_count = _official_target_count(cult)
            if target_count <= 0 or _active_official_count(cult) >= target_count:
                continue
            meeting = cult.setdefault("meeting", {})
            if not _meeting_active(cult, tick):
                continue
            if int(meeting.get("promotion_day", -9999)) == int(day):
                continue
            prop = _meeting_property(self.sim, cult)
            leader_eid = _safe_int(cult.get("leader_eid"), -1)
            if leader_eid <= 0 or not _is_living_actor(self.sim, leader_eid):
                continue
            if not _actor_at_property(self.sim, leader_eid, prop, radius=6):
                continue
            candidates = []
            for eid, row in _active_cult_rows(cult, roles=("member",)):
                if _actor_is_player(self.sim, eid) or not _is_living_actor(self.sim, eid):
                    continue
                if not _actor_at_property(self.sim, eid, prop, radius=7):
                    continue
                score = _candidate_promotion_score(self.sim, cult, eid, row)
                candidates.append((score, -eid, eid, row))
            if not candidates:
                continue
            _score, _neg_eid, eid, _row = sorted(candidates, reverse=True)[0]
            coverage = _coverage_property_for_promotion(self.sim, cult, eid)
            promoted = _promote_cult_official(self.sim, cult, eid, coverage)
            if promoted:
                meeting["promotion_day"] = int(day)
                meeting["promotion_tick"] = int(tick)

    def _update_official_service_outreach(self):
        for cult in _state(self.sim).get("cults", {}).values():
            if not _cult_active(cult):
                continue
            for official_eid, row in _active_cult_rows(cult, roles=("official",)):
                if not _is_living_actor(self.sim, official_eid):
                    continue
                _try_official_service_outreach(self.sim, cult, official_eid, row)

    def _update_recruitment(self):
        for cult in _state(self.sim).get("cults", {}).values():
            if not _cult_active(cult):
                continue
            crisis = dict(cult.get("crisis", {}) or {})
            if _key(crisis.get("kind")) == "leader_detained" and _key(cult.get("recruitment_style")) != "fervent":
                continue
            recruiters = tuple(cult.get("official_eids", ()) or ()) + tuple(cult.get("member_eids", ()) or ())
            for recruiter_eid in recruiters[:8]:
                if _is_living_actor(self.sim, recruiter_eid):
                    _try_recruit_nearby(self.sim, cult, recruiter_eid)

    def on_entity_damaged(self, event):
        target_eid = event.data.get("target_eid")
        source_eid = event.data.get("source_eid")
        if target_eid is None or source_eid is None:
            return
        target_pos = self.sim.ecs.get(Position).get(target_eid)
        if target_pos is None:
            return
        for cult in _state(self.sim).get("cults", {}).values():
            if not _cult_active(cult):
                continue
            if not _devotion_matches_animal(cult, self.sim, target_eid):
                continue
            witnesses = _nearby_cult_member_witnesses(self.sim, cult, target_pos.x, target_pos.y, target_pos.z, exclude_eid=source_eid, radius=11)
            for witness in witnesses:
                record_cult_grievance(
                    self.sim,
                    cult.get("cult_id"),
                    source_eid,
                    violation_kind="harmed_sacred_animal",
                    witness_eid=witness,
                    target_label=dict(cult.get("devotion", {}) or {}).get("label", "animal"),
                    immediate=True,
                )
                _cult_member_defends(self.sim, cult, witness, source_eid, reason="sacred_animal")
                break

    def on_npc_killed(self, event):
        target_eid = event.data.get("target_eid")
        if target_eid is None:
            return
        for cult in list(_state(self.sim).get("cults", {}).values()):
            if not _cult_active(cult):
                continue
            if int(target_eid) == _safe_int(cult.get("leader_eid"), -1):
                self._disband_cult(cult, reason="leader_killed")

    def on_actor_detained(self, event):
        target_eid = event.data.get("eid") or event.data.get("target_eid") or event.data.get("actor_eid")
        if target_eid is None:
            return
        tick = _safe_int(getattr(self.sim, "tick", 0), 0)
        for cult in _state(self.sim).get("cults", {}).values():
            if not _cult_active(cult):
                continue
            if int(target_eid) == _safe_int(cult.get("leader_eid"), -1):
                cult["crisis"] = {
                    "kind": "leader_detained",
                    "started_tick": tick,
                    "morale": "shaken" if _key(dict(cult.get("devotion", {}) or {}).get("family")) == "leader" else "pressured",
                }
                self.sim.emit(Event("cult_crisis_started", cult_id=cult.get("cult_id"), cult_name=cult.get("name"), leader_eid=target_eid, crisis_kind="leader_detained"))

    def on_flora_harvested(self, event):
        plant_id = event.data.get("plant_id") or event.data.get("flora_id")
        plant_name = event.data.get("plant_name")
        actor_eid = event.data.get("eid")
        if actor_eid is None:
            return
        x = event.data.get("x")
        y = event.data.get("y")
        z = event.data.get("z", 0)
        try:
            x, y, z = int(x), int(y), int(z)
        except (TypeError, ValueError):
            pos = self.sim.ecs.get(Position).get(actor_eid)
            if pos is None:
                return
            x, y, z = int(pos.x), int(pos.y), int(pos.z)
        for cult in _state(self.sim).get("cults", {}).values():
            if not _cult_active(cult) or not _devotion_matches_flora(cult, plant_id, plant_name):
                continue
            witnesses = _nearby_cult_member_witnesses(self.sim, cult, x, y, z, exclude_eid=actor_eid, radius=9)
            for witness in witnesses:
                record_cult_grievance(
                    self.sim,
                    cult.get("cult_id"),
                    actor_eid,
                    violation_kind="harvested_sacred_flora",
                    witness_eid=witness,
                    target_label=plant_name or plant_id,
                    immediate=True,
                )
                self.sim.emit(Event(
                    "cult_devotion_warning",
                    cult_id=cult.get("cult_id"),
                    cult_name=cult.get("name"),
                    witness_eid=witness,
                    offender_eid=actor_eid,
                    reason="sacred_flora",
                    response="warning",
                ))
                break

    def _disband_cult(self, cult, *, reason):
        cult["disbanded"] = True
        cult["disbanded_tick"] = _safe_int(getattr(self.sim, "tick", 0), 0)
        cult["disbanded_reason"] = _clean_text(reason)
        channel_id = protection_channel_id_for_assignment("principal", principal_eid=cult.get("leader_eid"))
        if channel_id:
            fire_bodyguard_contract(self.sim, cult.get("leader_eid"), protection_channel_id=channel_id)
        for raw_eid, member in dict(cult.get("members", {}) or {}).items():
            idx = _actor_index_row(self.sim, raw_eid)
            idx["active"] = [cid for cid in idx.get("active", []) if cid != cult.get("cult_id")]
            if isinstance(member, dict):
                member["active"] = False
                member["left_reason"] = "disbanded"
        self.sim.emit(Event("cult_disbanded", cult_id=cult.get("cult_id"), cult_name=cult.get("name"), reason=reason))


__all__ = [
    "CULT_KIND",
    "CULT_PLAYER_GRACE_TICKS",
    "CULT_SERVICE_IDS",
    "CultSystem",
    "actor_cult_ids",
    "actor_eligible_for_cult",
    "actor_in_cult_uniform",
    "actor_is_cult_member",
    "actor_is_shunned_by_cult",
    "apply_cult_service",
    "cult_for_property",
    "cult_local_situation_rows",
    "cult_property_association",
    "cult_propensity",
    "cult_service_cost_multiplier",
    "cult_services_for_property",
    "ensure_cult_state",
    "issue_cult_uniform",
    "join_cult",
    "leave_cult",
    "mark_cult_known",
    "propagate_cult_grievances",
    "record_cult_grievance",
    "seed_cults_if_needed",
]
