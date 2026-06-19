# Custom Content

Custom content is loaded once when a run starts. It can add consumable-style items and optional world-profile styles that bias new chunks. Existing built-in content stays in the game.

Copy JSON files into these live folders:

```bash
config/custom_content/items/
config/custom_content/world_profiles/
```

Copy-ready examples are included here:

```bash
PLAYER_GUIDE/examples/custom_content/items/morning_glory_seeds.json
PLAYER_GUIDE/examples/custom_content/world_profiles/canal_slums.json
```

## Load Rules

- the project will keep this file up-to-date when the specification changes. the loading process is strict. 
- Item files are checked as one domain. If any item file fails, no custom items load for that run.
- World-profile files are checked as one domain. If any world-profile file fails, no custom world profiles load for that run.
- A bad item file does not disable valid world-profile files, and a bad world-profile file does not disable valid item files.
- Problems are shown in game before play continues.
- Saved runs remember the exact custom files they started with. The game stores file paths, schema versions, SHA-256 hashes, and loaded ids, not the JSON bodies.
- When resuming a saved run, required custom files must still exist and match exactly. A missing file or hash mismatch blocks resume and leaves the save file in place.
- Extra current custom files are ignored when resuming an older save.

## Item Files

Each file is a JSON object with `_meta.schema_version` set to `1`, then one or more new item ids:

```json
{
  "_meta": {
    "schema_version": 1
  },
  "morning_glory_seeds": {
    "name": "Morning Glory Seeds",
    "glyph": "*",
    "stack_max": 2,
    "tags": ["consumable", "drug", "hallucinogen", "seed"],
    "category": "consumable",
    "legal_status": "illegal",
    "effects": [
      {
        "type": "status",
        "status": "tripping",
        "duration": 60,
        "modifiers": {
          "toxicity_tick_delta": 0.1,
          "hallucination_intensity": 1.0,
          "hallucination_read_chance": 0.45
        }
      }
    ]
  }
}
```

Item ids must be lowercase letters, numbers, and underscores only. Custom ids cannot collide with built-in item ids or other custom ids.

Allowed item fields in this version:

`name`, `glyph`, `stack_max`, `tags`, `category`, `legal_status`, `effects`, `appearance_family`, `appearance_slots`, `identification_profile`, `substance_profile`, `lead_profile`

This version does not add custom weapons, armor, containers, throwables, tools, scripts, or new building types.

Allowed effect types:

`modify_need`, `restore_hp`, `status`, `credits`, `add_ammo`

Allowed needs for `modify_need`:

`energy`, `safety`, `social`, `hunger`, `thirst`

Allowed status modifier keys:

`armor_absorb_bonus`, `assault_bias_delta`, `blackout_chance`, `blackout_cooldown_ticks`, `blackout_max_ticks`, `blackout_min_ticks`, `control_lapse_chance`, `control_lapse_ticks`, `cover_absorb_bonus`, `energy_tick_delta`, `hallucination_intensity`, `hallucination_read_chance`, `hp_tick_delta`, `hunger_tick_delta`, `incoming_damage_mult`, `melee_cooldown_mult`, `melee_damage_mult`, `move_speed_mult`, `movement_misdirect_chance`, `projectile_spread_mod`, `ranged_accuracy_mult`, `ranged_damage_mult`, `retreat_bias_delta`, `safety_tick_delta`, `social_tick_delta`, `suppression_resist_mult`, `thirst_tick_delta`, `toxicity_tick_delta`, `weapon_cooldown_mult`

## World Profile Files

World profiles are interpretive. They bias the existing city generator instead of painting exact tiles.

```json
{
  "_meta": {
    "schema_version": 1
  },
  "canal_slums": {
    "label": "Canal Slums",
    "selection_weight": 2.0,
    "area_types": ["city"],
    "district_types": ["slums", "industrial"],
    "population_density": "high",
    "building_density": "medium",
    "water": "medium",
    "building_weights": {
      "tenement": 2.0,
      "flophouse": 1.6,
      "soup_kitchen": 1.1
    },
    "service_building_weights": {
      "soup_kitchen": 1.5
    }
  }
}
```

Allowed world-profile fields:

`label`, `selection_weight`, `area_types`, `district_types`, `population_density`, `building_density`, `water`, `building_weights`, `service_building_weights`

Allowed `population_density`, `building_density`, and `water` values:

`none`, `low`, `medium`, `high`

Allowed `area_types` values:

`city`, `coastal`, `frontier`, `wilderness`

Allowed `district_types` values:

`corporate`, `downtown`, `entertainment`, `industrial`, `military`, `residential`, `slums`

Allowed building ids for `building_weights` and `service_building_weights`:

`accessory_shop`, `apartment`, `arcade`, `armory`, `auto_garage`, `backroom_clinic`, `bank`, `bar`, `barbershop`, `barracks`, `biotech_clinic`, `bookshop`, `bottom_shop`, `bounty_office`, `brokerage`, `casino`, `checkpoint`, `chop_shop`, `clothing_superstore`, `co_working_hub`, `cold_storage`, `command_center`, `contractor_office`, `corner_store`, `courier_office`, `courthouse`, `data_center`, `daycare`, `dress_shop`, `employment_agency`, `factory`, `field_hospital`, `flophouse`, `freight_depot`, `gallery`, `gaming_hall`, `hair_studio`, `hardware_store`, `headwear_shop`, `hotel`, `house`, `jail`, `jewelry_shop`, `junk_market`, `karaoke_box`, `lab`, `laundromat`, `machine_shop`, `makeup_counter`, `media_lab`, `metro_exchange`, `motor_pool`, `music_venue`, `nightclub`, `office`, `outerwear_shop`, `outfitter`, `pawn_shop`, `pharmacy`, `pool_hall`, `prison`, `recruitment_office`, `recycling_plant`, `restaurant`, `salon`, `server_hub`, `service_station`, `shoe_shop`, `soup_kitchen`, `street_kitchen`, `supply_bunker`, `surplus_store`, `tattoo_parlor`, `tavern`, `tenement`, `theater`, `thrift_store`, `tool_depot`, `top_shop`, `tower`, `warehouse`

Water values mean:

- `none`: no profile-added water.
- `low`: sparse outdoor water.
- `medium`: narrow water bands or canal-like edges.
- `high`: wider waterfront-like local water.

Profile water is placed only on safe outdoor cells and avoids buildings, returns, doors, and roads.
