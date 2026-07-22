"""Subjective identity and witness-evidence helpers.

The simulation may know an actor eid without every person in the world knowing
who that actor is. This module keeps the identity state needed to preserve that
boundary reusable by dialogue, incidents, and justice.
"""

from __future__ import annotations

from copy import deepcopy

from game.appearance_loadout import appearance_loadout_for, appearance_metadata_for_entry
from game.color_words import color_word_family_profile
from game.components import (
    ArmorLoadout,
    ContactLedger,
    CreatureIdentity,
    Inventory,
    NPCMemory,
    Position,
    WeaponLoadout,
)
from game.human_description import build_human_description_profile
from game.items import ITEM_CATALOG
from game.lighting import ambient_snapshot


def _text(value):
    return str(value or "").strip()


def actor_identity_snapshot(sim, eid):
    """Return durable public identity fields for ``eid`` when they exist."""

    if sim is None or eid is None:
        return None
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    if identity is None:
        return None
    snapshot = {
        "personal_name": _text(getattr(identity, "personal_name", "")),
        "common_name": _text(getattr(identity, "common_name", "")),
        "gender_identity": _text(getattr(identity, "gender_identity", "")).lower(),
        "pronoun_set": _text(getattr(identity, "pronoun_set", "")).lower(),
        "creature_type": _text(getattr(identity, "creature_type", "")).lower(),
        "taxonomy_class": _text(getattr(identity, "taxonomy_class", "")).lower(),
    }
    return snapshot if any(snapshot.values()) else None


def ensure_contact_ledger(sim, eid):
    """Return an actor's sparse contact ledger, creating it only when needed."""

    if sim is None or eid is None:
        return None
    ledger = sim.ecs.get(ContactLedger).get(eid)
    if ledger is None:
        ledger = ContactLedger()
        sim.ecs.add(eid, ledger)
    return ledger


def remember_presented_identity(
    sim,
    viewer_eid,
    subject_eid,
    *,
    source_eid=None,
    relation_kind="known_person",
    standing=0.2,
    property_id=None,
    introduced=False,
    met_directly=False,
    benefits=("known_name",),
    tick=None,
):
    """Record the identity ``subject_eid`` deliberately presented to a viewer.

    Dossiers, records, and overheard names must not call this: those are
    unilateral knowledge. Personal meetings and arranged introductions use it
    to make name knowledge reciprocal.
    """

    if sim is None or viewer_eid is None or subject_eid is None:
        return None
    try:
        if int(viewer_eid) == int(subject_eid):
            return None
    except (TypeError, ValueError):
        if viewer_eid == subject_eid:
            return None

    ledger = ensure_contact_ledger(sim, viewer_eid)
    if ledger is None:
        return None
    if tick is None:
        tick = int(getattr(sim, "tick", 0) or 0)
    entry = ledger.person_entry(subject_eid) or {}
    first_met_tick = entry.get("first_met_tick")
    last_met_tick = entry.get("last_met_tick")
    if met_directly:
        if first_met_tick is None:
            first_met_tick = int(tick)
        last_met_tick = int(tick)
    merged_benefits = {
        str(bit or "").strip().lower()
        for bit in tuple(benefits or ())
        if str(bit or "").strip()
    }
    merged_benefits.update({"known_name", "mutual_identity"})
    ledger.remember_person(
        subject_eid,
        source_eid=source_eid,
        relation_kind=relation_kind,
        standing=max(0.0, min(1.0, float(standing or 0.0))),
        tick=int(tick),
        property_id=property_id,
        benefits=merged_benefits,
        introduced=bool(introduced),
        met_directly=bool(met_directly),
        first_met_tick=first_met_tick,
        last_met_tick=last_met_tick,
        identity_snapshot=actor_identity_snapshot(sim, subject_eid),
    )
    return ledger.person_entry(subject_eid)


def identities_are_mutually_known(sim, left_eid, right_eid):
    """Return whether both actors currently hold name knowledge of the other."""

    if sim is None or left_eid is None or right_eid is None:
        return False
    ledgers = sim.ecs.get(ContactLedger)
    left = ledgers.get(left_eid)
    right = ledgers.get(right_eid)
    if left is None or right is None:
        return False

    def _known(ledger, subject_eid):
        entry = ledger.person_entry(subject_eid)
        if not isinstance(entry, dict):
            return False
        benefits = {
            str(bit or "").strip().lower()
            for bit in tuple(entry.get("benefits", ()) or ())
            if str(bit or "").strip()
        }
        return bool(entry.get("introduced", False)) or "known_name" in benefits

    return _known(left, right_eid) and _known(right, left_eid)


