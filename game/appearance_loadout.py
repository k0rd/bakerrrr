from __future__ import annotations

import random
from dataclasses import dataclass

from engine.events import Event
from game.appearance_palette import (
    appearance_color_words,
    choose_appearance_color_word,
    fallback_render_key_for_color_word,
    render_key_for_color_word,
)
from game.color_words import color_word_display_name
from game.components import AI, AppearanceLoadout, ArmorLoadout, CreatureIdentity, Inventory, Occupation, PlayerControlled
from game.fashion_market import (
    choose_cosmetic_flora_motif,
    cosmetic_flora_motif_phrase,
    record_cosmetic_popularity,
    with_cosmetic_rarity_metadata,
)
from game.human_description import (
    build_human_description_profile,
    human_complexion_render_color_key,
    human_eye_render_color_key,
    human_hair_render_color_key,
    human_render_color_key,
    human_self_physical_summary,
)
from game.human_identity import pronoun_format_slots
from game.item_semantics import item_display_name_for_actor
from game.items import ITEM_CATALOG, item_display_name, item_inventory_slot_cost
from game.organization_production import organization_clothing_culture
from game.organizations import primary_actor_membership


APPEARANCE_METADATA_KEY = "appearance"
APPEARANCE_WORN_METADATA_KEY = "appearance_worn"
APPEARANCE_SLOT_METADATA_KEY = "appearance_slot"

APPEARANCE_SLOTS = AppearanceLoadout.VALID_SLOTS
BASEWEAR_SLOTS = AppearanceLoadout.BASEWEAR_SLOTS
ALL_APPEARANCE_SLOTS = tuple(dict.fromkeys(APPEARANCE_SLOTS + BASEWEAR_SLOTS))
APPEARANCE_SLOT_LABELS = {
    "base_top": "Base top",
    "base_bottom": "Base bottom",
    "hat": "Hat",
    "earrings": "Earrings",
    "necklace": "Neck",
    "bracelet": "Wrist",
    "ring_left": "Left ring",
    "ring_right": "Right ring",
    "top": "Top",
    "bottom": "Bottom",
    "full_body": "Full body",
    "shoes": "Shoes",
    "outer": "Outer",
}
APPEARANCE_SLOT_ORDER = (
    "base_top",
    "base_bottom",
    "hat",
    "full_body",
    "top",
    "bottom",
    "outer",
    "shoes",
    "earrings",
    "necklace",
    "bracelet",
    "ring_left",
    "ring_right",
)
OUTFIT_COLOR_PRIORITY = (
    "outer",
    "full_body",
    "top",
    "bottom",
    "shoes",
    "hat",
    "necklace",
    "bracelet",
    "ring_left",
    "ring_right",
    "earrings",
)
def _catalog_appearance_profile(item_id, item_def):
    """Build the runtime fashion profile from one normalized catalogue row."""
    if not isinstance(item_def, dict):
        return {}
    raw = item_def.get("appearance_profile")
    if not isinstance(raw, dict) or not raw:
        return {}
    slots = tuple(
        str(slot).strip().lower()
        for slot in item_def.get("appearance_slots", ())
        if str(slot).strip().lower() in ALL_APPEARANCE_SLOTS
    )
    if not slots:
        return {}
    profile = dict(raw)
    profile["slots"] = slots
    profile.setdefault("label", str(item_def.get("name", "") or item_id).strip())
    return profile


# These indexes are projections of content, not parallel Python catalogues.
# New wearables opt in solely through items.json.
COSMETIC_ITEM_IDS = {
    item_id: profile
    for item_id, item_def in ITEM_CATALOG.items()
    if (profile := _catalog_appearance_profile(item_id, item_def))
    and bool(profile.get("fashion_item", True))
}
BASEWEAR_ITEM_IDS = {
    item_id: profile
    for item_id, profile in COSMETIC_ITEM_IDS.items()
    if bool(profile.get("basewear"))
    or any(slot in BASEWEAR_SLOTS for slot in tuple(profile.get("slots", ())))
}
ARTICLELESS_APPEARANCE_TYPES = frozenset(
    item_id
    for item_id, profile in COSMETIC_ITEM_IDS.items()
    if bool(profile.get("articleless"))
)


BASEWEAR_EMBLEMS = (
    "bee",
    "cherry",
    "daisy",
    "little heart",
    "little skull",
    "moon",
    "moth",
    "mushroom",
    "star",
    "strawberry",
    "tiny lightning bolt",
    "worklight",
)
COSMETIC_COLORS = appearance_color_words()
COSMETIC_COLOR_KEYS = {word: render_key_for_color_word(word) for word in COSMETIC_COLORS}
CLOTHING_RENDER_COLOR_KEYS = tuple(dict.fromkeys(COSMETIC_COLOR_KEYS.values()))
STYLE_SERVICE_OPTIONS = {
    "hair_style": (
        "cropped", "short", "bob", "braided", "loose", "nape-tied",
        "loose hair", "pinned-back hair", "side braid", "sharp bob", "high tail", "swept-back hair",
        "close sides", "slicked-back hair", "unruly hair", "rough crop", "neat part", "tied-back hair",
        "jaw-cut hair", "one-sided shave", "capped hair", "nape tie", "brow-falling hair", "uneven cut",
        "clipped-back hair", "careless tie", "heavy wave", "tight braids", "sharp short cut", "loose knot",
    ),
    "hair_color": (
        "black", "brown", "auburn", "blonde", "silver", "copper",
        "dark brown", "chestnut", "warm brown", "ash blond", "honey blond", "platinum blond",
        "copper-red", "charcoal",
    ),
    "makeup": ("none", "clean", "subtle", "smoky", "bold"),
    "makeup_eyes": ("none", "clean", "subtle", "smoky", "bold"),
    "makeup_lips": ("none", "clear", "soft", "dark", "bold"),
    "makeup_cheeks": ("none", "clean", "subtle", "warm", "bold"),
}
MAKEUP_STYLE_KINDS = frozenset({"makeup", "makeup_eyes", "makeup_lips", "makeup_cheeks"})
MAKEUP_REGION_BY_KIND = {
    "makeup_eyes": "eyes",
    "makeup_lips": "lips",
    "makeup_cheeks": "cheeks",
}
MAKEUP_REGION_LABELS = {
    "eyes": "Eyes",
    "lips": "Lips",
    "cheeks": "Cheeks",
}
APPEARANCE_STYLE_KINDS_BY_ARCHETYPE = {
    "hair_studio": ("hair_style", "hair_color"),
    "makeup_counter": ("makeup", "makeup_eyes", "makeup_lips", "makeup_cheeks"),
}
SKIN_MARK_SLOT_LABELS = {
    "forehead": "Forehead",
    "left_brow": "Left brow",
    "right_brow": "Right brow",
    "left_eye_area": "Left eye area",
    "right_eye_area": "Right eye area",
    "left_cheek": "Left cheek",
    "right_cheek": "Right cheek",
    "nose": "Nose",
    "lips": "Lips",
    "chin": "Chin",
    "neck": "Neck",
    "collarline": "Collarline",
    "left_wrist": "Left wrist",
    "right_wrist": "Right wrist",
    "left_hand": "Left hand",
    "right_hand": "Right hand",
    "left_forearm": "Left forearm",
    "right_forearm": "Right forearm",
    "upper_chest": "Upper chest",
    "back": "Back",
    "left_leg": "Left leg",
    "right_leg": "Right leg",
}
SKIN_MARK_SLOTS = tuple(SKIN_MARK_SLOT_LABELS)
MAKEUP_CONFLICT_REGIONS_BY_MARK_SLOT = {
    "left_brow": ("eyes",),
    "right_brow": ("eyes",),
    "left_eye_area": ("eyes",),
    "right_eye_area": ("eyes",),
    "left_cheek": ("cheeks",),
    "right_cheek": ("cheeks",),
    "lips": ("lips",),
}
TATTOO_SERVICE_ITEM_ID = "tattoo_service"
TATTOO_DESIGNS = (
    "anchor line",
    "blackwork band",
    "cedar sprig",
    "compass rose",
    "little starburst",
    "moth silhouette",
    "orbit line",
    "river wave",
    "threaded needle",
    "worklight halo",
)
TATTOO_LOCATION_ROWS = (
    ("left_forearm", "left forearm"),
    ("right_forearm", "right forearm"),
    ("left_wrist", "left wrist"),
    ("right_wrist", "right wrist"),
    ("collarline", "collarline"),
    ("neck", "neck"),
    ("left_cheek", "left cheek"),
    ("right_cheek", "right cheek"),
    ("left_eye_area", "left eye area"),
    ("right_eye_area", "right eye area"),
    ("lips", "near the lips"),
    ("upper_chest", "upper chest"),
)
NPC_DESCRIBED_OUTFIT_METADATA_KEY = "npc_described_outfit"
NPC_DESCRIBED_OUTFIT_SOURCE = "seeded_description_outfit"
EMPLOYER_CLOTHING_CULTURE_METADATA_KEY = "employer_clothing_culture"
PERSONAL_CLOTHING_TOKEN_METADATA_KEY = "personal_clothing_token"
PERSONAL_TOKEN_ITEMS = tuple(
    item_id
    for item_id, profile in COSMETIC_ITEM_IDS.items()
    if bool(profile.get("personal_token"))
)
PERSONAL_TOKEN_MOTIFS = (
    "bee", "broken chevron", "little eye", "little star", "moth",
    "painted hand", "threaded ring", "tiny lightning bolt",
)
NPC_DESCRIPTION_ATTIRE_ITEMS = {
    "dark fitted coat": ("coat", "tee", "trousers", "boots"),
    "tailored jacket": ("blazer", "button_up", "trousers", "boots"),
    "long cardigan": ("cardigan", "sweater", "trousers", "boots"),
    "sharp blouse and coat": ("coat", "blouse", "trousers", "boots"),
    "clean-cut jacket": ("jacket", "blouse", "skirt", "sneakers"),
    "structured coat": ("coat", "sweater", "trousers", "boots"),
    "weathered bomber jacket": ("jacket", "tee", "trousers", "boots"),
    "heavy coat": ("coat", "button_up", "trousers", "boots"),
    "dark blazer": ("blazer", "button_up", "trousers", "boots"),
    "field jacket": ("jacket", "tee", "trousers", "boots"),
    "denim jacket": ("jacket", "button_up", "trousers", "boots"),
    "thick overshirt": ("overshirt", "tee", "trousers", "boots"),
    "boxy coat": ("coat", "turtleneck", "trousers", "boots"),
    "straight-cut jacket": ("jacket", "turtleneck", "trousers", "boots"),
    "oversized overshirt": ("overshirt", "turtleneck", "trousers", "boots"),
    "cropped jacket": ("jacket", "turtleneck", "trousers", "boots"),
    "sleeveless vest": ("vest", "turtleneck", "trousers", "boots"),
    "severe long coat": ("coat", "turtleneck", "trousers", "boots"),
    "mixed dark coat": ("coat", "tee", "trousers", "boots"),
    "sharp jacket": ("jacket", "blouse", "trousers", "boots", "scarf"),
    "weathered coat": ("coat", "button_up", "trousers", "boots"),
    "structured blazer": ("blazer", "button_up", "trousers", "boots"),
    "neat overshirt": ("overshirt", "tee", "trousers", "boots"),
    "layered long coat": ("coat", "sweater", "trousers", "boots"),
}
NPC_DESCRIPTION_ACCESSORY_ITEMS = {
    "silver rings": ("ring",),
    "small earrings": ("earrings",),
    "narrow scarf": ("scarf",),
    "watch chain": ("watch",),
    "fingerless gloves": ("gloves",),
    "heavy rings": ("ring",),
    "chain and cuff": ("necklace", "bracelet"),
    "wrapped scarf": ("scarf",),
    "ear studs": ("earrings",),
    "rings and watchband": ("ring", "watch"),
    "scarf and id tag": ("scarf",),
    "bracelets and gloves": ("bracelet", "gloves"),
    "bag and rings": ("ring",),
}


@dataclass(frozen=True)
class AppearanceEquipResult:
    ok: bool
    action: str = ""
    reason: str = ""
    slot: str = ""
    item_name: str = ""


def _text(value):
    return str(value or "").strip()


def _key(value):
    return _text(value).lower()


def _title_words(text):
    return " ".join(part.capitalize() for part in _text(text).replace("_", " ").split())


def _clean_slots(values):
    if not isinstance(values, (list, tuple, set)):
        values = (values,)
    slots = []
    for value in values:
        slot = _key(value)
        if slot in ALL_APPEARANCE_SLOTS and slot not in slots:
            slots.append(slot)
    return tuple(slots)


def style_service_kinds_for_property(prop):
    metadata = prop.get("metadata") if isinstance(prop, dict) and isinstance(prop.get("metadata"), dict) else {}
    configured = metadata.get("appearance_style_kinds") if isinstance(metadata, dict) else None
    if isinstance(configured, (list, tuple, set)):
        kinds = tuple(_key(kind) for kind in configured if _key(kind) in STYLE_SERVICE_OPTIONS)
        if kinds:
            return kinds
    archetype = _key(metadata.get("archetype") if isinstance(metadata, dict) else "")
    return tuple(APPEARANCE_STYLE_KINDS_BY_ARCHETYPE.get(archetype, tuple(STYLE_SERVICE_OPTIONS)))


def _skin_mark_entry(kind, slot, *, description="", self_phrase="", design="", source="", covered_mark=None):
    kind = _key(kind)
    slot = _key(slot)
    if not kind or slot not in SKIN_MARK_SLOTS:
        return {}
    row = {
        "kind": kind,
        "slot": slot,
        "description": _text(description),
        "self_phrase": _text(self_phrase),
        "design": _text(design),
        "source": _key(source),
    }
    if isinstance(covered_mark, dict) and covered_mark:
        row["covered_mark"] = dict(covered_mark)
    return row


