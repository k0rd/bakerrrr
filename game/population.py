import random

from game.components import (
    AI,
    ArmorLoadout,
    Collider,
    CoverState,
    CreatureIdentity,
    Inventory,
    ItemUseProfile,
    JusticeProfile,
    MovementThrottle,
    NoiseProfile,
    NPCMemory,
    NPCNeeds,
    NPCRoutine,
    NPCSocial,
    NPCTraits,
    NPCWill,
    Occupation,
    Position,
    PropertyKnowledge,
    PropertyPortfolio,
    Render,
    SkillProfile,
    StatusEffects,
    Vitality,
    WeaponLoadout,
    WeaponUseProfile,
    SuppressionState,
    WildlifeBehavior,
)
from game.economy import chunk_economy_profile, pick_career_for_workplace
from game.items import ITEM_CATALOG, loot_table_for_property, roll_loot
from game.npc_names import generate_human_personal_name, human_descriptor
from game.organizations import ensure_property_organization, sync_actor_organization_affiliations
from game.property_access import property_is_open, property_is_public, property_is_storefront, world_hour
from game.skills import seed_skill_profile
from game.weapons import roll_weapon_instance


RESIDENTIAL_ARCHETYPES = {
    "apartment",
    "house",
    "tenement",
    "hotel",
    "ranger_hut",
    "ruin_shelter",
    "field_camp",
    "survey_post",
    "beacon_house",
}
MEDICAL_ARCHETYPES = {
    "backroom_clinic",
    "pharmacy",
    "biotech_clinic",
    "field_hospital",
    "tide_station",
    "herbalist_camp",
}
SECURITY_ARCHETYPES = {
    "checkpoint",
    "armory",
    "barracks",
    "courthouse",
    "command_center",
    "motor_pool",
    "coast_watch",
    "firewatch_tower",
    "inspection_shed",
    "recruitment_office",
    "supply_bunker",
}
INDUSTRIAL_ARCHETYPES = {
    "warehouse",
    "factory",
    "machine_shop",
    "recycling_plant",
    "auto_garage",
    "freight_depot",
    "server_hub",
    "data_center",
    "lab",
    "pump_house",
    "work_shed",
    "breaker_yard",
    "drydock_yard",
    "cold_storage",
}
SALVAGE_ARCHETYPES = {
    "pawn_shop",
    "chop_shop",
    "junk_market",
    "salvage_camp",
    "breaker_yard",
    "drydock_yard",
}
NIGHTLIFE_ARCHETYPES = {
    "nightclub",
    "bar",
    "music_venue",
    "gaming_hall",
    "arcade",
    "theater",
    "karaoke_box",
    "pool_hall",
}
TRANSIT_ARCHETYPES = {
    "metro_exchange",
    "relay_post",
    "roadhouse",
    "dock_shack",
    "ferry_post",
    "lookout_post",
    "truck_stop",
    "courier_office",
}
STOREFRONT_ARCHETYPES = {
    "bait_shop",
    "corner_store",
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
    "theater",
    "music_venue",
    "gaming_hall",
    "truck_stop",
    "tool_depot",
    "bookshop",
    "hardware_store",
    "gallery",
    "flophouse",
    "street_kitchen",
    "karaoke_box",
    "pool_hall",
}
LARGE_STAFF_ARCHETYPES = {
    "hotel",
    "warehouse",
    "factory",
    "nightclub",
    "music_venue",
    "gaming_hall",
    "metro_exchange",
    "field_hospital",
    "freight_depot",
    "bank",
    "cold_storage",
    "brokerage",
}
VERTICAL_WORK_ARCHETYPES = {
    "bank",
    "brokerage",
    "co_working_hub",
    "courthouse",
    "data_center",
    "field_hospital",
    "hotel",
    "lab",
    "metro_exchange",
    "office",
    "server_hub",
    "tower",
}
SECURE_ROOM_KINDS = {
    "vault",
    "secure_storage",
    "secure_cage",
    "security_room",
    "count_room",
    "cash_cage",
    "surveillance_room",
    "holding",
    "armored_store",
    "cold_backup",
    "server_room",
    "signals_room",
    "control_room",
    "control_booth",
    "noc",
}
ADMIN_ROOM_KINDS = {
    "office",
    "back_office",
    "front_office",
    "executive_office",
    "executive_suite",
    "manager_office",
    "meeting_room",
    "conference",
    "records",
    "records_room",
    "records_office",
    "dispatch",
    "dispatch_desk",
    "briefing_room",
    "reception",
    "lobby",
    "front_counter",
    "service_counter",
}
MEDICAL_ROOM_KINDS = {
    "exam",
    "treatment_room",
    "testing_lab",
    "triage",
    "recovery",
    "dispensary",
    "intake",
    "surgery",
    "storage",
    "cold_storage",
}
WORKROOM_KINDS = {
    "tool_crib",
    "parts",
    "parts_room",
    "parts_store",
    "stock_room",
    "stock_rack",
    "repair_bench",
    "maintenance",
    "service_bay",
    "shop_floor",
    "assembly",
    "assembly_line",
    "sorting_floor",
    "loading_bay",
    "loading_lane",
    "receiving",
    "storage",
    "power_room",
    "racks",
}
FRONT_ROOM_KINDS = {
    "entry",
    "entrance",
    "lobby",
    "reception",
    "waiting",
    "foyer",
    "concourse",
    "public_hall",
    "counter",
    "front_counter",
    "host_desk",
    "service_counter",
    "showroom",
    "sales",
    "gaming_floor",
    "main_floor",
    "dining",
    "seating",
    "common_room",
}
HOSPITALITY_ROOM_KINDS = {
    "bar",
    "bar_top",
    "booth_row",
    "vip_lounge",
    "green_room",
    "commons",
    "kitchen",
    "prep_kitchen",
    "kitchenette",
    "breakroom",
    "reading_nook",
    "guest_floor",
}
ROUND_CLOCK_ARCHETYPES = {
    "checkpoint",
    "armory",
    "barracks",
    "backroom_clinic",
    "hotel",
    "server_hub",
    "data_center",
    "field_hospital",
    "relay_post",
    "ferry_post",
    "beacon_house",
    "flophouse",
}
DAY_SHIFT_WINDOWS = ((7, 15), (8, 16), (9, 17), (10, 18))
EARLY_SHIFT_WINDOWS = ((5, 13), (6, 14), (7, 15), (8, 16))
LATE_SHIFT_WINDOWS = ((12, 20), (14, 22), (15, 23), (16, 0))
NIGHT_SHIFT_WINDOWS = ((17, 1), (18, 2), (20, 4), (22, 6))
ROUND_CLOCK_SHIFT_WINDOWS = ((6, 14), (14, 22), (22, 6))

WILDLIFE_COUNT_RANGE_BY_AREA = {
    "city": (1, 2),
    "frontier": (1, 3),
    "wilderness": (2, 4),
    "coastal": (2, 4),
}

