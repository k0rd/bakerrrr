"""Deterministic item object profiles and item-backed fixture helpers."""

from __future__ import annotations

import copy
import hashlib
import json
import random
from collections.abc import Mapping
from typing import Any

from game.color_words import (
    approved_color_words,
    color_word_display_name,
    imported_color_words,
    normalize_color_word,
    render_key_for_color_word,
)


OBJECT_PROFILE_SCHEMA_VERSION = 1

OBJECT_PROFILE_FAMILIES: tuple[str, ...] = (
    "plants_pots",
    "tokens_charms",
    "tools_parts",
    "textiles",
    "paper_books",
    "containers",
    "light_ritual",
    "personal_home",
    "trade_work",
    "nature_finds",
    "medical_herbal",
)

OBJECT_PROFILE_SILHOUETTES: dict[str, tuple[str, ...]] = {
    "plants_pots": ("round_pot", "tall_pot", "moss_tray", "seed_jar", "hanging_planter"),
    "tokens_charms": ("coin", "tag", "ring_charm", "transit_token", "shrine_charm"),
    "tools_parts": ("wrench", "tool_roll", "wire_spool", "gauge", "knife_case"),
    "textiles": ("folded_scarf", "ribbon_bundle", "sash", "patched_cloth", "soft_wrap"),
    "paper_books": ("recipe_card", "ledger", "sealed_note", "map_scrap", "little_book"),
    "containers": ("tin", "crate", "basket", "lockbox", "bottle_jar"),
    "light_ritual": ("candle", "lantern", "incense_cup", "vigil_bowl", "oil_lamp"),
    "personal_home": ("mug", "comb", "mirror", "toy", "desk_ornament"),
    "trade_work": ("counter_bell", "claim_tag", "manifest_stamp", "order_ticket", "number_token"),
    "nature_finds": ("shell", "smooth_stone", "pressed_flower", "driftwood", "feather"),
    "medical_herbal": ("tincture_vial", "mortar_cup", "dried_bundle", "wrapped_poultice", "salve_tin"),
}

OBJECT_PROFILE_MATERIALS: tuple[str, ...] = (
    "ceramic",
    "wood",
    "brass",
    "glass",
    "cloth",
    "paper",
    "steel",
    "tin",
    "stone",
    "shell",
    "wax",
    "herb",
)

OBJECT_PROFILE_MOTIFS: tuple[str, ...] = (
    "none",
    "star",
    "stripe",
    "dot_ring",
    "crescent",
    "flower",
    "key_mark",
    "route_mark",
    "slash",
)

OBJECT_PROFILE_CONDITIONS: tuple[str, ...] = (
    "plain",
    "chipped",
    "polished",
    "wrapped",
    "dusty",
    "repaired",
    "cracked",
)

OBJECT_PROFILE_RARITIES: tuple[str, ...] = ("common", "uncommon", "rare", "unique")

OBJECT_PROFILE_COLORS: tuple[str, ...] = tuple(
    dict.fromkeys(approved_color_words(include_reserved=False) + imported_color_words())
)

OBJECT_PROFILE_ALLOWED_FIELDS: tuple[str, ...] = (
    "schema_version",
    "family",
    "silhouette",
    "material",
    "primary_color",
    "accent_color",
    "motif",
    "condition",
    "rarity",
    "placeable",
    "pickup_allowed",
    "display_name",
    "description",
    "display_glyph",
    "display_color",
    "future_tags",
)

OBJECT_PROFILE_OWNER_REVEAL_FIELDS: tuple[str, ...] = (
    "owner_eid",
    "owner_id",
    "owner_name",
    "npc_eid",
    "npc_id",
    "npc_name",
    "source_eid",
    "source_npc_eid",
    "relationship",
    "relationship_label",
    "belongs_to",
)

