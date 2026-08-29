"""Shared raw-schema declarations for authored item definitions.

The runtime remains forgiving when it consumes third-party or old content.  The
built-in validator and Workbench editor use these declarations to agree on
which authored fields are intentional instead of maintaining parallel lists.
"""

from __future__ import annotations


COMMON_ITEM_FIELDS = (
    "name", "description", "glyph", "stack_max", "inventory_slot_cost",
    "tags", "category", "legal_status", "effects", "weapon_id",
    "appearance_family", "appearance_slots", "appearance_drawable",
)

ITEM_PROFILE_FIELDS = (
    "appearance_profile", "identification_profile", "tool_profiles", "armor",
    "disguise", "container", "throw_profile", "trap_profile",
    "substance_profile", "lead_profile", "drone_profile", "wire_profile",
    "wire_interface_profile", "object_profile", "scratch_payout_table",
    "condition_profile", "world_distribution", "fire_profile",
)

KNOWN_ITEM_FIELDS = frozenset(COMMON_ITEM_FIELDS + ITEM_PROFILE_FIELDS)

ITEM_PROFILE_KEYS: dict[str, frozenset[str]] = {
    "appearance_profile": frozenset({
        "label", "presentation", "materials", "styles", "details", "patterns",
        "emblems", "emblem_chance", "basewear", "articleless", "personal_token",
        "fashion_item", "starter_weights",
    }),
    "identification_profile": frozenset({
        "family", "requires_identification", "auto_identify_on_use",
        "unidentified_name", "appraisal_fields",
    }),
    "armor": frozenset({"slot", "damage_reduction"}),
    "disguise": frozenset({"role_id", "strength"}),
    "container": frozenset({
        "bonus_slots", "slot", "blocks_armor", "accepted_item_ids",
        "accepted_tags", "rejected_tags", "accepts_note",
    }),
    "throw_profile": frozenset({
        "range", "trajectory", "projectile_glyph", "speed", "damage",
        "noise_radius", "explosion_radius", "aoe_falloff", "cover_penetration",
        "fire_intensity", "smoke_intensity", "cloud_radius", "cloud_duration",
        "aerosol_status", "aerosol_duration", "aerosol_modifiers",
        "aerosol_exposure_cooldown", "aerosol_label", "consume_on_throw", "shatter",
    }),
    "trap_profile": frozenset({
        "payload_item_id", "trigger_kind", "armed_glyph", "armed_color",
        "noise_radius", "homemade",
    }),
    "substance_profile": frozenset({
        "substance_id", "intoxication_duration", "dependence_gain",
        "dependence_decay", "withdrawal_threshold", "withdrawal_status",
        "withdrawal_duration", "withdrawal_cooldown", "withdrawal_modifiers",
    }),
    "lead_profile": frozenset({
        "lead_kind", "confidence", "discovery_mode", "consume_on_use",
        "hidden_on_learn", "source_metadata_key", "property_services",
        "property_archetypes",
    }),
    "drone_profile": frozenset({
        "active_draw", "base_color", "base_glyph", "base_hp", "base_range",
        "capabilities", "charge_max", "chassis_class", "compatible_chassis",
        "disposable", "idle_overhead", "kind", "mark", "module_kind",
        "power_output", "procedure_slot_limit", "sensor_kind",
        "sensor_occlusion_depth", "sensor_power_cost", "sensor_range", "slot_cost",
        "slot_limit", "standby_draw", "visible_overlay", "weight", "weight_limit",
    }),
    "wire_profile": frozenset({
        "backup_family", "burnable", "buyer_tags", "capabilities",
        "corruption_tags", "credential_scope", "dangerous", "data_family",
        "default_quality", "display_family", "durability_max", "freshness",
        "heat_risk", "kind", "legality", "license_scope", "license_source",
        "loadable", "noise", "program_family", "program_key", "program_mode",
        "ram_cost", "reload_ticks", "restores_corruption", "runs_max",
        "sensitivity", "source_context", "storage_points", "trace_cost",
        "trace_strength",
    }),
    "wire_interface_profile": frozenset({
        "buffer_size", "default_quality", "kind", "manufacturer", "noise_floor",
        "panic_eject_delay", "program_slots", "range", "recovery_delay", "safe_yank",
        "shock_risk", "signature_leakage", "style", "supported_target_classes",
        "trace_resistance", "warning_rating",
    }),
    "object_profile": frozenset({
        "schema_version", "family", "silhouette", "material", "primary_color",
        "accent_color", "motif", "condition", "rarity", "placeable",
        "pickup_allowed", "display_name", "description", "display_glyph",
        "display_color", "future_tags",
    }),
    "condition_profile": frozenset({
        "supports_quality", "supports_durability", "default_quality", "max_durability",
    }),
    "world_distribution": frozenset({
        "weight", "store_archetypes", "loot_archetypes", "carrier_archetypes",
    }),
    "fire_profile": frozenset({"breakable", "flammability", "hp", "max_hp"}),
}

TOOL_PROFILE_KEYS = frozenset({
    "contexts", "enable_contexts", "intrusion_bonus", "mechanics_bonus",
    "perception_bonus", "score_bonus", "requirement_delta", "tool_wear_mult",
})
