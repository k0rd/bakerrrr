from __future__ import annotations

from dataclasses import dataclass

from engine.buildings import building_exterior_profile
from game.components import AI, CreatureIdentity, Render, Vitality
from game.property_runtime import (
    building_id_from_structure,
    finance_services_for_property,
    property_aperture_at,
    property_covering,
    property_fixture_type,
    property_is_public,
    property_metadata,
)
from game.semantic_catalog import get_runtime_semantic_catalog

DISTRICT_GLYPHS = {
    "industrial": ":",
    "residential": ".",
    "downtown": "%",
    "slums": ",",
    "corporate": ";",
    "military": "=",
    "entertainment": "*",
}

AREA_GLYPHS = {
    "city": ".",
    "frontier": ",",
    "wilderness": "'",
    "coastal": "_",
}

DISTRICT_FLOOR_COLORS = {
    "industrial": "floor_industrial",
    "residential": "floor_residential",
    "downtown": "floor_downtown",
    "slums": "floor_slums",
    "corporate": "floor_corporate",
    "military": "floor_military",
    "entertainment": "floor_entertainment",
}

AREA_FLOOR_COLORS = {
    "city": "floor_residential",
    "frontier": "floor_frontier",
    "wilderness": "floor_wilderness",
    "coastal": "floor_coastal",
}

PROPERTY_GLYPHS = {
    "building": "B",
    "fixture": "F",
    "asset": "A",
    "vehicle": "&",
}

PROPERTY_COLORS = {
    "building": "property_building",
    "fixture": "property_fixture",
    "asset": "property_asset",
    "vehicle": "vehicle_parked",
}

PROPERTY_ARCHETYPE_DISPLAY = {
    "bank": ("$", "property_service"),
    "brokerage": ("$", "property_service"),
    "pawn_shop": ("$", "property_service"),
    "pharmacy": ("M", "item_medical"),
    "backroom_clinic": ("M", "item_medical"),
    "biotech_clinic": ("M", "item_medical"),
    "field_hospital": ("M", "item_medical"),
    "tide_station": ("M", "item_medical"),
    "herbalist_camp": ("M", "item_medical"),
    "casino": ("C", "building_roof_entertainment"),
    "checkpoint": ("G", "building_roof_secure"),
    "armory": ("G", "building_roof_secure"),
    "barracks": ("G", "building_roof_secure"),
    "courthouse": ("G", "building_roof_secure"),
    "jail": ("G", "building_roof_secure"),
    "prison": ("G", "building_roof_secure"),
    "tower": ("G", "building_roof_secure"),
    "command_center": ("G", "building_roof_secure"),
    "supply_bunker": ("G", "building_roof_secure"),
    "nightclub": ("N", "building_roof_entertainment"),
    "bar": ("N", "building_roof_entertainment"),
    "theater": ("N", "building_roof_entertainment"),
    "music_venue": ("N", "building_roof_entertainment"),
    "gaming_hall": ("N", "building_roof_entertainment"),
    "karaoke_box": ("N", "building_roof_entertainment"),
    "pool_hall": ("N", "building_roof_entertainment"),
    "gallery": ("N", "building_roof_entertainment"),
    "tavern": ("T", "building_roof_entertainment"),
    "restaurant": ("R", "building_roof_storefront"),
    "street_kitchen": ("R", "building_roof_storefront"),
    "soup_kitchen": ("R", "building_roof_storefront"),
    "roadhouse": ("R", "building_roof_storefront"),
    "bait_shop": ("R", "building_roof_storefront"),
    "auto_garage": ("V", "property_asset"),
    "truck_stop": ("V", "property_asset"),
    "dock_shack": ("V", "property_asset"),
    "ferry_post": ("V", "property_asset"),
    "metro_exchange": ("V", "property_asset"),
    "tool_depot": ("T", "building_roof_industrial"),
    "hardware_store": ("T", "building_roof_industrial"),
    "chop_shop": ("T", "building_roof_industrial"),
    "junk_market": ("T", "building_roof_industrial"),
    "cold_storage": ("T", "building_roof_industrial"),
    "house": ("H", "building_roof_residential"),
    "apartment": ("H", "building_roof_residential"),
    "tenement": ("H", "building_roof_residential"),
    "hotel": ("H", "building_roof_residential"),
    "flophouse": ("H", "building_roof_residential"),
    "ranger_hut": ("H", "building_roof_residential"),
    "ruin_shelter": ("H", "building_roof_residential"),
    "field_camp": ("H", "building_roof_residential"),
    "survey_post": ("H", "building_roof_residential"),
    "beacon_house": ("H", "building_roof_residential"),
    "office": ("O", "building_roof_civic"),
    "courier_office": ("O", "building_roof_civic"),
    "recruitment_office": ("O", "building_roof_civic"),
    "media_lab": ("O", "building_roof_civic"),
    "data_center": ("O", "building_roof_civic"),
    "server_hub": ("O", "building_roof_civic"),
}