OBJECT_PROFILE_GLYPHS: dict[str, str] = {
    "plants_pots": "o",
    "tokens_charms": "*",
    "tools_parts": "t",
    "textiles": "{",
    "paper_books": "?",
    "containers": "c",
    "light_ritual": "v",
    "personal_home": "m",
    "trade_work": "j",
    "nature_finds": ",",
    "medical_herbal": "!",
}

OBJECT_PROFILE_COLOR_KEYS: dict[str, str] = {
    "plants_pots": "world_object_plant",
    "tokens_charms": "world_object_charm",
    "tools_parts": "world_object_tool",
    "textiles": "world_object_textile",
    "paper_books": "world_object_paper",
    "containers": "world_object_container",
    "light_ritual": "world_object_light",
    "personal_home": "world_object_home",
    "trade_work": "world_object_trade",
    "nature_finds": "world_object_nature",
    "medical_herbal": "world_object_medical",
}

OBJECT_PROFILE_COLOR_WORD_KEYS: dict[str, str] = {
    word: render_key_for_color_word(word, domain="world_object") or "world_object_home"
    for word in OBJECT_PROFILE_COLORS
}


def _text(value: Any, default: str = "") -> str:
    text = str(value if value is not None else "").strip().lower()
    return text or str(default)


def _stable_seed(*parts: Any) -> int:
    payload = json.dumps(parts, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return int(hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16], 16)


def _identifier_list(value: Any, *, limit: int = 8) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        return ()
    parsed: list[str] = []
    for raw in value:
        token = _text(raw)
        if not token or not token.replace("_", "").isalnum():
            continue
        if token not in parsed:
            parsed.append(token)
        if len(parsed) >= limit:
            break
    return tuple(parsed)


def default_object_profile_for_family(family: str = "personal_home") -> dict[str, Any]:
    family_key = _text(family, "personal_home")
    if family_key not in OBJECT_PROFILE_FAMILIES:
        family_key = "personal_home"
    return {
        "schema_version": OBJECT_PROFILE_SCHEMA_VERSION,
        "family": family_key,
        "silhouette": OBJECT_PROFILE_SILHOUETTES[family_key][0],
        "material": "ceramic" if family_key in {"plants_pots", "personal_home"} else "paper",
        "primary_color": "blue",
        "accent_color": "white",
        "motif": "none",
        "condition": "plain",
        "rarity": "common",
        "placeable": False,
        "pickup_allowed": True,
        "display_name": "",
        "description": "",
        "display_glyph": OBJECT_PROFILE_GLYPHS[family_key],
        "display_color": OBJECT_PROFILE_COLOR_KEYS[family_key],
        "future_tags": (),
    }


