"""Corporate expansion and deniable pressure helpers.

This layer consumes the shared organization diplomacy substrate.  It is not a
stock-market or government simulator; it gives corporate organizations bounded
ways to pick targets, pressure holdouts, and leave visible evidence in the
world while keeping actual crimes attached to the actors who commit them.
"""

from __future__ import annotations

import random

from engine.events import Event
from engine.systems import System
from game.components import OrganizationProfile, PlayerAssets
from game.corporate_presence import (
    refresh_all_corporate_neighborhood_presence,
    refresh_corporate_neighborhood_presence,
)
from game.organizations import (
    ensure_organization_diplomacy_state,
    ensure_property_organization,
    link_property_organization,
    organization_compatibility_read,
    organization_policy_snapshot,
    organization_profile,
    property_field_domains,
    property_organization_eid,
    property_org_links,
    property_service_ids,
    record_organization_practice,
    record_organization_pressure,
    record_organization_relationship,
)
from game.player_businesses import property_supports_player_business


CORPORATE_EXPANSION_INTERVAL = 720
CORPORATE_ACTION_TTL = 24 * 600
CORPORATE_INVALID_METADATA_FLAGS = frozenset(
    (
        "critical",
        "objective",
        "objective_critical",
        "quest_critical",
        "final_operation",
        "final_operation_site",
        "no_acquisition",
        "no_corporate_acquisition",
        "player_protected",
        "protected_from_acquisition",
    )
)
CORPORATE_LEGAL_ACTIONS = frozenset(
    (
        "buyout_offer",
        "branch_opening",
        "franchise_offer",
        "service_exclusivity",
        "supply_pressure",
        "staff_poaching",
        "pricing_pressure",
        "security_upgrade",
    )
)
CORPORATE_DENIABLE_ACTIONS = frozenset(
    (
        "fake_inspection",
        "intimidation",
        "vandalism",
        "arson_attempt",
        "gang_contract",
        "hostile_rumor",
    )
)
CORPORATE_ALL_ACTIONS = CORPORATE_LEGAL_ACTIONS | CORPORATE_DENIABLE_ACTIONS
CORPORATE_RESISTANCE_TAGS = frozenset(
    (
        "player_owned",
        "cult_associated",
        "sacred_site",
        "gang_front",
        "rival_corporate",
        "stubborn_owner",
    )
)


def _text(value):
    return str(value or "").strip()


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _slug(value):
    cleaned = []
    for char in _text(value).lower():
        if char.isalnum():
            cleaned.append(char)
        elif cleaned and cleaned[-1] != "_":
            cleaned.append("_")
    return "".join(cleaned).strip("_")


def _metadata(prop):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        prop["metadata"] = metadata
    return metadata


def _tick(sim):
    return _safe_int(getattr(sim, "tick", 0), default=0)


def _corp_state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    state = traits.get("corporate_expansion")
    if not isinstance(state, dict):
        state = {}
        traits["corporate_expansion"] = state
    for key in ("actions", "goals", "cooldowns"):
        if not isinstance(state.get(key), dict):
            state[key] = {}
    state["next_action_id"] = max(1, _safe_int(state.get("next_action_id"), default=1))
    return state


def ensure_corporate_expansion_state(sim):
    """Return the save-compatible corporate expansion state."""

    state = _corp_state(sim)
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
    ensure_organization_diplomacy_state(sim)
    return state


def _organization_tags(profile):
    return {str(tag).strip().lower() for tag in (getattr(profile, "tags", ()) or ()) if str(tag).strip()}


def _is_corporate_organization(sim, organization_eid):
    profile = organization_profile(sim, organization_eid)
    if profile is None:
        return False
    policy = organization_policy_snapshot(sim, organization_eid=organization_eid) or {}
    tags = _organization_tags(profile)
    kind = _text(getattr(profile, "kind", "")).lower()
    family = _text(policy.get("family")).lower()
    return family == "corporate" or kind == "corporation" or "corporate" in tags or "corpsec" in tags


