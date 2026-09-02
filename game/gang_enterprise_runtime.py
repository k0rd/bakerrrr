"""Gang enterprise, territory, and style-signal runtime.

This is the street-gang counterpart to corporate expansion.  It keeps the
state concrete: gangs claim or pressure real properties, assign real loaded
actors to roles, mark affiliation through AppearanceLoadout skin marks, and
write visible organization pressure rows.  Crimes remain ordinary actor events.
"""

from __future__ import annotations

import random

from engine.derived_facts import mark_derived_fact_changed
from engine.events import Event
from engine.systems import System
from game.appearance_loadout import apply_tattoo_service, appearance_loadout_for
from game.components import Occupation, OrganizationProfile
from game.local_service_demand import record_local_service_supply
from game.organizations import (
    assign_actor_organization,
    ensure_organization_diplomacy_state,
    link_property_organization,
    organization_compatibility_read,
    organization_crime_plans,
    organization_policy_snapshot,
    organization_profile,
    property_field_domains,
    property_org_links,
    property_service_ids,
    record_organization_crime_plan,
    record_organization_practice,
    record_organization_pressure,
    record_organization_relationship,
    record_organization_vocabulary,
)
from game.player_businesses import property_supports_player_business
from game.service_runtime import casino_game_capabilities
from game.slot_machine import SLOT_BONUS_WILD_WEIGHT_SCALE, normalize_slot_bonus_wild_weight_scale


GANG_ENTERPRISE_INTERVAL = 540
GANG_ENTERPRISE_TTL = 18 * 600
GANG_INVALID_METADATA_FLAGS = frozenset(
    (
        "critical",
        "objective",
        "objective_critical",
        "quest_critical",
        "final_operation",
        "final_operation_site",
        "no_gang_enterprise",
        "no_gang_territory",
        "protected_from_gang",
    )
)
GANG_CLAIM_KINDS = frozenset(("territory", "front", "stash_site", "fence_contact", "vendor_route"))
GANG_ENTERPRISE_ACTIONS = frozenset(
    (
        "territory_claim",
        "territory_contest",
        "front_claim",
        "stash_site",
        "fence_route",
        "vendor_tax",
        "protection_money",
        "intimidation",
        "retaliation",
        "weapon_flow",
    )
)
GANG_ROLE_TITLES = (
    "runner",
    "lookout",
    "dealer",
    "enforcer",
    "recruiter",
    "stash keeper",
    "fence contact",
    "front employee",
)
GANG_TATTOO_SLOTS = (
    "left_forearm",
    "right_forearm",
    "left_hand",
    "right_hand",
    "neck",
    "collarline",
    "left_leg",
    "right_leg",
)
GANG_STYLE_COLORS = (
    "wine",
    "emerald",
    "blue",
    "violet",
    "gold",
    "black",
    "white",
    "silver",
    "red",
    "charcoal",
    "teal",
    "purple",
)
GANG_MOTIFS = (
    "split crown",
    "bent key",
    "blue knot",
    "glass tooth",
    "red ladder",
    "little door",
    "rail mark",
    "three coin",
    "thin flame",
    "black ribbon",
    "crooked star",
    "salt hook",
)
GANG_HOUSE_GAME_STAKE_CULTURES = ("nickel_corner", "street", "house", "danger_room")
GANG_HOUSE_GAME_TONES = ("loud", "watched", "ritual", "swagger", "quiet", "hungry")
GANG_SLOT_BONUS_WILD_WEIGHT_SCALES = {
    "nickel_corner": (1.075, 1.1),
    "street": (1.075, 1.1, 1.125),
    "house": (1.1, 1.125, 1.15),
    "danger_room": (1.125, 1.15, 1.175),
}


def _gang_slot_bonus_wild_weight_scale(sim, gang_org_eid, stake_culture):
    """Seed cabinet math independently from later house-profile additions."""

    choices = GANG_SLOT_BONUS_WILD_WEIGHT_SCALES.get(
        _key(stake_culture),
        (SLOT_BONUS_WILD_WEIGHT_SCALE,),
    )
    rng = random.Random(
        f"gang-slot-cabinet:{getattr(sim, 'seed', 0)}:{int(gang_org_eid)}:{_key(stake_culture)}"
    )
    return normalize_slot_bonus_wild_weight_scale(rng.choice(choices))


def _text(value):
    return str(value or "").strip()


def _key(value):
    return _text(value).lower().replace(" ", "_")


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


def _tick(sim):
    return _safe_int(getattr(sim, "tick", 0), default=0)


def _metadata(prop):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        prop["metadata"] = metadata
    return metadata


def _property_id(prop):
    return _text(prop.get("id")) if isinstance(prop, dict) else ""


def _gang_state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    state = traits.get("gang_enterprise")
    if not isinstance(state, dict):
        state = {}
        traits["gang_enterprise"] = state
    for key in ("claims", "actions", "roles", "house_games", "cooldowns"):
        if not isinstance(state.get(key), dict):
            state[key] = {}
    state["next_action_id"] = max(1, _safe_int(state.get("next_action_id"), default=1))
    ensure_organization_diplomacy_state(sim)
    return state


def ensure_gang_enterprise_state(sim):
    """Return save-compatible gang enterprise state."""

    state = _gang_state(sim)
    now = _tick(sim)
    for key, row in tuple(state.get("actions", {}).items()):
        if not isinstance(row, dict):
            state["actions"].pop(key, None)
            continue
        expires = _safe_int(row.get("expires_tick"), default=0)
        if expires and expires < now:
            state["actions"].pop(key, None)
    for key, value in tuple(state.get("cooldowns", {}).items()):
        if _safe_int(value, default=0) <= now:
            state["cooldowns"].pop(key, None)
    return state


def _profile_tags(profile):
    return {
        _key(tag)
        for tag in tuple(getattr(profile, "tags", ()) or ())
        if _key(tag)
    }


def _is_gang_organization(sim, organization_eid):
    profile = organization_profile(sim, organization_eid)
    if profile is None:
        return False
    policy = organization_policy_snapshot(sim, organization_eid=organization_eid) or {}
    family = _key(policy.get("family"))
    kind = _key(getattr(profile, "kind", ""))
    tags = _profile_tags(profile)
    return family == "street_gang" or kind in {"gang", "crew"} or "street_gang" in tags