def object_profile_validation_errors(value: Any, *, stack_max: int | None = None) -> list[tuple[str, str]]:
    errors: list[tuple[str, str]] = []
    if value in (None, ""):
        return errors
    if not isinstance(value, Mapping):
        return [("$", "object_profile must be an object")]

    allowed = set(OBJECT_PROFILE_ALLOWED_FIELDS)
    forbidden = set(OBJECT_PROFILE_OWNER_REVEAL_FIELDS)
    for raw_key in value:
        key = str(raw_key or "").strip()
        path = f"$.object_profile.{key}" if key else "$.object_profile"
        key_lower = key.lower()
        if key_lower in forbidden:
            errors.append((path, "owner or relationship fields are reserved for future behavior layers"))
        elif key not in allowed:
            errors.append((path, "unknown object_profile field"))

    family = _text(value.get("family"), "personal_home")
    if family not in OBJECT_PROFILE_FAMILIES:
        errors.append(("$.object_profile.family", f"family must be one of {list(OBJECT_PROFILE_FAMILIES)}"))
    silhouettes = OBJECT_PROFILE_SILHOUETTES.get(family, ())
    silhouette = _text(value.get("silhouette"), silhouettes[0] if silhouettes else "")
    if silhouette not in silhouettes:
        errors.append(("$.object_profile.silhouette", f"silhouette must match the selected family"))
    material = _text(value.get("material"), "ceramic")
    if material not in OBJECT_PROFILE_MATERIALS:
        errors.append(("$.object_profile.material", f"material must be one of {list(OBJECT_PROFILE_MATERIALS)}"))
    for field in ("primary_color", "accent_color"):
        color = normalize_color_word(_text(value.get(field), "blue"))
        if color not in OBJECT_PROFILE_COLORS:
            errors.append((f"$.object_profile.{field}", f"{field} must be one of {list(OBJECT_PROFILE_COLORS)}"))
    motif = _text(value.get("motif"), "none")
    if motif not in OBJECT_PROFILE_MOTIFS:
        errors.append(("$.object_profile.motif", f"motif must be one of {list(OBJECT_PROFILE_MOTIFS)}"))
    condition = _text(value.get("condition"), "plain")
    if condition not in OBJECT_PROFILE_CONDITIONS:
        errors.append(("$.object_profile.condition", f"condition must be one of {list(OBJECT_PROFILE_CONDITIONS)}"))
    rarity = _text(value.get("rarity"), "common")
    if rarity not in OBJECT_PROFILE_RARITIES:
        errors.append(("$.object_profile.rarity", f"rarity must be one of {list(OBJECT_PROFILE_RARITIES)}"))
    for field in ("placeable", "pickup_allowed"):
        if field in value and not isinstance(value.get(field), bool):
            errors.append((f"$.object_profile.{field}", f"{field} must be true or false"))
    for field in ("display_name", "description", "display_color"):
        if field in value and value.get(field) is not None and not isinstance(value.get(field), str):
            errors.append((f"$.object_profile.{field}", f"{field} must be text"))
    if "display_glyph" in value:
        glyph = str(value.get("display_glyph", "") or "")
        if len(glyph) != 1:
            errors.append(("$.object_profile.display_glyph", "display_glyph must be one character"))
    if "future_tags" in value:
        if not isinstance(value.get("future_tags"), (list, tuple)):
            errors.append(("$.object_profile.future_tags", "future_tags must be a list of identifiers"))
    try:
        stack_max_int = int(stack_max) if stack_max is not None else None
    except (TypeError, ValueError):
        stack_max_int = None
    if bool(value.get("placeable")) and stack_max_int is not None and stack_max_int != 1:
        errors.append(("$.object_profile.placeable", "placeable object-profile items must have stack_max 1"))
    return errors


def normalize_object_profile(value: Any, *, item_id: str = "", tags: tuple[str, ...] | list[str] = ()) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    family = _text(value.get("family"), "")
    tag_set = {_text(tag) for tag in tags if _text(tag)}
    if not family:
        if "plant_pot" in tag_set or "cultivation" in tag_set:
            family = "plants_pots"
        elif "medical" in tag_set or "herbal_ingredient" in tag_set:
            family = "medical_herbal"
        elif "tool" in tag_set:
            family = "tools_parts"
        elif "token" in tag_set or "keepsake" in tag_set:
            family = "tokens_charms"
        else:
            family = "personal_home"
    if family not in OBJECT_PROFILE_FAMILIES:
        family = "personal_home"

    default = default_object_profile_for_family(family)
    silhouettes = OBJECT_PROFILE_SILHOUETTES[family]
    profile = dict(default)
    profile["schema_version"] = OBJECT_PROFILE_SCHEMA_VERSION
    profile["family"] = family
    profile["silhouette"] = _text(value.get("silhouette"), profile["silhouette"])
    if profile["silhouette"] not in silhouettes:
        profile["silhouette"] = silhouettes[0]
    profile["material"] = _text(value.get("material"), profile["material"])
    if profile["material"] not in OBJECT_PROFILE_MATERIALS:
        profile["material"] = default["material"]
    for field in ("primary_color", "accent_color"):
        profile[field] = normalize_color_word(_text(value.get(field), profile[field]))
        if profile[field] not in OBJECT_PROFILE_COLORS:
            profile[field] = default[field]
    profile["motif"] = _text(value.get("motif"), profile["motif"])
    if profile["motif"] not in OBJECT_PROFILE_MOTIFS:
        profile["motif"] = "none"
    profile["condition"] = _text(value.get("condition"), profile["condition"])
    if profile["condition"] not in OBJECT_PROFILE_CONDITIONS:
        profile["condition"] = "plain"
    profile["rarity"] = _text(value.get("rarity"), profile["rarity"])
    if profile["rarity"] not in OBJECT_PROFILE_RARITIES:
        profile["rarity"] = "common"
    profile["placeable"] = bool(value.get("placeable", default["placeable"]))
    profile["pickup_allowed"] = bool(value.get("pickup_allowed", default["pickup_allowed"]))
    profile["display_name"] = str(value.get("display_name", "") or "").strip()
    profile["description"] = str(value.get("description", "") or "").strip()
    glyph = str(value.get("display_glyph", "") or "").strip()
    profile["display_glyph"] = glyph[:1] if glyph else OBJECT_PROFILE_GLYPHS[family]
    display_color = _text(value.get("display_color"), "")
    if not display_color.startswith("world_object_"):
        display_color = OBJECT_PROFILE_COLOR_WORD_KEYS.get(profile["primary_color"]) or OBJECT_PROFILE_COLOR_KEYS[family]
    profile["display_color"] = display_color
    profile["future_tags"] = _identifier_list(value.get("future_tags"))
    return profile