def corporate_organization_rows(sim):
    """Return active corporate organization refs."""

    rows = []
    for organization_eid, _profile_component in tuple(getattr(sim, "ecs").get(OrganizationProfile).items()):
        if not _is_corporate_organization(sim, organization_eid):
            continue
        profile = organization_profile(sim, organization_eid)
        if profile is None:
            continue
        policy = organization_policy_snapshot(sim, organization_eid=organization_eid) or {}
        rows.append(
            {
                "organization_eid": int(organization_eid),
                "organization_key": _text(getattr(profile, "key", "")),
                "organization_name": _text(getattr(profile, "name", "")) or "Corporate office",
                "organization_kind": _text(getattr(profile, "kind", "")) or "corporation",
                "family": _text(policy.get("family")) or "corporate",
                "root_organization_eid": _safe_int(policy.get("root_organization_eid"), default=int(organization_eid)),
                "tags": tuple(sorted(_organization_tags(profile))),
            }
        )
    rows.sort(key=lambda row: (_text(row.get("organization_name")).lower(), row.get("organization_eid", 0)))
    return tuple(rows)


def corporate_expansion_profile(sim, corporate_org_eid):
    """Return a compact expansion read for a corporation."""

    profile = organization_profile(sim, corporate_org_eid)
    if profile is None:
        return {}
    policy = organization_policy_snapshot(sim, organization_eid=corporate_org_eid) or {}
    tags = _organization_tags(profile)
    domain_tags = tuple(sorted(tag.split(":", 1)[1] for tag in tags if tag.startswith("domain:") and tag.split(":", 1)[1]))
    interest_tags = tuple(sorted(tag.split(":", 1)[1] for tag in tags if tag.startswith("interest:") and tag.split(":", 1)[1]))
    aggression = 0.22
    if tags & {"aggressive", "corpsec", "hostile_takeover", "deniable_pressure"}:
        aggression += 0.28
    if tags & {"civic_partner", "cooperative", "relief_optics"}:
        aggression -= 0.1
    dirty = 0.12
    if tags & {"deniable_pressure", "aggressive", "corpsec"}:
        dirty += 0.35
    if tags & {"clean_brand", "compliance"}:
        dirty -= 0.08
    return {
        "organization_eid": int(corporate_org_eid),
        "organization_name": _text(getattr(profile, "name", "")) or "Corporate office",
        "family": _text(policy.get("family")) or "corporate",
        "domain_tags": domain_tags,
        "interest_tags": interest_tags,
        "aggression": max(0.0, min(1.0, aggression)),
        "deniable_pressure": max(0.0, min(1.0, dirty)),
        "tags": tuple(sorted(tags)),
    }


def _property_id(prop):
    return _text(prop.get("id")) if isinstance(prop, dict) else ""


def _player_owned_property(sim, prop):
    if not isinstance(prop, dict):
        return False
    owner_eid = _safe_int(prop.get("owner_eid"), default=0)
    if owner_eid > 0 and owner_eid == _safe_int(getattr(sim, "player_eid", 0), default=0):
        return True
    if owner_eid > 0 and getattr(sim, "ecs", None) is not None and sim.ecs.get(PlayerAssets).get(owner_eid) is not None:
        return True
    property_id = _property_id(prop)
    if not property_id:
        return False
    player_eid = _safe_int(getattr(sim, "player_eid", 0), default=0)
    assets = sim.ecs.get(PlayerAssets).get(player_eid) if player_eid > 0 else None
    owned = getattr(assets, "owned_properties", None)
    return isinstance(owned, (set, list, tuple)) and property_id in owned


def _metadata_flagged_invalid(metadata):
    return any(bool(metadata.get(flag)) for flag in CORPORATE_INVALID_METADATA_FLAGS)


