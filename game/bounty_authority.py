"""Identity-bound authority for posted alive-recovery work.

This module deliberately does not decide whether violence happened or whether
anyone witnessed it.  It answers the narrower civic question: did this actor
hold a live bounty credential and a matching posted assignment, and did the
specific act stay inside that assignment's limited scope?
"""

from __future__ import annotations

from game.civic_records import civic_license_is_active, civic_license_record
from game.components import SuppressionState, Vitality


BOUNTY_LICENSE_KIND = "bounty"
BOUNTY_AUTHORITY_SCOPE = (
    "locate posted target",
    "pursue posted target",
    "apply unarmed recovery force",
    "restrain downed or surrendered target",
)
BOUNTY_EXCLUDED_SCOPE = (
    "lethal force",
    "firearms against a non-threatening target",
    "explosives",
    "property entry or search",
    "force after surrender or incapacitation",
)

_STAMP_FIELDS = (
    "bounty_authority_relevant",
    "bounty_authority_authorized",
    "bounty_authority_reason",
    "bounty_action_kind",
    "bounty_license_status",
    "bounty_assignment_active",
    "bounty_opportunity_id",
    "bounty_issuer_name",
    "bounty_credential_misuse",
    "bounty_severity_mitigation",
    "bounty_severity_adjustment",
    "bounty_authority_scope",
    "bounty_authority_exclusions",
    "bounty_authority_evaluated_tick",
)


def _safe_int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


def _same_eid(left, right):
    if left is None or right is None:
        return False
    try:
        return int(left) == int(right)
    except (TypeError, ValueError):
        return str(left) == str(right)


def _active_opportunities(sim):
    traits = getattr(sim, "world_traits", None)
    state = traits.get("opportunities") if isinstance(traits, dict) else None
    active = state.get("active", ()) if isinstance(state, dict) else ()
    return tuple(row for row in tuple(active or ()) if isinstance(row, dict))


def active_bounty_assignment(sim, actor_eid, target_eid, *, include_restrained=False):
    """Return the exact active posted assignment held by ``actor_eid``."""

    if sim is None or actor_eid is None or target_eid is None:
        return None
    player_eid = getattr(sim, "player_eid", None)
    for opportunity in _active_opportunities(sim):
        if str(opportunity.get("kind", "") or "").strip().lower() != "bounty_capture":
            continue
        requirements = opportunity.get("requirements") if isinstance(opportunity.get("requirements"), dict) else {}
        if not _same_eid(requirements.get("bounty_target_eid"), target_eid):
            continue
        if bool(requirements.get("bounty_restrained")) and not include_restrained:
            continue
        assigned_eid = requirements.get("assigned_actor_eid", requirements.get("bounty_hunter_eid"))
        if assigned_eid is None and bool(requirements.get("player_accepted")):
            assigned_eid = player_eid
        if not _same_eid(assigned_eid, actor_eid):
            continue
        expire_tick = _safe_int(opportunity.get("expire_tick"), 0)
        if expire_tick > 0 and _safe_int(getattr(sim, "tick", 0), 0) >= expire_tick:
            continue
        return opportunity
    return None


def _target_is_incapacitated(sim, target_eid):
    vitality = sim.ecs.get(Vitality).get(target_eid) if sim is not None else None
    if vitality is not None and bool(getattr(vitality, "downed", False)):
        return True
    suppression = sim.ecs.get(SuppressionState).get(target_eid) if sim is not None else None
    return bool(suppression is not None and getattr(suppression, "surrendered", False))


def bounty_action_kind(action="", context=""):
    action = str(action or "").strip().lower()
    context = str(context or "").strip().lower()
    if context == "homicide" or action in {"homicide", "kill", "execute", "lethal_force"}:
        return "lethal_force"
    if context == "explosive_discharge" or action in {"explosion", "explosive_force"}:
        return "explosive_force"
    if context == "armed_assault" or action in {"fire_weapon", "shoot", "armed_force"}:
        return "armed_force"
    if context == "melee_assault" or action in {"melee_attack", "melee_force"}:
        return "melee_force"
    if context == "unarmed_assault" or action in {"unarmed_attack", "unarmed_force"}:
        return "unarmed_force"
    aliases = {
        "locate": "locate",
        "pursue": "pursue",
        "tail": "pursue",
        "question": "question",
        "restrain": "restrain",
        "search_property": "search_property",
    }
    return aliases.get(action, action or context or "unknown")


def bounty_authority_from_stamped_data(data):
    """Recover an action-time authority read carried by an incident/event."""

    if not isinstance(data, dict) or "bounty_authority_evaluated_tick" not in data:
        return None
    return {field: data.get(field) for field in _STAMP_FIELDS if field in data}


