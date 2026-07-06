"""Live outfit impression helpers for dialogue and social bond context."""

from __future__ import annotations

import random
from math import copysign

from engine.visibility import has_line_of_sight
from game.appearance_palette import appearance_color_words, tags_for_color_word
from game.appearance_loadout import appearance_loadout_for, appearance_metadata_for_entry, appearance_signal_profile
from game.color_words import (
    color_word_display_name,
    color_word_family_profile,
    color_word_matches_family,
    curated_color_words,
    find_closest_native_color_word,
)
from game.components import (
    AI,
    ArmorLoadout,
    CreatureIdentity,
    Inventory,
    NPCSocial,
    NPCTraits,
    Occupation,
    OrganizationAffiliations,
    OrganizationProfile,
    Position,
    Vitality,
)
from game.human_description import build_human_description_profile


VISIBLE_OUTFIT_MAX_RANGE = 6
OUTFIT_COMMENT_THRESHOLD = 0.18
OUTFIT_SOCIAL_OFFSET_THRESHOLD = 0.08
OUTFIT_SOCIAL_OFFSET_CAP = 0.015
OUTFIT_SOCIAL_OFFSET_FRACTION = 0.2

_TAG_WEIGHTS = (
    "practical",
    "polished",
    "flashy",
    "jewelry",
    "rough",
    "street",
    "armor",
    "muted",
    "tattoo",
    "makeup",
    "styled_hair",
    "visible_mark",
)
_COLORS = appearance_color_words()
_COLOR_PREFERENCE_WORDS = curated_color_words()
_RENDER_COLOR_PROFILE = {
    "human_charcoal": ("charcoal", "black"),
    "human_olive": ("olive", "brown"),
    "human_denim": ("denim", "gray"),
    "human_accent": ("gold", "red"),
    "human_monochrome": ("gray", "white"),
    "human_rust": ("rust", "brown"),
    "human_slate": ("slate", "blue"),
    "human_wine": ("wine", "brass"),
}
_PRACTICAL_WORDS = {
    "canvas",
    "denim",
    "twill",
    "rubber",
    "boots",
    "sandals",
    "shorts",
    "workwear",
    "worn-in",
    "heavy",
    "lined",
    "plain",
    "relaxed",
    "field",
    "overshirt",
    "coat",
    "cardigan",
    "gloves",
}
_POLISHED_WORDS = {
    "crisp",
    "creased",
    "polished",
    "clean",
    "fitted",
    "sharp",
    "neat",
    "tailored",
    "blouse",
    "sweater",
    "turtleneck",
    "blazer",
    "scarf",
    "watch",
    "monochrome",
    "structured",
    "signet",
}
_FLASHY_WORDS = {
    "bright",
    "gold",
    "brass",
    "wine",
    "red",
    "satin",
    "drop",
    "hoop",
    "chain",
    "pendant",
    "jewelry",
    "rings",
    "bracelet",
    "earrings",
    "bandana",
    "scarf",
    "watch",
}
_ROUGH_WORDS = {
    "scuffed",
    "weathered",
    "patched",
    "rough",
    "worn",
    "faded",
    "leather",
    "bomber",
    "heavy",
    "coat",
    "gloves",
}
_STREET_WORDS = {
    "street",
    "denim",
    "jacket",
    "windbreaker",
    "sneakers",
    "cap",
    "baseball",
    "bandana",
    "patched",
    "overshirt",
    "boots",
    "coat",
    "vest",
    "scarf",
}
_MUTED_COLORS = frozenset(
    color
    for color in _COLORS
    if {"muted", "neutral", "dark"} & set(tags_for_color_word(color))
)
_FLASHY_COLORS = frozenset(
    color
    for color in _COLORS
    if {"flashy", "bright", "metal"} & set(tags_for_color_word(color))
)


def _key(value):
    return str(value or "").strip().lower()


def _safe_float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _clamp(value, lo=-1.0, hi=1.0):
    return max(float(lo), min(float(hi), float(value)))