def _resistance_tags_for_property(sim, corporate_org_eid, prop):
    metadata = _metadata(prop)
    tags = set()
    if _player_owned_property(sim, prop):
        tags.add("player_owned")
    if _text(metadata.get("cult_id")) or _text(metadata.get("cult_associated")):
        tags.add("cult_associated")
    if _text(metadata.get("sacred_to_cult")) or _text(metadata.get("devotion_target")):
        tags.add("sacred_site")
    if _text(metadata.get("gang_id")) or _text(metadata.get("gang_front")):
        tags.add("gang_front")
    if bool(metadata.get("stubborn_owner")):
        tags.add("stubborn_owner")

    local_org = property_organization_eid(sim, prop, ensure=False)
    if local_org and int(local_org) != int(corporate_org_eid):
        local_policy = organization_policy_snapshot(sim, organization_eid=local_org) or {}
        corp_policy = organization_policy_snapshot(sim, organization_eid=corporate_org_eid) or {}
        if _text(local_policy.get("family")).lower() == "corporate" and _safe_int(local_policy.get("root_organization_eid"), default=local_org) != _safe_int(corp_policy.get("root_organization_eid"), default=corporate_org_eid):
            tags.add("rival_corporate")
    return tuple(sorted(tags))


def _property_domain_score(expansion_profile, domains, service_ids):
    domains = {str(value).strip().lower() for value in (domains or ()) if str(value).strip()}
    service_ids = {str(value).strip().lower() for value in (service_ids or ()) if str(value).strip()}
    profile_domains = set(expansion_profile.get("domain_tags", ()) or ())
    interests = set(expansion_profile.get("interest_tags", ()) or ())
    score = 0.0
    if domains & profile_domains:
        score += 0.28
    if "customers" in interests and service_ids:
        score += 0.12
    if "supply" in interests and (domains & {"logistics", "industrial", "repair", "food"}):
        score += 0.12
    if "labor" in interests and service_ids:
        score += 0.06
    if "service_access" in interests and service_ids:
        score += 0.08
    return score


def corporate_target_read(sim, corporate_org_eid, prop):
    """Describe whether a property is a plausible corporate target."""

    if not isinstance(prop, dict):
        return {"valid": False, "reason": "invalid_property"}
    property_id = _property_id(prop)
    metadata = _metadata(prop)
    if not property_id:
        return {"valid": False, "reason": "missing_property_id"}
    if _text(prop.get("kind")).lower() != "building":
        return {"valid": False, "property_id": property_id, "reason": "not_building"}
    if _metadata_flagged_invalid(metadata):
        return {"valid": False, "property_id": property_id, "reason": "protected_or_objective"}
    if not property_supports_player_business(prop):
        return {"valid": False, "property_id": property_id, "reason": "not_business"}

    policy = organization_policy_snapshot(sim, organization_eid=corporate_org_eid) or {}
    local_org = property_organization_eid(sim, prop, ensure=False)
    local_policy = organization_policy_snapshot(sim, organization_eid=local_org) if local_org else None
    corporate_root = _safe_int(policy.get("root_organization_eid"), default=corporate_org_eid)
    local_root = _safe_int((local_policy or {}).get("root_organization_eid"), default=local_org or 0)
    linked_same_lineage = False
    for link in property_org_links(sim, prop, active_only=True):
        linked_eid = _safe_int(link.get("organization_eid"), default=0)
        if linked_eid <= 0:
            continue
        linked_policy = organization_policy_snapshot(sim, organization_eid=linked_eid) or {}
        linked_root = _safe_int(linked_policy.get("root_organization_eid"), default=linked_eid)
        if linked_root == corporate_root:
            linked_same_lineage = True
            break
    if (local_org and local_root and local_root == corporate_root) or linked_same_lineage:
        return {"valid": False, "property_id": property_id, "reason": "already_corporate_lineage"}

    expansion = corporate_expansion_profile(sim, corporate_org_eid)
    domains = property_field_domains(prop)
    service_ids = property_service_ids(prop)
    resistance_tags = _resistance_tags_for_property(sim, corporate_org_eid, prop)
    base = 0.42
    base += _property_domain_score(expansion, domains, service_ids)
    if metadata.get("is_storefront"):
        base += 0.1
    if _text(metadata.get("business_name")):
        base += 0.04
    if "player_owned" in resistance_tags:
        base -= 0.18
    if "rival_corporate" in resistance_tags:
        base += 0.12
    if "sacred_site" in resistance_tags:
        base += 0.05
    jitter_seed = f"{getattr(sim, 'seed', 0)}:{corporate_org_eid}:{property_id}:corporate_target"
    base += random.Random(jitter_seed).uniform(-0.035, 0.035)
    score = max(0.0, min(1.0, base))
    can_acquire = not any(tag in resistance_tags for tag in ("player_owned", "sacred_site", "gang_front", "rival_corporate"))
    if "stubborn_owner" in resistance_tags and score < 0.75:
        can_acquire = False
    action_kinds = ("buyout_offer", "branch_opening", "franchise_offer", "service_exclusivity", "security_upgrade")
    if resistance_tags:
        action_kinds = ("buyout_offer", "supply_pressure", "pricing_pressure", "fake_inspection", "intimidation")
    return {
        "valid": True,
        "property_id": property_id,
        "property_name": _text(prop.get("name")) or _text(metadata.get("business_name")) or "business",
        "corporate_org_eid": int(corporate_org_eid),
        "local_org_eid": int(local_org) if local_org else None,
        "score": score,
        "can_acquire": bool(can_acquire),
        "resistance_tags": tuple(sorted(resistance_tags)),
        "reason_tags": tuple(sorted(set(domains) | set(service_ids) | set(resistance_tags))),
        "action_kinds": action_kinds,
        "visible_cue": corporate_visible_cue(corporate_org_eid, prop, action_kind="targeting", resistance_tags=resistance_tags),
    }