def gang_organization_rows(sim):
    rows = []
    for organization_eid, _profile_component in tuple(getattr(sim, "ecs").get(OrganizationProfile).items()):
        if not _is_gang_organization(sim, organization_eid):
            continue
        profile = organization_profile(sim, organization_eid)
        policy = organization_policy_snapshot(sim, organization_eid=organization_eid) or {}
        rows.append(
            {
                "organization_eid": int(organization_eid),
                "organization_key": _text(getattr(profile, "key", "")),
                "organization_name": _text(getattr(profile, "name", "")) or "street crew",
                "family": _text(policy.get("family")) or "street_gang",
                "root_organization_eid": _safe_int(policy.get("root_organization_eid"), default=int(organization_eid)),
                "tags": tuple(sorted(_profile_tags(profile))),
            }
        )
    rows.sort(key=lambda row: (_text(row.get("organization_name")).lower(), row.get("organization_eid", 0)))
    return tuple(rows)


def gang_enterprise_profile(sim, gang_org_eid):
    profile = organization_profile(sim, gang_org_eid)
    if profile is None:
        return {}
    tags = _profile_tags(profile)
    posture = ""
    for tag in tags:
        if tag.startswith("gang_posture:"):
            posture = tag.split(":", 1)[1]
            break
    aggression = 0.32
    if posture in {"vigilante", "protective"}:
        aggression -= 0.12
    if posture in {"predatory", "raider", "hardline"} or tags & {"aggressive", "violent"}:
        aggression += 0.24
    profit = 0.46
    if tags & {"interest:weapons", "interest:supply", "criminal"}:
        profit += 0.14
    return {
        "organization_eid": int(gang_org_eid),
        "organization_name": _text(getattr(profile, "name", "")) or "street crew",
        "posture": posture or "enterprise",
        "aggression": max(0.0, min(1.0, aggression)),
        "profit_focus": max(0.0, min(1.0, profit)),
        "tags": tuple(sorted(tags)),
    }


def gang_style_profile(sim, gang_org_eid):
    """Return deterministic appearance/style rules for a gang."""

    state = ensure_gang_enterprise_state(sim)
    key = f"gang_style:{gang_org_eid}"
    stored = state.get("roles", {}).get(key)
    if isinstance(stored, dict):
        return dict(stored)
    profile = organization_profile(sim, gang_org_eid)
    seed = f"gang-style:{getattr(sim, 'seed', 0)}:{gang_org_eid}:{_text(getattr(profile, 'key', ''))}"
    rng = random.Random(seed)
    color = rng.choice(GANG_STYLE_COLORS)
    accent = rng.choice([value for value in GANG_STYLE_COLORS if value != color])
    motif = rng.choice(GANG_MOTIFS)
    tattoo_slot = rng.choice(GANG_TATTOO_SLOTS)
    hair_rule = rng.choice(("none", "slicked back", "braided", "short crop", "ponytail", "sharp side part"))
    row = {
        "organization_eid": int(gang_org_eid),
        "color": color,
        "accent_color": accent,
        "motif": motif,
        "tattoo_design": f"{color} {motif}",
        "tattoo_slot": tattoo_slot,
        "hair_rule": hair_rule,
        "style_summary": f"{color} with {accent} and a {motif} mark",
    }
    state["roles"][key] = dict(row)
    return row


def _game_capability_score(sim, gang_org_eid, game_id, capability, style, profile, rng):
    tags = set(tuple(capability.get("style_tags", ()) or ()))
    org_tags = set(tuple(profile.get("tags", ()) or ()))
    posture = _key(profile.get("posture"))
    aggression = _safe_float(profile.get("aggression"), default=0.35)
    profit = _safe_float(profile.get("profit_focus"), default=0.45)
    motif = _key(style.get("motif"))
    color = _key(style.get("color"))
    accent = _key(style.get("accent_color"))
    score = 8.0 + rng.uniform(0.0, 4.0)
    if game_id == "three_bright":
        score += 4.0
    if "interest:weapons" in org_tags or "criminal" in org_tags:
        if tags & {"backroom", "risk", "pressure", "street"}:
            score += 2.5
    if "interest:territory" in org_tags and tags & {"street", "crowd", "dice"}:
        score += 2.25
    if "interest:supply" in org_tags and tags & {"ticket", "machine", "numbers"}:
        score += 1.4
    if posture in {"predatory", "raider", "hardline"} and capability.get("risk_band") == "high":
        score += 2.0
    if posture in {"vigilante", "protective"} and capability.get("risk_band") in {"low", "medium"}:
        score += 1.1
    if aggression > 0.55 and capability.get("risk_band") == "high":
        score += 1.8
    if profit > 0.55 and bool(capability.get("supports_debt")):
        score += 1.2
    if "three" in motif and tags & {"dice", "cards"}:
        score += 1.5
    if "coin" in motif and tags & {"machine", "ticket", "numbers"}:
        score += 1.2
    if "flame" in motif and tags & {"risk", "pressure", "quick"}:
        score += 1.2
    if "ribbon" in motif and tags & {"cards", "ritual", "quiet"}:
        score += 1.0
    if color in {"red", "green", "blue", "gold", "black", "white", "violet"} and bool(capability.get("supports_visual_accents")):
        score += 0.8
    if accent in {"red", "green", "blue", "gold", "black", "white", "violet"} and bool(capability.get("supports_visual_accents")):
        score += 0.6
    return max(0.5, float(score))