def _bucket_add(mapping, key, amount):
    token = _key(key)
    if not token:
        return
    mapping[token] = _safe_float(mapping.get(token)) + float(amount)


def _positions(sim, left_eid, right_eid):
    if sim is None:
        return None, None
    positions = sim.ecs.get(Position)
    return positions.get(left_eid), positions.get(right_eid)


def actors_can_see_each_other(sim, viewer_eid, subject_eid, *, max_range=VISIBLE_OUTFIT_MAX_RANGE):
    viewer_pos, subject_pos = _positions(sim, viewer_eid, subject_eid)
    if viewer_pos is None or subject_pos is None:
        return False
    if int(getattr(viewer_pos, "z", 0)) != int(getattr(subject_pos, "z", 0)):
        return False
    if max(abs(int(viewer_pos.x) - int(subject_pos.x)), abs(int(viewer_pos.y) - int(subject_pos.y))) > int(max_range):
        return False
    try:
        return bool(
            has_line_of_sight(
                sim,
                int(viewer_pos.x),
                int(viewer_pos.y),
                int(viewer_pos.z),
                int(subject_pos.x),
                int(subject_pos.y),
                int(subject_pos.z),
            )
        )
    except Exception:
        return max(abs(int(viewer_pos.x) - int(subject_pos.x)), abs(int(viewer_pos.y) - int(subject_pos.y))) <= 1


def _actor_is_available(sim, eid):
    if sim is None or eid is None:
        return False
    pos = sim.ecs.get(Position).get(eid)
    if pos is None:
        return False
    vitality = sim.ecs.get(Vitality).get(eid)
    if vitality is not None and bool(getattr(vitality, "downed", False)):
        return False
    return True


def _inventory_entry_for_instance(sim, eid, instance_id):
    inventory = sim.ecs.get(Inventory).get(eid) if sim is not None else None
    if inventory is None:
        return None
    return inventory.find(instance_id=str(instance_id or "").strip())


def _add_profile_tags_from_words(tags, words):
    lowered = {_key(word) for word in words if _key(word)}
    if lowered & _PRACTICAL_WORDS:
        tags.add("practical")
    if lowered & _POLISHED_WORDS:
        tags.add("polished")
    if lowered & _FLASHY_WORDS:
        tags.add("flashy")
    if lowered & _ROUGH_WORDS:
        tags.add("rough")
    if lowered & _STREET_WORDS:
        tags.add("street")


def _clean_list(values):
    out = []
    for value in tuple(values or ()):
        token = _key(value)
        if token and token not in out:
            out.append(token)
    return tuple(out)


def _preference_color_key(color):
    token = _key(color)
    if not token:
        return ""
    return find_closest_native_color_word(token, default=token) or token


def _color_preference_keys(color):
    token = _key(color)
    if not token:
        return ()
    keys = []
    profile = color_word_family_profile(token)
    if profile is not None:
        keys.extend(profile.hue_families)
        if profile.native_fallback:
            keys.append(profile.native_fallback)
    fallback = _preference_color_key(token)
    if fallback:
        keys.append(fallback)
    if token in _COLOR_PREFERENCE_WORDS:
        keys.append(token)
    return _clean_list(keys)


def _dialogue_color_family_key(color):
    profile = color_word_family_profile(color)
    if profile is not None and profile.primary_hue:
        return profile.primary_hue
    return _preference_color_key(color)


def _dialogue_color_display_name(color):
    family = _dialogue_color_family_key(color)
    return color_word_display_name(family, default=family or color)