def corporate_acquisition_candidate_properties(sim, corporate_org_eid, *, include_resistant=True, limit=32):
    """Return sorted plausible corporate targets from real property state."""

    if not _is_corporate_organization(sim, corporate_org_eid):
        return ()
    candidates = []
    for prop in tuple(getattr(sim, "properties", {}).values()):
        read = corporate_target_read(sim, corporate_org_eid, prop)
        if not read.get("valid"):
            continue
        if read.get("resistance_tags") and not include_resistant:
            continue
        candidates.append(read)
    candidates.sort(key=lambda row: (-_safe_float(row.get("score"), default=0.0), _text(row.get("property_name")).lower(), _text(row.get("property_id"))))
    if limit is not None:
        candidates = candidates[: max(0, _safe_int(limit, default=32))]
    return tuple(candidates)


def corporate_visible_cue(corporate_org_eid, prop, *, action_kind, resistance_tags=()):
    name = "the company"
    resistance = set(resistance_tags or ())
    if action_kind in {"buyout_offer", "branch_opening", "franchise_offer"}:
        if resistance:
            return "paperwork, new signs, and wary counter-talk make the pressure visible"
        return "fresh corporate signage and matching counter habits are starting to show"
    if action_kind == "security_upgrade":
        return "security posture is tighter, cleaner, and more standardized than before"
    if action_kind in {"service_exclusivity", "supply_pressure"}:
        return "stock and delivery habits look like they are being steered from outside"
    if action_kind in {"fake_inspection", "intimidation"}:
        return "official-looking questions and hard smiles are making the frontage tense"
    if action_kind == "vandalism":
        return "the damage looks less random than everyone is willing to say out loud"
    if action_kind == "arson_attempt":
        return "scorch marks and careful silence make the pressure hard to miss"
    if action_kind == "gang_contract":
        return "street pressure and business pressure are sharing the same doorway"
    if action_kind == "hostile_rumor":
        return "the rumor weather around the counter has gone pointed and commercial"
    return f"{name} is giving this place a corporate look"


def select_corporate_action_for_target(sim, corporate_org_eid, target_read):
    if not isinstance(target_read, dict) or not target_read.get("valid"):
        return ""
    resistance = set(target_read.get("resistance_tags", ()) or ())
    expansion = corporate_expansion_profile(sim, corporate_org_eid)
    dirty = _safe_float(expansion.get("deniable_pressure"), default=0.0)
    seed = f"{getattr(sim, 'seed', 0)}:{_tick(sim) // CORPORATE_EXPANSION_INTERVAL}:{corporate_org_eid}:{target_read.get('property_id')}:action"
    rng = random.Random(seed)
    if resistance and dirty >= 0.35 and rng.random() < dirty:
        if "gang_front" in resistance:
            return "gang_contract"
        if "sacred_site" in resistance:
            return "intimidation"
        return rng.choice(("fake_inspection", "intimidation", "hostile_rumor"))
    if not target_read.get("can_acquire"):
        return rng.choice(("buyout_offer", "supply_pressure", "pricing_pressure", "security_upgrade"))
    return rng.choice(("buyout_offer", "branch_opening", "franchise_offer", "service_exclusivity", "security_upgrade"))