def gang_house_game_profile(sim, gang_org_eid):
    """Return deterministic favored-game culture for a gang."""

    state = ensure_gang_enterprise_state(sim)
    key = f"gang_house_game:{gang_org_eid}"
    stored = state.get("house_games", {}).get(key)
    if isinstance(stored, dict):
        row = dict(stored)
        if _key(row.get("favored_game")) == "slots" and "slot_bonus_wild_weight_scale" not in row:
            row["slot_bonus_wild_weight_scale"] = _gang_slot_bonus_wild_weight_scale(
                sim,
                gang_org_eid,
                row.get("stake_culture", "house"),
            )
            state["house_games"][key] = dict(row)
        return row
    if not _is_gang_organization(sim, gang_org_eid):
        return {}
    capabilities = {
        game_id: dict(row)
        for game_id, row in casino_game_capabilities().items()
        if bool(row.get("available_for_gang_favorite", True))
    }
    if not capabilities:
        return {}
    style = gang_style_profile(sim, gang_org_eid)
    profile = gang_enterprise_profile(sim, gang_org_eid)
    org_profile = organization_profile(sim, gang_org_eid)
    seed = f"gang-house-game:{getattr(sim, 'seed', 0)}:{gang_org_eid}:{_text(getattr(org_profile, 'key', ''))}"
    rng = random.Random(seed)
    weighted = []
    for game_id, capability in sorted(capabilities.items()):
        weighted.append((game_id, _game_capability_score(sim, gang_org_eid, game_id, capability, style, profile, rng)))
    total = sum(weight for _game_id, weight in weighted)
    pick = rng.uniform(0.0, max(0.1, total))
    favored_game = weighted[-1][0]
    running = 0.0
    for game_id, weight in weighted:
        running += weight
        if pick <= running:
            favored_game = game_id
            break
    capability = dict(capabilities.get(favored_game) or {})
    stake_culture = rng.choice(GANG_HOUSE_GAME_STAKE_CULTURES)
    if capability.get("risk_band") == "low" and stake_culture == "danger_room":
        stake_culture = "house"
    if capability.get("risk_band") == "high" and rng.random() < 0.24:
        stake_culture = "danger_room"
    stake_profile = {
        "nickel_corner": "street",
        "street": "gang_street",
        "house": "gang_house",
        "danger_room": "gang_high",
    }.get(stake_culture, "gang_house")
    tone = rng.choice(GANG_HOUSE_GAME_TONES)
    slot_bonus_wild_weight_scale = _gang_slot_bonus_wild_weight_scale(sim, gang_org_eid, stake_culture)
    colors = []
    for color in (style.get("color"), style.get("accent_color")):
        clean = _key(color)
        if clean and clean not in colors:
            colors.append(clean)
    for fallback in ("red", "green", "blue", "gold", "black", "white", "violet"):
        if len(colors) >= 3:
            break
        if fallback not in colors:
            colors.append(fallback)
    label = _text(capability.get("public_label")) or favored_game.replace("_", " ").title()
    motif = _text(style.get("motif")) or "table mark"
    row = {
        "organization_eid": int(gang_org_eid),
        "favored_game": favored_game,
        "favored_game_label": label,
        "game_colors": tuple(colors[:3]),
        "table_motif": motif,
        "stake_culture": stake_culture,
        "stake_profile": stake_profile,
        "table_tone": tone,
        "slot_bonus_wild_weight_scale": float(slot_bonus_wild_weight_scale),
        "risk_band": _text(capability.get("risk_band")) or "medium",
        "social_texture": _text(capability.get("social_texture")) or "table",
        "supports_table_context": bool(capability.get("supports_table_context")),
        "supports_custom_stakes": bool(capability.get("supports_custom_stakes")),
        "supports_visual_accents": bool(capability.get("supports_visual_accents")),
        "supports_multiplayer_seats": bool(capability.get("supports_multiplayer_seats")),
        "supports_offscreen_resolution": bool(capability.get("supports_offscreen_resolution")),
        "table_read": (
            f"{label} has become the crew's house game: "
            f"{stake_culture.replace('_', ' ')} stakes, {tone} posture, {motif} colors."
        ),
        "feature_tags": tuple(sorted(set(tuple(capability.get("style_tags", ()) or ())))),
    }
    state["house_games"][key] = dict(row)
    return dict(row)


def _gang_house_game_visible_cue(profile):
    label = _text(profile.get("favored_game_label")) or "a table game"
    colors = tuple(_text(color).replace("_", " ") for color in tuple(profile.get("game_colors", ()) or ()) if _text(color))
    color_text = "/".join(colors[:2]) if colors else "crew-colored"
    texture = _text(profile.get("social_texture")) or "table"
    if texture == "machine":
        return f"people keep drifting toward {color_text} machines and talking about {label} payouts"
    if texture in {"dice", "house_dice", "crowd"}:
        return f"{color_text} dice chatter and {label} calls keep leaking from the back of the place"
    if texture in {"cards", "poker", "formal"}:
        return f"{color_text} card talk and guarded {label} glances make the table culture visible"
    if texture == "ticket":
        return f"{color_text} tickets and repeated number talk make {label} feel like the local habit"
    return f"{color_text} table talk makes {label} feel like more than a house game"


def apply_gang_house_game_to_property(sim, gang_org_eid, prop, *, exposure="front", visible=True):
    """Expose a gang's favored game at a concrete service host/front."""

    if not isinstance(prop, dict) or not _is_gang_organization(sim, gang_org_eid):
        return {"ok": False, "reason": "invalid_target"}
    profile = gang_house_game_profile(sim, gang_org_eid)
    game_id = _key(profile.get("favored_game"))
    if not game_id:
        return {"ok": False, "reason": "missing_house_game"}
    capabilities = casino_game_capabilities()
    capability = dict(capabilities.get(game_id) or {})
    metadata = _metadata(prop)
    services = list(metadata.get("site_services", ()) or ())
    if isinstance(metadata.get("site_services"), str):
        services = [metadata.get("site_services")]
    normalized_services = []
    for service in services:
        clean = _key(service)
        if clean and clean not in normalized_services:
            normalized_services.append(clean)
    if game_id not in normalized_services:
        normalized_services.append(game_id)
    metadata["site_services"] = normalized_services
    metadata["site_services_extend_defaults"] = True
    mark_derived_fact_changed(sim, "transit_nodes")
    record_local_service_supply(sim, prop)
    metadata["gang_house_game"] = {
        "organization_eid": int(gang_org_eid),
        "favored_game": game_id,
        "favored_game_label": _text(profile.get("favored_game_label")),
        "game_colors": tuple(profile.get("game_colors", ()) or ()),
        "table_motif": _text(profile.get("table_motif")),
        "stake_culture": _text(profile.get("stake_culture")),
        "table_tone": _text(profile.get("table_tone")),
        "exposure": _key(exposure) or "front",
        "last_update_tick": _tick(sim),
    }
    contexts = metadata.get("casino_table_contexts")
    if not isinstance(contexts, dict):
        contexts = {}
    table_features = {
        "colors": tuple(profile.get("game_colors", ()) or ()),
        "stake_profile": _text(profile.get("stake_profile")) or "gang_house",
        "table_tone": _text(profile.get("table_tone")) or "watched",
        "variance": 0.74 if profile.get("stake_culture") == "danger_room" else 0.55,
    }
    if game_id == "slots":
        table_features["bonus_wild_weight_scale"] = normalize_slot_bonus_wild_weight_scale(
            profile.get("slot_bonus_wild_weight_scale", SLOT_BONUS_WILD_WEIGHT_SCALE)
        )
    contexts[game_id] = {
        "sponsor_kind": "gang",
        "sponsor_id": int(gang_org_eid),
        "access_style": "gang_backroom" if profile.get("stake_culture") == "danger_room" else "gang_linked",
        "stake_profile": _text(profile.get("stake_profile")) or "gang_house",
        "table_tone": _text(profile.get("table_tone")) or "watched",
        "presentation_accents": tuple(profile.get("game_colors", ()) or ()),
        "features": table_features,
    }
    metadata["casino_table_contexts"] = contexts
    if game_id == "three_bright":
        metadata["casino_table_context"] = {
            **dict(metadata.get("casino_table_context") or {}),
            **dict(contexts[game_id]),
        }
    cue = _gang_house_game_visible_cue(profile)
    metadata["gang_house_game"]["visible_cue"] = cue
    pressure = record_organization_pressure(
        sim,
        organization_eid=gang_org_eid,
        pressure_kind="gang_house_game",
        stance="transactional",
        reason_tags=("gang_enterprise", "house_game", game_id, _text(profile.get("stake_culture")), *tuple(capability.get("style_tags", ()) or ())),
        anchor_property_id=_property_id(prop),
        visible=bool(visible),
        visible_cue=cue,
        confidence=0.71,
        source_event="gang_house_game",
        pressure_key=f"gang_house_game:{gang_org_eid}:{_property_id(prop)}:{game_id}",
    )
    record_organization_vocabulary(
        sim,
        organization_eid=gang_org_eid,
        vocabulary_kind="directive",
        entry_key=f"gang_house_game:{_property_id(prop)}:{game_id}",
        topic_key="gang_house_game",
        label=f"{_text(profile.get('favored_game_label')) or game_id} house game",
        summary=cue,
        source_kind="gang_enterprise",
        subject_property_id=_property_id(prop),
        target_property_id=_property_id(prop),
        tags=("gang_enterprise", "house_game", game_id),
        priority=61,
    )
    return {
        "ok": True,
        "profile": dict(profile),
        "pressure": pressure,
        "visible_cue": cue,
        "service_id": game_id,
    }


