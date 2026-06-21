"""Public registries for narrow custom content surfaces."""

from __future__ import annotations


PUBLIC_ITEM_EFFECT_TYPES = (
    "modify_need",
    "restore_hp",
    "status",
    "credits",
    "add_ammo",
)

PUBLIC_ITEM_NEEDS = (
    "energy",
    "safety",
    "social",
    "hunger",
    "thirst",
)

PUBLIC_STATUS_MODIFIERS = {
    "energy_tick_delta": "Energy change each tick while the status lasts.",
    "safety_tick_delta": "Safety/nerve change each tick while the status lasts.",
    "social_tick_delta": "Social comfort change each tick while the status lasts.",
    "hunger_tick_delta": "Hunger change each tick while the status lasts.",
    "thirst_tick_delta": "Thirst change each tick while the status lasts.",
    "hp_tick_delta": "Low-grade HP regeneration or bleed-like drift each tick.",
    "toxicity_tick_delta": "Low-grade toxin HP drift each tick.",
    "move_speed_mult": "Movement speed multiplier modifier.",
    "ranged_accuracy_mult": "Ranged accuracy multiplier modifier.",
    "projectile_spread_mod": "Projectile spread adjustment.",
    "weapon_cooldown_mult": "Weapon cooldown multiplier modifier.",
    "melee_cooldown_mult": "Melee cooldown multiplier modifier.",
    "ranged_damage_mult": "Ranged damage multiplier modifier.",
    "melee_damage_mult": "Melee damage multiplier modifier.",
    "incoming_damage_mult": "Incoming damage multiplier modifier.",
    "armor_absorb_bonus": "Armor absorption bonus.",
    "cover_absorb_bonus": "Cover absorption bonus.",
    "suppression_resist_mult": "Suppression resistance multiplier modifier.",
    "assault_bias_delta": "NPC assault intent bias adjustment.",
    "retreat_bias_delta": "NPC retreat intent bias adjustment.",
    "movement_misdirect_chance": "Chance a movement input goes a nearby direction.",
    "hallucination_intensity": "Strength of hallucination rendering overlays.",
    "hallucination_read_chance": "Chance look/examine reads are altered.",
    "control_lapse_chance": "Chance a control lapse begins.",
    "control_lapse_ticks": "Ticks a control lapse lasts.",
    "blackout_chance": "Chance an altered-state blackout begins.",
    "blackout_min_ticks": "Minimum blackout duration in ticks.",
    "blackout_max_ticks": "Maximum blackout duration in ticks.",
    "blackout_cooldown_ticks": "Cooldown between blackout attempts.",
}

PUBLIC_DENSITY_LEVELS = ("none", "low", "medium", "high")
PUBLIC_WATER_LEVELS = ("none", "low", "medium", "high")

PUBLIC_WORLD_PROFILE_FIELDS = (
    "label",
    "selection_weight",
    "area_types",
    "district_types",
    "population_density",
    "building_density",
    "water",
    "building_weights",
    "service_building_weights",
)

PUBLIC_ROOM_CURIOSITY_FLAVOR_FIELDS = (
    "label",
    "base_profile",
    "selection_weight",
    "archetypes",
    "room_kinds",
    "room_curiosity_signal",
)

PUBLIC_ROOM_CURIOSITY_BASE_PROFILES = (
    "afterhours_pusher",
    "backroom_doctor",
    "backroom_entrepreneur",
    "backstage_worker",
    "hotel_afterhours_guest",
    "quiet_contact",
    "records_keeper",
    "stash_ledger",
    "transit_staff_roamer",
)

PUBLIC_ROOM_CURIOSITY_ROOM_KINDS = (
    "archive",
    "back_office",
    "backstage",
    "balcony",
    "boardroom",
    "clerk_office",
    "evidence_lockup",
    "executive_office",
    "front_desk",
    "green_room",
    "guest_floor",
    "guest_lounge",
    "linen_closet",
    "locker_wall",
    "meeting_room",
    "office",
    "platform",
    "quiet_room",
    "records",
    "records_office",
    "records_room",
    "screening_room",
    "server_room",
    "service_corridor",
    "service_office",
    "sound_booth",
    "stock_room",
    "storage",
    "surveillance_room",
    "ticketing",
    "vip_lounge",
)


def public_building_archetype_ids():
    from engine.world import World

    world = World(seed=0)
    return tuple(sorted(str(archetype) for archetype in world.building_archetypes))


def public_area_types():
    from engine.world import World

    return tuple(World.AREA_TYPES)


def public_district_types():
    from engine.world import World

    return tuple(World.DISTRICT_TYPES)
