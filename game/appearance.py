from __future__ import annotations

import random
from collections import OrderedDict
from dataclasses import dataclass
from functools import lru_cache
from typing import Mapping, Tuple

from engine.buildings import building_exterior_profile
from game.components import AI, CreatureIdentity, NPCSocial, NPCWill, Occupation, Render, Vitality
from game.appearance_loadout import (
    appearance_render_colors,
    humanoid_render_profile,
)
from game.color_words import clothing_render_key_for_color_word
from game.dialogue_runtime import active_contractor_record
from game.property_runtime import (
    building_id_from_structure,
    finance_services_for_property,
    property_access_level,
    property_aperture_at,
    property_covering,
    property_fixture_type,
    property_is_public,
    property_is_storefront,
    property_lock_state,
    property_metadata,
    site_services_for_property,
)
from game.property_access import property_access_controller
from game.semantic_catalog import get_runtime_semantic_catalog
from game.object_profile_runtime import (
    object_profile_effects,
    object_profile_for_item,
    object_visual_signature,
    property_is_item_backed_fixture,
)
from game.system_support.actor_role_runtime import actor_presentation_role

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
    "herbalist_shop": ("M", "item_medical"),
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

BUILDING_MATERIAL_COLOR_KEYS: Mapping[str, Tuple[str, str]] = {
    "gray_a": ("building_edge_gray_a", "building_fill_gray_a"),
    "gray_b": ("building_edge_gray_b", "building_fill_gray_b"),
    "gray_c": ("building_edge_gray_c", "building_fill_gray_c"),
    "brick": ("building_edge_brick", "building_fill_brick"),
    "plaster": ("building_edge_plaster", "building_fill_plaster"),
    "painted": ("building_edge_painted", "building_fill_painted"),
    "dark": ("building_edge_dark", "building_fill_dark"),
}

_DEFAULT_BUILDING_MATERIAL_WEIGHTS: Tuple[Tuple[str, int], ...] = (
    ("gray_a", 24),
    ("gray_b", 24),
    ("gray_c", 24),
    ("brick", 12),
    ("plaster", 8),
    ("painted", 5),
    ("dark", 3),
)

_BUILDING_MATERIAL_WEIGHTS_BY_CLASS: Mapping[str, Tuple[Tuple[str, int], ...]] = {
    "residential": (
        ("gray_a", 20),
        ("gray_b", 21),
        ("gray_c", 21),
        ("brick", 18),
        ("plaster", 12),
        ("painted", 6),
        ("dark", 2),
    ),
    "storefront": (
        ("gray_a", 20),
        ("gray_b", 20),
        ("gray_c", 22),
        ("brick", 17),
        ("plaster", 12),
        ("painted", 7),
        ("dark", 2),
    ),
    "corporate": (
        ("gray_a", 30),
        ("gray_b", 28),
        ("gray_c", 28),
        ("brick", 2),
        ("plaster", 6),
        ("painted", 4),
        ("dark", 2),
    ),
    "civic": (
        ("gray_a", 30),
        ("gray_b", 28),
        ("gray_c", 28),
        ("brick", 2),
        ("plaster", 6),
        ("painted", 4),
        ("dark", 2),
    ),
    "secure": (
        ("gray_a", 28),
        ("gray_b", 28),
        ("gray_c", 28),
        ("brick", 2),
        ("plaster", 2),
        ("painted", 4),
        ("dark", 8),
    ),
    "industrial": (
        ("gray_a", 23),
        ("gray_b", 23),
        ("gray_c", 24),
        ("brick", 8),
        ("plaster", 2),
        ("painted", 10),
        ("dark", 10),
    ),
    "entertainment": (
        ("gray_a", 22),
        ("gray_b", 22),
        ("gray_c", 22),
        ("brick", 9),
        ("plaster", 9),
        ("painted", 13),
        ("dark", 3),
    ),
}

PROPERTY_FIXTURE_SEMANTICS = {
    "streetlamp": "infra_lamp",
    "trail_lamp": "infra_lamp",
    "utility_pole": "infra_pole",
    "relay_pole": "infra_pole",
    "hydrant": "infra_hydrant",
    "bench": "prop_cover_bench",
    "bus_stop": "prop_cover_shelter",
    "mailbox": "infra_mailbox",
    "junction_box": "prop_cover_junction",
    "planter_box": "prop_cover_planter",
    "drift_fence": "prop_cover_fence",
    "transformer": "prop_cover_transformer",
    "wall_camera": "infra_camera",
    "atm_kiosk": "infra_atm",
    "banking_kiosk": "infra_atm",
    "claim_terminal": "infra_claim_terminal",
    "vending_machine": "service_fixture_vending",
    "security_booth": "service_fixture_security_booth",
    "alarm_panel": "infra_alarm_panel",
    "alarm": "infra_alarm_panel",
    "charging_pillar": "service_fixture_charging",
    "service_terminal": "service_fixture_terminal",
    "access_panel": "infra_access_panel",
    "field_cache_box": "prop_cover_cache",
    "maintenance_cache_box": "prop_cover_cache",
    "water_tank": "prop_cover_tank",
    "campfire_ring": "prop_campfire_ring",
    "way_marker": "infra_way_marker",
    "underground_route_marker": "infra_way_marker",
    "electrochemical_waste_hazard": "hazard_contamination",
    "storm_siren": "infra_siren",
    "solar_rig": "infra_solar",
    "notice_board": "prop_notice_board",
    "news_rack": "prop_notice_board",
    "meeting_board": "prop_notice_board",
    "watch_board": "prop_notice_board",
    "help_wanted_board": "prop_notice_board",
    "complaint_board": "prop_notice_board",
    "route_welcome_board": "prop_notice_board",
    "shift_board": "prop_notice_board",
    "quick_travel_ramp": "prop_vehicle_onramp",
}