def _makeup_conflict_regions_for_slot(slot):
    return tuple(MAKEUP_CONFLICT_REGIONS_BY_MARK_SLOT.get(_key(slot), ()))


def _tattoo_conflict_regions(loadout):
    blocked = set()
    marks = dict(getattr(loadout, "skin_marks", {}) or {})
    for slot, mark in marks.items():
        if _key((mark or {}).get("kind")) != "tattoo":
            continue
        blocked.update(_makeup_conflict_regions_for_slot(slot))
    return tuple(sorted(blocked))


def _makeup_region_blocked(loadout, region):
    return _key(region) in set(_tattoo_conflict_regions(loadout))


def seed_appearance_skin_marks_from_description(sim, eid, *, loadout=None):
    if sim is None or eid is None:
        return False
    if loadout is None:
        loadout = sim.ecs.get(AppearanceLoadout).get(eid)
    if loadout is None:
        return False
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    profile = build_human_description_profile(
        getattr(sim, "seed", 0),
        eid=eid,
        identity=identity,
        personal_name=getattr(identity, "personal_name", "") if identity is not None else "",
    )
    mark = profile.get("standout_mark") if isinstance(profile, dict) else None
    if isinstance(mark, dict) and mark:
        slot = _key(mark.get("slot"))
        if slot in SKIN_MARK_SLOTS and not dict(getattr(loadout, "skin_marks", {}) or {}).get(slot):
            loadout.skin_marks[slot] = _skin_mark_entry(
                mark.get("kind"),
                slot,
                description=mark.get("description"),
                self_phrase=mark.get("self_phrase"),
                design=mark.get("design"),
                source=mark.get("source") or "seeded_description",
            )
    loadout.skin_marks_seeded = True
    return True


def _seeded_makeup_for_profile(profile, rng):
    profile = profile if isinstance(profile, dict) else {}
    style_axis = _key(profile.get("style_axis"))
    grooming = _key(profile.get("grooming_sentence"))
    standout = _key(profile.get("standout_compact"))
    global_makeup = ""
    regions = {}
    if standout == "sharp eyeliner":
        global_makeup = "clean"
        regions["eyes"] = "bold"
    elif "makeup" in grooming:
        global_makeup = rng.choice(("clean", "subtle"))
    elif style_axis == "femme" and rng.random() < 0.42:
        global_makeup = rng.choice(("clean", "subtle"))
    elif style_axis == "mixed" and rng.random() < 0.22:
        global_makeup = "subtle"
    elif style_axis == "androgynous" and rng.random() < 0.12:
        global_makeup = "clean"
    return global_makeup, regions


def _seeded_silhouette_variant(profile, rng):
    profile = profile if isinstance(profile, dict) else {}
    presentation = _key(profile.get("style_axis"))
    stature_phrase = _key(profile.get("stature_phrase"))
    build = _key(profile.get("stature_compact"))
    if presentation == "femme":
        weights = (("straight", 0.34), ("soft", 0.48), ("curvy", 0.18))
        if "lightly built" in stature_phrase or build == "lean":
            weights = (("straight", 0.68), ("soft", 0.27), ("curvy", 0.05))
        elif build in {"sturdy", "compact"}:
            weights = (("straight", 0.12), ("soft", 0.48), ("curvy", 0.40))
    elif presentation == "masc":
        weights = (("lean", 0.30), ("regular", 0.48), ("broad", 0.22))
        if "lightly built" in stature_phrase or build == "lean":
            weights = (("lean", 0.66), ("regular", 0.29), ("broad", 0.05))
        elif build in {"sturdy", "compact"} or "broad-shouldered" in stature_phrase or "square-shouldered" in stature_phrase:
            weights = (("lean", 0.08), ("regular", 0.36), ("broad", 0.56))
    else:
        weights = (("slight", 0.34), ("balanced", 0.48), ("solid", 0.18))
        if "lightly built" in stature_phrase or build == "lean":
            weights = (("slight", 0.62), ("balanced", 0.33), ("solid", 0.05))
        elif build in {"sturdy", "compact"}:
            weights = (("slight", 0.10), ("balanced", 0.46), ("solid", 0.44))
    pick = rng.random()
    running = 0.0
    for variant, weight in weights:
        running += float(weight)
        if pick <= running:
            return variant
    return weights[-1][0]


def seed_npc_innate_appearance_from_description(sim, eid, *, seed_token=""):
    loadout = appearance_loadout_for(sim, eid, create=True)
    if loadout is None:
        return False
    persisted_profile_keys = (
        "style_axis",
        "stature_phrase",
        "stature_compact",
        "complexion_phrase",
        "eye_color",
        "hair_color",
        "hair_texture",
        "hair_length",
        "hair_style_compact",
        "hair_style_phrase",
    )
    existing_overrides = dict(getattr(loadout, "body_overrides", {}) or {})
    already_seeded = bool(getattr(loadout, "description_appearance_seeded", False))
    if (
        already_seeded
        and all(_text(existing_overrides.get(key)) for key in persisted_profile_keys)
        and _text(existing_overrides.get("silhouette_variant"))
    ):
        return False
    identity = sim.ecs.get(CreatureIdentity).get(eid) if sim is not None else None
    profile = build_human_description_profile(
        getattr(sim, "seed", 0),
        eid=eid,
        identity=identity,
        personal_name=getattr(identity, "personal_name", None),
    )
    if not isinstance(profile, dict):
        return False

    seed_appearance_skin_marks_from_description(sim, eid, loadout=loadout)
    overrides = dict(existing_overrides)
    for key in persisted_profile_keys:
        source_key = "hair_style_compact" if key == "hair_style_compact" else key
        value = _text(profile.get(source_key))
        if value and not _text(overrides.get(key)):
            overrides[key] = value
    if not _text(overrides.get("hair_style")) and _text(profile.get("hair_style_compact")):
        overrides["hair_style"] = _text(profile.get("hair_style_compact"))
    if not _text(overrides.get("silhouette_variant")):
        silhouette_rng = random.Random(f"human-silhouette:{getattr(sim, 'seed', 0)}:{eid}:{profile.get('seed_token')}")
        overrides["silhouette_variant"] = _seeded_silhouette_variant(profile, silhouette_rng)
    rng = random.Random(f"npc-innate-appearance:{getattr(sim, 'seed', 0)}:{eid}:{seed_token}:{profile.get('seed_token')}")
    makeup, regions = _seeded_makeup_for_profile(profile, rng)
    if makeup and not _text(overrides.get("makeup")) and not _tattoo_conflict_regions(loadout):
        overrides["makeup"] = makeup
    loadout.body_overrides = AppearanceLoadout._clean_overrides(overrides)
    makeup_regions = dict(getattr(loadout, "makeup_regions", {}) or {})
    for region, value in regions.items():
        if not _makeup_region_blocked(loadout, region) and not _text(makeup_regions.get(region)):
            makeup_regions[region] = value
    loadout.makeup_regions = AppearanceLoadout._clean_overrides(makeup_regions)
    loadout.description_appearance_seeded = True
    return (not already_seeded) or overrides != existing_overrides


def appearance_loadout_for(sim, eid, create=False):
    if sim is None or eid is None:
        return None
    bucket = sim.ecs.get(AppearanceLoadout)
    loadout = bucket.get(eid)
    if loadout is None and create:
        loadout = AppearanceLoadout()
        sim.ecs.add(eid, loadout)
    if loadout is not None and hasattr(loadout, "normalize"):
        loadout.normalize()
        if not bool(getattr(loadout, "skin_marks_seeded", False)):
            seed_appearance_skin_marks_from_description(sim, eid, loadout=loadout)
        if _is_player_appearance_owner(sim, eid):
            ensure_player_basewear(sim, eid, loadout=loadout)
    return loadout


def _is_player_appearance_owner(sim, eid):
    if sim is None or eid is None:
        return False
    if eid == getattr(sim, "player_eid", None):
        return True
    return sim.ecs.get(PlayerControlled).get(eid) is not None


def _inventory_for(sim, eid):
    if sim is None or eid is None:
        return None
    return sim.ecs.get(Inventory).get(eid)


def _item_def(item_id, item_catalog=None):
    catalog = ITEM_CATALOG if item_catalog is None else item_catalog
    return catalog.get(_key(item_id), {})


def _appearance_profile(item_id, *, item_catalog=None):
    item_id = _key(item_id)
    return _catalog_appearance_profile(
        item_id,
        _item_def(item_id, item_catalog=item_catalog),
    )


def _entry_metadata(entry):
    return dict(entry.get("metadata") or {}) if isinstance(entry, dict) else {}


def appearance_metadata_for_entry(entry, *, item_catalog=None):
    if not isinstance(entry, dict):
        return {}
    metadata = _entry_metadata(entry)
    nested = metadata.get(APPEARANCE_METADATA_KEY)
    item_id = _key(entry.get("item_id"))
    item_def = _item_def(item_id, item_catalog=item_catalog)
    profile = _appearance_profile(item_id, item_catalog=item_catalog)
    nested_data = nested if isinstance(nested, dict) else {}
    slots = _clean_slots(
        metadata.get("appearance_slots")
        or metadata.get("occupied_slots")
        or nested_data.get("slots")
    )
    if not slots:
        slots = _clean_slots(item_def.get("appearance_slots"))
    if not slots and profile:
        slots = tuple(profile.get("slots", ()))
    appearance_type = _key(metadata.get("appearance_type") or nested_data.get("type")) or item_id
    outer_color = _key(metadata.get("color"))
    nested_color = _key(nested_data.get("color"))
    explicit_color_word = _key(metadata.get("color_word") or nested_data.get("color_word"))
    # The nested appearance record is the canonical garment description. The
    # outer ``color`` field predates exact color words and can still contain a
    # neutral render fallback on older or externally-authored items.
    legacy_color = nested_color or outer_color
    color_word = explicit_color_word or legacy_color
    # ``color`` predates the shared exact color-word channel and some saved or
    # externally-authored items still carry a neutral render fallback there.
    # When both exist, the precise word is the appearance truth.
    color = color_word or legacy_color
    material = _key(metadata.get("material") or nested_data.get("material"))
    style = _key(metadata.get("style") or nested_data.get("style"))
    accent = _key(metadata.get("accent_color") or nested_data.get("accent_color"))
    detail = _key(metadata.get("detail") or nested_data.get("detail"))
    pattern = _key(metadata.get("pattern") or nested_data.get("pattern"))
    emblem = _key(metadata.get("emblem") or nested_data.get("emblem"))
    flora_motif_source = metadata.get("flora_motif") if isinstance(metadata.get("flora_motif"), dict) else nested_data.get("flora_motif")
    flora_motif = dict(flora_motif_source) if isinstance(flora_motif_source, dict) else {}
    presentation = _key(metadata.get("presentation") or nested_data.get("presentation") or profile.get("presentation"))
    label = _text(metadata.get("appearance_label") or nested_data.get("label"))
    if not label:
        label = _text(profile.get("label")) or _text(item_def.get("name")) or _title_words(item_id)
    if not color:
        color = color_word or "charcoal"
    if not color_word:
        color_word = color
    if not material:
        material = _text((profile.get("materials") or ("cotton",))[0]).lower()
    if not style:
        style = _text((profile.get("styles") or ("plain",))[0]).lower()
    derived_accent = fallback_render_key_for_color_word(color_word, default="") if color_word else ""
    stale_neutral_accent = accent in {"clothing_gray", "human_gray", "human_monochrome", "default"}
    precise_non_neutral_fallback = derived_accent and derived_accent not in {
        "clothing_gray",
        "human_gray",
        "human_monochrome",
        "default",
    }
    if (
        derived_accent
        and explicit_color_word
        and legacy_color
        and explicit_color_word != legacy_color
    ) or (stale_neutral_accent and precise_non_neutral_fallback):
        # ``accent_color`` is the limited-palette rendering fallback for worn
        # clothing, not a second decorative color. Replace a genuinely stale
        # neutral value, while retaining compatible legacy keys such as
        # ``human_wine`` that still represent the same stated color.
        accent = derived_accent
    elif not accent:
        accent = derived_accent or "human_monochrome"
    if not slots:
        return {}
    return {
        "appearance_type": appearance_type,
        "appearance_drawable": _key(item_def.get("appearance_drawable")),
        "label": label,
        "slots": slots,
        "color": color,
        "color_word": color_word,
        "material": material,
        "style": style,
        "accent_color": accent,
        "detail": detail,
        "pattern": pattern,
        "emblem": emblem,
        "flora_motif": flora_motif,
        "presentation": presentation,
        "fashion_rarity": _key(metadata.get("fashion_rarity") or nested_data.get("fashion_rarity")),
        "fashion_rarity_score": metadata.get("fashion_rarity_score", nested_data.get("fashion_rarity_score")),
        "fashion_base_value": metadata.get("fashion_base_value", nested_data.get("fashion_base_value")),
        "fashion_rarity_value": metadata.get("fashion_rarity_value", nested_data.get("fashion_rarity_value")),
        "basewear": bool(profile.get("basewear") or any(slot in BASEWEAR_SLOTS for slot in slots)),
    }


def is_appearance_item(entry_or_item_id, *, item_catalog=None):
    if isinstance(entry_or_item_id, dict):
        entry = entry_or_item_id
        metadata = _entry_metadata(entry)
        if metadata.get(APPEARANCE_METADATA_KEY) or metadata.get("appearance_type"):
            return bool(appearance_metadata_for_entry(entry, item_catalog=item_catalog))
        item_id = _key(entry.get("item_id"))
    else:
        item_id = _key(entry_or_item_id)
    item_def = _item_def(item_id, item_catalog=item_catalog)
    tags = {_key(tag) for tag in item_def.get("tags", ())}
    category = _key(item_def.get("category"))
    return bool(_appearance_profile(item_id, item_catalog=item_catalog)) or category == "cosmetic" or "cosmetic" in tags or "clothing" in tags