def _action_status(action_kind, target_read):
    if action_kind == "buyout_offer" and target_read.get("can_acquire"):
        return "acquired"
    if action_kind == "branch_opening" and target_read.get("can_acquire"):
        return "branch_linked"
    if action_kind == "franchise_offer" and target_read.get("can_acquire"):
        return "franchise_linked"
    if action_kind in CORPORATE_DENIABLE_ACTIONS:
        return "deniable_pressure"
    if target_read.get("resistance_tags"):
        return "resisted"
    return "pressure_active"


def _record_expansion_action(sim, corporate_org_eid, prop, *, action_kind, status, target_read, visible_cue):
    state = ensure_corporate_expansion_state(sim)
    now = _tick(sim)
    property_id = _property_id(prop)
    action_key = f"corporate_action:{corporate_org_eid}:{property_id}:{action_kind}"
    row = {
        "action_key": action_key,
        "action_id": _safe_int(state.get("next_action_id"), default=1),
        "corporate_org_eid": int(corporate_org_eid),
        "property_id": property_id,
        "action_kind": action_kind,
        "status": status,
        "score": _safe_float(target_read.get("score"), default=0.0),
        "resistance_tags": list(target_read.get("resistance_tags", ()) or ()),
        "reason_tags": list(target_read.get("reason_tags", ()) or ()),
        "visible_cue": visible_cue,
        "created_tick": now,
        "last_update_tick": now,
        "expires_tick": now + CORPORATE_ACTION_TTL,
    }
    state["actions"][action_key] = row
    state["goals"][f"{corporate_org_eid}:{property_id}"] = dict(row)
    state["next_action_id"] = max(_safe_int(state.get("next_action_id"), default=1), row["action_id"] + 1)
    return dict(row)


def _stamp_corporate_metadata(sim, corporate_org_eid, prop, *, action_kind, status, target_read, visible_cue):
    metadata = _metadata(prop)
    history = list((metadata.get("corporate_acquisition_history") or [])[-5:])
    entry = {
        "tick": _tick(sim),
        "corporate_org_eid": int(corporate_org_eid),
        "action_kind": action_kind,
        "status": status,
        "visible_cue": visible_cue,
        "resistance_tags": list(target_read.get("resistance_tags", ()) or ()),
    }
    history.append(entry)
    metadata["corporate_acquisition_history"] = history[-6:]
    metadata["corporate_acquisition"] = dict(entry)
    metadata["corporate_pressure_cue"] = visible_cue
    if status in {"acquired", "branch_linked", "franchise_linked"}:
        metadata["corporate_branding_active"] = True
    return metadata


def _record_corporate_practice(sim, corporate_org_eid, prop, *, action_kind, status):
    property_id = _property_id(prop)
    if not property_id:
        return None
    modifier_by_action = {
        "security_upgrade": {"screening_bias": 0.55, "manifest_bias": 0.18, "paperwork_bias": 0.08},
        "buyout_offer": {"screening_bias": 0.2, "manifest_bias": 0.16, "handoff_bias": 0.08},
        "branch_opening": {"screening_bias": 0.24, "manifest_bias": 0.22, "handoff_bias": 0.1},
        "franchise_offer": {"manifest_bias": 0.2, "paperwork_bias": 0.12, "handoff_bias": 0.08},
        "service_exclusivity": {"paperwork_bias": 0.18, "manifest_bias": 0.18},
        "supply_pressure": {"manifest_bias": 0.14, "dispatch_bias": 0.08},
        "staff_poaching": {"handoff_bias": 0.16, "paperwork_bias": 0.1},
        "pricing_pressure": {"paperwork_bias": 0.14},
    }
    modifiers = modifier_by_action.get(action_kind, {"paperwork_bias": 0.08})
    label = "Corporate security posture" if action_kind == "security_upgrade" else "Corporate expansion posture"
    summary = "A corporate push has made the site more standardized and visibly managed."
    if status == "resisted":
        summary = "A corporate push is meeting resistance, but the frontage is still carrying its pressure."
    return record_organization_practice(
        sim,
        organization_eid=corporate_org_eid,
        practice_kind="operational_pattern",
        entry_key=f"corporate_expansion:{corporate_org_eid}:{property_id}:{action_kind}",
        domain_key="corporate_expansion",
        label=label,
        summary=summary,
        source_kind="corporate_expansion",
        service_ids=property_service_ids(prop),
        target_scope="property",
        target_property_id=property_id,
        target_field_domains=property_field_domains(prop),
        effect_modifiers=modifiers,
        tags=("corporate_expansion", action_kind, status),
        priority=58 if action_kind == "security_upgrade" else 50,
    )


