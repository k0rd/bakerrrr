"""Shared profession gear used by normal starts and ambient workers."""


NORMAL_START_LOADOUT_IDS = (
    "street",
    "butcher",
    "herbalist",
    "clinic_hand",
    "garage_hand",
    "courier",
)


def _merged_item_rows(*groups):
    quantities = {}
    for group in groups:
        for item_id, quantity in tuple(group or ()):
            item_id = str(item_id or "").strip().lower()
            if item_id:
                quantities[item_id] = int(quantities.get(item_id, 0)) + max(0, int(quantity))
    return tuple((item_id, quantity) for item_id, quantity in quantities.items() if quantity > 0)


_PROFESSION_PROFILES = {
    "butcher": {
        "workplace_archetypes": ("butcher_shop",),
        "core_items": (
            ("butcher_apron", 1),
            ("field_knife", 1),
            ("kill_bag", 1),
            ("packaged_game_meat", 1),
        ),
        "player_extras": (
            ("packaged_game_meat", 1),
            ("bottled_water", 1),
        ),
        "worn_item_id": "butcher_apron",
    },
    "herbalist": {
        "workplace_archetypes": ("herbalist_shop", "herbalist_camp"),
        "core_items": (
            ("botany_apron", 1),
            ("pruning_shears", 1),
            ("mortar_kit", 1),
            ("seed_packet", 1),
            ("herbal_poultice", 1),
        ),
        "player_extras": (
            ("street_ration", 1),
            ("bottled_water", 1),
        ),
        "worn_item_id": "botany_apron",
    },
    "clinic_hand": {
        "workplace_archetypes": (
            "backroom_clinic",
            "pharmacy",
            "biotech_clinic",
            "field_hospital",
            "tide_station",
        ),
        "core_items": (
            ("micro_medkit", 1),
            ("field_dressing", 1),
            ("antiseptic_wipes", 1),
        ),
        "player_extras": (
            ("field_dressing", 1),
            ("bandage_roll", 1),
            ("suture_kit", 1),
            ("protein_wrap", 1),
            ("bottled_water", 1),
        ),
    },
    "garage_hand": {
        "workplace_archetypes": ("auto_garage",),
        "core_items": (
            ("maintenance_vest", 1),
            ("pocket_multitool", 1),
            ("battery_pack", 1),
            ("wire_spool", 1),
        ),
        "player_extras": (
            ("salvaged_hardware", 1),
            ("canteen_coffee", 1),
        ),
        "worn_item_id": "maintenance_vest",
        "weapon_id": "tire_iron",
    },
    "courier": {
        "workplace_archetypes": ("courier_office",),
        "core_items": (
            ("backpack", 1),
            ("phone", 1),
            ("transit_daypass", 1),
            ("pocket_notebook", 1),
        ),
        "player_extras": (
            ("energy_bar", 2),
            ("bottled_water", 1),
        ),
        "armor_item_id": "courier_mesh",
    },
}


NORMAL_START_LOADOUTS = {
    loadout_id: {
        "items": _merged_item_rows(profile.get("core_items"), profile.get("player_extras")),
        **{
            key: str(profile.get(key, "") or "").strip()
            for key in ("worn_item_id", "weapon_id", "armor_item_id")
            if str(profile.get(key, "") or "").strip()
        },
    }
    for loadout_id, profile in _PROFESSION_PROFILES.items()
}


NPC_PROFESSION_LOADOUTS_BY_ARCHETYPE = {
    str(archetype): {
        "items": tuple(profile.get("core_items", ()) or ()),
        **(
            {"worn_item_id": str(profile.get("worn_item_id"))}
            if str(profile.get("worn_item_id", "") or "").strip()
            else {}
        ),
    }
    for profile in _PROFESSION_PROFILES.values()
    for archetype in tuple(profile.get("workplace_archetypes", ()) or ())
}


__all__ = (
    "NORMAL_START_LOADOUT_IDS",
    "NORMAL_START_LOADOUTS",
    "NPC_PROFESSION_LOADOUTS_BY_ARCHETYPE",
)