AMBIENT_CREATURE_PROFILES = (
    {
        "id": "stray_dog",
        "taxonomy_class": "canine",
        "species": "canis lupus familiaris",
        "common_names": ("stray dog", "yard dog", "feral dog"),
        "areas": {"city": 1.9, "frontier": 1.6, "coastal": 1.0},
        "districts": {"residential": 0.35, "slums": 0.65, "industrial": 0.2},
        "terrains": {"urban": 0.35, "scrub": 0.2, "shore": 0.12},
        "spawn_zones": ("street", "frontage", "perimeter"),
        "archetypes": ("house", "tenement", "roadhouse", "truck_stop", "field_camp", "dock_shack"),
        "color": "canine",
        "max_hp": (30, 42),
        "speed": (0.92, 1.16),
        "noise_radius": 3,
    },
    {
        "id": "alley_pigeon",
        "taxonomy_class": "avian",
        "species": "columba livia",
        "common_names": ("pigeon", "alley pigeon", "roof pigeon"),
        "areas": {"city": 2.0, "frontier": 0.4, "coastal": 0.6},
        "districts": {"downtown": 0.5, "industrial": 0.32, "entertainment": 0.24},
        "terrains": {"urban": 0.38, "park": 0.3, "shore": 0.1},
        "spawn_zones": ("frontage", "street", "perimeter"),
        "archetypes": ("corner_store", "restaurant", "bar", "metro_exchange", "relay_post", "dock_shack"),
        "color": "avian",
        "max_hp": (16, 24),
        "speed": (1.0, 1.26),
        "noise_radius": 2,
    },
    {
        "id": "sewer_rat",
        "taxonomy_class": "rodent",
        "species": "rattus norvegicus",
        "common_names": ("sewer rat", "dock rat", "yard rat"),
        "areas": {"city": 1.8, "frontier": 0.9, "coastal": 1.4},
        "districts": {"industrial": 0.6, "slums": 0.75, "entertainment": 0.22},
        "terrains": {"urban": 0.2, "shore": 0.2, "ruins": 0.24},
        "spawn_zones": ("perimeter", "street", "frontage"),
        "archetypes": ("warehouse", "factory", "junk_market", "salvage_camp", "dock_shack", "drydock_yard"),
        "color": "rodent",
        "max_hp": (14, 22),
        "speed": (1.02, 1.28),
        "noise_radius": 2,
    },
    {
        "id": "roach_swarm",
        "taxonomy_class": "insect",
        "species": "blattodea urbanus",
        "common_names": ("roach swarm", "wall roaches", "trash roaches"),
        "areas": {"city": 1.7, "frontier": 0.55, "coastal": 0.9},
        "districts": {"industrial": 0.55, "slums": 0.62, "entertainment": 0.28},
        "terrains": {"urban": 0.22, "ruins": 0.26, "marsh": 0.14},
        "spawn_zones": ("perimeter", "frontage", "street"),
        "archetypes": ("factory", "warehouse", "bar", "junk_market", "salvage_camp", "breaker_yard"),
        "color": "insect",
        "max_hp": (10, 16),
        "speed": (1.06, 1.34),
        "noise_radius": 1,
    },
    {
        "id": "crow",
        "taxonomy_class": "avian",
        "species": "corvus brachyrhynchos",
        "common_names": ("crow", "black crow", "yard crow"),
        "areas": {"frontier": 1.5, "wilderness": 1.3, "city": 0.7},
        "districts": {"industrial": 0.24, "residential": 0.14, "slums": 0.18},
        "terrains": {"scrub": 0.28, "plains": 0.18, "badlands": 0.24, "forest": 0.12},
        "spawn_zones": ("street", "perimeter", "frontage"),
        "archetypes": ("roadhouse", "truck_stop", "work_shed", "breaker_yard", "field_camp", "survey_post"),
        "color": "avian",
        "max_hp": (18, 28),
        "speed": (1.02, 1.24),
        "noise_radius": 2,
    },
    {
        "id": "dust_moth",
        "taxonomy_class": "insect",
        "species": "noctuidae ferrum",
        "common_names": ("dust moths", "lamp moths", "ash moths"),
        "areas": {"frontier": 1.45, "wilderness": 1.0, "city": 0.35},
        "districts": {"industrial": 0.1, "residential": 0.08},
        "terrains": {"scrub": 0.34, "badlands": 0.32, "dunes": 0.22, "hills": 0.14},
        "spawn_zones": ("street", "perimeter"),
        "archetypes": ("pump_house", "work_shed", "inspection_shed", "field_camp", "roadhouse"),
        "color": "insect",
        "max_hp": (10, 16),
        "speed": (1.08, 1.34),
        "noise_radius": 1,
    },
    {
        "id": "fence_lizard",
        "taxonomy_class": "reptile",
        "species": "sceloporus undulatus",
        "common_names": ("fence lizard", "scrub lizard", "wall lizard"),
        "areas": {"frontier": 1.38, "wilderness": 1.0, "coastal": 0.45},
        "districts": {"industrial": 0.06, "residential": 0.06},
        "terrains": {"scrub": 0.3, "badlands": 0.36, "hills": 0.18, "dunes": 0.14},
        "spawn_zones": ("street", "perimeter"),
        "archetypes": ("pump_house", "work_shed", "inspection_shed", "ranger_hut", "survey_post"),
        "color": "reptile",
        "max_hp": (12, 20),
        "speed": (0.98, 1.22),
        "noise_radius": 1,
    },
    {
        "id": "deer",
        "taxonomy_class": "ungulate",
        "species": "odocoileus virginianus",
        "common_names": ("deer", "doe", "young buck"),
        "areas": {"wilderness": 1.7, "frontier": 0.6},
        "districts": {},
        "terrains": {"forest": 0.4, "plains": 0.24, "hills": 0.18, "scrub": 0.12},
        "spawn_zones": ("street",),
        "archetypes": ("ranger_hut", "field_camp", "survey_post", "lookout_post"),
        "color": "ungulate",
        "max_hp": (34, 48),
        "speed": (0.96, 1.18),
        "noise_radius": 3,
    },
    {
        "id": "tree_frog",
        "taxonomy_class": "amphibian",
        "species": "hyla versicolor",
        "common_names": ("tree frog", "reed frog", "marsh frog"),
        "areas": {"wilderness": 1.4, "coastal": 0.9, "frontier": 0.45},
        "districts": {},
        "terrains": {"marsh": 0.46, "forest": 0.16, "shore": 0.12, "shoals": 0.12},
        "spawn_zones": ("street", "perimeter"),
        "archetypes": ("tide_station", "herbalist_camp", "weather_station", "field_camp"),
        "color": "amphibian",
        "max_hp": (10, 18),
        "speed": (0.92, 1.16),
        "noise_radius": 1,
    },
    {
        "id": "stag_beetle",
        "taxonomy_class": "insect",
        "species": "lucanus cervus",
        "common_names": ("stag beetle", "marsh beetle", "bark beetle"),
        "areas": {"wilderness": 1.28, "frontier": 0.72, "coastal": 0.54},
        "districts": {},
        "terrains": {"forest": 0.3, "marsh": 0.28, "hills": 0.12, "shore": 0.08},
        "spawn_zones": ("street", "perimeter"),
        "archetypes": ("ranger_hut", "field_camp", "herbalist_camp", "firewatch_tower"),
        "color": "insect",
        "max_hp": (10, 16),
        "speed": (0.96, 1.18),
        "noise_radius": 1,
    },
    {
        "id": "gull",
        "taxonomy_class": "avian",
        "species": "larus argentatus",
        "common_names": ("gull", "harbor gull", "pier gull"),
        "areas": {"coastal": 1.95, "city": 0.4, "wilderness": 0.2},
        "districts": {"industrial": 0.1, "downtown": 0.06},
        "terrains": {"shore": 0.44, "shoals": 0.4, "cliffs": 0.18, "lake": 0.16},
        "spawn_zones": ("street", "frontage", "perimeter"),
        "archetypes": ("dock_shack", "ferry_post", "net_house", "beacon_house", "bait_shop", "drydock_yard"),
        "color": "avian",
        "max_hp": (18, 28),
        "speed": (1.0, 1.24),
        "noise_radius": 2,
    },
    {
        "id": "shore_crab",
        "taxonomy_class": "other",
        "species": "brachyura littoralis",
        "common_names": ("shore crab", "dock crab", "tide crab"),
        "areas": {"coastal": 1.7, "wilderness": 0.22},
        "districts": {},
        "terrains": {"shore": 0.42, "shoals": 0.34, "salt_flats": 0.22, "lake": 0.08},
        "spawn_zones": ("street", "perimeter"),
        "archetypes": ("dock_shack", "ferry_post", "net_house", "bait_shop", "tide_station"),
        "color": "other",
        "max_hp": (12, 20),
        "speed": (0.86, 1.08),
        "noise_radius": 1,
    },
    {
        "id": "wharf_rat",
        "taxonomy_class": "rodent",
        "species": "rattus rattus",
        "common_names": ("wharf rat", "pier rat", "salt rat"),
        "areas": {"coastal": 1.6, "city": 0.8, "frontier": 0.3},
        "districts": {"industrial": 0.24, "slums": 0.2},
        "terrains": {"shore": 0.28, "shoals": 0.2, "salt_flats": 0.16},
        "spawn_zones": ("perimeter", "frontage", "street"),
        "archetypes": ("dock_shack", "drydock_yard", "bait_shop", "cold_storage", "net_house"),
        "color": "rodent",
        "max_hp": (14, 22),
        "speed": (1.04, 1.28),
        "noise_radius": 2,
    },
    {
        "id": "alley_possum",
        "taxonomy_class": "other",
        "species": "didelphis virginiana",
        "common_names": ("alley possum", "roof possum", "trash possum"),
        "areas": {"city": 1.0, "frontier": 0.95, "coastal": 0.55},
        "districts": {"residential": 0.18, "slums": 0.28, "industrial": 0.1},
        "terrains": {"urban": 0.16, "park": 0.18, "scrub": 0.14},
        "spawn_zones": ("street", "perimeter", "frontage"),
        "archetypes": ("house", "tenement", "field_camp", "truck_stop", "salvage_camp"),
        "color": "other",
        "max_hp": (18, 28),
        "speed": (0.92, 1.14),
        "noise_radius": 2,
    },
)


def ensure_chunk_population_state(sim):
    if not hasattr(sim, "chunk_ground_item_records"):
        sim.chunk_ground_item_records = {}
    if not hasattr(sim, "chunk_population_records"):
        sim.chunk_population_records = {}
    return sim.chunk_ground_item_records, sim.chunk_population_records


def _property_metadata(prop):
    if not isinstance(prop, dict):
        return {}
    metadata = prop.get("metadata")
    return metadata if isinstance(metadata, dict) else {}


def _property_archetype(prop):
    return str(_property_metadata(prop).get("archetype", "") or "").strip().lower()


def _property_entry(prop):
    metadata = _property_metadata(prop)
    entry = metadata.get("entry")
    if isinstance(entry, dict):
        try:
            return (
                int(entry.get("x")),
                int(entry.get("y")),
                int(entry.get("z", prop.get("z", 0))),
            )
        except (TypeError, ValueError):
            return None
    try:
        return (int(prop.get("x")), int(prop.get("y")), int(prop.get("z", 0)))
    except (TypeError, ValueError):
        return None


def _property_footprint(prop):
    footprint = _property_metadata(prop).get("footprint")
    return footprint if isinstance(footprint, dict) else {}


def _property_level_bounds(prop):
    metadata = _property_metadata(prop)
    try:
        base_z = int(prop.get("z", 0))
        floors = max(1, int(metadata.get("floors", 1)))
        basement_levels = max(0, int(metadata.get("basement_levels", 0)))
    except (TypeError, ValueError):
        return 0, 0
    return base_z - basement_levels, base_z + floors - 1


def _property_total_levels(prop):
    low_z, high_z = _property_level_bounds(prop)
    return max(1, (int(high_z) - int(low_z)) + 1)


def _hour_in_window(hour, start_hour, end_hour):
    hour = int(hour) % 24
    start_hour = int(start_hour) % 24
    end_hour = int(end_hour) % 24
    if start_hour == end_hour:
        return True
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    return hour >= start_hour or hour < end_hour


def _shift_window_for(archetype, role, rng):
    archetype = str(archetype or "").strip().lower()
    role = str(role or "").strip().lower()
    if role == "guard" or archetype in SECURITY_ARCHETYPES:
        return rng.choice(ROUND_CLOCK_SHIFT_WINDOWS)
    if archetype in NIGHTLIFE_ARCHETYPES:
        return rng.choice(NIGHT_SHIFT_WINDOWS)
    if archetype in ROUND_CLOCK_ARCHETYPES:
        return rng.choice(ROUND_CLOCK_SHIFT_WINDOWS)
    if archetype in TRANSIT_ARCHETYPES:
        return rng.choice(EARLY_SHIFT_WINDOWS + LATE_SHIFT_WINDOWS[:2])
    if archetype in {"restaurant", "corner_store", "laundromat", "daycare", "soup_kitchen", "street_kitchen", "tool_depot", "hardware_store", "bookshop"}:
        return rng.choice(EARLY_SHIFT_WINDOWS + DAY_SHIFT_WINDOWS)
    return rng.choice(DAY_SHIFT_WINDOWS)