def apply_corporate_expansion_action(sim, corporate_org_eid, prop, *, action_kind=None, visible=True):
    """Apply one bounded corporate expansion/pressure action to a target property."""

    if not _is_corporate_organization(sim, corporate_org_eid):
        return {"ok": False, "reason": "not_corporate"}
    target_read = corporate_target_read(sim, corporate_org_eid, prop)
    if not target_read.get("valid"):
        return {"ok": False, "reason": target_read.get("reason", "invalid_target"), "target": target_read}
    if not action_kind:
        action_kind = select_corporate_action_for_target(sim, corporate_org_eid, target_read)
    action_kind = _text(action_kind).lower().replace(" ", "_")
    if action_kind not in CORPORATE_ALL_ACTIONS:
        return {"ok": False, "reason": "invalid_action", "target": target_read}

    status = _action_status(action_kind, target_read)
    visible_cue = corporate_visible_cue(corporate_org_eid, prop, action_kind=action_kind, resistance_tags=target_read.get("resistance_tags", ()))
    local_org = property_organization_eid(sim, prop, ensure=True)
    _stamp_corporate_metadata(sim, corporate_org_eid, prop, action_kind=action_kind, status=status, target_read=target_read, visible_cue=visible_cue)

    if action_kind == "buyout_offer" and target_read.get("can_acquire"):
        link_property_organization(sim, prop, organization_eid=corporate_org_eid, link_kind="operates", primary=True, active=True)
    elif action_kind in {"branch_opening", "franchise_offer", "service_exclusivity"} and target_read.get("can_acquire"):
        link_property_organization(sim, prop, organization_eid=corporate_org_eid, link_kind="service_host", primary=False, active=True)

    if action_kind in CORPORATE_LEGAL_ACTIONS:
        _record_corporate_practice(sim, corporate_org_eid, prop, action_kind=action_kind, status=status)

    if local_org and int(local_org) != int(corporate_org_eid):
        stance = "transactional"
        if status == "resisted":
            stance = "competitive"
        if action_kind in {"fake_inspection", "intimidation", "vandalism", "arson_attempt", "gang_contract", "hostile_rumor"}:
            stance = "hostile"
        record_organization_relationship(
            sim,
            org_a_eid=corporate_org_eid,
            org_b_eid=local_org,
            stance=stance,
            confidence=0.64 if stance == "hostile" else 0.56,
            reason_tags=("corporate_expansion", action_kind, status, *tuple(target_read.get("resistance_tags", ()) or ())),
            source_event="corporate_expansion",
            anchor_property_id=_property_id(prop),
            visible=bool(visible),
            visible_cue=visible_cue,
            cooldown_ticks=240,
        )

    pressure_kind = "corporate_deniable_pressure" if action_kind in CORPORATE_DENIABLE_ACTIONS else "corporate_expansion"
    pressure = record_organization_pressure(
        sim,
        organization_eid=corporate_org_eid,
        related_org_eid=local_org if local_org and int(local_org) != int(corporate_org_eid) else None,
        pressure_kind=pressure_kind,
        stance="hostile" if action_kind in CORPORATE_DENIABLE_ACTIONS else ("competitive" if status == "resisted" else "transactional"),
        reason_tags=("corporate_expansion", action_kind, status, *tuple(target_read.get("resistance_tags", ()) or ())),
        anchor_property_id=_property_id(prop),
        visible=bool(visible),
        visible_cue=visible_cue,
        confidence=0.68 if action_kind in CORPORATE_DENIABLE_ACTIONS else 0.58,
        source_event="corporate_expansion",
    )
    action = _record_expansion_action(sim, corporate_org_eid, prop, action_kind=action_kind, status=status, target_read=target_read, visible_cue=visible_cue)
    chunk = _metadata(prop).get("chunk")
    if not isinstance(chunk, (tuple, list)) or len(chunk) < 2:
        try:
            chunk = sim.chunk_coords(int(prop.get("x", 0)), int(prop.get("y", 0)))
        except (AttributeError, TypeError, ValueError):
            chunk = None
    if isinstance(chunk, (tuple, list)) and len(chunk) >= 2:
        refresh_corporate_neighborhood_presence(
            sim,
            corporate_org_eid,
            (int(chunk[0]), int(chunk[1])),
            materialize=True,
        )
    return {
        "ok": True,
        "action": action,
        "pressure": pressure,
        "target": target_read,
        "status": status,
        "visible_cue": visible_cue,
    }