def viewer_personally_knows_identity(sim, viewer_eid, subject_eid):
    """Return whether a viewer has a personal, rather than documentary, link."""

    if sim is None or viewer_eid is None or subject_eid is None:
        return False
    ledger = sim.ecs.get(ContactLedger).get(viewer_eid)
    entry = ledger.person_entry(subject_eid) if ledger is not None else None
    if not isinstance(entry, dict):
        return False
    benefits = {
        str(bit or "").strip().lower()
        for bit in tuple(entry.get("benefits", ()) or ())
        if str(bit or "").strip()
    }
    return bool(
        entry.get("introduced", False)
        or entry.get("met_directly", False)
        or "mutual_identity" in benefits
    )


def _recognized_memory_strength(sim, viewer_eid, subject_eid):
    memory = sim.ecs.get(NPCMemory).get(viewer_eid)
    if memory is None:
        return 0.0
    best = 0.0
    for entry in tuple(getattr(memory, "entries", ()) or ()):
        if not isinstance(entry, dict) or str(entry.get("kind", "")).strip().lower() != "recognized":
            continue
        data = entry.get("data") if isinstance(entry.get("data"), dict) else {}
        candidate = data.get("player_eid", data.get("subject_eid"))
        try:
            matches = int(candidate) == int(subject_eid)
        except (TypeError, ValueError):
            matches = candidate == subject_eid
        if matches:
            best = max(best, float(entry.get("strength", 0.0) or 0.0))
    return max(0.0, min(1.0, best))


def _worn_appearance_rows(sim, eid):
    loadout = appearance_loadout_for(sim, eid, create=False)
    if loadout is None:
        return ()
    inventory = sim.ecs.get(Inventory).get(eid)
    rows = []
    seen = set()
    slot_order = (
        "hat",
        "earrings",
        "necklace",
        "bracelet",
        "ring_left",
        "ring_right",
        "top",
        "bottom",
        "full_body",
        "outer",
        "shoes",
    )
    for slot in slot_order:
        instance_id = _text(getattr(loadout, "slots", {}).get(slot))
        if not instance_id or instance_id in seen or inventory is None:
            continue
        entry = inventory.find(instance_id=instance_id)
        profile = appearance_metadata_for_entry(entry) if entry else {}
        if not profile:
            continue
        seen.add(instance_id)
        metadata = dict(entry.get("metadata") or {})
        nested = metadata.get("appearance") if isinstance(metadata.get("appearance"), dict) else {}
        culture = metadata.get("employer_clothing_culture", nested.get("employer_clothing_culture"))
        token = metadata.get("personal_clothing_token", nested.get("personal_clothing_token"))
        culture = culture if isinstance(culture, dict) else {}
        token = token if isinstance(token, dict) else {}
        rows.append({
            "slot": slot,
            "item_id": _text(entry.get("item_id")),
            "label": _text(profile.get("label")),
            "color": _text(profile.get("color_word") or profile.get("color")).lower(),
            "material": _text(profile.get("material")).lower(),
            "style": _text(profile.get("style")).lower(),
            "pattern": _text(profile.get("pattern")).lower(),
            "emblem": _text(profile.get("emblem")).lower(),
            "employer_culture_signature": _text(culture.get("signature")),
            "employer_culture_motif": _text(culture.get("motif")).lower(),
            "employer_culture_salience": round(max(0.0, min(1.0, float(culture.get("recognition_salience", 0.0) or 0.0))), 3),
            "personal_token_signature": _text(token.get("signature")),
            "personal_token_motif": _text(token.get("motif")).lower(),
            "personal_token_salience": round(max(0.0, min(1.0, float(token.get("salience", 0.0) or 0.0))), 3),
        })

    occupied = {str(row.get("slot", "")) for row in rows}
    basewear = dict(getattr(loadout, "basewear", {}) or {})
    for base_slot, outer_slot in (("base_top", "top"), ("base_bottom", "bottom")):
        if outer_slot in occupied or "full_body" in occupied:
            continue
        profile = basewear.get(base_slot)
        if not isinstance(profile, dict):
            continue
        rows.append({
            "slot": base_slot,
            "item_id": _text(profile.get("item_id")),
            "label": _text(profile.get("label") or profile.get("appearance_type")).replace("_", " "),
            "color": _text(profile.get("color_word") or profile.get("color")).lower(),
            "material": _text(profile.get("material")).lower(),
            "style": _text(profile.get("style") or profile.get("detail")).lower(),
            "pattern": _text(profile.get("pattern")).lower(),
            "emblem": _text(profile.get("emblem")).lower(),
        })

    armor = sim.ecs.get(ArmorLoadout).get(eid)
    armor_id = _text(getattr(armor, "equipped_item_id", "")) if armor is not None else ""
    if armor_id:
        item = ITEM_CATALOG.get(armor_id, {})
        rows.append({
            "slot": "armor",
            "item_id": armor_id,
            "label": _text(getattr(armor, "equipped_name", "") or item.get("name") or armor_id).replace("_", " "),
            "color": "",
            "material": "",
            "style": "",
            "pattern": "",
            "emblem": "",
        })
    return tuple(rows)