def _property_invalid_for_gang(prop):
    metadata = _metadata(prop)
    return any(bool(metadata.get(flag)) for flag in GANG_INVALID_METADATA_FLAGS)


def _same_gang_linked(sim, gang_org_eid, prop):
    policy = organization_policy_snapshot(sim, organization_eid=gang_org_eid) or {}
    root = _safe_int(policy.get("root_organization_eid"), default=gang_org_eid)
    for link in property_org_links(sim, prop, active_only=True):
        linked_eid = _safe_int(link.get("organization_eid"), default=0)
        if linked_eid <= 0:
            continue
        linked_policy = organization_policy_snapshot(sim, organization_eid=linked_eid) or {}
        linked_root = _safe_int(linked_policy.get("root_organization_eid"), default=linked_eid)
        if linked_root == root and _key(link.get("link_kind")) in {"territory", "safehouse", "service_host"}:
            return True
    return False


def _rival_gang_link(sim, gang_org_eid, prop):
    policy = organization_policy_snapshot(sim, organization_eid=gang_org_eid) or {}
    root = _safe_int(policy.get("root_organization_eid"), default=gang_org_eid)
    for link in property_org_links(sim, prop, active_only=True):
        linked_eid = _safe_int(link.get("organization_eid"), default=0)
        if linked_eid <= 0:
            continue
        if not _is_gang_organization(sim, linked_eid):
            continue
        linked_policy = organization_policy_snapshot(sim, organization_eid=linked_eid) or {}
        linked_root = _safe_int(linked_policy.get("root_organization_eid"), default=linked_eid)
        if linked_root != root:
            return int(linked_eid)
    return None


def _player_owned_property(sim, prop):
    owner_eid = _safe_int(prop.get("owner_eid"), default=0)
    player_eid = _safe_int(getattr(sim, "player_eid", 0), default=0)
    return owner_eid > 0 and player_eid > 0 and owner_eid == player_eid


def _claim_kind_for_property(prop, target_read=None):
    metadata = _metadata(prop)
    domains = set(property_field_domains(prop))
    services = set(property_service_ids(prop))
    if bool(metadata.get("dialogue_trade_only")) or _text(metadata.get("hidden_contact_kind")):
        return "fence_contact"
    if domains & {"criminal"}:
        return "stash_site"
    if property_supports_player_business(prop):
        if domains & {"trade", "retail", "food", "medical", "repair"} or services:
            return "front"
        return "vendor_route"
    archetype = _key(metadata.get("archetype"))
    if archetype in {"residential", "apartment", "tenement", "shelter"}:
        return "stash_site"
    return "territory"


def gang_target_read(sim, gang_org_eid, prop):
    if not isinstance(prop, dict):
        return {"valid": False, "reason": "invalid_property"}
    property_id = _property_id(prop)
    metadata = _metadata(prop)
    if not property_id:
        return {"valid": False, "reason": "missing_property_id"}
    if _key(prop.get("kind")) != "building":
        return {"valid": False, "property_id": property_id, "reason": "not_building"}
    if _property_invalid_for_gang(prop):
        return {"valid": False, "property_id": property_id, "reason": "protected_or_objective"}
    if _same_gang_linked(sim, gang_org_eid, prop):
        return {"valid": False, "property_id": property_id, "reason": "already_claimed"}

    profile = gang_enterprise_profile(sim, gang_org_eid)
    domains = set(property_field_domains(prop))
    service_ids = set(property_service_ids(prop))
    resistance = set()
    if _player_owned_property(sim, prop):
        resistance.add("player_owned")
    if _text(metadata.get("cult_id")) or _text(metadata.get("sacred_to_cult")):
        resistance.add("cult_pressure")
    rival = _rival_gang_link(sim, gang_org_eid, prop)
    if rival:
        resistance.add("rival_gang")
    if _text(metadata.get("corporate_acquisition")) or any(_key(link.get("organization_kind")) == "corporation" for link in property_org_links(sim, prop, active_only=True)):
        resistance.add("corporate_security")

    score = 0.34
    if property_supports_player_business(prop):
        score += 0.2
    if metadata.get("is_storefront"):
        score += 0.08
    if service_ids:
        score += 0.08
    if domains & {"criminal", "trade", "retail", "logistics", "repair"}:
        score += 0.13
    if resistance & {"rival_gang", "corporate_security"}:
        score += 0.1
    if "player_owned" in resistance:
        score -= 0.16
    seed = f"gang-target:{getattr(sim, 'seed', 0)}:{gang_org_eid}:{property_id}"
    score += random.Random(seed).uniform(-0.035, 0.035)
    claim_kind = _claim_kind_for_property(prop)
    can_claim = "player_owned" not in resistance and "corporate_security" not in resistance
    return {
        "valid": True,
        "property_id": property_id,
        "property_name": _text(prop.get("name")) or _text(metadata.get("business_name")) or "property",
        "gang_org_eid": int(gang_org_eid),
        "claim_kind": claim_kind,
        "rival_gang_eid": rival,
        "resistance_tags": tuple(sorted(resistance)),
        "reason_tags": tuple(sorted(domains | service_ids | resistance | {claim_kind})),
        "score": max(0.0, min(1.0, score)),
        "can_claim": bool(can_claim),
        "visible_cue": gang_visible_cue(gang_org_eid, prop, action_kind="targeting", claim_kind=claim_kind, resistance_tags=resistance),
    }


