from __future__ import annotations

import random
from dataclasses import dataclass

from engine.events import Event
from game.components import AppearanceLoadout, ArmorLoadout, CreatureIdentity, Inventory
from game.human_description import human_physical_summary, human_render_color_key
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
COSMETIC_COLORS = (
    "black",
    "charcoal",
    "white",
    "ivory",
    "gray",
    "slate",
    "denim",
    "blue",
    "olive",
    "green",
    "rust",
    "brown",
    "tan",
    "red",
    "wine",
    "gold",
    "brass",
    "teal",
)
COSMETIC_COLOR_KEYS = {
    "black": "human_charcoal",
    "charcoal": "human_charcoal",
    "white": "human_monochrome",
    "ivory": "human_monochrome",
    "gray": "human_slate",
    "slate": "human_slate",
    "denim": "human_denim",
    "blue": "human_denim",
    "olive": "human_olive",
    "green": "human_olive",
    "rust": "human_rust",
    "brown": "human_rust",
    "tan": "human_olive",
    "red": "human_wine",
    "wine": "human_wine",
    "gold": "human_accent",
    "brass": "human_accent",
    "teal": "human_denim",
    "silver": "human_monochrome",
    "steel": "human_slate",
    "onyx": "human_charcoal",
}
STYLE_SERVICE_OPTIONS = {
    "hair_style": ("cropped", "short", "bob", "braided", "loose", "nape-tied"),
    "hair_color": ("black", "brown", "auburn", "blonde", "silver", "copper"),
    "makeup": ("none", "clean", "subtle", "smoky", "bold"),
}
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
    material = _key(metadata.get("material") or nested_data.get("material"))
    style = _key(metadata.get("style") or nested_data.get("style"))
    accent = _key(metadata.get("accent_color") or nested_data.get("accent_color"))
    label = _text(metadata.get("appearance_label") or nested_data.get("label"))
    if not label:
        label = _text(profile.get("label")) or _text(item_def.get("name")) or _title_words(item_id)
    if not color:
        color = "charcoal"
    if not material:
        material = _text((profile.get("materials") or ("cotton",))[0]).lower()
    if not style:
        style = _text((profile.get("styles") or ("plain",))[0]).lower()
    if not accent:
        accent = COSMETIC_COLOR_KEYS.get(color, "human_monochrome")
    if not slots:
        return {}
    return {
        "appearance_type": appearance_type,
        "label": label,
        "slots": slots,
        "color": color,
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
    color = rng.choice(COSMETIC_COLORS)
    materials = tuple(profile.get("materials") or ("cotton",))
    styles = tuple(profile.get("styles") or ("plain",))
    material = rng.choice(materials)
    style = rng.choice(styles)
    slots = tuple(profile.get("slots", ()))
    accent = COSMETIC_COLOR_KEYS.get(color, "human_monochrome")
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
        "material": material,
        "style": style,
        "accent_color": accent,
    }
    return {
        "appearance_type": item_id,
        "appearance_label": label,
        "appearance_slots": list(slots),
        "color": color,
        "material": material,
        "style": style,
        "accent_color": accent,
        "display_name": display_name,
        APPEARANCE_METADATA_KEY: appearance,
    }


def _metadata_with_color(metadata, *, color):
    updated = dict(metadata or {})
    color = _key(color) or "charcoal"
    accent = COSMETIC_COLOR_KEYS.get(color, "human_monochrome")
    updated["color"] = color
    updated["accent_color"] = accent
    nested = dict(updated.get(APPEARANCE_METADATA_KEY) or {})
    nested["color"] = color
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


def _entry_phrase(entry, *, compact=False):
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
    return " ".join(bit for bit in bits if bit)


def _entry_for_slot(sim, eid, slot):
    loadout = appearance_loadout_for(sim, eid, create=False)
    if loadout is None:
        return None
    instance_id = str(loadout.slots.get(slot) or "").strip()
    if not instance_id:
        return None
    inventory = _inventory_for(sim, eid)
    return inventory.find(instance_id=instance_id) if inventory else None


