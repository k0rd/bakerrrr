"""Seed-stable underground community culture and language color.

The generated words in this module are deliberately high-context texture.  They
can decorate greetings, farewells, and ritual expression, but they must never
carry prices, directions, hazards, objectives, or other actionable facts.
"""

from __future__ import annotations

import random

from game.components import NPCSocial, OrganizationAffiliations, Position
from game.organizations import (
    assign_actor_organization,
    ensure_organization,
    link_property_organization,
    organization_eid_for_key,
    organization_profile,
)


UNDERGROUND_CULTURE_SCHEMA_VERSION = 1
UNDERGROUND_CULTURE_PARENT_KEY = "community:underground"
UNDERGROUND_CULTURE_COUNT = 2

# These are phonetic building blocks rather than authored words.  Keeping the
# corpus here makes generation reviewable and lets the run seed do the joining.
_SYLLABLES = (
    "ba", "be", "bi", "bo", "bu",
    "cha", "che", "chi", "cho",
    "da", "de", "di", "do", "du",
    "fa", "fe", "fi", "fo",
    "ga", "ge", "gi", "go", "gu",
    "ha", "he", "hi", "ho",
    "ja", "je", "ji", "jo",
    "ka", "ke", "ki", "ko", "ku",
    "la", "le", "li", "lo", "lu",
    "ma", "me", "mi", "mo", "mu",
    "na", "ne", "ni", "no", "nu",
    "pa", "pe", "pi", "po", "pu",
    "ra", "re", "ri", "ro", "ru",
    "sa", "se", "si", "so", "su",
    "sha", "she", "shi", "sho", "shu",
    "ta", "te", "ti", "to", "tu",
    "va", "ve", "vi", "vo", "vu",
    "ya", "ye", "yo", "yu",
    "za", "ze", "zi", "zo", "zu",
)
_CONCEPT_SYLLABLE_COUNTS = {
    "greeting": 2,
    "farewell": 2,
    "thanks": 2,
    "approval": 2,
    "affection": 2,
    "mocking": 2,
    "exclamation": 2,
    "ancestral": 3,
}
_BLOCKED_FRAGMENTS = (
    "chink", "cunt", "dyke", "fag", "fuck", "kike", "nigg", "rape",
    "retard", "shit", "spic",
)
_NAME_SUFFIX_PAIRS = (
    ("Kin", "Ways"),
    ("Line", "Fold"),
    ("Circle", "Steps"),
    ("House", "Road"),
)
_RITUAL_MODE_PAIRS = (
    ("heelbeat", "turnstep"),
    ("handbeat", "shoulder_sway"),
    ("stomp_circle", "cross_step"),
    ("palm_rhythm", "half_turn"),
)
_SOCIAL_EXPRESSION_CONCEPTS = {
    "conspiring": ("approval", "approval", "exclamation", "mocking"),
    "rambling": ("exclamation", "exclamation", "affection", "mocking"),
    "check_in": ("thanks", "affection", "affection", "approval"),
    "gossip": ("approval", "thanks", "mocking", "mocking"),
}
_SOCIAL_EXPRESSION_LINES = {
    "thanks": (
        "{word}. I needed the company.",
        "{word}. You showed up; that counts.",
        "{word}. Sit a minute. You made the tunnel feel shorter.",
    ),
    "approval": (
        "Clean step. {word}.",
        "{word}. You still know how to land it.",
        "There it is. {word}.",
    ),
    "affection": (
        "{word}, you old nuisance. Sit down.",
        "Come here, {word}. The ceiling did not get you yet.",
        "Still upright, {word}? Good. Stay awhile.",
    ),
    "mocking": (
        "{word}! You could lose a straight tunnel with both walls helping.",
        "{word}. All that confidence and both feet still arguing.",
        "Careful, {word}. Your shadow nearly got here first.",
    ),
    "exclamation": (
        "{word}! There you are.",
        "{word}! Nearly walked past your whole face.",
        "{word}! That woke the old pipes.",
    ),
}
_SOCIAL_EXPRESSION_SUMMARIES = {
    "thanks": "one voice softens after the other stays to talk",
    "approval": "a practiced step draws a warm answer",
    "affection": "a teasing word gets an easy shoulder-bump",
    "mocking": "a sharp-sounding word lands, then both people laugh",
    "exclamation": "a sudden call is answered without alarm",
}


def _text(value):
    return str(value or "").strip()