def gang_enterprise_candidate_properties(sim, gang_org_eid, *, include_resistant=True, limit=32):
    if not _is_gang_organization(sim, gang_org_eid):
        return ()
    rows = []
    for prop in tuple(getattr(sim, "properties", {}).values()):
        row = gang_target_read(sim, gang_org_eid, prop)
        if not row.get("valid"):
            continue
        if row.get("resistance_tags") and not include_resistant:
            continue
        rows.append(row)
    rows.sort(key=lambda row: (-_safe_float(row.get("score"), default=0.0), _text(row.get("property_name")).lower(), _text(row.get("property_id"))))
    if limit is not None:
        rows = rows[: max(0, _safe_int(limit, default=32))]
    return tuple(rows)


def gang_visible_cue(gang_org_eid, prop, *, action_kind, claim_kind="", resistance_tags=()):
    claim_kind = _key(claim_kind)
    resistance = set(resistance_tags or ())
    if action_kind == "territory_contest" or "rival_gang" in resistance:
        return "repeated faces and hard looks make the corner feel contested"
    if action_kind in {"vendor_tax", "protection_money"}:
        return "the counter has a nervous rhythm around certain regulars"
    if action_kind == "weapon_flow":
        return "gear handoffs and careful glances make the supply line visible"
    if action_kind in {"intimidation", "retaliation"}:
        return "people lower their voices when the same crew colors pass"
    if claim_kind == "front":
        return "matching colors and repeated faces are turning the frontage into a crew place"
    if claim_kind == "stash_site":
        return "the place has too many short visits and too few honest errands"
    if claim_kind == "fence_contact":
        return "quiet handoffs make the back channel feel organized"
    if claim_kind == "vendor_route":
        return "street sellers keep checking the same corner before moving on"
    return "the same colors and faces keep returning to this block"


def _claim_link_kind(claim_kind):
    key = _key(claim_kind)
    if key in {"stash_site", "safehouse"}:
        return "safehouse"
    if key in {"front", "fence_contact", "vendor_route"}:
        return "service_host"
    return "territory"


def claim_gang_territory(sim, gang_org_eid, prop, *, claim_kind=None, visible=True):
    """Attach a gang to a concrete property as territory/front/stash/fence."""

    if not _is_gang_organization(sim, gang_org_eid):
        return {"ok": False, "reason": "not_gang"}
    target = gang_target_read(sim, gang_org_eid, prop)
    if not target.get("valid"):
        return {"ok": False, "reason": target.get("reason", "invalid_target"), "target": target}
    claim_kind = _key(claim_kind) or _key(target.get("claim_kind")) or "territory"
    if claim_kind not in GANG_CLAIM_KINDS:
        return {"ok": False, "reason": "invalid_claim_kind", "target": target}
    if not target.get("can_claim") and claim_kind != "territory":
        return {"ok": False, "reason": "resisted_target", "target": target}

    property_id = _property_id(prop)
    now = _tick(sim)
    state = ensure_gang_enterprise_state(sim)
    cue = gang_visible_cue(gang_org_eid, prop, action_kind=f"{claim_kind}_claim", claim_kind=claim_kind, resistance_tags=target.get("resistance_tags", ()))
    link = link_property_organization(
        sim,
        prop,
        organization_eid=gang_org_eid,
        link_kind=_claim_link_kind(claim_kind),
        primary=False,
        active=True,
    )
    metadata = _metadata(prop)
    metadata.setdefault("gang_enterprise", {})
    metadata["gang_enterprise"] = {
        **dict(metadata.get("gang_enterprise") or {}),
        "organization_eid": int(gang_org_eid),
        "claim_kind": claim_kind,
        "visible_cue": cue,
        "last_update_tick": now,
    }
    claim_key = f"gang_claim:{gang_org_eid}:{property_id}:{claim_kind}"
    row = {
        "claim_key": claim_key,
        "organization_eid": int(gang_org_eid),
        "property_id": property_id,
        "claim_kind": claim_kind,
        "link_kind": _claim_link_kind(claim_kind),
        "visible_cue": cue,
        "reason_tags": list(target.get("reason_tags", ()) or ()),
        "created_tick": now,
        "last_update_tick": now,
        "active": True,
    }
    state["claims"][claim_key] = row
    record_organization_pressure(
        sim,
        organization_eid=gang_org_eid,
        pressure_kind=f"gang_{claim_kind}",
        stance="transactional" if claim_kind in {"front", "fence_contact", "vendor_route"} else "competitive",
        reason_tags=("gang_enterprise", claim_kind, *tuple(target.get("reason_tags", ()) or ())),
        anchor_property_id=property_id,
        visible=bool(visible),
        visible_cue=cue,
        confidence=0.62,
        source_event="gang_enterprise_claim",
    )
    record_organization_vocabulary(
        sim,
        organization_eid=gang_org_eid,
        vocabulary_kind="directive",
        entry_key=f"gang_{claim_kind}:{property_id}",
        topic_key=f"gang_{claim_kind}",
        label=f"{claim_kind.replace('_', ' ').title()}",
        summary=cue,
        source_kind="gang_enterprise",
        subject_property_id=property_id,
        target_property_id=property_id,
        tags=("gang_enterprise", claim_kind),
        priority=58,
    )
    _record_gang_practice(sim, gang_org_eid, prop, action_kind=f"{claim_kind}_claim", claim_kind=claim_kind)
    house_game = None
    if claim_kind in {"front", "fence_contact", "vendor_route"}:
        house_game = apply_gang_house_game_to_property(sim, gang_org_eid, prop, exposure=claim_kind, visible=visible)
    return {"ok": True, "claim": dict(row), "link": link, "target": target, "visible_cue": cue, "house_game": house_game}


def _member_eids(sim, gang_org_eid):
    profile = organization_profile(sim, gang_org_eid)
    if profile is None:
        return ()
    return tuple(sorted(_safe_int(eid, default=0) for eid in tuple(getattr(profile, "member_eids", ()) or ()) if _safe_int(eid, default=0) > 0))


def _role_rank(title):
    title = _key(title)
    if title in {"cell_lead", "leader"}:
        return 15
    if title in {"enforcer", "stash_keeper", "fence_contact"}:
        return 45
    if title in {"recruiter", "dealer"}:
        return 55
    if title in {"runner", "lookout", "front_employee"}:
        return 70
    return 75


def choose_gang_role(sim, gang_org_eid, actor_eid, *, prop=None):
    career = ""
    occupation = getattr(sim, "ecs").get(Occupation).get(actor_eid)
    if occupation is not None:
        career = _key(getattr(occupation, "career", ""))
    if "fence" in career:
        return "fence contact"
    if "dealer" in career:
        return "dealer"
    if "guard" in career or "security" in career or "enforcer" in career:
        return "enforcer"
    if "lookout" in career or "watch" in career:
        return "lookout"
    if "runner" in career or "courier" in career:
        return "runner"
    seed = f"gang-role:{getattr(sim, 'seed', 0)}:{gang_org_eid}:{actor_eid}:{_property_id(prop)}"
    return random.Random(seed).choice(GANG_ROLE_TITLES)