def _profile_from_loadout(sim, eid):
    loadout = appearance_loadout_for(sim, eid, create=False)
    if loadout is None:
        return None
    slots = dict(getattr(loadout, "slots", {}) or {})
    items = []
    tags = set()
    colors = []
    accent_colors = []
    materials = []
    styles = []
    labels = []
    types = []
    signature_parts = []
    for slot, instance_id in sorted(slots.items()):
        instance_id = str(instance_id or "").strip()
        if not instance_id:
            continue
        entry = _inventory_entry_for_instance(sim, eid, instance_id)
        profile = appearance_metadata_for_entry(entry)
        if not profile:
            continue
        color = _key(profile.get("color"))
        material = _key(profile.get("material"))
        style = _key(profile.get("style"))
        label = _key(profile.get("label"))
        appearance_type = _key(profile.get("appearance_type"))
        colors.append(color)
        accent_colors.append(_key(profile.get("accent_color")))
        materials.append(material)
        styles.append(style)
        labels.append(label)
        types.append(appearance_type)
        signature_parts.append(f"{slot}:{appearance_type}:{color}:{material}:{style}")
        words = [color, material, style, label, appearance_type, slot]
        _add_profile_tags_from_words(tags, words)
        for palette_tag in tags_for_color_word(color):
            if palette_tag in _TAG_WEIGHTS:
                tags.add(palette_tag)
        if slot in {"earrings", "necklace", "bracelet", "ring_left", "ring_right"}:
            tags.add("jewelry")
            tags.add("flashy")
        if color in _MUTED_COLORS:
            tags.add("muted")
        if color in _FLASHY_COLORS:
            tags.add("flashy")
        items.append({
            "slot": slot,
            "type": appearance_type,
            "label": label,
            "color": color,
            "material": material,
            "style": style,
        })

    armor = sim.ecs.get(ArmorLoadout).get(eid) if sim is not None else None
    if armor is not None and getattr(armor, "equipped_instance_id", None):
        tags.add("armor")
        tags.add("practical")
        label = _key(getattr(armor, "equipped_name", None) or getattr(armor, "equipped_item_id", "armor"))
        labels.append(label or "armor")
        types.append("armor")
        signature_parts.append(f"armor:{getattr(armor, 'equipped_item_id', '')}:{getattr(armor, 'equipped_instance_id', '')}")

    appearance_signals = appearance_signal_profile(sim, eid)
    for tag in tuple(appearance_signals.get("tags", ()) or ()):
        clean_tag = _key(tag)
        if clean_tag:
            tags.add(clean_tag)
    for tattoo in tuple(appearance_signals.get("tattoos", ()) or ()):
        if not isinstance(tattoo, dict):
            continue
        design = _key(tattoo.get("design"))
        if design:
            labels.append(f"{design} tattoo")
            signature_parts.append(f"tattoo:{tattoo.get('slot')}:{design}")
    makeup_regions = dict(appearance_signals.get("makeup_regions", {}) or {})
    if makeup_regions:
        styles.extend(_key(value) for value in makeup_regions.values() if _key(value))
        signature_parts.append("makeup:" + ",".join(f"{_key(k)}={_key(v)}" for k, v in sorted(makeup_regions.items())))
    body_overrides = dict(appearance_signals.get("body_overrides", {}) or {})
    if _key(body_overrides.get("hair_style")):
        styles.append(_key(body_overrides.get("hair_style")))
    if _key(body_overrides.get("hair_color")):
        colors.append(_key(body_overrides.get("hair_color")))

    if not items and "armor" not in tags and not appearance_signals.get("tags"):
        return None
    primary = _display_label(colors, labels, tags)
    dialogue_primary = _dialogue_display_label(colors, labels, tags)
    return {
        "source": "loadout",
        "items": tuple(items),
        "tags": tuple(sorted(tags)),
        "colors": _clean_list(colors),
        "accent_colors": _clean_list(accent_colors),
        "materials": _clean_list(materials),
        "styles": _clean_list(styles),
        "types": _clean_list(types),
        "labels": _clean_list(labels),
        "display_label": primary,
        "dialogue_display_label": dialogue_primary,
        "signature": "|".join(signature_parts) or primary,
    }


