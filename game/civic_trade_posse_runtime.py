"""Lightweight civic, trade, posse, and revenge organization helpers.

This is the last organization-expansion packet: lighter groups can create
visible pressure, practices, watchlists, and diplomacy without becoming another
territory engine.  Posses/revenge squads are temporary and target-focused.
"""

from __future__ import annotations

import random

from engine.systems import System
from game.components import OrganizationProfile
from game.organizations import (
    ensure_organization,
    ensure_organization_diplomacy_state,
    link_property_organization,
    organization_compatibility_read,
    organization_policy_snapshot,
    organization_profile,
    property_field_domains,
    property_org_links,
    property_service_ids,
    record_organization_practice,
    record_organization_pressure,
    record_organization_relationship,
    record_organization_vocabulary,
    record_organization_watchlist,
)
from game.property_runtime import property_is_storefront


CIVIC_TRADE_POSSE_INTERVAL = 720
CIVIC_TRADE_POSSE_TTL = 18 * 600
POSSE_DEFAULT_TTL = 36 * 600

LIGHTWEIGHT_FAMILIES = frozenset(
    (
        "labor_union",
        "trade_guild",
        "civic_security",
        "municipal",
        "community",
        "posse",
        "revenge_squad",
    )
)
LIGHTWEIGHT_KINDS = frozenset(("trade_group", "civic", "community", "posse", "revenge_squad"))
TRADE_ACTIONS = frozenset(
    (
        "broker_endorsement",
        "member_discount",
        "supplier_coordination",
        "blacklist",
        "pressure_resistance",
        "mediation",
    )
)
CIVIC_ACTIONS = frozenset(
    (
        "relief_table",
        "shelter_warning",
        "repair_relief",
        "watchful_warning",
        "rumor_cooling",
        "pressure_opposition",
    )
)
POSSE_ACTIONS = frozenset(("posse_watch", "revenge_focus", "target_warning", "temporary_blacklist", "stand_down"))


def _text(value):
    return str(value or "").strip()


def _key(value):
    return _text(value).lower().replace(" ", "_")


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _tick(sim):
    return _safe_int(getattr(sim, "tick", 0), default=0)


def _slug(value):
    cleaned = []
    for char in _text(value).lower():
        if char.isalnum():
            cleaned.append(char)
        elif cleaned and cleaned[-1] != "_":
            cleaned.append("_")
    return "".join(cleaned).strip("_")


def _property_id(prop):
    return _text(prop.get("id")) if isinstance(prop, dict) else ""


def _metadata(prop):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        prop["metadata"] = metadata
    return metadata


def _profile_tags(profile):
    return {
        _key(tag)
        for tag in tuple(getattr(profile, "tags", ()) or ())
        if _key(tag)
    }


def _state(sim):
    traits = getattr(sim, "world_traits", None)
    if not isinstance(traits, dict):
        sim.world_traits = {}
        traits = sim.world_traits
    state = traits.get("civic_trade_posse")
    if not isinstance(state, dict):
        state = {}
        traits["civic_trade_posse"] = state
    for key in ("actions", "posses", "cooldowns"):
        if not isinstance(state.get(key), dict):
            state[key] = {}
    state["next_action_id"] = max(1, _safe_int(state.get("next_action_id"), default=1))
    ensure_organization_diplomacy_state(sim)
    return state


def ensure_civic_trade_posse_state(sim):
    """Return save-compatible lightweight organization action state."""

    state = _state(sim)
    now = _tick(sim)
    for key, row in tuple(state.get("actions", {}).items()):
        if not isinstance(row, dict):
            state["actions"].pop(key, None)
            continue
        expires = _safe_int(row.get("expires_tick"), default=0)
        if expires and expires < now:
            state["actions"].pop(key, None)
    for key, row in tuple(state.get("posses", {}).items()):
        if not isinstance(row, dict):
            state["posses"].pop(key, None)
            continue
        expires = _safe_int(row.get("expires_tick"), default=0)
        if expires and expires < now:
            row["active"] = False
            row["resolved_reason"] = row.get("resolved_reason") or "expired"
            state["posses"][key] = row
    for key, value in tuple(state.get("cooldowns", {}).items()):
        if _safe_int(value, default=0) <= now:
            state["cooldowns"].pop(key, None)
    return state