def apply_gang_appearance_signal(sim, actor_eid, gang_org_eid):
    """Apply a deterministic gang tattoo/style signal to an actor's loadout."""

    loadout = appearance_loadout_for(sim, actor_eid, create=True)
    if loadout is None:
        return {"ok": False, "reason": "missing_loadout"}
    style = gang_style_profile(sim, gang_org_eid)
    preferred_slots = (style.get("tattoo_slot"), *GANG_TATTOO_SLOTS)
    applied = None
    for slot in preferred_slots:
        slot = _key(slot)
        if not slot:
            continue
        result = apply_tattoo_service(
            sim,
            actor_eid,
            design=_text(style.get("tattoo_design")),
            slot=slot,
            source_metadata={"tattoo_location": slot.replace("_", " ")},
            prop=None,
        )
        if getattr(result, "ok", False):
            applied = slot
            break
        existing = dict(getattr(loadout, "skin_marks", {}) or {}).get(slot)
        if isinstance(existing, dict) and existing.get("gang_organization_eid") == int(gang_org_eid):
            applied = slot
            break
    if applied:
        mark = dict(loadout.skin_marks.get(applied) or {})
        mark.update(
            {
                "source": "gang_affiliation",
                "gang_signal": True,
                "gang_organization_eid": int(gang_org_eid),
                "gang_style_color": _text(style.get("color")),
                "gang_motif": _text(style.get("motif")),
            }
        )
        loadout.skin_marks[applied] = mark
    overrides = dict(getattr(loadout, "body_overrides", {}) or {})
    overrides["gang_style_color"] = _text(style.get("color"))
    overrides["gang_style_summary"] = _text(style.get("style_summary"))
    hair_rule = _text(style.get("hair_rule"))
    if hair_rule and hair_rule != "none" and not _text(overrides.get("hair_style")):
        overrides["hair_style"] = hair_rule
        overrides["hair_style_compact"] = hair_rule
    loadout.body_overrides = loadout._clean_overrides(overrides)
    return {
        "ok": True,
        "tattoo_slot": applied,
        "style": dict(style),
        "tattoo_applied": bool(applied),
    }


def assign_gang_enterprise_role(sim, actor_eid, gang_org_eid, *, title=None, prop=None, primary=False):
    if not _is_gang_organization(sim, gang_org_eid):
        return {"ok": False, "reason": "not_gang"}
    title = _text(title) or choose_gang_role(sim, gang_org_eid, actor_eid, prop=prop)
    property_id = _property_id(prop)
    building_id = _text(_metadata(prop).get("building_id") or _metadata(prop).get("local_building_id")) if isinstance(prop, dict) else ""
    assign_actor_organization(
        sim,
        actor_eid,
        organization_eid=gang_org_eid,
        role="member",
        kind="membership",
        title=title,
        primary=bool(primary),
        authority_rank=_role_rank(title),
        site_property_id=property_id,
        site_building_id=building_id,
        active=True,
    )
    style_result = apply_gang_appearance_signal(sim, actor_eid, gang_org_eid)
    state = ensure_gang_enterprise_state(sim)
    role_key = f"gang_role:{gang_org_eid}:{actor_eid}"
    row = {
        "role_key": role_key,
        "organization_eid": int(gang_org_eid),
        "actor_eid": int(actor_eid),
        "title": title,
        "property_id": property_id,
        "style": dict(style_result.get("style") or {}),
        "last_update_tick": _tick(sim),
        "active": True,
    }
    state["roles"][role_key] = row
    return {"ok": True, "role": dict(row), "style": style_result}


def _record_gang_practice(sim, gang_org_eid, prop, *, action_kind, claim_kind=""):
    property_id = _property_id(prop)
    if not property_id:
        return None
    action_kind = _key(action_kind)
    claim_kind = _key(claim_kind)
    modifiers = {
        "front_pressure": 0.18,
        "stash_flow": 0.1 if claim_kind != "stash_site" else 0.28,
        "lookout_bias": 0.12 if claim_kind in {"territory", "front"} else 0.06,
        "fence_bias": 0.2 if claim_kind == "fence_contact" else 0.06,
        "recruitment_bias": 0.08,
    }
    if action_kind in {"intimidation", "retaliation", "territory_contest"}:
        modifiers["retaliation_bias"] = 0.22
        modifiers["lookout_bias"] = max(modifiers["lookout_bias"], 0.18)
    return record_organization_practice(
        sim,
        organization_eid=gang_org_eid,
        practice_kind="operational_pattern",
        entry_key=f"gang_enterprise:{gang_org_eid}:{property_id}:{action_kind or claim_kind}",
        domain_key="criminal",
        label="Gang enterprise pressure",
        summary="The crew has practical habits around this site: short visits, lookouts, pressure, and handoffs.",
        source_kind="gang_enterprise",
        service_ids=property_service_ids(prop),
        target_scope="property",
        target_property_id=property_id,
        target_field_domains=property_field_domains(prop),
        effect_modifiers=modifiers,
        tags=("gang_enterprise", action_kind, claim_kind),
        priority=62,
    )


def _record_enterprise_action(sim, gang_org_eid, prop, *, action_kind, status, target_read, visible_cue):
    state = ensure_gang_enterprise_state(sim)
    now = _tick(sim)
    property_id = _property_id(prop)
    key = f"gang_action:{gang_org_eid}:{property_id}:{action_kind}"
    row = {
        "action_key": key,
        "action_id": _safe_int(state.get("next_action_id"), default=1),
        "organization_eid": int(gang_org_eid),
        "property_id": property_id,
        "action_kind": action_kind,
        "status": status,
        "claim_kind": _text(target_read.get("claim_kind")),
        "score": _safe_float(target_read.get("score"), default=0.0),
        "resistance_tags": list(target_read.get("resistance_tags", ()) or ()),
        "reason_tags": list(target_read.get("reason_tags", ()) or ()),
        "visible_cue": visible_cue,
        "created_tick": now,
        "last_update_tick": now,
        "expires_tick": now + GANG_ENTERPRISE_TTL,
    }
    state["actions"][key] = row
    state["next_action_id"] = max(_safe_int(state.get("next_action_id"), default=1), row["action_id"] + 1)
    return dict(row)