def _perceived_color_fields(value, *, quality=1.0):
    """Return only the color detail a witness could carry from the scene.

    Exact wardrobe words are useful at arm's length in good light, but become
    broad hue/value reads and finally simple light/dark contrast as visual
    quality falls.  The structured family fields let a later exact garment
    match a truthful coarse report without pretending the witness saw its
    catalogue color name.
    """

    word = _text(value).lower()
    if not word:
        return {"color": "", "color_precision": "", "color_family": "", "color_tone": ""}
    profile = color_word_family_profile(word)
    family = _text(getattr(profile, "primary_hue", "")).lower() if profile is not None else ""
    tone = _text(getattr(profile, "value", "")).lower() if profile is not None else ""
    if tone in {"very_dark", "deep", "shadow"}:
        tone = "dark"
    elif tone in {"very_light", "pale", "bright"}:
        tone = "light"
    elif tone not in {"dark", "light"}:
        tone = "mid-tone"
    if family in {"black", "gray", "white"}:
        family = "neutral"

    quality = max(0.0, min(1.0, float(quality or 0.0)))
    if quality >= 0.72:
        perceived = word.replace("_", " ")
        precision = "exact"
    elif quality >= 0.48 and family:
        perceived = " ".join(bit for bit in (tone, family) if bit and bit != "mid-tone") or family
        precision = "broad"
    else:
        perceived = tone or "indistinct"
        precision = "tone"
    return {
        "color": perceived,
        "color_precision": precision,
        "color_family": family,
        "color_tone": tone,
    }


def _perceived_worn_row(row, *, quality=1.0):
    perceived = dict(row or {})
    perceived.update(_perceived_color_fields(perceived.get("color"), quality=quality))
    quality = max(0.0, min(1.0, float(quality or 0.0)))
    token_salience = max(0.0, min(1.0, float(perceived.get("personal_token_salience", 0.0) or 0.0)))
    culture_salience = max(0.0, min(1.0, float(perceived.get("employer_culture_salience", 0.0) or 0.0)))
    if quality < max(0.34, 0.67 - (token_salience * 0.38)):
        perceived["personal_token_signature"] = ""
        perceived["personal_token_motif"] = ""
    if quality < max(0.42, 0.72 - (culture_salience * 0.34)):
        perceived["employer_culture_signature"] = ""
        perceived["employer_culture_motif"] = ""
    return perceived