def work_shift_active(sim, occupation=None, workplace_prop=None, hour=None, role=None):
    if hour is None:
        hour = world_hour(sim)
    hour = int(hour) % 24

    if occupation is not None:
        start = getattr(occupation, "shift_start", None)
        end = getattr(occupation, "shift_end", None)
        if start is not None and end is not None:
            return _hour_in_window(hour, start, end)

    open_state = property_is_open(sim, workplace_prop, hour=hour) if workplace_prop else None
    if open_state is not None:
        return bool(open_state)

    archetype = _property_archetype(workplace_prop)
    role = str(role or "").strip().lower()
    if role == "guard" or archetype in SECURITY_ARCHETYPES:
        return _hour_in_window(hour, 6, 22)
    if archetype in NIGHTLIFE_ARCHETYPES:
        return _hour_in_window(hour, 17, 3)
    if archetype in TRANSIT_ARCHETYPES:
        return _hour_in_window(hour, 6, 20)
    return _hour_in_window(hour, 8, 18)


def item_zone_for_property(prop, item_def):
    kind = str(prop.get("kind", "")).strip().lower()
    archetype = _property_archetype(prop)
    tags = {str(tag).strip().lower() for tag in item_def.get("tags", ()) if str(tag).strip()}

    if kind in {"fixture", "asset", "vehicle"}:
        return "street"
    if archetype in RESIDENTIAL_ARCHETYPES:
        if "token" in tags:
            return "entry"
        return "interior"
    if archetype in MEDICAL_ARCHETYPES:
        return "interior" if "medical" in tags else "entry"
    if archetype in SECURITY_ARCHETYPES:
        return "perimeter" if {"tool", "restricted"} & tags else "interior"
    if archetype in SALVAGE_ARCHETYPES or archetype in INDUSTRIAL_ARCHETYPES:
        return "interior" if "tool" in tags else "perimeter"
    if archetype in NIGHTLIFE_ARCHETYPES:
        return "frontage" if {"drink", "social", "stimulant", "token"} & tags else "interior"
    if archetype in TRANSIT_ARCHETYPES:
        return "entry" if "token" in tags else "frontage"
    if property_is_storefront(prop) or property_is_public(prop):
        if {"food", "drink", "token"} & tags:
            return "frontage"
        return "entry"
    return "entry"


def _spawn(sim, *components):
    eid = sim.ecs.create()
    position = None
    for component in components:
        sim.ecs.add(eid, component)
        if isinstance(component, Position):
            position = component
    if position is not None:
        sim.tilemap.add_entity(eid, position.x, position.y, position.z)
    return eid


def _give_item(sim, eid, item_id, quantity=1, owner_tag="npc"):
    inventory = sim.ecs.get(Inventory).get(eid)
    if not inventory:
        return False
    item_def = ITEM_CATALOG.get(item_id)
    if not item_def:
        return False
    added, _instance_id = inventory.add_item(
        item_id=item_id,
        quantity=int(max(1, quantity)),
        stack_max=item_def.get("stack_max", 1),
        instance_factory=sim.new_item_instance_id,
        owner_eid=eid,
        owner_tag=owner_tag,
        metadata={"ambient_spawn": True},
    )
    return bool(added)


def _bond_rank(kind):
    return {
        "family": 5,
        "partner": 4,
        "friend": 3,
        "coworker": 2,
        "neighbor": 1,
    }.get(str(kind or "").strip().lower(), 0)


def _set_bond(social, other_eid, kind, closeness, trust):
    existing = social.bonds.get(other_eid)
    new_rank = _bond_rank(kind)
    if existing:
        current_rank = _bond_rank(existing.get("kind"))
        if current_rank > new_rank:
            return False
        if (
            current_rank == new_rank
            and float(existing.get("closeness", 0.0)) >= float(closeness)
            and float(existing.get("trust", 0.0)) >= float(trust)
        ):
            return False
    social.add_bond(other_eid, kind=kind, closeness=closeness, trust=trust)
    return True


def _bond_pair(sim, left_eid, right_eid, *, kind, closeness, trust):
    if left_eid == right_eid:
        return False
    socials = sim.ecs.get(NPCSocial)
    left = socials.get(left_eid)
    right = socials.get(right_eid)
    if not left or not right:
        return False
    changed_left = _set_bond(left, right_eid, kind, closeness, trust)
    changed_right = _set_bond(right, left_eid, kind, closeness, trust)
    return bool(changed_left or changed_right)


def _surname_for_actor(sim, eid):
    identity = sim.ecs.get(CreatureIdentity).get(eid)
    if not identity:
        return ""
    personal_name = str(getattr(identity, "personal_name", "") or "").strip()
    if " " not in personal_name:
        return ""
    return personal_name.rsplit(" ", 1)[-1].strip().lower()


def _seed_chunk_social_bonds(sim, actor_contexts):
    home_groups = {}
    work_groups = {}
    home_positions = {}

    for eid, context in actor_contexts.items():
        home_id = str(context.get("home_property_id") or "").strip()
        work_id = str(context.get("work_property_id") or "").strip()
        if home_id:
            home_groups.setdefault(home_id, []).append(eid)
            home_positions[home_id] = context.get("home_anchor")
        if work_id:
            work_groups.setdefault(work_id, []).append(eid)

    for home_id, members in home_groups.items():
        members = sorted(set(int(eid) for eid in members))
        if len(members) < 2:
            continue
        for index, left_eid in enumerate(members):
            for right_eid in members[index + 1:]:
                rng = random.Random(f"{sim.seed}:home_bond:{home_id}:{left_eid}:{right_eid}")
                same_surname = bool(_surname_for_actor(sim, left_eid) and _surname_for_actor(sim, left_eid) == _surname_for_actor(sim, right_eid))
                if same_surname:
                    kind = "family"
                elif len(members) == 2 and rng.random() < 0.22:
                    kind = "partner"
                else:
                    kind = "friend"
                closeness = rng.uniform(0.7, 0.94) if kind in {"family", "partner"} else rng.uniform(0.58, 0.84)
                trust = rng.uniform(0.7, 0.93) if kind in {"family", "partner"} else rng.uniform(0.52, 0.8)
                _bond_pair(sim, left_eid, right_eid, kind=kind, closeness=closeness, trust=trust)

    for work_id, members in work_groups.items():
        members = sorted(set(int(eid) for eid in members))
        if len(members) < 2:
            continue
        for index, left_eid in enumerate(members):
            for right_eid in members[index + 1:]:
                rng = random.Random(f"{sim.seed}:work_bond:{work_id}:{left_eid}:{right_eid}")
                _bond_pair(
                    sim,
                    left_eid,
                    right_eid,
                    kind="coworker",
                    closeness=rng.uniform(0.4, 0.72),
                    trust=rng.uniform(0.42, 0.74),
                )

    home_ids = sorted(home_groups.keys())
    for index, home_id in enumerate(home_ids):
        anchor_a = home_positions.get(home_id)
        if not anchor_a:
            continue
        for other_home_id in home_ids[index + 1:]:
            anchor_b = home_positions.get(other_home_id)
            if not anchor_b:
                continue
            if int(anchor_a[2]) != int(anchor_b[2]):
                continue
            distance = abs(int(anchor_a[0]) - int(anchor_b[0])) + abs(int(anchor_a[1]) - int(anchor_b[1]))
            if distance > 8:
                continue
            rng = random.Random(f"{sim.seed}:neighbor_bond:{home_id}:{other_home_id}")
            if rng.random() > 0.42:
                continue
            left_members = sorted(set(int(eid) for eid in home_groups.get(home_id, ())))
            right_members = sorted(set(int(eid) for eid in home_groups.get(other_home_id, ())))
            if not left_members or not right_members:
                continue
            left_eid = rng.choice(left_members)
            right_eid = rng.choice(right_members)
            _bond_pair(
                sim,
                left_eid,
                right_eid,
                kind="neighbor",
                closeness=rng.uniform(0.34, 0.62),
                trust=rng.uniform(0.3, 0.56),
            )


def _equip_npc_weapon(sim, eid, rng, item_id):
    inventory = sim.ecs.get(Inventory).get(eid)
    loadout = sim.ecs.get(WeaponLoadout).get(eid)
    item_def = ITEM_CATALOG.get(item_id, {})
    weapon_id = str(item_def.get("weapon_id", "") or "").strip()
    if not inventory or not loadout or not weapon_id:
        return False
    added, instance_id = inventory.add_item(
        item_id=item_id,
        quantity=1,
        stack_max=int(max(1, item_def.get("stack_max", 1))),
        instance_factory=sim.new_item_instance_id,
        owner_eid=eid,
        owner_tag="npc",
        metadata={"ambient_spawn": True, "equipped": True},
    )
    if not added:
        return False
    instance = roll_weapon_instance(rng, weapon_id, named_chance=0.08)
    instance["inventory_instance_id"] = instance_id
    loadout.add_weapon(weapon_id, instance=instance)
    loadout.equip(weapon_id)
    return True


def _equip_npc_armor(sim, eid, item_id):
    inventory = sim.ecs.get(Inventory).get(eid)
    loadout = sim.ecs.get(ArmorLoadout).get(eid)
    item_def = ITEM_CATALOG.get(item_id, {})
    armor = item_def.get("armor") if isinstance(item_def.get("armor"), dict) else None
    if not inventory or not loadout or not armor:
        return False
    added, instance_id = inventory.add_item(
        item_id=item_id,
        quantity=1,
        stack_max=int(max(1, item_def.get("stack_max", 1))),
        instance_factory=sim.new_item_instance_id,
        owner_eid=eid,
        owner_tag="npc",
        metadata={"ambient_spawn": True, "equipped": True},
    )
    if not added:
        return False
    loadout.equip(
        instance_id=instance_id,
        item_id=item_id,
        name=str(item_def.get("name", item_id)).strip() or item_id,
        damage_reduction=float(armor.get("damage_reduction", 0.0)),
        slot=armor.get("slot", "body"),
    )
    return True


def _unique_positions(positions):
    seen = set()
    results = []
    for pos in positions:
        if not isinstance(pos, (list, tuple)) or len(pos) < 3:
            continue
        key = (int(pos[0]), int(pos[1]), int(pos[2]))
        if key in seen:
            continue
        seen.add(key)
        results.append(key)
    return results


def _inside_property(sim, prop, x, y, z):
    covered = sim.property_covering(x, y, z)
    return bool(covered and covered.get("id") == prop.get("id"))