def _safe_slot(slot):
    try:
        return int(slot) % UNDERGROUND_CULTURE_COUNT
    except (TypeError, ValueError):
        return 0


def _word_is_safe(word):
    lowered = _text(word).lower()
    return bool(lowered) and lowered.isalpha() and not any(fragment in lowered for fragment in _BLOCKED_FRAGMENTS)


def _dialect_word(root, slot):
    """Give two neighboring dialects visibly related forms of one root."""

    root = _text(root).lower()
    if not root:
        return ""
    if _safe_slot(slot) == 0 and len(root) >= 5 and root[-1] in "aeiou":
        return root[:-1]
    return root


def _family_bundle(seed):
    rng = random.Random(f"{seed}:underground-culture-family:v{UNDERGROUND_CULTURE_SCHEMA_VERSION}")
    roots = {}
    used_forms = set()
    for concept, syllable_count in _CONCEPT_SYLLABLE_COUNTS.items():
        root = ""
        for _attempt in range(256):
            candidate = "".join(rng.choice(_SYLLABLES) for _index in range(int(syllable_count)))
            forms = {_dialect_word(candidate, slot) for slot in range(UNDERGROUND_CULTURE_COUNT)}
            if (
                len(forms) == UNDERGROUND_CULTURE_COUNT
                and all(_word_is_safe(form) for form in forms)
                and not forms.intersection(used_forms)
            ):
                root = candidate
                used_forms.update(forms)
                break
        if not root:
            # The corpus is large enough that this should be unreachable, but
            # the fallback remains deterministic if it is later heavily edited.
            root = f"naro{len(roots)}"
        roots[concept] = root

    pair_index = rng.randrange(len(_NAME_SUFFIX_PAIRS))
    ritual_index = rng.randrange(len(_RITUAL_MODE_PAIRS))
    return {
        "family_key": f"underground-family-v{UNDERGROUND_CULTURE_SCHEMA_VERSION}",
        "roots": roots,
        "name_suffixes": _NAME_SUFFIX_PAIRS[pair_index],
        "ritual_modes": _RITUAL_MODE_PAIRS[ritual_index],
    }


def underground_culture_profile(seed, slot):
    """Return one of two related culture profiles for a run seed."""

    slot = _safe_slot(slot)
    family = _family_bundle(seed)
    lexemes = {
        concept: _dialect_word(root, slot)
        for concept, root in family["roots"].items()
    }
    ancestral_word = lexemes["ancestral"]
    return {
        "schema_version": UNDERGROUND_CULTURE_SCHEMA_VERSION,
        "culture_key": f"{UNDERGROUND_CULTURE_PARENT_KEY}:{slot}",
        "culture_name": f"{ancestral_word.title()} {family['name_suffixes'][slot]}",
        "family_key": family["family_key"],
        "family_roots": dict(family["roots"]),
        "slot": slot,
        "dialect": "clipped" if slot == 0 else "open",
        "lexemes": lexemes,
        "ancestral_word": ancestral_word,
        "ritual_mode": family["ritual_modes"][slot],
    }


def underground_culture_slot(seed, chunk):
    """Choose a culture by stable two-by-two chunk neighborhood."""

    chunk = chunk if isinstance(chunk, dict) else {}
    try:
        cx = int(chunk.get("cx", 0))
        cy = int(chunk.get("cy", 0))
    except (TypeError, ValueError):
        cx, cy = 0, 0
    zone_x = cx // 2
    zone_y = cy // 2
    rng = random.Random(f"{seed}:underground-culture-zone:{zone_x}:{zone_y}")
    return int(rng.randrange(UNDERGROUND_CULTURE_COUNT))


