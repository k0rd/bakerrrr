"""Shared catalogue and item-instance valuation.

The value calculated here is an item's fair, one-unit baseline.  Store markup,
buyer interest, local pressure, and cosmetic demand belong to their respective
markets, but every market starts from this same appraisal.
"""

from __future__ import annotations

from collections.abc import Mapping

from game.drone_distribution import DRONE_ITEM_BASE_VALUES
from game.items import ITEM_CATALOG, credstick_total_credits, is_credstick_item, item_instance_condition
from game.weapons import weapon_by_id
from game.wire_distribution import WIRE_ITEM_BASE_VALUES


CORE_ITEM_BASE_VALUES = {
    "street_ration": 10,
    "protein_wrap": 11,
    "raw_game_meat": 6,
    "bagged_game_meat": 8,
    "cooked_game_meat": 10,
    "packaged_game_meat": 14,
    "noodle_cup": 9,
    "spark_brew": 14,
    "calm_patch": 18,
    "caff_shot": 16,
    "hydration_salts": 15,
    "med_gel": 22,
    "micro_medkit": 18,
    "trauma_foam": 34,
    "trauma_autoinjector": 92,
    "field_restraint_jab": 48,
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
    "two_way_radio": 38,
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
    "field_knife": 26,
    "pruning_shears": 24,
    "mortar_kit": 36,
    "kill_bag": 34,
    "butcher_apron": 48,
    "botany_apron": 48,
    "fresh_blossoms": 6,
    "leaf_clippings": 5,
    "moss_scrapings": 6,
    "vine_cuttings": 5,
    "seed_packet": 10,
    "plant_pot": 18,
    "herbal_poultice": 24,
    "hydrating_tonic": 20,
    "calming_tincture": 20,
    "strong_herbal_poultice": 42,
    "field_restorative": 38,
    "steadying_draught": 34,
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
    "undershirt": 8,
    "tank_undershirt": 9,
    "bra": 16,
    "bralette": 18,
    "camisole": 17,
    "bandeau": 13,
    "boxers": 9,
    "boxer_briefs": 11,
    "briefs": 8,
    "boyshorts": 13,
    "bikini_panties": 14,
    "cheeky_panties": 16,
    "thong": 13,
    "high_waist_panties": 15,
}

ITEM_BASE_VALUES = {
    **CORE_ITEM_BASE_VALUES,
    **DRONE_ITEM_BASE_VALUES,
    **WIRE_ITEM_BASE_VALUES,
}

CATEGORY_BASE_VALUES = {
    "ammo": 7,
    "armor": 28,
    "consumable": 6,
    "container": 18,
    "cosmetic": 12,
    "credential": 18,
    "device": 18,
    "drone": 90,
    "drone_part": 38,
    "medical": 8,
    "misc": 5,
    "throwable": 7,
    "token": 4,
    "tool": 16,
    "weapon": 20,
    "wire_data": 18,
    "wire_interface": 55,
    "wireware": 35,
}

LEGALITY_MULTIPLIERS = {
    "legal": 1.0,
    "suspicious": 1.08,
    "restricted": 1.16,
    "illegal": 1.28,
    "stolen": 0.72,
}

OBJECT_MATERIAL_VALUES = {
    "paper": 3,
    "herb": 4,
    "cloth": 5,
    "wax": 5,
    "shell": 7,
    "wood": 8,
    "tin": 9,
    "stone": 10,
    "ceramic": 11,
    "glass": 13,
    "steel": 16,
    "brass": 20,
}

OBJECT_RARITY_MULTIPLIERS = {
    "common": 1.0,
    "uncommon": 1.4,
    "rare": 2.15,
    "unique": 3.4,
}

OBJECT_CONDITION_MULTIPLIERS = {
    "cracked": 0.58,
    "chipped": 0.76,
    "dusty": 0.84,
    "repaired": 0.96,
    "plain": 1.0,
    "wrapped": 1.08,
    "polished": 1.24,
}

QUALITY_MULTIPLIERS = {
    "poor": 0.74,
    "standard": 1.0,
    "good": 1.16,
    "excellent": 1.34,
}