def generated_object_profile(seed: Any, *, family: str | None = None) -> dict[str, Any]:
    rng = random.Random(_stable_seed("object-profile", seed))
    family_key = _text(family, "")
    if family_key not in OBJECT_PROFILE_FAMILIES:
        family_key = rng.choice(OBJECT_PROFILE_FAMILIES)
    silhouette = rng.choice(OBJECT_PROFILE_SILHOUETTES[family_key])
    material_pool = {
        "plants_pots": ("ceramic", "wood", "glass"),
        "tokens_charms": ("brass", "steel", "wood", "stone"),
        "tools_parts": ("steel", "wood", "brass"),
        "textiles": ("cloth",),
        "paper_books": ("paper", "cloth"),
        "containers": ("tin", "wood", "glass", "ceramic"),
        "light_ritual": ("wax", "brass", "glass", "ceramic"),
        "personal_home": ("ceramic", "wood", "glass", "cloth"),
        "trade_work": ("paper", "brass", "steel", "wood"),
        "nature_finds": ("shell", "stone", "wood", "herb"),
        "medical_herbal": ("glass", "tin", "herb", "cloth"),
    }.get(family_key, OBJECT_PROFILE_MATERIALS)
    material = rng.choice(tuple(material for material in material_pool if material in OBJECT_PROFILE_MATERIALS))
    profile = default_object_profile_for_family(family_key)
    profile.update({
        "silhouette": silhouette,
        "material": material,
        "primary_color": rng.choice(OBJECT_PROFILE_COLORS),
        "accent_color": rng.choice(OBJECT_PROFILE_COLORS),
        "motif": rng.choice(OBJECT_PROFILE_MOTIFS),
        "condition": rng.choice(OBJECT_PROFILE_CONDITIONS),
        "rarity": rng.choices(OBJECT_PROFILE_RARITIES, weights=(62, 26, 10, 2), k=1)[0],
        "placeable": True,
        "pickup_allowed": True,
    })
    profile["display_color"] = OBJECT_PROFILE_COLOR_WORD_KEYS.get(profile["primary_color"], OBJECT_PROFILE_COLOR_KEYS[family_key])
    return normalize_object_profile(profile)