def _profile_from_seeded_description(sim, eid):
    identity = sim.ecs.get(CreatureIdentity).get(eid) if sim is not None else None
    if identity is None:
        return None
    profile = build_human_description_profile(
        getattr(sim, "seed", 0),
        eid=eid,
        identity=identity,
        personal_name=getattr(identity, "personal_name", ""),
    )
    if not profile:
        return None
    tags = set()
    words = []
    for key in ("attire_phrase", "attire_compact", "palette_phrase", "palette_compact", "condition_phrase", "accessory_phrase", "accessory_compact"):
        words.extend(str(profile.get(key, "") or "").replace("-", " ").replace(",", " ").split())
    _add_profile_tags_from_words(tags, words)
    accessory = _key(profile.get("accessory_phrase"))
    if any(word in accessory for word in ("ring", "earring", "chain", "bracelet", "jewelry", "pin")):
        tags.add("jewelry")
        tags.add("flashy")
    palette_key = _key(profile.get("render_color_key"))
    colors = _RENDER_COLOR_PROFILE.get(palette_key, ())
    for color in colors:
        for palette_tag in tags_for_color_word(color):
            if palette_tag in _TAG_WEIGHTS:
                tags.add(palette_tag)
        if color in _MUTED_COLORS:
            tags.add("muted")
        if color in _FLASHY_COLORS:
            tags.add("flashy")
    display = _key(profile.get("attire_compact")) or "outfit"
    dialogue_display = _dialogue_display_label(colors, (display,), tags)
    return {
        "source": "seeded_description",
        "items": (),
        "tags": tuple(sorted(tags)),
        "colors": _clean_list(colors),
        "accent_colors": (palette_key,) if palette_key else (),
        "materials": (),
        "styles": (),
        "types": (),
        "labels": (display,),
        "display_label": display,
        "dialogue_display_label": dialogue_display,
        "signature": f"npc:{palette_key}:{display}:{_key(profile.get('accessory_compact'))}",
    }


def _display_label(colors, labels, tags):
    labels = [label for label in labels if label and label not in {"armor"}]
    colors = [color for color in colors if color]
    if labels:
        label = labels[0].replace("_", " ")
        if colors:
            return f"{color_word_display_name(colors[0], default=colors[0])} {label}".strip()
        return label
    if "armor" in tags:
        return "armor"
    if "jewelry" in tags:
        return "jewelry"
    if colors:
        return f"{color_word_display_name(colors[0], default=colors[0])} outfit"
    return "outfit"


def _dialogue_display_label(colors, labels, tags):
    labels = [label for label in labels if label and label not in {"armor"}]
    colors = [color for color in colors if color]
    if labels:
        label = labels[0].replace("_", " ")
        if colors:
            return f"{_dialogue_color_display_name(colors[0])} {label}".strip()
        return label
    if "armor" in tags:
        return "armor"
    if "jewelry" in tags:
        return "jewelry"
    if colors:
        return f"{_dialogue_color_display_name(colors[0])} outfit".strip()
    return "outfit"


def _dialogue_label_for_item(item):
    if not isinstance(item, dict):
        return ""
    color = _key(item.get("color"))
    label = _key(item.get("label") or item.get("type") or item.get("slot"))
    if not label:
        return ""
    label = label.replace("_", " ")
    if color:
        return f"{_dialogue_color_display_name(color)} {label}".strip()
    return label


def _dialogue_display_cue(profile, reason_key):
    reason = _key(reason_key)
    if reason.startswith("color:"):
        family = reason.split(":", 1)[1]
        for item in tuple(profile.get("items", ()) or ()):
            if color_word_matches_family(item.get("color"), family):
                cue = _dialogue_label_for_item(item)
                if cue:
                    return cue
    return str(profile.get("dialogue_display_label") or profile.get("display_label") or "outfit").strip()


def actor_outfit_profile(sim, eid) -> dict:
    if sim is None or eid is None:
        return {}
    loadout_profile = _profile_from_loadout(sim, eid)
    if loadout_profile:
        return loadout_profile
    if eid == getattr(sim, "player_eid", None):
        return {}
    return _profile_from_seeded_description(sim, eid) or {}