def _maybe_record_enterprise_plan(sim, gang_org_eid, prop, *, action_kind, target_read):
    members = _member_eids(sim, gang_org_eid)
    if not members:
        return None
    action_kind = _key(action_kind)
    if action_kind in {"stash_site", "fence_route", "weapon_flow"}:
        kind = "fence_run"
    elif action_kind in {"front_claim", "vendor_tax", "protection_money"}:
        kind = "covert_sale"
    else:
        return None
    property_id = _property_id(prop)
    plan_key = f"gang_enterprise:{gang_org_eid}:{_tick(sim) // max(1, GANG_ENTERPRISE_INTERVAL)}:{kind}:{property_id}"
    return record_organization_crime_plan(
        sim,
        organization_eid=gang_org_eid,
        plan_key=plan_key,
        kind=kind,
        stage="rendezvous",
        method_key="fence_run_handoff" if kind == "fence_run" else "covert_sale_handoff",
        method_label="fence handoff" if kind == "fence_run" else "covert handoff",
        leader_eid=members[0],
        assigned_member_eids=members[: min(3, len(members))],
        target_property_id=property_id,
        staging_property_id=property_id,
        disposal_property_id=property_id,
        created_tick=_tick(sim),
        execute_after_tick=_tick(sim) + 18,
        expires_tick=_tick(sim) + 150,
        required_member_count=1,
        source_pressure=_safe_float(target_read.get("score"), default=0.5),
        summary=f"gang enterprise {kind.replace('_', ' ')} around {_text(prop.get('name')) or property_id}",
    )


def apply_gang_enterprise_action(sim, gang_org_eid, prop, *, action_kind=None, visible=True):
    if not _is_gang_organization(sim, gang_org_eid):
        return {"ok": False, "reason": "not_gang"}
    target = gang_target_read(sim, gang_org_eid, prop)
    if not target.get("valid"):
        return {"ok": False, "reason": target.get("reason", "invalid_target"), "target": target}
    if not action_kind:
        action_kind = select_gang_enterprise_action(sim, gang_org_eid, target)
    action_kind = _key(action_kind)
    if action_kind not in GANG_ENTERPRISE_ACTIONS:
        return {"ok": False, "reason": "invalid_action", "target": target}

    claim_kind = _key(target.get("claim_kind"))
    status = "pressure_active"
    claim = None
    if action_kind in {"territory_claim", "front_claim", "stash_site", "fence_route"} and target.get("can_claim"):
        claim_action = {
            "territory_claim": "territory",
            "front_claim": "front",
            "stash_site": "stash_site",
            "fence_route": "fence_contact",
        }.get(action_kind, claim_kind)
        claim = claim_gang_territory(sim, gang_org_eid, prop, claim_kind=claim_action, visible=visible)
        status = "claimed" if claim.get("ok") else "pressure_active"
    elif action_kind == "territory_contest" or target.get("rival_gang_eid"):
        status = "contested"
    elif target.get("resistance_tags"):
        status = "resisted"

    cue = gang_visible_cue(gang_org_eid, prop, action_kind=action_kind, claim_kind=claim_kind, resistance_tags=target.get("resistance_tags", ()))
    stance = "transactional" if action_kind in {"front_claim", "vendor_tax", "protection_money", "fence_route", "weapon_flow"} else "competitive"
    if action_kind in {"intimidation", "retaliation"} or status == "contested":
        stance = "hostile"
    related_org = _safe_int(target.get("rival_gang_eid"), default=0) or None
    if related_org:
        record_organization_relationship(
            sim,
            org_a_eid=gang_org_eid,
            org_b_eid=related_org,
            stance="hostile" if action_kind in {"retaliation", "intimidation", "territory_contest"} else "competitive",
            confidence=0.68,
            reason_tags=("gang_enterprise", action_kind, "territory_overlap"),
            source_event="gang_enterprise",
            anchor_property_id=_property_id(prop),
            visible=bool(visible),
            visible_cue=cue,
            cooldown_ticks=300,
        )
    pressure = record_organization_pressure(
        sim,
        organization_eid=gang_org_eid,
        related_org_eid=related_org,
        pressure_kind=f"gang_{action_kind}",
        stance=stance,
        reason_tags=("gang_enterprise", action_kind, status, *tuple(target.get("reason_tags", ()) or ())),
        anchor_property_id=_property_id(prop),
        visible=bool(visible),
        visible_cue=cue,
        confidence=0.68,
        source_event="gang_enterprise",
    )
    practice = _record_gang_practice(sim, gang_org_eid, prop, action_kind=action_kind, claim_kind=claim_kind)
    plan = _maybe_record_enterprise_plan(sim, gang_org_eid, prop, action_kind=action_kind, target_read=target)
    action = _record_enterprise_action(sim, gang_org_eid, prop, action_kind=action_kind, status=status, target_read=target, visible_cue=cue)
    return {
        "ok": True,
        "action": action,
        "claim": claim,
        "pressure": pressure,
        "practice": practice,
        "plan": plan,
        "target": target,
        "status": status,
        "visible_cue": cue,
    }


def select_gang_enterprise_action(sim, gang_org_eid, target_read):
    if not isinstance(target_read, dict) or not target_read.get("valid"):
        return ""
    resistance = set(target_read.get("resistance_tags", ()) or ())
    profile = gang_enterprise_profile(sim, gang_org_eid)
    seed = f"gang-action:{getattr(sim, 'seed', 0)}:{_tick(sim) // GANG_ENTERPRISE_INTERVAL}:{gang_org_eid}:{target_read.get('property_id')}"
    rng = random.Random(seed)
    if "rival_gang" in resistance:
        return "territory_contest"
    if resistance and rng.random() < _safe_float(profile.get("aggression"), default=0.4):
        return rng.choice(("intimidation", "protection_money", "retaliation"))
    claim_kind = _key(target_read.get("claim_kind"))
    if claim_kind == "front":
        return rng.choice(("front_claim", "vendor_tax", "protection_money"))
    if claim_kind == "stash_site":
        return "stash_site"
    if claim_kind == "fence_contact":
        return "fence_route"
    if claim_kind == "vendor_route":
        return rng.choice(("vendor_tax", "territory_claim"))
    return "territory_claim"