def _walkable_inside_tiles(sim, prop):
    footprint = _property_footprint(prop)
    if not footprint:
        return []
    try:
        left = int(footprint.get("left"))
        right = int(footprint.get("right"))
        top = int(footprint.get("top"))
        bottom = int(footprint.get("bottom"))
    except (TypeError, ValueError):
        return []
    low_z, high_z = _property_level_bounds(prop)

    tiles = []
    for z in range(int(low_z), int(high_z) + 1):
        for y in range(top, bottom + 1):
            for x in range(left, right + 1):
                if not sim.tilemap.is_walkable(x, y, z):
                    continue
                if not _inside_property(sim, prop, x, y, z):
                    continue
                tiles.append((x, y, z))
    return tiles


def _adjacent_walkable(sim, x, y, z, radius=1):
    results = []
    radius = max(1, int(radius))
    for dist in range(1, radius + 1):
        for dx, dy in ((dist, 0), (-dist, 0), (0, dist), (0, -dist)):
            nx = int(x) + dx
            ny = int(y) + dy
            if sim.tilemap.is_walkable(nx, ny, z):
                results.append((nx, ny, z))
    return results


def _sorted_by_distance(positions, origin, reverse=False):
    if not origin:
        return list(positions)
    ox, oy, oz = origin
    return sorted(
        positions,
        key=lambda row: (abs(int(row[0]) - ox) + abs(int(row[1]) - oy) + (2 * abs(int(row[2]) - oz))),
        reverse=bool(reverse),
    )


def _tile_candidates_for_property(sim, prop, zone):
    zone = str(zone or "entry").strip().lower() or "entry"
    entry = _property_entry(prop)
    entry_key = tuple(int(v) for v in entry) if entry else None
    inside_tiles = _walkable_inside_tiles(sim, prop)
    near_inside = [tile for tile in _sorted_by_distance(inside_tiles, entry, reverse=False) if tile != entry_key]
    deep_inside = [tile for tile in _sorted_by_distance(inside_tiles, entry, reverse=True) if tile != entry_key]
    boundary_inside = []
    for tile in inside_tiles:
        x, y, z = tile
        if tile == entry_key:
            continue
        entry_dist = abs(x - entry[0]) + abs(y - entry[1]) if entry else 0
        if entry_dist <= 2:
            boundary_inside.append(tile)

    frontage = []
    if entry:
        for pos in _adjacent_walkable(sim, entry[0], entry[1], entry[2], radius=2):
            if _inside_property(sim, prop, pos[0], pos[1], pos[2]):
                continue
            frontage.append(pos)

    street = list(frontage)
    try:
        anchor = (int(prop.get("x", 0)), int(prop.get("y", 0)), int(prop.get("z", 0)))
    except (TypeError, ValueError):
        anchor = entry
    if anchor:
        for pos in _adjacent_walkable(sim, anchor[0], anchor[1], anchor[2], radius=2):
            if _inside_property(sim, prop, pos[0], pos[1], pos[2]):
                continue
            street.append(pos)

    def _within(limit, positions):
        if not entry:
            return list(positions)
        results = []
        for pos in positions:
            dist = abs(int(pos[0]) - entry[0]) + abs(int(pos[1]) - entry[1])
            if dist <= int(limit):
                results.append(pos)
        return results

    if zone == "interior":
        return _unique_positions(deep_inside + near_inside)
    if zone == "frontage":
        return _unique_positions(_within(4, frontage)[:6] + boundary_inside[:4] + _within(3, near_inside)[:4])
    if zone == "street":
        return _unique_positions(_within(5, street)[:8] + _within(4, frontage)[:4])
    if zone == "perimeter":
        return _unique_positions(boundary_inside[:8] + _within(4, frontage)[:4] + _within(3, near_inside)[:4])
    return _unique_positions(boundary_inside[:8] + _within(3, near_inside)[:6] + _within(4, frontage)[:2])


def _room_kind_at(sim, x, y, z):
    info = sim.structure_at(x, y, z) if hasattr(sim, "structure_at") else None
    if not isinstance(info, dict):
        return ""
    return str(info.get("room_kind", "") or "").strip().lower()


def _item_tile_weight(sim, prop, item_def, zone, pos):
    room_kind = _room_kind_at(sim, pos[0], pos[1], pos[2])
    tags = {str(tag).strip().lower() for tag in item_def.get("tags", ()) if str(tag).strip()}
    weight = 1.0

    if zone == "entry":
        if room_kind in FRONT_ROOM_KINDS:
            weight += 3.0
        elif room_kind:
            weight += 1.0
    elif zone == "interior":
        if room_kind and room_kind not in FRONT_ROOM_KINDS:
            weight += 0.5
        elif room_kind in FRONT_ROOM_KINDS:
            weight = max(0.35, weight - 0.45)

    if "medical" in tags and room_kind in MEDICAL_ROOM_KINDS:
        weight += 6.0
    if {"weapon", "restricted", "illegal"} & tags:
        if room_kind in SECURE_ROOM_KINDS:
            weight += 7.0
        elif room_kind in ADMIN_ROOM_KINDS:
            weight += 2.5
    if {"credential", "token", "key"} & tags:
        if room_kind in ADMIN_ROOM_KINDS:
            weight += 5.0
        elif room_kind in SECURE_ROOM_KINDS:
            weight += 2.5
    if "tool" in tags:
        if room_kind in WORKROOM_KINDS:
            weight += 5.0
        elif room_kind in SECURE_ROOM_KINDS:
            weight += 1.5
    if {"food", "drink", "social", "stimulant"} & tags and room_kind in HOSPITALITY_ROOM_KINDS:
        weight += 4.0

    archetype = _property_archetype(prop)
    if zone == "interior" and archetype in SECURITY_ARCHETYPES and room_kind in SECURE_ROOM_KINDS:
        weight += 1.5
    if zone == "interior" and archetype in MEDICAL_ARCHETYPES and room_kind in MEDICAL_ROOM_KINDS:
        weight += 1.5
    return max(0.1, float(weight))


def _pick_tile(sim, candidates, rng, allow_entities=False, weight_fn=None):
    filtered = []
    for x, y, z in candidates:
        if not sim.tilemap.is_walkable(x, y, z):
            continue
        if not allow_entities and sim.tilemap.entities_at(x, y, z):
            continue
        filtered.append((x, y, z))
    if not filtered:
        return None
    if callable(weight_fn):
        weighted = []
        for pos in filtered:
            try:
                weight = float(weight_fn(pos))
            except (TypeError, ValueError):
                weight = 1.0
            weighted.append((pos, max(0.0, weight)))
        picked = _weighted_choice(rng, weighted)
        if picked is not None:
            return picked
    return rng.choice(filtered)


def _chunk_descriptor(sim, chunk):
    chunk = chunk if isinstance(chunk, dict) else {}
    try:
        cx = int(chunk.get("cx", 0))
        cy = int(chunk.get("cy", 0))
    except (TypeError, ValueError):
        cx = 0
        cy = 0

    district = chunk.get("district") if isinstance(chunk.get("district"), dict) else {}
    world = getattr(sim, "world", None)
    descriptor = world.overworld_descriptor(cx, cy) if world is not None else {}
    descriptor = descriptor if isinstance(descriptor, dict) else {}

    area_type = str(district.get("area_type", descriptor.get("area_type", "city"))).strip().lower() or "city"
    district_type = str(district.get("district_type", descriptor.get("district_type", "unknown"))).strip().lower() or "unknown"
    terrain = str(descriptor.get("terrain", "urban" if area_type == "city" else "plains")).strip().lower()
    return {
        "cx": cx,
        "cy": cy,
        "area_type": area_type,
        "district_type": district_type,
        "terrain": terrain or ("urban" if area_type == "city" else "plains"),
    }


def _wildlife_target_count(descriptor, rng):
    area_type = str(descriptor.get("area_type", "city")).strip().lower() or "city"
    terrain = str(descriptor.get("terrain", "")).strip().lower()
    district_type = str(descriptor.get("district_type", "")).strip().lower()
    lo, hi = WILDLIFE_COUNT_RANGE_BY_AREA.get(area_type, (1, 2))
    if terrain in {"forest", "marsh", "shore", "shoals", "park", "scrub"}:
        hi += 1
    if area_type == "city" and district_type in {"slums", "industrial"}:
        hi += 1
    return int(max(0, rng.randint(int(lo), int(max(lo, hi)))))


def _creature_profile_weight(profile, descriptor):
    if not isinstance(profile, dict):
        return 0.0

    area_type = str(descriptor.get("area_type", "city")).strip().lower() or "city"
    district_type = str(descriptor.get("district_type", "")).strip().lower()
    terrain = str(descriptor.get("terrain", "")).strip().lower()

    areas = profile.get("areas") if isinstance(profile.get("areas"), dict) else {}
    weight = float(areas.get(area_type, 0.0))
    if weight <= 0.0:
        return 0.0

    districts = profile.get("districts") if isinstance(profile.get("districts"), dict) else {}
    terrains = profile.get("terrains") if isinstance(profile.get("terrains"), dict) else {}
    weight += float(districts.get(district_type, 0.0))
    weight += float(terrains.get(terrain, 0.0))
    return max(0.0, weight)


def _chunk_outdoor_tiles(sim, chunk, z=0):
    descriptor = _chunk_descriptor(sim, chunk)
    cx = int(descriptor["cx"])
    cy = int(descriptor["cy"])
    origin_x, origin_y = sim.chunk_origin(cx, cy)
    tiles = []
    min_x = int(origin_x) + 1
    max_x = int(origin_x) + int(sim.chunk_size) - 2
    min_y = int(origin_y) + 1
    max_y = int(origin_y) + int(sim.chunk_size) - 2

    for y in range(min_y, max_y + 1):
        for x in range(min_x, max_x + 1):
            if not sim.tilemap.is_walkable(x, y, z):
                continue
            covered = sim.property_covering(x, y, z)
            if covered and str(covered.get("kind", "building")).strip().lower() == "building":
                continue
            tiles.append((x, y, z))
    return _unique_positions(tiles)


def _nearby_walkable_tiles(sim, origin, *, radius=3, outside_only=False):
    if not isinstance(origin, (list, tuple)) or len(origin) < 3:
        return []
    ox, oy, oz = int(origin[0]), int(origin[1]), int(origin[2])
    tiles = []
    for dy in range(-int(radius), int(radius) + 1):
        for dx in range(-int(radius), int(radius) + 1):
            if dx == 0 and dy == 0:
                continue
            if max(abs(dx), abs(dy)) > int(radius):
                continue
            x = ox + dx
            y = oy + dy
            if not sim.tilemap.is_walkable(x, y, oz):
                continue
            if outside_only and sim.property_covering(x, y, oz):
                continue
            tiles.append((x, y, oz))
    return _unique_positions(tiles)


