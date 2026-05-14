"""Shared dialogue, contractor, and contact-facing helpers."""

from game.components import Collider, ContactLedger, NPCSocial, Position, Vitality
from game.property_access import (
    evaluate_property_access as _evaluate_property_access,
    property_access_level as _property_access_level,
)
from game.property_runtime import (
    building_id_from_property as _building_id_from_property,
    property_covering as _property_covering,
    property_is_public as _property_is_public,
    property_linked_building_id as _property_linked_building_id,
    property_linked_property_id as _property_linked_property_id,
)
from game.system_support.entity_naming import _entity_display_name


def active_contractor_record(sim, npc_eid, *, ally_eid=None, jobs=None):
    if sim is None or npc_eid is None:
        return None
    contractors = getattr(sim, "contractors", {})
    if not isinstance(contractors, dict):
        return None
    tick = int(getattr(sim, "tick", 0))
    job_keys = None
    if jobs is not None:
        job_keys = {
            str(job).strip().lower()
            for job in (jobs if isinstance(jobs, (set, tuple, list)) else (jobs,))
            if str(job).strip()
        }
    for key, rec in contractors.items():
        try:
            same_npc = int(key) == int(npc_eid)
        except (TypeError, ValueError):
            same_npc = key == npc_eid
        if not same_npc or not isinstance(rec, dict):
            continue
        if int(rec.get("until", 0) or 0) <= tick:
            continue
        job = str(rec.get("job", "") or "").strip().lower()
        if job_keys is not None and job not in job_keys:
            continue
        if ally_eid is not None:
            rec_ally = rec.get("ally_eid", getattr(sim, "player_eid", None))
            try:
                same_ally = int(rec_ally) == int(ally_eid)
            except (TypeError, ValueError):
                same_ally = rec_ally == ally_eid
            if not same_ally:
                continue
        return rec
    return None


def contractor_order_target_from_record(rec):
    if not isinstance(rec, dict):
        return None
    target = rec.get("order_target")
    if not isinstance(target, (tuple, list)) or len(target) < 3:
        return None
    try:
        return (int(target[0]), int(target[1]), int(target[2]))
    except (TypeError, ValueError):
        return None


def first_blocking_entity_at(sim, x, y, z, exclude_eid=None):
    colliders = sim.ecs.get(Collider)
    vitalities = sim.ecs.get(Vitality)

    for other_eid in sorted(sim.tilemap.entities_at(x, y, z)):
        if other_eid == exclude_eid:
            continue
        collider = colliders.get(other_eid)
        if not collider or not collider.blocks:
            continue
        vitality = vitalities.get(other_eid)
        if vitality and vitality.downed:
            continue
        return other_eid
    return None


def dialog_backup_mark_from_state(state):
    if not isinstance(state, dict):
        return {}
    mark = state.get("backup_cursor_mark")
    if not isinstance(mark, dict):
        return {}
    try:
        x = int(mark.get("x", 0))
        y = int(mark.get("y", 0))
        z = int(mark.get("z", 0))
    except (TypeError, ValueError):
        return {}
    target_eid = mark.get("target_eid")
    if target_eid is not None:
        try:
            target_eid = int(target_eid)
        except (TypeError, ValueError):
            target_eid = None
    return {
        "x": x,
        "y": y,
        "z": z,
        "label": str(mark.get("label", "")).strip(),
        "target_eid": target_eid,
        "target_name": str(mark.get("target_name", "")).strip(),
    }


def dialog_map_marker_for_player(sim, player_eid, x, y, z):
    player_pos = sim.ecs.get(Position).get(player_eid) if sim is not None else None
    if player_pos and int(player_pos.z) == int(z):
        return f"{int(x)},{int(y)}"
    return f"{int(x)},{int(y)},z{int(z)}"