def record_gang_enterprise_deal(
    sim,
    gang_org_eid,
    partner_org_eid,
    *,
    deal_kind="street_arrangement",
    anchor_property_id=None,
    visible=False,
):
    if not _is_gang_organization(sim, gang_org_eid) or organization_profile(sim, partner_org_eid) is None:
        return None
    deal_kind = _key(deal_kind) or "street_arrangement"
    compatibility = organization_compatibility_read(sim, gang_org_eid, partner_org_eid)
    stance = "transactional"
    if deal_kind in {"weapon_supply", "vendor_route", "fence_access", "street_arrangement", "customer_flow"}:
        stance = "transactional"
    if deal_kind in {"truce", "mutual_enforcement"}:
        stance = "allied"
    if deal_kind in {"territory_overlap", "rival_front", "failed_payment"}:
        stance = "competitive"
    if deal_kind in {"retaliation", "exposed_informant", "bodyguard_conflict"}:
        stance = "hostile"
    if deal_kind in {"sacred_conflict", "devotion_conflict"}:
        stance = "sacred_conflict"
    cue = "the arrangement reads through repeated faces, guarded handoffs, and careful counter habits"
    if stance == "hostile":
        cue = "the street pressure feels ready to become violence if someone pushes"
    elif stance == "competitive":
        cue = "the same corners are being measured by different crews"
    elif stance == "allied":
        cue = "the crews move like they know where not to step on each other"
    elif stance == "sacred_conflict":
        cue = "money pressure is colliding with something people refuse to treat as business"
    return record_organization_relationship(
        sim,
        org_a_eid=gang_org_eid,
        org_b_eid=partner_org_eid,
        stance=stance,
        confidence=0.63,
        reason_tags=("gang_enterprise", deal_kind, *tuple(compatibility.get("reason_tags", ()) or ())),
        source_event="gang_enterprise_deal",
        anchor_property_id=anchor_property_id,
        visible=bool(visible),
        visible_cue=cue,
        cooldown_ticks=300,
    )


def record_gang_enterprise_actor_event(
    sim,
    *,
    actor_eid,
    gang_org_eid,
    prop=None,
    tactic="intimidation",
    target_eid=None,
    witnessed=False,
    observer_eids=(),
):
    """Emit an ordinary actor event with gang-enterprise motive metadata."""

    tactic = _key(tactic) or "intimidation"
    observer_eids = tuple(int(eid) for eid in tuple(observer_eids or ()) if _safe_int(eid, default=0) > 0)
    if tactic in {"assault", "weapon_threat"} and _safe_int(target_eid, default=0) > 0:
        event = Event(
            "action_offense",
            offender_eid=_safe_int(actor_eid, default=0),
            victim_eid=_safe_int(target_eid, default=0),
            action_kind="criminal_attack" if tactic == "assault" else "weapon_threat",
            offense_kind="assault" if tactic == "assault" else "threat",
            severity_score=72 if tactic == "assault" else 36,
            witnessed=bool(witnessed),
            witness_count=len(observer_eids) if witnessed else 0,
            witnesses=observer_eids if witnessed else (),
            gang_enterprise_motive=True,
            source_organization_eid=int(gang_org_eid),
        )
        sim.emit(event)
        return event

    prop = prop if isinstance(prop, dict) else {}
    severity = {
        "intimidation": 26,
        "protection_money": 32,
        "vandalism": 46,
        "arson_attempt": 76,
        "retaliation": 58,
        "territory_mark": 22,
    }.get(tactic, 34)
    event = Event(
        "property_tamper",
        offender_eid=_safe_int(actor_eid, default=0),
        property_id=_property_id(prop),
        property_name=_text(prop.get("name")),
        x=_safe_int(prop.get("x"), default=0),
        y=_safe_int(prop.get("y"), default=0),
        z=_safe_int(prop.get("z"), default=0),
        witnessed=bool(witnessed),
        witness_count=len(observer_eids) if witnessed else 0,
        witnesses=observer_eids if witnessed else (),
        access_level="restricted",
        severity_score=int(severity),
        severity_label="serious_tamper" if severity >= 45 else "tamper",
        ingress_kind="gang_enterprise_pressure",
        ingress_method=tactic,
        standing_reason="none",
        gang_enterprise_motive=True,
        source_organization_eid=int(gang_org_eid),
    )
    sim.emit(event)
    return event


def gang_pressure_for_property(sim, prop):
    if not isinstance(prop, dict):
        return ()
    property_id = _property_id(prop)
    state = ensure_gang_enterprise_state(sim)
    rows = [
        dict(row)
        for row in state.get("actions", {}).values()
        if isinstance(row, dict) and _text(row.get("property_id")) == property_id
    ]
    rows.extend(
        {
            **dict(row),
            "action_kind": _text(row.get("action_kind")) or f"{_text(row.get('claim_kind'))}_claim",
            "status": _text(row.get("status")) or "claimed",
        }
        for row in state.get("claims", {}).values()
        if isinstance(row, dict) and _text(row.get("property_id")) == property_id
    )
    rows.sort(key=lambda row: (-_safe_int(row.get("last_update_tick"), default=0), _text(row.get("action_kind"))))
    return tuple(rows)


def advance_gang_enterprise(sim, *, limit=1):
    state = ensure_gang_enterprise_state(sim)
    now = _tick(sim)
    results = []
    for gang in gang_organization_rows(sim):
        if len(results) >= max(1, _safe_int(limit, default=1)):
            break
        gang_org_eid = _safe_int(gang.get("organization_eid"), default=0)
        cooldown_key = f"gang:{gang_org_eid}:enterprise"
        if _safe_int(state.get("cooldowns", {}).get(cooldown_key), default=0) > now:
            continue
        candidates = gang_enterprise_candidate_properties(sim, gang_org_eid, include_resistant=True, limit=8)
        if not candidates:
            state["cooldowns"][cooldown_key] = now + GANG_ENTERPRISE_INTERVAL
            continue
        target = candidates[0]
        prop = getattr(sim, "properties", {}).get(target.get("property_id"))
        if not isinstance(prop, dict):
            state["cooldowns"][cooldown_key] = now + GANG_ENTERPRISE_INTERVAL
            continue
        result = apply_gang_enterprise_action(sim, gang_org_eid, prop, action_kind=select_gang_enterprise_action(sim, gang_org_eid, target))
        if result.get("ok"):
            results.append(result)
        state["cooldowns"][cooldown_key] = now + GANG_ENTERPRISE_INTERVAL
    return tuple(results)


class GangEnterpriseSystem(System):
    """Slow, bounded gang enterprise pulse."""

    def __init__(self, sim, refresh_interval=GANG_ENTERPRISE_INTERVAL):
        super().__init__(sim)
        self.refresh_interval = max(120, _safe_int(refresh_interval, default=GANG_ENTERPRISE_INTERVAL))
        self._next_tick = 0

    def update(self):
        now = _tick(self.sim)
        if now < self._next_tick:
            return
        self._next_tick = now + self.refresh_interval
        advance_gang_enterprise(self.sim, limit=1)


__all__ = [
    "GangEnterpriseSystem",
    "advance_gang_enterprise",
    "apply_gang_appearance_signal",
    "apply_gang_enterprise_action",
    "assign_gang_enterprise_role",
    "claim_gang_territory",
    "ensure_gang_enterprise_state",
    "gang_enterprise_candidate_properties",
    "gang_enterprise_profile",
    "gang_organization_rows",
    "gang_pressure_for_property",
    "gang_style_profile",
    "gang_target_read",
    "record_gang_enterprise_actor_event",
    "record_gang_enterprise_deal",
    "select_gang_enterprise_action",
]