def _actor_org_kinds(sim, eid):
    if sim is None or eid is None:
        return set()
    affiliations = sim.ecs.get(OrganizationAffiliations).get(eid)
    if affiliations is None:
        return set()
    profiles = sim.ecs.get(OrganizationProfile)
    kinds = set()
    for org_eid, row in dict(getattr(affiliations, "memberships", {}) or {}).items():
        if isinstance(row, dict) and not bool(row.get("active", True)):
            continue
        profile = profiles.get(org_eid)
        if profile is not None:
            kinds.add(_key(getattr(profile, "kind", "")))
    return {kind for kind in kinds if kind}


def _shared_org_kinds(sim, viewer_eid, subject_eid):
    return _actor_org_kinds(sim, viewer_eid) & _actor_org_kinds(sim, subject_eid)


def _district_type_for_actor(sim, eid):
    pos = sim.ecs.get(Position).get(eid) if sim is not None else None
    world = getattr(sim, "world", None)
    if pos is None or world is None:
        return ""
    try:
        chunk = world.get_chunk(*sim.chunk_coords(pos.x, pos.y))
        district = chunk.get("district", {}) if isinstance(chunk, dict) else {}
        return _key((district or {}).get("district_type"))
    except Exception:
        return ""


def npc_outfit_taste_profile(sim, npc_eid) -> dict:
    role = ""
    ai = sim.ecs.get(AI).get(npc_eid) if sim is not None else None
    if ai is not None:
        role = _key(getattr(ai, "role", ""))
    occupation = sim.ecs.get(Occupation).get(npc_eid) if sim is not None else None
    career = _key(getattr(occupation, "career", "")) if occupation is not None else ""
    traits = sim.ecs.get(NPCTraits).get(npc_eid) if sim is not None else None
    discipline = _safe_float(getattr(traits, "discipline", 0.5) if traits else 0.5, 0.5)
    bravery = _safe_float(getattr(traits, "bravery", 0.5) if traits else 0.5, 0.5)
    empathy = _safe_float(getattr(traits, "empathy", 0.5) if traits else 0.5, 0.5)
    district = _district_type_for_actor(sim, npc_eid)
    org_kinds = _actor_org_kinds(sim, npc_eid)
    seed = f"{getattr(sim, 'seed', 0)}:outfit-taste:{npc_eid}:{role}:{career}:{district}:{','.join(sorted(org_kinds))}"
    rng = random.Random(seed)
    tag_weights = {tag: rng.uniform(-0.045, 0.045) for tag in _TAG_WEIGHTS}
    color_weights = {color: 0.0 for color in _COLOR_PREFERENCE_WORDS}
    for color in rng.sample(tuple(_COLOR_PREFERENCE_WORDS), 2):
        color_weights[color] += rng.uniform(0.04, 0.09)
    for color in rng.sample(tuple(_COLOR_PREFERENCE_WORDS), 2):
        color_weights[color] -= rng.uniform(0.04, 0.09)

    tokens = {role, career, district}
    security_like = {"guard", "security", "cop", "peace_officer", "scout", "bouncer"} & tokens
    nightlife_like = {"bartender", "server", "dancer", "entertainment", "casino", "nightlife"} & tokens
    medical_like = {"doctor", "nurse", "medic", "clinic", "hospital"} & tokens
    industrial_like = {"mechanic", "worker", "courier", "driver", "industrial", "warehouse"} & tokens
    civic_like = {"clerk", "shopkeeper", "manager", "office", "civic", "commercial"} & tokens
    criminal_like = {"thief", "criminal", "gang", "crew", "runner"} & tokens

    if security_like:
        _bucket_add(tag_weights, "armor", 0.18)
        _bucket_add(tag_weights, "practical", 0.12)
        _bucket_add(tag_weights, "flashy", -0.09)
    if nightlife_like:
        _bucket_add(tag_weights, "flashy", 0.16)
        _bucket_add(tag_weights, "jewelry", 0.12)
        _bucket_add(tag_weights, "polished", 0.08)
    if medical_like:
        _bucket_add(tag_weights, "muted", 0.12)
        _bucket_add(tag_weights, "polished", 0.11)
        _bucket_add(tag_weights, "armor", -0.08)
        _bucket_add(tag_weights, "rough", -0.06)
    if industrial_like:
        _bucket_add(tag_weights, "practical", 0.17)
        _bucket_add(tag_weights, "rough", 0.08)
        _bucket_add(tag_weights, "polished", -0.04)
    if civic_like:
        _bucket_add(tag_weights, "polished", 0.1)
        _bucket_add(tag_weights, "muted", 0.07)
        _bucket_add(tag_weights, "rough", -0.04)
    if criminal_like:
        _bucket_add(tag_weights, "street", 0.16)
        _bucket_add(tag_weights, "rough", 0.08)
        _bucket_add(tag_weights, "muted", 0.05)
        _bucket_add(tag_weights, "polished", -0.04)

    if discipline >= 0.65:
        _bucket_add(tag_weights, "practical", (discipline - 0.5) * 0.18)
        _bucket_add(tag_weights, "polished", (discipline - 0.5) * 0.14)
        _bucket_add(tag_weights, "flashy", -(discipline - 0.5) * 0.12)
    if bravery >= 0.65:
        _bucket_add(tag_weights, "armor", (bravery - 0.5) * 0.16)
        _bucket_add(tag_weights, "street", (bravery - 0.5) * 0.08)
    if empathy >= 0.68:
        _bucket_add(tag_weights, "rough", (empathy - 0.5) * 0.06)

    for org_kind in org_kinds:
        if org_kind in {"street_gang", "gang", "criminal_network", "crew", "cell"}:
            _bucket_add(tag_weights, "street", 0.14)
            _bucket_add(tag_weights, "rough", 0.07)
            _bucket_add(tag_weights, "flashy", 0.04)
        elif org_kind in {"corporation", "corp", "company"}:
            _bucket_add(tag_weights, "polished", 0.15)
            _bucket_add(tag_weights, "muted", 0.09)
            _bucket_add(tag_weights, "rough", -0.07)
        elif org_kind in {"collective", "union"}:
            _bucket_add(tag_weights, "practical", 0.1)
            _bucket_add(tag_weights, "muted", 0.05)

    return {
        "tag_weights": {key: _clamp(value, -0.35, 0.35) for key, value in tag_weights.items()},
        "color_weights": {key: _clamp(value, -0.18, 0.18) for key, value in color_weights.items() if abs(value) > 0.001},
        "org_kinds": tuple(sorted(org_kinds)),
        "seed": seed,
    }


