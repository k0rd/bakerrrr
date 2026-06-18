"""Trade system extracted from ``game.systems``."""

import curses
import random

from engine.events import Event
from engine.systems import System
from game.appearance import ground_item_color as _ground_item_color, item_display_glyph as _appearance_item_display_glyph
from game.appearance_loadout import (
    TATTOO_SERVICE_ITEM_ID,
    apply_tattoo_service,
    cosmetic_variant_metadata,
    is_appearance_item,
    tattoo_service_metadata,
)
from game.components import Inventory, NPCSocial, PlayerAssets, Position, VehicleState
from game.economy import item_market_bias, store_supply_profile
from game.item_semantics import item_display_name_for_actor
from game.items import ITEM_CATALOG
from game.organization_reputation import organization_instability_profile
from game.organization_response import property_vigilante_denial
from game.organizations import (
    local_workplace_org_posture,
    property_item_practice_bundle,
    property_trade_practice_bundle,
    realize_item_instance_metadata,
)
from game.player_businesses import (
    player_business_markup_profile as _player_business_markup_profile,
    player_business_record_direct_sale as _player_business_record_direct_sale,
)
from game.property_access import evaluate_property_access as _evaluate_property_access
from game.property_keys import (
    PROPERTY_KEY_ITEM_ID,
    PROPERTY_MANAGER_BADGE_ITEM_ID,
    PROPERTY_STAFF_BADGE_ITEM_ID,
    ensure_property_lock,
    remove_actor_property_credentials,
)
from game.property_runtime import (
    property_covering as _property_covering,
    property_distance as _property_distance,
    property_focus_position as _property_focus_position,
    property_is_storefront as _property_is_storefront,
    property_is_vehicle as _property_is_vehicle,
    property_metadata as _property_metadata,
    site_services_for_property as _site_services_for_property,
    vehicle_fuel_values as _vehicle_fuel_values,
    vehicle_label as _vehicle_label,
)
from game.service_runtime import _int_or_default, _legend_line, _storefront_service_profile
from game.skills import actor_skill as _actor_skill
from game.system_support.container_runtime import _unlink_removed_item_from_gear
from game.system_support.item_provenance_runtime import CLAIM_MERCHANDISE, stamp_item_provenance
from game.system_support.npc_income_runtime import inventory_liquid_credits, spend_npc_wallet_credits
from game.system_support.offense_runtime import _emit_action_offense_event
from game.system_support.awareness_runtime import observation_payload_for_position
from game.system_support.store_purchase_runtime import (
    INTEREST_ADJACENT,
    INTEREST_REFUSED,
    INTEREST_UNUSUAL,
    canonical_store_item_id,
    classify_store_purchase_interest,
)
from game.system_support.street_vendor_trade_runtime import (
    STREET_TRADE_SOURCE_KIND,
    ensure_street_vendor_stock,
    street_vendor_buy_rows,
    street_vendor_contact_profile,
    street_vendor_sell_rows,
)
from game.system_support.throwable_runtime import throwable_summary_text


def _default_trade_contact_terms(_sim, _viewer_eid, _prop):
    return {
        "buy_mult": 1.0,
        "sell_mult": 1.0,
        "source_eid": None,
        "note": "",
    }


def _item_display_glyph(item_def):
    return _appearance_item_display_glyph(item_def)


def _item_legend_line(item_id, text):
    item_def = ITEM_CATALOG.get(item_id, {})
    return _legend_line(
        text,
        glyph=_item_display_glyph(item_def),
        color=_ground_item_color(item_def),
        attrs=getattr(curses, "A_BOLD", 0),
    )


def _item_trade_trait_text(item_id):
    item_def = ITEM_CATALOG.get(str(item_id or "").strip().lower(), {})
    if not isinstance(item_def, dict):
        return ""
    bits = []
    armor = item_def.get("armor") if isinstance(item_def.get("armor"), dict) else {}
    if armor:
        try:
            bits.append(f"armor reduction {int(round(float(armor.get('damage_reduction', 0.0)) * 100.0))}%")
        except (TypeError, ValueError):
            bits.append("armor")
    disguise = item_def.get("disguise") if isinstance(item_def.get("disguise"), dict) else {}
    role_id = str(disguise.get("role_id", "") or "").strip().replace("_", " ")
    if role_id:
        try:
            strength_pct = int(round(max(0.0, float(disguise.get("strength", 1.0))) * 100.0))
        except (TypeError, ValueError):
            strength_pct = 100
        bits.append(f"cover {role_id} {strength_pct}%")
    throw_text = throwable_summary_text(item_def.get("throw_profile"), include_consumed=False)
    if throw_text:
        bits.append(throw_text)
    legal_status = str(item_def.get("legal_status", "legal") or "legal").strip().lower()
    if legal_status in {"restricted", "illegal"}:
        bits.append(legal_status)
    return "; ".join(bits)


def _trade_item_line(row, base_text):
    trait_text = _item_trade_trait_text(row.get("item_id"))
    if trait_text:
        return f"{base_text} - {trait_text}"
    return base_text


def _metadata_float(metadata, key, default=0.0):
    if not isinstance(metadata, dict):
        return float(default)
    try:
        value = metadata.get(key, default)
        if value is None:
            raise TypeError
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _metadata_weight_mults(metadata):
    if not isinstance(metadata, dict):
        return {}
    raw = metadata.get("trade_item_weight_mults")
    if not isinstance(raw, dict):
        return {}
    out = {}
    for item_id, value in raw.items():
        key = str(item_id or "").strip().lower()
        if not key:
            continue
        try:
            out[key] = max(0.05, float(value))
        except (TypeError, ValueError):
            continue
    return out