def culture_social_expression(culture, *, seed, speaker_eid, partner_eid, relation="friend", tone="gossip", count=0):
    """Return sparse, gesture-readable culture color for a safe social beat."""

    culture = culture if isinstance(culture, dict) else {}
    lexemes = culture.get("lexemes", {})
    if not isinstance(lexemes, dict) or not _text(culture.get("culture_key")):
        return {}
    relation = _text(relation).lower() or "friend"
    tone = _text(tone).lower() or "gossip"
    rng = random.Random(
        f"{seed}:underground-culture-social:{culture.get('culture_key')}:"
        f"{speaker_eid}:{partner_eid}:{relation}:{tone}:{int(count)}"
    )
    # Culture occupies the quiet gaps in social chatter; it is not guaranteed
    # merely because two community members happen to speak.
    if rng.random() >= 0.44:
        return {}
    if relation in {"family", "partner"}:
        concepts = ("affection", "affection", "thanks", "approval")
    else:
        concepts = _SOCIAL_EXPRESSION_CONCEPTS.get(tone, _SOCIAL_EXPRESSION_CONCEPTS["gossip"])
    concept = concepts[rng.randrange(len(concepts))]
    word = _text(lexemes.get(concept)).capitalize()
    lines = _SOCIAL_EXPRESSION_LINES.get(concept, ())
    if not word or not lines:
        return {}
    quote = lines[rng.randrange(len(lines))].format(word=word)
    return {
        "topic": "culture_expression",
        "quote": quote,
        "summary": _SOCIAL_EXPRESSION_SUMMARIES[concept],
        "detail": "The word and the response belong to the same easy social rhythm.",
        "channel": "social",
        "priority": "low",
        "source_domain": "underground_culture",
        "culture_key": _text(culture.get("culture_key")),
        "culture_word": word,
        "culture_concept": concept,
        "level_local": True,
    }


def _culture_bond_count(social, culture_key):
    if social is None or not isinstance(getattr(social, "bonds", None), dict):
        return 0
    return sum(
        1 for bond in social.bonds.values()
        if isinstance(bond, dict) and _text(bond.get("shared_culture_key")) == _text(culture_key)
    )


def _upsert_culture_neighbor_bond(sim, left_eid, right_eid, culture_key, *, closeness, trust):
    socials = sim.ecs.get(NPCSocial)
    left = socials.get(int(left_eid))
    right = socials.get(int(right_eid))
    if left is None or right is None:
        return False
    changed = False
    for social, other_eid in ((left, int(right_eid)), (right, int(left_eid))):
        existing = social.bonds.get(other_eid)
        if not isinstance(existing, dict):
            social.add_bond(other_eid, kind="neighbor", closeness=closeness, trust=trust)
            existing = social.bonds.get(other_eid)
            changed = True
        else:
            old_closeness = float(existing.get("closeness", 0.0) or 0.0)
            old_trust = float(existing.get("trust", 0.0) or 0.0)
            existing["closeness"] = max(old_closeness, float(closeness))
            existing["trust"] = max(old_trust, float(trust))
            changed = bool(changed or existing["closeness"] != old_closeness or existing["trust"] != old_trust)
        if isinstance(existing, dict) and _text(existing.get("shared_culture_key")) != _text(culture_key):
            existing["shared_culture_key"] = _text(culture_key)
            existing["bond_reason"] = "underground_culture_neighbor"
            changed = True
    return changed


def seed_underground_culture_bonds(sim, actor_eid, organization_eid, culture, *, max_bonds=2, max_distance=14):
    """Attach a bounded same-level neighborhood around one native resident."""

    if sim is None or actor_eid is None or organization_eid is None:
        return ()
    culture = culture if isinstance(culture, dict) else {}
    culture_key = _text(culture.get("culture_key"))
    profile = organization_profile(sim, organization_eid)
    positions = sim.ecs.get(Position)
    socials = sim.ecs.get(NPCSocial)
    actor_pos = positions.get(int(actor_eid))
    actor_social = socials.get(int(actor_eid))
    if not culture_key or profile is None or actor_pos is None or actor_social is None:
        return ()
    actor_chunk = sim.chunk_coords(int(actor_pos.x), int(actor_pos.y))
    candidates = []
    for other_eid in tuple(getattr(profile, "member_eids", ()) or ()):
        try:
            other_eid = int(other_eid)
        except (TypeError, ValueError):
            continue
        if other_eid == int(actor_eid):
            continue
        other_pos = positions.get(other_eid)
        other_social = socials.get(other_eid)
        if other_pos is None or other_social is None or int(other_pos.z) != int(actor_pos.z):
            continue
        if sim.chunk_coords(int(other_pos.x), int(other_pos.y)) != actor_chunk:
            continue
        distance = abs(int(other_pos.x) - int(actor_pos.x)) + abs(int(other_pos.y) - int(actor_pos.y))
        if distance > int(max_distance):
            continue
        if _culture_bond_count(other_social, culture_key) >= int(max_bonds):
            continue
        candidates.append((distance, other_eid))
    candidates.sort(key=lambda row: (row[0], row[1]))

    linked = []
    for distance, other_eid in candidates:
        if len(linked) >= int(max_bonds) or _culture_bond_count(actor_social, culture_key) >= int(max_bonds):
            break
        pair = tuple(sorted((int(actor_eid), int(other_eid))))
        rng = random.Random(f"{getattr(sim, 'seed', 0)}:underground-culture-bond:{culture_key}:{pair[0]}:{pair[1]}")
        closeness = rng.uniform(0.46, 0.64) + max(0.0, (6 - int(distance)) * 0.012)
        trust = rng.uniform(0.5, 0.68) + max(0.0, (6 - int(distance)) * 0.01)
        if _upsert_culture_neighbor_bond(
            sim,
            actor_eid,
            other_eid,
            culture_key,
            closeness=min(0.7, closeness),
            trust=min(0.72, trust),
        ):
            linked.append(other_eid)
    return tuple(linked)