def _weighted_profile_score(profile, taste, *, shared_org_kinds=()):
    contributions = []
    tag_weights = dict(taste.get("tag_weights", {}) or {})
    color_weights = dict(taste.get("color_weights", {}) or {})
    for tag in tuple(profile.get("tags", ()) or ()):
        amount = _safe_float(tag_weights.get(tag))
        if amount:
            contributions.append((amount, tag))
    for idx, color in enumerate(tuple(profile.get("colors", ()) or ())):
        color_matches = []
        for preference_color in _color_preference_keys(color):
            amount = _safe_float(color_weights.get(preference_color))
            if amount:
                color_matches.append((amount, preference_color))
        if color_matches:
            amount, preference_color = max(color_matches, key=lambda row: abs(row[0]))
            amount *= 1.0 if idx == 0 else 0.45
            contributions.append((amount, f"color:{preference_color}"))

    score = sum(amount for amount, _reason in contributions)
    shared = {_key(kind) for kind in tuple(shared_org_kinds or ()) if _key(kind)}
    tags = set(profile.get("tags", ()) or ())
    group_bonus = 0.0
    if shared:
        if shared & {"street_gang", "gang", "criminal_network", "crew", "cell"} and tags & {"street", "rough", "flashy"}:
            group_bonus = 0.12
        elif shared & {"corporation", "corp", "company"} and tags & {"polished", "muted"}:
            group_bonus = 0.12
        elif shared & {"collective", "union"} and tags & {"practical", "muted"}:
            group_bonus = 0.1
        if score < 0.0:
            score *= 0.5
        if group_bonus:
            contributions.append((group_bonus, "group_signal"))
            score += group_bonus
    score = _clamp(score, -0.9, 0.9)
    if not contributions:
        return score, "neutral"
    reason = max(contributions, key=lambda row: abs(row[0]))[1]
    return score, reason