def _org_family(sim, organization_eid):
    profile = organization_profile(sim, organization_eid)
    if profile is None:
        return ""
    policy = organization_policy_snapshot(sim, organization_eid=organization_eid) or {}
    family = _key(policy.get("family"))
    kind = _key(getattr(profile, "kind", ""))
    tags = _profile_tags(profile)
    if family in LIGHTWEIGHT_FAMILIES:
        return family
    if kind in {"posse", "revenge_squad"}:
        return kind
    if kind == "trade_group" or tags & {"trade_group", "trade_guild", "guild", "labor_union", "union"}:
        return "trade_guild" if "trade_guild" in tags or "guild" in tags else "labor_union"
    if kind in {"civic", "community"} or tags & {"civic", "community", "municipal", "civic_security", "relief"}:
        return "civic_security" if "civic_security" in tags else "community"
    return ""


def _is_lightweight_org(sim, organization_eid):
    profile = organization_profile(sim, organization_eid)
    if profile is None:
        return False
    kind = _key(getattr(profile, "kind", ""))
    return kind in LIGHTWEIGHT_KINDS or _org_family(sim, organization_eid) in LIGHTWEIGHT_FAMILIES


def lightweight_organization_rows(sim, *, include_posses=True):
    """Return civic/trade/posse org refs that can use this lighter runtime."""

    rows = []
    for organization_eid, _component in tuple(getattr(sim, "ecs").get(OrganizationProfile).items()):
        if not _is_lightweight_org(sim, organization_eid):
            continue
        family = _org_family(sim, organization_eid)
        if not include_posses and family in {"posse", "revenge_squad"}:
            continue
        profile = organization_profile(sim, organization_eid)
        policy = organization_policy_snapshot(sim, organization_eid=organization_eid) or {}
        rows.append(
            {
                "organization_eid": int(organization_eid),
                "organization_key": _text(getattr(profile, "key", "")),
                "organization_name": _text(getattr(profile, "name", "")) or "local organization",
                "organization_kind": _text(getattr(profile, "kind", "")) or "other",
                "family": family or _text(policy.get("family")) or "other",
                "tags": tuple(sorted(_profile_tags(profile))),
            }
        )
    rows.sort(key=lambda row: (_text(row.get("organization_name")).lower(), row.get("organization_eid", 0)))
    return tuple(rows)


def lightweight_org_profile(sim, organization_eid):
    profile = organization_profile(sim, organization_eid)
    if profile is None:
        return {}
    family = _org_family(sim, organization_eid)
    tags = _profile_tags(profile)
    emphasis = "local"
    if family in {"trade_guild", "labor_union"}:
        emphasis = "trade"
    elif family in {"civic_security", "municipal", "community"}:
        emphasis = "civic"
    elif family in {"posse", "revenge_squad"}:
        emphasis = "posse"
    return {
        "organization_eid": int(organization_eid),
        "organization_name": _text(getattr(profile, "name", "")) or "local organization",
        "organization_key": _text(getattr(profile, "key", "")),
        "organization_kind": _text(getattr(profile, "kind", "")) or "other",
        "family": family,
        "emphasis": emphasis,
        "tags": tuple(sorted(tags)),
    }