def dialog_backup_cursor_payload(sim, player_eid, npc_eid, x, y, z):
    if sim is None or player_eid is None:
        return {}
    try:
        x = int(x)
        y = int(y)
        z = int(z)
    except (TypeError, ValueError):
        return {}
    player_pos = sim.ecs.get(Position).get(player_eid)
    if not player_pos or int(player_pos.z) != int(z):
        return {}

    target_eid = first_blocking_entity_at(
        sim,
        x,
        y,
        z,
        exclude_eid=player_eid,
    )
    if target_eid in {None, npc_eid}:
        target_eid = None
    elif active_contractor_record(
        sim,
        target_eid,
        ally_eid=player_eid,
        jobs={"backup", "party"},
    ) is not None:
        target_eid = None

    target_name = _entity_display_name(sim, target_eid, title_case=True) if target_eid is not None else ""
    return {
        "x": x,
        "y": y,
        "z": z,
        "label": dialog_map_marker_for_player(sim, player_eid, x, y, z),
        "target_eid": target_eid,
        "target_name": target_name,
    }


def world_trait_claim_value(data):
    if not isinstance(data, dict):
        return ""
    value = data.get("claimed_value")
    if value in (None, ""):
        value = data.get("claimed_coat", "")
    return str(value).strip().lower()


def dialogue_guard_grace_state(sim):
    state = getattr(sim, "dialogue_guard_grace", None)
    if not isinstance(state, dict):
        state = {}
        sim.dialogue_guard_grace = state
    return state


def dialogue_guard_grace_key(npc_eid, prop_or_property_id):
    if isinstance(prop_or_property_id, dict):
        property_id = str(prop_or_property_id.get("id", "")).strip()
    else:
        property_id = str(prop_or_property_id or "").strip()
    if not property_id:
        return None
    try:
        npc_key = int(npc_eid)
    except (TypeError, ValueError):
        npc_key = npc_eid
    return (npc_key, property_id)


def dialogue_guard_grace_active(sim, npc_eid, prop_or_property_id):
    key = dialogue_guard_grace_key(npc_eid, prop_or_property_id)
    if key is None:
        return False
    state = dialogue_guard_grace_state(sim)
    entry = state.get(key)
    if not isinstance(entry, dict):
        return False
    try:
        expires_tick = int(entry.get("expires_tick", -1))
    except (TypeError, ValueError):
        expires_tick = -1
    if expires_tick < int(getattr(sim, "tick", 0)):
        state.pop(key, None)
        return False
    return True


def grant_dialogue_guard_grace(sim, npc_eid, prop_or_property_id, *, duration=18, tactic=""):
    key = dialogue_guard_grace_key(npc_eid, prop_or_property_id)
    if key is None:
        return False
    state = dialogue_guard_grace_state(sim)
    duration = max(1, int(duration))
    state[key] = {
        "expires_tick": int(getattr(sim, "tick", 0)) + duration,
        "property_id": key[1],
        "tactic": str(tactic or "").strip().lower(),
    }
    return True


def world_trait_claim_text(topic, claim_value):
    topic = str(topic or "").strip().lower()
    claim = str(claim_value or "").replace("_", " ").strip()
    if not claim:
        claim = "unknown"

    if topic == "cat_toxin_coat":
        return f"{claim} cats are poisonous."
    if topic == "contamination_taxonomy":
        return f"{claim} animals are contaminated this cycle."
    if topic == "illness_human_role":
        return f"{claim} groups are carrying an illness."
    if topic == "war_human_role":
        return f"{claim} groups are gearing for conflict."
    if topic == "blessing_taxonomy":
        return f"{claim} animals are said to be lucky this run."
    return f"{topic.replace('_', ' ')} -> {claim}."


def infrastructure_target_property(sim, prop):
    if not isinstance(prop, dict):
        return None

    linked_property_id = _property_linked_property_id(prop)
    if linked_property_id:
        target = sim.properties.get(linked_property_id)
        if target is not None:
            return target

    linked_building_id = _property_linked_building_id(prop)
    if not linked_building_id:
        return None

    for candidate in sim.properties.values():
        if str(candidate.get("kind", "")).strip().lower() != "building":
            continue
        if _building_id_from_property(candidate) == linked_building_id:
            return candidate
    return None