def bounty_action_authority(sim, actor_eid, target_eid, *, action="", context=""):
    """Classify one recovery act without granting general police powers."""

    now = _safe_int(getattr(sim, "tick", 0), 0)
    action_kind = bounty_action_kind(action, context)
    assignment = active_bounty_assignment(
        sim,
        actor_eid,
        target_eid,
        include_restrained=action_kind == "restrain",
    )
    license_record = civic_license_record(sim, actor_eid, BOUNTY_LICENSE_KIND)
    license_status = str((license_record or {}).get("status", "unlicensed") or "unlicensed").strip().lower()
    license_active = civic_license_is_active(sim, actor_eid, BOUNTY_LICENSE_KIND)
    relevant = isinstance(assignment, dict)
    incapacitated = _target_is_incapacitated(sim, target_eid)
    opportunity_id = _safe_int((assignment or {}).get("id"), 0)
    issuer = (assignment or {}).get("issuer") if isinstance((assignment or {}).get("issuer"), dict) else {}
    base = {
        "bounty_authority_relevant": bool(relevant),
        "bounty_authority_authorized": False,
        "bounty_authority_reason": "no matching posted recovery assignment",
        "bounty_action_kind": action_kind,
        "bounty_license_status": license_status,
        "bounty_assignment_active": bool(relevant),
        "bounty_opportunity_id": opportunity_id,
        "bounty_issuer_name": str(issuer.get("property_name", "") or "").strip(),
        "bounty_credential_misuse": False,
        "bounty_severity_mitigation": 0.0,
        "bounty_severity_adjustment": 0,
        "bounty_authority_scope": BOUNTY_AUTHORITY_SCOPE,
        "bounty_authority_exclusions": BOUNTY_EXCLUDED_SCOPE,
        "bounty_authority_evaluated_tick": now,
    }
    if not relevant:
        return base
    if not license_active:
        base.update({
            "bounty_authority_reason": f"matching posting but bounty credential is {license_status}",
            "bounty_credential_misuse": True,
            "bounty_severity_adjustment": 8,
        })
        return base
    if action_kind in {"locate", "pursue", "question"}:
        base.update({
            "bounty_authority_authorized": True,
            "bounty_authority_reason": "active credential and matching posted target",
            "bounty_severity_mitigation": 1.0,
        })
        return base
    if action_kind == "restrain":
        if incapacitated:
            base.update({
                "bounty_authority_authorized": True,
                "bounty_authority_reason": "matching posted target is downed or surrendered",
                "bounty_severity_mitigation": 1.0,
            })
        else:
            base.update({
                "bounty_authority_reason": "custodial authority begins only after the target is downed or surrendered",
                "bounty_credential_misuse": True,
                "bounty_severity_adjustment": 6,
            })
        return base
    if action_kind == "unarmed_force" and not incapacitated:
        base.update({
            "bounty_authority_authorized": True,
            "bounty_authority_reason": "limited unarmed force against the matching live posted target",
            "bounty_severity_mitigation": 1.0,
        })
        return base

    reason = {
        "unarmed_force": "force continued after the target was downed or surrendered",
        "melee_force": "the credential does not authorize weapon force against a non-threatening target",
        "armed_force": "the credential does not authorize shooting a non-threatening target",
        "explosive_force": "the credential never authorizes explosives",
        "lethal_force": "the credential never authorizes killing",
        "search_property": "the credential does not grant property entry or search authority",
    }.get(action_kind, "the act falls outside the posted recovery authority")
    base.update({
        "bounty_authority_reason": reason,
        "bounty_credential_misuse": True,
        "bounty_severity_adjustment": 12 if action_kind in {"explosive_force", "lethal_force"} else 8,
    })
    return base


def stamp_bounty_authority(sim, data, *, offender_eid=None, target_eid=None):
    """Attach an action-time authority snapshot to an offense payload."""

    if not isinstance(data, dict):
        return data
    offender_eid = offender_eid if offender_eid is not None else data.get("offender_eid", data.get("eid"))
    target_eid = target_eid if target_eid is not None else data.get("target_eid", data.get("victim_eid"))
    read = bounty_action_authority(
        sim,
        offender_eid,
        target_eid,
        action=data.get("action"),
        context=data.get("context"),
    )
    data.update(read)
    return data


__all__ = [
    "BOUNTY_AUTHORITY_SCOPE",
    "BOUNTY_EXCLUDED_SCOPE",
    "BOUNTY_LICENSE_KIND",
    "active_bounty_assignment",
    "bounty_action_authority",
    "bounty_action_kind",
    "bounty_authority_from_stamped_data",
    "stamp_bounty_authority",
]