def _number(value, default=0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _meaningful_object_value(profile: Mapping | None) -> tuple[float, dict]:
    profile = profile if isinstance(profile, Mapping) else {}
    material = str(profile.get("material", "ceramic") or "ceramic").strip().lower()
    rarity = str(profile.get("rarity", "common") or "common").strip().lower()
    condition = str(profile.get("condition", "plain") or "plain").strip().lower()
    motif = str(profile.get("motif", "none") or "none").strip().lower()
    family = str(profile.get("family", "personal_home") or "personal_home").strip().lower()
    material_value = float(OBJECT_MATERIAL_VALUES.get(material, 8))
    craft_value = {
        "paper_books": 2.0,
        "nature_finds": 1.0,
        "textiles": 3.0,
        "tokens_charms": 4.0,
        "plants_pots": 4.0,
        "personal_home": 5.0,
        "containers": 6.0,
        "tools_parts": 7.0,
        "trade_work": 7.0,
        "medical_herbal": 8.0,
        "light_ritual": 9.0,
    }.get(family, 4.0)
    motif_mult = 1.0 if motif in {"", "none"} else 1.1
    rarity_mult = float(OBJECT_RARITY_MULTIPLIERS.get(rarity, 1.0))
    condition_mult = float(OBJECT_CONDITION_MULTIPLIERS.get(condition, 1.0))
    value = (material_value + craft_value) * motif_mult * rarity_mult * condition_mult
    return value, {
        "material": material,
        "rarity": rarity,
        "object_condition": condition,
        "motif": motif,
    }


def _derived_catalogue_value(item_id: str, item_def: Mapping) -> tuple[float, dict]:
    category = str(item_def.get("category", "misc") or "misc").strip().lower()
    tags = {str(tag or "").strip().lower() for tag in item_def.get("tags", ()) if str(tag or "").strip()}
    value = float(CATEGORY_BASE_VALUES.get(category, 8))
    details = {"category": category, "utility": 0.0}

    weapon_id = str(item_def.get("weapon_id", "") or "").strip()
    if weapon_id:
        weapon = weapon_by_id(weapon_id)
        damage = _number(weapon.get("base_damage"), 4)
        range_value = _number(weapon.get("range"), 1)
        pellets = max(1.0, _number(weapon.get("pellets"), 1))
        explosion = _number(weapon.get("explosion_radius"), 0)
        penetration = _number(weapon.get("cover_penetration"), 0)
        cooldown = max(1.0, _number(weapon.get("cooldown_ticks"), 2))
        combat_utility = (damage * (1.0 + min(2.5, (pellets - 1.0) * 0.22)) * 5.0) + (range_value * 2.6)
        combat_utility += explosion * 34.0 + penetration * 42.0 + max(0.0, 3.0 - cooldown) * 10.0
        value = 15.0 + combat_utility
        details["utility"] += combat_utility

    armor = item_def.get("armor") if isinstance(item_def.get("armor"), Mapping) else {}
    if armor:
        reduction = max(0.0, _number(armor.get("damage_reduction"), 0.0))
        armor_utility = reduction * 520.0
        value = 24.0 + armor_utility
        details["utility"] += armor_utility

    tool_profiles = tuple(profile for profile in item_def.get("tool_profiles", ()) if isinstance(profile, Mapping))
    if tool_profiles:
        tool_utility = 0.0
        for profile in tool_profiles:
            contexts = set(profile.get("contexts", ()) or ()) | set(profile.get("enable_contexts", ()) or ())
            bonuses = sum(max(0.0, _number(profile.get(key), 0.0)) for key in ("intrusion_bonus", "mechanics_bonus", "perception_bonus", "score_bonus"))
            tool_utility += len(contexts) * 1.8 + bonuses * 5.0 + max(0.0, -_number(profile.get("requirement_delta"), 0.0)) * 4.0
        value = max(value, 12.0 + tool_utility)
        details["utility"] += tool_utility

    for effect in item_def.get("effects", ()) or ():
        if not isinstance(effect, Mapping):
            continue
        effect_type = str(effect.get("type", "") or "").strip().lower()
        utility = 0.0
        if effect_type == "restore_hp":
            utility = max(0.0, _number(effect.get("delta"), 0.0)) * 1.05
        elif effect_type == "modify_need":
            utility = max(0.0, _number(effect.get("delta"), 0.0)) * 0.16
        elif effect_type == "extend_wakefulness":
            utility = max(0.0, _number(effect.get("hours"), 0.0)) * 4.0
        elif effect_type == "add_ammo":
            utility = max(0.0, _number(effect.get("amount"), 0.0)) * 1.45
        elif effect_type == "credits":
            utility = max(0.0, _number(effect.get("delta"), 0.0))
        elif effect_type == "status":
            utility = max(1.0, _number(effect.get("duration"), 0.0) * 0.11)
            utility += len(effect.get("modifiers", {}) or {}) * 1.5
        else:
            utility = 2.0
        value += utility
        details["utility"] += utility

    container = item_def.get("container") if isinstance(item_def.get("container"), Mapping) else {}
    if container:
        value += max(0.0, _number(container.get("bonus_slots"), 0.0)) * 8.0

    throw_profile = item_def.get("throw_profile") if isinstance(item_def.get("throw_profile"), Mapping) else {}
    if throw_profile:
        tactical = _number(throw_profile.get("damage"), 0.0) * 2.0
        tactical += _number(throw_profile.get("range"), 0.0) * 1.4
        tactical += _number(throw_profile.get("explosion_radius"), 0.0) * 16.0
        tactical += _number(throw_profile.get("fire_intensity"), 0.0) * 8.0
        tactical += _number(throw_profile.get("smoke_intensity"), 0.0) * 5.0
        tactical += _number(throw_profile.get("cloud_duration"), 0.0) * 0.5
        value += tactical
        details["utility"] += tactical

    trap_profile = item_def.get("trap_profile") if isinstance(item_def.get("trap_profile"), Mapping) else {}
    if trap_profile:
        trap_utility = 12.0 + _number(trap_profile.get("duration"), 0.0) * 0.5
        value += trap_utility
        details["utility"] += trap_utility

    if "quest" in tags:
        value = max(value, 20.0)
    if "junk" in tags:
        value *= 0.72
    if "disguise" in tags:
        value += 12.0
    if "death_save" in tags:
        value += 28.0

    legal_status = str(item_def.get("legal_status", "legal") or "legal").strip().lower()
    value *= float(LEGALITY_MULTIPLIERS.get(legal_status, 1.0))
    details["legal_status"] = legal_status
    return value, details


def item_value_quote(item_id, metadata=None, *, item_catalog=None) -> dict:
    """Return a transparent fair-value quote for one item unit."""

    catalog = item_catalog or ITEM_CATALOG
    item_id = str(item_id or "").strip().lower()
    item_def = catalog.get(item_id, {}) if isinstance(catalog, Mapping) else {}
    metadata = metadata if isinstance(metadata, Mapping) else {}

    if is_credstick_item(item_id) and metadata:
        stored = int(max(0, credstick_total_credits(quantity=1, metadata=metadata)))
        if stored > 0:
            return {
                "item_id": item_id,
                "base_value": stored,
                "fair_value": stored,
                "source": "stored_credits",
                "condition_multiplier": 1.0,
            }

    profile = metadata.get("object_profile") if isinstance(metadata.get("object_profile"), Mapping) else None
    if item_id == "meaningful_object" and profile:
        base, details = _meaningful_object_value(profile)
        source = "object_profile"
    elif item_id in ITEM_BASE_VALUES:
        base = float(ITEM_BASE_VALUES[item_id])
        details = {"category": str(item_def.get("category", "") or "").strip().lower()}
        source = "explicit"
    else:
        base, details = _derived_catalogue_value(item_id, item_def)
        source = "catalogue_derived"

    condition = item_instance_condition(item_id, metadata=dict(metadata), item_catalog=catalog)
    quality = str(condition.get("quality", "standard") or "standard").strip().lower()
    condition_mult = float(QUALITY_MULTIPLIERS.get(quality, 1.0))
    if bool((condition.get("profile") or {}).get("supports_durability")):
        durability_ratio = max(0.0, min(1.0, _number(condition.get("durability_ratio"), 1.0)))
        condition_mult *= 0.48 + durability_ratio * 0.52

    ecology_mult = max(1.0, min(8.0, _number(metadata.get("ecology_value_multiplier"), 1.0)))
    fair_value = max(1, int(round(max(1.0, base) * condition_mult * ecology_mult)))
    return {
        "item_id": item_id,
        "base_value": max(1, int(round(max(1.0, base)))),
        "fair_value": fair_value,
        "source": source,
        "quality": quality,
        "condition_multiplier": condition_mult,
        "ecology_value_multiplier": ecology_mult,
        **details,
    }


def item_fair_value(item_id, metadata=None, *, item_catalog=None) -> int:
    return int(item_value_quote(item_id, metadata, item_catalog=item_catalog)["fair_value"])