def visible_actor_description(sim, eid, *, quality=1.0):
    """Capture a structured, immutable-looking snapshot of a visible person."""

    if sim is None or eid is None:
        return {}
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    profile = build_human_description_profile(
        getattr(sim, "seed", 0),
        eid=eid,
        identity=identity,
        personal_name=getattr(identity, "personal_name", "") if identity is not None else None,
    )
    if not isinstance(profile, dict):
        return {}
    quality = max(0.0, min(1.0, float(quality or 0.0)))
    loadout = appearance_loadout_for(sim, eid, create=False)
    overrides = dict(getattr(loadout, "body_overrides", {}) or {}) if loadout is not None else {}
    marks = dict(getattr(loadout, "skin_marks", {}) or {}) if loadout is not None else {}

    description = {
        "presentation": _text(profile.get("gender_identity")).lower() if quality >= 0.22 else "",
        "build": _text(overrides.get("stature_compact") or profile.get("stature_compact")) if quality >= 0.28 else "",
        "complexion": _text(overrides.get("complexion_phrase") or profile.get("complexion_phrase")) if quality >= 0.68 else "",
        "eye_color": _text(overrides.get("eye_color") or profile.get("eye_color")) if quality >= 0.82 else "",
        "hair": {},
        "visible_marks": (),
        "worn_items": (),
        "weapon": {},
    }
    if quality >= 0.4:
        description["hair"] = {
            "color": _text(overrides.get("hair_color") or profile.get("hair_color")).lower(),
            "length": _text(overrides.get("hair_length") or profile.get("hair_length")).lower() if quality >= 0.5 else "",
            "texture": _text(overrides.get("hair_texture") or profile.get("hair_texture")).lower() if quality >= 0.62 else "",
            "style": _text(overrides.get("hair_style") or overrides.get("hair_style_compact") or profile.get("hair_style_compact")).lower() if quality >= 0.56 else "",
        }
    worn_rows = [_perceived_worn_row(row, quality=quality) for row in _worn_appearance_rows(sim, eid)]
    if quality < 0.42:
        worn_rows = [
            {
                "slot": row.get("slot", ""),
                "color": row.get("color", ""),
                "color_precision": row.get("color_precision", ""),
                "color_family": row.get("color_family", ""),
                "color_tone": row.get("color_tone", ""),
                "personal_token_signature": row.get("personal_token_signature", ""),
                "personal_token_motif": row.get("personal_token_motif", ""),
                "personal_token_salience": row.get("personal_token_salience", 0.0),
            }
            for row in worn_rows[:2]
        ]
    elif quality < 0.66:
        worn_rows = [
            {
                "slot": row.get("slot", ""),
                "label": row.get("label", ""),
                "color": row.get("color", ""),
                "color_precision": row.get("color_precision", ""),
                "color_family": row.get("color_family", ""),
                "color_tone": row.get("color_tone", ""),
                "style": row.get("style", ""),
                "emblem": row.get("emblem", ""),
                "pattern": row.get("pattern", ""),
                "employer_culture_signature": row.get("employer_culture_signature", ""),
                "employer_culture_motif": row.get("employer_culture_motif", ""),
                "employer_culture_salience": row.get("employer_culture_salience", 0.0),
                "personal_token_signature": row.get("personal_token_signature", ""),
                "personal_token_motif": row.get("personal_token_motif", ""),
                "personal_token_salience": row.get("personal_token_salience", 0.0),
            }
            for row in worn_rows[:4]
        ]
    description["worn_items"] = tuple(dict(row) for row in worn_rows)
    if quality >= 0.76:
        description["visible_marks"] = tuple(
            {
                "slot": _text(slot).lower(),
                "kind": _text(mark.get("kind")).lower(),
                "description": _text(mark.get("description") or mark.get("self_phrase")),
                "design": _text(mark.get("design")),
            }
            for slot, mark in sorted(marks.items())
            if isinstance(mark, dict) and _text(mark.get("kind"))
        )[:3]
    weapon = sim.ecs.get(WeaponLoadout).get(eid)
    weapon_id = _text(getattr(weapon, "equipped_weapon_id", "")) if weapon is not None else ""
    if weapon_id and quality >= 0.3:
        item = ITEM_CATALOG.get(weapon_id, {})
        description["weapon"] = {
            "item_id": weapon_id if quality >= 0.64 else "",
            "label": _text(item.get("name") or weapon_id).replace("_", " "),
        }
    return description


def observation_quality(sim, observer_eid, subject_eid, *, source_kind="witnessed", confidence=1.0):
    """Estimate how much identifying detail an observation can carry."""

    kind = _text(source_kind).lower()
    if observer_eid is not None and subject_eid is not None:
        try:
            if int(observer_eid) == int(subject_eid):
                return 1.0
        except (TypeError, ValueError):
            pass
    observer_pos = sim.ecs.get(Position).get(observer_eid) if observer_eid is not None else None
    subject_pos = sim.ecs.get(Position).get(subject_eid) if subject_eid is not None else None
    if observer_pos is not None and subject_pos is not None and int(observer_pos.z) == int(subject_pos.z):
        distance = abs(int(observer_pos.x) - int(subject_pos.x)) + abs(int(observer_pos.y) - int(subject_pos.y))
        quality = max(0.18, 0.98 - (distance * 0.055))
    elif kind in {"camera", "linked_drone_camera", "drone_radio_feed"}:
        quality = 0.76
    else:
        quality = 0.48
    if subject_pos is not None:
        sample = ambient_snapshot(sim, subject_pos.x, subject_pos.y, subject_pos.z)
        ambient = max(0.0, min(1.0, float(sample.get("ambient", 1.0) or 0.0)))
        quality *= 0.44 + (ambient * 0.56)
    if kind in {"camera", "linked_drone_camera", "drone_radio_feed"}:
        quality = min(0.94, quality + 0.08)
    return max(0.0, min(1.0, quality * max(0.0, min(1.0, float(confidence or 0.0)))))