PROPERTY_FIXTURE_SEMANTICS = {
    "bench": "prop_cover_bench",
    "bus_stop": "prop_cover_shelter",
    "junction_box": "prop_cover_junction",
    "planter_box": "prop_cover_planter",
    "drift_fence": "prop_cover_fence",
    "transformer": "prop_cover_transformer",
    "field_cache_box": "prop_cover_cache",
    "water_tank": "prop_cover_tank",
}

SPECIAL_TILE_RENDER_STYLES = {
    "B": ("#", "building_edge"),
    "b": ("=", "building_fill"),
    "#": ("#", "terrain_block"),
    ",": (",", "terrain_brush"),
    "^": ("^", "terrain_rock"),
    "~": ("~", "terrain_water"),
    "_": ("_", "terrain_salt"),
    "=": ("=", "terrain_road"),
    "+": ("+", "feature_door"),
    "/": ("/", "feature_breach"),
    ":": (":", "transit"),
    ">": (">", "transit"),
    "<": ("<", "transit"),
    "E": ("E", "transit"),
}

FEATURE_PRIORITY_TILE_GLYPHS = {'"', "+", "/", ":", "=", "S", ">", "<", "E"}
CAT_COAT_COLOR = {
    "orange": "cat_orange",
    "ginger": "cat_orange",
    "orange_tabby": "cat_orange",
    "tabby": "cat_tabby",
    "brown_tabby": "cat_tabby",
    "gray_tabby": "cat_gray",
    "grey_tabby": "cat_gray",
    "black": "cat_black",
    "white": "cat_white",
    "calico": "cat_calico",
    "tuxedo": "cat_tuxedo",
    "gray": "cat_gray",
    "grey": "cat_gray",
    "purple": "cat_purple",
}

ENTITY_TAXONOMY_SEMANTICS = {
    "feline": "entity_feline",
    "canine": "entity_canine",
    "avian": "entity_avian",
    "insect": "entity_insect",
    "arachnid": "entity_arachnid",
    "rodent": "entity_rodent",
    "reptile": "entity_reptile",
    "amphibian": "entity_amphibian",
    "fish": "entity_fish",
    "ungulate": "entity_ungulate",
    "other": "entity_other",
}


@dataclass(frozen=True)
class AppearanceSnapshot:
    glyph: str = "?"
    color: str | None = None
    semantic_id: str | None = None
    layer: str | None = None
    priority: int | None = None
    attrs: int = 0
    effects: tuple[str, ...] = ()
    visible: bool = True
    overlays: tuple[dict, ...] = ()


def _normalize_effects(effects):
    return tuple(
        dict.fromkeys(
            str(effect).strip().lower()
            for effect in (effects or ())
            if str(effect).strip()
        )
    )


def _normalize_overlays(overlays):
    normalized = []
    for overlay in overlays or ():
        if not isinstance(overlay, dict):
            continue
        glyph = str(overlay.get("glyph", "") or "")[:1]
        semantic_id = str(overlay.get("semantic_id", "") or "").strip() or None
        if not glyph and not semantic_id:
            continue
        normalized.append({
            "glyph": glyph or " ",
            "color": overlay.get("color"),
            "semantic_id": semantic_id,
            "attrs": int(overlay.get("attrs", 0) or 0),
            "effects": _normalize_effects(overlay.get("effects", ())),
            "visible": bool(overlay.get("visible", True)),
        })
    return tuple(normalized)


