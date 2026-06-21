# Custom Content

Custom content is loaded once when a run starts. It can add consumable-style items and optional world-profile styles that bias new chunks. Existing built-in content stays in the game.

Copy JSON files into these live folders:

```bash
config/custom_content/items/
config/custom_content/world_profiles/
config/custom_content/room_curiosity_flavors/
```

Copy-ready examples are included here:

```bash
PLAYER_GUIDE/examples/custom_content/items/morning_glory_seeds.json
PLAYER_GUIDE/examples/custom_content/world_profiles/canal_slums.json
```

## Generated Rewards

Successful non-tutorial runs can write optional generated reward files under:

```bash
saves/rewards/
```

The first version writes one item file, one area profile file, one receipt, and one ledger row:

```bash
saves/rewards/items/
saves/rewards/world_profiles/
saves/rewards/receipts/
saves/rewards/earned_rewards.json
```

These files are not enabled automatically. To use a generated reward in a future run, copy the item JSON into `config/custom_content/items/` and the area profile JSON into `config/custom_content/world_profiles/` before starting a new run.

The receipt and ledger prove that the files were earned from a BAKERRRR run. They are not required for ordinary custom-content loading, and editing a copy of a reward file just makes it normal player-authored custom content.

Generated reward files are also good examples. You can inspect them to see the exact JSON shape the loader accepts.

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

`accessory_shop`, `apartment`, `arcade`, `armory`, `auto_garage`, `backroom_clinic`, `bank`, `bar`, `barbershop`, `barracks`, `biotech_clinic`, `bookshop`, `bottom_shop`, `bounty_office`, `brokerage`, `butcher_shop`, `casino`, `checkpoint`, `chop_shop`, `clothing_superstore`, `co_working_hub`, `cold_storage`, `command_center`, `contractor_office`, `corner_store`, `courier_office`, `courthouse`, `data_center`, `daycare`, `dress_shop`, `employment_agency`, `factory`, `field_hospital`, `flophouse`, `freight_depot`, `gallery`, `gaming_hall`, `hair_studio`, `hardware_store`, `headwear_shop`, `hotel`, `house`, `jail`, `jewelry_shop`, `junk_market`, `karaoke_box`, `lab`, `laundromat`, `machine_shop`, `makeup_counter`, `media_lab`, `metro_exchange`, `motor_pool`, `music_venue`, `nightclub`, `office`, `outerwear_shop`, `outfitter`, `pawn_shop`, `pharmacy`, `pool_hall`, `prison`, `recruitment_office`, `recycling_plant`, `restaurant`, `salon`, `server_hub`, `service_station`, `shoe_shop`, `soup_kitchen`, `street_kitchen`, `supply_bunker`, `surplus_store`, `tattoo_parlor`, `tavern`, `tenement`, `theater`, `thrift_store`, `tool_depot`, `top_shop`, `tower`, `warehouse`

Water values mean:

- `none`: no profile-added water.
- `low`: sparse outdoor water.
- `medium`: narrow water bands or canal-like edges.
- `high`: wider waterfront-like local water.

Profile water is placed only on safe outdoor cells and avoids buildings, returns, doors, and roads.

## Room Curiosity Flavor Files

Room curiosity flavors bias existing upstairs, backroom, and tucked-away room payoff families. They do not create brand-new NPC AI, loot scripts, businesses, or services. They can make an existing family show up in different known building/room contexts and give it a custom telegraph line.

```json
{
  "_meta": {
    "schema_version": 1
  },
  "quiet_counter_offices": {
    "label": "Quiet Counter Offices",
    "base_profile": "quiet_contact",
    "selection_weight": 2.0,
    "archetypes": ["corner_store"],
    "room_kinds": ["back_office"],
    "room_curiosity_signal": "A quiet knock pattern keeps returning to the back office."
  }
}
```

Allowed room-curiosity flavor fields:

`label`, `base_profile`, `selection_weight`, `archetypes`, `room_kinds`, `room_curiosity_signal`

Allowed `base_profile` values:

`afterhours_pusher`, `backroom_doctor`, `backroom_entrepreneur`, `backstage_worker`, `hotel_afterhours_guest`, `quiet_contact`, `records_keeper`, `stash_ledger`, `transit_staff_roamer`

Allowed `selection_weight` is `0.01` through `4.0`.

Allowed `room_kinds` values:

`archive`, `back_office`, `backstage`, `balcony`, `boardroom`, `clerk_office`, `evidence_lockup`, `executive_office`, `front_desk`, `green_room`, `guest_floor`, `guest_lounge`, `linen_closet`, `locker_wall`, `meeting_room`, `office`, `platform`, `quiet_room`, `records`, `records_office`, `records_room`, `screening_room`, `server_room`, `service_corridor`, `service_office`, `sound_booth`, `stock_room`, `storage`, `surveillance_room`, `ticketing`, `vip_lounge`

`archetypes` uses the same allowed building ids listed above for world profiles.