def _join_notes(*parts):
    seen = set()
    notes = []
    for part in parts:
        text = str(part or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        notes.append(text)
    return "; ".join(notes)


def _clamp_float(value, low, high, default=0.0):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = float(default)
    return max(float(low), min(float(high), number))


def _item_tags(item_id):
    item_def = ITEM_CATALOG.get(str(item_id or "").strip().lower(), {})
    tags = {
        str(tag).strip().lower()
        for tag in item_def.get("tags", ())
        if str(tag).strip()
    }
    appearance_family = str(item_def.get("appearance_family", "") or "").strip().lower()
    if appearance_family:
        tags.add(appearance_family)
    category = str(item_def.get("category", "") or "").strip().lower()
    if category:
        tags.add(category)
    if item_def.get("legal_status") == "illegal" and tags.intersection({"stimulant", "medical", "injectable"}):
        tags.add("drug")
    return tags


def _merge_effect_modifiers(base, extra):
    merged = dict(base or {})
    for raw_key, raw_value in dict(extra or {}).items():
        key = str(raw_key or "").strip().lower().replace(" ", "_")
        if not key:
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue
        if key.endswith("_mult") or key.endswith("_scalar"):
            current = float(merged.get(key, 1.0) or 1.0)
            merged[key] = current * max(0.0, value)
        else:
            current = float(merged.get(key, 0.0) or 0.0)
            merged[key] = current + value
    return merged


def _merged_practice_bundle(bundle, *, extra_modifiers=None, extra_note="", source_fields=None):
    base = bundle if isinstance(bundle, dict) else {}
    extra_modifiers = dict(extra_modifiers or {})
    note = str(extra_note or "").strip()
    if not extra_modifiers and not note and not source_fields:
        return dict(base)

    notes = [
        str(text).strip()
        for text in tuple(base.get("notes", ()) or ())
        if str(text).strip()
    ]
    if note and note not in notes:
        notes.append(note)
    merged = {
        **base,
        "rows": tuple(base.get("rows", ()) or ()),
        "entry_keys": tuple(base.get("entry_keys", ()) or ()),
        "effect_modifiers": _merge_effect_modifiers(base.get("effect_modifiers"), extra_modifiers),
        "notes": tuple(notes),
        "note_text": "; ".join(notes),
        "count": int(base.get("count", len(tuple(base.get("rows", ()) or ())))) + (1 if extra_modifiers else 0),
    }
    if isinstance(source_fields, dict):
        merged.update(source_fields)
    return merged


class TradeSystem(System):

    STOREFRONT_ARCHETYPES = {
        "bait_shop",
        "corner_store",
        "outfitter",
        "restaurant",
        "pawn_shop",
        "backroom_clinic",
        "nightclub",
        "arcade",
        "bar",
        "auto_garage",
        "daycare",
        "laundromat",
        "pharmacy",
        "hotel",
        "herbalist_camp",
        "chop_shop",
        "junk_market",
        "soup_kitchen",
        "tool_depot",
        "bookshop",
        "hardware_store",
        "service_station",
        "gallery",
        "flophouse",
        "street_kitchen",
        "theater",
        "thrift_store",
        "music_venue",
        "gaming_hall",
        "surplus_store",
        "truck_stop",
        "karaoke_box",
        "pool_hall",
    }

    VEHICLE_TRADE_IN_VALUE_BY_QUALITY = {
        "new": 0.72,
        "used": 0.58,
    }

    ITEM_BASE_VALUES = {
        "street_ration": 10,
        "protein_wrap": 11,
        "noodle_cup": 9,
        "spark_brew": 14,
        "calm_patch": 18,
        "caff_shot": 16,
        "hydration_salts": 15,
        "med_gel": 22,
        "micro_medkit": 18,
        "trauma_foam": 34,
        "trauma_autoinjector": 92,
        "shiver_patch": 42,
        "counterfeit_med_gel": 18,
        "sedative_ampoule": 52,
        "burner_serum": 46,
        "focus_inhaler": 30,
        "synth_focus_tabs": 24,
        "smoke_tab": 13,
        "cocaine_bindle": 32,
        "mdma_capsule": 30,
        "lsd_blotter": 26,
        "credstick_chip": 20,
        "city_pass_token": 7,
        "transit_daypass": 12,
        "meal_voucher": 11,
        "parking_stub": 3,
        "metro_flyer": 2,
        "scratch_ticket": 6,
        "tattoo_service": 85,
        "pocket_notebook": 5,
        "deck_of_cards": 7,
        "phone": 22,
        "burner_phone": 22,
        "forged_badge": 40,
        "energy_bar": 9,
        "bottled_water": 7,
        "instant_soup_pack": 12,
        "canteen_coffee": 15,
        "cheap_whiskey": 10,
        "mint_strip": 6,
        "bandage_roll": 11,
        "field_dressing": 14,
        "pain_blocker": 19,
        "scrap_circuit": 14,
        "battery_pack": 15,
        "light_ammo_box": 24,
        "shell_bandolier": 28,
        "rifle_mag_crate": 32,
        "rocket_tube_pack": 48,
        "pocket_multitool": 28,
        "lucky_charm": 9,
        "lockpick_kit": 36,
        "prybar": 32,
        "signal_jammer": 42,
        "glass_cutter": 34,
        "hotwire_leads": 30,
        "cloned_thumb": 52,
        "black_market_stim": 44,
        "shiv_knife": 72,
        "crowbar_club": 84,
        "telescopic_baton": 92,
        "trail_machete": 88,
        "fire_axe": 98,
        "holdout_pistol": 108,
        "service_pistol": 146,
        "rust_revolver": 132,
        "heavy_revolver": 156,
        "alley_shotgun": 168,
        "sawed_off_shotgun": 174,
        "machine_pistol": 188,
        "compact_smg": 226,
        "machine_carbine": 248,
        "patrol_carbine": 238,
        "hunting_rifle": 256,
        "improvised_launcher": 284,
        "grenade_launcher": 308,
        "recoilless_launcher": 356,
        "smoke_grenade": 64,
        "tear_gas_canister": 82,
        "toxic_aerosol_canister": 96,
        "dissociative_aerosol": 112,
        "hallucinogen_aerosol": 108,
        "courier_mesh": 42,
        "padded_jacket": 54,
        "field_vest": 74,
        "security_vest": 96,
        "riot_plates": 124,
        "ceramic_plate_rig": 158,
    }

    DEFAULT_PROFILE = {
        "min_slots": 3,
        "max_slots": 5,
        "min_stock": 1,
        "max_stock": 4,
        "buy_mult_lo": 1.05,
        "buy_mult_hi": 1.45,
        "sell_ratio": 0.46,
        "unlisted_sell_ratio": 0.28,
        "item_pool": (
            ("street_ration", 24),
            ("energy_bar", 18),
            ("bottled_water", 16),
            ("spark_brew", 20),
            ("calm_patch", 16),
            ("caff_shot", 14),
            ("city_pass_token", 20),
            ("meal_voucher", 10),
            ("med_gel", 10),
            ("field_dressing", 8),
            ("focus_inhaler", 8),
            ("scratch_ticket", 8),
            ("deck_of_cards", 6),
            ("battery_pack", 6),
            ("light_ammo_box", 6),
            ("lockpick_kit", 4),
            ("shiv_knife", 4),
            ("crowbar_club", 3),
            ("black_market_stim", 2),
            ("cocaine_bindle", 2),
        ),
    }

    STORE_PROFILES = {
        "corner_store": {
            "buy_mult_lo": 0.95,
            "buy_mult_hi": 1.25,
            "item_pool": (
                ("street_ration", 30),
                ("protein_wrap", 22),
                ("noodle_cup", 18),
                ("energy_bar", 16),
                ("spark_brew", 22),
                ("bottled_water", 18),
                ("caff_shot", 18),
                ("hydration_salts", 12),
                ("electrolyte_drink", 12),
                ("water_purifier_tabs", 7),
                ("glucose_gel", 7),
                ("light_ammo_box", 8),
                ("pocket_light_rounds", 6),
                ("city_pass_token", 26),
                ("transit_daypass", 14),
                ("meal_voucher", 12),
                ("scratch_ticket", 10),
                ("deck_of_cards", 8),
                ("mint_strip", 10),
                ("calm_patch", 14),
                ("med_gel", 9),
                ("cheap_whiskey", 10),
                ("glass_bottle", 5),
                ("focus_inhaler", 6),
            ),
        },
        "restaurant": {
            "min_slots": 2,
            "max_slots": 4,
            "buy_mult_lo": 0.92,
            "buy_mult_hi": 1.18,
            "item_pool": (
                ("street_ration", 35),
                ("protein_wrap", 28),
                ("noodle_cup", 22),
                ("instant_soup_pack", 18),
                ("spark_brew", 26),
                ("bottled_water", 16),
                ("city_pass_token", 22),
                ("meal_voucher", 12),
                ("caff_shot", 10),
                ("cheap_whiskey", 8),
                ("calm_patch", 6),
            ),
        },
        "pawn_shop": {
            "buy_mult_lo": 1.08,
            "buy_mult_hi": 1.42,
            "sell_ratio": 0.52,
            "unlisted_sell_ratio": 0.34,
            "item_pool": (
                ("city_pass_token", 20),
                ("credstick_chip", 14),
                ("lucky_charm", 12),
                ("forged_badge", 12),
                ("battery_pack", 10),
                ("lockpick_kit", 18),
                ("glass_cutter", 14),
                ("hotwire_leads", 10),
                ("pocket_multitool", 10),
                ("prybar", 12),
                ("bolt_cutters", 8),
                ("inspection_mirror", 7),
                ("shiv_knife", 12),
                ("box_cutter", 8),
                ("crowbar_club", 10),
                ("tire_iron", 7),
                ("telescopic_baton", 8),
                ("fire_axe", 6),
                ("holdout_pistol", 14),
                ("snub_revolver", 9),
                ("surplus_pistol", 8),
                ("pipe_pistol", 5),
                ("service_pistol", 10),
                ("rust_revolver", 10),
                ("heavy_revolver", 8),
                ("alley_shotgun", 6),
                ("sawed_off_shotgun", 5),
                ("pump_shotgun", 6),
                ("varmint_rifle", 5),
                ("machine_pistol", 8),
                ("padded_jacket", 10),
                ("courier_mesh", 10),
                ("stab_vest", 8),
                ("armored_motor_jacket", 6),
                ("security_vest", 8),
                ("scrap_circuit", 9),
                ("signal_jammer", 10),
                ("cloned_thumb", 6),
                ("black_market_stim", 8),
                ("cocaine_bindle", 6),
                ("mdma_capsule", 4),
                ("light_ammo_box", 12),
                ("pocket_light_rounds", 12),
                ("bulk_light_rounds", 8),
                ("shell_bandolier", 8),
                ("buckshot_pouch", 8),
                ("rifle_strip_pack", 7),
                ("focus_inhaler", 10),
                ("caff_shot", 12),
                ("street_ration", 8),
            ),
        },
        "backroom_clinic": {
            "buy_mult_lo": 1.0,
            "buy_mult_hi": 1.34,
            "sell_ratio": 0.5,
            "item_pool": (
                ("med_gel", 28),
                ("micro_medkit", 22),
                ("hydration_salts", 18),
                ("electrolyte_drink", 12),
                ("water_purifier_tabs", 10),
                ("glucose_gel", 10),
                ("calm_patch", 22),
                ("trauma_foam", 14),
                ("trauma_autoinjector", 4),
                ("shiver_patch", 8),
                ("counterfeit_med_gel", 6),
                ("sedative_ampoule", 8),
                ("burner_serum", 7),
                ("antiseptic_wipes", 12),
                ("suture_kit", 8),
                ("emergency_blanket", 8),
                ("field_dressing", 18),
                ("focus_inhaler", 14),
                ("caff_shot", 9),
                ("street_ration", 8),
            ),
        },
        "backroom_market": {
            "buy_mult_lo": 1.14,
            "buy_mult_hi": 1.62,
            "sell_ratio": 0.58,
            "unlisted_sell_ratio": 0.38,
            "item_pool": (
                ("phone", 12),
                ("lockpick_kit", 16),
                ("glass_cutter", 12),
                ("hotwire_leads", 10),
                ("signal_jammer", 12),
                ("cloned_thumb", 8),
                ("bolt_cutters", 8),
                ("inspection_mirror", 7),
                ("med_gel", 10),
                ("counterfeit_med_gel", 8),
                ("trauma_foam", 8),
                ("burner_serum", 8),
                ("trauma_autoinjector", 3),
                ("focus_inhaler", 10),
                ("black_market_stim", 12),
                ("cocaine_bindle", 10),
                ("mdma_capsule", 8),
                ("lsd_blotter", 6),
                ("fentanyl_patch", 4),
                ("heroin_syringe", 4),
                ("ketamine_vial", 5),
                ("forged_badge", 8),
                ("contractor_badge_lanyard", 5),
                ("credstick_chip", 12),
                ("holdout_pistol", 6),
                ("snub_revolver", 5),
                ("pipe_pistol", 4),
                ("light_ammo_box", 8),
                ("pocket_light_rounds", 8),
                ("molotov_cocktail", 3),
                ("smoke_grenade", 3),
                ("tear_gas_canister", 2),
                ("toxic_aerosol_canister", 1),
                ("dissociative_aerosol", 1),
                ("hallucinogen_aerosol", 1),
            ),
        },
        "nightclub": {
            "buy_mult_lo": 1.02,
            "buy_mult_hi": 1.38,
            "item_pool": (
                ("spark_brew", 34),
                ("cheap_whiskey", 24),
                ("smoke_tab", 20),
                ("cocaine_bindle", 10),
                ("mdma_capsule", 10),
                ("lsd_blotter", 6),
                ("mint_strip", 12),
                ("deck_of_cards", 10),
                ("phone", 8),
                ("caff_shot", 20),
                ("synth_focus_tabs", 10),
                ("credstick_chip", 12),
                ("black_market_stim", 8),
                ("city_pass_token", 16),
                ("calm_patch", 8),
            ),
        },
        "arcade": {
            "buy_mult_lo": 0.96,
            "buy_mult_hi": 1.26,
            "item_pool": (
                ("city_pass_token", 30),
                ("transit_daypass", 18),
                ("credstick_chip", 10),
                ("scratch_ticket", 10),
                ("caff_shot", 24),
                ("spark_brew", 18),
                ("deck_of_cards", 8),
                ("street_ration", 12),
                ("calm_patch", 10),
            ),
        },
        "bar": {
            "buy_mult_lo": 0.97,
            "buy_mult_hi": 1.32,
            "item_pool": (
                ("spark_brew", 34),
                ("cheap_whiskey", 26),
                ("smoke_tab", 16),
                ("cocaine_bindle", 4),
                ("deck_of_cards", 12),
                ("mint_strip", 10),
                ("caff_shot", 18),
                ("street_ration", 18),
                ("instant_soup_pack", 10),
                ("protein_wrap", 14),
                ("noodle_cup", 12),
                ("city_pass_token", 14),
                ("black_market_stim", 7),
            ),
        },
        "auto_garage": {
            "buy_mult_lo": 1.02,
            "buy_mult_hi": 1.48,
            "item_pool": (
                ("lockpick_kit", 20),
                ("prybar", 18),
                ("battery_pack", 12),
                ("hotwire_leads", 14),
                ("pocket_multitool", 12),
                ("scrap_circuit", 10),
                ("signal_jammer", 10),
                ("city_pass_token", 20),
                ("caff_shot", 18),
                ("protein_wrap", 10),
                ("padded_jacket", 7),
                ("street_ration", 12),
                ("black_market_stim", 7),
                ("cocaine_bindle", 4),
                ("med_gel", 8),
            ),
        },
        "tool_depot": {
            "buy_mult_lo": 0.98,
            "buy_mult_hi": 1.34,
            "item_pool": (
                ("lockpick_kit", 16),
                ("prybar", 18),
                ("glass_cutter", 12),
                ("battery_pack", 12),
                ("hotwire_leads", 10),
                ("pocket_multitool", 14),
                ("scrap_circuit", 10),
                ("signal_jammer", 8),
                ("padded_jacket", 10),
                ("bandage_roll", 10),
                ("caff_shot", 10),
                ("city_pass_token", 12),
                ("street_ration", 10),
            ),
        },
        "daycare": {
            "min_slots": 2,
            "max_slots": 4,
            "buy_mult_lo": 0.9,
            "buy_mult_hi": 1.2,
            "item_pool": (
                ("street_ration", 34),
                ("protein_wrap", 22),
                ("noodle_cup", 18),
                ("energy_bar", 12),
                ("bottled_water", 14),
                ("calm_patch", 22),
                ("hydration_salts", 12),
                ("city_pass_token", 22),
                ("meal_voucher", 12),
                ("spark_brew", 10),
            ),
        },
        "laundromat": {
            "buy_mult_lo": 0.93,
            "buy_mult_hi": 1.21,
            "item_pool": (
                ("street_ration", 25),
                ("protein_wrap", 16),
                ("noodle_cup", 14),
                ("bottled_water", 14),
                ("city_pass_token", 24),
                ("transit_daypass", 16),
                ("parking_stub", 12),
                ("scratch_ticket", 10),
                ("spark_brew", 17),
                ("caff_shot", 13),
                ("calm_patch", 11),
            ),
        },
        "pharmacy": {
            "buy_mult_lo": 0.98,
            "buy_mult_hi": 1.3,
            "sell_ratio": 0.48,
            "item_pool": (
                ("med_gel", 32),
                ("micro_medkit", 24),
                ("bandage_roll", 24),
                ("field_dressing", 20),
                ("hydration_salts", 22),
                ("bottled_water", 12),
                ("calm_patch", 24),
                ("pain_blocker", 16),
                ("trauma_foam", 16),
                ("trauma_autoinjector", 5),
                ("counterfeit_med_gel", 4),
                ("focus_inhaler", 16),
                ("synth_focus_tabs", 10),
                ("caff_shot", 12),
                ("street_ration", 8),
            ),
        },
        "bookshop": {
            "buy_mult_lo": 0.92,
            "buy_mult_hi": 1.18,
            "item_pool": (
                ("city_pass_token", 30),
                ("transit_daypass", 18),
                ("metro_flyer", 22),
                ("pocket_notebook", 12),
                ("mint_strip", 12),
                ("canteen_coffee", 12),
                ("deck_of_cards", 10),
                ("calm_patch", 12),
                ("focus_inhaler", 8),
                ("spark_brew", 8),
                ("street_ration", 10),
            ),
        },
        "hardware_store": {
            "buy_mult_lo": 0.98,
            "buy_mult_hi": 1.36,
            "item_pool": (
                ("lockpick_kit", 14),
                ("prybar", 16),
                ("glass_cutter", 10),
                ("battery_pack", 12),
                ("hotwire_leads", 8),
                ("pocket_multitool", 16),
                ("scrap_circuit", 10),
                ("signal_jammer", 6),
                ("padded_jacket", 12),
                ("courier_mesh", 10),
                ("security_vest", 6),
                ("riot_plates", 4),
                ("light_ammo_box", 10),
                ("shell_bandolier", 7),
                ("rifle_mag_crate", 6),
                ("smoke_grenade", 2),
                ("tear_gas_canister", 1),
                ("bandage_roll", 10),
                ("city_pass_token", 12),
                ("street_ration", 10),
            ),
        },
        "service_station": {
            "buy_mult_lo": 0.97,
            "buy_mult_hi": 1.28,
            "sell_ratio": 0.44,
            "item_pool": (
                ("street_ration", 28),
                ("protein_wrap", 20),
                ("noodle_cup", 16),
                ("bottled_water", 20),
                ("spark_brew", 18),
                ("caff_shot", 16),
                ("city_pass_token", 24),
                ("transit_daypass", 12),
                ("parking_stub", 14),
                ("battery_pack", 12),
                ("bandage_roll", 10),
                ("med_gel", 8),
                ("field_dressing", 8),
                ("pocket_multitool", 8),
                ("light_ammo_box", 6),
            ),
        },
        "top_shop": {
            "min_slots": 3,
            "max_slots": 5,
            "buy_mult_lo": 0.98,
            "buy_mult_hi": 1.32,
            "sell_ratio": 0.46,
            "item_pool": (
                ("tee", 16),
                ("button_up", 14),
                ("blouse", 12),
                ("sweater", 12),
                ("overshirt", 12),
                ("turtleneck", 10),
            ),
        },
        "bottom_shop": {
            "min_slots": 3,
            "max_slots": 5,
            "buy_mult_lo": 0.98,
            "buy_mult_hi": 1.32,
            "sell_ratio": 0.46,
            "item_pool": (
                ("trousers", 16),
                ("shorts", 12),
                ("skirt", 12),
            ),
        },
        "dress_shop": {
            "min_slots": 2,
            "max_slots": 4,
            "buy_mult_lo": 1.02,
            "buy_mult_hi": 1.42,
            "sell_ratio": 0.48,
            "item_pool": (
                ("dress", 18),
                ("blazer", 8),
                ("cardigan", 8),
                ("necklace", 6),
                ("bracelet", 6),
            ),
        },
        "shoe_shop": {
            "min_slots": 2,
            "max_slots": 4,
            "buy_mult_lo": 1.0,
            "buy_mult_hi": 1.36,
            "sell_ratio": 0.48,
            "item_pool": (
                ("boots", 14),
                ("sneakers", 14),
                ("sandals", 10),
            ),
        },
        "outerwear_shop": {
            "min_slots": 3,
            "max_slots": 5,
            "buy_mult_lo": 1.02,
            "buy_mult_hi": 1.44,
            "sell_ratio": 0.5,
            "item_pool": (
                ("jacket", 14),
                ("windbreaker", 12),
                ("coat", 12),
                ("cardigan", 10),
                ("blazer", 10),
                ("vest", 9),
            ),
        },
        "headwear_shop": {
            "min_slots": 2,
            "max_slots": 4,
            "buy_mult_lo": 0.94,
            "buy_mult_hi": 1.24,
            "sell_ratio": 0.42,
            "item_pool": (
                ("cap", 14),
                ("baseball_cap", 14),
                ("bandana", 12),
                ("scarf", 8),
            ),
        },
        "jewelry_shop": {
            "min_slots": 3,
            "max_slots": 5,
            "buy_mult_lo": 1.08,
            "buy_mult_hi": 1.6,
            "sell_ratio": 0.52,
            "item_pool": (
                ("earrings", 12),
                ("ring", 12),
                ("necklace", 12),
                ("bracelet", 10),
                ("watch", 8),
            ),
        },
        "accessory_shop": {
            "min_slots": 3,
            "max_slots": 5,
            "buy_mult_lo": 0.98,
            "buy_mult_hi": 1.34,
            "sell_ratio": 0.46,
            "item_pool": (
                ("scarf", 12),
                ("bracelet", 10),
                ("gloves", 10),
                ("watch", 8),
                ("bandana", 8),
                ("cap", 6),
                ("earrings", 6),
                ("ring", 6),
            ),
        },
        "tattoo_parlor": {
            "min_slots": 3,
            "max_slots": 5,
            "min_stock": 1,
            "max_stock": 2,
            "buy_mult_lo": 1.05,
            "buy_mult_hi": 1.5,
            "sell_ratio": 0.0,
            "unlisted_sell_ratio": 0.0,
            "item_pool": (
                (TATTOO_SERVICE_ITEM_ID, 20),
            ),
        },
        "outfitter": {
            "min_slots": 3,
            "max_slots": 5,
            "buy_mult_lo": 0.98,
            "buy_mult_hi": 1.34,
            "sell_ratio": 0.48,
            "item_pool": (
                ("light_ammo_box", 18),
                ("pocket_light_rounds", 12),
                ("shell_bandolier", 14),
                ("buckshot_pouch", 10),
                ("rifle_mag_crate", 10),
                ("rifle_strip_pack", 8),
                ("trail_machete", 12),
                ("fire_axe", 9),
                ("holdout_pistol", 10),
                ("snub_revolver", 7),
                ("surplus_pistol", 7),
                ("service_pistol", 4),
                ("alley_shotgun", 8),
                ("pump_shotgun", 6),
                ("sawed_off_shotgun", 5),
                ("hunting_rifle", 8),
                ("varmint_rifle", 6),
                ("machine_carbine", 4),
                ("padded_jacket", 12),
                ("field_vest", 12),
                ("courier_mesh", 10),
                ("stab_vest", 10),
                ("armored_motor_jacket", 8),
                ("cutproof_apron", 6),
                ("maintenance_vest", 7),
                ("pocket_multitool", 8),
                ("bandage_roll", 10),
                ("field_dressing", 10),
                ("electrolyte_drink", 10),
                ("water_purifier_tabs", 7),
                ("emergency_blanket", 7),
                ("energy_bar", 10),
                ("bottled_water", 10),
                ("tee", 12),
                ("button_up", 10),
                ("blouse", 8),
                ("sweater", 8),
                ("overshirt", 8),
                ("turtleneck", 7),
                ("trousers", 10),
                ("shorts", 8),
                ("skirt", 8),
                ("dress", 8),
                ("boots", 10),
                ("sneakers", 10),
                ("sandals", 7),
                ("cap", 8),
                ("baseball_cap", 8),
                ("bandana", 7),
                ("jacket", 10),
                ("windbreaker", 8),
                ("coat", 8),
                ("cardigan", 7),
                ("blazer", 7),
                ("vest", 7),
                ("earrings", 6),
                ("ring", 6),
                ("necklace", 6),
                ("scarf", 6),
                ("bracelet", 6),
                ("gloves", 6),
                ("watch", 5),
            ),
        },
        "surplus_store": {
            "min_slots": 4,
            "max_slots": 7,
            "buy_mult_lo": 1.02,
            "buy_mult_hi": 1.4,
            "sell_ratio": 0.5,
            "unlisted_sell_ratio": 0.34,
            "item_pool": (
                ("light_ammo_box", 20),
                ("pocket_light_rounds", 16),
                ("bulk_light_rounds", 16),
                ("shell_bandolier", 18),
                ("buckshot_pouch", 14),
                ("slug_sleeve", 10),
                ("rifle_mag_crate", 16),
                ("rifle_strip_pack", 12),
                ("carbine_mag_bundle", 12),
                ("rocket_tube_pack", 4),
                ("single_launcher_round", 5),
                ("trail_machete", 14),
                ("fire_axe", 10),
                ("box_cutter", 8),
                ("tire_iron", 8),
                ("telescopic_baton", 10),
                ("holdout_pistol", 10),
                ("snub_revolver", 8),
                ("surplus_pistol", 10),
                ("pipe_pistol", 4),
                ("service_pistol", 14),
                ("rust_revolver", 12),
                ("heavy_revolver", 8),
                ("alley_shotgun", 12),
                ("sawed_off_shotgun", 8),
                ("pump_shotgun", 10),
                ("riot_shotgun", 8),
                ("hunting_rifle", 12),
                ("varmint_rifle", 9),
                ("marksman_rifle", 5),
                ("patrol_carbine", 10),
                ("machine_carbine", 8),
                ("grenade_launcher", 4),
                ("recoilless_launcher", 2),
                ("smoke_grenade", 6),
                ("tear_gas_canister", 4),
                ("padded_jacket", 10),
                ("field_vest", 12),
                ("courier_mesh", 8),
                ("stab_vest", 8),
                ("armored_motor_jacket", 8),
                ("security_vest", 9),
                ("plate_carrier", 7),
                ("ballistic_helmet", 6),
                ("riot_plates", 6),
                ("ceramic_plate_rig", 4),
                ("maintenance_vest", 5),
                ("patrol_rain_shell", 5),
                ("bandage_roll", 10),
                ("field_dressing", 10),
                ("battery_pack", 8),
            ),
        },
        "thrift_store": {
            "buy_mult_lo": 0.9,
            "buy_mult_hi": 1.18,
            "sell_ratio": 0.42,
            "unlisted_sell_ratio": 0.28,
            "item_pool": (
                ("street_ration", 18),
                ("protein_wrap", 12),
                ("spark_brew", 12),
                ("deck_of_cards", 12),
                ("pocket_notebook", 10),
                ("lucky_charm", 10),
                ("battery_pack", 10),
                ("bandage_roll", 10),
                ("field_dressing", 9),
                ("pocket_multitool", 8),
                ("padded_jacket", 8),
                ("courier_mesh", 5),
                ("calm_patch", 8),
                ("smoke_tab", 6),
                ("city_pass_token", 10),
                ("tee", 14),
                ("button_up", 10),
                ("blouse", 7),
                ("sweater", 9),
                ("overshirt", 8),
                ("turtleneck", 6),
                ("trousers", 12),
                ("shorts", 10),
                ("skirt", 10),
                ("dress", 8),
                ("boots", 8),
                ("sneakers", 10),
                ("sandals", 8),
                ("cap", 10),
                ("baseball_cap", 10),
                ("bandana", 9),
                ("jacket", 8),
                ("windbreaker", 7),
                ("coat", 7),
                ("cardigan", 8),
                ("blazer", 6),
                ("vest", 7),
                ("earrings", 6),
                ("ring", 6),
                ("necklace", 6),
                ("scarf", 7),
                ("bracelet", 6),
                ("gloves", 7),
                ("watch", 5),
            ),
        },
        "hotel": {
            "buy_mult_lo": 0.96,
            "buy_mult_hi": 1.22,
            "item_pool": (
                ("street_ration", 28),
                ("protein_wrap", 18),
                ("noodle_cup", 16),
                ("bottled_water", 16),
                ("spark_brew", 24),
                ("city_pass_token", 22),
                ("transit_daypass", 16),
                ("parking_stub", 12),
                ("deck_of_cards", 8),
                ("mint_strip", 8),
                ("hydration_salts", 12),
                ("calm_patch", 14),
                ("caff_shot", 10),
                ("cheap_whiskey", 8),
            ),
        },
        "chop_shop": {
            "buy_mult_lo": 1.08,
            "buy_mult_hi": 1.55,
            "sell_ratio": 0.54,
            "unlisted_sell_ratio": 0.36,
            "item_pool": (
                ("lockpick_kit", 24),
                ("prybar", 18),
                ("bolt_cutters", 12),
                ("inspection_mirror", 8),
                ("battery_pack", 10),
                ("pocket_multitool", 12),
                ("scrap_circuit", 12),
                ("signal_jammer", 12),
                ("forged_badge", 10),
                ("glass_cutter", 14),
                ("hotwire_leads", 14),
                ("shiv_knife", 14),
                ("box_cutter", 8),
                ("crowbar_club", 12),
                ("tire_iron", 12),
                ("fire_axe", 8),
                ("telescopic_baton", 10),
                ("cloned_thumb", 8),
                ("black_market_stim", 10),
                ("cocaine_bindle", 8),
                ("mdma_capsule", 5),
                ("lsd_blotter", 4),
                ("light_ammo_box", 12),
                ("pocket_light_rounds", 8),
                ("bulk_light_rounds", 8),
                ("shell_bandolier", 10),
                ("buckshot_pouch", 8),
                ("rifle_mag_crate", 9),
                ("rifle_strip_pack", 7),
                ("rocket_tube_pack", 4),
                ("holdout_pistol", 16),
                ("snub_revolver", 8),
                ("surplus_pistol", 8),
                ("pipe_pistol", 6),
                ("service_pistol", 12),
                ("rust_revolver", 14),
                ("heavy_revolver", 8),
                ("alley_shotgun", 12),
                ("pump_shotgun", 8),
                ("sawed_off_shotgun", 8),
                ("machine_pistol", 10),
                ("compact_smg", 8),
                ("machine_carbine", 6),
                ("patrol_carbine", 7),
                ("grenade_launcher", 3),
                ("glass_bottle", 6),
                ("brick", 6),
                ("molotov_cocktail", 3),
                ("smoke_grenade", 4),
                ("tear_gas_canister", 3),
                ("toxic_aerosol_canister", 2),
                ("dissociative_aerosol", 1),
                ("hallucinogen_aerosol", 1),
                ("cutproof_apron", 5),
                ("maintenance_vest", 5),
                ("security_vest", 10),
                ("riot_plates", 8),
                ("ceramic_plate_rig", 6),
                ("phone", 10),
                ("smoke_tab", 10),
                ("city_pass_token", 16),
                ("caff_shot", 14),
                ("focus_inhaler", 8),
                ("street_ration", 8),
            ),
        },
        "junk_market": {
            "buy_mult_lo": 0.9,
            "buy_mult_hi": 1.38,
            "unlisted_sell_ratio": 0.38,
            "item_pool": (
                ("city_pass_token", 28),
                ("street_ration", 21),
                ("protein_wrap", 14),
                ("battery_pack", 12),
                ("lockpick_kit", 16),
                ("glass_cutter", 12),
                ("pocket_multitool", 12),
                ("hotwire_leads", 8),
                ("rust_revolver", 10),
                ("holdout_pistol", 12),
                ("padded_jacket", 12),
                ("courier_mesh", 10),
                ("security_vest", 7),
                ("prybar", 16),
                ("scrap_circuit", 14),
                ("signal_jammer", 10),
                ("forged_badge", 8),
                ("phone", 10),
                ("lucky_charm", 12),
                ("deck_of_cards", 10),
                ("spark_brew", 14),
                ("caff_shot", 14),
                ("black_market_stim", 5),
                ("cocaine_bindle", 4),
            ),
        },
        "truck_stop": {
            "buy_mult_lo": 0.93,
            "buy_mult_hi": 1.26,
            "item_pool": (
                ("street_ration", 30),
                ("protein_wrap", 20),
                ("energy_bar", 22),
                ("instant_soup_pack", 18),
                ("bottled_water", 20),
                ("canteen_coffee", 16),
                ("meal_voucher", 12),
                ("scratch_ticket", 8),
                ("battery_pack", 8),
                ("city_pass_token", 10),
            ),
        },
        "roadhouse": {
            "buy_mult_lo": 0.92,
            "buy_mult_hi": 1.24,
            "item_pool": (
                ("street_ration", 34),
                ("protein_wrap", 22),
                ("noodle_cup", 18),
                ("instant_soup_pack", 16),
                ("spark_brew", 24),
                ("bottled_water", 16),
                ("caff_shot", 18),
                ("canteen_coffee", 12),
                ("calm_patch", 14),
                ("cheap_whiskey", 12),
                ("hydration_salts", 10),
                ("med_gel", 8),
                ("deck_of_cards", 8),
                ("city_pass_token", 10),
            ),
        },
        "dock_shack": {
            "buy_mult_lo": 0.95,
            "buy_mult_hi": 1.3,
            "item_pool": (
                ("street_ration", 26),
                ("protein_wrap", 18),
                ("noodle_cup", 14),
                ("instant_soup_pack", 14),
                ("spark_brew", 18),
                ("bottled_water", 14),
                ("city_pass_token", 20),
                ("transit_daypass", 14),
                ("meal_voucher", 10),
                ("lockpick_kit", 10),
                ("caff_shot", 14),
                ("med_gel", 7),
            ),
        },
        "gallery": {
            "buy_mult_lo": 0.96,
            "buy_mult_hi": 1.24,
            "item_pool": (
                ("city_pass_token", 28),
                ("metro_flyer", 20),
                ("transit_daypass", 16),
                ("credstick_chip", 10),
                ("canteen_coffee", 10),
                ("mint_strip", 10),
                ("spark_brew", 8),
                ("street_ration", 8),
            ),
        },
        "flophouse": {
            "buy_mult_lo": 0.82,
            "buy_mult_hi": 1.08,
            "sell_ratio": 0.38,
            "item_pool": (
                ("street_ration", 32),
                ("protein_wrap", 16),
                ("instant_soup_pack", 14),
                ("bottled_water", 16),
                ("canteen_coffee", 10),
                ("city_pass_token", 16),
                ("parking_stub", 10),
                ("calm_patch", 10),
                ("bandage_roll", 10),
            ),
        },
        "street_kitchen": {
            "min_slots": 2,
            "max_slots": 4,
            "buy_mult_lo": 0.88,
            "buy_mult_hi": 1.12,
            "item_pool": (
                ("street_ration", 38),
                ("protein_wrap", 28),
                ("instant_soup_pack", 20),
                ("spark_brew", 18),
                ("canteen_coffee", 16),
                ("bottled_water", 14),
                ("city_pass_token", 10),
                ("meal_voucher", 10),
            ),
        },
        "bait_shop": {
            "buy_mult_lo": 0.94,
            "buy_mult_hi": 1.24,
            "item_pool": (
                ("street_ration", 18),
                ("protein_wrap", 16),
                ("instant_soup_pack", 14),
                ("bottled_water", 18),
                ("spark_brew", 12),
                ("meal_voucher", 10),
                ("battery_pack", 6),
                ("city_pass_token", 10),
            ),
        },
        "herbalist_camp": {
            "buy_mult_lo": 0.9,
            "buy_mult_hi": 1.18,
            "item_pool": (
                ("bottled_water", 22),
                ("bandage_roll", 18),
                ("hydration_salts", 20),
                ("calm_patch", 16),
                ("pain_blocker", 12),
                ("energy_bar", 10),
                ("mint_strip", 8),
            ),
        },
        "soup_kitchen": {
            "min_slots": 2,
            "max_slots": 4,
            "buy_mult_lo": 0.72,
            "buy_mult_hi": 1.0,
            "sell_ratio": 0.35,
            "item_pool": (
                ("street_ration", 42),
                ("protein_wrap", 24),
                ("noodle_cup", 22),
                ("city_pass_token", 25),
                ("hydration_salts", 12),
                ("calm_patch", 12),
                ("spark_brew", 8),
            ),
        },
        "theater": {
            "buy_mult_lo": 0.94,
            "buy_mult_hi": 1.28,
            "item_pool": (
                ("city_pass_token", 30),
                ("transit_daypass", 18),
                ("metro_flyer", 16),
                ("credstick_chip", 10),
                ("meal_voucher", 10),
                ("spark_brew", 24),
                ("caff_shot", 16),
                ("street_ration", 14),
                ("mint_strip", 8),
                ("smoke_tab", 8),
                ("focus_inhaler", 8),
            ),
        },
        "music_venue": {
            "buy_mult_lo": 0.98,
            "buy_mult_hi": 1.36,
            "item_pool": (
                ("spark_brew", 30),
                ("smoke_tab", 16),
                ("mint_strip", 10),
                ("caff_shot", 20),
                ("city_pass_token", 20),
                ("credstick_chip", 12),
                ("synth_focus_tabs", 10),
                ("black_market_stim", 6),
                ("mdma_capsule", 8),
                ("lsd_blotter", 4),
                ("street_ration", 12),
            ),
        },
        "gaming_hall": {
            "buy_mult_lo": 1.02,
            "buy_mult_hi": 1.42,
            "item_pool": (
                ("city_pass_token", 33),
                ("credstick_chip", 14),
                ("transit_daypass", 12),
                ("lucky_charm", 12),
                ("caff_shot", 20),
                ("spark_brew", 18),
                ("focus_inhaler", 12),
                ("smoke_tab", 9),
                ("black_market_stim", 5),
                ("cocaine_bindle", 5),
                ("mdma_capsule", 4),
            ),
        },
        "karaoke_box": {
            "buy_mult_lo": 0.99,
            "buy_mult_hi": 1.34,
            "item_pool": (
                ("spark_brew", 28),
                ("smoke_tab", 14),
                ("mint_strip", 12),
                ("caff_shot", 16),
                ("city_pass_token", 16),
                ("credstick_chip", 10),
                ("synth_focus_tabs", 8),
                ("street_ration", 10),
            ),
        },
        "pool_hall": {
            "buy_mult_lo": 0.96,
            "buy_mult_hi": 1.28,
            "item_pool": (
                ("spark_brew", 24),
                ("smoke_tab", 12),
                ("mint_strip", 10),
                ("caff_shot", 16),
                ("city_pass_token", 18),
                ("credstick_chip", 10),
                ("street_ration", 12),
                ("protein_wrap", 10),
            ),
        },
    }

    def __init__(self, sim, player_eid, *, trade_contact_terms=None):
        super().__init__(sim)
        self.player_eid = player_eid
        self.sim.trade_system = self
        self._trade_contact_terms = trade_contact_terms or _default_trade_contact_terms
        if not hasattr(self.sim, "stores"):
            self.sim.stores = {}
        if not hasattr(self.sim, "trade_unwanted_sale_pressure"):
            self.sim.trade_unwanted_sale_pressure = {}
        if not hasattr(self.sim, "trade_ui"):
            self.sim.trade_ui = {
                "open": False,
                "mode": "buy",
                "selected_index": 0,
                "rows": [],
                "inspect_text": "",
                "store_name": "",
                "property_id": None,
                "supply_note": "",
                "contact_note": "",
                "service_note": "",
                "service_eid": None,
                "owner_transfer": False,
                "source_kind": "storefront",
                "contact_eid": None,
                "available_modes": ("buy", "sell"),
                "vendor_kind": "",
            }
        self.sim.events.subscribe("player_action", self.on_player_action)
        self.sim.events.subscribe("property_interact", self.on_property_interact)
        self.sim.events.subscribe("trade_panel_open_request", self.on_trade_panel_open_request)
        self.sim.events.subscribe("trade_panel_close_request", self.on_trade_panel_close_request)
        self.sim.events.subscribe("trade_panel_mode_request", self.on_trade_panel_mode_request)
        self.sim.events.subscribe("trade_execute_request", self.on_trade_execute_request)

    def _assets_for(self, eid):
        return self.sim.ecs.get(PlayerAssets).get(eid)

    def _inventory_for(self, eid):
        return self.sim.ecs.get(Inventory).get(eid)

    def _position_for(self, eid):
        return self.sim.ecs.get(Position).get(eid)

    def _trade_terms(self, eid, prop):
        return self._trade_contact_terms(self.sim, eid, prop)

    def _actor_owns_property(self, eid, prop):
        if not isinstance(prop, dict):
            return False
        try:
            if int(prop.get("owner_eid") or 0) == int(eid):
                return True
        except (TypeError, ValueError):
            if prop.get("owner_eid") == eid:
                return True
        assets = self._assets_for(eid)
        if not assets:
            return False
        property_id = str(prop.get("id", "") or "").strip()
        return bool(property_id and property_id in getattr(assets, "owned_property_ids", set()))

    def _owner_transfer_enabled(self, eid, prop):
        return bool(self._actor_owns_property(eid, prop) and _property_is_storefront(prop))

    def _effective_buy_price(self, base_price, terms):
        return max(1, int(round(int(base_price) * float(terms.get("buy_mult", 1.0)))))

    def _effective_sell_price(self, base_price, terms):
        return max(1, int(round(int(base_price) * float(terms.get("sell_mult", 1.0)))))

    def _trade_ui_state(self):
        state = getattr(self.sim, "trade_ui", None)
        if state is None:
            state = {
                "open": False,
                "mode": "buy",
                "selected_index": 0,
                "rows": [],
                "inspect_text": "",
                "store_name": "",
                "property_id": None,
                "supply_note": "",
                "contact_note": "",
                "service_note": "",
                "service_eid": None,
                "source_kind": "storefront",
                "contact_eid": None,
                "available_modes": ("buy", "sell"),
                "vendor_kind": "",
            }
            self.sim.trade_ui = state
        else:
            state.setdefault("source_kind", "storefront")
            state.setdefault("contact_eid", None)
            state.setdefault("available_modes", ("buy", "sell"))
            state.setdefault("vendor_kind", "")
            state.setdefault("owner_transfer", False)
        return state

    def _store_profile(self, archetype):
        profile = dict(self.DEFAULT_PROFILE)
        profile.update(self.STORE_PROFILES.get(archetype, {}))
        return profile

    def _is_storefront(self, prop):
        return _property_is_storefront(prop)

    def _service_is_machine(self, service):
        if not isinstance(service, dict):
            return False
        mode = str(service.get("mode", "")).strip().lower()
        return mode == "automated" or bool(service.get("fallback_self_serve"))

    def _nearest_store(self, pos, radius=2, automated_only=False):
        nearby = self.sim.properties_in_radius(pos.x, pos.y, pos.z, r=radius)
        available = []
        blocked = []
        for prop in nearby:
            if not self._is_storefront(prop):
                continue
            metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
            if bool(metadata.get("dialogue_trade_only")):
                continue
            access = _evaluate_property_access(
                self.sim,
                self.player_eid,
                prop,
                x=pos.x,
                y=pos.y,
                z=pos.z,
            )
            if not access.can_use_services:
                continue
            dist = _property_distance(pos.x, pos.y, prop)
            service = _storefront_service_profile(self.sim, prop, actor_eid=self.player_eid)
            if automated_only and not self._service_is_machine(service):
                continue
            if service.get("available"):
                available.append((dist, prop, service))
            else:
                blocked.append((dist, prop, service))
        if available:
            available.sort(key=lambda row: row[0])
            return available[0][1], available[0][2]
        if blocked:
            blocked.sort(key=lambda row: row[0])
            return blocked[0][1], blocked[0][2]
        return None, None

    def _storefront_by_id(self, property_id):
        if not property_id:
            return None
        prop = self.sim.properties.get(property_id)
        if not self._is_storefront(prop):
            return None
        return prop

    def _resolve_store(self, pos, preferred_property_id=None, radius=2, automated_only=False):
        preferred = self._storefront_by_id(preferred_property_id)
        if preferred and int(preferred.get("z", 0)) == int(pos.z):
            covered = _property_covering(self.sim, pos.x, pos.y, pos.z)
            inside_preferred = isinstance(covered, dict) and str(covered.get("id", "")).strip() == str(preferred.get("id", "")).strip()
            if _property_distance(pos.x, pos.y, preferred) <= radius or inside_preferred:
                preferred_service = _storefront_service_profile(self.sim, preferred, actor_eid=self.player_eid)
                if not automated_only or self._service_is_machine(preferred_service):
                    return preferred, preferred_service
        return self._nearest_store(pos, radius=radius, automated_only=automated_only)

    def _npc_store_accessible(self, eid, prop, *, x=None, y=None, z=None):
        if not isinstance(prop, dict) or eid is None:
            return False, None
        focus = _property_focus_position(prop)
        if focus is None:
            return False, None
        fx, fy, fz = int(focus[0]), int(focus[1]), int(focus[2])
        try:
            sx = int(x if x is not None else fx)
            sy = int(y if y is not None else fy)
            sz = int(z if z is not None else fz)
        except (TypeError, ValueError):
            sx, sy, sz = fx, fy, fz
        if int(prop.get("z", sz) or sz) != int(sz):
            return False, None
        access = _evaluate_property_access(self.sim, eid, prop, x=sx, y=sy, z=sz)
        if not access.can_use_services:
            return False, None
        service = _storefront_service_profile(self.sim, prop, actor_eid=eid)
        if not isinstance(service, dict) or not bool(service.get("available")):
            return False, service if isinstance(service, dict) else None
        if self._trade_denial(eid, prop) is not None:
            return False, service
        return True, service

    def npc_purchase_options(self, eid, pos, *, radius=8, max_price=None, preferred_property_id=None):
        """Return nearby concrete store-stock rows an NPC can buy with carried credits."""
        inventory = self._inventory_for(eid)
        if inventory is None or pos is None:
            return []
        try:
            actor_eid = int(eid)
            radius = max(1, int(radius))
        except (TypeError, ValueError):
            return []
        wallet = inventory_liquid_credits(inventory)
        try:
            max_price = None if max_price is None else max(0, int(max_price))
        except (TypeError, ValueError):
            max_price = None

        props = []
        preferred = self._storefront_by_id(preferred_property_id)
        if preferred is not None:
            props.append(preferred)
        for prop in self.sim.properties_in_radius(pos.x, pos.y, pos.z, r=radius):
            if not isinstance(prop, dict):
                continue
            if preferred is not None and str(prop.get("id", "") or "").strip() == str(preferred.get("id", "") or "").strip():
                continue
            props.append(prop)

        rows = []
        seen = set()
        for prop in props:
            if not self._is_storefront(prop):
                continue
            metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
            if bool(metadata.get("dialogue_trade_only")):
                continue
            focus = _property_focus_position(prop)
            if focus is None or int(focus[2]) != int(pos.z):
                continue
            distance = abs(int(pos.x) - int(focus[0])) + abs(int(pos.y) - int(focus[1]))
            if distance > radius and (
                preferred is None
                or str(prop.get("id", "") or "").strip() != str(preferred.get("id", "") or "").strip()
            ):
                continue
            accessible, service = self._npc_store_accessible(actor_eid, prop, x=focus[0], y=focus[1], z=focus[2])
            if not accessible:
                continue
            store = self._store_state(prop)
            terms = self._trade_terms(actor_eid, prop)
            for entry in tuple(store.get("entries", ()) or ()):
                item_id = str(entry.get("item_id", "") or "").strip().lower()
                if not item_id or int(entry.get("stock", 0) or 0) <= 0:
                    continue
                price = self._effective_buy_price(entry.get("buy_price", 1), terms)
                if max_price is not None and price > max_price:
                    continue
                if price > wallet:
                    continue
                key = (str(prop.get("id", "") or "").strip(), item_id)
                if key in seen:
                    continue
                seen.add(key)
                item_def = ITEM_CATALOG.get(item_id, {"name": item_id})
                row_entry = {
                    "item_id": item_id,
                    "metadata": entry.get("metadata") if isinstance(entry.get("metadata"), dict) else None,
                }
                rows.append({
                    "property_id": str(prop.get("id", "") or "").strip() or None,
                    "property_name": str(prop.get("name", prop.get("id", "store")) or "store").strip() or "store",
                    "store_name": str(prop.get("name", prop.get("id", "store")) or "store").strip() or "store",
                    "archetype": str(metadata.get("archetype", "") or "").strip().lower(),
                    "target": (int(focus[0]), int(focus[1]), int(focus[2])),
                    "distance": int(distance),
                    "service_eid": service.get("service_eid") if isinstance(service, dict) else None,
                    "item_id": item_id,
                    "item_name": item_display_name_for_actor(self.sim, self.player_eid, row_entry, item_catalog=ITEM_CATALOG),
                    "category": str(item_def.get("category", "") or "").strip().lower(),
                    "tags": tuple(_item_tags(item_id)),
                    "price": int(price),
                    "base_price": int(max(1, entry.get("buy_price", 1))),
                    "stock": int(max(0, entry.get("stock", 0) or 0)),
                    "wallet": int(wallet),
                })
        rows.sort(key=lambda row: (int(row.get("distance", 0)), int(row.get("price", 0)), str(row.get("item_id", ""))))
        return rows

    def _trade_practice_bundle(self, prop):
        bundle = property_trade_practice_bundle(
            self.sim,
            prop,
            current_tick=getattr(self.sim, "tick", 0),
        )
        workplace = local_workplace_org_posture(
            self.sim,
            prop,
            current_tick=getattr(self.sim, "tick", 0),
        )
        instability = organization_instability_profile(self.sim, prop=prop, ensure=True)
        if (not isinstance(instability, dict) or not bool(instability.get("unstable"))) and not workplace.get("note_text"):
            return bundle

        extra_modifiers = {}
        extra_notes = []
        if isinstance(instability, dict) and bool(instability.get("unstable")):
            instability_value = float(instability.get("instability", 0.0) or 0.0)
            underrepresented = bool(instability.get("underrepresented", False))
            extra_modifiers.update(
                {
                    "trade_stock_mult": max(0.55, 1.0 - (instability_value * 0.14) - (0.08 if underrepresented else 0.0)),
                    "trade_buy_price_mult": min(1.25, 1.0 + (instability_value * 0.06) + (0.05 if underrepresented else 0.0)),
                }
            )
            note = str(instability.get("note", "") or "").strip()
            if note:
                extra_notes.append(f"{note} and the stock looks inconsistent")
            else:
                extra_notes.append("the stock looks inconsistent")
        workplace_note = str(workplace.get("note_text", "") or "").strip()
        if workplace_note:
            extra_notes.append(workplace_note)
        return _merged_practice_bundle(bundle, extra_modifiers=extra_modifiers, extra_note=_join_notes(*extra_notes))

    def _item_realization_bundle(self, prop, item_id):
        bundle = property_item_practice_bundle(
            self.sim,
            prop,
            item_id,
            current_tick=getattr(self.sim, "tick", 0),
            realization_kind="trade_purchase",
        )
        instability = organization_instability_profile(self.sim, prop=prop, ensure=True)
        if not isinstance(instability, dict) or not bool(instability.get("unstable")):
            return bundle

        tags = _item_tags(item_id)
        instability_value = float(instability.get("instability", 0.0) or 0.0)
        pressure = float(instability.get("operational_pressure", instability_value) or instability_value)
        underrepresented = bool(instability.get("underrepresented", False))
        extra_modifiers = {}
        extra_note = ""

        if "tool" in tags:
            if instability_value >= 0.25:
                extra_modifiers["item_quality_shift"] = -1
                extra_modifiers["item_max_durability_bonus"] = -1
            if instability_value >= 0.55:
                extra_modifiers["item_durability_bonus"] = -1
            extra_modifiers["tool_wear_mult"] = 1.0 + (instability_value * 0.28) + (0.12 if underrepresented else 0.0)
            extra_modifiers["tamper_severity_mult"] = 1.0 + (instability_value * 0.14)
            extra_note = "the tools look rough and inconsistent"
        elif tags.intersection({"drug", "stimulant"}) or ("illegal" in tags and tags.intersection({"medical", "injectable", "social"})):
            if instability_value >= 0.24:
                extra_modifiers["item_quality_shift"] = -1
            extra_modifiers["item_positive_effect_scalar"] = max(0.8, 1.0 - (instability_value * 0.14))
            extra_modifiers["item_negative_effect_scalar"] = min(1.8, 1.0 + (instability_value * 0.26) + (pressure * 0.08))
            extra_modifiers["item_status_duration_scalar"] = 1.0 + (instability_value * 0.12)
            if instability_value >= 0.22:
                extra_modifiers["item_extra_safety_delta"] = -max(1.0, round((instability_value * 2.5) + (0.5 if pressure >= 0.5 else 0.0)))
            extra_note = "the lot feels dirty and unstable"
        elif tags.intersection({"medical", "injectable"}):
            if instability_value >= 0.35:
                extra_modifiers["item_quality_shift"] = -1
            extra_modifiers["item_positive_effect_scalar"] = max(
                0.78,
                1.0 - (instability_value * 0.18) - (0.06 if underrepresented else 0.0),
            )
            extra_modifiers["item_negative_effect_scalar"] = min(1.5, 1.0 + (instability_value * 0.16))
            extra_modifiers["item_status_duration_scalar"] = 1.0 + (instability_value * 0.08)
            if instability_value >= 0.22:
                extra_modifiers["item_extra_safety_delta"] = -max(1.0, round((instability_value * 1.5) + (0.5 if underrepresented else 0.0)))
            extra_note = "the restorative stock looks degraded"

        if not extra_modifiers:
            return bundle

        return _merged_practice_bundle(
            bundle,
            extra_modifiers=extra_modifiers,
            extra_note=extra_note or str(instability.get("note", "") or "").strip(),
            source_fields={
                "source_organization_eid": int(instability.get("organization_eid", 0) or 0) or None,
                "source_organization_key": str(instability.get("organization_key", "") or "").strip() or None,
                "source_practice_key": f"org_instability:{prop.get('id')}:{str(item_id or '').strip().lower()}",
                "instability_applied": True,
            },
        )

    def _trade_modifier_mult(self, modifiers, key, *, default=1.0, low=0.6, high=1.6):
        modifiers = modifiers if isinstance(modifiers, dict) else {}
        try:
            value = float(modifiers.get(key, default) or default)
        except (TypeError, ValueError):
            value = float(default)
        return max(float(low), min(float(high), value))

    def _trade_denial(self, eid, prop):
        return property_vigilante_denial(self.sim, prop, viewer_eid=eid)

    def _weighted_unique(self, rng, pool, count):
        entries = []
        for item_id, weight in pool:
            if item_id not in ITEM_CATALOG:
                continue
            try:
                weight = int(weight)
            except (TypeError, ValueError):
                continue
            entries.append({"item_id": item_id, "weight": max(1, weight)})

        picks = []
        while entries and len(picks) < max(0, int(count)):
            total = sum(item["weight"] for item in entries)
            pick = rng.uniform(0, total)
            running = 0.0
            choice_idx = len(entries) - 1
            for idx, item in enumerate(entries):
                running += item["weight"]
                if pick <= running:
                    choice_idx = idx
                    break
            picks.append(entries.pop(choice_idx)["item_id"])
        return picks

    def _refresh_interval_for(self, property_id):
        rng = random.Random(f"{self.sim.seed}:store_refresh:{property_id}")
        return rng.randint(140, 220)

    def _rebuild_store(self, state, prop, cycle_index):
        metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
        archetype = str(metadata.get("archetype", "")).strip().lower()
        profile = self._store_profile(archetype)
        market_profile = store_supply_profile(self.sim, prop)
        practice = self._trade_practice_bundle(prop)
        practice_modifiers = dict(practice.get("effect_modifiers", {}))
        rng = random.Random(f"{self.sim.seed}:store:{prop['id']}:cycle:{cycle_index}")
        weight_mults = _metadata_weight_mults(metadata)
        extra_supply_note = _join_notes(
            metadata.get("trade_supply_note", ""),
            metadata.get("covert_hint", ""),
            practice.get("note_text", ""),
        )
        practice_stock_mult = self._trade_modifier_mult(practice_modifiers, "trade_stock_mult", default=1.0, low=0.5, high=2.0)
        practice_buy_price_mult = self._trade_modifier_mult(practice_modifiers, "trade_buy_price_mult", default=1.0, low=0.75, high=1.4)
        practice_sell_ratio_mult = self._trade_modifier_mult(practice_modifiers, "trade_sell_ratio_mult", default=1.0, low=0.75, high=1.35)

        min_slots = int(max(1, profile.get("min_slots", 3)))
        max_slots = int(max(min_slots, profile.get("max_slots", 5)))
        slots = rng.randint(min_slots, max_slots)
        weighted_pool = []
        for item_id, weight in profile.get("item_pool", ()):
            bias = item_market_bias(item_id, market_profile)
            adjusted = float(weight) * float(bias.get("weight_mult", 1.0)) * float(weight_mults.get(item_id, 1.0))
            adjusted = int(max(1, round(adjusted)))
            weighted_pool.append((item_id, adjusted))
        item_ids = self._weighted_unique(rng, weighted_pool, slots)
        if not item_ids:
            item_ids = ["city_pass_token"]

        entries = []
        min_stock = int(max(1, profile.get("min_stock", 1)))
        max_stock = int(max(min_stock, profile.get("max_stock", 4)))
        buy_mult_lo = float(max(0.5, profile.get("buy_mult_lo", 1.0) + _metadata_float(metadata, "trade_buy_mult_lo_delta", 0.0)))
        buy_mult_hi = float(max(buy_mult_lo, profile.get("buy_mult_hi", 1.4) + _metadata_float(metadata, "trade_buy_mult_hi_delta", 0.0)))
        sell_ratio = float(max(0.1, min(0.9, profile.get("sell_ratio", 0.45) + _metadata_float(metadata, "trade_sell_ratio_delta", 0.0))))
        unlisted_sell_ratio = float(
            max(
                0.1,
                min(
                    0.85,
                    profile.get("unlisted_sell_ratio", 0.3) + _metadata_float(metadata, "trade_unlisted_sell_ratio_delta", 0.0),
                ),
            )
        )
        trade_stock_mult = max(0.25, _metadata_float(metadata, "trade_stock_mult", 1.0) * practice_stock_mult)
        markup_profile = _player_business_markup_profile(prop)
        markup_mult = max(0.5, float(markup_profile.get("buy_mult", 1.0) or 1.0))
        buy_mult_lo = max(0.5, buy_mult_lo * markup_mult * practice_buy_price_mult)
        buy_mult_hi = max(buy_mult_lo, buy_mult_hi * markup_mult * practice_buy_price_mult)
        sell_ratio = max(0.1, min(0.9, sell_ratio * practice_sell_ratio_mult))
        unlisted_sell_ratio = max(0.1, min(0.85, unlisted_sell_ratio * practice_sell_ratio_mult))

        for item_id in item_ids:
            item_def = ITEM_CATALOG.get(item_id)
            if not item_def:
                continue
            seed_token = f"{self.sim.seed}:{prop['id']}:{cycle_index}:{len(entries)}"
            if item_id == TATTOO_SERVICE_ITEM_ID:
                entry_metadata = tattoo_service_metadata(seed_token=seed_token, prop=prop)
            elif is_appearance_item(item_id, item_catalog=ITEM_CATALOG):
                entry_metadata = cosmetic_variant_metadata(
                    item_id,
                    seed_token=seed_token,
                    item_catalog=ITEM_CATALOG,
                )
            else:
                entry_metadata = {}
            bias = item_market_bias(item_id, market_profile)
            base = int(max(1, self.ITEM_BASE_VALUES.get(item_id, 10)))
            buy_price = max(
                1,
                int(round(base * rng.uniform(buy_mult_lo, buy_mult_hi) * float(bias.get("price_mult", 1.0)))),
            )
            sell_price = max(1, int(round(buy_price * sell_ratio)))
            stock_mult = float(bias.get("stock_mult", 1.0)) * trade_stock_mult
            item_min_stock = max(1, int(round(min_stock * max(0.6, stock_mult * 0.8))))
            item_max_stock = max(item_min_stock, int(round(max_stock * stock_mult)))
            entries.append({
                "item_id": item_id,
                "metadata": entry_metadata or None,
                "stock": rng.randint(item_min_stock, item_max_stock),
                "buy_price": buy_price,
                "sell_price": sell_price,
                "sale_count": 0,
            })

        entries.sort(key=lambda row: (row["buy_price"], row["item_id"]))

        state["property_id"] = prop["id"]
        state["store_name"] = prop.get("name", prop["id"])
        state["archetype"] = archetype
        state["cycle_index"] = cycle_index
        state["buy_mult_lo"] = buy_mult_lo
        state["buy_mult_hi"] = buy_mult_hi
        state["sell_ratio"] = sell_ratio
        state["unlisted_sell_ratio"] = unlisted_sell_ratio
        state["supply_note"] = _join_notes(market_profile.get("store_note", ""), extra_supply_note)
        state["family_profile"] = str(market_profile.get("family_profile", "")).strip()
        state["pressure_note"] = str(market_profile.get("pressure_note", "")).strip()
        state["entries"] = entries
        state["last_refresh_tick"] = self.sim.tick

    def _store_state(self, prop):
        property_id = prop["id"]
        state = self.sim.stores.get(property_id)
        if not isinstance(state, dict):
            state = {
                "property_id": property_id,
                "refresh_ticks": self._refresh_interval_for(property_id),
                "cycle_index": None,
                "entries": [],
            }
            self.sim.stores[property_id] = state

        refresh_ticks = int(max(30, state.get("refresh_ticks", 180)))
        state["refresh_ticks"] = refresh_ticks
        cycle_index = self.sim.tick // refresh_ticks
        trade_ui = getattr(self.sim, "trade_ui", None)
        session_locked = bool(
            isinstance(trade_ui, dict)
            and trade_ui.get("open")
            and str(trade_ui.get("property_id", "") or "").strip() == str(property_id or "").strip()
        )

        if state.get("cycle_index") != cycle_index and not session_locked:
            self._rebuild_store(state, prop, cycle_index)

        return state

    def _entry_for_item(self, state, item_id):
        item_key = canonical_store_item_id(item_id)
        for entry in state.get("entries", []):
            if entry.get("item_id") == item_id or canonical_store_item_id(entry.get("item_id")) == item_key:
                return entry
        return None

    def _best_buy_entry(self, state, credits, terms=None):
        terms = terms or {"buy_mult": 1.0}
        candidates = [
            entry for entry in state.get("entries", [])
            if int(entry.get("stock", 0)) > 0
        ]
        if not candidates:
            return None, None

        candidates.sort(
            key=lambda row: (
                self._effective_buy_price(row.get("buy_price", 0), terms),
                row.get("item_id", ""),
            )
        )
        cheapest = candidates[0]
        for entry in candidates:
            if credits >= self._effective_buy_price(entry.get("buy_price", 0), terms):
                return entry, cheapest
        return None, cheapest

    def _sell_quote(self, item_id, state, terms=None, interest=None):
        terms = terms or {"sell_mult": 1.0}
        listed = self._entry_for_item(state, item_id)
        price_mult = 1.0
        if isinstance(interest, dict):
            try:
                price_mult = max(0.0, float(interest.get("price_mult", 1.0)))
            except (TypeError, ValueError):
                price_mult = 1.0
        if listed:
            base_price = max(1, int(round(int(listed.get("sell_price", 1)) * price_mult)))
            return self._effective_sell_price(base_price, terms), True
        base = int(max(1, self.ITEM_BASE_VALUES.get(item_id, 10)))
        ratio = float(max(0.1, min(0.85, state.get("unlisted_sell_ratio", 0.3))))
        return self._effective_sell_price(max(1, int(round(base * ratio * price_mult))), terms), False

    def _store_accepts_vehicle_trade_in(self, store_prop):
        if not isinstance(store_prop, dict):
            return False
        services = set(_site_services_for_property(store_prop))
        return "vehicle_sales_new" in services or "vehicle_sales_used" in services

    def _credential_sell_action(self, entry, store_prop, *, owner_transfer=False):
        item_id = str((entry or {}).get("item_id", "") or "").strip().lower()
        if item_id in {PROPERTY_STAFF_BADGE_ITEM_ID, PROPERTY_MANAGER_BADGE_ITEM_ID}:
            return None
        if item_id != PROPERTY_KEY_ITEM_ID:
            return ""
        if owner_transfer or not self._store_accepts_vehicle_trade_in(store_prop):
            return None

        metadata = entry.get("metadata") if isinstance(entry.get("metadata"), dict) else {}
        property_id = str(metadata.get("property_id", "") or "").strip()
        vehicle_prop = self.sim.properties.get(property_id) if property_id else None
        if not _property_is_vehicle(vehicle_prop):
            return None
        return "trade-in"

    def _vehicle_trade_in_quote(self, vehicle_prop):
        metadata = _property_metadata(vehicle_prop)
        quality = str(metadata.get("vehicle_quality", "used") or "used").strip().lower() or "used"
        purchase_cost = int(max(80, _int_or_default(metadata.get("purchase_cost"), 500)))
        ratio = float(self.VEHICLE_TRADE_IN_VALUE_BY_QUALITY.get(quality, self.VEHICLE_TRADE_IN_VALUE_BY_QUALITY["used"]))

        durability = max(0, min(10, _int_or_default(metadata.get("durability"), 5)))
        fuel_efficiency = max(1, min(10, _int_or_default(metadata.get("fuel_efficiency"), 5)))
        condition_mult = 0.78 + (float(durability) * 0.03) + (float(fuel_efficiency) * 0.015)

        fuel, fuel_capacity = _vehicle_fuel_values(vehicle_prop)
        fuel_ratio = (float(fuel) / float(fuel_capacity)) if fuel_capacity > 0 else 0.0
        fuel_bonus = max(0.0, min(0.08, fuel_ratio * 0.06))

        payout = int(round(float(purchase_cost) * max(0.25, (ratio * condition_mult) + fuel_bonus)))
        return max(40, min(purchase_cost, payout))

    def _trade_in_vehicle_from_key(self, eid, store_prop, key_entry, terms=None):
        key_meta = key_entry.get("metadata") if isinstance(key_entry.get("metadata"), dict) else {}
        vehicle_id = str(key_meta.get("property_id", "") or "").strip()
        if not vehicle_id:
            self.sim.emit(Event("trade_sell_blocked", eid=eid, reason="invalid_vehicle_key"))
            return False

        vehicle_prop = self.sim.properties.get(vehicle_id)
        if not _property_is_vehicle(vehicle_prop):
            self.sim.emit(Event("trade_sell_blocked", eid=eid, reason="vehicle_not_found", vehicle_id=vehicle_id))
            return False

        if vehicle_prop.get("owner_eid") != eid and str(vehicle_prop.get("owner_tag", "") or "").strip().lower() != "player":
            self.sim.emit(Event("trade_sell_blocked", eid=eid, reason="vehicle_not_owned", vehicle_id=vehicle_id))
            return False

        store_chunk = self.sim.chunk_coords(int(store_prop.get("x", 0)), int(store_prop.get("y", 0)))
        vehicle_chunk = self.sim.chunk_coords(int(vehicle_prop.get("x", 0)), int(vehicle_prop.get("y", 0)))
        if tuple(store_chunk) != tuple(vehicle_chunk):
            self.sim.emit(
                Event(
                    "trade_sell_blocked",
                    eid=eid,
                    reason="vehicle_not_in_chunk",
                    vehicle_id=vehicle_id,
                    vehicle_name=_vehicle_label(vehicle_prop),
                )
            )
            return False

        inventory = self._inventory_for(eid)
        assets = self._assets_for(eid)
        if not inventory or not assets:
            self.sim.emit(Event("trade_sell_blocked", eid=eid, reason="missing_sale_state"))
            return False

        removed = inventory.remove_item(
            instance_id=key_entry.get("instance_id"),
            quantity=max(1, _int_or_default(key_entry.get("quantity"), 1)),
        )
        if not removed:
            self.sim.emit(Event("trade_sell_blocked", eid=eid, reason="remove_failed"))
            return False

        payout = int(self._vehicle_trade_in_quote(vehicle_prop))
        old_owner_eid = vehicle_prop.get("owner_eid")
        old_owner_tag = vehicle_prop.get("owner_tag")
        self.sim.assign_property_owner(vehicle_id, owner_eid=None, owner_tag="public")
        vehicle_meta = _property_metadata(vehicle_prop)
        vehicle_meta["vehicle_owner_tag"] = "public"
        current_display_color = str(vehicle_meta.get("display_color", "")).strip()
        if not current_display_color.startswith("vehicle_paint_"):
            vehicle_meta["display_color"] = "vehicle_parked"
        ensure_property_lock(vehicle_prop, locked=True)
        remove_actor_property_credentials(self.sim, eid, vehicle_prop)

        vehicle_state = self.sim.ecs.get(VehicleState).get(eid)
        if vehicle_state and str(vehicle_state.active_vehicle_id or "").strip() == vehicle_id:
            vehicle_state.set_active_vehicle(None, tick=self.sim.tick)
            vehicle_state.set_in_vehicle(False, tick=self.sim.tick)

        assets.credits = int(max(0, int(assets.credits) + payout))

        self.sim.emit(Event(
            "property_owner_changed",
            property_id=vehicle_id,
            old_owner_eid=old_owner_eid,
            old_owner_tag=old_owner_tag,
            new_owner_eid=None,
            new_owner_tag="public",
        ))

        vehicle_name = _vehicle_label(vehicle_prop)
        self.sim.emit(Event(
            "trade_sold",
            eid=eid,
            property_id=store_prop["id"],
            store_name=store_prop.get("name", store_prop["id"]),
            item_id="property_key",
            item_name=f"{vehicle_name} key",
            quantity=1,
            price=payout,
            base_price=payout,
            listed=False,
            stock_now=0,
            credits=assets.credits,
            contact_source_eid=(terms or {}).get("source_eid") if isinstance(terms, dict) else None,
            contact_note=(terms or {}).get("note", "") if isinstance(terms, dict) else "",
        ))
        return True

    def _trade_sell_candidates(self, inventory, store, terms=None, owner_transfer=False, actor_eid=None, service_eid=None):
        candidates = []
        if not inventory:
            return candidates
        store_prop = self.sim.properties.get(store.get("property_id")) if isinstance(store, dict) else None
        actor_eid = self.player_eid if actor_eid is None else actor_eid

        for entry in inventory.items:
            item_id = entry.get("item_id")
            action_label = self._credential_sell_action(
                entry,
                store_prop,
                owner_transfer=owner_transfer,
            )
            if action_label is None:
                continue
            interest = {
                "purchase_interest": "wanted",
                "interest_actual": "wanted",
                "interest_known": True,
                "interest_label": "wanted here",
                "actual_label": "wanted here",
                "row_color": "property_service",
                "price_mult": 1.0,
                "accepted": True,
                "pressure_weight": 0,
                "can_attempt": True,
            }
            if not owner_transfer and action_label != "trade-in":
                interest = classify_store_purchase_interest(
                    self.sim,
                    actor_eid,
                    store_prop,
                    store,
                    entry,
                    service_eid=service_eid,
                )
                if str(interest.get("interest_actual", "") or "").strip().lower() == INTEREST_REFUSED:
                    continue
            quote, listed = self._sell_quote(item_id, store, terms=terms, interest=interest)
            item_def = ITEM_CATALOG.get(item_id, {"name": item_id, "glyph": "*"})
            display_name = item_display_name_for_actor(self.sim, self.player_eid, entry, item_catalog=ITEM_CATALOG)
            candidates.append({
                "entry": entry,
                "instance_id": entry.get("instance_id"),
                "item_id": item_id,
                "item_name": display_name,
                "glyph": _item_display_glyph(item_def),
                "quantity": int(entry.get("quantity", 1)),
                "price": 0 if owner_transfer else int(max(1, quote)),
                "listed": bool(listed and not owner_transfer),
                "action_label": "stock" if owner_transfer else action_label,
                "purchase_interest": interest.get("purchase_interest"),
                "interest_label": interest.get("interest_label"),
                "interest_known": bool(interest.get("interest_known", True)),
                "interest_actual": interest.get("interest_actual"),
                "actual_label": interest.get("actual_label"),
                "row_color": interest.get("row_color"),
                "interest_reason": interest.get("reason", ""),
                "interest_profile_summary": interest.get("profile_summary", ""),
                "interest_price_mult": float(max(0.0, interest.get("price_mult", 1.0) or 1.0)),
                "interest_accepted": bool(interest.get("accepted", True)),
                "interest_pressure_weight": int(max(0, interest.get("pressure_weight", 0) or 0)),
            })

        if owner_transfer:
            candidates.sort(key=lambda row: (row["item_id"], row["instance_id"]))
        else:
            rank = {INTEREST_ADJACENT: 2, INTEREST_UNUSUAL: 1}
            candidates.sort(
                key=lambda row: (
                    -rank.get(str(row.get("interest_actual", "") or "").strip().lower(), 3),
                    -row["price"],
                    row["item_id"],
                    row["instance_id"],
                )
            )
        return candidates

    def _trade_buy_rows(self, store, terms=None, owner_transfer=False):
        terms = terms or {"buy_mult": 1.0}
        rows = []
        for entry in sorted(
            list(store.get("entries", [])),
            key=lambda row: (self._effective_buy_price(row.get("buy_price", 0), terms), row.get("item_id", "")),
        ):
            item_id = entry.get("item_id")
            item_def = ITEM_CATALOG.get(item_id, {"name": item_id, "glyph": "*"})
            row_entry = {
                "item_id": item_id,
                "metadata": entry.get("metadata") if isinstance(entry.get("metadata"), dict) else None,
            }
            rows.append({
                "item_id": item_id,
                "item_name": item_display_name_for_actor(self.sim, self.player_eid, row_entry, item_catalog=ITEM_CATALOG),
                "glyph": _item_display_glyph(item_def),
                "price": 0 if owner_transfer else self._effective_buy_price(entry.get("buy_price", 1), terms),
                "stock": int(max(0, entry.get("stock", 0))),
                "action_label": "withdraw" if owner_transfer else "",
            })
        return rows

    def _trade_sell_rows(self, inventory, store, terms=None, owner_transfer=False, actor_eid=None, service_eid=None):
        rows = []
        for row in self._trade_sell_candidates(
            inventory,
            store,
            terms=terms,
            owner_transfer=owner_transfer,
            actor_eid=actor_eid,
            service_eid=service_eid,
        ):
            rows.append({
                "instance_id": row["instance_id"],
                "item_id": row["item_id"],
                "item_name": row["item_name"],
                "glyph": row["glyph"],
                "quantity": row["quantity"],
                "price": row["price"],
                "listed": row["listed"],
                "action_label": row.get("action_label", ""),
                "purchase_interest": row.get("purchase_interest"),
                "interest_label": row.get("interest_label"),
                "interest_known": bool(row.get("interest_known", True)),
                "interest_actual": row.get("interest_actual"),
                "interest_actual_label": row.get("actual_label"),
                "row_color": row.get("row_color"),
                "interest_reason": row.get("interest_reason", ""),
                "interest_price_mult": float(max(0.0, row.get("interest_price_mult", 1.0) or 1.0)),
            })
        return rows

    def _refresh_trade_inspect_text(self, state):
        rows = list(state.get("rows", []))
        if not rows:
            state["inspect_text"] = "No offers."
            return

        idx = int(state.get("selected_index", 0))
        idx = max(0, min(idx, len(rows) - 1))
        state["selected_index"] = idx
        row = rows[idx]
        action_label = str(row.get("action_label", "")).strip().lower()

        if state.get("mode") == "buy":
            if action_label:
                state["inspect_text"] = _item_legend_line(
                    row.get("item_id"),
                    _trade_item_line(row, (
                        f"{row.get('item_name', row.get('item_id', 'item'))} "
                        f"{action_label} from shelf stock {int(row.get('stock', 0))}"
                    )),
                )
            else:
                interest_text = str(row.get("interest_label", "") or "").strip()
                risk_text = str(row.get("risk_label", "") or "").strip()
                extra_bits = [bit for bit in (interest_text, risk_text) if bit]
                extra_text = f"; {'; '.join(extra_bits)}" if extra_bits else ""
                state["inspect_text"] = _item_legend_line(
                    row.get("item_id"),
                    _trade_item_line(row, (
                        f"{row.get('item_name', row.get('item_id', 'item'))} "
                        f"{int(row.get('price', 0))} credits stock {int(row.get('stock', 0))}"
                        f"{extra_text}"
                    )),
                )
            return

        if action_label:
            if action_label == "trade-in":
                state["inspect_text"] = _item_legend_line(
                    row.get("item_id"),
                    _trade_item_line(row, (
                        f"{row.get('item_name', row.get('item_id', 'item'))} "
                        f"trade-in quote {int(row.get('price', 0))} credits "
                        f"qty {int(row.get('quantity', 0))}"
                    )),
                )
            else:
                state["inspect_text"] = _item_legend_line(
                    row.get("item_id"),
                    _trade_item_line(row, (
                        f"{row.get('item_name', row.get('item_id', 'item'))} "
                        f"{action_label} into shelf stock qty {int(row.get('quantity', 0))}"
                    )),
                )
            return
        listed_text = "listed" if row.get("listed") else "unlisted"
        interest_text = str(row.get("interest_label", "") or "").strip()
        read_text = ""
        if interest_text:
            read_text = f"; {interest_text}"
            if not bool(row.get("interest_known", True)):
                read_text += " (your read)"
        state["inspect_text"] = _item_legend_line(
            row.get("item_id"),
            _trade_item_line(row, (
                f"{row.get('item_name', row.get('item_id', 'item'))} "
                f"offer {int(row.get('price', 0))} credits ({listed_text}) "
                f"qty {int(row.get('quantity', 0))}{read_text}"
            )),
        )

    def _contact_trade_available(self, contact_eid):
        if contact_eid is None:
            return False
        player_pos = self._position_for(self.player_eid)
        contact_pos = self._position_for(contact_eid)
        if player_pos is None or contact_pos is None:
            return False
        if int(player_pos.z) != int(contact_pos.z):
            return False
        return abs(int(player_pos.x) - int(contact_pos.x)) + abs(int(player_pos.y) - int(contact_pos.y)) <= 3

    def _reset_trade_ui_closed(self, *, blocked_reason=None, emit_toggle=False):
        state = self._trade_ui_state()
        was_open = bool(state.get("open"))
        state["open"] = False
        state["rows"] = []
        state["selected_index"] = 0
        state["inspect_text"] = ""
        state["store_name"] = ""
        state["property_id"] = None
        state["supply_note"] = ""
        state["contact_note"] = ""
        state["service_note"] = ""
        state["service_eid"] = None
        state["owner_transfer"] = False
        state["source_kind"] = "storefront"
        state["contact_eid"] = None
        state["available_modes"] = ("buy", "sell")
        state["vendor_kind"] = ""
        state["street_context"] = {}
        if emit_toggle and was_open:
            self.sim.emit(Event("trade_panel_toggled", eid=self.player_eid, open=False))
        if blocked_reason:
            self.sim.emit(Event("trade_panel_blocked", eid=self.player_eid, reason=str(blocked_reason)))
        return False

    def _street_vendor_profile(self, contact_eid, *, context=None):
        return street_vendor_contact_profile(self.sim, contact_eid, self.player_eid, context=context)

    def _refresh_street_vendor_trade_ui(
        self,
        mode=None,
        keep_selection=True,
        preferred_item_id=None,
        preferred_instance_id=None,
        contact_eid=None,
        profile_context=None,
        emit_toggle=False,
    ):
        state = self._trade_ui_state()
        if contact_eid is None:
            contact_eid = state.get("contact_eid")
        if contact_eid is None or not self._contact_trade_available(contact_eid):
            return self._reset_trade_ui_closed(blocked_reason="no_street_vendor", emit_toggle=emit_toggle)

        if profile_context is None:
            profile_context = state.get("street_context")
        if not isinstance(profile_context, dict):
            profile_context = {}

        profile = self._street_vendor_profile(contact_eid, context=profile_context)
        if profile.get("blocked_reason"):
            return self._reset_trade_ui_closed(blocked_reason=profile.get("blocked_reason"), emit_toggle=emit_toggle)
        ensure_street_vendor_stock(self.sim, contact_eid, self.player_eid, profile=profile)
        profile = self._street_vendor_profile(contact_eid, context=profile_context)
        if profile.get("blocked_reason"):
            return self._reset_trade_ui_closed(blocked_reason=profile.get("blocked_reason"), emit_toggle=emit_toggle)
        available_modes = tuple(
            str(value).strip().lower()
            for value in tuple(profile.get("available_modes", ()) or ())
            if str(value).strip()
        )
        if not available_modes:
            return self._reset_trade_ui_closed(blocked_reason="street_vendor_no_trade", emit_toggle=emit_toggle)

        wanted_mode = str(mode or state.get("mode") or profile.get("default_mode", "sell")).strip().lower()
        if wanted_mode not in available_modes:
            wanted_mode = str(profile.get("default_mode", "") or "").strip().lower()
        if wanted_mode not in available_modes:
            wanted_mode = available_modes[0]

        rows = (
            street_vendor_buy_rows(self.sim, contact_eid, self.player_eid, profile=profile)
            if wanted_mode == "buy"
            else street_vendor_sell_rows(self.sim, contact_eid, self.player_eid, profile=profile)
        )
        if not rows and len(available_modes) > 1:
            alternate = "buy" if wanted_mode == "sell" else "sell"
            if alternate in available_modes:
                wanted_mode = alternate
                rows = (
                    street_vendor_buy_rows(self.sim, contact_eid, self.player_eid, profile=profile)
                    if wanted_mode == "buy"
                    else street_vendor_sell_rows(self.sim, contact_eid, self.player_eid, profile=profile)
                )

        prev_index = int(state.get("selected_index", 0))
        selected_index = 0
        if rows:
            if wanted_mode == "buy" and preferred_item_id:
                for idx, row in enumerate(rows):
                    if row.get("item_id") == preferred_item_id:
                        selected_index = idx
                        break
                else:
                    selected_index = prev_index if keep_selection else 0
            elif wanted_mode == "sell" and preferred_instance_id:
                for idx, row in enumerate(rows):
                    if row.get("instance_id") == preferred_instance_id:
                        selected_index = idx
                        break
                else:
                    selected_index = prev_index if keep_selection else 0
            else:
                selected_index = prev_index if keep_selection else 0
            selected_index = max(0, min(selected_index, len(rows) - 1))

        state["open"] = True
        state["mode"] = wanted_mode
        state["rows"] = rows
        state["selected_index"] = selected_index
        state["store_name"] = f"Street Trade: {profile.get('contact_name', 'contact')}"
        state["property_id"] = None
        state["supply_note"] = str(profile.get("stock_note" if wanted_mode == "buy" else "sell_note", "") or "").strip()
        state["contact_note"] = str(profile.get("contact_note", "") or "").strip()
        state["service_note"] = ""
        state["service_eid"] = contact_eid
        state["owner_transfer"] = False
        state["source_kind"] = STREET_TRADE_SOURCE_KIND
        state["contact_eid"] = contact_eid
        state["available_modes"] = available_modes
        state["vendor_kind"] = str(profile.get("vendor_kind", "") or "").strip().lower()
        state["street_context"] = dict(profile_context)
        self._refresh_trade_inspect_text(state)

        if emit_toggle:
            self.sim.emit(Event(
                "trade_panel_toggled",
                eid=self.player_eid,
                open=True,
                mode=wanted_mode,
                source_kind=STREET_TRADE_SOURCE_KIND,
                contact_eid=contact_eid,
                store_name=state["store_name"],
                supply_note=state.get("supply_note", ""),
                contact_note=state.get("contact_note", ""),
                service_note=state.get("service_note", ""),
                service_eid=state.get("service_eid"),
                rows=len(rows),
            ))
        return True

    def _street_deal_observation_payload(self, buyer_eid, seller_eid):
        pos = self._position_for(buyer_eid) or self._position_for(seller_eid)
        if pos is None:
            return {}
        payload = observation_payload_for_position(
            self.sim,
            pos.x,
            pos.y,
            pos.z,
            exclude_eid=buyer_eid,
            offender_eid=buyer_eid,
            observation_channels=("actor_witness",),
        )
        filtered = {}
        seller_id = None
        try:
            seller_id = int(seller_eid) if seller_eid is not None else None
        except (TypeError, ValueError):
            seller_id = None
        for key in ("observer_eids", "accountable_observer_eids", "witnesses"):
            values = []
            for raw in tuple(payload.get(key, ()) or ()):
                try:
                    eid = int(raw)
                except (TypeError, ValueError):
                    continue
                if seller_id is not None and eid == seller_id:
                    continue
                values.append(eid)
            filtered[key] = tuple(values)
        filtered["observer_count"] = len(filtered.get("observer_eids", ()))
        filtered["accountable_observer_count"] = len(filtered.get("accountable_observer_eids", ()))
        filtered["witness_count"] = len(filtered.get("accountable_observer_eids", ()))
        filtered["witnessed"] = bool(filtered.get("accountable_observer_eids"))
        filtered["observation_channels"] = tuple(payload.get("observation_channels", ()) or ("actor_witness",))
        return filtered

    def _refresh_trade_ui(
        self,
        mode=None,
        keep_selection=True,
        preferred_item_id=None,
        preferred_instance_id=None,
        contact_eid=None,
        target_property_id=None,
        emit_toggle=False,
        automated_only=False,
    ):
        state = self._trade_ui_state()
        if (
            str(state.get("source_kind", "storefront") or "storefront").strip().lower() == STREET_TRADE_SOURCE_KIND
            and contact_eid is None
        ):
            return self._refresh_street_vendor_trade_ui(
                mode=mode,
                keep_selection=keep_selection,
                preferred_item_id=preferred_item_id,
                preferred_instance_id=preferred_instance_id,
                contact_eid=state.get("contact_eid"),
                profile_context=state.get("street_context"),
                emit_toggle=emit_toggle,
            )
        if mode in {"buy", "sell"}:
            state["mode"] = mode

        pos = self._position_for(self.player_eid)
        if not pos:
            return False

        preferred_property_id = target_property_id or state.get("property_id")
        store_prop, service = self._resolve_store(
            pos,
            preferred_property_id=preferred_property_id,
            radius=2,
            automated_only=automated_only,
        )
        if not store_prop:
            was_open = bool(state.get("open"))
            state["open"] = False
            state["rows"] = []
            state["selected_index"] = 0
            state["inspect_text"] = ""
            state["store_name"] = ""
            state["property_id"] = None
            state["supply_note"] = ""
            state["contact_note"] = ""
            state["service_note"] = ""
            state["service_eid"] = None
            state["owner_transfer"] = False
            if emit_toggle and was_open:
                self.sim.emit(Event("trade_panel_toggled", eid=self.player_eid, open=False))
            blocked_reason = "no_machine_store" if automated_only else "no_store"
            self.sim.emit(Event("trade_panel_blocked", eid=self.player_eid, reason=blocked_reason))
            return False
        retain_open_session = bool(
            bool(state.get("open"))
            and isinstance(store_prop, dict)
            and str(state.get("property_id", "") or "").strip()
            and str(store_prop.get("id", "") or "").strip() == str(state.get("property_id", "") or "").strip()
        )
        if (not service or not service.get("available")) and not retain_open_session:
            was_open = bool(state.get("open"))
            state["open"] = False
            state["rows"] = []
            state["selected_index"] = 0
            state["inspect_text"] = ""
            state["store_name"] = ""
            state["property_id"] = None
            state["supply_note"] = ""
            state["contact_note"] = ""
            state["service_note"] = ""
            state["service_eid"] = None
            state["owner_transfer"] = False
            if emit_toggle and was_open:
                self.sim.emit(Event("trade_panel_toggled", eid=self.player_eid, open=False))
            self.sim.emit(
                Event(
                    "trade_panel_blocked",
                    eid=self.player_eid,
                    reason=str(service.get("blocked_reason", "no_store") or "no_store"),
                    property_id=store_prop.get("id"),
                )
            )
            return False

        denial = self._trade_denial(self.player_eid, store_prop)
        if denial is not None:
            was_open = bool(state.get("open"))
            state["open"] = False
            state["rows"] = []
            state["selected_index"] = 0
            state["inspect_text"] = ""
            state["store_name"] = ""
            state["property_id"] = None
            state["supply_note"] = ""
            state["contact_note"] = ""
            state["service_note"] = ""
            state["service_eid"] = None
            state["owner_transfer"] = False
            if emit_toggle and was_open:
                self.sim.emit(Event("trade_panel_toggled", eid=self.player_eid, open=False))
            self.sim.emit(Event(
                "trade_panel_blocked",
                eid=self.player_eid,
                reason="organization_denial",
                property_id=store_prop.get("id"),
                organization_key=denial.get("root_organization_key") or denial.get("organization_key"),
                organization_name=denial.get("root_organization_name") or denial.get("organization_name"),
            ))
            return False

        store = self._store_state(store_prop)
        inventory = self._inventory_for(self.player_eid)
        terms = self._trade_terms(self.player_eid, store_prop)
        mode = state.get("mode", "buy")
        owner_transfer = self._owner_transfer_enabled(self.player_eid, store_prop)
        rows = (
            self._trade_buy_rows(store, terms=terms, owner_transfer=owner_transfer)
            if mode == "buy"
            else self._trade_sell_rows(
                inventory,
                store,
                terms=terms,
                owner_transfer=owner_transfer,
                actor_eid=self.player_eid,
                service_eid=service.get("service_eid") if isinstance(service, dict) else None,
            )
        )

        prev_index = int(state.get("selected_index", 0))
        selected_index = 0
        if rows:
            if mode == "buy" and preferred_item_id:
                for idx, row in enumerate(rows):
                    if row.get("item_id") == preferred_item_id:
                        selected_index = idx
                        break
                else:
                    selected_index = prev_index if keep_selection else 0
            elif mode == "sell" and preferred_instance_id:
                for idx, row in enumerate(rows):
                    if row.get("instance_id") == preferred_instance_id:
                        selected_index = idx
                        break
                else:
                    selected_index = prev_index if keep_selection else 0
            else:
                selected_index = prev_index if keep_selection else 0
            selected_index = max(0, min(selected_index, len(rows) - 1))

        state["open"] = True
        state["mode"] = mode
        state["rows"] = rows
        state["selected_index"] = selected_index
        state["store_name"] = store_prop.get("name", store_prop["id"])
        state["property_id"] = store_prop["id"]
        state["supply_note"] = str(store.get("supply_note", "")).strip()
        state["contact_note"] = str(terms.get("note", "")).strip()
        state["service_note"] = str(service.get("service_note", "")).strip() if isinstance(service, dict) else ""
        state["service_eid"] = service.get("service_eid") if isinstance(service, dict) else None
        state["owner_transfer"] = bool(owner_transfer)
        self._refresh_trade_inspect_text(state)

        if emit_toggle:
            self.sim.emit(Event(
                "trade_panel_toggled",
                eid=self.player_eid,
                open=True,
                mode=mode,
                property_id=store_prop["id"],
                store_name=state["store_name"],
                supply_note=state.get("supply_note", ""),
                contact_note=state.get("contact_note", ""),
                service_note=state.get("service_note", ""),
                service_eid=state.get("service_eid"),
                rows=len(rows),
            ))
        return True

    def _close_trade_ui(self):
        state = self._trade_ui_state()
        was_open = bool(state.get("open"))
        state["open"] = False
        state["rows"] = []
        state["selected_index"] = 0
        state["inspect_text"] = ""
        state["store_name"] = ""
        state["property_id"] = None
        state["supply_note"] = ""
        state["contact_note"] = ""
        state["service_note"] = ""
        state["service_eid"] = None
        state["owner_transfer"] = False
        state["source_kind"] = "storefront"
        state["contact_eid"] = None
        state["available_modes"] = ("buy", "sell")
        state["vendor_kind"] = ""
        if was_open:
            self.sim.emit(Event("trade_panel_toggled", eid=self.player_eid, open=False))

    def npc_buy_item(self, eid, property_id, item_id, *, motive="", quirk_id="", impulse=False):
        """Buy one real store-stock item for an NPC using carried credstick credits."""
        inventory = self._inventory_for(eid)
        pos = self._position_for(eid)
        if inventory is None:
            self.sim.emit(Event("trade_buy_blocked", eid=eid, reason="no_inventory"))
            return None
        if pos is None:
            self.sim.emit(Event("trade_buy_blocked", eid=eid, reason="no_position"))
            return None
        try:
            actor_eid = int(eid)
        except (TypeError, ValueError):
            return None
        item_id = str(item_id or "").strip().lower()
        store_prop = self._storefront_by_id(property_id)
        if not store_prop:
            self.sim.emit(Event("trade_buy_blocked", eid=actor_eid, reason="no_store", property_id=property_id))
            return None
        focus = _property_focus_position(store_prop)
        if focus is None or int(focus[2]) != int(pos.z):
            self.sim.emit(Event("trade_buy_blocked", eid=actor_eid, reason="no_store", property_id=store_prop.get("id")))
            return None
        distance = abs(int(pos.x) - int(focus[0])) + abs(int(pos.y) - int(focus[1]))
        covered = _property_covering(self.sim, pos.x, pos.y, pos.z)
        inside_store = isinstance(covered, dict) and str(covered.get("id", "") or "").strip() == str(store_prop.get("id", "") or "").strip()
        if distance > 2 and not inside_store:
            self.sim.emit(Event("trade_buy_blocked", eid=actor_eid, reason="no_store", property_id=store_prop.get("id")))
            return None
        accessible, _service = self._npc_store_accessible(actor_eid, store_prop, x=pos.x, y=pos.y, z=pos.z)
        if not accessible:
            self.sim.emit(Event("trade_buy_blocked", eid=actor_eid, reason="service_unavailable", property_id=store_prop.get("id")))
            return None

        store = self._store_state(store_prop)
        choice = self._entry_for_item(store, item_id)
        if choice is None or int(choice.get("stock", 0) or 0) <= 0:
            self.sim.emit(Event(
                "trade_buy_blocked",
                eid=actor_eid,
                reason="item_unavailable",
                item_id=item_id,
                property_id=store_prop.get("id"),
            ))
            return None
        if item_id == TATTOO_SERVICE_ITEM_ID:
            self.sim.emit(Event(
                "trade_buy_blocked",
                eid=actor_eid,
                reason="npc_service_stock_skipped",
                item_id=item_id,
                property_id=store_prop.get("id"),
            ))
            return None

        terms = self._trade_terms(actor_eid, store_prop)
        base_price = int(max(1, choice.get("buy_price", 1)))
        price = self._effective_buy_price(base_price, terms)
        wallet_before = inventory_liquid_credits(inventory)
        if wallet_before < price:
            self.sim.emit(Event(
                "trade_buy_blocked",
                eid=actor_eid,
                reason="insufficient_funds",
                credits=wallet_before,
                cheapest_price=price,
                property_id=store_prop.get("id"),
            ))
            return None

        item_def = ITEM_CATALOG.get(item_id, {"name": item_id, "stack_max": 1})
        item_practice = self._item_realization_bundle(store_prop, item_id)
        source_row = next(iter(item_practice.get("rows", ())), None)
        source_organization_eid = (source_row or {}).get("organization_eid")
        source_organization_key = (source_row or {}).get("organization_key")
        source_practice_key = (source_row or {}).get("entry_key")
        if source_organization_eid in (None, 0, "0") and item_practice.get("source_organization_eid"):
            source_organization_eid = item_practice.get("source_organization_eid")
        if not str(source_organization_key or "").strip() and item_practice.get("source_organization_key"):
            source_organization_key = item_practice.get("source_organization_key")
        if not str(source_practice_key or "").strip() and item_practice.get("source_practice_key"):
            source_practice_key = item_practice.get("source_practice_key")
        next_sale_count = int(choice.get("sale_count", 0) or 0) + 1
        base_metadata = dict(choice.get("metadata") or {}) if isinstance(choice.get("metadata"), dict) else {}
        base_metadata.update({
            "purchased_from": store_prop["id"],
            "store_cycle": store.get("cycle_index"),
        })
        item_metadata = realize_item_instance_metadata(
            item_id,
            base_metadata,
            practice_bundle=item_practice,
            source_property_id=store_prop["id"],
            source_organization_eid=source_organization_eid,
            source_organization_key=source_organization_key,
            source_practice_key=source_practice_key,
            serial_seed=f"{store_prop['id']}:{store.get('cycle_index')}:{item_id}:{next_sale_count}",
        )
        item_metadata = stamp_item_provenance(
            self.sim,
            {
                "item_id": item_id,
                "owner_eid": store_prop.get("owner_eid"),
                "owner_tag": store_prop.get("owner_tag"),
                "metadata": item_metadata,
            },
            prop=store_prop,
            source_context="trade_purchase",
            claim_class=CLAIM_MERCHANDISE,
            source_owner_eid=store_prop.get("owner_eid"),
            source_owner_tag=store_prop.get("owner_tag"),
            source_property_id=store_prop.get("id"),
            source_organization_eid=source_organization_eid,
            latent_claim_violation=False,
            last_transfer_tick=int(getattr(self.sim, "tick", 0)),
            last_transfer_kind="trade_purchase",
            last_holder_eid=actor_eid,
        )
        added, instance_id = inventory.add_item(
            item_id=item_id,
            quantity=1,
            stack_max=item_def.get("stack_max", 1),
            instance_factory=self.sim.new_item_instance_id,
            owner_eid=actor_eid,
            owner_tag="npc",
            metadata=item_metadata,
        )
        if not added:
            self.sim.emit(Event(
                "trade_buy_blocked",
                eid=actor_eid,
                reason="inventory_full",
                item_id=item_id,
                property_id=store_prop["id"],
            ))
            return None

        spent = spend_npc_wallet_credits(inventory, price)
        if spent < price:
            inventory.remove_item(instance_id=instance_id, quantity=1)
            self.sim.emit(Event(
                "trade_buy_blocked",
                eid=actor_eid,
                reason="insufficient_funds",
                credits=inventory_liquid_credits(inventory),
                cheapest_price=price,
                property_id=store_prop.get("id"),
            ))
            return None
        wallet_after = inventory_liquid_credits(inventory)
        choice["stock"] = max(0, int(choice.get("stock", 0)) - 1)
        choice["sale_count"] = next_sale_count
        item_name = item_display_name_for_actor(
            self.sim,
            self.player_eid,
            {"item_id": item_id, "metadata": item_metadata, "instance_id": instance_id},
            item_catalog=ITEM_CATALOG,
        )
        sale_result = _player_business_record_direct_sale(
            self.sim,
            store_prop,
            price,
            buyer_eid=actor_eid,
            item_id=item_id,
            item_name=item_name,
        )

        self.sim.emit(Event(
            "trade_bought",
            eid=actor_eid,
            property_id=store_prop["id"],
            store_name=store_prop.get("name", store_prop["id"]),
            item_id=item_id,
            item_name=item_name,
            price=price,
            base_price=base_price,
            stock_left=choice["stock"],
            credits=wallet_after,
            instance_id=instance_id,
            owner_transfer=False,
            transfer_mode="",
            contact_source_eid=terms.get("source_eid"),
            contact_note=terms.get("note", ""),
            practice_note=item_practice.get("note_text", ""),
        ))
        result = {
            "npc_eid": actor_eid,
            "eid": actor_eid,
            "property_id": store_prop["id"],
            "store_name": store_prop.get("name", store_prop["id"]),
            "property_name": store_prop.get("name", store_prop["id"]),
            "item_id": item_id,
            "item_name": item_name,
            "price": int(price),
            "base_price": int(base_price),
            "wallet_before": int(wallet_before),
            "wallet_after": int(wallet_after),
            "stock_left": int(choice["stock"]),
            "instance_id": instance_id,
            "motive": str(motive or "").strip().lower(),
            "quirk_id": str(quirk_id or "").strip().lower(),
            "impulse": bool(impulse),
            "player_business_sale": bool(isinstance(sale_result, dict)),
            "x": int(pos.x),
            "y": int(pos.y),
            "z": int(pos.z),
        }
        self.sim.emit(Event("npc_item_purchased", **result))
        return result

    def _emit_removed_gear_events(self, eid, gear_changes, *, reason):
        if gear_changes.get("armor_name"):
            self.sim.emit(Event(
                "armor_removed",
                eid=eid,
                item_id=gear_changes.get("armor_item_id"),
                armor_name=gear_changes["armor_name"],
                reason=reason,
            ))
        if gear_changes.get("weapon_id"):
            self.sim.emit(Event(
                "weapon_removed",
                eid=eid,
                weapon_id=gear_changes["weapon_id"],
                weapon_name=gear_changes["weapon_name"],
                reason=reason,
            ))
        if gear_changes.get("disguise_name"):
            self.sim.emit(Event(
                "disguise_removed",
                eid=eid,
                item_id=gear_changes.get("disguise_item_id"),
                item_name=gear_changes["disguise_name"],
                reason=reason,
            ))
        if gear_changes.get("container_name"):
            self.sim.emit(Event(
                "container_removed",
                eid=eid,
                item_id=gear_changes.get("container_item_id"),
                item_name=gear_changes["container_name"],
                reason=reason,
            ))

    def _street_vendor_buy(self, eid, target_instance_id=None, target_item_id=None):
        assets = self._assets_for(eid)
        player_inventory = self._inventory_for(eid)
        if not assets:
            self.sim.emit(Event("trade_buy_blocked", eid=eid, reason="no_assets"))
            return False
        if not player_inventory:
            self.sim.emit(Event("trade_buy_blocked", eid=eid, reason="no_inventory"))
            return False
        state = self._trade_ui_state()
        contact_eid = state.get("contact_eid")
        if contact_eid is None or not self._contact_trade_available(contact_eid):
            self.sim.emit(Event("trade_buy_blocked", eid=eid, reason="no_street_vendor"))
            return False
        contact_inventory = self._inventory_for(contact_eid)
        if not contact_inventory:
            self.sim.emit(Event("trade_buy_blocked", eid=eid, reason="street_vendor_empty"))
            return False
        profile = self._street_vendor_profile(contact_eid, context=state.get("street_context"))
        rows = street_vendor_buy_rows(self.sim, contact_eid, eid, profile=profile)
        choice = None
        for row in rows:
            if target_instance_id and row.get("instance_id") == target_instance_id:
                choice = row
                break
            if not target_instance_id and target_item_id and row.get("item_id") == target_item_id:
                choice = row
                break
        if choice is None and not target_instance_id and not target_item_id:
            choice = rows[0] if rows else None
        if choice is None:
            self.sim.emit(Event("trade_buy_blocked", eid=eid, reason="item_unavailable", item_id=target_item_id))
            return False

        price = int(max(1, choice.get("price", 1) or 1))
        if assets.credits < price:
            self.sim.emit(Event(
                "trade_buy_blocked",
                eid=eid,
                reason="insufficient_funds",
                credits=assets.credits,
                cheapest_price=price,
                item_id=choice.get("item_id"),
            ))
            return False

        removed = contact_inventory.remove_item(instance_id=choice.get("instance_id"), quantity=1)
        if not removed:
            self.sim.emit(Event("trade_buy_blocked", eid=eid, reason="item_unavailable", item_id=choice.get("item_id")))
            return False

        item_id = str(removed.get("item_id", "") or "").strip().lower()
        item_def = ITEM_CATALOG.get(item_id, {"stack_max": 1})
        metadata = dict(removed.get("metadata") or {}) if isinstance(removed.get("metadata"), dict) else {}
        metadata.update({
            "purchased_from_contact_eid": contact_eid,
            "last_transfer_tick": int(getattr(self.sim, "tick", 0)),
            "last_transfer_kind": "street_vendor_purchase",
            "last_holder_eid": eid,
        })
        added, instance_id = player_inventory.add_item(
            item_id=item_id,
            quantity=1,
            stack_max=max(1, int(item_def.get("stack_max", 1) or 1)),
            instance_factory=self.sim.new_item_instance_id,
            owner_eid=eid,
            owner_tag="player",
            metadata=metadata,
        )
        if not added:
            contact_inventory.add_item(
                item_id=item_id,
                quantity=max(1, int(removed.get("quantity", 1) or 1)),
                stack_max=max(1, int(item_def.get("stack_max", 1) or 1)),
                instance_id=removed.get("instance_id"),
                instance_factory=self.sim.new_item_instance_id,
                owner_eid=contact_eid,
                owner_tag="npc",
                metadata=removed.get("metadata"),
            )
            self.sim.emit(Event("trade_buy_blocked", eid=eid, reason="inventory_full", item_id=item_id))
            return False

        assets.credits -= price
        item_name = item_display_name_for_actor(
            self.sim,
            self.player_eid,
            {"item_id": item_id, "metadata": metadata, "instance_id": instance_id},
            item_catalog=ITEM_CATALOG,
        )
        vendor_kind = str(state.get("vendor_kind") or profile.get("vendor_kind", "") or "").strip().lower()
        self.sim.emit(Event(
            "street_vendor_purchase",
            eid=eid,
            npc_eid=contact_eid,
            contact_eid=contact_eid,
            vendor_kind=vendor_kind,
            item_id=item_id,
            item_name=item_name,
            price=price,
            base_price=int(max(1, choice.get("base_price", price) or price)),
            stock_left=max(0, int((contact_inventory.find(instance_id=choice.get("instance_id")) or {}).get("quantity", 0) or 0)),
            credits=assets.credits,
            instance_id=instance_id,
            illegal=bool(choice.get("illegal")),
            hot=bool(choice.get("hot")),
            risk_label=str(choice.get("risk_label", "") or "").strip(),
        ))
        pusher_drug_deal = (
            vendor_kind == "drug_pusher"
            and bool(choice.get("illegal"))
            and "drug" in _item_tags(item_id)
        )
        if pusher_drug_deal:
            pos = self._position_for(eid) or self._position_for(contact_eid)
            observation = self._street_deal_observation_payload(eid, contact_eid)
            self.sim.emit(Event(
                "street_deal_transaction",
                eid=eid,
                buyer_eid=eid,
                seller_eid=contact_eid,
                npc_eid=contact_eid,
                contact_eid=contact_eid,
                vendor_kind=vendor_kind,
                item_id=item_id,
                item_name=item_name,
                price=price,
                x=getattr(pos, "x", None),
                y=getattr(pos, "y", None),
                z=getattr(pos, "z", 0) if pos is not None else 0,
                illegal=True,
                severity_score=28,
                **observation,
            ))
        elif bool(choice.get("illegal")):
            pos = self._position_for(eid)
            if pos:
                _emit_action_offense_event(
                    self.sim,
                    eid,
                    "trade_buy",
                    pos.x,
                    pos.y,
                    pos.z,
                    context="contraband_use",
                    score=16,
                )
        return True

    def _street_vendor_sell(self, eid, target_instance_id=None):
        assets = self._assets_for(eid)
        inventory = self._inventory_for(eid)
        if not assets:
            self.sim.emit(Event("trade_sell_blocked", eid=eid, reason="no_assets"))
            return False
        if not inventory:
            self.sim.emit(Event("trade_sell_blocked", eid=eid, reason="no_inventory"))
            return False
        state = self._trade_ui_state()
        contact_eid = state.get("contact_eid")
        if contact_eid is None or not self._contact_trade_available(contact_eid):
            self.sim.emit(Event("trade_sell_blocked", eid=eid, reason="no_street_vendor"))
            return False
        profile = self._street_vendor_profile(contact_eid, context=state.get("street_context"))
        rows = street_vendor_sell_rows(self.sim, contact_eid, eid, profile=profile)
        choice = None
        for row in rows:
            if target_instance_id and row.get("instance_id") == target_instance_id:
                choice = row
                break
        if choice is None and not target_instance_id:
            choice = rows[0] if rows else None
        if choice is None:
            self.sim.emit(Event("trade_sell_blocked", eid=eid, reason="no_sellable_item"))
            return False

        quantity = int(max(1, choice.get("quantity", 1) or 1))
        removed = inventory.remove_item(instance_id=choice.get("instance_id"), quantity=quantity)
        if not removed:
            self.sim.emit(Event("trade_sell_blocked", eid=eid, reason="remove_failed"))
            return False
        gear_changes = _unlink_removed_item_from_gear(self.sim, eid, removed, item_catalog=ITEM_CATALOG)
        self._emit_removed_gear_events(eid, gear_changes, reason="street_sold")

        payout = int(max(1, choice.get("price", 1) or 1))
        assets.credits += payout
        illegal_units = quantity if bool(choice.get("illegal")) else 0
        if illegal_units > 0:
            pos = self._position_for(eid)
            if pos:
                score = min(28, 10 + (illegal_units * 4) + (6 if bool(choice.get("desired")) else 0))
                _emit_action_offense_event(
                    self.sim,
                    eid,
                    "trade_sell",
                    pos.x,
                    pos.y,
                    pos.z,
                    context="contraband_use",
                    score=score,
                )

        item_id = str(removed.get("item_id", choice.get("item_id", "")) or "").strip().lower()
        self.sim.emit(Event(
            "street_buy_transaction",
            eid=eid,
            npc_eid=contact_eid,
            payout=payout,
            item_count=1,
            illegal_units=int(illegal_units),
            desired_item_id=str((profile.get("sell_terms") or {}).get("desired_item_id", "") or "").strip().lower(),
            sold_items=({
                "item_id": item_id,
                "quantity": int(max(1, removed.get("quantity", quantity) or quantity)),
            },),
            credits=int(getattr(assets, "credits", 0) or 0),
        ))
        return True

    def _trade_buy_service_stock(self, eid, store_prop, store, choice, terms, *, owner_transfer=False):
        assets = self._assets_for(eid)
        metadata = dict(choice.get("metadata") or {}) if isinstance(choice.get("metadata"), dict) else {}
        service = str(metadata.get("appearance_service", "") or "").strip().lower()
        item_id = str(choice.get("item_id", "") or "").strip().lower()
        if item_id != TATTOO_SERVICE_ITEM_ID or service != "tattoo":
            return None
        base_price = int(max(1, choice.get("buy_price", 1)))
        price = 0 if owner_transfer else self._effective_buy_price(base_price, terms)
        if not owner_transfer and assets.credits < price:
            self.sim.emit(Event(
                "trade_buy_blocked",
                eid=eid,
                reason="insufficient_funds",
                credits=assets.credits,
                cheapest_price=price,
                property_id=store_prop["id"],
            ))
            return False
        result = apply_tattoo_service(
            self.sim,
            eid,
            design=metadata.get("tattoo_design"),
            slot=metadata.get("tattoo_slot"),
            prop=store_prop,
            source_metadata=metadata,
        )
        if not bool(getattr(result, "ok", False)):
            self.sim.emit(Event(
                "trade_buy_blocked",
                eid=eid,
                reason=getattr(result, "reason", "service_blocked"),
                item_id=item_id,
                property_id=store_prop["id"],
            ))
            return False

        if not owner_transfer:
            assets.credits -= price
        next_sale_count = int(choice.get("sale_count", 0) or 0) + 1
        choice["stock"] = max(0, int(choice.get("stock", 0)) - 1)
        choice["sale_count"] = next_sale_count
        item_name = item_display_name_for_actor(
            self.sim,
            self.player_eid,
            {"item_id": item_id, "metadata": metadata},
            item_catalog=ITEM_CATALOG,
        )
        self.sim.emit(Event(
            "trade_bought",
            eid=eid,
            property_id=store_prop["id"],
            store_name=store_prop.get("name", store_prop["id"]),
            item_id=item_id,
            item_name=item_name,
            price=price,
            base_price=base_price,
            stock_left=choice["stock"],
            credits=assets.credits,
            instance_id=None,
            owner_transfer=bool(owner_transfer),
            transfer_mode="service" if not owner_transfer else "withdraw",
            contact_source_eid=terms.get("source_eid"),
            contact_note=terms.get("note", ""),
            practice_note="",
            service_stock=True,
            appearance_service=service,
            tattoo_design=metadata.get("tattoo_design"),
            tattoo_slot=metadata.get("tattoo_slot"),
        ))
        return True

    def _trade_buy(self, eid, pos, target_item_id=None):
        assets = self._assets_for(eid)
        inventory = self._inventory_for(eid)
        if not assets:
            self.sim.emit(Event("trade_buy_blocked", eid=eid, reason="no_assets"))
            return False
        if not inventory:
            self.sim.emit(Event("trade_buy_blocked", eid=eid, reason="no_inventory"))
            return False

        state = self._trade_ui_state()
        store_prop, _service = self._resolve_store(pos, preferred_property_id=state.get("property_id"), radius=2)
        if not store_prop:
            self.sim.emit(Event("trade_buy_blocked", eid=eid, reason="no_store"))
            return False
        denial = self._trade_denial(eid, store_prop)
        if denial is not None:
            self.sim.emit(Event(
                "trade_buy_blocked",
                eid=eid,
                reason="organization_denial",
                property_id=store_prop.get("id"),
                organization_key=denial.get("root_organization_key") or denial.get("organization_key"),
                organization_name=denial.get("root_organization_name") or denial.get("organization_name"),
            ))
            return False

        store = self._store_state(store_prop)
        terms = self._trade_terms(eid, store_prop)
        owner_transfer = self._owner_transfer_enabled(eid, store_prop)
        cheapest = None
        choice = None
        if target_item_id:
            choice = self._entry_for_item(store, target_item_id)
            if choice and int(choice.get("stock", 0)) <= 0:
                choice = None
            if not choice:
                self.sim.emit(Event(
                    "trade_buy_blocked",
                    eid=eid,
                    reason="item_unavailable",
                    item_id=target_item_id,
                    property_id=store_prop["id"],
                ))
                return False
            effective_price = self._effective_buy_price(choice.get("buy_price", 0), terms)
            if not owner_transfer and assets.credits < effective_price:
                self.sim.emit(Event(
                    "trade_buy_blocked",
                    eid=eid,
                    reason="insufficient_funds",
                    credits=assets.credits,
                    cheapest_price=effective_price,
                    property_id=store_prop["id"],
                ))
                return False
        else:
            choice, cheapest = self._best_buy_entry(store, assets.credits if not owner_transfer else 10**9, terms=terms)
        if not choice:
            if cheapest:
                self.sim.emit(Event(
                    "trade_buy_blocked",
                    eid=eid,
                    reason="insufficient_funds",
                    credits=assets.credits,
                    cheapest_price=self._effective_buy_price(cheapest.get("buy_price", 0), terms),
                    property_id=store_prop["id"],
                ))
            else:
                self.sim.emit(Event(
                    "trade_buy_blocked",
                    eid=eid,
                    reason="store_empty",
                    property_id=store_prop["id"],
                ))
            return False

        item_id = choice["item_id"]
        service_purchase = self._trade_buy_service_stock(
            eid,
            store_prop,
            store,
            choice,
            terms,
            owner_transfer=owner_transfer,
        )
        if service_purchase is not None:
            return bool(service_purchase)
        item_def = ITEM_CATALOG.get(item_id, {"name": item_id, "stack_max": 1})
        item_practice = self._item_realization_bundle(store_prop, item_id)
        source_row = next(iter(item_practice.get("rows", ())), None)
        source_organization_eid = (source_row or {}).get("organization_eid")
        source_organization_key = (source_row or {}).get("organization_key")
        source_practice_key = (source_row or {}).get("entry_key")
        if source_organization_eid in (None, 0, "0") and item_practice.get("source_organization_eid"):
            source_organization_eid = item_practice.get("source_organization_eid")
        if not str(source_organization_key or "").strip() and item_practice.get("source_organization_key"):
            source_organization_key = item_practice.get("source_organization_key")
        if not str(source_practice_key or "").strip() and item_practice.get("source_practice_key"):
            source_practice_key = item_practice.get("source_practice_key")
        next_sale_count = int(choice.get("sale_count", 0) or 0) + 1
        base_metadata = dict(choice.get("metadata") or {}) if isinstance(choice.get("metadata"), dict) else {}
        base_metadata.update({
            "purchased_from": store_prop["id"],
            "store_cycle": store.get("cycle_index"),
        })
        item_metadata = realize_item_instance_metadata(
            item_id,
            base_metadata,
            practice_bundle=item_practice,
            source_property_id=store_prop["id"],
            source_organization_eid=source_organization_eid,
            source_organization_key=source_organization_key,
            source_practice_key=source_practice_key,
            serial_seed=f"{store_prop['id']}:{store.get('cycle_index')}:{item_id}:{next_sale_count}",
        )
        item_metadata = stamp_item_provenance(
            self.sim,
            {
                "item_id": item_id,
                "owner_eid": store_prop.get("owner_eid"),
                "owner_tag": store_prop.get("owner_tag"),
                "metadata": item_metadata,
            },
            prop=store_prop,
            source_context="trade_purchase",
            claim_class=CLAIM_MERCHANDISE,
            source_owner_eid=store_prop.get("owner_eid"),
            source_owner_tag=store_prop.get("owner_tag"),
            source_property_id=store_prop.get("id"),
            source_organization_eid=source_organization_eid,
            latent_claim_violation=False,
            last_transfer_tick=int(getattr(self.sim, "tick", 0)),
            last_transfer_kind="trade_purchase",
            last_holder_eid=eid,
        )
        added, instance_id = inventory.add_item(
            item_id=item_id,
            quantity=1,
            stack_max=item_def.get("stack_max", 1),
            instance_factory=self.sim.new_item_instance_id,
            owner_eid=eid,
            owner_tag="player" if eid == self.player_eid else "npc",
            metadata=item_metadata,
        )
        if not added:
            self.sim.emit(Event(
                "trade_buy_blocked",
                eid=eid,
                reason="inventory_full",
                item_id=item_id,
                property_id=store_prop["id"],
            ))
            return False

        base_price = int(max(1, choice.get("buy_price", 1)))
        price = 0 if owner_transfer else self._effective_buy_price(base_price, terms)
        if not owner_transfer:
            assets.credits -= price
        choice["stock"] = max(0, int(choice.get("stock", 0)) - 1)
        choice["sale_count"] = next_sale_count

        self.sim.emit(Event(
            "trade_bought",
            eid=eid,
            property_id=store_prop["id"],
            store_name=store_prop.get("name", store_prop["id"]),
            item_id=item_id,
            item_name=item_display_name_for_actor(
                self.sim,
                self.player_eid,
                {"item_id": item_id, "metadata": item_metadata, "instance_id": instance_id},
                item_catalog=ITEM_CATALOG,
            ),
            price=price,
            base_price=base_price,
            stock_left=choice["stock"],
            credits=assets.credits,
            instance_id=instance_id,
            owner_transfer=bool(owner_transfer),
            transfer_mode="withdraw" if owner_transfer else "",
            contact_source_eid=terms.get("source_eid"),
            contact_note=terms.get("note", ""),
            practice_note=item_practice.get("note_text", ""),
        ))
        return True

    def _unwanted_sale_pressure_key(self, eid, store_prop, service=None):
        property_id = str((store_prop or {}).get("id", "") or "").strip()
        service_eid = None
        if isinstance(service, dict):
            service_eid = service.get("service_eid")
        enforcer = service_eid if service_eid is not None else (store_prop or {}).get("owner_eid")
        return f"{property_id}:{enforcer if enforcer is not None else 'counter'}:{eid}"

    def _unwanted_sale_pressure_threshold(self, eid, store_prop, service=None):
        threshold = 3
        if self._actor_owns_property(eid, store_prop):
            return 99
        service_eid = service.get("service_eid") if isinstance(service, dict) else None
        if service_eid is not None:
            social = self.sim.ecs.get(NPCSocial).get(service_eid)
            bond = social.bonds.get(eid) if social and isinstance(getattr(social, "bonds", None), dict) else None
            if isinstance(bond, dict):
                trust = _clamp_float(bond.get("trust"), 0.0, 1.0, default=0.0)
                closeness = _clamp_float(bond.get("closeness"), 0.0, 1.0, default=0.0)
                if max(trust, closeness) >= 0.72:
                    threshold += 2
                elif max(trust, closeness) >= 0.48:
                    threshold += 1
        streetwise = float(_actor_skill(self.sim, eid, "streetwise", default=5.0))
        if streetwise >= 7.5:
            threshold += 1
        return int(threshold)

    def _handle_unwanted_sale_attempt(self, eid, store_prop, service, row):
        pressure_store = getattr(self.sim, "trade_unwanted_sale_pressure", None)
        if not isinstance(pressure_store, dict):
            pressure_store = {}
            self.sim.trade_unwanted_sale_pressure = pressure_store
        key = self._unwanted_sale_pressure_key(eid, store_prop, service)
        weight = int(max(1, row.get("interest_pressure_weight", 1) or 1))
        pressure = int(max(0, pressure_store.get(key, 0))) + weight
        pressure_store[key] = pressure

        threshold = self._unwanted_sale_pressure_threshold(eid, store_prop, service)
        if pressure >= threshold:
            reason = "unwanted_item_eject"
        elif pressure >= max(2, threshold - 1):
            reason = "unwanted_item_firm"
        else:
            reason = "unwanted_item_warning"

        self.sim.emit(Event(
            "trade_sell_blocked",
            eid=eid,
            reason=reason,
            property_id=store_prop.get("id"),
            store_name=store_prop.get("name", store_prop.get("id", "store")),
            item_id=row.get("item_id"),
            item_name=row.get("item_name"),
            purchase_interest=row.get("interest_actual"),
            interest_label=row.get("actual_label") or row.get("interest_label", ""),
            pressure=pressure,
            threshold=threshold,
        ))

        if reason != "unwanted_item_eject":
            return False

        self._close_trade_ui()
        enforcer = service.get("service_eid") if isinstance(service, dict) else None
        if enforcer is None:
            enforcer = store_prop.get("owner_eid")
        if enforcer is not None:
            self.sim.emit(Event(
                "npc_boundary_violation",
                npc_eid=enforcer,
                target_eid=eid,
                property_id=store_prop.get("id"),
                context="unwanted_trade",
                source_kind="trade_refusal",
                offense_score=24 + min(12, pressure * 3),
                perceived=0.72,
                violation_count=pressure,
                violence_eligible=False,
            ))
        return False

    def _trade_sell(self, eid, pos, target_instance_id=None):
        assets = self._assets_for(eid)
        inventory = self._inventory_for(eid)
        if not assets:
            self.sim.emit(Event("trade_sell_blocked", eid=eid, reason="no_assets"))
            return False
        if not inventory:
            self.sim.emit(Event("trade_sell_blocked", eid=eid, reason="no_inventory"))
            return False
        if not inventory.items:
            self.sim.emit(Event("trade_sell_blocked", eid=eid, reason="inventory_empty"))
            return False

        state = self._trade_ui_state()
        store_prop, service = self._resolve_store(pos, preferred_property_id=state.get("property_id"), radius=2)
        if not store_prop:
            self.sim.emit(Event("trade_sell_blocked", eid=eid, reason="no_store"))
            return False
        denial = self._trade_denial(eid, store_prop)
        if denial is not None:
            self.sim.emit(Event(
                "trade_sell_blocked",
                eid=eid,
                reason="organization_denial",
                property_id=store_prop.get("id"),
                organization_key=denial.get("root_organization_key") or denial.get("organization_key"),
                organization_name=denial.get("root_organization_name") or denial.get("organization_name"),
            ))
            return False

        store = self._store_state(store_prop)
        terms = self._trade_terms(eid, store_prop)
        owner_transfer = self._owner_transfer_enabled(eid, store_prop)

        candidates = self._trade_sell_candidates(
            inventory,
            store,
            terms=terms,
            owner_transfer=owner_transfer,
            actor_eid=eid,
            service_eid=service.get("service_eid") if isinstance(service, dict) else None,
        )
        if target_instance_id:
            best = None
            for row in candidates:
                if row.get("instance_id") == target_instance_id:
                    best = row
                    break
            if not best:
                self.sim.emit(Event(
                    "trade_sell_blocked",
                    eid=eid,
                    reason="item_not_found",
                    instance_id=target_instance_id,
                    property_id=store_prop["id"],
                ))
                return False
        else:
            best = candidates[0] if candidates else None

        if not best:
            self.sim.emit(Event("trade_sell_blocked", eid=eid, reason="no_sellable_item"))
            return False

        if (
            not owner_transfer
            and str(best.get("interest_actual", "") or "").strip().lower() == INTEREST_UNUSUAL
            and not bool(best.get("interest_accepted", True))
        ):
            return self._handle_unwanted_sale_attempt(eid, store_prop, service, best)

        if (
            not owner_transfer
            and
            str(best.get("action_label", "") or "").strip().lower() == "trade-in"
            and self._store_accepts_vehicle_trade_in(store_prop)
        ):
            return self._trade_in_vehicle_from_key(
                eid,
                store_prop,
                best.get("entry") or {},
                terms=terms,
            )

        removed = inventory.remove_item(instance_id=best["instance_id"], quantity=1)
        if not removed:
            self.sim.emit(Event("trade_sell_blocked", eid=eid, reason="remove_failed"))
            return False

        gear_changes = _unlink_removed_item_from_gear(self.sim, eid, removed, item_catalog=ITEM_CATALOG)
        if gear_changes.get("armor_name"):
            self.sim.emit(Event(
                "armor_removed",
                eid=eid,
                item_id=gear_changes.get("armor_item_id"),
                armor_name=gear_changes["armor_name"],
                reason="sold",
            ))
        if gear_changes.get("weapon_id"):
            self.sim.emit(Event(
                "weapon_removed",
                eid=eid,
                weapon_id=gear_changes["weapon_id"],
                weapon_name=gear_changes["weapon_name"],
                reason="sold",
            ))
        if gear_changes.get("disguise_name"):
            self.sim.emit(Event(
                "disguise_removed",
                eid=eid,
                item_id=gear_changes.get("disguise_item_id"),
                item_name=gear_changes["disguise_name"],
                reason="sold",
            ))
        if gear_changes.get("container_name"):
            self.sim.emit(Event(
                "container_removed",
                eid=eid,
                item_id=gear_changes.get("container_item_id"),
                item_name=gear_changes["container_name"],
                reason="sold",
            ))

        item_id = removed["item_id"]
        item_def = ITEM_CATALOG.get(item_id, {"name": item_id})
        base_payout, _ = self._sell_quote(
            item_id,
            store,
            terms={"sell_mult": 1.0},
            interest={"price_mult": 1.0 if owner_transfer else best.get("interest_price_mult", 1.0)},
        )
        payout = 0 if owner_transfer else int(max(1, best["price"]))
        if not owner_transfer:
            assets.credits += payout

        existing = self._entry_for_item(store, item_id)
        if existing:
            existing["stock"] = int(existing.get("stock", 0)) + int(max(1, removed.get("quantity", 1)))
            if is_appearance_item(removed, item_catalog=ITEM_CATALOG) and not isinstance(existing.get("metadata"), dict):
                existing["metadata"] = dict(removed.get("metadata") or {})
            stock_now = existing["stock"]
        else:
            base = int(max(1, self.ITEM_BASE_VALUES.get(item_id, 10)))
            buy_mult_lo = float(store.get("buy_mult_lo", 1.0))
            buy_mult_hi = float(store.get("buy_mult_hi", 1.4))
            buy_price = max(1, int(round(base * ((buy_mult_lo + buy_mult_hi) * 0.5))))
            sell_ratio = float(max(0.1, min(0.9, store.get("sell_ratio", 0.45))))
            sell_price = max(1, int(round(buy_price * sell_ratio)))
            existing = {
                "item_id": item_id,
                "metadata": dict(removed.get("metadata") or {}) if is_appearance_item(removed, item_catalog=ITEM_CATALOG) else None,
                "stock": int(max(1, removed.get("quantity", 1))),
                "buy_price": buy_price,
                "sell_price": sell_price,
                "sale_count": 0,
            }
            store["entries"].append(existing)
            store["entries"].sort(key=lambda row: (int(row.get("buy_price", 0)), row.get("item_id", "")))
            stock_now = existing["stock"]

        self.sim.emit(Event(
            "trade_sold",
            eid=eid,
            property_id=store_prop["id"],
            store_name=store_prop.get("name", store_prop["id"]),
            item_id=item_id,
            item_name=item_display_name_for_actor(self.sim, self.player_eid, removed, item_catalog=ITEM_CATALOG),
            quantity=int(max(1, removed.get("quantity", 1) or 1)),
            price=payout,
            base_price=base_payout,
            listed=bool(best["listed"] and not owner_transfer),
            stock_now=stock_now,
            credits=assets.credits,
            owner_transfer=bool(owner_transfer),
            transfer_mode="stock" if owner_transfer else "",
            contact_source_eid=terms.get("source_eid"),
            contact_note=terms.get("note", ""),
        ))
        return True

    def on_trade_panel_open_request(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        mode = str(event.data.get("mode", "buy")).lower()
        if mode not in {"buy", "sell"}:
            mode = "buy"
        source_kind = str(event.data.get("source_kind", "storefront") or "storefront").strip().lower()
        if source_kind == STREET_TRADE_SOURCE_KIND:
            street_context = event.data.get("street_context")
            if not isinstance(street_context, dict):
                street_context = {
                    key: event.data.get(key)
                    for key in ("pressure_tier", "pressure_attention", "contact_standing", "social_standing", "rapport")
                    if key in event.data
                }
            self._refresh_street_vendor_trade_ui(
                mode=mode,
                keep_selection=False,
                contact_eid=event.data.get("contact_eid"),
                profile_context=street_context,
                emit_toggle=True,
            )
            return
        state = self._trade_ui_state()
        state["source_kind"] = "storefront"
        state["contact_eid"] = None
        automated_only = bool(event.data.get("automated_only"))
        self._refresh_trade_ui(
            mode=mode,
            keep_selection=False,
            target_property_id=event.data.get("property_id"),
            emit_toggle=True,
            automated_only=automated_only,
        )

    def on_trade_panel_close_request(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        self._close_trade_ui()

    def on_trade_panel_mode_request(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        state = self._trade_ui_state()
        if not state.get("open"):
            return
        mode = str(event.data.get("mode", state.get("mode", "buy"))).lower()
        if mode not in {"buy", "sell"}:
            return
        if str(state.get("source_kind", "storefront") or "storefront").strip().lower() == STREET_TRADE_SOURCE_KIND:
            if mode not in set(state.get("available_modes", ("buy", "sell")) or ("buy", "sell")):
                return
            self._refresh_street_vendor_trade_ui(
                mode=mode,
                keep_selection=False,
                contact_eid=state.get("contact_eid"),
                profile_context=state.get("street_context"),
            )
            return
        self._refresh_trade_ui(mode=mode, keep_selection=False)

    def on_trade_execute_request(self, event):
        if event.data.get("eid") != self.player_eid:
            return

        pos = self._position_for(self.player_eid)
        if not pos:
            return

        mode = str(event.data.get("mode", "buy")).lower()
        item_id = event.data.get("item_id")
        instance_id = event.data.get("instance_id")
        success = False
        state = self._trade_ui_state()
        if str(state.get("source_kind", "storefront") or "storefront").strip().lower() == STREET_TRADE_SOURCE_KIND:
            if mode == "buy":
                success = self._street_vendor_buy(self.player_eid, target_instance_id=instance_id, target_item_id=item_id)
                if bool(self._trade_ui_state().get("open")):
                    self._refresh_street_vendor_trade_ui(
                        mode="buy",
                        keep_selection=True,
                        preferred_item_id=item_id if success else None,
                        contact_eid=state.get("contact_eid"),
                        profile_context=state.get("street_context"),
                    )
                return
            if mode == "sell":
                success = self._street_vendor_sell(self.player_eid, target_instance_id=instance_id)
                if bool(self._trade_ui_state().get("open")):
                    self._refresh_street_vendor_trade_ui(
                        mode="sell",
                        keep_selection=True,
                        preferred_instance_id=instance_id if not success else None,
                        contact_eid=state.get("contact_eid"),
                        profile_context=state.get("street_context"),
                    )
                return
        if mode == "buy":
            success = self._trade_buy(self.player_eid, pos, target_item_id=item_id)
            self._refresh_trade_ui(
                mode="buy",
                keep_selection=True,
                preferred_item_id=item_id,
            )
            return
        if mode == "sell":
            success = self._trade_sell(self.player_eid, pos, target_instance_id=instance_id)
            if bool(self._trade_ui_state().get("open")):
                self._refresh_trade_ui(
                    mode="sell",
                    keep_selection=True,
                    preferred_instance_id=instance_id if not success else None,
                )

    def on_property_interact(self, event):
        if event.data.get("eid") != self.player_eid:
            return
        if bool(event.data.get("handled")):
            return
        interaction_mode = str(event.data.get("interaction_mode", "") or "").strip().lower()
        if interaction_mode and interaction_mode != "service":
            return

        prop = self.sim.properties.get(event.data.get("property_id"))
        if not self._is_storefront(prop):
            return
        metadata = prop.get("metadata") if isinstance(prop.get("metadata"), dict) else {}
        if bool(metadata.get("dialogue_trade_only")) and not bool(event.data.get("allow_dialogue_trade_only")):
            return
        pos = self._position_for(self.player_eid)
        if pos:
            access = _evaluate_property_access(
                self.sim,
                self.player_eid,
                prop,
                x=pos.x,
                y=pos.y,
                z=pos.z,
            )
            if not access.can_use_services:
                return

        self._refresh_trade_ui(
            mode="buy",
            keep_selection=False,
            target_property_id=prop["id"],
            emit_toggle=True,
        )

    def on_player_action(self, event):
        eid = event.data.get("eid")
        if eid != self.player_eid:
            return

        action = event.data.get("action")
        if action not in {"trade_buy", "trade_sell"}:
            return

        pos = self._position_for(eid)
        if not pos:
            return

        if action == "trade_buy":
            self._trade_buy(eid, pos)
            state = self._trade_ui_state()
            if state.get("open") and state.get("mode") == "buy":
                self._refresh_trade_ui(mode="buy", keep_selection=True)
            return

        self._trade_sell(eid, pos)
        state = self._trade_ui_state()
        if state.get("open") and state.get("mode") == "sell":
            self._refresh_trade_ui(mode="sell", keep_selection=True)
