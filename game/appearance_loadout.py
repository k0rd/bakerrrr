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
from game.components import AI, AppearanceLoadout, ArmorLoadout, CreatureIdentity, Inventory, Occupation
from game.human_description import build_human_description_profile, human_self_physical_summary, human_render_color_key
from game.human_identity import pronoun_format_slots
from game.item_semantics import item_display_name_for_actor
from game.items import ITEM_CATALOG, item_display_name, item_inventory_slot_cost


APPEARANCE_METADATA_KEY = "appearance"
APPEARANCE_WORN_METADATA_KEY = "appearance_worn"
APPEARANCE_SLOT_METADATA_KEY = "appearance_slot"

APPEARANCE_SLOTS = AppearanceLoadout.VALID_SLOTS
APPEARANCE_SLOT_LABELS = {
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
ARTICLELESS_APPEARANCE_TYPES = frozenset({
    "boots",
    "earrings",
    "gloves",
    "sandals",
    "shorts",
    "sneakers",
    "trousers",
})
COSMETIC_ITEM_IDS = {
    "tee": {
        "label": "tee",
        "slots": ("top",),
        "materials": ("cotton", "jersey", "linen", "ribbed cotton"),
        "styles": ("plain", "soft", "trim", "faded"),
    },
    "button_up": {
        "label": "button-up",
        "slots": ("top",),
        "materials": ("cotton", "linen", "poplin", "brushed cotton"),
        "styles": ("crisp", "rolled-sleeve", "loose", "neat"),
    },
    "blouse": {
        "label": "blouse",
        "slots": ("top",),
        "materials": ("cotton", "linen", "satin", "poplin"),
        "styles": ("sharp", "soft", "neat", "loose"),
    },
    "sweater": {
        "label": "sweater",
        "slots": ("top",),
        "materials": ("knit", "wool", "cotton", "ribbed knit"),
        "styles": ("soft", "plain", "loose", "trim"),
    },
    "overshirt": {
        "label": "overshirt",
        "slots": ("top",),
        "materials": ("cotton", "canvas", "flannel", "denim"),
        "styles": ("thick", "neat", "oversized", "workwear"),
    },
    "turtleneck": {
        "label": "turtleneck",
        "slots": ("top",),
        "materials": ("knit", "cotton", "ribbed knit", "wool"),
        "styles": ("clean", "sharp", "soft", "severe"),
    },
    "trousers": {
        "label": "trousers",
        "slots": ("bottom",),
        "materials": ("twill", "denim", "wool", "canvas"),
        "styles": ("straight-leg", "creased", "relaxed", "tapered"),
    },
    "shorts": {
        "label": "shorts",
        "slots": ("bottom",),
        "materials": ("cotton", "denim", "twill", "linen"),
        "styles": ("plain", "cuffed", "loose", "utility"),
    },
    "skirt": {
        "label": "skirt",
        "slots": ("bottom",),
        "materials": ("cotton", "denim", "satin", "linen"),
        "styles": ("pleated", "straight", "wrap", "soft"),
    },
    "dress": {
        "label": "dress",
        "slots": ("full_body",),
        "materials": ("cotton", "linen", "satin", "knit"),
        "styles": ("simple", "fitted", "loose", "sharp"),
    },
    "orange_jumpsuit": {
        "label": "jumpsuit",
        "slots": ("full_body",),
        "materials": ("cotton",),
        "styles": ("issued",),
    },
    "boots": {
        "label": "boots",
        "slots": ("shoes",),
        "materials": ("leather", "canvas", "rubber", "suede"),
        "styles": ("scuffed", "polished", "heavy", "soft"),
    },
    "sneakers": {
        "label": "sneakers",
        "slots": ("shoes",),
        "materials": ("canvas", "mesh", "suede", "rubber"),
        "styles": ("clean", "worn-in", "bright", "low-top"),
    },
    "sandals": {
        "label": "sandals",
        "slots": ("shoes",),
        "materials": ("leather", "rubber", "canvas", "woven cord"),
        "styles": ("plain", "strapped", "soft", "worn-in"),
    },
    "cap": {
        "label": "cap",
        "slots": ("hat",),
        "materials": ("cotton", "canvas", "denim", "wool"),
        "styles": ("plain", "low-brim", "soft", "patched"),
    },
    "baseball_cap": {
        "label": "baseball cap",
        "slots": ("hat",),
        "materials": ("cotton", "canvas", "denim", "polyester"),
        "styles": ("plain", "curved-brim", "faded", "patched"),
    },
    "bandana": {
        "label": "bandana",
        "slots": ("hat",),
        "materials": ("cotton", "linen", "gauze", "soft cotton"),
        "styles": ("plain", "knotted", "folded", "faded"),
    },
    "jacket": {
        "label": "jacket",
        "slots": ("outer",),
        "materials": ("canvas", "denim", "leather", "wool"),
        "styles": ("boxy", "cropped", "workwear", "lined"),
    },
    "windbreaker": {
        "label": "windbreaker",
        "slots": ("outer",),
        "materials": ("nylon", "polyester", "ripstop", "light canvas"),
        "styles": ("lightweight", "hooded", "zip-front", "boxy"),
    },
    "coat": {
        "label": "coat",
        "slots": ("outer",),
        "materials": ("wool", "canvas", "cotton", "weatherproof cloth"),
        "styles": ("dark", "heavy", "boxy", "long"),
    },
    "cardigan": {
        "label": "cardigan",
        "slots": ("outer",),
        "materials": ("knit", "wool", "cotton", "soft knit"),
        "styles": ("long", "soft", "loose", "neat"),
    },
    "blazer": {
        "label": "blazer",
        "slots": ("outer",),
        "materials": ("wool", "twill", "linen", "structured cotton"),
        "styles": ("structured", "sharp", "tailored", "dark"),
    },
    "vest": {
        "label": "vest",
        "slots": ("outer",),
        "materials": ("cotton", "canvas", "wool", "denim"),
        "styles": ("sleeveless", "plain", "neat", "severe"),
    },
    "earrings": {
        "label": "earrings",
        "slots": ("earrings",),
        "materials": ("silver", "brass", "glass", "steel"),
        "styles": ("small", "hoop", "drop", "simple"),
    },
    "ring": {
        "label": "ring",
        "slots": ("ring_left", "ring_right"),
        "materials": ("silver", "brass", "steel", "onyx"),
        "styles": ("plain", "signet", "thin", "wide"),
    },
    "necklace": {
        "label": "necklace",
        "slots": ("necklace",),
        "materials": ("silver", "brass", "cord", "steel"),
        "styles": ("simple", "chain", "pendant", "short"),
    },
    "scarf": {
        "label": "scarf",
        "slots": ("necklace",),
        "materials": ("cotton", "wool", "linen", "soft knit"),
        "styles": ("narrow", "wrapped", "knotted", "soft"),
    },
    "bracelet": {
        "label": "bracelet",
        "slots": ("bracelet",),
        "materials": ("silver", "brass", "cord", "steel"),
        "styles": ("cuff", "chain", "simple", "wrapped"),
    },
    "gloves": {
        "label": "gloves",
        "slots": ("bracelet",),
        "materials": ("leather", "canvas", "wool", "knit"),
        "styles": ("fingerless", "work-rough", "soft", "worn-in"),
    },
    "watch": {
        "label": "watch",
        "slots": ("bracelet",),
        "materials": ("steel", "brass", "leather", "canvas"),
        "styles": ("weathered", "smooth", "narrow", "polished"),
    },
}
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
STARTER_OUTFIT_COLOR_BUCKETS = {
    "human_charcoal": ("charcoal", "black", "slate"),
    "human_olive": ("olive", "green", "tan"),
    "human_denim": ("denim", "blue", "slate"),
    "human_accent": ("rust", "gold", "brown"),
    "human_monochrome": ("gray", "white", "charcoal"),
    "human_rust": ("rust", "brown", "tan"),
    "human_slate": ("slate", "gray", "blue"),
    "human_wine": ("wine", "red", "black"),
}
STARTER_SHOE_COLORS = ("black", "brown", "charcoal", "gray")
NPC_DESCRIBED_OUTFIT_METADATA_KEY = "npc_described_outfit"
NPC_DESCRIBED_OUTFIT_SOURCE = "seeded_description_outfit"
NPC_DESCRIPTION_COLOR_BUCKETS = {
    "human_charcoal": {
        "outer": ("charcoal", "black", "slate", "smoke", "violet"),
        "top": ("slate", "gray", "smoke", "lavender", "periwinkle", "rose", "white"),
        "bottom": ("charcoal", "black", "slate", "plum", "navy"),
        "shoes": ("black", "charcoal", "slate", "smoke", "purple"),
        "accessory": ("silver", "steel", "onyx", "lavender", "cobalt"),
    },
    "human_olive": {
        "outer": ("olive", "green", "moss", "forest", "sage", "mint"),
        "top": ("green", "olive", "sage", "mint", "lime", "cream", "peach"),
        "bottom": ("brown", "olive", "moss", "forest", "khaki", "sage"),
        "shoes": ("brown", "olive", "moss", "tan", "green", "black"),
        "accessory": ("brass", "copper", "bronze", "mint", "gold"),
    },
    "human_denim": {
        "outer": ("denim", "blue", "cerulean", "slate"),
        "top": ("blue", "sky", "aqua", "turquoise", "periwinkle", "ash", "white"),
        "bottom": ("denim", "blue", "navy", "slate", "cerulean"),
        "shoes": ("black", "denim", "navy", "blue", "aqua", "charcoal"),
        "accessory": ("steel", "silver", "onyx", "aqua", "cobalt"),
    },
    "human_accent": {
        "outer": ("cobalt", "teal", "coral", "violet", "pink", "orange", "charcoal"),
        "top": ("cobalt", "coral", "violet", "gold", "teal", "pink", "magenta", "white"),
        "bottom": ("black", "slate", "charcoal", "cobalt", "purple", "magenta"),
        "shoes": ("black", "charcoal", "cobalt", "white", "red", "pink", "orange"),
        "accessory": ("gold", "cobalt", "coral", "violet", "pink", "brass"),
    },
    "human_monochrome": {
        "outer": ("black", "charcoal", "gray", "ash", "lavender"),
        "top": ("white", "ivory", "gray", "ash", "lavender", "peach"),
        "bottom": ("black", "gray", "charcoal", "ash"),
        "shoes": ("black", "gray", "white", "charcoal", "silver"),
        "accessory": ("silver", "steel", "onyx", "ivory", "lavender"),
    },
    "human_rust": {
        "outer": ("rust", "copper", "orange", "brown", "amber"),
        "top": ("rust", "amber", "orange", "coral", "salmon", "peach", "cream"),
        "bottom": ("brown", "rust", "copper", "smoke", "maroon"),
        "shoes": ("brown", "rust", "copper", "tan", "orange", "black"),
        "accessory": ("copper", "brass", "bronze", "coral", "amber"),
    },
    "human_slate": {
        "outer": ("slate", "blue", "navy", "cerulean", "periwinkle"),
        "top": ("sky", "blue", "cerulean", "periwinkle", "aqua", "lavender", "ash"),
        "bottom": ("navy", "denim", "slate", "blue", "indigo"),
        "shoes": ("black", "navy", "slate", "blue", "cerulean", "charcoal"),
        "accessory": ("steel", "silver", "blue", "cobalt", "periwinkle"),
    },
    "human_wine": {
        "outer": ("wine", "burgundy", "maroon", "plum", "charcoal"),
        "top": ("wine", "rose", "pink", "burgundy", "lilac", "magenta", "ivory"),
        "bottom": ("black", "wine", "burgundy", "charcoal", "plum", "purple"),
        "shoes": ("black", "wine", "burgundy", "brown", "plum", "rose"),
        "accessory": ("brass", "gold", "copper", "rose", "lilac"),
    },
}
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
        if slot in APPEARANCE_SLOTS and slot not in slots:
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


def seed_npc_innate_appearance_from_description(sim, eid, *, seed_token=""):
    loadout = appearance_loadout_for(sim, eid, create=True)
    if loadout is None:
        return False
    if bool(getattr(loadout, "description_appearance_seeded", False)):
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
    overrides = dict(getattr(loadout, "body_overrides", {}) or {})
    for key in ("hair_color", "hair_texture", "hair_length", "hair_style_compact", "hair_style_phrase"):
        source_key = "hair_style_compact" if key == "hair_style_compact" else key
        value = _text(profile.get(source_key))
        if value and not _text(overrides.get(key)):
            overrides[key] = value
    if not _text(overrides.get("hair_style")) and _text(profile.get("hair_style_compact")):
        overrides["hair_style"] = _text(profile.get("hair_style_compact"))
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
    return True


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
    return loadout


def _inventory_for(sim, eid):
    if sim is None or eid is None:
        return None
    return sim.ecs.get(Inventory).get(eid)


def _item_def(item_id, item_catalog=None):
    catalog = item_catalog or ITEM_CATALOG
    return catalog.get(_key(item_id), {})


def _entry_metadata(entry):
    return dict(entry.get("metadata") or {}) if isinstance(entry, dict) else {}


def appearance_metadata_for_entry(entry, *, item_catalog=None):
    if not isinstance(entry, dict):
        return {}
    metadata = _entry_metadata(entry)
    nested = metadata.get(APPEARANCE_METADATA_KEY)
    item_id = _key(entry.get("item_id"))
    item_def = _item_def(item_id, item_catalog=item_catalog)
    profile = COSMETIC_ITEM_IDS.get(item_id, {})
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
    color = _key(metadata.get("color") or nested_data.get("color"))
    color_word = _key(color or metadata.get("color_word") or nested_data.get("color_word"))
    material = _key(metadata.get("material") or nested_data.get("material"))
    style = _key(metadata.get("style") or nested_data.get("style"))
    accent = _key(metadata.get("accent_color") or nested_data.get("accent_color"))
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
    if not accent:
        accent = fallback_render_key_for_color_word(color_word, default="human_monochrome")
    if not slots:
        return {}
    return {
        "appearance_type": appearance_type,
        "label": label,
        "slots": slots,
        "color": color,
        "color_word": color_word,
        "material": material,
        "style": style,
        "accent_color": accent,
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
    return item_id in COSMETIC_ITEM_IDS or "cosmetic" in tags


def is_entry_worn(entry):
    metadata = _entry_metadata(entry)
    return bool(metadata.get(APPEARANCE_WORN_METADATA_KEY))


def cosmetic_variant_metadata(item_id, *, seed_token="", item_catalog=None):
    item_id = _key(item_id)
    profile = COSMETIC_ITEM_IDS.get(item_id)
    if not profile:
        return {}
    seed = f"cosmetic-variant:{item_id}:{seed_token}"
    rng = random.Random(seed)
    slots = tuple(profile.get("slots", ()))
    color = choose_appearance_color_word(rng, slots=slots)
    materials = tuple(profile.get("materials") or ("cotton",))
    styles = tuple(profile.get("styles") or ("plain",))
    material = rng.choice(materials)
    style = rng.choice(styles)
    accent = fallback_render_key_for_color_word(color, default="human_monochrome")
    label = str(profile.get("label", item_id)).strip() or item_id
    display_parts = [color, material, label]
    if style and style not in {"plain", "simple"}:
        display_parts.insert(0, style)
    display_name = _title_words(" ".join(display_parts))
    appearance = {
        "type": item_id,
        "label": label,
        "slots": list(slots),
        "color": color,
        "color_word": color,
        "material": material,
        "style": style,
        "accent_color": accent,
    }
    return {
        "appearance_type": item_id,
        "appearance_label": label,
        "appearance_slots": list(slots),
        "color": color,
        "color_word": color,
        "material": material,
        "style": style,
        "accent_color": accent,
        "display_name": display_name,
        APPEARANCE_METADATA_KEY: appearance,
    }


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
    label = _text(updated.get("appearance_label") or nested.get("label") or updated.get("appearance_type"))
    material = _text(updated.get("material") or nested.get("material"))
    style = _text(updated.get("style") or nested.get("style"))
    display_parts = [color, material, label]
    if style and style not in {"plain", "simple"}:
        display_parts.insert(0, style)
    updated["display_name"] = _title_words(" ".join(part for part in display_parts if part))
    return updated


def _starter_outfit_color(sim, eid, identity, rng):
    render_key = human_render_color_key(
        getattr(sim, "seed", 0),
        eid=eid,
        identity=identity,
        personal_name=getattr(identity, "personal_name", None),
    )
    options = STARTER_OUTFIT_COLOR_BUCKETS.get(_key(render_key), ("charcoal", "denim", "olive", "slate"))
    return rng.choice(tuple(options))


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
    render_key = _key((profile or {}).get("render_color_key")) or "human_charcoal"
    buckets = NPC_DESCRIPTION_COLOR_BUCKETS.get(render_key, NPC_DESCRIPTION_COLOR_BUCKETS["human_charcoal"])
    bucket_key = "accessory" if slot in {"hat", "earrings", "necklace", "bracelet", "ring_left", "ring_right"} else slot
    options = tuple(buckets.get(bucket_key) or buckets.get("top") or ("charcoal",))
    color = rng.choice(options)
    if _key(item_id) == "jacket" and "denim" in _key((profile or {}).get("attire_compact")):
        color = "denim"
    if _key(item_id) == "ring" and "silver" in _key((profile or {}).get("accessory_compact")):
        color = "silver"
    return color


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


def _description_item_metadata(item_id, *, color, profile, slot, seed_token):
    metadata = cosmetic_variant_metadata(item_id, seed_token=seed_token, item_catalog=ITEM_CATALOG)
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
    seeded = []
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
        color = _description_color_for(profile, slot, rng, item_id=item_id, role=role, career=career)
        metadata = _description_item_metadata(
            item_id,
            color=color,
            profile=profile,
            slot=slot,
            seed_token=f"{seed_token}:{eid}:{item_id}:{slot}",
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
        seeded.append({
            "item_id": item_id,
            "instance_id": str(instance_id),
            "slot": slot,
            "item_name": item_display_name(item_id, metadata=metadata, item_catalog=ITEM_CATALOG),
            "attire_compact": attire_key,
            "accessory_compact": accessory_key,
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
    if loadout.slots.get("full_body") or loadout.slots.get("top") or loadout.slots.get("bottom") or loadout.slots.get("shoes"):
        return ()

    identity = sim.ecs.get(CreatureIdentity).get(eid) if sim is not None else None
    rng = random.Random(f"starter-outfit:{getattr(sim, 'seed', 0)}:{eid}:{seed_token}")
    outfit_color = _starter_outfit_color(sim, eid, identity, rng)
    rows = (
        (rng.choice(("tee", "button_up", "button_up")), outfit_color),
        ("trousers", outfit_color if rng.random() < 0.35 else rng.choice(("charcoal", "denim", "slate", "black"))),
        (rng.choice(("sneakers", "boots")), rng.choice(STARTER_SHOE_COLORS)),
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
        result = equip_appearance_item(sim, eid, instance_id)
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


def equip_appearance_item(sim, eid, instance_id, preferred_slot=None):
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
    if target_slot == "outer" and armor and getattr(armor, "equipped_instance_id", None):
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
    color = profile.get("color", "")
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
    appearance_type = _key(profile.get("appearance_type") or profile.get("type"))
    if article and appearance_type not in ARTICLELESS_APPEARANCE_TYPES:
        return _indefinite_article_phrase(phrase)
    return phrase


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


def _outfit_parts(sim, eid):
    loadout = appearance_loadout_for(sim, eid, create=False)
    if loadout is None:
        return []
    parts = []
    full_body = _entry_for_slot(sim, eid, "full_body")
    if full_body:
        phrase = _entry_phrase(full_body, article=True)
        if phrase:
            parts.append(phrase)
    else:
        top = _entry_for_slot(sim, eid, "top")
        bottom = _entry_for_slot(sim, eid, "bottom")
        top_phrase = _entry_phrase(top, article=True) if top else ""
        bottom_phrase = _entry_phrase(bottom, article=True) if bottom else ""
        if top_phrase:
            parts.append(top_phrase)
        if bottom_phrase:
            parts.append(bottom_phrase)
    outer = _entry_for_slot(sim, eid, "outer")
    if outer:
        phrase = _entry_phrase(outer, article=True)
        if phrase:
            parts.append(phrase)
    armor = sim.ecs.get(ArmorLoadout).get(eid) if sim is not None else None
    if armor and getattr(armor, "equipped_instance_id", None):
        name = _text(getattr(armor, "equipped_name", None) or getattr(armor, "equipped_item_id", "armor"))
        if name:
            parts.append(name)
    shoes = _entry_for_slot(sim, eid, "shoes")
    if shoes:
        phrase = _entry_phrase(shoes, article=True)
        if phrase:
            parts.append(phrase)
    return parts


def _outfit_sentence(sim, eid):
    parts = _outfit_parts(sim, eid)
    if not parts:
        return ""
    if len(parts) == 1:
        return f"I am wearing {parts[0]}."
    return f"I am wearing {', '.join(parts[:-1])}, and {parts[-1]}."


def _adornment_parts(sim, eid):
    bits = []
    for slot in ("hat", "earrings", "necklace", "bracelet", "ring_left", "ring_right"):
        entry = _entry_for_slot(sim, eid, slot)
        if not entry:
            continue
        phrase = _entry_phrase(entry, compact=True, article=True)
        if phrase:
            bits.append(phrase)
    return bits


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


def human_live_conversation_presentation(sim, eid, *, identity=None, personal_name=None):
    if sim is None or eid is None:
        return {"text": "", "segments": []}
    if identity is None:
        identity = sim.ecs.get(CreatureIdentity).get(eid)
    resolved_name = personal_name or getattr(identity, "personal_name", "")
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

    extra_sentences = []
    skin = _skin_mark_sentence(loadout, subject=subject, possessive_adj=possessive_lower, have=have, first_person=False)
    makeup = _makeup_sentence_for_subject(loadout, subject=subject, have=have)
    outfit = _outfit_sentence_for_subject(sim, eid, subject=subject, be=be)
    adornment = _adornment_sentence_for_subject(sim, eid, subject=subject, have=have)
    for sentence in (skin, makeup, outfit, adornment):
        if sentence:
            extra_sentences.append(sentence)
    outfit_color = appearance_color_key(sim, eid)
    for sentence in extra_sentences:
        color = outfit_color if sentence == outfit else None
        segments.append(_appearance_segment(sentence + " ", color=color))
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
    resolved_name = personal_name or getattr(identity, "personal_name", "")
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
        "dominant_word": None,
        "primary_word": None,
        "inner_word": None,
        "secondary_word": None,
        "footwear_word": None,
        "headwear_word": None,
        "accessory_word": None,
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
    }
    for role, part in parts.items():
        if not part:
            continue
        result[role] = part["render_key"]
        result[f"{role}_word"] = _key(part.get("word")) or None
    for role in ("primary", "inner", "secondary", "footwear", "headwear", "accessory"):
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