def object_profile_for_item(item_def: Mapping[str, Any] | None, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    metadata = metadata if isinstance(metadata, Mapping) else {}
    if isinstance(metadata.get("object_profile"), Mapping):
        return normalize_object_profile(metadata.get("object_profile"), item_id=metadata.get("item_id", ""))
    if isinstance(item_def, Mapping):
        return normalize_object_profile(item_def.get("object_profile"), item_id=item_def.get("id", ""), tags=item_def.get("tags", ()))
    return {}


def object_visual_signature(item_id: str, profile: Mapping[str, Any] | None, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    profile = normalize_object_profile(profile or {})
    if not profile:
        profile = generated_object_profile(item_id or "object")
    seed_token = (metadata or {}).get("visual_seed") if isinstance(metadata, Mapping) else None
    seed = _stable_seed("visual-signature", item_id, profile, seed_token)
    detail_seed = seed & 0xFFFF_FFFF
    family = profile["family"]
    return {
        "schema_version": OBJECT_PROFILE_SCHEMA_VERSION,
        "family": family,
        "silhouette": profile["silhouette"],
        "material": profile["material"],
        "primary_color": profile["primary_color"],
        "accent_color": profile["accent_color"],
        "motif": profile["motif"],
        "condition": profile["condition"],
        "rarity": profile["rarity"],
        "glyph": profile.get("display_glyph") or OBJECT_PROFILE_GLYPHS[family],
        "color": profile.get("display_color") or OBJECT_PROFILE_COLOR_KEYS[family],
        "semantic_id": f"world_object_{family}",
        "detail_seed": int(detail_seed),
    }


def object_profile_effects(profile: Mapping[str, Any] | None, signature: Mapping[str, Any] | None = None) -> tuple[str, ...]:
    profile = normalize_object_profile(profile or {})
    signature = signature if isinstance(signature, Mapping) else object_visual_signature("", profile)
    parts = (
        f"object_family_{_text(signature.get('family'), profile.get('family'))}",
        f"object_silhouette_{_text(signature.get('silhouette'), profile.get('silhouette'))}",
        f"object_material_{_text(signature.get('material'), profile.get('material'))}",
        f"object_motif_{_text(signature.get('motif'), profile.get('motif'))}",
        f"object_condition_{_text(signature.get('condition'), profile.get('condition'))}",
        f"object_rarity_{_text(signature.get('rarity'), profile.get('rarity'))}",
        f"object_seed_{int(signature.get('detail_seed', 0) or 0) % 997}",
    )
    return tuple(part for part in parts if part and not part.endswith("_"))


def object_profile_display_text(profile: Mapping[str, Any] | None, *, fallback_name: str = "object") -> str:
    profile = normalize_object_profile(profile or {})
    if not profile:
        return str(fallback_name or "object")
    explicit = str(profile.get("display_name", "") or "").strip()
    if explicit:
        return explicit
    condition = profile.get("condition", "plain")
    primary = color_word_display_name(profile.get("primary_color", ""))
    material = profile.get("material", "")
    silhouette = str(profile.get("silhouette", "object") or "object").replace("_", " ")
    motif = str(profile.get("motif", "none") or "none").replace("_", " ")
    parts = []
    if condition and condition != "plain":
        parts.append(condition)
    if primary:
        parts.append(primary)
    if material:
        parts.append(material)
    parts.append(silhouette)
    if motif and motif != "none":
        parts.append(f"with a {motif}")
    return " ".join(str(part) for part in parts if str(part).strip())


def item_backed_fixture_metadata(item_entry: Mapping[str, Any], item_def: Mapping[str, Any], *, tick: int = 0, source: str = "manual") -> dict[str, Any]:
    metadata = item_entry.get("metadata") if isinstance(item_entry.get("metadata"), Mapping) else {}
    profile = object_profile_for_item(item_def, metadata)
    signature = object_visual_signature(str(item_entry.get("item_id", item_def.get("id", ""))), profile, metadata)
    display_name = object_profile_display_text(profile, fallback_name=item_def.get("name", "Object"))
    return {
        "archetype": "item_backed_fixture",
        "fixture_type": "item_backed_object",
        "item_backed_fixture": True,
        "source_item_id": str(item_entry.get("item_id", item_def.get("id", "")) or "").strip().lower(),
        "source_item_instance_id": str(item_entry.get("instance_id", "") or "").strip(),
        "source_item_owner_eid": item_entry.get("owner_eid"),
        "source_item_owner_tag": str(item_entry.get("owner_tag", "") or "").strip(),
        "source_item_metadata": copy.deepcopy(dict(metadata)),
        "object_profile": copy.deepcopy(profile),
        "visual_signature": copy.deepcopy(signature),
        "display_glyph": str(signature.get("glyph", profile.get("display_glyph", "o")))[:1] or "o",
        "display_color": str(signature.get("color", profile.get("display_color", "world_object_home"))),
        "display_name": display_name,
        "display_description": str(profile.get("description", "") or "").strip(),
        "pickup_allowed": bool(profile.get("pickup_allowed", True)),
        "placement_source": str(source or "manual"),
        "placed_tick": int(tick or 0),
        "public": True,
        "cover_kind": "none",
        "cover_value": 0.0,
        "cover_intended": False,
    }


def property_is_item_backed_fixture(prop: Mapping[str, Any] | None) -> bool:
    if not isinstance(prop, Mapping):
        return False
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), Mapping) else {}
    return bool(metadata.get("item_backed_fixture"))