def _wildlife_anchor_properties(sim, property_records, profile):
    building_props = []
    profile_archetypes = {
        str(value).strip().lower()
        for value in profile.get("archetypes", ())
        if str(value).strip()
    }
    matched = []

    for record in property_records:
        prop = sim.properties.get(record.get("id"))
        if not prop:
            continue
        if str(prop.get("kind", "")).strip().lower() != "building":
            continue
        building_props.append(prop)
        if profile_archetypes and _property_archetype(prop) in profile_archetypes:
            matched.append(prop)

    if matched:
        return matched
    return building_props


def _wildlife_tile_candidates(sim, chunk, property_records, profile, outdoor_tiles):
    zones = tuple(profile.get("spawn_zones", ("street",))) or ("street",)
    props = _wildlife_anchor_properties(sim, property_records, profile)
    candidates = []
    for prop in props:
        for zone in zones:
            candidates.extend(_tile_candidates_for_property(sim, prop, zone))
    exterior_candidates = []
    for x, y, z in _unique_positions(candidates):
        covered = sim.property_covering(x, y, z)
        if covered and str(covered.get("kind", "building")).strip().lower() == "building":
            continue
        exterior_candidates.append((x, y, z))
    candidates = exterior_candidates
    if candidates:
        return candidates

    if outdoor_tiles:
        return list(outdoor_tiles)
    return _chunk_outdoor_tiles(sim, chunk)


def _loot_spawn_profile(prop, rng):
    kind = str(prop.get("kind", "")).strip().lower()
    archetype = _property_archetype(prop)
    total_levels = _property_total_levels(prop)
    metadata = _property_metadata(prop)
    if kind == "vehicle":
        return 0.0, 0
    if kind in {"fixture", "asset"}:
        chance = 0.16 if kind == "fixture" else 0.24
        return chance, 1

    chance = 0.64
    count = 1
    if archetype in RESIDENTIAL_ARCHETYPES:
        chance = 0.72
    elif archetype in STOREFRONT_ARCHETYPES or archetype in MEDICAL_ARCHETYPES or archetype in TRANSIT_ARCHETYPES:
        chance = 0.82
    elif archetype in INDUSTRIAL_ARCHETYPES or archetype in SALVAGE_ARCHETYPES or archetype in SECURITY_ARCHETYPES:
        chance = 0.74

    if archetype in LARGE_STAFF_ARCHETYPES and rng.random() < 0.34:
        count += 1
    elif rng.random() < 0.2:
        count += 1
    if total_levels > 1:
        chance += 0.05
        if rng.random() < 0.34:
            count += 1
    if int(metadata.get("basement_levels", 0) or 0) > 0:
        chance += 0.03
    return chance, count


def seed_chunk_items(sim, chunk, property_records):
    ground_records, _population_records = ensure_chunk_population_state(sim)
    key = (int(chunk.get("cx", 0)), int(chunk.get("cy", 0)))
    if key in ground_records:
        return len(ground_records[key])

    rng = random.Random(f"{sim.seed}:{key[0]}:{key[1]}:chunk_items")
    spawned = []
    for record in property_records:
        prop = sim.properties.get(record.get("id"))
        if not prop:
            continue
        chance, count = _loot_spawn_profile(prop, rng)
        if chance <= 0.0 or rng.random() > chance:
            continue
        table_key = loot_table_for_property(kind=record.get("kind"), archetype=record.get("archetype"))
        for item_id in roll_loot(rng, table_key=table_key, count=count):
            item_def = ITEM_CATALOG.get(item_id)
            if not item_def:
                continue
            zone = item_zone_for_property(prop, item_def)
            tile = _pick_tile(
                sim,
                _tile_candidates_for_property(sim, prop, zone),
                rng,
                allow_entities=True,
                weight_fn=lambda pos, _prop=prop, _item_def=item_def, _zone=zone: _item_tile_weight(sim, _prop, _item_def, _zone, pos),
            )
            if not tile:
                continue
            room_kind = _room_kind_at(sim, tile[0], tile[1], tile[2])
            ground_id = sim.register_ground_item(
                item_id=item_id,
                x=tile[0],
                y=tile[1],
                z=tile[2],
                quantity=1,
                owner_eid=None,
                owner_tag="city",
                metadata={
                    "source_property_id": prop.get("id"),
                    "chunk": key,
                    "placement_zone": zone,
                    "placement_room_kind": room_kind or None,
                },
            )
            spawned.append(ground_id)

    ground_records[key] = list(spawned)
    return len(spawned)


def _weighted_choice(rng, rows):
    total = 0.0
    weighted = []
    for value, weight in rows:
        try:
            weight = float(weight)
        except (TypeError, ValueError):
            continue
        if weight <= 0.0:
            continue
        total += weight
        weighted.append((value, weight))
    if not weighted:
        return None
    pick = rng.uniform(0.0, total)
    running = 0.0
    for value, weight in weighted:
        running += weight
        if pick <= running:
            return value
    return weighted[-1][0]


def _home_weight(prop):
    archetype = _property_archetype(prop)
    if archetype == "house":
        return 1.2
    if archetype == "apartment":
        return 1.0
    if archetype == "tenement":
        return 0.9
    return 0.7


def _spawn_zone_for_actor(role, prop, at_work):
    archetype = _property_archetype(prop)
    if not at_work:
        return "interior"
    if role == "guard" or archetype in SECURITY_ARCHETYPES:
        return "perimeter"
    if _property_total_levels(prop) > 1 and (archetype in LARGE_STAFF_ARCHETYPES or archetype in VERTICAL_WORK_ARCHETYPES):
        return "interior"
    if archetype in STOREFRONT_ARCHETYPES or archetype in TRANSIT_ARCHETYPES or property_is_public(prop):
        return "frontage"
    return "interior"


def human_max_hp_for_role(rng, role, workplace_prop=None):
    role = str(role or "").strip().lower()
    archetype = _property_archetype(workplace_prop)

    if role == "guard" or archetype in SECURITY_ARCHETYPES:
        lo, hi = 60, 74
    elif role == "thief":
        lo, hi = 50, 62
    elif role == "drunk":
        lo, hi = 46, 58
    elif role == "scout":
        lo, hi = 56, 68
    elif role == "worker" or archetype in INDUSTRIAL_ARCHETYPES or archetype in SALVAGE_ARCHETYPES:
        lo, hi = 54, 66
    else:
        lo, hi = 48, 60

    return int(rng.randint(lo, hi))


def _traits_for_role(rng, role):
    role = str(role or "").strip().lower()
    if role == "guard":
        return NPCTraits(
            bravery=rng.uniform(0.58, 0.86),
            empathy=rng.uniform(0.32, 0.62),
            loyalty=rng.uniform(0.55, 0.88),
            discipline=rng.uniform(0.68, 0.92),
        )
    if role == "thief":
        return NPCTraits(
            bravery=rng.uniform(0.38, 0.68),
            empathy=rng.uniform(0.18, 0.44),
            loyalty=rng.uniform(0.2, 0.54),
            discipline=rng.uniform(0.18, 0.58),
        )
    if role == "drunk":
        return NPCTraits(
            bravery=rng.uniform(0.16, 0.52),
            empathy=rng.uniform(0.34, 0.72),
            loyalty=rng.uniform(0.18, 0.48),
            discipline=rng.uniform(0.1, 0.32),
        )
    if role == "worker":
        return NPCTraits(
            bravery=rng.uniform(0.34, 0.66),
            empathy=rng.uniform(0.42, 0.76),
            loyalty=rng.uniform(0.38, 0.78),
            discipline=rng.uniform(0.46, 0.84),
        )
    return NPCTraits(
        bravery=rng.uniform(0.22, 0.56),
        empathy=rng.uniform(0.48, 0.86),
        loyalty=rng.uniform(0.28, 0.72),
        discipline=rng.uniform(0.24, 0.62),
    )


def _justice_for_role(rng, role, workplace_prop=None):
    archetype = _property_archetype(workplace_prop)
    if role == "guard" or archetype in SECURITY_ARCHETYPES:
        return JusticeProfile(
            enforce_all=bool(archetype in SECURITY_ARCHETYPES),
            justice=rng.uniform(0.62, 0.94),
            corruption=rng.uniform(0.02, 0.18),
            crime_sensitivity=rng.uniform(0.72, 0.98),
        )
    if archetype in MEDICAL_ARCHETYPES:
        return JusticeProfile(
            enforce_all=False,
            justice=rng.uniform(0.34, 0.62),
            corruption=rng.uniform(0.04, 0.16),
            crime_sensitivity=rng.uniform(0.42, 0.7),
        )
    if role == "thief":
        return JusticeProfile(
            enforce_all=False,
            justice=rng.uniform(0.02, 0.18),
            corruption=rng.uniform(0.28, 0.62),
            crime_sensitivity=rng.uniform(0.06, 0.24),
        )
    if role == "drunk":
        return JusticeProfile(
            enforce_all=False,
            justice=rng.uniform(0.04, 0.22),
            corruption=rng.uniform(0.12, 0.4),
            crime_sensitivity=rng.uniform(0.1, 0.32),
        )
    return JusticeProfile(
        enforce_all=False,
        justice=rng.uniform(0.14, 0.46),
        corruption=rng.uniform(0.02, 0.22),
        crime_sensitivity=rng.uniform(0.22, 0.58),
    )