def build_witness_subject_account(
    sim,
    observer_eid,
    subject_eid,
    *,
    source_kind="witnessed",
    confidence=1.0,
):
    """Describe what one observer can honestly claim about an incident actor."""

    if sim is None or subject_eid is None:
        return {
            "identification": "unknown",
            "suspect_eid": None,
            "presented_name": "",
            "identity_confidence": 0.0,
            "description": {},
            "observation": {"source": _text(source_kind).lower(), "quality": 0.0},
        }
    try:
        same_actor = int(observer_eid) == int(subject_eid)
    except (TypeError, ValueError):
        same_actor = observer_eid == subject_eid
    quality = observation_quality(
        sim,
        observer_eid,
        subject_eid,
        source_kind=source_kind,
        confidence=confidence,
    )
    subject_pos = sim.ecs.get(Position).get(subject_eid)
    observer_pos = sim.ecs.get(Position).get(observer_eid) if observer_eid is not None else None
    distance = None
    ambient = None
    light_phase = ""
    if subject_pos is not None and observer_pos is not None and int(subject_pos.z) == int(observer_pos.z):
        distance = abs(int(subject_pos.x) - int(observer_pos.x)) + abs(int(subject_pos.y) - int(observer_pos.y))
    if subject_pos is not None:
        sample = ambient_snapshot(sim, subject_pos.x, subject_pos.y, subject_pos.z)
        ambient = round(max(0.0, min(1.0, float(sample.get("ambient", 1.0) or 0.0))), 3)
        light_phase = _text(sample.get("phase")).lower()

    personally_known = viewer_personally_knows_identity(sim, observer_eid, subject_eid)
    recognition_memory = _recognized_memory_strength(sim, observer_eid, subject_eid)
    disguise_strength = 0.0
    if subject_eid == getattr(sim, "player_eid", None):
        disguise = getattr(sim, "disguise_state", None)
        if isinstance(disguise, dict):
            disguise_strength = max(0.0, min(1.0, float(disguise.get("strength", 0.0) or 0.0)))
    face_visibility = max(0.0, min(1.0, quality - (disguise_strength * 0.58)))
    recognized = bool(
        same_actor
        or (
            face_visibility >= 0.52
            and (personally_known or recognition_memory >= 0.58)
        )
    )
    identity = actor_identity_snapshot(sim, subject_eid) or {}
    identification = "verified" if same_actor else "recognized" if recognized else "described" if quality >= 0.16 else "unknown"
    return {
        "identification": identification,
        "suspect_eid": int(subject_eid) if recognized else None,
        "presented_name": _text(identity.get("personal_name")) if recognized else "",
        "identity_confidence": round(1.0 if same_actor else max(face_visibility, recognition_memory), 3) if recognized else 0.0,
        "description": visible_actor_description(sim, subject_eid, quality=quality) if quality >= 0.16 else {},
        "observation": {
            "source": _text(source_kind).lower() or "witnessed",
            "quality": round(float(quality), 3),
            "face_visibility": round(float(face_visibility), 3),
            "distance": distance,
            "ambient": ambient,
            "light_phase": light_phase,
            "tick": int(getattr(sim, "tick", 0) or 0),
        },
    }


def subject_account_rank(account):
    key = _text((account or {}).get("identification")).lower()
    return {
        "unknown": 0,
        "described": 1,
        "reported": 2,
        "recognized": 3,
        "verified": 4,
    }.get(key, 0)