def is_entry_worn(entry):
    metadata = _entry_metadata(entry)
    return bool(metadata.get(APPEARANCE_WORN_METADATA_KEY))


def is_basewear_item(entry_or_item_id, *, item_catalog=None):
    if isinstance(entry_or_item_id, dict):
        profile = appearance_metadata_for_entry(entry_or_item_id, item_catalog=item_catalog)
        return bool(profile.get("basewear"))
    profile = _appearance_profile(entry_or_item_id, item_catalog=item_catalog)
    return bool(profile.get("basewear") or any(slot in BASEWEAR_SLOTS for slot in tuple(profile.get("slots", ()))))


def _basewear_phrase(profile):
    profile = profile if isinstance(profile, dict) else {}
    color_key = _key(profile.get("color_word") or profile.get("color"))
    color = color_word_display_name(color_key, default=color_key.replace("_", " "))
    detail = _key(profile.get("detail") or profile.get("style"))
    pattern = _key(profile.get("pattern"))
    material = _key(profile.get("material"))
    label = _text(profile.get("label")) or _text(profile.get("appearance_type")).replace("_", " ")
    bits = [color]
    if pattern:
        bits.append(pattern.replace("_", " "))
    if detail and detail not in {"plain", "simple", "classic"}:
        bits.append(detail.replace("_", " "))
    elif material:
        bits.append(material.replace("_", " "))
    bits.append(label)
    phrase = " ".join(bit for bit in bits if bit)
    flora_motif = profile.get("flora_motif") if isinstance(profile.get("flora_motif"), dict) else {}
    motif_phrase = cosmetic_flora_motif_phrase(flora_motif)
    emblem = _key(profile.get("emblem")).replace("_", " ")
    if motif_phrase:
        phrase += f" with {motif_phrase}"
    elif emblem:
        phrase += f" with {_indefinite_article_phrase(emblem)} emblem"
    return phrase


def cosmetic_variant_metadata(item_id, *, seed_token="", item_catalog=None, sim=None):
    item_id = _key(item_id)
    profile = _appearance_profile(item_id, item_catalog=item_catalog)
    if not profile:
        return {}
    basewear = bool(profile.get("basewear") or any(slot in BASEWEAR_SLOTS for slot in tuple(profile.get("slots", ()))))
    seed = f"cosmetic-variant:{item_id}:{seed_token}"
    rng = random.Random(seed)
    slots = tuple(profile.get("slots", ()))
    color = choose_appearance_color_word(rng, slots=slots)
    materials = tuple(profile.get("materials") or ("cotton",))
    details = tuple(profile.get("details") or ())
    styles = tuple(profile.get("styles") or details or ("plain",))
    material = rng.choice(materials)
    style = rng.choice(styles)
    detail = rng.choice(details) if details else ""
    patterns = tuple(profile.get("patterns") or ())
    pattern = rng.choice(patterns) if patterns else ""
    emblem = ""
    if basewear and rng.random() < float(profile.get("emblem_chance", 0.0) or 0.0):
        emblem = rng.choice(tuple(profile.get("emblems") or BASEWEAR_EMBLEMS))
    pattern_key = _key(pattern)
    emblem_key = _key(emblem)
    generic_flora_pattern = pattern_key in {"little-floral", "floral", "flower-print"}
    generic_flora_emblem = emblem_key == "daisy"
    flora_motif = choose_cosmetic_flora_motif(
        sim,
        item_id,
        seed_token=seed_token,
        slots=slots,
        force=generic_flora_pattern or generic_flora_emblem,
        treatment_hint="print" if generic_flora_pattern else ("embroidery" if generic_flora_emblem else ""),
    )
    if flora_motif:
        pattern = ""
        emblem = ""
    accent = fallback_render_key_for_color_word(color, default="human_monochrome")
    label = str(profile.get("label", item_id)).strip() or item_id
    presentation = _key(profile.get("presentation"))
    if basewear:
        display_name = _title_words(_basewear_phrase({
            "appearance_type": item_id,
            "label": label,
            "color": color,
            "color_word": color,
            "material": material,
            "style": style,
            "detail": detail,
            "pattern": pattern,
            "emblem": emblem,
            "flora_motif": flora_motif,
        }))
    else:
        display_parts = [color, material, label]
        if style and style not in {"plain", "simple"}:
            display_parts.insert(0, style)
        display_name = _title_words(" ".join(display_parts))
        motif_phrase = cosmetic_flora_motif_phrase(flora_motif)
        if motif_phrase:
            display_name += f" With {_title_words(motif_phrase)}"
    appearance = {
        "type": item_id,
        "label": label,
        "slots": list(slots),
        "color": color,
        "color_word": color,
        "material": material,
        "style": style,
        "accent_color": accent,
        "detail": detail,
        "pattern": pattern,
        "emblem": emblem,
        "flora_motif": dict(flora_motif),
        "presentation": presentation,
        "basewear": basewear,
    }
    metadata = {
        "appearance_type": item_id,
        "appearance_label": label,
        "appearance_slots": list(slots),
        "color": color,
        "color_word": color,
        "material": material,
        "style": style,
        "accent_color": accent,
        "detail": detail,
        "pattern": pattern,
        "emblem": emblem,
        "flora_motif": dict(flora_motif),
        "presentation": presentation,
        "basewear": basewear,
        "display_name": display_name,
        APPEARANCE_METADATA_KEY: appearance,
    }
    return with_cosmetic_rarity_metadata(item_id, metadata)


def _starter_basewear_pool(family, slot):
    weighted = []
    for item_id, profile in BASEWEAR_ITEM_IDS.items():
        if slot not in tuple(profile.get("slots", ())):
            continue
        weights = profile.get("starter_weights")
        weights = weights if isinstance(weights, dict) else {}
        weight = int(weights.get(family, 0) or 0)
        if family == "mixed" and weight <= 0:
            weight = 1
        weighted.extend((item_id,) * max(0, weight))
    return tuple(weighted)


STARTER_BASEWEAR_POOLS = {
    family: {
        slot: _starter_basewear_pool(family, slot)
        for slot in BASEWEAR_SLOTS
    }
    for family in ("masc", "femme", "mixed")
}


def _basewear_state_from_metadata(item_id, metadata, *, starter=False):
    item_id = _key(item_id)
    entry = {"item_id": item_id, "metadata": dict(metadata or {})}
    profile = appearance_metadata_for_entry(entry, item_catalog=ITEM_CATALOG)
    slots = tuple(profile.get("slots", ()) or ())
    slot = next((candidate for candidate in slots if candidate in BASEWEAR_SLOTS), "")
    if not slot:
        return {}
    state = {
        "item_id": item_id,
        "appearance_type": _key(profile.get("appearance_type")) or item_id,
        "label": _text(profile.get("label")) or _title_words(item_id),
        "slot": slot,
        "color": _key(profile.get("color")) or "charcoal",
        "color_word": _key(profile.get("color_word") or profile.get("color")) or "charcoal",
        "material": _key(profile.get("material")) or "cotton",
        "style": _key(profile.get("style")) or "plain",
        "detail": _key(profile.get("detail")),
        "pattern": _key(profile.get("pattern")),
        "emblem": _key(profile.get("emblem")),
        "flora_motif": dict(profile.get("flora_motif") or {}) if isinstance(profile.get("flora_motif"), dict) else {},
        "accent_color": _key(profile.get("accent_color")) or fallback_render_key_for_color_word(profile.get("color_word"), default="human_monochrome"),
        "presentation": _key(profile.get("presentation")),
        "basewear": True,
        "starter_basewear": bool(starter),
    }
    state["display_name"] = _title_words(_basewear_phrase(state))
    return state


def _basewear_loose_metadata(state):
    state = dict(state or {})
    item_id = _key(state.get("item_id") or state.get("appearance_type"))
    slot = _key(state.get("slot"))
    label = _text(state.get("label")) or _text(BASEWEAR_ITEM_IDS.get(item_id, {}).get("label")) or _title_words(item_id)
    appearance = {
        "type": _key(state.get("appearance_type")) or item_id,
        "label": label,
        "slots": [slot],
        "color": _key(state.get("color")) or "charcoal",
        "color_word": _key(state.get("color_word") or state.get("color")) or "charcoal",
        "material": _key(state.get("material")) or "cotton",
        "style": _key(state.get("style")) or "plain",
        "detail": _key(state.get("detail")),
        "pattern": _key(state.get("pattern")),
        "emblem": _key(state.get("emblem")),
        "flora_motif": dict(state.get("flora_motif") or {}) if isinstance(state.get("flora_motif"), dict) else {},
        "accent_color": _key(state.get("accent_color")) or "human_monochrome",
        "presentation": _key(state.get("presentation")),
        "basewear": True,
    }
    metadata = {
        "appearance_type": appearance["type"],
        "appearance_label": label,
        "appearance_slots": [slot],
        "color": appearance["color"],
        "color_word": appearance["color_word"],
        "material": appearance["material"],
        "style": appearance["style"],
        "detail": appearance["detail"],
        "pattern": appearance["pattern"],
        "emblem": appearance["emblem"],
        "flora_motif": dict(appearance["flora_motif"]),
        "accent_color": appearance["accent_color"],
        "presentation": appearance["presentation"],
        "basewear": True,
        "display_name": _title_words(_basewear_phrase({**state, "label": label})),
        APPEARANCE_METADATA_KEY: appearance,
    }
    if bool(state.get("starter_basewear")):
        metadata["starter_basewear"] = True
        metadata[APPEARANCE_METADATA_KEY]["starter_basewear"] = True
    return with_cosmetic_rarity_metadata(item_id, metadata)


def basewear_presentation_family(sim, eid):
    """Map the actor's chosen gender identity onto the shared clothing fit family."""
    identity = sim.ecs.get(CreatureIdentity).get(eid) if sim is not None else None
    gender_identity = _key(getattr(identity, "gender_identity", ""))
    if gender_identity == "woman":
        return "femme"
    if gender_identity == "man":
        return "masc"
    return "mixed"


def ensure_player_basewear(sim, eid, *, loadout=None, seed_token=""):
    """Issue the player's starter base garments as ordinary worn items once.

    Older saves may still carry the former intrinsic profile dictionaries in
    ``loadout.basewear``.  They enter the same inventory/equipment path here;
    after that, removing, dropping, selling, and replacing basewear all use the
    ordinary clothing rules.
    """

    if not _is_player_appearance_owner(sim, eid):
        return {}
    if loadout is None:
        loadout = sim.ecs.get(AppearanceLoadout).get(eid)
    if loadout is None:
        return {}
    inventory = _inventory_for(sim, eid)
    if inventory is None:
        return {}

    def _current_profiles():
        profiles = {}
        for current_slot in BASEWEAR_SLOTS:
            instance_id = str(loadout.slots.get(current_slot) or "").strip()
            entry = inventory.find(instance_id=instance_id) if instance_id else None
            profile = appearance_metadata_for_entry(entry) if entry else {}
            if profile:
                profiles[current_slot] = {**dict(profile), "item_id": _key(entry.get("item_id"))}
        return profiles

    current = _current_profiles()
    if bool(getattr(loadout, "basewear_initialized", False)):
        return current

    legacy = AppearanceLoadout._clean_basewear(getattr(loadout, "basewear", None))

    family = basewear_presentation_family(sim, eid)
    pools = STARTER_BASEWEAR_POOLS.get(family, STARTER_BASEWEAR_POOLS["mixed"])
    rng = random.Random(f"player-basewear:{getattr(sim, 'seed', 0)}:{eid}:{family}:{seed_token}")
    issued = dict(current)
    pending = []
    for slot in BASEWEAR_SLOTS:
        if slot in issued:
            continue
        legacy_state = dict(legacy.get(slot) or {})
        if legacy_state:
            item_id = _key(legacy_state.get("item_id") or legacy_state.get("appearance_type"))
            metadata = _basewear_loose_metadata(legacy_state)
        else:
            pool = tuple(pools.get(slot) or STARTER_BASEWEAR_POOLS["mixed"].get(slot) or ())
            if not pool:
                continue
            item_id = rng.choice(pool)
            metadata = cosmetic_variant_metadata(
                item_id,
                seed_token=f"starter-basewear:{getattr(sim, 'seed', 0)}:{eid}:{family}:{slot}:{seed_token}",
                item_catalog=ITEM_CATALOG,
                sim=sim,
            )
            metadata["starter_basewear"] = True
            nested = dict(metadata.get(APPEARANCE_METADATA_KEY) or {})
            nested["starter_basewear"] = True
            metadata[APPEARANCE_METADATA_KEY] = nested
        pending.append([slot, item_id, metadata])

    if pending and not any(
        _key(appearance_metadata_for_entry({"item_id": item_id, "metadata": metadata}).get("emblem"))
        or bool(appearance_metadata_for_entry({"item_id": item_id, "metadata": metadata}).get("flora_motif"))
        for _slot, item_id, metadata in pending
    ):
        target = pending[-1]
        target[2] = dict(target[2])
        target[2]["emblem"] = rng.choice(BASEWEAR_EMBLEMS)
        nested = dict(target[2].get(APPEARANCE_METADATA_KEY) or {})
        nested["emblem"] = target[2]["emblem"]
        target[2][APPEARANCE_METADATA_KEY] = nested

    for slot, item_id, metadata in pending:
        if not item_id:
            continue
        worn_metadata = _metadata_with_worn(metadata, worn=True, slot=slot)
        added, instance_id = inventory.add_item(
            item_id=item_id,
            quantity=1,
            stack_max=ITEM_CATALOG.get(item_id, {}).get("stack_max", 1),
            instance_factory=sim.new_item_instance_id,
            owner_eid=eid,
            owner_tag="player",
            metadata=worn_metadata,
        )
        if not added or not instance_id:
            continue
        loadout.slots[slot] = str(instance_id)

    loadout.basewear = AppearanceLoadout._clean_basewear(None)
    loadout.basewear_initialized = True
    return _current_profiles()