def _snapshot(
    glyph,
    *,
    color=None,
    semantic_id=None,
    layer=None,
    priority=None,
    attrs=0,
    effects=None,
    visible=True,
    overlays=None,
):
    return AppearanceSnapshot(
        glyph=str(glyph)[:1] or "?",
        color=(str(color).strip() if isinstance(color, str) else color),
        semantic_id=str(semantic_id).strip() if semantic_id else None,
        layer=str(layer).strip().lower() if str(layer or "").strip() else None,
        priority=None if priority is None else int(priority),
        attrs=int(attrs or 0),
        effects=_normalize_effects(effects),
        visible=bool(visible),
        overlays=_normalize_overlays(overlays),
    )


def _semantic_snapshot(
    glyph,
    *,
    color=None,
    semantic_id=None,
    catalog=None,
    preferred_categories=(),
    layer=None,
    priority=None,
    attrs=0,
    effects=None,
    visible=True,
    overlays=None,
):
    catalog = catalog or get_runtime_semantic_catalog()
    resolved_semantic_id = str(semantic_id or "").strip() or catalog.semantic_id_for(
        glyph,
        color,
        preferred_categories=preferred_categories,
    )
    render_profile = catalog.render_defaults_for_semantic(
        resolved_semantic_id,
        fallback_categories=preferred_categories,
    )
    resolved_layer = layer if layer is not None else render_profile.get("layer")
    resolved_priority = priority if priority is not None else render_profile.get("priority", 0)
    return _snapshot(
        glyph,
        color=color,
        semantic_id=resolved_semantic_id,
        layer=resolved_layer,
        priority=resolved_priority,
        attrs=attrs,
        effects=effects,
        visible=visible,
        overlays=overlays,
    )


def _property_cover_overlays(prop):
    if not isinstance(prop, dict):
        return ()
    kind = str(prop.get("kind", "") or "").strip().lower()
    if kind not in {"fixture", "asset"}:
        return ()

    metadata = property_metadata(prop)
    if not isinstance(metadata, dict):
        return ()

    cover_kind = str(metadata.get("cover_kind", "") or "").strip().lower()
    try:
        cover_value = float(metadata.get("cover_value", 0.0) or 0.0)
    except (TypeError, ValueError):
        cover_value = 0.0
    cover_value = max(0.0, min(0.95, cover_value))
    cover_intended = bool(metadata.get("cover_intended"))

    if cover_kind == "full" or cover_value >= 0.5:
        semantic_id = "cover_rating_full"
    elif cover_intended or cover_value >= 0.4:
        semantic_id = "cover_rating_low"
    else:
        return ()

    return (
        {
            "glyph": " ",
            "semantic_id": semantic_id,
        },
    )


def _owner_appearance(owner, fallback_glyph="?"):
    if owner is None:
        return _snapshot(fallback_glyph)
    glyph = str(getattr(owner, "glyph", fallback_glyph) or fallback_glyph)[:1] or fallback_glyph
    return _snapshot(
        glyph,
        color=getattr(owner, "color", None),
        semantic_id=getattr(owner, "semantic_id", None),
        layer=getattr(owner, "layer", None),
        priority=getattr(owner, "priority", None),
        attrs=getattr(owner, "attrs", 0),
        effects=getattr(owner, "effects", ()),
        visible=getattr(owner, "visible", True),
        overlays=getattr(owner, "overlays", ()),
    )


def _merge_snapshots(base, override):
    if override is None:
        return base
    if base is None:
        return override
    return AppearanceSnapshot(
        glyph=str(getattr(override, "glyph", "") or getattr(base, "glyph", "?"))[:1] or getattr(base, "glyph", "?"),
        color=override.color if override.color is not None else base.color,
        semantic_id=override.semantic_id or base.semantic_id,
        layer=override.layer if override.layer is not None else base.layer,
        priority=override.priority if override.priority is not None else base.priority,
        attrs=int(base.attrs or 0) | int(override.attrs or 0),
        effects=tuple(dict.fromkeys(tuple(base.effects or ()) + tuple(override.effects or ()))),
        visible=bool(base.visible) and bool(override.visible),
        overlays=tuple(base.overlays or ()) + tuple(override.overlays or ()),
    )