def _degraded_description(description, *, propagation_depth=0, corruption_kind=""):
    """Return detail a person could plausibly preserve while retelling."""

    if not isinstance(description, dict):
        return {}
    result = deepcopy(description)
    depth = max(0, int(propagation_depth or 0))
    corruption = _text(corruption_kind).lower()

    hair = result.get("hair") if isinstance(result.get("hair"), dict) else {}
    worn = [dict(row) for row in tuple(result.get("worn_items", ()) or ()) if isinstance(row, dict)]
    weapon = result.get("weapon") if isinstance(result.get("weapon"), dict) else {}

    # Even the first retelling loses inventory-grade identifiers and other
    # details a witness would not naturally encode as database fields.
    for row in worn:
        row.pop("item_id", None)
        row.pop("emblem", None)
    weapon.pop("item_id", None)

    if depth >= 2 or corruption in {"detail_loss", "actor_blur"}:
        result["eye_color"] = ""
        result["visible_marks"] = ()
        hair["texture"] = ""
        hair["style"] = ""
        worn = worn[:3]
    if depth >= 3:
        result["complexion"] = ""
        hair["length"] = ""
        worn = [
            {
                "slot": _text(row.get("slot")).lower(),
                "label": _text(row.get("label")),
                "color": _text(row.get("color")).lower(),
            }
            for row in worn[:2]
        ]
    if depth >= 4 or corruption == "actor_blur":
        result["visible_marks"] = ()
        hair["style"] = ""
        worn = worn[:1]

    result["hair"] = hair
    result["worn_items"] = tuple(worn)
    result["weapon"] = weapon
    return result


def transmitted_subject_account(
    account,
    *,
    channel,
    source_eid=None,
    confidence=1.0,
    propagation_depth=0,
    corruption_kind="",
    preserve_reporter_account=False,
):
    """Copy a subjective identity claim across a communication channel.

    Rumors may transmit a name allegation, but do not make the listener a
    firsthand recognizer. Formal authority reports preserve what the reporter
    personally claims while attaching explicit report provenance.
    """

    incoming = deepcopy(account) if isinstance(account, dict) else {}
    identification = _text(incoming.get("identification")).lower() or "unknown"
    channel_key = _text(channel).lower() or "reported"
    depth = max(0, int(propagation_depth or 0))
    corruption = _text(corruption_kind).lower()
    try:
        source_eid = int(source_eid) if source_eid is not None else None
    except (TypeError, ValueError):
        source_eid = None
    try:
        confidence = max(0.0, min(1.0, float(confidence or 0.0)))
    except (TypeError, ValueError):
        confidence = 0.0

    if not preserve_reporter_account and identification in {"reported", "recognized", "verified"}:
        identification = "reported"
    if corruption == "actor_blur":
        identification = "described" if incoming.get("description") else "unknown"
        incoming["suspect_eid"] = None
        incoming["presented_name"] = ""

    original_observation = deepcopy(incoming.get("observation")) if isinstance(incoming.get("observation"), dict) else {}
    original_quality = float(original_observation.get("quality", 0.0) or 0.0)
    identity_confidence = float(incoming.get("identity_confidence", 0.0) or 0.0)
    channel_factor = 0.94 if preserve_reporter_account else max(0.36, 0.82 - max(0, depth - 1) * 0.1)
    carried_quality = max(0.0, min(1.0, original_quality * confidence * channel_factor))
    carried_identity_confidence = max(0.0, min(1.0, identity_confidence * confidence * channel_factor))

    if identification not in {"reported", "recognized", "verified"}:
        incoming["suspect_eid"] = None
        incoming["presented_name"] = ""
        carried_identity_confidence = 0.0

    incoming.update({
        "identification": identification,
        "identity_confidence": round(carried_identity_confidence, 3),
        "description": _degraded_description(
            incoming.get("description"),
            propagation_depth=0 if preserve_reporter_account else depth,
            corruption_kind="" if preserve_reporter_account else corruption,
        ),
        "observation": original_observation,
        "transmission": {
            "channel": channel_key,
            "source_eid": source_eid,
            "firsthand": False,
            "propagation_depth": depth,
            "confidence": round(confidence, 3),
            "carried_quality": round(carried_quality, 3),
            "corruption_kind": corruption,
        },
    })
    return incoming


def _description_value(value):
    return " ".join(_text(value).lower().split())