def record_corporate_org_deal(
    sim,
    corporate_org_eid,
    partner_org_eid,
    *,
    deal_kind="service_contract",
    anchor_property_id=None,
    visible=False,
):
    """Record a corporate cooperation/conflict deal through shared diplomacy."""

    if not _is_corporate_organization(sim, corporate_org_eid) or organization_profile(sim, partner_org_eid) is None:
        return None
    deal_kind = _text(deal_kind).lower().replace(" ", "_") or "service_contract"
    compatibility = organization_compatibility_read(sim, corporate_org_eid, partner_org_eid)
    shared = set(compatibility.get("shared_interests", ()) or ())
    stance = "transactional"
    if deal_kind in {"relief_optics", "member_discount", "supply_alliance"} or shared & {"supply", "customers", "service_access"}:
        stance = "transactional"
    if deal_kind in {"brand_alliance", "mutual_security"}:
        stance = "allied"
    if deal_kind in {"territory_conflict", "competitor_pressure"}:
        stance = "competitive"
    if deal_kind in {"sacred_conflict", "devotion_conflict"}:
        stance = "sacred_conflict"
    if deal_kind in {"deniable_pressure", "gang_contract"}:
        stance = "transactional"
    cue = "a corporate arrangement is visible in the way people, stock, and service habits line up"
    if stance == "competitive":
        cue = "corporate polish and local refusal are sharing the same frontage uneasily"
    elif stance == "allied":
        cue = "the corporate and local symbols look deliberately coordinated"
    elif stance == "sacred_conflict":
        cue = "corporate pressure is meeting a refusal that feels devotional instead of commercial"
    return record_organization_relationship(
        sim,
        org_a_eid=corporate_org_eid,
        org_b_eid=partner_org_eid,
        stance=stance,
        confidence=0.6,
        reason_tags=("corporate_deal", deal_kind, *tuple(compatibility.get("reason_tags", ()) or ())),
        source_event="corporate_org_deal",
        anchor_property_id=anchor_property_id,
        visible=bool(visible),
        visible_cue=cue,
        cooldown_ticks=300,
    )


