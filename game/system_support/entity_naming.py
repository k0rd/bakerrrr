"""Shared entity display-label helpers."""

from game.components import AI, ContactLedger, CreatureIdentity, Occupation
from game.system_support.actor_role_runtime import actor_presentation_role


_ARTICLE_SKIP_WORDS = {"a", "an", "the", "some", "someone", "somebody", "you"}
_AN_LETTER_SOUNDS = set("AEFHILMNORSX")


def _clean_display_label(value):
    return str(value or "").replace("_", " ").strip()


def _looks_like_specific_person_name(label):
    parts = [part for part in str(label or "").replace("#", " ").split() if part]
    if len(parts) < 2:
        return False
    proper = 0
    for part in parts[:3]:
        token = part.strip(".,:;()[]{}")
        if not token:
            continue
        if token[:1].isupper() and token[1:].islower() and "-" not in token:
            proper += 1
    return proper >= 2


def _indefinite_article_for(label):
    text = _clean_display_label(label)
    if not text:
        return "a"
    first = text.split()[0].strip("\"'([{")
    if not first:
        return "a"
    first_upper = first[:1].upper()
    if len(first) == 1 and first_upper in _AN_LETTER_SOUNDS:
        return "an"
    if len(first) >= 2 and first[1:2] in {"-", "."} and first_upper in _AN_LETTER_SOUNDS:
        return "an"
    lowered = first.lower()
    if lowered.startswith(("honest", "hour", "heir")):
        return "an"
    if lowered.startswith(("uni", "use", "user", "u-")):
        return "a"
    return "an" if lowered[:1] in {"a", "e", "i", "o"} else "a"


def _display_label_phrase(label, *, article=True):
    label = _clean_display_label(label)
    if not label:
        return ""
    first_word = label.split()[0].strip("\"'([{").lower()
    if not article or first_word in _ARTICLE_SKIP_WORDS or _looks_like_specific_person_name(label):
        return label
    return f"{_indefinite_article_for(label)} {label}"


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


def _entity_display_phrase(sim, eid, *, title_case=False, article=True, fallback="entity"):
    identities = sim.ecs.get(CreatureIdentity) if getattr(sim, "ecs", None) is not None else None
    identity = identities.get(eid) if identities is not None else None
    label = _entity_display_name(sim, eid, title_case=title_case)
    if not label or str(label).strip().lower() in {"entity", "someone"}:
        label = fallback
    if identity is not None and _clean_display_label(getattr(identity, "personal_name", "")):
        return _clean_display_label(label)
    return _display_label_phrase(label, article=article)


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
    occupations = sim.ecs.get(Occupation) if getattr(sim, "ecs", None) is not None else None
    identity = identities.get(eid) if identities is not None else None
    ai = ais.get(eid) if ais is not None else None
    occupation = occupations.get(eid) if occupations is not None else None

    role = actor_presentation_role(sim, eid, ai=ai, occupation=occupation).replace("_", " ").strip()
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