def _item_use_profile_for(role, workplace_prop=None):
    archetype = _property_archetype(workplace_prop)
    if role == "guard":
        return ItemUseProfile(
            willingness=0.68,
            risk_tolerance=0.26,
            auto_use=True,
            cooldown_ticks=12,
            preferred_tags={"medical", "safety", "energy"},
            avoid_tags={"illegal"},
        )
    if archetype in MEDICAL_ARCHETYPES:
        return ItemUseProfile(
            willingness=0.66,
            risk_tolerance=0.18,
            auto_use=True,
            cooldown_ticks=11,
            preferred_tags={"medical", "safety"},
            avoid_tags={"illegal"},
        )
    if role == "thief":
        return ItemUseProfile(
            willingness=0.64,
            risk_tolerance=0.58,
            auto_use=True,
            cooldown_ticks=11,
            preferred_tags={"energy", "social", "medical", "tool"},
            avoid_tags=set(),
        )
    if role == "drunk":
        return ItemUseProfile(
            willingness=0.56,
            risk_tolerance=0.46,
            auto_use=True,
            cooldown_ticks=13,
            preferred_tags={"drink", "social", "energy"},
            avoid_tags={"restricted"},
        )
    if role == "worker":
        return ItemUseProfile(
            willingness=0.54,
            risk_tolerance=0.24,
            auto_use=True,
            cooldown_ticks=14,
            preferred_tags={"energy", "food", "drink", "medical"},
            avoid_tags={"illegal"},
        )
    return ItemUseProfile(
        willingness=0.46,
        risk_tolerance=0.18,
        auto_use=True,
        cooldown_ticks=15,
        preferred_tags={"food", "drink", "social", "medical"},
        avoid_tags={"illegal", "stimulant"},
    )


def _uniform_item_for_npc(role, workplace_prop=None, home_prop=None):
    archetype = _property_archetype(workplace_prop or home_prop)
    if role == "guard" or archetype in SECURITY_ARCHETYPES:
        return "security_jacket"
    if role == "worker" and (archetype in INDUSTRIAL_ARCHETYPES or archetype in SALVAGE_ARCHETYPES):
        return "worker_coverall"
    return None


def _inventory_pool_for(role, workplace_prop=None, home_prop=None):
    archetype = _property_archetype(workplace_prop or home_prop)
    if role == "guard" or archetype in SECURITY_ARCHETYPES:
        return (
            "med_gel",
            "caff_shot",
            "focus_inhaler",
            "city_pass_token",
            "micro_medkit",
            "field_dressing",
            "bandage_roll",
            "bottled_water",
            "battery_pack",
        )
    if role == "thief":
        return (
            "city_pass_token",
            "scratch_ticket",
            "burner_phone",
            "lockpick_kit",
            "glass_cutter",
            "hotwire_leads",
            "forged_badge",
            "smoke_tab",
            "caff_shot",
            "cheap_whiskey",
        )
    if role == "drunk":
        return (
            "spark_brew",
            "cheap_whiskey",
            "smoke_tab",
            "deck_of_cards",
            "scratch_ticket",
            "lucky_charm",
            "mint_strip",
            "bottled_water",
        )
    if archetype in MEDICAL_ARCHETYPES:
        return ("med_gel", "micro_medkit", "hydration_salts", "calm_patch", "trauma_foam", "field_dressing", "bandage_roll", "pain_blocker", "bottled_water")
    if archetype in SALVAGE_ARCHETYPES or archetype in INDUSTRIAL_ARCHETYPES:
        return ("street_ration", "protein_wrap", "caff_shot", "city_pass_token", "prybar", "glass_cutter", "energy_bar", "canteen_coffee", "battery_pack", "scrap_circuit", "pocket_multitool")
    if archetype in NIGHTLIFE_ARCHETYPES:
        return ("spark_brew", "cheap_whiskey", "caff_shot", "smoke_tab", "city_pass_token", "street_ration", "mint_strip", "deck_of_cards", "lucky_charm")
    if archetype in STOREFRONT_ARCHETYPES or archetype in TRANSIT_ARCHETYPES:
        return ("street_ration", "protein_wrap", "spark_brew", "city_pass_token", "transit_daypass", "scratch_ticket", "energy_bar", "bottled_water", "meal_voucher", "mint_strip")
    return ("street_ration", "protein_wrap", "spark_brew", "calm_patch", "city_pass_token", "scratch_ticket", "energy_bar", "bottled_water", "meal_voucher", "lucky_charm")


def _weapon_use_profile_for(role):
    role = str(role or "").strip().lower()
    if role == "guard":
        return WeaponUseProfile(
            aggression=0.72,
            aim_bias=0.68,
            min_range=1,
            max_range=10,
            cooldown_jitter=1,
            allow_explosives=False,
        )
    if role == "thief":
        return WeaponUseProfile(
            aggression=0.58,
            aim_bias=0.62,
            min_range=1,
            max_range=8,
            cooldown_jitter=1,
            allow_explosives=False,
        )
    if role == "worker":
        return WeaponUseProfile(
            aggression=0.44,
            aim_bias=0.58,
            min_range=1,
            max_range=9,
            cooldown_jitter=1,
            allow_explosives=False,
        )
    if role == "drunk":
        return WeaponUseProfile(
            aggression=0.3,
            aim_bias=0.45,
            min_range=1,
            max_range=6,
            cooldown_jitter=2,
            allow_explosives=False,
        )
    return WeaponUseProfile(
        aggression=0.22,
        aim_bias=0.54,
        min_range=1,
        max_range=9,
        cooldown_jitter=1,
        allow_explosives=False,
    )


def _gear_pool_for(role, workplace_prop=None, home_prop=None):
    archetype = _property_archetype(workplace_prop or home_prop)
    if role == "guard" or archetype in SECURITY_ARCHETYPES:
        return {
            "weapon_chance": 0.78,
            "weapon_pool": (
                ("service_pistol", 28),
                ("rust_revolver", 18),
                ("compact_smg", 16),
                ("patrol_carbine", 12),
                ("alley_shotgun", 8),
            ),
            "armor_chance": 0.72,
            "armor_pool": (
                ("security_vest", 28),
                ("riot_plates", 14),
                ("courier_mesh", 8),
            ),
        }
    if role == "thief":
        return {
            "weapon_chance": 0.42,
            "weapon_pool": (
                ("holdout_pistol", 24),
                ("rust_revolver", 18),
                ("machine_pistol", 10),
                ("service_pistol", 8),
            ),
            "armor_chance": 0.24,
            "armor_pool": (
                ("courier_mesh", 18),
                ("padded_jacket", 14),
                ("security_vest", 8),
            ),
        }
    if role == "drunk":
        return {
            "weapon_chance": 0.08,
            "weapon_pool": (
                ("holdout_pistol", 14),
                ("rust_revolver", 8),
            ),
            "armor_chance": 0.06,
            "armor_pool": (
                ("padded_jacket", 18),
                ("courier_mesh", 8),
            ),
        }
    if archetype in SALVAGE_ARCHETYPES or archetype in NIGHTLIFE_ARCHETYPES:
        return {
            "weapon_chance": 0.2,
            "weapon_pool": (
                ("holdout_pistol", 18),
                ("rust_revolver", 14),
                ("alley_shotgun", 8),
            ),
            "armor_chance": 0.18,
            "armor_pool": (
                ("padded_jacket", 18),
                ("courier_mesh", 10),
            ),
        }
    if role == "worker" or archetype in INDUSTRIAL_ARCHETYPES:
        return {
            "weapon_chance": 0.12,
            "weapon_pool": (
                ("holdout_pistol", 12),
                ("rust_revolver", 10),
            ),
            "armor_chance": 0.16,
            "armor_pool": (
                ("courier_mesh", 12),
                ("padded_jacket", 16),
            ),
        }
    return {
        "weapon_chance": 0.04,
        "weapon_pool": (
            ("holdout_pistol", 10),
        ),
        "armor_chance": 0.08,
        "armor_pool": (
            ("courier_mesh", 10),
            ("padded_jacket", 8),
        ),
    }


def _seed_npc_gear(sim, eid, rng, role, workplace_prop=None, home_prop=None):
    profile = _gear_pool_for(role, workplace_prop=workplace_prop, home_prop=home_prop)
    if rng.random() < float(profile.get("weapon_chance", 0.0)):
        item_id = _weighted_choice(rng, profile.get("weapon_pool", ()))
        if item_id:
            gear_rng = random.Random(f"{sim.seed}:ambient_weapon:{eid}:{item_id}")
            _equip_npc_weapon(sim, eid, gear_rng, item_id)
    if rng.random() < float(profile.get("armor_chance", 0.0)):
        item_id = _weighted_choice(rng, profile.get("armor_pool", ()))
        if item_id:
            _equip_npc_armor(sim, eid, item_id)


def _seed_npc_inventory(sim, eid, rng, role, workplace_prop=None, home_prop=None):
    uniform_item_id = _uniform_item_for_npc(role, workplace_prop=workplace_prop, home_prop=home_prop)
    if uniform_item_id in ITEM_CATALOG:
        _give_item(sim, eid, uniform_item_id, quantity=1)
    pool = [item_id for item_id in _inventory_pool_for(role, workplace_prop=workplace_prop, home_prop=home_prop) if item_id in ITEM_CATALOG]
    if not pool:
        return
    _give_item(sim, eid, rng.choice(pool), quantity=1)
    if rng.random() < 0.28:
        _give_item(sim, eid, rng.choice(pool), quantity=1)
    if role in {"thief", "drunk"} and rng.random() < 0.42:
        _give_item(sim, eid, rng.choice(pool), quantity=1)


def _chaotic_role_for_resident(rng, area_type, home_prop=None, workplace_prop=None, current_role="civilian"):
    current_role = str(current_role or "civilian").strip().lower() or "civilian"
    if current_role == "guard":
        return current_role

    archetypes = {
        _property_archetype(home_prop),
        _property_archetype(workplace_prop),
    }
    nightlife_bias = bool(archetypes & NIGHTLIFE_ARCHETYPES)
    salvage_bias = bool(archetypes & SALVAGE_ARCHETYPES)
    transit_bias = bool(archetypes & TRANSIT_ARCHETYPES)

    drunk_chance = 0.05
    thief_chance = 0.04
    if area_type == "city":
        drunk_chance += 0.03
        thief_chance += 0.03
    if nightlife_bias:
        drunk_chance += 0.12
        thief_chance += 0.04
    if salvage_bias or transit_bias:
        thief_chance += 0.1
    if workplace_prop is None:
        drunk_chance += 0.04
        thief_chance += 0.02

    roll = rng.random()
    if roll < thief_chance:
        return "thief"
    if roll < thief_chance + drunk_chance:
        return "drunk"
    return current_role