def _outfit_sentence(sim, eid):
    loadout = appearance_loadout_for(sim, eid, create=False)
    if loadout is None:
        return ""
    parts = []
    full_body = _entry_for_slot(sim, eid, "full_body")
    if full_body:
        phrase = _entry_phrase(full_body)
        if phrase:
            parts.append(phrase)
    else:
        top = _entry_for_slot(sim, eid, "top")
        bottom = _entry_for_slot(sim, eid, "bottom")
        top_phrase = _entry_phrase(top) if top else ""
        bottom_phrase = _entry_phrase(bottom) if bottom else ""
        if top_phrase:
            parts.append(top_phrase)
        if bottom_phrase:
            parts.append(bottom_phrase)
    outer = _entry_for_slot(sim, eid, "outer")
    if outer:
        phrase = _entry_phrase(outer)
        if phrase:
            parts.append(phrase)
    armor = sim.ecs.get(ArmorLoadout).get(eid) if sim is not None else None
    if armor and getattr(armor, "equipped_instance_id", None):
        name = _text(getattr(armor, "equipped_name", None) or getattr(armor, "equipped_item_id", "armor"))
        if name:
            parts.append(name)
    shoes = _entry_for_slot(sim, eid, "shoes")
    if shoes:
        phrase = _entry_phrase(shoes)
        if phrase:
            parts.append(phrase)
    if not parts:
        return ""
    if len(parts) == 1:
        return f"They are wearing {parts[0]}."
    return f"They are wearing {', '.join(parts[:-1])}, and {parts[-1]}."


def _adornment_sentence(sim, eid):
    bits = []
    for slot in ("hat", "earrings", "necklace", "bracelet", "ring_left", "ring_right"):
        entry = _entry_for_slot(sim, eid, slot)
        if not entry:
            continue
        phrase = _entry_phrase(entry, compact=True)
        if phrase:
            bits.append(phrase)
    if not bits:
        return ""
    if len(bits) == 1:
        return f"They have {bits[0]} on."
    return f"They have {', '.join(bits[:-1])}, and {bits[-1]} on."


def _salon_sentence(loadout):
    overrides = dict(getattr(loadout, "body_overrides", {}) or {})
    bits = []
    hair_style = _text(overrides.get("hair_style"))
    hair_color = _text(overrides.get("hair_color"))
    makeup = _text(overrides.get("makeup"))
    if hair_style and hair_color:
        bits.append(f"hair worn {hair_style} and colored {hair_color}")
    elif hair_style:
        bits.append(f"hair worn {hair_style}")
    elif hair_color:
        bits.append(f"hair colored {hair_color}")
    if makeup and makeup.lower() != "none":
        bits.append(f"{makeup} makeup")
    if not bits:
        return ""
    return "Salon styling: " + ", ".join(bits) + "."


def player_appearance_summary(sim, player_eid):
    identity = sim.ecs.get(CreatureIdentity).get(player_eid) if sim is not None else None
    base = ""
    if identity is not None:
        base = human_physical_summary(
            getattr(sim, "seed", 0),
            eid=player_eid,
            identity=identity,
            personal_name=getattr(identity, "personal_name", ""),
        )
    loadout = appearance_loadout_for(sim, player_eid, create=True)
    sentences = [base] if base else []
    salon = _salon_sentence(loadout)
    outfit = _outfit_sentence(sim, player_eid)
    adornment = _adornment_sentence(sim, player_eid)
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
    return rows


def player_appearance_color_key(sim, player_eid):
    loadout = appearance_loadout_for(sim, player_eid, create=False)
    if loadout is None:
        return None
    for slot in OUTFIT_COLOR_PRIORITY:
        entry = _entry_for_slot(sim, player_eid, slot)
        if not entry:
            continue
        profile = appearance_metadata_for_entry(entry)
        color = _key(profile.get("accent_color"))
        if color:
            return color
    return None


def apply_appearance_service(sim, eid, *, kind="", value="", prop=None):
    kind = _key(kind)
    value = _key(value)
    if kind not in STYLE_SERVICE_OPTIONS:
        return AppearanceEquipResult(False, reason="invalid_style_kind")
    if value not in STYLE_SERVICE_OPTIONS[kind]:
        return AppearanceEquipResult(False, reason="invalid_style_value")
    loadout = appearance_loadout_for(sim, eid, create=True)
    loadout.body_overrides[kind] = value
    sim.emit(Event(
        "appearance_style_updated",
        eid=eid,
        style_kind=kind,
        style_value=value,
        property_id=(prop or {}).get("id") if isinstance(prop, dict) else None,
    ))
    return AppearanceEquipResult(True, action="style_updated", item_name=value)