def description_match_score(description, current_description):
    """Compare a reported appearance with a currently visible actor.

    The result is investigative similarity, never identity proof. Missing
    details do not count against either side; contradictions lower the score.
    """

    wanted = description if isinstance(description, dict) else {}
    current = current_description if isinstance(current_description, dict) else {}
    matched = []
    conflicted = []
    matched_weight = 0.0
    comparable_weight = 0.0

    def compare(label, left, right, weight):
        nonlocal matched_weight, comparable_weight
        left_key = _description_value(left)
        right_key = _description_value(right)
        if not left_key or not right_key:
            return
        comparable_weight += float(weight)
        if left_key == right_key:
            matched_weight += float(weight)
            matched.append(label)
        else:
            conflicted.append(label)

    compare("presentation", wanted.get("presentation"), current.get("presentation"), 0.06)
    compare("build", wanted.get("build"), current.get("build"), 0.14)
    compare("complexion", wanted.get("complexion"), current.get("complexion"), 0.16)
    compare("eyes", wanted.get("eye_color"), current.get("eye_color"), 0.08)

    wanted_hair = wanted.get("hair") if isinstance(wanted.get("hair"), dict) else {}
    current_hair = current.get("hair") if isinstance(current.get("hair"), dict) else {}
    compare("hair color", wanted_hair.get("color"), current_hair.get("color"), 0.12)
    compare("hair length", wanted_hair.get("length"), current_hair.get("length"), 0.04)
    compare("hair texture", wanted_hair.get("texture"), current_hair.get("texture"), 0.03)
    compare("hair style", wanted_hair.get("style"), current_hair.get("style"), 0.03)

    current_worn = {
        _description_value(row.get("slot")): row
        for row in tuple(current.get("worn_items", ()) or ())
        if isinstance(row, dict) and _description_value(row.get("slot"))
    }
    for row in tuple(wanted.get("worn_items", ()) or ()):
        if not isinstance(row, dict):
            continue
        slot = _description_value(row.get("slot"))
        actual = current_worn.get(slot)
        if not slot or not isinstance(actual, dict):
            continue
        precision = _description_value(row.get("color_precision"))
        if precision == "tone":
            compare(f"{slot} color", row.get("color_tone") or row.get("color"), actual.get("color_tone"), 0.045)
        elif precision == "broad":
            wanted_family = row.get("color_family")
            actual_family = actual.get("color_family")
            wanted_tone = row.get("color_tone")
            actual_tone = actual.get("color_tone")
            compare(f"{slot} color", wanted_family, actual_family, 0.03)
            compare(f"{slot} tone", wanted_tone, actual_tone, 0.015)
        else:
            compare(f"{slot} color", row.get("color"), actual.get("color"), 0.045)
        compare(f"{slot} garment", row.get("label"), actual.get("label"), 0.035)
        compare(f"{slot} style", row.get("style"), actual.get("style"), 0.02)
        compare(f"{slot} pattern", row.get("pattern"), actual.get("pattern"), 0.025)
        compare(f"{slot} emblem", row.get("emblem"), actual.get("emblem"), 0.035)
        token_weight = 0.12 + (0.1 * max(0.0, min(1.0, float(row.get("personal_token_salience", 0.0) or 0.0))))
        culture_weight = 0.055 + (0.055 * max(0.0, min(1.0, float(row.get("employer_culture_salience", 0.0) or 0.0))))
        compare(
            f"{slot} personal token",
            row.get("personal_token_signature"),
            actual.get("personal_token_signature"),
            token_weight,
        )
        compare(
            f"{slot} employer colors",
            row.get("employer_culture_signature"),
            actual.get("employer_culture_signature"),
            culture_weight,
        )

    wanted_marks = {
        (_description_value(row.get("slot")), _description_value(row.get("kind")), _description_value(row.get("description")))
        for row in tuple(wanted.get("visible_marks", ()) or ())
        if isinstance(row, dict)
    }
    current_marks = {
        (_description_value(row.get("slot")), _description_value(row.get("kind")), _description_value(row.get("description")))
        for row in tuple(current.get("visible_marks", ()) or ())
        if isinstance(row, dict)
    }
    for mark in wanted_marks:
        if not any(mark):
            continue
        comparable_weight += 0.14
        if mark in current_marks:
            matched_weight += 0.14
            matched.append("visible mark")
        else:
            conflicted.append("visible mark")

    wanted_weapon = wanted.get("weapon") if isinstance(wanted.get("weapon"), dict) else {}
    current_weapon = current.get("weapon") if isinstance(current.get("weapon"), dict) else {}
    compare("carried weapon", wanted_weapon.get("label"), current_weapon.get("label"), 0.05)

    score = matched_weight / comparable_weight if comparable_weight > 0.0 else 0.0
    evidence_weight = min(1.0, comparable_weight / 0.65)
    plausible = bool(comparable_weight >= 0.18 and score >= 0.62)
    return {
        "score": round(max(0.0, min(1.0, score)), 3),
        "evidence_weight": round(max(0.0, min(1.0, evidence_weight)), 3),
        "comparable_weight": round(comparable_weight, 3),
        "plausible": plausible,
        "matched_cues": tuple(dict.fromkeys(matched)),
        "conflicting_cues": tuple(dict.fromkeys(conflicted)),
    }