def _spawn_human(
    sim,
    rng,
    role,
    position,
    career=None,
    workplace=None,
    home=None,
    work=None,
    shift_window=None,
    workplace_prop=None,
    home_prop=None,
    personal_name=None,
):
    role = str(role or "civilian").strip().lower() or "civilian"
    glyph = {
        "guard": "G",
        "worker": "W",
        "thief": "T",
        "drunk": "D",
    }.get(role, "C")
    personal_name = personal_name or generate_human_personal_name(sim, rng)
    needs = NPCNeeds(
        energy=rng.uniform(62.0, 88.0),
        safety=rng.uniform(58.0, 86.0),
        social=rng.uniform(52.0, 84.0),
    )
    shift_start = None
    shift_end = None
    if isinstance(shift_window, (list, tuple)) and len(shift_window) >= 2:
        shift_start = int(shift_window[0]) % 24
        shift_end = int(shift_window[1]) % 24

    eid = _spawn(
        sim,
        Position(*position),
        Render(glyph),
        CreatureIdentity(
            taxonomy_class="hominid",
            species="homo sapiens",
            creature_type="human",
            common_name=human_descriptor(role, career),
            personal_name=personal_name,
        ),
        AI(role),
        MovementThrottle(
            default_cooldown=2,
            state_cooldowns={"patrolling": 2, "resting": 3, "seeking_safety": 2},
            speed_multiplier=round(rng.uniform(0.82, 1.18), 2),
        ),
        Collider(blocks=True),
        Occupation(
            career=str(career or "resident").strip().lower().replace(" ", "_"),
            workplace=workplace,
            shift_start=shift_start,
            shift_end=shift_end,
        ) if career else Occupation(career="resident", workplace=None),
        needs,
        _traits_for_role(rng, role),
        NPCWill(),
        NPCMemory(),
        NPCSocial(),
        Inventory(capacity=8 if role == "thief" else (6 if role in {"civilian", "drunk"} else 7)),
        StatusEffects(),
        Vitality(max_hp=human_max_hp_for_role(rng, role, workplace_prop=workplace_prop)),
        ArmorLoadout(),
        WeaponLoadout(),
        _weapon_use_profile_for(role),
        CoverState(),
        SuppressionState(),
        _item_use_profile_for(role, workplace_prop=workplace_prop),
        NPCRoutine(home=home, work=work),
        PropertyKnowledge(),
        PropertyPortfolio(),
        _justice_for_role(rng, role, workplace_prop=workplace_prop),
        seed_skill_profile(
            random.Random(
                f"{sim.seed}:chunk_human_skill:{position[0]}:{position[1]}:{position[2]}:{role}:{career or 'resident'}:{personal_name}"
            ),
            role=role,
            career=career,
            jitter=0.28,
        ),
    )
    sync_actor_organization_affiliations(sim, eid)
    _seed_npc_inventory(sim, eid, rng, role, workplace_prop=workplace_prop, home_prop=home_prop)
    _seed_npc_gear(sim, eid, rng, role, workplace_prop=workplace_prop, home_prop=home_prop)
    return eid


def _wildlife_behavior_for_profile(profile):
    profile = profile if isinstance(profile, dict) else {}
    taxonomy = str(profile.get("taxonomy_class", "other")).strip().lower() or "other"
    profile_id = str(profile.get("id", "")).strip().lower()

    defaults = {
        "canine": {"home_radius": 6, "flee_radius": 7, "flock_radius": 4, "flocking": True, "activity_period": "day", "rest_bias": 0.3},
        "avian": {"home_radius": 7, "flee_radius": 8, "flock_radius": 5, "flocking": True, "activity_period": "day", "rest_bias": 0.2},
        "rodent": {"home_radius": 4, "flee_radius": 5, "flock_radius": 3, "flocking": True, "activity_period": "night", "rest_bias": 0.28},
        "insect": {"home_radius": 3, "flee_radius": 4, "flock_radius": 3, "flocking": False, "activity_period": "any", "rest_bias": 0.18},
        "reptile": {"home_radius": 3, "flee_radius": 4, "flock_radius": 2, "flocking": False, "activity_period": "day", "rest_bias": 0.42},
        "amphibian": {"home_radius": 3, "flee_radius": 4, "flock_radius": 2, "flocking": False, "activity_period": "night", "rest_bias": 0.38},
        "ungulate": {"home_radius": 7, "flee_radius": 8, "flock_radius": 5, "flocking": True, "activity_period": "day", "rest_bias": 0.26},
        "feline": {"home_radius": 5, "flee_radius": 6, "flock_radius": 3, "flocking": False, "activity_period": "day", "rest_bias": 0.46},
        "other": {"home_radius": 4, "flee_radius": 5, "flock_radius": 3, "flocking": False, "activity_period": "any", "rest_bias": 0.34},
    }
    behavior = dict(defaults.get(taxonomy, defaults["other"]))

    if profile_id in {"roach_swarm", "dust_moth"}:
        behavior.update({"flocking": True, "activity_period": "night"})
    elif profile_id in {"shore_crab"}:
        behavior.update({"home_radius": 3, "flee_radius": 4, "activity_period": "crepuscular", "rest_bias": 0.36})
    elif profile_id in {"alley_possum"}:
        behavior.update({"activity_period": "night", "home_radius": 4, "flee_radius": 5, "rest_bias": 0.4})

    for key in ("home_radius", "flee_radius", "flock_radius", "flocking", "activity_period", "rest_bias"):
        if key in profile:
            behavior[key] = profile[key]
    return WildlifeBehavior(**behavior)


def _spawn_wildlife(sim, rng, profile, position):
    taxonomy = str(profile.get("taxonomy_class", "other")).strip().lower() or "other"
    common_names = tuple(
        str(value).strip()
        for value in profile.get("common_names", ())
        if str(value).strip()
    ) or ("creature",)
    common_name = rng.choice(common_names)
    species = str(profile.get("species", "unknown species")).strip().lower() or "unknown species"
    color = str(profile.get("color", taxonomy)).strip().lower() or taxonomy
    hp_lo, hp_hi = profile.get("max_hp", (12, 20))
    speed_lo, speed_hi = profile.get("speed", (0.9, 1.1))
    try:
        noise_radius = int(profile.get("noise_radius", 2))
    except (TypeError, ValueError):
        noise_radius = 2

    home = (int(position[0]), int(position[1]), int(position[2]))
    nearby = _nearby_walkable_tiles(sim, home, radius=3, outside_only=True)
    patrol_target = rng.choice(nearby) if nearby else home
    max_hp = int(rng.randint(int(hp_lo), int(max(hp_lo, hp_hi))))
    speed = round(rng.uniform(float(speed_lo), float(speed_hi)), 2)
    behavior = _wildlife_behavior_for_profile(profile)

    eid = _spawn(
        sim,
        Position(*home),
        Render(CreatureIdentity.GLYPH_BY_TAXONOMY.get(taxonomy, "O"), color=color),
        CreatureIdentity(
            taxonomy_class=taxonomy,
            species=species,
            creature_type="animal",
            common_name=common_name,
        ),
        AI("wildlife"),
        MovementThrottle(
            default_cooldown=3,
            state_cooldowns={"patrolling": 3, "resting": 4, "seeking_safety": 2},
            speed_multiplier=speed,
        ),
        Collider(blocks=True),
        NoiseProfile(move_radius=max(1, noise_radius)),
        NPCNeeds(
            energy=rng.uniform(68.0, 92.0),
            safety=rng.uniform(54.0, 82.0),
            social=rng.uniform(28.0, 62.0),
        ),
        NPCWill(),
        StatusEffects(),
        Vitality(max_hp=max(6, max_hp)),
        CoverState(),
        ItemUseProfile(
            willingness=0.0,
            risk_tolerance=0.08,
            auto_use=False,
            cooldown_ticks=30,
        ),
        NPCRoutine(home=home, work=None),
        behavior,
    )

    ai = sim.ecs.get(AI).get(eid)
    if ai:
        if patrol_target != home:
            ai.state = "patrolling"
            ai.target = patrol_target
        else:
            ai.state = "resting"
            ai.target = home
    return eid


def _spawn_chunk_wildlife(sim, chunk, property_records, rng, *, target_count):
    descriptor = _chunk_descriptor(sim, chunk)
    outdoor_tiles = _chunk_outdoor_tiles(sim, chunk)
    if not outdoor_tiles:
        return []

    spawned = []
    profile_counts = {}
    max_attempts = max(4, int(target_count) * 5)

    for _ in range(max_attempts):
        if len(spawned) >= int(target_count):
            break

        weighted = []
        for profile in AMBIENT_CREATURE_PROFILES:
            weight = _creature_profile_weight(profile, descriptor)
            if weight <= 0.0:
                continue
            profile_id = str(profile.get("id", "creature"))
            repeat_penalty = 1.0 + (float(profile_counts.get(profile_id, 0)) * 0.9)
            weighted.append((profile, weight / repeat_penalty))

        profile = _weighted_choice(rng, weighted)
        if not profile:
            break

        candidates = _wildlife_tile_candidates(sim, chunk, property_records, profile, outdoor_tiles)
        tile = _pick_tile(sim, candidates, rng, allow_entities=False)
        if not tile:
            continue

        eid = _spawn_wildlife(sim, rng, profile, tile)
        spawned.append(eid)
        profile_id = str(profile.get("id", "creature"))
        profile_counts[profile_id] = int(profile_counts.get(profile_id, 0)) + 1

    return spawned


def _pick_home(rng, homes, loads, fallback_prop=None):
    weighted = []
    for prop in homes:
        property_id = prop.get("id")
        current = int(loads.get(property_id, 0))
        if current >= 2:
            continue
        weighted.append((prop, _home_weight(prop) / (1.0 + current)))
    choice = _weighted_choice(rng, weighted)
    if choice:
        loads[choice.get("id")] = int(loads.get(choice.get("id"), 0)) + 1
        return choice
    return fallback_prop


def _pick_workplace(rng, workplaces, loads, limit=2):
    weighted = []
    for prop in workplaces:
        property_id = prop.get("id")
        current = int(loads.get(property_id, 0))
        if current >= int(limit):
            continue
        weight = 1.0
        if _property_archetype(prop) in LARGE_STAFF_ARCHETYPES:
            weight += 0.4
        if property_is_public(prop) or property_is_storefront(prop):
            weight += 0.2
        weighted.append((prop, weight / (1.0 + current)))
    choice = _weighted_choice(rng, weighted)
    if choice:
        loads[choice.get("id")] = int(loads.get(choice.get("id"), 0)) + 1
    return choice


def _focus_position(prop):
    entry = _property_entry(prop)
    if entry:
        return entry
    try:
        return (int(prop.get("x")), int(prop.get("y")), int(prop.get("z", 0)))
    except (TypeError, ValueError):
        return None