def creature_color_key(identity, *, role=""):
    if not identity:
        return None

    taxonomy = str(getattr(identity, "taxonomy_class", "") or "").strip().lower()
    common_name = str(getattr(identity, "common_name", "") or "").strip().lower()
    species = str(getattr(identity, "species", "") or "").strip().lower()
    coat = str(getattr(identity, "coat_variant", "") or "").strip().lower()
    role = str(role or "").strip().lower()

    if taxonomy == "hominid":
        if role == "guard":
            return "guard"
        if role == "scout":
            return "scout"
        return "human"

    if taxonomy == "feline":
        if coat:
            mapped = CAT_COAT_COLOR.get(coat)
            if mapped:
                return mapped
        if "orange" in common_name or "ginger" in common_name:
            return "cat_orange"
        if "black" in common_name:
            return "cat_black"
        if "calico" in common_name:
            return "cat_calico"
        if "tabby" in common_name:
            return "cat_tabby"
        if species in {"felis catus", "felis silvestris catus"}:
            return "cat_tabby"
        return "feline"

    taxonomy_colors = {
        "canine": "canine",
        "avian": "avian",
        "insect": "insect",
        "arachnid": "insect",
        "rodent": "rodent",
        "reptile": "reptile",
        "amphibian": "amphibian",
        "fish": "fish",
        "ungulate": "ungulate",
        "other": "other",
    }
    return taxonomy_colors.get(taxonomy)


def _entity_state_semantic(identity, vitality):
    if vitality is None:
        return None
    if bool(getattr(vitality, "downed", False)):
        return None
    try:
        hp = int(getattr(vitality, "hp", 0) or 0)
    except (TypeError, ValueError):
        hp = 0
    if hp > 0:
        return None
    taxonomy = str(getattr(identity, "taxonomy_class", "") or "").strip().lower() or "other"
    if taxonomy == "hominid":
        return "entity_corpse_hominid"
    return "entity_corpse_nonhuman"


def _entity_state_overlays(vitality):
    if vitality is None:
        return ()
    if not bool(getattr(vitality, "downed", False)):
        return ()
    return ({"glyph": " ", "semantic_id": "entity_state_downed"},)


def entity_default_snapshot(identity, *, role="", player=False, catalog=None):
    catalog = catalog or get_runtime_semantic_catalog()

    if player:
        return _semantic_snapshot(
            "@",
            color="player",
            semantic_id="entity_player",
            catalog=catalog,
            preferred_categories=("entities",),
        )

    if not identity:
        return _snapshot("?")

    taxonomy = str(getattr(identity, "taxonomy_class", "") or "").strip().lower() or "other"
    glyph = str(identity.taxonomy_glyph(fallback="O"))[:1] or "O"
    color = creature_color_key(identity, role=role)
    semantic_id = None

    if taxonomy == "hominid":
        glyph = "@"
        color = color or "human"
        semantic_id = catalog.semantic_id_for_key("entities", "hominid", color, allow_defaults=True)
    elif taxonomy in ENTITY_TAXONOMY_SEMANTICS:
        color = color or taxonomy
        semantic_id = ENTITY_TAXONOMY_SEMANTICS.get(taxonomy)
    else:
        color = color or taxonomy
        semantic_id = catalog.semantic_id_for(glyph, color, preferred_categories=("entities",))

    return _semantic_snapshot(
        glyph,
        color=color,
        semantic_id=semantic_id,
        catalog=catalog,
        preferred_categories=("entities",),
    )


