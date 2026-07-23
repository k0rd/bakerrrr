# Custom Content

Custom content is loaded once when a run starts. It can add consumable-style items, optional world-profile styles that bias new chunks, room curiosity flavor, and optional Pygame UI themes. Existing built-in content stays in the game.

Copy JSON files into these live folders:

```bash
config/custom_content/items/
config/custom_content/world_profiles/
config/custom_content/room_curiosity_flavors/
config/custom_content/ui_themes/
```

Copy-ready examples are included here:

```bash
PLAYER_GUIDE/examples/custom_content/items/morning_glory_seeds.json
PLAYER_GUIDE/examples/custom_content/world_profiles/canal_slums.json
PLAYER_GUIDE/examples/custom_content/ui_themes/coastal_glass.json
```

## Generated Rewards

Successful runs can write optional generated reward files under:

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

UI themes validate through the same custom-content loader and may become generated rewards later, but the current reward exporter does not create theme files yet.

The receipt and ledger prove that the files were earned from a BAKERRRR run. They are not required for ordinary custom-content loading, and editing a copy of a reward file just makes it normal player-authored custom content.

That distinction matters for post-game traces. Valid custom content without matching generated-reward receipts can still be played, but that run cannot create or receive generated rewards, failed-run bones, or run echoes. Generated reward files keep those systems eligible only when their matching receipt still verifies against the saved reward bundle.

Generated reward files are also good examples. You can inspect them to see the exact JSON shape the loader accepts.

## Load Rules

- The project will keep this file up-to-date when the specification changes. The loading process is strict.
- Invalid custom content blocks a new run before play starts. The game shows an in-game notice and also prints fix steps to stdout.
- To run without custom content, move the listed file out of `config/custom_content/` and start again.
- Valid hand-authored custom content can load, but if it does not have matching generated-reward receipts, post-game generated rewards, failed-run bones, and run echoes are disabled for that run.
- Generated reward files stay post-game eligible when the copied files match their receipt and the original saved reward bundle is still present under `saves/rewards/`.
- Item, world-profile, room-curiosity, and UI-theme files are all validated before play starts.
- Problems are shown in game before play continues or before startup exits.
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

`name`, `glyph`, `stack_max`, `tags`, `category`, `legal_status`, `effects`, `appearance_family`, `appearance_slots`, `identification_profile`, `substance_profile`, `lead_profile`, `object_profile`

This version does not add custom weapons, armor, containers, throwables, tools, scripts, or new building types.

`object_profile` is optional metadata for small, placeable world objects. It does not make an item appear in the world by itself. A game system has to place or consume the object before it matters.

Allowed `object_profile` fields:

`schema_version`, `family`, `silhouette`, `material`, `primary_color`, `accent_color`, `motif`, `condition`, `rarity`, `placeable`, `pickup_allowed`, `display_name`, `description`, `display_glyph`, `display_color`, `future_tags`

Allowed `object_profile.family` values:

`plants_pots`, `tokens_charms`, `tools_parts`, `textiles`, `paper_books`, `containers`, `light_ritual`, `personal_home`, `trade_work`, `nature_finds`, `medical_herbal`

Allowed `object_profile.material` values:

`ceramic`, `wood`, `brass`, `glass`, `cloth`, `paper`, `steel`, `tin`, `stone`, `shell`, `wax`, `herb`

Allowed `object_profile.motif` values:

`none`, `star`, `stripe`, `dot_ring`, `crescent`, `flower`, `key_mark`, `route_mark`, `slash`

Allowed `object_profile.condition` values:

`plain`, `chipped`, `polished`, `wrapped`, `dusty`, `repaired`, `cracked`

Allowed `object_profile.rarity` values:

`common`, `uncommon`, `rare`, `unique`

Placeable object-profile items must have `stack_max` set to `1`. Owner names, NPC ids, relationship labels, and "belongs to" fields are intentionally not accepted here; those meanings have to be learned through game systems, not leaked by the item file.

