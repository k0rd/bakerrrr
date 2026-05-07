"""Trade system extracted from ``game.systems``."""

import curses
import random

from engine.events import Event
from engine.systems import System
from game.appearance import ground_item_color as _ground_item_color, item_display_glyph as _appearance_item_display_glyph
from game.components import Inventory, PlayerAssets, Position, VehicleState
from game.economy import item_market_bias, store_supply_profile
from game.items import ITEM_CATALOG, item_display_name
from game.property_access import evaluate_property_access as _evaluate_property_access
from game.property_keys import ensure_property_lock, remove_actor_property_credentials
from game.property_runtime import (
    property_distance as _property_distance,
    property_is_storefront as _property_is_storefront,
    property_is_vehicle as _property_is_vehicle,
    property_metadata as _property_metadata,
    site_services_for_property as _site_services_for_property,
    vehicle_fuel_values as _vehicle_fuel_values,
    vehicle_label as _vehicle_label,
)
from game.service_runtime import _int_or_default, _legend_line, _storefront_service_profile
from game.system_support.container_runtime import _unlink_removed_item_from_gear


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
        "gallery",
        "flophouse",
        "street_kitchen",
        "theater",
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
        "focus_inhaler": 30,
        "synth_focus_tabs": 24,
        "smoke_tab": 13,
        "credstick_chip": 20,
        "city_pass_token": 7,
        "transit_daypass": 12,
        "meal_voucher": 11,
        "parking_stub": 3,
        "metro_flyer": 2,
        "scratch_ticket": 6,
        "pocket_notebook": 5,
        "deck_of_cards": 7,
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
        "holdout_pistol": 108,
        "service_pistol": 146,
        "rust_revolver": 132,
        "alley_shotgun": 168,
        "machine_pistol": 188,
        "compact_smg": 226,
        "patrol_carbine": 238,
        "hunting_rifle": 256,
        "improvised_launcher": 284,
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
            ("black_market_stim", 3),
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
                ("light_ammo_box", 8),
                ("city_pass_token", 26),
                ("transit_daypass", 14),
                ("meal_voucher", 12),
                ("scratch_ticket", 10),
                ("deck_of_cards", 8),
                ("mint_strip", 10),
                ("calm_patch", 14),
                ("med_gel", 9),
                ("cheap_whiskey", 10),
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
                ("shiv_knife", 12),
                ("crowbar_club", 10),
                ("telescopic_baton", 8),
                ("holdout_pistol", 14),
                ("service_pistol", 10),
                ("rust_revolver", 10),
                ("alley_shotgun", 6),
                ("machine_pistol", 8),
                ("padded_jacket", 10),
                ("courier_mesh", 10),
                ("security_vest", 8),
                ("scrap_circuit", 9),
                ("signal_jammer", 10),
                ("cloned_thumb", 6),
                ("black_market_stim", 12),
                ("light_ammo_box", 12),
                ("shell_bandolier", 8),
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
                ("calm_patch", 22),
                ("trauma_foam", 14),
                ("trauma_autoinjector", 4),
                ("field_dressing", 18),
                ("focus_inhaler", 14),
                ("caff_shot", 9),
                ("street_ration", 8),
            ),
        },
        "nightclub": {
            "buy_mult_lo": 1.02,
            "buy_mult_hi": 1.38,
            "item_pool": (
                ("spark_brew", 34),
                ("cheap_whiskey", 24),
                ("smoke_tab", 20),
                ("mint_strip", 12),
                ("deck_of_cards", 10),
                ("burner_phone", 8),
                ("caff_shot", 20),
                ("synth_focus_tabs", 10),
                ("credstick_chip", 12),
                ("black_market_stim", 10),
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
                ("black_market_stim", 8),
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
                ("bandage_roll", 10),
                ("city_pass_token", 12),
                ("street_ration", 10),
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
                ("shell_bandolier", 14),
                ("rifle_mag_crate", 10),
                ("trail_machete", 12),
                ("holdout_pistol", 10),
                ("service_pistol", 4),
                ("alley_shotgun", 8),
                ("hunting_rifle", 8),
                ("padded_jacket", 12),
                ("field_vest", 12),
                ("courier_mesh", 10),
                ("pocket_multitool", 8),
                ("bandage_roll", 10),
                ("field_dressing", 10),
                ("energy_bar", 10),
                ("bottled_water", 10),
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
                ("shell_bandolier", 18),
                ("rifle_mag_crate", 16),
                ("rocket_tube_pack", 4),
                ("trail_machete", 14),
                ("telescopic_baton", 10),
                ("holdout_pistol", 10),
                ("service_pistol", 14),
                ("rust_revolver", 12),
                ("alley_shotgun", 12),
                ("hunting_rifle", 12),
                ("patrol_carbine", 10),
                ("padded_jacket", 10),
                ("field_vest", 12),
                ("courier_mesh", 8),
                ("security_vest", 9),
                ("riot_plates", 6),
                ("ceramic_plate_rig", 4),
                ("bandage_roll", 10),
                ("field_dressing", 10),
                ("battery_pack", 8),
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
                ("battery_pack", 10),
                ("pocket_multitool", 12),
                ("scrap_circuit", 12),
                ("signal_jammer", 12),
                ("forged_badge", 10),
                ("glass_cutter", 14),
                ("hotwire_leads", 14),
                ("shiv_knife", 14),
                ("crowbar_club", 12),
                ("telescopic_baton", 10),
                ("cloned_thumb", 8),
                ("black_market_stim", 14),
                ("light_ammo_box", 12),
                ("shell_bandolier", 10),
                ("rifle_mag_crate", 9),
                ("rocket_tube_pack", 4),
                ("holdout_pistol", 16),
                ("service_pistol", 12),
                ("rust_revolver", 14),
                ("alley_shotgun", 12),
                ("machine_pistol", 10),
                ("compact_smg", 8),
                ("patrol_carbine", 7),
                ("security_vest", 10),
                ("riot_plates", 8),
                ("ceramic_plate_rig", 6),
                ("burner_phone", 10),
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
                ("burner_phone", 10),
                ("lucky_charm", 12),
                ("deck_of_cards", 10),
                ("spark_brew", 14),
                ("caff_shot", 14),
                ("black_market_stim", 6),
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
                ("black_market_stim", 8),
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
                ("black_market_stim", 7),
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
        self._trade_contact_terms = trade_contact_terms or _default_trade_contact_terms
        if not hasattr(self.sim, "stores"):
            self.sim.stores = {}
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
            }
            self.sim.trade_ui = state
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
            service = _storefront_service_profile(self.sim, prop)
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
            if _property_distance(pos.x, pos.y, preferred) <= radius:
                preferred_service = _storefront_service_profile(self.sim, preferred)
                if not automated_only or self._service_is_machine(preferred_service):
                    return preferred, preferred_service
        return self._nearest_store(pos, radius=radius, automated_only=automated_only)

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
        metadata = prop.get("metadata", {})
        archetype = str(metadata.get("archetype", "")).strip().lower()
        profile = self._store_profile(archetype)
        market_profile = store_supply_profile(self.sim, prop)
        rng = random.Random(f"{self.sim.seed}:store:{prop['id']}:cycle:{cycle_index}")

        min_slots = int(max(1, profile.get("min_slots", 3)))
        max_slots = int(max(min_slots, profile.get("max_slots", 5)))
        slots = rng.randint(min_slots, max_slots)
        weighted_pool = []
        for item_id, weight in profile.get("item_pool", ()):
            bias = item_market_bias(item_id, market_profile)
            adjusted = int(max(1, round(float(weight) * float(bias.get("weight_mult", 1.0)))))
            weighted_pool.append((item_id, adjusted))
        item_ids = self._weighted_unique(rng, weighted_pool, slots)
        if not item_ids:
            item_ids = ["city_pass_token"]

        entries = []
        min_stock = int(max(1, profile.get("min_stock", 1)))
        max_stock = int(max(min_stock, profile.get("max_stock", 4)))
        buy_mult_lo = float(max(0.5, profile.get("buy_mult_lo", 1.0)))
        buy_mult_hi = float(max(buy_mult_lo, profile.get("buy_mult_hi", 1.4)))
        sell_ratio = float(max(0.1, min(0.9, profile.get("sell_ratio", 0.45))))

        for item_id in item_ids:
            item_def = ITEM_CATALOG.get(item_id)
            if not item_def:
                continue
            bias = item_market_bias(item_id, market_profile)
            base = int(max(1, self.ITEM_BASE_VALUES.get(item_id, 10)))
            buy_price = max(
                1,
                int(round(base * rng.uniform(buy_mult_lo, buy_mult_hi) * float(bias.get("price_mult", 1.0)))),
            )
            sell_price = max(1, int(round(buy_price * sell_ratio)))
            stock_mult = float(bias.get("stock_mult", 1.0))
            item_min_stock = max(1, int(round(min_stock * max(0.6, stock_mult * 0.8))))
            item_max_stock = max(item_min_stock, int(round(max_stock * stock_mult)))
            entries.append({
                "item_id": item_id,
                "stock": rng.randint(item_min_stock, item_max_stock),
                "buy_price": buy_price,
                "sell_price": sell_price,
            })

        entries.sort(key=lambda row: (row["buy_price"], row["item_id"]))

        state["property_id"] = prop["id"]
        state["store_name"] = prop.get("name", prop["id"])
        state["archetype"] = archetype
        state["cycle_index"] = cycle_index
        state["buy_mult_lo"] = buy_mult_lo
        state["buy_mult_hi"] = buy_mult_hi
        state["sell_ratio"] = sell_ratio
        state["unlisted_sell_ratio"] = float(max(0.1, min(0.85, profile.get("unlisted_sell_ratio", 0.3))))
        state["supply_note"] = str(market_profile.get("store_note", "")).strip()
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

        if state.get("cycle_index") != cycle_index:
            self._rebuild_store(state, prop, cycle_index)

        return state

    def _entry_for_item(self, state, item_id):
        for entry in state.get("entries", []):
            if entry.get("item_id") == item_id:
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

    def _sell_quote(self, item_id, state, terms=None):
        terms = terms or {"sell_mult": 1.0}
        listed = self._entry_for_item(state, item_id)
        if listed:
            return self._effective_sell_price(listed.get("sell_price", 1), terms), True
        base = int(max(1, self.ITEM_BASE_VALUES.get(item_id, 10)))
        ratio = float(max(0.1, min(0.85, state.get("unlisted_sell_ratio", 0.3))))
        return self._effective_sell_price(max(1, int(round(base * ratio))), terms), False

    def _store_accepts_vehicle_trade_in(self, store_prop):
        if not isinstance(store_prop, dict):
            return False
        services = set(_site_services_for_property(store_prop))
        return "vehicle_sales_new" in services or "vehicle_sales_used" in services

    def _vehicle_trade_in_quote(self, vehicle_prop):
        metadata = _property_metadata(vehicle_prop)
        quality = str(metadata.get("vehicle_quality", "used") or "used").strip().lower() or "used"
        purchase_cost = int(max(80, _int_or_default(metadata.get("purchase_cost"), 500)))
        ratio = float(self.VEHICLE_TRADE_IN_VALUE_BY_QUALITY.get(quality, self.VEHICLE_TRADE_IN_VALUE_BY_QUALITY["used"]))

        durability = max(1, min(10, _int_or_default(metadata.get("durability"), 5)))
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
            price=payout,
            base_price=payout,
            listed=False,
            stock_now=0,
            credits=assets.credits,
            contact_source_eid=(terms or {}).get("source_eid") if isinstance(terms, dict) else None,
            contact_note=(terms or {}).get("note", "") if isinstance(terms, dict) else "",
        ))
        return True

    def _trade_sell_candidates(self, inventory, store, terms=None):
        candidates = []
        if not inventory:
            return candidates

        for entry in inventory.items:
            item_id = entry.get("item_id")
            quote, listed = self._sell_quote(item_id, store, terms=terms)
            item_def = ITEM_CATALOG.get(item_id, {"name": item_id, "glyph": "*"})
            display_name = item_display_name(item_id, metadata=entry.get("metadata"), item_catalog=ITEM_CATALOG)
            candidates.append({
                "entry": entry,
                "instance_id": entry.get("instance_id"),
                "item_id": item_id,
                "item_name": display_name,
                "glyph": _item_display_glyph(item_def),
                "quantity": int(entry.get("quantity", 1)),
                "price": int(max(1, quote)),
                "listed": bool(listed),
            })

        candidates.sort(key=lambda row: (-row["price"], row["item_id"], row["instance_id"]))
        return candidates

    def _trade_buy_rows(self, store, terms=None):
        terms = terms or {"buy_mult": 1.0}
        rows = []
        for entry in sorted(
            list(store.get("entries", [])),
            key=lambda row: (self._effective_buy_price(row.get("buy_price", 0), terms), row.get("item_id", "")),
        ):
            item_id = entry.get("item_id")
            item_def = ITEM_CATALOG.get(item_id, {"name": item_id, "glyph": "*"})
            rows.append({
                "item_id": item_id,
                "item_name": item_def.get("name", item_id),
                "glyph": _item_display_glyph(item_def),
                "price": self._effective_buy_price(entry.get("buy_price", 1), terms),
                "stock": int(max(0, entry.get("stock", 0))),
            })
        return rows

    def _trade_sell_rows(self, inventory, store, terms=None):
        rows = []
        for row in self._trade_sell_candidates(inventory, store, terms=terms):
            rows.append({
                "instance_id": row["instance_id"],
                "item_id": row["item_id"],
                "item_name": row["item_name"],
                "glyph": row["glyph"],
                "quantity": row["quantity"],
                "price": row["price"],
                "listed": row["listed"],
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

        if state.get("mode") == "buy":
            state["inspect_text"] = _item_legend_line(
                row.get("item_id"),
                (
                    f"{row.get('item_name', row.get('item_id', 'item'))} "
                    f"{int(row.get('price', 0))} credits stock {int(row.get('stock', 0))}"
                ),
            )
            return

        listed_text = "listed" if row.get("listed") else "unlisted"
        state["inspect_text"] = _item_legend_line(
            row.get("item_id"),
            (
                f"{row.get('item_name', row.get('item_id', 'item'))} "
                f"offer {int(row.get('price', 0))} credits ({listed_text}) "
                f"qty {int(row.get('quantity', 0))}"
            ),
        )

    def _refresh_trade_ui(
        self,
        mode=None,
        keep_selection=True,
        preferred_item_id=None,
        preferred_instance_id=None,
        target_property_id=None,
        emit_toggle=False,
        automated_only=False,
    ):
        state = self._trade_ui_state()
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

        store = self._store_state(store_prop)
        inventory = self._inventory_for(self.player_eid)
        terms = self._trade_terms(self.player_eid, store_prop)
        mode = state.get("mode", "buy")
        rows = (
            self._trade_buy_rows(store, terms=terms)
            if mode == "buy"
            else self._trade_sell_rows(inventory, store, terms=terms)
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
        if was_open:
            self.sim.emit(Event("trade_panel_toggled", eid=self.player_eid, open=False))

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

        store = self._store_state(store_prop)
        terms = self._trade_terms(eid, store_prop)
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
            if assets.credits < effective_price:
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
            choice, cheapest = self._best_buy_entry(store, assets.credits, terms=terms)
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
        item_def = ITEM_CATALOG.get(item_id, {"name": item_id, "stack_max": 1})
        added, instance_id = inventory.add_item(
            item_id=item_id,
            quantity=1,
            stack_max=item_def.get("stack_max", 1),
            instance_factory=self.sim.new_item_instance_id,
            owner_eid=eid,
            owner_tag="player" if eid == self.player_eid else "npc",
            metadata={
                "purchased_from": store_prop["id"],
                "store_cycle": store.get("cycle_index"),
            },
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
        price = self._effective_buy_price(base_price, terms)
        assets.credits -= price
        choice["stock"] = max(0, int(choice.get("stock", 0)) - 1)

        self.sim.emit(Event(
            "trade_bought",
            eid=eid,
            property_id=store_prop["id"],
            store_name=store_prop.get("name", store_prop["id"]),
            item_id=item_id,
            item_name=item_def.get("name", item_id),
            price=price,
            base_price=base_price,
            stock_left=choice["stock"],
            credits=assets.credits,
            instance_id=instance_id,
            contact_source_eid=terms.get("source_eid"),
            contact_note=terms.get("note", ""),
        ))
        return True

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
        store_prop, _service = self._resolve_store(pos, preferred_property_id=state.get("property_id"), radius=2)
        if not store_prop:
            self.sim.emit(Event("trade_sell_blocked", eid=eid, reason="no_store"))
            return False

        store = self._store_state(store_prop)
        terms = self._trade_terms(eid, store_prop)

        candidates = self._trade_sell_candidates(inventory, store, terms=terms)
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
            str(best.get("item_id", "") or "").strip().lower() == "property_key"
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
        base_payout, _ = self._sell_quote(item_id, store, terms={"sell_mult": 1.0})
        payout = int(max(1, best["price"]))
        assets.credits += payout

        existing = self._entry_for_item(store, item_id)
        if existing:
            existing["stock"] = int(existing.get("stock", 0)) + int(max(1, removed.get("quantity", 1)))
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
                "stock": int(max(1, removed.get("quantity", 1))),
                "buy_price": buy_price,
                "sell_price": sell_price,
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
            item_name=item_display_name(item_id, metadata=removed.get("metadata"), item_catalog=ITEM_CATALOG),
            price=payout,
            base_price=base_payout,
            listed=bool(best["listed"]),
            stock_now=stock_now,
            credits=assets.credits,
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

        prop = self.sim.properties.get(event.data.get("property_id"))
        if not self._is_storefront(prop):
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