def district_floor_glyph(sim, x, y):
    cx, cy = sim.chunk_coords(x, y)
    loaded = sim.world.loaded_chunks.get((cx, cy))
    if not loaded:
        return " "

    district = loaded["chunk"].get("district", {})
    area_type = str(district.get("area_type", "city")).strip().lower() or "city"
    district_type = district.get("district_type", "residential")
    detail = str(loaded.get("detail", "active") or "active").strip().lower() or "active"
    if detail == "coarse":
        glyph = AREA_GLYPHS.get(area_type, ".")
        modulus = 2
    elif area_type != "city":
        glyph = AREA_GLYPHS.get(area_type, ".")
        modulus = 4
    else:
        glyph = DISTRICT_GLYPHS.get(district_type, ".")
        modulus = 5

    texture_seed = ((int(x) * 17) + (int(y) * 31) + (int(cx) * 13) + (int(cy) * 19))
    if texture_seed % modulus != 0:
        return " "
    return glyph


def district_floor_color(sim, x, y):
    cx, cy = sim.chunk_coords(x, y)
    loaded = sim.world.loaded_chunks.get((cx, cy))
    if not loaded:
        return None

    district = loaded["chunk"].get("district", {})
    area_type = str(district.get("area_type", "city")).strip().lower() or "city"
    district_type = str(district.get("district_type", "residential")).strip().lower() or "residential"
    detail = loaded.get("detail", "active")

    if detail == "coarse":
        return "floor_coarse"
    if area_type != "city":
        return AREA_FLOOR_COLORS.get(area_type, "floor_residential")
    return DISTRICT_FLOOR_COLORS.get(district_type, "floor_residential")


def district_floor_snapshot(sim, x, y, catalog=None):
    catalog = catalog or get_runtime_semantic_catalog()
    glyph = district_floor_glyph(sim, x, y)
    color = district_floor_color(sim, x, y)
    return _semantic_snapshot(
        glyph,
        color=color,
        catalog=catalog,
        preferred_categories=("terrain",),
    )


def floor_link_flags(sim, x, y, z):
    tilemap = getattr(sim, "tilemap", None)
    if tilemap is None:
        return False, False

    return (
        bool(tilemap.floor_transition(int(x), int(y), int(z), 1)),
        bool(tilemap.floor_transition(int(x), int(y), int(z), -1)),
    )


def feature_tile_style(sim, tile, x, y, z=0):
    if not tile:
        return None

    glyph = str(tile.glyph)[:1] or "."
    cx, cy = sim.chunk_coords(x, y)
    loaded = sim.world.loaded_chunks.get((cx, cy), {})
    district = loaded.get("chunk", {}).get("district", {}) if isinstance(loaded, dict) else {}
    area_type = str(district.get("area_type", "city")).strip().lower() or "city"
    if glyph == '"':
        return '"', "feature_window", "window"
    if glyph == "'":
        return "'", "feature_door", "open door"
    if glyph == "+":
        prop = property_covering(sim, x, y, z)
        aperture = property_aperture_at(prop, x, y, z)
        if aperture:
            kind = str(aperture.get("kind", "door") or "door").strip().lower()
            if kind in {"service_door", "employee_door", "side_door"}:
                return "+", "feature_door", "service door"
            if kind in {"window", "skylight"}:
                label = "skylight" if kind == "skylight" else "window"
                return '"', "feature_window", label
        return "+", "feature_door", "door"
    if glyph == "/":
        return "/", "feature_breach", "breach opening"
    if glyph == "=":
        return "=", "terrain_road", "road"
    if glyph == ":":
        has_higher, has_lower = floor_link_flags(sim, x, y, z)
        if area_type != "city" and not has_higher and not has_lower:
            return ":", "terrain_trail", "trail"
        return ":", "transit", "stairs between floors"
    if glyph == ">":
        return ">", "transit", "stairs to higher floor"
    if glyph == "<":
        return "<", "transit", "stairs to lower floor"
    if glyph == "S":
        has_higher, has_lower = floor_link_flags(sim, x, y, z)
        if has_higher and has_lower:
            return ":", "transit", "stairs between floors"
        if has_higher:
            return ">", "transit", "stairs to higher floor"
        if has_lower:
            return "<", "transit", "stairs to lower floor"
        return ":", "transit", "stairs"
    if glyph == "E":
        has_higher, has_lower = floor_link_flags(sim, x, y, z)
        if has_higher and has_lower:
            return "E", "transit", "elevator access"
        if has_higher:
            return "E", "transit", "elevator to higher floor"
        if has_lower:
            return "E", "transit", "elevator to lower floor"
        return "E", "transit", "elevator"
    return None