def property_interaction_modes(sim, prop, viewer_eid=None):
    if not isinstance(prop, dict):
        return ()

    access = _evaluate_property_access(sim, viewer_eid, prop)
    modes = []
    infrastructure_role = str(prop.get("interaction_role", "") or "").strip().lower()
    if infrastructure_role == "access_panel":
        modes.append("panel")
    elif infrastructure_role == "security_post":
        modes.append("security")

    services = [
        str(service).strip().lower()
        for service in list(prop.get("services", ()) or ())
        if str(service).strip()
    ]
    if str(prop.get("storefront_service", "") or "").strip() and access.can_use_services:
        modes.append("trade")
    if access.can_use_services:
        modes.extend(services)

    if viewer_eid is not None:
        owner_eid = prop.get("owner_eid")
        if owner_eid == viewer_eid or _property_is_public(prop) or access.standing >= 0.45:
            modes.append("inspect")

    return tuple(modes)


def property_access_summary(sim, prop, viewer_eid=None):
    access_modes = [
        mode
        for mode in property_interaction_modes(sim, prop, viewer_eid=viewer_eid)
        if mode != "inspect"
    ]
    if not access_modes:
        return ""
    return ",".join(access_modes)


def property_contact_lead(sim, prop, relation, viewer_eid=None):
    if not prop:
        return ""

    relation = str(relation or "linked").strip().lower() or "linked"
    relation_text = {
        "workplace": "they work at",
        "owner": "they own",
    }.get(relation, relation.replace("_", " "))
    name = str(prop.get("name", prop.get("id", "property"))).strip() or "property"
    access = _property_access_level(prop)
    access_modes = property_access_summary(sim, prop, viewer_eid=viewer_eid)
    if access_modes:
        return f"Lead: {relation_text} {name} ({access}; access:{access_modes})."
    return f"Lead: {relation_text} {name} ({access})."


def property_contact_benefits(prop):
    if not isinstance(prop, dict):
        return ()

    benefits = set()
    services = {
        str(service).strip().lower()
        for service in list(prop.get("services", ()) or ())
        if str(service).strip()
    }
    if str(prop.get("storefront_service", "") or "").strip():
        benefits.update({"trade_buy_discount", "trade_sell_bonus"})
    if "insurance" in services or "banking" in services:
        benefits.add("insurance_discount")

    if not _property_is_public(prop):
        benefits.add("soft_access")
    elif not benefits:
        benefits.add("known_name")

    return tuple(sorted(benefits))


def property_contact_entry(sim, viewer_eid, prop):
    if viewer_eid is None or not prop:
        return None

    ledger = sim.ecs.get(ContactLedger).get(viewer_eid)
    if not ledger:
        return None
    return ledger.property_entry(prop["id"])


def person_contact_entry(sim, viewer_eid, person_eid):
    if viewer_eid is None or person_eid is None:
        return None

    ledger = sim.ecs.get(ContactLedger).get(viewer_eid)
    if not ledger:
        return None
    return ledger.person_entry(person_eid)


def contact_benefit_labels(benefits):
    benefits = {str(bit).strip().lower() for bit in benefits if str(bit).strip()}
    labels = []
    if "trade_buy_discount" in benefits or "trade_sell_bonus" in benefits:
        labels.append("trade terms")
    if "insurance_discount" in benefits:
        labels.append("policy rates")
    if "soft_access" in benefits and ("trade terms" in labels or "policy rates" in labels):
        labels.append("soft access")
    if "soft_access" in benefits and not labels:
        labels.append("local name")
    return labels


def dialogue_lower_start(text):
    text = str(text or "").strip()
    if not text:
        return ""
    return text[:1].lower() + text[1:]