def _action_defaults(sim, organization_eid, action_kind):
    profile = lightweight_org_profile(sim, organization_eid)
    family = profile.get("family")
    action_kind = _key(action_kind)
    if not action_kind:
        if family in {"trade_guild", "labor_union"}:
            action_kind = "broker_endorsement"
        elif family in {"posse", "revenge_squad"}:
            action_kind = "posse_watch"
        else:
            action_kind = "relief_table"

    trade = {
        "broker_endorsement": ("transactional", "trade_brokerage", "Brokered Standard", "notices and counter habits point to a brokered trade standard"),
        "member_discount": ("transactional", "trade_member_terms", "Member Terms", "regulars are getting careful member-rate language without much theatre"),
        "supplier_coordination": ("allied", "trade_supply_coordination", "Supplier Coordination", "deliveries and manifests are being coordinated in the open"),
        "blacklist": ("hostile", "trade_blacklist", "Trade Blacklist", "clerks and carriers are repeating the same refusal script"),
        "pressure_resistance": ("competitive", "trade_pressure_resistance", "Trade Resistance", "small operators are comparing notes against outside pressure"),
        "mediation": ("transactional", "trade_mediation", "Trade Mediation", "the storefront feels like somebody brokered a compromise"),
    }
    civic = {
        "relief_table": ("allied", "civic_relief", "Relief Table", "folding tables, lists, and quiet offers of help are visible"),
        "shelter_warning": ("neutral", "civic_shelter_warning", "Shelter Warning", "people are warning each other where it is safer to wait"),
        "repair_relief": ("allied", "civic_repair_relief", "Repair Relief", "tools and patient civic help are gathered around the frontage"),
        "watchful_warning": ("competitive", "civic_watchful_warning", "Watchful Block", "the block is not police, but it is paying attention"),
        "rumor_cooling": ("neutral", "civic_rumor_cooling", "Rumor Cooling", "calmer voices are trying to keep the block from boiling over"),
        "pressure_opposition": ("competitive", "civic_pressure_opposition", "Civic Opposition", "neighbors are making outside pressure harder to hide"),
    }
    posse = {
        "posse_watch": ("hostile", "posse_watch", "Temporary Posse", "watchful locals are measuring one target instead of the whole block"),
        "revenge_focus": ("hostile", "revenge_focus", "Revenge Focus", "the talk has narrowed around old harm and a specific person"),
        "target_warning": ("competitive", "posse_target_warning", "Target Warning", "warnings are being passed hand to hand, not broadcast"),
        "temporary_blacklist": ("hostile", "posse_blacklist", "Temporary Blacklist", "doors and faces close in the same direction for one person"),
        "stand_down": ("neutral", "posse_stand_down", "Posse Standing Down", "the temporary watch is losing its grip on the street"),
    }

    if action_kind in trade:
        stance, pressure_kind, label, cue = trade[action_kind]
        domain = "trade_group"
    elif action_kind in civic:
        stance, pressure_kind, label, cue = civic[action_kind]
        domain = "civic_org"
    else:
        if action_kind not in posse:
            action_kind = "posse_watch"
        stance, pressure_kind, label, cue = posse[action_kind]
        domain = "incident_posse"
    return {
        "action_kind": action_kind,
        "stance": stance,
        "pressure_kind": pressure_kind,
        "label": label,
        "visible_cue": cue,
        "domain_key": domain,
    }


def _anchor_for_action(prop, subject_eid=None):
    property_id = _property_id(prop)
    if property_id:
        return {"anchor_property_id": property_id}
    subject_eid = _safe_int(subject_eid, default=0)
    if subject_eid > 0:
        return {"anchor_actor_eid": int(subject_eid)}
    return {}


def _property_action_tags(prop):
    tags = []
    if isinstance(prop, dict):
        tags.extend(f"service:{service_id}" for service_id in property_service_ids(prop))
        tags.extend(f"field:{domain}" for domain in property_field_domains(prop))
        if property_is_storefront(prop):
            tags.append("storefront")
    return tuple(tags)


