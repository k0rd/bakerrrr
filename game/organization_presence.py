"""Player-facing organization presence presentation helpers."""

from __future__ import annotations

from game.organizations import (
    actor_org_memberships,
    organization_policy_snapshot,
    property_org_links,
)


COLLECTIVE_FAMILIES = {"labor_union", "trade_guild"}
CRIMINAL_FAMILIES = {"street_gang", "criminal_network", "criminal"}


def _text(value):
    return str(value or "").strip()


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _policy(sim, organization_eid):
    organization_eid = _safe_int(organization_eid, default=0)
    if organization_eid <= 0:
        return {}
    snapshot = organization_policy_snapshot(sim, organization_eid=organization_eid)
    return snapshot if isinstance(snapshot, dict) else {}


def _presence_label(*, link_kind="", family="", primary=False):
    link_kind = _text(link_kind).lower()
    family = _text(family).lower()
    if primary or link_kind == "operates":
        if family == "corporate":
            return "corp"
        return "operator"
    if link_kind == "territory":
        return "territory"
    if link_kind == "safehouse":
        return "safehouse"
    if link_kind == "meeting_place":
        return "meeting"
    if link_kind == "service_host":
        if family in COLLECTIVE_FAMILIES:
            return "collective"
        return "service host"
    if family == "corporate":
        return "corp"
    if family in COLLECTIVE_FAMILIES:
        return "collective"
    if family in CRIMINAL_FAMILIES:
        return "crew"
    return link_kind.replace("_", " ") or "org"


def property_org_presence_rows(sim, prop, *, active_only=True, include_primary=True):
    """Return compact, current organization presence rows for a property."""

    rows = []
    seen = set()
    for link in property_org_links(sim, prop, active_only=active_only):
        organization_eid = _safe_int(link.get("organization_eid"), default=0)
        if organization_eid <= 0:
            continue
        primary = bool(link.get("primary", False))
        link_kind = _text(link.get("link_kind")).lower()
        if not include_primary and (primary or link_kind == "operates"):
            continue
        policy = _policy(sim, organization_eid)
        family = _text(policy.get("family")).lower()
        name = _text(link.get("organization_name")) or _text(policy.get("organization_name"))
        if not name:
            continue
        key = (organization_eid, link_kind, primary)
        if key in seen:
            continue
        seen.add(key)
        root_name = _text(policy.get("root_organization_name"))
        display_name = root_name if family == "corporate" and root_name and root_name.lower() != name.lower() else name
        rows.append({
            "organization_eid": organization_eid,
            "organization_key": _text(link.get("organization_key")) or _text(policy.get("organization_key")),
            "organization_name": name,
            "display_name": display_name,
            "organization_kind": _text(link.get("organization_kind")) or _text(policy.get("organization_kind")),
            "organization_family": family,
            "root_organization_name": root_name,
            "link_kind": link_kind,
            "primary": primary,
            "label": _presence_label(link_kind=link_kind, family=family, primary=primary),
        })
    return tuple(rows)


def actor_org_presence_rows(sim, actor_eid, *, active_only=True, include_primary=True):
    """Return compact, current organization presence rows for an actor."""

    rows = []
    for membership in actor_org_memberships(sim, actor_eid, active_only=active_only):
        organization_eid = _safe_int(membership.get("organization_eid"), default=0)
        if organization_eid <= 0:
            continue
        primary = bool(membership.get("primary", False))
        if not include_primary and primary:
            continue
        policy = _policy(sim, organization_eid)
        family = _text(policy.get("family")).lower()
        name = _text(membership.get("organization_name")) or _text(policy.get("organization_name"))
        if not name:
            continue
        title = _text(membership.get("title")) or _text(membership.get("role"))
        root_name = _text(policy.get("root_organization_name"))
        display_name = root_name if family == "corporate" and root_name and root_name.lower() != name.lower() else name
        rows.append({
            "organization_eid": organization_eid,
            "organization_key": _text(membership.get("organization_key")) or _text(policy.get("organization_key")),
            "organization_name": name,
            "display_name": display_name,
            "organization_kind": _text(membership.get("organization_kind")) or _text(policy.get("organization_kind")),
            "organization_family": family,
            "root_organization_name": root_name,
            "primary": primary,
            "membership_kind": _text(membership.get("kind")),
            "role": _text(membership.get("role")),
            "title": title,
            "label": "operator" if primary else _presence_label(family=family),
        })
    return tuple(rows)


def format_property_org_presence(sim, prop, *, include_primary=True, max_rows=3):
    parts = []
    for row in property_org_presence_rows(sim, prop, include_primary=include_primary)[: max(0, int(max_rows))]:
        label = _text(row.get("label"))
        name = _text(row.get("display_name")) or _text(row.get("organization_name"))
        if label and name:
            parts.append(f"{label}:{name}")
    return " ".join(parts)


def format_visible_property_org_presence(sim, prop, *, max_rows=3):
    secondary = format_property_org_presence(sim, prop, include_primary=False, max_rows=max_rows)
    if secondary:
        return secondary
    primary = format_property_org_presence(sim, prop, include_primary=True, max_rows=1)
    return primary if primary.startswith("corp:") else ""


def format_actor_org_presence(sim, actor_eid, *, include_primary=True, max_rows=3):
    parts = []
    for row in actor_org_presence_rows(sim, actor_eid, include_primary=include_primary)[: max(0, int(max_rows))]:
        label = _text(row.get("label"))
        name = _text(row.get("display_name")) or _text(row.get("organization_name"))
        title = _text(row.get("title"))
        if not label or not name:
            continue
        text = f"{label}:{name}"
        if title and title.lower() not in {"member", "staff", "employee"}:
            text += f"({title})"
        parts.append(text)
    return " ".join(parts)


def has_visible_property_org_presence(sim, prop):
    return bool(format_visible_property_org_presence(sim, prop))