def player_basewear_profile(sim, eid, slot):
    slot = _key(slot)
    if slot not in BASEWEAR_SLOTS:
        return {}
    loadout = appearance_loadout_for(sim, eid, create=True)
    if loadout is None:
        return {}
    inventory = _inventory_for(sim, eid)
    instance_id = str(loadout.slots.get(slot) or "").strip()
    entry = inventory.find(instance_id=instance_id) if inventory is not None and instance_id else None
    profile = appearance_metadata_for_entry(entry) if entry else {}
    return {**dict(profile), "item_id": _key(entry.get("item_id"))} if profile else {}


def replace_player_basewear(sim, eid, instance_id):
    return equip_appearance_item(sim, eid, instance_id)


def tattoo_service_metadata(*, seed_token="", prop=None):
    prop_id = ""
    archetype = ""
    if isinstance(prop, dict):
        prop_id = _text(prop.get("id"))
        metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
        archetype = _key(metadata.get("archetype"))
    rng = random.Random(f"tattoo-service:{prop_id}:{archetype}:{seed_token}")
    slot, location_label = rng.choice(TATTOO_LOCATION_ROWS)
    design = rng.choice(TATTOO_DESIGNS)
    display_name = f"{_title_words(design)} Tattoo - {_title_words(location_label)}"
    return {
        "display_name": display_name,
        "appearance_service": "tattoo",
        "tattoo_design": design,
        "tattoo_slot": slot,
        "tattoo_location": location_label,
        "service_stock": True,
        "non_inventory_service": True,
    }


def apply_tattoo_service(sim, eid, *, design="", slot="", prop=None, source_metadata=None):
    loadout = appearance_loadout_for(sim, eid, create=True)
    if loadout is None:
        return AppearanceEquipResult(False, reason="missing_loadout")
    slot = _key(slot)
    design = _text(design)
    metadata = source_metadata if isinstance(source_metadata, dict) else {}
    if not design:
        design = _text(metadata.get("tattoo_design")) or "linework"
    if slot not in SKIN_MARK_SLOTS:
        return AppearanceEquipResult(False, reason="invalid_tattoo_location")
    existing = dict(getattr(loadout, "skin_marks", {}) or {}).get(slot)
    if isinstance(existing, dict) and _key(existing.get("kind")) == "tattoo":
        return AppearanceEquipResult(False, reason="tattoo_slot_occupied", slot=slot, item_name=design)

    label = _text(metadata.get("tattoo_location")) or SKIN_MARK_SLOT_LABELS.get(slot, slot.replace("_", " ").title()).lower()
    covered = existing if isinstance(existing, dict) and _key(existing.get("kind")) in {"scar", "burn", "nick"} else None
    self_phrase = f"a {_text(design)} tattoo on my {label}"
    if label.startswith("near "):
        self_phrase = f"a {_text(design)} tattoo {label}"
    mark = _skin_mark_entry(
        "tattoo",
        slot,
        description=f"{design} tattoo at {label}",
        self_phrase=self_phrase,
        design=design,
        source="tattoo_parlor",
        covered_mark=covered,
    )
    if not mark:
        return AppearanceEquipResult(False, reason="invalid_tattoo")
    loadout.skin_marks[slot] = mark
    blocked_regions = _makeup_conflict_regions_for_slot(slot)
    for region in blocked_regions:
        loadout.makeup_regions.pop(region, None)
    if blocked_regions and _key(loadout.body_overrides.get("makeup")) not in {"", "none"}:
        loadout.body_overrides["makeup"] = "none"
    sim.emit(Event(
        "appearance_tattoo_applied",
        eid=eid,
        property_id=(prop or {}).get("id") if isinstance(prop, dict) else None,
        tattoo_design=design,
        tattoo_slot=slot,
        tattoo_location=label,
        covered_mark_kind=_key((covered or {}).get("kind")),
        blocked_makeup_regions=tuple(blocked_regions),
    ))
    return AppearanceEquipResult(True, action="tattoo_applied", slot=slot, item_name=f"{design} tattoo")


def _metadata_with_color(metadata, *, color):
    updated = dict(metadata or {})
    color = _key(color) or "charcoal"
    accent = fallback_render_key_for_color_word(color, default="human_monochrome")
    updated["color"] = color
    updated["color_word"] = color
    updated["accent_color"] = accent
    nested = dict(updated.get(APPEARANCE_METADATA_KEY) or {})
    nested["color"] = color
    nested["color_word"] = color
    nested["accent_color"] = accent
    updated[APPEARANCE_METADATA_KEY] = nested
    item_id = _key(updated.get("appearance_type") or nested.get("type"))
    label = _text(updated.get("appearance_label") or nested.get("label") or item_id)
    material = _text(updated.get("material") or nested.get("material"))
    style = _text(updated.get("style") or nested.get("style"))
    if item_id in BASEWEAR_ITEM_IDS:
        updated["display_name"] = _title_words(_basewear_phrase(appearance_metadata_for_entry({"item_id": item_id, "metadata": updated})))
    else:
        display_parts = [color, material, label]
        if style and style not in {"plain", "simple"}:
            display_parts.insert(0, style)
        updated["display_name"] = _title_words(" ".join(part for part in display_parts if part))
        motif_phrase = cosmetic_flora_motif_phrase(updated.get("flora_motif") or nested.get("flora_motif"))
        if motif_phrase:
            updated["display_name"] += f" With {_title_words(motif_phrase)}"
    return updated


def _starter_outfit_color(sim, eid, identity, rng):
    return choose_appearance_color_word(rng, slots=("top", "starter"))


NPC_BODYGUARD_COLOR_BUCKETS = {
    "outer": ("black", "charcoal", "onyx", "navy", "slate", "forest"),
    "top": ("black", "charcoal", "smoke", "slate", "olive", "gray"),
    "bottom": ("black", "charcoal", "navy", "slate", "forest"),
    "shoes": ("black", "charcoal", "onyx", "navy"),
    "accessory": ("steel", "silver", "onyx"),
}


def _description_color_for(profile, slot, rng, item_id="", role="", career=""):
    role_key = _key(role)
    career_key = _key(career)
    if role_key == "guard" and "bodyguard" in career_key:
        bucket_key = "accessory" if slot in {"hat", "earrings", "necklace", "bracelet", "ring_left", "ring_right"} else slot
        options = tuple(NPC_BODYGUARD_COLOR_BUCKETS.get(bucket_key) or NPC_BODYGUARD_COLOR_BUCKETS.get("top") or ("charcoal",))
        return rng.choice(options)
    bucket_key = "accessory" if slot in {"hat", "earrings", "necklace", "bracelet", "ring_left", "ring_right"} else slot
    color = choose_appearance_color_word(rng, slots=(bucket_key, _key(item_id)))
    if _key(item_id) == "jacket" and "denim" in _key((profile or {}).get("attire_compact")):
        color = "denim"
    if _key(item_id) == "ring" and "silver" in _key((profile or {}).get("accessory_compact")):
        color = "silver"
    return color


def employer_clothing_culture_for_actor(sim, eid):
    """Return an actor's durable employer dress grammar and adoption read."""

    if sim is None or eid is None:
        return {}
    occupation = sim.ecs.get(Occupation).get(eid)
    workplace = getattr(occupation, "workplace", None) if occupation is not None else None
    raw_org_eid = workplace.get("organization_eid") if isinstance(workplace, dict) else None
    try:
        organization_eid = int(raw_org_eid) if raw_org_eid is not None else None
    except (TypeError, ValueError):
        organization_eid = None
    if organization_eid is None:
        membership = primary_actor_membership(sim, eid)
        if isinstance(membership, dict) and _key(membership.get("kind")) in {"employment", "ownership"}:
            try:
                organization_eid = int(membership.get("organization_eid"))
            except (TypeError, ValueError):
                organization_eid = None
    if organization_eid is None:
        return {}
    culture = organization_clothing_culture(sim, organization_eid)
    if not culture:
        return {}
    cohesion = max(0.0, min(1.0, float(culture.get("cohesion", 0.0) or 0.0)))
    adoption_rng = random.Random(
        f"employer-clothing-adoption:{getattr(sim, 'seed', 0)}:{eid}:{culture.get('signature', '')}"
    )
    result = dict(culture)
    result["adopted"] = adoption_rng.random() <= cohesion
    return result


def _metadata_with_employer_clothing_culture(metadata, culture, *, slot, show_motif=False):
    culture = dict(culture or {})
    signature = _text(culture.get("signature"))
    if not signature:
        return dict(metadata or {})
    row = {
        "signature": signature,
        "organization_eid": culture.get("organization_eid"),
        "organization_name": _text(culture.get("organization_name")),
        "family": _key(culture.get("family")),
        "motif": _text(culture.get("motif")),
        "slot": _key(slot),
        "recognition_salience": round(max(0.0, min(1.0, float(culture.get("recognition_salience", 0.0) or 0.0))), 3),
        "primary_color_word": _key(culture.get("primary_color_word")),
        "secondary_color_word": _key(culture.get("secondary_color_word")),
        "accent_color_word": _key(culture.get("accent_color_word")),
    }
    updated = dict(metadata or {})
    nested = dict(updated.get(APPEARANCE_METADATA_KEY) or {})
    updated[EMPLOYER_CLOTHING_CULTURE_METADATA_KEY] = row
    nested[EMPLOYER_CLOTHING_CULTURE_METADATA_KEY] = row
    if show_motif and row["motif"]:
        # One actual garment carries the house mark.  Keeping it in the normal
        # emblem channel makes the culture visible in item prose and pygame's
        # existing clothing-detail pixels instead of only storing a matcher tag.
        updated["emblem"] = row["motif"]
        nested["emblem"] = row["motif"]
    updated[APPEARANCE_METADATA_KEY] = nested
    return updated


def _metadata_with_personal_clothing_token(metadata, *, sim, eid, slot, item_id, motif, salience):
    identity = sim.ecs.get(CreatureIdentity).get(eid) if sim is not None else None
    owner_name = _text(getattr(identity, "personal_name", ""))
    signature_rng = random.Random(
        f"personal-clothing-token:{getattr(sim, 'seed', 0)}:{eid}:{slot}:{item_id}:{owner_name}"
    )
    row = {
        "signature": f"personal-token:{eid}:{signature_rng.getrandbits(56):014x}",
        "owner_eid": int(eid),
        "owner_name": owner_name,
        "usual": True,
        "slot": _key(slot),
        "item_id": _key(item_id),
        "motif": _text(motif),
        "salience": round(max(0.0, min(1.0, float(salience or 0.0))), 3),
    }
    updated = dict(metadata or {})
    nested = dict(updated.get(APPEARANCE_METADATA_KEY) or {})
    updated[PERSONAL_CLOTHING_TOKEN_METADATA_KEY] = row
    updated["personal_token_owner_eid"] = int(eid)
    nested[PERSONAL_CLOTHING_TOKEN_METADATA_KEY] = row
    nested["personal_token_owner_eid"] = int(eid)
    if motif:
        updated["emblem"] = _text(motif)
        nested["emblem"] = _text(motif)
    updated[APPEARANCE_METADATA_KEY] = nested
    return updated


def _appearance_slot_for_item(item_id, loadout):
    slots = tuple(COSMETIC_ITEM_IDS.get(_key(item_id), {}).get("slots", ()) or ())
    if set(slots) == {"ring_left", "ring_right"}:
        return "ring_right" if loadout.slots.get("ring_left") else "ring_left"
    return slots[0] if slots else ""


def _npc_has_described_outfit(inventory):
    if inventory is None:
        return False
    for entry in tuple(getattr(inventory, "items", ()) or ()):
        metadata = entry.get("metadata") if isinstance(entry, dict) else {}
        if isinstance(metadata, dict) and metadata.get(NPC_DESCRIBED_OUTFIT_METADATA_KEY):
            return True
    return False


def _description_item_metadata(item_id, *, color, profile, slot, seed_token, sim=None):
    metadata = cosmetic_variant_metadata(item_id, seed_token=seed_token, item_catalog=ITEM_CATALOG, sim=sim)
    metadata = _metadata_with_color(metadata, color=color)
    metadata = _metadata_with_worn(metadata, worn=True, slot=slot)
    metadata[NPC_DESCRIBED_OUTFIT_METADATA_KEY] = True
    metadata["described_outfit"] = True
    metadata["ambient_spawn"] = True
    metadata["source"] = NPC_DESCRIBED_OUTFIT_SOURCE
    metadata["description_seed_token"] = _text((profile or {}).get("seed_token"))
    metadata["description_attire_compact"] = _text((profile or {}).get("attire_compact"))
    metadata["description_accessory_compact"] = _text((profile or {}).get("accessory_compact"))
    nested = dict(metadata.get(APPEARANCE_METADATA_KEY) or {})
    nested[NPC_DESCRIBED_OUTFIT_METADATA_KEY] = True
    nested["described_outfit"] = True
    nested["source"] = NPC_DESCRIBED_OUTFIT_SOURCE
    metadata[APPEARANCE_METADATA_KEY] = nested
    return metadata