def apply_lightweight_org_action(
    sim,
    organization_eid,
    prop=None,
    *,
    action_kind=None,
    subject_eid=None,
    partner_org_eid=None,
    visible=True,
):
    """Record one anchored light-org action without changing law/price/access."""

    if not _is_lightweight_org(sim, organization_eid):
        return {"ok": False, "reason": "not_lightweight_org"}
    subject_eid = _safe_int(subject_eid, default=0) or None
    partner_org_eid = _safe_int(partner_org_eid, default=0) or None
    defaults = _action_defaults(sim, organization_eid, action_kind)
    action_kind = defaults["action_kind"]
    anchor = _anchor_for_action(prop, subject_eid=subject_eid)
    if not anchor:
        return {"ok": False, "reason": "no_anchor"}

    now = _tick(sim)
    state = ensure_civic_trade_posse_state(sim)
    action_id = int(state["next_action_id"])
    state["next_action_id"] = action_id + 1
    profile = lightweight_org_profile(sim, organization_eid)
    property_id = _text(anchor.get("anchor_property_id"))
    expires_tick = now + CIVIC_TRADE_POSSE_TTL
    action_key = f"light_org:{organization_eid}:{property_id or subject_eid or 0}:{action_kind}"
    tags = ("lightweight_org", profile.get("family"), action_kind, *_property_action_tags(prop))

    practice = None
    if action_kind != "stand_down":
        practice = record_organization_practice(
            sim,
            organization_eid=organization_eid,
            practice_kind="operational_pattern",
            entry_key=action_key,
            domain_key=defaults["domain_key"],
            label=defaults["label"],
            summary=defaults["visible_cue"],
            source_kind="civic_trade_posse",
            target_scope="property" if property_id else "organization",
            target_property_id=property_id or None,
            target_affiliated_org_eids=(partner_org_eid,) if partner_org_eid else None,
            tags=tags,
            priority=54,
            expires_tick=expires_tick,
        )

    vocabulary = record_organization_vocabulary(
        sim,
        organization_eid=organization_eid,
        vocabulary_kind="site_brief" if property_id else "subject_notice",
        entry_key=f"{action_key}:brief",
        topic_key=action_kind,
        label=defaults["label"],
        summary=defaults["visible_cue"],
        source_kind="civic_trade_posse",
        subject_actor_eid=subject_eid,
        target_scope="property" if property_id else "organization",
        target_property_id=property_id or None,
        target_affiliated_org_eids=(partner_org_eid,) if partner_org_eid else None,
        tags=tags,
        priority=55,
        expires_tick=expires_tick,
    )

    pressure = record_organization_pressure(
        sim,
        organization_eid=organization_eid,
        related_org_eid=partner_org_eid,
        pressure_kind=defaults["pressure_kind"],
        stance=defaults["stance"],
        reason_tags=tags,
        visible=bool(visible),
        visible_cue=defaults["visible_cue"],
        confidence=0.56 if defaults["domain_key"] != "incident_posse" else 0.68,
        source_event="civic_trade_posse",
        expires_tick=expires_tick,
        pressure_key=f"{action_key}:pressure",
        **anchor,
    )

    watchlist = None
    if subject_eid and action_kind in {"blacklist", "temporary_blacklist", "posse_watch", "revenge_focus", "target_warning"}:
        watch_action = "deny_service" if action_kind in {"blacklist", "temporary_blacklist"} else "watch"
        watchlist = record_organization_watchlist(
            sim,
            organization_eid=organization_eid,
            subject_eid=subject_eid,
            action=watch_action,
            reason=action_kind,
            source_kind="civic_trade_posse",
            target_scope="property" if property_id else "organization",
            target_property_id=property_id or None,
            tags=tags,
            priority=66 if defaults["domain_key"] == "incident_posse" else 58,
            expires_tick=expires_tick,
        )

    if partner_org_eid and organization_profile(sim, partner_org_eid) is not None:
        record_lightweight_org_deal(
            sim,
            organization_eid,
            partner_org_eid,
            deal_kind=action_kind,
            anchor_property_id=property_id or None,
            visible=bool(visible),
        )

    state["actions"][str(action_id)] = {
        "action_id": action_id,
        "organization_eid": int(organization_eid),
        "organization_family": profile.get("family"),
        "action_kind": action_kind,
        "property_id": property_id,
        "subject_eid": subject_eid,
        "partner_org_eid": partner_org_eid,
        "visible": bool(visible),
        "visible_cue": defaults["visible_cue"],
        "created_tick": now,
        "expires_tick": expires_tick,
    }

    if action_kind == "stand_down":
        _deactivate_posse_rows_for_org(sim, organization_eid, reason="stand_down")

    return {
        "ok": True,
        "action_id": action_id,
        "action_kind": action_kind,
        "organization_eid": int(organization_eid),
        "pressure": pressure,
        "practice": practice,
        "vocabulary": vocabulary,
        "watchlist": watchlist,
    }


def record_trade_group_action(sim, trade_org_eid, prop, *, action_kind="broker_endorsement", subject_eid=None, partner_org_eid=None, visible=True):
    action_kind = _key(action_kind) or "broker_endorsement"
    if action_kind not in TRADE_ACTIONS:
        action_kind = "broker_endorsement"
    return apply_lightweight_org_action(
        sim,
        trade_org_eid,
        prop,
        action_kind=action_kind,
        subject_eid=subject_eid,
        partner_org_eid=partner_org_eid,
        visible=visible,
    )