def visible_outfit_impression(sim, viewer_eid, subject_eid, context="dialogue") -> dict:
    if not _actor_is_available(sim, viewer_eid) or not _actor_is_available(sim, subject_eid):
        return {"visible": False, "score": 0.0, "polarity": "neutral", "reason_key": "", "display_cue": "", "outfit_signature": ""}
    if not actors_can_see_each_other(sim, viewer_eid, subject_eid):
        return {"visible": False, "score": 0.0, "polarity": "neutral", "reason_key": "", "display_cue": "", "outfit_signature": ""}
    profile = actor_outfit_profile(sim, subject_eid)
    if not profile:
        return {"visible": False, "score": 0.0, "polarity": "neutral", "reason_key": "", "display_cue": "", "outfit_signature": ""}
    taste = npc_outfit_taste_profile(sim, viewer_eid)
    score, reason = _weighted_profile_score(profile, taste, shared_org_kinds=_shared_org_kinds(sim, viewer_eid, subject_eid))
    if score >= OUTFIT_COMMENT_THRESHOLD:
        polarity = "positive"
    elif score <= -OUTFIT_COMMENT_THRESHOLD:
        polarity = "negative"
    else:
        polarity = "neutral"
    return {
        "visible": True,
        "score": score,
        "polarity": polarity,
        "reason_key": reason,
        "display_cue": (
            _dialogue_display_cue(profile, reason)
            if _key(context) == "dialogue"
            else str(profile.get("display_label", "") or "outfit").strip()
        ),
        "outfit_signature": str(profile.get("signature", "") or "").strip(),
        "context": _key(context) or "dialogue",
    }


def _strong_bond_dampening(sim, viewer_eid, subject_eid, score):
    if score >= 0:
        return score
    social = sim.ecs.get(NPCSocial).get(viewer_eid) if sim is not None else None
    bond = (getattr(social, "bonds", {}) or {}).get(subject_eid) if social is not None else None
    if not isinstance(bond, dict):
        return score
    kind = _key(bond.get("kind"))
    trust = _safe_float(bond.get("trust"))
    closeness = _safe_float(bond.get("closeness"))
    if kind in {"family", "partner"} or (kind == "friend" and max(trust, closeness) >= 0.72):
        return score * 0.35
    return score


def _adjust_delta(delta, score):
    delta = _safe_float(delta)
    if abs(delta) < 0.0001 or abs(score) < OUTFIT_SOCIAL_OFFSET_THRESHOLD:
        return delta
    magnitude = min(abs(delta) * OUTFIT_SOCIAL_OFFSET_FRACTION, OUTFIT_SOCIAL_OFFSET_CAP) * min(1.0, abs(score))
    return delta + copysign(magnitude, score)


def apply_visible_outfit_social_offset(
    sim,
    viewer_eid,
    subject_eid,
    *,
    trust_delta=0.0,
    closeness_delta=0.0,
    context="social_bond",
) -> dict:
    impression = visible_outfit_impression(sim, viewer_eid, subject_eid, context=context)
    score = _safe_float(impression.get("score"))
    if not bool(impression.get("visible")):
        return {
            "trust_delta": _safe_float(trust_delta),
            "closeness_delta": _safe_float(closeness_delta),
            "offset_applied": False,
            "impression": impression,
        }
    score = _strong_bond_dampening(sim, viewer_eid, subject_eid, score)
    adjusted_trust = _adjust_delta(trust_delta, score)
    adjusted_closeness = _adjust_delta(closeness_delta, score)
    return {
        "trust_delta": adjusted_trust,
        "closeness_delta": adjusted_closeness,
        "offset_applied": (
            abs(adjusted_trust - _safe_float(trust_delta)) >= 0.0001
            or abs(adjusted_closeness - _safe_float(closeness_delta)) >= 0.0001
        ),
        "impression": {**impression, "score": score},
    }