def seed_npc_described_outfit(sim, eid, *, seed_token=""):
    loadout = appearance_loadout_for(sim, eid, create=True)
    inventory = _inventory_for(sim, eid)
    if loadout is None or inventory is None:
        return ()
    if _npc_has_described_outfit(inventory):
        return ()

    identity = sim.ecs.get(CreatureIdentity).get(eid) if sim is not None else None
    profile = build_human_description_profile(
        getattr(sim, "seed", 0),
        eid=eid,
        identity=identity,
        personal_name=getattr(identity, "personal_name", None),
    )
    if not isinstance(profile, dict):
        return ()

    attire_key = _key(profile.get("attire_compact"))
    accessory_key = _key(profile.get("accessory_compact"))
    item_ids = list(NPC_DESCRIPTION_ATTIRE_ITEMS.get(attire_key, ("jacket", "tee", "trousers", "boots")))
    for item_id in NPC_DESCRIPTION_ACCESSORY_ITEMS.get(accessory_key, ()):
        if item_id not in item_ids:
            item_ids.append(item_id)

    rng = random.Random(f"npc-described-outfit:{getattr(sim, 'seed', 0)}:{eid}:{seed_token}:{profile.get('seed_token')}")
    ai = sim.ecs.get(AI).get(eid) if sim is not None else None
    occupation = sim.ecs.get(Occupation).get(eid) if sim is not None else None
    role = _key(getattr(ai, "role", ""))
    career = _key(getattr(occupation, "career", ""))
    employer_culture = employer_clothing_culture_for_actor(sim, eid)
    culture_adopted = bool(employer_culture.get("adopted", False))
    signature_slots = tuple(_key(slot) for slot in tuple(employer_culture.get("signature_slots", ()) or ()))

    token_rng = random.Random(
        f"npc-personal-clothing-token:{getattr(sim, 'seed', 0)}:{eid}:{seed_token}:{profile.get('seed_token')}"
    )
    personal_token_item_id = ""
    personal_token_motif = ""
    personal_token_salience = 0.0
    if token_rng.random() < 0.38:
        existing_tokens = [item_id for item_id in item_ids if _key(item_id) in PERSONAL_TOKEN_ITEMS]
        personal_token_item_id = _key(token_rng.choice(existing_tokens or PERSONAL_TOKEN_ITEMS))
        if personal_token_item_id not in item_ids:
            item_ids.append(personal_token_item_id)
        personal_token_motif = token_rng.choice(PERSONAL_TOKEN_MOTIFS)
        personal_token_salience = round(token_rng.uniform(0.72, 0.98), 3)

    seeded = []
    culture_piece_index = 0
    for item_id in item_ids:
        item_id = _key(item_id)
        item_def = ITEM_CATALOG.get(item_id)
        if not item_def or item_id not in COSMETIC_ITEM_IDS:
            continue
        slot = _appearance_slot_for_item(item_id, loadout)
        if slot not in APPEARANCE_SLOTS:
            continue
        if loadout.slots.get(slot):
            continue
        if any(loadout.slots.get(conflict) for conflict in _slot_conflicts(slot)):
            continue
        culture_slot = "accessory" if slot in {"hat", "earrings", "necklace", "bracelet", "ring_left", "ring_right"} else slot
        carries_culture = bool(culture_adopted and culture_slot in signature_slots)
        is_personal_token = bool(personal_token_item_id and item_id == personal_token_item_id)
        color = _description_color_for(profile, slot, rng, item_id=item_id, role=role, career=career)
        if carries_culture:
            culture_colors = (
                _key(employer_culture.get("primary_color_word")),
                _key(employer_culture.get("secondary_color_word")),
                _key(employer_culture.get("accent_color_word")),
            )
            color = culture_colors[min(culture_piece_index, len(culture_colors) - 1)] or color
            culture_piece_index += 1
        elif is_personal_token and employer_culture:
            color = _key(employer_culture.get("accent_color_word")) or color
        metadata = _description_item_metadata(
            item_id,
            color=color,
            profile=profile,
            slot=slot,
            seed_token=f"{seed_token}:{eid}:{item_id}:{slot}",
            sim=sim,
        )
        if carries_culture:
            metadata = _metadata_with_employer_clothing_culture(
                metadata,
                employer_culture,
                slot=slot,
                show_motif=culture_piece_index == 1,
            )
        if is_personal_token:
            metadata = _metadata_with_personal_clothing_token(
                metadata,
                sim=sim,
                eid=eid,
                slot=slot,
                item_id=item_id,
                motif=personal_token_motif,
                salience=personal_token_salience,
            )
        added, instance_id = inventory.add_item(
            item_id=item_id,
            quantity=1,
            stack_max=item_def.get("stack_max", 1),
            instance_factory=sim.new_item_instance_id,
            owner_eid=eid,
            owner_tag="npc",
            metadata=metadata,
        )
        if not added or not instance_id:
            continue
        loadout.slots[slot] = str(instance_id).strip()
        record_cosmetic_popularity(
            sim,
            item_id,
            metadata,
            source="npc",
            source_token=f"described:{eid}",
        )
        seeded.append({
            "item_id": item_id,
            "instance_id": str(instance_id),
            "slot": slot,
            "item_name": item_display_name(item_id, metadata=metadata, item_catalog=ITEM_CATALOG),
            "attire_compact": attire_key,
            "accessory_compact": accessory_key,
            "employer_clothing_culture": bool(carries_culture),
            "personal_clothing_token": bool(is_personal_token),
        })
    return tuple(seeded)


def seed_npc_appearance_from_description(sim, eid, *, seed_token=""):
    innate_seeded = seed_npc_innate_appearance_from_description(sim, eid, seed_token=seed_token)
    outfit_rows = seed_npc_described_outfit(sim, eid, seed_token=seed_token)
    return {
        "innate_seeded": bool(innate_seeded),
        "outfit_rows": tuple(outfit_rows),
    }


def seed_player_starting_outfit(sim, eid, *, seed_token=""):
    loadout = appearance_loadout_for(sim, eid, create=True)
    inventory = _inventory_for(sim, eid)
    if loadout is None or inventory is None:
        return ()
    # Player and NPC icons read the same persisted outward-presentation fields.
    # Despite its historical name, this helper contains no NPC-only behavior.
    seed_npc_innate_appearance_from_description(sim, eid, seed_token=seed_token)
    if loadout.slots.get("full_body") or loadout.slots.get("top") or loadout.slots.get("bottom") or loadout.slots.get("shoes"):
        return ()

    identity = sim.ecs.get(CreatureIdentity).get(eid) if sim is not None else None
    rng = random.Random(f"starter-outfit:{getattr(sim, 'seed', 0)}:{eid}:{seed_token}")
    outfit_color = _starter_outfit_color(sim, eid, identity, rng)
    rows = (
        (rng.choice(("tee", "button_up", "button_up")), outfit_color),
        ("trousers", outfit_color if rng.random() < 0.35 else choose_appearance_color_word(rng, slots=("bottom", "starter"))),
        (rng.choice(("sneakers", "boots")), choose_appearance_color_word(rng, slots=("shoes", "starter"))),
    )

    seeded = []
    for item_id, color in rows:
        item_def = ITEM_CATALOG.get(item_id)
        if not item_def:
            continue
        metadata = cosmetic_variant_metadata(
            item_id,
            seed_token=f"{seed_token}:{item_id}",
            item_catalog=ITEM_CATALOG,
            sim=sim,
        )
        metadata = _metadata_with_color(metadata, color=color)
        metadata["starter_item"] = True
        metadata["starter_outfit"] = True
        nested = dict(metadata.get(APPEARANCE_METADATA_KEY) or {})
        nested["starter_outfit"] = True
        metadata[APPEARANCE_METADATA_KEY] = nested
        added, instance_id = inventory.add_item(
            item_id=item_id,
            quantity=1,
            stack_max=item_def.get("stack_max", 1),
            instance_factory=sim.new_item_instance_id,
            owner_eid=eid,
            owner_tag="player" if eid == getattr(sim, "player_eid", None) else "npc",
            metadata=metadata,
        )
        if not added or not instance_id:
            continue
        result = equip_appearance_item(sim, eid, instance_id, record_fashion=False)
        if bool(getattr(result, "ok", False)):
            seeded.append({
                "item_id": item_id,
                "instance_id": instance_id,
                "slot": getattr(result, "slot", ""),
                "item_name": getattr(result, "item_name", ""),
            })
    return tuple(seeded)


def _metadata_with_worn(metadata, *, worn, slot=None):
    updated = dict(metadata or {})
    nested = dict(updated.get(APPEARANCE_METADATA_KEY) or {})
    if worn:
        updated[APPEARANCE_WORN_METADATA_KEY] = True
        if slot:
            updated[APPEARANCE_SLOT_METADATA_KEY] = str(slot)
            nested["worn_slot"] = str(slot)
    else:
        updated.pop(APPEARANCE_WORN_METADATA_KEY, None)
        updated.pop(APPEARANCE_SLOT_METADATA_KEY, None)
        nested.pop("worn_slot", None)
    if nested:
        updated[APPEARANCE_METADATA_KEY] = nested
    return updated


def mark_inventory_instance_worn(sim, eid, instance_id, *, worn, slot=None):
    inventory = _inventory_for(sim, eid)
    if inventory is None:
        return False
    entry = inventory.find(instance_id=instance_id)
    if entry is None:
        return False
    metadata = _metadata_with_worn(entry.get("metadata"), worn=bool(worn), slot=slot)
    inventory.update_item_metadata(instance_id, metadata=metadata, replace=True)
    return True


def appearance_metadata_as_loose_item(metadata):
    return _metadata_with_worn(metadata, worn=False)


def _find_entry_by_instance(sim, eid, instance_id):
    inventory = _inventory_for(sim, eid)
    if inventory is None:
        return None, None
    return inventory, inventory.find(instance_id=instance_id)


def _display_name(sim, eid, entry):
    try:
        return item_display_name_for_actor(sim, eid, entry, item_catalog=ITEM_CATALOG)
    except Exception:
        return item_display_name(entry.get("item_id"), metadata=entry.get("metadata"), item_catalog=ITEM_CATALOG)


def _slot_conflicts(slot):
    if slot == "full_body":
        return ("top", "bottom")
    if slot in {"top", "bottom"}:
        return ("full_body",)
    return ()


def _pick_target_slot(loadout, slots, preferred_slot=None):
    preferred = _key(preferred_slot)
    slots = tuple(slots or ())
    if preferred in slots:
        return preferred
    if set(slots) == {"ring_left", "ring_right"}:
        for slot in ("ring_left", "ring_right"):
            if not loadout.slots.get(slot):
                return slot
        return "ring_left"
    for slot in slots:
        if not loadout.slots.get(slot):
            return slot
    return slots[0] if slots else ""


def _pack_has_room_to_unwear(inventory, entry):
    metadata = _metadata_with_worn(entry.get("metadata"), worn=False)
    cost = item_inventory_slot_cost({
        "item_id": entry.get("item_id"),
        "metadata": metadata,
    })
    return (inventory.slot_count() + int(max(0, cost))) <= int(getattr(inventory, "capacity", 0) or 0)


def _release_active_container_for_unworn_item(sim, eid, instance_id, *, item_name="", reason="appearance_unequipped"):
    current = getattr(sim, "equipped_container", None)
    if not isinstance(current, dict):
        return None
    instance_id = str(instance_id or "").strip()
    if not instance_id or str(current.get("instance_id", "") or "").strip() != instance_id:
        return None

    from game.system_support.container_runtime import release_stowed_items_for_removed_container

    inventory = sim.ecs.get(Inventory).get(eid)
    try:
        bonus_slots = int(max(0, int(current.get("bonus_slots", 0) or 0)))
    except (TypeError, ValueError):
        bonus_slots = 0
    sim.equipped_container = None
    release = {"released": 0, "dropped": 0, "ground_item_ids": ()}
    if inventory:
        inventory.capacity = max(1, int(getattr(inventory, "capacity", 1) or 1) - bonus_slots)
        release = release_stowed_items_for_removed_container(sim, eid, inventory, instance_id)
    sim.emit(Event(
        "container_removed",
        eid=eid,
        item_id=current.get("item_id"),
        item_name=current.get("item_name") or item_name,
        reason=reason,
        released_container_items=release.get("released", 0),
        dropped_container_items=release.get("dropped", 0),
        dropped_container_ground_item_ids=release.get("ground_item_ids", ()),
    ))
    return release


def equip_appearance_item(sim, eid, instance_id, preferred_slot=None, *, record_fashion=True):
    loadout = appearance_loadout_for(sim, eid, create=True)
    inventory, entry = _find_entry_by_instance(sim, eid, instance_id)
    if loadout is None or inventory is None or entry is None:
        return AppearanceEquipResult(False, reason="missing_item")
    item_name = _display_name(sim, eid, entry)
    if is_entry_worn(entry):
        slot = _key(_entry_metadata(entry).get(APPEARANCE_SLOT_METADATA_KEY))
        if not slot:
            for candidate, candidate_id in loadout.slots.items():
                if str(candidate_id or "").strip() == str(instance_id or "").strip():
                    slot = candidate
                    break
        if slot:
            return unequip_appearance_slot(sim, eid, slot)
    if not is_appearance_item(entry):
        return AppearanceEquipResult(False, reason="not_appearance_item", item_name=item_name)

    profile = appearance_metadata_for_entry(entry)
    slots = tuple(profile.get("slots", ()) or ())
    target_slot = _pick_target_slot(loadout, slots, preferred_slot=preferred_slot)
    if target_slot not in APPEARANCE_SLOTS:
        return AppearanceEquipResult(False, reason="invalid_slot", item_name=item_name)

    armor = sim.ecs.get(ArmorLoadout).get(eid)
    armor_slot = str(getattr(armor, "slot", "body") or "body").strip().lower() if armor else ""
    if target_slot == "outer" and armor and getattr(armor, "equipped_instance_id", None) and armor_slot == "body":
        return AppearanceEquipResult(False, reason="armor_outer_active", slot=target_slot, item_name=item_name)

    occupied = loadout.slots.get(target_slot)
    if occupied and str(occupied).strip() != str(instance_id).strip():
        return AppearanceEquipResult(False, reason="slot_occupied", slot=target_slot, item_name=item_name)
    for conflict in _slot_conflicts(target_slot):
        if loadout.slots.get(conflict):
            return AppearanceEquipResult(False, reason=f"conflicts_{conflict}", slot=target_slot, item_name=item_name)

    loadout.slots[target_slot] = str(instance_id).strip()
    metadata = _metadata_with_worn(entry.get("metadata"), worn=True, slot=target_slot)
    inventory.update_item_metadata(instance_id, metadata=metadata, replace=True)
    if record_fashion:
        record_cosmetic_popularity(
            sim,
            entry.get("item_id"),
            metadata,
            source="player" if _is_player_appearance_owner(sim, eid) else "npc",
            source_token=f"equipped:{eid}",
        )
    sim.emit(Event(
        "appearance_item_equipped",
        eid=eid,
        item_id=entry.get("item_id"),
        instance_id=str(instance_id),
        item_name=item_name,
        slot=target_slot,
    ))
    return AppearanceEquipResult(True, action="equipped", slot=target_slot, item_name=item_name)