def record_civic_org_action(sim, civic_org_eid, prop, *, action_kind="relief_table", subject_eid=None, partner_org_eid=None, visible=True):
    action_kind = _key(action_kind) or "relief_table"
    if action_kind not in CIVIC_ACTIONS:
        action_kind = "relief_table"
    return apply_lightweight_org_action(
        sim,
        civic_org_eid,
        prop,
        action_kind=action_kind,
        subject_eid=subject_eid,
        partner_org_eid=partner_org_eid,
        visible=visible,
    )


def record_posse_action(sim, posse_org_eid, *, prop=None, action_kind="posse_watch", subject_eid=None, visible=True):
    action_kind = _key(action_kind) or "posse_watch"
    if action_kind not in POSSE_ACTIONS:
        action_kind = "posse_watch"
    return apply_lightweight_org_action(
        sim,
        posse_org_eid,
        prop,
        action_kind=action_kind,
        subject_eid=subject_eid,
        visible=visible,
    )


def _deal_stance(deal_kind, compatibility):
    deal_kind = _key(deal_kind)
    shared = set((compatibility or {}).get("shared_interests", ()) or ())
    if deal_kind in {"mutual_aid", "endorsement", "cooperative_relief", "truce"}:
        return "allied"
    if deal_kind in {"boycott", "pressure_resistance", "blacklist", "territory_concern"}:
        return "competitive"
    if deal_kind in {"retaliation", "revenge_target", "violent_feud"}:
        return "hostile"
    if deal_kind in {"sacred_conflict", "devotion_conflict"}:
        return "sacred_conflict"
    if shared & {"relief", "service_access", "labor", "supply", "reputation"}:
        return "transactional"
    return "transactional"


def record_lightweight_org_deal(
    sim,
    org_eid,
    partner_org_eid,
    *,
    deal_kind="local_arrangement",
    anchor_property_id=None,
    visible=False,
):
    if not _is_lightweight_org(sim, org_eid) or organization_profile(sim, partner_org_eid) is None:
        return None
    deal_kind = _key(deal_kind) or "local_arrangement"
    compatibility = organization_compatibility_read(sim, org_eid, partner_org_eid)
    stance = _deal_stance(deal_kind, compatibility)
    cue = "the local arrangement is visible in the way people hand off work and warnings"
    if stance == "allied":
        cue = "the local groups look coordinated without needing a sign to say so"
    elif stance == "competitive":
        cue = "notices, refusals, and careful conversations are pushing back against another organization"
    elif stance == "hostile":
        cue = "the temporary pressure has a target and a bad memory behind it"
    elif stance == "sacred_conflict":
        cue = "ordinary local business is snagging on something people treat as sacred"
    return record_organization_relationship(
        sim,
        org_a_eid=org_eid,
        org_b_eid=partner_org_eid,
        stance=stance,
        confidence=0.58,
        reason_tags=("lightweight_org", deal_kind, *tuple(compatibility.get("reason_tags", ()) or ())),
        source_event="lightweight_org_deal",
        anchor_property_id=anchor_property_id,
        visible=bool(visible),
        visible_cue=cue,
        cooldown_ticks=300,
    )