def _item_def(item_catalog: Mapping[str, Any] | None, item_id: str) -> dict[str, Any]:
    if isinstance(item_catalog, Mapping):
        row = item_catalog.get(str(item_id or "").strip().lower())
        if isinstance(row, Mapping):
            return dict(row)
    return {}


def item_entry_can_be_placed(item_entry: Mapping[str, Any] | None, item_def: Mapping[str, Any] | None) -> tuple[bool, str]:
    if not isinstance(item_entry, Mapping):
        return False, "missing_item"
    item_def = item_def if isinstance(item_def, Mapping) else {}
    try:
        quantity = int(item_entry.get("quantity", 1) or 1)
    except (TypeError, ValueError):
        quantity = 1
    if quantity != 1:
        return False, "stacked_item"
    try:
        stack_max = int(item_def.get("stack_max", 1) or 1)
    except (TypeError, ValueError):
        stack_max = 1
    if stack_max != 1:
        return False, "stackable_item"
    tags = {_text(tag) for tag in item_def.get("tags", ()) if _text(tag)}
    metadata = item_entry.get("metadata") if isinstance(item_entry.get("metadata"), Mapping) else {}
    if bool(metadata.get("appearance_worn")):
        return False, "worn_item"
    if tags.intersection({"quest", "objective", "critical"}) or bool(metadata.get("critical_item")):
        return False, "critical_item"
    profile = object_profile_for_item(item_def, metadata)
    if not profile or not bool(profile.get("placeable")):
        return False, "not_placeable"
    return True, ""


def can_place_item_backed_fixture(sim: Any, item_entry: Mapping[str, Any] | None, item_def: Mapping[str, Any] | None, x: int, y: int, z: int = 0) -> tuple[bool, str]:
    ok, reason = item_entry_can_be_placed(item_entry, item_def)
    if not ok:
        return False, reason
    tile = sim.tilemap.tile_at(int(x), int(y), int(z)) if hasattr(sim, "tilemap") else None
    if tile is None:
        return False, "no_tile"
    if not bool(getattr(tile, "walkable", False)):
        return False, "blocked_tile"
    if hasattr(sim, "property_at") and sim.property_at(int(x), int(y), int(z)):
        return False, "occupied_fixture"
    if hasattr(sim, "property_covering") and sim.property_covering(int(x), int(y), int(z)):
        return False, "covered_property"
    if hasattr(sim, "ground_items_at") and sim.ground_items_at(int(x), int(y), z=int(z)):
        return False, "ground_item_present"
    return True, ""