Allowed effect types:

`modify_need`, `extend_wakefulness`, `restore_hp`, `status`, `credits`, `add_ammo`

`extend_wakefulness` accepts numeric `hours`. It adds a bounded chemical wake reserve that postpones future sleep-pressure loss; it does not erase existing sleep debt.

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

`accessory_shop`, `apartment`, `arcade`, `armory`, `auto_garage`, `backroom_clinic`, `bank`, `bar`, `barbershop`, `barracks`, `biotech_clinic`, `bookshop`, `bottom_shop`, `bounty_office`, `brokerage`, `butcher_shop`, `casino`, `checkpoint`, `chop_shop`, `clothing_superstore`, `co_working_hub`, `cold_storage`, `command_center`, `comms_shop`, `contractor_office`, `corner_store`, `courier_office`, `courthouse`, `data_center`, `daycare`, `dress_shop`, `drone_shop`, `electronics_shop`, `employment_agency`, `factory`, `field_hospital`, `flophouse`, `freight_depot`, `gallery`, `gaming_hall`, `hair_studio`, `hardware_store`, `headwear_shop`, `herbalist_shop`, `hotel`, `house`, `jail`, `jewelry_shop`, `junk_market`, `karaoke_box`, `lab`, `laundromat`, `machine_shop`, `makeup_counter`, `media_lab`, `metro_exchange`, `motor_pool`, `music_venue`, `nightclub`, `office`, `outerwear_shop`, `outfitter`, `pawn_shop`, `pharmacy`, `pool_hall`, `prison`, `recruitment_office`, `recycling_plant`, `restaurant`, `salon`, `server_hub`, `service_station`, `shoe_shop`, `soup_kitchen`, `street_kitchen`, `supply_bunker`, `surplus_store`, `tattoo_parlor`, `tavern`, `tenement`, `theater`, `thrift_store`, `tool_depot`, `top_shop`, `tower`, `warehouse`, `wire_shop`

Some building ids are especially useful for service-facing custom profiles. For example, `bank`, `brokerage`, `office`, `employment_agency`, and `recruitment_office` can naturally support the in-game `business_management` Business desk service. Custom world profiles weight building types, not individual service ids, so use those building ids when you want more places where owned-business policy, hours, markup, and wage controls can appear.

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

## UI Theme Files

UI themes change the color roles used by the main Pygame modal frames. They do not change controls, fonts, layout, menu options, or gameplay. Curses and terminal-stable builds can ignore the richer theme geometry and keep their normal modal presentation.

```json
{
  "_meta": {
    "schema_version": 1
  },
  "coastal_glass": {
    "label": "Coastal Glass",
    "selection_weight": 2.0,
    "area_types": ["coastal"],
    "district_types": [],
    "context_tags": ["shore", "water"],
    "tokens": {
      "surface": "floor_coastal",
      "surface_alt": "terrain_water",
      "border": "terrain_water",
      "accent": "flora_flower_coral",
      "title": "vehicle_glass",
      "muted": "human_slate",
      "footer": "human_denim"
    }
  }
}
```

Allowed UI-theme fields:

`label`, `selection_weight`, `area_types`, `district_types`, `context_tags`, `tokens`

Allowed UI-theme token roles:

`surface`, `surface_alt`, `border`, `accent`, `title`, `body`, `muted`, `divider`, `selection`, `warning`, `footer`

Token values must be existing safe render color keys from the built-in appearance, world, and symbolic palettes, such as:

`building_edge`, `floor_coastal`, `terrain_water`, `flora_flower_coral`, `vehicle_glass`, `human_slate`, `human_denim`, `player`, `objective`, `default`

`area_types` and `district_types` use the same allowed values listed for world profiles. `context_tags` are simple lowercase tags such as `shore`, `water`, `forest`, `secure`, or `underground`.