def tile_render_snapshot(sim, tile, x, y, z=0, revealed_building_id="", catalog=None):
    catalog = catalog or get_runtime_semantic_catalog()
    explicit = _owner_appearance(tile, fallback_glyph=".")
    has_explicit_style = bool(explicit.color or explicit.semantic_id or explicit.effects or explicit.attrs or explicit.overlays)

    if not tile:
        return district_floor_snapshot(sim, x, y, catalog=catalog)

    if tile.walkable and str(tile.glyph)[:1] == "." and not has_explicit_style:
        return district_floor_snapshot(sim, x, y, catalog=catalog)

    if str(tile.glyph)[:1] == "b":
        structure = sim.structure_at(x, y, z) if hasattr(sim, "structure_at") else None
        building_id = building_id_from_structure(structure)
        if building_id and building_id != str(revealed_building_id or ""):
            base = _semantic_snapshot(
                "#",
                color=_building_roof_style(structure),
                catalog=catalog,
                preferred_categories=("terrain", "properties"),
            )
            return _merge_snapshots(base, explicit)

    feature_style = feature_tile_style(sim, tile, x, y, z)
    if feature_style:
        base = _semantic_snapshot(
            feature_style[0],
            color=feature_style[1],
            catalog=catalog,
            preferred_categories=("features", "terrain"),
        )
        return _merge_snapshots(base, explicit)

    glyph = str(tile.glyph)[:1] or "?"
    style = SPECIAL_TILE_RENDER_STYLES.get(glyph)
    if style:
        base = _semantic_snapshot(
            style[0],
            color=style[1],
            catalog=catalog,
            preferred_categories=("terrain", "features"),
        )
        return _merge_snapshots(base, explicit)

    base = _semantic_snapshot(
        explicit.glyph if has_explicit_style else glyph,
        color=explicit.color,
        semantic_id=explicit.semantic_id or catalog.semantic_id_for(
            explicit.glyph if has_explicit_style else glyph,
            explicit.color,
        ),
        catalog=catalog,
        preferred_categories=("terrain", "features", "properties"),
    )
    return _merge_snapshots(base, explicit)


def property_render_snapshot(prop, active_quest_target=None, catalog=None):
    catalog = catalog or get_runtime_semantic_catalog()
    if not isinstance(prop, dict):
        return _semantic_snapshot(
            "B",
            color="property_building",
            catalog=catalog,
            preferred_categories=("properties",),
        )

    if prop.get("id") == active_quest_target:
        return _semantic_snapshot(
            "!",
            color="objective",
            semantic_id="objective",
            catalog=catalog,
            preferred_categories=("properties", "ui_markers"),
        )

    metadata = property_metadata(prop)
    kind = str(prop.get("kind", "building")).strip().lower() or "building"
    archetype = str(metadata.get("archetype", "")).strip().lower()
    explicit_glyph = str(metadata.get("display_glyph", "")).strip()
    explicit_color = str(metadata.get("display_color", "")).strip()
    default_glyph, default_color = PROPERTY_ARCHETYPE_DISPLAY.get(
        archetype,
        (PROPERTY_GLYPHS.get(kind, "P"), PROPERTY_COLORS.get(kind, "property_building")),
    )
    if kind == "building" and not explicit_glyph and archetype not in PROPERTY_ARCHETYPE_DISPLAY and finance_services_for_property(prop):
        default_glyph, default_color = "$", "property_service"
    if kind == "building" and not explicit_glyph and archetype not in PROPERTY_ARCHETYPE_DISPLAY and bool(metadata.get("is_storefront")):
        default_glyph, default_color = "S", "building_roof_storefront"

    glyph = str(explicit_glyph or default_glyph)[:1] or "P"
    color = str(explicit_color or default_color or "property_building")
    semantic_id = None
    overlays = _property_cover_overlays(prop)
    if kind == "vehicle":
        quality = str(metadata.get("vehicle_quality", "used")).strip().lower()
        paint_color = str(metadata.get("vehicle_paint", "")).strip()
        owner_tag = str(prop.get("owner_tag", "")).strip().lower()
        if explicit_color:
            color = explicit_color
        elif paint_color:
            color = paint_color
        elif owner_tag == "player":
            color = "vehicle_player"
        elif quality == "new":
            color = "vehicle_new"
        elif not color:
            color = "vehicle_parked"
    elif kind in {"fixture", "asset"}:
        semantic_id = PROPERTY_FIXTURE_SEMANTICS.get(property_fixture_type(prop))
    if property_is_public(prop) and glyph.isalpha():
        glyph = glyph.lower()

    preferred_categories = ("vehicles",) if kind == "vehicle" else ("properties",)
    return _semantic_snapshot(
        glyph,
        color=color,
        semantic_id=semantic_id,
        catalog=catalog,
        preferred_categories=preferred_categories,
        overlays=overlays,
    )