def unequip_appearance_slot(sim, eid, slot):
    slot = _key(slot)
    loadout = appearance_loadout_for(sim, eid, create=False)
    if loadout is None or slot not in APPEARANCE_SLOTS:
        return AppearanceEquipResult(False, reason="invalid_slot", slot=slot)
    instance_id = str(loadout.slots.get(slot) or "").strip()
    if not instance_id:
        return AppearanceEquipResult(False, reason="empty_slot", slot=slot)
    inventory, entry = _find_entry_by_instance(sim, eid, instance_id)
    if inventory is None or entry is None:
        loadout.slots[slot] = None
        return AppearanceEquipResult(True, action="cleared_missing", slot=slot)
    item_name = _display_name(sim, eid, entry)
    if not _pack_has_room_to_unwear(inventory, entry):
        return AppearanceEquipResult(False, reason="pack_full", slot=slot, item_name=item_name)
    metadata = _metadata_with_worn(entry.get("metadata"), worn=False)
    inventory.update_item_metadata(instance_id, metadata=metadata, replace=True)
    loadout.slots[slot] = None
    _release_active_container_for_unworn_item(
        sim,
        eid,
        instance_id,
        item_name=item_name,
        reason="appearance_unequipped",
    )
    sim.emit(Event(
        "appearance_item_unequipped",
        eid=eid,
        item_id=entry.get("item_id"),
        instance_id=instance_id,
        item_name=item_name,
        slot=slot,
    ))
    return AppearanceEquipResult(True, action="unequipped", slot=slot, item_name=item_name)


def clear_appearance_instance(sim, eid, instance_id, *, clear_inventory_metadata=True):
    loadout = appearance_loadout_for(sim, eid, create=False)
    if loadout is None:
        return None
    instance_id = str(instance_id or "").strip()
    if not instance_id:
        return None
    cleared_slot = None
    for slot, worn_id in list(loadout.slots.items()):
        if str(worn_id or "").strip() == instance_id:
            loadout.slots[slot] = None
            cleared_slot = slot
    if clear_inventory_metadata:
        mark_inventory_instance_worn(sim, eid, instance_id, worn=False)
    return cleared_slot


def clear_removed_entry_appearance(sim, eid, removed_entry):
    if not isinstance(removed_entry, dict):
        return {}
    instance_id = str(removed_entry.get("instance_id", "") or "").strip()
    if not instance_id:
        return {}
    slot = clear_appearance_instance(sim, eid, instance_id, clear_inventory_metadata=False)
    metadata = _metadata_with_worn(removed_entry.get("metadata"), worn=False)
    removed_entry["metadata"] = metadata
    if not slot:
        return {}
    return {
        "appearance_slot": slot,
        "appearance_name": item_display_name(
            removed_entry.get("item_id"),
            metadata=metadata,
            item_catalog=ITEM_CATALOG,
        ),
    }


def stow_cosmetic_outer_for_armor(sim, eid):
    loadout = appearance_loadout_for(sim, eid, create=False)
    if loadout is None:
        return AppearanceEquipResult(True, action="none", slot="outer")
    if not loadout.slots.get("outer"):
        return AppearanceEquipResult(True, action="none", slot="outer")
    return unequip_appearance_slot(sim, eid, "outer")


def appearance_worn_instance_ids(sim, eid):
    loadout = appearance_loadout_for(sim, eid, create=False)
    if loadout is None:
        return set()
    return set(loadout.worn_instance_ids())


def public_exposure_profile(sim, eid):
    """Describe visible clothing coverage without inferring hidden garments."""

    loadout = appearance_loadout_for(sim, eid, create=False)
    if loadout is None:
        return {
            "level": "unknown",
            "label": "clothing state unavailable",
            "indecent": False,
            "offense_score": 0,
            "uncovered": (),
            "visible_basewear": (),
            "covered": {},
            "basewear": {},
        }
    slots = dict(getattr(loadout, "slots", {}) or {}) if loadout is not None else {}
    armor = sim.ecs.get(ArmorLoadout).get(eid) if sim is not None else None
    body_armor = bool(
        armor is not None
        and getattr(armor, "equipped_instance_id", None)
        and str(getattr(armor, "slot", "body") or "body").strip().lower() == "body"
    )
    full_body = bool(str(slots.get("full_body") or "").strip()) or body_armor
    covered = {
        "top": full_body or bool(str(slots.get("top") or "").strip()),
        "bottom": full_body or bool(str(slots.get("bottom") or "").strip()),
    }
    base = {
        "top": bool(str(slots.get("base_top") or "").strip()),
        "bottom": bool(str(slots.get("base_bottom") or "").strip()),
    }
    uncovered = tuple(part for part in ("top", "bottom") if not covered[part] and not base[part])
    visible_basewear = tuple(part for part in ("top", "bottom") if not covered[part] and base[part])
    if uncovered:
        level = "uncovered"
        label = "partly or fully unclothed"
        offense_score = 30
    elif visible_basewear:
        level = "basewear_only"
        label = "wearing exposed basewear"
        offense_score = 18
    else:
        level = "dressed"
        label = "dressed"
        offense_score = 0
    return {
        "level": level,
        "label": label,
        "indecent": level != "dressed",
        "offense_score": offense_score,
        "uncovered": uncovered,
        "visible_basewear": visible_basewear,
        "covered": dict(covered),
        "basewear": dict(base),
    }


def _indefinite_article_phrase(text):
    text = str(text or "").strip()
    if not text:
        return ""
    lowered = text.lower()
    if lowered.startswith(("a ", "an ", "the ", "some ", "one ")):
        return text
    article = "an" if lowered[:1] in {"a", "e", "i", "o", "u"} else "a"
    return f"{article} {text}"


def _entry_phrase(entry, *, compact=False, article=False):
    profile = appearance_metadata_for_entry(entry)
    if not profile:
        return ""
    if bool(profile.get("basewear")):
        phrase = _basewear_phrase(profile)
        appearance_type = _key(profile.get("appearance_type") or profile.get("type"))
        if article and appearance_type not in ARTICLELESS_APPEARANCE_TYPES:
            return _indefinite_article_phrase(phrase)
        return phrase
    color_key = profile.get("color_word") or profile.get("color", "")
    color = color_word_display_name(color_key, default=str(color_key or ""))
    material = profile.get("material", "")
    style = profile.get("style", "")
    label = profile.get("label", "")
    bits = []
    if style and style not in {"plain", "simple"}:
        bits.append(style)
    if color:
        bits.append(color)
    if material and not compact:
        bits.append(material)
    if label:
        bits.append(label)
    phrase = " ".join(bit for bit in bits if bit)
    motif_phrase = cosmetic_flora_motif_phrase(profile.get("flora_motif"))
    if motif_phrase:
        phrase += f" with {motif_phrase}"
    appearance_type = _key(profile.get("appearance_type") or profile.get("type"))
    if article and appearance_type not in ARTICLELESS_APPEARANCE_TYPES:
        return _indefinite_article_phrase(phrase)
    return phrase


def _entry_display_part(entry, *, compact=False, article=False, fallback_color=None):
    phrase = _entry_phrase(entry, compact=compact, article=article)
    if not phrase:
        return None
    profile = appearance_metadata_for_entry(entry)
    metadata = _entry_metadata(entry)
    color_word = _key(
        (profile or {}).get("color_word")
        or (profile or {}).get("color")
        or metadata.get("color_word")
        or metadata.get("color")
    )
    color = render_key_for_color_word(color_word, default=None) if color_word else None
    if not color:
        color = _key((profile or {}).get("accent_color") or metadata.get("accent_color")) or fallback_color
    return {
        "text": phrase,
        "color": color,
        "color_word": color_word or None,
    }


def _join_with_and(parts):
    bits = [str(part).strip() for part in tuple(parts or ()) if str(part).strip()]
    if not bits:
        return ""
    if len(bits) == 1:
        return bits[0]
    if len(bits) == 2:
        return f"{bits[0]} and {bits[1]}"
    return f"{', '.join(bits[:-1])}, and {bits[-1]}"


def _entry_for_slot(sim, eid, slot):
    loadout = appearance_loadout_for(sim, eid, create=False)
    if loadout is None:
        return None
    instance_id = str(loadout.slots.get(slot) or "").strip()
    if not instance_id:
        return None
    inventory = _inventory_for(sim, eid)
    return inventory.find(instance_id=instance_id) if inventory else None


def _basewear_display_part(sim, eid, slot, *, article=True):
    state = player_basewear_profile(sim, eid, slot)
    if not state:
        return None
    phrase = _basewear_phrase(state)
    appearance_type = _key(state.get("appearance_type") or state.get("item_id"))
    if article and appearance_type not in ARTICLELESS_APPEARANCE_TYPES:
        phrase = _indefinite_article_phrase(phrase)
    color_word = _key(state.get("color_word") or state.get("color"))
    color = render_key_for_color_word(color_word, default=None) if color_word else None
    return {
        "text": phrase,
        "color": color or _key(state.get("accent_color")) or "human_monochrome",
        "color_word": color_word or None,
    }


def _outfit_display_parts(sim, eid):
    loadout = appearance_loadout_for(sim, eid, create=False)
    if loadout is None:
        return []
    parts = []
    full_body = _entry_for_slot(sim, eid, "full_body")
    if full_body:
        part = _entry_display_part(full_body, article=True)
        if part:
            parts.append(part)
    else:
        top = _entry_for_slot(sim, eid, "top")
        bottom = _entry_for_slot(sim, eid, "bottom")
        top_part = _entry_display_part(top, article=True) if top else None
        bottom_part = _entry_display_part(bottom, article=True) if bottom else None
        if not top_part:
            top_part = _basewear_display_part(sim, eid, "base_top", article=True)
        if not bottom_part:
            bottom_part = _basewear_display_part(sim, eid, "base_bottom", article=True)
        if top_part:
            parts.append(top_part)
        if bottom_part:
            parts.append(bottom_part)
    outer = _entry_for_slot(sim, eid, "outer")
    if outer:
        part = _entry_display_part(outer, article=True)
        if part:
            parts.append(part)
    armor = sim.ecs.get(ArmorLoadout).get(eid) if sim is not None else None
    if armor and getattr(armor, "equipped_instance_id", None):
        name = _text(getattr(armor, "equipped_name", None) or getattr(armor, "equipped_item_id", "armor"))
        if name:
            inventory = _inventory_for(sim, eid)
            armor_entry = inventory.find(instance_id=armor.equipped_instance_id) if inventory else None
            armor_part = _entry_display_part(armor_entry, article=False, fallback_color="item_armor") if armor_entry else None
            parts.append(armor_part or {"text": name, "color": "item_armor", "color_word": None})
    shoes = _entry_for_slot(sim, eid, "shoes")
    if shoes:
        part = _entry_display_part(shoes, article=True)
        if part:
            parts.append(part)
    return parts


def _outfit_parts(sim, eid):
    return [str(part.get("text", "")) for part in _outfit_display_parts(sim, eid) if str(part.get("text", ""))]


def _outfit_sentence(sim, eid):
    parts = _outfit_parts(sim, eid)
    if not parts:
        return ""
    if len(parts) == 1:
        return f"I am wearing {parts[0]}."
    return f"I am wearing {', '.join(parts[:-1])}, and {parts[-1]}."


def _adornment_display_parts(sim, eid):
    bits = []
    for slot in ("hat", "earrings", "necklace", "bracelet", "ring_left", "ring_right"):
        entry = _entry_for_slot(sim, eid, slot)
        if not entry:
            continue
        part = _entry_display_part(entry, compact=True, article=True)
        if part:
            bits.append(part)
    return bits


def _adornment_parts(sim, eid):
    return [str(part.get("text", "")) for part in _adornment_display_parts(sim, eid) if str(part.get("text", ""))]


def _adornment_sentence(sim, eid):
    bits = _adornment_parts(sim, eid)
    if not bits:
        return ""
    if len(bits) == 1:
        return f"I have {bits[0]} on."
    return f"I have {', '.join(bits[:-1])}, and {bits[-1]} on."


def _skin_mark_phrase(mark, *, possessive_adj="my", first_person=True):
    if not isinstance(mark, dict):
        return ""
    phrase = _text(mark.get("self_phrase")) if first_person else ""
    if phrase:
        return phrase
    if not first_person:
        phrase = _text(mark.get("description"))
        if phrase:
            return phrase
    kind = _key(mark.get("kind")) or "mark"
    design = _text(mark.get("design"))
    slot = _key(mark.get("slot"))
    label = SKIN_MARK_SLOT_LABELS.get(slot, slot.replace("_", " ").title()).lower()
    if kind == "tattoo":
        return f"a {design or 'linework'} tattoo on {possessive_adj} {label}"
    if kind == "burn":
        return f"an old burn mark near {possessive_adj} {label}"
    if kind == "nick":
        return f"a nick at {possessive_adj} {label}"
    if kind == "scar":
        return f"a scar at {possessive_adj} {label}"
    return _text(mark.get("description"))