def place_item_backed_fixture(sim: Any, inventory: Any, item_entry: Mapping[str, Any], x: int, y: int, z: int = 0, *, item_catalog: Mapping[str, Any] | None = None, source: str = "manual") -> dict[str, Any]:
    item_id = str(item_entry.get("item_id", "") or "").strip().lower()
    item_def = _item_def(item_catalog, item_id)
    ok, reason = can_place_item_backed_fixture(sim, item_entry, item_def, x, y, z)
    if not ok:
        return {"ok": False, "reason": reason}
    removed = inventory.remove_item(instance_id=item_entry.get("instance_id"), quantity=1) if inventory else None
    if not removed:
        return {"ok": False, "reason": "remove_failed"}
    metadata = item_backed_fixture_metadata(removed, item_def, tick=int(getattr(sim, "tick", 0)), source=source)
    name = metadata.get("display_name") or item_def.get("name", "Placed Object")
    property_id = sim.register_property(
        name=str(name).strip() or "Placed Object",
        kind="fixture",
        x=int(x),
        y=int(y),
        z=int(z),
        owner_eid=None,
        owner_tag="public",
        metadata=metadata,
    )
    return {"ok": True, "property_id": property_id, "item": removed, "metadata": metadata}


def pickup_item_backed_fixture(sim: Any, inventory: Any, property_id: str, *, item_catalog: Mapping[str, Any] | None = None) -> dict[str, Any]:
    prop = getattr(sim, "properties", {}).get(str(property_id)) if sim is not None else None
    if not property_is_item_backed_fixture(prop):
        return {"ok": False, "reason": "not_item_backed_fixture"}
    metadata = prop.get("metadata") if isinstance(prop.get("metadata"), Mapping) else {}
    if not bool(metadata.get("pickup_allowed", True)):
        return {"ok": False, "reason": "pickup_blocked"}
    item_id = str(metadata.get("source_item_id", "") or "").strip().lower()
    if not item_id:
        return {"ok": False, "reason": "missing_item"}
    item_def = _item_def(item_catalog, item_id)
    item_metadata = copy.deepcopy(dict(metadata.get("source_item_metadata") or {}))
    if "object_profile" not in item_metadata and isinstance(metadata.get("object_profile"), Mapping):
        item_metadata["object_profile"] = copy.deepcopy(dict(metadata.get("object_profile")))
    if "visual_signature" not in item_metadata and isinstance(metadata.get("visual_signature"), Mapping):
        item_metadata["visual_signature"] = copy.deepcopy(dict(metadata.get("visual_signature")))
    if "object_context" not in item_metadata and isinstance(metadata.get("object_context"), Mapping):
        item_metadata["object_context"] = copy.deepcopy(dict(metadata.get("object_context")))
    if not str(item_metadata.get("display_name", "") or "").strip():
        fixture_display_name = str(metadata.get("display_name", "") or "").strip()
        if fixture_display_name:
            item_metadata["display_name"] = fixture_display_name
        elif isinstance(item_metadata.get("object_profile"), Mapping):
            item_metadata["display_name"] = object_profile_display_text(
                item_metadata.get("object_profile"),
                fallback_name=item_def.get("name", "Object"),
            )
    instance_id = str(metadata.get("source_item_instance_id", "") or "").strip() or None
    added, new_instance_id = inventory.add_item(
        item_id,
        quantity=1,
        stack_max=int(item_def.get("stack_max", 1) or 1),
        instance_id=instance_id,
        instance_factory=getattr(sim, "new_item_instance_id", None),
        owner_eid=metadata.get("source_item_owner_eid"),
        owner_tag=str(metadata.get("source_item_owner_tag", "") or "").strip() or None,
        metadata=item_metadata,
    ) if inventory else (False, None)
    if not added:
        return {"ok": False, "reason": "inventory_full"}
    removed = sim.remove_property(str(property_id))
    return {"ok": True, "item_id": item_id, "instance_id": new_instance_id, "removed_property": removed}