SPECIAL_TILE_RENDER_STYLES = {
    "B": ("#", "building_edge"),
    "b": (".", "building_fill"),
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
    color_word: str | None = None
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
            "color_word": str(overlay.get("color_word", "") or "").strip().lower() or None,
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
    color_word=None,
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
        color_word=str(color_word).strip().lower() if str(color_word or "").strip() else None,
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
    color_word=None,
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
        color_word=color_word,
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


def _truthy_metadata_flag(metadata, *keys):
    for key in keys:
        if bool(metadata.get(key)):
            return True
    return False


def _property_access_badge_overlay(prop):
    if not isinstance(prop, dict):
        return ()

    metadata = property_metadata(prop)
    owner_tag = str(prop.get("owner_tag", "") or "").strip().lower()
    kind = str(prop.get("kind", "building") or "building").strip().lower() or "building"
    if kind in {"fixture", "asset", "vehicle"}:
        return ()
    if owner_tag == "player":
        return ({"glyph": "*", "color": "player", "semantic_id": "ui_property_owned"},)

    try:
        locked = bool(property_lock_state(prop).get("locked", False))
    except (AttributeError, TypeError, ValueError):
        locked = False
    if locked:
        return ({"glyph": "L", "color": "objective", "semantic_id": "ui_property_locked"},)

    public = bool(property_is_public(prop))
    service_facing = bool(
        property_is_storefront(prop)
        or finance_services_for_property(prop)
        or site_services_for_property(prop)
        or _truthy_metadata_flag(metadata, "is_storefront")
    )
    controller_kind = str(metadata.get("access_controller_kind", "") or "").strip().lower()
    access_level = str(
        property_access_level(prop)
        or metadata.get("access_level", "")
        or metadata.get("access", "")
        or ""
    ).strip().lower()
    restricted = (
        kind == "building"
        and not public
        and (
            bool(controller_kind)
            or access_level in {"private", "restricted", "secure", "staff", "staff_only"}
            or owner_tag not in {"", "public", "city", "community", "neutral", "none", "unowned"}
        )
    )
    if restricted:
        return ({"glyph": "!", "color": "projectile", "semantic_id": "ui_property_restricted"},)

    if public or service_facing:
        return ({"glyph": "+", "color": "property_service", "semantic_id": "ui_property_public"},)

    return ()


def _property_open_status_overlay(sim, prop):
    if sim is None or not isinstance(prop, dict):
        return ()

    metadata = property_metadata(prop)
    kind = str(prop.get("kind", "building") or "building").strip().lower() or "building"
    if kind != "building":
        return ()

    service_facing = bool(
        property_is_storefront(prop)
        or finance_services_for_property(prop)
        or site_services_for_property(prop)
        or _truthy_metadata_flag(metadata, "is_storefront")
    )
    if not service_facing:
        return ()

    try:
        controller = property_access_controller(sim, prop)
    except (AttributeError, TypeError, ValueError):
        return ()
    open_now = controller.get("open_now")
    if open_now is None:
        return ()
    if bool(open_now):
        return ({"glyph": ".", "color": "property_service", "semantic_id": "ui_property_open"},)
    return ({"glyph": ".", "color": "projectile", "semantic_id": "ui_property_closed"},)


def _owner_appearance(owner, fallback_glyph="?"):
    if owner is None:
        return _snapshot(fallback_glyph)
    glyph = str(getattr(owner, "glyph", fallback_glyph) or fallback_glyph)[:1] or fallback_glyph
    return _snapshot(
        glyph,
        color=getattr(owner, "color", None),
        color_word=getattr(owner, "color_word", None),
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
        color_word=override.color_word or base.color_word,
        semantic_id=override.semantic_id or base.semantic_id,
        layer=override.layer if override.layer is not None else base.layer,
        priority=override.priority if override.priority is not None else base.priority,
        attrs=int(base.attrs or 0) | int(override.attrs or 0),
        effects=tuple(dict.fromkeys(tuple(base.effects or ()) + tuple(override.effects or ()))),
        visible=bool(base.visible) and bool(override.visible),
        overlays=tuple(base.overlays or ()) + tuple(override.overlays or ()),
    )


def _is_building_structure_color(color):
    key = str(color or "").strip().lower()
    return (
        key in {"building_edge", "building_fill", "building_roof"}
        or key.startswith("building_edge_")
        or key.startswith("building_fill_")
        or key.startswith("building_roof_")
    )


def _is_building_structure_semantic(semantic_id):
    key = str(semantic_id or "").strip().lower()
    return key in {"wall_building", "floor_building_fill", "terrain_building_roof"}


def _merge_structure_snapshot(
    base,
    override,
    *,
    preserve_base_glyph=False,
    preserve_base_color=False,
    preserve_base_semantic=False,
):
    if override is None:
        return base
    if base is None:
        return override

    override_color = override.color
    if preserve_base_color or _is_building_structure_color(override_color):
        override_color = None

    override_semantic = override.semantic_id
    if preserve_base_semantic or _is_building_structure_semantic(override_semantic):
        override_semantic = None

    return AppearanceSnapshot(
        glyph=(
            str(getattr(base, "glyph", "?"))[:1] or "?"
            if preserve_base_glyph
            else str(getattr(override, "glyph", "") or getattr(base, "glyph", "?"))[:1]
            or getattr(base, "glyph", "?")
        ),
        color=override_color if override_color is not None else base.color,
        color_word=override.color_word or base.color_word,
        semantic_id=override_semantic or base.semantic_id,
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


ACTOR_THREAT_STATES = {
    "attacking",
    "chasing",
    "ejecting_target",
    "investigating",
    "protecting",
    "warning",
}


def _eid_equal(left, right):
    if left is None or right is None:
        return False
    try:
        return int(left) == int(right)
    except (TypeError, ValueError):
        return left == right


def _vitality_is_living(vitality):
    if vitality is None:
        return True
    if bool(getattr(vitality, "downed", False)):
        return False
    try:
        return int(getattr(vitality, "hp", 0) or 0) > 0
    except (TypeError, ValueError):
        return False


def _player_bond_score(social, player_eid):
    if social is None or player_eid is None:
        return 0.0
    bond = getattr(social, "bonds", {}).get(player_eid)
    if not isinstance(bond, dict):
        return 0.0
    try:
        trust = float(bond.get("trust", 0.0) or 0.0)
    except (TypeError, ValueError):
        trust = 0.0
    try:
        closeness = float(bond.get("closeness", 0.0) or 0.0)
    except (TypeError, ValueError):
        closeness = 0.0
    return max(trust, closeness)


def _actor_badge_overlay(sim, eid, *, player_eid=None, ai=None, will=None, social=None, vitality=None):
    if player_eid is None or _eid_equal(eid, player_eid) or not _vitality_is_living(vitality):
        return ()

    ai_state = str(getattr(ai, "state", "") or "").strip().lower()
    will_intent = str(getattr(will, "intent", "") or "").strip().lower()
    ai_target_eid = getattr(ai, "target_eid", None)
    will_target_eid = getattr(will, "target_eid", None)
    if (
        (ai_state in ACTOR_THREAT_STATES and _eid_equal(ai_target_eid, player_eid))
        or (will_intent in ACTOR_THREAT_STATES and _eid_equal(will_target_eid, player_eid))
    ):
        return ({"glyph": "!", "color": "projectile", "semantic_id": "ui_actor_threat"},)

    contracted = active_contractor_record(sim, eid, ally_eid=player_eid, jobs={"backup", "party"}) is not None
    if (
        (ai_state == "following" and (_eid_equal(ai_target_eid, player_eid) or contracted))
        or (will_intent == "following" and (_eid_equal(will_target_eid, player_eid) or contracted))
        or contracted
    ):
        return ({"glyph": "+", "color": "player", "semantic_id": "ui_actor_ally"},)

    if _player_bond_score(social, player_eid) >= 0.45:
        return ({"glyph": "*", "color": "player", "semantic_id": "ui_actor_contact"},)

    return ()


def _actor_outfit_color_overlays(render_colors, humanoid_profile=None):
    if not isinstance(render_colors, Mapping):
        return ()
    overlays = []
    actor_effects = _actor_presentation_effects(humanoid_profile)
    rows = (
        ("base_top", "ui_actor_basewear_top"),
        ("base_bottom", "ui_actor_basewear_bottom"),
        ("inner", "ui_actor_outfit_inner"),
        ("secondary", "ui_actor_outfit_secondary"),
        ("footwear", "ui_actor_outfit_footwear"),
        ("primary", "ui_actor_outfit_primary"),
        ("headwear", "ui_actor_outfit_headwear"),
        ("accessory", "ui_actor_outfit_accessory"),
    )
    for role, semantic_id in rows:
        color = str(render_colors.get(role) or "").strip()
        if not color:
            continue
        part = render_colors.get("parts", {}).get(role, {}) if isinstance(render_colors.get("parts"), Mapping) else {}
        if role == "inner":
            primary_part = render_colors.get("parts", {}).get("primary", {}) if isinstance(render_colors.get("parts"), Mapping) else {}
            if part and primary_part and part.get("slot") == primary_part.get("slot") and part.get("type") == primary_part.get("type"):
                continue
        effects = list(actor_effects)
        for prefix, value in (
            ("outfit_drawable_", part.get("drawable_id")),
            ("outfit_type_", part.get("type")),
            ("outfit_material_", part.get("material")),
            ("outfit_style_", part.get("style")),
            ("outfit_detail_", part.get("detail")),
            ("outfit_pattern_", part.get("pattern")),
            ("outfit_emblem_", part.get("emblem")),
            ("outfit_slot_", part.get("slot")),
        ):
            clean_value = str(value or "").strip().lower().replace(" ", "_")
            if clean_value:
                effects.append(f"{prefix}{clean_value}")
        flora_motif = part.get("flora_motif") if isinstance(part.get("flora_motif"), Mapping) else {}
        for prefix, value in (
            ("outfit_flora_motif_", flora_motif.get("plant_id")),
            ("outfit_motif_treatment_", flora_motif.get("treatment")),
            ("outfit_motif_shape_", flora_motif.get("petal_shape") or flora_motif.get("leaf_shape")),
            ("outfit_motif_rarity_", flora_motif.get("rarity")),
        ):
            clean_value = str(value or "").strip().lower().replace(" ", "_")
            if clean_value:
                effects.append(f"{prefix}{clean_value}")
        overlays.append({
            "glyph": " ",
            "color": color,
            "color_word": str(render_colors.get(f"{role}_word") or "").strip().lower() or None,
            "semantic_id": semantic_id,
            "effects": tuple(effects),
        })
    return tuple(overlays)


def _actor_presentation_effects(profile):
    if not isinstance(profile, Mapping):
        return ()

    def token(value):
        return str(value or "").strip().lower().replace("-", "_").replace(" ", "_")

    effects = []
    presentation = token(profile.get("presentation"))
    if presentation in {"femme", "masc", "androgynous", "mixed"}:
        effects.append(f"actor_presentation_{presentation}")
    build = token(profile.get("build"))
    if build:
        effects.append(f"actor_build_{build}")
    silhouette = token(profile.get("silhouette"))
    if silhouette:
        effects.append(f"actor_silhouette_{silhouette}")
    hair_length = token(profile.get("hair_length"))
    if hair_length:
        effects.append(f"actor_hair_length_{hair_length}")
    hair_style = token(profile.get("hair_style"))
    if hair_style:
        effects.append(f"actor_hair_style_{hair_style}")
    eye_color = token(profile.get("eye_color"))
    if eye_color:
        effects.append(f"actor_eye_{eye_color}")
    return tuple(effects)


def _actor_hair_overlay(profile):
    if not isinstance(profile, Mapping) or not str(profile.get("hair_length", "") or "").strip():
        return ()
    return ({
        "glyph": " ",
        "color": str(profile.get("hair_color_key") or "human_charcoal").strip() or "human_charcoal",
        "color_word": str(profile.get("hair_color") or "").strip().lower() or None,
        "semantic_id": "ui_actor_hair",
        "effects": _actor_presentation_effects(profile),
    },)


def _hominid_semantic_id_for_role(catalog, role=""):
    semantic_role = "human"
    if role == "guard":
        semantic_role = "guard"
    elif role == "scout":
        semantic_role = "scout"
    return catalog.semantic_id_for_key("entities", "hominid", semantic_role, allow_defaults=True)


def entity_default_snapshot(identity, *, role="", player=False, catalog=None, seed=None, eid=None, sim=None, humanoid_profile=None):
    catalog = catalog or get_runtime_semantic_catalog()
    humanoid_effects = _actor_presentation_effects(humanoid_profile)
    body_color = str((humanoid_profile or {}).get("body_color_key") or "").strip() or "human_monochrome"

    if player:
        return _semantic_snapshot(
            "@",
            color=body_color,
            semantic_id="entity_player",
            catalog=catalog,
            preferred_categories=("entities",),
            effects=humanoid_effects,
        )

    if not identity:
        return _snapshot("?")

    taxonomy = str(getattr(identity, "taxonomy_class", "") or "").strip().lower() or "other"
    glyph = str(identity.taxonomy_glyph(fallback="O"))[:1] or "O"
    color = creature_color_key(identity, role=role)
    color_word = str(getattr(identity, "phenotype_color_word", "") or "").strip().lower() or None
    semantic_id = None

    if taxonomy == "hominid":
        glyph = "@"
        color = body_color or color or "human_monochrome"
        color_word = None
        semantic_id = _hominid_semantic_id_for_role(catalog, role=role)
    elif taxonomy in ENTITY_TAXONOMY_SEMANTICS:
        color = color or taxonomy
        semantic_id = ENTITY_TAXONOMY_SEMANTICS.get(taxonomy)
    else:
        color = color or taxonomy
        semantic_id = catalog.semantic_id_for(glyph, color, preferred_categories=("entities",))

    return _semantic_snapshot(
        glyph,
        color=color,
        color_word=color_word,
        semantic_id=semantic_id,
        catalog=catalog,
        preferred_categories=("entities",),
        effects=humanoid_effects if taxonomy == "hominid" else (),
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

    glyph = str(tile.glyph)[:1] or "?"
    structure = sim.structure_at(x, y, z) if hasattr(sim, "structure_at") else None
    building_id = building_id_from_structure(structure)
    is_building_floor = (
        tile.walkable
        and glyph == "."
        and bool(building_id)
    )
    if is_building_floor and building_id != str(revealed_building_id or ""):
        base = _semantic_snapshot(
            "#",
            color=_building_roof_style(structure),
            catalog=catalog,
            preferred_categories=("terrain", "properties"),
        )
        return _merge_structure_snapshot(
            base,
            explicit,
            preserve_base_glyph=True,
            preserve_base_color=True,
            preserve_base_semantic=True,
        )

    if bool(building_id) and not tile.walkable and glyph == "#":
        base = _semantic_snapshot(
            "#",
            color=_building_material_color_key(structure, filled=False),
            semantic_id="wall_building",
            catalog=catalog,
            preferred_categories=("properties", "terrain"),
        )
        return _merge_structure_snapshot(base, explicit)

    if is_building_floor:
        base = _semantic_snapshot(
            ".",
            color=_building_material_color_key(structure, filled=True),
            semantic_id="floor_building_fill",
            catalog=catalog,
            preferred_categories=("properties", "terrain"),
        )
        return _merge_structure_snapshot(base, explicit)

    if tile.walkable and glyph == "." and not has_explicit_style and not is_building_floor:
        return district_floor_snapshot(sim, x, y, catalog=catalog)

    feature_style = feature_tile_style(sim, tile, x, y, z)
    if feature_style:
        base = _semantic_snapshot(
            feature_style[0],
            color=feature_style[1],
            catalog=catalog,
            preferred_categories=("features", "terrain"),
        )
        return _merge_snapshots(base, explicit)

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


def property_render_snapshot(prop, active_quest_target=None, catalog=None, sim=None):
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
    overlays = (
        tuple(_property_cover_overlays(prop))
        + tuple(_property_access_badge_overlay(prop))
        + tuple(_property_open_status_overlay(sim, prop))
    )
    if kind == "vehicle":
        effects = ()
        quality = str(metadata.get("vehicle_quality", "used")).strip().lower()
        paint_color = str(metadata.get("vehicle_paint", "")).strip()
        owner_tag = str(prop.get("owner_tag", "")).strip().lower()
        if bool(metadata.get("vehicle_explosion_armed")) and not bool(metadata.get("vehicle_exploded")):
            effects = ("blink",)
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
        return _semantic_snapshot(
            glyph,
            color=color,
            semantic_id=semantic_id,
            catalog=catalog,
            preferred_categories=("vehicles",),
            effects=effects,
            overlays=overlays,
        )
    elif kind in {"fixture", "asset"}:
        if property_is_item_backed_fixture(prop):
            signature = metadata.get("visual_signature") if isinstance(metadata.get("visual_signature"), dict) else {}
            profile = metadata.get("object_profile") if isinstance(metadata.get("object_profile"), dict) else {}
            semantic_id = str(signature.get("semantic_id", "") or "").strip() or f"world_object_{profile.get('family', 'personal_home')}"
            color_word = str(signature.get("color_word", profile.get("primary_color", "")) or "").strip().lower() or None
            effects = object_profile_effects(profile, signature)
            return _semantic_snapshot(
                glyph,
                color=color,
                color_word=color_word,
                semantic_id=semantic_id,
                catalog=catalog,
                preferred_categories=("world_objects", "properties"),
                effects=effects,
                overlays=overlays,
            )
        fixture_type = property_fixture_type(prop)
        semantic_id = PROPERTY_FIXTURE_SEMANTICS.get(fixture_type)
        if fixture_type in {"street_stairwell", "underpass_stairs", "underpass_stairwell"}:
            access_name = str(prop.get("name", "") or "").strip().lower()
            if "hatch" in access_name or "grate" in access_name:
                semantic_id = "infra_ground_hatch"
            elif "ladder" in access_name:
                semantic_id = "infra_ladder"
            else:
                semantic_id = "infra_stairs"
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
    tags = _item_tags(item_def)
    category = str(item_def.get("category", "") or "").strip().lower()
    raw = str(item_def.get("glyph", "*"))[:1] or "*"

    if item_id == "credstick_chip":
        return "$"
    render_kind = item_render_kind(item_def)
    if render_kind == "drone":
        return "d"
    if render_kind == "drone_part":
        return "p"
    if render_kind == "wire_interface":
        return "u"
    if render_kind == "wireware":
        return "w"
    if render_kind == "wire_data":
        return "D"
    if render_kind == "ammo":
        return ";"
    if render_kind == "device":
        return "u"
    if render_kind == "container":
        return "b"
    if render_kind == "cosmetic":
        return "c"
    if render_kind == "disguise":
        return "v"
    if render_kind == "throwable":
        return "o"
    if render_kind == "trap":
        return "^"
    if render_kind == "plant_material":
        return ","
    if render_kind == "meat":
        return "%"
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
    if "tool" in tags or category == "tool":
        return ")"
    if "junk" in tags:
        return "*"
    return raw


def _item_tags(item_def):
    if not isinstance(item_def, dict):
        return set()
    return {
        str(tag).strip().lower()
        for tag in item_def.get("tags", [])
        if str(tag).strip()
    }


def item_render_kind(item_def):
    if not isinstance(item_def, dict):
        return "ground"

    item_id = str(item_def.get("id", "") or "").strip().lower()
    category = str(item_def.get("category", "") or "").strip().lower()
    tags = _item_tags(item_def)
    drone_profile = item_def.get("drone_profile") if isinstance(item_def.get("drone_profile"), Mapping) else {}
    wire_profile = item_def.get("wire_profile") if isinstance(item_def.get("wire_profile"), Mapping) else {}
    wire_interface = (
        item_def.get("wire_interface_profile")
        if isinstance(item_def.get("wire_interface_profile"), Mapping)
        else {}
    )

    if (
        drone_profile
        or category in {"drone", "drone_part"}
        or item_id == "packed_drone"
        or bool(tags & {"drone_chassis", "drone_module", "drone_power", "drone_battery"})
    ):
        drone_kind = str(drone_profile.get("kind", "") or "").strip().lower()
        if drone_kind == "assembly" or category == "drone" or item_id == "packed_drone":
            return "drone"
        return "drone_part"
    if wire_interface or category == "wire_interface" or ({"wire", "interface"} <= tags):
        return "wire_interface"
    if wire_profile:
        wire_kind = str(wire_profile.get("kind", "") or "").strip().lower()
        if (
            wire_kind in {"data_packet", "backup", "trace", "corrupted_file"}
            or category == "wire_data"
            or "data" in tags
        ):
            return "wire_data"
        if wire_kind in {"credential", "license"} or category == "credential" or "credential" in tags or "license" in tags:
            return "access"
        return "wireware"
    if category == "wireware" or "program" in tags:
        return "wireware"
    if category == "wire_data" or ({"wire", "data"} <= tags):
        return "wire_data"
    if category == "ammo" or "ammo" in tags:
        return "ammo"
    if category == "weapon" or "weapon" in tags:
        return "weapon"
    if category == "armor" or "armor" in tags:
        return "armor"
    if category == "cosmetic" or "cosmetic" in tags or "clothing" in tags:
        return "cosmetic"
    if category == "disguise":
        return "disguise"
    if category == "throwable" or "throwable" in tags:
        return "throwable"
    if category == "medical" or "medical" in tags:
        return "medical"
    if "trap" in tags or "aerosol_trap" in tags:
        return "trap"
    if "meat" in tags or "raw_meat" in tags or item_id.endswith("_meat"):
        return "meat"
    if "plant_pot" in tags:
        return "container"
    if (
        "herbal_ingredient" in tags
        or "plant_material" in tags
        or "blossom" in tags
        or "seed" in tags
        or "plantable" in tags
        or "cultivation" in tags
        or category == "plant_material"
    ):
        return "plant_material"
    if "food" in tags:
        return "food"
    if "drink" in tags or "stimulant" in tags or "consumable" in tags:
        return "drink"
    if category == "credential" or "credential" in tags or "key" in tags:
        return "access"
    if category == "device" or "device" in tags or "phone" in tags or "communication" in tags:
        return "device"
    if category == "container" or "container" in tags:
        return "container"
    if category == "token" or "token" in tags:
        return "token"
    if "junk" in tags:
        return "junk"
    if category == "tool" or "tool" in tags:
        return "tool"
    return "ground"


_OBVIOUS_LEGAL_STATUS_TAGS = frozenset(
    {
        "aerosol_trap",
        "explosive",
        "launcher",
        "missile",
        "ordnance",
        "rocket",
    }
)


_ITEM_SHAPE_EFFECTS = {
    "battery_pack": "tool_shape_battery_pack",
    "bolt_cutters": "tool_shape_cutters",
    "cloned_thumb": "tool_shape_biometric",
    "drone_programmer": "tool_shape_programmer",
    "glass_cutter": "tool_shape_glass_cutter",
    "hotwire_leads": "tool_shape_leads",
    "inspection_mirror": "tool_shape_mirror",
    "lockpick_kit": "tool_shape_lockpick_kit",
    "mortar_kit": "tool_shape_mortar",
    "pocket_multitool": "tool_shape_multitool",
    "pruning_shears": "tool_shape_cutters",
    "prybar": "tool_shape_prybar",
    "scrap_circuit": "tool_shape_circuit",
    "signal_jammer": "tool_shape_jammer",
}


def _visible_legal_status_color(item_def, tags):
    legal_status = str(item_def.get("legal_status", "legal") or "legal").strip().lower()
    if legal_status not in {"illegal", "restricted"}:
        return ""
    if tags & _OBVIOUS_LEGAL_STATUS_TAGS:
        return "item_illegal" if legal_status == "illegal" else "item_restricted"
    return ""


def _clothing_color_from_metadata(item_def, metadata):
    if not isinstance(item_def, Mapping) or not isinstance(metadata, Mapping):
        return "", None
    tags = _item_tags(item_def)
    category = str(item_def.get("category", "") or "").strip().lower()
    if not (
        category in {"cosmetic", "disguise"}
        or "clothing" in tags
        or "cosmetic" in tags
        or "disguise" in tags
    ):
        return "", None

    explicit_render = str(
        metadata.get("render_color") or metadata.get("color_key") or ""
    ).strip().lower()
    if explicit_render.startswith("clothing_"):
        return explicit_render, explicit_render.removeprefix("clothing_") or None

    appearance = metadata.get("appearance") if isinstance(metadata.get("appearance"), Mapping) else {}
    word = str(
        metadata.get("color_word")
        or metadata.get("color")
        or appearance.get("color_word")
        or appearance.get("color")
        or ""
    ).strip().lower()
    color = clothing_render_key_for_color_word(word, default="") if word else ""
    if color:
        return str(color), word or None
    return "clothing_charcoal", "charcoal"


def _item_id_text(item_def):
    return str(item_def.get("id", "") or "").strip().lower()


def _appearance_slot_set(item_def):
    slots = item_def.get("appearance_slots")
    if not isinstance(slots, (list, tuple, set)):
        slots = ()
    return {
        str(slot or "").strip().lower()
        for slot in slots
        if str(slot or "").strip()
    }


def _item_weapon_shape(item_def, tags):
    item_id = _item_id_text(item_def)
    if "launcher" in tags or "rocket" in tags or "grenade" in item_id:
        return "launcher"
    if "shotgun" in tags or "shotgun" in item_id:
        return "shotgun"
    if "rifle" in tags or "carbine" in tags or "rifle" in item_id or "carbine" in item_id:
        return "rifle"
    if "smg" in tags or "machine_pistol" in item_id or "compact_smg" in item_id:
        return "smg"
    if "handgun" in tags or "pistol" in item_id or "revolver" in item_id:
        return "handgun"
    if "axe" in item_id:
        return "axe"
    if "knife" in tags or "knife" in item_id or "cutter" in item_id:
        return "knife"
    if "blade" in tags or "machete" in item_id:
        return "blade"
    if "club" in tags or "baton" in tags or "iron" in item_id or "crowbar" in item_id:
        return "club"
    return "generic"


def _item_armor_shape(item_def, tags):
    item_id = _item_id_text(item_def)
    slot = str((item_def.get("armor") or {}).get("slot", "") if isinstance(item_def.get("armor"), Mapping) else "").strip().lower()
    if slot == "head" or "helmet" in item_id:
        return "helmet"
    if "apron" in item_id or "apron" in tags:
        return "apron"
    if "jacket" in item_id:
        return "jacket"
    if "plate" in item_id or "plates" in item_id or "carrier" in item_id or "rig" in item_id:
        return "plate"
    if "vest" in item_id or "mesh" in item_id:
        return "vest"
    return "vest"


def _item_cosmetic_shape(item_def, tags):
    item_id = _item_id_text(item_def)
    slots = _appearance_slot_set(item_def)
    if "earpiece" in item_id:
        return "earpiece"
    if "lanyard" in item_id or "badge" in item_id:
        return "lanyard"
    if "apron" in item_id:
        return "apron"
    if "coverall" in item_id or "jumpsuit" in item_id:
        return "coverall"
    if "full_body" in slots or "dress" in item_id:
        return "dress"
    if "skirt" in item_id:
        return "skirt"
    if "bottom" in slots:
        return "shorts" if "shorts" in item_id else "trousers"
    if "shoes" in slots:
        if "sandals" in item_id:
            return "sandals"
        if "sneakers" in item_id:
            return "sneakers"
        return "boots"
    if "hat" in slots or item_id in {"cap", "baseball_cap", "bandana"}:
        return "bandana" if "bandana" in item_id else "cap"
    if tags & {"jewelry"} or slots & {"necklace", "ring_left", "ring_right", "bracelet", "earrings"}:
        if "watch" in item_id:
            return "watch"
        if "ring" in item_id:
            return "ring"
        if "earring" in item_id:
            return "earrings"
        if "bracelet" in item_id:
            return "bracelet"
        return "necklace"
    if "scarf" in item_id:
        return "scarf"
    if "gloves" in item_id:
        return "gloves"
    if "outer" in slots or item_id in {"jacket", "windbreaker", "coat", "cardigan", "blazer", "vest", "security_jacket", "patrol_rain_shell"}:
        if "vest" in item_id:
            return "vest"
        if "coat" in item_id or "rain" in item_id:
            return "coat"
        if "blazer" in item_id:
            return "blazer"
        return "jacket"
    if "turtleneck" in item_id:
        return "turtleneck"
    if "sweater" in item_id or "cardigan" in item_id:
        return "sweater"
    if "button" in item_id or "blouse" in item_id:
        return "buttoned_top"
    return "top"


def _item_drone_part_shape(item_def, tags):
    profile = item_def.get("drone_profile") if isinstance(item_def.get("drone_profile"), Mapping) else {}
    item_id = _item_id_text(item_def)
    kind = str(profile.get("kind", "") or "").strip().lower()
    module_kind = str(profile.get("module_kind", "") or "").strip().lower()
    if kind == "chassis" or "chassis" in tags:
        return "chassis"
    if kind == "power_center" or "power" in tags or "power_core" in item_id:
        return "power_core"
    if kind == "battery" or "battery" in tags:
        return "battery"
    if module_kind:
        if module_kind in {"radar", "ir", "sonar", "lidar"}:
            return "sensor"
        if module_kind in {"pistol", "ammo_rack", "fuel_tank", "flame_nozzle"}:
            return module_kind
        return module_kind
    if "procedure" in tags or "procedure" in item_id:
        return "procedure"
    return "module"


def _item_wireware_shape(item_def, tags):
    profile = item_def.get("wire_profile") if isinstance(item_def.get("wire_profile"), Mapping) else {}
    item_id = _item_id_text(item_def)
    family = str(profile.get("program_family", "") or "").strip().lower()
    key = str(profile.get("program_key", "") or "").strip().lower()
    if key in {"spike", "ice_cutter"} or family == "attack":
        return "attack"
    if key in {"signal_cloak", "trace_scrubber"} or family in {"stealth", "trace"}:
        return "stealth"
    if key in {"checksum_ward", "sacrificial_shell"} or family in {"defense", "ward"}:
        return "defense"
    if key in {"panic_eject"}:
        return "eject"
    if key in {"door_latch"} or "door" in item_id:
        return "door"
    if key in {"camera_loop"} or "camera" in item_id:
        return "camera"
    if key in {"data_siphon_shell"} or "data" in item_id:
        return "data"
    if key in {"route_probe"} or "route" in item_id:
        return "route"
    if key in {"talk"} or "talk" in item_id:
        return "talk"
    return "program"


def _item_access_shape(item_def, tags):
    profile = item_def.get("wire_profile") if isinstance(item_def.get("wire_profile"), Mapping) else {}
    item_id = _item_id_text(item_def)
    wire_kind = str(profile.get("kind", "") or "").strip().lower()
    if wire_kind == "credential" or "wire_access" in item_id:
        return "wire_key"
    if wire_kind == "license" or "license" in item_id:
        return "license"
    if "badge" in item_id or "badge" in tags:
        return "badge"
    if "key" in item_id or "key" in tags:
        return "key"
    if "pass" in item_id or "token" in item_id:
        return "pass"
    return "credential"


def _item_wire_interface_shape(item_def, tags):
    profile = item_def.get("wire_interface_profile") if isinstance(item_def.get("wire_interface_profile"), Mapping) else {}
    item_id = _item_id_text(item_def)
    kind = str(profile.get("kind", "") or "").strip().lower()
    if kind:
        return kind
    if "jack" in item_id:
        return "jack"
    if "rig" in item_id:
        return "rig"
    if "cable" in item_id:
        return "cable"
    if "dongle" in item_id:
        return "dongle"
    if "bridge" in item_id:
        return "bridge"
    return "deck"


def _item_token_shape(item_def, tags):
    item_id = _item_id_text(item_def)
    if "phone" in tags or "phone" in item_id:
        return "phone"
    if "radio" in tags or "radio" in item_id:
        return "radio"
    if "credstick" in item_id or "chip" in item_id:
        return "chip"
    if "deck" in item_id and "card" in item_id:
        return "cards"
    if "badge" in item_id:
        return "badge"
    if "pass" in item_id or "token" in item_id:
        return "pass"
    if "card" in item_id:
        return "card"
    if "ticket" in item_id or "voucher" in item_id:
        return "ticket"
    if "notebook" in item_id or "ledger" in item_id:
        return "book"
    if "flyer" in item_id or "scrap" in item_id or "note" in item_id:
        return "paper"
    if "charm" in item_id:
        return "charm"
    if "deck" in item_id:
        return "cards"
    return "token"


def _item_plant_material_shape(item_def, tags):
    item_id = _item_id_text(item_def)
    if "seed" in tags or "seed" in item_id:
        return "seed"
    if "blossom" in tags or "flower" in tags or "blossom" in item_id:
        return "blossom"
    if "moss" in tags or "moss" in item_id:
        return "moss"
    if "vine" in tags or "cutting" in item_id or "vine" in item_id:
        return "vine"
    if "leaf" in tags or "leaf" in item_id or "clipping" in item_id:
        return "leaf"
    return "bundle"


def _item_container_shape(item_def, tags):
    item_id = _item_id_text(item_def)
    if "plant_pot" in tags or "plant_pot" in item_id or item_id == "plant_pot":
        return "pot"
    if "backpack" in item_id or "pack" in item_id:
        return "backpack"
    if "apron" in item_id or "satchel" in item_id or "bag" in item_id:
        return "soft_bag"
    return "box"


def _item_junk_shape(item_def, tags):
    item_id = _item_id_text(item_def)
    if "circuit" in item_id or "electronics" in tags:
        return "circuit"
    if "stub" in item_id:
        return "stub"
    if "scrap" in item_id:
        return "scrap"
    if "paper" in tags or "flyer" in item_id or "note" in item_id:
        return "paper"
    return "junk"


def _item_medical_shape(item_def, tags):
    item_id = _item_id_text(item_def)
    if "kit" in item_id or "suture" in item_id:
        return "kit"
    if "injector" in item_id or "ampoule" in item_id or "serum" in item_id or "jab" in item_id:
        return "injector"
    if "patch" in item_id:
        return "patch"
    if "foam" in item_id:
        return "foam"
    if "bandage" in item_id or "dressing" in item_id:
        return "bandage"
    if "inhaler" in item_id:
        return "inhaler"
    if "tabs" in item_id or "salts" in item_id or "wipes" in item_id:
        return "packet"
    if tags & {"herbal", "herbal_medicine"} or "poultice" in item_id or "tincture" in item_id or "draught" in item_id:
        return "herbal"
    return "vial"


def _item_food_shape(item_def, tags):
    item_id = _item_id_text(item_def)
    if "soup" in item_id or "bowl" in item_id:
        return "bowl"
    if "fruit" in item_id:
        return "fruit"
    if "bar" in item_id or "wrap" in item_id or "ration" in item_id:
        return "bar"
    return "meal"


def _item_drink_shape(item_def, tags):
    item_id = _item_id_text(item_def)
    if "coffee" in item_id or "brew" in item_id:
        return "cup"
    if "shot" in item_id or "gel" in item_id or "strip" in item_id:
        return "small"
    if "juice" in item_id:
        return "carton"
    return "bottle"


def _item_shape_effect_for_kind(item_def, render_kind, tags):
    if render_kind == "weapon":
        return f"weapon_shape_{_item_weapon_shape(item_def, tags)}"
    if render_kind == "armor":
        return f"armor_shape_{_item_armor_shape(item_def, tags)}"
    if render_kind == "cosmetic":
        return f"cosmetic_shape_{_item_cosmetic_shape(item_def, tags)}"
    if render_kind == "drone_part":
        return f"drone_part_shape_{_item_drone_part_shape(item_def, tags)}"
    if render_kind == "wireware":
        return f"wireware_shape_{_item_wireware_shape(item_def, tags)}"
    if render_kind == "wire_interface":
        return f"wire_interface_shape_{_item_wire_interface_shape(item_def, tags)}"
    if render_kind == "access":
        return f"access_shape_{_item_access_shape(item_def, tags)}"
    if render_kind == "token":
        return f"token_shape_{_item_token_shape(item_def, tags)}"
    if render_kind == "plant_material":
        return f"plant_material_shape_{_item_plant_material_shape(item_def, tags)}"
    if render_kind == "container":
        return f"container_shape_{_item_container_shape(item_def, tags)}"
    if render_kind == "junk":
        return f"junk_shape_{_item_junk_shape(item_def, tags)}"
    if render_kind == "medical":
        return f"medical_shape_{_item_medical_shape(item_def, tags)}"
    if render_kind == "food":
        return f"food_shape_{_item_food_shape(item_def, tags)}"
    if render_kind == "drink":
        return f"drink_shape_{_item_drink_shape(item_def, tags)}"
    if render_kind == "wire_data":
        item_id = _item_id_text(item_def)
        profile = item_def.get("wire_profile") if isinstance(item_def.get("wire_profile"), Mapping) else {}
        wire_kind = str(profile.get("kind", "") or "").strip().lower()
        if wire_kind == "backup" or "backup" in item_id:
            return "wire_data_shape_backup"
        if wire_kind == "trace" or "trace" in item_id:
            return "wire_data_shape_trace"
        if wire_kind == "corrupted_file" or "corrupted" in item_id:
            return "wire_data_shape_corrupt"
        return "wire_data_shape_cache"
    return ""


def _stable_item_mark_effects(item_def, metadata=None):
    metadata = metadata if isinstance(metadata, Mapping) else {}
    item_id = _item_id_text(item_def)
    seed_text = str(
        metadata.get("instance_id")
        or metadata.get("source_instance_id")
        or metadata.get("visual_seed")
        or item_id
    )
    if not seed_text:
        return ()
    value = 0
    for char in f"{item_id}:{seed_text}":
        value = ((value * 131) + ord(char)) % 1000003
    marks = ("dot", "slash", "bar", "chevron", "ring", "corner")
    return (f"item_mark_{marks[value % len(marks)]}", f"item_mark_seed_{value % 31}")


def _item_shape_effects(item_def, render_kind, metadata=None):
    item_id = str(item_def.get("id", "") or "").strip().lower()
    tags = _item_tags(item_def)
    effects = []
    effect = _ITEM_SHAPE_EFFECTS.get(item_id)
    if effect and (render_kind == "tool" and effect.startswith("tool_shape_")):
        effects.append(effect)
    taxonomy = _item_shape_effect_for_kind(item_def, render_kind, tags)
    if taxonomy and taxonomy not in effects:
        effects.append(taxonomy)
    effects.extend(effect for effect in _stable_item_mark_effects(item_def, metadata) if effect not in effects)
    return tuple(effects)


def ground_item_color(item_def):
    if not isinstance(item_def, dict):
        return "item_ground"

    tags = {
        str(tag).strip().lower()
        for tag in item_def.get("tags", [])
        if str(tag).strip()
    }

    visible_status_color = _visible_legal_status_color(item_def, tags)
    if visible_status_color:
        return visible_status_color
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
    if "herbal_ingredient" in tags or "plant_material" in tags or "seed" in tags or "plantable" in tags:
        return "item_plant_material"
    if "container" in tags:
        return "item_container"
    if "tool" in tags:
        return "item_tool"
    if "token" in tags:
        return "item_token"
    if "junk" in tags:
        return "item_junk"
    return "item_ground"


def item_render_snapshot(item_def, *, metadata=None, catalog=None):
    catalog = catalog or get_runtime_semantic_catalog()
    metadata = metadata if isinstance(metadata, Mapping) else {}
    profile = object_profile_for_item(item_def, metadata) if metadata else {}
    if profile and isinstance(metadata.get("object_profile"), Mapping):
        signature = metadata.get("visual_signature") if isinstance(metadata.get("visual_signature"), Mapping) else {}
        if not signature:
            signature = object_visual_signature(str(item_def.get("id", "") or ""), profile, metadata)
        glyph = str(signature.get("glyph", profile.get("display_glyph", "o")) or "o")[:1] or "o"
        color = str(signature.get("color", profile.get("display_color", "world_object_home")) or "world_object_home")
        color_word = str(signature.get("color_word", profile.get("primary_color", "")) or "").strip().lower() or None
        semantic_id = str(signature.get("semantic_id", f"world_object_{profile.get('family', 'personal_home')}") or "")
        return _semantic_snapshot(
            glyph,
            color=color,
            color_word=color_word,
            semantic_id=semantic_id,
            catalog=catalog,
            preferred_categories=("world_objects", "items"),
            effects=object_profile_effects(profile, signature),
        )
    glyph = item_display_glyph(item_def)
    color = ground_item_color(item_def)
    render_kind = item_render_kind(item_def)
    color_word = None
    clothing_color, clothing_word = _clothing_color_from_metadata(item_def, metadata)
    if clothing_color:
        color = clothing_color
        color_word = clothing_word
    return _semantic_snapshot(
        glyph,
        color=color,
        color_word=color_word,
        semantic_id=f"item_{render_kind}",
        catalog=catalog,
        preferred_categories=("items",),
        effects=_item_shape_effects(item_def, render_kind, metadata),
    )


def projectile_render_snapshot(glyph, *, color="projectile", catalog=None, layer=None, priority=None):
    catalog = catalog or get_runtime_semantic_catalog()
    return _semantic_snapshot(
        glyph,
        color=color,
        semantic_id="projectile",
        catalog=catalog,
        preferred_categories=("projectiles",),
        layer=layer,
        priority=priority,
    )


def _building_roof_style(info):
    profile = building_exterior_profile(info) if isinstance(info, dict) else {}
    style = str(profile.get("roof_style", "") or "").strip()
    return style or "building_roof"


def _building_material_style(info):
    if not isinstance(info, dict):
        return "gray_a"
    profile = building_exterior_profile(info)
    exterior_class = str(profile.get("class", "") or "").strip().lower()
    archetype = str(profile.get("archetype", "") or info.get("archetype", "") or "").strip().lower()
    building_id = building_id_from_structure(info) or str(info.get("id", "") or "").strip()
    name = str(
        info.get("name", "")
        or info.get("label", "")
        or info.get("business_name", "")
        or info.get("display_name", "")
        or ""
    ).strip().lower()
    return _building_material_style_for_token(building_id, archetype, name, exterior_class)


@lru_cache(maxsize=16_384)
def _building_material_style_for_token(building_id, archetype, name, exterior_class):
    """Resolve one immutable building identity without reseeding every frame."""

    seed_token = f"building-material:{building_id}:{archetype}:{name}:{exterior_class}"
    rng = random.Random(seed_token)
    weights = _BUILDING_MATERIAL_WEIGHTS_BY_CLASS.get(
        exterior_class,
        _DEFAULT_BUILDING_MATERIAL_WEIGHTS,
    )
    total = sum(max(0, weight) for _, weight in weights)
    if total <= 0:
        return "gray_a"
    roll = rng.uniform(0, total)
    cursor = 0.0
    for material, weight in weights:
        cursor += max(0, weight)
        if roll <= cursor:
            return material
    return weights[-1][0]


def _building_material_color_key(info, *, filled=False):
    material = _building_material_style(info)
    edge_key, fill_key = BUILDING_MATERIAL_COLOR_KEYS.get(
        material,
        BUILDING_MATERIAL_COLOR_KEYS["gray_a"],
    )
    return fill_key if filled else edge_key


class AppearanceManager:
    def __init__(self, sim, catalog=None):
        self.sim = sim
        self.catalog = catalog or get_runtime_semantic_catalog()
        self._tile_snapshot_cache = OrderedDict()
        self._tile_snapshot_cache_limit = 32_768
        self._tile_snapshot_cache_hits = 0
        self._tile_snapshot_cache_misses = 0

    def _tile_snapshot_context_key(self, tile, x, y, z, revealed_building_id):
        x = int(x)
        y = int(y)
        z = int(z)
        tilemap = getattr(self.sim, "tilemap", None)
        structure = self.sim.structure_at(x, y, z) if hasattr(self.sim, "structure_at") else None
        building_id = building_id_from_structure(structure)
        revealed = bool(building_id) and building_id == str(revealed_building_id or "")

        detail = ""
        area_type = ""
        district_type = ""
        if hasattr(self.sim, "detail_for_xy"):
            detail = str(self.sim.detail_for_xy(x, y) or "")
        if hasattr(self.sim, "chunk_coords"):
            cx, cy = self.sim.chunk_coords(x, y)
            loaded = getattr(getattr(self.sim, "world", None), "loaded_chunks", {}).get((cx, cy), {})
            district = loaded.get("chunk", {}).get("district", {}) if isinstance(loaded, dict) else {}
            if isinstance(district, dict):
                area_type = str(district.get("area_type", "") or "").strip().lower()
                district_type = str(district.get("district_type", "") or "").strip().lower()

        glyph = str(getattr(tile, "glyph", "") or "")[:1] if tile is not None else ""
        links = (False, False)
        if glyph in {":", "S", "E"}:
            links = floor_link_flags(self.sim, x, y, z)

        aperture_kind = ""
        if glyph == "+":
            prop = property_covering(self.sim, x, y, z)
            aperture = property_aperture_at(prop, x, y, z)
            if isinstance(aperture, Mapping):
                aperture_kind = str(aperture.get("kind", "door") or "door").strip().lower()

        structure_token = ("", "", "")
        if building_id and isinstance(structure, dict):
            structure_token = (
                str(building_id),
                _building_roof_style(structure),
                _building_material_style(structure),
            )
        return (
            x,
            y,
            z,
            tile,
            int(getattr(tile, "visual_revision", 0) or 0) if tile is not None else 0,
            structure_token,
            revealed,
            detail,
            area_type,
            district_type,
            links,
            aperture_kind,
        )

    def clear_tile_snapshot_cache(self):
        self._tile_snapshot_cache.clear()

    def tile_snapshot_cache_stats(self):
        return {
            "size": len(self._tile_snapshot_cache),
            "limit": int(self._tile_snapshot_cache_limit),
            "hits": int(self._tile_snapshot_cache_hits),
            "misses": int(self._tile_snapshot_cache_misses),
        }

    def entity(self, eid, *, player_eid=None):
        render = self.sim.ecs.get(Render).get(eid)
        identity = self.sim.ecs.get(CreatureIdentity).get(eid)
        ai = self.sim.ecs.get(AI).get(eid)
        occupation = self.sim.ecs.get(Occupation).get(eid)
        will = self.sim.ecs.get(NPCWill).get(eid)
        social = self.sim.ecs.get(NPCSocial).get(eid)
        vitality = self.sim.ecs.get(Vitality).get(eid)
        taxonomy = str(getattr(identity, "taxonomy_class", "") or "").strip().lower()
        humanoid_profile = humanoid_render_profile(self.sim, eid) if taxonomy == "hominid" else {}

        player_controlled = player_eid is not None and eid == player_eid
        defaults = entity_default_snapshot(
            identity,
            role=actor_presentation_role(self.sim, eid, ai=ai, occupation=occupation),
            player=player_controlled,
            catalog=self.catalog,
            seed=getattr(self.sim, "seed", None),
            eid=eid,
            sim=self.sim,
            humanoid_profile=humanoid_profile,
        )
        state_semantic = _entity_state_semantic(identity, vitality)
        if state_semantic:
            defaults = _semantic_snapshot(
                defaults.glyph,
                color=defaults.color,
                color_word=defaults.color_word,
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
        badge_overlays = _actor_badge_overlay(
            self.sim,
            eid,
            player_eid=player_eid,
            ai=ai,
            will=will,
            social=social,
            vitality=vitality,
        )
        owned = _owner_appearance(render, fallback_glyph=defaults.glyph)
        owned_color = owned.color
        if (
            player_controlled
            and str(owned_color or "").strip().lower() == "player"
            and str(defaults.color or "").strip().lower() != "player"
        ):
            owned_color = None
        outfit_overlays = ()
        hair_overlays = ()
        if taxonomy == "hominid":
            hair_overlays = _actor_hair_overlay(humanoid_profile)
            outfit_overlays = _actor_outfit_color_overlays(appearance_render_colors(self.sim, eid), humanoid_profile=humanoid_profile)
        if taxonomy == "hominid" and str(owned_color or "").strip().lower() in {"human", "guard", "scout", "player"}:
            owned_color = None
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
                owned_color if owned_color is not None else defaults.color,
                preferred_categories=("entities",),
            )

        actor_layer = owned.layer if owned.layer is not None else defaults.layer
        if actor_layer is None and taxonomy == "hominid":
            actor_layer = "actor"
        final_color = owned_color if owned_color is not None else defaults.color
        final_color_word = owned.color_word if owned_color is not None else (owned.color_word or defaults.color_word)

        return AppearanceSnapshot(
            glyph=glyph,
            color=final_color,
            color_word=final_color_word,
            semantic_id=semantic_id,
            layer=actor_layer,
            priority=owned.priority if owned.priority is not None else defaults.priority,
            attrs=int(defaults.attrs or 0) | int(owned.attrs or 0),
            effects=tuple(dict.fromkeys(tuple(defaults.effects or ()) + tuple(owned.effects or ()))),
            visible=bool(defaults.visible) and bool(owned.visible),
            overlays=(
                tuple(defaults.overlays or ())
                + tuple(hair_overlays or ())
                + tuple(outfit_overlays or ())
                + tuple(state_overlays or ())
                + tuple(badge_overlays or ())
                + tuple(owned.overlays or ())
            ),
        )

    def tile(self, tile, x, y, z=0, *, revealed_building_id=""):
        cache_key = self._tile_snapshot_context_key(tile, x, y, z, revealed_building_id)
        cached = self._tile_snapshot_cache.get(cache_key)
        if cached is not None:
            self._tile_snapshot_cache.move_to_end(cache_key)
            self._tile_snapshot_cache_hits += 1
            return cached

        self._tile_snapshot_cache_misses += 1
        snapshot = tile_render_snapshot(
            self.sim,
            tile,
            x,
            y,
            z=z,
            revealed_building_id=revealed_building_id,
            catalog=self.catalog,
        )
        self._tile_snapshot_cache[cache_key] = snapshot
        self._tile_snapshot_cache.move_to_end(cache_key)
        while len(self._tile_snapshot_cache) > self._tile_snapshot_cache_limit:
            self._tile_snapshot_cache.popitem(last=False)
        return snapshot

    def property(self, prop, *, active_quest_target=None):
        return property_render_snapshot(
            prop,
            active_quest_target=active_quest_target,
            catalog=self.catalog,
            sim=self.sim,
        )

    def item(self, item_def, *, metadata=None):
        return item_render_snapshot(item_def, metadata=metadata, catalog=self.catalog)

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
            semantic_id="projectile",
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