def create_incident_posse(
    sim,
    *,
    source_incident_id,
    target_eid,
    anchor_property_id=None,
    revenge=False,
    organization_key=None,
    organization_name="",
    ttl_ticks=POSSE_DEFAULT_TTL,
):
    """Create a temporary incident-driven posse/revenge-squad organization."""

    target_eid = _safe_int(target_eid, default=0)
    if target_eid <= 0:
        return None
    state = ensure_civic_trade_posse_state(sim)
    kind = "revenge_squad" if revenge else "posse"
    incident_key = _slug(source_incident_id) or f"target_{target_eid}"
    organization_key = _text(organization_key) or f"{kind}:{incident_key}:{target_eid}"
    seed = getattr(sim, "seed", 0)
    rng = random.Random(f"{seed}:{organization_key}:posse")
    if not organization_name:
        prefix = rng.choice(("Front", "Back", "Door", "Block", "Quiet", "Lantern", "Rail"))
        suffix = rng.choice(("Watch", "Circle", "Line", "Hands", "Table", "Neighbors", "Witnesses"))
        organization_name = f"{prefix} {suffix}"
    org_eid = ensure_organization(
        sim,
        organization_key=organization_key,
        organization_name=organization_name,
        organization_kind=kind,
        tags=(kind, "incident_driven", "interest:revenge", "interest:protection"),
    )
    if org_eid is None:
        return None
    now = _tick(sim)
    expires_tick = now + max(60, _safe_int(ttl_ticks, default=POSSE_DEFAULT_TTL))
    posse_id = organization_key
    row = {
        "posse_id": posse_id,
        "organization_eid": int(org_eid),
        "source_incident_id": _text(source_incident_id),
        "target_eid": int(target_eid),
        "anchor_property_id": _text(anchor_property_id),
        "kind": kind,
        "active": True,
        "created_tick": now,
        "expires_tick": expires_tick,
    }
    state["posses"][posse_id] = row
    prop = getattr(sim, "properties", {}).get(_text(anchor_property_id)) if _text(anchor_property_id) else None
    record_posse_action(
        sim,
        org_eid,
        prop=prop,
        action_kind="revenge_focus" if revenge else "posse_watch",
        subject_eid=target_eid,
        visible=True,
    )
    return dict(row)


def _deactivate_posse_rows_for_org(sim, organization_eid, *, reason="resolved"):
    state = ensure_civic_trade_posse_state(sim)
    changed = []
    for key, row in tuple(state.get("posses", {}).items()):
        if _safe_int(row.get("organization_eid"), default=0) != _safe_int(organization_eid, default=0):
            continue
        row["active"] = False
        row["resolved_reason"] = reason
        row["resolved_tick"] = _tick(sim)
        state["posses"][key] = row
        changed.append(dict(row))
    return tuple(changed)


def lightweight_org_action_rows(sim, *, organization_eid=None, active_only=True):
    state = ensure_civic_trade_posse_state(sim)
    organization_eid = _safe_int(organization_eid, default=0) or None
    rows = []
    now = _tick(sim)
    for row in state.get("actions", {}).values():
        if not isinstance(row, dict):
            continue
        if organization_eid and _safe_int(row.get("organization_eid"), default=0) != organization_eid:
            continue
        active = _safe_int(row.get("expires_tick"), default=0) > now
        if active_only and not active:
            continue
        rows.append(dict(row))
    rows.sort(key=lambda row: (-_safe_int(row.get("created_tick"), default=0), _safe_int(row.get("action_id"), default=0)))
    return tuple(rows)


def incident_posse_rows(sim, *, active_only=True):
    state = ensure_civic_trade_posse_state(sim)
    rows = []
    for row in state.get("posses", {}).values():
        if not isinstance(row, dict):
            continue
        if active_only and not bool(row.get("active", True)):
            continue
        rows.append(dict(row))
    rows.sort(key=lambda row: (_text(row.get("posse_id")), _safe_int(row.get("organization_eid"), default=0)))
    return tuple(rows)


def _linked_properties_for_org(sim, organization_eid):
    rows = []
    for prop in getattr(sim, "properties", {}).values():
        if not isinstance(prop, dict):
            continue
        links = property_org_links(sim, prop, active_only=True)
        if any(_safe_int(link.get("organization_eid"), default=0) == int(organization_eid) for link in links):
            rows.append(prop)
    rows.sort(key=lambda prop: (_property_id(prop), _safe_int(prop.get("x"), default=0), _safe_int(prop.get("y"), default=0)))
    return tuple(rows)


def lightweight_org_candidate_properties(sim, organization_eid):
    profile = lightweight_org_profile(sim, organization_eid)
    family = profile.get("family")
    linked = list(_linked_properties_for_org(sim, organization_eid))
    if linked:
        return tuple(linked)
    candidates = []
    for prop in getattr(sim, "properties", {}).values():
        if not isinstance(prop, dict):
            continue
        metadata = _metadata(prop)
        if metadata.get("objective_critical") or metadata.get("quest_critical") or metadata.get("final_operation_site"):
            continue
        if family in {"trade_guild", "labor_union"} and not (property_is_storefront(prop) or property_service_ids(prop) or property_field_domains(prop)):
            continue
        if family in {"civic_security", "municipal", "community"} and _text(prop.get("kind")).lower() != "building":
            continue
        candidates.append(prop)
    candidates.sort(key=lambda prop: (_property_id(prop), _safe_int(prop.get("x"), default=0), _safe_int(prop.get("y"), default=0)))
    return tuple(candidates)