def item_display_glyph(item_def):
    if not isinstance(item_def, dict):
        return "*"

    item_id = str(item_def.get("id", "")).strip().lower()
    tags = {
        str(tag).strip().lower()
        for tag in item_def.get("tags", [])
        if str(tag).strip()
    }
    raw = str(item_def.get("glyph", "*"))[:1] or "*"

    if item_id == "credstick_chip":
        return "$"
    if "weapon" in tags:
        return "/"
    if "armor" in tags:
        return "["
    if "medical" in tags:
        return "!"
    if "food" in tags:
        return "%"
    if "drink" in tags or "stimulant" in tags or "consumable" in tags:
        return "!"
    if "credential" in tags or "key" in tags:
        return ":"
    if "token" in tags:
        return "="
    if "tool" in tags:
        return ")"
    if "junk" in tags:
        return "*"
    return raw


def ground_item_color(item_def):
    if not isinstance(item_def, dict):
        return "item_ground"

    legal_status = str(item_def.get("legal_status", "legal")).strip().lower()
    tags = {
        str(tag).strip().lower()
        for tag in item_def.get("tags", [])
        if str(tag).strip()
    }

    if legal_status == "illegal":
        return "item_illegal"
    if legal_status == "restricted":
        return "item_restricted"
    if "weapon" in tags:
        return "item_weapon"
    if "armor" in tags:
        return "item_armor"
    if "medical" in tags:
        return "item_medical"
    if "food" in tags:
        return "item_food"
    if "drink" in tags or "stimulant" in tags:
        return "item_drink"
    if "credential" in tags or "key" in tags:
        return "item_access"
    if "tool" in tags:
        return "item_tool"
    if "token" in tags:
        return "item_token"
    return "item_ground"


def item_render_snapshot(item_def, *, catalog=None):
    catalog = catalog or get_runtime_semantic_catalog()
    glyph = item_display_glyph(item_def)
    color = ground_item_color(item_def)
    return _semantic_snapshot(
        glyph,
        color=color,
        catalog=catalog,
        preferred_categories=("items",),
    )


def projectile_render_snapshot(glyph, *, color="projectile", catalog=None, layer=None, priority=None):
    catalog = catalog or get_runtime_semantic_catalog()
    return _semantic_snapshot(
        glyph,
        color=color,
        catalog=catalog,
        preferred_categories=("projectiles",),
        layer=layer,
        priority=priority,
    )


def _building_roof_style(info):
    profile = building_exterior_profile(info) if isinstance(info, dict) else {}
    style = str(profile.get("roof_style", "") or "").strip()
    return style or "building_roof"