def subject_account_conflict_read(left, right):
    """Describe material disagreement between two independently sourced accounts.

    This deliberately does not merge the accounts or decide which witness is
    right.  It gives casework a durable reason to keep an identification open
    when named identities or sufficiently detailed appearances disagree.
    """

    first = left if isinstance(left, dict) else {}
    second = right if isinstance(right, dict) else {}
    first_identification = _text(first.get("identification")).lower()
    second_identification = _text(second.get("identification")).lower()
    identity_kinds = {"reported", "recognized", "verified"}
    first_subject = first.get("suspect_eid")
    second_subject = second.get("suspect_eid")
    try:
        first_subject = int(first_subject) if first_subject is not None else None
    except (TypeError, ValueError):
        first_subject = None
    try:
        second_subject = int(second_subject) if second_subject is not None else None
    except (TypeError, ValueError):
        second_subject = None

    identity_conflict = bool(
        first_identification in identity_kinds
        and second_identification in identity_kinds
        and first_subject is not None
        and second_subject is not None
        and first_subject != second_subject
    )
    match = description_match_score(first.get("description"), second.get("description"))
    evidence_weight = float(match.get("evidence_weight", 0.0) or 0.0)
    score = float(match.get("score", 0.0) or 0.0)
    appearance_conflict = bool(evidence_weight >= 0.32 and score < 0.48)
    conflicting_cues = list(tuple(match.get("conflicting_cues", ()) or ()))
    if identity_conflict:
        conflicting_cues.insert(0, "named identity")
    return {
        "conflicted": bool(identity_conflict or appearance_conflict),
        "identity_conflict": identity_conflict,
        "appearance_conflict": appearance_conflict,
        "score": round(score, 3),
        "evidence_weight": round(evidence_weight, 3),
        "matched_cues": tuple(match.get("matched_cues", ()) or ()),
        "conflicting_cues": tuple(dict.fromkeys(conflicting_cues)),
    }


def description_match_for_actor(sim, description, actor_eid):
    current = visible_actor_description(sim, actor_eid, quality=1.0)
    result = description_match_score(description, current)
    result["current_description"] = current
    return result


def subject_description_summary(description):
    description = description if isinstance(description, dict) else {}
    bits = []
    for value in (description.get("presentation"), description.get("build"), description.get("complexion")):
        value = _text(value)
        if value and value.lower() not in {bit.lower() for bit in bits}:
            bits.append(value)
    hair = description.get("hair") if isinstance(description.get("hair"), dict) else {}
    hair_bits = [_text(hair.get(key)).lower() for key in ("length", "color", "texture") if _text(hair.get(key))]
    if hair_bits:
        bits.append(f"{' '.join(hair_bits)} hair")
    worn = [row for row in tuple(description.get("worn_items", ()) or ()) if isinstance(row, dict)]
    for row in worn[:2]:
        clothing = " ".join(bit for bit in (_text(row.get("color")).lower(), _text(row.get("label"))) if bit)
        if clothing:
            bits.append(clothing)
    return ", ".join(bits[:6]) or "a person with few reliable visual details"


def preferred_subject_account(existing, incoming):
    """Choose the strongest supported account without upgrading by retelling."""

    old = dict(existing or {})
    new = dict(incoming or {})
    if not old:
        return new
    if not new:
        return old
    old_rank = subject_account_rank(old)
    new_rank = subject_account_rank(new)
    if new_rank != old_rank:
        return new if new_rank > old_rank else old
    old_conf = float(old.get("identity_confidence", 0.0) or 0.0)
    new_conf = float(new.get("identity_confidence", 0.0) or 0.0)
    if old_rank <= 1:
        old_conf = float((old.get("observation") or {}).get("quality", old_conf) or 0.0)
        new_conf = float((new.get("observation") or {}).get("quality", new_conf) or 0.0)
    return new if new_conf > old_conf else old


__all__ = [
    "actor_identity_snapshot",
    "build_witness_subject_account",
    "description_match_for_actor",
    "description_match_score",
    "ensure_contact_ledger",
    "identities_are_mutually_known",
    "observation_quality",
    "preferred_subject_account",
    "remember_presented_identity",
    "subject_account_rank",
    "subject_account_conflict_read",
    "subject_description_summary",
    "transmitted_subject_account",
    "viewer_personally_knows_identity",
    "visible_actor_description",
]