def _skin_mark_sentence(loadout, *, subject="I", possessive_adj="my", have="have", first_person=True):
    marks = dict(getattr(loadout, "skin_marks", {}) or {})
    if not marks:
        return ""
    phrases = []
    coverups = []
    for slot in SKIN_MARK_SLOTS:
        mark = marks.get(slot)
        if not isinstance(mark, dict):
            continue
        phrase = _skin_mark_phrase(mark, possessive_adj=possessive_adj, first_person=first_person)
        if phrase:
            phrases.append(phrase)
        covered = mark.get("covered_mark") if isinstance(mark.get("covered_mark"), dict) else None
        if _key(mark.get("kind")) == "tattoo" and covered:
            covered_kind = _key(covered.get("kind")) or "mark"
            coverups.append(f"it covers an older {covered_kind}")
    if not phrases:
        return ""
    sentence = f"{subject} have {_join_with_and(phrases)}." if first_person else f"{subject} {have} {_join_with_and(phrases)}."
    if coverups:
        sentence = f"{sentence[:-1]}, and {_join_with_and(coverups)}."
    return sentence


def _salon_sentence(loadout):
    overrides = dict(getattr(loadout, "body_overrides", {}) or {})
    makeup_regions = dict(getattr(loadout, "makeup_regions", {}) or {})
    bits = []
    hair_style = _text(overrides.get("hair_style"))
    hair_color = _text(overrides.get("hair_color"))
    makeup = _text(overrides.get("makeup"))
    if hair_style and hair_color:
        bits.append(f"my hair is worn {hair_style} and colored {hair_color}")
    elif hair_style:
        bits.append(f"my hair is worn {hair_style}")
    elif hair_color:
        bits.append(f"my hair is colored {hair_color}")
    if makeup and makeup.lower() != "none":
        bits.append(f"I have {makeup} makeup")
    region_bits = []
    for region in ("eyes", "lips", "cheeks"):
        value = _text(makeup_regions.get(region))
        if value and value.lower() != "none":
            region_bits.append(f"{value} {region} makeup")
    if region_bits:
        bits.append(f"I have {_join_with_and(region_bits)}")
    if not bits:
        return ""
    sentence = _join_with_and(bits)
    return sentence[:1].upper() + sentence[1:] + "." if sentence else ""


def _identity_noun_for_profile(profile):
    gender_identity = _key((profile or {}).get("gender_identity"))
    return {
        "woman": "woman",
        "man": "man",
        "nonbinary": "person",
    }.get(gender_identity, "person")


HAIR_STYLE_PHRASE_BY_COMPACT = {
    "loose hair": "worn loose",
    "pinned-back hair": "pinned back with a clip",
    "side braid": "braided over one shoulder",
    "sharp bob": "cut in a sharp bob",
    "high tail": "gathered into a high tail",
    "swept-back hair": "swept behind one ear",
    "close sides": "cut close at the sides",
    "slicked-back hair": "slicked back",
    "unruly hair": "left a little unruly",
    "rough crop": "trimmed into a rough crop",
    "neat part": "parted neatly",
    "tied-back hair": "tied back at the nape",
    "jaw-cut hair": "cut blunt at the jaw",
    "one-sided shave": "shaved at one side",
    "capped hair": "tucked beneath a cap",
    "nape tie": "gathered at the nape",
    "brow-falling hair": "falling across the brow",
    "uneven cut": "cut uneven on purpose",
    "clipped-back hair": "worn loose with one side clipped back",
    "careless tie": "tied up carelessly",
    "heavy wave": "let down in a heavy wave",
    "tight braids": "worked into tight braids",
    "sharp short cut": "cut short but styled sharply",
    "loose knot": "kept in a loose knot",
    "short": "worn short",
    "bob": "cut in a bob",
    "braided": "braided",
    "loose": "worn loose",
    "nape-tied": "tied at the nape",
}


def _live_hair_phrase(loadout, profile):
    overrides = dict(getattr(loadout, "body_overrides", {}) or {}) if loadout is not None else {}
    length = _text(overrides.get("hair_length") or (profile or {}).get("hair_length"))
    color = _text(overrides.get("hair_color") or (profile or {}).get("hair_color"))
    texture = _text(overrides.get("hair_texture") or (profile or {}).get("hair_texture"))
    style = _text(overrides.get("hair_style_phrase"))
    if not style:
        style = HAIR_STYLE_PHRASE_BY_COMPACT.get(_key(overrides.get("hair_style"))) or _text(overrides.get("hair_style"))
    if not style:
        style = HAIR_STYLE_PHRASE_BY_COMPACT.get(_key((profile or {}).get("hair_style_compact"))) or _text((profile or {}).get("hair_style_phrase"))
    bits = [length, color, texture, "hair"]
    base = " ".join(bit for bit in bits if bit)
    if base and style:
        return f"{base} {style}"
    return base or style


def _makeup_sentence_for_subject(loadout, *, subject, have):
    overrides = dict(getattr(loadout, "body_overrides", {}) or {}) if loadout is not None else {}
    makeup_regions = dict(getattr(loadout, "makeup_regions", {}) or {}) if loadout is not None else {}
    bits = []
    makeup = _text(overrides.get("makeup"))
    if makeup and _key(makeup) != "none":
        bits.append(f"{makeup} makeup")
    region_labels = {"eyes": "eye", "lips": "lip", "cheeks": "cheek"}
    for region in ("eyes", "lips", "cheeks"):
        value = _text(makeup_regions.get(region))
        if value and _key(value) != "none":
            bits.append(f"{value} {region_labels.get(region, region)} makeup")
    if not bits:
        return ""
    return f"{subject} {have} {_join_with_and(bits)}."


def _outfit_sentence_for_subject(sim, eid, *, subject, be):
    parts = _outfit_parts(sim, eid)
    if not parts:
        return ""
    if len(parts) == 1:
        return f"{subject} {be} wearing {parts[0]}."
    return f"{subject} {be} wearing {', '.join(parts[:-1])}, and {parts[-1]}."


def _adornment_sentence_for_subject(sim, eid, *, subject, have):
    bits = _adornment_parts(sim, eid)
    if not bits:
        return ""
    if len(bits) == 1:
        return f"{subject} {have} {bits[0]} on."
    return f"{subject} {have} {', '.join(bits[:-1])}, and {bits[-1]} on."


def _appearance_segment(text, *, color=None, attrs=0):
    return {"text": str(text or ""), "color": color, "attrs": int(attrs or 0)}


def _appearance_text(segments):
    return "".join(str(segment.get("text", "")) for segment in segments if isinstance(segment, dict))


def _described_wearable_segments(parts, *, opening, closing):
    visible_parts = [part for part in tuple(parts or ()) if isinstance(part, dict) and str(part.get("text", "")).strip()]
    if not visible_parts:
        return []
    segments = [_appearance_segment(opening)]
    for index, part in enumerate(visible_parts):
        if index:
            connector = ", and " if index == len(visible_parts) - 1 else ", "
            segments.append(_appearance_segment(connector))
        segments.append(_appearance_segment(str(part.get("text", "")), color=part.get("color")))
    segments.append(_appearance_segment(closing))
    return segments


def human_live_conversation_presentation(sim, eid, *, identity=None, personal_name=None):
    if sim is None or eid is None:
        return {"text": "", "segments": []}
    if identity is None:
        identity = sim.ecs.get(CreatureIdentity).get(eid)
    resolved_name = getattr(identity, "personal_name", "") if personal_name is None else personal_name or ""
    profile = build_human_description_profile(
        getattr(sim, "seed", 0),
        eid=eid,
        identity=identity,
        personal_name=resolved_name,
    )
    if not isinstance(profile, dict):
        return {"text": "", "segments": []}
    loadout = appearance_loadout_for(sim, eid, create=False)
    slots = pronoun_format_slots(
        str(getattr(identity, "pronoun_set", "") or "").strip().lower() or profile.get("gender_identity"),
        prefix="person",
        personal_name=resolved_name,
        seed_token=profile.get("seed_token"),
    )
    subject = str(slots.get("person_subject_cap", "They") or "They")
    possessive = str(slots.get("person_possessive_adj_cap", "Their") or "Their")
    possessive_lower = str(slots.get("person_possessive_adj", "their") or "their")
    be = str(slots.get("person_be", "are") or "are")
    have = str(slots.get("person_have", "have") or "have")
    identity_noun = _identity_noun_for_profile(profile)
    hair = _live_hair_phrase(loadout, profile)
    stature = _text(profile.get("stature_phrase"))
    segments = [_appearance_segment(f"You see a {identity_noun} here. ")]
    if stature and hair:
        segments.append(_appearance_segment(f"{subject} {be} {stature} and {have} "))
        segments.append(_appearance_segment(hair, color=human_render_color_key(getattr(sim, "seed", 0), eid=eid, identity=identity, personal_name=resolved_name)))
        segments.append(_appearance_segment(". "))
    elif stature:
        segments.append(_appearance_segment(f"{subject} {be} {stature}. "))
    elif hair:
        segments.append(_appearance_segment(f"{subject} {have} "))
        segments.append(_appearance_segment(hair, color=human_render_color_key(getattr(sim, "seed", 0), eid=eid, identity=identity, personal_name=resolved_name)))
        segments.append(_appearance_segment(". "))

    eye_phrase = f"{profile.get('eye_color')} eyes" if _text(profile.get("eye_color")) else ""
    complexion = _text(profile.get("complexion_phrase"))
    feature_bits = []
    if eye_phrase:
        feature_bits.append(eye_phrase)
    if complexion:
        feature_bits.append(complexion)
    if feature_bits:
        verb = "stand" if len(feature_bits) > 1 or (len(feature_bits) == 1 and "eyes" in feature_bits[0]) else "stands"
        segments.append(_appearance_segment(f"{possessive} {_join_with_and(feature_bits)} {verb} out. "))

    skin = _skin_mark_sentence(loadout, subject=subject, possessive_adj=possessive_lower, have=have, first_person=False)
    makeup = _makeup_sentence_for_subject(loadout, subject=subject, have=have)
    for sentence in (skin, makeup):
        if sentence:
            segments.append(_appearance_segment(sentence + " "))
    segments.extend(_described_wearable_segments(
        _outfit_display_parts(sim, eid),
        opening=f"{subject} {be} wearing ",
        closing=". ",
    ))
    segments.extend(_described_wearable_segments(
        _adornment_display_parts(sim, eid),
        opening=f"{subject} {have} ",
        closing=" on. ",
    ))
    text = _appearance_text(segments).strip()
    return {"text": text, "segments": [segment for segment in segments if str(segment.get("text", ""))]}


def _skin_mark_compact_bits(loadout):
    bits = []
    marks = dict(getattr(loadout, "skin_marks", {}) or {}) if loadout is not None else {}
    for slot in SKIN_MARK_SLOTS:
        mark = marks.get(slot)
        if not isinstance(mark, dict) or not mark:
            continue
        kind = _key(mark.get("kind"))
        design = _text(mark.get("design"))
        if kind == "tattoo" and design:
            bits.append(f"{design} tattoo")
        else:
            bits.append(_text(mark.get("description")) or _skin_mark_phrase(mark, first_person=False))
    return tuple(bit for bit in bits if bit)


def _makeup_compact_bits(loadout):
    overrides = dict(getattr(loadout, "body_overrides", {}) or {}) if loadout is not None else {}
    makeup_regions = dict(getattr(loadout, "makeup_regions", {}) or {}) if loadout is not None else {}
    bits = []
    makeup = _text(overrides.get("makeup"))
    if makeup and _key(makeup) != "none":
        bits.append(f"{makeup} makeup")
    labels = {"eyes": "eye makeup", "lips": "lip makeup", "cheeks": "cheek makeup"}
    for region in ("eyes", "lips", "cheeks"):
        value = _text(makeup_regions.get(region))
        if value and _key(value) != "none":
            bits.append(f"{value} {labels.get(region, region)}")
    return tuple(bits)


def human_live_look_description_clause(sim, eid, *, identity=None, personal_name=None):
    if sim is None or eid is None:
        return ""
    if identity is None:
        identity = sim.ecs.get(CreatureIdentity).get(eid)
    resolved_name = getattr(identity, "personal_name", "") if personal_name is None else personal_name or ""
    profile = build_human_description_profile(
        getattr(sim, "seed", 0),
        eid=eid,
        identity=identity,
        personal_name=resolved_name,
    )
    if not isinstance(profile, dict):
        return ""
    loadout = appearance_loadout_for(sim, eid, create=False)
    bits = []
    for value in (
        _text(profile.get("stature_compact")),
        _live_hair_phrase(loadout, profile),
        _text(profile.get("standout_compact")),
    ):
        if value:
            bits.append(value)
    bits.extend(_skin_mark_compact_bits(loadout)[:2])
    bits.extend(_makeup_compact_bits(loadout)[:2])
    outfit = _outfit_parts(sim, eid)
    if outfit:
        bits.append("wearing " + _join_with_and(outfit[:4]))
    adornment = _adornment_parts(sim, eid)
    if adornment:
        bits.append("with " + _join_with_and(adornment[:3]))
    demeanor = _text(profile.get("demeanor_compact"))
    if demeanor:
        bits.append(demeanor)
    return ", ".join(bit for bit in bits if bit)