def record_corporate_deniable_actor_event(
    sim,
    *,
    actor_eid,
    corporate_org_eid,
    prop,
    tactic="vandalism",
    witnessed=False,
    observer_eids=(),
):
    """Emit an ordinary actor tamper event with hidden corporate-pressure context."""

    if not isinstance(prop, dict):
        return None
    tactic = _text(tactic).lower().replace(" ", "_") or "vandalism"
    severity = {
        "fake_inspection": 18,
        "intimidation": 28,
        "vandalism": 46,
        "arson_attempt": 74,
        "gang_contract": 42,
    }.get(tactic, 36)
    prop_id = _property_id(prop)
    metadata = _metadata(prop)
    event = Event(
        "property_tamper",
        offender_eid=_safe_int(actor_eid, default=0),
        property_id=prop_id,
        property_name=_text(prop.get("name")) or _text(metadata.get("business_name")),
        x=_safe_int(prop.get("x"), default=0),
        y=_safe_int(prop.get("y"), default=0),
        z=_safe_int(prop.get("z"), default=0),
        witnessed=bool(witnessed),
        witness_count=len(tuple(observer_eids or ())) if witnessed else 0,
        witnesses=tuple(int(eid) for eid in tuple(observer_eids or ()) if _safe_int(eid, default=0) > 0),
        access_level="restricted",
        severity_score=int(severity),
        severity_label="serious_tamper" if severity >= 45 else "tamper",
        ingress_kind="corporate_deniable_pressure",
        ingress_method=tactic,
        standing_reason="none",
        deniable_motive=True,
        suspected_source_kind="corporate_pressure",
        suspected_source_organization_eid=int(corporate_org_eid),
    )
    sim.emit(event)
    return event


def corporate_pressure_for_property(sim, prop):
    if not isinstance(prop, dict):
        return ()
    property_id = _property_id(prop)
    if not property_id:
        return ()
    state = ensure_corporate_expansion_state(sim)
    rows = [
        dict(row)
        for row in state.get("actions", {}).values()
        if isinstance(row, dict) and _text(row.get("property_id")) == property_id
    ]
    rows.sort(key=lambda row: (-_safe_int(row.get("last_update_tick"), default=0), _text(row.get("action_kind"))))
    return tuple(rows)


def advance_corporate_expansion(sim, *, limit=1):
    """Let a small number of corporations advance expansion pressure."""

    state = ensure_corporate_expansion_state(sim)
    now = _tick(sim)
    advanced = []
    for corp in corporate_organization_rows(sim):
        if len(advanced) >= max(1, _safe_int(limit, default=1)):
            break
        org_eid = _safe_int(corp.get("organization_eid"), default=0)
        cooldown_key = f"corporate:{org_eid}:expansion"
        if _safe_int(state.get("cooldowns", {}).get(cooldown_key), default=0) > now:
            continue
        candidates = corporate_acquisition_candidate_properties(sim, org_eid, include_resistant=True, limit=8)
        if not candidates:
            state["cooldowns"][cooldown_key] = now + CORPORATE_EXPANSION_INTERVAL
            continue
        target = candidates[0]
        prop = getattr(sim, "properties", {}).get(target.get("property_id"))
        if not isinstance(prop, dict):
            state["cooldowns"][cooldown_key] = now + CORPORATE_EXPANSION_INTERVAL
            continue
        result = apply_corporate_expansion_action(sim, org_eid, prop, action_kind=select_corporate_action_for_target(sim, org_eid, target))
        if result.get("ok"):
            advanced.append(result)
        state["cooldowns"][cooldown_key] = now + CORPORATE_EXPANSION_INTERVAL
    return tuple(advanced)


class CorporateExpansionSystem(System):
    """Periodic, bounded corporate expansion pulse."""

    def __init__(self, sim, refresh_interval=CORPORATE_EXPANSION_INTERVAL):
        super().__init__(sim)
        self.refresh_interval = max(120, _safe_int(refresh_interval, default=CORPORATE_EXPANSION_INTERVAL))
        self._next_tick = 0

    def update(self):
        now = _tick(self.sim)
        if now < self._next_tick:
            return
        self._next_tick = now + self.refresh_interval
        advance_corporate_expansion(self.sim, limit=1)
        refresh_all_corporate_neighborhood_presence(self.sim, materialize=True)


__all__ = [
    "CorporateExpansionSystem",
    "advance_corporate_expansion",
    "apply_corporate_expansion_action",
    "corporate_acquisition_candidate_properties",
    "corporate_expansion_profile",
    "corporate_organization_rows",
    "corporate_pressure_for_property",
    "corporate_target_read",
    "ensure_corporate_expansion_state",
    "record_corporate_deniable_actor_event",
    "record_corporate_org_deal",
    "select_corporate_action_for_target",
]
