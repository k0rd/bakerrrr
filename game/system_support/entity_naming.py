"""Shared entity display-label helpers."""

from game.components import AI, ContactLedger, CreatureIdentity


def _entity_display_name_from_record(record):
    if not isinstance(record, dict):
        return ""
    for key in (
        "display_name",
        "personal_name",
        "common_name",
        "species",
        "role",
        "creature_type",
        "taxonomy_class",
    ):
        label = str(record.get(key, "") or "").replace("_", " ").strip()
        if label:
            return label
    return ""


def _entity_generic_display_name_from_record(record):
    if not isinstance(record, dict):
        return ""
    for key in (
        "common_name",
        "role",
        "creature_type",
        "taxonomy_class",
        "species",
    ):
        label = str(record.get(key, "") or "").replace("_", " ").strip()
        if label:
            return label
    return ""


def _entity_display_name(sim, eid, title_case=False):
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    ai = sim.ecs.get(AI).get(eid)

    if identity:
        label = str(identity.display_name()).replace("_", " ").strip()
    elif ai:
        label = str(ai.role or "entity").replace("_", " ").strip()
    elif hasattr(sim, "entity_identity_record"):
        label = _entity_display_name_from_record(sim.entity_identity_record(eid))
    else:
        label = "entity"

    if not label:
        label = "entity"
    return label.title() if title_case else label


def _person_name_known_from_entry(entry):
    if not isinstance(entry, dict):
        return False
    if bool(entry.get("introduced", False)):
        return True
    benefits = {
        str(bit).strip().lower()
        for bit in tuple(entry.get("benefits", ()) or ())
        if str(bit).strip()
    }
    return "known_name" in benefits


def _viewer_knows_entity_name(sim, viewer_eid, eid):
    if sim is None or viewer_eid is None or eid is None:
        return False
    try:
        if int(viewer_eid) == int(eid):
            return True
    except (TypeError, ValueError):
        if viewer_eid == eid:
            return True
    ledgers = sim.ecs.get(ContactLedger) if getattr(sim, "ecs", None) is not None else None
    ledger = ledgers.get(viewer_eid) if ledgers is not None else None
    entry = ledger.person_entry(eid) if ledger is not None else None
    return _person_name_known_from_entry(entry)


def _entity_generic_display_name(sim, eid, title_case=False):
    identities = sim.ecs.get(CreatureIdentity) if getattr(sim, "ecs", None) is not None else None
    ais = sim.ecs.get(AI) if getattr(sim, "ecs", None) is not None else None
    identity = identities.get(eid) if identities is not None else None
    ai = ais.get(eid) if ais is not None else None

    role = str(getattr(ai, "role", "") or "").replace("_", " ").strip() if ai else ""
    if identity:
        common = str(getattr(identity, "common_name", "") or "").replace("_", " ").strip()
        creature_type = str(getattr(identity, "creature_type", "") or "").replace("_", " ").strip()
        taxonomy = str(getattr(identity, "taxonomy_class", "") or "").replace("_", " ").strip()
        species = str(getattr(identity, "species", "") or "").replace("_", " ").strip()
        humanish = (
            creature_type.strip().lower() == "human"
            or taxonomy.strip().lower() == "hominid"
        )
        if humanish:
            if role and role.strip().lower() not in {"civilian", "npc", "local", "human", "person"}:
                label = role
            elif common and common.strip().lower() not in {"human", "homo sapiens"}:
                label = common
            else:
                label = "person"
        else:
            label = common or creature_type or species or taxonomy
    elif ai:
        label = role or "entity"
    elif hasattr(sim, "entity_identity_record"):
        label = _entity_generic_display_name_from_record(sim.entity_identity_record(eid))
    else:
        label = "entity"

    if not label:
        label = "entity"
    return label.title() if title_case else label


def _entity_viewer_display_name(sim, eid, *, viewer_eid=None, title_case=False):
    if _viewer_knows_entity_name(sim, viewer_eid, eid):
        return _entity_display_name(sim, eid, title_case=title_case)
    return _entity_generic_display_name(sim, eid, title_case=title_case)