def dialogue_human_join(labels):
    cleaned = [str(label).strip() for label in tuple(labels or ()) if str(label).strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]
    if len(cleaned) == 2:
        return f"{cleaned[0]} and {cleaned[1]}"
    return ", ".join(cleaned[:-1]) + f", and {cleaned[-1]}"


def dialogue_hours_text(window):
    if not isinstance(window, (list, tuple)) or len(window) != 2:
        return ""
    try:
        start = int(window[0]) % 24
        end = int(window[1]) % 24
    except (TypeError, ValueError):
        return ""

    def _fmt(hour):
        suffix = "AM"
        display = hour % 24
        if display == 0:
            display = 12
        elif display == 12:
            suffix = "PM"
        elif display > 12:
            display -= 12
            suffix = "PM"
        return f"{display}:00 {suffix}"

    if start == end:
        return "around the clock"
    return f"{_fmt(start)} to {_fmt(end)}"


def dialogue_credential_mode_text(mode):
    mode = str(mode or "").strip().lower()
    mapping = {
        "mechanical_key": "key-controlled",
        "badge": "badge-controlled",
        "biometric": "biometric-controlled",
    }
    return mapping.get(mode, "controlled")


def dialogue_security_tier_text(tier):
    try:
        resolved = max(1, min(5, int(tier)))
    except (TypeError, ValueError):
        resolved = 1
    mapping = {
        1: "light security",
        2: "some security",
        3: "tight security",
        4: "heavy security",
        5: "serious security",
    }
    return mapping.get(resolved, "security")


def career_label(occupation, title_case=False):
    if not occupation:
        return ""

    label = str(getattr(occupation, "career", "") or "").replace("_", " ").strip()
    if not label:
        return ""
    return label.title() if title_case else label


def disguise_role_label(role_id, *, title_case=False):
    label = str(role_id or "").replace("_", " ").strip()
    if not label:
        return "unknown" if not title_case else "Unknown"
    return label.title() if title_case else label


def workplace_property(sim, occupation=None, routine=None):
    workplace = getattr(occupation, "workplace", None)
    if isinstance(workplace, dict):
        property_id = workplace.get("property_id")
        if property_id:
            prop = sim.properties.get(property_id)
            if prop:
                return prop

    work = getattr(routine, "work", None)
    if isinstance(work, (list, tuple)) and len(work) >= 3:
        prop = _property_covering(sim, int(work[0]), int(work[1]), int(work[2]))
        if prop:
            return prop

    return None


_active_contractor_record = active_contractor_record
_career_label = career_label
_contact_benefit_labels = contact_benefit_labels
_contractor_order_target_from_record = contractor_order_target_from_record
_dialog_backup_cursor_payload = dialog_backup_cursor_payload
_dialog_backup_mark_from_state = dialog_backup_mark_from_state
_dialog_map_marker_for_player = dialog_map_marker_for_player
_dialogue_credential_mode_text = dialogue_credential_mode_text
_dialogue_guard_grace_active = dialogue_guard_grace_active
_dialogue_guard_grace_key = dialogue_guard_grace_key
_dialogue_guard_grace_state = dialogue_guard_grace_state
_dialogue_hours_text = dialogue_hours_text
_dialogue_human_join = dialogue_human_join
_dialogue_lower_start = dialogue_lower_start
_dialogue_security_tier_text = dialogue_security_tier_text
_disguise_role_label = disguise_role_label
_first_blocking_entity_at = first_blocking_entity_at
_grant_dialogue_guard_grace = grant_dialogue_guard_grace
_infrastructure_target_property = infrastructure_target_property
_person_contact_entry = person_contact_entry
_property_access_summary = property_access_summary
_property_contact_benefits = property_contact_benefits
_property_contact_entry = property_contact_entry
_property_contact_lead = property_contact_lead
_workplace_property = workplace_property
_world_trait_claim_text = world_trait_claim_text
_world_trait_claim_value = world_trait_claim_value