def select_lightweight_org_action(sim, organization_eid, prop=None):
    profile = lightweight_org_profile(sim, organization_eid)
    family = profile.get("family")
    tags = set(profile.get("tags", ()) or ())
    seed = f"{getattr(sim, 'seed', 0)}:{organization_eid}:{_property_id(prop)}:{_tick(sim) // CIVIC_TRADE_POSSE_INTERVAL}"
    rng = random.Random(seed)
    if family in {"trade_guild", "labor_union"}:
        choices = ["broker_endorsement", "supplier_coordination", "mediation"]
        if tags & {"resistance", "anti_corporate", "collective"}:
            choices.append("pressure_resistance")
        return rng.choice(choices)
    if family in {"posse", "revenge_squad"}:
        return "revenge_focus" if family == "revenge_squad" else "posse_watch"
    choices = ["relief_table", "shelter_warning", "repair_relief", "rumor_cooling"]
    if tags & {"watchful", "civic_security", "security"}:
        choices.append("watchful_warning")
    return rng.choice(choices)


def advance_civic_trade_posse(sim, *, limit=1):
    state = ensure_civic_trade_posse_state(sim)
    now = _tick(sim)
    advanced = []

    for posse in incident_posse_rows(sim, active_only=True):
        if len(advanced) >= int(limit):
            return tuple(advanced)
        org_eid = _safe_int(posse.get("organization_eid"), default=0)
        cooldown_key = f"posse:{org_eid}:{posse.get('target_eid')}"
        if _safe_int(state["cooldowns"].get(cooldown_key), default=0) > now:
            continue
        prop = getattr(sim, "properties", {}).get(_text(posse.get("anchor_property_id")))
        result = record_posse_action(
            sim,
            org_eid,
            prop=prop,
            action_kind="revenge_focus" if posse.get("kind") == "revenge_squad" else "posse_watch",
            subject_eid=posse.get("target_eid"),
            visible=True,
        )
        if result.get("ok"):
            advanced.append(result)
            state["cooldowns"][cooldown_key] = now + CIVIC_TRADE_POSSE_INTERVAL

    for row in lightweight_organization_rows(sim, include_posses=False):
        if len(advanced) >= int(limit):
            break
        org_eid = _safe_int(row.get("organization_eid"), default=0)
        cooldown_key = f"org:{org_eid}"
        if _safe_int(state["cooldowns"].get(cooldown_key), default=0) > now:
            continue
        candidates = lightweight_org_candidate_properties(sim, org_eid)
        if not candidates:
            continue
        prop = candidates[0]
        action = select_lightweight_org_action(sim, org_eid, prop)
        result = apply_lightweight_org_action(sim, org_eid, prop, action_kind=action, visible=True)
        if result.get("ok"):
            advanced.append(result)
            state["cooldowns"][cooldown_key] = now + CIVIC_TRADE_POSSE_INTERVAL
    return tuple(advanced)


class CivicTradePosseSystem(System):
    """Slow, bounded pulse for lighter-weight organizations."""

    def __init__(self, sim, refresh_interval=CIVIC_TRADE_POSSE_INTERVAL):
        super().__init__(sim)
        self.refresh_interval = max(120, _safe_int(refresh_interval, default=CIVIC_TRADE_POSSE_INTERVAL))
        self._next_tick = 0

    def update(self):
        now = _tick(self.sim)
        if now < self._next_tick:
            return
        self._next_tick = now + self.refresh_interval
        advance_civic_trade_posse(self.sim, limit=1)


__all__ = [
    "CivicTradePosseSystem",
    "advance_civic_trade_posse",
    "apply_lightweight_org_action",
    "create_incident_posse",
    "ensure_civic_trade_posse_state",
    "incident_posse_rows",
    "lightweight_org_action_rows",
    "lightweight_org_candidate_properties",
    "lightweight_org_profile",
    "lightweight_organization_rows",
    "record_civic_org_action",
    "record_lightweight_org_deal",
    "record_posse_action",
    "record_trade_group_action",
    "select_lightweight_org_action",
]