def player_appearance_summary(sim, player_eid):
    identity = sim.ecs.get(CreatureIdentity).get(player_eid) if sim is not None else None
    loadout = appearance_loadout_for(sim, player_eid, create=True)
    overrides = dict(getattr(loadout, "body_overrides", {}) or {})
    omit_seeded_hair = bool(_text(overrides.get("hair_style")) or _text(overrides.get("hair_color")))
    base = ""
    if identity is not None:
        base = human_self_physical_summary(
            getattr(sim, "seed", 0),
            eid=player_eid,
            identity=identity,
            personal_name=getattr(identity, "personal_name", ""),
            omit_structured_mark=True,
            omit_hair=omit_seeded_hair,
        )
    sentences = [base] if base else []
    salon = _salon_sentence(loadout)
    skin = _skin_mark_sentence(loadout)
    outfit = _outfit_sentence(sim, player_eid)
    adornment = _adornment_sentence(sim, player_eid)
    if skin:
        sentences.append(skin)
    if salon:
        sentences.append(salon)
    if outfit:
        sentences.append(outfit)
    if adornment:
        sentences.append(adornment)
    return " ".join(sentence for sentence in sentences if sentence).strip()


def appearance_slot_rows(sim, eid):
    loadout = appearance_loadout_for(sim, eid, create=True)
    inventory = _inventory_for(sim, eid)
    rows = []
    for slot in APPEARANCE_SLOT_ORDER:
        label = APPEARANCE_SLOT_LABELS.get(slot, slot.replace("_", " ").title())
        value = "empty"
        instance_id = str(loadout.slots.get(slot) or "").strip()
        if instance_id and inventory is not None:
            entry = inventory.find(instance_id=instance_id)
            if entry:
                value = _display_name(sim, eid, entry)
            else:
                value = "missing item"
        if slot == "outer":
            armor = sim.ecs.get(ArmorLoadout).get(eid) if sim is not None else None
            if armor and getattr(armor, "equipped_instance_id", None):
                armor_name = _text(getattr(armor, "equipped_name", None) or getattr(armor, "equipped_item_id", "armor"))
                value = f"armor: {armor_name}"
        rows.append(f"{label}: {value}")
    overrides = dict(getattr(loadout, "body_overrides", {}) or {})
    for key in ("hair_style", "hair_color", "makeup"):
        label = key.replace("_", " ").title()
        rows.append(f"{label}: {_text(overrides.get(key)) or 'default'}")
    makeup_regions = dict(getattr(loadout, "makeup_regions", {}) or {})
    for region in ("eyes", "lips", "cheeks"):
        label = f"Makeup {MAKEUP_REGION_LABELS.get(region, region.title())}"
        blocked = " blocked by tattoo" if _makeup_region_blocked(loadout, region) else ""
        rows.append(f"{label}: {_text(makeup_regions.get(region)) or 'default'}{blocked}")
    marks = dict(getattr(loadout, "skin_marks", {}) or {})
    for slot in SKIN_MARK_SLOTS:
        mark = marks.get(slot)
        if not isinstance(mark, dict):
            continue
        kind = _key(mark.get("kind")) or "mark"
        phrase = _text(mark.get("description")) or _skin_mark_phrase(mark)
        rows.append(f"{SKIN_MARK_SLOT_LABELS.get(slot, slot.title())}: {kind} - {phrase}")
    return rows


def appearance_signal_profile(sim, eid):
    loadout = appearance_loadout_for(sim, eid, create=False)
    if loadout is None:
        return {}
    marks = {
        slot: dict(mark)
        for slot, mark in dict(getattr(loadout, "skin_marks", {}) or {}).items()
        if isinstance(mark, dict)
    }
    tattoos = []
    visible_marks = []
    covered_marks = []
    for slot, mark in marks.items():
        kind = _key(mark.get("kind"))
        row = {
            "slot": slot,
            "kind": kind,
            "description": _text(mark.get("description")),
            "design": _text(mark.get("design")),
        }
        if kind == "tattoo":
            tattoos.append(row)
            covered = mark.get("covered_mark") if isinstance(mark.get("covered_mark"), dict) else None
            if covered:
                covered_marks.append({
                    "slot": slot,
                    "kind": _key(covered.get("kind")),
                    "description": _text(covered.get("description")),
                    "covered_by": "tattoo",
                })
        elif kind:
            visible_marks.append(row)
    makeup_regions = {
        region: value
        for region, value in dict(getattr(loadout, "makeup_regions", {}) or {}).items()
        if _text(value) and _key(value) != "none"
    }
    overrides = dict(getattr(loadout, "body_overrides", {}) or {})
    global_makeup = _key(overrides.get("makeup"))
    tags = set()
    if tattoos:
        tags.add("tattoo")
        tags.add("visible_mark")
    if visible_marks:
        tags.add("visible_mark")
        tags.add("scar")
    if global_makeup and global_makeup != "none":
        tags.add("makeup")
    if makeup_regions:
        tags.add("makeup")
    if _text(overrides.get("hair_style")) or _text(overrides.get("hair_color")):
        tags.add("styled_hair")
    return {
        "skin_marks": marks,
        "tattoos": tuple(tattoos),
        "visible_marks": tuple(visible_marks),
        "covered_marks": tuple(covered_marks),
        "makeup_regions": dict(makeup_regions),
        "blocked_makeup_regions": _tattoo_conflict_regions(loadout),
        "body_overrides": overrides,
        "tags": tuple(sorted(tags)),
    }


def _appearance_render_color_part(sim, eid, slot):
    entry = _entry_for_slot(sim, eid, slot)
    if not entry:
        return None
    profile = appearance_metadata_for_entry(entry)
    word = _key(profile.get("color_word") or profile.get("color"))
    render_key = _key(profile.get("accent_color"))
    if not render_key and word:
        render_key = _key(fallback_render_key_for_color_word(word, default=""))
    if not render_key:
        return None
    return {
        "slot": slot,
        "word": word,
        "render_key": render_key,
        "type": _key(profile.get("appearance_type")) or _key(entry.get("item_id")),
        "drawable_id": _key(profile.get("appearance_drawable")),
        "material": _key(profile.get("material")),
        "style": _key(profile.get("style")),
        "detail": _key(profile.get("detail")),
        "pattern": _key(profile.get("pattern")),
        "emblem": _key(profile.get("emblem")),
        "flora_motif": dict(profile.get("flora_motif") or {}) if isinstance(profile.get("flora_motif"), dict) else {},
    }


def _basewear_render_color_part(sim, eid, slot):
    state = player_basewear_profile(sim, eid, slot)
    if not state:
        return None
    word = _key(state.get("color_word") or state.get("color"))
    render_key = _key(state.get("accent_color"))
    if not render_key and word:
        render_key = _key(fallback_render_key_for_color_word(word, default=""))
    if not render_key:
        return None
    return {
        "slot": slot,
        "word": word,
        "render_key": render_key,
        "type": _key(state.get("appearance_type") or state.get("item_id")),
        "drawable_id": _key(
            (_item_def(state.get("item_id")) or {}).get("appearance_drawable")
        ),
        "material": _key(state.get("material")),
        "style": _key(state.get("style")),
        "detail": _key(state.get("detail")),
        "pattern": _key(state.get("pattern")),
        "emblem": _key(state.get("emblem")),
        "flora_motif": dict(state.get("flora_motif") or {}) if isinstance(state.get("flora_motif"), dict) else {},
    }


def _first_appearance_render_color_part(sim, eid, slots):
    for slot in tuple(slots or ()):
        part = _appearance_render_color_part(sim, eid, slot)
        if part:
            return part
    return None


def appearance_render_colors(sim, eid):
    loadout = appearance_loadout_for(sim, eid, create=False)
    result = {
        "dominant": None,
        "primary": None,
        "inner": None,
        "secondary": None,
        "footwear": None,
        "headwear": None,
        "accessory": None,
        "base_top": None,
        "base_bottom": None,
        "dominant_word": None,
        "primary_word": None,
        "inner_word": None,
        "secondary_word": None,
        "footwear_word": None,
        "headwear_word": None,
        "accessory_word": None,
        "base_top_word": None,
        "base_bottom_word": None,
        "parts": {},
        "words": {},
        "word_list": (),
    }
    if loadout is None:
        return result
    parts = {
        "primary": _first_appearance_render_color_part(sim, eid, ("outer", "full_body", "top")),
        "inner": _first_appearance_render_color_part(sim, eid, ("full_body", "top")),
        "secondary": _first_appearance_render_color_part(sim, eid, ("bottom",)),
        "footwear": _first_appearance_render_color_part(sim, eid, ("shoes",)),
        "headwear": _first_appearance_render_color_part(sim, eid, ("hat",)),
        "accessory": _first_appearance_render_color_part(
            sim,
            eid,
            ("necklace", "bracelet", "ring_left", "ring_right", "earrings"),
        ),
        "base_top": _basewear_render_color_part(sim, eid, "base_top"),
        "base_bottom": _basewear_render_color_part(sim, eid, "base_bottom"),
    }
    for role, part in parts.items():
        if not part:
            continue
        result[role] = part["render_key"]
        result[f"{role}_word"] = _key(part.get("word")) or None
        result["parts"][role] = dict(part)
    for role in ("primary", "inner", "secondary", "footwear", "headwear", "accessory", "base_top", "base_bottom"):
        if result.get(role):
            result["dominant"] = result[role]
            result["dominant_word"] = result.get(f"{role}_word")
            break
    words = {}
    word_list = []
    for role, part in parts.items():
        if not part:
            continue
        word = _key(part.get("word"))
        if not word:
            continue
        words[role] = word
        if word not in word_list:
            word_list.append(word)
    result["words"] = words
    result["word_list"] = tuple(word_list)
    return result


def humanoid_render_profile(sim, eid):
    """Return persisted outward-presentation traits used by the tiny actor art."""

    if sim is None or eid is None:
        return {}
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    if identity is None or _key(getattr(identity, "taxonomy_class", "")) != "hominid":
        return {}
    loadout = appearance_loadout_for(sim, eid, create=False)
    overrides = dict(getattr(loadout, "body_overrides", {}) or {}) if loadout is not None else {}
    # Older saves predate persisted complexion/presentation render fields. Fill
    # them once from the same deterministic description that powers the sheet;
    # subsequent frames remain a cheap component read.
    if not _text(overrides.get("complexion_phrase")) or not _text(overrides.get("silhouette_variant")):
        seed_npc_innate_appearance_from_description(sim, eid, seed_token="render-profile-backfill")
        loadout = appearance_loadout_for(sim, eid, create=False)
    overrides = dict(getattr(loadout, "body_overrides", {}) or {}) if loadout is not None else {}
    gender_identity = _key(getattr(identity, "gender_identity", ""))
    presentation = _key(overrides.get("style_axis"))
    if presentation not in {"femme", "masc", "androgynous", "mixed"}:
        presentation = {
            "woman": "femme",
            "man": "masc",
            "nonbinary": "mixed",
        }.get(gender_identity, "mixed")
    hair_color = _key(overrides.get("hair_color"))
    eye_color = _key(overrides.get("eye_color"))
    complexion_phrase = _key(overrides.get("complexion_phrase"))
    return {
        "presentation": presentation,
        "build": _key(overrides.get("stature_compact")),
        "silhouette": _key(overrides.get("silhouette_variant")),
        "hair_length": _key(overrides.get("hair_length")),
        "hair_style": _key(overrides.get("hair_style") or overrides.get("hair_style_compact")),
        "hair_color": hair_color,
        "hair_color_key": human_hair_render_color_key(hair_color) or "human_hair_charcoal",
        "eye_color": eye_color,
        "eye_color_key": human_eye_render_color_key(eye_color) or "",
        "complexion_phrase": complexion_phrase,
        "body_color_key": human_complexion_render_color_key(complexion_phrase) or "human_monochrome",
    }


def appearance_color_key(sim, eid):
    colors = appearance_render_colors(sim, eid)
    return colors.get("dominant") if isinstance(colors, dict) else None


def appearance_color_word(sim, eid):
    colors = appearance_render_colors(sim, eid)
    return colors.get("dominant_word") if isinstance(colors, dict) else None


def player_appearance_color_key(sim, player_eid):
    return appearance_color_key(sim, player_eid)


def player_appearance_color_word(sim, player_eid):
    return appearance_color_word(sim, player_eid)


def apply_appearance_service(sim, eid, *, kind="", value="", prop=None):
    kind = _key(kind)
    value = _key(value)
    if kind not in STYLE_SERVICE_OPTIONS:
        return AppearanceEquipResult(False, reason="invalid_style_kind")
    if value not in STYLE_SERVICE_OPTIONS[kind]:
        return AppearanceEquipResult(False, reason="invalid_style_value")
    loadout = appearance_loadout_for(sim, eid, create=True)
    if kind in MAKEUP_REGION_BY_KIND:
        region = MAKEUP_REGION_BY_KIND[kind]
        if value != "none" and _makeup_region_blocked(loadout, region):
            return AppearanceEquipResult(False, reason="makeup_blocked_by_tattoo")
        if value == "none":
            loadout.makeup_regions.pop(region, None)
        else:
            loadout.makeup_regions[region] = value
    elif kind == "makeup":
        if value != "none" and _tattoo_conflict_regions(loadout):
            return AppearanceEquipResult(False, reason="makeup_blocked_by_tattoo")
        loadout.body_overrides[kind] = value
    else:
        loadout.body_overrides[kind] = value
    sim.emit(Event(
        "appearance_style_updated",
        eid=eid,
        style_kind=kind,
        style_value=value,
        makeup_region=MAKEUP_REGION_BY_KIND.get(kind, ""),
        property_id=(prop or {}).get("id") if isinstance(prop, dict) else None,
    ))
    return AppearanceEquipResult(True, action="style_updated", item_name=value)