def ensure_underground_culture_organization(sim, slot):
    """Ensure the shared parent and one generated subculture organization."""

    if sim is None:
        return None
    slot = _safe_slot(slot)
    culture = underground_culture_profile(getattr(sim, "seed", 0), slot)
    parent_organization_eid = ensure_organization(
        sim,
        organization_key=UNDERGROUND_CULTURE_PARENT_KEY,
        organization_name="Underway Communities",
        organization_kind="community",
        tags=("underground", "community", "culture_family"),
    )
    organization_eid = ensure_organization(
        sim,
        organization_key=culture["culture_key"],
        organization_name=culture["culture_name"],
        organization_kind="community",
        tags=("underground", "community", "culture"),
        parent_organization_key=UNDERGROUND_CULTURE_PARENT_KEY,
        parent_org_eid=parent_organization_eid,
    )
    profile = organization_profile(sim, organization_eid)
    if profile is not None:
        profile.culture_profile = dict(culture)
    return organization_eid


def assign_underground_culture_member(sim, actor_eid, prop, chunk):
    """Give a native resident secondary community membership at this place."""

    if sim is None or actor_eid is None or not isinstance(prop, dict):
        return {}
    slot = underground_culture_slot(getattr(sim, "seed", 0), chunk)
    organization_eid = ensure_underground_culture_organization(sim, slot)
    profile = organization_profile(sim, organization_eid)
    culture = dict(getattr(profile, "culture_profile", {}) or {}) if profile is not None else {}
    if organization_eid is None or not culture:
        return {}

    metadata = prop.get("metadata")
    if not isinstance(metadata, dict):
        metadata = {}
        prop["metadata"] = metadata
    property_id = _text(prop.get("id")) or None
    building_id = _text(metadata.get("building_id") or metadata.get("local_building_id")) or None
    assign_actor_organization(
        sim,
        actor_eid,
        organization_eid=organization_eid,
        role="member",
        kind="membership",
        title="resident",
        primary=False,
        site_property_id=property_id,
        site_building_id=building_id,
    )
    link_property_organization(
        sim,
        prop,
        organization_eid=organization_eid,
        link_kind="meeting_place",
        primary=False,
    )
    metadata["underground_culture_key"] = culture["culture_key"]
    metadata["underground_culture_name"] = culture["culture_name"]
    metadata["underground_culture_slot"] = slot
    seed_underground_culture_bonds(sim, actor_eid, organization_eid, culture)
    return culture


def culture_profile_for_actor(sim, actor_eid):
    """Return an actor's active generated culture without implying knowledge."""

    if sim is None or actor_eid is None:
        return {}
    affiliations = sim.ecs.get(OrganizationAffiliations).get(int(actor_eid))
    memberships = getattr(affiliations, "memberships", {}) if affiliations is not None else {}
    if not isinstance(memberships, dict):
        return {}
    for organization_eid, membership in sorted(memberships.items(), key=lambda row: int(row[0])):
        if not isinstance(membership, dict) or not bool(membership.get("active", True)):
            continue
        profile = organization_profile(sim, organization_eid)
        culture = getattr(profile, "culture_profile", {}) if profile is not None else {}
        if isinstance(culture, dict) and _text(culture.get("culture_key")):
            return dict(culture)
    return {}


def culture_profile_for_property(sim, prop):
    """Return culture anchored to a property by a spawned resident."""

    if sim is None or not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata", {})
    if not isinstance(metadata, dict):
        return {}
    culture_key = _text(metadata.get("underground_culture_key"))
    if not culture_key:
        return {}
    organization_eid = organization_eid_for_key(sim, culture_key)
    profile = organization_profile(sim, organization_eid)
    culture = getattr(profile, "culture_profile", {}) if profile is not None else {}
    return dict(culture) if isinstance(culture, dict) else {}