def _property_kind_weight(prop):
    archetype = _property_archetype(prop)
    if archetype in SECURITY_ARCHETYPES:
        return 0.95
    if archetype in MEDICAL_ARCHETYPES or archetype in TRANSIT_ARCHETYPES:
        return 0.85
    if archetype in STOREFRONT_ARCHETYPES:
        return 0.78
    if archetype in INDUSTRIAL_ARCHETYPES or archetype in SALVAGE_ARCHETYPES:
        return 0.68
    return 0.42


def _business_founder_name(prop):
    metadata = _property_metadata(prop)
    founder_name = str(metadata.get("business_founder_name") or "").strip()
    if founder_name:
        return founder_name

    founder_first = str(metadata.get("business_founder_first_name") or "").strip()
    founder_last = str(metadata.get("business_founder_last_name") or "").strip()
    if founder_first and founder_last:
        return f"{founder_first} {founder_last}"
    return ""


def _business_founder_keyholder_chance(prop):
    metadata = _property_metadata(prop)
    configured = metadata.get("business_founder_keyholder_chance")
    if configured is not None:
        try:
            return max(0.0, min(1.0, float(configured)))
        except (TypeError, ValueError):
            pass
    return 0.26 if property_is_storefront(prop) else 0.14


def _business_founder_candidate(sim, prop, assigned_property_ids):
    if not isinstance(prop, dict):
        return ""

    property_id = str(prop.get("id") or "").strip()
    if not property_id or property_id in assigned_property_ids:
        return ""
    if prop.get("owner_eid") is not None:
        return ""

    metadata = _property_metadata(prop)
    if not str(metadata.get("business_name") or "").strip():
        return ""

    founder_name = _business_founder_name(prop)
    if not founder_name:
        return ""

    identities = sim.ecs.get(CreatureIdentity)
    for identity in identities.values():
        existing_name = str(getattr(identity, "personal_name", "") or "").strip().lower()
        if existing_name == founder_name.lower():
            return ""

    roll = random.Random(f"{sim.seed}:business_founder_keyholder:{property_id}").random()
    if roll >= _business_founder_keyholder_chance(prop):
        return ""
    return founder_name


def spawn_chunk_npcs(sim, chunk, property_records, reserved_property_ids=None):
    _ground_records, population_records = ensure_chunk_population_state(sim)
    key = (int(chunk.get("cx", 0)), int(chunk.get("cy", 0)))
    if key in population_records:
        return list(population_records[key])

    rng = random.Random(f"{sim.seed}:{key[0]}:{key[1]}:chunk_population")
    reserved_property_ids = {
        str(value)
        for value in (reserved_property_ids or ())
        if str(value).strip()
    }

    props = []
    for record in property_records:
        prop = sim.properties.get(record.get("id"))
        if not prop:
            continue
        if str(prop.get("kind", "")).strip().lower() != "building":
            continue
        props.append(prop)

    homes = [prop for prop in props if _property_archetype(prop) in RESIDENTIAL_ARCHETYPES and prop.get("id") not in reserved_property_ids]
    workplaces = [prop for prop in props if _property_archetype(prop) not in RESIDENTIAL_ARCHETYPES]
    area_type = str(chunk.get("district", {}).get("area_type", "city")).strip().lower() or "city"
    worker_cap = 4 if area_type == "city" else 2
    resident_cap = 3 if area_type == "city" else 1
    work_loads = {}
    home_loads = {}
    economy_profile = chunk_economy_profile(sim, chunk)
    current_hour = world_hour(sim)
    spawned = []
    founder_assigned_property_ids = set()
    actor_contexts = {}

    worker_candidates = list(workplaces)
    rng.shuffle(worker_candidates)
    for workplace_prop in worker_candidates:
        if len(spawned) >= worker_cap:
            break
        if rng.random() > _property_kind_weight(workplace_prop):
            continue

        archetype = _property_archetype(workplace_prop)
        role = "guard" if archetype in SECURITY_ARCHETYPES else "worker"
        shift_window = _shift_window_for(archetype, role, rng)
        career = pick_career_for_workplace(
            sim.world,
            rng,
            archetype=archetype,
            economy_profile=economy_profile,
        )
        home_prop = _pick_home(rng, homes, home_loads, fallback_prop=workplace_prop if area_type != "city" else None)
        role = _chaotic_role_for_resident(
            rng,
            area_type,
            home_prop=home_prop,
            workplace_prop=workplace_prop,
            current_role=role,
        )
        home_anchor = _focus_position(home_prop) if home_prop else _focus_position(workplace_prop)
        work_anchor = _focus_position(workplace_prop)
        organization_eid = ensure_property_organization(sim, workplace_prop)
        workplace = {
            "property_id": workplace_prop.get("id"),
            "building_id": _property_metadata(workplace_prop).get("building_id"),
            "archetype": archetype,
            "organization_eid": organization_eid,
        }
        founder_name = _business_founder_candidate(sim, workplace_prop, founder_assigned_property_ids)
        if founder_name:
            workplace["authority_role"] = "manager"
        occupation = Occupation(career=career, workplace=workplace, shift_start=shift_window[0], shift_end=shift_window[1])
        at_work = work_shift_active(sim, occupation=occupation, workplace_prop=workplace_prop, hour=current_hour, role=role)
        spawn_prop = workplace_prop if at_work else (home_prop or workplace_prop)
        spawn_zone = _spawn_zone_for_actor(role, spawn_prop, at_work=at_work)
        tile = _pick_tile(sim, _tile_candidates_for_property(sim, spawn_prop, spawn_zone), rng, allow_entities=False)
        if not tile:
            continue
        if home_prop and spawn_prop is home_prop:
            home_anchor = tile
        if workplace_prop and at_work and spawn_prop is workplace_prop:
            work_anchor = tile

        eid = _spawn_human(
            sim,
            rng,
            role=role,
            position=tile,
            career=career,
            workplace=workplace,
            home=home_anchor,
            work=work_anchor,
            shift_window=shift_window,
            workplace_prop=workplace_prop,
            home_prop=home_prop,
            personal_name=founder_name or None,
        )
        if founder_name:
            founder_assigned_property_ids.add(str(workplace_prop.get("id") or ""))
        spawned.append(eid)
        actor_contexts[eid] = {
            "home_property_id": home_prop.get("id") if isinstance(home_prop, dict) else None,
            "home_anchor": home_anchor,
            "work_property_id": workplace_prop.get("id") if isinstance(workplace_prop, dict) else None,
        }

    resident_candidates = list(homes)
    rng.shuffle(resident_candidates)
    for home_prop in resident_candidates:
        if len(spawned) >= worker_cap + resident_cap:
            break
        if rng.random() > (0.62 if area_type == "city" else 0.78):
            continue

        role = "civilian"
        workplace_prop = None
        career = None
        shift_window = None
        if workplaces and rng.random() < 0.68:
            workplace_prop = _pick_workplace(rng, workplaces, work_loads, limit=2)
            if workplace_prop:
                role = "worker"
                career = pick_career_for_workplace(
                    sim.world,
                    rng,
                    archetype=_property_archetype(workplace_prop),
                    economy_profile=economy_profile,
                )
                shift_window = _shift_window_for(_property_archetype(workplace_prop), role, rng)
        role = _chaotic_role_for_resident(
            rng,
            area_type,
            home_prop=home_prop,
            workplace_prop=workplace_prop,
            current_role=role,
        )
        if role == "drunk":
            workplace_prop = None
            career = "drunk"
            shift_window = None
        elif role == "thief":
            career = "thief"
            if workplace_prop and rng.random() < 0.55:
                workplace_prop = None
                shift_window = None
        home_anchor = _focus_position(home_prop)
        work_anchor = _focus_position(workplace_prop) if workplace_prop else None
        workplace = None
        occupation = None
        if workplace_prop and career:
            organization_eid = ensure_property_organization(sim, workplace_prop)
            workplace = {
                "property_id": workplace_prop.get("id"),
                "building_id": _property_metadata(workplace_prop).get("building_id"),
                "archetype": _property_archetype(workplace_prop),
                "organization_eid": organization_eid,
            }
            founder_name = _business_founder_candidate(sim, workplace_prop, founder_assigned_property_ids)
            if founder_name:
                workplace["authority_role"] = "manager"
            occupation = Occupation(
                career=career,
                workplace=workplace,
                shift_start=shift_window[0],
                shift_end=shift_window[1],
            )
        else:
            founder_name = ""
        at_work = bool(workplace_prop and occupation and work_shift_active(sim, occupation=occupation, workplace_prop=workplace_prop, hour=current_hour, role=role))
        spawn_prop = workplace_prop if at_work else home_prop
        spawn_zone = _spawn_zone_for_actor(role, spawn_prop, at_work=at_work)
        tile = _pick_tile(sim, _tile_candidates_for_property(sim, spawn_prop, spawn_zone), rng, allow_entities=False)
        if not tile:
            continue
        if home_prop and spawn_prop is home_prop:
            home_anchor = tile
        if workplace_prop and at_work and spawn_prop is workplace_prop:
            work_anchor = tile

        eid = _spawn_human(
            sim,
            rng,
            role=role,
            position=tile,
            career=career or "resident",
            workplace=workplace,
            home=home_anchor,
            work=work_anchor,
            shift_window=shift_window,
            workplace_prop=workplace_prop,
            home_prop=home_prop,
            personal_name=founder_name or None,
        )
        if founder_name and workplace_prop:
            founder_assigned_property_ids.add(str(workplace_prop.get("id") or ""))
        spawned.append(eid)
        actor_contexts[eid] = {
            "home_property_id": home_prop.get("id") if isinstance(home_prop, dict) else None,
            "home_anchor": home_anchor,
            "work_property_id": workplace_prop.get("id") if isinstance(workplace_prop, dict) else None,
        }

    wildlife_target_count = _wildlife_target_count(_chunk_descriptor(sim, chunk), rng)
    if wildlife_target_count > 0:
        spawned.extend(
            _spawn_chunk_wildlife(
                sim,
                chunk,
                property_records,
                rng,
                target_count=wildlife_target_count,
            )
        )

    _seed_chunk_social_bonds(sim, actor_contexts)
    population_records[key] = list(spawned)
    sim.property_registry_dirty = True
    return list(spawned)