class AppearanceManager:
    def __init__(self, sim, catalog=None):
        self.sim = sim
        self.catalog = catalog or get_runtime_semantic_catalog()

    def entity(self, eid, *, player_eid=None):
        render = self.sim.ecs.get(Render).get(eid)
        identity = self.sim.ecs.get(CreatureIdentity).get(eid)
        ai = self.sim.ecs.get(AI).get(eid)
        vitality = self.sim.ecs.get(Vitality).get(eid)

        player_controlled = player_eid is not None and eid == player_eid
        defaults = entity_default_snapshot(
            identity,
            role=str(getattr(ai, "role", "") or "").strip().lower(),
            player=player_controlled,
            catalog=self.catalog,
        )
        state_semantic = _entity_state_semantic(identity, vitality)
        if state_semantic:
            defaults = _semantic_snapshot(
                defaults.glyph,
                color=defaults.color,
                semantic_id=state_semantic,
                catalog=self.catalog,
                preferred_categories=("entities",),
                layer=defaults.layer,
                priority=defaults.priority,
                attrs=defaults.attrs,
                effects=defaults.effects,
                visible=defaults.visible,
                overlays=defaults.overlays,
            )
        state_overlays = _entity_state_overlays(vitality)
        owned = _owner_appearance(render, fallback_glyph=defaults.glyph)
        taxonomy = str(getattr(identity, "taxonomy_class", "") or "").strip().lower()
        uses_legacy_hominid_placeholder = (
            taxonomy == "hominid"
            and not getattr(render, "semantic_id", None)
            and getattr(render, "color", None) is None
        )
        glyph = defaults.glyph if uses_legacy_hominid_placeholder else (owned.glyph or defaults.glyph)

        semantic_id = owned.semantic_id or defaults.semantic_id
        if not semantic_id:
            semantic_id = self.catalog.semantic_id_for(
                glyph,
                owned.color if owned.color is not None else defaults.color,
                preferred_categories=("entities",),
            )

        return AppearanceSnapshot(
            glyph=glyph,
            color=owned.color if owned.color is not None else defaults.color,
            semantic_id=semantic_id,
            layer=owned.layer if owned.layer is not None else defaults.layer,
            priority=owned.priority if owned.priority is not None else defaults.priority,
            attrs=int(defaults.attrs or 0) | int(owned.attrs or 0),
            effects=tuple(dict.fromkeys(tuple(defaults.effects or ()) + tuple(owned.effects or ()))),
            visible=bool(defaults.visible) and bool(owned.visible),
            overlays=tuple(defaults.overlays or ()) + tuple(state_overlays or ()) + tuple(owned.overlays or ()),
        )

    def tile(self, tile, x, y, z=0, *, revealed_building_id=""):
        return tile_render_snapshot(
            self.sim,
            tile,
            x,
            y,
            z=z,
            revealed_building_id=revealed_building_id,
            catalog=self.catalog,
        )

    def property(self, prop, *, active_quest_target=None):
        return property_render_snapshot(
            prop,
            active_quest_target=active_quest_target,
            catalog=self.catalog,
        )

    def item(self, item_def):
        return item_render_snapshot(item_def, catalog=self.catalog)

    def snapshot(
        self,
        glyph,
        *,
        color=None,
        semantic_id=None,
        preferred_categories=(),
        layer=None,
        priority=None,
        attrs=0,
        effects=None,
        visible=True,
        overlays=None,
    ):
        return _semantic_snapshot(
            glyph,
            color=color,
            semantic_id=semantic_id,
            catalog=self.catalog,
            preferred_categories=preferred_categories,
            layer=layer,
            priority=priority,
            attrs=attrs,
            effects=effects,
            visible=visible,
            overlays=overlays,
        )

    def projectile(self, glyph, *, color="projectile", layer=None, priority=None, attrs=0, effects=None, overlays=None):
        return self.snapshot(
            glyph,
            color=color,
            preferred_categories=("projectiles",),
            layer=layer,
            priority=priority,
            attrs=attrs,
            effects=effects,
            overlays=overlays,
        )

    def marker(
        self,
        semantic_id,
        glyph,
        *,
        color=None,
        layer=None,
        priority=None,
        attrs=0,
        effects=None,
        overlays=None,
    ):
        return self.snapshot(
            glyph,
            color=color,
            semantic_id=semantic_id,
            preferred_categories=("ui_markers",),
            layer=layer,
            priority=priority,
            attrs=attrs,
            effects=effects,
            overlays=overlays,
        )

    def semantic_id_for(self, glyph, color_key=None, **kwargs):
        return self.catalog.semantic_id_for(glyph, color_key, **kwargs)
